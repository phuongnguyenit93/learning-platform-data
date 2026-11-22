# DataLoader cache theo request trong Spring for GraphQL

DataLoader không chỉ gom nhiều lần tải dữ liệu thành một batch mà còn lưu kết quả đã tải trong một cache memoization theo request. Khi cùng một key được yêu cầu nhiều lần trong một GraphQL execution, DataLoader có thể trả lại cùng future đã tạo trước đó mà không đưa key đó vào batch loader lần nữa.

Trong Spring for GraphQL, `BatchLoaderRegistry` đăng ký các batch loading function ở cấp ứng dụng, còn các `DataLoader` thực tế được tạo và đăng ký vào `DataLoaderRegistry` riêng cho từng request. Nhờ đó, cache mặc định chỉ tồn tại trong phạm vi GraphQL request, tránh chia sẻ dữ liệu đã tải giữa những request có người dùng hoặc quyền truy cập khác nhau.

## 1. DataLoader cache theo request giải quyết vấn đề gì?

Giả sử một GraphQL query lấy nhiều bài viết, mỗi bài có một tác giả:

```graphql
query {
    posts {
        id
        title
        author {
            id
            name
        }
    }
}
```

Nếu cùng một tác giả xuất hiện trong nhiều bài viết, resolver có thể gọi `load("author-1")` nhiều lần. Nếu không có cache, cùng một key có thể bị đưa vào batch loader nhiều lần hoặc gây nhiều lần tải dữ liệu ở các thời điểm khác nhau.

DataLoader cache kết quả theo key trong một request. Ví dụ:

```text
GraphQL request R1
  load(author-1)  -> cache miss, xếp vào batch
  load(author-2)  -> cache miss, xếp vào batch
  load(author-1)  -> cache hit, dùng lại future trước
  load(author-1)  -> cache hit, dùng lại future trước
                 |
                 v
       Batch loader nhận author-1, author-2
```

Cache giúp loại bỏ các lần tải trùng key trong cùng request. Batch loading gom các key khác nhau vào một lần tải; hai cơ chế phối hợp với nhau nhưng có mục đích khác nhau.

## 2. Phạm vi cache trong Spring for GraphQL

Spring for GraphQL có hai thành phần tên gần giống nhau nhưng vai trò khác nhau:

| Thành phần | Phạm vi | Trách nhiệm |
|---|---|---|
| `BatchLoaderRegistry` | Thành phần đăng ký ở cấp ứng dụng | Lưu các hàm batch loader và cấu hình DataLoader. |
| `DataLoaderRegistry` | Từng GraphQL request/execution | Chứa các DataLoader instance được tạo cho request đó. |
| `DataLoader` | Từng registry/request | Queue key, dispatch batch và memoize kết quả theo key. |

Spring Boot cung cấp bean `BatchLoaderRegistry`. `DefaultExecutionGraphQlService` sử dụng registry này để đăng ký các DataLoader vào `DataLoaderRegistry` riêng cho mỗi request. Do đó, batch loader function có thể được khai báo một lần, nhưng cache của DataLoader không phải cache singleton dùng chung cho mọi request.

Vòng đời khái quát:

```text
Ứng dụng khởi động
       |
       v
BatchLoaderRegistry giữ các registration
       |
       +-------------------------------+
       |                               |
       v                               v
GraphQL request A                 GraphQL request B
       |                               |
       v                               v
DataLoaderRegistry A              DataLoaderRegistry B
       |                               |
       v                               v
DataLoader cache A                DataLoader cache B
       |                               |
       v                               v
Kết thúc execution                 Kết thúc execution
       |                               |
       v                               v
Cache A hết phạm vi                Cache B hết phạm vi
```

Không lưu `DataLoader` instance vào field của `@Controller`, `@Service` singleton hoặc biến static. Hãy để Spring đăng ký loader qua `BatchLoaderRegistry` và inject DataLoader vào method argument của data fetcher khi cần.

`@BatchMapping` là shortcut của Spring for GraphQL cho việc đăng ký DataLoader và ánh xạ field theo batch. Cache của mapping này cũng thuộc DataLoader instance của request; không có một cache `@BatchMapping` dùng chung giữa các request.

## 3. Caching được bật mặc định

Trong GraphQL Java `DataLoaderOptions`, caching future được bật mặc định. Khi gọi `load(key)` lần đầu, DataLoader tạo future và ghi future đó vào cache. Các lần gọi tiếp theo với cùng cache key có thể nhận lại future đã lưu.

