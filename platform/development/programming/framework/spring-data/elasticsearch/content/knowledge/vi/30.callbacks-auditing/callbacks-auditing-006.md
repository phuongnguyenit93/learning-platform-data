# Phân biệt callback đồng bộ và callback reactive

Spring Data Elasticsearch cung cấp callback để can thiệp vào vòng đời entity khi ứng dụng đọc, ghi và chuyển đổi dữ liệu. Callback có thể chuẩn hóa entity trước khi lưu, bổ sung metadata, thay đổi Document sau khi mapping hoặc xử lý entity sau khi đọc.

Khi dùng stack imperative, callback trả về trực tiếp giá trị đã xử lý. Khi dùng stack reactive, callback trả về một Publisher để công việc được ghép vào pipeline Reactor. Hai loại callback có mục đích tương tự nhưng khác nhau về hợp đồng trả về, thời điểm thực thi, cách xử lý lỗi và cách truy cập context của request.

Hiểu đúng khác biệt này giúp tránh các lỗi như chặn event-loop bằng thao tác blocking, gọi subscribe bên trong callback, mất thông tin người dùng khi chuyển thread hoặc vô tình thực hiện side effect nhiều lần khi reactive sequence được retry hay subscribe lại.

## 1. Callback trong Spring Data Elasticsearch là gì?

### 1.1. Callback can thiệp vào lifecycle của entity

Spring Data Elasticsearch ánh xạ entity Java thành Document để gửi tới Elasticsearch và chuyển Document trở lại entity khi đọc. Callback cho phép ứng dụng chạy logic tại những điểm xác định trong quy trình đó.

Các use case thường gặp:

- Chuẩn hóa dữ liệu trước khi convert.
- Tạo slug, mã chuẩn hóa hoặc giá trị tìm kiếm.
- Bổ sung thông tin audit như created date, modified date và auditor.
- Điều chỉnh Document sau khi mapping.
- Bổ sung giá trị mặc định khi đọc.
- Ghi nhận metric hoặc trace cho thao tác lifecycle.

Callback là một phần của Spring Data mapping/operations lifecycle. Chúng không phải một cơ chế tổng quát để theo dõi mọi request Elasticsearch.

Nếu ứng dụng gọi Elasticsearch Java API Client trực tiếp, bỏ qua Spring Data ElasticsearchOperations/repository, các entity lifecycle callback của Spring Data không tự động được gọi.

### 1.2. Hai nhóm execution model

Spring Data có các API imperative và reactive:

| Stack | API thao tác thường dùng | Callback model | Kết quả callback |
|---|---|---|---|
| Imperative | ElasticsearchOperations, ElasticsearchTemplate, ElasticsearchRepository | EntityCallbacks và callback đồng bộ | Trả entity/Document trực tiếp |
| Reactive | ReactiveElasticsearchOperations, ReactiveElasticsearchTemplate, ReactiveElasticsearchRepository | ReactiveEntityCallbacks và callback reactive | Trả Publisher |

Với imperative stack, method thường hoàn tất công việc trước khi trả kết quả. Callback chạy trong luồng thực thi đồng bộ của thao tác đó.

Với reactive stack, method thường trả Mono hoặc Flux. Pipeline được thực thi khi có subscription. Reactive callback trả Publisher, cho phép Spring Data nối logic callback vào cùng pipeline.

### 1.3. Không nhầm entity callback với callback của HTTP client

Một ứng dụng có thể có nhiều loại callback:

- Entity lifecycle callback của Spring Data.
- Listener nhận bulk response.
- Callback của Elasticsearch Java API Client.
- Reactor operator như doOnNext, doOnError.
- Event listener của Spring Application Events.

Chúng có vị trí và semantics khác nhau. Bài này tập trung vào callback gắn với lifecycle entity trong Spring Data Elasticsearch. Listener của Bulk API hoặc Reactor operator không tự thay thế các callback đó.

## 2. Các điểm callback trong lifecycle

### 2.1. Quy trình ghi entity

Một luồng ghi điển hình có các điểm sau:

~~~mermaid
flowchart TD
    A[Application submits entity] --> B[BeforeConvert callback]
    B --> C[Convert entity to Document]
    C --> D[BeforeSave callback]
    D --> E[Send write request to Elasticsearch]
    E --> F[AfterSave callback]
    F --> G[Return result]
~~~

Các callback cụ thể có thể được cung cấp theo stack imperative hoặc reactive. Ý nghĩa lifecycle vẫn tương ứng:

| Callback | Thời điểm | Mục đích |
|---|---|---|
| BeforeConvertCallback | Trước khi entity được convert thành Document | Chuẩn hóa entity, bổ sung giá trị trước mapping |
| BeforeSaveCallback | Sau mapping, trước khi gửi write request | Điều chỉnh entity hoặc Document đã tạo |
| AfterSaveCallback | Sau thao tác save | Xử lý kết quả sau ghi, ghi metric hoặc chuẩn bị kết quả trả về |

BeforeConvert phù hợp với thay đổi thuộc mô hình entity. BeforeSave phù hợp khi cần xem hoặc thay đổi cả Document đã được tạo. AfterSave chạy sau write operation, nên side effect ở đây cần được thiết kế cẩn thận.

### 2.2. Quy trình đọc entity

Luồng đọc có thể có các điểm:

~~~mermaid
flowchart TD
    A[Search/get request] --> B[Elasticsearch returns Document]
    B --> C[AfterLoad callback]
    C --> D[Convert Document to entity]
    D --> E[AfterConvert callback]
    E --> F[Return entity]
~~~

| Callback | Thời điểm | Mục đích |
|---|---|---|
| AfterLoadCallback | Sau khi Document được tải, trước khi convert | Điều chỉnh dữ liệu Document trước mapping |
| AfterConvertCallback | Sau khi Document được convert thành entity | Hoàn thiện entity hoặc áp dụng logic sau mapping |

Callback đọc không phải nơi phù hợp để thực hiện write ngược vào Elasticsearch cho mọi entity. Việc đó dễ tạo vòng lặp hoặc làm tăng số request ngoài dự kiến.

### 2.3. Thứ tự callback và thứ tự thực tế

Callback được gọi tại điểm lifecycle tương ứng. Nếu có nhiều callback cùng loại, thứ tự có thể được điều khiển bằng cơ chế ordering mà phiên bản Spring Data hỗ trợ, chẳng hạn Ordered hoặc @Order.

Không nên dựa vào thứ tự quét bean ngẫu nhiên. Nếu callback B cần dữ liệu do callback A tạo ra, hãy khai báo order rõ ràng và kiểm thử thứ tự đó.

Một callback cũng có thể trả về entity mới thay vì sửa object hiện tại. Trong trường hợp dùng immutable object, phải trả đúng instance đã được thay đổi để pipeline tiếp tục với dữ liệu đó.

## 3. Callback đồng bộ

### 3.1. Hợp đồng trả về trực tiếp

Callback imperative xử lý entity và trả kết quả ngay trong method. Ví dụ BeforeConvertCallback:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeConvert
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        if (entity.getName() != null) {
            entity.setNormalizedName(
                entity.getName().trim().toLowerCase()
            );
        }

        return entity;
    }
}
~~~

Đây là callback đồng bộ: method nhận entity, xử lý và trả về entity. Không có Mono, Flux hoặc Publisher trong hợp đồng.

Tên package và chữ ký interface cần được đối chiếu với phiên bản Spring Data Elasticsearch đang dùng. Ví dụ trên minh họa API lifecycle callback imperative phổ biến.

### 3.2. Callback đồng bộ chạy trên đường gọi hiện tại

Khi ứng dụng gọi một thao tác imperative, callback được thực thi như một phần của thao tác đó. Một callback chậm sẽ làm chậm chính thao tác save/read đang gọi.

~~~java
Product saved = operations.save(product);
~~~

Trước khi save trả về, các callback imperative tương ứng được thực hiện theo lifecycle. Nếu callback gọi một dịch vụ HTTP blocking mất 2 giây, thao tác save của ứng dụng cũng phải chờ.

Không nên đưa công việc mạng hoặc I/O chậm vào callback đồng bộ nếu có thể thực hiện ở tầng service phù hợp hơn.

### 3.3. Phù hợp với logic nhanh và xác định

Callback đồng bộ phù hợp cho:

- Chuẩn hóa chuỗi.
- Tính giá trị dẫn xuất nhẹ.
- Kiểm tra invariant đơn giản.
- Bổ sung metadata từ dữ liệu đã có trong entity.
- Ánh xạ hoặc điều chỉnh Document.
- Ghi metric nhẹ.

Nếu callback cần gọi database khác, gọi dịch vụ từ xa hoặc chờ một tài nguyên bất đồng bộ, hãy đánh giá lại vị trí của logic. Callback đồng bộ không tự trở thành non-blocking chỉ vì nó được khai báo trong Spring bean.

### 3.4. Lỗi trong callback đồng bộ

Nếu callback ném exception, thao tác Spring Data có thể thất bại và exception truyền về caller. Với callback trước save, write request có thể chưa được gửi. Với callback sau save, dữ liệu có thể đã được ghi thành công trước khi callback ném lỗi.

Điều này tạo khác biệt quan trọng:

- Lỗi BeforeConvert/BeforeSave: thường xảy ra trước write.
- Lỗi AfterSave: write có thể đã hoàn tất, nhưng caller vẫn nhận exception.

Không được giả định mọi exception từ save() có nghĩa Elasticsearch chắc chắn chưa lưu document. Với lỗi sau write, cần thiết kế retry dựa trên idempotency và kiểm tra trạng thái thực tế nếu nghiệp vụ yêu cầu.

## 4. Callback reactive

### 4.1. Hợp đồng trả về Publisher

Callback reactive không trả entity trực tiếp. Nó trả một Publisher để Spring Data ghép vào pipeline reactive.

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveProductBeforeConvert
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        return Mono.fromSupplier(() -> {
            if (entity.getName() != null) {
                entity.setNormalizedName(
                    entity.getName().trim().toLowerCase()
                );
            }

            return entity;
        });
    }
}
~~~

Callback trả Publisher<Product>. Có thể trả Mono<Product> vì Mono triển khai Reactive Streams Publisher.

Tên interface, package và chữ ký cụ thể có thể thay đổi theo release train. Hãy xác nhận dependency version trước khi sao chép code vào dự án.

### 4.2. Callback reactive được thực thi khi subscribe

Reactive sequence thường lazy. Việc gọi method tạo Mono không đồng nghĩa callback đã chạy.

~~~java
Mono<Product> result = reactiveOperations.save(product);
~~~

Tại thời điểm này, ứng dụng có pipeline mô tả công việc. Công việc được kích hoạt khi có subscription. Trong ứng dụng web reactive, framework thường quản lý subscription. Service/controller nên trả Mono hoặc Flux về tầng gọi thay vì tự subscribe bên trong.

Nếu callback tạo side effect ngay khi method được gọi thay vì bên trong Publisher, side effect có thể xảy ra trước subscription và không còn tuân theo lifecycle reactive mong đợi.

### 4.3. Dùng Mono.defer khi cần trì hoãn việc tạo Publisher hoặc đọc context

Mono.defer tạo Publisher mới khi có subscription:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    return Mono.defer(() -> {
        normalize(entity);
        return Mono.just(entity);
    });
}
~~~

Cách này hữu ích khi logic cần chạy tại thời điểm subscription. Nếu chỉ tính một giá trị đồng bộ, Mono.fromSupplier cũng có thể phù hợp.

Không cần bọc mọi phép tính đơn giản trong scheduler riêng. Hãy giữ pipeline đơn giản và chỉ chuyển scheduler khi có lý do rõ ràng.

### 4.4. Không gọi block hoặc subscribe bên trong callback reactive

Các anti-pattern:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    // Không nên: chặn reactive pipeline.
    Product normalized = remoteService.normalize(entity).block();

    return Mono.just(normalized);
}
~~~

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    // Không nên: tạo subscription tách rời khỏi lifecycle.
    remoteService.audit(entity).subscribe();

    return Mono.just(entity);
}
~~~

block() có thể chặn thread đang chạy pipeline và gây lỗi khi chạy trên Reactor non-blocking thread. subscribe() bên trong callback tạo một luồng thực thi tách rời: lỗi, cancellation và thời điểm hoàn tất của side effect không còn được kết nối với thao tác save.

Hãy compose Publisher:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    return remoteService.normalize(entity)
        .map(normalized -> {
            entity.setNormalizedName(normalized);
            return entity;
        });
}
~~~

Khi Publisher được compose, lỗi và cancellation có thể truyền qua cùng pipeline.

### 4.5. Reactive không có nghĩa tự động chạy trên background thread

Một callback reactive có thể chạy trên thread đang subscribe hoặc thread do upstream/downstream scheduler quyết định. Reactor không tự tạo một thread mới cho mỗi callback.

- subscribeOn ảnh hưởng scheduler nơi subscription/upstream được thực thi.
- publishOn chuyển việc xử lý các operator phía sau sang scheduler được chọn.
- Nếu không có scheduler switch, pipeline có thể tiếp tục trên thread hiện tại.

Đừng giả định callback reactive luôn chạy trên một thread chuyên dụng. Cũng không dùng publishOn(boundedElastic()) như cách che giấu mọi thao tác blocking; hãy chọn scheduler theo bản chất công việc và ưu tiên API non-blocking.

## 5. So sánh đồng bộ và reactive

### 5.1. Bảng khác biệt

