# Xác định trước kích thước danh sách hoặc tập khóa

> **Mốc cập nhật: 27-11-2026.** Bài thực hành dùng API preview hiện hành của JDK 27: `List.ofLazy(int, IntFunction)` và `Map.ofLazy(Set, Function)`. Cả hai API vẫn là Preview theo JEP 531 (Lazy Constants, Third Preview), chưa phải API ổn định của Java SE. Nội dung tập trung vào hai miền dữ liệu cố định: số lượng phần tử của List và tập key của Map.

## 1. Mục tiêu

Trong nhiều ứng dụng, ta biết trước danh sách có bao nhiêu vị trí hoặc Map sẽ có những key nào, nhưng không cần tính tất cả value ngay lúc khởi tạo. Ví dụ:

- Danh sách 24 shard, mỗi shard chỉ được tạo khi request cần đến shard đó.
- Danh sách trang báo cáo có số trang xác định từ trước, nhưng nội dung mỗi trang được dựng theo nhu cầu.
- Bản đồ cấu hình cho một tập route đã biết, mỗi cấu hình chỉ được tải khi route tương ứng được truy cập.
- Cache cho một tập mã sản phẩm hoặc tham số hữu hạn, trong đó giá trị được tính khi có lần đọc đầu tiên.

Java 27 cung cấp hai factory preview để biểu diễn trực tiếp trường hợp này:

| Factory | Miền được xác định trước | Hàm tính giá trị |
|---|---|---|
| `List.ofLazy(size, computingFunction)` | Số lượng phần tử và index từ `0` đến `size - 1`. | `IntFunction<? extends E>`, nhận index. |
| `Map.ofLazy(keys, computingFunction)` | Tập key được truyền vào lúc tạo Map. | `Function<? super K, ? extends V>`, nhận key. |

Cả hai tạo collection không thể thay đổi cấu trúc. Value chỉ được tính khi cần truy cập, và hàm tính được gọi tối đa một lần cho mỗi index hoặc key, kể cả khi nhiều thread truy cập đồng thời cùng phần tử.

## 2. Trạng thái API và điều kiện sử dụng

`List.ofLazy` và `Map.ofLazy` là Preview API của Java Platform. Chúng được giới thiệu từ JDK 26 và tiếp tục nằm trong hợp đồng preview JDK 27 cùng JEP 531. Không được coi chúng là API ổn định hoặc mặc định có mặt trong mọi JDK.

| Phiên bản | Cách hiểu |
|---|---|
| JDK 26 | Các factory lazy collection đã xuất hiện dưới dạng preview. |
| JDK 27 | Tiếp tục là Preview API; cần biên dịch và chạy với preview được bật. |
| JDK tiếp theo | Phải kiểm tra Preview API List và Javadoc của đúng phiên bản; không giả định chữ ký hoặc hành vi preview được giữ nguyên. |

Biên dịch và chạy bằng JDK 27:

```text
javac --release 27 --enable-preview -Xlint:preview LazyCollectionsDemo.java
java --enable-preview LazyCollectionsDemo
```

Cả compiler và runtime phải dùng JDK 27. Không thể biên dịch preview bằng JDK 26 rồi chạy với runtime JDK 27 như thể đó là cùng một hợp đồng. Khi nâng cấp JDK, cần biên dịch lại và xử lý thay đổi preview.

## 3. Xác định trước kích thước List với List.ofLazy

### 3.1. Chữ ký và mô hình hoạt động

Chữ ký API:

```java
static <E> List<E> ofLazy(
        int size,
        IntFunction<? extends E> computingFunction
)
```

Khi gọi factory, ứng dụng cung cấp:

- `size`: kích thước cố định của danh sách.
- `computingFunction`: hàm tạo phần tử khi một index được truy cập lần đầu.

Ví dụ:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicIntegerArray;

record ReportPage(int pageNumber, String title) {}

public class LazyListExample {
    private static final int PAGE_COUNT = 12;

    private static final AtomicIntegerArray COMPUTE_COUNTS =
            new AtomicIntegerArray(PAGE_COUNT);

    private static final List<ReportPage> PAGES =
            List.ofLazy(PAGE_COUNT, index -> {
                COMPUTE_COUNTS.incrementAndGet(index);
                System.out.println("Building page " + index);
                return new ReportPage(
                        index,
                        "Report page " + (index + 1)
                );
            });

