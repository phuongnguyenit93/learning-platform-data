# `Class<T>` như thông tin kiểu được truyền tường minh trong Java Generics

## 1. Khi `T` ở compile time chưa đủ cho runtime

Trong Java, một type variable như `T` giúp compiler kiểm tra và liên kết kiểu đầu vào, đầu ra. Ví dụ:

~~~java
static <T> T identity(T input) {
    return input;
}
~~~

Lời gọi `identity("Java")` trả một giá trị có kiểu tĩnh String, còn `identity(7)` trả Integer. Không cần một runtime token nào vì thuật toán chỉ chuyển tiếp tham chiếu đã được kiểm tra ở compile time.

Nhưng nếu phương thức nhận một `Object` từ API legacy, cấu hình hoặc reflection và phải **xác minh class do người gọi yêu cầu khi chương trình đang chạy**, generic type variable `T` không tự cung cấp class ấy.

~~~java
// CỐ Ý SAI theo mục đích kiểm tra runtime:
static <T> T unchecked(Object input) {
    return (T) input; // Cảnh báo unchecked; không biết class cụ thể của T.
}
~~~

Trong mô hình **type erasure**, `T` có thể bị xóa thành Object hoặc erasure của bound đầu tiên. Không có runtime class riêng cho mỗi lời gọi `T=String` hay `T=Integer` để câu `(T) input` thực sự chứng minh đúng kiểu cụ thể.

Thiết kế giải quyết được nhu cầu này bằng cách để **caller truyền một đối tượng Class**:

~~~java
static <T> T checked(Object input, Class<T> expected) {
    return expected.cast(input);
}
~~~

Caller:

~~~java
String word = checked("Java", String.class);
Integer number = checked(42, Integer.class);
~~~

Ở source, `Class<T>` liên kết token với kết quả `T`. Ở runtime, `expected.cast` sử dụng class thật được cung cấp để kiểm tra object.

**Đây là bản chất của class token:** `Class<T>` đại diện cho một class/interface/array type có runtime identity cụ thể; nó không làm Java Generics được reify toàn bộ.

## 2. Phân biệt `T`, `Class<T>`, `Class<?>` và `Type`

| Ký hiệu | Vai trò | Khi nào hữu ích |
| --- | --- | --- |
| `<T>` | Khai báo type parameter. | Khi API cần giữ mối quan hệ kiểu giữa các vị trí. |
| `T` | Type variable trong method/class generic. | Compile-time type checking, suy luận kiểu. |
| `Class<T>` | Class token có type argument liên kết với T. | Kiểm tra class của Object hoặc class được chọn tại runtime. |
| `Class<?>` | Class token nhưng type argument chưa biết. | Đọc metadata class/plugin mà chưa được xác minh kiểu cụ thể. |
| `Class<? extends Base>` | Token thuộc Base hoặc subtype. | API dùng class của một implementation Base. |
| `java.lang.reflect.Type` | Giao diện mô tả kiểu khai báo, có thể chứa type arguments lồng nhau. | Phân tích `List<String>`, `Map<String,List<Integer>>` từ metadata. |

Tương ứng:

~~~java
Class<String> textToken = String.class;
Class<Integer> numberToken = Integer.class;
Class<?> unknown = textToken;
Class<? extends Number> numeric = Integer.class;
~~~

`Class<T>` vẫn theo **invariance**:

~~~java
// Không hợp lệ:
// Class<CharSequence> parent = String.class;

// Hợp lệ:
Class<? extends CharSequence> parent = String.class;
~~~

Một runtime Class object **không phải** một class sinh riêng cho mỗi parameterized type. `Class<String>` mô tả token của class String. Nó **không** có ý nghĩa rằng mọi `ArrayList<String>` instance đều mang sẵn token của String.

### Những phép thử bị cấm trên type variable

~~~java
// Các biểu thức sau cố ý không biên dịch khi T là type variable:
// T.class
// new T()
// new T[10]
// input instanceof T
~~~

