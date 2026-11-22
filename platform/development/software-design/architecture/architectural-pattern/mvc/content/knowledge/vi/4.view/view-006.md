# Hiển thị danh sách, chi tiết và trạng thái rỗng

## 1. Vai trò của View trong MVC

Trong kiến trúc Model–View–Controller, **View** chịu trách nhiệm trình bày thông tin để người dùng quan sát và tương tác. Với ứng dụng web, View thường là HTML được tạo từ template phía máy chủ hoặc giao diện được dựng ở trình duyệt. View nhận dữ liệu đã được Controller chuẩn bị, sau đó tổ chức dữ liệu thành tiêu đề, bảng, liên kết, nhãn trạng thái, biểu mẫu và thông báo.

Trong một chức năng quản lý sách, người dùng thường cần ba cách nhìn cơ bản:

- **Danh sách:** quan sát nhiều cuốn sách, tìm kiếm, lọc, sắp xếp và mở một mục.
- **Chi tiết:** xem đầy đủ thông tin của một cuốn sách và các thao tác được phép.
- **Trạng thái rỗng:** hiểu vì sao danh sách hiện không có mục nào và biết bước tiếp theo có thể thực hiện.

Ba cách nhìn này có quan hệ với nhau. Danh sách cung cấp đường dẫn đến chi tiết; chi tiết cung cấp đường quay lại danh sách; trạng thái rỗng giúp người dùng không nhầm một kết quả hợp lệ có số lượng bằng không với lỗi tải dữ liệu.

View nên tập trung vào cách trình bày. Quy tắc như người dùng có được phép sửa sách hay không, sách nào được đưa vào kết quả tìm kiếm, hoặc một cuốn sách có tồn tại hay không phải được quyết định ở tầng nghiệp vụ và xử lý request. Controller chuyển kết quả đó thành dữ liệu phù hợp cho View.

## 2. Luồng dữ liệu từ Controller đến View

Với một trang danh sách, luồng thường gặp là:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant C as BookController
    participant S as BookService
    participant R as BookRepository
    participant V as View template
    U->>B: Mở /books?q=java
    B->>C: GET /books?q=java
    C->>S: Tìm sách theo điều kiện
    S->>R: Truy vấn danh sách và phân trang
    R-->>S: Kết quả truy vấn
    S-->>C: Dữ liệu và thông tin trang
    C->>V: Truyền View Model
    V-->>B: HTML danh sách hoặc trạng thái rỗng
~~~

Controller không nên truyền toàn bộ đối tượng persistence vào template nếu View chỉ cần một vài trường. Thay vào đó, Controller hoặc lớp trình bày có thể chuyển kết quả nghiệp vụ thành **View Model**: một cấu trúc dữ liệu dành riêng cho mục đích hiển thị.

Ví dụ, một mục trong danh sách sách có thể chỉ cần:

~~~java
public record BookListItem(
        UUID id,
        String title,
        String authorName,
        String isbn,
        String statusLabel
) {}

public record PageInfo(
        int currentPage,
        int totalPages,
        long totalItems
) {}
~~~

`BookListItem` không cần chứa mọi quan hệ của Entity `Book`, thông tin nội bộ hay dữ liệu không được phép công khai. `PageInfo` cung cấp những gì View cần để hiển thị điều hướng phân trang. Tên và cấu trúc các kiểu dữ liệu thực tế phụ thuộc vào ứng dụng.

## 3. Thiết kế màn hình danh sách

Một trang danh sách tốt giúp người dùng trả lời nhanh ba câu hỏi: đang xem loại dữ liệu nào, có những mục nào, và có thể làm gì tiếp theo. Vì vậy, trang thường có tiêu đề rõ ràng, khu vực tìm kiếm/lọc, tổng số kết quả khi hữu ích, nội dung danh sách và điều hướng.

### Chọn cấu trúc trình bày phù hợp

**Bảng (table)** phù hợp khi người dùng cần so sánh nhiều thuộc tính giữa các bản ghi, chẳng hạn tiêu đề, tác giả, ISBN, trạng thái và ngày cập nhật. Bảng cần tiêu đề cột có ý nghĩa và mỗi hàng cần có một liên kết hoặc thao tác rõ ràng.

