# Không suy ra kiểu phần tử chỉ bằng việc xem các phần tử đang có

Trong Java Reflection và **phân giải generic**, việc duyệt một `List`, `Set` hay `Collection` và quan sát `element.getClass()` chỉ cho biết **kiểu runtime của những đối tượng đã được nhìn thấy**. Nó **không chứng minh được** kiểu tham số generic mà tập hợp được khai báo, cũng không bảo đảm tập hợp sẽ chỉ nhận đúng những kiểu đó trong tương lai.

Ví dụ, một `List<Number>` hoàn toàn hợp lệ khi chứa `Integer` và `Double`. Việc thấy phần tử đầu là `Integer` không biến danh sách thành `List<Integer>`. Tương tự, một `List<Object>` có thể tình cờ chỉ chứa `String`; danh sách rỗng không cung cấp phần tử để quan sát; và phần tử `null` không có `getClass()`.

**Nguyên tắc:** muốn biết *kiểu khai báo* của generic, hãy tìm **thông tin kiểu từ khai báo/metadata**, hoặc yêu cầu caller truyền một **type contract** tường minh. Đừng đoán chữ ký generic chỉ từ sample dữ liệu.

## 1. Phân biệt bốn lớp thông tin về kiểu

| Câu hỏi | Ví dụ | Điều có thể xác định |
|---|---|---|
| **Kiểu runtime của collection object?** | `list.getClass()` | Chẳng hạn `java.util.ArrayList`; thường **không** có đối số kiểu `String`/`Number` |
| **Kiểu runtime của phần tử đang có?** | `list.get(0).getClass()` | Chẳng hạn `Integer.class`, nếu có phần tử khác `null` |
| **Kiểu generic được khai báo ở field/method?** | `Field.getGenericType()`, `Method.getGenericReturnType()` | Có thể là `List<Number>`, `List<? extends Number>`, `List<T>`... |
| **Hợp đồng kiểu mà ứng dụng muốn áp dụng?** | `Class<E>`, `Type`/type token, schema | Kiểu đích do API hoặc schema quy định, không nhất thiết có thể phục hồi từ giá trị hiện tại |

Hai kiểu đầu là **runtime observations**. Kiểu thứ ba là **thông tin khai báo có trong metadata** nếu nơi bạn đang xét lưu đủ chữ ký generic. Kiểu thứ tư là **yêu cầu do thiết kế ứng dụng cung cấp**.

Một danh sách cụ thể có thể thỏa đồng thời:

```java
List<Number> prices = new ArrayList<>();
prices.add(Integer.valueOf(7));
prices.add(Double.valueOf(2.5));
```

- Kiểu khai báo của biến `prices`: `List<Number>`.
- Kiểu runtime của object: `ArrayList`.
- Kiểu runtime của hai phần tử: `Integer` và `Double`.
- Không có mâu thuẫn: `Integer` và `Double` đều là lớp con của `Number`.

Đoạn mã trên là minh họa riêng, không có `main`. Nếu chỉ quan sát phần tử đầu, ta thậm chí còn **không thấy được** phần tử `Double` phía sau.

## 2. Tại sao xem phần tử không đủ để suy ra `List<T>`?

### 2.1. Có thể quan sát sai vì dữ liệu chưa đại diện

Một danh sách ban đầu chỉ chứa `Integer` nhưng sau đó được thêm `Double` nếu chữ ký của nó là `List<Number>`. Việc quan sát tập hợp tại một thời điểm chỉ phản ánh **trạng thái dữ liệu tại thời điểm đó**, không phản ánh mọi giá trị hợp lệ.

Tương tự, một `List<Object>` có thể chứa toàn `String` hôm nay, nhưng ngày mai chứa một `LocalDate`. Trong trường hợp này, tìm lớp chung gần nhất giữa các phần tử (nếu cố làm) cũng chỉ là một phép xấp xỉ trên **mẫu**, không phải **kiểu tham số được khai báo**.

### 2.2. Danh sách rỗng: không có thông tin runtime về phần tử

```java
List<String> names = new ArrayList<>();
List<Integer> ids = new ArrayList<>();
```

Cả `names` và `ids` đều rỗng. Việc gọi `getClass()` trên hai object này cho cùng lớp `ArrayList`; không thể lấy một phần tử để nhận diện generic argument. Thậm chí khi danh sách không rỗng, `getClass()` của container vẫn không phục hồi được tham số `String` hoặc `Integer` cho một `ArrayList` thông thường.

