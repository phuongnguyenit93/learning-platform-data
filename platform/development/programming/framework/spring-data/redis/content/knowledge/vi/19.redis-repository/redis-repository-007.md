# Phân trang, sắp xếp và giới hạn thực tế của Redis Repository

## 1. Bài toán: có Repository rồi, vì sao phân trang vẫn khó?

Trong Spring Data, lập trình viên đã quen với các API như `findAll(Pageable)`, `findAll(Sort)` hoặc phương thức suy diễn `findByCategory(..., Pageable)`. Với cơ sở dữ liệu quan hệ, các API này thường dẫn đến câu truy vấn có `ORDER BY`, `LIMIT` và `OFFSET`. Nhưng **Spring Data Redis Repository** hoạt động trên cấu trúc key-value và các chỉ mục Redis, không phải trên một bộ máy truy vấn SQL.

Vì vậy, khi thiết kế danh sách sản phẩm, bài viết, phiên làm việc hoặc bảng xếp hạng, cần tách ba yêu cầu:

1. **Lọc**: tìm khóa ứng với một điều kiện, ví dụ `category = "book"`.
2. **Sắp xếp**: xác định thứ tự, ví dụ `createdAt DESC, id ASC`.
3. **Phân trang**: lấy một đoạn của thứ tự đó, ví dụ 20 mục tiếp theo, và có thể cần tổng số mục.

Redis Repository hỗ trợ lưu, đọc và một số truy vấn dựa trên chỉ mục phụ (`@Indexed`). Tuy nhiên, **không nên mặc định rằng chữ ký `Pageable` hay `Sort` bảo đảm sắp xếp và phân trang hiệu quả ngay bên trong Redis**. Khả năng hỗ trợ, kiểu kết quả và cách thực thi cụ thể phụ thuộc phiên bản Spring Data Redis và loại truy vấn.

Một danh sách đúng chức năng trên tập dữ liệu nhỏ có thể trở nên chậm trên tập lớn nếu ứng dụng phải tải toàn bộ entity về rồi tự sắp xếp và cắt trang.

> Ý tưởng xuyên suốt bài: **Redis Repository quản lý entity; cấu trúc dữ liệu phù hợp của Redis quản lý thứ tự và vị trí phân trang khi hệ thống có yêu cầu hiệu năng cụ thể.** Hai phần có thể phối hợp với nhau.

## 2. Redis Repository lưu và tìm entity như thế nào?

Xét một entity sản phẩm:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("product")
public class Product {

    @Id
    private String id;

    @Indexed
    private String category;

    private String name;
    private long createdAtEpochMillis;
    private long priceInCents;

    public Product() { }

    public Product(String id, String category, String name,
                   long createdAtEpochMillis, long priceInCents) {
        this.id = id;
        this.category = category;
        this.name = name;
        this.createdAtEpochMillis = createdAtEpochMillis;
        this.priceInCents = priceInCents;
    }

    public String getId() { return id; }
    public String getCategory() { return category; }
    public String getName() { return name; }
    public long getCreatedAtEpochMillis() { return createdAtEpochMillis; }
    public long getPriceInCents() { return priceInCents; }

    public void setId(String id) { this.id = id; }
    public void setCategory(String category) { this.category = category; }
    public void setName(String name) { this.name = name; }
    public void setCreatedAtEpochMillis(long createdAtEpochMillis) {
        this.createdAtEpochMillis = createdAtEpochMillis;
    }
    public void setPriceInCents(long priceInCents) {
        this.priceInCents = priceInCents;
    }
}
```

Một Repository đơn giản:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

Spring Data Redis lưu nội dung entity theo khóa và quản lý các cấu trúc hỗ trợ Repository. `@Indexed` khai báo chỉ mục phụ để truy vấn theo `category`. Có thể hình dung:

```text
Product(id=p101, category=book, createdAt=..., price=...)
       |
       +--> dữ liệu entity theo ID
       |
       +--> tập ID cho category=book (secondary index)
```

Một tập ID cho biết **phần tử nào thỏa điều kiện**, nhưng không tự nói **phần tử nào mới nhất**, **rẻ nhất** hoặc **đứng thứ 21**. Nếu chỉ lấy danh sách từ một chỉ mục kiểu tập hợp, không nên dựa vào thứ tự trả về làm quy tắc sắp xếp nghiệp vụ.

### Redis Repository không phải công cụ truy vấn tổng quát

Các đặc tính cần nhớ:

- `@Indexed` giúp một số truy vấn suy diễn tìm các ID phù hợp, nhưng không tự xây dựng chỉ mục sắp xếp đa trường.
- Redis không có phép `JOIN`, `GROUP BY` hoặc `ORDER BY` trên tập entity Repository tương đương SQL.
- Một câu truy vấn kết hợp nhiều điều kiện có thể không được Redis Repository hỗ trợ, dù cú pháp tương tự tồn tại ở module Spring Data khác.
- `findAll()` có thể phải xét rất nhiều entity; dùng nó như nguồn dữ liệu để lọc/sắp xếp thường không phù hợp với danh sách lớn.
- Việc triển khai `PagingAndSortingRepository` không đồng nghĩa mọi kiểu phương thức đều được hỗ trợ ở mức module hoặc có chi phí tốt. Cần xét phiên bản API cụ thể và cách backend thực thi.

## 3. `Page`, `Slice`, `Pageable` và `Sort` có ý nghĩa gì?

Các abstraction của Spring Data mô tả **yêu cầu** và **kết quả** phân trang; chúng không tự tạo một chỉ mục sắp xếp trong Redis.

| Khái niệm | Chức năng | Câu hỏi thực tế với Redis |
| --- | --- | --- |
| `Pageable` | Số trang, kích thước trang và `Sort` | Backend có hỗ trợ áp dụng đầy đủ, hay phải thực hiện ở ứng dụng? |
| `Sort` | Thuộc tính và hướng tăng/giảm | Có cấu trúc Redis nào duy trì được thứ tự theo thuộc tính đó? |
| `Page<T>` | Nội dung trang kèm tổng số phần tử/trang | Tổng số được tính ở đâu, có cần quét dữ liệu không? |
| `Slice<T>` | Nội dung trang và dấu hiệu còn trang kế | Có thể lấy `size + 1` mục để nhận biết trang tiếp? |
| Cursor/keyset | Lấy mục đứng sau một mốc đã biết | Mốc có duy nhất, cố định và tìm lại được không? |

Ví dụ biểu diễn yêu cầu thông dụng:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable requested = PageRequest.of(
    2, // trang thứ ba, đánh số từ 0
    20,
    Sort.by(
        Sort.Order.desc("createdAtEpochMillis"),
        Sort.Order.asc("id")
    )
);
```

