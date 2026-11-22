# Thêm validation, auditing và sự kiện xử lý dữ liệu trong Spring Data REST

## 1. Mục tiêu và cách phối hợp ba cơ chế

Spring Data REST xuất repository thành REST resource. Khi client tạo hoặc cập nhật entity, ứng dụng thường cần thực hiện ba nhóm công việc:

- **Validation:** kiểm tra dữ liệu và quy tắc nghiệp vụ trước khi repository lưu entity.
- **Auditing:** tự động ghi nhận ai tạo, ai sửa và thời điểm tạo/cập nhật.
- **Repository events:** thực hiện logic gắn với các bước trong vòng đời request như trước khi tạo, sau khi lưu hoặc sau khi xóa.

Ba cơ chế có mục đích khác nhau. Validation quyết định dữ liệu có được phép ghi hay không. Auditing ghi metadata do hệ thống quản lý. Event handler kết nối thao tác của exporter với logic ứng dụng. Không nên dùng event handler để thay thế toàn bộ validation hoặc tự gán audit field từ dữ liệu client.

Luồng điển hình:

1. Request được Spring Data REST chuyển thành entity.
2. Validator của sự kiện phù hợp kiểm tra dữ liệu trước khi ghi.
3. JPA lifecycle callback cập nhật audit metadata khi persist/update.
4. Repository hoàn thành thao tác lưu.
5. Spring Data REST phát event tương ứng, cho phép ứng dụng chạy logic hậu xử lý.
6. Nếu tác vụ bên ngoài chỉ được phép chạy sau transaction commit, chuyển tiếp application event tới listener dùng transaction phase AFTER_COMMIT.

## 2. Validation cho repository endpoint

### 2.1. Đăng ký Spring Validator theo tên bean

Spring Data REST có cơ chế đăng ký Validator theo tên bean. Tên bean bắt đầu bằng event cần xử lý, theo sau là tên domain type và hậu tố Validator.

Ví dụ:

- beforeCreateOrderValidator: kiểm tra Order trước khi tạo.
- beforeSaveOrderValidator: kiểm tra Order trước khi cập nhật.
- beforeCreatePersonValidator: kiểm tra Person trước khi tạo.

Ví dụ validator kiểm tra số đơn hàng và tổng tiền:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component("beforeCreateOrderValidator")
public class OrderBeforeCreateValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Order.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Order order = (Order) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "orderNumber", "order.number.required",
                "Order number is required"
        );

        if (order.getTotal() == null || order.getTotal().signum() <= 0) {
            errors.rejectValue(
                    "total", "order.total.positive",
                    "Order total must be greater than zero"
            );
        }
    }
}
~~~

Spring Data REST phát hiện bean có prefix beforeCreate và đăng ký nó với sự kiện tạo tương ứng. Validator cần là Spring bean; @Component với tên tường minh giúp tránh sai tên do quy tắc đặt bean mặc định.

Nếu cần kiểm tra cả lúc tạo và cập nhật, đăng ký validator riêng cho beforeSave hoặc tách logic kiểm tra dùng chung vào một service để hai validator gọi lại. Đừng giả định validator beforeCreate tự động chạy cho mọi thao tác cập nhật.

### 2.2. Dùng Jakarta Bean Validation

Với các constraint phổ biến như @NotBlank, @Size, @Email và @Positive, có thể dùng Jakarta Bean Validation. Trong Spring Boot, thêm dependency validation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đặt constraint trên entity hoặc DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public class OrderInput {

    @NotBlank
    @Size(max = 40)
    private String orderNumber;

    @Positive
    private BigDecimal total;

    // getters và setters
}
~~~

Spring Data REST có validating repository event listener riêng. Để các constraint Jakarta được chạy trong lifecycle của exporter, đăng ký một Spring Validator tương thích với Bean Validation bằng tên bean theo event. Ví dụ, LocalValidatorFactoryBean triển khai cả Jakarta Validator và Spring Validator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration(proxyBeanMethods = false)
public class OrderValidationConfiguration {

