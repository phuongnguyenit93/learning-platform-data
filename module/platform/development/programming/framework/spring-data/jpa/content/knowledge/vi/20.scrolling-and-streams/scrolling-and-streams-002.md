# Mô hình Window, ScrollPosition và truy vấn hỗ trợ scrolling

Spring Data cung cấp Scroll API để đọc một tập kết quả lớn theo từng phần nhỏ. Thay vì tải toàn bộ dữ liệu vào bộ nhớ hoặc yêu cầu database bỏ qua một offset ngày càng lớn, ứng dụng lấy một Window<T>, xử lý các phần tử trong cửa sổ đó rồi dùng ScrollPosition để yêu cầu cửa sổ tiếp theo.

Ba khái niệm cần nắm là:

- **Window<T>:** một nhóm kết quả giới hạn, có thông tin để tiếp tục cuộn.
- **ScrollPosition:** vị trí dùng để bắt đầu hoặc tiếp tục đọc kết quả.
- **Scrolling query:** phương thức Repository có khả năng nhận ScrollPosition và trả về Window<T>.

Spring Data hỗ trợ cuộn theo offset và theo keyset. Offset dễ hiểu, gần với phân trang; keyset dùng các giá trị sắp xếp của phần tử cuối cùng để tiếp tục truy vấn và thường phù hợp hơn với tập dữ liệu lớn. Việc chọn cách cuộn, thứ tự sắp xếp và loại query được hỗ trợ ảnh hưởng trực tiếp đến tính đúng đắn và hiệu năng.

## 1. Scrolling giải quyết vấn đề gì?

Giả sử một bảng có vài triệu bản ghi và một tác vụ cần xử lý tất cả bản ghi theo từng lô 500 phần tử. Nếu gọi findAll(), toàn bộ kết quả có thể được tải vào bộ nhớ, gây áp lực heap và garbage collection.

Có thể dùng Pageable để lấy từng Page, nhưng Page thường cần tổng số phần tử để cung cấp totalElements và totalPages. Count query có thể tốn kém, trong khi tác vụ batch chỉ cần lấy dữ liệu tiếp theo.

Scrolling cung cấp một cách đọc theo từng Window mà không yêu cầu tổng số kết quả. Mỗi lần truy vấn chỉ lấy một phần hữu hạn, sau đó trả về vị trí có thể dùng để tiếp tục.

| Cách đọc | Đặc điểm |
|---|---|
| findAll() | Có thể tải toàn bộ kết quả vào bộ nhớ |
| Page<T> | Có nội dung trang và tổng số; có thể cần count query |
| Slice<T> | Có nội dung và thông tin còn trang tiếp theo, không cần tổng số |
| Window<T> | Có một cửa sổ kết quả cùng vị trí để tiếp tục cuộn |
| Stream<T> | Trả luồng kết quả; gắn với tài nguyên truy vấn và cần đóng đúng cách |

Window không phải một Stream JDBC và không tự bảo đảm rằng database/driver không buffer dữ liệu. Nó là abstraction để lấy kết quả theo từng cửa sổ có giới hạn. Ứng dụng cần xử lý từng Window rồi yêu cầu Window kế tiếp.

## 2. Window<T> là gì?

Window<T> đại diện cho một phần kết quả của truy vấn. T là kiểu dữ liệu của từng phần tử, thường là Entity hoặc projection được query trả về.

Một Window cung cấp các thao tác quan trọng:

- Lặp qua các phần tử trong cửa sổ.
- Kiểm tra cửa sổ có rỗng hay không.
- Kiểm tra còn kết quả tiếp theo hay không.
- Lấy ScrollPosition tại một phần tử bằng positionAt(index).
- Dùng vị trí của phần tử cuối để yêu cầu cửa sổ kế tiếp.

Ví dụ chữ ký Repository:

~~~java
Window<Product> findFirst100ByActiveTrueOrderByIdAsc(
        ScrollPosition position
);
~~~

