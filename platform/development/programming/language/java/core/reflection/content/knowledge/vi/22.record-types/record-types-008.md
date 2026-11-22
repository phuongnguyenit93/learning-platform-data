# `RecordComponent.getAnnotatedType()` và annotation trên kiểu thành phần

Một thành phần record có thể mang annotation trên chính khai báo, trên kiểu ngoài cùng, hoặc sâu bên trong kiểu generic, mảng và giới hạn kiểu. Chỉ đọc `RecordComponent.getAnnotations()` không đủ để nhìn thấy tất cả những vị trí đó.

`getAnnotatedType()` đưa bạn tới **cấu trúc kiểu có thể chứa annotation** của thành phần. Từ đó, chương trình có thể đi tới đúng vị trí được đánh dấu thay vì gộp mọi annotation thành một danh sách phẳng.

Điều này hữu ích khi viết công cụ kiểm tra dữ liệu hoặc phân tích cấu trúc kiểu: “danh sách không được rỗng”, “phần tử không được null” và “mảng có một đặc tính nào đó” có thể là các yêu cầu khác nhau ở những vị trí kiểu khác nhau.

## 1. Ba cách nhìn vào kiểu của một thành phần

[API `RecordComponent`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html) cung cấp các mức thông tin khác nhau:

| API | Kết quả | Nhu cầu chính |
| --- | --- | --- |
| `getType()` | `Class<?>` | Kiểu ở dạng lớp, dùng cho nhiều thao tác tra cứu Reflection |
| `getGenericType()` | `Type` | Cấu trúc kiểu khai báo có generic, biến kiểu hoặc wildcard |
| `getAnnotatedType()` | `AnnotatedType` | Cấu trúc kiểu khai báo kèm annotation trên từng vị trí sử dụng kiểu |

Ví dụ, với `List<@TypeNote("item") String> tags`, `getType()` cho `List.class`, còn `getGenericType()` mô tả `List<String>`. Muốn biết annotation gắn với vị trí `String` bên trong danh sách, cần đi vào cấu trúc `AnnotatedType`.

`getAnnotatedType()` mô tả **kiểu được khai báo**, không đọc giá trị của một đối tượng record và không tự đổi biến kiểu generic thành kiểu thực tế của dữ liệu đang chứa.

## 2. Annotation khai báo và annotation sử dụng kiểu

Hai kiểu annotation trong thí nghiệm có các đích riêng:

- `ComponentNote` có `@Target(RECORD_COMPONENT)`: đánh dấu chính thành phần record.
- `TypeNote` có `@Target(TYPE_USE)`: đánh dấu một vị trí sử dụng kiểu.

`TYPE_USE` cho phép đặt annotation tại những vị trí như kiểu thành phần, đối số kiểu generic hoặc kiểu phần tử mảng; đây là ngữ cảnh được phân loại trong [`ElementType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html#TYPE_USE).

Với một thành phần vừa có `@ComponentNote` vừa có `@TypeNote`, hai lời gọi này không hỏi cùng một nơi:

```java
component.getDeclaredAnnotation(ComponentNote.class);
component.getAnnotatedType().getAnnotation(TypeNote.class);
```

Đây là đoạn trích khi đã có biến `RecordComponent component` và các kiểu annotation tương ứng. Lời gọi đầu đọc metadata khai báo của thành phần; lời gọi sau đọc annotation tại gốc của kiểu thành phần.

Cả hai annotation trong ví dụ đều có `@Retention(RUNTIME)` để đọc được khi chạy. Đích áp dụng và thời gian lưu giữ là hai điều kiện độc lập.

## 3. Cần nhìn cấu trúc kiểu theo từng vị trí

[`AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html) biểu diễn một cách sử dụng kiểu có thể mang annotation. Nó không nhất thiết có annotation ở chính nút ngoài cùng.

| Dạng cấu trúc | Giao diện Reflection | Bước đi tiếp |
| --- | --- | --- |
| Kiểu generic như `List<String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| Kiểu mảng | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| Wildcard như `? extends Number` | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()` và `getAnnotatedLowerBounds()` |
| Biến kiểu như `T` | `AnnotatedTypeVariable` | `getAnnotatedBounds()` |

