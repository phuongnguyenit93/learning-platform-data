# So sánh LRU đơn giản với yêu cầu của bộ nhớ đệm thực tế

## 1. Bài toán và mục tiêu

Một ứng dụng thường đọc đi đọc lại cùng dữ liệu: cấu hình, danh mục sản phẩm, kết quả tính toán hoặc thông tin tra cứu từ cơ sở dữ liệu. Đặt kết quả gần nơi sử dụng giúp giảm độ trễ và số lần gọi nguồn dữ liệu. Nhưng RAM hữu hạn: khi cache đầy, phải quyết định giữ mục nào và loại mục nào.

**LRU (Least Recently Used)** là một chính sách loại bỏ: khi cần chỗ, bỏ phần tử ít được truy cập gần đây nhất. LRU đơn giản rất hữu ích để luyện Java Collections và hiểu chính sách eviction, nhưng **một bộ nhớ đệm thực tế là cả hệ thống quản lý dữ liệu tạm**, còn phải xử lý thời hạn dữ liệu, tải đồng thời, giới hạn RAM, lỗi nguồn và quan sát vận hành.

Sau bài này, người học cần có thể:
- Cài một LRU theo số mục bằng Java Collections, dự đoán đúng thứ tự sau thao tác đọc/ghi.
- Phân biệt **eviction** (loại bỏ để lấy chỗ), **expiration** (hết hạn theo thời gian) và **invalidation** (chủ động làm dữ liệu cũ mất hiệu lực).
- Chỉ ra nơi LRU tối giản sẽ thất bại khi triển khai thật và lựa chọn biện pháp phù hợp với yêu cầu.
- Thiết kế phép đo và ca kiểm thử trước khi chuyển từ ví dụ học thuật sang hệ thống có tải.

### Tình huống xuyên suốt

Giả sử dịch vụ sản phẩm đọc bản ghi từ database, giữ tối đa ba sản phẩm trong một cache ở bộ nhớ tiến trình. Nếu mỗi truy vấn đều có kích thước tương tự nhau, không có cập nhật và chỉ một luồng sử dụng cache, LRU theo số mục là điểm khởi đầu hợp lý. Bây giờ thêm các yêu cầu: giá sản phẩm thay đổi, truy vấn đồng thời tăng mạnh, payload lớn nhỏ khác nhau và dịch vụ có nhiều instance. Từng yêu cầu đó làm lộ ra một giới hạn của LRU cơ bản.

## 2. LRU hoạt động như thế nào?

Với capacity = 3, giả sử thứ tự từ **ít dùng gần đây nhất → mới dùng gần đây nhất**:

| Thao tác | Thứ tự sau thao tác | Diễn giải |
| --- | --- | --- |
| put(A), put(B), put(C) | A → B → C | A là mục cũ nhất. |
| get(A) | B → C → A | Đọc trúng A khiến A trở thành mục mới dùng. |
| put(D) | C → A → D | Cache đầy, loại B rồi đưa D vào. |
| get(B) | C → A → D | B không còn trong cache: cache miss. |
| put(A, giá trị mới) | C → D → A | Cập nhật A cũng tính là một lần truy cập trong LinkedHashMap access-order. |

Cần phân biệt:
- **Hit**: khóa tồn tại và giá trị đáp ứng điều kiện hợp lệ của cache; không phải gọi nguồn dữ liệu.
- **Miss**: không có giá trị dùng được; thường phải tải từ nguồn.
- **Eviction**: loại bỏ mục theo chính sách dung lượng. Trong ví dụ là mục lâu chưa được dùng.
- **Expiration**: mục quá hạn theo chính sách thời gian, dù có thể chưa từng bị eviction.
- **Invalidation**: xóa hoặc làm mất hiệu lực mục do sự kiện cập nhật, xóa, đổi quyền hoặc yêu cầu nghiệp vụ.

LRU không biết giá trị còn đúng về nghiệp vụ hay không. Một mục được đọc liên tục có thể luôn ở cuối danh sách LRU mà vẫn chứa giá cũ.

### LRU khác các lựa chọn nào?

