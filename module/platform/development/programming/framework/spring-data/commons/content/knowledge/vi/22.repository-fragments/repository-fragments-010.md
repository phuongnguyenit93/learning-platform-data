# RepositoryMethodContext và RepositoryMetadataAccess trong phiên bản có tính năng

Một repository fragment dùng chung có thể cần biết repository nào đang gọi nó. Ví dụ, cùng một fragment tìm kiếm được ghép vào `ProductRepository` và `ArticleRepository`, nhưng mỗi repository phải truy vấn một chỉ mục khác nhau. Nếu chỉ nhìn vào đối tượng implementation của fragment, ứng dụng chưa chắc biết được domain type của lời gọi hiện tại.

Trong những phiên bản Spring Data Commons có hỗ trợ, `RepositoryMethodContext` cung cấp ngữ cảnh của lời gọi repository, còn marker interface `RepositoryMetadataAccess` cho biết một fragment cần truy cập metadata đó. Hai API này giúp fragment dùng lại thông tin repository mà không buộc mỗi repository phải viết một bản sao implementation.

Bài học thuộc chương **Repository fragment** của **Spring Data Commons**, tập trung vào metadata và cách ghép fragment. Khả năng truy vấn, lưu dữ liệu, auditing hoặc tìm kiếm của từng kho dữ liệu vẫn do module và công nghệ tương ứng quyết định.

## 1. Điều kiện áp dụng: dependency thực tế phải có tính năng

Không áp dụng ví dụ chỉ vì dự án có dependency mang tên Spring Data. Cần phân biệt tên thư viện với tập API mà phiên bản đang dùng thực sự cung cấp.

Những kiểu được sử dụng trong bài là:

```java
org.springframework.data.repository.core.RepositoryMethodContext
org.springframework.data.repository.core.support.RepositoryMetadataAccess
org.springframework.data.repository.core.support.RepositoryFactoryBeanSupport
```

Đường cấu hình tường minh trong bài còn cần API `setExposeMetadata(true)` trên repository factory bean của phiên bản tương ứng.

Nếu IDE hoặc trình biên dịch không tìm thấy các kiểu hay phương thức này, trước hết kiểm tra phiên bản Spring Data Commons thực tế đã được quản lý trong dự án. Với ứng dụng Spring Boot, cần lưu ý bộ phiên bản Spring Data được dependency management của Boot lựa chọn; không mặc định phiên bản thư viện bằng phiên bản Boot.

Không tự tạo một interface cùng tên để làm hết lỗi import. Marker do ứng dụng tự định nghĩa không làm hạ tầng Spring Data nhận diện nhu cầu metadata. Cũng không nên thay riêng một artifact Spring Data bằng một phiên bản khác mà bỏ qua tính tương thích của cả bộ thư viện.

Bài này không gắn tính năng vào một số phiên bản cố định. Điều kiện sử dụng là bộ dependency đang chạy có các API và cơ chế kích hoạt tương ứng. Nếu dự án chưa có tính năng, có thể truyền domain type hoặc cấu hình chỉ mục một cách tường minh cho collaborator thay vì giả định context luôn tồn tại.

## 2. Hai API đảm nhận hai vai trò khác nhau

| Thành phần | Vai trò | Không nên hiểu thành |
| --- | --- | --- |
| `RepositoryMethodContext` | Cho phép lấy metadata của lời gọi repository hiện tại | Một object chứa toàn bộ dữ liệu nghiệp vụ hoặc toàn bộ trạng thái persistence |
| `RepositoryMetadataAccess` | Marker cho fragment implementation cần metadata | Annotation, lớp context hoặc API đọc metadata trực tiếp |
| `RepositoryMetadata` | Mô tả repository, như repository interface, domain type và ID type | Mapping đầy đủ tên bảng, collection, index hoặc tenant |
| `RepositoryFactoryBeanSupport#setExposeMetadata` | Cấu hình factory để expose metadata cho repository được tạo | Một thiết lập tự động áp dụng cho mọi object do ứng dụng tự tạo |

