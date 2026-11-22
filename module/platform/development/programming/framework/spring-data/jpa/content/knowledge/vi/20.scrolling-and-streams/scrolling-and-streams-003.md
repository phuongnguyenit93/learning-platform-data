# So sánh offset scrolling và keyset scrolling

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích offset scrolling và keyset scrolling khác nhau ở cách xác định vị trí tiếp theo.
- Chọn chiến lược phù hợp cho phân trang giao diện, duyệt dữ liệu lớn và export.
- Dùng `Window<T>`, `ScrollPosition` và `WindowIterator` trong Spring Data.
- Thiết kế thứ tự sắp xếp ổn định và index hỗ trợ keyset.
- Nhận biết ảnh hưởng của offset lớn, dữ liệu thay đổi đồng thời và thuộc tính sort nullable.
- Kiểm thử việc duyệt nhiều cửa sổ dữ liệu mà không bỏ sót hoặc lặp bản ghi ngoài dự kiến.

## 1. Scrolling giải quyết bài toán gì?

Một truy vấn có thể trả về hàng trăm nghìn hoặc hàng triệu bản ghi. Tải tất cả vào một `List` có thể tiêu tốn nhiều bộ nhớ, tăng thời gian phản hồi và gây áp lực lên database.

Scrolling chia kết quả thành từng cửa sổ nhỏ (window). Ứng dụng xử lý một cửa sổ rồi yêu cầu cửa sổ tiếp theo bằng một vị trí tiếp tục (scroll position).

Trong Spring Data, Scroll API dùng các kiểu chính:

- `Window<T>`: một nhóm kết quả có giới hạn, kèm khả năng cho biết còn dữ liệu tiếp theo hay không.
- `ScrollPosition`: vị trí dùng để tiếp tục truy vấn.
- `WindowIterator<T>`: iterator tự gọi repository method với vị trí tiếp theo để duyệt các window.

Hai chiến lược xác định vị trí phổ biến là:

- **Offset scrolling**: bỏ qua một số lượng bản ghi tính từ đầu tập kết quả.
- **Keyset scrolling**: tiếp tục sau giá trị khóa sắp xếp của bản ghi cuối cùng đã đọc.

Cả hai đều giúp xử lý dữ liệu theo từng phần. Khác biệt nằm ở cách database tìm phần tiếp theo và loại workload mà mỗi cách phù hợp.

## 2. Offset scrolling

Offset scrolling xác định vị trí bằng số lượng bản ghi cần bỏ qua. Ví dụ, lấy 100 dòng sau 50.000 dòng đầu:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE status = 'PAID'
ORDER BY created_at ASC, id ASC
LIMIT 100 OFFSET 50000;
~~~

Cú pháp SQL thực tế có thể khác theo database và dialect. Ý nghĩa chung là database phải xác định thứ tự kết quả, bỏ qua 50.000 dòng đầu rồi trả về 100 dòng tiếp theo.

### Ưu điểm

- Dễ hiểu vì vị trí là một con số.
- Có thể nhảy tới một offset hoặc trang cụ thể.
- Phù hợp với màn hình cần điều hướng đến trang số 1, 2, 3...
- Không yêu cầu lưu giá trị các cột sắp xếp của bản ghi cuối cùng.
- Có thể dùng với nhiều kiểu sort, miễn query có thứ tự phù hợp.

### Hạn chế

Khi offset lớn, database thường phải đi qua hoặc xác định nhiều dòng trước khi trả phần cần lấy. Chi phí có thể tăng theo độ sâu của trang, đặc biệt khi query phải sort hoặc join trên tập dữ liệu lớn.

Offset cũng nhạy với thay đổi dữ liệu giữa các lần gọi. Giả sử trang đầu đã trả 100 dòng. Trước khi lấy offset 100, có một bản ghi mới được chèn vào trước vị trí đó. Các dòng bị dịch chuyển; lần gọi tiếp theo có thể lặp lại một dòng đã thấy. Nếu bản ghi bị xóa, ứng dụng có thể bỏ qua một dòng.