**Danh sách (list)** phù hợp khi mỗi mục có ít thuộc tính hoặc nội dung dạng văn bản. **Thẻ (card)** hữu ích khi mỗi mục có phần mô tả, hình ảnh hoặc hành động riêng. Không nên dùng bảng chỉ vì dữ liệu đến từ cơ sở dữ liệu; hãy chọn cấu trúc dựa trên nhiệm vụ của người dùng.

### Ví dụ View danh sách với Thymeleaf

Đoạn template dưới đây minh họa một bảng sách. `books` là danh sách View Model do Controller cung cấp:

~~~html
<main>
  <header>
    <h1>Danh sách sách</h1>
    <a th:href="@{/books/new}">Thêm sách</a>
  </header>

  <form method="get" th:action="@{/books}" role="search">
    <label for="book-query">Tìm theo tiêu đề hoặc tác giả</label>
    <input id="book-query" name="q" type="search"
           th:value="${query}" />
    <button type="submit">Tìm kiếm</button>
  </form>

  <table th:if="${!#lists.isEmpty(books)}">
    <caption>Danh sách sách trong thư viện</caption>
    <thead>
      <tr>
        <th scope="col">Tiêu đề</th>
        <th scope="col">Tác giả</th>
        <th scope="col">ISBN</th>
        <th scope="col">Trạng thái</th>
      </tr>
    </thead>
    <tbody>
      <tr th:each="book : ${books}">
        <td>
          <a th:href="@{/books/{id}(id=${book.id})}"
             th:text="${book.title}">Tên sách</a>
        </td>
        <td th:text="${book.authorName}">Tên tác giả</td>
        <td th:text="${book.isbn}">ISBN</td>
        <td th:text="${book.statusLabel}">Đang lưu hành</td>
      </tr>
    </tbody>
  </table>
</main>
~~~

`th:each` lặp qua từng mục; `th:text` đưa giá trị vào nội dung văn bản theo cơ chế escape mặc định của Thymeleaf; `th:href` tạo URL chi tiết từ ID. Nhờ dùng URL có tham số đường dẫn, View không phải tự nối chuỗi URL bằng tay.

Đoạn ví dụ giả định Controller luôn cung cấp `books` dưới dạng collection không null. Hãy thống nhất hợp đồng dữ liệu này: View nhận một collection rỗng khi không có kết quả, thay vì phải xử lý cả `null` lẫn collection.

### Tìm kiếm, lọc và sắp xếp

Khi danh sách có nhiều dữ liệu, tìm kiếm và lọc giúp người dùng thu hẹp phạm vi. Các điều kiện thường được biểu diễn bằng query parameter, ví dụ:

~~~http
GET /books?q=java&status=AVAILABLE&sort=title&page=0&size=20
~~~

Controller đọc các tham số, kiểm tra giới hạn hợp lệ và yêu cầu Service thực hiện truy vấn. View hiển thị lại các điều kiện hiện tại để người dùng hiểu vì sao họ đang thấy tập kết quả đó. Khi chuyển trang hoặc đổi thứ tự sắp xếp, các bộ lọc hiện tại nên được giữ lại.

Không nên để template tự lọc toàn bộ danh sách lớn ở phía máy chủ bằng các vòng lặp điều kiện. Việc tìm kiếm, lọc, sắp xếp và phân trang dữ liệu lớn thuộc về tầng truy vấn hoặc Service. View chỉ trình bày kết quả và các lựa chọn điều hướng.

### Phân trang

Phân trang giúp giới hạn số bản ghi gửi đến một response và giúp người dùng di chuyển qua tập kết quả. View thường cần biết trang hiện tại, tổng số trang và các tham số tìm kiếm/lọc đang áp dụng.

~~~html
<nav aria-label="Điều hướng trang" th:if="${page.totalPages > 1}">
  <a th:if="${page.currentPage > 0}"
     th:href="@{/books(q=${query}, page=${page.currentPage - 1})}">
    Trang trước
  </a>
  <span>
    Trang <span th:text="${page.currentPage + 1}">1</span>
    / <span th:text="${page.totalPages}">5</span>
  </span>
  <a th:if="${page.currentPage + 1 < page.totalPages}"
     th:href="@{/books(q=${query}, page=${page.currentPage + 1})}">
    Trang sau
  </a>
