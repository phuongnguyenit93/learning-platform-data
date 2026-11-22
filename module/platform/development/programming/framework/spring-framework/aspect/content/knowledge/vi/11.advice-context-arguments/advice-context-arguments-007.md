# argNames, tên tham số và tùy chọn biên dịch -parameters trong Spring Aspect

## 1. Vấn đề thực tế: advice lấy đúng đối số bằng cách nào?

Một Spring `@Aspect` thường cần biết **giá trị argument**, **annotation trên method**, **giá trị trả về** hoặc **ngoại lệ** của Spring bean được advise. Để đưa các giá trị ấy vào tham số của advice method, Spring phải giải quyết một bài toán: **tên biến được dùng trong biểu thức pointcut phải ánh xạ chính xác đến tên tham số nào trong Java advice method?**

Ví dụ:

```java
@Before("execution(* com.example.service..*.*(..)) && args(account,..)")
public void check(Account account) {
    System.out.println(account.id());
}
```

Ở đây, `account` trong `args(account,..)` là **tên binding**; `Account account` trong chữ ký advice là **tham số nhận actual argument**. Spring phải biết hai cái tên ấy tương ứng với nhau. Nếu file `.class` không giữ tên tham số, pointcut hoặc advice có nhiều tham số cùng kiểu, quá trình bind có thể thất bại hoặc trở nên mơ hồ.

Trong Spring AOP có hai cách chủ động, phổ biến nhất:

1. **Khai báo tường minh tên bằng `argNames`** trên annotation advice hoặc `@Pointcut`.
2. **Biên dịch Java với `-parameters`** để giữ metadata tên tham số cho reflection, cho phép Spring tự phát hiện tên từ method signature.

Spring còn có những cơ chế suy luận fallback khác, nhưng chúng có giới hạn; đừng dựa vào việc “đôi lúc suy ra được” để thiết kế hệ thống cần chạy ổn định giữa các bản build.

**Phạm vi bài:** tên tham số và binding trong Spring Framework `@AspectJ` **theo cơ chế Spring AOP proxy**, không phải hướng dẫn tổng quát về Java reflection hay lập trình AspectJ weaving bên ngoài Spring.

### Sau bài học, bạn sẽ làm được

- Hiểu ba khái niệm khác nhau: **tên biến trong pointcut**, **tên tham số Java** và **giá trị argument runtime**.
- Sử dụng `argNames` cho `@Before`, `@Around`, `@AfterReturning`, `@AfterThrowing` và `@Pointcut`.
- Biết khi nào có thể bỏ tên `JoinPoint`/`ProceedingJoinPoint` khỏi `argNames`.
- Bật `-parameters` khi build bằng Gradle, Maven hoặc `javac`.
- Kiểm tra metadata `Parameter.isNamePresent()` và phân biệt nó với debug information.
- Phát hiện lỗi khi đổi tên biến, thiếu tên binding, nhiều tham số cùng kiểu, hoặc không tương thích giữa named pointcut và advice.
- Chạy project Java 17/Spring Framework với **một aspect dùng `argNames`** và **một aspect dựa trên `-parameters`**, so sánh kết quả.
- Phân biệt name binding với những giới hạn bình thường của Spring AOP proxy như self-invocation.

## 2. Hai loại tên và giá trị thực tế

Xem lời gọi:

```java
orderService.submit("P-42", 3);
```

Giả sử target method là:

```java
public String submit(String code, int amount) {
    return "accepted:" + code + ":" + amount;
}
```

Một Spring advice có thể khai báo:

```java
@Before("execution(* demo.binding.OrderService.submit(..))"
      + " && args(code,amount)")
public void before(String code, int amount) {
    System.out.println(code + ":" + amount);
}
```

Ba phần có vai trò riêng:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Pointcut binding identifier** | `code` trong `args(code,amount)` | Biến do expression giới thiệu để bắt giá trị đối số phù hợp |
| **Advice Java parameter name** | `String code` | Tên mà Spring cần khám phá hoặc được khai báo tường minh |
| **Actual runtime value** | `"P-42"` | Đối số thật được caller truyền vào invocation |
| **Declared Java parameter type** | `String` / `int` | Điều kiện kiểu cho advice binding và method signature |
| **Spring bean proxy** | `orderService` được inject | Nơi Spring xét pointcut/advisors trước khi gọi target |

Đổi tên tham số của target từ `code` thành `sku` **không nhất thiết** làm expression `args(code,amount)` sai. `args(...)` có binding identifiers của **pointcut/advice**, không phải lệnh tìm target parameter theo tên source code. Nếu interface/implementation target được biên dịch không có `-parameters`, advice `args(code,amount)` vẫn có thể bind actual argument values nếu Spring xác định được **tên tham số của advice** bằng một trong các chiến lược hỗ trợ.

