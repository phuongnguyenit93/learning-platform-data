# Batch loading có argument trong Spring for GraphQL

Trong GraphQL, cùng một field có thể được gọi nhiều lần với các argument khác nhau trong một operation. Khi field đó cần tải dữ liệu theo batch, server phải giữ được cả hai thông tin: object cha nào đang được resolve và argument nào được client truyền cho lần gọi đó.

`@BatchMapping` là cách ngắn gọn để batch load field lồng nhau, nhưng method của nó không nhận `@Argument` như một `@SchemaMapping` thông thường. Nếu argument ảnh hưởng đến dữ liệu cần tải, hãy dùng `@SchemaMapping` kết hợp `DataLoader` được đăng ký qua `BatchLoaderRegistry`. Có thể đưa argument vào key của DataLoader để cache phân biệt các yêu cầu khác nhau, hoặc tải dữ liệu rộng hơn rồi lọc ở resolver tùy theo đặc điểm dữ liệu.

## 1. Vì sao batch loading cần quan tâm đến argument?

Giả sử mỗi người có danh sách bạn bè và client có thể lọc danh sách theo đồ uống yêu thích:

```graphql
input FriendsFilter {
    favoriteBeverage: String
}

type Query {
    me: Person
    person(id: ID!): Person
    people: [Person!]!
}

type Person {
    id: ID!
    name: String!
    favoriteBeverage: String
    friends(filter: FriendsFilter): [Person!]!
}
```

Client có thể yêu cầu cùng một field với filter khác nhau:

```graphql
query {
    me {
        friends(filter: { favoriteBeverage: "tea" }) {
            id
            name
        }
    }
    people {
        id
        friends(filter: { favoriteBeverage: "coffee" }) {
            id
            name
        }
    }
}
```

Resolver của `Person.friends` phải biết cả `Person` cha và `filter`. Nếu chỉ batch theo `personId`, hai lời gọi `friends` của cùng một người nhưng dùng filter khác nhau có thể bị coi là cùng một lần tải. Kết quả cache khi đó không còn đúng với argument của từng field.

Đây là điểm cốt lõi: **argument là một phần của yêu cầu dữ liệu nếu nó làm thay đổi kết quả field**. Khi batch, key và chiến lược cache phải phản ánh các yếu tố đó.

## 2. Giới hạn của `@BatchMapping`

`@BatchMapping` nhận một danh sách source/parent object và trả kết quả đã tải theo batch. Ví dụ đơn giản:

```java
@Controller
public class BookController {

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        // Tải tác giả cho toàn bộ sách trong một batch.
    }
}
```

Spring for GraphQL đăng ký batch loader và data fetcher cho field `Book.author` tự động. Với các trường hợp đơn giản, cách này giảm boilerplate so với việc tự đăng ký `DataLoader` và viết `@SchemaMapping` chỉ để gọi `loader.load(...)`.

Tuy nhiên, method `@BatchMapping` chỉ hỗ trợ các tham số theo batch contract như:

| Tham số | Ý nghĩa |
| --- | --- |
| `List<K>` | Các source/parent object cần tải field. |
| `Principal` | Principal hiện tại nếu Spring Security cung cấp. |
| `@ContextValue` | Giá trị trong `GraphQLContext` của batch environment. |
| `GraphQLContext` | Context chung của GraphQL execution. |
| `BatchLoaderEnvironment` | Context và metadata của lần dispatch batch. |

Method `@BatchMapping` không hỗ trợ `@Argument` để lấy argument riêng của field. Lý do là batch loader làm việc ở tầng DataLoader: nó nhận các key và batch environment, không có một `DataFetchingEnvironment` riêng cho từng lời gọi field. Một batch có thể gộp nhiều parent và nhiều lời gọi field với argument khác nhau.

Vì vậy, nếu field chỉ phụ thuộc parent object và context chung của request, `@BatchMapping` thường phù hợp. Nếu field phụ thuộc argument như `filter`, `sort`, `first`, `after` hoặc chế độ hiển thị, cần thiết kế DataLoader key có chứa các yếu tố đó hoặc chọn chiến lược tải rồi lọc.

