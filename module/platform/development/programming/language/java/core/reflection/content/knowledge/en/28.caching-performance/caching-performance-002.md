# Cache Field, Method và Constructor theo ngữ cảnh phù hợp

## 1. Vì sao và khi nào nên cache metadata Reflection?

Trong Java Reflection, một chương trình có thể tìm metadata của class bằng những API như `Class.getDeclaredField(...)`, `getDeclaredMethod(...)`, `getDeclaredConstructor(...)`, sau đó dùng đối tượng `Field`, `Method` hoặc `Constructor` để đọc/ghi field, gọi phương thức hoặc tạo object.

Nếu một framework lặp đi lặp lại thao tác **tra cứu đúng cùng một thành viên** khi xử lý hàng nghìn đối tượng, việc tìm metadata nhiều lần có thể tạo chi phí không cần thiết. Cache cho phép tách hai việc:

1. **Khám phá thành viên một lần** trong một ngữ cảnh cụ thể: tên class, tên thành viên, kiểu tham số, quyền truy cập.
2. **Sử dụng metadata đã tìm** cho những receiver hoặc đối số phù hợp trong các lần thao tác tiếp theo.

Ví dụ, một serializer ghi giá trị field `name` cho rất nhiều đối tượng `Person` có thể tra cứu `Field` đó một lần rồi dùng `field.get(person)` trên từng instance. Một dependency injector có thể cache constructor đã lựa chọn theo loại component; một router có thể cache method tương ứng với endpoint cố định.

Tuy nhiên **cache không mặc nhiên làm lời gọi Reflection nhanh như lời gọi Java trực tiếp**. Nó chủ yếu tránh chi phí tra cứu metadata lặp lại. `Method.invoke(...)` vẫn có chi phí gọi gián tiếp, kiểm tra kiểu, boxing/unboxing hoặc xử lý ngoại lệ phù hợp. Cơ chế thực thi Reflection và JIT có thể khác nhau giữa các phiên bản JDK. Hãy tối ưu dựa trên profile/benchmark khi performance là yêu cầu thật.

### Mô hình ba lớp

```text
Đặc tả cần truy cập
  └── Class + loại thành viên + tên + chữ ký + chính sách quyền
        ↓
Tra cứu/kiểm tra một lần
  └── Field / Method / Constructor
        ↓
Cache theo ngữ cảnh phù hợp
  └── Metadata đã được chọn
        ↓
Dùng cho từng object/lần gọi
  └── Field.get/set | Method.invoke | Constructor.newInstance
```

Điều quan trọng nhất không phải “đưa mọi thứ vào static Map”, mà là chọn **đúng đơn vị tái sử dụng, khóa cache và vòng đời cache**.

## 2. Thông tin cần lưu của Field, Method, Constructor

Ba loại metadata đều thuộc Reflection nhưng có quy tắc tra cứu và sử dụng khác nhau:

| Loại | Tra cứu thông thường | Khóa nhận diện cần thiết | Sử dụng sau khi cache |
| --- | --- | --- | --- |
| `Field` | `getDeclaredField("name")` / `getField("name")` | Lớp/ngữ cảnh khai báo, tên field, chính sách tìm declared/public | `field.get(receiver)`, `field.set(receiver, value)` |
| `Method` | `getDeclaredMethod("save", String.class)` / `getMethod(...)` | Lớp/ngữ cảnh tìm, **tên và danh sách kiểu tham số theo đúng thứ tự**, chính sách tìm | `method.invoke(receiver, args...)` |
| `Constructor` | `getDeclaredConstructor(String.class)` / `getConstructor(...)` | Lớp cần tạo và **danh sách kiểu tham số**, chính sách tìm | `constructor.newInstance(args...)` |