Vì vậy, offset pagination không tự bảo đảm một lần duyệt nhất quán khi dữ liệu liên tục thay đổi.

## 3. Keyset scrolling

Keyset scrolling dùng giá trị của các cột sắp xếp ở bản ghi cuối cùng đã đọc để xác định vị trí tiếp theo. Thay vì nói “bỏ qua 50.000 dòng”, ứng dụng nói “lấy các dòng đứng sau khóa sắp xếp này”.

Giả sử thứ tự là:

~~~sql
ORDER BY created_at ASC, id ASC
~~~

Sau khi đọc bản ghi cuối cùng có:

~~~text
created_at = 2026-10-01T10:30:00Z
id = 850
~~~

Truy vấn tiếp theo có thể được biểu diễn về mặt logic như sau:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE status = 'PAID'
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at ASC, id ASC
LIMIT 100;
~~~

Đây là cách diễn đạt điều kiện keyset cho thứ tự tăng dần; SQL do provider sinh có thể dùng cấu trúc khác tùy database. Với thứ tự giảm dần hoặc sort hỗn hợp ASC/DESC, toán tử so sánh phải phù hợp với từng hướng.

### Ưu điểm

- Không phải bỏ qua một số lượng lớn bản ghi trước cursor.
- Hiệu năng thường ổn định hơn khi duyệt sâu nếu có index phù hợp.
- Ít bị dịch chuyển vị trí do insert/delete ở phía trước cursor.
- Phù hợp với export, batch processing, feed và duyệt tập dữ liệu lớn theo thứ tự.

### Hạn chế

- Không nhảy trực tiếp đến trang số bất kỳ nếu chưa có keyset position của trang đó.
- Cần thứ tự sắp xếp ổn định và xác định duy nhất.
- Các thuộc tính sort cần được chọn trong projection và phải đáp ứng yêu cầu của keyset.
- Thuộc tính sort nullable gây khó xác định thứ tự so sánh; Spring Data keyset scrolling yêu cầu các keyset property không null.
- Nếu giá trị sort thay đổi trong khi đang duyệt, bản ghi có thể di chuyển qua vị trí cursor.
- Không tự tạo một snapshot nhất quán của toàn bộ dữ liệu.

## 4. Vì sao phải có thứ tự duy nhất?

Nếu chỉ sắp xếp theo `createdAt`, nhiều đơn hàng có thể cùng timestamp. Khi đó, vị trí sau timestamp cuối cùng không đủ để xác định chính xác bản ghi tiếp theo.

Hãy thêm một thuộc tính duy nhất làm tie-breaker, thường là primary key:

~~~sql
ORDER BY created_at ASC, id ASC
~~~

Thứ tự này tạo một thứ tự toàn phần nếu `id` duy nhất. Keyset position sẽ chứa các giá trị sort cần thiết, ví dụ `createdAt` và `id`.

Quy tắc thực hành:

1. Chọn thuộc tính sort phù hợp với use case.
2. Thêm một khóa duy nhất ở cuối để phân biệt các dòng có cùng giá trị sort.
3. Giữ thứ tự sort cố định trong suốt quá trình scrolling.
4. Bảo đảm các thuộc tính keyset không null.
5. Nếu dùng projection, trả về tất cả thuộc tính sort và khóa duy nhất.

Nếu đổi sort giữa hai lần gọi, vị trí keyset cũ có thể không còn tương ứng với query mới. Không dùng cursor tạo từ một thứ tự để tiếp tục một query có thứ tự khác.

## 5. So sánh trực tiếp