Nhưng nếu đổi tên tham số advice `String code` thành `String sku` mà giữ `args(code,amount)` và không đặt `argNames` tương ứng, Spring có thể không liên kết được biến đúng; khi đó mới xảy ra vấn đề trực tiếp của bài học.

### Phân biệt name binding với index

`JoinPoint.getArgs()[0]` lấy phần tử đầu theo **vị trí**, không cần đọc tên tham số advice. `args(code,amount)` bind theo những **tên symbol** được khai báo trong pointcut expression để Spring truyền giá trị đến advice parameters có kiểu tương ứng.

Khi một advice chỉ cần raw arguments để log đơn giản, `JoinPoint.getArgs()` đôi khi phù hợp hơn. Khi cần type-safe binding hoặc annotation/result/exception, `argNames`/`-parameters` mang ý nghĩa rõ ràng.

## 3. Spring tìm tên tham số như thế nào?

Theo Spring Framework reference, quá trình bind advice dựa trên những `ParameterNameDiscoverer` được thử theo thứ tự ưu tiên. Chiến lược nào lấy được tên hợp lệ trước sẽ được sử dụng.

### 3.1. Những chiến lược quan trọng

| Chiến lược Spring | Nguồn thông tin | Khi nào hiệu quả? |
| --- | --- | --- |
| `AspectJAnnotationParameterNameDiscoverer` | `argNames` khai báo trong annotation advice/pointcut | Khi tác giả tự đặt tên tường minh |
| `KotlinReflectionParameterNameDiscoverer` | Kotlin reflection | Với code Kotlin và thư viện reflection phù hợp |
| `StandardReflectionParameterNameDiscoverer` | Java reflection `Parameter.getName()` | Khi code Java được biên dịch bằng `javac -parameters` |
| `AspectJAdviceParameterNameDiscoverer` | Suy luận từ pointcut, `returning`, `throwing`, method types | Fallback trong những tình huống có đủ thông tin và không mơ hồ |

Nếu không discover được tên cần thiết, Spring có thể ném exception khi khởi tạo Spring AOP advisor hoặc khi chuẩn bị advice binding. **Không bảo đảm fallback suy luận được mọi expression phức tạp.**

Khi nhiều tham số cùng kiểu `String`, việc suy luận “tham số nào tương ứng tên nào” có thể không duy nhất; đó là một lý do lớn để dùng `-parameters` hoặc `argNames`.

### 3.2. Trường hợp không cần tên tham số

Advice không bind dữ liệu contextual nào:

```java
@Before("execution(public * com.example.service..*.*(..))")
public void count() {
    // Không có parameter cần bind.
}
```

Không cần `argNames` vì advice không nhận parameter.

Advice chỉ nhận join point:

```java
@Before("execution(public * com.example.service..*.*(..))")
public void inspect(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

Nếu tham số đầu là `JoinPoint` (hoặc `ProceedingJoinPoint` trong `@Around`), Spring có xử lý riêng cho tham số này. Advice chỉ có `JoinPoint` không nhất thiết phải khai báo `argNames`.

**Đừng suy ra từ hai trường hợp đơn giản rằng name metadata không quan trọng khi advice nhận nhiều parameters để bind.**

## 4. Cách thứ nhất: argNames tường minh

### 4.1. Trên @Before với args

```java
@Before(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void before(String code, int amount) {
    System.out.println("code=" + code + ", amount=" + amount);
}
```

`argNames` nhận danh sách tên phân cách bằng dấu phẩy, đặt theo **thứ tự parameters được bind trong advice signature**. Tham số `String code` nhận binding `code`; `int amount` nhận `amount`.

Nếu Java source đổi parameter names thành `String sku, int qty` nhưng annotation vẫn dùng `argNames="code,amount"`, Spring vẫn có thể bind đúng theo thứ tự, miễn các điểm cắt/kiểu tham số khớp. Với phương pháp này, **tên được khai báo bởi `argNames` là nguồn sự thật cho expression**, không nhất thiết phải trùng tên tham số Java source.

Để dễ đọc và ít nhầm, thông lệ tốt vẫn là **giữ tên `argNames` trùng với tên tham số thực tế**.

### 4.2. Kết hợp @annotation và args

```java
@Before(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount) && @annotation(marker)",
    argNames = "code,amount,marker"
)
public void before(
        String code, int amount, Tracked marker) {
    System.out.println(marker.value() + ":" + code + ":" + amount);
}
```

`marker` là một annotation object được bind từ annotation trên method; `code` và `amount` đến từ actual method arguments. `Tracked` ở snippet là một runtime-retained annotation dùng trên method, cần định nghĩa/import phù hợp. Project chạy đầy đủ ở phần 9 có định nghĩa đó.

Đây là **ba binding names** và ba advice parameters. Không được chỉ ghi `argNames="marker"` nếu Spring không còn cách khám phá `code` và `amount` tương ứng.

### 4.3. Bỏ tên JoinPoint khỏi argNames

Spring có quy tắc tiện lợi: nếu **tham số đầu tiên** của advice là `JoinPoint`, `ProceedingJoinPoint` hoặc `JoinPoint.StaticPart`, bạn **có thể bỏ tên của tham số ấy** khỏi `argNames`.

```java
@Before(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount) && @annotation(marker)",
    argNames = "code,amount,marker"
)
public void before(
        JoinPoint jp, String code, int amount, Tracked marker) {

    String method = jp.getSignature().getName();
    System.out.println(method + ":" + marker.value());
}
```

Ở đây có **bốn Java parameters**, nhưng `argNames` chỉ có **ba tên**; không phải lỗi. Spring nhận ra `JoinPoint jp` đứng đầu, còn ba tên được dùng cho các binding variables.

Quy tắc này không có nghĩa bạn có thể bỏ ngẫu nhiên tên của bất kỳ tham số nào. Nếu tham số đầu tiên là `String code`, không được bỏ `code` rồi chờ Spring tự đoán phần còn lại.

### 4.4. Với @Around và ProceedingJoinPoint

```java
@Around(
    value = "execution(public String com.example.service.NameService.hello(..))"
          + " && args(name)",
    argNames = "name"
)
public Object around(ProceedingJoinPoint pjp, String name)
        throws Throwable {

    return pjp.proceed(new Object[] { name.trim() });
}
```

`pjp` đứng đầu và được bỏ khỏi danh sách `argNames`; `name` được bind từ method argument. Đây là snippet minh họa cần có `NameService` và AOP setup phù hợp.

Trong **Spring AOP**, `proceed(Object[])` lấy **bộ arguments của target method** theo đúng số lượng, thứ tự và kiểu; không tự đồng nghĩa với `argNames`, và đây là điểm cần chú ý khi so với AspectJ compiler/weaver.

### 4.5. Với @AfterReturning và returning

```java
@AfterReturning(
    pointcut = "execution(public String com.example.service..*.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterReturning(String result) {
    System.out.println("returned=" + result);
}
```

`returning="result"` đặt **tên binding** của giá trị trả về; `argNames="result"` ánh xạ binding ấy đến parameter advice. Advice chỉ chạy khi target invocation kết thúc bình thường và kết quả phù hợp ràng buộc kiểu `String`.

**`result` không phải tên tham số của target method.** Nó là tên symbol của giá trị trả về ở advice layer.

### 4.6. Với @AfterThrowing và throwing

```java
@AfterThrowing(
    pointcut = "execution(* com.example.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterThrowing(Throwable error) {
    System.out.println("thrown=" + error.getClass().getSimpleName());
}
```

`throwing="error"` bind throwable được ném khỏi method invocation vào advice parameter. Kiểu `Throwable` bao quát checked/unchecked exceptions. Nếu dùng `IllegalArgumentException`, advice chỉ nhận loại throwable phù hợp kiểu đó.

Việc đổi string `throwing="error"` thành `throwing="cause"` mà không đồng bộ tên binding tương ứng có thể khiến Spring không resolve được advice parameters.

## 5. Cách thứ hai: bật javac -parameters

### 5.1. Java mặc định có giữ parameter names không?

Khi biên dịch Java bằng `javac` mà không bật `-parameters`, file `.class` thông thường **không có metadata MethodParameters cần cho `java.lang.reflect.Parameter` cung cấp tên source-level một cách đáng tin**.

Ví dụ:

```java
public void before(String code, int amount) {}
```

Nếu compile thiếu `-parameters`, Java reflection có thể trả những tên tổng hợp như `arg0` và `arg1`; `Parameter.isNamePresent()` thường là `false`. Những tên đó không nhất thiết trùng biến `code`/`amount` dùng trong pointcut.

Với:

```bash
javac -parameters -d out MyAspect.java
```

`javac` giữ tên parameters trong class metadata; reflection có thể thấy `code` và `amount`, cùng `isNamePresent() == true`.

Lệnh trên minh họa syntax compiler option, **không đủ để compile một Spring aspect độc lập** nếu thiếu classpath Spring/AspectJ và các source dependencies. Project chạy ở phần 9 cấu hình Gradle đầy đủ.

### 5.2. Gradle

Nếu dùng Gradle với plugin Java:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Lệnh này thêm `-parameters` vào các tác vụ compile Java. Nếu muốn chỉ đặt cho source set hoặc module chứa aspects, có thể cấu hình task cụ thể, nhưng cần đảm bảo **các aspect classes cần name discovery** thật sự được biên dịch với flag.

Trong Gradle hiện đại, có thể sử dụng cách tương đương:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Đừng mặc định một flag thiết lập ở module A sẽ tự áp dụng cho module B. Trong multi-module Gradle, cấu hình cần áp dụng ở module chứa mã aspect cần được compile. Việc Gradle daemon hoặc IDE chọn JDK khác với toolchain cấu hình cũng cần được kiểm tra khi build có lỗi.

### 5.3. Maven

Với Maven Compiler Plugin hỗ trợ tham số này, có thể khai báo:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Đây là đoạn cấu hình Maven POM cần ghép vào project thực tế, **không phải POM hoàn chỉnh**. `<parameters>true</parameters>` khiến plugin truyền metadata names tương ứng cho Java compilation; dùng version plugin được tổ chức dự án phê duyệt.

### 5.4. Kiểm tra metadata bằng reflection

```java
Method method =
    MyAspect.class.getDeclaredMethod("before", String.class, int.class);

