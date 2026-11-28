# Tái sử dụng cùng service cho CLI, batch hoặc REST khi ứng dụng cần

Một nghiệp vụ như đăng ký khách hàng, tạo đơn hàng hoặc đồng bộ dữ liệu có thể được gọi từ nhiều nơi. Người vận hành có thể chạy command trong Spring Shell, một lịch batch có thể xử lý hàng nghìn bản ghi, còn ứng dụng web có thể cung cấp REST API cho hệ thống khác.

Nếu mỗi giao diện tự viết lại quy tắc nghiệp vụ, kết quả dễ khác nhau: CLI kiểm tra trùng email nhưng REST bỏ sót, batch chuẩn hóa dữ liệu khác với command, hoặc mỗi nơi áp dụng một transaction boundary riêng. Cách tổ chức phù hợp là đặt use case trong một application service dùng chung, rồi để CLI, batch và REST đóng vai trò adapter chuyển input sang kiểu dữ liệu ứng dụng và chuyển kết quả thành định dạng của từng giao diện.

Bài này dùng Spring Shell 4.0.4 cho ví dụ command. Phần REST sử dụng Spring MVC; phần batch minh họa Spring Batch. Các adapter có thể cùng chạy trong một Spring `ApplicationContext`, hoặc được đóng gói thành các ứng dụng riêng nhưng vẫn gọi cùng application service/module.

## 1. Một nghiệp vụ, nhiều cách gọi

Giả sử ứng dụng cần đăng ký khách hàng. Cùng một use case có thể được kích hoạt từ ba nguồn:

- CLI: người vận hành gõ `customer register --name ... --email ...`.
- REST: một hệ thống khác gửi `POST /api/customers` với JSON.
- Batch: một job đọc file hoặc message rồi đăng ký từng khách hàng.

Luồng phụ thuộc nên hội tụ tại application service:

```text
                   +-------------------------+
                   | RegisterCustomerUseCase |
                   | validate business rules |
                   | apply transaction       |
                   | call repository         |
                   +------------+------------+
                                ^
             +------------------+------------------+
             |                  |                  |
       +-----+------+    +------+-------+   +------+-------+
       | Spring Shell|    | REST adapter |   | Batch adapter|
       | @Command    |    | @RestController| | Tasklet/Step  |
       +------------+    +--------------+   +--------------+
```

Mỗi adapter chịu trách nhiệm giao tiếp với transport của nó. Application service chịu trách nhiệm thực hiện use case và bảo vệ quy tắc nghiệp vụ. Repository hoặc gateway thực hiện truy cập database, file, queue hay dịch vụ bên ngoài.

## 2. Tách application service khỏi giao diện gọi

Service không nên nhận `CommandContext`, `HttpServletRequest`, `StepContribution` hoặc kiểu dữ liệu đặc thù của terminal/web/batch. Những kiểu này thuộc adapter. Service nên nhận một command object của ứng dụng và trả về kết quả có ý nghĩa nghiệp vụ.

Ví dụ cấu trúc package:

```text
com.example.customer
├── application
│   ├── RegisterCustomerUseCase.java
│   ├── RegisterCustomerCommand.java
│   ├── CustomerResult.java
│   └── CustomerRegistrationService.java
├── domain
│   ├── Customer.java
│   └── CustomerRepository.java
├── infrastructure
│   └── persistence
│       └── JpaCustomerRepository.java
└── adapter
    ├── cli
    │   └── CustomerCommands.java
    ├── web
    │   └── CustomerController.java
    └── batch
        └── CustomerImportTasklet.java
```

Đây là một cách tổ chức tham khảo. Dự án nhỏ có thể dùng ít package hơn, nhưng vẫn nên giữ ranh giới giữa command handler/controller/tasklet và logic nghiệp vụ.

## 3. Khai báo input và kết quả của use case

