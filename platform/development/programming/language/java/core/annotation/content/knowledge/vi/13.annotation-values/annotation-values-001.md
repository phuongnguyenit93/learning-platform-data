# annotationType() và kiểu thực của annotation trong Java

Khi đọc một annotation bằng reflection, ta nhận được **một đối tượng biểu diễn giá trị annotation**. Đối tượng này có thể được sử dụng để gọi các phần tử như **name()**, **value()** hoặc **version()**. Tuy nhiên, cần phân biệt:

1. **Annotation type được khai báo bằng @interface**, ví dụ **Route**.
2. **Annotation instance** được trả về khi đọc metadata, ví dụ từ **getAnnotation(Route.class)**.
3. **Lớp thực thi tại runtime của đối tượng đó** mà **getClass()** trả về. Trên các bản JDK phổ biến, nó là một lớp proxy nội bộ; tên và cách tạo không phải hợp đồng lập trình ổn định.

Phương thức **annotationType()** thuộc **java.lang.annotation.Annotation** và trả về **Class đại diện cho kiểu annotation được khai báo**, không trả về lớp proxy triển khai ở runtime.

Ví dụ ý chính:

~~~java
Route route = Service.class.getAnnotation(Route.class);

Class<? extends java.lang.annotation.Annotation> declaredType =
        route.annotationType();

Class<?> runtimeImplementation = route.getClass();
~~~

Trong đó **declaredType** đại diện cho kiểu **Route**; còn **runtimeImplementation** là class thực tế của đối tượng **route**. Hai đối tượng Class này không phải cùng một ý nghĩa. Phải kiểm tra **route != null** trước khi gọi **annotationType()**.

## 1. Annotation type: kiểu được định nghĩa bởi @interface

Một kiểu annotation được khai báo như sau:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Route {
    String path();
    int version() default 1;
}
~~~

**Route** là **annotation interface** theo cách gọi trong Java Language Specification; cú pháp định nghĩa của nó là **@interface**. Java xem annotation interface là một kiểu interface chuyên biệt, kế thừa ngầm **java.lang.annotation.Annotation**.

Các thuộc tính quan trọng:

- **Route.class** là một đối tượng **Class** đại diện cho định nghĩa kiểu Route.
- **Route.class.isAnnotation()** trả về **true**.
- **Route.class.isInterface()** cũng trả về **true**, vì một annotation type là một loại interface đặc biệt.
- **Route.class.getDeclaredMethods()** mô tả các phần tử đã khai báo như **path()** và **version()**.
- **Route.class.getDeclaredMethod("version").getDefaultValue()** trả về giá trị mặc định **1** (được đóng hộp thành Integer); nếu một phần tử không có default thì **getDefaultValue()** trả về **null**.
- **@Retention(RUNTIME)** là điều kiện quan trọng khi muốn truy xuất annotation từ class bằng reflection ở runtime. Không có nó, mặc định là **RetentionPolicy.CLASS**.

Annotation type **không phải một class nghiệp vụ thông thường**. Không dùng **new Route(...)** để tạo một đối tượng annotation. Mã Java gắn annotation dùng cú pháp **@Route(path = "...")**, còn các API reflection cung cấp đối tượng có thể đọc các phần tử annotation.

## 2. Annotation instance: giá trị thu được từ reflection

Sử dụng Route:

~~~java
@Route(path = "/users", version = 2)
class UserService {
}
~~~

Đọc:

~~~java
Route route =
        UserService.class.getAnnotation(Route.class);

if (route != null) {
    System.out.println(route.path());
    System.out.println(route.version());
}
~~~

**route** là một **giá trị annotation** có kiểu tĩnh **Route**. Các lời gọi **path()**, **version()** lấy element-value mà annotation biểu diễn.

Nếu class không được gắn Route và không có annotation Route inherited phù hợp, **getAnnotation(Route.class)** trả về **null**. Vì thế, không thể gọi **annotationType()** hoặc **path()** ngay trên kết quả mà không kiểm tra.

Nếu annotation hiện diện nhưng không ghi **version**, **route.version()** trả về giá trị **default 1**, chứ không phải null. Đây là hai tình huống khác nhau:

- **Thiếu toàn bộ annotation**: **getAnnotation(...) == null**.
- **Có annotation, thiếu một element-value tường minh**: phương thức phần tử nhận **default** nếu kiểu annotation khai báo default.

Java không tự kích hoạt routing khi class có **@Route**; annotation chỉ cung cấp metadata. Framework hoặc mã ứng dụng phải đọc và xử lý metadata để tạo hành vi.

## 3. annotationType() trả về gì?

Hợp đồng của interface **java.lang.annotation.Annotation** gồm:

~~~java
Class<? extends java.lang.annotation.Annotation> annotationType();
~~~

Phương thức này trả về đối tượng Class biểu diễn **annotation interface mà giá trị annotation thuộc về**.

Với:

~~~java
Route route =
        UserService.class.getAnnotation(Route.class);

if (route != null) {
    System.out.println(route.annotationType() == Route.class);
}
~~~

Kết quả là **true**. Không cần biết JDK đã tạo instance Route bằng cơ chế nội bộ nào.

Giá trị trả về có kiểu generic **Class<? extends Annotation>** vì phương thức ở interface Annotation phải hoạt động cho mọi annotation type. Đối tượng Class thực tế trong ví dụ là Class đại diện cho **Route**.

### annotationType() khác Route.class như thế nào?

- **Route.class** là một **class literal** được viết trực tiếp trong source để biểu diễn kiểu Route.
- **route.annotationType()** là kết quả truy vấn **kiểu annotation của đối tượng route** đang có.

Hai biểu thức có thể cùng tham chiếu **một đối tượng Class** khi đối tượng route thực sự là một giá trị Route. Sự khác biệt là **cách thu được thông tin kiểu**, không phải có hai định nghĩa kiểu Route.

Khi đã biết kiểu Route từ compile time và gọi **getAnnotation(Route.class)**, trả về Route có sẵn kiểu tĩnh **Route**, nên **annotationType()** thường không cần để xác định lại kiểu. Nó hữu ích hơn khi xử lý một tập **Annotation[]** gồm nhiều kiểu chưa biết trước tại lúc viết code.

## 4. annotationType() KHÔNG giống getClass()

**getClass()** là phương thức có ở mọi đối tượng Java từ **Object**. Với một annotation instance, nó cho biết lớp triển khai thực tế của instance đó tại runtime.

~~~java
Route route = UserService.class.getAnnotation(Route.class);

if (route != null) {
    Class<? extends java.lang.annotation.Annotation> annotationClass =
            route.annotationType();

    Class<?> runtimeClass = route.getClass();

    System.out.println(annotationClass == Route.class); // true
    System.out.println(runtimeClass == Route.class);    // false
}
~~~

**Vì sao false ở dòng cuối?** **Route** là một annotation interface; object **route** phải có một triển khai cụ thể để tồn tại tại runtime. Lớp triển khai không chính là interface Route.

Trên nhiều JVM/JDK, reflection hiện thực các annotation object bằng **dynamic proxy**, có thể có tên nội bộ mang dạng như **jdk.proxy...$Proxy...**. Nhưng:

- Tên class runtime **không ổn định** giữa bản JDK, môi trường module/class loader hoặc cách triển khai JVM.
- Không hardcode một tên proxy, không so sánh chuỗi tên proxy để suy ra annotation type.
- Không coi proxy class là kiểu annotation để truyền vào **getAnnotation(...)**.
- Không suy luận một annotation có hay không bằng việc soi vào tên class triển khai.

**Cách đúng để biết kiểu annotation** là **annotation.annotationType()**. Nếu muốn biết đối tượng có thực sự là một giá trị Route, có thể dùng **route instanceof Route**, **Route.class.isInstance(route)** hoặc kiểm tra **annotationType() == Route.class** trong tình huống cụ thể.

### So sánh nhanh