for (Parameter parameter : method.getParameters()) {
    System.out.println(parameter.getName()
            + ":" + parameter.isNamePresent());
}
```

Snippet này cần `java.lang.reflect.Method`, `Parameter` và lớp `MyAspect` thật. Nếu compile bằng `-parameters` và method có hai tham số mang tên `code`, `amount`, ví dụ có thể in:

```text
code:true
amount:true
```

Khi không có flag, **tên cụ thể do reflection trả về không nên dùng như API hợp đồng**; kiểm tra `isNamePresent()` thay vì phỏng đoán tên biến từ debugger.

## 6. -parameters không đồng nghĩa debug information (-g)

Một nhầm lẫn phổ biến là cho rằng compile có debug symbols thì Spring chắc chắn biết tên advice parameters.

| Cơ chế | Thông tin | Có thay thế -parameters theo cách ổn định không? |
| --- | --- | --- |
| `javac -parameters` | Metadata `MethodParameters` đọc được bằng `java.lang.reflect.Parameter` | **Có**, dành cho Java reflection parameter-name discovery |
| `javac -g` | Debug information phục vụ debugger, có thể có local variable tables | **Không nên xem là thay thế tương đương** |
| `@Before(argNames="...")` | Tên binding được khai báo rõ trong annotation | **Có** cho binding advice đó, không cần phụ thuộc reflection names |
| AspectJ `ajc` | Có cơ chế giữ tên cần thiết của `@AspectJ` advice | Có thể không cần `argNames` nếu tên đã được compiler cung cấp |
| Compiler inference fallback của Spring | Suy luận từ biểu thức/loại parameter | Chỉ trong các trường hợp đủ thông tin, dễ có ambiguity |

Đối với Spring Framework hiện đại, tài liệu chính thức **khuyến nghị `-parameters`** cho Java reflection. Không lấy behavior từng có ở các phiên bản cũ hoặc build tool cũ làm hợp đồng bất biến.

**Điểm tinh tế:** Metadata trong `-parameters` cần xuất hiện trên **advice/pointcut method** để Spring tìm tên parameters của advice/pointcut. Bạn không nhất thiết phải gắn `-parameters` vào mọi target method nếu mục tiêu duy nhất là bind `args(code,amount)` đến advice parameters; nhưng việc giữ tên target method cũng hữu ích cho các tính năng Spring khác như data binding, validation và reflection. Quyết định phạm vi phải dựa trên dependency và đặc điểm project.

## 7. Named pointcut cũng có parameter names

Một named pointcut được tái sử dụng có thể mang parameters:

```java
@Pointcut(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void orderOperation(String code, int amount) {}
```

Khi advice dùng named pointcut:

```java
@Before(
    value = "orderOperation(code,amount)",
    argNames = "code,amount"
)
public void before(String code, int amount) {
    // ...
}
```

Hai lớp ánh xạ tồn tại:
1. `@Pointcut` method: expression `args(code,amount)` và signature của named pointcut nhận đúng binding.
2. Advice method: expression `orderOperation(code,amount)` cung cấp binding cho advice signature.

**Không lẫn** `argNames` ở `@Pointcut` với `argNames` ở advice. Nếu khai báo explicit ở một nơi nhưng nơi còn lại thiếu thông tin tên phù hợp, binding vẫn có thể thất bại.

### Chia sẻ sang aspect khác

Khi named pointcut nằm trong `com.example.aop.CommonPointcuts`, advice ở một `@Aspect` khác có thể tham chiếu:

```java
@Before(
    value = "com.example.aop.CommonPointcuts.orderOperation(code,amount)",
    argNames = "code,amount"
)
public void record(String code, int amount) {
    // ...
}
```

Đây là snippets minh họa cho visibility/name binding; các class phải được định nghĩa và dùng đúng Spring bean/pointcut configuration. Thường nên đặt named pointcut public nếu cần tham chiếu từ class/package khác.

## 8. Lỗi thường gặp khi sử dụng argNames và -parameters

### 8.1. Thiếu tên dẫn tới bind không được

```java
@Before("execution(* com.example.service..*.*(..))"
      + " && args(code,amount)")
public void before(String x, int y) {
}
```

Nếu không có `-parameters` và không khai báo `argNames`, Spring có thể suy luận được trong vài trường hợp đơn giản nhưng **không có bảo đảm ổn định trong mọi biểu thức**. Nếu quá trình suy luận không thành công, startup AOP có thể báo lỗi thiếu/bất nhất tham số binding.

Khắc phục:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void before(String x, int y) {
}
```

Cách này cho parser tên binding rõ theo thứ tự parameter. Hoặc giữ tên `String code,int amount` trong source và build với `-parameters`.

### 8.2. Hai tham số cùng kiểu gây ambiguity

```java
@Before("execution(* com.example.service..*.*(..))"
      + " && args(first,second)")
public void before(String first, String second) {
}
```

Nếu thiếu `argNames`/`-parameters`, algorithm suy luận không luôn xác định được symbol nào ứng với parameter nào. Không nên “tráo” thứ tự ý nghĩa của `first` và `second` chỉ vì hai tham số đều `String`.

Đặt explicit:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(first,second)",
    argNames = "first,second"
)
public void before(String first, String second) {
}
```

### 8.3. Trả kết quả và lỗi khác nhau: returning/throwing

Sai về tên:

```java
@AfterReturning(
    pointcut = "execution(* com.example.service..*.*(..))",
    returning = "value",
    argNames = "result"
)
public void after(String result) {}
```

`returning` muốn bind symbol `value`, trong khi `argNames` lại khai báo `result`. Đây là sự **không nhất quán về tên** cần sửa.

Đúng:

```java
@AfterReturning(
    pointcut = "execution(* com.example.service..*.*(..))",
    returning = "value",
    argNames = "value"
)
public void after(Object result) {}
```

Java parameter thực có thể tên `result`, vì explicit `argNames` mô tả binding names theo thứ tự. Tuy nhiên, để dễ bảo trì, nên đổi Java parameter thành `value` đồng nhất.

Với `throwing`, nguyên tắc hoàn toàn tương tự.

### 8.4. Đếm sai số tên do JoinPoint

Sai về assumption:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "jp,code"
)
public void before(JoinPoint jp, String code, int amount) {}
```