| Tiêu chí | Callback đồng bộ | Callback reactive |
|---|---|---|
| Interface | BeforeConvertCallback<T> và callback imperative tương ứng | ReactiveBeforeConvertCallback<T> và callback reactive tương ứng |
| Giá trị trả về | Entity hoặc Document trực tiếp | Publisher<T>/Publisher<Document> |
| Thời điểm chạy | Trong lời gọi operations imperative | Khi reactive pipeline được subscribe và đi qua callback |
| Thread | Luồng thực thi của thao tác imperative | Thread do subscription và scheduler của pipeline quyết định |
| I/O bất đồng bộ | Không có composition bất đồng bộ trong hợp đồng | Có thể compose Mono/Flux |
| Blocking | Có thể block nhưng làm chậm thao tác | Không nên block event-loop hoặc pipeline |
| Error | Exception truyền qua lời gọi imperative | Error signal truyền qua Publisher |
| Cancellation | Thường không có cancellation signal theo Reactive Streams | Có thể truyền cancellation qua pipeline |
| Context | Thường dựa vào call context/ThreadLocal | Có thể dùng Reactor Context; ThreadLocal không tự an toàn qua thread switch |
| Kiểm thử | Gọi callback và assert kết quả/exception | Dùng StepVerifier và kiểm tra subscription/context |

### 5.2. Chọn callback theo stack của ứng dụng

Nếu ứng dụng dùng ElasticsearchOperations và repository imperative, dùng callback imperative. Nếu ứng dụng dùng ReactiveElasticsearchOperations hoặc reactive repository, dùng reactive callback tương ứng.

Không nên dùng callback đồng bộ trong reactive pipeline chỉ vì code dễ viết hơn, đặc biệt khi callback thực hiện I/O. Cũng không cần biến toàn bộ ứng dụng thành reactive chỉ để dùng một callback; chọn stack theo kiến trúc tổng thể.

### 5.3. Không trộn hai model một cách vô tình

Một class không nên cố triển khai cả callback imperative và reactive cùng tên logic nếu điều đó khiến cùng một thao tác bị chạy hai lần hoặc khó xác định thứ tự.

Nếu ứng dụng thật sự có cả hai stack, có thể tách adapter hoặc implementation theo từng model. Phần logic nghiệp vụ thuần nên được tái sử dụng ở service nhỏ, còn adapter chịu trách nhiệm chuyển sang kiểu trả về phù hợp.

## 6. Những callback lifecycle thường gặp

### 6.1. Callback trước khi convert

BeforeConvertCallback và reactive counterpart phù hợp để thay đổi entity trước khi Spring Data tạo Document.

Ví dụ:

- Trim và chuẩn hóa tên.
- Tạo slug.
- Điền giá trị mặc định.
- Gắn metadata nguồn dữ liệu.
- Chuẩn bị field dùng cho tìm kiếm.

Không nên dùng callback này để gọi save lại chính entity qua cùng repository. Điều đó có thể tạo vòng lặp callback.

### 6.2. Callback trước khi save

BeforeSaveCallback chạy sau khi entity đã được chuyển thành Document và trước khi dữ liệu được ghi. Callback này phù hợp khi logic cần cả entity lẫn representation đã mapping.

Ví dụ, thêm field kỹ thuật vào Document hoặc kiểm tra mapping đầu ra. Nếu chỉnh sửa Document, cần bảo đảm thay đổi tương thích với mapping và không vô tình ghi đè field do converter tạo.

### 6.3. Callback sau khi save

AfterSaveCallback chạy sau khi thao tác save hoàn tất. Có thể dùng để ghi metric hoặc chuẩn bị dữ liệu trả về.

Nếu callback gọi một hệ thống bên ngoài, cần lưu ý write Elasticsearch có thể đã thành công dù callback thất bại. Với side effect quan trọng như gửi message hoặc ghi audit bắt buộc, cân nhắc outbox hoặc quy trình bền vững thay vì phụ thuộc vào một callback sau save đơn lẻ.

### 6.4. Callback sau khi load và sau khi convert

AfterLoadCallback nhận Document sau khi tải. AfterConvertCallback nhận entity sau khi convert.

Dùng chúng cho logic đọc cần thiết và xác định. Không thực hiện network call cho từng entity trong một Flux lớn nếu có thể batch hoặc tải dữ liệu ở service layer; điều đó có thể tạo N+1 request và làm chậm luồng đọc.

### 6.5. Callback reactive tương ứng

Reactive stack có các callback tương ứng theo lifecycle, thường được đặt tên với tiền tố Reactive, ví dụ:

- ReactiveBeforeConvertCallback<T>.
- ReactiveBeforeSaveCallback<T>.
- ReactiveAfterSaveCallback<T>.
- ReactiveAfterLoadCallback<T>.
- ReactiveAfterConvertCallback<T>.

Hãy xác nhận danh sách interface và chữ ký của release train đang dùng. Các callback nhận entity thường trả Publisher của entity; callback thao tác trên Document trả Publisher của Document.

## 7. Auditing và callback