</nav>
~~~

Đây là ví dụ tối giản để minh họa việc giữ lại từ khóa tìm kiếm. Nếu trang còn có trạng thái, sắp xếp hoặc kích thước trang, các tham số đó cũng cần được giữ khi tạo liên kết. Không hiển thị liên kết trang trước/trang sau khi người dùng đã ở biên tương ứng. Controller cần xử lý page/size ngoài phạm vi hợp lệ và tránh trả về trang trống gây hiểu nhầm khi người dùng nhập một số trang không tồn tại.

## 4. Thiết kế màn hình chi tiết

Trang chi tiết tập trung vào một đối tượng. Người dùng cần nhận biết họ đang xem mục nào, các thông tin quan trọng là gì, trạng thái hiện tại ra sao và hành động nào có thể thực hiện.

Với trang chi tiết sách, thông tin có thể gồm tiêu đề, tác giả, ISBN, mô tả, ngày xuất bản và tình trạng lưu thông. Hãy sắp xếp theo mức độ quan trọng và nhóm các thuộc tính có quan hệ. Những trường ít quan trọng hoặc chỉ phục vụ quản trị có thể nằm ở khu vực phụ.

### Ví dụ View chi tiết với Thymeleaf

~~~html
<main>
  <nav aria-label="Đường dẫn điều hướng">
    <a th:href="@{/books}">Danh sách sách</a>
    <span aria-hidden="true">/</span>
    <span aria-current="page" th:text="${book.title}">Tên sách</span>
  </nav>

  <article>
    <header>
      <h1 th:text="${book.title}">Tên sách</h1>
      <p>
        Tình trạng:
        <span th:text="${book.statusLabel}">Đang lưu hành</span>
      </p>
    </header>

    <dl>
      <dt>Tác giả</dt>
      <dd th:text="${book.authorName}">Tên tác giả</dd>

      <dt>ISBN</dt>
      <dd th:text="${book.isbn}">ISBN</dd>

      <dt>Ngày xuất bản</dt>
      <dd th:text="${book.publishedDateLabel}">01/01/2025</dd>
    </dl>

    <section aria-labelledby="description-heading">
      <h2 id="description-heading">Mô tả</h2>
      <p th:text="${book.description}">Mô tả sách</p>
    </section>

    <a th:href="@{/books/{id}/edit(id=${book.id})}">Chỉnh sửa</a>
  </article>
</main>
~~~

`<dl>`, `<dt>` và `<dd>` thể hiện quan hệ giữa tên thuộc tính và giá trị. Liên kết quay lại danh sách giúp người dùng giữ được định hướng. Nếu cần quay lại đúng bộ lọc và trang trước đó, ứng dụng có thể lưu các tham số điều hướng trong URL hoặc cung cấp một liên kết trở về có chủ đích.

Không phải người dùng nào cũng được phép chỉnh sửa. Controller hoặc tầng phân quyền phải quyết định quyền đó; View chỉ nhận một cờ hoặc danh sách hành động được phép để hiển thị. Việc ẩn liên kết chỉnh sửa không thay thế kiểm tra quyền ở endpoint cập nhật.

### Khi không tìm thấy bản ghi

Yêu cầu chi tiết cho một ID không tồn tại thường phải được xử lý như tài nguyên không tìm thấy, ví dụ HTTP `404 Not Found`, kèm trang thông báo phù hợp. Không nên hiển thị một trang chi tiết với các trường rỗng vì điều đó khiến người dùng nghĩ bản ghi tồn tại nhưng chưa có dữ liệu.

Tương tự, nếu người dùng không có quyền xem tài nguyên, ứng dụng phải áp dụng chính sách truy cập nhất quán và trả mã phản hồi phù hợp. Trạng thái không tìm thấy, không được phép và lỗi hệ thống là những tình huống khác nhau, cần được phân biệt ở tầng xử lý request.

## 5. Thiết kế trạng thái rỗng

**Trạng thái rỗng (empty state)** là cách View phản hồi khi một vùng nội dung hợp lệ hiện không có mục nào để trình bày. Đây là một phần của thiết kế giao diện, không phải một lỗi mặc định.

