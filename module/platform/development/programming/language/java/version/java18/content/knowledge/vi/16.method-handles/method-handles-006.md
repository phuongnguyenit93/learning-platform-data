# findConstructor(): kiểu void trong yêu cầu tra cứu và kiểu đối tượng trong handle được trả về

## 1. Mục tiêu và tình huống dễ nhầm

`MethodHandles.Lookup.findConstructor(...)` thuộc API `java.lang.invoke`, cho phép tìm constructor và nhận một `MethodHandle` để tạo đối tượng khi gọi. Một điểm quan trọng của hợp đồng API này là **hai kiểu phương thức khác nhau** xuất hiện trong cùng một thao tác:

- **Kiểu truyền vào để tra cứu** (`MethodType`): phải có **return type là `void`**, mô tả chữ ký của constructor cần tìm.
- **Kiểu của handle được trả về** (`handle.type()`): có **return type là lớp được tạo**, vì lời gọi handle vừa tạo một đối tượng vừa trả lại tham chiếu tới đối tượng ấy.

Ví dụ, nếu lớp `User` có constructor `User(String, int)`, lời gọi đúng là:

```java
MethodType requested = MethodType.methodType(
        void.class, String.class, int.class);

MethodHandle constructor = MethodHandles.lookup()
        .findConstructor(User.class, requested);
```

Nhưng kiểu thực tế của `constructor` sẽ là:

```text
Yêu cầu tìm constructor:  (String, int)void
Handle được trả về:       (String, int)User
```

**Không** dùng `MethodType.methodType(User.class, String.class, int.class)` làm đối số `type` của `findConstructor()`. Kiểu trả về là `User` chỉ xuất hiện **sau khi** tra cứu thành công, trên handle được trả về.

Bài thuộc chương **MethodHandle** của module `JAVA_VERSION_JAVA18`. Module học những thay đổi từ Java 18 còn hữu ích trên JDK hiện đại, bao gồm kiểm chứng hợp đồng Reflection và MethodHandle. Nội dung này dùng API chuẩn vẫn được hỗ trợ; nó không dựa vào cơ chế triển khai nội bộ cũ hay các API đã lỗi thời.

## 2. Vì sao constructor có hai kiểu liên quan?

Về mặt ngôn ngữ Java, biểu thức:

```java
User user = new User("Lan", 21);
```

tạo một đối tượng và trả tham chiếu tới đối tượng kiểu `User`. Tuy nhiên, constructor ở mức khai báo JVM là phương thức khởi tạo đặc biệt `<init>`, có descriptor kết thúc bằng `V` (kiểu `void`); nó khởi tạo đối tượng đã được cấp phát và **không trực tiếp khai báo giá trị trả về `User` như một phương thức thông thường**.

`findConstructor` kết hợp việc cấp phát đối tượng với việc gọi constructor. Vì vậy API dùng:

1. **`(String, int)void` để xác định constructor** trong lớp `User`.
2. **`(String, int)User` để biểu diễn lời gọi tạo đối tượng** trên `MethodHandle` trả về.

Sơ đồ:

```text
Lookup.findConstructor(
    User.class,
    MethodType.methodType(void.class, String.class, int.class)
)
                   │
                   │ Tìm constructor User(String, int)
                   ▼
          MethodHandle constructor
          type = (String, int)User
                   │
                   │ constructor.invokeExact("Lan", 21)
                   ▼
          Đối tượng mới: User
```

Lưu ý `MethodType` vốn mô tả một kiểu lời gọi, không chứa tên phương thức. Thông tin **lớp cần tạo** được truyền qua đối số `refc` (ở ví dụ là `User.class`); danh sách **kiểu tham số** và `void` nằm trong `type`.

### Hợp đồng theo từng thành phần

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| `refc` | `User.class` | Lớp mà constructor được tra cứu |
| `type` truyền vào | `(String,int)void` | Chữ ký tham số của constructor; return type **bắt buộc là `void`** |
| `MethodHandle` trả về | `(String,int)User` | Lời gọi nhận hai đối số, tạo và trả đối tượng `User` |
| `handle.type().returnType()` | `User.class` | Kiểu kết quả thực tế của handle |
| `handle.type().parameterArray()` | `String.class`, `int.class` | Kiểu hai tham số, tương ứng constructor được tìm |

Không có tham số `this` hay một đối tượng `User` có sẵn phải truyền vào constructor handle. Khác với nhiều handle trỏ đến **instance method**, constructor handle tự tạo receiver mới để khởi tạo.

