# Non-null type trong GraphQL SDL

Trong GraphQL, một trường có thể trả về giá trị hoặc `null`. Mặc định, các kiểu trong schema đều cho phép `null`. Khi muốn cam kết một trường luôn có giá trị, ta thêm dấu `!` sau kiểu dữ liệu để tạo **Non-null type**.

Ví dụ, `String` cho phép kết quả là chuỗi hoặc `null`, còn `String!` yêu cầu kết quả phải là chuỗi. Quy tắc này là một phần của hợp đồng GraphQL giữa server và client. Với Spring for GraphQL, hợp đồng được khai báo trong SDL; resolver Java phải trả về dữ liệu phù hợp với hợp đồng đó.

## 1. Kiểu nullable và Non-null type

Mặc định, kiểu GraphQL là nullable:

```graphql
type Product {
    name: String
    description: String
}
```

Trong ví dụ này, cả `name` và `description` đều có thể trả về `null`. Một response hợp lệ có thể là:

```json
{
  "data": {
    "product": {
      "name": "Keyboard",
      "description": null
    }
  }
}
```

Thêm dấu `!` sau kiểu để khai báo giá trị không được là `null`:

```graphql
type Product {
    id: ID!
    name: String!
    description: String
}
```

`id` và `name` phải có giá trị khi GraphQL hoàn tất việc phân giải các trường đó. `description` vẫn có thể là `null`. Nếu server trả về `null` cho `id` hoặc `name`, GraphQL tạo execution error và áp dụng quy tắc lan truyền null được trình bày ở phần sau.

Dấu `!` không có nghĩa là chuỗi phải khác rỗng. `String!` vẫn chấp nhận `""`; nó chỉ cấm giá trị `null`. Nếu nghiệp vụ yêu cầu chuỗi không được để trống, giới hạn độ dài hoặc phải đúng định dạng, ứng dụng cần kiểm tra thêm bằng validation hoặc logic nghiệp vụ.

## 2. Non-null với List

GraphQL cho phép kết hợp dấu `!` với kiểu danh sách. Cần phân biệt nullability của chính danh sách và nullability của từng phần tử trong danh sách.

| Cú pháp | Danh sách có thể `null`? | Phần tử có thể `null`? |
|---|---|---|
| `[String]` | Có | Có |
| `[String]!` | Không | Có |
| `[String!]` | Có | Không |
| `[String!]!` | Không | Không |

Ví dụ khai báo:

```graphql
type Product {
    tags: [String!]!
    aliases: [String]
    relatedIds: [ID!]
}
```

- `tags: [String!]!`: danh sách luôn phải tồn tại và từng phần tử đều phải là chuỗi khác `null`.
- `aliases: [String]`: danh sách có thể là `null`; nếu danh sách tồn tại, một phần tử cũng có thể là `null`.
- `relatedIds: [ID!]`: danh sách có thể là `null`, nhưng nếu có danh sách thì từng ID phải khác `null`.

Với `tags: [String!]!`, cả hai response sau đều hợp lệ:

```json
{ "tags": ["mechanical", "wireless"] }
```

```json
{ "tags": [] }
```

Danh sách rỗng không phải là `null`, vì vậy vẫn hợp lệ. Non-null không đặt ra yêu cầu danh sách phải có ít nhất một phần tử. Nếu nghiệp vụ cần tối thiểu một phần tử, phải kiểm tra điều kiện đó riêng.

## 3. Quy tắc lan truyền null (Null propagation)

Non-null là một cam kết của server. Nếu một field được khai báo Non-null nhưng resolver trả về `null`, hoặc quá trình thực thi field phát sinh lỗi khiến field không có giá trị, GraphQL ghi nhận lỗi và thay giá trị của field bằng `null` ở cấp nullable gần nhất. Nếu field cha cũng là Non-null, giá trị `null` tiếp tục lan truyền lên trên. Quy tắc này thường được gọi là *null bubbling*.

Xét schema:

```graphql
type Query {
    product: Product!
    status: String
}

type Product {
    id: ID!
    name: String!
    description: String
}
```

Nếu resolver của `Product.name` trả về `null`, field `name` vi phạm hợp đồng. Vì `name` là Non-null, đối tượng `Product` không thể được trả về đầy đủ và bị thay bằng `null`. `Query.product` cũng là Non-null nên giá trị `null` tiếp tục lan truyền lên cấp root. Response có thể có dạng:

```json
{
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Product.name.",
      "path": ["product", "name"]
    }
  ],
  "data": null
}
```

Thông điệp lỗi trên chỉ mang tính minh họa; nội dung cụ thể phụ thuộc runtime và cách ứng dụng xử lý exception. Điểm quan trọng là `data` có thể trở thành `null` vì vi phạm ở một field Non-null đã lan truyền qua các field cha Non-null.

Nếu khai báo `product: Product` (nullable) thay cho `product: Product!`, quá trình lan truyền sẽ dừng ở `product`. Khi đó các field root khác như `status` vẫn có thể được trả về:

```json
{
  "errors": [
    {
      "message": "A product field could not be completed.",
      "path": ["product", "name"]
    }
  ],
  "data": {
    "product": null,
    "status": "available"
  }
}
```

Thông điệp lỗi trong ví dụ này cũng là nội dung minh họa. GraphQL vẫn trả về các nhánh dữ liệu không bị ảnh hưởng bởi lỗi.

### Lan truyền null trong danh sách

Quy tắc tương tự áp dụng cho phần tử của list:

- Với `[Product]`, một phần tử `null` được chấp nhận; danh sách vẫn có thể được trả về.
- Với `[Product!]`, nếu một phần tử là `null`, toàn bộ danh sách trở thành `null`. Vì bản thân danh sách nullable, lan truyền dừng tại danh sách.
- Với `[Product!]!`, phần tử `null` làm danh sách thành `null`, sau đó vi phạm Non-null của chính danh sách và tiếp tục lan truyền lên field cha.
- Với `[Product]!`, danh sách không được `null`, nhưng từng phần tử vẫn có thể `null`.

Ví dụ, nếu schema khai báo `products: [Product!]!` và phần tử thứ hai không thể phân giải, GraphQL không thay riêng phần tử đó bằng `null`; toàn bộ field `products` bị thay bằng `null`, rồi tiếp tục lan truyền theo nullability của field cha.

## 4. Non-null trong Input, Argument và Mutation

Non-null cũng áp dụng cho dữ liệu client gửi lên server. Ví dụ:

```graphql
type Mutation {
    createProduct(input: ProductInput!): Product!
}

input ProductInput {
    name: String!
    description: String
    tags: [String!]!
}
```

Trong khai báo này:

- `input` là argument bắt buộc; client không thể bỏ qua hoặc truyền `null`.
- `name` là field bắt buộc trong input object.
- `description` có thể bị bỏ qua hoặc được truyền `null`.
- `tags` phải có danh sách và các phần tử trong danh sách không được là `null`; danh sách rỗng vẫn hợp lệ.
- Kết quả `Product!` cam kết mutation trả về một Product khác `null` khi thực thi thành công.

Ví dụ mutation hợp lệ:

```graphql
mutation {
    createProduct(input: {
        name: "Keyboard"
        description: "Wireless keyboard"
        tags: ["computer", "accessory"]
    }) {
        id
        name
    }
}
```

Nếu client bỏ `name`, bỏ `input`, hoặc truyền `null` cho một vị trí Non-null không có giá trị mặc định, GraphQL từ chối request trong bước kiểm tra/coercion đầu vào và resolver mutation không được gọi cho request không hợp lệ đó.

Có một điểm cần phân biệt: bỏ qua một giá trị nullable và truyền tường minh `null` là hai trạng thái đầu vào khác nhau. Ngoài ra, nếu argument hoặc input field Non-null có khai báo default value, client có thể bỏ qua giá trị đó và GraphQL sử dụng giá trị mặc định. Giá trị `null` tường minh vẫn không hợp lệ đối với Non-null.

## 5. Ánh xạ Non-null với resolver trong Spring for GraphQL

Spring for GraphQL thường dùng SDL để định nghĩa schema và các annotation như `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` để nối field với phương thức Java.

Ví dụ schema:

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

Resolver tương ứng:

```java
@Controller
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    Product product(@Argument String id) {
        return productService.findById(id);
    }
}
```

Ở đây argument `id: ID!` yêu cầu client cung cấp ID hợp lệ về mặt GraphQL. Trường `product: Product` cho phép resolver trả về `null`, ví dụ khi không tìm thấy sản phẩm. Nếu đổi schema thành `product(id: ID!): Product!`, trường hợp không tìm thấy và resolver trả về `null` sẽ trở thành lỗi thực thi Non-null và kích hoạt null propagation.

Các annotation Java như `@Nullable` hoặc `@NonNull` có thể giúp IDE, công cụ phân tích tĩnh và nhóm phát triển hiểu ý định của mã nguồn. Tuy nhiên, với cách xây dựng schema-first bằng SDL, dấu `!` trong schema mới là khai báo GraphQL quyết định nullability của API. Không nên giả định rằng đổi annotation Java sẽ tự động thay đổi SDL.

Điều này cũng đúng với kiểu trả về bất đồng bộ. Nếu resolver trả về một publisher không phát ra giá trị, chẳng hạn một `Mono` hoàn tất rỗng, GraphQL có thể nhận kết quả tương đương `null` cho field đó. Nếu field là Non-null, ứng dụng sẽ gặp quy tắc lỗi và lan truyền null như các trường hợp khác.

## 6. Cách lựa chọn nullable hay Non-null

Hãy chọn nullability dựa trên cam kết dữ liệu mà API có thể duy trì, không chỉ dựa trên việc cơ sở dữ liệu hiện tại có cột `NOT NULL` hay không.

