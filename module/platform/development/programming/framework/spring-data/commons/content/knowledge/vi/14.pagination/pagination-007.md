# Page.empty, trang cuối, trang vượt phạm vi và dữ liệu thay đổi giữa các lần đọc

Một `Page` có nội dung rỗng chưa đủ để kết luận toàn bộ truy vấn không có kết quả. Có thể tập dữ liệu thật sự rỗng, caller yêu cầu một trang quá xa, hoặc dữ liệu đã bị xóa kể từ lần đọc trước. Nếu thay mọi kết quả rỗng bằng `Page.empty(...)`, ứng dụng có thể làm mất tổng số đã biết và khiến giao diện hiểu sai trạng thái hiện tại.

Bài học thuộc chương **Phân trang** của **SPRING_DATA_COMMONS**. Mục tiêu là đọc đúng nội dung cùng metadata của `Page`, dùng factory rỗng đúng ý nghĩa, phân biệt trang cuối với trang vượt phạm vi và thiết kế hành vi rõ ràng khi dữ liệu thay đổi giữa các lần đọc.

## 1. Phân biệt bốn trạng thái

| Trạng thái | Nội dung trang | Tổng số có thể có | Ý nghĩa |
| --- | --- | --- | --- |
| Tập kết quả không có entity phù hợp | Rỗng | `0` | Không có dữ liệu cho bộ lọc đang xét |
| Trang cuối có dữ liệu | Có thể đủ size hoặc ít hơn size | Dương | Đây là phần cuối của tập kết quả theo metadata |
| Trang vượt phạm vi dữ liệu | Rỗng | Có thể vẫn dương | Có dữ liệu, nhưng không nằm ở vị trí caller yêu cầu |
| Truy vấn không thực hiện thành công | Không có một kết quả thành công để diễn giải | Không được tự gán là `0` | Lỗi phải được xử lý theo hợp đồng ứng dụng |

Không nên biến bốn trạng thái này thành cùng một thông báo “chưa có dữ liệu”. Chúng có nguyên nhân và cách tiếp tục khác nhau.

Một chỉ số trang âm hoặc page size bằng không lại là vấn đề cấu trúc yêu cầu, khác với một chỉ số không âm vượt cuối tập dữ liệu. `PageRequest` không cần biết tổng số để từ chối đầu vào âm; ngược lại, nó không tự biết tổng để chuyển mọi yêu cầu quá xa về trang cuối.

## 2. Nội dung và metadata phải được đọc cùng nhau

Các thông tin quan trọng:

```java
page.getContent();
page.getNumberOfElements();
page.getSize();
page.getNumber();
page.getTotalElements();
page.getTotalPages();
page.hasContent();
page.isEmpty();
page.hasNext();
page.isLast();
```

| Thông tin | Câu hỏi được trả lời |
| --- | --- |
| `getNumberOfElements()` | Trang hiện tại có bao nhiêu phần tử thực tế? |
| `getSize()` | Kích thước trang theo yêu cầu là bao nhiêu? |
| `getNumber()` | Chỉ số trang hiện tại là gì? |
| `getTotalElements()` | Metadata cho biết toàn bộ truy vấn có bao nhiêu kết quả? |
| `getTotalPages()` | Metadata tương ứng có bao nhiêu trang? |
| `hasContent()` / `isEmpty()` | Nội dung phần hiện tại có rỗng không? |
| `hasNext()` / `isLast()` | Theo hợp đồng trang hiện tại, có phần tiếp theo không? |

`getNumberOfElements()` bằng `0` không bắt buộc `getTotalElements()` cũng bằng `0`.

Tương tự, `isLast()` không tự khẳng định “đây là trang cuối có dữ liệu hợp lệ”. Một trang rỗng ở vị trí vượt cuối cũng có thể không có trang tiếp theo và được báo là last theo metadata của `PageImpl`.

## 3. Page.empty tạo ra điều gì?

Commons cung cấp hai factory:

```java
Page<PurchaseOrder> noRequest = Page.empty();
Page<PurchaseOrder> withRequest = Page.empty(pageable);
```

