# Page và Slice: tổng số phần tử, chi phí đếm và liên kết điều hướng

## Mục tiêu

Sau bài này, bạn có thể:

- Cấu hình phân trang và sắp xếp cho collection resource của Spring Data REST.
- Phân biệt dữ liệu và metadata mà Page và Slice cung cấp.
- Giải thích vì sao Page có thể phát sinh truy vấn COUNT và khi nào Slice phù hợp hơn.
- Đọc page metadata cùng các liên kết prev/next trong HAL.
- Thiết kế thứ tự sắp xếp ổn định và tránh các truy vấn phân trang quá tốn kém.

## 1. Phân trang trong Spring Data REST

Khi repository được export và hỗ trợ phân trang, Spring Data REST không cần trả toàn bộ bản ghi trong một request. Client có thể yêu cầu một phần dữ liệu bằng các query parameter:

| Tham số | Ý nghĩa | Mặc định thường gặp |
|---|---|---|
| page | Chỉ số trang, bắt đầu từ 0 | 0 |
| size | Số phần tử tối đa trong một trang | 20 |
| sort | Thuộc tính và chiều sắp xếp | Theo cấu hình/query |

Ví dụ:

~~~http
GET /orders?page=0&size=20
Accept: application/hal+json
~~~

Request trên lấy trang đầu tiên, tối đa 20 đơn hàng. Trang kế tiếp có chỉ số **page=1**; chỉ số trang bắt đầu từ 0, vì vậy **page=1** là trang thứ hai.

Có thể kết hợp phân trang với nhiều điều kiện sort:

~~~http
GET /orders?page=1&size=10&sort=createdAt,desc&sort=id,desc
Accept: application/hal+json
~~~

Mỗi tham số **sort** mô tả một tiêu chí. Trong ví dụ, kết quả được sắp xếp theo **createdAt** giảm dần; nếu nhiều bản ghi có cùng thời điểm tạo, **id** giảm dần sẽ quyết định thứ tự giữa chúng.

Các giá trị mặc định có thể được thay đổi bằng cấu hình Spring Data REST. Ứng dụng cũng nên giới hạn page size tối đa để một client không thể yêu cầu một lượng dữ liệu quá lớn trong một request.

## 2. Pageable, Page và Slice ở tầng repository

**Pageable** mô tả yêu cầu truy vấn: trang cần lấy, kích thước trang và thứ tự sắp xếp. **Page** và **Slice** mô tả kết quả truy vấn theo hai mức metadata khác nhau.

Ví dụ repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @RestResource(path = "byStatus", rel = "byStatus")
    Page<PurchaseOrder> findByStatus(
            @Param("status") OrderStatus status,
            Pageable pageable
    );

    @RestResource(path = "byCustomer", rel = "byCustomer")
    Slice<PurchaseOrder> findByCustomerId(
            @Param("customerId") Long customerId,
            Pageable pageable
    );
}
~~~

Spring Data REST nhận biết phương thức tìm kiếm có tham số **Pageable** và kết quả **Page** hoặc **Slice**, sau đó export search resource có khả năng phân trang.

Ví dụ gọi hai search resource:

~~~http
GET /orders/search/byStatus?status=PAID&page=0&size=20
GET /orders/search/byCustomer?customerId=7&page=0&size=20
~~~

Tên path và relation có thể được tùy chỉnh bằng **@RestResource**. Client nên khám phá search link từ resource hoặc API profile mà server công bố thay vì tự suy đoán endpoint.

## 3. Page: có tổng số phần tử và tổng số trang

**Page<T>** cung cấp nội dung của trang hiện tại cùng thông tin về toàn bộ kết quả:

- **getContent()**: các phần tử trong trang hiện tại.
- **getNumber()**: chỉ số trang hiện tại, bắt đầu từ 0.
- **getSize()**: kích thước trang được yêu cầu.
- **getNumberOfElements()**: số phần tử thực tế trong trang hiện tại.
- **getTotalElements()**: tổng số phần tử thỏa điều kiện truy vấn.
- **getTotalPages()**: tổng số trang dựa trên tổng số phần tử và kích thước trang.
- **hasNext() / hasPrevious()**: có trang kế tiếp hoặc trang trước hay không.

Ví dụ một truy vấn có 50 đơn hàng phù hợp và page size bằng 5:

~~~json
{
  "content": [
    { "id": 101, "status": "PAID" },
    { "id": 102, "status": "PAID" }
  ],
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
~~~

Phần **content** ở trên chỉ minh họa một phần dữ liệu. Nếu trang đầu có đủ dữ liệu thì số phần tử thực tế thường bằng **size**; **totalElements=50** và **totalPages=10** mô tả toàn bộ kết quả của truy vấn.

**Page** phù hợp khi giao diện thực sự cần hiển thị tổng số kết quả, tổng số trang, số trang cuối hoặc thanh điều hướng cho phép nhảy đến một trang cụ thể.

## 4. Vì sao Page có thể tốn chi phí COUNT?

Để tạo **Page**, hệ thống cần biết tổng số bản ghi phù hợp với điều kiện truy vấn. Với Spring Data JPA, việc này thường cần thêm một truy vấn đếm bên cạnh truy vấn lấy dữ liệu.

Về mặt khái niệm, hai truy vấn có dạng:

~~~sql
-- Lấy nội dung của trang hiện tại
SELECT *
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;

-- Đếm tổng số bản ghi phù hợp
SELECT COUNT(*)
FROM purchase_order
WHERE status = 'PAID';
~~~

Truy vấn dữ liệu có thể tận dụng giới hạn **LIMIT/OFFSET**. Truy vấn COUNT phải xác định số bản ghi thỏa điều kiện trên toàn bộ tập kết quả. Vì vậy, với bảng lớn hoặc điều kiện lọc phức tạp, COUNT có thể tốn thời gian đáng kể.

Chi phí có thể tăng khi truy vấn chứa:

- JOIN nhiều bảng hoặc quan hệ một-nhiều làm nhân số dòng.
- **DISTINCT**, **GROUP BY**, subquery hoặc điều kiện lọc phức tạp.
- Bộ lọc trên cột chưa có index phù hợp.
- Truy vấn count được suy ra không đúng hoặc kém hiệu quả so với truy vấn dữ liệu.

Không nên kết luận mọi request Page luôn thực thi hai SQL query trong mọi tình huống. Spring Data có thể tối ưu và suy ra tổng số từ kết quả trong một số trường hợp. Tuy nhiên, khi cần tổng số chính xác, một truy vấn đếm vẫn có thể được yêu cầu.

Với custom query, có thể chỉ định riêng **countQuery** để kiểm soát câu lệnh đếm:

~~~java
@Query(
    value = """
        select o
        from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o)
        from PurchaseOrder o
        where o.status = :status
        """
)
Page<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable
);
~~~

Count query phải đếm đúng tập kết quả mà truy vấn chính trả về. Nếu truy vấn chính dùng DISTINCT hoặc JOIN làm thay đổi cardinality, hãy thiết kế câu COUNT tương ứng và kiểm tra kết quả trên dữ liệu thực tế.

## 5. Slice: chỉ cần biết còn dữ liệu tiếp theo

**Slice<T>** tập trung vào nội dung của lát dữ liệu hiện tại và khả năng tiếp tục lấy dữ liệu. Nó không cung cấp tổng số phần tử hoặc tổng số trang của toàn bộ kết quả.

Các thông tin thường dùng:

- **getContent()**: các phần tử trong lát hiện tại.
- **getNumber()**, **getSize()**, **getNumberOfElements()**: vị trí và kích thước lát hiện tại.
- **hasNext()**: còn dữ liệu ở lát tiếp theo không.
- **hasPrevious()**: có lát trước đó không.

Để xác định có dữ liệu tiếp theo mà không đếm toàn bộ kết quả, Spring Data thường lấy nhiều hơn một phần tử so với page size. Ví dụ page size bằng 20 thì truy vấn có thể lấy 21 dòng. Nếu dòng thứ 21 tồn tại, hệ thống biết rằng còn dữ liệu và chỉ trả 20 dòng đầu cho client.

Ví dụ:

~~~java
Slice<PurchaseOrder> findByCustomerId(
        Long customerId,
        Pageable pageable
);
~~~

Slice phù hợp với màn hình cuộn liên tục, nút “Tải thêm” hoặc xử lý tuần tự qua nhiều lô dữ liệu khi không cần biết trước tổng số kết quả.

Spring Data REST nhận biết phương thức trả về **Slice** và bổ sung các liên kết điều hướng trước/sau cho resource. Vì bản thân Slice không biết tổng số toàn cục, client không nên giả định rằng có **totalElements** hoặc **totalPages** chính xác để hiển thị.

