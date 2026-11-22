# Xử lý thay đổi dữ liệu trong lúc người dùng duyệt nhiều trang

Phân trang thường được triển khai bằng cách chia tập kết quả thành các trang có kích thước cố định. Tuy nhiên, dữ liệu trong database có thể thay đổi trong lúc người dùng đang đọc trang 1, chuyển sang trang 2 rồi tiếp tục sang trang 3. Một người dùng khác có thể thêm bản ghi mới, xóa bản ghi đang hiển thị hoặc cập nhật trường dùng để sắp xếp. Khi đó, tập kết quả của truy vấn sau không còn giống tập kết quả của truy vấn trước.

Nếu ứng dụng chỉ dùng `LIMIT` và `OFFSET`, các thay đổi này có thể làm một bản ghi xuất hiện hai lần, bị bỏ qua hoặc làm số lượng trang thay đổi giữa chừng. Đây không nhất thiết là lỗi của R2DBC; đó là hệ quả của việc chạy nhiều truy vấn độc lập trên một tập dữ liệu đang biến động.

Trong Spring Data Relational R2DBC, cần chọn chiến lược phân trang và hợp đồng nhất quán dữ liệu phù hợp với nghiệp vụ. Các lựa chọn thường gồm offset pagination, keyset/cursor pagination, giới hạn theo mốc dữ liệu, snapshot hoặc phiên bản dữ liệu. Phần giao diện cũng cần quyết định cách phản ứng khi trang hiện tại đã thay đổi.

Bài học này giải thích các bất thường khi duyệt nhiều trang, cách giảm trùng và bỏ sót bằng thứ tự ổn định, cách triển khai truy vấn bằng SQL/`DatabaseClient`, giới hạn của transaction kéo dài qua nhiều request và cách thiết kế trải nghiệm người dùng khi dữ liệu mới xuất hiện.

## 1. Vì sao dữ liệu thay đổi làm phân trang mất ổn định?

Giả sử danh sách đơn hàng được sắp xếp mới nhất trước, mỗi trang có 10 hàng:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
ORDER BY created_at DESC, id DESC
LIMIT 10 OFFSET 0;
~~~

Người dùng mở trang đầu và nhận các đơn hàng có thứ tự 100 đến 91. Trước khi họ mở trang tiếp theo, một đơn hàng mới được thêm vào đầu danh sách. Khi truy vấn trang 2 với `OFFSET 10`, vị trí của mọi hàng phía sau bị dịch chuyển một bước. Hàng 91 có thể xuất hiện lại ở trang 2 dù đã có trong trang 1.

Tương tự, nếu một hàng ở trang trước bị xóa, các hàng phía sau dịch lên một vị trí. Truy vấn trang sau vẫn bỏ qua số hàng cũ bằng `OFFSET`, nên một hàng có thể bị bỏ qua.

Có ba nhóm thay đổi chính:

- **Insert:** bản ghi mới được thêm trước hoặc trong vùng đang phân trang.
- **Delete:** bản ghi bị xóa làm các hàng phía sau dịch chuyển vị trí.
- **Update:** bản ghi thay đổi trường lọc hoặc trường sắp xếp, khiến nó đi vào hoặc rời khỏi tập kết quả, hoặc chuyển vị trí trong thứ tự.

Các bất thường thường gặp:

| Thay đổi giữa hai request | Hệ quả có thể xảy ra với OFFSET |
|---|---|
| Thêm hàng trước vị trí trang kế tiếp | Hàng cũ có thể lặp lại ở trang sau |
| Xóa hàng ở trang trước | Hàng chưa đọc có thể bị bỏ qua |
| Cập nhật giá trị sort key | Hàng có thể di chuyển qua ranh giới trang |
| Cập nhật trường lọc | Hàng có thể xuất hiện hoặc biến mất khỏi tập kết quả |
| Nhiều thay đổi đồng thời | Số trang, tổng số hàng và nội dung từng trang không còn đồng bộ |

Vấn đề cốt lõi là mỗi request phân trang thường chạy một truy vấn mới trên trạng thái database tại thời điểm truy vấn đó.

## 2. OFFSET pagination và ví dụ trùng hoặc bỏ sót

Offset pagination chọn một đoạn trong thứ tự kết quả:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

Với `pageSize = 10`:

- Trang 0 có `offset = 0`.
- Trang 1 có `offset = 10`.
- Trang 2 có `offset = 20`.

