# Dùng curl và HAL Explorer kiểm tra tài nguyên gốc

Khi khởi động một ứng dụng Spring Data REST, nên kiểm tra **tài nguyên gốc (API root)** trước. Root resource là điểm vào để client khám phá những tài nguyên mà server công bố. Thay vì tự đoán URL của collection hoặc item, client đọc các liên kết trong response HAL rồi đi theo relation phù hợp.

Hai công cụ thường dùng:

- **curl** gửi HTTP request trực tiếp, hiển thị status code, headers và body. Công cụ phù hợp để kiểm tra giao thức, tái hiện lỗi và tự động hóa.
- **HAL Explorer** là giao diện web để điều hướng các response HAL/HAL-FORMS. Nó đọc link từ response, hiển thị các thao tác được công bố và giúp thử request trong trình duyệt.

curl cho thấy chính xác request/response HTTP; HAL Explorer giúp khám phá API trực quan. Cả hai đều dựa trên các link mà server trả về.

## 1. Tài nguyên gốc trong Spring Data REST

Spring Data REST xuất repository thành HTTP resource. Repository quản lý Book có thể tạo collection resource **/books** và item resource **/books/1**. API root nằm ở cấp cao nhất và chứa các link dẫn tới tài nguyên khác.

Ví dụ response root theo HAL:

~~~json
{
  "_links": {
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
~~~

Đây là response minh họa; tên relation và URL thực tế phụ thuộc repository, base path và cấu hình ứng dụng.

- **_links:** tập hợp các liên kết server công bố.
- **books:** relation (rel), mô tả ý nghĩa liên kết; trong ví dụ dẫn tới collection sách.
- **href:** URI đích của liên kết.
- **profile:** relation có thể dẫn tới metadata/profile mô tả resource.
- **self:** relation thường trỏ tới chính resource hiện tại.

Root resource không phải collection. Root chỉ đường tới collection hoặc chức năng; collection mới chứa các item, thường nằm trong **_embedded**.

Ngay cả khi collection rỗng, root vẫn có thể trả link **books**. Do đó, không cần tạo dữ liệu trước để kiểm tra repository có được xuất thành API hay không.

## 2. Chuẩn bị ứng dụng

Nếu đã có ứng dụng Spring Data REST đang chạy, có thể dùng URL của ứng dụng hiện tại. Với dự án Spring Boot 3.x và Java 17+, các dependency cơ bản có thể khai báo như sau:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ repository:

~~~java
package com.example.library;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

**Book** là domain type và **Long** là ID type. Spring Data REST dùng repository để tạo collection resource. Entity Book cần được định nghĩa và mapping theo persistence provider.

Có thể đặt base path trong **src/main/resources/application.properties**:

~~~properties
spring.data.rest.base-path=/api
~~~

Khi đó API root nằm dưới **/api**. Nếu không đặt base path, API thường được xuất tại root của ứng dụng.

Khởi động bằng Maven wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Chờ đến khi Spring Boot báo ứng dụng đã khởi động và server đang lắng nghe, ví dụ cổng 8080.

## 3. Gửi GET tới API root bằng curl

Với base path **/api**, chạy:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Trong PowerShell, gọi **curl.exe** để tránh alias **curl** có thể trỏ tới Invoke-WebRequest:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Các tùy chọn:

- **-i:** in cả response headers và response body.
- **-H:** gửi HTTP header tùy chỉnh.
- **Accept: application/hal+json:** yêu cầu representation HAL JSON.
- **URL:** URI API root, bao gồm base path nếu đã cấu hình.

Response thành công thường có status **200 OK**, Content-Type tương ứng HAL JSON, ví dụ **application/hal+json**, và body chứa relation trong **_links**.

Ví dụ output rút gọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "_links": {
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
~~~

Header thực tế có thể có thêm Date, Cache-Control, Vary, Transfer-Encoding hoặc header bảo mật. Không yêu cầu response phải giống hoàn toàn ví dụ.

### Đọc status, headers và body

Kiểm tra ba phần:

1. **Status line:** request có thành công không?
2. **Response headers:** server trả media type nào?
3. **Response body:** có phải HAL document và có relation mong đợi không?

Một số status thường gặp:

| Status | Điều cần kiểm tra |
|---|---|
| 200 OK | Root resource trả response thành công |
| 301/302/307/308 | Kiểm tra header Location và đích chuyển hướng |
| 401 Unauthorized | Request chưa được xác thực theo yêu cầu |
| 403 Forbidden | Request bị từ chối bởi chính sách truy cập |
| 404 Not Found | Có thể sai URL/base path hoặc root không được map tại đường dẫn đó |
| 406 Not Acceptable | Media type trong Accept không được hỗ trợ |
| 500 Internal Server Error | Kiểm tra log server và exception |

401/403 không tự chứng minh repository không được xuất. Tương tự, 404 không chứng minh repository thiếu CRUD method. Cần phân biệt lỗi đường dẫn, xác thực, phân quyền và cấu hình resource.

### Dùng verbose mode

Khi cần xem request headers, kết nối hoặc redirect:

~~~bash
curl -v -H "Accept: application/hal+json" http://localhost:8080/api
~~~

**-v** hiển thị thông tin chẩn đoán như request line, request headers và thông tin kết nối. Nếu chỉ cần response headers và body, **-i** thường dễ đọc hơn. Không nhầm dòng debug của curl với JSON body.

## 4. Đọc và theo link trong HAL response

Sau khi GET root thành công, đọc **_links**. Mỗi tên relation đại diện cho một hướng điều hướng.

Ví dụ relation **books**:

~~~json
{
  "books": {
    "href": "http://localhost:8080/api/books"
  }
}
~~~

Dùng đúng URI trong **href** để gửi request tiếp theo:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/books
~~~

Response collection thường có:

- **_embedded:** danh sách item được nhúng trong collection.
- **_links.self:** link tới collection hiện tại.
- **_links.profile:** link tới metadata của collection.
- **_links.search:** link tới các query method được công bố.
- **page:** số trang, kích thước trang và tổng số phần tử/trang.

Ví dụ collection rỗng:

~~~json
{
  "_embedded": {
    "books": []
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books?page=0&size=20"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/books"
    },
    "search": {
      "href": "http://localhost:8080/api/books/search"
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

Đây là response minh họa. Khi có dữ liệu, item xuất hiện trong **_embedded.books**; tên key phụ thuộc collection relation.

### Trích xuất link bằng jq

Nếu đã cài **jq**, có thể liệt kê relation và href:

~~~bash
curl -sS -H "Accept: application/hal+json" http://localhost:8080/api \
  | jq -r '._links | to_entries[] | "\(.key)\t\(.value.href)"'
~~~

Output minh họa:

~~~text
books    http://localhost:8080/api/books
profile  http://localhost:8080/api/profile
~~~

Một link có thể là URI template và có thuộc tính **templated: true**:

~~~json
{
  "self": {
    "href": "http://localhost:8080/api/books{?page,size,sort}",
    "templated": true
  }
}
~~~

Dấu ngoặc nhọn biểu diễn các biến URI template. HAL Explorer hiểu template và hiển thị hộp thoại để nhập biến. curl không tự mở rộng URI template; khi dùng curl, cần mở rộng theo đúng tên biến được server công bố hoặc dùng thư viện hiểu URI Template. Không tự giả định tên tham số nếu response không cung cấp.

Nếu đã xác nhận collection chấp nhận **page** và **size**, có thể gửi query parameters bằng curl:

~~~bash
curl -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "page=0" \
  --data-urlencode "size=10" \
  http://localhost:8080/api/books
~~~

**-G** chuyển các giá trị **--data-urlencode** thành query string của GET. Dùng đúng tên biến được công bố trong link hoặc tài liệu API.

## 5. Cài đặt HAL Explorer

HAL Explorer là giao diện web để duyệt response theo HAL và HAL-FORMS. Nó đọc link, điều hướng collection/item, hiển thị headers/body và hỗ trợ gửi request mà API công bố.

Với Spring Data REST hiện đại, thêm dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-rest-hal-explorer</artifactId>
</dependency>
~~~

Với Gradle:

~~~gradle
runtimeOnly 'org.springframework.data:spring-data-rest-hal-explorer'
~~~

Nếu dùng Spring Boot dependency management hoặc Spring Data BOM, thường không cần chỉ định version riêng. Giữ các phiên bản Spring Boot và Spring Data tương thích với nhau.

Dependency tự cấu hình HAL Explorer để được phục vụ khi mở URI gốc của ứng dụng trong trình duyệt. Nếu ứng dụng có base path như **/api**, mở API root theo cấu hình đó; integration có thể chuyển hướng tới giao diện Explorer.

HAL Explorer hỗ trợ khám phá thủ công. Nó không thay thế API contract, automated tests hoặc kiểm tra quyền truy cập ở server.

## 6. Khám phá root resource bằng HAL Explorer

Sau khi thêm dependency và khởi động ứng dụng:

1. Mở trình duyệt tới địa chỉ ứng dụng, ví dụ **http://localhost:8080/**. Nếu API dùng base path, nhập API root tương ứng, ví dụ **http://localhost:8080/api**.
2. HAL Explorer hiển thị URI hiện tại và danh sách link mà response HAL cung cấp.
3. Chọn relation **books** để điều hướng tới collection.
4. Quan sát response headers và response body trong phần inspector.
5. Từ collection, chọn link tới item hoặc relation **search** nếu được công bố.
6. Khi gặp URI template, nhập tham số trong hộp thoại Explorer hiển thị.

Giao diện thường có hai khu vực:

- **Explorer:** URI hiện tại, các link, method/action có thể thực hiện và thông tin request.
- **Inspector:** response headers và response body của request vừa gửi.

Explorer đọc link trong HAL response và trình bày thành danh sách có thể thao tác. Nút GET điều hướng tới resource. Các nút khác có thể mở thao tác tạo, cập nhật hoặc xóa nếu API công bố và cho phép chúng.

### Quan sát một request

Khi chọn link **books**, kiểm tra:

- URI được điều hướng tới có đúng với **href** trong response root không?
- HTTP method là GET hay method khác?
- Status response có thành công không?
- Content-Type có phải HAL JSON không?
- Collection có **_embedded** và **_links** không?
- Link **self**, **profile** và **search** có xuất hiện theo cấu hình mong đợi không?

Khi chọn item, kiểm tra link **self** và link association nếu domain model có quan hệ. Explorer cho thấy đường đi server công bố; nó không bảo đảm mọi thao tác nghiệp vụ đều hợp lệ.

### Thử URI template

Nếu link có **templated: true**, Explorer có thể mở hộp thoại để nhập page, size, sort hoặc biến khác. Nhập giá trị và quan sát URL cuối cùng được gửi.

Nếu không nhập biến nào, Explorer có thể bỏ qua các biến template. Điều này hữu ích khi muốn xem collection với giá trị mặc định, nhưng hãy kiểm tra URL/response để biết server đã áp dụng mặc định nào.

### Thử thao tác ghi

Explorer có thể cung cấp giao diện cho POST, PUT, PATCH hoặc DELETE. Với thao tác không phải GET, nó có thể hiển thị method, các field suy ra từ metadata và vùng nhập JSON body.

Chỉ thử thao tác ghi trên môi trường phát triển hoặc dữ liệu thử nghiệm:

- POST tới collection có thể tạo bản ghi mới.
- PUT tới item có thể thay thế dữ liệu.
- PATCH tới item có thể cập nhật một phần.
- DELETE có thể xóa item.

Trước khi gửi, kiểm tra URI, method, headers và body. POST hoặc DELETE có thể làm thay đổi dữ liệu nếu đang kết nối nhầm môi trường.

## 7. Đối chiếu curl và HAL Explorer

| Tiêu chí | curl | HAL Explorer |
|---|---|---|
| Gửi GET tới root | Có | Có |
| Hiển thị status và headers | Có, qua -i hoặc -v | Có, trong inspector |
| Đọc JSON HAL | Có, đọc trực tiếp hoặc qua jq | Có, tự phân tích link |
| Theo link | Copy href hoặc viết script | Chọn relation trong giao diện |
| URI template | Tự mở rộng hoặc dùng thư viện | Có hộp thoại nhập biến |
| POST/PUT/PATCH/DELETE | Qua option HTTP và body | Có giao diện nếu API công bố |
| Tự động hóa CI | Rất phù hợp | Không phải mục đích chính |
| Khám phá trực quan | Ít trực quan | Phù hợp để khám phá thủ công |

Chọn curl khi cần tái hiện request, kiểm tra header chính xác, viết script hoặc chạy kiểm tra trong pipeline. Chọn HAL Explorer khi cần quan sát link, chuyển qua resource và thử nhanh API chưa quen thuộc.

## 8. Quy trình kiểm tra từ đầu đến cuối

Giả sử ứng dụng chạy tại **http://localhost:8080** và Spring Data REST có base path **/api**.

**Bước 1 — kiểm tra root:**

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Kỳ vọng: response thành công, Content-Type HAL JSON và body có **_links**.

**Bước 2 — xác nhận collection link:**

Đọc relation **books** và lấy nguyên URI trong **href**. Không tự dựng path nếu link đã có sẵn.

**Bước 3 — gọi collection:**

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books
~~~

Kỳ vọng: collection HAL có **_links**; nếu có phần tử thì chúng xuất hiện trong **_embedded**.

**Bước 4 — mở profile:**

Dùng link **profile** nhận được từ response collection hoặc root. Không mặc định URL profile ở mọi ứng dụng giống nhau.

**Bước 5 — mở HAL Explorer:**

Mở root URI trong trình duyệt. Chọn **books**, quan sát request và response trong Explorer/Inspector. Theo link server cung cấp để đi tiếp.

**Bước 6 — kiểm tra phân trang:**

Nếu link collection có URI template, dùng Explorer để nhập tham số. Với curl, mở rộng đúng các biến được công bố rồi gửi GET.

**Bước 7 — xác nhận kết quả:**

Ghi nhận status, Content-Type, relation, href, dữ liệu collection và thông tin phân trang. Nếu kết quả không như mong đợi, so sánh request curl với request Explorer gửi để tìm khác biệt về URI, header hoặc trạng thái xác thực.

## 9. Lỗi thường gặp và cách xử lý

### curl trả về 404

- Kiểm tra host và port.
- Kiểm tra ứng dụng đã khởi động chưa.
- Kiểm tra **spring.data.rest.base-path**.
- Gọi đúng API root, không nhầm URL giao diện quản trị hoặc collection cụ thể.
- Dùng link **href** từ response trước đó.

### curl trả về 406

Kiểm tra header **Accept**. Với HAL JSON, thử:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Nếu endpoint chỉ hỗ trợ media type khác, hãy xem contract của endpoint thay vì liên tục đổi URL.

### curl trả về 401 hoặc 403

Kiểm tra cấu hình Spring Security, thông tin xác thực và quyền truy cập. HAL Explorer chạy trong trình duyệt cũng chịu ảnh hưởng của session, cookie, token và chính sách bảo mật.

### Body không có _links

Kiểm tra:

- Có đang gọi đúng Spring Data REST API root không?
- Content-Type có phải HAL JSON không?
- Request có bị chuyển tới controller hoặc static resource khác không?
- Repository có được export không?
- Header Accept có đúng không?

### HAL Explorer không xuất hiện

- Xác nhận dependency **spring-data-rest-hal-explorer** nằm trong runtime classpath.
- Kiểm tra dependency version tương thích với Spring Data REST.
- Khởi động lại ứng dụng sau khi thêm dependency.
- Mở đúng URI root của ứng dụng/API và theo redirect nếu có.
- Kiểm tra log server và response của URI root nếu giao diện không tải được.

### Explorer hiển thị link nhưng request thất bại

Kiểm tra URI, method, header, body, authentication và status code. Link được công bố chỉ là hướng dẫn điều hướng; server vẫn có thể từ chối request vì validation, authorization hoặc trạng thái nghiệp vụ.

### Link URI template không hoạt động

Kiểm tra **templated: true**, tên biến và cách mở rộng URI. Explorer có hộp thoại cho biến; với curl, cần mở rộng template đúng cú pháp. Không gửi nguyên dấu ngoặc nhọn như thể đó là URL hoàn chỉnh.

## 10. Checklist kiểm tra API root

- [ ] Ứng dụng Spring Boot đã khởi động và đúng port.
- [ ] Đã xác định base path của Spring Data REST.
- [ ] GET root trả status phù hợp.
- [ ] Content-Type là HAL JSON theo yêu cầu.
- [ ] Body có **_links**.
- [ ] Đã đọc relation và **href** thực tế.
- [ ] Đã theo link collection và kiểm tra response.
- [ ] Đã kiểm tra link **profile** nếu cần metadata.
- [ ] HAL Explorer đã được thêm dependency và mở được.
- [ ] Explorer hiển thị links, request method, headers và body.
- [ ] URI template được xử lý đúng.
- [ ] Thao tác ghi chỉ được thử trên môi trường/dữ liệu thử nghiệm.
- [ ] Đã phân biệt lỗi URL, media type, authentication và authorization.

## 11. Kết luận

API root là điểm bắt đầu để khám phá một Spring Data REST API. Dùng curl để kiểm tra HTTP status, headers, media type và body HAL một cách chính xác. Đọc **_links**, lấy URI trong **href** và theo relation để đi tới collection, item hoặc profile.

HAL Explorer cung cấp giao diện trực quan cho cùng luồng khám phá: nó đọc link, hiểu URI template, hiển thị response và hỗ trợ thử những method mà API công bố. Kết hợp hai công cụ giúp kiểm tra API vừa có thể tái hiện bằng command line, vừa dễ quan sát trong quá trình phát triển.

## Tài liệu tham khảo

- [Spring Data REST Reference — Resource Discoverability](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — The HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html)
- [Spring Data REST — Getting Started](https://spring.io/guides/gs/accessing-data-rest)
- [HAL Explorer Reference Documentation](https://toedter.github.io/hal-explorer/release/reference-doc/)
