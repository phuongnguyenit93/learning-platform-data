# Đặt tên type và field trong GraphQL Schema

## Mục tiêu

Sau bài học này, bạn có thể:

- Áp dụng quy tắc đặt tên hợp lệ của GraphQL.
- Phân biệt cách đặt tên cho object type, interface, union, scalar, enum và input type.
- Đặt tên field, argument và root field sao cho thể hiện đúng ngữ nghĩa nghiệp vụ.
- Dùng nhất quán chữ hoa, chữ thường, số ít, số nhiều và cách viết tắt.
- Viết mô tả schema để client hiểu ý nghĩa của type và field.
- Nhận biết những tên mơ hồ, tên gắn với chi tiết triển khai và các tên dành riêng cho introspection.
- Đổi tên schema có kiểm soát để hạn chế ảnh hưởng đến client hiện tại.

## 1. Vì sao naming quan trọng trong GraphQL?

Trong GraphQL, schema là hợp đồng mà client trực tiếp sử dụng. Client viết operation bằng tên type, field, argument và enum value mà server công bố. IDE, công cụ introspection và code generator cũng dựa vào các tên này để gợi ý, kiểm tra và sinh mã.

Ví dụ, hai schema sau có thể cùng trả về thông tin một cuốn sách:

~~~graphql
type Query {
    getBookById(bookID: ID!): Book
}
~~~

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Schema thứ hai ngắn gọn và thể hiện đúng mô hình tài nguyên mà client đang truy vấn. Client đọc operation cũng dễ hiểu hơn:

~~~graphql
query FindBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Naming tốt giúp:

- Client hiểu field trả về dữ liệu gì mà không phải đọc implementation.
- Schema dễ khám phá bằng GraphiQL, GraphQL IDE và introspection.
- Các type và field nhất quán giữa nhiều nhóm phát triển.
- Code sinh tự động từ schema dễ đọc và ít gây nhầm lẫn.
- Việc tiến hóa API có thể được thực hiện mà không tạo ra nhiều tên gần giống nhau.

Tên trong GraphQL là một phần của API công khai. Đổi tên field, argument, type hoặc enum value có thể làm operation của client không còn hợp lệ. Vì vậy, naming nên được quyết định ngay khi thiết kế schema.

## 2. Quy tắc cú pháp của một tên GraphQL

GraphQL dùng quy tắc cú pháp thống nhất cho tên (Name). Một tên hợp lệ:

- Bắt đầu bằng chữ cái ASCII hoặc dấu gạch dưới.
- Các ký tự tiếp theo có thể là chữ cái ASCII, chữ số hoặc dấu gạch dưới.
- Phân biệt chữ hoa và chữ thường.
- Không chứa dấu gạch ngang, dấu cách hoặc dấu chấm.

Dạng tổng quát:

~~~text
[_A-Za-z][_0-9A-Za-z]*
~~~

Ví dụ:

| Tên | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `Book` | Có | Bắt đầu bằng chữ cái |
| `bookDetail` | Có | Chữ camelCase |
| `book_2` | Có | Chữ số ở vị trí sau ký tự đầu |
| `_internalCode` | Có về cú pháp | Dấu gạch dưới được phép |
| `2Book` | Không | Bắt đầu bằng chữ số |
| `book-title` | Không | Chứa dấu gạch ngang |
| `book.title` | Không | Chứa dấu chấm |
| `book title` | Không | Chứa khoảng trắng |

GraphQL phân biệt hoa thường. `Book`, `book` và `BOOK` là ba tên khác nhau. Không nên thay đổi kiểu viết hoa giữa các vị trí tham chiếu.

Các tên bắt đầu bằng hai dấu gạch dưới, chẳng hạn `__typename`, được dành riêng cho hệ thống introspection của GraphQL. Không đặt tên type, field hoặc thành phần schema của ứng dụng với tiền tố `__`. Client có thể dùng `__typename` để nhận biết kiểu cụ thể của một giá trị trong quá trình thực thi.

Lưu ý: cú pháp cho phép dấu gạch dưới ở đầu tên, nhưng điều đó không có nghĩa mọi tên bắt đầu bằng dấu gạch dưới đều là lựa chọn tốt. Hãy dành các quy ước nội bộ cho nhu cầu thực sự cần thiết và tránh đụng vào namespace introspection.

## 3. Quy ước chữ hoa và chữ thường

