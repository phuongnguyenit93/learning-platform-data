# Kế thừa annotation và khác biệt giữa khai báo với thực thi trong Aspect/AOP

## 1. Vì sao chủ đề này quan trọng?

Trong **Aspect-Oriented Programming (AOP)**, một **aspect** có thể dùng annotation làm tiêu chí chọn những **join point** sẽ được advice. Ví dụ người phát triển đánh dấu một method bằng `@Audited` rồi kỳ vọng thao tác ấy sẽ được ghi audit:

```java
@Audited
public void submit() {
    // nghiệp vụ
}
```

Khi ứng dụng có kế thừa, triển khai interface hoặc method overriding, kỳ vọng này dễ sai:

- Annotation ở **class cha** có tự xuất hiện ở class con không?
- Annotation ở **method cha** có tự xuất hiện ở method override không?
- Nếu class con **không override** method, reflection thấy method thuộc class nào?
- Annotation trên **interface method** có tự áp cho implementation method không?
- Một method call qua kiểu interface và một method execution ở implementation có cùng metadata không?
- Nếu runtime receiver mang annotation kiểu, nó có nghĩa **method được gọi** cũng có annotation không?
- Khi proxy lấy một `Method` từ interface, liệu advice có đọc đúng annotation ở implementation?
- Việc một pointcut có thể chọn annotation ở **khai báo** đồng nghĩa advice chắc chắn **chạy** hay chưa?

Các câu hỏi ấy nằm tại giao điểm của **hệ thống kiểu Java**, **quy tắc kế thừa metadata**, **reflection** và **cơ chế chọn join point của một AOP engine**.

Điểm then chốt:

> **Kế thừa hành vi không đồng nghĩa kế thừa annotation; có annotation trong source cũng không đồng nghĩa mọi lời gọi runtime đều được can thiệp.**

Bài này trình bày kiến thức Aspect/AOP tổng quát từ cơ bản đến nâng cao, lấy **Java 17** làm nền tảng ngôn ngữ và **AspectJ** làm một ví dụ cụ thể về cú pháp pointcut dựa trên annotation. Cú pháp của AspectJ không phải cú pháp bắt buộc hay mặc định của mọi hệ thống AOP.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **annotation declaration**, **class inheritance**, **method inheritance** và **overriding**.
2. Giải thích chính xác phạm vi của meta-annotation `@Inherited` trong Java.
3. Phân biệt **method được thừa kế** với **method được override**, kể cả khi cả hai có cùng tên.
4. Hiểu khác biệt giữa `getMethod`, `getDeclaredMethod`, `getAnnotation` và `getDeclaredAnnotation`.
5. Phân biệt metadata ở **interface declaration**, **implementation declaration**, **runtime class** và **join-point subject**.
6. Phân biệt method **call** với method **execution** khi chọn annotation.
7. Thiết kế pointcut phù hợp khi class/method/interface có annotation ở những vị trí khác nhau.
8. Xác định ảnh hưởng của retention policy, annotation target, repeatable annotations và metadata ở parameter/type use.
9. Không suy diễn từ pointcut matching thành bảo đảm runtime interception khi còn weaving/proxy boundaries.
10. Kiểm thử dương/âm để xác nhận chính xác coverage và hành vi của advice.

## 3. Annotation trong Java là metadata, không phải lệnh thực thi

Một annotation là metadata gắn với thành phần chương trình. Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audited {}
```

Annotation `@Audited` tự nó **không chạy một dòng audit nào**. Cần một thành phần khác — compiler, processor, runtime reflection, interceptor hoặc AOP weaver — **đọc** metadata và quyết định hành vi.

Cần tách ba pha:

```text
Source declaration
  @Audited void submit()
        |
        v
Annotation metadata trong source / class file / reflection
        |
        v
AOP pointcut hoặc interceptor đọc/chọn metadata
        |
        v
Advice thực sự được áp dụng tại một join point
```

Bước cuối chỉ xảy ra khi công cụ hỗ trợ join-point kind ấy, class hoặc call site nằm trong phạm vi xử lý, điều kiện động đúng và đường chạy thực tế đi qua interception boundary.

**Annotation không tự biến method thành advised operation.**

## 4. Ba retention policies và vì sao chúng quan trọng

Java hỗ trợ:

| Retention | Có trong source? | Có trong class file? | Java reflection runtime thông thường đọc được? |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Có | Không được giữ | Không |
| `RetentionPolicy.CLASS` | Có | Có | Không qua reflection annotation thông thường |
| `RetentionPolicy.RUNTIME` | Có | Có | Có |

Nếu không chỉ định `@Retention`, mặc định của annotation type là **CLASS**.

Ý nghĩa với AOP:

- **Compile-time weaver** có thể quan sát annotation theo cơ chế compiler/source hoặc class file hỗ trợ.
- Một số **bytecode weaver** có thể phân tích annotation retention CLASS hoặc RUNTIME.
- Một **runtime reflection-based interceptor** thường cần `RUNTIME`.
- Đối với **annotation binding** vào tham số advice tại runtime, công cụ có thể yêu cầu `RUNTIME`.
- `SOURCE` không tồn tại trong binary để một runtime-only interceptor đọc lại.

Không có nguyên tắc “cứ dùng AOP thì annotation phải RUNTIME” cho mọi trường hợp; cần xác định **pha thực sự đọc metadata**.

### 4.1. Annotation target khác retention

```java
@Target(ElementType.TYPE)
```

giới hạn nơi có thể **khai báo annotation**, không nói nó tồn tại bao lâu.

```java
@Target(ElementType.METHOD)
```

cho phép đặt lên **method declaration**, không tự áp lên các method được gọi trong class.

```java
@Target(ElementType.TYPE_USE)
```

cho phép đặt trên **vị trí sử dụng kiểu**, khác với annotation của một method hoặc class declaration. Pointcut phải được thiết kế theo đúng loại metadata cần chọn.

## 5. `@Inherited` trong Java: phạm vi rất hẹp

Meta-annotation `java.lang.annotation.Inherited` báo rằng annotation có thể được tìm trên **superclass** khi truy vấn annotation của một **class declaration**.

Ví dụ:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Monitored {}

@Monitored
class Parent {}

class Child extends Parent {}
```

Với reflection:

```java
Child.class.isAnnotationPresent(Monitored.class) // true
```

nếu `Child` không trực tiếp khai báo annotation cùng kiểu và chuỗi superclass có annotation phù hợp.

Nhưng:

- `@Inherited` **không truyền annotation từ interface sang class implements**.
- `@Inherited` **không truyền annotation của method được override**.
- `@Inherited` **không truyền annotation của field hoặc constructor**.
- Việc subclass có annotation theo quy tắc này không làm các method của nó tự có method annotation tương ứng.
- `@Inherited` không tự chạy advice, không tự tạo pointcut hay tự sửa bytecode.

**Câu ngắn để ghi nhớ: `@Inherited` là quy tắc tìm annotation ở class hierarchy, không phải quy tắc “mọi thứ kế thừa mọi annotation”.**

### 5.1. Kế thừa class annotation không đồng nghĩa khai báo lại

Với `Child` ở trên:

```java
Child.class.getAnnotation(Monitored.class)         // khác null
Child.class.getDeclaredAnnotation(Monitored.class) // null
```

Hai phép đọc mô tả hai ý nghĩa khác nhau:

- **getAnnotation:** annotation được xem là *present* theo quy tắc của `AnnotatedElement`, có xét superclass với type annotation `@Inherited` phù hợp.
- **getDeclaredAnnotation:** chỉ annotation **khai báo trực tiếp** trên element được hỏi.

Dù `getAnnotation` trên `Child` tìm thấy `Monitored`, mã nguồn `Child` vẫn không chứa một khai báo `@Monitored` trực tiếp.

### 5.2. Class con khai báo annotation riêng

Nếu `Child` trực tiếp gắn cùng annotation type với giá trị khác, giá trị trên class con có thể **che** giá trị inherited của superclass theo semantics tương ứng.

Ví dụ:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Level {
    int value();
}

@Level(1)
class Base {}

@Level(2)
class Derived extends Base {}
```

`Derived.class.getAnnotation(Level.class).value()` trả `2`. Đừng tự gộp `1` và `2` thành một danh sách nếu annotation type không được thiết kế để biểu đạt aggregation.

## 6. Interface annotations không được thừa kế theo `@Inherited`

Ví dụ:

```java
@Monitored
interface Task {}

class TaskImpl implements Task {}
```

Ngay cả khi `Monitored` được khai báo `@Inherited`, Java không coi `TaskImpl` có annotation `Monitored` chỉ vì implement `Task`.

```java
TaskImpl.class.isAnnotationPresent(Monitored.class) // false
```

Lý do: quy tắc `@Inherited` của Java tra **superclass chain**, không tìm qua tất cả implemented interfaces.

### 6.1. Nhưng một công cụ có thể có chính sách mở rộng riêng

Một hệ thống metadata hoặc AOP engine có thể chủ động duyệt:

```text
class -> superclass
      -> interfaces
      -> superinterfaces
```

và tự hợp nhất annotation theo một policy. Nếu nó làm vậy, đó là **quy tắc resolver của công cụ**, không phải semantics mặc định của `Class.getAnnotation`.

Phải công bố:

- Có duyệt interfaces không?
- Nếu hai interfaces có annotation cùng type nhưng giá trị xung đột thì chọn thế nào?
- Có ưu tiên class trực tiếp hơn interface không?
- Có duyệt superinterfaces không?
- Có dừng khi gặp annotation trực tiếp không?

Không được suy từ một công cụ tự hỗ trợ interface lookup thành quy tắc chung của Java/AOP.

## 7. Method được thừa kế và method được override là hai trường hợp khác

Giả sử:

```java
class Parent {
    @Audited
    public void original() {}

    @Audited
    public void overridden() {}
}

class Child extends Parent {
    @Override
    public void overridden() {}
}
```

Có hai trường hợp:

**Trường hợp A — method không override**

`Child` không khai báo `original()`. Khi tra public method được thừa kế, reflection có thể trả về chính `Method` được khai báo ở `Parent`. Annotation `@Audited` thuộc **declaration của Parent.original** nên vẫn tồn tại trên Method đó.

**Trường hợp B — method override**

`Child.overridden()` là một **method declaration mới**. Dù nó override behavior của `Parent.overridden()`, annotation `@Audited` **không tự được copy** sang method declaration mới.

```text
Parent.original [@Audited]
       |
Child inherits unchanged
       -> reflection Method declaringClass = Parent
       -> annotation on that Method = present

Parent.overridden [@Audited]
       |
Child.overridden [no @Audited]
       -> reflection Method declaringClass = Child
       -> annotation on Child Method = absent
```

Đây là khác biệt trung tâm của bài.

### 7.1. `@Inherited` không sửa quy tắc này

Kể cả một annotation type đặt `@Inherited`, **method annotation vẫn không được inherited theo override**. Meta-annotation ấy được định nghĩa cho **class-level inheritance**.

Nếu muốn override tiếp tục được AOP advice áp dụng dựa trên annotation cha, phải thiết kế một **chính sách tìm metadata ancestor method** hoặc pointcut type/signature khác; không chỉ thêm `@Inherited`.

### 7.2. Overriding không đồng nghĩa redeclaration của annotation

`@Override` chỉ giúp compiler kiểm tra quan hệ override. Nó không chép metadata runtime của method cha sang method con.

Một method child có thể có **khác hẳn annotation**, kể cả khi trả cùng result. Cần phân biệt **behavioral substitutability** với **metadata inheritance**.

## 8. Reflection: `getMethod` và `getDeclaredMethod`

Với class `Child`:

- `getMethod("name", ...)` tìm **public method**, kể cả public method kế thừa.
- `getDeclaredMethod("name", ...)` chỉ tìm method **khai báo trực tiếp trong class**, bất kể visibility (nhưng cần quyền truy cập phù hợp nếu invoke).
- `Method.getDeclaringClass()` cho biết method declaration thực sự thuộc type nào.
- `Method.getAnnotation(...)` đọc annotation gắn với **method element ấy**, không tự đi lên override chain.
- `Class.getAnnotation(...)` có thể áp `@Inherited` đối với annotation trên class.

Ví dụ:

```java
Method inherited = Child.class.getMethod("original");
Method override = Child.class.getDeclaredMethod("overridden");

System.out.println(inherited.getDeclaringClass()); // Parent
System.out.println(override.getDeclaringClass());  // Child
```

Đây là **mảnh mã minh họa**; chương trình Java 17 runnable đầy đủ ở phần tiếp theo.

### 8.1. Khi dùng `getMethods()`

`getMethods()` trả một tập public methods nhìn thấy qua class, bao gồm inherited public methods. Kết quả không đồng nghĩa “mọi method được khai báo trong class”. Không dùng nó để kết luận `@Audited` được khai báo trực tiếp trên một class.

### 8.2. Khi dùng `getDeclaredMethods()`

`getDeclaredMethods()` không liệt kê những inherited methods chỉ tồn tại ở superclass/interface. Nếu aspect/interceptor dùng API này mà chưa xét inheritance, nó có thể bỏ sót annotation trên inherited declarations.

### 8.3. Metadata của method không phụ thuộc runtime receiver trong reflection thông thường

Một `Method` object chỉ một **declaration** cụ thể. `method.getAnnotation(Audited.class)` không thay đổi chỉ vì ta invoke method đó trên object kiểu `Parent` hay `Child`.

Ngược lại, **dispatch khi invoke** có thể chọn implementation override của receiver. Đây là ranh giới khai báo/thực thi rất quan trọng.

## 9. Java 17 runnable: class annotation, method override, interface và dispatch

Chương trình sau không cần một AOP framework hoặc compiler đặc biệt. Nó dùng reflection và một interceptor tự viết để minh họa chính xác **metadata có thể khác hành vi thực sự chạy**.

Tạo file `AnnotationInheritanceDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class AnnotationInheritanceDemo {

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Monitored {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Audited {}

    @Monitored
    static class Parent {
        @Audited
        public String process() {
            System.out.println("business:parent-process");
            return "parent";
        }

        @Audited
        public String inherited() {
            System.out.println("business:inherited");
            return "inherited";
        }
    }

    static class Child extends Parent {
        @Override
        public String process() {
            System.out.println("business:child-process");
            return "child";
        }
    }

    @Monitored
    interface Tagged {}

    static class TaggedImpl implements Tagged {}

    interface Task {
        @Audited
        String apply();
    }

    static class TaskImpl implements Task {
        @Override
        public String apply() {
            System.out.println("business:task");
            return "task";
        }
    }

    static void execute(String label, Object receiver,
                        Method selectedMethod) throws Exception {
        boolean annotated =
                selectedMethod.isAnnotationPresent(Audited.class);

        System.out.println("case:" + label
                + ":declaration="
                + selectedMethod.getDeclaringClass().getSimpleName()
                + ":annotated=" + annotated);

        if (annotated) {
            System.out.println("advice:before:" + label);
        }

        Object result = selectedMethod.invoke(receiver);
        System.out.println("result:" + result);

        if (annotated) {
            System.out.println("advice:after:" + label);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("class:child:present="
                + Child.class.isAnnotationPresent(Monitored.class));
        System.out.println("class:child:declared="
                + (Child.class.getDeclaredAnnotation(
                        Monitored.class) != null));
        System.out.println("class:interface-impl:present="
                + TaggedImpl.class.isAnnotationPresent(Monitored.class));

        Method childOverride =
                Child.class.getDeclaredMethod("process");
        Method inheritedMethod =
                Child.class.getMethod("inherited");
        Method interfaceMethod =
                Task.class.getMethod("apply");
        Method implementationMethod =
                TaskImpl.class.getMethod("apply");
        Method parentMethod =
                Parent.class.getMethod("process");

        System.out.println("method:child-override:annotated="
                + childOverride.isAnnotationPresent(Audited.class));
        System.out.println("method:inherited:declaring="
                + inheritedMethod.getDeclaringClass().getSimpleName());
        System.out.println("method:inherited:annotated="
                + inheritedMethod.isAnnotationPresent(Audited.class));
        System.out.println("method:interface:annotated="
                + interfaceMethod.isAnnotationPresent(Audited.class));
        System.out.println("method:implementation:annotated="
                + implementationMethod.isAnnotationPresent(Audited.class));

        Child child = new Child();
        TaskImpl task = new TaskImpl();

        execute("parent-method-on-child", child, parentMethod);
        execute("child-override", child, childOverride);
        execute("inherited-method", child, inheritedMethod);
        execute("interface-declaration", task, interfaceMethod);
        execute("implementation-declaration",
                task, implementationMethod);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac AnnotationInheritanceDemo.java
java AnnotationInheritanceDemo
```

**Stdout dự kiến chính xác:**

```text
class:child:present=true
class:child:declared=false
class:interface-impl:present=false
method:child-override:annotated=false
method:inherited:declaring=Parent
method:inherited:annotated=true
method:interface:annotated=true
method:implementation:annotated=false
case:parent-method-on-child:declaration=Parent:annotated=true
advice:before:parent-method-on-child
business:child-process
result:child
advice:after:parent-method-on-child
case:child-override:declaration=Child:annotated=false
business:child-process
result:child
case:inherited-method:declaration=Parent:annotated=true
advice:before:inherited-method
business:inherited
result:inherited
advice:after:inherited-method
case:interface-declaration:declaration=Task:annotated=true
advice:before:interface-declaration
business:task
result:task
advice:after:interface-declaration
case:implementation-declaration:declaration=TaskImpl:annotated=false
business:task
result:task
```

### 9.1. Vì sao `Child.class.isAnnotationPresent(Monitored.class)` là true?

`Monitored` được meta-annotated bằng `@Inherited` và được đặt trên `Parent`. `Child` extends `Parent` nhưng không trực tiếp khai báo `Monitored`, nên runtime class reflection tìm theo quy tắc inherited class annotation.

`Child.class.getDeclaredAnnotation(...)` là null vì không có khai báo annotation trực tiếp trên `Child`.

### 9.2. Vì sao `TaggedImpl` không có annotation?

`TaggedImpl` implements `Tagged`, còn `@Inherited` **không tìm annotation qua interface hierarchy**.

Đây là kết quả của **Java reflection semantics**, không phải phán quyết mọi AOP engine có hoặc không có resolver interface metadata riêng.

### 9.3. Vì sao `Child.process` không có `@Audited`?

`Child.process()` là một **override declaration mới**. Method-level annotation từ `Parent.process` không được Java kế thừa tự động.

### 9.4. Vì sao `Child.inherited` vẫn có `@Audited` khi tra `getMethod`?

`Child` không override `inherited`, nên `getMethod("inherited")` trả về `Method` được khai báo ở `Parent`. Annotation tồn tại **trên declaration của Parent**, chứ không phải được chép sang Child.

### 9.5. Vì sao `parent-method-on-child` in ra `business:child-process`?

Interceptor nhận một `Method` object đại diện cho `Parent.process` (có `@Audited`), nhưng gọi nó trên receiver thực tế là `Child`.

Theo dispatch động của Java với instance method override, `Method.invoke(child)` thực thi **Child.process**. Do vậy:

```text
Metadata được đọc từ Parent.process
Actual body chạy là Child.process
```

Chương trình cố ý mô phỏng một **policy chọn metadata dựa trên declaration được truyền vào**, không khẳng định một AOP engine phải chọn như thế ở mọi call/execution join point.

### 9.6. Vì sao interface-declaration có advice nhưng implementation-declaration không?

`Task.apply` được gắn `@Audited`; `TaskImpl.apply` không được gắn. Một interceptor đọc `Method` từ interface sẽ thấy annotation; một interceptor đọc `Method` từ implementation sẽ không thấy.

Cả hai invocation cuối cùng có thể chạy **cùng body TaskImpl.apply**. Sự khác biệt nằm ở **nguồn declaration metadata**, không phải body nghiệp vụ.

### 9.7. Những giới hạn của demo

- Không có weaving hoặc pointcut DSL thực sự.
- Interceptor chỉ kiểm một `Method` object được truyền vào, không tự chọn join point từ ứng dụng.
- Các method trong demo public để reflection invocation không vướng access.
- Reflection `invoke` có thể bọc exception business trong `InvocationTargetException`; ví dụ này không dùng nhánh lỗi.
- Việc source/interface metadata được chọn là **policy minh họa**, không chứng minh một engine khác sẽ làm y hệt.
- Không mô phỏng bridge methods, generics, default methods, concurrency hoặc asynchronous completions.

## 10. “Khai báo” và “thực thi” là hai trục độc lập

Cần phân biệt **declaration site** và **runtime execution site**.

```text
Interface Task.apply() [@Audited]          metadata ở interface
                   |
                   v
        TaskImpl.apply() [không annotation]
                   |
                   v
             Runtime executes TaskImpl.apply
```

Bốn thứ khác nhau:

1. **Annotated declaration:** annotation thực sự đặt trên element nào?
2. **Static signature at call site:** compiler thấy lời gọi qua kiểu nào?
3. **Runtime receiver class:** object thật thuộc lớp nào?
4. **Executed method body:** runtime dispatch vào phần code nào?

Một AOP engine có thể dựa vào một hoặc nhiều thứ ấy tùy **pointcut kind**, **designator** và **weaving boundary**.

### 10.1. Đừng dùng “method có annotation” mà không nêu Method nào

Tối thiểu phải biết: `Task.apply` ở interface, `TaskImpl.apply` ở implementation, hay `Parent.process` ở superclass?

Đó không phải các element tương đương trong Java reflection, dù chúng có quan hệ override/implementation.

## 11. Method call khác method execution trong AOP

Hai join-point kinds có ngữ nghĩa khác nhau trong những mô hình AOP hỗ trợ cả hai:

- **Method call join point:** sự kiện tại **nơi gọi** một method.
- **Method execution join point:** sự kiện tại **thời điểm thân method được thực thi**.

Ví dụ:

```java
Task task = new TaskImpl();
task.apply();
```

Ở source, static type của biến `task` là `Task`, nhưng runtime dispatch chạy `TaskImpl.apply`.

Với một engine hỗ trợ call-site weaving, pointcut dựa annotation ở call signature có thể xét **declaration được call site tham chiếu**.

Với execution weaving, pointcut có thể xét **method execution subject** tương ứng với body implementation.

**Do đó cùng một invocation logic có thể khớp annotation-based call pointcut nhưng không khớp annotation-based execution pointcut**, hoặc ngược lại, tùy metadata đặt ở đâu và quy tắc chính xác của engine.

### 11.1. Java dynamic dispatch không tự sao chép metadata

Dynamic dispatch chọn body thực thi. Nó **không gắn @Audited từ interface/parent lên class implementation/override**. Mọi lựa chọn kế thừa metadata ngoài quy tắc Java phải được diễn đạt bằng một resolver hoặc pointcut policy.

## 12. Cú pháp AspectJ: `@annotation`

Phần này dùng **AspectJ pointcut language** để minh họa. Đây không phải syntax Java thuần hay chuẩn cho mọi công cụ.

```java
pointcut annotatedExecutions():
    execution(* *(..)) && @annotation(Audited);

before(): annotatedExecutions() {
    System.out.println("audited execution");
}
```

**Đây là mảnh code AspectJ**, giả định `Audited` tồn tại với retention/target phù hợp và có một `aspect` chứa các khai báo. Nó chỉ những **execution join point** mà **subject** được xem có annotation `@Audited`.

Điều **không được suy** từ ví dụ:

- Không có quy tắc “override của annotated method cũng annotated”.
- Không có quy tắc “method implementation kế thừa method annotation từ interface”.
- Không có nghĩa chỉ cần đánh dấu interface là execution body implementation tự match.
- Không bảo đảm tất cả class sẽ được woven vào ứng dụng.
- Không bảo đảm annotation retention SOURCE có thể được đọc ở runtime.

### 12.1. `@annotation` trên method call

Một AspectJ snippet khác:

```java
pointcut annotatedCalls():
    call(* *(..)) && @annotation(Audited);
```

Pointcut này lựa chọn **call join points** có annotation ở subject của call, không đồng nghĩa với `execution`. Với interface/override, metadata subject có thể khác phương thức mà JVM cuối cùng chạy.

Tài liệu AspectJ phân biệt **subject of join point** và runtime target; phải kiểm tra đúng loại điểm, chữ ký và static call site.

### 12.2. Pattern có annotation trong method signature

Cũng trong AspectJ:

```java
execution(@Audited * *(..))
```

là ví dụ dùng **annotation pattern trên declaration của method** để chọn execution. Mặc dù có thể diễn tả tập tương tự `@annotation` ở một số trường hợp, binding giá trị annotation hoặc các điều kiện phức tạp cần xem ngữ nghĩa riêng của pointcut.

Đừng nhầm `@Audited` trong pattern với một lời gọi Java method có tên `Audited`.

## 13. `@within` và `@target` không cùng ý nghĩa

AspectJ có nhiều annotation designators:

| Designator | Trọng tâm lựa chọn trong AspectJ |
| --- | --- |
| `@annotation(A)` | Annotation ở **subject** của join point |
| `@within(A)` | Join point nằm trong code được khai báo trong type mang A |
| `@withincode(A)` | Join point nằm trong method/constructor mang A |
| `@this(A)` | Runtime type của object `this` tại join point mang A |
| `@target(A)` | Runtime type của target object mang A |
| `@args(A)` | Annotation trên runtime type của đối số được bind/match |

Các designator có những yêu cầu retention khác nhau. Theo tài liệu AspectJ:

- `@this`, `@target`, `@args` chỉ match khi annotation có **runtime retention**.
- `@within`, `@withincode` và `@annotation` có thể match annotation có ít nhất **class-file retention** theo khả năng weaving; khi cần **bind annotation instance vào advice**, yêu cầu runtime retention.

### 13.1. `@within`: lexical declaring type

Ví dụ:

```java
@within(Monitored) && execution(* *(..))
```

được đọc như các execution join points trong code được khai báo ở type thỏa điều kiện annotation theo ngữ nghĩa AspectJ.

Nó **không có nghĩa mọi method trong type đã có @Audited method annotation**. Đây là tiêu chí của **type declaration** và lexical location.

### 13.2. `@target`: runtime target type

```java
@target(Monitored) && execution(* *(..))
```

nhấn mạnh annotation trên **runtime target type**. Một runtime receiver là subclass của type được đánh dấu `@Inherited` có thể liên quan tới inherited class-level annotation theo quy tắc ngôn ngữ/công cụ, trong khi lexical declaring type lại thuộc type khác.

Không đánh đồng `@within` và `@target`: một bên hỏi **code khai báo trong type nào**, bên kia hỏi **object runtime thuộc type nào**.

### 13.3. `@this` và `@target` khác nhau khi có proxy-like models

Một số AOP implementations phân biệt `this` hiện tại và `target` object. Trong weaving models, binding cụ thể phụ thuộc join-point kind. Không áp một công thức “`this` luôn là proxy” cho mọi AOP engine; phải đọc semantics chính thức của công cụ.

## 14. `@withincode`: annotation ở method *chứa* join point

Ví dụ AspectJ:

```java
call(* *(..)) && @withincode(Audited)
```

Ý tưởng: chọn các **call join points** nằm **bên trong phần code của method/constructor được đánh dấu @Audited**.

Khác với:

```java
call(* *(..)) && @annotation(Audited)
```

Điểm thứ hai quan sát annotation ở **subject của lời gọi**, không phải ở **method đang chứa câu lệnh call**.

Ví dụ:

```java
@Audited
public void process() {
    helper();  // call nằm trong một method được chú thích
}
```

`@withincode(Audited)` có thể chọn call tới `helper` vì call site nằm trong body annotated `process`, **dù `helper` không mang @Audited**.

Đây là một khác biệt giữa **“declaration chứa code đang chạy”** và **“declaration của method được gọi”**.

## 15. Tại sao override làm thay đổi annotation-based pointcut?

Với:

```java
class Parent {
    @Audited
    public void process() {}
}

class Child extends Parent {
    @Override
    public void process() {}
}
```

Trong Java, annotation ở `Parent.process` không tự xuất hiện ở `Child.process`.

Đối với pointcut dựa trên **method execution annotation** của method override:

```text
execute Parent.process -> subject annotated @Audited
execute Child.process  -> child declaration not annotated
```

Khi call site dùng static type `Parent` nhưng runtime receiver là `Child`, call-site selection có thể liên hệ declaration `Parent.process` trong khi body thực tế là `Child.process`.

Điều này lý giải một vấn đề AOP rất phổ biến: **đánh dấu superclass method không luôn đủ để can thiệp mọi override bằng execution annotation pointcut**.

### 15.1. Những cách sửa có chủ đích

- **Gắn lại annotation trên override** nếu mỗi implementation cần xác nhận độc lập.
- **Đặt class-level annotation có @Inherited** rồi chọn theo đúng type-level policy, nếu nghiệp vụ là “toàn bộ type thuộc nhóm được audit”.
- **Viết một resolver duyệt overridden ancestor methods** nếu đó là yêu cầu và engine hỗ trợ.
- **Dùng pointcut theo signature/type/interface/role** thay vì dựa duy nhất method annotation.
- **Sử dụng một wrapper/facade chịu trách nhiệm công khai** để bảo đảm security/audit boundary khi annotation lookup qua proxy có thể mơ hồ.

Không giải quyết bằng cách tự thêm `@Inherited` vào `@Target(METHOD)` rồi kỳ vọng Java tự kế thừa annotation method.

## 16. Interface method annotation: lựa chọn giao diện hay triển khai?

Ví dụ:

```java
interface Billing {
    @Audited
    Receipt charge();
}

class BillingImpl implements Billing {
    @Override
    public Receipt charge() {
        // logic
    }
}
```

Annotation `@Audited` nằm ở `Billing.charge`. `BillingImpl.charge` là **method declaration riêng** không tự có annotation.

Các cách định nghĩa chính sách:

**Policy A — theo interface contract:** mọi implementation của `Billing.charge` đều được audit vì interface công bố một hợp đồng xuyên suốt.

**Policy B — theo implementation opt-in:** chỉ những concrete implementation methods gắn `@Audited` được audit.

**Policy C — theo public entry point:** audit khi caller đi qua một facade/proxy cụ thể, không phụ thuộc annotation kế thừa.

Cả ba đều có thể hợp lý tùy mục tiêu, nhưng **không phải cùng một policy**.

### 16.1. Tránh phụ thuộc cách interceptor lấy `Method`

Một dynamic proxy interface có thể nhận metadata method tương ứng **interface**; một mechanism khác có thể nhìn implementation method. Nếu code giả định luôn lấy đúng nguồn nhưng deployment đổi interception strategy, coverage có thể thay đổi.

Hợp đồng AOP nên nêu rõ annotation được đọc ở đâu và có fallback từ implementation sang interface không.

### 16.2. Nếu interface có nhiều cha

```text
Interface A declares work @Policy(level=1)
Interface B declares work @Policy(level=2)
Concrete C implements A, B
```

Resolver tự duyệt interfaces có thể gặp **xung đột**. Không nên tự chọn “interface đầu tiên” phụ thuộc thứ tự reflection không được hứa.

Cần một precedence policy, quy tắc hợp nhất, hoặc từ chối cấu hình mơ hồ.

## 17. Không nên “hợp nhất annotation” theo trực giác

Một số hệ thống cố làm:

```text
Find annotation on:
  1. concrete method
  2. superclass method
  3. interface method
  4. runtime class
  5. superclass class annotation
```

Đây là **cơ chế resolver tùy chỉnh**. Nếu chọn triển khai, phải ghi:

- Thứ tự ưu tiên.
- Dừng ở annotation đầu tiên hay hợp nhất nhiều annotation?
- Thế nào là override hợp lệ? Bao gồm covariant return, generics?
- Có tính bridge/synthetic methods không?
- Có duyệt superinterfaces không?
- Cách giải quyết diamond graph.
- Annotation repeatable được trả dưới dạng nào?
- Annotation trên type khác annotation trên method ra sao?
- Nếu annotation âm tính hoặc override policy, điều gì thắng?
- Có cache metadata để tránh reflection lặp nhiều lần không?

**Đừng tự biến một thuật toán resolver riêng thành “Java annotation inheritance”.** Ghi rõ đây là semantics của thư viện hoặc application AOP policy.

## 18. Declaration metadata và runtime context phải được đánh giá riêng

Ví dụ một annotation trên class:

```java
@Monitored
class SharedService {}
```

Một runtime object `SharedService` có type metadata. Nhưng điều đó không nói rằng mọi method đều có annotation `@Audited`.

Một annotation trên method:

```java
@Audited
public void save() {}
```

không nói rằng runtime args, target hay caller mang `@Monitored`.

Vì thế khi thiết kế aspect nên tách:

1. **Type-level selection** — dựa trên class/interface metadata theo policy.
2. **Method-level selection** — dựa trên method declaration metadata.
3. **Argument-level dynamic checks** — dựa trên actual argument values/runtime types.
4. **Control-flow selection** — dựa trên ngữ cảnh call stack/join-point flow.
5. **Weaving coverage** — class nào/call site nào thực sự được instrument.

Một “chính sách @Audited” có thể là kết hợp của nhiều tiêu chí nhưng phải diễn đạt rõ phép AND/OR/exclude.

## 19. `@Inherited` và repeatable annotations

Java cho phép một annotation type được khai báo `@Repeatable`. Khi tra annotation bằng reflection:

- `getAnnotation(A.class)` có semantics cho **một annotation type**; không tự trả mọi repeated annotations.
- `getAnnotationsByType(A.class)` có thể **mở container annotation** để trả nhiều annotation type A.
- `getDeclaredAnnotationsByType(A.class)` chỉ xét annotation trực tiếp/gián tiếp trên element, **không kế thừa**.
- `getAnnotationsByType` trên class có thể xét `@Inherited` theo quy tắc *associated* annotations.
- Quy tắc với **container annotation** phải phù hợp với yêu cầu của `@Repeatable` và `@Inherited` trong JLS.

Ví dụ cấu trúc:

```java
@Inherited
@Repeatable(Labels.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Label {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}
```

Đây là **mảnh code Java** để giải thích schema repeatable; compiler cần thấy import `java.lang.annotation.*` và các khai báo đặt trong file hợp lệ. Có thể khai báo cả repeatable type và container với `@Inherited` nếu muốn thực hiện kế thừa phù hợp.

### 19.1. Repeatable + subclass annotations không phải hợp nhất tự động

Nếu superclass có hai `@Label` và subclass có một `@Label` khác, không tự suy danh sách của subclass là **ba**. Theo quy tắc liên quan đến `getAnnotationsByType`, khi class hiện tại có annotation liên quan trực tiếp/gián tiếp, kết quả có thể ưu tiên declaration hiện tại thay vì cộng dồn superclass.

Một AOP resolver cần định nghĩa rõ muốn **shadow**, **append** hay **reject conflicts**.

## 20. Annotation trên parameter và type use khác method annotation

Ví dụ:

```java
public void save(@Sensitive String token) {}
```

`@Sensitive` trên **parameter declaration** (nếu `@Target(PARAMETER)`) không có nghĩa method `save` được annotate `@Sensitive`.

Ví dụ khác:

```java
public @Nonnull String lookup() { ... }
```

`@Nonnull` có thể là annotation trên **return type use**, không nhất thiết là method declaration annotation, tùy `@Target` được hỗ trợ.

Java reflection phân biệt:

- `Method.getAnnotations()` cho declaration annotations của method.
- `Method.getParameterAnnotations()` cho annotations trên parameter declarations.
- `Method.getAnnotatedReturnType()` cho type-use annotations của return type.
- `Parameter.getAnnotations()` cho parameter declaration annotation.
- `AnnotatedType` API cho metadata gắn với type uses.

AOP engines có thể hỗ trợ matching parameter annotations/type patterns theo cú pháp riêng. Không coi `@annotation(A)` là một phép tìm mọi annotation nằm ở bất kỳ vị trí nào trong chữ ký method.

## 21. Bridge và synthetic methods khi có generics

Java compiler có thể tạo **bridge methods** để giữ polymorphism sau type erasure. Một class có:

```java
interface Store<T> {
    T load();
}

class StringStore implements Store<String> {
    public String load() {
        return "value";
    }
}
```

có thể có bridge method synthetic ở class file để thực hiện hợp đồng erased signature.

Rủi ro khi xây annotation resolver:

- Reflection liệt kê nhiều `Method` có vẻ cùng tên.
- Annotation có thể hiện diện/được copy lên bridge method tùy cơ chế compiler, không được suy tất cả toolchains đều giống nhau.
- Pointcut signature/annotation matching có thể phụ thuộc compiler/weaver.
- Cache key chỉ dùng tên method dễ trùng overload/bridge.
- Một method đang chạy không đồng nhất với element mà annotation ban đầu được đặt trong source.

Khi thiết kế AOP dùng annotation làm quy tắc quan trọng, nên kiểm thử bytecode và `Method.isBridge()`, `Method.isSynthetic()`, signature thực sự với compiler/toolchain đang dùng.

### 21.1. Không dùng tên method làm khóa metadata duy nhất

`save(String)` và `save(long)` có thể mang policy khác. Resolver nên định danh method bằng declaring type, tên, parameter types và các thông tin phù hợp; đừng bỏ qua overload/generic erasure.

## 22. Default methods và abstract methods của interface

Một interface có thể có **default method** với implementation. Khi class không override, phần code được thực thi có thể nằm trong interface default method.

Khác với interface abstract method chỉ công bố contract:

```java
interface AuditOps {
    @Audited
    default void audit() {
        // code mặc định
    }
}
```

Tùy static receiver và weaving model:

- Call site có thể liên hệ method declaration trong interface.
- Execution body có thể là default implementation của interface.
- Nếu class override, body và method declaration thay đổi.
- Reflection `getMethod` có thể trả interface method khi class kế thừa nó.
- Nếu class cụ thể override, annotation trên default method không tự được copy vào override.

Nên có test riêng cho default method thay vì suy từ những case class inheritance thông thường.

## 23. Annotation trên constructor không được kế thừa

Constructors không override như instance methods. Một constructor annotation trên superclass **không xuất hiện** trên constructor của subclass chỉ vì subclass gọi `super(...)`.

```java
class Parent {
    @AuditedConstructor
    Parent() {}
}

class Child extends Parent {
    Child() {
        super();
    }
}
```

Đây là **mảnh code minh họa**, giả định `AuditedConstructor` có target phù hợp. Không có nghĩa `Child()` đã gắn annotation của `Parent()`.

Một aspect chọn **constructor call/execution** phải xem join-point kind, declaration của constructor và weaving scope; không áp quy tắc override method.

## 24. Annotation có thể ở package/module mà không phải type/member

Java cho phép annotation trên package hoặc module declarations theo `@Target(PACKAGE)` hoặc `@Target(MODULE)` và cú pháp khai báo hợp lệ.

Việc một package được annotate **không tự làm mọi class trong package mang annotation**. Tương tự, module metadata không tự lan thành class/method annotations.

Một AOP framework có thể tự xây policy kiểu “mọi class trong package có marker đều được audit”, nhưng đây là **configuration rule riêng**, không phải Java `@Inherited`.

Trong AspectJ cụ thể, các loại annotation pointcut được hỗ trợ và giới hạn với package annotations cần tra **tài liệu phiên bản đang dùng**; không suy rằng một designator nhìn method annotation sẽ tự đọc package metadata.

## 25. Type-level annotation và cấu trúc inheritance phức tạp

Xét:

```text
@Monitored
Base
  |
Middle
  |
Leaf
```

Nếu `@Monitored` là annotation type có `@Inherited` và không bị một declaration trực tiếp phù hợp che, `Leaf.class.getAnnotation(Monitored.class)` có thể tìm xuyên các superclass theo quy tắc Java.

Nhưng nếu:

```text
@Monitored Interface A
          \
           Leaf implements A
```

thì `Leaf` không thừa kế class-level annotation từ interface theo `@Inherited`.

Cần phân biệt:

- **Superclass inheritance path:** là nơi `@Inherited` của Java có hiệu lực.
- **Interface implementation path:** không nằm trong quy tắc ấy.
- **Containment/nesting:** inner class không tự thừa kế annotation của enclosing class.
- **Composition/delegation:** một field giữ object annotated không làm class chứa field mang annotation.
- **Subclass-specific declaration:** có thể che hoặc thay giá trị theo annotation type.
- **Annotation meta-hierarchy:** không có quy tắc Java “tự duyệt mọi annotation gắn trên annotation khác” thành một compositional policy.

## 26. Meta-annotation không đồng nghĩa alias/chaining tùy ý

Một annotation type có thể được annotate bởi annotation khác:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Classified {}

@Classified
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Restricted {}
```

Một class gắn `@Restricted` **không tự được `Class.getAnnotation(Classified.class)` xem là có `@Classified`**. `Classified` ở đây được khai báo trên **annotation type Restricted**, không trực tiếp trên class.

Nếu muốn “annotation composed” có thể thay marker khác trong pointcut/resolver, phải có quy tắc xử lý meta-annotation riêng, có thể duyệt annotation types và xác định cách giải quyết alias/conflict.

**Java không tự định nghĩa semantics alias của mọi meta-annotations.**

## 27. Cách thiết kế resolver annotation có chủ đích

Một hệ thống muốn hỗ trợ kế thừa metadata qua interface/override có thể định nghĩa một **hợp đồng**:

```text
ResolvePolicy(method, runtimeClass):
  1. Read annotation directly on most-specific method.
  2. If none, inspect matching overridden superclass declaration.
  3. If none, inspect matching interface declarations.
  4. If none, inspect class-level policy (direct/inherited).
  5. If none, return NO_POLICY.
```

Đây là **pseudocode của một resolver do ứng dụng thiết kế**, không phải semantics mặc định của Java hay pointcut AspectJ.

### 27.1. Kiểm tra “matching overridden declaration” không đơn giản bằng tên

Resolver cần hiểu:

- Method overloads.
- Parameter erasure/bridge.
- Covariant returns.
- Visibility/override constraints.
- Static method hiding (không phải overriding).
- Private methods (không override theo nghĩa thông thường).
- Interface default methods.
- Những class/member ngoài weaving scope.
- Quy tắc dispatch runtime và module access.

Nếu chỉ “tìm method cùng tên trên superclass”, dễ gắn policy của method không liên quan.

### 27.2. Cần chính sách conflict rõ

Nếu concrete method không gắn annotation, còn superclass/interface có hai policy khác nhau, cần biết:

- Ưu tiên class direct annotation không?
- Có inherit policy từ interface nếu override không annotate không?
- Interface A hay B thắng?
- Có nên từ chối khi conflicting values?
- Có annotation “opt-out” riêng không, với semantics gì?
- Có cần cache kết quả không và khi nào invalidate?

Một policy bảo mật hoặc audit bắt buộc không nên dựa trên thứ tự reflection không được bảo đảm.

## 28. Metadata resolution khác weaving coverage

Ngay cả khi resolver trả “có `@Audited`”:

```text
policy resolver says audited = true
```

nó **không đảm bảo advice thực sự chạy** ở mọi invocation.

Các nguyên nhân:

- Class/call site chưa được weave.
- Engine chỉ intercept những interface proxy invocations cụ thể.
- Caller giữ raw target và gọi trực tiếp.
- Target self-invocation không đi qua proxy delegation vào object khác.
- Advice precedence cao hơn short-circuit trước khi advice bên trong chạy.
- Runtime guard hoặc dynamic condition không match.
- Build khác đã dùng metadata đã cũ hoặc class loader khác.
- Method final/private/static/constructor không nằm trong loại join point engine hỗ trợ.
- Annotation retention không tương thích với pha đọc.

Do đó test phải tách:

1. **Metadata present?**
2. **Pointcut matched?**
3. **Actual interception fired?**
4. **Advice behavior satisfied contract?**

Không được gộp thành một unit test `isAnnotationPresent == true` rồi tuyên bố hệ thống AOP an toàn.

## 29. Thực hành với AspectJ: câu hỏi cần trả lời trước khi viết pointcut

Trước một pointcut dựa annotation:

```java
execution(* *(..)) && @annotation(Audited)
```

hãy hỏi:

1. Metadata nằm trên implementation method hay interface method?
2. Method có được override mà quên annotation không?
3. Class-level annotation có `@Inherited` không?
4. Dùng `execution` hay `call` đúng boundary mong muốn?
5. Type/method nào là subject trong DSL của engine?
6. Có dynamic subtype context cần xét `@target` hay không?
7. Có yêu cầu matching annotation ở code chứa join point (`@within`, `@withincode`) không?
8. Annotation retention CLASS/RUNTIME có tương thích không?
9. Có cần bind giá trị annotation vào advice không?
10. Module/class loader nào đã được weave?
11. Có self-invocation hoặc raw-target bypass không?
12. Advice có thể bị precedence/around short-circuit không?

### 29.1. Một mẫu pointcut “có cả type và method”

Có thể muốn:

```text
advised operation = method explicitly @Audited
                    OR execution on a @Monitored target type
```

Đây là **quy tắc nghiệp vụ giả định**, không phải lúc nào cũng đúng. Nếu được triển khai, cần chú ý:

- `OR` có thể tăng coverage mạnh.
- `@Monitored` inherited từ superclass không nói từng method annotation nào tồn tại.
- Một method nhạy cảm được loại bởi exclusion có thể vẫn bị `OR` chọn lại nếu thiếu group parentheses.
- Một target type có runtime annotation nhưng method chạy trong library ngoài scope có thể không được weave.

Nên xác nhận cả **positive và negative matching** trước khi bật.

## 30. Bộ kiểm thử nên có

| Tình huống | Java annotation kết quả | Kiểm thử AOP cần thêm |
| --- | --- | --- |
| Class con extends annotated class với `@Inherited` | Class-level annotation có thể present | Xác nhận type-level pointcut và runtime target |
| Class con implements annotated interface | Không tự inherited qua interface | Xác nhận engine có policy interface traversal hay không |
| Child override annotated parent method | Child override không tự annotated | Xác nhận method-execution pointcut có match không |
| Child kế thừa method không override | `getMethod` có thể trả Parent Method có annotation | Xác nhận execution/call subject |
| Interface method annotated, impl không annotated | Hai `Method` có metadata khác nhau | Test proxy/interceptor nguồn method được chọn |
| Annotation chỉ `CLASS` retention | Java runtime reflection không đọc được | Test compile/binary weaver support |
| Annotation chỉ `SOURCE` retention | Không tồn tại trong class file | Test processor/compiler, không chỉ runtime |
| Repeatable annotations | `getAnnotationsByType` có thể mở container | Test shadow vs merge superclass |
| Generic bridge method | Có thể có synthetic/bridge metadata khác | Test actual selected Method và bridge |
| Interface default method | Body có thể nằm ở interface | Test override và execution boundary |
| Parameter annotation | Không tự là method annotation | Test designator/API đúng loại metadata |
| Type-use annotation | Không tự là class declaration annotation | Test `AnnotatedType`/DSL support |
| Raw target invocation | Có thể bypass proxy | Test advice thực sự chạy |
| Self-invocation | Phụ thuộc weaving/proxy model | Test nested method coverage |
| Multi-aspect overlap | Có thể nhận nhiều advice | Test precedence, event count |
| Async method | Method return khác task completion | Test completion boundary |

### 30.1. Positive test

Một method được đánh dấu trực tiếp tại đúng declaration và nằm trong weaving scope cần nhận advice.

### 30.2. Negative test

Một override không có annotation **không được coi là có method annotation tự động** nếu policy đã công bố chỉ chọn direct declaration.

### 30.3. Test semantics riêng của resolver

Nếu chính sách cố ý lấy annotation từ parent/interface, cần test resolver trả đúng policy, và test integration rằng **advice thực sự dùng policy đã resolve**.

### 30.4. Test class annotation vs method annotation

Không để một class-level `@Monitored` vô tình làm test method-level `@Audited` luôn pass. Tách mỗi trục với test case riêng.

### 30.5. Test runtime receiver vs static type

Có cùng một target object nhưng gọi qua typed interface và concrete class reference; xác nhận call/execution/interceptor có semantics nhất quán với contract, không phụ thuộc tình cờ vào reference khai báo.

## 31. Lỗi hiểu nhầm phổ biến

**“@Inherited nghĩa annotation được sao chép xuống mọi method của subclass.”** Sai. Quy tắc chỉ áp dụng cho annotations trên class declarations trong superclass chain.

**“Class implements annotated interface nên `Class.getAnnotation` trả annotation ấy.”** Sai theo Java `@Inherited`.

**“Method override tự kế thừa annotation từ method cha.”** Sai.

**“Method kế thừa không override thì annotation đã được copy vào class con.”** Sai. Reflection có thể trả chính `Method` được khai báo ở class cha.

**“Cùng một body thực thi thì nguồn metadata luôn giống nhau.”** Sai. Interface Method, Parent Method và Child Method là các declarations khác nhau.

**“getMethod và getDeclaredMethod tương đương.”** Sai, một bên tìm public inherited methods, bên kia tìm declared methods.

**“Method.getAnnotation luôn tìm annotation của overridden parent methods.”** Sai theo reflection Java mặc định.

**“@annotation, @within và @target chọn cùng một thứ.”** Sai. Subject/method, lexical type và runtime target là những khái niệm khác nhau.

**“Method call và method execution là cùng join point.”** Sai trong các mô hình phân biệt hai loại.

**“Java annotations tự thực thi advice.”** Sai. Cần cơ chế đọc metadata và thực thi interception.

**“Chỉ cần `RetentionPolicy.RUNTIME` là aspect chắc chắn chạy.”** Sai. Retention chỉ giúp metadata có thể được đọc, không đảm bảo weaving/proxy coverage.

**“Meta-annotation tự lan qua annotation type khác như alias.”** Sai, trừ khi resolver/tool có quy tắc riêng.

**“Constructor annotation kế thừa từ constructor cha.”** Sai.

**“Annotation trên parameter chính là annotation trên method.”** Sai.

**“Không có advice log nghĩa method chưa chạy.”** Sai khi bypass, không match hoặc log sink lỗi.

**“Một unit test reflection pass chứng minh pointcut production pass.”** Sai. Cần kiểm actual join points và deployment.

## 32. Bài tập có lời giải

### Bài 1 — Class inheritance

`@Monitored` được khai báo `@Inherited` trên `Parent`. `Child extends Parent` nhưng không có annotation trực tiếp. `Child.class.isAnnotationPresent(Monitored.class)` là gì?

**Đáp án:** `true` theo Java class-level inheritance, nếu annotation retention cho phép reflection và không có điều kiện khác che/đổi kết quả.

### Bài 2 — Interface inheritance

`@Monitored interface Task` và `class TaskImpl implements Task`. `TaskImpl.class.getAnnotation(Monitored.class)` là gì?

**Đáp án:** `null` theo Java default annotation inheritance; implements interface không mang annotation ấy xuống class.

### Bài 3 — Override method

`Parent.process` có `@Audited`, `Child.process` override không annotate. `Child.class.getDeclaredMethod("process").isAnnotationPresent(Audited.class)`?

**Đáp án:** `false`. Method override là declaration mới.

### Bài 4 — Inherited method

`Child` không override `Parent.inherited`. `Child.class.getMethod("inherited").getDeclaringClass()` là gì?

**Đáp án:** `Parent.class` nếu đó là public inherited method được tìm thấy và không có declaration tương ứng ở Child.

### Bài 5 — Reflection dispatch

Một `Method` object đại diện cho `Parent.process` được invoke trên instance `Child` có override. Body nào chạy?

**Đáp án:** Override `Child.process` cho virtual instance method thông thường, dù `Method` object trỏ declaration của Parent. Điều đó không thay annotation được trả từ `Method`.

### Bài 6 — Interface method

Annotation có trên `Task.apply` nhưng không có trên `TaskImpl.apply`. Nếu interceptor kiểm Method từ interface, kết quả có thể khác interceptor kiểm Method từ implementation không?

**Đáp án:** Có. Hai declarations mang metadata khác nhau; cần contract resolver rõ.

### Bài 7 — Retention

`@Audited` không khai báo `@Retention`. Reflection runtime có chắc đọc được annotation đó không?

**Đáp án:** Không. Default retention là `CLASS`, nên runtime reflection annotation thông thường không nhìn thấy nó.

### Bài 8 — `@within`

Method `helper` không annotated, nhưng nằm trong class được annotate. `@within` có giống `@annotation` trên `helper` không?

**Đáp án:** Không. Một tiêu chí dựa trên lexical type, tiêu chí kia dựa trên subject annotation.

### Bài 9 — `@withincode`

Call tới `helper` nằm trong body của `process` được annotate. Có thể match `@withincode(Audited)` dù `helper` không annotated không?

**Đáp án:** Có thể trong AspectJ với join-point kind/cú pháp phù hợp, vì điều kiện xét method **chứa call site**, không phải callee.

### Bài 10 — Policy kế thừa thông qua interface

Ứng dụng muốn mọi implementation của interface có annotated method đều được audit, dù implementation override không annotate. Có dùng `@Inherited` một mình đủ không?

**Đáp án:** Không. Cần chọn theo interface contract hoặc resolver duyệt interface methods, và test thực tế interception boundary.

### Bài 11 — Repeatable annotation

Một type có nhiều annotations cùng kiểu repeatable. Dùng `getAnnotation(A.class)` có đủ lấy toàn bộ không?

**Đáp án:** Không. Dùng `getAnnotationsByType(A.class)` khi cần diễn giải các annotations repeatable được associated với element.

### Bài 12 — Proxy bypass

Annotation lookup trả true nhưng caller gọi raw target ngoài proxy. Advice có chắc chạy không?

**Đáp án:** Không. Metadata và interception coverage là hai bước khác nhau.

## 33. Quy trình thiết kế annotation-based aspect có thể kiểm chứng

1. **Chốt ý nghĩa annotation:** đánh dấu type, method, parameter, field hay type use?
2. **Chốt retention:** engine đọc metadata lúc compile, load hay runtime?
3. **Chốt selection:** chọn join-point kind call hay execution hoặc loại khác?
4. **Chốt declaration precedence:** concrete override, parent method, interface, type-level metadata.
5. **Xác định @Inherited có liên quan không:** chỉ cho class-level annotation theo Java default.
6. **Chốt cách xử lý subclass override:** annotation trực tiếp bắt buộc hay tìm ancestor methods?
7. **Chốt interfaces:** có dò implementation contracts từ interfaces không?
8. **Định nghĩa conflict policy:** nhiều interfaces/annotations khác giá trị thì sao?
9. **Xem xét generics/bridge/default methods** nếu API có chúng.
10. **Xem xét annotation repeatable và type-use** nếu business policy dùng.
11. **Phân biệt static call site với runtime receiver và executed body**.
12. **Kiểm tra weaving/proxy boundaries** trên đúng module/artifact.
13. **Viết positive/negative tests** cho declaration/inheritance/override.
14. **Viết test actual advice fire**, không chỉ reflection.
15. **Viết test nhiều aspect cùng match** để không double count hoặc đổi precedence bất ngờ.
16. **Kiểm tra logger/helper exclusions** nếu pointcut rộng.
17. **Kiểm tra lỗi/cleanup/async** theo contract advice.
18. **Công bố scope và giới hạn** trong tài liệu cho consumer.

## 34. Checklist ghi nhớ

- [ ] Annotation là metadata, tự nó không chạy.
- [ ] `@Target` và `@Retention` giải quyết hai câu hỏi khác nhau.
- [ ] Default retention là CLASS nếu không khai báo.
- [ ] `@Inherited` tác động lên class-level annotation trong superclass chain.
- [ ] Interface annotation không tự lan sang implementation class qua `@Inherited`.
- [ ] Method annotations không tự kế thừa qua override.
- [ ] Method được thừa kế không override có thể vẫn là declaration ở superclass.
- [ ] `Method.getDeclaringClass` cho biết nơi method khai báo.
- [ ] `getMethod` khác `getDeclaredMethod`.
- [ ] `getAnnotation` khác `getDeclaredAnnotation`.
- [ ] Interface Method và implementation Method không đồng nhất metadata.
- [ ] Dynamic dispatch không sao chép annotation giữa declarations.
- [ ] Call join point khác execution join point khi công cụ hỗ trợ.
- [ ] `@annotation` khác `@within`, `@target` và `@withincode`.
- [ ] Một type-level annotation không làm mọi method tự có method annotation.
- [ ] Annotation repeatable có quy tắc container và lookup riêng.
- [ ] Annotation trên parameter/type use phải đọc theo API/designator phù hợp.
- [ ] Generic bridge/synthetic methods cần được kiểm tra khi resolver dùng reflection.
- [ ] Cấu hình inheritance/alias riêng của một công cụ không phải Java default.
- [ ] Annotated element phù hợp không bảo đảm class được weave.
- [ ] Có test direct target/proxy/self-invocation nếu hệ thống dùng proxy.
- [ ] Có test cả metadata matching lẫn actual advice behavior.
- [ ] Không dùng annotation-based matcher đơn lẻ làm security boundary khi còn đường bypass.
- [ ] Mọi thay đổi resolver/pointcut được đánh giá backward compatibility.

## 35. Tài liệu đối chiếu

Những nguồn sau được dùng để tách **quy tắc Java** khỏi **quy tắc của một AOP pointcut language cụ thể**:

- [Java 17 JLS — Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): `@Inherited`, `@Retention`, `@Target`, `@Repeatable` và vị trí annotation declaration.
- [Java 17 — `Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): phạm vi của class-level annotation inheritance.
- [Java 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): direct/indirect/present/associated annotations và những phương thức lookup.
- [Java 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getMethod`, `getDeclaredMethod` và class annotation reflection.
- [Java 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): declaring class, method reflection và invocation.
- [Eclipse AspectJ — Annotations and Pointcuts](https://eclipse.dev/aspectj/doc/latest/adk15notebook/annotations.html): annotation inheritance, `@annotation`, `@within`, `@target`, `@withincode`, parameter annotations và pointcut matching.
- [Eclipse AspectJ — Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): khác biệt giữa call và execution join points, signature patterns, pointcuts và advice.

Khi triển khai thật, nên đối chiếu **JDK, AOP compiler/weaver, class loader và deployment** đang dùng; không suy semantics của một công cụ sang tất cả.

## 36. Kết luận

**Kế thừa annotation** và **kế thừa/override method** là những cơ chế khác nhau trong Java. `@Inherited` chỉ giải quyết annotation trên class qua superclass hierarchy; nó không sao chép annotations trên overridden methods hoặc từ interface sang class implementation.

Đối với AOP, cần thêm một phân biệt quan trọng: **metadata của declaration được quan sát không nhất thiết thuộc body thực thi cuối cùng**. Call-site static type, reflective `Method`, runtime receiver và method execution subject có thể chỉ những vị trí khác nhau trong type system.

Do đó, thiết kế annotation-based aspect đúng không chỉ hỏi “đặt `@Audited` ở đâu?”, mà phải nêu rõ **pointcut chọn join-point kind nào, đọc metadata từ declaration nào, có quy tắc kế thừa tùy chỉnh nào, và runtime có thực sự đi qua interception boundary hay không**.

Viết test cho **class-level inheritance**, **override không kế thừa**, **inherited method**, **interface/implementation declarations**, **call/execution khác nhau** và **actual advice fire** là cách biến một quy tắc annotation tưởng như đơn giản thành hợp đồng AOP đáng tin cậy.