Chúng tạo một kết quả rỗng, không chạy truy vấn và không tự đếm dữ liệu trong store.

### 3.1. Page.empty()

Dạng không tham số tạo trang rỗng gắn với một yêu cầu không phân trang. Nó không bảo toàn page index, page size hoặc sort của một yêu cầu phân trang mà caller đã gửi trước đó.

Nếu đang xây dựng phản hồi cho một request cụ thể, việc bỏ metadata request có thể làm ứng dụng khó phân biệt trang nào đã được yêu cầu.

### 3.2. Page.empty(pageable)

Dạng có `Pageable` bảo toàn thông tin request tương ứng, đồng thời tạo nội dung rỗng với tổng số bằng `0`.

Ví dụ:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable request = PageRequest.of(
        3,
        10,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));

Page<PurchaseOrder> empty = Page.empty(request);
```

Với `PageImpl` có phân trang trong ví dụ:

```text
Nội dung             = rỗng
Chỉ số trang         = 3
Kích thước yêu cầu   = 10
Tổng số phần tử      = 0
Tổng số trang        = 0
```

Factory này không có nghĩa “chỉ trang 3 không có dữ liệu, còn toàn bộ truy vấn có thể vẫn có 23 entity”. Nó đang biểu đạt một tổng bằng không.

Không dùng riêng một quy tắc về `getTotalPages()` để nhận diện mọi dạng kết quả rỗng, đặc biệt khi trộn cả unpaged và paged. Hãy đọc nội dung, tổng số và bối cảnh request; dạng không phân trang không có cùng ý nghĩa chỉ số/kích thước như một request đã phân trang.

### 3.3. Khi nào có thể dùng factory rỗng?

Một trường hợp hợp lý là ứng dụng đã biết chắc truy vấn logic không thể có kết quả. Ví dụ truy vấn bị giới hạn bởi một tập candidate id đầy đủ, và tập này không có phần tử:

```java
if (candidateIds.isEmpty()) {
    return Page.empty(pageable);
}
```

Điều này chỉ đúng nếu nghiệp vụ định nghĩa tập candidate rỗng là “không có ứng viên phù hợp”. Nếu một bộ lọc rỗng có ý nghĩa “không áp dụng lọc”, không được dùng cùng nhánh đó.

Không dùng `Page.empty()` như một cách biểu đạt lỗi kết nối, một query chưa được thực hiện hoặc một tổng số mà ứng dụng chưa biết.

## 4. Trang cuối có thể ngắn hoặc đầy

Giả sử truy vấn có `23` entity và size bằng `10`, dữ liệu ổn định:

| Page index | Offset | Số phần tử nội dung | Tổng số | Tổng trang | `isLast()` theo PageImpl |
| --- | --- | --- | --- | --- | --- |
| `0` | `0` | `10` | `23` | `3` | `false` |
| `1` | `10` | `10` | `23` | `3` | `false` |
| `2` | `20` | `3` | `23` | `3` | `true` |
| `3` | `30` | `0` | `23` | `3` | `true` |

Page index bắt đầu từ `0`. Trang cuối **có dữ liệu** trong ví dụ là index `2`, còn index `3` đã vượt phạm vi dữ liệu.

Nếu tổng bằng `20`, trang cuối index `1` có đủ `10` phần tử. Do đó:

```text
Nội dung ngắn hơn size có thể là dấu hiệu phần cuối trong một query đơn giản.
Nội dung đủ size không chứng minh vẫn còn phần tiếp theo.
```

Với `Page`, dùng metadata như `hasNext()` cho hợp đồng điều hướng thay vì tự đặt:

```java
boolean hasNext = page.getNumberOfElements() == page.getSize();
```

Biểu thức trên sai ở trường hợp tổng vừa chia hết cho size.

## 5. Trang vượt phạm vi không đồng nghĩa tổng bằng không

Giả sử request index `3`, size `10`, còn toàn bộ truy vấn có `23` entity. Một kết quả mô tả tình huống đó có thể được xây dựng như sau:

```java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;

Page<PurchaseOrder> outside = new PageImpl<>(
        List.<PurchaseOrder>of(),
        request,
        23L);