Phương thức này trả về tối đa 100 Product active, sắp xếp theo ID tăng dần, bắt đầu từ vị trí được truyền vào.

Window không cung cấp totalElements hoặc totalPages như Page. Vì vậy, nếu giao diện cần hiển thị tổng số bản ghi hoặc số trang chính xác, Page có thể phù hợp hơn. Nếu tác vụ chỉ cần tiếp tục xử lý cho đến khi hết dữ liệu, Window thường phù hợp hơn.

## 3. ScrollPosition biểu diễn vị trí như thế nào?

ScrollPosition xác định điểm trong toàn bộ kết quả truy vấn để ứng dụng có thể bắt đầu hoặc tiếp tục đọc. Có hai kiểu vị trí chính:

- OffsetScrollPosition: lưu vị trí theo số lượng phần tử đã bỏ qua.
- KeysetScrollPosition: lưu các giá trị khóa sắp xếp của phần tử cuối cùng đã đọc.

Các phương thức khởi tạo phổ biến:

~~~java
ScrollPosition.offset()
ScrollPosition.keyset()
~~~

Hai phương thức trên tạo vị trí ban đầu cho từng kiểu cuộn. Sau khi nhận một Window, ứng dụng lấy vị trí của phần tử đã xử lý bằng:

~~~java
ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);
~~~

Vị trí được dùng theo quy tắc **exclusive**: truy vấn tiếp theo bắt đầu sau phần tử tại vị trí đã truyền. Vì vậy, hãy lấy vị trí của phần tử cuối cùng trong Window hiện tại để không đọc lại phần tử cuối.

Không tự cộng hoặc trừ index nếu đã dùng positionAt(). API tạo ScrollPosition phù hợp với kiểu cuộn đang sử dụng.

## 4. Truy vấn Repository hỗ trợ scrolling

Spring Data JPA hỗ trợ Scroll API với các loại query method phù hợp, đặc biệt là derived query methods. Một phương thức scrolling thường có:

- Kiểu trả về Window<T>.
- Tham số ScrollPosition để xác định điểm bắt đầu.
- Giới hạn kết quả bằng First hoặc Top, hoặc giới hạn được hỗ trợ theo API query.
- Thứ tự sắp xếp ổn định.

Ví dụ:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Window<Product> findFirst100ByActiveTrueOrderByIdAsc(
            ScrollPosition position
    );
}
~~~

Tên phương thức thể hiện:
- find: truy vấn dữ liệu.
- First100: giới hạn mỗi Window tối đa 100 kết quả.
- ByActiveTrue: chỉ lấy Product đang active.
- OrderByIdAsc: sắp xếp ID tăng dần.

Khi gọi phương thức lần đầu, truyền vị trí ban đầu. Những lần sau, truyền vị trí lấy từ Window trước đó.

Ví dụ này dùng derived query. Hãy bảo đảm tên thuộc tính active và id đúng với Entity thực tế.

## 5. Cuộn thủ công qua từng Window

Có thể điều khiển vòng lặp trực tiếp để hiểu rõ cách ScrollPosition được cập nhật.

~~~java
ScrollPosition position = ScrollPosition.offset();

Window<Product> window =
        productRepository.findFirst100ByActiveTrueOrderByIdAsc(position);

while (!window.isEmpty()) {
    for (Product product : window) {
        process(product);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);

    window = productRepository
            .findFirst100ByActiveTrueOrderByIdAsc(position);
}
~~~

Trình tự hoạt động:

1. Bắt đầu với ScrollPosition ban đầu.
2. Repository trả về Window đầu tiên.
3. Ứng dụng xử lý tất cả Product trong Window.
4. Nếu không còn phần tử tiếp theo, vòng lặp kết thúc.
5. Nếu còn dữ liệu, lấy vị trí của phần tử cuối cùng.
6. Gọi lại Repository với vị trí mới để nhận Window tiếp theo.

Điều quan trọng là chỉ chuyển vị trí sau khi đã xử lý xong Window hiện tại. Nếu chuyển vị trí từ phần tử giữa cửa sổ, các phần tử còn lại có thể bị bỏ qua.

