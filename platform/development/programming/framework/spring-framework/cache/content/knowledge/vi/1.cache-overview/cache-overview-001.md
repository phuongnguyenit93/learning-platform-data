# Bộ nhớ đệm (cache) là gì và bài toán giảm xử lý lặp?

> Phạm vi: kiến thức nền tảng về cache, vì sao cache giảm công việc lặp và cách nhận biết lợi ích, chi phí, rủi ro của nó trong ứng dụng Java/Spring.

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Giải thích cache bằng mô hình `key → value`, phân biệt cache với nguồn dữ liệu gốc.
- Mô tả `cache hit`, `cache miss`, luồng đọc lần đầu và các lần đọc sau.
- Nhận diện tác vụ lặp phù hợp để cache; tính được lợi ích độ trễ bằng một ví dụ định lượng.
- Biết vì sao cache có thể trả dữ liệu cũ, chiếm bộ nhớ, tăng độ phức tạp và cần chính sách hết hạn/vô hiệu hóa.
- Hiểu chỗ đứng của Spring Cache và thực hành một ví dụ Java 17 có thể chạy độc lập.

## 1. Bài toán: cùng một yêu cầu, cùng một xử lý tốn kém

Giả sử dịch vụ cần lấy thông tin sản phẩm để hiển thị trên trang. Mỗi lần gọi `getProduct("P100")`, ứng dụng phải truy vấn cơ sở dữ liệu, ghép thông tin và tạo kết quả. Nếu dữ liệu sản phẩm chưa đổi nhưng hàng trăm yêu cầu cùng hỏi về `P100`, ta đang làm lại những việc giống nhau.

Một số công việc lặp thường gặp:
- Cùng một câu truy vấn dữ liệu tham chiếu hoặc cấu hình ít thay đổi.
- Tạo lại kết quả tính toán tốn CPU từ cùng bộ tham số.
- Đọc lặp một tài nguyên từ dịch vụ ngoài có độ trễ mạng cao.
- Chuyển đổi hoặc tổng hợp lại dữ liệu ổn định cho nhiều lần đọc.

Không phải mọi lần gọi cùng phương thức đều có thể tái sử dụng kết quả. Nếu kết quả phụ thuộc thời gian hiện tại, quyền truy cập, trạng thái mới thay đổi, hoặc có tác dụng phụ, việc dùng lại kết quả cũ có thể sai. Vì vậy câu hỏi đầu tiên là: **với cùng đầu vào và trong một khoảng thời gian chấp nhận được, kết quả có thể được tái sử dụng an toàn không?**

## 2. Cache là gì?

**Cache (bộ nhớ đệm)** là nơi lưu tạm kết quả đã có hoặc đã tính, để lần yêu cầu tiếp theo có thể đọc lại với chi phí thấp hơn việc thực hiện toàn bộ xử lý gốc. Một mục cache thường gồm:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `key` | Định danh duy nhất cho kết quả cần tìm | `product:P100:vi` |
| `value` | Kết quả đã được lưu để tái sử dụng | Dữ liệu sản phẩm P100 |
| Thời hạn/chính sách | Quy định lúc nào mục không còn hợp lệ hoặc cần bị loại | TTL 5 phút, xóa khi sản phẩm đổi |

Cache là **bản sao hoặc kết quả suy ra**, thường không phải *source of truth* (nguồn dữ liệu có thẩm quyền). Ví dụ, cơ sở dữ liệu giữ thông tin sản phẩm chính thức; cache giữ một bản đọc nhanh có thể cũ hơn.

Từ vựng cần nhớ:

- **Cache hit:** tìm thấy mục còn dùng được theo key; trả kết quả lưu sẵn và bỏ qua phần xử lý gốc tương ứng.
- **Cache miss:** không có mục hợp lệ; cần thực hiện công việc gốc rồi có thể lưu kết quả cho lần sau.
- **Cache population:** đưa kết quả vào cache.
- **Invalidation:** chủ động làm mục cache không còn được sử dụng, chẳng hạn xóa `product:P100` sau khi cập nhật P100.
- **Expiration:** mục hết hạn theo thời gian hoặc chính sách.
- **Eviction:** loại mục khỏi cache, thường để giải phóng dung lượng hoặc áp dụng chính sách thay thế.

