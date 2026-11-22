# @Inherited chỉ áp dụng theo các quy tắc kế thừa annotation của lớp trong Java Reflection

Trong Java, **@Inherited** là một *meta-annotation* thuộc gói **java.lang.annotation**, được đặt trên **khai báo annotation type** để cho phép Reflection nhìn thấy annotation đó trên **lớp con** khi annotation được khai báo trên **lớp cha**. Tuy nhiên, phạm vi kế thừa của @Inherited hẹp hơn trực giác: nó áp dụng cho **annotation trên khai báo class** khi tra cứu theo **chuỗi superclass**, không tự truyền annotation từ interface, không truyền annotation của method/field sang method/field có cùng tên ở subclass, và không tạo bản sao annotation thực sự trong class file của lớp con.

Ví dụ: nếu annotation type **@Category** được đánh dấu @Inherited, class Base có @Category("service") và class Child extends Base chưa khai báo @Category, thì **Child.class.getAnnotation(Category.class)** tìm thấy annotation từ Base. Nhưng **Child.class.getDeclaredAnnotation(Category.class)** trả null, vì Child không trực tiếp khai báo @Category.

Để hiểu đúng hành vi Reflection, cần phân biệt ba thứ: **annotation được khai báo ở đâu**, **annotation type có @Inherited và @Retention(RUNTIME) hay không**, và **API tra cứu có xét annotation kế thừa không**.

## 1. Khai báo annotation kế thừa đúng cách

Ví dụ khai báo annotation dành cho class:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}
~~~

Ý nghĩa từng meta-annotation:

- **@Inherited**: cho phép truy vấn annotation trên class con đi ngược chuỗi superclass nếu class hiện tại không trực tiếp có annotation cùng type.
- **@Retention(RetentionPolicy.RUNTIME)**: giữ annotation để Reflection đọc ở runtime. Nếu không khai báo @Retention, giá trị mặc định là CLASS; annotation có thể nằm trong class file nhưng không được Reflection cung cấp qua các API runtime thông thường.
- **@Target(ElementType.TYPE)**: cho phép annotation xuất hiện trên khai báo type, gồm class và interface. Điều này không có nghĩa annotation trên interface sẽ được kế thừa sang class triển khai.
- **@interface Category**: khai báo một *annotation interface*, còn từ khóa @Inherited là chú thích trên chính annotation interface đó, không phải trên class Base.

Sử dụng:

~~~java
@Category("service")
class Base {}

class Child extends Base {}
~~~

Các truy vấn sau có ý nghĩa khác nhau:

~~~java
Category inherited = Child.class.getAnnotation(Category.class);         // từ Base
Category direct = Child.class.getDeclaredAnnotation(Category.class);   // null
~~~

Hai đoạn mã này là các phần minh họa, cần đặt chung trong một chương trình hoặc cùng package có khai báo Category, Base và Child.

**Không có sự sao chép annotation vào Child.** @Inherited tác động lên quy tắc *tra cứu* trong Reflection, không thay đổi cấu trúc class, method, field hoặc mã bytecode đã biên dịch của subclass.

## 2. Quy tắc kế thừa chỉ đi qua superclass của class

Đối với một annotation type A có @Inherited và được giữ ở runtime, khi gọi **SomeClass.class.getAnnotation(A.class)**, quy tắc khái quát là:

1. Nếu class đang xét có annotation A trực tiếp, trả A của chính class đó.
2. Nếu không có A trực tiếp, kiểm tra **superclass** gần nhất.
3. Tiếp tục đi lên các superclass cho đến khi tìm thấy A phù hợp hoặc hết chuỗi superclass (đến Object).
4. Nếu không tìm được, trả **null**.

Quy tắc này **chỉ dành cho annotation của class declaration**. Nó không duyệt các implemented interfaces hay các superinterfaces.

Ví dụ:

~~~text
@Category("root") Base
                  │
                Middle
                  │
                Leaf

Leaf.class.getAnnotation(Category.class) -> Category("root")
~~~

Nếu Middle khai báo **@Category("middle")**, thì Leaf sẽ nhìn thấy **"middle"** vì đây là annotation gần Leaf hơn. Nếu Leaf tự khai báo **@Category("leaf")**, kết quả của Leaf là **"leaf"**. Một annotation trực tiếp của cùng type trên subclass **che** annotation cùng type kế thừa, chứ Java không cộng gộp cả hai.

