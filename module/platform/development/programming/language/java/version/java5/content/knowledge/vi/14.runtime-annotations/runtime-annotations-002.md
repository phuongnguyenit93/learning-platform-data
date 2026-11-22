# Đọc annotation trên lớp, phương thức, hàm tạo và trường

## 1. Từ annotation trong mã nguồn đến thông tin lúc chạy

Annotation có thể mang thông tin như mã thao tác, tên cấu hình hoặc phiên bản hợp đồng. Để một chương trình đọc thông tin đó lúc chạy, Java cung cấp reflection: ta lấy đối tượng mô tả lớp hoặc thành viên, rồi hỏi đối tượng ấy về annotation.

Có hai việc riêng:

1. **Tìm đúng phần tử:** lớp nào, phương thức có chữ ký nào, hàm tạo nào, trường nào?
2. **Đọc annotation trên phần tử đó:** có annotation cần tìm không, và các thuộc tính mang giá trị gì?

`Class<?>`, `Method`, `Constructor<?>` và `Field` đều hỗ trợ hợp đồng `AnnotatedElement`. Nhờ vậy, có thể dùng chung các phương thức đọc annotation. [API AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

Đọc annotation không tự gọi phương thức, không tạo đối tượng nghiệp vụ và không thay đổi giá trị trường. Ý nghĩa nghiệp vụ của annotation chỉ có hiệu lực khi có mã hay công cụ thực sự diễn giải nó.

## 2. Điều kiện để reflection đọc được

Annotation cần có `@Retention(RetentionPolicy.RUNTIME)`. Nếu bỏ `@Retention`, mặc định là `CLASS`: annotation có thể được lưu trong tệp class nhưng không được cung cấp qua các API reflection đọc annotation thông thường. [API Retention](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html)

Ví dụ khai báo, chưa phải chương trình độc lập:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR,
    ElementType.FIELD
})
@interface RuntimeTag {
    String value();
    int version() default 1;
}
```

`@Target` cho phép đặt annotation ở bốn vị trí của bài. Nó không thay thế `@Retention`: một annotation đặt đúng chỗ vẫn có thể không đọc được lúc chạy nếu chính sách lưu giữ không phù hợp.

## 3. Tìm đúng đối tượng mô tả

| Phần tử cần đọc | Đối tượng reflection | Ví dụ tìm trực tiếp trong Service |
| --- | --- | --- |
| Lớp | `Class<?>` | `Service.class` |
| Phương thức | `Method` | `Service.class.getDeclaredMethod("save", String.class)` |
| Hàm tạo | `Constructor<?>` | `Service.class.getDeclaredConstructor(String.class)` |
| Trường | `Field` | `Service.class.getDeclaredField("code")` |

Đối số kiểu tham số là một phần của việc chọn phương thức/hàm tạo. Nếu có `save()` và `save(String)`, hai lệnh `getDeclaredMethod("save")` và `getDeclaredMethod("save", String.class)` trả về hai phương thức khác nhau. Kiểu `int.class` cũng khác `Integer.class`; tên tham số trong mã nguồn không được dùng để phân biệt chữ ký. [API Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)

Không tìm thấy phương thức hoặc hàm tạo gây `NoSuchMethodException`; không tìm thấy trường gây `NoSuchFieldException`. Đây là lỗi ở **bước tìm phần tử**, khác với phần tử tồn tại nhưng không có annotation.

## 4. Chương trình đầy đủ cho cả bốn vị trí

Lưu toàn bộ mã vào **RuntimeAnnotationReadDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class RuntimeAnnotationReadDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.CONSTRUCTOR,
        ElementType.FIELD
    })
    @interface RuntimeTag {
        String value();
        int version() default 1;
    }

    @RuntimeTag("booking-service")
    static class BookingService {
        @RuntimeTag(value = "booking-reference", version = 2)
        private String reference;

        private String description;

        @RuntimeTag("create-booking")
        private BookingService(String reference) {
            this.reference = reference;
        }

        @RuntimeTag(value = "confirm-booking", version = 3)
        private void confirm(String channel) {
        }

        private void confirm() {
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = BookingService.class;
        Method method =
                type.getDeclaredMethod("confirm", String.class);
        Constructor<?> constructor =
                type.getDeclaredConstructor(String.class);
        Field field = type.getDeclaredField("reference");
        Method otherOverload = type.getDeclaredMethod("confirm");
        Field untaggedField = type.getDeclaredField("description");

        show("class", type);
        show("method", method);
        show("constructor", constructor);
        show("field", field);
        show("overload", otherOverload);
        show("untaggedField", untaggedField);
    }

    private static void show(
            String label, AnnotatedElement element) {
        RuntimeTag tag =
                element.getDeclaredAnnotation(RuntimeTag.class);

        if (tag == null) {
            System.out.println(label + "=none");
            return;
        }

        System.out.println(label + "=" + tag.value()
                + ",version=" + tag.version());
    }
}
```

