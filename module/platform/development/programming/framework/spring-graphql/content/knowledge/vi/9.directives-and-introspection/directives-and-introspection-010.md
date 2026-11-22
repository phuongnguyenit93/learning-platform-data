# GraphQL documentation trong schema

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của description trong GraphQL schema.
- Phân biệt mô tả được introspection giữ lại với comment chỉ phục vụ người đọc mã nguồn.
- Viết documentation cho type, field, argument, input field, enum và enum value bằng SDL.
- Dùng directive @deprecated để thông báo API sắp ngừng hỗ trợ.
- Đọc description và thông tin deprecation qua GraphQL introspection.
- Bật GraphiQL trong Spring Boot để khám phá schema và tài liệu API.
- Viết mô tả ngắn gọn, chính xác và hữu ích cho client.

## 1. Vì sao cần documentation ngay trong schema?

GraphQL schema là hợp đồng giữa server và client. Schema mô tả những type nào tồn tại, field nào được truy vấn, argument nào được truyền vào và kiểu dữ liệu nào được trả về.

Tuy nhiên, tên field và kiểu dữ liệu chưa đủ để giải thích ý nghĩa nghiệp vụ. Ví dụ, một field có tên status và kiểu String chưa cho biết những giá trị nào hợp lệ, trạng thái nào là cuối cùng hay client có được phép cập nhật nó hay không.

GraphQL hỗ trợ description ngay trong Schema Definition Language (SDL). Description được lưu trong schema và có thể được truy xuất bằng introspection. Các công cụ như GraphiQL có thể hiển thị mô tả đó trong tài liệu API.

Ví dụ:

~~~graphql
"""
A book available in the catalog.
"""
type Book {
  """
  Stable identifier of the book.
  """
  id: ID!

  """
  Title displayed to readers.
  """
  title: String!
}
~~~

Khi client khám phá schema, nó có thể đọc được ý nghĩa của type Book và hai field id, title mà không cần mở mã nguồn server.

Documentation trong schema giúp:

- Client hiểu mục đích của field và argument.
- Công cụ tạo tài liệu API tự động có nội dung nghiệp vụ.
- Đội frontend và backend thống nhất cách sử dụng API.
- Người phát triển nhận biết field cũ, field thay thế và giới hạn sử dụng.
- Giảm sự phụ thuộc vào tài liệu bên ngoài có thể bị lỗi thời.

## 2. Description khác với comment trong SDL

SDL hỗ trợ cả comment và description, nhưng hai thành phần có mục đích khác nhau.

### Comment

Comment bắt đầu bằng dấu #. Nó phục vụ người đọc file SDL và không trở thành metadata description trong GraphQL schema.

~~~graphql
# Book data returned by the catalog.
type Book {
  id: ID!
  title: String!
}
~~~

Câu comment ở trên không xuất hiện như description của Book khi client introspect schema.

### Description

Description là một string literal được đặt ngay trước định nghĩa mà nó mô tả. Có thể dùng string một dòng hoặc block string nhiều dòng.

~~~graphql
"Represents a book in the catalog."
type Book {
  "Stable identifier."
  id: ID!

  """
  Title shown to readers.
  The value is localized by the catalog service.
  """
  title: String!
}
~~~

Description được gắn với schema element tương ứng và có thể truy xuất qua introspection.

| Thành phần | Comment bằng # | Description bằng string |
|---|---|---|
| Giúp người đọc file SDL | Có | Có |
| Được lưu thành metadata description | Không | Có |
| Truy xuất qua introspection | Không | Có |
| Hiển thị trong công cụ tài liệu schema | Không trực tiếp | Có |

Hãy dùng comment cho ghi chú về tổ chức file, quyết định triển khai hoặc nhắc việc nội bộ. Dùng description cho thông tin mà người sử dụng GraphQL API cần biết.

## 3. Cú pháp string và block string

Description có thể dùng string literal thông thường:

~~~graphql
"Returns the display name of the author."
type Author {
  name: String!
}
~~~