    @Bean("beforeCreateOrderValidator")
    LocalValidatorFactoryBean beforeCreateOrderValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean("beforeSaveOrderValidator")
    LocalValidatorFactoryBean beforeSaveOrderValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

Nếu chỉ cần validation tùy chỉnh cho một event, có thể dùng Spring Validator trực tiếp như ví dụ trước. Không nhầm việc có annotation @NotBlank trên field với việc mọi luồng lưu đều tự động gọi Bean Validation: phải xác nhận validator đã được tích hợp vào đúng request path. Spring MVC controller thông thường còn có cơ chế @Valid riêng; cơ chế đó không thay thế cấu hình validating repository event listener của Spring Data REST.

### 2.3. Đăng ký validator thủ công bằng RepositoryRestConfigurer

Nếu muốn kiểm soát đăng ký tại một điểm cấu hình, triển khai RepositoryRestConfigurer và thêm validator vào đúng event:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;

@Configuration
public class RepositoryRestValidationConfiguration
        implements RepositoryRestConfigurer {

    private final OrderBeforeCreateValidator orderValidator;

    public RepositoryRestValidationConfiguration(
            OrderBeforeCreateValidator orderValidator) {
        this.orderValidator = orderValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", orderValidator);
    }
}
~~~

Dùng một trong hai cách đăng ký: tên bean theo prefix hoặc đăng ký thủ công. Không đăng ký cùng validator hai lần nếu không có lý do rõ ràng, vì cùng một validation có thể chạy lặp lại.

### 2.4. Xử lý lỗi validation

Khi validator thêm lỗi vào Errors, Spring Data REST có thể từ chối thao tác ghi và trả lỗi validation cho client. Hãy kiểm tra HTTP status và response body thực tế theo phiên bản Spring Data REST đang sử dụng; không nên để client chỉ nhận một lỗi 500 chung cho dữ liệu đầu vào không hợp lệ.

Thông điệp lỗi nên:

- Chỉ ra field và quy tắc không hợp lệ.
- Dùng error code ổn định để client có thể xử lý.
- Không tiết lộ thông tin nội bộ, SQL hoặc stack trace.
- Giữ cùng quy ước giữa repository resource và custom controller.

## 3. Auditing với Spring Data JPA

Spring Data auditing có thể ghi nhận thời điểm và principal thực hiện thay đổi. Các annotation chính:

| Annotation | Ý nghĩa |
|---|---|
| @CreatedBy | Người tạo entity |
| @CreatedDate | Thời điểm tạo |
| @LastModifiedBy | Người sửa gần nhất |
| @LastModifiedDate | Thời điểm sửa gần nhất |

Nếu chỉ cần ngày giờ tạo và cập nhật, không bắt buộc phải triển khai AuditorAware. AuditorAware chỉ cần khi dùng @CreatedBy hoặc @LastModifiedBy để xác định người thực hiện.

### 3.1. Khai báo metadata trên entity

Ví dụ entity Order dùng JPA:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @CreatedBy
    @Column(updatable = false)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String createdBy;

    @CreatedDate
    @Column(updatable = false)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;

    @LastModifiedBy
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String lastModifiedBy;

    @LastModifiedDate
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant lastModifiedAt;

    protected Order() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

@EntityListeners(AuditingEntityListener.class) kết nối entity với callback auditing của Spring Data JPA. Có thể đăng ký listener cho từng entity bằng @EntityListeners hoặc cấu hình dùng chung qua orm.xml. Annotation-based metadata giúp entity ít phụ thuộc hơn so với việc phải triển khai interface Auditable.

Các field audit được đánh dấu READ_ONLY để Jackson không nhận giá trị ghi từ request. Đây là một lớp bảo vệ cho JSON binding; vẫn cần bảo vệ bằng thiết kế DTO, quyền truy cập và quy tắc cập nhật ở tầng ứng dụng. Không cho client tự quyết định createdBy hoặc createdAt.

### 3.2. Bật auditing

Khai báo @EnableJpaAuditing trong configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {
}
~~~

Khi dùng @CreatedBy hoặc @LastModifiedBy, cung cấp bean AuditorAware có kiểu trả về tương thích với kiểu field audit:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

@Configuration
public class AuditorConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.of("system");
            }

            return Optional.of(authentication.getName());
        };
    }
}
~~~

