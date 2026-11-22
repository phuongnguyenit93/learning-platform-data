# Phạm vi DataLoader theo request

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao DataLoader thường có vòng đời gắn với một GraphQL execution request.
- Phân biệt `BatchLoaderRegistry` cấp ứng dụng với `DataLoaderRegistry` và DataLoader được tạo cho từng request.
- Hiểu cache của DataLoader hoạt động trong phạm vi nào và vì sao không nên chia sẻ instance giữa các request.
- Nhận biết cách DataLoader gom các lần `load` và khử trùng lặp key trong cùng một request.
- Truyền request context như tenant, principal, locale và correlation ID tới batch loader.
- Thiết kế cache key chứa đủ thông tin ảnh hưởng đến kết quả.
- Cập nhật hoặc xóa cache entry sau mutation để tránh đọc dữ liệu cũ.
- Xử lý phạm vi DataLoader trong subscription và các luồng thực thi kéo dài.
- Kiểm thử cache isolation giữa hai request và chẩn đoán lỗi rò rỉ dữ liệu.

## 1. Vì sao DataLoader cần phạm vi theo request?

DataLoader giúp gom nhiều lần tải dữ liệu thành batch và cache kết quả theo key. Ví dụ, một operation lấy nhiều sách và cần tác giả của từng sách:

~~~graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Nếu có 30 sách, resolver `Book.author` có thể yêu cầu 30 lần tải tác giả. DataLoader gom các key trong cùng execution để batch loader truy vấn tác giả theo tập ID. Nếu nhiều field yêu cầu cùng một ID, cache của DataLoader còn giúp tránh tải lặp lại trong phạm vi đó.

Dữ liệu tác giả có thể phụ thuộc vào người dùng, tenant, locale hoặc quyền truy cập. Nếu một DataLoader instance được dùng chung giữa nhiều request, cache có thể trả kết quả được tạo trong security context của request trước cho request sau.

Ví dụ:

- Request của người dùng A tải `Author(id = 42)` trong tenant A.
- Kết quả được cache trong DataLoader dùng chung.
- Request của người dùng B thuộc tenant B cũng tải key `42`.
- Nếu loader trả cache entry của A, dữ liệu của tenant A có thể bị lộ cho B.

Vì vậy, DataLoader thường phải được tạo và sử dụng trong phạm vi một GraphQL execution request. Mỗi request có cache riêng, context riêng và vòng đời riêng.

## 2. Phân biệt BatchLoaderRegistry và DataLoaderRegistry

Spring for GraphQL cung cấp `BatchLoaderRegistry` để đăng ký các batch loader. Cần phân biệt registry dùng để khai báo loader với registry chứa các DataLoader instance được dùng trong lúc thực thi.

| Thành phần | Phạm vi | Vai trò |
| --- | --- | --- |
| `BatchLoaderRegistry` | Cấp ứng dụng, thường là Spring bean singleton | Lưu các định nghĩa và cách đăng ký batch loader |
| `DataLoaderRegistry` | Theo từng GraphQL execution request | Chứa các DataLoader instance dành cho execution đó |
| `DataLoader<K, V>` | Theo request/execution | Nhận key, gom batch và cache kết quả trong phạm vi của nó |
| Batch loader function | Được đăng ký ở cấp ứng dụng, được gọi cho batch của execution | Tải dữ liệu cho tập key nhận được |

`BatchLoaderRegistry` có thể tồn tại lâu như application context vì nó giữ cấu hình đăng ký. Điều đó không có nghĩa các DataLoader instance do nó đăng ký cũng được dùng chung toàn ứng dụng.

Khi Spring GraphQL tạo execution context cho request, các DataLoader được đăng ký vào `DataLoaderRegistry` tương ứng. Resolver của request đó nhận DataLoader từ registry của execution hiện tại.

Đây là ranh giới quan trọng: có thể chia sẻ cấu hình batch loader giữa các request, nhưng không chia sẻ cache và DataLoader instance theo cách làm mất isolation giữa các request.

## 3. Đăng ký batch loader trong Spring for GraphQL

Ví dụ dưới đây dùng reactive repository để batch loader trả về `Flux<Author>`:

~~~java
@Configuration
class AuthorBatchLoaderConfiguration {

    AuthorBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(UUID.class, Author.class)
                .registerBatchLoader((authorIds, environment) ->
                        authorService.findAllInBatchKeyOrder(authorIds)
                );
    }
}
~~~

`forTypePair(UUID.class, Author.class)` đăng ký loader theo cặp key/value type. `registerBatchLoader` nhận tập key cần tải và trả về publisher các giá trị tương ứng. Với batch loader trả về một sequence, service phải bảo đảm thứ tự giá trị khớp thứ tự key theo hợp đồng của loader. Không giả định mọi repository method như `findAllById` đều giữ thứ tự đầu vào; nếu không thể bảo đảm, hãy dùng mapped batch loader.

`BatchLoaderRegistry` là thành phần cấu hình cấp ứng dụng. Spring dùng các đăng ký này để chuẩn bị DataLoader cho từng GraphQL execution. Mỗi execution nhận DataLoader instance riêng, vì vậy cache của request này không trở thành cache mặc định của request khác.

Với loader trả về `Flux<V>`, cần bảo đảm kết quả được liên kết đúng với key theo hợp đồng của batch loader. Nếu việc ánh xạ thứ tự hoặc key không có dữ liệu có thể gây nhầm lẫn, cân nhắc dùng mapped batch loader để trả về `Map<K, V>`.

Ví dụ mapped loader:

~~~java
@Configuration
class AuthorMappedBatchLoaderConfiguration {

    AuthorMappedBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(UUID.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findMapByIds(authorIds)
                );
    }
}
~~~

Trong ví dụ thứ hai, `findMapByIds` trả về publisher của map từ author ID tới author. Những key không có trong map không có giá trị tương ứng; resolver cần xử lý theo nullability của schema.

Chỉ đăng ký một cách mapping cho cùng một DataLoader key/type pair theo thiết kế của ứng dụng. Nếu cần nhiều loader khác nhau cùng dùng kiểu Java giống nhau nhưng có mục đích khác, hãy đặt tên loader riêng và inject theo tên phù hợp.

## 4. Nhận DataLoader trong resolver

Sau khi đăng ký loader, resolver có thể nhận `DataLoader` làm method parameter:

~~~java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;

@Controller
class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<UUID, Author> authorLoader) {

        return authorLoader.load(book.getAuthorId());
    }
}
~~~

Resolver không gọi repository trực tiếp. Nó gửi key vào DataLoader và trả về `CompletableFuture` cho GraphQL. DataLoader có thể gom các key được yêu cầu trong cùng execution thành batch.

Kiểu generic của `DataLoader<K, V>` cần tương thích với loader đã đăng ký. Trong ví dụ:

- `UUID` là kiểu key.
- `Author` là kiểu giá trị.
- `book.getAuthorId()` cung cấp key cho lần tải.

Nếu ứng dụng có nhiều loader cùng key/value type, cần phân biệt chúng bằng tên registration và qualifier theo cơ chế Spring for GraphQL hỗ trợ. Không để hai loader khác mục đích vô tình dùng chung một tên.

## 5. Vòng đời của DataLoader trong một request

Có thể mô tả vòng đời điển hình như sau:

~~~mermaid
flowchart TD
    A["Nhận GraphQL request"] --> B["Tạo execution context"]
    B --> C["Tạo DataLoaderRegistry cho execution"]
    C --> D["Đăng ký DataLoader instances"]
    D --> E["Resolver gọi load(key)"]
    E --> F["Gom key và kiểm tra cache"]
    F --> G["Dispatch batch loader"]
    G --> H["Ghi kết quả vào cache của request"]
    H --> I["Hoàn tất GraphQL response"]
    I --> J["Kết thúc vòng đời registry của execution"]
~~~

Một request thường đi qua các bước:

1. Spring GraphQL nhận operation và variables.
2. Execution được tạo cùng context của request.
3. DataLoader registry tương ứng được chuẩn bị từ các đăng ký batch loader.
4. Resolver gọi `load(key)` khi GraphQL xử lý field.
5. Các key được gom lại và dispatch cho batch loader.
6. Kết quả được trả về cho các resolver đang chờ và được cache trong DataLoader của execution.
7. Execution hoàn tất; DataLoader registry của execution không được giữ lại để dùng cho request độc lập tiếp theo.

