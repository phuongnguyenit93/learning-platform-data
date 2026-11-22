# Built-in @include

Trong GraphQL, directive `@include` cho phép client quyết định một field hoặc một phần selection set có được đưa vào kết quả hay không, dựa trên một điều kiện Boolean. Directive này hữu ích khi giao diện có các phần dữ liệu tùy chọn, ví dụ chỉ tải mô tả chi tiết khi người dùng mở rộng một sản phẩm hoặc chỉ lấy thông tin liên hệ khi màn hình cần hiển thị.

`@include` là directive tích hợp sẵn của GraphQL. GraphQL engine xử lý điều kiện trong quá trình thực thi operation; ứng dụng Spring for GraphQL không cần tạo annotation Java hay resolver riêng cho directive này. Resolver của field chỉ được thực thi khi field được chọn sau khi áp dụng các directive điều kiện.

## 1. Cú pháp của @include

Cú pháp cơ bản:

```graphql
fieldName @include(if: Boolean!)
```

Directive nhận đúng một argument tên `if`, có kiểu `Boolean!`:

- Nếu `if` là `true`, field hoặc selection được giữ lại để thực thi.
- Nếu `if` là `false`, field hoặc selection bị loại khỏi operation đang thực thi.
- Nếu giá trị không thể coercion thành Boolean hoặc là `null`, request không hợp lệ vì argument yêu cầu `Boolean!`.

Ví dụ đơn giản:

```graphql
query {
    product(id: "p-101") {
        id
        name
        description @include(if: true)
    }
}
```

Vì điều kiện là `true`, field `description` được đưa vào response. Nếu đổi thành `false`, field đó bị bỏ qua trong lần thực thi này.

Directive có thể gắn vào field, fragment spread hoặc inline fragment. Đây là executable directive, tức directive được dùng trong GraphQL operation. `@include` không phải directive dùng để cấu hình schema type hoặc khai báo metadata cho field trong SDL.

## 2. Dùng variable để điều khiển field

Trong ứng dụng thực tế, điều kiện thường phụ thuộc vào trạng thái giao diện hoặc lựa chọn của người dùng. Dùng variable giúp tái sử dụng cùng một query document với nhiều giá trị khác nhau.

```graphql
query ProductDetail($id: ID!, $showDescription: Boolean!) {
    product(id: $id) {
        id
        name
        description @include(if: $showDescription)
    }
}
```

Variables khi cần mô tả chi tiết:

```json
{
  "id": "p-101",
  "showDescription": true
}
```

Variables khi chỉ cần thông tin tóm tắt:

```json
{
  "id": "p-101",
  "showDescription": false
}
```

Với `true`, response có thể là:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "description": "A compact keyboard for everyday work."
    }
  }
}
```

Với `false`, response không chứa key `description`:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard"
    }
  }
}
```

Điểm cần nhớ là field bị loại khỏi selection set sẽ không được trả về như một field có giá trị `null`. Key của field không xuất hiện trong response, trừ khi một selection khác cùng response key vẫn yêu cầu field đó.

## 3. @include trên field lồng nhau

Directive có thể áp dụng ở bất kỳ field nào trong selection set. Điều này cho phép client bật hoặc tắt từng phần dữ liệu mà không cần tạo nhiều query gần giống nhau.

```graphql
query CustomerDetail(
    $id: ID!
    $includeContact: Boolean!
    $includeOrders: Boolean!
) {
    customer(id: $id) {
        id
        name
        email @include(if: $includeContact)
        phone @include(if: $includeContact)
        orders @include(if: $includeOrders) {
            id
            status
            total
        }
    }
}
```

Ví dụ này cho phép màn hình hồ sơ chỉ tải tên và mã khách hàng. Khi người dùng mở phần liên hệ, client gửi `includeContact: true`; khi mở lịch sử đơn hàng, client gửi `includeOrders: true`.

Điều kiện áp dụng độc lập cho từng field. Nếu `includeOrders` là `false`, field `orders` bị bỏ qua và resolver của field đó không cần chạy. Các field `id` và `name` vẫn được thực thi như bình thường.

## 4. Dùng @include trên fragment spread

Khi một nhóm field thường được bật hoặc tắt cùng nhau, đặt directive trên fragment spread giúp query gọn hơn.

```graphql
fragment CustomerContact on Customer {
    email
    phone
    address {
        street
        city
    }
}

query CustomerDetail($id: ID!, $showContact: Boolean!) {
    customer(id: $id) {
        id
        name
        ...CustomerContact @include(if: $showContact)
    }
}
```

Nếu `showContact` là `false`, toàn bộ selection trong `CustomerContact` không được thực thi tại vị trí fragment spread đó. Khi là `true`, các field của fragment được mở rộng vào selection set và thực thi theo quy tắc thông thường.

Directive trên fragment spread đặc biệt hữu ích khi một fragment chứa nhiều field lồng nhau hoặc được chia sẻ giữa nhiều query. Client có thể tái sử dụng fragment mà không cần sao chép selection set.

## 5. Dùng @include trên inline fragment

