# Duyệt nhiều cửa sổ và quản lý vị trí tiếp tục trong Spring Data JPA

## 1. Scrolling là gì và giải quyết vấn đề nào?

Khi truy vấn một bảng có hàng trăm nghìn hoặc hàng triệu bản ghi, tải toàn bộ kết quả thành một `List<T>` có thể tiêu tốn nhiều bộ nhớ và thời gian. Phân trang bằng `Page<T>` giúp chia kết quả thành từng trang, nhưng thường cần thêm truy vấn đếm tổng số bản ghi. Khi chỉ cần xử lý lần lượt dữ liệu lớn, việc tính tổng có thể không cần thiết.

Spring Data cung cấp **Scroll API** để đọc dữ liệu theo từng nhóm nhỏ, gọi là `Window<T>`. Mỗi window chứa một phần kết quả và cung cấp `ScrollPosition` để tiếp tục truy vấn từ vị trí cuối cùng. Ứng dụng có thể xử lý một window, lấy vị trí tiếp theo rồi yêu cầu window kế tiếp cho tới khi hết dữ liệu.

Scrolling hữu ích cho:

- Xuất dữ liệu lớn thành tệp theo từng nhóm.
- Đồng bộ dữ liệu giữa hai hệ thống.
- Chạy tác vụ nền trên nhiều bản ghi.
- Tính toán hoặc lập báo cáo theo lô.
- Duyệt dữ liệu theo thứ tự ổn định mà không cần tải toàn bộ vào bộ nhớ.
- Lưu checkpoint để tiếp tục xử lý sau khi tiến trình bị gián đoạn.

Scroll API có hai kiểu định vị chính:

1. **Offset-based scrolling:** tiếp tục bằng số lượng bản ghi đã bỏ qua.
2. **Keyset-based scrolling:** tiếp tục bằng giá trị các khóa sắp xếp của bản ghi cuối cùng trong window.

Hai cách có đặc tính hiệu năng và khả năng chịu thay đổi dữ liệu khác nhau. Cần chọn theo kích thước dữ liệu, cách sắp xếp và yêu cầu tiếp tục công việc.

## 2. Các kiểu trả về: List, Page, Slice, Window và Stream

Spring Data JPA hỗ trợ nhiều cách lấy dữ liệu. Chúng không thay thế hoàn toàn cho nhau:

| Kiểu trả về | Cách hoạt động | Có tổng số bản ghi? | Phù hợp |
|---|---|---|---|
| `List<T>` | Lấy toàn bộ kết quả phù hợp | Không | Tập dữ liệu nhỏ |
| `Page<T>` | Lấy một trang và thường chạy thêm count query | Có | Giao diện cần tổng số trang/bản ghi |
| `Slice<T>` | Lấy một phần và cho biết còn trang tiếp theo không | Không | Giao diện chỉ cần nút tiếp theo |
| `Window<T>` | Lấy một cửa sổ, dùng `ScrollPosition` để tiếp tục | Không | Duyệt dữ liệu lớn theo từng nhóm |
| `Stream<T>` | Xử lý kết quả qua Java Stream gắn với tài nguyên truy vấn | Không | Một lượt xử lý liên tục trong transaction |

`Page<T>` phù hợp khi người dùng cần biết tổng số trang. `Slice<T>` giảm chi phí đếm tổng. `Window<T>` cung cấp vị trí tiếp tục rõ ràng và hỗ trợ offset hoặc keyset. `Stream<T>` là một tài nguyên có thể gắn với JDBC ResultSet; phải quản lý vòng đời và đóng luồng đúng cách.

Một điểm quan trọng: `Window<T>` không phải một Java `Stream<T>`. Window là một nhóm kết quả đã được truy vấn; `ScrollPosition` dùng để yêu cầu nhóm tiếp theo. Stream là một tài nguyên có thể được tiêu thụ tuần tự và phải đóng.

## 3. ScrollPosition và Window hoạt động như thế nào?

Một scroll query thường có ba thành phần:

- **Điều kiện truy vấn:** xác định tập dữ liệu cần duyệt, ví dụ trạng thái đơn hàng.
- **Thứ tự ổn định:** xác định bản ghi nào đứng trước hoặc sau.
- **Vị trí tiếp tục:** xác định nơi bắt đầu truy vấn window kế tiếp.

