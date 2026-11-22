# Chuyển đổi tham số đường dẫn, query parameter và request body

## Mục tiêu

Trong Spring Data REST, một repository được export có thể tự cung cấp các endpoint để đọc, tạo, cập nhật và tìm kiếm entity. Mỗi request HTTP mang dữ liệu vào ứng dụng theo một trong ba cách phổ biến:

- **Path variable** nằm trong URL, thường xác định entity cần truy cập.
- **Query parameter** nằm sau dấu hỏi trong URL, thường truyền điều kiện tìm kiếm, phân trang hoặc sắp xếp.
- **Request body** chứa dữ liệu JSON, thường dùng khi tạo mới hoặc cập nhật entity.

Spring Data REST phối hợp với Spring MVC và Jackson để chuyển các giá trị nhận được thành kiểu Java mà repository và domain model cần. Hiểu rõ từng đường chuyển đổi giúp xử lý đúng kiểu dữ liệu, cấu hình endpoint tìm kiếm và chẩn đoán lỗi request.

## 1. Luồng xử lý tổng quan

Ví dụ một repository quản lý tài nguyên people có thể cung cấp các request:

| Request | Dữ liệu đầu vào chính | Mục đích |
|---|---|---|
| GET /people/42 | Path variable **42** | Tìm entity có ID là 42 |
| GET /people/search/by-last-name?lastName=Nguyen | Query parameter **lastName** | Tìm entity theo họ |
| GET /people?page=0&size=20&sort=lastName,asc | Query parameters **page**, **size**, **sort** | Đọc danh sách có phân trang và sắp xếp |
| POST /people | JSON trong request body | Tạo entity |
| PATCH /people/42 | Path variable và JSON body | Cập nhật một phần entity |

Luồng xử lý có thể hình dung như sau:

1. Spring MVC nhận HTTP request và chọn endpoint của Spring Data REST tương ứng với repository.
2. Giá trị trên URL được tách thành path variable và query parameter. Các giá trị dạng chuỗi được chuyển sang kiểu Java phù hợp bằng cơ chế conversion và binding của Spring.
3. Nếu request có body, một `HttpMessageConverter` đọc nội dung. Với JSON, Jackson deserialize JSON thành entity hoặc kiểu dữ liệu tương ứng.
4. Spring Data REST gọi thao tác repository, xử lý liên kết giữa các tài nguyên và các bước mở rộng được cấu hình trong ứng dụng.
5. Kết quả được chuyển thành HTTP response. Với cấu hình mặc định, tài nguyên thường được biểu diễn theo HAL JSON.

Ba nguồn dữ liệu này đi qua các cơ chế khác nhau. Path variable và query parameter chủ yếu dùng Spring ConversionService; JSON body chủ yếu dùng Jackson thông qua HTTP message converter.

## 2. Path variable: xác định tài nguyên qua URL

Với repository được export, Spring Data REST thường tạo endpoint cho collection và endpoint cho từng item. Endpoint item có dạng:

~~~http
GET /people/{id}
~~~

Phần **{id}** là path variable. Khi nhận request:

~~~http
GET /people/42
~~~

Spring Data REST lấy chuỗi **42**, chuyển nó sang kiểu ID của repository rồi dùng ID đó để tìm entity. Nếu repository khai báo ID là `Long`, giá trị phải chuyển đổi được sang `Long`. Repository dùng `UUID` hoặc kiểu ID khác thì quá trình chuyển đổi phải phù hợp với kiểu đó.

Ví dụ repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Một số tình huống thường gặp:

- ID hợp lệ và entity tồn tại: endpoint trả về tài nguyên tương ứng.
- ID có định dạng không chuyển đổi được sang kiểu ID: request thường thất bại ở bước binding/conversion và trả lỗi 400.
- ID chuyển đổi hợp lệ nhưng không có entity tương ứng: tài nguyên không được tìm thấy và thường trả lỗi 404.

Không nên lấy ID từ body để thay thế ID trên URL khi cập nhật item. URL xác định tài nguyên đích; body cung cấp các giá trị của tài nguyên đó.

## 3. Query parameter: tìm kiếm, phân trang và sắp xếp

### 3.1. Tham số của repository search method

Spring Data REST có thể export các query method của repository dưới đường dẫn `search`. Dùng `@Param` để xác định tên query parameter công khai:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(@Param("lastName") String value);

    @RestResource(path = "created-after", rel = "created-after")
    List<Person> findByCreatedAtAfter(@Param("from") LocalDate from);
}
~~~

