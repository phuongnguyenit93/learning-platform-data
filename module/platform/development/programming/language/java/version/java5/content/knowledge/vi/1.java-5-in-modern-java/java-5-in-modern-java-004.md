# Mối liên hệ giữa enum, annotation và thông tin kiểu lúc chạy

## 1. Ba vai trò khác nhau trong cùng một thiết kế

Giả sử một lớp xử lý cần được đánh dấu là dành cho nhóm hỗ trợ hoặc nhóm quản trị. `enum` diễn tả tập lựa chọn hợp lệ; annotation gắn lựa chọn đó vào khai báo; thông tin kiểu lúc chạy cho phép một thành phần đọc metadata và thực hiện quyết định.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Enum | Một kiểu có tập hằng được đặt tên | `Audience.ADMIN` |
| Annotation | Metadata gắn vào khai báo hoặc vị trí dùng kiểu theo hợp đồng | `@AudienceTag(Audience.ADMIN)` |
| Thông tin kiểu lúc chạy | Biết kiểu nào đang được xử lý và đọc metadata được giữ lại | `SomeTask.class.getAnnotation(...)` |

Annotation không thay enum, và reflection không tự tạo quy tắc nghiệp vụ. Mối liên hệ hữu ích là **lựa chọn có kiểu → metadata có cấu trúc → mã đọc metadata**.

## 2. Enum tạo miền giá trị có tên

Với `enum Audience { SUPPORT, ADMIN }`, mã chỉ dùng các hằng của đúng kiểu `Audience` khi truyền cho phần tử annotation tương ứng. Không cần dựa vào chuỗi như `"admim"` rồi đợi đến lúc chạy mới phát hiện gõ sai.

Enum là một kiểu lớp đặc biệt; các hằng của nó là các đối tượng được đặt tên. Có thể dùng enum trong biến, tham số, `switch`, `EnumSet` hoặc `EnumMap`. Khi ý nghĩa chỉ là một lựa chọn trong một tập đã biết, enum giúp giữ hợp đồng rõ ràng.

Đừng dùng `ordinal()` làm mã dữ liệu ổn định: đó là vị trí khai báo, có thể đổi khi sửa thứ tự. Nếu cần mã trao đổi ổn định, thiết kế mã riêng và phép ánh xạ có kiểm tra.

Enum cũng không tự biến thành một hệ thống plugin có tập lựa chọn mở ở lúc chạy. Nếu cần thêm loại hành vi mà không sửa tập enum đã biên dịch, cần mô hình mở rộng khác.

## 3. Annotation có thể dùng enum và Class làm phần tử

Khai báo annotation dùng cú pháp `@interface`. Các phần tử có những kiểu được ngôn ngữ cho phép: kiểu nguyên thủy, `String`, `Class`, enum, một annotation khác hoặc mảng một chiều của các kiểu đó.

Đoạn minh họa khai báo:

```java
enum Audience { SUPPORT, ADMIN }

@interface AudienceTag {
    Audience value();
    Class<?> payloadType() default Void.class;
    String description() default "";
}
```

`Audience` tạo miền giá trị của `value`; `Class<?>` cho phép metadata chỉ đến một kiểu như `String.class`. Không dùng một đối tượng tùy ý, `List<String>` hoặc kết quả gọi hàm làm giá trị phần tử annotation. Giá trị phần tử cũng không thể là `null`.

Với phần tử kiểu enum, tại nơi dùng annotation phải chỉ định hằng enum hợp lệ. Với phần tử kiểu `Class`, dùng class literal. Đây là quy tắc của ngôn ngữ, không phải cách serialize một đối tượng bất kỳ vào annotation. [JLS: phần tử annotation](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.1)

## 4. Retention quyết định metadata có đọc được lúc chạy không

`@Retention` là metadata của chính annotation, xác định nó được giữ đến giai đoạn nào:

| Chính sách | Hệ quả chính |
| --- | --- |
| `SOURCE` | Chỉ ở mã nguồn; công cụ biên dịch có thể dùng |
| `CLASS` | Ghi vào tệp class, không phải dạng được reflection chuẩn đọc lúc chạy |
| `RUNTIME` | Giữ để reflection đọc được khi chạy |

Nếu không khai báo `@Retention`, mặc định là `CLASS`. Vì vậy, viết annotation lên lớp chưa bảo đảm `getAnnotation` sẽ tìm thấy nó.

`@Target` xác định vị trí được phép đặt, ví dụ `TYPE`, `METHOD`, `FIELD` hoặc `TYPE_USE`. Nó không chọn nơi framework sẽ quét và không tự kích hoạt xử lý. Một annotation dành cho lớp có thể không được phép gắn vào phương thức.