Không lưu DataLoader nhận từ resolver vào field của controller singleton, static field hoặc một cache toàn cục. Không truyền instance đó sang request khác.

## 6. Cache theo key trong cùng request

DataLoader thường bật caching theo key. Khi một key được yêu cầu nhiều lần trong cùng request, các lần gọi có thể dùng chung kết quả đang tải hoặc kết quả đã có trong cache.

Ví dụ:

~~~java
CompletableFuture<Author> first = authorLoader.load(authorId);
CompletableFuture<Author> second = authorLoader.load(authorId);
~~~

Nếu cache của loader được bật, hai lần gọi cùng key trong cùng DataLoader instance thường được khử trùng lặp. Batch loader không cần tải lại cùng một key nhiều lần.

Điều này có ích khi:

- Nhiều sách cùng tham chiếu một tác giả.
- Hai nested field cùng cần một entity theo ID.
- Một fragment được dùng ở nhiều nhánh selection set.
- Resolver khác nhau cùng truy vấn một key trong một operation.

Cache này không phải cache liên request. Một GraphQL request mới nhận DataLoader instance mới và thực hiện tải dữ liệu theo execution mới, trừ khi ứng dụng chủ động thiết kế thêm cache ở tầng service hoặc distributed cache.

## 7. Hai request độc lập không dùng chung cache

Giả sử hai request cùng tải author ID `42`:

~~~text
Request A
  DataLoader A
    load(42) -> batch loader -> Author 42
    cache A[42] = Author 42

Request B
  DataLoader B
    load(42) -> batch loader -> Author 42
    cache B[42] = Author 42
~~~

Cùng một key không có nghĩa hai request phải chia sẻ cùng một lần tải. Việc tải lại ở request B là hành vi bình thường nếu không có cache tầng cao hơn.

Phạm vi riêng bảo đảm:

- Request A không nhìn thấy cache entry được tạo trong request B.
- Principal hoặc tenant của request trước không tự động ảnh hưởng request sau.
- Lỗi hoặc kết quả tạm thời trong một execution không trở thành cache mặc định cho execution khác.
- Request mới có cơ hội đọc trạng thái dữ liệu mới nhất từ nguồn dữ liệu theo consistency model của ứng dụng.

Nếu muốn cache dữ liệu qua nhiều request để giảm tải database, hãy dùng cache ở service/repository hoặc distributed cache với key và chính sách invalidation rõ ràng. Đừng biến DataLoader thành singleton cache chỉ để đạt mục tiêu đó.

## 8. Request context và dữ liệu phụ thuộc người gọi

Batch loader đôi khi cần thêm thông tin ngoài key, ví dụ:

- Tenant hiện tại.
- Principal hoặc quyền truy cập.
- Locale dùng để dịch nội dung.
- Correlation ID để tracing.
- Một số lựa chọn thực thi ổn định trong suốt request.

Spring for GraphQL hỗ trợ truyền context của execution tới batch loader thông qua `BatchLoaderEnvironment` và GraphQL context. Hãy lấy thông tin request từ context được framework quản lý hoặc từ cơ chế context propagation đã cấu hình.

Ví dụ khái niệm về phạm vi dữ liệu:

~~~text
GraphQL request context
  principal = user-17
  tenantId  = tenant-A
  locale    = vi-VN

Batch loader
  keys      = [author-1, author-2, author-3]
  scope     = tenant-A
  result    = authors visible to user-17 in tenant-A
~~~

Không lưu principal, tenant hoặc locale của một request vào field mutable của bean singleton dùng để đăng ký loader. Bean đăng ký có thể sống lâu hơn request; state request phải được truyền theo execution context.

Nếu dùng reactive pipeline, cần bảo đảm context được truyền qua Reactor Context theo cơ chế phù hợp. Không giả định `ThreadLocal` tự động có giá trị khi batch loader chạy trên scheduler khác.