Nếu xử lý từng phần tử có thể thất bại, cần thiết kế cách lưu checkpoint và retry theo nghiệp vụ. ScrollPosition không tự lưu tiến độ lâu dài cho ứng dụng.

## 6. WindowIterator giúp đơn giản hóa vòng lặp

WindowIterator là tiện ích của Spring Data Commons để duyệt liên tục qua nhiều Window. Nó tự lấy vị trí tiếp theo, giúp code không phải tự viết điều kiện kiểm tra cửa sổ và cập nhật ScrollPosition.

Ví dụ:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Product> iterator =
        WindowIterator.of(position ->
                productRepository
                    .findFirst100ByActiveTrueOrderByIdAsc(position)
        ).startingAt(ScrollPosition.offset());

while (iterator.hasNext()) {
    Product product = iterator.next();
    process(product);
}
~~~

Giải thích:

- WindowIterator.of(...) nhận một hàm truy vấn, trong đó Spring Data truyền ScrollPosition cho mỗi lần lấy Window.
- startingAt(...) xác định vị trí bắt đầu.
- hasNext() kiểm tra còn phần tử để đọc.
- next() lấy phần tử kế tiếp từ các Window.

WindowIterator thuận tiện khi muốn xử lý từng Entity tuần tự. Nếu cần xử lý theo lô, lưu checkpoint, ghi log theo từng Window hoặc kiểm soát transaction theo lô, vòng lặp thủ công có thể dễ tùy chỉnh hơn.

Không nên gọi iterator nhiều lần cho cùng một tác vụ nếu điều đó khiến query bị chạy lại ngoài ý muốn. Tạo iterator một lần và tiêu thụ nó theo vòng đời của công việc.

## 7. Offset-based scrolling

Offset scrolling dùng một số nguyên thể hiện vị trí trong kết quả đã sắp xếp. Database được yêu cầu bỏ qua một số dòng rồi trả về phần tiếp theo.

Ví dụ:

~~~java
Window<Product> findFirst100ByActiveTrueOrderByIdAsc(
        ScrollPosition position
);
~~~

Bắt đầu:

~~~java
Window<Product> first =
        productRepository.findFirst100ByActiveTrueOrderByIdAsc(
                ScrollPosition.offset()
        );
~~~

Offset đơn giản vì gần với LIMIT/OFFSET trong SQL. Tuy nhiên, khi offset tăng rất lớn, database thường phải xác định và bỏ qua nhiều dòng trước khi trả về phần kết quả cần thiết. Vì vậy, các cửa sổ sâu có thể ngày càng chậm.

### Phân biệt offset() và offset(0)

Hai giá trị này không có cùng ý nghĩa:

- ScrollPosition.offset() biểu thị bắt đầu từ đầu truy vấn, chưa chỉ đến một phần tử cụ thể.
- ScrollPosition.offset(0) chỉ đến phần tử ở vị trí 0.

ScrollPosition là exclusive. Vì vậy, nếu truyền offset(0), truy vấn tiếp theo bắt đầu sau phần tử đầu tiên và có thể bỏ qua phần tử đó.

Để lấy kết quả từ đầu, dùng:

~~~java
ScrollPosition.offset()
~~~

Không dùng offset(0) làm vị trí khởi đầu nếu muốn nhận cả phần tử đầu tiên.

## 8. Keyset-based scrolling

Keyset scrolling tiếp tục truy vấn dựa trên các giá trị sắp xếp của phần tử cuối cùng trong Window hiện tại, thay vì đếm số dòng cần bỏ qua.

Giả sử kết quả được sắp xếp:

~~~sql
ORDER BY created_at ASC, id ASC
~~~

Sau khi đọc phần tử cuối có created_at = thời điểm T và id = 500, truy vấn tiếp theo có thể được viết về mặt logic như:

~~~sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at ASC, id ASC
LIMIT 100
~~~