### 2.3. Phần tử `null` không có runtime class

```java
List<String> names = new ArrayList<>();
names.add(null);
```

`null` hợp lệ với kiểu phần tử tham chiếu, nhưng `names.get(0).getClass()` ném `NullPointerException`. Ngay cả khi bỏ qua các phần tử `null`, dữ liệu còn lại vẫn không đủ để kết luận chữ ký generic.

### 2.4. Kiểu phần tử runtime thường cụ thể hơn kiểu khai báo

```java
List<CharSequence> texts = new ArrayList<>();
texts.add("abc");
```

Một phần tử `String` là `CharSequence`. Đọc `texts.get(0).getClass()` cho `String.class`, nhưng **kiểu generic khai báo là `CharSequence`**, không phải `String`.

Tương tự: field `List<? extends Number>` có thể cung cấp các phần tử `Integer`, nhưng không thể kết luận đối số kiểu gốc là `Integer`. Wildcard chỉ công bố **ràng buộc**, không công bố nhất thiết một concrete type.

### 2.5. Raw types/unchecked operations có thể làm bẩn dữ liệu

Java generic chủ yếu bảo vệ kiểu ở compile time. Code sử dụng raw type, unchecked cast hoặc interop với thư viện cũ có thể tạo **heap pollution**:

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static void corrupt(List<String> strings) {
    List raw = strings;
    raw.add(Integer.valueOf(99));
}
```

Đây là **đoạn phương thức minh họa**, không nên dùng trong ứng dụng thực. Sau thao tác ấy, metadata khai báo vẫn có thể nói `List<String>`, nhưng nội dung thực tế lại chứa `Integer`. Khi code Java bình thường lấy phần tử như `String`, có thể gặp `ClassCastException`.

Kết luận hai chiều: **không suy ra kiểu khai báo từ phần tử**, đồng thời **không dùng metadata khai báo để khẳng định dữ liệu runtime không bao giờ bị vi phạm** nếu có unchecked/raw operations.

## 3. Vì sao dữ liệu quan sát khác thông tin generic?

Một đối tượng `new ArrayList<String>()` thông thường có runtime class `ArrayList.class`, giống đối tượng tạo với `new ArrayList<Integer>()`. Cơ chế **type erasure** không lưu đối số `String` hay `Integer` riêng trên mỗi instance. Nếu duyệt một danh sách chứa toàn chuỗi, đó vẫn chỉ là dữ liệu hiện tại: kiểu khai báo hoàn toàn có thể là `List<Object>` hoặc `List<CharSequence>`.

Ngược lại, class file có thể giữ *generic signature* của **nơi khai báo**: một field `List<Number> prices`, return type `List<String>` hoặc quan hệ `extends ArrayList<Long>`. Reflection có API đọc metadata đó, nhưng không tự gắn ngược metadata của một biến local bất kỳ vào object mà biến trỏ tới.

| Muốn biết | Đọc bằng | Giới hạn cần giữ rõ |
| --- | --- | --- |
| Collection đang dùng implementation nào | `object.getClass()` | Không tiết lộ generic argument |
| Giá trị hiện có thuộc class nào | `element.getClass()` | Có thể rỗng, `null`, subtype hoặc bị thay đổi |
| Kiểu đã khai báo trên field | `Field.getGenericType()` | Mô tả khai báo; không chứng minh nội dung runtime |
| Kiểu đã khai báo trên method | `Method.getGenericReturnType()` / `getGenericParameterTypes()` | Không tự lưu type argument suy diễn của từng lời gọi |
| Supertype generic đã khai báo | `Class.getGenericSuperclass()` / `getGenericInterfaces()` | Nếu còn `TypeVariable` thì cần ngữ cảnh phân giải |

## 4. Đọc chữ ký phần tử từ đúng declaration

Với field bên dưới, Reflection đọc được `Number` vì thông tin nằm trong **khai báo field**, không phải do lấy `getClass()` của phần tử đầu tiên:

~~~java
class Catalog {
    java.util.List<Number> prices = new java.util.ArrayList<>();
}

// Đặt trong method có xử lý NoSuchFieldException:
java.lang.reflect.Field field = Catalog.class.getDeclaredField("prices");
java.lang.reflect.Type declared = field.getGenericType();
if (declared instanceof java.lang.reflect.ParameterizedType p) {
    System.out.println(p.getActualTypeArguments()[0].getTypeName());
    // java.lang.Number
}
~~~

Nếu chỉ có tham chiếu `Object unknown` tới một list được tạo thông thường, không có phép Reflection tổng quát nào xác định **field hoặc biến nguồn** từng dùng để tham chiếu object đó. Bài thí nghiệm tiếp theo đặt runtime observations cạnh metadata từ field để thấy sự khác biệt này.

## 5. Khi đối số generic chưa phải một Class cụ thể

`Field.getGenericType()` trả `Type`; một argument trực tiếp của `List<E>` có thể là `Class<?>` (như `Number`), `TypeVariable<?>` (như `T` trong `Holder<T>`), `WildcardType` (như `? extends Number`) hoặc một `ParameterizedType` lồng nhau (như `List<Integer>` trong `List<List<Integer>>`). Với `List<String>[]`, lớp bao ngoài có thể là `GenericArrayType`; component là một `ParameterizedType`.

Vì thế, phép lấy `getActualTypeArguments()[0]` phải đặt trong ngữ cảnh **raw type** đang phân tích. `Map<K,V>` có hai arguments, và `List<? extends Number>` mang wildcard bound chứ không công bố chính xác `Number` như đối số cụ thể. Nếu argument còn là biến kiểu `T` của superclass, cần ánh xạ theo khai báo và quan hệ kế thừa; tuyệt đối không thay bằng `Object` hoặc upper bound một cách tùy ý.

## 6. Thí nghiệm Java 17+ hoàn chỉnh: kiểu quan sát khác kiểu khai báo

Lưu thành tệp **`GenericElementDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class GenericElementDemo {
    static class Catalog {
        List<Number> prices = new ArrayList<>();
        List<String> emptyNames = new ArrayList<>();
        List<String> nullableNames = Arrays.asList(null, "Lan");
        List<List<Integer>> matrix = List.of(List.of(1, 2));
        List<? extends Number> readOnly = List.of(5, 6.5);
        List<? super Integer> writable = new ArrayList<Number>();
        List<String>[] buckets;
    }

    static class Holder<T extends Number> {
        List<T> items = new ArrayList<>();
    }

    static class IntegerHolder extends Holder<Integer> { }
    static class LongList extends ArrayList<Long> { }

    static Type firstArgument(Field field) {
        Type generic = field.getGenericType();
        if (!(generic instanceof ParameterizedType parameterized)) {
            throw new IllegalArgumentException(
                    "Not parameterized: " + field.getName());
        }
        return parameterized.getActualTypeArguments()[0];
    }

    public static void main(String[] args) throws Exception {
        Catalog data = new Catalog();
        data.prices.add(7);
        data.prices.add(2.5);

        System.out.println("observed: "
                + data.prices.get(0).getClass().getSimpleName()
                + ", " + data.prices.get(1).getClass().getSimpleName());
        System.out.println("runtime list: "
                + data.prices.getClass().getName());
        System.out.println("empty sample: "
                + data.emptyNames.isEmpty());
        System.out.println("first null: "
                + (data.nullableNames.get(0) == null));

        Field prices = Catalog.class.getDeclaredField("prices");
        System.out.println("erased field: "
                + prices.getType().getTypeName());
        System.out.println("generic field: "
                + prices.getGenericType().getTypeName());
        System.out.println("declared element: "
                + firstArgument(prices).getTypeName());

        System.out.println("nested element: "
                + firstArgument(
                        Catalog.class.getDeclaredField("matrix"))
                        .getTypeName());
        System.out.println("upper wildcard: "
                + firstArgument(
                        Catalog.class.getDeclaredField("readOnly"))
                        .getTypeName());
        System.out.println("lower wildcard: "
                + firstArgument(
                        Catalog.class.getDeclaredField("writable"))
                        .getTypeName());
        System.out.println("array type: "
                + Catalog.class.getDeclaredField("buckets")
                        .getGenericType().getTypeName());

        System.out.println("unresolved variable: "
                + firstArgument(Holder.class.getDeclaredField("items"))
                        .getTypeName());
        Type parent = IntegerHolder.class.getGenericSuperclass();
        System.out.println("subclass binding: "
                + ((ParameterizedType) parent)
                        .getActualTypeArguments()[0].getTypeName());

        Type inherited = LongList.class.getGenericSuperclass();
        System.out.println("specialized subclass: "
                + ((ParameterizedType) inherited)
                        .getActualTypeArguments()[0].getTypeName());

        System.out.println("same erased class: "
                + (new ArrayList<String>().getClass()
                == new ArrayList<Integer>().getClass()));
    }
}
```

Chạy từ thư mục chứa tệp bằng JDK 17+:

```bash
javac GenericElementDemo.java
java GenericElementDemo
```

**Stdout đã kiểm tra trên JDK 21:**

```text
observed: Integer, Double
runtime list: java.util.ArrayList
empty sample: true
first null: true
erased field: java.util.List
generic field: java.util.List<java.lang.Number>
declared element: java.lang.Number
nested element: java.util.List<java.lang.Integer>
upper wildcard: ? extends java.lang.Number
lower wildcard: ? super java.lang.Integer
array type: java.util.List<java.lang.String>[]
unresolved variable: T
subclass binding: java.lang.Integer
specialized subclass: java.lang.Long
same erased class: true
```

### Vì sao những dòng này quan trọng?

1. Hai phần tử của `prices` có kiểu runtime khác nhau (`Integer`, `Double`); chữ ký khai báo vẫn là `List<Number>`.
2. `prices.getClass()` chỉ cho biết container là `ArrayList`, không biết `Number`.
3. Với `emptyNames`, không có phần tử để suy đoán. Với `nullableNames`, phần tử đầu là `null`; gọi `getClass()` trực tiếp trên nó sẽ lỗi.
4. `Field.getType()` trả `java.util.List` do erasure; `Field.getGenericType()` đọc signature khai báo `List<Number>`. Đây là lý do Reflection có thể biết kiểu phần tử **từ metadata**, chứ không phải từ nội dung.
5. Argument đầu của `matrix` là `List<Integer>` (một nested `ParameterizedType`); chưa phải bản thân `Integer`.
6. Hai wildcard công bố bounds, không công bố chính xác một actual type argument đơn lẻ.
7. Field `Holder.items` có argument `T`, vì bối cảnh `Holder<T>` vẫn trừu tượng; `IntegerHolder` mang binding `Integer` ở superclass, nhưng phải **tự kết hợp ngữ cảnh** khi phân giải field kế thừa.
8. `LongList` bảo tồn `Long` ở chữ ký **generic superclass** vì chính class được khai báo là `extends ArrayList<Long>`.
9. Hai object `new ArrayList<String>()` và `new ArrayList<Integer>()` có cùng `Class` runtime; type erasure không tạo một `ArrayList` class riêng cho từng đối số generic.

## 7. Tra cứu generic từ method và superclass/interface

Không phải thông tin generic nào cũng nằm trên field. Một API thường công bố dữ liệu qua return type của getter hoặc parameter type của setter:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.lang.reflect.ParameterizedType;
import java.util.List;

class Service {
    public List<String> findNames() {
        return List.of("Lan");
    }

    public void replaceNames(List<String> names) {
    }
}

// Đoạn minh họa dùng trong phương thức có xử lý NoSuchMethodException:
Method getter = Service.class.getMethod("findNames");
Type returnSignature = getter.getGenericReturnType();
// returnSignature mô tả List<String>

Method setter = Service.class.getMethod("replaceNames", List.class);
Type parameterSignature = setter.getGenericParameterTypes()[0];
// parameterSignature mô tả List<String>
```