## 6. So sánh Page và Slice

| Tiêu chí | Page | Slice |
|---|---|---|
| Nội dung trang hiện tại | Có | Có |
| Kích thước và vị trí hiện tại | Có | Có |
| Biết còn dữ liệu tiếp theo | Có | Có |
| Tổng số phần tử | Có | Không |
| Tổng số trang | Có | Không |
| Nhu cầu truy vấn COUNT | Có thể cần | Không cần để xác định tổng số |
| Chi phí điển hình | Truy vấn dữ liệu và có thể thêm COUNT | Truy vấn dữ liệu giới hạn, thường lấy thêm một dòng |
| Phù hợp | Giao diện cần tổng số và số trang | Cuộn liên tục, tải thêm, xử lý theo lô |

Chọn **Page** khi nghiệp vụ hoặc giao diện cần tổng số chính xác. Chọn **Slice** khi chỉ cần biết có thể tải tiếp hay không. Không nên dùng Page chỉ vì muốn có nút Next/Previous; Slice đã đáp ứng nhu cầu xác định còn dữ liệu tiếp theo.

## 7. Liên kết điều hướng trong HAL

Spring Data REST sử dụng HAL để trả dữ liệu cùng các liên kết hypermedia. Một response collection được phân trang có thể có dạng:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders{&sort,page,size}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/orders?page=1&size=5{&sort}",
      "templated": true
    }
  },
  "_embedded": {
    "orders": [
      { "id": 101, "status": "PAID" },
      { "id": 102, "status": "PAID" }
    ]
  },
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
~~~

Các thành phần quan trọng:

- **_embedded.orders**: dữ liệu của trang hiện tại; tên relation phụ thuộc repository được export.
- **_links.self**: link của collection hiện tại, có thể là URI template.
- **_links.next**: link đến trang tiếp theo nếu còn dữ liệu.
- **_links.prev**: link đến trang trước nếu đang ở trang sau trang đầu.
- **page**: metadata của Page, gồm **size**, **totalElements**, **totalPages** và **number**.

Ở trang đầu, response không có link **prev**. Ở trang cuối, response không có link **next**. Với trang giữa, cả hai link có thể cùng xuất hiện.

Khi client cần chuyển trang, hãy đọc **href** từ **_links.next** hoặc **_links.prev** và gọi chính URL đó. Các link này có thể giữ lại điều kiện lọc, sort và page size. Cách làm này tránh phải tự ghép query string và giúp client ít phụ thuộc vào cấu trúc URL nội bộ của server.

Ví dụ trang thứ hai:

~~~http
GET /orders?page=1&size=5
Accept: application/hal+json
~~~

Response sẽ có link **prev** trỏ về trang 0 và link **next** trỏ đến trang tiếp theo nếu còn dữ liệu. Các giá trị **page** trong URL vẫn được đánh số từ 0.

## 8. Sắp xếp ổn định để tránh trùng hoặc bỏ sót bản ghi

Phân trang chỉ đáng tin khi thứ tự dữ liệu có tính xác định. Nếu sort theo một cột có nhiều giá trị trùng nhau, thứ tự giữa các bản ghi bằng nhau có thể thay đổi giữa các request.

Ví dụ chỉ sắp xếp theo thời gian tạo:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc
~~~

Nếu nhiều đơn hàng có cùng **createdAt**, database không đảm bảo thứ tự giữa chúng. Khi client chuyển sang trang tiếp theo, một bản ghi có thể xuất hiện lặp lại hoặc bị bỏ qua.

Nên bổ sung một thuộc tính duy nhất làm tiêu chí phụ:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=id,desc
~~~

Các điểm cần nhớ:

- Ưu tiên sort theo thuộc tính có index phù hợp khi dữ liệu lớn.
- Dùng một thuộc tính duy nhất, thường là ID, làm tiêu chí cuối để phá hòa.
- Spring Data REST hỗ trợ nhiều tham số sort; thứ tự tham số xác định thứ tự tiêu chí.
- Có thể sort theo thuộc tính lồng nhau bằng property path.
- Sort theo association được export thành link đến resource cấp cao nhất không được hỗ trợ như một thuộc tính sort thông thường.
- Chỉ cho phép các thuộc tính sort hợp lệ mà API dự định công bố; không để client tự do chọn mọi trường nếu điều đó gây rủi ro hiệu năng.