| Cơ chế | Căn cứ quyết định | Dùng khi nào | Giới hạn đáng nhớ |
| --- | --- | --- | --- |
| FIFO | Thời điểm đưa vào | Muốn cách đơn giản, không ưu tiên truy cập lại | Có thể loại mục vừa được đọc nhiều lần. |
| LRU | Lần truy cập gần nhất | Tập truy cập có tính cục bộ theo thời gian | Một đợt quét tuần tự có thể đẩy dữ liệu nóng ra ngoài. |
| LFU | Tần suất truy cập | Dữ liệu có độ phổ biến ổn định | Phải quản lý bộ đếm, tránh dữ liệu từng rất nóng chiếm chỗ mãi. |
| TTL / expire-after-write | Thời gian từ lúc ghi | Muốn giới hạn tuổi dữ liệu | Không tự đảm bảo giới hạn số mục hoặc số byte. |
| Expire-after-access / TTI | Thời gian từ lần truy cập | Muốn bỏ mục lâu không dùng | Dữ liệu có thể cũ mãi nếu cứ được truy cập. |
| Invalidate theo sự kiện | Biến đổi dữ liệu/nghiệp vụ | Cần làm mới ngay khi có thay đổi đã biết | Cần luồng sự kiện tin cậy và xử lý sự kiện thất lạc. |

TTL, giới hạn kích thước và chính sách eviction có thể **kết hợp** với nhau. Chúng giải những vấn đề khác nhau.

## 3. Cài LRU đơn giản bằng Java 17+

Java cung cấp **LinkedHashMap**. Constructor với tham số accessOrder = true giữ thứ tự theo lần truy cập thay vì theo thứ tự chèn. Ghi đè removeEldestEntry cho phép tự động loại mục đứng đầu khi chèn xong và vượt capacity.