Ví dụ dùng username từ Spring Security. Nếu ứng dụng lưu User entity trong @CreatedBy, hãy trả về đúng kiểu User và tra cứu principal phù hợp. Với tác vụ nền, có thể trả về một system account rõ ràng thay vì null.

Nếu ứng dụng không dùng Spring Security, AuditorAware có thể lấy người thực hiện từ context riêng hoặc trả về system principal. Tránh lấy username từ request header do client tự gửi nếu header đó không được gateway xác thực.

### 3.3. Kiểm soát ngày giờ và kiểu dữ liệu

Auditing hỗ trợ các kiểu thời gian như Instant, các kiểu ngày giờ Java 8, long/Long và một số kiểu legacy. DateTimeProvider mặc định lấy thời gian hiện tại. Có thể cấu hình dateTimeProviderRef nếu cần clock riêng để test hoặc chuẩn hóa timezone.

Nên lưu timestamp theo Instant hoặc UTC và chuyển sang timezone hiển thị ở tầng API/UI. Nếu test cần thời gian xác định, cung cấp DateTimeProvider/Clock có thể kiểm soát được thay vì phụ thuộc vào đồng hồ hệ thống.

## 4. Xử lý repository lifecycle events

Spring Data REST exporter phát tám event trong quá trình làm việc với entity:

| Event | Thời điểm |
|---|---|
| BeforeCreateEvent | Trước khi tạo entity |
| AfterCreateEvent | Sau khi tạo entity |
| BeforeSaveEvent | Trước khi lưu entity |
| AfterSaveEvent | Sau khi lưu entity |
| BeforeLinkSaveEvent | Trước khi lưu association |
| AfterLinkSaveEvent | Sau khi lưu association |
| BeforeDeleteEvent | Trước khi xóa entity |
| AfterDeleteEvent | Sau khi xóa entity |

Có hai cách chính để nhận event:

- Kế thừa AbstractRepositoryEventListener và override callback tương ứng. Cách này nhận nhiều domain type, nên cần tự kiểm tra kiểu entity.
- Dùng @RepositoryEventHandler với các annotation như @HandleBeforeCreate hoặc @HandleAfterSave. Cách này cho phép khai báo method theo domain type và thường dễ đọc hơn.

### 4.1. Annotated repository event handler

Ví dụ chuẩn hóa dữ liệu trước khi tạo và phát application event sau khi lưu:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleAfterSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(Order.class)
public class OrderRepositoryEventHandler {

    private final ApplicationEventPublisher eventPublisher;

