# Thiết kế kho lưu trữ nhiều kiểu với `Class<T>` làm khóa trong Java Generics

## 1. Bài toán: một kho chứa nhiều kiểu dữ liệu nhưng API vẫn an toàn kiểu

Một cấu trúc như `Map<String, Object>` có thể chứa tên người dùng kiểu `String`, số lần thử kiểu `Integer`, hoặc thời gian chờ kiểu `Duration`. Tuy nhiên, API đọc thường phải ép kiểu:

```java
Object raw = values.get("retryCount");
Integer retries = (Integer) raw;
```

Đây là đoạn minh họa, giả định có biến `values`. Compiler không thể chứng minh `"retryCount"` luôn được liên kết với `Integer`. Nếu mã khác đặt `String` vào cùng khóa, lời ép kiểu có thể ném `ClassCastException` lúc chạy.

Một thiết kế khác dùng **runtime class token `Class<T>` như khóa**:

```java
registry.put(String.class, "Java");
registry.put(Integer.class, 3);

String language = registry.get(String.class);
Integer retries = registry.get(Integer.class);
```

Khi caller đưa `String.class`, compiler biết giá trị tương ứng cần có kiểu `String`. Với `Integer.class`, compiler biết giá trị cần là `Integer`. Bên trong vẫn có thể dùng một `Map<Class<?>, Object>`, nhưng **public API generic** kết nối kiểu của key và value.

Thiết kế này thường được gọi là **typesafe heterogeneous container**: một container không khai báo một type parameter chung như `Box<T>`, mà **mỗi entry có một mối quan hệ kiểu riêng** thông qua khóa lớp.

Điểm cốt lõi:

> Không phải `Map<Class<?>, Object>` tự an toàn kiểu. Tính an toàn đến từ việc chỉ cho phép truy cập map qua API như `<T> void put(Class<T>, T)` và `<T> T get(Class<T>)`, đồng thời dùng `Class.cast` để giữ ràng buộc ở runtime.

Bài này xây một registry từ mức tối thiểu tới thiết kế thực dụng: type tokens, `Class.cast`, `null`, thay thế giá trị, subclass/interface, identity của key, giới hạn với `List<String>`, đồng thời, khả năng thay đổi của dữ liệu, kiểm thử và lỗi thường gặp. Các chương trình hoàn chỉnh sử dụng Java 17 trở lên.

## 2. Kiểu của key và kiểu của value liên hệ thế nào?

Xét method:

```java
public <T> void put(Class<T> type, T value)
```

`T` là một **method type parameter**. Nó xuất hiện đồng thời ở key và value:

- `Class<T>` cho biết một class token cụ thể đang được dùng.
- `T value` nói giá trị phải tương thích với kiểu token đó.
- Caller không cần viết `<T>` tường minh nếu compiler suy luận được từ lời gọi.

Tương tự:

```java
public <T> T get(Class<T> type)
```

Khi truyền `String.class` có kiểu `Class<String>`, kết quả được định kiểu thành `String`.

Ví dụ:

```java
registry.put(String.class, "hello");   // Hợp lệ
registry.put(Integer.class, 123);      // Hợp lệ

// CỐ Ý KHÔNG BIÊN DỊCH:
// registry.put(String.class, 123);     // String và Integer không tương thích
```

Để biết kiểu, compiler không cần đọc nội dung runtime của map: **chữ ký generic** đủ để kiểm tra các lời gọi được viết đúng kiểu.

Chữ ký không làm Java Generics trở thành reified. Nếu code dùng raw types, casts không kiểm tra, reflection hoặc truy cập backing map từ một đường khác, quan hệ key/value vẫn có thể bị phá. Vì vậy cần khóa chặt **đường ghi** và dùng runtime validation.

## 3. Thiết kế tối thiểu: `Map<Class<?>, Object>`

Một class registry cơ bản:

```java
final class Registry {
    private final Map<Class<?>, Object> values = new HashMap<>();

    public <T> void put(Class<T> type, T value) {
        values.put(type, type.cast(value));
    }

    public <T> T get(Class<T> type) {
        return type.cast(values.get(type));
    }
}
```

Đây là mảnh khai báo minh họa; cần import `Map` và `HashMap`, hoặc dùng tên đầy đủ như trong chương trình bên dưới.

Tại sao field là `Map<Class<?>, Object>` chứ không phải `Map<Class<T>, T>`?

- **Không có một `T` chung cho mọi entry.** Một khóa `String.class` có giá trị `String`, khóa `Integer.class` có giá trị `Integer`.
- `Class<?>` cho phép map nhận class token của nhiều lớp.
- `Object` cho phép lưu các object reference thuộc nhiều class.
- Chữ ký generic của **method** `<T>` sẽ đảm bảo từng thao tác có đúng quan hệ kiểu.

Cũng đừng nghĩ `Map<Class<?>, Object>` là một `Map<Class<T>, T>` cho một `T` duy nhất. Generic parameter ở cấp class sẽ giới hạn toàn bộ registry vào một loại, không đúng mục đích heterogeneous.

`Class.cast` là bước xác minh runtime bổ sung: nếu `type` đại diện `String` và `value` không phải `String`, nó sẽ ném `ClassCastException`. Với `null`, `Class.cast(null)` trả `null`, nên cần chính sách `null` riêng nếu ứng dụng không muốn chấp nhận.

## 4. Ví dụ chạy được: registry tối thiểu

Tạo tệp **`BasicTypeRegistryDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class BasicTypeRegistryDemo {

    static final class Registry {
        private final Map<Class<?>, Object> values = new HashMap<>();

        public <T> void put(Class<T> type, T value) {
            values.put(type, type.cast(value));
        }

        public <T> T get(Class<T> type) {
            return type.cast(values.get(type));
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        registry.put(String.class, "Java 17");
        registry.put(Integer.class, 4);
        registry.put(Boolean.class, true);

        String label = registry.get(String.class);
        Integer attempts = registry.get(Integer.class);
        Boolean enabled = registry.get(Boolean.class);

        System.out.println(label);
        System.out.println(attempts);
        System.out.println(enabled);
        System.out.println(registry.get(Double.class) == null);
    }
}
```

