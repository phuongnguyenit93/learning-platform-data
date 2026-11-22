# Đọc kiểu generic và annotation của tham số trong Java

Một tham số Java có thể mang nhiều lớp metadata: kiểu runtime sau *type erasure*, chữ ký generic trong source, annotation trên **khai báo tham số**, annotation trên **kiểu được sử dụng**, và tên tham số nếu compiler đã lưu. Java Reflection cung cấp API khác nhau cho từng lớp. Đọc sai lớp metadata dễ khiến framework mapper, validator hay công cụ phân tích API hiểu sai hợp đồng.

Từ Java 8, `java.lang.reflect.Parameter` kết hợp với `Type` và `AnnotatedType` cho phép truy vấn cấu trúc này. Bài tập trung các kỹ thuật vẫn phù hợp trong Java 17+ và JDK hiện đại.

## 1. Bản đồ API theo mục đích

| Thông tin muốn đọc | API | Ý nghĩa |
| --- | --- | --- |
| Các tham số của method/constructor | `Executable.getParameters()` | Mảng các `Parameter` |
| Số tham số | `Executable.getParameterCount()` | Số phần tử trong chữ ký phản chiếu |
| Kiểu runtime | `Parameter.getType()` | `Class<?>` sau erasure |
| Kiểu generic được khai báo | `Parameter.getParameterizedType()` | `Type`, giữ thông tin generic khả dụng |
| Annotation trên *khai báo tham số* | `Parameter.getAnnotation(...)` | Annotation với target `PARAMETER` |
| Annotation trên *kiểu của tham số* | `Parameter.getAnnotatedType()` | `AnnotatedType` và các node lồng nhau |
| Tên tham số | `Parameter.getName()` và `isNamePresent()` | Phụ thuộc metadata build |
| Chữ ký generic theo method | `Executable.getGenericParameterTypes()` | `Type[]` |
| Kiểu có annotation theo method | `Executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` |
| Annotation declarations theo method | `Executable.getParameterAnnotations()` | Mảng hai chiều `Annotation[][]` |

Điều quan trọng nhất: `getType()`, `getParameterizedType()` và `getAnnotatedType()` không phải ba cách viết khác nhau cho cùng một giá trị. Chúng trả lời ba câu hỏi riêng.

### Ví dụ định hướng

```java
void save(
        @InputName("customers")
        List<@TypeTag("element") String> customers) {}
```

Đây là **đoạn minh họa**, giả định `@InputName` target `PARAMETER` và `@TypeTag` target `TYPE_USE`, đều có retention `RUNTIME`.

- `getType()` của tham số trả `List.class`.
- `getParameterizedType()` mô tả `List<String>`.
- `getAnnotation(InputName.class)` đọc metadata `customers` từ declaration.
- `getAnnotatedType()` có thể dẫn đến `@TypeTag` trên **String** nằm trong `List`.
- `getName()` phản ánh tên source `customers` chỉ khi compiler đã lưu thông tin tên thích hợp.

## 2. Chọn đúng Method hoặc Constructor

Dùng erased parameter classes để tìm một overload cụ thể:

```java
Method method = Service.class.getDeclaredMethod(
        "save", List.class, int.class);

Parameter[] params = method.getParameters();
```

Đây là **đoạn minh họa**, cần import `java.lang.reflect.Method`, `Parameter` và class `Service` có chữ ký phù hợp. Nếu source khai báo `save(List<String>, int)`, reflection tra cứu bằng `List.class`, không phải `List<String>.class` vì Java không có class literal cho một parameterized type đầy đủ.

- `getDeclaredMethod` tìm method khai báo trực tiếp tại class/interface, kể cả non-public, nhưng không tự truy tìm methods kế thừa.
- `getMethod` tìm public method phù hợp, có thể gồm public methods được kế thừa.
- `getDeclaredMethods()` không bảo đảm thứ tự của mảng kết quả: **không chọn overload bằng index tùy ý**.

Với constructor:

```java
Constructor<?> constructor =
        Service.class.getDeclaredConstructor(String.class);
Parameter[] ctorParams = constructor.getParameters();
```

Đây là đoạn minh họa cần `java.lang.reflect.Constructor` và constructor thực sự tồn tại. `Method` và `Constructor` đều mở rộng `Executable`, nên có nhiều API metadata giống nhau.

