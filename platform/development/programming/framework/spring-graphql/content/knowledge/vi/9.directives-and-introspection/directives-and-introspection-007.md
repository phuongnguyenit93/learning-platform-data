# Introspection query trong GraphQL

**Introspection** là cơ chế cho phép client hoặc công cụ truy vấn metadata của GraphQL schema ngay thông qua GraphQL API. Thay vì phải đọc thủ công file SDL, client có thể hỏi server có những type nào, field nào, argument nào, kiểu trả về ra sao và directive nào được định nghĩa.

Introspection đặc biệt hữu ích cho công cụ phát triển như GraphQL IDE, trình tạo tài liệu API, code generator và client cần kiểm tra hợp đồng API. Với Spring for GraphQL, GraphQL Java cung cấp cơ chế introspection; ta có thể dùng `GraphQlTester` để kiểm tra metadata schema trong test.

## 1. Introspection hoạt động như thế nào?

GraphQL định nghĩa một số meta-field và meta-type dành riêng cho việc khám phá schema. Các thành phần thường dùng nhất là:

| Thành phần | Vai trò |
|---|---|
| `__schema` | Truy vấn schema tổng thể, gồm các root type, danh sách type và directive được định nghĩa. |
| `__type(name: String!)` | Truy vấn thông tin của một type theo tên. |
| `__typename` | Trả về tên object type cụ thể đang được phân giải tại runtime. |
| `__Type` | Introspection type mô tả một GraphQL type như object, interface, union, scalar hoặc enum. |
| `__Field`, `__InputValue`, `__EnumValue`, `__Directive` | Mô tả field, argument/input field, enum value và directive. |

`__schema` và `__type` là meta-field dành cho query root. `__typename` có thể được chọn trên object, interface và union để nhận diện kiểu cụ thể. `__typename` thường xuất hiện trong query nghiệp vụ, trong khi `__schema` và `__type` chủ yếu được dùng để khám phá hợp đồng schema.

## 2. Truy vấn tổng quan schema bằng `__schema`

Query sau lấy tên các root type, danh sách type và directive mà schema công bố:

```graphql
query SchemaOverview {
    __schema {
        queryType {
            name
        }
        mutationType {
            name
        }
        subscriptionType {
            name
        }
        types {
            kind
            name
            description
        }
        directives {
            name
            description
            locations
            args {
                name
                description
            }
        }
    }
}
```

Ý nghĩa các trường:

- `queryType`: object type làm điểm bắt đầu cho query operation.
- `mutationType`: root type của mutation; có thể là `null` nếu schema không khai báo mutation root.
- `subscriptionType`: root type của subscription; có thể là `null` nếu schema không hỗ trợ subscription.
- `types`: danh sách các type trong schema, bao gồm cả type tích hợp sẵn của GraphQL và type do ứng dụng định nghĩa.
- `directives`: các directive được định nghĩa, cùng vị trí được phép sử dụng và argument của chúng.

Mỗi phần tử trong `types` có `kind`, `name` và `description`. `kind` cho biết type thuộc nhóm nào, chẳng hạn `OBJECT`, `INTERFACE`, `UNION`, `SCALAR`, `ENUM` hoặc `INPUT_OBJECT`.

Danh sách `types` có thể khá dài vì chứa cả các scalar và introspection type tích hợp sẵn như `String`, `Int`, `__Schema`, `__Type`. Khi xây dựng tài liệu hoặc code generator, client thường lọc những type có tiền tố `__` hoặc chỉ lấy những type thuộc phạm vi ứng dụng.

## 3. Xem chi tiết một type bằng `__type`

`__type(name: String!)` nhận tên type và trả về metadata của type đó. Ví dụ, để xem type `Book`:

```graphql
query InspectBook {
    __type(name: "Book") {
        kind
        name
        description
        fields {
            name
            description
            type {
                kind
                name
            }
        }
    }
}
```

Nếu `Book` là object type, `fields` cho biết các field mà object công bố. Mỗi field có tên, mô tả và kiểu dữ liệu trả về. Nếu tên truyền vào không tồn tại, `__type` trả về `null`.

Có thể dùng biến thay cho tên type cố định:

```graphql
query InspectType($typeName: String!) {
    __type(name: $typeName) {
        name
        kind
        description
    }
}
```

Ví dụ variables:

```json
{
  "typeName": "Book"
}
```

### Xem field, argument và kiểu trả về

Để xây dựng tài liệu chi tiết hơn, có thể truy vấn cả argument và default value:

```graphql
query InspectBookFields {
    __type(name: "Book") {
        name
        fields(includeDeprecated: true) {
            name
            description
            args {
                name
                description
                defaultValue
                type {
                    kind
                    name
                }
            }
            type {
                kind
                name
            }
            isDeprecated
            deprecationReason
        }
    }
}
```

`args` mô tả các argument mà field nhận. `defaultValue` là biểu diễn giá trị mặc định theo cú pháp GraphQL; nó được trả về dưới dạng chuỗi. `isDeprecated` và `deprecationReason` cho biết field có được đánh dấu bằng `@deprecated` hay không.

Trong ví dụ trên, `includeDeprecated: true` yêu cầu trả về cả field đã deprecated. Nếu không truyền tham số này, những field deprecated có thể bị ẩn khỏi danh sách tùy theo mặc định của introspection field.

## 4. Đọc các nhóm type khác nhau

`__Type` cung cấp những field introspection phù hợp với từng loại GraphQL type. Không phải field nào cũng có giá trị cho mọi `kind`.

| Field của `__Type` | Dùng cho | Nội dung |
|---|---|---|
| `fields` | Object và interface | Các field mà type cung cấp. |
| `interfaces` | Object và interface | Các interface mà type triển khai hoặc kế thừa. |
| `possibleTypes` | Interface và union | Những object type cụ thể có thể xuất hiện tại runtime. |
| `enumValues` | Enum | Các giá trị enum được khai báo. |
| `inputFields` | Input object | Những field có thể gửi trong input object. |
| `specifiedByURL` | Custom scalar | URL đặc tả của scalar nếu được khai báo bằng `@specifiedBy`. |

Ví dụ xem các thành viên của union:

```graphql
query InspectSearchResult {
    __type(name: "SearchResult") {
        name
        kind
        possibleTypes {
            name
            kind
        }
    }
}
```

Nếu `SearchResult` là union của `Book` và `Author`, `possibleTypes` sẽ liệt kê hai object type đó. Thông tin này hữu ích cho công cụ sinh code hoặc client cần biết các kiểu mà inline fragment có thể sử dụng.

Ví dụ xem enum:

```graphql
query InspectOrderStatus {
    __type(name: "OrderStatus") {
        kind
        enumValues(includeDeprecated: true) {
            name
            description
            isDeprecated
            deprecationReason
        }
    }
}
```

Ví dụ xem input object:

```graphql
query InspectProductInput {
    __type(name: "ProductInput") {
        kind
        inputFields {
            name
            description
            defaultValue
            type {
                kind
                name
            }
        }
    }
}
```

Với các phiên bản GraphQL hỗ trợ tham số `includeDeprecated` trên `inputFields`, có thể truyền `includeDeprecated: true` để lấy cả input field đã deprecated. Nếu server dùng phiên bản cũ chưa hỗ trợ argument đó, hãy bỏ tham số để query tương thích.

## 5. Hiểu kiểu dữ liệu qua `kind`, `name` và `ofType`

Khi introspection một field, `type.name` đôi khi là `null`. Điều này thường xảy ra khi field sử dụng wrapper type như Non-null (`!`) hoặc List (`[]`). Cần đọc thêm `ofType` để đi sâu vào kiểu bên trong.

Các giá trị `kind` quan trọng:

- `SCALAR`: kiểu scalar như `String`, `Int`, `Float`, `Boolean`, `ID` hoặc custom scalar.
- `OBJECT`: object type như `Book`.
- `INTERFACE`: interface type.
- `UNION`: union type.
- `ENUM`: enum type.
- `INPUT_OBJECT`: input object type.
- `LIST`: wrapper danh sách.
- `NON_NULL`: wrapper không cho phép `null`.

Ví dụ:

```graphql
type Query {
    book: Book!
    books: [Book!]!
}
```

Với `book: Book!`, introspection trả về cấu trúc tương tự:

```text
kind = NON_NULL
name = null
ofType:
  kind = OBJECT
  name = Book
```

Với `books: [Book!]!`, cấu trúc lồng nhau tương tự:

```text
NON_NULL
  ofType: LIST
    ofType: NON_NULL
      ofType: OBJECT
        name: Book
```

Do `ofType` có thể lồng nhiều cấp, một query introspection thường dùng fragment đệ quy có độ sâu hữu hạn. GraphQL không cho phép fragment tự tham chiếu vô hạn trong document; vì vậy client cần đặt đủ số cấp cho schema mình muốn đọc.