| Biểu thức | Ý nghĩa | Ví dụ kết quả |
| --- | --- | --- |
| **Route.class** | Kiểu annotation được khai báo | **demo.Route** |
| **route.annotationType()** | Kiểu annotation mà giá trị route biểu diễn | **demo.Route** |
| **route.getClass()** | Lớp triển khai của chính object route | Proxy/class triển khai do JVM/JDK chọn |
| **route.annotationType().isAnnotation()** | Kiểu khai báo có phải annotation interface không? | **true** |
| **route instanceof Route** | Object có tương thích kiểu Route không? | **true** |
| **Route.class.isInstance(route)** | Kiểm tra object theo Class đại diện cho Route | **true** |

**Không dùng getClass() == Route.class** để kiểm tra annotation object vì đây là phép so sánh với **interface**, không phải với class triển khai.

## 5. Ví dụ Java 17+ đầy đủ, biên dịch và chạy độc lập

Tạo tệp **src/demo/AnnotationTypeDemo.java**:

~~~java
package demo;

import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Route {
    String path();
    int version() default 1;
    String[] tags() default {};
}

@Route(path = "/users", tags = {"api", "public"})
class UserService {
}

@Route(path = "/users", tags = {"api", "public"})
class AnotherUserService {
}

class PlainService {
}

public class AnnotationTypeDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {

        Route first = UserService.class.getAnnotation(Route.class);
        Route second =
                AnotherUserService.class.getAnnotation(Route.class);

        System.out.println("annotation type="
                + first.annotationType().getName());
        System.out.println("type is annotation="
                + first.annotationType().isAnnotation());
        System.out.println("same declared type="
                + (first.annotationType() == Route.class));

        Class<?> runtimeClass = first.getClass();
        System.out.println("runtime equals annotation type="
                + (runtimeClass == Route.class));
        System.out.println("instance of Route="
                + (first instanceof Route));

        System.out.println("path=" + first.path());
        System.out.println("version=" + first.version());
        System.out.println("tags=" + Arrays.toString(first.tags()));

        System.out.println("same values=" + first.equals(second));
        System.out.println("same hash code="
                + (first.hashCode() == second.hashCode()));

        Method versionMethod =
                Route.class.getDeclaredMethod("version");
        System.out.println("declared default="
                + versionMethod.getDefaultValue());

        Route missing = PlainService.class.getAnnotation(Route.class);
        System.out.println("plain has route=" + (missing != null));

        Annotation[] annotations =
                UserService.class.getAnnotations();
        for (Annotation annotation : annotations) {
            System.out.println("from Annotation[]="
                    + annotation.annotationType().getSimpleName());
        }
    }
}
~~~

Biên dịch, chạy từ thư mục chứa **src**:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationTypeDemo.java
java -cp out demo.AnnotationTypeDemo
~~~

**Stdout dự kiến chính xác, không phụ thuộc tên proxy nội bộ:**

~~~text
annotation type=demo.Route
type is annotation=true
same declared type=true
runtime equals annotation type=false
instance of Route=true
path=/users
version=1
tags=[api, public]
same values=true
same hash code=true
declared default=1
plain has route=false
from Annotation[]=Route
~~~

### Phân tích chương trình

1. **UserService** có **@Route** trực tiếp và Route được giữ tới runtime; **getAnnotation(Route.class)** trả về một đối tượng Route khác null.
2. **first.annotationType().getName()** là **demo.Route**, tên đầy đủ của annotation type; không phải tên runtime proxy.
3. **isAnnotation()** cho true vì Route được khai báo bằng **@interface**.
4. **getClass() == Route.class** cho false vì Route.class là interface annotation còn **getClass()** chỉ class triển khai thực.
5. **path()** trả "/users"; **version()** trả 1 vì phần tử **version()** không được truyền tường minh và có **default 1**.
6. **tags()** trả **String[]**; **Arrays.toString(...)** in dạng **[api, public]**.
7. Hai class UserService và AnotherUserService sử dụng annotation Route với các giá trị element bằng nhau nên **equals()** trả true, và các object annotation bằng nhau phải có cùng **hashCode()**.
8. **Method.getDefaultValue()** kiểm tra phần tử **version()** trong định nghĩa kiểu Route và trả **1**, không cần biết annotation đang gắn lên class nào.
9. **PlainService** không được gắn Route nên **getAnnotation(Route.class)** trả null; chương trình kiểm tra null thay vì gọi method trên kết quả.
10. **getAnnotations()** trả về các annotation hiện diện trên UserService; vòng lặp dùng kiểu **Annotation** chung nên **annotationType()** cho biết từng annotation type khi duyệt một tập có khả năng chứa nhiều kiểu.

