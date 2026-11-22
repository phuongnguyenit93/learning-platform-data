# Phân biệt dữ liệu ràng buộc trực tiếp với tra cứu bằng phản chiếu trong AOP

## 1. Vấn đề cốt lõi: Advice lấy dữ liệu từ đâu?

Khi lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một **advice** cần dữ liệu về sự kiện đang được can thiệp để quyết định ghi log, kiểm tra, đo đạc, đổi tham số hoặc xử lý kết quả. Hai cách lấy thông tin rất dễ bị đánh đồng:

1. **Ràng buộc trực tiếp (direct binding):** thông qua **pointcut** và hệ thống tham số của advice, công cụ AOP truyền thẳng các giá trị ngữ cảnh được lựa chọn vào các biến có kiểu được khai báo. Ví dụ ràng buộc đối số String, đối tượng target hoặc exception được ném.
2. **Tra cứu qua metadata hoặc phản chiếu (reflection/introspection):** advice hoặc interceptor có một đối tượng mô tả join point, chữ ký hay Method/Class/Annotation, sau đó chủ động xem thông tin của phần tử chương trình, ví dụ tên method, kiểu tham số, annotation, nơi khai báo hoặc cấu trúc class.

Hai cách **không đối lập tuyệt đối**. Một advice có thể bind trực tiếp giá trị đối số và đồng thời đọc metadata của phương thức bằng reflection. Một cơ chế AOP cũng có thể **dùng reflection nội bộ để hiện thực việc binding**; điều quan trọng là **hợp đồng của code advice với dữ liệu** chứ không phải phỏng đoán công cụ đã sinh những instruction nào.

Cần phân biệt ba lớp dữ liệu:

- **Giá trị runtime:** object nào đang nhận lời gọi, String hiện tại là gì, exception nào vừa phát sinh, return value nào vừa được trả.
- **Join point metadata:** điểm đó là call hay execution, chữ ký được hệ thống AOP mô tả, vị trí mã hoặc ngữ cảnh thực thi được cung cấp.
- **Java reflection metadata:** Method, Constructor, Field, Class, parameter types, annotation có retention phù hợp, access modifiers...

Một object **Method** mô tả khai báo phương thức; nó **không chứa** giá trị đối số của một lần gọi cụ thể. Ngược lại, một String được bind từ **args** là giá trị tham số của **lần gọi hiện tại**, không tự nói method đó có annotation nào.

## 2. Nền tảng: Join point, pointcut, advice, binding

| Thành phần | Vai trò |
|---|---|
| **Join point** | Điểm thực thi mà mô hình AOP hỗ trợ nhận diện, ví dụ method call, method execution, constructor, field access. |
| **Pointcut** | Quy tắc chọn join point theo chữ ký, kiểu, vị trí, annotation, runtime context hoặc kết hợp của chúng. |
| **Advice** | Hành vi được áp dụng tại các join point khớp, có thể chạy trước/sau/bao quanh. |
| **Binding** | Truyền những giá trị liên quan đến join point vào tham số được khai báo trong advice. |
| **Join point descriptor** | Đối tượng/API mô tả join point, có thể cung cấp signature, args, this, target hay source location. |
| **Reflection** | API để tra cứu hoặc tương tác với khai báo class/method/field/constructor và metadata runtime. |

Trong mô hình AOP có ràng buộc dữ liệu, pointcut vừa **chọn điểm**, vừa có thể **cung cấp reference** hoặc **giá trị** cho advice. Ví dụ một selector chọn method execution có argument **String orderId**, rồi bind đúng **orderId của lượt thực thi hiện tại**.

Mô hình:

~~~text
Caller -> join point khớp pointcut
                  |
                  +-- Runtime value: orderId = "A42"
                  |         |
                  |         v
                  |   Direct binding:
                  |   advice(String orderId)
                  |
                  +-- Metadata: chữ ký và nơi khai báo
                            |
                            v
                      Join point descriptor
                            |
                            v
                       Class / Method
                       reflection lookup
~~~

Đừng đặt đồng nhất “có đối tượng join point” với “đang dùng Java reflection”. Ví dụ API kiểu **getArgs()** do một join point descriptor cung cấp là cách lấy **giá trị runtime**; còn **Method.getParameterTypes()** là cách lấy **kiểu được khai báo**. Chúng trả lời hai câu hỏi khác nhau.

## 3. Binding trực tiếp hoạt động như thế nào?

### 3.1. Ràng buộc giá trị đối số

Một mô hình AOP có pointcut designator dạng **args(...)** có thể cho advice nhận trực tiếp đối số theo **tên biến formal** và **kiểu khai báo**.

Ví dụ cú pháp minh họa theo ngôn ngữ AspectJ, không phải file Java độc lập cho javac:

~~~java
before(String orderId, int quantity):
        execution(* example.OrderService.submit(String, int))
        && args(orderId, quantity) {
    System.out.println("orderId=" + orderId + ", quantity=" + quantity);
}
~~~

Trong mô hình này:

- Pointcut chọn **execution** của phương thức phù hợp chữ ký.
- **args(orderId, quantity)** bind hai đối số tại join point vào formal parameters.
- Thân advice sử dụng các biến có tên và kiểu rõ ràng: **orderId** là String, **quantity** là int.
- Không cần gọi **getMethod(...)**, duyệt parameter array, cast thủ công hoặc suy luận đối số thứ hai thuộc kiểu nào.

Chính xác cú pháp binding, primitive boxing, phạm vi join point và khả năng kiểu tương thích phải theo quy tắc của ngôn ngữ AOP cụ thể. Ví dụ này chỉ diễn giải khả năng binding trong một ngôn ngữ có nó.

### 3.2. Ràng buộc đối tượng đang thực thi và target

Trong những mô hình có designator **this(Type)** và **target(Type)**, có thể bind reference đến đối tượng tương ứng:

~~~text
pointcut selected(current, receiver):
    method-call of Service.execute(...)
    AND this(current)
    AND target(receiver)
~~~

Đây là giả mã, không phải cú pháp chung của tất cả compiler.

- Ở **method call**, đối tượng đang thực thi mã tại điểm gọi và đối tượng target nhận lời gọi có thể khác nhau.
- Ở **method execution** của instance method, hai vai trò đó thường cùng là receiver theo mô hình AspectJ.
- Ở static context, không được giả định có một instance this/target như khi gọi method instance.

