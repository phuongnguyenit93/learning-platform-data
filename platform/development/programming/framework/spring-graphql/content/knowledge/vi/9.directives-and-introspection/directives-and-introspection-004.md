# Deprecated field

## 1. Deprecated field là gì?

GraphQL schema là hợp đồng giữa server và các client. Khi API đã được nhiều ứng dụng sử dụng, việc đổi tên hoặc xóa một field có thể làm query đang chạy của client cũ thất bại. Trong thực tế, server thường cần một giai đoạn chuyển tiếp để giới thiệu field mới, hướng dẫn client di chuyển và xác nhận field cũ không còn được sử dụng trước khi loại bỏ.

GraphQL cung cấp directive chuẩn `@deprecated` để đánh dấu một field hoặc enum value không còn được khuyến nghị sử dụng. Metadata này giúp công cụ đọc schema, IDE và người phát triển biết API nào đang được thay thế, đồng thời có thể hiển thị cảnh báo và lý do di chuyển.

Ví dụ, API trước đây công bố field `name` nhưng muốn chuyển sang `displayName`:

```graphql
type User {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
```

Trong ví dụ này, `name` vẫn tồn tại trong schema và client cũ vẫn có thể truy vấn nó. Directive chỉ đánh dấu field đã lỗi thời và cung cấp hướng dẫn chuyển sang `displayName`. Server quyết định thời điểm xóa field trong một thay đổi schema sau này.

## 2. Cú pháp `@deprecated` trong SDL

`@deprecated` là directive được GraphQL định nghĩa sẵn. Không cần tự khai báo directive này trong schema. Có thể đặt nó sau kiểu trả về của field:

```graphql
type Product {
    id: ID!
    oldPrice: Float @deprecated(reason: "Use price instead.")
    price: Float!
}
```

`reason` là argument kiểu `String`. Nếu không truyền `reason`, giá trị mặc định theo đặc tả là `No longer supported`:

```graphql
type Product {
    oldPrice: Float @deprecated
    price: Float!
}
```

Trong dự án thực tế, nên cung cấp lý do rõ ràng và chỉ ra field thay thế. Lý do mặc định cho biết field không còn được hỗ trợ nhưng không giúp client biết cần sửa query thế nào.

### Đánh dấu một field trong root Query

Directive có thể áp dụng cho field ở root type như `Query` hoặc `Mutation`:

```graphql
type Query {
    user(id: ID!): User

    userByUsername(username: String!): User
        @deprecated(reason: "Use user(id:) instead.")
}
```

Client nên chuyển từ `userByUsername` sang `user` và truyền định danh phù hợp. Trong thời gian chuyển đổi, cả hai field có thể cùng tồn tại để các phiên bản client cũ tiếp tục hoạt động.

### Đánh dấu enum value

`@deprecated` cũng có thể đánh dấu một giá trị của enum:

```graphql
enum OrderStatus {
    PENDING
    PAID
    FULFILLED
    SHIPPED @deprecated(reason: "Use FULFILLED instead.")
}
```

Client không nên tiếp tục gửi hoặc phụ thuộc vào `SHIPPED` khi đã có giá trị thay thế. Server cần duy trì cách xử lý tương thích trong giai đoạn di chuyển, đặc biệt nếu enum value xuất hiện trong dữ liệu lưu trữ hoặc được gửi từ nhiều client.

## 3. `@deprecated` không xóa field và không chặn truy vấn

Đây là điểm quan trọng khi thiết kế vòng đời API:

- Field được đánh dấu deprecated vẫn là một phần của schema.
- Client vẫn có thể gửi query sử dụng field đó.
- GraphQL vẫn validation và thực thi resolver của field như bình thường.
- Metadata deprecation giúp công cụ và con người nhận biết field nên được thay thế.
- Field chỉ biến mất khi server thực sự xóa định nghĩa khỏi schema.

Ví dụ, cả hai query sau vẫn hợp lệ khi schema có `name` và `displayName`:

```graphql
query OldClient($id: ID!) {
    user(id: $id) {
        name
    }
}

query NewClient($id: ID!) {
    user(id: $id) {
        displayName
    }
}
```

Sau khi xóa `name` khỏi schema, query của `OldClient` sẽ bị validation từ chối vì field không còn tồn tại. Do đó, đánh dấu deprecated là bước chuẩn bị cho việc thay đổi hợp đồng, không phải cơ chế tự động chuyển client sang field mới.

`@deprecated` cũng không phải cơ chế bảo mật. Không dùng directive này để ẩn dữ liệu, thu hồi quyền hoặc ngăn người dùng truy vấn field. Nếu cần từ chối truy cập, hãy thiết kế authorization ở server và thay đổi API theo quy trình phù hợp.

