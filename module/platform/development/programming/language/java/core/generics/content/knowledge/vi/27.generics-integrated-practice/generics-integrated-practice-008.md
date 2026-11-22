# Xây dựng kho nhiều kiểu và type token cho cấu trúc lồng nhau trong Java Generics

## 1. Bài toán và kết quả mong đợi

Thông thường, một collection generic lưu nhiều giá trị **cùng một kiểu phần tử**:

~~~java
List<String> names = List.of("Java", "Kotlin");
Map<String, Integer> points = Map.of("A", 10, "B", 20);
~~~

Nhưng có trường hợp ứng dụng muốn một **kho giá trị nhiều kiểu** (*heterogeneous typed store*), trong đó từng khóa cho biết kiểu của giá trị đi kèm:

- Khóa `String.class` đi kèm một `String`.
- Khóa `Integer.class` đi kèm một `Integer`.
- Khóa đại diện `List<String>` đi kèm danh sách chuỗi.
- Khóa đại diện `List<Integer>` đi kèm danh sách số nguyên.
- Khóa đại diện `Map<String, List<Integer>>` đi kèm cấu trúc lồng nhau.

Ta muốn gọi phương thức có chữ ký generic:

~~~java
<T> void put(TypeRef<T> key, T value);
<T> T get(TypeRef<T> key);
~~~

để compiler kiểm tra mối quan hệ giữa **kiểu khóa** và **kiểu dữ liệu được thêm vào**, trong khi bên trong kho vẫn phải lưu các giá trị khác kiểu cạnh nhau.

Mục tiêu của bài:

1. Xây dựng phiên bản đơn giản dùng **`Class<T>` làm type token** cho kiểu reifiable như String/Integer.
2. Nhận ra hạn chế: `List<String>.class`, `Map<String, List<Integer>>.class` không tồn tại trong Java.
3. Xây dựng **`TypeRef<T>`** lưu `java.lang.reflect.Type` để đại diện cho cấu trúc generic lồng nhau.
4. Xây dựng một kho dùng `Map<Type, Object>` làm nơi lưu nội bộ, với API generic ở bên ngoài.
5. Hiểu chính xác phần an toàn **compile time** và phần **runtime validation** chưa được bảo đảm chỉ bằng một type token.
6. Thử thực tế với Java 17+, kèm trường hợp dữ liệu sai kiểu bị phát hiện.

Không nên gọi `TypeRef<T>` là một “kiểu runtime mới” hay cho rằng nó khiến JVM giữ nguyên toàn bộ thông tin generic của mọi đối tượng. Nó giữ **mô tả kiểu bằng Reflection**, còn dữ liệu thực sự vẫn chịu type erasure.

## 2. Kho nhiều kiểu khác Map<String, Object> thông thường như thế nào?

Một cách thiết kế ban đầu:

~~~java
Map<String, Object> values = new HashMap<>();
values.put("title", "Java");
values.put("count", 3);
~~~

Cách này lưu được nhiều kiểu, nhưng kiểu của giá trị **không được nối với kiểu khóa** bằng hệ thống kiểu:

~~~java
String title = (String) values.get("title");
Integer count = (Integer) values.get("count");
~~~

Các cast do người dùng viết có thể thất bại vì gõ sai khóa hoặc dữ liệu ở khóa tương ứng đã bị thay.

Kho có type token muốn đưa quan hệ đó vào **chữ ký generic**:

~~~java
store.put(String.class, "Java");
store.put(Integer.class, 3);

String title = store.get(String.class);
Integer count = store.get(Integer.class);
~~~

Compiler có thể suy luận `T = String` hoặc `T = Integer` từ `Class<T>`, nên người gọi không phải viết cast khi đọc.

Mặc dù kho nội bộ vẫn dùng Object, một API được thiết kế đúng có thể giữ bất biến:

> Với mỗi type token dùng làm khóa, giá trị lưu dưới khóa đó được chấp nhận theo kiểu gắn với token tại thời điểm ghi.

Đây là **bất biến của API**, không phải phép màu của bộ nhớ runtime. Nếu cho phép truy cập raw type, unchecked cast, reflection, hoặc thay đổi dữ liệu lồng nhau qua alias không an toàn, bất biến vẫn có thể bị phá vỡ.

## 3. Phiên bản đầu tiên: type token Class<T>

`Class<T>` là token quen thuộc và hữu ích cho những kiểu có thể kiểm tra trực tiếp tại runtime:

~~~java
final class ClassStore {
    private final Map<Class<?>, Object> values = new HashMap<>();

    <T> void put(Class<T> type, T value) {
        values.put(type, type.cast(value));
    }

    <T> T get(Class<T> type) {
        return type.cast(values.get(type));
    }
}
~~~