Ví dụ truy cập các thông tin cơ bản trong một lời gọi hợp lệ:

```java
import java.lang.reflect.Method;

import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.RepositoryMethodContext;

RepositoryMethodContext context = RepositoryMethodContext.getContext();
RepositoryMetadata repository = context.getRepository();

Class<?> repositoryInterface = repository.getRepositoryInterface();
Class<?> domainType = repository.getDomainType();
Class<?> idType = repository.getIdType();
Method method = context.getMethod();
```

Các biến trên có ý nghĩa khác nhau:

- `repositoryInterface` cho biết kiểu repository được metadata mô tả.
- `domainType` là domain type của repository, chẳng hạn `Product`.
- `idType` là kiểu định danh được repository khai báo, chẳng hạn `Long`.
- `method` mô tả phương thức của lời gọi hiện tại theo cơ chế phân giải của hạ tầng.

Nếu `ProductRepository` trả về một projection hoặc DTO từ một phương thức, domain type của repository vẫn có thể là `Product`. Không lấy `getDomainType()` để thay thế mọi phân tích về kiểu trả về của từng phương thức.

Tương tự, `method.getDeclaringClass()` có thể là một superinterface hoặc interface fragment. Không giả định nó luôn bằng repository interface cuối cùng; muốn lấy repository interface, dùng metadata của repository.

## 3. Vì sao metadata không được expose mặc định?

Để cung cấp context của lời gọi hiện tại, hạ tầng cần gắn và quản lý thông tin invocation quanh lời gọi repository. Công việc này có chi phí bổ sung. Vì vậy, việc expose metadata được tắt mặc định và cần được bật khi có nhu cầu.

Luồng sử dụng thông thường là:

```text
Người gọi
   |
   v
Repository proxy có bật expose metadata
   |
   +-- Thiết lập context cho lời gọi hiện tại
   |
   v
Fragment implementation
   |
   +-- RepositoryMethodContext.getContext()
   +-- Đọc domain type / repository interface / method
   +-- Thực hiện logic của fragment
   |
   v
Lời gọi kết thúc, context của lời gọi được dọn hoặc khôi phục
```

Metadata ở đây thuộc phạm vi một lời gọi đang diễn ra. Nó không phải một registry toàn cục để bất kỳ bean nào cũng có thể hỏi “repository gần nhất là gì”.

Chỉ thêm dependency chứa `RepositoryMethodContext` chưa bật exposure. Chỉ gọi `getContext()` cũng không tự yêu cầu hạ tầng tạo context cho lời gọi ấy.

## 4. Cách bật phù hợp với fragment: triển khai marker

Trong phiên bản hỗ trợ cơ chế marker, implementation của fragment có thể triển khai `RepositoryMetadataAccess`:

```java
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class SearchFragmentImpl
        implements SearchFragment, RepositoryMetadataAccess {

    // Constructor và các phương thức của fragment.
}
```

`RepositoryMetadataAccess` là marker interface: không có một phương thức nghiệp vụ cần được cài đặt để “trả metadata”. Hạ tầng nhận diện marker trên fragment implementation và bật exposure cho repository có composition cần metadata.

Cần đặt marker trên implementation được Spring Data thực sự sử dụng. Một lớp khác có triển khai marker nhưng không được ghép vào repository không giúp lời gọi đến fragment hiện tại có context.

Cũng không cần ép interface nghiệp vụ `SearchFragment` phải công khai chi tiết hạ tầng này cho mọi người dùng. Đặt marker ở implementation thể hiện rằng nhu cầu đọc metadata thuộc cách triển khai của fragment.

Cơ chế marker giúp nhu cầu metadata đi cùng fragment. Tuy nhiên, khi một repository đã được bật exposure do chứa fragment này, không nên hiểu rằng chi phí hạ tầng chắc chắn chỉ phát sinh đúng tại một dòng `getContext()` trong fragment.

