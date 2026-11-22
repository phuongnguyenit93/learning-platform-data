# Annotation trên đối số kiểu generic và wildcard trong Java

Java cho phép gắn annotation lên **vị trí sử dụng kiểu** (*type use*), gồm kiểu nằm giữa dấu `<...>` của generic, chính wildcard `?`, và kiểu làm **giới hạn trên/dưới** của wildcard. Những annotation này mô tả *cách một kiểu được sử dụng tại vị trí cụ thể*, thay vì chỉ đánh dấu class, field hoặc method.

Ví dụ:

```java
List<@Label("element") String> names;
List<@Label("wildcard") ? extends @Label("upper") Number> numbers;
List<? super @Label("lower") Integer> receivers;
```

Đây là **các khai báo field minh họa**; cần import `java.util.List` và tự định nghĩa `@Label` có `@Target(ElementType.TYPE_USE)`. Trong ba dòng này, vị trí đặt annotation khác nhau:

- `@Label("element")` đứng trước `String`: đánh dấu **kiểu đối số generic `String`**.
- `@Label("wildcard")` đứng ngay trước `?`: đánh dấu **wildcard**.
- `@Label("upper")` đứng trước `Number`: đánh dấu **kiểu của upper bound** trong `? extends Number`.
- `@Label("lower")` đứng trước `Integer`: đánh dấu **kiểu của lower bound** trong `? super Integer`.

Dù đều xuất hiện trong khai báo một field, đây là **TYPE_USE annotations ở các vị trí lồng trong kiểu generic**, không phải annotation trực tiếp trên *field declaration*. Phân biệt vị trí là chìa khóa để đọc và kiểm tra metadata chính xác.

## 1. Cơ sở: type-use annotation là gì?

Annotation trên kiểu sử dụng được Java hỗ trợ từ Java 8, cùng với `ElementType.TYPE_USE`. Định nghĩa tối thiểu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Label {
    String value();
}
```

Ý nghĩa:

- `@Target(ElementType.TYPE_USE)` cho phép annotation xuất hiện tại **các ngữ cảnh sử dụng kiểu** mà Java quy định, bao gồm kiểu đối số generic và wildcard.
- `@Retention(RetentionPolicy.RUNTIME)` cho phép các annotation phù hợp được giữ trong class file để đọc qua **annotated type reflection** lúc chạy.
- Element `value()` cung cấp một chuỗi để minh họa thông tin được đính kèm. Java không diễn giải nội dung chuỗi này thành quy tắc nghiệp vụ.

Nếu chỉ khai báo `@Target(FIELD)`, bạn có thể đánh dấu một field, nhưng **không thể** dùng annotation đó trên `String` bên trong `List<String>` theo cú pháp `List<@Label String>`. Để đánh dấu các vị trí kiểu bên trong generic, annotation cần target `TYPE_USE`.

### Ví dụ đối chiếu declaration và type use

```java
import java.util.List;

// Giả sử FieldTag chỉ cho phép FIELD,
// còn TypeTag chỉ cho phép TYPE_USE.
@FieldTag
List<@TypeTag String> names;
```

Đây là **đoạn minh họa không độc lập**, cần khai báo `FieldTag`, `TypeTag` phù hợp và đặt field bên trong class.

- `@FieldTag` gắn lên **khai báo field** tên `names`.
- `@TypeTag` gắn lên **kiểu `String` dùng làm đối số generic**.
- Không nên trông chờ `Field.getAnnotation(TypeTag.class)` đọc được annotation nằm trên `String` trong generic. Khi đọc metadata TYPE_USE, phải đi qua `Field.getAnnotatedType()` rồi các lớp kiểu lồng.

Một annotation chỉ khai báo `TYPE_USE` không nên bị hiểu đơn giản là “annotation của mọi field”. Việc viết gần khai báo field không đồng nghĩa metadata ấy thuộc về field declaration.

## 2. Annotation trên đối số kiểu generic

Generic của Java dùng đối số kiểu như `List<String>`, `Map<String, Integer>` hoặc `Optional<User>`. Khi muốn ghi metadata cho **đối số kiểu cụ thể**, đặt annotation trước kiểu được dùng:

```java
List<@Label("name") String> names;

