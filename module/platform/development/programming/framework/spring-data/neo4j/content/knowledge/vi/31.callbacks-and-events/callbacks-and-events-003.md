# ReactiveBeforeBindCallback và xử lý bất đồng bộ

Trong Spring Data Neo4j (SDN), callback cho phép can thiệp vào entity tại một thời điểm xác định trong quá trình mapping và lưu dữ liệu. Với ứng dụng dùng reactive repository hoặc reactive template, `ReactiveBeforeBindCallback<T>` cho phép chuẩn bị entity bằng một `Publisher<T>`. Callback có thể gọi dịch vụ bất đồng bộ, bổ sung metadata hoặc kiểm tra thông tin trước khi SDN chuyển entity thành record để ghi vào Neo4j.

Khác với callback đồng bộ trả về entity ngay lập tức, reactive callback trả về một publisher mô tả công việc cần hoàn tất. SDN đợi publisher đó phát ra entity đã chuẩn bị rồi mới tiếp tục bind dữ liệu. Nhờ vậy, callback có thể tham gia cùng reactive pipeline mà không cần chặn thread bằng `block()` hoặc tự gọi `subscribe()`.

## 1. Callback diễn ra ở bước nào?

`ReactiveBeforeBindCallback` được gọi trước khi một domain object được lưu và trước khi entity được chuyển thành map record. Callback có thể trả về chính entity đầu vào hoặc một instance đã được chỉnh sửa; giá trị trả về sẽ được dùng để tạo record ghi xuống Neo4j.

~~~mermaid
flowchart TD
    A[Reactive repository save] --> B[ReactiveBeforeBindCallback]
    B --> C[Thực hiện xử lý bất đồng bộ]
    C --> D[Trả entity đã chuẩn bị]
    D --> E[SDN mapping entity thành record]
    E --> F[Thực thi Cypher qua reactive driver]
    F --> G[Phát entity đã lưu]
~~~

Ví dụ, trước khi lưu một node `Person`, ứng dụng cần tra cứu thông tin phân loại từ dịch vụ profile. Callback gọi dịch vụ đó, đưa kết quả vào entity rồi trả entity về cho SDN.

Callback này chạy trong luồng ghi entity. Nó không phải callback sau khi commit và cũng không phải nơi phù hợp để gửi email hoặc phát thông báo ra hệ thống ngoài. Nếu cần phản ứng sau khi lưu, hãy chọn application event hoặc cơ chế domain event phù hợp với yêu cầu transaction.

## 2. Phân biệt callback đồng bộ và reactive

SDN có hai loại callback trước khi bind:

| Callback | Kiểu trả về | Ngữ cảnh phù hợp |
|---|---|---|
| `BeforeBindCallback<T>` | `T` | Thao tác imperative, xử lý đồng bộ |
| `ReactiveBeforeBindCallback<T>` | `Publisher<T>` | Thao tác reactive, có thể hoàn tất bất đồng bộ |

Reactive callback thuộc package:

~~~java
import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;
~~~

API này có từ Spring Data Neo4j 6.0.2. Khi dùng reactive repository, hãy triển khai reactive callback để SDN có thể ghép công việc callback vào publisher lưu entity. Không đặt một lời gọi blocking bên trong reactive callback chỉ để tái sử dụng một callback đồng bộ.

Một callback đồng bộ có thể thực hiện phép biến đổi rất nhanh trên entity, nhưng nếu phải gọi HTTP, đọc cache bất đồng bộ hoặc truy vấn một reactive service khác thì callback reactive biểu đạt đúng vòng đời xử lý hơn.

## 3. Hợp đồng của ReactiveBeforeBindCallback

Interface có một phương thức chính:

~~~java
public interface ReactiveBeforeBindCallback<T> extends EntityCallback<T> {

    Publisher<T> onBeforeBind(T entity);
}
~~~

Ý nghĩa các thành phần:

- `T` là kiểu entity mà callback xử lý.
- Tham số `entity` là domain object sắp được lưu.
- Kết quả `Publisher<T>` phát ra entity sẽ được dùng để bind thành record.
- Callback có thể phát lại entity ban đầu hoặc một instance khác đã được chuẩn bị.
- Nếu publisher kết thúc bằng lỗi, thao tác lưu không thể tiếp tục như thể callback đã thành công.

Trong ứng dụng dùng Project Reactor, thường trả về `Mono<T>` vì mỗi lần callback xử lý một entity và cần phát ra đúng một entity:

~~~java
@Override
public Publisher<Person> onBeforeBind(Person entity) {
    return Mono.just(entity);
}
~~~

