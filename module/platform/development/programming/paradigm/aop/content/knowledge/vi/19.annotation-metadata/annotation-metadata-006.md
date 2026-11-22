# Đọc giá trị cấu hình từ annotation trong advice — Aspect/AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), một **advice** có thể cần thông tin cấu hình riêng cho từng điểm can thiệp: tên nhóm nghiệp vụ để gắn vào log, mức độ theo dõi, có được ghi kết quả hay không, ngưỡng thời gian, chiến lược chọn những dữ kiện an toàn, hoặc mã chính sách kiểm toán. Nếu nhúng hết những thông tin này trong thân advice bằng các phép so sánh tên method, mã sẽ nhanh chóng khó bảo trì.

**Annotation** cho phép gắn **siêu dữ liệu có kiểu** vào một declaration. Ví dụ, một phương thức có thể mang một annotation như `@Observe(category = "inventory", logReturn = false)`. Khi một join point tương ứng được can thiệp, advice có thể **nhận annotation đã được bind bởi công cụ AOP**, hoặc **đọc annotation qua Java reflection**, rồi dùng các giá trị của nó theo một hợp đồng đã định nghĩa.

Điểm quan trọng là phải tách ba câu hỏi:

1. **Điểm nào được chọn?** Một pointcut có thể chọn những method có annotation hoặc những method execution thuộc tập mục tiêu.
2. **Giá trị annotation nào được đọc?** Annotation ở method khai báo trên interface hay method implementation, trên class, parameter, hay annotation được kế thừa? Quy tắc tìm kiếm phải rõ.
3. **Advice được phép làm gì với giá trị ấy?** Ví dụ, `logReturn=true` không được trở thành quyền ghi token bí mật, và `maxAttempts=3` không tự có nghĩa retry mọi giao dịch an toàn.

Vì vậy, **đọc cấu hình từ annotation trong advice** là cầu nối giữa **metadata của chương trình** và **hành vi cắt ngang có kiểm soát**. Bài này trình bày Aspect/AOP cơ bản và nâng cao **nói chung**. Khi đưa ra cú pháp pointcut đặc thù của một ngôn ngữ AOP, bài sẽ ghi nhãn riêng. Ví dụ đầy đủ sử dụng **Java 17 và JDK dynamic proxy** để mô phỏng cơ chế gọi advice, không nhận nó là một weaver bao phủ mọi join point.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Tạo annotation chứa các **annotation elements** có kiểu, giá trị mặc định và giới hạn vị trí áp dụng.
2. Phân biệt `@Retention(SOURCE)`, `CLASS`, `RUNTIME`; biết vì sao reflection runtime thường cần `RUNTIME`.
3. Phân biệt `@Target(METHOD)`, `TYPE`, `PARAMETER` và các nơi khác theo Java.
4. Đọc cấu hình qua `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType` hoặc thông qua annotation binding trong pointcut nếu công cụ hỗ trợ.
5. Xử lý trường hợp method khai báo trên **interface** khác method cụ thể trên **class triển khai**, đặc biệt với proxy.
6. Quy định precedence giữa annotation ở implementation/interface/type và fallback, tránh lấy nhầm giá trị.
7. Kiểm tra mặc định, giá trị không hợp lệ, annotation lặp, meta-annotation, kế thừa và reflection trên phương thức generic/bridge.
8. Đọc cấu hình một cách **an toàn**: không lộ dữ liệu nhạy cảm, không để flag tùy tiện vô hiệu chính sách bắt buộc.
9. Nhận diện giới hạn của **compile-time/weaving**, proxy, module, class loader, self-invocation và caching.
10. Viết, chạy và phân tích một chương trình Java 17 minh họa đọc annotation trong advice, bảo toàn kết quả và lỗi.
11. Thiết kế kiểm thử cho điểm được annotate, không được annotate, thiếu runtime retention, override/fallback, lỗi và concurrency.

## 2. Annotation là gì, và không phải là gì?

Trong Java, một annotation type được khai báo bằng `@interface` và cung cấp **các phần tử dữ liệu có kiểu**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface OperationTag {
    String category() default "general";
    boolean logReturn() default false;
    int slowThresholdMs() default 100;
    String[] tags() default {};
}
```

Đây là một **đoạn khai báo hợp lệ** nhưng chưa phải một chương trình độc lập có `main`. Các biểu thức như `category()` và `logReturn()` là **annotation elements**; khi đọc một instance annotation, Java cung cấp các phương thức này để lấy giá trị. Chúng không phải những instance fields mutable được sửa tùy ý sau khi đọc.

Dùng trên một method:

```java
@OperationTag(
    category = "inventory",
    logReturn = false,
    slowThresholdMs = 250,
    tags = {"read", "internal"}
)
public String load(String sku) {
    return "item:" + sku;
}
```

Đây là **snippet minh họa method**, không tự biên dịch như một file độc lập nếu thiếu class chứa nó.

Điều annotation **không tự thực hiện**:

- Không tự chạy advice chỉ vì nó tồn tại.
- Không tự tạo pointcut, weaving hoặc proxy.
- Không tự bảo đảm authorization, logging, transaction hay retry.
- Không tự thay đổi mỗi khi file cấu hình ngoài ứng dụng đổi: giá trị annotation thường là **metadata đi cùng mã đã biên dịch**.
- Không tự “lan” từ interface method sang implementation method theo quy tắc mà người viết mong muốn.
- Không tự thẩm định giá trị an toàn; `slowThresholdMs = -10` vẫn cần được phát hiện nếu contract không cho phép số âm.

**Annotation là một nguồn metadata; logic AOP quyết định cách chọn, đọc, kiểm tra và sử dụng nguồn ấy.**

## 3. Những phần tử và giá trị được phép trong annotation

Annotation elements trong Java được phép có những kiểu phù hợp như các primitive, `String`, `Class`, enum, annotation type khác và mảng một chiều của những kiểu được phép. Không khai báo tùy ý một `List<String>` làm annotation element rồi mặc định compiler chấp nhận.

Ví dụ:

```java
enum Sensitivity { PUBLIC, INTERNAL, RESTRICTED }