### 2.1. Insert gây lặp bản ghi

Trạng thái ban đầu:

~~~text
Thứ tự trước khi có insert:
[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, ...]

Trang 1 (OFFSET 0):
[100, 99, 98, 97, 96, 95, 94, 93, 92, 91]
~~~

Một đơn hàng mới `101` được thêm vào đầu danh sách:

~~~text
Thứ tự sau insert:
[101, 100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, ...]

Trang 2 (OFFSET 10):
[91, 90, 89, 88, 87, 86, 85, 84, 83, 82]
~~~

`91` xuất hiện ở cả hai trang. Người dùng nhìn thấy một đơn hàng lặp lại dù mỗi truy vấn đều chạy đúng theo `LIMIT/OFFSET`.

### 2.2. Delete gây bỏ sót

Trang 1 đã trả về các hàng `100` đến `91`. Sau đó hàng `100` bị xóa:

~~~text
Thứ tự sau delete:
[99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, ...]

Trang 2 (OFFSET 10):
[89, 88, 87, 86, 85, 84, 83, 82, 81, 80]
~~~

Hàng `90` không nằm trong trang 1 nhưng đã bị đẩy từ vị trí 10 xuống vị trí 9 sau khi xóa. Truy vấn trang 2 bắt đầu từ vị trí 10 nên bỏ qua `90`.

Đây là lý do offset pagination có thể phù hợp với danh sách ít thay đổi hoặc nơi chấp nhận sai lệch nhỏ, nhưng không tạo ra một hành trình duyệt nhất quán khi dữ liệu biến động liên tục.

## 3. Luôn dùng thứ tự ổn định và có tính duy nhất

Một truy vấn phân trang phải có `ORDER BY`. Nếu không có thứ tự, database không bảo đảm các request trả hàng theo cùng một thứ tự.

Ngay cả khi có `ORDER BY created_at DESC`, nhiều hàng có thể có cùng timestamp. Khi đó thứ tự giữa các hàng bằng timestamp vẫn chưa xác định. Thêm một khóa duy nhất làm tiêu chí phụ:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Trong đó:

- `created_at` quyết định thứ tự nghiệp vụ.
- `id` phá hòa khi nhiều hàng có cùng timestamp.

Một thứ tự ổn định cần thỏa:

1. Mọi hàng trong tập kết quả đều có vị trí xác định.
2. Nếu trường sắp xếp chính có thể trùng, có tiêu chí phụ.
3. Tiêu chí cuối cùng nên là khóa duy nhất.
4. Hướng sắp xếp được giữ nguyên giữa các trang.
5. Giá trị sort key nên ít thay đổi trong lúc duyệt.

Thứ tự ổn định không tự ngăn insert hoặc delete làm thay đổi offset. Nó chỉ loại bỏ sự không xác định do thứ tự bằng nhau hoặc thiếu `ORDER BY`, và là điều kiện cần để keyset pagination hoạt động đúng.

Không nên dùng `ORDER BY` theo trường có thể thay đổi liên tục nếu nghiệp vụ không cần thứ tự đó. Nếu cần danh sách theo thời gian tạo, `created_at` thường phù hợp hơn trường như `status`, `priority` hoặc `last_modified_at`, vốn có thể thay đổi khi người dùng đang duyệt.

## 4. Keyset pagination là gì?

Keyset pagination (còn gọi là seek pagination) dùng giá trị của hàng cuối cùng ở trang hiện tại làm mốc để truy vấn trang tiếp theo. Thay vì yêu cầu database bỏ qua N hàng đầu tiên, truy vấn yêu cầu lấy các hàng đứng sau mốc đã đọc theo thứ tự sắp xếp.

Với thứ tự giảm dần theo `created_at` và `id`:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Trang đầu không có cursor:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Ứng dụng lưu cặp giá trị của hàng cuối cùng, ví dụ `lastCreatedAt` và `lastId`. Khi người dùng yêu cầu trang kế tiếp, ứng dụng truyền hai giá trị đó vào truy vấn.

### 4.1. Minh họa luồng cursor

~~~text
Truy vấn đầu tiên
       |
       v
[100, 99, 98, 97, 96]
       |
       v
Cursor = khóa sắp xếp của hàng 96
       |
       v
Truy vấn tiếp theo:
lấy hàng đứng sau cursor 96
       |
       v
[95, 94, 93, 92, 91]
       |
       v