Biên dịch và chạy:

```bash
javac BasicTypeRegistryDemo.java
java BasicTypeRegistryDemo
```

Stdout:

```text
Java 17
4
true
true
```

Giải thích:

1. Registry chỉ có **một map nội bộ**, không phải ba map cho `String`, `Integer`, `Boolean`.
2. `put(String.class, "Java 17")` giữ đúng cặp class/value.
3. `get(Integer.class)` trả kết quả kiểu `Integer`; caller không cần ép `(Integer)`.
4. Vì `Double.class` chưa có entry, `Map.get` trả `null`, và `Class.cast(null)` trả `null`.
5. Đây là ví dụ đơn giản để thấy cơ chế, **chưa quyết định chính sách null và primitive class tokens**.

Khi muốn dùng thiết kế trong thư viện, đừng dừng ở ví dụ tối thiểu: cần làm rõ khóa vắng, `null`, cập nhật, thread safety và khả năng lưu generic parameterized types.

## 5. Vì sao `Class<T>` là một “type token”?

Một class literal:

```java
Class<String> s = String.class;
Class<Integer> n = Integer.class;
```

là reference tới runtime `Class` objects của `String` và `Integer`.

Token cung cấp API như:

- `type.cast(object)` — kiểm tra và trả object với kiểu `T`, hoặc ném `ClassCastException`.
- `type.isInstance(object)` — kiểm tra object không null có là instance phù hợp không.
- `type.getName()` — tên class để log/diagnostic.
- `type.isPrimitive()` — nhận diện token đại diện primitive.
- `type.isInterface()` — nhận diện interface.
- `type.isAssignableFrom(otherClass)` — kiểm tra khả năng gán runtime theo chiều thích hợp.

Registry ở đây dùng token theo **identity của class runtime**, không phải theo chuỗi tên đơn thuần. `String.class` là một key; `CharSequence.class` là key khác ngay cả khi một giá trị `String` có thể được lưu dưới cả hai.

Cần phân biệt:

```java
registry.put(String.class, "text");
```

khác với:

```java
registry.put(CharSequence.class, "text");
```

Hai lời gọi có thể chứa cùng một object thực nhưng ghi vào **hai khóa khác nhau**.

## 6. `Class.cast` bảo vệ quan hệ key–value thế nào?

Một implementer có thể viết:

```java
@SuppressWarnings("unchecked")
public <T> T get(Class<T> type) {
    return (T) values.get(type);
}
```

Khi cast sang một type variable `T`, compiler không thể kiểm tra đầy đủ tại runtime vì erasure. Lời gọi của client có thể vẫn nhận được lỗi khi kết quả được dùng như kiểu cụ thể.

Thay bằng:

```java
public <T> T get(Class<T> type) {
    return type.cast(values.get(type));
}
```

có hai lợi ích:

1. **Ý định rõ**: result phải thuộc runtime class mà caller đưa vào.
2. **Vị trí kiểm tra rõ**: `Class.cast` thực hiện kiểm tra kiểu cụ thể theo token, không dựa vào giả định rằng dữ liệu map luôn đúng.

Nên dùng `type.cast(value)` cả ở đường `put` để phòng những đường gọi không hoàn toàn typed, chẳng hạn raw `Class` do mã legacy cung cấp.

Tuy nhiên, `Class.cast` **không kiểm tra bên trong `List<String>`**. Nếu type là `List.class`, nó chỉ xác nhận một object thuộc interface `List`, không quan tâm phần tử là `String` hay `Integer`. Giới hạn ấy được phân tích riêng ở phần sau.

## 7. API thực dụng: cấm null, trả giá trị cũ và xóa đúng kiểu

Để có hợp đồng dễ kiểm tra, giả sử registry chọn:

- `null` **không được dùng làm value**.
- Class token `null` bị từ chối.
- Primitive token như `int.class` bị từ chối.
- Mỗi `Class<?>` key chỉ có **một value**; `put` mới thay value cũ.
- `get` trả `null` khi key vắng; `find` có thể trả `Optional<T>`.
- `remove` trả giá trị cũ có kiểu `T`, hoặc `null` khi không tồn tại.

Tệp **`StrictTypeRegistryDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class StrictTypeRegistryDemo {

    static final class Registry {
        private final Map<Class<?>, Object> entries = new HashMap<>();

        private static <T> Class<T> checkToken(Class<T> type) {
            Objects.requireNonNull(type, "type");

            if (type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Primitive class token is unsupported");
            }

            return type;
        }

        public <T> T put(Class<T> type, T value) {
            type = checkToken(type);
            Objects.requireNonNull(value, "value");

            Object previous = entries.put(type, type.cast(value));
            return type.cast(previous);
        }

        public <T> T get(Class<T> type) {
            type = checkToken(type);
            return type.cast(entries.get(type));
        }

        public <T> Optional<T> find(Class<T> type) {
            return Optional.ofNullable(get(type));
        }

        public <T> T remove(Class<T> type) {
            type = checkToken(type);
            return type.cast(entries.remove(type));
        }

        public boolean contains(Class<?> type) {
            checkToken(type);
            return entries.containsKey(type);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        System.out.println(registry.put(String.class, "first"));
        System.out.println(registry.put(String.class, "second"));
        System.out.println(registry.get(String.class));
        System.out.println(registry.contains(String.class));
        System.out.println(registry.find(Integer.class).isPresent());
        System.out.println(registry.remove(String.class));
        System.out.println(registry.contains(String.class));
    }
}
```

Biên dịch và chạy trên Java 17:

```bash
javac StrictTypeRegistryDemo.java
java StrictTypeRegistryDemo
```

