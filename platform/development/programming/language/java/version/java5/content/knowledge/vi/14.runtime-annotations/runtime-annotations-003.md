# Đọc annotation trên tham số phương thức

## Khái niệm và mục đích

Annotation trên tham số phương thức là siêu dữ liệu gắn vào **khai báo một tham số hình thức**. Nó có thể mô tả tên dữ liệu bên ngoài, quy tắc xử lý hoặc thông tin cần cho công cụ ánh xạ dữ liệu.

Ví dụ, trong khai báo `create(@Argument("email") String email)`, annotation `@Argument` gắn vào tham số `email`. Nó không gắn vào toàn bộ phương thức `create` và cũng không gắn vào đối tượng `String` được truyền vào khi gọi.

Một công cụ có thể đọc annotation đó để biết đối số ở vị trí nào được ánh xạ từ trường `"email"`. Tuy nhiên, Java không tự thực hiện ánh xạ hoặc kiểm tra dữ liệu chỉ vì annotation xuất hiện. Phải có thành phần đọc và diễn giải siêu dữ liệu.

Bài này dùng reflection để đọc annotation **khi chương trình chạy**, với API Java hiện đại và ví dụ chạy trên JDK 17 trở lên.

## Phân biệt ba thứ thường bị nhầm

| Đối tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tham số hình thức | Khai báo trong phương thức | `String email` |
| Đối số | Giá trị được truyền trong một lần gọi | `"user@example.com"` |
| Annotation của tham số | Siêu dữ liệu của khai báo tham số | `@Argument("email")` |

Reflection đọc thông tin khai báo. Nó không tự cung cấp giá trị các đối số của những lần gọi đang diễn ra.

Nếu muốn kiểm tra dữ liệu của một lần gọi dựa trên annotation, chương trình cần cả hai nguồn: siêu dữ liệu theo vị trí tham số và các giá trị đối số tương ứng. Việc thu thập, kiểm tra hay chặn một lần gọi là phần triển khai riêng, nằm ngoài thao tác đọc annotation.

## Điều kiện để đọc được annotation lúc chạy

Một kiểu annotation dành cho khai báo tham số có thể viết như sau:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Argument {
    String value();
    boolean required() default true;
}
```

Đây là phần khai báo minh họa; chương trình đầy đủ phía dưới có toàn bộ import.

- `ElementType.PARAMETER` cho phép gắn annotation vào khai báo tham số.
- `RetentionPolicy.RUNTIME` giữ annotation để reflection đọc được khi chạy.
- `value()` và `required()` là các thuộc tính siêu dữ liệu do ví dụ tự định nghĩa.

Nếu bỏ `@Retention`, chính sách mặc định là `CLASS`; khi đó không thể kỳ vọng `Parameter.getAnnotation` trả annotation lúc chạy. `SOURCE` cũng không đáp ứng mục tiêu này.

Thuộc tính `required = true` không tự tạo kiểm tra `null` hoặc kiểm tra chuỗi rỗng. Tên và ý nghĩa thuộc tính phải được thành phần sử dụng annotation quy định rõ.

## Đường đọc thứ nhất: Method → Parameter → annotation

Một cách đọc dễ theo dõi gồm ba bước:

1. Tìm chính xác phương thức để lấy đối tượng `Method`.
2. Gọi `method.getParameters()` để lấy các `Parameter` theo thứ tự khai báo.
3. Trên từng `Parameter`, gọi `getAnnotation(KieuAnnotation.class)`.

Dạng minh họa:

```java
Method method = Service.class.getDeclaredMethod(
        "create", String.class, int.class, String.class);

