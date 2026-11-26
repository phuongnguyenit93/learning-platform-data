# Callback, auditing hoặc sự kiện không chạy ở thao tác đang dùng

## Mục tiêu và phạm vi

Một thao tác dữ liệu thành công không có nghĩa mọi callback, trường auditing và listener sự kiện đều phải chạy. Các cơ chế này được kích hoạt ở những điểm khác nhau và không bao phủ mọi đường ghi.

Ví dụ:

- Cập nhật trực tiếp bằng một query không nhất thiết đi qua vòng đời của từng entity.
- Tạo một reactive publisher chưa có nghĩa thao tác đã được thực thi.
- JPA dirty checking có thể ghi thay đổi mà không đi qua một lời gọi repository save.
- Domain event được publish không đồng nghĩa transaction đã commit.
- Listener AFTER_COMMIT không chạy nếu transaction kiểm thử bị rollback.

Trong phạm vi Spring Data Commons, bài học giúp bạn nhận diện cơ chế đang kỳ vọng, xác định đường thực thi thực tế và sửa đúng nơi thiếu liên kết.

Các ví dụ JPA và MongoDB minh họa những tích hợp riêng. Không áp dụng tên callback hoặc hành vi của một module cho mọi store.

## 1. Phân biệt các cơ chế trước khi chẩn đoán

| Cơ chế | Điểm tích hợp chính | Ví dụ |
|---|---|---|
| Callback của entity theo store | Pipeline mapping/lưu dữ liệu do module cung cấp | BeforeConvertCallback trong MongoDB |
| JPA entity listener | Vòng đời entity của JPA provider | PrePersist, PreUpdate |
| Auditing | Hạ tầng gán metadata theo tích hợp store | CreatedDate, LastModifiedBy |
| Mapping event | Sự kiện vòng đời do module phát theo đường thao tác hỗ trợ | BeforeConvertEvent của MongoDB |
| Domain event của aggregate | Sự kiện nghiệp vụ được aggregate cung cấp qua cơ chế repository hỗ trợ | DomainEvents |
| Application event listener | Nhận event từ Spring ApplicationEventPublisher | EventListener |
| Transactional event listener | Nhận và xử lý event theo phase giao dịch | TransactionalEventListener |

Một method tên `onBeforeSave` tự viết không tự trở thành callback. Nó cần implement đúng interface hoặc được đăng ký theo cơ chế mà module thực sự gọi.

Tương tự, một field có tên `createdAt` chưa tự có auditing, và một class event chưa tự được publish chỉ vì có listener nhận nó.

## 2. Bốn câu hỏi xác định đường đi thực tế

Trước khi thêm annotation, hãy trả lời:

1. **Ai gọi thao tác?** Repository proxy của Spring, template được cấu hình, EntityManager hay driver trực tiếp?
2. **Thao tác gì?** Save entity, cập nhật trực tiếp theo điều kiện, bulk update, xóa theo ID hay dirty checking?
3. **Đang kỳ vọng cơ chế nào?** EntityCallback, JPA listener, auditing hay domain event?
4. **Đang quan sát vào lúc nào?** Trước subscription, sau save, sau flush hay sau commit?

Một đường ghi khái niệm có thể là:

```text
Repository proxy
    |
Hạ tầng của module store
    |
Mapping / callback / auditing theo thao tác hỗ trợ
    |
Driver hoặc provider
    |
Flush / hoàn tất thao tác / commit theo mô hình giao dịch
```

Domain event của aggregate và application listener có đường kích hoạt riêng. Không đặt mọi cơ chế vào một chuỗi “save xong thì tất cả đều chạy”.

## 3. Ma trận thao tác: điều gì không được tự giả định?

| Thao tác | Điều cần kiểm tra |
|---|---|
| Repository save(entity) | Module có callback nào, auditing đã bật chưa, aggregate có event nào? |
| Template save(entity) | Callback/mapping event của template được cấu hình thế nào; không tự đồng nhất với domain event qua repository |
| JPA sửa entity đang managed rồi flush | JPA lifecycle có thể chạy; không tự có lời gọi repository publish domain event |
| Query update trực tiếp | Có materialize từng entity không, có bypass listener hoặc auditing per-entity không? |
| Driver/SQL trực tiếp | Đường ghi có đi qua hạ tầng Spring Data đang kỳ vọng không? |
| deleteById(id) | Có aggregate instance để đọc domain event không? |
| Reactive save trả publisher | Đã có subscription thực sự và có quan sát lỗi không? |
| Listener AFTER_COMMIT | Event có được publish trong transaction phù hợp và transaction có commit không? |