Nếu advice nhận object đã bind, nó có thể dùng API công khai của object đó mà không cần reflection. Nhưng việc bind một reference **không biến object chưa hoàn tất initialization thành an toàn để sử dụng**.

### 3.3. Ràng buộc return value và exception

Một số loại advice hỗ trợ bind giá trị từ giai đoạn hoàn tất:

~~~text
after-returning(result):
    examine return value of the selected join point

after-throwing(error):
    examine exception raised by the selected join point
~~~

Đây là giả mã trung lập công cụ. Return value chỉ có sau khi join point hoàn tất bình thường; Throwable tương ứng chỉ có ở đường ngoại lệ. **Before advice** không thể bind trước giá trị trả về tương lai như thể target đã chạy.

Đây là khác biệt quan trọng so với Method reflection: **Method.getReturnType()** có thể cho biết kiểu trả về được khai báo bất cứ lúc nào metadata truy cập được; nó **không biết giá trị trả về của một lần invocation**. Để lấy giá trị cụ thể, cần join point context ở thời điểm thích hợp.

### 3.4. Ràng buộc annotation

Một số pointcut cho bind **annotation instance** gắn với phần tử chương trình đang được chọn, chẳng hạn annotation tại method execution. Advice có thể đọc thuộc tính annotation trực tiếp qua reference được bind.

Tuy nhiên, cần phân biệt:

- Annotation trên **method khai báo ở interface**.
- Annotation trên **method implementation**.
- Annotation trên **method override**.
- Annotation trên **class** hoặc đối tượng target.
- Annotation nhìn thấy được theo **RetentionPolicy.RUNTIME** khi dùng Java reflection ở runtime.

Method annotation trong Java **không tự động được kế thừa qua overriding**. Một engine có thể chủ động tra cứu khai báo ở superclass/interface theo chính sách riêng, nhưng không được suy đó là hành vi của Java reflection trên chính Method override.

## 4. Reflection: tra cứu thông tin về khai báo

**Java reflection** cung cấp các lớp như:

- **Class<?>:** kiểu runtime, superclass, interfaces, fields, methods, annotations và các thành viên khác.
- **java.lang.reflect.Method:** tên, declaring class, parameter types, return type, modifiers, annotations; có thể gọi method bằng **invoke**.
- **Constructor<?>:** thông tin về constructor và khả năng tạo object bằng reflection.
- **Field:** thông tin về trường dữ liệu và khả năng đọc/ghi theo quyền truy cập.
- **java.lang.reflect.Parameter:** metadata của formal parameter, bao gồm tên khi metadata phù hợp được lưu.

Ví dụ:

~~~java
Method method = SomeService.class.getMethod("process", String.class, int.class);
System.out.println(method.getName());
System.out.println(method.getReturnType());
~~~

Đây là đoạn minh họa Java, cần import **java.lang.reflect.Method** và định nghĩa SomeService cùng process để chạy. Nó tra cứu **khai báo method** theo tên và **chính xác các parameter Class**, không tra cứu giá trị String/int của invocation nào.

**Reflection không tự giúp biết caller đã truyền nội dung gì trong một lần gọi thật.** Muốn lấy giá trị invocation cần code đang có argument values, API interceptor cung cấp chúng hoặc join point context tương ứng. Method object không giữ lịch sử những lần invoke.

### 4.1. getMethod và getDeclaredMethod khác nhau

- **getMethod(name, parameterTypes...)** tìm **public** method theo quy tắc API, có thể bao gồm method public được kế thừa.
- **getDeclaredMethod(name, parameterTypes...)** tìm method được **khai báo trực tiếp trong Class** được gọi, không tìm method kế thừa và không yêu cầu nó public.
- Với overload, phải truyền đúng **parameter types**, không chỉ tên method.
- Với bridge/synthetic methods do compiler sinh, một số kết quả phản chiếu có thể khiến việc lựa chọn method cần xử lý cẩn thận.

Nếu subclass không override một method public của Base, **Child.class.getMethod(...)** có thể trả một Method mà **getDeclaringClass()** là Base. Nếu Child override method đó, Method khai báo tại Child có thể khác metadata so với Method ở Base.

### 4.2. Reflection tìm được method nhưng không đồng nghĩa được phép gọi

Java có các quy tắc kiểm soát truy cập; mô-đun trong hệ thống Java hiện đại cũng có ràng buộc **module boundaries**. Có thể lấy metadata của một member nhưng vẫn không có quyền tùy ý truy cập nó. Việc gọi **setAccessible(true)** không bảo đảm sẽ thành công qua mọi module; có thể gặp **InaccessibleObjectException** hoặc lỗi truy cập.

Một advice chỉ cần metadata của public API thường không nên cố phá encapsulation bằng deep reflection. Nếu tính năng cần truy cập member không public, hãy xem xét API chính thức, module openness và giới hạn được quản lý rõ ràng.

### 4.3. Reflection cần metadata tồn tại tại runtime

Annotation muốn lấy bằng **Method.getAnnotation(...)** thường cần được giữ ở runtime bằng **RetentionPolicy.RUNTIME**. Không phải annotation nào xuất hiện ở mã nguồn cũng được Java reflection đọc thấy.

Tên tham số source của Method không luôn được giữ mặc định trong class file theo cách reflection đọc như tên gốc. Khi cần tên tham số, một trong những yếu tố liên quan là cách biên dịch, chẳng hạn flag **-parameters**. Trong AOP, đôi khi có hệ thống binding dựa tên formal parameters hoặc cần metadata riêng; phải phân biệt điều đó với kiểu được biết nhờ chữ ký bytecode.

## 5. Bảng so sánh: binding trực tiếp và reflection