Đây là điều kiện keyset theo thứ tự từ điển (lexicographic). Spring Data xây dựng điều kiện tiếp tục dựa trên các giá trị khóa được lưu trong ScrollPosition.

Keyset giúp database tìm các bản ghi sau vị trí đã đọc thông qua index phù hợp, tránh chi phí bỏ qua một offset rất lớn. Đây là lựa chọn đáng cân nhắc khi đọc tuần tự một tập dữ liệu lớn.

## 9. Bắt đầu keyset scrolling

Ví dụ Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Window<Product>
    findFirst100ByActiveTrueOrderByCreatedAtAscIdAsc(
            ScrollPosition position
    );
}
~~~

Bắt đầu từ đầu:

~~~java
Window<Product> window =
        productRepository
            .findFirst100ByActiveTrueOrderByCreatedAtAscIdAsc(
                ScrollPosition.keyset()
            );
~~~

Hoặc dùng WindowIterator:

~~~java
WindowIterator<Product> products =
        WindowIterator.of(position ->
            productRepository
                .findFirst100ByActiveTrueOrderByCreatedAtAscIdAsc(position)
        ).startingAt(ScrollPosition.keyset());

while (products.hasNext()) {
    process(products.next());
}
~~~

Thứ tự phải ổn định và xác định rõ. Nếu nhiều Product có cùng createdAt, ID cung cấp tiêu chí phụ để xác định thứ tự duy nhất. Spring Data keyset mechanism cũng bổ sung khóa chính (hoặc các thành phần còn lại của khóa chính ghép) để bảo đảm vị trí có thể xác định duy nhất.

Dù vậy, khai báo tie-breaker rõ ràng trong sort thường giúp người đọc hiểu thứ tự và dễ thiết kế index hơn.

## 10. Điều kiện để keyset scrolling hoạt động đúng

Keyset cần các thuộc tính sắp xếp có giá trị xác định:

- Các thuộc tính trong sort nên không-null.
- Kết quả query phải trả về các thuộc tính dùng để sắp xếp.
- Khóa chính phải có mặt để phân biệt các phần tử có cùng giá trị sort.
- Thứ tự phải ổn định trong suốt quá trình cuộn.
- Database nên có index phù hợp với các điều kiện lọc và thứ tự sắp xếp.

Spring Data cần các giá trị sort của phần tử cuối để tạo ScrollPosition tiếp theo. Nếu projection không chứa thuộc tính sắp xếp, framework không thể trích xuất đầy đủ keyset và có thể phát sinh lỗi hoặc không thể tiếp tục cuộn.

Ví dụ projection cần giữ các trường sort:

~~~java
public interface ProductScrollView {
    Long getId();
    Instant getCreatedAt();
    String getName();
}
~~~

Nếu truy vấn sắp xếp theo createdAt và id, projection phải chứa cả createdAt và id. Có thể không hiển thị các trường này cho người dùng, nhưng chúng cần có trong kết quả để tạo vị trí keyset.

### Tránh thuộc tính sort nullable

Keyset filtering dựa trên các phép so sánh như lớn hơn, nhỏ hơn và bằng. NULL có semantics riêng trong SQL và thứ tự NULL có thể khác theo database. Vì vậy, Spring Data yêu cầu keyset properties không-nullable để tránh kết quả tiếp tục không xác định.

Nếu trường nghiệp vụ có thể null, hãy chọn trường sort khác không-null hoặc chuẩn hóa dữ liệu và mapping theo một quy tắc rõ ràng trước khi dùng keyset.

## 11. Thiết kế index cho keyset

Keyset đạt hiệu quả tốt khi database có index phù hợp với thứ tự sắp xếp và điều kiện lọc.

Ví dụ truy vấn:

~~~sql
WHERE active = true
ORDER BY created_at ASC, id ASC
LIMIT 100
~~~

Có thể xem xét index kết hợp:

~~~sql
CREATE INDEX idx_products_active_created_id
ON products (active, created_at, id);
~~~

