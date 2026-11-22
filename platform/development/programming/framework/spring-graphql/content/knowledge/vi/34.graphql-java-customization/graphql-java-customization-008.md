# PreparsedDocumentProvider

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao GraphQL Java phải parse và validate document trước khi thực thi.
- Mô tả vai trò của PreparsedDocumentProvider và PreparsedDocumentEntry.
- Phân biệt document cache với response cache và DataLoader cache.
- Cấu hình PreparsedDocumentProvider trong Spring for GraphQL thông qua GraphQlSourceBuilderCustomizer.
- Tạo cache có giới hạn bằng Caffeine và dùng API getDocumentAsync hiện hành.
- Hiểu vì sao GraphQL variables giúp tăng cache hit ratio.
- Phân biệt query caching, Automatic Persisted Queries (APQ) và operation allowlist.
- Quản lý cache khi schema, validation rule hoặc phiên bản GraphQL Java thay đổi.
- Kiểm thử cache hit, cache miss, invalid document và hành vi thực thi mỗi request.
- Tránh cache không giới hạn, bỏ qua validation instrumentation hoặc làm rò rỉ quy tắc truy cập giữa các context.

## Vì sao GraphQL cần parse và validate?

Khi server nhận một GraphQL request, phần query text là một chuỗi ký tự. GraphQL Java phải chuyển chuỗi đó thành cấu trúc cú pháp và xác minh cấu trúc này phù hợp với schema trước khi gọi data fetcher.

Ví dụ:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

Trước khi thực thi, engine phải:

1. Parse document thành Abstract Syntax Tree (AST).
2. Kiểm tra field book có tồn tại trong Query hay không.
3. Kiểm tra argument id và kiểu ID! có hợp lệ hay không.
4. Kiểm tra các field lồng nhau như title, author và name.
5. Kiểm tra variable $id được khai báo và sử dụng đúng kiểu.
6. Chỉ khi document hợp lệ, engine mới chuyển sang chọn operation, coerce variables và thực thi các field.

Parse và validate là công việc lặp lại nếu client gửi cùng document nhiều lần. Với API có operation ổn định và tần suất request cao, chi phí CPU này có thể đáng kể dù resolver và database rất nhanh.

## PreparsedDocumentProvider là gì?

GraphQL Java cung cấp interface PreparsedDocumentProvider để ứng dụng can thiệp vào bước lấy document đã parse và validate. Provider có thể:

- Trả về PreparsedDocumentEntry đã có trong cache.
- Gọi callback parse/validate khi cache miss.
- Từ chối operation không nằm trong danh sách cho phép.
- Tích hợp cơ chế persisted query theo ID hoặc hash.

Nếu ứng dụng không cấu hình provider cache hoặc persisted query riêng, GraphQL Java dùng provider không cache và phải parse/validate document lại ở các request tiếp theo.

GraphQL Java gọi provider trước khi thực thi operation. Provider nhận hai tham số:

- ExecutionInput: request hiện tại, bao gồm query text, operation name, variables và extensions.
- parseAndValidateFunction: callback để GraphQL Java parse và validate request nếu provider chưa có entry tương ứng.

Với API hiện hành của GraphQL Java, phương thức là:

~~~java
CompletableFuture<PreparsedDocumentEntry> getDocumentAsync(
        ExecutionInput executionInput,
        Function<ExecutionInput, PreparsedDocumentEntry> parseAndValidateFunction);
~~~

PreparsedDocumentEntry biểu diễn kết quả của bước parse và validation. Entry có thể chứa:

- Document đã parse và không có validation error.
- Document đã parse nhưng có validation error.
- Danh sách lỗi parse hoặc validation khi không tạo được document.

Khi document hợp lệ được tìm thấy trong cache, GraphQL Java có thể dùng lại AST và bỏ qua việc parse/validate lại. Khi không có entry, provider phải gọi callback để engine thực hiện đúng pipeline parse và validation.

