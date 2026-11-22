# Starter cho Spring MVC

## 1. Spring MVC starter là gì?

Trong Spring Boot, dependency thường được dùng để xây dựng ứng dụng Spring MVC là `spring-boot-starter-web`. Đây là một *starter*: một gói dependency được Spring Boot chọn sẵn để đưa những thư viện thường cần cho một nhóm chức năng vào dự án. Khi thêm starter, Maven hoặc Gradle giải quyết các dependency liên quan theo phiên bản được Spring Boot quản lý.

`spring-boot-starter-web` cung cấp nền tảng web theo mô hình Servlet và Spring MVC. Trong cấu hình thông dụng, starter này đưa vào Spring Web MVC, các thành phần web cần thiết, hỗ trợ chuyển đổi JSON và một máy chủ Servlet nhúng như Tomcat. Nhờ đó, ứng dụng có thể khởi động như một tiến trình Java độc lập mà không cần tự đóng gói và triển khai lên một máy chủ ứng dụng bên ngoài.

Spring MVC xử lý các HTTP request theo mô hình request-response. Controller nhận request, gọi tầng nghiệp vụ và trả response. Các annotation như `@Controller`, `@RestController`, `@GetMapping` và `@PostMapping` giúp ánh xạ URL và HTTP method đến phương thức Java.

Trong module Spring for GraphQL, `spring-boot-starter-web` có vai trò cung cấp nền tảng HTTP theo Servlet để ứng dụng tiếp nhận GraphQL request. Starter này không định nghĩa schema GraphQL hay tự viết resolver. Những chức năng đó thuộc Spring for GraphQL và GraphQL Java.

## 2. Phân biệt các starter trong ứng dụng Spring GraphQL

Một ứng dụng GraphQL chạy trên Spring MVC thường cần hai nhóm dependency có trách nhiệm khác nhau:

| Dependency | Trách nhiệm chính |
| --- | --- |
| `spring-boot-starter-graphql` | Tích hợp Spring for GraphQL, GraphQL Java, schema và cơ chế thực thi operation |
| `spring-boot-starter-web` | Cung cấp Spring MVC và Servlet HTTP transport để client gửi GraphQL request qua HTTP |

Có thể hình dung sự phân chia như sau:

```mermaid
flowchart TD
    A[GraphQL client] -->|HTTP request| B[Spring MVC / Servlet stack]
    B --> C[Spring for GraphQL]
    C --> D[GraphQL schema và execution engine]
    D --> E[@QueryMapping / @MutationMapping / @SchemaMapping]
    E --> F[Service và Repository]
    F --> G[Database hoặc hệ thống khác]
    G --> F
    F --> E
    E --> D
    D --> C
    C --> B
    B -->|HTTP JSON response| A
```

`spring-boot-starter-web` đảm nhiệm lớp web của ứng dụng. `spring-boot-starter-graphql` đảm nhiệm lớp GraphQL. Khi kết hợp chúng, Spring Boot có thể tự cấu hình endpoint GraphQL trên nền tảng Servlet theo các dependency có mặt trong ứng dụng.

Nếu chỉ thêm `spring-boot-starter-web`, dự án có Spring MVC nhưng chưa có schema và engine GraphQL. Nếu chỉ thêm `spring-boot-starter-graphql`, dự án có phần tích hợp GraphQL nhưng vẫn cần một transport phù hợp để nhận request từ client qua HTTP. Với ứng dụng dùng Spring MVC, transport đó được cung cấp bởi `spring-boot-starter-web`.

## 3. Thêm dependency vào dự án

### Maven

