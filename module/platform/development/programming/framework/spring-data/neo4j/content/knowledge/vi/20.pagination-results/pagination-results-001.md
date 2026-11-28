# Chọn entity đơn, `Optional`, `List`, `Page`, `Slice` hoặc `Stream` theo hỗ trợ

Kiểu trả về của một repository method cho biết ứng dụng mong đợi bao nhiêu kết quả và cần thông tin gì về tập kết quả đó. Trong Spring Data Neo4j (SDN), bạn có thể trả về một entity khi truy vấn bảo đảm tối đa một kết quả, dùng `Optional` khi kết quả có thể không tồn tại, dùng `List` cho một tập kết quả hữu hạn, hoặc chọn `Page`, `Slice` và `Stream` khi cần xử lý tập dữ liệu lớn theo cách phù hợp.

Chọn kiểu trả về đúng giúp hợp đồng repository thể hiện rõ nghiệp vụ và tránh tải quá nhiều dữ liệu vào bộ nhớ. Với `Page` và `Slice`, SDN cần tham số `Pageable` để biết vị trí, kích thước và thứ tự trang. Với `Stream`, ứng dụng phải quản lý vòng đời tài nguyên được mở trong lúc đọc kết quả.

## 1. Bắt đầu từ số lượng kết quả mong đợi

Trước khi chọn kiểu trả về, hãy trả lời ba câu hỏi:

1. Truy vấn có thể trả về không kết quả, đúng một kết quả hay nhiều kết quả?
2. Caller có cần toàn bộ kết quả, một phần kết quả hay chỉ cần duyệt tuần tự?
3. Caller có cần biết tổng số kết quả và tổng số trang hay chỉ cần biết còn dữ liệu tiếp theo không?

| Kiểu trả về | Số lượng kết quả | Metadata bổ sung | Trường hợp phù hợp |
|---|---|---|---|
| `Article` | Tối đa một | Không | Truy vấn chắc chắn trả về một entity hoặc chấp nhận `null` khi không có |
| `Optional<Article>` | Không hoặc một | Biểu diễn rõ trạng thái vắng mặt | Tìm theo mã duy nhất, slug hoặc ID |
| `List<Article>` | Không đến nhiều | Không | Tập kết quả nhỏ hoặc hữu hạn, cần xử lý toàn bộ |
| `List<Article>` cùng `Pageable` | Chỉ một đoạn kết quả | Không có tổng số trang | Cần giới hạn dữ liệu trả về nhưng không cần tổng số |
| `Page<Article>` | Một trang | Tổng phần tử và tổng số trang | Giao diện cần hiển thị số trang hoặc tổng số kết quả |
| `Slice<Article>` | Một lát dữ liệu | Có hoặc không có lát tiếp theo | Duyệt tuần tự mà không cần đếm toàn bộ |
| `Stream<Article>` | Duyệt tăng dần | Không có metadata phân trang | Xử lý nhiều kết quả tuần tự, tránh giữ toàn bộ danh sách trong bộ nhớ |

Các kiểu `Page`, `Slice` và `Stream` là những lựa chọn khác nhau. `Page` trả thêm thông tin tổng số; `Slice` trả thông tin còn trang kế tiếp; `Stream` cung cấp cách duyệt kết quả và có thể giữ tài nguyên truy vấn mở trong lúc tiêu thụ.

## 2. Entity đơn và `Optional<T>`

Nếu truy vấn phải trả về tối đa một entity, bạn có thể khai báo trực tiếp kiểu entity:

```java
Article findBySlug(String slug);
```

Nếu không tìm thấy kết quả, phương thức kiểu entity có thể trả về `null`. Nếu truy vấn trả về nhiều hơn một kết quả, Spring Data ném `IncorrectResultSizeDataAccessException`. Vì vậy, chỉ dùng kiểu entity đơn khi điều kiện truy vấn và ràng buộc dữ liệu bảo đảm tính duy nhất.