@interface RecordPolicy {
    String category();
    Sensitivity sensitivity() default Sensitivity.INTERNAL;
    Class<?> serializer() default Object.class;
    String[] labels() default {};
}
```

Đây là các khai báo minh họa, không có `main`. Nếu một element **không có default**, nơi dùng annotation phải cung cấp nó theo luật Java. Nếu có default, advice đọc giá trị đã được xác định theo annotation contract mà không cần tự điền bằng một câu lệnh if cho từng nơi sử dụng.

### 3.1. Mặc định không có nghĩa “không tồn tại”

Với:

```java
@interface TraceRule {
    String group() default "general";
    boolean revealResult() default false;
}
```

Khai báo `@TraceRule` và `@TraceRule(group = "general", revealResult = false)` có thể cho advice **cùng các giá trị phần tử**. Một advice dùng `rule.group()` sẽ thấy `"general"` trong cả hai trường hợp.

Nếu thiết kế bắt buộc phân biệt **“caller không đặt”** với **“caller cố ý đặt bằng default”**, annotation element mặc định không tự mang cờ đó. Cần thiết kế contract khác, chẳng hạn sentinel có ý nghĩa, tách annotation hoặc dùng cấu hình tường minh; không suy nguồn gốc giá trị từ dữ liệu runtime thông thường.

### 3.2. Giá trị cấu hình phải được kiểm tra

Dù compiler kiểm tra kiểu, nó không tự biết `slowThresholdMs=-1` có vô nghĩa với nghiệp vụ không. Hãy đặt ràng buộc:

- `category` không được rỗng nếu là khóa metric.
- `slowThresholdMs` không âm và không vượt ngân sách hợp lý.
- `logReturn` chỉ áp với những kết quả đã được phân loại an toàn.
- `tags` nên giới hạn số lượng/độ dài và tránh cardinality bùng nổ.
- `Class<?>` chỉ được dùng làm strategy type sau khi kiểm tra tương thích và quyền khởi tạo.

Không dùng annotation làm kênh nạp code chưa tin cậy chỉ vì nó đã được biên dịch.

## 4. `@Retention` quyết định khả năng đọc runtime

Với **advice đọc cấu hình qua Java Reflection tại runtime**, annotation type thường phải khai báo `@Retention(RetentionPolicy.RUNTIME)`. Nếu bỏ `@Retention`, giá trị mặc định là `CLASS`; `SOURCE` cũng không được reflection cung cấp. Điều này không phủ nhận khả năng một compiler/binary weaver đọc `SOURCE` hoặc `CLASS` metadata ở **giai đoạn khác**.

Ví dụ quan sát cần một annotation instance để đọc các element cấu hình:

```java
Observe mark = method.getAnnotation(Observe.class);
```

Giá trị `mark` vẫn có thể là `null` dù annotation đã xuất hiện trong source nếu resolver đọc **sai declaration**. Cần xác định rõ method thuộc interface hay implementation. `@Target(METHOD)` chỉ cho phép gắn trên method declaration; `@Target(TYPE)`, `PARAMETER` và `TYPE_USE` diễn đạt vị trí khác, cần API đọc tương ứng (`Class.getAnnotation`, `getParameterAnnotations`, `AnnotatedType`).

**Điểm riêng của bài đọc cấu hình:** trước khi gọi các element như `mark.operation()`, phải biết annotation được resolve theo chính sách precedence nào; nếu không tìm thấy, chọn rõ default/failure policy thay vì âm thầm áp một rule tùy ý. Nếu advice bắt buộc đối với an ninh hoặc audit, không coi `null` là lý do tự động bỏ qua kiểm soát. `@Retention` và `@Target` nên được khai báo tường minh để caller biết nơi nào có thể cung cấp cấu hình hợp lệ.

## 5. Hai cách đưa annotation vào advice

### 5.1. Binding ngay trong pointcut khi công nghệ hỗ trợ

Một số ngôn ngữ AOP cho phép pointcut kiểm tra một annotation hiện diện tại join point và **bind** annotation instance cho tham số của advice. Pseudocode:

```text
pointcut: methodExecutionHasAnnotation(Observe config)

before(config):
    validate(config)
    record(config.category())
```

Đây là **giả mã có chủ đích**, không phải API chung của Java hoặc mọi AOP. Trong một công cụ có khả năng annotation pointcut và binding, cách này có thể tránh việc advice tự đoán method nào mang annotation. Tuy nhiên vẫn phải hiểu **annotation được xét ở declaration nào**, khả năng binding class/method/parameter và các giới hạn của weaving.

Một ví dụ **cú pháp riêng cho AspectJ**, cần các declarations/type phù hợp và AOP compiler/weaver, không chạy bằng `javac` thông thường:

```java
// Observe là annotation type có @Retention(RUNTIME) và @Target(METHOD).
public aspect ObservationAspect {
    before(Observe cfg):
        execution(* *(..)) && @annotation(cfg) {
        System.out.println("Category = " + cfg.category());
    }
}
```

Đây là minh họa ngữ nghĩa **binding annotation ở join point execution**. Không suy rằng một annotation chỉ đặt trên interface method chắc chắn được binding khi weaver đang chọn **implementation execution**. Quy tắc declaration của pointcut, dispatch và weaving thực tế quyết định kết quả.

### 5.2. Đọc qua reflection trong advice/interceptor

Khi cơ chế AOP cung cấp `Method` hoặc dữ liệu join point, advice có thể gọi reflection:

```java
Observe config = method.getAnnotation(Observe.class);
if (config != null) {
    String category = config.category();
    boolean logReturn = config.logReturn();
}
```

Đây là **snippet minh họa**, giả định có biến `method` và annotation `Observe`. Ưu điểm là dùng các API Java quen thuộc, nhưng phải xác định:

- `method` có phải method trên interface proxy hay method concrete class?
- Metadata có retention RUNTIME không?
- Implementation override có khai báo annotation khác không?
- Annotation được đặt ở class, method hay parameter?
- Method là synthetic/bridge method hay là method được khai báo trong superclass?
- Access tới class/method có bị module/classloader giới hạn không?
- Cơ chế AOP có thực sự đưa lời gọi đi qua advice này không?

**Đọc một `Method` đúng tên không luôn đủ.** Một method tương ứng ở interface và một method ở implementation là **hai declaration khác nhau**, nên có thể mang metadata khác.

## 6. Lấy đúng method: interface và implementation

Với JDK dynamic proxy, `InvocationHandler.invoke(proxy, method, args)` thường nhận một `Method` thuộc **giao diện mà proxy cung cấp**. Nếu chỉ gọi `method.getAnnotation`, một annotation gắn **chỉ trên implementation** có thể không thấy.

Ví dụ:

```java
interface Store {
    void save(String id);
}

class StoreImpl implements Store {
    @Observe(category = "database-write")
    public void save(String id) {}
}
```

Đoạn này minh họa một cặp declaration; cần định nghĩa `Observe`. Trong `InvocationHandler`, `method` tương ứng `Store.save` có thể không mang annotation, trong khi `StoreImpl.save` mang nó.

Một chiến lược đơn giản cho **public method có cùng parameter types**:

```java
Method implementationMethod =
    target.getClass().getMethod(
        interfaceMethod.getName(),
        interfaceMethod.getParameterTypes());