- **Instance receiver không phải một phần của khóa metadata** nếu cùng một `Field`/`Method` có thể dùng với nhiều instance cùng loại phù hợp. Đừng cache từng đối tượng nghiệp vụ chỉ để tránh tra cứu cùng field.
- **Field** được tra cứu theo tên. Kiểu field có thể được kiểm tra qua `field.getType()` khi cần, nhưng tên cùng chính sách tra cứu/lớp là cơ sở nhận diện trong các API nói trên.
- **Method** có thể overload. Ví dụ `parse(String)` và `parse(int)` là hai method khác nhau; cache chỉ theo tên `"parse"` là sai. Khi dùng `getDeclaredMethod` hay `getMethod`, danh sách tham số quyết định overload. Các API tra cứu Java Reflection này không nhận kiểu trả về làm tham số; nếu hệ thống yêu cầu kiểm tra return type, so sánh thêm `method.getReturnType()` theo hợp đồng của hệ thống.
- **Constructor** không có tên riêng để truyền vào API tra cứu. Khóa cần lớp và các kiểu tham số; `getDeclaredConstructor()` không đồng nghĩa với “chọn constructor bất kỳ”.
- `getDeclaredXxx` tra cứu thành viên **khai báo trực tiếp** ở lớp được hỏi, kể cả non-public, nhưng không tự duyệt toàn bộ cấp cha cho mọi loại thành viên. `getXxx` công khai tìm public member theo quy tắc kế thừa. Hai chiến lược tra cứu này không được dùng chung cache key khi ý nghĩa khác nhau.

Cũng phải phân biệt **cache đối tượng mô tả** với **cache kết quả đọc dữ liệu**. Cache `Field` có thể hợp lệ; cache `field.get(person)` thì sẽ giữ một giá trị từ một thời điểm, có thể đã lỗi thời nếu field thay đổi.

## 3. Thiết kế khóa cache an toàn

Nếu cache phục vụ một class cố định cùng danh sách thành viên cố định, có thể tạo một bộ metadata gắn với class đó. Nếu cache dùng cho nhiều class, overload và chiến lược lookup, cần khóa mô tả đầy đủ.

Một khóa cho method động có thể được định nghĩa như sau:

```java
record MethodKey(
        Class<?> owner,
        String name,
        java.util.List<Class<?>> parameterTypes,
        boolean declaredOnly) {}
```

Đoạn này chỉ minh họa khai báo khóa, không phải chương trình độc lập. Khi tạo key, dùng một danh sách **bất biến được copy từ các kiểu tham số**, chẳng hạn:

```java
MethodKey key = new MethodKey(
        Person.class,
        "greet",
        java.util.List.of(String.class),
        true
);
```

Những điểm cần xem xét khi triển khai cache thật:

1. **Lớp `Class<?>` xác định theo identity, gồm cả classloader**. Hai lớp có cùng tên đầy đủ nhưng do hai classloader khác nhau nạp là hai `Class` khác nhau; dùng `getName()` làm toàn bộ khóa có thể gây nhầm metadata.
2. **Overload phải có đầy đủ signature**. Đối với danh sách tham số do caller cung cấp, sao chép sang danh sách bất biến trước khi đưa vào khóa; đừng giữ một array có thể bị thay đổi làm nguồn hash/equality.
3. **Phạm vi tìm thành viên** phải được cố định: declared-only, public/inherited hoặc thuật toán tìm thủ công trên cây lớp. Cùng tên và signature nhưng lookup policy khác có thể cho kết quả khác.
4. **Quyền và ngữ cảnh caller** không tự suy ra chỉ từ tên lớp. Nếu framework tạo metadata đã được `setAccessible(true)` hoặc tạo handle bằng lookup có đặc quyền, đừng phát tán đối tượng đó qua một cache toàn cục mà code ít tin cậy cũng đọc được.
5. **Chính sách chọn constructor** phải ổn định: nếu framework chọn theo annotation, visibility hay config, những yếu tố ấy thuộc hợp đồng của cache. Thay đổi quy tắc chọn phải làm mất hiệu lực entry thích hợp.

Ví dụ sai:

```java
// Sai: hai overload save(String) và save(int) bị gộp vào cùng key.
java.util.Map<String, java.lang.reflect.Method> methodsByName;
```

Ví dụ tốt hơn về cấu trúc, khi mỗi class có cache riêng:

```java
record Signature(String name, java.util.List<Class<?>> params) {}

java.util.concurrent.ConcurrentMap<Signature, java.lang.reflect.Method> methods;
```

Hai khai báo trên là các mảnh của một thiết kế, chưa khởi tạo biến hay xử lý ngoại lệ. Class chủ sở hữu có thể là khóa ở lớp ngoài; khi cache theo class, inner key chỉ cần mô tả các method **bên trong** đúng lớp/ngữ cảnh đó.

## 4. Chọn phạm vi cache theo vòng đời hệ thống

Có nhiều phạm vi hợp lệ. Chọn theo mức ổn định của class, quyền truy cập và thời gian tồn tại:

| Phạm vi | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Biến local trong một đợt xử lý | Chỉ dùng lặp lại trong một request/batch | Dễ kiểm soát, không giữ class/object lâu hơn batch |
| Một service hoặc component | Service cố định một vài kiểu DTO/domain | Cache sống theo vòng đời service, dễ invalidation |
| Theo mỗi `Class<?>` với `ClassValue<T>` | Thư viện xử lý nhiều lớp, muốn dữ liệu gắn với lớp và vòng đời lớp | Phù hợp hơn static map mạnh trong môi trường classloader thay đổi |
| Cache dùng chung theo key đầy đủ | Nhiều entry động, công việc thực sự tái sử dụng metadata | Cần kiểm soát quyền, đồng thời, kích thước và classloader |

### Nguy cơ static Map giữ classloader

Một cache cấp ứng dụng như:

```java
static final java.util.Map<Class<?>, Object> CACHE = new java.util.concurrent.ConcurrentHashMap<>();
```

có **strong reference** tới `Class<?>` và giá trị. Nếu cache sống lâu hơn plugin, deployment hoặc classloader chứa class, nó có thể ngăn các class/classloader đó được thu gom. Đây là vấn đề thực tế với application server có hot deploy, plugin system, IDE, framework dùng generated classes.

Chuyển khóa sang `WeakHashMap<Class<?>, Field>` **không tự động giải quyết mọi leak**: giá trị `Field`/`Method` có thể tham chiếu ngược tới declaring class, tạo đường strong reference từ map đến chính khóa qua value. Dùng `ClassValue` hoặc cache được quản lý theo vòng đời component/classloader thường rõ ràng hơn. Nếu vẫn dùng map lâu sống, cần có lifecycle cleanup, giới hạn số entry phù hợp và kiểm tra tham chiếu giữ lại.

### `ClassValue<T>`

`ClassValue<T>` cung cấp ánh xạ giá trị **theo từng `Class<?>`**, hữu ích khi muốn giữ metadata thuộc về một class mà không xây một static map mạnh theo class. Khi `ClassValue.get(type)` chưa có giá trị cho class ấy, `computeValue(type)` sẽ được gọi để tính.

```java
ClassValue<SomeMetadata> cache = new ClassValue<>() {
    @Override
    protected SomeMetadata computeValue(Class<?> type) {
        // Khám phá và tạo metadata cho chính type này.
        return buildMetadata(type);
    }
};
```

Đây là **pseudocode Java theo hợp đồng**: `SomeMetadata` và `buildMetadata` phải được định nghĩa trong ứng dụng; ví dụ hoàn chỉnh ở mục 6.

`ClassValue` hỗ trợ truy cập đồng thời, nhưng **`computeValue` có thể bị gọi nhiều lần cho cùng một class khi có cạnh tranh**; chỉ một giá trị phù hợp được xuất bản cho các `get` thành công. Vì vậy, hàm compute nên thuần hoặc có tác dụng phụ an toàn, không khởi chạy một lần duy nhất các hành động không thể lặp. `ClassValue.remove(type)` cho phép bỏ giá trị của class, nhưng khi có thread đang tính hoặc đọc đồng thời, cần thiết kế lại quy trình invalidation thật cẩn thận.

## 5. Quyền truy cập: cache metadata không phải giấy phép vượt private/module

Mỗi `Field`, `Method` và `Constructor` là một đối tượng phản chiếu. Tra cứu được một member **không có nghĩa** mọi caller đều được phép thao tác trên member đó.

- Với member public ở class public/package exported hợp lệ, thường có thể dùng các phương thức `getField`, `getMethod`, `getConstructor` mà không cần nới quyền.
- Với member private/package-private, thao tác reflective có thể bị chặn vì access control. `setAccessible(true)` chỉ thành công khi Java language/module rules cho phép mở quyền; trong named modules, `opens` và quan hệ module có thể quyết định kết quả.
- Nếu không có quyền mở truy cập, `setAccessible(true)` có thể ném `InaccessibleObjectException`, một unchecked exception. Tùy nhu cầu có thể sử dụng `trySetAccessible()` để nhận tín hiệu `false` khi không thể bật, rồi phản hồi phù hợp.
- **Cờ accessible của đối tượng `AccessibleObject` là trạng thái mutable**. Nếu một thành phần đã bật quyền rồi chia sẻ cùng `Method`/`Field` cho code không tin cậy, đó có thể là vấn đề bảo mật. Cache metadata nên nằm trong phạm vi dịch vụ tin cậy sử dụng nó.
- Reflection không làm mất đi cơ chế bảo vệ riêng của module, cũng không khiến field `final` bình thường trở thành điểm cập nhật tùy ý theo mọi hoàn cảnh.

