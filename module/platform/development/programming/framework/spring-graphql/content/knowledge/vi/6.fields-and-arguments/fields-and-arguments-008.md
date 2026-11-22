# Alias

Trong GraphQL, alias cho phép client đặt tên response key riêng cho một field trong query. Cú pháp này đặc biệt hữu ích khi cần gọi cùng một field nhiều lần với các argument khác nhau, ví dụ lấy hai sản phẩm theo hai ID hoặc lấy địa chỉ giao hàng và địa chỉ thanh toán của cùng một khách hàng.

Alias chỉ thay đổi tên key trong response mà client nhận được. Nó không đổi tên field trong schema, không tạo field mới trên server và không yêu cầu viết thêm resolver. Với Spring for GraphQL, resolver vẫn được ánh xạ theo tên field thật trong SDL; alias thuộc về operation do client gửi.

## 1. Alias là gì?

Cú pháp của alias:

```graphql
responseKey: fieldName
```

Trong đó:

- `responseKey` là tên client muốn xuất hiện trong response.
- `fieldName` là field thực sự được khai báo trong schema.

Ví dụ schema có field `product`:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    price: Float!
}
```

Client có thể đặt alias `selectedProduct`:

```graphql
query {
    selectedProduct: product(id: "p-101") {
        id
        name
        price
    }
}
```

Response dùng alias làm key:

```json
{
  "data": {
    "selectedProduct": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "price": 125.5
    }
  }
}
```

Nếu bỏ alias, key mặc định sẽ là `product`. Tên alias không cần tồn tại trong schema; đó là tên cục bộ của response trong operation hiện tại.

## 2. Gọi cùng một field nhiều lần với argument khác nhau

Một use case phổ biến là so sánh hai sản phẩm. Schema chỉ cần một field `product(id: ID!)`, nhưng client muốn lấy hai bản ghi khác nhau trong cùng một operation.

```graphql
query CompareProducts {
    firstProduct: product(id: "p-101") {
        id
        name
        price
    }
    secondProduct: product(id: "p-205") {
        id
        name
        price
    }
}
```

Response có hai key riêng:

```json
{
  "data": {
    "firstProduct": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "price": 125.5
    },
    "secondProduct": {
      "id": "p-205",
      "name": "Wireless Mouse",
      "price": 49.9
    }
  }
}
```

Hai field đều gọi schema field `product`, nhưng có argument `id` khác nhau và response key khác nhau. Client nhận được hai kết quả có tên rõ nghĩa trong một GraphQL response.

Nếu không dùng alias và viết hai lần `product` với argument khác nhau, GraphQL validation sẽ phát hiện xung đột response key. Alias giúp phân biệt hai lần chọn field này.

## 3. Dùng alias với field lồng nhau

Alias không chỉ dùng cho root field. Có thể dùng ở bất kỳ cấp nào trong selection set.

Giả sử một khách hàng có nhiều loại địa chỉ:

```graphql
type Query {
    customer(id: ID!): Customer
}

type Customer {
    id: ID!
    name: String!
    address(type: AddressType!): Address
}

enum AddressType {
    SHIPPING
    BILLING
}