Trong đa số trường hợp tìm kiếm có thể không tìm thấy dữ liệu, `Optional<T>` thể hiện ý định rõ hơn:

```java
Optional<Article> findBySlug(String slug);
```

Caller phải xử lý cả hai trạng thái:

```java
Article article = articleRepository.findBySlug(slug)
    .orElseThrow(() -> new ArticleNotFoundException(slug));
```

`Optional` biểu diễn không có hoặc có một kết quả. Nếu truy vấn trả về nhiều kết quả, nó cũng không tự chọn một kết quả bất kỳ; Spring Data báo lỗi kích thước kết quả. Nếu nghiệp vụ thật sự muốn lấy một bản ghi đầu tiên theo thứ tự xác định, hãy dùng từ khóa giới hạn như `findFirstBy...OrderBy...` và khai báo thứ tự rõ ràng.

Không nên dùng `Optional<List<Article>>` cho truy vấn thông thường. Collection không có kết quả đã được biểu diễn tự nhiên bằng một danh sách rỗng; `Optional` thường dành cho một kết quả đơn có thể vắng mặt.

## 3. `List<T>` khi cần toàn bộ kết quả

`List<T>` phù hợp khi tập kết quả có quy mô nhỏ hoặc ứng dụng thực sự cần xử lý tất cả kết quả:

```java
List<Article> findByStatus(String status);
```

Nếu không có kết quả, repository trả về danh sách rỗng thay vì `null`. Với truy vấn không có giới hạn, SDN phải lấy toàn bộ kết quả để tạo collection. Nếu truy vấn khớp hàng trăm nghìn node, việc giữ tất cả entity trong bộ nhớ có thể làm tăng thời gian xử lý và mức sử dụng heap.

`List<T>` cũng có thể kết hợp với `Pageable`:

```java
List<Article> findByCategory(String category, Pageable pageable);
```

Trong trường hợp này, SDN chỉ lấy đoạn kết quả được xác định bởi `Pageable`. Caller nhận một danh sách đơn giản, không nhận metadata tổng số phần tử hoặc trang. Cách này phù hợp khi giao diện chỉ cần danh sách cho một trang hiện tại nhưng không cần hiển thị tổng số trang.

Nếu chỉ cần sắp xếp mà không phân trang, dùng `Sort`:

```java
List<Article> findByStatus(String status, Sort sort);
```

Không truyền đồng thời `Pageable` và `Sort` cho cùng một query method vì `Pageable` đã chứa thông tin sắp xếp.

## 4. Phân trang bằng `Page<T>`

`Page<T>` đại diện cho một trang dữ liệu và cung cấp thêm tổng số phần tử, tổng số trang, số trang hiện tại cùng các cờ điều hướng. Một phương thức trả về `Page` cần nhận `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Article> findByStatus(String status, Pageable pageable);
```

Tạo một yêu cầu trang ở tầng service:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.asc("id")
    )
);

Page<Article> page = articleRepository.findByStatus("PUBLISHED", pageable);
```

Chỉ số trang bắt đầu từ `0`. Ví dụ trên lấy 20 kết quả đầu tiên, sắp xếp theo thời điểm xuất bản giảm dần và dùng `id` làm tiêu chí phụ để thứ tự ổn định khi nhiều bài có cùng thời điểm.

`Page` cần biết tổng số kết quả. Vì vậy, SDN phải chạy thêm một count query ngoài truy vấn lấy nội dung trang. Với derived query, framework có thể suy diễn count query từ điều kiện tìm kiếm. Count query có thể tốn chi phí trên graph lớn, nhất là khi điều kiện đi qua nhiều relationship.

### Count query với Cypher tùy chỉnh

Khi dùng `@Query`, bạn cần thiết kế cả truy vấn lấy dữ liệu và truy vấn đếm. Ví dụ dưới đây minh họa cách viết theo cơ chế phân trang custom query của SDN 7.x: query chính có `$skip` và `$limit`, còn `countQuery` trả về tổng số kết quả phù hợp.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query(
    value = """
        MATCH (a:Article)
        WHERE a.status = $status
        RETURN a
        ORDER BY a.publishedAt DESC, a.id ASC
        SKIP $skip LIMIT $limit
        """,
    countQuery = """
        MATCH (a:Article)
        WHERE a.status = $status
        RETURN count(a)
        """
)
Page<Article> findPageByStatus(
    @Param("status") String status,
    Pageable pageable
);
```