**Quy trình khuyến nghị:** cache khi đã xác định chắc chắn member cần thao tác và quyền cần thiết; tập trung logic truy cập vào component có trách nhiệm. Đừng gọi `setAccessible(true)` đại trà lên mọi field của mọi class, vì dễ vi phạm chính sách module và tạo bề mặt truy cập rộng.

## 6. Ví dụ độc lập Java 17+: cache ba loại member bằng ClassValue

Ví dụ dưới đây có một lớp `Person` với constructor, field và method private. Cache chứa cả ba metadata, mỗi lần gọi `CACHE.get(Person.class)` đều nhận bộ member cho đúng `Person`. Việc mở quyền thành công trong ví dụ vì `Person` là nested class cùng **nest** với lớp truy cập, nên Java cho phép ngữ cảnh này truy cập private member; không được mặc định điều đó khi đổi sang class thuộc module khác.

Lưu file **`ReflectionCacheDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionCacheDemo {
    private static class Person {
        private String name;

        private Person(String name) {
            this.name = name;
        }

        private String greet(String greeting) {
            return greeting + " " + name;
        }
    }

    private record Accessors(
            Constructor<?> constructor,
            Field field,
            Method method) {
    }

    private static final ClassValue<Accessors> CACHE = new ClassValue<>() {
        @Override
        protected Accessors computeValue(Class<?> type) {
            if (type != Person.class) {
                throw new IllegalArgumentException("Class not supported");
            }
            try {
                Constructor<?> constructor =
                        type.getDeclaredConstructor(String.class);
                Field field = type.getDeclaredField("name");
                Method method = type.getDeclaredMethod("greet", String.class);

                constructor.setAccessible(true);
                field.setAccessible(true);
                method.setAccessible(true);

                return new Accessors(constructor, field, method);
            } catch (ReflectiveOperationException ex) {
                throw new IllegalStateException("Cannot resolve members", ex);
            }
        }
    };

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Accessors a = CACHE.get(Person.class);
        Person person = (Person) a.constructor().newInstance("Lan");

        System.out.println(a.field().get(person));
        System.out.println(a.method().invoke(person, "Hello,"));

        a.field().set(person, "Minh");
        System.out.println(a.method().invoke(person, "Hi,"));

        System.out.println(a == CACHE.get(Person.class));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ReflectionCacheDemo.java
java ReflectionCacheDemo
```

Kết quả:

```text
Lan
Hello, Lan
Hi, Minh
true
```

Giải thích:

1. Lần đầu `CACHE.get(Person.class)` cần tạo `Accessors` bằng `computeValue`: tìm constructor `Person(String)`, field `name` và method `greet(String)`.
2. Bộ metadata được dùng để tạo một object `Person("Lan")`, đọc field và gọi method. Không cần tra cứu lại mỗi lần gọi `get`/`invoke`.
3. Sau khi đổi field trên instance thành `"Minh"`, gọi method đã cache sẽ thấy **giá trị hiện tại** của instance; cache metadata không đóng băng dữ liệu nghiệp vụ.
4. Trong lần chạy tuần tự này, `CACHE.get(Person.class)` lần sau trả cùng tham chiếu `Accessors`, nên so sánh bằng `==` in `true`.

Vì `setAccessible(true)` có thể không hợp lệ ở các ngữ cảnh khác, ví dụ này **không** khuyến khích cấp quyền private cho mọi class. Với member public, nên ưu tiên tra cứu/truy cập public thông thường. Trong triển khai thực tế, việc bắt `ReflectiveOperationException` trong `computeValue` chưa xử lý `InaccessibleObjectException` (unchecked) nếu cấu hình module không cho phép; cần báo rõ lỗi cấu hình thay vì che giấu.

## 7. Cache nhiều member của cùng một lớp

Trong serializer hoặc framework, mỗi lớp có thể có hàng chục field và method. Khi đó một `ClassValue` có thể giữ **bảng metadata riêng cho từng class**:

```text
ClassValue<PerClassCache>
   |
   +-- Person.class → PerClassCache
   |       +-- Field "name"
   |       +-- Method ("greet", [String])
   |       +-- Constructor ([String])
   |
   +-- Order.class → PerClassCache
           +-- Field "status"
           +-- Method ("update", [int])
           +-- Constructor ([long])
```

