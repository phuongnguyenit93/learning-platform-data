# Luồng xóa và xác nhận thao tác

Trong module **MODEL_VIEW_CONTROLLER**, thao tác xóa là một luồng tương tác có ảnh hưởng trực tiếp đến dữ liệu và thường khó đảo ngược. Người dùng chọn một đối tượng, yêu cầu xóa, xem lại thông tin liên quan, xác nhận ý định, rồi gửi request đến Controller. Controller kiểm tra quyền và điều phối ca sử dụng; Model cùng tầng lưu trữ thực thi chính sách xóa; kết quả được phản hồi để giao diện cập nhật.

Bài học thuộc chương **Luồng tương tác**. Trọng tâm là cách thiết kế toàn bộ luồng xóa từ giao diện đến server: xác nhận đúng đối tượng, phân biệt hủy với xác nhận, bảo vệ endpoint, xử lý xung đột và lỗi, cũng như lựa chọn xóa mềm hay xóa vĩnh viễn. Một hộp thoại xác nhận chỉ là một phần của quy trình; tính đúng đắn vẫn phải được bảo đảm ở phía server.

## 1. Vì sao thao tác xóa cần một luồng riêng?

Xóa thường có hậu quả lớn hơn một thao tác đọc hoặc cập nhật thông thường. Người dùng có thể bấm nhầm, chọn nhầm dòng, hiểu sai phạm vi xóa hoặc không biết dữ liệu đang được đối tượng khác sử dụng. Hệ thống cũng phải đối mặt với request lặp, quyền truy cập không hợp lệ, dữ liệu thay đổi đồng thời và các ràng buộc lưu trữ.

Ví dụ, trong ứng dụng thư viện, người dùng muốn xóa một cuốn sách khỏi danh mục. Trước khi xóa, hệ thống cần biết:

- Người dùng đã chọn đúng cuốn sách chưa?
- Sách có đang được mượn hoặc được tham chiếu bởi giao dịch khác không?
- Người dùng có quyền xóa sách thuộc thư viện này không?
- Chính sách là ẩn khỏi danh mục, chuyển vào thùng rác hay xóa vĩnh viễn?
- Có thể khôi phục trong một khoảng thời gian không?
- Nếu một người dùng khác vừa thay đổi trạng thái sách thì request xóa có còn hợp lệ không?

Một luồng xóa rõ ràng giúp người dùng hiểu hậu quả, đồng thời giúp server bảo vệ tính toàn vẹn dữ liệu. Xác nhận trên giao diện không thay thế xác thực, phân quyền hoặc kiểm tra quy tắc nghiệp vụ.

## 2. Các bước của luồng xóa

Một luồng xóa điển hình gồm các bước:

1. Người dùng chọn đối tượng và khởi tạo thao tác xóa.
2. Giao diện hiển thị thông tin nhận diện đối tượng cùng hậu quả của thao tác.
3. Người dùng chọn **Hủy** hoặc **Xác nhận xóa**.
4. Nếu hủy, hộp thoại đóng và dữ liệu không bị thay đổi.
5. Nếu xác nhận, giao diện gửi request có chủ đích đến endpoint xóa.
6. Server định tuyến request đến Controller, xác thực danh tính và kiểm tra quyền trên đối tượng.
7. Application Service kiểm tra điều kiện nghiệp vụ, thực hiện chính sách xóa trong transaction.
8. Repository và database lưu thay đổi hoặc trả lỗi ràng buộc.
9. Controller trả kết quả; giao diện cập nhật danh sách và thông báo cho người dùng.

~~~mermaid
flowchart TD
    A["Người dùng chọn Xóa"] --> B["Giao diện lấy đúng đối tượng"]
    B --> C["Hiển thị hộp thoại xác nhận"]
    C --> D{"Người dùng quyết định"}
    D -- "Hủy" --> E["Đóng hộp thoại, giữ nguyên dữ liệu"]
    D -- "Xác nhận" --> F["Gửi request xóa"]
    F --> G["Router và Controller"]
    G --> H["Xác thực và phân quyền"]
    H --> I{"Được phép?"}
    I -- "Không" --> J["Trả lỗi phù hợp"]
    I -- "Có" --> K["Kiểm tra quy tắc nghiệp vụ"]
    K --> L{"Có thể xóa?"}
    L -- "Không" --> M["Trả xung đột hoặc lỗi nghiệp vụ"]
    L -- "Có" --> N["Thực hiện xóa trong transaction"]
    N --> O["Commit và trả kết quả"]
    O --> P["Cập nhật giao diện, thông báo"]