## 9. Bảo mật tenant và quyền truy cập trong batch loader

Một DataLoader per request giúp cô lập cache giữa các request, nhưng không tự thực hiện authorization. Batch loader vẫn phải giới hạn dữ liệu theo tenant và quyền của người gọi.

Ví dụ service nhận tenant ID được xác định từ context đáng tin cậy:

~~~java
@Service
class AuthorService {

    private final AuthorRepository repository;

    AuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    public Map<UUID, Author> findVisibleByIds(
            Collection<UUID> ids,
            UUID tenantId) {

        return repository.findVisibleByIdsAndTenantId(ids, tenantId)
                .stream()
                .collect(Collectors.toMap(
                        Author::getId,
                        Function.identity()
                ));
    }
}
~~~

Batch loader phải lấy `tenantId` từ context của request rồi gọi service với phạm vi đó. Không lấy tenant từ argument tùy ý do client gửi lên rồi tin tưởng nó như danh tính đã xác thực.

Ngay cả trong cùng một request, batch loader cũng cần cân nhắc authorization theo từng key. Có thể một số author trong batch được phép xem còn một số khác nằm ngoài phạm vi. Không nên trả tất cả kết quả chỉ vì một phần tử trong batch hợp lệ.

Các lựa chọn thường gặp:

- Lọc ngay trong truy vấn repository theo tenant và quyền.
- Trả map chỉ gồm các key mà người dùng được phép truy cập.
- Ánh xạ key ngoài phạm vi thành `null` hoặc lỗi theo schema và chính sách bảo mật.
- Không để thông báo lỗi tiết lộ tài nguyên của tenant khác.

## 10. Cache key phải đại diện đầy đủ cho kết quả

DataLoader cache theo key. Nếu kết quả phụ thuộc vào nhiều yếu tố nhưng key chỉ chứa ID, cache có thể trả nhầm kết quả ngay cả trong cùng request.

Ví dụ resolver nhận thêm locale:

~~~graphql
type Author {
    id: ID!
    biography(locale: String!): String
}

type Query {
    author(id: ID!): Author
}
~~~

Nếu loader chỉ dùng `authorId` làm key, hai lần gọi sau có thể khác locale:

~~~graphql
query {
    author(id: "author-42") {
        vietnamese: biography(locale: "vi")
        english: biography(locale: "en")
    }
}
~~~

Hai field có cùng author ID nhưng cần hai kết quả khác nhau. Nếu cache key chỉ là ID, lần gọi thứ hai có thể nhận kết quả đã cache từ lần đầu.

Thiết kế key tổng hợp:

~~~java
public record BiographyKey(UUID authorId, String locale) {
}
~~~

Loader dùng `BiographyKey`:

~~~java
DataLoader<BiographyKey, String> biographyLoader;
~~~

Khi gọi:

~~~java
biographyLoader.load(new BiographyKey(authorId, locale));
~~~

Key cần bao gồm mọi chiều dữ liệu làm thay đổi kết quả, chẳng hạn ID, locale, projection hoặc chế độ hiển thị. Với tenant/principal ổn định trong một request, có thể lấy scope từ context; tuy nhiên, nếu cùng loader được gọi trong một execution với nhiều scope khác nhau, scope đó cũng phải được đưa vào key hoặc loader phải được tách riêng theo scope.

## 11. Khi nào cần clear hoặc prime cache?

Cache theo request có thể trở nên cũ khi chính operation thực hiện mutation rồi tiếp tục đọc cùng key bằng DataLoader đó.

Ví dụ một mutation cập nhật tác giả:

~~~java
@MutationMapping
public Author updateAuthor(
        @Argument("id") UUID id,
        @Argument("input") UpdateAuthorInput input,
        DataLoader<UUID, Author> authorLoader) {

    Author updated = authorService.update(id, input);

    authorLoader.clear(id).prime(id, updated);

    return updated;
}
~~~

Sau khi ghi dữ liệu thành công:

- `clear(id)` xóa cache entry cũ của key.
- `prime(id, updated)` đưa giá trị mới vào cache.
- Những resolver tiếp theo trong cùng execution có thể nhận giá trị vừa cập nhật.