### Vòng đời một lần đọc: cache-aside (lazy loading)

```text
Yêu cầu getProduct("P100")
          |
          v
Tìm key "product:P100" trong cache
          |
       +--+--+
       |     |
      HIT   MISS
       |     |
       |     v
       |  Truy vấn/tính toán từ nguồn gốc
       |     |
       |  Lưu kết quả vào cache (nếu được phép)
       |     |
       +--+--+
          |
          v
      Trả kết quả
```

Lần đầu thường là miss; lần đọc lại cùng key có thể là hit. Một miss không tự động là lỗi hệ thống: đó là hành vi bình thường khi mục chưa được nạp, đã hết hạn, bị xóa hoặc cache vừa khởi động lại. Trong mô hình cache-aside, ứng dụng chủ động kiểm tra cache và nạp dữ liệu khi miss.

## 3. Cache giải quyết bài toán giảm xử lý lặp như thế nào?

Giả sử truy vấn và tổng hợp một sản phẩm tốn 120 ms, còn kiểm tra cache tốn 2 ms. Với tỷ lệ hit `H = 80%`, mô hình đơn giản cho thời gian trung bình là:

```text
T_trung_bình ≈ T_tra_cache + (1 - H) × T_xử_lý_gốc
             = 2 ms + (1 - 0,8) × 120 ms
             = 26 ms/yêu cầu
```

Không dùng cache, đường xử lý gốc trong ví dụ tốn khoảng 120 ms/yêu cầu. Đây là phép tính minh họa, không phải cam kết hiệu năng: trong thực tế còn có cạnh tranh tài nguyên, serialization, truy cập mạng, cập nhật dữ liệu, phân phối key và chi phí bộ nhớ.

**Tỷ lệ cache hit** = số yêu cầu đọc trúng cache / tổng số yêu cầu tra cache. Tỷ lệ hit cao có thể giảm số lần chạm cơ sở dữ liệu hoặc API bên ngoài, qua đó giảm tải CPU/I/O, cải thiện độ trễ và hỗ trợ hệ thống chịu nhiều yêu cầu hơn. Nhưng hit rate cao không đủ để chứng minh hệ thống tốt: nếu cache chứa dữ liệu sai hoặc stale quá lâu, số liệu đẹp vẫn đi kèm kết quả sai.

### Phân biệt ba khái niệm

- **Tiết kiệm xử lý:** tránh thực hiện lại công việc gốc cho một hit.
- **Giảm độ trễ:** hit thường phản hồi nhanh hơn miss; không phải mọi cache đều nhanh hơn nguồn gốc.
- **Tăng throughput:** khi giảm tải nút thắt cổ chai, hệ thống có thể phục vụ nhiều yêu cầu hơn; lợi ích phụ thuộc nơi phát sinh nút thắt.

## 4. Khi nào nên cache, và khi nào không?

Ưu tiên những kết quả có **chi phí tạo lớn**, **được yêu cầu lặp nhiều**, **xác định được bằng key**, và **cho phép một mức độ trễ cập nhật nhất định**. Ví dụ: danh mục ít thay đổi, thông tin sản phẩm hiển thị, cấu hình đã công bố, kết quả tổng hợp cho cùng bộ lọc.

Cần cân nhắc kỹ hoặc tránh cache trực tiếp trong các tình huống sau:

1. Dữ liệu phải chính xác ngay sau mỗi thay đổi (ví dụ số dư dùng để quyết định giao dịch), trừ khi đã có cơ chế nhất quán đáp ứng yêu cầu.
2. Kết quả phụ thuộc danh tính, tenant, vai trò hoặc ngữ cảnh riêng tư nhưng key không bao gồm đầy đủ ngữ cảnh đó: có nguy cơ lộ dữ liệu chéo người dùng.
3. Tác vụ có tác dụng phụ như thanh toán, gửi thông báo, ghi đơn hàng; trả lại kết quả cũ **không** thay thế được việc thực hiện nghiệp vụ.
4. Mỗi yêu cầu dùng key khác nhau, hiếm khi lặp, hoặc việc kiểm tra cache còn đắt hơn xử lý gốc.
5. Dữ liệu rất lớn, bộ nhớ hạn chế, cần tính nhất quán mạnh nhưng chưa có phương án invalidation.