## 3. getType(): erasure là gì?

Giả sử:

```java
void collect(List<String> names, Map<String, Integer> values) {}
```

`getType()` lần lượt trả `List.class` và `Map.class`. Java generic chủ yếu được kiểm tra lúc biên dịch; không tồn tại một runtime class riêng cho `List<String>` khác với `List<Integer>`.

| Khai báo | `getType()` |
| --- | --- |
| `String text` | `String.class` |
| `int count` | `int.class` |
| `List<String> list` | `List.class` |
| `Map<String,Integer> map` | `Map.class` |
| `String[] tags` | `String[].class` |
| `T value`, với `T extends Number` | `Number.class` |
| `T value`, không có bound tường minh | `Object.class` |

Dùng `getType()` để xây lookup signature hay kiểm tra raw class là phù hợp. Nhưng nếu cần biết phần tử `List` là `String`, đừng chỉ xét `getType() == List.class`. Hãy đọc chữ ký generic.

## 4. getParameterizedType(): cấu trúc Type

`Parameter.getParameterizedType()` trả một `java.lang.reflect.Type`. Để kiểm tra `List<String>`:

```java
Type type = parameter.getParameterizedType();
if (type instanceof ParameterizedType p) {
    Type raw = p.getRawType();
    Type[] args = p.getActualTypeArguments();
}
```

Đây là đoạn minh họa cần import `Type`, `ParameterizedType`. Pattern matching for `instanceof` được hỗ trợ ổn định từ Java 16. Khi `type` là `List<String>`, `raw` biểu diễn `List` và `args[0]` là `String.class`.

### Những dạng Type phải xử lý

| Loại | Ví dụ khai báo | API cần biết |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, raw `List` | `Class` |
| `ParameterizedType` | `List<String>` | `getRawType`, `getActualTypeArguments` |
| `TypeVariable` | `T` trong `<T extends Number>` | `getName`, `getBounds` |
| `WildcardType` | `? extends Number`, `? super Integer` | `getUpperBounds`, `getLowerBounds` |
| `GenericArrayType` | `T[]` | `getGenericComponentType` |

Ví dụ `Map<String,List<Integer>>` có type arguments `String` và `List<Integer>`; type argument thứ hai lại là `ParameterizedType`. Muốn tới `Integer`, phải đi qua **hai tầng**.

### Wildcard

```java
void process(List<? extends Number> input) {}
```

Type argument của `List` là `WildcardType`; upper bound `Number` được lấy qua `getUpperBounds()`. Với `? super Integer`, lower bound chứa `Integer`. Không được xem wildcard là class cụ thể của từng phần tử runtime.

### TypeVariable và multiple bounds

```java
static <T extends Number & Comparable<T>>
void compare(T input) {}
```

`getParameterizedType()` của `input` biểu diễn type variable `T`; `getType()` là `Number.class` vì erasure dùng bound đầu tiên. `getBounds()` mô tả `Number` cùng `Comparable<T>`. Reflection đọc **khai báo**, không biết một lời gọi riêng đã suy luận `T=Integer` hay không.

### GenericArrayType

```java
static <T> void load(T[] items) {}
```

Generic type của `items` có thể là `GenericArrayType`, trong khi erased runtime type là `Object[].class`. Không ép mọi `Type` về `Class` hoặc `ParameterizedType`: cả hai kiểu cast đó đều có thể gây `ClassCastException`.

## 5. @Target(PARAMETER): annotation của declaration

Một annotation mô tả **tham số trong hợp đồng API**:

```java
import java.lang.annotation.*;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface InputName {
    String value();
}
```

Dùng:

```java
void register(@InputName("customer-id") String id) {}
```

Để đọc, lấy `Parameter` tương ứng rồi gọi:

```java
InputName info = parameter.getAnnotation(InputName.class);
System.out.println(info.value()); // customer-id
```

Các đoạn trên là minh họa cần cùng scope. `@InputName` chỉ có target `PARAMETER` nên không thể đặt nó trên `String` **bên trong** `List<String>`; muốn annotate một type argument, cần một annotation được phép dùng với `TYPE_USE`.

`Parameter.getAnnotations()` trả declaration annotations mà runtime reflection có thể thấy. Nếu một annotation type là repeatable, dùng `getAnnotationsByType(MyAnnotation.class)` để không bỏ sót nhiều entries được lưu qua container.