Khi `@BatchMapping` trả `Map<K,V>` với parent object làm key, kiểu parent cần có `equals` và `hashCode` ổn định để map khớp đúng từng source. Nếu trả `Flux<V>` hoặc `List<V>` theo dạng positional, kết quả phải có cùng số phần tử và đúng thứ tự với danh sách parent nhận vào.

## 3. Cách 1: Dùng `@SchemaMapping` và lọc sau khi DataLoader tải

Chiến lược đầu tiên là DataLoader tải toàn bộ entity liên quan theo ID, sau đó `@SchemaMapping` áp dụng argument để lọc kết quả.

### 3.1. Đăng ký DataLoader theo ID

```java
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class PersonDataLoaderConfiguration {

    public PersonDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            PersonService personService) {

        registry.forTypePair(Integer.class, Person.class)
                .registerMappedBatchLoader((personIds, environment) ->
                        personService.findByIds(personIds)
                                .collectMap(Person::id));
    }
}
```

`findByIds` nhận tập ID và trả về `Flux<Person>`. `collectMap(Person::id)` tạo `Mono<Map<Integer, Person>>`, phù hợp với mapped batch loader. Loader trả kết quả theo key nên không cần tự sắp xếp danh sách theo thứ tự đầu vào.

### 3.2. Nhận argument tại `@SchemaMapping`

```java
import java.util.Objects;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class FriendsController {

    @SchemaMapping(typeName = "Person", field = "friends")
    public CompletableFuture<List<Person>> friends(
            Person person,
            @Argument("filter") FriendsFilter filter,
            DataLoader<Integer, Person> personLoader) {

        return personLoader.loadMany(person.friendIds())
                .thenApply(friends -> filter == null
                        ? friends.stream().filter(Objects::nonNull).toList()
                        : friends.stream()
                                .filter(Objects::nonNull)
                                .filter(filter::matches)
                                .toList());
    }
}
```

Input record:

```java
public record FriendsFilter(String favoriteBeverage) {

    public boolean matches(Person person) {
        return favoriteBeverage == null
                || favoriteBeverage.equals(person.favoriteBeverage());
    }
}
```

Ở đây:

- `Person person` là source object cha.
- `@Argument("filter")` là argument của field `friends`.
- `DataLoader<Integer, Person>` tải bạn bè theo ID và cache entity theo ID trong request.
- `thenApply` lọc danh sách đã tải theo filter của lần gọi field hiện tại.

### 3.3. Khi nào nên lọc sau khi tải?

Chiến lược này phù hợp khi tập liên quan tương đối nhỏ hoặc các filter thường dùng có nhiều dữ liệu trùng nhau. Ví dụ một người có vài chục bạn bè và client có thể hỏi nhiều filter khác nhau trong cùng operation. Tải mỗi người một lần rồi lọc tại resolver giúp tái sử dụng cache theo ID.

Ưu điểm:

- DataLoader key đơn giản, chỉ là ID entity.
- Một entity có thể được tái sử dụng qua nhiều filter trong cùng request.
- Truy vấn batch ít phụ thuộc vào số lượng tổ hợp argument.
- Dễ triển khai nếu tập dữ liệu liên quan nhỏ và đã được giới hạn.

Hạn chế:

- Có thể tải nhiều entity mà client không cần.
- Tốn bộ nhớ hơn khi parent có nhiều quan hệ.
- Filter được áp dụng sau khi dữ liệu đã vào ứng dụng, không tận dụng được index hoặc query planner của database.
- Không phù hợp khi mỗi parent có hàng nghìn quan hệ hoặc filter rất chọn lọc.

## 4. Cách 2: Đưa parent và argument vào composite key

Nếu filter làm thay đổi tập dữ liệu cần tải và việc tải toàn bộ quan hệ quá tốn kém, hãy tạo một key kết hợp parent với argument.

