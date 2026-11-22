# Bảo vệ introspection

GraphQL có cơ chế introspection cho phép client hỏi server về schema đang được triển khai: root query/mutation/subscription type, object type, field, argument, scalar, enum, directive, mô tả và trạng thái deprecated. Khả năng này giúp GraphQL tự mô tả và hỗ trợ công cụ như GraphiQL, nhưng cũng có thể làm lộ cấu trúc API nội bộ nếu mọi client đều được phép truy vấn schema.

Spring Boot mặc định cho phép field introspection. Spring for GraphQL cho phép tắt introspection ở cấp schema bằng `spring.graphql.schema.introspection.enabled=false`. GraphQL Java cũng hỗ trợ chính sách theo từng request thông qua `Introspection.INTROSPECTION_DISABLED` trong `GraphQLContext`. Nhờ đó, ứng dụng có thể tắt introspection toàn bộ ở môi trường production hoặc chỉ cho phép người dùng có role phù hợp xem schema.

Bài học này giải thích introspection hoạt động thế nào, cách tắt bằng cấu hình Spring Boot, cách áp dụng chính sách theo request, cách kiểm thử, và những giới hạn cần hiểu trước khi coi đây là một biện pháp hardening.

## 1. Introspection là gì?

Introspection là khả năng GraphQL cho phép client truy vấn metadata của chính schema. Hai meta-field chính là:

- `__schema`: trả về thông tin tổng thể của schema.
- `__type(name: String!)`: trả về thông tin về một type có tên cụ thể.

Ví dụ truy vấn root type:

```graphql
query InspectSchema {
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
  }
}
```

Ví dụ xem các field của một type:

```graphql
query InspectBook {
  __type(name: "Book") {
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
      }
    }
  }
}
```

Client có thể dùng introspection để:

- Khám phá những operation và field mà API cung cấp.
- Tìm kiểu input, argument, scalar và enum hợp lệ.
- Tạo tài liệu và client code.
- Hỗ trợ autocomplete, validation và schema explorer trong IDE.
- Phát hiện field đã deprecated cùng lý do deprecation.

GraphQL schema vì vậy không chỉ là hợp đồng giữa client và server; khi introspection được bật, server còn cung cấp một giao diện máy đọc được để khám phá hợp đồng đó.

## 2. Phân biệt __schema, __type và __typename

Không phải mọi field bắt đầu bằng hai dấu gạch dưới đều có cùng mục đích:

| Meta-field | Mục đích | Khi introspection bị tắt |
| --- | --- | --- |
| `__schema` | Khám phá toàn bộ schema | Bị chặn |
| `__type` | Khám phá một type theo tên | Bị chặn |
| `__typename` | Lấy tên runtime type của object hiện tại | Vẫn hoạt động |

`__typename` rất hữu ích khi client làm việc với interface, union hoặc cache normalized. Nó cho biết object cụ thể là type nào trong response:

```graphql
query BookDetails {
  bookById(id: "book-1") {
    __typename
    id
    title
  }
}
```

Ví dụ response:

```json
{
  "data": {
    "bookById": {
      "__typename": "Book",
      "id": "book-1",
      "title": "Spring for GraphQL"
    }
  }
}
```

Trong GraphQL Java, cơ chế tắt introspection kiểm tra các meta-field `__schema` và `__type`; `__typename` không phải truy vấn khám phá schema và vẫn được giữ lại. Không nên chặn tất cả field có prefix `__` bằng một field visibility rule tổng quát nếu ứng dụng vẫn cần `__typename`.

## 3. Vì sao cần bảo vệ introspection?

Khi introspection mở cho mọi người, client có thể khám phá:

- Tên type và field mà API công bố.
- Các mutation và input object.
- Field hoặc argument đã deprecated.
- Mô tả schema và quy tắc nullability.
- Những phần của API được thiết kế cho tích hợp nội bộ.

