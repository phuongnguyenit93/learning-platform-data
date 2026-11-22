# 404 cho tài nguyên thiếu và phân biệt với truy vấn trả tập hợp rỗng trong Spring Data REST

## Mục tiêu

Khi làm việc với Spring Data REST, cần phân biệt hai tình huống có vẻ giống nhau ở giao diện: một tài nguyên cụ thể không tồn tại và một truy vấn hợp lệ không tìm thấy phần tử nào.

Hai tình huống này có ý nghĩa HTTP khác nhau:

- Yêu cầu một tài nguyên đơn lẻ theo định danh nhưng tài nguyên đó không tồn tại thường trả về **404 Not Found**.
- Yêu cầu một collection resource hoặc truy vấn trả về danh sách nhưng không có phần tử phù hợp thường trả về **200 OK** cùng collection rỗng.

Sau bài này, bạn có thể xác định loại resource đang được gọi, đọc đúng status code, xử lý collection rỗng ở client và kiểm thử hai trường hợp độc lập.

## 1. Phân biệt item resource và collection resource

Spring Data REST thường xuất bản hai dạng resource chính từ một repository:

- **Item resource:** đại diện cho một entity cụ thể, thường được truy cập bằng URI có định danh, ví dụ **/orders/42**.
- **Collection resource:** đại diện cho tập entity, ví dụ **/orders**; có thể nhận query parameter để lọc, phân trang hoặc sắp xếp.

Giả sử repository Order được xuất bản tại **/orders**.

Đọc một đơn hàng cụ thể:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Nếu đơn hàng có id 42 tồn tại, server trả về representation của đơn hàng, thường với **200 OK**.

Nếu không có đơn hàng đó, Spring Data REST trả về **404 Not Found**, vì item resource mà client yêu cầu không tồn tại.

Ngược lại, đọc collection:

~~~http
GET /orders
Accept: application/hal+json
~~~

Nếu repository chưa có đơn hàng nào, collection vẫn tồn tại. Server có thể trả về **200 OK** với collection không chứa phần tử và metadata phân trang tương ứng.

Điểm quan trọng: collection rỗng là một kết quả hợp lệ của việc đọc collection. Nó không có nghĩa endpoint collection bị thiếu.

## 2. Truy vấn không có kết quả vẫn là một request thành công

Giả sử repository có phương thức tìm đơn hàng theo trạng thái:

~~~java
@RepositoryRestResource
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Page<Order> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
~~~

Spring Data REST có thể xuất bản finder dưới search resource. Với tên mặc định, client gọi:

~~~http
GET /orders/search/findByStatus?status=CANCELLED&page=0&size=20
Accept: application/hal+json
~~~

Nếu không có đơn hàng nào mang trạng thái **CANCELLED**, truy vấn vẫn hợp lệ. Server trả về **200 OK** và một collection representation rỗng.

Ví dụ minh họa về response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/search/findByStatus?status=CANCELLED"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Đây là cấu trúc minh họa. HAL có thể không có phần **_embedded** khi collection rỗng; các link và metadata cụ thể phụ thuộc kiểu kết quả, cấu hình và phiên bản Spring Data REST.

Client nên dựa vào status code và collection content để xử lý. Không nên coi việc thiếu phần tử trong **_embedded** là lỗi HTTP.

## 3. Ví dụ so sánh hai tình huống

Giả sử database hiện có đơn hàng 10 và 11, nhưng không có đơn hàng 99. Đồng thời không có đơn hàng nào mang trạng thái CANCELLED.

| Request | Ý nghĩa | Kết quả điển hình |
|---|---|---|
| **GET /orders/10** | Đọc item resource có tồn tại | **200 OK** |
| **GET /orders/99** | Đọc item resource không tồn tại | **404 Not Found** |
| **GET /orders?status=CANCELLED** | Đọc collection sau khi lọc, không có kết quả | **200 OK**, collection rỗng nếu endpoint hỗ trợ filter này |
| **GET /orders/search/findByStatus?status=CANCELLED** | Gọi finder trả về collection hoặc Page rỗng | **200 OK**, collection rỗng |

Request collection có thể dùng finder URL hoặc query parameter tùy API đã được xuất bản. Ví dụ trên nhằm thể hiện sự khác nhau về bản chất giữa item resource và collection resource.

