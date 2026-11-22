# Đối số `null`, kiểu nguyên thủy, overload và varargs trong Spring AOP

## 1. Vì sao đây là vấn đề quan trọng khi viết Spring Aspect?

Một lời gọi tới Spring bean có thể có tham số `null`, `int`, `boolean`, các method cùng tên nhưng khác kiểu tham số (*overload*), hoặc một method khai báo `String...` (*varargs*). Khi sử dụng `@Before`, `@Around` hay một loại advice khác, ta cần biết Spring AOP nhận diện **method nào** và lấy **giá trị đối số nào**.

Có hai phép xét khác nhau, rất dễ nhầm:

1. **`execution(...)`** chọn *method execution join point* theo **chữ ký method đã khai báo**, như tên method, số lượng và kiểu formal parameters.
2. **`args(...)`** xét **các đối số tại lời gọi**, có thể kiểm tra kiểu hoặc **bind argument value** vào tham số của advice. Một số điều kiện của `args` cần kiểm tra runtime, trong khi `execution` thường dùng thông tin tĩnh về chữ ký.

Trong Spring AOP, cả hai chỉ áp dụng cho **method execution đi qua Spring AOP proxy**. Chúng không tự biến mọi method call trong Java thành join point có thể được advice.

Các vấn đề cụ thể:

| Tình huống | Điểm cần nhớ |
| --- | --- |
| Đối số `null` | Không có runtime class của giá trị `null`; khi kiểm tra theo type, cần xét declared parameter type và cơ chế pointcut, không dùng `arg.getClass()` trực tiếp |
| `int`, `boolean` ... | Java method vẫn có kiểu primitive; nhưng `JoinPoint.getArgs()` là `Object[]`, nên primitive values xuất hiện dưới dạng boxed values |
| Overload | Java xác định overload theo compile-time argument types; Spring proxy intercept **method cụ thể đã được chọn**, không chọn overload mới |
| Varargs `T...` | Tại bytecode/reflective method signature, varargs là **một tham số array `T[]`**, không phải vô hạn tham số formal |
| Bind tham số advice | Tên trong `args(name)` phải được Spring liên kết đúng với Java advice parameter; có thể cung cấp `argNames` |
| Sửa arguments trong `@Around` | `proceed(Object[])` phải nhận đúng số lượng và kiểu tham số logic, chú ý primitive, `null` và array của varargs |

**Phạm vi:** tập trung vào **Spring Aspect / Spring AOP**, các kiểu advice, `JoinPoint`/`ProceedingJoinPoint` và method matching của Spring; không lặp lại lý thuyết Aspect tổng quát hay AspectJ compile-time weaving.

## 2. Hai cách đọc đối số trong advice

### 2.1. Cách tổng quát: `JoinPoint.getArgs()`

Mọi loại advice hỗ trợ `JoinPoint` làm tham số đầu tiên, còn `@Around` dùng `ProceedingJoinPoint`. Ví dụ:

```java
@Before("execution(* com.example.service..*.*(..))")
public void inspect(JoinPoint jp) {
    Object[] args = jp.getArgs();

    System.out.println("count=" + args.length);
    for (int i = 0; i < args.length; i++) {
        Object value = args[i];
        System.out.println(
            i + ": " + (value == null ? "<null>" : value.getClass().getName())
        );
    }
}
```

Đây là **đoạn minh họa cần đặt trong Spring-managed `@Aspect` bean**. `getArgs()` cho bạn từng argument tại invocation dưới dạng phần tử của `Object[]`:

- Argument được truyền `null` → phần tử `null`, không có class để gọi `getClass()`.
- Formal parameter `int` → giá trị ở `Object[]` được **box** thành `Integer` tương ứng.
- Varargs `String... tags` → thường là **một phần tử `String[]`** trong `Object[]` (không tự tách thành nhiều phần tử ở top level).
- Với overload, số/kiểu **giá trị runtime** chưa chắc nói hết chữ ký method cụ thể. Hai overload `foo(String)` và `foo(Integer)` đều có thể được gọi bằng một `null` được cast tương ứng.

`Object[]` chứa các **đối số được truyền vào lời gọi**, không phải mảng khai báo kiểu formal parameters. Muốn biết kiểu khai báo của method, sử dụng `MethodSignature`.

### 2.2. Cách có kiểu: `args(name)` để bind

Spring AOP cho phép ràng buộc argument vào tham số Java của advice:

```java
@Before(
    value = "execution(* com.example.service..*.save(..)) && args(id,..)",
    argNames = "id"
)
public void beforeSave(String id) {
    System.out.println("id=" + id);
}
```

**Đây là snippet, không phải file standalone.** Cú pháp `args(id,..)`:

- Chọn join point có **ít nhất một argument**, argument đầu thỏa binding type của `id`.
- Bind giá trị argument đầu vào tham số advice `String id`.
- `,..` cho phép còn **không hoặc nhiều** argument sau đó.
- `argNames = "id"` nói rõ tên binding để giảm phụ thuộc vào metadata tên tham số của compiler.