Những cú pháp này đòi một runtime type theo cách không thể rút trực tiếp từ `T` chưa được reify. Truyền `Class<T>` nếu cần một runtime class; truyền factory nếu cần tạo object.

## 3. Ranh giới sử dụng phù hợp: dữ liệu ngoài dạng `Object`

Một ví dụ thực tế là đọc cấu hình hoặc data đã giải mã từ map:

~~~java
Map<String, Object> values = new HashMap<>();
values.put("user", "Ada");
values.put("count", 17);
~~~

Một typed API cần nói rõ:
1. Key có tồn tại không?
2. Null có được chấp nhận không?
3. Value có đúng class mà caller yêu cầu không?
4. Nếu đúng, kết quả sẽ mang kiểu tĩnh nào?

~~~java
static <T> T require(
        Map<String, ?> values,
        String key,
        Class<T> expected) {

    Objects.requireNonNull(expected, "expected");

    if (!values.containsKey(key)) {
        throw new IllegalArgumentException("missing: " + key);
    }

    Object candidate = Objects.requireNonNull(
            values.get(key), "null: " + key);

    return expected.cast(candidate);
}
~~~

Caller:

~~~java
String user = require(values, "user", String.class);
Integer count = require(values, "count", Integer.class);
~~~

Nhờ cùng type parameter T trong `Class<T>` và return type, caller nhận kiểu được compiler kiểm tra mà không cần cast thủ công.

Các lỗi được phân tách theo hợp đồng của **API minh họa**:
- Thiếu key → IllegalArgumentException.
- Có key nhưng null → NullPointerException.
- Đúng key nhưng sai class → ClassCastException.
- Đúng kiểu → trả giá trị T.

**Lưu ý:** `Class.cast(null)` tự nó trả null. Chính `Objects.requireNonNull` tạo null policy trong ví dụ, không phải `Class<T>` tự cấm null.

### Vì sao `(T) candidate` không thay thế `expected.cast(candidate)`?

Cast tới type variable `T` sau erasure không có sẵn class String hoặc Integer để kiểm tra chính xác. Một sai kiểu có thể chỉ xuất hiện ở caller khi kết quả được dùng như String. `Class.cast` dùng token thật được truyền vào để kiểm tra và báo lỗi tại boundary, gần nguồn dữ liệu sai hơn.

Cũng đừng nhầm cast với **chuyển đổi dữ liệu**: `String.class.cast(17)` không tự tạo chuỗi `"17"`. Nếu cần parser/converter, dùng `String.valueOf`, `Integer.parseInt` hoặc logic nghiệp vụ riêng.

## 4. Generic object chủ động giữ token để kiểm soát invariant

Một generic object có thể nhận dữ liệu từ cả nguồn typed và nguồn Object. Nếu cần chấp nhận input chưa định kiểu, token được lưu ở object là ràng buộc thực tế:

~~~java
static final class Slot<T> {
    private final Class<T> token;
    private T value;

    Slot(Class<T> token) {
        this.token = Objects.requireNonNull(token);
    }

    void setUnknown(Object input) {
        value = token.cast(input);
    }

    T get() {
        return value;
    }
}
~~~

Cách gọi:

~~~java
Slot<String> slot = new Slot<>(String.class);
slot.setUnknown("ready");

try {
    slot.setUnknown(123);
} catch (ClassCastException ex) {
    // Input không thuộc runtime class String.
}
~~~

Mỗi instance Slot có **runtime class giống nhau** về mặt generic class, nhưng instance cụ thể có thể giữ **token khác nhau** do caller truyền tới. Token không phải dữ liệu JVM tự suy ra từ `Slot<String>`.

Bởi phép cast được thực hiện **trước** lệnh gán field hoàn tất, lỗi ở `setUnknown(123)` không thay đổi giá trị `"ready"`. Đây là một hậu điều kiện phù hợp để test.

Đừng sửa mọi setter thành `setUnknown(Object)` chỉ vì có class token: setter `void set(T value)` vẫn là thiết kế tốt hơn khi API chỉ nhận callers typed bình thường. Token hữu ích ở những điểm **cố ý mở dữ liệu chưa biết kiểu**.