Inline fragment thường được dùng với interface hoặc union để chọn field tùy theo kiểu object cụ thể. Có thể kết hợp với `@include` để chỉ lấy phần dữ liệu đa hình khi cần.

```graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    author: String!
}

type Author implements SearchResult {
    id: ID!
    title: String!
    biography: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

Client có thể yêu cầu field đặc thù theo điều kiện:

```graphql
query Search($keyword: String!, $showExtra: Boolean!) {
    search(keyword: $keyword) {
        id
        title
        ... on Book @include(if: $showExtra) {
            author
        }
        ... on Author @include(if: $showExtra) {
            biography
        }
    }
}
```

Khi `showExtra` là `false`, cả hai inline fragment bị loại khỏi selection. Khi là `true`, fragment phù hợp với concrete type của từng kết quả được áp dụng. `@include` không làm thay đổi kiểu thực tế của object và cũng không biến một `Book` thành `Author`.

## 6. Kết hợp @include với @skip

GraphQL có hai directive điều kiện tích hợp sẵn thường được dùng cùng nhau:

- `@include(if: Boolean!)`: chỉ đưa selection vào khi điều kiện là `true`.
- `@skip(if: Boolean!)`: loại selection khi điều kiện là `true`.

Hai directive biểu đạt hai cách nhìn đối lập của cùng một nhu cầu. Ví dụ:

```graphql
query ProductDetail($showDescription: Boolean!) {
    product(id: "p-101") {
        id
        name
        description @include(if: $showDescription)
        internalCode @skip(if: $showDescription)
    }
}
```

Trong ví dụ trên, mô tả sản phẩm được lấy khi `showDescription` là `true`, còn `internalCode` được lấy khi điều kiện đó là `false`.

Có thể đặt cả `@include` và `@skip` trên cùng một selection. Selection chỉ được thực thi khi tất cả điều kiện đều cho phép: `@include` phải nhận `true` và `@skip` phải nhận `false`. Nếu một trong hai điều kiện loại selection, field sẽ bị bỏ qua.

Không nên lạm dụng việc kết hợp nhiều điều kiện trên cùng field nếu một biến Boolean có tên rõ nghĩa đã đủ diễn đạt ý định. Query dễ đọc giúp client và người vận hành hiểu chính xác response mong đợi.

## 7. Phân biệt field bị bỏ qua, null và danh sách rỗng

Ba trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Ví dụ response |
| --- | --- | --- |
| Field bị `@include` loại bỏ | Client không yêu cầu field trong operation này | Không có key `description` |
| Field được thực thi và trả null | Resolver trả null hoặc dữ liệu không có giá trị, nếu schema cho phép | `"description": null` |
| Field được thực thi và trả danh sách rỗng | Có yêu cầu field và kết quả là không có phần tử | `"orders": []` |

Client không nên diễn giải field bị thiếu như thể server đã xác nhận giá trị của field là null hoặc danh sách rỗng. Field có thể bị bỏ qua vì điều kiện `@include` là false, hoặc không được chọn trong operation ngay từ đầu.

Nếu field bị bỏ qua do directive, server không có cơ hội resolver field đó trong lần thực thi hiện tại. Điều này khác với resolver chạy và chủ động trả null.

## 8. @include ảnh hưởng tới việc thực thi resolver

Directive điều kiện được GraphQL engine xử lý trong giai đoạn thu thập field để thực thi. Selection bị loại bởi `@include(if: false)` không được đưa vào tập field cần resolve tại vị trí đó.

Điều này có thể giảm công việc không cần thiết, đặc biệt khi field cần truy vấn database, gọi service bên ngoài hoặc tính toán tốn kém. Tuy nhiên, không nên mặc định rằng mọi chi phí query đều giảm tương ứng với số field bị ẩn:

- Query parser và validation vẫn phải xử lý document.
- Công cụ phân tích độ sâu hoặc độ phức tạp có thể tính chi phí theo cách bảo thủ và không đánh giá điều kiện runtime.
- Field cùng response key có thể vẫn được yêu cầu từ một selection khác.
- Các resolver cha cần chạy để tạo ra object chứa selection lồng nhau.

Vì vậy, hãy đo chi phí thực thi thay vì chỉ nhìn số field trong response. Nếu query cost được dùng để bảo vệ server, cần cấu hình chính sách giới hạn phù hợp với cách công cụ tính directive.

## 9. Sử dụng @include với Spring for GraphQL

Spring for GraphQL dùng GraphQL Java để parse, validate và thực thi operation. `@include` là directive chuẩn của GraphQL nên được xử lý tự động. Không cần khai báo `@IncludeMapping`, `@SchemaMapping` hay một resolver riêng cho directive.

Ví dụ SDL:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    description: String
}
```

Controller xử lý field gốc:

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

Client gửi operation:

```graphql
query ProductDetail($id: ID!, $showDescription: Boolean!) {
    product(id: $id) {
        id
        name
        description @include(if: $showDescription)
    }
}
```