Đoạn trên chỉ tạo đối tượng `Pageable`. Nó **không chứng minh** phương thức Redis Repository nào đó có thể thực thi truy vấn theo `createdAtEpochMillis DESC, id ASC` ở phía máy chủ.

### Lưu ý khi chọn interface Repository

Ở các thế hệ Spring Data mới, `PagingAndSortingRepository` và `CrudRepository` là các interface riêng. Khi module có hỗ trợ các thao tác tương ứng và cần cả hai nhóm phương thức, có thể phải kế thừa cả hai:

```java
// Minh họa cấu trúc API Spring Data Commons.
// Không mặc định rằng Redis hỗ trợ mọi phương thức với cùng ngữ nghĩa/hiệu năng.
interface ExampleRepository extends
        org.springframework.data.repository.CrudRepository<Product, String>,
        org.springframework.data.repository.PagingAndSortingRepository<Product, String> {
}
```

Trước khi xây API nghiệp vụ phụ thuộc `findAll(Pageable)`, `findAll(Sort)` hoặc một query method trả về `Page`, hãy xác định **tài liệu và hành vi của chính phiên bản Spring Data Redis đang dùng**. Nếu tính năng không được hỗ trợ hoặc khiến ứng dụng materialize nhiều dữ liệu, chuyển sang cách xây chỉ mục cụ thể như ở các phần sau.

## 4. Cách đơn giản: đọc danh sách, sắp xếp trong Java rồi cắt trang

Đối với tập cấu hình rất nhỏ hoặc dữ liệu giới hạn cứng, cách dễ hiểu nhất là đọc hết các entity liên quan:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.StreamSupport;

public List<Product> smallCatalogPage(
        ProductRepository repository, int page, int size) {

    if (page < 0 || size <= 0) {
        throw new IllegalArgumentException("Invalid page or size");
    }

    long skip = Math.multiplyExact((long) page, (long) size);

    return StreamSupport
        .stream(repository.findAll().spliterator(), false)
        .sorted(
            Comparator.comparingLong(
                Product::getCreatedAtEpochMillis
            ).reversed().thenComparing(Product::getId)
        )
        .skip(skip)
        .limit(size)
        .toList();
}
```

Kết quả có thứ tự rõ ràng vì comparator định nghĩa cả trường phụ `id` khi hai sản phẩm có cùng thời điểm tạo.

Nhưng giả sử hệ thống có 500.000 sản phẩm và chỉ cần 20 sản phẩm cho trang đầu:

- Redis và ứng dụng vẫn có thể phải đọc **rất nhiều** entity trước khi chọn 20 mục.
- Sắp xếp trong Java cần xử lý danh sách lớn, thường tốn bộ nhớ và CPU theo quy mô dữ liệu.
- Mỗi request lặp lại công việc; nhiều request đồng thời dễ tạo áp lực cho Redis, mạng và JVM.
- Thứ tự/tổng số có thể thay đổi giữa các request do dữ liệu đang được thêm, xóa hoặc sửa.

Do đó, cách này phù hợp khi **số lượng phần tử được giới hạn và đã biết là nhỏ**, không phù hợp làm mặc định cho danh sách phát triển không giới hạn.

## 5. Dùng Redis Sorted Set để lưu thứ tự

Redis Sorted Set (`ZSET`) lưu cặp **member + score**, duy trì member theo score. Lệnh lấy phần tử theo rank hoặc khoảng score giúp giải quyết chính bài toán “ID nào đứng trước ID nào?”.

Ví dụ, tạo chỉ mục thứ tự sản phẩm:

```redis
ZADD product:order 101 p101 102 p102 103 p103 104 p104
ZCARD product:order
ZREVRANGE product:order 0 1 WITHSCORES
```

Kết quả `ZREVRANGE ... 0 1` là hai member có score cao nhất: `p104` và `p103`. Đây có thể là hai sản phẩm mới nhất nếu score được tạo theo thứ tự thêm sản phẩm.

Sơ đồ dữ liệu:

```text
Redis Repository                  Redis Sorted Set
+------------------------+       +--------------------------+
| product:p101 -> fields  |       | product:order            |
| product:p102 -> fields  |       | (p104, 104)              |
| product:p103 -> fields  | <--+  | (p103, 103)              |
| product:p104 -> fields  |    |  | (p102, 102)              |
+------------------------+    |  | (p101, 101)              |
                              |  +--------------------------+
                         đọc ID theo thứ tự
                         rồi tải entity tương ứng