Cursor mới = khóa sắp xếp của hàng 91
~~~

Nếu một hàng mới `101` được thêm vào đầu danh sách sau trang đầu, truy vấn tiếp theo vẫn tìm các hàng nhỏ hơn cursor `96`. Hàng mới nằm trước cursor nên không đẩy các hàng chưa đọc sang vị trí khác như OFFSET.

### 4.2. Cursor phải chứa đủ sort key

Nếu thứ tự là:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

cursor cần giữ cả `created_at` và `id`. Chỉ giữ timestamp là chưa đủ vì nhiều hàng có thể có cùng timestamp; truy vấn tiếp theo có thể lặp hoặc bỏ sót những hàng cùng thời điểm.

Với thứ tự nhiều cột, cursor cần mang mọi giá trị cần thiết để xác định vị trí cuối cùng. Nếu có cột nullable hoặc hướng sort hỗn hợp, điều kiện so sánh phải phản ánh chính xác semantics của database.

### 4.3. Keyset không tự tạo snapshot

Keyset pagination tránh việc insert ở phía trước cursor làm dịch vị trí các hàng chưa đọc. Nhưng nó không đóng băng toàn bộ tập dữ liệu.

Nếu một hàng chưa đọc được cập nhật sort key để chuyển lên trước cursor, hàng đó có thể không xuất hiện trong các trang tiếp theo. Nếu một hàng đã đọc bị cập nhật sort key để chuyển xuống sau cursor, nó có thể xuất hiện lại. Nếu trường lọc thay đổi, hàng có thể gia nhập hoặc rời tập kết quả.

Vì vậy, keyset pagination đặc biệt hiệu quả khi thứ tự dựa trên các cột bất biến hoặc gần như bất biến, chẳng hạn khóa tăng đơn điệu hoặc thời điểm tạo không bị sửa.

## 5. Cách triển khai keyset trong Spring Data R2DBC