Stdout:

```text
null
first
second
true
false
second
false
```

Giải thích:

- `put` trả về **giá trị cũ** cùng class nếu đã có entry; lần đầu trả `null`.
- `get` và `remove` có return type `T` theo token.
- `containsKey` giúp phân biệt vắng mặt trong hợp đồng nếu cần.
- `Optional.ofNullable` diễn đạt “có hoặc không có giá trị” khi value null bị cấm.
- `checkToken` loại primitive class tokens vì chúng không thể được dùng tương tự reference tokens trong `Class.cast`.

Ví dụ này **không an toàn khi nhiều thread truy cập cùng lúc**, vì backing map là `HashMap`. Nếu cần concurrent access, dùng một thiết kế khác thay vì giả định API generic đã xử lý concurrency.

## 8. Chính sách null: quyết định rõ từ đầu

`HashMap` cho phép `null` làm value. `Class.cast(null)` cũng trả `null`. Vì vậy registry tối thiểu không phân biệt được:

```java
registry.get(String.class) == null
```

có nghĩa “không có entry” hay “entry có value null”.

Có ba hướng thiết kế hợp lệ:

**Hướng A — Không chấp nhận null value.** Dùng `Objects.requireNonNull(value)` trong `put`; khi đó `get(...) == null` có thể biểu thị key không tồn tại. Đây là lựa chọn của `StrictTypeRegistryDemo`.

**Hướng B — Cho phép null nhưng có API `contains`.** `containsKey(type)` phân biệt key vắng và key hiện diện với null. `Optional<T>` **không** thể hiện riêng ba trạng thái vắng / có null / có non-null.

**Hướng C — Dùng mô hình kết quả riêng.** Ví dụ record hoặc sealed type mô tả `Absent`, `PresentNull`, `PresentValue<T>` nếu nghiệp vụ cần phân biệt đầy đủ.

Không nên đặt `Optional<T>` như value map một cách máy móc để giải quyết toàn bộ. Nó thêm một tầng đối tượng và vẫn cần thống nhất `Optional.empty()` biểu diễn điều gì.

Đối với `ConcurrentHashMap`, `null` key và `null` value không được chấp nhận; chính sách cấm null là cần thiết nếu lựa chọn backing map này.

## 9. Primitive tokens: `int.class` khác `Integer.class`

Một chi tiết nâng cao:

```java
System.out.println(int.class.isPrimitive());
System.out.println(Integer.class.isPrimitive());
```

Hai dòng trên (khi đặt trong `main`) in:

```text
true
false
```

Java có class token cho primitive để phục vụ reflection, nhưng generic type arguments không được là primitive. Trong các ngữ cảnh class literal, `int.class` có thể tham gia API với kiểu `Class<Integer>` theo quy tắc đặc biệt của `Class` literals, **không có nghĩa `int.class` tương đương `Integer.class`**.

Runtime class token của `int` không phải runtime class của boxed `Integer` instance. Trong một registry lưu `Object`, hợp đồng đơn giản nhất là:

- **Dùng `Integer.class`** khi muốn lưu một giá trị `Integer` (được autobox từ `int` nếu cần).
- **Từ chối `int.class`** khi đăng ký value bằng `Class.cast`.
- Tương tự dùng `Boolean.class`, `Double.class` thay cho primitive tokens.

`Class.cast` trên primitive class token không thực hiện phép boxing/unboxing chung như một converter. Đừng coi `int.class.cast(1)` là cách chuyển `Integer` sang primitive `int`.

## 10. Registry định danh theo chính class token, không tìm subtype tự động

Khi gọi:

```java
registry.put(String.class, "A");
```

registry ghi key `String.class`. Một lời gọi sau:

```java
registry.get(CharSequence.class);
```

không tự tìm entry của `String.class`, dù `String implements CharSequence`.

Nguyên nhân: `Map.get` tìm **đúng key**, không chạy thuật toán duyệt class hierarchy.

Nếu nghiệp vụ cần “tìm tất cả service implement interface X”, đó là **một bài toán khác**:

- Có thể đăng ký rõ bằng key interface: `registry.put(CharSequence.class, "A")`.
- Có thể thiết kế resolver dùng `isAssignableFrom` để tìm ứng viên phù hợp.
- Nhưng khi có nhiều implementation phù hợp, resolver cần quy tắc ưu tiên/độ duy nhất; không thể trả tùy ý entry đầu tiên từ map như một hợp đồng chắc chắn.

Thiết kế chính của bài ưu tiên **lookup theo class key chính xác**, vì đơn giản, xác định và dễ bảo đảm type safety.

## 11. Chương trình minh họa key interface và key implementation

Tệp **`ExactClassKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class ExactClassKeyDemo {
    static final class Registry {
        private final Map<Class<?>, Object> values = new HashMap<>();

        <T> void put(Class<T> type, T value) {
            values.put(type, type.cast(value));
        }

        <T> T get(Class<T> type) {
            return type.cast(values.get(type));
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        registry.put(String.class, "concrete");

        System.out.println(registry.get(String.class));
        System.out.println(registry.get(CharSequence.class));

        registry.put(CharSequence.class, "interface");
        System.out.println(registry.get(String.class));
        System.out.println(registry.get(CharSequence.class));
    }
}
```

Biên dịch/chạy:

```bash
javac ExactClassKeyDemo.java
java ExactClassKeyDemo
```

Stdout:

```text
concrete
null
concrete
interface
```

`String.class` và `CharSequence.class` là hai keys riêng. Cả hai có thể trỏ tới các object có runtime class `String`, nhưng API nhận diện chúng theo **class tokens người đăng ký đã chọn**.

Đây là hành vi nên ghi rõ trong tài liệu API; nếu không, caller dễ lầm rằng `get(SuperType.class)` sẽ tự tìm tất cả subtype instances.

## 12. `Class<T>` invariance và wildcard trong registry