Đây là **đoạn minh họa gồm class và các lệnh Reflection**, không phải chương trình độc lập có `main`. Chữ ký `getMethod("replaceNames", List.class)` dùng **raw runtime parameter class** vì lookup method diễn ra sau erasure; sau khi tìm xong mới đọc `getGenericParameterTypes()` để biết `String`.

Bạn cũng có thể đọc:

- `SomeClass.class.getGenericSuperclass()` để xem superclass được khai báo với type arguments nào.
- `SomeClass.class.getGenericInterfaces()` để xem các generic interfaces được triển khai.
- `field.getGenericType()` để xem field signature được khai báo.
- `method.getGenericReturnType()` và `getGenericParameterTypes()` để xem return/parameter signatures.

**Không được suy từ method body:** `findNames()` có thể trả một `List.of()` rỗng, hoặc mọi phần tử là `null` trong các triển khai khác. Điều hữu ích cho Reflection là **return type khai báo** `List<String>`, chứ không phải runtime sample trong từng lần gọi.

### Cần ngữ cảnh khi type variable đi qua nhiều cấp kế thừa

Ví dụ:

```java
class Base<T> {
    List<T> values;
}

class Middle<U> extends Base<U> {
}

class Concrete extends Middle<Long> {
}
```

Field `values` được khai báo ở `Base` với `T`, trong khi `Concrete` cung cấp binding `U -> Long` và `Middle<U>` cung cấp `T -> U`. Để kết luận `values` ứng với `List<Long>` khi xét `Concrete`, bộ phân giải generic phải **đi qua các generic superclass signatures** và thay thế type variables nhất quán.

