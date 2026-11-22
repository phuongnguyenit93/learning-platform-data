# Nested list type trong GraphQL

Trong GraphQL SDL, **list type** biểu diễn một danh sách các giá trị. Một list có thể chứa scalar, enum hoặc object type; phần tử của list cũng có thể là một list khác. Khi list lồng nhau, schema mô tả dữ liệu nhiều tầng như ma trận, nhóm sản phẩm theo danh mục, bảng dữ liệu hoặc các nhóm kết quả.

Điểm quan trọng khi khai báo nested list là hiểu rõ hai lớp quy tắc: dấu ngoặc vuông `[]` xác định cấu trúc danh sách, còn dấu chấm than `!` xác định vị trí nào không được phép `null`. Hai quy tắc này kết hợp đệ quy ở từng tầng của list.

## List type cơ bản

GraphQL dùng cặp ngoặc vuông để khai báo list:

```graphql
type Query {
  productIds: [ID]
  names: [String!]
  products: [Product!]
}
```

Các khai báo trên có ý nghĩa:

- `[ID]`: field có thể trả về `null` hoặc một danh sách; từng phần tử ID cũng có thể `null`.
- `[String!]`: field có thể là `null`, nhưng nếu trả về danh sách thì từng phần tử phải là chuỗi khác `null`.
- `[Product!]`: field có thể là `null`; từng phần tử trong danh sách phải là một `Product` hợp lệ.

List giữ nguyên thứ tự phần tử do server trả về. GraphQL không tự loại bỏ phần tử trùng lặp và cũng không tự quy định giới hạn số phần tử. Nếu không có dữ liệu, server thường trả về danh sách rỗng `[]`; danh sách rỗng khác với giá trị `null`.

## Cách đọc nested list type

Nested list được khai báo bằng cách đặt một list type bên trong một list type khác. Ví dụ:

```graphql
type Query {
  matrix: [[Int]]
}
```

`[[Int]]` là một danh sách bên ngoài, mỗi phần tử của danh sách bên ngoài lại là một danh sách số nguyên. Một giá trị phù hợp có thể là:

```json
{
  "data": {
    "matrix": [
      [1, 2, 3],
      [4, 5, 6],
      [7, 8, 9]
    ]
  }
}
```

Có thể đọc kiểu từ ngoài vào trong:

1. `[...]` ngoài cùng: danh sách các hàng.
2. `[...]` bên trong: mỗi hàng là một danh sách.
3. `Int`: mỗi phần tử trong hàng là số nguyên.

GraphQL cho phép lồng nhiều tầng, ví dụ `[[[String!]!]!]!`. Mỗi cặp ngoặc vuông tạo một lớp list. Tuy nhiên, nested list chỉ mô tả cấu trúc lồng nhau; nó không tự bảo đảm các hàng có cùng độ dài, số hàng cố định hay dữ liệu tạo thành một ma trận chữ nhật. Những ràng buộc đó phải được kiểm tra ở tầng nghiệp vụ.

## Kết hợp list với Non-Null

Dấu `!` có thể đặt sau kiểu phần tử hoặc sau dấu ngoặc vuông. Vị trí của nó quyết định chính xác giá trị nào được phép null.

Với list một chiều, bốn dạng thường gặp là:

| SDL | List có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| `[Int]` | Có | Có |
| `[Int]!` | Không | Có |
| `[Int!]` | Có | Không |
| `[Int!]!` | Không | Không |

Ví dụ:

- `[Int]!` yêu cầu resolver trả về một list. List có thể chứa `null`, chẳng hạn `[1, null, 3]`.
- `[Int!]` cho phép toàn bộ field là `null`, nhưng nếu có list thì các phần tử phải là số nguyên, chẳng hạn `[1, 2, 3]`.
- `[Int!]!` yêu cầu cả list và từng phần tử đều khác `null`.

Với nested list, quy tắc tương tự được áp dụng ở từng tầng:

| SDL | Ý nghĩa |
| --- | --- |
| `[[Int]]` | List ngoài có thể null; list con có thể null; phần tử Int có thể null. |
| `[[Int]!]!` | List ngoài và từng list con không được null; phần tử Int có thể null. |
| `[[Int!]]!` | List ngoài không được null; list con có thể null; phần tử Int không được null. |
| `[[Int!]!]` | List ngoài có thể null; list con và từng phần tử Int không được null. |
| `[[Int!]!]!` | List ngoài, từng list con và từng phần tử Int đều không được null. |

