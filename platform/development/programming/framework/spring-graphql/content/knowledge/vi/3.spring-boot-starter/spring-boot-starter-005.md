# `spring.graphql.schema.locations` là gì?

`spring.graphql.schema.locations` là thuộc tính cấu hình của Spring Boot dùng để chỉ định những thư mục chứa tệp định nghĩa GraphQL Schema viết bằng SDL (Schema Definition Language). Khi ứng dụng khởi động, Spring Boot dựa vào các vị trí này để tìm và nạp các tệp schema, sau đó tạo nguồn GraphQL Schema cho Spring for GraphQL sử dụng.

Thuộc tính này đặc biệt hữu ích khi một schema được chia thành nhiều tệp, chẳng hạn tách phần khai báo `Query`, `Mutation`, các kiểu dữ liệu và những phần mở rộng theo từng tính năng. Thay vì phải ghép schema thủ công, ta tổ chức các tệp trong những thư mục tài nguyên và cấu hình nơi Spring Boot cần tìm chúng.

## 1. Vai trò trong ứng dụng Spring for GraphQL

Một API GraphQL cần có schema để mô tả những kiểu dữ liệu và thao tác mà client được phép gọi. Ví dụ, SDL có thể khai báo một trường truy vấn như sau:

```graphql
type Query {
    greeting: String!
}
```

Schema mô tả hợp đồng của API. Nó cho biết `Query` có trường `greeting`, trường đó trả về chuỗi và kết quả không được là `null`. Schema không tự thực thi nghiệp vụ. Phần xử lý trường được kết nối với các resolver trong ứng dụng Spring, ví dụ một phương thức được đánh dấu `@QueryMapping`.

Trong cấu hình Spring Boot tiêu chuẩn, quá trình này có thể hình dung như sau:

1. Spring Boot đọc `spring.graphql.schema.locations` và các thuộc tính liên quan đến phần mở rộng tệp.
2. Cơ chế nạp tài nguyên tìm những tệp SDL phù hợp trong các vị trí đã cấu hình.
3. Spring for GraphQL xây dựng GraphQL Schema từ nội dung các tệp tìm được.
4. Các controller và phương thức mapping của ứng dụng cung cấp cách thực thi những trường đã khai báo.

Vì vậy, `spring.graphql.schema.locations` quyết định **schema được tìm ở đâu**. Nó không quyết định URL của GraphQL endpoint, cũng không khai báo các resolver Java.

## 2. Vị trí mặc định

Với cấu hình Spring Boot mặc định, vị trí schema là:

```yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
```

Các tệp schema thường được đặt trong thư mục tài nguyên của dự án:

```text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            ├── common/
            │   └── scalar.graphqls
            └── product/
                └── product.graphqls
```

Sau khi build, nội dung trong `src/main/resources` được đưa vào classpath của ứng dụng. Tiền tố `classpath:` yêu cầu Spring tìm tài nguyên trên classpath. Phần `graphql/**/` cho phép tìm trong thư mục `graphql` và các thư mục con của nó.

Theo cấu hình mặc định của Spring Boot, các phần mở rộng schema được nhận diện là `.graphqls` và `.gqls`. Vì thế, những tên như `schema.graphqls`, `product.gqls` là phù hợp. Nếu dự án dùng phần mở rộng khác, cần cấu hình thêm `spring.graphql.schema.file-extensions` tương ứng.

Thông thường, không cần khai báo lại `spring.graphql.schema.locations` nếu toàn bộ schema đã nằm trong `src/main/resources/graphql/` hoặc các thư mục con của nó và dự án đang dùng cấu hình auto-configuration mặc định.

## 3. Cấu hình một vị trí schema

Khi muốn đặt schema trong một thư mục khác, khai báo vị trí đó trong `application.yml`:

```yaml
spring:
  graphql:
    schema:
      locations: classpath:api-schema/**/
```

Ví dụ cấu trúc tài nguyên tương ứng:

```text
src/main/resources/
└── api-schema/
    ├── root.graphqls
    └── customer/
        └── customer.graphqls
```