Một trạng thái rỗng hữu ích thường có ba phần:

1. **Ngữ cảnh:** cho biết vùng dữ liệu nào đang rỗng.
2. **Giải thích:** nêu lý do phù hợp với tình huống.
3. **Hành động tiếp theo:** gợi ý tạo mục mới, xóa bộ lọc hoặc thử từ khóa khác khi có thể.

### Phân biệt các trường hợp rỗng

| Trường hợp | Ý nghĩa | Cách phản hồi phù hợp |
|---|---|---|
| Chưa có dữ liệu ban đầu | Hệ thống chưa có bản ghi nào | Giải thích danh sách đang trống và đưa ra hành động tạo mới nếu người dùng có quyền |
| Không có kết quả tìm kiếm | Có dữ liệu nói chung nhưng không mục nào khớp điều kiện hiện tại | Hiển thị từ khóa/bộ lọc đang áp dụng và gợi ý đổi từ khóa hoặc xóa bộ lọc |
| Bộ lọc trả về rỗng | Dữ liệu tồn tại nhưng không thuộc nhóm được chọn | Nêu rõ bộ lọc đang giới hạn kết quả và cho phép đặt lại |
| Trang hiện tại không có mục | Tham số phân trang không tương ứng với trang hợp lệ | Điều chỉnh trang ở Controller hoặc đưa người dùng về trang hợp lệ |
| Không tìm thấy chi tiết | ID không đại diện cho tài nguyên hiện có | Trả 404 và hiển thị trang không tìm thấy |
| Không tải được dữ liệu | Truy vấn hoặc dịch vụ gặp lỗi | Hiển thị thông báo lỗi phù hợp, có hướng thử lại nếu thích hợp |

Không nên dùng cùng một câu “Không có dữ liệu” cho tất cả trường hợp. Người dùng cần biết họ chưa tạo dữ liệu, tìm kiếm không khớp hay hệ thống đang gặp lỗi. Một lỗi truy vấn không được biến thành collection rỗng vì như vậy lỗi bị che giấu và người dùng có thể hiểu sai trạng thái dữ liệu.

### Ví dụ hai trạng thái rỗng trong Thymeleaf

~~~html
<section th:if="${#lists.isEmpty(books) and !filtersApplied}"
         aria-labelledby="empty-library-heading">
  <h2 id="empty-library-heading">Thư viện chưa có sách</h2>
  <p>Bạn có thể thêm cuốn sách đầu tiên vào danh mục.</p>
  <a th:if="${canCreateBook}" th:href="@{/books/new}">Thêm sách</a>
</section>

<section th:if="${#lists.isEmpty(books) and filtersApplied}"
         aria-labelledby="no-results-heading">
  <h2 id="no-results-heading">Không tìm thấy sách phù hợp</h2>
  <p>Hãy thử từ khóa khác hoặc xóa bộ lọc hiện tại.</p>
  <a th:href="@{/books}">Xóa bộ lọc</a>
</section>
~~~

`filtersApplied` là dữ liệu View Model do Controller chuẩn bị dựa trên điều kiện tìm kiếm/lọc đã xác nhận. `canCreateBook` phản ánh quyền được xác định ở phía máy chủ. View dùng các giá trị này để chọn nội dung phù hợp, không tự suy luận quyền hoặc truy vấn dữ liệu.

Trong ứng dụng thực tế, nên kiểm tra trạng thái rỗng theo tổng số kết quả và trang hiện tại. Một trang không có mục vì người dùng đang ở trang 99 không đồng nghĩa danh mục hoàn toàn trống. Hãy để Service/Controller chuẩn hóa trang hoặc cung cấp trạng thái riêng cho trường hợp tham số trang không hợp lệ.

## 6. Trạng thái hiển thị và cách diễn đạt

Trạng thái như “Đang lưu hành”, “Đã mượn”, “Ngừng sử dụng” giúp người dùng nhận biết tình hình của một đối tượng. View nên hiển thị nhãn chữ rõ ràng. Màu sắc có thể hỗ trợ nhận biết nhưng không được là tín hiệu duy nhất, vì người dùng có thể không phân biệt được màu hoặc sử dụng trình đọc màn hình.

