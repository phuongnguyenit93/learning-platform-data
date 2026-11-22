# Dùng annotation để thể hiện ý định áp dụng hành vi trong AOP

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một câu hỏi quan trọng là: **làm sao đánh dấu những nơi cần một hành vi cắt ngang mà không trộn toàn bộ logic logging, đo thời gian, kiểm toán, kiểm tra quyền hoặc retry vào mã nghiệp vụ?** Một giải pháp thông dụng trong Java là sử dụng **annotation** để thể hiện **ý định (intent)** tại type, method hoặc phần tử chương trình phù hợp, rồi để một cơ chế **pointcut + advice + weaving/interception** diễn giải ý định ấy và áp dụng hành vi.

Ví dụ:

~~~java
@Observed(operation = "submit")
String submit(String orderId);
~~~

Annotation **@Observed** nói rằng invocation này *được chỉ định để quan sát* với nhãn operation là submit. Tuy nhiên, annotation **không tự thực thi logging, không tạo proxy, không kiểm tra quyền và cũng không biến thành advice**. Hành vi thật chỉ xuất hiện khi có một thành phần khác **nhận diện metadata, lựa chọn đúng join point, và can thiệp vào lời gọi** theo một hợp đồng rõ ràng.

Bài thuộc chủ đề **Annotation và siêu dữ liệu**. Nội dung trình bày:
- Annotation thể hiện **điều gì**, ai chịu trách nhiệm **thực thi điều đó**, và đâu là ranh giới của hai phần.
- Cách tạo annotation trong Java, sử dụng **@Target**, **@Retention**, thuộc tính và giá trị mặc định.
- Cách AOP chọn join point dựa trên metadata ở method/type/interface, cùng các bẫy khi annotation nằm ở interface nhưng không có ở implementation.
- Phân biệt marker annotation, annotation có cấu hình, repeatable annotation, meta-annotation và quy tắc kế thừa.
- Ví dụ Java 17 hoàn chỉnh, có thể biên dịch và chạy, minh họa **annotation → interception → advice → business** và những trường hợp không được áp dụng.
- Thiết kế an toàn: thứ tự nhiều aspect, runtime proxy vs weaving, privacy, security, validation, concurrency và kiểm thử.

**Phạm vi là AOP cơ bản và nâng cao nói chung.** Ví dụ dùng **JDK dynamic proxy** như một cơ chế minh họa. Một bộ weaver khác có thể chọn **method call**, **method execution** hoặc cấu trúc khác, và không có bảo đảm mọi nền tảng dùng cùng cú pháp pointcut hoặc cách tìm annotation.

## 1. Đặt annotation vào đúng vai trò

Các khái niệm:
- **Join point:** điểm chương trình có thể can thiệp, chẳng hạn method call hoặc method execution nếu mô hình hỗ trợ.
- **Pointcut:** điều kiện chọn join point; có thể dựa trên tên, type, signature, annotation, đối tượng hoặc điều kiện runtime.
- **Advice:** hành vi thêm vào tại join point phù hợp, như before, after-returning, after-throwing hoặc around.
- **Aspect:** nhóm pointcut/advice cho một concern cắt ngang.
- **Weaving/interception:** đưa advice vào luồng thực thi bằng biên dịch, bytecode, load-time hoặc proxy/wrapper.
- **Annotation:** metadata mô tả ý định hoặc cấu hình, không tự thay đổi cách method thực thi nếu không có thành phần diễn giải.
- **Annotation-driven pointcut:** quy tắc chọn join point dựa vào annotation hiện diện ở những phần tử được định nghĩa rõ.

Sơ đồ:

~~~text
Developer marks method with @Observed
                 |
                 v
       Annotation stored as metadata
                 |
                 v
       Pointcut / metadata resolver
                 |
                 v
     Matching join point occurs?
           /           \
         No             Yes
         |               |
         v               v
   Business only     Advice wraps/calls business
                         |
                         v
                 Result / exception to caller
~~~

Điều này giúp tách biệt hai trách nhiệm:
1. **Business code** tuyên bố operation nào cần concern.
2. **Aspect infrastructure** thực thi concern tương ứng tại những join point có thể quan sát được.

### 1.1 Annotation mô tả ý định, không bảo đảm enforcement

Một developer có thể đặt **@Audited**, **@Timed**, **@Validated** hoặc **@RequiresPermission** trên method. Nếu runtime không có pointcut/advice phù hợp, không có bytecode weaving, hoặc lời gọi **bypass proxy**, metadata vẫn tồn tại mà hành vi có thể **không xảy ra**.

Với logging/metrics, thiếu advice có thể là lỗi observability. Với **authorization**, việc suy rằng “có annotation tức đã chặn quyền” là **lỗi bảo mật**. Các bất biến bắt buộc phải được bảo vệ ở ranh giới mà mọi đường cần bảo vệ đều đi qua và phải có **tests cho đường bypass**.

### 1.2 Tách metadata khai báo và metadata thực thi

~~~text
Intent (declaration):
    @Observed(operation="submit")
    @Timed(metric="order.submit")

Policy/implementation:
    Observe advice
    Timing advice
    Metadata lookup and precedence rules

Invocation:
    Caller -> interception boundary -> applicable advice -> target
~~~

Một annotation có thể khai báo “đo thời gian cho operation này”, nhưng **đo từ lúc nào tới lúc nào** là hợp đồng của advice: call entry, target execution, toàn bộ retry, hay completion của một asynchronous stage? Annotation một mình không trả lời các câu hỏi đó.