Không được nhầm:

- `args(java.lang.String)`: phần trong là **type pattern**.
- `args(id)` và Java advice parameter `String id`: đây là **binding form**.
- `execution(* *.*(java.lang.String))`: kiểm tra **declared method parameter type**, không phải class runtime của giá trị cụ thể.

Spring khuyến nghị sử dụng typed binding khi có thể, nhưng với yêu cầu quan sát nhiều overload, `null` và varargs cùng lúc, `JoinPoint.getArgs()` kết hợp `MethodSignature` thường dễ phân tích hơn.

## 3. Trường hợp đối số `null`

### 3.1. Một giá trị `null` không có runtime class

Giả sử method:

```java
public String accept(String value) {
    return value == null ? "EMPTY" : value;
}
```

Và lời gọi thông qua Spring proxy:

```java
service.accept(null);
```

Tại Spring advice, `jp.getArgs().length == 1` và `jp.getArgs()[0] == null`. Không được viết:

```java
String typeName = jp.getArgs()[0].getClass().getName();
```

vì có thể gây `NullPointerException` **ngay trong advice**, làm lỗi mới xuất hiện trước khi target chạy.

Cách an toàn:

```java
Object arg = jp.getArgs()[0];
String kind = (arg == null) ? "null" : arg.getClass().getSimpleName();
```

Các snippet ở phần này không phải project hoàn chỉnh; phần 7 có chương trình runnable.

### 3.2. Phân biệt `execution` và `args` khi có `null`

Với method khai báo `accept(String value)`:

- `execution(* *.accept(java.lang.String))` match **chữ ký một tham số `String`**, dù invocation truyền `"abc"` hay `null`.
- `args(java.lang.String)` là điều kiện type-related trên argument. Trong ngữ nghĩa AspectJ, khi argument **là `null`**, khả năng match được xét theo **static declared argument type** tương thích với type pattern; không thể lấy runtime class từ chính `null`. Với method có declared parameter `String` thì có thể match cho `null`.
- Nếu method khai báo `accept(Object value)` và caller truyền `null`, **đừng suy** rằng `args(java.lang.String)` phải match như trường hợp declared parameter `String`: kiểu tĩnh là `Object` và `null` không cung cấp class runtime để chứng minh nó là `String`.

Một case dễ nhầm:

```java
Object item = null;
service.acceptObject(item); // method acceptObject(Object)
```

Không thể suy “item từng dùng để giữ String nên `args(String)` khớp”; đối với `null` thì thông tin kiểu object động không tồn tại.

**Nguyên tắc thực hành:** nếu mục tiêu của advice là xử lý **cả giá trị `null`**, hãy match method theo chữ ký rõ ràng bằng `execution(...)` hoặc phạm vi method thích hợp, sau đó dùng `JoinPoint.getArgs()` và kiểm tra `null` bên trong advice. Cách này ổn định, dễ kiểm chứng và không phụ thuộc một suy luận sai về runtime class.

### 3.3. `null` và typed binding

Ví dụ:

```java
@Before(
    value = "execution(* demo..*.accept(java.lang.String)) && args(value)",
    argNames = "value"
)
public void capture(String value) {
    System.out.println(value == null ? "NULL INPUT" : "INPUT " + value);
}
```

Đây là advice **minh họa**, chưa được thêm vào project ở phần 7. Việc một binding kiểu tham chiếu có thể mang `null` **không giống** việc được phép bind `null` vào primitive `int`. Nếu cần xử lý `null` một cách chủ động, đặt tham số advice là reference type thích hợp và kiểm tra trước khi dereference.

`null` **không thể truyền trực tiếp** làm giá trị cho formal parameter primitive `int`/`boolean` của method Java; nếu wrapper `Integer` được unbox từ `null`, lỗi `NullPointerException` có thể xảy ra trước lúc Spring proxy thực sự nhận lời gọi đó.

## 4. Kiểu nguyên thủy và boxing khi đi qua Spring AOP

### 4.1. Formal parameter là primitive nhưng `getArgs()` chứa wrapper

Xét:

```java
public int addOne(int number) {
    return number + 1;
}
```

Với client gọi `addOne(4)` qua proxy:

| Câu hỏi | Kết quả |
| --- | --- |
| `Method.getParameterTypes()[0]` | `int.class` |
| `method.getParameterTypes()[0].isPrimitive()` | `true` |
| `JoinPoint.getArgs()[0]` | Boxed `Integer` giữ giá trị 4 |
| `JoinPoint.getArgs()[0] instanceof Integer` | `true` |
| Có thể truyền `null` trực tiếp cho formal `int`? | Không |

Tại JVM reflective/AOP invocation boundary, `Object[]` không thể chứa một primitive như `int` trực tiếp. Vì vậy Java boxing/unboxing tham gia khi biểu diễn hoặc chuyển đối số.

### 4.2. `args` và autoboxing