| Tiêu chí | Offset scrolling | Keyset scrolling |
|---|---|---|
| Vị trí tiếp tục | Số dòng đã bỏ qua | Giá trị các cột sort của dòng cuối |
| Truy vấn phần sâu | Có thể tốn chi phí lớn do phải đi qua nhiều dòng | Thường hiệu quả hơn với index phù hợp |
| Nhảy tới trang bất kỳ | Thuận tiện | Không thuận tiện nếu chưa có cursor |
| Thứ tự sort | Cần sort ổn định để tránh kết quả khó đoán | Bắt buộc ổn định và có tie-breaker duy nhất |
| Thuộc tính nullable | Có thể dùng tùy query/database | Keyset property cần không null |
| Dữ liệu thay đổi giữa các lần gọi | Insert/delete trước offset dễ làm lặp hoặc bỏ sót | Ít bị dịch chuyển do thay đổi trước cursor, nhưng không phải snapshot |
| Projection | Linh hoạt hơn về sort keys | Phải bao gồm các keyset/sort properties |
| Trường hợp phù hợp | UI có số trang, tập dữ liệu vừa phải | Export, feed, batch và duyệt dữ liệu lớn |

Không có chiến lược nào tốt hơn trong mọi trường hợp. Hãy chọn theo cách người dùng điều hướng, kích thước dữ liệu, tốc độ ghi đồng thời và khả năng tạo index.

## 6. Dùng Scroll API trong Spring Data

Spring Data cung cấp `Window<T>` và `ScrollPosition` trong Scroll API. API này có từ Spring Data 3.1; hãy kiểm tra phiên bản Spring Data được Spring Boot BOM quản lý trước khi áp dụng.

Repository method có thể trả về một window:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Window<Order> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Method trên:

- Lọc theo `status`.
- Lấy tối đa 100 kết quả trong một window.
- Sắp xếp theo `createdAt` tăng dần rồi `id` tăng dần.
- Nhận `ScrollPosition` để xác định vị trí bắt đầu.

`Window` không giống `Page`: nó không cung cấp tổng số dòng hoặc tổng số trang. Nó tập trung vào việc tiếp tục duyệt kết quả. Có thể kiểm tra `window.hasNext()` để biết còn window sau hay không.

## 7. Bắt đầu offset scrolling

Dùng vị trí khởi đầu offset:

~~~java
ScrollPosition position = ScrollPosition.offset();

Window<Order> window =
    orderRepository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus.PAID,
        position
    );
~~~

`ScrollPosition.offset()` biểu diễn vị trí ban đầu trước phần tử đầu tiên. Vì scroll position mang semantics vị trí độc quyền (exclusive), không nên nhầm nó với `ScrollPosition.offset(0)`, vốn biểu diễn vị trí của phần tử tại offset 0.

Sau khi xử lý window, có thể lấy vị trí ở phần tử cuối để tiếp tục:

~~~java
if (window.hasNext() && !window.isEmpty()) {
    ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

    Window<Order> nextWindow =
        orderRepository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus.PAID,
            nextPosition
        );
}
~~~

Vị trí lấy từ phần tử cuối cho phép truy vấn tiếp tục sau phần tử đó. Trong code thực tế, phải giữ cùng predicate và sort giữa các lần gọi.

## 8. Bắt đầu keyset scrolling

Dùng vị trí khởi đầu keyset:

~~~java
ScrollPosition position = ScrollPosition.keyset();

Window<Order> firstWindow =
    orderRepository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus.PAID,
        position
    );
~~~

Ở lần gọi đầu, chưa có giá trị cursor nên Spring Data lấy từ đầu tập kết quả. Các window tiếp theo sử dụng keyset position dựa trên các giá trị sort của phần tử cuối trong window trước.

Không tự tạo một offset rồi truyền vào query với kỳ vọng nó trở thành keyset position. Kiểu ScrollPosition xác định chiến lược scrolling được sử dụng.

## 9. Duyệt liên tục bằng WindowIterator

Nếu cần xử lý toàn bộ kết quả, `WindowIterator` giúp tránh viết vòng lặp quản lý vị trí thủ công.

Ví dụ keyset scrolling:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Order> iterator = WindowIterator
    .of(position ->
        orderRepository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus.PAID,
            position
        )
    )
    .startingAt(ScrollPosition.keyset());

