# Page với count, Slice và Window theo nhu cầu client

## Mục tiêu và phạm vi

Chọn kiểu kết quả repository là một quyết định về hợp đồng dữ liệu và hiệu năng. Client cần “trang 3 trên tổng số 240 trang” khác với client chỉ cần “tải thêm”, và cả hai lại khác một tiến trình cần duyệt lần lượt nhiều triệu bản ghi.

Spring Data Commons cung cấp `Page`, `Slice`, `Window`, `Pageable` và `ScrollPosition` để diễn đạt những nhu cầu đó. Cách thực thi cụ thể thuộc module store và backend đang sử dụng.

Sau bài học này, bạn có thể:

- Chọn `Page` khi client thực sự cần tổng số kết quả.
- Chọn `Slice` khi chỉ cần nội dung cùng thông tin còn dữ liệu.
- Phân biệt scrolling dùng offset với scrolling dùng keyset qua `Window`.
- Giải thích tác động của count, offset, sort, index và projection.
- Thiết kế hợp đồng HTTP phù hợp với cách truy xuất đã chọn.
- Xác định những điều cần đo thay vì suy luận hiệu năng chỉ từ tên abstraction.

Ví dụ repository dùng Spring Data JPA ở phần mà module hỗ trợ query method và scrolling tương ứng. Không suy rằng mọi store có cùng khả năng chỉ vì các kiểu kết quả thuộc Commons.

## 1. Bắt đầu từ câu hỏi của client

Trước khi viết repository method, hãy xác định client cần biết gì.

| Nhu cầu | Thông tin thực sự cần | Hướng xem xét |
|---|---|---|
| Bảng quản trị có tổng số và số trang | Content, total elements, total pages | Page |
| Danh sách chỉ có nút tiếp theo | Content và hasNext | Slice |
| Feed hoặc tải thêm theo vị trí đã đọc | Content và vị trí tiếp tục | Window |
| Export hoặc job duyệt tuần tự | Từng nhóm dữ liệu có giới hạn, vị trí tiếp tục | Window hoặc cơ chế batch/scroll phù hợp store |
| Chỉ lấy một số kết quả đầu | List giới hạn, không cần metadata trang | Limit hoặc phương thức giới hạn phù hợp |
| Dashboard cần một con số tổng | Kết quả tổng hợp riêng | Query đếm/tổng hợp theo hợp đồng riêng |

Không trả `Page` mặc định cho mọi endpoint chỉ vì đó là kiểu quen thuộc. Nếu giao diện không hiển thị tổng số và không sử dụng tổng số trang, việc tính chúng có thể là công việc thừa.

Ngược lại, đổi `Page` thành `Slice` để tránh count nhưng vẫn hứa “trang 3 trên 240” làm hợp đồng trở nên thiếu cơ sở.

## 2. Page: trả nội dung cùng thông tin tổng thể

`Page<T>` mở rộng khả năng của một lát dữ liệu với metadata như:

- Tổng số phần tử khớp điều kiện.
- Tổng số trang theo kích thước trang.
- Số trang hiện tại, kích thước và nội dung.
- Khả năng đi tới trang trước hoặc tiếp theo.

Ví dụ:

```java
Page<OrderCard> page = orders.findByStatus(
        OrderStatus.CONFIRMED,
        PageRequest.of(
                0,
                50,
                Sort.by(
                        Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id"))));
```

Khi cần biết tổng số, implementation thường phải thực hiện một phép đếm ngoài truy vấn lấy dữ liệu.

Mô hình khái niệm:

```text
Query dữ liệu:
    điều kiện lọc
    sắp xếp
    offset và giới hạn

Query tổng số:
    đếm toàn bộ tập khớp điều kiện
```

### Không phải mọi Page luôn chạy đúng hai query

Implementation có thể suy ra total trong một số trường hợp, chẳng hạn từ một trang không đầy mà dữ liệu đã đủ để xác định tổng. Vì vậy, không coi “Page luôn bằng hai query” là hợp đồng bất biến.

Điều cần nắm là Page yêu cầu cung cấp tổng số. Chi phí đáp ứng yêu cầu đó phụ thuộc tình huống và chiến lược của store.

### Tổng số chính xác theo điều kiện nào?

Một count đúng phải phản ánh cùng tập kết quả mà client đang phân trang.