Theo AspectJ pointcut semantics, boxing/unboxing được tính đến khi match các kiểu primitive/wrapper. Ví dụ với **một argument** kiểu `int`, `args(int)` và `args(java.lang.Integer)` có thể đều phù hợp; điểm này không đổi formal signature là `int`.

Phân biệt rõ:

```text
Method signature: addOne(int)
                        |
                Spring AOP invocation
                        |
              JoinPoint.getArgs()[0]
                        |
                        v
                  Integer(4)
```

Nếu muốn chỉ chọn **formal primitive int**, dùng:

```java
@Before("execution(* demo..*.addOne(int))")
public void beforePrimitiveAdd() {
    // match method signature addOne(int)
}
```

Nếu muốn bind giá trị:

```java
@Before(
    value = "execution(* demo..*.addOne(int)) && args(amount)",
    argNames = "amount"
)
public void beforeAdd(int amount) {
    System.out.println("amount=" + amount);
}
```

Đây là **hai snippets độc lập**, cần @Aspect bean và import. `argNames` là tên tham số advice, không liên quan tên formal parameter trên implementation (formal parameter có thể tên `number` nhưng binding vẫn tên `amount`).

### 4.3. Những lỗi primitive thường gặp

- **Ép `Object` sang primitive bằng cast sai:** dùng `((Integer) obj).intValue()` hoặc cast hợp lệ với unboxing, không `obj.getClass()==int.class`.
- **Thay argument bằng `null` khi target cần `int`:** `proceed(...)` có thể thất bại khi Spring/reflective invocation phải unbox `null`.
- **Cho advice return `null` với method trả primitive:** nếu `@Around` trả `null` thay `int`, Spring có thể ném lỗi vì không thể dùng `null` làm primitive return value.
- **Nghĩ `Integer` và `int` luôn giống nhau:** declared method signatures `calculate(int)` và `calculate(Integer)` là **hai overload khác nhau**, dù argument reflection đều có thể xuất hiện dưới dạng `Integer` khi khác `null`.

## 5. Overload: Spring advice intercept method nào?

Java chọn **overload** trước khi Spring AOP thực thi invocation trên proxy. Ví dụ:

```java
public String render(String text) { return "S:" + text; }
public String render(Integer number) { return "I:" + number; }
```

Với lời gọi:

```java
service.render("hello");         // render(String)
service.render(Integer.valueOf(3)); // render(Integer)
service.render((String) null);   // render(String)
service.render((Integer) null);  // render(Integer)
```

Lời gọi không cast:

```java
service.render(null);
```

là **lỗi biên dịch do ambiguous overload** trong ví dụ hai kiểu không có quan hệ subtype `String` và `Integer`. Spring AOP không “giải quyết” lại overload ở runtime; program phải biên dịch trước đã.

### 5.1. Vì sao `getArgs()` chưa đủ để nhận diện overload?

Hai lời gọi:

```java
service.render((String) null);
service.render((Integer) null);
```

đều có `JoinPoint.getArgs()` biểu diễn thành:

```text
[null]
```

Nhưng method chữ ký khác nhau. Muốn biết chính xác method:

```java
MethodSignature sig = (MethodSignature) jp.getSignature();
Class<?>[] declaredTypes = sig.getMethod().getParameterTypes();
```

- Với overload đầu: `declaredTypes[0] == String.class`.
- Với overload thứ hai: `declaredTypes[0] == Integer.class`.

Mã đó là snippet cần import `org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method` nếu dùng `Method` trực tiếp.

### 5.2. Pointcut theo overload cụ thể

```java
@Before("execution(* demo..*.render(java.lang.String))")
public void beforeRenderText() {
    System.out.println("TEXT");
}

@Before("execution(* demo..*.render(java.lang.Integer))")
public void beforeRenderNumber() {
    System.out.println("NUMBER");
}
```

Đây là **hai advice minh họa**. Spring AOP dùng static signature để phân biệt hai overloaded methods, kể cả khi client truyền `null` đã cast.

Đừng dùng riêng `args(java.lang.String)` nếu bạn cần ràng buộc **tuyệt đối** vào overload có formal parameter `String`: khi tham số khai báo là `Object` nhưng runtime value là `String`, điều kiện `args(String)` còn có thể match lời gọi `render(Object)`. Kết hợp `execution(...)` và `args(...)` khi cần cả static method selection lẫn runtime value condition.

### 5.3. `int` vs `Integer` overload

Nếu class có:

```java
void total(int quantity) { }
void total(Integer quantity) { }
```

thì Java có hai overload hợp lệ. Khi gọi `total(5)`, compiler thường chọn formal primitive `int` phù hợp trực tiếp; `total(Integer.valueOf(5))` chọn reference `Integer`. Đối với `total(null)`, formal `int` không thể nhận null, nên overload wrapper `Integer` có thể được chọn.

Tại `getArgs()`, lời gọi thành công ở cả hai overload có thể thấy boxed `Integer`, nên **phải dùng method signature nếu muốn phân biệt formal `int` và `Integer`**.

## 6. Varargs: `T...` chính là một formal array parameter

