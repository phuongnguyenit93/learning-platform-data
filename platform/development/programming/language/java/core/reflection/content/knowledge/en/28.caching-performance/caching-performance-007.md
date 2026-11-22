# An toàn nhiều luồng khi công bố và sử dụng metadata Reflection đã cache

## 1. Vấn đề: cache đúng nhưng công bố sai vẫn gây lỗi

Reflection cho phép tìm metadata tại runtime, chẳng hạn `Class<?>`, `Method`, `Constructor<?>`, `Field`, annotation và chữ ký generic. Việc tra cứu metadata lặp lại trong đường xử lý nóng có thể không cần thiết; framework thường **cache kết quả tra cứu** rồi dùng lại từ nhiều thread.

Tuy nhiên, cache có hai trách nhiệm độc lập:

1. **Công bố an toàn (*safe publication*):** thread khác phải nhìn thấy đối tượng cache **đã được khởi tạo đầy đủ**, không thấy cấu trúc đang xây dở hoặc giá trị thiếu cập nhật.
2. **Sử dụng an toàn (*safe concurrent use*):** sau khi nhận metadata từ cache, mọi thread phải tuân thủ quyền truy cập, kiểu receiver/đối số và quy tắc đồng bộ của **đối tượng đích**. Bản thân metadata dùng chung không khiến trạng thái nghiệp vụ được bảo vệ.

Ví dụ, một cache `Map<Class<?>, Method>` có thể trả về đúng phương thức cho tất cả thread. Nếu các thread dùng `Method.invoke(...)` trên cùng một đối tượng có field đếm không đồng bộ, kết quả cập nhật vẫn có thể sai vì data race trên **đối tượng đích**.

Điều cốt lõi là tách các tầng:

```text
            [Thread A]              [Thread B]
                |                       |
                +----- đọc cache --------+
                          |
            cache đã publish an toàn
                          |
                   Method / Field /
            MethodHandle / InvocationPlan
                          |
                kiểm tra quyền + kiểu
                          |
                   gọi trên receiver
                          |
                 state của receiver
         (cần bảo vệ riêng nếu có chia sẻ)
```

**Không nên** suy ra “metadata gần như bất biến” đồng nghĩa có thể đặt nó vào bất kỳ `HashMap` dùng chung nào rồi đọc/ghi tự do. Rủi ro có thể nằm ở cấu trúc cache, cách dựng value, bước publish, thao tác thay đổi metadata liên quan tới accessibility hoặc object mà metadata được dùng để gọi.

## 2. Safe publication trong Java Memory Model

Theo Java Memory Model (JMM), nếu một thread xây dữ liệu và thread khác đọc nó mà không có quan hệ **happens-before** thích hợp, việc chỉ gán tham chiếu không bảo đảm thread đọc nhìn thấy mọi write đã xảy ra trong quá trình xây dựng.

Ví dụ **không an toàn**, chỉ để chỉ ra lỗi:

```java
// Minh họa lỗi: KHÔNG dùng như cache nhiều luồng.
static Map<Class<?>, Method> cache = new HashMap<>();

static void register(Class<?> type, Method method) {
    cache.put(type, method); // ghi đồng thời không được đồng bộ
}

static Method lookup(Class<?> type) {
    return cache.get(type); // đọc đồng thời không được đồng bộ
}
```

`HashMap` không an toàn khi nhiều thread đọc/ghi đồng thời không được điều phối. Kể cả có một thread điền cache rồi thread khác bắt đầu, vẫn cần một cơ chế công bố đảm bảo visibility, ví dụ class initialization, đồng bộ lock hoặc primitive concurrent phù hợp. Không dùng `volatile HashMap` như cách “sửa” mọi cập nhật: `volatile` trên **tham chiếu** không biến các thao tác `put/get` của map thành thread-safe.

Những cơ chế công bố hữu ích:

| Cơ chế | Bảo đảm liên quan | Khi nào hợp lý |
| --- | --- | --- |
| Khởi tạo trường `static final` trong class initialization | JVM bảo đảm các thread thấy trạng thái class được khởi tạo đúng | Cache hoặc đối tượng bất biến dựng trong giai đoạn khởi tạo |
| `synchronized` hoặc `Lock` cùng giao thức | Unlock happens-before lock tiếp theo trên cùng monitor/lock | Cache có transaction hoặc nhiều thay đổi liên quan |
| Ghi/đọc một tham chiếu `volatile` | Ghi volatile happens-before đọc volatile tương ứng về sau | Công bố **snapshot bất biến** bằng cách thay toàn bộ tham chiếu |
| `ConcurrentHashMap` | API concurrent và bảo đảm visibility cho dữ liệu được gắn với key đúng cách | Cache tăng trưởng động, truy cập theo key |
| `ClassValue<T>` | Gắn value được tạo lười với từng `Class<?>`, cơ chế truy cập an toàn cho nhiều thread | Cache metadata theo class, đặc biệt môi trường nạp/gỡ class động |
| Immutable object với field `final` | Hỗ trợ final-field semantics khi dựng đúng, không để `this` thoát khỏi constructor | Value của cache không cần sửa sau khi xây |

**`final` không thay thế đồng bộ cho mọi cấu trúc mutable.** Ví dụ `final List<Method> methods` chỉ cố định tham chiếu; nếu danh sách thật là `ArrayList` rồi bị sửa đồng thời, vẫn có race. Ưu tiên tạo đầy đủ dữ liệu trong biến cục bộ, biến thành `List.copyOf(...)`/`Map.copyOf(...)`, đặt vào field `final` và publish qua primitive an toàn. Không để `this` hay collection nội bộ thoát ra trước khi constructor hoàn thành.

## 3. Chọn khóa cache đủ định danh metadata

Một khóa cache thiếu thông tin có thể trả metadata **sai** dù map hoàn toàn thread-safe.

- `Class<?>` phân biệt **kiểu runtime thực sự**, bao gồm danh tính class loader. Hai class loader có thể định nghĩa lớp có cùng tên nhị phân nhưng đó là hai `Class<?>` khác nhau. Dùng mỗi chuỗi `type.getName()` làm khóa toàn ứng dụng có thể trộn metadata của hai lớp không tương thích.
- Nếu cache **nhiều method trong cùng một class**, khóa cần đủ tên, kiểu tham số khai báo, static/instance khi phù hợp và chính sách xử lý overload, bridge, visibility. `getMethod("convert", String.class)` khác `getMethod("convert", Object.class)`.
- Field của superclass và field cùng tên của subclass có thể tồn tại đồng thời; chỉ lưu `"id"` mà bỏ declaring class hoặc chính sách tra cứu dễ gây nhầm.
- Với constructor, khóa gồm declaring class và các kiểu tham số. Constructor không kế thừa.
- Với `MethodHandle`, cần hiểu `MethodType` và quyền `Lookup` tại thời điểm tạo; không dùng handle có quyền rộng như một phần của public API thiếu kiểm soát.

Phạm vi cache nên gắn với **lifecycle và quyền sử dụng**: cache metadata public để đọc có thể dùng chung rộng rãi; handle private được tạo bằng `Lookup` có quyền đặc biệt cần giới hạn phạm vi chia sẻ. Đưa handle vào cache không làm mất các quy tắc JPMS, cũng không cấp quyền gọi cho mọi người dùng cuối của ứng dụng.

## 4. Ưu tiên `ClassValue<T>` khi cache theo class

`java.lang.ClassValue<T>` cung cấp cách gắn dữ liệu tính toán lười với một `Class<?>` mà không cần tự duy trì một `Map<Class<?>, T>` static lâu sống. API này đặc biệt phù hợp cho serializer, framework, proxy, plugin hoặc công cụ Reflection có nhiều class loader.

Mẫu ý tưởng:

```java
private static final ClassValue<Plan> PLANS = new ClassValue<>() {
    @Override
    protected Plan computeValue(Class<?> type) {
        return createPlan(type); // tạo đầy đủ trước khi công bố
    }
};

Plan plan = PLANS.get(SomeType.class);
```

Đoạn này là **mẫu minh họa**, chưa có khai báo `Plan`/`createPlan`; ví dụ hoàn chỉnh ở phần tiếp theo.

Những điểm quan trọng:

- `get(type)` cung cấp value gắn với class được yêu cầu. Không cần tự khóa một `HashMap` trong đường đọc.
- Với truy cập cạnh tranh, **`computeValue(type)` có thể được gọi nhiều lần**, dù cuối cùng một value được dùng làm mapping tương ứng. Vì vậy hàm xây cache phải an toàn khi chạy lặp lại và không được gây side effect nghiệp vụ kiểu “mỗi class đăng ký đúng một sự kiện” dựa đơn thuần vào số lần gọi.
- Không tạo và chia sẻ trước một `Plan` chưa hoàn tất, không publish tham chiếu tới map đang điền.
- `ClassValue.remove(type)` có thể được dùng để bỏ value khi chính sách cho phép tạo lại, nhưng không coi thao tác remove/get cạnh tranh là cơ chế cập nhật nguyên tử cho mọi thread hoặc hủy các reference `Plan` mà thread đã lấy trước đó.
- So với `ConcurrentHashMap<Class<?>, ...>` static, `ClassValue` thường phù hợp hơn với vòng đời class/class loader. Một map static giữ khóa `Class<?>` có thể **giữ class loader không được unload** nếu không có chính sách dọn dẹp.

## 5. Chương trình Java 17+ hoàn chỉnh: một plan bất biến, nhiều thread dùng chung

Chương trình xây `InvocationPlan` bất biến chứa `Method` public `greet(String)` của một kiểu, cache theo class bằng `ClassValue`. Nhiều tác vụ chạy đồng thời lấy plan, nhưng mỗi tác vụ dùng một receiver riêng; main in kết quả theo thứ tự Future được tạo để stdout xác định.

Tạo tệp **`SafeReflectionCacheDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SafeReflectionCacheDemo {
    public static final class Greeter {
        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    private static final class InvocationPlan {
        private final Method method;

        private InvocationPlan(Method method) {
            this.method = method;
        }

        String call(Object receiver, String argument)
                throws ReflectiveOperationException {
            return (String) method.invoke(receiver, argument);
        }
    }

    private static final ClassValue<InvocationPlan> PLANS =
            new ClassValue<>() {
                @Override
                protected InvocationPlan computeValue(Class<?> type) {
                    try {
                        Method method =
                                type.getMethod("greet", String.class);
                        return new InvocationPlan(method);
                    } catch (NoSuchMethodException e) {
                        throw new IllegalArgumentException(
                                "Requires public greet(String): "
                                        + type.getName(), e);
                    }
                }
            };

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 1; i <= 6; i++) {
                final int number = i;
                futures.add(pool.submit(() -> {
                    InvocationPlan plan = PLANS.get(Greeter.class);
                    Greeter receiver = new Greeter();
                    return plan.call(receiver, "bạn " + number);
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SafeReflectionCacheDemo.java
java SafeReflectionCacheDemo
```

Stdout:

```text
Xin chào, bạn 1
Xin chào, bạn 2
Xin chào, bạn 3
Xin chào, bạn 4
Xin chào, bạn 5
Xin chào, bạn 6
```

Tại sao ví dụ an toàn?

1. Trường `PLANS` được tạo trong quá trình **class initialization**. Mọi thread dùng cùng cơ chế `ClassValue` để lấy plan cho `Greeter.class`.
2. `computeValue` chỉ tìm `Method` public và tạo `InvocationPlan` hoàn chỉnh; không đăng ký side effect và vẫn đúng nếu bị tính lặp do cạnh tranh.
3. `InvocationPlan` có field `final Method`; không có setter hay collection bị sửa sau khi publish. Program không thay đổi `setAccessible` trên `Method` đã chia sẻ.
4. `ClassValue` chịu trách nhiệm phối hợp association; các thread không truy cập `HashMap` dùng chung chưa đồng bộ.
5. Mỗi task tạo `new Greeter()` của riêng mình. Nếu `Greeter.greet` sửa state chia sẻ, riêng cache an toàn vẫn **không** bảo đảm lời gọi nghiệp vụ an toàn.
6. Các task có thể hoàn tất không theo thứ tự, nhưng `futures` được duyệt theo **thứ tự submit**, nên các dòng stdout có thứ tự từ 1 đến 6.
7. `Future.get()` có cơ chế chờ/visibility: main chỉ xử lý kết quả sau khi tác vụ hoàn thành; không phải dùng sleep để “đợi dữ liệu hiện ra”.

Ví dụ dùng `getMethod` cho API public đã biết. Với method private, module khác, overload phức tạp hoặc quyền truy cập đặc biệt, thêm chính sách xử lý phù hợp; không suy rằng cache sẽ tự giải quyết vấn đề access.

## 6. Dùng `ConcurrentHashMap` khi cần cache theo nhiều khóa động

