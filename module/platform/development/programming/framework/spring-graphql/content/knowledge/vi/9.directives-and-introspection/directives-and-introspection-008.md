# Schema introspection trong production

GraphQL introspection là cơ chế cho phép client hỏi server về chính schema đang được triển khai: có những type nào, field nào, argument nào, kiểu trả về ra sao và field nào đã deprecated. Cơ chế này rất hữu ích cho GraphiQL, IDE, code generation, tài liệu API và công cụ kiểm thử.

Trong production, introspection cần được xem như một khả năng truy cập metadata của API. Việc bật hay tắt nên dựa trên đối tượng sử dụng, mức độ công khai của schema và yêu cầu vận hành. Với Spring for GraphQL, cần phân biệt rõ introspection query, giao diện GraphiQL và endpoint xuất schema; đây là các tính năng liên quan nhưng độc lập.

## 1. Introspection là gì?

GraphQL định nghĩa các meta-field để client có thể khám phá schema:

- `__schema`: truy vấn thông tin tổng quan về schema, gồm root operation types, danh sách type và directive.
- `__type(name: ...)`: truy vấn chi tiết một type theo tên, ví dụ field, argument, kiểu trả về và mô tả.
- `__typename`: lấy tên object type cụ thể của giá trị đang được trả về tại runtime.

Ví dụ truy vấn tên root query type và một số type trong schema:

```graphql
query InspectSchema {
    __schema {
        queryType {
            name
        }
        types {
            name
            kind
        }
    }
}
```

Truy vấn chi tiết type `Product`:

```graphql
query InspectProduct {
    __type(name: "Product") {
        name
        kind
        description
        fields {
            name
            description
            isDeprecated
            deprecationReason
            type {
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

Response introspection có thể cho biết `Product` là object type, có field nào và field đó trả về kiểu gì. Với wrapper như List và Non-Null, thông tin kiểu có thể được lồng trong `ofType`; công cụ introspection thường truy vấn đệ quy để dựng lại đầy đủ kiểu như `[Product!]!`.

`__typename` có mục đích khác: nó cho biết kiểu object cụ thể của một giá trị trong response, thường dùng cùng interface, union và inline fragment. Trong nhiều ứng dụng, client vẫn cần `__typename` kể cả khi quyền khám phá toàn bộ schema bị giới hạn.

## 2. Introspection giúp ích gì trong quá trình phát triển?

Các công cụ GraphQL sử dụng introspection cho nhiều công việc:

- GraphiQL và IDE hiển thị field, argument, kiểu dữ liệu và mô tả khi người dùng viết query.
- Code generator tạo model, type và client API từ schema.
- Công cụ tài liệu xây dựng reference cho từng type, field và directive.
- Công cụ kiểm thử hoặc schema registry lấy schema để so sánh thay đổi.
- Công cụ tích hợp có thể xác minh server đang triển khai đúng contract mà client mong đợi.

Với API nội bộ, introspection có thể giảm công sức đồng bộ tài liệu giữa server và các nhóm client. Tuy nhiên, công cụ nên lấy schema trong CI hoặc từ schema registry đáng tin cậy nếu không cần truy cập endpoint production.

## 3. Rủi ro khi để introspection mở công khai

Introspection không tự trả về dữ liệu nghiệp vụ của người dùng. Nó trả về metadata của API. Tuy vậy, schema metadata có thể giúp người ngoài hiểu cấu trúc và tìm kiếm các điểm cần kiểm tra:

- Tên query và mutation cho biết những khả năng mà API cung cấp.
- Field và argument có thể gợi ý luồng nghiệp vụ, bộ lọc hoặc chức năng quản trị.
- Kiểu dữ liệu và nullability giúp dự đoán cách server xử lý input và output.
- Description, deprecation reason và directive có thể để lộ thông tin thiết kế hoặc chi tiết triển khai nếu nội dung được viết quá cụ thể.
- Danh sách type có thể làm lộ những phần API chưa được công bố rộng rãi hoặc những chức năng cũ vẫn còn trong schema.

Thông tin này có thể hỗ trợ reconnaissance và giúp việc dò tìm endpoint thuận tiện hơn. Tuy nhiên, tắt introspection không thay thế xác thực, phân quyền hoặc kiểm tra dữ liệu. Nếu một mutation quản trị vẫn gọi được mà không có quyền phù hợp, việc ẩn schema không giải quyết được lỗ hổng đó.

Vì vậy, cần đánh giá introspection cùng các lớp bảo vệ khác: authentication, authorization theo field, validation, giới hạn độ sâu/độ phức tạp query, rate limiting và logging.

## 4. Phân biệt introspection, GraphiQL và schema printer

Ba khả năng sau thường bị nhầm lẫn:

| Khả năng | Chức năng | Tác động khi tắt |
| --- | --- | --- |
| Introspection query | Cho phép query `__schema` và `__type` khám phá schema | Công cụ không thể tải schema qua introspection endpoint. |
| GraphiQL | Giao diện web để viết và chạy GraphQL query | Người dùng không còn giao diện GraphiQL tại đường dẫn đã cấu hình. |
| Schema printer | Xuất schema dưới dạng SDL qua endpoint riêng khi được bật | Client không thể tải SDL qua endpoint schema printer. |

Tắt GraphiQL không tự động tắt introspection. Ngược lại, tắt introspection cũng không nhất thiết làm biến mất giao diện GraphiQL nếu giao diện vẫn được phục vụ; tuy nhiên, phần tài liệu/schema explorer của nó có thể không tải được schema.

Schema printer cũng là một kênh xuất metadata riêng. Nếu bật endpoint này trong production, cần bảo vệ nó tương tự một endpoint cung cấp tài liệu API hoặc tắt nếu không có nhu cầu vận hành.

## 5. Cấu hình giao diện và schema printer theo môi trường

Spring Boot cung cấp thuộc tính để điều khiển GraphiQL và schema printer. Nên cấu hình rõ theo profile để tránh vô tình bật công cụ phát triển ở môi trường production.

Ví dụ `application-dev.properties`:

```properties
spring.graphql.graphiql.enabled=true
spring.graphql.schema.printer.enabled=true
```

Ví dụ `application-prod.properties`:

```properties
spring.graphql.graphiql.enabled=false
spring.graphql.schema.printer.enabled=false
spring.graphql.schema.introspection.enabled=false
```

Khi chạy production profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

`spring.graphql.schema.introspection.enabled=false` tắt khả năng introspection trong cấu hình auto-configuration Spring Boot. Mặc định introspection được cho phép vì các công cụ như GraphiQL cần khả năng này. Hai thuộc tính còn lại điều khiển GraphiQL và schema printer riêng biệt.

Không nên dựa vào profile để bảo vệ endpoint nếu profile có thể bị ghi đè ngoài ý muốn. Hãy xác nhận cấu hình cuối cùng trong môi trường triển khai, kiểm tra biến môi trường/command line và đưa trạng thái các endpoint hỗ trợ vào deployment verification.

## 6. Tắt introspection trong Spring Boot

Với ứng dụng dùng GraphQL auto-configuration mặc định, thuộc tính chính thức để tắt introspection là:

```properties
spring.graphql.schema.introspection.enabled=false
```

Khi thuộc tính này được áp dụng, các truy vấn introspection như `__schema` và `__type` không còn khả dụng. Hãy đặt thuộc tính trong profile production hoặc cấu hình triển khai tương ứng. Đừng chỉ tắt GraphiQL rồi kết luận schema đã được ẩn; cần cấu hình introspection riêng.

Nếu ứng dụng tự khai báo bean `GraphQlSource`, auto-configuration tạo `GraphQlSource` mặc định có thể không còn được sử dụng. Trong trường hợp đó, cần kiểm tra cách phiên bản Spring Boot đang dùng áp dụng thuộc tính introspection cho custom source và cấu hình tương đương trên đúng GraphQL runtime nếu cần. Không tạo một GraphQL instance riêng mà HTTP handler không sử dụng.

Sau khi cấu hình, luôn xác minh bằng request đến endpoint thật. Gửi cả query dùng `__schema` và query dùng `__type`; kiểm tra kết quả không thể lấy schema metadata trong profile production. Hành vi có thể khác nếu một bean tùy chỉnh thay thế auto-configuration.

Việc giới hạn introspection không đồng nghĩa xóa `__typename`. `__typename` là meta-field phục vụ việc xác định runtime object type và thường vẫn cần cho client xử lý interface/union, cache và fragment.

## 7. Chính sách introspection theo môi trường và đối tượng

Không có một chính sách duy nhất phù hợp với mọi hệ thống. Có thể cân nhắc các lựa chọn sau:

| Loại hệ thống | Chính sách gợi ý |
| --- | --- |
| Local development | Bật introspection và GraphiQL để khám phá schema nhanh. |
| CI/test | Cho phép introspection trong môi trường cô lập để kiểm thử contract và sinh client artifacts. |
| Internal staging | Chỉ mở cho người dùng hoặc mạng nội bộ được phép; có thể bật công cụ schema explorer theo nhu cầu. |
| Public production API | Đánh giá lợi ích cho developer ecosystem; nếu không cần, giới hạn introspection ở endpoint hoặc nhóm người dùng phù hợp. |
| Private production API | Ưu tiên yêu cầu authentication và giới hạn quyền truy cập schema metadata theo vai trò. |

Một số tổ chức vẫn cho phép introspection trên public API vì tài liệu và code generation là một phần của trải nghiệm nhà phát triển. Khi đó, schema cần được rà soát để description không chứa bí mật, thông tin nội bộ hoặc chi tiết không nên công bố. Các thao tác và field nhạy cảm vẫn phải được bảo vệ độc lập.

Với API riêng tư, có thể chỉ cho phép introspection từ tài khoản kỹ thuật hoặc mạng quản trị. Chính sách này cần được áp dụng ở request/runtime layer có thể xác thực principal, không chỉ dựa vào tên operation do client gửi lên. Nếu lọc operation bằng AST, cần xử lý fragment, alias và nhiều operation trong cùng document; so khớp chuỗi đơn giản dễ bị bỏ qua hoặc chặn nhầm.

## 8. Bảo vệ schema bằng nhiều lớp

Introspection chỉ là một phần của bề mặt API. Một cấu hình production nên kết hợp nhiều biện pháp:

1. **Authentication:** xác định danh tính người gọi bằng cơ chế phù hợp như session, OAuth2/JWT hoặc API gateway.
2. **Authorization:** kiểm tra quyền ở operation, field hoặc tầng service/domain; không dựa vào việc client không biết tên field.
3. **Input validation:** xác thực giá trị, giới hạn kích thước, miền số, định dạng và quan hệ giữa các input.
4. **Query depth và complexity:** giới hạn query lồng sâu hoặc yêu cầu quá nhiều dữ liệu trong một request.
5. **Rate limiting:** giới hạn tần suất request theo người dùng, token hoặc client.
6. **Timeout và giới hạn tài nguyên:** tránh query kéo dài chiếm worker, kết nối database hoặc bộ nhớ.
7. **Logging và monitoring:** ghi nhận lỗi, query bất thường và mức sử dụng endpoint mà không log thông tin nhạy cảm.
8. **Schema governance:** rà soát thay đổi, deprecation và mô tả schema trước khi phát hành.

Trong Spring Security, bảo vệ đường dẫn GraphQL ở HTTP layer là một lớp cần thiết, nhưng phân quyền theo field vẫn phải được áp dụng nếu các field trong cùng một operation có yêu cầu khác nhau. Một request có thể chứa nhiều field, vì vậy chỉ kiểm tra quyền truy cập URL `/graphql` là chưa đủ.

## 9. Quản lý schema mà không phụ thuộc production introspection

Nếu mục tiêu là tạo tài liệu, sinh client hoặc kiểm tra schema compatibility, không nhất thiết phải truy vấn production mỗi lần. Một quy trình CI/CD có thể:

- Lấy SDL từ source control hoặc artifact được build cùng phiên bản ứng dụng.
- Chạy kiểm tra schema syntax và validation trong CI.
- So sánh schema mới với phiên bản đã phát hành để phát hiện breaking change.
- Sinh client model và tài liệu từ SDL đã được review.
- Lưu schema artifact có version, commit hoặc build identifier.
- Kiểm tra schema đang chạy trong staging trước khi promote lên production.

Cách này giúp schema dùng bởi client và schema triển khai có nguồn gốc rõ ràng, đồng thời giảm nhu cầu cấp quyền introspection rộng trên production. Nếu vẫn cần xác minh runtime schema, có thể dùng một tài khoản kỹ thuật có quyền giới hạn và một bước kiểm tra được kiểm soát trong pipeline.

## 10. Kiểm thử chính sách introspection

Không nên chỉ kiểm tra file properties. Cần gửi request thực tế đến endpoint GraphQL để xác nhận hành vi cuối cùng.

Ví dụ truy vấn kiểm tra introspection:

```graphql
query IntrospectionCheck {
    __schema {
        queryType {
            name
        }
    }
}
```

Với môi trường cho phép introspection, response cần có `data.__schema.queryType.name`. Với môi trường đã tắt introspection, request phải bị từ chối theo chính sách và response chứa lỗi phù hợp. Cũng nên kiểm tra `__type(name: "Product")` để chắc rằng cả hai entry point introspection đều được xử lý.

Ví dụ kiểm thử bằng `GraphQlTester`:

```java
@Test
void introspectionIsRejectedWhenProductionPolicyDisablesIt() {
    graphQlTester.document("""
            query {
                __schema {
                    queryType { name }
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());
}
```

Test này giả định `graphQlTester` được cấu hình với production policy. Tên và chi tiết lỗi có thể khác theo GraphQL Java version; nên kiểm tra hành vi và error classification thay vì phụ thuộc vào toàn bộ message. Nếu policy cho phép một nhóm admin introspect, hãy kiểm thử cả người dùng được phép và người dùng không được phép.

Ngoài introspection, kiểm tra riêng:

- GraphiQL không được phục vụ trong production nếu đã tắt.
- Schema printer endpoint không được phục vụ nếu đã tắt.
- Query `__typename` vẫn hoạt động ở các object/interface/union nếu client cần.
- Các field nhạy cảm vẫn bị chặn khi người dùng không có quyền, kể cả khi họ biết tên field.
- Query sâu, query lớn và request lặp lại bị giới hạn theo chính sách vận hành.

## 11. Checklist trước khi đưa GraphQL vào production

1. Xác định ai cần đọc schema metadata và lý do cần introspection.
2. Quyết định introspection được mở công khai, giới hạn theo vai trò hay tắt ở runtime.
3. Cấu hình GraphiQL và schema printer riêng theo profile; không nhầm chúng với introspection.
4. Nếu tắt introspection, xác nhận thuộc tính hoặc cấu hình tùy chỉnh được áp dụng cho đúng GraphQL runtime mà Spring `GraphQlSource` đang sử dụng.
5. Giữ `__typename` nếu client cần runtime type information.
6. Bảo vệ operation và field bằng authentication/authorization độc lập.
7. Bật validation, query depth/complexity limits, rate limiting và timeout phù hợp.
8. Quản lý SDL trong source control/CI hoặc schema registry để không phải mở production introspection cho mọi công cụ.
9. Viết integration test cho `__schema`, `__type`, `__typename`, GraphiQL và schema printer.
10. Xác minh cấu hình thực tế sau khi deploy, bao gồm profile, environment variables và command-line overrides.

Schema introspection là công cụ mạnh để khám phá và tích hợp GraphQL API. Trong production, quyết định bật hay giới hạn cần dựa trên nhu cầu của client và mức độ công khai của schema. Dù chọn chính sách nào, bảo mật thực sự vẫn đến từ xác thực, phân quyền, giới hạn tài nguyên và quy trình quản trị schema được thực thi nhất quán.

Tài liệu tham khảo: [Spring Boot - Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html).