Ví dụ với Java API:

```java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;

DataLoader<String, Author> loader = ...;

CompletableFuture<Author> first = loader.load("author-1");
CompletableFuture<Author> second = loader.load("author-1");

// Khi caching được bật, hai lần load cùng key dùng chung kết quả/future đã cache.
```

Kết quả này không có nghĩa database đã được gọi ngay tại dòng `load`. DataLoader xếp key vào hàng đợi; GraphQL Java dispatch batch ở thời điểm phù hợp trong quá trình thực thi.

Cache mặc định dựa trên key của DataLoader. Với key kiểu `String`, `Long`, UUID hoặc record bất biến có `equals`/`hashCode` đúng, việc so sánh thường dễ dự đoán. Với object key tự định nghĩa, cần bảo đảm equality và hash code ổn định.

## 4. Caching khác batching như thế nào?

Hai tính năng này có thể được cấu hình độc lập:

| Cơ chế | Mục đích | Tác dụng |
|---|---|---|
| Batching | Gom nhiều key chưa tải vào cùng lần dispatch | Giảm số lần gọi backend. |
| Caching | Ghi nhớ kết quả/future theo key | Tránh tải lại cùng key trong một request. |

Ví dụ request gọi `load(A)`, `load(B)`, `load(C)`:

- Batching gom A, B, C thành một batch.
- Nếu sau đó gọi lại `load(B)`, caching trả lại future đã có của B.

Nếu tắt caching nhưng vẫn bật batching, các lần gọi vẫn có thể được gom trong batch. Tuy nhiên, key trùng có thể được đưa vào batch loader nhiều lần nếu loader dùng kiểu nhận danh sách có thứ tự. Batch loader phải trả một kết quả tương ứng cho từng lần xuất hiện của key.

Trong Spring, `registerMappedBatchLoader` nhận `Set<K>` nên key trùng được biểu diễn một lần trong tập. `registerBatchLoader` nhận `List<K>` và cần xử lý thứ tự cùng các key trùng khi caching bị tắt.

## 5. Đăng ký DataLoader trong Spring for GraphQL

Ví dụ domain có `Author` và GraphQL query tìm tác giả theo ID:

```graphql
type Query {
    author(id: ID!): Author
}

type Author {
    id: ID!
    name: String!
}
```

Model Java:

```java
public record Author(String id, String name) {}
```

Batch service trả về map theo ID:

```java
public interface AuthorCatalog {
    Mono<Map<String, Author>> findAllByIds(Set<String> ids);
}
```

Đăng ký loader bằng `BatchLoaderRegistry`:

```java
import java.util.Map;
import java.util.Set;

import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Mono;

@Configuration
class AuthorBatchLoaderConfiguration {

    AuthorBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorCatalog authorCatalog) {

        registry.forTypePair(String.class, Author.class)
            .registerMappedBatchLoader((ids, environment) ->
                authorCatalog.findAllByIds(ids)
            );
    }
}
```

`forTypePair(String.class, Author.class)` khai báo kiểu key và kiểu value. Mặc định tên DataLoader được suy ra từ class của kiểu value, ở đây là `Author.class.getName()`. Có thể tùy chỉnh tên loader trong registration builder nếu cần.

Data fetcher nhận DataLoader qua method argument:

```java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class AuthorQueryController {

    @QueryMapping
    CompletableFuture<Author> author(
            @Argument String id,
            DataLoader<String, Author> authorLoader) {

        return authorLoader.load(id);
    }
}
```

Spring for GraphQL tìm DataLoader theo generic type và tên mặc định. Mỗi lần `authorLoader.load(id)` được gọi trong cùng GraphQL execution sẽ sử dụng cache của loader instance gắn với execution đó.

## 6. Minh họa cache hit trong cùng một GraphQL request

Một query có thể chọn cùng field nhiều lần bằng alias:

```graphql
query {
    first: author(id: "author-1") {
        id
        name
    }
    second: author(id: "author-1") {
        id
        name
    }
}
```

Hai field resolver cùng gọi `authorLoader.load("author-1")`. Khi cache mặc định bật, DataLoader chỉ cần một lần batch load cho key này; hai field có thể dùng chung kết quả.

Trong cùng request, một key có thể được yêu cầu từ nhiều field hoặc nhiều nhánh của object graph. Cache giúp các nhánh đó không tải lặp lại cùng một entity.

## 7. Cache được tạo mới cho request tiếp theo

