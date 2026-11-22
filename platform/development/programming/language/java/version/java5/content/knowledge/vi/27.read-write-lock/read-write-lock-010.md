# Bảo vệ dữ liệu dùng chung trong bộ nhớ đệm đọc nhiều

## 1. Vấn đề cần giải quyết

Một bộ nhớ đệm (cache) giữ dữ liệu trong bộ nhớ để tránh tính toán hoặc truy vấn lại quá thường xuyên. Ví dụ, hàng trăm yêu cầu đọc bảng giá trong khi chỉ thỉnh thoảng có một lần thay bảng giá.

Khi nhiều luồng cùng sử dụng, vấn đề không chỉ là hai luồng cùng gọi `put()`. Một luồng có thể đang đọc trong khi luồng khác xóa và nạp lại dữ liệu; hoặc người đọc có thể lấy số phiên bản của bảng mới nhưng lại nhận một phần dữ liệu của bảng cũ.

Cần xác định **đơn vị trạng thái phải nhất quán** trước khi chọn khóa. Với bảng giá, đơn vị đó có thể gồm:

- Các cặp mã sản phẩm → giá.
- Số phiên bản tương ứng.
- Thông tin dữ liệu còn hợp lệ hay cần nạp lại.

Nếu các trường có quan hệ với nhau, chúng phải đi qua cùng một giao thức bảo vệ. Bảo vệ riêng từng thao tác mà để người đọc ghép kết quả từ nhiều thời điểm vẫn có thể sai yêu cầu.

`ReadWriteLock` cung cấp hai quyền gắn với cùng một miền dữ liệu: nhiều luồng có thể giữ quyền đọc, còn quyền ghi là độc quyền. Trong bài này, lớp triển khai được dùng là `ReentrantReadWriteLock`.

Mục tiêu là cho phép các lần đọc an toàn cùng tiến hành, đồng thời giữ cho mỗi lần cập nhật không bị người đọc nhìn thấy ở trạng thái trung gian.

## 2. Xác định giao thức bảo vệ

Với một `HashMap` riêng tư và những trường liên quan, có thể đặt quy tắc:

| Hoạt động | Quyền cần giữ |
|---|---|
| Lấy một giá trị đã lưu | Khóa đọc |
| Kiểm tra có dữ liệu hay không | Khóa đọc |
| Đọc phiên bản cùng toàn bộ dữ liệu tương ứng | Một lượt khóa đọc bao trùm cả hai |
| Duyệt bản đồ để tính tổng hoặc tạo bản sao | Khóa đọc trong suốt quá trình duyệt |
| Thêm, thay, xóa dữ liệu | Khóa ghi |
| Đổi cờ hợp lệ hoặc số phiên bản | Khóa ghi, cùng cập nhật dữ liệu liên quan |
| Nạp từ nguồn bên ngoài | Tùy thiết kế; tránh giữ khóa toàn cục trong công việc chậm |

`HashMap` không tự đồng bộ hóa. Khóa chỉ có hiệu lực khi **mọi đường truy cập** tuân thủ quy tắc. Một phương thức đọc bỏ qua khóa vì “chỉ có get” vẫn phá vỡ giao thức khi luồng khác có thể ghi.

Khóa đọc không tự biến mã bên trong thành chỉ đọc. Lập trình viên phải bảo đảm nó không sửa dữ liệu được bảo vệ. Chẳng hạn, `computeIfAbsent()` có thể thêm phần tử nên không được gọi trên `HashMap` chỉ dưới khóa đọc.

Một ví dụ ít rõ hơn là [`LinkedHashMap` được cấu hình theo thứ tự truy cập](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html): một lần lấy giá trị có thể cập nhật thứ tự bên trong. Không thể phân loại quyền chỉ dựa trên tên phương thức; phải xét hành vi thực tế.

Nếu đối tượng bộ nhớ đệm được chia sẻ giữa các luồng, bản thân đối tượng đó cũng phải được công bố an toàn, chẳng hạn tạo trước khi giao tác vụ cho bộ thực thi hoặc thông qua một cấu trúc chia sẻ có cơ chế đồng bộ phù hợp.

## 3. Ví dụ: đọc ảnh chụp bảng giá nhất quán

