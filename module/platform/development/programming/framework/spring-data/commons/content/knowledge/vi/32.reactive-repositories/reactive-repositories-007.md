# Giới hạn Page, count, Sort và Pageable theo triển khai

## 1. Reactive không tự biến mọi truy vấn thành một Page

Trong chương **Repository reactive** của module **SPRING_DATA_COMMONS**, cần phân biệt hai lớp:

- Các abstraction dùng chung như `Page`, `Slice`, `Pageable` và `Sort`.
- Khả năng thực thi truy vấn, phân trang và đếm của một module lưu trữ cụ thể.

Một kiểu dữ liệu có mặt trong Spring Data Commons không có nghĩa mọi reactive repository đều hỗ trợ dùng kiểu đó ở mọi chữ ký phương thức.

Ví dụ, ba kết quả sau có ý nghĩa khác nhau:

~~~java
Flux<Product> content;
Mono<Long> total;
Mono<Page<Product>> response;
~~~

`content` là luồng sản phẩm. `total` là một kết quả đếm. `response` là một đối tượng trang có thể được service tự ghép từ nội dung và metadata.

Không nên suy rằng chỉ cần khai báo một derived query trả `Mono<Page<Product>>` là framework tự thực hiện cả query nội dung và query đếm cho mọi reactive store.

Mục tiêu của bài là xác định rõ phần nào thuộc hợp đồng chung, phần nào phải do ứng dụng điều phối và phần nào phụ thuộc triển khai của kho dữ liệu.

## 2. Mỗi abstraction mô tả điều gì?

| Abstraction | Mô tả | Không tự bảo đảm |
| --- | --- | --- |
| `Sort` | Các thuộc tính và chiều sắp xếp | Store hỗ trợ mọi thuộc tính, null ordering hoặc collation được yêu cầu |
| `Pageable` | Yêu cầu vị trí trang, kích thước và sort; có thể biểu diễn yêu cầu không phân trang | Repository tự thực thi được mọi dạng paging |
| `Page<T>` | Nội dung trang cùng metadata tổng số phần tử và số trang | Total được truy vấn chính xác, rẻ hoặc cùng snapshot với nội dung |
| `Slice<T>` | Một phần nội dung cùng thông tin còn phần tiếp theo hay không | Có tổng số phần tử hoặc cho phép nhảy tới trang cuối |
| `Flux<T>` | Luồng từ không đến nhiều phần tử | Có sẵn tổng số phần tử hay metadata phân trang |
| `Mono<Long>` từ count | Một kết quả đếm khi publisher được thực thi | Count có cùng bộ lọc hoặc cùng thời điểm quan sát với query nội dung |

`Pageable` là mô tả yêu cầu. `Page` và `Slice` là mô tả kết quả. Không nên coi một đối số `Pageable` là lời hứa rằng kết quả sẽ là `Page`.

### 2.1. PageImpl là một đối tượng kết quả

Ứng dụng có thể tạo:

~~~java
Page<Product> page =
        new PageImpl<>(content, pageable, total);
~~~

Lúc này, `content`, `pageable` và `total` phải được cung cấp bởi code của ứng dụng. Constructor không tự gửi query tới database.

Đóng gói dữ liệu vào `PageImpl` cũng không làm hai query đã chạy ở những thời điểm khác nhau trở thành một snapshot nhất quán.

### 2.2. Reactive Page vẫn cần gom nội dung của một trang

Nếu API trả một `Mono<Page<T>>`, nó thường phải chờ có nội dung trang và metadata cần thiết trước khi phát đối tượng kết quả.

Đây khác với một `Flux<T>` có thể phát từng phần tử. Việc chọn `Page` là một lựa chọn về hình dạng response, không phải cách duy nhất để một API reactive trả danh sách.

## 3. Các interface reactive không sao chép nguyên API đồng bộ

Các chữ ký tiêu biểu cần nhận diện:

| Hợp đồng | Method tiêu biểu | Kết quả |
| --- | --- | --- |
| `ReactiveCrudRepository<T, ID>` | `findAll()` | `Flux<T>` |
| `ReactiveCrudRepository<T, ID>` | `count()` | `Mono<Long>` |
| `ReactiveSortingRepository<T, ID>` | `findAll(Sort sort)` | `Flux<T>` |
| Query method của module có hỗ trợ | Method nhận `Pageable` | Thường dùng luồng nội dung theo khả năng của module |

Không nên mặc định `ReactiveCrudRepository` có sẵn một method `findAll(Pageable)` trả kết quả như repository phân trang đồng bộ.

Cũng không nên suy rằng chỉ kế thừa sorting repository là chắc chắn đã có mọi CRUD method. Cần chọn đúng interface của module hoặc kết hợp các interface cần thiết theo API của phiên bản đang dùng.

Ví dụ, một interface cụ thể của R2DBC hoặc reactive MongoDB có thể tập hợp nhiều khả năng. Việc tổng hợp đó thuộc interface module, không làm mọi repository khác có cùng API.

### 3.1. Kiểu bọc reactive không tự bổ sung khả năng query

Các khai báo như sau không phải công thức dùng chung cho mọi module:

~~~java
Mono<Page<Product>> findByCategory(String category, Pageable page);
Flux<Page<Product>> findByCategory(String category, Pageable page);
~~~

Phải kiểm tra query method và return type mà module hỗ trợ. Reactive repository có thể hỗ trợ nhận `Pageable` để giới hạn nội dung nhưng không hỗ trợ tự sinh một kết quả `Page` với total.

Ngược lại, một **service do ứng dụng viết** hoàn toàn có thể trả `Mono<Page<Product>>` bằng cách tự điều phối query. Hai trường hợp này không mâu thuẫn.

## 4. Pageable có thể chỉ áp dụng limit và offset

Một derived query được module hỗ trợ có thể có dạng:

~~~java
Flux<Product> findByCategoryAndActiveTrue(
        String category,
        Pageable pageable);
~~~

Theo hợp đồng của query đó, framework có thể chuyển yêu cầu trang thành giới hạn số dòng, vị trí bắt đầu và sort tương ứng của store.

Điều này chưa tự cung cấp:

- Tổng số sản phẩm thỏa điều kiện.
- Tổng số trang.
- Một truy vấn count bổ sung.
- Snapshot chung giữa nội dung và một query khác.

Ví dụ, nhận được 20 phần tử với page size 20 không cho biết toàn bộ tập dữ liệu có 20, 21 hay hàng triệu phần tử.

### 4.1. Vị trí trang và offset

Với phân trang theo offset:

~~~text
offset = pageNumber × pageSize
~~~

`PageRequest` dùng chỉ số trang bắt đầu từ 0. Trang số 2, kích thước 20 có offset 40.

Ứng dụng nên xác định rõ quy ước API nếu giao diện hiển thị trang bắt đầu từ 1. Không trừ hoặc cộng 1 tùy tiện ở nhiều lớp.

### 4.2. Unpaged không phải một kích thước trang rất lớn

`Pageable` có thể biểu diễn yêu cầu không phân trang. Không phải mọi method xử lý pageable đều nên gọi `getOffset()` hoặc `getPageSize()` mà bỏ qua trạng thái đó.

Nếu endpoint bắt buộc phân trang, nên xác thực yêu cầu và chỉ tạo `PageRequest` có giới hạn. Nếu cho phép unpaged, phải có nhánh xử lý và hợp đồng tài nguyên riêng.

## 5. Count là một truy vấn có phạm vi và chi phí riêng

`repository.count()` thường đếm toàn bộ entity trong phạm vi repository, không tự mang lại các điều kiện đã dùng ở một query nội dung khác.

Ví dụ sai về ý nghĩa:

~~~java
Flux<Product> content =
        repository.findByCategoryAndActiveTrue("BOOK", pageable);

Mono<Long> total = repository.count();
~~~