Thông tin này có thể giúp người kiểm thử và người dùng API hợp pháp, nhưng cũng giúp người tấn công hiểu bề mặt API nhanh hơn. Ví dụ, tên mutation quản trị, field chứa dữ liệu nhạy cảm hoặc luồng nghiệp vụ nội bộ có thể trở nên dễ phát hiện.

Tuy nhiên, introspection không phải là quyền truy cập dữ liệu. Tắt introspection không ngăn client gọi một field mà họ đã biết tên. Nếu resolver thiếu authorization, client vẫn có thể gọi field đó trực tiếp. Ngược lại, API được bảo vệ tốt ở tầng field vẫn có thể cho phép introspection mà không làm lộ dữ liệu nghiệp vụ.

Hãy xem tắt introspection là một lớp hardening bổ sung, kết hợp với:

- Authentication ở transport hoặc API gateway.
- Authorization tại field resolver, service và domain boundary.
- Giới hạn query depth, complexity, số lượng operation và thời gian thực thi.
- Rate limiting, logging và monitoring.
- Error message không tiết lộ stack trace hoặc thông tin nội bộ.

Không dựa vào việc ẩn schema như biện pháp bảo mật duy nhất.

## 4. Tắt introspection bằng Spring Boot

Spring Boot cung cấp property:

```yaml
spring:
  graphql:
    schema:
      introspection:
        enabled: false
```

Mặc định `spring.graphql.schema.introspection.enabled` là `true`. Đặt thành `false` để tắt field introspection khi Boot tạo GraphQL source.

Có thể tách cấu hình theo profile:

```yaml
# application-dev.yml
spring:
  graphql:
    schema:
      introspection:
        enabled: true
```

```yaml
# application-prod.yml
spring:
  graphql:
    schema:
      introspection:
        enabled: false
```

Trong development, introspection giúp GraphiQL và IDE khám phá schema. Trong production, quyết định bật hay tắt phụ thuộc mô hình API và nhu cầu của client. Nếu API công khai cần hỗ trợ code generation hoặc developer portal, có thể giữ introspection cho nhóm consumer được xác thực thay vì tắt tuyệt đối.

### Cấu hình application.properties

```properties
spring.graphql.schema.introspection.enabled=false
```

Property này điều khiển introspection ở cấp schema/runtime của GraphQL Java. Nó không xóa schema khỏi ứng dụng, không thay đổi SDL và không tự thêm authorization cho các field.

## 5. Tắt introspection theo từng request bằng GraphQLContext

Có trường hợp chỉ một số client hoặc role được phép khám phá schema:

- Developer hoặc schema reader được introspection.
- Người dùng thông thường không được introspection.
- API nội bộ và API public có thể áp dụng chính sách khác nhau.

GraphQL Java cung cấp key `Introspection.INTROSPECTION_DISABLED`. Đặt giá trị `true` trong `GraphQLContext` của một request để từ chối introspection trong request đó:

```java
import graphql.introspection.Introspection;

request.configureExecutionInput((executionInput, builder) ->
        builder.graphQLContext(context ->
                context.put(Introspection.INTROSPECTION_DISABLED, true))
                .build());
```

Đoạn code trên minh họa cách thêm cờ vào context của execution. Trong ứng dụng Spring for GraphQL, có thể thực hiện từ `WebGraphQlInterceptor` sau khi đã xác định danh tính và quyền của caller.

### Ví dụ WebGraphQlInterceptor với Spring Security WebFlux

Ví dụ sau chỉ cho phép người dùng có authority `ROLE_SCHEMA_READER` thực hiện introspection:

```java
import graphql.introspection.Introspection;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class IntrospectionAccessInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> authentication.getAuthorities().stream()
                        .anyMatch(authority ->
                                authority.getAuthority().equals("ROLE_SCHEMA_READER")))
                .defaultIfEmpty(false)
                .flatMap(allowed -> {
                    request.configureExecutionInput((executionInput, builder) ->
                            builder.graphQLContext(context ->
                                    context.put(
                                            Introspection.INTROSPECTION_DISABLED,
                                            !allowed))
                                    .build());
                    return chain.next(request);
                });
    }
}
```