Nếu client gửi lại cùng query trong một GraphQL request mới, Spring tạo `DataLoaderRegistry` mới và DataLoader cache mới. Vì vậy, key `author-1` sẽ là cache miss trong request tiếp theo, trừ khi batch loader hoặc tầng service có một cache riêng.

Ví dụ:

```text
Request A:
  load(author-1) -> miss -> batch loader gọi backend
  load(author-1) -> hit
  request kết thúc, cache A hết phạm vi

Request B:
  load(author-1) -> miss -> batch loader gọi backend lần nữa
  load(author-1) -> hit
  request kết thúc, cache B hết phạm vi
```

Đây là hành vi mong muốn khi kết quả phụ thuộc user, tenant, quyền truy cập hoặc trạng thái dữ liệu tại thời điểm request. DataLoader request cache không thay thế Redis, Caffeine hoặc cache dùng chung ở service layer.

## 8. Kiểm thử cache theo request bằng `GraphQlTester`

Có thể kiểm tra hai đặc điểm trong cùng một test:

1. Hai lần load cùng key trong một GraphQL execution chỉ gọi batch service một lần.
2. Cùng key trong GraphQL execution kế tiếp gọi batch service thêm một lần nữa.

Test slice minh họa:

```java
import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.times;

import reactor.core.publisher.Mono;

@GraphQlTest(AuthorQueryController.class)
@Import(AuthorBatchLoaderConfiguration.class)
class DataLoaderRequestCacheTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    AuthorCatalog authorCatalog;

    private static final String QUERY = """
        query {
            first: author(id: "author-1") { id name }
            second: author(id: "author-1") { id name }
        }
        """;

    @Test
    void cachesWithinOneRequestButNotAcrossRequests() {
        Author author = new Author("author-1", "Ada");

        given(authorCatalog.findAllByIds(Set.of("author-1")))
            .willReturn(Mono.just(Map.of("author-1", author)));

        graphQlTester.document(QUERY)
            .execute()
            .path("first.name")
            .entity(String.class)
            .isEqualTo("Ada");

        then(authorCatalog).should(times(1))
            .findAllByIds(Set.of("author-1"));

        graphQlTester.document(QUERY)
            .execute()
            .path("second.name")
            .entity(String.class)
            .isEqualTo("Ada");

        then(authorCatalog).should(times(2))
            .findAllByIds(Set.of("author-1"));
    }
}
```

Ví dụ dùng `@MockitoBean` của Spring Framework 6.2 trở lên và package `@GraphQlTest` của Spring Boot 3.x. Với Spring Boot 4.x, package test auto-configuration được tổ chức lại dưới `org.springframework.boot.graphql.test.autoconfigure`; với Boot cũ hơn, dùng mock bean annotation tương ứng phiên bản như `@MockBean`.

Test giả định `AuthorBatchLoaderConfiguration` được import, `AuthorCatalog` là mock và schema có field `Query.author`. Hai alias trong một query kiểm tra cache trong một execution; lần gọi `graphQlTester.document(QUERY).execute()` tiếp theo kiểm tra cache không được dùng chung giữa request.

## 9. Xóa một key khỏi cache bằng `clear`

Sau khi dữ liệu thay đổi trong cùng GraphQL execution, giá trị đã cache có thể không còn đúng. `DataLoader.clear(key)` xóa một key để lần `load(key)` tiếp theo gọi batch loader lại.

Ví dụ mutation đổi tên tác giả:

Giả sử controller đã inject service nghiệp vụ:

```java
public interface AuthorService {
    Author rename(String id, String name);
    BulkUpdateResult recalculateAll();
}

public record BulkUpdateResult(int updatedCount) {}
```

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.dataloader.DataLoader;

@MutationMapping
Author renameAuthor(
        @Argument String id,
        @Argument String name,
        DataLoader<String, Author> authorLoader) {

    Author updated = authorService.rename(id, name);
    authorLoader.clear(id);

    return updated;
}
```

Sau `clear(id)`, lần load tiếp theo của cùng ID không dùng future đã cache trước đó. Điều này hữu ích khi một mutation thay đổi entity mà các field tiếp theo trong cùng execution có thể tải lại entity qua DataLoader.

## 10. Cập nhật cache bằng `clear` và `prime`

Nếu mutation đã có entity mới sau khi lưu, có thể đưa trực tiếp entity đó vào cache để field tiếp theo không cần tải lại:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.dataloader.DataLoader;

@MutationMapping
Author renameAuthor(
        @Argument String id,
        @Argument String name,
        DataLoader<String, Author> authorLoader) {

    Author updated = authorService.rename(id, name);

    authorLoader.clear(id).prime(id, updated);

    return updated;
}
```