Ví dụ cố ý **không in runtimeClass.getName()** để tránh gắn kết quả bài học với tên lớp proxy không được Java cam kết ổn định.

## 6. Khi làm việc với Annotation[]: nhận diện kiểu và ép kiểu an toàn

Khi chưa biết trước mỗi phần tử của một mảng annotation mang kiểu gì, **annotationType()** đặc biệt hữu ích:

~~~java
import java.lang.annotation.Annotation;

for (Annotation a : UserService.class.getAnnotations()) {
    Class<? extends Annotation> type = a.annotationType();

    System.out.println("found: " + type.getName());

    if (type == Route.class) {
        Route route = Route.class.cast(a);
        System.out.println("path: " + route.path());
    }
}
~~~

Đoạn trên thuộc package demo và giả định đã có Route/UserService như ví dụ hoàn chỉnh.

Phép kiểm tra **type == Route.class** diễn đạt rõ rằng giá trị Annotation được hỏi thuộc **kiểu annotation Route**, chứ không phụ thuộc vào lớp triển khai nội bộ.

**Route.class.cast(a)** là phép ép kiểu có kiểm tra tại runtime. Sau khi xác định đúng kiểu, có thể gọi các element đặc thù như **path()** và **version()**.

Cách viết với **instanceof** cũng hợp lệ và thường ngắn hơn khi chỉ quan tâm một kiểu đã biết:

~~~java
for (Annotation a : UserService.class.getAnnotations()) {
    if (a instanceof Route route) {
        System.out.println(route.path());
    }
}
~~~

Đoạn này dùng **pattern matching for instanceof** được hỗ trợ trong Java 17. Khi cần làm việc với nhiều annotation type khác nhau, **annotationType()** cho phép truy cập Class để dùng các API phản chiếu theo kiểu.

**Không nên ép kiểu dựa vào getClass().getSimpleName()** hoặc dựa trên một chuỗi proxy-name. Những chi tiết triển khai đó không phải phần giao diện công khai của annotation type.

## 7. annotationType() và hợp đồng equals/hashCode của annotation

**java.lang.annotation.Annotation** quy định các giá trị annotation được so sánh theo **kiểu annotation và giá trị các phần tử**, không theo địa chỉ tham chiếu hay tên runtime proxy.

Ví dụ:

~~~java
@Route(path = "/health", version = 1)
class HealthA {
}

@Route(path = "/health")
class HealthB {
}
~~~

Khi đọc bằng cùng định nghĩa Route với **version() default 1**, hai annotation biểu diễn cùng kiểu và cùng các element-value hiệu lực nên **equals()** trả true:

~~~java
Route a = HealthA.class.getAnnotation(Route.class);
Route b = HealthB.class.getAnnotation(Route.class);

System.out.println(a.equals(b)); // true
~~~

Điều này thể hiện **giá trị mặc định của annotation element** cũng được dùng để xác định giá trị hiệu lực lúc đọc. Không nhất thiết hai annotation phải có cú pháp nguồn giống hệt nhau để bằng nhau.

Các nguyên tắc:

- Hai annotation không thể bằng nhau nếu chúng thuộc **hai annotation type khác nhau**.
- Hai annotation cùng type bằng nhau khi từng phần tử tương ứng có giá trị bằng nhau theo quy tắc annotation, kể cả **mảng** được so theo nội dung mảng.
- Nếu **a.equals(b)** là true thì **a.hashCode() == b.hashCode()** theo hợp đồng hashCode.
- **a == b** chỉ so sánh đồng nhất object; không phải phép kiểm tra giá trị annotation cần thiết.
- **a.getClass() == b.getClass()** không phải điều kiện bảo đảm các giá trị annotation bằng nhau hay cùng annotation type theo API.

**Không tự viết equals theo getClass() của annotation object.** Khi cần so sánh annotation values, dùng **equals()**; khi cần phân loại theo kiểu annotation, dùng **annotationType()**.