Nếu chỉ đặt `classpath:api-schema/`, việc tìm kiếm được giới hạn theo pattern thư mục đã khai báo. Dùng `**/` khi muốn bao gồm các thư mục con ở nhiều cấp. Hãy bảo đảm giá trị cấu hình trỏ đến thư mục tài nguyên thực sự có trong classpath sau khi build.

Có thể dùng `application.properties` thay cho YAML:

```properties
spring.graphql.schema.locations=classpath:api-schema/**/
```

Hai cách viết trên có cùng mục đích; chọn một định dạng cấu hình phù hợp với quy ước của dự án.

## 4. Cấu hình nhiều vị trí

Khi schema được chia theo nhiều nhóm hoặc được cung cấp từ nhiều thư mục tài nguyên, có thể khai báo danh sách vị trí:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/shared/**/
        - classpath:graphql/catalog/**/
        - classpath:graphql/order/**/
```

Mỗi phần tử là một vị trí để tìm các tệp schema. Ví dụ trên giúp nhóm schema dùng chung, schema sản phẩm và schema đơn hàng theo từng thư mục riêng. Nếu dùng `application.properties`, danh sách có thể được biểu diễn bằng các giá trị phân tách bởi dấu phẩy:

```properties
spring.graphql.schema.locations=classpath:graphql/shared/**/,classpath:graphql/catalog/**/,classpath:graphql/order/**/
```

Khi ghi đè thuộc tính mặc định bằng danh sách riêng, hãy liệt kê đầy đủ các vị trí mà ứng dụng cần nạp. Không nên giả định rằng vị trí mặc định `classpath:graphql/**/` vẫn tự động được giữ lại sau khi cấu hình một danh sách mới.

Spring cũng hỗ trợ tham chiếu tài nguyên trên hệ thống tệp. Ví dụ, một môi trường triển khai có thể cung cấp schema tại một thư mục bên ngoài ứng dụng:

```yaml
spring:
  graphql:
    schema:
      locations: file:/opt/my-service/graphql/**/
```

Đường dẫn `file:` cần trỏ đến vị trí tồn tại và tiến trình chạy ứng dụng phải có quyền đọc. Với cấu hình phụ thuộc môi trường, nên đặt giá trị trong file cấu hình theo profile hoặc biến môi trường của môi trường triển khai. Đường dẫn tuyệt đối thường dễ kiểm soát hơn đường dẫn tương đối vì thư mục làm việc của tiến trình có thể thay đổi.

## 5. Kết hợp nhiều tệp SDL thành một schema

Một ứng dụng có thể tách schema thành nhiều tệp để dễ quản lý. Ví dụ:

`src/main/resources/graphql/root.graphqls`:

```graphql
type Query {
    greeting: String!
    product(id: ID!): Product
}
```

`src/main/resources/graphql/product/product.graphqls`:

```graphql
type Product {
    id: ID!
    name: String!
    price: Float!
}
```

Các tệp đều nằm trong vùng tài nguyên được cấu hình nên Spring Boot có thể nạp chúng để xây dựng schema. Những kiểu được khai báo trong một tệp có thể được tham chiếu từ tệp khác, miễn là toàn bộ schema sau khi kết hợp hợp lệ.

Nếu cần bổ sung trường cho một kiểu đã được khai báo, hãy dùng cú pháp mở rộng của GraphQL SDL. Chẳng hạn, nếu `Query` đã được khai báo trong `root.graphqls`, một tệp khác có thể viết:

```graphql
extend type Query {
    featuredProducts: [Product!]!
}
```

Không khai báo lặp lại `type Query` như hai định nghĩa kiểu độc lập. Việc mở rộng bằng `extend type` giúp schema được chia tệp rõ ràng và tránh xung đột định nghĩa.

Sau khi schema được nạp, resolver trong Spring có thể xử lý trường đã khai báo:

```java
@Controller
class GreetingController {