## 6. @Target(TYPE_USE): annotation của kiểu

Type-use annotation có thể đặt trên nhiều node của một kiểu, kể cả phần tử generic hoặc chiều mảng:

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface TypeTag {
    String value();
}
```

Các vị trí khác nhau:

```java
void inspect(
        @TypeTag("top") String title,
        List<@TypeTag("element") String> names,
        List<? extends @TypeTag("bound") Number> amounts,
        String @TypeTag("array") [] tags) {}
```

Đây là khai báo minh họa cần `List`. Bốn `@TypeTag` có ý nghĩa vị trí khác nhau:

1. `top` thuộc kiểu `String` của `title`.
2. `element` thuộc type argument `String` của `List`.
3. `bound` thuộc `Number` trong upper bound của wildcard.
4. `array` thuộc array level `String[]`.

Đừng gọi `Parameter.getAnnotations()` rồi kết luận những type-use annotations không tồn tại. Hãy đi qua `getAnnotatedType()`. Nếu annotation chỉ target `TYPE_USE`, `parameter.getAnnotation(TypeTag.class)` trên **declaration** thường trả `null`, kể cả khi `parameter.getAnnotatedType().getAnnotation(TypeTag.class)` trả về một annotation ở top-level type.

## 7. Đọc generic annotation bằng AnnotatedParameterizedType

Với `List<@TypeTag("element") String>`:

```java
AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) parameter.getAnnotatedType();

AnnotatedType elementType =
        listType.getAnnotatedActualTypeArguments()[0];

TypeTag tag = elementType.getAnnotation(TypeTag.class);
System.out.println(tag.value()); // element
```

Đây là đoạn minh họa với `Parameter` của chữ ký phù hợp, cần imports từ `java.lang.reflect`.

- `getAnnotatedType()` ở node `List` chưa chắc có annotation nào **trực tiếp**.
- `getAnnotatedActualTypeArguments()[0]` là node `String` đã được annotate.
- `elementType.getType()` có thể cho `String.class`, còn `getAnnotation` truy vấn annotation ở node đó.

**Không làm phẳng cây metadata:** `@Tag List<String>` khác `List<@Tag String>`. Framework validation có thể dùng annotation trên collection và phần tử cho hai chính sách khác nhau.

### Generic lồng nhau

```java
void update(Map<String, List<@TypeTag("inner") Integer>> values) {}
```

Đây là minh họa cần `Map` và `List`. Đường đi:

```text
Map<String, List<@TypeTag Integer>>
  -> argument[1]: List<@TypeTag Integer>
      -> argument[0]: @TypeTag Integer
```

Mã truy cập:

```java
AnnotatedParameterizedType mapType =
        (AnnotatedParameterizedType) parameter.getAnnotatedType();
AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType)
                mapType.getAnnotatedActualTypeArguments()[1];
TypeTag inner = listType.getAnnotatedActualTypeArguments()[0]
        .getAnnotation(TypeTag.class);
```

Đây là đoạn minh họa; `inner.value()` là `"inner"`. Dùng interface phản chiếu có cấu trúc, không tách chuỗi `getTypeName()` bằng dấu phẩy hoặc dấu ngoặc nhọn.

## 8. Wildcard bounds và annotated arrays

### Annotation trên upper bound

```java
void scores(List<? extends @TypeTag("upper") Number> values) {}
```

Để tới node `Number`:

```java
AnnotatedParameterizedType outer =
        (AnnotatedParameterizedType) parameter.getAnnotatedType();
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
                outer.getAnnotatedActualTypeArguments()[0];
AnnotatedType upper = wildcard.getAnnotatedUpperBounds()[0];
TypeTag tag = upper.getAnnotation(TypeTag.class);
```

Đoạn minh họa này dùng `java.lang.reflect.AnnotatedWildcardType`. `tag.value()` là `"upper"`. Với `? super @TypeTag("lower") Integer`, truy cập lower bound bằng `getAnnotatedLowerBounds()`. Đừng nhầm wildcard bound với type-variable bound (`<T extends Number>`); chúng có cấu trúc reflection khác nhau.

### Annotation trên chiều mảng

```java
void send(String @TypeTag("array") [] names) {}
```

Để đọc:

```java
AnnotatedArrayType arrayType =
        (AnnotatedArrayType) parameter.getAnnotatedType();