Index này minh họa thứ tự cột phù hợp với điều kiện lọc active và các cột sắp xếp. Cấu trúc index tối ưu thực tế còn phụ thuộc database, độ chọn lọc, điều kiện lọc khác và workload ghi.

Nếu query luôn lọc tenant_id trước, index có thể cần bắt đầu bằng tenant_id. Nếu sắp xếp theo hướng giảm dần hoặc có điều kiện khác, cần kiểm tra khả năng sử dụng index của database.

Dùng EXPLAIN hoặc EXPLAIN ANALYZE để kiểm tra:
- Có dùng index dự kiến không?
- Số dòng cần đọc trước khi trả Window là bao nhiêu?
- Có bước sort lớn không?
- Chi phí của Window đầu và các Window sâu có ổn định không?

Không tạo index chỉ dựa trên tên phương thức. Đo trên dữ liệu và database gần với production.

## 12. Truy vấn nào hỗ trợ Scroll API trong Spring Data JPA?

Theo tài liệu Spring Data JPA hiện hành, Scroll API có thể dùng với:

- **Query methods:** các query method được hỗ trợ, ví dụ derived query nhận ScrollPosition và trả Window<T>.
- **Query by Example (QBE):** có thể dùng fluent API và terminal operation scroll(position).
- **Querydsl:** có thể dùng API scrolling khi repository hỗ trợ Querydsl.

Ví dụ derived query đã trình bày ở trên. Với Query by Example, ý tưởng là gọi fluent query:

~~~java
Window<Customer> window = customerRepository.findBy(
        Example.of(probe),
        query -> query.scroll(ScrollPosition.offset())
);
~~~

Cú pháp cụ thể phụ thuộc kiểu repository và phiên bản Spring Data Commons/JPA. Terminal operation scroll() trả Window<T> và nhận ScrollPosition.

### Giới hạn với @Query và string-based query

Tài liệu Spring Data JPA hiện hành ghi rõ scrolling với string-based query methods chưa được hỗ trợ. Điều này bao gồm phương thức khai báo query bằng chuỗi như @Query; stored @Procedure query methods cũng không hỗ trợ Scroll API theo tài liệu đó.

Vì vậy, không nên mặc định có thể viết:

~~~java
@Query("select p from Product p where p.active = true")
Window<Product> findActiveProducts(ScrollPosition position);
~~~

rồi mong mọi phiên bản Spring Data JPA tự xử lý scrolling. Hãy kiểm tra tài liệu đúng phiên bản dependency. Nếu cần điều kiện phức tạp, có thể cân nhắc derived query phù hợp, Query by Example, Querydsl hoặc custom repository dùng Criteria API/EntityManager và tự quản lý giới hạn, thứ tự, cursor.

Các khả năng scrolling thay đổi theo phiên bản Spring Data. Scroll API được giới thiệu trong dòng Spring Data 3.1; hãy kiểm tra phiên bản Spring Boot BOM và Spring Data JPA thực tế của dự án trước khi áp dụng.

## 13. Scrolling với projection

Có thể trả về projection thay vì Entity đầy đủ để chỉ tải các trường cần thiết. Điều này hữu ích khi xử lý dữ liệu lớn mà tác vụ chỉ cần một vài thuộc tính.

Ví dụ:

~~~java
public interface ProductExportRow {
    Long getId();
    Instant getCreatedAt();
    String getName();
}
~~~

Một query method có thể trả Window<ProductExportRow> nếu kiểu query và projection được hỗ trợ:

~~~java
Window<ProductExportRow>
findFirst200ByActiveTrueOrderByCreatedAtAscIdAsc(
        ScrollPosition position
);
~~~

Với keyset scrolling, cần đưa tất cả thuộc tính sort vào projection. Trong ví dụ, createdAt và id đều có mặt. Nếu chỉ trả name mà bỏ createdAt hoặc ID, framework có thể không tạo được keyset tiếp theo.