    @QueryMapping
    String greeting() {
        return "Hello from Spring GraphQL";
    }
}
```

Tên phương thức `greeting` được ánh xạ đến trường `Query.greeting`. Ví dụ này cho thấy hai phần có trách nhiệm khác nhau: `spring.graphql.schema.locations` giúp tìm SDL, còn `@QueryMapping` kết nối trường truy vấn với mã Java thực thi nghiệp vụ.

## 6. Phân biệt với các thuộc tính GraphQL khác

Một số thuộc tính có tên gần nhau nhưng giải quyết những vấn đề khác nhau:

| Thuộc tính | Mục đích |
|---|---|
| `spring.graphql.schema.locations` | Chỉ định nơi tìm các tệp GraphQL SDL. |
| `spring.graphql.schema.file-extensions` | Chỉ định phần mở rộng của tệp schema cần tìm; mặc định thường là `.graphqls` và `.gqls`. |
| `spring.graphql.path` | Chỉ định đường dẫn HTTP mà GraphQL endpoint được phục vụ. |
| `spring.graphql.graphiql.enabled` | Bật hoặc tắt giao diện GraphiQL khi ứng dụng có cấu hình hỗ trợ. |

Ví dụ, thay đổi `spring.graphql.path` không làm thay đổi nơi Spring Boot tìm schema. Tương tự, đặt `spring.graphql.schema.locations` không tự tạo endpoint mới và cũng không bật GraphiQL.

## 7. Kiểm tra khi schema không được nạp

Nếu ứng dụng không khởi động được hoặc một kiểu GraphQL không xuất hiện trong schema, hãy kiểm tra lần lượt các điểm sau:

1. **Đúng vị trí tài nguyên:** kiểm tra tệp nằm dưới `src/main/resources` hoặc một thư mục tài nguyên thực sự được đưa vào classpath. Với `file:`, kiểm tra đường dẫn trên máy chạy ứng dụng.
2. **Đúng pattern thư mục:** kiểm tra tiền tố `classpath:` hoặc `file:` và dấu `/` ở cuối. Dùng `**/` nếu tệp nằm trong thư mục con nhiều cấp.
3. **Đúng phần mở rộng:** kiểm tra tệp có phần mở rộng nằm trong `spring.graphql.schema.file-extensions`. Nếu dùng phần mở rộng tùy chỉnh, khai báo nó trong cấu hình.
4. **Đúng profile:** kiểm tra `application.yml`, `application-{profile}.yml` và biến môi trường có ghi đè vị trí schema hay không.
5. **Schema hợp lệ:** kiểm tra lỗi cú pháp SDL, kiểu chưa được khai báo, trường tham chiếu sai kiểu và các định nghĩa bị trùng. Nhiều tệp được nạp vẫn phải tạo thành một schema GraphQL hợp lệ.
6. **Cấu hình nguồn schema:** nếu ứng dụng tự khai báo `GraphQlSource` hoặc tự xây dựng schema, kiểm tra cấu hình tùy chỉnh đó có thay thế cơ chế auto-configuration đang dùng thuộc tính này hay không.

Một cách kiểm tra đơn giản là tạo một trường truy vấn nhỏ trong tệp SDL thuộc vị trí đã cấu hình, viết resolver tương ứng bằng `@QueryMapping`, khởi động ứng dụng và gửi truy vấn đến GraphQL endpoint. Nếu trường được nhận diện và resolver được gọi, schema đã được nạp và ánh xạ đúng cho trường hợp thử nghiệm đó.

Với schema đặt bên ngoài classpath, cần quản lý quyền đọc và vòng đời triển khai của các tệp. Schema là hợp đồng API của server; nên kiểm soát thay đổi schema cùng quy trình review và phát hành ứng dụng để tránh môi trường chạy những định nghĩa không tương thích với resolver hiện có.

## 8. Khi nào nên cấu hình thuộc tính này?

Giữ cấu hình mặc định khi dự án tuân theo quy ước đặt schema trong `src/main/resources/graphql/`. Khai báo `spring.graphql.schema.locations` khi cần chuyển schema sang thư mục khác, chia schema theo nhiều thư mục, hoặc nạp schema từ một vị trí bên ngoài classpath.

Khi tổ chức nhiều tệp, hãy chọn cấu trúc thư mục dễ hiểu theo miền nghiệp vụ, bảo đảm mọi vị trí cần thiết đều được khai báo và giữ cho các định nghĩa SDL hợp lệ khi kết hợp. Cách tổ chức đó giúp Spring Boot tìm được schema nhất quán ở các môi trường phát triển, kiểm thử và triển khai.
