# totalElements, totalPages, hasNext và thông tin điều hướng

## Mục tiêu bài học

Một trang kết quả không chỉ có danh sách phần tử. Màn hình còn cần biết tổng số kết quả, tổng số trang, vị trí hiện tại và khả năng chuyển tới trang trước hoặc sau. Trong Spring Data Commons, `Page<T>` cung cấp những thông tin này thông qua một hợp đồng chung.

Sau bài học, bạn có thể:

- Phân biệt tổng số phần tử với số phần tử trong trang hiện tại.
- Đọc đúng `totalPages` khi chỉ số trang bắt đầu từ 0.
- Sử dụng `hasNext`, `hasPrevious`, `isFirst` và `isLast` theo ý nghĩa thực tế.
- Tạo yêu cầu điều hướng mà không vô tình bỏ phân trang ở trang cuối.
- Nhận diện giới hạn của phép đếm và tính nhất quán khi dữ liệu thay đổi.
- Xây dựng metadata phản hồi cho API theo một quy ước rõ ràng.

Các ví dụ dùng repository đồng bộ với store hỗ trợ phân trang. Commons định nghĩa abstraction, còn module lưu trữ quyết định cách lấy dữ liệu, tính tổng và áp dụng giới hạn trên backend.

## 1. Phân biệt yêu cầu và metadata kết quả

```text
Pageable: tôi muốn trang nào, kích thước bao nhiêu, thứ tự gì?
                    ↓
Repository và store thực hiện truy vấn
                    ↓
Page<T>: đây là dữ liệu và metadata của lần đọc này
```

`Pageable` không biết tổng số dữ liệu. Gọi `pageable.next()` chỉ tạo một yêu cầu có chỉ số trang tiếp theo; nó không xác nhận rằng trang đó tồn tại.

`Page<T>` kết hợp nội dung với thông tin tổng và điều hướng. Các getter metadata trên đối tượng Page đã nhận không phải là lệnh yêu cầu chạy một truy vấn mới mỗi lần gọi.

Ví dụ repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

interface ProductRepository extends Repository<Product, Long> {

    Page<Product> findByTenantIdAndActiveTrue(
            String tenantId, Pageable pageable);
}
```

Giả sử `Product` có các thuộc tính `id`, `tenantId`, `name`, `active`, `createdAt`, đã được mapping theo store. Truy vấn lấy sản phẩm hoạt động trong một tenant.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest request = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        )
);

Page<Product> page = repository.findByTenantIdAndActiveTrue(
        tenantId, request);
```

Trang đầu có chỉ số `0`. Các thông tin tổng của `page` cần được hiểu trong đúng phạm vi tenant và điều kiện active của truy vấn này.

## 2. Những đại lượng thường bị nhầm

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getNumber()` | `int` | Chỉ số trang hiện tại, bắt đầu từ 0 |
| `getSize()` | `int` | Kích thước trang theo hợp đồng yêu cầu |
| `getNumberOfElements()` | `int` | Số phần tử thực tế trong nội dung trang |
| `getTotalElements()` | `long` | Tổng số phần tử khớp điều kiện theo metadata Page |
| `getTotalPages()` | `int` | Tổng số trang được suy ra theo kích thước trang và tổng số |
| `hasContent()` | `boolean` | Trang hiện tại có phần tử hay không |

Với một Page đã phân trang thông thường, `getSize()` không giảm chỉ vì trang cuối thiếu phần tử. `getNumberOfElements()` mới mô tả số phần tử thực tế của trang đó.

Ví dụ tổng số là 53, kích thước trang là 20:

| Chỉ số trang | Nội dung thực tế | size | totalElements | totalPages |
| --- | --- | --- | --- | --- |
| 0 | 20 phần tử | 20 | 53 | 3 |
| 1 | 20 phần tử | 20 | 53 | 3 |
| 2 | 13 phần tử | 20 | 53 | 3 |

`totalElements` không phải số phần tử của trang hiện tại. Nó cũng không phải tổng mọi sản phẩm trong toàn hệ thống nếu truy vấn chỉ xét một tenant và một trạng thái.

Nếu chỉ cần số phần tử đang hiển thị, dùng `getNumberOfElements()` hoặc kích thước nội dung. Không cần lấy tổng toàn bộ để trả lời câu hỏi đó.

## 3. Hiểu totalPages và chỉ số trang cuối

Với yêu cầu đã phân trang, kích thước `S > 0` và tổng số `N >= 0`, ý nghĩa thông thường là:

```text
 totalPages = làm tròn lên của N / S
