# Đánh dấu ở cấp kiểu, phương thức hoặc tham số trong AOP

## 1. Tại sao vị trí đánh dấu lại quan trọng?

Trong **Aspect-Oriented Programming (AOP)**, một **aspect** mô tả mối quan tâm xuyên cắt; một **pointcut** xác định tập **join point** được chọn, còn **advice** thực hiện hành vi bổ sung trước, sau hoặc bao quanh những join point đó. **Annotation** là một loại **metadata khai báo** thường giúp xác định ý định của tác giả mã nguồn thay vì chỉ phỏng đoán từ tên method hoặc package.

Ví dụ cùng ý tưởng audit có thể được đánh dấu ở ba vị trí:

~~~java
@AuditedType
class PaymentOperations {

    @AuditedOperation
    void transfer(@SensitiveValue String account, long amount) {
        // Mã xử lý chuyển tiền
    }
}
~~~

Đây là **snippet minh họa**, chưa phải một chương trình độc lập. Ba annotation ở đây chưa được định nghĩa; phần sau sẽ có ví dụ Java 17 đầy đủ.

**Ba mức đánh dấu diễn đạt ba ý nghĩa khác nhau:**

1. **Cấp kiểu (type):** mô tả vai trò, chính sách mặc định hoặc phạm vi cho toàn bộ class/interface/annotation type.
2. **Cấp phương thức (method):** mô tả một operation cụ thể: cần audit, retry, đo thời gian, kiểm soát quyền, validation hoặc tracing.
3. **Cấp tham số (parameter):** mô tả **một tham số khai báo**: dữ liệu nhạy cảm, định danh tenant, giá trị cần validate hoặc tham số dùng làm cache key.

Điều quan trọng: annotation chỉ là **metadata**. Bản thân việc đặt @AuditedOperation hoặc @SensitiveValue **không tự động chạy advice**, không tự tạo kiểm tra bảo mật và không tự lọc dữ liệu nhạy cảm. Cần có một compiler/weaver/interceptor/metadata processor thật sự hiểu và áp dụng quy tắc đó.

Bài tập trung **AOP tổng quát**, từ chọn join point bằng metadata đến đọc metadata runtime, precedence, inheritance, override, proxy, weaving, validation, concurrency và testing. Java 17 dùng để minh họa annotation/reflection một cách chạy được; các biểu thức pointcut ở phần giải thích là **giả mã khái niệm**, không giả định mọi ngôn ngữ AOP có cùng syntax.

## 2. Annotation khác comment, naming convention và marker interface

| Cách biểu đạt | Điểm mạnh | Giới hạn |
|---|---|---|
| Comment | Dễ diễn giải ý định | Không có semantics tự động với compiler/runtime nếu không có processor |
| Tên như saveAudited | Có thể đọc được | Mơ hồ, khó kiểm soát rename và overload |
| Marker interface | Biểu diễn **quan hệ kiểu** | Không mô tả tự nhiên một tham số hoặc một method riêng |
| Type annotation | Rõ chính sách của class/interface | Chưa nhất thiết diễn đạt mọi method, cần quy tắc kế thừa/phủ |
| Method annotation | Rõ operation cụ thể | Cần xác định method declaration nào được soi |
| Parameter annotation | Gắn metadata đúng tham số | Cần reflection/binding và cách áp dụng chính sách |
| External configuration | Không làm code chứa nhiều metadata | Mapping với type/method có thể drift theo refactor |

Một marker interface có thể thay type hierarchy; annotation thường mô tả metadata mà không nhất thiết đổi inheritance. Trong AOP, chọn theo annotation có thể sạch hơn chọn theo tên, nhưng **không có một cách tốt nhất cho mọi trường hợp**.

### 2.1. Annotation là khai báo; advice là hành động

~~~text
Source code
   |
   +-- Annotation metadata
   |
   v
Compiler / runtime metadata
   |
   v
Pointcut matching / metadata lookup
   |
   v
Advice selected?
   |
   +-- Không --> Target thực thi theo đường bình thường
   |
   +-- Có ---> Before/Around/After theo ngữ nghĩa engine
~~~

Nếu annotation không được retention hoặc nếu target không nằm trong phạm vi weaving, điểm đánh dấu có thể hoàn toàn không dẫn tới behavior mong đợi.

## 3. Các thành phần định nghĩa annotation trong Java

Một custom annotation là một kiểu đặc biệt khai báo bằng @interface.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
@interface PolicyMark {
    String value();
}
~~~

Đây là một đoạn minh họa; có thể chạy khi đặt trong một source file hợp lệ cùng imports và declarations cần thiết.

Các thành phần:

- **@interface:** định nghĩa annotation type.
- **@Target:** hạn chế những vị trí khai báo nào được phép mang annotation.
- **@Retention:** chỉ định annotation còn tồn tại tới giai đoạn nào.
- **Annotation elements:** value(), name(), enabled()... mô tả dữ liệu được gắn.
- **Default value:** cung cấp mặc định cho element khi annotation không truyền giá trị đó.

### 3.1. @Target không đồng nghĩa type-checking của AOP

@Target giúp compiler kiểm tra vị trí **đặt annotation**. Nó không tự nói một AOP pointcut sẽ match các vị trí đó; việc match vẫn do ngôn ngữ AOP và join point model quyết định.

### 3.2. Annotation elements có giới hạn kiểu

Trong Java, annotation elements không thể tùy ý là Object, List hay một Strategy instance mutable. Những loại được phép gồm primitives, String, Class literals, enums, annotation types và mảng một chiều của các loại cho phép. Giá trị annotation phải đáp ứng quy tắc compile-time constant thích hợp.

Nếu chính sách cần cấu trúc dữ liệu phức tạp, hãy gắn một **policy ID hoặc enum** rồi resolve ra immutable Policy object trong một registry. Đừng biến annotation thành một ngôn ngữ cấu hình tùy tiện không validate.

## 4. Cấp kiểu: @Target(TYPE)

Annotation cấp kiểu có thể được đặt trên class, interface, enum, record hoặc annotation type tùy @Target và quy tắc ngôn ngữ.

~~~java
@AuditedType
class InventoryService {
    void receive() { }
    void ship() { }
}
~~~

Đây là snippet minh họa, chưa định nghĩa @AuditedType.

Cách diễn giải AOP có thể là: mọi operation **trong những type mang @AuditedType** là ứng viên cho audit advice, trừ khi policy loại trừ. Một rule khác có thể chỉ ghi metadata để registrar biết class có một capability.

