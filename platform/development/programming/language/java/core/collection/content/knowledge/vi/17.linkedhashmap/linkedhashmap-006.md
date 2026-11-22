# Giới hạn an toàn đa luồng của bộ nhớ đệm tự viết

## 1. Cache đúng ở một luồng chưa có nghĩa đúng khi dùng chung

Một bộ nhớ đệm (cache) tự viết bằng LinkedHashMap có thể rất ngắn: lấy theo khóa, khi thiếu thì tải dữ liệu, thêm vào map, và loại mục ít được dùng gần đây nhất khi vượt giới hạn.

Ở một luồng, những bước ấy có vẻ nối tiếp tự nhiên. Khi hai luồng cùng dùng cache, chúng có thể xen kẽ ở bất kỳ khoảng trống nào mà thiết kế cho phép.

Một lỗi không nhất thiết biểu hiện thành ngoại lệ. Có thể cấu trúc map vẫn còn dùng được nhưng:

- Cùng một khóa bị tải nhiều lần.
- Giá trị cũ ghi đè dữ liệu vừa được làm mới.
- Giới hạn số entry bị vượt hoặc loại sai mục.
- Vòng duyệt thấy trạng thái không nhất quán.
- Đối tượng giá trị bị sửa đồng thời dù map được bảo vệ.
- Một hàm tải chậm chặn mọi yêu cầu khác.

Mục tiêu của bài là hiểu **phạm vi bảo đảm của từng cách đồng bộ**, xây một ví dụ nhỏ có hợp đồng rõ ràng, rồi nhận diện những yêu cầu mà ví dụ ấy chưa giải quyết.

Không cần cố tạo một lỗi phá hỏng LinkedHashMap bằng cách chạy đua không kiểm soát. Ta có thể chứng minh một vấn đề cụ thể bằng lịch xen kẽ được điều khiển và phân tích vùng bảo vệ.

## 2. “An toàn đa luồng” gồm nhiều câu hỏi khác nhau

| Lớp vấn đề | Câu hỏi cần trả lời |
| --- | --- |
| Tính toàn vẹn cấu trúc | Bảng băm và liên kết thứ tự có bị thao tác đồng thời sai cách không? |
| Khả năng nhìn thấy dữ liệu | Luồng đọc có quan hệ đồng bộ để thấy những ghi cần thiết không? |
| Tính nguyên tử | Một thao tác logic nhiều bước có bị luồng khác chen vào không? |
| Chính sách dung lượng | Thêm, cập nhật thứ tự và loại mục có thống nhất trong cùng quy tắc không? |
| Phối hợp tải | Những yêu cầu đồng thời cho cùng khóa có dùng chung một lần tải không? |
| Vòng đời dữ liệu | Invalidate, lỗi tải và tải đang chạy được hiểu thế nào? |
| Đối tượng giá trị | Ai được sửa giá trị sau khi lấy ra, và bằng cách nào? |
| Khả năng phục vụ | Một yêu cầu chậm có chặn toàn bộ cache không? |

Một cấu trúc Map an toàn ở từng phương thức chưa tự trả lời toàn bộ bảng này.

Khi nói “cache an toàn”, hãy nêu rõ những thao tác nào, những bất biến nào và điều kiện sử dụng nào được bảo đảm. Không dùng một nhãn chung để che nhiều quyết định chưa có.

## 3. LinkedHashMap access-order có thao tác đọc làm thay đổi cấu trúc

LinkedHashMap không tự đồng bộ. Tài liệu [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html) nêu yêu cầu phối hợp khi các luồng dùng chung và có thay đổi cấu trúc.

Trong chế độ access-order, get trúng một entry có thể đưa nó về cuối chuỗi. Vì vậy nhiều luồng chỉ gọi get cũng có thể cùng sửa liên kết thứ tự.

### 3.1. Không chỉ khóa put và remove

Nếu một thiết kế khóa put/remove nhưng để get đi tự do vì cho rằng “get chỉ đọc”, nó chưa bảo vệ đầy đủ map access-order.

Ngay cả một phương thức không tự đổi thứ tự như containsKey cũng không được tùy ý đọc cấu trúc đang bị luồng khác sửa mà không có cơ chế phối hợp phù hợp.

Phải xét trạng thái thực sự được đụng tới, không phân loại an toàn chỉ theo tên phương thức.

### 3.2. Read lock không tự phù hợp với get

Một khóa đọc–ghi cho phép nhiều bên cùng giữ read lock. Điều đó chỉ hợp lý nếu những thao tác trong vùng đọc thật sự không cùng sửa trạng thái cần bảo vệ.

Get của map access-order không thỏa giả định ấy trong mọi trường hợp. Đưa mọi get vào read lock rồi cho chúng chạy song song không tự biến chuỗi thứ tự thành an toàn.

Nếu vẫn muốn dùng mô hình đọc–ghi, phải xác định đúng phần nào cần bảo vệ độc quyền. Đừng thêm một lớp khóa phức tạp chỉ để giữ lại một giả định đọc sai.

### 3.3. Fail-fast không thay cơ chế đồng bộ

ConcurrentModificationException chỉ hỗ trợ phát hiện một số cách dùng sai theo khả năng.

Không thấy ngoại lệ không chứng minh không có tranh chấp dữ liệu. Bắt ngoại lệ rồi thử lại cũng không sửa một cấu trúc được chia sẻ sai quy tắc.

Đồng bộ phải đến từ thiết kế truy cập chung, không đến từ việc hy vọng iterator phát hiện mọi lỗi.

### 3.4. RemoveEldestEntry không tự thêm sự đồng bộ