### 7.1. Auditing là một use case của lifecycle callback

Auditing tự động điền thông tin về thời điểm và người tạo/cập nhật entity. Các annotation thường dùng:

~~~java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

Auditing được thực hiện tại lifecycle thích hợp trước khi entity được convert/lưu. Vì vậy, ứng dụng không cần lặp logic gán timestamp và user ở mọi service method.

### 7.2. AuditorAware cho imperative stack

Trong imperative application, AuditorAware<T> cung cấp người dùng hiện tại:

~~~java
@Component
public class SpringSecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(
            SecurityContextHolder.getContext()
                .getAuthentication()
        )
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
    }
}
~~~

Ví dụ dùng Spring Security imperative. Nếu ứng dụng không có authentication hoặc chạy job nền, cần định nghĩa rõ auditor hệ thống hoặc trả Optional.empty() theo quy tắc nghiệp vụ.

Cấu hình enable auditing và cách tham chiếu AuditorAware phụ thuộc phiên bản Spring Data Elasticsearch. Hãy dùng annotation/configuration được tài liệu của release train hỗ trợ.

### 7.3. ReactiveAuditorAware cho reactive stack

Reactive application nên lấy auditor từ reactive security context hoặc Reactor Context, không dựa vào SecurityContextHolder kiểu ThreadLocal.

Ví dụ khái niệm với Spring Security reactive:

~~~java
@Component
public class ReactiveSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
~~~

ReactiveAuditorAware<T> trả Mono<T>. Khi không có auditor, Publisher có thể hoàn tất rỗng theo contract. Không gọi block() để biến nó thành Optional trong reactive path.

Cấu hình bật auditing reactive cần khớp phiên bản Spring Data Elasticsearch đang sử dụng. Một số release dùng cấu hình enable auditing chung và tự nhận diện ReactiveAuditorAware; hãy kiểm tra tài liệu thay vì giả định annotation giữa các release luôn giống nhau.

### 7.4. Vì sao ThreadLocal có thể làm mất auditor trong reactive?

Reactive pipeline có thể chuyển thread khi dùng scheduler. ThreadLocal gắn dữ liệu với thread hiện tại, không phải với subscription. Khi pipeline chuyển sang thread khác, SecurityContextHolder hoặc MDC có thể không còn dữ liệu mong đợi nếu không có cơ chế context propagation phù hợp.

Reactor Context đi cùng subscription và là nơi thích hợp để mang dữ liệu contextual trong reactive flow. Với Spring Security reactive, dùng ReactiveSecurityContextHolder.

Không tự copy user ID từ request vào một static field hoặc ThreadLocal dùng chung; điều đó có thể làm lộ auditor giữa các request đồng thời.

### 7.5. Phân biệt created và modified metadata

Thông thường:

- CreatedDate và CreatedBy mô tả lần tạo đầu tiên.
- LastModifiedDate và LastModifiedBy mô tả lần cập nhật gần nhất.

Không ghi đè created metadata trong mỗi lần update nếu muốn giữ lịch sử tạo ban đầu. Cần kiểm thử hành vi auditing của phiên bản và cách entity được persist, đặc biệt khi application tự đặt giá trị hoặc dùng update script trực tiếp.

Auditing entity callback chỉ áp dụng khi thao tác đi qua cơ chế Spring Data có kích hoạt callback. Một update bằng low-level client hoặc script trực tiếp có thể không đi qua auditing lifecycle.

## 8. Side effect, transaction và tính lặp lại

### 8.1. Callback không phải transaction boundary

Không nên giả định entity callback tự tạo transaction bao trùm Elasticsearch và các hệ thống khác. Elasticsearch không tham gia một transaction phân tán ACID với database hoặc message broker chỉ vì callback được gọi trong lúc save.

Nếu callback ghi vào database khác rồi Elasticsearch save thất bại, hoặc ngược lại, ứng dụng có thể để lại trạng thái một phần.

Với nghiệp vụ cần tính nhất quán giữa nhiều hệ thống, dùng outbox, saga hoặc một quy trình có thể reconcile thay vì dựa vào callback để tạo transaction xuyên dịch vụ.

### 8.2. Callback có thể được chạy lại

Reactive Publisher có thể được subscribe lại. Retry operator cũng có thể thực hiện lại một phần pipeline. Ứng dụng hoặc framework có thể gọi lại thao tác sau lỗi.

Vì vậy callback nên:

- Ưu tiên logic thuần và xác định.
- Tránh tạo ID ngẫu nhiên mới mỗi lần chạy nếu ID cần ổn định.
- Làm side effect idempotent.
- Không giả định callback chỉ chạy đúng một lần.
- Ghi correlation ID/operation ID nếu cần deduplicate.