Không trả về `Mono.empty()` nếu mục tiêu là bỏ qua bước xử lý nhưng vẫn lưu entity. Một publisher rỗng không phát ra entity để SDN tiếp tục bind. Nếu không cần thay đổi entity, hãy trả về `Mono.just(entity)`.

## 4. Đăng ký callback như một Spring bean

SDN phát hiện các bean triển khai `ReactiveBeforeBindCallback` trong application context. Bạn có thể đăng ký bằng `@Component` hoặc khai báo bean trong lớp cấu hình. Không cần tự gọi callback từ repository method.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;
import org.reactivestreams.Publisher;
import reactor.core.publisher.Mono;

@Component
@Order(100)
public class PersonBeforeBindCallback
        implements ReactiveBeforeBindCallback<Person> {

    @Override
    public Publisher<Person> onBeforeBind(Person entity) {
        entity.setNormalizedName(entity.getName().trim().toLowerCase());
        return Mono.just(entity);
    }
}
~~~

Ví dụ trên chỉ chuẩn hóa dữ liệu ngay trong bộ nhớ, không thực hiện I/O. `@Order(100)` giúp xác định thứ tự tương đối khi có nhiều callback được áp dụng. SDN gọi các callback theo thứ tự; có thể dùng `Ordered` hoặc `@Order` để kiểm soát thứ tự đó.

Nếu nhiều callback cùng thay đổi một property, thứ tự thực thi ảnh hưởng đến giá trị cuối cùng. Hãy phân chia trách nhiệm hoặc đặt thứ tự rõ ràng để tránh callback sau ghi đè kết quả callback trước ngoài ý muốn.

## 5. Thực hiện lời gọi bất đồng bộ trước khi lưu

Giả sử một dịch vụ profile cung cấp thông tin khu vực và cấp độ thành viên. API client đã được viết theo reactive style:

~~~java
import reactor.core.publisher.Mono;

public interface ProfileMetadataClient {

    Mono<ProfileMetadata> findByExternalKey(String externalKey);
}
~~~

DTO metadata:

~~~java
public record ProfileMetadata(String region, String membershipLevel) {
}
~~~

Entity `Person` có hai property sẽ được bổ sung trước khi lưu. Callback gọi dịch vụ profile rồi trả entity đã được cập nhật:

~~~java
import java.time.Duration;

import org.reactivestreams.Publisher;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;
import reactor.core.publisher.Mono;