    public static void main(String[] args) {
        System.out.println("Size = " + PAGES.size());

        // Chỉ index 7 được tính ở lần truy cập này.
        ReportPage page = PAGES.get(7);
        System.out.println(page.title());

        // Cùng index: nhận lại giá trị đã được tính.
        System.out.println(PAGES.get(7) == page);

        // Index 2 chưa được yêu cầu nên supplier của index 2 chưa chạy.
        System.out.println("Count[2] = " + COMPUTE_COUNTS.get(2));
        System.out.println("Count[7] = " + COMPUTE_COUNTS.get(7));
    }
}
```

Kết quả minh họa:

```text
Size = 12
Building page 7
Report page 8
true
Count[2] = 0
Count[7] = 1
```

`size()` cho biết số vị trí ngay từ lúc tạo List. Nó không cần dựng toàn bộ phần tử. Gọi `get(index)` mới yêu cầu tính value của index đó. Những index chưa được truy cập vẫn chưa cần tính.

### 3.2. Những quy tắc quan trọng của List.ofLazy

- Kích thước được cố định tại thời điểm tạo; không thể thêm, xóa hoặc thay thế phần tử.
- Index hợp lệ là từ `0` đến `size - 1`; truy cập ngoài phạm vi ném `IndexOutOfBoundsException`.
- Kích thước âm làm factory ném `IllegalArgumentException`.
- Computing function không được là `null`; truyền `null` ném `NullPointerException`.
- Phần tử không được là `null`. Nếu function trả về null, index đó chuyển sang error state.
- Mỗi index được tính tối đa một lần. Nhiều thread cùng truy cập index đang được tính sẽ chờ kết quả hoặc chờ phép tính kết thúc bất thường.
- List không thể sửa đổi, hỗ trợ truy cập ngẫu nhiên và các view `subList()`, `reversed()` vẫn giữ tính lazy cho phần tử tương ứng.
- List lazy được trả về không Serializable.
- List thuộc nhóm value-based collection; không dùng chính instance List làm khóa đồng bộ và không phụ thuộc vào identity của instance.

List.ofLazy phù hợp khi miền index cố định và mỗi vị trí có thể tạo độc lập. Nó không phù hợp với danh sách có số phần tử tăng giảm theo nghiệp vụ.

### 3.3. View và thao tác có thể kích hoạt tính phần tử

Các thao tác sau không có cùng chi phí:

| Thao tác | Có cần tính value? |
|---|---|
| `size()` | Không cần tính các phần tử. |
| `get(i)` | Tính phần tử tại index `i` nếu chưa có. |
| `subList(from, to)` | Tạo view; phần tử vẫn được tính khi view truy cập chúng. |
| `reversed()` | Tạo view đảo thứ tự; phần tử vẫn được tính khi được truy cập. |
| Duyệt toàn bộ List | Sẽ truy cập và tính tất cả phần tử được duyệt. |
| `equals()`, `hashCode()`, `toString()` | Có thể kích hoạt tính một hoặc nhiều phần tử. |

Một lỗi quan sát thường gặp là log toàn bộ List ngay sau khi tạo:

```java
System.out.println(PAGES);
```

`toString()` có thể truy cập các phần tử để tạo chuỗi, khiến nhiều hoặc toàn bộ trang được khởi tạo. Vì vậy, trong giai đoạn kiểm tra lazy behavior, chỉ log `size()` hoặc index cụ thể; không log nguyên collection nếu muốn giữ các phần tử chưa được tính.

## 4. Xác định trước tập key của Map với Map.ofLazy

### 4.1. Chữ ký và mô hình hoạt động

Chữ ký API:

```java
static <K, V> Map<K, V> ofLazy(
        Set<? extends K> keys,
        Function<? super K, ? extends V> computingFunction
)
```

Ứng dụng phải biết trước các key có thể xuất hiện. Khi tạo Map, key domain đã được xác định; value tương ứng chỉ được tính khi truy cập lần đầu.

Ví dụ:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

record RouteConfig(String path, int timeoutSeconds) {}

public class LazyMapExample {
    private static final AtomicInteger COMPUTE_COUNT =
            new AtomicInteger();

    private static final Set<String> ROUTE_KEYS =
            Set.of("profile", "orders", "billing");

    private static final Map<String, RouteConfig> ROUTES =
            Map.ofLazy(ROUTE_KEYS, key -> {
                COMPUTE_COUNT.incrementAndGet();
                System.out.println("Loading route " + key);

                return switch (key) {
                    case "profile" ->
                            new RouteConfig("/api/profile", 2);
                    case "orders" ->
                            new RouteConfig("/api/orders", 4);
                    case "billing" ->
                            new RouteConfig("/api/billing", 5);
                    default -> throw new IllegalArgumentException(
                            "Unsupported route: " + key
                    );
                };
            });

    public static void main(String[] args) {
        // Key đã biết từ lúc tạo Map.
        System.out.println(ROUTES.keySet());

        // Value của orders được tính lần đầu.
        RouteConfig orders = ROUTES.get("orders");
        System.out.println(orders);

        // Lần đọc sau lấy lại cùng value.
        System.out.println(ROUTES.get("orders") == orders);

        // Key ngoài miền đã khai báo không có mapping.
        System.out.println(ROUTES.get("unknown"));

        System.out.println("Computed values = " + COMPUTE_COUNT.get());
    }
}
```