Tạo command object biểu diễn yêu cầu đăng ký khách hàng:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record RegisterCustomerCommand(
        @NotBlank String name,
        @NotBlank @Email String email) {
}
```

Kết quả use case không cần chứa định dạng dành riêng cho CLI hoặc HTTP:

```java
import java.util.UUID;

public record CustomerResult(
        UUID id,
        String name,
        String email) {
}
```

Tạo interface cho use case:

```java
public interface RegisterCustomerUseCase {

    CustomerResult register(RegisterCustomerCommand command);
}
```

Interface này giúp các adapter phụ thuộc vào hành vi cần dùng. Chúng không cần biết implementation lưu khách hàng bằng JPA, JDBC hay một dịch vụ từ xa.

## 4. Đặt quy tắc nghiệp vụ trong service dùng chung

Implementation là Spring bean. Nó nhận repository và `jakarta.validation.Validator` qua constructor injection. Service kiểm tra dữ liệu ở ranh giới use case để CLI, REST và batch đều đi qua cùng quy tắc.

```java
import java.util.Locale;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CustomerRegistrationService implements RegisterCustomerUseCase {

    private final CustomerRepository customers;
    private final Validator validator;

    CustomerRegistrationService(
            CustomerRepository customers,
            Validator validator) {
        this.customers = customers;
        this.validator = validator;
    }

    @Override
    @Transactional
    public CustomerResult register(RegisterCustomerCommand command) {
        Set<ConstraintViolation<RegisterCustomerCommand>> violations =
                validator.validate(command);
        if (!violations.isEmpty()) {
            throw new InvalidCustomerInputException(violations);
        }

        String normalizedEmail = command.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        if (customers.existsByEmail(normalizedEmail)) {
            throw new CustomerAlreadyExistsException();
        }

        Customer customer = Customer.create(
                command.name().trim(), normalizedEmail);
        Customer saved = customers.save(customer);

        return new CustomerResult(
                saved.id(), saved.name(), saved.email());
    }
}
```

`CustomerRepository`, `Customer` và các exception là kiểu của domain/infrastructure. Một hợp đồng tối thiểu có thể trông như sau:

```java
import java.util.UUID;

record Customer(UUID id, String name, String email) {

    static Customer create(String name, String email) {
        return new Customer(UUID.randomUUID(), name, email);
    }
}

interface CustomerRepository {

    boolean existsByEmail(String email);

    Customer save(Customer customer);
}
```

Các exception nghiệp vụ có thể được định nghĩa ngắn gọn:

```java
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;

class InvalidCustomerInputException extends RuntimeException {

    InvalidCustomerInputException(
            Set<? extends ConstraintViolation<?>> violations) {
        super(violations.stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .collect(Collectors.joining("; ")));
    }
}

class CustomerAlreadyExistsException extends RuntimeException {