Generic class `Class<T>` là **invariant**. Mặc dù `Integer extends Number`, không thể tự gán `Class<Integer>` cho biến `Class<Number>`:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
// Class<Number> token = Integer.class;
```

Nhưng:

```java
Class<? extends Number> numericToken = Integer.class;
```

là hợp lệ.

Lúc dùng một token wildcard, compiler chỉ biết **một subtype chưa xác định** của `Number`:

```java
Class<? extends Number> type = Integer.class;
```

Một API:

```java
<T> T get(Class<T> type)
```

có thể trả một giá trị được nhìn an toàn như `Number` khi nhận một `Class<? extends Number>`, nhưng không thể giả định nó là **bất kỳ** subtype nào do caller tùy ý chọn.

Các helper nên dùng `Class<? extends Base>` nếu muốn nhận plugin implementations, còn public `get(Class<T>)` giữ quan hệ **cùng một type parameter T** giữa class token và result.

Đừng thay chữ ký bằng raw `Class` để “giải quyết” các lỗi wildcard. Khi cần, dùng capture helper hoặc chuyển value trong phạm vi bound đã biết.

## 13. Khi có key lấy động từ `Class.forName`

Một ứng dụng plugin có thể nhận class name từ cấu hình:

```java
Class<?> loaded = Class.forName("java.lang.String");
```

Token có kiểu tĩnh `Class<?>`: compiler không biết một `T` cụ thể. Nếu cần giới hạn plugin về một interface hoặc base class, hãy kiểm tra runtime:

```java
Class<? extends CharSequence> type =
        loaded.asSubclass(CharSequence.class);
```

`asSubclass` trả một token có bound đã được kiểm tra, hoặc ném `ClassCastException` nếu class không phải subtype thích hợp.

**Không làm điều này cho mọi class name từ input chưa tin cậy rồi khởi tạo tùy ý.** Việc load/instantiate có thể chạy code, dùng tài nguyên và đụng tới chính sách quyền truy cập. Sử dụng allowlist hoặc một danh sách plugin đã được xác thực khi triển khai runtime registry.

Trong registry theo class key, API nhận `Class<?>` giúp đọc metadata hoặc kiểm tra có entry; nhưng nếu muốn `get` trả về một kiểu cụ thể có compile-time guarantee, **người gọi phải có token được ràng buộc phù hợp**. Truyền một class name dạng string không tự làm compiler biết kiểu kết quả.

## 14. Không dùng khóa chuỗi để giả vờ đã tạo quan hệ kiểu

So sánh hai API:

```java
Object get(String key);
<T> T get(Class<T> type);
```

API thứ nhất không thể suy từ một chuỗi `"port"` ra return type `Integer` trừ khi có schema/registry khác và caller cast.

API thứ hai liên kết giá trị trả về trực tiếp với type argument của `Class<T>` trong method signature. Nó phù hợp với dữ liệu mà **mỗi class chỉ có một entry** và class identity là key hợp lý.

Nhưng nếu nghiệp vụ muốn **hai chuỗi khác nhau** như `"firstName"` và `"lastName"` cùng mang kiểu `String`, registry class-key không giải quyết đủ:

```java
registry.put(String.class, "first");
registry.put(String.class, "last");
```

Lần ghi thứ hai sẽ **thay thế** lần đầu vì trùng key.

Giải pháp có thể là một **typed key object** kết hợp tên và class token, ví dụ `Key<T>("firstName", String.class)`, hoặc key gồm namespace + type. Đó là một cấu trúc khác với bài toán “mỗi runtime class là một key”.

## 15. Khi một class cần nhiều giá trị: typed key có tên

Nếu nghiệp vụ cần nhiều giá trị cùng kiểu, có thể dùng một khóa có danh tính riêng, đồng thời lưu token để duy trì relation với value.

Một mô hình:

```java
record Key<T>(String name, Class<T> type) {
}
```

Nhưng cần lưu ý: generic `Key<T>` bị erasure, và Java record equality sẽ so **name và type**; nếu hai key có cùng name và class token, chúng trùng theo equality dù được tạo hai lần.

Bản thiết kế hợp lý có thể có:

```java
Map<Key<?>, Object> values;
<T> void put(Key<T> key, T value);
<T> T get(Key<T> key);
```

Và kiểm tra `key.type().cast(value)` ở cả hai chiều. Mẫu này thêm một chiều **định danh nghiệp vụ** ngoài class runtime.

Ở bài hiện tại, trọng tâm vẫn là `Class<T>` làm key. Typed named keys là **phương án mở rộng** khi một class cần nhiều hơn một registration hoặc cần key namespace.

## 16. Ví dụ mở rộng: `Key<T>` kết hợp tên và class token

Tệp **`NamedTypedKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class NamedTypedKeyDemo {

    record Key<T>(String name, Class<T> type) {
        Key {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);
        }
    }

    static final class Registry {
        private final Map<Key<?>, Object> values = new HashMap<>();

        <T> void put(Key<T> key, T value) {
            Objects.requireNonNull(value);
            values.put(key, key.type().cast(value));
        }

        <T> T get(Key<T> key) {
            return key.type().cast(values.get(key));
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        Key<String> first = new Key<>("firstName", String.class);
        Key<String> last = new Key<>("lastName", String.class);

        registry.put(first, "An");
        registry.put(last, "Nguyen");

        System.out.println(registry.get(first));
        System.out.println(registry.get(last));
    }
}
```

Biên dịch/chạy:

```bash
javac NamedTypedKeyDemo.java
java NamedTypedKeyDemo
```

Stdout:

```text
An
Nguyen
```

Đây là một giải pháp có **hai khóa khác nhau cùng class token `String.class`**. Nó cho thấy khi nào phải nâng cấp thiết kế so với `Map<Class<?>,Object>`.

Lưu ý: nếu cần name case-insensitive, namespace, tenant hoặc các ràng buộc hợp lệ khác, phải tự định nghĩa quy tắc định danh ở record/class key. Generic signature không thay thế dữ liệu nghiệp vụ.

## 17. Giới hạn rất quan trọng: `List<String>` và `List<Integer>` dùng cùng `List.class`

Java Generics có **type erasure**. Một parameterized type như `List<String>` không có class literal riêng:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
// Class<List<String>> stringList = List<String>.class;
```