## 4. Đọc thông tin deprecated bằng introspection

GraphQL introspection cho phép client hoặc công cụ hỏi schema về các type, field, argument và directive. Với field, introspection cung cấp hai thuộc tính:

- `isDeprecated`: cho biết field có được đánh dấu deprecated hay không.
- `deprecationReason`: lý do được khai báo trong directive, hoặc giá trị mặc định nếu không truyền lý do.

Theo mặc định, trường `fields` của introspection bỏ qua field deprecated. Cần truyền `includeDeprecated: true` để lấy cả field cũ:

```graphql
query UserFields {
    __type(name: "User") {
        name
        fields(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
```

Response minh họa:

```json
{
  "data": {
    "__type": {
      "name": "User",
      "fields": [
        {
          "name": "id",
          "isDeprecated": false,
          "deprecationReason": null
        },
        {
          "name": "name",
          "isDeprecated": true,
          "deprecationReason": "Use displayName instead."
        },
        {
          "name": "displayName",
          "isDeprecated": false,
          "deprecationReason": null
        }
      ]
    }
  }
}
```

`__type(name: "User")` yêu cầu thông tin của type `User`. `includeDeprecated: true` bảo đảm field cũ vẫn xuất hiện trong danh sách để công cụ có thể đọc metadata và đưa ra cảnh báo.

### Introspection enum value

Đối với enum, dùng `enumValues(includeDeprecated: true)`:

```graphql
query OrderStatusValues {
    __type(name: "OrderStatus") {
        name
        enumValues(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
```

Các công cụ sinh tài liệu hoặc kiểm tra schema có thể dùng kết quả này để liệt kê giá trị enum cần di chuyển. Nếu không bật `includeDeprecated`, các giá trị đã deprecated có thể không xuất hiện trong danh sách.

## 5. Thiết kế lý do deprecation hữu ích

Lý do deprecation là thông tin hướng dẫn cho người đang dùng API. Một reason tốt nên ngắn gọn, cụ thể và có hành động tiếp theo.

Ví dụ tốt:

```graphql
type User {
    fullName: String
        @deprecated(reason: "Use displayName; it preserves the formatted name shown to users.")
    displayName: String!
}
```

Reason cho biết field mới cần dùng và giải thích khác biệt quan trọng. Một số nội dung nên cân nhắc đưa vào reason:

- Tên field hoặc enum value thay thế.
- Cách chuyển đổi đối số nếu field mới có signature khác.
- Khác biệt về ý nghĩa dữ liệu hoặc định dạng trả về.
- Liên kết đến tài liệu migration nếu tổ chức có tài liệu công khai ổn định.
- Mốc ngừng hỗ trợ nếu đã có lịch chính thức và có thể duy trì đúng cam kết.

Tránh các reason mơ hồ như `Old field`, `Deprecated` hoặc `Do not use`. Những câu này không giúp người dùng biết phải thay đổi query như thế nào.

## 6. Duy trì resolver trong Spring for GraphQL

Với Spring for GraphQL, schema-first SDL thường được đặt trong `src/main/resources/graphql/`. Directive `@deprecated` được khai báo trực tiếp trong schema:

```graphql
type User {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}

type Query {
    user(id: ID!): User
}
```

