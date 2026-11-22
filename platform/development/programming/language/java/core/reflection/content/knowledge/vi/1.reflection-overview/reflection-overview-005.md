# Quan hệ giữa reflection, kế thừa, generic và annotation trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích **reflection nhìn thấy gì ở thời điểm chạy** khi một lớp có lớp cha, kiểu generic và annotation; chọn đúng API để đọc metadata; phân biệt metadata khai báo với hành vi thực khi gọi phương thức; và nhận diện các giới hạn thường gặp khi viết framework, thư viện hoặc công cụ phân tích mã Java.

Bốn khái niệm liên quan nhưng có vai trò khác nhau:

| Khái niệm | Vai trò trong chương trình | Reflection có thể quan sát |
| --- | --- | --- |
| **Kế thừa (inheritance)** | Tạo quan hệ lớp cha–con; thành viên có thể được thừa hưởng hoặc ghi đè | Cây kiểu, thành viên khai báo/truy cập được, lớp khai báo thành viên |
| **Generic** | Kiểm tra kiểu ở thời điểm biên dịch; mô tả kiểu tham số hóa | Kiểu đã bị xóa khi chạy và một phần thông tin khai báo generic được lưu trong metadata |
| **Annotation** | Gắn metadata có cấu trúc lên khai báo hoặc vị trí dùng kiểu | Annotation còn hiệu lực ở runtime, tùy `@Retention` và API truy vấn |
| **Reflection** | Đọc metadata và có thể thao tác động trên đối tượng/thành viên | Các đối tượng `Class`, `Method`, `Field`, `Constructor`, `Type`, `Annotation` |

**Điểm mấu chốt:** reflection không thay thế quy tắc kế thừa, không làm generic trở thành kiểm tra kiểu đầy đủ ở runtime, và không tự thực thi ý nghĩa nghiệp vụ của annotation. Nó chỉ cung cấp cơ chế quan sát hoặc gọi thành viên theo những quy tắc Java đã định nghĩa.

## 1. Kế thừa quyết định tập thành viên mà reflection có thể nhìn thấy

### 1.1. Hai nhóm API rất dễ nhầm

| Nhu cầu | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Lấy phương thức `public`, kể cả phương thức thừa hưởng | `clazz.getMethods()`, `clazz.getMethod(name, types...)` | Xét các phương thức `public` của kiểu đó và các phương thức `public` kế thừa từ lớp cha/interface |
| Lấy phương thức **khai báo trực tiếp** ở lớp đang xét | `clazz.getDeclaredMethods()`, `clazz.getDeclaredMethod(...)` | Bao gồm `private`, `protected`, package-private và `public`; không tự đi lên lớp cha |
| Lấy trường `public`, kể cả trường thừa hưởng | `clazz.getFields()`, `clazz.getField(name)` | Không bao gồm trường không `public` |
| Lấy trường khai báo trực tiếp | `clazz.getDeclaredFields()`, `clazz.getDeclaredField(name)` | Không tự tìm trường lớp cha |
| Lấy constructor | `clazz.getConstructors()` hoặc `clazz.getDeclaredConstructors()` | Chỉ constructor của chính lớp: **constructor không được kế thừa** |
| Xem quan hệ cha/interface | `getSuperclass()`, `getInterfaces()` | Trả về kiểu cha trực tiếp và các interface trực tiếp |
| Giữ thông tin generic của quan hệ cha | `getGenericSuperclass()`, `getGenericInterfaces()` | Trả về `Type`, có thể là `ParameterizedType` hoặc `Class` |

Ví dụ: nếu `Child extends Parent` và `Parent` có phương thức `public void ping()` thì `Child.class.getMethod("ping")` tìm được nó, nhưng `Child.class.getDeclaredMethod("ping")` sẽ ném `NoSuchMethodException` nếu `Child` không khai báo lại `ping`. Khi tìm metadata khai báo ở cả các lớp cha, hãy duyệt `getSuperclass()` và đọc `getDeclaredMethods()` theo từng cấp.

### 1.2. Ghi đè, che khuất và nơi khai báo là ba chuyện khác nhau