Thứ tự các key được in ra không được bảo đảm. Kết quả minh họa:

```text
[profile, billing, orders]
Loading route orders
RouteConfig[path=/api/orders, timeoutSeconds=4]
true
null
Computed values = 1
```

Các điểm cần đọc đúng:

- `keySet()` biểu diễn các key đã được xác định trước; không cần tính tất cả value.
- `get("orders")` yêu cầu value của key `orders`.
- Đọc lại cùng key trả về value đã khởi tạo.
- `get("unknown")` trả về null vì key đó không thuộc tập key đã khai báo. Đây không phải một value null được tạo bởi computing function.

### 4.2. Quy tắc của Map.ofLazy

- Tập key được xác định khi gọi factory; Map không hỗ trợ thêm hoặc xóa key.
- Value được tính theo từng key khi lần đầu được truy cập.
- Mỗi key được tính tối đa một lần, kể cả khi nhiều thread truy cập đồng thời cùng key.
- Key null, Set null hoặc computing function null làm factory ném `NullPointerException`.
- Value null không được phép; function trả null khiến mapping đó chuyển sang error state.
- Nếu Set key được sửa đổi sau khi tạo Map, Map trả về không phản ánh thay đổi đó.
- Set key phải sử dụng `equals()` làm quan hệ tương đương, hoặc comparator phải nhất quán với `equals()`; nếu không, hành vi không được xác định.
- Map không đảm bảo thứ tự lặp key.
- Map không thể sửa đổi và không Serializable.
- Map thuộc nhóm value-based collection; không dùng chính instance Map làm khóa đồng bộ và không phụ thuộc vào identity của instance.

**Giữ key ổn định.** Nếu key là object mutable và việc sửa object làm thay đổi `equals()` hoặc `hashCode()`, hành vi của Map có thể không còn được xác định đúng. Nên dùng String, enum hoặc record có thành phần ổn định làm key.

### 4.3. View và thao tác có thể kích hoạt value

| Thao tác | Hành vi |
|---|---|
| `keySet()` | Trả về view của miền key đã biết; không cần tính value. |
| `containsKey(key)` | Kiểm tra key có thuộc miền Map hay không. |
| `get(key)` | Tính value nếu key tồn tại và value chưa được tính. |
| `values()` | Các value trong view được tính khi truy cập. |
| `entrySet()` | Value trong entry view cũng được tính khi truy cập. |
| `equals()`, `hashCode()`, `toString()` | Có thể kích hoạt tính một hoặc nhiều value. |

Cẩn thận khi gọi:

```java
System.out.println(ROUTES);
System.out.println(ROUTES.values());
System.out.println(ROUTES.entrySet());
```

Các thao tác này có thể yêu cầu value để dựng kết quả hiển thị hoặc so sánh. Chúng có thể làm mất lợi ích trì hoãn nếu mục tiêu là chỉ khởi tạo một vài key.

## 5. So sánh miền index và miền key

