# Ẩn metadata nhạy cảm trong GraphQL

GraphQL có cơ chế **introspection** cho phép client hỏi server về schema đang được công bố: các type, field, argument, directive và mô tả của chúng. Cơ chế này rất hữu ích cho IDE, tài liệu API và sinh mã client. Tuy nhiên, nếu schema chứa tên field nội bộ, mô tả quy trình riêng tư hoặc metadata chỉ dành cho đội vận hành, introspection có thể làm lộ những thông tin đó.

Ẩn metadata nhạy cảm cần được xử lý ở hai lớp. Trước hết, thiết kế schema và descriptions sao cho không chứa bí mật hoặc thông tin nội bộ không cần công bố. Sau đó, lựa chọn chính sách introspection phù hợp với môi trường và đối tượng sử dụng. Việc tắt introspection chỉ giảm khả năng khám phá schema; nó không thay thế xác thực và phân quyền cho dữ liệu.

## Introspection có thể tiết lộ những gì?

GraphQL cung cấp các meta-field để khám phá schema. Hai field thường gặp là:

- `__schema`: trả về thông tin tổng quan về schema, bao gồm query root, mutation root, subscription root, các type và directive được công bố.
- `__type(name: "...")`: tra cứu chi tiết một type theo tên, gồm field, argument, kiểu dữ liệu, enum value và mô tả nếu có.

Ví dụ truy vấn các type và field:

```graphql
query InspectSchema {
  __schema {
    queryType {
      name
    }
    types {
      name
      description
      fields {
        name
        description
      }
    }
  }
}
```

Client cũng có thể tra cứu riêng một type:

```graphql
query InspectAccount {
  __type(name: "Account") {
    name
    description
    fields {
      name
      description
      args {
        name
        description
      }
    }
  }
}
```

Introspection không trả về dữ liệu runtime của mọi người dùng hay nội dung cơ sở dữ liệu. Nó mô tả hợp đồng API mà server công bố. Dù vậy, cấu trúc schema có thể tiết lộ thông tin hữu ích cho người đang tìm hiểu bề mặt tấn công, ví dụ:

- Tên type và field liên quan tới chức năng quản trị, thanh toán, kiểm duyệt hoặc vận hành nội bộ.
- Các argument cho thấy cách lọc dữ liệu, trạng thái nghiệp vụ hoặc tham số truy vấn.
- Enum values tiết lộ những trạng thái nội bộ của hệ thống.
- Descriptions giải thích quy trình, tên hệ thống tích hợp, mã lỗi hoặc giới hạn vận hành.
- Directive và lý do deprecation cho biết metadata về vòng đời API.
- URL trong directive như `@specifiedBy` có thể chỉ tới tài liệu hoặc tài nguyên bên ngoài.

Introspection không tự tạo ra lỗ hổng phân quyền. Rủi ro xuất hiện khi metadata công bố nhiều hơn mức cần thiết hoặc khi server dựa vào việc người dùng không biết tên field để bảo vệ dữ liệu.

## Descriptions trong SDL cũng là metadata

GraphQL SDL hỗ trợ descriptions bằng chuỗi nhiều dòng đặt trước type, field, argument hoặc enum value. Các descriptions này có thể được truy xuất qua introspection:

```graphql
"""Thông tin tài khoản hiển thị cho người dùng."""
type Account {
  id: ID!
  displayName: String!

  """Ghi chú nội bộ của nhóm vận hành."""
  internalReviewNote: String
}
```

Description là một phần của schema và có thể được công bố cho client. Vì vậy, không nên đặt trong descriptions:

- Thông tin đăng nhập, token, khóa API, mật khẩu hoặc chuỗi kết nối.
- Tên host, địa chỉ nội bộ, tên bảng hoặc cấu trúc hạ tầng không cần công bố.
- Hướng dẫn khai thác, ghi chú kiểm thử hoặc quy trình xử lý sự cố nội bộ.
- Thông tin cá nhân, dữ liệu khách hàng hoặc nội dung bí mật của tổ chức.

Comment bắt đầu bằng `#` trong file SDL không trở thành description của schema theo cách chuỗi mô tả `"""..."""` thực hiện. Tuy nhiên, comment vẫn nằm trong mã nguồn và có thể bị lộ qua repository, artifact hoặc hệ thống build; không dùng comment để lưu bí mật.

## Directive có ẩn field khỏi introspection không?

Không. Directive mô tả metadata hoặc điều khiển một phần hành vi GraphQL theo vị trí và quy tắc đã định nghĩa. Các directive phổ biến có ý nghĩa khác nhau:

| Directive | Tác dụng | Có tự ẩn field khỏi schema không? |
| --- | --- | --- |
| `@skip(if: ...)` | Bỏ qua field trong một lần thực thi nếu điều kiện đúng. | Không. |
| `@include(if: ...)` | Bao gồm field trong một lần thực thi nếu điều kiện đúng. | Không. |
| `@deprecated(reason: ...)` | Đánh dấu field hoặc enum value đã lỗi thời và có thể cung cấp lý do. | Không. Lý do deprecation có thể được introspection đọc. |
| `@specifiedBy(url: ...)` | Cung cấp URL mô tả quy ước của custom scalar. | Không. URL có thể được công bố. |
| Custom directive | Đưa metadata hoặc quy ước riêng vào schema. | Không, trừ khi ứng dụng có cơ chế riêng xử lý visibility. |

Ví dụ `@skip` chỉ điều khiển một response cụ thể:

```graphql
query AccountView($showEmail: Boolean!) {
  account(id: "acc-100") {
    id
    displayName
    email @include(if: $showEmail)
  }
}
```

Field `email` vẫn tồn tại trong schema và vẫn xuất hiện khi introspection liệt kê field của `Account`. Directive chỉ quyết định có resolve field trong operation cụ thể hay không.

`@deprecated` cũng không phải công cụ bảo mật:

```graphql
type Account {
  id: ID!
  legacyCode: String @deprecated(reason: "Thay bằng accountReference")
  accountReference: String!
}
```

Client có thể xem `legacyCode` và deprecation reason thông qua introspection. Hãy viết lý do ngắn gọn, hướng dẫn chuyển đổi đủ dùng cho client và không chứa ghi chú nội bộ.

## Custom directive đánh dấu dữ liệu nhạy cảm

Ứng dụng có thể định nghĩa directive riêng để gắn nhãn field nhạy cảm:

```graphql
directive @sensitive on FIELD_DEFINITION

type Account {
  id: ID!
  displayName: String!
  internalReviewNote: String @sensitive
}
```

Directive `@sensitive` ở ví dụ này chỉ là metadata do schema khai báo. GraphQL Java không tự hiểu rằng field có directive này phải bị ẩn, phải yêu cầu quyền admin hoặc không được introspection. Muốn áp dụng quy tắc, ứng dụng phải viết cơ chế xử lý directive, ví dụ kiểm tra metadata khi xây dựng schema hoặc kiểm tra quyền trong resolver.

Định nghĩa directive cùng các metadata như tên, argument và vị trí được phép sử dụng có thể được đọc qua introspection. GraphQL introspection chuẩn không cung cấp một cách tổng quát để liệt kê mọi vị trí directive tùy chỉnh đã được áp dụng. Dù vậy, đánh dấu field là sensitive không làm tên field biến mất khỏi schema.

Đối với quyền đọc dữ liệu, một field resolver có thể kiểm tra quyền trước khi trả giá trị:

```java
@SchemaMapping(typeName = "Account", field = "internalReviewNote")
public String internalReviewNote(Account account) {
    authorizationService.checkCanReadInternalNote(account.getId());
    return accountService.getInternalReviewNote(account.getId());
}
```

Ví dụ này bảo vệ giá trị field theo người dùng hiện tại. Tên `internalReviewNote` vẫn có thể được nhìn thấy trong schema nếu introspection được bật; người gọi cũng có thể thử truy vấn field đã biết tên, nhưng resolver phải từ chối nếu họ không có quyền.

## Chính sách introspection theo môi trường

Introspection rất hữu ích trong quá trình phát triển:

- GraphiQL hoặc IDE có thể tải schema để gợi ý field và argument.
- Công cụ sinh client có thể tạo type an toàn từ schema.
- Đội ngũ tích hợp có thể đọc tài liệu và kiểm tra thay đổi API.
- Kiểm thử hợp đồng có thể xác minh schema được công bố.

Trong production, tổ chức cần quyết định schema có được công khai cho mọi client hay chỉ cho công cụ và người dùng nội bộ. Không có một lựa chọn phù hợp cho mọi API. Một API công khai có thể chủ động công bố schema; API nghiệp vụ nội bộ có thể giới hạn introspection theo chính sách vận hành.

Một ma trận chính sách tham khảo:

| Môi trường | Chính sách gợi ý |
| --- | --- |
| Local development | Bật introspection để hỗ trợ IDE và thử nghiệm. |
| CI và test | Bật để kiểm tra schema, sinh client và xác minh hợp đồng. |
| Staging | Bật có kiểm soát hoặc yêu cầu xác thực để đội tích hợp kiểm thử. |
| Production public API | Quyết định theo hợp đồng công bố; không đưa metadata bí mật vào schema. |
| Production private API | Có thể giới hạn hoặc tắt introspection theo yêu cầu bảo mật và vận hành. |