`ConcurrentHashMap` thường hợp lý nếu khóa không chỉ là `Class<?>`, chẳng hạn cặp class + tên method + danh sách kiểu tham số hoặc cấu hình operation riêng. Nó hỗ trợ truy cập concurrent và `computeIfAbsent` để liên kết value với key:

```java
private static final ConcurrentMap<Class<?>, Method> METHODS =
        new ConcurrentHashMap<>();

static Method resolve(Class<?> type) {
    return METHODS.computeIfAbsent(type, key -> {
        try {
            return key.getMethod("greet", String.class);
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(
                    "Requires greet(String): " + key.getName(), e);
        }
    });
}
```

Đây là **đoạn minh họa**, cần import `java.lang.reflect.Method`, `java.util.concurrent.ConcurrentMap` và `java.util.concurrent.ConcurrentHashMap`; đặt trong class có quyền dùng những member ấy.

`computeIfAbsent` thực hiện mapping cho key chưa có theo hợp đồng concurrent map; với một mapping thành công đang tồn tại, những thread khác có thể tái sử dụng. Tuy nhiên, **không thiết kế mapping function dựa vào giả định “chạy đúng một lần trong suốt vòng đời ứng dụng”**: khi entry bị xóa, compute ném exception, trả `null` hoặc cache được tái tạo, phép tính có thể thực hiện trở lại.

Mapping function nên:

- **Ngắn, độc lập, không có side effect nghiệp vụ** và trả đối tượng đã khởi tạo đầy đủ.
- Không cập nhật đệ quy/chồng chéo cùng map trong lúc tính; `ConcurrentHashMap` có thể ngăn recursive update và ném `IllegalStateException`.
- Không làm I/O hoặc công việc chặn quá lâu vì các thread khác có thể bị ảnh hưởng trong quá trình cập nhật mapping.
- Trả về value bất biến hoặc value có đồng bộ nội bộ. **Concurrent map chỉ bảo vệ cấu trúc map và cách publish**, không khiến một `ArrayList` bên trong value tự thread-safe.

**Không cache lỗi bằng cách lén trả `null`.** `ConcurrentHashMap` không chấp nhận key/value `null`; mapping function trả `null` thì mapping không được ghi. Nếu muốn negative cache cho lookup không tồn tại, hãy định nghĩa một kiểu kết quả biểu diễn rõ “không tìm thấy” (ví dụ value immutable chứa trạng thái) với chính sách thời hạn và invalidation.

Với map static chứa khóa `Class<?>`, phải quan tâm tới class loader leak. Nếu chủ yếu gắn dữ liệu với mỗi class, `ClassValue` thường là lựa chọn đơn giản và phù hợp vòng đời hơn.

## 7. Bẫy “map thread-safe nhưng value không thread-safe”

Ví dụ sai:

```java
// Minh họa lỗi: map concurrent nhưng value ArrayList vẫn mutable.
ConcurrentMap<Class<?>, List<Method>> cache =
        new ConcurrentHashMap<>();

List<Method> list = cache.computeIfAbsent(
        SomeType.class, type -> new ArrayList<>());
list.add(someMethod); // nhiều thread add cùng List -> race
```

Đoạn trên chỉ mô tả anti-pattern; `SomeType`, `someMethod` và imports chưa được khai báo. `ConcurrentHashMap` bảo vệ việc gán/get danh sách vào map, **không đồng bộ các lời gọi `ArrayList.add`** trên danh sách trả về.

Cách tốt hơn cho metadata chỉ đọc là **dựng xong rồi mới publish**:

```java
List<Method> collected = new ArrayList<>();
// ... thu thập Method vào collected chỉ trong thread khởi tạo ...
List<Method> immutableSnapshot = List.copyOf(collected);
// Publish immutableSnapshot qua ClassValue, ConcurrentHashMap,
// volatile hoặc primitive đồng bộ phù hợp.
```

Đây cũng là snippet, không phải chương trình độc lập. `List.copyOf` tạo danh sách không cho sửa cấu trúc và không để lộ `collected` làm backing list mutable. Nhưng nó chỉ cố định **danh sách các tham chiếu**: nếu phần tử của collection có trạng thái mutable bị sửa sau publish, phải đánh giá riêng.

Nếu có nhiều nhóm metadata liên quan, hãy dựng **một đối tượng snapshot** chứa đủ các map/list và publish đồng thời thông qua **một tham chiếu**. Publish từng map riêng lẻ dễ khiến reader thấy “method map version mới, field map version cũ” trong cùng một lượt xử lý.