~~~

Luồng này mô tả một request đồng bộ. Nếu xóa cần xử lý nhiều tài nguyên hoặc chạy nền, server có thể trả trạng thái đã tiếp nhận và giao diện cần theo dõi tiến trình riêng.

### 2.1. Phân biệt chọn Xóa, xác nhận và thực thi

Ba bước này có mục đích khác nhau:

- **Chọn Xóa** biểu thị người dùng bắt đầu một ý định. Chưa có thay đổi dữ liệu nào xảy ra.
- **Xác nhận** cho biết người dùng đã xem thông tin và muốn tiếp tục. Đây là quyết định ở giao diện.
- **Thực thi xóa** là hành động phía server sau khi kiểm tra quyền và quy tắc. Chỉ server mới có thể quyết định request có được phép hoàn tất hay không.

Không nên xóa dữ liệu ngay khi người dùng bấm biểu tượng thùng rác rồi mới hỏi xác nhận. Tương tự, không được xem việc hộp thoại đã được xác nhận là bằng chứng người dùng có quyền xóa.

### 2.2. Hủy phải không tạo tác dụng phụ

Nút **Hủy** chỉ đóng hộp thoại hoặc đưa giao diện về trạng thái trước đó. Nó không gửi request xóa, không cập nhật database và không tạo một bản ghi “đã xóa”.

Nếu giao diện đã gọi API để tải thông tin xác nhận, đó chỉ nên là request đọc. Việc mở hộp thoại không được tạo thay đổi nghiệp vụ. Điều này đặc biệt quan trọng khi người dùng mở hộp thoại rồi đóng lại, nhấn Escape hoặc click ra ngoài.

## 3. Thiết kế hộp thoại xác nhận

Hộp thoại xác nhận có nhiệm vụ giúp người dùng nhận biết chính xác hành động sắp thực hiện. Một hộp thoại chỉ ghi “Bạn có chắc không?” thường thiếu thông tin để người dùng đưa ra quyết định có ý nghĩa.

Một hộp thoại tốt nên có:

- **Đối tượng cụ thể:** tên hoặc mã của bản ghi sắp xóa.
- **Hậu quả:** dữ liệu sẽ bị ẩn, chuyển vào thùng rác hay xóa vĩnh viễn.
- **Phạm vi ảnh hưởng:** các bản ghi liên quan có bị xóa theo hay không.
- **Khả năng khôi phục:** có thể khôi phục và trong thời hạn nào.
- **Hai lựa chọn rõ ràng:** Hủy và Xác nhận xóa; nút xác nhận cần có nhãn thể hiện hành động.
- **Trạng thái đang xử lý:** khóa nút xác nhận hoặc hiển thị tiến trình để tránh gửi nhiều request do click liên tục.

Ví dụ:

~~~text
Xóa cuốn sách?

Bạn sắp chuyển “Clean Code” (mã BK-1042) vào thùng rác.
Sách sẽ không còn xuất hiện trong danh mục thông thường.
Bạn có thể khôi phục sách trong 30 ngày.

[Hủy]  [Chuyển vào thùng rác]
~~~

Nếu hệ thống xóa vĩnh viễn, nội dung cần nói rõ điều đó. Nếu thao tác kéo theo việc xóa nhiều dữ liệu liên quan, hộp thoại phải mô tả phạm vi ảnh hưởng bằng ngôn ngữ dễ hiểu.

### 3.1. Hộp thoại cần hỗ trợ bàn phím và trình đọc màn hình

Khi hộp thoại mở, focus nên được chuyển vào trong hộp thoại, thường đến tiêu đề hoặc nút an toàn như Hủy. Người dùng có thể di chuyển focus bằng bàn phím; khi đóng hộp thoại, focus được trả về nút đã mở nó.

Cần cung cấp tên truy cập được, vai trò dialog, tiêu đề và mô tả phù hợp. Escape có thể đóng hộp thoại và được hiểu như hủy. Không đặt focus mặc định vào nút xóa trong các thao tác có hậu quả lớn, vì người dùng có thể nhấn Enter theo thói quen.