Trong custom query, `$skip` và `$limit` nhận offset và kích thước trang từ `Pageable`. Count query phải dùng cùng điều kiện lọc với query chính nhưng không cần `ORDER BY`, `SKIP` hoặc `LIMIT`. Ví dụ đặt thứ tự trực tiếp trong Cypher, vì vậy hãy truyền `Pageable` không có sort; nếu cần sort động, dùng cơ chế được phiên bản SDN hỗ trợ cho custom query. Hãy kiểm tra tài liệu đúng phiên bản SDN của dự án vì cách xử lý `Pageable` trong custom Cypher có thể có yêu cầu cụ thể về placeholder và sorting.

Nếu truy vấn nối nhiều relationship và có thể tạo nhiều record cho cùng một node gốc, hãy loại bỏ trùng lặp ở query chính bằng `RETURN DISTINCT a` và đếm bằng `count(DISTINCT a)`. Nếu không, số phần tử trong trang và tổng số phần tử có thể bị đếm sai.

## 5. Dùng `Slice<T>` khi không cần tổng số

`Slice<T>` cung cấp một đoạn dữ liệu cùng thông tin có còn đoạn tiếp theo hay không. Nó không cần tổng số phần tử của toàn bộ truy vấn, vì vậy thường tránh được count query:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Article> findByFeaturedTrue(Pageable pageable);
```

Caller có thể điều hướng:

```java
Slice<Article> slice = articleRepository.findByFeaturedTrue(
    PageRequest.of(0, 20)
);

if (slice.hasNext()) {
    Slice<Article> nextSlice = articleRepository.findByFeaturedTrue(
        slice.nextPageable()
    );
}
```

SDN thường lấy thêm một kết quả ngoài kích thước yêu cầu để xác định có dữ liệu tiếp theo hay không. Nếu yêu cầu 20 phần tử, hệ thống có thể đọc 21 phần tử rồi trả 20 phần tử đầu và đặt `hasNext` tương ứng.

`Slice` phù hợp với nút “Tải thêm”, danh sách cuộn vô hạn hoặc tác vụ duyệt từng lô. Nếu giao diện cần “Trang 3 trên 12” hoặc tổng số bản ghi, `Slice` không cung cấp thông tin đó; hãy dùng `Page` hoặc một count query riêng khi thực sự cần.

### Custom Cypher trả về `Slice`

Với derived query, SDN xử lý `Pageable` cho bạn. Với custom `@Query`, query phải có thứ tự ổn định và các placeholder phân trang mà phiên bản SDN yêu cầu:

```java
@Query("""
    MATCH (a:Article)
    WHERE a.featured = true
    RETURN a
    ORDER BY a.publishedAt DESC, a.id ASC
    SKIP $skip LIMIT $limit
    """)
Slice<Article> findFeaturedSlice(Pageable pageable);
```

Custom query trả về `Slice` không cần count query. Khi query đã tự viết `ORDER BY`, hãy xác định rõ cách xử lý sorting từ `Pageable`; ví dụ trên dùng thứ tự cố định trong Cypher. Đừng cho rằng mọi phiên bản SDN đều tự chèn sorting động vào một query tùy chỉnh.

## 6. Duyệt kết quả bằng `Stream<T>`

`Stream<T>` cho phép xử lý kết quả tăng dần thay vì yêu cầu một `List` chứa toàn bộ dữ liệu:

```java
import java.util.stream.Stream;