while (iterator.hasNext()) {
    Order order = iterator.next();
    process(order);
}
~~~

Để dùng offset scrolling, thay vị trí bắt đầu:

~~~java
WindowIterator<Order> iterator = WindowIterator
    .of(position ->
        orderRepository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus.PAID,
            position
        )
    )
    .startingAt(ScrollPosition.offset());
~~~

Iterator tự yêu cầu window kế tiếp khi cần. Ứng dụng xử lý từng phần tử thay vì tải toàn bộ kết quả vào bộ nhớ.

Nếu mục tiêu là export file lớn, không nên gom tất cả entity vào một List trước khi ghi file. Hãy xử lý từng phần tử hoặc từng window, giải phóng tham chiếu không cần thiết và theo dõi thời gian truy vấn.

Ví dụ trên là fragment cần đặt trong service/repository có các dependency tương ứng; `process(order)` là thao tác nghiệp vụ của ứng dụng, không phải API của Spring Data.

## 10. Thiết kế index cho keyset

Keyset hiệu quả khi database có index phù hợp với điều kiện lọc và thứ tự sort.

Với truy vấn:

~~~sql
WHERE status = ?
ORDER BY created_at ASC, id ASC
~~~

Một index có thể phù hợp là:

~~~sql
CREATE INDEX idx_orders_status_created_id
    ON orders(status, created_at, id);
~~~

Thứ tự cột trong index quan trọng:

- `status` đứng đầu vì là điều kiện equality.
- `created_at` và `id` theo thứ tự sort và cursor.
- Index giúp database tìm phần tử sau keyset nhanh hơn mà không phải quét/bỏ qua hàng chục nghìn dòng.

Index cụ thể cần được xác nhận bằng execution plan của database đích. Nếu predicate có nhiều điều kiện, sort khác hoặc phân bố dữ liệu lệch, index này có thể chưa tối ưu.

Không tạo index theo mọi tổ hợp sort tùy ý. Index làm tăng chi phí insert/update và dung lượng lưu trữ. Hãy dựa trên query thực tế và workload.

## 11. Projection khi dùng keyset

Nếu repository trả về entity, các thuộc tính sort thường có sẵn. Nếu dùng DTO hoặc interface projection, kết quả phải chứa tất cả thuộc tính cần thiết để tạo keyset position.

Ví dụ projection:

~~~java
public interface OrderScrollView {
    Long getId();
    Instant getCreatedAt();
    BigDecimal getTotalAmount();
}
~~~

Repository:

~~~java
Window<OrderScrollView> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
    OrderStatus status,
    ScrollPosition position
);
~~~

Projection cần có `id` và `createdAt` vì cả hai đều tham gia sort. Nếu chỉ trả `totalAmount` và bỏ các sort properties, Spring Data không có đủ giá trị để tạo keyset position.

Với projection tùy chỉnh, kiểm tra cả tên property lẫn kiểu dữ liệu. Đừng chỉ kiểm tra dữ liệu hiển thị; keyset còn cần metadata của sort key.

## 12. Dữ liệu thay đổi trong lúc scrolling

Scrolling qua nhiều lần gọi thường không đồng nghĩa với một transaction snapshot duy nhất.

### Offset và thay đổi dữ liệu

Giả sử window đầu lấy các dòng 1–100. Một dòng mới được chèn ở vị trí trước dòng 100. Khi gọi offset 100, ranh giới đã dịch chuyển; có thể nhận lại dòng 100 cũ hoặc bỏ qua một dòng tùy thứ tự và thời điểm commit.

Xóa một dòng trước offset cũng làm các dòng phía sau dịch chuyển theo hướng ngược lại.

### Keyset và thay đổi dữ liệu

Keyset tiếp tục sau giá trị sort cuối cùng. Một bản ghi mới có sort key nhỏ hơn hoặc bằng cursor thường nằm phía trước vị trí hiện tại và không xuất hiện trong phần còn lại. Một bản ghi mới có sort key lớn hơn cursor có thể xuất hiện trong window sau.