```

Ví dụ:

| N | S | totalPages | Các chỉ số có dữ liệu |
| --- | --- | --- | --- |
| 0 | 20 | 0 | Không có trang chứa dữ liệu |
| 1 | 20 | 1 | 0 |
| 20 | 20 | 1 | 0 |
| 21 | 20 | 2 | 0, 1 |
| 40 | 20 | 2 | 0, 1 |
| 53 | 20 | 3 | 0, 1, 2 |

Khi `totalPages > 0`, chỉ số trang cuối có dữ liệu là:

```text
 lastPageIndex = totalPages - 1
```

Không dùng `PageRequest.of(page.getTotalPages(), size)` để yêu cầu trang cuối. Với 3 trang, câu lệnh đó tạo yêu cầu chỉ số 3, tức trang thứ tư theo cách đếm của người dùng.

Khi tổng số trang bằng 0, không tính ra chỉ số `-1` rồi tạo PageRequest. Một yêu cầu trang 0 trả nội dung rỗng là trạng thái cần được xử lý riêng ở giao diện.

Các công thức trên mô tả trường hợp đã phân trang với kích thước dương. Không áp dụng chúng máy móc cho biểu diễn unpaged hoặc tự chia cho một kích thước bằng 0 của một cấu trúc kết quả khác.

## 4. hasNext không được suy ra chỉ từ trang đầy

`hasNext()` trả lời: theo thông tin điều hướng của kết quả này, còn trang tiếp theo không?

Với Page phân trang thông thường có chỉ số `p` và tổng số trang `P`, ý nghĩa tương ứng là:

```text
 hasNext = p + 1 < P
```

So sánh hai lần đọc với kích thước trang 20:

| Tổng số phần tử | Trang hiện tại | Số phần tử trong trang | hasNext |
| --- | --- | --- | --- |
| 40 | 1 | 20 | false |
| 41 | 1 | 20 | true |
| 53 | 1 | 20 | true |
| 53 | 2 | 13 | false |

Trang có đúng 20 phần tử vẫn có thể là trang cuối nếu tổng số kết thúc đúng ở ranh giới đó. Vì vậy:

```java
boolean hasNext = page.getContent().size() == page.getSize();
```

không phải cách thay thế đúng cho `page.hasNext()`.

Một danh sách đầy chỉ cho biết query đã trả đủ số lượng yêu cầu. Nó chưa cho biết còn dữ liệu ở phía sau hay không.

### So sánh với Slice

`Slice<T>` cũng cung cấp `hasNext`, nhưng không yêu cầu tổng số phần tử/trang như Page. Module có thể lấy thêm một phần tử hoặc dùng cơ chế tương ứng để xác định còn dữ liệu tiếp theo.

Nếu giao diện chỉ cần nút “Tiếp”, Slice có thể đáp ứng mà không yêu cầu phép đếm tổng. Không được lấy một Slice rồi tự gán `totalElements` bằng số phần tử của slice để mô phỏng metadata Page.

## 5. hasPrevious, isFirst và isLast

| API | Cách hiểu |
| --- | --- |
| `hasPrevious()` | Có vị trí trang trước theo chỉ số hiện tại |
| `isFirst()` | Đang ở vị trí đầu theo hợp đồng điều hướng |
| `hasNext()` | Có trang tiếp theo theo metadata kết quả |
| `isLast()` | Không còn trang tiếp theo theo hợp đồng điều hướng |

Với tổng số 53 và size 20:

| pageIndex | hasPrevious | isFirst | hasNext | isLast |
| --- | --- | --- | --- | --- |
| 0 | false | true | true | false |
| 1 | true | false | true | false |
| 2 | true | false | false | true |

### 5.1. isLast không phải phép kiểm tra chỉ số luôn hợp lệ

Một yêu cầu vượt cuối có thể trả Page rỗng. Ví dụ chỉ số 3 với tổng số trang 3 đã nằm sau trang cuối có dữ liệu.

Trong cách điều hướng của PageImpl thông thường, kết quả đó có thể có:

```text
number = 3
numberOfElements = 0
totalElements = 53
totalPages = 3
hasNext = false
isLast = true
```

`isLast = true` ở đây thể hiện không có trang tiếp theo theo metadata, không xác nhận rằng chỉ số 3 chính là trang cuối hợp lệ có dữ liệu.

Nếu ứng dụng cần xác định chỉ số nằm trong phạm vi đã biết, phải kiểm tra riêng trường hợp tổng số trang dương và chỉ số nhỏ hơn tổng số trang. Khi dữ liệu thay đổi đồng thời, phạm vi ấy cũng chỉ phản ánh lần đọc tương ứng.

### 5.2. hasPrevious không thực hiện truy vấn thăm dò

Một Page rỗng ở chỉ số lớn hơn 0 vẫn có thể báo `hasPrevious = true`. Điều này mô tả vị trí trước đó, không bảo đảm rằng trang trước hiện còn nội dung sau các lần thêm hoặc xóa dữ liệu.

Nếu yêu cầu vượt rất xa cuối, lùi một trang có thể vẫn vượt cuối. Ứng dụng cần định nghĩa chính sách điều hướng, không coi `hasPrevious` là lệnh tự tìm trang gần nhất có dữ liệu.

## 6. Điều hướng an toàn bằng metadata của kết quả

```java
if (page.hasNext()) {
    Pageable nextRequest = page.nextPageable();

    Page<Product> nextPage =
            repository.findByTenantIdAndActiveTrue(
                    tenantId, nextRequest);

    // Sử dụng nextPage theo luồng của ứng dụng.
}
```

Tương tự:

```java
if (page.hasPrevious()) {
    Pageable previousRequest = page.previousPageable();

    Page<Product> previousPage =
            repository.findByTenantIdAndActiveTrue(
                    tenantId, previousRequest);

    // Sử dụng previousPage theo luồng của ứng dụng.
}
```

Các phương thức tạo Pageable điều hướng giữ thông tin cần thiết theo hợp đồng của kết quả. Điều kiện tenant và các bộ lọc vẫn cần được truyền nhất quán vào lời gọi repository tiếp theo.

### Cẩn thận với biểu diễn unpaged ở biên

Khi không có trang tiếp theo hoặc trước đó, `nextPageable()` hay `previousPageable()` có thể trả `Pageable.unpaged()` theo hợp đồng API.

Vì vậy, không nên làm như sau mà không kiểm tra:

```java
// Chưa kiểm tra có trang tiếp theo.
Page<Product> next = repository.findByTenantIdAndActiveTrue(
        tenantId, page.nextPageable());