@Component
@Order(200)
public class EnrichPersonBeforeBindCallback
        implements ReactiveBeforeBindCallback<Person> {

    private final ProfileMetadataClient metadataClient;

    public EnrichPersonBeforeBindCallback(
            ProfileMetadataClient metadataClient) {
        this.metadataClient = metadataClient;
    }

    @Override
    public Publisher<Person> onBeforeBind(Person person) {
        if (person.getExternalKey() == null
                || person.getExternalKey().isBlank()) {
            return Mono.just(person);
        }

        return Mono.defer(() ->
                metadataClient.findByExternalKey(person.getExternalKey()))
            .map(metadata -> {
                person.setRegion(metadata.region());
                person.setMembershipLevel(metadata.membershipLevel());
                return person;
            })
            .defaultIfEmpty(person)
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

Luồng xử lý:

1. Nếu entity không có external key, callback trả ngay entity ban đầu.
2. `Mono.defer` trì hoãn việc gọi client cho đến khi publisher được subscribe.
3. Khi dịch vụ trả metadata, `map` bổ sung property vào entity.
4. `defaultIfEmpty` giữ entity ban đầu nếu dịch vụ không có metadata.
5. `timeout` giới hạn thời gian chờ kết quả.
6. Publisher phát entity đã chuẩn bị để SDN tiếp tục mapping và ghi.

Ví dụ dùng entity mutable để minh họa. Nếu domain model bất biến, hãy tạo và trả về một instance mới chứa các property đã cập nhật thay vì sửa object đầu vào.

## 6. Không chặn reactive pipeline

Một reactive callback phải trả về publisher mô tả công việc. Không chờ kết quả bằng `block()`:

~~~java
// Không nên: chặn thread trong callback
ProfileMetadata metadata =
    metadataClient.findByExternalKey(person.getExternalKey()).block();
person.setRegion(metadata.region());
return Mono.just(person);
~~~

Cách làm này biến một lời gọi bất đồng bộ thành lời gọi đồng bộ, có thể chiếm thread trong thời gian chờ mạng và làm giảm khả năng mở rộng của ứng dụng.

Không tự gọi `subscribe()` bên trong callback:

~~~java
// Không nên: callback không chờ công việc này hoàn tất
metadataClient.findByExternalKey(person.getExternalKey())
    .subscribe(metadata -> person.setRegion(metadata.region()));

return Mono.just(person);
~~~

Trong ví dụ không đúng này, `Mono.just(person)` có thể phát entity trước khi metadata được tải về. SDN có thể bind và lưu entity khi property vẫn chưa được cập nhật. Lỗi từ publisher được subscribe độc lập cũng không được truyền ngược vào thao tác save.

Hãy nối công việc bằng `map`, `flatMap`, `switchIfEmpty` hoặc toán tử Reactor phù hợp rồi trả publisher hoàn chỉnh về SDN.

## 7. Xử lý trường hợp không có dữ liệu và lỗi từ dịch vụ ngoài

Callback cần xác định rõ chính sách khi dịch vụ phụ trợ không tìm thấy dữ liệu hoặc gặp lỗi:

| Tình huống | Cách xử lý | Kết quả đối với thao tác save |
|---|---|---|
| Không có external key | Trả entity ban đầu | Tiếp tục lưu |
| Dịch vụ trả `Mono.empty()` | Dùng `defaultIfEmpty(entity)` nếu metadata là tùy chọn | Tiếp tục lưu entity chưa bổ sung |
| Dịch vụ trả metadata | Cập nhật entity rồi phát ra | Lưu entity đã bổ sung |
| Dịch vụ lỗi và metadata là bắt buộc | Để lỗi truyền ra hoặc chuyển thành lỗi nghiệp vụ | Save thất bại |
| Dịch vụ lỗi nhưng metadata là tùy chọn | Có thể `onErrorResume` và trả entity gốc theo chính sách | Tiếp tục lưu, cần ghi nhận fallback |
| Dịch vụ phản hồi quá chậm | Dùng `timeout` với giới hạn phù hợp | Thất bại hoặc fallback theo chính sách |

Ví dụ nếu metadata chỉ mang tính bổ sung, ứng dụng có thể cho phép lưu khi dịch vụ profile tạm thời lỗi:

~~~java
return Mono.defer(() ->
        metadataClient.findByExternalKey(person.getExternalKey()))
    .map(metadata -> {
        person.setRegion(metadata.region());
        person.setMembershipLevel(metadata.membershipLevel());
        return person;
    })
    .defaultIfEmpty(person)
    .onErrorResume(error -> {
        // Ghi nhận lỗi bằng logging/metrics phù hợp.
        return Mono.just(person);
    });
~~~

Không nên dùng fallback im lặng nếu metadata là điều kiện bắt buộc để bảo đảm tính đúng đắn. Khi đó, để lỗi truyền ra giúp caller biết thao tác save chưa hoàn tất. Nếu dùng fallback, hãy ghi nhận lỗi qua logging hoặc metrics và tránh để callback tự phát sinh side effect không kiểm soát.

## 8. Callback và thứ tự nhiều bước bất đồng bộ

Nếu một entity cần nhiều bước chuẩn bị phụ thuộc nhau, hãy ghép chúng trong cùng publisher để SDN chỉ nhận entity khi toàn bộ chuỗi hoàn tất:

~~~java
@Override
public Publisher<Person> onBeforeBind(Person person) {
    return Mono.defer(() -> metadataClient.findByExternalKey(person.getExternalKey()))
        .flatMap(metadata ->
            permissionClient.checkCanPersist(person.getExternalKey())
                .filter(Boolean::booleanValue)
                .switchIfEmpty(Mono.error(
                    new IllegalStateException("Person cannot be persisted")
                ))
                .map(allowed -> {
                    person.setRegion(metadata.region());
                    person.setMembershipLevel(metadata.membershipLevel());
                    return person;
                })
        );
}
~~~

Ở đây bước lấy metadata hoàn tất trước, sau đó mới kiểm tra quyền lưu. Nếu kiểm tra quyền không thành công, publisher phát lỗi và entity không được chuyển sang bước bind.

Chỉ thêm các bước thực sự cần thiết cho mọi lần lưu entity thuộc loại này. Nếu một bước chỉ áp dụng cho một use case cụ thể, cân nhắc thực hiện trong service trước khi gọi repository thay vì đưa logic đó vào callback dùng chung.

## 9. Thứ tự callback và phối hợp với auditing

SDN có thể phát hiện nhiều bean triển khai `ReactiveBeforeBindCallback` và gọi chúng theo thứ tự. Dùng `@Order` hoặc triển khai `Ordered` khi thứ tự có ảnh hưởng đến kết quả.

Với dữ liệu kiểm toán như người tạo, thời điểm tạo, người sửa và thời điểm sửa, nên dùng cơ chế auditing của Spring Data Neo4j thay vì tự viết lại logic trong mọi callback. Ở ứng dụng reactive, nguồn cung cấp người thực hiện cần theo reactive style, ví dụ `ReactiveAuditorAware<T>`, để việc lấy auditor trở thành một phần của reactive flow.

Hãy cân nhắc thứ tự giữa callback bổ sung dữ liệu và callback auditing. Nếu một callback tạo ra property được callback khác dùng, hãy đặt thứ tự rõ ràng và kiểm thử kết quả cuối trước khi ghi.

## 10. Callback không phải application event

`ReactiveBeforeBindCallback` thích hợp cho logic cần thay đổi hoặc chuẩn bị entity trước khi lưu. Application event phục vụ việc thông báo một sự kiện để thành phần khác phản ứng, chẳng hạn gửi thông báo hoặc cập nhật một hệ thống phụ.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Chuẩn hóa hoặc bổ sung property trước khi bind | `ReactiveBeforeBindCallback` |
| Tra cứu metadata bất đồng bộ cần có trước khi lưu | `ReactiveBeforeBindCallback` |
| Điền thông tin auditor trong reactive flow | Reactive auditing |
| Thông báo cho thành phần khác sau một hành động | Application event hoặc domain event |
| Xử lý thay đổi cần gắn với vòng đời aggregate và transaction | Domain event/`@DomainEvents` theo mô hình aggregate |

Application event có thể được xử lý bất đồng bộ, nhưng khi chạy bất đồng bộ nó không còn phù hợp để bảo đảm thay đổi nằm trong transaction ghi entity. Nếu yêu cầu xử lý sau commit đáng tin cậy, hãy chọn cơ chế sự kiện/outbox phù hợp thay vì đặt side effect vào callback trước khi bind.

## 11. Tác động đến transaction và side effect

Reactive callback được ghép vào pipeline lưu entity. Nếu callback phát lỗi trước khi bind, thao tác save không thể hoàn tất. Nếu callback gọi dịch vụ bên ngoài, lời gọi đó không tự trở thành một phần của transaction Neo4j.

Ví dụ, Neo4j có thể rollback transaction sau khi một bước ghi thất bại, nhưng một HTTP request đã gửi sang dịch vụ profile không thể tự rollback cùng Neo4j. Vì vậy:

- Ưu tiên các bước đọc metadata hoặc kiểm tra có thể gọi lặp an toàn.
- Không gửi thanh toán, email hoặc lệnh không thể đảo ngược trong callback trước bind.
- Không giả định transaction Neo4j bao trùm HTTP client.
- Nếu callback có thể được gọi lại do retry, bảo đảm thao tác ngoài có tính idempotent.
- Giữ timeout hữu hạn để không giữ pipeline lưu entity quá lâu.

Nếu dữ liệu phụ trợ là bắt buộc và có thể thay đổi giữa lúc tra cứu với lúc lưu, hãy đánh giá lại ranh giới nhất quán. Callback chỉ đảm bảo dữ liệu được lấy trước bước bind; nó không tạo distributed transaction giữa Neo4j và dịch vụ ngoài.

## 12. Kiểm thử ReactiveBeforeBindCallback

Có thể kiểm thử callback riêng mà không cần khởi chạy Neo4j. Dùng Reactor Test để xác minh entity phát ra và lỗi được truyền đúng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class EnrichPersonBeforeBindCallbackTest {

    @Test
    void shouldEnrichPersonBeforeBinding() {
        ProfileMetadataClient client = key ->
            Mono.just(new ProfileMetadata("North", "GOLD"));

        EnrichPersonBeforeBindCallback callback =
            new EnrichPersonBeforeBindCallback(client);

        Person person = new Person();
        person.setExternalKey("person-42");

        StepVerifier.create(Mono.from(callback.onBeforeBind(person)))
            .assertNext(saved -> {
                assertThat(saved.getRegion()).isEqualTo("North");
                assertThat(saved.getMembershipLevel()).isEqualTo("GOLD");
            })
            .verifyComplete();
    }
}
~~~

Đây là ví dụ kiểm thử minh họa; lớp `Person` và client cần cung cấp constructor hoặc setter tương ứng trong dự án. Nên bổ sung kiểm thử cho các trường hợp:

- Không có external key thì entity được phát nguyên trạng.
- Client trả publisher rỗng thì fallback đúng chính sách.
- Client phát lỗi thì lỗi truyền ra hoặc được fallback có chủ đích.
- Client vượt timeout thì callback kết thúc theo chính sách.
- Nhiều callback có thứ tự xác định thì property cuối cùng đúng như mong đợi.
- Khi callback lỗi, repository không phát ra entity đã lưu thành công.

Trong kiểm thử tích hợp, dùng reactive repository và xác nhận property được callback bổ sung thực sự xuất hiện trong Neo4j sau khi save hoàn tất.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Triển khai callback đồng bộ cho reactive save | Công việc bất đồng bộ không được ghép vào reactive pipeline | Dùng `ReactiveBeforeBindCallback<T>` |
| Gọi `block()` trong callback | Chặn thread và làm mất lợi ích non-blocking | Trả publisher và nối bằng toán tử Reactor |
| Gọi `subscribe()` bên trong callback | SDN có thể bind entity trước khi bước phụ hoàn tất | Trả toàn bộ publisher từ `onBeforeBind` |
| Trả `Mono.empty()` khi chỉ muốn bỏ qua enrichment | Không phát entity để SDN bind | Trả `Mono.just(entity)` |
| Không xử lý lỗi từ dịch vụ phụ trợ | Save thất bại khi callback lỗi | Chọn rõ fail-fast hoặc fallback |
| Fallback mọi lỗi một cách im lặng | Mất dữ liệu quan trọng hoặc che giấu sự cố | Chỉ fallback khi metadata là tùy chọn và có logging/metrics |
| Nhiều callback cùng sửa một property nhưng không có thứ tự | Giá trị cuối khó dự đoán | Dùng `@Order` hoặc hợp nhất logic |
| Gửi side effect không idempotent trước bind | Retry có thể gửi trùng email hoặc lệnh thanh toán | Tách side effect khỏi callback |
| Giả định HTTP client nằm trong transaction Neo4j | Không thể rollback tác động ngoài database | Thiết kế idempotency/outbox hoặc xử lý bù |

## 14. Quy trình triển khai đề xuất

1. Xác định property nào cần được chuẩn bị trước khi entity bind thành record.
2. Chỉ dùng `ReactiveBeforeBindCallback<T>` cho reactive persistence path.
3. Đăng ký callback như một Spring bean để SDN tự phát hiện.
4. Trả về `Publisher<T>`; dùng `Mono<T>` cho một entity.
5. Dùng reactive client và toán tử Reactor để nối các bước bất đồng bộ.
6. Quy định rõ hành vi khi dữ liệu không có, dịch vụ lỗi hoặc timeout.
7. Dùng `@Order` khi nhiều callback có phụ thuộc thứ tự.
8. Giữ callback tập trung vào việc chuẩn bị entity; chuyển side effect sau lưu sang event/outbox phù hợp.
9. Kiểm thử kết quả, lỗi, timeout và việc callback thực sự hoàn tất trước khi entity được bind.

## 15. Tự kiểm tra

1. `ReactiveBeforeBindCallback<T>` được gọi ở thời điểm nào trong quá trình lưu entity?
2. Vì sao phương thức `onBeforeBind` trả về `Publisher<T>`?
3. Khác biệt giữa `BeforeBindCallback<T>` và `ReactiveBeforeBindCallback<T>` là gì?
4. Vì sao không nên gọi `block()` hoặc `subscribe()` bên trong callback?
5. `Mono.empty()` khác `Mono.just(entity)` như thế nào đối với bước bind?
6. Làm thế nào để xử lý lỗi từ dịch vụ ngoài khi metadata là tùy chọn?
7. Vì sao cần dùng `@Order` khi nhiều callback cùng sửa entity?
8. Vì sao callback trước bind không phù hợp để gửi email hoặc thực hiện thanh toán?

`ReactiveBeforeBindCallback` cho phép hoàn tất công việc chuẩn bị entity bất đồng bộ trước khi SDN tạo record để lưu. Hãy trả publisher hoàn chỉnh, không chặn thread và không tự subscribe; chọn chính sách lỗi rõ ràng, kiểm soát thứ tự callback và giữ side effect ngoài transaction ở cơ chế phù hợp.

Tài liệu tham khảo:

- [Spring Data Neo4j API – ReactiveBeforeBindCallback](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/ReactiveBeforeBindCallback.html)
- [Spring Data Neo4j FAQ – Auditing and callbacks](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
