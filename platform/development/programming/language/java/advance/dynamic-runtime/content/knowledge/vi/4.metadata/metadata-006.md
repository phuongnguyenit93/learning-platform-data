# 4.6 Đọc annotation lúc chạy, annotation lặp và các quy tắc kế thừa

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Xác định annotation nào **được giữ lại đến runtime** và đọc giá trị của nó bằng Reflection.
- Phân biệt các API `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, `getDeclaredAnnotationsByType`, kể cả khi một annotation xuất hiện nhiều lần.
- Khai báo annotation lặp bằng `@Repeatable` và **container annotation**, rồi đọc đúng tất cả phần tử.
- Giải thích chính xác khi nào `@Inherited` có tác dụng và những trường hợp **không** tự kế thừa qua interface, method, field hoặc override.
- Thiết kế một bộ đọc metadata cho framework/plugin có quy tắc rõ ràng về thứ tự, ghi đè, gộp và xử lý lỗi.

Phạm vi ở đây là **đọc annotation trong lúc JVM chạy** (runtime reflection). Việc viết annotation processor ở lúc biên dịch và việc sinh/chỉnh sửa bytecode là các kỹ thuật khác, không phải điều kiện bắt buộc để dùng Reflection.

## 2. Annotation trở thành dữ liệu runtime như thế nào?

Annotation là **metadata** gắn lên khai báo hoặc vị trí sử dụng kiểu. Một annotation không tự thực thi logic: thành phần framework đọc metadata và quyết định làm gì với nó. Chẳng hạn `@Route("/users")` chỉ có tác dụng đăng ký HTTP route nếu có mã hoặc framework chủ động quét và xử lý `@Route`.

Vòng đời giản lược:

1. Mã nguồn khai báo một annotation interface, ví dụ `@interface Route`, và gắn annotation lên lớp hoặc method.
2. Compiler kiểm tra cách dùng dựa trên các quy tắc kiểu, `@Target`, chữ ký các phần tử annotation; metadata được giữ hay loại bỏ theo `@Retention`.
3. Khi runtime còn metadata phù hợp, Reflection dùng các đối tượng `Class`, `Method`, `Field`, `Constructor`, `Parameter` hoặc `AnnotatedType` để đọc.
4. Ứng dụng xử lý dữ liệu đó: dựng route table, áp dụng policy, chọn plugin, đăng ký handler, kiểm tra schema…

### 2.1. `@Retention` quyết định khả năng đọc lúc chạy

| Retention policy | Còn trong `.class`? | Đọc được bằng Reflection lúc chạy? | Ví dụ mục đích |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Không bắt buộc giữ trong class file; compiler loại bỏ | Không | Hỗ trợ phân tích mã nguồn, annotation processor. |
| `RetentionPolicy.CLASS` | Có trong class file | Không, theo API Reflection thông thường | Metadata cho công cụ đọc bytecode. Đây cũng là **giá trị mặc định** khi không khai báo `@Retention`. |
| `RetentionPolicy.RUNTIME` | Có, kèm thuộc tính runtime-visible | **Có** | Framework/DI/ORM/router đọc trong JVM đang chạy. |

Vì vậy, muốn `SomeType.class.getAnnotation(MyTag.class)` tìm thấy `@MyTag`, trước hết loại `MyTag` phải được khai báo `@Retention(RetentionPolicy.RUNTIME)`. Chỉ viết `@interface MyTag` mà không thêm retention thì mặc định là `CLASS`; Java Reflection thường trả về `null` hoặc mảng rỗng khi tìm.

`@Target` giới hạn những nơi có thể viết annotation, ví dụ `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `CONSTRUCTOR`, `ANNOTATION_TYPE`, `TYPE_USE`. `@Target` **không làm annotation xuất hiện tại runtime**; đó là vai trò của `@Retention`. `@Documented` chủ yếu ảnh hưởng tài liệu Javadoc, cũng không thay cho `RUNTIME`.

### 2.2. Ví dụ chạy được: đọc annotation trên class và method

Tạo tệp **`RuntimeAnnotationDemo.java`**:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Route {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface CompileTag {}

@Route("catalog")
@CompileTag
class Catalog {
    @Route("lookup")
    public void lookup() {}
}

public class RuntimeAnnotationDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Route typeAnnotation =
                Catalog.class.getAnnotation(Route.class);
        Route methodAnnotation = Catalog.class
                .getDeclaredMethod("lookup")
                .getAnnotation(Route.class);

        System.out.println("class: " + typeAnnotation.value());
        System.out.println("method: " + methodAnnotation.value());
        System.out.println("CLASS visible at runtime: "
                + (Catalog.class.getAnnotation(CompileTag.class) != null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 RuntimeAnnotationDemo.java
java RuntimeAnnotationDemo
```

Stdout:

```text
class: catalog
method: lookup
CLASS visible at runtime: false
```

**Giải thích:** `Route` có retention `RUNTIME` nên `Class` và `Method` đọc được qua `getAnnotation`. `CompileTag` có retention `CLASS`, vẫn có metadata dành cho công cụ class file nhưng không hiện diện qua truy vấn runtime Reflection này. `value()` là **phần tử của annotation**; nó trả về chuỗi được khai báo tại chỗ sử dụng. Trong ứng dụng thật, hãy kiểm tra giá trị trả về khác `null` trước khi gọi `value()`.

**API chọn đúng phần tử:** `Catalog.class.getDeclaredMethod("lookup")` yêu cầu đúng tên và danh sách kiểu tham số; một method overload cần chỉ rõ kiểu, ví dụ `getDeclaredMethod("lookup", String.class)`. Việc tìm method qua Reflection và việc đọc annotation trên method là hai bước độc lập.

## 3. Sáu cách đọc chính từ `AnnotatedElement`

Các kiểu như `Class`, `Method`, `Field`, `Constructor`, `Parameter` hỗ trợ giao diện `java.lang.reflect.AnnotatedElement`. Phân biệt bốn trạng thái theo hợp đồng API:

- **Directly present — trực tiếp:** annotation có mặt trực tiếp trên phần tử phản chiếu.
- **Indirectly present — gián tiếp:** annotation **có thể lặp**, và một **container annotation** trên phần tử chứa nó.
- **Present — hiện diện:** có trực tiếp, hoặc có thể được thừa hưởng từ superclass theo `@Inherited` khi truy vấn annotation trên **class** và không có annotation cùng loại trực tiếp.
- **Associated — gắn với phần tử theo truy vấn nhiều kết quả:** có trực tiếp hoặc gián tiếp, hoặc được kế thừa theo `@Inherited` khi truy vấn class và không có annotation cùng loại trực tiếp/gián tiếp.

| API | Nhận diện | Có “mở” container của repeatable? | Xét `@Inherited` trên class? | Khi nào dùng |
| --- | --- | --- | --- | --- |
| `getAnnotation(A.class)` | **Present** | Không | Có | Tìm một annotation không lặp hoặc lấy một annotation trực tiếp của loại cần tìm. |
| `getDeclaredAnnotation(A.class)` | **Directly present** | Không | Không | Chỉ xét annotation trực tiếp trên phần tử. |
| `getAnnotationsByType(A.class)` | **Associated** | **Có** | Có, nếu ở class và có điều kiện kế thừa | Đọc **tất cả** annotation lặp, có xét superclass. |
| `getDeclaredAnnotationsByType(A.class)` | **Directly/indirectly present** | **Có** | Không | Đọc tất cả annotation lặp **chỉ khai báo tại phần tử**. |
| `getAnnotations()` | **Present** của từng kiểu annotation | Không tự trải ra thành mọi bản lặp | Có với annotation có thể kế thừa trên class | Kiểm kê các annotation hiện diện; có thể thấy **container** thay cho từng bản lặp. |
| `getDeclaredAnnotations()` | **Directly present** | Không tự trải ra thành mọi bản lặp | Không | Kiểm kê annotation khai báo trực tiếp. |

`isAnnotationPresent(A.class)` tương đương về kết quả logic với `getAnnotation(A.class) != null`. Vì nó dùng khái niệm **present**, đối với **một loại annotation lặp đang được chứa trong container**, hàm này có thể trả `false` dù `getAnnotationsByType(A.class)` trả về nhiều phần tử.

Lỗi hay gặp: dùng `getAnnotations()` rồi kỳ vọng mỗi lần viết `@Tag` sẽ trở thành một phần tử `Tag` trong mảng. Với annotation lặp, compiler có thể ghi một **container** như `@Tags`. Khi biết loại cần đọc có thể lặp, dùng API `...AnnotationsByType(Tag.class)`.

**Quy ước kết quả:** `getAnnotation` / `getDeclaredAnnotation` trả `null` khi không tìm thấy; `getAnnotationsByType` / `getDeclaredAnnotationsByType` trả **mảng có độ dài 0**, không trả `null` khi không có annotation. Mảng kết quả có thể được caller sửa mà không thay đổi các mảng kết quả truy vấn sau.

## 4. Định nghĩa annotation lặp với `@Repeatable`

Từ Java 8, một annotation có thể xuất hiện nhiều lần tại cùng một phần tử, ví dụ:

```java
@Tag("read")
@Tag("write")
class Handler {}
```

Để khai báo hợp lệ, cần:

1. **Annotation lặp** `Tag` được đánh dấu `@Repeatable(Tags.class)`.
2. **Container annotation** `Tags` phải có phần tử **`value()` trả về `Tag[]`**.
3. Retention của container phải tương thích và không ngắn hơn retention của annotation lặp; với mục tiêu Reflection, hãy khai báo **cả hai là `RUNTIME`**.
4. `@Target` của container phải phù hợp với phạm vi dùng annotation lặp. Nếu annotation lặp là `@Inherited`, container tương ứng cũng phải mang `@Inherited` (quy tắc Java cho phép compiler kiểm tra).
5. Compiler có thể chuyển nhiều lần viết `@Tag` thành một container `@Tags({@Tag(...), @Tag(...)})` trong metadata. Vì vậy API đọc từng `Tag` cần mở container.

**Có một annotation:** `@Tag("read")` trên lớp thường là annotation `Tag` trực tiếp, `getAnnotation(Tag.class)` có thể trả về nó. **Có nhiều annotation:** `@Tag("read") @Tag("write")` thường được biểu diễn qua `Tags`; `getAnnotation(Tag.class)` **không mở container** và có thể trả `null`. `getAnnotationsByType(Tag.class)` xử lý cả hai tình huống.

### 4.1. Thứ tự các bản lặp

Với `getAnnotationsByType` và `getDeclaredAnnotationsByType`, đặc tả nêu cách xác định thứ tự khi một phần tử có annotation lặp trực tiếp/gián tiếp: các bản lặp trong container được xét **theo thứ tự của mảng `value()`**, và các annotation gián tiếp được coi như xuất hiện ở vị trí container.

Điều này **không có nghĩa** mọi mảng từ các API Reflection đều có thứ tự mặc định phù hợp cho nghiệp vụ. Nếu các bản `@Tag` biểu thị tập quyền không có thứ tự, hãy xử lý chúng như tập; nếu thứ tự mang ý nghĩa ưu tiên, cần đưa ra chính sách rõ ràng và kiểm thử. Không suy ra thứ tự của **các loại annotation khác nhau** từ kết quả `getAnnotations()`.

## 5. Ví dụ chạy được: annotation lặp và kế thừa

Đây là ví dụ kết hợp vì tương tác giữa `@Repeatable` và `@Inherited` là nơi rất dễ mắc lỗi. Tạo tệp **`RepeatableInheritanceDemo.java`**:

```java
import java.lang.annotation.*;
import java.util.Arrays;
import java.util.stream.Collectors;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("base-a")
@Tag("base-b")
class Parent {}

class Child extends Parent {}

@Tag("child")
class OwnChild extends Parent {}

@Tag("interface")
interface Contract {}

class Implementation implements Contract {}

public class RepeatableInheritanceDemo {
    private static String names(Tag[] tags) {
        return Arrays.stream(tags)
                .map(Tag::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("Parent tags: "
                + names(Parent.class.getAnnotationsByType(Tag.class)));
        System.out.println("Child associated: "
                + names(Child.class.getAnnotationsByType(Tag.class)));
        System.out.println("Child declared count: "
                + Child.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("Child single Tag: "
                + (Child.class.getAnnotation(Tag.class) != null));
        System.out.println("Child container: "
                + (Child.class.getAnnotation(Tags.class) != null));
        System.out.println("OwnChild associated: "
                + names(OwnChild.class.getAnnotationsByType(Tag.class)));
        System.out.println("OwnChild inherited container: "
                + (OwnChild.class.getAnnotation(Tags.class) != null));
        System.out.println("Implementation tags count: "
                + Implementation.class.getAnnotationsByType(Tag.class).length);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 RepeatableInheritanceDemo.java
java RepeatableInheritanceDemo
```

Stdout:

```text
Parent tags: base-a,base-b
Child associated: base-a,base-b
Child declared count: 0
Child single Tag: false
Child container: true
OwnChild associated: child
OwnChild inherited container: true
Implementation tags count: 0
```

### 5.1. Giải thích những kết quả có thể gây ngạc nhiên

**`Parent`:** Có hai `@Tag`, compiler biểu diễn chúng thông qua `@Tags` chứa hai phần tử. `Parent.class.getAnnotationsByType(Tag.class)` nhận cả hai theo thứ tự khai báo trong container.

**`Child`:** Không khai báo `Tag` riêng. Vì `Tag` và container `Tags` đều có `@Inherited`, `getAnnotationsByType(Tag.class)` xem xét superclass và nhận `base-a,base-b`. `getDeclaredAnnotationsByType(Tag.class)` vẫn trả mảng rỗng vì `Child` không khai báo `Tag` hoặc `Tags`.

**Vì sao `Child.getAnnotation(Tag.class)` là `false`?** Phương thức này chỉ xét annotation loại `Tag` **present**, không trải qua container `Tags`. Hai `Tag` trên `Parent` là **indirectly present**, không phải một `Tag` trực tiếp. Đổi lại, `Child.getAnnotation(Tags.class)` thấy container `Tags` được kế thừa, nên trả khác `null`.

**`OwnChild`:** Có `@Tag("child")` trực tiếp. Truy vấn `getAnnotationsByType(Tag.class)` trả **chỉ phần tử của lớp con**, không tự nối thêm `base-a,base-b` của lớp cha. Với semantics **associated**, khi lớp con có annotation trực tiếp hoặc gián tiếp cùng loại, tìm kiếm ở superclass cho loại đó dừng lại.

**Vì sao `OwnChild.getAnnotation(Tags.class)` vẫn là `true`?** Đây là truy vấn **loại container `Tags`** riêng biệt. `OwnChild` không khai báo `@Tags` trực tiếp nên truy vấn container này vẫn có thể kế thừa container từ `Parent`. Điều đó **không làm** `getAnnotationsByType(Tag.class)` tự động gộp hai cấp. Tránh dùng `getAnnotation(Tags.class)` cộng thủ công vào `getAnnotationsByType(Tag.class)`, vì dễ trùng hoặc lẫn dữ liệu theo quy tắc khác nhau.

**`Implementation`:** `@Tag("interface")` nằm trên interface `Contract`. `@Inherited` **không lan truyền từ interface triển khai** sang class `Implementation`. Không có `Tag` trực tiếp hoặc trên superclass của `Implementation` nên kết quả là 0.

### 5.2. Quy tắc thừa kế của annotation lặp

Khi `A` là repeatable và có `@Inherited`:

- Lớp con **không có** `A` trực tiếp hoặc qua container: `getAnnotationsByType(A.class)` có thể kế thừa các phần tử từ superclass gần nhất tìm được.
- Lớp con **có ít nhất một** `A` riêng: kết quả `getAnnotationsByType(A.class)` dùng các `A` của chính lớp đó; không mặc định trộn với các `A` ở superclass.
- `getDeclaredAnnotationsByType(A.class)` luôn giới hạn trong chính phần tử; không đi ngược hierarchy.
- Truy vấn **container** `As.class` là một truy vấn loại annotation khác, có thể tạo kết quả khác truy vấn `A.class`.

Nếu nghiệp vụ muốn **gộp policy ở tất cả superclass** (ví dụ các rule được phép cộng dồn), phải tự duyệt hierarchy và định nghĩa cách gộp, ghi đè và xử lý trùng lặp; không được giả định `@Inherited` tự làm điều đó.

## 6. `@Inherited` áp dụng ở đâu?

Javadoc của `java.lang.annotation.Inherited` xác định rõ:

1. Annotation type phải có meta-annotation `@Inherited`.
2. Khi truy vấn annotation trên một **class**, nếu class chưa có annotation cùng loại theo semantics của API, runtime có thể tìm trên **superclass** và tiếp tục lên trên.
3. `@Inherited` **không lấy annotation của interface đã implements**.
4. `@Inherited` **không làm annotation của method, field, constructor hoặc parameter tự được kế thừa**.
5. Trong hierachy, khai báo cùng loại gần class được truy vấn hơn có thể che khuất annotation phía superclass theo các quy tắc `present` hoặc `associated`.

Những phát biểu “annotation đều kế thừa theo Java inheritance” hoặc “implements interface cũng nhận `@Inherited`” là sai. Kế thừa annotation có hợp đồng riêng với kế thừa type/method.

### 6.1. Ví dụ chạy được: class kế thừa; method và interface thì không

Tạo tệp **`AnnotationInheritanceDemo.java`**:

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Label {
    String value();
}

@Label("parent")
class ParentType {
    @Label("method-parent")
    public void work() {}
}

class ChildType extends ParentType {
    @Override
    public void work() {}
}

@Label("contract")
interface Marker {}

class Implementor implements Marker {}

public class AnnotationInheritanceDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        System.out.println("Child class: "
                + ChildType.class.getAnnotation(Label.class).value());
        System.out.println("Child declared? "
                + (ChildType.class.getDeclaredAnnotation(Label.class) != null));
        System.out.println("Child method annotated? "
                + (ChildType.class.getDeclaredMethod("work")
                    .getAnnotation(Label.class) != null));
        System.out.println("Parent method: "
                + ParentType.class.getDeclaredMethod("work")
                    .getAnnotation(Label.class).value());
        System.out.println("Interface transferred? "
                + (Implementor.class.getAnnotation(Label.class) != null));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 AnnotationInheritanceDemo.java
java AnnotationInheritanceDemo
```

Stdout:

```text
Child class: parent
Child declared? false
Child method annotated? false
Parent method: method-parent
Interface transferred? false
```

- Class `ChildType` nhận `@Label("parent")` qua API `getAnnotation` vì `Label` có `@Inherited`.
- `ChildType.getDeclaredAnnotation(Label.class)` là `null`: chính `ChildType` không khai báo `@Label`.
- Method `work()` trong `ChildType` **override** method cùng tên của `ParentType` nhưng không tự mang `@Label("method-parent")`. Muốn xét annotation của method bên lớp cha, phải chủ động tìm method tương ứng trong superclass theo quy tắc framework.
- Class `Implementor` không được tự động gắn `@Label("contract")` chỉ vì implements `Marker`.

**Phân biệt cực kỳ quan trọng:** nếu lớp con **không override** `work()` và bạn gọi `ChildType.class.getMethod("work")`, Reflection có thể trả đối tượng `Method` **được khai báo ở lớp cha**; đọc annotation trên chính `Method` đó thấy `@Label("method-parent")`. Đây là kết quả của **tra cứu method kế thừa**, không phải việc `@Inherited` được áp dụng cho annotation trên method. Dùng `getDeclaredMethod` khi bạn cần biết lớp hiện tại **tự khai báo** method nào.

## 7. Tình huống thực tế: framework đọc metadata thế nào?

### 7.1. Đăng ký endpoint bằng annotation

Giả sử framework muốn tìm các method mang `@Route`:

- Đặt `@Retention(RUNTIME)` và `@Target(METHOD)` lên `Route`.
- Tìm đúng tập class cần quét dựa vào cấu hình hoặc cơ chế đăng ký; Reflection **không tự tìm toàn bộ classpath**.
- Đọc method bằng `getDeclaredMethods()` hoặc chiến lược gồm cả method kế thừa; mỗi cách cho tập method khác nhau.
- Với mỗi `Method`, gọi `getDeclaredAnnotation(Route.class)` hoặc `getAnnotationsByType(Route.class)` nếu `Route` là repeatable.
- Kiểm tra route trùng, giá trị path/method, quyền truy cập và thứ tự đăng ký theo quy tắc riêng.

Nếu framework muốn annotation của interface method tác động tới implementation, phải **cố ý truy vấn interface hierarchy và map method theo chữ ký**; `@Inherited` không làm việc này.

### 7.2. Chính sách quyền nhiều tầng

Giả sử `@Permission` có thể lặp:

```java
@Permission("read")
@Permission("write")
class AdminHandler {}
```

Đây là **mẫu sử dụng minh họa**, giả định `Permission` đã được định nghĩa đúng với `@Repeatable`, container và `@Retention(RUNTIME)`. Có ít nhất ba chính sách hợp lý nhưng khác nhau:

- **Override:** nếu lớp con khai báo policy của nó, bỏ policy lớp cha. `getAnnotationsByType` với `@Inherited` gần với kiểu này.
- **Merge/union:** cộng quyền từ cha và con; phải tự duyệt superclass, loại trùng và xác định cách xử lý `deny` so với `allow`.
- **Deny by default:** nếu không có policy hợp lệ hoặc có xung đột thì không cho phép; metadata chỉ là đầu vào, quyết định bảo mật cần logic riêng và kiểm thử.

Không xây cơ chế phân quyền chỉ dựa trên suy luận rằng một mảng annotation đã tự động hợp nhất mọi cấp hierarchy.

### 7.3. Thứ tự annotation lặp và tính xác định

Với `@Tag("first") @Tag("second")`, `getAnnotationsByType(Tag.class)` phản ánh thứ tự của các bản lặp theo quy tắc container. Tuy nhiên, một hệ thống dùng tag làm **tập lựa chọn** có thể chuẩn hóa chúng theo tên để tránh output thay đổi không có ý nghĩa nghiệp vụ. Nếu **thứ tự thực thi** có ý nghĩa, tốt hơn là định nghĩa `order()` / `priority()` hoặc dependency rõ ràng, thay vì trông chờ thứ tự liệt kê annotation từ nhiều element khác nhau.

### 7.4. Khi annotation gắn trên tham số hoặc type use

Không phải mọi metadata nằm trên `Class` và `Method`:

- Annotation khai báo trên **tham số** có thể đọc qua `method.getParameters()[i].getAnnotationsByType(MyTag.class)`, với `@Target(PARAMETER)`.
- Annotation dùng tại **vị trí kiểu** (ví dụ `List<@NonNull String>` nếu `NonNull` có `@Target(TYPE_USE)`) cần API `AnnotatedType` và các biến thể như `Method.getAnnotatedReturnType()`, `Field.getAnnotatedType()`, `Parameter.getAnnotatedType()`. `Class.getAnnotations()` chỉ cho metadata khai báo của chính class, không thể hiện đầy đủ annotation trong mọi biểu thức kiểu.

Đây là sự khác nhau giữa **declaration annotations** và **type annotations**, không phải lỗi của `@Retention(RUNTIME)`.

## 8. Lỗi thường gặp và chẩn đoán

| Triệu chứng / lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `getAnnotation(X.class) == null` dù thấy `@X` trong source | `@Retention` là `CLASS` mặc định, hoặc `X` chỉ hiện diện trong container của repeatable | Khai báo `@Retention(RUNTIME)`; nếu `X` repeatable, dùng `getAnnotationsByType(X.class)`. |
| Chỉ nhận một phần tử khi viết `@X` hai lần | Đọc `getAnnotation(X.class)` hoặc raw `getAnnotations()`, bỏ qua container | Dùng `getDeclaredAnnotationsByType` / `getAnnotationsByType` theo nhu cầu kế thừa. |
| Class con không thấy annotation của interface | `@Inherited` chỉ duyệt **superclass** | Tự duyệt interface/superinterface, quy định thứ tự ưu tiên và chống trùng. |
| Method override không thấy annotation method cha | `@Inherited` không áp dụng cho method | Tự tra cứu method có chữ ký tương ứng trong hierarchy, nếu hợp đồng framework muốn áp dụng. |
| Class con chỉ thấy annotation lặp của chính nó | `getAnnotationsByType` ưu tiên các phần tử trực tiếp/gián tiếp của lớp con | Nếu muốn gộp, duyệt hierarchy và merge theo chính sách tường minh. |
| `getAnnotation(X.class)` không thấy nhưng `getAnnotation(Xs.class)` thấy | `Xs` là container và `getAnnotation` không unwrap | Dùng `getAnnotationsByType(X.class)`; đừng cộng kết quả container thủ công. |
| Compile error khi định nghĩa `@Repeatable` | Container không có `value(): X[]` hoặc retention/target/`@Inherited` không tương thích | Sửa khai báo cả annotation lặp và container theo quy tắc của Java. |
| Đọc nhầm annotation của kiểu sử dụng ở generic | Dùng API annotation khai báo thay vì `AnnotatedType` | Chuyển sang API `getAnnotated...` khi `@Target(TYPE_USE)`. |
| Kết quả “đúng trên máy tôi” nhưng sai khi đổi cách quét | Nhầm thứ tự class/method/annotation từ nhiều nguồn với thứ tự nghiệp vụ | Chuẩn hóa và sắp xếp kết quả theo khóa/priority do ứng dụng quy định. |

### 8.1. Lưu ý về lỗi runtime và tương thích

Code Reflection không mặc định thành công chỉ vì annotation từng tồn tại khi biên dịch. Khi thay JAR, đổi định nghĩa annotation hoặc thiếu kiểu được nhắc trong giá trị annotation, các lỗi có thể xuất hiện khi đọc phần tử annotation: `TypeNotPresentException`, `EnumConstantNotPresentException`, `AnnotationTypeMismatchException` hoặc `IncompleteAnnotationException`. Framework nên báo **lớp, member, annotation type và thuộc tính** gây lỗi, thay vì nuốt exception và hiểu nhầm rằng annotation không tồn tại.

Nếu chỉ cần kiểm tra marker, `isAnnotationPresent` phù hợp cho annotation **không lặp** hoặc có semantics “present” đã được hiểu. Khi xử lý repeatable, kiểm tra `getAnnotationsByType(A.class).length > 0` thường rõ nghĩa hơn.

### 8.2. Bảo mật và giới hạn

Annotation là **dữ liệu**, không phải cơ chế bảo vệ tự động. `@Permission("admin")` không tự khóa endpoint; framework phải đánh giá policy ở mọi đường gọi thích hợp. Đừng kích hoạt tùy ý lớp/phương thức chỉ vì metadata đến từ JAR hoặc cấu hình không tin cậy. Áp dụng allowlist, kiểm thử logic ưu tiên và giới hạn nguồn plugin.

Việc **đọc annotation** khác với việc bật khả năng truy cập private member. Thông thường bạn không cần `setAccessible(true)` chỉ để kiểm tra metadata; JPMS có thể hạn chế deep reflection, và không nên mở module tràn lan để khắc phục một lỗi đọc annotation chưa được chẩn đoán.

## 9. Kiểm thử đúng quy tắc annotation

Một bộ kiểm thử cần cover ít nhất các trường hợp độc lập sau:

1. Annotation `SOURCE`, `CLASS` và `RUNTIME` trên cùng loại phần tử; xác minh chỉ `RUNTIME` được đọc qua Reflection.
2. Annotation đơn và annotation lặp **2+ lần**; so sánh `getAnnotation` với `getAnnotationsByType`.
3. Repeatable và container khai báo đúng `@Retention(RUNTIME)`, `@Target` và `@Inherited` (nếu có).
4. Class con không khai báo annotation; class con khai báo một annotation cùng loại; kiểm tra khác biệt giữa `getAnnotationsByType` và `getDeclaredAnnotationsByType`.
5. Interface mang `@Inherited` và class implements; bảo đảm không tự nhận annotation từ interface.
6. Method override và method kế thừa nhưng không override; phân biệt `getDeclaredMethod` với `getMethod`.
7. Một class không có annotation; kết quả một phần tử từ `getAnnotation` là `null` còn kết quả mảng từ `getAnnotationsByType` có độ dài 0.
8. Với framework có chính sách **merge**, viết test riêng cho thứ tự cha/con, duplicate, allow/deny và xung đột; không dựa vào mặc định `@Inherited`.

Khi test annotation lặp, assert **các giá trị theo thứ tự thực sự cần cho contract**, ví dụ:

```text
Parent tags: base-a,base-b
Child associated: base-a,base-b
Child declared count: 0
```

Đây là ba dòng lấy từ ví dụ mục 5, không phải toàn bộ stdout. Tránh viết test kiểm tra thứ tự raw của các **loại annotation không liên quan** trong `getAnnotations()`.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@MyTag` có mặt trong source nhưng `SomeClass.class.getAnnotation(MyTag.class)` trả `null`?

**Đáp:** Một nguyên nhân phổ biến là `MyTag` mặc định có retention `CLASS`. Nếu `MyTag` là repeatable và bị gói vào container, `getAnnotation(MyTag.class)` cũng không tự mở container. Kiểm tra định nghĩa annotation, sau đó dùng API phù hợp.

**Câu 2.** Hai `@Tag` trên lớp cha, lớp con không khai báo gì. API nào trả cả hai nếu `Tag` và container đều `@Inherited`?

**Đáp:** `Child.class.getAnnotationsByType(Tag.class)`. `getDeclaredAnnotationsByType(Tag.class)` trả mảng rỗng; `getAnnotation(Tag.class)` không mở container.

**Câu 3.** Khi lớp con khai báo một `@Tag` riêng, `getAnnotationsByType(Tag.class)` có trả luôn hai tag từ lớp cha không?

**Đáp:** Không. Các tag khai báo trên lớp con được ưu tiên; API không mặc định gộp toàn bộ hierarchy. Muốn union phải thiết kế thuật toán riêng.

**Câu 4.** `@Inherited` có khiến annotation của interface truyền sang class implements hoặc annotation của method cha truyền sang method override?

**Đáp:** Không. `@Inherited` của Java áp dụng cho truy vấn annotation **trên class qua chuỗi superclass**, không phải mọi hình thức kế thừa ngôn ngữ Java.

**Câu 5.** Nếu method kế thừa không override trả về annotation đã viết trên method cha thì đó có phải `@Inherited` hoạt động trên method?

**Đáp:** Không. Reflection đang trả về chính đối tượng `Method` khai báo ở lớp cha khi tra cứu member kế thừa. Khi override, method mới không tự có annotation đó.

## 11. Ghi nhớ

- **Đọc annotation tại runtime cần `@Retention(RUNTIME)`**; `CLASS` và `SOURCE` không xuất hiện qua Reflection thường dùng.
- **Đọc annotation lặp bằng `getAnnotationsByType` / `getDeclaredAnnotationsByType`**. `getAnnotation` và `getDeclaredAnnotation` không tự mở container.
- **`@Inherited` chỉ có hiệu lực trên khai báo class qua superclass**, không tự áp dụng cho interface, method, field hoặc parameter. Với repeatable, lớp con khai báo bản riêng sẽ không tự gộp với các bản trên lớp cha.
- **Phân biệt dữ liệu và policy.** Framework phải chọn rõ quy tắc đọc trên phần tử, có kế thừa hay không, có hợp nhất hay ghi đè, và thứ tự xử lý theo hợp đồng ứng dụng.
- Khi thiết kế API metadata, hãy kết hợp kiểm thử đối với retention, container, inheritance, override và trường hợp không có annotation; tránh phụ thuộc hành vi tình cờ của môi trường.

### Tài liệu chính thức (Java SE 17)

- [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): định nghĩa **directly present**, **indirectly present**, **present**, **associated**, bảng semantics của các API và thứ tự phần tử lặp.
- [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html) và [`RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): khả năng tồn tại của annotation sau compile và tại runtime.
- [`Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): khai báo annotation lặp và container.
- [`Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): quy tắc thừa kế chỉ qua superclass đối với annotation trên class.
- [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) và [`AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): truy vấn metadata của class, executable và vị trí dùng kiểu.
