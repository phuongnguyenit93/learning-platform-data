# getAnnotationsByType và getDeclaredAnnotationsByType trong Java

## Mục tiêu học tập

Từ Java 8, **repeatable annotation** cho phép gắn nhiều annotation **cùng một loại** lên một khai báo hoặc vị trí sử dụng kiểu, thay vì phải tự viết nhiều annotation có tên khác nhau. Khi đọc những annotation ấy bằng reflection, hai phương thức quan trọng là:

- **AnnotatedElement.getAnnotationsByType(Class<T> annotationClass)**
- **AnnotatedElement.getDeclaredAnnotationsByType(Class<T> annotationClass)**

Cả hai trả về **mảng annotation** cùng loại và hiểu cơ chế **container annotation** của **@Repeatable**. Điểm khác biệt lớn nhất nằm ở việc có xét annotation được **kế thừa theo quy tắc @Inherited** hay không.

Bài học giúp bạn phân biệt annotation xuất hiện trực tiếp với annotation được chứa trong container; hiểu tại sao **getAnnotation** có thể trả null dù **getAnnotationsByType** tìm thấy nhiều annotation; phân biệt declared với inherited; hiểu tại sao @Inherited chỉ liên quan đến **lớp** chứ không làm annotation trên method tự kế thừa khi override; và áp dụng API reflection này vào những hệ thống cần đọc metadata thực sự.

Các API này được giới thiệu từ Java 8 và vẫn còn phù hợp trên các phiên bản Java hiện đại. Ví dụ đầy đủ dùng Java 8-compatible API, có lệnh biên dịch và đầu ra xác định; không sử dụng kiến thức đã lỗi thời hoặc legacy.

## 1. Bối cảnh: vì sao annotation có thể lặp lại?

Giả sử một phương thức được đánh dấu bằng hai nhãn độc lập:

~~~java
@Label("stable")
@Label("public")
void handle() {
}
~~~

Đoạn này là **mã minh họa**, giả định **Label** là một annotation đã được khai báo là repeatable. Chữ ký Java thông thường không cho phép lặp cùng một annotation type ở một vị trí nếu annotation type đó không được cấu hình lặp lại.

Với repeatable annotation, một vị trí có thể mang nhiều phần tử metadata cùng loại. Điều này hữu ích cho những tình huống như nhiều nhãn, nhiều quy tắc lựa chọn, nhiều thông tin cấu hình độc lập hoặc nhiều điều kiện gắn cho cùng một phần tử chương trình.

Định nghĩa cơ bản:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Labels {
    Label[] value();
}
~~~

Đây là **hai khai báo annotation hoàn chỉnh** ở mức minh họa; để tạo chương trình chạy độc lập, cần đặt chúng trong tệp hoặc lớp hợp lệ. Những thành phần cần hiểu:

1. **@Repeatable(Labels.class)** trên Label chỉ ra **container annotation type**.
2. Container **Labels** phải có phần tử tên **value()** trả về **Label[]**.
3. Annotation Label và container phải thỏa các ràng buộc về target, retention và các quy tắc annotation type của Java. Ví dụ trên cho cả hai target METHOD và retention RUNTIME.
4. **@Retention(RUNTIME)** được chọn để reflection runtime nhìn thấy metadata. Nếu mục tiêu chỉ là phân tích source hoặc class file, retention và công cụ đọc cần được thiết kế phù hợp.
5. Việc định nghĩa annotation **không tự làm bất kỳ business rule nào được thực thi**. Reflection chỉ đọc metadata; logic tiêu thụ metadata phải được viết riêng.

Nói ngắn gọn, **Label** là annotation được lặp, còn **Labels** là container biểu diễn nhiều Label tại cùng một vị trí.

## 2. Hai phương thức cần học có chữ ký gì?

**java.lang.reflect.AnnotatedElement** cung cấp các phương thức generic:

~~~java
<T extends java.lang.annotation.Annotation>
T[] getAnnotationsByType(Class<T> annotationClass);

<T extends java.lang.annotation.Annotation>
T[] getDeclaredAnnotationsByType(Class<T> annotationClass);
~~~

Đây là **chữ ký giản lược để học**, không phải đoạn triển khai Java cần tự tạo. Cả hai nhận **Class<T>** biểu diễn loại annotation mà bạn muốn tìm và trả **T[]**.

Ví dụ:

~~~java
Label[] all = method.getAnnotationsByType(Label.class);
Label[] own = method.getDeclaredAnnotationsByType(Label.class);
~~~

Đây là đoạn minh họa, giả sử **method** là một java.lang.reflect.Method và Label đã được định nghĩa. Với method được gắn hai Label, hai mảng thường chứa cùng hai annotation theo thứ tự được khai báo.

**Nếu không tìm thấy annotation**, phương thức trả về **mảng rỗng**, không phải null. Vì vậy có thể viết:

~~~java
if (method.getDeclaredAnnotationsByType(Label.class).length == 0) {
    // Không tìm thấy Label được khai báo trực tiếp hoặc chứa gián tiếp.
}
~~~

Đoạn này chỉ minh họa ý nghĩa. Không nên viết **if (annotations == null)** để kiểm tra không có kết quả: hợp đồng của hai API này trả mảng rỗng.

**Không dùng tên annotation type dưới dạng chuỗi**: đối số là một **Class object**, ví dụ Label.class, không phải "Label". Kiểu generic giúp kết quả được kiểm tra là Label[] và giảm nhu cầu ép kiểu thủ công.

## 3. “Directly present”, “indirectly present” và “inherited” khác nhau thế nào?

Từ vựng trong Java reflection về repeatable annotations có ý nghĩa kỹ thuật:

**Directly present (hiện diện trực tiếp):** annotation của loại T được gắn ngay lên phần tử và được biểu diễn như annotation T. Ví dụ một phương thức chỉ có **@Label("one")** thường có Label hiện diện trực tiếp.

**Indirectly present (hiện diện gián tiếp qua container):** annotation T nằm trong **mảng value()** của container được gắn lên phần tử, chẳng hạn metadata biểu diễn hai **@Label(...)** như một **@Labels(...)** chứa hai Label. Phương thức *ByType* hiểu cách tìm các annotation con này.