Mẫu này có **thiếu `amount`** cho binding, và `jp` lại được ghi như tên thường mà Spring có thể xử lý đặc biệt. Đúng và dễ đọc:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void before(JoinPoint jp, String code, int amount) {}
```

### 8.5. Cho rằng -parameters sửa mọi lỗi pointcut

`-parameters` **không giải quyết**:
- Pointcut `execution(...)` sai package/type/method signature;
- Spring aspect chưa được đăng ký bean;
- Target không được proxy;
- Self-invocation `this.method()` bypass proxy;
- CGLIB không override được `final`/`private` method;
- Annotation cần `RetentionPolicy.RUNTIME` nhưng không có;
- Binding kiểu không tương thích, hoặc expression `args(...)` yêu cầu arity khác actual method;
- Exception hoặc result không có type phù hợp với advice binding;
- Nhiều advisors trong context cùng tham gia và thay outcome.

Đó là các vấn đề khác, không phải name discovery.

## 9. Ví dụ chạy đầy đủ: explicit argNames và tự tìm tên từ -parameters

Ví dụ này tạo **một Spring service** với method `submit(String code, int amount)` và **hai aspects**:
- `ExplicitAspect` chủ động khai báo `argNames`, bind cả `args` và `@annotation`, đếm `@Before`, `@AfterReturning`, `@AfterThrowing`.
- `InferredAspect` **không dùng `argNames`**, nhờ `javac -parameters` để Spring đọc tên parameters `code`/`amount` từ bytecode.

Chúng ta tránh in log bên trong mỗi advice để kết quả không phụ thuộc thứ tự giữa hai aspects. Mỗi aspect tự đếm, rồi `main` in snapshot sau khi gọi service.

**Môi trường:** Java 17+, Spring Framework `6.1.14`, AspectJ Weaver `1.9.22.1`, Gradle. Spring Framework thuần, không cần Spring Boot, web server hoặc database.

### 9.1. Cấu trúc project

```text
spring-aop-parameter-names/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/binding/
    ├── Tracked.java
    ├── OrderService.java
    ├── ExplicitAspect.java
    ├── InferredAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 9.2. Gradle bật -parameters

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-parameter-names'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.binding.DemoApplication'
}
```

Điểm quyết định là `options.compilerArgs += ['-parameters']`: `InferredAspect.before(String code, int amount)` giữ lại hai tên cần thiết cho Spring reflection name discovery.

### 9.3. Annotation dùng trong @annotation binding

`src/main/java/demo/binding/Tracked.java`:

```java
package demo.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Tracked {
    String value();
}
```

`@Retention(RUNTIME)` bảo đảm Spring có thể đọc method annotation trong quá trình pointcut/advice matching. `@Tracked` đặt ở **method**, không phải argument type.

### 9.4. Target Spring service

`src/main/java/demo/binding/OrderService.java`:

```java
package demo.binding;