Chỉ gọi `Concrete.class.getDeclaredField("values")` còn thất bại vì field **không được khai báo trực tiếp** trong `Concrete`. Phải tìm field ở lớp khai báo hoặc duyệt hierarchy, rồi phân giải theo ngữ cảnh class cụ thể.

Khi thiết kế resolver, đừng luôn coi `TypeVariable.getBounds()[0]` là actual type. Bound chỉ giới hạn các kiểu hợp lệ; không phải giá trị thay thế thực tế.

## 8. Khi không có generic metadata: yêu cầu hợp đồng kiểu tường minh

Nhiều API nhận trực tiếp một object:

```java
void process(List<?> items) {
    // Không có field/method declaration của danh sách ban đầu
    // để khôi phục chắc chắn actual element type E.
}
```

Tại đây `items.getClass()` thường chỉ cho lớp collection. Nếu API cần bảo đảm kiểu phần tử, hãy chuyển kiểu mong đợi vào theo một trong các cách:

**Lựa chọn A — truyền `Class<E>` cho phần tử không generic lồng nhau:**

```java
static <E> void validate(List<?> items, Class<E> elementClass) {
    for (Object item : items) {
        if (item != null && !elementClass.isInstance(item)) {
            throw new IllegalArgumentException(
                    "Unexpected element type: " + item.getClass().getName());
        }
    }
}

// Ví dụ trong một phương thức khác:
validate(List.of("a", "b"), String.class);
```