Bảng này dùng để đặt câu hỏi. Hành vi chi tiết của callback, bulk operation và mapping event phải theo module cùng thao tác cụ thể.

Không kết luận rằng “mọi thao tác qua template đều bỏ qua callback” hoặc “mọi method repository đều publish cùng loại event”. Cả hai suy luận đều quá rộng.

## 4. Callback theo store phải được đăng ký đúng hạ tầng

Ví dụ MongoDB có BeforeConvertCallback. Một callback chuẩn hóa email cho document bất biến có thể là:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public record CustomerDocument(
        @Id String id,
        String email,
        String normalizedEmail) {
}
```

```java
import java.util.Locale;

import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class NormalizeCustomerEmail
        implements BeforeConvertCallback<CustomerDocument> {

    @Override
    public CustomerDocument onBeforeConvert(
            CustomerDocument entity,
            String collection) {

        String normalized = entity.email() == null
                ? null
                : entity.email().strip()
                        .toLowerCase(Locale.ROOT);

        return new CustomerDocument(
                entity.id(),
                entity.email(),
                normalized);
    }
}
```

Ví dụ giả định ứng dụng có hạ tầng MongoDB và việc đăng ký callback bean đã nối với template thực hiện thao tác.

Những điểm cần kiểm tra khi callback không chạy:

- Bean có thuộc component scan không?
- Callback có generic type phù hợp với object thực tế không?
- Repository đang dùng template nào?
- Template đó có nhận hệ thống EntityCallbacks phù hợp không?
- Test có dùng context thật hay chỉ mock repository?
- Thao tác có đi qua giai đoạn convert entity hay chỉ gửi lệnh update trực tiếp?

Một template được tự tạo bằng constructor trong mã tùy biến không mặc nhiên có mọi thành phần mà một bean template được hạ tầng cấu hình đầy đủ đang có.

### Entity bất biến cần dùng kết quả callback

Callback trên trả một object mới. Pipeline hỗ trợ callback phải tiếp tục bằng object đó.

Ở mã ứng dụng cũng nên sử dụng instance mà thao tác save trả về khi còn cần kết quả lưu. Không chỉ kiểm tra object đầu vào rồi kết luận callback chưa chạy vì object bất biến không bị sửa tại chỗ.

Không gọi callback thủ công ở nhiều service như cách vá mặc định. Cách đó dễ làm chạy lặp hoặc bỏ sót các đường ghi khác; cần sửa liên kết pipeline trước.

## 5. Callback imperative và reactive là các hợp đồng khác nhau

Một callback imperative không tự được áp dụng như một reactive callback ở mọi đường ghi.

Ví dụ MongoDB có các interface reactive tương ứng như ReactiveBeforeConvertCallback. Khi dùng ReactiveMongoTemplate hoặc reactive repository, cần đăng ký đúng loại callback của pipeline đó.

Cũng cần phân biệt tạo công việc và thực thi:

```java
Mono<CustomerDocument> result =
        customers.save(document);
