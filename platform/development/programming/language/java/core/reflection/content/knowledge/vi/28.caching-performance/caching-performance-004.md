# ClassValue: lưu dữ liệu tính toán riêng cho từng Class trong Java

## 1. Bài toán: cache metadata gắn với runtime class

Với Java Reflection, các thao tác như `getDeclaredMethods()`, `getDeclaredFields()`, đọc annotation hoặc phân tích cấu trúc lớp có thể lặp lại rất nhiều lần. Nếu mỗi request đều dựng lại danh sách metadata và bảng ánh xạ từ tên method sang `Method`, chương trình tốn công tính toán và cấp phát bộ nhớ.

Một lựa chọn thường gặp là tạo `Map<Class<?>, Metadata>`:

```java
// Ví dụ minh họa, chưa phải lời giải đầy đủ:
// private static final Map<Class<?>, Metadata> CACHE = ...
Metadata metadata = CACHE.get(type);
```

Tuy nhiên, với map dùng **strong key** tồn tại suốt vòng đời ứng dụng, khóa `Class<?>` có thể giữ tham chiếu tới class và class loader của plugin/module mà chương trình đã ngừng sử dụng. Việc đồng bộ hóa tính toán, tránh xây dữ liệu nhiều lần và xử lý class unloading cũng trở thành trách nhiệm riêng của người viết cache.

**`java.lang.ClassValue<T>`** được thiết kế cho trường hợp **một giá trị kiểu `T` gắn với từng đối tượng `Class<?>`**. Chúng ta mô tả cách tính giá trị bằng `computeValue(Class<?> type)` rồi lấy nó bằng `get(type)`. JVM/JDK quản lý mối liên kết từ mỗi `Class` tới giá trị tương ứng của từng `ClassValue`.

Ví dụ ứng dụng:

- Cache danh sách method hoặc field của mỗi class phục vụ cơ chế serialize/binding/dispatch.
- Lưu metadata đã phân tích từ annotation của từng kiểu.
- Lưu codec, descriptor hoặc thông tin cấu hình được suy ra **chỉ từ class**, không từ object cụ thể.
- Giảm số lần phân tích Reflection trong thư viện/framework có thể gặp nhiều class và class loader khác nhau.

`ClassValue` không tạo ra field thật trong bytecode của class, không thay đổi `Class<?>`, không tự gọi method nghiệp vụ và không phải cơ chế lưu trạng thái **riêng cho từng object instance**.

## 2. API cốt lõi và phạm vi khóa

Phác thảo chữ ký các thành viên quan trọng của `ClassValue<T>`:

```java
public abstract class ClassValue<T> {
    protected ClassValue();
    protected abstract T computeValue(Class<?> type);
    public T get(Class<?> type);
    public void remove(Class<?> type);
}
```

Đây là phần **chữ ký minh họa**, không phải một class người học tự định nghĩa; sử dụng implementation của JDK qua `java.lang.ClassValue`.

| API | Vai trò | Lưu ý |
|---|---|---|
| `new ClassValue<T>() { ... }` | Tạo một đối tượng cache với hàm tính giá trị cụ thể | Phải override `computeValue` |
| `computeValue(Class<?> type)` | Tính dữ liệu ứng với một class khi cần | Có thể được gọi hơn một lần cho cùng class trong tình huống cạnh tranh |
| `get(Class<?> type)` | Trả giá trị hiện gắn với cặp `(ClassValue instance, Class<?>)`; khi chưa có sẽ yêu cầu tính | Không cần tự quản lý `Map<Class<?>,T>` |
| `remove(Class<?> type)` | Loại giá trị đang gắn cho class cụ thể để lần đọc tiếp theo có thể tính lại | Chỉ ảnh hưởng **một class trong một ClassValue**; không có thao tác xóa toàn bộ cache tương đương `Map.clear()` |

Ví dụ gọi:

```java
ClassValue<String> simpleNames = new ClassValue<>() {
    @Override
    protected String computeValue(Class<?> type) {
        return type.getSimpleName();
    }
};

System.out.println(simpleNames.get(String.class)); // String
System.out.println(simpleNames.get(Integer.class)); // Integer
```