```

Ở trang cuối, biểu diễn unpaged có thể khiến lời gọi sau không còn giới hạn trang theo cách bạn dự định, nếu store chấp nhận nó. Hãy dùng `hasNext()` hoặc `hasPrevious()` trước khi thực hiện điều hướng.

### Tạo vị trí tiếp khác với xác nhận có dữ liệu

```java
Pageable blindlyNext = request.next();
```

Lệnh này chỉ tăng vị trí yêu cầu. Nó không dùng metadata của Page và không xác nhận còn dữ liệu. Lựa chọn API cần khớp với mục đích: tạo một vị trí mới hay chỉ cho phép đi tiếp khi kết quả báo còn trang sau.

## 7. Trang rỗng không luôn nghĩa là toàn bộ truy vấn không có dữ liệu

Hai kết quả có thể đều có `hasContent() = false`:

| Trường hợp | Nội dung trang | Tổng số theo metadata |
| --- | --- | --- |
| Bộ lọc không khớp sản phẩm nào | Rỗng | 0 |
| Chỉ số trang vượt phần dữ liệu hiện có | Rỗng | Có thể lớn hơn 0 |

Giao diện nên phân biệt thông điệp:

```text
Không có sản phẩm phù hợp với bộ lọc
```

và:

```text
Trang được yêu cầu hiện không có dữ liệu
```

Khi người dùng đổi bộ lọc, việc đưa chỉ số về trang đầu thường giúp tránh ở lại một trang quá xa trong tập kết quả mới. Đó là chính sách giao diện cần được thực hiện có chủ đích.

Các chính sách với trang vượt cuối có thể là trả trang rỗng, báo lỗi phạm vi hoặc điều hướng lại một vị trí phù hợp. Hợp đồng API cần nhất quán; repository không có nghĩa vụ tự thay yêu cầu thành trang cuối.

Với tập hoàn toàn rỗng ở vị trí đầu, `isFirst` và `isLast` có thể cùng đúng. Không cần tạo một phần tử giả chỉ để hai trạng thái này khác nhau.

## 8. Tổng số phải được tính trên đúng tập kết quả

`totalElements` có ý nghĩa khi phép đếm cùng mô tả phạm vi với nội dung trang.

Nếu dữ liệu trang lọc theo tenant và active, nhưng phép đếm chỉ lọc active, giao diện có thể hiển thị tổng số sai và làm lộ quy mô dữ liệu ngoài phạm vi tenant.

Với derived query, module thường xây dựng phần đọc và đếm từ cùng điều kiện. Với truy vấn khai báo, người viết có thể cần cung cấp count query phù hợp.

### Ví dụ riêng cho Spring Data JPA

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

interface JpaProductRepository extends Repository<Product, Long> {

    @Query(
        value = """
            select p from Product p
            where p.tenantId = :tenantId
              and p.active = true
            """,
        countQuery = """
            select count(p) from Product p
            where p.tenantId = :tenantId
              and p.active = true
            """
    )
    Page<Product> findActiveProducts(
            @Param("tenantId") String tenantId,
            Pageable pageable);
}
```

