# BeforeBindCallback trước khi entity được chuyển thành tham số ghi

## Mục tiêu

Sau bài học này, bạn có thể:

- Xác định chính xác thời điểm `BeforeBindCallback` chạy trong luồng ghi của Spring Data Neo4j (SDN).
- Cài đặt callback imperative để kiểm tra hoặc chuẩn hóa entity trước khi SDN ánh xạ thành dữ liệu ghi.
- Trả về cùng entity hoặc một instance đã được sửa đổi, kể cả với domain object bất biến.
- Đăng ký callback dưới dạng Spring bean và kiểm soát thứ tự khi có nhiều callback.
- Phân biệt `BeforeBindCallback` với auditing, `AfterConvertCallback` và application event.
- Chọn đúng callback imperative hoặc reactive.
- Kiểm thử dữ liệu đã chuẩn hóa thực sự được ghi vào Neo4j.

## 1. BeforeBindCallback nằm ở đâu trong luồng ghi?

Khi ứng dụng gọi `repository.save(entity)` hoặc lưu entity qua `Neo4jTemplate`, SDN cần chuyển domain object thành dữ liệu có thể bind vào câu lệnh Cypher. `BeforeBindCallback` là điểm mở rộng cho phép ứng dụng kiểm tra hoặc thay đổi domain object ngay trước bước ánh xạ đó.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["repository.save(entity) hoặc Neo4jTemplate.save(entity)"] --> B["BeforeBindCallback.onBeforeBind(entity)"]
    B --> C["Neo4jEntityConverter chuyển entity thành Map"]
    C --> D["SDN tạo câu lệnh Cypher và tham số"]
    D --> E["Neo4j Java Driver thực thi"]
    E --> F["Neo4j lưu node và relationship"]
~~~

Callback nhận domain object và trả về domain object. SDN dùng instance được trả về để tạo record dạng `Map<String, Object>`, sau đó dùng record này để tạo tham số cho câu lệnh ghi.

Vì vậy, callback phù hợp cho những thay đổi cần xuất hiện trong dữ liệu được lưu, chẳng hạn:

- Chuẩn hóa tên hoặc mã nghiệp vụ.
- Tạo trường tìm kiếm từ các trường hiện có.
- Kiểm tra một invariant trước khi ghi.
- Bổ sung giá trị mặc định có quy tắc rõ ràng.
- Chuẩn bị metadata thuộc chính entity.

Callback không nhận `Map` tham số Cypher và không trực tiếp tạo câu lệnh Cypher. Nếu cần kiểm soát câu query, hãy dùng repository query, `Neo4jClient` hoặc `Neo4jTemplate` theo đúng use case.

## 2. Hợp đồng của BeforeBindCallback

Interface imperative nằm trong package:

~~~java
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;
~~~

Chữ ký rút gọn:

~~~java
@FunctionalInterface
public interface BeforeBindCallback<T> extends EntityCallback<T> {

    T onBeforeBind(T entity);
}
~~~

Trong đó:

- `T` là kiểu domain entity.
- `onBeforeBind` được gọi trước khi domain object được chuyển thành `Map`.
- Callback có thể trả về chính instance nhận được hoặc một instance khác đã được cập nhật.
- Instance được trả về là instance SDN dùng để tiếp tục quá trình ghi.

Nếu entity là class mutable có setter (ví dụ `MutableProduct`), callback có thể sửa instance tại chỗ:

~~~java
@Component
public class MutableProductBeforeBindCallback
        implements BeforeBindCallback<MutableProduct> {

    @Override
    public MutableProduct onBeforeBind(MutableProduct product) {
        product.setName(product.getName().trim());
        return product;
    }
}
~~~

Với entity bất biến, hãy tạo và trả về instance mới. Không được trả `null`, vì SDN cần một domain object để tiếp tục mapping.

## 3. Ví dụ domain: chuẩn hóa tên Product trước khi lưu

Giả sử Product có hai thuộc tính:

- `name`: tên hiển thị.
- `normalizedName`: tên đã bỏ khoảng trắng đầu/cuối và chuyển về chữ thường để tìm kiếm.

Domain object:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public record Product(
    @Id String id,
    String name,
    String normalizedName
) {
}
~~~

Callback:

~~~java
import java.util.Locale;

import org.springframework.core.annotation.Order;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class NormalizeProductBeforeBind
        implements BeforeBindCallback<Product> {

    @Override
    public Product onBeforeBind(Product product) {
        if (product.name() == null || product.name().isBlank()) {
            throw new IllegalArgumentException(
                "Product name must not be blank"
            );
        }

        String displayName = product.name().trim();
        String normalizedName =
            displayName.toLowerCase(Locale.ROOT);

        return new Product(
            product.id(),
            displayName,
            normalizedName
        );
    }
}
~~~