### 6.1. Method được biên dịch ra chữ ký nào?

Java:

```java
public String tags(String label, String... names) {
    return label + ":" + names.length;
}
```

Về tham số phản chiếu (reflection), chữ ký tương đương:

```java
tags(String label, String[] names)
```

cộng thuộc tính **isVarArgs** trên method. Khi client gọi:

```java
service.tags("many", "a", "b");
```

Java compiler gom các varargs vào array cuối cùng trước khi invocation. Ở Spring AOP:

- `MethodSignature.getMethod().getParameterCount()` là **2**, không phải 3.
- `JoinPoint.getArgs().length` thông thường là **2**.
- `getArgs()[0]` là String `"many"`.
- `getArgs()[1]` là `String[] {"a","b"}`, **không** phải hai arguments top-level `"a"`, `"b"`.
- `((MethodSignature) jp.getSignature()).getMethod().isVarArgs()` trả `true`.

Nếu định bind phần varargs, hãy nghĩ tới **một array argument** `String[]`, không phải vô hạn Java advice parameters.

### 6.2. Ba trạng thái varargs cần phân biệt

| Cách gọi Java | Formal argument thứ hai trong method |
| --- | --- |
| `tags("zero")` | `new String[0]`, tức array rỗng |
| `tags("two","a","b")` | `String[] {"a","b"}` |
| `tags("nil",(String[]) null)` | **null array**, không phải mảng rỗng |
| `tags("oneNull",(String) null)` | `String[] {null}`, tức mảng có một phần tử null |

`tags("nil", (String[]) null)` là lời gọi đặc biệt cần cast rõ ràng. Đối với:

```java
tags("ambiguous", null);
```

Java có thể cảnh báo **non-varargs call for last parameter**, vì `null` có thể là array argument; đừng để người đọc đoán rằng null này có nghĩa là một phần tử trong array. Muốn một null element, dùng `(String)null` hoặc `new String[] { null }`.

Khi code advice cần in array đẹp, dùng:

```java
System.out.println(Arrays.deepToString(jp.getArgs()));
```

với import `java.util.Arrays`. `Arrays.toString(jp.getArgs())` có thể in identity string của nested `String[]`; `deepToString` hiển thị nội dung nested arrays một cách đọc được.

### 6.3. Pointcut `execution(..)` với varargs

Để chọn đúng method `tags(String, String...)` theo Java reflection parameter types, cần biết tham số cuối là `String[]`. Tuy nhiên cú pháp AspectJ pattern cho varargs có thể cần lưu ý cú pháp dấu ba chấm. Nếu không phải cố ý lọc chữ ký array, cách rõ ràng và ít lỗi:

```java
@Before("execution(* demo..*.tags(..))")
public void beforeTags(JoinPoint jp) {
    Object[] args = jp.getArgs();
    // Kiểm tra signature, array ở vị trí cuối nếu cần.
}
```

Đây là snippet. `(..)` match bất kỳ số formal parameters của method có tên `tags`; kiểm tra array thật bằng `MethodSignature` giúp tránh nhầm varargs ở call site với số lượng formal parameters.

**Không dùng** `args(label, first, second)` chỉ vì Java source call có hai vararg elements; đó không phải ba formal invocation arguments trong cơ chế proxy.

## 7. Project Spring AOP runnable: bốn loại tình huống trong một service

Ví dụ đầy đủ sử dụng **Java 17+, Maven, Spring Framework 6.2.6**. Nó có:

- Một Spring-managed bean `ArgumentService`, target implementation `ArgumentServiceImpl`.
- Một `@Aspect` dùng một `@Around` advice chỉ để **ghi lại method signature và argument values** rồi gọi `proceed()` đúng một lần, không thay đổi dữ liệu.
- Những lời gọi `null`, primitive `int`, hai overload nhận `String`/`Integer`, varargs rỗng/nhiều phần tử/null array/array chứa null.
- Output độc lập với tên generated proxy class: aspect in **declared parameter simple names** từ `MethodSignature` và argument values qua `Arrays.deepToString`.

Cách tổ chức một `@Around` này giúp trace không phụ thuộc thứ tự của nhiều advices cùng match một join point. Mã chạy bằng Spring AOP proxy của framework, **không** compile-time weaving.

### 7.1. Cấu trúc thư mục

```text
spring-aop-argument-cases/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ArgumentCasesDemo.java
```

### 7.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-argument-cases</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ArgumentCasesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Tệp `src/main/java/demo/ArgumentCasesDemo.java`