Biên dịch bằng JDK hỗ trợ Java 17:

```shell
javac --release 17 -encoding UTF-8 RuntimeAnnotationReadDemo.java
java RuntimeAnnotationReadDemo
```

Kết quả chuẩn:

```text
class=booking-service,version=1
method=confirm-booking,version=3
constructor=create-booking,version=1
field=booking-reference,version=2
overload=none
untaggedField=none
```

Đọc theo từng dòng:

- Annotation trên lớp được đọc từ chính `Class`.
- Phương thức có tham số `String` có tag riêng; phương thức cùng tên không tham số không có.
- Hàm tạo là `Constructor`, không được tra bằng `getDeclaredMethod` với tên lớp.
- Trường `reference` có tag; trường `description` không có.
- `version=1` là giá trị mặc định khai báo trong annotation, không phải giá trị do hàm đọc tự điền.
- `none` là chuỗi do chương trình quy ước khi API trả `null`.

Trong ví dụ, mã chỉ truy vấn thông tin; không tạo `BookingService`, không gọi `confirm`, không đọc nội dung `reference`.

### Thành viên private có cần setAccessible(true) không?

Không cần chỉ để lấy annotation. `getDeclaredMethod`, `getDeclaredConstructor` và `getDeclaredField` tìm được thành viên khai báo trực tiếp dù nó là `private`; sau đó có thể đọc metadata annotation.

Kiểm tra quyền khi gọi `Method.invoke`, tạo đối tượng qua `Constructor.newInstance` hoặc đọc/ghi dữ liệu bằng `Field.get/set` là câu chuyện khác. Không thêm `setAccessible(true)` theo thói quen vào mã chỉ đọc annotation. [API AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html)

## 5. Chọn API đọc annotation theo yêu cầu

Các đoạn dưới là lời gọi minh họa trên một biến `element` kiểu `AnnotatedElement`:

| API | Khi dùng |
| --- | --- |
| `getDeclaredAnnotation(Tag.class)` | Lấy một annotation trực tiếp của kiểu yêu cầu; không tìm kế thừa |
| `getAnnotation(Tag.class)` | Lấy một annotation có mặt; trên lớp có thể xét `@Inherited` |
| `isAnnotationPresent(Tag.class)` | Chỉ cần biết có annotation theo quy tắc `getAnnotation` hay không |
| `getDeclaredAnnotations()` | Liệt kê annotation trực tiếp |
| `getAnnotations()` | Liệt kê annotation có mặt, có thể gồm annotation lớp được kế thừa |
| `getDeclaredAnnotationsByType(Tag.class)` | Lấy các annotation cùng kiểu, bao gồm bên trong container của annotation lặp, không xét kế thừa |
| `getAnnotationsByType(Tag.class)` | Lấy các annotation cùng kiểu và xét quy tắc kế thừa áp dụng |