Điểm quan trọng: callback này không chỉ parse và validate. Nó còn chạy các instrumentation liên quan tới parse/validation. Nếu cache miss mà provider tự tạo một Document hoặc trả entry giả, các bước kiểm tra và instrumentation tương ứng có thể bị bỏ qua. [GraphQL Java – PreparsedDocumentProvider API](https://www.javadoc.io/static/com.graphql-java/graphql-java/22.4/graphql/execution/preparsed/PreparsedDocumentProvider.html)

## Document cache không phải response cache

PreparsedDocumentProvider chỉ tái sử dụng kết quả parse/validation. Mỗi request vẫn thực thi data fetcher và tạo response mới.

| Cơ chế | Thứ được lưu | Phạm vi thường gặp |
| --- | --- | --- |
| PreparsedDocumentProvider | AST và kết quả parse/validation | Dùng lại giữa các request có cùng document |
| DataLoader cache | Kết quả tải entity theo key | Thường giới hạn trong một GraphQL request |
| Application/data cache | Dữ liệu domain như Product hoặc Author | Theo chính sách cache của ứng dụng |
| HTTP/response cache | Response đã hoàn thiện | Phụ thuộc URL, variables, identity, headers và cache policy |

Ví dụ, cùng query book(id: $id) được gửi 1.000 lần với các giá trị $id khác nhau:

- PreparsedDocumentProvider có thể dùng lại cùng AST.
- Data fetcher book vẫn chạy cho mỗi request.
- Repository vẫn được gọi theo logic của ứng dụng, trừ khi có data cache riêng.
- Response của từng người dùng vẫn được tạo riêng.

Không dùng document cache để giả định rằng dữ liệu đã được tải hoặc authorization đã được thực hiện. Resolver, service và security policy vẫn phải chạy theo từng request.

## Query text, operation name và variables

Cache document thường dùng query text làm key. Điều đó có nghĩa hai document chỉ khác literal value vẫn có thể tạo hai cache entry:

~~~graphql
query {
  book(id: "book-101") {
    title
  }
}
~~~

~~~graphql
query {
  book(id: "book-202") {
    title
  }
}
~~~

Hai query trên có cấu trúc gần giống nhau nhưng query text khác nhau. Cache theo raw query text sẽ xem chúng là hai key khác nhau.

Hãy đưa giá trị thay đổi vào variables:

~~~graphql
query BookTitle($id: ID!) {
  book(id: $id) {
    title
  }
}
~~~

Request thứ nhất:

~~~json
{
  "query": "query BookTitle($id: ID!) { book(id: $id) { title } }",
  "variables": {
    "id": "book-101"
  }
}
~~~

Request thứ hai dùng cùng query text nhưng variables khác:

~~~json
{
  "query": "query BookTitle($id: ID!) { book(id: $id) { title } }",
  "variables": {
    "id": "book-202"
  }
}
~~~

Document có thể được tái sử dụng trong khi giá trị variables vẫn được coerce và sử dụng ở mỗi lần thực thi.

Operation name và variables không cần nằm trong cache key của một document cache thông thường vì chúng không làm thay đổi cấu trúc document được parse. Nếu một document có nhiều operation, GraphQL Java vẫn chọn operation theo operationName ở bước thực thi.

Whitespace, comment, alias, fragment và literal argument đều nằm trong query text. Nếu cache dùng raw query text thì các cách viết khác nhau của cùng một ý nghĩa có thể tạo nhiều entry. Không nên tự canonicalize query bằng thao tác chuỗi đơn giản; việc chuẩn hóa phải bảo toàn semantics của GraphQL document.

## Cấu hình trong Spring for GraphQL

Spring for GraphQL cho phép đăng ký PreparsedDocumentProvider thông qua GraphQlSource.Builder#configureGraphQl. Trong Spring Boot, cách thông thường là khai báo một bean GraphQlSourceBuilderCustomizer.

Ví dụ dưới đây dùng Spring Boot 4.x:

~~~java
import graphql.execution.preparsed.PreparsedDocumentProvider;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlDocumentCacheConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer preparsedDocumentCustomizer(
            PreparsedDocumentProvider provider) {

        return builder -> builder.configureGraphQl(graphQLBuilder ->
                graphQLBuilder.preparsedDocumentProvider(provider));
    }
}
~~~