Có thể khai báo truy vấn bằng `@Query` hoặc dùng `DatabaseClient`. Ví dụ repository method cho trang đầu và trang tiếp theo:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT id, order_number, created_at, status
        FROM purchase_order
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """)
    Flux<Order> findFirstSlice(
            OrderStatus status,
            int limit);

    @Query("""
        SELECT id, order_number, created_at, status
        FROM purchase_order
        WHERE status = :status
          AND (
              created_at < :lastCreatedAt
              OR (created_at = :lastCreatedAt AND id < :lastId)
          )
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """)
    Flux<Order> findNextSlice(
            OrderStatus status,
            LocalDateTime lastCreatedAt,
            Long lastId,
            int limit);
}
~~~

Đây là mẫu minh họa; cú pháp bind tên tham số và hỗ trợ giới hạn phụ thuộc phiên bản Spring Data, driver và dialect. Nếu method parameter không được bind theo tên trong cấu hình dự án, dùng `@Param` để chỉ rõ tên.

Service có thể lấy thêm một hàng để xác định còn trang tiếp theo hay không:

~~~java
Mono<OrderSlice> nextOrders(
        OrderStatus status,
        OrderCursor cursor,
        int pageSize) {

    Flux<Order> query = cursor == null
            ? orderRepository.findFirstSlice(status, pageSize + 1)
            : orderRepository.findNextSlice(
                    status,
                    cursor.createdAt(),
                    cursor.id(),
                    pageSize + 1);

    return query.collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > pageSize;

                List<Order> content = hasNext
                        ? rows.subList(0, pageSize)
                        : rows;

                OrderCursor nextCursor = content.isEmpty()
                        ? null
                        : OrderCursor.from(
                                content.get(content.size() - 1));

                return new OrderSlice(content, nextCursor, hasNext);
            });
}
~~~

Các kiểu `OrderSlice` và `OrderCursor` là DTO do ứng dụng định nghĩa. Ví dụ record:

~~~java
public record OrderCursor(
        LocalDateTime createdAt,
        Long id) {
}

public record OrderSlice(
        List<Order> content,
        OrderCursor nextCursor,
        boolean hasNext) {
}
~~~

Cách `pageSize + 1` giúp biết có hàng tiếp theo mà không cần chạy `COUNT(*)` cho mỗi request. Nếu có thêm một hàng, trả về đúng `pageSize` hàng và đặt `hasNext = true`.

Với tập kết quả rất lớn, có thể tránh `collectList()` bằng cách xử lý publisher theo cách phù hợp với API và chỉ giữ tối đa `pageSize + 1` phần tử. Dù dùng cách nào, truy vấn database vẫn nên giới hạn số hàng ngay từ SQL.

## 6. Cursor cần gắn với bộ lọc và thứ tự truy vấn

Cursor chỉ có ý nghĩa trong ngữ cảnh truy vấn đã tạo ra nó. Nếu trang đầu được đọc với:

- `status = OPEN`
- `created_at DESC, id DESC`
- một phạm vi tenant cụ thể

thì trang tiếp theo phải dùng cùng bộ lọc, cùng tenant và cùng thứ tự.

Nếu client gửi cursor cũ nhưng thay filter hoặc sort, cursor có thể trỏ tới vị trí không hợp lệ trong tập kết quả mới. Có thể lưu các thông tin sau trong cursor:

- Các giá trị sort key của hàng cuối.
- Phiên bản hoặc định danh bộ lọc.
- Mã tenant/phạm vi dữ liệu nếu cần.
- Phiên bản định dạng cursor để hỗ trợ thay đổi API.

Một cursor có thể được mã hóa thành chuỗi opaque để client không phải tự tạo các giá trị sort. Nếu cursor được client gửi lại, cần kiểm tra định dạng, kiểu dữ liệu và quyền truy cập. Nếu cursor chứa thông tin nhạy cảm hoặc ảnh hưởng tới quyền truy cập, hãy ký hoặc mã hóa theo yêu cầu bảo mật; không tin filter/tenant chỉ vì chúng được nhúng trong cursor.

Không dùng cursor làm cơ chế phân quyền. Mỗi request vẫn phải kiểm tra người dùng có quyền đọc tập dữ liệu tương ứng.

## 7. Xử lý cập nhật sort key trong lúc duyệt

Keyset hoạt động tốt nhất khi các cột sắp xếp không đổi sau khi bản ghi được tạo. Nhưng không phải nghiệp vụ nào cũng có thể dùng trường bất biến.

Ví dụ danh sách công việc được sắp xếp theo `priority DESC, id DESC`. Người dùng khác có thể tăng priority của một công việc chưa đọc. Công việc đó chuyển lên phía trước cursor. Khi truy vấn trang kế tiếp, nó có thể không còn được trả về.

Có ba hướng xử lý:

1. **Chọn sort key ít thay đổi:** dùng `created_at`, sequence hoặc khóa định danh ổn định nếu phù hợp nghiệp vụ.
2. **Chấp nhận danh sách cập nhật liên tục:** cho phép item di chuyển; UI cần xử lý refresh và thông báo thay đổi.
3. **Yêu cầu snapshot nhất quán:** cố định tập dữ liệu theo mốc thời gian, version hoặc snapshot database nếu nghiệp vụ yêu cầu người dùng duyệt cùng một tập.

Không thể đồng thời bảo đảm mọi thay đổi mới xuất hiện ngay, giữ vị trí trang bất biến và không lặp/bỏ sót trong mọi trường hợp nếu không xác định một semantics nhất quán. Hãy chọn hành vi sản phẩm rõ ràng.

## 8. Dùng mốc dữ liệu (high-water mark) để giới hạn tập kết quả

Một cách giảm ảnh hưởng của insert mới là chụp một mốc ở lần truy vấn đầu và chỉ đọc các bản ghi không vượt qua mốc đó.

Ví dụ, nếu `id` là khóa tăng đơn điệu và phù hợp với semantics tạo dữ liệu, truy vấn đầu lấy giá trị ID lớn nhất:

~~~sql
SELECT MAX(id)
FROM purchase_order
WHERE status = :status;
~~~

Giả sử mốc là `1000`. Mọi trang sau thêm điều kiện:

~~~sql
WHERE status = :status
  AND id <= :maxId
  AND id < :lastId
ORDER BY id DESC
LIMIT :pageSize;
~~~

Các hàng mới có ID lớn hơn mốc sẽ không chen vào tập đang duyệt. Cursor tiếp tục là ID cuối của trang trước.

Mốc này có các giới hạn:

- Chỉ phù hợp khi ID có thứ tự tăng và không được tái sử dụng.
- ID được cấp trước khi transaction commit có thể tạo khoảng trống hoặc thứ tự commit khác thứ tự cấp ID.
- Một bản ghi mới được tạo với ID cũ hoặc dữ liệu được backfill có thể lọt vào phạm vi mốc.
- Mốc ID không cố định nội dung của hàng nếu các property khác vẫn được cập nhật.
- Bộ lọc có thể thay đổi kết quả nếu trường lọc được cập nhật.

Có thể dùng `created_at <= :asOf` thay cho ID khi timestamp được gán ở server và không bị sửa. Tuy nhiên, transaction tạo trước mốc nhưng commit sau mốc hoặc dữ liệu backfill vẫn có thể làm semantics phức tạp. High-water mark là giới hạn tập dữ liệu theo quy tắc đã chọn, không mặc nhiên là snapshot database hoàn chỉnh.

## 9. Snapshot nhất quán và transaction

Nếu nghiệp vụ yêu cầu mọi trang phản ánh cùng một trạng thái dữ liệu, cần một khái niệm snapshot.

Một số database hỗ trợ transaction isolation như `REPEATABLE READ` hoặc snapshot isolation. Trong cùng một transaction, nhiều câu SELECT có thể đọc cùng một snapshot tùy hệ quản trị và isolation level.

Ví dụ, transaction có thể thực hiện:

1. Đọc trang đầu.
2. Đọc trang kế tiếp.
3. Đọc các trang còn lại.
4. Commit khi hoàn tất.

Nhưng duyệt trang trong ứng dụng web thường kéo dài qua nhiều HTTP request và người dùng có thể dừng vài phút giữa hai lần bấm. Giữ một transaction mở trong toàn bộ khoảng thời gian đó thường không phù hợp:

- Connection bị chiếm dụng lâu.
- Snapshot cũ giữ lại phiên bản dữ liệu hoặc làm tăng áp lực vacuum/undo tùy database.
- Transaction có thể timeout hoặc bị ngắt.
- Tăng nguy cơ lock và ảnh hưởng các request khác.
- Khó phục hồi khi người dùng đóng tab hoặc mất mạng.

Vì vậy, không nên giữ một reactive transaction mở chỉ để người dùng có thể chuyển qua nhiều trang tùy ý. Transaction reactive trong R2DBC phù hợp để bao bọc một use case ngắn, chẳng hạn đọc/ghi nhiều bảng trong một request, chứ không phải phiên duyệt kéo dài.

Nếu cần snapshot thực sự qua nhiều request, cần cơ chế chuyên biệt mà database hoặc ứng dụng hỗ trợ, ví dụ snapshot token có thời hạn, bảng staging chứa danh sách ID, versioned data hoặc một bản export bất biến. Đây là quyết định kiến trúc có chi phí lưu trữ và vận hành.

## 10. Đếm tổng số hàng khi dữ liệu thay đổi

Offset pagination thường hiển thị tổng số trang bằng cách chạy thêm:

~~~sql
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status;
~~~

Sau đó truy vấn trang:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

Nếu có insert hoặc delete giữa hai truy vấn, `totalElements` và nội dung trang có thể phản ánh hai trạng thái khác nhau. Ngay cả khi chạy gần nhau, hai câu SQL độc lập dưới mức isolation mặc định có thể nhìn thấy snapshot khác nhau.

Vì vậy:

- Tổng số hàng nên được coi là thông tin tại thời điểm truy vấn, trừ khi có snapshot nhất quán.
- Không giả định `totalPages` vẫn đúng sau khi người dùng chờ rồi chuyển trang.
- Nếu UI không cần tổng số trang, dùng `hasNext` sẽ đơn giản và ít tốn kém hơn.
- Nếu cần tổng số chính xác theo cùng snapshot, phải thiết kế transaction/snapshot phù hợp và cân nhắc chi phí.

Với keyset pagination, `hasNext` có thể được xác định bằng cách lấy `pageSize + 1` hàng. Cách này không cần đếm toàn bộ tập kết quả.

## 11. Xử lý thay đổi ở giao diện người dùng

Backend có thể chọn cursor hoặc snapshot, nhưng UI vẫn cần một chính sách rõ ràng khi danh sách thay đổi.

### 11.1. Có bản ghi mới

Nếu người dùng đang ở trang 3 và có bản ghi mới xuất hiện ở đầu danh sách:

- Không nhất thiết chèn bản ghi đó vào đầu trang hiện tại vì có thể làm dịch vị trí mọi hàng.
- Có thể hiển thị thông báo "Có dữ liệu mới" hoặc nút "Tải lại".
- Khi người dùng chọn tải lại, đưa họ về trang đầu hoặc tạo cursor mới.
- Nếu nghiệp vụ cần cập nhật realtime, dùng cơ chế live update riêng và xử lý ID trùng.

### 11.2. Bản ghi hiện tại bị xóa

Nếu một hàng trong trang hiện tại bị xóa:

- Có thể hiển thị trang với ít hơn số hàng chuẩn.
- Có thể tải bù một hàng từ trang kế tiếp nếu UX muốn luôn đủ số lượng.
- Nếu trang hiện tại trở thành rỗng do xóa, có thể quay về trang trước hoặc hiển thị trạng thái rỗng kèm nút quay lại.
- Với offset pagination, tải bù phải tính lại offset và có nguy cơ nhìn thấy dữ liệu khác; cần tránh vòng lặp truy vấn không giới hạn.

### 11.3. Bản ghi đổi trạng thái hoặc không còn khớp bộ lọc

Ví dụ người dùng đang xem đơn hàng `OPEN`, trong lúc đó đơn hàng chuyển sang `CLOSED`. Khi tải trang tiếp theo, bản ghi đó không còn thuộc tập kết quả.

Đây là thay đổi hợp lệ của filter. UI có thể cập nhật hàng đó ngay nếu nhận được event, hoặc chỉ phản ánh thay đổi khi người dùng refresh. API nên trả dữ liệu theo filter hiện tại và không giả định danh sách trước đó vẫn đầy đủ.

### 11.4. Khử trùng lặp ở client

Khi dùng offset trên dữ liệu biến động, UI có thể nhận một ID đã có ở trang trước. Client có thể khử trùng lặp theo ID để tránh hiển thị hai dòng giống nhau:

~~~javascript
const byId = new Map(existingItems.map(item => [item.id, item]));

for (const item of incomingPage) {
  byId.set(item.id, item);
}

const mergedItems = [...byId.values()];
~~~

Khử trùng lặp chỉ xử lý biểu hiện lặp. Nó không khôi phục bản ghi đã bị bỏ sót do offset dịch chuyển. Nếu người dùng cần duyệt đầy đủ hoặc xuất dữ liệu chính xác, cần keyset/snapshot thay vì dựa vào deduplication.

## 12. Thiết kế API cho offset và cursor

Offset API thường có dạng:

~~~http
GET /orders?status=OPEN&page=2&size=20&sort=createdAt,desc
~~~

Response có thể chứa:

~~~json
{
  "content": [],
  "page": 2,
  "size": 20,
  "totalElements": 145,
  "totalPages": 8
}
~~~

Các số liệu tổng có thể thay đổi khi dữ liệu được thêm hoặc xóa. Client nên coi chúng là snapshot tại thời điểm response được tạo.

Cursor API thường có dạng:

~~~http
GET /orders?status=OPEN&limit=20
GET /orders?status=OPEN&limit=20&after=eyJjcmVhdGVkQXQiOi...
~~~

Response:

~~~json
{
  "content": [],
  "nextCursor": "eyJjcmVhdGVkQXQiOi...",
  "hasNext": true
}
~~~

Cursor nên là opaque token do server tạo. Client chỉ gửi lại token ở request tiếp theo, không tự sửa giá trị sort key bên trong.

Nếu filter hoặc sort thay đổi, server nên từ chối cursor không tương thích hoặc yêu cầu bắt đầu một chuỗi phân trang mới. Có thể dùng version trong cursor để xử lý thay đổi format theo thời gian.

## 13. Xây dựng truy vấn an toàn với DatabaseClient

`DatabaseClient` cho phép bind các giá trị như filter, cursor và limit:

~~~java
Flux<Order> findAfter(
        OrderStatus status,
        LocalDateTime lastCreatedAt,
        Long lastId,
        int pageSize) {

    return databaseClient.sql("""
            SELECT id, order_number, created_at, status
            FROM purchase_order
            WHERE status = :status
              AND (
                  created_at < :lastCreatedAt
                  OR (
                      created_at = :lastCreatedAt
                      AND id < :lastId
                  )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
            .bind("status", status.name())
            .bind("lastCreatedAt", lastCreatedAt)
            .bind("lastId", lastId)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> new Order(
                    row.get("id", Long.class),
                    row.get("order_number", String.class),
                    row.get("created_at", LocalDateTime.class),
                    row.get("status", String.class)))
            .all();
}
~~~