## 8. Thay snapshot bằng `volatile` khi có cập nhật cấu hình

Một chương trình có thể xây catalog metadata mới rồi **thay toàn bộ snapshot**. Với mô hình nhiều reader, ít writer, việc đọc một trường `volatile` là lựa chọn đơn giản:

```java
private volatile List<Method> methods = List.of();

void reload(Class<?> type) {
    List<Method> fresh = List.copyOf(
            java.util.Arrays.asList(type.getMethods()));
    methods = fresh; // publish cả snapshot bằng một volatile write
}

List<Method> currentMethods() {
    return methods; // một volatile read
}
```

Đây là đoạn minh họa đặt trong một class; cần import `Method`. Trường `methods` phải được khai báo trên instance mà các thread chia sẻ có chủ đích.

Các điểm quan trọng:

- `volatile` trên **tham chiếu snapshot** giúp thread đọc thấy snapshot được công bố sau write volatile; không cần sửa trực tiếp list đã publish.
- Cả snapshot cũ lẫn snapshot mới đều hợp lệ với thread đã lấy tham chiếu trước lúc swap; việc thay tham chiếu không “thu hồi” dữ liệu trong tay reader.
- Nếu phải cập nhật nhiều field liên quan, hãy gói chúng vào một snapshot immutable rồi swap **một** tham chiếu để tránh phiên bản dữ liệu lẫn lộn.
- Nếu nhiều writer đồng thời tính snapshot bằng cách đọc trạng thái trước và cộng thêm dữ liệu, `volatile` **không** bảo vệ thao tác read-modify-write khỏi **lost update**. Dùng lock, `AtomicReference.compareAndSet` hoặc cơ chế version/generation thích hợp.
- Một thread lấy snapshot rồi dùng lâu có thể tiếp tục thấy dữ liệu cũ. Nếu yêu cầu nhất quán mạnh hơn (ví dụ yêu cầu mọi lần gọi sau reload đều dùng policy mới), cần xác định synchronization boundary, phiên bản và cách xử lý thao tác đang chạy.

Không dùng “double-checked locking” tự viết với tham chiếu mutable không `volatile`. Đối với cache lười theo class, `ClassValue` và `ConcurrentHashMap.computeIfAbsent` thường rõ ràng, ít lỗi hơn.

## 9. Sử dụng metadata chia sẻ: khi nào là an toàn?

### 9.1. `Method`, `Constructor` và `Field`

Metadata đã tìm được có thể được giữ để tái sử dụng. Việc nhiều thread gọi `Method.invoke` thông qua cùng một `Method` đã được cấu hình ổn định là tình huống thông thường. Tuy vậy:

- **Không thay đổi `setAccessible(true/false)` đồng thời** trên đối tượng `AccessibleObject` dùng chung trong khi thread khác đang dùng. Việc đổi trạng thái access là thay đổi có tác động đến quyền/kiểm tra truy cập; nên giải quyết quyền trước khi công bố hoặc dùng `MethodHandles.Lookup` hợp lệ với phạm vi quyền rõ ràng.
- `Field.get/set` truy cập **trạng thái field thực**. Nếu nhiều thread đọc/ghi cùng field của cùng object, phải xét `volatile`, lock hoặc VarHandle access mode; cache `Field` không bảo vệ giá trị được đọc/ghi.
- `Constructor.newInstance` tạo instance; constructor có thể thực hiện side effect hoặc sử dụng tài nguyên dùng chung. An toàn cache `Constructor` không bảo đảm constructor đích thread-safe.
- Metadata cho class được tải từ plugin có thể phụ thuộc class loader/module. Quyền access có thể khác ở caller khác; không công bố handle/metadata đặc quyền ra ngoài boundary truy cập.

### 9.2. `MethodHandle` và `VarHandle`

`MethodHandle` biểu diễn thao tác đã liên kết, có type; `VarHandle` biểu diễn một biến và các mode truy cập. Chúng phù hợp để chia sẻ theo mục đích đã xác định, nhưng:

- Receiver, array hoặc đối tượng mà handle thao tác **vẫn có thể mutable và chia sẻ**.
- `VarHandle.get`/`set` bình thường không đồng nghĩa `getVolatile`/`setVolatile` hay `compareAndSet`. Chọn access mode theo hợp đồng bộ nhớ và loại field.
- Không dùng handle có quyền private làm “đường vòng” bỏ xác thực quyền nghiệp vụ. Quyền tạo handle, quyền module và quyền của người dùng thao tác là các tầng khác nhau.
- Bind receiver vào handle (`bindTo`) có thể làm cache giữ mạnh object receiver và class loader, ảnh hưởng vòng đời, đồng thời có thể khiến nhiều thread vô tình tác động cùng instance. Khi có thể, cache handle không bind receiver và truyền receiver tại lời gọi.

### 9.3. Annotation và tập metadata đã tiền xử lý

Nếu đọc annotation và tạo sơ đồ mapping, lưu một **immutable descriptor** chứa tên, `MethodType`/kiểu field, danh sách tham số, flags và kết quả validation. Nếu chứa `Map`/`List`, dùng bản copy immutable; đừng trả trực tiếp mutable collection nội bộ cho caller.

Các kết quả `Annotation` runtime không nên bị hiểu là cấu hình nghiệp vụ bất biến theo thời gian nếu ứng dụng còn đọc file cấu hình hoặc policy động bên ngoài. Phân biệt metadata của class với **trạng thái cấu hình có thể reload**.

## 10. Cache lifecycle, refresh và class loader

Một cache có thể thread-safe nhưng vẫn sai vì giữ metadata **quá lâu** hoặc đặt khóa không đủ định danh.

- Dùng khóa `Class<?>` (hoặc `ClassValue`) thay vì chỉ tên class; cùng binary name trong hai class loader có thể là hai kiểu khác nhau.
- Cache static `ConcurrentHashMap<Class<?>, ...>` giữ strong reference tới key/value. Plugin class loader có thể không được unload nếu cache không xóa entry và value giữ class.
- Trường hợp chỉ cần giá trị gắn với class, `ClassValue` giảm gánh nặng quản lý vòng đời.
- Nếu metadata phụ thuộc **phiên bản cấu hình**, annotation scan policy, feature flags hoặc quyền tenant, khóa hoặc snapshot cần chứa version/policy tương ứng. `ClassValue` chỉ theo class không tự phân biệt các phiên bản policy.
- Nếu refresh, phải định nghĩa rõ thời điểm snapshot mới có hiệu lực, xử lý thread đang giữ snapshot cũ, và khi nào có thể loại bỏ tài nguyên đã gắn với snapshot.
- Không mặc định gọi `ClassValue.remove(type)` sẽ buộc mọi thread dừng dùng value cũ; remove chỉ tác động mapping mà `ClassValue` quản lý.

Đối với long-running server, quan sát kích thước cache, số class loader, hit/miss, thời gian khởi tạo metadata và tính đúng của invalidation. Đừng chọn cache toàn cục chỉ vì tra cứu reflection “có vẻ chậm”; hãy đo trên đường đi thực tế.

## 11. Những lỗi nhiều luồng thường gặp và cách sửa

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| `HashMap` static với `put/get` từ nhiều thread | Race ở cấu trúc map và visibility | `ConcurrentHashMap`, `ClassValue` hoặc đồng bộ nhất quán |
| Xây object một phần rồi đưa vào cache | Reader thấy state chưa hoàn tất | Dựng local đầy đủ, publish value immutable |
| `final Map` nhưng vẫn gọi `put` đồng thời | `final` chỉ khóa tham chiếu, không khóa state | Immutable map hoặc map concurrent |
| `volatile Map` rồi cùng sửa `HashMap` | `volatile` không bảo vệ nội bộ map | Thay snapshot immutable, hoặc dùng concurrent map |
| `computeIfAbsent` vừa compute vừa cập nhật cùng map | Recursive update, blocking và side effect không xác định | Compute thuần, nhanh, tránh đụng map từ mapping function |
| Cho rằng `ClassValue.computeValue` chạy đúng một lần | Có thể tính cạnh tranh nhiều lần | Giữ phép tính idempotent, không side effect |
| Cache theo chuỗi tên class | Hai class loader định nghĩa cùng tên có thể bị trộn | Khóa bằng `Class<?>` hoặc `ClassValue` |
| Cache `Method` rồi đổi `setAccessible` trong khi dùng | Quyền/kiểm tra access bị thay đổi lúc chạy | Cấu hình trước publish; tránh toggle shared metadata |
| Metadata thread-safe ⇒ method đích thread-safe | State của receiver và side effect vẫn race | Đồng bộ object nghiệp vụ hoặc thiết kế bất biến |
| Cache handle đã `bindTo` receiver dài hạn | Giữ receiver và có thể giữ class loader; nhiều thread cùng sửa state | Cache handle độc lập rồi truyền receiver |
| Publish nhiều map ở nhiều thời điểm | Reader có thể thấy nửa phiên bản mới, nửa cũ | Gộp vào một immutable snapshot để atomic swap |
| Không dọn cache cho plugin unload | Strong reference giữ `Class<?>`/loader | `ClassValue` hoặc chính sách lifecycle/eviction |