Nếu repository còn chứa sản phẩm thuộc nhóm khác hoặc đã ngừng hoạt động, total không tương ứng nội dung đang phân trang.

Một count phù hợp cần cùng điều kiện nghiệp vụ:

~~~java
Mono<Long> countByCategoryAndActiveTrue(String category);
~~~

Ngoài category và active, còn phải xét tenant, quyền truy cập, xóa mềm và mọi bộ lọc khác của endpoint.

### 5.1. Đếm tập kết quả nào?

Với query đơn giản, total có thể là số entity thỏa predicate. Với join, distinct, group hoặc projection phức tạp, cần xác định đơn vị được đếm.

Ví dụ, một sản phẩm có ba dòng liên quan có thể xuất hiện ba lần trong kết quả join thô. `COUNT(*)` trên phép join không tự là số sản phẩm duy nhất.

Count của một truy vấn nhóm cũng có thể cần đếm số nhóm thay vì số dòng nguồn. Không sao chép một count đơn giản vào mọi custom query.

### 5.2. Flux.count khác repository count

Xét:

~~~java
repository.findByCategoryAndActiveTrue(category, pageable)
        .count();
~~~

Phép `count()` của Reactor đếm số phần tử được luồng đó phát. Nếu query đã bị giới hạn theo trang, nó thường chỉ đếm nội dung của trang, không phải tổng tập kết quả trước phân trang.

Ngược lại, gọi `findAll().count()` có thể yêu cầu đọc toàn bộ luồng dữ liệu để đếm. Nó không tự được tối ưu thành một câu count tại store chỉ vì cuối pipeline có operator tên `count`.

Khi cần count tại database, dùng API hoặc query count phù hợp với module.

### 5.3. Reactive không làm count miễn phí

Reactive giúp mô tả và điều phối I/O theo mô hình không blocking phù hợp. Nó không loại bỏ công việc mà database phải làm để xác định số lượng.

Count chính xác trên một tập lớn có thể phải duyệt nhiều entry, xử lý predicate hoặc thực hiện một kế hoạch riêng. Index có thể giúp, nhưng không nên mặc định mọi count đều là một lần đọc metadata có chi phí cố định.

Nếu dùng giá trị ước lượng, cache hoặc metadata thống kê, phải mô tả đúng đó là một total ước lượng hoặc có độ trễ. Không trình bày như total chính xác của cùng query mà thiếu hợp đồng rõ ràng.

## 6. Sort cần được store dịch và hỗ trợ

`Sort` mô tả thuộc tính và chiều sắp xếp, ví dụ:

~~~java
Sort sort = Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"));
~~~

Việc thực thi còn phụ thuộc:

- Mapping giữa tên property trong model và field hoặc cột lưu trữ.
- Khả năng sắp xếp theo field đó của store.
- Index và query plan.
- Quy tắc null, collation và kiểu dữ liệu.
- Hình dạng query, chẳng hạn join hoặc projection có alias.

Không tự coi một tên field trong DTO là một property persistence hợp lệ.

### 6.1. Cần khóa phân biệt khi phân trang

Nếu chỉ sort theo `createdAt`, nhiều sản phẩm có thể cùng timestamp. Store không bắt buộc trả các dòng bằng nhau theo một thứ tự ổn định khác mà ứng dụng chưa chỉ định.

Thêm một khóa phân biệt phù hợp, chẳng hạn `id`, giúp xác định thứ tự giữa các dòng cùng thời gian trong tập dữ liệu được quan sát.

Điều này chưa ngăn mọi dịch chuyển trang khi dữ liệu bị thêm hoặc xóa giữa hai request. Thứ tự xác định và snapshot ổn định là hai yêu cầu khác nhau.

### 6.2. Kiểm soát sort từ client

Một API nên ánh xạ các khóa sort được cho phép sang property đã biết. Không truyền nguyên một chuỗi bất kỳ từ client vào mọi loại query.