## 5. Ví dụ đầy đủ về ý tưởng: fragment tìm kiếm dùng domain type để chọn index

Giả sử ứng dụng có hai domain type là `Product` và `Article`, cùng các repository được module lưu trữ phù hợp quản lý. Dịch vụ tìm kiếm bên ngoài dùng hai index:

| Domain type | Index tìm kiếm |
| --- | --- |
| `Product` | `catalog-products` |
| `Article` | `editorial-articles` |

Các đoạn mã dưới đây minh họa những kiểu cần thiết cho fragment. Mỗi public type nằm trong một tệp Java riêng. Entity, kết nối kho dữ liệu, search backend và cấu hình scan repository phải do ứng dụng cung cấp.

### 5.1. Hợp đồng của fragment và kết quả tìm kiếm

```java
import java.util.List;

public interface SearchFragment {
    List<SearchHit> searchIndex(String text);
}
```

```java
public record SearchHit(String id, String title) {
}
```

Ví dụ trả về một kiểu kết quả tìm kiếm riêng nên fragment không cần ép kiểu metadata từ `Class<?>` thành `Class<T>`. Domain type được dùng để chọn index, không được dùng để khẳng định kết quả tìm kiếm là entity đã được persistence context quản lý.

### 5.2. Tách client tìm kiếm và quy tắc chọn index

```java
import java.util.List;

public interface SearchClient {
    List<SearchHit> search(String indexName, String text);
}
```

```java
public interface IndexNameResolver {
    String indexNameFor(Class<?> domainType);
}
```

Đây là hai abstraction do ứng dụng định nghĩa, không phải API có sẵn của Spring Data Commons. `SearchClient` được hiện thực bằng công nghệ tìm kiếm mà ứng dụng chọn. `IndexNameResolver` quản lý ánh xạ từ domain type sang index.

Không mặc định dùng `domainType.getSimpleName().toLowerCase()` làm tên index thật. Hai lớp khác package có thể trùng simple name, và tên index có thể cần tuân theo một quy ước riêng của hệ thống.

Ví dụ cấu hình ánh xạ tường minh:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class SearchIndexConfiguration {

    @Bean
    IndexNameResolver indexNameResolver() {
        Map<Class<?>, String> indexes = Map.of(
                Product.class, "catalog-products",
                Article.class, "editorial-articles"
        );

        return domainType -> {
            String indexName = indexes.get(domainType);
            if (indexName == null) {
                throw new IllegalArgumentException(
                        "No search index configured for " + domainType.getName()
                );
            }
            return indexName;
        };
    }
}
```

### 5.3. Implementation đọc context ngay trong lời gọi fragment

```java
import java.util.List;
import java.util.Objects;

import org.springframework.data.repository.core.RepositoryMethodContext;
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class SearchFragmentImpl
        implements SearchFragment, RepositoryMetadataAccess {

    private final SearchClient client;
    private final IndexNameResolver indexNameResolver;

    public SearchFragmentImpl(
            SearchClient client,
            IndexNameResolver indexNameResolver) {
        this.client = client;
        this.indexNameResolver = indexNameResolver;
    }

    @Override
    public List<SearchHit> searchIndex(String text) {
        Objects.requireNonNull(text, "text must not be null");

        RepositoryMethodContext context = RepositoryMethodContext.getContext();
        Class<?> domainType = context.getRepository().getDomainType();
        String indexName = indexNameResolver.indexNameFor(domainType);

        return client.search(indexName, text);
    }
}
```

Có ba điểm quan trọng trong implementation:

1. Context được lấy bên trong phương thức đang được repository proxy gọi, không lấy khi khởi tạo bean.
2. Domain type được lấy cho từng invocation, không lưu thành một field đại diện cho mọi repository.
3. Sau khi chọn được index, fragment chuyển cho client những giá trị cụ thể. Client không cần biết `RepositoryMethodContext` tồn tại.

Hậu tố `Impl` trong `SearchFragmentImpl` tuân theo quy ước mặc định để tìm implementation của fragment. Package và cấu hình dò tìm của dự án phải cho phép Spring Data nhận diện đúng implementation; nếu đổi postfix hoặc đăng ký fragment theo cách khác, cần tuân theo cấu hình đó.

### 5.4. Ghép cùng một hợp đồng vào hai repository

```java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, SearchFragment {
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface ArticleRepository
        extends CrudRepository<Article, String>, SearchFragment {
}
```

Khi gọi qua các repository proxy được cấu hình đúng:

```java
productRepository.searchIndex("spring");
// SearchClient nhận indexName = "catalog-products".

articleRepository.searchIndex("spring");
// SearchClient nhận indexName = "editorial-articles".
```

Fragment đọc metadata của repository đang gọi nó. Nó không cần một nhánh kiểm tra tên bean repository và không nên lưu domain type của lời gọi đầu tiên để dùng cho mọi lời gọi sau.

### 5.5. Context không làm thay đổi khả năng của kho dữ liệu

Lời gọi đến `SearchClient` ở ví dụ là logic ứng dụng. Nó không có nghĩa mọi repository CRUD đều tự có một search engine, hoặc Spring Data Commons tự thực thi truy vấn full-text cho mọi store.

Nếu dùng JPA, MongoDB hay một store khác, entity mapping, transaction và API ghi dữ liệu vẫn tuân theo module tương ứng. Nếu cần auditing hoặc projection, cũng phải xem đúng khả năng và cấu hình của module đang dùng.

## 6. Cách bật tường minh bằng repository factory bean

Trong một số trường hợp, ứng dụng muốn cấu hình exposure ở tầng factory thay vì để nhu cầu đó được phát hiện qua marker. Với phiên bản có API hỗ trợ, có thể dùng `BeanPostProcessor` để đặt `setExposeMetadata(true)`.

Ví dụ sau chỉ nhắm đến repository có bean name `productRepository`:

```java
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.repository.core.support.RepositoryFactoryBeanSupport;

@Configuration(proxyBeanMethods = false)
class RepositoryMetadataConfiguration {

    @Bean
    static BeanPostProcessor exposeProductRepositoryMetadata() {
        return new BeanPostProcessor() {

            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {
                if ("productRepository".equals(beanName)
                        && bean instanceof RepositoryFactoryBeanSupport<?, ?, ?> factory) {
                    factory.setExposeMetadata(true);
                }
                return bean;
            }
        };
    }
}
```

Bean name trong ví dụ là một điều kiện cấu hình của ứng dụng. Nếu dự án tùy chỉnh cách đặt tên repository bean, cần dùng tên thực tế; không suy ra rằng mọi repository của một domain type đều có cùng tên này.

Phương thức `@Bean` được khai báo `static` để đăng ký post-processor mà không cần khởi tạo sớm instance của lớp cấu hình chứa nó. Processor đặt thuộc tính trước khi factory bean hoàn tất quá trình khởi tạo repository.

Đây là một hướng cấu hình thay thế hoặc phục vụ nhu cầu riêng của ứng dụng. Với ví dụ fragment đã triển khai marker và hạ tầng hỗ trợ cơ chế đó, không cần thêm một post-processor chỉ để bật lại cùng tính năng.

Nếu chỉ bật bằng processor trên, `ArticleRepository` không tự được bật chỉ vì dùng cùng kiểu fragment. Khi không có marker, phạm vi exposure phải bao phủ từng repository thực sự cần context. Có thể mở rộng điều kiện chọn repository một cách có chủ đích.

Tránh bỏ điều kiện tên rồi áp dụng cho tất cả factory bean chỉ vì một fragment cần metadata. Mở rộng phạm vi exposure nên đi kèm một nhu cầu cụ thể, vì đó là lựa chọn có ảnh hưởng đến mọi lời gọi repository nằm trong phạm vi ấy.

## 7. Những thời điểm không có context hợp lệ

`RepositoryMethodContext.getContext()` yêu cầu có metadata của lời gọi đang được expose. Khi không có context hiện tại, API ném `IllegalStateException`; nó không trả về một repository mặc định để ứng dụng tiếp tục xử lý.

| Nơi đọc context | Điều cần lưu ý |
| --- | --- |
| Bên trong fragment được gọi qua repository proxy đã bật exposure | Đây là đường sử dụng chính của ví dụ |
| Constructor của fragment | Chưa có một lời gọi repository đang được xử lý |
| Phương thức `@PostConstruct` | Khởi tạo bean không phải invocation repository phục vụ nghiệp vụ |
| Unit test gọi trực tiếp `new SearchFragmentImpl(...)` | Không đi qua repository proxy nên marker không tự tạo context |
| Service tùy ý gọi `getContext()` trước khi gọi repository | Chưa có context của lời gọi repository sắp diễn ra |
| Task chạy ở một thread khác | Không được mặc định mang theo context của thread gọi repository |

Không xử lý lỗi thiếu context bằng cách âm thầm chọn index mặc định. Với một fragment dùng chung cho nhiều domain type, cách fallback đó có thể gửi truy vấn đến sai nơi. Nếu thiết kế cần hoạt động cả khi không qua repository, hãy cung cấp dependency hoặc tham số tường minh cho phần logic dùng chung.

### 7.1. Không đọc context một lần rồi cache trong field

Thiết kế sau sai về phạm vi dữ liệu:

```java
// Sai: khởi tạo bean không cung cấp context của một lời gọi repository.
private final Class<?> domainType = RepositoryMethodContext.getContext()
        .getRepository()
        .getDomainType();
```

Chuyển việc gán sang “lần gọi đầu tiên” cũng không sửa được toàn bộ vấn đề. Nếu cùng implementation phục vụ nhiều repository, field đó vẫn có thể giữ domain type của lời gọi trước.

Nếu cần cache kết quả ánh xạ domain type sang index, cache theo một khóa phù hợp như `Class<?>`, đồng thời bảo đảm cấu trúc cache an toàn khi truy cập đồng thời. Không cache một context invocation rồi dùng lại cho lời gọi khác.

### 7.2. Context mô tả lời gọi hiện tại, không mô tả mọi lời gọi bên ngoài

Nếu một fragment gọi tiếp repository khác, code bên trong lời gọi repository thứ hai phải được hiểu theo context đang có hiệu lực tại vị trí đó. Đừng dùng một lần đọc context ở tầng sâu để suy luận toàn bộ chuỗi repository đã được gọi trước đó.

Nếu cần theo dõi chuỗi nghiệp vụ hoặc correlation ID, hãy dùng cơ chế được thiết kế cho mục đích đó. Metadata của một repository invocation không phải bản ghi toàn bộ call chain.

## 8. Ranh giới thread và xử lý bất đồng bộ

Context của repository gắn với phạm vi thực thi lời gọi và cơ chế quản lý context của hạ tầng. Không mặc định rằng nó tự truyền sang executor, `CompletableFuture`, phương thức `@Async` hoặc một đoạn xử lý reactive được thực thi sau đó.

Ví dụ ý tưởng dễ sai:

```java
// Không dựa vào việc context của repository tự xuất hiện trong task này.
executor.execute(() -> {
    Class<?> domainType = RepositoryMethodContext.getContext()
            .getRepository()
            .getDomainType();
    // ...
});
```

Cách tổ chức phù hợp hơn là đọc thông tin cần thiết khi còn ở trong lời gọi hợp lệ, rồi truyền giá trị đã xác định vào công việc tiếp theo:

```java
// Thực hiện bên trong lời gọi fragment có context hợp lệ.
Class<?> domainType = RepositoryMethodContext.getContext()
        .getRepository()
        .getDomainType();
String indexName = indexNameResolver.indexNameFor(domainType);

// Task chỉ dùng dữ liệu đã được xác định tường minh.
executor.execute(() -> client.search(indexName, text));
```

Đoạn mã chỉ minh họa cách truyền dữ liệu qua ranh giới thread; nó không thay thế hợp đồng trả về đồng bộ của `SearchFragment.searchIndex` ở ví dụ trước. Nếu API thật cần trả kết quả bất đồng bộ, phải thiết kế riêng kiểu trả về, executor và cách xử lý lỗi tương ứng.

Cũng không dùng sự tồn tại của `RepositoryMethodContext` để kết luận một reactive pipeline bất kỳ sẽ có context này ở mọi operator. Tính năng expose invocation metadata không tự đồng nghĩa với cơ chế truyền Reactor Context hoặc mở rộng thời gian sống metadata cho mọi xử lý được trì hoãn.

## 9. Metadata nào nên dùng cho quyết định nào?

### 9.1. Domain type phục vụ chọn cấu hình theo entity

Domain type phù hợp để chọn một cấu hình đã khai báo trước, chẳng hạn index tìm kiếm hoặc một strategy xử lý theo domain. Như ví dụ, ánh xạ `Product.class` sang `catalog-products` là một quyết định của ứng dụng.

Không đồng nhất domain type với tên bảng, collection hoặc index. Những tên ấy có thể nằm trong mapping metadata của module lưu trữ hoặc cấu hình riêng, chứ không được bảo đảm bởi `RepositoryMetadata.getDomainType()`.

### 9.2. Repository interface phục vụ nhận diện hợp đồng repository

Thông tin repository interface có thể giúp chẩn đoán fragment đang được dùng ở đâu hoặc chọn một cấu hình theo repository. Tuy nhiên, nếu cấu hình chỉ phụ thuộc domain type thì dùng domain type trực tiếp thường dễ bảo trì hơn việc so sánh chuỗi tên repository.

### 9.3. Method phục vụ thông tin về lời gọi

`context.getMethod()` cung cấp đối tượng phản chiếu `Method`, có thể hữu ích cho log chẩn đoán hoặc phân tích hợp đồng phương thức. Khi dùng annotation, generic, phương thức kế thừa hoặc bridge method, phải xét các quy tắc phản chiếu và phân giải phương thức tương ứng; không giả định mọi annotation đều có mặt ngay trên một `Method` bất kỳ.

API này không cung cấp sẵn câu SQL đã tạo, execution plan, persistence context, danh tính người dùng hay tenant hiện tại. Tham số nghiệp vụ như chuỗi `text` vẫn được nhận qua tham số phương thức của fragment.

Đặc biệt, metadata repository không phải bằng chứng phân quyền. Việc chọn index theo domain type không thay thế kiểm tra quyền truy cập dữ liệu hoặc điều kiện tenant của ứng dụng.

## 10. Kiểm chứng ví dụ ở hai tầng

### 10.1. Kiểm thử logic thuần không cần context

`IndexNameResolver` và `SearchClient` là các collaborator tường minh, nên có thể kiểm thử riêng mà không tạo repository proxy. Ví dụ, kiểm tra `Product.class` ánh xạ đúng index, domain chưa cấu hình gây lỗi rõ ràng, và client nhận đúng tên index khi được gọi.

Cách tách này giúp phần lớn logic không phụ thuộc trực tiếp vào một context chỉ tồn tại khi lời gọi repository đang diễn ra.

### 10.2. Kiểm thử tích hợp phải đi qua repository proxy

Để xác nhận marker và exposure thật sự hoạt động, cần gọi repository được Spring Data tạo trong ngữ cảnh kiểm thử phù hợp với store. Tạo trực tiếp implementation bằng `new` không xác nhận được việc hạ tầng nhận diện marker.

Có thể dùng một `SearchClient` giả trong cấu hình kiểm thử:

```java
SearchClient fakeClient = (indexName, text) ->
        java.util.List.of(new SearchHit("demo", indexName));
```

Sau khi đăng ký client giả thay cho client thật theo cách cấu hình kiểm thử của dự án, các xác nhận cần có là:

```java
assertEquals(
        "catalog-products",
        productRepository.searchIndex("spring").get(0).title()
);

assertEquals(
        "editorial-articles",
        articleRepository.searchIndex("spring").get(0).title()
);
```

`assertEquals` trong ví dụ là assertion của framework kiểm thử, chẳng hạn JUnit. Các repository vẫn cần entity mapping và cấu hình của module lưu trữ; fake search client chỉ loại bỏ phụ thuộc vào search backend bên ngoài.

Nên kiểm tra thêm:

- Gọi luân phiên hai repository không làm domain type bị giữ lại từ lời gọi trước.
- Repository có domain chưa được ánh xạ bị từ chối rõ ràng.
- Đường cấu hình được chọn thực sự bật exposure: marker hoặc factory configuration.
- Gọi logic cần context ở ngoài repository invocation không bị hiểu nhầm thành một đường sử dụng hợp lệ.

Nếu muốn xác nhận exposure mặc định là tắt, dùng một repository kiểm thử riêng không có marker và không được bật bằng factory configuration. Chỉ bỏ marker khỏi một lớp trong khi một cấu hình toàn cục vẫn bật exposure không tạo ra phép thử cho trạng thái mặc định.

## 11. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không import được API | Phiên bản thực tế chưa có kiểu được sử dụng | Kiểm tra bộ dependency; dùng thiết kế tường minh nếu chưa hỗ trợ |
| `getContext()` ném `IllegalStateException` | Chưa bật exposure hoặc đang gọi ngoài invocation hợp lệ | Kiểm tra marker, factory configuration và đường gọi qua proxy |
| Đã thêm marker nhưng vẫn không có context | Marker nằm trên lớp không được ghép, hoặc fragment bị gọi trực tiếp | Xác nhận implementation được repository sử dụng |
| Processor không bật được repository mong muốn | Điều kiện bean name không khớp hoặc processor không được đăng ký | Kiểm tra phạm vi cấu hình và factory bean thực tế |
| Hai repository cùng truy vấn một index | Domain type hoặc tên index bị cache thành một field dùng chung | Đọc metadata theo invocation, ánh xạ theo khóa domain rõ ràng |
| Có domain type nhưng chọn sai bảng hoặc collection | Đồng nhất Commons metadata với store mapping | Dùng đúng mapping API hoặc cấu hình của module lưu trữ |
| Task bất đồng bộ mất context | Giả định context tự truyền qua thread | Đọc giá trị cần thiết trong invocation rồi truyền tường minh |

Khi chẩn đoán, tách ba câu hỏi: phiên bản có API không, repository có bật exposure không, và đoạn code có chạy trong đúng lời gọi repository không. Sửa một câu hỏi không tự giải quyết hai câu hỏi còn lại.

## 12. Bài tập thực hành

Trong một dự án có phiên bản hỗ trợ tính năng và store đã cấu hình:

1. Tạo `SearchFragment` và implementation triển khai `RepositoryMetadataAccess`.
2. Ghép fragment vào hai repository có domain type khác nhau.
3. Dùng resolver tường minh và search client giả để xác nhận mỗi repository chọn đúng index.
4. Gọi hai repository luân phiên nhiều lần để phát hiện việc lưu nhầm metadata vào state dùng chung.
5. Tách riêng một cấu hình thử nghiệm bỏ marker, rồi bật exposure chỉ cho một repository bằng factory post-processor; giải thích vì sao repository còn lại không được bật bởi cấu hình đó.
6. Thử gọi trực tiếp implementation ngoài repository proxy và giải thích lỗi thiếu context.
7. Nếu đưa xử lý sang executor, truyền index đã xác định vào task thay vì gọi `getContext()` bên trong task.

Mục tiêu là sử dụng metadata đúng phạm vi: fragment khai báo nhu cầu, repository factory cung cấp context khi được bật, và implementation chỉ lấy thông tin của invocation đang diễn ra. Các quyết định về truy vấn, lưu trữ và mapping tiếp tục thuộc về abstraction ứng dụng và module dữ liệu tương ứng.