Trên giao diện cảm ứng, nút Hủy và Xác nhận cần đủ lớn và có khoảng cách để giảm thao tác nhầm. Màu đỏ có thể biểu thị hành động nguy hiểm, nhưng màu sắc không được là tín hiệu duy nhất; nhãn hành động phải rõ ràng.

### 3.2. Xác nhận tăng cường cho thao tác rủi ro cao

Với một thao tác xóa hàng loạt, xóa tài khoản, xóa dữ liệu không thể phục hồi hoặc xóa trong hệ thống quản trị, có thể yêu cầu xác nhận mạnh hơn:

- Nhập lại tên đối tượng hoặc một cụm từ được chỉ định.
- Nhập mật khẩu hoặc xác thực lại khi thao tác có rủi ro cao.
- Hiển thị số lượng bản ghi và phạm vi ảnh hưởng.
- Yêu cầu người có vai trò đặc biệt phê duyệt.
- Tạo bản xem trước (preview) cho thao tác hàng loạt.

Không cần áp dụng xác nhận nhiều bước cho mọi thao tác. Mức xác nhận nên tương xứng với hậu quả, khả năng khôi phục và mức độ khó đảo ngược.

## 4. Từ giao diện đến Controller

Khi người dùng xác nhận, giao diện gửi request xóa. Với API, cách phổ biến là HTTP DELETE trên URL định danh tài nguyên:

~~~http
DELETE /api/books/1042
Authorization: Bearer <access-token>
~~~

Với form HTML, trình duyệt chỉ hỗ trợ trực tiếp GET và POST trong thuộc tính method của form. Ứng dụng có thể dùng POST tới một endpoint thể hiện rõ ý định xóa, hoặc dùng cơ chế method override do framework hỗ trợ. Dù cách biểu diễn khác nhau, server vẫn phải kiểm tra CSRF nếu xác thực dựa trên cookie session.

Ví dụ form gửi POST:

~~~html
<form method="post" action="/books/1042/delete">
  <input type="hidden" name="_csrf" value="csrf-token-do-framework-cap" />
  <button type="submit">Xác nhận xóa</button>
</form>
~~~

Trong ứng dụng thật, token CSRF phải được tạo và kiểm tra bởi cơ chế bảo mật của framework; không tự đặt một chuỗi cố định như ví dụ minh họa.

### 4.1. Controller chỉ tiếp nhận và điều phối