Đây là đoạn phương thức minh họa, đã giả định import `java.util.List`. Logic này **kiểm tra dữ liệu theo kiểu do caller cung cấp**, không *suy ra* generic type. Với `null`, code minh họa đang chấp nhận; nếu domain cấm null thì cần thêm nhánh từ chối riêng. `Class.isInstance` kiểm tra runtime assignability; không làm được kiểm tra đầy đủ với nested type `List<List<String>>`. Đối với generic `List<Integer>`, hãy truyền `Integer.class`, không phải `int.class`.

**Lựa chọn B — truyền một `Type` hoặc type token cho cấu trúc nested:**

```java
abstract class TypeRef<T> {
    final java.lang.reflect.Type type;

    protected TypeRef() {
        java.lang.reflect.Type parent =
                getClass().getGenericSuperclass();
        if (!(parent instanceof java.lang.reflect.ParameterizedType p)) {
            throw new IllegalStateException("Missing generic signature");
        }
        type = p.getActualTypeArguments()[0];
    }
}

// Khi tạo anonymous subclass của TypeRef:
java.lang.reflect.Type target =
        new TypeRef<java.util.List<java.util.Map<String, Integer>>>() { }
                .type;
```

Đây là đoạn **mẫu type token tối giản**, đặt các khai báo ở phạm vi class và câu lệnh `target` trong một phương thức phù hợp; nó dựa vào generic superclass signature được compiler ghi cho anonymous subclass. Không tự động kiểm tra dữ liệu hoặc chuyển JSON thành Java object: nó chỉ giữ cấu trúc `Type` để thư viện/bộ xử lý tiếp tục sử dụng. Với type variable chưa được giải trong anonymous subclass, vẫn phải xem ngữ cảnh phù hợp.

**Lựa chọn C — định nghĩa schema hoặc API rõ ràng:** nếu dữ liệu đến từ JSON, database, message queue hay plugin, hợp đồng bên ngoài (schema, serializer configuration hoặc type descriptor) thường đáng tin hơn việc xem phần tử đầu tiên. Những dữ liệu rỗng hay có null vẫn cần được parse/validate đúng kiểu.

