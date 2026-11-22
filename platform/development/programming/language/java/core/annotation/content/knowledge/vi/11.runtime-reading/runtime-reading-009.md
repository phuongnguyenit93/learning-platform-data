# Duyệt `AnnotatedParameterizedType`, `AnnotatedArrayType` và các kiểu liên quan bằng Reflection

Trong Java 8 trở lên, annotation không chỉ đặt trên **khai báo class, field hoặc method** mà còn có thể nằm ở **vị trí sử dụng kiểu** (*type use*): bên trong `List<...>`, trước một tầng mảng `[]`, trên wildcard `?`, trên giới hạn `extends`, hoặc trên chỗ sử dụng biến kiểu `T`. Khi cần đọc metadata ấy ở runtime, `Field.getAnnotations()` hoặc `Field.getGenericType()` là chưa đủ.

Java cung cấp họ interface `java.lang.reflect.AnnotatedType` để biểu diễn **cây kiểu cùng những annotation gắn lên từng nút**. Muốn đọc hết, ta phải bắt đầu từ nút gốc và đi xuống qua các nhánh như `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType` và `AnnotatedTypeVariable`.

Bài này tập trung vào cơ chế **duyệt cấu trúc `AnnotatedType` khi chạy**, phân biệt các lớp API, viết một bộ duyệt dùng được với Java 17+ và nhận biết những trường hợp dễ bỏ sót.

## 1. Vì sao phải duyệt cây kiểu?

Xét field:

```java
@Mark("collection") List<@Mark("item") String> names;
```

Field có kiểu `List<String>`, nhưng hai annotation có **vị trí khác nhau**:

- `@Mark("collection")` ở chính vị trí sử dụng kiểu `List<String>`.
- `@Mark("item")` ở vị trí sử dụng kiểu đối số `String` bên trong `List<...>`.

Gọi `field.getGenericType()` trả về thông tin kiểu generic (`Type`), nhưng **không cung cấp API để đọc các type annotation trên từng phần**. Gọi `field.getAnnotations()` thì nhắm vào **annotation trên khai báo field**, cũng không phải cách duyệt cây type-use annotation.

Cách thích hợp:

```java
AnnotatedType root = field.getAnnotatedType();
```

Từ `root`, kiểm tra nó có phải `AnnotatedParameterizedType` không, sau đó lấy các đối số annotated qua `getAnnotatedActualTypeArguments()`.

Tương tự:

```java
String @Mark("outer") [] @Mark("inner") [] grid;
```

Hai annotation đứng trước hai cặp `[]` thuộc **hai tầng mảng riêng**, nên cần hai lần đi xuống theo `AnnotatedArrayType.getAnnotatedGenericComponentType()` để khám phá cấu trúc. Một `AnnotatedType` đơn lẻ không tự phẳng hóa toàn bộ annotation ở các tầng con.

## 2. Khung API `AnnotatedType`

Mọi đối tượng trong họ này đều thực thi `java.lang.reflect.AnnotatedType`, và `AnnotatedType` kế thừa `AnnotatedElement`.

| API | Công dụng |
| --- | --- |
| `getType()` | Trả về `Type` cơ sở của nút (`Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType` tùy trường hợp). |
| `getAnnotation(Mark.class)` | Lấy một annotation kiểu `Mark` **gắn ở chính nút hiện tại** nếu có. |
| `getAnnotations()` / `getDeclaredAnnotations()` | Liệt kê annotation hiện diện trên nút kiểu đang xét, không tự đi vào các đối số generic hay component của mảng. |
| `getAnnotationsByType(...)` | Hữu ích nếu type annotation hỗ trợ `@Repeatable`; có thể trả về các lần áp dụng qua container. |
| `getAnnotatedOwnerType()` | Với kiểu thành viên/lồng nhau, cho biết kiểu chủ (*owner type*) được annotate khi có; nhiều dạng kiểu khác trả `null`. |