type Address {
    street: String!
    city: String!
    postalCode: String!
}
```

Client cần cả địa chỉ giao hàng và thanh toán:

```graphql
query CustomerAddresses($id: ID!) {
    customer(id: $id) {
        name
        shippingAddress: address(type: SHIPPING) {
            street
            city
            postalCode
        }
        billingAddress: address(type: BILLING) {
            street
            city
            postalCode
        }
    }
}
```

Response có cấu trúc dễ sử dụng:

```json
{
  "data": {
    "customer": {
      "name": "Lan Nguyen",
      "shippingAddress": {
        "street": "12 Nguyen Hue",
        "city": "Ho Chi Minh City",
        "postalCode": "700000"
      },
      "billingAddress": {
        "street": "88 Le Loi",
        "city": "Ho Chi Minh City",
        "postalCode": "700000"
      }
    }
  }
}
```

Ở đây, alias giúp phân biệt hai kết quả của cùng field `address` dựa trên argument `type`. Client có thể truy cập trực tiếp `shippingAddress` và `billingAddress` mà không phải tự ghép dữ liệu sau khi nhận response.

## 4. Kết hợp alias với variables

Alias có thể kết hợp với variables để query linh hoạt hơn. Ví dụ client so sánh hai sản phẩm mà ID đến từ trạng thái giao diện:

```graphql
query CompareProducts($leftId: ID!, $rightId: ID!) {
    left: product(id: $leftId) {
        id
        name
        price
    }
    right: product(id: $rightId) {
        id
        name
        price
    }
}
```

Variables:

```json
{
  "leftId": "p-101",
  "rightId": "p-205"
}
```

Alias và variable giải quyết hai việc khác nhau:

- Alias đặt tên cho kết quả trong response.
- Variable truyền giá trị vào argument mà không phải nội suy chuỗi vào query document.

Tên alias là một phần của GraphQL document, còn giá trị ID được truyền lúc thực thi. Client có thể dùng lại cùng một document cho nhiều cặp ID khác nhau.

## 5. Alias và quy tắc response key

GraphQL gọi tên được dùng làm key trong response là *response name*. Nếu field có alias, response name là alias; nếu không có alias, response name chính là tên field.

Ví dụ:

```graphql
query {
    featured: product(id: "p-101") {
        name
    }
}
```

Response name là `featured`, không phải `product`.

Các field có cùng response name phải tương thích để GraphQL có thể gộp selection. Nếu cùng response key nhưng trỏ tới field khác nhau hoặc dùng argument xung đột, operation có thể không vượt qua bước validation.

Ví dụ xung đột:

```graphql
query {
    product(id: "p-101") {
        id
    }
    product(id: "p-205") {
        id
    }
}
```

Hai lần chọn cùng response key `product` nhưng argument `id` khác nhau. Cách sửa là đặt alias riêng:

```graphql
query {
    first: product(id: "p-101") {
        id
    }
    second: product(id: "p-205") {
        id
    }
}
```

Ngược lại, nếu cùng một field với cùng argument được chọn lặp lại bằng cùng response name và các selection tương thích, GraphQL có thể gộp các selection đó theo quy tắc field collection. Không cần tạo alias chỉ để lặp lại cùng một dữ liệu.

## 6. Alias trong fragment

Alias có thể xuất hiện bên trong fragment giống như trong selection set thông thường. Điều này giúp tái sử dụng một cấu trúc query mà vẫn đặt tên response key theo ngữ cảnh.

```graphql
fragment ProductCard on Product {
    productName: name
    currentPrice: price
}