```

Tách hai việc:

1. **Repository** quản lý sản phẩm theo ID.
2. **ZSET** quyết định thứ tự và cung cấp các ID thuộc trang đang cần.

Cách này tránh phải tải toàn bộ entity chỉ để tìm 20 ID đứng đầu.

### Chọn score cho ZSET

Có nhiều lựa chọn:

| Score | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| Unix timestamp (mili giây) | Sắp theo thời điểm tạo/cập nhật | Nhiều entity có thể trùng timestamp |
| Giá sản phẩm | Sắp theo giá | Nếu giá thay đổi, phải cập nhật score |
| Lượt xem/điểm xếp hạng | Top-N theo mức độ phổ biến | Cần chính sách cập nhật và làm mới |
| Số thứ tự tăng đơn điệu | Thứ tự thêm mới duy nhất | Cần cấp số nhất quán; không tự đại diện thời gian thực tế |

Khi hai member có cùng score, Redis dùng thứ tự từ điển của member để phân định thứ tự. Quy tắc này có thể dự đoán được, nhưng không nhất thiết tương đương với quy tắc `createdAt DESC, id ASC` mà ứng dụng yêu cầu.

**Lưu ý số học:** score của ZSET là số dấu phẩy động 64-bit. Số nguyên có thể được biểu diễn chính xác đến khoảng `2^53`; nếu dùng số thứ tự dài hạn, phải chú ý giới hạn này. Không ghép timestamp lớn và ID bằng một phép nhân tùy ý rồi giả định mọi giá trị còn chính xác.

## 6. Phân trang theo vị trí (offset/rank pagination) với ZSET

Với trang đánh số từ 0, kích thước `size` và số trang `page`:

```text
start = page * size
stop  = start + size - 1
```

Ví dụ phân trang 3 sản phẩm một trang:

```redis
ZREVRANGE product:order 0 2
ZREVRANGE product:order 3 5
ZREVRANGE product:order 6 8
```

Nếu Redis mới hơn, có thể sử dụng cú pháp thống nhất với `ZRANGE ... REV`:

```redis
ZRANGE product:order 0 2 REV
```

Cần phân biệt: `ZREVRANGE` trả danh sách **ID**, không trả cả `Product`. Ứng dụng phải tải những entity đó qua Repository rồi ghép lại theo đúng thứ tự ID lấy từ ZSET.

### Ví dụ service kết hợp Repository và ZSET

Ví dụ sau dùng Spring Data Redis với `StringRedisTemplate`, `CrudRepository` và Java 17. Để đơn giản, giả sử ứng dụng tạo ID duy nhất và danh sách có thứ tự theo số thứ tự được cấp khi thêm.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private static final String ORDER_KEY = "product:order";
    private static final String SEQ_KEY = "product:order:seq";
    private static final long MAX_EXACT_SCORE = 9_007_199_254_740_991L;

    private final ProductRepository products;
    private final StringRedisTemplate redis;

    public ProductCatalogService(
            ProductRepository products,
            StringRedisTemplate redis) {
        this.products = products;
        this.redis = redis;
    }

    public void add(Product product) {
        // Demo: một ID chỉ được thêm mới một lần.
        Long seq = redis.opsForValue().increment(SEQ_KEY);

        if (seq == null || seq < 1 || seq > MAX_EXACT_SCORE) {
            throw new IllegalStateException("Invalid sequence number");
        }

        products.save(product);

        // ZSET chỉ lưu ID và thứ tự; entity vẫn do Repository quản lý.
        redis.opsForZSet().add(
            ORDER_KEY,
            product.getId(),
            seq.doubleValue()
        );
    }

    public ProductPage readPage(int page, int size) {
        if (page < 0 || size <= 0 || size > 100) {
            throw new IllegalArgumentException("Invalid page or size");
        }

        long start = Math.multiplyExact((long) page, (long) size);
        long stop = Math.addExact(start, size - 1L);

        Set<String> ids = redis.opsForZSet()
            .reverseRange(ORDER_KEY, start, stop);

        Long zcard = redis.opsForZSet().zCard(ORDER_KEY);
        long total = zcard == null ? 0 : zcard;

        if (ids == null || ids.isEmpty()) {
            return new ProductPage(List.of(), total, page, size);
        }

        // findAllById không được giả định giữ thứ tự đầu vào.
        Map<String, Product> byId = new HashMap<>();
        products.findAllById(ids).forEach(
            product -> byId.put(product.getId(), product)
        );

        List<Product> ordered = new ArrayList<>();

        for (String id : ids) {
            Product product = byId.get(id);

            if (product != null) {
                ordered.add(product);
            }
        }

        return new ProductPage(
            List.copyOf(ordered),
            total,
            page,
            size
        );
    }

    public record ProductPage(
        List<Product> items,
        long totalIndexed,
        int page,
        int size
    ) { }
}
```

**Giới hạn có chủ ý của ví dụ:** `add()` bao gồm nhiều lệnh Redis/Repository liên tiếp và chưa có cơ chế giao dịch đồng bộ hay dọn đối soát. Phần sau giải thích cách xử lý cho production. `totalIndexed` là kích thước ZSET, không mặc nhiên là tổng số entity hiện còn tồn tại nếu chỉ mục có ID cũ.

Khi gọi `readPage(0, 20)`, hệ thống chỉ chọn tối đa 20 ID trong Sorted Set rồi nạp các entity tương ứng. Chi phí xử lý thường tốt hơn nhiều so với tải hết dữ liệu rồi `sort()` trong Java.

### Chi phí của phân trang theo rank

Với ZSET, tìm đoạn theo rank thường có chi phí gần `O(log N + M)`, trong đó `M` là số member được trả về. Sau đó cần thêm chi phí tải `M` entity và chuyển chúng thành object Java.

Không nên suy diễn rằng mọi loại offset đều có cùng chi phí: lệnh phân trang theo **rank** khác với truy vấn theo **score** kết hợp `LIMIT offset count`, nơi offset lớn có thể cần bỏ qua nhiều phần tử hơn. Dù truy xuất theo rank hiệu quả, người dùng đi qua nhiều trang vẫn chịu vấn đề dữ liệu thay đổi làm dịch chuyển vị trí.

## 7. Vì sao offset pagination có thể bị lặp hoặc bỏ sót?

Giả sử danh sách sắp theo score giảm dần:

```text
Trước khi thêm:
Trang 1: [p105, p104, p103]
Trang 2: [p102, p101, p100]

Sau khi client lấy Trang 1, có p106 mới:
Danh sách: [p106, p105, p104, p103, p102, p101, p100]

Client tiếp tục lấy Trang 2 theo offset=3:
Trang 2: [p103, p102, p101]
             ^
             p103 lặp lại từ Trang 1
```