Ví dụ, một nhãn trạng thái có thể gồm cả văn bản và kiểu trình bày:

~~~html
<span class="status status--available">Đang lưu hành</span>
<span class="status status--borrowed">Đã mượn</span>
~~~

Class CSS nên được chọn từ các giá trị do ứng dụng kiểm soát, dựa trên enum hoặc mã trạng thái đã biết. Không đưa trực tiếp một chuỗi tùy ý từ người dùng vào thuộc tính class hoặc style. Nội dung nhãn nên được chuyển thành ngôn ngữ thân thiện ở tầng trình bày.

Thông báo cần ngắn, cụ thể và hướng hành động. Ví dụ “Không tìm thấy sách phù hợp với từ khóa ‘Java nâng cao’” hữu ích hơn “Không có dữ liệu”. Tránh thông báo kỹ thuật như tên bảng, câu SQL hoặc stack trace.

## 7. Khả năng truy cập và thiết kế đáp ứng

View cần hoạt động tốt với bàn phím, trình đọc màn hình, màn hình nhỏ và các mức phóng to khác nhau.

**Dùng cấu trúc HTML có ngữ nghĩa.** Mỗi trang nên có tiêu đề chính `<h1>`, các phần nội dung có heading theo thứ bậc, bảng có `<caption>` và tiêu đề cột dùng `<th scope="col">`. Điều này giúp công nghệ hỗ trợ hiểu cấu trúc nội dung.

**Gắn nhãn cho điều khiển.** Ô tìm kiếm cần `<label>` liên kết bằng `for` và `id`. Nút nên có nội dung mô tả hành động. Liên kết cần có văn bản đủ rõ khi đọc độc lập, tránh nhiều liên kết “Xem thêm” không có ngữ cảnh.

**Không chỉ dùng màu sắc.** Nhãn trạng thái cần văn bản; lỗi cần thông điệp rõ ràng và được liên kết với trường liên quan nếu là biểu mẫu. Trạng thái trang hiện tại có thể dùng `aria-current="page"`.

**Hỗ trợ bàn phím và tiêu điểm.** Các liên kết, nút và điều khiển phải có thể truy cập bằng bàn phím; thứ tự focus cần hợp lý và dấu focus không nên bị loại bỏ nếu không có thay thế dễ nhận biết.

**Thiết kế cho màn hình nhỏ.** Bảng rộng có thể cần vùng cuộn ngang có chủ đích hoặc chuyển sang cách trình bày dạng thẻ ở kích thước nhỏ. Không làm mất nhãn thuộc tính khi chuyển bố cục. Nội dung quan trọng và thao tác chính cần dễ tìm mà không phải phóng to hoặc cuộn theo nhiều hướng.

Nếu danh sách được cập nhật bất đồng bộ sau thao tác lọc, có thể thông báo kết quả mới qua vùng trạng thái phù hợp như `aria-live="polite"`. Chỉ dùng vùng live khi nội dung thực sự thay đổi động; không cần thêm thuộc tính ARIA khi HTML ngữ nghĩa đã cung cấp đầy đủ thông tin.

## 8. An toàn khi hiển thị dữ liệu

Dữ liệu hiển thị có thể bắt nguồn từ người dùng, tệp nhập hoặc hệ thống bên ngoài. View phải mã hóa đầu ra theo ngữ cảnh để nội dung được hiểu là dữ liệu, không bị diễn giải thành mã thực thi.

Với Thymeleaf, `th:text` là lựa chọn phù hợp để hiển thị văn bản thông thường vì nó escape nội dung. Tránh dùng `th:utext` cho nội dung không đáng tin cậy; thuộc tính này đưa HTML không escape vào trang và có thể tạo lỗ hổng Cross-Site Scripting (XSS). Nếu nghiệp vụ thật sự cần nội dung HTML định dạng, phải dùng quy trình làm sạch HTML bằng thư viện đáng tin cậy và giới hạn các thẻ/thuộc tính được phép.

View chỉ nên nhận dữ liệu cần trình bày. Không đưa mật khẩu, token, thông tin cá nhân không liên quan hoặc các trường nội bộ vào HTML, kể cả khi chúng bị ẩn bằng CSS. Dữ liệu nằm trong source HTML vẫn có thể được người dùng xem.