### Interface và implements không tạo kế thừa @Inherited

~~~java
@Category("contract")
interface Contract {}

class ContractImpl implements Contract {}
~~~

Mặc dù Category có @Inherited, **ContractImpl.class.getAnnotation(Category.class)** trả null. Thậm chí khi một interface con extends interface cha, @Inherited **không** biến annotation trên superinterface thành annotation kế thừa trên subinterface.

Lý do là @Inherited được định nghĩa cho truy vấn trên **khai báo class** theo **superclass chain**. Quan hệ implements/extends giữa interfaces không tạo đường tra cứu này.

Một framework có thể chủ động quét interfaces hoặc meta-annotations theo quy tắc riêng, nhưng đó là tính năng của **framework**, không phải hành vi mặc định của Class.getAnnotation trong Java core.

### Nested class không tự kế thừa annotation của enclosing class

~~~java
@Category("outer")
class Outer {
    static class Nested {}
}
~~~

Nested nằm trong Outer về mặt khai báo, nhưng không **extends Outer**. Vì thế Nested.class.getAnnotation(Category.class) không nhận "outer" chỉ nhờ quan hệ lồng nhau. **Kế thừa class** và **lồng class** là hai quan hệ khác nhau.

## 3. API Reflection: getAnnotation và getDeclaredAnnotation

Interface **AnnotatedElement** cung cấp API chung để đọc annotation trên Class, Method, Field, Constructor, Parameter và các loại reflective element khác. Nhưng hành vi kế thừa phụ thuộc **loại element đang truy vấn**.

| API | Tìm annotation trực tiếp? | Có thể thấy annotation kế thừa từ superclass? | Ghi chú |
| --- | --- | --- | --- |
| **Class.getAnnotation(A.class)** | Có | Có, nếu A có @Inherited | Trả A hoặc null |
| **Class.isAnnotationPresent(A.class)** | Có | Có, nếu A có @Inherited | Tương đương getAnnotation(A.class) != null |
| **Class.getAnnotations()** | Có | Có, với type inheritable theo quy tắc present | Trả Annotation[] |
| **Class.getDeclaredAnnotation(A.class)** | Có | **Không** | Chỉ annotation trực tiếp |
| **Class.getDeclaredAnnotations()** | Có | **Không** | Không duyệt superclass |
| **Class.getAnnotationsByType(A.class)** | Có | Có theo quy tắc **associated**, kể cả @Repeatable | Trả A[] |
| **Class.getDeclaredAnnotationsByType(A.class)** | Có | **Không** | Mở container @Repeatable nhưng không kế thừa |
| **Method/Field/Constructor.getAnnotation(A.class)** | Có | **Không theo @Inherited** | Annotation trên thành viên không được chuyển sang thành viên khác |

Một số thuật ngữ trong Javadoc AnnotatedElement:

- **Directly present (trực tiếp)**: annotation type A được biểu diễn trực tiếp trên element trong thuộc tính runtime annotation tương ứng.
- **Indirectly present (gián tiếp)**: annotation A là một phần tử bên trong **container annotation** của @Repeatable trên element.
- **Present**: trực tiếp hiện diện hoặc được tìm theo superclass khi A inheritable và element là class.
- **Associated**: trực tiếp/gián tiếp hiện diện, hoặc được tìm theo superclass nếu A inheritable và class hiện tại không có A trực tiếp/gián tiếp.

Phân biệt *present* và *associated* đặc biệt quan trọng với **annotation lặp**: getAnnotation/getAnnotations dùng quan hệ *present*, còn getAnnotationsByType dùng quan hệ *associated*.

### Ví dụ ngắn phân biệt declared và inherited

~~~java
@Category("base")
class Base {}

class Child extends Base {}

boolean visible = Child.class.isAnnotationPresent(Category.class);       // true
boolean own = Child.class.getDeclaredAnnotation(Category.class) != null; // false
~~~

Child có thể “thấy” Category khi được hỏi qua getAnnotation nhưng không **khai báo** Category. Đây không phải lỗi, mà là hai chế độ tra cứu khác nhau.

## 4. Đừng nhầm kế thừa thành viên với kế thừa annotation