Ngoài tính hợp lệ, còn cần kiểm soát chi phí. Một property được mapping đúng nhưng không có đường truy vấn hiệu quả vẫn có thể gây sort lớn.

Các tùy chọn như bỏ qua hoa thường hoặc null ordering cũng cần được đối chiếu với module và store; một hint trong abstraction không tự trở thành tính năng được mọi backend thực hiện giống nhau.

## 7. Ví dụ R2DBC: service tự ghép Page từ nội dung và count

Ví dụ sau dùng Spring Data R2DBC, Reactor và Java hỗ trợ `record`. Mỗi public type được đặt trong một file riêng. Ứng dụng cung cấp connection factory, mapping và quét repository phù hợp.

Điểm cần thấy là repository trả `Flux` và `Mono<Long>`, còn service tạo `Page`. Ví dụ không tuyên bố mọi reactive store hỗ trợ nguyên các chữ ký này.

### 7.1. Entity và dữ liệu trả về

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String category,
        boolean active,
        BigDecimal price,
        Instant createdAt) {
}
~~~

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record ProductView(
        Long id,
        String category,
        BigDecimal price,
        Instant createdAt) {

    public static ProductView from(Product product) {
        return new ProductView(
                product.id(),
                product.category(),
                product.price(),
                product.createdAt());
    }
}
~~~

### 7.2. Repository có query nội dung và query count riêng

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.r2dbc.repository.R2dbcRepository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends R2dbcRepository<Product, Long> {

    Flux<Product> findByCategoryAndActiveTrue(
            String category,
            Pageable pageable);

    Mono<Long> countByCategoryAndActiveTrue(String category);
}
~~~

Hai method dùng cùng category và cùng điều kiện active. Sort và giới hạn trang chỉ áp dụng cho query nội dung; query total không đếm riêng phần đã bị cắt theo trang.

### 7.3. Service giới hạn đầu vào và ghép kết quả

~~~java
import java.util.Objects;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProductPageService {

    private final ProductRepository products;

    public ProductPageService(ProductRepository products) {
        this.products = products;
    }

    public Mono<Page<ProductView>> findPage(
            String category,
            int page,
            int size,
            String sortKey,
            Sort.Direction direction) {

        return Mono.defer(() -> {
            if (category == null || category.isBlank()) {
                throw new IllegalArgumentException(
                        "category is required");
            }

            Pageable pageable = createPageable(
                    page, size, sortKey, direction);

            return products
                    .findByCategoryAndActiveTrue(category, pageable)
                    .map(ProductView::from)
                    .collectList()
                    .flatMap(content -> products
                            .countByCategoryAndActiveTrue(category)
                            .<Page<ProductView>>map(total ->
                                    new PageImpl<>(
                                            content,
                                            pageable,
                                            total)));
        });
    }

    private Pageable createPageable(
            int page,
            int size,
            String sortKey,
            Sort.Direction direction) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page must be non-negative and size must be 1..100");
        }

        Objects.requireNonNull(direction, "direction");

        String property = switch (
                sortKey == null ? "createdAt" : sortKey) {
            case "createdAt" -> "createdAt";
            case "price" -> "price";
            default -> throw new IllegalArgumentException(
                    "Unsupported sort key");
        };

        Sort sort = Sort.by(direction, property)
                .and(Sort.by(direction, "id"));

        return PageRequest.of(page, size, sort);
    }
}
~~~

Giới hạn 100 là một chính sách minh họa của endpoint, không phải giới hạn chung của Spring Data.

`Mono.defer` đặt việc tạo pipeline và xác thực trong lúc publisher được subscribe. Method không tự gọi `subscribe()` hay `block()` để lấy dữ liệu.

`collectList()` ở đây gom **nội dung trang đã được giới hạn tại query**. Nó không phải cách tải toàn bộ repository rồi cắt trong bộ nhớ.

Code chạy query count sau khi nội dung đã được gom. Đây là lựa chọn điều phối dễ thấy, không phải một bảo đảm hai query đọc cùng snapshot.