```

Đoạn này minh họa dữ liệu metadata đã biết, không thay thế việc truy vấn store để xác định tổng.

So sánh:

| Giá trị | `Page.empty(request)` | Trang rỗng với tổng `23` |
| --- | --- | --- |
| Nội dung | Rỗng | Rỗng |
| Page index | `3` | `3` |
| Size | `10` | `10` |
| Total elements | `0` | `23` |
| Total pages trong ví dụ paged | `0` | `3` |
| Có thể nói toàn bộ tập không có kết quả? | Factory đang công bố tổng bằng `0` | Không |

Vì vậy không nên thay kết quả repository bằng factory rỗng chỉ vì nội dung rỗng:

```java
Page<PurchaseOrder> result = repository.findByTenantIdAndStatus(
        tenantId, status, pageable);

// Làm mất tổng số và metadata kết quả đã có.
if (result.isEmpty()) {
    return Page.empty(pageable);
}

return result;
```

Nếu không có một lý do nghiệp vụ khác, hãy trả hoặc chuyển đổi chính `Page` đã nhận. Muốn map entity sang DTO, dùng `map(...)` của container để giữ metadata thay vì tự dựng một trang rỗng mới.

## 6. isLast, isFirst và hasPrevious không xác nhận trang có dữ liệu

Với trang index `3`, tổng trang `3` trong ví dụ vượt phạm vi:

- Nội dung rỗng.
- `isLast()` có thể là true vì không còn trang sau theo cách tính của `PageImpl`.
- `isFirst()` là false vì index không bằng `0`.
- `hasPrevious()` có thể là true vì vẫn có một chỉ số trước index hiện tại.

Các cờ điều hướng phản ánh quan hệ vị trí và metadata. Chúng không thay thế kiểm tra nội dung hay một chính sách hợp lệ hóa số trang của ứng dụng.

Đặc biệt, nếu caller yêu cầu index `100` trong một tập chỉ có ba trang, có previous không có nghĩa index `99` sẽ chứa dữ liệu.

### Đừng gọi nextPageable vô điều kiện

Khi không còn trang tiếp theo, `nextPageable()` có thể biểu đạt không có một yêu cầu phân trang tiếp theo bằng giá trị unpaged theo hợp đồng của implementation. Không dùng nó một cách mù quáng làm request kế tiếp rồi vô tình đổi sang truy vấn không phân trang.

Vòng duyệt cần xem cờ tiếp tục:

```java
if (page.hasNext()) {
    Pageable next = page.nextPageable();
    // Dùng next nếu ứng dụng cần lấy trang tiếp theo.
}
```

Cũng cần phân biệt `page.nextPageable()` với việc tự tạo `pageable.next()`. Một yêu cầu trang có thể tạo chỉ số tiếp theo mà không biết dữ liệu còn hay không.

## 7. Nhận diện trang ngoài phạm vi dựa trên metadata đã biết

Trong một kết quả paged có tổng dương và metadata nhất quán tại thời điểm quan sát, index hợp lệ có dữ liệu nằm trong:

```text
0 đến totalPages - 1
```

Có thể viết một helper phục vụ quyết định ứng dụng:

```java
static boolean beyondKnownRange(Page<?> page) {
    Pageable request = page.getPageable();

    return request.isPaged()
            && page.getTotalElements() > 0
            && page.getNumber() >= page.getTotalPages();
}
```

Tên “known range” nhấn mạnh đây là kết luận theo metadata hiện có, không phải một bảo đảm về snapshot vĩnh viễn.

### Khi tổng bằng không

Nếu tổng là `0`, không có một trang có dữ liệu để tính `totalPages - 1`. Nhiều ứng dụng chọn hiển thị trạng thái không có kết quả ở vị trí đầu thay vì tạo một chỉ số âm.

Nếu request ban đầu có index lớn hơn không, ứng dụng có thể reset hiển thị về đầu theo hợp đồng đã chọn. Nhưng không được dùng `PageRequest.of(-1, size)` từ một phép tính trang cuối không kiểm tra trường hợp tổng bằng không.

Cũng không dùng factory `Page.empty(request)` như một cách phát hiện tổng thật. Tổng bằng không mà factory công bố chỉ đáng tin khi ứng dụng có cơ sở logic để tạo kết quả đó.

## 8. Chọn chính sách ứng dụng cho request quá xa

Commons không quyết định giao diện phải phản ứng thế nào khi request vượt phạm vi dữ liệu. Có thể chọn một trong những hợp đồng rõ ràng:

| Chính sách | Hành vi | Điều cần giữ rõ |
| --- | --- | --- |
| Trả nội dung rỗng tại index đã yêu cầu | Giữ metadata tổng và request hiện tại | Caller hiểu đây không nhất thiết là toàn bộ tập rỗng |
| Điều hướng về một trang còn phù hợp | Tính lại hoặc đọc lại trang đã chọn | Phản hồi cho biết vị trí thực tế, tránh giả vờ đó vẫn là index cũ |
| Báo request ngoài phạm vi theo hợp đồng API | Không trả một trang dữ liệu bình thường | Phân biệt với đầu vào âm, lỗi store và không có kết quả |

Không có một lựa chọn đúng cho mọi sản phẩm. Một giao diện người dùng vừa xóa phần tử cuối có thể muốn quay về trang trước; một API cần giữ nguyên request có thể trả trang rỗng cùng tổng số.

### Tạo request cho trang cuối đã biết

Ví dụ helper, không thực hiện truy vấn:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

static Pageable lastKnownPageRequest(Page<?> page) {
    Pageable current = page.getPageable();
    if (current.isUnpaged()) {
        return current;
    }

    int lastIndex = Math.max(0, page.getTotalPages() - 1);
    return PageRequest.of(
            lastIndex,
            current.getPageSize(),
            current.getSort());
}
```