### 4.1. Cấp kiểu là chính sách mặc định hay bắt buộc?

Cần phân biệt:

- **Mặc định:** annotation cấp kiểu áp dụng cho mọi method trừ khi có override hợp lệ.
- **Bắt buộc:** mọi method có effect quan trọng phải chịu policy, annotation method không được tắt.
- **Phạm vi:** chỉ những method có annotation riêng mới được chọn, nhưng type annotation xác định group/tenant.
- **Đăng ký:** chỉ ghi nhận type để một công cụ build/runtime scan, không tự chọn mọi method.

Không thể suy semantics từ tên @AuditedType; quy tắc thực phải được tài liệu hóa.

### 4.2. Cấp kiểu không phải khai báo tại mọi method

Một class có annotation **không làm annotation ấy xuất hiện trên các Method objects** của từng method trong Java reflection. Một tool có thể tự kết hợp method metadata với declaring/runtime type metadata để suy inherited/default policy, nhưng đó là **logic của tool**, không phải Java tự nhân bản annotation.

## 5. Cấp phương thức: @Target(METHOD)

Annotation cấp method diễn đạt chính xác **một operation**.

~~~java
class PaymentService {
    @Measured
    void charge() { }

    void lookup() { }
}
~~~

Đây là snippet minh họa; @Measured chưa được định nghĩa.

Cơ chế AOP có thể lựa chọn execution của charge() mà không áp vào lookup(). Nó hữu ích cho các chính sách:

- Theo dõi latency theo operation.
- Audit một thao tác đụng trạng thái quan trọng.
- Retry một operation idempotent có điều kiện.
- Authorization ở entrypoint tin cậy.
- Giới hạn tần suất xử lý.
- Transaction boundary theo yêu cầu.
- Phân loại event schema cho một API.

### 5.1. Method annotation không nhất thiết bằng call join point

Một AOP language có thể phân biệt:

- **call join point:** tại vị trí gọi một method.
- **execution join point:** khi method body thực thi.
- **constructor execution:** không phải METHOD annotation bình thường.
- **field get/set:** không phải method execution.

Nếu mục tiêu là **mọi lần method thực thi**, cần hiểu pointcut chọn execution hay call. Annotation nằm trên method declaration không tự quyết định join point kind.

### 5.2. Method annotation và overload

Hai overloads:

~~~java
void save(String id) { }
void save(String id, boolean force) { }
~~~

có thể mang annotations khác nhau. Match theo tên save đơn thuần dễ chọn sai. Khi cần phân biệt rõ method, xem tên, declaring type, parameter types, return signature và annotation của **đúng Method**.

### 5.3. Getter, bridge và compiler-generated methods

Compiler có thể tạo **bridge methods** cho generic override hoặc covariant return. Khi scan reflection và lựa chọn join points, có nguy cơ nhìn thấy bridge/synthetic methods với metadata khác nhau.

Nên kiểm tra Method.isBridge(), Method.isSynthetic() khi cần và xác định policy áp ở logical user method hay generated bridge. Không mặc định mọi runtime/compiler truyền annotation tới bridge theo cùng một chiến lược.

## 6. Cấp tham số: @Target(PARAMETER)

Annotation cấp tham số gắn với **parameter declaration**:

~~~java
void transfer(
    @SensitiveValue String accountId,
    @ValidatedAmount long amount,
    @CorrelationId String traceId
) { }
~~~

Đây là snippet minh họa. Các annotation cần được định nghĩa riêng.

Các use cases:

- **Redaction:** không log giá trị của tham số nhạy cảm.
- **Validation:** kiểm tra nonblank, range, format của một tham số.
- **Context extraction:** lấy tenant ID hoặc correlation ID từ vị trí đúng.
- **Cache key selection:** xác định tham số nào góp phần tạo key.
- **Metrics tags:** chỉ dùng whitelisted fields.
- **Authorization:** tham số nào biểu diễn resource ID; vẫn cần context tin cậy.
- **Data classification:** phân biệt PII/secrets và dữ liệu công khai.

**Parameter annotation không phải annotation của runtime value.** Nếu method có @SensitiveValue String token, metadata thuộc declaration của tham số, không tự gắn vào String object truyền vào.

### 6.1. Parameter index và parameter name

Reflection trả các Parameter objects tương ứng vị trí khai báo; có thể xem index và annotations. **Tên tham số** không nhất thiết được giữ dưới dạng đáng tin mặc định trong bytecode; để reflection thấy source names thường biên dịch với **javac -parameters**.

Không cần -parameters để đọc annotation được retain tại runtime; hai cơ chế độc lập. Một processor có thể dùng parameter position thay vì name khi xác định value tương ứng.

### 6.2. Parameter annotations và arrays

Java reflection có thể dùng:

~~~java
Parameter[] parameters = method.getParameters();
for (Parameter parameter : parameters) {
    // Đọc annotation khai báo trên từng parameter.
}
~~~

Hoặc getParameterAnnotations(). Nhưng cần bảo đảm method đã được giải quyết đúng, đặc biệt khi interface method, implementation method, bridge method hoặc proxy method có metadata khác nhau.

### 6.3. TYPE_USE không đồng nghĩa PARAMETER

@Target(PARAMETER) cho phép đánh dấu **declaration của tham số**. @Target(TYPE_USE) cho phép annotation ở **nơi dùng kiểu**, chẳng hạn trên generic type argument hoặc một vị trí type use trong khai báo.

~~~java
void handle(@SensitiveValue String token) { }
List<@NonNullType String> ids;
~~~

Đây là snippets minh họa; cần định nghĩa annotation types với targets phù hợp. Annotation @NonNullType ở generic type argument cần TYPE_USE, không phải chỉ PARAMETER.

Với type-use annotation, đọc metadata có thể phải dùng **AnnotatedType/AnnotatedParameterizedType** thay vì chỉ Method.getParameterAnnotations(). Các AOP languages không nhất thiết hỗ trợ mọi type-use annotation như điều kiện pointcut.

## 7. Retention: SOURCE, CLASS, RUNTIME

Java @Retention có ba giá trị chính:

| Retention | Có trong nguồn? | Có trong class file? | Reflection runtime thấy trực tiếp? |
|---|---|---|---|
| **SOURCE** | Có | Thường không lưu | Không |
| **CLASS** | Có | Có, theo class-file annotations | Thường không qua core reflection API |
| **RUNTIME** | Có | Có | Có, theo phạm vi reflection được hỗ trợ |

Điểm cần hiểu:

- **SOURCE** phù hợp cho source analyzers, annotation processors hoặc compiler checks.
- **CLASS** phù hợp cho binary tooling hoặc weaver đọc class file mà không cần reflection thấy runtime.
- **RUNTIME** cần thiết nếu dùng Java reflection runtime để đọc annotation qua getAnnotation/getAnnotationsByType.

### 7.1. Không phải AOP nào cũng cần RUNTIME

Một **compile-time weaver** có thể đọc metadata trong nguồn/class file để dệt advice và tạo bytecode cuối, không nhất thiết đòi reflection runtime thấy annotation. Ngược lại, một **runtime reflection-based interceptor** thường cần RUNTIME retention nếu nó đọc annotations qua core reflection.

Vì vậy chọn retention theo **lúc nào và bằng công cụ nào metadata được đọc**, không theo một lời khuyên chung “AOP luôn phải RUNTIME”.

### 7.2. @Retention mặc định

Nếu không ghi @Retention, Java annotation type mặc định có **CLASS retention**. Không tự giả định một annotation viết tay sẽ có thể đọc bằng getAnnotation ở runtime.

### 7.3. Không nhầm RUNTIME với runtime behavior

@Retention(RUNTIME) chỉ giữ metadata; không làm annotation tự gọi advice hoặc policy. Nếu không có một consumer xử lý nó, annotation không tạo hiệu ứng.

## 8. @Inherited chỉ hỗ trợ một loại kế thừa hẹp

**@Inherited** là meta-annotation mà Java reflection hỗ trợ cho **class-level annotation inheritance** trong những điều kiện được định nghĩa.

Ví dụ:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category { String value(); }

@Category("base")
class BaseTask { }

class DerivedTask extends BaseTask { }
~~~

Đây là ví dụ minh họa, cần imports.

Khi tìm Category trên DerivedTask.class, một truy vấn reflection phù hợp có thể nhìn thấy Category kế thừa từ superclass dù DerivedTask không khai báo trực tiếp.

Nhưng có ba giới hạn:

1. **Không tự kế thừa annotation của interface** sang implementing class theo Java @Inherited rules.
2. **Không áp dụng cho method annotation** chỉ vì subclass override method.
3. **Không áp dụng cho parameter annotations** của method overriding một method khác.

Một annotation type có @Inherited và đồng thời cho phép TYPE/METHOD/PARAMETER **không làm method/parameter annotations tự được inherited**.

### 8.1. Kế thừa metadata khác kế thừa behavior

Java inheritance có thể cho subclass sử dụng inherited method body. Nếu subclass không override method, reflection tìm method theo API phù hợp có thể trả inherited Method object mang annotation của superclass. Nhưng nếu subclass **override method không đánh dấu**, annotation trên override declaration không tự được truyền từ base method.

Hai trường hợp này khác nhau:

~~~text
Child không override -> gọi inherited Base.execute method.
Child override không annotate -> Child.execute là declaration mới.
~~~

### 8.2. Vì sao điều này nguy hiểm cho AOP?

Nếu một security rule chỉ kiểm tra annotation trực tiếp của concrete override, nó có thể bỏ sót annotation security trên base declaration. Nhưng nếu nó luôn lùi về base thì có thể áp một policy cũ mà subclass muốn thay đổi.

Không có luật mặc định chung; **quy tắc hợp nhất metadata qua hierarchy phải được xác định, test và quản trị**. Với enforcement bắt buộc, tránh suy “thiếu annotation tức allow”.

## 9. @Repeatable: nhiều rule trên cùng vị trí

Nếu một method cần nhiều nhãn độc lập:

~~~java
@Rule("audit")
@Rule("timed")
void transfer() { }
~~~

Annotation Rule phải khai báo **@Repeatable(Container.class)** và một container annotation phù hợp.

Trong Java, khi cần lấy **tất cả annotations lặp**, dùng:

~~~java
Rule[] rules = method.getAnnotationsByType(Rule.class);
~~~

thay vì chỉ dùng getAnnotation(Rule.class) và giả định nó trả toàn bộ.

### 9.1. Container annotation không chỉ là chi tiết cú pháp

Compiler biểu diễn repeated annotations bằng một container trong các trường hợp cần thiết. Container cần target/retention tương thích; nếu muốn class-level inheritance của repeated annotations, cần chú ý @Inherited trên repeatable type và container theo Java rules.

### 9.2. Precedence khi có nhiều rules

Một method @Rule("audit") @Rule("timed") không xác định sẵn advice ordering. Có thể có nhiều aspects độc lập, hoặc một consumer tổng hợp rules rồi áp một strategy. Thứ tự advice phải đến từ AOP semantics/precedence tường minh, không lấy thứ tự khai báo annotations làm hợp đồng nếu công cụ không bảo đảm.

## 10. Ví dụ Java 17 chạy được: TYPE, METHOD, PARAMETER, @Inherited và @Repeatable

Ví dụ này có:

- Annotation @Rule dùng được ở TYPE, METHOD và PARAMETER.
- @Retention(RUNTIME) để reflection nhìn thấy.
- @Inherited để kiểm chứng **class-level inheritance**.
- @Repeatable(Rules.class) để gắn hai rules vào một method.
- Interface được annotate nhưng implementing class không tự inherited.
- Base method được annotate; Child override không tự inherited.
- Parameter annotations của Base không tự xuất hiện trên Child override.
- Compiler flag **-parameters** để in ra source parameter names.

**Đây là reflection demo, không tự dệt AOP advice.** Output giúp xác định metadata mà một AOP integration có thể cần đọc trước khi thực thi policy.

Tạo file **AnnotationScopeDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.stream.Collectors;

public class AnnotationScopeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
    @Inherited
    @Repeatable(Rules.class)
    @interface Rule {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
    @Inherited
    @interface Rules {
        Rule[] value();
    }

    @Rule("type:parent")
    static class Parent {
        @Rule("method:audit")
        @Rule("method:timed")
        public String execute(@Rule("param:redact") String secret,
                              @Rule("param:positive") int count) {
            return "parent:" + count;
        }
    }

    static class Child extends Parent {
        @Override
        public String execute(String secret, int count) {
            return "child:" + count;
        }
    }

    @Rule("type:interface")
    interface Contract {}

    static class ContractImpl implements Contract {}

    static String labels(AnnotatedElement element) {
        return Arrays.stream(element.getAnnotationsByType(Rule.class))
                .map(Rule::value)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    static String parameterNames(Method method) {
        return Arrays.stream(method.getParameters())
                .map(Parameter::getName)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        Method parentMethod = Parent.class.getDeclaredMethod(
                "execute", String.class, int.class);
        Method childMethod = Child.class.getDeclaredMethod(
                "execute", String.class, int.class);
        System.out.println("Parent.type=" + labels(Parent.class));
        System.out.println("Child.type=" + labels(Child.class));
        System.out.println("Child.declared=" + Arrays.toString(
                Child.class.getDeclaredAnnotationsByType(Rule.class)));
        System.out.println("ContractImpl.type=" + labels(ContractImpl.class));
        System.out.println("Parent.method=" + labels(parentMethod));
        System.out.println("Child.method=" + labels(childMethod));
        System.out.println("Parent.param0=" + labels(parentMethod.getParameters()[0]));
        System.out.println("Parent.param1=" + labels(parentMethod.getParameters()[1]));
        System.out.println("Child.param0=" + labels(childMethod.getParameters()[0]));
        System.out.println("Parent.parameterNames=" + parameterNames(parentMethod));
        System.out.println("Child.execute=" + new Child().execute("hidden", 2));
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~bash
javac --release 17 -parameters AnnotationScopeDemo.java
java AnnotationScopeDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
Parent.type=[type:parent]
Child.type=[type:parent]
Child.declared=[]
ContractImpl.type=[]
Parent.method=[method:audit, method:timed]
Child.method=[]
Parent.param0=[param:redact]
Parent.param1=[param:positive]
Child.param0=[]
Parent.parameterNames=secret,count
Child.execute=child:2
~~~

### 10.1. Vì sao Child.type có type:parent?

Rule và Rules cùng mang @Inherited. Parent có @Rule("type:parent"), Child kế thừa Parent, nên truy vấn getAnnotationsByType trên **Child.class** nhìn thấy annotation inherited trong điều kiện demo.

### 10.2. Vì sao Child.declared rỗng?

getDeclaredAnnotationsByType chỉ đọc annotations **khai báo trực tiếp** trên Child, không lấy annotations inherited. Vì Child không annotate riêng nên kết quả [].

### 10.3. Vì sao ContractImpl.type rỗng?

Contract interface có @Rule("type:interface"), nhưng @Inherited không truyền type annotation từ **interface** sang một class implements nó. Một AOP consumer muốn lấy annotations trên interfaces cần **tự chủ động duyệt interfaces** và có chính sách xử lý conflict.

### 10.4. Vì sao Parent.method có hai rules?

Parent.execute mang hai @Rule và annotation repeatable, nên getAnnotationsByType trả cả hai theo reflection semantics.

### 10.5. Vì sao Child.method rỗng?

Child tự override execute, không khai báo @Rule trên method override. Java reflection không tự sao chép method annotations từ Parent.execute sang Child.execute. Tương tự, annotation trên parameter 0 không tự xuất hiện ở parameter declaration của Child.execute.

### 10.6. Vì sao Parent.parameterNames có secret,count?

Demo biên dịch với **-parameters**, cho phép reflection nhìn tên source parameters trong class file. Không có flag này, tên có thể là arg0/arg1; metadata annotation vẫn được retain bởi @Retention(RUNTIME), độc lập với parameter names.

### 10.7. Vì sao Child.execute là child:2?

Đây chỉ là kết quả của Java overriding và method invocation. Annotation @Rule trên Parent.method không làm code của Child tự gọi logging, audit hoặc validation. Một AOP engine cần được cấu hình để hành động.

## 11. Cách sử dụng annotation làm pointcut

Một thiết kế AOP có thể có những điều kiện khái niệm:

~~~text
Candidate executions within types marked @AuditedType
    AND/OR
Executions of methods marked @AuditedOperation
    AND/OR
Method execution whose parameter declaration carries @SensitiveValue
~~~

**Đây là giả mã**, không phải cú pháp pointcut dùng chung.

### 11.1. Chọn theo type

Nếu aspect quan tâm mọi public operations trong nhóm types có @Observed, một type-based pointcut có thể xác định phạm vi chung. Nhưng phải làm rõ annotation được đọc từ:

- Declaring type của method.
- Runtime receiver class.
- Parent superclass.
- Interface declaration.
- Proxy/generated subclass.
- Một metadata index được build trước.

Những lựa chọn này **không đồng nhất** khi có inheritance/overrides/proxies.

### 11.2. Chọn theo method

Một method-annotation pointcut có thể đánh dấu một execution đặc biệt. Nếu annotation nằm ở **interface method**, implementation method không annotate, matcher cần biết nó đọc interface declaration hay concrete implementation.

Một interception model dựa proxy có thể nhìn **interface Method object**; một execution weaver có thể chọn **concrete implementation method**. Không tuyên bố một annotation trên interface tự luôn match execution của implementation ở mọi engine.

### 11.3. Chọn theo parameter

Không phải mọi AOP engine có sẵn pointcut primitive “method với tham số thứ hai có @SensitiveValue”. Nếu không hỗ trợ trực tiếp, có thể:

1. Chọn một tập method executions đủ hẹp.
2. Resolve metadata trên **đúng Method declaration**.
3. Đọc annotations từng Parameter theo index.
4. Ghép với arguments của invocation theo contract.
5. Dùng policy xác định argument nào được phép quan sát/log/validate.
6. Thực thi behavior trong advice theo lifecycle đúng.

Phải xử lý varargs, bridge methods, overloaded methods và proxy interface signatures nếu hệ thống sử dụng chúng.

## 12. Kết hợp ba cấp annotation thành một effective policy

Trong thiết kế thực tế, một method có thể nhận chính sách từ type, method và parameter cùng lúc.

Ví dụ:

~~~text
Type:    @Audit(enabled=true, mode=SUMMARY)
Method:  @Audit(mode=FULL)
Param 0: @Sensitive
Param 1: @PublicField
~~~

Mong muốn:

- Type định nghĩa default audit.
- Method có thể override mode theo quy tắc.
- Parameter annotations giới hạn **fields được phép ghi**.

Một **thứ tự hợp nhất metadata** có thể là:

~~~text
Global mandatory constraints
        |
        v
Type-level defaults
        |
        v
Method-level specialization
        |
        v
Parameter-level data classification
        |
        v
Effective policy validated
        |
        v
Advice execution
~~~

Đây là **một lựa chọn kiến trúc**, không phải quy tắc kế thừa annotation mặc định của Java hay tất cả ngôn ngữ AOP.

### 12.1. Phải phân biệt override được phép và invariant bắt buộc

Ví dụ type @AuditRequired có thể quy định mọi operation phải audit. Một method-level annotation @NoAudit không được phép vô hiệu hóa yêu cầu bắt buộc chỉ vì nó “ở cấp cụ thể hơn”.

Ngược lại, type @ObserveDefault có thể được method @IgnoreMetric override. Cần mô hình hóa rõ **non-overridable mandatory policy** và **overridable default policy**.

### 12.2. Không dùng policy merge ngầm

Khi hai interfaces cùng khai báo method với annotations khác nhau, một implementation có thể nhận hai conflicting policies nếu matcher duyệt cả hai. Phải có quy tắc conflict: báo lỗi build, chọn precedence đã công bố hoặc gộp theo một operation xác định. Không để thứ tự reflection iteration quyết định quyền truy cập.

### 12.3. Data classification là giới hạn trên việc quan sát

Nếu parameter @Sensitive, một annotation cấp method yêu cầu "log full arguments" không được tùy tiện ghi raw secret. Redaction/PII constraints có thể là quy tắc ưu tiên cao hơn, không phải option dễ bị override.

## 13. Reflection API quan trọng

| API | Công dụng |
|---|---|
| Class.getAnnotation(X.class) | Tìm annotation type theo semantics inherited của Java reflection |
| Class.getDeclaredAnnotation(X.class) | Chỉ annotation khai báo trực tiếp |
| AnnotatedElement.getAnnotationsByType(X.class) | Lấy các repeatable annotations, gồm semantics liên quan |
| AnnotatedElement.getDeclaredAnnotationsByType(X.class) | Lấy repeatable annotations khai báo trực tiếp |
| Method.getParameters() | Lấy Parameter objects |
| Method.getParameterAnnotations() | Lấy mảng annotation cho từng vị trí parameter |
| Parameter.getAnnotation(X.class) | Annotation trên parameter declaration |
| Parameter.getName() | Tên parameter nếu metadata được lưu |
| Method.isBridge() | Nhận diện compiler bridge method |
| Method.isSynthetic() | Nhận diện synthetic method |
| Class.getDeclaredMethods() | Methods khai báo trên class |
| Class.getMethods() | Public methods theo contract bao gồm inherited methods |

### 13.1. Annotation scanning cần cache có kiểm soát

Nếu lời gọi AOP chạy rất thường xuyên, tìm reflection metadata trên mọi invocation có thể tốn CPU và allocation. Có thể resolve **immutable policy descriptor** cho từng logical method rồi cache.

Nhưng key của cache cần tính tới:

- Declaring class/method signature.
- Class loader identity.
- Proxy/target mapping.
- Bridge/synthetic method resolution.
- Phiên bản policy/config.
- Reload/instrumentation lifecycle.

Không cache theo method name đơn thuần vì overloads khác nhau. Không dùng một global strong-reference cache vô hạn để giữ mọi ClassLoader plugin sống mãi.

### 13.2. Khi metadata thay đổi ở runtime?

Java annotations trên class definitions nhìn chung không phải một map mutable để bật/tắt tùy ý. Nếu cần thay policy runtime, dùng một **versioned immutable policy registry** dựa trên annotation IDs hoặc operation IDs thay vì sửa metadata giả.

## 14. Interface và implementation: xác định vị trí annotation đúng

Giả sử:

~~~java
interface Repository {
    @Traced
    void store(String key);
}

final class RepositoryImpl implements Repository {
    @Override
    public void store(String key) { }
}
~~~

Đây là snippets minh họa; @Traced chưa định nghĩa.

Một proxy interface-based có thể intercept thông qua Repository.store Method, còn implementation class method không có @Traced. Một direct execution matcher có thể nhìn RepositoryImpl.store và không tìm thấy annotation trực tiếp.

**Cùng một operation nhưng metadata sources khác nhau.** Thiết kế phải nêu một lựa chọn:

1. Annotation đặt trên interface là hợp đồng và được resolver duyệt chủ động.
2. Annotation bắt buộc đặt trên implementation để execution pointcut match.
3. Cả hai được hỗ trợ, có merge rule cụ thể.
4. Một lớp build-time validation đảm bảo interface và implementation đồng nhất.

Không khẳng định mọi runtime tự copy annotations từ interface sang implementation.

## 15. Kế thừa và override: những trường hợp đặc biệt

Nếu Parent.method có annotation và Child không override, một call tới inherited method có thể dùng Parent declaration, nên metadata trên Parent.method vẫn là metadata của method đang thực thi.

Nếu Child override không có annotation, metadata trên Child declaration khác Parent. Resolver nào chỉ đọc concrete method sẽ thấy rỗng.

Nếu Child override có một annotation khác, cần quyết định:

- Child annotation thay hoàn toàn Parent policy?
- Merge hai policies?
- Parent có một mandatory invariant?
- Child có được opt-out?
- Nếu override generic bridge phát sinh, Method object nào là logical declaration?

Với security policy, default behavior thiếu annotation cần được chọn có chủ đích và thường không thể là “cho qua” nếu thao tác cần enforcement.

## 16. Parameter annotation và redaction trong logging advice

Giả sử operation:

~~~java
void authenticate(
    @SensitiveValue String password,
    @PublicField String clientVersion
) { }
~~~

Đây là snippet minh họa.

Một advice log arguments không nên gọi:

~~~text
log("args=" + Arrays.toString(args))
~~~

vì nó có thể lộ password.

Giải pháp:

1. Resolve correct method metadata.
2. Tạo chính sách phân loại arguments bằng **parameter indices**.
3. Với parameter được đánh dấu sensitive, thay value bằng placeholder cố định.
4. Chỉ serialize fields có quyền được ghi, trong size/time limits.
5. Không để logger failure che business exception ngoài ý muốn.
6. Không in raw Throwable message/stack trace chứa secret nếu policy cấm.

### 16.1. Fail-closed đối với dữ liệu nhạy cảm

Nếu method metadata không truy cập được, tên parameter vắng mặt hoặc resolver tìm nhầm Method, với logging có dữ liệu nhạy cảm thường nên **không log arguments** thay vì log tất cả. Đây là lựa chọn conservative cần được ghi trong policy.

### 16.2. Annotation của parameter không kiểm tra giá trị tự động

Gắn @PositiveAmount vào một parameter không khiến Java compiler hoặc JVM mặc định từ chối -5. Một validator/advice phải có logic kiểm tra và quyết định ném exception ở boundary phù hợp.

### 16.3. Đừng chỉ tin metadata để bảo mật

Annotation @TenantId trên một parameter chỉ xác định **tham số nào được gọi là tenant ID**; nó không chứng minh giá trị tenant mà caller gửi thuộc quyền actor. Cần authorization dựa trên authenticated context và resource state.

## 17. Annotation và quyền áp dụng advice

Annotation nên được xem là **một tiêu chí selection**, không phải nguồn quyền lực tuyệt đối.

Ví dụ một method cần authorization nhưng developer quên gắn @RequiresPermission. Nếu bảo vệ chỉ dựa vào annotation này, method có thể được gọi mà không kiểm tra.

Cách giảm rủi ro:

- Áp mandatory security checks ở một boundary đáng tin.
- Có build-time checks cho operation bắt buộc phải annotate.
- Test positive và negative pointcut coverage.
- Dùng deny-by-default cho những operation class không có policy.
- Tách audit/telemetry optional khỏi authorization bắt buộc.
- Dùng static annotations như một lớp mô tả rõ, không thay threat model.

### 17.1. Annotation có thể bị đặt sai vị trí

@RequiresPermission trên một helper private không tương đương đặt nó ở API entrypoint nếu interceptor chỉ quan sát public interface calls. Weaver/proxy scope phải được xác minh.

### 17.2. Self-invocation và direct target access

Trong một số proxy-based mechanisms, lời gọi từ method này tới method khác **trên chính target** hoặc thông qua direct target reference có thể không đi qua proxy. Annotation vẫn tồn tại trên method nhưng advice không chạy. Binary weaving ở execution join point có khả năng khác.

Không dùng một annotation như chứng cứ rằng behavior luôn được enforce khi có các đường bypass.

## 18. Annotation inheritance không giải quyết aspect precedence

Giả sử type annotation yêu cầu tracing, method annotation yêu cầu transaction, parameter annotation yêu cầu redaction. Metadata này không mặc nhiên xác định:

~~~text
Tracing(Transaction(Business))
~~~

hay:

~~~text
Transaction(Tracing(Business))
~~~

Thứ tự outer/inner advice phụ thuộc precedence rules và configuration của engine. Khi transaction commit throw, tracing outer có thể thấy commit failure; tracing inner có thể đã kết thúc trước commit.

Một annotation có thể mang một field priority, nhưng **priority của policy** và **precedence thực thi** chỉ trùng nhau nếu engine được thiết kế để áp dụng đúng field đó.

### 18.1. Multiple annotations trên method

@Audit + @Retry + @Timed không tự nêu thứ tự. Cần có tests cho:

- Số lần business proceed.
- Số lượng audit events.
- Thời điểm đo start/stop.
- Exceptions gốc và cleanup errors.
- Transaction boundary.
- Khi policy chỉ match một số operations.

Không suy mọi annotation hoạt động độc lập; những advice lồng nhau có thể thay đổi kết quả quan sát.

## 19. Retry annotation cần kiểm soát idempotency

Gắn @Retryable lên method không tự khiến method an toàn khi chạy nhiều lần. Nếu method tạo side effects (gửi email, trừ tiền, publish message), một lần fail có thể xảy ra **sau khi side effect đã hoàn tất**.

Retry policy phải xem xét:

- Exception nào được retry.
- Maximum attempts.
- Backoff/jitter.
- Deadline/cancellation.
- Idempotency keys.
- Transaction per attempt.
- External side effect compensation.
- Mối quan hệ với logging/audit advice.

Đừng dùng annotation như lời hứa “method có thể chạy lại vô hại” nếu nghiệp vụ chưa xác nhận điều đó.

## 20. Async, threads và context propagation

Method annotation có thể ở method trả CompletableFuture hoặc một asynchronous handle.

~~~text
@Timed
CompletionStage<Result> fetchAsync(...)
~~~

Một after-returning advice trên method có thể chạy ngay sau khi method trả handle, **trước khi task thật hoàn tất**. Nếu policy muốn đo actual completion, cần instrument completion boundary.

Annotation cấp parameter như @CorrelationId có thể cho biết tham số nào mang correlation ID, nhưng **không làm ThreadLocal tự truyền qua Executor worker**.

Cần:

- Capture immutable context hợp lệ.
- Explicit propagation qua task/RPC khi được phép.
- Restore worker thread context trong finally.
- Không giữ thread-bound resource sai lifetime.
- Xác định khi nào log success/failure/cancellation.
- Kiểm tra task retry có cùng logical correlation nhưng attempt ID khác nhau không.

## 21. Kết hợp annotations với cấu hình runtime

Một annotation như @Policy("PAYMENT_AUDIT") có thể chỉ giữ một policy ID. Runtime registry map ID sang một immutable policy snapshot.

Lợi ích:

- Source thể hiện ý định.
- Policy chi tiết đổi qua validated configuration.
- Không cần code recompile mỗi khi đổi threshold.
- Có thể gắn version để audit.
- Giữ metadata nhỏ và type-safe hơn một annotation có hàng chục flags.

Rủi ro:

- Annotation trỏ policy ID không tồn tại.
- Runtime registry lỗi hoặc policy reload giữa invocation.
- Hai nodes có version khác nhau.
- Caller có thể cố chọn policy ID bất hợp lệ nếu API cho phép override.
- Metadata build-time chưa validate mapping.

Một invocation nên capture **một policy snapshot nhất quán** nếu before/after/failure cần cùng rule version. Với security/audit bắt buộc, missing policy behavior cần được định nghĩa và kiểm thử.

## 22. Annotation processing so với runtime AOP

Có hai giai đoạn khác nhau:

### 22.1. Build-time validation/processing

Một annotation processor hoặc compiler tool có thể:

- Phát hiện method thiếu annotation bắt buộc.
- Kiểm tra @SensitiveValue chỉ đặt trên những tham số hợp lệ.
- Sinh metadata index.
- Kiểm tra một annotation ID có được cấu hình không.
- Báo lỗi khi các annotations xung đột.
- Tránh một số lỗi trước khi deploy.

Nhưng một processor chỉ chạy lúc build **không mặc nhiên intercept mọi method runtime**.

### 22.2. Weaving hoặc runtime interception

Một AOP weaver/interceptor dùng metadata để chọn join points và thực thi advice. Nó có thể làm ở compile time, sau compile, lúc load hoặc qua proxy/runtime mechanism, tùy công nghệ.

Một chương trình có annotation processor nhưng không có weaving/interception phù hợp **không tự chạy AOP advice**.

## 23. Chi phí của annotation-based matching

Chi phí có thể xuất hiện ở:

- Scan type/method/parameter metadata lúc khởi tạo.
- Reflection resolution và class loader lookup.
- Resolve implementation Method từ interface Method.
- Caching policy descriptor.
- Runtime checks với dynamic context.
- Advice body: logging, metrics, serializer, remote policy.
- Allocation và GC của event/context objects.

### 23.1. Static matching có thể giảm overhead

Một compile-time weaver có thể quyết định nhiều join points bằng metadata sớm, rồi chỉ dệt những nơi match. Một runtime proxy có thể kiểm tra metadata và cache để giảm reflection work.

Không khẳng định mọi annotation-based AOP đều reflection-scan ở mỗi call hoặc luôn zero-cost.

### 23.2. Cache cần key đúng

Method signature bao gồm tên và parameter types; chỉ cache theo method name làm hai overloads bị trộn. Với interface/implementation mismatch, key có thể cần resolve logical operation identity theo cả concrete class và invoked method.

ClassLoader-scoped caches có thể gây memory retention nếu giữ Class/Method references bằng strong refs không giới hạn. Cần lifecycle hoặc weak-reference policy khi hỗ trợ plugins/reload.

### 23.3. Đo bằng workload thực

Khi tối ưu, phân biệt cost của metadata lookup với cost của advice body. Đừng đo một logger có System.out rồi quy toàn bộ latency cho annotation reflection. Có thể benchmark với JMH và kiểm tra p95/p99 qua profiling.

## 24. Ma trận kiểm thử annotation theo vị trí

| Kịch bản | Điều cần xác minh |
|---|---|
| Annotation ở class | Type-level selection đúng |
| Annotation ở interface | Resolver có hỗ trợ interface policy không |
| Subclass không annotate | @Inherited áp class annotation theo rule |
| Subclass override method | Method annotation không tự inherited |
| Override parameter | Parameter annotation không tự copy |
| Method overload | Đúng declaration được match |
| Generic bridge/synthetic method | Chọn logical method theo policy |
| Repeatable annotations | getAnnotationsByType trả đủ các rules |
| Annotation @Retention(SOURCE) | Runtime reflection không thấy |
| Annotation @Retention(CLASS) | Core reflection không mặc định thấy |
| Annotation @Retention(RUNTIME) | Reflection thấy khi query đúng |
| Parameter names không có -parameters | Resolver vẫn dựa index hợp lệ |
| @Target(TYPE_USE) | Đọc qua AnnotatedType nếu cần |
| Proxy interface vs target method | Metadata resolution đúng |
| Direct target/self-invocation | Không bypass enforcement ngoài dự kiến |
| Type + method policy | Precedence/merge được kiểm chứng |
| Parameter redaction | Không log raw secret |
| Missing mandatory policy | Fail-closed theo contract |
| Async handle return | Không nhầm schedule với task completion |
| Multiple aspects | Advice precedence đúng |
| Repeatable conflict | Resolver báo lỗi hoặc merge theo rule |
| Negative target | Method không được annotate không bị match nhầm |
| Class loader thay đổi | Reflection/cache không nhầm type |
| Policy reload | Một invocation có version nhất quán |

### 24.1. Test negative paths

Chỉ test một @AuditedOperation đã phát event là chưa đủ. Phải test các methods **không nên** phát event, hoặc không được phép tránh enforcement, để ngăn pointcut quá rộng/quá hẹp.

### 24.2. Fault injection

Chủ động gây lỗi trong target, trước proceed, sau proceed, logging sink, policy lookup và context cleanup. Xác nhận exception gốc còn giữ, resource context được restore và sensitive arguments không lộ ở tất cả các đường.

## 25. Những lỗi thường gặp

**Lỗi 1 — Annotation tự chạy logic.** Không, phải có consumer/weaver.

**Lỗi 2 — @Target(TYPE) có nghĩa tự annotate mọi Method.** Không; class metadata khác method metadata.

**Lỗi 3 — @Retention(RUNTIME) tự bảo đảm advice chạy.** Chỉ bảo đảm metadata runtime accessible theo API phù hợp.

**Lỗi 4 — Annotation default retention là RUNTIME.** Java default là CLASS.

**Lỗi 5 — @Inherited truyền annotation interface sang implementation.** Không theo Java reflection rules.

**Lỗi 6 — @Inherited truyền method annotation qua override.** Không.

**Lỗi 7 — @Inherited truyền parameter annotation qua override.** Không.

**Lỗi 8 — Đặt @SensitiveValue lên parameter tự che dữ liệu khi log.** Chỉ metadata, cần advice redaction.

**Lỗi 9 — PARAMETER và TYPE_USE là như nhau.** Không; type-use annotations có API metadata riêng.

**Lỗi 10 — getAnnotation luôn trả đủ repeated annotations.** Dùng getAnnotationsByType khi cần tất cả.

**Lỗi 11 — -parameters là bắt buộc để reflection đọc parameter annotations.** Không, nó chủ yếu liên quan source parameter names.

**Lỗi 12 — Annotation ở interface method luôn xuất hiện trên concrete override.** Không mặc định.

**Lỗi 13 — Một class @Audited cho biết transaction đã commit.** Không; phải phân biệt boundary và outcome.

**Lỗi 14 — Method @Retryable chứng minh idempotency.** Không.

**Lỗi 15 — Một method name là cache key đủ.** Overloads và class loaders có thể trùng tên.

**Lỗi 16 — Proxy và target có cùng Method object/type metadata.** Có thể khác nhau.

**Lỗi 17 — Runtime parameter annotation đi theo argument object.** Nó thuộc khai báo tham số, không phải object.

**Lỗi 18 — Multiple annotation order là advice precedence.** Không trừ khi ngôn ngữ/tool nói vậy.

**Lỗi 19 — Policy từ annotation luôn được tin cậy cho authorization.** Không thay authenticated actor/resource checks.

**Lỗi 20 — Reflection scan trên mỗi call không đáng quan tâm.** Có thể tốn kém ở hot paths; đo và cache hợp lý.

**Lỗi 21 — Thay config thì annotations trên class đang load tự thay.** Không.

**Lỗi 22 — Không annotation nghĩa luôn allow.** Điều này nguy hiểm cho enforcement bắt buộc.

## 26. Quy trình thiết kế annotation-driven aspect

1. **Xác định concern:** audit, trace, metrics, validation, security hay retry.
2. **Chọn vị trí đánh dấu:** TYPE cho group/default, METHOD cho operation, PARAMETER cho field-specific policy.
3. **Khai báo @Target chính xác**, không mở rộng tùy tiện.
4. **Chọn @Retention phù hợp** với compile-time weaver, class-file scanner hay runtime reflection.
5. **Quyết định @Inherited/@Repeatable** có thực sự cần không.
6. **Định nghĩa metadata semantics** thay vì chỉ đặt tên annotation.
7. **Định nghĩa chính sách hợp nhất** type/method/parameter và policy precedence.
8. **Phân biệt bắt buộc với có thể override**, đặc biệt security và redaction.
9. **Xác định điểm match**: call/execution, interface/concrete implementation, overload/bridge.
10. **Xác định cách truyền argument** theo đúng indices và data classification.
11. **Thiết kế exception/finally/async semantics** của advice.
12. **Xây metadata resolver có cache** với key và lifecycle đúng.
13. **Validate policy IDs và cấu hình** tại build/deploy boundary.
14. **Viết positive và negative tests** cho inheritance/override/interface/proxy.
15. **Kiểm tra privacy/security** ở cả success, error và logs.
16. **Đo hiệu năng** nếu advice nằm trên hot path.
17. **Tài liệu hóa limitation** của engine để tránh người dùng hiểu nhầm annotation làm magic.

## 27. Câu hỏi ôn tập có đáp án

**Câu 1.** Vì sao annotation trên class không đồng nghĩa annotation trên từng Method?

**Đáp:** Metadata class và method được khai báo ở các elements khác nhau; tool có thể tự hợp nhất theo policy nhưng Java không copy tự động.

**Câu 2.** @Target(PARAMETER) có bắt buộc validator chạy trước method không?

**Đáp:** Không; chỉ giới hạn nơi annotation được đặt.

**Câu 3.** Runtime reflection muốn đọc custom annotation thường cần retention nào?

**Đáp:** RUNTIME.

**Câu 4.** Một compile-time weaver có nhất thiết cần RUNTIME retention không?

**Đáp:** Không; nó có thể dùng source/class-file metadata tùy công cụ.

**Câu 5.** Java annotation không ghi @Retention mặc định là gì?

**Đáp:** CLASS.

**Câu 6.** @Inherited có áp cho overriding method không?

**Đáp:** Không theo Java annotation inheritance semantics.

**Câu 7.** Child extends Parent được @Inherited type annotation; getDeclaredAnnotationsByType trên Child trả inherited value không?

**Đáp:** Không; nó chỉ xét annotations khai báo trực tiếp.

**Câu 8.** Class implements annotated interface có tự inherited annotation type từ interface không?

**Đáp:** Không theo @Inherited; muốn hỗ trợ cần tự duyệt interface hoặc cơ chế riêng.

**Câu 9.** Vì sao dùng getAnnotationsByType với repeatable annotation?

**Đáp:** Để lấy đủ các annotation instances thay vì chỉ một biểu diễn.

**Câu 10.** Không biên dịch -parameters thì có mất parameter annotations runtime không?

**Đáp:** Không do flag đó; flag ảnh hưởng tên tham số, còn retention quyết định visibility của annotations.

**Câu 11.** Parameter annotation nằm trên String object truyền vào method không?

**Đáp:** Không, nó nằm trên parameter declaration.

**Câu 12.** TYPE_USE khác PARAMETER ở đâu?

**Đáp:** TYPE_USE đánh dấu một vị trí dùng kiểu; PARAMETER đánh dấu declaration của tham số.

**Câu 13.** Annotation trên interface method có chắc match concrete execution không?

**Đáp:** Không tự bảo đảm; phụ thuộc method metadata resolver và engine.

**Câu 14.** Vì sao không cache metadata theo method name đơn thuần?

**Đáp:** Overloads, declaring types và ClassLoaders có thể khác nhau.

**Câu 15.** @SensitiveValue có đủ để không lộ secret trong logs không?

**Đáp:** Không; logging advice phải chủ động redact và xử lý lỗi/diagnostics đúng.

**Câu 16.** Một method @Retryable có thể an toàn chạy lại sau external side effect không?

**Đáp:** Chỉ nếu retry policy và idempotency/compensation thật sự bảo đảm, không phải nhờ annotation.

**Câu 17.** Type @AuditRequired và method @DisableAudit xung đột, có quy tắc tự động nào?

**Đáp:** Không có rule chung; thiết kế phải xác định mandatory policy và conflict resolution.

**Câu 18.** Khi method trả CompletableFuture, after-returning đã chứng minh task success chưa?

**Đáp:** Chưa; cần quan sát async completion nếu đó là outcome cần đo.

## 28. Sơ đồ tổng kết

~~~text
                   SOURCE DECLARATIONS
                            |
           +----------------+-----------------+
           |                |                 |
           v                v                 v
       @TypeRule        @MethodRule        @ParamRule
       class/type       operation         parameter
           |                |                 |
           +----------------+-----------------+
                            |
                            v
               Compiler / class file
                            |
                    Retention / Target
                            |
                            v
              Annotation metadata resolver
              - inheritance/interface rules
              - override/bridge/proxy mapping
              - repeatable annotations
              - parameter index classification
                            |
                            v
                    Effective policy
                   validated and safe
                            |
                            v
              Pointcut + AOP advice engine
                 before / around / after
                            |
                            v
                Result / exception / audit
                 cleanup / async completion
~~~

**Kết luận:** Đánh dấu metadata ở **cấp kiểu, phương thức và tham số** giúp AOP mô tả những mối quan tâm xuyên cắt chính xác và có chủ đích. Nhưng ba vị trí này có semantics khác nhau: type-level thường đại diện scope/default, method-level chọn operation, parameter-level phân loại từng argument declaration. Cần hiểu @Target, @Retention, @Inherited, @Repeatable, reflection và khác biệt giữa interface/override/proxy trước khi xây pointcut. Annotation không tự enforce policy; **weaver/interceptor thực sự**, metadata resolution đúng, test coverage, redaction và exception semantics mới quyết định tính đúng đắn của hệ thống.

## Tài liệu tham khảo

- [Java Language Specification SE 17 — Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): khai báo annotation, meta-annotations và các quy tắc.
- [Java SE 17 — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html): TYPE/METHOD/PARAMETER/TYPE_USE.
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): retention semantics.
- [Java SE 17 — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): class annotation inheritance.
- [Java SE 17 — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): repeatable annotations.
- [Java SE 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): getAnnotationsByType và declared variants.
- [Java SE 17 — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): parameter metadata.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): pointcut/advice, type/method annotation matching trong một ngôn ngữ AOP.