Nếu không có giá trị mới để prime, chỉ cần clear key để lần tải tiếp theo đọc lại từ nguồn dữ liệu. Khi mutation ảnh hưởng nhiều key hoặc quan hệ, cần xác định các loader/cache entry liên quan để invalidate đúng phạm vi.

Không gọi `clearAll()` một cách tùy tiện nếu chỉ một key thay đổi, vì điều đó làm mất lợi ích cache của các key khác trong request. Ngược lại, khi mutation thay đổi dữ liệu ảnh hưởng toàn bộ kết quả của loader, có thể cần clear nhiều key hoặc toàn bộ cache theo chính sách rõ ràng.

## 12. DataLoader trong subscription và execution kéo dài

GraphQL subscription có vòng đời dài hơn một Query thông thường: một operation có thể nhận nhiều event và tạo nhiều kết quả theo thời gian.

Không nên giữ DataLoader trong singleton controller hoặc bean để dùng xuyên suốt mọi event và mọi subscriber. Mỗi execution cần có context và registry phù hợp với phạm vi thực thi mà Spring GraphQL quản lý.

Khi thiết kế subscription:

- Không dùng cache của subscriber A cho subscriber B.
- Không để tenant/principal của subscriber này ảnh hưởng subscriber khác.
- Xác định dữ liệu nào cần được tải mới cho từng event.
- Tránh cache entry tồn tại lâu hơn tính hợp lệ của dữ liệu.
- Kiểm tra hành vi registry và context theo transport/version đang dùng, nhất là khi connection sống lâu nhưng có nhiều operation.

Một WebSocket connection có thể tồn tại lâu, nhưng không nên mặc định DataLoader cache phải tồn tại bằng vòng đời connection. Connection, subscription operation và một lần GraphQL execution là các phạm vi khác nhau.

## 13. Batch size và giới hạn tài nguyên

Request scope giúp cô lập cache, nhưng một request vẫn có thể yêu cầu rất nhiều key. Nếu client gửi operation lớn, một batch có thể chứa số lượng key đáng kể.

Cần cân nhắc:

- Giới hạn số phần tử trong list và độ sâu selection set.
- Giới hạn batch size bằng `DataLoaderOptions` hoặc cơ chế tương ứng của loader.
- Chia batch thành các phần phù hợp với giới hạn `IN` clause hoặc API downstream.
- Đặt timeout cho truy vấn batch.
- Theo dõi số key mỗi batch, số lần dispatch và thời gian xử lý.
- Tránh giữ object lớn trong cache quá lâu nếu operation có lượng dữ liệu rất lớn.

Ví dụ khái niệm: nếu database chỉ xử lý hiệu quả tối đa vài trăm ID trong một truy vấn, batch loader nên chia tập key thành các nhóm nhỏ thay vì tạo một câu truy vấn có hàng chục nghìn tham số.

Request scope không thay thế giới hạn truy vấn. Nó chỉ xác định nơi cache và DataLoader instance được sở hữu.

## 14. Lỗi thường gặp về phạm vi DataLoader

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Người dùng khác tenant nhận dữ liệu cũ | DataLoader instance hoặc cache bị chia sẻ giữa request | Tạo DataLoader registry/instance theo execution |
| Hai request luôn dùng chung kết quả | Đặt DataLoader trong singleton hoặc static field | Chỉ inject DataLoader theo resolver execution |
| Cùng ID nhưng locale trả sai nội dung | Cache key chỉ chứa ID, thiếu locale | Dùng composite key hoặc loader riêng |
| Batch loader trả dữ liệu không đúng người dùng | Không áp dụng principal/tenant scope | Lấy scope từ request context và lọc trong repository |
| Mutation xong nested field vẫn trả giá trị cũ | Cache entry trong request chưa được invalidate | `clear(key)` rồi `prime(key, value)` hoặc clear |
| DataLoader cache quá nhiều key | Operation quá lớn hoặc không giới hạn input | Giới hạn query, list size và batch size |
| Subscription nhận dữ liệu của subscriber khác | Dùng chung loader/cache ở cấp connection hoặc singleton | Tách registry theo execution và subscriber |
| Batch loader không thấy tenant hoặc principal | Context propagation chưa được cấu hình | Dùng GraphQL context/BatchLoaderEnvironment và truyền context đúng cách |
| Cùng key bị tải lặp | Cache bị tắt hoặc key không chuẩn hóa | Kiểm tra cache option và cách tạo key |
| Loader hoạt động đúng ở dev nhưng sai khi tải đồng thời | Có mutable request state trong bean singleton | Loại bỏ state request khỏi singleton và test concurrency |

