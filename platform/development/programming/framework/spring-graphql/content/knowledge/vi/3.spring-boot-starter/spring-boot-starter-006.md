# GraphQL HTTP endpoint

Spring for GraphQL cung cấp HTTP endpoint để client gửi một GraphQL operation đến server và nhận kết quả thực thi dưới dạng JSON. Khi dùng Spring Boot, `spring-boot-starter-graphql` tự cấu hình phần tích hợp GraphQL; ứng dụng cần thêm một web starter để chạy HTTP server.

Mặc định, endpoint có đường dẫn `/graphql`. Các operation như query và mutation đều đi qua endpoint này. Những method Java được đánh dấu `@QueryMapping` hoặc `@MutationMapping` xử lý các field trong GraphQL schema; chúng không tự tạo ra các URL HTTP riêng.

## 1. Luồng xử lý HTTP

Một request GraphQL đi qua các bước chính sau:

```mermaid
flowchart LR
    A[GraphQL client] -->|HTTP request| B[/graphql endpoint]
    B --> C[Spring for GraphQL]
    C --> D[GraphQL schema và resolver]
    D --> E[GraphQL result]
    E -->|JSON response| A
```

HTTP handler tiếp nhận request, chuyển GraphQL document cùng variables vào engine để kiểm tra và thực thi theo schema. Các controller của Spring for GraphQL cung cấp dữ liệu cho những field được yêu cầu. Kết quả trả về chứa `data`, `errors` hoặc cả hai.

Endpoint là ranh giới giao tiếp HTTP của GraphQL. Schema và resolver quyết định client có thể yêu cầu dữ liệu gì; đường dẫn `/graphql` quyết định client gửi request đến đâu.

## 2. Thêm dependency cho Spring Boot

Với Maven, thêm GraphQL starter và một web starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <!-- Dùng Spring MVC để phục vụ HTTP -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Nếu ứng dụng sử dụng reactive stack, có thể thay `spring-boot-starter-web` bằng `spring-boot-starter-webflux`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Với Gradle, các dependency tương ứng là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Chọn web starter theo kiến trúc của ứng dụng. Spring Boot dùng web stack đó để tạo HTTP server và đăng ký GraphQL handler. Nên để Spring Boot dependency management quản lý phiên bản các thư viện Spring tương thích với phiên bản Boot đang dùng.

## 3. Tạo schema và resolver tối thiểu

Spring Boot mặc định tìm GraphQL schema trong `src/main/resources/graphql/`. Tạo file `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    greeting(name: String!): String!
}
```