    CustomerAlreadyExistsException() {
        super("Khách hàng với địa chỉ email này đã tồn tại.");
    }
}
```

Trong dự án thực tế, repository có thể là Spring Data interface và `Customer` có thể là JPA entity hoặc aggregate domain. Nếu dùng `Validator`, thêm implementation Bean Validation tương ứng, ví dụ dependency `spring-boot-starter-validation`.

Các exception như `InvalidCustomerInputException` và `CustomerAlreadyExistsException` là exception nghiệp vụ do ứng dụng định nghĩa; implementation repository có thể là Spring Data hoặc một adapter persistence khác.

Điểm quan trọng là mọi caller đều gọi `register(...)`. CLI không tự kiểm tra email trùng rồi bỏ qua service; REST không tự ghi repository; batch không có một bản sao khác của quy tắc đăng ký.

## 5. Transaction boundary ở use case

`@Transactional` thường đặt tại method application service đại diện cho một đơn vị nghiệp vụ cần nhất quán. Khi CLI, REST hoặc batch gọi method này thông qua Spring bean proxy, transaction interceptor có thể mở hoặc tham gia transaction theo cấu hình propagation.

Một số điểm cần nhớ:

- Cần có transaction manager và transaction management được cấu hình. Trong ứng dụng Spring Boot có dependency persistence phù hợp, auto-configuration thường cung cấp hạ tầng cần thiết.
- Với proxy mode mặc định, lời gọi từ bean khác đi qua proxy mới được áp dụng transaction advice.
- Một method trong cùng object gọi trực tiếp method `@Transactional` khác của chính object đó (self-invocation) không đi qua proxy, nên không tạo transaction mới chỉ nhờ annotation.
- Không giữ transaction database mở trong lúc chờ người dùng nhập lệnh, gọi API bên ngoài lâu hoặc xử lý file lớn nếu không cần thiết.
- Với batch theo chunk, transaction của chunk thường là boundary phù hợp; service có thể tham gia transaction đang hoạt động theo propagation đã chọn.

Nếu một nghiệp vụ cần ghi nhiều bảng, hãy giữ thao tác đó trong một use case có transaction rõ ràng. Adapter chỉ nên điều phối input/output, không tự mở nhiều transaction khác nhau cho cùng một nghiệp vụ.

## 6. Gọi service từ Spring Shell CLI

Spring Shell 4 đánh dấu method command bằng `@Command` trong package `org.springframework.shell.core.command.annotation`. Class chứa command phải là Spring-managed bean, ví dụ `@Component`. Trong ứng dụng Spring Boot, command scanning được auto-configuration hỗ trợ.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class CustomerCommands {

    private final RegisterCustomerUseCase registerCustomer;

    CustomerCommands(RegisterCustomerUseCase registerCustomer) {
        this.registerCustomer = registerCustomer;
    }

    @Command(
        name = "customer register",
        description = "Đăng ký khách hàng mới"
    )
    public String register(
            @Option(longName = "name", required = true) String name,
            @Option(longName = "email", required = true) String email) {

        CustomerResult result = registerCustomer.register(
                new RegisterCustomerCommand(name, email));

        return "Đã đăng ký khách hàng " + result.id()
                + " (" + result.email() + ").";
    }
}
```

Người vận hành gọi:

```text
customer register --name "Nguyen An" --email an@example.com
```

Các ví dụ command trong bài dùng annotation Spring Shell 4 (`@Command(name = ...)`, `@Option` trong `org.springframework.shell.core.command.annotation`). Nếu dự án còn ở Spring Shell 3.3.x, cú pháp command sử dụng annotation thuộc API 3.x như `@ShellComponent`/`@ShellMethod` hoặc `@Command(command = ...)`; không trộn package và thuộc tính của hai phiên bản trong cùng source.

Command handler chỉ chuyển option thành `RegisterCustomerCommand`, gọi use case và chuyển kết quả thành thông báo terminal. Không đưa `CommandContext` vào service và không truy cập repository trực tiếp trong command handler.

Nếu cần định dạng JSON hoặc CSV cho script, adapter CLI có thể cung cấp option `--format`; việc chuyển `CustomerResult` thành text/JSON vẫn nằm ở adapter, không làm thay đổi logic đăng ký.

## 7. Gọi cùng use case từ REST controller

REST adapter nhận HTTP request, kiểm tra cấu trúc payload và ánh xạ sang application command. Dùng request DTO riêng để public API có thể tiến hóa độc lập với model nội bộ.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

record RegisterCustomerRequest(
        @NotBlank String name,
        @NotBlank @Email String email) {
}

record CustomerResponse(String id, String name, String email) {
}

@RestController
@RequestMapping("/api/customers")
class CustomerController {

    private final RegisterCustomerUseCase registerCustomer;