`AnnotatedType` là **giao diện**. Tên kiểu generic, mảng hay wildcard thực tế quyết định interface con cần dùng để đi tới các nút tiếp theo:

```text
AnnotatedType (nút hiện tại)
├─ AnnotatedParameterizedType
│    └─ getAnnotatedActualTypeArguments() → từng AnnotatedType
├─ AnnotatedArrayType
│    └─ getAnnotatedGenericComponentType() → AnnotatedType thành phần
├─ AnnotatedWildcardType
│    ├─ getAnnotatedUpperBounds() → AnnotatedType[]
│    └─ getAnnotatedLowerBounds() → AnnotatedType[]
└─ AnnotatedTypeVariable
     └─ getAnnotatedBounds() → AnnotatedType[]
```

Một nút kiểu thường như `String`, `int` hoặc `Number` có thể chỉ cần đọc annotation trên chính nút mà **không có nhánh con** tương ứng trong bốn interface trên.

## 3. Lấy nút gốc từ Reflection

Tùy đối tượng Java muốn đọc, điểm vào là một API khác nhau:

| Nguồn metadata | API lấy kiểu có annotation |
| --- | --- |
| Kiểu của field | `Field.getAnnotatedType()` |
| Kiểu trả về của method | `Method.getAnnotatedReturnType()` |
| Kiểu tham số method hoặc constructor | `Executable.getAnnotatedParameterTypes()` |
| Kiểu ngoại lệ của method/constructor | `Executable.getAnnotatedExceptionTypes()` |
| Receiver type (nếu có) | `Executable.getAnnotatedReceiverType()` |
| Superclass được khai báo của class | `Class.getAnnotatedSuperclass()` |
| Các interface được triển khai | `Class.getAnnotatedInterfaces()` |
| Các giới hạn của một type variable | `TypeVariable.getAnnotatedBounds()` |

Các API trên cung cấp **điểm bắt đầu**, sau đó ta duyệt các nhánh trên `AnnotatedType` theo kiểu thực tế. Một constructor thông thường **không có kiểu trả về**, nên không thể xử lý nó giống `Method.getAnnotatedReturnType()`.

Với tham số method, thứ tự của `getAnnotatedParameterTypes()` tương ứng thứ tự các kiểu tham số. Dù tham số có tên hay không, vẫn có thể đọc type annotation theo vị trí. Muốn metadata type-use tồn tại ở runtime, annotation phải có retention phù hợp, thường là `@Retention(RetentionPolicy.RUNTIME)`.

## 4. `AnnotatedParameterizedType`: đi vào đối số generic

Ví dụ:

```java
List<@Mark("item") String> names;
Map<@Mark("key") String, List<@Mark("value") Integer>> lookup;
```

Một kiểu generic như `Map<String, List<Integer>>` có **cấu trúc lồng nhau**:

```text
Map<String, List<Integer>>
  ├─ đối số 0: String
  └─ đối số 1: List<Integer>
       └─ đối số 0: Integer
```

`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` trả về các `AnnotatedType` ở từng đối số. Ta phải duyệt **đệ quy**, vì một đối số có thể lại là `AnnotatedParameterizedType`, `AnnotatedArrayType`, wildcard hoặc biến kiểu.

Mẫu code minh họa, giả sử `type` đã được xác định:

```java
if (type instanceof AnnotatedParameterizedType parameterized) {
    AnnotatedType[] args =
            parameterized.getAnnotatedActualTypeArguments();

    for (int i = 0; i < args.length; i++) {
        visit(args[i], path + ".arg" + i);
    }
}
```

Khác biệt giữa hai API:

- `((ParameterizedType) field.getGenericType()).getActualTypeArguments()` cho `Type[]` thông thường.
- `((AnnotatedParameterizedType) field.getAnnotatedType()).getAnnotatedActualTypeArguments()` cho `AnnotatedType[]` **giữ được metadata type-use**.