`prime(key, value)` chỉ thêm giá trị nếu key chưa có trong cache. Nếu key đã tồn tại, `prime` không ghi đè. Vì vậy, để thay thế một entry cũ, gọi `clear(key).prime(key, value)`.

Chỉ prime giá trị đã được xác thực và lưu thành công. Nếu mutation thất bại hoặc transaction rollback, không đưa object chưa được commit vào cache.

## 11. Xóa toàn bộ cache bằng `clearAll`

`clearAll()` xóa mọi entry của một DataLoader. Dùng khi một thao tác làm thay đổi nhiều key mà ứng dụng không thể xác định chính xác các entry bị ảnh hưởng.

```java
@MutationMapping
BulkUpdateResult recalculateAuthors(
        DataLoader<String, Author> authorLoader) {

    BulkUpdateResult result = authorService.recalculateAll();
    authorLoader.clearAll();
    return result;
}
```

`clearAll()` có phạm vi toàn bộ cache của loader hiện tại, không xóa cache của DataLoader khác và không xóa cache ở Redis/Caffeine hoặc service layer. Dùng `clear(key)` khi biết chính xác key để tránh tải lại dữ liệu không liên quan.

## 12. Tắt memoization caching khi có lý do cụ thể

Caching có thể được tắt bằng `DataLoaderOptions.setCachingEnabled(false)`. Trong Spring for GraphQL, truyền options vào registration:

```java
import org.springframework.context.annotation.Configuration;
import org.dataloader.DataLoaderOptions;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
class UncachedAuthorLoaderConfiguration {

    UncachedAuthorLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorCatalog authorCatalog) {

        DataLoaderOptions options = DataLoaderOptions.newOptions()
            .setCachingEnabled(false)
            .build();

        registry.forTypePair(String.class, Author.class)
            .withOptions(options)
            .registerMappedBatchLoader((ids, environment) ->
                authorCatalog.findAllByIds(ids)
            );
    }
}
```

Tắt cache không tự tắt batching. Tuy nhiên, với `BatchLoader` nhận `List<K>`, cùng key có thể xuất hiện nhiều lần trong danh sách nếu được load nhiều lần. Loader phải trả kết quả đúng vị trí cho từng key. Với `MappedBatchLoader` nhận `Set<K>`, key trùng được gộp theo đặc tính của `Set`.

Không tắt cache chỉ để cập nhật một entity sau mutation. Dùng `clear`, `clearAll` hoặc `prime` thường phù hợp hơn và vẫn giữ lợi ích deduplication cho các key còn lại.

## 13. Tùy chỉnh cache key cho object key hoặc composite key

Mặc định DataLoader dùng chính key làm cache key. Nếu key là object, hai instance khác nhau chỉ được xem là cùng key khi `equals` và `hashCode` của chúng cho kết quả tương ứng.

Ví dụ một tác giả được tải theo tenant và locale:

```java
public record AuthorLookupKey(
    String tenantId,
    String locale,
    String authorId
) {}
```

Ba thành phần đều có thể ảnh hưởng kết quả. Dùng record giúp equality/hash code dựa trên các thành phần đó. Nếu dùng class tự định nghĩa, hãy triển khai `equals`/`hashCode` đúng hoặc cấu hình `DataLoaderOptions.setCacheKeyFunction(...)` để tạo cache key tương đương.

Không dùng riêng `authorId` làm cache key nếu kết quả còn phụ thuộc tenant, locale, quyền hoặc filter. Hai lần load cùng ID nhưng khác ngữ cảnh không được nhận nhầm cùng một giá trị cache.

## 14. Cache exception và lỗi từ batch loader

`DataLoaderOptions` có `setCachingExceptionsEnabled(...)` để điều khiển việc memoize các kết quả exceptional theo key. Với cache ngắn hạn theo request, mặc định giữ lỗi có thể tránh lặp lại một lần tải chắc chắn vẫn thất bại trong cùng execution. Tuy nhiên, nếu lỗi có thể phục hồi ngay trong request và ứng dụng cần thử lại, cần cân nhắc xóa key hoặc cấu hình không cache exceptional value.

Ví dụ cấu hình không cache exceptional values:

```java
import org.dataloader.DataLoaderOptions;

DataLoaderOptions options = DataLoaderOptions.newOptions()
    .setCachingEnabled(true)
    .setCachingExceptionsEnabled(false)
    .build();
```

Phân biệt lỗi toàn batch với lỗi gắn cho một key cụ thể. Khi batch function thất bại, các future của batch có thể kết thúc exceptional; với lỗi riêng từng key, cách biểu diễn phụ thuộc loại batch loader và phiên bản `java-dataloader`. Không nên tự động retry mọi lỗi vì có thể lặp lại thao tác backend hoặc che khuất lỗi dữ liệu.

## 15. DataLoader cache không thay thế cache dùng chung

DataLoader cache được thiết kế cho một GraphQL request ngắn hạn. Nó không tự chia sẻ dữ liệu giữa các request, process hoặc instance ứng dụng.

| Loại cache | Phạm vi | Ví dụ |
|---|---|---|
| DataLoader memoization cache | Một DataLoader trong một GraphQL execution | Cùng key chỉ tải một lần trong request. |
| Service/application cache | Nhiều request trong một process | Caffeine hoặc cache abstraction của Spring. |
| Distributed cache | Nhiều process/instance | Redis hoặc hệ thống cache dùng chung. |
| HTTP/GraphQL response cache | Toàn bộ response theo chính sách cache | Cache response theo query, variables và quyền. |

Trong Java DataLoader có hai lớp cache cần phân biệt:

- `CacheMap` lưu future theo key trong DataLoader instance; đây là memoization cache thường dùng cho request.
- `ValueCache` là một abstraction tùy chọn để đọc/ghi giá trị từ cache bên ngoài, có thể thực hiện bất đồng bộ. Mặc định nó không tự kết nối Redis hay cache phân tán nào.

Nếu muốn cache dữ liệu giữa nhiều request, hãy dùng cache ở service/data layer hoặc cấu hình `ValueCache` có chủ đích. Không kéo dài vòng đời DataLoader request cache thành singleton chỉ để tái sử dụng dữ liệu.

## 16. Tenant isolation và dữ liệu phụ thuộc người dùng

Request cache an toàn hơn khi mỗi GraphQL execution có DataLoader instance riêng, nhưng batch loader vẫn phải kiểm tra tenant và quyền truy cập đúng cách.

Ví dụ batch loader dùng tenant từ `BatchLoaderEnvironment`:

```java
import graphql.GraphQLContext;
import org.springframework.graphql.execution.BatchLoaderRegistry;

registry.forTypePair(String.class, Project.class)
    .registerMappedBatchLoader((projectIds, environment) -> {
        GraphQLContext context = (GraphQLContext) environment.getContext();
        TenantContext tenant = context.get("tenantContext");

        return projectService.findByTenantAndIds(
            tenant.tenantId(), projectIds
        ).collectMap(Project::id);
    });
```

`BatchLoaderRegistry` hỗ trợ chia sẻ cùng `GraphQLContext` với data fetcher và batch loading function. Dùng tenant context đã được xác minh, không lấy tenant ID tùy ý từ GraphQL argument rồi dùng làm căn cứ quyền.

Nếu cùng một DataLoader có thể tải dữ liệu cho nhiều tenant trong một execution đặc biệt, tenant phải là một phần của key/cache key hoặc loader phải được tách theo tenant. Không để cùng resource ID của hai tenant va chạm trong cache.

## 17. Giới hạn bộ nhớ và batch size

DataLoader giữ các entry đã tải trong cache cho tới khi request kết thúc hoặc key được xóa. Với một query lớn có hàng chục nghìn key duy nhất, cache có thể chiếm đáng kể bộ nhớ trong thời gian execution.

Một số cách kiểm soát:

- Giới hạn kích thước trang và số parent object mà query có thể trả về.
- Dùng query complexity/depth limit khi API cho phép truy vấn lớn.
- Chọn đúng key và chỉ load những field mà client yêu cầu.
- Cân nhắc `maxBatchSize` để chia một batch quá lớn thành nhiều dispatch.
- Dùng `clear(key)` hoặc `clearAll()` khi entry không còn cần thiết trong execution.
- Tránh giữ DataLoader hoặc future của nó sau khi GraphQL execution kết thúc.

`maxBatchSize` giới hạn số key gửi tới một lần gọi batch loader; nó không giới hạn tổng số key được cache trong toàn bộ request. Không dùng `maxBatchSize` như một giới hạn thay thế cho pagination hoặc query complexity.