Nếu truy vấn có join, `distinct`, nhóm hoặc điều kiện phức tạp, cần bảo đảm count không vô tình đếm số dòng trung gian thay vì số thực thể kết quả.

Ngoài ra, query dữ liệu và query đếm có thể quan sát các trạng thái khác nhau nếu dữ liệu thay đổi và ranh giới đọc không cung cấp bảo đảm nhất quán cần thiết. Kiểu Page không tự tạo snapshot chung.

## 3. Vì sao count có thể chi phối thời gian phản hồi?

Giả sử endpoint trả 50 đơn hàng đầu tiên trong một tập khớp rất lớn.

Một index tốt có thể giúp database nhanh chóng tìm 50 bản ghi theo thứ tự yêu cầu. Tuy nhiên, count vẫn cần xác định kích thước của toàn bộ tập khớp theo cách backend hỗ trợ.

Chi phí có thể bao gồm:

- Duyệt nhiều entry của index.
- Kiểm tra điều kiện không được đáp ứng hoàn toàn bởi index.
- Đọc thêm dữ liệu theo mô hình lưu trữ và isolation.
- Thực hiện join hoặc xử lý trùng.
- Chờ tài nguyên khi nhiều request cùng chạy query tương tự.

Không phải count nào cũng chậm. Count trên tập nhỏ, điều kiện chọn lọc hoặc index phù hợp có thể đủ rẻ. Quyết định cần dựa vào workload thực.

Có thể tách thời gian theo mô hình:

```text
T_request =
    thời gian chờ tài nguyên
  + thời gian query dữ liệu
  + thời gian đáp ứng yêu cầu total
  + mapping
  + serialization và truyền dữ liệu
```

Đây là mô hình phân tích, không phải khẳng định các thành phần luôn chạy tuần tự hoặc có cùng tỷ trọng.

Nếu count chiếm phần lớn thời gian mà client không dùng total, thay đổi hợp đồng kết quả có thể có ích hơn việc chỉ giảm vài cột trong JSON.

## 4. Slice: biết còn dữ liệu mà không cần total

`Slice<T>` cung cấp nội dung cùng thông tin điều hướng, đặc biệt là `hasNext()`, nhưng không cung cấp tổng số phần tử hoặc tổng số trang.

Ví dụ:

```java
Slice<OrderCard> slice = orders.findAllByStatus(
        OrderStatus.CONFIRMED,
        PageRequest.of(
                0,
                50,
                Sort.by(
                        Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id"))));
```

Một cách thực thi thường gặp là đọc nhiều hơn kích thước yêu cầu một phần tử để xác định có dữ liệu tiếp theo hay không.

```text
Client cần 50 phần tử.
Backend có thể lấy tối đa 51.
Trả 50 phần tử.
Nếu có phần tử thứ 51, hasNext là true.
```

Đây là cách giải thích thuật toán thường gặp, không phải yêu cầu mọi module phải dùng chính xác một kiểu query giống nhau.

### Slice tránh yêu cầu count, không tự tránh offset

Trong ví dụ dùng `PageRequest`, trang thứ p có offset tương ứng với p nhân page size.

Đổi từ Page sang Slice có thể loại yêu cầu tính tổng, nhưng một trang rất sâu vẫn có thể chịu chi phí offset lớn.

```text
Page ở trang sâu:
    chi phí dữ liệu với offset
    cộng chi phí xác định total khi cần

Slice ở trang sâu:
    vẫn có chi phí dữ liệu với offset
    không yêu cầu total
```

Nếu vấn đề chính là duyệt sâu theo offset, chỉ đổi kiểu trả về chưa chắc giải quyết được nguyên nhân.

### Một lát đầy không có nghĩa còn lát tiếp

Nếu toàn bộ tập có đúng 50 phần tử, lát đầu có đủ 50 nhưng `hasNext()` vẫn phải là false.

Không tự tính `hasNext = content.size() == pageSize` ở service rồi bỏ qua metadata mà repository cung cấp.

## 5. Offset pagination: tiện cho số trang, cần xem độ sâu

Với page index bắt đầu từ 0:

```text
offset = pageIndex × pageSize
```

Ví dụ page index bằng 10000 và page size bằng 50 có offset bằng 500000.

Một execution plan có thể phải duyệt hoặc bỏ qua nhiều entry trước khi tìm được nhóm cần trả. Chi tiết phụ thuộc index, điều kiện lọc, cách sắp xếp và optimizer.