Callback này tạo một Product mới vì record là bất biến. `name` được chuẩn hóa khoảng trắng; `normalizedName` được tính từ tên sau chuẩn hóa.

Khi lưu:

~~~java
Product product = new Product(
    "product-101",
    "  Graph Database  ",
    null
);

products.save(product);
~~~

SDN gọi callback trước khi mapping. Record được dùng để ghi có các giá trị:

| Property | Giá trị lưu |
|---|---|
| `id` | `product-101` |
| `name` | `Graph Database` |
| `normalizedName` | `graph database` |

Đầu vào ban đầu không cần tự tính `normalizedName`. Quy tắc này được tập trung ở một callback và áp dụng mỗi khi entity Product đi qua luồng ghi của SDN.

## 4. Đăng ký callback như một Spring bean

SDN tự nhận diện các bean triển khai `BeforeBindCallback<T>` trong ApplicationContext. Bạn có thể đăng ký bằng `@Component` như ví dụ trước hoặc khai báo bean trong `@Configuration`:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

@Configuration
public class ProductCallbackConfiguration {

    @Bean
    BeforeBindCallback<Product> normalizeProduct() {
        return product -> {
            if (product.name() == null || product.name().isBlank()) {
                throw new IllegalArgumentException(
                    "Product name must not be blank"
                );
            }

            String displayName = product.name().trim();

            return new Product(
                product.id(),
                displayName,
                displayName.toLowerCase(Locale.ROOT)
            );
        };
    }
}
~~~

Không cần một annotation bật callback riêng. Điều kiện là callback phải được đăng ký thành bean trong Spring context mà SDN sử dụng.

Generic type giúp callback gắn với domain type tương ứng. Một callback `BeforeBindCallback<Product>` được dùng cho Product; không nên khai báo callback quá rộng nếu logic chỉ dành cho một entity cụ thể.

## 5. Nhiều callback và thứ tự thực thi

Một domain type có thể có nhiều callback. Ví dụ:

1. Chuẩn hóa tên.
2. Tạo search key từ tên đã chuẩn hóa.
3. Kiểm tra dữ liệu trước khi mapping.

Hãy khai báo thứ tự bằng `@Order` hoặc triển khai `Ordered`:

~~~java
@Component
@Order(100)
public class NormalizeProductCallback
        implements BeforeBindCallback<Product> {

    @Override
    public Product onBeforeBind(Product product) {
        String name = product.name().trim();

        return new Product(
            product.id(),
            name,
            name.toLowerCase(Locale.ROOT)
        );
    }
}
~~~

~~~java
@Component
@Order(200)
public class ValidateProductCallback
        implements BeforeBindCallback<Product> {

    @Override
    public Product onBeforeBind(Product product) {
        if (product.normalizedName() == null
                || product.normalizedName().isBlank()) {
            throw new IllegalArgumentException(
                "normalizedName is required"
            );
        }

        return product;
    }
}
~~~

Callback có order nhỏ hơn được thực thi trước callback có order lớn hơn. Hãy dùng thứ tự tường minh khi một callback phụ thuộc vào kết quả callback trước.

Không nên tạo nhiều callback cùng sửa một property mà không có quy tắc thứ tự. Khi đó kết quả cuối phụ thuộc vào thứ tự thực thi và khó kiểm thử.

## 6. BeforeBindCallback và auditing

SDN có hỗ trợ auditing thông qua các annotation Spring Data:

- `@CreatedBy`
- `@CreatedDate`
- `@LastModifiedBy`
- `@LastModifiedDate`

Có thể bật auditing bằng `@EnableNeo4jAuditing`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing
public class Neo4jAuditingConfiguration {
}
~~~