Stream<Article> streamByStatus(String status);
```

Stream có thể giữ cursor hoặc tài nguyên truy vấn của driver mở trong khi ứng dụng tiêu thụ dữ liệu. Vì vậy, phải đóng stream sau khi dùng. Cách an toàn là dùng try-with-resources:

```java
try (Stream<Article> articles =
         articleRepository.streamByStatus("PUBLISHED")) {
    articles.forEach(article -> exportArticle(article));
}
```

Với tác vụ dài, hãy giữ stream trong phạm vi transaction và công việc đang tiêu thụ nó. Không trả stream ra khỏi service rồi để một tầng khác sử dụng sau khi transaction hoặc tài nguyên truy vấn đã đóng.

Ví dụ giữ việc tiêu thụ stream trong một phương thức service có transaction:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public void exportPublishedArticles() {
    try (Stream<Article> articles = articleRepository.streamByStatus("PUBLISHED")) {
        articles.forEach(this::exportArticle);
    }
}
```

`Stream` là API Java imperative, không đồng nghĩa với reactive `Flux`. Nếu ứng dụng dùng reactive repository, hãy dùng kiểu reactive mà SDN hỗ trợ và kiểm tra riêng khả năng phân trang của phiên bản đang sử dụng.

Lưu ý về hỗ trợ reactive: tài liệu SDN 7.0.x nêu rõ cơ chế paging không có trong reactive repository API ở phiên bản đó. Vì vậy, đừng mặc định có thể thay `Page` hoặc `Slice` bằng cùng kiểu trả về trong reactive repository; hãy kiểm tra tài liệu của release đang dùng và thiết kế luồng `Flux` hoặc giới hạn Cypher phù hợp.

## 7. Chọn kiểu trả về cho một repository

