# Chi phí bộ nhớ của chỉ mục và tập kết quả trung gian trong Spring Data Redis

## 1. Vì sao chỉ mục làm truy vấn nhanh hơn nhưng có thể tăng RAM?

Redis lưu các cấu trúc dữ liệu phục vụ truy vấn chủ yếu trong bộ nhớ. Với **Spring Data Redis Repository**, một thực thể Java thường được ánh xạ thành Redis Hash. Khi cần tìm theo thuộc tính ngoài ID, ứng dụng có thể khai báo `@Indexed` để Repository duy trì các **secondary index**.

Đổi lại, Redis phải lưu thêm các cấu trúc dữ liệu phụ, và lúc thực thi truy vấn có thể phải kết hợp nhiều tập ID. Nếu ứng dụng trả về hàng chục nghìn thực thể, bộ nhớ của Redis, buffer mạng và Java heap đều có thể tăng đáng kể.

Cần phân biệt ba dạng chi phí:

- **Bộ nhớ thường trú:** Hash gốc, chỉ mục phụ, tập ID của keyspace và metadata phục vụ quản lý index.
- **Bộ nhớ tạm khi truy vấn:** cấu trúc tính giao/hợp, kết quả chưa gửi hết và output buffer.
- **Bộ nhớ ứng dụng:** các ID đã nhận, Hash được giải mã, `List<Entity>` và dữ liệu API đang serialize.

Một index có thể dùng ít RAM trên dữ liệu nhỏ nhưng chiếm rất nhiều RAM khi số thực thể, số giá trị phân biệt hoặc số truy vấn đồng thời tăng. Bài học này tập trung vào cách hiểu, ước lượng, đo đạc và kiểm soát những khoản chi phí đó.

## 2. Từ thực thể Java đến Redis Hash và index Set

Xét thực thể `Article`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("articles")
public class Article {
    @Id
    private String id;

    private String title;

    @Indexed
    private String category;

    @Indexed
    private String status;

    @Indexed
    private String authorId;

    // Constructor, getter và setter thông thường.
}
~~~

Repository tương ứng:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface ArticleRepository extends CrudRepository<Article, String> {
    List<Article> findByCategory(String category);
    List<Article> findByCategoryAndStatus(String category, String status);
}
~~~

Spring Data Redis Repository hỗ trợ một số mẫu truy vấn dựa trên thuộc tính đã lập chỉ mục; các toán tử và cách thực thi cụ thể phụ thuộc phiên bản thư viện. Các phương thức trên minh họa truy vấn theo một và hai điều kiện bằng nhau.

Nếu lưu đối tượng:

~~~java
Article article = new Article(
    "a-101",
    "Giới thiệu Redis",
    "backend",
    "PUBLISHED",
    "u-7"
);
repository.save(article);
~~~

thì về mặt logic Redis có:

~~~text
Key thực thể:
    articles:a-101                  [HASH]
        id       = a-101
        title    = Giới thiệu Redis
        category = backend
        status   = PUBLISHED
        authorId = u-7
        _class   = ...

Các key chỉ mục:
    articles:category:backend       [SET] {a-101, ...}
    articles:status:PUBLISHED       [SET] {a-101, ...}
    articles:authorId:u-7           [SET] {a-101, ...}

Các key quản lý Repository:
    Tập ID trong keyspace, dữ liệu theo dõi index khi cần...
~~~

Mỗi Set chỉ mục chứa **ID các đối tượng phù hợp với một giá trị**. Tên key được trình bày theo quy ước thường gặp; metadata nội bộ và cách mã hóa giá trị có thể thay đổi theo phiên bản/cấu hình. Không nên viết logic nghiệp vụ phụ thuộc tùy tiện vào tất cả key quản lý nội bộ của Repository.

Hai điều quan trọng:

1. Chỉ mục thường **không sao chép toàn bộ Article**. Nó chứa các ID như `a-101` và được dùng để tìm Hash chính.
2. Một ID có thể xuất hiện trong **nhiều Set**. Các membership được lặp lại, cùng với chi phí quản lý key và cấu trúc Set của Redis.

### 2.1. So sánh hai đường truy vấn

~~~text
findById("a-101")
    |
    v
articles:a-101  ->  đọc Hash  ->  Article

findByCategory("backend")
    |
    v
articles:category:backend
    |
    +-- a-101  ->  articles:a-101  ->  Article
    +-- a-105  ->  articles:a-105  ->  Article
    +-- a-117  ->  articles:a-117  ->  Article
    ...
~~~

Tìm theo ID đi thẳng đến key. Tìm theo trường ngoài ID thêm bước đọc index, lấy ID rồi đọc các Hash. Index có thể giảm số Hash cần tìm nhưng phát sinh bộ nhớ lưu index và công xử lý tập kết quả.

## 3. Cấu phần bộ nhớ cần tính

| Thành phần | Ví dụ | Chi phí phát sinh |
|---|---|---|
| Hash gốc | `articles:a-101` | Key, field, value và overhead Hash |
| Index theo từng giá trị | `articles:status:PUBLISHED` | Key Set, bảng thành viên, ID lặp |
| Tập ID keyspace | Tập các ID của `articles` do Repository duy trì | Membership/metadata bổ sung |
| Thông tin theo dõi index | Metadata phục vụ cập nhật và xóa index | Key hoặc dữ liệu quản lý tùy phiên bản |
| Kết quả giao/hợp | ID tìm từ nhiều index | CPU, RAM tạm, phản hồi gửi về client |
| Key kết quả tạm nếu có | `tmp:query:123` do ứng dụng tạo bằng `SINTERSTORE` | Redis key và Set tồn tại đến khi dọn |
| Đối tượng trong JVM | `List<Article>` | Java object, String, collection, buffer |