Đặc biệt, AfterSaveCallback có thể chạy sau một write thành công; nếu callback gửi notification rồi lỗi, retry toàn bộ save có thể gửi notification lần nữa.

### 8.3. Tránh gọi repository đệ quy

Ví dụ callback BeforeSave gọi lại repository để cập nhật cùng entity có thể kích hoạt chính callback đó lần nữa. Điều này dễ tạo recursion, nhiều request hoặc deadlock logic.

Nếu cần đồng bộ dữ liệu khác, chuyển logic ra service orchestration hoặc dùng một API thấp hơn có chủ đích và kiểm soát rõ lifecycle.

### 8.4. Không dùng callback thay thế service layer

Callback nên chứa logic gắn trực tiếp với lifecycle mapping/persistence. Quy tắc nghiệp vụ lớn, gọi nhiều aggregate, kiểm tra quyền, orchestration hoặc gửi nhiều thông điệp nên ở application service.

Đặt quá nhiều logic trong callback khiến thao tác repository có side effect khó thấy và làm việc kiểm thử trở nên khó khăn.

## 9. Error handling trong hai model

### 9.1. Imperative callback

Với callback đồng bộ, exception thường thoát trực tiếp khỏi method thao tác:

~~~java
try {
    operations.save(product);
} catch (RuntimeException error) {
    // Ghi nhận và xử lý lỗi ở tầng service.
    throw error;
}
~~~

Không nuốt exception trong callback rồi trả entity như thể thành công nếu dữ liệu chưa được chuẩn hóa hoặc invariant bị vi phạm.

### 9.2. Reactive callback

Với reactive callback, lỗi được biểu diễn bằng error signal:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    return validateAsync(entity)
        .thenReturn(entity);
}
~~~

Có thể xử lý lỗi ở tầng service bằng onErrorMap, onErrorResume hoặc retry có điều kiện. Không biến mọi lỗi thành Mono.empty() nếu điều đó khiến thao tác save âm thầm không chạy hoặc mất dữ liệu.

### 9.3. Phân biệt lỗi trước và sau persistence

| Điểm lỗi | Khả năng write đã xảy ra? | Cách xử lý |
|---|---|---|
| BeforeConvert | Thông thường chưa | Sửa dữ liệu hoặc logic callback |
| BeforeSave | Thông thường chưa | Kiểm tra Document và mapping |
| Request Elasticsearch | Có thể chưa, một phần hoặc đã xử lý nhưng response mất | Xử lý timeout/retry dựa trên idempotency |
| AfterSave | Có thể đã thành công | Kiểm tra trạng thái write; side effect cần deduplicate |
| AfterLoad/AfterConvert | Read đã xảy ra | Xử lý lỗi chuyển đổi hoặc dữ liệu đầu vào |

Đây là mô hình tư duy; chi tiết exception và thời điểm commit phụ thuộc thao tác, client và phiên bản. Đừng suy luận trạng thái persistence chỉ từ loại exception.

## 10. Đăng ký callback và ordering

### 10.1. Đăng ký callback dưới dạng Spring bean

Một callback thường được phát hiện qua bean registration:

~~~java
@Component
public class ProductBeforeConvert
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {
        // Lifecycle logic.
        return entity;
    }
}
~~~

Có thể khai báo bằng @Bean trong configuration nếu cần cấu hình dependency rõ ràng. Tránh tạo callback bằng new bên trong repository method vì khi đó Spring không quản lý dependency injection và ordering.

### 10.2. Ordering khi có nhiều callback

Nếu có nhiều callback cùng loại, implement Ordered hoặc dùng @Order theo cơ chế Spring Data hỗ trợ trong phiên bản hiện tại.

~~~java
@Component
@Order(100)
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

~~~java
@Component
@Order(200)
public class EnrichProductCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Ví dụ thể hiện ý định normalize trước enrich. Giá trị order thấp hơn thường có độ ưu tiên trước trong cơ chế ordering của Spring, nhưng hãy xác nhận semantics của callback registry đang dùng và kiểm thử thứ tự thực tế.

Reactive callback registry cũng cần ordering được kiểm tra; không suy ra thứ tự chỉ từ tên bean.

### 10.3. Tách logic chung khỏi adapter callback

Nếu cùng quy tắc chuẩn hóa cần dùng ở imperative và reactive stack:

~~~java
public class ProductNormalizer {

    public Product normalize(Product product) {
        if (product.getName() != null) {
            product.setNormalizedName(
                product.getName().trim().toLowerCase()
            );
        }
        return product;
    }
}
~~~

Imperative callback gọi trực tiếp normalizer. Reactive callback có thể gọi normalizer trong Mono.fromSupplier hoặc Mono.fromCallable nếu thao tác thực sự phù hợp.

