# Annotation trên record được truyền theo `@Target` như thế nào?

Khi một annotation được viết trước thành phần record, không nên hiểu rằng nó chỉ nằm trên một đối tượng `RecordComponent`, cũng không nên hiểu rằng nó được chép tới mọi thành viên liên quan. **Đích áp dụng của annotation và cách thành viên được khai báo quyết định nơi metadata xuất hiện.**

Điều này quan trọng với công cụ dùng Reflection: một công cụ đọc annotation trên trường dữ liệu có thể thấy khác công cụ đọc trên accessor hoặc tham số constructor. Hai kết quả khác nhau chưa chắc là lỗi; trước hết phải xác định đúng phần tử đang được truy vấn.

Bài này dùng Java 17 trở lên và phân biệt annotation của khai báo với annotation trên cách sử dụng kiểu dữ liệu.

## 1. Một thành phần record liên hệ với nhiều khai báo

Xét header:

```java
record Message(String text) {
}
```

`text` là một thành phần record. Nó liên hệ với:

- Metadata của chính thành phần: `RecordComponent`.
- Trường dữ liệu `text` được cung cấp cho record.
- Accessor `text()`.
- Tham số `text` của constructor chuẩn.

Đây là các vị trí metadata riêng biệt. Annotation được viết trong header có thể được trình biên dịch truyền tới những vị trí thích hợp. Cơ chế này thường được gọi là **truyền annotation (annotation propagation)**.

Đó không phải việc `getAnnotation()` đang tự đi tìm ở các vị trí khác trong lúc chạy. Khi bạn hỏi một `Field`, Reflection đọc annotation của trường đó; nó không tự hỏi thêm `RecordComponent` để ghép kết quả.

## 2. `@Target` và `@Retention` trả lời hai câu hỏi khác nhau

[`@Target`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Target.html) mô tả những ngữ cảnh được phép áp dụng annotation. Trình biên dịch kiểm tra các giới hạn đó.

[`@Retention`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html) mô tả thời gian lưu giữ. Muốn đọc các annotation trong thí nghiệm bằng Reflection khi chạy, chúng được khai báo với `RetentionPolicy.RUNTIME`. Nếu bỏ `@Retention`, mặc định là `CLASS`, không phải `RUNTIME`.

Vì vậy, khi không tìm thấy annotation, cần kiểm tra cả **vị trí metadata** lẫn **chính sách lưu giữ**, thay vì chỉ nhìn xem mã nguồn có dấu `@` hay không.

Với các thành viên được cung cấp ngầm định cho record, các đích thường gặp có ý nghĩa như sau:

| Đích trong `@Target` | Vị trí liên quan cần xét |
| --- | --- |
| `RECORD_COMPONENT` | Metadata của chính thành phần record |
| `FIELD` | Khai báo trường thành phần |
| `METHOD` | Khai báo accessor được cung cấp ngầm định |
| `PARAMETER` | Tham số được suy ra cho constructor chuẩn ngầm định hoặc rút gọn |
| `TYPE_USE` | Vị trí sử dụng kiểu, như kiểu thành phần, kiểu trường, kiểu trả về và kiểu tham số được suy ra |