Đây là đoạn chạy được khi đặt vào thân một phương thức Java; không cần tạo instance `String` hoặc `Integer` vì khóa là **runtime class**, không phải object.

### Cặp khóa thực tế gồm hai identity

Hãy hình dung một bảng tra cứu logic:

```text
(ClassValue A, Alpha.class) --> giá trị A/Alpha
(ClassValue A, Beta.class)  --> giá trị A/Beta
(ClassValue B, Alpha.class) --> giá trị B/Alpha
```

Mỗi instance `ClassValue` có một không gian giá trị độc lập. `get(Alpha.class)` ở `ClassValue A` không dùng chung kết quả với cùng lời gọi ở `ClassValue B`. Đồng thời, hai đối tượng của cùng một class `Alpha` đều có chung **class key** nếu lấy metadata qua cùng một `ClassValue`.

## 3. Vòng đời: tính lười, đọc lại, xóa rồi tính lại

Ở luồng đơn, cơ chế cơ bản là:

1. Khởi tạo instance `ClassValue<T>` cùng cài đặt `computeValue`.
2. `get(Alpha.class)` lần đầu chưa có dữ liệu: gọi `computeValue(Alpha.class)` để tạo ứng viên giá trị và gắn giá trị được chọn.
3. `get(Alpha.class)` lần sau, nếu dữ liệu vẫn còn hợp lệ: trả lại giá trị cache; không cần phân tích Reflection lần nữa.
4. `get(Beta.class)` là khóa class khác: tính giá trị riêng cho `Beta`.
5. `remove(Alpha.class)` loại bỏ liên kết hiện có của `Alpha` trong **chính** instance `ClassValue` đó.
6. `get(Alpha.class)` sau khi xóa sẽ có thể chạy `computeValue` và cài đặt giá trị mới; giá trị của `Beta` không bị xóa.

```text
                        ClassValue<List<String>>
                                 |
                 +---------------+---------------+
                 |                               |
             Alpha.class                     Beta.class
                 |                               |
        computeValue(Alpha)              computeValue(Beta)
                 |                               |
          [hello, reset]                        [size]
                 |                               |
       get(Alpha) dùng lại               get(Beta) dùng lại
                 |
          remove(Alpha)
                 |
         get(Alpha) tính lại
```

Điểm khác `Map.computeIfAbsent` là `ClassValue` có cách gắn dữ liệu gắn liền với đối tượng `Class` và được thiết kế cho vòng đời class/class loader. Nó không cung cấp các thao tác map như `entrySet()`, `keySet()`, `put()` hay `clear()`.

## 4. Ví dụ Java 17+ chạy độc lập, kết quả chính xác

Tạo file **`ClassValueDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class ClassValueDemo {
    static class Alpha {
        public void hello() {}
        private void reset() {}
    }

    static class Beta {
        public int size() { return 42; }
    }

    private static final AtomicInteger COMPUTES = new AtomicInteger();

    private static final ClassValue<List<String>> METHOD_NAMES = new ClassValue<>() {
        @Override
        protected List<String> computeValue(Class<?> type) {
            COMPUTES.incrementAndGet();
            return Arrays.stream(type.getDeclaredMethods())
                    .map(Method::getName)
                    .sorted()
                    .toList();
        }
    };

    public static void main(String[] args) {
        List<String> first = METHOD_NAMES.get(Alpha.class);
        System.out.println("Alpha: " + first);

        List<String> again = METHOD_NAMES.get(Alpha.class);
        System.out.println("Alpha reused: " + (first == again));

        System.out.println("Beta: " + METHOD_NAMES.get(Beta.class));
        System.out.println("computeValue calls: " + COMPUTES.get());

        METHOD_NAMES.remove(Alpha.class);
        List<String> refreshed = METHOD_NAMES.get(Alpha.class);
        System.out.println("Alpha refreshed: " + refreshed);
        System.out.println("same list after remove: " + (first == refreshed));
        System.out.println("computeValue calls after remove: " + COMPUTES.get());

        ClassValue<String> CLASS_NAMES = new ClassValue<>() {
            @Override
            protected String computeValue(Class<?> type) {
                return type.getSimpleName();
            }
        };
        System.out.println("another ClassValue: " + CLASS_NAMES.get(Alpha.class));
    }
}
```