Không nên cast tùy ý: `List` raw không có đối số kiểu cụ thể để đi xuống như `List<String>`, và `field.getAnnotatedType()` không bắt buộc là `AnnotatedParameterizedType`. Mỗi nhánh phải được nhận diện bằng `instanceof`.

## 5. `AnnotatedArrayType`: đi qua từng chiều mảng

Xét khai báo:

```java
@Mark("element") String @Mark("outer") [] @Mark("inner") [] grid;
```

Đây là mảng hai chiều. Từ gốc đến lá:

```text
String[][]          annotation: outer
  └─ String[]       annotation: inner
       └─ String    annotation: element
```

`AnnotatedArrayType.getAnnotatedGenericComponentType()` đi từ kiểu **mảng hiện tại** sang **kiểu thành phần trực tiếp**, tức bỏ một tầng `[]`. Vì vậy phải gọi tiếp khi component vẫn là `AnnotatedArrayType`:

```java
AnnotatedType root = field.getAnnotatedType();

AnnotatedType inner =
        ((AnnotatedArrayType) root).getAnnotatedGenericComponentType();

AnnotatedType element =
        ((AnnotatedArrayType) inner).getAnnotatedGenericComponentType();
```

Không được coi `getAnnotatedGenericComponentType()` là API trả ngay kiểu phần tử cuối cùng của mọi mảng. Với mảng ba chiều, sẽ có ba tầng `AnnotatedArrayType` trước khi đến phần tử không phải mảng.

Mảng chứa generic cũng hợp lệ khi khai báo reference, chẳng hạn `List<@Mark("arg") String> @Mark("array") [] values;`. Khi duyệt, nhánh gốc là `AnnotatedArrayType`, nhưng component bên trong là `AnnotatedParameterizedType`. Đây là lý do bộ duyệt phải xử lý **kết hợp nhiều interface**, không thể chỉ kiểm tra tên kiểu gốc một lần.

## 6. `AnnotatedWildcardType`: duyệt `? extends` và `? super`

Wildcard là đối số generic có cú pháp `?`, thường dùng với upper bound hoặc lower bound:

```java
List<@Mark("wild") ? extends @Mark("upper") Number> upperNumbers;
List<@Mark("wild") ? super @Mark("lower") Integer> lowerNumbers;
```

Khi truy cập đối số kiểu số 0 của `List`, nút đó có thể là `AnnotatedWildcardType`.

- `getAnnotatedUpperBounds()` trả về các upper bound có thể mang annotation. Với `? extends Number`, đó là `Number`.
- `getAnnotatedLowerBounds()` trả về các lower bound; với `? super Integer`, đó là `Integer`.
- Khi **không viết upper bound rõ ràng**, wildcard có upper bound mặc định là `Object` không được annotate. Do vậy với `? super Integer`, thường có thể thấy upper bound `Object` và lower bound `Integer`.
- Với wildcard không bị ràng buộc `?`, lower bound là mảng rỗng và upper bound mặc định là `Object`.

Không phải annotation trên chính dấu `?` cũng là annotation trên `Number` hoặc `Integer`. Đó là các nút riêng; muốn thấy đủ phải đọc annotation của wildcard và **duyệt tiếp bound**.

```java
if (type instanceof AnnotatedWildcardType wildcard) {
    AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
    AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();

    for (int i = 0; i < upper.length; i++) {
        visit(upper[i], path + ".upper" + i);
    }
    for (int i = 0; i < lower.length; i++) {
        visit(lower[i], path + ".lower" + i);
    }
}
```

## 7. `AnnotatedTypeVariable`: phân biệt lần sử dụng `T` và giới hạn của `T`

Một type variable như `T` được khai báo trong class hoặc method. Nó cũng có thể được annotate ở **nơi sử dụng kiểu**:

```java
class Box<T extends @Mark("bound") Number> {
    @Mark("use") T item;
}
```

Ở đây:

- `@Mark("use")` đánh dấu **nút `T` tại field `item`**.
- `@Mark("bound")` đánh dấu **kiểu `Number`** trong giới hạn khai báo `T extends Number`.
- `Field.getAnnotatedType()` của `item` có thể là `AnnotatedTypeVariable`. Gọi `getAnnotation(Mark.class)` trên nút đó đọc marker ở nơi dùng `T`; gọi `getAnnotatedBounds()` đi xuống các bound của biến kiểu.
- Có thể lấy trực tiếp giới hạn từ khai báo type parameter qua `Box.class.getTypeParameters()[0].getAnnotatedBounds()`.

Không được suy rằng annotation trên **lần sử dụng `T`** sẽ tự động xuất hiện trên **khai báo tham số kiểu `T`**, hoặc ngược lại. Các vị trí sử dụng và khai báo này có ý nghĩa riêng.

Một biến kiểu không ghi bound rõ ràng có bound mặc định là `Object` không được annotate. Nếu có giao diện giao nhau, ví dụ `T extends Number & Comparable<T>`, `getAnnotatedBounds()` có thể trả **nhiều bound** theo thứ tự khai báo.

### Chú ý về recursion và chu trình

Bộ duyệt đệ quy có thể đi vô hạn nếu không có biện pháp phòng ngừa, ví dụ:

```java
class Recursive<T extends Comparable<T>> {
}
```

Khi đi theo bound của `T`, ta gặp `Comparable<T>`; đối số generic của nó lại là `T`, có thể dẫn về bound `Comparable<T>` một lần nữa.

Với công cụ tổng quát dùng trong production, nên theo dõi những **type variable/bound đang được duyệt trên nhánh hiện tại**, hoặc đặt giới hạn độ sâu phù hợp với trường hợp sử dụng và ghi nhận chu trình. Không dùng `getType().getTypeName()` làm khóa duy nhất cho mọi trường hợp, vì hai **lần sử dụng kiểu** có thể giống tên nhưng mang annotation khác nhau.

## 8. Chương trình Java 17+: duyệt đủ bốn dạng `AnnotatedType`

Ví dụ sau thực thi một hàm đệ quy `walk` với cấu trúc kiểu không tạo chu trình. Hàm in ra đường đi và nội dung `@Mark` ở **những nút thực sự được đánh dấu**; nó vẫn đi qua các nút không có annotation để tìm con.

Tạo file **`AnnotatedTypeWalkDemo.java`**:

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
import java.lang.reflect.Field;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

class Sample<T extends @Mark("bound") Number> {
    @Mark("list") List<@Mark("item") String> names;

    @Mark("cell")
    String @Mark("outer") [] @Mark("inner") [] grid;

    List<@Mark("wild") ? extends @Mark("upper") Number> maximums;

    List<@Mark("wildLower") ? super @Mark("lower") Integer> minimums;

    @Mark("useT") T current;
}

public class AnnotatedTypeWalkDemo {
    static void walk(AnnotatedType type, String path) {
        Mark mark = type.getAnnotation(Mark.class);
        if (mark != null) {
            System.out.println(path + "=" + mark.value());
        }

        if (type instanceof AnnotatedParameterizedType parameterized) {
            AnnotatedType[] args =
                    parameterized.getAnnotatedActualTypeArguments();
            for (int i = 0; i < args.length; i++) {
                walk(args[i], path + ".arg" + i);
            }
        } else if (type instanceof AnnotatedArrayType array) {
            walk(array.getAnnotatedGenericComponentType(),
                    path + ".component");
        } else if (type instanceof AnnotatedWildcardType wildcard) {
            AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
            AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();
            for (int i = 0; i < upper.length; i++) {
                walk(upper[i], path + ".upper" + i);
            }
            for (int i = 0; i < lower.length; i++) {
                walk(lower[i], path + ".lower" + i);
            }
        } else if (type instanceof AnnotatedTypeVariable variable) {
            AnnotatedType[] bounds = variable.getAnnotatedBounds();
            for (int i = 0; i < bounds.length; i++) {
                walk(bounds[i], path + ".bound" + i);
            }
        }
    }