## 8. Hai query có thể quan sát hai trạng thái dữ liệu

Giả sử:

~~~text
t0: query nội dung lấy 20 sản phẩm.
t1: một transaction khác thêm hoặc xóa sản phẩm.
t2: query count đọc tổng số mới.
~~~

Nội dung và total có thể đều đúng đối với từng lần đọc nhưng không mô tả một ảnh chụp chung.

Đổi thứ tự count trước, nội dung sau chỉ đổi chiều khoảng trống; không tự loại bỏ nó.

Nếu API chấp nhận dữ liệu đang thay đổi và total mang tính tức thời, có thể mô tả hợp đồng đó. Nếu cần một snapshot chung, phải kiểm tra khả năng transaction, isolation hoặc snapshot read của store.

### 8.1. Có transaction chưa chắc là cùng snapshot cho mọi câu lệnh

Mức cô lập và hành vi database quyết định hai câu lệnh trong transaction nhìn thấy gì. Không nên chỉ thêm `@Transactional` rồi mặc định mọi lần đọc đều nhìn cùng một phiên bản dữ liệu.

Trong ứng dụng reactive, cũng phải dùng hạ tầng transaction reactive phù hợp và giữ các publisher trong đúng pipeline/ngữ cảnh. Tự mở một subscription phụ có thể phá ranh giới cần kiểm soát.

### 8.2. Mono.zip không làm hai query trở thành một query nguyên tử

Ứng dụng có thể ghép một publisher nội dung với một publisher count bằng `Mono.zip`. Việc ghép này không tự bảo đảm:

- Cùng transaction hoặc cùng connection.
- Cùng snapshot.
- Hai câu lệnh được chạy song song thật sự.
- Driver cho phép mọi cách chạy đồng thời trên một connection giao dịch.

Nếu dùng một connection trong reactive transaction, cần đối chiếu khả năng điều phối của driver. Không dùng `zip` như một mẹo mặc định để vừa tăng tốc vừa đạt tính nhất quán.

## 9. Trang rỗng không có nghĩa total bằng 0

Một yêu cầu có offset vượt phần cuối tập kết quả có thể nhận nội dung rỗng dù tập dữ liệu vẫn có nhiều phần tử.

Ví dụ:

~~~text
total = 35
page  = 5
size  = 10
offset = 50
content = []
~~~

Trả total bằng 0 chỉ vì `content` rỗng sẽ diễn giải sai toàn bộ tập dữ liệu.

Điều này cũng quan trọng khi tối ưu count. Có thể có những trường hợp suy ra total từ nội dung và vị trí trang theo một hợp đồng nhất định, nhưng không được áp dụng một quy tắc “trang rỗng thì total 0” cho mọi trang.

### 9.1. Không che lỗi count bằng một total giả

Mẫu sau làm mất ý nghĩa của metadata:

~~~java
repository.countByCategoryAndActiveTrue(category)
        .onErrorReturn(0L);
~~~

Nếu count lỗi do kết nối, quyền truy cập hoặc query không hợp lệ, giá trị 0 không phải câu trả lời chính xác.

Có thể chọn trả lỗi cho response cần total, hoặc thiết kế một kiểu response cho phép total không có/không xác định. Không giả vờ đã biết total bằng một fallback thuận tiện.

## 10. Slice có thể bỏ nhu cầu count toàn bộ

Nếu giao diện chỉ cần “có trang tiếp theo không”, một hợp đồng giống `Slice` có thể phù hợp hơn `Page`.

Kỹ thuật phổ biến là yêu cầu thêm một phần tử:

~~~text
offset     = page × size
fetchLimit = size + 1

rows       = query(offset, fetchLimit)
hasNext    = rows.size > size
content    = size phần tử đầu tiên, hoặc ít hơn nếu hết dữ liệu
~~~

Không cần một query total chỉ để biết có phần tiếp theo ở thời điểm đọc.

### 10.1. Bẫy đổi page size khi lấy phần tử dư

Không nên đơn giản thay:

~~~java
PageRequest.of(page, size);
~~~

bằng:

~~~java
PageRequest.of(page, size + 1);
~~~

rồi cho rằng offset vẫn đúng.

Với page 2, size 20:

~~~text
offset cần giữ       = 2 × 20 = 40
offset sau đổi size  = 2 × 21 = 42
~~~

Nếu query nhận độc lập offset và limit, có thể giữ offset 40 và lấy tối đa 21 dòng. Nếu dùng một abstraction khác để biểu diễn yêu cầu, phải bảo đảm nó thực sự giữ nguyên quy tắc vị trí.

### 10.2. Phải thực thi giới hạn tại store khi có thể

Một query tùy biến theo dialect có thể biểu diễn ý định:

~~~sql
SELECT id, category, active, price, created_at
FROM product
WHERE category = :category
  AND active = TRUE
ORDER BY created_at DESC, id DESC
LIMIT :fetchLimit OFFSET :offset
~~~

Đây là mẫu SQL cho dialect có cú pháp tương ứng, không phải câu query di động cho mọi backend. Cách bind limit/offset và mapping kết quả cần theo API của module và driver đang dùng.

Sau khi gom tối đa `size + 1` dòng, ứng dụng có thể tạo `SliceImpl` với pageable gốc và `hasNext` đã xác định.

Slice giảm nhu cầu count, nhưng không tự loại bỏ chi phí offset lớn hoặc thay đổi dữ liệu giữa các request.

## 11. Phân trang trong Flux không luôn là phân trang tại database

Các đoạn code sau cần được hiểu đúng:

~~~java
repository.findAll()
        .skip(offset)
        .take(size);
~~~

~~~java
repository.findAll()
        .sort(comparator)
        .skip(offset)
        .take(size);
~~~

`skip`, `take` và `sort` ở đây là operator trên luồng kết quả. Không nên mặc định chúng được dịch ngược thành `OFFSET`, `LIMIT` và `ORDER BY` của query nguồn.

Đặc biệt, sort của Flux cần gom dữ liệu để sắp xếp theo comparator. Nó khác với yêu cầu `Sort` được module chuyển vào truy vấn store.

Backpressure có thể điều tiết demand và cách nhận dữ liệu theo khả năng của driver. Nó không tự thay thế predicate, index hoặc giới hạn logic của truy vấn.

Nếu endpoint cần đúng một cửa sổ nhỏ của một tập lớn, ưu tiên đưa điều kiện, sort và giới hạn vào query được store thực thi.

## 12. Offset lớn có thể cần một cách truy cập khác

Ngay cả khi chỉ trả 20 phần tử, một query ở offset rất lớn có thể phải bỏ qua nhiều dòng hoặc thực hiện công việc đáng kể tại store.

Nếu chỉ cần đi tiếp theo một thứ tự, có thể xem xét keyset/cursor pagination theo khả năng backend.

Ví dụ với thứ tự giảm dần theo `created_at`, sau đó `id`, query tiếp theo có thể có ý tưởng:

~~~sql
SELECT id, category, active, price, created_at
FROM product
WHERE category = :category
  AND active = TRUE
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :fetchLimit
~~~

Ví dụ giả định các khóa sort có quy tắc so sánh phù hợp và không có null chưa được xử lý. Với thứ tự khác, predicate cursor cũng phải thay đổi tương ứng.

Cursor cần giữ đủ khóa phân biệt, bộ lọc liên quan và quy tắc xác thực của API. Nó không tự cho tổng số trang hay khả năng nhảy tới một page number tùy ý.

Các abstraction scrolling của Commons, nếu được dùng, vẫn cần được đối chiếu khả năng triển khai của module. Không suy rằng có một kiểu cursor là mọi store đã thực hiện cùng chiến lược.

## 13. Derived query và query viết tay có thể có giới hạn khác nhau

Một module có thể hiểu `Pageable` ở derived query nhưng không tự thêm paging hoặc sort động vào mọi query string do người dùng viết.