```

Ở thời điểm chỉ tạo publisher, ứng dụng chưa thể kết luận dữ liệu đã được lưu hoặc callback đã thực hiện.

Trong service reactive, giữ công việc trong pipeline mà framework hoặc bên gọi sẽ subscribe:

```java
public Mono<CustomerDocument> create(
        CustomerDocument document) {

    return customers.save(document)
            .doOnNext(saved ->
                    log.info("Saved customer {}", saved.id()));
}
```

Đoạn mã giả định repository reactive và logger đã được inject hoặc khai báo.

Không tự gọi subscribe trong service chỉ để ép callback chạy, rồi trả một publisher khác. Điều đó có thể tách công việc khỏi vòng đời request, cancellation và transaction mong muốn.

Nếu callback reactive trả một publisher chứa lỗi, phải quan sát lỗi khi subscribe. Không diễn giải lỗi bị bỏ qua là callback “không được gọi”.

Với metadata người dùng, reactive context và ThreadLocal của mô hình imperative cũng không tự tương đương. Một auditor đọc sai nguồn ngữ cảnh có thể không tìm được danh tính dù thao tác save đang chạy.

## 6. Auditing cần nhiều điều kiện cùng đúng

Một field auditing chỉ được điền khi tích hợp auditing thực sự tham gia đường ghi.

Các điều kiện thường cần kiểm tra:

- Annotation đúng trên property được mapping.
- Hạ tầng auditing của module được bật.
- Listener hoặc callback auditing được nối đúng.
- AuditorAware hoặc ReactiveAuditorAware phù hợp.
- DateTimeProvider và kiểu dữ liệu thời gian phù hợp.
- Entity được nhận diện là mới hay đã tồn tại theo cơ chế của store.
- Thao tác đang dùng có đi qua điểm gán auditing không?

Không mặc định thiếu CreatedBy đồng nghĩa toàn bộ auditing không chạy. Có thể phần thời gian được gán nhưng AuditorAware trả Optional.empty.

Ngược lại, object đã có createdAt từ constructor không chứng minh auditing đang hoạt động.

### Tạo mới và cập nhật không phải cùng trường hợp

CreatedDate và CreatedBy thể hiện thông tin tạo. LastModifiedDate và LastModifiedBy thể hiện thông tin sửa theo cấu hình.

Thông tin modified có thể được gán ngay khi tạo nếu cấu hình coi lần tạo cũng là một lần sửa. Không viết assertion rằng createdAt và modifiedAt luôn phải khác nhau.

Với ID do ứng dụng gán, version hoặc Persistable, cần kiểm tra cơ chế nhận diện trạng thái mới theo store. Không chỉ nhìn ID khác null rồi tự suy ra mọi module sẽ xử lý giống nhau.

## 7. Ví dụ auditing JPA được nối đầy đủ

Trong JPA, AuditingEntityListener tích hợp với vòng đời entity của JPA. Đây không phải BeforeConvertCallback của MongoDB.

Entity minh họa:

```java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@Table(name = "audited_customer")
@EntityListeners(AuditingEntityListener.class)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String modifiedBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant modifiedAt;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void rename(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getModifiedAt() {
        return modifiedAt;
    }
}
```

Cấu hình minh họa:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "currentAuditor",
        dateTimeProviderRef = "auditTimeProvider")
public class JpaAuditConfiguration {

    @Bean
    public AuditorAware<String> currentAuditor() {
        return () -> Optional.of("system");
    }

    @Bean
    public Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    public DateTimeProvider auditTimeProvider(
            Clock auditClock) {

        return () -> Optional.of(Instant.now(auditClock));
    }
}
```

Auditor cố định system chỉ để ví dụ tự giải thích được. Ứng dụng thật cần chính sách lấy người dùng hoặc danh tính tác vụ hệ thống phù hợp; không âm thầm gán system cho mọi trường hợp thiếu ngữ cảnh.

Ví dụ còn giả định ứng dụng đã có hạ tầng JPA, các thành phần auditing cần thiết trên classpath, entity scan và schema tương ứng.

Nếu dùng MongoDB hoặc R2DBC, phải bật auditing và sử dụng điểm tích hợp tương ứng của module. Không sao chép EnableJpaAuditing sang một pipeline không dùng JPA.

## 8. Save, flush và bulk update trong JPA

### Entity lifecycle không đồng nhất với lời gọi save

Một entity đang được JPA quản lý có thể được cập nhật bằng dirty checking:

```java
@Transactional
public void rename(Long id, String name) {
    Customer customer = customers.findById(id)
            .orElseThrow();

    customer.rename(name);
}
```

Khi provider flush thay đổi, callback cập nhật của JPA có thể được thực hiện. Không bắt buộc phải có một câu lệnh repository save mới ở đúng chỗ đó để JPA ghi thay đổi.

Ngược lại, gọi save với một object không có thay đổi cần ghi không bảo đảm luôn có một SQL UPDATE và một lần PreUpdate giống nhau trong mọi tình huống.

Thời điểm callback JPA còn phụ thuộc persist, merge, dirty checking và flush. Hãy quan sát sau điểm thực thi thích hợp.

### Bulk update là một đường khác

Ví dụ query JPA trực tiếp:

```java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Modifying
@Query("""
        update Customer c
        set c.name = :name
        where c.id = :id
        """)
int renameDirectly(
        @Param("id") Long id,
        @Param("name") String name);
```