    static void walkField(String fieldName) throws Exception {
        Field field = Sample.class.getDeclaredField(fieldName);
        walk(field.getAnnotatedType(), fieldName);
    }

    public static void main(String[] args) throws Exception {
        walkField("names");
        walkField("grid");
        walkField("maximums");
        walkField("minimums");
        walkField("current");

        TypeVariable<?> typeParameter = Sample.class.getTypeParameters()[0];
        walk(typeParameter.getAnnotatedBounds()[0], "T.declaredBound");
    }
}
```

Biên dịch và chạy từ thư mục chứa file với JDK 17 trở lên:

```bash
javac -encoding UTF-8 AnnotatedTypeWalkDemo.java
java AnnotatedTypeWalkDemo
```

**Stdout dự kiến:**

```text
names=list
names.arg0=item
grid=outer
grid.component=inner
grid.component.component=cell
maximums.arg0=wild
maximums.arg0.upper0=upper
minimums.arg0=wildLower
minimums.arg0.lower0=lower
current=useT
current.bound0=bound
T.declaredBound=bound
```

Phân tích output:

1. `names=list`: nút gốc `List<String>` mang `@Mark("list")`; `names.arg0=item`: đối số generic `String` mang `@Mark("item")`.
2. `grid=outer`: kiểu mảng ngoài cùng là nút gốc. Hai lần `.component` lần lượt đến mảng con có `"inner"` và kiểu phần tử có `"cell"`.
3. `maximums.arg0=wild`: kiểu đối số đầu tiên của `List` là wildcard được đánh dấu. `.upper0=upper` là `Number` của `? extends Number`.
4. `minimums.arg0=wildLower`: wildcard của `List` có lower bound `Integer` được đánh dấu `"lower"`. Upper bound mặc định `Object` không có `@Mark`, vì thế không có dòng cho nó.
5. `current=useT`: annotation nằm trên lần dùng biến kiểu `T`. `.bound0=bound` đến `Number` trong khai báo `T extends Number`.
6. `T.declaredBound=bound`: một cách khác đọc cùng bound trực tiếp từ đối tượng `TypeVariable` của khai báo class.

Hàm này cố tình **chỉ in các nút có `@Mark`**, nên các nút không được gắn annotation vẫn được duyệt nhưng không xuất hiện trong stdout. Nó không thêm bước phát hiện chu trình, vì kiểu `T extends Number` trong ví dụ không tạo recursion. Với code xử lý input tùy ý, hãy thêm bộ nhớ truy vết như giải thích ở mục 7.

## 9. Duyệt sâu hơn với generic lồng nhau và mảng generic

Ví dụ **minh họa cú pháp độc lập**, giả sử `@Mark` đã khai báo:

```java
class MoreSamples {
    java.util.Map<
        @Mark("key") String,
        java.util.List<@Mark("value") Integer>
    > index;