**Nguyên tắc:** chỉ cache những gì có thể tái sử dụng đúng đắn; tối ưu đo được quan trọng hơn thêm cache ở mọi nơi.

## 5. Ví dụ Java 17+: cùng key chỉ tính một lần

Ví dụ độc lập dưới đây dùng `ConcurrentHashMap` và `computeIfAbsent`. Nó mô phỏng một công việc gốc tốn chi phí bằng dòng in `Tính lại...`; lần gọi sau với cùng key sẽ lấy kết quả đã lưu.

Tạo tệp `CacheDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheDemo {
    private final ConcurrentMap<String, String> cache =
            new ConcurrentHashMap<>();
    private final AtomicInteger calculations = new AtomicInteger();

    private String loadFromSource(String id) {
        int count = calculations.incrementAndGet();
        System.out.println("Tính lại cho " + id + " (lần " + count + ")");
        return "user:" + id;
    }

    public String getProfile(String id) {
        return cache.computeIfAbsent(id, this::loadFromSource);
    }

    public static void main(String[] args) {
        CacheDemo demo = new CacheDemo();
        System.out.println("Lấy 1: " + demo.getProfile("u1"));
        System.out.println("Lấy 2: " + demo.getProfile("u1"));
        System.out.println("Lấy 3: " + demo.getProfile("u2"));
        System.out.println("Số lần xử lý gốc: " + demo.calculations.get());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CacheDemo.java
java CacheDemo
```

Kết quả chuẩn khi chạy `main` theo thứ tự trên:

```text
Tính lại cho u1 (lần 1)
Lấy 1: user:u1
Lấy 2: user:u1
Tính lại cho u2 (lần 2)
Lấy 3: user:u2
Số lần xử lý gốc: 2
```

**Giải thích:** lần đầu gọi `u1` là miss nên chạy `loadFromSource`; lần thứ hai với `u1` là hit; `u2` là key mới nên miss. Nếu gọi trực tiếp `loadFromSource` cả ba lần thì công việc gốc sẽ chạy ba lần. `ConcurrentHashMap` hỗ trợ truy cập đồng thời an toàn cho bản đồ và `computeIfAbsent` tránh nhiều lần tính đua nhau cho cùng key trong ngữ cảnh hoạt động thông thường của map này.

**Giới hạn cố ý của ví dụ:** cache chỉ sống trong một đối tượng Java, không có TTL, không giới hạn số mục, không tự đồng bộ giữa nhiều instance và không xóa khi dữ liệu nguồn thay đổi. Không nên lấy nguyên mẫu này làm cache production dài hạn vì nó có thể giữ dữ liệu cũ và tăng bộ nhớ mãi theo số key khác nhau.

## 6. Dữ liệu cũ và quy tắc hết hạn: vấn đề không thể bỏ qua

Giả sử sản phẩm P100 có giá 100.000 đồng và kết quả đã vào cache. Nhân viên cập nhật giá nguồn thành 110.000 đồng. Nếu cache vẫn trả 100.000 đồng thì hệ thống có **stale data** (dữ liệu cũ).

Các chiến lược phổ biến:

| Chiến lược | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| TTL (*time to live*) | Mục hết hiệu lực sau một thời hạn | Đơn giản nhưng có cửa sổ dữ liệu cũ; TTL quá ngắn gây nhiều miss |
| Invalidate khi ghi | Khi dữ liệu nguồn cập nhật thành công, xóa key liên quan | Tươi hơn nhưng phải xác định đúng mọi key bị ảnh hưởng |
| Cập nhật cache khi ghi | Sau khi cập nhật nguồn, ghi lại giá trị cache phù hợp | Có thể tránh miss kế tiếp nhưng phải xử lý thứ tự/đồng thời |
| Giới hạn dung lượng + eviction | Bỏ mục theo chính sách như LRU/LFU của provider | Khống chế bộ nhớ; hit rate có thể giảm |