Giả sử mỗi lần cập nhật thay toàn bộ bảng giá. Người đọc cần một ảnh chụp gồm số phiên bản và bản đồ giá tương ứng.

Thiết kế dưới đây giữ `prices` và `version` dưới cùng một cặp khóa. `snapshot()` giữ khóa đọc cho đến khi sao chép xong. Sau đó người gọi làm việc với bản sao không cho sửa, không tiếp tục giữ khóa của bộ nhớ đệm.

Lưu thành `PriceCacheDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class PriceCacheDemo {
    private record Snapshot(long version, Map<String, Integer> prices) {
        int total() {
            return prices.values().stream()
                    .mapToInt(Integer::intValue)
                    .sum();
        }
    }

    private static final class PriceCache {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private final Lock read = rw.readLock();
        private final Lock write = rw.writeLock();

        private final Map<String, Integer> prices = new HashMap<>();
        private long version;

        void replaceAll(Map<String, Integer> newPrices) {
            // Validate/copy caller-owned data before taking the cache lock.
            Map<String, Integer> prepared = Map.copyOf(newPrices);

            write.lock();
            try {
                prices.clear();
                prices.putAll(prepared);
                version++;
            } finally {
                write.unlock();
            }
        }

        Snapshot snapshot() {
            read.lock();
            try {
                return new Snapshot(version, Map.copyOf(prices));
            } finally {
                read.unlock();
            }
        }
    }

    public static void main(String[] args) {
        PriceCache cache = new PriceCache();
        cache.replaceAll(Map.of("tea", 100, "coffee", 200));
        Snapshot first = cache.snapshot();

        cache.replaceAll(Map.of("tea", 200, "coffee", 300));
        Snapshot second = cache.snapshot();

        System.out.println("first.version=" + first.version());
        System.out.println("first.total=" + first.total());
        System.out.println("second.version=" + second.version());
        System.out.println("second.total=" + second.total());
        System.out.println("first.still=" + first.total());

        boolean unmodifiable = false;
        try {
            first.prices().put("water", 50);
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        System.out.println("snapshot.unmodifiable=" + unmodifiable);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 PriceCacheDemo.java
java PriceCacheDemo
```

Stdout:

```text
first.version=1
first.total=300
second.version=2
second.total=500
first.still=300
snapshot.unmodifiable=true
```

### Vì sao ảnh chụp nhất quán?

Trong lúc `snapshot()` giữ khóa đọc, không có luồng khác được giữ khóa ghi. Vì vậy, việc đọc `version` và sao chép `prices` thuộc cùng một trạng thái được bảo vệ.

Trong lúc `replaceAll()` giữ khóa ghi, người đọc không vào giữa `clear()`, `putAll()` và `version++`. Họ nhận trạng thái trước hoặc sau lần cập nhật thành công, không nhận bảng đang được thay dở.

Ảnh chụp `first` tiếp tục có tổng `300` sau lần thay bảng tiếp theo, vì nó không phải một khung nhìn trực tiếp vào `prices`.

`Map.copyOf()` không cho sửa cấu trúc bản đồ và không nhận khóa/giá trị `null`. Nó không sao chép sâu các đối tượng bên trong. Ở ví dụ này, `String` và `Integer` là bất biến nên có thể dùng ảnh chụp sau khi nhả khóa. Nếu giá trị là một danh sách sửa được, cần sao chép phù hợp hoặc thiết kế giá trị bất biến.

Bản đồ đầu vào `newPrices` thuộc người gọi. Người gọi không được sửa nó đồng thời với việc tạo bản sao nếu bản đồ đó không hỗ trợ truy cập như vậy. Khóa bên trong bộ nhớ đệm không bảo vệ các đối tượng đầu vào nằm ngoài quyền sở hữu của nó.

`finally` bảo đảm nhả khóa, không cung cấp giao dịch hoàn tác. Ví dụ chuẩn bị và kiểm tra dữ liệu đầu vào trước khi thay trạng thái để giảm lỗi trong vùng ghi. Nếu nghiệp vụ có nhiều bước có thể thất bại, cần thiết kế thêm cách chuẩn bị/công bố trạng thái mới; không dựa vào `unlock()` để phục hồi dữ liệu.

### Vì sao không tách thành getVersion() và getAllPrices()?