Biên dịch bằng Java 17 trở lên (cờ `--release 17` xác nhận mã chỉ cần các API có trong Java 17):

```bash
javac --release 17 ClassValueDemo.java
java ClassValueDemo
```

Stdout xác minh:

```text
Alpha: [hello, reset]
Alpha reused: true
Beta: [size]
computeValue calls: 2
Alpha refreshed: [hello, reset]
same list after remove: false
computeValue calls after remove: 3
another ClassValue: Alpha
```

**Phân tích từng dòng:**

- `computeValue` nhận đúng `Class<?>` được yêu cầu và gọi `getDeclaredMethods()` để lấy các method khai báo trực tiếp (gồm private method). Kết quả được sắp xếp tên bằng `sorted()` trước khi in; không phụ thuộc thứ tự Reflection vốn không được đảm bảo.
- Hai lần `METHOD_NAMES.get(Alpha.class)` liên tiếp trả **cùng tham chiếu `List`** trong ví dụ đơn luồng, nên phép so sánh `first == again` là `true`.
- Khóa `Beta.class` khác khóa `Alpha.class` nên tính thêm một lần. Tổng số lời gọi `computeValue` lúc đó là `2`.
- Sau `remove(Alpha.class)`, `get(Alpha.class)` tính danh sách mới. Nội dung có thể bằng nhau, nhưng đây là **hai instance list khác nhau**, nên kết quả `first == refreshed` là `false`.
- Lần tính lại tăng bộ đếm từ `2` lên `3`; `Beta` vẫn có giá trị của nó.
- `CLASS_NAMES` là instance `ClassValue` khác, quản lý chuỗi tên lớp; nó không chia sẻ nội dung với `METHOD_NAMES` dù cùng khóa `Alpha.class`.

Ví dụ cố tình chạy một luồng. **Không sử dụng tổng số lần `computeValue` của ví dụ này làm cam kết rằng trong chương trình nhiều luồng mỗi class luôn chỉ tính đúng một lần.** Phần tiếp theo giải thích khác biệt.

## 5. Đồng thời: không mặc định computeValue chạy đúng một lần

Khi nhiều thread cùng gọi `get(type)` lúc cache chưa có giá trị, **có thể có nhiều lần chạy `computeValue(type)` đồng thời**. JDK chỉ cài đặt/giữ một giá trị được chọn cho class tại một thời điểm cache ổn định; một số kết quả tính toán cạnh tranh có thể bị bỏ đi. Vì vậy, `ClassValue` loại bớt nhu cầu quản lý khóa cho phép tra cứu cache, nhưng **không biến `computeValue` thành “exactly once initializer”**.

Từ đó có các nguyên tắc:

- Làm `computeValue` **độc lập, xác định được** theo `type` và lý tưởng là không có side effect. Việc scan metadata và dựng một descriptor mới phù hợp hơn việc tạo kết nối, ghi file hoặc cộng tiền.
- Nếu `computeValue` có side effect hoặc tài nguyên ngoại vi, không dựa vào `ClassValue` để đảm bảo chỉ thực hiện một lần. Phải dùng cơ chế quản lý tài nguyên/idempotency riêng.
- Nếu cache trả một đối tượng **có thể thay đổi**, tính an toàn thread của chính đối tượng đó vẫn là trách nhiệm ứng dụng. `ClassValue` không tự biến `HashMap` được cache thành thread-safe.
- Với metadata bất biến, ưu tiên `List.copyOf(...)`, `Map.copyOf(...)` hoặc immutable record/value object. Ví dụ `Stream.toList()` từ Java 16 cho một danh sách không thể sửa bằng `add/remove/set`.
- Nếu có nhu cầu tính toán cực nặng và nhiều thread cùng tranh chấp một class, đo đạc và thiết kế chiến lược đồng bộ ở tầng tính toán riêng; không suy từ thao tác `get` rằng phép tính chỉ chạy một lần.

Khi `computeValue` ném exception, `get` đang thực hiện tính toán có thể ném theo exception đó; đừng coi kết quả lỗi là một descriptor hợp lệ đã được cache. Hãy xác định chính sách retry/diagnostics thay vì che giấu lỗi bằng giá trị placeholder không chính xác.