Mẫu trên giả định `created_at` không null và kiểu Java tương thích với driver. Nếu cột nullable, cần quy định rõ vị trí của null trong sort và viết điều kiện cursor tương ứng. Nếu dialect không hỗ trợ bind limit theo cách này, dùng cơ chế giới hạn phù hợp mà driver/database hỗ trợ.

Không thể bind tên cột hoặc từ khóa `ASC`/`DESC` như một giá trị parameter. Nếu client được chọn sort, hãy ánh xạ lựa chọn sang danh sách cột/hướng sort được cho phép ở server. Không nối trực tiếp chuỗi sort do người dùng gửi vào SQL.

## 14. Index và hiệu năng của truy vấn phân trang

Offset lớn có thể tốn kém vì database phải tìm và bỏ qua nhiều hàng trước khi trả về phần cần lấy. Ví dụ `OFFSET 100000` có thể phải duyệt qua một vùng kết quả lớn.

Keyset thường có thể tận dụng index trên bộ lọc và sort key. Với truy vấn:

~~~sql
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Một index có thể cân nhắc:

~~~sql
CREATE INDEX ix_order_status_created_id
ON purchase_order(status, created_at DESC, id DESC);
~~~

Index thực tế phụ thuộc database, selectivity, điều kiện filter, hướng sort và workload. Không tạo index chỉ vì có `ORDER BY`; hãy kiểm tra execution plan và đo hiệu năng trên dữ liệu gần với production.