## 8. annotationType() không phải là Class của phần tử được chú thích

Chú ý hai Class khác nhau về mặt ngữ nghĩa:

~~~java
Route route = UserService.class.getAnnotation(Route.class);

Class<?> annotatedClass = UserService.class;
Class<? extends java.lang.annotation.Annotation> type =
        route.annotationType();
~~~

**annotatedClass** là class được **gắn annotation**; **type** là kiểu **của annotation**. Chúng không giống nhau.

Ví dụ:

- UserService.class có thể được gắn nhiều annotation, mỗi annotation có kiểu riêng.
- Một kiểu annotation Route có thể được dùng ở rất nhiều class; **annotationType()** trên mỗi giá trị Route đều cho **Route.class**.
- **Class.getAnnotation(Route.class)** hỏi liệu class UserService có annotation Route hay không.
- **Route.class.getAnnotation(...)** sẽ hỏi một annotation khác đang được gắn **trên chính khai báo kiểu Route**, ví dụ **@Retention**, **@Target**. Đây không phải câu hỏi về UserService.

Để kiểm tra một Class là annotation type:

~~~java
System.out.println(Route.class.isAnnotation());       // true
System.out.println(UserService.class.isAnnotation()); // false
~~~

Nếu có một **Class<?>** không rõ kiểu, kiểm tra **isAnnotation()** trước khi xử lý nó như một annotation type. Kiểu Java **Annotation.class** đại diện cho interface cơ sở, không phải một annotation interface do **@interface** định nghĩa để gắn trực tiếp trong mã nguồn.

## 9. Từ annotationType() truy cập metadata của chính annotation type

Khi đã có một Annotation instance, có thể truy vấn các meta-annotation trên type của nó:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

Annotation a = UserService.class.getAnnotation(Route.class);
if (a != null) {
    Class<? extends Annotation> type = a.annotationType();

    Retention retention = type.getAnnotation(Retention.class);
    Target target = type.getAnnotation(Target.class);

    if (retention != null) {
        RetentionPolicy policy = retention.value();
        System.out.println(policy); // RUNTIME, với Route của ví dụ
    }

    if (target != null) {
        System.out.println(
                java.util.Arrays.toString(target.value()));
        // [TYPE], với Route của ví dụ
    }
}
~~~

Ở đây, **Retention** và **Target** là những meta-annotation đặt trên **kiểu Route**. Truy vấn **type.getAnnotation(Retention.class)** là đang xem cấu hình của Route, không phải lấy Retention trực tiếp từ UserService.

Muốn liệt kê các phần tử do Route định nghĩa:

~~~java
Class<? extends Annotation> type = a.annotationType();

for (java.lang.reflect.Method element : type.getDeclaredMethods()) {
    System.out.println(element.getName()
            + " -> " + element.getReturnType().getTypeName());
}
~~~

Khi không cần thứ tự, vòng lặp này hợp lệ; **thứ tự các Method do reflection trả về không được Java bảo đảm**. Không nên viết bài kiểm tra dựa vào thứ tự cố định của getDeclaredMethods().

Có thể đọc **Method.getDefaultValue()** trên từng phần tử. Giá trị trả về có thể là null nếu phần tử không khai báo mặc định. Không được nhầm việc **element default == null** với việc **annotation không tồn tại**.

## 10. TYPE_USE, @Inherited và @Repeatable có làm đổi annotationType() không?

**Không.** Các cơ chế này ảnh hưởng tới **nơi annotation có thể xuất hiện hoặc cách truy xuất**, chứ không thay đổi kiểu được **annotationType()** trả về trên một giá trị annotation đã thu được.

### Annotation trên kiểu được sử dụng (TYPE_USE)

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {
}

class Example {
    @NonNull String name;
}
~~~

Để đọc annotation trên **kiểu String** của field:

~~~java
java.lang.reflect.Field field =
        Example.class.getDeclaredField("name");

NonNull nonNull =
        field.getAnnotatedType().getAnnotation(NonNull.class);

if (nonNull != null) {
    System.out.println(nonNull.annotationType() == NonNull.class);
    // true
}
~~~