    CustomerController(RegisterCustomerUseCase registerCustomer) {
        this.registerCustomer = registerCustomer;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public CustomerResponse register(
            @Valid @RequestBody RegisterCustomerRequest request) {

        CustomerResult result = registerCustomer.register(
                new RegisterCustomerCommand(request.name(), request.email()));

        return new CustomerResponse(
                result.id().toString(), result.name(), result.email());
    }
}
```

`@Valid` giúp Spring MVC kiểm tra request DTO trước khi gọi controller. Service vẫn giữ validation ở ranh giới use case để các caller không phải HTTP cũng được bảo vệ. Việc lặp kiểm tra định dạng ở HTTP boundary và use case là có chủ đích: boundary trả lỗi request sớm, còn application service bảo đảm quy tắc không bị bỏ qua bởi CLI hoặc batch.

## 8. Ánh xạ exception theo từng giao diện

Service nên ném exception có ý nghĩa nghiệp vụ như `CustomerAlreadyExistsException` hoặc `InvalidCustomerInputException`. Không ném `ResponseStatusException`, `CommandExecutionException` hay kiểu riêng của Spring Batch từ application service.

Mỗi adapter ánh xạ cùng exception theo giao thức riêng:

| Exception ứng dụng | CLI | REST | Batch |
|---|---|---|---|
| Input không hợp lệ | Hiển thị field/message cần sửa | HTTP 400 với validation details | Đánh dấu record lỗi hoặc skip theo policy |
| Khách hàng đã tồn tại | Thông báo đã có khách hàng | HTTP 409 Conflict | Ghi nhận duplicate; skip hoặc fail theo yêu cầu |
| Database tạm thời không khả dụng | Thông báo lỗi và mã tham chiếu | HTTP 503 hoặc lỗi phù hợp | Retry theo cấu hình step |
| Lỗi không mong đợi | Thông báo chung, log stack trace | HTTP 500, log correlation ID | Đánh dấu job/step failed |

Ví dụ REST adapter dùng `@RestControllerAdvice`:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class CustomerApiExceptionHandler {

    @ExceptionHandler(CustomerAlreadyExistsException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    ApiError customerExists(CustomerAlreadyExistsException exception) {
        return new ApiError("CUSTOMER_EXISTS", exception.getMessage());
    }

    @ExceptionHandler(InvalidCustomerInputException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    ApiError invalidInput(InvalidCustomerInputException exception) {
        return new ApiError("INVALID_CUSTOMER", exception.getMessage());
    }
}

record ApiError(String code, String message) {
}
```

Với Spring Shell 4, có thể dùng `ExitStatusExceptionMapper` để đổi exception thành thông báo và `ExitStatus` cho command. Batch adapter dùng retry/skip/fail policy của step. Cả ba cùng nhận exception nghiệp vụ từ service nhưng không dùng chung cách trình bày lỗi.

## 9. Gọi use case từ Spring Batch

Spring Batch có thể dùng cùng application service trong `Tasklet`, `ItemProcessor` hoặc `ItemWriter`. Với một tác vụ nhỏ, `Tasklet` có thể điều phối một lần import:

```java
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.core.step.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.infrastructure.repeat.RepeatStatus;
import org.springframework.stereotype.Component;

@Component
class CustomerImportTasklet implements Tasklet {

    private final CustomerImportService importer;

    CustomerImportTasklet(CustomerImportService importer) {
        this.importer = importer;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {
        importer.importPendingFile();
        return RepeatStatus.FINISHED;
    }
}
```

`CustomerImportService` đọc từng dòng, tạo `RegisterCustomerCommand` rồi gọi `RegisterCustomerUseCase.register(...)`. Nó không tự viết lại quy tắc kiểm tra email, chuẩn hóa dữ liệu hoặc tạo khách hàng.

Với file lớn, nên dùng chunk-oriented step thay vì đọc toàn bộ file vào bộ nhớ trong một tasklet. `ItemReader` đọc từng record, processor chuyển đổi/kiểm tra cấu trúc, và writer hoặc application service thực hiện use case theo chunk. Spring Batch quản lý transaction và checkpoint theo cấu hình step; thiết kế retry, skip và restart dựa trên đặc điểm của dữ liệu.

Trong chunk-oriented step, `ItemWriter` nhận một `Chunk` các item đã được đọc và xử lý. Writer có thể gọi application service cho từng item hoặc một use case theo lô. Writer chạy trong transaction của chunk; `@Transactional` trên use case thường tham gia transaction đang hoạt động với propagation mặc định `REQUIRED`. Cần xác nhận transaction manager và resource được cấu hình để cùng tham gia transaction. Nếu xử lý nhiều record, đừng mở một transaction bao trùm toàn bộ file nếu chunk commit/restart là yêu cầu của job.

## 10. Một bean dùng chung trong cùng ApplicationContext

Nếu CLI, REST và batch cùng được bật trong một ứng dụng Spring Boot, constructor injection sẽ đưa cùng bean `RegisterCustomerUseCase` vào các adapter. Với bean `@Service` mặc định là singleton, các adapter trong cùng application context cùng gọi một instance service/proxy.

Điều đó không có nghĩa mọi state trong ứng dụng được tự động chia sẻ an toàn. Service singleton nên giữ dependency bất biến và không lưu dữ liệu request hoặc biến tạm của từng người dùng trong field mutable. Mỗi lần gọi nên nhận dữ liệu qua method parameter và dùng biến cục bộ.

Ví dụ cấu trúc:

```text
ApplicationContext
  ├── CustomerCommands -----------+
  ├── CustomerController ---------+--> RegisterCustomerService proxy
  ├── CustomerImportTasklet -----+             |
  └── CustomerRepository ----------------------+
```

Service được chia sẻ, còn input, authentication principal, output và lifecycle của mỗi request/job vẫn thuộc adapter tương ứng.

## 11. Khi adapter chạy trong process riêng

Nếu CLI và REST được triển khai thành hai ứng dụng độc lập, mỗi process tạo application context và bean instance riêng. Chúng có thể dùng chung source module hoặc thư viện application/domain, nhưng không chia sẻ cùng một object trong bộ nhớ.

Ví dụ:

```text
CLI process                       REST process
  ApplicationContext                ApplicationContext
    CustomerCommands                   CustomerController
    RegisterCustomerService            RegisterCustomerService
             |                                  |
             +------------ shared DB ----------+
```

Khi tách process:

- Cùng dùng application service code hoặc cùng triển khai use case theo một contract.
- Mỗi process có configuration, connection pool và lifecycle riêng.
- Database unique constraint vẫn cần để bảo vệ tính duy nhất khi hai process đăng ký cùng email đồng thời.
- Không dùng singleton bean trong bộ nhớ làm khóa hoặc cơ chế đồng bộ giữa các process.
- Nếu cần giao tiếp qua mạng, tạo API hoặc message contract rõ ràng; không cố chia sẻ object Java qua ranh giới process.

## 12. Validation ở adapter và validation trong use case

Validation nên được đặt theo ý nghĩa:

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| CLI/REST boundary | Kiểm tra cú pháp và hình dạng input | Option bắt buộc, JSON field, kiểu ngày |
| Batch reader/processor | Kiểm tra định dạng record nguồn | Cột thiếu, encoding sai, mã khách hàng không hợp lệ |
| Application service/domain | Bảo vệ quy tắc nghiệp vụ | Email không được trùng, trạng thái cho phép đăng ký |
| Database | Bảo vệ invariant ở mức lưu trữ | Unique constraint, foreign key, not-null |

Không chỉ dựa vào validation của REST vì CLI và batch có thể gọi cùng service. Không chỉ dựa vào validation ở UI vì một API hoặc một job khác có thể bỏ qua adapter hiện tại.

## 13. Idempotency và xử lý gọi lặp

Một use case có thể được gọi lại vì người dùng chạy lại command, REST client retry sau timeout hoặc Spring Batch restart job. Nếu thao tác tạo dữ liệu không idempotent, lần chạy lại có thể tạo bản ghi trùng hoặc lặp side effect.

Hãy quyết định theo nghiệp vụ:

- Dùng unique constraint cho khóa nghiệp vụ như email nếu yêu cầu là duy nhất.
- Dùng idempotency key cho request có thể được gửi lại sau timeout.
- Với batch, lưu checkpoint và định danh record để restart không xử lý sai dữ liệu đã commit.
- Với side effect bên ngoài database, cân nhắc outbox, message key hoặc API hỗ trợ idempotency.
- Không giả định transaction database có thể rollback email, HTTP request hoặc message đã gửi tới hệ thống khác.

Idempotency nên nằm ở application/domain boundary hoặc cơ chế lưu trữ dùng chung để CLI, REST và batch nhận cùng một hành vi.

## 14. Quyền truy cập và ngữ cảnh người gọi

Các adapter có cơ chế xác thực khác nhau. REST có thể dùng Spring Security; CLI có thể chạy dưới tài khoản hệ điều hành hoặc yêu cầu đăng nhập; batch thường dùng service account. Không nên để service phụ thuộc trực tiếp vào `HttpServletRequest` hoặc `SecurityContextHolder` nếu use case cần biết ai đang thực hiện thao tác.

Thay vào đó, truyền một actor/context rõ ràng khi nghiệp vụ cần:

```java
record ActorContext(String actorId, String channel) {
}

record RegisterCustomerInvocation(
        RegisterCustomerCommand command,
        ActorContext actor) {
}
```

Nếu use case cần actor, thay đổi contract để nhận `RegisterCustomerInvocation` thay cho `RegisterCustomerCommand`, rồi để mỗi adapter tạo actor context từ cơ chế xác thực của nó. Trong dự án thực tế, có thể dùng một abstraction như `CurrentActor` hoặc một tham số actor trong application command. Service kiểm tra quyền nghiệp vụ ở nơi có đủ thông tin và không tin vào actor ID tùy ý do client gửi lên.

## 15. Cấu hình ứng dụng có nhiều adapter

Không phải deployment nào cũng cần bật tất cả adapter. Có thể tách dependency hoặc cấu hình bằng profile/conditional configuration:

- CLI deployment chỉ đưa Spring Shell và adapter CLI vào classpath.
- REST deployment đưa Spring Web và adapter REST vào classpath.
- Batch deployment đưa Spring Batch và job configuration vào classpath.
- Một ứng dụng hợp nhất có thể bật nhiều adapter nếu yêu cầu vận hành phù hợp.

Không nên đưa dependency web hoặc batch vào module application chỉ để service biên dịch được. Module application nên phụ thuộc vào domain abstraction và các port cần thiết; adapter/infrastructure chịu trách nhiệm nối framework.

Nếu tất cả adapter nằm trong cùng Spring Boot application, cần kiểm tra component scan để command, controller, tasklet và service đều được đăng ký. Trong Spring Shell 4, method `@Command` phải nằm trong bean Spring và Spring Boot auto-configuration hỗ trợ command scanning.

## 16. Kiểm thử service và từng adapter

Tách service khỏi adapter giúp kiểm thử nghiệp vụ mà không cần khởi động terminal, web server hoặc batch runtime.

| Loại test | Phạm vi | Điều cần xác nhận |
|---|---|---|
| Unit test application service | Service + mock repository/validator | Quy tắc đăng ký, chuẩn hóa, duplicate và kết quả |
| CLI test | Command handler + mock use case hoặc `@ShellTest` | Option được ánh xạ đúng và thông báo terminal phù hợp |
| REST MVC test | Controller + mock use case | Route, JSON, validation và HTTP status |
| Batch step test | Tasklet/reader/writer + mock use case | Chunk, retry, skip, restart và transaction policy |
| Integration test | Application context + database thật hoặc container | Bean wiring, transaction, unique constraint và exception mapping |

Một test quan trọng là gọi cùng use case qua nhiều adapter với cùng input hợp lệ rồi xác nhận kết quả nghiệp vụ giống nhau. Các adapter có thể trả format khác nhau, nhưng không được tạo ra quy tắc đăng ký khác nhau.

## 17. Những cách tổ chức nên tránh

- **Đặt nghiệp vụ trong command handler:** REST và batch sẽ phải sao chép logic.
- **Controller gọi repository trực tiếp:** quy tắc nghiệp vụ bị rải trong transport layer.
- **Service nhận `CommandContext` hoặc request HTTP:** application layer bị khóa vào một giao diện.
- **Dùng static mutable state để chia sẻ giữa adapter:** khó kiểm thử và không hoạt động như mong đợi khi chạy nhiều process.
- **Tự tạo service bằng `new` trong từng adapter:** bỏ qua dependency injection, proxy và transaction management của Spring.
- **Đặt toàn bộ file import trong một transaction khổng lồ:** gây áp lực bộ nhớ/lock và làm restart khó khăn.
- **Ánh xạ HTTP status trong service:** CLI và batch sẽ phụ thuộc vào quy ước của REST.
- **Chỉ kiểm tra input ở adapter:** một caller khác có thể bỏ qua validation.

## 18. Bài tập thực hành

Xây dựng use case `RegisterCustomerUseCase` có thể được gọi từ Spring Shell, REST và Spring Batch.

Hãy thực hiện:

1. Tạo `RegisterCustomerCommand`, `CustomerResult` và interface use case.
2. Viết `CustomerRegistrationService` kiểm tra email, chuẩn hóa dữ liệu và lưu khách hàng.
3. Đặt transaction boundary ở method service.
4. Tạo command `customer register` dùng constructor injection.
5. Tạo `POST /api/customers` nhận request DTO và gọi cùng use case.
6. Tạo batch writer hoặc tasklet đọc record rồi gọi cùng use case.
7. Ánh xạ exception thành thông báo CLI, HTTP status và batch skip/retry policy tương ứng.
8. Thử đăng ký cùng email từ hai adapter và xác nhận database vẫn bảo vệ unique constraint.
9. Chạy các adapter trong cùng application context; sau đó mô phỏng CLI và REST ở hai process riêng.
10. Viết unit test service và test riêng từng adapter.

**Kết quả cần nộp:** sơ đồ package/adapter, application service, command handler, REST controller, batch component, cấu hình transaction và bộ test chứng minh cả ba giao diện dùng chung quy tắc nghiệp vụ.

## 19. Checklist trước khi thêm giao diện mới

- [ ] Use case có input/output kiểu ứng dụng, không phụ thuộc transport.
- [ ] Quy tắc nghiệp vụ được đặt trong application service/domain.
- [ ] CLI, REST và batch chỉ làm nhiệm vụ chuyển input/output.
- [ ] Mọi adapter đều gọi cùng interface use case.
- [ ] Validation nghiệp vụ được thực hiện dù caller đến từ đâu.
- [ ] Transaction boundary nằm ở method nghiệp vụ phù hợp.
- [ ] Đã hiểu proxy semantics và tránh self-invocation với `@Transactional`.
- [ ] Exception nghiệp vụ không chứa HTTP status hoặc command-specific type.
- [ ] Mỗi adapter ánh xạ lỗi theo giao thức riêng.
- [ ] Batch có chunk/retry/skip/restart policy phù hợp với kích thước dữ liệu.
- [ ] Tác vụ có thể gọi lại được bảo vệ bằng idempotency/unique constraint.
- [ ] Không dùng singleton mutable state để giữ dữ liệu request.
- [ ] Phân biệt reuse cùng code với chia sẻ cùng bean instance giữa các process.
- [ ] Đã kiểm thử service và từng adapter riêng.

## Tài liệu tham khảo

- [Spring Shell 4.0 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0 — Command Annotation](https://docs.spring.io/spring-shell/reference/4.0-SNAPSHOT/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 4.0 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Spring MVC Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Batch — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch 6 — Tasklet API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/step/tasklet/Tasklet.html)
- [Spring Batch 6 — RepeatStatus API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/infrastructure/repeat/RepeatStatus.html)