Hai phương thức có thể đều lấy khóa đọc đúng, nhưng nếu người gọi gọi lần lượt thì luồng ghi có thể cập nhật ở giữa hai lời gọi. Kết quả ghép lại chưa chắc cùng phiên bản.

Khi yêu cầu là một kết quả tổng hợp nhất quán, cung cấp một phương thức thực hiện toàn bộ lần đọc trong cùng vùng bảo vệ, như `snapshot()`.

## 4. Đừng để dữ liệu sửa được thoát khỏi khóa

Một bộ nhớ đệm có thể khóa đúng mọi thao tác trên bản đồ mà vẫn không an toàn vì giá trị bên trong bị sửa bên ngoài.

Ví dụ minh họa ý tưởng sai, không phải chương trình độc lập:

```text
khóa đọc
    lấy List từ bản đồ
nhả khóa đọc
trả List gốc cho người gọi
    người gọi thêm/xóa phần tử mà không lấy khóa
```

Khóa đã bảo vệ việc lấy tham chiếu, nhưng không bảo vệ các lần sửa danh sách sau đó.

Có ba hướng thiết kế thường dùng:

1. Lưu và trả các giá trị bất biến.
2. Tạo bản sao đủ sâu dưới khóa rồi trả bản sao.
3. Cung cấp phương thức nghiệp vụ thao tác bên trong bộ nhớ đệm thay vì đưa cấu trúc nội bộ ra ngoài.

Không trả trực tiếp `keySet()`, `values()`, `entrySet()` hoặc một `Iterator` của bản đồ rồi kỳ vọng lượt khóa đã kết thúc vẫn bảo vệ chúng. Các đối tượng này thường là khung nhìn gắn với dữ liệu gốc.

Một lớp bọc “không cho sửa” quanh bản đồ gốc cũng không nhất thiết là ảnh chụp: luồng ghi bên trong vẫn có thể thay bản đồ gốc. Cần phân biệt **không cho người gọi sửa** với **không thay đổi theo các lần cập nhật về sau**.

## 5. Khi chưa có dữ liệu: nạp ở đâu?

Một lần không tìm thấy khóa được gọi là trượt bộ nhớ đệm (cache miss). Lúc này cần tính toán hoặc truy vấn nguồn dữ liệu.

Không nên giữ khóa đọc rồi gọi `write.lock()` để thêm dữ liệu vào `ReentrantReadWriteLock`. Lớp này không hỗ trợ nâng cấp trực tiếp từ quyền đọc sang quyền ghi khi vẫn giữ lượt đọc.

Có hai hướng cơ bản:

| Hướng | Ưu điểm | Đánh đổi |
|---|---|---|
| Nhả đọc, lấy ghi, kiểm tra lại, nạp dưới ghi | Đơn giản để tuần tự hóa việc nạp | Một lần nạp chậm có thể chặn mọi lượt đọc/ghi dùng cùng khóa |
| Nhả đọc, nạp ngoài khóa, lấy ghi và kiểm tra lại | Không giữ khóa toàn cục khi nạp chậm | Nhiều luồng có thể cùng nạp; cần quy tắc chọn kết quả |

Đừng gọi cơ sở dữ liệu, mạng hoặc mã của bên ngoài dưới khóa toàn cục mà chưa xem xét thời gian chờ, vòng chờ và tác động đến mọi khóa dữ liệu khác trong bộ nhớ đệm.

### Mẫu nạp ngoài khóa với kiểm tra lại

Với dữ liệu không có `null` và không có thao tác vô hiệu hóa đồng thời, có thể dùng chuỗi:

1. Lấy khóa đọc, tìm dữ liệu; có thì trả về.
2. Nhả khóa đọc.
3. Nạp một ứng viên ngoài khóa.
4. Lấy khóa ghi và tìm lại.
5. Nếu luồng khác đã lưu giá trị, dùng giá trị đó; nếu chưa, lưu ứng viên.
6. Nhả khóa ghi.

Lần kiểm tra thứ hai phải ở bên trong khóa ghi. Nếu kiểm tra ngoài khóa rồi mới lấy khóa ghi, luồng khác vẫn có thể thêm giá trị ở giữa.

## 6. Chương trình: nạp trùng nhưng chỉ chọn một giá trị đã lưu