Thứ tự ổn định giúp phân trang nhất quán hơn. Tuy nhiên, nếu dữ liệu được thêm hoặc xóa giữa hai request, offset của các trang sau vẫn có thể dịch chuyển. Với luồng dữ liệu thay đổi liên tục, cần cân nhắc chiến lược cursor/keyset hoặc cơ chế snapshot phù hợp với nghiệp vụ.

## 9. Giới hạn page size và phân trang dữ liệu lớn

Phân trang giúp giới hạn số dòng trả về mỗi request, nhưng không tự động làm mọi truy vấn nhanh.

Một số nguyên tắc triển khai:

1. Đặt page size mặc định vừa phải và giới hạn page size tối đa.
2. Không cho client yêu cầu hàng trăm nghìn bản ghi trong một trang.
3. Kiểm tra index cho các cột lọc và sort thường dùng.
4. Kiểm tra execution plan của cả truy vấn lấy dữ liệu và truy vấn COUNT.
5. Với Page có custom query phức tạp, tối ưu hoặc khai báo count query riêng.
6. Nếu chỉ cần biết có dữ liệu tiếp theo, cân nhắc Slice để tránh tính tổng.
7. Với offset rất lớn, lưu ý database vẫn phải xử lý hoặc bỏ qua lượng bản ghi trước offset; Slice không loại bỏ hạn chế này.
8. Khi phải duyệt tập dữ liệu cực lớn, cân nhắc cursor/keyset pagination hoặc batch processing chuyên biệt thay cho việc tăng page liên tục.

Page size tối đa là một hàng rào bảo vệ tài nguyên server. Nó không thay thế việc thiết kế index và truy vấn phù hợp.

## 10. Thực hành với curl

Đọc trang đầu tiên của collection:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders?page=0&size=5&sort=createdAt,desc&sort=id,desc"
~~~

Đọc trang thứ hai:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders?page=1&size=5&sort=createdAt,desc&sort=id,desc"
~~~

Đọc kết quả tìm kiếm có phân trang:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders/search/byStatus?status=PAID&page=0&size=10"
~~~

Với URL có ký tự **&**, hãy đặt toàn bộ URL trong dấu nháy khi chạy curl để shell không diễn giải các tham số thành lệnh riêng.

Sau mỗi request, kiểm tra:

- **page.number** có đúng trang đã yêu cầu không.
- **page.size** có đúng page size server chấp nhận không.
- **page.totalElements** và **page.totalPages** có hợp lý nếu response là Page không.
- Link **next** có giữ lại sort và filter không.
- Link **prev** có xuất hiện khi đang ở trang sau trang đầu không.
- Trang cuối có bỏ link **next** không.

## 11. Bài tập tự luyện

Cho repository PurchaseOrder có hàng nghìn đơn hàng:

1. Viết một phương thức tìm đơn hàng theo status trả về **Page<PurchaseOrder>**.
2. Viết một phương thức tìm đơn hàng theo customer trả về **Slice<PurchaseOrder>**.
3. Giải thích vì sao Page có thể cần truy vấn COUNT, còn Slice thường chỉ lấy thêm một dòng để kiểm tra **hasNext**.
4. Một màn hình chỉ cần nút “Tải thêm”, không hiển thị tổng số kết quả. Bạn sẽ chọn Page hay Slice? Giải thích.
5. Một truy vấn lọc theo status có COUNT rất chậm. Bạn sẽ kiểm tra những yếu tố nào trong execution plan và count query?
6. Vì sao sort theo **createdAt** đơn lẻ có thể làm bản ghi lặp hoặc bị bỏ sót giữa hai trang? Hãy bổ sung tiêu chí sort để ổn định thứ tự.
7. Mô tả cách client dùng **_links.next.href** để tải trang kế tiếp mà không tự ghép URL.

**Ghi nhớ:** Page cung cấp tổng số phần tử và tổng số trang, nên có thể phát sinh chi phí COUNT. Slice chỉ cần biết còn dữ liệu tiếp theo, phù hợp với luồng tải thêm. Trong Spring Data REST, client nên điều hướng bằng các liên kết **next** và **prev** mà HAL trả về.

## Tài liệu tham khảo

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Commons — Paging, Iterating Large Results, Sorting and Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