| Trường hợp | Thiết kế thường phù hợp | Lý do |
|---|---|---|
| ID luôn tồn tại với một đối tượng hợp lệ | `ID!` | Client cần định danh ổn định. |
| Tên hiển thị luôn có khi đối tượng được trả về | `String!` | Server cam kết có tên. |
| Mô tả sản phẩm có thể chưa được nhập | `String` | `null` là trạng thái hợp lệ của dữ liệu. |
| Một collection luôn trả về được, dù không có phần tử | `[Item!]!` | Client nhận list, có thể là list rỗng. |
| Quan hệ có thể chưa tồn tại | `RelatedItem` | Không ép client coi quan hệ luôn có dữ liệu. |
| Argument cần để thực hiện thao tác | `ID!` hoặc `Input!` | GraphQL từ chối request thiếu dữ liệu bắt buộc. |

Một số nguyên tắc thực tế:

1. Chỉ khai báo Non-null khi server có thể bảo đảm giá trị đó trong mọi tình huống thực thi bình thường.
2. Dùng nullable cho dữ liệu thực sự có thể vắng mặt, chẳng hạn quan hệ tùy chọn hoặc thông tin chưa được cung cấp.
3. Với collection, cân nhắc `[Item!]!` nếu muốn client luôn xử lý một danh sách, kể cả khi danh sách rỗng.
4. Xem xét phạm vi ảnh hưởng của null bubbling. Một field Non-null sâu bên trong có thể làm mất dữ liệu ở cấp cha nếu các cấp đó cũng Non-null.
5. Khi thay đổi nullable thành Non-null, kiểm tra dữ liệu cũ, resolver, nguồn dữ liệu bên ngoài và các client đang sử dụng schema.

Non-null không thay thế các ràng buộc cơ sở dữ liệu, Bean Validation hay kiểm tra nghiệp vụ. Chẳng hạn, `price: Float!` không tự bảo đảm giá lớn hơn hoặc bằng 0; `email: String!` không tự kiểm tra định dạng email.

## 7. Những lỗi thường gặp

**Khai báo `String!` nhưng resolver có thể trả về `null`.** Hãy xác định trường hợp không có dữ liệu là hợp lệ hay là lỗi. Nếu hợp lệ, cân nhắc đổi SDL sang nullable. Nếu không hợp lệ, bảo đảm service/resolver xử lý tình huống đó và không để vi phạm hợp đồng.

**Cho rằng `[Item!]!` yêu cầu list phải có phần tử.** Cú pháp này vẫn cho phép `[]`. Muốn giới hạn số phần tử, cần validation riêng.

**Nhầm nullability của list với nullability của item.** Đọc từ trong ra ngoài: dấu `!` ngay sau kiểu item ràng buộc từng phần tử; dấu `!` sau dấu `]` ràng buộc chính list.

**Đánh dấu mọi field là Non-null để schema trông chặt chẽ.** Điều này có thể khiến một lỗi ở field con làm mất cả object hoặc nhánh dữ liệu lớn hơn do null bubbling. Chỉ cam kết những gì server thực sự bảo đảm.

**Nghĩ rằng `!` kiểm tra nội dung nghiệp vụ.** `String!` vẫn có thể là chuỗi rỗng, và `Int!` vẫn có thể là số âm. Hãy dùng validation cho các quy tắc đó.

**Chỉ kiểm tra schema mà không kiểm tra resolver.** SDL có thể hợp lệ nhưng resolver vẫn trả về `null` hoặc lỗi khi chạy. Cần kiểm thử cả request và response thực tế.

## 8. Kiểm thử hợp đồng Non-null

Khi kiểm thử API Spring for GraphQL, nên bao phủ cả trường hợp thành công và vi phạm hợp đồng:

- Với field Non-null có dữ liệu, xác minh response chứa giá trị đúng kiểu.
- Với field nullable không có dữ liệu, xác minh response chứa `null` mà không phát sinh lỗi chỉ vì nullability.
- Với field Non-null mà resolver trả về `null` hoặc phát sinh lỗi, xác minh response có `errors` và `data` bị null tại đúng cấp theo quy tắc lan truyền.
- Với argument hoặc input field Non-null bị thiếu hay được truyền `null`, xác minh request bị từ chối và resolver mutation không chạy.
- Với list, kiểm tra riêng list rỗng, phần tử null được phép và phần tử null bị cấm theo từng khai báo SDL.

`GraphQlTester` của Spring for GraphQL có thể gửi document và kiểm tra các nhánh dữ liệu cũng như lỗi trong response. Các kiểm thử này giúp phát hiện trường hợp schema đã đổi nullability nhưng resolver hoặc dữ liệu thực tế chưa đáp ứng cam kết mới.

## Kết luận

Non-null type dùng dấu `!` để biến nullability thành một phần rõ ràng của hợp đồng GraphQL. Nó áp dụng cho field đầu ra, list, từng phần tử trong list, argument và input field. Khi thiết kế SDL, hãy xác định đúng dữ liệu nào bắt buộc, hiểu tác động của null bubbling và bảo đảm resolver Spring thực hiện đúng cam kết đã công bố cho client.