Runtime chỉ có:

```java
Class<?> listClass = List.class;
```

Hệ quả trong class-key registry:

- Không có hai keys riêng tên `List<String>.class` và `List<Integer>.class`.
- `List.class` chỉ xác minh rằng object thuộc interface `List`.
- Không thể dùng `type.cast(value)` với `List.class` để xác minh mọi phần tử là `String`.
- Một registry có một entry cho `List.class` theo thiết kế cơ bản, không phân biệt generic type arguments.

### Ví dụ đọc đúng giới hạn

Tệp **`ListClassTokenLimitDemo.java`**:

```java
import java.util.List;

public class ListClassTokenLimitDemo {
    public static void main(String[] args) {
        List<?> text = List.of("A", "B");
        List<?> numbers = List.of(1, 2);

        System.out.println(List.class.isInstance(text));
        System.out.println(List.class.isInstance(numbers));

        Object mixed = List.of("A", 10);
        List<?> accepted = List.class.cast(mixed);

        System.out.println(accepted.size());
        System.out.println(accepted.get(1));
    }
}
```

Biên dịch/chạy:

```bash
javac ListClassTokenLimitDemo.java
java ListClassTokenLimitDemo
```

Stdout:

```text
true
true
2
10
```

`List.class` chấp nhận cả danh sách chuỗi, danh sách số và danh sách trộn. Điều đó đúng theo raw runtime interface, nhưng **không phải kiểm tra type argument**.

Khi cần lưu **generic type lồng nhau** làm key, phải dùng một loại key có thể mô tả `Type`, `ParameterizedType`, type reference hoặc schema riêng, và cần chính sách validation nếu muốn tin dữ liệu runtime.

## 18. Vì sao `Map<Type,Object>` cũng không tự an toàn?

Một lựa chọn nâng cao là dùng `java.lang.reflect.Type` làm key, ví dụ từ `TypeReference<List<String>>` và `TypeReference<List<Integer>>`. Nhờ `ParameterizedType`, hai keys có thể phân biệt **cấu trúc generic**.

Nhưng không được viết:

```java
// Ý tưởng chưa đủ để an toàn:
Map<Type, Object> values;
```

rồi tuyên bố đã an toàn kiểu.

Vì sao?

1. `Type` mô tả generic declaration/type schema, **không tự validate một object bất kỳ**.
2. `Type` không cung cấp `cast` tổng quát như `Class<T>` để kiểm tra `List<String>` ở runtime.
3. Một caller có thể đưa `List<Object>` trộn dữ liệu vào map nếu API dùng casts không kiểm tra.
4. Nếu cần `List<String>`, bộ kiểm tra phải duyệt từng phần tử và kiểm tra `String` theo schema, hoặc dựa vào một deserializer có validation rõ ràng.

Vì vậy hãy tách:

- **Class-key registry**: mối quan hệ runtime class đơn giản; dùng `Class.cast`.
- **Generic type-key registry**: key giữ cấu trúc `Type`, cần mô hình validation và trust boundary chặt hơn.

Không xây một API `get(Type)` trả `<T> T` không kiểm tra rồi gọi nó an toàn chỉ vì key chứa chữ `List<String>`.

## 19. Vấn đề identity: Class objects, class loaders và module

`Class` objects được JVM gắn với **runtime type definition**. Hai class có cùng tên nhị phân nhưng được định nghĩa bởi các class loaders khác nhau có thể là **hai runtime classes khác nhau**.

Đây là điều quan trọng trong plugin registries:

- Không dùng `Class.getName()` như một thay thế đáng tin cho class identity.
- `Class.cast` và `isAssignableFrom` kiểm tra quan hệ type thực, không chỉ so chuỗi tên.
- `Map<Class<?>,Object>` dùng class token làm key theo `equals/hashCode` của `Class`, gắn với runtime class identity.
- Nếu plugin được unload/reload bằng class loader mới, các tokens và entries cũ không tự chuyển thành token của class mới.

**Class-loader leaks:** một singleton registry sống lâu mà giữ keys là plugin `Class<?>` hoặc values là plugin instances có thể giữ class loader/plugin không được giải phóng. Khi có plugin lifecycle, phải hỗ trợ remove/close/clear theo phạm vi và không giữ references lâu hơn cần thiết.

Đây là vấn đề quản lý vòng đời tham chiếu, không phải lỗi của Generic type checking.

## 20. Quyền sở hữu và mutability: type-safe không có nghĩa immutable

Giả sử một registry chứa `ArrayList` dưới token `List.class` hoặc một class cụ thể `ArrayList.class`. Caller lấy về một reference tới **chính object** đang được giữ trong map.

Nếu object đó mutable, caller có thể sửa nó:

```java
List<String> names = new ArrayList<>();
names.add("A");
registry.put(List.class, names); // Cần xem chính sách generic API và raw List.
```

Đây là đoạn thảo luận, không phải mẫu khuyến khích: dùng `List.class` chỉ đại diện raw interface và không giữ `String` trong token. Không nên dùng ví dụ này làm chứng cứ một `List<String>` đã được runtime kiểm tra.

Một hướng tốt hơn là thiết kế registry lưu **các service objects hoặc cấu hình immutable**, và xác định caller có được thay đổi đối tượng sau `put` hay không.

Các chính sách có thể gồm:

- Lưu reference nguyên trạng: nhanh, nhưng thay đổi của caller được nhìn thấy qua registry.
- Tạo defensive copy với loại dữ liệu phù hợp.
- Lưu immutable value objects/records, hoặc snapshot không sửa được.
- Giới hạn quyền truy cập với registry hoặc dịch vụ API đọc-only.