Với `@Query`, custom repository hoặc template API, cần xác định:

1. Special parameter nào thực sự được nhận diện.
2. Query có được framework viết lại hay không.
3. Sort đã có sẵn trong query hay do framework bổ sung.
4. Limit/offset cần bind tường minh hay được module áp dụng.
5. Count có phải một query riêng với logic tương đương hay không.

Không truyền thêm `Pageable` vào chữ ký rồi coi một câu SQL hoặc một truy vấn document bất kỳ đã tự được phân trang.

Nếu sort động được xây vào query viết tay, hãy dùng ánh xạ các biểu thức được cho phép. Giá trị bind và tên cột/biểu thức query là các thành phần có cách xử lý khác nhau; không nối nguyên chuỗi sort chưa được kiểm soát.

## 14. Đối chiếu theo nhóm triển khai

| Nhóm triển khai | Cách đặt câu hỏi đúng |
| --- | --- |
| Spring Data Commons | Interface có mô tả capability này không, hay chỉ cung cấp kiểu dữ liệu dùng chung? |
| Spring Data R2DBC | Derived query, query string và dialect đang dùng áp dụng sort/limit/offset ra sao; count được viết như thế nào? |
| Reactive MongoDB | Query method hoặc template áp dụng sort, skip, limit thế nào; count có cùng filter và loại count phù hợp không? |
| Backend dùng paging state, chẳng hạn Cassandra | Có thể đi theo trạng thái phân trang của backend hay thực sự hỗ trợ nhảy offset tùy ý? |
| Module tìm kiếm hoặc backend khác | Metadata total, ngưỡng/độ chính xác của total và abstraction kết quả riêng có hợp đồng gì? |

Đây là các điểm cần đối chiếu, không phải tuyên bố mọi module có cùng method và cùng return type.

Ví dụ, không lấy khả năng SQL `LIMIT/OFFSET` làm giả định cho một backend vốn phân trang bằng continuation token hoặc paging state. Cũng không tự coi một total do hệ thống tìm kiếm trả về là count chính xác vô điều kiện của mọi tập dữ liệu.

Khi mở rộng repository hoặc dùng custom implementation, ghi rõ capability đã cung cấp. Một interface tự khai báo method có tên quen thuộc không làm backend tự có khả năng tương ứng.

## 15. Count và sort cần được đánh giá cùng query plan

Một trang nội dung có thể nhanh nhờ index đáp ứng filter và sort, trong khi count tương ứng vẫn chiếm phần lớn thời gian response.

Ngược lại, count có thể nhanh nhưng sort theo một field khác làm query nội dung phải xử lý nhiều dữ liệu.

Với ví dụ sản phẩm, một index kết hợp liên quan category, active, createdAt và id có thể là hướng đánh giá theo query shape. Nó không phải lời bảo đảm hiệu năng cho mọi database, phân bố dữ liệu hoặc cách sắp xếp.

Các câu hỏi thực tế:

- Có thể dùng index cho điều kiện và thứ tự đang chọn không?
- Page size và offset được giới hạn ra sao?
- Count chạy trên bao nhiêu dữ liệu và có thể bị gọi lại quá thường xuyên không?
- Có thật sự cần total ở mọi request không?
- Khi dữ liệu tăng, có cần Slice hoặc cursor không?

Nếu cache count, khóa cache phải phản ánh đúng phạm vi dữ liệu, bao gồm tenant và các điều kiện truy cập liên quan. Cache total không được làm lộ hoặc trộn số lượng giữa các phạm vi người dùng.

## 16. Các tình huống cần kiểm chứng