| Tiêu chí | `List.ofLazy` | `Map.ofLazy` |
|---|---|---|
| Miền xác định trước | Kích thước nguyên `size`. | Set các key. |
| Định danh phần tử | Index số nguyên. | Key. |
| Computing function | `IntFunction`. | `Function`. |
| Lúc tính value | Lần đầu truy cập index. | Lần đầu truy cập key. |
| Đơn vị bảo đảm at-most-once | Mỗi index. | Mỗi key. |
| Thay đổi cấu trúc | Không thêm/xóa/thay thế phần tử. | Không thêm/xóa/thay đổi mapping. |
| Thứ tự | Theo index của List. | Không đảm bảo thứ tự key. |
| View | `subList()`, `reversed()` vẫn lazy. | `values()`, `entrySet()` vẫn lazy. |
| Serialization | Không Serializable. | Không Serializable. |

Quyết định chọn API:

- Dữ liệu được mô hình hóa tự nhiên bằng vị trí, chẳng hạn shard 0 đến shard N-1: dùng List.
- Dữ liệu được mô hình hóa bằng mã định danh, chẳng hạn route name hoặc enum: dùng Map.
- Nếu miền phần tử chưa biết trước hoặc cần thay đổi thường xuyên: dùng collection mutable hoặc cấu trúc cache phù hợp.

## 6. Bài tập 1 — Tạo danh sách shard có kích thước cố định

Một dịch vụ có 8 shard logic. Mỗi shard chứa một object quản lý kết nối và chỉ được tạo khi có request tới shard tương ứng.

```java
import java.util.List;

record Shard(int id, String name) {}

final class ShardRegistry {
    private static final int SHARD_COUNT = 8;

    private static final List<Shard> SHARDS =
            List.ofLazy(SHARD_COUNT, id -> {
                System.out.println("Initialize shard " + id);
                return new Shard(id, "shard-" + id);
            });

    static Shard shard(int id) {
        return SHARDS.get(id);
    }

    static int shardCount() {
        return SHARDS.size();
    }
}
```

Thử gọi:

```java
System.out.println(ShardRegistry.shardCount());
System.out.println(ShardRegistry.shard(3));
System.out.println(ShardRegistry.shard(3));
System.out.println(ShardRegistry.shard(6));
```

Quan sát:

- Kích thước là 8 ngay từ đầu.
- Shard 3 chỉ khởi tạo một lần.
- Shard 6 được khởi tạo khi được truy cập.
- Shard 0, 1, 2, 4, 5, 7 chưa cần khởi tạo.

Không dùng index tính từ dữ liệu người dùng mà chưa kiểm tra phạm vi. Nếu request có thể yêu cầu index ngoài 0–7, cần kiểm tra và trả lỗi nghiệp vụ rõ ràng trước khi gọi `get()`.

## 7. Bài tập 2 — Map cấu hình cho tập route cố định

Một API gateway có tập route đã biết trong lúc khởi động. Cấu hình của mỗi route có thể được đọc từ một nguồn cấu hình khi route thực sự được gọi.

```java
import java.util.Map;
import java.util.Set;

record GatewayRoute(String path, int maxAttempts) {}

final class GatewayRoutes {
    private static final Set<String> ROUTE_KEYS =
            Set.of("users", "payments", "reports");

    private static final Map<String, GatewayRoute> ROUTES =
            Map.ofLazy(ROUTE_KEYS, GatewayRoutes::load);

    private static GatewayRoute load(String key) {
        System.out.println("Load route configuration: " + key);

        return switch (key) {
            case "users" -> new GatewayRoute("/v1/users", 2);
            case "payments" -> new GatewayRoute("/v1/payments", 1);
            case "reports" -> new GatewayRoute("/v1/reports", 3);
            default -> throw new IllegalArgumentException(key);
        };
    }

    static GatewayRoute route(String key) {
        return ROUTES.get(key);
    }

    static boolean supports(String key) {
        return ROUTES.containsKey(key);
    }
}
```

Thử gọi:

```java
System.out.println(GatewayRoutes.supports("payments"));
System.out.println(GatewayRoutes.route("payments"));
System.out.println(GatewayRoutes.supports("unknown"));
System.out.println(GatewayRoutes.route("unknown"));
```

Kiểm tra rằng việc hỏi key có được hỗ trợ không không cần dựng cấu hình route. Chỉ khi lấy value mới cần gọi computing function.

Không dùng Map.ofLazy làm registry plugin nếu plugin có thể được đăng ký hoặc gỡ bỏ trong runtime. Tập key của Map này cố định sau khi factory được gọi.