Không nên diễn giải rằng backend luôn chỉ xử lý đúng 50 phần tử vì client chỉ nhận 50 phần tử.

SQL minh họa theo cú pháp có LIMIT/OFFSET:

```sql
SELECT id, created_at, total
FROM sales_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

Cú pháp thực tế cần phù hợp database. Spring Data module chịu trách nhiệm dịch query và tham số theo store khi phương thức hỗ trợ cách truy xuất đó.

Offset phù hợp khi:

- Client cần địa chỉ trang theo số.
- Độ sâu có giới hạn hợp lý.
- Dữ liệu và query đủ nhỏ hoặc đủ nhanh cho workload.
- Nhu cầu truy cập ngẫu nhiên vào trang là có thật.

Không cần thay mọi offset query bằng keyset nếu phép đo cho thấy chi phí hiện tại đáp ứng được yêu cầu.

## 6. Window: một nhóm kết quả gắn với vị trí tiếp tục

`Window<T>` mô tả một nhóm dữ liệu thu được từ hoạt động scrolling. Người gọi có thể lấy nội dung, kiểm tra còn kết quả và lấy vị trí để tiếp tục.

Khác biệt quan trọng với suy nghĩ theo số trang:

```text
Phân trang theo số:
    cho tôi trang 100

Scrolling:
    tiếp tục sau vị trí đã đọc trước đó