Thiết kế một `PerClassCache` gồm nhiều `ConcurrentHashMap`, mỗi map dùng kiểu khóa phù hợp. Cách này:

- Giảm việc giữ trực tiếp `Class<?>` trong static map toàn cục.
- Tập trung chính sách tìm member và quyền truy cập trong mỗi class.
- Cho phép lazy lookup theo tên/signature thay vì khám phá toàn bộ member khi chưa cần.
- Dễ gắn metrics về số cache hit/miss nếu thật sự cần tối ưu.

### ConcurrentHashMap và checked exception

Lệnh `computeIfAbsent` tiện lợi nhưng hàm mapping không được khai báo ném checked `NoSuchMethodException`. Một ví dụ rút gọn minh họa cách bọc lỗi:

```java
Method result = methods.computeIfAbsent(key, k -> {
    try {
        return owner.getDeclaredMethod(
                k.name(),
                k.parameterTypes().toArray(Class<?>[]::new)
        );
    } catch (NoSuchMethodException ex) {
        throw new IllegalArgumentException("Method not found: " + k, ex);
    }
});
```

Đây là **đoạn minh họa trong một implementation `PerClassCache`**, không phải file Java chạy độc lập. Nó giả định có `methods: ConcurrentHashMap<Signature,Method>`, `key: Signature`, `owner: Class<?>` và `Signature` cung cấp `name()`/`parameterTypes()`. Một hệ thống thật cần quyết định trước cách xử lý lỗi: `computeIfAbsent` không cache kết quả `null` hay exception; truy vấn luôn thất bại có thể tiếp tục tốn chi phí nếu được gọi đi gọi lại.

Khi concurrency cao, mapping function có thể tạo tranh chấp khóa. Không đặt tác vụ I/O, truy vấn mạng, gọi lại vòng vào cùng map hoặc tác dụng phụ nặng trong compute. Xây key bất biến rồi cache thành viên có giá trị hợp lệ; khi metadata hết hiệu lực theo lifecycle, hủy cả cache liên quan.

## 8. Những trường hợp phải cẩn thận

### a) Method overload và method được kế thừa

Với `UserService.save(User)` và `UserService.save(String)`, khóa `(name="save")` không đủ. Nếu dùng `getDeclaredMethod` trên subclass, member kế thừa không nhất thiết hiện diện trong danh sách declared. Hãy cố định thuật toán tra cứu và chữ ký; nếu chuyển sang `getMethod` hoặc duyệt superclass thủ công, cần khóa/cấu hình phân biệt đúng hành vi.

### b) Proxy và nhiều classloader

Framework tạo proxy class có thể sử dụng nhiều `Class<?>` dù các class có cấu trúc tương tự. `Method` tìm cho class A không tự nhiên phù hợp với mọi proxy hoặc class cùng tên do loader khác nạp. Với `Method.invoke`, receiver thực tế phải tương thích với **declaring class** của method đó. Cache theo classloader chỉ bằng string như `"com.example.User"` là thiếu an toàn.

### c) Truy cập bất đồng bộ và đối tượng metadata dùng chung

`Field`, `Method` và `Constructor` có thể được tái sử dụng khi nhiều thread cùng gọi thông qua Reflection; điều đó không có nghĩa **đối tượng nghiệp vụ được truy cập tự động thread-safe**. Ví dụ `field.set(...)` cùng field trên một object không tạo atomicity/happens-before theo ý muốn. Nếu bài toán cần kiểm soát memory ordering hay CAS, xem `VarHandle` hoặc primitive đồng bộ tương ứng, không chỉ cache `Field`.

### d) Cache stale hoặc thay đổi mô hình runtime

Thay một class bằng phiên bản nạp từ classloader mới tạo ra **Class object khác**. Cần tìm metadata từ class mới. Với plugin reload, hot redeploy, instrumentation hoặc schema mapping thay đổi, định nghĩa rõ lúc nào bỏ cache theo loader/component/phiên bản. `ClassValue.remove(type)` chỉ loại entry gắn với `type` đó; không có nghĩa xóa mọi cấu trúc tham chiếu liên quan bên ngoài.

### e) Memory cost và lợi ích nhỏ

Nếu thành viên chỉ được gọi một lần, tạo map, key, synchronization và entry cache có thể tốn nhiều hơn việc tra cứu trực tiếp. Nếu một ứng dụng quét rất nhiều class nhưng chỉ sử dụng một phần nhỏ member, cache tất cả có thể tốn bộ nhớ. Với hot loop, cần đo riêng **chi phí tìm metadata** và **chi phí gọi member**, thay vì chỉ benchmark chung và gán mọi cải thiện cho cache.