Cần giữ nguyên filter và sort khi đọc lại theo request mới. Không chỉ giữ size rồi làm mất khóa phụ sắp xếp hoặc tenant/trạng thái của truy vấn ban đầu.

Nếu dữ liệu tiếp tục thay đổi, request cho trang cuối vừa tính vẫn có thể trở nên quá xa trước lúc chạy. Một chính sách đọc lại nên có giới hạn rõ ràng, chẳng hạn tối đa một lần điều chỉnh trong một request, thay vì lặp không giới hạn cho tới khi tìm thấy dữ liệu.

## 9. Ví dụ repository và thứ tự xác định

Giả sử `PurchaseOrder` có `id`, `tenantId`, `status`, `createdAt`; trong đó id là định danh duy nhất và createdAt không null. Ví dụ chính dùng **Spring Data JPA** với entity và hạ tầng đã được cấu hình phù hợp:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);
}
```

`OrderStatus` là enum nghiệp vụ, ví dụ gồm `NEW`, `PAID`, `CANCELLED`. Caller truyền sort:

```java
Sort order = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

Pageable request = PageRequest.of(2, 10, order);
```

Khóa phụ id giúp các entity cùng thời điểm có thứ tự tương đối rõ ràng trên dữ liệu không đổi. Nó không tự giữ snapshot giữa các request hoặc giữa query nội dung và query đếm.

Các tên sort là thuộc tính Java theo mapping, không phải tên cột SQL được chép tùy ý. Khả năng áp dụng sort, paging và count vẫn cần được xem theo module và loại truy vấn đang dùng.

## 10. Xóa dữ liệu có thể làm trang cuối biến mất

Giả sử trước đó có `23` entity, size `10`, trang cuối là index `2` với ba entity.

Caller xóa ba entity đó rồi đọc lại index `2`. Nếu hiện tại chỉ còn `20` entity:

```text
Index yêu cầu      = 2
Offset             = 20
Nội dung           = rỗng
Tổng hiện tại      = 20
Tổng trang         = 2
Trang cuối có dữ liệu = index 1
```

Kết quả này không chứng minh filter không có dữ liệu; nó phản ánh một vị trí đã trở nên quá xa sau khi xóa.

Một giao diện có thể quay về index `1`, nhưng phải dựa trên trạng thái hiện tại, không chỉ giảm index theo một giả định rằng mỗi lần chỉ mất đúng một trang. Nếu nhiều thao tác đồng thời làm tập dữ liệu giảm mạnh, lùi một trang vẫn có thể chưa đủ.

Nếu toàn bộ dữ liệu phù hợp bị xóa, tổng trở thành `0`; lúc đó không tồn tại một “trang cuối có dữ liệu” để quay tới. Cần xử lý trạng thái rỗng toàn tập riêng.

## 11. Insert, delete và update có thể làm dịch chuyển nội dung

### 11.1. Insert trước offset làm lặp phần tử

Giả sử dữ liệu theo thứ tự đang dùng là:

```text
A, B, C, D, E, F
```

Page size bằng `2`, trang đầu trả `A, B`. Một entity `X` được thêm vào trước chúng:

```text
X, A, B, C, D, E, F
```

Trang index `1` bỏ qua hai vị trí rồi trả `B, C`. Caller thấy lại `B`.

### 11.2. Delete trước offset làm bỏ qua phần tử

Từ tập ban đầu, caller đọc `A, B`, sau đó `A` bị xóa:

```text
B, C, D, E, F
```

Trang index `1` theo offset `2` trả `D, E`. Entity `C` có thể bị bỏ qua trong lượt duyệt đó.

### 11.3. Update khóa sort hoặc filter làm entity di chuyển

Một entity thay đổi `createdAt`, điểm xếp hạng hoặc trạng thái có thể chuyển vị trí hoặc ra/vào tập kết quả. Tổng số không đổi cũng không chứng minh nội dung giữa các trang không đổi.

Do đó cần tách ba yêu cầu:

| Yêu cầu | Cơ chế liên quan |
| --- | --- |
| Phân định entity bằng nhau trên sort chính | Bộ khóa sort đầy đủ |
| Tiếp tục từ một mốc thay vì offset | Keyset/scrolling nếu module hỗ trợ |
| Duyệt cùng một phiên bản tập dữ liệu | Snapshot, transaction hoặc mốc chốt phù hợp với store |

Keyset có thể tránh một số dịch chuyển do offset, nhưng không tự tạo snapshot khi giá trị khóa hoặc filter thay đổi. `Page.empty` cũng không giải quyết bất kỳ bài toán nhất quán nào trong bảng này.

## 12. Nội dung và count có thể được đọc ở hai thời điểm

Để trả `Page`, module có thể thực hiện truy vấn nội dung và một phép đếm riêng. Trong một số trường hợp framework có thể suy ra tổng mà không chạy count, nên không nên mặc định lúc nào cũng có hai câu truy vấn.

Khi nội dung và count là hai lần đọc, dữ liệu có thể đổi giữa chúng. Ví dụ nội dung lấy được một số entity cuối, rồi các entity bị xóa trước khi count chạy; metadata có thể không phản ánh chính xác cùng một trạng thái với nội dung.

`PageImpl` có cơ chế điều chỉnh tổng trong một số trường hợp nội dung trang cuối không khớp tổng được cung cấp. Điều đó giúp giảm một số bất nhất hình thức, nhưng không:

- Chạy lại truy vấn để xác minh dữ liệu.
- Tạo một snapshot chung.
- Chứng minh query đếm có đúng predicate.
- Sửa một thiết kế pagination sai trên join hoặc grouping.

Không dùng constructor `PageImpl` như một công cụ kiểm chứng tổng số. Nếu tự dựng page, ứng dụng phải cung cấp metadata có cơ sở và hiểu các quy tắc của implementation.

### Count đúng đơn vị cũng quan trọng

Một join có thể tạo nhiều dòng cho cùng entity gốc. Count cần phản ánh đơn vị mà UI đang hiển thị. Tổng số sai do query không tương đương phải được sửa ở query/mapping, không chỉ giải thích là “dữ liệu có thể đổi”.

## 13. Giữ thông tin khi map hoặc lọc kết quả

Để đổi entity sang DTO, có thể dùng:

```java
Page<OrderSummary> summaries = page.map(this::toSummary);
```

Giả định `toSummary` chuyển từng phần tử theo hợp đồng. Việc map giữ vai trò container và metadata liên quan, kể cả khi nội dung rỗng nhưng tổng số vẫn dương vì request quá xa.

Ngược lại, lọc bớt nội dung của một trang ở Java có thể làm trang rỗng mà toàn bộ truy vấn vẫn có dữ liệu:

```text
Store trả 10 entity
    -> service bỏ cả 10 do một điều kiện bổ sung
    -> nội dung sau lọc rỗng