## 8. Bài tập 3 — Kiểm tra đồng thời trên cùng index và key

Mỗi index/key có một trạng thái lazy riêng. Các thread cạnh tranh cùng một index hoặc key sẽ chờ kết quả của một lần tính duy nhất.

Ví dụ kiểm tra cùng index:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicIntegerArray;

record WorkerSlot(int index) {}

public class LazyListConcurrency {
    public static void main(String[] args) throws Exception {
        int workers = 32;
        int targetIndex = 4;
        var counts = new AtomicIntegerArray(8);

        List<WorkerSlot> slots = List.ofLazy(8, index -> {
            counts.incrementAndGet(index);
            return new WorkerSlot(index);
        });

        var ready = new CountDownLatch(workers);
        var start = new CountDownLatch(1);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<WorkerSlot>> results =
                    new ArrayList<>(workers);

            for (int i = 0; i < workers; i++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return slots.get(targetIndex);
                }));
            }

            ready.await();
            start.countDown();

            WorkerSlot first = results.getFirst().get();
            for (Future<WorkerSlot> result : results) {
                if (result.get() != first) {
                    throw new AssertionError("Different values");
                }
            }
        }

        System.out.println("Compute count = " + counts.get(targetIndex));
    }
}
```

Kết quả mong đợi:

```text
Compute count = 1
```

Có thể tạo bài tương tự cho Map bằng cách cho tất cả worker cùng gọi `routes.get("payments")` và dùng `AtomicInteger` đếm số lần computing function chạy.

Đối với các index khác nhau hoặc key khác nhau, không thiết kế supplier dựa trên giả định rằng mọi lần tính đều chạy tuần tự. Hãy coi các phép tính độc lập có thể diễn ra đồng thời và không chia sẻ mutable state không đồng bộ.

## 9. Xử lý lỗi và những trường hợp dễ nhầm

List lazy và Map lazy dùng hợp đồng lỗi tương tự LazyConstant:

| Tình huống | Hành vi |
|---|---|
| Function ném unchecked exception | Phần tử/key chuyển sang error state; lần đầu ném `NoSuchElementException` với exception gốc làm cause. |
| Truy cập lại phần tử/key lỗi | Ném `NoSuchElementException` không có cause; message chứa tên class của lỗi ban đầu. Function không chạy lại. |
| Function trả về null | Ném `NoSuchElementException` với `NullPointerException` làm cause; null không được lưu. |
| Function gọi đệ quy cùng index/key | Ném `NoSuchElementException` với `IllegalStateException` làm cause. |
| Nhiều thread cùng truy cập phần tử đang tính | Các thread cạnh tranh chờ đến khi value được tính hoặc phép tính thất bại. |

Ví dụ List có function trả null:

```java
List<String> names = List.ofLazy(3, index -> null);

try {
    names.get(1);
} catch (java.util.NoSuchElementException error) {
    System.out.println(error.getCause().getClass().getSimpleName());
}
```

Kết quả mong đợi:

```text
NullPointerException
```

Nếu miền dữ liệu cần biểu diễn giá trị có thể vắng mặt, hãy trả về một object `Optional` thay vì null:

```java
import java.util.List;
import java.util.Optional;

List<Optional<String>> aliases =
        List.ofLazy(4, index -> Optional.empty());