TypeTag tag = arrayType.getAnnotation(TypeTag.class);
```

Đây là đoạn minh họa, cần `java.lang.reflect.AnnotatedArrayType`. Nếu annotation đặt trên **component String**, dùng `arrayType.getAnnotatedGenericComponentType()` rồi truy vấn annotation ở component. Với mảng nhiều chiều, cần duyệt từng cấp.

`AnnotatedArrayType` khác `GenericArrayType`: loại thứ nhất cho biết annotation trên cây array type; loại thứ hai thuộc hệ `Type` và mô tả generic component.

## 9. Đọc annotated bounds của type variable

Ví dụ generic method:

```java
static <T extends @TypeTag("numeric") Number & Comparable<T>>
void evaluate(T input) {}
```

`@TypeTag("numeric")` nằm trên **bound Number**. Để đọc:

```java
TypeVariable<?> variable = (TypeVariable<?>)
        parameter.getParameterizedType();
AnnotatedType bound = variable.getAnnotatedBounds()[0];
TypeTag tag = bound.getAnnotation(TypeTag.class);
```

Đây là đoạn minh họa. `tag.value()` là `"numeric"`. `getType()` của `input` là `Number.class` sau erasure; `getParameterizedType()` vẫn là `TypeVariable` tên `T`.

Với bound `Comparable<T>`, `getAnnotatedBounds()[1]` là một node kiểu được tham số hóa, có thể duyệt tiếp các actual type arguments nếu cần. Một type variable có thể có bound đệ quy như `T extends Comparable<T>`; trình duyệt metadata tổng quát nên ghi nhớ node đã xem hoặc giới hạn độ sâu để tránh đi vòng.

## 10. Retention: vì sao annotation không xuất hiện?

| Retention policy | Có trong source | Có trong class file | Core reflection đọc? |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không | Không |
| `CLASS` | Có | Có | Không |
| `RUNTIME` | Có | Có | Có, khi API hỗ trợ vị trí |

Nếu **không có `@Retention`**, annotation mặc định là `RetentionPolicy.CLASS`. Vì vậy, một annotation `@Target(TYPE_USE)` đơn thuần chưa đủ để đọc bằng `getAnnotatedType().getAnnotation(...)` ở runtime.

`SOURCE` vẫn có thể được xử lý trong lúc compile bằng annotation processor/source analyzer. `CLASS` có thể được công cụ bytecode đọc từ `.class`. `RUNTIME` cho phép Java core reflection truy vấn những vị trí hỗ trợ; nhưng **không tự thực hiện validation** hoặc cho phép reflection đọc mọi local-variable annotation trong body method.

Ví dụ Java SE không tự biến `@NonNull` do người dùng đặt thành kiểm tra cấm null. Muốn có hiệu lực, cần checker/framework hoặc code validation được cấu hình rõ.

## 11. Tên tham số và javac -parameters

Tên source `customerId` chỉ được phản chiếu ổn định khi compiler lưu metadata tham số phù hợp. Dùng:

```bash
javac -parameters ParameterMetadataDemo.java
```

`Parameter.isNamePresent()` cho biết tên thật có được ghi hay không; nếu thiếu, `getName()` có thể trả tên tổng hợp như `arg0`. Đừng dùng `arg0` làm khóa JSON/HTTP hoặc phụ thuộc tên tham số khi chưa kiểm tra build.

`-parameters` **không** điều khiển generic type erasure hay retention của annotations. Tương tự, `javac -g` dành cho debugging information, không thay thế trực tiếp hợp đồng `-parameters` đối với `java.lang.reflect.Parameter`.

Một framework cần tên logic ổn định có thể ưu tiên explicit annotation `@InputName("customer-id")`, rồi chỉ fallback sang source parameter name nếu `isNamePresent()` là `true`.

### Tham số do compiler tạo

`Parameter` cung cấp `isImplicit()`, `isSynthetic()`, `isVarArgs()` và `getModifiers()`. Một số constructors của inner classes hoặc mã compiler-generated có tham số không tương ứng đơn giản với source parameters mà người lập trình nhìn thấy. Đừng luôn giả định index 0 là tham số nghiệp vụ đầu tiên trong mọi constructor.

## 12. Method overrides không tự kế thừa parameter annotations

Ví dụ method cha có `@InputName` trên một parameter nhưng class con override method mà không đặt lại annotation. Java không có cơ chế mặc định tự truyền parameter annotation của method cha sang parameter của override.

Đối với framework cần inheritance của metadata, hãy định nghĩa chính sách tường minh: ưu tiên declaration tại subclass hay tìm từ superclass/interfaces, cách gộp nhiều annotation, xử lý conflicts. Không nhầm `@Inherited` với khả năng parameter annotations tự đi qua method override; `@Inherited` chủ yếu liên quan annotation trên class.

## 13. Chương trình Java 17+ hoàn chỉnh

Chương trình này tự khai báo annotations và methods, rồi đọc các vị trí:

- `@ParamLabel` trên parameter declaration;
- `@TypeTag` trên generic argument, wildcard upper bound, array level và top-level parameter type;
- `@ClassOnly` có retention `CLASS`;
- tên tham số lưu bởi `-parameters`;
- generic method `T extends Number & Comparable<T>` cùng annotated bound.

Lưu thành **ParameterMetadataDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class ParameterMetadataDemo {

    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.RUNTIME)
    @interface ParamLabel {
        String value();
    }

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface TypeTag {
        String value();
    }

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.CLASS)
    @interface ClassOnly {}

    static void inspect(
            @ParamLabel("names")
            List<@TypeTag("element") String> names,
            List<? extends @TypeTag("upper") Number> numbers,
            String @TypeTag("array") [] tags,
            @TypeTag("title") String title,
            @ClassOnly String hidden) {}

    static <T extends @TypeTag("numeric") Number & Comparable<T>>
    void constrained(T item) {}

    public static void main(String[] args) throws Exception {
        Method method = ParameterMetadataDemo.class.getDeclaredMethod(
                "inspect", List.class, List.class, String[].class,
                String.class, String.class);

        Parameter[] parameters = method.getParameters();
        System.out.println("count=" + parameters.length);
        System.out.println("name=" + parameters[0].getName());
        System.out.println("namePresent=" +
                parameters[0].isNamePresent());
        System.out.println("erased=" +
                parameters[0].getType().getSimpleName());
        System.out.println("generic=" +
                parameters[0].getParameterizedType().getTypeName());
        System.out.println("declaration=" +
                parameters[0].getAnnotation(ParamLabel.class).value());

        AnnotatedParameterizedType first =
                (AnnotatedParameterizedType)
                        parameters[0].getAnnotatedType();
        System.out.println("argument=" +
                first.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeTag.class).value());

        AnnotatedParameterizedType second =
                (AnnotatedParameterizedType)
                        parameters[1].getAnnotatedType();
        AnnotatedWildcardType wildcard =
                (AnnotatedWildcardType)
                        second.getAnnotatedActualTypeArguments()[0];
        System.out.println("upper=" +
                wildcard.getAnnotatedUpperBounds()[0]
                        .getAnnotation(TypeTag.class).value());

        AnnotatedArrayType array =
                (AnnotatedArrayType) parameters[2].getAnnotatedType();
        System.out.println("array=" +
                array.getAnnotation(TypeTag.class).value());

        AnnotatedType title = parameters[3].getAnnotatedType();
        System.out.println("top=" +
                title.getAnnotation(TypeTag.class).value());
        System.out.println("typeUseOnDeclaration=" +
                (parameters[3].getAnnotation(TypeTag.class) != null));
        System.out.println("classPolicyVisible=" +
                (parameters[4].getAnnotatedType()
                        .getAnnotation(ClassOnly.class) != null));

        Method constrained =
                ParameterMetadataDemo.class.getDeclaredMethod(
                        "constrained", Number.class);
        Parameter genericParameter = constrained.getParameters()[0];
        TypeVariable<?> variable = (TypeVariable<?>)
                genericParameter.getParameterizedType();
        System.out.println("variable=" + variable.getName());
        System.out.println("variableErasure=" +
                genericParameter.getType().getSimpleName());
        System.out.println("variableBound=" +
                variable.getAnnotatedBounds()[0]
                        .getAnnotation(TypeTag.class).value());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -parameters ParameterMetadataDemo.java
java ParameterMetadataDemo
```

