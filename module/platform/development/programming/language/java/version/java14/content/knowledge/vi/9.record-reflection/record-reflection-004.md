# Kiểu generic và AnnotatedType của thành phần record qua Reflection

## 1. Mục tiêu và phạm vi

Một record Java khai báo trạng thái bằng **các thành phần (record components)** nằm trong header:

~~~java
record Response<T>(String requestId, List<T> results) {}
~~~

Khi cần xây dựng công cụ tự động như bộ ánh xạ dữ liệu, tạo schema, kiểm tra annotation hoặc serialization, chỉ nhìn kiểu `String`, `List` ở mức `Class<?>` thường chưa đủ. Ta còn muốn biết:

- Component `results` được khai báo là `List<T>`, không chỉ là `List`.
- `T` là một **biến kiểu (type variable)** của record generic, có giới hạn kiểu (*bounds*) nếu đã khai báo.
- Một annotation có thể gắn trực tiếp với **component** hoặc với **vị trí sử dụng kiểu (type use)**, kể cả kiểu lồng trong `List<...>`.
- Reflection trả về các đại diện khác nhau cho **kiểu sau erasure**, **cấu trúc generic**, và **cây kiểu có annotation**.

Bộ API trọng tâm của bài là `Class.isRecord()`, `Class.getRecordComponents()` và các phương thức của `java.lang.reflect.RecordComponent`:

- `getName()`, `getType()`;
- `getGenericType()`;
- `getAnnotatedType()`;
- `getAnnotation(...)` / `getDeclaredAnnotations()`;
- `getAccessor()` và `getDeclaringRecord()` khi cần liên kết với member.

**Tính hiện hành:** Record xuất hiện ở Java 14 dưới dạng preview, rồi được chuẩn hóa từ **Java 16**. `RecordComponent` và các API reflection record là tính năng chuẩn từ Java 16 và vẫn áp dụng trên các JDK hiện đại. Mọi ví dụ chạy được trong bài chọn **Java 17+**, không sử dụng cú pháp hay cờ preview cũ.

## 2. Lấy metadata thành phần từ một record

Để đọc component, bắt đầu từ chính `Class<?>` của record:

~~~java
import java.lang.reflect.RecordComponent;

record KeyValue<K, V>(K key, V value) {}

class ReadComponents {
    static void inspect() {
        Class<?> type = KeyValue.class;
        if (!type.isRecord()) {
            return;
        }

        for (RecordComponent component : type.getRecordComponents()) {
            System.out.println(component.getName());
        }
    }
}
~~~

Đây là đoạn Java minh họa có thể đặt trong cùng tệp (các type cấp package không phải `public`). Khi gọi `ReadComponents.inspect()`, stdout gồm hai dòng: `key` và `value`, theo thứ tự xuất hiện trong header.

Một số nguyên tắc quan trọng:

1. `isRecord()` chỉ đúng với loại đã được khai báo là record.
2. `getRecordComponents()` trả một mảng `RecordComponent[]` theo **thứ tự khai báo trong header**.
3. Với **record rỗng** như `record Empty() {}`, mảng có độ dài `0`.
4. Với **lớp không phải record**, `getRecordComponents()` trả **`null`**. Đừng gọi `.length` hoặc duyệt mảng trước khi kiểm tra.
5. `RecordComponent` là **metadata mô tả một component**, không phải một đối tượng chứa giá trị cụ thể của component. Để gọi accessor trên một instance, dùng `getAccessor()` trả về `Method` rồi áp dụng reflection phù hợp.

### 2.1. Component và các thành viên sinh ra từ header

~~~java
record Pair<A, B>(A left, B right) {}
~~~

Java cung cấp các field `private final` cho `left` và `right`, accessor `left()` / `right()` và canonical constructor. Nhưng `RecordComponent` **khác** với `java.lang.reflect.Field` và `java.lang.reflect.Method`. Khi cần mô tả chính xác **header** và generic declaration của component, dùng `RecordComponent` làm điểm xuất phát. Khi cần hành vi của accessor, dùng `getAccessor()` rồi mới làm việc với đối tượng `Method`.