## 5. Chương trình Java 17 hoàn chỉnh: kiểm tra, giữ token, xác minh danh sách

Lưu thành **ClassTokenFoundations.java**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

public class ClassTokenFoundations {
    static <T> T require(
            Map<String, ?> values,
            String key,
            Class<T> expected) {

        Objects.requireNonNull(expected, "expected");

        if (!values.containsKey(key)) {
            throw new IllegalArgumentException("missing: " + key);
        }

        Object candidate = Objects.requireNonNull(
                values.get(key), "null: " + key);

        return expected.cast(candidate);
    }

    static <T> List<T> checkedCopy(
            List<?> source,
            Class<T> expected) {

        List<T> output = new ArrayList<>();

        for (Object value : source) {
            output.add(expected.cast(
                    Objects.requireNonNull(value, "null element")));
        }

        return List.copyOf(output);
    }

    static <T> T create(Supplier<? extends T> factory) {
        return factory.get();
    }

    static final class Slot<T> {
        private final Class<T> token;
        private T value;

        Slot(Class<T> token) {
            this.token = Objects.requireNonNull(token);
        }

        void setUnknown(Object value) {
            this.value = token.cast(value);
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Map<String, Object> config = new HashMap<>();
        config.put("user", "Ada");
        config.put("count", 17);

        System.out.println(
                "user=" + require(config, "user", String.class));
        System.out.println(
                "count=" + require(config, "count", Integer.class));

        try {
            require(config, "count", String.class);
        } catch (ClassCastException ex) {
            System.out.println("bad-token=" +
                    ex.getClass().getSimpleName());
        }

        Slot<String> message = new Slot<>(String.class);
        message.setUnknown("ready");

        try {
            message.setUnknown(12);
        } catch (ClassCastException ex) {
            System.out.println("slot-reject=" +
                    ex.getClass().getSimpleName());
        }

        System.out.println("slot=" + message.get());
        System.out.println("verified=" +
                checkedCopy(List.of("a", "b"), String.class));

        try {
            checkedCopy(List.of("a", 8), String.class);
        } catch (ClassCastException ex) {
            System.out.println("list-reject=" +
                    ex.getClass().getSimpleName());
        }

        System.out.println(
                "nullCast=" + (String.class.cast(null) == null));
        System.out.println(
                "nullInstance=" + String.class.isInstance(null));
        System.out.println(
                "subtype=" +
                Number.class.isAssignableFrom(Integer.class));
        System.out.println(
                "factory=" + create(
                        () -> new StringBuilder("made")));
        System.out.println(
                "sameRuntime=" +
                (new ArrayList<String>().getClass()
                        == new ArrayList<Integer>().getClass()));
    }
}
~~~

Biên dịch/chạy không cần thư viện ngoài JDK:

~~~bash
javac --release 17 -Xlint:all ClassTokenFoundations.java
java ClassTokenFoundations
~~~

**Stdout đã kiểm chứng:**

~~~text
user=Ada
count=17
bad-token=ClassCastException
slot-reject=ClassCastException
slot=ready
verified=[a, b]
list-reject=ClassCastException
nullCast=true
nullInstance=false
subtype=true
factory=made
sameRuntime=true
~~~

**Đọc kết quả theo các mốc kiểm tra:**

- `bad-token`: map giữ Integer, nhưng caller yêu cầu String; token phát hiện mismatch ngay tại boundary.
- `slot-reject`/`slot=ready`: Token ở Slot<String> chặn ghi sai và giữ hậu điều kiện.
- `verified`/`list-reject`: Khi nguồn là List<?> chưa biết element type, kiểm tra **từng phần tử** theo token rồi copy mới là cách bảo vệ kết quả.
- `nullCast`/`nullInstance`: API null behaviors khác nhau; thiết kế null policy riêng.
- `subtype`: `Number.class.isAssignableFrom(Integer.class)` đúng chiều assignability.
- `factory`: Supplier tạo object mà không cần reflection.
- `sameRuntime`: hai cách tham số hóa ArrayList trực tiếp có cùng runtime class, không reify String/Integer.

## 6. Giới hạn: `List.class` chỉ kiểm tra container, không kiểm tra elements

Java cho phép:

~~~java
List<String> words = List.of("a", "b");
List<Integer> numbers = List.of(1, 2);

boolean a = List.class.isInstance(words);
boolean b = List.class.isInstance(numbers);
~~~

Cả `a` và `b` đều `true`. Runtime token `List.class` chỉ nhận diện loại container, không biết các phần tử theo generic argument String hay Integer.

Không thể viết:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
// Class<List<String>> token = List<String>.class;
// boolean ok = someObject instanceof List<String>;
~~~

`List<String>` là **non-reifiable parameterized type**; không có class literal riêng cho nó.

Để xác thực dữ liệu đầu vào `List<?>` theo element type, dùng vòng lặp:

~~~java
static <T> List<T> checkedCopy(
        List<?> source, Class<T> type) {

    List<T> result = new ArrayList<>();

    for (Object element : source) {
        result.add(type.cast(
                Objects.requireNonNull(element)));
    }

    return List.copyOf(result);
}
~~~

Phương thức này xác minh từng element trực tiếp và tạo một list mới. `List.copyOf` từ chối null, trả list không sửa được qua các mutation APIs thông thường; nhưng đây là **shallow copy** nếu elements vốn mutable.

Với nested generic types như `List<List<String>>`, một token `List.class` chỉ kiểm tra raw List của mỗi phần tử, **không** đi tới Strings ở tầng sâu. Những cấu trúc nested cần validator/decoder có schema thích hợp.

### `Collections.checkedList` kiểm tra một kiểu khác của thao tác

JDK có:

~~~java
List<String> checked = Collections.checkedList(
        new ArrayList<>(), String.class);
~~~

Wrapper dùng token String để kiểm tra **mutation đi qua wrapper**. Nó không tự xác thực hết phần tử đã có khi tạo wrapper và không thể chặn mutation qua một alias có thể viết trực tiếp lên backing list.

- **Validated copy:** phù hợp với dữ liệu bên ngoài mà bạn muốn kiểm tra toàn bộ một lần và sở hữu bản copy độc lập.
- **Checked wrapper:** phù hợp với nhu cầu chặn write sai kiểu qua một view có class token.

Đừng nhầm hai công cụ này với reification toàn bộ generic type arguments.

## 7. Khi nào `Class<T>` không cần thiết?

Một generic method có thể không hỏi bất kỳ runtime type nào:

~~~java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty");
    }
    return values.get(0);
}
~~~