**Stdout khi thực hiện đúng lệnh trên:**

```text
count=5
name=names
namePresent=true
erased=List
generic=java.util.List<java.lang.String>
declaration=names
argument=element
upper=upper
array=array
top=title
typeUseOnDeclaration=false
classPolicyVisible=false
variable=T
variableErasure=Number
variableBound=numeric
```

Giải thích: `List.class` là erasure, nhưng `getParameterizedType()` vẫn giữ `List<String>`. `@ParamLabel` trên declaration được lấy bằng `Parameter.getAnnotation`; các `@TypeTag` nằm ở những node khác nhau của cây `AnnotatedType`. Annotation retention `CLASS` không có trong Java core reflection. Với method generic, `getParameterizedType()` trả `TypeVariable` tên `T`, còn `getType()` là erasure `Number.class`. Hai dòng về `name` dựa vào cờ `-parameters`; nếu bỏ cờ, kết quả không được bảo đảm giống như trên.

## 14. Thiết kế bộ đọc metadata tổng quát

Khi không biết trước kiểu tham số, nên có một tầng traversal thay vì ép kiểu cố định:

```java
static String kind(java.lang.reflect.Type type) {
    if (type instanceof Class<?>) return "Class";
    if (type instanceof java.lang.reflect.ParameterizedType)
        return "ParameterizedType";
    if (type instanceof java.lang.reflect.TypeVariable<?>)
        return "TypeVariable";
    if (type instanceof java.lang.reflect.WildcardType)
        return "WildcardType";
    if (type instanceof java.lang.reflect.GenericArrayType)
        return "GenericArrayType";
    return "Unknown";
}
```