- **Override:** một phương thức instance phù hợp trong lớp con ghi đè phương thức lớp cha. Khi dùng `Method.invoke(object, args)` cho một phương thức instance, Java vẫn thực hiện **dispatch động** theo kiểu thực của đối tượng; `Method` lấy từ lớp cha vẫn có thể gọi phần triển khai override ở lớp con.
- **Overload:** cùng tên nhưng khác danh sách tham số; reflection yêu cầu **kiểu tham số chính xác** khi gọi `getMethod(name, parameterTypes...)`. Không thể chỉ dựa vào tên phương thức.
- **Field hiding:** trường cùng tên ở lớp con *che khuất* trường lớp cha, không dispatch đa hình như phương thức. `Field.getDeclaringClass()` cho biết đang đọc đúng trường nào.
- **Static method hiding:** phương thức `static` không override như phương thức instance; `Method.invoke` dùng phương thức static được khai báo, không dispatch động theo đối tượng.
- **Khả năng truy cập:** tìm thấy một `private` member không đồng nghĩa được phép đọc/gọi nó. `setAccessible(true)` hoặc `trySetAccessible()` phải tuân thủ kiểm tra truy cập và ranh giới module (JPMS).

Danh sách trả về từ `getMethods()` hoặc `getDeclaredMethods()` **không có thứ tự bảo đảm**. Nếu cần hiển thị ổn định hoặc sinh mã, hãy tự sắp xếp theo quy tắc rõ ràng.

## 2. Generic: còn metadata khai báo, nhưng kiểu tham số bị xóa phần lớn khi chạy

### 2.1. Type erasure tác động trực tiếp đến reflection

Trong Java, `List<String>` và `List<Integer>` thường cùng có raw runtime class `List`/`ArrayList`. Bạn không thể hỏi một đối tượng `new ArrayList<String>()` để lấy lại chắc chắn `String` chỉ từ `object.getClass()`. Compiler kiểm tra generic, chèn ép kiểu (cast) khi cần và xóa phần lớn thông tin tham số kiểu trong biểu diễn runtime.

Tuy nhiên, **khai báo** có thể giữ generic signature:

- `Field.getType()` trả về `Class<?>` của kiểu sau xóa, còn `Field.getGenericType()` trả về `Type` có thể chứa `List<String>`.
- `Method.getReturnType()` và `getParameterTypes()` cho các kiểu sau xóa; `getGenericReturnType()` và `getGenericParameterTypes()` trả về kiểu generic khai báo.
- `Class.getSuperclass()` trả về raw superclass, còn `Class.getGenericSuperclass()` có thể giữ quan hệ `Parent<String>`.
- `Class.getTypeParameters()` và `Method.getTypeParameters()` trả về các biến kiểu như `T`, `E` được khai báo ở lớp/phương thức.

Đừng đồng nhất `Type` với `Class<?>`. Các dạng quan trọng của `Type`:

| Dạng | Ví dụ khai báo | Ý nghĩa |
| --- | --- | --- |
| `Class<?>` | `String`, `int[]` | Kiểu cụ thể không tham số hóa trong biểu diễn đó |
| `ParameterizedType` | `List<String>` | Raw type cùng các đối số kiểu thực tế |
| `TypeVariable<?>` | `T` trong `class Box<T>` | Biến kiểu và các bound của nó |
| `WildcardType` | `? extends Number` | Wildcard và giới hạn trên/dưới |
| `GenericArrayType` | `T[]` | Kiểu mảng có thành phần là một generic type chưa thành `Class` cụ thể |

### 2.2. Generic ở lớp cha khác generic trên phương thức lớp cha

Giả sử `class Parent<T> { T read(); }` và `class Child extends Parent<String>`. Khi gọi `Child.class.getGenericSuperclass()`, metadata của *quan hệ extends* có thể chứa `String`. Nhưng `Parent.class.getDeclaredMethod("read").getGenericReturnType()` vẫn là biến kiểu `T` do `Parent` khai báo: reflection **không tự thay `T` bằng `String` trong metadata của chính `Parent`**.

Một công cụ cần suy luận kiểu trả về thực của `read` trong ngữ cảnh `Child` phải tự xây dựng ánh xạ `T -> String` rồi áp dụng ánh xạ qua từng cấp kế thừa (có thể qua nhiều lớp và interface). Với khai báo raw type hoặc thông tin generic không còn lưu, việc suy luận không phải lúc nào cũng thành công.

### 2.3. Bridge method là điểm giao giữa kế thừa và erasure

Để bảo toàn tính override khi signature bị xóa, compiler có thể sinh **bridge method**. Chẳng hạn, `Parent<T>.convert(T)` có tham số erasure là `Object`, còn `Child extends Parent<String>` override bằng `convert(String)`. Compiler tạo một bridge như `convert(Object)` trong `Child` để lời gọi qua kiểu `Parent` vẫn đến phần triển khai `convert(String)`.