Điều quan trọng là chính sách phải nhất quán giữa các instance và môi trường. Nếu công cụ nội bộ cần introspection, có thể cung cấp tài liệu schema đã xuất trong pipeline CI hoặc một endpoint/schema dành riêng cho đội phát triển.

## Hạn chế introspection trong GraphQL Java

GraphQL Java cung cấp `GraphqlFieldVisibility` để kiểm soát field nào được nhìn thấy trong schema. Một lựa chọn có sẵn là `NoIntrospectionGraphqlFieldVisibility`, dùng để loại bỏ các field introspection như `__schema` và `__type` khỏi khả năng truy vấn schema.

Ví dụ ở tầng GraphQL Java khi xây dựng schema:

```java
import graphql.schema.GraphQLSchema;
import graphql.schema.visibility.NoIntrospectionGraphqlFieldVisibility;

GraphQLSchema restrictedSchema = GraphQLSchema.newSchema(existingSchema)
        .fieldVisibility(new NoIntrospectionGraphqlFieldVisibility())
        .build();
```

Đoạn mã minh họa cơ chế của GraphQL Java: schema được xây dựng với field visibility không cho truy cập introspection. Khi tích hợp vào Spring for GraphQL, cần áp dụng visibility này tại bước tạo `GraphQlSource`/`GraphQLSchema`, theo API của phiên bản GraphQL Java và Spring for GraphQL mà dự án đang dùng. `GraphQlSource` do Spring Boot tự cấu hình cũng phải được tùy biến đúng ở giai đoạn xây dựng schema; thêm một controller hoặc directive vào SDL không có tác dụng tắt introspection.

Không nên sao chép một cấu hình theo phiên bản khác mà chưa kiểm tra dependency thực tế. API xây dựng schema và cách Spring Boot cho phép tùy biến `GraphQlSource` có thể thay đổi giữa các phiên bản. Sau khi cấu hình, hãy kiểm thử trực tiếp `__schema` và `__type` trên endpoint đang chạy để xác nhận policy được áp dụng.

### `__typename` vẫn có mục đích riêng

`__typename` là meta-field trả về tên concrete object type của giá trị hiện tại. Nó thường được dùng trong interface, union và cache của client. `NoIntrospectionGraphqlFieldVisibility` nhằm chặn việc khám phá schema qua `__schema` và `__type`; không nên nhầm mục tiêu đó với việc loại bỏ `__typename` khỏi mọi response.

Ví dụ client vẫn có thể cần:

```graphql
query Search {
  search(term: "spring") {
    __typename
    ... on Book {
      title
    }
    ... on Article {
      title
    }
  }
}
```

## Schema visibility không thay thế authorization

Có ba mục tiêu khác nhau cần phân biệt:

1. **Ẩn metadata:** hạn chế người gọi khám phá type, field, argument và descriptions.
2. **Ẩn field trong schema:** tạo một schema view không công bố một số field hoặc type cho một nhóm client.
3. **Bảo vệ dữ liệu:** xác thực người gọi và quyết định họ có quyền đọc hoặc thay đổi giá trị hay không.

Field visibility có thể làm field không xuất hiện trong schema view và không được truy vấn thông qua schema đó. Tuy nhiên, đây là kiểm soát bề mặt API. Mọi field nhạy cảm vẫn cần authorization ở resolver hoặc service, bởi cấu hình visibility có thể bị thay đổi, một endpoint khác có thể dùng schema đầy đủ hoặc client có thể gọi một API nội bộ khác.

Đặc biệt, tắt introspection không làm field nghiệp vụ biến mất. Nếu field `internalReviewNote` vẫn nằm trong schema đang chạy, client biết tên field vẫn có thể gửi operation trực tiếp. Server phải kiểm tra quyền truy cập trong lúc thực thi.

### Không nên giả định schema visibility tự thay đổi theo user

`GraphqlFieldVisibility` là cấu hình của schema/runtime. Không nên mặc định rằng chỉ cần kiểm tra role trong một resolver là introspection tự ẩn field theo từng người dùng. Nếu một hệ thống thực sự cần các schema view khác nhau cho các nhóm client, hãy thiết kế schema hoặc `GraphQlSource` riêng cho từng audience, kiểm soát endpoint và cache theo chính sách đó.

Việc tạo schema riêng cho từng user có thể làm tăng độ phức tạp, bộ nhớ và chi phí khởi tạo. Thường dễ vận hành hơn nếu có một public schema và một internal schema với endpoint, xác thực và tài liệu riêng. Dù dùng một hay nhiều schema, quyền truy cập dữ liệu vẫn phải được kiểm tra tại server.

## Những kênh khác có thể làm lộ metadata

Tắt introspection không bảo đảm mọi thông tin về API đều được giữ kín. Metadata có thể xuất hiện ở:

- Error message có gợi ý tên field hợp lệ hoặc tiết lộ tên type.
- Tài liệu API, schema SDL, file sinh mã, source map hoặc JavaScript bundle của frontend.
- Log request/response, dashboard giám sát hoặc hệ thống tracing.
- Repository, artifact build, image container hoặc package được phân phối.
- Endpoint nội bộ được mở ra ngoài do cấu hình reverse proxy hoặc network.

Vì vậy, cần kiểm soát cả thông báo lỗi, quyền truy cập tài liệu, log và cách phân phối schema. Error trả cho client nên đủ hữu ích để xử lý request nhưng không để lộ stack trace, cấu trúc hạ tầng hoặc chi tiết nội bộ không cần thiết.

## Kiểm thử chính sách introspection và field protection

Khi triển khai hạn chế introspection hoặc bảo vệ field, nên kiểm tra các trường hợp sau:

- Request `__schema` bị từ chối hoặc không thể truy cập trong môi trường đã tắt introspection.
- Request `__type(name: ...)` cũng bị hạn chế tương ứng.
- Query nghiệp vụ hợp lệ vẫn hoạt động.
- `__typename` vẫn hoạt động nếu client cần nó cho interface/union.
- Người dùng không có quyền không thể đọc field nhạy cảm kể cả khi biết chính xác tên field.
- Người dùng có quyền chỉ nhận được dữ liệu thuộc phạm vi của họ.
- Descriptions, deprecation reasons và directive metadata không chứa thông tin bí mật.
- GraphiQL, code generation và công cụ tích hợp được kiểm tra lại nếu chúng phụ thuộc vào introspection.
- Tất cả instance production áp dụng cùng một cấu hình và endpoint nội bộ không bị phơi ra ngoài.

Ví dụ kiểm tra bằng `GraphQlTester` cho một field được bảo vệ có thể xác minh lỗi hoặc giá trị null theo hợp đồng đã chọn:

```java
@Test
void unauthorizedUserCannotReadInternalNote() {
    graphQlTester.document("""
        query {
          account(id: "acc-100") {
            internalReviewNote
          }
        }
        """)
        .execute()
        .errors()
        .verify();
}
```

Test này giả định chính sách của ứng dụng trả execution error khi không đủ quyền. Nếu hợp đồng API chọn trả `null` hoặc che giấu sự tồn tại của tài nguyên, hãy kiểm thử đúng hành vi đó và kiểm tra `errors` tương ứng. Điều quan trọng là dữ liệu nhạy cảm không xuất hiện trong response.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đã thêm `@sensitive` nhưng introspection vẫn thấy field | Custom directive chỉ gắn metadata, không tự thay đổi visibility. | Cấu hình field visibility hoặc schema view riêng; vẫn kiểm tra quyền trong resolver. |
| Dùng `@skip` nhưng field vẫn xuất hiện trong schema | `@skip` chỉ ảnh hưởng một operation cụ thể. | Dùng chính sách introspection/schema visibility nếu mục tiêu là hạn chế khám phá schema. |
| Tắt `__schema` nhưng client vẫn truy vấn field đã biết tên | Field vẫn tồn tại trong schema đang chạy. | Bổ sung authorization ở resolver/service hoặc loại field khỏi schema view phù hợp. |
| Tooling không tải được schema ở production | Introspection đã bị giới hạn. | Cung cấp schema artifact có kiểm soát hoặc endpoint nội bộ yêu cầu xác thực. |
| Description làm lộ thông tin nội bộ | Đưa ghi chú vận hành vào SDL description. | Rà soát và viết descriptions hướng tới người dùng API. |
| Một instance vẫn cho introspection | Cấu hình môi trường không đồng nhất hoặc custom GraphQlSource không nhận policy. | Kiểm thử tất cả instance và xác minh schema thực tế khi khởi động. |

## Ghi nhớ

Introspection cho phép client khám phá schema qua `__schema` và `__type`. Metadata có thể bao gồm tên type/field, arguments, descriptions, enum values và directive. Không đưa bí mật hoặc ghi chú nội bộ vào SDL descriptions, deprecation reasons hay directive metadata.

Các directive như `@skip`, `@include`, `@deprecated` và custom directive không tự ẩn field khỏi schema. GraphQL Java có `GraphqlFieldVisibility` và `NoIntrospectionGraphqlFieldVisibility` để hạn chế introspection; khi dùng Spring for GraphQL, áp dụng policy tại bước xây dựng `GraphQlSource`/schema theo đúng phiên bản đang chạy.

Cuối cùng, ẩn metadata chỉ giảm khả năng khám phá API. Nó không thay thế authorization. Mọi field chứa dữ liệu nhạy cảm phải kiểm tra quyền ở server, ngay cả khi introspection đã bị tắt.