Nếu logic chung cần I/O reactive, không ép nó thành method đồng bộ. Tạo service trả Publisher và để imperative adapter dùng một cách tích hợp phù hợp hoặc thiết kế rõ hai implementation.

## 11. Kiểm thử callback đồng bộ

### 11.1. Unit test callback

Vì callback imperative trả giá trị trực tiếp, unit test có thể gọi method và assert:

~~~java
@Test
void normalizesNameBeforeConvert() {
    Product product = new Product();
    product.setName("  Wireless Keyboard  ");

    Product result = callback.onBeforeConvert(
        product,
        IndexCoordinates.of("products")
    );

    assertThat(result.getNormalizedName())
        .isEqualTo("wireless keyboard");
}
~~~

Test này xác nhận logic callback, không xác nhận Spring Data đã đăng ký hoặc gọi callback đúng lifecycle.

### 11.2. Integration test với Elasticsearch

Dùng test instance tương thích để xác nhận:

- Callback được gọi khi save qua ElasticsearchOperations.
- Callback chạy trước conversion hoặc trước save đúng vị trí.
- Document thực tế có field được bổ sung.
- Callback sau save nhận kết quả phù hợp.
- Callback không được gọi khi code đi qua low-level client trực tiếp.

### 11.3. Kiểm tra thứ tự

Tạo hai callback có order khác nhau và ghi lại sequence trong test. Đừng chỉ kiểm tra kết quả cuối nếu callback sau có thể vô tình che lỗi callback trước.

## 12. Kiểm thử callback reactive

### 12.1. Dùng StepVerifier

Reactive callback trả Publisher, vì vậy có thể kiểm thử bằng Reactor StepVerifier:

~~~java
@Test
void normalizesNameReactively() {
    Product product = new Product();
    product.setName("  Wireless Keyboard  ");

    Mono<Product> result = Mono.from(
        callback.onBeforeConvert(
            product,
            IndexCoordinates.of("products")
        )
    );

    StepVerifier.create(result)
        .assertNext(saved -> assertThat(
            saved.getNormalizedName()
        ).isEqualTo("wireless keyboard"))
        .verifyComplete();
}
~~~

Test này subscribe Publisher và xác nhận kết quả. Không cần gọi subscribe thủ công rồi dùng latch nếu StepVerifier có thể điều khiển subscription.

### 12.2. Xác nhận lazy execution

Có thể kiểm tra callback chưa chạy trước subscription và chỉ chạy khi Publisher được subscribe:

~~~java
AtomicBoolean executed = new AtomicBoolean();

Mono<Product> result = Mono.defer(() -> {
    executed.set(true);
    return Mono.just(product);
});

assertThat(executed).isFalse();

StepVerifier.create(result)
    .expectNext(product)
    .verifyComplete();

assertThat(executed).isTrue();
~~~

Ví dụ này kiểm tra semantics của Mono.defer. Trong test integration, áp dụng ý tưởng tương tự để xác nhận callback thực tế nằm trong reactive pipeline.

### 12.3. Test error và cancellation

Kiểm tra:

- Callback trả Mono.error thì thao tác reactive phát error signal.
- Cancellation không để lại side effect chưa được quản lý.
- Retry không nhân side effect ngoài dự kiến.
- Callback không gọi block hoặc subscribe lồng.
- Publisher hoàn tất đúng một entity theo contract.

### 12.4. Test Reactor Context

Nếu callback đọc auditor hoặc tenant từ Reactor Context, hãy tạo context trong test:

~~~java
StepVerifier.create(
    Mono.from(callback.onBeforeConvert(product, index))
        .contextWrite(ctx -> ctx.put("tenantId", "tenant-7"))
)
.assertNext(result -> assertThat(result).isNotNull())
.verifyComplete();
~~~

Để test có ý nghĩa, callback phải thực sự dùng deferContextual hoặc API context tương ứng để đọc key. contextWrite không tự chuyển giá trị vào ThreadLocal.

### 12.5. Test integration qua ReactiveElasticsearchOperations

Unit test callback không chứng minh reactive template đã phát hiện callback. Hãy chạy integration test qua ReactiveElasticsearchOperations hoặc reactive repository và xác nhận:

- Callback được gọi khi subscription chạy.
- Entity/Document sau callback được ghi đúng.
- Error signal được truyền tới subscriber.
- Không có blocking call trên event-loop.
- Auditing lấy đúng auditor từ reactive context.