Nếu filter thay đổi thường xuyên, một index duy nhất có thể không phục vụ mọi tổ hợp. Cân nhắc các truy vấn quan trọng nhất và tránh tạo quá nhiều index làm chậm insert/update.

## 15. Chọn chiến lược theo yêu cầu nghiệp vụ

| Nhu cầu | Chiến lược phù hợp | Đánh đổi |
|---|---|---|
| Danh sách nhỏ, ít thay đổi | Offset pagination | Dễ dùng, tổng trang rõ; vẫn có thể lệch khi dữ liệu thay đổi |
| Trang có thể nhảy tới số bất kỳ | Offset pagination | Offset lớn có thể chậm và nội dung có thể dịch chuyển |
| Dữ liệu lớn, liên tục có insert | Keyset/cursor | Tiến về trước ổn định hơn; khó nhảy tới trang số bất kỳ |
| Thứ tự dựa trên cột bất biến | Keyset/cursor | Giảm lặp/bỏ sót do insert trước cursor |
| Sort key thay đổi liên tục | Snapshot hoặc chấp nhận refresh | Keyset vẫn có thể bị ảnh hưởng bởi hàng di chuyển |
| Báo cáo/export cần tập dữ liệu cố định | Snapshot, version hoặc staging | Tốn thêm tài nguyên và cần quản lý vòng đời snapshot |
| UI cần biết còn dữ liệu hay không | `pageSize + 1` và `hasNext` | Không cung cấp tổng số trang chính xác |
| UI bắt buộc hiển thị tổng số trang | Count query | Tổng có thể thay đổi giữa các request |