Ví dụ `[[Int!]!]!` có thể đọc như sau:

1. Dấu `!` cuối cùng: list ngoài bắt buộc tồn tại.
2. Dấu `!` ngay sau `]` bên trong: mỗi phần tử của list ngoài phải là một list con khác null.
3. Dấu `!` sau `Int`: từng số nguyên trong mỗi list con không được null.

```graphql
type Query {
  strictMatrix: [[Int!]!]!
  flexibleMatrix: [[Int!]]!
}
```

`strictMatrix` không cho phép null ở bất kỳ tầng nào. `flexibleMatrix` yêu cầu list ngoài tồn tại và từng số nguyên phải có giá trị, nhưng cho phép một phần tử của list ngoài là một list con `null`.

## Ví dụ nested list trong schema thực tế

### Ma trận số

Một API phân tích dữ liệu có thể trả về các hàng số liệu:

```graphql
type Query {
  salesByMonth: [[Float!]!]!
}
```

Response minh họa:

```json
{
  "data": {
    "salesByMonth": [
      [120.5, 132.0, 128.75],
      [140.0, 151.25, 149.5]
    ]
  }
}
```

Trong ví dụ này, mỗi hàng là một nhóm số liệu. Kiểu SDL bảo đảm không có list hoặc phần tử số liệu nào là null, nhưng không quy định mỗi tháng phải có đúng ba giá trị. Nếu nghiệp vụ yêu cầu mỗi hàng có cùng số cột, service cần kiểm tra điều kiện đó trước khi trả dữ liệu.

### Nhóm object theo danh mục

Nested list cũng có thể chứa object type thay vì scalar:

```graphql
type Product {
  id: ID!
  name: String!
  price: Float!
}

type Query {
  productGroups: [[Product!]!]!
}
```

Mỗi phần tử của list ngoài là một nhóm sản phẩm; mỗi nhóm là một list các `Product`. Ví dụ này có thể dùng để biểu diễn các nhóm được chia theo khu vực, mức giá hoặc một tiêu chí nghiệp vụ nào đó.

Khi client truy vấn `productGroups`, client vẫn phải chọn các field của `Product`:

```graphql
query ProductGroups {
  productGroups {
    id
    name
    price
  }
}
```

GraphQL áp dụng selection set cho từng object trong mọi list con. Nếu các field của `Product` cần resolver riêng, cơ chế field mapping vẫn được áp dụng cho từng object tương ứng.

## Nested list trong input

List type không chỉ xuất hiện ở output. GraphQL cũng hỗ trợ nested list trong đối số field và input object. Ví dụ, client gửi một ma trận số để server tính toán:

```graphql
input MatrixInput {
  values: [[Int!]!]!
}

type Mutation {
  calculateMatrix(input: MatrixInput!): MatrixSummary!
}

type MatrixSummary {
  rowCount: Int!
  columnCount: Int!
  total: Int!
}
```

Client có thể gửi variables như sau:

```graphql
mutation Calculate($input: MatrixInput!) {
  calculateMatrix(input: $input) {
    rowCount
    columnCount
    total
  }
}
```

```json
{
  "input": {
    "values": [
      [1, 2, 3],
      [4, 5, 6]
    ]
  }
}
```

Kiểu `[[Int!]!]!` yêu cầu input có list ngoài, mỗi hàng là list khác null và mỗi phần tử là Int khác null. Nếu client gửi `null` ở một tầng bị khai báo Non-Null, GraphQL từ chối input trước khi resolver xử lý.

### Quy tắc singleton-to-list coercion

GraphQL có quy tắc input coercion cho list: khi một giá trị đầu vào không phải list được cung cấp cho một vị trí có kiểu list, giá trị đó có thể được ép thành list chỉ có một phần tử, sau khi giá trị phần tử được coercion theo kiểu bên trong.

Ví dụ field sau khai báo một list chuỗi:

```graphql
type Query {
  search(tags: [String!]!): [String!]!
}
```

Client có thể truyền một chuỗi đơn làm đối số `tags`; GraphQL xử lý nó như list một phần tử tương đương `["graphql"]`. Dù vậy, khi viết client và variables, nên gửi đúng dạng mảng để payload thể hiện rõ cấu trúc dữ liệu dự kiến.

Quy tắc coercion chỉ giúp biểu diễn input linh hoạt. Nó không bỏ qua các ràng buộc nullability và không tự kiểm tra những điều kiện nghiệp vụ như số hàng, số cột hay giới hạn kích thước ma trận.