Một Controller Spring MVC có thể ánh xạ request DELETE đến action:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookApplicationService books;

    public BookController(BookApplicationService books) {
        this.books = books;
    }

    @DeleteMapping("/{bookId}")
    public ResponseEntity<Void> delete(@PathVariable UUID bookId) {
        books.delete(bookId);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller nhận định danh, gọi ca sử dụng và chọn response. Nó không tự thực hiện câu SQL, tự xóa file hoặc tự quyết định mọi quy tắc nghiệp vụ. Application Service có thể tải Aggregate, kiểm tra điều kiện, yêu cầu repository xóa hoặc đánh dấu đã xóa, rồi hoàn tất transaction.

Với HTML MVC, action thường chuyển hướng về danh sách sau khi xóa thành công:

~~~java
@PostMapping("/{bookId}/delete")
public String delete(
    @PathVariable UUID bookId,
    RedirectAttributes redirect
) {
    books.delete(bookId);
    redirect.addFlashAttribute("message", "Đã chuyển sách vào thùng rác");
    return "redirect:/books";
}
~~~

Ví dụ rút gọn chưa bao gồm xử lý lỗi. Trong ứng dụng thực tế, lỗi không tìm thấy, không đủ quyền hoặc không thể xóa do ràng buộc nghiệp vụ cần được ánh xạ thành response hoặc thông báo phù hợp.

### 4.2. Không thực hiện xóa qua GET

Không tạo route kiểu GET /books/1042/delete để xóa ngay khi mở URL. Trình duyệt, crawler, link preview hoặc cơ chế prefetch có thể tự gửi GET. Người dùng cũng có thể vô tình mở liên kết từ lịch sử hoặc bookmark.

GET phải giữ ngữ nghĩa đọc an toàn. Thao tác thay đổi dữ liệu cần dùng method phù hợp như DELETE hoặc POST/PATCH theo hợp đồng. Hộp thoại xác nhận là bước giao diện trước request thay đổi, không phải lý do để biến hành động xóa thành GET.

## 5. Kiểm tra quyền và điều kiện nghiệp vụ phía server

Một request xóa có thể được gửi trực tiếp bằng công cụ HTTP mà không mở giao diện. Vì vậy, server phải tự kiểm tra tất cả điều kiện quan trọng.

### 5.1. Xác thực và phân quyền trên đúng đối tượng

Xác thực xác định ai đang gửi request. Phân quyền kiểm tra người đó có được xóa đối tượng cụ thể không. Kiểm tra quyền cần gắn với đối tượng, tổ chức hoặc phạm vi dữ liệu thực tế.

Ví dụ, nhân viên có quyền xóa sách thuộc chi nhánh của mình nhưng không có quyền xóa sách thuộc chi nhánh khác. Chỉ kiểm tra role ADMIN hoặc STAFF ở cấp Controller có thể không đủ nếu quyền còn phụ thuộc quyền sở hữu hoặc phạm vi tổ chức.

Không dựa vào việc nút Xóa chỉ hiển thị với một số vai trò. Giao diện chỉ hỗ trợ trải nghiệm; kiểm soát truy cập có thẩm quyền phải diễn ra ở server.

### 5.2. Kiểm tra trạng thái hiện tại

Một đối tượng có thể đã thay đổi kể từ khi hộp thoại được mở. Ví dụ, người dùng mở xác nhận xóa một cuốn sách chưa có giao dịch mượn; trong lúc đó, một người khác tạo giao dịch mượn. Khi request xóa đến server, điều kiện ban đầu không còn đúng.

Application Service hoặc Model cần kiểm tra lại trạng thái hiện tại trong lúc thực thi. Không dùng kết quả preview cũ làm bằng chứng rằng thao tác vẫn hợp lệ.

### 5.3. CSRF và request giả mạo

Nếu ứng dụng dùng cookie tự động gửi kèm request, một trang bên ngoài có thể tìm cách khiến trình duyệt gửi request xóa dưới danh nghĩa người dùng đang đăng nhập. Với HTML form và session cookie, cần bật token CSRF hoặc biện pháp bảo vệ tương đương.

Đối với API dùng bearer token được client chủ động gắn vào header, mô hình rủi ro CSRF khác với cookie tự động gửi; tuy vậy vẫn cần bảo vệ token, CORS và quyền truy cập theo thiết kế xác thực. Không nên tắt CSRF toàn ứng dụng chỉ vì có một số endpoint API.

## 6. Chọn chính sách xóa: mềm, cứng hay lưu trữ

Từ “xóa” có thể đại diện cho nhiều chính sách dữ liệu. UI và API phải thể hiện đúng chính sách được chọn.

| Chính sách | Cách thực hiện | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|---|
| Xóa mềm (soft delete) | Đánh dấu deletedAt, deletedBy hoặc trạng thái đã xóa | Cần khôi phục, audit hoặc giữ tham chiếu lịch sử | Truy vấn thông thường phải lọc dữ liệu đã xóa |
| Xóa vĩnh viễn (hard delete) | Xóa bản ghi khỏi nơi lưu trữ chính | Dữ liệu không còn cần thiết và không bị ràng buộc giữ lại | Khó khôi phục; cần xử lý quan hệ và backup |
| Lưu trữ (archive) | Chuyển sang trạng thái hoặc vùng lưu trữ ít hoạt động | Cần giữ lịch sử nhưng loại khỏi luồng làm việc thường ngày | Cần định nghĩa quyền đọc và thời hạn lưu |
| Ẩn (hide/unpublish) | Thay đổi khả năng hiển thị hoặc trạng thái công khai | Người dùng muốn ngừng hiển thị nhưng vẫn giữ dữ liệu hoạt động | Không được gọi nhầm là xóa nếu dữ liệu vẫn còn |

### 6.1. Xóa mềm

Xóa mềm thường cập nhật một số trường như deletedAt, deletedBy và trạng thái. Bản ghi vẫn còn trong database nhưng các truy vấn thông thường bỏ qua nó.

Ưu điểm là có thể khôi phục, giữ lịch sử và tránh phá vỡ tham chiếu. Tuy nhiên, cần thiết kế nhất quán:

- Repository mặc định không trả bản ghi đã xóa trong truy vấn thông thường.
- Màn hình thùng rác có truy vấn riêng để xem và khôi phục.
- Unique constraint cần xem xét dữ liệu đã xóa có được phép dùng lại khóa nghiệp vụ hay không.
- Các báo cáo và truy vấn tổng hợp cần xác định có tính bản ghi đã xóa hay không.
- Cần quy định thời hạn dọn dẹp và người được phép xóa vĩnh viễn.

Không chỉ thêm cột deleted_at rồi để mọi truy vấn tự quyết định. Một truy vấn quên điều kiện lọc có thể làm bản ghi đã xóa xuất hiện trở lại ngoài ý muốn.

### 6.2. Xóa vĩnh viễn

Xóa cứng loại bỏ bản ghi khỏi database chính. Trước khi thực hiện, cần hiểu các quan hệ:

- **RESTRICT / NO ACTION:** database từ chối xóa khi còn bản ghi tham chiếu.
- **CASCADE:** xóa bản ghi cha có thể xóa các bản ghi con.
- **SET NULL:** tham chiếu ở bản ghi con được đặt thành null nếu schema cho phép.
- **Xử lý theo nghiệp vụ:** application service có thể yêu cầu hoàn tất hoặc hủy các đối tượng liên quan trước khi xóa.

Không chọn CASCADE chỉ vì nó tiện. Xóa một cuốn sách không nên vô tình xóa lịch sử mượn, hóa đơn hoặc audit record nếu các dữ liệu đó cần được giữ lại. Chính sách xóa phải xuất phát từ ý nghĩa dữ liệu và yêu cầu lưu giữ.

Xóa bản ghi trong database cũng không tự động xóa file đính kèm, bản sao cache, chỉ mục tìm kiếm hoặc dữ liệu ở hệ thống bên ngoài. Những tài nguyên này cần một quy trình dọn dẹp phù hợp và có thể chạy bất đồng bộ.

### 6.3. Lưu trữ và ẩn dữ liệu

Có trường hợp người dùng nói “xóa” nhưng ý định thực là ngừng hiển thị. Ví dụ, một sách đã ngừng kinh doanh cần được ẩn khỏi danh mục nhưng lịch sử giao dịch vẫn phải tra cứu được. Khi đó, trạng thái archived hoặc unpublished diễn đạt đúng hơn việc xóa.

Tên nút và thông báo cần phản ánh hành vi thực tế. Không nói “đã xóa vĩnh viễn” nếu dữ liệu chỉ được đánh dấu ẩn; cũng không nói “đã chuyển vào thùng rác” nếu server đã xóa không thể phục hồi.

## 7. Transaction, ràng buộc và xử lý đồng thời

Xóa một đối tượng có thể ảnh hưởng nhiều bản ghi. Application Service cần xác định đơn vị công việc phải nhất quán và thực hiện trong transaction phù hợp.

Ví dụ, khi xóa một danh mục, hệ thống có thể cần gỡ liên kết đến sản phẩm, ghi audit event và đánh dấu danh mục đã xóa. Nếu một bước thất bại, transaction cần rollback các thay đổi thuộc cùng ranh giới nhất quán.

Tuy nhiên, transaction không tự giải quyết mọi cạnh tranh. Một request có thể đọc trạng thái, sau đó request khác thay đổi dữ liệu trước khi thao tác xóa commit. Có thể cần:

- Optimistic locking bằng version để phát hiện bản ghi đã thay đổi.
- Pessimistic locking khi cần khóa dữ liệu trong phạm vi ngắn.
- Điều kiện cập nhật nguyên tử, ví dụ chỉ xóa nếu trạng thái hiện vẫn là DRAFT.
- Ràng buộc khóa ngoại và unique constraint ở database.
- Chính sách retry có giới hạn cho xung đột có thể phục hồi.

Nếu version không khớp, server có thể trả 409 Conflict hoặc thông báo yêu cầu người dùng tải lại dữ liệu. Không tự động xóa tiếp bằng dữ liệu cũ vì điều đó có thể ghi đè một thay đổi hợp lệ khác.

### 7.1. Xóa nhiều đối tượng

Xóa hàng loạt cần xác định rõ danh sách ID và số lượng. Trước khi xác nhận, UI nên hiển thị số đối tượng được chọn và phạm vi ảnh hưởng. Server phải kiểm tra quyền trên từng đối tượng, vì một danh sách ID có thể chứa bản ghi mà người dùng không được phép xóa.

Nếu thao tác có thể hoàn tất nguyên tử, có thể dùng một transaction với giới hạn hợp lý. Nếu danh sách rất lớn hoặc có tác vụ ngoài, nên xử lý theo batch/job, lưu trạng thái tiến trình và báo rõ đối tượng nào thành công hoặc thất bại. Không trả “đã xóa tất cả” nếu chỉ một phần được xử lý.

### 7.2. Xóa tài nguyên bên ngoài database

Một đối tượng có thể tham chiếu file trong object storage hoặc bản ghi trong search index. Không thể luôn gộp thao tác database và dịch vụ ngoài vào cùng một transaction ACID.

Một mẫu thường dùng là đánh dấu yêu cầu xóa trong database và ghi outbox event cùng transaction. Worker đọc event để xóa file hoặc cập nhật search index; thao tác cần có retry và tính lặp an toàn. Giao diện có thể hiển thị trạng thái “đang xóa” cho đến khi công việc nền hoàn tất.

## 8. Phản hồi sau khi xóa

Controller cần trả kết quả phù hợp với loại client và chính sách xóa.

| Kết quả | API | HTML MVC |
|---|---|---|
| Xóa thành công | 204 No Content hoặc 200 với representation | Redirect về danh sách và hiển thị thông báo |
| Đã tiếp nhận tác vụ nền | 202 Accepted, có URL theo dõi nếu cần | Redirect đến trang trạng thái |
| Không tìm thấy | 404 Not Found | Trang/thông báo không tìm thấy |
| Không có quyền | 403 Forbidden hoặc 404 theo chính sách che giấu | Trang từ chối truy cập |
| Không thể xóa do ràng buộc | 409 Conflict | Hiển thị lý do và hướng xử lý |
| Dữ liệu đã thay đổi | 409 Conflict hoặc 412 Precondition Failed | Yêu cầu tải lại và xác nhận lại |
| Request không hợp lệ | 400 Bad Request | Trả lại form hoặc trang lỗi |

### 8.1. Không tìm thấy và request lặp

HTTP DELETE có ngữ nghĩa idempotent: gửi cùng yêu cầu nhiều lần không nên làm phát sinh thêm hiệu ứng ngoài ý muốn. Điều đó không bắt buộc mọi lần đều trả cùng status code. Lần đầu có thể trả 204; lần sau có thể trả 404 vì tài nguyên đã không còn, hoặc trả 204 nếu API định nghĩa xóa lặp là thành công.

Hãy chọn một hợp đồng nhất quán và tài liệu hóa. Với xóa mềm, lần gửi lại có thể nhận biết bản ghi đã ở trạng thái deleted và không cập nhật lại audit metadata ngoài chính sách. Với tác vụ xóa nền, cần mã tác vụ hoặc khóa idempotency để tránh tạo nhiều công việc dọn dẹp trùng lặp.

### 8.2. Thông báo không tiết lộ dữ liệu nhạy cảm

Thông báo nên nói rõ kết quả mà người dùng cần biết. Không hiển thị câu SQL, tên bảng, stack trace hoặc chi tiết nội bộ khi thao tác thất bại. Log nội bộ có thể ghi mã tương quan, danh tính người thao tác, đối tượng và nguyên nhân kỹ thuật theo chính sách bảo mật.

Với trường hợp không đủ quyền, thông báo cần tuân theo chính sách của ứng dụng. Một số hệ thống trả 404 để không tiết lộ sự tồn tại của tài nguyên; nếu chọn cách này, cần nhất quán giữa các endpoint.

## 9. Khôi phục và Undo

Nếu dùng xóa mềm, hệ thống có thể cung cấp khả năng khôi phục. Có hai trải nghiệm thường gặp:

- **Undo ngay sau thao tác:** sau khi xóa, giao diện hiển thị thông báo có nút Hoàn tác trong một khoảng thời gian ngắn.
- **Thùng rác:** người dùng vào một màn hình riêng để xem và khôi phục các bản ghi đã xóa.

Undo không nên chỉ đảo giao diện. Nó phải gọi endpoint khôi phục, kiểm tra quyền, kiểm tra bản ghi còn trong thời hạn và xác minh trạng thái hiện tại có cho phép khôi phục không.

Ví dụ, nếu một ISBN đã được dùng bởi bản ghi khác sau khi sách cũ bị xóa mềm, thao tác khôi phục có thể xung đột unique constraint. Server cần trả lỗi có ý nghĩa và hướng dẫn người dùng xử lý, không tự ghi đè bản ghi mới.

Với xóa vĩnh viễn, Undo thông thường không khả thi. Khôi phục chỉ có thể dựa trên backup hoặc cơ chế lưu trữ riêng, nên không nên quảng bá một nút Hoàn tác nếu hệ thống không bảo đảm thực hiện được.

## 10. Ví dụ luồng xác nhận trong giao diện

Pseudocode dưới đây minh họa cách giữ đối tượng được chọn, hiển thị xác nhận và chỉ gửi request khi người dùng xác nhận. Đây là ví dụ khái niệm; ứng dụng thực tế cần dùng framework UI và cơ chế quản lý state phù hợp.

~~~javascript
async function requestDelete(book) {
  const confirmed = await showConfirmDialog({
    title: "Xóa cuốn sách?",
    message: "Bạn muốn chuyển " + book.title + " vào thùng rác?",
    confirmLabel: "Chuyển vào thùng rác",
    cancelLabel: "Hủy"
  });

  if (!confirmed) {
    return;
  }

  setDeleteState(book.id, "pending");

  try {
    const response = await fetch("/api/books/" + book.id, {
      method: "DELETE",
      headers: {
        "Accept": "application/json"
      }
    });

    if (!response.ok) {
      throw new Error("Delete failed: " + response.status);
    }

    removeBookFromList(book.id);
    showMessage("Đã chuyển sách vào thùng rác");
  } catch (error) {
    showError("Không thể xóa sách. Hãy tải lại và thử lại.");
  } finally {
    setDeleteState(book.id, "idle");
  }
}
~~~

Đoạn code chỉ mô tả luồng phía client. Nếu ứng dụng xác thực bằng cookie session, request phải kèm token CSRF theo cách framework quy định. Không nên đặt token bí mật vào URL. Client cũng cần tránh gửi lại khi request đang pending và nên giữ dữ liệu để phục hồi giao diện nếu server trả lỗi.

### 10.1. Trạng thái giao diện khi request đang chạy

Sau khi người dùng xác nhận, nút xóa nên chuyển sang trạng thái đang xử lý. Có thể vô hiệu hóa nút xác nhận và hiển thị spinner hoặc nhãn “Đang xóa…”. Khi server trả thành công, loại bỏ dòng khỏi danh sách hoặc cập nhật trạng thái. Khi lỗi, giữ dữ liệu trên màn hình và hiển thị cách xử lý.

Nếu người dùng có thể mở nhiều hộp thoại hoặc chọn nhiều dòng, trạng thái pending cần gắn với đúng đối tượng hoặc đúng batch. Không dùng một cờ chung khiến thao tác xóa một dòng vô hiệu hóa nhầm toàn bộ danh sách.

## 11. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Xóa ngay khi bấm biểu tượng mà không có bước xem lại | Dễ xóa nhầm đối tượng | Hiển thị xác nhận có tên và mã đối tượng |
| Hộp thoại chỉ hỏi “Bạn có chắc không?” | Người dùng không hiểu hậu quả | Nêu chính sách xóa, phạm vi và khả năng khôi phục |
| Chỉ dựa vào xác nhận phía client | Request trực tiếp vẫn có thể xóa dữ liệu | Kiểm tra quyền và quy tắc ở server |
| Dùng GET để xóa | Crawler/prefetch có thể kích hoạt hành động | Dùng DELETE hoặc POST có CSRF |
| Chỉ ẩn nút Xóa theo role | Endpoint vẫn có thể bị gọi trực tiếp | Authorization trên từng tài nguyên |
| Dùng CASCADE không xem xét dữ liệu liên quan | Có thể mất lịch sử hoặc dữ liệu cần giữ | Xác định rõ chính sách quan hệ và retention |
| Xóa mềm nhưng quên lọc truy vấn | Bản ghi đã xóa vẫn xuất hiện | Chuẩn hóa truy vấn mặc định và màn hình thùng rác |
| Không xử lý request lặp | Audit hoặc job dọn dẹp bị nhân đôi | Thiết kế idempotency và trạng thái xóa |
| Không xử lý cạnh tranh | Xóa một đối tượng vừa được thay đổi hoặc sử dụng | Kiểm tra version/trạng thái trong transaction |
| Xóa database nhưng quên file/cache/index | Dữ liệu mồ côi hoặc kết quả tìm kiếm sai | Dùng outbox/job dọn dẹp có retry |
| Giao diện loại bỏ dòng ngay trước khi server xác nhận | UI thể hiện thành công giả khi server từ chối | Chỉ xác nhận trạng thái sau response thành công hoặc dùng optimistic UI có rollback |

## 12. Kiểm thử luồng xóa và xác nhận

Kiểm thử nên bao phủ cả quyết định ở giao diện, request đến Controller và thay đổi dữ liệu ở tầng nghiệp vụ.

### 12.1. Kiểm thử giao diện

- Mở hộp thoại đúng đối tượng đã chọn.
- Tên, mã và hậu quả hiển thị chính xác.
- Chọn Hủy hoặc nhấn Escape không gửi request xóa.
- Chọn Xác nhận gửi đúng ID và đúng method.
- Nút xác nhận bị khóa khi request đang xử lý.
- Thành công cập nhật danh sách và thông báo.
- Lỗi giữ lại dữ liệu hoặc phục hồi trạng thái giao diện.
- Focus được quản lý đúng khi mở và đóng dialog.

### 12.2. Kiểm thử Controller và bảo mật

- Request DELETE hợp lệ được ánh xạ đến action đúng.
- GET tới URL xóa không làm thay đổi dữ liệu.
- Người dùng chưa xác thực không thể thực hiện thao tác.
- Người dùng đã xác thực nhưng không có quyền nhận kết quả từ chối.
- Người dùng không thể xóa đối tượng ngoài phạm vi được phép.
- Request thiếu CSRF token bị từ chối khi dùng cookie session.
- Request ID sai định dạng hoặc không tồn tại được xử lý theo hợp đồng.

### 12.3. Kiểm thử nghiệp vụ và lưu trữ

- Đối tượng có thể xóa được chuyển sang trạng thái đúng.
- Đối tượng đang được tham chiếu bị từ chối hoặc xử lý theo chính sách đã định.
- Xóa mềm có thể khôi phục trong thời hạn.
- Xóa vĩnh viễn xử lý đúng foreign key và dữ liệu liên quan.
- Hai request đồng thời không làm mất tính toàn vẹn.
- Gửi lại DELETE tuân theo hợp đồng idempotency.
- Transaction rollback khi một bước bắt buộc thất bại.
- Outbox/job dọn dẹp có retry và không tạo tác dụng phụ trùng lặp.

## 13. Checklist thiết kế thao tác xóa

- [ ] Giao diện xác định rõ đối tượng trước khi mở xác nhận.
- [ ] Hộp thoại mô tả hậu quả, phạm vi và khả năng khôi phục.
- [ ] Hủy chỉ đóng hộp thoại và không gửi request thay đổi dữ liệu.
- [ ] Xác nhận gửi đúng endpoint, đúng ID và đúng HTTP method.
- [ ] Không dùng GET cho hành động xóa.
- [ ] Server xác thực, phân quyền và kiểm tra quyền trên đúng tài nguyên.
- [ ] Model hoặc ca sử dụng kiểm tra trạng thái và quy tắc nghiệp vụ hiện tại.
- [ ] Chính sách soft delete, hard delete, archive và retention được xác định rõ.
- [ ] Quan hệ dữ liệu, transaction và cạnh tranh đồng thời được xử lý.
- [ ] Request lặp, lỗi và thao tác bất đồng bộ có hợp đồng phản hồi rõ.
- [ ] UI chỉ hiển thị thành công sau khi có kết quả đáng tin cậy từ server.
- [ ] Có kiểm thử cho hủy, xác nhận, quyền, CSRF, lỗi, khôi phục và request lặp.

Luồng xóa an toàn kết hợp ba điều: người dùng hiểu rõ đối tượng và hậu quả trước khi xác nhận; Controller chuyển request đến đúng ca sử dụng; server kiểm tra quyền và chính sách dữ liệu trước khi thay đổi trạng thái. Khi ba phần này nhất quán, thao tác xóa trở nên dễ dự đoán, có thể kiểm thử và phù hợp với vòng đời dữ liệu của ứng dụng.