Override removeEldestEntry chỉ bổ sung quyết định loại mục trong đường thêm của map. Nó không tự tạo khóa bảo vệ cho get, put, các liên kết thứ tự hoặc những view được trả ra.

Một lớp con LinkedHashMap có quy tắc size() > limit vẫn cần cùng một giao thức đa luồng cho mọi đường truy cập. Nếu đường gọi được bao bởi khóa đúng, hook chạy trong ngữ cảnh bảo vệ ấy; bản thân hook không thay trách nhiệm phối hợp bên ngoài.

## 4. Khóa chung bảo vệ điều gì?

Một phương án dễ lập luận là dùng cùng một monitor để bảo vệ toàn bộ trạng thái cache và mọi thao tác lên trạng thái ấy.

Theo [Java Language Specification, chương 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html), mở khóa một monitor có quan hệ happens-before với lần khóa tiếp theo trên chính monitor đó.

Điều này giúp tạo cả sự loại trừ lẫn quan hệ nhìn thấy dữ liệu giữa các đoạn mã cùng tuân quy tắc.

### 4.1. Cùng trạng thái phải dùng cùng khóa

Khóa ở một phương thức nhưng dùng một đối tượng khác ở phương thức còn lại không tạo cùng vùng bảo vệ.

Tạo new Object() riêng mỗi lần gọi rồi synchronized trên đối tượng mới cũng không phối hợp được những lời gọi với nhau.

Một đối tượng khóa private final thuộc cache giúp làm rõ quyền sở hữu. Toàn bộ đường truy cập map, kể cả size, invalidate và chụp danh sách khóa, phải tuân cùng quy tắc.

### 4.2. Final và volatile không thay khóa cho các lần sửa tiếp theo

Final giữ tham chiếu field không bị gán lại và có vai trò trong việc khởi tạo đúng. Nó không biến đối tượng map được tham chiếu thành bất biến.

Đặt một tham chiếu volatile tới map có thể phục vụ việc công bố hoặc thay cả tham chiếu. Nhưng nếu sau đó nhiều luồng sửa trực tiếp cùng đối tượng LinkedHashMap mà không phối hợp, volatile trên tham chiếu không tự bảo vệ các bucket và liên kết bên trong.

Một thiết kế thay toàn bộ ảnh chụp bất biến là mô hình khác, có thể được phân tích riêng. Không nhầm nó với việc giữ một mutable map rồi chỉ thêm từ khóa volatile.

### 4.3. Công bố cache cho luồng khác cũng cần đúng cách

Khởi tạo cache hoàn chỉnh trước khi chia sẻ và không để this thoát khỏi constructor.

Các ví dụ dùng ExecutorService để gửi công việc sau khi tạo cache. Hợp đồng của công cụ phối hợp cung cấp quan hệ bộ nhớ cần thiết; không dùng một biến dùng chung tùy tiện rồi hy vọng luồng khác nhìn thấy đối tượng đầy đủ.

Khóa đúng trong phương thức và cách chia sẻ đối tượng đúng là hai phần bổ sung cho nhau.

## 5. Collections.synchronizedMap: hữu ích nhưng không tự tạo giao dịch cho mọi đoạn mã

Có thể bọc map:

```java
Map<String, String> cache = Collections.synchronizedMap(
        new LinkedHashMap<>(16, 0.75f, true));
```

Đây là đoạn khai báo minh họa với các import phù hợp.

Theo [Collections.synchronizedMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)), mọi truy cập vào map nền phải đi qua đối tượng được bọc để giữ quy tắc truy cập tuần tự.

Không giữ map nền rồi vừa gọi nó trực tiếp ở nơi này, vừa dùng wrapper ở nơi khác. Hai đường đi đó phá hợp đồng bảo vệ.

### 5.1. Hai lời gọi được khóa riêng vẫn có khoảng trống ở giữa

Đoạn logic “get; nếu thiếu thì tải; put” có ít nhất ba phần. Wrapper không tự mở rộng monitor của một lời gọi get tới tận lời gọi put được viết ở một dòng khác.

Lịch xen kẽ có thể là:

| Bước | Luồng T1 | Luồng T2 |
| --- | --- | --- |
| 1 | Get k: chưa có | |
| 2 | | Get k: chưa có |
| 3 | Tải dữ liệu cho k | |
| 4 | | Cũng tải dữ liệu cho k |
| 5 | Put kết quả | |
| 6 | | Put kết quả lần nữa |

Từng get/put có thể đã được bảo vệ đúng. Vấn đề ở đây là **chuỗi thao tác logic chưa nguyên tử**, nên hai lần tải vẫn xảy ra.

### 5.2. Không đánh đồng mọi API với chuỗi get/put tự viết

Ví dụ này không có nghĩa computeIfAbsent của wrapper được cài như một chuỗi get/put không khóa chung.

Trong [Collections.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Collections.java), SynchronizedMap giữ mutex khi gọi computeIfAbsent của map nền. Như vậy hàm tính cũng có thể chạy trong khóa chung.

Đó là một đường thao tác khác, và vẫn có đánh đổi về việc hàm tính chậm giữ khóa. Phải kiểm tra hợp đồng và cài đặt tương ứng, không suy từ một thí nghiệm get/put sang mọi phương thức của Map.

### 5.3. Duyệt cần bảo vệ toàn lượt

Khi dùng Iterator, Spliterator hoặc Stream trên view của synchronizedMap, tài liệu yêu cầu tự synchronized trên **map được bọc**, bao trùm lượt duyệt.

Khóa trên keySet là một monitor khác; nó không thay việc khóa đúng map.