Với mô tả nhiều câu hoặc cần xuống dòng, dùng block string ba dấu nháy kép:

~~~graphql
"""
Represents an author in the catalog.

An author can be associated with multiple books.
The name is displayed according to the user's locale.
"""
type Author {
  name: String!
}
~~~

Block string giúp mô tả dài dễ đọc hơn trong SDL. Nội dung được xử lý theo quy tắc block string của GraphQL, bao gồm việc loại bỏ phần thụt lề chung.

Một số nguyên tắc:

- Đặt description ngay trước element được mô tả.
- Viết câu đầy đủ, dùng thuật ngữ thống nhất với domain.
- Tránh mô tả điều hiển nhiên chỉ bằng cách lặp lại tên field.
- Không nhồi thông tin triển khai nội bộ vào tài liệu công khai.
- Nếu description có nhiều ý, dùng block string và tách đoạn hợp lý.

## 4. Document type và field

Type description nên giải thích đối tượng đại diện cho điều gì trong domain. Field description nên mô tả ý nghĩa, đơn vị, quy tắc và điều kiện có thể ảnh hưởng đến client.

Ví dụ:

~~~graphql
"""
A monetary amount represented in the currency of the order.
"""
type Money {
  """
  Amount in the smallest currency unit.
  For VND, this value represents đồng.
  """
  amount: Int!

  """
  ISO 4217 currency code, such as VND or USD.
  """
  currency: String!
}

"""
An order placed by a customer.
"""
type Order {
  """
  Unique order identifier.
  """
  id: ID!

  """
  Current lifecycle state of the order.
  """
  status: OrderStatus!

  """
  Total amount charged for this order.
  """
  total: Money!
}
~~~

Ở ví dụ này, description của Money giải thích ý nghĩa tổng thể. Description của amount làm rõ đơn vị lưu trữ; currency chỉ ra mã tiền tệ theo ISO 4217. Client có đủ ngữ cảnh để hiển thị số tiền chính xác hơn.

Không nên ghi mô tả kiểu “The amount” cho field amount nếu người dùng vẫn không biết amount được tính theo đơn vị nào.

## 5. Document Query, Mutation và argument

Các field trong Query và Mutation cũng cần mô tả rõ hành vi. Đặc biệt, argument nên giải thích điều kiện, đơn vị, giới hạn và giá trị mặc định nếu chúng có ý nghĩa nghiệp vụ.

~~~graphql
type Query {
  """
  Finds an order by its identifier.

  Returns null when the order does not exist.
  """
  order(
    """
    Identifier returned when the order was created.
    """
    id: ID!
  ): Order

  """
  Returns orders visible to the current user.

  Results are ordered by creation time, newest first.
  """
  orders(
    """
    Maximum number of orders to return.
    Must be between 1 and 100.
    """
    first: Int = 20
  ): [Order!]!
}

type Mutation {
  """
  Cancels an order if its current state allows cancellation.

  The operation may fail when fulfillment has already started.
  """
  cancelOrder(
    """
    Identifier of the order to cancel.
    """
    id: ID!
  ): Order!
}
~~~

Description cho argument được đặt bên trong dấu ngoặc của field, ngay trước argument tương ứng.

Một mô tả tốt cho argument nên trả lời các câu hỏi:

- Argument xác định đối tượng hay điều kiện nào?
- Giá trị có đơn vị hoặc định dạng gì?
- Có giới hạn min/max hay tập giá trị cho phép không?
- Khi bỏ qua argument thì hành vi mặc định là gì?
- Giá trị null có ý nghĩa gì nếu argument nullable?

Đừng chỉ mô tả rằng first là “number of items”. Hãy ghi rõ giới hạn và cách sắp xếp nếu đó là một phần của hợp đồng API.

## 6. Document input object và input field

Input object thường đại diện cho dữ liệu tạo mới hoặc cập nhật. Description cần làm rõ ý nghĩa của từng field, đặc biệt với field nullable hoặc field có thể bị bỏ qua.

