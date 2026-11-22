# Annotation là siêu dữ liệu, không tự tạo cơ chế AOP

## 1. Trọng tâm: dấu `@Trace` là một mô tả, không phải bộ máy can thiệp

Trong **Aspect-Oriented Programming (AOP)**, chúng ta muốn mô-đun hóa các concern cắt ngang như logging, tracing, authorization, metrics, caching hoặc transaction boundaries. Ở Java, **annotation** là một cách phổ biến để gắn **siêu dữ liệu (metadata)** vào class, method, field, constructor, parameter hoặc các thành phần được `@Target` cho phép. Nhưng **annotation tự nó không thay đổi luồng thực thi** và **không tự động tạo aspect, pointcut, advice, proxy hoặc bytecode weaving**.

Hãy xem một method có dấu:

~~~java
@Trace
public String send(String id) {
    return "sent:" + id;
}
~~~

Đây là fragment minh họa, không phải chương trình độc lập. Nếu không có **mã hoặc công cụ nhận diện và xử lý `@Trace`**, lời gọi `send("A")` vẫn chỉ chạy thân method như Java thông thường. Dấu `@Trace` không tự in log, không tự đo duration, không tự bắt lỗi và cũng không tự định nghĩa join point.

Muốn có hành vi AOP, phải có một cơ chế thực thi kết nối metadata với hành động:

~~~text
         [SOURCE / CLASSFILE]
             @Trace
                |
                | chỉ khai báo ý định / dữ liệu
                v
       [READER / POINTCUT RULE]
       xác định method được chọn
                |
                v
       [INTERCEPTION MECHANISM]
       proxy / weaver / transformer / dispatcher
                |
                v
          [ADVICE LOGIC]
         before / after / around
                |
                v
       [THỰC THI TARGET THẬT]
~~~

Không có các tầng nhận diện và can thiệp phù hợp, annotation là **metadata**, không phải **runtime behavior**.

### Mục tiêu học tập

Sau bài này, có thể:

1. Diễn giải vai trò của annotation trong AOP theo đúng ranh giới **metadata vs mechanism**.
2. Phân biệt **đánh dấu method**, **đọc annotation**, **chọn join point** và **can thiệp lời gọi**.
3. Phân biệt `RetentionPolicy.SOURCE`, `CLASS`, `RUNTIME` và tác động đến cách đọc.
4. Hiểu `@Target`, annotation elements, class/interface/method placement và giới hạn thừa kế.
5. Viết chương trình Java 17 kiểm chứng annotation tự nó không chạy advice.
6. Nhận diện coverage của proxy và các khác biệt với bytecode weaving.
7. Thiết kế, QA và triển khai annotation-driven aspect đúng hợp đồng, kể cả lỗi/caching/async/concurrency.

Bài tập trung vào **AOP tổng quát**, không đồng nhất annotation với bất kỳ thư viện cụ thể nào.

## 2. Annotation là gì trong Java?

Một annotation là một **khai báo dữ liệu có kiểu** được gắn với phần tử chương trình theo quy tắc Java. Tự định nghĩa:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface Trace {
    String value() default "default";
}
~~~

Đây là fragment khai báo hợp lệ khi được đặt trong file Java thích hợp. Nó nói:

- `@Target(ElementType.METHOD)`: annotation được phép xuất hiện trên method declarations.
- `@Retention(RetentionPolicy.RUNTIME)`: metadata được giữ để reflection API có thể đọc tại runtime.
- `value()`: một annotation element kiểu `String`, với giá trị mặc định.

Không có `before()`, `after()`, `proceed()` hay logic AOP nào tự động sinh ra chỉ từ định nghĩa đó. Mã thực thi có thể dùng `getAnnotation`/`isAnnotationPresent` để kiểm metadata, nhưng **đọc được** chưa phải **can thiệp được**.

### 2.1. Annotation có phải một đối tượng giống class runtime không?

Annotation type trong Java là một interface đặc biệt theo ngữ nghĩa ngôn ngữ, các giá trị có thể được đọc qua `java.lang.annotation.Annotation` và reflection. Khi được lưu với retention thích hợp, runtime có thể tạo biểu diễn annotation để truy cập elements.

Nhưng việc `SomeClass.class.getAnnotation(Trace.class)` trả dữ liệu không chứng minh JVM đã tự chạy một advice. Annotation object biểu diễn **declaration**, không phải một execution interceptor.

### 2.2. Metadata có thể phục vụ rất nhiều mục đích ngoài AOP

- Kiểm lỗi ở compiler hoặc annotation processor.
- Phát sinh source files / class resources trong build.
- Sinh tài liệu/schema.
- Kiểm validation khi một thư viện thực hiện reflection.
- Cấu hình serialization.
- Tạo registry/discovery.
- Chọn join points cho AOP.
- Ghi thông tin hỗ trợ IDE hoặc static analysis.

**Điểm chung:** một **consumer** nào đó phải quyết định metadata có ý nghĩa gì. Cùng một `@Trace` có thể không làm gì trong app A nhưng được một engine riêng diễn giải ở app B; annotation không mang hành vi AOP mặc định.

## 3. Bốn tầng phải phân biệt rõ

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Khai báo** | Annotation gắn ở đâu, có giá trị nào? | `@Trace("checkout")` |
| **Đọc metadata** | Ai khám phá nó, bằng API nào, ở giai đoạn nào? | Java reflection, compiler processor |
| **Matching / selection** | Rule nào biến metadata thành tiêu chí chọn join point? | Chọn execution method có `@Trace` |
| **Interception / advice** | Điều gì khiến đoạn advice thật sự chạy? | Proxy handler, woven instructions, agent transformer |

Một hệ thống có thể đã làm tầng 1 và 2 mà vẫn chưa có tầng 3/4. Ví dụ:

~~~java
boolean found = method.isAnnotationPresent(Trace.class);
~~~

Câu lệnh `found == true` **không** ép lần gọi `method.invoke()` tiếp theo phải chạy logging. Người viết phải xây wrapper, dispatcher hoặc weave bytecode theo rule đã định.

### 3.1. Trường hợp “có annotation nhưng không có aspect”

~~~text
Caller ---> annotated target ---> normal return

Không có proxy/advice/weaver:
  Không có AOP behavior mặc định.
~~~

Ngay cả khi annotation có retention `RUNTIME`, JVM vẫn không được yêu cầu chạy logic before/after khi call method đó.

### 3.2. Trường hợp “có aspect nhưng không cần annotation”

AOP cũng có thể chọn bằng **method signature**, type, package pattern, control flow hoặc điều kiện khác mà engine hỗ trợ:

~~~text
Select execution of all methods named charge(...),
regardless of whether @Trace is present.
~~~

Đây là **pseudocode ý niệm**, không phải cú pháp bắt buộc. Vì vậy câu “AOP phải có annotation” cũng sai. Annotation chỉ là **một trong nhiều nguồn dữ liệu để chọn điểm can thiệp**.

## 4. Retention: metadata nằm ở giai đoạn nào?

Một annotation không thể được đọc ở mọi thời điểm chỉ vì nó tồn tại trong source. **Retention phải phù hợp với consumer thực tế**; đây là điều kiện để metadata có thể tham gia lựa chọn join point, chưa phải bằng chứng advice được chạy.

| Retention | Consumer phù hợp | Có thể đọc bằng Java reflection runtime? |
| --- | --- | --- |
| `SOURCE` | Compiler hoặc annotation processor còn nhìn thấy source | Không |
| `CLASS` | Công cụ phân tích classfile hoặc binary weaver hỗ trợ thuộc tính annotation | Không qua API reflection annotation thông thường |
| `RUNTIME` | Runtime reflector/interceptor như `Method.getAnnotation` | Có, **trên đúng declaration** được truy vấn |

**Mặc định không viết `@Retention` là `CLASS`**, không phải `RUNTIME`. Một `SOURCE` marker có thể rất hữu ích để validate hoặc sinh code khi build; `CLASS` vẫn có thể được bytecode tooling đọc. Ngược lại, nếu handler JDK dùng `Method.isAnnotationPresent`, hãy dùng `RUNTIME` và kiểm tra đúng method/interface/implementation.

Sau cùng, thêm `RUNTIME` chỉ làm annotation **có thể đọc được**. Muốn AOP hoạt động vẫn cần rule lựa chọn, cơ chế interception/weaving, advice được đăng ký và đường gọi thực tế tới join point.

## 5. Target và phần tử được phép đánh dấu

`@Target` giới hạn vị trí hợp lệ của annotation, không quy định advice chạy khi nào.

Những `ElementType` thường gặp:

| Vị trí | Ý nghĩa declaration | Cần tránh suy diễn |
| --- | --- | --- |
| `TYPE` | Class/interface/enum/annotation type | Không tự áp method-level advice |
| `METHOD` | Method declaration | Không tự can thiệp method calls |
| `CONSTRUCTOR` | Constructor declaration | Không tự tạo constructor join point ở mọi engine |
| `FIELD` | Field declaration | Không có nghĩa field read/write đã được intercept |
| `PARAMETER` | Parameter metadata | Không tự chạy validation |
| `ANNOTATION_TYPE` | Meta-annotation | Không tự làm các annotation khác được quét đệ quy |
| `TYPE_USE` | Type usage | Không đồng nghĩa runtime method join point |
| `TYPE_PARAMETER` | Type parameter declaration | Không tự tạo business policy |
| `PACKAGE` / `MODULE` | Package/module declarations | Không tự tạo broad interception rule |
| `RECORD_COMPONENT` | Record component | Không tự can thiệp record accessor |

`@Target(TYPE)` trên một class và `@Target(METHOD)` trên method có thể cần **hai cách matching khác nhau**. Một engine có thể chọn mọi methods của class có annotation, trong khi engine khác chỉ chọn method trực tiếp được đánh dấu. **Không tự suy một rule từ vị trí annotation**.

### 5.1. Method annotation khác class annotation

~~~java
@Feature("payments")
class PaymentService {
    @Trace
    public void settle() { }
    public void status() { }
}
~~~

Đây là fragment minh họa: `@Feature` và `@Trace` cần khai báo phù hợp. `@Feature` ở class không đồng nghĩa `settle()` và `status()` đều có direct `@Feature` trên từng `Method`. Một rule “methods nằm trong class có `@Feature`” phải kiểm class metadata; một rule “method có `@Trace`” phải kiểm method metadata.

## 6. Ví dụ Java 17 hoàn chỉnh: annotation đứng yên cho tới khi có proxy

Chương trình sau dùng **JDK thuần** và viết rõ hai thành phần:

1. `@Trace` là annotation retention `RUNTIME` gắn vào implementation method `Core.run(String)`.
2. `AnnotationAopDemo.instrument(...)` tạo **JDK dynamic proxy**. Handler đọc annotation trên **method implementation** và chỉ với method được chọn mới in `ADVICE before/after`.

Bên cạnh đó còn có `@BuildMark` với `RetentionPolicy.CLASS`, `@SourceMark` với `RetentionPolicy.SOURCE` và `@Feature` trên class để so sánh reflection.

Các đường gọi cần quan sát:

- **Direct:** `core.run("A")` được đánh dấu nhưng **không có advice**, vì caller gọi raw core.
- **Proxy:** `proxy.run("B")` chạy handler; handler thấy `@Trace` và in advice trước/sau.
- **Không match:** `proxy.plain()` vẫn qua proxy nhưng không có `@Trace` nên không in advice.
- **Self-invocation:** `proxy.outer("C")` đi qua proxy ở `outer()`, nhưng `Core.outer()` gọi `this.run("C")` trực tiếp trong target, bypass proxy cho lời gọi bên trong.
- **Retention:** `RUNTIME` annotation được reflection nhìn thấy; `CLASS` và `SOURCE` không.
- **Assertion:** cả ba lần business `run` thật đều xảy ra, trong khi advice chỉ xuất hiện ở lời gọi qua proxy được đánh dấu.

**Giới hạn:** đây là một **proxy-based interception demo**, không phải compile-time/load-time weaving, không có pointcut language engine đầy đủ. Kết luận được chứng minh là **annotation chỉ mang metadata, còn proxy handler mới triển khai điều kiện và hành vi**.

