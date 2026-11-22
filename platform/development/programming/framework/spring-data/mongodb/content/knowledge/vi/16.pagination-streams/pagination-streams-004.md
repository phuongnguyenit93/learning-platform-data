# Slice và xác định còn dữ liệu tiếp theo

## 1. Bài toán phân trang khi không cần biết tổng số bản ghi

Trong chương **Phân trang và luồng** của **Spring Data MongoDB**, nhiều màn hình chỉ cần hiển thị một tập kết quả rồi trả lời câu hỏi: **“Có dữ liệu để tải tiếp không?”**. Ví dụ, trang danh mục sản phẩm có nút *Xem thêm*; mỗi lần người dùng yêu cầu 10 sản phẩm đang bán.

Nếu đang có 23 sản phẩm phù hợp, trải nghiệm mong muốn là:

| Lần gọi | Kích thước trang | Số phần tử trả về | Còn dữ liệu tiếp theo? |
|---|---:|---:|---|
| Trang 0 | 10 | 10 | Có |
| Trang 1 | 10 | 10 | Có |
| Trang 2 | 10 | 3 | Không |
| Trang 3 (ngoài phạm vi hiện có) | 10 | 0 | Không |

Để tạo giao diện này, client **không bắt buộc biết tổng số document hay tổng số trang**. Spring Data cung cấp kiểu trả về `Slice<T>` cho tình huống đó. `Slice` là một **khối kết quả đã tải** kèm thông tin về trang hiện tại và khả năng có trang sau, thay vì một kết quả có total count như `Page<T>`.

Mục tiêu của bài:

1. Hiểu chính xác ý nghĩa `Slice`, `hasNext()`, `hasPrevious()` và các giới hạn của chúng.
2. Viết phương thức `MongoRepository` trả `Slice<T>` với `Pageable` và sort ổn định.
3. Hiểu kỹ thuật truy vấn **kích thước trang + 1 phần tử** để xác định có dữ liệu tiếp theo mà không cần count toàn bộ.
4. Tạo API trả danh sách và thông tin trang kế tiếp mà không làm lộ chi tiết entity.
5. Phân tích chi phí `skip/limit`, vấn đề dữ liệu thay đổi giữa các trang, và khi nào nên chuyển sang keyset/cursor.
6. Kiểm thử hành vi trang đầu, trang cuối, trang rỗng, dữ liệu trùng khóa sort và truy vấn MongoDB thực tế.

> Các ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Hành vi triển khai `Slice`/`Page` và lệnh BSON cụ thể có thể khác theo phiên bản; nguyên tắc phân trang cần được kiểm chứng trên MongoDB và driver của dự án.

## 2. Phân biệt List, Slice, Page, Stream và Window

| Kiểu kết quả | Có danh sách hiện tại? | Có `hasNext()`? | Có tổng số phần tử? | Đặc điểm chính |
|---|---|---|---|---|
| `List<T>` | Có | Không theo contract riêng | Không | Chỉ là kết quả; ứng dụng tự xác định có trang tiếp hay không |
| `Slice<T>` | Có | Có | Không | Phù hợp nút “Xem thêm” và các trang không cần total count |
| `Page<T>` | Có | Có | Có, qua `getTotalElements()` | Phù hợp UI cần số trang hoặc tổng bản ghi |
| `Stream<T>` | Từng phần tử theo luồng | Không theo semantics `Slice` | Không | Có thể liên quan cursor/tài nguyên mở; cần đóng đúng cách |
| `Window<T>` và scrolling API | Một cửa sổ kết quả | Có chỉ dấu liên quan cửa sổ | Không | Có thể hỗ trợ offset/keyset scrolling nếu API và phiên bản cho phép |

`Page<T>` kế thừa ý nghĩa slice và bổ sung metadata tổng số, nhưng một truy vấn trả `Page` có thể phải thực hiện thêm thao tác đếm. Framework đôi khi tối ưu hoặc bỏ qua count nếu có đủ thông tin để suy ra tổng, nên **không khẳng định mọi Page luôn chạy đúng hai truy vấn**.

`Slice<T>` không có `getTotalElements()` hay `getTotalPages()`. Một số lệnh gọi hữu ích:

~~~java
Slice<CatalogProduct> slice = repository.findByStatus("ACTIVE", pageable);

List<CatalogProduct> currentItems = slice.getContent();
boolean hasMore = slice.hasNext();
boolean hasPrevious = slice.hasPrevious();
int currentPage = slice.getNumber();      // 0-based
int requestedSize = slice.getSize();
int itemsInSlice = slice.getNumberOfElements();
Sort appliedSort = slice.getSort();
~~~

Đoạn trên giả sử có biến `repository` và `pageable` như ví dụ ở mục 3; cần import `org.springframework.data.domain.Slice`, `Sort`, `java.util.List`. `Slice` đã chứa dữ liệu trang hiện tại, không phải một iterator giữ server cursor mở xuyên suốt nhiều HTTP request.