    public OrderRepositoryEventHandler(
            ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @HandleBeforeCreate
    public void beforeCreate(Order order) {
        // Chuẩn hóa dữ liệu cần thiết trước khi lưu.
    }

    @HandleAfterSave
    public void afterSave(Order order) {
        eventPublisher.publishEvent(new OrderChanged(order.getId()));
    }
}
~~~

Khai báo application event:

~~~java
public record OrderChanged(Long orderId) {
}
~~~

Spring Data REST tìm bean có @RepositoryEventHandler rồi đăng ký các method có annotation event tương ứng. Kiểu tham số đầu tiên của method xác định domain type. Bean phải được quản lý bởi Spring, ví dụ dùng @Component hoặc khai báo bằng @Bean.

Không đặt logic gửi email, gọi HTTP hoặc gửi broker trực tiếp trong callback nếu cần bảo đảm tác vụ chỉ chạy sau commit. AfterSaveEvent là mốc trong lifecycle của exporter; tên event không tự chứng minh transaction đã commit.

### 4.2. Chạy tác vụ sau commit

Nếu request đang chạy trong transaction, listener có thể đăng ký theo phase AFTER_COMMIT:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderChangedListener {

    private final OrderIndexService orderIndexService;

    public OrderChangedListener(OrderIndexService orderIndexService) {
        this.orderIndexService = orderIndexService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderChanged event) {
        orderIndexService.refresh(event.orderId());
    }
}
~~~

Listener chỉ được gọi sau khi transaction commit thành công. Nếu không có transaction đang hoạt động khi event được publish, listener mặc định không chạy. Hãy kiểm tra transaction boundary thực tế của endpoint Spring Data REST. Không bật fallbackExecution=true trừ khi việc xử lý cả khi không có transaction là chủ đích.

Nếu listener cần ghi database sau commit, gọi một service bean riêng dùng Propagation.REQUIRES_NEW. Nếu tác vụ phải được giao bền vững qua broker ngay cả khi process dừng sau commit, cân nhắc transactional outbox thay vì chỉ dùng event trong bộ nhớ.

## 5. Thứ tự thực thi và tránh ghi đè metadata

Khi tạo hoặc cập nhật entity qua Spring Data REST, cần để mỗi cơ chế chịu trách nhiệm đúng phần của nó:

- Validator kiểm tra dữ liệu client gửi và các quy tắc domain trước khi ghi.
- AuditingEntityListener cập nhật metadata tại JPA lifecycle callback.
- Repository event handler xử lý logic gắn với thao tác exporter.
- Transactional event listener chạy công việc phụ thuộc vào commit.

Không đặt audit timestamp hoặc username trong @HandleBeforeCreate / @HandleBeforeSave. Nếu làm vậy, logic audit có thể bị lặp, sai thời điểm hoặc bị ghi đè bởi JPA callback. Cũng không dựa vào một callback hậu lưu để kiểm tra dữ liệu vốn phải bị từ chối trước khi ghi.

Với quy tắc nghiệp vụ cần bảo đảm cho mọi đường ghi (REST, batch, message consumer, service nội bộ), đặt invariant quan trọng trong domain/service layer hoặc database constraint. Validator của Spring Data REST chỉ bảo vệ request đi qua exporter.

## 6. Kiểm thử validation, auditing và event

### 6.1. Kiểm thử validator

Có thể kiểm tra Spring Validator độc lập bằng BeanPropertyBindingResult:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;

import static org.assertj.core.api.Assertions.assertThat;

class OrderBeforeCreateValidatorTests {

    private final OrderBeforeCreateValidator validator =
            new OrderBeforeCreateValidator();

    @Test
    void rejectsMissingOrderNumber() {
        Order order = new Order();
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(order, "order");

        validator.validate(order, errors);

        assertThat(errors.hasFieldErrors("orderNumber")).isTrue();
    }
}
~~~

Kiểm thử unit giúp xác nhận quy tắc riêng lẻ. Ngoài ra, cần kiểm thử tích hợp để xác nhận Spring Data REST thực sự đăng ký validator theo tên bean và trả lỗi trên HTTP request.

### 6.2. Kiểm thử qua MockMvc

Ví dụ test endpoint repository resource /orders:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderRepositoryValidationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsOrderWithoutOrderNumber() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"orderNumber\":\"\",\"total\":0}"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Điều chỉnh path, JSON và status theo resource mapping và phiên bản Spring Data REST của dự án. Nếu API có base path, thêm base path vào URL. Kiểm tra response body để bảo đảm client nhận được field và mã lỗi có ý nghĩa. Quan trọng hơn, xác nhận entity không được lưu khi validation thất bại.

### 6.3. Kiểm thử auditing

Dùng repository test để lưu entity, flush và đọc lại từ persistence context mới:

~~~java
@DataJpaTest
@Import({JpaAuditingConfiguration.class, AuditorConfiguration.class})
class OrderAuditingTests {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void storesCreationAndModificationMetadata() {
        Order order = new Order();
        // Gán các field bắt buộc của entity.