Không cần `Class<T>` vì compiler có đủ quan hệ giữa type argument của List và kết quả T.

Tương tự, nếu caller **biết cách tạo object**, một factory callback thường đơn giản hơn:

~~~java
static <T> T create(
        java.util.function.Supplier<? extends T> factory) {

    return factory.get();
}

// StringBuilder builder = create(StringBuilder::new);
~~~

Nếu class thực sự chỉ được chọn ở runtime và phải gọi constructor bằng reflection, `Class<T>` có thể phù hợp:

~~~java
static <T> T createByClass(Class<T> type)
        throws ReflectiveOperationException {

    return type.getDeclaredConstructor().newInstance();
}
~~~

Nhưng constructor không đối số phải tồn tại, truy cập được theo access/module rules và class phải có thể khởi tạo. Một `Class<T>` không chứng minh điều đó và không tự vượt được quyền truy cập reflection.

### Chọn theo nhiệm vụ

| Nhiệm vụ | Tham số phù hợp |
| --- | --- |
| Chỉ bảo toàn cùng T giữa input/output | Generic `<T>` thông thường |
| Runtime yêu cầu object thuộc class caller chỉ định | `Class<T>` |
| Caller cung cấp cách tạo instance | `Supplier<? extends T>` |
| Runtime chọn class rồi kiểm tra constructor/plugin | `Class<?>`, bước kiểm tra subtype, reflection |
| Cần nested generic declaration `Map<String,List<Integer>>` | `java.lang.reflect.Type` / type reference / schema |