Các request tương ứng:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
GET /people/search/created-after?from=2026-01-01
~~~

Spring Data REST lấy giá trị query parameter, chuyển đổi sang kiểu của tham số method rồi gọi query method. Trong ví dụ trên:

- **lastName** được truyền vào tham số kiểu `String`.
- **from** được chuyển thành `LocalDate` trước khi gọi method.
- Tên query parameter công khai được xác định bởi `@Param`, không nhất thiết trùng với tên biến trong method.

Nếu kiểu dữ liệu là ngày, số, enum hoặc một kiểu domain tùy chỉnh, chuỗi trong URL phải có định dạng mà converter tương ứng hiểu được. Giá trị sai định dạng có thể làm request thất bại với lỗi 400.

### 3.2. Phân trang và sắp xếp

Spring Data REST hỗ trợ các query parameter phổ biến cho repository trả về danh sách có thể phân trang:

~~~http
GET /people?page=0&size=20&sort=lastName,asc
~~~

- **page**: số thứ tự trang, bắt đầu từ 0.
- **size**: số phần tử yêu cầu trong một trang.
- **sort**: tên thuộc tính và hướng sắp xếp, ví dụ **lastName,asc** hoặc **createdAt,desc**.

Có thể truyền nhiều tiêu chí sort bằng cách lặp lại parameter:

~~~http
GET /people?sort=lastName,asc&sort=createdAt,desc
~~~

Cấu hình của ứng dụng có thể thay đổi kích thước trang mặc định, giới hạn kích thước tối đa và cách xử lý sort. Vì vậy, client nên gửi rõ page, size và sort khi cần kết quả ổn định.

### 3.3. URL encoding

Query parameter là dữ liệu trên URL nên cần URL-encode các ký tự đặc biệt. Ví dụ dấu cách, dấu `&`, dấu `+` hoặc ký tự tiếng Việt phải được mã hóa đúng để server nhận được giá trị dự kiến. Dấu `&` phân tách các parameter; nếu nó là một phần của giá trị thì phải được encode.

## 4. Request body: chuyển JSON thành entity

Khi tạo mới hoặc cập nhật tài nguyên, client thường gửi dữ liệu trong request body. Ví dụ tạo một person:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "birthDate": "1998-06-12"
}
~~~

Quá trình xử lý cơ bản:

1. HTTP message converter nhận body theo `Content-Type`.
2. Với JSON, Jackson đọc JSON và deserialize các thuộc tính thành kiểu Java tương ứng.
3. Spring Data REST chuyển entity cho thao tác repository phù hợp.
4. Response trả về trạng thái HTTP và biểu diễn tài nguyên; khi tạo mới, response thường có header `Location` trỏ đến URI của tài nguyên vừa tạo.

Tên thuộc tính JSON cần khớp với cách Jackson ánh xạ thuộc tính của entity. Giá trị ngày, giờ, enum, số và object lồng nhau cần có định dạng tương thích với cấu hình Jackson và kiểu Java.

### 4.1. Quan hệ giữa các entity

Trong Spring Data REST, association được biểu diễn qua liên kết tài nguyên. Khi ghi một association, client thường gửi URI của tài nguyên liên quan theo tên thuộc tính association, ví dụ:

~~~http
POST /orders
Content-Type: application/json

{
  "description": "Đơn hàng đầu tiên",
  "customer": "http://localhost:8080/customers/1"
}
~~~

URI cho biết entity customer đã tồn tại mà order cần tham chiếu. Endpoint, tên association và cách biểu diễn cụ thể phụ thuộc domain model cùng cấu hình export của repository. Hãy dùng URI được server cung cấp trong HAL response để tham chiếu tài nguyên liên quan.

### 4.2. PUT và PATCH

Spring Data REST hỗ trợ cập nhật item qua URI của tài nguyên:

~~~http
PUT /people/42
Content-Type: application/json
~~~

`PUT` mang ý nghĩa thay thế representation của tài nguyên; client nên gửi đầy đủ các trường cần duy trì theo hợp đồng API.

~~~http
PATCH /people/42
Content-Type: application/json

{
  "lastName": "Tran"
}
~~~

`PATCH` dùng để cập nhật một phần tài nguyên. Chỉ gửi các trường cần thay đổi. Cách diễn giải giá trị `null`, trường bị bỏ qua và media type cụ thể phụ thuộc cơ chế patch cùng phiên bản/cấu hình ứng dụng; client nên tuân theo hợp đồng API của server.

## 5. Tùy chỉnh chuyển đổi kiểu dữ liệu

### 5.1. Path variable và query parameter