## Null propagation khi phần tử nested list bị lỗi

Nullability ảnh hưởng trực tiếp tới cách GraphQL xử lý lỗi trong quá trình resolve. Nếu resolver trả về `null` tại một vị trí được khai báo Non-Null, GraphQL tạo execution error và đẩy giá trị null lên vị trí cha gần nhất cho phép null.

Với list, nếu một phần tử không nullable bị lỗi, toàn bộ list chứa phần tử đó trở thành null. Nếu chính list đó cũng không nullable, null tiếp tục lan lên tầng cha. Quy tắc này lặp lại qua từng lớp nested list.

Xét hai field:

```graphql
type Query {
  strictMatrix: [[Int!]!]!
  tolerantMatrix: [[Int!]]!
}
```

Giả sử một số nguyên trong hàng thứ hai bị lỗi khi resolve:

- Với `strictMatrix`, phần tử Int không nullable làm list hàng thứ hai trở thành null. Vì hàng đó cũng là phần tử không nullable của list ngoài, list ngoài trở thành null. List ngoài lại không nullable nên null tiếp tục lan tới root response.
- Với `tolerantMatrix`, phần tử Int không nullable làm list hàng thứ hai trở thành null. Nhưng list ngoài cho phép phần tử list con null, nên các hàng còn lại vẫn có thể được trả về.

Response minh họa cho trường hợp thứ hai có thể là:

```json
{
  "data": {
    "tolerantMatrix": [
      [1, 2, 3],
      null,
      [7, 8, 9]
    ]
  },
  "errors": [
    {
      "message": "Không thể tính giá trị tại ô dữ liệu",
      "path": ["tolerantMatrix", 1, 0]
    }
  ]
}
```

`path` chỉ tới field, chỉ số hàng và chỉ số phần tử gây lỗi. Khi null lan tới một field nullable, phần dữ liệu còn lại có thể được giữ lại. Nếu null lan tới query root vì root field không nullable, `data` có thể trở thành `null` toàn bộ. Client nên đọc cả `data` và `errors` để xử lý dữ liệu một phần.

## Ánh xạ nested list trong Spring for GraphQL

Với Spring for GraphQL, nested list trong SDL thường được ánh xạ tự nhiên sang kiểu collection lồng nhau trong Java. Ví dụ schema:

```graphql
type Query {
  matrix: [[Int!]!]!
}
```

Controller có thể trả về `List<List<Integer>>`:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MatrixController {

    @QueryMapping
    public List<List<Integer>> matrix() {
        return List.of(
            List.of(1, 2, 3),
            List.of(4, 5, 6),
            List.of(7, 8, 9)
        );
    }
}
```

GraphQL Java xử lý các collection lồng nhau theo kiểu list đã khai báo trong schema. Kiểu Java cần tương thích với nullability của SDL: nếu schema dùng `!`, resolver phải bảo đảm không trả về null ở vị trí tương ứng. `Integer` là kiểu boxed nên có thể biểu diễn null; kiểu nguyên thủy `int` không thể biểu diễn null.

Với input, có thể nhận nested list bằng `@Argument`:

```java
@MutationMapping
public MatrixSummary calculateMatrix(@Argument MatrixInput input) {
    return matrixService.calculate(input.values());
}
```

Trong ví dụ này, `MatrixInput` là DTO hoặc record của ứng dụng có thuộc tính `values` tương ứng với `List<List<Integer>>`. Service cần kiểm tra các ràng buộc nghiệp vụ như ma trận rỗng, kích thước tối đa, số cột đồng nhất hoặc giới hạn giá trị.

### Nested object list và resolver

Khi list chứa object, mỗi object vẫn tuân theo schema type của nó. Ví dụ `[[Product!]!]!` nghĩa là GraphQL nhận list các nhóm Product; khi client chọn `name`, `price` hoặc field quan hệ khác, engine resolve các field đó cho từng Product.

Nested list không tự động gom các lần truy cập dữ liệu. Nếu field `seller` của mỗi Product cần truy vấn repository riêng, một ma trận có nhiều Product vẫn có thể tạo ra vấn đề N+1. Có thể dùng DataLoader hoặc `@BatchMapping` trong Spring for GraphQL để gom việc tải các quan hệ theo batch.

## Thiết kế nested list an toàn và hiệu quả

Nested list tiện lợi nhưng có thể tạo ra response lớn. Một query trả về nhiều nhóm, mỗi nhóm có hàng nghìn phần tử, có thể tiêu tốn nhiều bộ nhớ và thời gian serialize dù chỉ dùng một request.

Khi thiết kế schema, cần cân nhắc:

- **Chọn nullability theo hợp đồng:** chỉ dùng `!` khi server thực sự bảo đảm giá trị tồn tại. Đặt Non-Null quá chặt có thể làm lỗi một phần tử khiến cả cấu trúc lớn bị null.
- **Giới hạn kích thước:** kiểm tra số nhóm, số hàng và số phần tử tối đa ở tầng nghiệp vụ; không dựa vào SDL để giới hạn độ dài list.
- **Phân trang:** nếu mỗi nhóm có thể tăng không giới hạn, cân nhắc trả về connection hoặc field có tham số phân trang thay vì một nested list khổng lồ.
- **Kiểm soát độ sâu và độ phức tạp:** nested list kết hợp với object relationship có thể làm tăng số resolver và chi phí thực thi. Áp dụng query depth/complexity limits phù hợp.
- **Batch dữ liệu quan hệ:** dùng DataLoader hoặc `@BatchMapping` khi nhiều object trong list cần tải chung một loại dữ liệu liên quan.
- **Kiểm tra đầu vào:** nested list input cần giới hạn kích thước, kiểm tra hàng rỗng, độ dài từng hàng và quy tắc miền nghiệp vụ.
- **Tránh dùng nested list chỉ để nhóm tùy tiện:** nếu mỗi phần tử nhóm có metadata như tên nhóm, tổng số hoặc mã định danh, một object type chứa field list thường diễn đạt rõ hơn.

Ví dụ, thay vì chỉ trả `[[Product!]!]!`, có thể khai báo kiểu nhóm có thông tin riêng:

```graphql
type ProductGroup {
  groupId: ID!
  title: String!
  products: [Product!]!
}