Ví dụ dưới đây cố ý cho hai luồng cùng trượt trên một khóa và cùng chạy hàm nạp. Cả hai hoàn thành với **cùng tham chiếu đã được chọn lưu** trong bản đồ, mặc dù hàm nạp được gọi hai lần.

Đây là chính sách cho phép nạp trùng, không phải cơ chế hợp nhất yêu cầu để chỉ nạp một lần. Chính sách này phù hợp khi việc nạp có thể thực hiện nhiều lần an toàn và chi phí chấp nhận được.

Lưu thành `ReadMostlyCacheDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.function.Function;

public class ReadMostlyCacheDemo {
    private record Item(String name) {
    }

    private static final class Cache<K, V> {
        private final Map<K, V> entries = new HashMap<>();
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private final Lock read = rw.readLock();
        private final Lock write = rw.writeLock();

        V getOrLoad(K key, Function<? super K, ? extends V> loader) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(loader, "loader");

            read.lock();
            try {
                V hit = entries.get(key);
                if (hit != null) {
                    return hit;
                }
            } finally {
                read.unlock();
            }

            V candidate = Objects.requireNonNull(
                    loader.apply(key), "loader returned null");

            write.lock();
            try {
                V existing = entries.get(key);
                if (existing != null) {
                    return existing;
                }

                entries.put(key, candidate);
                return candidate;
            } finally {
                write.unlock();
            }
        }

        int size() {
            read.lock();
            try {
                return entries.size();
            } finally {
                read.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Cache<String, Item> cache = new Cache<>();
        AtomicInteger loadCalls = new AtomicInteger();
        CountDownLatch bothLoading = new CountDownLatch(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Function<String, Item> loader = key -> {
            loadCalls.incrementAndGet();
            bothLoading.countDown();
            try {
                if (!bothLoading.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Both loaders did not start");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Loading interrupted", e);
            }
            return new Item(key);
        };

        try {
            var firstTask = pool.submit(
                    () -> cache.getOrLoad("coffee", loader));
            var secondTask = pool.submit(
                    () -> cache.getOrLoad("coffee", loader));

            Item first = firstTask.get(10, TimeUnit.SECONDS);
            Item second = secondTask.get(10, TimeUnit.SECONDS);
            Item hit = cache.getOrLoad("coffee", key -> {
                throw new AssertionError("A cache hit must not load");
            });

            System.out.println("loader.calls=" + loadCalls.get());
            System.out.println("same.result=" + (first == second));
            System.out.println("hit.same=" + (hit == first));
            System.out.println("cache.size=" + cache.size());
            System.out.println("item.name=" + hit.name());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ReadMostlyCacheDemo.java
java ReadMostlyCacheDemo
```

Stdout khi các tác vụ hoàn thành trong giới hạn chờ:

```text
loader.calls=2
same.result=true
hit.same=true
cache.size=1
item.name=coffee
```

`CountDownLatch` buộc cả hai hàm nạp bắt đầu trước khi một trong hai trả ứng viên. Vì vậy phép thử chủ động tạo ra tình huống nạp trùng mà không dựa vào `Thread.sleep()`.

Không cần biết tác vụ nào giành khóa ghi trước. Tác vụ còn lại sẽ thấy giá trị đã lưu và trả giá trị đó, nên các phép so sánh tham chiếu vẫn có kết quả xác định.

Các mốc chờ có giới hạn giúp chương trình báo lỗi nếu môi trường không hoàn thành công việc kịp; chúng không phải thời gian mà thuật toán bắt buộc phải mất.

### Hợp đồng và giới hạn của ví dụ

- Khóa và giá trị không được `null`; vì vậy `get()==null` có nghĩa là chưa có dữ liệu.
- `Item` chứa `String` bất biến. Lớp `Cache<K,V>` tổng quát không tự làm cho mọi kiểu `V` bất biến.
- Hàm nạp có thể được gọi đồng thời nhiều lần cho cùng khóa; không đặt tác dụng phụ đòi hỏi đúng một lần vào hàm này.
- Nếu hàm nạp ném ngoại lệ, lời gọi đó không lưu ứng viên và không đang giữ khóa của bộ nhớ đệm.
- Ứng viên thua cuộc bị bỏ đi. Ví dụ dùng đối tượng dữ liệu thuần; nếu ứng viên sở hữu tài nguyên cần đóng, phải bổ sung chính sách giải phóng.
- Ví dụ không có thời hạn lưu, giới hạn dung lượng, xóa mục hay vô hiệu hóa. Không suy ra những bảo đảm này từ việc có khóa.