~~~graphql
"""
Information required to create a customer account.
"""
input CreateCustomerInput {
  """
  Full name displayed on invoices and customer pages.
  """
  fullName: String!

  """
  Email address used for account notifications.
  Must be unique within the customer system.
  """
  email: String!

  """
  Optional phone number in international format.
  """
  phoneNumber: String
}
~~~

Với mutation cập nhật một phần, cần giải thích sự khác biệt giữa bỏ qua field và truyền null nếu API có hỗ trợ hai hành vi khác nhau.

~~~graphql
"""
Fields that can be changed on an existing customer.
Omitted fields remain unchanged.
A nullable field explicitly set to null is cleared.
"""
input UpdateCustomerInput {
  displayName: String
  phoneNumber: String
}
~~~

Description giúp client hiểu ý nghĩa nghiệp vụ, nhưng bản thân description không thay đổi cách GraphQL bind dữ liệu. Logic phân biệt omitted và explicit null vẫn phải được triển khai ở resolver hoặc lớp xử lý input tương ứng.

## 7. Document enum và enum value

Enum giới hạn một field vào tập giá trị xác định. Nên mô tả cả enum và từng value để client hiểu ý nghĩa của mỗi trạng thái.

~~~graphql
"""
Lifecycle states of an order.
"""
enum OrderStatus {
  """
  The order has been created but payment is pending.
  """
  PENDING

  """
  Payment was confirmed and the order is being prepared.
  """
  CONFIRMED

  """
  The order has been handed to the delivery provider.
  """
  SHIPPED

  """
  The order was delivered to the customer.
  """
  DELIVERED

  """
  The order was cancelled before completion.
  """
  CANCELLED
}
~~~

Description của enum giải thích ý nghĩa chung. Description của từng value làm rõ trạng thái và giúp client tránh diễn giải theo tên một cách sai lệch.

Nếu enum có các trạng thái chỉ xuất hiện trong luồng nội bộ, hãy cân nhắc liệu chúng có nên được expose qua API hay không. Documentation không thay thế việc thiết kế đúng phạm vi dữ liệu công khai.

## 8. Dùng @deprecated để document vòng đời field

Khi API cần thay thế một field hoặc enum value, không nên xóa ngay nếu client vẫn đang sử dụng. GraphQL có directive chuẩn @deprecated để đánh dấu phần tử không còn được khuyến nghị.

Ví dụ:

~~~graphql
type Customer {
  id: ID!

  """
  Legacy display name field.
  Use fullName instead.
  """
  name: String @deprecated(
    reason: "Use fullName instead."
  )

  """
  Customer's full display name.
  """
  fullName: String!
}
~~~

Có thể áp dụng @deprecated cho enum value:

~~~graphql
enum PaymentMethod {
  CARD

  """
  Legacy bank transfer option.
  """
  BANK_TRANSFER @deprecated(
    reason: "Use BANK_REDIRECT instead."
  )

  BANK_REDIRECT
}
~~~

Directive @deprecated có các đặc điểm:

- reason giải thích lý do ngừng khuyến nghị sử dụng.
- Nếu không truyền reason, GraphQL sử dụng lý do mặc định theo specification.
- Công cụ introspection có thể hiển thị trạng thái deprecated và lý do.
- Client có thể chuyển sang field hoặc enum value thay thế trong thời gian tương thích.

Ở các phiên bản GraphQL hỗ trợ, directive này cũng có thể áp dụng cho một số input value definitions như argument và input field. Hãy xác nhận phiên bản GraphQL Java mà dự án đang sử dụng trước khi áp dụng các vị trí mới hơn.

Deprecated không đồng nghĩa với bị xóa. Server vẫn có thể nhận query sử dụng field đó cho đến khi field thực sự được loại bỏ khỏi schema.

## 9. Đọc documentation bằng introspection