Điều này không phải lỗi riêng của Redis. Offset pagination luôn bị ảnh hưởng khi dữ liệu thay đổi giữa các request. Nếu xóa phần tử ở đầu danh sách, client còn có thể bỏ sót một phần tử.

Khi API có lưu lượng lớn và dữ liệu thêm mới liên tục, **cursor/keyset pagination** thường phù hợp hơn so với các trang đánh số.

## 8. Phân trang bằng cursor dựa trên score

Một cách đơn giản là dùng số thứ tự **duy nhất và tăng đơn điệu** làm score:

```text
product:order
  p106 -> 106
  p105 -> 105
  p104 -> 104
  p103 -> 103
  p102 -> 102
```

Trang đầu: lấy tối đa ba sản phẩm có score cao nhất.

```redis
ZRANGE product:order +inf -inf BYSCORE REV LIMIT 0 3 WITHSCORES
```

Giả sử trả về `p106 (106)`, `p105 (105)`, `p104 (104)`. Cursor kế tiếp là score `104`. Trang sau yêu cầu **score nhỏ hơn 104**, loại trừ mốc:

```redis
ZRANGE product:order (104 -inf BYSCORE REV LIMIT 0 3 WITHSCORES
```

Redis dùng dấu `(` trước giá trị score để chỉ khoảng mở, nghĩa là **không bao gồm** `104`. Khi có `p107` mới chèn vào đầu bảng, trang sau vẫn bắt đầu dưới mốc `104` nên không lặp lại những sản phẩm đã đọc ở trang đầu.

Luồng API có thể là:

```text
GET /products?size=3
  -> items: [p106, p105, p104]
  -> nextCursor: "104"

GET /products?size=3&before=104
  -> items: [p103, p102, p101]
  -> nextCursor: "101"
```

### Quy tắc để cursor hoạt động đúng

- **Thứ tự phải ổn định và xác định rõ.** Với score duy nhất, một giá trị score là đủ để lấy phần trước/sau. Với score trùng, cursor cần mang thêm member và logic xử lý tie-break.
- **Không thể giả định score luôn bất biến.** Khi cập nhật giá, điểm, lượt xem hoặc thứ hạng, một item có thể chuyển vị trí giữa hai lần gọi; cursor không tự tạo snapshot.
- **Không nên dùng score chứa timestamp làm cursor duy nhất nếu nhiều item chung timestamp.** Chỉ dùng khoảng mở theo timestamp sẽ bỏ sót các item cùng score.
- **Số thứ tự đơn điệu phù hợp cho “mới được thêm vào”**, nhưng không thay thế lịch sử sắp xếp theo `updatedAt`, `price` hay nhiều trường.
- **Cursor cần được ràng buộc với filter và kiểu sort.** Cursor của `category=book` không được dùng tùy tiện cho `category=toy`.
- Có thể lấy `size + 1` item để xác định `hasNext`, rồi chỉ trả `size` item và cursor tương ứng.

Với Redis có dữ liệu rất lớn hoặc cập nhật liên tục, cursor dựa trên một chỉ mục có thứ tự giúp giảm nhiều vấn đề của offset, nhưng việc xóa, cập nhật và đồng bộ dữ liệu vẫn cần chính sách rõ ràng.

## 9. Đọc đúng thứ tự sau khi tải entity

Một lỗi tinh vi là lấy ID từ ZSET đúng thứ tự nhưng nhận danh sách entity từ Repository rồi trả về luôn:

```text
ZSET trả:          [p104, p103, p102]
findAllById trả:   [p102, p104, p103]  (thứ tự không được bảo đảm)
API trả sai:       [p102, p104, p103]
```

Đúng hơn:

1. Lấy chuỗi ID theo thứ tự mong muốn.
2. Đọc dữ liệu cho các ID đó.
3. Tạo ánh xạ `id -> entity`.
4. Duyệt lại chuỗi ID, lấy entity tương ứng và bỏ qua entity đã mất.

Đây là lý do ví dụ service dùng `Map` rồi tạo `List<Product> ordered` theo danh sách ID lấy từ ZSET.

Ngoài ra, khi một ID nằm trong ZSET nhưng entity gốc đã bị xóa hoặc hết TTL, số lượng item thực nhận có thể nhỏ hơn `size`. Hệ thống có thể dùng cách **đọc bù** một số ID kế tiếp và loại bỏ các ID không còn hợp lệ; cần giới hạn số vòng đọc để tránh request kéo dài nếu chỉ mục quá bẩn.

## 10. Lọc theo điều kiện kết hợp sắp xếp

Redis Repository có thể tìm theo `@Indexed`, nhưng điều kiện “sản phẩm loại book, mới nhất trước” cần kết hợp **membership** với **ordering**.

Có ba thiết kế phổ biến.

### 10.1. Một ZSET riêng cho mỗi nhóm truy vấn quan trọng

Nếu API chủ yếu có:

```text
GET /products?category=book&sort=createdAt_desc
GET /products?category=toy&sort=createdAt_desc
```

Có thể duy trì:

```text
product:order:all
product:order:category:book
product:order:category:toy
```

Lệnh minh họa:

```redis
ZADD product:order:category:book 101 p101 104 p104
ZADD product:order:category:toy 102 p102 103 p103

ZREVRANGE product:order:category:book 0 19
```

**Ưu điểm:** truy xuất theo nhóm và thứ tự định sẵn tương đối nhanh.

**Đổi lại:** mỗi lần thêm, sửa category, đổi score hoặc xóa sản phẩm phải cập nhật đúng mọi index liên quan. Số lượng cấu trúc tăng theo các cách lọc/sort được hỗ trợ.

### 10.2. Lấy ID từ tập chỉ mục rồi lọc trong ứng dụng

Nếu tập ứng viên đã nhỏ và được giới hạn rõ ràng, có thể:

1. Dùng phương thức Repository như `findByCategory("book")`.
2. Sắp xếp các item trong ứng dụng.
3. Lấy một trang.

Cách này đơn giản nhưng quay lại giới hạn tải toàn bộ tập ứng viên. Phù hợp với nhóm nhỏ, không thích hợp cho trường hợp có hàng trăm nghìn kết quả.