Có thể ghi nhớ bằng câu hỏi: client đang yêu cầu **một entity cụ thể** hay đang yêu cầu **một tập kết quả**?

- Nếu yêu cầu một entity cụ thể theo URI mà entity không tồn tại, trả về 404.
- Nếu yêu cầu một tập kết quả và không có entity nào phù hợp, trả về 200 với tập rỗng.

## 4. Chú ý kiểu trả về của finder method

Không phải mọi phương thức tìm kiếm đều trả về collection. Kiểu trả về của repository method ảnh hưởng tới cách Spring Data REST biểu diễn kết quả.

Ví dụ các dạng kết quả:

~~~java
List<Order> findByStatus(OrderStatus status);

Page<Order> findByStatus(
        OrderStatus status,
        Pageable pageable);

Optional<Order> findByExternalCode(String code);
~~~

- **List** hoặc **Page** biểu diễn nhiều kết quả. Khi không có phần tử, kết quả là collection rỗng và request thường trả về **200 OK**.
- **Optional<Order>** biểu diễn tối đa một kết quả. Khi không có entity, kết quả là Optional.empty; cách biểu diễn tài nguyên đơn lẻ và status cần được xác nhận theo phiên bản, cách xuất bản finder và cấu hình ứng dụng. Không suy diễn rằng finder đơn lẻ sẽ trả collection rỗng.
- Phương thức trả về một entity đơn lẻ cũng cần được kiểm tra khi không tìm thấy kết quả; không đồng nhất nó với finder trả List hoặc Page.

Nếu API cần ngữ nghĩa danh sách, hãy thiết kế finder với kiểu trả về collection hoặc Page. Nếu API cần ngữ nghĩa một tài nguyên duy nhất, hãy định nghĩa rõ hành vi khi không có kết quả và kiểm thử status code thực tế.

## 5. Trường hợp trang không có phần tử

Một collection có thể trả về content rỗng vì hai lý do khác nhau:

1. Không có bản ghi nào thỏa mãn bộ lọc.
2. Bộ lọc có dữ liệu, nhưng client yêu cầu một trang nằm ngoài phạm vi hiện có.

Ví dụ database có 35 đơn hàng phù hợp, page size là 10, nhưng client yêu cầu trang thứ 8:

~~~http
GET /orders/search/findByStatus?status=PAID&page=7&size=10
Accept: application/hal+json
~~~

Trang được yêu cầu có thể không chứa phần tử, nhưng collection và truy vấn vẫn hợp lệ. Response vẫn thường là **200 OK**. Metadata có thể cho biết **totalElements=35**, **totalPages=4** và **number=7**.

Vì vậy, khi content rỗng, client nên đọc thêm metadata phân trang:

- **totalElements = 0:** không có bản ghi nào phù hợp với truy vấn.
- **totalElements > 0** nhưng content rỗng: có thể client đã yêu cầu trang vượt quá trang cuối.
- **totalPages** và **number:** giúp xác định trang hiện tại có nằm trong phạm vi kết quả hay không.

Không chuyển một trang rỗng thành 404 chỉ vì mảng dữ liệu không có phần tử.

## 6. Xử lý ở client

Client nên phân nhánh theo status code và kiểu resource.

Ví dụ logic tổng quát:

~~~text
Gửi GET request
    |
    +-- 200 OK
    |     |
    |     +-- Item resource: hiển thị entity
    |     |
    |     +-- Collection resource:
    |             có phần tử -> hiển thị danh sách
    |             rỗng -> hiển thị trạng thái "Không có kết quả"
    |
    +-- 404 Not Found
    |     -> thông báo tài nguyên không tồn tại
    |        hoặc đường dẫn không được xuất bản
    |
    +-- 400 / 401 / 403 / 406 / 5xx
          -> xử lý lỗi tương ứng
~~~

Với collection rỗng, giao diện nên hiển thị empty state phù hợp, chẳng hạn “Không tìm thấy đơn hàng phù hợp với bộ lọc”. Đây là trạng thái kết quả bình thường, không nên hiển thị trang lỗi hoặc nút thử lại liên tục.