```

Với Map, `get(key)` trả null khi key không thuộc miền đã khai báo. Nhưng nếu key đã tồn tại và function trả null, đó là lỗi khởi tạo. Dùng `containsKey(key)` để phân biệt key không tồn tại với key có value cần được tính.

## 10. So sánh với các cấu trúc khác

### 10.1. List.ofLazy và ArrayList

| Nhu cầu | Phù hợp |
|---|---|
| Số vị trí cố định, phần tử tạo theo index khi cần, không sửa cấu trúc | `List.ofLazy` |
| Thêm, xóa, thay thế phần tử theo nghiệp vụ | `ArrayList` |
| Có sẵn toàn bộ value và muốn snapshot không sửa được | `List.copyOf` |

`ArrayList` thường khởi tạo phần tử khi ứng dụng thêm phần tử. Nó không tự ghi nhớ kết quả của một function theo từng index.

### 10.2. Map.ofLazy và computeIfAbsent

`Map.computeIfAbsent` là thao tác trên Map hiện có. Nó phù hợp khi key có thể phát sinh trong runtime và Map có thể thay đổi. `Map.ofLazy` phù hợp khi tập key đã biết và không thay đổi.

| Tiêu chí | `Map.ofLazy` | `computeIfAbsent` |
|---|---|---|
| Key domain | Cố định khi tạo. | Có thể thêm key mới. |
| Cấu trúc | Unmodifiable. | Phụ thuộc implementation; thường là mutable Map. |
| Khi tính | Lần đầu truy cập value của key đã khai báo. | Khi key chưa có mapping hoặc mapping null. |
| Null từ function | Lỗi; key chuyển sang error state. | Không ghi mapping; lần sau có thể tính lại. |
| Unchecked exception | Error state; lần sau không gọi function lại. | Exception được ném; không ghi mapping, lần sau có thể thử lại. |
| Dùng khi | Bảng tra cứu có miền key cố định. | Cache hoặc registry động. |

Không thay một cache động bằng Map.ofLazy chỉ vì muốn có tính lazy. Cần xác định trước miền key có thực sự hữu hạn và cố định hay không, cũng như chính sách retry sau lỗi.

### 10.3. Lazy collection và Stream

Stream pipeline cũng có tính lazy ở giai đoạn intermediate operation, nhưng nó không phải một List đã có kích thước và index cố định, cũng không tự bảo đảm memoization mỗi index/key. Khi cần collection truy cập ngẫu nhiên, có thể đọc lại nhiều lần và ghi nhớ mỗi phần tử sau lần đầu, lazy collection phù hợp hơn. Khi cần xử lý pipeline dữ liệu một lần, Stream phù hợp hơn.

## 11. Bộ nhớ, side effect và hiệu năng

### 11.1. Computing function có thể được giữ lại

Lazy List giữ computing function mạnh ít nhất cho đến khi tất cả phần tử đã được khởi tạo thành công hoặc chuyển sang error state. Lazy Map cũng giữ computing function trong khi còn value chưa được tính. Khi toàn bộ phần tử đã hoàn tất hoặc vào error state, implementation note cho biết function không còn được giữ mạnh và có thể được garbage collector thu hồi.

Với List hoặc Map chỉ được truy cập một phần, computing function có thể tiếp tục được giữ lại trong suốt thời gian collection còn sống. Nếu lambda capture một service, class loader hoặc object graph lớn, những đối tượng đó cũng có thể tiếp tục reachable. Thiết kế function gọn, chỉ capture những dependency thật sự cần thiết.

Nếu lambda capture một service graph lớn, collection có thể giữ graph đó trong bộ nhớ lâu hơn dự kiến. Tránh capture object lớn không cần thiết. Với Map, các key cũng được giữ trong collection suốt vòng đời Map.

### 11.2. Unmodifiable không đồng nghĩa deep immutable

Collection không cho thêm, xóa hoặc thay thế phần tử. Nhưng object được trả về vẫn có thể mutable:

```java
record MutableHolder(java.util.List<String> values) {}

List<MutableHolder> holders =
        List.ofLazy(1, index ->
                new MutableHolder(new java.util.ArrayList<>())
        );