## 8. Thao tác trên class token khác với thao tác trên object

Ba câu hỏi thường gặp:

~~~java
Class<?> pluginClass = Class.forName(className);
~~~

1. “**Object** có thuộc class X không?” — dùng `X.isInstance(object)`, hoặc `X.cast(object)` khi cần typed result.
2. “**Class** runtime này có phải subtype của Base không?” — dùng `pluginClass.asSubclass(Base.class)` để lấy token có bound đúng nếu hợp lệ, hoặc `Base.class.isAssignableFrom(pluginClass)` để hỏi boolean.
3. “Class này có thể **tạo instance** bằng constructor không?” — kiểm tra constructor/access và xử lý reflection exceptions riêng; `asSubclass` không tạo object.

`asSubclass` làm việc với **class token**, không cast một instance. `Class.cast` làm việc với **object thực**, không phát hiện nested generic arguments.

Khi class name đến từ plugin/config không tin cậy, phải có chính sách allowlist, class loader, module access và kiểm soát side effects. Type safety không đồng nghĩa security policy.

### `Class<?>` là loại thông tin chưa biết, không phải raw `Class`

Nếu chưa biết type argument ở compile time, dùng `Class<?>`. Không dùng raw `Class` chỉ để thoát khỏi type checker. Nếu API cần nói “class của subtype Number”, dùng `Class<? extends Number>`; `Class<Number>` sẽ không tự chấp nhận `Integer.class` do generic invariance.

## 9. `Class<T>` khác metadata `Type`

Giả sử một field được khai báo:

~~~java
class Model {
    List<String> names;
}
~~~

Reflection có hai góc nhìn:

~~~java
Field f = Model.class.getDeclaredField("names");

Class<?> erasedClass = f.getType();
java.lang.reflect.Type declared = f.getGenericType();
~~~

`getType()` trả runtime/erased class List. `getGenericType()` có thể trả `ParameterizedType` cho declaration `List<String>` khi generic Signature metadata hiện diện.

`Type` là interface chung được các cấu trúc như `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType` dùng để mô tả declaration. Nó **không** có method `cast` giống `Class<T>` cho tất cả các loại type.

Một super type token như `new TypeRef<List<String>>() {}` có thể lưu metadata được khai báo trong một anonymous subclass. Điều đó **không** khiến object `new ArrayList<String>()` tự tiết lộ `String` ở `getClass()`, cũng không làm một `T` chưa bound trong generic method tự resolve.

Khi xây schema/serializer, cần phân nhánh đúng loại `Type`, giải các bindings trong hierarchy khi có và thực hiện validation dữ liệu riêng. Bài `Class<T>` này chỉ giúp xác định **khi nào lớp runtime cụ thể là đủ và khi nào không**.

## 10. Ba sai lầm về type safety ở runtime

### Sai lầm A — “`Class.cast` biến kiểu dữ liệu”

Không. `Integer.class.cast("17")` không parse chuỗi "17" thành số; nếu kiểu thực không đúng, ném ClassCastException. Conversion cần parser/mapper thích hợp.

### Sai lầm B — “`Class<T>` biết generic arguments của từng collection”

Không. `List.class` không biết một ArrayList được khai báo thành `List<String>` hay `List<Integer>` trong source. Cần Type metadata từ declaration và/hoặc validation từng element.

### Sai lầm C — “Lấy được `Class<?>` từ string class name là đã tin cậy”

Không. Hai class trùng tên do class loaders khác nhau có thể không phải cùng runtime identity. Và class không tin cậy có thể có constructor/initialization side effects. Sử dụng Class identity và subtype relationship thực, cùng allowlist/policy phù hợp.

## 11. Câu hỏi và bài tập kiểm tra hiểu biết

**1.** `String.class` có type gì ở source?

**Đáp án:** `Class<String>`, là class token truyền được vào generic method nhận `Class<T>`.

**2.** `Class<String>` gán được cho `Class<CharSequence>` không?

**Đáp án:** Không, vì generic invariance. Dùng `Class<? extends CharSequence>` nếu muốn chấp nhận các token subtype như String.class.

