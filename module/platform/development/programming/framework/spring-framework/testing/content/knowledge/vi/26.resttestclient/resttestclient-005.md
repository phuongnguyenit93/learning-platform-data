# Chuẩn bị URI, header và body trước `exchange()`

`RestTestClient` cung cấp API đồng bộ, dạng fluent để gửi HTTP request và kiểm tra response trong các bài kiểm thử Spring. Trước khi gọi `exchange()`, test cần mô tả đầy đủ request: HTTP method, URI, query parameter, header và body nếu có. `exchange()` là điểm thực hiện request; sau đó test mới chuyển sang các assertion như `expectStatus()`, `expectHeader()` và `expectBody()`.

Việc chuẩn bị request rõ ràng giúp test phản ánh đúng HTTP contract của endpoint. URI xác định tài nguyên và tham số; header mô tả metadata như định dạng body, định dạng response mong muốn, thông tin xác thực hoặc correlation ID; body mang dữ liệu nghiệp vụ mà server cần xử lý.

## 1. Cấu trúc một request RestTestClient

Một request cơ bản có dạng:

```java
restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-100")
        .body(new CreateProductRequest("Notebook", 12.5))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(ProductView.class)
        .value(product -> assertThat(product.name()).isEqualTo("Notebook"));
```

Chuỗi request có thể chia thành hai phần:

| Phần | Các thao tác | Mục đích |
| --- | --- | --- |
| Chuẩn bị request | `post()`, `uri()`, `header()`, `accept()`, `contentType()`, `body()` | Xác định chính xác nội dung cần gửi |
| Thực hiện và kiểm tra | `exchange()`, `expectStatus()`, `expectHeader()`, `expectBody()` | Gửi request và xác nhận response |

Trước `exchange()`, các method đang cấu hình một request. Khi gọi `exchange()`, client mới thực hiện request và nhận response. Không nên chia một request thành nhiều lần `exchange()` nếu mục tiêu là kiểm tra một thao tác nghiệp vụ duy nhất.

`RestTestClient` là API đồng bộ được giới thiệu trong Spring Framework 7.0. Các ví dụ trong tài liệu dùng API `body(...)` theo phong cách `RestClient`. Nếu dự án đang dùng Spring Framework 6.x, cần dùng API có sẵn ở phiên bản đó như `MockMvc`, `WebTestClient` hoặc các công cụ kiểm thử tương ứng; chỉ đổi import không thể tạo ra API chưa có trong dependency.

## 2. Chọn HTTP method trước khi chuẩn bị URI

Client bắt đầu bằng method phù hợp với thao tác HTTP:

```java
restTestClient.get()
restTestClient.head()
restTestClient.post()
restTestClient.put()
restTestClient.patch()
restTestClient.delete()
restTestClient.options()
```

Method là một phần của contract endpoint. Ví dụ:

| Method | Mục đích thường gặp | Có request body? |
| --- | --- | --- |
| `GET` | Đọc tài nguyên | Thông thường không |
| `HEAD` | Đọc metadata của tài nguyên | Không |
| `POST` | Tạo tài nguyên hoặc thực hiện command | Thường có thể có |
| `PUT` | Thay thế hoặc cập nhật toàn bộ tài nguyên | Thường có |
| `PATCH` | Cập nhật một phần tài nguyên | Thường có |
| `DELETE` | Xóa tài nguyên | Thường không |
| `OPTIONS` | Hỏi các phương thức hoặc khả năng được hỗ trợ | Thường không |

Ví dụ GET:

```java
restTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk();
```

Ví dụ DELETE:

```java
restTestClient.delete()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isNoContent();
```

Không phải method nào cũng cần body. Nếu request không có body, thường không cần đặt `Content-Type`. Với request có body, hãy chọn method và media type đúng với contract của API.

## 3. Chuẩn bị URI bằng đường dẫn và URI template

`uri(...)` xác định endpoint mà request sẽ gửi tới. Khi client đã có `baseUrl`, có thể dùng đường dẫn tương đối:

```java
RestTestClient restTestClient = RestTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

restTestClient.get()
        .uri("/api/products")
        .exchange();
```

URI template cho phép đặt biến trong path thay vì ghép chuỗi thủ công:

```java
restTestClient.get()
        .uri("/api/products/{id}", 42)
        .exchange()
        .expectStatus().isOk();
```

Có thể truyền map cho nhiều biến:

```java
Map<String, Object> variables = Map.of(
        "category", "stationery",
        "id", 42);

restTestClient.get()
        .uri("/api/categories/{category}/products/{id}", variables)
        .exchange();
```

URI template giúp tách phần cấu trúc URL khỏi dữ liệu đầu vào. URI builder có thể encode các biến theo quy tắc URI phù hợp; cách này tránh nhiều lỗi do dấu cách, dấu `&`, dấu `/` hoặc ký tự Unicode khi tự nối chuỗi.

Nếu cần truyền một URI đã được tạo trước, có thể dùng `URI`:

```java
URI uri = URI.create("http://localhost:8080/api/products/42");

restTestClient.get()
        .uri(uri)
        .exchange();
```

URI tuyệt đối thường hữu ích khi test kết nối server thật hoặc cần xác định rõ scheme, host và port. Khi test bind vào mock infrastructure, nên sử dụng base URL và đường dẫn phù hợp với cấu hình của client.

## 4. Thêm query parameter bằng URI builder

Query parameter là phần sau dấu `?` trong URI, thường dùng cho tìm kiếm, lọc, sắp xếp hoặc phân trang. Có thể xây dựng URI bằng callback `UriBuilder`:

```java
restTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/products")
                .queryParam("category", "stationery")
                .queryParam("page", 0)
                .queryParam("size", 20)
                .build())
        .exchange()
        .expectStatus().isOk();
```

Khi cần path variable cùng query parameter:

```java
restTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/categories/{category}/products")
                .queryParam("sort", "name,asc")
                .queryParam("active", true)
                .build("stationery"))
        .exchange();
```

Nếu giá trị query có ký tự đặc biệt, nên để URI builder thực hiện encoding. Ví dụ từ khóa `blue pen & pencil` phải được encode đúng để dấu `&` không bị hiểu nhầm là dấu phân cách giữa hai parameter.

Không nên tự nối chuỗi như sau:

```java
String uri = "/api/search?q=" + keyword + "&page=" + page;
```

Cách nối chuỗi dễ tạo URI sai khi `keyword` chứa dấu cách, dấu `&`, dấu `#` hoặc ký tự cần encode. URI builder giúp biểu diễn từng thành phần riêng biệt và xử lý encoding nhất quán.

## 5. Đặt base URL và phân biệt URI tương đối/tuyệt đối

Base URL được cấu hình khi tạo client, còn `uri(...)` thường chỉ cần phần path:

```java
RestTestClient client = RestTestClient.bindToServer()
        .baseUrl("https://api.example.test")
        .build();

client.get()
        .uri("/v1/products")
        .exchange();
```

Điều này giúp test không phải lặp host và port ở mọi request. Có thể dùng cấu hình base URL theo môi trường test, chẳng hạn port ngẫu nhiên của server đang chạy.

Với URI tuyệt đối, scheme và authority đã nằm trong URI:

```java
client.get()
        .uri(URI.create("https://api.example.test/v1/products"))
        .exchange();
```

Hãy nhất quán cách dùng base URL và URI tuyệt đối trong một test suite. Nếu vừa cấu hình base URL vừa tạo URI tuyệt đối, URI tuyệt đối xác định host đích của request. Điều này đặc biệt quan trọng khi client có interceptor, authentication hoặc routing phụ thuộc host.

## 6. Thiết lập request header

Header mang metadata của HTTP message. Có thể đặt một header bằng `.header(...)`:

```java
restTestClient.get()
        .uri("/api/products/42")
        .header("X-Request-Id", "req-100")
        .header("X-Client", "catalog-test")
        .exchange();
```

Nếu cần thiết lập nhiều header cùng lúc, dùng `.headers(...)` để thao tác với `HttpHeaders`:

```java
restTestClient.get()
        .uri("/api/products/42")
        .headers(headers -> {
            headers.set("X-Request-Id", "req-100");
            headers.set("X-Client", "catalog-test");
            headers.setBearerAuth("test-access-token");
        })
        .exchange();
```