public class OrderService {

    @Tracked("orders")
    public String submit(String code, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "amount must be positive");
        }
        return "accepted:" + code + ":" + amount;
    }
}
```

Method không `final` và target class không `final`, nên có thể được Spring CGLIB proxy. Hai lần gọi trong `main` đều có `code="P42"`, nhưng khác `amount`.

### 9.5. Aspect khai báo argNames tường minh

`src/main/java/demo/binding/ExplicitAspect.java`:

```java
package demo.binding;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ExplicitAspect {

    private int beforeCalls;
    private int returnedCalls;
    private int thrownCalls;
    private String lastBinding = "";

    @Before(
        value = "execution(public String demo.binding.OrderService.submit(..))"
              + " && args(code,amount) && @annotation(tag)",
        argNames = "code,amount,tag"
    )
    public void before(JoinPoint jp, String code, int amount, Tracked tag) {
        beforeCalls++;
        lastBinding = jp.getSignature().getName()
            + ":" + code + ":" + amount + ":" + tag.value();
    }

    @AfterReturning(
        pointcut = "execution(public String demo.binding.OrderService.submit(..))",
        returning = "result",
        argNames = "result"
    )
    public void returned(String result) {
        returnedCalls++;
    }

    @AfterThrowing(
        pointcut = "execution(public String demo.binding.OrderService.submit(..))",
        throwing = "error",
        argNames = "error"
    )
    public void thrown(IllegalArgumentException error) {
        thrownCalls++;
    }

    public int beforeCalls() { return beforeCalls; }
    public int returnedCalls() { return returnedCalls; }
    public int thrownCalls() { return thrownCalls; }
    public String lastBinding() { return lastBinding; }
}
```

Trong `before`:
- `args(code,amount)` bind actual arguments theo vị trí và kiểu.
- `@annotation(tag)` bind instance của `@Tracked("orders")` từ method execution.
- `JoinPoint jp` là tham số **đứng đầu**, do đó `argNames="code,amount,tag"` cố ý **không có `jp`**.
- `@AfterReturning` chỉ tăng trên normal return.
- `@AfterThrowing` dùng kiểu `IllegalArgumentException`, đúng kiểu lỗi của ví dụ.

Các biến đếm là field mutable trên singleton aspect; ví dụ gọi tuần tự để output đơn giản. Trong production concurrent, hãy dùng counters thread-safe hoặc hệ metric có hỗ trợ concurrency; không coi code đếm `int` này là mẫu production.

### 9.6. Aspect dựa vào -parameters

`src/main/java/demo/binding/InferredAspect.java`:

```java
package demo.binding;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class InferredAspect {

    private int beforeCalls;

    @Before(
        "execution(public String demo.binding.OrderService.submit(..))"
        + " && args(code,amount)"
    )
    public void before(String code, int amount) {
        beforeCalls++;
    }

    public int beforeCalls() {
        return beforeCalls;
    }
}
```

Không có `argNames` trong `@Before`. Vì build đã bật `-parameters`, Spring có thể lấy tên `code`, `amount` từ chính method `InferredAspect.before(...)` bằng `StandardReflectionParameterNameDiscoverer`. Nếu bỏ `-parameters` rồi build lại, Spring có thể dựa vào fallback inference hoặc báo lỗi, tùy mức rõ ràng của expression; **không nên dựa vào kết quả một thử nghiệm đơn giản để bảo đảm mọi advice phức tạp vẫn chạy**.

### 9.7. Khởi tạo context và đăng ký aspects

`src/main/java/demo/binding/AppConfig.java`:

```java
package demo.binding;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public ExplicitAspect explicitAspect() {
        return new ExplicitAspect();
    }

    @Bean
    public InferredAspect inferredAspect() {
        return new InferredAspect();
    }
}
```

`@Aspect` **không tự đăng ký bean**; ba `@Bean` methods khiến service/aspects thuộc Spring context. `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật Spring AOP và tạo class-based proxy phù hợp với `OrderService` không implement interface.

### 9.8. Main kiểm tra Java reflection và advice binding

`src/main/java/demo/binding/DemoApplication.java`:

```java
package demo.binding;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) throws Exception {
        Method method = InferredAspect.class.getDeclaredMethod(
            "before", String.class, int.class);

        boolean namesPresent = Arrays.stream(method.getParameters())
            .allMatch(Parameter::isNamePresent);
        System.out.println("namesPresent=" + namesPresent);

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            ExplicitAspect explicit =
                context.getBean(ExplicitAspect.class);
            InferredAspect inferred =
                context.getBean(InferredAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            System.out.println("result=" + service.submit("P42", 3));

            try {
                service.submit("P42", 0);
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println(
                "explicitBefore=" + explicit.beforeCalls());
            System.out.println(
                "explicitReturned=" + explicit.returnedCalls());
            System.out.println(
                "explicitThrown=" + explicit.thrownCalls());
            System.out.println(
                "inferredBefore=" + inferred.beforeCalls());
            System.out.println(
                "lastBinding=" + explicit.lastBinding());
        }
    }
}
```

### 9.9. Chạy và stdout dự kiến

Trong thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu project đã có Gradle Wrapper thì dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Hãy dùng Gradle hỗ trợ toolchain Java 17.

**Những dòng do Java code tự in**, không kể Gradle output hoặc logger của Spring:

```text
namesPresent=true
proxy=true
result=accepted:P42:3
caught=amount must be positive
explicitBefore=2
explicitReturned=1
explicitThrown=1
inferredBefore=2
lastBinding=submit:P42:0:orders
```

Giải thích:
- `namesPresent=true` xác nhận **method `InferredAspect.before`** mang Java parameter-name metadata.
- `proxy=true` cho thấy `OrderService` được Spring AOP proxy, nên lời gọi trong `main` thực sự được interception.
- `explicitBefore=2`: explicit `argNames` bind thành công trong cả hai lần gọi.
- `inferredBefore=2`: cách khám phá tên bằng `-parameters` cũng bind thành công hai lần.
- `explicitReturned=1`: lần `amount=3` trả bình thường.
- `explicitThrown=1`: lần `amount=0` ném `IllegalArgumentException`.
- `lastBinding=submit:P42:0:orders` chứng minh binding nhận đúng method name, actual `code`/`amount`, và giá trị `@Tracked` trên method.

**Không suy luận về thứ tự hai `@Before`** từ ví dụ: chúng không in log trong invocation, nên số đếm là ổn định dù Spring thay advisor ordering. Nếu nghiệp vụ phụ thuộc thứ tự advice, khai báo và kiểm thử `@Order`/`Ordered` riêng.

## 10. Khi nào ưu tiên argNames, khi nào ưu tiên -parameters?

| Tình huống | Khuyến nghị |
| --- | --- |
| Java project đang dùng Spring Framework hiện đại, kiểm soát được build | Bật `-parameters` nhất quán trong module chứa aspects |
| Advice phức tạp, nhiều parameters cùng kiểu, muốn public documentation rõ | Thêm `argNames` tường minh và dùng tên nhất quán |
| Java class được build bởi thư viện bên ngoài, không kiểm soát compiler options | Dùng `argNames` khi viết advice của mình, tránh phụ thuộc names bị strip |
| Advice chỉ nhận `JoinPoint` | Thường không cần `argNames` |
| Advice chỉ log trước và không bind tham số | Không cần `argNames` hoặc reflection metadata |
| Advice bind `returning`/`throwing` | Giữ symbol tương ứng với `argNames` và advice parameter đúng kiểu |
| Named pointcut truyền parameters sang advice | Bảo đảm name metadata hoặc explicit `argNames` ở cả pointcut method và advice |
| Tính năng cần đọc tên **target method parameters** cho API/docs/data binding | Bật `-parameters` ở module chứa **target classes** liên quan |
| Di chuyển code giữa Gradle modules hoặc CI khác IDE | Kiểm tra compiler flag ở đúng compile task, tránh assumption flag tự lan |
| Muốn loại bỏ ambiguity khó tái hiện | Viết integration test Spring AOP proxy trên build artifact thực |

Không cần đồng thời khai báo `argNames` cho mọi advice đã có `-parameters`. Tuy vậy, với thư viện công khai hoặc expression phức tạp, explicit names có thể giúp người đọc hiểu binding contract và tránh phụ thuộc vào flags ở môi trường build bên ngoài.

## 11. Debug lỗi tên tham số theo từng bước