```

Không vì vậy mà tổng của truy vấn gốc trở thành `0`. Nếu điều kiện là một phần của bộ lọc nghiệp vụ cần phân trang, nên đưa nó vào cơ chế truy vấn thích hợp. Nếu cố ý post-filter, hợp đồng ứng dụng phải nói rõ metadata đang đếm tập nào.

Projection cũng không tự sửa count hoặc tạo dữ liệu thay thế khi thiếu entity. Auditing ghi metadata không tự đóng băng dữ liệu để các trang sau dùng chung phiên bản.

## 14. Phân biệt vượt phạm vi dữ liệu với giới hạn kỹ thuật của store

Một request có index rất lớn có thể rơi vào những tình huống khác nhau:

| Tình huống | Cách hiểu |
| --- | --- |
| Query hợp lệ, store thực hiện được, offset nằm sau kết quả cuối | Có thể nhận trang rỗng với tổng số đã biết |
| Offset vượt khả năng biểu đạt của provider/driver | Có thể bị từ chối trước hoặc trong thực thi |
| Backend có giới hạn truy cập sâu | Có thể phát lỗi theo API store |
| SQL, count query hoặc mapping sai | Đây là lỗi truy vấn, không phải trang rỗng hợp lệ |
| Kết nối hoặc quyền truy cập lỗi | Không có cơ sở kết luận tổng bằng không |

Không bắt mọi lỗi rồi trả `Page.empty(pageable)`. Làm vậy biến “không đọc được dữ liệu” thành “đã đọc thành công và không có entity”.

Commons cung cấp abstraction `Page`/`Pageable`, nhưng hành vi query, giới hạn offset và mức nhất quán phụ thuộc module, provider, driver và store. Một reactive repository cũng không tự hỗ trợ `Mono<Page<T>>` chỉ vì Commons có `Page`; phải xác nhận hình dạng kết quả theo module.

Nếu caller không cần tổng, có thể xem xét `Slice` hoặc `Window` theo khả năng store. Tuy nhiên, thay kiểu kết quả không tự giải quyết mọi vấn đề concurrent update hoặc contract ngoài phạm vi.

## 15. Kiểm thử các ranh giới quan trọng

### 15.1. Tổng bằng không và tổng chia hết cho size

Với `PageImpl` có phân trang size bằng `10`, dữ liệu ổn định:

| Tổng số | Tổng trang | Index trang cuối có dữ liệu | Số phần tử trang cuối có dữ liệu |
| --- | --- | --- | --- |
| `0` | `0` | Không có | Không có |
| `1` | `1` | `0` | `1` |
| `10` | `1` | `0` | `10` |
| `11` | `2` | `1` | `1` |
| `20` | `2` | `1` | `10` |
| `23` | `3` | `2` | `3` |

Các trường hợp `10` và `20` làm lộ lỗi tự suy `hasNext` chỉ từ việc nội dung đủ size.

### 15.2. Factory rỗng và trang vượt phạm vi

Ví dụ kiểm tra hợp đồng minh họa với JUnit, giả định đã có `request` index `3`, size `10`:

```java
Page<String> syntheticEmpty = Page.empty(request);
Page<String> outside = new PageImpl<>(List.<String>of(), request, 23L);