## 15. Kiểm thử cache isolation giữa hai request

Một bài kiểm thử quan trọng là xác minh cùng key trong hai GraphQL request độc lập không dùng chung DataLoader cache.

Có thể dùng service mock với bộ đếm số lần batch load hoặc repository call. Ví dụ về kịch bản:

1. Gửi request A để tải author ID `42`.
2. Gửi request B độc lập cũng tải author ID `42`.
3. Xác minh batch loader được gọi cho cả hai request nếu không có cache tầng service.
4. Xác minh kết quả của mỗi request được giới hạn theo tenant/principal tương ứng.
5. Xác minh hai request không nhìn thấy giá trị được `prime` trong DataLoader của nhau.

Ví dụ operation có thể dùng trong cả hai request:

~~~graphql
query {
    book(id: "book-42") {
        author {
            id
            name
        }
    }
}
~~~

Kịch bản test cần cung cấp authentication/context khác nhau cho từng request, chẳng hạn tenant A và tenant B. Nếu test chỉ dùng cùng principal và cùng dữ liệu, nó có thể không phát hiện lỗi cache leakage.

### 15.1. Kiểm thử cache trong cùng request

Cũng cần kiểm tra hành vi khác: hai field trong cùng request tải cùng key có thể dùng chung cache entry.

Có thể tạo operation yêu cầu cùng một tác giả từ hai nhánh khác nhau hoặc nhiều sách cùng tham chiếu một tác giả. Xác minh batch loader không tải lại cùng key khi cache được bật.

Hai loại test này bổ sung cho nhau:

- **Same request:** xác minh batching và deduplication hoạt động.
- **Different requests:** xác minh cache isolation và context không bị rò rỉ.

## 16. Quy tắc thiết kế phạm vi DataLoader

Khi triển khai DataLoader trong Spring for GraphQL, hãy áp dụng các quy tắc:

1. Đăng ký định nghĩa batch loader ở cấp ứng dụng qua `BatchLoaderRegistry`.
2. Để Spring tạo và quản lý DataLoader registry cho từng execution.
3. Inject DataLoader vào resolver theo execution hiện tại.
4. Không lưu DataLoader instance vào singleton, static field hoặc cache toàn cục.
5. Xem cache DataLoader là cache theo request, không phải cache liên request.
6. Đưa mọi chiều ảnh hưởng kết quả vào cache key hoặc context phù hợp.
7. Áp dụng tenant và authorization trong batch query.
8. Clear hoặc prime cache sau mutation khi cần.
9. Kiểm soát batch size và kích thước operation.
10. Kiểm thử cùng key trong một request và giữa hai request độc lập.

## 17. Tổng kết

Phạm vi DataLoader theo request giúp gom batch và cache các lần tải dữ liệu trong một GraphQL execution mà vẫn giữ isolation giữa những request độc lập. Trong Spring for GraphQL, `BatchLoaderRegistry` là nơi đăng ký cấu hình loader ở cấp ứng dụng; `DataLoaderRegistry` và các DataLoader instance được dùng cho execution cụ thể.

Không chia sẻ DataLoader instance hoặc cache của nó qua singleton, static field hay nhiều người dùng. Khi dữ liệu phụ thuộc tenant, principal, locale hoặc quyền truy cập, batch loader phải nhận context đáng tin cậy và cache key phải đại diện đầy đủ cho kết quả. Sau mutation, hãy clear hoặc prime các key bị ảnh hưởng. Kiểm thử cả deduplication trong cùng request lẫn cache isolation giữa hai request giúp phát hiện sớm lỗi dữ liệu cũ và rò rỉ dữ liệu.