`Class<T>` đảm bảo **kiểu runtime khi đặt/lấy**, không tự sao chép hoặc làm bất biến giá trị.

## 21. Khi nào nên dùng `ConcurrentHashMap`?

`HashMap` không hỗ trợ truy cập thay đổi đồng thời không đồng bộ một cách an toàn. Nếu nhiều threads có thể gọi `put`/`get`/`remove` trên cùng registry, phải chọn chiến lược thread safety.

Một lựa chọn là:

```java
private final ConcurrentHashMap<Class<?>, Object> values =
        new ConcurrentHashMap<>();
```

Các ưu điểm:

- `get`, `put`, `putIfAbsent`, `remove` hỗ trợ các bảo đảm concurrency thích hợp của `ConcurrentHashMap`.
- Không cho phép null key/value, phù hợp với chính sách từ chối null.
- Có các atomic operations cho nhiều trường hợp như `computeIfAbsent`.

Những giới hạn:

- Thread safety của map **không khiến các object value mutable trở thành thread-safe**.
- Nếu logic cần tính nhất quán qua nhiều keys hoặc nhiều bước, từng map operation độc lập chưa đảm bảo transaction.
- Với `computeIfAbsent`, mapping function nên ngắn gọn và không tự cập nhật chính map theo cách có thể gây lỗi hoặc deadlock.
- Không nên cho rằng mọi side effects trong factory được chạy đúng một lần trong mọi tình huống lỗi/retry bên ngoài.

Nếu registry chỉ dùng trong một scope đơn luồng, `HashMap` có thể đủ và đơn giản hơn.

## 22. Ví dụ đầy đủ: concurrent type registry

Tệp **`ConcurrentTypeRegistryDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Supplier;

public class ConcurrentTypeRegistryDemo {

    static final class Registry {
        private final ConcurrentMap<Class<?>, Object> values =
                new ConcurrentHashMap<>();

        private static <T> Class<T> checkType(Class<T> type) {
            Objects.requireNonNull(type, "type");

            if (type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Primitive class tokens not supported");
            }

            return type;
        }

        <T> T registerIfAbsent(Class<T> type, T value) {
            type = checkType(type);
            Objects.requireNonNull(value, "value");

            Object previous = values.putIfAbsent(
                    type, type.cast(value));

            return type.cast(previous);
        }

        <T> T get(Class<T> type) {
            type = checkType(type);
            return type.cast(values.get(type));
        }

        <T> T getOrCreate(
                Class<T> type,
                Supplier<? extends T> factory) {

            type = checkType(type);
            Objects.requireNonNull(factory, "factory");
            Class<T> checked = type;

            Object found = values.computeIfAbsent(
                    checked,
                    ignored -> checked.cast(
                            Objects.requireNonNull(factory.get())));

            return checked.cast(found);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        System.out.println(
                registry.registerIfAbsent(String.class, "first"));
        System.out.println(
                registry.registerIfAbsent(String.class, "second"));

        System.out.println(registry.get(String.class));
        System.out.println(
                registry.getOrCreate(Integer.class, () -> 5));
        System.out.println(
                registry.getOrCreate(Integer.class, () -> 99));
    }
}
```

Biên dịch/chạy:

```bash
javac ConcurrentTypeRegistryDemo.java
java ConcurrentTypeRegistryDemo
```

Stdout:

```text
null
first
first
5
5
```

Giải thích:

- `putIfAbsent` chỉ đặt `"first"` khi token `String.class` chưa có entry.
- Lần đăng ký `"second"` trả về giá trị đã lưu `"first"` thay vì ghi đè.
- `computeIfAbsent` tạo giá trị `Integer` khi chưa có; lần kế tiếp đọc giá trị cũ `5`.
- `Supplier<? extends T>` cho phép factory trả một subtype phù hợp.
- `Class.cast` xác minh class ở ranh giới ghi/đọc.

Đây là ví dụ tuần tự chạy `main` để có stdout xác định. Muốn khẳng định tính đúng đắn dưới concurrency thật, còn cần test stress phù hợp và thiết kế rõ lifecycle của các service values.

## 23. Lazy factories và scope của service registry

Một class-key registry thường dùng trong dependency injection hoặc service locator:

```java
registry.put(Logger.class, logger);
registry.put(Clock.class, clock);
```

Đây là code minh họa; giả định `Logger`/`Clock` phù hợp và đã được khởi tạo.

Một API có thể chọn:

- **Eager registration**: gọi `put` với value đã tạo.
- **Lazy creation**: `getOrCreate(token, supplier)` khi token chưa có value.
- **Per-request scope**: mỗi request có registry riêng.
- **Application scope**: một registry chung trong suốt vòng đời ứng dụng.

Chọn scope ảnh hưởng mạnh đến mutability và concurrency. Một singleton registry cho toàn ứng dụng có thể giữ service lâu hơn cần thiết. Một registry theo request đơn giản hơn về isolation nhưng không nên làm chậm hệ thống nếu dịch vụ khởi tạo tốn kém.

Nếu cần **đa dạng cấu hình** cho cùng một class (ví dụ hai database connections), class-key một mình không đủ để phân biệt; dùng named typed keys, qualifiers hoặc một service container có phạm vi/định danh.

## 24. `getRequired`: trả thông báo lỗi rõ khi thiếu entry

Một API `get(Class<T>)` trả `null` giúp linh hoạt, nhưng nhiều ứng dụng muốn thiếu service là lỗi cấu hình.

Có thể thêm:

```java
<T> T getRequired(Class<T> type) {
    T value = get(type);

    if (value == null) {
        throw new IllegalStateException(
                "No registration for " + type.getName());
    }

    return value;
}
```

Đây là method minh họa cần nằm trong class đã định nghĩa `get(type)`.