**TTL không đồng nghĩa dữ liệu luôn mới.** TTL 5 phút vẫn có thể trả giá cũ trong thời gian đó nếu không invalidation khi có thay đổi. Còn eviction vì đầy bộ nhớ không nhất thiết có nghĩa bản ghi đã quá hạn.

Khi xử lý cập nhật, cần tính đến giao dịch: invalidation trước khi ghi nguồn thành công có thể khiến cache bị nạp lại từ giá trị cũ; invalidation sau khi commit thường phù hợp hơn. Trong hệ thống phân tán còn có các race condition giữa yêu cầu đọc, cập nhật nguồn và điền lại cache; thiết kế tính nhất quán phải phù hợp yêu cầu nghiệp vụ.

## 7. Key, phạm vi lưu và các rủi ro đi kèm

### Thiết kế key đúng

Nếu phương thức `getPrice(productId, currency, customerGroup)` trả kết quả khác nhau theo từng nhóm, key chỉ gồm `productId` là thiếu. Key đúng cần phản ánh **toàn bộ tham số và ngữ cảnh làm thay đổi kết quả**, ví dụ `price:P100:VND:retail`. Với dữ liệu theo tài khoản hoặc tenant, xác định ranh giới quyền truy cập trước khi cache. Key nên ổn định, nhất quán và đủ phân biệt các kết quả.

### Local cache và distributed cache

- **Local/in-memory per instance:** tra cứu nhanh, ít phụ thuộc mạng; mỗi tiến trình có bản riêng, khó đồng bộ invalidation giữa nhiều instance và cache mất khi tiến trình khởi động lại.
- **Distributed cache:** nhiều instance có thể dùng chung dữ liệu (ví dụ Redis); giúp dùng chung hit và invalidation nhưng có độ trễ mạng, thêm hạ tầng, lỗi kết nối và chi phí serialization.
- **Nhiều tầng:** cache gần ứng dụng kết hợp cache dùng chung có thể giảm độ trễ thêm, nhưng càng phải định nghĩa rõ thứ tự đọc và cập nhật.

### Những sự cố dễ gặp

- **Cache stampede / thundering herd:** nhiều yêu cầu đồng thời miss một key nóng và cùng đổ xuống nguồn. Có thể dùng cơ chế tải một lần cho cùng key, khóa có phạm vi phù hợp, hoặc chính sách làm mới có kiểm soát.
- **Hot key:** một key nhận quá nhiều truy cập, gây nghẽn một nút hoặc vùng nhớ.
- **Memory pressure:** số lượng key tăng không kiểm soát; cần giới hạn dung lượng và chính sách eviction.
- **Negative caching:** lưu kết quả “không tìm thấy” trong thời gian ngắn khi phù hợp; nếu dữ liệu xuất hiện ngay sau đó, kết quả âm cũ cũng cần hết hạn.
- **Caching sai ngữ cảnh:** thiếu tham số quyền truy cập, locale, phiên bản hoặc tenant trong key dẫn đến trả sai dữ liệu.
- **Che giấu lỗi thiết kế:** cache có thể che một truy vấn quá chậm; nên đo và tối ưu nguồn gốc khi cần.

## 8. Trong Spring Framework, cache nằm ở đâu?

Spring Cache cung cấp **lớp trừu tượng** để khai báo việc kiểm tra/lưu/xóa cache quanh lời gọi phương thức. Ý tưởng vẫn là hit thì lấy kết quả đã lưu, miss thì thực thi phương thức và cân nhắc lưu kết quả. Các annotation thường gặp:

- `@Cacheable`: có thể bỏ qua việc chạy phương thức nếu tìm được kết quả trong cache.
- `@CachePut`: phương thức vẫn chạy; kết quả được ghi vào cache.
- `@CacheEvict`: loại bỏ mục cache được chỉ định (hoặc toàn bộ cache theo cấu hình).
- `@EnableCaching`: bật cơ chế xử lý các annotation cache trong cấu hình Spring.