### Hiểu đúng hasNext

- `hasNext() == true`: tại thời điểm truy vấn, có bằng chứng rằng còn ít nhất một bản ghi sau **khối kết quả đang trả**, theo điều kiện và thứ tự của truy vấn.
- `hasNext() == false`: không phát hiện thêm phần tử sau khối hiện tại trong lần truy vấn đó. Nó **không phải lời hứa** rằng collection sẽ không có dữ liệu mới sau này.
- `hasPrevious()`: thông tin về khả năng quay về trang trước theo vị trí trang, **không phải kết quả đếm hoặc kiểm tra lại xem các document trang trước còn tồn tại hay không**.
- `getNumberOfElements()` là số phần tử **đang trả**, khác với tổng số bản ghi thỏa filter.

Khi vừa đọc trang 2 và thấy `hasNext() == false`, UI có thể ẩn nút *Xem thêm*. Nếu có sản phẩm mới được thêm một giây sau, UI chưa tự biết sự thay đổi đó; người dùng cần refresh hoặc một cơ chế cập nhật riêng.

## 3. Mô hình Java và MongoRepository trả Slice

Để chạy ví dụ, ứng dụng có starter `spring-boot-starter-data-mongodb`, cấu hình MongoDB URI và đặt các class dưới package được Spring Boot quét. Dữ liệu được lưu trong collection `catalog_products`.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String title,
        String status,
        long priceVnd,
        @Field("created_at") Instant createdAt) {
}
~~~

`@MongoId(FieldType.STRING)` bảo toàn ID dạng BSON String và ánh xạ property Java `id` sang `_id`. `@Field("created_at")` ánh xạ property `createdAt` thành trường BSON `created_at`. Ta giả định `createdAt` không null và không bị sửa trong vòng đời sản phẩm; đây là lựa chọn **khóa sort ít biến động** hơn `updatedAt`.

Ví dụ BSON (lược bỏ metadata kiểu `_class`):

~~~json
{
  "_id": "p-023",
  "title": "Bình giữ nhiệt",
  "status": "ACTIVE",
  "priceVnd": 129000,
  "created_at": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Slice<CatalogProduct> findByStatus(
            String status, Pageable pageable);
}
~~~

Đây là derived query: `findByStatus` đặt điều kiện trên property `status`; tham số `Pageable` quy định **offset, limit và sort**. Khi kiểu trả về là `Slice<CatalogProduct>`, Spring Data sử dụng thông tin của truy vấn để xác định `hasNext` mà **không cần API Page công bố total count**.

### 3.1. Gọi repository với Pageable

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