## 7. Vô hiệu hóa và độ mới là một yêu cầu riêng

Khóa bảo vệ dữ liệu trong bộ nhớ không tự bảo đảm dữ liệu còn mới so với cơ sở dữ liệu hay dịch vụ bên ngoài.

Mẫu nạp ngoài khóa còn có một cuộc đua quan trọng khi thêm thao tác vô hiệu hóa:

```text
A: thấy chưa có dữ liệu và bắt đầu nạp phiên bản cũ
B: vô hiệu hóa hoặc cập nhật dữ liệu
A: nạp xong, lấy khóa ghi và lưu lại phiên bản cũ
```

Bản đồ có thể vẫn được bảo vệ đúng về truy cập đồng thời, nhưng chính sách độ mới đã bị vi phạm.

Nếu yêu cầu là “sau lần vô hiệu hóa này không được công bố kết quả nạp bắt đầu trước đó”, cần thêm cơ chế như số thế hệ/phiên bản. Luồng nạp ghi nhận thế hệ trước khi đi nạp và kiểm tra lại thế hệ dưới khóa ghi trước khi công bố; nếu đã đổi, phải bỏ kết quả hoặc thử lại theo chính sách đã định. Với vô hiệu hóa từng khóa, thường cần theo dõi thế hệ phù hợp cho từng khóa.

Nếu yêu cầu chỉ một lần nạp đang chạy cho mỗi khóa, cần cơ chế hợp nhất yêu cầu theo khóa, chẳng hạn lưu một đại diện tác vụ đang nạp và cho các yêu cầu khác chờ cùng kết quả. Thiết kế đó còn phải quy định xử lý lỗi, hủy, vô hiệu hóa và loại bỏ trạng thái tác vụ; không chỉ thêm một khóa đọc/ghi là đủ.

Bộ nhớ đệm thực tế cũng cần quyết định thời hạn lưu, mức độ chấp nhận dữ liệu cũ và dung lượng. Đây là chính sách nghiệp vụ/vận hành bổ sung, không phải chức năng mặc định của `ReadWriteLock`.

## 8. Nhìn thấy dữ liệu, phạm vi khóa và chi phí

Cặp khóa đọc/ghi có bảo đảm đồng bộ bộ nhớ: người đọc lấy thành công khóa đọc thấy các cập nhật trước lần nhả khóa ghi tương ứng trước đó. Vì vậy giao thức nhất quán vừa tránh truy cập xung đột vừa công bố thay đổi giữa các luồng.

Không cần đánh dấu từng trường được bảo vệ đúng là `volatile`. Ngược lại, chỉ dùng một tham chiếu `volatile HashMap` rồi tiếp tục sửa nội dung bản đồ không làm các thao tác trên bản đồ tự an toàn.

Với nhiều trường liên quan, một nhóm giá trị được đọc dưới một lượt khóa có ý nghĩa khác với việc đọc các trường `volatile` riêng rẽ: yêu cầu ảnh chụp nhất quán cần được thiết kế rõ.

### Đọc nhiều không đồng nghĩa luôn nhanh hơn

Các yếu tố cần đo gồm thời gian mỗi lần đọc, mức độ tranh chấp, số lõi, kích thước dữ liệu và độ dài vùng ghi. Nếu một lần đọc chỉ lấy một tham chiếu rất nhanh, chi phí quản lý khóa đọc có thể không đáng.

Trong chính ví dụ bảng giá, sao chép cả bản đồ dưới khóa đọc làm thời gian giữ khóa tăng theo dữ liệu. Đây là cách tạo ảnh chụp đơn giản để học tính nhất quán, không phải khẳng định rằng sao chép toàn bộ cho mọi yêu cầu là lựa chọn tốt nhất.

Khi đo ứng dụng, xem cả độ trễ cập nhật và độ trễ cao của yêu cầu, không chỉ tổng số lượt đọc mỗi giây. Một nhóm người đọc chạy lâu có thể làm người ghi chờ đáng kể.