Repository method có thể trả về `Window<T>` và nhận `ScrollPosition`:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Window<User> findFirst100ByStatusOrderByIdAsc(
        UserStatus status,
        ScrollPosition position
    );
}
~~~

Method trên lấy tối đa 100 user theo trạng thái, sắp xếp ID tăng dần. `ScrollPosition` cho Spring Data biết vị trí cần tiếp tục.

Một `Window<T>` có thể được duyệt như một collection:

~~~java
Window<User> window = repository.findFirst100ByStatusOrderByIdAsc(
    UserStatus.ACTIVE,
    ScrollPosition.offset()
);

for (User user : window) {
    process(user);
}
~~~

Để lấy window kế tiếp, lấy vị trí của phần tử cuối trong window hiện tại:

~~~java
ScrollPosition nextPosition = window.positionAt(window.size() - 1);
~~~

Vị trí này là mốc để query tiếp tục. Scroll position có ngữ nghĩa **exclusive**: truy vấn tiếp theo bắt đầu sau phần tử được biểu diễn bởi vị trí đó. Nhờ vậy, phần tử cuối của window trước không bị trả lại như phần tử đầu của window sau.

Nếu window rỗng, không gọi `positionAt(window.size() - 1)` vì chỉ số sẽ không hợp lệ. Luôn kiểm tra `isEmpty()` trước khi lấy vị trí.

## 4. Duyệt thủ công qua nhiều Window

Có thể viết vòng lặp để kiểm soát rõ từng lần truy vấn và xử lý:

~~~java
public void exportActiveUsers() {
    ScrollPosition position = ScrollPosition.offset();

    while (true) {
        Window<User> window =
            userRepository.findFirst100ByStatusOrderByIdAsc(
                UserStatus.ACTIVE,
                position
            );

        if (window.isEmpty()) {
            break;
        }

        for (User user : window) {
            exportUser(user);
        }

        if (window.isLast()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
~~~

Quy trình:

1. Bắt đầu từ `ScrollPosition.offset()`.
2. Lấy một window tối đa 100 phần tử.
3. Nếu window rỗng, kết thúc.
4. Xử lý từng phần tử trong window.
5. Nếu window cuối cùng, kết thúc.
6. Lấy vị trí của phần tử cuối và truy vấn window kế tiếp.

Trong ví dụ, `exportUser` là logic nghiệp vụ do ứng dụng định nghĩa. Cần bảo đảm mỗi window được xử lý thành công trước khi chuyển checkpoint sang window tiếp theo.

Vòng lặp thủ công phù hợp khi cần ghi log, đo thời gian, lưu checkpoint, xử lý lỗi hoặc commit theo từng lô. Với luồng duyệt đơn giản, `WindowIterator` giúp giảm mã điều khiển.

## 5. Dùng WindowIterator để đơn giản hóa việc duyệt

`WindowIterator` là tiện ích của Spring Data Commons giúp duyệt liên tục nhiều window. Nó tự gọi query với vị trí tiếp theo khi cần, nên ứng dụng không phải tự viết điều kiện kiểm tra window rỗng và cập nhật `ScrollPosition`.

Ví dụ:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

public void processActiveUsers() {
    WindowIterator<User> users = WindowIterator
        .of(position ->
            userRepository.findFirst100ByStatusOrderByIdAsc(
                UserStatus.ACTIVE,
                position
            )
        )
        .startingAt(ScrollPosition.offset());

    while (users.hasNext()) {
        User user = users.next();
        process(user);
    }
}
~~~

`WindowIterator.of(...)` nhận một hàm có đầu vào là `ScrollPosition` và trả về `Window<T>`. `startingAt(...)` xác định vị trí ban đầu.

Có thể khởi tạo bằng offset hoặc keyset:

~~~java
WindowIterator<User> offsetUsers = WindowIterator
    .of(position -> userRepository.findFirst100ByStatusOrderByIdAsc(
        UserStatus.ACTIVE, position
    ))
    .startingAt(ScrollPosition.offset());
~~~

`WindowIterator` hữu ích khi chỉ cần duyệt tuần tự. Nếu cần kiểm soát transaction, lưu checkpoint, retry hoặc commit theo từng window, vòng lặp thủ công có thể dễ tổ chức hơn.

`WindowIterator` có từ Spring Data Commons 3.1. Hãy kiểm tra phiên bản Spring Data trong dự án trước khi sử dụng.

## 6. Offset-based scrolling

Offset scrolling hoạt động tương tự phân trang theo offset. Query bỏ qua một số lượng kết quả rồi lấy nhóm tiếp theo.

Ví dụ repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    Window<Order> findFirst200ByStatusOrderByIdAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Khởi tạo:

~~~java
Window<Order> firstWindow =
    orderRepository.findFirst200ByStatusOrderByIdAsc(
        OrderStatus.PAID,
        ScrollPosition.offset()
    );
~~~

Khi chuyển qua window tiếp theo, Spring Data sử dụng offset tương ứng với vị trí đã lưu.

### Phân biệt offset() và offset(0)

Đây là chi tiết dễ gây mất bản ghi đầu tiên:

- `ScrollPosition.offset()` biểu thị vị trí bắt đầu, chưa trỏ tới một phần tử cụ thể.
- `ScrollPosition.offset(0)` biểu thị vị trí của phần tử đầu tiên, có offset bằng 0.

Vì scroll position là exclusive, truy vấn bắt đầu sau vị trí được chỉ định. Do đó, dùng `ScrollPosition.offset(0)` làm vị trí ban đầu sẽ bỏ qua phần tử ở offset 0. Để bắt đầu từ bản ghi đầu tiên, hãy dùng `ScrollPosition.offset()` hoặc `OffsetScrollPosition.initial()`.

### Ưu điểm và hạn chế của offset

Ưu điểm:

- Dễ hiểu và dễ triển khai.
- Không cần lưu giá trị khóa sắp xếp của bản ghi cuối.
- Có thể dùng với nhiều kiểu sắp xếp.
- Không cần truy vấn tổng số bản ghi như `Page<T>`.

Hạn chế:

- Khi offset tăng lớn, database thường phải xử lý hoặc bỏ qua nhiều hàng trước khi trả kết quả.
- Truy vấn sâu có thể chậm dần khi dữ liệu rất lớn.
- Nếu có bản ghi được chèn hoặc xóa trước offset hiện tại giữa các lần truy vấn, vị trí số học có thể dịch chuyển, gây lặp hoặc bỏ sót bản ghi.
- Kết quả cần có thứ tự ổn định; sắp xếp theo cột không duy nhất có thể khiến thứ tự giữa các hàng bằng nhau không xác định.

Offset phù hợp với tập dữ liệu vừa phải, truy vấn không quá sâu hoặc tình huống cần cách tiếp tục đơn giản. Với dữ liệu rất lớn, keyset thường phù hợp hơn.

## 7. Keyset-based scrolling

Keyset scrolling tiếp tục dựa trên giá trị của các thuộc tính sắp xếp tại bản ghi cuối cùng của window trước. Thay vì yêu cầu database bỏ qua hàng nghìn hoặc hàng triệu kết quả, query thêm điều kiện lọc để chỉ lấy bản ghi nằm sau keyset hiện tại.

Ví dụ, dữ liệu được sắp xếp theo `createdAt` tăng dần. Vị trí tiếp tục lưu giá trị `createdAt` của phần tử cuối. Truy vấn tiếp theo có thể được diễn giải theo dạng:

~~~sql
SELECT *
FROM orders
WHERE status = ?
  AND (
      created_at > ?
      OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
LIMIT 200;
~~~

Đây là SQL minh họa nguyên lý. Spring Data và JPA provider tự xây dựng điều kiện keyset phù hợp với database, thứ tự sort và khóa chính.

Keyset có thể tận dụng index trên các trường sắp xếp để giảm lượng dữ liệu phải xử lý. Nó đặc biệt hữu ích khi duyệt tập dữ liệu lớn theo thứ tự tăng/giảm ổn định.

### Khai báo query dùng keyset

Ví dụ entity có `createdAt` không null:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    Window<Order> findFirst200ByStatusOrderByCreatedAtAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Khởi tạo bằng keyset:

~~~java
Window<Order> firstWindow =
    orderRepository.findFirst200ByStatusOrderByCreatedAtAsc(
        OrderStatus.PAID,
        ScrollPosition.keyset()
    );
~~~

`ScrollPosition.keyset()` biểu thị bắt đầu từ đầu tập kết quả, chưa áp dụng điều kiện tiếp tục theo khóa. Sau khi có window, vị trí của phần tử cuối chứa các giá trị cần thiết để truy vấn tiếp.

Spring Data bổ sung khóa chính vào thứ tự khi cần để bảo đảm từng hàng có vị trí duy nhất. Nếu nhiều đơn hàng có cùng `createdAt`, khóa chính giúp phân biệt thứ tự của chúng.

### Điều kiện quan trọng của keyset

Keyset scrolling có một số yêu cầu:

1. **Thứ tự phải ổn định.** Các trường sort cần có ý nghĩa rõ ràng và không thay đổi tùy tiện trong lúc duyệt.
2. **Thuộc tính sort phải không nullable.** So sánh với NULL có ngữ nghĩa khác nhau giữa database; keyset trên thuộc tính nullable có thể cho kết quả không mong đợi.
3. **Projection phải chứa các trường sort.** Spring Data cần đọc các giá trị khóa để tạo vị trí tiếp tục. Nếu trả DTO, hãy đưa tất cả trường sort vào DTO projection.
4. **Nên có index phù hợp.** Index theo các trường lọc và sort giúp database thực hiện điều kiện keyset hiệu quả hơn.
5. **Khóa sắp xếp cần ổn định.** Nếu một bản ghi đổi giá trị sort trong khi quá trình đang chạy, nó có thể di chuyển qua vị trí đã duyệt hoặc chưa duyệt.

Với truy vấn sort theo `createdAt`, thuộc tính này nên được ánh xạ và có giá trị khác NULL. Khóa chính được dùng làm tie-breaker để tạo thứ tự duy nhất.

## 8. So sánh offset và keyset

| Tiêu chí | Offset scrolling | Keyset scrolling |
|---|---|---|
| Vị trí tiếp tục | Số hàng đã bỏ qua | Giá trị các khóa sort ở hàng cuối |
| Cách truy vấn | Bỏ qua offset rồi lấy limit | Thêm điều kiện WHERE theo keyset |
| Chi phí khi duyệt rất sâu | Có thể tăng theo offset | Thường ổn định hơn nếu có index phù hợp |
| Yêu cầu sort | Nên có thứ tự ổn định và tie-breaker duy nhất | Cần sort ổn định, khóa sort không null |
| Projection | Linh hoạt hơn | Phải chứa các thuộc tính sort |
| Dữ liệu thay đổi giữa các lần gọi | Insert/delete trước offset có thể làm dịch vị trí | Ít bị ảnh hưởng bởi insert trước vị trí, nhưng update/delete khóa vẫn có thể ảnh hưởng |
| Trường hợp phù hợp | Tập vừa, logic đơn giản | Tập lớn, xử lý theo thứ tự, cần tiếp tục hiệu quả |

Không có cách nào tự động bảo đảm snapshot nhất quán xuyên suốt nhiều request hoặc nhiều transaction. Keyset giảm một số vấn đề dịch chuyển offset, nhưng không thay thế transaction isolation, snapshot hoặc cơ chế checkpoint của ứng dụng.

## 9. Lưu và khôi phục vị trí tiếp tục

Một ưu điểm của scrolling là ứng dụng có thể lưu checkpoint sau mỗi window. Nếu tiến trình dừng, lần chạy sau có thể tiếp tục từ vị trí đã lưu thay vì bắt đầu lại từ đầu.

Checkpoint nên gắn với:

- Điều kiện lọc, ví dụ trạng thái hoặc khoảng thời gian.
- Thứ tự sort và chiều sort.
- Kiểu scroll (offset hay keyset).
- Giá trị offset hoặc keyset cuối cùng.
- Phiên bản định nghĩa truy vấn nếu logic có thể thay đổi.
- Thời điểm và trạng thái hoàn tất của lô đã xử lý.

Không nên chỉ lưu một offset mà không lưu điều kiện và thứ tự truy vấn đi kèm. Khi filter hoặc sort thay đổi, offset/keyset cũ có thể không còn biểu thị cùng một vị trí.

Với keyset, ứng dụng có thể lưu các giá trị khóa của phần tử cuối dưới dạng một DTO checkpoint do ứng dụng quản lý. Khi khôi phục, tạo lại vị trí tương ứng theo API của phiên bản Spring Data đang dùng. Không giả định object `ScrollPosition` có thể serialize, lưu lâu dài hoặc tái sử dụng an toàn qua mọi lần nâng cấp nếu chưa kiểm tra hợp đồng API.

### Thứ tự cập nhật checkpoint

Một quy trình xử lý theo lô nên:

1. Đọc window từ vị trí đã lưu.
2. Xử lý toàn bộ phần tử của window.
3. Xác nhận các thay đổi của lô đã commit thành công.
4. Lưu checkpoint ứng với phần tử cuối đã xử lý thành công.
5. Chuyển sang window kế tiếp.

Nếu lưu checkpoint trước khi dữ liệu được xử lý thành công, tiến trình có thể bỏ qua phần việc chưa hoàn thành. Nếu xử lý xong nhưng chưa lưu checkpoint rồi tiến trình dừng, window có thể được xử lý lại.

Vì vậy, tác vụ nên có tính idempotent hoặc có khóa chống xử lý trùng. Nếu cập nhật dữ liệu và checkpoint nằm trong cùng database, có thể thiết kế chúng trong cùng transaction để giảm rủi ro lệch trạng thái. Nếu có hệ thống ngoài, cần cân nhắc transactional outbox hoặc cơ chế xác nhận tương ứng.

## 10. Dữ liệu thay đổi trong khi scrolling

Scroll query thường thực hiện nhiều lần truy vấn, mỗi lần có thể ở transaction hoặc thời điểm khác nhau. Vì thế, dữ liệu nguồn có thể thay đổi giữa các window.

Ví dụ với offset:

- Window đầu đọc các hàng ở vị trí 0–99.
- Một hàng ở đầu tập bị xóa.
- Lần truy vấn tiếp theo bắt đầu tại offset 100.
- Hàng từng ở vị trí 100 đã dịch sang 99 và có thể bị bỏ qua.

Với keyset, truy vấn tiếp tục sau giá trị khóa cuối cùng đã đọc, nên việc chèn bản ghi có khóa nhỏ hơn vị trí hiện tại thường không làm dịch chuyển vị trí tiếp tục. Tuy nhiên:

- Bản ghi mới có khóa lớn hơn vị trí hiện tại có thể xuất hiện trong các window sau.
- Bản ghi chưa đọc bị xóa sẽ không còn xuất hiện.
- Bản ghi đã đọc nhưng sort key thay đổi sang phía sau cursor có thể xuất hiện lại.
- Bản ghi chưa đọc nhưng sort key thay đổi về phía trước cursor có thể bị bỏ qua.

Nếu cần duyệt đúng một tập dữ liệu cố định, hãy xác định chính sách snapshot. Có thể dùng transaction isolation phù hợp, một mốc thời gian/ID giới hạn tập dữ liệu hoặc bảng staging chứa danh sách công việc. Giữ một transaction rất dài để duy trì snapshot cũng có chi phí về connection, lock hoặc phiên bản dữ liệu tùy database; cần cân nhắc trước khi chọn.

## 11. Scrolling với DTO projection

Window có thể trả về projection thay vì entity. Đây là lựa chọn hữu ích khi chỉ cần một vài trường và muốn giảm lượng dữ liệu được tải.

Ví dụ record:

~~~java
public record UserExportRow(
    Long id,
    String email,
    Instant createdAt
) {}
~~~

Repository:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Window<UserExportRow> findFirst500ByStatusOrderByCreatedAtAsc(
        UserStatus status,
        ScrollPosition position
    );
}
~~~

Nếu dùng keyset theo `createdAt`, projection phải chứa `createdAt` để Spring Data lấy khóa tiếp tục. Nếu Spring Data tự bổ sung ID vào thứ tự, cần bảo đảm cơ chế projection có đủ thông tin khóa theo yêu cầu của provider/phiên bản; cách an toàn là đưa các trường sort và định danh cần thiết vào DTO.

DTO projection cũng giúp tránh giữ nhiều entity managed trong persistence context khi chỉ đọc và xuất dữ liệu. Dù vậy, vẫn cần xem SQL sinh ra và xác nhận các trường được chọn đúng.

## 12. Giới hạn hỗ trợ scrolling trong Spring Data JPA

Scroll API hỗ trợ query methods, Query by Example và Querydsl. Tuy nhiên, trong tài liệu Spring Data JPA hiện hành, **scrolling với string-based query methods chưa được hỗ trợ**. Điều này bao gồm các phương thức dựa trên chuỗi query khai báo như `@Query`; stored query methods dùng `@Procedure` cũng không hỗ trợ scrolling.

Khi cần scrolling:

- Ưu tiên derived query method có `Window<T>` và `ScrollPosition`.
- Cân nhắc Query by Example nếu điều kiện tìm kiếm phù hợp.
- Cân nhắc Querydsl khi cần biểu thức điều kiện động.
- Nếu truy vấn phức tạp chỉ có thể biểu đạt bằng `@Query`, xem xét custom repository với cơ chế phân lô phù hợp, hoặc thiết kế lại truy vấn thành query method/Querydsl.
- Kiểm tra tài liệu đúng phiên bản Spring Data JPA của dự án vì khả năng hỗ trợ có thể thay đổi theo phiên bản.

Không nên chuyển một truy vấn phức tạp sang derived query chỉ để dùng scrolling nếu điều đó làm tên method quá khó hiểu hoặc không thể diễn đạt đúng nghiệp vụ.

## 13. Java Stream<T> khi xử lý dữ liệu lớn

Spring Data JPA cũng hỗ trợ repository method trả về `Stream<T>`:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Stream<User> findByStatusOrderByIdAsc(UserStatus status);
}
~~~

Service có thể tiêu thụ stream:

~~~java
@Service
public class UserExportService {

    private final UserRepository userRepository;

    public UserExportService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional(readOnly = true)
    public void exportActiveUsers() {
        try (Stream<User> users =
                 userRepository.findByStatusOrderByIdAsc(
                     UserStatus.ACTIVE
                 )) {

            users.forEach(this::exportUser);
        }
    }

    private void exportUser(User user) {
        // Ghi dữ liệu ra đích xuất của ứng dụng.
    }
}
~~~

Có ba quy tắc quan trọng:

1. **Đóng stream:** dùng try-with-resources vì stream có thể giữ JDBC ResultSet, Statement và connection.
2. **Giữ transaction trong lúc tiêu thụ:** stream cần persistence context và tài nguyên database còn hiệu lực. Không trả stream ra ngoài transaction rồi mới xử lý.
3. **Không giả định stream tự động dùng ít bộ nhớ:** JPA provider và JDBC driver quyết định cách fetch. Cần kiểm tra fetch size và cấu hình cursor của driver nếu muốn đọc tăng dần.

`@Transactional(readOnly = true)` phù hợp cho luồng chỉ đọc và giúp khai báo rõ phạm vi transaction. Nó không thay thế việc đóng stream và không bảo đảm driver luôn dùng cursor.

## 14. Stream không đồng nghĩa với incremental fetching

Kiểu trả về `Stream<T>` chỉ thể hiện API tiêu thụ kết quả tuần tự. Nó không tự bảo đảm provider hoặc JDBC driver chỉ tải một số hàng tại một thời điểm.

Một số điều cần kiểm tra:

- JPA provider có hỗ trợ streaming/cursor cho truy vấn đó không?
- JDBC driver cần fetch size bao nhiêu?
- Database/driver có yêu cầu transaction hoặc tắt autocommit để dùng cursor không?
- Query hint fetch size có được provider hỗ trợ không?
- Các entity được stream có tích lũy trong persistence context không?

Khi stream entity, mỗi entity được tải thường vẫn được persistence context quản lý. Nếu duyệt hàng triệu entity trong một transaction, persistence context có thể tăng bộ nhớ dù kết quả được tiêu thụ qua Stream.

Các cách giảm áp lực bộ nhớ:

- Chỉ chọn các trường cần thiết bằng DTO/scalar projection nếu phù hợp.
- Dùng fetch size theo tài liệu provider và driver.
- Xử lý theo lô và cân nhắc `EntityManager.clear()` hoặc `detach()` khi phù hợp.
- Nếu có ghi dữ liệu theo lô, flush và clear theo chu kỳ, đồng thời kiểm soát các entity/quan hệ còn cần sử dụng.
- Tránh truy cập lazy association sau khi entity đã bị detach.

Việc clear persistence context trong khi đang stream cần được kiểm thử với provider và driver cụ thể. Không thực hiện máy móc nếu logic còn cần entity managed hoặc lazy relationship.

## 15. Không dùng parallel stream cho một persistence context

Một Java Stream có thể hỗ trợ `parallel()`, nhưng không nên mặc định dùng parallel stream để xử lý kết quả JPA.

`EntityManager` và persistence context không thread-safe. Stream có thể gắn với một JDBC ResultSet và transaction trên một connection. Chia luồng xử lý sang nhiều thread có thể gây truy cập đồng thời không an toàn hoặc sử dụng entity ngoài transaction.

Nếu cần xử lý song song:

1. Đọc từng window hoặc batch thành dữ liệu DTO độc lập.
2. Đóng hoặc hoàn tất truy vấn và ranh giới transaction phù hợp.
3. Chuyển dữ liệu bất biến sang worker.
4. Mỗi worker dùng transaction và persistence context riêng nếu cần truy cập database.
5. Thiết kế idempotency và thứ tự commit/checkpoint.

Không chuyển một Stream JPA đang mở sang nhiều thread và không chia sẻ `EntityManager` giữa các worker.

## 16. Chọn Window hay Stream?

| Tình huống | Nên cân nhắc |
|---|---|
| Cần đọc từng nhóm, kiểm soát ranh giới batch | `Window<T>` |
| Cần lưu vị trí và tiếp tục sau khi tiến trình dừng | `Window<T>` với `ScrollPosition` và checkpoint |
| Dữ liệu lớn, sort có index và muốn tránh offset sâu | Keyset `Window<T>` |
| Dữ liệu vừa, muốn triển khai đơn giản | Offset `Window<T>` |
| Cần tổng số bản ghi cho giao diện | `Page<T>` |
| Chỉ cần biết còn trang tiếp theo | `Slice<T>` |
| Một lượt xử lý liên tục trong một transaction và driver hỗ trợ cursor | `Stream<T>` |
| Cần chạy song song theo batch | Đọc window/batch thành DTO rồi phân phối cho worker |

`Window<T>` thường dễ kiểm soát hơn khi tác vụ cần retry, checkpoint và commit theo lô. `Stream<T>` phù hợp với một lượt xử lý tuần tự khi transaction và tài nguyên JDBC có thể được giữ mở trong thời gian tiêu thụ.

## 17. Kiểm thử và theo dõi quá trình scrolling

Nên dùng integration test với database phù hợp để kiểm tra việc duyệt window và vị trí tiếp tục.

Các trường hợp nên kiểm tra:

1. Tập dữ liệu nhỏ hơn kích thước window.
2. Tập dữ liệu đúng bằng kích thước window.
3. Tập dữ liệu lớn hơn nhiều window.
4. Window cuối cùng và window rỗng.
5. Không bỏ sót hoặc lặp phần tử giữa hai window.
6. Offset bắt đầu bằng `ScrollPosition.offset()` và trường hợp dễ nhầm `offset(0)`.
7. Keyset có nhiều hàng cùng giá trị sort và khóa chính được dùng làm tie-breaker.
8. Thuộc tính sort NULL và projection thiếu sort key cần được phát hiện trong test.
9. Khôi phục từ checkpoint sau khi hoàn tất một window.
10. Insert, update hoặc delete xảy ra giữa các lần truy vấn.
11. Stream luôn được đóng khi xử lý thành công hoặc khi có exception.
12. Fetch size và mức sử dụng bộ nhớ trên database/driver mục tiêu.

Có thể đo:

- Thời gian truy vấn của từng window.
- Số bản ghi đã xử lý.
- Thời gian xử lý mỗi batch.
- Số lần retry và số batch thất bại.
- Vị trí checkpoint gần nhất đã commit.
- Dung lượng heap và connection được giữ trong lúc chạy.

Không log toàn bộ entity hoặc dữ liệu cá nhân nếu không cần thiết. Log ID/checkpoint và số lượng thường đủ để theo dõi tiến độ.

## 18. Quy trình triển khai một tác vụ duyệt dữ liệu lớn

Một quy trình thực tế có thể thực hiện như sau:

1. Xác định điều kiện lọc và thứ tự sort cố định.
2. Chọn kích thước window phù hợp với thời gian truy vấn, bộ nhớ và giới hạn transaction.
3. Chọn offset cho tập vừa hoặc keyset cho tập lớn có sort key phù hợp.
4. Tạo repository method trả về `Window<T>` và nhận `ScrollPosition`.
5. Nếu duyệt đơn giản, dùng `WindowIterator`; nếu cần checkpoint và retry, viết vòng lặp thủ công.
6. Xử lý trọn window và commit công việc thành công.
7. Lưu checkpoint sau khi batch hoàn tất.
8. Khi lỗi, retry theo chính sách và bảo đảm thao tác có thể chạy lại an toàn.
9. Theo dõi số bản ghi, thời gian, lỗi và checkpoint.
10. Với Stream, mở transaction trong lúc tiêu thụ, dùng try-with-resources và xác nhận provider/driver thực sự fetch tăng dần.

## 19. Ghi nhớ

- Scroll API chia kết quả thành `Window<T>` và dùng `ScrollPosition` để truy vấn phần tiếp theo.
- Scroll position là exclusive: truy vấn tiếp tục sau phần tử được biểu diễn bởi vị trí.
- Dùng `ScrollPosition.offset()` để bắt đầu từ đầu; `offset(0)` trỏ vào phần tử đầu tiên và có thể khiến phần tử đó bị bỏ qua.
- Offset đơn giản nhưng có thể chậm ở vị trí sâu và dễ bị ảnh hưởng khi hàng trước cursor bị chèn/xóa.
- Keyset dùng giá trị sort của phần tử cuối, thường hiệu quả hơn với dữ liệu lớn và index phù hợp.
- Keyset yêu cầu sort key không NULL và projection phải chứa các trường sort.
- Thứ tự cần ổn định; khóa chính được dùng để phân biệt các hàng có cùng giá trị sort.
- `WindowIterator` giúp duyệt nhiều window mà không phải tự cập nhật vị trí.
- Theo tài liệu Spring Data JPA hiện hành, scrolling hỗ trợ query methods, Query by Example và Querydsl; string-based query methods và stored `@Procedure` chưa hỗ trợ scrolling.
- Java `Stream<T>` phải được đóng và tiêu thụ trong transaction; nó không tự bảo đảm incremental fetching.
- Stream entity có thể làm persistence context tăng bộ nhớ; xem xét DTO, fetch size, detach/clear theo batch.
- Không chia sẻ Stream JPA hoặc `EntityManager` qua nhiều thread.
- Checkpoint phải được lưu sau khi batch xử lý thành công; thiết kế idempotency để xử lý lại an toàn.

Hãy dùng `Window<T>` khi cần chia công việc thành batch và quản lý vị trí tiếp tục. Chọn offset cho cách duyệt đơn giản, keyset cho dữ liệu lớn có thứ tự ổn định, và `Stream<T>` khi cần một lượt xử lý tuần tự trong transaction với tài nguyên JDBC được quản lý đúng cách.

## Tài liệu tham khảo

- [Spring Data JPA — JPA Query Methods, phần Scrolling Large Query Results](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Repository Query Return Types](https://docs.spring.io/spring-data/jpa/reference/repositories/query-return-types-reference.html)
- [Spring Data Commons — WindowIterator API](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/support/WindowIterator.html)