Đây là **một đoạn minh họa**, giả định file có import `java.util.*`. Chương trình hoàn chỉnh được trình bày ở phần sau.

Cơ chế:

- `Map<Class<?>, Object>` lưu các đối tượng token của nhiều loại khác nhau.
- `put(Class<T>, T)` gắn kiểu của token và giá trị trong cùng một lời gọi.
- `Class.cast` kiểm tra được top-level runtime class, ví dụ không thể ép một `Integer` thành `String`.
- `get(Class<T>)` trả về T, suy luận từ token mà người gọi cung cấp.

Ví dụ sai bị compiler chặn:

~~~java
// store.put(String.class, 123); // Không biên dịch: T không phù hợp.
~~~

**Giới hạn:** `Class<T>` không trực tiếp biểu diễn được type argument lồng nhau như `List<String>`. `List.class` là class token của raw `List`; nó không chứa thông tin phần tử String.

## 4. Vì sao List<String>.class không tồn tại?

Java cho phép class literal:

~~~java
String.class
Integer.class
List.class
Map.class
~~~

Nhưng các biểu thức sau **không hợp lệ**:

~~~java
// List<String>.class
// Map<String, List<Integer>>.class
~~~

Bởi generics trong Java phần lớn dựa trên **type erasure**. Một thể hiện của `ArrayList<String>` và `ArrayList<Integer>` về cơ bản có cùng runtime class:

~~~java
var strings = new ArrayList<String>();
var integers = new ArrayList<Integer>();

System.out.println(strings.getClass() == integers.getClass()); // true
~~~

Nếu kho chỉ dùng `List.class`, các danh sách phần tử khác kiểu sẽ trùng khóa:

~~~java
// Cùng một Class object làm khóa:
values.put(List.class, List.of("A"));
values.put(List.class, List.of(1)); // Ghi đè giá trị trước.
~~~

Không thể giải quyết bằng cách thêm cast unchecked từ `Class<List>` sang `Class<List<String>>` rồi tuyên bố đã khôi phục tham số kiểu. JVM không thu thập thông tin String cho từng instance của List theo cách đó.

Ta cần **một đối tượng mô tả kiểu phức hợp**. Java Reflection có hệ thống `java.lang.reflect.Type` dành cho mục đích biểu diễn kiểu, không phải để khiến generic arguments trở nên reifiable.

## 5. Type và ParameterizedType đại diện cấu trúc lồng nhau

`java.lang.reflect.Type` là abstraction mô tả kiểu Java trong API Reflection. Một số dạng quan trọng:

| Reflection API | Đại diện điển hình | Ý nghĩa |
| --- | --- | --- |
| `Class<?>` | `String.class`, `List.class` | Lớp/interface trực tiếp, không phải danh sách type arguments. |
| `ParameterizedType` | `List<String>` | Kiểu có raw type và type arguments. |
| `TypeVariable<?>` | `T` trong `class Holder<T>` | Biến kiểu có bound, chưa chắc có giá trị cụ thể ở runtime. |
| `WildcardType` | `? extends Number` | Wildcard với giới hạn trên/dưới. |
| `GenericArrayType` | `T[]` hoặc mảng thành phần generic phù hợp | Kiểu mảng được mô tả bằng Type phức hợp. |

Với `Map<String, List<Integer>>`, đối tượng mô tả kiểu có cấu trúc **lồng nhau**:

~~~text
ParameterizedType: Map<String, List<Integer>>
├── raw type: Map
├── argument 0: Class<String>
└── argument 1: ParameterizedType List<Integer>
    ├── raw type: List
    └── argument 0: Class<Integer>
~~~

Nhờ vậy, một key cho `List<String>` có thể được phân biệt với key cho `List<Integer>` theo cấu trúc Type, dù runtime class của hai danh sách đều có thể là ArrayList.

`ParameterizedType` thường dùng structural equality: hai Type mô tả cùng khai báo generic với cùng type arguments có thể `equals` nhau. Điều đó cho phép dùng `Type` làm key trong `HashMap`, miễn cách tạo Type nhất quán.

Quan trọng: đây là **metadata kiểu**. Không có phép đảm bảo rằng chỉ cần mang một `ParameterizedType` thì mọi phần tử nằm trong object được gán với metadata đó đều có kiểu chính xác.

## 6. TypeRef<T>: giữ chữ ký generic bằng anonymous subclass

Một kỹ thuật phổ biến là **super type token**:

~~~java
abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type parent = getClass().getGenericSuperclass();

        if (!(parent instanceof ParameterizedType parameterized)) {
            throw new IllegalStateException("Use an anonymous subclass");
        }

        this.type = parameterized.getActualTypeArguments()[0];
    }

    public final Type type() {
        return type;
    }
}
~~~