**Inherited (được kế thừa):** annotation type được đánh dấu **@Inherited** và phần tử đang xét là **lớp** thỏa quy tắc kế thừa Java. Khi không tìm được T trực tiếp hoặc gián tiếp trên lớp đang xét, API không có chữ Declared có thể tìm trên superclass tương ứng.

Điều quan trọng là **indirectly present không có nghĩa là inherited**. Một Label được tìm thấy trong container ngay trên phương thức vẫn thuộc phương thức đó; nó không phải annotation được lấy từ lớp cha.

### Bảng phân biệt nhanh

| Nơi tìm thấy | Ví dụ | getDeclaredAnnotationsByType | getAnnotationsByType |
| --- | --- | --- | --- |
| Một T trực tiếp | Một @Label trên phương thức | Có | Có |
| Nhiều T trong container | Hai @Label trên phương thức | Có, giải container | Có, giải container |
| Không có T tại phần tử | Phương thức không gắn Label | Mảng rỗng | Mảng rỗng, trừ quy tắc kế thừa thực sự áp dụng |
| T được kế thừa từ superclass | Lớp con không khai báo T, T là @Inherited | Mảng rỗng | Có thể nhận T từ superclass |
| T chỉ nằm trên interface | Lớp implements interface | Không | Không nhận chỉ vì implements interface |
| T nằm trên method bị override | Method con không khai báo T | Không | Không tự kế thừa metadata của method cha |

**Chỉ cần nhớ một ý:** phương thức có chữ **Declared** không tự tìm annotation kế thừa; phương thức không có chữ Declared có thể xét inheritance **khi quy tắc Java cho phép**, không phải lúc nào cũng kế thừa.

## 4. Container thực sự liên quan như thế nào?

Để hiểu vì sao có hai API *ByType*, xét:

~~~java
@Label("alpha")
@Label("beta")
void process() {
}
~~~

Khi được biên dịch theo cơ chế repeatable annotation, nhiều lần dùng Label trên cùng phần tử thường được biểu diễn thông qua **container Labels**. Hãy hình dung metadata tương đương về ý tưởng với:

~~~java
@Labels({
    @Label("alpha"),
    @Label("beta")
})
void process() {
}
~~~

Đây là **hai cách khai báo thay thế**, không viết cùng lúc trên cùng phương thức để diễn đạt một tập lặp đơn giản. Kết quả tìm theo loại **Label.class** bằng *ByType* có thể nhận được hai phần tử "alpha" và "beta" mà không cần bên gọi tự biết tên container.

Nhờ đó, mã đọc annotation nhất quán:

~~~java
Label[] labels = method.getDeclaredAnnotationsByType(Label.class);
for (Label label : labels) {
    System.out.println(label.value());
}
~~~

Dù nguồn viết nhiều @Label hay viết @Labels chứa các Label, mã đọc theo loại Label vẫn đơn giản.

### Lưu ý: container là metadata có thật

Trong trường hợp nhiều annotation được chứa, các API reflection **không có hậu tố ByType** có thể nhìn thấy container **Labels** thay vì các Label riêng lẻ. Ví dụ:

~~~java
Label single = method.getAnnotation(Label.class);
Labels container = method.getAnnotation(Labels.class);
~~~

Với phương thức chứa **hai Label lặp**, **single** thường là null vì không có một Label hiện diện trực tiếp duy nhất theo cách API này tìm; **container** có thể hiện diện. Ngược lại, **getAnnotationsByType(Label.class)** trả cả hai Label.

Với phương thức chỉ có **một @Label**, **getAnnotation(Label.class)** có thể trả chính annotation đó, còn không nhất thiết có container. Đừng dùng **getAnnotation(Label.class)** để đọc dữ liệu repeatable rồi kết luận “không có nhãn” nếu nó trả null.

**Quy tắc thực hành:** khi annotation type được khai báo @Repeatable và bạn muốn toàn bộ giá trị cùng loại, dùng **getAnnotationsByType** hoặc **getDeclaredAnnotationsByType**, không tự phụ thuộc hình dạng lưu container.

## 5. Ví dụ Java hoàn chỉnh: đọc repeatable annotations trên method

Tạo tệp **RepeatableMethodLookupDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class RepeatableMethodLookupDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @Repeatable(Labels.class)
    @interface Label {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Labels {
        Label[] value();
    }

    static class Service {
        @Label("api")
        @Label("stable")
        public void execute() {
        }

        @Label("single")
        public void onlyOne() {
        }

        public void plain() {
        }
    }

    static String values(Label[] labels) {
        return Arrays.stream(labels)
            .map(Label::value)
            .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) throws Exception {
        Method repeated =
            Service.class.getDeclaredMethod("execute");
        Method single =
            Service.class.getDeclaredMethod("onlyOne");
        Method plain =
            Service.class.getDeclaredMethod("plain");

        System.out.println("Repeated/all: " +
            values(repeated.getAnnotationsByType(Label.class)));

        System.out.println("Repeated/declared: " +
            values(repeated.getDeclaredAnnotationsByType(Label.class)));

        System.out.println("Repeated/direct Label: " +
            (repeated.getDeclaredAnnotation(Label.class) != null));

        System.out.println("Repeated/container: " +
            (repeated.getDeclaredAnnotation(Labels.class) != null));

        System.out.println("Single/all: " +
            values(single.getAnnotationsByType(Label.class)));

        System.out.println("Single/direct Label: " +
            (single.getDeclaredAnnotation(Label.class) != null));

        System.out.println("Plain/all: " +
            values(plain.getAnnotationsByType(Label.class)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RepeatableMethodLookupDemo.java
java RepeatableMethodLookupDemo
~~~

Đầu ra:

~~~text
Repeated/all: [api, stable]
Repeated/declared: [api, stable]
Repeated/direct Label: false
Repeated/container: true
Single/all: [single]
Single/direct Label: true
Plain/all: []
~~~

**Phân tích từng phần:**

1. **execute()** dùng Label hai lần; reflection tìm hai annotation bằng cả hai phương thức *ByType*. Method không có cơ chế inheritance annotation theo @Inherited của class, vì vậy kết quả all/declared giống nhau trong tình huống này.
2. **getDeclaredAnnotation(Label.class)** không giải container thành hai Label riêng lẻ như phương thức *ByType*, nên không thấy Label trực tiếp ở trường hợp repeat.
3. **getDeclaredAnnotation(Labels.class)** cho thấy container của hai Label có mặt.
4. **onlyOne()** có một Label, nên phương thức single-annotation lookup và *ByType* đều có thể thấy Label đó.
5. **plain()** không có Label: *ByType* trả mảng rỗng, biểu diễn bởi **[]**.
6. Thứ tự hiển thị của hai Label đúng với thứ tự khai báo trong ví dụ. Khi dựa vào repeatable annotation như một tập quy tắc có thứ tự, hãy xác định hợp đồng về thứ tự và tránh tự dùng cấu trúc không có thứ tự rồi giả định kết quả giống lúc khai báo.

Ở ứng dụng thực tế, đôi khi chỉ cần đọc những annotation được khai báo ngay trên method nên **getDeclaredAnnotationsByType** thể hiện ý định rất rõ. Khi bạn viết công cụ chung làm việc với cả lớp và các phần tử reflection khác, hãy cân nhắc ngữ nghĩa inherited của phiên bản không có chữ Declared.

## 6. So sánh bốn API đọc annotation

Ngoài hai phương thức chính, AnnotatedElement còn có các API tương tự nhưng **không giải repeatable container theo cùng cách**:

| API | Kết quả | Có tự giải container T lặp? | Inheritance |
| --- | --- | --- | --- |
| **getAnnotation(T.class)** | Một T hoặc null | Không đọc toàn bộ T nằm trong container | Theo semantics của annotation có thể inherited |
| **getDeclaredAnnotation(T.class)** | Một T hoặc null | Không đọc toàn bộ T nằm trong container | Không xét inherited |
| **getAnnotationsByType(T.class)** | T[] | Có, gồm trực tiếp/gián tiếp | Có thể xét @Inherited trên class |
| **getDeclaredAnnotationsByType(T.class)** | T[] | Có, gồm trực tiếp/gián tiếp | Không xét inherited |
| **getAnnotations()** | Annotation[] | Trả annotation theo representation được thấy, container có thể xuất hiện | Có thể có annotation inherited |
| **getDeclaredAnnotations()** | Annotation[] | Trả annotation khai báo tại phần tử, container có thể xuất hiện | Không xét inherited |

Bảng nhấn mạnh câu hỏi **“Muốn một annotation hay toàn bộ annotation của loại lặp?”**. Nếu bạn đang viết một engine đọc repeatable annotation, hãy bắt đầu từ hai phương thức *ByType* thay vì tự dò container thủ công trong **getAnnotations()**.

**Tại sao không luôn dùng getAnnotationsByType?** Vì một công cụ như code generator đôi khi chỉ muốn những annotation **được khai báo ngay trên lớp hiện tại**, không muốn kế thừa cấu hình từ lớp cha. Khi đó **getDeclaredAnnotationsByType** có nghĩa chính xác hơn và tránh nhận metadata ngoài ý định.

## 7. Điểm khác biệt lớn nhất: @Inherited và lớp con

Giả sử annotation type được đánh dấu **@Inherited**:

~~~java
@java.lang.annotation.Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}
~~~

Đây là đoạn định nghĩa minh họa. @Inherited cho phép **class-level annotation** truyền từ superclass xuống subclass theo quy tắc reflection khi subclass không có annotation thuộc cùng loại trực tiếp hoặc gián tiếp.

Vì Role là repeatable, container cũng cần phù hợp quy tắc @Inherited:

~~~java
@java.lang.annotation.Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
~~~

Hai khai báo này dùng để minh họa. Annotation type Role có **@Repeatable(Roles.class)**, và cả Role lẫn Roles mang **@Inherited** để quan hệ inheritance của repeatable annotation hợp lệ.

Nếu có:

~~~java
@Role("read")
@Role("write")
class Parent {
}

class Child extends Parent {
}
~~~

thì:

~~~java
Role[] inherited = Child.class.getAnnotationsByType(Role.class);
Role[] declared = Child.class.getDeclaredAnnotationsByType(Role.class);
~~~

về ý nghĩa sẽ cho:

- **inherited**: hai Role từ Parent được tìm theo quy tắc inheritance.
- **declared**: mảng rỗng, vì Child không tự khai báo Role trực tiếp hoặc gián tiếp.

**Không có chữ Declared** không phải “tìm cả class và tất cả interface, superinterface, method đã override”. Quy tắc @Inherited của Java chủ yếu hoạt động trên **superclass chain**, và chỉ khi annotation type được thiết kế cho phép inheritance.

### Subclass có annotation riêng thì sao?

Nếu Child tự khai báo một Role, ví dụ **@Role("admin")**, **getAnnotationsByType(Role.class)** lấy Role của Child thay vì tự hợp nhất toàn bộ Role của Parent vào một mảng.

Đây là chỗ rất dễ nhầm: **@Inherited không mặc nhiên merge các danh sách annotation từ cha và con**. Khi subclass có Role trực tiếp/gián tiếp, cấu hình của subclass thường **che nhóm Role từ superclass** theo quy tắc tìm kiếm.

Nếu nghiệp vụ muốn **gộp quyền từ mọi lớp trong hệ thừa kế**, bạn phải xây chính sách duyệt cây lớp và ghép dữ liệu riêng, không coi kết quả của getAnnotationsByType là một phép cộng dồn mọi Role.

## 8. Ví dụ Java hoàn chỉnh: inherited so với declared

Tạo tệp **InheritedRepeatableLookupDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

public class InheritedRepeatableLookupDemo {

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Roles.class)
    @interface Role {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Roles {
        Role[] value();
    }

    @Role("reader")
    @Role("writer")
    static class Parent {
    }

    static class Child extends Parent {
    }

    @Role("admin")
    static class OwnChild extends Parent {
    }

    @Role("interface")
    interface Contract {
    }

    static class ImplementsContract implements Contract {
    }

    static String values(Role[] roles) {
        return Arrays.stream(roles)
            .map(Role::value)
            .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Parent all: " +
            values(Parent.class.getAnnotationsByType(Role.class)));

        System.out.println("Child all: " +
            values(Child.class.getAnnotationsByType(Role.class)));

        System.out.println("Child declared: " +
            values(Child.class.getDeclaredAnnotationsByType(Role.class)));

        System.out.println("OwnChild all: " +
            values(OwnChild.class.getAnnotationsByType(Role.class)));

        System.out.println("OwnChild declared: " +
            values(OwnChild.class.getDeclaredAnnotationsByType(Role.class)));

        System.out.println("Implements interface: " +
            values(ImplementsContract.class
                .getAnnotationsByType(Role.class)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InheritedRepeatableLookupDemo.java
java InheritedRepeatableLookupDemo
~~~

Đầu ra:

~~~text
Parent all: [reader, writer]
Child all: [reader, writer]
Child declared: []
OwnChild all: [admin]
OwnChild declared: [admin]
Implements interface: []
~~~

Phân tích:

- **Parent** có hai Role được chứa bằng cơ chế repeatable, nên getAnnotationsByType trả cả hai.
- **Child** không khai báo Role và extends Parent; vì Role/Roles có @Inherited, bản không Declared nhìn thấy các Role inherited.
- **Child.getDeclaredAnnotationsByType(Role.class)** trả mảng rỗng do Child không tự gắn Role.
- **OwnChild** tự có @Role("admin"), vì vậy kết quả *ByType* trên OwnChild là [admin], không phải [reader, writer, admin]. Default inheritance không phải merge.
- **ImplementsContract** implements một interface được đánh dấu Role, nhưng @Inherited **không truyền annotation từ interface sang implementing class** theo quy tắc class inheritance. Vì vậy kết quả là [].

**Kết luận thực hành:** với hệ thống cần đọc metadata kiểu, trước hết hãy xác định muốn **cấu hình ngay trên class hiện tại** hay **cấu hình có thể inherited từ superclass**. Nếu cần tổng hợp cả interface hoặc ancestor bất kỳ, phải định nghĩa thuật toán traversal riêng và nêu rõ quy tắc ưu tiên.

## 9. @Inherited không áp dụng như kế thừa annotation của method

Một hiểu nhầm thường gặp là: đặt **@Inherited** lên annotation type rồi annotation đó tự chuyển từ phương thức bị override của class cha sang phương thức tương ứng ở class con.

Điều này **không đúng**. @Inherited có ngữ nghĩa kế thừa từ superclass đối với **class declarations**. Một phương thức override là một phần tử khai báo khác; không có cơ chế Java reflection mặc định tự chuyển annotation của method cha sang method con chỉ vì tên/chữ ký giống nhau.

Ví dụ:

~~~java
class Parent {
    @Audit("parent")
    public void run() {
    }
}

class Child extends Parent {
    @Override
    public void run() {
    }
}
~~~

Đây là đoạn minh họa, cần khai báo annotation Audit. Nếu lấy Method được khai báo trong Child và gọi **getAnnotationsByType(Audit.class)**, nó không tự đọc @Audit từ Method của Parent.

Muốn chính sách “method override kế thừa annotation từ method cha” cho framework của bạn, cần **tự duyệt method hierarchy**, xử lý bridge methods, signature, interface methods và các trường hợp overload một cách cẩn thận. Một số framework có quy tắc riêng, không nên nhầm quy tắc của framework với hành vi mặc định của java.lang.reflect.

### Phân biệt getMethod và getDeclaredMethod

- **Class.getDeclaredMethod(name, ...)** tìm method được **khai báo ngay trên class**, không tìm inherited methods.
- **Class.getMethod(name, ...)** tìm public method phù hợp, bao gồm các phương thức public inherited theo quy tắc reflection.

Vì vậy nếu Child **không override** method và bạn dùng **Child.class.getMethod("run")**, object Method có thể đại diện cho method được khai báo ở Parent. Khi đọc annotation trên Method đó, bạn nhìn thấy annotation của chính method Parent; điều này **không chứng minh annotation method được tự kế thừa**.

Muốn thử nghiệm một cách rõ ràng, hãy dùng Child **có override thật** và **Child.class.getDeclaredMethod(...)** để chắc chắn đang đọc method của Child.

## 10. Ví dụ Java hoàn chỉnh: override không kéo theo method annotation

Tạo tệp **MethodOverrideAnnotationDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class MethodOverrideAnnotationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @Repeatable(Audits.class)
    @interface Audit {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Audits {
        Audit[] value();
    }

    static class Parent {
        @Audit("checked")
        @Audit("logged")
        public void run() {
        }
    }

    static class Child extends Parent {
        @Override
        public void run() {
        }
    }

    static String values(Audit[] audits) {
        return Arrays.stream(audits)
            .map(Audit::value)
            .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) throws Exception {
        Method parent =
            Parent.class.getDeclaredMethod("run");
        Method child =
            Child.class.getDeclaredMethod("run");

        System.out.println("Parent declared: " +
            values(parent.getDeclaredAnnotationsByType(Audit.class)));

        System.out.println("Parent all: " +
            values(parent.getAnnotationsByType(Audit.class)));

        System.out.println("Child declared: " +
            values(child.getDeclaredAnnotationsByType(Audit.class)));

        System.out.println("Child all: " +
            values(child.getAnnotationsByType(Audit.class)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MethodOverrideAnnotationDemo.java
java MethodOverrideAnnotationDemo
~~~

Đầu ra:

~~~text
Parent declared: [checked, logged]
Parent all: [checked, logged]
Child declared: []
Child all: []
~~~

**Giải thích:** phương thức Parent.run có hai annotation Audit. Child.run là một method được khai báo lại và **không có Audit**, nên cả hai *ByType* trên Method của Child đều trả mảng rỗng. Không có annotation inheritance tự động trên method trong Java reflection chuẩn.

Ví dụ dùng các phương thức public với tên và danh sách tham số giống nhau; không cần tạo instance hay thực thi run() để đọc annotation metadata.

## 11. @Inherited và repeatable container: cần đúng cả hai phía

Một annotation repeatable có thể có mối quan hệ inheritance, nhưng **@Inherited phải được khai báo nhất quán** với container tương ứng theo các quy tắc của Java.

Mẫu đúng cho annotation trên class:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Policies.class)
@interface Policy {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policies {
    Policy[] value();
}
~~~

Đây là một đoạn minh họa cần import các annotation types và đặt tại vị trí khai báo annotation type hợp lệ.

Nếu bạn thêm @Inherited vào annotation được lặp mà không thiết kế container cho phù hợp, compiler có thể báo lỗi ở khai báo annotation type. Không nên sửa bằng cách xóa retention hoặc dùng raw reflection; hãy bảo đảm cấu hình **@Repeatable**, container, target và retention tương thích.

### @Inherited chỉ có ý nghĩa ở một số phần tử

Theo semantics của @Inherited, cơ chế tìm annotation từ superclass **liên quan đến class**, không tự lan qua các interface implements hoặc các method đã override. Ngay cả khi bạn viết một annotation type có target METHOD và đánh dấu @Inherited, điều đó không làm annotation method tự truyền sang overriding method.

**Tại sao cần hiểu điều này?** Nhiều framework dùng annotations ở method/controller/service. Chúng có thể cung cấp cơ chế thừa kế metadata riêng; khi code trực tiếp đọc **Method.getAnnotationsByType(...)**, hãy dựa trên hợp đồng của Java reflection, không dựa trên kinh nghiệm từ framework khác.

## 12. Annotation retention và target vẫn quyết định metadata nào đọc được

Để hai phương thức *ByType* dùng được trong runtime reflection, annotation cần được lưu với **RetentionPolicy.RUNTIME**. Nếu dùng:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
@Repeatable(Hints.class)
@interface Hint {
    String value();
}
~~~

thì thông tin đó không được giữ như annotation runtime thông thường để tìm qua reflection. Đây là đoạn minh họa; container Hints cũng phải được định nghĩa với các ràng buộc tương thích.

Ba mức retention:

| Retention | Tình huống thường gặp | Runtime reflection có đọc trực tiếp bằng *ByType*? |
| --- | --- | --- |
| **SOURCE** | Thông tin dùng khi xử lý source | Không |
| **CLASS** | Metadata giữ trong class file cho công cụ phân tích bytecode | Không theo reflection runtime tiêu chuẩn |
| **RUNTIME** | Metadata cần tra cứu bằng reflection khi chạy | Có, nếu đặt đúng vị trí và sử dụng đúng API |

**@Target** xác định annotation được phép gắn ở đâu. Ví dụ **ElementType.METHOD** cho method declaration, **ElementType.TYPE** cho class/interface/annotation type declaration, **ElementType.TYPE_USE** cho vị trí sử dụng kiểu. Nếu gắn sai target, lỗi thuộc về cú pháp/hợp đồng annotation tại compile time, không phải lỗi của phương thức *ByType*.

### Type-use repeatable annotation và AnnotatedType

Nếu một repeatable annotation được đặt lên kiểu generic như **List<@Tag("a") @Tag("b") String>**, metadata ở **type argument** không nằm trực tiếp trên Class hoặc Field declaration. Để đọc đúng, bạn có thể cần:

- **Field.getAnnotatedType()** để lấy kiểu được chú thích.
- **AnnotatedParameterizedType.getAnnotatedActualTypeArguments()** để tìm phần tử kiểu trong generic.
- **AnnotatedType.getAnnotationsByType(Tag.class)** hoặc bản Declared theo nhu cầu, với annotation runtime và vị trí thích hợp.

Đây là các API còn áp dụng trong Java hiện đại. Lưu ý rằng **Field.getAnnotationsByType(Tag.class)** đọc annotation trên phần tử Field theo quy tắc của Field, không tự đi sâu vào mọi generic type argument.

**Bài này tập trung vào hai phương thức *ByType***; việc duyệt type-use metadata chỉ là phần mở rộng để bạn chọn đúng AnnotatedElement khi cần.

## 13. Lấy annotation từ class khác đọc từ method

Sự khác biệt nằm ở **đối tượng được hỏi**:

~~~java
Role[] roles =
    SomeClass.class.getAnnotationsByType(Role.class);

Method method = SomeClass.class.getDeclaredMethod("execute");

Label[] labels =
    method.getDeclaredAnnotationsByType(Label.class);
~~~

Đây là đoạn minh họa cần khai báo SomeClass, Role, Label. Đối tượng **Class** và **Method** đều thực hiện interface AnnotatedElement, nhưng inheritance của annotation không phải tính năng giống nhau trên mọi kind of element.

**Class:** khi annotation type có @Inherited và class hiện tại thiếu annotation trực tiếp/gián tiếp, getAnnotationsByType có thể nhìn lên superclass theo hợp đồng.

**Method:** getAnnotationsByType tìm annotation liên quan tới chính Method đó; không tự truy ngược overriding method cùng chữ ký của superclass.

**Field:** không có quy tắc annotation field inherited tương tự class annotation. Field được khai báo ở class cha vẫn là Field riêng; Field được khai báo ở class con là phần tử khác ngay cả khi tên giống.

**Constructor:** constructor không được inherited như method instance, nên không có ý nghĩa tìm annotation của constructor từ class cha để dùng cho constructor con theo @Inherited.

**Package/module/type-use:** phải xét loại phần tử cụ thể và API reflection tương ứng. Đừng áp một quy tắc inheritance duy nhất cho tất cả AnnotatedElement.

## 14. Khi nào nên chọn phương thức nào?

Hãy chọn theo **chính sách metadata** mà ứng dụng cần.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Đọc toàn bộ repeatable annotation trực tiếp hoặc chứa gián tiếp trên một method | **method.getDeclaredAnnotationsByType(T.class)** |
| Đọc repeatable annotation trên một class và **cho phép @Inherited** hoạt động | **clazz.getAnnotationsByType(T.class)** |
| Đọc repeatable annotation **chỉ thuộc class hiện tại** | **clazz.getDeclaredAnnotationsByType(T.class)** |
| Xây lệnh xử lý dựa trên một danh sách annotation có thể kế thừa từ superclass theo hợp đồng | **getAnnotationsByType** kết hợp kiểm tra @Inherited và chính sách phù hợp |
| Đọc annotation của một type argument được chú thích | Lấy **AnnotatedType** thích hợp rồi gọi *ByType* trên đó |
| Muốn **hợp nhất** annotation từ nhiều superclass/interface theo quy tắc tùy chỉnh | Tự duyệt hệ phân cấp và merge; không chỉ gọi *ByType* một lần |
| Chỉ cần biết một annotation không repeatable có mặt trực tiếp hay không | **getDeclaredAnnotation(T.class)** có thể đủ |
| Đọc repeatable annotation trong một engine/framework | Ưu tiên **ByType**, kiểm tra retention/target và chính sách inheritance |

**Chú ý về những lớp có annotation riêng:** khi class con có T trực tiếp hoặc gián tiếp, *ByType* không tự thêm các T từ superclass thành một danh sách. Nếu dự án muốn “tổng hợp roles từ cha và con”, đó là một **chính sách nghiệp vụ khác** và cần implement rõ.

## 15. Đừng nhầm loại annotation với tên phần tử metadata

Một số tên tương tự nhưng không đồng nghĩa:

- **getAnnotationsByType(T.class)**: tìm nhiều annotation T, bao gồm T chứa trong repeatable container; có thể xét class inheritance.
- **getDeclaredAnnotationsByType(T.class)**: tương tự nhưng chỉ tìm tại phần tử hiện tại.
- **getAnnotation(Container.class)**: tìm **container annotation type**, không phải cùng một lời gọi như tìm T.
- **getDeclaredAnnotations()**: trả các annotation khai báo trực tiếp theo representation; không flatten toàn bộ repeatable annotation như *ByType*.
- **getParameterAnnotations()**: API trên Executable/Method cho annotation của parameter declaration, không phải cách tổng quát để lấy mọi type-use annotation.
- **getAnnotatedParameterTypes()**: thông tin kiểu của các tham số, phù hợp khi annotation nằm trên type use.

Một quy tắc thiết kế tốt là **chọn annotation type T theo ý nghĩa nghiệp vụ**, rồi gọi *ByType* với T.class thay vì bắt bên gọi phải biết container name.

Ví dụ nếu API của bạn có **@Route** lặp lại và **@Routes** container, một người dùng muốn tìm các route nên dùng **getDeclaredAnnotationsByType(Route.class)**. Như vậy mã sẽ ít phụ thuộc vào cách compiler biểu diễn container.

## 16. Một repeatable annotation có thể dùng cho nhiều mục đích, nhưng không tự chạy

Dù một phương thức có:

~~~java
@Policy("audit")
@Policy("rate-limit")
void handle() {
}
~~~

đây vẫn chỉ là **metadata** nếu không có code hoặc framework sử dụng nó. **getAnnotationsByType(Policy.class)** có thể giúp lấy cả hai Policy, nhưng **không tự làm hệ thống ghi audit hay áp rate limit**.

Một framework muốn thực thi các policy phải:

1. Đọc annotation đúng vị trí.
2. Ánh xạ giá trị annotation thành logic xử lý.
3. Định nghĩa cách kết hợp nhiều annotation và thứ tự áp dụng.
4. Có một đường thực thi **chắc chắn kích hoạt** logic đó.
5. Định nghĩa cách báo lỗi và kiểm thử các tình huống không có annotation, một annotation và nhiều annotation.
6. Xác định inheritance chính xác: dùng superclass fallback, merge các levels hay không cho kế thừa.

**Annotation được tìm thấy không có nghĩa policy được thực thi.** Phương thức reflection chỉ trả dữ liệu để bên gọi tự đưa ra quyết định.

## 17. Những lỗi hay gặp

| Lỗi hoặc giả định | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Dùng **getAnnotation(T.class)** rồi thấy null khi gắn T hai lần | Repeatable annotation có thể được lưu qua container | Dùng **getAnnotationsByType(T.class)** |
| Tưởng **getAnnotationsByType** chỉ tìm annotation viết trực tiếp trên phần tử | Có thể giải container và xét inheritance | Đọc đúng semantics direct/indirect/inherited |
| Tưởng **getDeclaredAnnotationsByType** không giải repeatable container | Declared chỉ nói về inheritance, không tắt việc giải container | Dùng declared để lấy tất cả T thuộc phần tử hiện tại |
| Tưởng cả hai API trả null khi không tìm thấy | Hợp đồng trả mảng T[] rỗng | Kiểm tra length hoặc stream |
| Tưởng @Inherited tự merge annotation từ cha/con | Class có T riêng thường che nhóm T từ cha | Tự thiết kế merge nếu nghiệp vụ cần |
| Tưởng @Inherited truyền annotation từ interface sang class implements | Inheritance của @Inherited dựa trên superclass chain | Duyệt interface riêng nếu cần |
| Tưởng method override tự kế thừa annotation | Method con là phần tử khác | Tự duyệt method hierarchy hoặc dùng framework có quy tắc rõ |
| Nhầm **Child.class.getMethod** với **getDeclaredMethod** | getMethod có thể lấy public method inherited | Kiểm tra **Method.getDeclaringClass()** |
| Chỉ gắn @Inherited cho repeatable T mà bỏ container | Có thể vi phạm quy tắc nhất quán annotation | Khai báo cả T và container hợp lệ |
| Quên RUNTIME retention khi dùng reflection | Annotation không hiện qua API runtime tiêu chuẩn | Chọn retention tương thích khi thiết kế |
| Gắn annotation lên type argument nhưng đọc Field declaration | Hỏi sai AnnotatedElement | Dùng getAnnotatedType và AnnotatedType thích hợp |
| Tưởng **getAnnotations()** luôn trả từng T đã lặp | Có thể thấy container thay vì T riêng lẻ | Dùng *ByType* nếu cần các T |
| Tưởng @Repeatable tự chạy validation | Annotation chỉ là metadata | Viết/kích hoạt cơ chế xử lý |
| Gộp annotation từ nhiều nguồn mà không định nghĩa thứ tự | Dễ có policy bất ngờ | Thiết kế rõ precedence/merge |
| Dùng raw annotation type Class | Mất một phần kiểm tra generic | Truyền T.class có kiểu rõ |

### Lỗi biên dịch ở định nghĩa container

Đôi khi compiler báo lỗi ngay tại **@Repeatable(Container.class)**, không phải tại chỗ dùng annotation. Khi đó cần kiểm tra:

- Container có **value()** với return type **T[]** chính xác không?
- Retention của container có phù hợp loại T không?
- Target của container có hợp lệ so với target của T không?
- Nếu T có @Inherited, container đã khai báo @Inherited theo yêu cầu chưa?
- Nếu có những ràng buộc annotation type khác, ví dụ document/inherited semantics, đã được cấu hình nhất quán chưa?

Không sửa lỗi bằng cách bỏ toàn bộ annotation type safety hoặc chuyển sang xử lý tên bằng String trừ khi có lý do rõ ràng.

## 18. Trường hợp đặc biệt: chỉ một annotation hoặc container khai báo thủ công

Một annotation type có **@Repeatable(Container.class)** không có nghĩa lúc nào cũng xuất hiện container. Với một lần dùng duy nhất:

~~~java
@Label("only")
void one() {
}
~~~

Label có thể được biểu diễn như annotation đơn hiện diện trực tiếp. Với hai lần dùng:

~~~java
@Label("first")
@Label("second")
void two() {
}
~~~

container có thể xuất hiện để chứa các Label.

Bạn cũng có thể dùng container trực tiếp:

~~~java
@Labels({
    @Label("first"),
    @Label("second")
})
void two() {
}
~~~

Đây là **những khai báo minh họa thay thế**, không đồng thời khai báo nhiều method cùng chữ ký trên cùng class.

Cả hai cách viết có hai Label đều được **getDeclaredAnnotationsByType(Label.class)** trả về thành một mảng Label[] nếu retention và target phù hợp.

Nhưng một chương trình muốn kiểm tra **container object** vẫn có thể hỏi **getDeclaredAnnotation(Labels.class)**. Điều đó cho thấy mức trừu tượng khác nhau: **theo nội dung T** hoặc **theo container C**.

Trong phần lớn mã nghiệp vụ, người viết quan tâm tới các giá trị Label chứ không cần quan tâm compiler chọn representation nào. Vì vậy *ByType* là lựa chọn an toàn hơn khi làm việc với repeatable annotation.

## 19. Một số chi tiết về thứ tự và tính bất biến

Mảng do hai phương thức *ByType* trả về mô tả các annotation phù hợp tại thời điểm gọi. Trong chương trình ví dụ, các giá trị được in theo thứ tự xuất hiện trong nguồn. Nếu dùng annotation như một pipeline có thứ tự, cần xác nhận hợp đồng về thứ tự và cách khai báo, nhất là khi ứng dụng tự merge từ nhiều levels.

**Annotation interface instance** do reflection cung cấp có các phương thức lấy giá trị thành phần, ví dụ **label.value()**. Một annotation không phải một đối tượng cấu hình mutable thông thường mà bạn thay trực tiếp value qua setter. Nếu cần cấu hình động, hãy chuyển metadata thành cấu trúc dữ liệu ứng dụng riêng.

Các mảng trả về là kết quả truy vấn; bạn không nên chỉnh sửa mảng rồi mong việc đó thay đổi annotation lưu trong class file hoặc ảnh hưởng tới lần reflection sau. Thay đổi dữ liệu trả về của một lời gọi không sửa metadata biên dịch.

Nếu annotation có một thành phần là **mảng**, ví dụ **String[] paths()**, quy tắc về giá trị annotation và các mảng trả về cũng cần được hiểu theo hợp đồng của java.lang.annotation, thay vì coi annotation là một POJO có setter.

## 20. Thiết kế API reflection sử dụng hai phương thức này

Một API đọc cấu hình có thể cần chọn một trong ba chính sách:

**Chính sách A — chỉ đọc tại chỗ:** đọc declared annotations ngay trên class hoặc method đang xét. Hữu ích khi cấu hình con phải được khai báo độc lập và không tự thừa kế.

~~~java
Role[] roles =
    clazz.getDeclaredAnnotationsByType(Role.class);
~~~

**Chính sách B — superclass fallback:** khi annotation type có @Inherited và class con không khai báo Role, cho phép lấy Role từ superclass.

~~~java
Role[] roles =
    clazz.getAnnotationsByType(Role.class);
~~~

**Chính sách C — merge theo hệ phân cấp tùy chỉnh:** tự duyệt class/interface hierarchy, đọc declared ở từng nơi, rồi ghép theo một quy tắc rõ ràng. Ví dụ một hệ quyền có thể muốn union; một hệ cấu hình có thể muốn override; một hệ route có thể cấm trùng key.

Đây là **ba chính sách khác nhau**, không phải ba tên cho cùng hành vi. Chọn sai sẽ khiến lớp con nhận thiếu cấu hình hoặc nhận quá nhiều cấu hình ngoài dự kiến.

### Lưu ý về API public

Nếu xuất bản một annotation type repeatable, việc thay đổi container, target, retention hoặc @Inherited có thể ảnh hưởng tới mã sử dụng và cách reflection quan sát metadata. Đừng đổi các thuộc tính này tùy tiện khi đã có mã khách hàng phụ thuộc vào hành vi tra cứu.

Hãy viết test cho:

- Một annotation.
- Nhiều annotation.
- Không annotation.
- Container khai báo tường minh.
- Class con không có annotation riêng.
- Class con có annotation riêng.
- Interface có annotation.
- Method override có/không có annotation.
- Type-use annotation nếu API của bạn hỗ trợ vị trí đó.

Các test này bảo vệ hợp đồng reflection tốt hơn việc chỉ kiểm tra một trường hợp “có hai annotation” rồi giả định mọi trường hợp đều giống nhau.

## 21. Bài tập có đáp án

### Bài 1 — Chọn API để lấy tất cả nhãn

Một phương thức có **@Label("a") @Label("b")**. Muốn nhận cả "a" và "b" mà không đọc container thủ công, dùng gì?

**Đáp án:** **method.getDeclaredAnnotationsByType(Label.class)** hoặc **method.getAnnotationsByType(Label.class)**. Với method trong ví dụ và không có cơ chế inheritance annotation, kết quả cùng gồm hai Label. Chọn declared khi muốn nhấn mạnh annotation thuộc method hiện tại.

### Bài 2 — Vì sao getAnnotation trả null?

Một method có hai Label repeatable và **getAnnotation(Label.class)** trả null. Có nghĩa method không có Label?

**Đáp án:** không. Hai Label có thể được chứa trong container. Dùng **getAnnotationsByType(Label.class)** để lấy đầy đủ.

### Bài 3 — Hỏi class con

Role là @Inherited, Parent có hai Role, Child extends Parent và không khai báo Role. Dự đoán:

~~~java
Child.class.getAnnotationsByType(Role.class)
Child.class.getDeclaredAnnotationsByType(Role.class)
~~~

**Đáp án:** phương thức đầu có thể trả hai Role inherited theo quy tắc của Java; phương thức thứ hai trả mảng rỗng vì Child không khai báo trực tiếp/gián tiếp.

### Bài 4 — Class con thêm Role

Nếu Child tự khai báo **@Role("admin")**, getAnnotationsByType(Role.class) có tự trả "reader", "writer", "admin" không?

**Đáp án:** không. Từ superclass không được tự động merge với Role trực tiếp/gián tiếp ở subclass. Trong ví dụ, kết quả trên Child là [admin].

### Bài 5 — Interface

Một interface có @Role("contract"), class Impl implements interface đó. @Inherited có làm Impl.getAnnotationsByType(Role.class) tìm thấy Role ấy không?

**Đáp án:** không theo quy tắc @Inherited của class. Muốn xét interface, ứng dụng tự định nghĩa cách duyệt và xử lý metadata.

### Bài 6 — Method override

Parent.run có @Audit("logged"), Child override run nhưng không có Audit. Gọi **Child.class.getDeclaredMethod("run").getAnnotationsByType(Audit.class)** có nhận logged không?

**Đáp án:** không. Annotation trên method không tự được inherited qua override. Điều đó khác với **Class.getAnnotationsByType** cho class-level @Inherited.

### Bài 7 — getMethod khác getDeclaredMethod

Child không override Parent.run và bạn gọi **Child.class.getMethod("run")**. Nếu Method trả về có annotation của Parent, có chứng minh annotation method được kế thừa không?

**Đáp án:** không. Method có thể thực sự đại diện cho method Parent được tìm qua getMethod. Kiểm tra **method.getDeclaringClass()** để biết nơi khai báo.

### Bài 8 — Không có annotation

Khi không tìm thấy Role, phương thức *ByType* trả null hay một mảng trống?

**Đáp án:** **mảng trống**. Kiểm tra **roles.length == 0**.

### Bài 9 — Container retention

Vì sao cần xem retention của cả annotation lặp và container khi dùng reflection runtime?

**Đáp án:** vì việc lưu metadata và biểu diễn nhiều annotation phụ thuộc vào cả hai type. Thiết kế annotation và container phải tuân thủ ràng buộc retention, target và inheritance thích hợp.

### Bài 10 — Business rule

Một service có ba annotation @Policy, và reflection đọc được tất cả. Hệ thống có tự áp dụng cả ba policy không?

**Đáp án:** không. Reflection chỉ trả metadata. Code/framework phải chủ động xử lý các policy, xác định thứ tự, lỗi và đường kích hoạt.

## 22. Checklist khi làm việc với repeatable annotation trong dự án

**Trước khi đọc reflection:**

- Xác minh annotation type có **@Repeatable(Container.class)** và container khai báo **T[] value()** hợp lệ.
- Kiểm tra retention có phải RUNTIME nếu cần reflection lúc chạy.
- Xác định annotation đặt trên class, method, field hay type use.
- Quyết định có muốn inherited theo @Inherited trên superclass không.
- Xác định trường hợp không có annotation trả mảng rỗng sẽ được xử lý thế nào.

**Khi triển khai logic:**

- Chọn *ByType* để lấy tất cả T.
- Dùng declared khi chỉ muốn metadata được khai báo tại phần tử.
- Không kỳ vọng annotation method tự truyền qua override.
- Không kỳ vọng annotation trên interface tự có ở implementing class.
- Không kỳ vọng class-level @Inherited tự merge danh sách từ các superclass.
- Nếu cần merge, viết thuật toán traversal/precedence riêng và kiểm thử.
- Không coi annotation là runtime validator tự động.

**Khi kiểm thử và bảo trì:**

- Test sự khác biệt một T, nhiều T và explicit container.
- Test superclass fallback và subclass override.
- Test interface, method override và phần tử không annotated.
- Kiểm tra compiler báo lỗi ở định nghĩa repeatable annotation sai target/retention/inheritance.
- Ghi rõ chính sách metadata trong tài liệu API; đừng để người dùng suy đoán từ tên getAnnotationsByType.

## Tổng kết

**getAnnotationsByType(T.class)** và **getDeclaredAnnotationsByType(T.class)** đều đọc nhiều annotation cùng loại, hiểu cơ chế **@Repeatable** và giải annotation chứa gián tiếp qua container. Cả hai trả **T[]**, hoặc mảng rỗng nếu không có kết quả.

Sự khác biệt chính là **inheritance**: phiên bản không có chữ Declared có thể đọc annotation **@Inherited** từ superclass của một **lớp** khi lớp đó không có annotation T trực tiếp/gián tiếp; phiên bản có chữ Declared chỉ đọc annotation tại phần tử hiện tại. Hai API **không tự merge** nhiều mức cấu hình, **không tự kế thừa annotation từ interface**, và **không tự làm annotation trên method được kế thừa khi override**.

Khi sử dụng reflection, hãy xác định rõ **loại phần tử**, **retention**, **container**, **chính sách inheritance** và **cơ chế dùng metadata**. Chọn đúng phương thức sẽ giúp bạn đọc repeatable annotation nhất quán, thiết kế API dễ kiểm thử và tránh những lỗi rất khó tìm trong hệ thống dùng annotation ở nhiều cấp.