Đây là **phương thức minh họa**. Đối với metadata annotation, viết nhánh riêng cho `AnnotatedParameterizedType`, `AnnotatedWildcardType`, `AnnotatedArrayType` và `AnnotatedTypeVariable`; đi qua các children thay vì đếm annotations trên node cha. Cần bảo vệ khỏi recursive bounds như `T extends Comparable<T>`.

Trong schema framework, nên tách thành ba tầng: **khai báo metadata** (reflection), **giải nghĩa domain** (quy tắc và lỗi), và **thực thi** (validation hoặc mapping). Annotation không tự thực thi chính sách chỉ vì có tên `NotNull` hoặc `Range`.

### Generic signature có thể lỗi ở class từ bên ngoài

Khi làm việc với class files không đồng nhất, reflection của chữ ký generic có thể gặp `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` nếu metadata không hợp lệ hoặc type thiếu. Công cụ nên báo lỗi đúng ngữ cảnh method, parameter index và chữ ký gốc, thay vì coi mọi lỗi là dữ liệu ứng dụng sai.

## 15. Những sai lầm thường gặp

| Nhận định/cách làm | Vấn đề | Cách sửa |
| --- | --- | --- |
| `getType()` cho ra `List<String>` | Chỉ trả raw/erased `List` | `getParameterizedType()` |
| Cast mọi `Type` thành `Class` | TypeVariable, wildcard, generic array không phải Class | Kiểm tra `instanceof` |
| `getAnnotations()` tìm được `List<@Tag String>` | Annotation ở type argument, không ở declaration | Duyệt `getAnnotatedType()` |
| Không dùng `@Retention` mà muốn reflect | Mặc định `CLASS` | Chọn `RUNTIME` khi cần |
| `-parameters` tự giữ annotation runtime | Tên và retention là hai cơ chế khác nhau | Cấu hình từng cơ chế |
| `-g` giống `-parameters` | Debug info không bảo đảm `Parameter.getName` | Dùng `-parameters` |
| Lấy overload theo index từ `getDeclaredMethods()` | Thứ tự không được bảo đảm | Chọn name + erased signature |
| Runtime biết generic `T` của mọi lời gọi | Erasure không lưu mỗi type argument invocation | Đọc bounds và hợp đồng khai báo |
| Annotation trên method cha tự đến parameter override | Không có inheritance mặc định như vậy | Chính sách hierarchy tường minh |
| `TYPE_USE` annotation chỉ có ở node cha | Metadata có thể nằm trong generic, wildcard, array | Duyệt từng level |
| Annotation `RUNTIME` tự kiểm tra hợp lệ | Annotation chỉ là metadata | Dùng checker/validator riêng |