```java
package demo;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class ArgumentCasesDemo {

    public interface ArgumentService {
        String accept(String value);
        int addOne(int number);
        String render(String value);
        String render(Integer value);
        String tags(String label, String... values);
    }

    public static class ArgumentServiceImpl implements ArgumentService {

        @Override
        public String accept(String value) {
            System.out.println("TARGET accept=" + value);
            return value == null ? "NULL" : "TEXT:" + value;
        }

        @Override
        public int addOne(int number) {
            System.out.println("TARGET addOne=" + number);
            return number + 1;
        }

        @Override
        public String render(String value) {
            System.out.println("TARGET render(String)=" + value);
            return "S:" + value;
        }

        @Override
        public String render(Integer value) {
            System.out.println("TARGET render(Integer)=" + value);
            return "I:" + value;
        }

        @Override
        public String tags(String label, String... values) {
            String view = values == null ? "null" : Arrays.toString(values);
            System.out.println(
                "TARGET tags label=" + label + " values=" + view
            );
            return label + ":" + (values == null ? "NULL" : values.length);
        }
    }

    @Aspect
    public static class TraceAspect {

        @Around(
            "execution(* demo..*.accept(..)) || " +
            "execution(* demo..*.addOne(..)) || " +
            "execution(* demo..*.render(..)) || " +
            "execution(* demo..*.tags(..))"
        )
        public Object trace(ProceedingJoinPoint pjp) throws Throwable {
            Method method =
                ((MethodSignature) pjp.getSignature()).getMethod();

            String declaredTypes = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));

            System.out.println(
                "AOP " + method.getName()
                    + "(" + declaredTypes + ")"
                    + " varargs=" + method.isVarArgs()
                    + " args=" + Arrays.deepToString(pjp.getArgs())
            );

            return pjp.proceed();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public ArgumentService argumentService() {
            return new ArgumentServiceImpl();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ArgumentService service = ctx.getBean(ArgumentService.class);
            System.out.println("AOP_PROXY=" + AopUtils.isAopProxy(service));

            System.out.println("CLIENT=" + service.accept(null));
            System.out.println("CLIENT=" + service.addOne(4));
            System.out.println("CLIENT=" + service.render((String) null));
            System.out.println("CLIENT=" + service.render((Integer) null));
            System.out.println("CLIENT=" + service.tags("zero"));
            System.out.println("CLIENT=" + service.tags("many", "x", "y"));
            System.out.println(
                "CLIENT=" + service.tags("nil", (String[]) null)
            );
            System.out.println(
                "CLIENT=" + service.tags("oneNull", (String) null)
            );
        }
    }
}
```

Vì `ArgumentService` là interface, cấu hình Spring Framework dùng `proxyTargetClass = false` có thể tạo **JDK dynamic proxy**. `TraceAspect` được đăng ký qua `@Bean` nên Spring đọc `@Aspect` và tạo advisor áp dụng cho các method trong biểu thức.

### 7.4. Chạy Maven

Từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

**Những dòng stdout do chính chương trình in, theo logic và chữ ký trong ví dụ** (không tính logging riêng của Maven/Spring):

```text
AOP_PROXY=true
AOP accept(String) varargs=false args=[null]
TARGET accept=null
CLIENT=NULL
AOP addOne(int) varargs=false args=[4]
TARGET addOne=4
CLIENT=5
AOP render(String) varargs=false args=[null]
TARGET render(String)=null
CLIENT=S:null
AOP render(Integer) varargs=false args=[null]
TARGET render(Integer)=null
CLIENT=I:null
AOP tags(String,String[]) varargs=true args=[zero, []]
TARGET tags label=zero values=[]
CLIENT=zero:0
AOP tags(String,String[]) varargs=true args=[many, [x, y]]
TARGET tags label=many values=[x, y]
CLIENT=many:2
AOP tags(String,String[]) varargs=true args=[nil, null]
TARGET tags label=nil values=null
CLIENT=nil:NULL
AOP tags(String,String[]) varargs=true args=[oneNull, [null]]
TARGET tags label=oneNull values=[null]
CLIENT=oneNull:1
```

Đây là **stdout dự kiến từ mã được trình bày**, không phải tuyên bố đã chạy Maven trong môi trường cụ thể.

### 7.5. Phân tích output theo từng chủ đề

**Trường hợp `accept(null)`:** advice nhìn thấy `args=[null]` nhưng vẫn xác định formal parameter là `String` thông qua `MethodSignature`. Target trả `NULL` mà không gây `NullPointerException`.

**Trường hợp `addOne(4)`:** signature hiển thị `addOne(int)`, trong khi `getArgs()` biểu diễn giá trị primitive 4 dưới dạng phần tử của `Object[]` và in `[4]`.

**Hai overload `render(...)`:** cả hai có `args=[null]`. Chỉ dựa vào giá trị runtime trong mảng không thể biết caller chọn overload nào; signature cho thấy `render(String)` hoặc `render(Integer)`.

**Varargs rỗng:** `tags("zero")` vẫn có **2 formal arguments**, trong đó array cuối có length 0. Vì vậy output `[zero, []]`.

**Varargs nhiều phần tử:** `tags("many","x","y")` là một label và một array cuối; `Arrays.deepToString` in `[many, [x, y]]`, không phải ba phần tử top-level.

**Null array:** `tags("nil",(String[])null)` chuyển array cuối là `null`; output `[nil, null]` và target được viết để không dereference `null`.

**Một phần tử null:** `tags("oneNull",(String)null)` tạo một array độ dài 1 có phần tử `null`; output `[oneNull, [null]]`, khác rõ với null array.