Spring Boot 3.x dùng package org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer. API tùy chỉnh vẫn theo cùng cách: nhận builder và gọi configureGraphQl.

Boot starter tạo GraphQlSource builder, nạp schema resources và phát hiện các bean customizer. Không cần tự tạo một GraphQL instance riêng chỉ để đăng ký provider. Nếu ứng dụng tự xây dựng GraphQlSource, hãy gọi configureGraphQl trên builder tương ứng trước khi build.

## Tạo document cache bằng Caffeine

GraphQL Java không bắt buộc dùng một thư viện cache cụ thể. Có thể dùng Caffeine, cache nội bộ hoặc một implementation phù hợp với môi trường chạy.

Thêm dependency Caffeine:

~~~groovy
dependencies {
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Ví dụ provider dùng Caffeine:

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import graphql.ExecutionInput;
import graphql.execution.preparsed.PreparsedDocumentEntry;
import graphql.execution.preparsed.PreparsedDocumentProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PreparsedDocumentCacheConfiguration {

    @Bean
    PreparsedDocumentProvider preparsedDocumentProvider() {
        Cache<String, PreparsedDocumentEntry> cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterAccess(Duration.ofMinutes(30))
                .recordStats()
                .build();

        return (executionInput, parseAndValidateFunction) -> {
            String query = executionInput.getQuery();

            if (query == null || query.isBlank()) {
                PreparsedDocumentEntry entry =
                        parseAndValidateFunction.apply(executionInput);
                return CompletableFuture.completedFuture(entry);
            }

            PreparsedDocumentEntry entry = cache.get(
                    query,
                    key -> parseAndValidateFunction.apply(executionInput));

            // Không giữ lâu document lỗi do client gửi sai query.
            if (entry.hasErrors()) {
                cache.invalidate(query);
            }

            return CompletableFuture.completedFuture(entry);
        };
    }
}
~~~

Trong ví dụ:

- Cache key là query text.
- maximumSize(10_000) giới hạn số entry để tránh tăng bộ nhớ không kiểm soát.
- expireAfterAccess(30 phút) loại entry không được sử dụng trong một khoảng thời gian.
- recordStats() cho phép quan sát hit, miss, eviction và các thống kê cache.
- Cache chỉ giữ entry không có lỗi parse/validation.
- Cache miss gọi parseAndValidateFunction để GraphQL Java thực hiện pipeline chuẩn.

Cache được tạo một lần và chia sẻ giữa các request. Caffeine hỗ trợ truy cập đồng thời; không tạo cache mới bên trong mỗi lần gọi getDocumentAsync.

Số lượng 10.000 và thời gian 30 phút chỉ là ví dụ. Hãy chọn theo số operation thực tế, kích thước AST, lượng heap và tỷ lệ query text khác nhau. Cache lớn không mặc nhiên nhanh hơn nếu phần lớn request chỉ xuất hiện một lần.

### Vì sao cần giới hạn cache?

Nếu server cache mọi query text mà không giới hạn, client có thể gửi liên tục các document khác nhau. Mỗi document có thể chiếm một entry dù không bao giờ được sử dụng lại. Đây là dạng tăng cardinality và có thể làm heap tăng không cần thiết.

Các biện pháp cần cân nhắc:

- Đặt maximum size và expiry.
- Theo dõi hit ratio, miss rate và eviction.
- Giới hạn kích thước query text ở transport/request layer.
- Dùng persisted query hoặc allowlist nếu client chỉ được phép chạy operation đã duyệt.
- Không cache lâu các parse/validation error do query tùy ý gửi lên.
- Theo dõi lượng document duy nhất trong một khoảng thời gian.

Không nên tăng cache size chỉ vì thấy nhiều miss. Trước hết hãy xác định query text có ổn định hay đang bị sinh khác nhau do literal values, whitespace hoặc client tự tạo operation.

## Cách provider hoạt động qua cache miss và cache hit

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[PreparsedDocumentProvider]
    B --> C{Query text in cache?}
    C -->|Yes| D[Reuse PreparsedDocumentEntry]
    C -->|No| E[parseAndValidateFunction]
    E --> F[Parse AST and validate schema]
    F --> G[Create PreparsedDocumentEntry]
    G --> H{Has errors?}
    H -->|Yes| I[Return errors, do not retain]
    H -->|No| J[Store entry in bounded cache]
    J --> D
    D --> K[Select operation and coerce variables]
    I --> L[Return request errors]
    K --> M[Execute data fetchers]
    M --> N[Build response]
~~~

**Cache miss:** provider gọi callback. GraphQL Java parse document, validate với schema và trả về PreparsedDocumentEntry. Provider lưu entry hợp lệ rồi trả future cho engine.

**Cache hit:** provider trả lại entry đã có. Engine có thể bỏ qua parse và validation, sau đó tiếp tục xử lý operation name, variables và data fetcher cho request hiện tại.

**Document lỗi:** ví dụ query có field không tồn tại hoặc sai cú pháp. Provider trả lỗi để GraphQL Java tạo request error; ví dụ Caffeine phía trên xóa entry lỗi để client không thể làm đầy cache bằng các query sai khác nhau.

## Persisted query và APQ

Document cache dùng query text làm key. Persisted query cho phép client tham chiếu một document bằng ID hoặc hash, thay vì gửi toàn bộ query text ở mọi request.

GraphQL Java có các implementation trong package graphql.execution.preparsed.persisted:

- PersistedQuerySupport: nền tảng cho persisted query.
- ApolloPersistedQuerySupport: hỗ trợ định dạng Automatic Persisted Queries của Apollo.
- PersistedQueryCache: abstraction cho cache query đã đăng ký.
- InMemoryPersistedQueryCache: cache persisted query trong bộ nhớ.

Spring for GraphQL minh họa cấu hình APQ như sau:

~~~java
import graphql.execution.preparsed.PreparsedDocumentProvider;
import graphql.execution.preparsed.persisted.ApolloPersistedQuerySupport;
import graphql.execution.preparsed.persisted.InMemoryPersistedQueryCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Collections;

@Configuration(proxyBeanMethods = false)
public class ApolloPersistedQueryConfiguration {

    @Bean
    PreparsedDocumentProvider preparsedDocumentProvider() {
        return new ApolloPersistedQuerySupport(
                new InMemoryPersistedQueryCache(Collections.emptyMap()));
    }
}
~~~

Đây là một cách cấu hình thay thế cho Caffeine document cache ở trên. Không khai báo hai bean cùng kiểu PreparsedDocumentProvider nếu chưa có chiến lược kết hợp rõ ràng.

Với APQ, client gửi query hash trong extensions. Khi server đã biết hash, server lấy document từ persisted query cache. Trong quy trình automatic persistence, client có thể gửi query text cùng hash khi cache miss để server parse, validate và lưu document; các request sau chỉ cần gửi hash.

### APQ không đồng nghĩa với allowlist

Hai khái niệm thường bị nhầm:

| Cơ chế | Cách hoạt động | Mục đích |
| --- | --- | --- |
| Document cache | Client gửi query text; server cache kết quả parse/validation theo query text | Giảm parse/validation lặp lại |
| APQ | Client gửi hash; server tra cứu hoặc nhận query text để đăng ký khi miss | Giảm kích thước request và tái sử dụng document |
| Operation allowlist | Server chỉ chấp nhận ID/document đã được đăng ký trước | Giới hạn tập operation client được phép thực thi |

APQ theo kiểu automatic có thể chấp nhận query text mới khi client gửi lại trong lần cache miss. Vì vậy, APQ một mình không phải chính sách chỉ cho phép operation đã duyệt.

Nếu API cần allowlist nghiêm ngặt, chỉ nạp trước những operation đã được review và từ chối ID không tồn tại. Không bật đường đăng ký query tùy ý từ client. Cần kiểm tra cả hash và nội dung document theo chính sách của ứng dụng.

Trong môi trường nhiều instance, InMemoryPersistedQueryCache là cache riêng của từng process. Có thể dùng cache dùng chung hoặc phát hành cùng một danh sách persisted operation cho mọi instance để tránh trạng thái khác nhau giữa các node. [GraphQL Java – Persisted Query Support](https://www.javadoc.io/static/com.graphql-java/graphql-java/22.4/graphql/execution/preparsed/persisted/ApolloPersistedQuerySupport.html)

## Cache key và ranh giới schema

Một cache entry chỉ hợp lệ trong ngữ cảnh schema và validation policy mà nó được tạo ra.

Với một GraphQlSource dùng schema cố định, cache gắn với provider của GraphQL instance đó thường đủ. Khi schema thay đổi và GraphQlSource được build lại, provider/cache mới cũng nên được tạo hoặc namespace theo schema version.

Không dùng chung một cache entry chỉ dựa vào query text nếu kết quả validation phụ thuộc vào:

- Schema khác nhau theo tenant hoặc theo phiên bản API.
- Field visibility thay đổi theo principal.
- Validation rule thay đổi theo client, tenant hoặc quyền.
- Custom instrumentation đưa ra quyết định validation dựa trên GraphQLContext hoặc request state.

Trong các trường hợp đó, cache key cần bao gồm dimension ảnh hưởng tới validation, hoặc không cache qua các context khác nhau. Một lựa chọn khác là chỉ cache AST parse được ở tầng riêng, rồi vẫn chạy validation phù hợp theo request nếu kiến trúc hỗ trợ điều đó.

Authorization dữ liệu vẫn phải được kiểm tra trong resolver/service theo mỗi request. PreparsedDocumentProvider không phải nơi để cache quyết định người dùng có quyền đọc một Product hoặc gọi một field hay không.

## Parse/validation instrumentation và custom validation

Callback parseAndValidateFunction được GraphQL Java cung cấp để provider thực hiện đúng bước parse và validation. Khi cache miss, luôn gọi callback thay vì tự parse AST rồi tạo entry bằng tay.

Khi cache hit, engine có thể không chạy lại parse/validation. Vì vậy:

- Instrumentation đo riêng thời gian parse/validation sẽ chủ yếu phản ánh cache miss.
- Instrumentation đo execution và data fetcher vẫn cần được cấu hình để quan sát phần thực thi.
- Custom validation có tính động phải được xem xét trước khi bật cache dùng chung.
- Khi thay đổi schema hoặc validation rule, cần invalidation hoặc tạo cache namespace mới.

Nếu một custom validation rule kiểm tra quyền dựa trên request context, không lưu kết quả validation của user A để dùng cho user B chỉ vì query text giống nhau. Hãy đưa context ảnh hưởng validation vào cache key hoặc để validation chạy lại theo request.

## Kiểm thử PreparsedDocumentProvider

Nên kiểm thử provider ở hai lớp:

**Unit test cho cache provider**

- Cùng query text được gửi hai lần thì callback parse/validation chỉ chạy một lần trong trường hợp entry hợp lệ còn trong cache.
- Query text khác nhau tạo entry khác nhau.
- Query lỗi không được giữ lâu trong cache.
- Entry bị eviction sau khi vượt maximum size hoặc hết expiry.
- Query rỗng/null đi qua nhánh không cache.

**Integration test qua GraphQL**

Thêm dependency test nếu module chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
~~~

- Gửi cùng document với hai bộ variables khác nhau; kết quả phải phản ánh variables của từng request.
- Data fetcher vẫn được gọi ở mỗi request, chứng minh document cache không phải response cache.
- Query field không tồn tại vẫn trả validation error.
- Khi schema thay đổi, provider/cache mới phải validate theo schema mới.
- Nếu dùng persisted query, kiểm tra hash đã đăng ký, hash không tồn tại và cache miss có query text.

Ví dụ kiểm tra hành vi variables:

~~~java
@Test
void reusesDocumentButExecutesWithCurrentVariables() {
    graphQlTester.document("""
            query BookTitle($id: ID!) {
                book(id: $id) {
                    title
                }
            }
            """)
            .variable("id", "book-101")
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("GraphQL Basics");

    graphQlTester.document("""
            query BookTitle($id: ID!) {
                book(id: $id) {
                    title
                }
            }
            """)
            .variable("id", "book-202")
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

Test này giả định graphQlTester đã được cấu hình và dữ liệu fixture chứa hai sách. Để xác minh callback chỉ chạy một lần, có thể bọc PreparsedDocumentProvider hoặc callback bằng counter trong unit test và assert số lần parse/validation. Không dùng thời gian response làm bằng chứng duy nhất vì JIT, connection pool và cache khác cũng ảnh hưởng kết quả.

## Quan sát hiệu quả cache

Đừng bật cache rồi mặc định rằng hiệu năng đã tốt hơn. Hãy đo trước và sau:

- Hit ratio: bao nhiêu request dùng lại entry đã có.
- Miss rate: bao nhiêu document phải parse/validate.
- Eviction: entry bị loại do giới hạn size hoặc expiry.
- Kích thước cache và heap sử dụng.
- Thời gian parse/validation khi miss.
- Tổng thời gian GraphQL request và thời gian data fetcher.

Một hit ratio thấp có thể do client gửi query text thay đổi liên tục, literal argument được nhúng trong document hoặc operation được sinh động. Chuyển giá trị biến đổi sang variables và chuẩn hóa operation ở client thường cải thiện kết quả.

Nếu phần lớn độ trễ đến từ database hoặc downstream service, document cache có thể chỉ cải thiện một phần nhỏ. Hãy xem nó như một tối ưu cho giai đoạn parse/validation, không phải cách chữa N+1 hay resolver chậm.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cache hit thấp dù cùng một nghiệp vụ | Client sinh query text khác nhau hoặc nhúng literal values | Dùng variables và tái sử dụng operation document |
| Heap tăng theo thời gian | Cache không có maximum size/expiry | Dùng bounded cache và theo dõi eviction |
| Query sai cú pháp được giữ lâu | Cache cả PreparsedDocumentEntry có lỗi | Không lưu hoặc đặt TTL rất ngắn cho entry lỗi |
| Validation instrumentation không chạy ở request hit | Document được tái sử dụng nên parse/validation không lặp lại | Hiểu rõ phạm vi instrumentation và đo execution riêng |
| Cache dùng document đã validate cho schema cũ | Cache sống lâu hơn GraphQlSource/schema | Tạo cache mới hoặc namespace theo schema version |
| User ít quyền dùng được field đã validate bởi user khác | Validation phụ thuộc principal nhưng cache key chỉ là query text | Không chia sẻ cache theo query đơn thuần hoặc đưa context vào key |
| APQ bị xem như allowlist | Server vẫn cho đăng ký query text mới khi cache miss | Dùng danh sách operation được nạp trước và từ chối unknown ID |
| Hai node có trạng thái persisted query khác nhau | Dùng in-memory cache riêng từng process | Dùng shared cache hoặc phát hành cùng allowlist |
| Cache hit nhưng database vẫn được gọi | Document cache không lưu response hay domain data | Dùng data cache/DataLoader nếu phù hợp |
| Parse/validation instrumentation biến mất trên cache miss | Provider không gọi parseAndValidateFunction | Luôn gọi callback do GraphQL Java truyền vào |
| Query text không có trong ExecutionInput | Request dùng persisted query hoặc payload không có query | Dùng persisted-query-aware provider, không dùng plain text cache thay thế |

## Thực hành tổng hợp

Tích hợp document caching cho API thư viện:

1. Tạo GraphQL operation BookTitle($id: ID!) với argument dùng variable.
2. Thêm Caffeine dependency theo dependency management của Spring Boot.
3. Viết PreparsedDocumentProvider dùng cache có maximum size và expiry.
4. Khi cache miss, gọi parseAndValidateFunction và trả PreparsedDocumentEntry.
5. Không giữ entry có parse/validation errors trong cache lâu dài.
6. Đăng ký provider qua GraphQlSourceBuilderCustomizer và configureGraphQl.
7. Gửi cùng document với hai bộ variables khác nhau và xác minh response khác nhau.
8. Dùng counter trong unit test để xác minh parse/validation callback chỉ chạy khi miss.
9. Gửi document lỗi và xác minh GraphQL vẫn trả request error.
10. Đo hit ratio, miss, eviction và thời gian parse/validation.
11. Thử ApolloPersistedQuerySupport để nhận operation bằng hash.
12. Nếu cần allowlist, chỉ đăng ký trước operation đã duyệt và kiểm tra unknown ID bị từ chối.
13. Tạo schema version mới và xác minh cache cũ không được dùng lại sai ngữ cảnh.

Sau khi hoàn thành, hãy giải thích vì sao variables giúp cache hit cao, vì sao PreparsedDocumentProvider không giảm số lần gọi resolver và vì sao APQ không mặc nhiên là allowlist.

## Ghi nhớ

PreparsedDocumentProvider cho phép GraphQL Java tái sử dụng document đã parse và validate. Nó giảm chi phí parse/validation nhưng không cache response hoặc dữ liệu resolver. Với API hiện hành, implement getDocumentAsync và luôn gọi parseAndValidateFunction khi cache miss để giữ nguyên pipeline validation cùng instrumentation. Trong Spring Boot, đăng ký provider qua GraphQlSourceBuilderCustomizer và GraphQlSource.Builder#configureGraphQl. Dùng variables thay literal values để tái sử dụng cùng query text. Cache cần giới hạn size/expiry, quản lý entry lỗi và gắn với schema/validation context phù hợp. APQ giúp client gửi hash của operation; allowlist cần chính sách từ chối operation chưa đăng ký. Kiểm thử cả cache hit/miss, variables, validation errors, schema change và hành vi resolver mỗi request.

## Tài liệu tham khảo

- [Spring for GraphQL – Request Execution, Operation Caching](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java v25 – Execution and Query Caching](https://graphql-java.com/documentation/execution/)
- [GraphQL Java – PreparsedDocumentProvider API](https://www.javadoc.io/static/com.graphql-java/graphql-java/22.4/graphql/execution/preparsed/PreparsedDocumentProvider.html)
- [GraphQL Java – PreparsedDocumentEntry API](https://www.javadoc.io/static/com.graphql-java/graphql-java/0.0.0-2026-03-04T15-19-42-5b63591/graphql/execution/preparsed/PreparsedDocumentEntry.html)
- [GraphQL Java – ApolloPersistedQuerySupport API](https://www.javadoc.io/static/com.graphql-java/graphql-java/0.0.0-2026-03-04T15-19-42-5b63591/graphql/execution/preparsed/persisted/ApolloPersistedQuerySupport.html)
- [Spring Boot 4 – GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlSourceBuilderCustomizer.html)
