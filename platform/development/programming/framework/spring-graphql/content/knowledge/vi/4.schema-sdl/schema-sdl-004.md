# `type Subscription`

## 1. Subscription trong GraphQL là gì?

GraphQL định nghĩa ba loại operation ở cấp schema: `Query` để đọc dữ liệu, `Mutation` để thay đổi dữ liệu và `Subscription` để nhận các cập nhật khi sự kiện xảy ra. Trong đó, `Subscription` mô tả những luồng sự kiện mà client có thể đăng ký theo dõi.

Một query thông thường tạo ra một kết quả cho một lần thực thi. Một subscription tạo ra một luồng kết quả: mỗi khi nguồn sự kiện phát ra một sự kiện mới, server thực thi selection set của subscription và gửi một response tương ứng cho client. Vì vậy, client có thể nhận thay đổi mà không phải liên tục gửi query để hỏi server.

Trong Schema Definition Language (SDL), root type cho subscription thường được khai báo bằng:

```graphql
type Subscription {
    bookChanged: Book
}
```

`Subscription` là một object type. Field `bookChanged` là một khả năng đăng ký nhận sự kiện được công bố trong schema. Khai báo SDL chỉ mô tả tên field, đối số và kiểu dữ liệu trả về; nó chưa tạo ra nguồn sự kiện, chưa quyết định cách xác thực người đăng ký và cũng chưa thiết lập kết nối mạng.

Với Spring for GraphQL, field này thường được ánh xạ đến một phương thức `@SubscriptionMapping` trả về một publisher, chẳng hạn `Flux<T>`. Phần thực thi subscription và transport chịu trách nhiệm duy trì luồng response đến client.

## 2. Khai báo root type Subscription trong schema

### Quy ước tên root type

Theo quy ước mặc định của GraphQL, root operation type có tên `Query`, `Mutation` và `Subscription`. Nếu schema không khai báo rõ khối `schema`, GraphQL sử dụng các tên mặc định này khi chúng tồn tại và phù hợp với operation tương ứng.

Một schema có thể khai báo rõ các root type:

```graphql
schema {
    query: Query
    mutation: Mutation
    subscription: Subscription
}

type Query {
    book(id: ID!): Book
}

type Mutation {
    updateBookTitle(id: ID!, title: String!): Book!
}

type Subscription {
    bookChanged: BookChangeEvent!
}

type Book {
    id: ID!
    title: String!
}

type BookChangeEvent {
    bookId: ID!
    title: String!
}
```

Trong ví dụ trên, `query`, `mutation` và `subscription` ở khối `schema` là các tên operation root; `Query`, `Mutation` và `Subscription` là tên object type được dùng làm root. Query root là thành phần bắt buộc của một schema thực thi GraphQL. Mutation và subscription là tùy chọn nếu API không cung cấp hai loại operation này.

Nếu muốn dùng tên object type khác, cần khai báo ánh xạ rõ ràng:

```graphql
schema {
    query: Query
    subscription: LiveUpdates
}

type Query {
    health: String!
}

type LiveUpdates {
    systemNotice: String!
}
```

Khi đó `LiveUpdates` mới là root type cho subscription. Nếu không có khai báo `schema` tùy chỉnh, đừng tự ý đổi tên `Subscription` rồi kỳ vọng GraphQL tự nhận diện type mới.

### Field trong Subscription là gì?

Mỗi field của root type `Subscription` đại diện cho một loại sự kiện mà client có thể đăng ký. Field có thể nhận arguments để lọc hoặc xác định phạm vi theo dõi, và có thể trả về scalar, enum, object hoặc các kiểu output hợp lệ khác.

Ví dụ:

```graphql
type Subscription {
    systemNotice: String!
    bookChanged(bookId: ID!): BookChangeEvent!
    orderStatusChanged(orderId: ID!): OrderStatusEvent!
}
```

- `systemNotice` cung cấp thông báo hệ thống.
- `bookChanged` cho phép theo dõi thay đổi của một quyển sách cụ thể.
- `orderStatusChanged` cho phép theo dõi trạng thái của một đơn hàng.

Object type phải có ít nhất một field. Vì vậy, khi đã khai báo `type Subscription`, cần định nghĩa ít nhất một field có ý nghĩa. Nếu ứng dụng chưa có nhu cầu nhận sự kiện, có thể không khai báo subscription root type.

## 3. Thiết kế kiểu dữ liệu cho sự kiện

Một subscription có thể trả về trực tiếp đối tượng nghiệp vụ, ví dụ `Book!`. Tuy nhiên, khi client cần biết loại thay đổi, thời điểm phát sinh hoặc mã sự kiện, nên thiết kế một object type đại diện cho event payload.

Ví dụ:

```graphql
enum BookChangeKind {
    CREATED
    UPDATED
    DELETED
}

type BookChangeEvent {
    eventId: ID!
    bookId: ID!
    kind: BookChangeKind!
    occurredAt: String!
    book: Book
}

type Book {
    id: ID!
    title: String!
    authorName: String!
}

type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

Payload `BookChangeEvent` mang theo thông tin chung của sự kiện. Field `book` có thể là `null`, chẳng hạn khi sách đã bị xóa và server không còn đối tượng hiện tại để trả về. Trong khi đó, `eventId`, `bookId`, `kind` và `occurredAt` được khai báo non-null vì ví dụ giả định mọi sự kiện hợp lệ đều phải có các thông tin này.

Trong ví dụ, `occurredAt` dùng `String` với quy ước biểu diễn thời gian ISO-8601. Nếu muốn schema thể hiện kiểu thời gian rõ ràng hơn, có thể định nghĩa custom scalar như `DateTime`, nhưng server phải đăng ký scalar tương ứng và quy định định dạng serialize/parse. Chỉ khai báo `scalar DateTime` trong SDL không tự tạo ra bộ chuyển đổi cho Java.

### Vì sao nên có event payload riêng?

Payload riêng giúp API thể hiện ý nghĩa của sự kiện thay vì chỉ gửi một bản ghi dữ liệu không có ngữ cảnh. Nó cũng giúp schema mở rộng theo nhu cầu mà không phải thay đổi kiểu dữ liệu chính của entity.

Một event payload thường có thể bao gồm:

- `eventId`: mã định danh sự kiện, hữu ích cho log, đối soát hoặc xử lý trùng lặp.
- `kind`: loại thay đổi như `CREATED`, `UPDATED` hoặc `DELETED`.
- `occurredAt`: thời điểm sự kiện xảy ra theo quy ước thống nhất.
- `entityId`: mã đối tượng nghiệp vụ bị ảnh hưởng.
- `entity`: dữ liệu hiện tại hoặc snapshot tại thời điểm phát sinh sự kiện, nếu nghiệp vụ cho phép.
- `changedFields`: danh sách hoặc cấu trúc mô tả những thuộc tính đã thay đổi, nếu client thực sự cần.

Không nên đưa toàn bộ entity hoặc dữ liệu nội bộ vào payload theo mặc định. Chỉ công bố những field mà client cần và được phép xem. Payload càng ổn định thì việc thay đổi mô hình lưu trữ phía server càng ít ảnh hưởng đến các client đang subscribe.

## 4. Sử dụng arguments để xác định luồng sự kiện

Nếu mọi client đều nhận tất cả sự kiện, server có thể phải gửi lượng dữ liệu lớn và khiến việc phân quyền trở nên khó kiểm soát. Arguments giúp client đăng ký theo một phạm vi cụ thể.

Ví dụ đơn giản:

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

Client đăng ký theo dõi một quyển sách:

```graphql
subscription WatchBook($bookId: ID!) {
    bookChanged(bookId: $bookId) {
        eventId
        kind
        occurredAt
        book {
            id
            title
        }
    }
}
```

Variables gửi kèm operation:

```json
{
  "bookId": "book-42"
}
```

Arguments trong SDL dùng các input type hợp lệ. Nếu cần nhiều điều kiện lọc, có thể gom chúng vào một input object:

```graphql
input BookChangeFilter {
    bookId: ID
    authorId: ID
    kinds: [BookChangeKind!]
}

type Subscription {
    bookChanged(filter: BookChangeFilter!): BookChangeEvent!
}
```

`BookChangeFilter` là input type, vì vậy chỉ chứa scalar, enum, input object và danh sách các kiểu input phù hợp. Không thể dùng trực tiếp một object output như `Book` làm kiểu argument. Trong thiết kế thực tế, hãy cân nhắc liệu các bộ lọc có cần bắt buộc hay không và server xử lý trường hợp filter thiếu hoặc rỗng như thế nào.

Arguments chỉ mô tả điều kiện đăng ký. Server vẫn phải áp dụng filter ở nguồn sự kiện hoặc trong tầng xử lý trước khi phát event cho người đăng ký. Chỉ lọc ở client sau khi đã gửi toàn bộ sự kiện qua mạng không giảm được tải server và có thể làm lộ dữ liệu.

## 5. Quy tắc quan trọng của Subscription operation

Subscription operation có một quy tắc khác query thông thường: selection set ở cấp cao nhất phải chọn đúng một root field. Đây là yêu cầu để server xác định một nguồn sự kiện cho mỗi subscription operation.

Ví dụ hợp lệ:

```graphql
subscription WatchBook {
    bookChanged(bookId: "book-42") {
        eventId
        kind
    }
}
```

Ví dụ không hợp lệ vì có hai root field:

```graphql
subscription WatchEverything {
    bookChanged(bookId: "book-42") {
        eventId
    }
    systemNotice
}
```

Nếu client cần theo dõi hai loại sự kiện độc lập, hãy tạo hai subscription operation riêng. Có thể dùng cùng một kết nối WebSocket để quản lý nhiều operation đang hoạt động, tùy giao thức transport và giới hạn của server.

Các field lồng bên trong payload vẫn có thể được chọn tùy ý theo schema:

```graphql
subscription WatchBook {
    bookChanged(bookId: "book-42") {
        eventId
        kind
        book {
            id
            title
            authorName
        }
    }
}
```

Như vậy, quy tắc một field chỉ áp dụng cho root selection set của subscription operation, không giới hạn số field bên trong object payload.

## 6. Nullability và danh sách trong event payload

Các quy tắc nullable (`T`) và non-null (`T!`) trong SDL vẫn có hiệu lực đối với từng response được phát ra từ subscription.

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}

type BookChangeEvent {
    eventId: ID!
    book: Book
    tags: [String!]!
}
```

Ý nghĩa của các kiểu trong ví dụ:

| Khai báo | Ý nghĩa |
| --- | --- |
| `BookChangeEvent!` | Mỗi event payload không được là `null` |
| `Book` | Đối tượng sách có thể là `null` |
| `[String!]!` | Danh sách luôn có giá trị và từng phần tử trong danh sách không được là `null` |
| `[String]` | Danh sách có thể là `null`, từng phần tử cũng có thể là `null` |

Nếu một field non-null không thể được phân giải, lỗi có thể lan lên field cha gần nhất có thể nhận `null`. Với subscription, điều này xảy ra trong response của event tương ứng; cần thiết kế nullability theo dữ liệu thực tế của từng loại sự kiện. Ví dụ sự kiện xóa sách có thể không còn `book`, vì vậy khai báo `book: Book` hợp lý hơn `book: Book!` nếu payload vẫn phải được phát.

## 7. Mô tả schema và tiến hóa field Subscription

Có thể dùng description trong SDL để mô tả ý nghĩa của root type và field:

```graphql
"""Các luồng sự kiện liên quan đến thư viện."""
type Subscription {
    """Phát sự kiện khi một quyển sách thay đổi."""
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

Description giúp công cụ sinh tài liệu và người dùng schema hiểu được phạm vi sự kiện. Nội dung mô tả nên nói rõ ai có thể đăng ký, điều kiện lọc, ý nghĩa payload và các giới hạn nghiệp vụ quan trọng.

Khi cần thay thế một field subscription, có thể đánh dấu field cũ bằng `@deprecated`:

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
        @deprecated(reason: "Use catalogBookChanged instead")

    catalogBookChanged(bookId: ID!): BookChangeEvent!
}
```

Giữ field cũ trong một giai đoạn chuyển đổi giúp client có thời gian di chuyển. Trước khi xóa field, nên quan sát mức sử dụng và phối hợp lịch phát hành với các client đang hoạt động.

## 8. Từ SDL đến Spring for GraphQL

SDL định nghĩa hợp đồng. Spring for GraphQL cần một resolver để cung cấp publisher của các sự kiện tương ứng với field đã khai báo.

Với schema:

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

Một controller có thể ánh xạ field này bằng `@SubscriptionMapping`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class BookSubscriptionController {

    private final BookEventService bookEventService;

    public BookSubscriptionController(BookEventService bookEventService) {
        this.bookEventService = bookEventService;
    }

    @SubscriptionMapping
    public Flux<BookChangeEvent> bookChanged(@Argument String bookId) {
        return bookEventService.subscribeToBook(bookId);
    }
}
```

`@SubscriptionMapping` liên kết phương thức với field cùng tên trong root type `Subscription`. `@Argument` nhận giá trị `bookId` từ operation. `BookEventService` chịu trách nhiệm tạo publisher phát các event phù hợp; ví dụ này giả định service trả về `Flux<BookChangeEvent>`.

Một cách khác là dùng `@SchemaMapping(typeName = "Subscription", field = "bookChanged")`, nhưng `@SubscriptionMapping` thể hiện rõ ý định xử lý subscription và thường dễ đọc hơn.

Điểm cần phân biệt:

- SDL mô tả field và kiểu dữ liệu mà client được phép yêu cầu.
- `@SubscriptionMapping` ánh xạ field schema đến phương thức Java.
- `Flux` hoặc một `Publisher` cung cấp chuỗi giá trị theo thời gian.
- Event broker, message queue hoặc service nghiệp vụ là nơi tạo và phân phối sự kiện.
- Transport chuyển các response của subscription đến client.

Nếu SDL khai báo `bookChanged` nhưng không có resolver hoặc nguồn dữ liệu phù hợp, schema vẫn có thể được đọc nhưng subscription không hoạt động như mong đợi. Ngược lại, một phương thức Java không tự trở thành API công khai nếu không có field tương ứng trong schema và được cấu hình để ánh xạ.

## 9. Transport và vòng đời subscription

GraphQL SDL không quy định subscription phải dùng WebSocket, Server-Sent Events hay một cơ chế truyền tải cụ thể. GraphQL execution tạo ra luồng kết quả; ứng dụng cần một transport hỗ trợ truyền nhiều response trong suốt thời gian đăng ký.

Trong hệ sinh thái Spring for GraphQL, WebSocket là lựa chọn thường gặp cho subscription. Một số hệ thống có thể sử dụng transport streaming khác nếu framework và client cùng hỗ trợ. HTTP request-response thông thường chỉ trả một response rồi kết thúc, nên không thể mặc định rằng việc có endpoint `/graphql` qua Spring MVC đã đồng nghĩa subscription hoạt động.

Vòng đời khái quát:

1. Client gửi subscription operation và arguments đến transport.
2. Server xác thực người dùng, kiểm tra quyền đăng ký và tạo publisher tương ứng.
3. Nguồn sự kiện phát ra một event mới.
4. GraphQL thực thi selection set cho event đó và tạo response.
5. Transport gửi response đến client; quá trình lặp lại cho đến khi operation bị hủy, lỗi hoặc hoàn tất.

Khi client ngắt kết nối hoặc hủy operation, server cần giải phóng subscription và tài nguyên liên quan. Với nguồn sự kiện dùng chung, việc hủy một client không được làm dừng luồng của các client khác. Cần thiết kế cơ chế cleanup, backpressure và giới hạn số đăng ký đồng thời phù hợp với năng lực hệ thống.

## 10. Bảo mật và độ tin cậy của event stream

Subscription có vòng đời dài hơn một request thông thường. Việc kiểm tra quyền ở thời điểm kết nối là cần thiết nhưng có thể chưa đủ nếu quyền truy cập hoặc trạng thái nghiệp vụ thay đổi trong lúc client đang subscribe.

Một số nguyên tắc thiết kế:

- Xác thực người dùng khi thiết lập operation hoặc kết nối theo cơ chế của transport.
- Kiểm tra quyền xem đối tượng được truyền qua arguments, chẳng hạn `bookId` hoặc `orderId`.
- Lọc sự kiện ở phía server theo tenant, người sở hữu và phạm vi dữ liệu được phép truy cập.
- Xem xét lại quyền khi phát event nếu chính sách yêu cầu quyền phải còn hiệu lực trong toàn bộ vòng đời subscription.
- Giới hạn số subscription, tần suất event và kích thước payload theo người dùng hoặc tenant.
- Không ghi token, thông tin cá nhân hoặc payload nhạy cảm vào log không được bảo vệ.

Một kết nối streaming bị gián đoạn có thể làm client bỏ lỡ sự kiện. GraphQL subscription tự nó không bảo đảm lưu trữ event, gửi lại sau reconnect, thứ tự toàn cục hay xử lý đúng một lần. Nếu nghiệp vụ cần khả năng tiếp tục từ vị trí cũ, hãy thiết kế event ID hoặc cursor và cơ chế replay ở tầng event source. Client cũng nên có cách đồng bộ lại trạng thái hiện tại bằng query khi cần.

## 11. Kiểm thử schema và subscription

Nên kiểm thử cả hợp đồng SDL, resolver và transport vì mỗi lớp có thể gặp lỗi khác nhau.

**Kiểm thử schema:** xác nhận root type subscription được khai báo đúng, field có kiểu output hợp lệ, arguments dùng input type và các type tham chiếu tồn tại. Nếu schema dùng tên root tùy chỉnh, kiểm tra khối `schema` đã ánh xạ đúng.

**Kiểm thử mapping:** xác nhận field SDL được ánh xạ đến `@SubscriptionMapping`, arguments được truyền đúng và publisher phát ra đúng payload. Kiểm tra cả trường hợp không có event, publisher kết thúc và publisher phát lỗi.

**Kiểm thử quy tắc operation:** xác nhận subscription operation chỉ có một root field. Query có nhiều root field có thể hợp lệ, nhưng subscription có nhiều root field phải bị từ chối theo quy tắc validation.

**Kiểm thử quyền và vòng đời:** thử người dùng không có quyền, filter không hợp lệ, hủy operation, ngắt kết nối và nhiều client đăng ký đồng thời. Xác nhận việc hủy một subscription không ảnh hưởng đến subscription khác.

**Kiểm thử transport:** dùng đúng giao thức mà môi trường production triển khai. Một bài kiểm thử chỉ gọi trực tiếp publisher không chứng minh WebSocket hoặc streaming endpoint đã cấu hình chính xác.

## 12. Lỗi thiết kế thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Có `type Subscription` nhưng không khai báo root trong schema tùy chỉnh | GraphQL không nhận type đó làm subscription root | Bổ sung `subscription: Subscription` trong khối `schema` |
| Đổi tên root type mà không khai báo schema mapping | Root operation không được ánh xạ theo tên mặc định | Dùng tên `Subscription` hoặc khai báo root type tường minh |
| Subscription operation có nhiều root field | Operation không hợp lệ | Tách thành các subscription operation riêng |
| Field không có filter trong khi sự kiện có phạm vi lớn | Server có thể phát dữ liệu không cần thiết cho nhiều client | Thiết kế arguments và lọc ở server |
| Payload chỉ trả entity mà không có ngữ cảnh sự kiện | Client khó phân biệt tạo mới, cập nhật và xóa | Dùng event payload riêng khi nghiệp vụ cần metadata |
| Khai báo `book: Book!` dù sự kiện xóa không có entity | Non-null propagation có thể làm mất phần dữ liệu mong muốn trong response | Chọn nullability theo từng loại event hoặc dùng snapshot phù hợp |
| Chỉ kiểm tra quyền lúc mở kết nối | Người dùng có thể tiếp tục nhận event sau khi quyền thay đổi | Đánh giá lại quyền theo chính sách bảo mật của hệ thống |
| Cho rằng GraphQL tự replay event sau reconnect | Client có thể bỏ lỡ cập nhật | Bổ sung cursor, replay và cơ chế đồng bộ trạng thái nếu cần |
| Chỉ cấu hình HTTP request-response | Client không nhận được chuỗi response subscription | Cấu hình transport streaming tương thích ở server và client |

## 13. Checklist thiết kế `type Subscription`

- [ ] Schema có root subscription type và khai báo mapping tường minh nếu dùng tên tùy chỉnh.
- [ ] Mỗi field thể hiện một luồng sự kiện có ý nghĩa rõ ràng.
- [ ] Arguments dùng input type hợp lệ và hỗ trợ lọc theo phạm vi nghiệp vụ.
- [ ] Payload có đủ metadata cần thiết nhưng không công bố dữ liệu dư thừa.
- [ ] Nullability phù hợp với mọi loại event, bao gồm cả trường hợp xóa đối tượng.
- [ ] Client operation chỉ chọn đúng một root field.
- [ ] Spring for GraphQL có resolver trả về publisher tương ứng với field SDL.
- [ ] Transport streaming được cấu hình và kiểm thử với client thực tế.
- [ ] Có xác thực, phân quyền, giới hạn tài nguyên và cleanup khi hủy subscription.
- [ ] Có chiến lược reconnect, replay hoặc đồng bộ lại trạng thái nếu nghiệp vụ yêu cầu.

## Kết luận

`type Subscription` là root object type mô tả những luồng sự kiện mà GraphQL API công bố cho client. Mỗi field biểu diễn một loại đăng ký, có thể nhận arguments để xác định phạm vi và trả về một payload có cấu trúc. Quy tắc quan trọng của subscription operation là chỉ có một root field trong selection set.

Trong Spring for GraphQL, schema SDL cần được kết nối với resolver `@SubscriptionMapping` trả về publisher, cùng một transport có khả năng truyền nhiều response. Thiết kế tốt cần tính đến payload, nullability, filter phía server, quyền truy cập trong suốt vòng đời, cleanup và khả năng khôi phục sau khi mất kết nối. Khi những phần này được thiết kế đồng bộ, Subscription trở thành cơ chế hữu ích để xây dựng chức năng cập nhật theo sự kiện trong GraphQL API.