Không ép mọi `AnnotatedType` thành `AnnotatedParameterizedType`. Một thành phần `String`, `String[]` hay `T` có hình dạng khác. Dùng `instanceof` để chọn cách duyệt phù hợp.

## 4. Thí nghiệm đầy đủ trên Java 17+

Chương trình đánh dấu từng vị trí bằng chuỗi riêng để thấy rõ annotation nào thuộc nút nào. Nó không cần tạo đối tượng record, vì chỉ phân tích metadata kiểu.

Lưu toàn bộ vào **`RecordAnnotatedTypeDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedTypeVariable;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class RecordAnnotatedTypeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeNote {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface ComponentNote {
        String value();
    }

    public record Sample<T extends @TypeNote("bound") Number>(
            @ComponentNote("declaration-only") @TypeNote("text") String name,
            @TypeNote("list") List<@TypeNote("item") String> tags,
            @TypeNote("array-element") String @TypeNote("array") [] codes,
            List<? extends @TypeNote("upper") Number> numbers,
            List<? super @TypeNote("lower") Integer> sinks,
            @TypeNote("use-T") T quantity,
            String plain) {
    }

    public record Recursive<T extends Comparable<T>>(T value) {
    }

    private static String notes(AnnotatedType type) {
        return Arrays.stream(type.getAnnotationsByType(TypeNote.class))
                .map(TypeNote::value)
                .sorted()
                .toList()
                .toString();
    }

    private static void walk(String path, AnnotatedType type,
            Set<TypeVariable<?>> activeVariables) {
        System.out.println(path + ": " + type.getType().getTypeName()
                + " notes=" + notes(type));

        if (type instanceof AnnotatedTypeVariable variableType) {
            TypeVariable<?> variable = (TypeVariable<?>) type.getType();
            if (!activeVariables.add(variable)) {
                System.out.println(path + ".bounds: cycle stopped");
                return;
            }
            AnnotatedType[] bounds = variableType.getAnnotatedBounds();
            for (int i = 0; i < bounds.length; i++) {
                walk(path + ".bound[" + i + "]", bounds[i], activeVariables);
            }
            activeVariables.remove(variable);
            return;
        }

        AnnotatedType owner = type.getAnnotatedOwnerType();
        if (owner != null) {
            walk(path + ".owner", owner, activeVariables);
        }

        if (type instanceof AnnotatedParameterizedType parameterized) {
            AnnotatedType[] arguments = parameterized.getAnnotatedActualTypeArguments();
            for (int i = 0; i < arguments.length; i++) {
                walk(path + ".arg[" + i + "]", arguments[i], activeVariables);
            }
        } else if (type instanceof AnnotatedArrayType array) {
            walk(path + ".element",
                    array.getAnnotatedGenericComponentType(), activeVariables);
        } else if (type instanceof AnnotatedWildcardType wildcard) {
            AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
            for (int i = 0; i < upper.length; i++) {
                walk(path + ".upper[" + i + "]", upper[i], activeVariables);
            }
            AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();
            for (int i = 0; i < lower.length; i++) {
                walk(path + ".lower[" + i + "]", lower[i], activeVariables);
            }
        }
    }

    private static void inspect(Class<?> recordType) {
        RecordComponent[] components = recordType.getRecordComponents();
        if (components == null) {
            throw new IllegalArgumentException("Expected a record declaration");
        }
        System.out.println("Record " + recordType.getSimpleName());
        for (RecordComponent component : components) {
            ComponentNote declaration =
                    component.getDeclaredAnnotation(ComponentNote.class);
            System.out.println("component " + component.getName()
                    + " | raw=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | declaration="
                    + (declaration == null ? "none" : declaration.value()));
            walk("type", component.getAnnotatedType(), new HashSet<>());
        }
    }

    public static void main(String[] args) {
        inspect(Sample.class);
        inspect(Recursive.class);
        System.out.println("String class TypeNote = "
                + String.class.getAnnotation(TypeNote.class));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordAnnotatedTypeDemo.java
java RecordAnnotatedTypeDemo
```