Đừng lạm dụng khóa global bao trùm cả thao tác nghiệp vụ chỉ để bảo vệ cache. Nên tách **synchronization của việc tìm/bổ sung metadata** khỏi **synchronization của thao tác lên object đích**. Như vậy vừa rõ hợp đồng vừa tránh khóa lớn gây nghẽn.

## 12. Quy trình thiết kế và kiểm chứng

Với một cache metadata cần dùng chung nhiều thread:

1. **Xác định dữ liệu được cache**: chỉ `Class/Method/Field/Constructor`, hay cả handle, accessor, parser, map và policy.
2. **Xác định đơn vị nhận diện**: `Class<?>`, member signature, class loader, phiên bản cấu hình và quyền lookup.
3. **Tạo value hoàn chỉnh**: validate member, chuẩn hóa descriptor và sao chép collection thành immutable snapshot trước khi publish.
4. **Chọn cơ chế publish**: `ClassValue` cho per-class; `ConcurrentHashMap` cho nhiều khóa động; `static final`/class initialization cho value cố định; `volatile` cho swap snapshot nguyên khối.
5. **Tách an toàn của cache khỏi an toàn của receiver**: xác định thread nào có quyền đụng cùng đối tượng, field mutable và external side effect.
6. **Chỉ rõ chính sách thay đổi**: không thay `AccessibleObject` dùng chung tùy tiện; nếu có reload, xác định version và cách chuyển đổi.
7. **Kiểm tra dưới cạnh tranh**: nhiều thread cold-start cùng class, nhiều class loader, có cache miss/exception, thay snapshot trong khi đọc, kiểm tra stale value, và xác nhận không tự động giả định `computeValue` đúng một lần.
8. **Đo hiệu năng và vòng đời**: số lookup trùng, contention, allocation, memory retention và class-loader unload. Không phán đoán hiệu năng chỉ từ lựa chọn API.

### Câu hỏi tự kiểm tra

1. Vì sao `static final HashMap` vẫn không an toàn nếu có thread ghi vào map sau lúc khởi tạo?
2. `volatile` trên một tham chiếu tới `HashMap` có làm `HashMap.put`/`get` an toàn khi dùng đồng thời không?
3. Vì sao `ClassValue.computeValue` nên tránh side effect ngay cả khi đã có cache cho mỗi `Class<?>`?
4. Trong `SafeReflectionCacheDemo`, vì sao stdout ổn định dù các tác vụ chạy trên bốn worker thread?
5. Nếu giữ chung `Method` nhưng nhiều thread gọi trên cùng một counter chưa đồng bộ, cache có bảo vệ counter không?
6. `Class<?>` khác chuỗi `getName()` thế nào khi hai plugin class loader định nghĩa lớp cùng tên?
7. Vì sao `ConcurrentHashMap<Class<?>, ArrayList<Method>>` vẫn có thể lỗi nếu nhiều thread sửa cùng list?
8. Nếu hot reload một policy, việc thay ba `volatile Map` riêng lẻ có đảm bảo một reader luôn thấy cùng một version không?
9. Nếu cache `MethodHandle.bindTo(receiver)`, điều gì xảy ra với vòng đời receiver và an toàn truy cập state của nó?

**Ghi nhớ:** Một cache Reflection đúng đắn cần **value được xây hoàn chỉnh, được công bố với happens-before phù hợp, có khóa và vòng đời chính xác**, cùng chính sách sử dụng an toàn đối với receiver và trạng thái nghiệp vụ. `ClassValue` và `ConcurrentHashMap` xử lý tốt việc phối hợp truy cập metadata; chúng không thay thế cơ chế đồng bộ của đối tượng được gọi.