## 9. Vì sao không thể luôn lấy “kiểu chung” của tất cả phần tử?

Giả sử danh sách có `Integer` và `Double`. Ta có thể nhận thấy chúng đều mở rộng `Number`, nhưng:

- Kiểu khai báo có thể là `List<Number>`, `List<Object>`, `List<? extends Number>` hoặc một view/kiểu khác.
- Nhiều loại Java có chung interface như `Serializable`, `Comparable<?>...`; “kiểu chung gần nhất” không nhất thiết là một class duy nhất có ý nghĩa làm type argument.
- Với dữ liệu thiếu, null hoặc collection rỗng, không có đủ chứng cứ để suy ra type.
- Type variable và wildcard diễn đạt **quan hệ/ràng buộc**, không thể được phục hồi đầy đủ từ một tập hữu hạn object đang tồn tại.
- Type erasure cho phép nhiều generic instantiations dùng cùng runtime class; class của container không chứa đủ dữ liệu để đảo ngược erasure.

Một heuristic tính common superclass có thể hữu ích để **phân tích dữ liệu** hoặc đề xuất schema, nhưng phải được gọi đúng là **suy đoán dựa trên sample**. Đừng trình bày heuristic ấy như kết quả của generic type resolution, và đừng đưa nó vào cast/deserialize quan trọng mà không kiểm tra hoặc không có schema chính thức.

## 10. Ứng dụng thực tế

### Serialization / deserialization

Một JSON array `[]` không có phần tử nào để suy kiểu; JSON `[null]` cũng không có runtime class có thể dùng. Nếu mục tiêu là `List<Order>`, serializer cần nhận thông tin kiểu từ field/getter signature hoặc type descriptor, chứ không thể chỉ xem từng giá trị của array.

Ví dụ với nested type `List<Map<String, List<Order>>>`, `Class<List>` không mô tả đủ cấu trúc. Cần `Type`/type token hoặc mô tả kiểu tương đương để bảo toàn nested generic arguments.

### ORM / database mapping

Một quan hệ `List<User>` có thể hiện tại chưa load bản ghi nào. Khung ORM không thể nhìn tập hợp trống để suy entity type, mà cần field/association metadata, annotation, schema hoặc mapping được khai báo.

### Plugin / event processing

Một `List<Event>` có thể chứa nhiều subtype `LoginEvent`, `PurchaseEvent`; đó là polymorphism hợp lệ. Đừng dùng class của event đầu tiên để suy rằng mọi event thuộc subtype đó. Hợp đồng handler cần nói rõ event base type hoặc registry/type descriptor.

### Validation

Nếu hệ thống nhận `List<?>` từ dữ liệu không tin cậy, phải validate từng phần tử theo schema/type đã biết; việc quan sát một phần tử hợp lệ không chứng minh toàn bộ danh sách hợp lệ. Nếu type có nested generics, validation phải đi sâu vào từng tầng dữ liệu theo hợp đồng, không chỉ kiểm tra raw `List.class`.

## 11. Các lỗi tư duy phổ biến

1. **“Phần tử đầu là `Integer` nên list có kiểu `List<Integer>`.”** Sai. Có thể là `List<Number>`, `List<Object>` hoặc kiểu khác.
2. **“Mọi phần tử hiện có đều là `String` nên generic chắc chắn là `String`.”** Sai. Mẫu dữ liệu không chứng minh chữ ký khai báo.
3. **“Danh sách rỗng có thể suy phần tử từ `getClass()`.”** Sai với `ArrayList` thông thường do erasure.
4. **“Đọc `getClass()` trên một phần tử `null` vẫn biết được kiểu.”** Sai: gây `NullPointerException`.
5. **“Java xóa hết generic metadata nên Reflection không thể đọc bất kỳ generic type nào.”** Sai. Signature của field, method, superclass/interface có thể vẫn chứa cấu trúc generic.
6. **“`getType()` và `getGenericType()` luôn giống nhau.”** Sai. Với `List<String>`, một bên có thể trả `List.class`, bên kia trả `ParameterizedType` mô tả `List<String>`.
7. **“Mọi `Type` có thể cast thành `Class<?>`.”** Sai. `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType` cần xử lý riêng.
8. **“`List<? extends Number>` có actual argument đúng `Number`.”** Sai. Nó là wildcard có upper bound `Number`, không phải `Number.class`.
9. **“Field `List<T>` trong base class tự trở thành `List<Integer>` khi gọi `getGenericType()` ở base.”** Sai. Phải phân giải type variable theo generic bindings trên đường kế thừa.
10. **“Type token kiểm tra mọi phần tử runtime đã đúng kiểu.”** Sai. Type token chỉ mang metadata kiểu; validation/deserialization là bước khác.
11. **“`List<Integer>` là subtype của `List<Number>` vì `Integer extends Number`.”** Sai. Java generic ở đây **invariant**; có thể dùng `List<? extends Number>` cho read-only view phù hợp.
12. **“Đã biết `List<String>` từ field metadata thì runtime không thể có phần tử `Integer`.”** Không bảo đảm tuyệt đối khi tồn tại raw/unchecked operations; cần validation nếu input không tin cậy.
13. **“Mảng `List<String>[]` có component là `String`.”** Sai. Component là **`List<String>`**; từng List mới có element type `String`.