Đây là JPQL và annotation của JPA, giả định entity có tên Product cùng mapping tương ứng. Không đưa nguyên cú pháp này sang MongoDB hoặc coi `countQuery` là tính năng giống nhau trên mọi store.

Các điều kiện và binding phải thống nhất giữa hai truy vấn. Không cần khai báo count query thủ công cho mọi truy vấn đơn giản; ví dụ làm rõ trách nhiệm khi bạn chủ động cung cấp nó.

### Join, distinct và tổng số logic

Một phép join có thể tạo nhiều dòng vật lý cho cùng một entity. Nếu nội dung trả các entity duy nhất nhưng count query đếm mọi dòng join, tổng số có thể bị phóng đại.

Cần đếm đúng đơn vị kết quả: entity, projection, nhóm tổng hợp hoặc đơn vị nghiệp vụ mà trang đang biểu diễn. `count(distinct ...)` có thể là một phần giải pháp trong trường hợp phù hợp, nhưng không phải cách sửa chung cho mọi query.

## 9. Chi phí phép đếm và giới hạn nhất quán

Một Page thường cần lấy nội dung và xác định tổng số. Module có thể chạy một truy vấn đếm bổ sung hoặc tối ưu khi đã suy ra được tổng trong tình huống phù hợp.

Do đó, không nên giả định:

- Gọi `getTotalElements()` lần nào cũng chạy count lần đó.
- Mọi lần lấy Page luôn chạy đúng hai câu truy vấn.
- Count query và data query luôn nhìn cùng một snapshot.

Những kết luận này phụ thuộc cách thực thi và cấu hình cụ thể.

### 9.1. Tổng là thông tin của lần đọc, không phải cam kết cho mọi request

Giả sử lần đọc đầu báo 53 phần tử. Trước khi người dùng bấm trang cuối, các sản phẩm có thể được thêm hoặc xóa. Lần đọc tiếp theo có thể báo một tổng khác hoặc trả trang rỗng.

Transaction và mức cô lập ảnh hưởng sự nhất quán giữa các thao tác đọc. Chỉ thêm một transaction thông thường hoặc đặt `readOnly = true` không đủ để kết luận mọi backend sẽ cung cấp cùng snapshot cho tất cả tình huống.

Cũng không có một Page ban đầu nào tự giữ snapshot qua nhiều HTTP request.

### 9.2. Khi không cần tổng, đừng tự tạo một con số thay thế

Nếu yêu cầu chỉ cần cuộn tiếp, có thể chọn Slice hoặc cơ chế scroll/cursor phù hợp với store. Nếu tổng chỉ là ước tính do ứng dụng chủ động cung cấp, API cần nói rõ đó là ước tính thay vì gán cho nó ý nghĩa của một phép đếm chính xác.

Độ tốn kém của phép đếm cần được quan sát trên bộ lọc, index và dữ liệu thực tế. Một data query trả ít phần tử không có nghĩa count query tương ứng cũng rẻ.

## 10. Tạo PageImpl thủ công không tự tính tổng database

Với adapter hoặc kết quả đã có sẵn, có thể cần dùng `PageImpl`. Constructor nhận nội dung, Pageable và một tổng do bạn cung cấp; nó không tự gọi repository để đếm toàn bộ dữ liệu.

Ví dụ dễ sai về hợp đồng:

```java
// Không dùng items.size() như tổng toàn bộ khi items chỉ là một trang.
Page<Product> page = new PageImpl<>(items, pageable, items.size());
```