Nếu một bản ghi đã tồn tại bị thay đổi `createdAt` để chuyển từ phía sau cursor sang phía trước hoặc ngược lại, nó có thể bị bỏ qua hoặc xuất hiện ở vị trí khác. Vì vậy, các thuộc tính sort nên bất biến trong quá trình duyệt nếu cần kết quả dễ dự đoán.

Keyset giảm tác động của dịch chuyển offset, nhưng không bảo đảm snapshot consistency.

### Khi cần export nhất quán

Nếu yêu cầu nghiệp vụ là export đúng một tập dữ liệu tại một thời điểm:

- Xác định semantics snapshot và mức isolation database hỗ trợ.
- Cân nhắc transaction snapshot phù hợp, hoặc chốt một mốc dữ liệu như `createdAt <= exportStartedAt`.
- Dùng điều kiện lọc cố định và sort key bất biến.
- Nếu cần, lưu danh sách ID của tập dữ liệu trước khi xử lý.
- Đánh giá thời lượng transaction và tác động tới connection pool, MVCC/version store và vacuum của database.

Không kéo dài transaction hàng giờ chỉ để giữ snapshot nếu database không được thiết kế cho workload đó. Có thể cần một quy trình export theo batch với mốc dữ liệu hoặc bảng staging.

## 13. Khi nào dùng Page, Slice, Window hoặc Stream?

| Kiểu | Mục đích | Tổng số kết quả | Cách tiếp tục |
|---|---|---:|---|
| `Page<T>` | UI cần tổng số trang và điều hướng theo trang | Có, thường cần count query | Pageable/page number |
| `Slice<T>` | UI chỉ cần biết còn trang tiếp theo | Không cần tổng count | Pageable |
| `Window<T>` | Duyệt tuần tự theo scroll position | Không | ScrollPosition |
| `Stream<T>` | Xử lý kết quả dạng stream nếu provider/driver hỗ trợ | Không | Stream/cursor tùy implementation |

`Page` tiện cho giao diện có số trang nhưng count query có thể tốn kém. `Slice` tránh total count nếu chỉ cần nút “xem thêm”. `Window` phù hợp với scrolling theo offset hoặc keyset. `Stream` có thể giữ tài nguyên database trong thời gian stream mở; cần đóng stream và quản lý transaction đúng cách.

Đừng coi WindowIterator là JDBC server cursor. Nó duyệt qua các window bằng nhiều lần truy vấn, mỗi lần có vị trí tiếp tục.

## 14. Giới hạn và điều kiện tương thích

Scroll API thuộc Spring Data Commons và được tích hợp trong các phiên bản Spring Data phù hợp. Trước khi sử dụng:

- Kiểm tra phiên bản Spring Data JPA mà Spring Boot BOM đang quản lý.
- Xác nhận repository method hỗ trợ kiểu trả về `Window<T>` và tham số `ScrollPosition`.
- Kiểm tra loại query. Khả năng scrolling với derived query, Specification, Querydsl và string-based `@Query` có thể khác nhau theo release; tài liệu của đúng phiên bản là nguồn quyết định.
- Với native query, kiểm tra rõ hỗ trợ của provider và Spring Data JPA; không giả định mọi native query đều hỗ trợ keyset.
- Kiểm tra database dialect và SQL được sinh trong môi trường test.