`ReentrantReadWriteLock` mặc định không công bằng; có thể chọn chế độ công bằng, nhưng chế độ đó không tạo giới hạn cứng cho thời gian chờ. Quyết định phải dựa vào hành vi và phép đo của ứng dụng.

### Những lựa chọn cần phân biệt

| Nhu cầu chính | Hướng thiết kế có thể xem xét |
|---|---|
| Nhiều thao tác cần cùng bảo vệ quan hệ giữa nhiều trường/khóa | Một cặp khóa đọc/ghi cho miền trạng thái đó |
| Các mục độc lập, cần thao tác đồng thời theo từng khóa | [`ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) với các thao tác nguyên tử phù hợp |
| Thay toàn bộ trạng thái bất biến, người đọc chỉ lấy một phiên bản | Công bố một đối tượng trạng thái bất biến qua tham chiếu phù hợp |
| Vùng xử lý ngắn, cấu trúc đơn giản | Khóa loại trừ như `synchronized` hoặc `ReentrantLock` |
| Cần hết hạn, giới hạn dung lượng, hợp nhất nạp và số liệu vận hành | Một thiết kế hoặc thư viện bộ nhớ đệm có chính sách tương ứng |

Bảng này là cách phân loại yêu cầu. Chọn theo giao thức nhất quán và phép đo, không theo một tỷ lệ đọc/ghi cố định.

## 9. Những lỗi dễ bỏ sót khi rà mã

- Dùng khóa đọc và khóa ghi từ hai đối tượng khác nhau: chúng không tạo thành một cặp bảo vệ chung.
- Tạo một khóa mới trong mỗi lần gọi phương thức: các luồng không tranh cùng khóa.
- Chỉ khóa `put()` nhưng để `get()`, `size()` hoặc vòng lặp duyệt bản đồ chạy ngoài giao thức.
- Đọc số phiên bản và dữ liệu bằng hai lời gọi độc lập rồi cho rằng chúng cùng thời điểm.
- Sửa đối tượng giá trị sau khi đã trả nó ra ngoài khóa.
- Thêm dữ liệu bằng `computeIfAbsent()` dưới khóa đọc.
- Giữ khóa đọc trong khi đợi tác vụ khác mà tác vụ đó cần khóa ghi.
- Chỉ kiểm tra trượt một lần trước khi lấy khóa ghi.
- Nhầm “truy cập an toàn” với “luôn là dữ liệu mới nhất”.
- Dựa vào `ConcurrentModificationException` để phát hiện mọi truy cập sai. Việc không có ngoại lệ không chứng minh chương trình đúng.

## 10. Thực hành

1. Với bảng giá, vì sao `version` phải được đọc trong cùng vùng khóa với việc sao chép `prices`?  
   Vì nếu đọc riêng, một lần thay bảng có thể chen vào và khiến phiên bản không tương ứng với dữ liệu.

2. Thay `Integer` bằng `List<Integer>` trong ảnh chụp có còn an toàn khi dùng `Map.copyOf()` không?  
   Chưa đủ. Cần giải quyết cả khả năng sửa các danh sách bên trong.

3. Vì sao hai hàm nạp chạy ở ví dụ thứ hai nhưng bản đồ chỉ có một mục?  
   Công việc nạp ở ngoài khóa, còn bước chọn/lưu được kiểm tra lại và thực hiện dưới khóa ghi.

4. Nếu thêm `invalidate(key)`, có được dùng nguyên mẫu nạp ngoài khóa mà không phân tích lại không?  
   Không. Kết quả nạp bắt đầu trước vô hiệu hóa có thể được lưu trở lại sau đó.

5. Nếu ảnh chụp rất lớn và mỗi lần đọc sao chép đều tốn thời gian, nên kiểm tra điều gì?  
   Đo thời gian giữ khóa, độ trễ người ghi và cân nhắc công bố trạng thái bất biến dùng chung theo phiên bản.

## 11. Tài liệu chính thức

- [ReadWriteLock — quyền truy cập và đồng bộ bộ nhớ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html)
- [ReentrantReadWriteLock — đặc tính và ví dụ bảo vệ bộ sưu tập](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [HashMap — yêu cầu đồng bộ hóa khi truy cập đồng thời](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html)
- [Map — bản đồ không cho sửa và Map.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html)

Bài dùng các API hiện hành; hai chương trình độc lập chạy được từ JDK 17.