1. **Đọc chính xác exception root cause.** Lỗi có thể xuất hiện lúc Spring xây advisor hoặc khởi tạo context; đừng gộp mọi exception thành “pointcut sai”.
2. **Kiểm tra Spring bean.** Aspect đã được đăng ký và `@EnableAspectJAutoProxy` có hiệu lực trong đúng context?
3. **Kiểm tra biểu thức.** `args(x,y)` / `@annotation(tag)` / `returning` / `throwing` có tạo đủ binding variables không?
4. **Kiểm tra advice signature.** Số parameters, thứ tự, kiểu và tên có tương ứng expression?
5. **Kiểm tra tham số JoinPoint đầu tiên.** Nếu có, đừng bắt buộc phải khai báo tên nó trong `argNames`.
6. **Kiểm tra flags thực của compiler.** Build config chứa `-parameters` không đồng nghĩa source class được biên dịch lại thành công. Clean/rebuild khi cần.
7. **Kiểm tra trực tiếp `Parameter.isNamePresent()`** trên advice method trong compiled class.
8. **Không chỉ kiểm tra Debug/LineNumberTable.** `-g` không phải hợp đồng thay thế Java reflection parameter metadata.
9. **Nếu có nhiều parameters cùng kiểu**, dùng `argNames` rõ, không phụ thuộc fallback suy luận.
10. **Kiểm tra named pointcuts riêng.** Lớp chứa pointcut có tên parameters và annotation `argNames` phù hợp, expression được tham chiếu đúng scope/visibility?
11. **Kiểm tra Spring proxy/call path.** Nếu startup không lỗi nhưng advice không chạy, có thể vấn đề là method không match hoặc bị self-invocation, không phải tên parameters.
12. **Viết kiểm thử positive/negative.** Chạy method với các actual arguments/annotations phù hợp và không phù hợp; xác nhận advice values thực sự đúng, không chỉ đếm số lượt gọi.

### Ví dụ nhanh kiểm tra reflection metadata

```java
Method m = InferredAspect.class.getDeclaredMethod(
    "before", String.class, int.class);

for (Parameter p : m.getParameters()) {
    System.out.println(p.getName() + ":" + p.isNamePresent());
}
```

Trong project ở phần 9, đoạn này có thể in:

```text
code:true
amount:true
```

Khi dùng nhiều hệ build, nên đặt test/assertion tự động để phát hiện việc `-parameters` bị tắt ở module chứa aspects.

## 12. Checklist thực hành

- [ ] Xác định đây là bài toán **Spring Aspect binding**, không nhầm với tên target method parameters.
- [ ] Mỗi biến trong `args(...)`, `@annotation(...)`, `target(...)`, `this(...)`... có type và tên advice parameter tương ứng.
- [ ] Nếu dùng `argNames`, số lượng/thứ tự tên khớp với các parameters cần bind.
- [ ] `JoinPoint`/`ProceedingJoinPoint`/`JoinPoint.StaticPart` ở tham số đầu được xử lý đúng, có thể bỏ tên trong `argNames`.
- [ ] Tên `returning`/`throwing` khớp tên binding của advice.
- [ ] `javac -parameters` bật ở đúng module/compile task khi dựa trên reflection names.
- [ ] Không đánh đồng `-g` và `-parameters`.
- [ ] Với named pointcut nhận parameters, kiểm tra cả tên ở pointcut declaration và advice caller.
- [ ] Aspect có `@Aspect` và là Spring bean; target do Spring quản lý.
- [ ] Spring AOP proxy được tạo và method invocation thực sự đi qua proxy.
- [ ] Có test cho multiple same-type parameters để phát hiện ambiguity.
- [ ] Không kỳ vọng `-parameters` sửa self-invocation, method `final`, sai pointcut hoặc thiếu annotation retention.

## 13. Kết luận

**`argNames` và `-parameters` giải quyết cùng một nhu cầu cốt lõi trong Spring Aspect: cho Spring biết tên cần thiết để liên kết pointcut variables với advice parameters.**

- **`argNames`:** khai báo **tường minh** những binding names theo thứ tự chữ ký advice/pointcut, phù hợp khi muốn rõ ràng hoặc không kiểm soát compiler flags.
- **`-parameters`:** giữ Java method parameter names trong bytecode để Spring tìm bằng reflection; là phương án được Spring khuyến nghị cho Java code hiện đại.
- **Fallback inference:** chỉ là trợ giúp trong một số trường hợp có đủ thông tin; không nên xem như bảo đảm cho mọi advice phức tạp.

Cả hai cách chỉ liên quan **name binding**. Chúng không thay đổi semantics của `args`, `@annotation`, `returning` hoặc `throwing`, và không xóa giới hạn Spring AOP là **chỉ method invocation qua Spring-managed proxy mới có thể nhận advice**.

### Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice, Determining Argument Names](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): danh sách `ParameterNameDiscoverer`, `argNames`, `-parameters`, quy tắc bỏ tên `JoinPoint` đứng đầu và `returning`/`throwing`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): `args`, `@annotation`, binding pointcuts và named pointcut declarations.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký Spring `@Aspect` và auto-proxy infrastructure.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation và giới hạn proxy.
- [Spring Framework API — AspectJAdviceParameterNameDiscoverer](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/aspectj/AspectJAdviceParameterNameDiscoverer.html): thuật toán fallback phát hiện tên, những trường hợp ambiguity.
- [Java 17 — javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn `-parameters` để tạo MethodParameters metadata.