Map<
    @Label("key") String,
    @Label("value") Integer
> counts;

List<List<@Label("nested-element") String>> nested;
```

Đây là **các khai báo field minh họa**, chưa tạo thành class hay chương trình chạy. Annotation đang đứng trước:

- `String` của `List<String>`.
- `String` và `Integer` của `Map<String, Integer>`.
- `String` nằm **bên trong** `List<List<String>>`.

Vị trí trong biểu thức generic rất quan trọng. Hai khai báo sau mang metadata khác nhau:

```java
@Label("outer")
List<String> first;

List<@Label("inner") String> second;
```

Đây là **hai field minh họa**, với `Label` cho phép `TYPE_USE`.

- `@Label("outer")` đặt trước `List<String>` để chú thích vị trí dùng kiểu **List** của field `first`.
- `@Label("inner")` đặt ngay trước `String` để chú thích **đối số kiểu String** của field `second`.

Việc cả hai field cùng có kiểu Java nhìn thấy là `List<String>` không khiến metadata ở hai vị trí trở nên tương đương. Công cụ xử lý type annotation phải biết **vị trí nào** được annotate.

### Kiểu đối số không phải là khai báo type parameter

Phân biệt:

```java
class Box<T> { }                       // Khai báo type parameter T.

class Demo {
    Box<@Label("actual-argument") String> box;
}
```

Đây là **đoạn minh họa**, giả sử `Label` đã được định nghĩa.

- `T` ở `class Box<T>` là **type parameter declaration**.
- `String` ở `Box<String>` là **type argument use** tại một vị trí dùng `Box`.

Đích `ElementType.TYPE_PARAMETER` tồn tại riêng cho **khai báo type parameter**, trong khi `TYPE_USE` dùng cho ngữ cảnh sử dụng kiểu và cũng được phép tại một số vị trí khai báo type parameter theo quy tắc của Java. Khi bài toán của bạn là annotation trên **đối số kiểu cụ thể** như `Box<@Label String>`, hãy kiểm tra `TYPE_USE`.

## 3. Wildcard: annotation trên chính dấu ?

Một type argument có thể là một kiểu cụ thể hoặc một **wildcard**. Cú pháp wildcard theo Java Language Specification có dạng:

```text
{Annotation} ? [WildcardBounds]

WildcardBounds có thể là:
    extends ReferenceType
    super ReferenceType
```

Dấu `?` đại diện cho một kiểu chưa biết theo những ràng buộc nhất định. Để annotate **wildcard**, đặt annotation **ngay trước dấu hỏi**:

```java
List<@Label("any") ?> anyList;

List<@Label("source") ? extends Number> source;

List<@Label("destination") ? super Integer> destination;
```

Đây là **các khai báo field minh họa** có annotation TYPE_USE. Cả ba annotation trên đều gắn với **wildcard**, không trực tiếp gắn lên `Number` hoặc `Integer`.

Phân biệt rõ với:

```java
List<? extends @Label("numeric-upper-bound") Number> source;
List<? super @Label("integer-lower-bound") Integer> destination;
```

Ở đây annotation đứng **sau `extends` hoặc `super`**, trước tên kiểu, nên metadata thuộc **kiểu bound**, không thuộc nút wildcard `?`.

Có thể ghi đồng thời hai mức:

```java
List<@Label("wildcard") ? extends @Label("upper-bound") Number> values;
```

Trong một khai báo duy nhất:

- `@Label("wildcard")` thuộc wildcard.
- `@Label("upper-bound")` thuộc kiểu `Number` làm upper bound.
- Hai giá trị khác nhau là có chủ ý; reflection có thể truy xuất riêng.

### Wildcard và ý nghĩa generic vẫn giữ nguyên

Ví dụ `List<? extends Number>` thường được dùng khi một API cần đọc những giá trị tương thích `Number` mà không biết đối số kiểu cụ thể. `List<? super Integer>` dùng khi cần kiểu chứa phù hợp để đưa `Integer` vào.

Đó là **quy tắc variance/generic** của Java; annotation không thay thế quy tắc này.

```java
// Minh họa method Java với wildcard,
// cần import java.util.List.
static double firstValue(List<? extends Number> source) {
    return source.get(0).doubleValue();
}