Ưu điểm:

- Caller không phải tự unbox/dereference null.
- Thông báo nêu **class token bị thiếu**.
- Dễ tìm lỗi cấu hình sớm.

Điều kiện: registry cần cấm null values để `null` có nghĩa chính xác là “chưa đăng ký”. Nếu cho phép null value, phải dùng `containsKey` để phân biệt.

Một phương thức thay thế:

```java
<T> Optional<T> find(Class<T> type)
```

tốt khi missing entry là trạng thái bình thường. Đừng ném exception cho một trường hợp “không tìm thấy” hoàn toàn được mong đợi nếu API có thể diễn đạt rõ bằng `Optional`.

## 25. Những giới hạn của registry class-key

Bảng quyết định:

| Nhu cầu | `Map<Class<?>, Object>` phù hợp? | Ghi chú |
|---|---|---|
| Một service instance cho mỗi runtime class token | Có | API `<T> get(Class<T>)` rõ và an toàn |
| Một `String` và một `Integer` cùng trong registry | Có | Hai class keys khác nhau |
| Một value dưới interface token và một value dưới implementation token | Có | Hai entries tách biệt |
| Tự tìm subtype từ base interface | Không tự động | Cần resolver và chính sách ambiguity |
| Hai giá trị `String` theo tên `first`, `last` | Không đủ | Thêm named typed key/qualifier |
| Phân biệt `List<String>` và `List<Integer>` | Không | `List.class` chung; cần generic type key/schema |
| Xác minh nội dung `List<String>` runtime | Không | `Class.cast(List.class)` chỉ kiểm tra raw `List` |
| Lưu dữ liệu primitive không boxing | Không trực tiếp | Values là reference objects |
| Đọc/ghi đồng thời | Tùy backing map | Cân nhắc `ConcurrentHashMap` và value thread safety |
| Tự tạo object từ class token | Không tự động | Cần factory, constructor reflection hoặc DI |
| Đảm bảo immutable values | Không | Cần contract/copy riêng |
| Dùng cùng class qua nhiều class loaders | Không đồng nhất | Runtime Class identity phụ thuộc loader |

Một API tốt nên công bố những giới hạn này để caller không dựa trên giả định quá mức về type safety.

## 26. Anti-pattern: raw `Class`, unchecked cast và map bị lộ

**Không nên** cung cấp backing map ra ngoài:

```java
Map<Class<?>, Object> mutableBacking() {
    return entries;
}
```

Caller có thể ghi `entries.put(String.class, 123)` và phá invariant mà public `put` đang cố bảo vệ.

**Không nên** dùng raw `Class` trong phương thức chính:

```java
Object get(Class type)
```

Dạng này mất mối quan hệ generic giữa token và result và buộc caller cast.

**Không nên** viết:

```java
<T> T get(Class<T> type) {
    return (T) entries.get(type);
}
```

rồi chỉ gắn `@SuppressWarnings("unchecked")` để bỏ cảnh báo. `Class.cast` thể hiện runtime validation rõ ràng hơn.

**Không nên** dùng `Class.forName(userInput).newInstance()` một cách mù quáng để tự đăng ký. Reflection construction có lỗi truy cập, thiếu constructor, tác dụng phụ và an ninh; ngay cả `Class.newInstance()` cũ cũng không phải API được khuyến khích.

**Không nên** cố nhét nhiều parameterized types dưới `List.class` rồi cho rằng map sẽ giữ từng type argument.

Những lỗi trên thường không lộ khi test đúng dữ liệu, nhưng trở thành bug tại ranh giới legacy/unchecked hoặc khi thiết kế lớn hơn.

## 27. Type safety không che giấu lỗi ngữ nghĩa

Một registry hoàn toàn an toàn về runtime class vẫn có thể sai **nghiệp vụ**.

Ví dụ:

```java
registry.put(Integer.class, 8080);
```

Về type, đây là một `Integer` hợp lệ. Nhưng đó là cổng HTTP, số người dùng hay số retries? Nếu hệ thống cần nhiều `Integer` khác nhau, `Integer.class` không phải key đủ rõ.

Tương tự, một `Clock` service có thể được đăng ký dưới `Clock.class` nhưng dùng timezone hoặc lịch giả lập không đúng cho nghiệp vụ. Class token chỉ kiểm tra loại đối tượng; nó không xác minh semantic correctness.

Khi những loại thông tin cùng class xuất hiện nhiều, dùng:

- Named typed key (tên + `Class<T>`).
- Qualifier annotations với registry có quy tắc xử lý.
- Các value classes/records chuyên biệt như `Port`, `RetryCount`, `Timeout`.
- Một container DI có scopes/qualifiers phù hợp.

Đây là **thiết kế API rõ nghĩa**, không phải một giới hạn ngôn ngữ có thể giải quyết bằng generic syntax.

## 28. Bài thực hành: kiểm tra các lựa chọn API

### Bài 1 — Vì sao field là `Map<Class<?>, Object>`?

**Đáp án:** Mỗi key thuộc một class khác nhau, mỗi value cũng thuộc class tương ứng. Không có một `T` chung cho toàn container; method-level `<T>` khôi phục quan hệ khi thao tác.

### Bài 2 — `put` sai kiểu có biên dịch không?

```java
registry.put(String.class, 42);
```

**Đáp án:** Không hợp lệ trong typed code thông thường vì generic inference không thể làm `42` tương thích `String` với `Class<String>`.

### Bài 3 — `get` có cần cast ở caller không?

```java
String s = registry.get(String.class);
```

**Đáp án:** Không. Chữ ký `<T> T get(Class<T>)` khiến compiler suy luận `T = String`.

### Bài 4 — `Class.cast` có từ chối null không?

**Đáp án:** Không; `String.class.cast(null)` trả null. Hãy tự dùng `Objects.requireNonNull` nếu muốn cấm null values.

### Bài 5 — Có một entry của String, lookup bằng CharSequence?