### 10.3. Bộ máy truy vấn chuyên dụng

Nếu API yêu cầu kết hợp tùy ý:

- `category IN (...)`;
- khoảng giá, tồn kho, nhãn và nhiều điều kiện;
- sắp xếp theo `price ASC` hoặc `createdAt DESC`;
- tìm kiếm toàn văn;
- phân trang sâu, thống kê tổng và nhiều kiểu sort động;

thì việc tự duy trì hàng chục ZSET sẽ tăng chi phí cập nhật và rủi ro thiếu nhất quán. Cân nhắc **Redis Search** nếu hạ tầng hỗ trợ, hoặc một hệ quản trị truy vấn phù hợp như PostgreSQL/OpenSearch tùy yêu cầu. Redis Repository thông thường không tự chuyển mọi phương thức truy vấn thành Redis Search.

## 11. Sắp xếp nhiều trường, null và thay đổi score

Trong SQL, ta có thể yêu cầu:

```sql
ORDER BY created_at DESC, id ASC
```

Trong ZSET, **mỗi member có một score**. Sắp xếp theo hai hoặc nhiều thuộc tính tùy ý không tự nhiên như một mệnh đề `ORDER BY`. Có thể chọn một trong các chiến lược:

- Nếu trường thứ hai chỉ dùng để phá hòa, quy định cách mã hóa an toàn và deterministic, hoặc áp dụng tie-break rõ ràng tại tầng truy vấn.
- Nếu dữ liệu nhỏ, lấy nhóm ứng viên rồi sort trong ứng dụng.
- Nếu có ít cách sort cố định, duy trì nhiều chỉ mục (ví dụ một ZSET cho giá, một cho thời gian).
- Nếu nhiều điều kiện/sort động, chuyển nhu cầu truy vấn sang một engine hỗ trợ.

Không nên cộng/nhân score để nhét nhiều trường vào một số `double` khi chưa tính phạm vi giá trị, độ chính xác và quy tắc tie-break. Một phép mã hóa mất chính xác có thể đảo thứ tự những item tưởng như khác nhau.

### Sắp xếp theo trường thay đổi

Ví dụ `priceInCents`:

```redis
ZADD product:price:asc 1999 p101
ZADD product:price:asc 2999 p102
ZRANGE product:price:asc 0 19
```

Sau khi đổi giá sản phẩm `p101` lên 3.999 cents, phải cập nhật:

```redis
ZADD product:price:asc 3999 p101
```

`ZADD` cập nhật score của member đã có; nếu quên cập nhật, thứ tự trong ZSET không phản ánh dữ liệu mới của entity. Việc cập nhật entity và ZSET là hai thao tác có thể thất bại riêng rẽ.

## 12. `Page` và bài toán đếm tổng số chính xác

Nhiều giao diện yêu cầu:

```json
{
  "items": ["p104", "p103"],
  "page": 0,
  "size": 2,
  "totalElements": 42000,
  "totalPages": 21000
}
```

Với một ZSET toàn phần, `ZCARD` trả số member trong chỉ mục:

```redis
ZCARD product:order
```

Nhưng `ZCARD` đếm **member**, không kiểm tra liệu mỗi ID còn tương ứng với entity đang tồn tại hay không. Nếu chỉ mục có ID cũ, con số này không phải tổng số entity hợp lệ. Nếu dữ liệu đang được ghi đồng thời, count lấy trước và kết quả trang lấy sau còn có thể phản ánh hai mốc thời gian khác nhau.

Một số lựa chọn thiết kế:

| Yêu cầu UI | Lựa chọn |
| --- | --- |
| Phải hiển thị “Trang 1/100” | Cần count đáng tin cậy và quy tắc nhất quán |
| Nút “Xem thêm” hoặc cuộn vô hạn | Dùng `Slice`/cursor, chỉ cần biết còn phần tử tiếp |
| Bảng xếp hạng | ZSET theo score, thường quan tâm top N hơn tổng số trang |
| Dữ liệu lớn, cập nhật liên tục | Ưu tiên cursor và tránh đếm chính xác trên mọi request |

Nếu buộc phải trả số trang cuối cùng, có thể tính từ tổng:

```java
long totalPages = total == 0
    ? 0
    : 1 + (total - 1) / size;
```

Nhưng chỉ nên gọi là tổng chính xác khi **nguồn count có đúng ngữ nghĩa và được duy trì nhất quán**.

## 13. TTL, xóa và chỉ mục bị cũ

Đây là giới hạn rất quan trọng khi kết hợp Redis Repository với ZSET riêng.

Giả sử lưu `Product p101` với TTL 30 phút:

```text
T0:   Repository lưu p101; ZSET chứa p101
T+30: entity p101 hết hạn
T+31: ZSET vẫn có thể còn member p101
```

Redis **không tự hiểu** rằng member trong ZSET bên ngoài phải được xóa khi khóa entity hết hạn. Dù Repository có cơ chế theo dõi expiration và secondary indexes, **ZSET do ứng dụng tự tạo vẫn cần cơ chế bảo trì riêng**.

Các chiến lược thường kết hợp:

1. Khi xóa sản phẩm theo nghiệp vụ, gọi `ZREM` cho các chỉ mục liên quan.
2. Khi cập nhật trường quyết định phân nhóm/sort, xóa khỏi chỉ mục cũ và ghi vào chỉ mục mới.
3. Trong lúc nạp entity, phát hiện ID không còn tồn tại, bỏ qua khi trả kết quả và có thể xếp lịch dọn chỉ mục.
4. Chạy công việc **đối soát định kỳ** để sửa thành viên thiếu/thừa nếu cần count và thứ tự chính xác.
5. Có thể dùng Redis keyspace notifications như tín hiệu dọn sớm, nhưng đây là Pub/Sub và có thể bị trễ hoặc mất khi ứng dụng ngắt kết nối; không nên là cơ chế phục hồi duy nhất.

### Minh họa xóa dữ liệu