`@Inherited` chỉ điều chỉnh annotation trên **khai báo class**, kể cả khi annotation type có `@Target(METHOD)`. `Child.class.getDeclaredMethod("run").getAnnotation(Audited.class)` là `null` nếu `Child.run()` override `Base.run()` nhưng chính `Child.run()` không được đánh dấu `@Audited`.

Ngược lại, nếu `Child` **không override**, `Child.class.getMethod("run")` có thể trả chính `Method` do `Base` khai báo. Khi đó `method.getDeclaringClass() == Base.class`, và annotation của `Base.run()` vẫn có mặt **trên method gốc**. Field công khai được kế thừa hoạt động tương tự khi Reflection trả `Field` của superclass; field bị hide là khai báo mới. Constructor không được kế thừa, parameter và type-use annotation cũng không tự truyền. Bài interface/method đi sâu vào cách duyệt override và interface khi framework muốn tự tìm.

## 5. Ví dụ Java 17+ chạy hoàn chỉnh

Ví dụ duy nhất này minh họa cùng lúc: class annotation kế thừa qua superclass; annotation không có @Inherited; annotation trên interface; annotation của method override; và @Repeatable có @Inherited.

Lưu toàn bộ thành file **InheritedLessonDemo.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;

public class InheritedLessonDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Inherited
    @interface Feature { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Local { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @Inherited
    @interface Audited {}

    @Feature("base")
    @Local("base-only")
    static class Base {
        @Audited public void execute() {}
    }
    static class Child extends Base {}
    @Feature("child")
    static class TaggedChild extends Base {}

    @Feature("interface")
    interface Service {}
    static class ServiceImpl implements Service {}

    static class OverrideChild extends Base {
        @Override public void execute() {}
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Inherited
    @Repeatable(Roles.class)
    @interface Role { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Inherited
    @interface Roles { Role[] value(); }

    @Role("reader") @Role("writer")
    static class RoleBase {}
    static class RoleChild extends RoleBase {}
    @Role("admin")
    static class RoleOwn extends RoleBase {}

    public static void main(String[] args) throws Exception {
        System.out.println("inherited feature=" + Child.class.getAnnotation(Feature.class).value());
        System.out.println("declared feature=" + (Child.class.getDeclaredAnnotation(Feature.class) != null));
        System.out.println("noninherited local=" + (Child.class.getAnnotation(Local.class) != null));
        System.out.println("override annotation=" + TaggedChild.class.getAnnotation(Feature.class).value());
        System.out.println("interface annotation inherited=" + (ServiceImpl.class.getAnnotation(Feature.class) != null));

        Method overridden = OverrideChild.class.getDeclaredMethod("execute");
        Method unchanged = Child.class.getMethod("execute");
        System.out.println("overridden method annotated=" + overridden.isAnnotationPresent(Audited.class));
        System.out.println("inherited method annotated=" + unchanged.isAnnotationPresent(Audited.class));
        System.out.println("method declaring=" + unchanged.getDeclaringClass().getSimpleName());

        System.out.println("repeatable inherited=" + RoleChild.class.getAnnotationsByType(Role.class).length);
        System.out.println("repeatable declared=" + RoleChild.class.getDeclaredAnnotationsByType(Role.class).length);
        System.out.println("repeatable getAnnotation null=" + (RoleChild.class.getAnnotation(Role.class) == null));
        System.out.println("repeatable local overrides=" + RoleOwn.class.getAnnotationsByType(Role.class)[0].value());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 InheritedLessonDemo.java
java InheritedLessonDemo
~~~

Stdout đã được đối chiếu khi biên dịch bằng **javac --release 17** và chạy trên JDK 24:

~~~text
inherited feature=base
declared feature=false
noninherited local=false
override annotation=child
interface annotation inherited=false
overridden method annotated=false
inherited method annotated=true
method declaring=Base
repeatable inherited=2
repeatable declared=0
repeatable getAnnotation null=true
repeatable local overrides=admin
~~~

Đọc kết quả:

1. **inherited feature=base**: Child không có @Feature trực tiếp nên Class.getAnnotation đi lên Base để tìm @Feature("base").
2. **declared feature=false**: Class.getDeclaredAnnotation chỉ hỏi annotation trực tiếp trên Child.
3. **noninherited local=false**: @Local có runtime retention nhưng thiếu @Inherited, vì vậy không được Class.getAnnotation của Child tìm qua superclass.
4. **override annotation=child**: TaggedChild tự khai báo @Feature("child"), annotation trực tiếp gần nhất thắng @Feature("base") của Base.
5. **interface annotation inherited=false**: ServiceImpl implements Service nhưng không nhận @Feature trên Service.
6. **overridden method annotated=false**: method execute được OverrideChild override không nhận @Audited, dù @Audited type có @Inherited.
7. **inherited method annotated=true** và **method declaring=Base**: Child không override, getMethod trả Method gốc do Base khai báo, nên annotation gốc vẫn hiện diện.
8. **repeatable inherited=2**: RoleChild không khai báo Role, nên getAnnotationsByType tìm hai annotation Role ở superclass và mở container Roles.
9. **repeatable declared=0**: Không có Role trực tiếp/gián tiếp trong khai báo RoleChild.
10. **repeatable getAnnotation null=true**: trên RoleBase có hai @Role được compiler biểu diễn dưới **container @Roles**, vì thế getAnnotation(Role.class) không tự mở container để tìm phần tử Role. Dùng getAnnotationsByType(Role.class).
11. **repeatable local overrides=admin**: RoleOwn khai báo một Role riêng nên getAnnotationsByType(Role.class) lấy local Role("admin") và không cộng gộp hai Role ở superclass.

### Thử đổi annotation type

Trong chương trình trên, bỏ **@Inherited** khỏi @Feature rồi biên dịch lại. Khi đó Child.class.getAnnotation(Feature.class) sẽ trả null, vì @Feature không còn inheritable; dòng gọi .value() trực tiếp sẽ gây **NullPointerException**. Để thử nghiệm an toàn, hãy sửa dòng in thành kiểm tra null trước khi đọc value.

Tương tự, đổi RetentionPolicy.RUNTIME của Feature thành RetentionPolicy.CLASS thì các truy vấn runtime thông thường sẽ không còn tìm được @Feature dù vẫn giữ @Inherited: cả **retention** và **inheritance lookup** đều phải phù hợp.

## 6. @Inherited kết hợp @Repeatable: cần nhìn container

Từ Java 8, annotation type có thể được đánh dấu **@Repeatable(Container.class)** để xuất hiện nhiều lần trên cùng element. Khi dùng cả @Inherited, phải hiểu **base annotation** và **container annotation**.

Khai báo mẫu đúng:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Roles {
    Role[] value();
}
~~~

Nếu **Role** có @Inherited, **container Roles cũng phải có @Inherited** theo quy tắc JLS về containing annotation type; nếu container không có, compiler từ chối định nghĩa @Repeatable không hợp lệ.

Với:

~~~java
@Role("reader")
@Role("writer")
class Parent {}

class Child extends Parent {}
~~~

Compiler biểu diễn hai @Role trên Parent dưới một **container @Roles**. Khi đọc annotation cần quan tâm:

| Phương thức trên Child.class | Kết quả điển hình |
| --- | --- |
| **getAnnotationsByType(Role.class)** | Mảng hai Role ("reader", "writer") kế thừa theo quy tắc associated |
| **getDeclaredAnnotationsByType(Role.class)** | Mảng rỗng vì Child không trực tiếp khai báo Role |
| **getAnnotation(Role.class)** | null trong trường hợp Parent có hai Role được chứa bởi Roles |
| **getAnnotation(Roles.class)** | Có thể tìm container Roles được kế thừa |
| **getDeclaredAnnotation(Roles.class)** | null nếu Child không khai báo container Roles |

**Không đồng nhất getAnnotation(Role.class) với getAnnotationsByType(Role.class)**. Hàm thứ nhất chỉ tra một annotation *present* theo mô hình AnnotatedElement, còn hàm thứ hai có thể **mở container** và xử lý nhiều annotation liên quan (associated).

Với một @Role("admin") trực tiếp trên Child, getAnnotationsByType(Role.class) trả một Role trực tiếp của Child; nó không nối tiếp các Role inherited của Parent. Kế thừa annotation không tự gộp tất cả giá trị dọc cây class.

Một framework dùng annotation có thể thiết kế cơ chế merge riêng, nhưng nếu chỉ muốn hành vi Java chuẩn, hãy để getAnnotationsByType xử lý các annotation lặp và kế thừa, thay vì viết vòng quét tự động cộng dồn superclass.

## 7. Ranh giới của `@Inherited`

| Tình huống | `@Inherited` tự áp dụng? |
| --- | --- |
| `class Child extends Parent` với annotation trên `Parent` | Có, nếu annotation runtime và Child không có annotation cùng type. |
| `class Impl implements Interface` hoặc `SubInterface extends Interface` | Không, vì không phải superclass chain của class. |
| Method override, field hiding, constructor, formal parameter | Không; mỗi declaration có metadata riêng. |
| Nested class trong enclosing class, package/module annotation, type-use | Không; quan hệ lồng nhau/vị trí kiểu khác kế thừa lớp. |
| Annotation gắn lên một annotation type khác | Không; `Class.getAnnotation` không tự duyệt meta-annotation graph. |

Khi framework muốn mở rộng các đường tìm kiếm này, cần định nghĩa ưu tiên và xung đột, thay vì gán khả năng đó cho `@Inherited` của Java.

## 8. Ứng dụng thực tế khi quét annotation runtime

Giả sử một framework quét các class để tìm cấu hình kế thừa:

- **Nếu annotation có @Inherited và thiết kế yêu cầu kế thừa cấu hình từ class cha**: dùng Class.getAnnotation(A.class) hoặc Class.getAnnotationsByType(A.class) với annotation repeatable.
- **Nếu chỉ muốn biết cấu hình được ghi trực tiếp trên class**: dùng Class.getDeclaredAnnotation(A.class) hoặc Class.getDeclaredAnnotationsByType(A.class).
- **Nếu framework cần đọc annotation trên interfaces**: chủ động dùng getInterfaces()/getGenericInterfaces() hoặc tiện ích xử lý phân cấp interface; @Inherited không tự giúp.
- **Nếu cần đọc annotation trên method override**: xác định method đang xét và khi thích hợp truy vết overridden declarations/superinterfaces với chính sách hợp nhất rõ ràng.
- **Nếu dùng composed/meta-annotations**: phải duyệt annotation types; Java Class.getAnnotation không làm sẵn việc này.
- **Nếu xử lý annotation lặp**: dùng getAnnotationsByType để mở container, tránh chỉ lấy getAnnotation.
- **Nếu annotation không có runtime retention**: Reflection không thể dựa vào Class.getAnnotation để tìm; xem lại cấu hình @Retention hoặc dùng phân tích bytecode nếu bài toán thực sự cần metadata CLASS.

Ví dụ viết một helper đơn giản cho class inheritance:

~~~java
static <A extends java.lang.annotation.Annotation> A inheritedOnClass(
        Class<?> type, Class<A> annotationType) {
    return type.getAnnotation(annotationType);
}
~~~

Đây là method fragment. Hàm này sử dụng chính cơ chế chuẩn của Reflection, **không** tự đi qua interfaces hoặc methods. Nếu annotationType không được đánh dấu @Inherited, kết quả chỉ là annotation trực tiếp của class (không tìm superclass theo @Inherited).

### Lưu ý khi framework cho annotation nhiều nguồn

Nếu muốn gộp cả superclass, interface và annotation trên method, cần định nghĩa một hợp đồng riêng: ưu tiên class hiện tại hay superclass, có merge nhiều cấu hình hay không, khi gặp hai interface khai báo khác nhau thì bên nào thắng, và có đọc meta-annotations không. Đừng gọi tất cả những cách gộp này là hành vi chuẩn của @Inherited.

Việc quét sâu cũng có rủi ro hiệu năng và thứ tự: cache kết quả theo class/annotation type khi dùng nhiều lần, xử lý chu trình trong graph meta-annotations, và định nghĩa quy tắc ưu tiên rõ ràng. Với quy tắc đơn giản theo superclass thì API Class.getAnnotation đã xử lý.

## 9. Các lỗi thường gặp

1. **Đánh dấu @Inherited trên annotation type rồi chờ method annotation tự kế thừa:** không đúng. Nó chỉ áp dụng cho class declaration.
2. **Cho rằng annotated interface làm class implements tự nhận annotation:** không đúng; Class.getAnnotation không tìm qua interfaces.
3. **Quên @Retention(RUNTIME):** annotation sẽ không xuất hiện qua Reflection runtime thông thường.
4. **Nhầm getDeclaredAnnotation với getAnnotation:** declared bỏ qua inherited annotation, kể cả annotation type có @Inherited.
5. **Nhầm getMethod("run") tìm được annotation là vì method override kế thừa annotation:** cần kiểm tra Method.getDeclaringClass(); có thể đó chính là method của superclass.
6. **Giả định @Inherited tự merge annotation cùng type từ nhiều cấp:** annotation trực tiếp của subclass che annotation inherited cùng type; với repeatable, getAnnotationsByType trả nhóm liên quan gần nhất theo quy tắc associated.
7. **Dùng getAnnotation để đọc annotation repeatable có nhiều giá trị:** có thể nhận null vì compiler lưu container. Dùng getAnnotationsByType.
8. **Quên @Inherited trên container của một repeatable inheritable annotation:** cấu hình @Repeatable như vậy không hợp lệ theo JLS.
9. **Cho rằng @Inherited quét các meta-annotations:** không đúng. Đây là logic framework hoặc scanner phải tự thực hiện.
10. **Coi mọi annotation về runtime đều giống nhau:** @Target, @Retention và loại element được truy vấn đều ảnh hưởng đến kết quả.

## 10. Bài tập tự kiểm tra

**Câu 1.** @Feature được khai báo @Inherited và @Retention(RUNTIME). Base có @Feature("A"), Child extends Base không khai báo annotation. Child.class.getAnnotation(Feature.class) là gì?

**Đáp án:** Feature("A"). Class.getDeclaredAnnotation(Feature.class) trên Child trả null.

**Câu 2.** Nếu Child có @Feature("B") thì getAnnotation ở Child trả A hay B?

**Đáp án:** B. Annotation trực tiếp tại Child ưu tiên hơn loại cùng type trên superclass.

**Câu 3.** Interface Contract có @Feature("I"), class Impl implements Contract. Impl.class.getAnnotation(Feature.class) có trả I không?

**Đáp án:** Không. @Inherited không đi qua implemented interfaces.

**Câu 4.** Base.run được đánh dấu annotation @Audited có @Inherited. Child override run nhưng không ghi @Audited. Child.class.getDeclaredMethod("run").isAnnotationPresent(Audited.class) trả gì?

**Đáp án:** false. @Inherited không truyền annotation của method override.

**Câu 5.** Nếu Child **không override** run và Child.class.getMethod("run") tìm thấy public method ở Base, annotation @Audited có thể được đọc không?

**Đáp án:** Có, vì Method được trả về thực sự là của Base. Kiểm tra Method.getDeclaringClass() để xác nhận; đây không phải annotation inheritance giữa hai Method.

**Câu 6.** Superclass có @Role("read") và @Role("write") với Role @Repeatable và @Inherited. Subclass không khai báo Role. Nên dùng API nào để lấy đủ hai giá trị?

**Đáp án:** Class.getAnnotationsByType(Role.class). Hàm này mở container Roles và xem xét quy tắc associated.

**Câu 7.** Annotation @Meta đánh dấu annotation type @Label. Class Sample có @Label nhưng không có @Meta. @Inherited trên Meta có làm Sample.class.getAnnotation(Meta.class) tự tìm được không?

**Đáp án:** Không. @Inherited không tự quét meta-annotations; cần một thuật toán quét annotation type riêng.

**Ghi nhớ:** **@Inherited chỉ thêm quy tắc tra cứu annotation runtime của khai báo class theo chuỗi superclass.** Luôn kiểm tra **@Retention(RUNTIME)**, phân biệt **getAnnotation** với **getDeclaredAnnotation**, không suy diễn sang interface/method/field/constructor, và dùng **getAnnotationsByType** cho repeatable annotations.

### Tài liệu tham khảo

- Java SE 17 — java.lang.annotation.Inherited: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html
- JLS 17 — §9.6.4.3 @Inherited và §9.6.3 Repeatable Annotation Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html
- Java SE 17 — java.lang.reflect.AnnotatedElement, các định nghĩa directly present/present/associated: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java SE 17 — java.lang.Class, getAnnotation/getAnnotationsByType/getDeclaredAnnotation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — java.lang.annotation.Repeatable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html