Có thể hình dung:

~~~text
RAM Redis khi đang phục vụ
  ≈ RAM Hash gốc
  + RAM chỉ mục và metadata
  + RAM phục vụ truy vấn đang chạy
  + RAM buffer, allocator và thành phần hệ thống

RAM ứng dụng Java
  ≈ RAM các ID đã nhận
  + RAM các entity đã dựng lại
  + RAM buffer mạng và phản hồi
  + JVM runtime overhead
~~~

Đây là mô hình giúp phân tích chứ không phải công thức cấp phát byte chính xác. `MEMORY USAGE` của từng key không nhất thiết cộng lại bằng `used_memory_rss` của cả tiến trình Redis; RSS còn chịu ảnh hưởng của allocator, fragmentation và overhead khác.

## 4. Đếm membership và đếm bucket: hai đại lượng khác nhau

Đặt:

- `N` là số thực thể.
- `F` là số trường đơn có `@Indexed`.
- `M_f` là tổng số membership của index trường `f`.
- `V_f` là số giá trị phân biệt của trường `f`.

Nếu mọi thực thể có một giá trị trên mỗi trường indexed, tổng membership xấp xỉ:

~~~text
Tổng membership ≈ N × F
~~~

Số index key theo giá trị lại xấp xỉ:

~~~text
Số bucket Set ≈ V1 + V2 + ... + VF
~~~

Nếu trường có giá trị `null` hoặc chỉ có giá trị ở một phần thực thể, membership của trường đó ít hơn `N`. Nếu index áp dụng được cho các giá trị bên trong collection, một thực thể có thể tạo nhiều membership cho một đường dẫn thuộc tính.

### 4.1. Ví dụ 100.000 thực thể

Giả sử ứng dụng có `100.000` bài viết và bốn index đơn, tất cả thực thể đều có đủ giá trị:

| Trường indexed | Số membership | Số giá trị phân biệt | Số bucket Set |
|---|---:|---:|---:|
| `status` | 100.000 | 3 | 3 |
| `category` | 100.000 | 20 | 20 |
| `authorId` | 100.000 | 5.000 | 5.000 |
| `externalCode` | 100.000 | 100.000 | 100.000 |
| **Tổng** | **400.000** | | **105.023** |

Chỉ mục lưu khoảng **400.000 membership** phân tán qua **105.023 Redis Set**, ngoài 100.000 Hash chính và các cấu trúc quản lý khác. Đây là số liệu giả định để diễn giải, không phải kết quả đo của Redis thật.

Điểm đáng chú ý:

- `status` tạo rất ít Set, nhưng bucket `PUBLISHED` có thể chứa phần lớn ID.
- `externalCode` gần như duy nhất có thể tạo **một Set cho mỗi entity**, khiến overhead của tên key và cấu trúc Set nhỏ cộng dồn rất lớn.
- Hai index có cùng số membership vẫn có dung lượng khác nhau vì **số bucket**, độ dài tên key, độ dài ID, encoding và phân bố thành viên khác nhau.

Không thể chỉ lấy số membership rồi gán một số byte cố định cho mọi Redis Set.

### 4.2. Thuộc tính đa trị tạo thêm membership

Giả sử mỗi Article có nhiều tag và phiên bản mapping đang dùng hỗ trợ index các giá trị của collection:

~~~text
a-101: tags = [redis, spring, backend]
a-102: tags = [redis, performance]

Các quan hệ index logic:
    redis       -> {a-101, a-102}
    spring      -> {a-101}
    backend     -> {a-101}
    performance -> {a-102}
~~~

Hai thực thể tạo **năm membership** cho index tag. Nếu trung bình mỗi thực thể có `r` giá trị được index, riêng trường này có thể cần khoảng `N × r` membership. Cần xác nhận mapping collection/property path của phiên bản Spring Data Redis đang dùng trước khi áp dụng một phép tính cụ thể.

### 4.3. Độ dài ID và tên key không miễn phí

~~~text
ID ngắn: a-101
ID dài:  28ef9e31-5948-44e6-a6d0-bba720114d19
~~~

Nếu một ID xuất hiện trong năm index, dữ liệu thành viên của nó được giữ ở nhiều cấu trúc. Việc dùng ID dài có thể khiến tổng payload membership tăng đáng kể, nhất là ở quy mô hàng triệu phần tử.

Tương tự, một key `articles:status:PUBLISHED` có byte overhead khác một tên rất dài mang nhiều tiền tố và property path. Không nên hy sinh khả năng quản trị chỉ để rút ngắn vài ký tự; hãy ưu tiên đo thực tế rồi mới tối ưu khi cần.

## 5. Redis Set dùng bộ nhớ ra sao?

Redis không có một định mức cố định như “mỗi phần tử Set = 32 byte”. Cấu trúc dữ liệu và encoding thay đổi theo giá trị, số phần tử và cấu hình Redis.

Ví dụ:

- Một Set toàn giá trị số nguyên nhỏ có thể dùng biểu diễn gọn `intset`.
- Một Set chứa nhiều ID dạng String thường cần cấu trúc băm với chi phí quản lý riêng.
- Một Set chỉ có một thành viên vẫn cần key và cấu trúc Set.
- Khi cấu trúc được resize hoặc đổi encoding, bộ nhớ có thể tăng theo nấc thay vì tăng đều từng phần tử.