## 3. Ba góc nhìn về kiểu component

Giả sử:

~~~java
record Bounded<T extends Number>(
        List<T> numbers,
        T latest,
        String label
) {}
~~~

Bảng sau so sánh các API:

| API | Kiểu trả về | Giữ generic? | Giữ type-use annotations? | Mục đích |
| --- | --- | --- | --- | --- |
| `getType()` | `Class<?>` | Không: cho **erasure** | Không | Biết kiểu runtime được khai báo ở dạng class/array |
| `getGenericType()` | `java.lang.reflect.Type` | Có: `T`, `List<T>`, wildcard, generic array | Không | Đọc **cấu trúc generic** của component |
| `getAnnotatedType()` | `java.lang.reflect.AnnotatedType` | Có: `getType()` của đối tượng này trả `Type` biểu diễn khai báo | Có, nếu annotation được lưu ở runtime | Đọc **cây kiểu có annotation**, gồm kiểu tham số/lồng nhau |

Với `Bounded<T extends Number>`:

- Component `numbers`: `getType()` cho `List.class`; `getGenericType()` biểu diễn `List<T>`.
- Component `latest`: `getType()` cho `Number.class` vì `T` có giới hạn trên `Number`; `getGenericType()` là biến kiểu tên `T`.
- Component `label`: `getType()` cho `String.class`; `getGenericType()` thường là đối tượng `Class` đại diện `String` vì không có cấu trúc generic cần giữ.

**Phân biệt hai phương thức cùng tên `getType()`:**
- `component.getType()` trả `Class<?>` đã xóa thông tin generic.
- `component.getAnnotatedType().getType()` trả `Type` của biểu diễn kiểu có annotation; nó có thể là `ParameterizedType`, `TypeVariable`, v.v., **không tương đương** với erasure của `component.getType()`.

Đây là khác biệt thiết yếu khi viết code phản chiếu generic.

## 4. Kiểu `Type` và các trường hợp phải xử lý

`getGenericType()` trả giao diện `Type`. Không nên ép trực tiếp kết quả về `Class<?>` cho mọi component. Tùy khai báo, nó có thể thuộc các nhóm:

| Dạng khai báo | Đại diện thường gặp trong Reflection | Cách truy cập có ích |
| --- | --- | --- |
| `String name`, `int count` | `Class<?>` | `getTypeName()` hoặc kiểm tra class |
| `List<String> names` | `ParameterizedType` | `getRawType()`, `getActualTypeArguments()` |
| `T value` | `TypeVariable<?>` | `getName()`, `getBounds()` |
| `List<? extends Number> values` | `ParameterizedType` chứa `WildcardType` | `getUpperBounds()`, `getLowerBounds()` |
| `T[] values` | `GenericArrayType` | `getGenericComponentType()` |
| `int[] values` | `Class<?>` mảng | `getComponentType()` |

Ví dụ kiểm tra an toàn khi gặp `List<String>`:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;

record Names(List<String> values) {}

class GenericInspector {
    static void inspect() {
        RecordComponent c = Names.class.getRecordComponents()[0];
        Type type = c.getGenericType();

        if (type instanceof ParameterizedType p) {
            System.out.println(p.getRawType().getTypeName());
            System.out.println(p.getActualTypeArguments()[0].getTypeName());
        }
    }
}
~~~

Đây là đoạn minh họa cần bổ sung import `java.util.List` khi đặt vào tệp độc lập. Khi gọi `GenericInspector.inspect()`, hai dòng là `java.util.List` và `java.lang.String`.

Với `TypeVariable<?>`, các bounds có thể chứa type khác chứ không nhất thiết là một `Class` đơn giản. Với wildcard `? extends T`, đọc giới hạn trên qua `WildcardType.getUpperBounds()`; với `? super T`, đọc giới hạn dưới qua `getLowerBounds()`. Mã xử lý tổng quát nên kiểm tra đúng dạng kiểu trước khi ép kiểu.

## 5. `AnnotatedType` là gì và khác annotation trên component thế nào?

Java hỗ trợ annotation đặt trên **vị trí sử dụng kiểu**, không chỉ trên một khai báo field, method hay record component. Ví dụ:

~~~java
record Sample<T>(
        @Column("items") List<@TypeHint("element") T> items
) {}
~~~

Đây là đoạn **trích minh họa**: `Column` và `TypeHint` cần được định nghĩa trước (phần 6 cung cấp chương trình hoàn chỉnh).

Hai annotation có mục đích khác nhau:

- `@Column("items")` gắn với **khai báo component**. Nếu annotation có `@Target(RECORD_COMPONENT)` và `@Retention(RUNTIME)`, tra bằng `component.getAnnotation(Column.class)` hoặc `getDeclaredAnnotations()`.
- `@TypeHint("element")` gắn với **cách sử dụng kiểu `T`** bên trong đối số generic của `List`. Nếu có `@Target(TYPE_USE)` và `@Retention(RUNTIME)`, phải đọc từ **`component.getAnnotatedType()`**, rồi đi sâu tới đối số generic.

### 5.1. Hai vị trí metadata riêng biệt

Một annotation trên component **không đồng nghĩa** annotation trên type use. `RecordComponent.getAnnotations()` và `getDeclaredAnnotations()` biểu diễn **declaration annotations** trên component. Muốn đọc **type-use annotations**, dùng `getAnnotatedType().getAnnotations()` trên đúng nút kiểu cần xét.

Trong cùng một khai báo có thể tồn tại cả hai loại metadata. Java còn có quy tắc lan truyền annotation từ record component tới field/accessor/constructor parameter tương ứng theo `@Target` thích hợp; sự lan truyền phụ thuộc loại annotation và khai báo member. Để kiểm tra **component gốc**, đừng đoán metadata từ field hoặc accessor: đọc `RecordComponent`.

### 5.2. Vì sao phải có `@Retention(RUNTIME)`?

Một annotation muốn xuất hiện trong Reflection khi chương trình chạy cần retention `RUNTIME`. Retention mặc định là `CLASS`, nên đừng suy luận “trong mã nguồn có annotation” thì `getAnnotation(...)` chắc chắn tìm thấy nó lúc chạy.

`@Target(TYPE_USE)` quyết định **được đặt annotation tại vị trí dùng kiểu**; `@Target(RECORD_COMPONENT)` quyết định **được đặt trên khai báo record component**. Đây là các điều kiện khác nhau. `TYPE_USE` cũng không tự động làm việc kiểm tra null/validation: annotation chỉ là metadata, cần chương trình hoặc framework thực sự đọc và áp dụng quy tắc.

### 5.3. Dạng cây của `AnnotatedType`

`AnnotatedType` là gốc cho nhiều biểu diễn:

| Dạng | API bổ sung | Thí dụ |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` | `List<@TypeHint T>` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` | Cách dùng type variable `T` với các bound liên quan |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` | `@TypeHint ? extends T` |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` | `T @TypeHint []` |
| `AnnotatedType` đơn giản | `getType()`, `getAnnotations()` | `@TypeHint String` |

**Annotation nằm ở tầng nào thì đọc ở tầng đó**. Nếu `List<@TypeHint String>`, annotation nằm ở **`String`**, không phải ở đối tượng `List` bên ngoài. Nếu `T @TypeHint []`, annotation nằm ở **chiều mảng** được đánh dấu; muốn đi tới kiểu phần tử `T` thì dùng `getAnnotatedGenericComponentType()`.

## 6. Ví dụ hoàn chỉnh (Java 17+): generic, annotated wildcard và generic array

Lưu toàn bộ chương trình dưới đây vào tệp **`RecordGenericReflectionDemo.java`**. Ví dụ sử dụng hai annotation riêng: `Column` cho record component declaration và `TypeHint` cho các vị trí dùng kiểu. Nó còn cho thấy việc **xóa kiểu generic** ở runtime.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.TypeVariable;
import java.util.List;
import java.util.Map;

public class RecordGenericReflectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface Column {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeHint {
        String value();
    }

    public record Report<T extends Number>(
            @Column("items") List<@TypeHint("element") T> items,
            @Column("latest") @TypeHint("component") T latest,
            @Column("history") Map<String, List<@TypeHint("wildcard") ? extends T>> history
    ) {
    }

    public record GenericArray<T>(T @TypeHint("array") [] values) {
    }

    public static void main(String[] args) {
        Class<?> clazz = Report.class;
        System.out.println("Record: " + clazz.isRecord());

        for (RecordComponent component : clazz.getRecordComponents()) {
            System.out.println(component.getName()
                    + " | erased=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | column=" + component.getAnnotation(Column.class).value());
        }

        RecordComponent[] components = clazz.getRecordComponents();
        AnnotatedParameterizedType itemsType =
                (AnnotatedParameterizedType) components[0].getAnnotatedType();
        AnnotatedType elementType = itemsType.getAnnotatedActualTypeArguments()[0];
        System.out.println("Element hint: "
                + elementType.getAnnotation(TypeHint.class).value());

        System.out.println("Latest is TypeVariable: "
                + (components[1].getGenericType() instanceof TypeVariable<?>));
        System.out.println("Latest type hint: "
                + components[1].getAnnotatedType().getAnnotation(TypeHint.class).value());

        AnnotatedParameterizedType mapType =
                (AnnotatedParameterizedType) components[2].getAnnotatedType();
        AnnotatedParameterizedType nestedList =
                (AnnotatedParameterizedType) mapType.getAnnotatedActualTypeArguments()[1];
        AnnotatedWildcardType wildcard =
                (AnnotatedWildcardType) nestedList.getAnnotatedActualTypeArguments()[0];

        System.out.println("Wildcard hint: "
                + wildcard.getAnnotation(TypeHint.class).value());
        System.out.println("Wildcard upper bound: "
                + wildcard.getAnnotatedUpperBounds()[0].getType().getTypeName());
        System.out.println("TypeHint is declaration annotation: "
                + (components[0].getAnnotation(TypeHint.class) != null));

        RecordComponent arrayComponent =
                GenericArray.class.getRecordComponents()[0];
        System.out.println("Generic array type: "
                + (arrayComponent.getGenericType() instanceof GenericArrayType));
        System.out.println("Annotated array type: "
                + (arrayComponent.getAnnotatedType() instanceof AnnotatedArrayType));
        System.out.println("Array dimension hint: "
                + arrayComponent.getAnnotatedType().getAnnotation(TypeHint.class).value());
        System.out.println("Array element type: "
                + ((AnnotatedArrayType) arrayComponent.getAnnotatedType())
                        .getAnnotatedGenericComponentType().getType().getTypeName());

        Report<Integer> instance = new Report<>(List.of(1), 1, Map.of());
        System.out.println("Record type variable: "
                + clazz.getTypeParameters()[0].getName());
        System.out.println("Runtime instance class: "
                + instance.getClass().getSimpleName());
        System.out.println("Nonrecord components null: "
                + (String.class.getRecordComponents() == null));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 RecordGenericReflectionDemo.java
java RecordGenericReflectionDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
Record: true
items | erased=java.util.List | generic=java.util.List<T> | column=items
latest | erased=java.lang.Number | generic=T | column=latest
history | erased=java.util.Map | generic=java.util.Map<java.lang.String, java.util.List<? extends T>> | column=history
Element hint: element
Latest is TypeVariable: true
Latest type hint: component
Wildcard hint: wildcard
Wildcard upper bound: T
TypeHint is declaration annotation: false
Generic array type: true
Annotated array type: true
Array dimension hint: array
Array element type: T
Record type variable: T
Runtime instance class: Report
Nonrecord components null: true
~~~

Ví dụ đã được biên dịch thành công với `javac --release 17` và chạy đúng stdout ở trên.

## 7. Giải thích từng kết quả của chương trình

### 7.1. `items`: kiểu generic có annotation ở đối số `T`

Header:

~~~java
@Column("items") List<@TypeHint("element") T> items
~~~

Phản chiếu cho biết:

- `getType().getTypeName()` là `java.util.List`. Đây là **kiểu đã xóa generic**.
- `getGenericType().getTypeName()` là `java.util.List<T>`. Đây là **khai báo có generic**.
- `getAnnotation(Column.class).value()` là `items` vì `Column` được gắn với declaration và lưu ở runtime.
- `getAnnotatedType()` đại diện cho `List<@TypeHint T>`; ở nút ngoài, đối tượng thường có dạng `AnnotatedParameterizedType`.
- `getAnnotatedActualTypeArguments()[0]` đi vào **đối số kiểu đầu tiên** (`T`); gọi `getAnnotation(TypeHint.class)` tại nút này nhận `element`.

Nếu chỉ gọi `component.getAnnotation(TypeHint.class)` thì kết quả `null` vì `TypeHint` có `@Target(TYPE_USE)`, không phải annotation declaration của component.

### 7.2. `latest`: biến kiểu có giới hạn

Header:

~~~java
@Column("latest") @TypeHint("component") T latest
~~~

`T extends Number` là type parameter của `Report`. Vì vậy:

- `getType()` cho `Number.class`: erasure của `T` lấy **giới hạn trên đầu tiên** `Number`.
- `getGenericType()` cho `TypeVariable<?>` tên `T`, **không tự đổi thành `Integer`** khi một instance được khởi tạo với `Report<Integer>`.
- `getAnnotatedType().getAnnotation(TypeHint.class)` lấy annotation trên **vị trí dùng kiểu `T`** ở chính component, trả `component`.

`@TypeHint("component")` là metadata cho **cách dùng `T` tại component này**. Nó không tự biến `T` thành một kiểu mới và không thêm điều kiện runtime nào.

### 7.3. `history`: type-use annotation nằm trên wildcard lồng nhau

Header:

~~~java
@Column("history") Map<String, List<@TypeHint("wildcard") ? extends T>> history
~~~

Các lớp generic lần lượt là:

~~~text
Map<String, List<? extends T>>
  └─ argument[1] → List<? extends T>
                       └─ argument[0] → ? extends T
                                         └─ upper bound → T
~~~

Code phản chiếu đi đúng qua ba bước:

1. `Map` bên ngoài → `AnnotatedParameterizedType`.
2. Đối số thứ hai (`List`) → `AnnotatedParameterizedType` lồng nhau.
3. Đối số thứ nhất của `List` (`? extends T`) → `AnnotatedWildcardType`. Annotation `@TypeHint("wildcard")` nằm ở **nút wildcard**, nên đọc từ chính nút này.

`wildcard.getAnnotatedUpperBounds()[0].getType().getTypeName()` trả `T` vì giới hạn trên của wildcard là biến kiểu đó. Đừng nhầm annotation trên wildcard với annotation ở giới hạn trên: chúng là **hai vị trí khác nhau** trong cú pháp.

### 7.4. `GenericArray<T>`: mảng generic

Header:

~~~java
public record GenericArray<T>(T @TypeHint("array") [] values) {}
~~~

- `getGenericType() instanceof GenericArrayType` là `true` vì component có kiểu `T[]` với phần tử generic.
- `getAnnotatedType() instanceof AnnotatedArrayType` là `true` vì đây là dạng mảng trong cây annotated type.
- `getAnnotatedType().getAnnotation(TypeHint.class)` nhận `array`, vì annotation được gắn **vào chiều mảng** theo vị trí `T @TypeHint("array") []`.
- `getAnnotatedGenericComponentType().getType().getTypeName()` trả `T`, là kiểu của phần tử.
- `getType()` của component là kiểu mảng sau erasure (ở đây `Object[]` vì `T` không có bound cụ thể).

Đối với mảng nhiều chiều, mỗi tầng mảng có thể có annotation riêng; cần đi theo `getAnnotatedGenericComponentType()` lần lượt thay vì nhìn một annotation duy nhất ở tầng ngoài.

### 7.5. Record instance generic không cho bạn biết `Integer` qua `getClass()`

Dù tạo:

~~~java
Report<Integer> instance = new Report<>(List.of(1), 1, Map.of());
~~~

`instance.getClass()` vẫn đại diện cho **lớp `Report`**. Metadata header vẫn nói `T`, không trở thành `Integer` chỉ vì một instance dùng `Report<Integer>`. Đây là hệ quả của **type erasure**.

Muốn suy ra kiểu cụ thể trong một hệ thống serializer/schema, đôi khi phải xem **điểm khai báo kiểu có tham số** ở một field, method return type, hoặc đầu vào được framework cung cấp, rồi xây dựng ánh xạ `T -> Integer`. Chỉ gọi `getRecordComponents()` trên `Report.class` **không đủ** để biết kiểu tham số của từng instance.

## 8. Cách khám phá và xử lý `Type` / `AnnotatedType` an toàn

### 8.1. Lặp theo tên component thay vì gắn cứng chỉ số

Ví dụ thực hành phía trên dùng `components[0]`, `components[1]`, `components[2]` để minh họa trên header đã biết. Với library hỗ trợ nhiều record khác nhau, nên tìm component theo tên:

~~~java
static RecordComponent findComponent(Class<?> type, String name) {
    if (!type.isRecord()) {
        throw new IllegalArgumentException("Not a record: " + type.getName());
    }
    for (RecordComponent component : type.getRecordComponents()) {
        if (component.getName().equals(name)) {
            return component;
        }
    }
    throw new IllegalArgumentException("Missing component: " + name);
}
~~~

Đây là **method minh họa**, cần import `java.lang.reflect.RecordComponent` và đặt trong lớp phù hợp. Nó không giả định component nằm ở vị trí số mấy, và cho lỗi rõ ràng nếu đầu vào sai.

### 8.2. Luôn kiểm tra dạng kiểu trước khi ép

~~~java
AnnotatedType annotated = component.getAnnotatedType();

if (annotated instanceof AnnotatedParameterizedType p) {
    AnnotatedType[] args = p.getAnnotatedActualTypeArguments();
    // Đi vào các nút args khi cần đọc type-use annotations.
} else if (annotated instanceof AnnotatedArrayType a) {
    AnnotatedType element = a.getAnnotatedGenericComponentType();
} else if (annotated instanceof AnnotatedWildcardType w) {
    AnnotatedType[] upper = w.getAnnotatedUpperBounds();
}
~~~

Đây là **đoạn minh họa** trong method có biến `component` kiểu `RecordComponent` và các import `java.lang.reflect.*` thích hợp. Không phải mọi `AnnotatedType` đều là `AnnotatedParameterizedType`. Ép kiểu vội sẽ ném `ClassCastException` khi gặp component đơn giản, mảng, wildcard hoặc type variable.

Khi xử lý **nested generic tree** tổng quát, có thể xây dựng hàm đệ quy qua các interface chuyên biệt, nhưng phải tránh vòng lặp khi type variable có bound tự tham chiếu, ví dụ `T extends Comparable<T>`. Với bài toán cụ thể, duyệt đúng những nhánh cần đọc thường dễ kiểm soát hơn.

### 8.3. Đọc annotation đúng tầng

Hai đoạn sau hỏi hai câu khác nhau:

~~~java
// Hỏi annotation gắn vào khai báo component.
Column declaration = component.getAnnotation(Column.class);

// Hỏi annotation trên kiểu ngoài cùng của component.
TypeHint topLevelTypeUse =
        component.getAnnotatedType().getAnnotation(TypeHint.class);
~~~

Nếu annotation nằm ở `List<@TypeHint String>`, `topLevelTypeUse` có thể là `null` dù annotation tồn tại bên trong đối số generic. Phải dùng `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` để vào **nút `String`**.

Lưu ý: mã này là **trích minh họa** với kiểu `Column`, `TypeHint`, `component` đã được khai báo trong chương trình đầy đủ.

## 9. Ứng dụng thực tế

### 9.1. Bộ tạo schema

Một bộ tạo schema có thể duyệt từng component theo thứ tự header, lấy tên qua `getName()`, cấu trúc generic qua `getGenericType()`, rồi xét annotation runtime để quyết định tên cột hoặc quy tắc dữ liệu.

Ví dụ với `List<T>`, nếu chỉ dùng `getType() == List.class`, schema sẽ mất thông tin về `T`. Khi bản khai báo có dạng `List<String>`, `ParameterizedType` giữ được `String`. Khi là `List<T>`, hệ thống phải giữ hoặc giải quyết `T` từ ngữ cảnh generic.

### 9.2. Kiểm tra annotation phân tầng

Một công cụ kiểm tra kiểu có thể đặt annotation trên:
- **Component declaration**, ví dụ `@Column("items")` để quy định mapping.
- **Outer type use**, ví dụ `@TypeHint T value` để diễn đạt một quy tắc trên cách dùng kiểu của component.
- **Inner type use**, ví dụ `List<@TypeHint String>`.
- **Wildcard hoặc mảng**, ví dụ `List<@TypeHint ? extends Number>` và `String @TypeHint []`.

Không đủ chỉ gọi `getAnnotations()` tại component nếu hệ thống cần nhìn cả annotation trên **kiểu tham số sâu bên trong**. Tuy nhiên, annotation chỉ lưu metadata; validation sẽ chỉ xảy ra khi code/framework đọc nó và thực thi quy tắc tương ứng.

### 9.3. Mapping và serialization không nên giả định mọi generic đều đã cụ thể

Với `Report<T>`, metadata có `T` và `? extends T`. Một mapper muốn biết kiểu phần tử thực tế cần giữ ngữ cảnh thay thế type variable. Không nên tự suy đoán `T` là `Integer` từ một giá trị chạy qua một phương thức, bởi quan hệ đó không được lưu trực tiếp trên `Class` của record.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `getRecordComponents()` trên class thường rồi duyệt trực tiếp | Class không phải record trả `null` | Kiểm tra `isRecord()` hoặc `null` trước |
| `(Class<?>) component.getGenericType()` với `List<T>` | Generic type là `ParameterizedType`, không phải `Class` | Kiểm tra `instanceof ParameterizedType` và đọc type args |
| `getType()` trả `Number` nhưng muốn `Integer` | `T extends Number` bị erasure theo bound | Đọc `getGenericType()` và giải quyết type variable ở ngữ cảnh khai báo |
| Nhìn `getAnnotations()` mà không thấy `@TypeHint` | Đang hỏi declaration annotation, annotation thực tế là TYPE_USE | Đọc `getAnnotatedType()` ở nút tương ứng |
| Gọi `getAnnotatedType().getAnnotation(...)` chỉ một lần | Annotation có thể ở đối số `List<...>` sâu hơn | Duyệt `AnnotatedParameterizedType` và các kiểu lồng |
| Quên `@Retention(RUNTIME)` | Annotation không khả dụng ở runtime reflection | Định nghĩa retention đúng khi cần phản chiếu runtime |
| Gắn `@Target(RECORD_COMPONENT)` rồi kỳ vọng nó ở type argument | Target này áp dụng cho khai báo component | Dùng `TYPE_USE` cho vị trí kiểu |
| Ép mọi `AnnotatedType` về `AnnotatedParameterizedType` | Còn có array, wildcard, type variable, simple type | Dùng `instanceof` trước khi ép |
| Lấy `Report.class` rồi kỳ vọng thấy `Integer` của instance | Generic bị erasure, class metadata chỉ biết `T` | Lấy kiểu tham số từ declaration site có đủ ngữ cảnh |
| Coi annotation là kiểm tra null tự động | Annotation chỉ mô tả metadata | Tích hợp validator hoặc logic tự kiểm tra |
| Đọc type-use annotation ở wildcard thay vì bound, hoặc ngược lại | Các nút trong cây khác nhau | Đọc đúng `AnnotatedWildcardType` và bounds |

## 11. Bài tập tự kiểm tra

Xét record:

~~~java
import java.util.List;

record Container<T extends CharSequence>(
        List<T> values,
        T primary,
        List<? super T> output
) {}
~~~

1. `values`: `getType()` là kiểu nào? `getGenericType()` biểu diễn gì?
2. `primary`: `getType()` trả `CharSequence.class` hay `String.class`? Vì sao?
3. `output`: type argument thứ nhất thuộc loại nào khi lấy từ `ParameterizedType`?
4. Nếu khởi tạo `new Container<String>(...)`, liệu `Container.class.getRecordComponents()` có tự chuyển `T` thành `String` không?
5. Nếu thêm annotation chỉ có `@Target(TYPE_USE)` vào bên trong `List<...>`, nên gọi `getAnnotation(...)` trên `RecordComponent` hay đi qua `getAnnotatedType()`?

**Đáp án và lý do:**

1. `values` có erasure `List.class`, còn `getGenericType()` biểu diễn `List<T>`.
2. `primary` có erasure `CharSequence.class` vì bound trên là `CharSequence`; `T` không tự là `String`.
3. `? super T` là `WildcardType`; nó có giới hạn dưới `T`. Khi dùng annotated reflection, nút tương ứng có thể là `AnnotatedWildcardType`.
4. Không. `Container.class` giữ tham số kiểu `T` ở khai báo lớp, không lưu ràng buộc kiểu cụ thể của từng instance.
5. Dùng `getAnnotatedType()` rồi đi đến đối số generic tương ứng. `RecordComponent.getAnnotation(...)` phục vụ annotation **trên declaration**.

## 12. Ghi nhớ trọng tâm

- `getType()` cho **kiểu sau erasure** dưới dạng `Class<?>`.
- `getGenericType()` cho **`Type`**, giữ cấu trúc generic như `List<T>`, `? extends T`, `T[]`.
- `getAnnotatedType()` cho **`AnnotatedType`**, cho phép đọc type-use annotations trên **cả cây kiểu**, gồm tham số generic, wildcard, bounds và chiều mảng.
- `getAnnotation(...)` trên `RecordComponent` dùng cho **declaration annotations** của component; không thay thế `getAnnotatedType()`.
- Muốn annotation xuất hiện khi chạy cần retention phù hợp, thông thường `@Retention(RUNTIME)`; `TYPE_USE` và `RECORD_COMPONENT` có vai trò riêng.
- Generic record tuân theo **type erasure**: `Report<Integer>` không biến metadata `Report.class` thành `Report<Integer>`.
- Trước khi đọc metadata, kiểm tra `isRecord()` và dạng của `Type` / `AnnotatedType`; với library tổng quát, tìm component theo tên hoặc theo metadata thay vì gắn cứng chỉ số.

**Nguồn chính thức:**
- [Java SE 17 — `java.lang.reflect.RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html).
- [Java SE 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html), [`AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html) và [`AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html).
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html), bao gồm cấu trúc component và quy tắc annotation.
- [Java Language Specification SE 25 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10).