query {
    product(id: "p-101") {
        ...ProductCard
    }
}
```

Response:

```json
{
  "data": {
    "product": {
      "productName": "Mechanical Keyboard",
      "currentPrice": 125.5
    }
  }
}
```

Alias nằm trong fragment nên response key tương ứng vẫn được đổi tên khi fragment được trải vào selection set. Nếu nhiều fragment được dùng chung tại nhiều vị trí, hãy kiểm tra response shape mong đợi ở từng vị trí và tránh tạo các alias gây xung đột.

## 7. Alias ảnh hưởng đến lỗi GraphQL như thế nào?

Khi một field gặp lỗi trong lúc thực thi, GraphQL response có thể chứa `errors` với `path` chỉ vị trí field bị lỗi. Các phần tử của path sử dụng response name, tức alias nếu field đã được alias.

Ví dụ query:

```graphql
query {
    chosenProduct: product(id: "p-101") {
        displayPrice: price
    }
}
```

Nếu resolver của `price` phát sinh lỗi, path có thể có dạng:

```json
{
  "errors": [
    {
      "message": "Price is temporarily unavailable",
      "path": ["chosenProduct", "displayPrice"]
    }
  ],
  "data": {
    "chosenProduct": null
  }
}
```

Path dùng alias `chosenProduct` và `displayPrice`, vì đó là các response key mà client nhìn thấy. Khi xử lý lỗi hoặc ghi log ở phía client, cần dựa trên response path thay vì luôn giả định path chứa tên field trong schema.

## 8. Alias khi dùng Spring for GraphQL

Alias là tính năng của GraphQL query language và execution engine. Spring for GraphQL không cần một annotation riêng để khai báo alias. Controller vẫn ánh xạ theo tên field trong schema.

Ví dụ schema:

```graphql
type Query {
    product(id: ID!): Product
}
```

Controller:

```java
package com.example.graphql.product;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }
}
```

Client gửi:

```graphql
query {
    keyboard: product(id: "p-101") {
        id
        name
    }
    mouse: product(id: "p-205") {
        id
        name
    }
}
```

Cả hai selection đều gọi field schema `product`, vì vậy Spring ánh xạ chúng về method `@QueryMapping product`. Resolver được thực thi cho từng field occurrence với argument tương ứng. Không cần tạo method `keyboard()` hay `mouse()` và cũng không khai báo hai field mới trong SDL.

Alias không thay đổi `@Argument` name. Method vẫn nhận argument `id`, vì đó là tên argument trong schema field `product`. Nếu cần biết vị trí thực thi hoặc thông tin operation trong logic hạ tầng, có thể dùng các API execution context của GraphQL Java; nghiệp vụ thông thường không nên phụ thuộc vào alias do client tự đặt.

## 9. Alias với mutation

Alias cũng có thể dùng trong mutation operation. Ví dụ một operation cần đổi tên hai sản phẩm:

```graphql
mutation RenameProducts {
    keyboard: renameProduct(id: "p-101", name: "Keyboard Pro") {
        id
        name
    }
    mouse: renameProduct(id: "p-205", name: "Mouse Pro") {
        id
        name
    }
}
```

Response sẽ có hai key `keyboard` và `mouse`. Các field mutation cấp cao nhất trong cùng operation được thực thi tuần tự theo thứ tự xuất hiện trong document.

Alias không biến một operation thành transaction. Nếu mutation đầu tiên thành công và mutation thứ hai thất bại, GraphQL không tự rollback thay đổi đầu tiên. Với quy trình cần nguyên tử, nên cung cấp một command nghiệp vụ ở server và thực hiện transaction tại service/domain layer.

Không dùng alias để che giấu hoặc thay đổi ý nghĩa nghiệp vụ của mutation. Tên alias chỉ tổ chức response cho client; quyền truy cập, validation và audit vẫn phải dựa trên command và tài nguyên thực tế.

## 10. Giới hạn và thực hành tốt

Alias rất linh hoạt, nhưng mỗi lần chọn field vẫn có thể kích hoạt resolver và truy cập dữ liệu. Một query dùng hàng chục alias để gọi cùng field với nhiều argument có thể tạo tải lớn cho server.

Một số nguyên tắc nên áp dụng:

- Đặt alias ngắn gọn nhưng thể hiện đúng vai trò của kết quả, ví dụ `shippingAddress`, `billingAddress`, `primaryContact`.
- Dùng alias khi cần phân biệt các lần gọi cùng field hoặc cần response key phù hợp với ngữ cảnh.
- Dùng variables cho giá trị thay đổi giữa các lần thực thi; không tạo query document mới bằng cách nối chuỗi input.
- Giới hạn độ sâu, độ phức tạp và số lượng phần tử được trả về để kiểm soát chi phí query.
- Kiểm tra authorization cho từng tài nguyên và field được resolve, kể cả khi chúng xuất hiện dưới alias khác nhau.
- Không dùng alias như một cơ chế bảo mật hoặc để giấu field nhạy cảm.
- Theo dõi operation và resolver cost; tên alias do client đặt có thể thay đổi nên không phải định danh ổn định để phân nhóm metric.

Alias không làm thay đổi schema introspection và không tạo một API field mới. Client chỉ đổi tên response key trong operation hiện tại. Điều này giữ schema gọn trong khi cho phép mỗi client tổ chức dữ liệu theo nhu cầu.

## 11. Checklist khi sử dụng alias

- Alias có tên hợp lệ theo quy tắc GraphQL Name không?
- Response key có đủ rõ để client hiểu dữ liệu đại diện cho điều gì không?
- Các lần gọi cùng field với argument khác nhau đã có alias riêng chưa?
- Những field có cùng response name có tương thích để gộp không?
- Client có xử lý error path dựa trên alias không?
- Query có giới hạn số lần gọi và chi phí resolver hợp lý không?
- Với mutation, transaction và idempotency đã được thiết kế độc lập với alias chưa?

Alias là công cụ nhỏ nhưng quan trọng để tổ chức response GraphQL. Nó cho phép cùng một field xuất hiện nhiều lần với argument khác nhau, đặt tên rõ nghĩa cho dữ liệu lồng nhau và giúp client nhận response phù hợp với ngữ cảnh. Trong Spring for GraphQL, server vẫn xử lý field theo schema và resolver hiện có; alias chỉ tác động tới cách kết quả được đặt tên trong response.