Đo trên Redis thật bằng các lệnh:

~~~redis
TYPE articles:status:PUBLISHED
SCARD articles:status:PUBLISHED
MEMORY USAGE articles:status:PUBLISHED
OBJECT ENCODING articles:status:PUBLISHED
~~~

Ý nghĩa:

- `TYPE`: xác nhận key là Set.
- `SCARD`: số thành viên trong Set.
- `MEMORY USAGE`: số byte ước lượng Redis cấp phát để giữ key/value.
- `OBJECT ENCODING`: cách biểu diễn nội bộ của value.

Có thể lấy mẫu kỹ hơn cho collection:

~~~redis
MEMORY USAGE articles:status:PUBLISHED SAMPLES 0
~~~

`SAMPLES 0` yêu cầu xem xét đầy đủ các thành phần của collection khi ước tính; với key lớn, nên cân nhắc chi phí đo và tránh lạm dụng lúc hệ thống đang chịu tải. Đo một số bucket **nhỏ, trung bình, rất lớn** thường có giá trị hơn việc giả định một kích thước byte/member áp dụng cho mọi bucket.

## 6. Tập kết quả trung gian khi truy vấn nhiều điều kiện

Giả sử ba Set chỉ mục:

~~~text
articles:category:backend   = {a-1, a-2, a-3, a-4, a-5}
articles:status:PUBLISHED   = {a-2, a-4, a-6, a-8}
articles:authorId:u-7       = {a-2, a-5, a-9}
~~~

Nếu query là **backend AND PUBLISHED**, tập ID phù hợp bằng giao:

~~~text
{a-1, a-2, a-3, a-4, a-5}
             ∩
{a-2, a-4, a-6, a-8}
             =
         {a-2, a-4}
~~~

Nếu query là **backend OR PUBLISHED**, tập ID phù hợp bằng hợp:

~~~text
{a-1, a-2, a-3, a-4, a-5}
             ∪
{a-2, a-4, a-6, a-8}
             =
{a-1, a-2, a-3, a-4, a-5, a-6, a-8}
~~~

Redis có các lệnh Set điển hình `SINTER` và `SUNION`. Trên Spring Data Redis, thao tác thực tế để thực thi một method Repository có thể khác nhau theo phiên bản, mapper hoặc loại truy vấn. Minh họa này dùng đại số tập hợp để giải thích **chi phí dữ liệu trung gian**, không khẳng định Repository luôn gọi đúng một lệnh Set ở mọi phiên bản.

Đặt `A` và `B` là số thành viên của hai bucket:

~~~text
Giao:
    0 <= R_giao <= min(A, B)

Hợp:
    max(A, B) <= R_hop <= A + B
~~~

`R` là số ID kết quả. Nếu index chứa ID của Hash đã bị xóa hoặc hết hạn mà chưa dọn, số object đọc thành công có thể nhỏ hơn `R`.

**Quan trọng:** kết quả giao nhỏ không có nghĩa tính toán luôn rẻ. Hai Set mỗi Set 500.000 ID có thể chỉ có 50 ID chung, nhưng Redis vẫn phải xử lý các tập đầu vào lớn để tìm ra 50 ID đó.

## 7. Phân biệt trả kết quả và lưu kết quả thành key

### 7.1. `SINTER`, `SUNION`: trả ID về phía gọi

~~~redis
SINTER articles:category:backend articles:status:PUBLISHED
SUNION articles:category:backend articles:status:PUBLISHED
~~~

Lệnh trả dữ liệu đến client; nó không đặt một key có tên `tmp:...` vào keyspace. Dù vậy vẫn phát sinh chi phí:

- Redis tính toán giao/hợp và hình thành phản hồi.
- Output buffer có thể tăng khi kết quả chưa được client nhận hết.
- Network phải truyền ID kết quả.
- Client giữ những ID đã nhận và có thể tiếp tục đọc các Hash tương ứng.

Một phép hợp trả về vài trăm nghìn ID có thể tạo đỉnh sử dụng bộ nhớ ở cả Redis và JVM. Vì thế “không tạo key tạm” **không đồng nghĩa không dùng bộ nhớ tạm**.

### 7.2. `SINTERSTORE`, `SUNIONSTORE`: tạo Redis Set mới

~~~redis
SINTERSTORE tmp:articles:backend-published articles:category:backend articles:status:PUBLISHED
SCARD tmp:articles:backend-published
MEMORY USAGE tmp:articles:backend-published
~~~

Khác với `SINTER`, `SINTERSTORE` tạo hoặc ghi đè một key kết quả. Redis sẽ phải cấp phát bộ nhớ giữ Set này cho đến khi key bị xóa, hết hạn hoặc bị eviction theo chính sách.

Nếu muốn kết quả chỉ sống trong thời gian ngắn:

~~~redis
EXPIRE tmp:articles:backend-published 30
~~~

Hoặc khi không còn cần kết quả:

~~~redis
UNLINK tmp:articles:backend-published
~~~

`SINTERSTORE` và `EXPIRE` là hai lệnh riêng trong ví dụ, nên nếu tiến trình bị ngắt giữa hai lệnh có thể để lại key tạm không có TTL. Khi thực tế cần tạo key tạm, hãy thiết kế dọn dẹp đáng tin cậy và định danh key theo request để tránh hai request ghi đè dữ liệu của nhau.

### 7.3. `SINTERCARD`: chỉ lấy số lượng của giao

Redis 7 có lệnh:

~~~redis
SINTERCARD 2 articles:category:backend articles:status:PUBLISHED
~~~

Lệnh trả số lượng ID trong giao mà không gửi toàn bộ ID về client. Nếu chỉ cần biết số lượng kết quả, cách này tiết kiệm network và tránh tạo collection ID lớn phía client.

Có thể thêm giới hạn:

~~~redis
SINTERCARD 2 articles:category:backend articles:status:PUBLISHED LIMIT 1000
~~~

Khi chạm `LIMIT`, kết quả không còn biểu thị cardinality chính xác nếu giao thực sự lớn hơn giới hạn. `SINTERCARD` vẫn phải xử lý tập đầu vào; nó không biến phép giao thành thao tác hằng số thời gian.

Đây là lệnh Redis trực tiếp. Không nên giả định rằng mọi phương thức `countBy...` trên Spring Data Redis Repository tự động sử dụng `SINTERCARD`; hãy xác minh API và implementation khi quyết định dùng con đường này.

## 8. Hai ví dụ về bộ nhớ xử lý truy vấn

### 8.1. Giao rất nhỏ nhưng bucket nguồn rất lớn

~~~text
category=backend:    400.000 ID
status=PUBLISHED:   700.000 ID
giao:                    200 ID
~~~

Dù chỉ lấy 200 object cuối cùng, chi phí tìm giao vẫn bị ảnh hưởng bởi tập nguồn gồm hàng trăm nghìn membership. Chỉ nhìn kích thước `List<Article>` cuối cùng sẽ bỏ sót vấn đề.

### 8.2. Giao lớn và hydrate nhiều object

~~~text
category=backend:    200.000 ID
status=PUBLISHED:   320.000 ID
giao:                 80.000 ID
~~~

Luồng thực thi có thể gồm:

~~~text
Redis index Set (thường trú)
           |
           v
Tìm tập ID phù hợp (CPU / bộ nhớ xử lý)
           |
           v
Kết quả ID + output buffer + network
           |
           v
Đọc các Redis Hash
           |
           v
Dựng 80.000 Article trong JVM
           |
           v
List<Article>, serialization thành JSON, trả API
~~~

Ở đây có ba lớp bộ nhớ đáng theo dõi:

1. Redis xử lý index, tạo phản hồi và phục vụ Hash.
2. Buffer và đường truyền dữ liệu cho ID lẫn dữ liệu entity.
3. Java heap giữ object, String, collection và response buffer.

Ngay cả khi `INFO memory` của Redis không tăng mạnh, JVM vẫn có thể GC nhiều hoặc gặp `OutOfMemoryError` nếu API cố dựng tất cả 80.000 object cùng lúc.

## 9. Tính chọn lọc (selectivity) của chỉ mục

Với 1.000.000 Article:

| Điều kiện | Tỷ lệ phù hợp giả định | Kích thước bucket |
|---|---:|---:|
| `status = PUBLISHED` | 80% | 800.000 |
| `category = backend` | 12% | 120.000 |
| `authorId = u-7` | 0,01% | 100 |

Chỉ mục `status` có ít giá trị phân biệt, một bucket có thể rất lớn. Chỉ mục `authorId` có nhiều giá trị và một truy vấn cụ thể có thể lấy tập ID nhỏ hơn nhiều.

Với query kết hợp nhiều điều kiện, số ID cần dựng thành object có thể giảm khi thêm điều kiện chọn lọc cao. Tuy nhiên, **chi phí tìm giao** còn phụ thuộc kích thước các tập nguồn và cách thực thi. Không nên coi Repository là SQL optimizer luôn tự chọn kế hoạch truy vấn tốt nhất.

Nếu workload chủ yếu tìm theo ID, `@Indexed` trên các field không được truy vấn chỉ làm tăng dữ liệu index và công bảo trì. Nếu workload luôn yêu cầu “lấy toàn bộ PUBLISHED”, một bucket 80% dữ liệu không tự giải quyết vấn đề trả kết quả quá lớn.

## 10. Set không có thứ tự ổn định để phân trang

Redis Set không lưu một thứ tự nghiệp vụ. `SMEMBERS` hoặc `SINTER` không bảo đảm “20 bài mới nhất” nếu chỉ có Set index.

`SSCAN` có thể đọc dần các thành viên Set nhưng không tạo snapshot và thứ tự ổn định trong lúc dữ liệu thay đổi. Nó không tương đương phân trang theo thời gian hoặc theo score.

Nếu API cần thứ tự như `createdAt DESC` hoặc `score DESC`, một **Sorted Set** (`ZSET`) do ứng dụng quản lý có thể phù hợp hơn. Ví dụ index kiểu:

~~~text
ZSET articles:by-created-at
    score = timestamp
    member = articleId
~~~

Dùng những lệnh như `ZRANGE` với thứ tự và phạm vi phù hợp để lấy danh sách ID được giới hạn rồi đọc Hash. Đổi lại, Sorted Set cũng sử dụng RAM và cần cập nhật khi entity thay đổi hoặc hết hạn; không thể xem đây là “miễn phí bộ nhớ”.

Một API cần phân trang quy mô lớn có thể phải thiết kế index chuyên biệt và cơ chế cursor/score phù hợp. Tránh mặc định tải toàn bộ Set rồi cắt danh sách ở Java.
## 11. Chi phí cập nhật, xóa và tính nhất quán của chỉ mục

Chỉ mục không chỉ chiếm RAM ở trạng thái ổn định. Khi một thuộc tính có `@Indexed` thay đổi, Repository còn phải bảo trì quan hệ giữa ID và từng giá trị index.