Projection giúp giảm lượng cột đọc và giảm chi phí hydrate Entity, nhưng vẫn cần kiểm tra SQL thực tế và mapping projection trên provider đang dùng.

## 14. Scrolling và dữ liệu thay đổi đồng thời

ScrollPosition không tự tạo một snapshot bất biến của toàn bộ kết quả. Nếu dữ liệu thay đổi trong khi ứng dụng đang cuộn, kết quả có thể bị ảnh hưởng.

### Offset scrolling

Nếu có bản ghi mới được chèn trước offset hiện tại, vị trí số dòng có thể dịch chuyển. Ứng dụng có thể đọc lặp một số bản ghi hoặc bỏ qua bản ghi khác. Xóa dữ liệu trước vị trí cũng có thể làm offset thay đổi.

### Keyset scrolling

Keyset ít phụ thuộc vào số dòng đã bỏ qua, nhưng vẫn có thể bị ảnh hưởng nếu:
- Giá trị sort của bản ghi thay đổi trong khi cuộn.
- Bản ghi được thêm vào trước hoặc sau keyset hiện tại.
- Bản ghi bị xóa trước khi được đọc.
- Điều kiện lọc thay đổi theo thời gian.

Để giảm rủi ro:
- Dùng các trường sort ổn định, ít thay đổi.
- Dùng ID làm tie-breaker.
- Nếu nghiệp vụ cần snapshot nhất quán, xác định transaction isolation hoặc chiến lược snapshot phù hợp.
- Với export/batch dài, cân nhắc giới hạn tập dữ liệu theo thời điểm hoặc khóa mốc (high-water mark).
- Thiết kế xử lý idempotent nếu có retry.

Không giả định scrolling tự bảo đảm exactly-once processing khi dữ liệu đang thay đổi hoặc tiến trình bị dừng giữa chừng.

## 15. Phân biệt scrolling với Stream<T>

Tên gọi scrolling dễ khiến người đọc nhầm với Java Stream. Hai abstraction có mục đích và vòng đời khác nhau.

| Tiêu chí | Window<T> scrolling | Stream<T> |
|---|---|---|
| Đơn vị đọc | Một cửa sổ giới hạn | Một luồng phần tử |
| Cách tiếp tục | ScrollPosition | Tiếp tục tiêu thụ stream |
| Quản lý tài nguyên | Mỗi lần lấy Window là một lần query | Có thể giữ tài nguyên JDBC/cursor mở trong lúc stream |
| Đóng tài nguyên | Window là tập kết quả đã lấy | Stream phải được đóng |
| Dùng cho | Phân đoạn kết quả và tiếp tục bằng cursor | Xử lý luồng trong phạm vi transaction/resource |

Ví dụ dùng Stream:

~~~java
@Transactional(readOnly = true)
public void processAllProducts() {
    try (Stream<Product> products = repository.streamAllByActiveTrue()) {
        products.forEach(this::process);
    }
}
~~~

Phương thức repository cần được khai báo trả Stream<Product> và provider phải hỗ trợ phù hợp. Stream thường gắn với tài nguyên persistence/JDBC; cần đóng bằng try-with-resources và tiêu thụ trong transaction phù hợp.

Window scrolling lấy dữ liệu thành từng nhóm riêng. Sau khi xử lý xong một Window, ứng dụng yêu cầu Window tiếp theo. Đây là lựa chọn phù hợp khi cần checkpoint rõ ràng hoặc kiểm soát transaction theo từng batch.

Không coi Window là cursor JDBC luôn mở và cũng không coi Stream là thay thế hoàn toàn cho keyset pagination.

## 16. Chọn offset hay keyset?