Reflection có thể thấy cả phương thức nguồn và bridge trong `getDeclaredMethods()`. Khi quét phương thức để dựng API, routing, logging hoặc validation, thường cần kiểm tra `Method.isBridge()` và `Method.isSynthetic()` nhằm tránh đăng ký trùng. Nhưng khi gọi phương thức, không nên xóa/sửa bridge: nó phục vụ tương thích và dispatch của JVM.

## 3. Annotation: metadata của lớp hoặc thành viên có quy tắc kế thừa riêng

### 3.1. Retention và target phải đúng

- `@Retention(SOURCE)`: annotation chỉ có ở mã nguồn, không còn trong class file.
- `@Retention(CLASS)`: nằm trong class file nhưng **không truy cập bằng reflection runtime thông thường**; đây là mức mặc định nếu không khai báo `@Retention`.
- `@Retention(RUNTIME)`: có thể tra bằng API reflection khi chương trình chạy.
- `@Target(TYPE)` áp dụng cho khai báo kiểu; `METHOD`, `FIELD`, `PARAMETER` áp dụng cho từng loại thành viên; `TYPE_USE` dành cho các vị trí **dùng kiểu** như `List<@Checked String>`.

Annotation chỉ khai báo dữ liệu. Chẳng hạn `@Audit` không tự ghi log; phải có mã chủ động tìm annotation và thực hiện hành vi tương ứng.

### 3.2. `@Inherited` có phạm vi hẹp

`@Inherited` đặt **trên khai báo loại annotation**, và chỉ có tác dụng khi truy vấn annotation trên **khai báo class** của một lớp con; Java tìm dọc superclass nếu lớp con không khai báo annotation đó.

Vì vậy:

- `Child.class.getAnnotation(Audited.class)` có thể nhận annotation `@Audited` từ superclass nếu `Audited` được đánh dấu `@Inherited`.
- `Child.class.getDeclaredAnnotation(Audited.class)` chỉ xét lớp `Child`, nên có thể là `null`.
- `@Inherited` **không truyền annotation từ interface mà class implements**, không áp dụng tự động cho annotation trên method/field/constructor, và không khiến annotation của phương thức cha xuất hiện trên phương thức override.
- Để xử lý annotation trên interface, phương thức override, hoặc meta-annotation do ứng dụng định nghĩa, framework phải chủ động duyệt và đặt quy tắc kết hợp metadata.

Đối với annotation lặp lại (`@Repeatable`), dùng `getAnnotationsByType(...)` / `getDeclaredAnnotationsByType(...)` khi muốn lấy nhiều giá trị; tránh giả định `getAnnotation(...)` luôn đại diện đủ các annotation lặp.

### 3.3. Metadata của khai báo và của kiểu được dùng là khác nhau

Ví dụ trường `List<@Checked String> names`: annotation `@Checked` thuộc **type argument `String`**, không phải annotation khai báo trực tiếp của trường `names`. Vì thế `Field.getAnnotation(Checked.class)` không đọc nó; phải dùng `Field.getAnnotatedType()`, ép hợp lệ sang `AnnotatedParameterizedType` và truy cập `getAnnotatedActualTypeArguments()`.

Tương tự, Java có `Method.getAnnotatedReturnType()`, `getAnnotatedParameterTypes()` và `Class.getAnnotatedSuperclass()` khi cần annotation ở vị trí dùng kiểu. Các annotation này cũng phải có `RUNTIME` retention nếu muốn quan sát bằng reflection.

## 4. Ví dụ tích hợp Java 17+: kế thừa + generic + annotation + reflection

Lưu đoạn sau thành **KnowledgeReflectionDemo.java**. Chương trình dùng một lớp cha generic, một lớp con chuyên biệt kiểu `String`, một annotation trên lớp có `@Inherited` và một annotation đặt trên phương thức lớp cha.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.util.Arrays;
import java.util.Locale;

public class KnowledgeReflectionDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Audited {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Label {
        String value();
    }

    @Audited
    static class Parent<T> {
        @Label("parent")
        public T convert(T input) {
            return input;
        }

        public String ping() {
            return "parent";
        }
    }