type Query {
  productGroups: [ProductGroup!]!
}
```

Cách này cho phép client truy cập metadata của từng nhóm và phân trang danh sách sản phẩm bên trong nếu schema được thiết kế thêm các đối số tương ứng.

## Lỗi thường gặp với nested list

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Schema validation báo sai kiểu trả về | Resolver trả list một chiều trong khi SDL yêu cầu list lồng nhau. | Đảm bảo kiểu Java có đúng số tầng collection, ví dụ `List<List<Integer>>`. |
| Response có `null` ngoài dự kiến | SDL cho phép null ở tầng list hoặc resolver trả null. | Xem lại vị trí `!` và hợp đồng trả về của service. |
| Một phần response biến mất khi một phần tử lỗi | Phần tử hoặc list cha được khai báo Non-Null nên null lan lên. | Xác định vị trí nullable phù hợp để cô lập lỗi theo nghiệp vụ. |
| Client gửi mảng nhưng resolver nhận sai cấu trúc | JSON variables không khớp số tầng list hoặc input DTO không đúng cấu trúc. | So sánh SDL, JSON variables và kiểu `@Argument`. |
| Dữ liệu trông giống ma trận nhưng các hàng không đều nhau | GraphQL list không quy định số phần tử mỗi hàng. | Kiểm tra số cột và hình dạng dữ liệu trong service. |
| Request nested list làm server chậm hoặc tốn bộ nhớ | Kích thước list lớn hoặc field lồng nhau tạo nhiều lần truy cập dữ liệu. | Giới hạn kích thước, phân trang, batching và query complexity. |

Khi debug, hãy đọc kiểu từ ngoài vào trong, xác định mỗi dấu `[]` tương ứng với một tầng collection, rồi kiểm tra `!` tại từng tầng. Sau đó đối chiếu với dữ liệu resolver trả về hoặc cấu trúc JSON variables.

## Ghi nhớ

Nested list type cho phép GraphQL biểu diễn dữ liệu nhiều tầng như `[[Int]]` hoặc `[[Product!]!]!`. Dấu ngoặc vuông tạo cấu trúc list; dấu `!` xác định list hoặc phần tử tại vị trí đó có được phép null hay không. Quy tắc nullability áp dụng ở từng tầng và quyết định cách lỗi lan truyền trong response.

Trong Spring for GraphQL, nested list thường được ánh xạ sang collection Java lồng nhau như `List<List<Integer>>`. SDL không tự giới hạn số hàng, số cột hoặc kích thước response; service cần xác thực dữ liệu, còn resolver và DataLoader cần được thiết kế để tránh truy vấn dư thừa khi list chứa nhiều object.