### f) Dữ liệu nhạy cảm và phạm vi tin cậy

Một shared cache cho phép truy cập metadata private đã mở quyền có thể vô tình tạo khả năng truy cập từ component khác. Thiết kế ownership rõ ràng: chỉ code có quyền mới lấy hoặc nhận member đặc quyền; không công khai map member được bật accessible thành một service đa tenant mà không có kiểm tra quyền.

## 9. Đo hiệu năng đúng cách

Nếu mục tiêu là giảm độ trễ, hãy thử hai đường đi:

- **Không cache:** mỗi vòng gọi `getDeclaredMethod(...)` rồi `invoke(...)`.
- **Có cache:** tìm một lần hoặc lấy `Method` từ cache rồi `invoke(...)`.

Nhưng cần tách các chi phí: tạo key, cache hit/miss, lookup, invocation, autoboxing, kết quả và độ trễ của chính method được gọi. Nếu method làm I/O vài mili giây, tối ưu metadata có thể không đáng kể. Nếu call site rất nóng, cân nhắc giao diện trực tiếp hoặc `MethodHandle` sau khi đã đo và khi thiết kế cho phép.

Nên dùng JMH hoặc công cụ đo phù hợp có warmup, nhiều lần chạy, fork JVM, kiểm soát Dead Code Elimination và GC. Tránh kết luận từ một vòng `System.nanoTime()` đơn lẻ. Đặc biệt, **thời gian cache hit không bằng 0**: concurrent map lookup, key construction và memory footprint đều có giá.

Metrics hữu ích có thể gồm: số lớp/entry đang cache, số lần build metadata, cache hit/miss, số lỗi access/lookup, thời gian xử lý mỗi loại request, tổng heap giữ bởi cache và số classloader được giữ lại sau redeploy. Chọn số đo gắn với câu hỏi hiệu năng thực tế, không thêm cache chỉ vì mã “trông nhanh hơn”.

## 10. Quy trình quyết định và thực hành

Trước khi cache một thành viên Reflection, lần lượt trả lời:

1. **Có lặp lại đủ nhiều không?** Nếu chỉ tra cứu một lần, chưa cần cache.
2. **Khóa đã xác định đúng member chưa?** Với method/constructor phải có tham số đúng thứ tự; phân biệt declared và public lookup.
3. **Phạm vi và vòng đời là gì?** Request, component, class hay classloader; có plugin/redeploy không?
4. **Quyền của người dùng cache có thống nhất không?** Tránh đưa member đã nới quyền vào cache dùng bởi nhiều vùng tin cậy khác nhau.
5. **Cạnh tranh và invalidation ra sao?** Dùng cấu trúc concurrency phù hợp; xử lý lookup thất bại rõ ràng, không side effect nhạy cảm trong compute.
6. **Đã đo đúng nút thắt chưa?** Nếu chi phí nằm ở invoke hoặc công việc nghiệp vụ, cache lookup có thể chưa đủ.

### Bài tập tự kiểm tra

- Tạo hai method overload `convert(String)` và `convert(int)`. Giải thích vì sao map theo chuỗi `"convert"` là sai và thiết kế khóa phân biệt cả hai.
- Trong ví dụ `ReflectionCacheDemo`, dùng cùng `Accessors` trên hai object `Person` khác nhau. Cache lưu metadata nào, và giá trị `name` của từng object có ảnh hưởng nhau không?
- Chuyển `Person` sang một named module khác không `opens` package cho bên gọi. Giải thích vì sao `setAccessible(true)` có thể thất bại ngay cả khi lookup member thành công.
- Một plugin được nạp và gỡ liên tục. Vì sao static `ConcurrentHashMap<Class<?>,Method>` có thể giữ classloader cũ, và `ClassValue` giải quyết bài toán quản lý metadata theo class ra sao?
- Nếu một ứng dụng xử lý 100 request nhưng chỉ có 2 request dùng một method hiếm, cache eager toàn bộ method của class có chắc hiệu quả không? Bạn sẽ đo điều gì?

**Kết quả cần đạt:** biết khi nào cache `Field`/`Method`/`Constructor` có lợi, xây khóa cache phù hợp với chữ ký và chiến lược lookup, giữ đúng phạm vi quyền truy cập, tránh rò rỉ classloader và kiểm chứng hiệu năng bằng dữ liệu đo thực tế.