Pageable pageZero = PageRequest.of(
        0,
        10,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

Slice<CatalogProduct> first =
        repository.findByStatus("ACTIVE", pageZero);

boolean hasMore = first.hasNext();
~~~

`PageRequest.of(0, 10, ...)` yêu cầu trang đầu (trang bắt đầu từ **0**) với kích thước 10. `Sort` dùng tên **property Java**: `createdAt` được ánh xạ sang `created_at`, `id` sang `_id` trong MongoDB.

Tại sao sort hai field?

- `createdAt DESC` ưu tiên sản phẩm tạo gần đây nhất.
- `id DESC` là *tie-breaker* khi nhiều sản phẩm có cùng `createdAt`, tạo thứ tự xác định vì `_id` là duy nhất trong collection.

Nếu chỉ sort theo `createdAt` mà hàng trăm document có cùng timestamp, thứ tự trong nhóm bằng nhau **không được bảo đảm** giữa các lần truy vấn. Phân trang dựa trên thứ tự không xác định có thể lặp hoặc bỏ sót phần tử dù dữ liệu không thay đổi.

### 3.2. Sort không thay thế snapshot

Ngay cả với thứ tự tuyệt đối dựa trên (`createdAt`, `id`), **offset pagination không tạo snapshot bất biến giữa các request**. Nếu sản phẩm mới xuất hiện trước vị trí đã đọc, dữ liệu ở offset kế tiếp có thể dịch chuyển. Tương tự, xóa một sản phẩm ở trang trước có thể làm một phần tử bị bỏ qua.

Do đó có hai tầng bảo đảm khác nhau:

1. **Sort ổn định khi dữ liệu không thay đổi:** có tie-breaker duy nhất.
2. **Không trùng/bỏ sót khi dữ liệu thay đổi:** cần mô hình scrolling phù hợp, checkpoint/snapshot hoặc cơ chế nghiệp vụ bổ sung, chứ không phải chỉ thêm `OrderBy`.

## 4. Cơ chế lấy pageSize + 1 để biết hasNext

Giả sử `pageSize = 10`. Một kỹ thuật phổ biến để tạo `Slice` là truy vấn **tối đa 11 document**:

~~~mermaid
flowchart TD
    A["Filter + sort + offset"] --> B["Tải tối đa pageSize + 1 bản ghi"]
    B --> C{"Có hơn pageSize bản ghi?"}
    C -->|"Có"| D["Trả 10 bản ghi đầu, hasNext = true"]
    C -->|"Không"| E["Trả tất cả bản ghi, hasNext = false"]
    D --> F["Không cần total count"]
    E --> F
~~~

Khi lấy được 11 document, bản ghi thứ 11 **chỉ dùng để phát hiện trang tiếp theo**, không nằm trong response của trang hiện tại. Nếu chỉ có 10 document, không có bằng chứng cho trang sau tại thời điểm đọc. Đây là một cách thực thi nền tảng cho slice; số lệnh BSON và chi tiết tối ưu có thể thay đổi theo phiên bản Spring Data.

Với ví dụ 23 document:

- Truy vấn trang 0: `skip(0)`, lấy tối đa 11; trả 10, `hasNext = true`.
- Truy vấn trang 1: `skip(10)`, lấy tối đa 11; trả 10, `hasNext = true`.
- Truy vấn trang 2: `skip(20)`, lấy tối đa 11; thực tế chỉ có 3; trả 3, `hasNext = false`.

**Tại sao không chỉ lấy đúng 10?** Nếu trả đúng 10, không thể phân biệt collection còn 10 bản ghi (hết) với collection còn 11 hoặc nhiều hơn (có trang sau) chỉ từ tập hiện tại. Tải thêm **một** là tín hiệu đủ khi truy vấn có filter và sort nhất quán.

`Page` thường cần tổng số để tính tổng trang. `Slice` cố ý bỏ metadata đó, phù hợp khi UI chỉ có *Trước*/*Tiếp theo*, infinite-scroll hoặc nút *Xem thêm*.

## 5. Tạo API response từ Slice

Không nên trả nguyên Spring Data `Slice<CatalogProduct>` ra ngoài rồi phụ thuộc vào cấu trúc JSON framework tự serialize. API ổn định hơn khi chủ động xác định payload và chỉ công khai các trường cần thiết.

**ProductCard.java**

~~~java
package com.example.catalog;

public record ProductCard(
        String id, String title, long priceVnd) {
}
~~~

**ProductSliceResponse.java**

~~~java
package com.example.catalog;

import java.util.List;

public record ProductSliceResponse(
        List<ProductCard> items,
        int page,
        int size,
        boolean hasNext,
        Integer nextPage) {
}
~~~

**ProductBrowseService.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class ProductBrowseService {
    private final CatalogProductRepository products;

    public ProductBrowseService(CatalogProductRepository products) {
        this.products = products;
    }

    public ProductSliceResponse listActive(int page, int size) {
        if (page < 0 || page == Integer.MAX_VALUE
                || size < 1 || size > 100) {
            throw new IllegalArgumentException("Trang hoặc kích thước không hợp lệ");
        }

        Sort stableSort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
        Pageable pageable = PageRequest.of(page, size, stableSort);

        Slice<CatalogProduct> slice =
                products.findByStatus("ACTIVE", pageable);

        List<ProductCard> cards = slice.map(p ->
                new ProductCard(p.id(), p.title(), p.priceVnd()))
                .getContent();

        boolean more = slice.hasNext();
        return new ProductSliceResponse(
                cards,
                slice.getNumber(),
                slice.getSize(),
                more,
                more ? page + 1 : null);
    }
}
~~~

Trong API công khai, cần ánh xạ lỗi tham số thành response phù hợp (ví dụ HTTP 400); giới hạn `size <= 100` ở đây là **chính sách ví dụ**, không phải giới hạn bắt buộc của Spring Data. Tùy sản phẩm, có thể kiểm soát thêm offset tối đa và số lần tải.

`slice.map(...)` biến đổi **nội dung đã lấy** sang DTO và giữ metadata của slice. Đây là cách **giảm field công khai trong API**, không tự chứng minh truy vấn MongoDB chỉ tải các trường `id/title/priceVnd`. Nếu document có payload lớn, cần projection ở mức query hoặc repository DTO phù hợp và kiểm tra lệnh driver.

Payload một trang:

~~~json
{
  "items": [
    { "id": "p-023", "title": "Bình giữ nhiệt", "priceVnd": 129000 },
    { "id": "p-022", "title": "Sổ tay", "priceVnd": 45000 }
  ],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "nextPage": 1
}
~~~

Ví dụ response trên giả định `size = 2`; trang thực có thể chứa những sản phẩm khác tùy dữ liệu và sort. Khi `hasNext = false`, `nextPage` là `null`.

### 5.1. Dùng Slice.nextPageable()

Spring Data `Slice` có phương thức như `nextPageable()` để lấy phân trang kế tiếp khi có dữ liệu. Trong service hoặc xử lý nội bộ, hãy dùng `hasNext()` để kiểm tra trước rồi mới yêu cầu trang tiếp theo; ở endpoint HTTP, thường chỉ trả metadata/URL thay vì gửi object `Pageable` của framework tới client.

Không coi `nextPageable` là khóa cursor snapshot. Nó chủ yếu đại diện cho **vị trí trang offset tiếp theo** theo chiến lược hiện tại.

## 6. Tự xây dựng Slice bằng MongoTemplate

Khi filter được xây dựng động, `MongoTemplate` hữu ích để điều khiển chi tiết filter, sort và giới hạn. Ví dụ dưới đây thực hiện ý tưởng **pageSize+1** một cách tường minh, sau đó tạo `SliceImpl`.

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSliceQueryService {
    private final MongoTemplate mongo;

    public ProductSliceQueryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Slice<CatalogProduct> byStatus(
            String status, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Pagination không hợp lệ");
        }

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
        Pageable pageable = PageRequest.of(page, size, sort);

        Query query = Query.query(Criteria.where("status").is(status));
        query.with(sort);
        query.skip(pageable.getOffset());
        query.limit(size + 1);

        List<CatalogProduct> found =
                mongo.find(query, CatalogProduct.class);

        boolean hasNext = found.size() > size;
        List<CatalogProduct> current = List.copyOf(
                found.subList(0, Math.min(size, found.size())));
        return new SliceImpl<>(current, pageable, hasNext);
    }
}
~~~

Giải thích:

1. `Query.query(Criteria.where("status").is(status))` tạo filter theo property Java.
2. `query.with(sort)` đặt sort rõ ràng; với entity đích, Spring Data chuyển `createdAt` thành `created_at` và `id` thành `_id`.
3. `query.skip(pageable.getOffset())` bỏ qua `page * size` document theo thứ tự sort.
4. `query.limit(size + 1)` lấy thêm một document để xác định `hasNext`.
5. `SliceImpl<>(current, pageable, hasNext)` đóng gói kết quả mà không cần phép count.

Đây là **triển khai minh họa** cho trường hợp truy vấn không bị filter bổ sung sau khi tải về. Nếu tải 11 record rồi loại bớt một số record bằng Java trước khi xác định `hasNext`, kết quả có thể sai. Điều kiện xác định tập dữ liệu cần áp dụng **trong truy vấn MongoDB** để cơ chế thêm một phần tử còn đúng.

### MongoDB command minh họa

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ created_at: -1, _id: -1 })
  .skip(10)
  .limit(11);
~~~

Đây là lệnh tương đương về mặt ý nghĩa với `page = 1`, `size = 10`. Driver có thể gửi `find` command gồm `filter`, `sort`, `skip`, `limit` thay vì chuỗi shell như trên.

## 7. Index và hiệu năng phân trang theo offset

Với truy vấn thường xuyên lọc `status` và sắp xếp theo (`createdAt DESC`, `id DESC`), một compound index ứng viên:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, created_at: -1, _id: -1 },
  { name: "idx_status_created_id" }
);
~~~

Index giúp hỗ trợ bộ lọc và thứ tự trả dữ liệu phù hợp; vẫn cần kiểm tra `explain("executionStats")` trên dữ liệu đại diện. Truy vấn kèm filter `status` và sort có thể sử dụng index theo điều kiện và hình dạng truy vấn thực tế.

Ví dụ:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ created_at: -1, _id: -1 })
  .skip(50000)
  .limit(11)
  .explain("executionStats");
~~~

**`Slice` không loại bỏ chi phí `skip`.** Với offset lớn, database thường phải duyệt/bỏ qua nhiều entry trước khi lấy page tiếp theo. Dù index phù hợp và không cần count toàn bộ, trang thứ 5.000 vẫn có thể tốn nhiều tài nguyên.

Các dấu hiệu cần đo:

- `totalKeysExamined`, `totalDocsExamined` và thời gian thực thi ở trang gần đầu so với trang sâu.
- Số command MongoDB, số phần tử thực tải (`size+1`) và payload.
- `p95`/`p99` latency dưới tải thực, connection pool, read preference và sort stage.
- Index nào được chọn, chi phí ghi khi thêm compound index và kích thước collection.

Nếu UI chỉ cuộn liên tục qua nhiều nghìn trang, hãy cân nhắc **keyset/cursor scrolling** thay vì cho phép offset tăng không giới hạn. Nếu cần truy cập trực tiếp “trang 500” và biết tổng số trang, Page/offset vẫn có thể phù hợp với tập dữ liệu vừa phải, nhưng nên xác định giới hạn hiệu năng.

## 8. Vì sao offset pagination có thể lặp hoặc mất phần tử?

Giả sử sắp xếp mới nhất trước, kích thước trang 2:

~~~text
Trước khi gọi trang 0: [D, C, B, A]
Trang 0 (skip 0, limit 2): [D, C]

Sau đó xuất hiện bản ghi E mới hơn D:
Danh sách mới: [E, D, C, B, A]

Trang 1 (skip 2, limit 2): [C, B]
~~~

Kết quả: **C xuất hiện hai lần**. Nếu document bị xóa hoặc đổi vị trí sort, có thể xảy ra trường hợp **bỏ sót** một phần tử. `Slice.hasNext` chỉ phát hiện có phần tử sau offset tại thời điểm truy vấn; nó không giải quyết được việc các phần tử dịch chuyển giữa các request.

Các tình huống khác:

- Cập nhật `status` từ `ACTIVE` sang `INACTIVE` làm tập kết quả co lại.
- Nếu sort theo `updatedAt`, một bản ghi cũ được cập nhật có thể nhảy lên đầu danh sách.
- Một timestamp không đủ phân biệt thứ tự; nếu thiếu `_id` tie-breaker, truy vấn có thể trả trang khác nhau ngay cả khi không có insert/delete.
- Read preference tới secondary có thể quan sát dữ liệu trễ theo replication.

Do đó, nói “dùng Slice thì không trùng và không mất bản ghi” là **không chính xác**.

### Cách giảm rủi ro

1. Có sort **toàn phần và xác định**, dùng các field ít biến động và ID duy nhất.
2. Nếu nghiệp vụ cần duyệt xuyên qua tập thay đổi thường xuyên, ưu tiên keyset cursor.
3. Với tác vụ batch cần bảo đảm xử lý đủ tất cả bản ghi, dùng checkpoint/idempotency và thiết kế watermark hoặc snapshot phù hợp thay vì dùng một offset lớn làm checkpoint.
4. Với endpoint thường, chấp nhận dữ liệu thay đổi giữa các lượt và cho phép refresh; mô tả semantics rõ ràng trong API.

## 9. Khi nào nên dùng keyset/cursor thay cho Slice offset?

**Keyset pagination** là kỹ thuật nhớ khóa sort của phần tử cuối cùng đã hiển thị, rồi truy vấn những bản ghi **đứng sau khóa đó**. Nó có thể dùng cùng tư tưởng `size + 1` và `hasNext`, nhưng **không phải chỉ tăng số trang/skip**.

Giả sử sort `createdAt DESC, id DESC`. Phần tử cuối trang trước có:

~~~text
last.createdAt = 2026-11-20T08:00:00Z
last.id        = p-011
~~~

Điều kiện “đứng sau last” là:

~~~javascript
db.catalog_products.find({
  status: "ACTIVE",
  $or: [
    { created_at: { $lt: ISODate("2026-11-20T08:00:00Z") } },
    {
      created_at: ISODate("2026-11-20T08:00:00Z"),
      _id: { $lt: "p-011" }
    }
  ]
})
.sort({ created_at: -1, _id: -1 })
.limit(11);
~~~

Ta dùng `$lt` vì cả hai khóa đang sort **giảm dần**. Nếu sort tăng dần, điều kiện theo vị trí tiếp theo sẽ đổi tương ứng. Điều kiện này cần trùng khớp collation/kiểu dữ liệu của ID và index. Vì `_id` trong ví dụ là BSON String, so sánh chuỗi phải theo quy tắc sort đã chọn; nếu dùng kiểu khác phải điều chỉnh.

Với `MongoTemplate`, có thể diễn đạt filter sau cursor bằng `Criteria`:

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;

public Query afterCursor(Instant lastCreatedAt, String lastId, int size) {
    if (lastCreatedAt == null || lastId == null
            || lastId.isBlank() || size < 1 || size > 100) {
        throw new IllegalArgumentException("Cursor không hợp lệ");
    }

    Criteria after = new Criteria().orOperator(
            Criteria.where("createdAt").lt(lastCreatedAt),
            new Criteria().andOperator(
                    Criteria.where("createdAt").is(lastCreatedAt),
                    Criteria.where("id").lt(lastId)));

    Criteria filter = new Criteria().andOperator(
            Criteria.where("status").is("ACTIVE"), after);

    Query query = Query.query(filter);
    query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")));
    query.limit(size + 1);
    return query;
}
~~~

Đoạn này là phương thức xây dựng query, sử dụng sau với `mongo.find(query, CatalogProduct.class)` và kỹ thuật cắt `size+1` giống mục 6. Khi gọi MongoTemplate có entity type, Spring Data mapping `createdAt`/`id` thành `created_at`/`_id`.

**Giới hạn của keyset:** nó giảm chi phí skip và tránh tình huống insert mới *phía trước cursor* làm dịch offset, nhưng **không tạo snapshot giao dịch**. Nếu chính bản ghi đã đọc bị sửa khóa sort hoặc các bản ghi thỏa filter thay đổi, vẫn cần xác định semantics về tính nhất quán. Không dùng cursor thô do client sửa tùy ý: token production cần có version/điều kiện lọc, kiểm tra quyền/tenant, thời hạn nếu phù hợp và cơ chế chống sửa trái phép (ví dụ chữ ký).

Trong những phiên bản Spring Data hỗ trợ **scrolling API** với `ScrollPosition` và `Window<T>`, có thể dùng abstraction đó thay vì tự tạo cursor; hãy kiểm tra hỗ trợ cụ thể của Spring Data MongoDB và kết hợp đúng kiểu offset hoặc keyset position. `Window` là một khái niệm khác với `Slice`, không nên cho rằng chuyển kiểu trả về là đủ để biến offset pagination thành keyset.

## 10. Slice không phải streaming cursor

Tên chương *Phân trang và luồng* có thể khiến người học nhầm `Slice<T>` với Java `Stream<T>`:

| Khía cạnh | `Slice<T>` | `Stream<T>` / server cursor |
|---|---|---|
Hình thức | Một tập kết quả trang đã được materialize | Có thể duyệt tuần tự khi dữ liệu được fetch |
Vòng đời | Kết thúc truy vấn trang, response chứa một khối dữ liệu | Có thể giữ tài nguyên/cursor trong thời gian duyệt |
`hasNext` của trang | Có metadata `hasNext()` | Không phải contract biết “trang HTTP tiếp theo” |
Đóng tài nguyên | Không gửi `Slice` như cursor cần đóng | Stream/cursor cần đóng đúng cách, thường `try-with-resources` |
Ứng dụng điển hình | API danh sách, nút *Xem thêm* | Batch xử lý lớn, xuất dữ liệu có kiểm soát |

Một Java `Stream` từ repository có thể sử dụng hạ tầng cursor của MongoDB; không nên lưu stream như field trong service rồi xử lý kéo dài không kiểm soát. `Stream` không đương nhiên giải quyết lỗi retry, mất kết nối, checkpoint hoặc ordering.

Với Reactive MongoDB, API phổ biến trả `Flux<T>`/`Mono<T>` và dùng backpressure trong luồng xử lý, nhưng **reactive không đồng nghĩa tự động có metadata Slice**. Nếu cần một response có `hasNext`, có thể giới hạn `size+1` trong truy vấn, thu thập một khối hữu hạn rồi tính metadata.

Ví dụ minh họa ở service reactive, với `ReactiveMongoTemplate reactiveMongo`:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Mono<Boolean> hasMoreAfterFirstPage(
        ReactiveMongoTemplate reactiveMongo, int size) {
    if (size < 1 || size > 100) {
        return Mono.error(
                new IllegalArgumentException("size không hợp lệ"));
    }

    Query query = Query.query(Criteria.where("status").is("ACTIVE"));
    query.with(Sort.by(
            Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
    query.limit(size + 1);

    return reactiveMongo.find(query, CatalogProduct.class)
            .collectList()
            .map(items -> items.size() > size);
}
~~~

Đây chỉ là ví dụ **tính flag `hasMore`**, không phải API phân trang đầy đủ; muốn trả cả items phải cắt tập dữ liệu `size+1` và tạo response tương ứng. Tuy nhiên nó cho thấy không cần gọi `block()` để biến `Flux` thành một khối hữu hạn; `collectList()` tạo `Mono<List<T>>` trong pipeline reactive. Không dùng `collectList()` trên truy vấn **không giới hạn** nếu dữ liệu có thể rất lớn.

## 11. Kiểm thử Slice bằng MongoDB thật

Test bằng mock repository chỉ chứng minh service xử lý `hasNext` như được lập trình, không kiểm chứng cách Spring Data MongoDB áp dụng skip/sort/limit. Nên có integration test trên MongoDB thật, ví dụ dùng Testcontainers. `@DataMongoTest` tập trung vào phần mapping/repository của Spring Boot 3.x, nhưng **không tự khởi động MongoDB server**.

### 11.1. Test 23 sản phẩm, pageSize = 10

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataMongoTest
class CatalogProductSliceTest {
    @Autowired
    CatalogProductRepository products;

    private Pageable page(int number) {
        return PageRequest.of(number, 10,
                Sort.by(Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id")));
    }

    @BeforeEach
    void seedData() {
        products.deleteAll();
        products.saveAll(IntStream.rangeClosed(1, 23)
                .mapToObj(n -> new CatalogProduct(
                        "p-" + String.format("%03d", n),
                        "Product " + n,
                        "ACTIVE",
                        100_000L + n,
                        Instant.parse("2026-11-20T08:00:00Z")))
                .toList());
    }

    @Test
    void detectsLastSliceWithoutTotalCount() {
        Slice<CatalogProduct> first =
                products.findByStatus("ACTIVE", page(0));
        Slice<CatalogProduct> second =
                products.findByStatus("ACTIVE", page(1));
        Slice<CatalogProduct> third =
                products.findByStatus("ACTIVE", page(2));
        Slice<CatalogProduct> outside =
                products.findByStatus("ACTIVE", page(3));

        assertThat(first.getNumberOfElements()).isEqualTo(10);
        assertThat(first.hasNext()).isTrue();
        assertThat(first.hasPrevious()).isFalse();
        assertThat(first.getContent().get(0).id()).isEqualTo("p-023");

        assertThat(second.getNumberOfElements()).isEqualTo(10);
        assertThat(second.hasNext()).isTrue();
        assertThat(second.hasPrevious()).isTrue();
        assertThat(second.getContent().get(0).id()).isEqualTo("p-013");

        assertThat(third.getNumberOfElements()).isEqualTo(3);
        assertThat(third.hasNext()).isFalse();
        assertThat(third.getContent().get(0).id()).isEqualTo("p-003");

        assertThat(outside.getContent()).isEmpty();
        assertThat(outside.hasNext()).isFalse();
    }
}
~~~

Tất cả bản ghi có cùng `createdAt` để test **tie-breaker bằng `id`**. Vì ID được lưu theo BSON String với định dạng `p-001` đến `p-023`, sort giảm dần theo `_id` cho thứ tự xác định.

Đừng dùng `deleteAll()` trên database chia sẻ giữa nhiều test đang chạy song song. Dùng database cô lập hoặc bộ dữ liệu test riêng; test này chỉ là ví dụ cấu trúc.

### 11.2. Các trường hợp biên cần kiểm chứng

| Dữ liệu phù hợp | pageSize | Số phần tử trang hiện tại | `hasNext` mong đợi |
|---:|---:|---:|---|
| 0 | 10 | 0 | `false` |
| 1 | 10 | 1 | `false` |
| 10 | 10 | 10 | `false` |
| 11 | 10 | 10 | `true` ở trang 0 |
| 20 | 10 | 10 | `true` ở trang 0, `false` ở trang 1 |
| 23 | 10 | 3 | `false` ở trang 2 |

Đặc biệt **10 bản ghi đúng bằng pageSize** khác với 11 bản ghi: nếu không có “bản ghi cộng một”, chỉ nhìn kích thước trang đầu sẽ không xác định được `hasNext`.

Các test bổ sung:

1. Filter `status = ACTIVE` loại đúng sản phẩm khác trạng thái.
2. Nhiều sản phẩm có cùng `createdAt` vẫn không trùng/bỏ sót **khi tập dữ liệu không đổi** vì có `id` tie-breaker.
3. Cập nhật/insert xen giữa các lần tải offset để quan sát bản ghi bị dịch vị trí; không đánh dấu đây là lỗi `Slice`.
4. Tham số `page < 0`, `size = 0` hoặc `size` quá lớn bị từ chối tại boundary.
5. Truy vấn có projection DTO không vô tình lộ trường nội bộ và không tải document quá lớn khi không cần.
6. Kiểm tra hành vi sau khi xóa bản ghi ở trang trước và sau cursor; từ đó quyết định API dùng offset hay keyset.

## 12. Quan sát BSON command, count và query plan

Để biết repository thực sự gửi gì, có thể dùng MongoDB Java Driver `CommandListener` và `CommandStartedEvent` trong integration test hoặc MongoDB profiler khi được phép. Một lệnh find có cấu trúc tương đương:

~~~json
{
  "find": "catalog_products",
  "filter": { "status": "ACTIVE" },
  "sort": { "created_at": -1, "_id": -1 },
  "skip": 10,
  "limit": 11
}
~~~

Ví dụ minh họa **không phải cam kết byte-for-byte** về BSON command do Spring Data sinh ra. Driver/framework có thể dùng tên command, limit, cursor batch size hoặc cấu trúc tương đương khác; test cần dựa trên semantics đã quan sát.

Những điều nên xác minh:

- `filter` thực sự là `status = ACTIVE` và không quên điều kiện tenant/quyền.
- `sort` có thứ tự hoàn chỉnh (`created_at`, `_id`) với chiều phù hợp.
- Query không thực hiện count chỉ để trả total count mà API không cần; nếu có command khác do hạ tầng/test sinh ra phải phân loại chính xác.
- Có đọc đúng khoảng `size + 1` phần tử để xác định trang tiếp theo.
- Index có hỗ trợ filter/sort và `skip` lớn làm tăng chi phí ra sao.

Nếu dùng `Page` thay `Slice`, so sánh số command và thời gian thực tế. Trên một số phiên bản và trường hợp nhất định, Page có thể bỏ bớt count; đừng viết test bắt buộc rằng luôn có thêm một lệnh `count`.

`CommandListener` có thể nhìn thấy filter chứa thông tin nhạy cảm. Không bật log toàn bộ command trong production nếu không có kiểm soát quyền, thời gian lưu và quy tắc ẩn dữ liệu phù hợp.

## 13. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
Trả `Page` khi UI chỉ cần *Xem thêm* | Có thể phải trả chi phí total count không cần thiết | Ưu tiên `Slice` khi không cần tổng |
Giả định `Slice` cung cấp tổng bản ghi | Viết API sai, phụ thuộc method không tồn tại | Dùng `Page` hoặc truy vấn count tường minh nếu thật sự cần |
Lấy đúng `size` record rồi đoán `hasNext = (size == pageSize)` | Bị sai khi kết quả có đúng số phần tử bằng pageSize | Lấy `size + 1` hoặc dùng `Slice` hỗ trợ sẵn |
Không sort hoặc sort theo timestamp trùng nhau | Trang trả phần tử không ổn định | Thêm ID duy nhất làm tie-breaker |
Dùng `updatedAt` làm sort và kỳ vọng không dịch dữ liệu | Bản ghi nhảy giữa các trang khi cập nhật | Dùng khóa ít đổi hoặc cursor/snapshot phù hợp |
Tin `Slice` ngăn duplicate dưới concurrent insert | Lặp/bỏ sót do offset dịch | Hiểu semantics, cân nhắc keyset |
Cho rằng `Slice` luôn nhanh ở mọi số trang | `skip` sâu vẫn phải bỏ qua nhiều dữ liệu | Kiểm tra explain, giới hạn độ sâu hoặc đổi scrolling |
Trả nguyên entity trong response | Tăng payload, có thể lộ field nội bộ | Map DTO và kiểm tra projection BSON |
Xử lý `hasNext` bằng count toàn collection | Mất lợi ích tránh total count | Dùng phần tử bổ sung hoặc abstraction hỗ trợ |
Đọc `Slice` như một server cursor mở qua HTTP | Nhầm vòng đời dữ liệu và resource | Phân biệt Slice, Stream, Flux và Window |
Chỉ test trang đầu có nhiều dữ liệu | Không bắt lỗi trang cuối đúng bằng pageSize | Test 0, 1, N, N+1 và nhiều trang |
Truyền cursor không xác thực từ client | Sai filter hoặc lộ dữ liệu giữa tenant | Kiểm tra token, trạng thái lọc và quyền |

## 14. Bài tập thực hành

**Bài 1 — Repository Slice.** Tạo `CatalogProduct` và `CatalogProductRepository.findByStatus(status, pageable)`. Seed 23 sản phẩm ACTIVE và gọi các trang 0, 1, 2 với `size = 10`. Ghi lại số phần tử và `hasNext/hasPrevious`.

**Bài 2 — Phần tử cộng một.** Tự viết `MongoTemplate` trả `SliceImpl` với `skip`, `limit(size + 1)` và `List.subList`. Test trường hợp có đúng 10, 11, 20, 21 bản ghi khi `size = 10`.

**Bài 3 — Sort ổn định.** Cho 20 document cùng `createdAt`. So sánh truy vấn chỉ sort theo `createdAt` với truy vấn thêm `_id`. Giải thích vì sao cần tie-breaker và thiết kế compound index tương ứng.

**Bài 4 — Page hay Slice?** Xây dựng hai endpoint: endpoint A hiển thị `totalPages`, endpoint B chỉ có nút *Xem thêm*. Chọn kiểu trả về, đo số command và chi phí count trên MongoDB thật, không giả định mọi phiên bản luôn thực hiện số lệnh cố định.

**Bài 5 — Dữ liệu thay đổi giữa các trang.** Với danh sách [D,C,B,A] và size 2, thêm E ở đầu sau khi đọc trang 0. Gọi trang 1 bằng offset, chỉ ra phần tử trùng. Chuyển sang cursor theo cặp (`createdAt`, `id`) rồi quan sát sự khác biệt.

**Bài 6 — Trang sâu.** Tạo dữ liệu đủ lớn và so sánh `skip(0)`, `skip(1000)`, `skip(50000)` với cùng size/sort/index. Dùng `explain("executionStats")` ghi số keys/docs examined và độ trễ; đề xuất giới hạn offset.

**Bài 7 — Reactive slice-like response.** Dùng `ReactiveMongoTemplate` để lấy tối đa `size + 1` phần tử, tạo `Mono` mang `items` và `hasNext` mà không gọi `block()`. Kiểm tra bộ nhớ khi tăng `size` và phân biệt việc thu thập một page hữu hạn với streaming toàn collection.

## 15. Ghi nhớ

Trong **Spring Data MongoDB**, `Slice<T>` thích hợp khi ứng dụng cần **một trang dữ liệu và câu trả lời “còn trang tiếp theo không?”** mà không cần tổng số document. `Slice.hasNext()` có thể được xác định từ **phần tử thứ `pageSize + 1`** theo cùng filter và sort; `Page<T>` dùng khi thực sự cần metadata tổng số.

Để có kết quả đáng tin cậy, hãy **lọc trong MongoDB, dùng sort xác định với khóa duy nhất làm tie-breaker, giới hạn page size và kiểm tra index/query plan**. `Slice` tránh nhu cầu total count nhưng **không loại bỏ chi phí offset `skip` hoặc bảo đảm snapshot khi dữ liệu thay đổi giữa các request**. Với scrolling sâu, cân nhắc keyset cursor/`Window`; với xử lý luồng, phân biệt `Slice` khỏi `Stream` và `Flux`.

Cuối cùng, hãy kiểm thử trang rỗng, trang đúng bằng pageSize, trang còn đúng một bản ghi bổ sung, trang cuối và tình huống insert/delete xen giữa các lượt đọc. Chính các ca biên này quyết định nút *Xem thêm* có hoạt động đúng ngoài thực tế hay không.