Đoạn này dùng các import của Reflection và là thành phần sẽ xuất hiện trong chương trình hoàn chỉnh ở phần 8.

Cách tạo token:

~~~java
TypeRef<List<String>> names =
        new TypeRef<List<String>>() {};

TypeRef<Map<String, List<Integer>>> nested =
        new TypeRef<Map<String, List<Integer>>>() {};
~~~

Dấu `{}` tạo **anonymous subclass** kế thừa `TypeRef<List<String>>` hoặc `TypeRef<Map<...>>`. Reflection đọc **generic superclass** của lớp ẩn danh để lấy Type mô tả chính xác type argument được viết ở source.

Tại constructor:

1. `getClass()` là class của anonymous subclass thực tế.
2. `getGenericSuperclass()` thường trả một `ParameterizedType` mô tả `TypeRef<List<String>>`.
3. `getActualTypeArguments()[0]` lấy Type của `List<String>`.
4. Trường `type` giữ Type đó, và kho có thể dùng nó làm khóa.

**Điều kiện:** kỹ thuật này yêu cầu lớp con thực sự có generic superclass đã được ghi lại và type argument phải có đủ thông tin. `new TypeRef<String>() {}` được hỗ trợ, nhưng `new TypeRef() {}` dùng raw superclass sẽ không cung cấp `ParameterizedType` như mong đợi và constructor trên chủ động từ chối.

## 7. Thiết kế kho dùng Map<Type, Object>

Một kho chung có thể lưu cả token đơn giản và token lồng nhau:

~~~java
final class TypedStore {
    private final Map<Type, Object> values = new HashMap<>();

    public <T> void put(Class<T> token, T value) {
        values.put(token, token.cast(Objects.requireNonNull(value)));
    }

    public <T> T get(Class<T> token) {
        return token.cast(values.get(token));
    }

    public <T> void put(TypeRef<T> token, T value) {
        values.put(token.type(), Objects.requireNonNull(value));
    }

    @SuppressWarnings("unchecked")
    public <T> T get(TypeRef<T> token) {
        return (T) values.get(token.type());
    }
}
~~~

Đây là thành phần của chương trình hoàn chỉnh ở phần tiếp theo.

### Vì sao bên trong cần Object?

Không có một `T` duy nhất đại diện cho mọi value: kho vừa có String, Integer, List<String>, Map<String,List<Integer>>, ... Vì vậy `Map<Type,Object>` là tầng lưu trữ hỗn hợp; các API `put/get` dùng generic method riêng cho từng lời gọi.

### Vì sao có unchecked cast trong get(TypeRef<T>)?

Runtime không thể dùng một `ParameterizedType` để thực hiện kiểu cast đầy đủ đến `List<String>` hoặc `Map<String,List<Integer>>`. Trong chương trình, biểu thức `(T) values.get(token.type())` chỉ cung cấp kiểm tra kiểu đã bị xóa. Compiler có thể chèn thêm cast cho kiểu reifiable khi caller nhận dữ liệu.

Lời gọi được dự kiến an toàn **theo bất biến của kho**: mọi entry phải được thêm qua `put(TypeRef<T>, T)` với kiểu phù hợp, và không có raw/unchecked đường khác làm hỏng dữ liệu.

`@SuppressWarnings("unchecked")` cần được đặt **hẹp**, trên phương thức duy nhất sử dụng cast được lý giải, không rải trên toàn bộ class hoặc cả chương trình. Nó không biến một cast vốn không thể kiểm tra đầy đủ thành checked cast.

### Thiết kế giá trị null và khóa không tồn tại

`put` ở trên cố ý **từ chối null** bằng `Objects.requireNonNull` để giảm nhập nhằng khi gọi `get` trả null. Dù vậy, `get` trả null nếu chưa có entry. API sản phẩm có thể dùng `Optional<T>`, `contains`, hoặc ném ngoại lệ khi khóa vắng mặt; đây là lựa chọn hợp đồng, không ảnh hưởng nguyên lý type token.

## 8. Chương trình Java 17+ đầy đủ và chạy được