```

`Window` không tự có tổng số phần tử và không tự hứa truy cập ngẫu nhiên tới mọi trang theo số.

Vị trí tiếp tục được biểu diễn bởi `ScrollPosition`. Tùy khả năng module, có thể dùng:

- Offset position.
- Keyset position.

Do đó, không nói “dùng Window là đã dùng keyset”. Window là kiểu kết quả; chiến lược vị trí mới quyết định cách tiếp tục.

Window cũng không đồng nghĩa một database cursor phải được giữ mở xuyên nhiều request HTTP. Cách giữ tài nguyên thực tế thuộc implementation và hạ tầng truy vấn.

## 7. Offset Window và keyset Window giải quyết các vấn đề khác nhau

### Offset position

Offset scrolling vẫn xác định vị trí bằng số lượng phần tử đã đi qua.

Nó hữu ích để diễn đạt việc duyệt theo window, nhưng không tự loại bỏ chi phí offset lớn ở backend.

### Keyset position

Keyset scrolling tiếp tục theo giá trị các khóa sắp xếp của kết quả cuối đã đọc, thay vì chỉ nói “bỏ qua bao nhiêu phần tử”.

Với thứ tự:

```text
createdAt DESC, id DESC
```

Giả sử bản ghi cuối của window hiện tại có:

```text
createdAt = T
id = I
```

Điều kiện tiếp tục có dạng khái niệm:

```sql
SELECT id, created_at, total
FROM sales_order
WHERE status = :status
  AND (
       created_at < :last_created_at
       OR (
           created_at = :last_created_at
           AND id < :last_id
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Các phép so sánh phải tương ứng với từng hướng sort. Khi có nhiều khóa hoặc hướng tăng giảm hỗn hợp, điều kiện tiếp tục cũng cần phản ánh đúng thứ tự đó.

Trong module hỗ trợ keyset scrolling, framework xây dựng phần tiếp tục theo hợp đồng của nó. Không cần tự viết lại điều kiện trên chỉ để dùng API scrolling.

### Tác động lên chi phí

Khi có index phù hợp, backend có thể tìm vùng khóa cần tiếp tục thay vì duyệt một offset ngày càng lớn.

Đó là cơ hội tối ưu, không phải bảo đảm mọi query keyset đều nhanh. Nếu điều kiện lọc hoặc sort không phù hợp index, database vẫn có thể làm nhiều công việc.

## 8. Ví dụ repository với ba hợp đồng khác nhau

Giả định entity `SalesOrder` có các property:

- `id`: Long, định danh duy nhất.
- `status`: OrderStatus.
- `createdAt`: Instant, không null.
- `total`: BigDecimal.

Projection cho danh sách:

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface OrderCard {

    Long getId();

    Instant getCreatedAt();

    BigDecimal getTotal();
}
```

Repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<SalesOrder, Long> {

    Page<OrderCard> findByStatus(
            OrderStatus status,
            Pageable pageable);

    Slice<OrderCard> findAllByStatus(
            OrderStatus status,
            Pageable pageable);

    Window<OrderCard>
            findFirst50ByStatusOrderByCreatedAtDescIdDesc(
                    OrderStatus status,
                    ScrollPosition position);
}
```

Các đoạn mã giả định dự án đã có entity, enum, mapping và hạ tầng JPA phù hợp. Chúng minh họa hợp đồng repository, không phải toàn bộ ứng dụng chạy độc lập.

Điểm cần quan sát:

- Page và Slice nhận Pageable.
- Window nhận ScrollPosition.
- Phương thức Window giới hạn mỗi lần đọc bằng `First50`.
- Sort của Window được cố định để ý nghĩa vị trí tiếp tục rõ ràng.
- Projection chứa các property dùng làm khóa sắp xếp.

Không áp dụng chữ ký scrolling này vào mọi kiểu query hoặc mọi store mà không kiểm tra khả năng hỗ trợ. Việc một module hỗ trợ derived query thông thường không tự chứng minh mọi query string, join hoặc projection tùy biến đều hỗ trợ scrolling.

## 9. Duyệt bằng keyset Window mà không gom toàn bộ kết quả

Ví dụ xử lý tuần tự trong ứng dụng:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public void processConfirmedOrders() {
    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<OrderCard> window =
                orders.findFirst50ByStatusOrderByCreatedAtDescIdDesc(
                        OrderStatus.CONFIRMED,
                        position);

        if (window.isEmpty()) {
            break;
        }

        for (OrderCard order : window.getContent()) {
            processOne(order);
        }

        if (!window.hasNext()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Đoạn mã giả định `orders` được inject và `processOne` đã được định nghĩa.

Các điểm quan trọng:

1. Bắt đầu từ initial keyset position.
2. Xử lý một nhóm kết quả có giới hạn.
3. Chỉ lấy vị trí từ phần tử tồn tại.
4. Lấy vị trí của phần tử cuối đã xử lý.
5. Tiếp tục khi window báo còn dữ liệu.

Vị trí tiếp tục có tính exclusive: nó diễn đạt việc đi tiếp sau phần tử đã đọc. Không tự tăng offset hoặc sửa các key trong position do repository cung cấp.

Với offset scrolling, cũng cần phân biệt initial offset position với một position đã trỏ tới offset cụ thể. Không mặc định `ScrollPosition.offset()` và `ScrollPosition.offset(0)` có cùng ý nghĩa bắt đầu.

### Giới hạn bộ nhớ và thời gian sống giao dịch

Đọc 50 phần tử mỗi lần không tự bảo đảm toàn bộ job chỉ giữ 50 object trong bộ nhớ.

Ứng dụng vẫn có thể làm bộ nhớ tăng nếu:

- Thêm mọi kết quả vào một list chung.
- Giữ persistence context quá lâu với nhiều entity được quản lý.
- Tích lũy payload hoặc tác vụ bất đồng bộ chưa hoàn tất.
- Mở một transaction rất dài cho toàn bộ job.

Nếu cần xử lý theo chunk, hãy thiết kế transaction, giải phóng tài nguyên và checkpoint theo khả năng của store. Projection nhỏ có thể giảm dữ liệu phải tạo, nhưng không thay thế việc quản lý vòng đời xử lý.

## 10. Điều kiện để keyset hoạt động đúng

### 10.1. Sort phải xác định

Chỉ dùng `createdAt DESC` có thể để nhiều bản ghi bằng nhau ở cùng một thời điểm.

Thêm khóa duy nhất như `id DESC` giúp phân biệt vị trí:

```text
createdAt DESC, id DESC
```

Một số implementation có thể bổ sung khóa định danh để ổn định thứ tự. Viết rõ khóa trong hợp đồng giúp người đọc hiểu và giúp thiết kế index tương ứng.

### 10.2. Khóa sắp xếp phải được truy xuất

Framework cần các giá trị khóa để tạo vị trí tiếp tục.

Nếu dùng projection, phải đáp ứng yêu cầu của module về các trường sắp xếp và định danh. Trong ví dụ, OrderCard có cả id và createdAt.

Đừng bỏ createdAt khỏi projection của query keyset chỉ để giảm vài byte rồi mong framework vẫn có đủ dữ liệu tạo vị trí.

Sau khi repository đã trích xuất position, lớp HTTP có thể chuyển nội dung thành DTO riêng theo hợp đồng công khai.

### 10.3. Giá trị null cần được xét trước

Keyset phụ thuộc phép so sánh các khóa. Giá trị null có thể làm điều kiện tiếp tục không tương đương thứ tự mà backend áp dụng.

Một lựa chọn rõ ràng cho ví dụ là bảo đảm createdAt và id không null, đồng thời dùng các property mà module hỗ trợ keyset đúng.

Không giả định null ordering hint sẽ làm mọi query keyset trên mọi backend trở nên hợp lệ.

### 10.4. Khóa thay đổi có thể làm phần tử dịch vị trí

Nếu sort theo `lastModifiedAt` và thao tác xử lý lại sửa chính trường đó, bản ghi có thể chuyển sang một vùng khác trong thứ tự.

Keyset không tự ngăn việc đọc lặp hoặc bỏ sót trong một tập dữ liệu đang thay đổi theo cách đó.

Với job cần duyệt một tập xác định, có thể cần mốc chặn, snapshot hoặc một cơ chế ghi nhận công việc riêng. Ví dụ mốc createdAt chỉ có ý nghĩa nếu quy tắc gán thời điểm và phạm vi dữ liệu đáp ứng giả định của job.

## 11. Index phải đi cùng điều kiện lọc và sort

Với query lọc status và sort theo createdAt, id, một index để đánh giá có thể là:

```sql
CREATE INDEX idx_order_status_created_id
ON sales_order (status, created_at DESC, id DESC);
```

Đây là ví dụ thiết kế index cho backend hỗ trợ cú pháp đó, không phải hướng dẫn áp dụng nguyên trạng cho mọi database.

Cần kiểm tra execution plan và workload để biết:

- Điều kiện status có được dùng hiệu quả không?
- Backend có tránh được bước sort lớn không?
- Keyset predicate có giúp tìm đúng vùng index không?
- Có phải đọc thêm nhiều bản ghi để kiểm tra điều kiện khác không?
- Index có làm tăng đáng kể chi phí ghi hoặc dung lượng không?

Nếu query có tenant, tenant phải nằm trong điều kiện lọc được thực thi. Thiết kế index cần tính đến điều kiện đó, chẳng hạn xem xét tenant trước các khóa phù hợp khác.

Không thêm mọi tổ hợp sort thành index một cách máy móc. Cho client sắp xếp tự do theo quá nhiều trường có thể khiến không có một chiến lược index hiệu quả cho tất cả request.

## 12. Projection giảm dữ liệu, không tự xóa chi phí khác

Một danh sách chỉ cần id, createdAt và total không nhất thiết phải tải toàn bộ aggregate cùng các quan hệ.

Projection hoặc DTO query có thể giúp giảm:

- Số cột hoặc trường cần đọc, tùy module.
- Dữ liệu truyền từ backend.
- Chi phí tạo object và mapping.
- Kích thước response.

Tuy nhiên:

- Không phải mọi projection đều dẫn tới cùng mức tối ưu.
- Projection có biểu thức hoặc quan hệ lồng có thể phát sinh xử lý thêm.
- Count vẫn có thể đắt dù content rất nhỏ.
- Offset sâu vẫn có thể đắt dù mỗi hàng chỉ có vài cột.
- Mapping hoặc serialization có thể truy cập dữ liệu ngoài dự kiến.

Hãy chọn hình dạng dữ liệu phù hợp, rồi kiểm tra query thực tế. Không dùng “trả projection” như bằng chứng đủ rằng một endpoint đã tối ưu.

## 13. Thiết kế response theo khả năng dữ liệu thực sự có

### Page cho giao diện có tổng số

```json
{
  "items": [],
  "page": 3,
  "size": 50,
  "totalElements": 12000,
  "totalPages": 240
}
```

Các con số trên chỉ minh họa cấu trúc response. Trong một response thật, nội dung và metadata phải nhất quán với kết quả query.

### Slice cho điều hướng tiếp theo

```json
{
  "items": [],
  "page": 3,
  "size": 50,
  "hasNext": true
}
```

Không tự thêm `totalElements` bằng cách lấy số phần tử đã đọc đến hiện tại. Đó không phải tổng số khớp điều kiện.

### Window cho tiếp tục bằng cursor

```json
{
  "items": [],
  "hasNext": true,
  "nextCursor": "opaque-token"
}
```

Các array rỗng trong ba ví dụ là chỗ biểu diễn hình dạng dữ liệu, không phải ví dụ kết quả truy vấn hoàn chỉnh. Một Window thực sự rỗng không nên được công bố như đang có một cursor tiếp tục hợp lệ nếu implementation không cung cấp cơ sở cho điều đó.

Ứng dụng nên dùng DTO hoặc mô hình phân trang được cấu hình rõ ràng. Không để client phụ thuộc vào serialization ngẫu nhiên của một implementation nội bộ.

## 14. Cursor phải giữ đúng ngữ cảnh của lần duyệt

`ScrollPosition` là abstraction nội bộ; không nhất thiết là định dạng token công khai ổn định.

Một thiết kế cursor cần xác định:

- Query hoặc bộ lọc nào mà cursor thuộc về.
- Sort và hướng duyệt.
- Vị trí tiếp tục.
- Tenant hoặc phạm vi truy cập liên quan.
- Phiên bản định dạng token.
- Thời hạn hiệu lực nếu ứng dụng có chính sách hết hạn.

Nếu đổi filter hoặc sort nhưng vẫn dùng cursor cũ, kết quả có thể không còn ý nghĩa. Hãy từ chối hoặc khởi động lại lượt duyệt theo hợp đồng đã định nghĩa.

Có thể dùng token tham chiếu tới trạng thái phía server hoặc token chứa dữ liệu có cơ chế kiểm tra tính toàn vẹn. Base64 đơn thuần chỉ mã hóa biểu diễn, không chứng minh token chưa bị sửa.

Cursor không thay thế authorization. Mỗi request vẫn cần áp dụng điều kiện truy cập và tenant từ ngữ cảnh đáng tin cậy.

Không mặc định keyset cursor cho phép client nhảy thẳng tới “trang 1000”. Muốn điều đó cần một thiết kế bổ sung hoặc chấp nhận cách truy xuất khác.

## 15. Nhất quán khi dữ liệu thay đổi

Ba abstraction không tự biến nhiều request thành một snapshot:

| Tình huống | Điều cần hiểu |
|---|---|
| Page lấy content và total | Có thể lệch thời điểm quan sát nếu giao dịch/isolation không bảo đảm điều cần thiết |
| Slice theo offset | Insert hoặc delete trước offset có thể làm dịch phần tử giữa các request |
| Window theo keyset | Tránh phụ thuộc số lượng đã bỏ qua, nhưng bản ghi thay đổi khóa sort vẫn có thể dịch vị trí |
| Job xử lý rồi lưu checkpoint | Tiến trình dừng giữa xử lý và checkpoint có thể làm xử lý lại |
| Cursor tồn tại lâu | Filter, dữ liệu hoặc quyền truy cập có thể đã thay đổi |

Với job cần khả năng tiếp tục sau lỗi:

- Xác định checkpoint biểu diễn vị trí đã đọc hay đã xử lý thành công.
- Thiết kế thao tác xử lý chịu được lặp khi cần.
- Không lưu checkpoint trước khi các tác dụng cần thiết đã được ghi nhận bền vững.
- Xác định cách xử lý dữ liệu mới hoặc bị sửa trong lúc job chạy.

Window cung cấp vị trí truy xuất. Nó không tự cung cấp chính sách giao nhận đúng một lần cho tác dụng phụ của job.

## 16. Có thể tách total ra khỏi từng lần tải dữ liệu không?

Nếu client cần tổng số nhưng không cần tính lại ở mỗi lần tải thêm, có thể thiết kế tổng số như một thông tin riêng.

Ví dụ:

- Một endpoint trả danh sách bằng Slice hoặc Window.
- Một endpoint khác cung cấp count theo cùng bộ lọc.
- Count có thể được tính theo yêu cầu, cache hoặc cập nhật theo mô hình tổng hợp phù hợp.

Điều kiện là hợp đồng phải nói rõ count mang ý nghĩa gì:

| Loại total | Điều cần công bố |
|---|---|
| Count tại thời điểm query | Không bảo đảm luôn đồng bộ với một request danh sách khác |
| Count được cache | Có thể cũ theo chính sách cache |
| Count ước lượng | Phải phân biệt với tổng số chính xác |
| Count của snapshot xác định | Cần có cơ chế xác định snapshot và vòng đời tương ứng |

Không đặt một con số ước lượng hoặc cũ vào `Page.getTotalElements()` rồi để client hiểu là total chính xác của query hiện tại mà không có hợp đồng phù hợp.

Cache key phải phản ánh điều kiện lọc và phạm vi truy cập. Dùng chung count giữa các tenant là một lỗi về tính đúng, không chỉ là sai số hiệu năng.

## 17. Đo hiệu năng theo hành vi client

Một so sánh hữu ích nên dùng cùng dữ liệu và workload đại diện.

Các tình huống cần quan sát:

- Trang đầu.
- Trang ở độ sâu thường gặp.
- Trang sâu nhất được cho phép.
- Bộ lọc rất chọn lọc.
- Bộ lọc khớp phần lớn dữ liệu.
- Tải đồng thời.
- Dữ liệu đang có hoạt động ghi.

Các chỉ số cần xem có thể gồm:

| Chỉ số | Giúp nhận diện |
|---|---|
| Độ trễ trung vị và các phân vị cao | Trải nghiệm thường gặp và trường hợp chậm |
| Thời gian query dữ liệu | Chi phí filter, sort, offset hoặc keyset |
| Thời gian count | Phần chi phí để cung cấp total |
| Số dòng/entry backend phải xem xét | Chênh lệch giữa dữ liệu trả về và công việc thực |
| Lưu lượng dữ liệu | Tác động của projection và page size |
| Bộ nhớ ứng dụng | Object, persistence context, buffer và tích lũy kết quả |
| Thời gian giữ connection | Áp lực lên pool khi nhiều request cùng chạy |

Không tạo kết luận từ một lần chạy trên fixture rất nhỏ. Cũng không dùng số query như thước đo duy nhất: một count tốn nhiều thời gian có thể quan trọng hơn vài query nhỏ.

Các ví dụ trong bài giải thích mô hình chi phí, không đại diện cho benchmark đã được đo trên một hệ thống cụ thể.

## 18. Cây quyết định và bài thực hành

Có thể bắt đầu với chuỗi câu hỏi:

```text
Client có cần total chính xác không?
    |
    +-- Có: xem Page và chi phí count
    |
    +-- Không:
          |
          +-- Cần số trang và next theo offset?
          |      -> xem Slice với giới hạn độ sâu
          |
          +-- Cần duyệt tiếp sau vị trí đã đọc?
                 -> xem Window
                        |
                        +-- offset: vẫn xét chi phí bỏ qua
                        |
                        +-- keyset: xét sort, key, index
```

Bài thực hành với một store hỗ trợ các hình thức cần dùng:

1. Viết một query Page cho danh sách cần tổng số.
2. Viết query Slice cùng điều kiện và sort cho client chỉ cần tải tiếp.
3. Viết query Window với sort cố định và initial keyset position.
4. Chuẩn bị nhiều bản ghi có cùng createdAt để kiểm tra khóa id phụ.
5. Duyệt hết tập dữ liệu tĩnh và kiểm tra không lặp, không thiếu.
6. Quan sát query dữ liệu và count khi trả Page.
7. So sánh trang đầu với offset sâu và keyset continuation trên dữ liệu đại diện.
8. Thiết kế DTO cho mỗi kiểu response mà không tạo metadata giả.
9. Mô tả điều gì xảy ra khi dữ liệu bị thêm, xóa hoặc sửa khóa sort giữa hai lần đọc.
10. Thiết kế cursor không được dùng lại với filter hoặc tenant khác.

Mục tiêu là giải thích lựa chọn bằng nhu cầu của client và kết quả quan sát, không chỉ bằng số lượng phương thức repository.

## 19. Những điều cần nắm vững

Page phù hợp khi total là một phần cần thiết của hợp đồng. Slice bỏ yêu cầu total nhưng cách dùng với Pageable vẫn có thể chịu chi phí offset. Window chuyển trọng tâm sang vị trí tiếp tục, còn hiệu quả duyệt sâu phụ thuộc việc dùng offset hay keyset cùng khả năng của store.

Keyset cần thứ tự xác định, khóa phù hợp, dữ liệu khóa có thể truy xuất và index tương ứng. Nó không thay thế snapshot, authorization hoặc chính sách xử lý lại của một job.

Hãy chọn abstraction từ thông tin client thực sự cần, rồi đo phần công việc mà backend và ứng dụng phải làm để đáp ứng hợp đồng đó.