| Tiêu chí | Offset scrolling | Keyset scrolling |
|---|---|---|
| Vị trí tiếp tục | Số dòng đã bỏ qua | Giá trị các trường sort của dòng cuối |
| Độ đơn giản | Dễ hiểu và triển khai | Cần sort ổn định và keyset hợp lệ |
| Cửa sổ sâu | Có thể chậm do offset lớn | Thường ổn định hơn khi có index phù hợp |
| Yêu cầu index | Có lợi nhưng không phải điều kiện cốt lõi | Rất quan trọng để đạt hiệu quả |
| Thuộc tính nullable | Offset không có ràng buộc keyset tương tự | Sort properties cần không-null |
| Projection | Ít ràng buộc hơn | Phải chứa các trường sort và ID |
| Thay đổi dữ liệu đồng thời | Offset dễ bị dịch chuyển | Ít nhạy với chèn/xóa trước vị trí, nhưng sort key mutable vẫn có rủi ro |

Chọn offset khi:
- Tập dữ liệu không quá lớn.
- Cần cách triển khai đơn giản.
- Offset không tăng đến mức quá sâu.
- Thứ tự và dữ liệu ít thay đổi trong thời gian đọc.

Chọn keyset khi:
- Cần cuộn tuần tự qua lượng dữ liệu lớn.
- Có khóa sắp xếp ổn định, không-null.
- Có thể tạo index phù hợp.
- Không cần nhảy đến một trang bất kỳ theo số thứ tự.

Nếu cần điều hướng tùy ý đến trang 1000, offset có thể phù hợp về mặt trải nghiệm, dù chi phí có thể cao. Keyset phù hợp hơn với luồng “tiếp theo” và xử lý tuần tự.

## 17. Kiểm thử scrolling query

Nên kiểm tra các trường hợp sau:

1. Window đầu tiên bắt đầu đúng từ phần tử đầu tiên.
2. Window tiếp theo bắt đầu sau phần tử cuối của Window trước.
3. Không có phần tử nào bị lặp hoặc bỏ sót khi dữ liệu ổn định.
4. Window cuối có hasNext() bằng false.
5. Truy vấn không có dữ liệu trả Window rỗng.
6. Offset ban đầu dùng ScrollPosition.offset(), không dùng offset(0) nếu muốn lấy phần tử đầu.
7. Keyset sort có giá trị không-null và thứ tự xác định.
8. Projection chứa đầy đủ sort properties và ID.
9. Query method đang dùng được hỗ trợ bởi phiên bản Spring Data JPA.
10. Index và execution plan được kiểm tra trên database mục tiêu.

Ví dụ kiểm thử khái niệm với offset:

~~~java
@Test
void scrollingReadsAllProductsWithoutDuplicates() {
    List<Long> ids = new ArrayList<>();

    Window<Product> window =
            repository.findFirst2ByActiveTrueOrderByIdAsc(
                    ScrollPosition.offset()
            );

    while (!window.isEmpty()) {
        window.forEach(product -> ids.add(product.getId()));

        if (!window.hasNext()) {
            break;
        }

        window = repository.findFirst2ByActiveTrueOrderByIdAsc(
                window.positionAt(window.size() - 1)
        );
    }

    assertEquals(List.of(1L, 2L, 3L, 4L, 5L), ids);
}
~~~

Kết quả mong đợi trong fixture có năm Product active với ID từ 1 đến 5:

~~~text
[1, 2, 3, 4, 5]
~~~

Đây là test minh họa. Trong dự án thực tế, cần tạo dữ liệu fixture, kiểm tra ID theo thứ tự và bảo đảm không có dữ liệu khác làm thay đổi kết quả. Có thể chạy integration test với database thật để kiểm tra hành vi keyset, index và SQL được sinh ra.

## 18. Những lỗi thường gặp

**Dùng offset(0) để bắt đầu từ đầu**

Do vị trí là exclusive, phần tử tại offset 0 có thể bị bỏ qua. Dùng ScrollPosition.offset() để bắt đầu.

**Lấy vị trí từ phần tử đầu thay vì phần tử cuối**

Window tiếp theo sẽ bắt đầu quá sớm và có thể lặp dữ liệu. Dùng positionAt(window.size() - 1).

**Quên kiểm tra hasNext()**