GraphQL không bắt buộc một kiểu viết hoa cụ thể cho từng loại thành phần. Tuy nhiên, cộng đồng GraphQL có các quy ước phổ biến giúp người đọc nhận ra loại tên ngay khi nhìn vào schema.

| Thành phần | Quy ước thường dùng | Ví dụ |
| --- | --- | --- |
| Object type | PascalCase | `Book`, `Author` |
| Interface | PascalCase | `Node`, `Publishable` |
| Union | PascalCase | `SearchResult` |
| Scalar tùy chỉnh | PascalCase | `DateTime`, `EmailAddress` |
| Enum type | PascalCase | `BookStatus` |
| Enum value | UPPER_SNAKE_CASE | `IN_STOCK`, `OUT_OF_STOCK` |
| Field | lowerCamelCase | `title`, `publishedAt` |
| Argument | lowerCamelCase | `authorId`, `pageSize` |
| Input object | PascalCase, thường kết thúc bằng Input | `CreateBookInput` |
| Mutation payload | PascalCase, thường kết thúc bằng Payload | `CreateBookPayload` |
| Operation name phía client | PascalCase | `FindBookDetail` |

Các quy ước này không làm thay đổi khả năng thực thi của GraphQL, nhưng tạo ra một ngôn ngữ chung cho schema.

### 3.1. PascalCase cho tên type

Tên type nên là danh từ hoặc khái niệm miền nghiệp vụ:

~~~graphql
scalar Money

type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
~~~

`Book` và `Author` biểu diễn hai khái niệm mà client có thể nhận diện. Không nên đặt tên type theo tên bảng hoặc tên class persistence nếu các tên đó không phản ánh hợp đồng API.

### 3.2. lowerCamelCase cho field và argument

Field và argument bắt đầu bằng chữ thường, các từ tiếp theo viết hoa chữ cái đầu:

~~~graphql
type Book {
    id: ID!
    publishedAt: DateTime
    coverImageUrl: String
}

type Query {
    book(authorId: ID!): Book
}
~~~

Dùng nhất quán `authorId`, `publishedAt` và `coverImageUrl` thay vì trộn `authorID`, `published_at` hoặc `cover_image_url`.

### 3.3. UPPER_SNAKE_CASE cho enum value

Enum value thường viết hoa và phân tách từ bằng dấu gạch dưới:

~~~graphql
enum OrderStatus {
    PENDING_PAYMENT
    PAID
    READY_TO_SHIP
    SHIPPED
    CANCELLED
}
~~~

Tên enum type vẫn dùng PascalCase. Chỉ các giá trị bên trong enum dùng UPPER_SNAKE_CASE.

## 4. Đặt tên cho các loại type

Tên type nên phản ánh khái niệm mà client làm việc với, không mô tả cách dữ liệu được lưu hoặc cách server triển khai.

### 4.1. Object type: danh từ số ít

Object type thường dùng danh từ số ít vì một giá trị của type biểu diễn một thực thể:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
~~~

Dùng `Book` thay vì `Books` cho object type. Khi field trả về một danh sách, tên field mới thường ở dạng số nhiều:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

Quy tắc này giúp người đọc phân biệt một đối tượng với tập hợp đối tượng ngay từ tên field.

### 4.2. Interface: đặt tên cho hợp đồng chung

Interface biểu diễn tập field mà nhiều object type cùng cung cấp. Tên interface nên mô tả khái niệm hoặc khả năng chung:

~~~graphql
scalar DateTime

interface Node {
    id: ID!
}

interface Publishable {
    publishedAt: DateTime
}

type Book implements Node & Publishable {
    id: ID!
    title: String!
    publishedAt: DateTime
}

type Article implements Node & Publishable {
    id: ID!
    headline: String!
    publishedAt: DateTime
}
~~~

`Node` mô tả một đối tượng có định danh; `Publishable` mô tả khả năng xuất bản. Tên interface không nên gắn với một class Java cụ thể hoặc một chi tiết kỹ thuật của repository.

Chỉ tạo interface khi các type thực sự chia sẻ một hợp đồng có ý nghĩa. Không nên tạo interface chỉ để gom những field tình cờ trùng tên nhưng khác ngữ nghĩa.

### 4.3. Union: đặt tên cho nhóm kết quả

Union biểu diễn một giá trị có thể thuộc một trong nhiều object type. Tên nên mô tả nhóm kết quả hoặc vai trò chung:

~~~graphql
union CatalogSearchResult = Book | Author | Article

type Query {
    searchCatalog(keyword: String!): [CatalogSearchResult!]!
}
~~~

`CatalogSearchResult` cho biết đây là một loại kết quả tìm kiếm trong catalog. Tên như `BookOrAuthorOrArticle` sẽ dài và khó mở rộng khi thêm một type mới.

### 4.4. Scalar tùy chỉnh: nêu rõ ý nghĩa dữ liệu

Custom scalar nên có tên mô tả định dạng hoặc ý nghĩa của giá trị:

~~~graphql
scalar DateTime
scalar EmailAddress
scalar ISBN
scalar Money
~~~

Không nên tạo scalar cho mọi kiểu Java. Ví dụ, nếu một mã định danh chỉ là chuỗi không có quy tắc chuyển đổi riêng, `String` hoặc `ID` có thể đã đủ. Chỉ dùng custom scalar khi ứng dụng có quy ước parse, validate và serialize rõ ràng.

Tên scalar cần thống nhất với hợp đồng dữ liệu. `DateTime` thường gợi ý giá trị ngày giờ có quy tắc biểu diễn; `EmailAddress` gợi ý chuỗi địa chỉ email được kiểm tra theo quy tắc riêng.

### 4.5. Input object: thêm hậu tố Input

Input object dành cho dữ liệu client gửi vào. Hậu tố `Input` giúp phân biệt nó với output object:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

input UpdateBookInput {
    id: ID!
    title: String
    publishedYear: Int
}
~~~

Tên `CreateBookInput` và `UpdateBookInput` thể hiện rõ mục đích của từng input. Không nên đặt cả hai là `BookRequest` hoặc `BookData` nếu tên đó không nói rõ thao tác nào đang được thực hiện.

### 4.6. Payload type: mô tả kết quả của mutation

Nếu mutation trả về nhiều thông tin liên quan đến kết quả thao tác, có thể dùng payload type:

~~~graphql
type CreateBookPayload {
    book: Book
    created: Boolean!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Hậu tố `Payload` giúp client nhận ra đây là kiểu kết quả của một hành động. Với mutation đơn giản chỉ trả về một object, có thể trả trực tiếp object đó; không cần tạo payload type nếu nó không đem lại ý nghĩa bổ sung.

## 5. Đặt tên field theo ngữ nghĩa nghiệp vụ

Field là phần client nhìn thấy thường xuyên nhất. Tên field nên trả lời được câu hỏi: "Giá trị này là gì?" hoặc "Hành động này thực hiện điều gì?"

Ví dụ:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
    publishedAt: DateTime
    coverImageUrl: String
}
~~~

Các field `title`, `author`, `publishedAt` và `coverImageUrl` mô tả dữ liệu miền nghiệp vụ. Chúng không tiết lộ server đang đọc từ database, cache hay một API bên ngoài.

Tránh các tên gắn với chi tiết triển khai:

~~~graphql
type Book {
    redisBookValue: String
    bookEntity: String
    getTitleFromDatabase: String
}
~~~

Nếu sau này server chuyển từ Redis sang database khác, tên field sẽ trở nên sai lệch dù hợp đồng dữ liệu vẫn không thay đổi. Tên schema nên ổn định theo ngữ nghĩa nghiệp vụ.

### 5.1. Tránh tên quá chung chung

Các tên như `data`, `value`, `result`, `info` hoặc `item` có thể hợp lệ nhưng thường không đủ ngữ cảnh:

~~~graphql
type Book {
    data: String
    info: String
    value: String
}
~~~

Người dùng schema không thể biết các field này đại diện cho dữ liệu gì. Nên đặt tên cụ thể:

~~~graphql
type Book {
    summary: String
    publisherName: String
    retailPrice: Money
}
~~~

Tên chung chung chỉ phù hợp khi type hoặc cấu trúc xung quanh đã cung cấp ngữ cảnh rõ ràng và tên đó thực sự là khái niệm dùng chung.

### 5.2. Dùng danh từ cho dữ liệu, động từ cho hành động

Field đọc dữ liệu thường dùng danh từ hoặc cụm danh từ:

- `book`
- `author`
- `publicationDate`
- `orderStatus`

Field biểu diễn hành động ở root mutation thường dùng động từ rõ ràng:

- `createBook`
- `updateBook`
- `publishBook`
- `cancelOrder`

Cách đặt tên này giúp phân biệt truy vấn dữ liệu và hành động làm thay đổi trạng thái.

### 5.3. Không lặp lại tên type trong mọi field

Trong object type `Book`, các field như `bookTitle`, `bookAuthor`, `bookPublishedAt` thường lặp lại thông tin đã có từ tên type.

Có thể viết ngắn gọn hơn:

~~~graphql
type Book {
    title: String!
    author: Author!
    publishedAt: DateTime
}
~~~

Tên field cần có đủ ngữ cảnh khi đứng trong type của nó, không cần lặp lại tên type nếu điều đó không làm rõ thêm ý nghĩa.

## 6. Đặt tên field ở root Query, Mutation và Subscription

Ba root operation type có mục đích khác nhau. Tên field nên thể hiện đúng hành vi mà client thực hiện.

### 6.1. Query: tên tài nguyên hoặc hành động tìm kiếm

Với truy vấn một đối tượng, dùng danh từ số ít:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Với danh sách, dùng danh từ số nhiều:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Khi thao tác có ngữ nghĩa tìm kiếm riêng, tên bắt đầu bằng động từ tìm kiếm có thể phù hợp:

~~~graphql
type Query {
    searchBooks(keyword: String!): [Book!]!
}
~~~

Không cần thêm tiền tố `get` cho mọi Query. Field `book` đã thể hiện rõ client đang yêu cầu một cuốn sách. Chỉ dùng `get` khi nó là một phần của ngôn ngữ nghiệp vụ có chủ đích và được áp dụng nhất quán.

### 6.2. Mutation: động từ hành động + đối tượng

Mutation thay đổi dữ liệu nên tên thường bắt đầu bằng động từ:

~~~graphql
type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
    updateBook(input: UpdateBookInput!): Book!
    publishBook(id: ID!): Book!
    archiveBook(id: ID!): Book!
}
~~~

Tên mutation nên mô tả hành động nghiệp vụ cụ thể. `saveBook` có thể quá chung vì không cho biết thao tác tạo mới, cập nhật hay lưu nháp. `manageBook` cũng không nói rõ trạng thái nào sẽ thay đổi.

Khi hành động có quy tắc riêng, hãy dùng động từ phù hợp với nghiệp vụ, chẳng hạn `approveOrder`, `rejectOrder` hoặc `shipOrder`.

### 6.3. Subscription: đặt tên cho sự kiện

Subscription thường mô tả sự kiện mà client muốn theo dõi:

~~~graphql
type Subscription {
    bookAdded: Book!
    bookPublished: Book!
    orderStatusChanged(orderId: ID!): Order!
}
~~~

Các tên `bookAdded`, `bookPublished` và `orderStatusChanged` cho biết loại sự kiện hoặc thay đổi mà client quan tâm. Chọn cách đặt tên nhất quán giữa các subscription trong cùng miền nghiệp vụ.

Nếu subscription phát ra một object biểu diễn sự kiện thay vì chính object nghiệp vụ, hãy đặt tên type theo sự kiện:

~~~graphql
type BookStatusChangedEvent {
    bookId: ID!
    previousStatus: BookStatus!
    currentStatus: BookStatus!
    occurredAt: DateTime!
}

type Subscription {
    bookStatusChanged(bookId: ID!): BookStatusChangedEvent!
}
~~~

## 7. Đặt tên argument dễ hiểu và nhất quán

Argument là đầu vào của từng field. Tên argument cũng dùng lowerCamelCase và nên mô tả giá trị được truyền vào.

~~~graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

`id` là tên phổ biến cho định danh của chính đối tượng đang truy vấn. `authorId` cho biết định danh thuộc về tác giả. Khi một field có nhiều định danh, tên đầy đủ giúp tránh nhầm lẫn.

### 7.1. Dùng tên thống nhất cho filter, sort và phân trang

Nếu nhiều Query hỗ trợ lọc và sắp xếp, hãy thống nhất tên argument:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

enum SortDirection {
    ASC
    DESC
}

input BookSort {
    field: BookSortField!
    direction: SortDirection! = ASC
}

enum BookSortField {
    TITLE
    PUBLISHED_AT
}