Trong giai đoạn chuyển tiếp, resolver cho field cũ và field mới có thể cùng sử dụng một nguồn dữ liệu hoặc một quy tắc nghiệp vụ:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class UserController {

    @SchemaMapping(typeName = "User", field = "name")
    public String legacyName(User user) {
        return user.displayName();
    }

    @SchemaMapping(typeName = "User", field = "displayName")
    public String displayName(User user) {
        return user.displayName();
    }
}
```

Ví dụ giả định `User` là Java record có phương thức `displayName()`. Cả hai GraphQL field cùng trả về một giá trị nghiệp vụ, nhưng schema metadata cho biết `name` là field cũ.

`@SchemaMapping` ánh xạ phương thức Java đến field trong schema. Directive `@deprecated` thuộc hợp đồng SDL và được GraphQL Java công bố qua introspection. Không nên giả định rằng chỉ thêm annotation Java `@Deprecated` vào phương thức sẽ tự động cập nhật metadata deprecation trong schema; hãy khai báo directive trong SDL một cách tường minh.

### Không xóa resolver ngay khi đánh dấu deprecated

Nếu xóa resolver hoặc ngừng cung cấp dữ liệu trong khi field vẫn tồn tại, client cũ có thể nhận lỗi thực thi dù query vẫn hợp lệ theo schema. Trong giai đoạn chuyển tiếp, cần giữ hành vi tương thích cho field cũ, hoặc có một resolver mặc định có thể cung cấp đúng giá trị.

Chỉ sau khi đã xác nhận client không còn phụ thuộc vào field, nhóm phát triển mới nên xóa định nghĩa SDL và logic không còn cần thiết.

## 7. Quy trình thay thế một field an toàn

Giả sử API hiện có `user.fullName` và muốn thay bằng `user.displayName`. Có thể triển khai theo các bước:

1. **Thiết kế field mới:** xác định kiểu, nullability, ý nghĩa và cách resolver cung cấp dữ liệu.
2. **Bổ sung field mới:** thêm `displayName` vào SDL và triển khai resolver tương ứng.
3. **Đánh dấu field cũ:** thêm `@deprecated(reason: "Use displayName instead.")` vào `fullName`.
4. **Cập nhật tài liệu và client:** hướng dẫn nhóm phát triển chuyển query, fragment, generated types và code xử lý response sang field mới.
5. **Theo dõi việc sử dụng:** thu thập operation hoặc field usage phù hợp để xác định client nào vẫn dùng field cũ.
6. **Thông báo thời hạn:** nếu có lịch loại bỏ, công bố rõ mốc và phối hợp với các nhóm sở hữu client.
7. **Xác nhận không còn phụ thuộc:** kiểm tra traffic, persisted operation, phiên bản ứng dụng và các integration đã biết.
8. **Xóa field cũ:** loại bỏ định nghĩa SDL và resolver trong một thay đổi có kiểm soát; kiểm tra schema diff và các client còn hoạt động.

Không phải mọi dự án đều cần một khoảng thời gian dài cho từng bước. Thời gian chuyển tiếp phụ thuộc vào số lượng client, khả năng cập nhật đồng bộ và mức độ quan trọng của field.

## 8. Theo dõi việc sử dụng field cũ

Introspection cho biết field nào đã được đánh dấu deprecated, nhưng không cho biết client nào đang thực sự gọi field đó. Để quyết định thời điểm xóa, server cần dữ liệu usage từ hoạt động thực tế.

Các nguồn dữ liệu có thể sử dụng:

- Log hoặc metrics theo operation name và field được thực thi.
- GraphQL instrumentation hoặc observability để ghi nhận resolver/field usage.
- Persisted query registry nếu hệ thống quản lý danh sách operation đã đăng ký.
- Thông tin phiên bản ứng dụng hoặc client identity nếu request có cung cấp và chính sách cho phép.
- Kiểm tra query trong source code của các client do tổ chức quản lý.

Nên thu thập dữ liệu ở mức đủ để xác định phụ thuộc mà không ghi lại variables nhạy cảm hoặc toàn bộ payload không cần thiết. Một field không xuất hiện trong traffic vài ngày chưa chắc đã an toàn để xóa nếu có client chạy theo chu kỳ dài, ứng dụng di động cũ hoặc tác vụ tích hợp ít được gọi.

Nếu có nhiều client độc lập, nên thống nhất cách đo usage và mốc không còn request trước khi lên kế hoạch xóa. Với persisted queries, cần kiểm tra cả các operation đã đăng ký nhưng ít được thực thi.

## 9. Deprecation và tương thích schema

Đánh dấu deprecated thường là thay đổi tương thích ngược vì field vẫn tồn tại và client cũ vẫn có thể query. Xóa field là thay đổi phá vỡ tương thích đối với operation đang tham chiếu field đó.

| Thay đổi | Tác động thông thường |
| --- | --- |
| Thêm field mới | Tương thích với client hiện tại |
| Thêm `@deprecated` cho field đang tồn tại | Giữ khả năng query; bổ sung metadata cảnh báo |
| Đổi reason của `@deprecated` | Thay đổi hướng dẫn, không đổi cấu trúc dữ liệu |
| Giữ field cũ và thêm resolver tương thích | Client cũ và mới có thể cùng hoạt động |
| Xóa field khỏi schema | Client còn query field đó sẽ lỗi validation |
| Xóa enum value đang được client sử dụng | Có thể làm operation hoặc dữ liệu cũ không còn hợp lệ |

Trước khi xóa, cần kiểm tra schema diff, chạy kiểm thử operation đại diện và rà soát persisted queries. Với API được nhiều tổ chức sử dụng, có thể cần quy trình versioning hoặc lịch sunset được công bố rõ ràng.

## 10. Kiểm thử deprecated metadata

Có thể dùng GraphQlTester để kiểm tra introspection trả về đúng metadata:

```java
graphQlTester.document("""
    query UserFields {
        __type(name: "User") {
            fields(includeDeprecated: true) {
                name
                isDeprecated
                deprecationReason
            }
        }
    }
    """)
    .execute()
    .path("__type.fields")
    .entityList(UserFieldMetadata.class)
    .satisfies(fields -> {
        UserFieldMetadata legacy = fields.stream()
            .filter(field -> field.name().equals("name"))
            .findFirst()
            .orElseThrow();

        assertThat(legacy.isDeprecated()).isTrue();
        assertThat(legacy.deprecationReason())
            .isEqualTo("Use displayName instead.");
    });