Ví dụ đổi category của bài viết:

~~~java
Article article = repository.findById("a-101").orElseThrow();
article.setCategory("mobile");
repository.save(article);
~~~

Về mặt logic, trạng thái index cần thay đổi:

~~~text
Trước:
    articles:category:backend = {..., a-101, ...}
    articles:category:mobile  = {...}

Sau:
    articles:category:backend = {...}          (không còn a-101)
    articles:category:mobile  = {..., a-101}
~~~

Repository có thể duy trì thêm metadata để theo dõi và dọn những quan hệ index cũ. Vì vậy, chi phí của Redis Repository bao gồm cả **dữ liệu theo dõi index**, không chỉ các Set ánh xạ giá trị sang ID.

Các hệ quả:

- Càng nhiều field indexed, một lần `save` hoặc `deleteById` có thể cần càng nhiều thao tác cập nhật cấu trúc phụ.
- Field indexed thường xuyên đổi giá trị tạo thêm tải ghi và thay đổi kích thước bucket liên tục.
- Nếu sửa Hash bằng `HSET` trực tiếp, chỉ mục có thể không được cập nhật theo.
- Nếu xóa key entity bằng `DEL` trực tiếp, thông tin theo dõi/index có thể không được dọn như khi xóa qua Repository.
- Nếu index còn ID của Hash đã hết hạn, truy vấn có thể mất công đọc những key không tồn tại.

Vì thế, khi sử dụng `@Indexed`, cần xem xét cả **chi phí write amplification** và **tính nhất quán giữa index với Hash**.

## 12. TTL và dữ liệu phụ của expiration

Một entity có thể có TTL:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "sessions", timeToLive = 300)
public class SessionRecord {
    @Id
    private String id;

    @Indexed
    private String userId;

    // Constructor, getter và setter thông thường.
}
~~~

Về mặt logic:

~~~text
sessions:s-1001          [HASH, TTL 300 giây khi vừa lưu]
sessions:userId:u-7      [SET chứa s-1001, ...]
metadata liên quan       [tùy Repository và cấu hình]
~~~

Key chính có thể hết hạn sau 300 giây, nhưng index và metadata là cấu trúc phụ cần được bảo trì. Spring Data Redis có cơ chế xử lý expiration dùng Redis keyspace notifications khi được cấu hình tương ứng. Hành vi cleanup phụ thuộc phiên bản, cấu hình và khả năng nhận sự kiện.

Những nguồn RAM dễ bỏ sót:

1. **ID tồn dư trong index:** Hash đã hết hạn hoặc bị xóa nhưng chỉ mục chưa kịp dọn; truy vấn có thể trả ID không còn entity.
2. **Key quản lý expiration:** một số chế độ cần thêm metadata để phát sự kiện và dọn index.
3. **Shadow/phantom copy:** trong một số cấu hình, Spring Data Redis giữ bản sao entity thêm một khoảng thời gian để tạo event khi key chính hết hạn. Bản sao này sử dụng RAM.
4. **Tốc độ churn:** dữ liệu có TTL ngắn bị tạo và xóa liên tục, làm tăng tải ghi, tạo key nhỏ và biến động allocator.

Nếu Redis bật `maxmemory` với chính sách eviction, các key có thể bị loại bỏ mà không theo quy trình bảo trì Repository; cần cân nhắc nguy cơ không đồng bộ giữa Hash, index và metadata.

Với session, token hoặc cache entity có TTL ngắn, dự báo chỉ dựa trên kích thước Hash đang sống thường đánh giá thấp chi phí bộ nhớ thực tế.

## 13. Đo bộ nhớ Redis

### 13.1. Các chỉ số toàn Redis

~~~redis
INFO memory
MEMORY STATS
INFO stats
~~~

| Chỉ số | Ý nghĩa |
|---|---|
| `used_memory` | Bộ nhớ Redis báo đang cấp phát |
| `used_memory_peak` | Đỉnh bộ nhớ Redis ghi nhận |
| `used_memory_rss` | Resident memory theo hệ điều hành |
| `maxmemory` | Giới hạn bộ nhớ nếu được cấu hình |
| `mem_fragmentation_ratio` | Chỉ báo tham khảo về chênh lệch RSS và cấp phát |
| `evicted_keys` | Số key bị eviction |
| Client/output buffer metrics | Áp lực từ kết nối và phản hồi lớn |

Không được xem tất cả RAM nằm ngoài các Hash là RAM index. Nó còn bao gồm buffer, cấu trúc dữ liệu quản lý, allocator và những key khác.

### 13.2. Đo Hash gốc và một bucket index

~~~redis
TYPE articles:a-101
HLEN articles:a-101
MEMORY USAGE articles:a-101

TYPE articles:category:backend
SCARD articles:category:backend
MEMORY USAGE articles:category:backend

TYPE articles:status:PUBLISHED
SCARD articles:status:PUBLISHED
MEMORY USAGE articles:status:PUBLISHED
~~~

`HLEN` đếm field của Hash; `SCARD` đếm phần tử Set; `MEMORY USAGE` cho biết ước lượng byte của key/value hiện tại. Key không tồn tại có thể cho kết quả nil.

Khi lấy mẫu, nên chọn:

- Bucket chỉ có một ID.
- Bucket vài chục hoặc vài trăm ID.
- Bucket vài nghìn ID.
- Bucket đặc biệt lớn nếu có.