Kết quả:

```text
Record Sample
component name | raw=java.lang.String | generic=java.lang.String | declaration=declaration-only
type: java.lang.String notes=[text]
component tags | raw=java.util.List | generic=java.util.List<java.lang.String> | declaration=none
type: java.util.List<java.lang.String> notes=[list]
type.arg[0]: java.lang.String notes=[item]
component codes | raw=java.lang.String[] | generic=java.lang.String[] | declaration=none
type: java.lang.String[] notes=[array]
type.element: java.lang.String notes=[array-element]
component numbers | raw=java.util.List | generic=java.util.List<? extends java.lang.Number> | declaration=none
type: java.util.List<? extends java.lang.Number> notes=[]
type.arg[0]: ? extends java.lang.Number notes=[]
type.arg[0].upper[0]: java.lang.Number notes=[upper]
component sinks | raw=java.util.List | generic=java.util.List<? super java.lang.Integer> | declaration=none
type: java.util.List<? super java.lang.Integer> notes=[]
type.arg[0]: ? super java.lang.Integer notes=[]
type.arg[0].upper[0]: java.lang.Object notes=[]
type.arg[0].lower[0]: java.lang.Integer notes=[lower]
component quantity | raw=java.lang.Number | generic=T | declaration=none
type: T notes=[use-T]
type.bound[0]: java.lang.Number notes=[bound]
component plain | raw=java.lang.String | generic=java.lang.String | declaration=none
type: java.lang.String notes=[]
Record Recursive
component value | raw=java.lang.Comparable | generic=T | declaration=none
type: T notes=[]
type.bound[0]: java.lang.Comparable<T> notes=[]
type.bound[0].arg[0]: T notes=[]
type.bound[0].arg[0].bounds: cycle stopped
String class TypeNote = null
```

Trong kết quả, `notes` là danh sách giá trị của riêng annotation `TypeNote` tại nút đang xét. `declaration` là giá trị của riêng `ComponentNote` trên khai báo thành phần, hoặc `none` khi không có annotation đó.

Các nhãn đường đi `type`, `arg`, `element`, `upper`, `lower`, `bound` do chương trình đặt để giải thích vị trí; chúng không phải tên do API bắt buộc cung cấp.

## 5. Đọc annotation trên kiểu thông thường và kiểu generic

### Thành phần `name`

Kết quả có `declaration=declaration-only` từ `ComponentNote`, còn `type: java.lang.String notes=[text]` từ `TypeNote`.

Hai annotation cùng được viết gần nhau trong header nhưng được đọc qua hai đối tượng metadata khác nhau. Không dùng kết quả của một truy vấn để kết luận rằng truy vấn còn lại cũng phải có cùng annotation.

Dòng cuối `String class TypeNote = null` cũng cho thấy annotation tại vị trí sử dụng `String` trong record không được gắn toàn cục lên `String.class`. Nó mô tả **lần sử dụng kiểu tại thành phần này**, không sửa khai báo lớp `String`.

### Thành phần `tags`

Kiểu ngoài cùng `List<...>` có `notes=[list]`. Đối số kiểu thứ nhất `String` có `notes=[item]`, được đọc tại `type.arg[0]`.