Observe config = implementationMethod.getAnnotation(Observe.class);
if (config == null) {
    config = interfaceMethod.getAnnotation(Observe.class);
}
```

Đây là snippet, giả định có `target`, `interfaceMethod`, kiểu `Observe` và các import reflection. Nó thể hiện **quy tắc ưu tiên do ứng dụng thiết kế**: annotation ở implementation được ưu tiên, nếu vắng thì lấy annotation từ interface. Đây **không phải quy tắc mặc định bắt buộc** của mọi AOP.

### 6.1. Vì sao không chỉ dùng tên method?

Nếu target có overload:

```java
void process(String id);
void process(String id, boolean dryRun);
```

thì `getMethod("process", parameterTypes)` cần danh sách parameter types chính xác. Dùng chỉ `getName()` hoặc tìm method đầu tiên bằng stream có thể đọc nhầm annotation của overload khác.

Các vấn đề nâng cao còn có **varargs**, generic erasure, covariant return, bridge/synthetic methods và method được thừa hưởng. Java reflection trả `Method` của declaration có thể khác nơi cấu hình thực sự được định nghĩa; cần hợp đồng lookup cụ thể.

### 6.2. Interface annotation không tự kế thừa sang implementation method

Trong Java thông thường, annotation trên method khai báo của interface **không tự xuất hiện** khi hỏi:

```java
implementationMethod.getAnnotation(Observe.class)
```

Nếu implementation không tự khai báo annotation ấy, kết quả có thể là `null`. Vì vậy nếu muốn interface đóng vai trò fallback, cần **thực hiện lookup rõ ràng** hoặc dùng khả năng metadata resolution của chính công cụ AOP nếu có.

### 6.3. Quy tắc khi có nhiều interface

Một class có thể triển khai hai interfaces đều chứa method cùng chữ ký nhưng annotation khác nhau. Một JDK proxy có thể nhận `Method` tương ứng một interface theo quy tắc duplicate methods của proxy; nó không tự biết caller đã cast proxy sang interface nào.

Nếu hai annotations trái nghĩa, không nên chọn tùy tiện “interface xuất hiện đầu tiên”. Phải quyết định **một contract thống nhất cho method**, hoặc phát hiện conflict và từ chối cấu hình; với chính sách bảo mật bắt buộc, không được suy ra ALLOW từ một annotation vô tình thuận tiện hơn.

## 7. Thứ tự ưu tiên metadata phải thành hợp đồng

Có nhiều vị trí khả dĩ:

1. Annotation gắn trực tiếp vào **implementation method**.
2. Annotation gắn trực tiếp vào **interface method**.
3. Annotation trên **class implementation**.
4. Annotation trên **interface type**.
5. Annotation từ **superclass hoặc overridden method**.
6. Annotation ở **package/module** hoặc nguồn cấu hình ngoài.
7. Giá trị mặc định của annotation hoặc mặc định của policy.

Không có một hệ thống tự động duy nhất cho tất cả. **Hãy công bố thứ tự ưu tiên** và test từng trường hợp.

Ví dụ một quy ước cho advice quan sát:

```text
implementation method annotation
  -> matching interface method annotation
  -> implementation class default annotation
  -> local observer default