Nếu `items` chỉ có 20 phần tử của tổng 53, kích thước đó không phải tổng toàn bộ.

PageImpl có thể điều chỉnh tổng được cung cấp trong một số trường hợp dựa trên offset và nội dung, nhằm giảm một số bất nhất ở phần cuối. Cơ chế điều chỉnh đó không biến một giá trị tổng thiếu căn cứ thành một phép đếm đúng toàn bộ database.

Vì vậy, khi xây dựng adapter:

1. Xác định nội dung đã được cắt trang hay chưa.
2. Xác định nguồn tổng số phù hợp với đúng điều kiện.
3. Truyền metadata có cùng ngữ nghĩa với nội dung.
4. Không phân trang lần thứ hai trên nội dung vốn đã là một trang.

Các ví dụ Page trong bài giả định yêu cầu đã phân trang với kích thước dương. Với unpaged, không áp dụng máy móc công thức chỉ số/trang cuối; cần quyết định hợp đồng biểu diễn riêng nếu API cho phép trạng thái đó.

## 11. Chuyển sang DTO và giữ metadata

Nếu chỉ đổi hình dạng mỗi phần tử, có thể dùng `Page.map(...)`:

```java
Page<ProductView> views = page.map(ProductView::from);
```

Ví dụ view dùng Java record trong dự án có mức ngôn ngữ phù hợp:

```java
record ProductView(Long id, String name) {

    static ProductView from(Product product) {
        return new ProductView(product.getId(), product.getName());
    }
}
```

Phép map chuyển nội dung sang ProductView và giữ metadata phân trang của Page theo hợp đồng. Nó không tự chạy lại truy vấn đếm.

Nếu chỉ làm:

```java
List<ProductView> items = page.getContent().stream()
        .map(ProductView::from)
        .collect(Collectors.toList());
```

thì `items` chỉ còn danh sách. Muốn trả tổng và thông tin điều hướng, bạn vẫn phải giữ Page hoặc ánh xạ metadata riêng. Ví dụ này cần import `List` và `Collectors`.

### Ví dụ envelope cho API bắt đầu từ 0

```java
import java.util.List;

import org.springframework.data.domain.Page;

record PageEnvelope<T>(
        List<T> items,
        int pageIndex,
        int pageSize,
        int numberOfElements,
        long totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious,
        Integer nextPageIndex,
        Integer previousPageIndex) {

    static <T> PageEnvelope<T> from(Page<T> page) {
        if (page.getPageable().isUnpaged()) {
            throw new IllegalArgumentException(
                    "Envelope này yêu cầu kết quả đã phân trang");
        }

        return new PageEnvelope<>(
                page.getContent(),
                page.getNumber(),
                page.getSize(),
                page.getNumberOfElements(),
                page.getTotalElements(),
                page.getTotalPages(),
                page.hasNext(),
                page.hasPrevious(),
                page.hasNext() ? page.getNumber() + 1 : null,
                page.hasPrevious() ? page.getNumber() - 1 : null
        );
    }
}
```

Trong schema minh họa, hai field chỉ số điều hướng được phép null khi không có hướng tương ứng. Chúng là lựa chọn biểu diễn của API, không phải yêu cầu chung của Spring Data.

Các chỉ số trong envelope bắt đầu từ 0. Nếu API bên ngoài dùng số trang bắt đầu từ 1, chuyển đổi nhất quán tại ranh giới và đặt tên field rõ ràng; `totalPages` là số lượng nên không cộng thêm 1.

Envelope này không tự giải quyết chính sách trang vượt cuối. Chẳng hạn `previousPageIndex` vẫn chỉ là chỉ số liền trước, không phải trang cuối hợp lệ được tìm lại.

## 12. Hiển thị khoảng phần tử mà không tạo thông tin sai

Với một Page đã phân trang và có nội dung:

```text
 vị trí đầu hiển thị = offset + 1
 vị trí cuối hiển thị = offset + numberOfElements
```

Ví dụ trang chỉ số 2, size 20, có 13 phần tử:

```text
Đang hiển thị 41–53 trong 53 sản phẩm
```

Có thể lấy offset từ `page.getPageable().getOffset()` trong nhánh đã phân trang. Dùng kiểu long cho phép tính vị trí phù hợp.