Ví dụ ký hiệu trong **một dự án Spring đã có `Product`, `ProductRepository` và `CacheManager` phù hợp** (đoạn mã minh họa phương thức, không phải chương trình Java độc lập):

```java
@Cacheable(cacheNames = "products", key = "#id")
public Product getProduct(String id) {
    return repository.findById(id).orElseThrow();
}
```

Khi gọi `getProduct("P100")` qua Spring proxy, framework tra cache tên `products` bằng key `P100`. Hit có thể trả trực tiếp giá trị lưu; miss gọi `repository`, sau đó lưu kết quả theo quy tắc. Khi cập nhật sản phẩm, ứng dụng còn cần cơ chế xóa hoặc cập nhật mục liên quan.

**Hai điểm dễ hiểu nhầm:** (1) Spring Cache là abstraction, không tự quyết định TTL, eviction hay dung lượng cho mọi provider; việc này tùy cấu hình bên lưu trữ như Caffeine hoặc Redis. (2) Ở chế độ proxy mặc định, phương thức trong cùng đối tượng tự gọi một phương thức `@Cacheable` khác của chính nó (*self-invocation*) không đi qua proxy nên không kích hoạt hành vi caching như lời gọi từ bên ngoài bean.

Đọc thêm tài liệu chính thức:
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — TTL/TTI/Eviction Policies](https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html)

## 9. Đánh giá hiệu quả cache bằng số liệu thực tế

Trước và sau khi bật cache, theo dõi cùng một loại workload:

1. **Hit/miss rate theo cache và key group**: có thật sự tránh xử lý lặp?
2. **Độ trễ p50/p95/p99 của API** và độ trễ nguồn: người dùng có nhanh hơn không?
3. **Số truy vấn DB, lời gọi API, CPU và thông lượng**: điểm nghẽn có giảm?
4. **Dung lượng, eviction, expiration, thời gian nạp lại**: có đang giữ quá nhiều dữ liệu?
5. **Độ tươi và lỗi trả sai dữ liệu**: các kịch bản cập nhật đã được kiểm thử?
6. **Hành vi khi cache lỗi hoặc lạnh**: hệ thống nguồn có chịu nổi lưu lượng miss không?

Một cache tốt là cache tạo ra lợi ích đo được **mà vẫn đáp ứng yêu cầu đúng đắn của dữ liệu**. Tăng hit rate nhưng làm mất tính đúng đắn không phải tối ưu thành công.

## 10. Tình huống thực hành và tự kiểm tra

**Tình huống:** API trả danh sách tỉnh/thành từ nguồn dữ liệu hiếm thay đổi, được gọi 10.000 lần/ngày. Hãy chọn key xác định tập dữ liệu và ngôn ngữ hiển thị; nạp vào cache khi miss; đặt TTL hợp lý; chủ động invalidation khi tập dữ liệu thay đổi; theo dõi hit rate, độ trễ và độ tươi.

Tự trả lời:
1. Vì sao lời gọi thứ hai với cùng key thường nhanh hơn lần đầu? Điều gì có thể khiến nó vẫn miss?
2. Nếu giá sản phẩm vừa cập nhật, TTL 10 phút có đảm bảo kết quả mới ngay không? Cần thêm gì?
3. Vì sao `getPrice("P100", "USD")` và `getPrice("P100", "VND")` không nên dùng chung một key?
4. Khi chạy 5 instance ứng dụng, local cache khác distributed cache ở điểm nào?
5. Thấy hit rate 95% nhưng p95 latency và dữ liệu sai đều tăng: bạn sẽ điều tra những gì?

**Ghi nhớ:** Cache đổi chi phí tính/đọc lặp lấy chi phí lưu trữ, tra cứu và quản lý tính mới. Chọn đối tượng cache, key, thời hạn và cơ chế invalidation dựa trên yêu cầu nghiệp vụ; sau đó đo hiệu quả bằng số liệu.