```java
public record FriendsFilterKey(
        Integer personId,
        FriendsFilter filter) {

    public FriendsFilterKey {
        // Trong API này, bỏ qua filter và truyền filter rỗng có cùng ý nghĩa.
        filter = filter == null ? new FriendsFilter(null) : filter;
    }
}
```

Chuẩn hóa `null` thành một filter rỗng giúp omitted argument và `{}` tạo cùng cache key nếu chúng có cùng ý nghĩa nghiệp vụ. Nếu API phân biệt hai trường hợp này, không thực hiện bước chuẩn hóa.

Java record tự sinh `equals` và `hashCode`, vì vậy hai key có cùng `personId` và cùng giá trị filter được xem là bằng nhau. Cả `FriendsFilter` cũng nên là kiểu bất biến có `equals`/`hashCode` ổn định, ví dụ một record.

### 4.1. Đăng ký batch loader với composite key

Ví dụ dưới đây dùng `Person[]` làm kiểu kết quả của DataLoader để tránh nhập nhằng generic type do Java type erasure. GraphQL Java có thể hoàn tất mảng như một list field.

```java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class FilteredFriendsBatchLoader {

    public FilteredFriendsBatchLoader(
            BatchLoaderRegistry registry,
            FriendsQueryService friendsQueryService) {

        registry.forTypePair(FriendsFilterKey.class, Person[].class)
                .registerMappedBatchLoader((keys, environment) ->
                        friendsQueryService.findByKeys(keys)
                                .map(results -> results.entrySet().stream()
                                        .collect(Collectors.toMap(
                                                Map.Entry::getKey,
                                                entry -> entry.getValue()
                                                        .toArray(Person[]::new)))));
    }
}
```

`FriendsQueryService.findByKeys` là service của ứng dụng, nhận tập `FriendsFilterKey` và trả `Mono<Map<FriendsFilterKey, List<Person>>>`. Nó cần trả một entry cho mọi key được yêu cầu, kể cả khi danh sách kết quả rỗng. Có thể thay đổi kiểu kết quả của service theo mô hình dữ liệu thực tế.

Nếu truy vấn cần tenant hoặc principal, batch loader có thể đọc `GraphQLContext` qua `BatchLoaderEnvironment` và truyền giá trị đã được xác thực vào service. Không lấy tenant từ filter do client gửi rồi coi đó là căn cứ phân quyền.