`getAnnotation` hoặc `getDeclaredAnnotation` trả `null` khi không tìm thấy. Các API trả mảng trả mảng rỗng khi không có kết quả phù hợp. Với annotation có thể lặp (`@Repeatable`), nên dùng họ `...AnnotationsByType` khi cần các phần tử riêng lẻ; một lời gọi lấy annotation đơn không tự thay thế việc mở container. [Các phương thức AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

Không ép kiểu chuỗi từ `annotation.toString()` để lấy giá trị. Hãy đọc bằng phương thức đã định kiểu như `tag.value()` hoặc `tag.version()`.

## 6. Hai chữ “Declared” thuộc hai bước khác nhau

Cần phân biệt:

- `getDeclaredMethod`: **tìm phương thức** khai báo trực tiếp trong lớp.
- `getDeclaredAnnotation`: **đọc annotation** trực tiếp trên đối tượng đã tìm được.

Nếu dùng `Child.class.getMethod("execute")` và kết quả là phương thức khai báo ở `Base`, gọi `getDeclaredAnnotation` trên kết quả ấy vẫn đọc annotation trực tiếp của **phương thức Base**, không phải tìm trên Child.

Họ `getMethod/getField` tìm thành viên `public`, có xét thành viên kế thừa. Họ `getDeclaredMethod/getDeclaredField` chỉ xét thành viên khai báo trực tiếp, không giới hạn ở `public`. Tương tự, `getConstructor` tìm hàm tạo `public`, còn `getDeclaredConstructor` xét hàm tạo trực tiếp với mọi mức truy cập; hàm tạo không được kế thừa. [Tra cứu thành viên qua Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)

### Kế thừa annotation trên lớp khác kế thừa thành viên

`@Inherited` chỉ ảnh hưởng việc tra annotation trên **lớp**, theo chuỗi lớp cha. Nó không làm annotation của interface tự truyền sang lớp triển khai, cũng không tự chép annotation phương thức sang một phương thức ghi đè. [API Inherited](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Inherited.html)

Lưu chương trình sau thành **MemberLookupDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class MemberLookupDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface ClassRole {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.METHOD, ElementType.FIELD})
    @interface MemberRole {
    }

    @ClassRole
    static class Base {
        @MemberRole
        public int count;

        @MemberRole
        public void execute() {
        }
    }

    static class Child extends Base {
    }

    static class OverrideChild extends Base {
        @Override
        public void execute() {
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("classInherited="
                + Child.class.isAnnotationPresent(ClassRole.class));
        System.out.println("classDeclared="
                + (Child.class.getDeclaredAnnotation(
                        ClassRole.class) != null));

        Method inheritedMethod =
                Child.class.getMethod("execute");
        System.out.println("methodOwner="
                + inheritedMethod.getDeclaringClass().getSimpleName());
        System.out.println("methodTag="
                + inheritedMethod.isAnnotationPresent(MemberRole.class));

        boolean childDeclaresExecute;
        try {
            Child.class.getDeclaredMethod("execute");
            childDeclaresExecute = true;
        } catch (NoSuchMethodException ex) {
            childDeclaresExecute = false;
        }
        System.out.println("childDeclaresExecute="
                + childDeclaresExecute);

        System.out.println("fieldOwner="
                + Child.class.getField("count")
                    .getDeclaringClass().getSimpleName());
        System.out.println("fieldTag="
                + Child.class.getField("count")
                    .isAnnotationPresent(MemberRole.class));

        Method overridden =
                OverrideChild.class.getDeclaredMethod("execute");
        System.out.println("overriddenTag="
                + overridden.isAnnotationPresent(MemberRole.class));
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 MemberLookupDemo.java
java MemberLookupDemo
```

Kết quả:

```text
classInherited=true
classDeclared=false
methodOwner=Base
methodTag=true
childDeclaresExecute=false
fieldOwner=Base
fieldTag=true
overriddenTag=false
```

Hai dòng đầu thể hiện `ClassRole` có thể được tìm từ lớp cha, nhưng Child không trực tiếp có annotation ấy. Phương thức và trường tìm bằng họ API công khai thuộc Base; thấy tag của chúng không chứng minh có cơ chế kế thừa annotation thành viên. `OverrideChild.execute()` là khai báo khác, không có `MemberRole`.

## 7. Áp dụng trong mã đọc cấu hình hoặc xây công cụ

Một công cụ có thể quét các phương thức của lớp và chọn những phương thức có annotation phù hợp. Trước khi viết vòng lặp, cần quyết định rõ:

1. Chỉ xét thành viên trực tiếp hay bao gồm thành viên kế thừa?
2. Đọc annotation đơn hay annotation lặp?
3. Thiếu annotation là trường hợp bình thường hay vi phạm hợp đồng?
4. Có cần phân biệt các phương thức nạp chồng?
5. Kết quả có cần thứ tự ổn định để ghi log hoặc kiểm thử?

Nếu dùng `getDeclaredMethods()`, `getDeclaredFields()` hay `getDeclaredConstructors()`, không dựa vào thứ tự trả về như thứ tự viết trong mã nguồn. Hãy sắp xếp theo tiêu chí rõ ràng nếu cần kết quả ổn định; khi quét phương thức, cũng cân nhắc các phương thức synthetic/bridge do trình biên dịch tạo theo mục đích công cụ. [API Class: thành viên khai báo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)

Đọc annotation không tự quét toàn bộ classpath, không tự diễn giải annotation ghép của framework. Nếu một lớp chỉ có `@Feature`, trong khi khai báo `Feature` được gắn `@Policy`, lời gọi `SomeClass.class.getAnnotation(Policy.class)` không tự duyệt đệ quy siêu annotation. Cơ chế đó cần thuật toán riêng hoặc quy ước của framework.

Ngoài ra, annotation trên **khai báo trường** và annotation trên **kiểu sử dụng của trường** là hai đối tượng đọc khác nhau. Đối với chú thích kiểu, bắt đầu từ API như `Field.getAnnotatedType()`; bài này đọc annotation trên khai báo lớp và thành viên. [Khai báo và kiểu trong AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

## 8. Chẩn đoán kết quả thiếu hoặc sai annotation

Khi kết quả là `null` hoặc mảng rỗng, kiểm tra theo thứ tự:

- Annotation có `RUNTIME` không, và các lớp đã được biên dịch lại sau khi đổi retention chưa?
- Đang tra đúng lớp và đúng chữ ký phương thức/hàm tạo chưa?
- Annotation nằm trên lớp, thành viên hay kiểu sử dụng?
- Thành viên nằm trực tiếp trong lớp hay được kế thừa?
- Có cần họ API `ByType` cho annotation lặp không?
- Có đang kỳ vọng một quy tắc quét của framework mà reflection Java thuần không cung cấp không?

Phân biệt trường hợp “không có annotation” với lỗi “không có thành viên”. Ví dụ, `getDeclaredMethod("confirm", int.class)` trong chương trình đầu ném `NoSuchMethodException`; `getDeclaredMethod("confirm")` thành công nhưng đọc `RuntimeTag` trả `null`.

### Tự thực hành

1. Đổi `RuntimeTag` sang `RetentionPolicy.CLASS`, biên dịch lại chương trình đầu. Sáu dòng đầu ra chuyển thành gì?
2. Gắn tag cho `confirm()` với giá trị riêng, rồi xác nhận hai phương thức cùng tên được đọc độc lập.
3. Bỏ `@Inherited` khỏi `ClassRole`. Dòng nào trong chương trình thứ hai thay đổi?
4. Gắn `@MemberRole` trực tiếp lên `OverrideChild.execute()`. Vì sao `overriddenTag` chuyển thành `true` mà không cần thay annotation của Base?
5. Thử tìm `reference` bằng `getField` thay `getDeclaredField`. Vì sao việc trường tồn tại nhưng là `private` làm cách tra cứu này không phù hợp?