Với **404**, client có thể thông báo entity đã bị xóa, id không hợp lệ hoặc URI không còn tồn tại. Nếu đang đọc một item resource sau khi người dùng chọn từ danh sách, có thể làm mới danh sách hoặc đưa người dùng về màn hình trước.

Không tự động retry một request GET trả 404 như thể đó là lỗi mạng tạm thời. Trước tiên hãy kiểm tra URI và trạng thái tài nguyên.

## 7. 404 không phải lúc nào cũng chỉ do entity không tồn tại

Khi nhận 404, cần kiểm tra chính xác tài nguyên nào bị thiếu:

- **Sai định danh:** entity có id khác hoặc đã bị xóa.
- **Sai đường dẫn:** repository path hoặc base path không đúng.
- **Repository không được xuất bản:** repository bị ẩn, không được export hoặc cấu hình Spring Data REST không đăng ký endpoint như client kỳ vọng.
- **Sai URI association:** association link hoặc URI của tài nguyên liên quan không còn hợp lệ.
- **Sai kiểu định danh:** giá trị path không được chuyển đổi đúng sang kiểu id của domain.
- **Custom exception handling:** ứng dụng có thể chuyển một số lỗi nghiệp vụ thành 404.
- **Security policy:** một số hệ thống chủ động trả 404 để không tiết lộ sự tồn tại của tài nguyên mà người gọi không có quyền xem.

Vì vậy, đừng kết luận ngay database không có entity chỉ từ status 404. Hãy đối chiếu URL, repository export, quyền truy cập và log server.

Các status khác cũng mang ý nghĩa riêng:

| Status | Ý nghĩa thường gặp |
|---|---|
| **400 Bad Request** | Query parameter hoặc dữ liệu request không hợp lệ |
| **401 Unauthorized** | Chưa xác thực hoặc thông tin xác thực không hợp lệ |
| **403 Forbidden** | Đã xác thực nhưng không được phép thực hiện |
| **404 Not Found** | Resource hoặc endpoint được yêu cầu không được tìm thấy |
| **406 Not Acceptable** | Server không thể đáp ứng media type được yêu cầu |
| **500 Internal Server Error** | Lỗi xử lý ngoài dự kiến ở server |

Nội dung body của lỗi có thể thay đổi theo media type, cấu hình và exception handler. Client nên xử lý status code và cấu trúc lỗi đã được API công bố, không phụ thuộc vào một câu message cố định.

## 8. Kiểm thử hai trường hợp độc lập

Nên có integration test riêng cho item resource bị thiếu và collection query không có kết quả. Ví dụ dùng MockMvc:

~~~java
@Test
void missingOrderShouldReturnNotFound() throws Exception {
    mockMvc.perform(get("/orders/999999")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
}

@Test
void emptySearchShouldReturnOk() throws Exception {
    mockMvc.perform(get("/orders/search/findByStatus")
            .param("status", "CANCELLED")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk());
}
~~~

Đây là ví dụ định hướng; thay URL, tên finder, tham số và kiểu media theo repository thực tế. Test collection rỗng nên chuẩn bị dữ liệu sao cho chắc chắn không có kết quả phù hợp, rồi xác nhận response là một collection hợp lệ.

Có thể kiểm tra thêm:

- Item resource có tồn tại trả về 200 và đúng entity.
- Collection có kết quả trả về 200 và chứa các phần tử mong đợi.
- Collection không có kết quả trả về 200 và content rỗng.
- Trang vượt phạm vi trả về 200 với metadata phân trang phù hợp.
- Finder trả về một entity không tồn tại có hành vi đúng với contract đã chọn.
- Các trường hợp 401/403 không bị nhầm với 404 do policy bảo mật.

## Ghi nhớ

**404 Not Found** phù hợp khi client yêu cầu một tài nguyên cụ thể mà server không tìm thấy hoặc không công bố URI đó. Một truy vấn hợp lệ trả về danh sách rỗng vẫn là **200 OK**: server đã xử lý thành công và kết quả chỉ là không có phần tử phù hợp. Hãy phân biệt item resource với collection resource, xem kiểu trả về của finder và đọc metadata phân trang trước khi quyết định cách hiển thị empty state hay lỗi cho người dùng.