Spring vẫn ánh xạ root field `product` về method `@QueryMapping product`. Field `description` được resolve theo cơ chế mặc định từ property/accessor của object hoặc resolver tương ứng nếu ứng dụng đã khai báo. Khi `showDescription` là `false`, GraphQL bỏ qua selection `description`; không cần kiểm tra biến `showDescription` trong controller để tự xây response.

Nếu cần tránh tải dữ liệu mô tả từ database, cần thiết kế data access hoặc projection phù hợp. `@include` ngăn field resolver chạy, nhưng nếu resolver cha đã tải toàn bộ entity cùng mô tả thì phần dữ liệu đó có thể đã được lấy trước khi GraphQL bỏ qua field con.

## 10. Kiểm thử điều kiện @include với GraphQlTester

Có thể kiểm tra cùng một document với hai giá trị variable khác nhau. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void includesDescriptionWhenRequested() {
        graphQlTester.document("""
                query ProductDetail($id: ID!, $showDescription: Boolean!) {
                    product(id: $id) {
                        id
                        description @include(if: $showDescription)
                    }
                }
                """)
            .variable("id", "p-101")
            .variable("showDescription", true)
            .execute()
            .path("product.description")
            .entity(String.class)
            .isEqualTo("A compact keyboard.");
    }

    @Test
    void omitsDescriptionWhenNotRequested() {
        graphQlTester.document("""
                query ProductDetail($id: ID!, $showDescription: Boolean!) {
                    product(id: $id) {
                        id
                        description @include(if: $showDescription)
                    }
                }
                """)
            .variable("id", "p-101")
            .variable("showDescription", false)
            .execute()
            .path("product.description")
            .pathDoesNotExist();
    }
}
```

Ví dụ trên giả định test có fixture sản phẩm `p-101` với mô tả đã biết và cung cấp mock hoặc test bean cho `ProductService`. Test thứ nhất xác minh field có dữ liệu khi điều kiện đúng; test thứ hai xác minh response path không tồn tại khi điều kiện sai. Có thể bổ sung kiểm tra tương tác service hoặc repository để xác nhận field resolver tốn kém không được gọi khi selection bị loại.

Với query dùng fragment, nên có test cho cả trường hợp fragment được đưa vào và trường hợp fragment bị bỏ qua. Với operation có cả `@include` và `@skip`, kiểm tra các tổ hợp Boolean để tránh đảo điều kiện.

## 11. Những giới hạn và lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `@include` mà không truyền argument `if` | Argument là bắt buộc | Khai báo và truyền `Boolean!` |
| Truyền null cho `if` | `Boolean!` không chấp nhận null | Gửi `true` hoặc `false` |
| Mong field xuất hiện với null khi điều kiện false | Nhầm lẫn giữa bỏ qua và null | Kiểm tra sự tồn tại của response key |
| Gắn directive vào vị trí không hỗ trợ | `@include` chỉ có các executable locations quy định | Dùng trên field, fragment spread hoặc inline fragment |
| Dùng directive để bảo vệ field nhạy cảm | Client có thể tự gửi query không có directive | Thực hiện authorization ở server |
| Nghĩ rằng field bị bỏ qua sẽ không tốn bất kỳ chi phí nào | Resolver cha, parse và validation vẫn có thể chạy | Đo query và thiết kế projection/data access |
| Dùng nhiều điều kiện khó đọc | Query khó bảo trì | Đặt tên variable theo ý nghĩa giao diện và đơn giản hóa selection |

`@include` không phải cơ chế lọc bản ghi trong danh sách. Nếu query trả về `[Product!]!`, directive trên field `description` quyết định có lấy mô tả cho các sản phẩm hay không; nó không loại các sản phẩm khỏi danh sách. Muốn lọc bản ghi, hãy dùng argument của field hoặc quy tắc truy vấn dữ liệu phù hợp.

## 12. Checklist sử dụng @include

- Điều kiện đã dùng kiểu `Boolean!` chưa?
- Variable có tên mô tả rõ phần giao diện hoặc dữ liệu cần bật không?
- Đã phân biệt field bị bỏ qua với field null hoặc list rỗng chưa?
- Directive được đặt đúng vị trí: field, fragment spread hoặc inline fragment?
- Có cần áp dụng cho cả fragment thay vì lặp trên từng field không?
- Query có kết hợp `@skip` theo cách dễ hiểu không?
- Quyền truy cập vẫn được kiểm tra phía server khi client tự thay đổi điều kiện?
- Đã kiểm thử cả trường hợp true và false chưa?
- Resolver cha có đang tải dữ liệu không cần thiết trước khi directive loại field con không?

`@include` giúp client điều khiển selection set theo một điều kiện Boolean ngay trong GraphQL document. Nó làm response linh hoạt, giảm việc tải và resolve những field không cần thiết, đồng thời cho phép tái sử dụng một query cho nhiều trạng thái giao diện. Với Spring for GraphQL, directive được GraphQL runtime xử lý tự động; ứng dụng vẫn cần thiết kế data access hiệu quả, kiểm tra quyền ở server và kiểm thử cả hai nhánh điều kiện.