Để tới vị trí đó, mã dùng [`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html). Hai annotation nằm ở hai nút độc lập; đọc annotation gốc không tự gom annotation của phần tử.

Nếu một công cụ muốn áp dụng quy tắc khác nhau cho danh sách và cho phần tử, cần giữ lại đường đi của từng annotation thay vì chỉ thu một tập tên annotation.

### Thành phần `plain`

`plain` vẫn có đối tượng `AnnotatedType` mô tả `String`, dù danh sách `TypeNote` tại đó rỗng. Từ “annotated” trong tên API không có nghĩa kiểu bắt buộc phải mang ít nhất một annotation.

Cũng không nên dùng tên lớp cài đặt nội bộ của đối tượng Reflection để suy ra hình dạng kiểu. Các giao diện `AnnotatedType` và những giao diện con mới là bề mặt cần dựa vào.

## 6. Mảng: annotation trên mảng khác annotation trên phần tử

Thành phần `codes` được khai báo:

```java
@TypeNote("array-element") String @TypeNote("array") [] codes
```

Đây là đoạn trích header trong chương trình, không phải khai báo trường độc lập cần chép nguyên vào một lớp.

Vị trí trước `String` đánh dấu kiểu phần tử; vị trí trước `[]` đánh dấu kiểu mảng. Vì vậy:

- Nút `type` có `notes=[array]`.
- Nút `type.element` có `notes=[array-element]`.

Bước đi từ mảng tới kiểu phần tử dùng [`AnnotatedArrayType.getAnnotatedGenericComponentType()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html). Với mảng nhiều chiều, cần tiếp tục đi qua từng tầng mảng, không coi mọi dấu ngoặc vuông là cùng một vị trí.

Phân biệt này có ý nghĩa thực tế: một quy tắc về tham chiếu mảng và một quy tắc về từng giá trị phần tử không phải cùng một yêu cầu.

## 7. Wildcard: annotation có thể nằm trên giới hạn

### Giới hạn trên

`numbers` có kiểu `List<? extends @TypeNote("upper") Number>`. Nút `List` và nút wildcard đều không có `TypeNote`; annotation được tìm thấy ở giới hạn trên `Number`, tại `type.arg[0].upper[0]`.

Nếu chỉ hỏi gốc của `AnnotatedType`, bạn sẽ thấy mảng rỗng và bỏ sót metadata cần thiết bên trong.

### Giới hạn dưới

`sinks` có kiểu `List<? super @TypeNote("lower") Integer>`. Kết quả có giới hạn trên `Object` không được đánh dấu, cùng giới hạn dưới `Integer` mang `notes=[lower]`.

Đó là lý do bộ duyệt kiểm tra cả hai dãy giới hạn qua [`AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html). Không giả định rằng cứ thấy wildcard là phải có một annotation ở gốc wildcard, hoặc rằng chỉ cần nhìn một phía giới hạn.

## 8. Biến kiểu, giới hạn và đệ quy

### Phân biệt lần dùng `T` với giới hạn của `T`

`Sample` khai báo `T extends @TypeNote("bound") Number`. Thành phần `quantity` lại sử dụng `@TypeNote("use-T") T`.

Kết quả tách rõ:

- Nút `type: T` mang `notes=[use-T]`.
- Nút giới hạn `Number` mang `notes=[bound]`.
- `getType()` của thành phần cho `Number`, còn kiểu generic khai báo là `T`.

`getAnnotatedBounds()` trên [`AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html) đưa bạn tới các giới hạn khai báo của biến kiểu. Annotation của lần dùng biến kiểu và annotation của giới hạn là các thông tin khác nhau.

Metadata này không tự thay `T` bằng `Integer` chỉ vì một đối tượng có thể được tạo với tham số kiểu `Sample<Integer>`. Nếu cần phân giải kiểu theo ngữ cảnh sử dụng cụ thể, công cụ phải nhận và xử lý thêm ngữ cảnh generic đó.

### Giới hạn tự tham chiếu

`Recursive<T extends Comparable<T>>` tạo quan hệ:

```text
T → Comparable<T> → T → Comparable<T> → ...
```

Do đó, khi đi sâu vào giới hạn, cấu trúc cần xử lý có thể là một đồ thị có chu trình, dù cách trình bày ban đầu trông như cây.

Bộ duyệt dùng `Set<TypeVariable<?>>` để theo dõi các biến kiểu đang có trên đường đi hiện tại. Khi gặp lại cùng biến kiểu trong đường đó, nó vẫn in nút nhưng dừng mở rộng giới hạn và báo `cycle stopped`.

Biến kiểu được loại khỏi tập sau khi duyệt xong nhánh. Đây không phải một tập “đã gặp ở đâu đó trong toàn bộ kiểu” để tự động bỏ mọi lần xuất hiện về sau: các lần sử dụng khác nhau vẫn có thể mang annotation khác nhau và cần được quan sát.

