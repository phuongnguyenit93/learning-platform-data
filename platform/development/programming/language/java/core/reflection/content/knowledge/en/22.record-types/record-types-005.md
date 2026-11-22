# Annotation của record component khác annotation trên field, accessor và parameter

## 1. Một dòng khai báo, nhiều vị trí metadata

Xét một record có thành phần `name`:

~~~java
record Person(String name) {
}
~~~

Từ một thành phần trong phần đầu record, ta có những đối tượng khai báo liên quan:

~~~text
record component name
    -> trường lưu trữ private final name
    -> phương thức accessor name()
    -> tham số name của canonical constructor
~~~

Các đối tượng này có quan hệ với nhau, nhưng **không phải cùng một phần tử được gắn annotation**. Reflection cung cấp một đối tượng riêng cho mỗi vị trí:

- `RecordComponent`: thành phần record.
- `Field`: trường lưu trữ.
- `Method`: accessor.
- `Parameter`: tham số của constructor.

Vì thế, không thể thấy `@SomeAnnotation` gần một thành phần trong mã nguồn rồi kết luận rằng bốn truy vấn `getAnnotation(...)` đều phải có cùng kết quả.

Muốn hiểu kết quả, phải biết **annotation được phép áp dụng ở đâu**, **thành viên hoặc tham số là ngầm định hay được viết tường minh**, và **annotation có được giữ lại cho Reflection lúc chạy hay không**.

## 2. Target và Retention trả lời hai câu hỏi khác nhau

### 2.1. Target xác định vị trí áp dụng

`@Target` trên khai báo annotation xác định các ngữ cảnh hợp lệ.

| `ElementType` | Vị trí tương ứng trong bài |
| --- | --- |
| `RECORD_COMPONENT` | Khai báo thành phần record |
| `FIELD` | Khai báo trường lưu trữ |
| `METHOD` | Khai báo phương thức accessor |
| `PARAMETER` | Khai báo tham số của constructor |
| `TYPE_USE` | Một vị trí sử dụng kiểu, ví dụ kiểu `String` của thành phần |

Các hằng này được mô tả tại [ElementType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html).

Một annotation có thể cho phép nhiều target. Ví dụ, annotation có cả `RECORD_COMPONENT` lẫn `FIELD` có thể xuất hiện trên cả metadata thành phần lẫn trường tương ứng khi áp dụng qua phần đầu record.

Annotation chỉ có target `FIELD` vẫn có thể được viết tại vị trí thành phần trong phần đầu record và được truyền sang trường tương ứng. Điều đó **không** làm nó xuất hiện như annotation khai báo của `RecordComponent`. Chương trình ở phần sau sẽ kiểm chứng trường hợp này.

### 2.2. Retention xác định có quan sát được lúc chạy hay không

| Chính sách | Ảnh hưởng đối với Reflection lúc chạy |
| --- | --- |
| `SOURCE` | Annotation bị bỏ khi biên dịch; không quan sát được bằng Reflection thông thường |
| `CLASS` | Có trong class file nhưng không được giữ lại để các truy vấn annotation Reflection thông thường trả về |
| `RUNTIME` | Có thể được đọc qua Reflection ở vị trí phù hợp |

Nếu không khai báo `@Retention`, mặc định là `CLASS`.

Do đó, `getAnnotation(...)` trả về `null` có thể do đang hỏi sai vị trí, annotation không có ở vị trí đó, hoặc chính sách lưu giữ không cho quan sát lúc chạy. Không nên chỉ sửa `@Target` mà bỏ qua `@Retention`.

## 3. Chọn đúng đối tượng Reflection

Với một record có thành phần `name` và canonical constructor nhận `String name`, các điểm truy vấn tương ứng là:

| Cần hỏi annotation tại đâu? | Đối tượng cần đọc |
| --- | --- |
| Thành phần record | `recordType.getRecordComponents()[index]` |
| Trường lưu trữ | `recordType.getDeclaredField(component.getName())` |
| Accessor | `component.getAccessor()` |
| Tham số canonical constructor | `canonical.getParameters()[index]` |
| Kiểu của thành phần | `component.getAnnotatedType()` |
| Kiểu trả về của accessor | `accessor.getAnnotatedReturnType()` |