Nếu phiên bản dự án chưa hỗ trợ Scroll API, có thể dùng `Pageable`/`Slice` cho offset pagination hoặc tự viết keyset query với điều kiện seek, sort và giới hạn rõ ràng. Khi tự viết query, cần xử lý đúng tie-breaker và hướng sort.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trang sâu chậm dần | Offset lớn buộc database bỏ qua nhiều dòng | Dùng keyset nếu use case là duyệt tuần tự |
| Kết quả lặp hoặc thiếu khi có insert/delete | Offset thay đổi theo vị trí dòng | Dùng keyset và xác định semantics dữ liệu đồng thời |
| Keyset không tạo được cursor | Projection thiếu sort key hoặc keyset property null | Trả đầy đủ sort properties và bảo đảm không null |
| Bản ghi có cùng timestamp bị bỏ sót/không ổn định | Sort không có tie-breaker duy nhất | Thêm primary key vào cuối sort |
| Window sau không đúng vị trí | Dùng sai ScrollPosition hoặc thay sort giữa chừng | Giữ cùng predicate/sort và dùng position từ window trước |
| Không nhảy được tới trang bất kỳ | Keyset chỉ biết cursor hiện tại | Dùng offset/Pageable nếu random page navigation là yêu cầu |
| Tổng số trang không có | Window không thực hiện total count như Page | Dùng Page nếu cần tổng số; cân nhắc chi phí count |
| Dữ liệu export thay đổi giữa các window | Nhiều lần truy vấn không phải một snapshot | Chọn isolation hoặc mốc dữ liệu phù hợp |
| Query keyset không tận dụng index | Index không khớp filter và sort | Xem execution plan, thiết kế index theo predicate/sort |
| @Query không hỗ trợ scrolling trong version đang dùng | Giới hạn API của Spring Data JPA release | Dùng derived query method hoặc kiểm tra khả năng hỗ trợ đúng phiên bản |

## 16. Quy trình chọn chiến lược

1. Xác định người dùng cần nhảy đến trang số bất kỳ hay chỉ duyệt tiếp.
2. Nếu cần tổng số trang, cân nhắc `Page`; nếu chỉ cần biết còn dữ liệu, cân nhắc `Slice`.
3. Nếu duyệt tuần tự một tập lớn, đánh giá keyset scrolling.
4. Chọn sort ổn định, thêm khóa duy nhất làm tie-breaker.
5. Với keyset, bảo đảm sort keys không null và projection chứa đủ các key đó.
6. Thiết kế index theo filter prefix và sort keys; xác nhận bằng execution plan.
7. Quy định dữ liệu có thể thay đổi trong lúc scrolling như thế nào.
8. Kiểm tra hỗ trợ Scroll API của phiên bản Spring Data JPA và database dialect.
9. Đo hiệu năng với dữ liệu có quy mô gần production và kiểm tra kết quả không lặp/bỏ sót ngoài semantics đã chọn.

## Checklist trước khi merge

- [ ] Đã xác định rõ yêu cầu random page navigation hay sequential scrolling.
- [ ] Page/Slice/Window được chọn đúng nhu cầu total count và continuation.
- [ ] Repository method dùng Window và ScrollPosition tương thích phiên bản.
- [ ] Sort có thứ tự xác định và tie-breaker duy nhất.
- [ ] Keyset sort properties không null.
- [ ] Projection chứa đầy đủ sort/keyset properties.
- [ ] Index phù hợp với filter và sort đã được đánh giá.
- [ ] WindowIterator hoặc vòng lặp position xử lý hết window mà không tải toàn bộ dữ liệu.
- [ ] Hành vi khi insert/update/delete đồng thời đã được xác định.
- [ ] Integration test bao gồm nhiều window, giá trị sort trùng và dữ liệu rỗng.
- [ ] Execution plan và hiệu năng được kiểm tra trên database mục tiêu.

## Kết luận

Offset scrolling xác định vị trí bằng số dòng cần bỏ qua; cách này đơn giản và hỗ trợ nhảy tới trang nhưng có thể chậm ở offset sâu và nhạy với insert/delete. Keyset scrolling tiếp tục sau các giá trị sort của dòng cuối, thường hiệu quả hơn khi duyệt dữ liệu lớn nếu có index phù hợp. Đổi lại, keyset cần sort ổn định, khóa duy nhất, thuộc tính sort không null và projection chứa đủ keyset fields; nó cũng không tự tạo snapshot nhất quán. Trong Spring Data, dùng `Window<T>`, `ScrollPosition` và `WindowIterator`, rồi chọn offset hay keyset theo cách người dùng điều hướng và yêu cầu nhất quán dữ liệu.
