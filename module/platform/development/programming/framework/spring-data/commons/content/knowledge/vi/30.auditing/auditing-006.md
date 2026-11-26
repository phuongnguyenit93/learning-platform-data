# ReactiveAuditorAware và dữ liệu trong Reactor Context

## 1. Mục tiêu và phạm vi

Trong chương **Auditing** của module **Spring Data Commons**, bài này giải thích cách cung cấp danh tính người tạo hoặc người sửa dữ liệu trong một luồng reactive.

Sau bài học, bạn cần làm được các việc sau:

- Triển khai `ReactiveAuditorAware<T>` trả về auditor của subscriber hiện tại.
- Đọc dữ liệu bằng `Mono.deferContextual` thay vì dựa vào thread hiện tại.
- Đặt `contextWrite` đúng vị trí để thao tác persistence nhìn thấy danh tính.
- Chọn chính sách khi không có auditor.
- Tích hợp reactive auditing theo store và kiểm tra dữ liệu đã lưu.

Ví dụ chính dùng Spring Data MongoDB reactive. Phần cuối chỉ ra cách áp dụng cùng abstraction cho R2DBC. Cấu hình của một store không tự kích hoạt auditing cho store khác.

## 2. ReactiveAuditorAware cung cấp dữ liệu gì?

`ReactiveAuditorAware<T>` là SPI của Spring Data Commons để cung cấp người hoặc hệ thống đang thực hiện thao tác:

```java
public interface ReactiveAuditorAware<T> {

    Mono<T> getCurrentAuditor();
}
```

Theo [ReactiveAuditorAware API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/ReactiveAuditorAware.html), publisher có thể phát auditor hiện tại hoặc hoàn thành rỗng nếu auditor được xem là chưa biết.

Nếu implementation là `ReactiveAuditorAware<String>`, các thuộc tính `@CreatedBy` và `@LastModifiedBy` tương ứng phải có kiểu phù hợp với `String`.

| Metadata | Ý nghĩa |
| --- | --- |
| `@CreatedBy` | Danh tính gắn với việc tạo entity |
| `@LastModifiedBy` | Danh tính gắn với lần sửa |
| `@CreatedDate` | Thời điểm tạo |
| `@LastModifiedDate` | Thời điểm sửa |

Auditor trả lời câu hỏi **ai thực hiện**. Các trường ngày giờ có cơ chế cung cấp thời gian riêng. Xem [Spring Data Commons Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

Auditing không tự thực hiện xác thực hoặc phân quyền. Việc có một auditor không đồng nghĩa thao tác đã được cấp quyền; việc không có auditor cũng không mặc nhiên làm mọi thao tác lưu thất bại.

## 3. Vì sao không lấy danh tính theo thread?

Trong ứng dụng đồng bộ, một số cơ chế giữ danh tính bằng `ThreadLocal`. Trong Reactor, một luồng xử lý có thể chuyển scheduler, còn cùng một thread có thể phục vụ nhiều chuỗi bất đồng bộ.

Vì vậy, không nên xây dựng reactive auditor bằng giả định:

```text
thread đang chạy
    -> chắc chắn là thread của request ban đầu
    -> chắc chắn chứa đúng user của request đó
```

`Reactor Context` gắn với subscriber trong chuỗi operator. Nó cho phép thành phần hạ tầng đọc dữ liệu ngữ cảnh mà không phải đưa danh tính vào mọi chữ ký phương thức nghiệp vụ.

Cần phân biệt:

| Thành phần | Mang dữ liệu nào? |
| --- | --- |
| Giá trị trong `Mono<T>` hoặc `Flux<T>` | Dữ liệu nghiệp vụ được phát qua pipeline |
| Reactor Context | Dữ liệu ngữ cảnh của subscriber |
| ThreadLocal | Trạng thái gắn với thread |
| Field của singleton bean | Trạng thái dùng chung của instance |

Không dùng field `currentUser` trong một singleton để thay cho context của từng subscriber.

Context cũng không tự xuất hiện chỉ vì ứng dụng có HTTP request. Phải có thành phần phù hợp cung cấp dữ liệu, chẳng hạn hạ tầng Spring Security reactive hoặc mã ứng dụng đặt một identity đã được xác minh.

## 4. Xây dựng auditor đọc từ Reactor Context

Ví dụ chọn lưu mã người thực hiện dưới dạng chuỗi. Dữ liệu trong context được đóng gói bằng một record để có hợp đồng rõ ràng.

### 4.1. Danh tính và khóa context

```java
package com.example.reactiveaudit;

import java.util.Objects;

public record AuditIdentity(String actorId) {

    public AuditIdentity {
        Objects.requireNonNull(actorId, "actorId must not be null");

        if (actorId.isBlank()) {
            throw new IllegalArgumentException(
                    "actorId must not be blank");
        }
    }
}
```

Khóa context được chọn là `AuditIdentity.class`; giá trị tương ứng phải là một `AuditIdentity`. Bên ghi và bên đọc phải dùng cùng khóa và cùng hợp đồng kiểu.

Identity này nên được tạo từ nguồn do ứng dụng kiểm soát. Không lấy một tham số tùy ý trong request rồi coi nó là người thực hiện đã được xác thực.

### 4.2. Implementation

```java
package com.example.reactiveaudit;

import org.springframework.data.domain.ReactiveAuditorAware;
import reactor.core.publisher.Mono;

public final class ReactorContextAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return Mono.deferContextual(contextView ->
                Mono.justOrEmpty(
                        contextView.<AuditIdentity>getOrEmpty(
                                AuditIdentity.class))
                    .map(AuditIdentity::actorId));
    }
}
```

Luồng xử lý:

```text
Subscriber bắt đầu thực thi
    -> deferContextual nhận ContextView
    -> đọc AuditIdentity bằng khóa đã thống nhất
    -> phát actorId
    -> auditing infrastructure nhận auditor
```

`deferContextual` đọc context khi publisher được subscribe, thay vì cố chụp danh tính từ lúc xây dựng pipeline.

Khi khóa không tồn tại, implementation trên trả `Mono.empty()`. Đây là chính sách “không biết auditor”, chưa phải chính sách bắt buộc từ chối thao tác ghi.

## 5. contextWrite phải bao quanh đúng công việc

### 5.1. Cách đặt có hiệu lực

Với một publisher đọc auditor:

```java
ReactiveAuditorAware<String> auditorAware =
        new ReactorContextAuditorAware();

Mono<String> currentAuditor = auditorAware.getCurrentAuditor()
        .contextWrite(context ->
                context.put(
                        AuditIdentity.class,
                        new AuditIdentity("user-42")));
```

Khi subscribe, kết quả mong đợi là `user-42`.

Reactor Context được truyền theo hướng subscription từ downstream lên upstream. Vì vậy, `contextWrite` thường nằm phía sau đoạn pipeline cần đọc context trong cách viết chuỗi phương thức.

Tài liệu [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) giải thích tính bất biến, phạm vi subscriber và ảnh hưởng của vị trí operator.

### 5.2. Một vị trí không bao phủ phần đọc

```java
Mono<String> missingAuditor = Mono.just("start")
        .contextWrite(context ->
                context.put(
                        AuditIdentity.class,
                        new AuditIdentity("user-42")))
        .flatMap(ignored -> auditorAware.getCurrentAuditor());
```

Không có context bổ sung từ bên ngoài, đoạn đọc auditor trong `flatMap` phía sau không nhìn thấy identity được đặt chỉ cho phần upstream trước đó.

Với implementation ở mục 4, publisher này được kỳ vọng hoàn thành rỗng.

Một cách sửa là đặt context cho toàn đoạn công việc:

```java
Mono<String> resolvedAuditor = Mono.just("start")
        .flatMap(ignored -> auditorAware.getCurrentAuditor())
        .contextWrite(context ->
                context.put(
                        AuditIdentity.class,
                        new AuditIdentity("user-42")));
```

### 5.3. Context của một nhánh không tự đổi các nhánh khác

Trong `flatMap`, `contextWrite` trên một inner publisher có phạm vi của nhánh đó. Điều này hữu ích khi từng công việc cần một identity riêng.

Không giả định việc đặt identity cho một lần lưu sẽ tự cập nhật context của tất cả thao tác viết tiếp theo trong chuỗi. Hãy bao quanh đúng operation hoặc đúng đoạn workflow cần cùng danh tính.

Ngoài ra, `Context.put` trả về context mới. Khi dùng lambda, phải trả lại kết quả mới; gọi `put` rồi trả context cũ sẽ không áp dụng thay đổi như mong đợi.

## 6. Tích hợp với reactive auditing của MongoDB

### 6.1. Cấu hình hạ tầng

```java
package com.example.reactiveaudit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration
@EnableReactiveMongoAuditing(
        auditorAwareRef = "reactorAuditorAware",
        modifyOnCreate = true)
public class ReactiveAuditConfiguration {

    @Bean
    public ReactiveAuditorAware<String> reactorAuditorAware() {
        return new ReactorContextAuditorAware();
    }
}
```

Ví dụ giả định ứng dụng đã cấu hình kết nối MongoDB reactive, repository scanning và dependency phù hợp. Các lớp minh họa dùng Java 17 trở lên.

`auditorAwareRef` chọn rõ bean cung cấp auditor. `modifyOnCreate=true` thể hiện rằng entity mới cũng được đánh dấu đã sửa khi tạo. Xem [EnableReactiveMongoAuditing API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableReactiveMongoAuditing.html).

Đăng ký bean `ReactiveAuditorAware` chưa thay thế bước kích hoạt auditing của store. Xem thêm [MongoDB Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html).

### 6.2. Entity và repository

```java
package com.example.reactiveaudit;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("audited_notes")
public class AuditedNote {

    @Id
    private String id;

    private String title;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    public AuditedNote() {
    }

    public AuditedNote(String title) {
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

```java
package com.example.reactiveaudit;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface AuditedNoteRepository
        extends ReactiveMongoRepository<AuditedNote, String> {
}
```

Các trường auditor đều có kiểu `String`, phù hợp với `ReactiveAuditorAware<String>`. Không cần truyền `createdBy` và `lastModifiedBy` từ dữ liệu nhập của người dùng trong ví dụ này.

### 6.3. Tạo bởi A, sửa bởi B

Đoạn dưới giả định đã có bean `repository`:

```java
Mono<AuditedNote> workflow =
        Mono.defer(() ->
                repository.save(
                        new AuditedNote("Bản nháp")))
            .contextWrite(context ->
                    context.put(
                            AuditIdentity.class,
                            new AuditIdentity("user-a")))
            .flatMap(note -> {
                note.setTitle("Đã cập nhật");

                return repository.save(note)
                        .contextWrite(context ->
                                context.put(
                                        AuditIdentity.class,
                                        new AuditIdentity("user-b")));
            });

Mono<AuditedNote> readback = workflow.flatMap(note ->
        repository.findById(note.getId()));
```

`Mono.defer` tạo entity mới cho mỗi subscription vào workflow. Điều này tránh vô tình dùng lại cùng một object mutable đã được gán id hoặc audit metadata từ subscription trước.

Khi subscribe một lần và các thao tác đều thành công, kỳ vọng cuối cùng:

| Thuộc tính | Giá trị |
| --- | --- |
| `title` | `Đã cập nhật` |
| `createdBy` | `user-a` |
| `lastModifiedBy` | `user-b` |

Lần đọc lại không tự đổi người sửa thành danh tính của người đang đọc. Auditor của thao tác ghi và người đọc dữ liệu là hai khái niệm khác nhau.

Kỳ vọng còn phụ thuộc việc store nhận diện entity mới hay đã tồn tại đúng. Nếu tự gán id hoặc tùy biến `isNew`, cần xác minh riêng việc phân biệt tạo mới với sửa.

## 7. Khi đã dùng Spring Security reactive

Nếu danh tính đã nằm trong security context reactive, có thể đọc trực tiếp qua `ReactiveSecurityContextHolder` thay vì tạo thêm một khóa identity riêng chỉ để sao chép dữ liệu.

Một implementation thay thế:

```java
package com.example.reactiveaudit;

import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public final class SecurityReactiveAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(securityContext ->
                        Mono.justOrEmpty(
                                securityContext.getAuthentication()))
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication
                                instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .filter(name -> !name.isBlank());
    }
}
```

Đây là phương án thay thế cho provider ở mục 4. Nếu đăng ký nhiều provider, cần chọn bean rõ ràng trong cấu hình auditing.

Các điểm cần hiểu:

- `ReactiveSecurityContextHolder` đọc security context từ Reactor Context.
- Không thay nó bằng lời gọi imperative `SecurityContextHolder` rồi kỳ vọng luôn nhận đúng danh tính của pipeline.
- Trạng thái `isAuthenticated` cần được hiểu cùng mô hình authentication của ứng dụng; ví dụ chủ động loại anonymous token.
- `Authentication.getName()` chỉ phù hợp nếu ứng dụng đã chọn giá trị đó làm định danh audit.

Nếu cần mã tài khoản bất biến, hãy ánh xạ principal sang mã đó theo hợp đồng của hệ thống. Không mặc định principal luôn có một class domain cụ thể hoặc luôn là `UserDetails`.

Xem [ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html) và ví dụ reactive auditor trong [Commons Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

## 8. Chọn chính sách khi không có auditor

### 8.1. Chấp nhận trạng thái chưa biết

Implementation ở mục 4 hoàn thành rỗng khi context thiếu identity. Theo hợp đồng SPI, đó là một kết quả hợp lệ.

Không suy ra rằng mọi trường audit sẽ tự bị đặt thành null. Đối với entity đã có metadata, hành vi cập nhật còn phụ thuộc auditing handler, trạng thái entity và mapping.

Trong implementation `ReactiveAuditingHandler` nhánh 3.5.x, auditor rỗng được chuyển thành trạng thái không có auditor để tiếp tục xử lý. Xem [ReactiveAuditingHandler 3.5.x](https://github.com/spring-projects/spring-data-commons/blob/3.5.x/src/main/java/org/springframework/data/auditing/ReactiveAuditingHandler.java).

Nếu thao tác bắt buộc phải có người thực hiện, chỉ trả `Mono.empty()` không diễn đạt đủ chính sách đó.

### 8.2. Bắt buộc phải có identity

Có thể định nghĩa provider theo chính sách yêu cầu auditor:

```java
ReactiveAuditorAware<String> requiredAuditor =
        () -> new ReactorContextAuditorAware()
                .getCurrentAuditor()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "Auditor is required")));
```

Đây là ví dụ tạo provider thay thế, không phải đăng ký thêm một bean mà chưa chọn provider được sử dụng.

Lỗi tham gia vào reactive pipeline. Không nuốt lỗi bằng `onErrorResume` rồi tiếp tục coi thao tác như đã được audit đầy đủ.

Auditing vẫn không thay thế authorization. Quyền thực hiện thao tác phải được kiểm soát theo thiết kế của ứng dụng.

### 8.3. Công việc nền dùng identity hệ thống tường minh

Một job không có HTTP request có thể chủ động cung cấp:

```java
Mono<AuditedNote> jobWrite =
        Mono.defer(() ->
                repository.save(
                        new AuditedNote("Tổng hợp định kỳ")))
            .contextWrite(context ->
                    context.put(
                            AuditIdentity.class,
                            new AuditIdentity("system:scheduled-job")));
```

Điều này khác với việc tự động dùng `system` cho mọi request bị thiếu context.

| Tình huống | Chính sách phù hợp cần được quyết định |
| --- | --- |
| Người dùng đã xác thực | Identity từ nguồn xác thực của ứng dụng |
| Job được hệ thống chủ động chạy | Identity hệ thống được cấp rõ ràng |
| Context bị mất ngoài ý muốn | Phát hiện lỗi hoặc xử lý theo hợp đồng đã chọn |
| Thao tác cho phép không có người thực hiện | Auditor rỗng có chủ đích |

Không dùng fallback để che lỗi truyền context mà chưa phân biệt những tình huống này.

## 9. Những cách làm gây sai danh tính

### 9.1. Chụp danh tính quá sớm

```text
Khởi tạo singleton
    -> đọc current user một lần
    -> giữ lại cho mọi lần ghi sau đó
```

Cách này không phản ánh danh tính của subscriber hiện tại.

Ngay cả `Mono.defer` cũng không biến một nguồn dữ liệu sai thành đúng: trì hoãn việc đọc `ThreadLocal` không tự tạo hợp đồng truyền danh tính giữa các scheduler.

### 9.2. Cache kết quả auditor trên publisher dùng chung

Một mẫu cần tránh:

```java
private final Mono<String> sharedAuditor =
        new ReactorContextAuditorAware()
                .getCurrentAuditor()
                .cache();
```

Nếu publisher này được dùng chung giữa nhiều request, kết quả của lần subscription đầu có thể được phát lại cho các subscriber sau. Auditor không còn được đọc riêng theo context của từng subscriber.

Vấn đề ở đây là phạm vi của cache kết quả trên publisher dùng chung. Không suy rộng rằng mọi cách cache cục bộ trong một workflow đều có cùng hành vi; phạm vi dữ liệu phải được xác định rõ.

### 9.3. Tách subscription của thao tác ghi

```java
repository.save(note).subscribe();
```

Lời gọi như vậy bên trong service đang được một pipeline khác sử dụng tạo một subscription riêng. Không được giả định nó tự kế thừa context và vòng đời lỗi của caller.

Hãy trả publisher và ghép công việc bằng `flatMap`, `then` hoặc operator phù hợp, để bên gọi quản lý cùng một pipeline.

### 9.4. Cho rằng đổi scheduler luôn làm mất Reactor Context

Đổi scheduler không tự đồng nghĩa context bị mất trong một pipeline Reactor được ghép đúng. Đây là điểm khác với việc dựa vào ThreadLocal.

Khi thiếu auditor, trước tiên kiểm tra vị trí `contextWrite`, các subscription bị tách và ranh giới tích hợp. Không chỉ thêm `publishOn` hoặc `subscribeOn` để thử khắc phục lỗi danh tính.

## 10. Kiểm tra riêng provider và đường persistence

### 10.1. Kiểm tra publisher của auditor

Các ví dụ kiểm tra sau dùng JUnit Jupiter và `reactor-test`. Chúng kiểm tra hành vi context, chưa cần database.

```java
package com.example.reactiveaudit;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextAuditorAwareTest {

    private final ReactorContextAuditorAware auditorAware =
            new ReactorContextAuditorAware();

    @Test
    void resolvesIdentityForEachSubscription() {
        Mono<String> source = auditorAware.getCurrentAuditor();

        StepVerifier.create(
                source.contextWrite(context ->
                        context.put(
                                AuditIdentity.class,
                                new AuditIdentity("user-a"))))
                .expectNext("user-a")
                .verifyComplete();

        StepVerifier.create(
                source.contextWrite(context ->
                        context.put(
                                AuditIdentity.class,
                                new AuditIdentity("user-b"))))
                .expectNext("user-b")
                .verifyComplete();

        StepVerifier.create(source)
                .verifyComplete();
    }

    @Test
    void contextMustCoverTheOperationThatReadsIt() {
        Mono<String> wrongScope = Mono.just("start")
                .contextWrite(context ->
                        context.put(
                                AuditIdentity.class,
                                new AuditIdentity("user-a")))
                .flatMap(ignored ->
                        auditorAware.getCurrentAuditor());

        StepVerifier.create(wrongScope)
                .verifyComplete();

        Mono<String> correctScope = Mono.just("start")
                .flatMap(ignored ->
                        auditorAware.getCurrentAuditor())
                .contextWrite(context ->
                        context.put(
                                AuditIdentity.class,
                                new AuditIdentity("user-a")));

        StepVerifier.create(correctScope)
                .expectNext("user-a")
                .verifyComplete();
    }
}
```

Cùng một publisher `source` ở phép kiểm tra đầu được subscribe với các context khác nhau. Vì nó đọc context theo subscription và không cache kết quả dùng chung, mỗi subscriber nhận đúng kết quả của mình.

`StepVerifier` thực thi phép kiểm tra khi gọi các phương thức kết thúc như `verifyComplete`. Xem [Reactor Testing](https://projectreactor.io/docs/core/release/reference/testing.html).

### 10.2. Kiểm tra tích hợp auditing của store

Provider hoạt động đúng chưa chứng minh entity đã được ghi audit metadata.

Với workflow ở mục 6, cần kiểm tra:

1. Tạo entity mới với `user-a`.
2. Xác nhận metadata tạo và sửa phù hợp với `modifyOnCreate`.
3. Sửa entity đã có id với `user-b`.
4. Đọc lại từ store.
5. Xác nhận `createdBy` vẫn là `user-a` và `lastModifiedBy` là `user-b`.
6. Thử trường hợp không có context theo chính sách đã chọn.
7. Chạy các workflow độc lập có identity khác nhau, xác nhận không bị dùng lẫn auditor.

Không dùng một entity mutable duy nhất cho nhiều subscription đồng thời trong phép kiểm tra. Khi đó, object bị chia sẻ có thể gây lỗi độc lập với Reactor Context.

## 11. Áp dụng cho R2DBC và giới hạn đường ghi

Với R2DBC, module có annotation riêng để kích hoạt auditing:

```java
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@EnableR2dbcAuditing(auditorAwareRef = "reactorAuditorAware")
```

Đây là phần annotation/import minh họa cho cấu hình R2DBC tương ứng. Không ghép annotation này vào một ứng dụng chỉ có MongoDB rồi kỳ vọng có thêm auditing cho cơ sở dữ liệu quan hệ.

Provider `ReactiveAuditorAware<String>` có thể dùng lại nếu các trường audit và nguồn identity có cùng hợp đồng. Model, mapping, schema và hạ tầng store vẫn phải được cấu hình riêng. Xem [R2DBC Auditing](https://docs.spring.io/spring-data/relational/reference/r2dbc/auditing.html).

Reactor Context chỉ cung cấp dữ liệu cho đường xử lý đang sử dụng nó. Nó không khiến một modifying query, native SQL hoặc driver API tự tham gia vào auditing callback của entity.

Nếu một đường update bỏ qua auditing của store, cần xử lý metadata tường minh theo thiết kế của đường đó. Không kết luận context sai chỉ vì một API không kích hoạt auditing ngay từ đầu.

Ngoài ra, actor id, tenant id và correlation id có vai trò khác nhau. Lưu người sửa không tự thiết lập phạm vi tenant; lưu correlation id không tự tạo lịch sử thay đổi đầy đủ.

## 12. Chẩn đoán theo từng mắt xích

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| getCurrentAuditor trả rỗng | Khóa context, vị trí contextWrite và chính sách identity |
| Auditor đúng trong unit test nhưng trường vẫn rỗng | Cấu hình auditing, bean được chọn, annotation và mapping |
| createdBy không được gán như kỳ vọng | Store có nhận diện đúng entity mới hay không |
| Request sau nhận auditor của request trước | Field dùng chung, publisher cache hoặc object mutable dùng chung |
| Chỉ API reactive không có audit | Có dùng đúng ReactiveAuditorAware và cấu hình reactive của store không |
| Context có trong controller nhưng không có khi ghi | Subscription bị tách hoặc phạm vi context không bao phủ thao tác |
| Job nền không có user | Job đã được cấp identity hệ thống tường minh chưa |
| Đọc lại không thay lastModifiedBy | Đây có thể là hành vi đúng: đọc không phải sửa |
| Auditor lookup tự gọi lại vô hạn | Provider có gọi đường lưu entity đang được audit hay không |

Nếu cần tra cứu auditor từ dịch vụ hoặc database, giữ việc tra cứu trong publisher không blocking. Tránh gọi một thao tác lưu có auditing từ chính provider để tìm auditor, vì có thể tạo vòng phụ thuộc lặp lại.

Phần lớn trường hợp nên trả một định danh phù hợp đã có trong context, thay vì tải lại toàn bộ user entity chỉ để ghi mã người thực hiện.

## 13. Bài thực hành

Thực hiện với một store reactive đã chọn:

1. Tạo identity bất biến và thống nhất khóa context.
2. Triển khai provider dùng `deferContextual`.
3. Kích hoạt auditing đúng module và chọn bean tường minh.
4. Tạo bởi A, sửa bởi B và đọc lại dữ liệu audit.
5. Kiểm tra context đúng vị trí và sai vị trí.
6. Kiểm tra hai subscriber có danh tính khác nhau cùng dùng một publisher đọc context.
7. Chọn rõ chính sách cho request thiếu identity và cho job hệ thống.
8. Nếu ứng dụng dùng Spring Security reactive, so sánh phương án đọc security context trực tiếp với identity riêng của ứng dụng.

Bài thực hành đạt yêu cầu khi bạn lần theo được **nguồn danh tính**, **phạm vi subscriber**, **thời điểm đọc context**, **provider được auditing sử dụng** và **metadata thực sự được lưu**, đồng thời giải thích được hành vi khi context không có auditor.