Schema khai báo một field `greeting`, nhận đối số `name` và trả về chuỗi không null. Tiếp theo, tạo controller xử lý field đó:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingController {

    @QueryMapping
    public String greeting(@Argument("name") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

`@QueryMapping` ánh xạ method vào field `greeting` của root type `Query`. `@Argument` lấy giá trị đối số cùng tên từ GraphQL request. Khi ứng dụng khởi động, Spring Boot nạp schema và đăng ký controller thông qua cơ chế auto-configuration và component scanning.

Ví dụ này dùng query để làm rõ đường đi từ HTTP request đến resolver. Mutation cũng được gửi đến cùng HTTP endpoint; resolver của mutation thường được khai báo bằng `@MutationMapping` và field tương ứng trong schema `type Mutation`.

## 4. Cấu hình đường dẫn endpoint

Nếu không khai báo cấu hình, Spring Boot sử dụng `/graphql`. Có thể đổi đường dẫn trong `src/main/resources/application.properties`:

```properties
spring.graphql.path=/api/graphql
```

Sau thay đổi này, client gửi request đến `/api/graphql`. Hãy cập nhật URL trong client, reverse proxy và cấu hình bảo mật tương ứng. Nếu ứng dụng còn có servlet context path hoặc được triển khai dưới một base path khác, URL bên ngoài có thể bao gồm cả phần prefix đó.

Spring Boot cũng có thể bật giao diện GraphiQL để thử query trong trình duyệt:

```properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
```

GraphiQL là công cụ hỗ trợ phát triển, không phải endpoint xử lý GraphQL thay thế cho `/graphql`. Chỉ bật giao diện này ở môi trường cần thiết và kiểm soát quyền truy cập nếu triển khai trên môi trường dùng chung.

Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.graphql.path` | Đường dẫn HTTP nhận GraphQL request; mặc định là `/graphql`. |
| `spring.graphql.schema.locations` | Vị trí tìm schema; mặc định là `classpath:graphql/**/`. |
| `spring.graphql.graphiql.enabled` | Bật hoặc tắt giao diện GraphiQL; mặc định tắt. |
| `spring.graphql.graphiql.path` | Đường dẫn phục vụ giao diện GraphiQL khi đã bật. |

Chỉ cần khai báo thuộc tính khi muốn thay đổi giá trị mặc định hoặc cấu hình rõ ràng theo từng profile.

## 5. Gửi GraphQL request qua HTTP

GraphQL HTTP request thường được gửi bằng `POST` với body JSON. Body có thể chứa các trường:

- `query`: GraphQL document cần thực thi.
- `variables`: object chứa giá trị cho các biến trong document.
- `operationName`: tên operation cần chọn khi document có nhiều operation.
- `extensions`: dữ liệu mở rộng tùy theo client và server.

Ví dụ gọi endpoint mặc định bằng `curl`:

```bash
curl http://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "query": "query Greeting($name: String!) { greeting(name: $name) }",
    "variables": { "name": "An" },
    "operationName": "Greeting"
  }'
```

Với schema và controller ở trên, response có dạng:

```json
{
  "data": {
    "greeting": "Xin chào, An!"
  }
}
```

`Content-Type` mô tả định dạng body gửi lên server. `Accept` cho biết client muốn nhận định dạng response nào. Trong ví dụ, cả request body và response đều dùng JSON.

HTTP GET cũng có thể được dùng cho query khi client và server hỗ trợ cách truyền tham số qua URL. Mutation không được gửi bằng GET; hãy dùng POST cho mutation. Với dữ liệu nhạy cảm hoặc variables dài, POST thường phù hợp hơn vì tham số của GET nằm trong URL và có thể xuất hiện trong access log hoặc lịch sử trình duyệt.

## 6. Phân biệt lỗi HTTP và lỗi GraphQL

Không phải mọi lỗi khi gọi GraphQL đều đồng nghĩa endpoint HTTP không hoạt động. Cần xem cả HTTP status lẫn nội dung response:

- Lỗi ở tầng HTTP hoặc request transport, chẳng hạn JSON không hợp lệ hay method không được hỗ trợ, có thể được phản hồi bằng mã HTTP lỗi.
- Lỗi cú pháp GraphQL, lỗi validation hoặc lỗi khi resolver thực thi được biểu diễn trong trường `errors` của GraphQL response.
- Một response có thể chứa cả `data` và `errors` nếu một phần field thực thi thành công còn field khác thất bại.

Ví dụ cấu trúc response khi một field gặp lỗi:

```json
{
  "data": {
    "greeting": null
  },
  "errors": [
    {
      "message": "Không thể xử lý yêu cầu",
      "path": ["greeting"]
    }
  ]
}
```

Đây là ví dụ minh họa cấu trúc, không phải thông báo lỗi cố định của Spring. Mã HTTP cụ thể phụ thuộc loại lỗi, HTTP handler và cấu hình ứng dụng. Vì vậy, client nên đọc `data` và `errors` thay vì chỉ kiểm tra status code.

## 7. Kiểm thử endpoint HTTP

Một kiểm thử chỉ gọi resolver hoặc GraphQL execution engine chưa xác nhận rằng HTTP endpoint đã được đăng ký đúng. Để kiểm tra cả đường dẫn và transport, có thể chạy ứng dụng trên cổng ngẫu nhiên và dùng `HttpGraphQlTester`.

Thêm thư viện test của Spring GraphQL nếu dự án chưa có:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

Ví dụ kiểm thử với Spring Boot:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphqlHttpEndpointTest {

    @Value("${local.server.port}")
    int port;

    @Test
    void queryCanBeExecutedOverHttp() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        HttpGraphQlTester tester = HttpGraphQlTester.create(webTestClient);

        tester.document("query Greeting($name: String!) { greeting(name: $name) }")
                .variable("name", "An")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Xin chào, An!");
    }
}
```

Kiểm thử này gửi request qua HTTP đến cổng mà Spring Boot khởi chạy, sau đó xác nhận giá trị trả về ở path `data.greeting`. Nếu chỉ muốn kiểm thử schema và resolver mà không cần kiểm tra HTTP transport, có thể dùng các công cụ kiểm thử GraphQL ở tầng execution; hai loại kiểm thử trả lời hai câu hỏi khác nhau.

## 8. Xử lý các lỗi cấu hình thường gặp

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Nhận `404 Not Found` | URL có đúng `spring.graphql.path`, port, context path và base path của ứng dụng không? |
| Nhận `405 Method Not Allowed` | Client có đang dùng HTTP method được endpoint hỗ trợ không? Mutation phải dùng POST. |
| Request bị từ chối trước khi vào GraphQL | Kiểm tra JSON, `Content-Type`, cấu hình CORS và Spring Security. |
| Response có `errors` | Kiểm tra tên field, kiểu đối số, schema và lỗi trong resolver. |
| Ứng dụng không khởi động được | Kiểm tra cú pháp schema, vị trí file schema, dependency và log auto-configuration. |
| Không mở được GraphiQL | Kiểm tra `spring.graphql.graphiql.enabled` và đường dẫn GraphiQL đã cấu hình. |

Khi bật Spring Security, hãy bảo vệ `/graphql` theo cơ chế xác thực và phân quyền của ứng dụng. Với ứng dụng dùng session và CSRF protection, request POST từ trình duyệt cần gửi CSRF token phù hợp. CORS cũng cần được cấu hình theo các origin thực sự được phép truy cập. Không nên tắt các cơ chế bảo vệ chỉ để làm cho một request thử nghiệm chạy qua.

## 9. Checklist khi đưa endpoint vào ứng dụng

1. Có `spring-boot-starter-graphql` và web starter phù hợp.
2. Schema được đặt trong vùng tài nguyên mà Spring Boot tìm kiếm.
3. Controller và resolver được component scanning phát hiện.
4. Client gọi đúng đường dẫn GraphQL, mặc định là `/graphql`.
5. Request gửi đúng GraphQL document, variables và HTTP headers.
6. Client xử lý cả `data` lẫn `errors` trong response.
7. Endpoint được bảo vệ bằng xác thực, phân quyền và CORS phù hợp với môi trường triển khai.

Khi các điểm trên đã đúng, ứng dụng Spring Boot có thể nhận GraphQL operation qua HTTP. Những phần như schema design, `@BatchMapping`, DataLoader và xử lý lỗi ở resolver tiếp tục quyết định chất lượng thực thi của API, còn HTTP endpoint đảm nhiệm việc đưa request từ client vào Spring for GraphQL.
