# Ranh giới Reactor Context, bảo mật và giao dịch do store cung cấp

## 1. Mục tiêu và phạm vi

Trong chương **Repository reactive** của module **Spring Data Commons**, bài này giải thích cách ngữ cảnh subscriber, danh tính người dùng và tài nguyên transaction phối hợp khi gọi repository reactive.

Sau bài học, bạn cần làm được các việc sau:

- Đọc và ghi Reactor Context ở đúng phạm vi subscription.
- Lấy danh tính qua hạ tầng bảo mật reactive phù hợp.
- Phân biệt có danh tính với được phép truy cập dữ liệu.
- Chọn transaction manager tương ứng với store.
- Ghép các thao tác cần nguyên tử trong cùng một đường reactive.
- Kiểm tra kết quả commit, rollback và cách ly ngữ cảnh giữa các subscriber.

Ví dụ chính dùng R2DBC: chủ sở hữu sửa nội dung ghi chú và hệ thống ghi một dòng lịch sử trong cùng transaction. MongoDB được dùng để đối chiếu trách nhiệm của transaction manager theo store.

## 2. Phân công trách nhiệm giữa các tầng

| Tầng | Trách nhiệm chính | Điều không tự suy ra từ tầng đó |
| --- | --- | --- |
| Spring Data Commons | Hợp đồng repository và abstraction dùng chung | Mọi store có cùng transaction hoặc isolation |
| Reactor | Ghép publisher, truyền Context theo subscriber | Một giá trị trong Context đã được xác thực |
| Spring Security reactive | Quản lý security context và thực thi quy tắc bảo mật được cấu hình | Mọi query đã có điều kiện chủ sở hữu hoặc tenant |
| Transaction manager reactive | Quản lý transaction và tài nguyên tương ứng | Tự bao phủ mọi database hoặc lời gọi HTTP |
| Mô-đun, driver và database | Thực thi thao tác lưu trữ | Có mọi khả năng chỉ vì kiểu trả về là Mono hoặc Flux |

Một `ReactiveCrudRepository` không tự tạo hợp đồng transaction nghiệp vụ cho một chuỗi nhiều repository call. Khả năng thực tế cần được xác định ở store, manager và đường thực thi.

Ba câu hỏi nên được trả lời riêng:

1. Ngữ cảnh nào có mặt khi subscriber thực thi?
2. Danh tính nào được chấp nhận và được phép làm gì?
3. Những tài nguyên nào thực sự tham gia transaction?

## 3. Reactor Context thuộc subscriber, không thuộc thread

Trong một luồng reactive, cùng một thread có thể phục vụ nhiều subscriber; một subscriber cũng có thể đi qua nhiều scheduler. Vì vậy, tên thread hoặc một `ThreadLocal` tự tạo không đủ để nhận diện request hiện tại.

Reactor Context gắn với subscriber. `contextWrite` làm dữ liệu có hiệu lực cho phần upstream tương ứng; `deferContextual` đọc Context khi được subscribe. Context bất biến: thao tác `put` tạo một Context mới.

Xem [Reactor: Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).

Một giá trị chỉ phục vụ theo dõi request:

~~~java
package com.example.contextnotes;

import java.util.Objects;

public record RequestTrace(String correlationId) {

    public RequestTrace {
        Objects.requireNonNull(
                correlationId,
                "correlationId");

        if (correlationId.isBlank()) {
            throw new IllegalArgumentException(
                    "correlationId must not be blank");
        }
    }
}
~~~

Một publisher đọc nó:

~~~java
import reactor.core.publisher.Mono;

Mono<String> readTrace = Mono.deferContextual(context ->
        Mono.justOrEmpty(
                context.<RequestTrace>getOrEmpty(
                        RequestTrace.class))
            .map(RequestTrace::correlationId));
~~~

Gán trace cho phần đọc:

~~~java
Mono<String> traced = readTrace
        .contextWrite(context ->
                context.put(
                        RequestTrace.class,
                        new RequestTrace("trace-a")));
~~~

Khi subscribe vào `traced`, phần đọc nhìn thấy `trace-a`. Nếu subscribe vào `readTrace` mà không có Context bổ sung, nó hoàn tất rỗng theo implementation này.

Các object được lưu trong Context vẫn cần có thiết kế phù hợp. Context bất biến không làm một `ArrayList` mutable chứa bên trong tự trở thành bất biến.

## 4. Vị trí operator và cách bảo toàn Context

### 4.1. Bao quanh đúng phần công việc

Không có Context bổ sung từ bên ngoài, đoạn sau không cấp trace cho phần đọc phía sau `flatMap`:

~~~java
Mono<String> wrongScope = Mono.just("start")
        .contextWrite(context ->
                context.put(
                        RequestTrace.class,
                        new RequestTrace("trace-a")))
        .flatMap(ignored -> readTrace);
~~~

Đặt phần ghi Context sau đoạn công việc cần đọc nó:

~~~java
Mono<String> covered = Mono.just("start")
        .flatMap(ignored -> readTrace)
        .contextWrite(context ->
                context.put(
                        RequestTrace.class,
                        new RequestTrace("trace-a")));
~~~

Context truyền theo hướng subscription, từ downstream lên upstream. Chỉ nhìn thứ tự các giá trị dữ liệu được phát sẽ dễ hiểu sai phạm vi này.

### 4.2. Thêm dữ liệu thay vì thay toàn bộ Context

Một cách dễ gây mất thông tin:

~~~java
.contextWrite(ignored ->
        reactor.util.context.Context.of(
                RequestTrace.class,
                trace))
~~~

Tại phạm vi bị thay thế, cách này có thể bỏ những entry từ hạ tầng khác, bao gồm thông tin bảo mật hoặc transaction đã có ở downstream.

Cách thêm trace và giữ các entry còn lại:

~~~java
.contextWrite(context ->
        context.put(RequestTrace.class, trace))
~~~

Không tự tìm, sao chép hoặc ghi đè các khóa transaction nội bộ. Đó là trách nhiệm của transaction infrastructure.

### 4.3. Đổi scheduler và tạo subscription mới là hai việc khác nhau

Một `publishOn` trong pipeline Reactor được ghép đúng không tự đồng nghĩa Context bị mất. Ngược lại, gọi `subscribe()` thủ công để tách công việc tạo một ranh giới thực thi khác.

Khi thiếu Context, hãy kiểm tra phạm vi operator, subscription bị tách và ranh giới tích hợp trước khi thêm scheduler.

## 5. Security Context là ngữ cảnh do hạ tầng bảo mật quản lý

Spring Security reactive có `ReactiveSecurityContextHolder` để đọc `Mono<SecurityContext>` từ Reactor Context. Nó khác cơ chế imperative thường gắn với `SecurityContextHolder` và thread.

Xem [ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).

Một thành phần lấy actor:

~~~java
package com.example.contextnotes;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class CurrentActor {

    public Mono<String> requireActorId() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(securityContext ->
                        Mono.justOrEmpty(
                                securityContext.getAuthentication()))
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication
                                instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .filter(name -> !name.isBlank())
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authenticated actor required")));
    }
}
~~~

Ví dụ giả định ứng dụng chọn `Authentication.getName()` làm định danh actor phù hợp. Nếu tên đăng nhập có thể đổi hoặc không phải mã tài khoản, cần ánh xạ principal sang định danh theo hợp đồng hệ thống.

Không suy từ `isAuthenticated()` rằng mọi token đều đại diện cho một người dùng nghiệp vụ đã được cấp quyền. Ví dụ chủ động loại anonymous token; mô hình authentication thực tế vẫn phải được cấu hình đúng.

Trong ứng dụng HTTP, security filter chain phù hợp chịu trách nhiệm xác thực và thiết lập security context. Tự đặt một chuỗi `userId` lấy từ request vào Context không thực hiện các bước đó.

## 6. Có danh tính chưa đủ quyền truy cập dữ liệu

Có thể tách yêu cầu bảo mật của ví dụ thành hai lớp:

| Quy tắc | Cách thể hiện trong ví dụ |
| --- | --- |
| Actor có quyền sửa ghi chú | Method security kiểm tra authority `note:write` |
| Actor được sửa đúng ghi chú này | Query kèm điều kiện `ownerId` của actor |

Cấu hình `@EnableReactiveMethodSecurity` kích hoạt hạ tầng method security reactive. Method được bảo vệ trả về `Mono` hoặc `Flux` phù hợp để tích hợp với Context.

Xem [Spring Security: Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html).

Một query chỉ `findById(id)` không tự biết tenant hoặc chủ sở hữu vì Context có các giá trị đó. Phải có thành phần cụ thể áp dụng chúng vào điều kiện truy vấn hoặc kiểm tra quyền.

Tương tự, `@CreatedBy` hoặc `@LastModifiedBy` ghi danh tính audit không thay cho authorization.

Nếu dùng tenant context, cần giải quyết cả nguồn tenant đã được kiểm tra và cách giới hạn dữ liệu. Một tenant id trong header không đủ để kết luận người gọi thuộc tenant đó.

Correlation id phục vụ theo dõi, actor id phục vụ nhận diện và tenant id phục vụ phân vùng dữ liệu. Không dùng một giá trị thay cho cả ba vai trò.

## 7. Transaction reactive được gắn với tài nguyên của store

### 7.1. R2DBC

`R2dbcTransactionManager` quản lý transaction cho một `ConnectionFactory` và gắn connection vào subscriber context. Các thành phần Spring như `DatabaseClient` lấy connection theo cơ chế hỗ trợ transaction.

Gọi trực tiếp `ConnectionFactory.create()` thông thường không mặc nhiên lấy connection đang tham gia transaction của Spring.

Xem [R2dbcTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/r2dbc/connection/R2dbcTransactionManager.html).

Vì vậy, cần dùng cùng hạ tầng ConnectionFactory phù hợp giữa manager và các thao tác dữ liệu. Hai repository có kiểu trả về giống nhau nhưng trỏ hai tài nguyên khác nhau chưa tự có chung transaction.

### 7.2. MongoDB reactive

`ReactiveMongoTransactionManager` gắn session phục vụ transaction vào Reactor Context. Template tương ứng cần dùng cùng `ReactiveMongoDatabaseFactory` để tham gia tài nguyên đó.

Việc tự dùng `ClientSession` qua API template và việc dùng manager là những cơ chế cần đọc đúng hợp đồng; không suy rằng mọi driver call tự tham gia session.

Xem [Spring Data MongoDB: Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).

Ngoài cấu hình Java, deployment database phải hỗ trợ transaction tương ứng. Thêm manager không bổ sung một khả năng mà server hoặc topology không có.

### 7.3. Giới hạn tài nguyên

Một transaction R2DBC cục bộ không tự bao phủ việc ghi MongoDB, gọi HTTP hoặc gửi email. Reactor Context có thể hiện diện trong toàn workflow nhưng khả năng nguyên tử vẫn bị giới hạn bởi transaction manager và tài nguyên tham gia.

Nếu nghiệp vụ cần phối hợp nhiều hệ thống, phải thiết kế cơ chế phù hợp như lưu ý định gửi, xử lý bù hoặc điều phối riêng. Không coi một annotation là transaction phân tán mặc định.

## 8. Ví dụ R2DBC: sửa ghi chú và ghi lịch sử

Các public type trong ví dụ đặt trong file Java riêng khi đưa vào project. Ví dụ giả định Java 17 trở lên, R2DBC ConnectionFactory, repository scanning, schema và driver đã được cấu hình.

Schema cần hỗ trợ hai bảng tương ứng, id sinh cho dòng lịch sử, cột version và kiểu thời gian phù hợp.

### 8.1. Model và repository

~~~java
package com.example.contextnotes;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("notes")
public record Note(
        @Id Long id,
        @Column("owner_id") String ownerId,
        String body,
        @Version Long version) {

    public Note withBody(String nextBody) {
        return new Note(id, ownerId, nextBody, version);
    }
}
~~~

Dòng lịch sử được ghi tường minh:

~~~java
package com.example.contextnotes;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("note_changes")
public record NoteChange(
        @Id Long id,
        @Column("note_id") Long noteId,
        @Column("actor_id") String actorId,
        @Column("correlation_id") String correlationId,
        @Column("changed_at") Instant changedAt) {
}
~~~

~~~java
package com.example.contextnotes;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Mono;

public interface NoteRepository
        extends ReactiveCrudRepository<Note, Long> {

    Mono<Note> findByIdAndOwnerId(
            Long id,
            String ownerId);
}
~~~

~~~java
package com.example.contextnotes;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface NoteChangeRepository
        extends ReactiveCrudRepository<NoteChange, Long> {
}
~~~

`@Version` phục vụ optimistic locking ở đường lưu entity được hỗ trợ. Nó là lớp kiểm soát cạnh tranh riêng; transaction không tự ngăn mọi kiểu lost update chỉ vì có nhiều câu lệnh cùng transaction.

### 8.2. Cấu hình manager, operator và method security

~~~java
package com.example.contextnotes;

import java.time.Clock;

import io.r2dbc.spi.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
@EnableReactiveMethodSecurity
public class NoteInfrastructureConfiguration {

    @Bean("noteTransactionManager")
    public ReactiveTransactionManager noteTransactionManager(
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(
                connectionFactory);
    }

    @Bean("noteTx")
    public TransactionalOperator noteTx(
            @Qualifier("noteTransactionManager")
            ReactiveTransactionManager manager) {

        return TransactionalOperator.create(manager);
    }

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Cấu hình giả định một ConnectionFactory phù hợp cho cả hai repository. Nếu có nhiều factory, cần chỉ rõ factory và phạm vi repository của từng store.

Cấu hình method security không thay thế cấu hình xác thực HTTP của ứng dụng.

### 8.3. Service ghép cả hai lần ghi

~~~java
package com.example.contextnotes;

import java.time.Clock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

@Service
public class NoteService {

    private final NoteRepository notes;
    private final NoteChangeRepository changes;
    private final CurrentActor currentActor;
    private final TransactionalOperator tx;
    private final Clock clock;

    public NoteService(
            NoteRepository notes,
            NoteChangeRepository changes,
            CurrentActor currentActor,
            @Qualifier("noteTx") TransactionalOperator tx,
            Clock clock) {

        this.notes = notes;
        this.changes = changes;
        this.currentActor = currentActor;
        this.tx = tx;
        this.clock = clock;
    }

    @PreAuthorize("hasAuthority('note:write')")
    public Mono<Note> changeBody(
            Long noteId,
            String nextBody) {

        return Mono.deferContextual(context -> {
            if (noteId == null
                    || nextBody == null
                    || nextBody.isBlank()) {

                return Mono.error(
                        new IllegalArgumentException(
                                "noteId and body are required"));
            }

            RequestTrace trace = context.getOrDefault(
                    RequestTrace.class,
                    new RequestTrace("untracked"));

            return currentActor.requireActorId()
                    .flatMap(actorId -> {
                        Mono<Note> work = notes
                                .findByIdAndOwnerId(
                                        noteId,
                                        actorId)
                                .switchIfEmpty(Mono.error(
                                        new AccessDeniedException(
                                                "Note unavailable")))
                                .flatMap(note ->
                                        notes.save(
                                                note.withBody(nextBody)))
                                .flatMap(saved ->
                                        changes.save(
                                                new NoteChange(
                                                        null,
                                                        saved.id(),
                                                        actorId,
                                                        trace.correlationId(),
                                                        clock.instant()))
                                            .thenReturn(saved));

                        return tx.transactional(work);
                    });
        });
    }
}
~~~

Service cần được gọi qua bean/proxy để method security có hiệu lực. Không tự tạo service bằng `new` trong luồng production rồi kỳ vọng annotation được áp dụng.

Các quyết định trong ví dụ:

- Actor lấy từ security context, không từ trường `actorId` do client tự gửi.
- Query giới hạn ghi chú theo actor, ngoài việc kiểm tra authority.
- Trường hợp không thấy hoặc không sở hữu dùng chung thông báo `Note unavailable`.
- Trace có fallback cho theo dõi; actor bắt buộc phải có.
- Đọc, lưu ghi chú và lưu lịch sử nằm trong publisher được operator bao quanh.
- Lưu lịch sử thất bại phải làm workflow lỗi để transaction có thể rollback.

`NoteChange` là lịch sử do ví dụ chủ động lưu. Nó không được tự sinh bởi Commons auditing hay chỉ vì có RequestTrace.

## 9. Phạm vi TransactionalOperator và @Transactional

### 9.1. Operator bao quanh publisher nào?

Trong ví dụ, `work` gồm cả hai lần ghi trước khi truyền vào `tx.transactional(work)`. Đây là ranh giới cần quan sát.

Một kiểu đặt thiếu phạm vi:

~~~java
notes.save(note)
        .as(tx::transactional)
        .flatMap(saved ->
                changes.save(change)
                        .thenReturn(saved));
~~~

Không có transaction bên ngoài bổ sung, lần lưu lịch sử phía sau không được bao bởi cùng operator đó. Việc các lệnh nằm trong một chuỗi không đủ để kết luận chúng cùng transaction.

`TransactionalOperator` quản lý vòng đời theo subscription; cần tiêu thụ đến kết thúc phù hợp để hoàn tất transaction. Cancellation cũng ảnh hưởng kết quả transaction theo hạ tầng Spring.

Xem [Spring Framework: Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).

### 9.2. Dùng annotation là một phương án khác

Có thể thiết kế một service dùng:

~~~java
@Transactional(
        transactionManager = "noteTransactionManager")
public Mono<Note> changeBody(
        Long noteId,
        String nextBody) {
    // Trả lại publisher gồm toàn bộ công việc cần giao dịch.
}
~~~

Đây là hình dạng phương án thay thế, không phải implementation đầy đủ hay một annotation cần thêm vào ví dụ operator.

Nó cần hạ tầng annotation transaction được bật, đúng manager và lời gọi đi qua proxy. Self-invocation thông thường không tạo một lần interception mới.

Khi dùng `ReactiveTransactionManager`, công việc tham gia phải nằm trong cùng reactive pipeline phù hợp; không chọn manager imperative chỉ vì nó cũng có tên transaction manager.

Xem [Transactional API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Transactional.html) và [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

Một method `void` tự gọi `subscribe()` bên trong không mô tả cùng hợp đồng vòng đời với một method trả publisher cho caller.

## 10. Những ranh giới làm sai ngữ nghĩa

### 10.1. Subscription bị tách

~~~java
notes.save(note).subscribe();
return changes.save(change).then();
~~~

Lần lưu ghi chú có subscription riêng, không được ghép với publisher được trả về. Không giả định nó tự nhận security context, transaction hoặc lỗi của caller.

Hãy ghép bằng `flatMap`, `then` hoặc operator phù hợp và trả lại toàn bộ workflow.

### 10.2. Nuốt lỗi ở trong transaction

~~~java
work.onErrorResume(error -> Mono.empty())
        .as(tx::transactional);
~~~

Operator có thể nhìn thấy hoàn tất bình thường thay vì lỗi ứng dụng ban đầu. Tùy lỗi và trạng thái database, một phần công việc trước đó có thể được commit hoặc transaction đã bị đánh dấu không thể commit.

Đừng dùng fallback như cách mặc định để “giữ transaction chạy tiếp”. Nếu cần trả một phản hồi thay thế sau rollback, đặt việc ánh xạ lỗi ở ranh giới phù hợp sau publisher transaction và giữ rõ chính sách.

### 10.3. Hủy, timeout và tiêu thụ một phần

Các operator như `take`, `next` hoặc `timeout` có thể phát cancellation tới upstream. Với reactive transaction của Spring hiện đại, cancellation là một nguyên nhân rollback.

Nếu một `Flux` giao dịch chỉ được đọc một phần rồi caller hủy, không kết luận các phần tử đã nhìn thấy tương đương transaction đã commit.

Chọn ranh giới transaction theo đơn vị công việc; tránh kéo một transaction database dài chỉ để streaming dữ liệu qua một client chậm.

### 10.4. Song song trên tài nguyên có giới hạn

`Mono.zip` hoặc `flatMap` có concurrency không bổ sung transaction. Chúng cũng có thể tạo nhiều tác vụ đồng thời trên cùng connection hoặc session mà driver không hỗ trợ theo cách đó.

Ví dụ sửa ghi chú dùng các bước nối tiếp. Nếu muốn song song hóa, cần xét khả năng của tài nguyên và mục tiêu nhất quán trước.

### 10.5. Cache hoặc tái sử dụng dữ liệu theo người dùng

Cache kết quả của một publisher dùng chung có thể phát lại dữ liệu đã lấy dưới danh tính subscriber trước. Context theo subscriber không tự biến một cache kết quả dùng chung thành cache cách ly theo người dùng.

Phạm vi cache, khóa và quyền truy cập dữ liệu cần được thiết kế tường minh.

## 11. Đặt trace ở biên của workflow

Ở một thành phần đã có trace hợp lệ cho request, có thể bao quanh lời gọi service:

~~~java
return noteService.changeBody(noteId, nextBody)
        .contextWrite(context ->
                context.put(
                        RequestTrace.class,
                        trace));
~~~

Không cần truyền correlation id vào mọi chữ ký repository chỉ để hỗ trợ theo dõi. Nhưng nếu cần lưu nó thành dữ liệu, như dòng lịch sử trong ví dụ, phải có mã chủ động đưa giá trị vào entity được ghi.

Trong job nền, không có HTTP request hoặc security context mặc định. Job cần được cấp danh tính hệ thống theo cơ chế đã thiết kế, thay vì tự động dùng một actor bất kỳ khi thiếu danh tính.

Nếu workflow đi sang HTTP, message broker, `CompletableFuture` hoặc thư viện reactive khác, không mặc định Reactor Context tự truyền qua mọi ranh giới. Cần một cầu nối có hợp đồng rõ cho dữ liệu được phép chuyển tiếp.

Không log toàn bộ Context để chẩn đoán. Chọn các trường theo dõi cần thiết; security context có thể chứa thông tin không phù hợp để ghi vào log.

## 12. Kiểm tra từng tầng trước khi kết luận workflow đúng

### 12.1. Cùng publisher, hai Context khác nhau

Với `readTrace` ở mục 3, dùng `reactor-test`:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(
        readTrace.contextWrite(context ->
                context.put(
                        RequestTrace.class,
                        new RequestTrace("trace-a"))))
        .expectNext("trace-a")
        .verifyComplete();

StepVerifier.create(
        readTrace.contextWrite(context ->
                context.put(
                        RequestTrace.class,
                        new RequestTrace("trace-b"))))
        .expectNext("trace-b")
        .verifyComplete();

StepVerifier.create(readTrace)
        .verifyComplete();
~~~

Các phép kiểm tra xác minh dữ liệu được đọc theo subscription, không phải được chụp một lần cho mọi caller.

### 12.2. Kiểm tra đọc actor bằng security context giả lập

~~~java
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "user-a",
                "unused",
                List.of(new SimpleGrantedAuthority(
                        "note:write")));

CurrentActor currentActor = new CurrentActor();

StepVerifier.create(
        currentActor.requireActorId()
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authentication)))
        .expectNext("user-a")
        .verifyComplete();
~~~

Token ở đây phục vụ kiểm tra cách đọc Context. Nó không kiểm tra xác thực mật khẩu, JWT hoặc filter chain thật.

Cũng cần kiểm tra thiếu security context, anonymous và actor không có quyền phù hợp. Kiểm tra riêng `CurrentActor` chưa chứng minh annotation trên service được proxy thực thi.

### 12.3. Kiểm tra transaction với database thật

| Trường hợp | Kết quả cần xác minh sau khi workflow kết thúc |
| --- | --- |
| Actor có authority và sở hữu ghi chú | Nội dung mới và một dòng lịch sử được lưu |
| Actor không sở hữu | Không thay đổi ghi chú hoặc lịch sử |
| Thiếu authority | Method security từ chối theo cấu hình |
| Lưu lịch sử phát sinh lỗi | Nội dung ghi chú không giữ thay đổi của transaction lỗi |
| Hai request sửa cùng version | Chính sách optimistic locking hoạt động theo store |
| Hai subscriber khác actor và trace | Không dùng lẫn danh tính hoặc correlation id |
| Caller hủy workflow đang giao dịch | Quan sát rollback và hoàn tất dọn tài nguyên |
| Repository dùng sai tài nguyên so với manager | Cấu hình được phát hiện, không giả định vẫn cùng transaction |

Để kiểm tra rollback, đọc lại bằng một thao tác truy cập mới sau khi quá trình rollback đã hoàn tất. Chỉ nhìn entity trong bộ nhớ hoặc một tín hiệu `onNext` bên trong workflow chưa chứng minh commit.

Mock repository không chứng minh connection hoặc session thật đã được enlist vào transaction. Test Context và test quyền cần đi cùng test tích hợp tài nguyên ở mức phù hợp.

## 13. Chẩn đoán theo dấu hiệu

| Dấu hiệu | Điểm cần kiểm tra |
| --- | --- |
| Có dữ liệu trong Context nhưng query vẫn đọc sai người | Query có điều kiện chủ sở hữu/tenant và nguồn dữ liệu có đáng tin không |
| Không đọc được authentication | Reactive security context, filter chain, vị trí subscription |
| Thiếu trace sau một operator | Phạm vi contextWrite hoặc Context bị thay toàn bộ |
| Đổi scheduler rồi nghĩ security context bị mất | Kiểm tra subscription và cầu nối trước khi kết luận do thread |
| Một lần ghi rollback, lần khác vẫn tồn tại | Operator có bao cả hai, cùng factory và cùng đường truy cập không |
| `@Transactional` không có tác dụng mong đợi | Bean/proxy, manager, kiểu trả về và hạ tầng transaction |
| Service trả thành công trước khi lưu xong | Có tự subscribe và trả một publisher khác không |
| Thiếu quyền nhưng vẫn sửa được | Method security đã bật, lời gọi có đi qua proxy không |
| Request sau nhận dữ liệu người trước | Cache kết quả dùng chung hoặc field mutable giữ ngữ cảnh |
| Phản hồi HTTP đã gửi nhưng database lỗi | Tác động ngoài store và thời điểm commit không nằm trong cùng bảo đảm |

Các giá trị correlation id và actor id giúp lần theo thao tác. Chúng không thay thế bằng chứng về điều kiện query, tài nguyên transaction và kết quả cuối cùng.

## 14. Bài thực hành

Hoàn thiện luồng sửa ghi chú trên một store reactive đã chọn:

1. Định nghĩa trace bất biến và thống nhất khóa Context.
2. Lấy actor qua hạ tầng security reactive của ứng dụng.
3. Áp dụng cả quyền thao tác và giới hạn dữ liệu theo chủ sở hữu hoặc tenant.
4. Cấu hình đúng transaction manager của store.
5. Ghép thay đổi nghiệp vụ với một bản ghi lịch sử trong cùng transaction phù hợp.
6. Kiểm tra lỗi ở lần ghi thứ hai làm rollback lần ghi thứ nhất.
7. Kiểm tra hai subscriber có actor và trace khác nhau.
8. Giải thích ranh giới khi workflow gọi thêm một hệ thống khác.

Bài thực hành đạt yêu cầu khi bạn xác định được **ai thiết lập Context**, **ai xác thực và phân quyền**, **điều kiện nào giới hạn dữ liệu**, **manager nào quản lý tài nguyên** và **các thao tác nào thật sự commit hoặc rollback cùng nhau**.