Mỗi đối tượng khai báo có thể được hỏi bằng `getAnnotation(...)`, `isAnnotationPresent(...)` hoặc các API đọc annotation tương ứng.

Đừng nhầm annotation của **tham số** với annotation của **constructor**. `parameter.getAnnotation(A.class)` hỏi một vị trí khác với `constructor.getAnnotation(A.class)`. Target `PARAMETER` không đồng nghĩa target `CONSTRUCTOR`.

Cũng không cần mở quyền truy cập để chỉ đọc annotation của một trường private. Đọc metadata bằng `Field.getAnnotation(...)` khác với đọc hoặc ghi giá trị trường bằng `Field.get(...)` hay `Field.set(...)`.

## 4. Chương trình đầy đủ: đối chiếu bốn vị trí

Chương trình sau khai báo các annotation chỉ dành cho từng vị trí, một annotation dùng chung bốn vị trí và một annotation chỉ dành cho kiểu.

Nó cũng so sánh:

- Record có accessor và canonical constructor ngầm định.
- Record viết tường minh accessor và canonical constructor có danh sách tham số.
- Record có compact constructor.
- Record đặt các giá trị annotation khác nhau tại từng vị trí.

Lưu vào `RecordAnnotationLocationsDemo.java`:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordAnnotationLocationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface OnComponent {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface OnField {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface OnMethod {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface OnParameter {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.RECORD_COMPONENT, ElementType.FIELD,
             ElementType.METHOD, ElementType.PARAMETER})
    public @interface Everywhere {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeMark {
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface ClassOnly {
    }

    public record Automatic(
            @OnComponent @OnField @OnMethod @OnParameter
            @Everywhere("header") @TypeMark @ClassOnly String text) {
    }

    public record Manual(@Everywhere("header") @TypeMark String text) {
        public Manual(String text) {
            this.text = text;
        }

        public String text() {
            return text;
        }
    }

    public record Compact(@Everywhere("header") @TypeMark String text) {
        public Compact {
            text = text.strip();
        }
    }

    public record ExplicitValues(@Everywhere("header") String text) {
        public ExplicitValues(@Everywhere("parameter") String text) {
            this.text = text;
        }

        @Everywhere("accessor")
        public String text() {
            return text;
        }
    }

    static String names(AnnotatedElement element) {
        return Arrays.stream(element.getDeclaredAnnotations())
                .map(Annotation::annotationType)
                .map(Class::getSimpleName)
                .sorted()
                .toList()
                .toString();
    }

    static void inspect(Class<?> type) throws NoSuchMethodException,
            NoSuchFieldException {
        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField(component.getName());
        Method accessor = component.getAccessor();
        Constructor<?> constructor =
                type.getDeclaredConstructor(component.getType());
        Parameter parameter = constructor.getParameters()[0];

        System.out.println("== " + type.getSimpleName() + " ==");
        System.out.println("component: " + names(component));
        System.out.println("field: " + names(field));
        System.out.println("accessor: " + names(accessor));
        System.out.println("parameter: " + names(parameter));
        System.out.println("component type: "
                + names(component.getAnnotatedType()));
        System.out.println("field type: "
                + names(field.getAnnotatedType()));
        System.out.println("accessor return type: "
                + names(accessor.getAnnotatedReturnType()));
        System.out.println("parameter type: "
                + names(parameter.getAnnotatedType()));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        inspect(Automatic.class);
        inspect(Manual.class);
        inspect(Compact.class);

        RecordComponent component =
                Automatic.class.getRecordComponents()[0];
        System.out.println("ClassOnly visible at runtime: "
                + component.isAnnotationPresent(ClassOnly.class));

        Class<?> type = ExplicitValues.class;
        RecordComponent explicit = type.getRecordComponents()[0];
        System.out.println("explicit component value: "
                + explicit.getAnnotation(Everywhere.class).value());
        System.out.println("explicit field value: "
                + type.getDeclaredField("text")
                        .getAnnotation(Everywhere.class).value());
        System.out.println("explicit accessor value: "
                + explicit.getAccessor()
                        .getAnnotation(Everywhere.class).value());
        System.out.println("explicit parameter value: "
                + type.getDeclaredConstructor(String.class)
                        .getParameters()[0]
                        .getAnnotation(Everywhere.class).value());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 RecordAnnotationLocationsDemo.java
java RecordAnnotationLocationsDemo
~~~

Kết quả chính xác:

~~~text
== Automatic ==
component: [Everywhere, OnComponent]
field: [Everywhere, OnField]
accessor: [Everywhere, OnMethod]
parameter: [Everywhere, OnParameter]
component type: [TypeMark]
field type: [TypeMark]
accessor return type: [TypeMark]
parameter type: [TypeMark]
== Manual ==
component: [Everywhere]
field: [Everywhere]
accessor: []
parameter: []
component type: [TypeMark]
field type: [TypeMark]
accessor return type: []
parameter type: []
== Compact ==
component: [Everywhere]
field: [Everywhere]
accessor: [Everywhere]
parameter: [Everywhere]
component type: [TypeMark]
field type: [TypeMark]
accessor return type: [TypeMark]
parameter type: [TypeMark]
ClassOnly visible at runtime: false
explicit component value: header
explicit field value: header
explicit accessor value: accessor
explicit parameter value: parameter
~~~

Hàm `names(...)` chủ động sắp xếp tên annotation để stdout ổn định. Không dựa vào thứ tự các annotation trong mảng Reflection.

Các record trong ví dụ đều có đúng một thành phần kiểu `String`. Vì vậy, mã khảo sát dùng vị trí `0` và chữ ký constructor một tham số. Với công cụ tổng quát, cần ánh xạ đúng các vị trí theo phần đầu record; phần 8 trình bày cách đó.

## 5. Đọc các kết quả quan trọng

### 5.1. Automatic: target quyết định nơi xuất hiện

Với record `Automatic`, kết quả khai báo là:

| Vị trí | Annotation quan sát được |
| --- | --- |
| Component | `Everywhere`, `OnComponent` |
| Field | `Everywhere`, `OnField` |
| Accessor | `Everywhere`, `OnMethod` |
| Parameter | `Everywhere`, `OnParameter` |

`OnField`, `OnMethod` và `OnParameter` không xuất hiện khi hỏi annotation khai báo trên component, dù đều được viết trong phần đầu record.

`Everywhere` có đủ bốn target nên xuất hiện ở cả bốn vị trí khi accessor và constructor tương ứng được tạo ngầm định. Đây là sự truyền annotation theo các ngữ cảnh áp dụng, không phải bốn đối tượng Reflection dùng chung một danh sách annotation.

Quy tắc về component và các thành viên liên quan nằm tại [JLS §8.10.1–8.10.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.1).

### 5.2. Manual: viết tường minh làm thay đổi nơi quan sát

Record `Manual` có annotation trong phần đầu:

~~~java
@Everywhere("header") @TypeMark String text
~~~

Nhưng accessor được viết tường minh mà không thêm annotation:

~~~java
public String text() {
    return text;
}
~~~

Và canonical constructor cũng có danh sách tham số viết tường minh:

~~~java
public Manual(String text) {
    this.text = text;
}
~~~

Các đoạn trên trích từ chương trình hoàn chỉnh, không phải các chương trình độc lập.

Kết quả:

- Component và trường vẫn có `Everywhere`.
- Accessor không tự nhận `Everywhere` từ component.
- Tham số viết tường minh không tự nhận `Everywhere` từ component.
- Annotation trên kiểu của component và trường vẫn có `TypeMark`.
- Kiểu trả về và kiểu tham số được viết tường minh không tự có `TypeMark`.

Vì vậy, việc refactor từ accessor ngầm định sang accessor viết tay có thể thay đổi metadata mà một công cụ đang đọc trên `Method`, ngay cả khi phương thức vẫn trả về cùng giá trị như trước.

Đừng kết luận metadata thành phần bị mất: `RecordComponent` vẫn có annotation của chính nó. Chỉ có những vị trí khác nhau đang cho kết quả khác nhau.

### 5.3. Compact: tham số vẫn được khai báo ngầm định

Record `Compact` viết:

~~~java
public Compact {
    text = text.strip();
}
~~~

Đây là compact canonical constructor. Người viết cung cấp phần thân, nhưng không viết lại danh sách tham số. Các tham số của nó vẫn được suy ra từ phần đầu record và được khai báo ngầm định.

Do đó, trong chương trình:

- Annotation `Everywhere` áp dụng cho tham số vẫn xuất hiện trên `Parameter`.
- Annotation `TypeMark` vẫn có trên kiểu tham số.
- Accessor không được viết tường minh nên vẫn nhận annotation phù hợp.

Không áp dụng máy móc quy tắc “có viết constructor thì không truyền annotation”. Cần phân biệt **canonical constructor thông thường có danh sách tham số tường minh** với **compact constructor có tham số ngầm định**. Quy tắc hai dạng constructor được mô tả ở [JLS §8.10.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4).

### 5.4. ExplicitValues: cùng loại annotation nhưng giá trị có thể khác

Bốn dòng cuối của chương trình là:

~~~text
explicit component value: header
explicit field value: header
explicit accessor value: accessor
explicit parameter value: parameter
~~~

Chương trình hợp lệ. Annotation trên component có giá trị `header`, còn accessor và tham số canonical constructor được viết tường minh với các giá trị khác.

Vì thế, một công cụ không thể mặc định:

~~~text
Tìm thấy cùng một loại annotation
    -> mọi vị trí đều diễn đạt cùng một cấu hình
~~~

Nếu muốn kết hợp cấu hình từ nhiều nơi, công cụ phải định nghĩa rõ nơi ưu tiên và cách xử lý xung đột. Không nên nối tất cả annotation tìm được rồi xem chúng là các bản sao tương đương.

### 5.5. ClassOnly: target đúng nhưng Reflection vẫn không thấy

`ClassOnly` có target `RECORD_COMPONENT` nhưng retention là `CLASS`. Dòng kiểm tra cho:

~~~text
ClassOnly visible at runtime: false
~~~

Đây không phải bằng chứng rằng compiler không nhận annotation. Nó cho thấy annotation không được cung cấp qua API Reflection runtime ở chính sách lưu giữ đó.

Nếu cần khảo sát annotation có retention `CLASS`, đó là bài toán đọc class file bằng công cụ phù hợp, khác với việc chỉ gọi `RecordComponent.getAnnotation(...)`.

## 6. Annotation của khai báo khác annotation trên kiểu

`RecordComponent.getAnnotation(...)` trả lời về annotation **của khai báo thành phần**. Để hỏi annotation **trên vị trí sử dụng kiểu**, dùng `getAnnotatedType()`.

Trong record `Automatic`, `TypeMark` chỉ có target `TYPE_USE`. Vì vậy:

- Nó không xuất hiện trong danh sách annotation khai báo của component.
- Nó xuất hiện trên `component.getAnnotatedType()`.
- Với các phần tương ứng ngầm định, nó cũng xuất hiện trên kiểu trường, kiểu trả về accessor và kiểu tham số.

Có thể hình dung hai kênh riêng:

~~~text
RecordComponent
    -> getAnnotation(...)          : annotation của khai báo
    -> getAnnotatedType()
         -> getAnnotation(...)     : annotation trên kiểu
~~~

Một annotation có cả target `RECORD_COMPONENT` và `TYPE_USE` có thể được áp dụng theo cả hai vai trò. Khi đó hai truy vấn có thể cùng nhìn thấy một loại annotation, nhưng chúng vẫn đang đọc hai vị trí metadata khác nhau.

Đọc `getGenericType()` cũng không thay cho đọc `getAnnotatedType()`. `Type` mô tả cấu trúc kiểu; `AnnotatedType` cho phép khảo sát cấu trúc đó cùng các annotation trên vị trí sử dụng kiểu.

### Annotation lồng trong đối số generic

Với thành phần `List<@TypeMark String> values`, `TypeMark` được gắn với **lần sử dụng kiểu `String`**, không phải khai báo component hay kiểu `List` ngoài cùng. Vì thế, hai phép hỏi tại component và gốc `component.getAnnotatedType()` có thể không thấy annotation.

Mã minh họa sau giả sử đã có `RecordComponent component` của thành phần `values`, annotation `TypeMark` có `@Target(TYPE_USE)` và `@Retention(RUNTIME)`:

~~~java
java.lang.reflect.AnnotatedType root = component.getAnnotatedType();
if (root instanceof java.lang.reflect.AnnotatedParameterizedType listType) {
    boolean marked = listType.getAnnotatedActualTypeArguments()[0]
            .isAnnotationPresent(TypeMark.class);
    System.out.println(marked); // true với List<@TypeMark String>
}
~~~

Dùng `instanceof` vì không phải mọi component đều có kiểu generic. Với mảng, wildcard hoặc biến kiểu, cần chọn giao diện `AnnotatedType` tương ứng và đi tới đúng nút; không làm phẳng các annotation của những vị trí kiểu khác nhau thành một tập chung.

## 7. Một ma trận quy tắc để tự dự đoán

Giả sử annotation có retention `RUNTIME` và được viết ở thành phần trong phần đầu record:

| Target của annotation | Component | Trường lưu trữ | Accessor ngầm định | Tham số ngầm định của canonical constructor |
| --- | --- | --- | --- | --- |
| Chỉ `RECORD_COMPONENT` | Có | Không | Không | Không |
| Chỉ `FIELD` | Không | Có | Không | Không |
| Chỉ `METHOD` | Không | Không | Có | Không |
| Chỉ `PARAMETER` | Không | Không | Không | Có |
| Cả bốn target trên | Có | Có | Có | Có |
| Chỉ `TYPE_USE` | Không ở annotation khai báo | Đọc trên kiểu trường | Đọc trên kiểu trả về | Đọc trên kiểu tham số |

Với dòng `TYPE_USE`, còn phải đọc `component.getAnnotatedType()` để quan sát annotation trên kiểu thành phần. Vị trí có thể nằm sâu trong cấu trúc kiểu, như ví dụ `List<@ItemMark String>`.

Ma trận dành cho các phần ngầm định. Accessor viết tường minh và tham số của canonical constructor có danh sách tham số viết tường minh phải được xem theo khai báo của chính chúng.

Việc truyền annotation của record là quy tắc ngôn ngữ, không phải cơ chế kế thừa annotation qua `@Inherited`. Không dùng `@Inherited` như cách yêu cầu tự truyền annotation giữa component, field, accessor và parameter.

## 8. Ánh xạ đúng canonical constructor trong công cụ tổng quát

Chương trình đầu có một thành phần, nên dễ xác định tham số tương ứng. Với record có nhiều thành phần, nên bắt đầu từ thứ tự của `getRecordComponents()` và dựng chữ ký canonical constructor từ kiểu của các thành phần.

Đoạn sau là mã minh họa đặt trong một phương thức; `recordType` là token của lớp record đã biết. Cần các import Reflection tương ứng và `java.util.Arrays`; phương thức chứa đoạn này phải xử lý `NoSuchMethodException`.

~~~java
RecordComponent[] components = recordType.getRecordComponents();
if (components == null) {
    throw new IllegalArgumentException("Expected a record class");
}

Class<?>[] parameterTypes = Arrays.stream(components)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);

Constructor<?> canonical =
        recordType.getDeclaredConstructor(parameterTypes);
Parameter[] parameters = canonical.getParameters();

for (int i = 0; i < components.length; i++) {
    RecordComponent component = components[i];
    Parameter parameter = parameters[i];

    System.out.println(component.getName() + " -> "
            + parameter.getDeclaredAnnotations().length);
}
~~~

Các điểm cần giữ:

- Chọn canonical constructor bằng đúng danh sách kiểu và thứ tự thành phần.
- Không chọn constructor đầu tiên trong `getDeclaredConstructors()`; record có thể có constructor bổ sung.
- Dùng `getType()` để có `Class<?>` tìm chữ ký, không ép mọi `getGenericType()` thành `Class`.
- Ánh xạ tham số theo thứ tự thành phần, không đoán từ thứ tự field.
- Khi chỉ cần annotation của parameter, không cần tạo một đối tượng record hay gọi constructor.

Với canonical constructor viết tường minh, vẫn có quan hệ vị trí giữa thành phần và tham số, nhưng annotation của tham số có thể khác annotation trên component. Ánh xạ được hai vị trí không có nghĩa dữ liệu annotation của chúng giống nhau.

## 9. Cách thiết kế quy tắc đọc annotation

Một công cụ nên bắt đầu từ câu hỏi nghiệp vụ cụ thể:

- Nếu annotation mô tả thành phần trong lược đồ dữ liệu record, hãy xác định liệu nguồn cấu hình là `RecordComponent`.
- Nếu công cụ làm việc qua accessor, hãy quyết định cách xử lý annotation trên `Method` và kiểu trả về.
- Nếu công cụ chuẩn bị đối số để gọi constructor, annotation của `Parameter` là một nguồn thông tin riêng.
- Nếu annotation nói về kiểu dữ liệu hoặc phần tử trong cấu trúc generic, phải khảo sát `AnnotatedType`.

Đừng tự suy rằng annotation ở vị trí khác “chắc là cùng một annotation bị Reflection bỏ sót”. Hãy đọc từng nơi cần thiết và xác định chính sách rõ ràng.

Khi gặp nhiều vị trí có cấu hình khác nhau, công cụ có thể ưu tiên một vị trí, báo xung đột hoặc hỗ trợ một quy tắc kết hợp đã được định nghĩa. Lựa chọn đó thuộc hợp đồng của công cụ, không phải hành vi tự động của Reflection.

Nếu annotation là loại lặp được, nên dùng `getAnnotationsByType(...)` hoặc `getDeclaredAnnotationsByType(...)` theo nhu cầu để đọc các lần xuất hiện qua container. Đây vẫn là thao tác trên **một vị trí đã chọn**, không phải tự hợp nhất bốn vị trí của record.

## 10. Tự kiểm tra

1. Annotation chỉ có target `FIELD` được viết trước một thành phần record. Có thể đọc nó bằng `RecordComponent.getAnnotation(...)` không?
2. Annotation có target `RECORD_COMPONENT` và retention mặc định. Vì sao Reflection runtime có thể không thấy?
3. Khi viết tường minh accessor nhưng không chép annotation từ phần đầu record, annotation trên accessor có được tự truyền như accessor ngầm định không?
4. Compact constructor có tham số ngầm định hay danh sách tham số do người viết khai báo tường minh?
5. Annotation trên một tham số canonical constructor có đồng nghĩa annotation trên chính constructor không?
6. Với `List<@ItemMark String>`, vì sao hỏi annotation trên component và trên kiểu `List` ngoài cùng đều có thể không thấy?
7. Nếu component có `@Everywhere("header")` nhưng accessor viết tay có `@Everywhere("accessor")`, chương trình có nhất thiết lỗi biên dịch không?
8. Vì sao một công cụ không nên chọn constructor đầu tiên để đọc annotation tham số của record?

Đáp án:

1. Không với annotation chỉ có target đó. Hãy đọc trên `Field` tương ứng.
2. Retention mặc định là `CLASS`, không phải `RUNTIME`.
3. Không. Phải xem annotation của chính accessor được viết tường minh.
4. Tham số ngầm định, suy ra từ phần đầu record; annotation phù hợp được áp dụng theo các quy tắc cho tham số suy ra.
5. Không. Đây là hai vị trí khai báo khác nhau.
6. Annotation nằm trên đối số kiểu `String`; cần đi sâu qua `AnnotatedParameterizedType`.
7. Không. Chương trình mẫu cho thấy các giá trị ở những vị trí đó có thể khác nhau hợp lệ.
8. Record có thể có constructor bổ sung và mảng constructor không có thứ tự chọn mong muốn; cần tìm đúng chữ ký canonical theo các thành phần.