**Không gọi lại `sameClassValue.get(type)` trên chính khóa đó từ bên trong `computeValue(type)`.** Đây là cách rất dễ tạo đệ quy vô hạn hoặc vòng phụ thuộc, vì kết quả cho khóa đó còn chưa được xác lập.

## 6. Class identity, class loader và giải phóng class

Ở JVM, identity của một class phụ thuộc **binary name và defining class loader**. Có thể có hai class khác nhau cùng tên như `example.Plugin`, được định nghĩa bởi hai class loader khác nhau. Khi đó:

```text
Loader 1 -> example.Plugin (Class object A)
Loader 2 -> example.Plugin (Class object B)
```

`ClassValue.get(Class object A)` và `ClassValue.get(Class object B)` dùng **hai khóa khác nhau**. Điều này cần thiết cho Reflection: methods, fields, annotations và module access trên hai class có thể khác nhau dù `getName()` giống nhau.

**Vì sao có ích cho môi trường plugin/redeploy?**

Một cấu trúc như `static ConcurrentHashMap<Class<?>, Metadata>` có **khóa mạnh**. Khi map sống lâu và chưa xóa entry, nó có thể giữ class và class loader của plugin cũ không được thu gom. `ClassValue` được thiết kế để gắn dữ liệu với lifecycle của `Class` mà không cần đặt mọi đối tượng `Class` làm key mạnh trong một map toàn cục do ứng dụng quản lý.

Điều này **không bảo đảm class unloading sẽ xảy ra**: nếu ứng dụng/framework vẫn giữ tham chiếu mạnh tới class, class loader, object, thread hay metadata, chúng vẫn có thể ngăn giải phóng. Một `ClassValue` có giá trị liên kết với class không thay thế được việc đóng resource, dừng thread hoặc xóa các cache khác vốn giữ class loader.

Không tự tạo key bằng `type.getName()` để thay cho `Class<?>`: cùng tên nhưng loader khác có thể đại diện hai runtime type khác nhau. Khi cache metadata Reflection, việc phân biệt đúng identity là yêu cầu về **tính đúng đắn**, không chỉ về bộ nhớ.

## 7. Gắn dữ liệu Reflection có cấu trúc với từng class

`ClassValue` thường chứa **metadata đã được phân tích**, không chỉ danh sách tên method. Ví dụ cache các `Method` được khai báo trực tiếp của một class:

```java
// Mảnh code minh họa đặt trong class có sử dụng Reflection.
private static final ClassValue<List<java.lang.reflect.Method>> METHODS =
        new ClassValue<>() {
            @Override
            protected List<java.lang.reflect.Method> computeValue(Class<?> type) {
                return java.util.Arrays.stream(type.getDeclaredMethods())
                        .sorted(java.util.Comparator.comparing(
                                java.lang.reflect.Method::toGenericString))
                        .toList();
            }
        };
```

`METHODS.get(SomeType.class)` trả danh sách `Method` gắn với `SomeType.class`. Đoạn này chỉ định nghĩa field/cache; để chạy độc lập cần class bao quanh có `SomeType`. Mọi phép chọn overload phải dựa vào **tên và parameter types** thật sự: không lấy đại phần tử đầu tiên cùng tên, vì class có thể chứa nhiều overload, bridge hoặc synthetic method.

Một logic tra cứu mảnh:

```java
// Giả định biến 'type' là Class<?> và 'methodName' là String.
for (java.lang.reflect.Method method : METHODS.get(type)) {
    if (method.getName().equals(methodName) &&
            java.util.Arrays.equals(
                    method.getParameterTypes(),
                    new Class<?>[]{String.class})) {
        // Tìm được method nhận chính xác một String.
        // Cần kiểm tra access trước khi invoke.
        break;
    }
}
```

**Lưu ý Reflection:** caching một `Method` không đồng nghĩa method đó gọi được. `getDeclaredMethods()` có thể trả method private; `Method.invoke` vẫn phải tuân thủ visibility và ranh giới module. `setAccessible(true)` cũng có thể bị từ chối nếu module/package không mở phù hợp. Cache metadata **không tạo thêm quyền truy cập**.