Không có một chiến lược duy nhất phù hợp mọi màn hình. Hãy xác định người dùng cần nhảy tới trang bất kỳ, duyệt liên tục hay xuất một tập dữ liệu cố định.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Phân trang bằng OFFSET nhưng không có ORDER BY | Kết quả giữa các request không ổn định | Thêm thứ tự xác định |
| ORDER BY chỉ theo timestamp có thể trùng | Hàng bằng timestamp có thể đổi vị trí tương đối | Thêm khóa duy nhất làm tie-breaker |
| Nghĩ ORDER BY loại bỏ mọi sai lệch khi insert/delete | Offset vẫn dịch khi số hàng phía trước thay đổi | Dùng keyset hoặc snapshot theo nhu cầu |
| Cursor chỉ chứa một phần sort key | Có thể lặp hoặc bỏ sót hàng có sort key trùng | Lưu toàn bộ sort key, gồm unique tie-breaker |
| Dùng keyset với sort key thường xuyên thay đổi | Hàng có thể di chuyển qua cursor | Chọn key bất biến hoặc xác định semantics cập nhật |
| Đếm tổng và lấy trang rồi giả định cùng trạng thái | totalElements có thể không khớp nội dung trang | Coi count là thông tin tại thời điểm truy vấn hoặc dùng snapshot |
| Giữ transaction mở trong lúc người dùng duyệt nhiều phút | Chiếm connection và giữ snapshot lâu | Mỗi request dùng transaction ngắn; dùng snapshot chuyên biệt nếu bắt buộc |
| Dùng created_at <= asOf rồi coi là snapshot tuyệt đối | Backfill hoặc transaction commit trễ vẫn có thể lọt vào | Xác định giới hạn của watermark hoặc dùng version/snapshot thật |
| Khử trùng lặp ở UI rồi cho rằng đã đủ dữ liệu | Bản ghi bị bỏ sót vẫn không được khôi phục | Chọn pagination phù hợp; dedupe chỉ là biện pháp hiển thị |
| Chèn item mới vào đầu trang hiện tại | Các hàng đang hiển thị bị dịch và cursor/offset khó đồng bộ | Thông báo có dữ liệu mới và refresh có chủ đích |
| Nối sort string trực tiếp vào SQL | Có nguy cơ SQL injection và truy vấn không hợp lệ | Whitelist cột và hướng sort |
| Dùng OFFSET rất lớn cho bảng lớn | Truy vấn tốn thời gian | Cân nhắc keyset và index phù hợp |