Bucket nhỏ có thể bị chi phối bởi overhead key, bucket lớn chịu tác động rõ hơn của số membership. Phân phối không đều khiến việc lấy một byte/member bình quân có thể dẫn đến sai lệch lớn.

### 13.3. Dùng SCAN thay vì KEYS trên môi trường lớn

~~~redis
SCAN 0 MATCH articles:* COUNT 100
~~~

`SCAN` trả cursor và một phần danh sách key. Lặp đến khi cursor quay lại `0`. `COUNT` chỉ là gợi ý khối lượng mỗi lần quét, không bảo đảm số key trả về.

Từ terminal:

~~~bash
redis-cli --scan --pattern 'articles:*'
~~~

Không nên mặc định dùng `KEYS articles:*` trên production lớn để đếm key vì lệnh có thể chặn Redis trong lúc quét toàn bộ keyspace. `SCAN` vẫn có chi phí nhưng dễ điều tiết hơn.

### 13.4. Đếm index mà không kéo mọi ID về

Chỉ cần biết số ID trong một bucket:

~~~redis
SCARD articles:status:PUBLISHED
~~~

Tránh dùng `SMEMBERS articles:status:PUBLISHED` chỉ để đếm. Lệnh đó trả tất cả ID và có thể tạo output rất lớn.

Nếu cần xem dần phần tử của Set:

~~~redis
SSCAN articles:status:PUBLISHED 0 COUNT 100
~~~

`SSCAN` không tạo snapshot nhất quán khi dữ liệu đang thay đổi; có thể trả phần tử lặp. Nó là công cụ đọc dần Set, không phải cơ chế paging có thứ tự ổn định.

### 13.5. Đo cả ứng dụng Java

Cần theo dõi:

- Số ID trả về từ index.
- Số Hash thật sự được đọc và số object dựng thành công.
- Java heap used, GC pressure và tốc độ cấp phát.
- Byte network và kích thước phản hồi JSON.
- Số truy vấn đồng thời và lượng dữ liệu mỗi truy vấn.
- p95/p99 latency và peak memory, không chỉ trung bình.

Một query lấy 40.000 entity có thể chạy được riêng lẻ. Khi nhiều query như vậy xảy ra đồng thời, bộ nhớ tạm và heap có thể tăng mạnh.

## 14. Phương pháp ước lượng capacity

### Bước 1 — Đo dữ liệu gốc

Lấy mẫu `MEMORY USAGE` của các Hash đại diện, theo nhóm entity nhỏ/vừa/lớn. Ước lượng số entity cực đại trong hệ thống, không chỉ số entity trong dữ liệu demo.

### Bước 2 — Liệt kê từng index thực sự cần

Với mỗi trường:

- Có bao nhiêu entity mang giá trị?
- Có bao nhiêu giá trị phân biệt?
- Bucket lớn nhất và kích thước bình quân là bao nhiêu?
- Field đơn hay đa trị?
- ID và tên key dài bao nhiêu?
- Field có thường đổi hay không?
- Truy vấn có thường dùng index này hay không?

### Bước 3 — Đo kích thước bucket theo phân phối

Lấy mẫu nhiều bucket với cardinality khác nhau, dùng `SCARD`, `MEMORY USAGE`, khi cần dùng `OBJECT ENCODING`. Tính cả số key Set nhỏ thay vì chỉ tính số phần tử.

### Bước 4 — Đưa metadata và TTL vào bài toán

Quan sát key quản lý Repository, key phục vụ expiration và shadow copy nếu có. Nếu ứng dụng có index stale cần cleanup, đừng coi các phần tử đó là miễn phí.

### Bước 5 — Đánh giá truy vấn lớn nhất

Ghi nhận các đại lượng:

~~~text
Kích thước từng bucket đầu vào
Số ID sau giao/hợp
Số Hash phải đọc
Số object Java được dựng
Số request chạy đồng thời
~~~

Thử workload tương ứng để đo RAM đỉnh, buffer và heap. Một truy vấn trung bình nhỏ không bảo đảm hệ thống chịu được những truy vấn trả hàng trăm nghìn ID.

### Bước 6 — Dành headroom

Capacity phải dành dung lượng cho buffer, allocator, fragmentation, replication/failover và tăng trưởng. Mức headroom phụ thuộc workload, cấu hình Redis và SLO, không có một phần trăm đúng cho mọi hệ thống.

Ví dụ bảng ước lượng với 100.000 Article và ba field indexed đơn:

| Hạng mục | Quy mô logic | Số liệu cần đo |
|---|---|---|
| Hash gốc | 100.000 Hash | Byte theo phân phối Hash |
| Index `status` | ~100.000 membership | Số bucket, SCARD, MEMORY USAGE |
| Index `category` | ~100.000 membership | Số bucket, SCARD, MEMORY USAGE |
| Index `authorId` | ~100.000 membership | Số bucket, SCARD, MEMORY USAGE |
| Keyspace/metadata | Theo Repository | Byte của các key quản lý |
| TTL | Theo phiên bản/cấu hình | Byte của key và bản sao bổ sung |
| Query tạm | Theo concurrency | RAM đỉnh và buffer |
| Java client | Theo kết quả | Heap, GC và response bytes |

Ba index có thể tạo khoảng 300.000 membership. **Đó không phải 300.000 Redis key**; số key index phụ thuộc số giá trị phân biệt, còn số byte phụ thuộc encoding và phân phối thực tế.

## 15. Các hướng tối ưu

### 15.1. Chỉ index field phục vụ truy vấn thật

Nếu ứng dụng chỉ thường xuyên gọi:

~~~java
repository.findById(id);
~~~

thì việc thêm `@Indexed` vào những field khác không giúp truy vấn theo ID nhanh hơn. Trước khi thêm index, cần trả lời nó hỗ trợ method nào, có bao nhiêu request sử dụng và tiết kiệm bao nhiêu lần truy xuất.

### 15.2. Xem xét cả số bucket lẫn kích thước bucket

| Kiểu index | Lợi ích | Chi phí dễ nổi bật |
|---|---|---|
| Ít giá trị phân biệt | Phân nhóm nhanh | Bucket lớn, kết quả rộng |
| Nhiều giá trị phân biệt | Equality lookup chọn lọc | Rất nhiều Set nhỏ và overhead key |
| Thuộc tính đa trị | Tìm theo thành viên collection | Nhiều membership mỗi entity |
| Field thay đổi thường xuyên | Tìm theo trạng thái hiện tại | Nhiều thao tác index update |

Không loại bỏ index chỉ vì nó có nhiều bucket nhỏ: nó có thể cực kỳ hữu ích. Cần so sánh chi phí với giá trị thực của truy vấn.

### 15.3. Giảm số ID và object trả về

Nếu chỉ cần số lượng, cân nhắc đường đếm phù hợp thay vì gọi một method trả `List<Article>` rồi lấy `size()`. Các phép đếm trực tiếp trên index cần xem xét tính nhất quán của Set với Hash thực tế.

Nếu giao diện chỉ hiển thị vài chục item, không nên lấy toàn bộ kết quả rồi cắt tại Java. Với nhu cầu sắp xếp và phân trang, cân nhắc cấu trúc Sorted Set được duy trì phù hợp để có thể lấy một dải ID nhỏ trước khi đọc Hash.

### 15.4. Kiểm soát các key trung gian

Nếu ứng dụng chủ động dùng `SINTERSTORE` hoặc `SUNIONSTORE`:

- Chỉ lưu tập trung gian khi có nhu cầu sử dụng lại.
- Dùng định danh key theo request/job.
- Đặt TTL và xử lý trường hợp tiến trình dừng trước khi kịp đặt TTL.
- Giới hạn số request tạo key tạm cùng lúc.
- Có cơ chế dọn key và đo bộ nhớ của nhóm key tạm.

Một tên tiền tố `tmp:` không khiến Redis tự động xóa key. Phải quản lý vòng đời một cách rõ ràng.

### 15.5. Chọn cấu trúc theo kiểu truy vấn

| Nhu cầu | Cách triển khai có thể phù hợp | Chi phí cần tính |
|---|---|---|
| Đọc theo ID | Hash Repository theo key | Hash, metadata |
| Tìm equality theo một field | `@Indexed`/Set | Membership, bucket, update |
| Tìm AND/OR nhiều field | Kết hợp Set | Tập trung gian, CPU, output |
| Sắp theo thời gian/score | Sorted Set | RAM ZSET, đồng bộ dữ liệu |
| Tìm theo vị trí | Geospatial index | Cấu trúc index riêng, update |
| Nhiều điều kiện bất kỳ, tìm kiếm full-text | Công cụ tìm kiếm/truy vấn thích hợp | Hạ tầng và đồng bộ dữ liệu |

`@GeoIndexed` trong Spring Data Redis có thể gắn với cấu trúc Redis geospatial, vốn không có cùng công thức chi phí với Set equality. Cần đo đúng kiểu index thực dùng.

## 16. Tình huống: 250.000 session với TTL

Một hệ thống lưu 250.000 session đang hoạt động, mỗi session có:

~~~text
sessionId  -> duy nhất
userId     -> khoảng 50.000 người dùng
state      -> ACTIVE hoặc REVOKED
region     -> 10 vùng
TTL        -> 15 phút
~~~

Dự định index `userId`, `state`, `region`. Nếu mỗi session có đủ ba giá trị, quy mô logic là:

~~~text
userId index: 250.000 membership
state index:  250.000 membership
region index: 250.000 membership
--------------------------------
Tổng:        750.000 membership

Số bucket gần đúng:
    userId:  50.000
    state:        2
    region:      10
    ----------------
    Tổng:   50.012
~~~

Chưa tính 250.000 Hash, dữ liệu quản lý Repository và TTL.

Đánh giá ba câu hỏi:

- **“Lấy session của user u-7”**: index `userId` nhiều khả năng giúp thu hẹp tập ID.
- **“Đếm tất cả session ACTIVE”**: có thể nên dùng cơ chế đếm riêng thay vì hydrate mọi Session; cần phân biệt số ID trong index với số entity thực sự còn sống.
- **“Liệt kê mọi ACTIVE session ở một region”**: giao hai bucket có thể rất lớn; đây là áp lực đối với tập trung gian, network và Java heap.

Vì TTL chỉ 15 phút, hệ thống còn có tốc độ tạo/xóa index cao. Cần đo cả cleanup khi expiration, dữ liệu quản lý và shadow copy nếu được cấu hình.

## 17. Những lỗi thường gặp

### “Đã xóa nhiều entity nhưng Redis vẫn đầy”

Có thể còn index, metadata, shadow copy, key kết quả tạm hoặc allocator chưa trả RSS về mức trước. Phân biệt từng nhóm bằng `SCAN`, `MEMORY USAGE`, `INFO memory` và số đo sau khi bộ nhớ ổn định.

### “Thêm một `@Indexed` khiến RAM tăng bất thường”