Parameter[] parameters = method.getParameters();
Argument annotation = parameters[0].getAnnotation(Argument.class);
```

Đoạn này cần đặt trong một chương trình có `Service`, `Argument`, import và xử lý `NoSuchMethodException`; tất cả đều có trong ví dụ hoàn chỉnh.

`getAnnotation` trả `null` nếu không có annotation tương ứng. Phải kiểm tra trước khi gọi các thuộc tính như `annotation.value()`.

Các thao tác hữu ích trên `Parameter`:

| API | Công dụng |
| --- | --- |
| `getAnnotation(Argument.class)` | Lấy một annotation thuộc kiểu đang hỏi, hoặc `null` |
| `isAnnotationPresent(Argument.class)` | Kiểm tra có annotation theo kiểu đó hay không |
| `getAnnotations()` | Đọc các annotation trên khai báo tham số |
| `getAnnotationsByType(Tag.class)` | Đọc theo kiểu, kể cả cơ chế annotation lặp khi được khai báo phù hợp |
| `getType()` | Đọc kiểu của tham số dưới dạng `Class<?>` |
| `getName()` và `isNamePresent()` | Kiểm tra tên tham số và việc tên thật có được giữ lại hay không |

Các API được mô tả tại [Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html).

## Đường đọc thứ hai: ma trận Annotation[][]

`Method.getParameterAnnotations()` trả về một mảng hai chiều:

```java
Annotation[][] matrix = method.getParameterAnnotations();
```

Cách hiểu:

- `matrix.length` là số vị trí tham số được trả về cho phương thức.
- `matrix[i]` chứa các annotation của tham số ở vị trí `i`.
- Thứ tự các vị trí tham số đi theo thứ tự khai báo.
- Tham số không có annotation vẫn có một mảng con, với độ dài 0.

Ví dụ một phương thức có ba tham số, trong đó hai tham số đầu được gắn một annotation mỗi tham số:

```text
matrix[0] -> 1 annotation
matrix[1] -> 1 annotation
matrix[2] -> 0 annotation
```

Không bỏ qua tham số chưa được gắn annotation rồi đánh lại chỉ số của những tham số còn lại. Làm vậy sẽ phá vỡ ánh xạ vị trí giữa siêu dữ liệu và lời gọi phương thức.

Cũng không coi `matrix[i][0]` luôn là một kiểu annotation cụ thể. Một tham số có thể có nhiều loại annotation; khi cần một loại xác định, đọc theo kiểu bằng `Parameter.getAnnotation` thường rõ hơn.

API dùng chung của phương thức và constructor nằm trong [Executable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html#getParameterAnnotations()). Bài này tập trung vào tham số phương thức; không suy rộng các ví dụ chỉ số sang mọi trường hợp constructor có tham số ngầm định hoặc do trình biên dịch sinh.

## Ví dụ chạy đầy đủ

Lưu thành `ParameterAnnotationDemo.java`:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterAnnotationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Argument {
        String value();
        boolean required() default true;
    }

    static class Service {
        public void create(
                @Argument("email") String email,
                @Argument(value = "limit", required = false) int limit,
                String source) {
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = Service.class.getDeclaredMethod(
                "create", String.class, int.class, String.class);

        Parameter[] parameters = method.getParameters();
        System.out.println("count=" + parameters.length);
        System.out.println("firstNamePresent=" + parameters[0].isNamePresent());
        System.out.println("firstName=" + parameters[0].getName());

        for (int i = 0; i < parameters.length; i++) {
            Parameter parameter = parameters[i];
            Argument argument = parameter.getAnnotation(Argument.class);
            String details = argument == null
                    ? "label=none"
                    : "label=" + argument.value()
                            + ",required=" + argument.required();
            System.out.println(i + ":type="
                    + parameter.getType().getSimpleName() + "," + details);
        }

        Annotation[][] matrix = method.getParameterAnnotations();
        for (int i = 0; i < matrix.length; i++) {
            System.out.println("matrix[" + i + "]=" + matrix[i].length);
        }

        System.out.println("method.annotation="
                + method.isAnnotationPresent(Argument.class));
    }
}
```

Phương thức `create` có phần thân rỗng vì bài chỉ quan sát siêu dữ liệu khai báo. Chương trình không gọi phương thức này và không cần tạo đối tượng `Service`.

### Biên dịch không giữ tên tham số

Với `javac` mặc định, không thêm `-parameters`:

```shell
javac -encoding UTF-8 -d out-basic ParameterAnnotationDemo.java
java -cp out-basic ParameterAnnotationDemo
```

Kết quả:

```text
count=3
firstNamePresent=false
firstName=arg0
0:type=String,label=email,required=true
1:type=int,label=limit,required=false
2:type=String,label=none
matrix[0]=1
matrix[1]=1
matrix[2]=0
method.annotation=false
```

Điểm cần quan sát:

1. Ba vị trí tham số đều có trong `getParameters()`, kể cả tham số `source` không được gắn annotation.
2. Annotation thứ nhất dùng giá trị mặc định `required = true`.
3. Annotation thứ hai tự khai báo `required = false`.
4. Việc không giữ tên thật của tham số không làm annotation lúc chạy biến mất.
5. `method.annotation=false` chứng minh annotation của tham số không tự trở thành annotation của phương thức.

`required = false` trên tham số `int limit` trong ví dụ chỉ là một giá trị siêu dữ liệu được in ra. Nó không làm tham số biến thành tùy chọn trong cú pháp gọi Java, không cho phép truyền `null` cho `int` và không tự cấp giá trị mặc định cho một đối số bị thiếu.

### Biên dịch có giữ tên tham số

Biên dịch cùng tệp với `-parameters` và chạy từ thư mục đầu ra khác:

```shell
javac -encoding UTF-8 -parameters -d out-names ParameterAnnotationDemo.java
java -cp out-names ParameterAnnotationDemo
```

Trong kết quả, hai dòng về tên đổi thành:

```text
firstNamePresent=true
firstName=email
```

Các dòng đọc annotation vẫn giữ nguyên. Hai thư mục đầu ra giúp tránh vô tình chạy nhầm bản class của lần biên dịch trước.

Tùy chọn `-parameters` lưu tên các tham số hình thức để API reflection truy xuất; xem [tài liệu javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).

## Tên tham số và giá trị annotation là hai nguồn độc lập

Trong ví dụ, giá trị `"email"` đến từ `@Argument("email")`, không đến từ `Parameter.getName()`.

Có thể đổi tên biến tham số thành `contactAddress` mà vẫn giữ `@Argument("email")`. Khi đó:

- Giá trị annotation vẫn là `"email"`.
- Tên thật của tham số, nếu được giữ bằng `-parameters`, là `"contactAddress"`.
- Nếu không giữ tên, `getName()` cung cấp tên được tạo như `arg0`, không phải tên trường dữ liệu bên ngoài.

Vì vậy, khi thiết kế một công cụ ánh xạ dữ liệu, cần quyết định rõ lấy tên từ annotation, từ tên tham số, hay theo một thứ tự ưu tiên. Không dùng `arg0` làm tên nghiệp vụ chỉ vì API trả về một chuỗi.

Đồng thời, việc API đọc annotation là đúng không đảm bảo mọi công cụ đóng gói, làm rối mã hoặc tối ưu đầu ra đều giữ lại đầy đủ siêu dữ liệu. Hãy kiểm tra cấu hình và đầu ra thực tế nếu môi trường build có những bước xử lý đó.

## Tìm đúng Method trước khi đọc annotation

### Phải chỉ rõ đúng kiểu tham số

`getDeclaredMethod` tìm theo tên phương thức và danh sách kiểu tham số. Với ví dụ trên, cần dùng:

```java
Service.class.getDeclaredMethod(
        "create", String.class, int.class, String.class);
```

Không thay `int.class` bằng `Integer.class`. Các phép boxing có thể dùng trong một lời gọi Java không làm cho hai chữ ký phản chiếu này giống nhau.

Nếu phương thức được nạp chồng, chỉ tìm theo tên rồi tùy ý chọn phần tử đầu tiên trong `getDeclaredMethods()` có thể đọc nhầm annotation của phiên bản khác. Nên xác định chữ ký đang cần trước.

Với phương thức generic, danh sách `Class<?>` dùng để tìm phương thức phải tương ứng với kiểu sau xóa kiểu. Chẳng hạn tham số `List<String>` được tìm bằng `List.class`, không có một đối tượng class riêng tên `List<String>.class`.

### Phân biệt getDeclaredMethod và getMethod

- `getDeclaredMethod` tìm phương thức khai báo trong chính lớp, bao gồm các mức truy cập khác nhau.
- `getMethod` tìm phương thức public và có thể tìm cả phương thức được thừa kế.

Nếu dùng `getMethod` trên lớp con, đối tượng `Method` có thể đại diện cho một khai báo của lớp cha. Có thể xem `method.getDeclaringClass()` để xác định nơi khai báo thật.

Đọc annotation là đọc siêu dữ liệu. Trong ví dụ này, không cần `setAccessible(true)` và không cần `Method.invoke`. Quyền thực hiện một lời gọi phản chiếu là vấn đề khác, chỉ cần xem xét nếu thực sự gọi phương thức.

Xem các API phản chiếu trong [Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html).

## Annotation không tự đi theo phương thức ghi đè

Annotation trên tham số của một phương thức trong interface hoặc lớp cha không tự được sao chép sang tham số của phương thức ghi đè ở lớp con.

Ví dụ, nếu interface có tham số `@Argument("email") String email`, còn phần triển khai chỉ viết `String email`, đọc `Parameter` của chính phương thức triển khai không tự trả annotation từ interface.

`@Inherited` không thay đổi quy tắc này. Một framework có thể chủ động tìm annotation ở các phương thức tương ứng trong interface hoặc lớp cha, nhưng đó là cơ chế riêng cần được tài liệu của framework xác nhận.

Nếu cần một quy tắc tìm qua nhiều khai báo, phải xác định rõ nguồn ưu tiên và cách xử lý xung đột. Không mặc nhiên cộng dồn mọi annotation tìm thấy.

## Phân biệt annotation của tham số với annotation của kiểu sử dụng

Hai đích `PARAMETER` và `TYPE_USE` trả lời hai câu hỏi khác nhau:

| Vị trí annotation | API đọc phù hợp |
| --- | --- |
| Trên khai báo tham số | `Parameter.getAnnotation`, `getAnnotations`, hoặc `Method.getParameterAnnotations` |
| Trên kiểu được dùng làm kiểu tham số | `Parameter.getAnnotatedType()` hoặc `Method.getAnnotatedParameterTypes()` |
| Trên đối số kiểu bên trong, như `List<@Marker String>` | Duyệt cấu trúc `AnnotatedType` tương ứng, chẳng hạn `AnnotatedParameterizedType` |
| Trên chính phương thức | `Method.getAnnotation` |

Đừng kết luận annotation “bị mất” chỉ vì đọc sai phần tử. Trước tiên cần xem `@Target` của kiểu annotation và vị trí nó xuất hiện trong khai báo.

Một annotation cho phép cả `PARAMETER` và `TYPE_USE` có thể khiến mã nguồn trông gần giống nhau; vẫn phải dùng API phù hợp với loại siêu dữ liệu cần đọc.

## Trường hợp không có tham số và tham số varargs

Nếu phương thức không có tham số, `getParameters()` và `getParameterAnnotations()` trả mảng rỗng. Không truy cập phần tử `[0]` khi chưa biết số tham số. Ví dụ chính truy cập được `parameters[0]` vì chữ ký đã cố định ba tham số.

Tham số varargs được phản chiếu dưới dạng một tham số mảng. Ví dụ khai báo `send(@Argument("items") String... items)` có một vị trí tham số cho `items`, không phải một vị trí annotation cho từng phần tử được truyền vào.

Để tìm phương thức đó, dùng kiểu `String[].class`. Có thể dùng `Parameter.isVarArgs()` hoặc `Method.isVarArgs()` khi công cụ cần biết khai báo ban đầu là varargs.

## Annotation lặp và cách đọc theo kiểu

Một tham số có thể được gắn nhiều annotation cùng loại nếu kiểu annotation được khai báo bằng `@Repeatable` phù hợp.

Khi cần danh sách các lần xuất hiện của một kiểu annotation lặp, ưu tiên `parameter.getAnnotationsByType(Tag.class)`. Không giả định `getAnnotation(Tag.class)` hoặc một phần tử trong `Annotation[][]` luôn tự bóc tách mọi annotation được chứa.

Đây là lý do nên đọc theo **kiểu cần tìm**, thay vì phụ thuộc vào số lượng hay thứ tự các annotation trả về. Chương trình chính dùng annotation không lặp để làm rõ trước ánh xạ theo vị trí tham số.

## Lỗi phổ biến và cách kiểm tra

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| `NoSuchMethodException` | Tên phương thức, thứ tự/kiểu tham số, `int` so với `Integer`, và phạm vi tìm phương thức |
| `getAnnotation` trả `null` | Retention, phần tử đang đọc và đúng kiểu annotation |
| Không có tên như mã nguồn | `isNamePresent()` và tùy chọn `-parameters` của bước biên dịch |
| Tham số không có annotation gây lỗi | Kiểm tra `null`, không gọi thuộc tính ngay trên kết quả |
| Chỉ số annotation lệch với đối số | Giữ đủ mọi vị trí, kể cả tham số không có annotation |
| Không thấy annotation ở lớp triển khai | Xác định đang đọc phương thức interface, lớp cha hay khai báo ghi đè |
| Thấy annotation nhưng dữ liệu vẫn không được kiểm tra | Tìm thành phần thực sự áp dụng ngữ nghĩa annotation |
| Đọc nhầm annotation ở kiểu sử dụng | Đối chiếu `PARAMETER` với `TYPE_USE` và API đọc |

## Thực hành kiểm chứng

1. Chạy ví dụ với và không với `-parameters`; xác nhận chỉ thông tin tên thay đổi.
2. Đổi tên tham số `email` thành `contactAddress`, giữ nguyên annotation. Biên dịch với `-parameters` để tách biệt tên tham số và giá trị `"email"`.
3. Bỏ annotation ở tham số `limit`, biên dịch lại. Dòng mô tả vị trí 1 phải có `label=none`, còn `matrix[1]=0`; các tham số vẫn giữ nguyên vị trí.
4. Đổi retention của `Argument` thành `CLASS`, biên dịch lại. Các mảng vẫn có đủ ba vị trí nhưng không đọc được `Argument` lúc chạy.
5. Trong lệnh tìm phương thức, thay `int.class` bằng `Integer.class`; quan sát lỗi tìm chữ ký và giải thích vì sao dữ liệu annotation chưa hề được đọc.

Khi xây công cụ dựa trên annotation tham số, luôn xác định trước **phương thức nào, vị trí tham số nào, loại annotation nào và quy tắc áp dụng nào**.