## 17. Quy trình thiết kế trải nghiệm phân trang nhất quán

Khi xây dựng màn hình có thể được nhiều người cùng cập nhật dữ liệu, hãy quyết định:

1. Người dùng cần nhảy đến trang số bất kỳ hay chỉ đi tiếp/lùi?
2. Dữ liệu có được thêm, xóa hoặc đổi sort key thường xuyên không?
3. Thứ tự có tiêu chí phụ duy nhất và ổn định không?
4. Sort key có thể bị sửa sau khi tạo không?
5. Người dùng cần thấy dữ liệu mới ngay hay cần duyệt cùng một tập dữ liệu?
6. Tổng số trang chính xác có bắt buộc không, hay `hasNext` là đủ?
7. Khi có thay đổi, UI sẽ tự refresh, hiển thị thông báo hay chấp nhận danh sách cập nhật?
8. Cursor có ràng buộc với filter, sort và tenant hiện tại không?
9. Query có index phù hợp và giới hạn số hàng ngay trong database không?
10. Integration test đã mô phỏng insert, delete và update giữa hai lần lấy trang chưa?

Một kịch bản kiểm thử hữu ích:

- Lấy trang đầu với page size nhỏ.
- Thêm một hàng mới có sort key đứng trước trang đầu.
- Lấy trang tiếp theo và xác nhận keyset không trả lại hàng cuối của trang trước.
- Xóa một hàng đã đọc và kiểm tra hành vi trang tiếp theo.
- Thay đổi sort key của một hàng chưa đọc để xác nhận semantics đã chọn.
- Thay filter hoặc sort nhưng gửi cursor cũ và xác nhận server xử lý đúng.
- Kiểm tra trường hợp trang cuối không còn hàng và `hasNext = false`.

## 18. Ghi nhớ

- Dữ liệu thay đổi giữa các request có thể làm offset pagination lặp hoặc bỏ sót bản ghi.
- Luôn có `ORDER BY` xác định và thêm khóa duy nhất làm tie-breaker.
- Keyset/cursor pagination dùng sort key của hàng cuối để truy vấn phần tiếp theo, tránh dịch chuyển do insert trước cursor.
- Cursor phải chứa đầy đủ sort key và gắn với filter, sort, phạm vi truy cập tương ứng.
- Keyset không phải snapshot; update sort key hoặc filter vẫn có thể làm hàng di chuyển vào/ra vùng duyệt.
- High-water mark có thể giới hạn bản ghi mới theo một quy tắc cụ thể, nhưng không tự bảo đảm snapshot tuyệt đối.
- Không giữ transaction reactive mở trong suốt thời gian người dùng duyệt nhiều trang.
- Count query và page query có thể nhìn thấy trạng thái dữ liệu khác nhau; coi tổng số là thông tin tại thời điểm truy vấn nếu không có snapshot.
- UI nên có chính sách rõ ràng cho bản ghi mới, bị xóa hoặc đổi trạng thái; deduplication không khôi phục được hàng bị bỏ sót.
- Dùng `pageSize + 1` để xác định `hasNext` khi không cần tổng số hàng.
- Bind giá trị filter/cursor; whitelist tên cột và hướng sort vì identifier không thể bind như value parameter.
- Kiểm thử hành vi khi insert, delete và update xảy ra giữa các lần tải trang trên database mục tiêu.