## 12. Tự kiểm tra

**Câu 1.** Một `List<Number>` hiện chỉ chứa `Integer(1)`. `list.get(0).getClass()` cho biết điều gì?

**Đáp án:** Chỉ cho biết object được quan sát có runtime class `Integer`; không đổi hay xác định được kiểu khai báo `List<Number>`.

**Câu 2.** Một list rỗng có thể là `List<String>` hay `List<Integer>`. Vì sao `list.getClass()` không đủ?

**Đáp án:** Với `ArrayList` thông thường, generic type arguments đã bị erasure ở runtime; cả hai object đều có class `ArrayList`. Không có phần tử để suy thêm và sample inference cũng không chứng minh declaration.

**Câu 3.** Field `List<? extends Number> values` có `getGenericType()` thuộc dạng gì và argument đầu thuộc dạng gì?

**Đáp án:** `getGenericType()` có thể là `ParameterizedType` cho `List<? extends Number>`; argument đầu là `WildcardType` có upper bound `Number`, không phải trực tiếp `Number.class`.

**Câu 4.** Khi field được khai báo `Map<String, List<Integer>>`, có thể luôn lấy `getActualTypeArguments()[0]` làm kiểu phần tử của một List không?

**Đáp án:** Không. Raw type là `Map` với hai tham số `K,V`, trong đó phần tử cần phân tích thuộc **value argument** `List<Integer>`. Phải hiểu cấu trúc generic đúng loại.

**Câu 5.** `Holder<T>` khai báo `List<T> items`, `IntHolder extends Holder<Integer>`. Vì sao chỉ đọc field ở `Holder.class` vẫn thấy `T`?

**Đáp án:** Vì field được khai báo bằng type variable `T`. Binding `T -> Integer` thuộc bối cảnh `IntHolder` và phải được áp dụng khi phân giải.

**Câu 6.** API nhận `List<?>` có thể bảo đảm tất cả phần tử là `User` chỉ bằng kiểm tra phần tử đầu không?

**Đáp án:** Không. Cần hợp đồng `User.class`/schema/type token rõ ràng và validate mọi phần tử cần thiết; dữ liệu còn có thể rỗng, null, hỗn hợp hoặc bị thêm sau khi kiểm tra.

## Tài liệu chuẩn

- Java SE API — `java.lang.reflect.Field.getType()`, `Field.getGenericType()`; `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`.
- Java SE API — `java.lang.reflect.Type`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`.
- Java SE API — `java.lang.Class.getGenericSuperclass()`, `Class.getGenericInterfaces()`, `Class.isInstance(Object)`.
- Java Language Specification — §4.5 *Parameterized Types*; §4.6 *Type Erasure*; §4.8 *Raw Types*; §4.12.2 *Variables of Reference Type*; §5.1.10 *Capture Conversion*.
- Java Language Specification — §10.5 *Array Store Exception* và các quy tắc generic arrays/reifiable types khi phân tích mảng.

**Ghi nhớ:** phần tử đang có chỉ cho biết **runtime class của mẫu dữ liệu**, không xác nhận **kiểu generic được khai báo**. Để phân giải generic, hãy dùng **metadata ở đúng vị trí khai báo và đúng ngữ cảnh kế thừa**, hoặc **hợp đồng kiểu tường minh**. Với dữ liệu không tin cậy, kiểm tra phần tử theo hợp đồng, không suy kiểu từ phần tử đầu tiên.