Tạo tệp **LruComparisonDemo.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class LruComparisonDemo {

    static final class LruCache<K, V> {
        private final int capacity;
        private final LinkedHashMap<K, V> entries;

        LruCache(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
            this.entries = new LinkedHashMap<K, V>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                    return size() > LruCache.this.capacity;
                }
            };
        }

        synchronized V get(K key) {
            return entries.get(Objects.requireNonNull(key, "key"));
        }

        synchronized void put(K key, V value) {
            entries.put(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value")
            );
        }

        synchronized List<K> keysOldestFirst() {
            return new ArrayList<>(entries.keySet());
        }

        synchronized int size() {
            return entries.size();
        }
    }

    public static void main(String[] args) {
        LruCache<String, Integer> cache = new LruCache<>(3);

        cache.put("A", 10);
        cache.put("B", 20);
        cache.put("C", 30);
        System.out.println("Ban dau : " + cache.keysOldestFirst());

        System.out.println("get(A)  : " + cache.get("A"));
        System.out.println("Sau doc : " + cache.keysOldestFirst());

        cache.put("D", 40);
        System.out.println("Sau D   : " + cache.keysOldestFirst());
        System.out.println("get(B)  : " + cache.get("B"));

        cache.put("A", 100);
        System.out.println("Sua A   : " + cache.keysOldestFirst());
        System.out.println("Kich thuoc: " + cache.size());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac LruComparisonDemo.java
java LruComparisonDemo
```

Kết quả chuẩn:

```text
Ban dau : [A, B, C]
get(A)  : 10
Sau doc : [B, C, A]
Sau D   : [C, A, D]
get(B)  : null
Sua A   : [C, D, A]
Kich thuoc: 3
```

**Giải thích các chi tiết dễ nhầm:**
1. Map được cấu hình access-order, nên **get thành công thay đổi thứ tự**. Trong LinkedHashMap access-order, cả cập nhật put cho khóa đang tồn tại cũng làm mới vị trí của mục.
2. removeEldestEntry được xét sau khi chèn một mục mới. Khi kích thước vượt capacity, mục đầu danh sách bị loại. Điều kiện phải là size() > capacity, không phải >= capacity, nếu không sẽ không giữ đủ ba mục.
3. Ví dụ dùng synchronized cho mọi thao tác trên map, kể cả get và tạo ảnh chụp thứ tự. Điều này tránh truy cập cấu trúc access-order đồng thời không an toàn, nhưng một khóa toàn cục có thể làm giảm thông lượng.
4. Demo cố tình từ chối key/value null. Kết quả get(B) = null được hiểu là miss; nếu cho phép giá trị null, phải dùng containsKey hoặc kiểu kết quả rõ ràng để phân biệt miss với giá trị null.
5. keysOldestFirst tạo bản sao trong lúc khóa đang giữ; trả trực tiếp tập keySet ra ngoài sẽ khiến người gọi duyệt trên một cấu trúc có thể biến đổi sau khi phương thức kết thúc.
6. Thao tác đọc/ghi map trung bình gần O(1), song điều đó **không** bao gồm chi phí lấy dữ liệu, cấp phát đối tượng, tranh chấp khóa hoặc thu gom rác của cả dịch vụ.

Đây là một **cache LRU theo số entry, trong một JVM**. Nó chưa có loader, TTL, cân theo byte, metrics hoặc đồng bộ liên tiến trình. Khóa synchronized giúp an toàn cho các phương thức hiện có trong lớp, không bảo đảm một chuỗi thao tác nhiều bước ở phía gọi trở thành nguyên tử.

## 4. Tại sao LRU chạy đúng vẫn chưa đủ cho production?

### 4.1. Giới hạn theo số mục không phải giới hạn dung lượng RAM

Ba entry có thể lần lượt giữ 1 KB, 3 KB và 200 MB. Giữ tối đa ba key không giới hạn chắc chắn heap dùng cho các value, object header, index, string hay bản sao của payload. Với dữ liệu lớn hoặc biến thiên mạnh, hãy đặt **maximum weight** dựa trên chi phí ước tính của từng mục; thêm giới hạn thời gian và giới hạn tổng tài nguyên theo bối cảnh.

Weight là con số mô hình hóa (ví dụ kích thước byte của payload); nó không tự phản ánh chính xác mọi overhead JVM. Cần đo heap thực tế, tần suất GC và điều chỉnh ngưỡng qua vận hành. Đừng lấy sức chứa của ví dụ nhỏ làm cấu hình hệ thống.

### 4.2. LRU không bảo đảm dữ liệu còn mới

Giả sử cache giữ Product P với giá 100. Database đổi giá thành 120, nhưng người dùng tiếp tục get(P) mỗi giây. P luôn là mục rất mới theo LRU và có thể sống lâu tùy ý, trong khi giá là sai.

Các lựa chọn thường kết hợp:
- **Expire-after-write / TTL**: hết hạn sau một khoảng từ lúc ghi hoặc tải thành công; giới hạn tuổi bản lưu, nhưng chấp nhận cửa sổ dữ liệu cũ.
- **Invalidation sau cập nhật thành công**: xóa P khỏi cache khi cập nhật P trong database; lần đọc kế tiếp nạp bản mới.
- **Version/sequence**: kèm phiên bản, ETag hoặc nguồn sự thật có phiên bản; kiểm tra khi cần tính nhất quán cao.
- **Refresh có kiểm soát**: làm mới nền trước hoặc sau khi hết hạn tùy khả năng chấp nhận stale data và hỗ trợ của thư viện.

**Expiration không phải eviction vì đầy bộ nhớ**. Một entry có thể bị loại trước TTL do áp lực capacity; ngược lại nó có thể hết hạn dù cache còn rất nhiều chỗ. Nếu dữ liệu liên quan quyền truy cập, số dư hay quy tắc an toàn, TTL ngắn vẫn có thể là chưa đủ: định nghĩa mức nhất quán trước.

### 4.3. Thread-safe không tự giải quyết cache stampede

Mẫu dễ mắc lỗi:

```java
// Mảnh mã minh họa: cache và loadFromDatabase được định nghĩa ở nơi khác.
Value value = cache.get(key);
if (value == null) {
    value = loadFromDatabase(key);
    cache.put(key, value);
}
```

Hai mươi request có thể cùng thấy miss và cùng gọi database hai mươi lần. Dù get và put riêng lẻ được synchronized như demo, **toàn bộ chuỗi get → load → put không nguyên tử**.

Hướng xử lý:
- Hợp nhất các lần tải cùng key (single-flight / per-key loading) để nhiều request chờ chung một kết quả.
- Đặt timeout, giới hạn số request đang tải, retry có giới hạn và chính sách khi nguồn lỗi.
- Tránh khóa toàn bộ cache trong suốt một lệnh I/O chậm; dùng cơ chế loader hoặc cache concurrent phù hợp.
- Với nhiều process/instance, khóa trong một JVM không ngăn các instance cùng nạp một key. Cần đánh giá thêm shared cache, khóa phân tán hoặc giới hạn tải ở tầng nguồn nếu thực sự cần.

Một cache trong production cần xác định cách xử lý loader trả null, ném exception, bị timeout và kết quả đến muộn sau khi dữ liệu đã được cập nhật.

### 4.4. Tải theo key, negative cache và dữ liệu không tồn tại

Cache API chỉ trả null rất dễ nhập nhằng: không có entry, entry có giá trị null, hoặc nguồn trả “không có bản ghi”. Với key thường bị yêu cầu nhưng không tồn tại, nếu không dùng **negative caching** thì mọi request lại truy vấn database. Nếu cache trạng thái “không tồn tại”, hãy đặt thời hạn riêng, thường ngắn hơn dữ liệu bình thường, để bản ghi mới xuất hiện không bị che quá lâu.

Cần quyết định riêng trường hợp nguồn lỗi: lỗi tạm thời không đồng nghĩa “không tồn tại”. Đừng mặc định lưu exception hoặc dữ liệu chưa xác thực như một kết quả thành công.

### 4.5. Dữ liệu nào được phép chia sẻ?

Cache ở bộ nhớ tiến trình chỉ phục vụ process hiện tại; restart, scale-out hoặc deploy sẽ làm mất cache cục bộ. Với nhiều instance:
- Mỗi instance có LRU riêng nên hit rate, dữ liệu và thứ tự loại bỏ có thể khác nhau.
- Invalidation ở một instance không tự lan tới instance khác.
- Một shared cache như Redis có thể giảm sự phân tán bản lưu nhưng bổ sung network latency, vận hành, giới hạn dung lượng, serialization và failure mode mới.
- Một hệ thống có thể kết hợp cache local cấp L1 và shared cache cấp L2, song lúc đó cần chiến lược làm mới và vô hiệu hóa ở cả hai cấp.

Khóa cache phải có đủ thông tin ảnh hưởng kết quả: ví dụ tenant, locale, quyền/nhóm quyền khi thích hợp, version, tham số lọc. **Không cache nhầm dữ liệu cá nhân theo khóa thiếu ngữ cảnh**, vì đó là lỗi phân tách dữ liệu chứ không chỉ là hit rate thấp.

### 4.6. Hành vi khi cache hoặc nguồn dữ liệu gặp sự cố

Cache là một tối ưu hiệu năng, không nên mặc định trở thành nơi duy nhất lưu dữ liệu có giá trị. Thiết kế rõ:
- Khi cache miss: tải nguồn nào, timeout bao lâu, số lần retry tối đa và request nào được phép chờ.
- Khi cache lỗi: bypass về nguồn khi an toàn, trả stale có kiểm soát (chỉ nếu nghiệp vụ cho phép) hay trả lỗi rõ ràng.
- Khi nguồn dữ liệu lỗi: có cho dùng bản stale hay không; stale cần giới hạn tuổi tuyệt đối nếu dữ liệu nhạy cảm.
- Khi nhiều mục cùng hết hạn: thêm jitter cho TTL hoặc refresh phân tán để tránh dồn tải đột ngột.
- Khi ghi dữ liệu: cập nhật DB trước rồi invalidate đúng key hoặc áp dụng chiến lược write-through/write-behind có đánh giá mất dữ liệu, thứ tự thao tác và retry.

Không có một chính sách fallback đúng cho mọi lĩnh vực: ảnh đại diện có thể stale vài phút, còn hạn mức giao dịch hoặc quyền truy cập có thể đòi hỏi điều kiện nghiêm ngặt hơn.

## 5. Bảng đối chiếu: từ bài tập LRU đến cache dùng thật

| Khía cạnh | LRU LinkedHashMap của bài học | Nhu cầu cache production và câu hỏi thiết kế |
| --- | --- | --- |
| Mục tiêu | Hiểu thứ tự truy cập và loại mục | SLA về latency, tải nguồn, tính đúng đắn |
| Capacity | Đếm số entry | Đo chi phí bộ nhớ/weight, headroom heap, GC |
| Eviction | Bỏ entry ít dùng gần đây | Chọn LRU/LFU/thuật toán thích ứng theo workload; đo hiệu quả |
| Expiration | Chưa có | TTL, expire-after-access, refresh, jitter |
| Consistency | Không liên quan cập nhật nguồn | Invalidate/version/định nghĩa mức stale chấp nhận được |
| Concurrency | Một khóa synchronized | Tránh lock contention, gộp load cùng key, xử lý race |
| Loading | Người gọi tự viết | Loader, timeout, lỗi, null, negative caching |
| Topology | Trong một JVM | Nhiều instance, local/shared/two-level, invalidation |
| Observability | In danh sách key | Hit/miss, eviction theo lý do, load time, error, heap, p95/p99 |
| Security | Khóa là chuỗi ví dụ | Tenant isolation, cache key, quyền, dữ liệu nhạy cảm |
| Lifecycle | Mất khi ứng dụng dừng | Warm-up, restart, autoscale, cold start, giới hạn burst |

Bảng này **không có nghĩa** phải xây hết tính năng mới được dùng cache. Hãy chọn theo yêu cầu thực; một cache nhỏ trong ứng dụng nội bộ có thể chỉ cần vài điều kiện và số liệu cơ bản.

## 6. Lựa chọn công cụ: tự viết, thư viện, hay shared cache

**Tự cài bằng LinkedHashMap** phù hợp để học Collections, chạy demo hoặc làm cache rất nhỏ với ngữ nghĩa rõ ràng, ít luồng và chấp nhận thiếu tính năng. Khi viết thật, bạn sở hữu mọi race, TTL, metric, loader và vận hành.

**Thư viện cache cục bộ như Caffeine** phù hợp khi cần cache trong một JVM với quản lý dung lượng, thời hạn, loader, thống kê và concurrency đã được thư viện xử lý. Ví dụ sau là **mảnh minh họa API, cần dependency Caffeine và hàm repository thật**, không thể biên dịch độc lập chỉ bằng JDK:

```java
Cache<String, Product> products = Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(Duration.ofMinutes(5))
    .recordStats()
    .build();

Product product = products.get(id, key -> repository.findById(key));
```

Trong mã thật phải import kiểu Cache, Caffeine, Duration, Product; cần xác định repository trả về object, null hoặc exception thế nào. Đừng sao chép thông số 10.000 và 5 phút mà không có dữ liệu tải, dung lượng, yêu cầu nhất quán. Caffeine tối ưu cho cache **local**; không tự đồng bộ dữ liệu giữa các JVM.

**Shared cache như Redis** hữu ích khi nhiều instance cần chia sẻ bản lưu hoặc khi bộ nhớ ứng dụng không phù hợp để giữ lượng dữ liệu lớn. Đổi lại phải quản lý network, serialization, outage, TTL, áp lực RAM và eviction policy của chính hệ thống shared. Không đồng nhất “bật LRU” trong một sản phẩm với chính xác thuật toán LinkedHashMap của bài tập.

**Không dùng cache** cũng có thể là lựa chọn tốt nếu truy vấn rẻ, dữ liệu đổi liên tục, khó invalidate, hit rate thấp hoặc chi phí rủi ro dữ liệu cũ vượt phần hiệu năng tiết kiệm.

## 7. Đo hiệu quả thay vì đoán

Một cache được đánh giá bằng **hiệu quả toàn hệ thống**:
- Hit ratio = hits / (hits + misses). Phải định nghĩa rõ miss do absent, expired, invalidated; bỏ qua phép chia nếu chưa có lượt đọc.
- Load success/failure, thời gian truy cập nguồn, số request tải đồng thời, số lần tải trùng cùng key.
- Eviction count theo lý do: capacity/weight/expiration/manual invalidation nếu thư viện cung cấp.
- p50/p95/p99 latency của request, QPS tới database, CPU, heap, GC pause và network nếu có shared cache.
- Dung lượng thực tế và phân phối kích thước entry; tỷ lệ key nóng so với truy cập tuần tự.

Ví dụ: tỷ lệ hit 95% vẫn có thể xấu nếu 5% miss đồng thời tạo burst quá lớn tới database; tỷ lệ hit 70% có thể đủ nếu truy vấn miss rẻ và cache đơn giản, dễ duy trì. Đo bằng workload gần thực tế, có cả giai đoạn cold cache và tải tăng đột ngột. Benchmark chi tiết về chi phí map/lock nên dùng công cụ như JMH, tránh kết luận từ vòng lặp microbenchmark tự viết chưa warm-up.

## 8. Thực hành kiểm chứng và các ca biên

Bắt đầu bằng việc chạy chương trình mục 3, sau đó kiểm chứng các trường hợp sau. **Expected** bên dưới xét riêng một cache có capacity = 3 và không có TTL.

| Test | Chuỗi thao tác | Kỳ vọng |
| --- | --- | --- |
| Eviction đúng LRU | put(A), put(B), put(C), get(A), put(D) | B bị loại; thứ tự C, A, D |
| Ghi đè khóa cũ | put(A), put(B), put(C), put(A, mới) | Không tăng size; A thành mới nhất |
| Đọc khóa thiếu | put(A), get(X) | Trả null, A vẫn còn |
| Input không hợp lệ | Tạo cache capacity = 0 | Ném IllegalArgumentException |
| Value null | put(A, null) | Ném NullPointerException theo quyết định API demo |
| Đúng giới hạn | Chèn 100 key khác nhau với capacity = 3 | size không vượt 3 |
| Hai luồng dùng cùng cache | Đọc/ghi xen kẽ vào một LruCache | Không làm hỏng trạng thái map nhờ synchronized, song thứ tự cuối phụ thuộc lịch chạy |

**Bài tập mở rộng 1 – TTL:** thêm tuổi tối đa cho value và một Clock/Ticker có thể điều khiển trong test. Trường hợp cần kiểm thử: mục còn trong thứ tự LRU nhưng đã quá thời hạn thì get phải được coi là miss. Đừng dùng Thread.sleep để tạo kiểm thử phụ thuộc timing. Xác định rõ expire-after-write hay expire-after-access trước khi code.

**Bài tập mở rộng 2 – cache stampede:** giả lập mười request cùng truy vấn một key chưa có. Đếm số lần loader thực sự chạy. Chỉ synchronized get và synchronized put riêng lẻ sẽ không bảo đảm loader chạy đúng một lần. Thử cơ chế loading theo key rồi đo thời gian chờ của các request khác.

**Bài tập mở rộng 3 – cân theo weight:** thay ba value kích thước rất khác nhau. Chỉ ra tại sao capacity = 3 không thể là ngân sách RAM. Thiết kế quy tắc weight và kiểm thử mục quá lớn so với ngân sách sẽ được xử lý ra sao.

**Bài tập mở rộng 4 – tính nhất quán:** cache giá sản phẩm, cập nhật database rồi đọc lại. Xác định yêu cầu: có thể stale tối đa bao lâu, có sự kiện invalidation không, khi sự kiện đến trễ thì xử lý gì, và khi DB lỗi có được trả giá cũ không.

## 9. Checklist quyết định trước khi đưa cache vào ứng dụng

1. **Vì sao cache?** Biết bottleneck cụ thể và chỉ số muốn cải thiện (latency hay chi phí gọi nguồn).
2. **Cache cái gì?** Chọn key, value, tenant và dữ liệu nào không được lưu do yêu cầu quyền riêng tư/độ mới.
3. **Giới hạn tài nguyên?** Đếm số entry hay weight, có giới hạn heap/network và quan sát GC không?
4. **Bao giờ giá trị sai?** Xác định TTL, sự kiện invalidate, phiên bản và mức stale có thể chấp nhận.
5. **Ai cùng truy cập?** Một luồng, nhiều luồng hay nhiều instance? Chống duplicate load ở phạm vi nào?
6. **Khi lỗi thì sao?** Quyết định timeout, retry, fallback và có trả stale hay không.
7. **Đã chứng minh lợi ích?** Thử cold/warm cache, concurrent misses, phân phối key thật và đọc số liệu latency/load.

### Kết luận

**LRU trả lời một câu hỏi hẹp: “Khi thiếu chỗ, loại mục nào?”** Cache production còn phải trả lời “dữ liệu có đúng không, được giữ bao lâu, tốn bao nhiêu RAM, tải đồng thời xử lý ra sao và hệ thống quan sát/phục hồi thế nào?”. LinkedHashMap là công cụ rất tốt để hiểu eviction theo truy cập; việc chọn cơ chế cache thật cần bắt đầu từ đặc tính workload và yêu cầu tính đúng đắn, rồi mới chọn thư viện hoặc hạ tầng.

## Tài liệu đọc thêm

- Java 17 API – LinkedHashMap (insertion-order, access-order, removeEldestEntry): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html
- Caffeine (thư viện cache Java, chính sách eviction/expiration): https://github.com/ben-manes/caffeine
- Redis eviction policies (giới hạn bộ nhớ và lựa chọn chính sách): https://redis.io/docs/latest/develop/reference/eviction/