Có thể tiếp tục gọi query dù đã hết dữ liệu hoặc xử lý vòng lặp không đúng. Kiểm tra trạng thái Window trước khi yêu cầu cửa sổ tiếp theo.

**Dùng sort không ổn định**

Nhiều bản ghi có cùng giá trị sort mà không có tie-breaker có thể làm thứ tự không xác định. Dùng ID làm tiêu chí phụ.

**Dùng keyset trên trường nullable**

NULL có semantics so sánh khác nhau theo database. Chọn sort key không-null và kiểm tra dữ liệu.

**Projection bỏ mất trường sort**

Spring Data không thể trích xuất keyset đầy đủ. Đưa tất cả sort properties và ID vào projection.

**Kỳ vọng @Query luôn hỗ trợ scrolling**

String-based query methods chưa được hỗ trợ theo tài liệu Spring Data JPA hiện hành. Kiểm tra version và dùng query mechanism được hỗ trợ.

**Dùng offset rất sâu cho batch lớn**

Database có thể phải bỏ qua nhiều dòng. Cân nhắc keyset và index phù hợp.

**Nhầm Window với Stream**

Window là từng nhóm kết quả; Stream có vòng đời tài nguyên và phải được đóng đúng cách.

**Cho rằng ScrollPosition tự lưu checkpoint**

ScrollPosition chỉ biểu diễn vị trí. Nếu cần tiếp tục sau restart, ứng dụng phải tự lưu checkpoint một cách an toàn, cùng thông tin query/sort/filter tương ứng.

## 19. Quy trình thiết kế một scrolling query

Khi xây dựng chức năng đọc dữ liệu lớn, hãy thực hiện:

1. Xác định chỉ cần kết quả tuần tự hay cần tổng số chính xác.
2. Chọn Window thay cho Page nếu không cần totalElements.
3. Chọn offset cho luồng đơn giản hoặc keyset cho tập dữ liệu lớn có index phù hợp.
4. Định nghĩa sort ổn định và có tie-breaker duy nhất.
5. Tạo derived query method trả Window<T> và nhận ScrollPosition.
6. Kiểm tra query style có được phiên bản Spring Data JPA hỗ trợ hay không.
7. Với keyset, bảo đảm sort properties không-null và có mặt trong projection.
8. Dùng WindowIterator nếu chỉ cần duyệt tuần tự; dùng vòng lặp thủ công nếu cần xử lý theo batch/checkpoint.
9. Xác định cách xử lý khi dữ liệu thay đổi đồng thời và khi batch bị retry.
10. Đo SQL, execution plan, index, heap và thời gian xử lý trên dữ liệu gần production.
11. Viết integration test xác nhận không lặp, không bỏ sót và dừng đúng ở Window cuối.

## 20. Kết luận

Window<T> là nhóm kết quả giới hạn dùng để cuộn qua tập dữ liệu lớn; ScrollPosition xác định điểm bắt đầu hoặc tiếp tục. OffsetScrollPosition dựa trên số dòng bỏ qua, còn KeysetScrollPosition dựa trên giá trị sort của phần tử cuối và thường phù hợp hơn với truy vấn tuần tự lớn có index tốt. Dùng positionAt() trên phần tử cuối để tiếp tục, hoặc WindowIterator để đơn giản hóa vòng lặp. Keyset yêu cầu sort ổn định, thuộc tính sort không-null và projection chứa đủ khóa. Trong Spring Data JPA, derived query methods, Query by Example và Querydsl hỗ trợ scrolling theo tài liệu hiện hành; string-based @Query và stored @Procedure chưa hỗ trợ. Hãy kiểm tra phiên bản Spring Data, SQL và execution plan thực tế trước khi triển khai.

## Tài liệu tham khảo

- [Spring Data JPA Reference — Scrolling Large Query Results](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.scrolling)
- [Spring Data Commons API — ScrollPosition](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/domain/ScrollPosition.html)
- [Spring Data Commons API — KeysetScrollPosition](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/domain/KeysetScrollPosition.html)