Có thể chụp dữ liệu cần dùng trong một đoạn bảo vệ ngắn rồi xử lý bản chụp ở ngoài. Nếu chụp các entry, cần tránh giữ entry sống của map rồi tưởng đó là bản sao bất biến; bản sao khóa/giá trị cũng chưa tự sao chép sâu đối tượng bên trong.

Ngay cả khi đã khóa đúng, một vòng duyệt keySet rồi tự gọi get trên map access-order vẫn có thể tự thay liên kết trong cùng luồng. Khóa ngăn luồng khác chen vào, không ngăn chính đoạn mã trong khóa sửa thứ tự. Để chỉ đọc các cặp, dùng entrySet và lấy giá trị từ entry.

## 6. Ví dụ Java 17: map đã đồng bộ nhưng vẫn tải trùng

Chương trình sau cố ý tạo hai cache miss trước khi cho hai yêu cầu tiếp tục tải. CountDownLatch điều khiển lịch này; không dùng sleep để cầu may xuất hiện lỗi.

Cache trong ví dụ được bọc synchronizedMap. Đây là minh họa lỗi phối hợp tải, không phải cố chạy đua trên một LinkedHashMap trần.

Lưu thành **DuplicateLoadDemo.java**:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DuplicateLoadDemo {
    public static void main(String[] args) throws Exception {
        Map<String, String> cache = Collections.synchronizedMap(
                new LinkedHashMap<>(16, 0.75f, true));
        CountDownLatch bothMissed = new CountDownLatch(2);
        AtomicInteger loads = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<String> request = () -> {
            String value = cache.get("k");
            if (value == null) {
                bothMissed.countDown();
                if (!bothMissed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("second miss did not arrive");
                }
                loads.incrementAndGet();
                value = "value-k";
                cache.put("k", value);
            }
            return value;
        };

        try {
            Future<String> first = pool.submit(request);
            Future<String> second = pool.submit(request);
            boolean sameResult = first.get(10, TimeUnit.SECONDS)
                    .equals(second.get(10, TimeUnit.SECONDS));
            System.out.println("same result: " + sameResult);
            System.out.println("loader calls: " + loads.get());
            System.out.println("cache size: " + cache.size());
            System.out.println("cached value: " + cache.get("k"));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DuplicateLoadDemo.java
java DuplicateLoadDemo
```

Stdout:

```text
same result: true
loader calls: 2
cache size: 1
cached value: value-k
```

Hai chương trình chính trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ biên dịch chọn mức API/bytecode đích; JVM thực thi vẫn là phiên bản 24.0.2.

### 6.1. Vì sao size bằng 1 nhưng tải hai lần?

Hai luồng cùng dùng khóa k, nên cuối cùng chỉ có một ánh xạ. Tuy nhiên cả hai đã thấy thiếu trước khi một bên put, nên cả hai đều chạy phần tải.

Kết quả dữ liệu giống nhau không chứng minh cách phối hợp hiệu quả hay đúng với một hàm tải có tác dụng phụ. Nếu tải là một thao tác tốn tài nguyên, hai lần tải vẫn là hai công việc.

### 6.2. Latch đang chứng minh điều gì?

BothMissed chỉ về 0 khi cả hai yêu cầu đã đi qua nhánh thiếu. Sau đó mới cho chúng tải và put. Vì vậy kết quả tải trùng được tái hiện có chủ đích.

Các thời hạn await/get giúp chương trình thất bại rõ nếu thí nghiệm không tiến triển, thay vì treo vô hạn. Chúng là thời hạn của bộ kiểm tra, không phải chính sách timeout của cache.

Không bê nguyên barrier này vào một vùng khóa chung: nếu một luồng giữ khóa rồi đợi luồng kia vào cùng vùng khóa để đếm latch, có thể tự tạo bế tắc.

## 7. Một cache nhỏ có khóa chung và hợp đồng rõ ràng

Ví dụ tiếp theo dùng một lớp bao ngoài, không trả map nền hoặc view sống cho bên ngoài.

Hợp đồng minh họa:

- Số entry tối đa phải dương.
- Không chấp nhận khóa null hoặc giá trị null.
- Mọi thao tác lên map và thứ tự truy cập dùng chung một monitor private.
- Thêm và loại mục được thực hiện trong cùng vùng bảo vệ.
- GetOrLoad giữ khóa từ kiểm tra thiếu tới khi tải, ghi và loại mục xong.
- Hàm tải phải ngắn, không gọi lại cache và không tạo chuỗi chờ khóa bên ngoài.
- Khóa có định danh ổn định; các hàm hashCode/equals không tự sửa cache.
- Giá trị nên là dữ liệu bất biến hoặc được bảo vệ bằng hợp đồng riêng.

Đây là thiết kế cố ý đơn giản để có thể chỉ ra ranh giới bảo vệ. Nó dành cho khối lượng nhỏ và hàm tải phù hợp với việc chạy trong khóa; không phải một cache tải I/O có khả năng phục vụ cao.

### 7.1. Những bất biến cần giữ

Sau khi một phương thức công khai hoàn thành bình thường:

1. Map có không quá maximumSize entry.
2. Các entry còn lại tuân thứ tự truy cập do những thao tác đã được tuần tự hóa tạo ra.
3. Không có entry với giá trị null.
4. Bên ngoài không giữ iterator hoặc view sống để vượt qua quy tắc khóa.

Trong lúc thêm rồi loại mục, size có thể tạm lớn hơn giới hạn ở bên trong vùng bảo vệ. Những thao tác cùng tuân khóa không quan sát phần chuyển tiếp ấy.

Giới hạn số entry không phải giới hạn byte của toàn ứng dụng. Đối tượng giá trị, yêu cầu đang chờ và tài nguyên tải cũng sử dụng bộ nhớ riêng.

## 8. Ví dụ Java 17: khóa trọn thao tác và loại mục LRU

Lưu thành **LockedLruDemo.java**:

```java
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

public class LockedLruDemo {
    static final class LockedLruCache<K, V> {
        private final Object lock = new Object();
        private final int maximumSize;
        private final LinkedHashMap<K, V> data =
                new LinkedHashMap<>(16, 0.75f, true);

        LockedLruCache(int maximumSize) {
            if (maximumSize <= 0) {
                throw new IllegalArgumentException("maximumSize must be positive");
            }
            this.maximumSize = maximumSize;
        }

        public V get(K key) {
            Objects.requireNonNull(key, "key");
            synchronized (lock) {
                return data.get(key);
            }
        }

        public void put(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            synchronized (lock) {
                data.put(key, value);
                trimToLimit();
            }
        }

        public V getOrLoad(K key, Function<? super K, ? extends V> loader) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(loader, "loader");
            synchronized (lock) {
                V current = data.get(key);
                if (current != null) {
                    return current;
                }
                V loaded = Objects.requireNonNull(loader.apply(key), "loaded value");
                data.put(key, loaded);
                trimToLimit();
                return loaded;
            }
        }

        public void invalidate(K key) {
            Objects.requireNonNull(key, "key");
            synchronized (lock) {
                data.remove(key);
            }
        }

        public int size() {
            synchronized (lock) {
                return data.size();
            }
        }

        public List<K> keysSnapshot() {
            synchronized (lock) {
                return List.copyOf(data.keySet());
            }
        }

        private void trimToLimit() {
            while (data.size() > maximumSize) {
                Iterator<K> iterator = data.keySet().iterator();
                iterator.next();
                iterator.remove();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        LockedLruCache<String, String> cache = new LockedLruCache<>(2);
        AtomicInteger loads = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<String> request = () -> {
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("start signal missing");
            }
            return cache.getOrLoad("k", key -> {
                loads.incrementAndGet();
                return "value-" + key;
            });
        };

        try {
            Future<String> first = pool.submit(request);
            Future<String> second = pool.submit(request);
            start.countDown();
            boolean sameResult = first.get(10, TimeUnit.SECONDS)
                    .equals(second.get(10, TimeUnit.SECONDS));
            System.out.println("same result: " + sameResult);
            System.out.println("loader calls: " + loads.get());

            cache.put("b", "value-b");
            System.out.println("get k: " + cache.get("k"));
            cache.put("c", "value-c");
            System.out.println("keys after eviction: " + cache.keysSnapshot());
            System.out.println("get evicted b: " + cache.get("b"));
            System.out.println("final size: " + cache.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LockedLruDemo.java
java LockedLruDemo
```

Stdout trên môi trường đã nêu:

```text
same result: true
loader calls: 1
get k: value-k
keys after eviction: [k, c]
get evicted b: null
final size: 2
```

### 8.1. Hai yêu cầu đồng thời cho cùng khóa

Hai tác vụ đều được phép bắt đầu sau tín hiệu start. Bên vào vùng bảo vệ trước thấy thiếu k, gọi hàm tải và lưu giá trị.

Bên còn lại chỉ vào được sau đó, đọc được giá trị vừa có và không gọi hàm tải. Vì vậy loader calls bằng 1 trong kịch bản này.

Không cần giả định tác vụ được submit trước phải thắng. Kết quả không phụ thuộc việc luồng nào lấy khóa trước vì chúng yêu cầu cùng khóa và cùng giá trị.

### 8.2. Kiểm tra chính sách loại mục

Sau phần tải, cache có k. Thêm b tạo dãy k,b. Get k ghi nhận dùng k gần đây, nên dãy thành b,k.

Thêm c vượt giới hạn 2. Iterator lấy khóa đầu là b và xóa qua chính iterator, còn k,c.

Get b trả null; size cuối là 2. Đây là một trường hợp LRU cụ thể, không phải dự đoán thứ tự tùy ý của các luồng chạy song song.

### 8.3. Vì sao không cần trả keySet?

KeysSnapshot tạo List.copyOf trong khi giữ khóa, nên bên gọi nhận một danh sách độc lập về cấu trúc, không sửa được dãy danh sách ấy.

Nó chỉ chụp các tham chiếu khóa. Đối tượng khóa vẫn cần ổn định; danh sách không tự biến một khóa có thể sửa thành bất biến.

Trong ví dụ, khóa và giá trị đều là String, giúp tránh thêm bài toán sửa đối tượng dùng chung.

### 8.4. Lỗi tải và null được xử lý thế nào?

Nếu hàm tải ném ngoại lệ hoặc trả null, phương thức không đi tới bước put. Khối synchronized vẫn tự mở khóa khi thoát do ngoại lệ.

Không có ánh xạ đánh dấu lỗi được giữ lại. Một yêu cầu sau có thể thử tải lại. Đây là chính sách của ví dụ, không phải quy tắc duy nhất đúng cho mọi cache.

Không cất null giúp get trả null có nghĩa rõ ràng là chưa có dữ liệu trong cache. Nếu bài toán cần phân biệt “chưa tải” và “đã biết không tồn tại”, có thể dùng một kiểu kết quả riêng và một chính sách giữ kết quả âm; đó là yêu cầu bổ sung.

### 8.5. Không hứa “mỗi khóa chỉ tải một lần mãi mãi”

Một ánh xạ có thể bị loại vì dung lượng, bị invalidate, hoặc chưa bao giờ được lưu do lỗi tải. Sau đó cùng khóa có thể cần tải lại.

Bảo đảm của ví dụ là không cho hai đường getOrLoad chạy chồng phần kiểm tra–tải–ghi trong cùng cache, dưới các điều kiện đã nêu. Nó không biến hàm tải thành thao tác chỉ xảy ra một lần trong suốt đời ứng dụng.

## 9. Ranh giới quan trọng: hàm tải chạy trong khóa chung

Thiết kế trên dễ lập luận về tính nguyên tử vì mọi thứ liên quan tới trạng thái map nằm trong một vùng loại trừ.

Đánh đổi nằm ở đoạn loader.apply: nó chạy khi monitor vẫn đang bị giữ.

### 9.1. Một khóa chậm có thể chặn những khóa khác

Nếu tải k gọi mạng mất vài giây, các get cho những khóa khác trong cùng cache cũng phải đợi monitor, dù dữ liệu của chúng đã có.

Các yêu cầu cùng khóa dùng chung kết quả trong kịch bản đơn giản, nhưng cả cache cũng bị tuần tự hóa quanh công việc ấy.

Đây là lý do ví dụ yêu cầu hàm tải ngắn và không chặn. Không thay bằng một truy vấn chậm rồi vẫn giữ nguyên kết luận về khả năng phục vụ.

### 9.2. Gọi mã bên ngoài khi giữ khóa có thể tạo chuỗi chờ

Hàm tải có thể lấy một khóa khác hoặc đợi một tác vụ khác. Nếu tác vụ kia lại cần cache đang bị giữ, hai bên có thể chờ nhau.

Monitor Java có tính tái nhập: cùng luồng có thể lấy lại monitor nó đang giữ. Điều đó không tự sửa đệ quy tải cùng khóa, chuỗi phụ thuộc qua cache khác hoặc chờ giữa các luồng.

Vì vậy hợp đồng ví dụ cấm hàm tải gọi lại cache. Đừng xem việc một lời gọi lại tình cờ chạy được là bằng chứng một thiết kế tái nhập bất kỳ đã đúng.

### 9.3. Thứ tự đồng thời được xác lập bởi vùng bảo vệ

Khi nhiều luồng cùng truy cập những khóa khác nhau, thứ tự thực tế phụ thuộc thứ tự chúng vào và thực hiện các thao tác được bảo vệ.

Không nhất thiết đó là thứ tự request đến từ bên ngoài hoặc thứ tự thời gian được ghi ở một hệ thống khác.

Muốn hứa một cách sắp thứ tự mạnh hơn, phải định nghĩa thêm quy tắc. Khóa chung tạo một lịch thực hiện có thể lập luận; nó không đọc được ý định thời gian của mọi người gọi.

### 9.4. Giữ đúng dữ liệu không đồng nghĩa có độ trễ tốt

Một thiết kế có thể an toàn về cấu trúc nhưng không đạt thông lượng hoặc độ trễ cần có.

Đo thời gian chờ khóa, thời gian tải, tỷ lệ trúng cache và số yêu cầu đồng thời. Không chỉ đo get ở một luồng rồi suy rằng bản có khóa sẽ mở rộng tốt khi tải tăng.

Các chương trình trong bài xác nhận những thuộc tính cụ thể; stdout không phải phép đo hiệu năng.

## 10. Đưa việc tải ra ngoài khóa: giảm chặn nhưng phát sinh giao thức mới

Một cải tiến dễ nghĩ tới:

1. Khóa, kiểm tra cache.
2. Mở khóa, tải dữ liệu.
3. Khóa lại, kiểm tra và ghi kết quả.
4. Cập nhật thứ tự và loại mục nếu cần.

Cách này có thể giảm thời gian giữ khóa chung. Nhưng nó không tự giữ nguyên toàn bộ ý nghĩa của getOrLoad trong ví dụ trước.

### 10.1. Hai lần tải vẫn có thể xảy ra

Hai luồng có thể cùng vượt qua bước kiểm tra đầu và cùng tải. Kiểm tra lại khi ghi giúp chọn giá trị đã có thay vì ghi đè mù, nhưng không thu hồi được công tải trùng đã thực hiện.

Nếu hàm tải có tác dụng phụ, phải xét tác dụng ấy riêng. Việc chỉ một kết quả được giữ trong map không có nghĩa chỉ một lần tải đã chạy.

### 10.2. Có thể ghi lại dữ liệu sau invalidate

Lịch minh họa:

```text
T1: thấy k thiếu, bắt đầu tải dữ liệu cũ
T2: invalidate k vì dữ liệu nguồn vừa thay đổi
T1: tải xong, put kết quả cũ vào cache
```

Nếu invalidate chỉ xóa entry hiện có, bước ghi muộn của T1 có thể đưa dữ liệu trở lại.

Cần định nghĩa invalidate muốn bảo đảm điều gì: chỉ xóa trạng thái đang lưu, hay còn ngăn một lượt tải đã bắt đầu trước đó được công bố sau này?

Nếu cần yêu cầu thứ hai, thiết kế có thể phải dùng phiên bản hoặc mã thế hệ của khóa/lượt tải. Khi ghi, kết quả chỉ được nhận nếu còn khớp thế hệ hiện hành. Đây là một giao thức bổ sung, không có sẵn chỉ nhờ putIfAbsent.

### 10.3. Kết quả nào thắng khi dữ liệu nguồn đổi?

Nếu hai lượt tải trả hai phiên bản khác nhau, “bên ghi cuối thắng” không tự đồng nghĩa “dữ liệu mới nhất thắng”.

Cần một tiêu chí về phiên bản dữ liệu hoặc thứ tự chấp nhận kết quả. Đồng hồ hoàn thành của hai tác vụ không đủ để suy ra độ mới của dữ liệu nguồn.

### 10.4. Giảm thời gian khóa không được chia rời bất biến

Phần cập nhật map, lịch sử truy cập và chính sách loại mục vẫn cần phối hợp.

Nếu chuyển sang ConcurrentHashMap và một hàng đợi riêng để ghi lịch sử, ta có hai cấu trúc phải thống nhất. Xóa ở cấu trúc này mà không xử lý trạng thái tương ứng ở cấu trúc kia có thể tạo phần tử lịch sử cũ hoặc loại nhầm.

Một thuật toán LRU gần đúng có thể chấp nhận những khác biệt được định nghĩa rõ. Nhưng không được tự nhận LRU chính xác hoặc giới hạn cứng khi chưa có cơ chế bảo đảm chúng.

## 11. Dùng chung một lượt tải cho cùng khóa không chỉ là thêm Future

Có thể muốn mỗi khóa đang tải có một CompletableFuture để những yêu cầu khác chờ cùng kết quả. Ý tưởng này thường được gọi là phối hợp một lượt tải cho cùng khóa, hoặc single-flight.

Để thành thiết kế đúng, cần trả lời thêm:

| Sự kiện | Câu hỏi của giao thức |
| --- | --- |
| Chưa có dữ liệu, chưa có lượt tải | Ai được quyền đăng ký lượt tải? |
| Đã có lượt tải | Yêu cầu sau dùng chung kết quả bằng cách nào? |
| Tải thành công | Khi nào công bố giá trị và bỏ dấu đang tải? |
| Tải thất bại | Có giữ lỗi không, khi nào cho thử lại? |
| Một bên chờ hết hạn | Chỉ bỏ chờ hay hủy công việc chung? |
| Invalidate trong lúc tải | Kết quả đang chạy còn được phép ghi không? |
| Lượt tải cũ hoàn tất sau lượt mới | Làm sao tránh xóa hoặc ghi nhầm trạng thái mới? |
| Có quá nhiều khóa đang tải | Giới hạn số công việc và tài nguyên ở đâu? |

Một yêu cầu timeout không nhất thiết được quyền hủy lượt tải mà những bên khác còn đang chờ. Hủy một Future cũng không tự bảo đảm mọi I/O bên dưới đã dừng.

Việc dọn trạng thái đang tải phải gắn với đúng lượt tải. Một lượt cũ hoàn tất không nên xóa nhầm đăng ký của lượt mới hơn cho cùng khóa.

Giới hạn số entry đã lưu cũng không tự giới hạn số Future, tác vụ, kết nối hoặc dữ liệu trung gian của những khóa đang tải.

Các câu hỏi này giải thích vì sao một cache tải dữ liệu đồng thời có thể phức tạp hơn nhiều so với một Map cộng vài dòng synchronized. Đây là yêu cầu thiết kế; bài không đưa một mảnh Future chưa có đủ giao thức rồi gọi đó là bản triển khai hoàn chỉnh.

## 12. ConcurrentHashMap giải quyết phần nào?

ConcurrentHashMap cung cấp cấu trúc map dùng chung cùng những thao tác nguyên tử theo hợp đồng của lớp.

Theo [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function)), computeIfAbsent thực hiện lời gọi một cách nguyên tử; hàm tính cần ngắn, đơn giản và không sửa map trong lúc tính.

### 12.1. Có thể thay thế một chuỗi kiểm tra–ghi riêng lẻ

Với bài toán chỉ cần ánh xạ đồng thời và tính giá trị phù hợp với hợp đồng đó, API nguyên tử giúp tránh tự ghép get rồi put không có sự phối hợp.

Nhưng không hứa hàm được gọi một lần mãi mãi cho mỗi khóa. Nếu không lưu được giá trị, có lỗi hoặc ánh xạ bị xóa, các lần gọi sau có thể tính lại.

Cũng không diễn giải rằng mọi cập nhật cho mọi khóa khác luôn hoàn toàn không bị ảnh hưởng trong khi một hàm tính đang chạy. Tài liệu có nêu khả năng một số cập nhật phải chờ.

### 12.2. Nó không tự có thứ tự LRU hoặc trần dung lượng

ConcurrentHashMap không cung cấp chuỗi access-order như LinkedHashMap và không tự loại entry theo LRU.

Ghép size(), put() và một lần xóa ở các dòng riêng không tạo một phép giữ giới hạn nguyên tử. Dưới thay đổi đồng thời, các quan sát tổng hợp cũng không nên bị hiểu như một giao dịch toàn map.

Nếu bổ sung hàng đợi thứ tự hoặc bộ đếm riêng, phải phân tích giao thức chung. Đổi tên loại Map không tự hoàn thành phần chính sách của cache.

### 12.3. Khi cần nhiều khả năng cache

Nếu cần phối hợp tải, giới hạn theo kích thước/trọng số, hết hạn hoặc API bất đồng bộ với nhiều người dùng, có thể đánh giá một thư viện cache được duy trì và có hợp đồng phù hợp.

Ví dụ, tài liệu chính thức của Caffeine trình bày riêng [cách nạp dữ liệu](https://github.com/ben-manes/caffeine/wiki/Population) và [chính sách loại/hết hạn](https://github.com/ben-manes/caffeine/wiki/Eviction). Những tính năng ấy cần được chọn và cấu hình theo yêu cầu, không suy ra mọi cache đều có cùng bảo đảm.

Ngay cả khi dùng thư viện, đối tượng giá trị, tính đúng của hàm tải và độ mới của nguồn dữ liệu vẫn thuộc hợp đồng của ứng dụng.

## 13. Giá trị trả ra ngoài vẫn có thể bị sửa không an toàn

Khóa của cache bảo vệ cấu trúc và thao tác của cache. Khi get đã trả về một đối tượng, bên gọi có thể giữ và dùng đối tượng ấy sau khi khóa được mở.

Nếu giá trị là ArrayList và hai luồng cùng thêm phần tử vào nó, monitor của cache không tự bao quanh những lần thêm ở bên ngoài.

Một số lựa chọn thiết kế:

- Dùng giá trị bất biến, được tạo hoàn chỉnh trước khi lưu.
- Sao chép dữ liệu phù hợp khi nhận vào hoặc trả ra.
- Dùng một đối tượng giá trị có cơ chế an toàn riêng.
- Định nghĩa quyền sở hữu để một bên chịu trách nhiệm sửa.

Bản sao cấu trúc Map hoặc List không tự sao chép sâu giá trị. Một bản chụp không sửa được cũng có thể chứa tham chiếu tới đối tượng còn sửa được.

Tương tự, invalidate chỉ làm cache bỏ ánh xạ theo hợp đồng của nó. Nó không thu hồi mọi tham chiếu mà người gọi đã nhận trước đó.

## 14. Kiểm thử đa luồng cần chứng minh thuộc tính cụ thể

### 14.1. Dùng cơ chế phối hợp thay vì sleep để đoán lịch

Ví dụ đầu dùng CountDownLatch để buộc hai bên đều thấy thiếu trước khi tải. Đây là một lịch cụ thể mà thuật toán cho phép, đủ để bác bỏ lời khẳng định “chắc chỉ tải một lần”.

Tham khảo hợp đồng [CountDownLatch Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html) và [ExecutorService Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) khi xây những kiểm tra có chờ và chia sẻ dữ liệu.

Thread.sleep không bảo đảm luồng kia đã đi tới đúng bước, và có thể làm bài kiểm tra vừa chậm vừa khó tái hiện.

### 14.2. Kiểm tra dữ liệu, giới hạn và vòng đời riêng

Với cache có khóa chung, những kiểm tra hữu ích gồm:

- Nhiều thao tác đồng thời không làm sai cặp khóa–giá trị còn tồn tại.
- Mọi quan sát qua API công khai tuân giới hạn số entry đã hứa.
- Truy cập một khóa rồi thêm khóa khác loại đúng mục trong kịch bản tuần tự có kiểm soát.
- Hai yêu cầu cùng khóa chia sẻ kết quả trong kịch bản không có invalidate/loại mục xen giữa.
- Hàm tải lỗi không để lại một trạng thái mắc kẹt.
- Lần thử lại có thể tiến triển theo chính sách đã chọn.
- Bản chụp không phải view sống và không mở đường sửa map nền.
- Invalidate đang tải được kiểm tra theo đúng nghĩa đã công bố, nếu thiết kế có tải ngoài khóa.

Không kiểm tra một thứ tự toàn cục cố định giữa những luồng vốn được phép cạnh tranh khóa theo nhiều lịch khác nhau.

### 14.3. Chạy nhiều lần không thay chứng minh về vùng bảo vệ

Kiểm thử với nhiều luồng có thể phát hiện lỗi, nhưng không quan sát thấy lỗi trong vài nghìn vòng không chứng minh mọi lịch đều đúng.

Cần đọc mã để xác định mọi đường chạm trạng thái, vùng bảo vệ, điểm công bố kết quả và các giả định về mã gọi lại.

Hai lớp bằng chứng bổ sung nhau: một lịch tái hiện được cho lỗi cụ thể, và một lập luận về bất biến cho mọi đường mà lớp cho phép.

## 15. Những giới hạn nên viết vào hợp đồng của cache tự viết

| Yêu cầu | Cần mô tả rõ |
| --- | --- |
| Dung lượng | Đếm entry hay trọng số/byte; giới hạn cứng ở đâu hay được phép lệch tạm |
| LRU | Chính xác theo thao tác đã tuần tự hóa hay gần đúng |
| Null | Được lưu không; phân biệt thiếu và kết quả âm ra sao |
| Tải | Chạy trong khóa hay ngoài; có chia sẻ lượt tải không |
| Lỗi | Giữ lỗi, thử lại ngay hay có trì hoãn; ngoại lệ được chuyển cho ai |
| Invalidate | Chỉ xóa ánh xạ hay còn vô hiệu hóa kết quả đang tải |
| Giá trị | Bất biến, sao chép hay được sửa theo một cơ chế riêng |
| Duyệt | View sống, bản chụp hay cần người gọi giữ khóa |
| Nhiều luồng | Monitor/quy tắc nào bao trùm mọi truy cập |
| Tài nguyên | Giới hạn công việc đang tải, bên chờ và thời gian chờ |

Không nhất thiết một cache học tập phải đáp ứng mọi yêu cầu nâng cao. Nó cần nói đúng những gì mình đáp ứng và giữ các bất biến đó trong mã.

Nếu ứng dụng thật cần những điều vượt khỏi phạm vi ấy, nên đổi thiết kế hoặc dùng thành phần phù hợp trước khi dựa vào các bảo đảm chưa có.

## 16. Lỗi phổ biến và cách sửa

| Lỗi suy luận | Cách sửa |
| --- | --- |
| Chỉ get nên LinkedHashMap access-order không có ghi | Get trúng entry có thể sửa liên kết; phối hợp cả đường này |
| Bọc synchronizedMap là mọi đoạn get–load–put đã nguyên tử | Xác định ranh giới thao tác logic, không chỉ từng phương thức |
| Khóa trên keySet cũng như khóa wrapper | Duyệt theo monitor được tài liệu yêu cầu |
| Đã khóa thì keySet cộng get luôn an toàn với iterator | Cùng luồng vẫn có thể đổi thứ tự; đọc trực tiếp qua entry |
| Volatile map làm mọi nội dung map an toàn | Phân biệt công bố tham chiếu và sửa cấu trúc bên trong |
| Hai tác vụ trả cùng dữ liệu nghĩa là chỉ tải một lần | Đếm và phối hợp lượt tải, không chỉ nhìn giá trị cuối |
| ComputeIfAbsent có nghĩa đúng một lần suốt đời khóa | Xét xóa, lỗi, kết quả không lưu và phạm vi bảo đảm cụ thể |
| Tải trong khóa an toàn nên hiệu năng chắc tốt | Xét thời gian chờ và việc chặn những khóa khác |
| Chuyển tải ra ngoài khóa không đổi ý nghĩa invalidate | Phân tích lượt tải đang chạy và quyền công bố kết quả |
| Dùng ConcurrentHashMap là tự có LRU và giới hạn | Chính sách thứ tự/dung lượng vẫn cần thiết kế |
| Cache an toàn thì giá trị mutable cũng an toàn | Giá trị cần hợp đồng riêng sau khi trả ra |
| Không gặp ConcurrentModificationException chứng minh đúng | Fail-fast không thay vùng bảo vệ và lập luận đa luồng |

## 17. Bài tập tự kiểm tra có lời giải

### Bài 1: Hai luồng chỉ đọc

Map access-order đã có nhiều mục. Hai luồng chỉ gọi get. Có thể bỏ đồng bộ vì không gọi put không?

**Lời giải:** không. Get trúng entry có thể đổi liên kết thứ tự; phải phối hợp những truy cập ấy.

### Bài 2: Hai lần miss

Từng get/put đã được synchronizedMap bảo vệ. Hai luồng cùng tải k rồi cuối cùng size bằng 1. Có mâu thuẫn không?

**Lời giải:** không. Từng phương thức được bảo vệ nhưng cả chuỗi kiểm tra–tải–ghi không tự nguyên tử. Hai lượt tải có thể cùng tạo một khóa cuối.

### Bài 3: Duyệt có khóa

Một luồng synchronized trên wrapper rồi duyệt keySet và get từng khóa. Khóa có ngăn chính vòng ấy đổi thứ tự không?

**Lời giải:** không. Monitor ngăn những luồng tuân khóa khác chen vào, nhưng cùng luồng vẫn gọi get làm đổi dãy. Nếu chỉ cần dữ liệu, duyệt entrySet và lấy value từ entry.

### Bài 4: Loader chậm

Cache có một khóa chung và chạy loader trong khóa. Khi tải a bị chậm, một get b đang có sẵn có phải chờ không?

**Lời giải:** có thể phải chờ cùng monitor. An toàn cấu trúc không tự tạo khả năng phục vụ song song.

### Bài 5: Invalidate khi tải ngoài khóa

T1 bắt đầu tải k, T2 invalidate k, rồi T1 lưu kết quả. Nếu yêu cầu là không cho kết quả cũ quay lại sau invalidate, chỉ remove k có đủ không?

**Lời giải:** không. Cần giao thức cho lượt tải đang chạy, chẳng hạn kiểm tra thế hệ/phiên bản trước khi chấp nhận kết quả.

### Bài 6: Giá trị là danh sách

Cache khóa mọi get/put nhưng trả cùng ArrayList cho nhiều luồng. Những lần add bên ngoài có tự nằm trong khóa cache không?

**Lời giải:** không. Phải dùng giá trị bất biến, sao chép, cấu trúc giá trị an toàn hoặc hợp đồng sở hữu thích hợp.

### Bài 7: Giới hạn số mục và công việc đang chạy

Cache chỉ giữ tối đa 100 entry nhưng cho tải đồng thời hàng nghìn khóa. Có chắc toàn bộ tài nguyên bị giới hạn theo 100 không?

**Lời giải:** không. Công việc, Future, kết nối và dữ liệu trung gian có vòng đời khác với entry đã lưu.

### Bài 8: Chọn bằng chứng kiểm thử

Một bài kiểm tra chạy nhiều luồng một lần và không lỗi. Có đủ để tuyên bố lớp đúng với mọi lịch không?

**Lời giải:** không. Cần kiểm thử có thuộc tính rõ ràng và phân tích mọi đường truy cập, vùng bảo vệ cùng bất biến của lớp.

## 18. Tài liệu đối chiếu

- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): access-order, thay đổi cấu trúc và yêu cầu đồng bộ.
- [Collections.synchronizedMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)): truy cập qua wrapper và bảo vệ lượt duyệt.
- [Collections.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Collections.java): đường khóa các phương thức của SynchronizedMap.
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitor, quan hệ happens-before và tranh chấp dữ liệu.
- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thao tác nguyên tử và giới hạn hàm tính lại.
- [Caffeine — Population](https://github.com/ben-manes/caffeine/wiki/Population), [Caffeine — Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction): đối chiếu trách nhiệm nạp dữ liệu và chính sách cache.

Một cache tự viết có thể đúng trong một phạm vi nhỏ được xác định rõ. Điều làm nó an toàn là mọi đường truy cập cùng tuân giao thức, còn điều làm nó phù hợp với ứng dụng là những bảo đảm ấy khớp với yêu cầu về tải, vòng đời dữ liệu và khả năng phục vụ.