Liên kết hành động và nút chỉ hỗ trợ trải nghiệm. Máy chủ vẫn phải xác thực, kiểm tra quyền trên tài nguyên và xác thực dữ liệu ở mỗi request. Người dùng có thể tự tạo URL hoặc gửi request mà không cần bấm vào liên kết trên View.

## 9. Kiểm thử View

Kiểm thử nên xác nhận View thể hiện đúng trạng thái và hợp đồng dữ liệu, không chỉ kiểm tra template có render mà không phát sinh lỗi.

| Trường hợp | Điều cần xác minh |
|---|---|
| Danh sách có dữ liệu | Các cột hoặc mục cần thiết xuất hiện; liên kết chi tiết chứa đúng ID |
| Danh sách rỗng ban đầu | Hiển thị hướng dẫn tạo mới khi người dùng có quyền |
| Tìm kiếm không có kết quả | Hiển thị thông điệp tìm kiếm và đường xóa bộ lọc |
| Có bộ lọc và phân trang | Các tham số hiện tại được giữ khi chuyển trang |
| Chi tiết hợp lệ | Hiển thị đúng dữ liệu và hành động được phép |
| Chi tiết không tồn tại | Trả response 404 và trang thông báo phù hợp |
| Nội dung có ký tự đặc biệt | Văn bản được escape, không thực thi HTML/JavaScript do người dùng cung cấp |
| Trình bày trên màn hình nhỏ | Nội dung và thao tác chính vẫn có thể sử dụng |

Unit test cho Service xác minh kết quả truy vấn và quy tắc nghiệp vụ. Kiểm thử Controller xác minh dữ liệu được đưa vào model và status HTTP phù hợp. Kiểm thử template hoặc integration test xác minh HTML cuối cùng có nội dung, liên kết và trạng thái mong đợi. Kiểm thử truy cập có thể bổ sung kiểm tra nhãn, thứ bậc heading, điều hướng bàn phím và tương phản.

## 10. Những lỗi thiết kế thường gặp

- **Danh sách rỗng nhưng không giải thích:** người dùng không biết cần tạo dữ liệu hay thay đổi bộ lọc.
- **Dùng trạng thái rỗng để che lỗi:** truy vấn thất bại bị biến thành danh sách rỗng, khiến người dùng hiểu nhầm dữ liệu không tồn tại.
- **Hiển thị toàn bộ Entity:** View phụ thuộc vào cấu trúc persistence và có thể làm lộ trường không cần thiết.
- **Đặt nghiệp vụ trong template:** các điều kiện phức tạp trong View khó kiểm thử và có thể không được áp dụng ở những luồng khác.
- **Không giữ bộ lọc khi phân trang:** người dùng chuyển trang và mất ngữ cảnh tìm kiếm.
- **Chỉ dùng màu để biểu diễn trạng thái:** thông tin không còn rõ ràng với người dùng không nhận biết được màu.
- **Dùng HTML không escape:** dữ liệu đầu vào có thể trở thành mã thực thi trong trình duyệt.
- **Ẩn hành động nhưng không kiểm tra quyền:** endpoint vẫn có thể bị gọi trực tiếp nếu máy chủ không kiểm tra quyền.

## 11. Kết luận

View danh sách giúp người dùng duyệt và tìm các đối tượng; View chi tiết giúp hiểu một đối tượng cụ thể; trạng thái rỗng giải thích những tình huống hợp lệ khi không có nội dung để hiển thị. Ba dạng trình bày này cần dùng chung một hợp đồng dữ liệu rõ ràng từ Controller, phân biệt dữ liệu rỗng với lỗi, và cung cấp đường điều hướng phù hợp.

Khi thiết kế View trong MVC, hãy xác định dữ liệu nào người dùng cần thấy, trạng thái nào có thể xảy ra, hành động nào được phép, và cách trình bày vẫn dễ hiểu, an toàn, truy cập được trên nhiều thiết bị. View tốt phản ánh chính xác kết quả nghiệp vụ mà không tự gánh trách nhiệm của Model hoặc Controller.