Không dùng riêng tên chuỗi `"T"` làm định danh tổng quát cho biến kiểu, vì các khai báo khác nhau có thể cùng đặt tên biến là `T`.

## 9. Luồng áp dụng và giới hạn của ví dụ

Khi phân tích thành phần record:

1. Xác nhận đang có metadata của record và lấy đúng `RecordComponent`.
2. Đọc annotation khai báo riêng nếu công cụ cần ngữ nghĩa của thành phần.
3. Lấy gốc `component.getAnnotatedType()`.
4. Tại mỗi nút, đọc annotation ở chính nút đó.
5. Dựa vào giao diện kiểu để đi tới các nút con.
6. Giữ đường đi và có cơ chế dừng khi mở rộng giới hạn tự tham chiếu.

Mã còn xét `getAnnotatedOwnerType()` khi kiểu có một kiểu bao tương ứng. Điều này hữu ích với cấu trúc lớp lồng có thông tin kiểu ở phần bao. Các ví dụ chính trong bài tập trung vào generic, mảng, wildcard và biến kiểu.

Đây là bộ quan sát metadata, không phải bộ kiểm tra dữ liệu. Một annotation có tên `NonNull` hay một giá trị `TypeNote` không tự khiến JVM từ chối `null` hoặc kiểm tra từng phần tử danh sách. Muốn thực thi quy tắc, cần một bộ xử lý có hợp đồng rõ ràng.

Tương tự, đọc được metadata kiểu không tự cấp quyền truy cập trường dữ liệu, gọi accessor hay thay đổi trạng thái. Bài này không cần thao tác với dữ liệu của một instance.

## 10. Lỗi thường gặp và tự kiểm tra

| Lỗi | Cách khắc phục |
| --- | --- |
| Chỉ đọc `RecordComponent.getAnnotations()` | Phân biệt khai báo thành phần với kiểu sử dụng |
| Chỉ đọc annotation ở gốc kiểu | Duyệt đúng vị trí generic, mảng hoặc giới hạn |
| Ép mọi kiểu thành `AnnotatedParameterizedType` | Kiểm tra giao diện thực tế bằng `instanceof` |
| Gộp annotation trên mảng và phần tử | Giữ từng tầng của `AnnotatedArrayType` |
| Nhìn wildcard nhưng bỏ giới hạn | Kiểm tra dãy giới hạn trên và dưới |
| Duyệt giới hạn generic mà không phát hiện chu trình | Theo dõi biến kiểu đang mở rộng trên đường đi |
| Cho rằng metadata của `String` được sử dụng là annotation trên `String.class` | Phân biệt lần sử dụng kiểu với khai báo lớp |
| Cho rằng metadata kiểu chứa giá trị thực tế của một record | Tách việc phân tích kiểu khỏi đọc dữ liệu |

Hãy thử các thay đổi nhỏ rồi dự đoán đầu ra:

1. Bỏ `@TypeNote("list")` nhưng giữ `@TypeNote("item")`: vì sao gốc rỗng mà phần tử vẫn có annotation?
2. Đổi vị trí annotation giữa `String` và `[]` của `codes`: nút nào thay đổi?
3. Chuyển `numbers` sang một wildcard không ghi giới hạn: bộ duyệt nhìn thấy kiểu giới hạn nào?
4. Bỏ cơ chế phát hiện chu trình rồi thử `Recursive`: vì sao việc chỉ đi theo các lời gọi API hợp lệ vẫn có thể không kết thúc?
5. Thêm một thành phần `T` khác với một `TypeNote` khác: vì sao không nên bỏ qua nó chỉ vì đã gặp tên `T` trước đó?

Điểm cần nắm là **annotation thuộc một vị trí trong cấu trúc kiểu**. `getAnnotatedType()` là cửa vào cấu trúc đó; nhiệm vụ của công cụ là đi tới đúng nút, đọc đúng metadata và giữ nguyên ý nghĩa của vị trí.