## 18. Kiểm thử cache và invalidation

Nên có các kiểm thử sau:

| Tình huống | Kỳ vọng |
|---|---|
| Load cùng key hai lần trong một request | Batch loader chỉ nhận key một lần khi caching bật. |
| Load cùng key trong request tiếp theo | Loader được tạo mới và key được tải lại. |
| Hai key khác nhau | Cả hai có thể được gom vào cùng batch. |
| `clear(key)` rồi load lại | Key được đưa vào batch loader lần nữa. |
| `clearAll()` rồi load lại | Các key đã xóa được tải lại. |
| `clear(key).prime(key, value)` | Lần load sau dùng giá trị mới đã prime. |
| `prime` khi key đã có | Entry cũ không bị ghi đè. |
| Tắt caching | Cùng key có thể tạo nhiều load; batch loader phải xử lý duplicate theo contract. |
| Hai tenant/request đồng thời | Cache và context không trộn dữ liệu. |

Với `GraphQlTester`, kiểm tra cùng một query có hai alias gọi cùng key, rồi chạy query lần nữa để xác minh cache không đi qua request boundary. Với unit test DataLoader, có thể tạo `DefaultBatchLoaderRegistry`, đăng ký loader vào `DataLoaderRegistry`, gọi `load`, `clear`, `prime` và `dispatchAndJoin()` để kiểm tra trực tiếp cache behavior.

## 19. Lỗi thường gặp

**Cho rằng `BatchLoaderRegistry` chính là request cache.** Registry này giữ registration; `DefaultExecutionGraphQlService` tạo DataLoader instances trong `DataLoaderRegistry` riêng cho từng request.

**Đưa DataLoader vào singleton field.** Cache có thể bị dùng chung giữa người dùng hoặc request khác nhau. Nhận loader qua method argument trong data fetcher.

**Cho rằng cache thay thế batching.** Cache loại bỏ key trùng; batching gom nhiều key khác nhau. Hai cơ chế giải quyết hai phần khác nhau của bài toán N+1.

**Cho rằng tắt cache sẽ tắt batching.** `setCachingEnabled(false)` chỉ tắt memoization. Batching vẫn có thể hoạt động nếu `batchingEnabled` còn bật.

**Dùng `prime` để ghi đè entry đã tồn tại.** `prime` không thay đổi key đã cache. Dùng `clear(key).prime(key, value)` nếu cần thay giá trị.

**Không clear cache sau mutation trong cùng execution.** Resolver sau đó có thể nhận dữ liệu cũ. Xóa hoặc prime key đã thay đổi.

**Dùng object key mutable.** `equals`/`hashCode` có thể thay đổi sau khi key đã cache, khiến lookup không nhất quán. Dùng key bất biến hoặc cache key function ổn định.

**Dùng request cache làm distributed cache.** Cache bị bỏ khi execution kết thúc và không chia sẻ giữa instance. Dùng service cache hoặc `ValueCache` khi thực sự cần cache dài hơn.

**Không kiểm tra cardinality và memory của query lớn.** Cache giữ mỗi key duy nhất cho tới hết request. Giới hạn pagination, query complexity và batch size phù hợp.

## Kết luận

DataLoader cache theo request là cơ chế memoization mặc định của GraphQL Java, được Spring for GraphQL tích hợp thông qua `BatchLoaderRegistry` và `DataLoaderRegistry` riêng cho từng execution. Cache giúp cùng key chỉ cần tải một lần trong request, còn batching gom các key khác nhau vào một lần dispatch. Khi dữ liệu thay đổi trong cùng execution, dùng `clear`, `clearAll` hoặc `clear(...).prime(...)`; chỉ tắt caching khi có lý do cụ thể và hiểu ảnh hưởng tới duplicate keys. Không dùng DataLoader request cache như cache dùng chung giữa người dùng hoặc request; hãy dùng cache service/distributed riêng và bảo đảm key chứa đủ ngữ cảnh tenant, locale hoặc quyền nếu các yếu tố đó làm thay đổi kết quả.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution: DataLoader and BatchLoaderRegistry](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: DataLoader argument](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — java-dataloader README](https://github.com/graphql-java/java-dataloader)
- [GraphQL Java — `DataLoaderOptions` API](https://javadoc.io/doc/com.graphql-java/java-dataloader/latest/org/dataloader/DataLoaderOptions.html)