    java.util.List<@Mark("item") String>
        @Mark("array") [] batches;
}
```

Nếu duyệt field `index` bằng hàm `walk` ở mục 8, đường đi tới `@Mark("value")` là **`index.arg1.arg0`**. Phải đi qua đối số thứ hai của `Map`, rồi đối số thứ nhất của `List`; chỉ xem `Map` và một tầng con sẽ bỏ sót annotation ở `Integer`.

Với `batches`, nút gốc là `AnnotatedArrayType` (đánh dấu `"array"`). Component của mảng là `AnnotatedParameterizedType` đại diện `List<String>`, và đối số `String` mang `"item"`. Đường đi dự kiến:

```text
batches=array
batches.component.arg0=item
```

Điều này cho thấy một bộ duyệt nên kiểm tra **loại nút ở mỗi bước** rồi chuyển tiếp qua nhánh tương ứng; đừng dự đoán rằng cây bắt đầu bằng generic thì con luôn là generic, hoặc bắt đầu bằng array thì mọi con tiếp tục là array.

## 10. `getAnnotatedOwnerType()` và kiểu lồng nhau

Với một kiểu thành viên, Java còn cho phép metadata xuất hiện trên **kiểu owner** (kiểu bao ngoài). Ví dụ cấu trúc `Outer<T>.Inner<U>` có thể annotate owner `Outer<T>` lẫn `Inner<U>`.

Từ Java 9, `AnnotatedType.getAnnotatedOwnerType()` và các interface chuyên biệt hỗ trợ đọc kiểu owner được annotate khi tồn tại. Nó **khác** với:

- `getAnnotatedActualTypeArguments()`: đi vào `T`, `U` là các **đối số kiểu**.
- `getAnnotatedGenericComponentType()`: đi qua một tầng mảng.
- `getAnnotatedBounds()`: đi vào bound của wildcard hoặc type variable.

Với class/interface top-level, mảng, wildcard hoặc type variable, API owner thường trả `null`. Một bộ duyệt hỗ trợ kiểu lồng nhau có thể thêm:

```java
AnnotatedType owner = type.getAnnotatedOwnerType();
if (owner != null) {
    walk(owner, path + ".owner");
}
```

Đây là **đoạn bổ sung** cho hàm `walk` ở mục 8, không phải một chương trình độc lập. Chỉ dùng trên Java 9+ nếu muốn giữ khả năng tương thích. Vì cấu trúc owner có thể dẫn đến các type parameter lồng nhau, hãy duyệt theo nhánh có chiến lược chống chu trình khi xây dựng công cụ tổng quát.

## 11. Những giới hạn và lỗi dễ gặp

| Tình huống | Cách xử lý chính xác |
| --- | --- |
| Dùng `Field.getAnnotations()` rồi nghĩ đã đọc type argument annotation | Dùng `Field.getAnnotatedType()` và đi qua `AnnotatedParameterizedType`. |
| Dùng `Field.getGenericType()` rồi gọi `getAnnotation()` lên `Type` | `Type` là mô hình kiểu không mang giao diện `AnnotatedElement` chung; dùng `AnnotatedType` để đọc type-use annotation. |
| Ép mọi `AnnotatedType` sang `AnnotatedParameterizedType` | Kiểm tra `instanceof` tại mỗi nút vì con có thể là array, wildcard, type variable hoặc kiểu đơn giản. |
| Với `String[][]`, gọi một lần `getAnnotatedGenericComponentType()` rồi cho rằng đã đến `String` | Mới đến `String[]`; phải đi tiếp một tầng mảng nữa. |
| Chỉ duyệt upper bound của wildcard | Bỏ sót annotation trên `? super ...`; xét cả upper và lower bounds. |
| Chỉ xem `@Mark` trên `T` mà bỏ bound `T extends ...` | Nếu cần metadata bound, duyệt `AnnotatedTypeVariable.getAnnotatedBounds()` hoặc từ `TypeVariable.getAnnotatedBounds()`. |
| Duyệt bound của `T extends Comparable<T>` không giới hạn | Có thể tạo recursion vô hạn; cần cơ chế phát hiện chu trình. |
| Cho rằng annotation `SOURCE` xuất hiện qua Reflection | Để Reflection runtime đọc type annotation, phải có retention `RUNTIME`. |
| Annotation được khai báo chỉ với `@Target(FIELD)` rồi đặt trong `<...>` hoặc trước `[]` | Vị trí này cần `TYPE_USE`, không phải chỉ target trên khai báo field. |
| Diễn giải `getType()` trả về `Class<?>` ở mọi trường hợp | Nó trả về `Type`; có thể là `ParameterizedType`, `GenericArrayType`, `WildcardType` hay `TypeVariable`. |
| Xem việc annotation xuất hiện ở runtime là JVM tự kiểm tra nullness | Metadata chỉ là thông tin; cần công cụ/framework hiểu ý nghĩa và thực thi kiểm tra. |

### Những gì Reflection không bảo đảm

Type annotation được duy trì theo chính sách retention của annotation và theo metadata mà compiler ghi vào class file. Java Reflection không biến mọi annotation trong source thành đối tượng truy cập được.

Ví dụ, Reflection chuẩn **không có API tương ứng `Field.getAnnotatedType()` để quét mọi biến cục bộ trong thân method**. Một công cụ phân tích local variable/type-use ở mức sâu có thể cần xử lý source hoặc bytecode bằng công cụ phù hợp. Ngoài ra, thay đổi cấu trúc generic sau biên dịch (type erasure) khiến không thể lấy **kiểu generic thực tế của từng phần tử trong một `List` tại runtime** chỉ bằng cách đọc field type annotation.

`getAnnotatedType()` mô tả kiểu **được khai báo trên field/method/class**, không phải kiểm tra trạng thái hoặc dữ liệu thực tế của các object lưu trong field.

## 12. Cách thiết kế một trình duyệt `AnnotatedType` an toàn

Khi viết công cụ dùng chung, nên thực hiện theo trình tự:

1. **Chọn đúng điểm vào**: field, method return, parameter, superclass hoặc annotated bound.
2. **Đọc annotation trên nút hiện tại** (ví dụ `getAnnotationsByType` cho repeatable hoặc `getAnnotation` cho loại đơn).
3. **Phân nhánh bằng `instanceof`** cho parameterized, array, wildcard và type variable.
4. **Duyệt đệ quy các nút con** và ghi đường đi: `.argN`, `.component`, `.upperN`, `.lowerN`, `.boundN`.
5. Nếu cần, đọc **owner type** bằng `getAnnotatedOwnerType()`.
6. **Bảo vệ khỏi chu trình** do generic self-reference và xử lý metadata không hợp lệ hoặc thiếu lớp phụ thuộc theo mục tiêu của công cụ.
7. **Tách duyệt và diễn giải**: bộ duyệt phát hiện annotation; code khác quyết định annotation `"nullable"` hay `"validated"` có ý nghĩa nghiệp vụ nào.

Với use case chỉ cần đọc một field có `List<@Mark String>`, có thể truy cập đối số đầu tiên mà không cần bộ duyệt đệ quy tổng quát. Nhưng với cây nhiều tầng như `Map<String, List<@Mark Integer>[]>` hoặc generic có wildcard/bound, cách duyệt có cấu trúc như bài này giúp bảo đảm các vị trí type-use không bị bỏ sót.

## 13. Tự kiểm tra

Cho field minh họa:

```java
java.util.List<
    @Mark("wild") ? extends @Mark("bound") Number