static void addOne(List<? super Integer> destination) {
    destination.add(1);
}
```

Nếu gắn thêm `@Label` vào wildcard hoặc bound, compiler Java mặc định **không tự biến label đó thành một constraint nghiệp vụ**. Ví dụ đặt nhãn `"non-null"` không tự làm Java kiểm tra null. Muốn kiểm tra nullability hoặc luồng dữ liệu, phải dùng công cụ hiểu annotation cụ thể, như static analysis/checker tương ứng.

## 4. Ba lớp metadata: container, wildcard và bound

Xét một khai báo:

```java
List<@Label("wild") ? extends @Label("bound") Number> numbers;
```

Có thể hình dung cấu trúc kiểu:

```text
Field numbers
└── parameterized type: List<...>
    └── type argument: wildcard ?
        ├── annotation trên '?': @Label("wild")
        └── upper bound: Number
            └── annotation trên Number: @Label("bound")
```

Người viết thư viện xử lý annotation không nên chỉ “tìm `@Label` trên field” mà phải biết mục tiêu:

| Vị trí | Phần tử phản ánh metadata | Ví dụ |
| --- | --- | --- |
| Field declaration | `Field` và `Field.getAnnotation(...)` | Annotation khai báo `@Target(FIELD)` |
| Kiểu field được khai báo | `Field.getAnnotatedType()` | Annotation trên vị trí dùng kiểu `List` |
| Type argument `String` | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` | `List<@Label String>` |
| Wildcard `?` | `AnnotatedWildcardType` đại diện argument wildcard | `List<@Label ?>` |
| Bound `Number` / `Integer` | `getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` | `? extends @Label Number` |

Các API này được bổ sung để phản ánh những annotation **trên lần sử dụng kiểu**. Việc chỉ gọi `Field.getGenericType()` hoặc `ParameterizedType.getActualTypeArguments()` giúp biết *cấu trúc kiểu generic*, nhưng **không đủ** để duyệt toàn bộ thông tin annotation ở các type-use lồng nhau.

## 5. Ví dụ Java 17+ hoàn chỉnh: đọc type argument, wildcard và bounds

Tạo đúng một tệp **`TypeUseDemo.java`** với toàn bộ nội dung sau. Đây là chương trình **độc lập và đã được biên dịch/chạy kiểm chứng bằng JDK**, minh họa tất cả các cấp annotation đã nói.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.util.List;
import java.util.Map;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

class TypeSamples {
    List<@Mark("element") String> names;

    List<@Mark("wildcard") ? extends @Mark("upper") Number> readOnlyNumbers;

    List<@Mark("sink") ? super @Mark("lower") Integer> writeNumbers;

    Map<@Mark("key") String, List<@Mark("nested") Integer>> index;
}

public class TypeUseDemo {
    private static String mark(AnnotatedType t) {
        Mark a = t.getAnnotation(Mark.class);
        return a == null ? "none" : a.value();
    }

    private static AnnotatedParameterizedType fieldType(String name)
            throws NoSuchFieldException {
        return (AnnotatedParameterizedType)
                TypeSamples.class.getDeclaredField(name).getAnnotatedType();
    }