```

Nếu cho phép “implementation override interface”, cần xem chính sách ấy có hợp lý trong tổ chức: nếu interface annotation mang một **yêu cầu bắt buộc**, cho phép implementation tắt bằng `enabled=false` có thể phá bất biến. Quy tắc cho **telemetry tùy chọn** có thể khác hoàn toàn quy tắc cho **audit/authorization bắt buộc**.

### 7.1. Tách “không có annotation” và “cấu hình tắt”

Hai trường hợp:

- Method **không gắn annotation**.
- Method có `@Observe(enabled = false)`.

Chúng không nhất thiết giống nhau. Trường hợp đầu có thể là **không thuộc pointcut**; trường hợp hai có thể là **thuộc phạm vi chính sách nhưng chủ động từ chối observation**. Với bảo mật/audit, việc tắt phải được policy owner chấp thuận; không để một annotation do module không tin cậy tự tuyên bố không cần guard.

### 7.2. Tính nhất quán giữa pointcut và lookup

Một lỗi khó phát hiện: pointcut chỉ khớp annotation **trên interface** nhưng advice lại chỉ đọc **implementation method**. Lúc đó có thể:

- Pointcut được chọn nhưng advice thấy `null`.
- Advice mặc định sai và bỏ qua cấu hình.
- Hoặc điểm thực tế không được chọn vì công cụ xét một declaration khác.

Định nghĩa rõ **quy tắc nào chọn join point** và **quy tắc nào lấy annotation instance**, rồi kiểm tra hai bước khớp nhau.

## 8. Ví dụ Java 17 runnable: advice đọc cấu hình runtime

Chương trình sau minh họa **trong cùng một ví dụ**:

- Một annotation `@Observe` có `RUNTIME` retention, chỉ gắn lên method, chứa `category`, `logReturn` và `tags`.
- Một method `fetch` được annotate **chỉ ở interface**; advice đọc được nhờ fallback.
- Một method `save` có annotation ở cả interface và implementation; **implementation được ưu tiên** theo quy tắc tự thiết kế.
- Một method `reject` có annotation **chỉ ở implementation**, target ném lỗi; advice báo lỗi rồi ném lại nguyên gốc.
- Một method `plain` không gắn annotation nên handler chỉ gọi target, không phát thông báo advice.
- Kết quả an toàn `saved:B2` mới được in khi `logReturn=true`; không in kết quả của `fetch` trong advice.
- Lời gọi qua **JDK dynamic proxy** được can thiệp; ví dụ không weave trực tiếp class target.

**Lưu ý:** chương trình dùng `System.out` để có stdout xác định. Việc log kết quả dựa vào một dữ liệu mô phỏng không nhạy cảm; trong hệ thật phải kiểm tra classification/redaction/retention trước khi cho phép in result. Đây không phải ví dụ bảo mật hoặc kiểm toán bền vững.

Tạo file `AnnotationConfigAdviceDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class AnnotationConfigAdviceDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Observe {
        String category() default "general";
        boolean logReturn() default false;
        String[] tags() default {};
    }

    public interface Gateway {
        @Observe(category = "read", tags = {"public", "safe"})
        String fetch(String id);

        @Observe(category = "interface-write")
        String save(String id);

        String reject(String id);
        String plain();
    }

    public static final class GatewayImpl implements Gateway {
        @Override
        public String fetch(String id) {
            System.out.println("TARGET fetch " + id);
            return "value:" + id;
        }

        @Override
        @Observe(category = "impl-write",
                 logReturn = true, tags = {"mutation"})
        public String save(String id) {
            System.out.println("TARGET save " + id);
            return "saved:" + id;
        }

        @Override
        @Observe(category = "reject")
        public String reject(String id) {
            System.out.println("TARGET reject " + id);
            throw new IllegalArgumentException("blocked:" + id);
        }

        @Override
        public String plain() {
            System.out.println("TARGET plain");
            return "no-advice";
        }
    }

    static Observe configuration(
            Method interfaceMethod, Class<?> targetClass) {
        final Method implementation;
        try {
            implementation = targetClass.getMethod(
                    interfaceMethod.getName(),
                    interfaceMethod.getParameterTypes());
        } catch (NoSuchMethodException error) {
            throw new IllegalStateException(
                    "implementation method not found", error);
        }

        Observe local = implementation.getAnnotation(Observe.class);
        return local != null
                ? local
                : interfaceMethod.getAnnotation(Observe.class);
    }

    static Object invokeTarget(
            Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Gateway wrap(Gateway target) {
        return (Gateway) Proxy.newProxyInstance(
                Gateway.class.getClassLoader(),
                new Class<?>[] { Gateway.class },
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return invokeTarget(method, target, args);
                    }

                    Observe cfg = configuration(method, target.getClass());
                    if (cfg == null) {
                        return invokeTarget(method, target, args);
                    }

                    String category = cfg.category();
                    if (category.isBlank()) {
                        throw new IllegalStateException("blank category");
                    }

                    System.out.println("ADVICE before " + category
                            + " tags=" + Arrays.toString(cfg.tags()));

                    try {
                        Object result = invokeTarget(method, target, args);
                        if (cfg.logReturn()) {
                            System.out.println("ADVICE return " + result);
                        }
                        return result;
                    } catch (Throwable error) {
                        System.out.println("ADVICE throw "
                                + error.getClass().getSimpleName());
                        throw error;
                    } finally {
                        System.out.println("ADVICE finally " + category);
                    }
                });
    }

    public static void main(String[] args) {
        Gateway port = wrap(new GatewayImpl());

        System.out.println("CALL " + port.fetch("A1"));
        System.out.println("CALL " + port.save("B2"));

        try {
            port.reject("C3");
        } catch (IllegalArgumentException error) {
            System.out.println("CALL_ERROR " + error.getMessage());
        }

        System.out.println("CALL " + port.plain());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AnnotationConfigAdviceDemo.java
java AnnotationConfigAdviceDemo
```

**Stdout dự kiến chính xác**:

```text
ADVICE before read tags=[public, safe]
TARGET fetch A1
ADVICE finally read
CALL value:A1
ADVICE before impl-write tags=[mutation]
TARGET save B2
ADVICE return saved:B2
ADVICE finally impl-write
CALL saved:B2
ADVICE before reject tags=[]
TARGET reject C3
ADVICE throw IllegalArgumentException
ADVICE finally reject
CALL_ERROR blocked:C3
TARGET plain
CALL no-advice
```

### 8.1. Vì sao `fetch` đọc được annotation?

`Gateway.fetch` có `@Observe(category="read", ...)`; implementation `GatewayImpl.fetch` không có annotation. Trong handler, `configuration` tìm method của target, thử lấy annotation ở implementation (nhận null), sau đó **fallback về method interface** do proxy cung cấp.

Vì vậy `ADVICE before read ...` xuất hiện. `logReturn` lấy default `false`, nên không có dòng `ADVICE return value:A1`, dù caller vẫn nhận `value:A1`.

### 8.2. Vì sao `save` dùng `impl-write` thay `interface-write`?

Cả interface và implementation đều gắn `@Observe`. Hàm `configuration` đặt **ưu tiên implementation**; khi annotation địa phương khác null, nó được trả ngay.

Do đó nhãn là `impl-write` và `logReturn=true`, khiến advice in kết quả `saved:B2`. Đây là **quy tắc do ví dụ thiết kế**, không phải một quy tắc được mọi framework AOP áp dụng.

### 8.3. Vì sao `reject` vẫn chạy advice và trả lỗi gốc?

`Gateway.reject` không annotate, nhưng `GatewayImpl.reject` có `@Observe(category="reject")`. Hàm lookup tìm được annotation trên implementation nên advice được áp.

Target in `TARGET reject C3` rồi ném `IllegalArgumentException("blocked:C3")`. `Method.invoke` bọc ngoại lệ target bằng `InvocationTargetException`; `invokeTarget` lấy `getCause()`, advice ghi loại lỗi rồi **ném lại chính lỗi đó**. Caller bắt đúng `IllegalArgumentException`. `finally` vẫn chạy trên đường throw.

### 8.4. Vì sao `plain` không có dòng ADVICE?

Method này không có annotation ở interface lẫn implementation. `configuration` trả null, handler chuyển thẳng tới target. Do vậy `TARGET plain` xuất hiện trước `CALL no-advice`, không có advice messages.

### 8.5. Những giới hạn phải nhận ra

- Handler dùng JDK dynamic proxy; lời gọi **trực tiếp** `new GatewayImpl().save(...)` không qua proxy nên không chạy advice.
- Handler minh họa method public trên một interface. Nó không tự chặn field access, constructor, private method hoặc self-invocation qua target.
- Việc lookup interface bằng `Method` proxy chỉ phục vụ trường hợp đơn giản, không giải quyết xung đột nhiều interfaces cùng method signature.
- `targetClass.getMethod` tìm public method; nếu code thật có bridge methods, generic signatures, interface defaults hoặc nhiều overload, cần resolver và tests chính xác hơn.
- `configuration` phản chiếu mỗi invocation cho dễ hiểu; ứng dụng tải lớn có thể cache metadata an toàn theo method và class với cấu trúc concurrency/loader lifecycle phù hợp.
- Ví dụ không có async, transaction, retry, audit bền vững hoặc logger có thể lỗi. Những chính sách ấy không xuất hiện tự động từ `@Observe`.
- Annotation `logReturn=true` **không phải quyền log mọi payload**. Dữ liệu nhạy cảm và chính sách privacy phải được kiểm tra độc lập.
- `category.isBlank()` chỉ kiểm tra một ràng buộc đơn giản; production nên kiểm tra cả độ dài, allowed values và metadata khác.
- Handler không hỗ trợ nhiều chính sách cùng lúc, pointcut precedence hoặc selector khác annotation; các mối quan hệ đó thuộc thiết kế rộng hơn.

## 9. `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`

Các API đọc metadata không hoàn toàn cùng ý nghĩa.

| API | Ý nghĩa cần lưu ý |
| --- | --- |
| `element.getAnnotation(A.class)` | Lấy annotation A theo quy tắc Java của phần tử được phản chiếu, hoặc null |
| `element.getDeclaredAnnotation(A.class)` | Xét annotation **trực tiếp** trên declaration theo quy tắc API |
| `element.getAnnotations()` | Liệt kê annotations hiện diện theo semantics của element |
| `element.getDeclaredAnnotations()` | Chỉ annotations khai báo trực tiếp |
| `element.getAnnotationsByType(A.class)` | Hữu ích cho **repeatable annotations**, xét container và một số quy tắc inheritance |
| `method.getParameterAnnotations()` | Annotation trên từng parameter declaration |
| `method.getAnnotatedReturnType()` | Type-use annotations trên kiểu trả về, nếu có |

### 9.1. `@Inherited` không làm method annotation tự thừa kế

`@Inherited` trong Java áp cho annotation type dùng trên **classes** theo semantics kế thừa annotation của class/subclass. Nó **không khiến annotation gắn trên interface method hoặc overridden method tự xuất hiện** khi đọc implementation method.

Ví dụ một class con kế thừa implementation của một method không đồng nghĩa annotation của một method override được “chuyển” theo cách tùy ý. Chỉ dựa trên `@Inherited` mà bỏ lookup interface/supermethod sẽ tạo lỗi cấu hình.

Cũng không mặc định annotation trên interface type được coi là annotation inherited trên implementing class: phải xem quy tắc `AnnotatedElement` và chủ động thiết kế fallback nếu cần.

### 9.2. Repeatable annotations

Một annotation đánh dấu `@Repeatable(Container.class)` có thể xuất hiện nhiều lần ở cùng nơi nếu khai báo container hợp lệ. Khi muốn đọc **tất cả bản cấu hình**, `getAnnotationsByType(A.class)` là API phù hợp hơn so với `getAnnotation(A.class)` đơn lẻ.

Ví dụ về metadata mong muốn:

```java
@Tag("finance")
@Tag("critical")
void process() {}
```

Đây là snippet **chỉ minh họa cách sử dụng**, chưa định nghĩa `@Tag`, container hoặc class, nên không chạy độc lập. Phải xác định **thứ tự và quy tắc hợp nhất** nhiều cấu hình: có cộng dồn hay annotation thứ hai đè thứ nhất? Nếu hai `@RetryPolicy` cùng có max attempts khác nhau, không nên chọn một cách ngẫu nhiên.

### 9.3. Meta-annotations không được quét đệ quy mặc định

Một annotation `@CriticalOperation` có thể tự mang `@Observe(category="critical")` nếu annotation target cho phép áp vào annotation type. Nhưng:

```java
method.getAnnotation(Observe.class)
```

không tự đảm bảo sẽ **truy vết annotation nằm trên annotation type khác** để tìm Observe trong mọi trường hợp. Cần code tìm kiếm meta-annotation có quy tắc rõ hoặc sử dụng khả năng của một thư viện/công cụ nếu đã được xác minh.

Các câu hỏi cần định nghĩa: quét mấy tầng, xử lý vòng meta-annotations ra sao, giá trị annotation nào được ưu tiên, và có hỗ trợ alias thuộc tính không? Không có một cơ chế alias/merge chung do Java reflection tự tạo cho mọi annotation.

## 10. Cấu hình kiểu hợp đồng hay chỉ là gợi ý?

Không phải mọi giá trị metadata có cùng mức tin cậy.

**Gợi ý quan sát:** `category="inventory"`, `samplePercent=20`, `logReturn=false`. Chúng có thể quyết định mức quan sát **nếu** không bỏ qua các nghĩa vụ bắt buộc.

**Ràng buộc bắt buộc:** `requiresAuthorization=true`, `auditRequired=true` hoặc `maxRetries` với một operation nhạy cảm. Nếu annotation được đặt/sửa bởi thành phần không nắm quyền chính sách, không được mặc định nó có thể tắt một guard có tính bắt buộc.

### 10.1. Không đặt quyền truy cập hoàn toàn trong một Boolean annotation

Nếu một method tự khai báo `@ProtectedOperation(enabled=false)`, điều đó không chứng minh thao tác được phép chạy mà không kiểm tra quyền. Cần xác định **nguồn tin cậy của chính sách**, ranh giới thực thi bắt buộc và cách xử lý khi annotation thiếu hoặc sai.

Với guard, “annotation không có” có thể phải **fail closed** chứ không phải “bỏ qua aspect” nếu ranh giới đó cần luôn được kiểm soát.

### 10.2. Cấu hình log cũng có thể gây rò dữ liệu

`@Observe(logReturn=true)` nghe tiện, nhưng một method có thể trả thông tin sức khỏe, credentials, tài khoản hoặc object chứa field nhạy cảm. Gọi `toString()` bừa bãi có thể lộ dữ liệu hoặc ném lỗi.

Nên thiết kế:

- Allowlist của những loại result được phép ghi.
- Mask/redact theo schema và quyền của caller/sink.
- Giới hạn độ dài, tần suất, cardinality, retention.
- Không ghi trực tiếp `Throwable.getMessage()` nếu chứa payload nhạy cảm.
- Không in toàn bộ `args` chỉ vì annotation bật một flag.
- Quy tắc logger lỗi để không làm sai return/throw của target khi chỉ là observer tùy chọn.

Trong ví dụ Java, chuỗi `saved:B2` là dữ liệu học tập được giả định an toàn; không phải lời khuyên log kết quả bất kỳ.

## 11. Validation: thời điểm nào và khi sai phải làm gì?

Có ba chiến lược phổ biến:

1. **Compile-time/build validation:** công cụ kiểm tra annotation đúng nơi và giá trị thỏa ràng buộc có thể biết sớm.
2. **Startup validation:** quét tập join point được quản lý, phát hiện cấu hình rỗng/trái ngữ nghĩa trước khi hệ phục vụ.
3. **Per-invocation validation:** kiểm tra ở thời điểm advice chạy; hữu ích khi target/metadata động, nhưng có chi phí runtime và lỗi đến muộn.

Không phải hệ thống nào cũng có khả năng quét toàn bộ classes khi startup, nhất là với dynamic proxies/module/plugin loaders. Nên kết hợp **chứng cứ có thật** thay vì tuyên bố đã bao phủ hết hệ chỉ nhờ một bước scan.

### 11.1. Quy tắc lỗi phải tùy chính sách

Nếu annotation telemetry có `category=""`:

- Có thể từ chối khởi động module nếu cấu hình invalid là lỗi phát triển.
- Hoặc phát tín hiệu degraded và không ghi sample **nếu** telemetry thật sự tùy chọn và hợp đồng cho phép.

Nếu annotation kiểm soát quyền bắt buộc không hợp lệ:

- Không được tự rơi về `ALLOW`.
- Cần từ chối thao tác, báo cấu hình lỗi và sửa theo quy trình đáng tin.

**Không dùng một catch rộng nuốt `Throwable` và tiếp tục target cho mọi annotation**, vì nó có thể che chính sách cần fail closed.

### 11.2. Xử lý default khi tiến hóa phiên bản annotation

Khi thêm element mới vào annotation dùng ở nhiều module, có default hợp lệ có thể hỗ trợ tương thích. Nhưng đổi ý nghĩa default có thể thay hành vi của **tất cả methods đã annotate**.

Nếu element mới **không có default**, những declaration cũ có thể không thỏa contract khi biên dịch mới. Với class files biên dịch từ các phiên bản annotation khác nhau, có thể gặp lỗi metadata/runtime như `IncompleteAnnotationException` khi đọc phần tử còn thiếu trong một số điều kiện.

Cần kiểm tra binary/source compatibility và chạy đúng artifact triển khai, không chỉ unit test với tất cả classes được rebuild đồng thời.

## 12. Annotation và tham số binding của advice

Một advice thường cần **hai nhóm dữ liệu**:

- **Metadata**: annotation instance chứa category, threshold, mode, tags.
- **Invocation data**: method, target, args, kiểu return, exception, thời gian bắt đầu, context của lời gọi.

Đừng nhầm `@Observe(category="A")` với argument `category` do caller truyền khi chạy. Annotation là **metadata declaration**; args thuộc **lượt gọi runtime**.

Pseudocode:

```text
advice around join point:
    config = resolveAnnotation(joinPoint)
    validate(config)
    started = monotonicClock()
    try:
        result = proceed exactly once
        if config permits safe result recording:
            record(result)
        return result
    catch original error:
        recordSafeFailure(error)
        rethrow original error
    finally:
        recordDuration(config, monotonicClock() - started)
```

Đây là **giả mã**; không có API chung tên `proceed` cho mọi công nghệ. Chỉ xét điểm advice thực sự được áp.

### 12.1. Threshold và đồng hồ

Nếu annotation có `slowThresholdMs=250`, đo elapsed bằng nguồn **monotonic** phù hợp như `System.nanoTime()` để so khoảng thời lượng, thay vì lấy chênh lệch wall-clock có thể thay đổi do chỉnh thời gian.

Chú ý overflow/đổi đơn vị, và chỉ kết luận “slow” nếu policy đã định nghĩa đo **method execution đồng bộ** hay **completion của future**. Với method trả `CompletableFuture`, return future không đồng nghĩa công việc đã xong.

### 12.2. Exception contract

Một aspect quan sát không nên dùng giá trị annotation để tùy tiện chuyển lỗi nghiệp vụ thành `null`. Nếu target ném lỗi, advice nên bảo toàn exception theo hợp đồng. Nếu logging backend ném lỗi, xử lý **riêng lỗi logging** theo chính sách của observer, không catch toàn bộ `proceed` rồi tuyên bố target thành công.

### 12.3. Thứ tự nhiều advice

Một method có thể đồng thời mang annotation đo thời gian và annotation yêu cầu kiểm toán. Thứ tự ảnh hưởng:

- Thời lượng đo toàn chuỗi hay chỉ target?
- Audit ghi attempt, return bình thường hay committed effect?
- Retry có gọi target nhiều lần?
- Authorization có chạy trước cache-hit short circuit?
- Lỗi exporter có che lỗi target không?

Annotation mô tả cấu hình; nó **không tự quyết định precedence**. Cần quy tắc phối hợp độc lập theo cơ chế AOP và test.

## 13. Tối ưu reflection và cache cấu hình

Mỗi lần invocation gọi `target.getClass().getMethod(...).getAnnotation(...)` có thể có overhead. Khi metadata của class ổn định, có thể cache một **resolved configuration** theo khóa đủ chính xác, ví dụ:

```text
(target runtime class, interface Method, annotation type)
    -> validated immutable configuration
```

Đây là mô hình khóa cache; tùy thiết kế có thể cần cả class loader/biến thể generic/pointcut. Một `ConcurrentHashMap` có thể giúp thread safety, nhưng nó **có thể giữ mạnh key `Class`** và làm class loader khó được thu gom trong môi trường plugin/redeploy.

Cần chọn phương án phù hợp:

- Cache metadata theo `ClassValue` khi phù hợp để tránh một số kiểu retention.
- Không cache bằng key chỉ là **tên method**, vì overload sẽ xung đột.
- Có chiến lược cho **dynamic class loading/redefinition** nếu môi trường hỗ trợ.
- Validation được làm trước khi đưa vào cache.
- Phân biệt “không có annotation” với “annotation bị lỗi”.
- Nếu annotation type thay đổi khi deploy, cache cũ không tự phản ánh artifact mới.
- Dùng microbenchmark đáng tin để chứng minh reflection là bottleneck trước khi làm cache phức tạp.

**Không phải lúc nào cache cũng tốt hơn.** Với lưu lượng thấp, lookup đơn giản dễ hiểu và ít rủi ro hơn một registry sống lâu chứa hàng nghìn class loader.

## 14. Generic methods, bridge, default interface methods

Cần thận trọng khi method resolution không đơn giản:

### 14.1. Generic erasure và bridge methods

Một implementation của interface generic có thể khiến Java compiler tạo **bridge method** synthetic để duy trì polymorphism sau erasure. Một bộ quét metadata có thể thấy bridge và method implementation, trong khi annotation nằm ở declaration cụ thể khác.

Đừng mặc định `getMethods()` rồi lấy method đầu tiên cùng tên là đúng. Cần xét `Method.isBridge()`, `isSynthetic()`, parameter types, declaring class và các quy tắc của công cụ đang dùng.

### 14.2. Default interface methods

Một default method có body trên interface. Tùy trường hợp class không override, lời gọi có thể dùng implementation của interface. Resolver dựa trên `getMethod` có thể nhận một `Method` do interface khai báo chứ không phải “method viết tại target class”.

Quy tắc precedence vẫn phải đọc được annotation đúng declaration, không suy mọi `getMethod` đều trả method do class triển khai tự khai báo.

### 14.3. Method overrides

Một method override trên subclass có thể mang annotation khác hoặc không mang annotation nào. Java method annotations thông thường không được kế thừa tự động theo mọi override. Nếu muốn fallback tới superclass method, phải tự định nghĩa điểm dừng và thứ tự tìm kiếm.

Với nhiều interfaces kế thừa nhau, cũng phải chọn declaration có ý nghĩa. Nếu hai interface đặt cấu hình trái nhau, nên phát hiện conflict hơn là chọn âm thầm một nguồn có thứ tự không được công bố.

## 15. Module, access và class-loader

Một runtime có Java Platform Module System (**JPMS**) có thể giới hạn access. `exports` cho phép truy cập public API ở biên module theo quy tắc; `opens` liên quan tới deep reflection. Hai cơ chế khác nhau.

Một annotation type hoặc target method không accessible từ module đang thực hiện lookup/invocation có thể tạo lỗi liên kết hoặc phản chiếu. `setAccessible(true)` không bảo đảm luôn thành công dưới module mạnh.

Trong môi trường nhiều class loader, hai class có **cùng binary name** nhưng do những loader khác nhau định nghĩa có thể là hai runtime types khác nhau. Khi đó:

```java
method.getAnnotation(Observe.class)
```

có thể không thấy annotation type người đọc mong đợi nếu `Observe.class` thuộc một loader/phiên bản khác. Không chỉ so tên annotation dạng chuỗi rồi cast tùy tiện sang kiểu trong loader khác.

Điểm kiểm chứng:

- Annotation type có được tải bằng loader đúng không?
- Target class có được weaver/proxy xử lý đúng không?
- Method `public` có thực sự accessible xuyên module?
- Artifact có giữ runtime annotation trong bytecode không?
- Có lẫn class đã weave và chưa weave không?
- Cache metadata có làm giữ class loader cũ không?

## 16. Đọc cấu hình từ annotation không phải cấu hình động từ xa

Annotation thường được **đóng vào class file**. Muốn đổi `@Observe(category="billing")` thành `"warehouse"` ở một implementation đã biên dịch, thông thường phải **đổi mã/bytecode rồi build/deploy tương ứng**, trừ khi công cụ có cơ chế biến đổi đặc thù.

Một hệ quản trị cấu hình động có thể kết hợp metadata với giá trị từ nơi khác:

```text
Annotation declaration:
    policyId = "invoice-tracing"

Runtime policy registry:
    invoice-tracing -> sampling = 10%, enabled = true
```

Đây là sơ đồ kiến trúc, không phải Java. Trong mô hình này, annotation chỉ là **khóa lựa chọn chính sách**, còn giá trị động đến từ registry. Phải công bố thứ tự ưu tiên, version, lỗi không khả dụng và mức tin cậy. Không tự nói “đọc annotation trong advice” đồng nghĩa đọc giá trị mới nhất từ service cấu hình.

Với cấu hình bảo mật quan trọng, dùng một service động còn cần xác thực, integrity, cache freshness và fallback fail-safe; annotation đơn lẻ không đảm bảo những điều đó.

## 17. Lỗi thường gặp và cách nhận diện

| Sai lầm | Biểu hiện | Cách giải quyết |
| --- | --- | --- |
| Thiếu `@Retention(RUNTIME)` | `getAnnotation` trả null dù source có annotation | Đặt retention đúng khi cần reflection |
| Dùng sai `@Target` | Annotation không gắn được nơi mong muốn | Định nghĩa METHOD/TYPE/PARAMETER phù hợp |
| Chỉ đọc interface method | Bỏ mất cấu hình ở implementation | Resolve implementation và công bố precedence |
| Chỉ đọc implementation method | Bỏ mất annotation ở interface | Fallback có chủ đích nếu hợp đồng cho phép |
| Coi `@Inherited` áp cho overridden methods | Cấu hình bị thiếu | Lookup method hierarchy rõ ràng |
| Coi meta-annotation tự được tìm đệ quy | `getAnnotation` trả null | Viết resolver/meta-lookup hoặc dùng công cụ đã xác minh |
| Đọc repeatable annotation bằng một `getAnnotation` | Thiếu các lần khai báo | Dùng `getAnnotationsByType` và merge rule |
| Chỉ so tên method | Lấy metadata sai overload | Dùng parameter types/signature |
| Bỏ qua bridge/synthetic method | Nhìn nhầm declaration hoặc metadata | Xử lý resolver đúng ngữ nghĩa |
| Không kiểm tra giá trị mặc định | Category trống, timeout âm, cardinality tăng | Validation ở build/startup/runtime |
| Dùng `logReturn=true` với dữ liệu nhạy cảm | Rò dữ liệu trong log | Redaction, allowlist, policy review |
| Annotation tùy ý tắt guard bắt buộc | Mất authorization/audit | Chính sách từ nguồn đáng tin, fail closed |
| Bọc mọi `proceed` trong catch “logger offline” | Nuốt lỗi target | Catch riêng nguồn lỗi observer |
| Coi proxy tự can thiệp self-invocation | Advice không chạy | Xác minh đường qua proxy/weaver |
| Cache theo tên method | Metadata sai giữa overload/classes | Khóa cache đủ chính xác |
| Cache class/Method trong global map vô hạn | Class-loader retention | Lifetime và eviction hoặc ClassValue |
| Tin annotation tự là dynamic config | Đổi config runtime không có hiệu lực | Tách declaration và registry |
| Không test deployment artifact | Runtime thiếu metadata/weaving | Kiểm tra đúng class file, loader và toolchain |

## 18. Ma trận kiểm thử advice đọc annotation

| Kịch bản | Kỳ vọng |
| --- | --- |
| Method có annotation RUNTIME ở implementation | Đọc đúng giá trị phần tử |
| Method chỉ annotate ở interface | Fallback đúng khi chính sách yêu cầu |
| Cả interface lẫn implementation annotate | Chọn precedence đã công bố |
| Method không annotate | Không áp observer nếu đó là contract |
| Method annotate với defaults | Giá trị default đúng |
| Method có category rỗng | Báo lỗi cấu hình hoặc degrade theo policy |
| Annotation thiếu RUNTIME retention | Reflection không thấy, không tự giả có |
| Nhiều overload cùng tên | Không đọc nhầm annotation |
| Override superclass annotation | Có/không fallback đúng theo quy tắc |
| Repeatable annotations | Đọc và hợp nhất đúng tất cả lần gắn |
| Meta-annotation | Chỉ đọc nếu resolver hỗ trợ đã định nghĩa |
| Method có `logReturn=false` | Không ghi result trong advice |
| Method có `logReturn=true` | Chỉ ghi result khi an toàn theo policy |
| Target return bình thường | Giá trị không bị đổi bởi observer |
| Target throw | Lỗi gốc không bị che |
| Logger/exporter lỗi | Observer handling không nuốt target error |
| Hai aspects cùng match | Precedence/nesting chính xác |
| Proxy bypass | Direct target không tự kích hoạt advice |
| Async method trả future | Phân biệt method return và future completion |
| Multi-thread | Metadata cache/target state an toàn |
| Class/module loader thay đổi | Lookup không giữ nhầm phiên bản |
| Artifact sau weaving | Annotation/advice hiện diện ở build thực |

### 18.1. Test âm quan trọng không kém test dương

Chỉ assert rằng method `save` có log chưa đủ. Cần assert rằng method `plain` **không** phát advice message, `fetch` **không** bị log result nếu annotation không cho phép, method khác với cùng tên nhưng chữ ký khác không bị chọn nhầm, và lỗi target vẫn đến đúng caller.

### 18.2. Test giá trị không phải chỉ test sự tồn tại

Một test kiểu `assertNotNull(getAnnotation(...))` không chứng minh `category`, `tags`, `logReturn` đúng hoặc quy tắc implementation-first được tôn trọng. Hãy assert **giá trị từng element và hành vi advice sau khi dùng cấu hình đó**.

### 18.3. Test trên đường gọi thực tế

Nếu dùng JDK proxy, test phải gọi **qua proxy**; nếu dùng weaver, test phải chạy trên **artifact đã được weave**. Cần thử đường gọi trực tiếp target và self-invocation để phát hiện phạm vi không được chặn. “Annotation tồn tại trong class file” và “advice thực sự chạy” là **hai sự thật riêng**.

## 19. Checklist thiết kế

1. Annotation có **mục đích và owner** rõ không?
2. `@Target` có đúng loại declaration advice cần xét không?
3. `@Retention` đủ cho giai đoạn truy xuất (runtime hay build) không?
4. Các annotation elements có kiểu, default và ràng buộc rõ không?
5. Pointcut chọn theo **method/interface/implementation/type** nào?
6. Resolver có quy tắc **precedence và fallback** công khai không?
7. Có trường hợp nhiều interfaces hoặc method overrides conflict không?
8. Có repeatable/meta/inherited annotation nào cần xử lý riêng không?
9. Values có phải **đề nghị quan sát** hay **chính sách bắt buộc**?
10. Advice có áp giới hạn dữ liệu nhạy cảm trước khi in args/result không?
11. Lỗi của observer có được tách khỏi lỗi target không?
12. Annotation có thể làm thay đổi retry/transaction/authorization ngoài ý muốn không?
13. Lookup reflection/caching có đúng overload, class loader và module không?
14. Có theo dõi phiên bản annotation/schema và binary compatibility không?
15. Có test return/throw, method không annotate, override và direct-target bypass không?
16. Có chạy test bằng toolchain/artifact **thật** thay vì chỉ bằng snippet đơn lẻ không?

## 20. Bài tập vận dụng và đáp án

### Bài 1 — Annotation không xuất hiện runtime

Một method có `@TraceRule` trong source nhưng `method.getAnnotation(TraceRule.class) == null`. Nguyên nhân đầu tiên cần kiểm tra?

**Đáp án:** `@Retention(RetentionPolicy.RUNTIME)` của annotation type, rồi đến method declaration thực sự được phản chiếu. Mặc định retention CLASS không bảo đảm reflection runtime đọc được.

### Bài 2 — Interface và implementation

`Gateway.save` ở interface có `@Observe(category="A")`, `GatewayImpl.save` có `@Observe(category="B")`. Theo contract implementation-first của ví dụ, category nào được dùng?

**Đáp án:** `B`. Resolver ưu tiên method của implementation; chỉ khi không có annotation mới dùng interface. Đây là quyết định thiết kế, không phải quy tắc tự động của mọi AOP.

### Bài 3 — Không có annotation

Method không mang `@Observe` ở bất kỳ nơi nào được quy tắc lookup xét. Advice quan sát có nên in log không?

**Đáp án:** Trong contract của ví dụ, không. Nó chuyển thẳng tới target. Nhưng nếu một chính sách bắt buộc phải áp mọi method nhạy cảm, **vắng annotation** không nên tự cho phép bypass.

### Bài 4 — Mặc định và cấu hình tường minh

`@Observe` có `logReturn() default false`. Có khác `@Observe(logReturn=false)` khi advice gọi `cfg.logReturn()` không?

**Đáp án:** Không khác ở **giá trị đọc được**. Cả hai trả false. Nếu cần phân biệt intent “không chỉ định”, phải có contract bổ sung.

### Bài 5 — Method overrides

Interface method annotate, implementation method không. Vì sao `implementationMethod.getAnnotation(...)` có thể trả null?

**Đáp án:** Java method annotation không được tự kế thừa từ interface declaration sang implementation. Resolver cần fallback nếu policy cho phép.

### Bài 6 — Annotation lặp

Method có hai `@Tag` repeatable. Tại sao chỉ gọi `getAnnotation(Tag.class)` có thể bỏ sót?

**Đáp án:** Vì nhiều annotation được biểu diễn qua repeatable/container semantics. Dùng `getAnnotationsByType(Tag.class)` nếu cần cả hai và quy định cách merge.

### Bài 7 — An toàn log

Method trả một object chứa credential, annotation đặt `logReturn=true`. Có được in `result.toString()` ngay không?

**Đáp án:** Không. Flag không thay thế kiểm soát dữ liệu. Cần giới hạn loại result, redaction và quy tắc log theo chính sách; có thể từ chối logging khi dữ liệu không an toàn.

### Bài 8 — Kiểu annotation và lỗi cấu hình

Method gắn `@Observe(category="")`. Vì sao compiler vẫn có thể chấp nhận nhưng advice nên báo lỗi?

**Đáp án:** Chuỗi rỗng vẫn là `String` hợp kiểu; ràng buộc “category không trống” là bất biến nghiệp vụ của annotation, cần validation riêng.

### Bài 9 — Java 17 demo

Vì sao `fetch("A1")` có dòng `ADVICE before read` nhưng không có `ADVICE return value:A1`?

**Đáp án:** Interface có annotation category read, implementation không annotate nên fallback dùng interface. `logReturn()` mặc định false, nên advice không in result; caller vẫn nhận và in `CALL value:A1`.

### Bài 10 — Lỗi target

`reject("C3")` ném `IllegalArgumentException`. Vì sao caller nhận đúng ngoại lệ thay vì `InvocationTargetException`?

**Đáp án:** Helper gọi reflection bắt wrapper `InvocationTargetException` và ném `getCause()`, còn advice chỉ quan sát và rethrow. `finally` vẫn chạy.

### Bài 11 — Meta-annotation

`@Critical` có `@Observe` gắn trên annotation type. Vì sao `method.getAnnotation(Observe.class)` không tự bảo đảm tìm được Observe?

**Đáp án:** Reflection không có một quy tắc quét meta-annotation tùy ý nhiều tầng cho mọi use case. Cần thiết kế resolver hoặc dùng công cụ có semantics đã xác minh.

### Bài 12 — Nhiều interface cùng method

Hai interfaces khai báo `save(String)` nhưng annotate khác nhau. Có nên coi handler biết chắc caller đã cast qua interface nào không?

**Đáp án:** Không. JDK Proxy xử lý duplicate signatures theo quy tắc riêng; một handler không nên suy ý nghĩa caller từ cast. Phải định nghĩa một contract thống nhất hoặc phát hiện conflict.

### Bài 13 — Cấu hình runtime

Bạn thay file YAML của ứng dụng nhưng `@Observe(category="old")` trong class file không đổi. Vì sao advice vẫn đọc `old`?

**Đáp án:** Annotation đi cùng declaration đã biên dịch, không phải một liên kết tới file cấu hình từ xa. Nếu muốn dynamic policy, phải xây một nguồn runtime riêng và quy tắc merge/version.

### Bài 14 — Proxy bypass

Một lớp có annotation ở `save` nhưng caller giữ target gốc thay vì proxy. Annotation có đủ làm advice tự chạy không?

**Đáp án:** Không. Annotation chỉ là metadata; cơ chế interception cần thực sự bao phủ đường gọi. Trong ví dụ JDK proxy, gọi trực tiếp target không chạy advice.

## 21. Ghi nhớ

- **Đọc annotation trong advice cần xác định đúng declaration, đúng retention và đúng hợp đồng sử dụng giá trị**, không chỉ gọi `getAnnotation` rồi tin kết quả.
- **RUNTIME retention** quan trọng cho Java reflection; `@Target` phải phù hợp method/type/parameter thực sự được xem.
- **Interface method khác implementation method**; annotations của chúng không tự được hợp nhất. Fallback/precedence phải được công bố và kiểm thử.
- **`@Inherited` không tự truyền method annotations**; repeatable và meta-annotations cần APIs/quy tắc riêng.
- **Giá trị annotation là metadata có kiểu**, không tự là dynamic config từ xa hay quyền bỏ qua một chính sách bảo mật.
- **Advice có thể bind annotation bằng pointcut hoặc lookup bằng reflection** khi ngôn ngữ/công cụ cho phép; selection và resolution phải thống nhất.
- **Không log kết quả nhạy cảm chỉ vì flag cho phép**; validation, data classification và failure contract là bắt buộc về mặt thiết kế.
- Reflection caching cần khóa đủ chính xác, thread safety và quản lý class loader; không tối ưu quá sớm.
- **Proxy/weaving coverage** quyết định advice có chạy hay không; annotation hiện diện trong class file không tự chứng minh join point đã được can thiệp.
- Test **positive/negative, method variants, inheritance, return/throw, proxy bypass, metadata version và artifact runtime thật**.