Đoạn phản chiếu trên cần đặt trong một method có **throws NoSuchFieldException** hoặc xử lý ngoại lệ tương ứng. **Field.getAnnotation(NonNull.class)** không thay thế **Field.getAnnotatedType().getAnnotation(...)** vì ví dụ chỉ khai báo target TYPE_USE; hai API hỏi về hai vị trí metadata khác nhau.

### Annotation được tìm qua lớp cha (@Inherited)

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("backend")
class Parent {
}

class Child extends Parent {
}
~~~

Nếu khai báo import **java.lang.annotation.Inherited**, phương thức **Child.class.getAnnotation(Category.class)** có thể tìm Category từ Parent nhờ @Inherited. Khi có giá trị, **annotation.annotationType()** vẫn là **Category.class**. Nó không trở thành **Child.class** hoặc một “kiểu annotation kế thừa” khác.

**getDeclaredAnnotation(Category.class)** trên Child trả null vì Child không trực tiếp khai báo Category.

### Annotation lặp lại (@Repeatable)

~~~java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("fast")
@Tag("safe")
class Job {
}
~~~

Để lấy các annotation Tag đơn lẻ được lặp, dùng:

~~~java
Tag[] tags = Job.class.getAnnotationsByType(Tag.class);

for (Tag tag : tags) {
    System.out.println(tag.annotationType() == Tag.class); // true
}
~~~

Container annotation nếu được đọc riêng có kiểu **Tags**, không phải Tag:

~~~java
Tags container = Job.class.getAnnotation(Tags.class);
if (container != null) {
    System.out.println(container.annotationType() == Tags.class);
    // true
}
~~~

Không nhầm số lượng annotation được trả về với **kiểu annotation của từng instance**. Quy tắc repeatable có thể lưu một container cho nhiều giá trị Tag, nhưng **tag.annotationType()** vẫn xác định kiểu Tag cho từng giá trị tag.

## 11. Những giới hạn và lỗi thường gặp

| Lỗi hoặc nhận định | Vấn đề | Cách hiểu/khắc phục |
| --- | --- | --- |
| **annotation.getClass() == Route.class** được kỳ vọng true | getClass() là class triển khai, Route.class là annotation interface | Dùng **annotation.annotationType() == Route.class** |
| Lấy **annotation.getClass().getName()** làm định danh cấu hình | Tên lớp proxy/runtime là chi tiết triển khai | Dùng **annotation.annotationType().getName()** |
| Gọi **getAnnotation(...).annotationType()** ngay | getAnnotation có thể trả null | Kiểm tra đối tượng trước khi gọi |
| Dùng **new Route(...)** | Annotation type không được tạo trực tiếp bằng constructor như object thông thường | Gắn **@Route(...)** và đọc qua API thích hợp |
| So sánh annotation bằng toán tử **==** | So sánh identity thay vì element-value | Dùng **equals()** khi mục tiêu là so sánh giá trị |
| Dùng **getClass()** để cài equals tùy chỉnh cho annotation value | Lớp hiện thực không thuộc hợp đồng kiểu annotation | Dựa vào hợp đồng **Annotation.equals/hashCode** |
| Nhầm **Route.class** với **UserService.class** | Một bên là annotation type, một bên là class được chú thích | Đặt tên biến rõ ràng: annotationType và annotatedClass |
| Mong **getAnnotation** thấy một annotation không có runtime retention | Retention mặc định là CLASS | Thêm **@Retention(RUNTIME)** nếu cần đọc runtime |
| Dùng **Class.getAnnotation** để đọc TYPE_USE trên field | Truy vấn sai vị trí metadata | Dùng **Field.getAnnotatedType()** hoặc AnnotatedType thích hợp |
| Cho rằng **annotationType()** cho biết nơi annotation được gắn | Nó trả về type, không phải vị trí sử dụng | Giữ riêng thông tin reflection element/vị trí |
| Cho rằng default của element khiến annotation tự hiện diện | Default chỉ áp dụng khi annotation tồn tại | Kiểm tra **getAnnotation(...) != null** trước |
| Duyệt repeatable annotation chỉ bằng **getAnnotation(Tag.class)** | Có thể tồn tại container thay vì Tag trực tiếp | Dùng **getAnnotationsByType(Tag.class)** |