Ví dụ tổng hợp các kiểu trả về cho entity `Article`:

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ArticleRepository extends Neo4jRepository<Article, Long> {

    Optional<Article> findBySlug(String slug);

    List<Article> findByStatus(String status);

    Page<Article> findByStatus(String status, Pageable pageable);

    Slice<Article> findByFeaturedTrue(Pageable pageable);

    List<Article> findByCategory(String category, Pageable pageable);

    Stream<Article> streamByStatus(String status);
}
```

Các method có cùng tên `findByStatus` vẫn hợp lệ vì một method không có `Pageable`, method còn lại có `Pageable`; kiểu trả về không phải yếu tố phân biệt overload trong Java. Tên property trong derived query phải khớp với entity domain.

## 8. Sắp xếp ổn định và giới hạn của offset pagination

Phân trang theo `Pageable` thường sử dụng offset và limit. Với offset lớn, Neo4j vẫn phải duyệt hoặc bỏ qua nhiều kết quả trước khi trả về trang được yêu cầu. Trang càng sâu có thể càng tốn thời gian.

Một số nguyên tắc giúp phân trang đáng tin cậy:

- Luôn đặt thứ tự rõ ràng khi phân trang. Nếu nhiều node có cùng giá trị sắp xếp, thêm một property duy nhất làm tiêu chí phụ.
- Dùng index phù hợp với các property lọc và sắp xếp thường xuyên; xác nhận bằng `EXPLAIN` hoặc `PROFILE`.
- Giới hạn page size ở tầng API để client không yêu cầu một trang quá lớn.
- Tránh `Page` nếu giao diện không dùng tổng số phần tử; `Slice` hoặc `List` có `Pageable` có thể tiết kiệm count query.
- Với tập dữ liệu rất lớn và duyệt sâu, cân nhắc keyset/scrolling hoặc truy vấn theo mốc định danh thay vì offset lớn, nếu phiên bản và API của dự án hỗ trợ.

Thứ tự ổn định đặc biệt quan trọng khi dữ liệu được thêm hoặc cập nhật trong lúc người dùng chuyển trang. Nếu chỉ sắp xếp theo `publishedAt` và nhiều bài có cùng thời điểm, một bản ghi có thể xuất hiện ở hai trang hoặc bị bỏ qua khi thứ tự giữa các lần truy vấn thay đổi.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả entity đơn cho truy vấn có thể có nhiều kết quả | Phát sinh `IncorrectResultSizeDataAccessException` | Dùng `List`, `Page`, `Slice` hoặc giới hạn bằng `First`/`Top` |
| Dùng entity đơn nhưng không xử lý trường hợp không có | Nhận `null` và có thể phát sinh lỗi ở caller | Dùng `Optional<T>` khi kết quả có thể vắng mặt |
| Dùng `List` cho graph rất lớn | Tốn bộ nhớ và thời gian materialize | Dùng `Page`, `Slice` hoặc `Stream` theo nhu cầu |
| Dùng `Page` dù không cần tổng số | Phát sinh count query không cần thiết | Dùng `Slice` hoặc `List` kết hợp `Pageable` |
| Custom `Page` không có count query đúng | Tổng số phần tử hoặc trang sai | Viết `countQuery` cùng điều kiện lọc với query chính |
| Custom query không có `$skip`/`$limit` theo hợp đồng SDN | `Pageable` không giới hạn kết quả như mong muốn | Kiểm tra hướng dẫn custom query của phiên bản SDN và khai báo placeholder cần thiết |
| Dùng `Stream` nhưng không đóng | Rò rỉ tài nguyên truy vấn hoặc kết nối | Dùng try-with-resources |
| Phân trang mà không có thứ tự duy nhất | Kết quả giữa các trang có thể trùng hoặc thiếu | Thêm tiêu chí sắp xếp phụ duy nhất |
| Dùng offset quá lớn | Truy vấn chậm khi chuyển tới trang sâu | Cân nhắc keyset/scrolling hoặc phân trang theo mốc |

## 10. Quy trình chọn kiểu trả về

1. Nếu truy vấn bảo đảm tối đa một kết quả và dữ liệu luôn tồn tại, có thể trả về entity đơn.
2. Nếu kết quả đơn có thể không tồn tại, ưu tiên `Optional<T>`.
3. Nếu cần toàn bộ một tập kết quả nhỏ, dùng `List<T>`.
4. Nếu cần một đoạn kết quả mà không cần tổng số, dùng `Slice<T>` hoặc `List<T>` với `Pageable`.
5. Nếu cần tổng số phần tử và tổng số trang, dùng `Page<T>` và xác nhận count query phù hợp.
6. Nếu cần xử lý nhiều kết quả tuần tự, dùng `Stream<T>` và đóng stream đúng cách.
7. Với custom Cypher, xác minh yêu cầu `skip`, `limit`, `countQuery` và sorting theo phiên bản SDN của dự án.

## 11. Tự kiểm tra

1. Nếu truy vấn có thể không tìm thấy entity, vì sao `Optional<T>` rõ nghĩa hơn kiểu entity đơn?
2. Điều gì xảy ra nếu phương thức trả về `Optional<Article>` nhưng Cypher tạo ra nhiều kết quả?
3. Khác biệt quan trọng nhất giữa `Page<T>` và `Slice<T>` là gì?
4. Vì sao `Page<T>` thường cần một count query bổ sung?
5. Khi nào `List<T>` kết hợp với `Pageable` là đủ?
6. Vì sao phải đóng `Stream<T>` bằng try-with-resources?
7. Vì sao cần một tiêu chí sắp xếp phụ duy nhất khi phân trang?

Chọn kiểu trả về dựa trên cách caller sử dụng kết quả: một entity, một kết quả có thể vắng mặt, toàn bộ danh sách, một trang có tổng số, một lát có chỉ báo tiếp theo hay một luồng được tiêu thụ tuần tự. Với SDN, hãy đặc biệt chú ý count query của `Page`, placeholder phân trang trong custom Cypher và vòng đời tài nguyên của `Stream`.