Các điểm quan trọng:

1. Quyền được lấy từ Spring Security reactive context, không lấy từ một header tùy ý do client gửi.
2. Nếu không có authentication hoặc không có authority phù hợp, `allowed` là `false`.
3. `INTROSPECTION_DISABLED` nhận giá trị ngược với `allowed`.
4. Cờ được thêm vào GraphQLContext của đúng execution, nên request khác không dùng chung quyết định này.

Ví dụ giả định ứng dụng đã cấu hình Spring Security WebFlux và xác thực principal trước interceptor. Với Spring MVC, cách lấy SecurityContext khác WebFlux nhưng vẫn phải lấy từ context đã được Spring Security xác thực.

### Thứ tự ưu tiên giữa cấu hình toàn JVM và cờ request

GraphQL Java có hai mức kiểm soát:

| Mức | API | Phạm vi |
| --- | --- | --- |
| Toàn JVM | `Introspection.enabledJvmWide(false)` | Tắt introspection cho mọi GraphQL execution trong cùng JVM |
| Theo request | `Introspection.INTROSPECTION_DISABLED = true` | Tắt introspection cho một execution |

Hai mức này kết hợp theo hướng chỉ có thể hạn chế thêm:

- Nếu introspection bị tắt toàn JVM, request không thể bật lại bằng context.
- Nếu introspection được bật toàn JVM, request có thể tự tắt bằng `INTROSPECTION_DISABLED=true`.
- Nếu key không có hoặc là `false`, request dùng trạng thái toàn JVM.

`spring.graphql.schema.introspection.enabled=false` của Spring Boot sử dụng cơ chế tắt toàn cục của GraphQL Java. Vì vậy, nếu cần role-based introspection, không bật cờ JVM-wide `false`; hãy để global state bật và áp dụng quyết định theo từng request.

## 6. Kiểm soát GraphiQL và schema printer riêng biệt

Tắt field introspection không tự động tắt mọi endpoint hỗ trợ khám phá schema. Spring Boot có các endpoint phục vụ developer experience:

| Thành phần | Property | Mặc định |
| --- | --- | --- |
| GraphiQL UI | `spring.graphql.graphiql.enabled` | Tắt |
| Schema printer | `spring.graphql.schema.printer.enabled` | Tắt |
| Field introspection | `spring.graphql.schema.introspection.enabled` | Bật |

GraphiQL là giao diện web để gửi GraphQL operation, được phục vụ tại `/graphiql` theo mặc định khi bật. Nó thường cần introspection để tải schema và cung cấp autocomplete. Schema printer có thể trả schema dưới dạng SDL tại `/graphql/schema` khi được bật.

Trong production, nếu không cần các công cụ này, cấu hình tường minh:

```yaml
spring:
  graphql:
    graphiql:
      enabled: false
    schema:
      printer:
        enabled: false
      introspection:
        enabled: false
```

GraphiQL có thể được bật trong development qua cấu hình hoặc DevTools. Hãy kiểm tra profile production và endpoint thực tế sau khi triển khai; không giả định rằng tắt introspection cũng đồng nghĩa trang GraphiQL hoặc schema printer đã biến mất.

Nếu cần developer portal, nên đặt nó ở môi trường hoặc endpoint được xác thực riêng, và chỉ cấp quyền cho nhóm cần dùng.

## 7. Lưu ý khi tự cấu hình GraphQlSource

Property introspection của Spring Boot được áp dụng trong quá trình auto-configuration tạo `GraphQlSource`. Nếu ứng dụng tự khai báo bean `GraphQlSource`, auto-configuration có thể lùi lại và không chạy đoạn cấu hình introspection tương ứng ở một số phiên bản.

Vì vậy, khi dùng custom `GraphQlSource`:

1. Không chỉ dựa vào việc property xuất hiện trong `application.yml`.
2. Kiểm tra cấu hình thực tế của đúng phiên bản Spring Boot.
3. Gửi một introspection query trong integration test để xác nhận nó bị từ chối.
4. Nếu cần, áp dụng cơ chế GraphQL Java phù hợp trong cấu hình custom và giữ chính sách đó nhất quán cho mọi GraphQL execution.

Đây là một điểm cần kiểm chứng sau khi tùy biến auto-configuration; đừng để hệ thống báo cấu hình đã tắt nhưng runtime vẫn cho phép introspection.

## 8. Tránh các cách tắt introspection cũ

Một số ví dụ cũ dùng:

```java
NoIntrospectionGraphqlFieldVisibility.NO_INTROSPECTION_FIELD_VISIBILITY
```

hoặc gắn `NoIntrospectionGraphqlFieldVisibility` vào `GraphQLSchema.Builder.fieldVisibility(...)`.

Không nên dùng cách này trong code mới. `NoIntrospectionGraphqlFieldVisibility` đã deprecated trong GraphQL Java 22; GraphQL Java cung cấp `Introspection.enabledJvmWide(false)` và key `Introspection.INTROSPECTION_DISABLED` theo request để điều khiển trực tiếp việc thực thi introspection.

Các field visibility rule tổng quát có thể chặn cả meta-field mà client cần cho hoạt động bình thường như `__typename`, hoặc làm hành vi khác với cơ chế introspection guard hiện hành. Khi nâng cấp GraphQL Java, hãy kiểm tra Javadoc đúng version thay vì sao chép snippet cũ.

## 9. Introspection bị tắt không có nghĩa schema đã được bảo vệ hoàn toàn

Khi `__schema` và `__type` bị chặn, client không thể dùng hai meta-field đó để khám phá schema. Nhưng vẫn còn những cách khác để suy đoán bề mặt API:

- Gửi trực tiếp field name mà client đã biết hoặc đoán được.
- Quan sát error message và gợi ý tên field gần giống.
- Đọc tài liệu SDL đã được công bố ở nơi khác.
- Dùng client schema, code generation artifact hoặc API documentation đã lưu.
- Khám phá endpoint phụ do ứng dụng hoặc API gateway cung cấp.

Nếu không muốn lộ tên field qua gợi ý lỗi, hãy xem xét cách GraphQL Java và exception handling của ứng dụng tạo validation errors. Khả năng tắt field suggestions phụ thuộc GraphQL Java version và cấu hình validation; không mặc định rằng tắt introspection sẽ tự tắt suggestions.

Không đưa bí mật, credential, internal URL hoặc dữ liệu nhạy cảm vào schema description. Mô tả schema có thể được trả qua introspection hoặc schema printer trong môi trường cho phép truy cập.

### Good faith introspection

Một số phiên bản GraphQL Java có cơ chế `GoodFaithIntrospection` để giới hạn hình dạng và độ lớn của introspection query, chẳng hạn giới hạn depth hoặc số field. Cơ chế này nhằm kiểm soát các truy vấn introspection quá lớn hoặc có dấu hiệu lạm dụng; nó không tương đương với việc tắt introspection và không thay thế authorization.

Nếu sử dụng, hãy xem Javadoc đúng phiên bản GraphQL Java để biết mặc định và các giới hạn được hỗ trợ.

## 10. Kiểm thử chính sách introspection

Không nên chỉ kiểm tra property trong file cấu hình. Hãy gửi query tới GraphQL execution thực tế để xác nhận `__schema` và `__type` bị từ chối, trong khi các field nghiệp vụ và `__typename` vẫn hoạt động.

Ví dụ với `GraphQlTester`:

```java
@GraphQlTest(BookQueryController.class)
@TestPropertySource(properties = {
        "spring.graphql.schema.introspection.enabled=false"
})
class IntrospectionSecurityTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void rejectsSchemaIntrospection() {
        graphQlTester.document("""
                query {
                    __schema {
                        queryType {
                            name
                        }
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());
    }

    @Test
    void rejectsTypeIntrospection() {
        graphQlTester.document("""
                query {
                    __type(name: "Book") {
                        name
                        fields {
                            name
                        }
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());
    }

    @Test
    void keepsTypenameAvailable() {
        graphQlTester.document("""
                query {
                    bookById(id: "book-1") {
                        __typename
                    }
                }
                """)
                .execute()
                .errors()
                .verify()
                .path("bookById.__typename")
                .entity(String.class)
                .isEqualTo("Book");
    }
}
```

Ví dụ giả định schema có `Query.bookById`, dữ liệu `book-1` tồn tại và field trả về type `Book`. Thêm resolver/configuration phù hợp trong test context. Nếu chỉ muốn kiểm tra schema introspection, có thể dùng một query đơn giản không phụ thuộc dữ liệu nghiệp vụ.

`@GraphQlTest` tự cấu hình `GraphQlTester` để kiểm tra GraphQL execution mà không cần HTTP server. Nếu muốn kiểm tra HTTP endpoint, GraphiQL hoặc header/security filter, dùng `@SpringBootTest` kết hợp `@AutoConfigureHttpGraphQlTester` và `HttpGraphQlTester`. Property `spring.graphql.graphiql.enabled` và `spring.graphql.schema.printer.enabled` nên được xác minh thêm qua integration/smoke test ở transport thực tế.

### Kiểm thử role-based policy

Với interceptor theo role:

- Gửi `__schema` bằng user có `ROLE_SCHEMA_READER`; query phải thành công.
- Gửi cùng query bằng user không có role; query phải trả GraphQL error.
- Gửi query thông thường bằng cả hai user; kết quả phải tuân theo authorization của field, độc lập với introspection policy.
- Gửi request không có authentication; introspection phải bị tắt.

Điều này kiểm tra cả nhánh được phép lẫn nhánh mặc định từ chối. Nếu chỉ test user không có quyền, interceptor có thể vô tình tắt introspection cho tất cả mọi người mà không bị phát hiện.

### Kiểm tra endpoint phụ

Trong integration test hoặc deployment smoke test, xác nhận:

- `/graphiql` không được phục vụ nếu UI đã tắt.
- `/graphql/schema` không được phục vụ nếu schema printer đã tắt.
- HTTP GraphQL endpoint vẫn hoạt động cho query/mutation được phép.
- WebSocket hoặc transport khác không vô tình có chính sách introspection khác HTTP.

Lưu ý: `Introspection.enabledJvmWide(false)` là static state ở cấp JVM. Test nhiều Spring context trong cùng JVM với các cấu hình introspection khác nhau có thể ảnh hưởng lẫn nhau. Tránh bật/tắt flag global giữa các test song song; ưu tiên cấu hình cố định cho test suite hoặc kiểm thử per-request bằng GraphQLContext.

## 11. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đã đặt property false nhưng introspection vẫn chạy | Custom `GraphQlSource` khiến auto-configuration không áp dụng setting trong một số phiên bản | Kiểm tra runtime bằng integration test và cấu hình custom source |
| Developer có role vẫn không introspect được | Global JVM flag đã bị tắt | Không dùng global disable nếu cần role-based access |
| `__typename` cũng bị lỗi | Field visibility rule cũ chặn mọi field có prefix `__` | Dùng GraphQL Java `Introspection` guard thay cho rule tổng quát |
| GraphiQL vẫn mở được | Chỉ tắt field introspection, chưa tắt GraphiQL endpoint | Đặt `spring.graphql.graphiql.enabled=false` |
| Schema vẫn tải được qua URL khác | Schema printer hoặc endpoint phụ còn bật | Tắt schema printer và kiểm tra mọi transport |
| Introspection bị tắt nhưng field nhạy cảm vẫn truy cập được | Nhầm lẫn introspection với authorization | Thêm field/service authorization |
| Error vẫn gợi ý tên field | Validation error có thể đưa ra field suggestions | Kiểm tra error policy và GraphQL Java version |
| Test chạy độc lập pass nhưng chạy chung suite fail | JVM-wide static flag bị test khác thay đổi | Cô lập test hoặc dùng per-request context flag |
| Một số client không thể tạo schema cache | Client phụ thuộc introspection để tải schema | Cấp quyền cho schema reader hoặc phân phối SDL an toàn |