Chỉ hiển thị khoảng này khi `page.hasContent()` đúng. Với trang rỗng vượt cuối, không tạo một khoảng như “61–60” hoặc tuyên bố tổng toàn bộ bằng 0 chỉ vì không có nội dung ở vị trí yêu cầu.

Tương tự, chỉ hiển thị nhãn “Trang 3/3” khi đã chuyển chỉ số nội bộ sang số hiển thị đúng và đang xử lý một vị trí phù hợp. Một trang yêu cầu vượt cuối cần trạng thái riêng thay vì nhãn “Trang 4/3” gây khó hiểu.

Các ca dữ liệu có ích để xác minh metadata:

| Ca | Điều cần quan sát |
| --- | --- |
| Tổng bằng 0 | Nội dung rỗng, trạng thái giao diện không tính trang cuối âm |
| Tổng nhỏ hơn size | Một trang có nội dung nhưng thiếu phần tử |
| Tổng đúng bằng size | Trang đầy và không còn trang sau |
| Tổng bằng bội số của size | Trang cuối vẫn đầy nhưng hasNext false |
| Tổng vượt bội số một phần tử | Có thêm trang cuối chỉ một phần tử |
| Yêu cầu vượt cuối | Phân biệt trang rỗng với toàn bộ tập rỗng |
| Dữ liệu thay đổi giữa các lần đọc | Tổng và nội dung có thể thay đổi theo mức nhất quán |
| Count query thiếu bộ lọc | Metadata sai dù nội dung trang trông hợp lệ |

## 13. Bài tập tự kiểm tra

### Bài 1: Trang đầy

Có 40 kết quả, size 20 và đang ở pageIndex 1. Trang hiện tại có 20 phần tử. `hasNext()` nên là gì?

**Gợi ý đáp án:** False. Đây là trang cuối dù trang đầy. Số phần tử trong trang không tự chứng minh còn trang sau.

### Bài 2: Trang cuối và chỉ số

Page báo `totalPages = 5`. Khi có dữ liệu, chỉ số trang cuối theo quy ước nội bộ là bao nhiêu?

**Gợi ý đáp án:** 4. Tổng số trang là số lượng, không phải chỉ số bắt đầu từ 0.

### Bài 3: Nội dung rỗng nhưng tổng dương

Một Page có nội dung rỗng và totalElements bằng 53. Có thể kết luận bộ lọc không khớp sản phẩm nào không?

**Gợi ý đáp án:** Không. Có thể yêu cầu đang vượt cuối hoặc có bất nhất do dữ liệu thay đổi. Cần xem chỉ số, tổng số trang và điều kiện thực thi.

### Bài 4: Điều hướng ở biên

Có nên luôn gọi repository với `page.nextPageable()` mà không xét `hasNext()` không?

**Gợi ý đáp án:** Không. Khi không có trang tiếp theo, API có thể trả biểu diễn unpaged. Kiểm tra metadata trước khi thực hiện lời gọi điều hướng.

### Bài 5: Tổng tự tạo

Adapter chỉ có 20 phần tử của một trang và truyền `items.size()` làm total cho PageImpl. Có đủ để tạo metadata toàn bộ chính xác không?

**Gợi ý đáp án:** Không. Cần nguồn tổng số đúng với cùng điều kiện. PageImpl không tự đếm database và việc điều chỉnh một số trường hợp không thay thế phép đếm ấy.

### Bài 6: Không cần tổng

Một màn hình chỉ có nút “Tiếp” và không hiển thị tổng. Có bắt buộc dùng Page cùng count query không?

**Gợi ý đáp án:** Không. Có thể cân nhắc Slice hoặc cơ chế khác được store hỗ trợ. Không nên tạo tổng giả chỉ để giữ một hình dạng phản hồi không cần thiết.

## Những điểm cần nhớ

- totalElements là tổng theo điều kiện truy vấn; numberOfElements là số phần tử thực tế của trang.
- totalPages là số lượng trang; chỉ số trang cuối có dữ liệu là totalPages trừ 1 khi tổng số trang dương.
- Dùng hasNext và hasPrevious để điều hướng; trang đầy, isLast hoặc nội dung rỗng riêng lẻ chưa trả lời mọi câu hỏi về phạm vi.
- Nội dung và phép đếm phải cùng ngữ nghĩa; metadata không tự tạo snapshot xuyên các request.
- Giữ metadata khi ánh xạ DTO, và xác định rõ quy ước chỉ số, trang rỗng, trang vượt cuối trong hợp đồng API.