Bảng sau là tiêu chí thiết kế kiểm thử, không phải báo cáo đã chạy kiểm thử cho một phiên bản hoặc database cụ thể:

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Query category đang hoạt động | Nội dung và count dùng cùng predicate |
| Có nhiều category và dữ liệu inactive | Total không bị lấy từ count toàn repository |
| Trang đầu không có dữ liệu | Metadata phản ánh đúng tập kết quả |
| Offset vượt cuối tập kết quả | Nội dung rỗng không tự làm total thành 0 |
| Nhiều dòng cùng khóa sort chính | Khóa phân biệt tạo thứ tự xác định theo hợp đồng |
| Page size bằng 0, âm hoặc vượt giới hạn | Bị từ chối trước khi thực hiện query không hợp lệ |
| Sort key không được cho phép | Không biến thành query tùy ý |
| Count phát sinh lỗi | Không âm thầm trả total giả |
| Có ghi đồng thời giữa content và count | Hành vi phù hợp hợp đồng nhất quán đã chọn |
| Slice lấy dư một phần tử | Giữ đúng offset gốc và tính `hasNext` chính xác |
| Custom query nhận Pageable | Xác nhận limit/offset/sort thực sự được áp dụng |
| Đổi module hoặc dialect | Kiểm chứng lại return type và special parameter được hỗ trợ |

Unit test với repository mock có thể kiểm tra service truyền cùng category hoặc chặn sort không hợp lệ. Nó không đủ chứng minh module đã dịch pageable thành query đúng hoặc database dùng một query plan hiệu quả.

Đối với khả năng query của repository, cần kiểm chứng bằng store/driver phù hợp. Đối với reactive pipeline, cần phân biệt việc tạo publisher với việc subscribe và hoàn tất xử lý.

## 17. Những cách diễn giải cần tránh

**“Có Pageable thì luôn có Page.”**

Pageable có thể chỉ điều khiển phần nội dung. Metadata tổng số cần một nguồn riêng theo hợp đồng triển khai.

**“Đổi Page thành Mono<Page> là có reactive pagination tự động.”**

Kiểu bọc không tự làm query factory hỗ trợ return type đó. Service có thể tự ghép Page, nhưng repository generated query phải theo khả năng module.

**“Flux.count luôn là COUNT tại database.”**

Đó là operator đếm phần tử được phát bởi luồng. Một repository count query là một đường thực thi khác.

**“Reactive thì không cần quan tâm count chậm.”**

Mô hình I/O không loại bỏ chi phí truy vấn tại backend.

**“Sort của Flux và Sort của query là cùng một việc.”**

Một bên xử lý luồng ở ứng dụng; bên kia có thể được store thực thi. Vị trí xử lý quyết định lượng dữ liệu phải đọc và bộ nhớ cần dùng.

**“Chạy content và count bằng zip thì luôn nhất quán hơn.”**

Zip ghép kết quả publisher, không tự cung cấp transaction, snapshot hoặc khả năng chạy nhiều câu lệnh đồng thời trên một connection.

## 18. Tự kiểm tra kiến thức

1. Tại sao một method trả `Flux<Product>` và nhận `Pageable` có thể không cung cấp total?
2. Khi nào `Mono<Page<ProductView>>` là kết quả hợp lệ do service tạo, nhưng không phải một return type được query method của module tự hỗ trợ?
3. Vì sao `repository.count()` có thể sai khi dùng cho một query đã lọc tenant, category hoặc trạng thái?
4. `Flux.count()` sau một query đã phân trang đang đếm tập dữ liệu nào?
5. Vì sao cần thêm khóa phân biệt vào sort khi nhiều dòng có cùng timestamp?
6. Điều gì sai khi đổi size 20 thành 21 nhưng giữ page number để lấy phần tử dư cho Slice?
7. Vì sao một trang rỗng ở offset lớn không chứng minh toàn bộ tập kết quả rỗng?
8. Những giả định nào cần kiểm tra lại khi chuyển từ R2DBC sang một reactive store khác?

Thiết kế phân trang reactive cần bắt đầu từ khả năng của repository và backend: xác định query nội dung, nguồn total nếu cần, thứ tự và ranh giới nhất quán. Các abstraction của Commons giúp biểu diễn hợp đồng đó; chúng không tự thay thế phần triển khai và kiểm chứng tại store.