## 8. Ghép `execution(...)` và `args(...)` cho đúng mục đích

Bốn biểu thức minh họa sau **không phải advice được đăng ký trong project ở mục 7**:

```java
// 1. Formal method signature có một tham số String
@Before("execution(* demo..*.accept(java.lang.String))")
public void declaredString() { }

// 2. Runtime argument được bind theo type String
@Before(
    value = "execution(* demo..*.accept(..)) && args(value)",
    argNames = "value"
)
public void boundString(String value) { }

// 3. Formal overload render(Integer)
@Before("execution(* demo..*.render(java.lang.Integer))")
public void integerOverload() { }

// 4. Formal primitive int
@Before("execution(* demo..*.addOne(int))")
public void primitiveOverload() { }
```

Với **overload**, ưu tiên dùng `execution(...FormalType...)` để chọn chữ ký. Với **runtime condition hoặc muốn lấy giá trị cụ thể**, dùng `args(...)` (binding) hoặc `JoinPoint.getArgs()` khi muốn inspect rộng.

### `args(..)` không tự phân biệt mọi overload

Đặc biệt:

- Nếu overload có `render(String)` và `render(Object)`, một invocation `render(Object)` nhận runtime `String` có thể thỏa điều kiện `args(String)`, dù declared signature không phải `render(String)`.
- Nếu argument là `null`, kết quả typed matching chịu ảnh hưởng của declared parameter type; đừng coi `args(String)` là cách thử `arg instanceof String` trong mọi tình huống.
- Nếu method có primitive `int`, argument quan sát trong `Object[]` là boxed wrapper. Không suy ra formal signature từ mỗi `Object#getClass()`.
- Nếu method có varargs, phần cuối của `args` thường tương ứng với **một array argument** trong runtime invocation, không phải một biến binding riêng cho từng vararg element.

Một chiến lược an toàn cho bài toán logging tổng quát là **pointcut tương đối tĩnh** cộng với code xử lý các `Object[]` và signature có kiểm tra null/array.

## 9. Thay thế argument bằng `ProceedingJoinPoint.proceed(Object[])`

Trong `@Around`, Spring cho phép tiếp tục chain với **mảng arguments thay thế**:

```java
@Around("execution(* demo..*.accept(java.lang.String))")
public Object trimInput(ProceedingJoinPoint pjp) throws Throwable {
    Object[] next = pjp.getArgs().clone();

    String oldValue = (String) next[0]; // Có thể null
    next[0] = oldValue == null ? "" : oldValue.trim();

    return pjp.proceed(next);
}
```

Đây là **snippet**, chưa được đăng ký trong project mục 7. Điều quan trọng:

1. `proceed()` giữ nguyên arguments hiện tại.
2. `proceed(next)` chuyển các values mới tới phần tiếp theo của Spring AOP invocation, phù hợp khi cần chuẩn hóa input.
3. Số phần tử `next` phải khớp **formal parameter count** của method được intercept. Không nhầm số phần tử trong varargs array với số formal params.
4. Giá trị thay thế phải **assignable** tới formal parameter type; primitive không nhận `null`.
5. Nếu method overload, `proceed(newArgs)` **không gọi overload khác**. Nó tiếp tục *method invocation đã chọn* với các values mới, không gọi lại Java overload resolution.
6. Thay arguments có thể ảnh hưởng logic nghiệp vụ, cache key, validation và các advice khác tùy thứ tự interceptor; chỉ sửa khi có chủ đích và test.

### 9.1. Khi muốn sửa varargs

Giả sử đang advice method:

```java
String tags(String label, String... values);
```

Về formal params, có **hai vị trí**: `String` và `String[]`. Muốn thay array cuối bằng hai phần tử:

```java
Object[] next = pjp.getArgs().clone();
next[1] = new String[] {"normalized", "checked"};
return pjp.proceed(next);
```

Nếu chuyển nhầm:

```java
return pjp.proceed(new Object[] {
    "label", "normalized", "checked"
});
```

thì `Object[]` thay thế có ba phần tử, trong khi formal method chỉ có **hai parameters**; đây không phải cách an toàn để truyền varargs cho `proceed(Object[])`.

### 9.2. Kiểu `int` và `Integer` khi thay args

Với method `addOne(int)`:

```java
Object[] args = pjp.getArgs().clone();
args[0] = Integer.valueOf(10); // Hợp lệ để unbox thành int
return pjp.proceed(args);
```

Không dùng `args[0] = null`: không thể unbox null thành primitive `int`. Cũng không đưa một `Long` tùy ý thay cho `Integer` rồi giả định Spring luôn tự chuyển đổi mọi numeric type theo ý bạn.

### 9.3. Spring AOP và native AspectJ có khác biệt về binding

Tài liệu Spring giải thích cách viết `proceed(Object[])` nhất quán khi dùng fully-typed `@Around` advice và bind các method arguments theo thứ tự tương ứng. Khi chuyển logic từ Spring proxy mode sang AspectJ weaving mode, **không mặc định** mọi cách đẩy `Object[]` trong các snippets đều giữ nguyên semantics; tuân theo hợp đồng advice arguments/binding của mode đó.