## 12. Nguyên tắc thiết kế chính sách introspection

- Quyết định rõ API có cần introspection cho developer portal, code generation và client tooling hay không.
- Dùng `spring.graphql.schema.introspection.enabled=false` khi muốn tắt ở cấp ứng dụng/JVM bằng auto-configuration Spring Boot.
- Dùng `Introspection.INTROSPECTION_DISABLED` trong GraphQLContext khi cần chính sách theo request hoặc role.
- Không kết hợp global disable với yêu cầu cho một số role được bật lại; global flag không thể được override bằng request context.
- Lấy role từ Spring Security đã xác thực; không tin một header hoặc GraphQL variable do client tự khai báo.
- Giữ `__typename` hoạt động cho client và normalized cache.
- Tắt GraphiQL và schema printer riêng nếu không cần chúng trong production.
- Kiểm tra cả HTTP, WebSocket và transport khác nếu cùng phục vụ một GraphQL schema.
- Không xem introspection disable là authorization; bảo vệ resolver và dữ liệu độc lập.
- Không để schema description chứa secret hoặc internal implementation detail.
- Kiểm thử query `__schema`, `__type`, `__typename`, field nghiệp vụ và endpoint phụ.
- Kiểm tra lại chính sách khi thay đổi Spring Boot hoặc GraphQL Java version.

## 13. Bài tập thực hành

Xây dựng chính sách introspection cho API thư viện:

1. Khai báo `Query.bookById` và type `Book` trong SDL.
2. Gửi query `__schema` và `__type` để quan sát metadata được trả về khi introspection bật.
3. Cấu hình `spring.graphql.schema.introspection.enabled=false`.
4. Gửi lại hai query trên và xác nhận GraphQL trả error.
5. Gửi query có `__typename` và xác nhận field vẫn hoạt động.
6. Tắt GraphiQL và schema printer trong profile production.
7. Viết `WebGraphQlInterceptor` chỉ cho authority `ROLE_SCHEMA_READER` được introspection.
8. Kiểm thử request có role, không có role và anonymous.
9. Kiểm tra query thông thường vẫn cần authorization riêng ở resolver.
10. Thử tạo custom `GraphQlSource` và xác nhận property introspection có tác dụng trong cấu hình thực tế.
11. Viết smoke test cho `/graphiql` và `/graphql/schema`.
12. Giải thích vì sao ẩn schema không thể thay thế authorization hoặc rate limiting.

Sau bài tập, bạn cần biết chọn global policy hay per-request policy, hiểu vai trò của `__typename`, và chứng minh chính sách bằng query thực tế thay vì chỉ đọc file cấu hình.

## 14. Tài liệu tham khảo

- [Spring Boot — Spring for GraphQL: Schema Introspection, GraphiQL and Schema Printer](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — Introspection API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/introspection/Introspection.html)
- [GraphQL Java — NoIntrospectionGraphqlFieldVisibility](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/visibility/NoIntrospectionGraphqlFieldVisibility.html)
- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [OWASP GraphQL Cheat Sheet — Introspection and GraphiQL](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)

`Introspection`, field visibility API và auto-configuration có thể thay đổi theo phiên bản GraphQL Java và Spring Boot. Đặc biệt, `NoIntrospectionGraphqlFieldVisibility` đã deprecated trong GraphQL Java 22; hãy ưu tiên API `Introspection` và kiểm tra Javadoc đúng version mà Spring Boot quản lý.