Đây là khai báo method trong một repository JPA phù hợp; lời gọi cần ranh giới giao dịch tương ứng.

Bulk update không đi qua cùng vòng đời cập nhật từng entity như sửa managed entity rồi flush. Vì vậy không mặc định AuditingEntityListener sẽ tự gán modifiedAt cho từng bản ghi ở đường này.

Nếu chọn đường cập nhật trực tiếp, ứng dụng cần quyết định:

- Gán các trường audit cần thiết trong chính câu lệnh.
- Lấy auditor và thời gian theo chính sách nào.
- Có chấp nhận bỏ qua callback per-entity hay không.
- Đồng bộ hoặc làm mới persistence context như thế nào.

Chỉ thêm Modifying không làm auditing tự hoạt động. Annotation này phục vụ cách thực thi query ghi của JPA.

Nếu database có trigger, trigger có thể chạy theo quy tắc database. Đó là cơ chế khác với Spring Data auditing và phải được phân biệt khi quan sát kết quả.

## 9. Update trực tiếp trong document store cũng cần xét riêng

Ví dụ một lệnh update theo điều kiện có thể chỉ mang:

```text
Điều kiện:
    _id = customerId

Thay đổi:
    set name = newName
```

Nếu thao tác không tạo và convert một CustomerDocument đầy đủ, không được mặc định callback BeforeConvertCallback<CustomerDocument> sẽ chạy như khi save document.

Tương tự, đường bulk, update theo query hoặc driver trực tiếp có thể có khả năng callback/auditing khác nhau theo module và phiên bản.

Cách chẩn đoán:

1. Ghi rõ method template hoặc driver thực tế được gọi.
2. Xác định object nào đi vào pipeline.
3. Xem thao tác có materialize entity không.
4. Xác định các callback mà thao tác đó hỗ trợ.
5. Kiểm tra metadata audit được gán ở đâu.

Nếu normalizedEmail là invariant bắt buộc, việc chỉ đặt nó trong callback save không đủ khi ứng dụng còn cho phép update email bằng một đường bypass callback.

Có thể cần gom đường ghi, cập nhật các trường liên quan cùng một thao tác nguyên tử hoặc đặt quy tắc ở một tầng bảo đảm bao phủ được mọi đường cần thiết.

Không xử lý bằng cách thêm nhiều listener ngẫu nhiên cho tới khi một đường ghi tình cờ thay đổi đúng dữ liệu.

## 10. Domain event phải được aggregate cung cấp và được publish

Spring Data Commons có DomainEvents và AfterDomainEventPublication cho việc lấy các sự kiện mà aggregate đang giữ.

Ví dụ JPA minh họa một đơn hàng đã tồn tại:

```java
public record OrderConfirmed(Long orderId) {
}
```

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Transient;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @Transient
    private final List<Object> pendingEvents =
            new ArrayList<>();

    protected PurchaseOrder() {
    }

    public void confirm() {
        status = "CONFIRMED";
        pendingEvents.add(new OrderConfirmed(id));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        pendingEvents.clear();
    }
}
```

Ví dụ giả định confirm được gọi trên aggregate đã có ID hợp lệ. Với aggregate mới, cần thiết kế event ID và aggregate ID theo thời điểm chúng thực sự sẵn có.

Điểm cần hiểu:

- DomainEvents không tự tạo sự kiện nghiệp vụ.
- Method confirm thêm event vào danh sách.
- Cơ chế repository hỗ trợ sẽ lấy event từ aggregate.
- AfterDomainEventPublication dùng để dọn các event sau khi được công bố theo cơ chế đó.
- Annotation dọn event không có nghĩa transaction đã commit.

Nếu pendingEvents rỗng, listener không có sự kiện để nhận dù cơ chế publish được cấu hình đúng.

## 11. Đường repository và dirty checking không giống nhau đối với domain event

Với repository hỗ trợ publication từ aggregate:

```java
@Transactional
public void confirm(Long orderId) {
    PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

    order.confirm();

    orders.save(order);
}
```

Đoạn mã giả định orders là repository thực được tạo bởi hạ tầng phù hợp, không phải mock hoặc implementation tự viết bỏ qua cơ chế publication.

Trong JPA, lời gọi save có thể không cần thiết riêng cho dirty checking của một entity đang managed. Nhưng nó có ý nghĩa khác khi ứng dụng dựa vào repository invocation để công bố domain event.

Nếu bỏ save và chỉ chờ flush, trạng thái entity có thể được lưu nhưng không có lời gọi repository tương ứng để đọc DomainEvents từ aggregate.

Tương tự:

- Template save không tự đồng nghĩa publication DomainEvents qua repository proxy.
- Native update không cung cấp aggregate instance chứa pendingEvents.
- Driver trực tiếp không tự tham gia cơ chế này.
- deleteById chỉ nhận ID không có cùng dữ liệu aggregate như delete(entity).

Trong cơ chế domain event của repository, không trông chờ deleteById tự tải aggregate rồi đọc các event của nó. Nếu nghiệp vụ cần một sự kiện xóa, hãy chọn luồng nghiệp vụ có aggregate hoặc cơ chế ghi nhận phù hợp.

Các biến thể saveAll và delete cần được kiểm tra theo method cùng module cụ thể. Không suy rộng rằng mọi bulk method có tên save hoặc delete đều có cùng hành vi.

### Việc dọn event không phải một hàng đợi bền vững

pendingEvents trong bộ nhớ và AfterDomainEventPublication không tạo ra một message queue bền vững.

Nếu cần gửi thông tin sang hệ thống khác sau commit với khả năng khôi phục khi tiến trình dừng, cần thiết kế cơ chế như outbox và consumer chịu được lặp.

Một event được publish trong tiến trình không tự cung cấp bảo đảm giao nhận đúng một lần tới hệ thống ngoài.

## 12. EventListener và TransactionalEventListener quan sát thời điểm khác nhau

Listener thông thường:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @EventListener
    public void on(OrderConfirmed event) {
        // Xử lý theo cơ chế application event của ứng dụng.
    }
}
```

Application event trong cấu hình thông thường có thể được xử lý đồng bộ, nhưng ứng dụng có thể cấu hình multicaster hoặc listener bất đồng bộ. Không mặc định mọi listener chạy cùng thread và cùng ngữ cảnh.

Listener theo commit:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommittedOrderListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = false)
    public void on(OrderConfirmed event) {
        // Phản ứng khi giao dịch phù hợp đã commit.
    }
}
```

Điều kiện cần kiểm tra:

- Event đã được publish chưa?
- Listener có là bean không?
- Event type có khớp không?
- Event được publish trong transaction phù hợp không?
- Transaction có đi tới phase yêu cầu không?

Với fallbackExecution bằng false, không có transaction phù hợp có thể khiến listener không được thực hiện. Đó là hành vi theo hợp đồng, không nhất thiết là đăng ký bean bị lỗi.

Nếu transaction rollback, listener AFTER_COMMIT không được kỳ vọng chạy như một transaction đã thành công.

### Sau commit không có nghĩa mọi ghi tiếp theo tự được commit

Không mặc định phần ghi dữ liệu mới trong listener AFTER_COMMIT tự thuộc một giao dịch mới có hiệu lực. Nếu listener cần ghi, phải thiết kế ranh giới giao dịch tương ứng, hoặc chuyển việc sang một quy trình có lưu trạng thái rõ ràng.

Tương tự, callback sau commit trong bộ nhớ không thay thế cơ chế chuyển phát bền vững khi tiến trình có thể dừng.

## 13. Transaction của kiểm thử có thể làm listener không chạy

Một integration test thường có transaction bao ngoài và được rollback khi kết thúc.

Khi đó:

```text
Test bắt đầu transaction
    |
Service publish OrderConfirmed
    |
Listener AFTER_COMMIT chờ commit
    |
Test kết thúc bằng rollback
    |