GraphQL introspection cho phép client hỏi chính schema về type, field, argument, enum và directive. Các metadata description cũng được cung cấp qua các trường introspection tương ứng.

Ví dụ, lấy mô tả của type Book và các field:

~~~graphql
query BookDocumentation {
  __type(name: "Book") {
    name
    description
    fields {
      name
      description
      isDeprecated
      deprecationReason
      args {
        name
        description
      }
    }
  }
}
~~~

Một phần response có thể giống như sau:

~~~json
{
  "data": {
    "__type": {
      "name": "Book",
      "description": "A book available in the catalog.",
      "fields": [
        {
          "name": "id",
          "description": "Stable identifier of the book.",
          "isDeprecated": false,
          "deprecationReason": null,
          "args": []
        }
      ]
    }
  }
}
~~~

Có thể khám phá enum và mô tả từng giá trị:

~~~graphql
query OrderStatusDocumentation {
  __type(name: "OrderStatus") {
    name
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
  }
}
~~~

Các trường quan trọng:

| Introspection type | Metadata |
|---|---|
| __Type | name, description, fields, inputFields, enumValues |
| __Field | name, description, args, isDeprecated, deprecationReason |
| __InputValue | name, description, type, defaultValue |
| __EnumValue | name, description, isDeprecated, deprecationReason |
| __Directive | name, description, locations, args |

Introspection không trả về comment bắt đầu bằng #. Chỉ description đã được khai báo trong schema mới có thể được truy xuất dưới dạng metadata mô tả.

## 10. Khám phá documentation bằng GraphiQL trong Spring Boot

Spring Boot có thể cung cấp giao diện GraphiQL để phát triển và khám phá GraphQL API. Khi GraphiQL được bật, người phát triển có thể chạy query và xem tài liệu schema dựa trên introspection.

Ví dụ cấu hình:

~~~yaml
spring:
  graphql:
    graphiql:
      enabled: true
      path: /graphiql
~~~

Sau khi ứng dụng khởi động với HTTP GraphQL transport và cấu hình phù hợp, mở đường dẫn GraphiQL đã cấu hình trên trình duyệt.

Trong giao diện GraphiQL, phần Documentation Explorer có thể hiển thị:

- Các root operation như Query, Mutation và Subscription.
- Danh sách object type, interface, union và enum.
- Description của type và field.
- Argument, kiểu dữ liệu và giá trị mặc định.
- Thông tin deprecated cùng lý do.

Nếu phần mô tả không xuất hiện, hãy kiểm tra SDL đã dùng description string thay vì chỉ dùng comment. Đồng thời kiểm tra introspection có được cho phép trong môi trường đang chạy hay không.

GraphiQL là công cụ hỗ trợ phát triển. Việc bật giao diện này trong production cần tuân theo chính sách triển khai và bảo mật của hệ thống.

## 11. Documentation không thay thế validation và authorization

Description chỉ cung cấp thông tin cho người đọc schema. Nó không thực thi quy tắc nghiệp vụ.

Ví dụ, mô tả argument first có giới hạn từ 1 đến 100 không khiến GraphQL tự động từ chối giá trị 500. Resolver hoặc lớp validation vẫn phải kiểm tra giới hạn đó.

Tương tự:

- Mô tả “Only the owner can view this field” không tự bảo vệ field.
- Mô tả “Email must be unique” không tạo unique constraint trong database.
- Mô tả “This operation is idempotent” không tự làm mutation trở nên idempotent.
- @deprecated thông báo vòng đời API nhưng không tự chuyển request sang field mới.

Hãy triển khai validation, authorization, transaction và các quy tắc tương ứng trong server. Documentation phải mô tả đúng hành vi đã được triển khai, không được dùng để hứa hẹn hành vi mà hệ thống chưa bảo đảm.

## 12. Quy tắc viết documentation tốt

Một schema dễ sử dụng cần description nhất quán và có giá trị thực tế. Có thể áp dụng checklist sau khi review SDL:

- [ ] Mỗi type quan trọng có description giải thích ý nghĩa nghiệp vụ.
- [ ] Field có quy tắc đặc biệt, đơn vị hoặc điều kiện sử dụng đã được mô tả.
- [ ] Argument có giới hạn, định dạng và hành vi mặc định được giải thích.
- [ ] Input field phân biệt rõ required, optional và nullable.
- [ ] Enum và enum value có mô tả rõ ràng.
- [ ] Field hoặc enum value cũ có @deprecated và lý do thay thế.
- [ ] Description không mâu thuẫn với validation và hành vi resolver.
- [ ] Không dùng comment # thay cho description khi nội dung cần hiển thị cho client.
- [ ] Không đưa thông tin bí mật hoặc chi tiết triển khai nội bộ vào schema công khai.

Nên ưu tiên mô tả điều client cần biết để sử dụng API đúng. Ví dụ, với field amount, đơn vị tiền tệ và quy tắc làm tròn hữu ích hơn câu mô tả lặp lại tên field.

## 13. Ví dụ schema được document đầy đủ

Ví dụ tổng hợp dưới đây kết hợp description cho type, field, argument, input object, enum và deprecation:

~~~graphql
scalar Date

"""
Lifecycle states of a reservation.
"""
enum ReservationStatus {
  """
  Reservation is awaiting confirmation.
  """
  PENDING

  """
  Reservation has been confirmed.
  """
  CONFIRMED

  """
  Reservation has been cancelled.
  """
  CANCELLED
}

"""
A reservation made by a customer.
"""
type Reservation {
  """
  Stable reservation identifier.
  """
  id: ID!

  """
  Current state in the reservation lifecycle.
  """
  status: ReservationStatus!

  """
  Customer-facing note attached to the reservation.
  """
  note: String

  """
  Legacy reference field. Use id instead.
  """
  reference: String @deprecated(
    reason: "Use id instead."
  )
}

"""
Information required to create a reservation.
"""
input CreateReservationInput {
  """
  Identifier of the customer making the reservation.
  """
  customerId: ID!

  """
  Date on which the reservation takes place.
  """
  reservationDate: Date!

  """
  Optional note visible to the customer.
  """
  note: String
}

type Query {
  """
  Finds a reservation by its identifier.

  Returns null if no matching reservation exists.
  """
  reservation(
    """
    Stable reservation identifier.
    """
    id: ID!
  ): Reservation
}

type Mutation {
  """
  Creates a reservation for the current customer.
  """
  createReservation(
    """
    Reservation details supplied by the client.
    """
    input: CreateReservationInput!
  ): Reservation!
}
~~~

Khi công cụ introspect schema, client có thể lấy description của Reservation, status, note, input CreateReservationInput và argument của từng operation. Field reference cũng được nhận diện là deprecated và cung cấp lý do thay thế.

## Kết luận

GraphQL documentation trong schema được khai báo bằng description string của SDL. Khác với comment #, description được lưu thành metadata và có thể truy xuất qua introspection. Có thể mô tả type, field, argument, input field, enum và enum value để tạo hợp đồng API dễ hiểu.

Kết hợp description với @deprecated, introspection và GraphiQL giúp client khám phá schema, hiểu cách sử dụng và chuyển đổi khỏi API cũ. Trong Spring for GraphQL, hãy xem documentation là một phần của thiết kế schema và giữ nội dung mô tả đồng bộ với validation, authorization cùng hành vi thực tế của resolver.

## Tài liệu tham khảo

- [GraphQL Specification — Descriptions](https://spec.graphql.org/October2021/#sec-Descriptions)
- [GraphQL Specification — Type System](https://spec.graphql.org/October2021/#sec-Type-System)
- [GraphQL Specification — Introspection](https://spec.graphql.org/October2021/#sec-Introspection)
- [GraphQL Specification — @deprecated](https://spec.graphql.org/October2021/#sec--deprecated)
- [Spring Boot — Spring for GraphQL and GraphiQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