| Tiêu chí | Binding trực tiếp vào advice | Tra cứu qua reflection/metadata |
|---|---|---|
| **Đối tượng dữ liệu chính** | Giá trị hoặc object của một join point đang chạy | Thông tin về method/class/field/annotation; có thể kết hợp với args runtime |
| **Hình thức truy cập** | Formal parameter có tên và type | Method, Class, Annotation, Signature, Object[] và API tra cứu |
| **Phân biệt lượt gọi** | Giá trị được bind theo mỗi invocation | Metadata Method thường dùng lại giữa nhiều invocations; args runtime phải lấy riêng |
| **Độ an toàn kiểu** | Có thể được kiểm tra ở mức ngôn ngữ AOP/compile, tùy binder | Thường cần cast, kiểm tra kiểu và xử lý lỗi runtime |
| **Phù hợp với** | Đã biết chính xác giá trị cần lấy | Logging tổng quát, kiểm tra metadata, dispatch động nhiều signature |
| **Chi phí** | Có thể được tối ưu bằng weaving | Lookup/annotation traversal/invoke có overhead riêng; cần đo thực tế |
| **Phạm vi áp dụng** | Phụ thuộc pointcut và kiểu formal tương thích | Phụ thuộc đối tượng metadata sẵn có, quyền truy cập và engine |
| **Độ linh hoạt** | Tốt cho nhu cầu cố định, tường minh | Tốt khi cần khám phá cấu trúc nhiều method khác nhau |
| **Ảnh hưởng refactor** | Đổi type/signature có thể gây lỗi biên dịch hoặc làm pointcut không khớp | String tên method, lookup và cast có thể lỗi runtime hoặc trả metadata khác |
| **Kết quả của method** | Có thể bind trong after-returning/around phù hợp | Method object chỉ biết return type; giá trị thực phải lấy từ invocation |
| **Ngoại lệ target** | Có thể bind tại after-throwing phù hợp | Method.invoke có thể bọc exception trong InvocationTargetException |
| **Bảo mật** | Không tự có quyền truy cập mọi field của object | Reflection bị giới hạn bởi access control và module boundaries |

**Không kết luận binding luôn nhanh hơn reflection một số lần cố định.** Những chương trình khác nhau có weaving strategy, chi phí dispatch, caching, hot path và workload khác nhau. Sự khác biệt an toàn nhất khi thiết kế là **mô hình dữ liệu và độ tường minh của hợp đồng**, rồi mới benchmark hiệu năng.

## 6. Ví dụ Java 17 chạy được: dữ liệu có kiểu và metadata qua Method

Ví dụ sau mô phỏng hai cách xử lý tại một biên lời gọi:

1. **TypedBoundary:** method có signature được biết trước; lấy trực tiếp **String text**, **int count** và **target** bằng các tham số Java có kiểu.
2. **ReflectiveBoundary:** dùng **JDK dynamic proxy**; handler nhận **Method** và **Object[] args**, tra method implementation và annotation bằng reflection, rồi gọi target.

Đây là **chương trình Java độc lập để hiểu sự khác biệt dữ liệu**, không phải một aspect được dệt bằng compiler AOP. Đường TypedBoundary giống về **giao diện dữ liệu tường minh** với direct binding nhưng là decorator Java viết tay; đường proxy biểu diễn introspection runtime.