## 16. Checklist khi dùng trong framework

1. Đã tìm đúng `Executable` và overload bằng erased signature chưa?
2. `getParameterCount()` có bao gồm tham số implicit/synthetic cần xử lý không?
3. Có cần tên tham số thật? Nếu có, build bật `-parameters` và `isNamePresent()` đúng không?
4. `Type` hiện tại là `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` hay `GenericArrayType`?
5. Có duyệt đủ type arguments của generic lồng nhau không?
6. Đã phân biệt `PARAMETER` declaration annotation với `TYPE_USE` annotation chưa?
7. Với `AnnotatedType`, annotation gắn ở top-level, element, wildcard bound hay array level?
8. Retention có là `RUNTIME` nếu công cụ đọc qua reflection không?
9. Có xử lý multiple bounds và recursion của type variable không?
10. Framework có định nghĩa rõ ý nghĩa/validation của annotation và cách báo lỗi không?
11. Có test cùng một phương thức khi bật và tắt `-parameters`?
12. Có test metadata generic, wildcard, array và một annotation `CLASS` không hiện qua reflection không?

## 17. Bài tập và đáp án định hướng

**Bài 1.** Tham số `Map<String,Integer>`: `getType()` và `getParameterizedType()` khác gì? **Đáp án:** `Map.class` so với `ParameterizedType` có hai type arguments.

**Bài 2.** Với `List<@TypeTag String>`, API nào lấy annotation trên `String`? **Đáp án:** `getAnnotatedType()` → `AnnotatedParameterizedType` → argument index 0 → `getAnnotation`.

**Bài 3.** Với `List<? extends @TypeTag Number>`, annotation nằm trên wildcard hay upper bound? **Đáp án:** trên `Number` trong upper bound; dùng `getAnnotatedUpperBounds()`.

**Bài 4.** Với `String @TypeTag []` và `@TypeTag String[]`, đường truy vấn có giống nhau không? **Đáp án:** không; xem array level và component level trong `AnnotatedArrayType`.

**Bài 5.** Với `<T extends Number & Comparable<T>> void use(T value)`, `getType()` là gì? **Đáp án:** `Number.class` do erasure của bound đầu tiên, trong khi generic view vẫn là `TypeVariable` `T`.

**Bài 6.** Nếu `getName()` in `arg0`, có nên dùng nó làm tên JSON field không? **Đáp án:** không; kiểm tra `isNamePresent()` hoặc khai báo metadata tên logic rõ ràng.

**Bài 7.** Vì sao annotation `@Retention(CLASS)` có thể xuất hiện trong class file nhưng `getAnnotation` trả `null`? **Đáp án:** core reflection chỉ truy xuất annotation retention `RUNTIME` tại các vị trí hỗ trợ.

**Bài 8.** Có thể khai báo hai overload `accept(List<String>)` và `accept(List<Integer>)` không? **Đáp án:** không, erasure khiến cả hai signature đều dùng `List`.

**Bài 9.** Một tool duyệt `T extends Comparable<T>` đệ quy không có visited set có thể gặp gì? **Đáp án:** lặp lại cấu trúc bound; cần theo dõi node hoặc giới hạn độ sâu.

## 18. Kết luận

Bốn khái niệm phải được giữ tách biệt:

- **Erasure:** `Parameter.getType()` trả `Class` runtime.
- **Generic declaration:** `Parameter.getParameterizedType()` trả cây `Type`.
- **Parameter declaration annotations:** `Parameter.getAnnotation(...)` đọc annotation của tham số.
- **Type-use annotations:** `Parameter.getAnnotatedType()` và các subtype của `AnnotatedType` đọc annotation trên kiểu, generic argument, wildcard bound và array level.

Tất cả là **metadata của khai báo**, không tự nói chính xác phần tử runtime của một collection có nguồn gốc không an toàn hay tự thực thi validation. Khi xây công cụ tổng quát, luôn kiểm tra loại node trước khi cast, giữ đúng vị trí annotation và viết test với các chữ ký phức tạp.

### Tham khảo API và đặc tả

- [Java SE 25: Parameter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Java SE 25: Executable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Executable.html)
- [Java SE 25: ParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 25: AnnotatedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 25: AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 25: AnnotatedWildcardType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [JLS `4.6: Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6)
- [JLS `9.7.4: Annotation locations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4)