Trường có thể có rất nhiều giá trị phân biệt, tạo hàng loạt Set nhỏ; hoặc là thuộc tính đa trị tạo nhiều membership. Cần đo số bucket, cardinality và encoding.

### “Truy vấn chỉ trả 50 object nhưng vẫn chậm”

Hai index đầu vào có thể chứa hàng trăm nghìn ID. Kết quả cuối nhỏ không có nghĩa phép kết hợp hoặc đọc index nhẹ.

### “Redis còn RAM nhưng Java bị OutOfMemoryError”

Có thể query đang dựng `List<Entity>` khổng lồ. Theo dõi Java heap, GC và số entity được hydrate; không chỉ theo dõi RAM Redis.

### “SINTERSTORE làm memory cứ tăng”

Key đích của `SINTERSTORE` là Set có thật. Nếu thiếu TTL hoặc cleanup, nó tiếp tục chiếm RAM.

### “SCARD cao hơn số entity find được”

Index có thể giữ ID của entity đã hết hạn, bị xóa trực tiếp hoặc bị eviction. Xem xét đường cập nhật và cơ chế cleanup.

### “SSCAN trả ID lặp hoặc thứ tự không ổn định”

`SSCAN` không phải pagination có snapshot và thứ tự cố định. Nếu ứng dụng cần phân trang nghiệp vụ ổn định, phải thiết kế cấu trúc khác.

## 18. Bài thực hành

### Bài 1 — Đo Hash và index bucket

1. Tạo `Article` có `@Indexed` trên `category` và `status`.
2. Lưu 100 thực thể thuộc ba category và hai status.
3. Dùng `MEMORY USAGE` đo một Hash và một bucket Set.
4. Dùng `SCARD` tìm bucket lớn nhất.
5. Đổi category của một Article qua Repository và quan sát index tương ứng.

Lưu ý rằng thêm `@Indexed` vào lớp có dữ liệu cũ không tự động bảo đảm mọi bản ghi cũ đã được backfill index.

### Bài 2 — Giao, hợp và lưu tập trung gian

Dùng namespace riêng, không đụng vào key do Repository quản lý:

~~~redis
SADD demo:category:backend a-1 a-2 a-3 a-4 a-5
SADD demo:status:published a-2 a-4 a-6 a-8

SCARD demo:category:backend
SCARD demo:status:published

SINTER demo:category:backend demo:status:published
SUNION demo:category:backend demo:status:published
SINTERCARD 2 demo:category:backend demo:status:published
~~~

Sau đó:

~~~redis
SINTERSTORE demo:tmp:intersection demo:category:backend demo:status:published
SCARD demo:tmp:intersection
MEMORY USAGE demo:tmp:intersection
TTL demo:tmp:intersection
EXPIRE demo:tmp:intersection 30
~~~

Quan sát sự khác nhau giữa lệnh chỉ trả tập kết quả và lệnh tạo một key Redis chứa tập kết quả. `SINTERCARD` yêu cầu Redis có hỗ trợ lệnh.

### Bài 3 — Ước lượng capacity

Hệ thống giả định:

~~~text
N = 500.000 entity
Index đơn: state, region, ownerId
Số giá trị phân biệt:
    state   = 4
    region  = 12
    ownerId = 80.000
~~~

Hãy tính số membership và bucket nếu mọi entity đều có ba giá trị. Sau đó liệt kê các phép đo cần có để chuyển con số logic thành ước lượng RAM, và phân tích nguy cơ nếu một API lấy toàn bộ entity thuộc một region.

### Bài 4 — Peak khi truy vấn đồng thời

Có 20 request đồng thời. Mỗi request giao hai bucket lớn và tạo 50.000 Article để trả về. Hãy chỉ ra bộ nhớ nào nằm trong Redis thường trú, bộ nhớ nào tạm trong quá trình truy vấn và bộ nhớ nào trong JVM. Nếu giao diện chỉ cần 20 dòng/trang, đề xuất cách thay đổi luồng truy xuất.

## 19. Ghi nhớ

- `@Indexed` duy trì quan hệ **giá trị → tập ID**, sử dụng RAM ngoài Hash chính và làm tăng chi phí ghi/xóa.
- **Số membership khác số bucket.** Cardinality của giá trị index và cấu trúc Set ảnh hưởng đến RAM, không chỉ số entity.
- Giao/hợp index có thể tốn CPU, bộ nhớ tạm, output buffer và Java heap; tập kết quả nhỏ không bảo đảm tập đầu vào nhỏ.
- `SINTERSTORE`/`SUNIONSTORE` lưu thành key cần cleanup/TTL. `SINTERCARD` phù hợp khi chỉ cần đếm giao trên Redis hỗ trợ.
- Cần tính số object Java dựng lại cùng số ID trả về, nhất là với query lớn hoặc đồng thời cao.
- TTL, index cleanup và shadow copy nếu có khiến chi phí thực khác việc chỉ cộng kích thước Hash.
- Đo bằng `MEMORY USAGE`, `SCARD`, `OBJECT ENCODING`, `SCAN`, `INFO memory` và metric Java.
- Lựa chọn index theo query thực tế. Với pagination có thứ tự hoặc tìm kiếm rất lớn, có thể cần cấu trúc chuyên biệt.

### Tài liệu tham khảo chính thức

- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries-and-query-methods.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — SCARD](https://redis.io/docs/latest/commands/scard/)
- [Redis — SINTERCARD](https://redis.io/docs/latest/commands/sintercard/)
- [Redis — SINTERSTORE](https://redis.io/docs/latest/commands/sinterstore/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