Nếu kết quả phụ thuộc vào những tham số khác ngoài class, chẳng hạn schema version, locale, quyền người dùng hoặc cấu hình tenant, hãy thiết kế key/value thích hợp. Chỉ dùng `ClassValue` khi dữ liệu được gắn với class; không nhét trạng thái người dùng có vòng đời ngắn vào một giá trị dùng chung giữa các request.

## 8. Làm mới cache, thay đổi cấu hình và remove()

`ClassValue.remove(Class<?> type)` xóa liên kết cache cho **một class** trong instance `ClassValue` cụ thể. Phương thức trả về `void`; nó không trả giá trị cũ và không phải thao tác xóa cả cache.

Ví dụ:

```java
// Nếu metadata được tính bởi CACHED_METADATA:
CACHED_METADATA.remove(type);
// Lần get(type) tiếp theo có thể tính lại:
Metadata refreshed = CACHED_METADATA.get(type);
```

Đây là **mảnh code minh họa**, trong đó `CACHED_METADATA`, `type` và `Metadata` do ứng dụng định nghĩa. Gọi `remove` hợp lý khi chính sách cache nhận biết dữ liệu cần tính lại. Với nhiều luồng, phải xem các guarantee của ứng dụng về việc đồng bộ cập nhật và truy vấn; các lời gọi `get` đang diễn ra có thể cạnh tranh với `remove`. Không coi `remove` là rào chắn giao dịch đảm bảo toàn bộ thread lập tức dùng chung một version dữ liệu mới.

Nếu metadata là hàm của **cấu hình thay đổi trong runtime**, một bản cache được tạo từ cấu hình cũ có thể lỗi thời. Có ba lựa chọn thiết kế cần cân nhắc:

1. Bảo đảm dữ liệu chỉ phụ thuộc vào class và bất biến trong suốt vòng đời liên kết, khi đó `ClassValue` phù hợp trực tiếp.
2. Gọi `remove` cho những class cần làm mới khi biết có cập nhật, đồng thời dùng cơ chế đồng bộ ở tầng ứng dụng để quản lý lần đọc/ghi cạnh tranh.
3. Nếu config/version thay đổi độc lập với class và cần nhiều version cùng lúc, tổ chức **giá trị bên trong** thành map/versioned descriptor hoặc chọn cache với composite key. `ClassValue` đơn lẻ chỉ có một chiều khóa `Class<?>`.

Không có API để duyệt tất cả `Class<?>` hiện được lưu và gọi `remove` hàng loạt trên một `ClassValue`. Nếu cần quản lý từng tập khóa, ứng dụng phải có registry riêng, cùng cân nhắc khả năng giữ class loader sống lâu ngoài ý muốn.

## 9. So sánh lựa chọn cache

| Lựa chọn | Khi thích hợp | Điểm cần cẩn thận |
|---|---|---|
| `ClassValue<T>` | Một giá trị tính lười trên mỗi runtime `Class<?>`, chẳng hạn metadata Reflection | Không có API duyệt key, không bảo đảm `computeValue` chỉ chạy một lần dưới concurrency |
| `ConcurrentHashMap<Class<?>, T>` | Cần duyệt key, eviction tùy ý, cache policy cụ thể; class set có vòng đời được kiểm soát | Khóa mạnh có thể giữ class/class loader; phải dọn dẹp và thiết kế compute policy |
| `WeakHashMap<Class<?>, T>` | Cần key yếu với chính sách synchronization do ứng dụng quản lý | Không thread-safe mặc định; value tham chiếu ngược tới class có thể vô hiệu hóa lợi ích weak key |
| Tính lại bằng Reflection mỗi lần | Gọi hiếm, metadata nhỏ, chưa có bằng chứng bottleneck | Trả chi phí tra cứu/khởi tạo dữ liệu mỗi lần |
| Cache gắn với instance object | Kết quả phụ thuộc trạng thái từng object | Không phải cache **theo Class**; `ClassValue` sẽ chia sẻ theo runtime class |

`ClassValue` thường là lựa chọn gọn cho thư viện phân tích type metadata trong môi trường nhiều class loader. Nhưng không mặc định rằng nó nhanh hơn mọi map trong mọi workload. Hãy đo bằng benchmark tương ứng với số class, số lần đọc, mức độ tranh chấp, chi phí `computeValue` và yêu cầu giải phóng lớp.