Chỉ chọn `RUNTIME` khi có thành phần thực sự cần đọc ở lúc chạy. Annotation dùng cho kiểm tra hoặc sinh mã khi biên dịch không tự trở nên lỗi thời chỉ vì không tồn tại qua reflection. [Retention](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html)

## 5. Class là cầu nối đến thông tin kiểu

`SomeTask.class` là một đối tượng `Class<SomeTask>`, đại diện kiểu trong chương trình đang chạy. `value.getClass()` cho kiểu thực tế của một đối tượng; kiểu đó có thể khác kiểu biến được khai báo ở mã nguồn.

Qua `Class`, có thể hỏi tên, loại kiểu, annotation được giữ lại hoặc các thành viên qua reflection. Đối với enum có `isEnum()` và `getEnumConstants()`; đối với annotation interface có `isAnnotation()`.

Phân biệt ba đối tượng:

- `AudienceTag.class`: đối tượng `Class` đại diện kiểu annotation.
- Một giá trị trả từ `getAnnotation(AudienceTag.class)`: biểu diễn annotation gắn trên một phần tử.
- `Audience.ADMIN`: một hằng enum có thể được trả từ phần tử của annotation.

Không cần đọc tên lớp triển khai nội bộ của annotation để suy ra kiểu annotation; dùng `annotation.annotationType()`. Cách JVM hoặc thư viện tạo biểu diễn đó không phải hợp đồng nghiệp vụ. [Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)

## 6. Chương trình đầy đủ: đọc metadata có enum và kiểu dữ liệu

Ví dụ chọn tag trực tiếp trên lớp, không quét classpath và không tự nạp tên lớp từ chuỗi. Chương trình chỉ minh họa cách đọc mô tả và kiểm tra một đối tượng có thuộc kiểu payload được công bố hay không.

Lưu thành `EnumAnnotationTypeDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public class EnumAnnotationTypeDemo {
    enum Audience { SUPPORT, ADMIN }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface AudienceTag {
        Audience value();
        Class<?> payloadType() default Void.class;
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface BuildTag {}

    @AudienceTag(value = Audience.SUPPORT, payloadType = String.class)
    @BuildTag
    static class ReportTask {}

    @AudienceTag(Audience.ADMIN)
    static class MaintenanceTask {}

    static class UntaggedTask {}

    static boolean acceptsPayload(Class<?> taskType, Object payload) {
        AudienceTag tag = taskType.getDeclaredAnnotation(AudienceTag.class);
        return tag != null && tag.payloadType().isInstance(payload);
    }

    static void describe(Class<?> taskType) {
        AudienceTag tag = taskType.getDeclaredAnnotation(AudienceTag.class);
        if (tag == null) {
            System.out.println(taskType.getSimpleName() + ": no tag");
            return;
        }
        String route = switch (tag.value()) {
            case SUPPORT -> "support";
            case ADMIN -> "admin";
        };
        System.out.println(taskType.getSimpleName() + ": " + route
                + ", payload=" + tag.payloadType().getSimpleName());
    }

    public static void main(String[] args) {
        describe(ReportTask.class);
        describe(MaintenanceTask.class);
        describe(UntaggedTask.class);

        System.out.println("audienceIsEnum=" + Audience.class.isEnum());
        System.out.println("tagIsAnnotation=" + AudienceTag.class.isAnnotation());
        System.out.println("acceptsText="
                + acceptsPayload(ReportTask.class, "daily report"));
        System.out.println("acceptsNumber=" + acceptsPayload(ReportTask.class, 42));
        System.out.println("buildTagVisible="
                + (ReportTask.class.getDeclaredAnnotation(BuildTag.class) != null));

        AudienceTag tag = ReportTask.class.getDeclaredAnnotation(AudienceTag.class);
        System.out.println("annotationType=" + tag.annotationType().getSimpleName());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 EnumAnnotationTypeDemo.java
java EnumAnnotationTypeDemo
```

Stdout chính xác:

```text
ReportTask: support, payload=String
MaintenanceTask: admin, payload=Void
UntaggedTask: no tag
audienceIsEnum=true
tagIsAnnotation=true
acceptsText=true
acceptsNumber=false
buildTagVisible=false
annotationType=AudienceTag
```

`SUPPORT`/`ADMIN` quyết định nhánh của `switch` vì có mã đọc và dùng giá trị đó. Chỉ thêm annotation lên một lớp không làm chương trình tự định tuyến hoặc cấp quyền.