type Query {
    books(
        filter: BookFilter
        sort: BookSort
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}
~~~

Các tên `filter`, `sort`, `page` và `size` nên được dùng nhất quán ở những field có cùng quy ước. Nếu API dùng cursor pagination, có thể chọn cặp `first`/`after` hoặc `last`/`before` theo một quy ước nhất quán.

Không nên dùng `limit` ở một Query, `pageSize` ở Query khác và `count` ở Query thứ ba nếu chúng đều mang cùng ý nghĩa mà không có lý do nghiệp vụ.

### 7.2. Tránh viết tắt khó hiểu

Tên argument như `authId`, `pubDt` hoặc `usrCd` có thể ngắn nhưng khiến client phải tra cứu tài liệu. Nên dùng `authorId`, `publishedAt` và `userCode` nếu đó là thuật ngữ miền nghiệp vụ.

Một số viết tắt phổ biến như `id`, `url` hoặc `isbn` có thể được giữ nguyên nếu nhóm phát triển và người dùng API đều hiểu rõ. Nguyên tắc là dùng một cách viết nhất quán, không tự tạo nhiều biến thể chữ hoa chữ thường.

## 8. Đặt tên cho Boolean, trạng thái và thời điểm

Tên field cần gợi ý đúng loại giá trị mà nó trả về.

### 8.1. Boolean: dùng tiền tố thể hiện câu hỏi

Boolean thường có thể được đọc như một câu hỏi có/không:

~~~graphql
type Book {
    isPublished: Boolean!
    hasCoverImage: Boolean!
    canBeBorrowed: Boolean!
}
~~~

Các tiền tố phổ biến:

- `is`: trạng thái, ví dụ `isPublished`.
- `has`: sự tồn tại hoặc sở hữu, ví dụ `hasCoverImage`.
- `can`: khả năng hoặc quyền được thực hiện, ví dụ `canBeBorrowed`.

Không nên dùng tên `published` cho một Boolean nếu client dễ nhầm nó với thời điểm xuất bản. Nếu field trả về ngày giờ, hãy dùng `publishedAt`.

### 8.2. Phân biệt Boolean với enum trạng thái

Nếu đối tượng có nhiều trạng thái, Boolean có thể không đủ diễn đạt:

~~~graphql
type Order {
    isCompleted: Boolean!
}
~~~

Nếu đơn hàng có các trạng thái chờ thanh toán, đã thanh toán, đang giao và đã giao, enum sẽ thể hiện rõ hơn:

~~~graphql
enum OrderStatus {
    PENDING_PAYMENT
    PAID
    SHIPPING
    DELIVERED
    CANCELLED
}

type Order {
    status: OrderStatus!
}
~~~

Tên `status` có ngữ cảnh rõ trong type `Order`. Nếu một type chứa nhiều loại trạng thái khác nhau, nên đặt tên cụ thể hơn, chẳng hạn `paymentStatus` và `shippingStatus`.

### 8.3. Thời điểm và ngày tháng

Dùng hậu tố có ý nghĩa rõ ràng cho field thời gian:

- `createdAt`: thời điểm tạo.
- `updatedAt`: thời điểm cập nhật gần nhất.
- `publishedAt`: thời điểm xuất bản.
- `expiresAt`: thời điểm hết hạn.
- `dueDate`: ngày đến hạn nếu chỉ mang ý nghĩa ngày.

Phân biệt ngày lịch với thời điểm cụ thể. `dueDate` và `dueAt` không nên được dùng thay thế nhau nếu hợp đồng dữ liệu của chúng khác nhau.

## 9. Đặt tên enum và giá trị enum

Enum type dùng PascalCase, giá trị dùng UPPER_SNAKE_CASE:

~~~graphql
enum PaymentStatus {
    PENDING
    AUTHORIZED
    CAPTURED
    REFUNDED
    FAILED
}
~~~

Giá trị enum nên là các trạng thái hoặc lựa chọn có ý nghĩa rõ ràng trong miền nghiệp vụ.

Tránh tên quá chung hoặc phụ thuộc vào thứ tự:

~~~graphql
enum Status {
    VALUE_1
    VALUE_2
    OTHER
}
~~~

`VALUE_1` và `VALUE_2` không nói lên ý nghĩa nghiệp vụ. Nếu trạng thái là thanh toán, hãy đặt tên theo trạng thái thanh toán.

Với giá trị đại diện cho trường hợp khác, chỉ dùng `OTHER` khi nghiệp vụ thực sự có khái niệm "khác" và client có thể xử lý nó. Đừng dùng `UNKNOWN` để thay thế một giá trị chưa được xác định nếu server có thể biểu diễn trạng thái chưa biết bằng nullable hoặc một trạng thái riêng có ý nghĩa.

Tên enum value cũng là hợp đồng. Khi client dùng một enum value trong variables, đổi tên hoặc xóa giá trị cũ có thể làm request không hợp lệ.

## 10. Mô tả schema bằng description

Tên tốt là điều cần thiết, nhưng một số field vẫn cần giải thích rõ phạm vi và quy tắc. GraphQL hỗ trợ description bằng chuỗi đặt trước định nghĩa type, field, argument hoặc enum value.

~~~graphql
"""
A book available in the catalog.
"""
type Book {
    """Stable identifier of this book."""
    id: ID!

    """The title displayed to readers."""
    title: String!

    """
    The date when the book was first published.
    The value is null when the publication date is unknown.
    """
    publishedAt: DateTime
}
~~~

Description giúp IDE và công cụ introspection hiển thị tài liệu ngay cạnh tên field. Đây là nơi thích hợp để giải thích:

- Đơn vị đo hoặc định dạng giá trị.
- Ý nghĩa của nullable.
- Quy tắc lọc, sắp xếp và phân trang.
- Điều kiện nghiệp vụ của mutation.
- Phạm vi quyền truy cập hoặc giới hạn sử dụng nếu client cần biết.

Không nên dùng description để bù đắp cho một tên quá mơ hồ. Hãy chọn tên đủ rõ trước, rồi dùng description cho những chi tiết không thể thể hiện gọn trong tên.

Comment bắt đầu bằng dấu # trong SDL là ghi chú cho người đọc source. Nếu muốn tài liệu xuất hiện trong introspection và công cụ GraphQL, hãy dùng description string.

## 11. Một schema ví dụ với naming nhất quán

Ví dụ sau kết hợp các quy tắc đã học trong một miền catalog sách:

~~~graphql
scalar DateTime

"""
Một cuốn sách có trong danh mục.
"""
type Book {
    """Mã định danh ổn định của cuốn sách."""
    id: ID!

    """Tiêu đề hiển thị cho độc giả."""
    title: String!

    """Tác giả của cuốn sách."""
    author: Author!

    """Ngày xuất bản, nếu đã biết."""
    publishedAt: DateTime

    """Trạng thái hiện tại trong vòng đời cuốn sách."""
    status: BookStatus!
}

"""
Một người viết sách.
"""
type Author {
    id: ID!
    fullName: String!
    books: [Book!]!
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

enum BookSortField {
    TITLE
    PUBLISHED_AT
}

enum SortDirection {
    ASC
    DESC
}

input BookSort {
    field: BookSortField!
    direction: SortDirection! = ASC
}

input CreateBookInput {
    title: String!
    authorId: ID!
    publishedAt: DateTime
}

type CreateBookPayload {
    book: Book!
}

type Query {
    book(id: ID!): Book
    books(
        filter: BookFilter
        sort: BookSort
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
    publishBook(id: ID!): Book!
}

type Subscription {
    bookPublished: Book!
}
~~~

Có thể nhận ra một số quy ước:

- Type dùng PascalCase và danh từ số ít.
- Field dùng lowerCamelCase.
- Field danh sách dùng danh từ số nhiều.
- Enum value dùng UPPER_SNAKE_CASE.
- Input và payload có hậu tố thể hiện vai trò.
- Query field mô tả tài nguyên cần đọc.
- Mutation field bắt đầu bằng động từ hành động.
- Subscription field mô tả sự kiện.
- Description giải thích ý nghĩa của các field quan trọng.

Schema ví dụ tập trung vào naming. Khi triển khai thật, cần bảo đảm có resolver cho các field nghiệp vụ và cấu hình scalar tương ứng với các custom scalar đã khai báo.

## 12. Những cách đặt tên nên tránh

| Cách đặt tên | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| `getBookById` | Tiền tố get dư thừa với Query | `book(id: ID!)` |
| `Books` làm object type | Tên số nhiều gây nhầm với danh sách | `Book` |
| `book_title` | Trộn snake_case với quy ước camelCase | `title` |
| `bookTitle` bên trong type Book | Lặp tên type | `title` |
| `usrId` | Viết tắt khó hiểu | `userId` |
| `data` hoặc `value` | Không thể hiện ngữ nghĩa | Tên miền cụ thể |
| `saveBook` | Không rõ tạo mới hay cập nhật | `createBook` hoặc `updateBook` |
| `Status` cho mọi trạng thái | Không rõ trạng thái của đối tượng nào | `BookStatus`, `OrderStatus` |
| `BookDTO` | Tiết lộ cách tổ chức lớp phía server | `Book` |
| `__book` | Dùng tiền tố dành cho introspection | Chọn tên không bắt đầu bằng `__` |

Một schema có nhiều tên gần giống nhau cũng gây khó khăn:

~~~graphql
type Query {
    book(id: ID!): Book
    getBook(id: ID!): Book
    findBook(id: ID!): Book
    fetchBook(id: ID!): Book
}
~~~

Bốn field trên có thể cùng thực hiện một truy vấn. Client không biết nên chọn field nào. Hãy thống nhất một tên đại diện cho một khái niệm, chỉ tạo field riêng khi chúng có ngữ nghĩa hoặc hành vi thực sự khác nhau.

## 13. Đổi tên schema và khả năng tương thích

Vì client tham chiếu trực tiếp tên trong schema, đổi tên là một thay đổi có thể phá vỡ tương thích.

Ví dụ, nếu đang có field:

~~~graphql
type Book {
    name: String!
}
~~~

và muốn đổi thành `title`, client hiện tại vẫn có thể đang gửi:

~~~graphql
query {
    book(id: "book-42") {
        name
    }
}
~~~

Xóa hoặc đổi tên `name` ngay lập tức sẽ làm operation cũ không còn hợp lệ.

Một cách chuyển đổi an toàn hơn là thêm field mới và đánh dấu field cũ deprecated:

~~~graphql
type Book {
    title: String!

    name: String @deprecated(reason: "Use title instead")
}
~~~

Sau đó:

1. Thông báo field mới cho các nhóm client.
2. Cập nhật client để dùng field mới.
3. Theo dõi việc sử dụng field cũ nếu hệ thống có observability phù hợp.
4. Chỉ loại bỏ field cũ khi đã xác nhận không còn client phụ thuộc và quy trình phát hành cho phép.

Quy trình tương tự cần áp dụng khi đổi tên argument, type hoặc enum value. Description và deprecation reason nên nói rõ tên mới để người dùng schema biết cách chuyển đổi.

Không phải mọi thay đổi tên đều có thể dùng alias ở server để duy trì tương thích. Alias trong operation là tên khóa response do client chọn, không thay thế cho việc field cũ biến mất khỏi schema.

## 14. Checklist trước khi công bố schema

Trước khi đưa schema vào sử dụng, hãy rà soát:

- Tên có đúng cú pháp GraphQL và không bắt đầu bằng tiền tố dành riêng `__`?
- Type có dùng PascalCase và mô tả đúng khái niệm nghiệp vụ?
- Object type có dùng danh từ số ít, field danh sách có tên số nhiều?
- Field và argument có dùng lowerCamelCase nhất quán?
- Enum type và enum value có đúng quy ước?
- Input và payload có tên thể hiện đúng vai trò?
- Tên Boolean có gợi ý rõ câu hỏi đúng/sai?
- Tên thời gian phân biệt ngày lịch với thời điểm cụ thể?
- Có field nào tên quá chung, viết tắt khó hiểu hoặc tiết lộ chi tiết triển khai?
- Các Query, Mutation và Subscription có tên thể hiện đúng hành vi?
- Những field hoặc enum value cũ có được deprecate và có lý do chuyển đổi rõ ràng?
- Description có giải thích những quy tắc mà tên không thể hiện hết?

## 15. Tổng kết

Naming trong GraphQL là một phần của hợp đồng API. Tên type nên thể hiện khái niệm miền nghiệp vụ; field và argument cần rõ ngữ nghĩa; enum value cần nhất quán; input và payload nên có hậu tố giúp người đọc nhận ra vai trò. Các quy ước PascalCase, lowerCamelCase và UPPER_SNAKE_CASE tạo nên schema dễ đọc và dễ khám phá.

Khi thiết kế tên, hãy ưu tiên ý nghĩa mà client cần hiểu, tránh gắn schema với chi tiết database hoặc implementation. Hãy bổ sung description cho các quy tắc quan trọng và dùng deprecation khi cần thay đổi tên đã công bố. Một schema có naming rõ ràng sẽ giúp client viết operation chính xác, nhóm phát triển trao đổi thống nhất và API tiến hóa có kiểm soát.