```java
public void delete(String productId) {
    products.deleteById(productId);
    redis.opsForZSet().remove("product:order", productId);
}
```

Mẫu này dễ hiểu nhưng chưa bảo đảm nguyên tử: tiến trình có thể dừng giữa hai thao tác. Nếu cần nhất quán mạnh, phải thiết kế chung cơ chế ghi, retry/idempotency và đối soát theo mức rủi ro thực tế.

### “Đọc bù” khi gặp ID không tồn tại

Giả sử page size = 3 và ZSET trả `[p103, p102, p101]`, nhưng `p102` đã hết TTL. Nếu chỉ loại bỏ `p102`, client nhận hai item. Nếu contract yêu cầu đủ ba item khi còn dữ liệu, hãy lấy thêm ID ở vị trí kế tiếp và kiểm tra. Tránh vòng lặp vô hạn bằng giới hạn số ID quét/số lượt nạp, và lên lịch dọn index theo nền.

## 14. Tính nhất quán, đồng thời và giao dịch

Một thao tác ghi có thể gồm:

```text
Repository.save(product)
         |
         +--> HSET entity
         +--> cập nhật các index do Repository quản lý
         |
         +--> ZADD custom order index
```

Nếu ứng dụng bị dừng sau khi lưu entity nhưng trước `ZADD`, entity tồn tại song không hiện trong trang danh sách. Ngược lại, nếu ghi index trước mà lưu entity thất bại, ZSET sẽ có ID không tồn tại.

### Những tình huống cần tính đến

- **Create:** làm sao tránh một product ID được gán score nhiều lần khi request retry?
- **Update:** khi đổi category, xóa khỏi index cũ và thêm vào index mới theo trình tự nào?
- **Delete:** có chấp nhận chỉ mục còn phần tử rác trong một khoảng ngắn không?
- **TTL:** entity biến mất mà callback ứng dụng không chạy thì dọn index ra sao?
- **Concurrent writes:** hai luồng cùng thay đổi giá hoặc thứ tự, bản cập nhật nào thắng?
- **Replica reads:** nếu đọc từ replica có độ trễ, entity và index có thể phản ánh thời điểm khác nhau.

Các cách xử lý phụ thuộc độ nghiêm ngặt của sản phẩm:

- **Dữ liệu hiển thị best effort:** ghi idempotent, lọc ID rác khi đọc, đối soát định kỳ.
- **Yêu cầu độ chính xác cao:** gom các thay đổi liên quan trong cùng ranh giới lưu trữ/atomic operation khi khả thi; dùng transaction/Lua theo đúng mô hình key Redis và quy tắc cluster; duy trì cơ chế retry và đối soát.
- **Nghiệp vụ cần transaction nhiều entity phức tạp:** cân nhắc nguồn dữ liệu giao dịch chuyên dụng, dùng Redis làm cache hoặc read model.

Không nên giả định đặt `@Transactional` lên một phương thức gọi cả Repository và `StringRedisTemplate` sẽ tự động biến tất cả thao tác liên quan thành một giao dịch Redis nguyên tử. Hành vi thực tế còn tùy transaction manager, cấu hình Spring Data Redis và các lệnh được sử dụng.

## 15. Redis Cluster và chi phí truy vấn thực tế

Trong Redis Cluster, các key được phân phối theo hash slot. Khi ứng dụng cần dùng thao tác nhiều key (transaction, Lua, phép giao/chập set hoặc lệnh đặc thù), ràng buộc cùng hash slot có thể ảnh hưởng thiết kế index.

Ví dụ:

```text
product:order                  -> một slot
product:p101                   -> slot khác
product:p102                   -> slot khác nữa
```

Đọc riêng từng key có thể vẫn thực hiện qua client tương ứng, nhưng không thể mặc nhiên thực hiện mọi lệnh đa key một cách nguyên tử trên các slot khác nhau.

Hash tag (cặp ngoặc nhọn) có thể ép những key liên quan vào cùng slot:

```text
product:{category-book}:order
product:{category-book}:metadata
```

Tuy nhiên, đặt toàn bộ dữ liệu ứng dụng vào cùng một hash tag có thể dồn tải về một slot/node, làm mất lợi ích phân phối. Hãy thiết kế theo các thao tác thực sự cần cùng slot, thay vì gom mọi key.

### Độ phức tạp không chỉ nằm ở lệnh ZSET

Một request trang có thể trải qua:

```text
Client -> API
          |
          +--> Redis: lấy ID từ ZSET
          +--> Redis: đọc N hash entity
          +--> Java: ghép đúng thứ tự
          +--> Client: trả JSON
```

Ngay cả khi truy vấn ZSET nhanh, request vẫn có thể chậm vì quá nhiều lần round-trip, serialization, entity có kích thước lớn hoặc thao tác đọc trên nhiều node. Khi cần tối ưu, đo riêng thời gian lấy ID, nạp entity và chuyển đổi dữ liệu. Có thể dùng batching/pipelining ở những đoạn thích hợp sau khi hiểu đường đi của Repository.

## 16. Một thiết kế API phân trang rõ ràng

Một API thực tế nên cho biết **kiểu phân trang nào được hỗ trợ**, thay vì chỉ nhận `page`, `sort` rồi ngầm hứa thực thi mọi tổ hợp.

### Offset khi cần chuyển tới số trang

```http
GET /api/products?page=0&size=20&sort=createdAt,desc
```

Response ví dụ:

```json
{
  "items": [
    {"id": "p104", "name": "Book A"},
    {"id": "p103", "name": "Book B"}
  ],
  "page": 0,
  "size": 20,
  "totalIndexed": 42000
}
```

`totalIndexed` nên được đặt tên đúng bản chất khi count lấy từ ZSET và có thể lệch với số entity hợp lệ.

### Cursor khi dữ liệu thay đổi thường xuyên

```http
GET /api/products?size=20
GET /api/products?size=20&cursor=opaque-token
```

Response:

```json
{
  "items": [
    {"id": "p104", "name": "Book A"},
    {"id": "p103", "name": "Book B"}
  ],
  "nextCursor": "opaque-token",
  "hasNext": true
}
```

`opaque-token` có thể chứa score cuối, kiểu sort, điều kiện filter và phiên bản schema, được mã hóa phù hợp để client không cần hiểu cấu trúc Redis nội bộ. Khi giải mã, server phải xác thực giá trị, kích thước trang và phạm vi truy vấn. Nếu score là dữ liệu nhạy cảm hoặc token cần chống sửa, bổ sung chữ ký/xác thực phù hợp.

### Sắp xếp nào được phép?

Thay vì chấp nhận tùy ý tên trường, khai báo rõ:

```text
sort=created_desc   -> ZSET product:order
sort=price_asc      -> ZSET product:price:asc
sort=popular_desc   -> ZSET product:popularity
```

Với sort chưa có index, API có thể trả lỗi validation hoặc chuyển yêu cầu sang backend tìm kiếm khác; không âm thầm tải toàn bộ Redis để sắp xếp mọi lần.

## 17. Chọn giải pháp theo quy mô và yêu cầu

| Bối cảnh | Phương án khởi đầu | Giới hạn cần lưu ý |
| --- | --- | --- |
| Tập dữ liệu rất nhỏ, số lượng giới hạn | Repository `findAll`/`findBy...` rồi sort trong Java | Chi phí tăng theo toàn bộ tập ứng viên |
| Một danh sách top N / mới nhất | ZSET + Repository để hydrate | Phải duy trì score và xóa index |
| Danh sách có vài bộ lọc/sort cố định | Mỗi filter/sort quan trọng có chỉ mục ZSET riêng | Tăng số index và thao tác ghi |
| Dữ liệu thêm liên tục, infinite scroll | Cursor/keyset theo thứ tự ổn định | Xử lý score trùng, item bị cập nhật/xóa |
| Muốn chuyển tới trang bất kỳ | Offset/rank trên ZSET | Có thể lặp/bỏ sót khi dữ liệu thay đổi |
| Lọc đa điều kiện, nhiều sort động | Redis Search hoặc hệ truy vấn khác | Cần vận hành index và lựa chọn engine |
| Dữ liệu giao dịch, quan hệ phức tạp | Cơ sở dữ liệu giao dịch phù hợp | Redis làm cache/read model khi cần |

### Các tiêu chí đánh giá khi đưa vào production

**Độ lớn tập dữ liệu.** Hãy ước tính tổng số entity, số ID trong mỗi index và số phần tử cho một trang. Đừng chỉ nhìn latency khi có vài trăm bản ghi thử nghiệm.

**Độ biến động.** Nếu có nhiều write hơn read, chi phí duy trì nhiều ZSET có thể đáng kể. Nếu read nhiều hơn write và sort cố định, ZSET thường là lựa chọn hợp lý.

**Nhất quán.** Cần quyết định UI chấp nhận count gần đúng hay phải chính xác, có thể hiển thị thiếu item tạm thời hay không, và có cần kết quả bất biến giữa các trang không.

**Truy vấn tương lai.** Nếu product roadmap có lọc động, tìm kiếm toàn văn hoặc thống kê, nên chọn một query engine phù hợp trước khi xây quá nhiều custom index.

## 18. Các lỗi thường gặp

### Lỗi 1: “Có `PageRequest` nghĩa là Redis sẽ LIMIT”

`PageRequest` chỉ biểu diễn một yêu cầu. Module lưu trữ phải hỗ trợ và thực hiện; nếu API không phù hợp, kết quả có thể là lỗi hoặc truy vấn tốn kém. Không suy luận khả năng Redis từ thói quen dùng Spring Data JPA.

### Lỗi 2: Dựa vào thứ tự của tập ID

Một index membership không phải danh sách đã sắp xếp. Muốn thứ tự xác định phải định nghĩa comparator phù hợp hoặc dùng cấu trúc duy trì thứ tự như ZSET.

### Lỗi 3: Lấy ID bằng ZSET nhưng làm mất thứ tự khi `findAllById`

Dùng ánh xạ theo ID rồi ghép lại theo thứ tự trả về từ ZSET. Nếu không, API có thể trả sản phẩm sai thứ tự dù ZSET đúng.

### Lỗi 4: Trả `ZCARD` như tổng số sản phẩm đang sống

Nếu member trong ZSET không được dọn khi entity hết TTL hoặc bị xóa, `ZCARD` đếm cả ID cũ. Cần ghi rõ ngữ nghĩa count và duy trì index.

### Lỗi 5: Dùng thời gian mili giây làm cursor duy nhất

Hai sản phẩm có thể cùng timestamp; truy vấn trang sau với khoảng mở sẽ bỏ sót những item khác có cùng score. Dùng tie-break đầy đủ hoặc thứ tự đơn điệu duy nhất.

### Lỗi 6: Cập nhật entity nhưng quên cập nhật ZSET

Một trường thay đổi như `price` hoặc `popularity` phải cập nhật score của đúng các index. Nên tập trung các thao tác ghi vào cùng một service hoặc pipeline thay đổi có quy tắc rõ ràng.

### Lỗi 7: Tin rằng keyspace notifications sẽ giữ chỉ mục nhất quán tuyệt đối

Sự kiện Redis hết hạn có thể đến muộn hoặc mất do Pub/Sub; dọn index chỉ bằng callback sẽ bỏ sót. Cần đối soát nếu dữ liệu đúng là yêu cầu thiết yếu.

## 19. Bài thực hành: thiết kế danh sách sản phẩm có filter và sort

Giả sử hệ thống có 2 triệu sản phẩm, cần:

- Xem 20 sản phẩm mới nhất, có “Load more”.
- Lọc theo một category.
- Hiển thị top 100 sản phẩm được xem nhiều.
- Xóa sản phẩm hết hạn khỏi danh sách.

Thiết kế đề xuất:

```text
                              +----------------------+
                              | Spring REST API      |
                              +----------+-----------+
                                         |
                  +----------------------+--------------------+
                  |                      |                    |
                  v                      v                    v
           product:order       product:category:X:order   product:views
           ZSET: ID/seq        ZSET: ID/seq              ZSET: ID/views
                  |                      |                    |
                  +----------------------+--------------------+
                                         |
                                         v
                                 danh sách ID
                                         |
                                         v
                             ProductRepository.findAllById
                                         |
                                         v
                             ghép entity theo thứ tự ID
                                         |
                                         v
                                    response
```

Quy tắc vận hành:

1. Dùng một thứ tự sinh số duy nhất cho các sản phẩm mới; áp dụng cursor score cho `created_desc`.
2. Khi thêm sản phẩm, ghi entity và đúng ZSET toàn cục/theo category.
3. Khi đổi category, chuyển member giữa các ZSET category.
4. Khi tăng lượt xem, cập nhật score trong `product:views` theo quy tắc thống nhất.
5. Khi xóa hoặc TTL làm entity không còn, đường đọc bỏ ID thiếu; công việc đối soát sửa index.
6. Chỉ expose các kiểu filter/sort đã có index; yêu cầu truy vấn rộng hơn phải dùng query engine khác.

Một bảng xếp hạng top N có thể lấy bằng:

```redis
ZREVRANGE product:views 0 99 WITHSCORES
```

Danh sách theo category có thể lấy bằng:

```redis
ZRANGE product:category:book:order +inf -inf BYSCORE REV LIMIT 0 20 WITHSCORES
```

Đây là những lệnh Redis tiêu biểu cho phần **chọn ID theo thứ tự**. Để API hoàn chỉnh, ứng dụng còn phải nạp entity, lọc ID mất, xử lý cursor, đảm bảo phân quyền và cập nhật index khi dữ liệu thay đổi.

## 20. Câu hỏi thường gặp

**Có thể dùng `Pageable` trực tiếp trong Redis Repository không?**

Phải kiểm tra theo phiên bản Spring Data Redis, kiểu Repository và kiểu query đang dùng. Không giả định hành vi giống Spring Data JPA hoặc rằng thao tác được xử lý bằng index tại Redis. Nếu yêu cầu là paging/sort hiệu quả theo một trường nhất định, ZSET hoặc query engine chuyên dụng thường cho khả năng kiểm soát rõ hơn.

**`@Indexed` có giúp `ORDER BY` nhanh hơn không?**

`@Indexed` chủ yếu phục vụ tìm các entity thỏa điều kiện tương ứng. Nó không tự tạo thứ tự `createdAt DESC` hay `price ASC` trên tập kết quả.

**Vì sao `findByCategory(...)` trả kết quả không theo thứ tự như mong đợi?**

Vì membership index và thứ tự nghiệp vụ là hai việc khác nhau. Cần định nghĩa rõ thứ tự, không dựa vào thứ tự ngẫu nhiên của các ID hoặc container.

**ZSET có lưu toàn bộ `Product` được không?**

Thực tế nên lưu **ID** làm member và một score dùng để sắp xếp. Repository vẫn là nơi quản lý entity; ứng dụng hydrate ID thành object khi cần. Cách này tránh nhân bản toàn bộ payload vào các chỉ mục.

**Nên dùng `Page` hay `Slice` cho ứng dụng di động?**

Với cuộn vô hạn và dữ liệu thay đổi nhanh, cursor cùng metadata `hasNext` thường phù hợp hơn; không bắt buộc đếm tổng trên mỗi lần tải. `Page` hữu ích khi UI thực sự cần số trang và tổng số chính xác.

**Nếu client yêu cầu trang 10.000 thì sao?**

Truy xuất theo rank trên ZSET vẫn có thể làm được, nhưng còn vấn đề dữ liệu thay đổi và tổng chi phí lấy/hydrate. API nên đặt giới hạn kích thước trang, xem xét giới hạn số trang, hoặc chuyển sang cursor cho hành vi duyệt liên tục.

**Có thể sắp xếp đồng thời theo thời gian và ID không?**

Có thể thiết kế quy tắc tie-break, nhưng ZSET chỉ có một score cho mỗi member. Nếu score trùng, Redis có thứ tự từ điển theo member; cần chứng minh quy tắc đó phù hợp với nghiệp vụ hoặc thiết kế cursor hai thành phần. Không nên mặc định timestamp duy nhất.

**Redis Search và Redis Repository là cùng một công cụ?**

Không. Redis Repository là cơ chế ánh xạ entity/key-value của Spring Data Redis. Redis Search là một khả năng truy vấn/tìm kiếm riêng trên hạ tầng Redis có hỗ trợ; muốn dùng phải thiết kế index và client/API thích hợp.

## 21. Ghi nhớ

- **Repository trả về entity và hỗ trợ một số truy vấn indexed**, nhưng không phải bộ máy SQL với `ORDER BY`/`OFFSET` tổng quát.
- **`Pageable` và `Sort` là các abstraction**, không bảo đảm Redis có execution plan phù hợp.
- **ZSET là cấu trúc cốt lõi** khi cần duy trì thứ tự trên tập ID và lấy top N, trang theo rank hoặc cursor theo score.
- **Offset** tiện cho trang đánh số, nhưng có thể trùng/bỏ sót khi dữ liệu đổi; **cursor** tốt hơn cho danh sách thay đổi nhanh nếu có thứ tự ổn định.
- **Index phải được duy trì khi create/update/delete/expire**; đừng nhầm `ZCARD` với số entity đang sống.
- **Bài toán nhiều filter/sort động** thường nên chuyển sang query engine phù hợp thay vì tăng vô hạn số custom ZSET.

## Tài liệu tham khảo

- [Spring Data Redis Reference – Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis Reference – Redis Repositories Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis Reference – Repository Query Methods](https://docs.spring.io/spring-data/redis/reference/repositories/query-methods-details.html)
- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Redis – Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/)
- [Redis – ZRANGE](https://redis.io/docs/latest/commands/zrange/)
- [Redis – ZADD](https://redis.io/docs/latest/commands/zadd/)