    static class Child extends Parent<String> {
        @Override
        public String convert(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        System.out.println("Inherited annotation: "
                + type.isAnnotationPresent(Audited.class));
        System.out.println("Declared annotation: "
                + (type.getDeclaredAnnotation(Audited.class) != null));

        ParameterizedType parentType =
                (ParameterizedType) type.getGenericSuperclass();
        System.out.println("Actual parent argument: "
                + parentType.getActualTypeArguments()[0].getTypeName());

        Method parentMethod = Parent.class.getMethod("convert", Object.class);
        Method childMethod = Child.class.getDeclaredMethod("convert", String.class);
        System.out.println("Base method generic return: "
                + parentMethod.getGenericReturnType().getTypeName());
        System.out.println("Child override has @Label: "
                + childMethod.isAnnotationPresent(Label.class));
        System.out.println("Parent method label: "
                + parentMethod.getAnnotation(Label.class).value());

        Method inherited = type.getMethod("ping");
        System.out.println("Inherited method declared by Parent: "
                + (inherited.getDeclaringClass() == Parent.class));

        long bridges = Arrays.stream(type.getDeclaredMethods())
                .filter(Method::isBridge)
                .count();
        System.out.println("Bridge methods in Child: " + bridges);

        Object result = parentMethod.invoke(new Child(), "java");
        System.out.println("Reflective call result: " + result);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac KnowledgeReflectionDemo.java
java KnowledgeReflectionDemo
~~~

Kết quả:

~~~text
Inherited annotation: true
Declared annotation: false
Actual parent argument: java.lang.String
Base method generic return: T
Child override has @Label: false
Parent method label: parent
Inherited method declared by Parent: true
Bridge methods in Child: 1
Reflective call result: JAVA
~~~

**Giải thích các quan sát:**

1. `Audited` được đánh dấu `@Inherited` nên truy vấn trên `Child` thấy annotation của `Parent`, nhưng truy vấn *declared* trên `Child` không thấy.
2. Metadata `Child extends Parent<String>` giữ đối số `java.lang.String`. Trái lại, kiểu trả về khai báo của `Parent.convert(T)` vẫn là `T`.
3. `@Label("parent")` tồn tại trên method của `Parent`; `Child.convert(String)` không tự kế thừa annotation của method bị override.
4. `ping()` là phương thức `public` kế thừa; `getMethod("ping")` lấy được `Method` có `getDeclaringClass() == Parent.class`.
5. Bridge `convert(Object)` giúp lời gọi qua kiểu `Parent` tìm đúng `Child.convert(String)`. Vì `Method.invoke` trên instance áp dụng dispatch động, kết quả là `JAVA` dù `Method` được lấy từ `Parent`.

Lưu ý: `getDeclaredMethods()` có thể chứa cả phương thức nguồn lẫn bridge/synthetic; không dựa vào thứ tự phần tử mảng để suy ra đâu là phương thức cần dùng.

## 5. Ví dụ riêng về generic field và annotation ở vị trí dùng kiểu

Ví dụ trước dùng annotation trên **khai báo class/method**. Ví dụ này làm rõ một trường có generic signature và annotation **trên type argument**. Lưu thành **TypeUseDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.util.List;

public class TypeUseDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Checked {}

    static class Input {
        List<@Checked String> names;
    }

    public static void main(String[] args) throws Exception {
        Field field = Input.class.getDeclaredField("names");
        ParameterizedType genericType =
                (ParameterizedType) field.getGenericType();
        AnnotatedParameterizedType annotatedType =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        System.out.println("Raw field type: "
                + field.getType().getTypeName());
        System.out.println("Type argument: "
                + genericType.getActualTypeArguments()[0].getTypeName());
        System.out.println("Type-use annotation: "
                + annotatedType.getAnnotatedActualTypeArguments()[0]
                        .isAnnotationPresent(Checked.class));
    }
}
~~~

~~~bash
javac TypeUseDemo.java
java TypeUseDemo
~~~

~~~text
Raw field type: java.util.List
Type argument: java.lang.String
Type-use annotation: true
~~~

`getType()` chỉ thấy `List` đã xóa tham số, `getGenericType()` thấy `String` ở khai báo trường, còn `getAnnotatedType()` truy cập annotation trên vị trí dùng kiểu. Không có bước nào tự chứng minh mọi phần tử được đưa vào danh sách ở runtime đều thực sự là `String`; đó vẫn là trách nhiệm của hệ thống kiểu và logic kiểm tra dữ liệu.

## 6. Áp dụng khi xây dựng công cụ dùng reflection

Xét một thư viện cần tìm các phương thức gắn `@Action` trên một đối tượng có nhiều lớp cha. Một quy trình có thể kiểm chứng được:

1. **Xác định quy tắc kế thừa mong muốn.** Chỉ đọc phương thức `public` có thể truy cập bằng `getMethods()`, hay quét tất cả khai báo qua từng cấp bằng `getDeclaredMethods()`? Annotation của method override có được ứng dụng *chủ động* lấy từ method cha hay không?
2. **Duyệt kiểu có chủ đích.** Khi dùng `getDeclaredMethods()`, lần lượt duyệt superclass bằng `getSuperclass()`; xét interface riêng nếu yêu cầu. Lưu `getDeclaringClass()` để xác định nguồn metadata.
3. **Xử lý bridge/synthetic và override.** Kiểm tra `isBridge()`/`isSynthetic()`, đối chiếu tên + kiểu tham số + quan hệ override để tránh cùng một hành vi được đăng ký hai lần. Không giả định mọi phương thức cùng tên là một.
4. **Đọc annotation theo vị trí.** `getDeclaredAnnotation()` chỉ lấy trực tiếp; `getAnnotation()` trên class có thể tôn trọng `@Inherited`; đối với method cha/interface phải tự định nghĩa thuật toán tìm. Annotation gắn vào generic type argument cần API `AnnotatedType`.
5. **Giải kiểu generic theo ngữ cảnh.** Trước tiên kiểm tra `Type` bằng `instanceof`; nếu gặp `TypeVariable` thì duyệt các quan hệ `ParameterizedType` giữa lớp cụ thể và nơi khai báo rồi thay biến kiểu theo mapping, bao gồm các trường hợp generic lồng nhau và nhiều cấp.
6. **Thực thi có kiểm soát.** Kiểm tra modifier, quyền truy cập, tham số, kiểu receiver và lỗi có thể phát sinh. `Method.invoke` có thể ném `IllegalAccessException`, `IllegalArgumentException`, hoặc `InvocationTargetException` (bọc lỗi từ chính phương thức đích). Trong module Java, việc mở `private` member có thể bị từ chối.
7. **Chọn và kiểm thử chính sách xung đột.** Nếu cả method lớp con và lớp cha có annotation, cần quy định cái nào ưu tiên; nếu có annotation trên interface, chỉ lấy khi nghiệp vụ quy định; nếu là repeatable annotation, phải xử lý tất cả giá trị thích hợp.

**Ví dụ thực tế:** một framework mapping dữ liệu nhìn vào `Field.getGenericType()` để suy ra kiểu phần tử của `List<User>`, xem annotation trên trường hoặc trên `User` để quyết định chuyển đổi, rồi chọn setter `public` hay constructor phù hợp. Nếu lớp entity kế thừa từ entity cha, framework phải quyết định có quét field cha và xử lý field bị che khuất không. Reflection cung cấp dữ liệu để quyết định; chính framework sở hữu các quy tắc này.

## 7. Những hiểu lầm thường gặp và cách tự kiểm tra

| Hiểu lầm | Thực tế / cách kiểm tra |
| --- | --- |
| “`getDeclaredMethods()` có mọi method dùng được của object.” | Nó chỉ trả những method khai báo trong `Class` đang xét; muốn member thừa hưởng thì dùng `getMethods()` hoặc duyệt cấp cha. |
| “`Method` của lớp cha luôn gọi thân method cha.” | Với instance method bị override, `invoke` vẫn dispatch động theo receiver. Static method thì khác. |
| “Reflection lấy được `T=String` từ mọi đối tượng generic.” | Type erasure làm mất nhiều thông tin runtime; metadata quan hệ `extends Parent<String>` chỉ giúp giải được một số ngữ cảnh. |
| “`@Inherited` áp dụng cho method và interface.” | Nó chỉ có tác dụng với annotation **trên class** được tìm qua **superclass**. |
| “Không tìm thấy annotation tức annotation không tồn tại trong mã.” | Có thể annotation không có `RUNTIME` retention, đang ở method cha, hoặc nằm ở vị trí dùng kiểu thay vì khai báo. |
| “Mỗi method trong `getDeclaredMethods()` tương ứng một method mã nguồn.” | Compiler có thể thêm bridge/synthetic methods. |
| “`setAccessible(true)` luôn mở được private member.” | Kiểm tra truy cập, module JPMS và chính sách runtime có thể từ chối. |
| “Có annotation thì tính năng tự chạy.” | Phải có thành phần đọc annotation và triển khai hành vi. |

Để tự kiểm tra, hãy trả lời ba câu hỏi: (a) `getMethod` và `getDeclaredMethod` khác nhau thế nào khi method chỉ có ở cha? (b) tại sao `Parent<T>.convert(T)` vẫn có generic return `T` dù `Child extends Parent<String>`? (c) vì sao `@Inherited` cho kết quả khác nhau giữa `Child.class.getAnnotation(...)` và `Child.class.getDeclaredAnnotation(...)`? Nếu giải thích được cả ba bằng ví dụ trên, bạn đã nắm được ranh giới giữa metadata khai báo, quan hệ kế thừa và hành vi runtime.

### Tài liệu API chính thức

- Java SE 21, `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21, `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21, `Inherited`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Inherited.html