Lưu đúng tên tệp **HeterogeneousStoreDemo.java**:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HeterogeneousStoreDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType parameterized)) {
                throw new IllegalStateException("Use an anonymous subclass");
            }
            type = parameterized.getActualTypeArguments()[0];
        }

        public final Type type() {
            return type;
        }
    }

    static final class TypedStore {
        private final Map<Type, Object> values = new HashMap<>();

        public <T> void put(Class<T> token, T value) {
            values.put(token, token.cast(Objects.requireNonNull(value)));
        }

        public <T> T get(Class<T> token) {
            return token.cast(values.get(token));
        }

        public <T> void put(TypeRef<T> token, T value) {
            values.put(token.type(), Objects.requireNonNull(value));
        }

        @SuppressWarnings("unchecked")
        public <T> T get(TypeRef<T> token) {
            return (T) values.get(token.type());
        }
    }

    // Kiểm tra toàn bộ cấu trúc Map<String, List<Integer>> tại runtime
    // trước khi nhận dữ liệu từ một nguồn chưa đáng tin.
    static Map<String, List<Integer>> checkedNested(Object candidate) {
        if (!(candidate instanceof Map<?, ?> map)) {
            throw new IllegalArgumentException("Map required");
        }

        Map<String, List<Integer>> result = new HashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            String key = String.class.cast(entry.getKey());

            if (!(entry.getValue() instanceof List<?> raw)) {
                throw new IllegalArgumentException("List required");
            }

            List<Integer> numbers = new ArrayList<>();
            for (Object element : raw) {
                numbers.add(Integer.class.cast(element));
            }

            result.put(key, List.copyOf(numbers));
        }

        return Map.copyOf(result);
    }

    public static void main(String[] args) {
        TypedStore store = new TypedStore();

        // Class<T> type tokens: kiểm tra được top-level runtime class.
        store.put(String.class, "Hello");
        store.put(Integer.class, 3);

        // TypeRef<T> type tokens: giữ type arguments lồng nhau.
        TypeRef<List<String>> labels =
                new TypeRef<List<String>>() {};
        TypeRef<List<Integer>> scores =
                new TypeRef<List<Integer>>() {};
        TypeRef<Map<String, List<Integer>>> nested =
                new TypeRef<Map<String, List<Integer>>>() {};

        store.put(labels, List.of("Java", "Kotlin"));
        store.put(scores, List.of(10, 20));

        store.put(
                nested,
                checkedNested(
                        Map.of(
                                "odd", List.of(1, 3),
                                "even", List.of(2, 4)
                        )
                )
        );

        System.out.println("greeting=" + store.get(String.class));
        System.out.println("count=" + store.get(Integer.class));
        System.out.println("labels=" + store.get(labels));
        System.out.println("scores=" + store.get(scores));
        System.out.println("odd=" + store.get(nested).get("odd"));

        // Type làm khóa theo cấu trúc, không theo identity của token wrapper.
        System.out.println(
                "sameType=" +
                labels.type().equals(
                        new TypeRef<List<String>>() {}.type()
                )
        );
        System.out.println(
                "differentType=" + labels.type().equals(scores.type())
        );
        System.out.println(
                "nestedCaptured=" +
                (nested.type() instanceof ParameterizedType)
        );

        // Một phần tử String sai vị trí số nguyên bị từ chối khi validate.
        try {
            checkedNested(Map.of("bad", List.of("wrong")));
        } catch (ClassCastException error) {
            System.out.println("invalid=ClassCastException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -Xlint:unchecked HeterogeneousStoreDemo.java
java HeterogeneousStoreDemo
~~~

Stdout chính xác:

~~~text
greeting=Hello
count=3
labels=[Java, Kotlin]
scores=[10, 20]
odd=[1, 3]
sameType=true
differentType=false
nestedCaptured=true
invalid=ClassCastException
~~~

Giải thích kết quả:

- Hai giá trị đơn giản được lưu bằng `String.class` và `Integer.class`, không cần ép kiểu thủ công khi đọc.
- Hai key `List<String>` và `List<Integer>` **khác nhau** dù đều có raw type List. Vì vậy danh sách chuỗi và số không ghi đè lẫn nhau.
- Token lồng nhau ghi nhận `Map<String, List<Integer>>`. Truy xuất khóa `"odd"` trả `List<Integer>` có giá trị `[1, 3]`.
- `sameType=true` cho thấy hai anonymous TypeRef khác nhau có thể giữ Type mô tả cùng `List<String>`.
- `differentType=false` vì `List<String>` không phải `List<Integer>`.
- `nestedCaptured=true` xác nhận token của Map lồng nhau được mô tả bởi `ParameterizedType`.
- `invalid=ClassCastException` xuất hiện trong **checkedNested**, khi `Integer.class.cast` gặp một String là `"wrong"`. Đây là kiểm tra runtime chủ động, **không phải kiểm tra tự động từ TypeRef**.

Ví dụ sử dụng `List.of` và `Map.copyOf` để các collection đầu ra không hỗ trợ sửa đổi qua những tham chiếu trả về thông thường. Điều này giảm nguy cơ dữ liệu bị biến đổi về sau, nhưng nếu dùng giá trị mutable được tạo từ nguồn khác, vẫn phải chú ý alias và các thao tác unchecked.

## 9. Kiểm tra sai kiểu ở compile time

Với token:

~~~java
TypeRef<List<String>> words =
        new TypeRef<List<String>>() {};
~~~

Lời gọi hợp lệ:

~~~java
store.put(words, List.of("Java", "Go"));
~~~

Lời gọi cố tình sai:

~~~java
// store.put(words, List.of(1, 2)); // Không thỏa List<String>.
~~~

Trong một bối cảnh method invocation thông thường với token có kiểu `TypeRef<List<String>>`, compiler sẽ kiểm tra argument danh sách có thể dùng như `List<String>` hay không. Không được giả định rằng kho tự động chuyển Integer thành String hoặc lọc phần tử sai.

Với nested token:

~~~java
TypeRef<Map<String, List<Integer>>> nested =
        new TypeRef<Map<String, List<Integer>>>() {};
~~~

Cách dùng đúng:

~~~java
store.put(nested, Map.of("scores", List.of(1, 2, 3)));
~~~

Dùng sai sẽ bị kiểm tra theo ràng buộc type parameter:

~~~java
// store.put(nested, Map.of("scores", List.of("bad")));
~~~

Các dòng có comment là **đoạn minh họa lỗi biên dịch**, không nằm trong chương trình chạy độc lập.

### Lỗ hổng không thể giải quyết chỉ bằng chữ ký generic

Một caller vẫn có thể phá kiểm tra kiểu bằng raw types hoặc unchecked casts:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafeInsert(TypedStore store, TypeRef<List<String>> key) {
    TypeRef raw = key;
    store.put(raw, List.of(123));
}
~~~

Ví dụ trên minh họa code cố ý không an toàn và chỉ biên dịch khi các class liên quan có thể truy cập tại vị trí đặt phương thức. Khi khôi phục thành `List<String>`, việc đọc phần tử như String có thể ném `ClassCastException`. Lý do: raw token đã bỏ ràng buộc generic, còn TypeRef chỉ giữ mô tả kiểu chứ không duyệt mọi phần tử của value.

Không sử dụng cách này trong ứng dụng thật. Khi tích hợp mã cũ, giữ unchecked cast trong một adapter được kiểm soát và validate dữ liệu trước khi đưa vào kho.

## 10. Runtime type validation cho cấu trúc lồng nhau

`Class.cast` có thể kiểm tra được một đối tượng top-level có phải String hay Integer. Nhưng `Map<String, List<Integer>>` chứa nhiều lớp kiểm tra:

1. Đối tượng ngoài cùng là Map.
2. Mọi **khóa** phải là String.
3. Mọi **giá trị** phải là List.
4. Mọi phần tử của mỗi List phải là Integer.
5. Nếu hệ thống từ chối null, phải áp chính sách cho map, key, list và từng phần tử.
6. Nếu muốn tránh thay đổi sau kiểm tra, nên tạo bản sao độc lập và hạn chế mutation.

Đó là lý do chương trình có `checkedNested(Object)` với `instanceof Map<?, ?>`, `instanceof List<?>`, `String.class.cast` và `Integer.class.cast`. Sau khi từng phần tử đã được kiểm tra, nó xây một `Map<String, List<Integer>>` mới.

Phương thức:

~~~java
static Map<String, List<Integer>> checkedNested(Object candidate)
~~~

có thể xem như một **ranh giới dữ liệu đáng tin**: nhận Object, kiểm tra cấu trúc, tạo giá trị có kiểu đã được xác minh, rồi mới đưa vào TypedStore.

**Chú ý:** ví dụ dùng `List.copyOf` và `Map.copyOf` nên **không chấp nhận null**; nếu nghiệp vụ có null hợp lệ, hãy thiết kế một bản kiểm tra và sao chép khác có chính sách null rõ ràng. Ngoài ra, validator này được viết cụ thể cho một cấu trúc; TypeRef không tự cung cấp một bộ validator tổng quát.

### Tại sao không dùng instanceof List<String>?

Java không cho kiểm tra đầy đủ tham số generic bằng:

~~~java
// if (candidate instanceof List<String>) { } // Không hợp lệ.
~~~

Cách dùng đúng ở bước đầu:

~~~java
if (candidate instanceof List<?> list) {
    for (Object value : list) {
        // Kiểm tra từng phần tử phù hợp với kiểu mong muốn.
    }
}
~~~

`List<?>` có thể kiểm tra ở runtime dưới dạng raw List, trong khi wildcard vẫn thể hiện sự không biết của kiểu phần tử ở mức source. Các type arguments như String không trở thành điều kiện runtime mà JVM tự kiểm định khi dùng `instanceof`.

## 11. Type token của nested generics và so sánh khóa

Với các token:

~~~java
TypeRef<List<String>> a = new TypeRef<List<String>>() {};
TypeRef<List<String>> b = new TypeRef<List<String>>() {};
TypeRef<List<Integer>> c = new TypeRef<List<Integer>>() {};
~~~

Ta thường có:

~~~java
a.type().equals(b.type()); // true
a.type().equals(c.type()); // false
~~~

Nếu kho sử dụng chính **Type** làm key, a và b truy cập cùng mục lưu bởi chúng mô tả cùng generic type. Điều này đúng với nhu cầu “một cấu trúc kiểu xác định là một khóa”.

Nhưng lưu ý hai trường hợp:

- Nếu dùng **chính đối tượng TypeRef** làm key mà không định nghĩa `equals/hashCode` theo `type()`, hai instance TypeRef khác nhau có thể không bằng nhau.
- Nếu nhiều giá trị khác nhau cần cùng kiểu, ví dụ hai danh sách List<String> ứng với “ngôn ngữ học” và “ngôn ngữ dịch”, **chỉ Type không đủ phân biệt**. Cần key kết hợp tên/định danh và Type, ví dụ `record TypedKey<T>(String name, Type type)` cùng API có kiểm tra kiểu. Không nên giả định một kho gắn khóa theo Type đáp ứng mọi trường hợp có nhiều bản ghi cùng kiểu.

Trong chương trình chính, `Map<Type,Object>` thể hiện rõ mô hình **mỗi Type có tối đa một giá trị**; lời gọi put kế tiếp với cùng Type sẽ thay thế value trước đó.

## 12. Khi super type token không ghi được kiểu cụ thể

Kỹ thuật đọc generic superclass không tự biến mọi type variable thành type argument runtime cụ thể.

Xét mẫu:

~~~java
static <X> TypeRef<List<X>> captureInGenericMethod() {
    return new TypeRef<List<X>>() {};
}
~~~

Phần Type được giữ có thể chứa **TypeVariable X**, vì khi javac biên dịch phương thức generic, X vẫn là biến kiểu. Gọi phương thức với String ở call site không tự tái tạo một class ẩn danh mới có `List<String>` cố định ở Reflection metadata.

Vì vậy, nếu hệ thống cần key chính xác `List<String>` hay `Map<String,List<Integer>>`, hãy tạo token ở nơi các type arguments **đã được viết cụ thể** hoặc sử dụng cơ chế xây dựng `Type` từ các token được cung cấp.

Một số thư viện xây dựng Type tokens hỗ trợ giải kiểu biến dựa trên context, wildcard, arrays và generic supertypes phức tạp. Bản TypeRef tối giản trong bài chỉ đủ để trình bày **anonymous subclass trực tiếp** với kiểu cụ thể; nó chưa thực hiện giải TypeVariable, kiểm tra generic owner type, canonicalization toàn diện hoặc validation runtime tổng quát.

Đừng hứa hẹn rằng `getGenericSuperclass()` luôn là ParameterizedType: một subclass raw, một lớp trung gian không generic hoặc cấu trúc kế thừa không phù hợp có thể làm phép kiểm tra thất bại. Constructor trong ví dụ chủ động ném lỗi nếu không gặp dạng đã dự kiến.

## 13. Những giới hạn an toàn của kho

### 13.1. Không chống được alias mutable chứa dữ liệu sai kiểu

Nếu ta lưu một `ArrayList<String>` mutable, mã khác giữ tham chiếu đến cùng object có thể làm nó thay đổi; những mã raw/unchecked có thể thêm dữ liệu không đúng kiểu.

~~~java
List<String> mutable = new ArrayList<>(List.of("A"));
store.put(new TypeRef<List<String>>() {}, mutable);

// Nếu bên khác dùng raw alias để thêm Integer, bất biến bị phá.
// Cách khắc phục: sao chép và xác thực ở ranh giới cần tin cậy.
~~~

Trong bản demo, các list từ `List.of` và bản sao từ `List.copyOf` không cho sửa đổi thông thường. Nhưng kho generic tối giản không tự chuyển mọi collection caller truyền vào thành immutable.

### 13.2. TypeRef ghi lại mô tả kiểu, không là validator

Hai câu sau hoàn toàn khác nhau:

- “Tôi có token đại diện cho `List<String>`.”
- “Tôi đã xác minh giá trị runtime thực sự là List chỉ chứa String.”

Câu đầu là metadata; câu sau yêu cầu **duyệt/kiểm tra dữ liệu** hoặc đặt niềm tin vào một API có bất biến được kiểm soát.

### 13.3. Type erasure vẫn tồn tại

Trình biên dịch có thể chèn cast ở nơi nhận kết quả từ generic method `get`. Với `List<String>`, runtime có thể kiểm tra top-level List nhưng không xác minh toàn bộ các phần tử thông qua cast của caller. Lỗi có thể xuất hiện khi đọc phần tử như String.

### 13.4. Missing key và null không đồng nghĩa vấn đề kiểu

`get` trong demo trả null cho key không tồn tại, còn `put` từ chối null để tránh phân biệt hai trạng thái. Một hệ thống thực tế nên quyết định rõ hành vi khi key vắng: Optional, exception, default value hoặc API contains. Đừng dùng cast hay raw types để giải quyết bài toán missing keys.

### 13.5. Thread safety và versioning

`HashMap` trong demo **không thread-safe** khi nhiều thread ghi hoặc đồng thời đọc/ghi. Nếu kho dùng trong môi trường concurrent, cần cơ chế đồng bộ thích hợp hoặc `ConcurrentHashMap` kèm thiết kế về atomic operations và publication.

Nếu dùng Type của Reflection làm key trong dữ liệu persist, không nên mặc định `Type.getTypeName()` là một định dạng serialization ổn định qua refactor, classloader hoặc thay đổi tên package. Persistence cần schema và versioning riêng.

## 14. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng `List.class` để phân biệt List<String> và List<Integer> | Type arguments không có trong Class literal | Dùng TypeRef và `ParameterizedType` làm key. |
| Dùng raw `TypeRef` để gọi put | Mất ràng buộc T giữa token và value | Giữ `TypeRef<T>`, không ép raw. |
| Dùng token nhưng tin rằng JVM tự kiểm tra phần tử lồng nhau | Type erasure; token là metadata | Viết validator/checking adapter. |
| Dùng `Map<Type,Object>` rồi trả Object công khai | Caller phải cast thủ công | Bọc bằng phương thức generic get/put với token. |
| Lưu dữ liệu mutable rồi tin kho luôn đúng | Alias có thể thay đổi giá trị | Sao chép/đóng băng khi thích hợp; giới hạn lối ghi. |
| Dùng TypeRef như key theo identity | Hai token cùng type có thể là hai object khác nhau | Key bằng `type()` hoặc tự định nghĩa equals/hashCode. |
| Tạo `new TypeRef() {}` | Raw subclass không giữ type argument T | Viết `new TypeRef<List<String>>() {}`. |
| Capturing `List<X>` trong generic method rồi mong X biến thành String | Reflection vẫn có TypeVariable X | Cấp token cụ thể từ caller, hoặc resolve biến kiểu chính thức. |
| Muốn lưu hai giá trị khác nhau cùng List<String> | Key chỉ bằng Type bị trùng | Dùng typed key có định danh cộng Type. |
| Trộn null và missing entry | API không nêu hợp đồng null | Chọn Optional/exception/contains và thống nhất chính sách. |

### Sai kiểu được compiler phát hiện trước

Ví dụ minh họa:

~~~java
TypeRef<Map<String, List<Integer>>> matrix =
        new TypeRef<Map<String, List<Integer>>>() {};

// store.put(matrix, Map.of("x", List.of("not a number")));
// Phải sửa dữ liệu thành List<Integer>.
~~~

### Sai kiểu compiler không thể biết vì đầu vào là Object

~~~java
Object externalData = receiveFromExternalSource();

// Không được ép ngay externalData thành Map<String,List<Integer>>.
Map<String, List<Integer>> checked = checkedNested(externalData);
store.put(matrix, checked);
~~~

`receiveFromExternalSource()` là tên placeholder của một API nguồn dữ liệu, không phải chương trình Java độc lập. Điểm học tập là phải **kiểm tra và chuyển** Object trước khi gắn nó với token generic có ý nghĩa nghiệp vụ.

## 15. Hướng phát triển một kho nhiều kiểu thực tế

Tùy yêu cầu, có thể phát triển từ mẫu demo:

1. **TypedKey<T>** có id và `Type`: phân biệt các vai trò khác nhau dù cùng kiểu cấu trúc.
2. **Validator<T>** đi cùng key: kiểm tra runtime tại put, đặc biệt cho JSON, config và dữ liệu từ API ngoài.
3. **Bản sao dữ liệu/immutability**: không để alias mutable hoặc raw API phá bất biến sau khi kiểm tra.
4. **Missing-value contract**: chọn Optional, exception hoặc giá trị mặc định được định nghĩa rõ.
5. **Quy tắc kế thừa/variance**: xem rõ khi nào chấp nhận subtype, wildcard hay đúng bằng kiểu token; không dùng unchecked cast để giả lập covariance.
6. **Thread safety**: dùng đồng bộ, immutable snapshot hoặc concurrent map nếu có truy cập song song.
7. **Kiểm thử âm tính**: xem các lệnh put sai kiểu có bị compiler chặn và các nguồn dữ liệu không đúng cấu trúc có bị validator từ chối.
8. **Định dạng khi lưu trữ**: schema và codec được phiên bản hóa nếu cần ghi/đọc dữ liệu ra ngoài JVM.

Các cải tiến đó giải quyết những yêu cầu ngoài phạm vi kho demo; **TypeRef chỉ là thành phần nhận diện kiểu**, không thay thế validation, authorization, concurrency control hay persistence schema.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao kho `Map<Class<?>,Object>` không thể dùng `List.class` để phân biệt List<String> và List<Integer>?

**Đáp án:** Cả hai có cùng runtime raw class List. Tham số generic không có trong `List.class`, nên chúng tạo cùng một key.

**Câu 2.** Hai token `new TypeRef<List<String>>() {}` được tạo riêng có thể dẫn đến cùng mục lưu trong Map<Type,Object> không?

**Đáp án:** Có. Khi `type()` trả hai `ParameterizedType` mô tả cùng List<String>, chúng có thể so sánh bằng `equals` và được dùng làm cùng key. Đây không phải so sánh identity của hai wrapper TypeRef.

**Câu 3.** Vì sao `TypeRef<Map<String,List<Integer>>>` không tự bắt được phần tử String trong List<Integer> ở runtime?

**Đáp án:** TypeRef là Reflection metadata của cấu trúc kiểu. Do erasure, JVM không thực hiện kiểm tra mọi phần tử lồng nhau chỉ dựa trên TypeRef. Cần validator duyệt Map, List và từng phần tử.

**Câu 4.** Một typed store vẫn dùng Map<Type,Object>. Điều đó có mâu thuẫn với việc API là generic không?

**Đáp án:** Không. Kho cần chỗ chứa chung cho các kiểu khác nhau; các phương thức generic ràng buộc token và dữ liệu ở compile time. An toàn của cast nội bộ dựa trên bất biến ghi đúng kiểu và kiểm soát nguồn dữ liệu.

**Câu 5.** `new TypeRef<List<X>>() {}` bên trong generic method có luôn đại diện cho List<String> nếu caller sử dụng X=String không?

**Đáp án:** Không. Generic superclass có thể chứa TypeVariable X, vì mã anonymous subclass đã được biên dịch khi X chưa có kiểu cụ thể. Cần token cụ thể hoặc giải biến kiểu theo ngữ cảnh.

**Câu 6.** Làm thế nào để lưu hai danh sách List<String> có cùng kiểu nhưng vai trò khác nhau?

**Đáp án:** Tạo key kết hợp một tên/định danh và Type thay vì chỉ dùng Type. API vẫn phải giữ liên hệ giữa `TypedKey<T>` với value T.

**Câu 7.** Trong ví dụ, chuỗi “wrong” bị phát hiện ở đâu?

**Đáp án:** Trong `checkedNested` khi duyệt phần tử của List và gọi `Integer.class.cast(element)`, không phải do `get` hoặc TypeRef tự kiểm tra.

**Câu 8.** Nếu kho dùng trong multi-thread environment, thay HashMap bằng ConcurrentHashMap đã đủ để mọi vấn đề an toàn được giải quyết chưa?

**Đáp án:** Chưa. ConcurrentMap hỗ trợ truy cập đồng thời vào chính map, nhưng vẫn cần xử lý immutability của giá trị, hợp đồng key/value, validation và các thao tác nghiệp vụ nhiều bước nếu muốn atomicity.

## 17. Ghi nhớ

Một kho nhiều kiểu kiểu an toàn ở **mức API** dùng ràng buộc `<T> put(Token<T>, T)` và `<T> T get(Token<T>)` để nối kiểu key với value.

- **`Class<T>`** phù hợp với các lớp runtime có thể kiểm tra trực tiếp như String/Integer.
- **`TypeRef<T>` dựa trên `ParameterizedType`** giúp phân biệt `List<String>`, `List<Integer>` và `Map<String,List<Integer>>` như các key có cấu trúc.
- **`Map<Type,Object>`** là cơ chế lưu hỗn hợp; cast nội bộ cần một bất biến ghi đúng kiểu và không nên phơi raw storage ra caller.
- **Metadata không bằng validation**: nguồn dữ liệu lồng nhau, raw alias hoặc unchecked cast vẫn có thể phá kiểu, nên cần kiểm tra và sao chép ở ranh giới dữ liệu phù hợp.
- **Key chỉ bằng Type** chỉ lưu được một giá trị cho mỗi cấu trúc kiểu; khi cần nhiều bản ghi cùng kiểu, hãy thêm định danh mang nghĩa nghiệp vụ.

Nắm được ranh giới giữa **compile-time generic safety**, **Reflection type metadata** và **runtime validation** là điều quan trọng nhất khi thiết kế kho heterogeneous trong Java.