```

DTO dùng trong ví dụ có thể khai báo bằng Java record:

```java
public record UserFieldMetadata(
        String name,
        boolean isDeprecated,
        String deprecationReason) {
}
```

Đoạn mã tập trung minh họa cách đọc introspection; tùy phiên bản Spring GraphQL và cách cấu hình mapper, có thể cần điều chỉnh kiểu DTO hoặc cách trích xuất dữ liệu.

Ngoài introspection, cần kiểm tra field cũ vẫn thực thi được trong giai đoạn chuyển tiếp:

```graphql
query LegacyUser($id: ID!) {
    user(id: $id) {
        name
    }
}
```

Và field mới trả về dữ liệu đúng:

```graphql
query CurrentUser($id: ID!) {
    user(id: $id) {
        displayName
    }
}
```

Khi đến thời điểm xóa field cũ, bổ sung kiểm thử xác nhận schema không còn field đó và các operation mới vẫn hợp lệ. Không nên chỉ kiểm tra file SDL; hãy kiểm tra schema runtime sau khi Spring for GraphQL khởi tạo.

## 11. Lỗi thường gặp khi sử dụng `@deprecated`

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field cũ không xuất hiện trong introspection | Truy vấn `fields` không đặt `includeDeprecated: true` | Bật `includeDeprecated` khi cần đọc đầy đủ schema |
| Client vẫn query được field deprecated | Đây là hành vi đúng; directive không chặn thực thi | Giữ resolver tương thích cho đến khi đủ điều kiện xóa |
| IDE không hiển thị cảnh báo | Tooling chưa đọc metadata hoặc schema cache chưa được cập nhật | Refresh schema và kiểm tra hỗ trợ deprecation của công cụ |
| Reason không giúp client di chuyển | Nội dung quá chung chung hoặc không chỉ ra field thay thế | Viết reason có tên thay thế và hướng dẫn cụ thể |
| Field cũ query hợp lệ nhưng resolver lỗi | Logic hoặc resolver đã bị xóa quá sớm | Duy trì resolver cho tới khi hoàn tất migration |
| Xóa field làm hỏng client cũ | Chưa đo usage hoặc chưa kiểm tra persisted operation | Rà soát traffic, schema diff và client trước khi xóa |
| Nghĩ `@Deprecated` Java tự cập nhật SDL | Annotation Java và directive GraphQL là hai metadata khác nhau | Khai báo `@deprecated` trong schema SDL |
| Dùng deprecation để bảo vệ dữ liệu | Directive chỉ là metadata hướng dẫn | Dùng authorization và kiểm soát truy cập phía server |

## 12. Checklist trước khi loại bỏ field deprecated

- [ ] Field thay thế đã tồn tại và có ý nghĩa dữ liệu tương đương hoặc được mô tả rõ.
- [ ] Field cũ có `@deprecated` với reason cụ thể.
- [ ] Resolver cũ vẫn hoạt động trong thời gian chuyển tiếp.
- [ ] Tài liệu migration đã hướng dẫn cách cập nhật query và generated types.
- [ ] Introspection trả về `isDeprecated` và `deprecationReason` đúng.
- [ ] Đã theo dõi field usage từ traffic, instrumentation hoặc persisted operations.
- [ ] Đã xem xét client ít hoạt động, ứng dụng di động cũ và integration định kỳ.
- [ ] Đã thông báo lịch loại bỏ cho các nhóm sở hữu client nếu cần.
- [ ] Schema diff và kiểm thử operation đã được chạy trước khi xóa.
- [ ] Định nghĩa SDL, resolver và logic liên quan chỉ được xóa sau khi hết phụ thuộc.

## Kết luận

Directive `@deprecated` giúp đánh dấu field hoặc enum value không còn được khuyến nghị sử dụng và công bố lý do thay thế trong GraphQL schema. Metadata này được đọc qua introspection bằng `isDeprecated` và `deprecationReason`; khi cần lấy cả field cũ, truy vấn phải đặt `includeDeprecated: true`.

Trong Spring for GraphQL, hãy khai báo `@deprecated` trực tiếp trong SDL và duy trì resolver tương thích trong giai đoạn chuyển tiếp. Việc đánh dấu deprecated không tự chặn query, không xóa field và không thay thế cơ chế phân quyền. Chỉ loại bỏ field sau khi đã hướng dẫn client di chuyển, đo mức sử dụng, kiểm tra operation còn phụ thuộc và xác nhận thay đổi schema an toàn.