**3.** Có thể viết `T.class` trong một generic method không?

**Đáp án:** Không. Type variable T không tự mang runtime class literal. Hãy nhận token nếu thật sự cần runtime class.

**4.** `String.class.cast(null)` và `String.class.isInstance(null)` trả gì?

**Đáp án:** Lần lượt null và false. API phải có null policy nếu không muốn nhận null.

**5.** Một map có `count=17`, caller yêu cầu `String.class`. Điều gì xảy ra ở `require`?

**Đáp án:** ClassCastException tại runtime class check. Class.cast không đổi Integer thành chuỗi.

**6.** Nếu object thật là `List<Integer>`, `List.class.isInstance(object)` có true không?

**Đáp án:** Có. Nó chỉ kiểm tra object thực hiện List, không kiểm tra Integer type argument.

**7.** Làm sao đưa một `List<?>` từ nguồn chưa tin cậy vào API trả `List<String>`?

**Đáp án:** Kiểm tra từng phần tử với String.class, tạo typed copy có chính sách null/mutability/ownership rõ ràng.

**8.** Có `Class<T>` thì `new T()` hợp lệ chưa?

**Đáp án:** Chưa. Dùng reflection với constructor phù hợp hoặc factory callback. Không phải class nào cũng có constructor không đối số hay quyền truy cập cần thiết.

**9.** `Supplier<T>` có ưu điểm gì khi caller biết cách tạo object?

**Đáp án:** Không cần reflection, constructor được compiler kiểm tra tại caller và API đơn giản hơn.

**10.** `getGenericType()` trên field khai báo List<String> có chứng minh object list hiện chỉ chứa String không?

**Đáp án:** Không. Đó là declaration metadata, không phải runtime payload validation.

**11.** Muốn giới hạn một Class<?> do plugin loader trả về thành một subtype của Service thì làm sao?

**Đáp án:** Dùng `discovered.asSubclass(Service.class)` hoặc kiểm tra equivalent, rồi xem xét constructor/access/security riêng.

**12.** Vì sao không so tên class bằng String như bằng chứng subtype?

**Đáp án:** Runtime type identity và subtype còn phụ thuộc class loader và quan hệ kế thừa thật, không chỉ tên nhị phân.

## 12. Checklist thiết kế và kết luận

- [ ] Chỉ đưa `Class<T>` vào API khi **runtime thực sự cần class object**.
- [ ] Tách generic type variable `T` khỏi Class token caller cung cấp.
- [ ] Đặt class check ngay ở boundary nhận `Object`/legacy data.
- [ ] Xác định chính sách key thiếu, null, sai class và conversion.
- [ ] Dùng `Class<?>` khi type argument chưa biết, tránh raw `Class`.
- [ ] Dùng bounded class token nếu cần giới hạn class subtype.
- [ ] Với `List<?>`, `List.class` không xác thực type của elements.
- [ ] Chọn validated copy hoặc checked wrapper theo nhiệm vụ, kiểm soát aliases.
- [ ] Nếu chỉ cần factory, cân nhắc `Supplier<? extends T>`.
- [ ] Nếu cần nested type declarations, dùng `Type`/TypeRef và logic giải/kiểm tra riêng.
- [ ] Không suy generic argument từ `obj.getClass()` ở một instance collection thông thường.
- [ ] Khi load runtime class, kiểm tra class loader, access, trust và subtype contract.

**Ghi nhớ:** `Class<T>` là cầu nối **tường minh** giữa generic type relationship mà javac kiểm tra và class cụ thể mà JVM có thể kiểm tra. Nó không “giải mã lại” các generic arguments đã erasure, không làm `T.class` hợp lệ và không tự validate collections lồng nhau. Dùng token đúng **tại những nơi dữ liệu chưa typed**, còn giữ các generic APIs thông thường ở những nơi compiler đã bảo đảm đầy đủ hợp đồng.

### Tài liệu chuẩn

- [Java 17 Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java 17 Type API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html)
- [JLS `4.6 Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6)
- [JLS `4.7 Reifiable types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7)