Ví dụ entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class ProductAudit {

    @Id
    private String id;

    private String name;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant modifiedAt;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Nếu dùng `@CreatedBy` hoặc `@LastModifiedBy`, hãy cung cấp `AuditorAware<T>` để SDN biết người dùng hiện tại. Với ứng dụng reactive, sử dụng `ReactiveAuditorAware<T>` để lấy auditor trong reactive flow.

Auditing đã có callback chuyên dụng. Vì vậy, không cần tự viết `BeforeBindCallback` chỉ để gán created date hoặc modified date nếu chức năng auditing đáp ứng yêu cầu.

Hãy dùng callback tùy chỉnh cho quy tắc riêng của domain; dùng auditing cho metadata tạo và sửa được quản lý theo chuẩn Spring Data.

## 7. Phân biệt BeforeBindCallback với các extension point khác

| Extension point | Thời điểm | Mục đích |
|---|---|---|
| `BeforeBindCallback<T>` | Trước khi entity được chuyển thành `Map` để ghi | Sửa domain object trước mapping |
| `ReactiveBeforeBindCallback<T>` | Trước mapping trong luồng reactive | Sửa entity bằng reactive pipeline |
| `AfterConvertCallback<T>` | Sau khi SDN hydrate entity và các association từ record | Bổ sung hoặc điều chỉnh entity sau khi đọc |
| Auditing callback | Trong quá trình chuẩn bị entity để lưu | Gán created/modified metadata |
| Spring application event | Theo thời điểm event được phát trong lifecycle | Thông báo cho thành phần khác về sự kiện ứng dụng |

`BeforeBindCallback` tác động trực tiếp lên entity mà SDN sắp mapping. Nó không nhận bản ghi đã chuyển đổi và cũng không phải một listener chạy sau khi database commit.

`AfterConvertCallback` phù hợp khi cần xử lý entity sau khi đọc. Nó không thay thế `BeforeBindCallback` cho dữ liệu ghi.

Application event phù hợp để thông báo cho thành phần khác. Nếu mục tiêu là sửa entity theo thứ tự xác định trước khi persistence mapping diễn ra, entity callback là lựa chọn phù hợp hơn. Application event có thể được xử lý bất đồng bộ; không nên dựa vào một listener bất đồng bộ để sửa entity trước khi lưu.

## 8. Callback imperative và reactive

SDN có hai interface riêng:

- `BeforeBindCallback<T>` cho repository/template imperative.
- `ReactiveBeforeBindCallback<T>` cho repository/template reactive.

Callback reactive trả về `Publisher<T>`, thường được triển khai bằng `Mono<T>`:

~~~java
import java.util.Locale;

import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class ReactiveProductBeforeBindCallback
        implements ReactiveBeforeBindCallback<Product> {

    @Override
    public Mono<Product> onBeforeBind(Product product) {
        if (product.name() == null || product.name().isBlank()) {
            return Mono.error(
                new IllegalArgumentException("Product name must not be blank")
            );
        }

        String displayName = product.name().trim();

        Product updated = new Product(
            product.id(),
            displayName,
            displayName.toLowerCase(Locale.ROOT)
        );

        return Mono.just(updated);
    }
}
~~~

Các điểm cần nhớ:

- Reactive callback được thực thi trong reactive pipeline.
- Không gọi `block()` để chờ kết quả trong callback reactive.
- Không dùng callback imperative thay cho callback reactive.
- Nếu cần lấy thông tin từ reactive security context hoặc một nguồn reactive khác, hãy kết hợp publisher trong callback thay vì chặn luồng.
- Logic chuẩn hóa thuần có thể dùng chung giữa hai implementation để tránh hai quy tắc khác nhau.

Một ứng dụng chỉ dùng repository imperative có thể chỉ cần `BeforeBindCallback`. Chỉ đăng ký reactive callback khi có luồng ghi reactive cần xử lý.

## 9. Giới hạn và những việc không nên làm trong callback

`BeforeBindCallback` nên tập trung vào việc chuẩn bị entity. Hãy giữ callback ngắn, có thể dự đoán và không phụ thuộc vào tác động bên ngoài.

| Việc cần làm | Có nên đặt trong callback? | Lý do |
|---|---|---|
| Chuẩn hóa chuỗi hoặc mã | Có | Quy tắc thuần, xác định |
| Tính search key từ field có sẵn | Có | Giá trị được chuẩn bị trước mapping |
| Kiểm tra invariant của entity | Có | Có thể từ chối dữ liệu trước khi ghi |
| Gán giá trị mặc định xác định | Có | Nếu quy tắc rõ và không ghi đè dữ liệu hợp lệ |
| Gửi email hoặc message broker | Không | Đây là tác động bên ngoài persistence |
| Gọi HTTP API | Không | Tăng độ trễ và tạo phụ thuộc mạng trong luồng ghi |
| Gọi lại `repository.save()` | Không | Có thể gây gọi callback lặp hoặc đệ quy |
| Chạy một truy vấn khác để cập nhật entity | Tránh | Làm callback có side effect và khó kiểm soát transaction |
| Chặn reactive pipeline bằng `block()` | Không | Làm mất lợi ích của reactive flow |

Một số lưu ý quan trọng:

**Callback chạy theo luồng ghi.** Nếu ứng dụng gọi một Cypher query trực tiếp qua `Neo4jClient`, không có domain entity được SDN chuyển thành record theo quy trình save; do đó không nên trông đợi `BeforeBindCallback` xử lý câu query thuần đó.

**Không tạo dữ liệu ngẫu nhiên hoặc thời gian mới mỗi lần mà không có chủ đích.** Nếu callback sinh UUID hoặc gọi đồng hồ hệ thống mỗi lần save, cùng một entity có thể có giá trị khác nhau giữa các lần lưu. Hãy xác định rõ giá trị đó là định danh mới, thời điểm cập nhật hay dữ liệu cần ổn định.

**Không thay đổi khóa định danh ngoài ý muốn.** Callback có thể trả về instance khác, nhưng không nên tự đổi ID của entity đã tồn tại vì SDN có thể coi đó là một thực thể khác hoặc tạo ra hành vi ghi không mong đợi.

**Đừng dùng callback thay cho validation ở biên API.** Kiểm tra request, quyền truy cập và thông báo lỗi đầu vào nên diễn ra ở tầng phù hợp. Callback có thể bảo vệ invariant domain ngay trước mapping, nhưng không nên trở thành nơi duy nhất xác thực toàn bộ request.

## 10. Kiểm thử callback độc lập

Unit test xác nhận quy tắc biến đổi mà không cần Spring context hoặc Neo4j server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class NormalizeProductBeforeBindTest {

    private final NormalizeProductBeforeBind callback =
        new NormalizeProductBeforeBind();

    @Test
    void returnsNormalizedProduct() {
        Product input = new Product(
            "product-101",
            "  Graph Database  ",
            null
        );

        Product output = callback.onBeforeBind(input);

        assertThat(output.id()).isEqualTo("product-101");
        assertThat(output.name()).isEqualTo("Graph Database");
        assertThat(output.normalizedName())
            .isEqualTo("graph database");
    }

    @Test
    void rejectsBlankName() {
        Product input = new Product("product-102", "   ", null);

        assertThatThrownBy(() -> callback.onBeforeBind(input))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void doesNotMutateImmutableInput() {
        Product input = new Product(
            "product-103",
            "  Neo4j  ",
            null
        );

        callback.onBeforeBind(input);

        assertThat(input.name()).isEqualTo("  Neo4j  ");
        assertThat(input.normalizedName()).isNull();
    }
}
~~~

Test cuối xác nhận callback trả về một record mới mà không thay đổi instance đầu vào. Điều này hữu ích với domain object bất biến.

Nếu dùng entity mutable, hãy kiểm tra rõ callback sửa instance tại chỗ hay trả instance mới; không để hành vi đó trở thành điều bất ngờ đối với code gọi.

## 11. Integration test qua repository

Unit test mới chứng minh logic callback. Integration test cần chứng minh SDN thực sự nhận callback bean và dùng kết quả của nó khi ghi vào Neo4j.

Repository dùng trong ví dụ:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository
        extends Neo4jRepository<Product, String> {
}
~~~

Ví dụ với repository và `Neo4jClient`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.neo4j.core.Neo4jClient;

@DataNeo4jTest
@Import(NormalizeProductBeforeBind.class)
class ProductBeforeBindIntegrationTest {

    @Autowired
    private ProductRepository products;

    @Autowired
    private Neo4jClient client;

    @Test
    void callbackValueIsTheValueStoredInNeo4j() {
        products.save(
            new Product(
                "product-201",
                "  Graph Database  ",
                null
            )
        );

        String storedName = client.query("""
                MATCH (p:Product {id: $id})
                RETURN p.name AS name
                """)
            .bind("product-201").to("id")
            .fetchAs(String.class)
            .one()
            .orElseThrow();

        String storedNormalizedName = client.query("""
                MATCH (p:Product {id: $id})
                RETURN p.normalizedName AS normalizedName
                """)
            .bind("product-201").to("id")
            .fetchAs(String.class)
            .one()
            .orElseThrow();

        assertThat(storedName).isEqualTo("Graph Database");
        assertThat(storedNormalizedName).isEqualTo("graph database");
    }
}
~~~

`@DataNeo4jTest` tạo test slice cho repository, template và client. Test cần có Neo4j server, Testcontainers hoặc Neo4j Test Harness được cấu hình cho môi trường test; annotation này không tự cung cấp một database nhúng.

Dùng `Neo4jClient` trong test để đọc property trực tiếp từ graph. Cách này xác nhận giá trị đã qua callback được ghi thật vào Neo4j, thay vì chỉ kiểm tra object ở phía Java.

Nếu cần xác nhận callback được gọi đúng một lần trong một lần save, có thể dùng spy hoặc một callback test ghi nhận số lần gọi. Tuy nhiên, không nên đưa bộ đếm mutable hoặc logging có side effect vào callback production chỉ để kiểm thử.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Callback không được gọi | Callback chưa là Spring bean hoặc không đúng domain type | Đăng ký bean trong ApplicationContext |
| Dữ liệu lưu không được chuẩn hóa | Callback trả về instance cũ hoặc không cập nhật field cần ghi | Trả về entity đã sửa đổi |
| Entity bất biến không đổi | Callback chỉ tính giá trị nhưng bỏ qua instance mới | Tạo và trả về record/entity mới |
| Callback imperative không chạy trong reactive flow | Đang dùng sai loại callback | Triển khai `ReactiveBeforeBindCallback` |
| Callback chạy theo thứ tự không mong muốn | Có nhiều callback nhưng không khai báo order | Dùng `@Order` hoặc `Ordered` |
| Property bị ghi đè nhiều lần | Nhiều callback cùng sửa một field | Phân công trách nhiệm và khai báo thứ tự |
| Lưu entity gây gọi callback lặp | Callback gọi lại repository save | Không gọi persistence operation từ callback |
| Dữ liệu raw Cypher không qua callback | Query chạy trực tiếp bằng Neo4jClient | Chuẩn hóa input trước query hoặc dùng đường lưu entity phù hợp |
| Callback làm luồng ghi chậm | Gọi mạng, file hoặc truy vấn không cần thiết | Giữ callback thuần và ngắn |

## 13. Bài tập thực hành

Xây dựng callback cho entity `Article` với các thuộc tính `id`, `title`, `normalizedTitle` và `slug`.

Thực hiện:

1. Tạo `Article` dưới dạng record hoặc class mutable.
2. Viết `BeforeBindCallback<Article>` để trim title và tạo normalizedTitle.
3. Tạo slug từ normalizedTitle theo một quy tắc đơn giản, có thể chỉ thay khoảng trắng bằng dấu gạch ngang.
4. Đăng ký callback bằng `@Component` hoặc `@Bean`.
5. Lưu Article qua `Neo4jRepository`.
6. Dùng Neo4jClient đọc trực tiếp các property đã lưu.
7. Viết unit test cho title null, chuỗi rỗng và title có nhiều khoảng trắng.
8. Tạo callback thứ hai và dùng `@Order` để bảo đảm slug được tính sau normalizedTitle.
9. Nếu ứng dụng có repository reactive, viết `ReactiveBeforeBindCallback<Article>` và kiểm tra kết quả trong reactive pipeline.
10. Bật auditing và so sánh metadata auditing với field dẫn xuất do callback tự chuẩn bị.

Câu hỏi tự kiểm tra:

- `BeforeBindCallback` chạy trước hay sau khi entity được chuyển thành `Map`?
- Callback nhận và trả về kiểu dữ liệu nào?
- Vì sao entity bất biến cần được tạo instance mới?
- Callback được đăng ký như thế nào trong Spring context?
- Khi có nhiều callback cùng domain type, làm thế nào để kiểm soát thứ tự?
- Vì sao `BeforeBindCallback` không thay thế auditing?
- Callback imperative có được dùng thay cho reactive callback không?
- Vì sao không nên gọi email hoặc HTTP API trong callback?
- Làm thế nào để chứng minh giá trị callback trả về thực sự đã được ghi vào Neo4j?

## Kết luận

`BeforeBindCallback<T>` là entity callback của Spring Data Neo4j được gọi trước khi domain object được chuyển thành `Map<String, Object>` để tạo dữ liệu ghi. Callback có thể trả về chính entity hoặc một instance đã được sửa đổi; SDN dùng instance đó để tiếp tục mapping và tạo tham số cho Cypher.

Đăng ký callback như Spring bean, dùng `@Order` hoặc `Ordered` khi cần thứ tự rõ ràng, và chọn `ReactiveBeforeBindCallback` cho luồng reactive. Hãy giữ callback ngắn, xác định và tập trung vào chuẩn hóa hoặc kiểm tra entity. Dùng auditing cho metadata tạo/sửa và dùng application event cho thông báo tới thành phần khác. Kết hợp unit test với integration test đọc property trực tiếp từ Neo4j để xác nhận callback thực sự tác động đến dữ liệu được lưu.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 API: BeforeBindCallback](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/BeforeBindCallback.html)
- [Spring Data Neo4j 8.1.2 API: ReactiveBeforeBindCallback](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/ReactiveBeforeBindCallback.html)
- [Spring Data Neo4j FAQ: Auditing và callbacks](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Commons: Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html)