Thêm hai dependency vào phần `dependencies` của `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

### Gradle Kotlin DSL

Nếu dự án dùng Gradle với Kotlin DSL, khai báo trong `build.gradle.kts`:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

### Gradle Groovy DSL

Với `build.gradle`, cú pháp tương ứng là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Thông thường, không cần ghi version riêng cho từng starter. Hãy dùng Spring Boot parent hoặc cơ chế dependency management/plugin của Spring Boot để các thư viện thuộc cùng hệ sinh thái được quản lý phiên bản đồng bộ. Tự ghim các phiên bản Spring Framework, Spring GraphQL hoặc GraphQL Java không tương thích có thể gây lỗi lúc biên dịch hoặc khởi động.

## 4. Spring MVC đảm nhiệm phần HTTP như thế nào?

Khi dùng `spring-boot-starter-web`, ứng dụng chạy trên Servlet stack. Trong cấu hình mặc định phổ biến, Spring Boot khởi động máy chủ nhúng và đăng ký hạ tầng Spring MVC. `DispatcherServlet` là thành phần trung tâm điều phối request đến handler phù hợp.

Một ứng dụng có thể cung cấp nhiều loại HTTP endpoint cùng lúc:

- REST endpoint được ánh xạ bằng `@RestController`, `@GetMapping`, `@PostMapping` và các annotation MVC khác.
- GraphQL endpoint do phần tích hợp Spring for GraphQL đăng ký trên web stack.
- Tài nguyên tĩnh như file CSS, JavaScript hoặc hình ảnh nếu ứng dụng có cấu hình phục vụ chúng.

Với GraphQL, client thường gửi một HTTP POST đến endpoint `/graphql`. Phần body chứa operation, variables và có thể có operation name. Spring MVC tiếp nhận HTTP request; phần tích hợp Spring for GraphQL chuyển nội dung request vào GraphQL engine để kiểm tra schema, chọn resolver và thực thi các field được yêu cầu. Kết quả được trả về dưới dạng JSON.

Luồng khái quát:

1. Client gửi HTTP request đến endpoint GraphQL.
2. Servlet container nhận request và chuyển vào web stack của ứng dụng.
3. Spring for GraphQL đọc GraphQL request và tạo execution input.
4. GraphQL engine kiểm tra operation với schema rồi thực thi các resolver liên quan.
5. Resolver gọi service hoặc repository để lấy và thay đổi dữ liệu theo nghiệp vụ.
6. Kết quả và lỗi GraphQL được đóng gói thành response JSON gửi lại client.

Điểm quan trọng là GraphQL operation không được ánh xạ thành một phương thức `@PostMapping` do ứng dụng tự viết cho từng query. Spring for GraphQL cung cấp endpoint HTTP chung; các phương thức `@QueryMapping`, `@MutationMapping` và `@SchemaMapping` đảm nhiệm việc phân giải field bên trong GraphQL operation.

## 5. Ví dụ ứng dụng GraphQL chạy trên Spring MVC

Giả sử ứng dụng thư viện cần cung cấp query tìm sách theo mã. Cấu trúc tối thiểu có thể như sau:

```text
src/main/
├── java/com/example/library/
│   ├── LibraryApplication.java
│   └── BookGraphQlController.java
└── resources/
    └── graphql/
        └── schema.graphqls
```

### Khai báo schema SDL

Tạo file `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Schema định nghĩa một root field `bookById`. Tham số `id` bắt buộc, còn kết quả `Book` có thể là `null` nếu không tìm thấy sách. Các field `id` và `title` của một đối tượng Book phải có giá trị.

Trong cấu hình mặc định của Spring Boot, schema có thể được đặt trong thư mục `src/main/resources/graphql/` với phần mở rộng `.graphqls` hoặc `.gqls`. Nếu đổi vị trí, cần cấu hình lại schema location tương ứng.

### Viết GraphQL controller

Tạo controller dùng annotation của Spring for GraphQL:

```java
package com.example.library;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`@Controller` giúp Spring phát hiện component chứa các handler GraphQL. `@QueryMapping` liên kết phương thức với field cùng tên trong root type `Query`; `@Argument` lấy giá trị đối số `id` từ GraphQL request. `BookService` là tầng nghiệp vụ do ứng dụng cung cấp.

Ví dụ mô hình trả về:

```java
public record Book(String id, String title) {
}
```

Controller GraphQL không cần khai báo `@PostMapping("/graphql")`. Endpoint HTTP được phần tích hợp Spring GraphQL cấu hình. Phương thức `bookById` chỉ xử lý field tương ứng sau khi operation đã được GraphQL engine phân tích.

### Cấu hình endpoint

Endpoint HTTP mặc định của Spring for GraphQL trong Spring Boot thường là `/graphql`. Có thể khai báo rõ đường dẫn trong `application.yml`:

```yaml
spring:
  graphql:
    path: /graphql

server:
  port: 8080
```

Nếu đổi `path`, client phải gửi request đến đường dẫn mới. Thuộc tính `server.port` điều chỉnh cổng HTTP của máy chủ nhúng.

### Gửi request từ client

GraphQL operation:

```graphql
query BookById($id: ID!) {
    bookById(id: $id) {
        id
        title
    }
}
```

Request JSON gửi đến `http://localhost:8080/graphql`:

```json
{
  "query": "query BookById($id: ID!) { bookById(id: $id) { id title } }",
  "operationName": "BookById",
  "variables": {
    "id": "42"
  }
}
```

Có thể kiểm tra nhanh bằng curl:

```bash
curl -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query BookById($id: ID!) { bookById(id: $id) { id title } }","variables":{"id":"42"}}'
```

Nếu tìm thấy sách, response có dạng:

```json
{
  "data": {
    "bookById": {
      "id": "42",
      "title": "GraphQL với Spring"
    }
  }
}
```

Ví dụ này cho thấy Spring MVC cung cấp HTTP transport, còn GraphQL schema và resolver quyết định cấu trúc operation cũng như dữ liệu trả về.

## 6. Kết hợp REST và GraphQL trong cùng ứng dụng MVC

Spring MVC và Spring for GraphQL có thể cùng tồn tại trong một ứng dụng. Điều này hữu ích khi hệ thống đã có REST API nhưng một số màn hình hoặc client cần truy vấn kết hợp dữ liệu linh hoạt hơn.

Ví dụ REST controller:

```java
@RestController
@RequestMapping("/api/books")
public class BookRestController {

    private final BookService bookService;

    public BookRestController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/{id}")
    public Book findById(@PathVariable String id) {
        return bookService.findById(id).orElseThrow();
    }
}
```

REST endpoint có thể là `GET /api/books/42`, trong khi GraphQL endpoint vẫn là `POST /graphql`. Cả hai controller có thể gọi cùng `BookService`, nhờ vậy quy tắc nghiệp vụ không phải nhân đôi theo từng kiểu API.

Không nên đặt toàn bộ nghiệp vụ trong controller. Controller REST và GraphQL chỉ nên chuyển dữ liệu đầu vào, gọi service, rồi định hình kết quả phù hợp với giao thức tương ứng.

## 7. Khi nào nên chọn Spring MVC cho GraphQL?

Spring for GraphQL hỗ trợ cả mô hình Servlet dựa trên Spring MVC và mô hình reactive dựa trên Spring WebFlux. GraphQL schema và cách viết các mapping annotation về cơ bản không phụ thuộc vào việc chọn web stack nào.

Chọn `spring-boot-starter-web` khi:

- Ứng dụng đang dùng Spring MVC hoặc cần tương thích với hệ sinh thái Servlet.
- Tầng nghiệp vụ chủ yếu dùng JDBC, JPA hoặc các thư viện đồng bộ/blocking.
- Hệ thống cần kết hợp REST controller và GraphQL endpoint trên cùng web stack.
- Đội ngũ đã có kinh nghiệm vận hành Spring MVC, Servlet filter và các thành phần liên quan.

Chọn `spring-boot-starter-webflux` khi ứng dụng được thiết kế theo mô hình reactive và cần xử lý I/O không chặn xuyên suốt các tầng. Chỉ đổi sang WebFlux không tự động làm truy vấn database blocking trở thành non-blocking; cần xem xét cả driver, client HTTP và cách tổ chức nghiệp vụ.