Tạo file `AnnotationAopDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class AnnotationAopDemo {
    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Trace {}

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.CLASS)
    @interface BuildMark {}

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.SOURCE)
    @interface SourceMark {}

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Feature { String value(); }

    interface Operation {
        String run(String id);
        String plain();
        String outer(String id);
    }

    @Feature("orders")
    static final class Core implements Operation {
        int runs;
        @Trace @BuildMark @SourceMark
        public String run(String id) {
            runs++;
            System.out.println("CORE run " + id);
            return "ok:" + id;
        }
        public String plain() {
            System.out.println("CORE plain");
            return "plain";
        }
        public String outer(String id) {
            System.out.println("CORE outer");
            return this.run(id);
        }
    }

    static Object invoke(Object target, Method m, Object[] args) throws Throwable {
        try {
            return m.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Operation instrument(Operation target) {
        return (Operation) Proxy.newProxyInstance(
            Operation.class.getClassLoader(),
            new Class<?>[] { Operation.class },
            (proxy, interfaceMethod, args) -> {
                Method implementation = target.getClass().getMethod(
                    interfaceMethod.getName(), interfaceMethod.getParameterTypes());
                boolean selected = implementation.isAnnotationPresent(Trace.class);
                if (!selected) return invoke(target, implementation, args);
                System.out.println("ADVICE before " + implementation.getName());
                Object result = invoke(target, implementation, args);
                System.out.println("ADVICE after " + result);
                return result;
            });
    }

    static void check(boolean value) {
        if (!value) throw new AssertionError("check failed");
    }

    public static void main(String[] args) throws Exception {
        Method run = Core.class.getMethod("run", String.class);
        boolean runtime = run.isAnnotationPresent(Trace.class);
        boolean build = run.isAnnotationPresent(BuildMark.class);
        boolean source = run.isAnnotationPresent(SourceMark.class);
        check(runtime && !build && !source);
        System.out.println("REFLECTION runtime=true class=false source=false");
        System.out.println("FEATURE " + Core.class.getAnnotation(Feature.class).value());

        Core core = new Core();
        System.out.println("DIRECT " + core.run("A"));
        Operation proxy = instrument(core);
        System.out.println("PROXY " + proxy.run("B"));
        System.out.println("PLAIN " + proxy.plain());
        System.out.println("OUTER " + proxy.outer("C"));
        check(core.runs == 3);
        System.out.println("ASSERT runs=3");
        System.out.println("ALL ASSERTIONS PASSED");
    }
}
~~~

Biên dịch bằng API tương thích Java 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AnnotationAopDemo.java
java AnnotationAopDemo
~~~

Đầu ra đã được kiểm chứng bằng `javac --release 17` và JVM:

~~~text
REFLECTION runtime=true class=false source=false
FEATURE orders
CORE run A
DIRECT ok:A
ADVICE before run
CORE run B
ADVICE after ok:B
PROXY ok:B
CORE plain
PLAIN plain
CORE outer
CORE run C
OUTER ok:C
ASSERT runs=3
ALL ASSERTIONS PASSED
~~~

### 6.1. Vì sao `DIRECT ok:A` không có advice?

`core` là **target object gốc**. Lệnh `core.run("A")` không đi qua `instrument(...)` proxy. JVM không tự phát hiện `@Trace` rồi chèn lệnh in `ADVICE`, dù annotation có `RUNTIME` retention.

Đây là bằng chứng trực tiếp nhất cho câu **annotation là metadata, không tự tạo AOP**.

### 6.2. Vì sao `PROXY ok:B` có advice?

Caller gọi `proxy.run("B")`. `InvocationHandler` được JVM proxy machinery gọi, sau đó handler dùng reflection:

~~~java
Method implementation = target.getClass().getMethod(
    interfaceMethod.getName(), interfaceMethod.getParameterTypes());

boolean selected = implementation.isAnnotationPresent(Trace.class);
~~~

Đây là fragment cắt từ chương trình đầy đủ. `selected` là true vì `Core.run` có `@Trace`. **Handler** chủ động in before, gọi method thật và in after. Chính handler cung cấp behavior; annotation chỉ giúp nó quyết định **có chọn method hay không**.

### 6.3. Vì sao `plain()` không in advice?

`proxy.plain()` vẫn đi qua proxy. Handler tìm `Core.plain()` nhưng method đó không có `@Trace`. Điều kiện false, nên handler gọi target mà không in dòng advice. Đây là một **negative matching test** quan trọng: kiểm đúng việc proxy tồn tại không đồng nghĩa mọi method đều chịu cùng behavior.

### 6.4. Vì sao `outer("C")` bypass advice ở `run`?

`proxy.outer("C")` tới handler, nhưng `outer` không có `@Trace`. Target `Core.outer` được gọi, rồi bên trong nó thực hiện `this.run(id)` trên **chính core object**, không đi qua `proxy`.

Vì vậy `CORE run C` xuất hiện, còn `ADVICE before run` không xuất hiện lần hai. Đây là một giới hạn **đường gọi proxy**; một cơ chế dệt bytecode vào execution join point có thể có coverage khác, nếu thực sự instrument đúng class/method.

### 6.5. Vì sao `BuildMark` và `SourceMark` không thấy bằng reflection?

`BuildMark` dùng `RetentionPolicy.CLASS`: classfile có thể giữ metadata, nhưng Java reflection thông thường không đưa nó vào `isAnnotationPresent`. `SourceMark` chỉ ở source nên không còn trong classfile sau compile. `Trace` dùng `RUNTIME` nên runtime method reflection có thể đọc.

**Không suy** rằng classfile scanner sẽ thấy kết quả hệt runtime reflection; hai consumers dùng hai cấp dữ liệu khác nhau.

### 6.6. Vì sao phải unwrap `InvocationTargetException`?

`Method.invoke()` đóng gói exception target ném trong `InvocationTargetException`. Handler lấy `getCause()` để giữ exception target theo đường caller trong giới hạn hợp đồng proxy. Nếu không xử lý, caller có thể thấy loại wrapper khác hoặc exception handling bị thay đổi ngoài ý muốn.

**Chính sách exceptions của advice** luôn là một phần hợp đồng: observer không nên vô tình che hoặc biến lỗi nghiệp vụ.

## 7. Annotation placement: interface khác implementation

Một lỗi phổ biến khi dùng interface proxy:

~~~java
interface Operation {
    @Trace
    String run(String value);
}

final class Core implements Operation {
    public String run(String value) {
        return "ok:" + value;
    }
}
~~~

Đây là fragment minh họa, yêu cầu `@Trace` được khai báo phù hợp.

Tại đây annotation nằm trên **interface declaration**, không phải direct annotation của implementation method. Nếu handler chỉ gọi:

~~~java
target.getClass().getMethod("run", String.class)
      .isAnnotationPresent(Trace.class);
~~~

thì **không được mặc định** kết quả true. Method annotations không tự được kế thừa từ interface method sang implementation method theo logic reflection thông thường.

Ngược lại, nếu `@Trace` gắn trên implementation method như demo, nhưng handler chỉ kiểm **interfaceMethod** từ proxy, nó cũng có thể không thấy dấu ấy.

### 7.1. Muốn hỗ trợ cả hai vị trí phải định nghĩa rule

Một scanner có thể chọn:

1. Chỉ annotation ở implementation method.
2. Chỉ annotation ở interface declaration.
3. Ưu tiên implementation rồi fallback interface.
4. Gộp metadata từ interface, superclass và implementation với precedence do hệ thống quy định.
5. Chỉ match type-level annotation rồi áp cho methods.

Không có policy thống nhất bắt buộc cho mọi AOP engine. Nếu chọn gộp, phải quyết định **giá trị nào thắng khi mâu thuẫn**, xử lý overload/bridge methods/generics ra sao và test method resolution thật.

### 7.2. Không nhầm annotation lookup với pointcut execution coverage

Có thể scanner tìm đúng `@Trace` nhưng target call không qua proxy, nên advice vẫn không chạy. Cũng có thể weaving đã instrument target nhưng matcher lấy metadata ở vị trí khác mong đợi, nên advice không được chọn.

**Hai câu hỏi riêng**:

- `selected(method)` có đúng không?
- `intercepted(invocation)` có thật không?

Chỉ khi cả hai đúng, annotation-driven advice mới phát tác dụng.

## 8. `@Inherited` và các giới hạn về thừa kế annotation

Java có meta-annotation `@Inherited` dùng cho **annotation types**, nhưng nó không phải một quy tắc “mọi annotation của mọi member được tự động kế thừa”.

Điểm then chốt:

- `@Inherited` có ý nghĩa đặc biệt cho **class-level annotation lookup** trong những API reflection phù hợp.
- Nó **không** có nghĩa method annotations tự chảy từ superclass/interface methods sang overriding methods.
- Nó **không** tự tạo AOP interception cho subclass.
- Nó **không** tự làm annotations trên interface được kế thừa bởi implementing class theo cùng cơ chế class inheritance.
- Một engine tự xây metadata traversal qua interfaces/superclasses có thể cung cấp policy riêng.

Ví dụ ý niệm:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface TrackedType {}

@TrackedType
class Parent {}

class Child extends Parent {}
~~~

Đây là declaration fragment hợp lệ trong một file Java với imports phù hợp. Khi `TrackedType` được đánh dấu `@Inherited`, class-level reflection có thể thấy annotation inherited trên `Child` theo quy tắc Java. Nhưng không nên suy rằng mọi method `Child` có annotation `TrackedType` hoặc đã được weave.

### 8.1. Vì sao điều này quan trọng cho AOP?

Một rule match “class có `@TrackedType`” phải định nghĩa có dùng `getDeclaredAnnotation` hay `getAnnotation`, có xét interface metadata hay không. Khác lookup policy dẫn đến khác **pointcut coverage**, dù source classes y hệt nhau.

## 9. Meta-annotations và composed annotations

Một annotation cũng có thể mang annotations khác:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Trace
@interface Audited {}
~~~

Đây là fragment minh họa: `@Trace` trong ví dụ cần `@Target(ANNOTATION_TYPE)` hoặc một tập target bao annotation types mới hợp lệ, khác với `@Trace` method-only ở chương trình Java trước. Không trộn hai khai báo trái target trong cùng file.

Quan trọng hơn: nếu một method được đánh dấu `@Audited`, một scanner chỉ gọi:

~~~java
method.isAnnotationPresent(Trace.class)
~~~

**không tự động tìm đệ quy `@Trace` trên annotation type `Audited`**. Muốn hỗ trợ composed annotations, consumer phải viết hoặc dùng logic **meta-annotation traversal**, có policy về vòng lặp, alias attributes và precedence.

### 9.1. Phân biệt “meta-annotation có tồn tại” và “được hiểu là alias”

Java reflection có thể cho phép khám phá annotations trên annotation type khi chúng có retention phù hợp. Nhưng **cách diễn giải** chúng như `@Trace` gián tiếp vẫn do scanner/engine quyết định.

Một số câu hỏi cần thiết kế:

- Chỉ scan direct annotation hay duyệt transitive meta-annotations?
- Nếu cùng metadata xuất hiện trực tiếp và gián tiếp, giá trị nào ưu tiên?
- Nếu hai composed annotations cung cấp giá trị mâu thuẫn, xử lý ra sao?
- Có hỗ trợ repeatable container không?
- Có cache kết quả scan theo đúng `ClassLoader` và version không?

Đừng coi “đã có composed annotation” là bằng chứng aspect chắc chắn nhận nó.

## 10. Repeatable annotations cũng cần consumer hiểu

Java cho phép khai báo annotation có `@Repeatable` cùng container type thích hợp. Khi có nhiều annotation cùng loại trên một element, API như `getAnnotationsByType(...)` có thể gom các lần xuất hiện theo hợp đồng reflection.

Nhưng một pointcut/processor chỉ dùng `getAnnotation(...)` hoặc kiểm một direct annotation chưa chắc cho kết quả mà người thiết kế mong muốn với repeatable forms. **Cấu trúc dữ liệu metadata** và **policy matching** vẫn phải được kiểm đúng.

Ví dụ một annotation `@Permission("READ")` và `@Permission("WRITE")` có thể cần ý nghĩa AND hoặc OR; **annotation không tự định nghĩa runtime authorization semantics**. Phải viết rule và security tests.

## 11. Annotation processor khác runtime AOP

**Annotation processor** hoạt động trong luồng compilation để đọc annotation, báo lỗi, tạo source/resources hoặc artifacts theo API hỗ trợ. Nó không tự động là một around advice ở runtime.

~~~text
SOURCE @Marker
    |
    v
COMPILER / ANNOTATION PROCESSOR
    |
    +-> diagnostics / generated source / metadata resources
    |
    v
compiled application
~~~

Nếu processor sinh ra wrapper hoặc code gọi interceptor, **generated code** đó mới thực hiện hành vi khi ứng dụng chạy. Nếu processor chỉ báo cảnh báo hoặc sinh tài liệu, không có runtime interception.

### 11.1. Compile-time weaving cũng là cơ chế riêng

Một compile-time weaver có thể sử dụng metadata để xác định nơi cần chèn instructions vào class hoặc source transformation. Trong trường hợp đó:

- Annotation có thể là **input** của rule.
- Weaver là **mechanism** áp dụng transformation.
- Code đã được dệt mới là thứ **thực hiện advice** khi join point chạy.

Chỉ annotation trong source không tự làm compiler vanilla tạo aspect.

### 11.2. Binary weaving có thể dùng retention `CLASS`

Một binary weaver đọc bytecode có thể thấy annotation retention `CLASS` nếu classfile chứa nó và tool có logic đọc. Runtime reflection thông thường không phải nguồn dữ liệu duy nhất cho aspect matching.

Đây là lý do phải biết **tool đọc annotations vào lúc nào** trước khi chọn retention.

### 11.3. Load-time weaving có lifecycle riêng

Một load-time transformer có thể can thiệp classfile trước khi JVM định nghĩa class, nhưng:

- Transformer/agent phải thực sự được cài và có quyền xem class.
- Classloader, module boundaries và timing ảnh hưởng coverage.
- Một class đã load trước khi transformer hoạt động có thể không được xử lý theo plan.
- Hot retransformation có ràng buộc schema riêng.
- Một target dù có annotation vẫn không tự xuất hiện trong danh sách class được transform.

Như vậy **annotation được giữ** chưa đủ; còn phải **engine có chạy và match đúng**.

## 12. Annotation-driven AOP: sơ đồ thực thi an toàn hơn

Một thiết kế rõ ràng thường có các trách nhiệm tách biệt:

~~~text
1. DECLARATION
   Define @Observed with retention/targets/attributes

2. DISCOVERY
   Locate eligible classes/methods and read metadata

3. RESOLUTION
   Resolve implementation vs interface, inheritance, overloads, bridge methods

4. MATCHING
   Select eligible join points using explicit policy

5. INSTALLATION
   Create proxy / apply weaving / register interceptor

6. INVOCATION
   Advice before/after/around runs at selected boundaries

7. VERIFICATION
   Assert both positive and negative coverage on release artifact
~~~

Bỏ qua tầng 5 là lỗi rất thường gặp: scanner đã tìm metadata, log “registered 100 methods”, nhưng caller vẫn gọi raw objects nên không có interception.

### 12.1. Thứ tự cài đặt và lifecycle

- Một proxy chỉ có tác dụng khi caller giữ **reference tới proxy**, không phải raw target.
- Một structural/weaving transformation cần áp dụng lên **đúng class và join point** trước/ở thời điểm công nghệ hỗ trợ.
- Việc tạo aspect instance, load class và invoke advice là **các mốc khác nhau**.
- Đổi annotation value có thể yêu cầu rebuild/reweave/reload tùy cơ chế.
- Nếu cache metadata scan, cần chính sách invalidation khi code hoặc loader thay đổi.

## 13. `@Target` không đảm bảo join point nào có thể được dệt

Nếu tạo:

~~~java
@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
@interface Sensitive {}
~~~

điều đó chỉ cho phép `@Sensitive` gắn trên field. Nó **không** làm mọi field get/set tự trở thành join points mà tool có thể intercept. Một interface proxy thường chỉ thấy method invocations đi qua wrapper; nó không tự nhìn thấy mọi direct field read.

Tương tự:
- Annotation trên constructor không ép proxy method interceptor quan sát constructor execution.
- Annotation trên private method không làm JDK interface proxy có thể intercept private method.
- Annotation trên class không làm static initialization trở thành một advice event.
- Annotation trên parameter không tự validation hoặc convert input.

**Khả năng join point model** và **tính hợp lệ của vị trí annotation** là hai lớp quy tắc khác nhau.

## 14. Proxy, weaving và đường bypass

Một annotated method không tạo behavior trên mọi đường gọi:

| Đường gọi | JDK interface proxy thường thấy? | Ý nghĩa |
| --- | --- | --- |
| Caller gọi `proxy.run()` | Có | Handler có thể kiểm annotation và chạy advice |
| Caller gọi `core.run()` raw | Không | Direct execution bypass proxy |
| `core.outer()` gọi `this.run()` | Không qua proxy cho inner call | Self-invocation bypass |
| Caller gọi private method | Không phải interface proxy method | Cần engine khác nếu muốn instrument |
| Caller đọc field trực tiếp | Không | JDK proxy không tự intercept field access |
| Constructor tạo target | Không mặc nhiên | Proxy được tạo sau theo design |
| Bytecode-woven execution | Tùy engine/instrumentation thực | Có thể bắt được những nơi proxy không thấy |
| Load-time transformer bỏ lỡ class | Không có weaving ở class ấy | Annotation không thể tự bù coverage |

**Không đánh đồng** kết quả của JDK proxy demo với mọi compile-time/binary/load-time weaving engine. Mỗi công nghệ có phạm vi join points và chi phí khác nhau.

### 14.1. Tại sao annotation ở implementation dễ bị bỏ sót?

InvocationHandler nhận `Method` từ proxy interface. Nếu annotation ở implementation method, phải resolve target implementation tương ứng. Với overloads, generics/bridge methods và inheritance, việc lấy implementation method không đơn giản là so mỗi tên.

### 14.2. Cẩn thận với object methods

`equals`, `hashCode` và `toString` có thể đi qua proxy handler. Nếu code mặc định coi mọi invocation đều là business method có một String argument, nó có thể ném lỗi. Demo chỉ tập trung vào ba methods đã khai báo; production handler phải định nghĩa chính sách cho Object methods và corner cases.

## 15. Hợp đồng của annotation phải được đặc tả rõ

Một annotation `@Audited` có thể là **nhãn dữ liệu**, hoặc được một công cụ diễn giải theo contract cụ thể. Muốn dùng làm API của AOP, cần viết rõ:

- **Target:** đặt trên method, type, annotation type hay field?
- **Retention:** ai cần nhìn thấy metadata?
- **Parameters:** các attributes có giá trị hợp lệ nào?
- **Matching:** direct annotation hay recursive lookup/meta-annotation?
- **Scope:** implementation vs interface, superclass vs declared method?
- **Interception:** proxy, weaver hoặc dispatcher?
- **Order:** advice này đứng trước/sau authorization/cache/retry ra sao?
- **Exceptions:** advice có được thay đổi lỗi của target không?
- **Concurrency:** advice state có per-invocation hay shared không?
- **Asynchronous completion:** theo method return hay Future completion?
- **Security:** có đường bypass raw/direct/async không?
- **Failure policy:** metadata invalid, advice sink down, scanning failure xử lý thế nào?
- **Versioning:** xóa/đổi annotation value có ảnh hưởng clients/build artifacts không?

Không có hợp đồng này, dấu `@Audited` dễ tạo ra **cảm giác an toàn giả**.

## 16. Ví dụ ứng dụng: `@RequiresPermission` không phải kiểm quyền tự động

Giả sử method có:

~~~java
@RequiresPermission("TRANSFER")
public void transfer() {
    moveFunds();
}
~~~

Đây là fragment khái niệm; annotation và `moveFunds()` cần được định nghĩa. Không có security enforcement chỉ vì annotation đã được đặt. Một người gọi trực tiếp `transfer()` trên raw target có thể bỏ qua proxy nếu chỉ proxy chịu trách nhiệm kiểm quyền.

**Vì vậy:** một policy bảo mật quan trọng phải có ranh giới enforcement đáng tin. Đừng dựa duy nhất vào annotation như một thứ “tự bảo vệ” method. Cần test cả proxy path, raw path, self-invocation, async/remote entry points và điều kiện loader/weaving.

### 16.1. Đừng nhầm annotation-driven audit với transaction

`@Audited` ở `save()` không tự đảm bảo event `BUSINESS_COMMITTED` thật sự xảy ra sau database commit. Một after-returning advice có thể chạy **trước khi** outer transaction commit; hoặc advice gửi audit ngoài ngay sau khi nghiệp vụ đã commit rồi lỗi.

Annotation không tạo tính nguyên tử, idempotency hoặc durability. Những tính chất đó thuộc **tài nguyên và workflow** được thiết kế.

### 16.2. Đừng nhầm annotation-driven caching với tính thuần

`@Cached` không chứng minh method pure, deterministic hay không có side effects. Nếu around advice short-circuit mà không gọi target, hành vi nghiệp vụ có thể khác kỳ vọng. Cần đặc tả cache key, expiration, concurrency và exceptions.

**Hành vi chỉ xuất hiện khi có mechanism** và phải được kiểm theo hợp đồng nghiệp vụ chứ không chỉ theo syntax annotation.

## 17. Làm gì khi metadata không tồn tại hoặc sai?

Các trường hợp:

1. Annotation không có trên method.
2. Annotation có nhưng `RetentionPolicy.CLASS`; runtime reflection không đọc được.
3. Annotation nằm trên interface nhưng scanner chỉ kiểm implementation.
4. Annotation nằm trên implementation nhưng scanner chỉ kiểm interface.
5. Annotation nằm trên superclass nhưng scanner không duyệt hierarchy.
6. Annotation nằm trên meta-annotation nhưng scanner chỉ kiểm direct annotation.
7. Annotation element value không hợp lệ theo domain.
8. Runtime nạp class khác version chưa có annotation.
9. Method generic được gọi qua bridge/overload khác matcher dự kiến.
10. Scanning gặp classloader/module visibility giới hạn.

Mỗi trường hợp phải có policy: **không match**, **fail-fast khi khởi động**, **cảnh báo**, **fallback** hoặc **từ chối request** tùy độ quan trọng. Với security, lựa chọn fail-open do “không thấy metadata” có thể không chấp nhận được.

## 18. Performance: metadata lookup cũng có chi phí

Một implementation đơn giản có thể làm mỗi invocation:

~~~text
get implementation Method
read annotation metadata
check conditions
invoke target
~~~

Dưới tải lớn, reflection lookup/method resolution lặp lại có thể thêm overhead. Có thể cache metadata scan theo method/type:

- Cần dùng key phân biệt **method signature, declaring class, proxy interface, classloader**.
- Classloaders động có thể bị giữ lại nếu cache static giữ `Method`/`Class` quá lâu.
- Module/plugin reload cần invalidation hoặc weak references thích hợp.
- `Method` reflection cache không tự giải quyết vấn đề **pointcut coverage**.
- Nếu scan chỉ chạy khi startup, đừng đánh đồng chi phí startup với overhead mỗi invocation.
- Một advice ghi network log có thể tốn hơn metadata lookup rất nhiều; đo trên workload đại diện.

**Đừng tối ưu bằng cách bỏ kiểm policy.** Với authentication/authorization, correctness có ưu tiên cao hơn vài microseconds; nên thiết kế cache đúng và test concurrent behavior.

### 18.1. Annotation metadata không phải invocation-local state

`@Trace` là metadata dùng chung của method/type; correlation ID, start time hoặc request context thường là **state theo invocation**. Đừng lưu `startTime` trên singleton handler chỉ vì annotation gắn trên method; requests song song có thể ghi đè state.

Ví dụ:

~~~java
long started = System.nanoTime();
try {
    return proceed();
} finally {
    elapsed.record(System.nanoTime() - started);
}
~~~

Đây là fragment minh họa chưa độc lập. `started` là local của từng invocation; `elapsed.record` cần concurrency contract phù hợp. `@Trace` có thể quyết định **có đo hay không**, nhưng không cung cấp sẵn sự an toàn đồng thời cho code đo.

## 19. Annotation không tự lan qua thread hay Future

Giả sử một annotated method trả `CompletableFuture<Result>`. AOP advice ở **method execution boundary** có thể chạy khi method **trả Future**, trước khi công việc thực hoàn tất:

~~~text
Caller -> annotated start()
            -> returns Future immediately
                       |
                       v
                task completes later
~~~

Để ghi event khi task hoàn thành, interceptor phải gắn vào completion stage hoặc task lifecycle được hỗ trợ; method annotation không tự cung cấp context propagation/cancellation handling.

Tương tự, `ThreadLocal` chứa request context không tự lan sang mọi executor. Annotation trên method của caller cũng không khiến một remote worker có cùng call stack. Đừng xây bảo đảm audit/bảo mật phân tán trên giả định ấy.

## 20. Kiểm thử theo bốn chiều: declaration, discovery, matching, execution

Một test chỉ assert:

~~~java
assert method.isAnnotationPresent(Trace.class);
~~~

mới chứng minh **metadata tồn tại**, chưa chứng minh advice chạy. Một suite tốt chia:

| Chiều | Test cần có |
| --- | --- |
| Declaration | Annotation có target, retention, default values đúng |
| Discovery | Reader thấy direct annotation ở đúng method/class |
| Matching | Rule chọn annotated method; loại unannotated method |
| Execution | Caller qua interceptor nhận advice; raw call không bị “ảo tưởng” instrument |
| Nested/self-call | Self-invocation có được/không được chọn theo engine |
| Exception | Target throw, advice không che lỗi ngoài policy |
| Concurrent | Invocation-local context không lẫn |
| Async | Method return vs Future completion không bị nhầm |
| Versioning | Woven/proxy artifact đúng version và classloader |
| Security | Không bypass nơi enforcement bắt buộc |
| Negative coverage | Không vô tình instrument unrelated methods |
| Performance | Overhead phù hợp, metadata scan cache đúng |

### 20.1. Test matrix đề nghị

1. Gọi method annotated trên **raw target**: trong proxy-only setup, không có proxy advice.
2. Gọi cùng method qua **proxy**: advice chạy đúng số lần.
3. Gọi unannotated method qua proxy: chỉ business behavior.
4. Annotation chỉ trên interface method: kiểm đúng lookup policy.
5. Annotation chỉ trên implementation method: kiểm đúng lookup policy.
6. `SOURCE`/`CLASS` retention: reflection không thấy, nhưng build-time/classfile consumer có thể.
7. Composed/repeatable annotations: test trực tiếp và gián tiếp theo policy.
8. Method overloaded/generic/bridge: map method đúng, không match nhầm.
9. Inner self-invocation: xác nhận proxy/weaving behavior thực.
10. Nhiều aspects: order/precedence và exception propagation.
11. After-returning advice throw: caller outcome & side effects hợp đồng.
12. Target async complete exceptionally: completion observer đúng.
13. Plugin classloader/reload: metadata cache và class identity đúng.
14. Raw/woven artifact mismatch: build test báo lỗi rõ thay vì silently thiếu advice.
15. Security or audit annotation removed: fail behavior theo policy, không tự bỏ qua.

### 20.2. Test chính chương trình Java ở mục 6

Bài demo đã có assertions:
- `Trace` runtime visible.
- `BuildMark` và `SourceMark` không visible với reflection.
- `Feature("orders")` ở class được đọc đúng.
- Target chạy tổng cộng 3 lần.
- Proxy advice xuất hiện chỉ ở `run("B")`.
- `outer("C")` gọi nested `run` nhưng bypass proxy.

**Chỉ một test reflection `@Trace` true** sẽ bỏ lỡ sự khác biệt giữa `DIRECT` và `PROXY`. Đây chính là bài học trọng tâm.

## 21. Những nhầm lẫn phổ biến

1. **“Thêm `@Trace` tự in log.”** Sai nếu không có reader/matcher/interceptor.
2. **“Retention `RUNTIME` đồng nghĩa JVM tự áp aspect.”** Sai, nó chỉ hỗ trợ runtime metadata lookup.
3. **“Annotation processor là around advice.”** Không; processor chạy lúc compile, behavior runtime chỉ có nếu code/weaving được tạo tương ứng.
4. **“`CLASS` annotation luôn thấy qua `getAnnotation()`.”** Sai.
5. **“`SOURCE` annotation không thể có mục đích.”** Nó có thể dùng cho compile-time validation/generation.
6. **“`@Target(METHOD)` tạo method-execution join point.”** Không; target chỉ giới hạn vị trí annotation.
7. **“`@Target(FIELD)` tự intercept field reads.”** Không.
8. **“Annotation ở interface tự hiện trên implementation method.”** Không theo direct reflection thông thường.
9. **“`@Inherited` làm mọi method annotations được thừa kế.”** Không; quy tắc này không rộng như vậy.
10. **“Meta-annotation tự được mọi scanner nhận diện đệ quy.”** Không, scanner phải hỗ trợ traversal.
11. **“Một method có annotation nghĩa pointcut đã chọn nó.”** Chưa đủ: rule/capability/coverage vẫn quyết định.
12. **“Pointcut chọn được thì advice chắc chạy.”** Không nếu invocation bypass proxy hoặc class không woven.
13. **“Một proxy nhìn thấy mọi self-call.”** Không; `this.run()` có thể bypass.
14. **“Annotation ở class tự phủ mọi methods.”** Phải có rule xác định scope.
15. **“Annotation quyết định thứ tự của nhiều aspects.”** Không nếu engine cần precedence policy riêng.
16. **“Annotation auto rollback side effects.”** Không; transaction/compensation là cơ chế độc lập.
17. **“`@Cached` chứng minh method pure.”** Không.
18. **“Method return Future tức task đã thành công.”** Không.
19. **“Handler có `Method` nên call sẽ luôn match đúng overload.”** Cần map implementation/bridge/generics đúng.
20. **“Annotation metadata tự cung cấp thread-safety.”** Không.
21. **“Không cần test unannotated methods.”** Negative coverage rất quan trọng.
22. **“Test reflection true là integration test AOP.”** Không.
23. **“Thấy advice log là đã có security enforcement trên mọi đường.”** Không nếu raw/direct paths khác vẫn tồn tại.
24. **“Đổi annotation value không cần rebuild/redeploy.”** Phụ thuộc thời điểm scanning/weaving và cache.
25. **“Dynamic proxy làm thay đổi class target.”** Không; proxy có runtime class khác.
26. **“Annotation luôn là bắt buộc để viết pointcut.”** AOP có thể chọn bằng signature/flow/loại join point.
27. **“Cứ dùng reflection tại mỗi invocation là tối ưu.”** Có thể đắt, cần đo và cache đúng.
28. **“Annotation ở method cũng là annotation ở parameter/type use.”** Java phân biệt từng `ElementType`.
29. **“Một regex scan theo tên annotation là đủ an toàn.”** Có classloader/version/type identity và annotation values.
30. **“`@RequiresPermission` tự cấm caller không có quyền.”** Không có enforcement chỉ từ metadata.
31. **“Bỏ `@Trace` không ảnh hưởng gì nếu code target giữ nguyên.”** Nếu interceptor đọc annotation, behavior thực có thể thay đổi.
32. **“AOP engine nào cũng hỗ trợ constructors/private/fields.”** Join point capability khác nhau.
33. **“AOP runtime biết metadata nhưng không cần instance hook.”** Vẫn cần cơ chế cài can thiệp để advice chạy.
34. **“Một annotation ở interface đảm bảo classloader khác luôn hiểu nó.”** Runtime type identity và module visibility quan trọng.
35. **“Đã weave là đã gọi advice.”** Class definition/transform không đồng nghĩa một join point đã xảy ra.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Method có `@Trace` nhưng không có proxy, weaver hoặc interceptor. Có tự chạy advice không?  
**Đáp án:** Không; annotation chỉ khai báo metadata.

**Câu 2.** `RetentionPolicy.RUNTIME` thêm bảo đảm gì?  
**Đáp án:** Metadata có thể được đọc bằng Java runtime reflection API; nó không tự kích hoạt AOP.

**Câu 3.** `RetentionPolicy.CLASS` có thể hữu ích cho binary weaver không?  
**Đáp án:** Có nếu weaver đọc classfile attributes phù hợp; nhưng runtime reflection thông thường không thấy nó.

**Câu 4.** `@Target(ElementType.METHOD)` có nghĩa mọi calls tới method đều được intercept?  
**Đáp án:** Không. `@Target` chỉ nói vị trí được phép gắn annotation.

**Câu 5.** Annotation trên interface method có tự xuất hiện là direct annotation của method override không?  
**Đáp án:** Không; phải định nghĩa scanner traversal/lookup policy.

**Câu 6.** Vì sao `core.run("A")` không in advice dù `Core.run` có `@Trace`?  
**Đáp án:** Vì gọi raw core, không đi qua proxy interceptor.

**Câu 7.** Vì sao `proxy.run("B")` in advice?  
**Đáp án:** Vì invocation handler đọc metadata của implementation method, chọn true rồi chủ động in trước/sau.

**Câu 8.** Vì sao `proxy.outer("C")` không in advice cho `this.run("C")` bên trong?  
**Đáp án:** Self-invocation gọi trực tiếp method target, không đi qua proxy.

**Câu 9.** Có thể dùng annotation processor để tạo AOP runtime không?  
**Đáp án:** Có thể dùng processor sinh code phục vụ runtime; nhưng processor và annotation riêng lẻ không phải advice khi method chạy.

**Câu 10.** `@Inherited` làm method annotations tự được kế thừa?  
**Đáp án:** Không. Đó không phải quy tắc thừa kế tự động cho methods.

**Câu 11.** Với composed annotation, `isAnnotationPresent(Trace.class)` tự tìm transitive meta-annotations?  
**Đáp án:** Không; phải có traversal policy/cơ chế phù hợp.

**Câu 12.** Annotation `@Audited` bảo đảm event chỉ phát sau DB commit không?  
**Đáp án:** Không. Thời điểm commit và delivery cần được thiết kế ở transaction/outbox/advice boundary.

**Câu 13.** Làm sao chứng minh annotation-driven AOP thực sự hoạt động?  
**Đáp án:** Test đủ metadata, discovery, matching và invocation qua proxy/weaver thật, cả positive lẫn negative paths.

**Câu 14.** Vì sao reflection thấy `@Trace` chưa đủ kết luận mọi callers được bảo vệ?  
**Đáp án:** Vì callers có thể đi qua raw target, self-call, loader khác hoặc join points không instrument.

## 23. Checklist áp dụng thực tế

### Khai báo metadata

- [ ] Annotation có `@Target` phù hợp loại phần tử.
- [ ] Chọn `RetentionPolicy` theo consumer thực sự.
- [ ] Định nghĩa elements/default values và validation constraints rõ.
- [ ] Phân biệt annotation trên type/interface/implementation/method.
- [ ] Nếu dùng meta/repeatable annotations, xác định traversal policy.
- [ ] Tài liệu hóa rằng annotation tự nó không tạo AOP behavior.

### Cài cơ chế AOP

- [ ] Xác định method selector/pointcut cụ thể.
- [ ] Có cơ chế proxy/weaving/dispatcher được cài thật.
- [ ] Dùng đúng classloader/artifact; tránh raw/woven mismatch.
- [ ] Với proxy, callers giữ proxy reference, không raw target nếu cần interception.
- [ ] Resolve implementation vs interface annotation đúng.
- [ ] Xử lý overload, generics, bridge methods và Object methods.
- [ ] Xác định advice order, exception propagation và `proceed` contract.
- [ ] Không dùng annotation như bảo đảm auth/transaction/caching mặc định.
- [ ] Thiết kế policy khi annotation thiếu hoặc metadata invalid.
- [ ] Cache scanner metadata an toàn theo classloader/version.

### Kiểm thử và vận hành

- [ ] Reflection tests theo SOURCE/CLASS/RUNTIME retention.
- [ ] Direct annotated method không tự chạy advice trong môi trường chưa instrument.
- [ ] Proxy/woven invocation có chạy advice chính xác.
- [ ] Unannotated method không bị match nhầm.
- [ ] Test interface vs implementation placement và `@Inherited`.
- [ ] Test self-invocation/proxy bypass, nested calls và exception.
- [ ] Test async completion/context và concurrency khi concern yêu cầu.
- [ ] Kiểm coverage của field/constructor/private join points theo tool capability.
- [ ] Kiểm true runtime artifact/configuration, không chỉ gọi advice unit-test trực tiếp.
- [ ] Benchmark scanning/interception overhead và theo dõi failures khi triển khai.
- [ ] Audit annotation changes như thay đổi policy/API, không chỉ cosmetic code change.

## 24. Tổng kết

**Annotation là siêu dữ liệu; AOP là một cơ chế can thiệp vào việc thực thi chương trình.** `@Trace`, `@Audited` hay một annotation tùy biến chỉ khai báo dữ liệu. Chúng có ý nghĩa AOP **khi** một reader/pointcut rule nhận diện chúng **và** một proxy, weaver, transformer hoặc interceptor thật sự khiến advice chạy ở join point đã chọn. `@Retention(RUNTIME)` giúp reflection thấy annotation, chứ không tự khởi chạy advice.

Muốn thiết kế đúng, hãy tách **declaration → discovery → matching → interception → execution**, phân biệt interface/implementation metadata, retention, meta-annotations, proxy bypass, self-invocation và async boundaries. Với các concern bắt buộc như phân quyền hoặc audit, đừng coi annotation là ranh giới an toàn nếu chưa có enforcement và coverage tests tương ứng.

Ví dụ Java 17 chứng minh điều này một cách có thể kiểm tra: cùng method có `@Trace` nhưng raw call không in advice; proxy call in before/after vì handler được viết rõ ràng; unannotated method không match; internal `this.run()` không đi qua proxy. **Chìa khóa không phải dấu @, mà là cơ chế đọc và áp dụng quy tắc được xây dựng có chủ đích.**