Spring ConversionService đảm nhiệm nhiều chuyển đổi từ chuỗi trên URL sang kiểu Java. Spring đã cung cấp converter cho nhiều kiểu thông dụng như số, boolean, enum và các kiểu ngày giờ được hỗ trợ.

Nếu API dùng kiểu tùy chỉnh, có thể đăng ký `Converter<String, T>` thông qua `RepositoryRestConfigurer`:

~~~java
public record TrackingCode(String value) {
}

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureConversionService(
            ConfigurableConversionService conversionService) {
        conversionService.addConverter(
            String.class,
            TrackingCode.class,
            TrackingCode::new
        );
    }
}
~~~

Converter cần kiểm tra và từ chối chuỗi không hợp lệ theo quy tắc của domain. Lỗi chuyển đổi nên được biểu diễn rõ để client biết parameter nào có định dạng sai.

### 5.2. JSON request body

JSON body được Jackson deserialize thông qua HTTP message converter. Converter trong ConversionService không tự động thay thế Jackson deserializer cho mọi thuộc tính trong JSON.

Để tùy chỉnh cách đọc JSON, có thể dùng các cơ chế Jackson như:

- `@JsonCreator` và `@JsonProperty` để xác định cách tạo object từ JSON.
- `@JsonDeserialize` để chỉ định custom deserializer cho kiểu cần xử lý riêng.
- Jackson module để đăng ký serializer/deserializer cho một nhóm kiểu.
- Cấu hình `ObjectMapper` dùng bởi Spring Data REST khi cần thay đổi quy tắc JSON chung.

Hãy chọn cơ chế theo nguồn dữ liệu: giá trị trên URL cần converter/binding phù hợp; giá trị trong JSON cần Jackson mapping phù hợp.

## 6. Phân biệt các lỗi thường gặp

| Hiện tượng | Bước có thể phát sinh | Hướng kiểm tra |
|---|---|---|
| ID trên URL sai định dạng | Chuyển path variable sang kiểu ID | Kiểm tra kiểu ID và định dạng ID client gửi |
| Không tìm thấy item | Tra cứu repository sau khi chuyển đổi ID | Kiểm tra ID có tồn tại và endpoint có đúng không |
| Query parameter ngày/số không hợp lệ | Binding và conversion của query parameter | Kiểm tra tên `@Param`, định dạng giá trị và converter |
| Search endpoint không tồn tại | Export repository/search method | Kiểm tra repository, `@RestResource` và cấu hình export |
| JSON sai cú pháp hoặc sai kiểu | Jackson deserialize request body | Kiểm tra JSON, tên thuộc tính và kiểu Java |
| Content-Type không được hỗ trợ | HTTP message converter | Gửi Content-Type mà endpoint hỗ trợ |
| Association không được gắn đúng | Ánh xạ association trong body | Kiểm tra tên association và URI tài nguyên liên quan |

Các mã HTTP cụ thể còn phụ thuộc endpoint, exception handler và cấu hình của ứng dụng. Khi debug, hãy xác định lỗi xuất hiện ở bước đọc URL, chuyển đổi kiểu, deserialize body hay thao tác repository.

## 7. Checklist khi xây dựng client

- Dùng đúng URI và kiểu ID mà repository export.
- Gửi query parameter đúng tên đã khai báo bằng `@Param`.
- Encode giá trị query parameter trước khi ghép vào URL.
- Gửi page, size và sort theo quy ước của API khi cần phân trang.
- Đặt `Content-Type` phù hợp với định dạng request body.
- Gửi JSON có tên thuộc tính và kiểu giá trị tương thích với entity/Jackson.
- Dùng URI tài nguyên do server cung cấp khi ghi association.
- Chọn `POST` để tạo mới, `PUT` khi thay thế representation và `PATCH` khi cập nhật một phần.
- Đọc response status, header `Location` và nội dung lỗi để xác định bước xử lý thất bại.

## 8. Kết luận

Path variable xác định tài nguyên và thường cần chuyển sang kiểu ID của repository. Query parameter truyền điều kiện tìm kiếm hoặc tùy chọn phân trang/sắp xếp và được binding vào tham số của search method. Request body mang dữ liệu entity dưới dạng JSON và được Jackson deserialize. Khi cần kiểu dữ liệu tùy chỉnh, hãy cấu hình Spring ConversionService cho dữ liệu trên URL và cấu hình Jackson cho dữ liệu JSON. Phân biệt đúng ba cơ chế này giúp endpoint Spring Data REST dễ dùng và dễ xử lý lỗi hơn.