## 10. Lỗi thiết kế thường gặp

**1. Nhầm mỗi class với mỗi object.** Nếu hai object `a` và `b` có cùng `a.getClass() == b.getClass()`, cùng `ClassValue` sẽ trả cùng giá trị đã gắn cho class đó. Không đặt data per-request/per-instance vào đây.

**2. Nghĩ computeValue chạy đúng một lần.** Dưới contention, có thể có nhiều computation ứng viên. Side effects cần được kiểm soát độc lập.

**3. Giữ dữ liệu mutable không an toàn.** Cache trả `ArrayList` hoặc `HashMap` bị sửa từ nhiều request sẽ gây race/corruption. Dựng immutable snapshot hoặc dùng cấu trúc concurrent có chủ đích.

**4. Tính dữ liệu theo trạng thái bên ngoài nhưng không invalidation.** Giá trị có thể lỗi thời khi config, feature flags, schema hoặc plugin registration thay đổi. Xác định rõ chính sách cập nhật.

**5. Gọi `get` đệ quy cho cùng khóa từ `computeValue`.** Kết quả chưa được cache; có thể dẫn tới vòng lặp/`StackOverflowError`.

**6. Giả định remove xóa “mọi class”.** `remove(type)` chỉ xóa entry của cặp `(ClassValue instance, type)`, không tác động giá trị của class hoặc `ClassValue` khác.

**7. Cache metadata để “né” quy tắc accessibility.** `ClassValue` không thay đổi `private`, module openness hoặc các exception khi invoke.

**8. Dùng tên lớp string làm identity.** Class loader khác nhau có thể định nghĩa hai kiểu cùng tên; cache từ `getName()` đơn thuần dễ trả sai metadata.

**9. Xem cache là giải pháp cho memory leak từ mọi nguồn.** ClassValue không tự dừng thread/plugin loader còn bị giữ bởi cache khác, thread-local hay static reference.

## 11. Câu hỏi tự kiểm tra

1. Hai lần `cache.get(String.class)` liên tiếp trong một luồng, chưa xóa cache, có phải chạy `computeValue` lần hai không? — Thông thường **không**, vì giá trị đã được gắn và tái sử dụng.
2. Hai instance `ClassValue` khác nhau cùng gọi `get(String.class)` có chia sẻ giá trị không? — **Không**; mỗi `ClassValue` quản lý liên kết riêng.
3. Có thể mặc định `computeValue` chạy chính xác một lần cho mỗi class trong hệ nhiều thread không? — **Không**; nhiều computation cạnh tranh có thể xảy ra.
4. `remove(Alpha.class)` có làm mất entry `Beta.class` không? — **Không**, nếu đó là hai class khác nhau trong cùng `ClassValue`.
5. Hai plugin định nghĩa hai `Class` cùng binary name dưới hai defining loader khác nhau có dùng chung key không? — **Không**; runtime class identity khác nhau.
6. `ClassValue<List<Method>>` có cho phép gọi mọi private method của lớp đó không? — **Không**; vẫn phải tuân thủ Java access control và module boundaries.

## 12. Ghi nhớ

- **`ClassValue<T>`** gắn dữ liệu tính lười với từng `Class<?>` và từng instance `ClassValue`; phù hợp để cache metadata Reflection.
- **`get` tái sử dụng giá trị**, `computeValue` tạo giá trị khi cần, còn `remove(type)` yêu cầu bỏ liên kết cho đúng class đó.
- **Thread-safe ở cơ chế ánh xạ không có nghĩa compute exactly once**, cũng không làm các đối tượng mutable được cache trở nên thread-safe.
- **Class loader là phần của identity**: ClassValue phân biệt đúng những class cùng tên do loader khác nhau định nghĩa và hỗ trợ kiến trúc tương thích class unloading.
- **Cache không thay thế thiết kế vòng đời, invalidation hay bảo mật truy cập**: chỉ cache dữ liệu đúng scope và xử lý thay đổi cấu hình, resource và quyền truy cập tại tầng phù hợp.