`set(...)` đặt hoặc thay thế giá trị của header; `add(...)` thêm một giá trị vào danh sách hiện có. Phân biệt hai thao tác này khi header cho phép nhiều giá trị, ví dụ `Accept` hoặc một số header tùy chỉnh.

Có thể truyền nhiều giá trị cho cùng header:

```java
restTestClient.get()
        .uri("/api/products")
        .header("X-Feature", "search", "recommendations")
        .exchange();
```

Chỉ nên thêm header mà endpoint hoặc contract của client thực sự cần. Việc thêm nhiều header không liên quan làm test khó đọc và có thể che giấu dependency ngoài ý muốn.

## 7. Phân biệt `Accept` và `Content-Type`

Hai header thường được chuẩn bị cùng request nhưng mô tả hai hướng dữ liệu khác nhau:

| Header | Mô tả | API thiết lập |
| --- | --- | --- |
| `Accept` | Media type client muốn nhận trong response | `.accept(MediaType...)` |
| `Content-Type` | Media type của request body đang gửi | `.contentType(MediaType)` |

Ví dụ gửi JSON và yêu cầu JSON:

```java
restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreateProductRequest("Notebook", 12.5))
        .exchange();
```

Trong ví dụ, `Content-Type` cho biết request body là JSON; `Accept` cho biết client muốn response là JSON. Đặt `Accept` không làm body tự trở thành JSON, và đặt `Content-Type` không buộc server trả JSON.

Có thể yêu cầu nhiều response media type:

```java
restTestClient.get()
        .uri("/api/products/42")
        .accept(MediaType.APPLICATION_JSON, MediaType.APPLICATION_XML)
        .exchange();
```

Server chọn representation dựa trên `Accept`, mapping `produces` và converter được cấu hình. Nếu endpoint không hỗ trợ media type mà client chấp nhận, response có thể là 406 Not Acceptable.

Với request không có body như GET, thường chỉ cần `Accept` nếu muốn ràng buộc định dạng response. Không cần thêm `Content-Type: application/json` khi không gửi JSON body.

## 8. Header xác thực và thông tin request

API có thể yêu cầu thông tin xác thực hoặc metadata để xử lý request. Dùng `headers(...)` giúp thiết lập các giá trị liên quan ở một chỗ:

```java
restTestClient.get()
        .uri("/api/me")
        .headers(headers -> {
            headers.setBearerAuth("test-token");
            headers.set("X-Correlation-Id", "corr-202");
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .exchange()
        .expectStatus().isOk();
```

Nếu API dùng Basic authentication, có thể đặt header tương ứng:

```java
restTestClient.get()
        .uri("/api/private")
        .headers(headers -> headers.setBasicAuth("test-user", "test-password"))
        .exchange()
        .expectStatus().isOk();
```

Giá trị xác thực trong test nên là credential giả dành riêng cho môi trường kiểm thử. Nếu ứng dụng dùng Spring Security, header chỉ là một phần của request; test cần cấu hình authentication provider hoặc test security context tương ứng để xác nhận hành vi bảo mật thật.

Các header có thể dùng cho conditional request:

```java
restTestClient.get()
        .uri("/api/products/42")
        .header(HttpHeaders.IF_NONE_MATCH, "\"product-42-v1\"")
        .exchange()
        .expectStatus().isNotModified();
```

Ví dụ này giả định endpoint hỗ trợ ETag và trả 304 khi tài nguyên chưa thay đổi. Conditional header chỉ nên đưa vào test khi endpoint có contract tương ứng.

## 9. Gửi body dạng object

Với request JSON, có thể truyền DTO trực tiếp qua `.body(...)`:

```java
CreateProductRequest request = new CreateProductRequest("Notebook", 12.5);

restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(request)
        .exchange()
        .expectStatus().isCreated();
```

Client chọn `HttpMessageConverter` phù hợp để serialize object thành HTTP body. Với JSON, ứng dụng test thường cần Jackson và converter JSON. Kiểu Java cần được hỗ trợ bởi converter, ví dụ DTO, record, map hoặc collection.

`Content-Type` rất quan trọng khi serialize object. Nếu body là object nhưng media type không phù hợp hoặc không có converter ghi kiểu đó, request có thể không được tạo như mong muốn và client có thể báo lỗi ghi message trước khi request tới server.