## 10. Các tình huống bị hiểu nhầm với `@args`

Trong Spring AOP pointcuts, `args(Type)` và `@args(Annotation)` **khác hoàn toàn**:

- `args(Type)` xem kiểu/đối số runtime, có thể dùng binding form.
- `@args(Annotation)` dùng **annotation trên runtime class của argument object** để match theo cơ chế annotation designator.

Ví dụ:

```java
@Pointcut("@args(com.example.app.Tracked)")
public void trackedRuntimeArgument() {
}
```

Đây là **snippet minh họa**, cần annotation/class thật. Với argument `null` thì **không có runtime object class** để kiểm tra annotation. Vì thế không thể dùng `@args(Tracked)` như một cách tổng quát nhận diện annotation nằm trên type formal parameter khi giá trị null.

Nếu muốn điều kiện về **annotation trên khai báo parameter** hoặc trên method, cần chọn công cụ phù hợp (reflection metadata, annotation resolver, `@annotation` đối với method annotation) thay vì đánh đồng với `@args`.

## 11. Proxy boundary, JDK/CGLIB và method eligibility

### 11.1. Cùng biểu thức nhưng method không qua proxy

Một Spring aspect có pointcut khớp `addOne(int)`, nhưng nếu caller gọi:

```java
new ArgumentServiceImpl().addOne(4);
```

thì object này không phải Spring AOP proxy; advice không tự chạy.

Tương tự, khi target thực thi:

```java
public void outer() {
    this.inner("x");
}
```

lời gọi `this.inner(...)` bên trong target không quay lại proxy. Dù method `inner(String)` có `args(String)` và `execution(...)` phù hợp, Spring AOP sẽ không xử lý một join point mới ở ranh giới proxy cho lời gọi nội bộ đó.

### 11.2. Proxy strategy ảnh hưởng nơi có thể intercept

- JDK dynamic proxy công bố các interface methods. Trong project runnable, cả hai overload `render(String)` và `render(Integer)` đều nằm trên interface nên client gọi chúng được qua JDK proxy.
- CGLIB subclass proxy có thể intercept method overrideable trên implementation; `final/private` method không được advice nhờ CGLIB override.
- Chuyển từ JDK sang CGLIB **không tự làm null/varargs khác bản chất Java**: `String...` vẫn là array trong signature, primitive vẫn có boxing khi đi qua `Object[]`.
- Không cần ép CGLIB để phân biệt overload nếu interface đã công bố các overload.

### 11.3. Method reflection có thể là method interface

Với JDK proxy, `MethodSignature.getMethod()` thường phản ánh interface method được gọi. Nó vẫn chứa chữ ký formal parameters để phân biệt overload và varargs. Nếu cần tìm declaration cụ thể trên implementation để đọc method annotations, Spring cung cấp tiện ích như `AopUtils.getMostSpecificMethod(interfaceMethod, targetClass)`. Nhưng với bài toán **số argument, kiểu formal và isVarArgs**, chữ ký interface đã đủ trong demo.

## 12. Bảng quy tắc chọn công cụ

| Nhu cầu | Cách ưu tiên | Lý do |
| --- | --- | --- |
| Ghi lại mọi giá trị arguments, bao gồm null/array | `JoinPoint.getArgs()` + kiểm tra an toàn | Không ràng buộc bắt buộc một typed parameter |
| Phân biệt hai overload cùng tên | `MethodSignature.getMethod().getParameterTypes()` hoặc `execution(...Type...)` | Giá trị `null` có thể làm mảng runtime giống nhau |
| Bind tham số đầu kiểu cụ thể | `args(name,..)` + Java advice param + `argNames` | Typed binding rõ ràng |
| Chỉ chọn method formal `int` | `execution(* *.method(int))` | Tránh nhầm kiểu boxed value với declared signature |
| Biết method có varargs hay không | `Method.isVarArgs()` | Cờ metadata đúng thay vì đếm call-site arguments |
| Đếm varargs elements | Kiểm tra/cast formal array cuối, rồi `Array.getLength` hoặc `values.length` | Varargs được truyền như một array formal param |
| Muốn sửa input trước target | `@Around` và `proceed(Object[])` | Có quyền điều phối chain |
| Muốn chọn theo runtime object annotations | `@args(...)`, xét giới hạn null | Không phải cùng nghĩa với `args(...)` |
| Chẩn đoán không có advice | Kiểm tra proxy, expression và đường gọi | Spring AOP chỉ chặn lời gọi đi qua proxy |

## 13. Checklist gỡ lỗi