    public static void main(String[] args) throws Exception {
        AnnotatedType arg = fieldType("names").getAnnotatedActualTypeArguments()[0];
        System.out.println("names-arg=" + mark(arg));

        AnnotatedWildcardType upper = (AnnotatedWildcardType)
                fieldType("readOnlyNumbers").getAnnotatedActualTypeArguments()[0];
        System.out.println("upper-wildcard=" + mark(upper));
        System.out.println("upper-bound=" + mark(upper.getAnnotatedUpperBounds()[0]));

        AnnotatedWildcardType lower = (AnnotatedWildcardType)
                fieldType("writeNumbers").getAnnotatedActualTypeArguments()[0];
        System.out.println("lower-wildcard=" + mark(lower));
        System.out.println("lower-bound=" + mark(lower.getAnnotatedLowerBounds()[0]));

        AnnotatedType nestedList = fieldType("index").getAnnotatedActualTypeArguments()[1];
        AnnotatedType nestedArg = ((AnnotatedParameterizedType) nestedList)
                .getAnnotatedActualTypeArguments()[0];
        System.out.println("nested-arg=" + mark(nestedArg));
        System.out.println("field-declaration=" +
                TypeSamples.class.getDeclaredField("names")
                        .isAnnotationPresent(Mark.class));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TypeUseDemo.java
java TypeUseDemo
```

Stdout **chính xác**:

```text
names-arg=element
upper-wildcard=wildcard
upper-bound=upper
lower-wildcard=sink
lower-bound=lower
nested-arg=nested
field-declaration=false
```

Giải thích từng kết quả:

1. `names-arg=element`: đối số kiểu `String` của `List` được annotate bằng `@Mark("element")`, nên `getAnnotatedActualTypeArguments()[0]` đọc được giá trị đó.
2. `upper-wildcard=wildcard`: annotation ngay trước `?` thuộc chính `AnnotatedWildcardType`.
3. `upper-bound=upper`: annotation sau `extends` thuộc upper-bound type `Number`.
4. `lower-wildcard=sink`: `@Mark("sink")` đứng trên wildcard `?` của `? super Integer`.
5. `lower-bound=lower`: `@Mark("lower")` đứng trên `Integer`, được trả bởi `getAnnotatedLowerBounds()[0]`.
6. `nested-arg=nested`: phải đi qua `Map`, chọn đối số thứ hai là `List<Integer>`, rồi đi thêm một lớp `AnnotatedParameterizedType` để lấy annotation trên `Integer`.
7. `field-declaration=false`: annotation nằm trên **kiểu đối số String**, không được khai báo trực tiếp trên field `names`. Vì vậy `Field.isAnnotationPresent(Mark.class)` trả về `false`.

Đoạn mã dùng `@Retention(RUNTIME)` vì mục tiêu bài là quan sát reflection tại runtime. Nếu dùng `SOURCE` hoặc `CLASS`, các annotation này sẽ không được API reflection thông thường trả về như trong ví dụ. Việc các type argument trong mã nguồn vẫn tồn tại không đồng nghĩa metadata mọi retention đều đọc được lúc chạy.

### Thử tách annotation wildcard khỏi annotation bound

Thay:

```java
List<@Mark("wildcard") ? extends @Mark("upper") Number> readOnlyNumbers;
```

bằng:

```java
List<? extends @Mark("upper") Number> readOnlyNumbers;
```

và giữ các lệnh reflection tương ứng. Khi đó:

- `mark(upper)` trả về `"none"` vì wildcard không được annotate.
- `mark(upper.getAnnotatedUpperBounds()[0])` vẫn trả về `"upper"`.

Tương tự, nếu chỉ ghi `List<@Mark("wildcard") ? extends Number>`, annotation tồn tại trên wildcard, không tự được sao chép sang `Number`.

### Với wildcard không bound tường minh

```java
List<@Mark("any") ?> unknownValues;
```

`getAnnotatedUpperBounds()` của wildcard không có `extends` tường minh vẫn có bound ngầm là `Object` (không mang annotation này); `getAnnotatedLowerBounds()` trả về mảng rỗng. Annotation `@Mark("any")` thuộc wildcard, không thuộc `Object` ngầm định.

## 6. Annotation generic ở method parameter và return type

Annotation trên type argument có thể xuất hiện ở nhiều **type contexts**, không chỉ field.

```java
import java.util.List;

class SampleApi {
    public List<@Mark("response-element") String> names() {
        return List.of("An", "Binh");
    }

    public void receive(List<@Mark("request-element") String> input) {
        System.out.println(input.size());
    }
}
```

Đây là **đoạn minh họa**, giả sử `Mark` đã định nghĩa với `@Target(TYPE_USE)`. Nếu muốn đọc metadata, reflection cần đi qua:

- `Method.getAnnotatedReturnType()` với annotation trên đối số kiểu của **kiểu trả về**.
- `Method.getAnnotatedParameterTypes()` rồi xét phần tử tham số có dạng `AnnotatedParameterizedType`.
- Sau đó dùng `getAnnotatedActualTypeArguments()` để đi vào `String` đã được annotate.

`Method.getAnnotation(Mark.class)` không tự trả về `@Mark` nằm sâu trong `List<@Mark String>`. Tương tự, việc runtime truyền một đối tượng `ArrayList` vào method không tự làm annotation type-use xuất hiện trên class `ArrayList`.

## 7. Type annotation và giới hạn của Java generics

### Type erasure không có nghĩa annotation dùng làm dữ liệu cấu hình bị mất hết

Java generics sử dụng **type erasure**: đa số phân biệt `List<String>` với `List<Integer>` không tồn tại như các kiểu object runtime tách biệt. Nhưng thông tin signature generic trên **khai báo** và các type-use annotations với retention thích hợp vẫn có thể được lưu vào class file, để API reflection đọc lại.

Phân biệt hai việc:

- **Kiểu thực tế của object lúc chạy:** `new ArrayList<String>() ` và `new ArrayList<Integer>() ` không tạo hai class runtime riêng.
- **Metadata trên một khai báo đã biên dịch:** reflection trên một field khai báo `List<@Mark String>` có thể đi qua `AnnotatedParameterizedType` để xem annotation trên `String`, nếu retention là `RUNTIME`.

Cần có **khai báo chứa metadata** để đọc. Không thể tùy ý nhìn vào bất cứ instance `List` rồi suy ra annotation generic từng được viết ở call site nào.

### Annotation không tự thay thế kiểm tra nullability hoặc quy tắc generic

```java
// Nếu chỉ là annotation tự định nghĩa, không có tool hiểu nội dung này:
List<@Mark("non-null") String> names;
```

Java compiler mặc định không tự từ chối việc thêm `null` vào `names` chỉ vì `"non-null"` xuất hiện trong một annotation tự định nghĩa. Để annotation có ý nghĩa kiểm tra tĩnh, cần một checker/plugin/phần mở rộng phù hợp hiểu chính sách của annotation.

Tương tự, `List<@Mark("allowed") ? extends Number>` vẫn tuân theo quy tắc đọc/ghi của `? extends Number`. Annotation không biến wildcard thành một type argument cố định và không mở quyền `add()` tùy ý.

### Không phải mọi annotation đều hợp lệ ở TYPE_USE

Ví dụ cố ý lỗi biên dịch:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.FIELD)
@interface FieldMarker {}

class Invalid {
    List<@FieldMarker String> values; // LỖI: FIELD không cho annotate type argument.
}
```

Muốn dùng annotation trên `String` như type argument, kiểu annotation phải cho phép `ElementType.TYPE_USE`. Đổi vị trí sử dụng và mở rộng target là quyết định về hợp đồng annotation; không nên tùy tiện thêm `TYPE_USE` nếu consumer chưa hỗ trợ đọc vị trí đó.

## 8. Những trường hợp cú pháp dễ nhầm

| Cách viết | Annotation gắn vào đâu? | Nhận xét |
| --- | --- | --- |
| `@Mark List<String> list;` | Vị trí sử dụng kiểu `List<String>` | Không tự đánh dấu đối số `String` |
| `List<@Mark String> list;` | Type argument `String` | Metadata nằm sâu trong parameterized type |
| `List<@Mark ?> list;` | Wildcard `?` | Metadata thuộc `AnnotatedWildcardType` |
| `List<? extends @Mark Number> list;` | Upper-bound type `Number` | Đọc qua `getAnnotatedUpperBounds()` |
| `List<? super @Mark Integer> list;` | Lower-bound type `Integer` | Đọc qua `getAnnotatedLowerBounds()` |
| `List<@Mark ? extends @Mark Number> list;` | Cả wildcard và upper bound | Hai vị trí annotate riêng |
| `Map<String, List<@Mark Integer>> data;` | Kiểu `Integer` lồng trong đối số thứ hai | Reflection phải đi qua hai cấp generic |

Bảng trên dùng `@Mark` như ký hiệu rút gọn; nếu annotation có element `String value();` bắt buộc như ví dụ thực thi, khi viết code phải cung cấp giá trị như `@Mark("x")`.

### Vị trí so với dấu < và từ khóa extends/super

Để annotate **wildcard**, cú pháp phải đặt annotation ở trước dấu `?`. Để annotate **bound**, annotation phải đặt trước chính kiểu bound, **sau** từ khóa `extends` hoặc `super`. Việc chuyển annotation giữa hai nơi có thể thay đổi ý nghĩa đối với static analyzer, dù phần kiểu Java không thay đổi.

Một wildcard `?` không thể đứng ở mọi vị trí mà type name đứng được. Ví dụ không thể khai báo một biến có kiểu chỉ là `?`; wildcard thuộc **type argument** của một parameterized type. Annotation không thay đổi quy tắc này.

## 9. Cách thiết kế và tiêu thụ annotation trên generic cho đúng

Khi bạn muốn dùng metadata để kiểm tra hoặc sinh mã, hãy quyết định cụ thể:

1. **Chọn đối tượng kiểm tra.** Đó là chính `List`, phần tử `String`, wildcard, hay kiểu bound của wildcard?
2. **Khai báo @Target chính xác.** Với annotation nằm trong type argument và wildcard, cần `TYPE_USE`.
3. **Quy định retention.** Annotation processor/compiler plugin có thể quan sát ở giai đoạn compile theo cơ chế phù hợp; reflection runtime cần `RUNTIME`.
4. **Giải thích ngữ nghĩa.** Metadata `"not-null"`, `"safe"`, `"validated"` tự nó chỉ là chuỗi; tài liệu phải nêu ai kiểm tra và hành vi được bảo đảm ở phạm vi nào.
5. **Duyệt đúng cấu trúc kiểu.** Dùng `AnnotatedParameterizedType`, `AnnotatedWildcardType` và khi cần `AnnotatedArrayType` / `AnnotatedTypeVariable`, thay vì giả định `Field.getAnnotations()` chứa tất cả.
6. **Cân nhắc type erasure và vị trí khai báo.** Không thiết kế API đòi suy ra các type-use annotations từ một instance runtime bất kỳ.
7. **Viết bài test thật về metadata.** Một ví dụ reflection như ở phần 5 giúp chứng minh annotation được ghi vào đúng vị trí sau khi biên dịch.

Trong các hệ thống validation, serialization hoặc static analysis, sự phân biệt này đặc biệt quan trọng. Một framework có thể chọn diễn giải annotation trên `List<@Rule Item>` thành chính sách cho **từng phần tử**, trong khi `@Rule List<Item>` có thể được hiểu là chính sách cho **container**. Java cho phép biểu đạt hai cách viết; hành vi cuối cùng tùy thuộc công cụ được dùng.

## 10. Lỗi thường gặp

**Lỗi 1 — Nhầm TYPE_PARAMETER với TYPE_USE.** Khai báo `<T>` và sử dụng `Box<String>` là hai chuyện khác nhau. Với `Box<@Mark String>`, cần annotation hỗ trợ type use.

**Lỗi 2 — Dùng annotation chỉ có @Target(FIELD) trong dấu <...>.** Annotation đặt trên type argument hoặc wildcard không được phép chỉ bằng `FIELD`.

**Lỗi 3 — Nhầm @Mark ? với ? extends @Mark Number.** Dòng đầu đánh dấu **wildcard**, dòng sau đánh dấu **bound**; hai metadata không nằm cùng nút trong annotated-type tree.

**Lỗi 4 — Chỉ đọc Field.getAnnotation().** API này đọc annotation trực tiếp của field, nên bỏ qua annotation trên generic type argument lồng bên trong. Dùng `Field.getAnnotatedType()` và đi sâu thích hợp.

**Lỗi 5 — Có TYPE_USE nhưng quên retention.** Mặc định `RetentionPolicy.CLASS` không khiến annotation type use truy cập được bằng reflection runtime như một annotation `RUNTIME`.

**Lỗi 6 — Cho rằng mọi instance List đều mang lại generic type annotations tại runtime.** Generic type erasure và metadata trên khai báo là hai cơ chế khác nhau; instance `ArrayList` không mang theo “annotation ở type argument của biến lúc được gán”.

**Lỗi 7 — Annotation tự có chức năng kiểm tra null hoặc giới hạn dữ liệu.** Java compiler không tự hiểu annotation tùy chỉnh; phải có checker/processor/framework biết metadata.

**Lỗi 8 — Tự thêm annotation vào bound ngầm.** Với wildcard `?`, upper bound ngầm là `Object` nhưng không được annotate tự động chỉ vì wildcard được annotate.

**Lỗi 9 — Coi annotation trên nested generic là annotation của outer type.** `Map<String, List<@Mark Integer>>` đánh dấu `Integer`, không trực tiếp đánh dấu `Map` hoặc `List`.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `List<@Mark("x") String>` và `@Mark("x") List<String>` có cùng vị trí metadata không?

**Đáp án:** Không. Cách thứ nhất annotate `String` làm type argument; cách thứ hai annotate vị trí sử dụng kiểu `List`.

**Câu 2.** Để đặt annotation ngay trước `?` trong `List<?>`, cần `ElementType.FIELD` hay `ElementType.TYPE_USE`?

**Đáp án:** `TYPE_USE`, vì wildcard nằm trong type argument.

**Câu 3.** `List<@Mark("a") ? extends @Mark("b") Number>` có bao nhiêu vị trí annotate?

**Đáp án:** Hai: wildcard `?` có nhãn `a`, upper-bound type `Number` có nhãn `b`.

**Câu 4.** Dùng reflection nào để lấy `@Mark` trên `String` của field `List<@Mark String> names;`?

**Đáp án:** `getDeclaredField("names").getAnnotatedType()`, cast/kiểm tra thành `AnnotatedParameterizedType`, gọi `getAnnotatedActualTypeArguments()[0]` rồi `getAnnotation(Mark.class)`.

**Câu 5.** Chỉ có `@Target(TYPE_USE)` mà thiếu `@Retention(RUNTIME)` thì ví dụ dùng reflection ở phần 5 có nhận được annotation không?

**Đáp án:** Không theo cách demo. `TYPE_USE` cho phép vị trí; `RUNTIME` quyết định tính khả dụng qua reflection.

**Câu 6.** `List<? super @Mark("low") Integer>` đánh dấu wildcard hay lower bound?

**Đáp án:** Lower-bound type `Integer`, vì annotation đứng sau `super` và trước tên kiểu.

**Câu 7.** Vì sao `List<@Mark("non-null") String>` không tự ngăn việc thêm `null`?

**Đáp án:** Annotation tùy chỉnh chỉ là metadata, Java mặc định không diễn giải tên/giá trị đó thành quy tắc kiểm tra. Cần checker hoặc consumer phù hợp.

## Tài liệu chính thức

- [Java Language Specification 17, §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1).
- [Java Language Specification 17, §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).
- [Java SE 17 API — ElementType.TYPE_USE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [Java SE 17 API — AnnotatedWildcardType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html).

Khi đọc hoặc viết `List<...>`, hãy xác định **annotation thuộc container, đối số kiểu, wildcard hay bound**. Đây là những vị trí khác nhau với cách truy cập metadata và khả năng diễn giải khác nhau. Thực hành với `TypeUseDemo.java` giúp nhìn thấy chính xác từng vị trí bằng reflection.