holders.get(0).values().add("changed");
```

Cấu trúc List vẫn không đổi, nhưng nội dung của object bên trong đã đổi. Nếu cần snapshot bất biến, hãy trả về object immutable hoặc defensive copy trong computing function.

### 11.3. Constant folding là cơ hội tối ưu, không phải cam kết

Sau khi value được tính, JVM có thể tối ưu việc đọc lại value bằng constant folding trong một số cấu trúc tham chiếu phù hợp. Điều kiện thuận lợi gồm đường dẫn từ `static final` field qua các trusted fields tới lazy collection hoặc lazy constant.

Điều đó không có nghĩa mọi lần gọi `List.get()` hoặc `Map.get()` chắc chắn được biến thành hằng số. JVM quyết định dựa trên implementation, bytecode, trạng thái khởi tạo và tối ưu JIT. Không viết code dựa trên giả định rằng collection lazy luôn nhanh hơn collection eager.

Khi đo hiệu năng:

- Tách chi phí tạo collection, truy cập phần tử lần đầu và truy cập sau khởi tạo.
- Dùng JMH hoặc benchmark harness phù hợp; tránh kết luận từ một vòng lặp `nanoTime()` đơn lẻ.
- Giữ kết quả benchmark có thể quan sát để tránh dead-code elimination.
- Chạy nhiều fork và warm-up đủ để JIT ổn định.
- Đo heap và retained object nếu computing function capture nhiều object.
- So sánh với `ArrayList`, `List.copyOf`, `Map.of` hoặc cache phù hợp cùng workload.

## 12. Bài tập tổng hợp

Thực hiện bằng JDK 27 có bật preview:

1. Tạo một List lazy có 1.000 vị trí. Chỉ truy cập index 2, 17 và 999; ghi lại số lần computing function chạy.
2. Gọi lại các index đã truy cập và xác nhận mỗi index chỉ được tính một lần.
3. Tạo Map lazy với 5 key cấu hình. Truy cập hai key; xác nhận các key còn lại chưa cần tính.
4. Thử key không tồn tại và key có function trả null. Giải thích vì sao hai trường hợp cho kết quả khác nhau.
5. Sửa Set key ban đầu sau khi tạo Map và quan sát Map không phản ánh thay đổi đó.
6. Truy cập cùng index/key từ 32 virtual threads; kiểm tra function chạy một lần cho đơn vị tương ứng.
7. Gọi `toString()` hoặc duyệt toàn bộ collection; quan sát việc các value có thể được khởi tạo ngoài dự kiến.
8. Thử function ném exception và truy cập lại; xác nhận error state không tự retry.
9. So sánh với `computeIfAbsent` trên Map mutable khi function ném exception hoặc trả null.
10. Đo thời gian khởi tạo eager so với lazy cho workload chỉ truy cập một phần nhỏ phần tử.

Bảng kết quả:

| Thử nghiệm | Dữ liệu cần ghi | Kết quả mong đợi |
|---|---|---|
| List 1.000 phần tử | Số index đã truy cập, số lần function chạy | Chỉ index được yêu cầu mới cần tính. |
| Truy cập lặp | Count theo từng index | Mỗi index tối đa một lần. |
| Map 5 key | Key đã truy cập, số lần function chạy | Chỉ key được yêu cầu mới cần tính. |
| Key ngoài miền | `containsKey`, `get` | Không có mapping; `get` trả null. |
| Null từ function | Exception và cause | Error state với cause là NullPointerException. |
| Nhiều thread cùng key/index | Count và object identity | Function chạy một lần; cùng đơn vị nhận cùng value. |
| `toString()` / iteration | Count trước và sau | Có thể kích hoạt nhiều value. |
| Function ném lỗi | Exception ở lần 1/lần 2 | Lần sau không gọi function lại. |
| Eager vs lazy | Startup, first access, retained heap | Kết luận theo tỷ lệ truy cập và workload thực. |

## 13. Checklist chọn API

- [ ] Số phần tử có thể xác định trước bằng một số nguyên? Nếu có, xem xét `List.ofLazy`.
- [ ] Tập key có thể xác định trước bằng Set? Nếu có, xem xét `Map.ofLazy`.
- [ ] Collection có cần thêm/xóa key hoặc phần tử trong runtime? Nếu có, chọn collection mutable.
- [ ] Function có thể trả null hoặc cần retry? Thiết kế Optional và chính sách lỗi rõ ràng.
- [ ] Function có thể chạy đồng thời cho các index/key khác nhau? Bảo vệ shared mutable state.
- [ ] Có nguy cơ function block vô hạn hoặc gọi đệ quy? Xử lý trước khi đưa vào lazy collection.
- [ ] Có log hoặc debug bằng cách in nguyên collection? Kiểm tra vì thao tác đó có thể kích hoạt tính nhiều value.
- [ ] Có phụ thuộc serialization hoặc thứ tự key? Hai lazy collection này không Serializable và Map không đảm bảo iteration order.
- [ ] Build và runtime đã bật preview trên cùng JDK 27? Kiểm tra lại khi nâng cấp.
- [ ] Đã benchmark workload thực tế thay vì mặc định lazy luôn nhanh hơn?

## Tài liệu tham khảo chính thức

- [JEP 531: Lazy Constants (Third Preview)](https://openjdk.org/jeps/531)
- [List API — Java SE 27, List.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html)
- [Map API — Java SE 27, Map.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html)
- [LazyConstant API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [Java SE 27 Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)