Thông thường, hãy chọn một web stack làm nền tảng chính. Không thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` chỉ để thử nghiệm nếu chưa hiểu cách Spring Boot lựa chọn và cấu hình application type, vì điều đó có thể gây nhầm lẫn khi khởi động và vận hành.

## 8. Các lưu ý về cấu hình, bảo mật và lỗi

### Đường dẫn GraphQL và đường dẫn MVC

`spring.graphql.path` điều chỉnh endpoint GraphQL. Các route MVC như `/api/books` vẫn được khai báo riêng bằng `@RequestMapping` hoặc các annotation tương ứng. Cần tránh cấu hình route trùng nhau và bảo đảm client sử dụng đúng endpoint.

### Bảo mật HTTP và bảo mật field

Spring Security có thể bảo vệ request đến `/graphql` thông qua security filter chain của ứng dụng Servlet. Tuy nhiên, việc cho phép request đến endpoint không có nghĩa là người dùng được phép đọc mọi field hoặc thay đổi mọi đối tượng.

Các quy tắc nghiệp vụ cần được kiểm tra trong resolver hoặc service, dựa trên người dùng hiện tại, quyền, chủ sở hữu dữ liệu và tenant. Vì nhiều operation dùng chung một URL, chỉ dựa vào quy tắc phân quyền theo URL thường không đủ để kiểm soát truy cập đến từng field.

### Xử lý lỗi MVC và lỗi GraphQL

REST controller thường dùng các cơ chế xử lý exception của Spring MVC, chẳng hạn `@ExceptionHandler` hoặc `@ControllerAdvice`. Với lỗi phát sinh trong quá trình phân giải field GraphQL, Spring for GraphQL cung cấp cơ chế như `DataFetcherExceptionResolver` để ánh xạ exception thành phần tử trong `errors` của GraphQL response.

Hai loại API có thể chia sẻ service và quy tắc nghiệp vụ, nhưng cần định hình response lỗi theo đúng giao thức. Không đưa stack trace, câu SQL, token hoặc thông tin nội bộ vào response gửi client.

### Không nhầm endpoint với resolver

Nếu `POST /graphql` trả về 404, hãy kiểm tra dependency web stack, cấu hình endpoint và trạng thái khởi động ứng dụng. Nếu endpoint đã nhận request nhưng response báo lỗi validation hoặc không tìm thấy field, hãy kiểm tra schema, tên operation và mapping resolver. Đây là hai lớp lỗi khác nhau.

## 9. Một số lỗi thường gặp khi thêm Spring MVC starter

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `/graphql` trả về 404 | Chưa có HTTP transport phù hợp, endpoint bị đổi path hoặc ứng dụng chưa đăng ký GraphQL handler | Kiểm tra `spring-boot-starter-web`, `spring-boot-starter-graphql`, log khởi động và `spring.graphql.path` |
| Ứng dụng có REST nhưng chưa có GraphQL | Chỉ thêm `spring-boot-starter-web` | Bổ sung `spring-boot-starter-graphql` và schema SDL |
| Schema không được nhận diện | File schema sai thư mục, sai phần mở rộng hoặc cấu hình location không đúng | Kiểm tra `src/main/resources/graphql/` và tên file `.graphqls`/`.gqls` |
| Field không được phân giải | Tên field và mapping không khớp, hoặc controller chưa được Spring phát hiện | Đối chiếu root field trong SDL với `@QueryMapping`/`@MutationMapping` và package scan |
| Lỗi tương thích thư viện | Các dependency Spring Boot/Spring Framework/Spring GraphQL bị ghim phiên bản không đồng bộ | Dùng dependency management của Spring Boot và kiểm tra dependency tree |
| REST và GraphQL trả lỗi khác nhau | Hai giao thức có định dạng lỗi và cơ chế ánh xạ exception riêng | Kiểm tra handler MVC và `DataFetcherExceptionResolver` tương ứng |

## 10. Checklist khi thiết lập ứng dụng

- [ ] Dự án dùng dependency management của một phiên bản Spring Boot thống nhất.
- [ ] Đã thêm `spring-boot-starter-graphql` để cung cấp schema và GraphQL execution.
- [ ] Đã thêm `spring-boot-starter-web` khi chọn Spring MVC làm HTTP stack.
- [ ] Schema SDL nằm trong vị trí được Spring Boot quét hoặc đã cấu hình schema location.
- [ ] GraphQL controller được Spring phát hiện và mapping khớp với field trong schema.
- [ ] Client gửi request đến đúng GraphQL path với payload hợp lệ.
- [ ] Security filter chain bảo vệ HTTP endpoint và service/resolver kiểm tra quyền theo dữ liệu.
- [ ] REST và GraphQL có chiến lược xử lý lỗi phù hợp với từng giao thức.

## Kết luận

`spring-boot-starter-web` là lựa chọn tiêu chuẩn để xây dựng ứng dụng Spring MVC trên nền tảng Servlet. Trong một ứng dụng Spring for GraphQL, starter này cung cấp lớp HTTP để client gửi query và mutation đến server; `spring-boot-starter-graphql` cung cấp schema, engine thực thi và cơ chế ánh xạ field đến resolver.

Khi hiểu rõ trách nhiệm của từng starter, việc cấu hình trở nên dễ kiểm soát: chọn web stack phù hợp với mô hình I/O của ứng dụng, để Spring Boot quản lý phiên bản dependency, đặt schema đúng vị trí và triển khai resolver bằng các annotation của Spring for GraphQL. Một ứng dụng có thể đồng thời cung cấp REST và GraphQL, miễn là controller tập trung vào giao thức còn nghiệp vụ được tổ chức ở tầng service.