Có thể gửi chuỗi hoặc byte array khi muốn kiểm soát body chính xác:

```java
String json = """
        {"name":"Notebook","price":12.5}
        """;

restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(json)
        .exchange();
```

Hoặc:

```java
byte[] payload = json.getBytes(StandardCharsets.UTF_8);

restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(payload)
        .exchange();
```

Khi gửi chuỗi hoặc byte array, test chịu trách nhiệm bảo đảm nội dung thực sự đúng định dạng đã khai báo. Việc đặt `Content-Type: application/json` không tự kiểm tra chuỗi có phải JSON hợp lệ hay không.

## 10. Gửi form URL-encoded

Form URL-encoded thường dùng khi endpoint nhận dữ liệu theo dạng `application/x-www-form-urlencoded`. Có thể chuẩn bị dữ liệu bằng `MultiValueMap`:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("username", "lan");
form.add("password", "example-password");

restTestClient.post()
        .uri("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(form)
        .exchange()
        .expectStatus().is3xxRedirection();
```

`MultiValueMap` cho phép một key có nhiều giá trị, phù hợp với form có checkbox cùng tên hoặc field lặp. `FormHttpMessageConverter` có thể serialize map thành form body khi được đăng ký.

Không nên gửi form map với `Content-Type: application/json`. Kiểu dữ liệu Java có thể là map trong cả hai trường hợp, nhưng media type quyết định cách converter biểu diễn dữ liệu trên HTTP.

## 11. Gửi multipart và file upload

Đối với upload file, request thường dùng `multipart/form-data`. Có thể xây dựng multipart data bằng `MultiValueMap<String, Object>`:

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("description", "Product manual");
parts.add("file", new ByteArrayResource(
        "manual content".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "manual.txt";
    }
});

restTestClient.post()
        .uri("/api/documents")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(parts)
        .exchange()
        .expectStatus().isCreated();
```

`ByteArrayResource` cung cấp nội dung file trong bộ nhớ; override `getFilename()` để phần multipart có tên file. Có thể dùng `FileSystemResource` hoặc `ClassPathResource` khi file fixture đã tồn tại trong test resources.

Không nên tự đặt boundary thủ công khi client/converter đang tạo multipart body. Boundary là một phần của `Content-Type` multipart và phải khớp với delimiter trong body; converter cần quản lý chúng đồng bộ.

Nếu endpoint nhận nhiều file hoặc nhiều part cùng tên, `MultiValueMap` cho phép thêm nhiều giá trị cho một key. Nên kiểm tra cả tên part, filename, content type của part và nội dung file theo contract của endpoint.

## 12. Thiết lập header có điều kiện và giá trị lặp

Một số header có thể có nhiều giá trị hoặc cần thay đổi tùy tình huống test. Dùng `headers(...)` cho phép xử lý logic trước khi gửi:

```java
restTestClient.get()
        .uri("/api/products")
        .headers(headers -> {
            headers.setAccept(List.of(
                    MediaType.APPLICATION_JSON,
                    MediaType.APPLICATION_XML));
            headers.set("X-Client-Version", "2");
            if (includeExperimentalFeature) {
                headers.add("X-Feature", "experimental");
            }
        })
        .exchange();
```

`set(...)` thay thế danh sách giá trị của header bằng giá trị mới; `add(...)` thêm một giá trị. Dùng đúng thao tác để tránh vô tình gửi header trùng hoặc xóa giá trị đã được thiết lập bởi cấu hình chung.

Khi có header mặc định từ interceptor hoặc client configuration, cần xác định header nào thuộc cấu hình dùng chung và header nào thuộc request cụ thể. Test nên chủ động override khi contract yêu cầu một giá trị đặc biệt.

## 13. Kết hợp URI, header và body trong một ví dụ hoàn chỉnh

Giả sử endpoint tạo đơn hàng nhận JSON, hỗ trợ correlation ID và trả về JSON cùng header `Location`:

```java
OrderCommand command = new OrderCommand(
        "customer-42",
        List.of(new OrderLine("BK-01", 2)));

restTestClient.post()
        .uri(uriBuilder -> uriBuilder
                .path("/api/customers/{customerId}/orders")
                .queryParam("notify", false)
                .build("customer-42"))
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers -> {
            headers.set("X-Correlation-Id", "order-test-001");
            headers.setBearerAuth("test-token");
        })
        .body(command)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectHeader().exists(HttpHeaders.LOCATION)
        .expectBody(OrderView.class)
        .value(order -> {
            assertThat(order.customerId()).isEqualTo("customer-42");
            assertThat(order.lines()).hasSize(1);
        });
```

Ví dụ thể hiện rõ từng phần của HTTP contract:

- Path variable xác định khách hàng sở hữu đơn hàng.
- Query parameter điều khiển tùy chọn thông báo.
- `Content-Type` mô tả request body là JSON.
- `Accept` yêu cầu response JSON.
- Correlation ID hỗ trợ truy vết request.
- Bearer token đại diện thông tin xác thực của test.
- DTO được serialize thành request body.
- `exchange()` gửi request trước khi kiểm tra response.

## 14. Những điều cần tránh khi chuẩn bị request

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Ghép query string bằng nối chuỗi | URI sai khi dữ liệu chứa ký tự đặc biệt | Dùng URI template hoặc `UriBuilder` |
| Nhầm `Accept` với `Content-Type` | Server chọn sai converter hoặc trả 406/415 | `Accept` cho response; `Content-Type` cho request body |
| Gửi DTO nhưng không có converter phù hợp | Client không serialize được body | Thêm converter/codec cần thiết và khai báo media type |
| Gửi form map với media type JSON | Body không theo contract form | Dùng `APPLICATION_FORM_URLENCODED` |
| Tự tạo multipart boundary không khớp body | Server không parse được multipart | Để converter quản lý boundary |
| Thêm cùng header nhiều lần ngoài ý muốn | Server nhận nhiều giá trị khác dự kiến | Dùng `set` khi muốn thay thế, `add` khi muốn thêm |
| Đặt body cho GET mà endpoint không hỗ trợ | Hành vi không nhất quán giữa client/server | Chỉ gửi body khi contract yêu cầu |
| Gọi `exchange()` trước khi cấu hình xong | Request được thực hiện với thông tin thiếu | Hoàn tất URI, headers và body trước `exchange()` |
| Dùng URI tuyệt đối không đúng host | Request đi tới đích khác | Kiểm tra base URL và URI đích |

Một lỗi phổ biến là test chỉ kiểm tra response nhưng gửi request không giống client thật. Ví dụ, test gửi JSON object nhưng bỏ `Content-Type`, trong khi client production luôn gửi JSON. Khi đó test có thể không tái hiện đúng lỗi mà endpoint gặp trong môi trường thật. Hãy mô tả request theo đúng contract, bao gồm method, URI, media type và header bắt buộc.

## 15. Nguyên tắc tổ chức request specification

1. Chọn HTTP method đúng với hành vi endpoint.
2. Dùng URI template cho path variable và `UriBuilder` cho query parameter phức tạp.
3. Cấu hình base URL một lần khi có thể, giữ URI request ngắn và rõ.
4. Dùng `.header(...)` cho header đơn giản và `.headers(...)` khi cần thao tác nhiều header.
5. Phân biệt `Accept` với `Content-Type`; chỉ đặt Content-Type khi request có body cần mô tả.
6. Chọn body Java, text, byte array, form map hoặc multipart map theo contract endpoint.
7. Bảo đảm converter phù hợp có mặt để serialize object thành request body.
8. Hoàn thành toàn bộ phần chuẩn bị request trước khi gọi `exchange()`.
9. Gửi một request cho mỗi hành động nghiệp vụ rồi nối các assertion trên response đó.
10. Khi test thất bại, kiểm tra request thực tế trước khi kết luận lỗi nằm ở controller.

Trong `RestTestClient`, phần chuẩn bị URI, header và body quyết định chính xác request mà server nhận được. URI xác định tài nguyên, header mô tả metadata và media type, còn body mang dữ liệu cần xử lý. Khi cấu hình các thành phần này một cách tường minh trước `exchange()`, test trở thành một ví dụ rõ ràng về HTTP contract mà ứng dụng cần hỗ trợ.