assertTrue(syntheticEmpty.isEmpty());
assertTrue(outside.isEmpty());

assertEquals(0L, syntheticEmpty.getTotalElements());
assertEquals(23L, outside.getTotalElements());
assertEquals(3, outside.getNumber());
assertEquals(3, outside.getTotalPages());
assertTrue(outside.isLast());
```

Kiểm tra này làm rõ vì sao nội dung rỗng và cờ last chưa đủ để kết luận toàn bộ tập rỗng.

### 15.3. Kiểm tra tích hợp với repository thật

Fixture và thao tác nên bao gồm:

- Không có entity phù hợp: trang đầu rỗng và tổng đúng.
- Trang cuối ngắn và trang cuối đầy: metadata tiếp tục đúng.
- Request sau trang cuối: nội dung rỗng nhưng giữ tổng dương nếu query/count xác định được tổng đó.
- Entity trùng khóa sort chính: khóa phụ phân định đúng thứ tự.
- Entity sai tenant/trạng thái: không lọt vào nội dung hoặc count.
- Xóa phần tử cuối rồi đọc lại index cũ: chính sách điều chỉnh trang đúng.
- Đọc hai trang với insert/delete giữa chúng: hành vi phù hợp yêu cầu nhất quán đã công bố.
- Lỗi query/store: không bị đổi thành một trang thành công tổng bằng không.

Nếu kiểm tra một kịch bản concurrency, cần điều khiển rõ thời điểm thay đổi và các ranh giới transaction. Một test fixture tĩnh không thể chứng minh hệ thống có snapshot xuyên nhiều request.

## 16. Bài tập phân tích

### Bài 1: Hai page cùng rỗng nhưng khác nghĩa

Request index `3`, size `10`. Kết quả thứ nhất là `Page.empty(request)`, kết quả thứ hai có nội dung rỗng và tổng `23`.

**Phân tích:** kết quả đầu công bố tổng bằng không. Kết quả sau nói tập dữ liệu có ba trang nhưng caller đang yêu cầu index nằm sau chúng. Không nên thay kết quả sau bằng kết quả đầu chỉ để chuẩn hóa nội dung rỗng.

### Bài 2: Trang cuối đủ size

Tổng số là `20`, page size `10`. Caller đọc index `1` và nhận mười entity.

**Phân tích:** đây vẫn là trang cuối. Không dùng `content.size() == pageSize` làm bằng chứng còn trang sau.

### Bài 3: Xóa hết nội dung của trang cuối

Tổng từ `23` giảm xuống `20` sau khi xóa ba entity cuối. Caller giữ index `2`.

**Phân tích:** index đó có thể trả rỗng dù tập còn hai mươi entity. Ứng dụng có thể giữ phản hồi rỗng cùng metadata hoặc điều hướng lại theo chính sách, nhưng không được kết luận toàn bộ filter không có kết quả.

### Bài 4: Vì sao id tie-breaker vẫn có lặp?

Hai trang dùng cùng sort đầy đủ, nhưng một entity mới được chèn trước offset giữa hai lần đọc.

**Phân tích:** bộ khóa đủ phân định không ngăn dịch chuyển vị trí. Cần đánh giá cách tiếp tục và mức nhất quán, không chỉ cấu trúc sort.

### Bài 5: Fallback khi lỗi kết nối

Một service bắt mọi exception từ repository và trả `Page.empty(pageable)` để giao diện không hiện lỗi.

**Phân tích:** service đã công bố một kết quả thành công tổng bằng không mà không có bằng chứng. Cần giữ hoặc chuyển đổi đường lỗi theo hợp đồng ứng dụng, tách nó khỏi trạng thái không có dữ liệu.

## 17. Các điểm cần nhớ

- `Page.empty(pageable)` giữ request nhưng công bố nội dung rỗng và tổng bằng không; nó không tự tra cứu tổng trong store.
- Trang rỗng có thể là một request vượt phạm vi trong khi tập kết quả vẫn có dữ liệu.
- Trang cuối có thể đầy size; `isLast()` cũng không tự chứng minh đó là trang cuối có nội dung hợp lệ.
- Chính sách giữ trang rỗng, điều hướng lại hoặc báo ngoài phạm vi thuộc hợp đồng ứng dụng và phải giữ đúng metadata.
- Insert, delete, update và query count ở thời điểm khác nhau có thể làm trạng thái trang thay đổi; sort đầy đủ không tạo snapshot.
- Mapping DTO, projection, giới hạn store và xử lý lỗi cần giữ sự khác biệt giữa không có dữ liệu, không ở đúng trang và không đọc được dữ liệu.