`Void.class` trong ví dụ là một dấu mốc mô tả mặc định, không phải một đối tượng payload thật. Cách xử lý tác vụ không cần payload phải được thiết kế riêng; hàm `acceptsPayload` chỉ kiểm tra đúng khả năng `isInstance` được nêu.

`buildTagVisible=false` không có nghĩa tag không tồn tại trong tệp class. Nó có retention `CLASS`, nên không được API reflection này trả về ở lúc chạy.

## 7. Đọc annotation theo phần tử và kế thừa

`Class`, `Method` và `Field` đều có thể cung cấp annotation qua hợp đồng `AnnotatedElement`, nhưng metadata gắn vào phần tử nào phải đọc ở phần tử đó. Một tag trên phương thức không tự trở thành tag của lớp.

`getDeclaredAnnotation` tìm annotation được khai báo trực tiếp trên phần tử. `getAnnotation` còn xét các quy tắc hiện diện được API định nghĩa; với annotation trên lớp, `@Inherited` có thể cho phép tìm từ lớp cha.

`@Inherited` không khiến annotation tự truyền qua interface hoặc tự kế thừa trên các phương thức ghi đè. Nếu framework có quy tắc tìm metadata rộng hơn, đó là quy tắc riêng của framework, phải đọc đúng tài liệu thay vì gán cho reflection chuẩn.

Với annotation lặp, `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType` có thể đọc qua container theo hợp đồng. Không mặc định một lần `getAnnotation` sẽ đại diện mọi tag cùng loại. [AnnotatedElement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

## 8. Những giới hạn quan trọng của thông tin kiểu lúc chạy

### Metadata không tự kiểm tra nghiệp vụ

`@AudienceTag(Audience.ADMIN)` chỉ nói lớp mang metadata đó. Nếu dùng vào phân quyền thực tế, hệ thống còn cần kiểm tra danh tính và quyền của người gọi ở đúng ranh giới; không coi một tag trên lớp là chứng cứ người dùng được phép truy cập.

### Class token không giữ mọi đối số generic

`String.class` giữ thông tin kiểu `String`, nhưng không có class literal `List<String>.class`. Hai đối tượng `ArrayList<String>` và `ArrayList<Integer>` thường có cùng đối tượng `Class` cho `ArrayList`.

Reflection có thể đọc một số chữ ký generic được khai báo, nhưng `payloadType = List.class` không tự kiểm tra từng phần tử có phải `String`. Nếu cần ràng buộc dữ liệu phức tạp, phải có hợp đồng/kiểm tra thêm thay vì suy quá nhiều từ `Class<?>`.

### Đọc metadata khác với thực thi phản chiếu

Đọc annotation công khai không có nghĩa có thể gọi mọi thành viên riêng tư. Những hạn chế truy cập và module của Java hiện đại vẫn áp dụng khi thực hiện reflection sâu. Không cần mở truy cập riêng tư chỉ để giải thích mối liên hệ enum/annotation ở ví dụ này.

## 9. Dùng kết hợp khi nào?

Dùng enum làm phần tử annotation khi tập lựa chọn nhỏ, có tên và thay đổi cùng mã nguồn. Dùng annotation khi metadata gắn tự nhiên vào khai báo và có thành phần tiêu thụ rõ ràng, chẳng hạn công cụ biên dịch hoặc bộ đọc metadata lúc chạy.

Nếu cấu hình cần đổi theo người dùng, môi trường hoặc từng yêu cầu mà không biên dịch lại, một đối tượng cấu hình thường phù hợp hơn annotation. Nếu chỉ cần gọi hành vi đa hình, một interface trực tiếp có thể rõ hơn việc đọc tag rồi suy ra mọi hành vi.

Khi thiết kế bộ đọc, chọn rõ tag bắt buộc hay tùy chọn, quy tắc tìm metadata và cách xử lý kiểu không có tag. Không giả định `getAnnotation` luôn khác `null`.

## 10. Tự thực hành

1. Đổi retention của `AudienceTag` thành `CLASS` trong một thí nghiệm riêng và quan sát bộ đọc.
2. Thêm một giá trị enum và cập nhật `switch` để thấy trình biên dịch hỗ trợ kiểm tra tập lựa chọn.
3. Chuyển tag sang phương thức với `@Target(METHOD)` rồi đọc đúng đối tượng `Method`.
4. Giải thích vì sao `payloadType = List.class` không đủ xác nhận một danh sách chỉ chứa chuỗi.

Đối chiếu: enum cung cấp lựa chọn có kiểu, annotation gắn metadata, retention quyết định khả năng đọc lúc chạy, và mã tiêu thụ thông tin kiểu mới tạo ra hành vi cụ thể.