## 13. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Callback imperative không chạy trong reactive save | Đăng ký sai callback registry/interface | Dùng reactive callback contract đúng phiên bản |
| Reactive callback chạy nhưng không có thay đổi | Không trả entity đã biến đổi hoặc Publisher không phát giá trị | Return Mono<T>/Publisher<T> đúng contract |
| Logic reactive chạy trước khi subscribe | Thực hiện side effect khi tạo Publisher | Đặt logic trong defer, fromSupplier hoặc operator phù hợp |
| Event-loop bị block | Gọi block, sleep hoặc I/O blocking | Compose non-blocking Publisher |
| Callback tạo request nhưng save không chờ | Gọi subscribe nội bộ | Trả và compose Publisher |
| Không lấy được auditor trong reactive request | Dùng ThreadLocal/SecurityContextHolder imperative | Dùng ReactiveAuditorAware và Reactor/Security Context |
| Callback chạy nhiều lần | Nhiều subscription, retry hoặc nhiều lifecycle operation | Thiết kế callback idempotent và kiểm soát retry |
| Save báo lỗi nhưng document đã tồn tại | Exception phát sinh ở AfterSave hoặc response mất | Kiểm tra trạng thái và dùng ID/operation id ổn định |
| Callback không được gọi qua client trực tiếp | Bỏ qua Spring Data operations | Dùng Spring Data hoặc gọi logic riêng có chủ đích |
| Thứ tự callback không ổn định | Không khai báo order | Dùng Ordered/@Order và integration test |
| Save chậm bất thường | Callback đồng bộ thực hiện I/O hoặc reactive callback có operator blocking | Đưa I/O ra service phù hợp và đo latency callback |
| Auditing ghi sai người dùng | Auditor provider lấy sai context hoặc job không có principal | Định nghĩa system auditor và test cả request/job |
| Callback save gọi repository đệ quy | Persistence logic nằm trong callback | Chuyển orchestration ra service layer |

## 14. Quy trình chọn callback model

Khi thêm lifecycle logic cho Spring Data Elasticsearch:

1. Xác định ứng dụng dùng ElasticsearchOperations hay ReactiveElasticsearchOperations.
2. Chọn callback interface imperative hoặc reactive tương ứng.
3. Chọn lifecycle point: before convert, before save, after save, after load hoặc after convert.
4. Giữ callback ngắn và gắn trực tiếp với mapping/persistence lifecycle.
5. Nếu cần I/O, ưu tiên service phù hợp; trong reactive stack phải compose Publisher.
6. Không gọi block hoặc subscribe bên trong reactive callback.
7. Trả lại entity/Document đã được thay đổi.
8. Đăng ký callback thành Spring bean và khai báo order khi cần.
9. Cấu hình auditing với AuditorAware hoặc ReactiveAuditorAware theo stack.
10. Đảm bảo side effect idempotent và không giả định callback chạy đúng một lần.
11. Kiểm thử unit callback và integration qua đúng operations/template.
12. Theo dõi callback latency, error rate và side effect trong production.

## 15. Những điểm cần ghi nhớ

- Callback đồng bộ trả entity hoặc Document trực tiếp; callback reactive trả Publisher.
- Imperative callback chạy trong luồng thực thi của thao tác imperative.
- Reactive callback là một phần của pipeline và được thực thi khi subscription đi qua callback.
- Reactive không tự động tạo background thread; scheduler quyết định việc chuyển thread.
- Không dùng block hoặc subscribe bên trong reactive callback; hãy compose Publisher.
- Chọn callback lifecycle đúng: BeforeConvert, BeforeSave, AfterSave, AfterLoad hoặc AfterConvert.
- Đăng ký callback bằng Spring bean và khai báo ordering khi có nhiều callback phụ thuộc nhau.
- Auditing dùng các annotation created/modified và auditor provider phù hợp với imperative hoặc reactive context.
- Reactive auditing cần ReactiveAuditorAware; không dựa vào ThreadLocal để lấy user trong reactive pipeline.
- Callback không tạo transaction phân tán và không bảo đảm side effect exactly-once.
- AfterSave có thể lỗi sau khi write đã thành công; retry cần tính đến idempotency.
- Callback nên giữ logic ngắn, rõ và gắn với lifecycle; orchestration nghiệp vụ thuộc service layer.
- Kiểm thử reactive callback bằng StepVerifier, đồng thời integration test qua đúng reactive template/repository.
- Low-level Elasticsearch client không tự kích hoạt Spring Data entity callbacks.

Khi chọn đúng callback contract và execution model, ứng dụng có thể tái sử dụng logic lifecycle mà vẫn giữ được đặc tính đồng bộ hoặc non-blocking của stack đang sử dụng. Điều đó đặc biệt quan trọng với auditing, nơi thông tin người tạo/cập nhật phải theo đúng context của từng request và không bị mất khi reactive pipeline chuyển thread.