```graphql
query InspectBookType {
    __type(name: "Query") {
        fields {
            name
            type {
                ...TypeRef
            }
        }
    }
}

fragment TypeRef on __Type {
    kind
    name
    ofType {
        kind
        name
        ofType {
            kind
            name
            ofType {
                kind
                name
                ofType {
                    kind
                    name
                }
            }
        }
    }
}
```

Độ sâu bốn cấp là ví dụ minh họa, không phải giới hạn cố định của GraphQL. Nếu schema có kiểu wrapper sâu hơn, hãy mở rộng fragment tương ứng. Khi viết công cụ tổng quát, cần xử lý trường hợp query chưa lấy đủ cấp và không được nhầm `name: null` của wrapper với một type không hợp lệ.

## 6. Introspection và directive

`__schema.directives` cho phép xem các directive được schema định nghĩa, ví dụ tên, mô tả, location và argument:

```graphql
query InspectDirectives {
    __schema {
        directives {
            name
            description
            locations
            args {
                name
                description
                defaultValue
                type {
                    kind
                    name
                }
            }
        }
    }
}
```

Kết quả có thể bao gồm directive tích hợp như `include`, `skip`, `deprecated`, `specifiedBy` và directive tùy chỉnh của ứng dụng.

Cần phân biệt **định nghĩa directive** với **vị trí đã áp dụng directive**. Introspection tiêu chuẩn cho phép khám phá định nghĩa directive, nhưng không phải mọi phiên bản GraphQL đều cung cấp metadata về từng lần directive được gắn lên field hoặc type trong SDL. Nếu cần xác định chính xác field nào được gắn `@requiresRole` hoặc `@sensitive`, hãy kiểm tra SDL hoặc dùng API/AST của GraphQL Java phù hợp với phiên bản đang chạy.

## 7. `__typename` trong query nghiệp vụ

Khác với `__schema` và `__type`, `__typename` thường được dùng ngay trong query nghiệp vụ để xác định kiểu runtime của object:

```graphql
query {
    search(keyword: "GraphQL") {
        __typename
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

Nếu một phần tử là `Book`, `__typename` trả về `Book`; nếu là `Author`, nó trả về `Author`. Client có thể dùng kết quả để chọn cách hiển thị phù hợp.

`__typename` cũng hữu ích khi làm việc với interface, union và normalized cache của GraphQL client. Nó không thay thế `TypeResolver` ở server: server vẫn phải xác định object Java thuộc GraphQL object type nào trước khi trả kết quả.

## 8. Sử dụng introspection trong Spring for GraphQL

Spring for GraphQL dựa trên GraphQL Java để xây dựng schema và xử lý query. Khi introspection được cho phép trong cấu hình server, client có thể gửi query `__schema` hoặc `__type` đến GraphQL endpoint giống như các query khác.

Không cần viết `@QueryMapping` riêng cho `__schema` hay `__type`; đây là meta-field của GraphQL. Những resolver nghiệp vụ của ứng dụng vẫn được đăng ký bình thường.

Có thể kiểm tra schema bằng `GraphQlTester` trong test:

```java
@GraphQlTest(BookController.class)
class SchemaIntrospectionTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void exposesBookType() {
        graphQlTester.document("""
                query {
                    __type(name: "Book") {
                        name
                        kind
                        fields {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("__type.name").entity(String.class).isEqualTo("Book");
    }
}
```

Đây là ví dụ minh họa; các import được lược bỏ và schema có khai báo `Book` cần được nạp trong test context. `BookService` được mock để controller có thể được khởi tạo; tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Có thể mở rộng assertion để kiểm tra các field bắt buộc, kiểu trả về, directive hoặc union member. Cách này giúp phát hiện thay đổi schema ngoài dự kiến ngay trong quá trình kiểm thử.

Nếu introspection bị tắt trong cấu hình ứng dụng, test cần dùng cấu hình cho phép introspection hoặc kiểm tra schema trực tiếp qua API phù hợp. Cơ chế bật/tắt cụ thể phụ thuộc phiên bản Spring Boot và GraphQL Java mà dự án sử dụng; không nên sao chép một property cấu hình từ phiên bản khác khi chưa kiểm tra dependency hiện tại.

## 9. Ứng dụng thực tế của Introspection

Introspection không chỉ dành cho GraphQL IDE. Một số ứng dụng phổ biến:

| Ứng dụng | Cách sử dụng |
|---|---|
| Tạo tài liệu API | Đọc type, field, argument, description và deprecation metadata để tạo tài liệu. |
| Code generation | Sinh kiểu dữ liệu client, model và operation helper từ schema. |
| Kiểm tra tương thích | So sánh schema giữa các lần phát hành để phát hiện field bị xóa, đổi kiểu hoặc thay đổi nullability. |
| Công cụ phát triển | GraphQL IDE dùng metadata để gợi ý field, argument và autocomplete. |
| Kiểm thử hợp đồng | Xác minh schema có type, field, union member và directive như mong đợi. |
| Phân tích schema | Liệt kê object, interface, union, enum và quan hệ giữa các type. |

Ví dụ, pipeline CI có thể truy vấn introspection schema từ môi trường kiểm thử rồi so sánh với schema của bản phát hành trước. Nếu một field `String` bị đổi thành `String!`, đó có thể là thay đổi hợp đồng ảnh hưởng đến client vì server đang đưa ra cam kết chặt hơn về nullability.

## 10. Bảo mật và giới hạn của Introspection

Introspection công bố cấu trúc API: tên type, field, argument, mô tả, directive và quan hệ giữa các kiểu. Điều này hữu ích cho client hợp lệ nhưng cũng giúp người ngoài hiểu bề mặt API nếu endpoint công khai.

Một số hệ thống giới hạn introspection ở production hoặc yêu cầu quyền truy cập phù hợp. Cần lưu ý:

1. Việc tắt introspection không thay thế authentication và authorization cho các field nghiệp vụ.
2. Không nên dựa vào việc ẩn schema để bảo vệ dữ liệu; resolver và service vẫn phải kiểm tra quyền truy cập.
3. Nếu bật introspection cho công cụ nội bộ, hãy kiểm soát ai có thể truy cập endpoint và môi trường nào được phép dùng.
4. Kiểm tra mô tả schema để tránh đưa thông tin nội bộ, tên hệ thống hoặc chi tiết triển khai nhạy cảm vào metadata công khai.
5. Một số công cụ cần introspection để hoạt động; hãy cân nhắc tác động trước khi tắt hoàn toàn trong môi trường phát triển hoặc tích hợp.

Introspection query lớn có thể trả về nhiều metadata và tốn tài nguyên. Server có thể áp dụng giới hạn kích thước query, depth, complexity hoặc chính sách riêng cho endpoint. Các giới hạn này nên được thiết kế cùng cơ chế bảo vệ GraphQL tổng thể.

## 11. Lỗi thường gặp

**Nhầm `__typename` với `__type`.** `__typename` trả về tên object type đang được phân giải trong query; `__type(name:)` truy vấn metadata của một type theo tên.

**Nghĩ rằng `__schema.types` chỉ chứa type do ứng dụng tạo.** Danh sách còn có các scalar và introspection type tích hợp sẵn. Hãy lọc theo `kind` hoặc tên khi tạo tài liệu.

**Không đọc `ofType`.** Nếu field là `String!` hoặc `[Book!]!`, `name` của wrapper có thể là `null`. Cần đi sâu qua `ofType` để hiểu kiểu thực.

**Query fragment type reference quá nông.** Một wrapper có nhiều cấp có thể bị cắt cụt nếu fragment chỉ đọc một hoặc hai lần `ofType`. Tăng độ sâu phù hợp với schema và xử lý trường hợp chưa đủ dữ liệu.

**Cho rằng introspection luôn hiển thị directive đã áp dụng.** Introspection tiêu chuẩn chủ yếu công bố định nghĩa directive. Muốn biết directive được gắn lên field cụ thể, cần kiểm tra SDL hoặc API AST phù hợp.

**Dùng introspection như cơ chế bảo mật.** Ẩn schema không ngăn client gọi một field nếu họ đã biết tên và được endpoint cho phép. Phải bảo vệ resolver và dữ liệu bằng authorization thực tế.

**Không kiểm tra phiên bản GraphQL.** Các argument introspection như `includeDeprecated` trên input fields có thể khác nhau theo phiên bản. Query cần tương thích với schema introspection mà server thực sự cung cấp.

## Kết luận

Introspection query cho phép khám phá GraphQL schema thông qua `__schema`, `__type` và các introspection type như `__Type`, `__Field`, `__InputValue` và `__Directive`. Nó giúp công cụ tạo tài liệu, sinh code, kiểm tra hợp đồng và hỗ trợ client khám phá API. Khi dùng với Spring for GraphQL, hãy kiểm tra metadata bằng `GraphQlTester`, hiểu cấu trúc wrapper qua `ofType`, kiểm tra khả năng introspection của môi trường triển khai và luôn thực thi bảo mật ở resolver cùng service.