Những tên đích này thuộc [`ElementType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html). `CONSTRUCTOR` nói về **khai báo constructor**, còn `PARAMETER` nói về **tham số của constructor**; không được xem chúng là một đích.

Một annotation chỉ có đích `CONSTRUCTOR` không được viết lên thành phần rồi trông đợi nó tự chuyển tới constructor. Trong ví dụ bên dưới, `Mark` có cả đích `CONSTRUCTOR`, nhưng việc dùng `@Mark` trong header vẫn không tự đánh dấu toàn bộ constructor.

## 3. Thí nghiệm Java 17+ đầy đủ

Chương trình dùng ba annotation:

- `Mark`: áp dụng cho nhiều loại khai báo để quan sát từng nơi nhận metadata.
- `FieldOnly`: chỉ áp dụng cho trường dữ liệu.
- `TypeMark`: chỉ áp dụng cho cách sử dụng kiểu dữ liệu.

Các record khác nhau ở việc để trình biên dịch cung cấp accessor hoặc constructor, tự khai báo chúng, hay tự ghi lại annotation tại những vị trí tường minh.

Lưu toàn bộ vào **`RecordAnnotationTargetsDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordAnnotationTargetsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.FIELD,
            ElementType.METHOD,
            ElementType.PARAMETER,
            ElementType.CONSTRUCTOR
    })
    public @interface Mark {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface FieldOnly {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeMark {
    }

    public record Generated(@Mark @FieldOnly @TypeMark String text) {
    }

    public record Compact(@Mark @TypeMark String text) {
        public Compact {
            text = Objects.requireNonNull(text, "text");
        }
    }

    public record OwnAccessor(@Mark @TypeMark String text) {
        public String text() {
            return text;
        }
    }

    public record OwnConstructor(@Mark @TypeMark String text) {
        public OwnConstructor(String text) {
            this.text = text;
        }
    }

    public record Restated(@Mark @TypeMark String text) {
        @Mark
        public Restated(@Mark @TypeMark String text) {
            this.text = text;
        }

        @Mark
        public @TypeMark String text() {
            return text;
        }
    }

    public record NestedType(List<@TypeMark String> values) {
    }

    private static String names(Annotation[] annotations) {
        return Arrays.stream(annotations)
                .map(annotation -> annotation.annotationType().getSimpleName())
                .sorted()
                .toList()
                .toString();
    }

    private static void show(Class<?> type) throws NoSuchMethodException,
            NoSuchFieldException {
        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField(component.getName());
        Method accessor = component.getAccessor();
        Constructor<?> constructor = type.getDeclaredConstructor(component.getType());
        Parameter parameter = constructor.getParameters()[0];

        System.out.println(type.getSimpleName());
        System.out.println("  declarations: component="
                + names(component.getDeclaredAnnotations())
                + "; field=" + names(field.getDeclaredAnnotations())
                + "; accessor=" + names(accessor.getDeclaredAnnotations())
                + "; parameter=" + names(parameter.getDeclaredAnnotations())
                + "; constructor=" + names(constructor.getDeclaredAnnotations()));
        System.out.println("  types: component="
                + names(component.getAnnotatedType().getAnnotations())
                + "; field=" + names(field.getAnnotatedType().getAnnotations())
                + "; return=" + names(accessor.getAnnotatedReturnType().getAnnotations())
                + "; parameter=" + names(parameter.getAnnotatedType().getAnnotations()));
    }

    private static String firstTypeArgument(AnnotatedType type) {
        AnnotatedParameterizedType parameterized = (AnnotatedParameterizedType) type;
        return names(parameterized.getAnnotatedActualTypeArguments()[0].getAnnotations());
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        show(Generated.class);
        show(Compact.class);
        show(OwnAccessor.class);
        show(OwnConstructor.class);
        show(Restated.class);
        show(NestedType.class);

        RecordComponent component = NestedType.class.getRecordComponents()[0];
        Field field = NestedType.class.getDeclaredField("values");
        Method accessor = component.getAccessor();
        Constructor<?> constructor = NestedType.class.getDeclaredConstructor(List.class);
        System.out.println("Nested component argument = "
                + firstTypeArgument(component.getAnnotatedType()));
        System.out.println("Nested field argument = "
                + firstTypeArgument(field.getAnnotatedType()));
        System.out.println("Nested return argument = "
                + firstTypeArgument(accessor.getAnnotatedReturnType()));
        System.out.println("Nested parameter argument = "
                + firstTypeArgument(constructor.getParameters()[0].getAnnotatedType()));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordAnnotationTargetsDemo.java
java RecordAnnotationTargetsDemo
```

Kết quả:

```text
Generated
  declarations: component=[Mark]; field=[FieldOnly, Mark]; accessor=[Mark]; parameter=[Mark]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[TypeMark]
Compact
  declarations: component=[Mark]; field=[Mark]; accessor=[Mark]; parameter=[Mark]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[TypeMark]
OwnAccessor
  declarations: component=[Mark]; field=[Mark]; accessor=[]; parameter=[Mark]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[]; parameter=[TypeMark]
OwnConstructor
  declarations: component=[Mark]; field=[Mark]; accessor=[Mark]; parameter=[]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[]
Restated
  declarations: component=[Mark]; field=[Mark]; accessor=[Mark]; parameter=[Mark]; constructor=[Mark]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[TypeMark]
NestedType
  declarations: component=[]; field=[]; accessor=[]; parameter=[]; constructor=[]
  types: component=[]; field=[]; return=[]; parameter=[]
Nested component argument = [TypeMark]
Nested field argument = [TypeMark]
Nested return argument = [TypeMark]
Nested parameter argument = [TypeMark]
```

Hàm `names()` sắp xếp tên annotation để kết quả dễ đối chiếu. Không dùng thứ tự các phần tử trong mảng annotation làm quy tắc ưu tiên.

`show()` là hàm kiểm chứng cho những record đã biết trong thí nghiệm; mỗi record ở đây có đúng một thành phần. Nó không được thiết kế như bộ quét tùy ý cho mọi loại lớp.

## 4. Đọc kết quả khi thành viên được cung cấp ngầm định

### `Generated`: một vị trí trong nguồn, nhiều đích metadata

Header có `@Mark @FieldOnly @TypeMark String text`, nhưng kết quả không phải ba annotation khai báo trên `RecordComponent`.

| Vị trí được truy vấn | Annotation khai báo nhìn thấy |
| --- | --- |
| `RecordComponent` | `Mark` |
| Trường `text` | `FieldOnly`, `Mark` |
| Accessor `text()` | `Mark` |
| Tham số constructor chuẩn | `Mark` |
| Chính khai báo constructor | Không có |

`FieldOnly` hợp lệ trong header nhờ đích trường dữ liệu, và nó xuất hiện trên trường tương ứng. Nhưng `RecordComponent.getDeclaredAnnotations()` không thấy `FieldOnly`, vì kiểu annotation đó không có đích `RECORD_COMPONENT`.

`TypeMark` không xuất hiện trong các mảng annotation khai báo ở bảng trên. Nó xuất hiện ở những đối tượng `AnnotatedType` của kiểu thành phần, trường, kiểu trả về accessor và tham số.

`Mark` có đích `CONSTRUCTOR` nhưng dòng `constructor=[]` vẫn rỗng. Điều này cho thấy “được phép dùng trên constructor” không có nghĩa “mọi lần dùng annotation ở header đều tự đánh dấu constructor”.

### `Compact`: tham số vẫn được suy ra từ header

`Compact` tự viết phần thân constructor chuẩn rút gọn nhưng không tự viết danh sách tham số. Các tham số vẫn được suy ra từ header, nên tham số `text` có `Mark` và kiểu tham số có `TypeMark`.

Việc có một phần thân constructor tường minh không đủ để kết luận metadata tham số bị mất; phải phân biệt **constructor rút gọn** với **constructor đầy đủ có danh sách tham số tự khai báo**.

## 5. Khi tự khai báo accessor hoặc constructor

### Accessor tường minh

`OwnAccessor` tự viết `public String text()`. Trong kết quả, annotation khai báo trên accessor là `[]`, và annotation trên kiểu trả về cũng là `[]`.

Annotation ở header vẫn tồn tại trên thành phần và trường; constructor chuẩn ngầm định vẫn có metadata tham số phù hợp. Chỉ accessor đã tự khai báo không nhận các annotation từ header một cách tự động.

Nếu công cụ của bạn đọc metadata trên accessor, việc thay một accessor ngầm định bằng accessor tường minh có thể làm thay đổi kết quả, dù tên và kiểu trả về của phương thức không đổi.

### Constructor chuẩn đầy đủ

`OwnConstructor` tự viết danh sách tham số `String text`. Kết quả cho thấy tham số đó không có `Mark`, và kiểu của nó không có `TypeMark` nếu không được ghi lại trong khai báo tham số.

Ngược lại, accessor vẫn được cung cấp ngầm định nên nhận metadata từ header theo các đích thích hợp.

### Ghi lại metadata khi cần

`Restated` chủ động viết annotation trên tham số và accessor tường minh. Vì thế các vị trí này lại nhìn thấy `Mark` hoặc `TypeMark`.

Annotation `@Mark` được viết riêng ngay trên khai báo constructor của `Restated` cũng làm `constructor=[Mark]`. Đây là annotation trực tiếp trên constructor, không phải kết quả của việc dùng `@Mark` trong header.

Tóm tắt hành vi của `Mark` trong các record của thí nghiệm:

| Record | Thành phần | Trường | Accessor | Tham số chuẩn | Constructor |
| --- | --- | --- | --- | --- | --- |
| `Generated` | Có | Có | Có | Có | Không |
| `Compact` | Có | Có | Có | Có | Không |
| `OwnAccessor` | Có | Có | Không | Có | Không |
| `OwnConstructor` | Có | Có | Có | Không | Không |
| `Restated` | Có | Có | Có do ghi trực tiếp | Có do ghi trực tiếp | Có do ghi trực tiếp |

Quy tắc truyền sang trường, accessor và tham số được mô tả trong [JLS về thành viên record](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3) cùng phần constructor chuẩn. Cơ chế này không phải kế thừa annotation theo `@Inherited`.

## 6. `TYPE_USE` cần được đọc tại đúng vị trí trong cấu trúc kiểu

Annotation khai báo và annotation trên kiểu là hai kênh metadata khác nhau:

| Cần quan sát | API |
| --- | --- |
| Annotation khai báo của component | `component.getDeclaredAnnotations()` |
| Annotation trên kiểu ngoài cùng | `component.getAnnotatedType().getAnnotations()` |
| Annotation trên đối số generic | `((AnnotatedParameterizedType) component.getAnnotatedType()).getAnnotatedActualTypeArguments()` |

Trường hợp `NestedType(List<@TypeMark String> values)` ở thí nghiệm cho thấy `TypeMark` nằm trên `String` bên trong `List`; mảng annotation tại gốc `List` vẫn rỗng. Hàm `firstTypeArgument` trong chương trình kiểm tra trực tiếp vị trí đó cho component, field, accessor return và parameter type.

Phép ép sang `AnnotatedParameterizedType` chỉ hợp lệ khi đã xác định hình dạng kiểu như trong thí nghiệm. Với một công cụ tổng quát, hãy kiểm tra giao diện bằng `instanceof` và hỗ trợ thêm kiểu mảng, wildcard hoặc biến kiểu khi cần. Sự có mặt của `TYPE_USE` trong `@Target` chỉ xác định ngữ cảnh được phép đánh dấu; nó không khiến annotation tự thực thi kiểm tra dữ liệu.

## 7. Áp dụng trong công cụ xử lý metadata

Trước khi đọc annotation, cần quyết định nguồn metadata nào có ý nghĩa đối với công cụ:

- Xử lý cấu trúc record: có thể chọn metadata của `RecordComponent`.
- Xử lý trường dữ liệu: đọc `Field` và kiểu trường.
- Xử lý lời gọi accessor: đọc `Method` và kiểu trả về.
- Xử lý đối số tạo record: đọc `Parameter` của constructor chuẩn và kiểu tham số.

Đừng mặc định chuyển sang đọc vị trí khác chỉ vì vị trí hiện tại không có annotation. Điều đó có thể vô tình hợp nhất các hợp đồng mà tác giả chủ động tách ra, như trường hợp accessor hoặc tham số được khai báo tường minh.

Nếu công cụ thật sự muốn tổng hợp nhiều vị trí, hãy quy định thứ tự ưu tiên, cách phát hiện xung đột và cách tránh xử lý lặp cùng một ý nghĩa. Annotation xuất hiện trên nhiều khai báo do cùng một vị trí nguồn không tự nói cho công cụ biết phải thực thi một quy tắc bao nhiêu lần.

Việc truyền annotation cũng không tự thực hiện kiểm tra dữ liệu. Ví dụ, tên `TypeMark` hay một annotation tên `NonNull` chỉ là metadata nếu không có trình biên dịch, bộ xử lý hoặc mã runtime được thiết kế để sử dụng nó. Kiểm tra `Objects.requireNonNull` trong constructor `Compact` là hành vi được viết tường minh.

## 8. Lỗi thường gặp và tự kiểm tra

| Suy luận sai | Cách xác minh |
| --- | --- |
| Annotation viết trong header phải nằm trên `RecordComponent` | Kiểm tra đích `RECORD_COMPONENT` |
| Có `RUNTIME` là tìm được ở mọi vị trí | Kiểm tra cả đích áp dụng lẫn phần tử đang đọc |
| Có `METHOD` là tự truyền cả vào accessor tường minh | Phân biệt accessor ngầm định với tự khai báo |
| Mọi constructor tự viết đều làm mất metadata tham số | Phân biệt constructor rút gọn với dạng đầy đủ |
| `PARAMETER` và `CONSTRUCTOR` cùng chỉ một vị trí | Đọc `Parameter` riêng với `Constructor` |
| `TYPE_USE` được đọc bằng annotation của khai báo | Đi qua `AnnotatedType` phù hợp |
| Mức kiểu ngoài cùng không có annotation thì kiểu generic bên trong cũng không có | Duyệt cấu trúc kiểu đến đúng vị trí |
| Metadata đã được truyền thì dữ liệu tự được kiểm tra | Xác định bộ xử lý hoặc mã thực hiện quy tắc |

Hãy thử thay đổi từng yếu tố nhỏ của thí nghiệm rồi dự đoán kết quả trước khi chạy:

1. Bỏ `RECORD_COMPONENT` khỏi đích của `Mark`, giữ các đích khác: vị trí nào vẫn đọc được nó?
2. Bỏ `@Mark` trên accessor tường minh của `Restated`: annotation ở header có tự bổ sung lại không?
3. Đổi constructor đầy đủ của `OwnConstructor` thành dạng rút gọn: metadata tham số thay đổi thế nào?
4. Chuyển `@TypeMark` từ `List<@TypeMark String>` ra `@TypeMark List<String>`: vị trí trong cây kiểu cần đọc có đổi không?
5. Thay `RUNTIME` bằng `CLASS`: vì sao kết quả Reflection thay đổi dù cú pháp dùng annotation vẫn còn trong mã nguồn?

Ba câu hỏi cần giữ rõ là: **annotation được phép áp dụng ở đâu, thành viên đó được cung cấp ngầm định hay tự khai báo, và Reflection đang đọc khai báo hay đọc cách sử dụng kiểu**.