### 4.2. Resolver truyền argument vào DataLoader key

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class FriendsController {

    @SchemaMapping(typeName = "Person", field = "friends")
    public CompletableFuture<Person[]> friends(
            Person person,
            @Argument("filter") FriendsFilter filter,
            DataLoader<FriendsFilterKey, Person[]> friendsLoader) {

        FriendsFilterKey key = new FriendsFilterKey(person.id(), filter);
        return friendsLoader.load(key);
    }
}
```

DataLoader lúc này cache theo cả parent ID lẫn filter. Cùng một người với filter `tea` và `coffee` tạo hai key khác nhau, nên không dùng nhầm kết quả. Hai lần gọi cùng người với cùng filter có thể dùng chung kết quả cache trong request.

### 4.3. Tổ chức truy vấn batch trong service

Service có thể nhóm keys theo filter rồi truy vấn nhiều parent cùng lúc:

```java
public Mono<Map<FriendsFilterKey, List<Person>>> findByKeys(
        Set<FriendsFilterKey> keys) {

    // Nhóm các key theo filter để tận dụng một truy vấn cho nhiều personId.
    Map<FriendsFilter, Set<Integer>> personIdsByFilter = keys.stream()
            .collect(Collectors.groupingBy(
                    FriendsFilterKey::filter,
                    Collectors.mapping(
                            FriendsFilterKey::personId,
                            Collectors.toSet())));

    return repository.findFriendsGroupedByFilter(personIdsByFilter)
            .collectMap(FriendQueryResult::key, FriendQueryResult::friends)
            .map(found -> keys.stream().collect(Collectors.toMap(
                    key -> key,
                    key -> found.getOrDefault(key, List.of()))));
}
```

`findFriendsGroupedByFilter` đại diện cho truy vấn repository tùy ứng dụng. Điểm quan trọng là service phải tạo kết quả cho tất cả keys, dùng `List.of()` cho key không có bạn bè phù hợp. Nếu bỏ hẳn key khỏi mapped result, DataLoader có thể trả null cho key đó, trong khi SDL có thể yêu cầu list khác null.

## 5. So sánh hai chiến lược

| Tiêu chí | Tải tất cả rồi lọc | Composite key gồm parent + filter |
| --- | --- | --- |
| DataLoader key | Chỉ ID entity | Parent ID và argument |
| Cache | Tái sử dụng entity giữa các filter | Cache riêng cho từng tổ hợp argument |
| Lượng dữ liệu tải | Có thể nhiều hơn nhu cầu | Có thể chỉ tải đúng dữ liệu cần |
| Số truy vấn | Thường ít truy vấn hơn khi dữ liệu dùng chung nhiều | Có thể tăng khi có nhiều filter khác nhau |
| Bộ nhớ | Có thể lớn do giữ cả entity không được trả về | Có thể ít dữ liệu thừa hơn nhưng có thể lặp entity ở nhiều key |
| Phù hợp | Tập quan hệ nhỏ, filter dùng chung nhiều | Tập lớn, filter chọn lọc, argument làm thay đổi tập kết quả |

Không có chiến lược luôn tốt hơn. Hãy đo số lượng parent, số lượng quan hệ trung bình, mức độ trùng lặp filter, kích thước batch và chi phí query trước khi chọn.

## 6. Vì sao không thể chỉ thêm `@Argument` vào `@BatchMapping`?

Một `@BatchMapping` được gọi khi DataLoader dispatch một nhóm parent keys. Nếu cùng field `friends` xuất hiện với filter khác nhau, batch loader cần biết filter nào thuộc parent nào. Một tham số `@Argument` đơn lẻ không thể biểu diễn đầy đủ mối quan hệ đó nếu batch gộp nhiều lời gọi.

Ví dụ query:

```graphql
query {
    personA: person(id: "1") {
        friends(filter: { favoriteBeverage: "tea" }) { name }
    }
    personB: person(id: "2") {
        friends(filter: { favoriteBeverage: "coffee" }) { name }
    }
}
```

Batch loader có thể nhận các parent từ nhiều field invocation trong cùng request. Nó cần key hoặc metadata tương ứng cho từng invocation. `@BatchMapping` không có tham số `@Argument` để cung cấp thông tin đó; `BatchLoaderRegistry` cùng `DataLoader` cho phép resolver tạo key phù hợp trước khi load.

`@BatchMapping` vẫn có thể nhận `GraphQLContext` hoặc `@ContextValue` vì đó là metadata chung của execution/batch. Hãy phân biệt:

- Argument là dữ liệu của một lần gọi field, ví dụ `filter`, `first`, `sort`.
- Context là metadata chung theo request hoặc execution, ví dụ tenant đã xác thực, principal và locale.

## 7. Argument, context và key có vai trò khác nhau

| Thành phần | Ví dụ | Vai trò trong batch |
| --- | --- | --- |
| Parent key | `personId` | Xác định object cha cần resolve field. |
| Field argument | `FriendsFilter`, `first`, `sort` | Thay đổi tập dữ liệu hoặc cách sắp xếp cần trả về. |
| GraphQL context | `tenantId`, principal, locale | Cung cấp metadata chung cho execution/batch. |
| DataLoader key | `FriendsFilterKey(personId, filter)` | Xác định một kết quả có thể cache riêng biệt. |

Nếu tenant cố định trong toàn request, thường không cần đưa tenant vào composite key vì DataLoader được tạo theo request. Tuy nhiên, nếu một loader hoặc cache được chia sẻ qua nhiều tenant, tenant phải được phân vùng trong key/cache hoặc cơ chế cô lập tương đương.

## 8. Argument ảnh hưởng đến cache của DataLoader

DataLoader mặc định cache theo key trong phạm vi request. Nếu resolver chỉ gọi `loader.load(personId)`, hai lần gọi cùng person với filter khác nhau sẽ cùng key và có nguy cơ nhận cùng kết quả.

Ví dụ sai về mặt mô hình cache:

```java
// Không đủ nếu kết quả phụ thuộc filter.
return friendsLoader.load(person.id());
```

Khi filter ảnh hưởng đến dữ liệu, key phải bao gồm filter hoặc resolver phải lọc sau khi tải:

```java
// Key bao gồm mọi yếu tố làm thay đổi kết quả.
return friendsLoader.load(new FriendsFilterKey(person.id(), filter));
```

Các quy tắc cần nhớ:

- Dùng key bất biến, có `equals` và `hashCode` ổn định.
- Chuẩn hóa argument trước khi tạo key nếu các biểu diễn khác nhau mang cùng ý nghĩa nghiệp vụ.
- Nếu `null` và filter rỗng có ý nghĩa khác nhau, giữ chúng khác nhau trong key.
- Nếu default trong SDL làm hai request có cùng ngữ nghĩa, nên chuẩn hóa để tránh cache key không cần thiết khác nhau.
- Không dùng object mutable làm key vì thay đổi field sau khi đưa vào cache có thể phá vỡ hash lookup.

## 9. Batch loading với pagination, sort và limit

Argument không chỉ là filter. Các field quan hệ thường có pagination hoặc sort:

```graphql
type Person {
    id: ID!
    posts(first: Int = 20, after: String, sort: PostSort): [Post!]!
}
```

Nếu `first`, `after` hoặc `sort` ảnh hưởng kết quả, chúng cũng cần được tính đến trong chiến lược batch/cache. Ví dụ key có thể là:

```java
public record PostsKey(
        Integer personId,
        int first,
        String after,
        PostSort sort) {
}
```

Khi batch nhiều parent, không được áp dụng `LIMIT 20` cho toàn bộ truy vấn nếu yêu cầu là tối đa 20 bài viết cho mỗi người. Cần giới hạn theo từng parent, ví dụ dùng window function `ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY created_at DESC)` rồi lọc `row_number <= first`. Với cursor, truy vấn phải áp dụng điều kiện sau cursor riêng cho từng parent.

Nếu pagination có cursor opaque, hãy giải mã/kiểm tra cursor ở tầng phù hợp trước khi tạo key. Không dùng raw cursor không chuẩn hóa nếu nhiều cursor khác nhau đại diện cùng vị trí và làm cache phân mảnh không cần thiết.

## 10. Giới hạn batch size và xử lý tập key lớn

Batch loading giảm số lần gọi service/database, nhưng một batch quá lớn cũng có thể tạo câu SQL dài, nhiều bind parameter hoặc chiếm nhiều bộ nhớ. `@BatchMapping` có thuộc tính `maxBatchSize` để giới hạn số source keys trong mỗi batch:

```java
@BatchMapping(typeName = "Book", field = "author", maxBatchSize = 100)
public Mono<Map<Book, Author>> author(
        List<Book> books,
        @ContextValue("tenantId") String tenantId) {
    return authorService.findForBooks(tenantId, books);
}
```

Ví dụ cho thấy `@BatchMapping` có thể nhận context chung qua `@ContextValue`, dù không nhận được `@Argument` của từng lời gọi field. `maxBatchSize` có từ Spring for GraphQL 1.1.0. Khi dùng `BatchLoaderRegistry`, có thể cấu hình `DataLoaderOptions` hoặc batch loader theo cách phù hợp với phiên bản thư viện để giới hạn kích thước batch. Việc chia batch không thay thế pagination ở GraphQL schema; nó chỉ giới hạn số key mỗi lần dispatch.

Với composite key, kích thước batch cần tính theo số tổ hợp parent/argument, không chỉ số parent object. Một parent có thể xuất hiện nhiều lần với các filter khác nhau và tạo nhiều key.

## 11. Xử lý key không có kết quả, null và lỗi

Batch loader cần trả kết quả đúng với contract của schema:

- Với field `[Person!]!`, không có bạn bè phù hợp nên trả danh sách rỗng, không trả null.
- Với field nullable `[Person!]`, có thể trả null nếu null mang ý nghĩa nghiệp vụ riêng; hãy phân biệt rõ với danh sách rỗng.
- Không phát phần tử null nếu phần tử được khai báo Non-Null.
- Nếu một key không có dữ liệu, mapped loader nên trả giá trị tương ứng phù hợp, ví dụ empty list hoặc null theo schema.
- Lỗi truy vấn batch nên được chuyển thành GraphQL error theo chính sách ứng dụng, không âm thầm trả dữ liệu chưa lọc.

Nếu batch loader trả `Map<K,V>`, map cần có kết quả cho từng key cần xử lý. Nếu dùng positional `Flux<V>` hoặc `List<V>`, số phần tử và thứ tự phải khớp chính xác với danh sách key đầu vào.

## 12. Bảo mật khi argument dùng để lọc dữ liệu

Argument có thể chứa điều kiện lọc nhưng không phải bằng chứng về quyền truy cập. Ví dụ `tenantId`, `ownerId` hoặc `includePrivate` do client gửi không được tự động coi là phạm vi dữ liệu hợp lệ.

Các nguyên tắc:

1. Xác thực principal trước khi thực thi field.
2. Lấy tenant/organization từ context đã được server xác minh.
3. Kết hợp điều kiện quyền với filter client gửi trong repository/service.
4. Không tải dữ liệu của tenant khác rồi mới lọc ở Java nếu có thể giới hạn ngay trong truy vấn.
5. Đưa mọi yếu tố ảnh hưởng kết quả vào cache key hoặc bảo đảm DataLoader được giới hạn theo request.
6. Kiểm thử hai người dùng/tenant với cùng parent ID và argument giống nhau để xác nhận không có rò rỉ cache.

Ví dụ batch loader có thể lấy tenant từ `BatchLoaderEnvironment`:

```java
registry.forTypePair(FriendsFilterKey.class, Person[].class)
        .registerMappedBatchLoader((keys, environment) -> {
            GraphQLContext context = (GraphQLContext) environment.getContext();
            String tenantId = context.get("tenantId");
            return friendsQueryService.findByTenantAndKeys(tenantId, keys)
                    .map(this::toArrayMap);
        });