> @Mark("array") [] values;
```

Giả sử `Mark` có `@Target(TYPE_USE)` và `@Retention(RUNTIME)`. Hãy xác định:

1. Nút gốc `field.getAnnotatedType()` thuộc interface nào? **`AnnotatedArrayType`** vì field là mảng `List<...>[]`.
2. Annotation `"array"` nằm ở đâu? **Trên chính nút mảng gốc**.
3. Đi từ mảng đến `List<...>` bằng API nào? **`getAnnotatedGenericComponentType()`**.
4. Từ `List<...>` đến wildcard `?` dùng API nào? **`getAnnotatedActualTypeArguments()[0]`** của `AnnotatedParameterizedType`.
5. Marker `"wild"` nằm ở đâu? **Trên nút `AnnotatedWildcardType`**.
6. Marker `"bound"` nằm ở đâu? **Trên `Number` trả về bởi `getAnnotatedUpperBounds()[0]`**.
7. Có thể đọc tất cả marker bằng `Field.getAnnotations()` không? **Không**: đó là metadata trên các vị trí sử dụng kiểu, phải bắt đầu từ `getAnnotatedType()` rồi đi theo cây.

Tài liệu API chính thức của Java 17: [`AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [`AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html), [`AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html), [`AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html), [`AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html).