Tạo file **AdviceDataDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AdviceDataDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Tracked {
        String value();
    }

    interface Formatter {
        String format(String text, int count);
    }

    static final class FormatterImpl implements Formatter {
        @Override
        @Tracked("format-impl")
        public String format(String text, int count) {
            System.out.println("core: format");
            return text.repeat(count);
        }
    }

    static final class TypedBoundary implements Formatter {
        private final Formatter target;

        TypedBoundary(Formatter target) {
            this.target = target;
        }

        @Override
        public String format(String text, int count) {
            System.out.println("bound: text=" + text + ", count=" + count
                    + ", target=" + target.getClass().getSimpleName());
            return target.format(text, count);
        }
    }

    static Formatter reflectiveBoundary(Formatter target) {
        return (Formatter) Proxy.newProxyInstance(
                Formatter.class.getClassLoader(),
                new Class<?>[]{Formatter.class},
                (proxy, method, args) -> {
                    System.out.println("reflect: declaring="
                            + method.getDeclaringClass().getSimpleName()
                            + ", args=" + args.length);

                    Method implementationMethod = target.getClass()
                            .getMethod(method.getName(), method.getParameterTypes());
                    Tracked marker = implementationMethod.getAnnotation(Tracked.class);
                    System.out.println("reflect: marker="
                            + (marker == null ? "none" : marker.value()));

                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException exception) {
                        throw exception.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Formatter core = new FormatterImpl();
        Formatter typed = new TypedBoundary(core);
        Formatter reflected = reflectiveBoundary(core);

        System.out.println("typed result=" + typed.format("ha", 2));
        System.out.println("reflect result=" + reflected.format("go", 3));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AdviceDataDemo.java
java AdviceDataDemo
~~~

**Stdout chính xác:**

~~~text
bound: text=ha, count=2, target=FormatterImpl
core: format
typed result=haha
reflect: declaring=Formatter, args=2
reflect: marker=format-impl
core: format
reflect result=gogogo
~~~

### 6.1. Nhánh typed đang nhận dữ liệu gì?

- Tham số **text** là String ngay trong signature của method **format**.
- Tham số **count** là int, không cần cast từ **Object[]**.
- **target** là reference kiểu Formatter được truyền vào constructor TypedBoundary.
- Sau khi ghi nhận, code gọi **target.format(text, count)** qua interface có kiểu.

Trong một advice AOP thực, code có thể đạt mức rõ ràng tương tự bằng pointcut **args(text,count)** và **target(...)** được bind. Nhưng ví dụ dùng **decorator viết tay** để chạy chỉ với JDK, chứ không khẳng định đó là direct binding do một weaver tạo tự động.

### 6.2. Nhánh reflection đang thấy những đối tượng nào?

InvocationHandler nhận **Method method** là phương thức giao diện Formatter mà proxy đang thực hiện. Vì vậy:

~~~text
reflect: declaring=Formatter
~~~

Nó không tự nói method được khai báo trực tiếp tại implementation, dù target runtime là FormatterImpl. Để đọc annotation đã được đặt lên method triển khai, handler cố ý tìm:

~~~java
Method implementationMethod = target.getClass()
        .getMethod(method.getName(), method.getParameterTypes());
~~~

Sau đó lấy annotation **Tracked** có runtime retention. Khi phương thức triển khai có **@Tracked("format-impl")**, log là:

~~~text
reflect: marker=format-impl
~~~

Nếu chỉ tìm annotation trên Method đại diện cho interface, có thể không thấy annotation được đặt **chỉ ở implementation**. Đây là ví dụ về sự khác nhau giữa **Method ở biên proxy** và **Method chứa metadata nghiệp vụ**.

### 6.3. Nhánh reflective gọi target như thế nào?

Handler dùng **method.invoke(target,args)** và truyền những đối số runtime mà proxy nhận được. Nếu phương thức gốc ném exception, Java reflection có thể bọc nó trong **InvocationTargetException**; code bắt và ném lại **getCause()** để tránh chuyển một exception bọc thành lỗi mới ngoài ý định.

Ví dụ hiện tại thành công, nên cả nhánh typed và reflective đều trả về String từ Core. Chúng không chứng minh công cụ AOP bất kỳ luôn dùng reflection invocation; bytecode weaving có thể tạo mã thực thi khác mà vẫn cung cấp metadata tương đương cho advice.

### 6.4. Hai đường không tương đương về bao phủ

TypedBoundary và ReflectiveBoundary được đưa vào biến **typed** và **reflected**. Nếu caller giữ reference **core** rồi gọi trực tiếp, cả hai lớp bao ngoài đều bị bỏ qua. Một bytecode weaver gắn advice trực tiếp vào execution của implementation có thể quan sát những đường khác, tùy phạm vi weave và loại join point.

Đừng dùng việc example handler nhận Method để kết luận AOP là “Java reflection tự động”. AOP mô tả **pointcut và lời khuyên tại join point**; reflection chỉ là một kỹ thuật lấy metadata hoặc dispatch trong số các kỹ thuật có thể dùng.

## 7. Khi nào đọc thông tin từ join point descriptor?

Một số mô hình AOP cung cấp đối tượng mô tả join point. Ví dụ các API phổ biến về mặt khái niệm:

~~~text
joinPoint.getKind()          -> loại join point
joinPoint.getSignature()     -> mô tả chữ ký
joinPoint.getArgs()          -> Object[] đối số runtime nếu được hỗ trợ
joinPoint.getThis()          -> đối tượng đang thực thi nếu có
joinPoint.getTarget()        -> đối tượng đích nếu có
joinPoint.getSourceLocation()-> vị trí source nếu metadata sẵn có
~~~

Đây là **minh họa dạng API**, không phải một interface Java độc lập được khai báo trong bài. Tên method trên một công cụ cụ thể có thể khác và metadata có thể thiếu ở một số loại join point.

Với một API như AspectJ **thisJoinPoint**, thông tin được cung cấp không đồng nhất với Java reflection:

- **getArgs()** trả **giá trị đối số runtime** của join point được mô tả. Đây là thông tin invocation.
- **getSignature()** trả **mô tả chữ ký join point**, không phải lúc nào cũng là Method reflection object.
- Một cơ chế lấy **Method** từ chữ ký có thể chỉ dùng được cho đúng loại join point và đúng kiểu signature được hỗ trợ.
- **getThis()** và **getTarget()** biểu thị vai trò runtime ở join point; không phải truy vấn tất cả instance của một class.

Chỉ cần tên method và argument count cho logging tổng quát? Descriptor có thể đủ, chưa cần thực hiện Java reflection để tìm lại Method. Cần đọc annotation trên một implementation method? Có thể phải kết hợp metadata do engine cung cấp với Java reflection hoặc API annotation binding tương ứng.

### 7.1. Static information và dynamic information

| Dữ liệu | Thường có thể tách khỏi từng invocation? |
|---|---|
| Tên method, parameter types được khai báo | Có thể ổn định trên nhiều lượt của cùng điểm |
| Declaring class/chữ ký join point | Thường ổn định theo loại điểm đã được weave |
| Giá trị String/number trong argument | Không; thay đổi theo lượt gọi |
| Target runtime subtype | Có thể thay đổi theo lượt gọi |
| Return value | Chỉ có tại đường hoàn tất thích hợp |
| Exception object | Chỉ có khi join point thất bại |
| Annotation trên Method được chọn | Metadata tương đối ổn định theo khai báo nhưng phương thức được chọn phải chính xác |

Nhiều API AOP cho khả năng lấy một **static part** của join point để tái sử dụng thông tin không đổi giữa invocations. Điều này hữu ích cho ghi trace nhẹ hoặc caching metadata. Nhưng không được cache **args runtime** như thể chúng là static metadata.

## 8. Chọn binding hay reflection theo nhu cầu

### 8.1. Chọn binding khi giá trị cần lấy đã biết

Ví dụ advice chỉ cần **orderId** và **quantity** của đúng một method hoặc họ method có hợp đồng tương ứng.

Ưu điểm:

- Biến có tên, type và mục đích rõ.
- Ít Object[] access, cast và lookup động trong thân advice.
- Dễ gắn vào test vì dữ liệu cần dùng là input tường minh.
- Compiler hoặc AOP compiler có thể phát hiện một số mismatch về signature và binding.

Bất lợi:

- Advice gắn tương đối chặt với chữ ký hoặc pointcut cụ thể.
- Refactor thay danh sách/thứ tự tham số có thể cần cập nhật pointcut.
- Một advice phải hỗ trợ rất nhiều signature khác nhau có thể trở nên khó khai báo formal parameters chung.

### 8.2. Chọn metadata/reflection khi cần khám phá tổng quát

Ví dụ một aspect logging chung cho hàng trăm method có chữ ký khác nhau muốn ghi:

- Tên method và declaring type.
- Những annotation được gắn tại method implementation.
- Kiểu tham số được khai báo.
- Một dấu nhận diện cho nhóm operation dựa trên metadata.
- Thông tin về một số argument theo policy mà không cần biết trước signature.

Ưu điểm:

- Một cơ chế chung có thể áp dụng nhiều method với signature khác nhau.
- Phù hợp hạ tầng logging, tracing, metric, kiểm tra cấu hình hoặc kiểm toán metadata.
- Cho phép xử lý annotation-driven behavior khi không thể bind một formal type chung cho mọi method.

Bất lợi:

- Có thể phải cast và xử lý type errors ở runtime.
- Lookup string-based dễ nhầm overload, declaring class, bridge/synthetic method.
- Reflection có vấn đề quyền truy cập và module boundaries.
- Nếu dùng Method.invoke, phải xử lý exception wrapper, return type, primitive boxing.
- Quá rộng dễ thu thập dữ liệu nhạy cảm ngoài phạm vi dự kiến.

### 8.3. Kết hợp khi có hai nhu cầu

Một thiết kế cân bằng:

~~~text
Pointcut chọn đúng các method có @Tracked
     |
     +--> Bind target và argument quan trọng có type
     |
     +--> Đọc annotation/metadata chỉ khi cần
     |
     +--> Advice thực hiện logging đã giới hạn dữ liệu
~~~

Có thể tận dụng annotation binding nếu công cụ hỗ trợ để tránh tự lookup Method ở mỗi lần. Ngược lại, với một handler thực sự tổng quát không có formal signature ổn định, nhận Method và Object[] là lựa chọn hợp lý nếu code kiểm tra kiểu chặt và thực sự cần.

## 9. Rủi ro: Method ở interface khác Method ở implementation

Giả sử có:

~~~java
interface Operation {
    void execute();
}

class OperationImpl implements Operation {
    @Override
    @Audited
    public void execute() {
        // Nghiệp vụ
    }
}
~~~

Đây là **mã minh họa**, annotation Audited cần được định nghĩa để biên dịch. Một proxy chặn qua interface có thể nhận Method của **Operation**, còn annotation chỉ gắn với **OperationImpl.execute()**. Nếu gọi **method.getAnnotation(Audited.class)** trên Method của interface, kết quả có thể là null.

Cách xử lý tùy chính sách:

1. Nếu annotation trên interface chính là **hợp đồng**, tìm tại interface.
2. Nếu annotation trên implementation chính là **hợp đồng**, tìm method implementation tương ứng.
3. Nếu cần tìm theo cả interface và superclass, phải đặc tả **thứ tự ưu tiên khi metadata xung đột**.
4. Nếu subclass override method, method annotation không tự gắn vào override; policy có muốn nhận annotation từ superclass không?
5. Nếu method được tạo bridge bởi compiler, cần xét cách engine/lookup liên kết bridge với implementation.

Không có quy tắc chung “annotation sẽ tự được thừa kế” khi chỉ gọi Java Method.getAnnotation. Những giải pháp duyệt hierarchy thủ công hoặc metadata resolver riêng là **cơ chế bổ sung**, không phải mặc định của Java reflection.

## 10. Bridge methods, overload và generic type erasure

### 10.1. Overload có cùng tên

~~~java
void save(String value);
void save(String value, int version);
~~~

Đây là khai báo minh họa. **getMethod("save", String.class)** chọn overload thứ nhất, còn **getMethod("save", String.class, int.class)** chọn overload thứ hai. Chỉ log method name rồi chọn theo tên không đủ phân biệt.

Khi bind argument cho advice, pointcut cũng phải biết đang chọn overload nào nếu chúng có semantics khác. Một rule ghi log mọi method tên save có thể khớp cả hai nhưng không chắc mọi method có chung danh sách formal parameters để bind.

### 10.2. Generics và bridge

Java generics sử dụng **type erasure** ở bytecode. Khi triển khai hoặc override generic method, compiler có thể sinh **bridge method** (synthetic) để duy trì dispatch và tương thích. Reflection có API như **isBridge()** và **isSynthetic()** để nhận diện một số method như vậy.

Một công cụ AOP cấp cao có thể tránh những duplicate events theo cách riêng; một công cụ instrument bytecode ở mức thấp có thể nhìn nhiều method mà Java source chỉ hiển thị một. Khi pointcut và reflection cùng tham gia, cần test:

- Advice có chạy đúng một lần cho một thao tác nghiệp vụ không?
- Method object nào được dùng để tìm annotation?
- Metadata đang lấy từ bridge hay method implementation?
- Generic signature được diễn giải theo source type hay erased type?

Nếu reflection lookup trả Method không đúng khai báo mong muốn, bạn có thể đọc sai annotation hoặc kiểm tra kiểu không đúng. Đừng dựa vào tên method và số parameter làm khóa duy nhất khi có overload/bridge.

## 11. Null, primitive và mảng đối số

Binding trực tiếp với **int count** khác với đọc phần tử **args[1]** là Object rồi cast thành int:

~~~java
int count = (int) args[1];
~~~

Đoạn Java minh họa trên chỉ đúng nếu phần tử là wrapper tương thích để unbox, ví dụ Integer, và không phải null. Nếu null, có thể gặp NullPointerException; sai kiểu có thể gây ClassCastException.

Một số điểm cần kiểm tra:

- **Object[]** trong InvocationHandler có thể **null** nếu method không có đối số; không được luôn giả định **args.length** hợp lệ.
- Với method có đối số primitive, reflection/proxy dùng boxed values theo quy tắc API.
- Với varargs, tham số cuối có thể là array theo representation runtime, không tự là nhiều vị trí riêng.
- Giá trị object trong mảng có thể là subtype so với type được khai báo.
- Nếu mảng chỉ để quan sát, sửa phần tử của mảng không tự đồng nghĩa công cụ đã thay đối số được truyền tiếp cho target; khả năng thay argument phụ thuộc API proceed/invoke.

Binding có kiểu giảm nhu cầu cast thủ công nhưng **không tự thay thế kiểm tra null và domain invariants**. Một String được bind vẫn có thể null nếu method contract cho phép.

## 12. Hiệu năng: tránh giả định tuyệt đối

Một lời khuyên thường thấy là “binding luôn nhanh, reflection luôn chậm”. Điều này đơn giản hóa quá mức:

- **Direct binding** có thể được dệt thành đường truy cập ngắn đến argument/object.
- **Join point introspection** có thể tạo Object[] hoặc đối tượng mô tả, nhưng một số dữ liệu có thể được tối ưu hoặc tái sử dụng.
- **Reflection lookup** có thể tốn chi phí khi liên tục tìm Method/annotation, nhưng lookup được cache có thể giảm overhead.
- **Method.invoke** có chi phí và semantics khác gọi trực tiếp; JVM và phiên bản runtime có thể tối ưu ở mức khác nhau.
- **Advice làm network I/O hoặc ghi log đồng bộ** có thể chiếm áp đảo mọi chênh lệch binding/reflection.

Định hướng thiết kế:

1. Khi chỉ cần một vài argument đã biết, ưu tiên **binding có kiểu** nếu engine hỗ trợ.
2. Khi chỉ cần method name, dùng **metadata join point** sẵn có thay vì tìm lại Method theo tên nếu thông tin đã đủ.
3. Chỉ dùng Java reflection khi cần API thông tin hoặc invocation không được binding/descriptor cung cấp.
4. Nếu metadata là bất biến theo method, cân nhắc cache có vòng đời phù hợp. Không cache một giá trị argument của lượt gọi trước rồi tái sử dụng ở lượt sau.
5. Benchmark trên workload và cấu hình weaving/proxy thực tế; kiểm tra cả allocation, lock contention, GC, I/O và p95/p99 latency.

Không cache Method/metadata ở một static map không giới hạn trong hệ thống có class loader được tạo/xóa động mà chưa đánh giá rủi ro giữ reference khiến loader không giải phóng được.

## 13. Bảo mật và quyền truy cập metadata

Reflection có thể làm code nhìn thấy rất nhiều chi tiết về class. Binding cũng có thể làm advice nắm reference đến object và argument nhạy cảm. Hai cơ chế không cấp giấy phép thu thập toàn bộ dữ liệu.

Các rủi ro:

- Log **toString()** của một object có thể lộ token, mật khẩu, khóa hoặc thông tin cá nhân.
- Dùng reflection đọc tất cả field có thể vượt quá mục đích kiểm toán.
- Khi cố truy cập member không public, quy tắc encapsulation của Java và module system có thể chặn hành động.
- Annotation chứa cấu hình có thể cũng là thông tin cần bảo vệ.
- Advice lưu target trong collection sống lâu có thể tạo memory leak và giữ dữ liệu nhạy cảm ngoài vòng đời dự kiến.

Thực hành phù hợp là **data minimization**: chỉ bind hoặc tra cứu đúng giá trị cần cho chính sách, redaction các trường nhạy cảm, nêu rõ nơi và thời gian giữ dữ liệu, và kiểm thử trên đường thành công/lỗi.

## 14. Điều kiện kiểu và thời điểm binding

### 14.1. Type pattern không phải kiểm tra object runtime

Một biểu thức chọn **execution** theo chữ ký có thể match dựa type khai báo; còn điều kiện dạng **target(Type)** ở mô hình hỗ trợ có thể phụ thuộc **runtime receiver**. Hai điều kiện không luôn tương đương khi có kế thừa và override.

Ví dụ:

~~~java
Formatter service = new FormatterImpl();
service.format("x", 2);
~~~

Kiểu tĩnh của biến là Formatter; runtime target là FormatterImpl. Một advice bind object target có thể dùng interface Formatter hoặc kiểu rộng hơn; một đoạn reflection tìm implementation method qua target.getClass() có thể trả metadata thuộc FormatterImpl. Nhưng ở một call join point, signature được engine mô tả có thể phản ánh góc nhìn của caller/interface.

Đừng đoán declaring class dựa duy nhất vào runtime getClass() hoặc ngược lại. Hãy xác định **loại join point** và **đối tượng metadata** được engine cung cấp.

### 14.2. Binding diễn ra theo invocation

Giá trị được bind từ args/this/target tương ứng với **lượt thực thi cụ thể**. Nếu cùng một method gọi hai lần với argument khác nhau, binding sẽ nhận giá trị khác nhau.

Ngược lại, Method reflection object có thể được dùng cho nhiều lần gọi cùng method với các argument khác nhau. Nó không chứa “argument trước đó” hay “result của lần cuối”. Cố dùng Method metadata để suy ra giá trị runtime là sai mô hình.

### 14.3. Không có target ở mọi loại join point

Static method execution, static initialization và các điểm đặc thù có thể không có receiver instance. Một advice bind target cho những join point đó có thể không khớp hoặc không hợp lệ tùy ngôn ngữ.

Tương tự, constructor hoặc initialization join point có thể có đối tượng đang được xây dựng nhưng trạng thái chưa hoàn thiện; reflection để đọc tất cả field lúc đó đặc biệt nguy hiểm. Luôn đánh giá khả năng tồn tại của this/target và invariant trước khi dereference.

## 15. Exception: binding lỗi gốc so với InvocationTargetException

Giả sử target ném **IllegalArgumentException**. Nếu dùng một **after throwing advice** và engine hỗ trợ **throwing(exception)** binding, advice có thể nhận Throwable do join point báo cáo theo semantics của engine.

Nếu dùng Java Method.invoke:

~~~java
try {
    return method.invoke(target, args);
} catch (java.lang.reflect.InvocationTargetException exception) {
    throw exception.getCause();
}
~~~

Đoạn minh họa thuộc thân phương thức có return type tương thích, không phải một chương trình độc lập. Reflection bọc lỗi do target ném trong InvocationTargetException; nếu không tách cause, exception mà interceptor/caller thấy có thể khác với lỗi nghiệp vụ ban đầu.

Hai cơ chế có **ranh giới exception** khác nhau. Không nên so sánh chỉ dựa tên Throwable mà không xác định exception đến từ advice, target, reflection invocation hay proxy wrapping.

Với JDK dynamic proxy, nếu handler ném checked exception không phù hợp với những loại exception method interface khai báo, caller có thể nhận một wrapper như **UndeclaredThrowableException**. Test exception contract quan trọng không kém test return value.

## 16. Annotation binding và reflection: chọn đúng nguồn sự thật

Giả sử có chính sách quan sát bằng annotation:

~~~text
@Tracked(level = "INFO")
public void execute()
~~~

Điều này chỉ là ví dụ metadata, chưa định nghĩa đầy đủ một chương trình Java.

Bạn có hai cách nhìn:

**Cách A — Bind trực tiếp annotation từ pointcut:** nếu engine có designator và binding phù hợp, dùng annotation gắn với **join point được chọn**. Ưu tiên cách này khi semantics annotation của engine trùng chính xác policy muốn áp dụng.

**Cách B — Tìm annotation bằng Java reflection:** lấy Method phù hợp, gọi getAnnotation hoặc các API liên quan. Cần tự trả lời Method đó thuộc interface, implementation, superclass hay bridge. Nếu cần tìm nhiều cấp, phải chủ động thiết kế resolver cùng precedence.

Không nên trộn hai cách mà không kiểm tra sự tương đồng. Một engine có thể định nghĩa annotation pointcut theo execution declaration, trong khi code reflection lại đọc interface Method; kết quả khác nhau là có thể dự đoán, không mặc định do một trong hai bị lỗi.

Khi policy muốn đọc annotation ở implementation, test ít nhất các ca:

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Annotation chỉ ở interface | Reflection trên implementation Method có nhìn thấy không? |
| Annotation chỉ ở implementation | Method tại proxy handler thuộc loại nào? |
| Subclass override không lặp annotation | Policy có muốn áp dụng metadata ở base không? |
| Subclass kế thừa method không override | getDeclaringClass() là ai? |
| Bridge method từ generics | Method nào thực sự mang annotation? |
| Annotation có SOURCE/CLASS retention | Java runtime reflection có đọc thấy không? |

## 17. Tương tác với around advice

Around advice có thể cần cả **argument values** lẫn **return value**. Với engine có hỗ trợ thay argument khi proceed:

~~~text
around join point:
    boundInput = arguments at this invocation
    revisedInput = normalize(boundInput)
    raw = proceed(revisedInput)
    return transformResult(raw)
~~~

Đây là giả mã. Nếu API proceed yêu cầu truyền argument mới, việc chỉ sửa một biến local của advice không tự đổi input của target. Nếu code mutate object truyền theo reference, target có thể nhìn thấy side effect nhưng đó vẫn khác “thay reference argument”.

Reflection-based interceptor có thể thực hiện một việc tương tự bằng Method.invoke(target, newArgs), như ví dụ Java ở phần 6 dùng method.invoke(target,args). Nhưng nghĩa của **proceed** trong một woven join point không phải luôn bằng **Method.invoke**, đặc biệt khi quanh nó còn nhiều advice và thứ tự precedence.

Với before advice đơn thuần, chưa có return value của target để bind; với after returning có giá trị return nhưng không tự có quyền replay target; với around, việc gọi tiếp và thay output phụ thuộc contract cụ thể.

## 18. Những lỗi thường gặp

**Lỗi 1 — Nghĩ Method object chứa giá trị của invocation.** Method mô tả khai báo; đối số runtime phải lấy ở join point/interceptor đang xử lý lượt gọi.

**Lỗi 2 — Tưởng mọi introspection đều là Java reflection.** Join point descriptor có thể cung cấp signature và args; không cần Method reflection cho mọi câu hỏi.

**Lỗi 3 — Dùng Object[] quá nhiều dù formal binding đủ.** Cast, index và lookup thủ công làm advice khó đọc và dễ hỏng khi signature đổi.

**Lỗi 4 — Cho rằng typed binding tự động thay đổi tham số target.** Binding cung cấp giá trị cho advice; muốn thay argument được chuyển tiếp phải có API và hợp đồng hỗ trợ.

**Lỗi 5 — Dùng Method của interface để tìm annotation chỉ gắn ở implementation.** Có thể nhận null dù implementation đã được đánh dấu.

**Lỗi 6 — Cho rằng method annotation truyền tự động sang override.** Java không áp dụng @Inherited cho method overriding theo cách đó; phải xác định policy tra cứu hierarchy nếu cần.

**Lỗi 7 — Tra Method chỉ theo tên.** Overload, primitive types, arrays, bridges và generics có thể làm tra cứu sai.

**Lỗi 8 — Không unwrap InvocationTargetException.** Caller nhận wrapper thay vì lỗi gốc, khiến xử lý exception sai.

**Lỗi 9 — Dùng deep reflection bừa bãi.** JPMS/access control có thể chặn, đồng thời vượt quá yêu cầu bảo mật.

**Lỗi 10 — Cache cả Object[] args của invocation.** Giá trị runtime thay đổi theo lượt; cache nhầm có thể làm rò dữ liệu request hoặc báo sai.

**Lỗi 11 — Cho rằng getArgs() cung cấp tên tham số source.** Nó cung cấp giá trị; tên source phụ thuộc loại metadata/compiler/engine.

**Lỗi 12 — Benchmark mà bỏ qua I/O.** So sánh chỉ chi phí lookup nhưng advice thực tế làm network/log có thể dẫn đến kết luận hiệu năng vô nghĩa.

**Lỗi 13 — Tưởng dynamic proxy bao phủ mọi method.** Caller đi thẳng target, self-invocation hoặc static/private/constructor có thể không đi qua interceptor; khả năng khác nếu dùng bytecode weaving.

## 19. Quy trình lựa chọn và kiểm chứng

### Bước 1 — Phân loại dữ liệu cần lấy

Hãy viết ra các trường thật sự cần:

- **Giá trị của một argument cụ thể:** ưu tiên bind trực tiếp nếu chữ ký đã biết.
- **Đối tượng target hoặc this:** dùng binding hoặc context do engine hỗ trợ.
- **Tên method/chữ ký:** thử metadata từ join point descriptor.
- **Annotation trên implementation:** kiểm tra engine có binding phù hợp không; nếu không, dùng reflection với resolver chính xác.
- **Return value/Throwable:** dùng advice loại thích hợp, không tra Method để tìm giá trị invocation.

### Bước 2 — Xác định join point kind

Call và execution có thể cung cấp chữ ký từ những góc nhìn khác nhau. Trong đa hình, call site giữ kiểu tĩnh còn execution chọn triển khai thật; reflection ở proxy có thể là Method của interface. Đây là tiền đề chọn đúng declaring class.

### Bước 3 — Kiểm tra kiểu và null

Với binding trực tiếp, xác minh formal type tương thích; với Object[] và reflection, kiểm tra array null/length, index, primitive wrapper, varargs, nullable reference.

### Bước 4 — Kiểm tra nguồn metadata

Khai báo ở interface hay implementation? Annotation retention? Superclass hoặc override? Bridge method? Có đủ quyền truy cập trong module không?

### Bước 5 — Kiểm tra cơ chế áp dụng

Code gốc có nằm trong phạm vi weaving không? Caller có đi qua proxy không? Một pointcut chọn execution có được engine hỗ trợ không? Binding chỉ tồn tại nếu join point thật được chọn.

### Bước 6 — Thử đường thành công và thất bại

Test dữ liệu đầu vào đúng kiểu, sai kiểu (nếu API cho phép), null, method không có args, overload, target throw, annotation thiếu, không tìm được Method và lỗi access.

### Bước 7 — Kiểm tra nonfunctional

Đo allocation, lookup cost, số lần advice được kích hoạt, memory retention, khả năng lộ dữ liệu và tác động concurrency. Tối ưu sau khi biết thực tế workload.

## 20. Ma trận kiểm thử ngắn

| Trường hợp | Kỳ vọng cần xác minh |
|---|---|
| Advice bind String và int | Lấy đúng giá trị từng invocation, không lệch index |
| Method có 0 tham số trong proxy | Handler không dereference Object[] null |
| Method overload cùng tên | Lookup chọn đúng parameter Class[] |
| Annotation chỉ ở implementation | Resolver đọc đúng Method chứa annotation |
| Override method | Không giả định method annotation được kế thừa |
| Method kế thừa | Declaring class có thể là superclass |
| Generics tạo bridge | Không gây event trùng hoặc đọc annotation sai |
| Target throw | Lỗi gốc được quan sát/lan truyền đúng |
| Primitive argument/result | Boxing/unboxing hợp lệ |
| Lời gọi không qua proxy | Không kỳ vọng proxy handler chạy |
| Static call hoặc constructor | Không bind this/target khi mô hình không hỗ trợ |
| Concurrent invocations | Không cache nhầm args/result giữa các thread |
| Hot path có reflection | Đo bằng benchmark và workload thích hợp |
| Dữ liệu nhạy cảm | Chỉ log những trường được phép |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Advice đã bind biến String orderId từ args. Có cần dùng Method.getParameterTypes để biết nội dung String orderId không?

**Trả lời:** Không. Giá trị được bind trực tiếp; parameter types chỉ mô tả kiểu khai báo.

**Câu 2.** Method.getReturnType trả int. Có biết lần gọi trước đã trả 42 không?

**Trả lời:** Không. Return type là metadata tĩnh; giá trị của lần gọi là dữ liệu động cần được thu ở return boundary.

**Câu 3.** JDK proxy handler nhận Method của Formatter interface nhưng annotation chỉ ở FormatterImpl.format. Tại sao handler có thể không thấy annotation nếu đọc Method trực tiếp?

**Trả lời:** Vì đó là hai khai báo method khác nhau; annotation ở implementation không tự xuất hiện trên interface Method.

**Câu 4.** Chỉ cần method name và kind cho trace, có nhất thiết phải dùng Java reflection?

**Trả lời:** Không. Join point descriptor của một số mô hình AOP đã có thể cung cấp thông tin cần.

**Câu 5.** Có thể dùng Object[] args từ lượt A làm thông tin cho lượt B trên cùng Method object không?

**Trả lời:** Không. Args thuộc từng invocation, có thể khác nhau ở mỗi lần gọi và cần được xử lý/cất giữ an toàn.

**Câu 6.** Direct binding có bảo đảm target luôn nhận tham số mới nếu advice gán lại biến không?

**Trả lời:** Không. Binding cho advice thấy giá trị; việc thay argument khi tiếp tục đòi hỏi cơ chế tương ứng và có thể không được hỗ trợ.

**Câu 7.** Một method reflection có thể được tìm thấy nhưng invoke không thành công không?

**Trả lời:** Có. Access control, module boundary, target/arguments không tương thích hoặc lỗi trong target đều có thể làm invocation thất bại.

**Câu 8.** Advice chỉ cần annotation của join point được chọn. Có thể ưu tiên binding annotation không?

**Trả lời:** Có nếu engine hỗ trợ và semantics của annotation pointcut khớp chính sách. Nếu phải tìm theo interface, implementation hoặc override hierarchy khác với engine, cần resolver được xác định rõ.

## 22. Tóm tắt mô hình dữ liệu

~~~text
                  JOIN POINT THỰC THI
                          │
            ┌─────────────┴──────────────┐
            │                            │
            ▼                            ▼
    DỮ LIỆU RUNTIME               METADATA VỀ ĐIỂM
    args / this / target           signature / kind / class
    return / exception            annotation / declaring method
            │                            │
            ▼                            ▼
     DIRECT BINDING                INTROSPECTION API
     formal parameters             join point descriptor
     được khai báo kiểu             hoặc Java reflection
            │                            │
            └─────────────┬──────────────┘
                          │
                          ▼
                       ADVICE
                          │
                          ▼
            HÀNH VI XUYÊN CẮT CÓ KIỂM SOÁT
~~~

**Ghi nhớ:**

1. Binding trực tiếp dùng **giá trị thật của lượt join point hiện tại** qua formal parameters mà pointcut/advice hỗ trợ; ưu tiên khi biết rõ dữ liệu nào cần dùng.
2. Reflection khám phá **cấu trúc và metadata của chương trình**, và có thể invoke method, nhưng không tự biết giá trị argument/return của một lượt thực thi nếu không có ngữ cảnh invocation.
3. API mô tả join point nằm **giữa hai khái niệm**: nó có thể cung cấp cả metadata lẫn dữ liệu invocation, không nhất thiết đồng nghĩa với Java reflection.
4. Chọn đúng declaring Method, loại join point, thứ tự exception, quyền truy cập và phạm vi weaving/proxy quan trọng hơn việc quyết định công cụ nào “tốt hơn” một cách tuyệt đối.

## Tài liệu đối chiếu

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): pointcut, advice binding, this/target/args, annotation pointcuts và join point context trong một ngôn ngữ AOP cụ thể.
- [Java SE 17 — java.lang.reflect.Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): introspection method, getParameterTypes, getAnnotation, invoke và exception wrapper.
- [Java SE 17 — java.lang.reflect.InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): object Method và Object[] args được chuyển vào JDK dynamic proxy handler.
- [Java Language Specification, Java SE 17 — Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): metadata annotation, retention và các giới hạn kế thừa theo ngữ nghĩa Java.