Không có AFTER_COMMIT cho một commit thành công
```

Nếu assertion đòi listener AFTER_COMMIT đã chạy ngay sau save, test đang kiểm tra sai thời điểm.

Đối với kiểm thử commit thật, cần điều khiển ranh giới transaction theo cơ chế của môi trường test, chẳng hạn dùng TestTransaction khi phù hợp hoặc gọi service ngoài một transaction test bao ngoài.

Điều đó cũng làm thay đổi cleanup: dữ liệu đã commit không tự được xóa bằng một rollback đã kết thúc trước đó.

Các test khác nhau nên kiểm tra:

| Test | Kỳ vọng |
|---|---|
| Event được đăng ký trên aggregate | pending event có nội dung đúng |
| Repository publication | Application listener nhận event theo cấu hình |
| Transaction commit | Listener AFTER_COMMIT được thực hiện |
| Transaction rollback | Listener AFTER_COMMIT không thực hiện |
| Không có transaction, fallback false | Không trông chờ listener chạy |
| Reactive operation chưa subscribe | Không kết luận thao tác lưu và callback đã hoàn tất |

Với listener bất đồng bộ, dùng cơ chế chờ theo điều kiện có thời hạn. Không dùng một khoảng ngủ cố định rồi coi mọi lần chậm là listener không chạy.

## 14. Kiểm tra auditing bằng dữ liệu lưu thực, không chỉ object đầu vào

Ví dụ repository:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Test minh họa:

```java
import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("repository-test")
@Transactional
class CustomerAuditingTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    EntityManager entityManager;

    @Test
    void auditMetadataIsPersistedOnCreation() {
        Customer saved = customers.save(
                new Customer("Example"));

        entityManager.flush();
        Long id = saved.getId();
        entityManager.clear();

        Customer loaded = customers.findById(id)
                .orElseThrow();

        assertThat(loaded.getCreatedAt()).isNotNull();
        assertThat(loaded.getCreatedBy()).isEqualTo("system");
    }
}
```

Test giả định:

- Profile repository-test trỏ tới database kiểm thử riêng.
- JpaAuditConfiguration được tải vào context.
- Entity và repository scan đúng.
- Auditor minh họa trả system như cấu hình đã trình bày.

Flush rồi clear giúp kiểm tra dữ liệu được đọc lại, thay vì chỉ xem một object đang được quản lý.

Để kiểm tra modifiedAt thay đổi chính xác, nên dùng nguồn thời gian điều khiển được. Không dựa vào sleep hoặc giả định hai lời gọi rất gần nhau luôn có timestamp khác nhau sau khi lưu xuống database.

Cũng cần có test cho đường update trực tiếp nếu ứng dụng sử dụng đường đó. Một test save thành công không chứng minh auditing bao phủ mọi thao tác.

## 15. Đăng ký bean, generic type và thứ tự xử lý

Nếu đường thao tác phù hợp nhưng callback vẫn không chạy, kiểm tra phần đăng ký:

- Callback hoặc listener có được tạo thành bean trong context đang dùng không?
- Có nằm ngoài phạm vi scan hoặc chỉ được khai báo trong profile khác không?
- Generic type có khớp domain thực tế không?
- Có nhiều template hoặc nhiều application context không?
- Có object do mã ứng dụng tự new mà không nhận hạ tầng mong muốn không?
- Test có thay bean thật bằng mock không?

Đối với các EntityCallback có hỗ trợ ordering, hãy cấu hình thứ tự theo cơ chế của module. Không mặc định mọi callback đều chạy theo thứ tự khai báo file.

JPA entity listener, mapping event và EntityCallback không phải một danh sách duy nhất được sắp bởi cùng một annotation Order.

Nếu một bước tạo object mới nhưng bước sau vẫn dùng object cũ, cần xem cách pipeline truyền kết quả. Nếu nhiều callback cùng sửa một field, cần xác định ai có quyền quyết định giá trị cuối.

Không dùng việc tăng số listener để giải quyết một hợp đồng thứ tự chưa rõ.

## 16. Quan sát để biết “không chạy” nghĩa là gì

Một thông tin quan sát hữu ích nên cho biết:

- Loại thao tác đang thực hiện.
- Repository hoặc template liên quan.
- Domain type.
- Tên giai đoạn callback hoặc event.
- Event ID hoặc correlation ID khi có.
- Có transaction hay không theo cơ chế đang dùng.
- Kết quả hoàn tất hoặc lỗi ở pipeline.

Cần phân biệt ít nhất các tình huống:

```text
A. Callback không được đăng ký.
B. Callback được đăng ký nhưng thao tác không đi qua điểm đó.
C. Callback đã chạy nhưng trả một object mới.
D. Callback đã chạy nhưng auditor không có giá trị.
E. Callback hoặc listener đã chạy rồi phát sinh lỗi.
F. Event đã publish nhưng transaction chưa commit.
G. Reactive work chưa được subscribe.
H. Dữ liệu đã ghi nhưng đang đọc lại từ một nguồn cũ.
```

Một breakpoint không trúng hoặc một field chưa đổi tại thời điểm quan sát chưa đủ để phân biệt các trường hợp này.

Nếu có lỗi trong callback reactive hoặc listener, giữ lại chuỗi cause và tín hiệu lỗi. Không bắt mọi exception rồi trả thành công, vì điều đó biến lỗi thực thi thành một triệu chứng khó chẩn đoán hơn.

## 17. Các cách sửa sai thường gặp

| Cách làm | Vấn đề |
|---|---|
| Thêm CreatedDate nhưng không bật auditing | Chưa nối hạ tầng gán metadata |
| Dùng callback MongoDB cho JPA | Sai điểm tích hợp |
| Dùng callback imperative cho mọi pipeline reactive | Không bảo đảm được gọi theo hợp đồng reactive |
| Gọi subscribe thủ công trong service | Có thể tách vòng đời công việc và transaction |
| Kỳ vọng bulk update chạy listener từng entity | Không cùng đường thực thi với lưu entity |
| Kỳ vọng dirty checking publish DomainEvents | Có thể không có repository invocation đọc event |
| Kỳ vọng deleteById đọc event từ aggregate | Chỉ có ID, không có aggregate instance chứa event |
| Hiểu AfterDomainEventPublication là sau commit | Nhầm publication với transaction completion |
| Test AFTER_COMMIT trong transaction luôn rollback | Không có commit thành công để kích hoạt phase |
| Chỉ kiểm tra object đầu vào bất biến | Có thể bỏ qua instance mới do callback/save trả về |
| Dùng event trong bộ nhớ làm hàng đợi bền vững | Không có bảo đảm khôi phục sau khi tiến trình dừng |
| Gán system khi auditor rỗng mà không có chính sách | Có thể che việc mất ngữ cảnh người dùng |

Cách sửa cần khớp với nguyên nhân đã xác định: đăng ký đúng bean, dùng đúng pipeline, thay đổi đường ghi hoặc thiết kế lại hợp đồng event và giao dịch.

## 18. Quy trình chẩn đoán và bài thực hành

Có thể điều tra theo trình tự:

1. Ghi rõ thao tác thực tế và module store.
2. Chọn đúng cơ chế đang kỳ vọng.
3. Xác nhận hạ tầng và bean được đăng ký.
4. Xác nhận domain/generic type phù hợp.
5. Xác định thao tác có đi qua lifecycle đó không.
6. Với reactive, xác nhận subscription và kết quả hoàn tất.
7. Với JPA, xác định flush và trạng thái managed.
8. Với domain event, kiểm tra aggregate có event và repository có publication path.
9. Với transactional listener, kiểm tra phase và commit.
10. Đọc lại dữ liệu từ nguồn phù hợp sau ranh giới cần quan sát.

Bài thực hành:

- Tạo một entity JPA có auditing và kiểm tra lưu rồi đọc lại.
- So sánh sửa managed entity với query update trực tiếp.
- Tạo một callback MongoDB trong môi trường MongoDB riêng và so sánh save document với update theo query.
- Tạo aggregate có DomainEvents rồi so sánh repository save với chỉ dirty checking.
- Kiểm tra listener thường và listener AFTER_COMMIT trong các trường hợp commit, rollback và không có transaction.
- Với repository reactive, so sánh thời điểm tạo publisher với thời điểm pipeline được thực thi.

Mỗi thí nghiệm cần ghi lại điểm kích hoạt, dữ liệu quan sát và điều kiện mà cơ chế không được kỳ vọng chạy.

## 19. Những điều cần nắm vững

Callback, auditing và sự kiện thuộc những hợp đồng khác nhau. Chúng chỉ chạy khi bean, pipeline, thao tác và thời điểm vòng đời phù hợp cùng được đáp ứng.

Một lần ghi trực tiếp, một entity được dirty checking hoặc một reactive publisher chưa subscribe không thể được diễn giải giống một lời gọi save qua repository có đầy đủ hạ tầng.

Khi chẩn đoán, hãy lần theo đường thao tác và ranh giới giao dịch. Phân biệt đã đăng ký, đã gọi, đã hoàn tất, đã publish và đã commit giúp xác định đúng nguyên nhân thay vì thêm annotation một cách thử vận may.