1. **Client có lấy đúng Spring bean từ context không?** Không dùng `new` để kiểm tra advice.
2. **Bean có proxy chưa?** Dùng `AopUtils.isAopProxy(bean)` trong test.
3. **Method actual signature là gì?** In `MethodSignature.getMethod()` và `getParameterTypes()`.
4. **Pointcut đang match static signature hay runtime arg type?** Phân biệt `execution` và `args`.
5. **Có argument `null` không?** Tránh dereference; kiểm tra declared type, không đoán runtime class.
6. **Formal parameter primitive hay wrapper?** `int` và `Integer` là overload khác nhau, nhưng `getArgs()` hiển thị boxed value.
7. **Method overload có ambiguous call không?** Java compile-time resolution có thể yêu cầu explicit cast với `null`.
8. **Varargs có phải array cuối không?** Phân biệt array rỗng, null array và array chứa phần tử null.
9. **Có `@Around` nào sửa arguments không?** `proceed(Object[])` phải đúng số formal params và kiểu được chấp nhận.
10. **Có `args(...)` binding name mismatch không?** Kiểm tra advice parameter names, `argNames` và kiểu binding.
11. **Method có bị short-circuit bởi advice khác không?** Cache/around advice có thể không gọi tiếp target.
12. **Có self-invocation, final/private hoặc khác biệt JDK/CGLIB không?** Pointcut khớp không có nghĩa mọi lời gọi đều được Spring proxy chặn.
13. **Logging có gây side effects không?** Đừng gọi `toString()` mù trên input lớn hoặc nhạy cảm; với arrays dùng cách in phù hợp và cẩn thận bảo mật.

## 14. Bài tập tự kiểm tra

**Câu 1.** `String accept(String value)` được gọi bằng `null` qua proxy. `getArgs()[0]` và formal parameter type là gì?  
**Đáp án:** Value là `null`; formal type vẫn `String.class`.

**Câu 2.** `int addOne(int number)` được gọi với 4. `getArgs()[0].getClass()` thường trả class nào?  
**Đáp án:** `Integer.class` do boxing; formal type vẫn `int.class`.

**Câu 3.** Có `render(String)` và `render(Integer)`. Gọi `render(null)` có chạy đến Spring aspect không?  
**Đáp án:** Không nếu Java compile báo ambiguous overload; cần cast `(String)null` hoặc `(Integer)null` để chọn method.

**Câu 4.** Với `render((String)null)` và `render((Integer)null)`, mảng `getArgs()` có đủ phân biệt overload không?  
**Đáp án:** Không; cả hai có thể là `[null]`. Dùng `MethodSignature` hoặc match `execution(...FormalType...)`.

**Câu 5.** `tags("x","a","b")` khai báo `tags(String, String...)`. `getArgs().length` thông thường bằng mấy?  
**Đáp án:** 2, vì formal varargs parameter là một `String[]`.

**Câu 6.** Khác biệt giữa `tags("x")` và `tags("x",(String[])null)`?  
**Đáp án:** Lần đầu có array rỗng; lần sau có null array. Code target cần xử lý khác nhau nếu muốn.

**Câu 7.** `tags("x",(String)null)` khác null array như thế nào?  
**Đáp án:** Nó tạo array một phần tử `null`; độ dài array là 1, không phải `null`.

**Câu 8.** `args(String)` có ý nghĩa chính xác như `execution(* *(String))` không?  
**Đáp án:** Không. `execution` chọn formal method signature, `args` xét argument/type at invocation; `null` và runtime subtype khiến khác biệt thể hiện rõ.

**Câu 9.** Dùng `@Around` đã intercept `render(String)`, rồi gọi `proceed(new Object[]{Integer.valueOf(5)})` có chuyển sang overload `render(Integer)`?  
**Đáp án:** Không. Spring tiếp tục invocation của method đã chọn; argument mới không buộc Java chọn overload lại.

**Câu 10.** `proceed(new Object[]{"label","a","b"})` có thích hợp để truyền ba vararg elements cho method `tags(String, String...)` không?  
**Đáp án:** Không. Formal signature có hai tham số, nên cần array cuối như `new Object[]{"label", new String[]{"a","b"}}`.

**Câu 11.** Nếu `@Before` match method nhưng target gọi nó bằng `this.method()` nội bộ, advice có chắc chạy không?  
**Đáp án:** Không, vì self-invocation trên target bỏ qua Spring proxy.

**Câu 12.** Vì sao không nên log `value.getClass()` cho mọi phần tử `getArgs()`?  
**Đáp án:** Vì có thể chứa null; ngoài ra log raw values có thể lộ bí mật và varargs arrays cần trình bày riêng.

## 15. Tài liệu chính thức

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `JoinPoint.getArgs()`, `args(name)` binding, advice parameter names, `proceed(Object[])`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `execution(...)` versus `args(...)`, static method signatures và runtime argument matching.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): method matching tĩnh/động trong Spring proxy.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): giới hạn JDK/CGLIB, self-invocation.
- [AspectJ Programming Guide — Pointcut Semantics](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): semantics của `args` và trường hợp `null`.
- [AspectJ 5 — Autoboxing and Unboxing](https://eclipse.dev/aspectj/doc/latest/adk15notebook/autoboxing.html): match primitive và wrapper với `args`.