```

`tenantId` phải được đưa vào `GraphQLContext` từ authentication/authorization layer. Nếu context bắt buộc mà bị thiếu, nên từ chối request thay vì truy vấn không giới hạn tenant.

## 13. Kiểm thử batch loading có argument

Kiểm thử cần chứng minh cả dữ liệu trả về và tính đúng đắn của cache key. Một test chỉ xác nhận số query giảm là chưa đủ nếu các filter khác nhau bị trả cùng một danh sách.

Ví dụ GraphQL document gọi cùng field với hai filter khác nhau:

```graphql
query {
    person(id: "1") {
        teaFriends: friends(filter: { favoriteBeverage: "tea" }) {
            name
        }
        coffeeFriends: friends(filter: { favoriteBeverage: "coffee" }) {
            name
        }
    }
}
```

Ví dụ kiểm thử bằng `GraphQlTester`:

```java
@Test
void sameParentCanBeLoadedWithDifferentFilters() {
    var response = graphQlTester.document("""
            query {
                person(id: "1") {
                    teaFriends: friends(filter: { favoriteBeverage: "tea" }) {
                        name
                    }
                    coffeeFriends: friends(filter: { favoriteBeverage: "coffee" }) {
                        name
                    }
                }
            }
            """)
        .execute();

    response.path("person.teaFriends[0].name")
        .entity(String.class)
        .isEqualTo("An");

    response.path("person.coffeeFriends[0].name")
        .entity(String.class)
        .isEqualTo("Binh");
}
```

Test giả định fixture có một người bạn tên `An` thích trà và một người bạn tên `Binh` thích cà phê. Nên kiểm tra thêm filter không truyền, filter null, filter rỗng, hai parent khác nhau, cùng key lặp lại, không có kết quả, và trường hợp batch được chia do `maxBatchSize`. Có thể verify số lần gọi repository để chắc rằng các key được gom batch.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thể bind `@Argument` trong `@BatchMapping` | `@BatchMapping` không hỗ trợ field argument | Dùng `@SchemaMapping` với `DataLoader` và `@Argument`. |
| Cùng parent nhưng filter khác nhau nhận cùng kết quả | DataLoader key chỉ chứa parent ID | Lọc sau khi load hoặc đưa filter vào composite key. |
| Batch loader tải quá nhiều dữ liệu | Tải tất cả quan hệ rồi lọc sau dù tập dữ liệu lớn | Dùng composite key và lọc trong truy vấn batch. |
| Batch loader trả sai thứ tự | Dùng positional `List`/`Flux` nhưng không giữ thứ tự key | Dùng mapped loader hoặc sắp xếp kết quả theo đúng thứ tự keys. |
| DataLoader cache không hit | Key là object không có `equals`/`hashCode` ổn định | Dùng record hoặc immutable key class. |
| Cùng filter nhưng tạo nhiều cache key | Giá trị argument chưa được chuẩn hóa | Chuẩn hóa default, sort và filter trước khi tạo key. |
| Field Non-Null bị lỗi khi không có kết quả | Batch loader trả null thay vì empty list | Trả giá trị phù hợp với nullability của SDL. |
| Dữ liệu giữa tenant bị trộn | Cache hoặc key không cô lập theo tenant | Dùng request-scoped DataLoader và context đã xác thực; kiểm tra cache scope. |

## 15. Checklist thiết kế batch loading có argument

1. Xác định argument nào thực sự làm thay đổi tập kết quả hoặc cách sắp xếp.
2. Dùng `@BatchMapping` cho field chỉ phụ thuộc parent keys và request context chung.
3. Khi cần field argument, dùng `@SchemaMapping` để đọc `@Argument`.
4. Chọn tải tất cả rồi lọc sau nếu tập dữ liệu nhỏ và có khả năng tái sử dụng cao.
5. Chọn composite key gồm parent ID và argument nếu cần tải đúng tập dữ liệu theo từng yêu cầu.
6. Dùng immutable key có `equals`/`hashCode` ổn định.
7. Chuẩn hóa argument/default trước khi tạo key.
8. Đưa tenant/principal vào context đã xác thực và lọc dữ liệu ở service/repository.
9. Giữ đúng số lượng, thứ tự, nullability và empty-result contract của batch loader.
10. Giới hạn batch size và pagination theo từng parent khi dữ liệu lớn.
11. Kiểm thử cùng parent với nhiều argument trong cùng GraphQL operation.
12. Đo số lần query, lượng dữ liệu tải và cache hit để chọn chiến lược phù hợp.

Batch loading có argument cần giữ đúng mối quan hệ giữa parent object và từng lần gọi field. `@BatchMapping` phù hợp với trường hợp đơn giản, nơi field chỉ phụ thuộc parent và context chung. Khi argument thay đổi kết quả, `@SchemaMapping` kết hợp `DataLoader` cho phép lọc sau khi tải hoặc dùng composite key để cache từng tổ hợp parent/argument. Chọn chiến lược dựa trên kích thước dữ liệu, mức độ trùng lặp và yêu cầu bảo mật sẽ giúp giảm N+1 mà vẫn trả đúng kết quả cho từng lời gọi field.

Tài liệu tham khảo: [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping) và [Spring for GraphQL — Batch Loading Recipes](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-batching).