## 2. Tạo một annotation đúng mục đích trong Java

Java dùng **@interface** để định nghĩa annotation. Ví dụ tối giản:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Observed {
    String operation();
    boolean logResult() default false;
}
~~~

Đây là một **mảnh định nghĩa độc lập về cú pháp annotation**, không phải chương trình chạy có main. Hai thuộc tính có ý nghĩa:
- **operation()** là thuộc tính bắt buộc; nơi sử dụng phải cung cấp tên operation.
- **logResult()** mặc định là false, thể hiện lựa chọn thận trọng: không ghi kết quả nghiệp vụ tùy tiện, tránh lộ dữ liệu.

Áp dụng:

~~~java
@Observed(operation = "submit")
String submit(String orderId);

@Observed(operation = "lookup", logResult = false)
String lookup(String orderId);
~~~

Đây là **các chữ ký minh họa**, đặt trong interface hoặc type hợp lệ, không phải các phương thức top-level Java độc lập.

### 2.1 @Target: annotation được dùng ở đâu?

Các phần tử mục tiêu thường liên quan:
- **ElementType.TYPE:** class, interface, enum và các loại khai báo type phù hợp.
- **ElementType.METHOD:** method declaration.
- **ElementType.FIELD:** field declaration.
- **ElementType.PARAMETER:** tham số phương thức.
- **ElementType.CONSTRUCTOR:** constructor.
- **ElementType.ANNOTATION_TYPE:** một loại annotation khác.
- **ElementType.TYPE_USE:** vị trí sử dụng type, thường cần những công cụ hiểu type annotations.

Chọn **@Target(METHOD)** khi ý định gắn cho operation; **@Target(TYPE)** khi muốn đánh dấu một vùng type hoặc một class policy. Một annotation có thể nhận **nhiều target**, nhưng mở rộng target quá mức không tự làm pointcut hiểu thêm loại join point.

**Điểm cần ghi rõ:** annotation trên **field** hoặc **parameter** không tự biến thành annotation trên method. Nếu aspect cần kiểm parameter annotation, phải xác định resolver nào đọc đúng parameter metadata tại đúng join point.

### 2.2 @Retention: annotation tồn tại tới giai đoạn nào?

| Chính sách retention | Ý nghĩa chính | Lựa chọn phù hợp |
| --- | --- | --- |
| **SOURCE** | Chỉ có ở source; không giữ trong class file | Compiler/source checker |
| **CLASS** | Ghi vào class file nhưng không được Java reflection runtime phơi bày theo hợp đồng | Bytecode/static analysis và công cụ build |
| **RUNTIME** | Có ở class file và có thể truy vấn bằng reflection tại runtime | Proxy/interceptor dùng reflection |

Nếu một **JDK dynamic proxy** cần đọc annotation bằng **Method.getAnnotation**, annotation phải có **RUNTIME retention**. Nếu quy tắc chỉ được kiểm tại compile-time bằng processor, có thể dùng retention phù hợp với công cụ và mục tiêu.

**Không mặc định CLASS-retained annotation hiện diện qua reflection runtime.** Ngược lại, RUNTIME retention **không** tự kích hoạt advice: nó chỉ khiến metadata có thể được đọc.

### 2.3 Annotation element không là object cấu hình tự do

Các kiểu phần tử annotation Java được phép giới hạn: primitive, String, Class, enum, annotation và mảng một chiều của những loại phù hợp. Không khai báo một arbitrary service object hoặc mutable Map như giá trị annotation.

Một số nguyên tắc:
- Dùng **enum** cho tập giá trị hữu hạn cần kiểm.
- Tránh magic strings nếu cùng tên operation được dùng rộng rãi.
- Giữ dữ liệu cấu hình **ngắn, ổn định và phi nhạy cảm**.
- Không đưa token, password, key hoặc dữ liệu của request vào giá trị annotation.
- Xác định default rõ; ví dụ **logResult=false** giúp giảm nguy cơ vô tình log nội dung nhạy cảm.

Annotation thường mô tả **policy metadata tĩnh**. Ngữ cảnh người dùng hiện tại, trace ID hay tenant đã xác thực là **dữ liệu của invocation runtime**, không nên gói thành thuộc tính annotation cố định trong source.

## 3. Marker annotation và annotation có cấu hình

**Marker annotation** không có element:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface IdempotentOperation {}
~~~

Mục đích là đánh dấu một tính chất, ví dụ operation *được thiết kế* theo hợp đồng idempotency. Tuy nhiên, marker này **không tự biến mọi tác vụ thành idempotent**; side effects, deduplication và request key phải được xử lý thực tế.

**Annotation có cấu hình**:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Measured {
    String metric();
    boolean includeFailure() default true;
}
~~~

Nó cho phép cùng một advice nhận cấu hình khác nhau theo operation. Đổi lại, cần:
- Validate tên metric không rỗng.
- Quy định metric đo invocation hay attempt.
- Quy định thế nào là “failure”: throw đồng bộ, returned failure object, hay async completion exceptional.
- Không gắn các tham số runtime chứa identity/secret vào tên metric gây cardinality hoặc rò dữ liệu.

**Không biến annotation thành một ngôn ngữ cấu hình quá phức tạp** với hàng chục cờ tương tác. Nếu hành vi phụ thuộc nhiều điều kiện, một policy component rõ có thể dễ test và bảo trì hơn.

## 4. Resolver: annotation trên interface và trên class triển khai

Đây là một bẫy Java/AOP quan trọng.

~~~text
interface Orders {
    @Observed(operation="submit")
    String submit(String id);
}

class OrdersImpl implements Orders {
    public String submit(String id) { ... }
}
~~~

Annotation nằm trên **method khai báo trong interface**. Nó **không tự được reflection của method triển khai nhìn thấy** như một annotation trực tiếp trên implementation method.

Trong proxy dùng interface, **Method** nhận được trong **InvocationHandler** có thể biểu diễn interface method. Nếu đọc **method.getAnnotation(Observed.class)** tại đó, ta thấy annotation. Nhưng nếu chuyển sang **OrdersImpl.class.getMethod(...)** rồi đọc annotation trực tiếp, kết quả có thể là null.

Một mô hình AOP khác có thể chọn join point dựa trên **implementation method** hoặc có metadata resolver tự tìm trong interface/hierarchy. Vì vậy phải định nghĩa rõ **nguồn metadata chuẩn**:
- Annotation trên interface method có được nhận không?
- Annotation trên implementation method có được ưu tiên không?
- Nếu interface và implementation cùng annotate với cấu hình khác, giải quyết thế nào?
- Override và overload có được đọc đúng chữ ký không?
- Bridge/synthetic methods từ generics có được chuẩn hóa về method gốc không?
- Class-level annotation có áp cho toàn bộ method hay chỉ khi một rule cụ thể quy định?

Không được tự cho rằng annotation method trên interface **“được kế thừa”** theo Java reflection. Nền tảng có thể **tự triển khai quy tắc tìm metadata**, nhưng đó là một lựa chọn resolver chứ không phải Java tự sao chép annotation sang mọi method override.

### 4.1 @Inherited có giải quyết annotation method không?

**@Inherited** trong Java có hiệu lực đối với việc tìm **class-level annotation theo superclass chain** khi annotation type được đánh dấu thích hợp. Nó **không tự làm annotation method được kế thừa** sang method override và **không khiến class triển khai tự kế thừa annotation trên interface**.

Ví dụ:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}
~~~

Đây là một khai báo hợp lệ khi bổ sung import **java.lang.annotation.Inherited** và các import khác như những đoạn ví dụ trước. Một class con có thể được xem là có **Category** từ superclass khi dùng lookup API có semantics inherited, nhưng không được mở rộng suy luận đó sang method-level hoặc interface ancestry.

### 4.2 Không gộp type annotation với method annotation một cách tùy ý

Một class có **@Area("sales")**, một method có **@Observed(operation="submit")**. Ta có thể định nghĩa rule:
- **@Observed** chọn method được quan sát.
- **@Area** cung cấp nhãn bổ trợ của implementation type.
- Nếu thiếu **@Area**, sử dụng nhãn an toàn **unknown** hoặc báo lỗi cấu hình theo policy.

Nhưng nếu chỉ có **@Area**, nó không tự đồng nghĩa **mọi method của class đều phải có Observed**. Muốn hiệu lực type-wide, phải định nghĩa pointcut và precedence cụ thể.

## 5. Ví dụ Java 17 hoàn chỉnh: annotation → proxy → advice

Ví dụ này dùng **JDK dynamic proxy** làm một interceptor minh họa:
- Interface **Orders** khai báo annotation **@Observed** trên **submit** và **cancel**.
- Method **status** không có annotation, nên đi thẳng tới nghiệp vụ.
- Class **OrdersImpl** có annotation **@Area("sales")** để bổ sung một nhãn không nhạy cảm.
- Handler tìm **@Observed** trên interface Method mà proxy đưa vào.
- Handler không in return value nếu **logResult=false**.
- Khi target ném **IllegalArgumentException**, handler unwrap **InvocationTargetException** và **giữ nguyên nguyên nhân** cho caller.
- Gọi **OrdersImpl** trực tiếp sẽ **bypass proxy**, do đó annotation không được áp dụng qua handler.

Lưu toàn bộ mã thành một file **AnnotationIntentDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AnnotationIntentDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {
        String operation();
        boolean logResult() default false;
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Area {
        String value();
    }

    interface Orders {
        @Observed(operation = "submit")
        String submit(String id);

        String status();

        @Observed(operation = "cancel")
        String cancel(String id);
    }

    @Area("sales")
    static final class OrdersImpl implements Orders {
        public String submit(String id) {
            System.out.println("BUSINESS submit " + id);
            return "submitted:" + id;
        }

        public String status() {
            System.out.println("BUSINESS status");
            return "ready";
        }

        public String cancel(String id) {
            System.out.println("BUSINESS cancel " + id);
            if ("blocked".equals(id)) {
                throw new IllegalArgumentException("cannot cancel");
            }
            return "cancelled:" + id;
        }
    }

    static Object invokeTarget(Orders target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    static Orders wrap(Orders target) {
        return (Orders) Proxy.newProxyInstance(
                Orders.class.getClassLoader(),
                new Class<?>[] { Orders.class },
                (proxy, method, args) -> {
                    Observed intent = method.getAnnotation(Observed.class);
                    if (intent == null) {
                        return invokeTarget(target, method, args);
                    }

                    if (intent.operation().isBlank()) {
                        throw new IllegalArgumentException("empty operation");
                    }
                    Area area = target.getClass().getAnnotation(Area.class);
                    String areaName = area == null ? "unknown" : area.value();
                    System.out.println("ADVICE enter " + intent.operation()
                            + " area=" + areaName);
                    try {
                        Object result = invokeTarget(target, method, args);
                        System.out.println("ADVICE success "
                                + intent.operation()
                                + (intent.logResult()
                                        ? " result=" + result : ""));
                        return result;
                    } catch (RuntimeException error) {
                        System.out.println("ADVICE error " + intent.operation()
                                + " " + error.getClass().getSimpleName());
                        throw error;
                    } finally {
                        System.out.println("ADVICE finally "
                                + intent.operation());
                    }
                });
    }

    public static void main(String[] args) throws Exception {
        System.out.println("INTERFACE annotated=" +
                Orders.class.getMethod("submit", String.class)
                        .isAnnotationPresent(Observed.class));
        System.out.println("IMPLEMENTATION annotated=" +
                OrdersImpl.class.getMethod("submit", String.class)
                        .isAnnotationPresent(Observed.class));

        OrdersImpl raw = new OrdersImpl();
        Orders observed = wrap(raw);

        System.out.println("CASE annotated");
        System.out.println("RESULT " + observed.submit("A1"));

        System.out.println("CASE unannotated");
        System.out.println("RESULT " + observed.status());

        System.out.println("CASE exception");
        try {
            observed.cancel("blocked");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        System.out.println("CASE direct");
        System.out.println("RESULT " + raw.submit("B2"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac --release 17 AnnotationIntentDemo.java
java AnnotationIntentDemo
~~~

Stdout **đã được kiểm chứng khi biên dịch và chạy Java 17**:

~~~text
INTERFACE annotated=true
IMPLEMENTATION annotated=false
CASE annotated
ADVICE enter submit area=sales
BUSINESS submit A1
ADVICE success submit
ADVICE finally submit
RESULT submitted:A1
CASE unannotated
BUSINESS status
RESULT ready
CASE exception
ADVICE enter cancel area=sales
BUSINESS cancel blocked
ADVICE error cancel IllegalArgumentException
ADVICE finally cancel
CALLER cannot cancel
CASE direct
BUSINESS submit B2
RESULT submitted:B2
~~~

### 5.1 Metadata nằm ở đâu?

Hai dòng đầu là oracle về reflection:
- **INTERFACE annotated=true**: annotation **Observed** có trên method của interface.
- **IMPLEMENTATION annotated=false**: method triển khai trên **OrdersImpl** không có annotation trực tiếp ấy.

Handler cố ý đọc metadata từ **Method của proxy interface**. Nếu chuyển resolver sang method triển khai mà không có chính sách tìm interface, advice có thể **không còn chạy** dù annotation vẫn ở source.

### 5.2 Vì sao submit được quan sát?

Lời gọi đi qua **observed.submit("A1")**, tức qua proxy. Handler đọc **@Observed(operation="submit")**, in entry, gọi target và in success/finally. Caller nhận kết quả **submitted:A1**.

Vì **logResult=false**, advice không in return value. Caller vẫn nhận kết quả; không log kết quả không có nghĩa advice đã làm mất kết quả.

### 5.3 Vì sao status không có advice?

Method **status()** không được gắn **@Observed**, nên handler gọi target mà không in **ADVICE**. Đây là negative test thiết yếu: **có proxy không có nghĩa mọi method đều phải được chọn bởi pointcut annotation-driven**.

### 5.4 Vì sao lỗi vẫn được caller nhận?

Method **cancel("blocked")** là annotated và ném **IllegalArgumentException**. Java reflection bao lỗi từ target bằng **InvocationTargetException**, nên helper **invokeTarget** lấy **getCause()** để chuyển tiếp lỗi nghiệp vụ.

Advice thấy **RuntimeException**, in dòng error/finally, rồi **ném lại đúng lỗi**. Caller in **CALLER cannot cancel**. Tránh nuốt lỗi trong logging advice hoặc tự động biến mọi lỗi thành success vì có thể làm sai transaction và business contract.

### 5.5 Vì sao direct call không có advice?

Lệnh **raw.submit("B2")** gọi object triển khai trực tiếp, không qua proxy, nên không có dòng **ADVICE**. Annotation vẫn hiện diện trên interface nhưng không có handler ở đường gọi này.

Ví dụ chỉ chứng minh đặc điểm **delegation qua JDK proxy**; một cơ chế bytecode weaving trực tiếp tại method execution có thể chặn tập lời gọi khác. **Annotation đánh dấu ý định không đồng nghĩa mọi đường gọi đã được instrument.**

## 6. Annotation-driven pointcut: matching phải được thiết kế rõ

Một rule có thể nói:

~~~text
If method invocation has effective @Observed metadata:
    run observation advice
Else:
    do not run that advice
~~~

Tuy nhiên, chữ **effective metadata** cần định nghĩa. Một hệ thống có thể chọn:
- Annotation trên interface method.
- Annotation trên implementation method.
- Annotation từ superclass method khi có quy tắc kế thừa/override riêng.
- Annotation ở class/type làm quy tắc mặc định.
- Meta-annotation hoặc composed annotation.
- Kết quả kết hợp annotation type-level và method-level.

Không có thuật toán fallback duy nhất áp cho mọi AOP. Với hệ thống lớn, nên có một **metadata resolver tập trung** và các fixture cho từng tình huống, thay vì mỗi aspect tự đọc reflection theo quy tắc khác nhau.

### 6.1 Định nghĩa resolution order trước khi viết advice

Một chính sách minh họa:

~~~text
1. Method-level annotation on implementation method
2. Method-level annotation on declared interface method
3. Type-level annotation on implementation type
4. No annotation -> no advice

Conflict if multiple explicit method annotations differ:
    report configuration error, or use a documented priority
~~~

Đây **không phải quy tắc của Java reflection tự động**, cũng không phải quy tắc mặc định của mọi AOP compiler. Nó là **chính sách gợi ý** mà application có thể lựa chọn nếu cơ chế interceptor cho phép.

Nếu hai interface khai báo cùng signature với annotations khác nhau, hãy viết **test cụ thể**. Một JDK proxy có thể đưa một Method tương ứng với một interface trong những điều kiện nhất định; dựa hoàn toàn vào Method nhận được mà không có quy tắc conflict có thể tạo ambiguity. Nên tránh việc annotation security khác nhau trên các khai báo cạnh tranh.

### 6.2 Annotation trên type không tự đồng nghĩa annotation trên mọi method

Nếu class gắn **@Area("sales")**, đó là metadata type-level. Trong demo, class label chỉ được đọc **khi method đã có @Observed**. Nó không làm **status()** tự được áp dụng Observed.

Muốn class-level opt-in cho mọi method, cần nêu rõ:
- Những method nào được chọn: public only, declared/inherited, constructors?
- Method-level **opt-out** có được cho phép không?
- Khi một method override class policy khác, ưu tiên thế nào?
- Nếu target type không ở runtime vì proxy/interface dispatch, lấy type nào?
- Advice nào phải được áp dụng và theo thứ tự nào?

## 7. Annotation lặp và meta-annotation

### 7.1 @Repeatable: một phần tử có nhiều khai báo

Một method có thể cần nhiều nhãn hoặc rule độc lập. Java hỗ trợ **repeatable annotations** nếu annotation type được khai báo đúng:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Tags {
    Tag[] value();
}
~~~

Mảnh trên minh họa cơ chế khai báo. Khi sử dụng:

~~~java
@Tag("external")
@Tag("financial")
void transfer() {}
~~~

Đây là method declaration **đặt bên trong một type hợp lệ**. Một metadata resolver muốn lấy **toàn bộ tag** nên cân nhắc **getAnnotationsByType(Tag.class)** thay vì chỉ **getAnnotation(Tag.class)**, vì compiler có thể dùng container annotation cho nhiều Tag.

Repeatable **không đồng nghĩa chạy advice hai lần**. Hai tag có thể là **cấu hình bổ sung** cho một advice duy nhất; có chạy nhiều lần hay không là quy tắc của pointcut/resolver. Cần test duplicates và thứ tự nếu thứ tự có ý nghĩa.

### 7.2 Meta-annotation: annotation mô tả annotation khác

Có thể tạo một nhóm annotation chuyên biệt được đánh dấu bởi một meta-annotation. Nhưng Java không mặc định **getAnnotation(Observed.class)** sẽ tìm xuyên qua mọi custom annotation type rồi coi chúng là Observed.

Muốn có **composed semantics**, resolver phải:
1. Tìm annotation trực tiếp.
2. Kiểm meta-annotations theo một chính sách.
3. Giải quyết alias/attribute conflicts nếu cơ chế có.
4. Xử lý recursion/cycle và duplicates khi đi trên annotation graph.
5. Cache kết quả một cách có kiểm soát.

Một custom annotation đặt trên method nhưng bản thân type đó được đánh dấu bằng một marker khác **chưa đủ** để Java reflection tự gắn marker ấy lên method.

## 8. Nhiều aspect cùng dựa trên annotation

Một method có thể được đánh dấu:

~~~java
@Observed(operation = "submit")
@Measured(metric = "order.submit")
String submit(String id);
~~~

Đây là **chữ ký minh họa** với các annotation được định nghĩa trong phạm vi tương ứng; không phải toàn bộ chương trình.

Giả sử hai aspect cùng match:
- **Observation** ghi nhận outcome.
- **Timing** đo duration.

Nếu chúng là around advice lồng nhau, kết quả:

~~~text
Timing(Observe(Business))
~~~

khác với:

~~~text
Observe(Timing(Business))
~~~

ở vị trí log và phạm vi đo khi một advice short-circuit, retry hoặc bắt exception. Annotation metadata **không tự quyết định precedence**.

Một chính sách cần làm rõ:
- Aspect nào ở ngoài cùng?
- Nếu cache hit trả sớm, những concern bên trong có còn thấy call không?
- Nếu authorization từ chối trước proceed, audit nào vẫn phải ghi?
- Timing đo mỗi attempt hay request-level duration?
- Nếu hai aspect cùng log result, có rò dữ liệu hoặc double counting không?

### 8.1 Security không thể là optional concern vô tình bị bỏ

Nếu dùng **@RequiresPermission** như một annotation intent, đừng chỉ dựa vào nó để giả định việc kiểm soát quyền. Một rule bắt buộc cần:
- Kiểm đúng principal từ nguồn đáng tin, tài nguyên và hành động.
- Chặn mọi ranh giới cần bảo vệ, kể cả direct-call/self-invocation nếu applicable.
- Test success, deny, exception và short-circuit.
- Không đặt cache có thể trả private data trước một kiểm tra quyền bắt buộc.
- Không bỏ security advice theo một guard/feature flag không được phê duyệt.
- Phát hiện configuration thiếu interceptor hoặc annotation resolution sai trong CI/runtime startup khi policy yêu cầu.

**Metadata là dấu hiệu được kiểm tra; quyền là quyết định phải được thực thi.**

### 8.2 Aspect stateless và concurrency

Annotation trên method thường không thay đổi giữa các invocations, nhưng một shared aspect có thể chạy đồng thời. Không giữ **currentAnnotation, currentUser, startTime hoặc lastArgs** trong mutable field dùng chung.

Nếu cần cấu hình annotation, có thể cache **immutable resolved metadata** theo identity Method/type, với đồng bộ và class-loader lifecycle đúng. Dữ liệu riêng invocation như trace ID, arguments và timing start phải nằm trong local/context thuộc invocation ấy.

## 9. Phân biệt compile-time và runtime metadata

Một cách triển khai khác là dùng annotation **chỉ ở build**:
- Annotation processor phân tích khai báo, phát lỗi/cảnh báo hoặc sinh metadata/code.
- Static analyzer hoặc compiler kiểm rule kiến trúc.
- Compile-time weaver chọn join point và dệt advice nếu cú pháp/representation cho phép.

Với **runtime reflection**, annotation phải có retention phù hợp, và handler/resolver phải được gọi thực tế tại interception boundary.

### 9.1 Annotation processor không tự là AOP runtime weaving

Annotation processor có thể tìm **@Observed** và phát:
- ERROR nếu **operation** rỗng hoặc trùng trái policy.
- WARNING nếu annotation áp dụng cho một method không thể instrument theo cơ chế đang chọn.
- Generated metadata registry cho build nếu thiết kế cho phép.

Nhưng processor bình thường **không tự thay mọi method body thành lời gọi advice**. Nếu bài toán cần runtime interception, cần weaving/proxy/instrumentation hoặc một cách lắp ghép tương đương.

### 9.2 Retention và tập công cụ phải tương thích

| Mục tiêu | Retention thường cần | Điều phải xác minh |
| --- | --- | --- |
| Source-only compiler checker | SOURCE có thể đủ | Checker đọc source/annotations đúng pha |
| Bytecode rule/checker | CLASS hoặc RUNTIME | Classfile chứa metadata mà tool đọc được |
| Reflection interceptor | RUNTIME | getAnnotation/isAnnotationPresent thấy đúng element |
| Post-weave structural verifier | Phụ thuộc representation | Introduction đã được áp dụng trước verifier |
| Runtime advice bắt mọi execution | Không do retention quyết định một mình | Weaving coverage/pointcut và đường gọi thật |

Nếu annotation nằm ở interface method nhưng một bytecode weaver chỉ match implementation method annotations, việc đặt **RUNTIME** vẫn không tự sửa khác biệt về nguồn metadata.

## 10. Giải thích vì sao annotation-driven AOP khác decorator tự gọi

Dùng annotation trên method và một wrapper thực thi là **hai việc khác nhau**:
1. Annotation giữ metadata trong source/classfile.
2. Wrapper hoặc weaver quyết định khi nào sử dụng metadata.

Có thể không dùng annotation mà khai báo pointcut theo package/signature. Ngược lại, có thể có annotation nhưng không dùng AOP: một compiler checker hoặc serializer vẫn có thể đọc nó.

Lợi ích của annotation khi phù hợp:
- Intent ở gần nơi khai báo API.
- Review dễ thấy operation nào chịu concern.
- Không rải logging code trong nghiệp vụ.
- Dễ trích xuất metadata để kiểm các quy tắc build-time.
- Có thể định nghĩa behavior theo một policy thống nhất.

Nhược điểm:
- **Ẩn luồng điều khiển** nếu người đọc không biết có advice ngoài method.
- Metadata và interceptor có thể lệch khi refactor.
- Overlap nhiều annotation gây precedence/conflict.
- Runtime reflection hoặc weaving làm debugging phức tạp.
- Có thể tạo **ảo giác an toàn** với annotation bảo mật nếu đường gọi không đi qua interception.

Vì vậy cần tài liệu **“annotation nào → aspect nào → áp dụng ở boundary nào → điều kiện nào”** và kiểm thử cụ thể.

## 11. Thiết kế đặt annotation ở interface hay implementation?

| Vị trí | Lợi ích | Rủi ro/câu hỏi |
| --- | --- | --- |
| Interface method | Thể hiện API contract, caller dễ nhìn | Resolver ở implementation có tự tìm interface không? |
| Implementation method | Gần mã thực thi, policy theo implementation | Proxy Method từ interface có đọc được không? |
| Interface type | Metadata cho toàn bộ contract | Java @Inherited không tự áp dụng từ interface xuống class |
| Concrete class | Phù hợp type-level category/policy | Có match method riêng lẻ không? |
| Superclass method/type | Tái sử dụng metadata trong hierarchy | Override/inheritance lookup khác loại element |
| Parameter | Phù hợp validation/binding một tham số | Cần resolver theo parameter index, không tự là method advice |
| Annotation type (meta) | Nhóm policy/intent | Cần composed-annotation resolver tường minh |

**Không có một vị trí tối ưu chung.** Với AOP dựa trên interface proxy, interface method có thể tự nhiên. Với weaving theo execution của implementation method, implementation annotations có thể phù hợp hơn. Quan trọng nhất là **quy tắc nhất quán và được test**.

### 11.1 Override và overload

Nếu method **submit(String)** có annotation nhưng **submit(long)** không, một matcher dựa vào **method name** thay vì chữ ký có thể chọn nhầm. Nếu subclass override method, annotation method không tự được copy sang method override; resolver cần chính sách inheritance riêng.

Với generics, bridge/synthetic method có thể xuất hiện; một bytecode interceptor cần biết nên kiểm annotation của bridge hay method nguồn. **Không suy kết quả chỉ từ simple name**.

### 11.2 Annotation loại TYPE_USE

Java có thể gắn annotation vào **vị trí dùng type**. Nhưng một type-use annotation trên generic type argument không tự đồng nghĩa annotation trên method declaration. Một aspect chọn method-level annotation không nên âm thầm đọc mọi type-use annotation như marker của method.

## 12. Kiểm thử annotation-driven AOP

Một test suite hữu ích phải tách **metadata resolution** và **interception behavior**.

| Ca kiểm thử | Oracle mong đợi |
| --- | --- |
| Annotated interface method qua proxy | Advice được gọi đúng một lần |
| Unannotated method qua proxy | Không có advice của concern đó |
| Annotated method nhưng gọi raw target | Không có proxy advice trong mô hình delegation |
| Implementation method không annotate | Reflection trực tiếp trên implementation method không thấy annotation interface |
| Method có annotation cả interface và impl | Áp dụng conflict/precedence policy đã công bố |
| Type-level annotation, method chưa annotate | Chọn hoặc không chọn theo rule type-wide, không suy tùy tiện |
| Annotation SOURCE + runtime reflection | Không có metadata phản chiếu runtime |
| Annotation RUNTIME | Resolver thấy đúng element khi được truy vấn |
| Repeatable annotation | Đếm và xử lý đúng các phần tử qua getAnnotationsByType |
| Override/overload | Đúng signature và hierarchy policy |
| Success path | Advice giữ nguyên return value đúng hợp đồng |
| Exception path | Advice thấy lỗi; không nuốt/mất exception |
| Around short-circuit | Inner advice/target có thể không chạy |
| Two annotated aspects | Precedence/metric scope/cleanup đúng |
| Self-invocation | Biết lời gọi qua proxy hay bypass |
| Concurrency | Không lẫn context/metadata giữa hai invocations |
| Async completion | Phân biệt return stage với hoàn tất tác vụ |
| Missing interceptor | Security/required concern bị phát hiện và build/startup không âm thầm PASS |
| Logging data | Không ghi token/PII do cờ logResult sai |
| Clean vs incremental build | Metadata/registry và artifact khớp source mới |

### 12.1 Kiểm cả positive và negative

Một test chỉ xác nhận **annotated submit được log** không đủ. Cần xác nhận:
- **status không log**, vì không có annotation.
- **direct raw call không log**, vì không qua proxy.
- **cancel lỗi vẫn có finally và ném lỗi**.
- **method implementation không tự mang annotation interface**.
- **không có log return value** khi logResult=false.

Các negative controls giúp chứng minh matcher **không chọn quá rộng** và cho thấy chính xác giới hạn instrumentation.

### 12.2 Tách lỗi metadata với lỗi coverage

Khi advice không xuất hiện, kiểm tra theo thứ tự:

~~~text
Was the join point actually executed?
    |
    +-- No -> no advice event expected.
    |
    +-- Yes -> did the call cross the interception boundary?
                    |
                    +-- No -> coverage/bypass issue.
                    |
                    +-- Yes -> is annotation visible to resolver?
                                   |
                                   +-- No -> placement/retention/inheritance issue.
                                   |
                                   +-- Yes -> did pointcut select it?
                                                  |
                                                  +-- No -> matching rule issue.
                                                  +-- Yes -> advice order,
                                                             exception, short-circuit
                                                             or logging issue.
~~~

**Không đổi annotation hoặc precedence ngay lập tức** khi thiếu một dòng log. Thiếu log có thể do exporter bị lỗi, log filter, proxy bypass hoặc một around advice ngoài đã return sớm.

## 13. Quy tắc thiết kế annotation cho API lâu dài

1. **Một annotation, một ngữ nghĩa chính.** Tránh tên chung mơ hồ như @Magic.
2. **Tên phản ánh intent**, không mô tả cơ chế nội bộ có thể thay đổi.
3. **Thuộc tính tối thiểu**; default an toàn với dữ liệu nhạy cảm.
4. **Target chính xác**, không cho dùng ở những nơi resolver không hỗ trợ.
5. **Retention phù hợp** với công cụ đọc metadata.
6. **Validation sớm** cho operation rỗng, cấu hình mâu thuẫn và illegal combinations.
7. **Thứ tự/precedence rõ** khi nhiều annotations áp dụng.
8. **Tương thích refactor**: đổi method/type không âm thầm làm mất pointcut coverage.
9. **Không che giấu side effects**: annotation mang hậu quả retry/transaction/security cần docs và tests.
10. **Không coi marker là bằng chứng enforcement**: luôn kiểm con đường thật.
11. **Giới hạn logging**: không log args/results tùy ý.
12. **Quản lý version metadata** khi annotations được dùng qua module/artifact khác.
13. **Không giữ invocation context trong annotation values**: identity, trace và deadline thuộc runtime.
14. **Kiểm soát performance** nếu có reflection lookup ở hot path; cache immutable metadata đúng scope.
15. **Kiểm tra code generated/bridge methods và introductions** khi công cụ biến đổi cấu trúc.
16. **Kiểm thử advice khi exception và async**, không chỉ happy path.

## 14. Những ngộ nhận phổ biến

1. **“Đặt annotation là hành vi tự chạy.”** Không, annotation là metadata.
2. **“Retention RUNTIME có nghĩa mọi method đều được intercept.”** Không, chỉ làm annotation đọc được bằng reflection.
3. **“JDK proxy sẽ chặn raw target calls.”** Không trong mô hình delegation của demo.
4. **“Annotation method trong interface tự có trên implementation method.”** Không.
5. **“@Inherited áp dụng cho mọi override và interface.”** Không, cơ chế Java giới hạn ở class-level superclass inheritance.
6. **“Annotation type-level đương nhiên áp lên mọi method.”** Chỉ nếu pointcut/resolver quy định.
7. **“Marker @Idempotent làm side effects tự idempotent.”** Không.
8. **“@RequiresPermission đủ thay authorization thực.”** Không.
9. **“Dùng @Observed thì không thể log nhầm dữ liệu.”** Advice vẫn phải tuân thủ privacy.
10. **“Log kết quả luôn hữu ích.”** Có thể lộ bí mật hoặc PII.
11. **“Annotation processor là runtime aspect.”** Không, nó chủ yếu chạy tại compile-time.
12. **“Có hai repeatable annotations nghĩa advice chạy hai lần.”** Tùy resolver và contract.
13. **“getAnnotation tự đọc xuyên mọi meta-annotation.”** Không.
14. **“Cùng method name là cùng annotation intent.”** Overload cần phân biệt signature.
15. **“Mọi bộ weaver xử lý call/execution giống JDK proxy.”** Khác nhau về join point model.
16. **“Một class annotation thay được method-level chính xác.”** Phụ thuộc mục tiêu và quy tắc.
17. **“Một lần test thành công chứng minh security mọi đường.”** Cần negative/bypass paths.
18. **“Annotation tĩnh chứa được request context sống.”** Giá trị annotation không được thiết kế cho dữ liệu động như vậy.
19. **“Aspect dùng chung có thể giữ currentMethod/currentUser trong field.”** Dễ data race giữa các invocations.
20. **“Đổi tên annotation không ảnh hưởng build.”** Metadata resolver, generated registries và binary consumers có thể phụ thuộc API.

## 15. Bài tập tự kiểm tra

**Bài 1.** Một method có @Observed, nhưng caller gọi trực tiếp target thay vì đi qua proxy. Advice có chắc được gọi?

**Đáp:** không trong mô hình proxy delegation. Annotation vẫn tồn tại nhưng handler không được vào. Weaving trực tiếp có thể có phạm vi khác, cần kiểm công cụ cụ thể.

**Bài 2.** Vì sao RUNTIME retention cần thiết cho getAnnotation ở proxy?

**Đáp:** metadata được lưu và có thể đọc bằng reflection khi JVM chạy. SOURCE/CLASS không cung cấp hợp đồng reflection runtime tương đương.

**Bài 3.** Annotation method nằm trên interface. Java reflection trực tiếp trên implementation method có tự thấy nó?

**Đáp:** không. Resolver phải đọc đúng interface declaration hoặc áp dụng quy tắc tìm hierarchy tường minh.

**Bài 4.** @Inherited có tự truyền annotation trên interface method xuống override không?

**Đáp:** không. Nó không giải quyết phương thức/interface theo cách đó.

**Bài 5.** Nếu @Area gắn class, @Observed gắn một method, liệu status() không annotate có phải được quan sát?

**Đáp:** theo policy demo thì không. Area chỉ bổ sung nhãn cho những method đã được Observed chọn.

**Bài 6.** Trong demo, tại sao exception từ cancel không trở thành InvocationTargetException ở caller?

**Đáp:** invokeTarget lấy nguyên nhân bằng getCause() và chuyển tiếp; proxy handler không vô tình giữ lớp bọc reflection.

**Bài 7.** Nếu cần nhiều nhãn trên cùng method, nên lấy metadata bằng gì?

**Đáp:** với Java repeatable annotation, cân nhắc getAnnotationsByType đúng loại, không chỉ getAnnotation và suy số nhãn.

**Bài 8.** Nếu method được đánh dấu @RequiresPermission nhưng không có interceptor, điều gì phải được kiểm?

**Đáp:** kiểm coverage và policy bắt buộc ở build/startup hoặc runtime, cùng test direct/proxy/self-invocation. Không được tin annotation một mình bảo vệ.

**Bài 9.** Vì sao logResult=false là default có ích?

**Đáp:** kết quả có thể chứa thông tin nhạy cảm; không ghi mặc định giúp giảm nguy cơ vô tình lộ dữ liệu.

**Bài 10.** Method trả CompletionStage và advice log success ngay khi stage được trả. Có chắc async operation thành công chưa?

**Đáp:** chưa. Cần quan sát completion và lỗi bất đồng bộ bằng cơ chế thích hợp.

## 16. Kết luận

**Dùng annotation để thể hiện ý định áp dụng hành vi** là một kỹ thuật AOP hữu ích khi ta muốn đánh dấu concern ngay ở API/method nhưng giữ logic thực thi trong aspect độc lập. Để làm đúng:

1. **Định nghĩa annotation có Target/Retention/attributes phù hợp.**
2. **Quy định metadata resolver** tìm annotation ở interface, implementation, type hay hierarchy nào.
3. **Gắn pointcut/advice vào những join point thật sự có thể instrument**, thay vì suy rằng metadata tự chạy.
4. **Bảo toàn contract** về return value, exception, thứ tự nhiều aspect và request-local state.
5. **Kiểm thử cả negative paths**: unannotated method, direct target call, proxy bypass, runtime retention và exception.
6. **Với concern bắt buộc như security/audit, chứng minh enforcement ở mọi đường cần bảo vệ**, không chỉ nhìn thấy một annotation trong source.

Ghi nhớ: **annotation tuyên bố điều muốn áp dụng; pointcut và weaving/interception quyết định nơi nào có thể áp dụng; advice và policy quyết định hành vi thật.** Ba tầng này phải nhất quán thì annotation-driven AOP mới đáng tin.