**Đáp án:** `get(CharSequence.class)` không tự tìm `String.class`. Keys khác nhau; chỉ trả value nếu đã đăng ký với chính `CharSequence.class`.

### Bài 6 — Có thể có hai entry String khác nhau theo class key không?

**Đáp án:** Không nếu map chỉ dùng `String.class` làm khóa; bản ghi mới thay bản ghi cũ. Cần typed named keys/qualifiers nếu muốn cả hai.

### Bài 7 — Có `List<String>.class` không?

**Đáp án:** Không. Java không tạo class literal cho parameterized type đó.

### Bài 8 — `List.class.cast(...)` xác minh phần tử String chưa?

**Đáp án:** Chưa. Nó chỉ kiểm tra object là `List`. Cần kiểm tra từng phần tử hoặc dùng decoder/schema khác nếu cần.

### Bài 9 — Vì sao không dùng `(T)` ở getter?

**Đáp án:** Cast tới type variable bị erasure, khó xác minh runtime class cụ thể. `type.cast(...)` sử dụng class token của caller để kiểm tra trước khi trả.

### Bài 10 — Registry concurrent có giải quyết thread safety của service object?

**Đáp án:** Không. `ConcurrentHashMap` bảo vệ thao tác map; value mutable vẫn cần cơ chế concurrency riêng.

### Bài 11 — `int.class` có nên là key cho `Integer`?

**Đáp án:** Không theo API mẫu. Dùng `Integer.class` làm key; `int.class` là primitive token, không thực hiện boxing trong `Class.cast`.

### Bài 12 — Nếu key thiếu và value null đều được cho phép?

**Đáp án:** Dùng `containsKey` hoặc result type rõ để phân biệt. `get == null` không đủ.

### Bài 13 — Plugin class loader ảnh hưởng class key thế nào?

**Đáp án:** Class cùng tên do loaders khác nhau định nghĩa có runtime Class identities khác nhau; key không tự trùng.

### Bài 14 — Khi nào nên tách registry thành named keys?

**Đáp án:** Khi nhiều values cùng runtime class cần phân biệt theo tên, scope hoặc qualifier nghiệp vụ.

### Bài 15 — Có thể lấy class token để tự tạo instance bằng constructor không?

**Đáp án:** Có thể dùng reflection với điều kiện class có constructor phù hợp và quyền truy cập thích hợp, nhưng registry không nên mặc định tự tạo mọi class khi thiếu entry.

## 29. Checklist đưa vào code thực tế

1. Viết hợp đồng rõ: **mỗi class token có tối đa một value** hay cần multiple keys?
2. Định nghĩa chính sách với **null token, null value, primitive class token**.
3. Đảm bảo backing map **private**, không expose đường ghi khác.
4. Dùng `<T> put(Class<T>, T)` và `<T> get(Class<T>)`.
5. Dùng `type.cast` ở ranh giới dữ liệu khi cần runtime validation.
6. Quy định `put` ghi đè hay `putIfAbsent`; có cần trả value cũ không?
7. Thiết kế API missing key: `get` nullable, `find` Optional, hoặc `getRequired` ném lỗi.
8. Phân biệt key interface với key implementation — lookup **theo key chính xác**.
9. Không giả định `List.class` phân biệt generic arguments.
10. Nếu phải lưu `List<String>` và `List<Integer>`, thiết kế generic `Type` key cùng validator thay vì unchecked cast.
11. Với concurrent access, dùng map/locks phù hợp; bảo vệ cả mutable values nếu cần.
12. Nếu factory lazy, kiểm tra exception, null và side effects.
13. Xác định lifecycle, clear/remove khi scope hoặc plugin kết thúc.
14. Tránh giữ Class tokens từ plugin loader lâu hơn cần thiết.
15. Đừng trộn class type safety với semantics của qualifiers hoặc keys.
16. Viết unit test cả **đường sai kiểu**, **key vắng**, **replace**, **null**, **interface token** và **repeated same-class keys**.
17. Không bỏ qua lỗi compiler bằng raw types.
18. Ghi tài liệu giải thích `Class<T>` giúp runtime class checking nhưng không reify parameterized types.

## 30. Tổng kết và tài liệu tham khảo

**Kho lưu trữ nhiều kiểu dùng `Class<T>` làm khóa** là một thiết kế hữu ích khi muốn giữ nhiều loại object trong cùng container mà caller vẫn nhận kết quả theo kiểu cụ thể:

```java
registry.put(String.class, "text");
registry.put(Integer.class, 7);

String text = registry.get(String.class);
Integer number = registry.get(Integer.class);
```

Cốt lõi là field nội bộ `Map<Class<?>, Object>` và các method-level type parameters liên kết **`Class<T>` với `T`**. `Class.cast` giúp kiểm tra runtime class tại đường ghi/đọc, còn map phải được giữ private để bảo toàn invariant.

Nhưng thiết kế này **không phải type token cho mọi parameterized type**: nó không phân biệt `List<String>` với `List<Integer>` bởi cả hai dùng `List.class`. Class key cũng không tự giải quyết nhiều entries cùng class, lookup theo subtype, mutation của values, chính sách null hay concurrency.

Chọn registry class-key khi **runtime class identity** đúng là key nghiệp vụ. Nếu bài toán cần named/qualified keys hoặc generic nested schemas, dùng abstraction mở rộng cùng validation tương ứng.

Tài liệu chuẩn:

- [Java SE 17 `Class<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `cast`, `isInstance`, primitive tokens, class identity.
- [Java SE 17 `Map<K,V>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): map key semantics, `put`, `get`, `containsKey`.
- [Java SE 17 `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thread-safe map operations và `computeIfAbsent`.
- [Java SE 17 `Optional<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): biểu diễn kết quả có thể vắng.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments và invariance.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): giới hạn runtime của Generics.
- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): vì sao `List<String>` không có class literal riêng.