        Order saved = orderRepository.saveAndFlush(order);

        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("system");
    }
}
~~~

Ví dụ giả định auditor trả về system khi không có principal đăng nhập. Nếu test dùng Spring Security principal, đặt SecurityContext trước khi save và xác nhận createdBy/lastModifiedBy khớp user. Có thể dùng Clock cố định để test timestamp chính xác.

### 6.4. Kiểm thử event handler

Kiểm tra cả hai phần: handler được đăng ký và method đúng được gọi khi thao tác repository đi qua Spring Data REST. Dùng Spring application event recorder hoặc một test listener để ghi nhận OrderChanged. Nếu listener dùng @TransactionalEventListener, kiểm thử cả commit và rollback; test transaction mặc định rollback khi kết thúc nên cần chủ động commit nếu muốn xác nhận AFTER_COMMIT.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Validator không chạy khi POST | Tên bean không có prefix beforeCreate hoặc suffix domain type sai | Kiểm tra bean name chính xác, component scan và event tạo |
| Validator chạy khi tạo nhưng không chạy khi cập nhật | Chỉ đăng ký beforeCreate | Đăng ký beforeSave riêng hoặc cấu hình nhiều event |
| @NotBlank không được thực thi qua repository endpoint | Chỉ thêm constraint nhưng chưa nối Bean Validation vào validating repository event listener | Đăng ký LocalValidatorFactoryBean hoặc Spring Validator bằng tên bean prefix |
| Validation chạy hai lần | Cùng validator được đăng ký theo bean name và thủ công | Chọn một cơ chế đăng ký |
| Entity có dữ liệu hợp lệ nhưng vẫn bị từ chối | supports() không nhận đúng domain type hoặc field path sai | Kiểm tra supports(), tên property và Errors |
| createdAt hoặc createdBy luôn null | Chưa bật @EnableJpaAuditing hoặc entity thiếu AuditingEntityListener | Kiểm tra configuration và entity listener registration |
| lastModifiedDate không đổi | Entity không được dirty/update hoặc field mapping sai | Kiểm tra transaction, dirty checking, flush và callback |
| createdBy không đúng người | AuditorAware đọc sai principal hoặc request không có SecurityContext | Kiểm tra authentication, anonymous handling và kiểu principal |
| Client ghi đè audit field | Field được deserialize từ JSON | Đánh dấu read-only, dùng DTO hoặc chặn cập nhật field hệ thống |
| Repository event handler không được gọi | Bean chưa được Spring quản lý hoặc annotation/domain type sai | Kiểm tra @Component, component scan và tham số đầu tiên của method |
| Tác vụ ngoài chạy dù database rollback | Gọi trực tiếp trong AfterSave handler hoặc dùng listener thông thường | Dùng @TransactionalEventListener(AFTER_COMMIT) |
| Listener AFTER_COMMIT không chạy | Event được publish ngoài transaction | Kiểm tra transaction boundary và nơi publish |
| Test audit không có timestamp | Test slice chưa import auditing config hoặc listener chưa đăng ký | Import config, kiểm tra @EntityListeners và flush entity |

## 8. Checklist triển khai

1. Chọn quy tắc validation ở mức DTO, entity hoặc service theo nơi cần bảo vệ.
2. Đăng ký Spring Validator cho đúng event bằng tên bean prefix hoặc RepositoryRestConfigurer.
3. Nếu dùng Jakarta Bean Validation, bảo đảm provider có mặt và LocalValidatorFactoryBean được nối vào event phù hợp.
4. Bật auditing bằng @EnableJpaAuditing và đăng ký AuditingEntityListener cho entity hoặc persistence unit.
5. Dùng AuditorAware khi cần ghi người tạo/người sửa; xác định rõ principal cho user, anonymous và tác vụ nền.
6. Không cho client cập nhật metadata auditing.
7. Dùng @RepositoryEventHandler cho logic lifecycle theo domain type; bảo đảm bean được Spring quản lý.
8. Dùng @TransactionalEventListener(AFTER_COMMIT) cho tác vụ chỉ được chạy sau commit.
9. Kiểm thử unit validator và tích hợp HTTP/repository cho validation, audit metadata và event.
10. Kiểm tra cả luồng lỗi, rollback, request không xác thực và các đường ghi ngoài Spring Data REST.

## Tài liệu chính thức

- [Spring Data REST – Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST – Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST – RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data JPA – Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data JPA – EnableJpaAuditing API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/config/EnableJpaAuditing.html)
- [Spring Data JPA – AuditingEntityListener API](https://docs.spring.io/spring-data/data-jpa/docs/current/api/org/springframework/data/jpa/domain/support/AuditingEntityListener.html)
- [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Framework – Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html)