### Phân biệt getClass, instanceof và annotationType

Nếu bạn đã có một **Annotation a** chưa rõ loại:

~~~java
if (a instanceof Route route) {
    System.out.println(route.path());
}
~~~

Đây là cách diễn đạt Java 17 rõ ràng khi cần xử lý **một kiểu cụ thể**. Nếu chương trình cần lấy **Class của annotation type** để phân tích generic bằng reflection, dùng:

~~~java
Class<? extends java.lang.annotation.Annotation> type =
        a.annotationType();
~~~

Nếu cần tìm **lớp triển khai runtime để debug**, có thể dùng **a.getClass()**, nhưng không dựa vào chi tiết đó để ra quyết định nghiệp vụ.

## 12. Bài tập tự kiểm tra

**Bài 1.** Với:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Flag {
}

@Flag
class FeatureA {
}
~~~

Giả sử đã import **Retention** và **RetentionPolicy**. Lấy **Flag f = FeatureA.class.getAnnotation(Flag.class)**. Hãy so sánh:

- **f.annotationType() == Flag.class**: **true**.
- **f.getClass() == Flag.class**: **false** vì Flag.class là annotation interface, không phải lớp triển khai đối tượng.
- **f instanceof Flag**: **true**.
- **f.annotationType().isAnnotation()**: **true**.

**Bài 2.** Một class không gắn Flag. Lệnh **SomeClass.class.getAnnotation(Flag.class)** trả về gì nếu không có quan hệ kế thừa annotation phù hợp? **null**. Cần kiểm tra trước khi gọi **annotationType()**.

**Bài 3.** Hai class có **@Route(path = "/health")** và **@Route(path = "/health", version = 1)**. Nếu Route.version() có **default 1** và các phần tử còn lại bằng nhau, hai giá trị annotation có bằng nhau không? **Có**, vì các element-value hiệu lực bằng nhau.

**Bài 4.** Trong vòng lặp **for (Annotation a : clazz.getAnnotations())**, bạn cần ghi tên kiểu annotation. Chọn **a.annotationType().getName()** hay **a.getClass().getName()**? **Chọn annotationType().getName()**. getClass() cung cấp tên lớp triển khai có thể thay đổi.

**Bài 5.** Với **Tag[] tags = Job.class.getAnnotationsByType(Tag.class)**, **tags[0].annotationType()** có phải Tags.class không? **Không**, từng phần tử trong mảng là Tag, nên trả **Tag.class**; annotation chứa **Tags** (nếu truy vấn riêng) có **annotationType() == Tags.class**.

**Bài 6.** Muốn đọc giá trị default được khai báo trên element version() của Route, dùng phương thức nào? **Route.class.getDeclaredMethod("version").getDefaultValue()**. Phương thức này đọc default của định nghĩa type; không yêu cầu một Route instance cụ thể.

## 13. Tài liệu Java chính thức

- **Java SE 17 — Annotation:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html — hợp đồng **annotationType()**, **equals()**, **hashCode()** và **toString()** của các giá trị annotation.
- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — **getAnnotation(...)**, **getDeclaredAnnotation(...)**, **getAnnotationsByType(...)** và quy tắc truy xuất annotation.
- **Java SE 17 — Class:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — **isAnnotation()**, **isInstance(...)**, **getName()**, **getDeclaredMethods()**.
- **Java SE 17 — Method.getDefaultValue():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue() — lấy giá trị mặc định khai báo cho phần tử annotation.
- **Java Language Specification §9.6 — Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6 — định nghĩa annotation interface, các phần tử và hành vi ngôn ngữ liên quan.

Tóm lại: **annotationType() trả về annotation interface mà annotation value biểu diễn**. **getClass() trả về lớp triển khai của object runtime**, thường là proxy nhưng không ổn định để sử dụng như tên kiểu annotation. Khi lập trình reflection, dùng **annotationType()** để phân loại hoặc khám phá kiểu annotation, **equals()** để so sánh giá trị annotation, và luôn **kiểm tra null trước khi đọc** kết quả của getAnnotation(...).