## 3. Ví dụ Java đầy đủ, tự chạy được

Lưu tệp `ConstructorHandleDemo.java` và chạy bằng JDK hiện đại. Ví dụ chỉ dùng API có sẵn trong JDK, không cần dependency ngoài.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class ConstructorHandleDemo {

    public static final class User {
        private final String name;
        private final int age;

        public User(String name, int age) {
            if (age < 0) {
                throw new IllegalArgumentException("age must be >= 0");
            }
            this.name = name;
            this.age = age;
        }

        public String summary() {
            return name + " (" + age + ")";
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Kiểu dùng để TÌM constructor: return type là void.
        MethodType request = MethodType.methodType(
                void.class, String.class, int.class);

        MethodHandle ctor = lookup.findConstructor(User.class, request);

        // Kiểu của HANDLE: return type trở thành User.
        MethodType actual = ctor.type();
        System.out.println(request);                    // (String,int)void
        System.out.println(actual);                     // (String,int)User
        System.out.println(actual.returnType() == User.class);

        // invokeExact: tham số và kiểu kết quả tại điểm gọi phải khớp.
        User first = (User) ctor.invokeExact("Lan", 21);
        System.out.println(first.summary());

        // Có thể tái sử dụng handle để tạo nhiều đối tượng mới.
        User second = (User) ctor.invokeExact("Minh", 24);
        System.out.println(second.summary());
        System.out.println(first == second);
    }
}
```

Kết quả mong đợi:

```text
(String,int)void
(String,int)User
true
Lan (21)
Minh (24)
false
```

Trong câu lệnh:

```java
User first = (User) ctor.invokeExact("Lan", 21);
```

kiểu `(User)` nằm ngay tại lời gọi `invokeExact(...)` là quan trọng: nó khiến kiểu trả về tại điểm gọi là `User`. Số nguyên `21` có kiểu `int`, nên kiểu lời gọi tương ứng là `(String,int)User` và khớp với `ctor.type()`.

Đoạn mã cũng chứng minh handle trả về **một đối tượng mới mỗi khi được gọi**: `first == second` là `false`. `findConstructor(...)` chỉ tìm và chuẩn bị handle; nó **không** tạo đối tượng `User` ngay ở bước tra cứu.

### Kiểm tra hợp đồng bằng các phép so sánh kiểu

```java
MethodType lookupType = MethodType.methodType(
        void.class, String.class, int.class);

MethodHandle ctor = MethodHandles.lookup()
        .findConstructor(User.class, lookupType);

MethodType expectedHandleType = MethodType.methodType(
        User.class, String.class, int.class);

System.out.println(lookupType.returnType() == void.class); // true
System.out.println(ctor.type().equals(expectedHandleType)); // true
System.out.println(ctor.type().equals(lookupType));         // false
```

`MethodType` là đối tượng biểu diễn kiểu phương thức bất biến. Phép `equals(...)` so sánh cấu trúc kiểu, nên phù hợp để kiểm tra hợp đồng.

## 4. Vì sao truyền `User.class` làm return type khi tìm sẽ sai?

Với constructor có tham số `(String,int)`, có hai tình huống khác nhau:

```java
// ĐÚNG: return type của type truyền vào findConstructor là void.
lookup.findConstructor(
        User.class,
        MethodType.methodType(void.class, String.class, int.class));
```

```java
// SAI HỢP ĐỒNG: return type của request lại là User.
lookup.findConstructor(
        User.class,
        MethodType.methodType(User.class, String.class, int.class));
```

Trường hợp thứ hai vi phạm điều kiện về return type của `findConstructor(...)` và gây `IllegalArgumentException`. Không nên diễn giải lỗi đó là “thiếu constructor trả về User”: constructor vốn không khai báo kiểu trả về giống phương thức thông thường.

Một lỗi khác là tìm constructor bằng **danh sách kiểu tham số không tồn tại**:

```java
// User chỉ có User(String, int), không có User(String, long).
lookup.findConstructor(
        User.class,
        MethodType.methodType(void.class, String.class, long.class));
```

Trong trường hợp `User(String,long)` không được khai báo, phép tìm thất bại với `NoSuchMethodException`. `findConstructor` tìm một chữ ký **theo kiểu tham số chính xác**; nó không tự đổi `long.class` thành `int.class` khi tra cứu.

Điểm cần phân biệt:

| Trường hợp | Nguyên nhân | Kết quả tiêu biểu |
|---|---|---|
| Request có return type `User.class` | Vi phạm hợp đồng return type phải `void` | `IllegalArgumentException` |
| Request đúng `void` nhưng sai danh sách kiểu tham số | Không có constructor khớp | `NoSuchMethodException` |
| Constructor tồn tại nhưng caller không đủ quyền | Kiểm tra access của `Lookup` không đạt | `IllegalAccessException` |
| Lookup thành công nhưng gọi bằng kiểu không khớp `invokeExact` | Chữ ký tại điểm gọi khác `handle.type()` | `WrongMethodTypeException` |
| Constructor chạy và tự ném ngoại lệ | Lỗi phát sinh trong chính mã đích | Ngoại lệ từ constructor được truyền tới caller |

Điểm cuối có ý nghĩa khi so sánh với `java.lang.reflect.Constructor.newInstance(...)`: API reflection thường bọc ngoại lệ do constructor đích ném trong `InvocationTargetException`, còn method handle thông thường truyền ngoại lệ của mã đích trực tiếp.

## 5. `invokeExact()` phải khớp kiểu của handle **trả về**, không phải kiểu request

Sai lầm phổ biến là thấy `void.class` trong request rồi gọi handle như một hàm không có giá trị trả về:

```java
MethodHandle ctor = lookup.findConstructor(
        User.class,
        MethodType.methodType(void.class, String.class, int.class));

// Lời gọi này đòi kiểu (String,int)void ở điểm gọi,
// nhưng ctor thực tế có kiểu (String,int)User.
ctor.invokeExact("Lan", 21);
```

Vì `invokeExact` là phương thức có chữ ký đặc biệt (*signature-polymorphic*), kiểu tại điểm gọi được xác định theo cách biểu thức được biên dịch. Khi sử dụng như một statement không nhận kết quả, điểm gọi trên yêu cầu kiểu trả về `void`, khác với return type `User` của handle. Khi chạy, điều đó dẫn tới `WrongMethodTypeException`.

Tương tự, phép gán trực tiếp kết quả vào `Object` bằng cast `(Object)` **không** làm `invokeExact` tự nới return type:

```java
// Yêu cầu return type Object ở điểm gọi, nên không khớp.
Object wrong = (Object) ctor.invokeExact("Lan", 21);
```

Nếu muốn giữ `invokeExact` mà nhận vào biến kiểu `Object`, phải dùng chữ ký kết quả `User` ngay tại lời gọi, sau đó mới upcast:

```java
Object correct = (Object) (User) ctor.invokeExact("Lan", 21);
```

Một cách khác là thay đổi kiểu handle bằng adapter `asType(...)`, hoặc dùng `invoke(...)` với những chuyển đổi được phép. Đây là hai cơ chế riêng, không làm thay đổi hợp đồng `findConstructor()`.

### Khi dùng `invoke()`

`invoke(...)` cũng là phương thức signature-polymorphic nhưng có thể áp dụng các phép chuyển kiểu theo quy tắc `asType(...)`, thay vì yêu cầu trùng khớp tuyệt đối như `invokeExact(...)`.

```java
MethodHandle ctor = lookup.findConstructor(
        User.class,
        MethodType.methodType(void.class, String.class, int.class));

// Integer được unbox thành int; User được chuyển lên Object.
Object result = ctor.invoke("Hà", Integer.valueOf(27));

System.out.println(result instanceof User); // true
```

Không phải mọi chuyển đổi đều được chấp nhận. Nếu đối số không thể chuyển thành kiểu handle yêu cầu, lời gọi vẫn có thể thất bại (chẳng hạn `WrongMethodTypeException` hoặc `ClassCastException` tùy tình huống).

### Khi muốn tạo adapter có kiểu rõ ràng

```java
MethodType genericType = MethodType.methodType(
        Object.class, String.class, Integer.class);

MethodHandle adapted = ctor.asType(genericType);

// Sau khi adapt, kiểu chính xác là (String,Integer)Object.
Object value = (Object) adapted.invokeExact(
        "Hà", Integer.valueOf(27));

System.out.println(adapted.type());      // (String,Integer)Object
System.out.println(value instanceof User); // true
```

`adapted` là một handle có kiểu nhìn từ phía caller khác với `ctor`, nhưng vẫn tạo `User` khi gọi. Adapter chịu trách nhiệm chuyển `Integer` sang `int` và trả tham chiếu kết quả dưới dạng `Object`. Nếu cần hiệu năng cao, hãy tạo và tái sử dụng adapter thay vì tạo lại trong từng lần xử lý; hiệu quả cụ thể cần đo trên JDK đang chạy.

## 6. Khác biệt giữa constructor handle và instance method handle

Phương thức instance thông thường cần một **receiver**; constructor handle không cần truyền receiver đã tồn tại.

Giả sử `User` có phương thức `summary()`, ta có thể tìm hai handle:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle makeUser = lookup.findConstructor(
        User.class, MethodType.methodType(
                void.class, String.class, int.class));

MethodHandle summary = lookup.findVirtual(
        User.class, "summary", MethodType.methodType(String.class));

System.out.println(makeUser.type()); // (String,int)User
System.out.println(summary.type());  // (User)String

User user = (User) makeUser.invokeExact("Lan", 21);
String text = (String) summary.invokeExact(user);
System.out.println(text);            // Lan (21)
```

Ở handle của `summary`, tham số đầu `User` chính là receiver. Ở handle constructor, `User` xuất hiện ở **kiểu trả về** vì handle khởi tạo một đối tượng mới.

Có thể hình dung:

```text
Constructor handle: (String, int) --> User mới
Instance method:    (User)        --> String
                       ^
                    receiver đã có
```

Sự khác biệt này giúp tránh thêm nhầm `User.class` vào danh sách tham số của `findConstructor`. Đối số `refc` đã chỉ định lớp được tạo, còn `type.parameterArray()` chỉ chứa **các tham số constructor khai báo**.

## 7. Constructor overload và cách xác định chữ ký

Giả sử có hai constructor cùng tên lớp nhưng khác tham số:

```java
public static final class Service {
    private final String endpoint;
    private final int timeoutMillis;

    public Service(String endpoint) {
        this(endpoint, 1000);
    }

    public Service(String endpoint, int timeoutMillis) {
        this.endpoint = endpoint;
        this.timeoutMillis = timeoutMillis;
    }

    public String description() {
        return endpoint + ":" + timeoutMillis;
    }
}
```

Hai lookup là hai hợp đồng khác nhau:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle withOneArg = lookup.findConstructor(
        Service.class, MethodType.methodType(void.class, String.class));

MethodHandle withTwoArgs = lookup.findConstructor(
        Service.class, MethodType.methodType(
                void.class, String.class, int.class));

Service a = (Service) withOneArg.invokeExact("https://example.test");
Service b = (Service) withTwoArgs.invokeExact(
        "https://example.test", 3000);

System.out.println(a.description()); // https://example.test:1000
System.out.println(b.description()); // https://example.test:3000
```

Việc phân giải overload diễn ra ở bước **tìm handle**, theo danh sách kiểu tham số đã khai báo. Khi gọi `withOneArg`, việc truyền thêm một `int` không làm JVM tự chọn lại constructor hai tham số. Mỗi handle có chữ ký cố định; muốn gọi constructor khác thì tìm handle khác hoặc dùng adapter hợp lệ cho handle mong muốn.

Khi soạn `MethodType`, dùng kiểu nguyên thủy đúng như khai báo (`int.class` thay vì `Integer.class`); `Integer` và `int` là hai kiểu tham số khác nhau tại bước tra cứu. Các chuyển đổi boxing/unboxing (nếu được phép) chỉ diễn ra khi **gọi hoặc adapt** handle, không khiến lookup tự đổi constructor được chọn.

## 8. Quyền truy cập và ranh giới module

`findConstructor(...)` phải kiểm tra quyền truy cập theo **đối tượng `MethodHandles.Lookup` đang dùng**. Một constructor tồn tại không có nghĩa caller nào cũng được quyền lấy handle để gọi.

- `MethodHandles.lookup()` tạo lookup với khả năng truy cập phù hợp **ngữ cảnh lớp caller**. Nó không cấp toàn quyền trên mọi kiểu trong JVM.
- `MethodHandles.publicLookup()` thích hợp khi chỉ cần tìm thành viên công khai có thể truy cập; các ranh giới Java Platform Module System vẫn có hiệu lực.
- `MethodHandles.privateLookupIn(targetClass, lookup)` hỗ trợ tạo lookup cho truy cập sâu khi caller có quyền tương ứng. Việc có thể tìm private constructor phụ thuộc điều kiện truy cập của lookup gốc và package/module của lớp đích, đặc biệt quy tắc `opens` đối với named modules.

Ví dụ, từ một module khác, constructor `public` của một lớp `public` trong package được **export** phù hợp có thể được tìm bằng lookup có quyền truy cập thích hợp. Ngược lại, constructor `private` không tự truy cập được chỉ bằng cách đổi `publicLookup()` thành `lookup()`.

Không dựa vào cờ JVM mở sâu module hoặc API nội bộ để “ép” lookup thành công. Nếu hệ thống cần tạo đối tượng qua constructor không công khai, hãy thiết kế quyền truy cập có chủ đích hoặc sử dụng public factory.

### So sánh với Reflection API

| Tác vụ | Reflection API | MethodHandle API |
|---|---|---|
| Tìm constructor | `Class.getConstructor(...)` / `getDeclaredConstructor(...)` | `Lookup.findConstructor(refc, type)` |
| Biểu diễn chữ ký | `Constructor<?>` mang thông tin constructor, không có return type như `MethodType` | Request dùng `(... )void`; handle có kiểu `(... )refc` |
| Tạo đối tượng | `Constructor.newInstance(args...)` | `handle.invokeExact(...)` / `handle.invoke(...)` |
| Quyền truy cập | Kiểm tra qua `Constructor.newInstance` và khả năng `trySetAccessible()` | Kiểm tra theo khả năng của `Lookup` khi tìm handle |
| Ngoại lệ từ constructor đích | Thường nằm trong `InvocationTargetException` | Thông thường truyền trực tiếp tới caller |
| Kiểm soát kiểu tại điểm gọi | Đối số dạng `Object...` | `MethodType` và chữ ký `invokeExact`/`invoke` |

Một `Constructor<?>` được tìm bằng `getDeclaredConstructor(...)` có thể mô tả constructor `private` mà caller chưa được phép gọi. Tương tự, `findConstructor(...)` phải thực hiện kiểm tra quyền trước khi trả về handle; hai API giải quyết nhu cầu khác nhau và không nên xem thay đổi API là cách bỏ qua quyền truy cập.

## 9. Xử lý lỗi chính xác

Khi xử lý thực tế, có thể tách lỗi thành ba nhóm:

1. **Lỗi yêu cầu tra cứu**: return type của request không là `void`; danh sách tham số không trùng constructor nào.
2. **Lỗi quyền truy cập**: constructor có thật nhưng lookup hiện tại không được phép truy cập, bao gồm các quy tắc named module.
3. **Lỗi lúc gọi**: chữ ký `invokeExact` không khớp, đối số không chuyển đổi được, hoặc logic constructor phát sinh ngoại lệ.

Ví dụ minh họa cách phân loại:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

try {
    lookup.findConstructor(User.class,
            MethodType.methodType(User.class, String.class, int.class));
} catch (IllegalArgumentException invalidRequest) {
    System.out.println("Request phải có return type void");
}

try {
    lookup.findConstructor(User.class,
            MethodType.methodType(void.class, String.class, long.class));
} catch (NoSuchMethodException noMatchingConstructor) {
    System.out.println("Không có User(String, long)");
}
```

Trong ví dụ ở phần 3, constructor `User` tự kiểm tra `age` và ném `IllegalArgumentException` khi âm. Một lời gọi có chữ ký chính xác vẫn có thể thất bại do **nghiệp vụ bên trong constructor**:

```java
MethodHandle ctor = lookup.findConstructor(
        User.class,
        MethodType.methodType(void.class, String.class, int.class));

try {
    User invalid = (User) ctor.invokeExact("Lan", -1);
} catch (IllegalArgumentException fromConstructor) {
    System.out.println(fromConstructor.getMessage());
    // age must be >= 0
}
```

`findConstructor` trả về handle có thể gọi được không có nghĩa mọi đối số đều thỏa điều kiện nghiệp vụ. Khi chẩn đoán, trước hết xem lỗi xảy ra ở **lookup** hay **invocation**, sau đó mới quyết định sửa chữ ký, cấu hình quyền hoặc dữ liệu đầu vào.

## 10. Cache handle và hiệu năng trên JDK hiện đại

Nếu một framework tạo hàng triệu đối tượng cùng lớp, việc tìm lại metadata và tạo handle trên mọi request sẽ gộp chi phí **tra cứu/chuẩn bị** vào đường xử lý lặp lại. Thường nên:

1. Dùng `findConstructor` trong pha khởi tạo component hoặc xây mapping.
2. Lưu `MethodHandle` có kiểu đã kiểm tra trong cấu trúc dùng chung có quản lý vòng đời.
3. Tại hot path, gọi handle với đúng kiểu, tránh tự tạo lại `MethodType`/adapter nếu không cần.
4. Kiểm thử tính đúng đắn của các lần gọi và đo trên JDK thực tế trước khi quyết định giữa Reflection, constructor handle hay public factory.

JEP 416 ở Java 18 thay đổi cách triển khai nội bộ Core Reflection dựa trên method handles, nhưng không hứa `MethodHandle` **luôn** nhanh hơn `Constructor.newInstance(...)` trong mọi trường hợp. Hiệu năng còn phụ thuộc khả năng JIT nhìn thấy handle, cách giữ tham chiếu, cách truyền tham số, boxing, adapter, warmup và thời gian chạy chính constructor. Không suy diễn tốc độ hiện tại từ số liệu ở JDK cũ.

## 11. Kiểm chứng hợp đồng bằng các ca thử

Các phép thử dưới đây tách riêng **kiểu request** và **kiểu handle**, tránh chỉ thử đối tượng trả về:

| Kiểm tra | Hành động | Kỳ vọng |
|---|---|---|
| Return type của request | `request.returnType()` | `void.class` |
| Return type của handle | `ctor.type().returnType()` | `User.class` |
| Danh sách tham số giữ nguyên | So sánh `request.parameterArray()` và `ctor.type().parameterArray()` | Cùng `String.class`, `int.class` |
| Gọi đúng `invokeExact` | `(User) ctor.invokeExact("Lan", 21)` | Trả đối tượng `User` mới |
| Gọi constructor lần hai | Lấy hai kết quả, so sánh tham chiếu | Hai tham chiếu khác nhau |
| Request sai return type | Yêu cầu `(String,int)User` | `IllegalArgumentException` |
| Request sai tham số | Yêu cầu `(String,long)void` | `NoSuchMethodException` |
| Gọi `invokeExact` với return type khác | Nhận trực tiếp kiểu `Object` thay `User` | `WrongMethodTypeException` |
| Constructor kiểm tra tuổi âm | Gọi `(User) ctor.invokeExact("Lan", -1)` | `IllegalArgumentException` do constructor ném |

Ví dụ các assertion đơn giản; đặt trong một phương thức có xử lý ngoại lệ thích hợp:

```java
MethodType request = MethodType.methodType(
        void.class, String.class, int.class);
MethodHandle ctor = MethodHandles.lookup()
        .findConstructor(User.class, request);

if (request.returnType() != void.class) {
    throw new AssertionError("Request phải là void");
}
if (ctor.type().returnType() != User.class) {
    throw new AssertionError("Handle phải trả User");
}
if (!ctor.type().equals(
        MethodType.methodType(User.class, String.class, int.class))) {
    throw new AssertionError("Kiểu handle không đúng");
}
```

Cần chạy thử trên phiên bản JDK đang sử dụng, đặc biệt trong hệ thống có named modules, vì quyền lookup phụ thuộc ngữ cảnh đóng gói và caller. Hợp đồng `void` ở request và kiểu đối tượng ở handle là yếu tố ổn định cần bảo vệ khi nâng JDK.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `findConstructor(User.class, MethodType.methodType(User.class, String.class))` là một yêu cầu sai dù constructor có thể tạo `User`?
2. Nếu request hợp lệ có kiểu `(String,int)void`, tại sao handle nhận được có kiểu `(String,int)User`?
3. Khi gọi `invokeExact`, phải dùng kiểu trả về nào ở điểm gọi? Điều gì xảy ra nếu dùng trực tiếp `Object` thay `User`?
4. `findConstructor(...)` có tạo một đối tượng ngay khi lookup thành công hay không? Bước nào tạo đối tượng?
5. Constructor handle khác gì với handle lấy bằng `findVirtual(...)` về vị trí receiver và kiểu trả về?
6. Sai chữ ký constructor, thiếu quyền truy cập và exception do constructor tự ném khác nhau ra sao?

**Ghi nhớ:** `findConstructor()` yêu cầu `MethodType` có **return type `void`** để tìm đúng constructor; `MethodHandle` trả về có **return type là lớp cần khởi tạo** để gọi và nhận đối tượng mới. Khi dùng `invokeExact()`, phải khớp kiểu của **handle thực tế**, không dùng kiểu `void` của request để suy ra kiểu lời gọi.
