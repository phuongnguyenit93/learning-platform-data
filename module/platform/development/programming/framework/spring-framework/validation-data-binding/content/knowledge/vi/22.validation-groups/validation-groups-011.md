# Tiêu chí chọn nhiều DTO thay vì một mô hình có quá nhiều nhóm

> **Ngữ cảnh:** Jakarta Bean Validation và Spring Framework, phần **Nhóm kiểm tra**. Mục tiêu của bài là quyết định khi nào dùng một DTO với các nhóm `Create`/`Update`, khi nào tách `CreateRequest`, `UpdateRequest`, `PatchRequest` và `Response`. Nội dung có ma trận quyết định, ví dụ Java 17+ chạy được với Maven/Hibernate Validator, code Spring MVC, chiến lược migration, kiểm thử và các sai lầm thường gặp.

## 1. Câu hỏi đúng trước khi chọn thiết kế

Giả sử ứng dụng quản lý tài khoản có các thao tác:

- `POST /accounts`: client gửi tên và mã khởi tạo; server sinh `id`.
- `PUT /accounts/{id}`: client được sửa tên, không được đổi mã khởi tạo hoặc vai trò quản trị qua API này.
- `PATCH /accounts/{id}`: client có thể chỉ gửi một số field cần cập nhật.
- `GET /accounts/{id}`: trả `id`, tên và trạng thái công khai, không trả secret.

Có hai giải pháp:

1. **Một DTO + validation groups:** đặt mọi field vào `AccountInput`, dùng `@NotBlank(groups = Create.class)`, `@NotNull(groups = Update.class)`; controller chọn nhóm bằng `@Validated(Create.class)` hoặc `@Validated(Update.class)`.
2. **Nhiều DTO theo use case:** `CreateAccountRequest`, `UpdateAccountRequest`, `PatchAccountRequest`, `AccountResponse`. Mỗi type chứa đúng những field thuộc contract, thường dùng `@Valid` để kiểm tra nhóm `Default`.

Hai giải pháp có thể đạt cùng kết quả Bean Validation, nhưng **không đảm bảo cùng mức rõ ràng về hợp đồng dữ liệu**. Groups là công cụ chọn ràng buộc sẽ chạy; DTO là công cụ mô tả **hình dạng và ý nghĩa** của dữ liệu. Groups **không tự xóa field khỏi JSON**, không ngăn client gửi một property đang có trong class và không thay thế kiểm tra quyền ghi.

```text
                    Các thao tác / use case
                             │
                 Shape và ý nghĩa có giống nhau?
                       /             \
                     Có               Không
                      │                 │
             Một DTO + groups       DTO riêng
             có thể đơn giản        thường rõ hơn
                      │                 │
                      └────────┬────────┘
                               ▼
                    Mapper/command rõ ràng
                               ▼
                Domain + authorization + database
```

**Không có quy tắc “cứ hai nhóm là phải tách DTO”.** Phải xem độ khác biệt về shape, quyền ghi, vòng đời, khả năng tiến hóa và độ phức tạp của ma trận group.

## 2. Trách nhiệm khác nhau của DTO, group và domain

| Lớp/cơ chế | Trách nhiệm chính | Không phải trách nhiệm của nó |
| --- | --- | --- |
| Request DTO | Field nào client có thể gửi cho một operation; constraint đầu vào | Quy tắc nghiệp vụ toàn hệ thống |
| Bean Validation group | Chọn tập constraint nào được xét trên object | Ẩn field, chặn mass assignment, phân quyền |
| Service/domain | Invariant, trạng thái, authorization, transaction, quy tắc liên đối tượng | Là một bản sao của tất cả JSON request |
| Response DTO | Field nào server công khai | Dùng request/entity chứa secret làm response |
| Mapper | Chỉ chuyển field được phép vào domain command/entity | Copy tất cả property chỉ vì tên trùng |

Trong Jakarta Validation:

- Constraint **không khai báo `groups`** thuộc `jakarta.validation.groups.Default`.
- Constraint `@NotBlank(groups = Create.class)` chỉ thuộc `Create`, **không tự thuộc `Default`**.
- `validator.validate(bean)` kiểm tra nhóm mặc định; `validate(bean, Create.class)` kiểm tra nhóm được chọn và các quan hệ được định nghĩa theo đặc tả.
- `@Valid` trên Spring MVC argument thông thường chọn `Default`; `@Validated(Create.class)` giúp yêu cầu group tùy chỉnh.
- Truyền `validate(bean, Default.class, Create.class)` chọn cả hai; không mặc định bảo đảm thứ tự thực hiện nếu không định nghĩa `@GroupSequence`.

**Kết luận nhỏ:** thay một DTO chung bằng DTO riêng có thể xóa nhu cầu phải chọn custom group trong controller, nhưng không tự giải quyết mọi rule nghiệp vụ, lỗi JSON parsing hoặc kiểm tra quyền.

## 3. Hai thiết kế trên cùng một ví dụ

### 3.1. Một DTO với hai nhóm kiểm tra

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public interface Create {}
public interface Update {}

public class AccountInput {
    @NotBlank(groups = {Create.class, Update.class})
    private String displayName;

    @NotBlank(groups = Create.class)
    private String initialCode;

    @NotNull(groups = Update.class)
    private Long id;
}
```

Đây là các **fragment minh họa**; khi biên dịch, mỗi top-level `public` type cần file riêng, và DTO cần constructor/accessors phù hợp với cách binding.

Bảng logic:

| Nhóm được yêu cầu | `displayName` | `initialCode` | `id` |
| --- | --- | --- | --- |
| `Default` | Không kiểm tra | Không kiểm tra | Không kiểm tra |
| `Create` | `@NotBlank` | `@NotBlank` | Không kiểm tra |
| `Update` | `@NotBlank` | Không kiểm tra | `@NotNull` |

Nếu một endpoint chỉ gắn `@Valid`, không chỉ định `Create`/`Update`, các constraint kể trên có thể không chạy vì chúng chỉ thuộc nhóm tùy chỉnh. Đây là lỗi rất dễ xảy ra khi số nhóm lớn và mỗi controller phải nhớ group của mình.

Ngoài ra, class `AccountInput` vẫn tồn tại ba field ở cả create/update. Nếu client gửi `id` trong create, việc nhóm `Create` không kiểm tra `id` **không có nghĩa Jackson tự từ chối property đó**, và mapper có thể vô tình sử dụng nó.

### 3.2. DTO riêng theo thao tác

```java
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
        @NotBlank String displayName,
        @NotBlank String initialCode) {
}

public record UpdateAccountRequest(
        @NotBlank String displayName) {
}

public record AccountResponse(
        Long id,
        String displayName) {
}
```

Các record trên là fragment; mỗi `public record` cần file riêng khi đặt top-level. Với `PUT /accounts/{id}`, ID nằm trong path nên `UpdateAccountRequest` không cần thêm ID; một API khác có thể chủ ý đặt ID trong body nếu contract quy định.

Lợi ích:

- `CreateAccountRequest` không có field `id`.
- `UpdateAccountRequest` không có field `initialCode`.
- Các constraint thường thuộc `Default`, phù hợp với `@Valid`.
- Request/response có schema riêng; type system và reviewer thấy rõ trường nào có mặt.
- API create có thể thay đổi mà không nhất thiết làm thay đổi update.
- Khi mapping, mỗi request type dẫn đến một command/domain operation cụ thể.

Chi phí là có thêm class, tests và mapper. Việc hai DTO đều có `displayName` là **lặp khai báo contract** có chủ đích, không nhất thiết là lặp logic nghiệp vụ.

## 4. Những tiêu chí khiến **nhiều DTO** thường tốt hơn

### 4.1. Field được phép nhận khác nhau

Nếu create nhận `initialCode` nhưng update không được phép nhận, hoặc admin API mới được phép sửa `role`, việc đưa tất cả field vào một DTO chung tạo “superset” dễ bị dùng nhầm.

Ví dụ:

- `CreateUserRequest`: `email`, `password`.
- `UpdateProfileRequest`: `displayName`, `avatarUrl`.
- `ChangePasswordRequest`: `oldPassword`, `newPassword`.
- `AdminChangeRoleRequest`: `role`, `reason`.

Bốn thao tác này có ý nghĩa và quyền truy cập khác nhau. Dùng một DTO khổng lồ với bốn group có thể giảm số class nhưng tăng số trạng thái vô nghĩa, khó phân biệt field được phép bind. **DTO riêng mô tả quyền gửi ở cấp shape**; tuy vậy vẫn phải có authorization và mapping allowlist ở server.

### 4.2. Nhiều field null vì “không áp dụng cho bước này”

Nếu create luôn có `id=null`, update luôn có `initialCode=null`, publish luôn có `draftOnlyFlag=null`, service phải biết group đã được dùng để diễn giải null. Rủi ro xuất hiện khi một type mô tả rất nhiều tổ hợp trạng thái không hợp lệ theo nghiệp vụ.

**Tín hiệu tách:** code service có nhiều nhánh `if (creating)`/`if (updating)` chỉ để quyết định field nào được đọc. DTO theo use case có thể loại bỏ các field không tồn tại trong ngữ cảnh đó, thay vì chỉ bỏ qua constraint.

Không nên tách nếu một field thật sự **tùy chọn** trong cả hai thao tác và có cùng ý nghĩa.

### 4.3. Bảo mật và dữ liệu nội bộ

`groups` **không phải** allowlist của data binding. Một field `isAdmin` không được validate ở group Update vẫn có thể bị deserialize nếu type có field đó và mapper nhận nó. Dùng DTO riêng giúp giảm field không cần thiết trên request, nhưng không thay thế:

- Kiểm tra identity và authorization.
- Chỉ map những property được phép cập nhật.
- Rule nghiệp vụ ở service/domain.
- Kiểm tra lại state từ database thay vì tin mọi dữ liệu client gửi.

Đừng dùng cùng class cho request và response nếu class có `passwordHash`, `initialCode`, token, các cờ nội bộ hoặc metadata audit. Validation group không quyết định những field Jackson sẽ serialize.

### 4.4. Contract và schema tiến hóa khác nhau

Nếu create phải có `invitationToken` mới nhưng update không cần thay đổi, DTO riêng giúp cô lập tác động và dễ cập nhật OpenAPI/client SDK. Với DTO chung, thêm field có thể làm thay đổi schema của nhiều endpoint dù group tương ứng không áp dụng.

Việc tách DTO có ích khi:

- Các endpoint có lịch version/deprecation khác nhau.
- Các loại client được phép dùng payload khác nhau.
- Một bước import/batch có shape khác hoàn toàn CRUD.
- Response có computed fields mà client không bao giờ gửi.

Tuy nhiên, nếu hai endpoint thật sự chia sẻ cùng schema và cùng thay đổi trong tương lai, DTO chung vẫn có thể giảm chi phí bảo trì.

### 4.5. Quá nhiều groups khiến người đọc phải suy luận

Những dấu hiệu nên xem lại thiết kế:

- Hầu hết constraint có danh sách nhóm dài: `{Create.class, Update.class, Import.class, Publish.class, Admin.class, ...}`.
- Nhiều `@GroupSequence`, `@ConvertGroup`, group kế thừa chỉ để phục vụ các endpoint khác nhau.
- Test phải phối hợp nhiều group mới phát hiện một field thiếu.
- Một thay đổi trong create thường làm test update/import hỏng.
- Reviewer không thể suy ra từ type: “request này có được gửi field `role` không?”.
- Bug xảy ra vì endpoint dùng nhầm `@Valid` với `@Validated(SomeGroup.class)`.

Số lượng group **không có ngưỡng chuẩn**. Hai hoặc ba nhóm rõ ràng không tự động là lỗi; một nhóm cũng có thể quá tải nếu DTO chứa các field nhạy cảm không phù hợp.

### 4.6. PATCH có ba trạng thái cần phân biệt

PATCH thường mang semantics khác PUT:

1. **Absent:** field không được gửi, giữ nguyên giá trị.
2. **Present-null:** field có mặt với `null`, có thể nghĩa là xóa giá trị.
3. **Present-value:** field có mặt với giá trị mới.

Trong DTO `String displayName` thông thường, absent và explicit null có thể cùng trở thành null sau binding, nên chỉ thêm `@NotNull(groups = Patch.class)` không làm xuất hiện thông tin “field có được gửi hay không”.

Nếu API cần semantics này, dùng `PatchAccountRequest` với cơ chế **field presence** rõ (mô hình present/value riêng, JSON Merge Patch/JSON Patch hoặc parser có chủ đích). Kiểm thử chính xác behavior của Jackson/HTTP boundary; `Optional<T>` không tự xử lý ổn định mọi trường hợp absent/null ở mọi cấu hình.

## 5. Khi một DTO dùng chung với groups lại hợp lý

Groups vẫn là tính năng chuẩn và hữu ích. Một DTO chung thường đáng giữ khi:

- Hai use case có **cùng tập field, cùng ý nghĩa**; chỉ khác ít constraint.
- Không có field nhạy cảm bị cấm xuất hiện trong một operation.
- Nhiều bước của **cùng biểu mẫu** (draft → submit) yêu cầu mức kiểm tra khác nhau, nhưng shape không đổi.
- Số nhóm ít, cách chọn nhóm và test rõ ràng.
- DTO được dùng nội bộ như một command/state object, không phải một superset cho mọi REST boundary.

Ví dụ một biểu mẫu được lưu nháp rồi gửi:

```java
public interface OnSubmit {}

public class ApplicationDraft {
    @NotBlank
    private String applicantName; // Default

    @NotNull(groups = OnSubmit.class)
    private Long chosenProgramId;
}
```

Đây là code minh họa. Khi gọi `validate(draft, OnSubmit.class)`, constraint `applicantName` chỉ thuộc `Default` **không tự chạy**; muốn submit kiểm tra cả hai, chọn `Default.class, OnSubmit.class` hoặc dùng kế thừa/sequence có chủ đích.

Vì cùng một đơn giữ nguyên các field qua các giai đoạn, groups có thể diễn đạt đúng yêu cầu mà không phải tách `DraftRequest` và `SubmitRequest` nếu hai contract thật sự trùng shape.

## 6. Java 17+ chạy được: cùng quy tắc bằng hai phương án

Ví dụ sau dùng Jakarta Validation/Hibernate Validator để chứng minh: (1) DTO chung có custom groups có thể không được kiểm tra ở `Default`; (2) DTO riêng với constraint mặc định có thể phát hiện những lỗi tương đương, đồng thời làm rõ field thuộc use case nào.

Cấu trúc:

```text
dto-design-demo/
├── pom.xml
└── src/main/java/demo/DtoDecisionDemo.java
```

**`pom.xml`** — dùng Spring Boot starter validation làm dependency, nhưng chương trình `main` là **Java độc lập**, không khởi động Spring:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>dto-design-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/DtoDecisionDemo.java`**:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public final class DtoDecisionDemo {
    private DtoDecisionDemo() {}

    public interface Create {}
    public interface Update {}

    public record SharedRequest(
            @NotBlank(groups = {Create.class, Update.class})
            String displayName,
            @NotBlank(groups = Create.class)
            String initialCode,
            @NotNull(groups = Update.class)
            Long id) {
    }

    public record CreateRequest(
            @NotBlank String displayName,
            @NotBlank String initialCode) {
    }

    public record UpdateRequest(
            @NotNull Long id,
            @NotBlank String displayName) {
    }

    public static void main(String[] args) {
        SharedRequest sharedBad = new SharedRequest("", "", null);
        CreateRequest createBad = new CreateRequest("", "");
        UpdateRequest updateBad = new UpdateRequest(null, "");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            show(validator, "shared.Default", sharedBad);
            show(validator, "shared.Create", sharedBad, Create.class);
            show(validator, "shared.Update", sharedBad, Update.class);
            show(validator, "createDTO.Default", createBad);
            show(validator, "updateDTO.Default", updateBad);

            show(validator, "shared.createValid",
                    new SharedRequest("Mai", "CODE-1", null),
                    Create.class);
            show(validator, "shared.updateValid",
                    new SharedRequest("Mai", null, 7L),
                    Update.class);
            show(validator, "createDTO.valid",
                    new CreateRequest("Mai", "CODE-1"));
            show(validator, "updateDTO.valid",
                    new UpdateRequest(7L, "Mai"));
        }
    }

    private static void show(Validator validator,
                             String label,
                             Object bean,
                             Class<?>... groups) {
        List<String> errors = validator.validate(bean, groups)
                .stream()
                .map(v -> v.getPropertyPath().toString() + ":"
                        + v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName())
                .sorted()
                .toList();

        System.out.println(label + " -> " + errors);
    }
}
```

Chạy từ thư mục chứa `pom.xml` với Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DtoDecisionDemo
```

**Các dòng do chương trình in ra** (không gồm log phụ của Maven/provider):

```text
shared.Default -> []
shared.Create -> [displayName:NotBlank, initialCode:NotBlank]
shared.Update -> [displayName:NotBlank, id:NotNull]
createDTO.Default -> [displayName:NotBlank, initialCode:NotBlank]
updateDTO.Default -> [displayName:NotBlank, id:NotNull]
shared.createValid -> []
shared.updateValid -> []
createDTO.valid -> []
updateDTO.valid -> []
```

Giải thích:

1. `shared.Default` rỗng vì tất cả constraint của `SharedRequest` đều ghi `Create`/`Update`, không thuộc `Default`. Một controller dùng nhầm `@Valid` có thể bỏ lọt các lỗi đó.
2. `shared.Create` chọn tên + mã; `id` không bị kiểm tra.
3. `shared.Update` chọn tên + ID; mã không bị kiểm tra.
4. Hai DTO riêng chứa đúng các constraint cần thiết, đều thuộc nhóm mặc định, nên `validator.validate(bean)` cho kết quả tương ứng.
5. Với dữ liệu hợp lệ, cả hai cách đều không tạo violation, nhưng DTO chung vẫn có field không cần dùng ở mỗi thao tác.

Code sắp xếp violations theo path/tên constraint để không phụ thuộc thứ tự `Set`; không in message đã địa phương hóa. `ValidatorFactory` được đóng đúng lifecycle bằng `try-with-resources`.

Đây là **minh chứng về Bean Validation**, không có nghĩa Jackson sẽ tự cấm client gửi field ở nhóm khác hoặc service sẽ tự có authorization.

## 7. Spring MVC: nhóm chọn constraint, DTO chọn contract

### 7.1. Nếu giữ một DTO chung

Các fragment sau nằm trong ứng dụng Spring Boot 3 có Spring Web MVC và starter-validation:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SharedAccountController {
    @PostMapping("/shared-accounts")
    public void create(
            @Validated(Groups.Create.class)
            @RequestBody SharedAccountRequest request) {
        // Chỉ map field cho Create.
    }

    @PutMapping("/shared-accounts")
    public void update(
            @Validated(Groups.Update.class)
            @RequestBody SharedAccountRequest request) {
        // Chỉ map field cho Update.
    }
}
```

Đây là **mã tích hợp minh họa**, cần định nghĩa `Groups`, `SharedAccountRequest`, package/import và service. Nếu quên `@Validated(...)` hoặc truyền nhầm group, các constraint có thể không được chạy như mong đợi.

### 7.2. Nếu dùng DTO theo use case

```java
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
        @NotBlank String displayName,
        @NotBlank String initialCode) {}

public record UpdateAccountRequest(
        @NotBlank String displayName) {}
```

Các `public record` đặt trong file Java riêng; controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateAccountRequest input) {
        // accountService.create(input);
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateAccountRequest input) {
        // accountService.update(id, input);
        return ResponseEntity.noContent().build();
    }
}
```

Mã trên là **fragment tích hợp**, không phải chương trình độc lập. Response 204 chỉ là lựa chọn minh họa, không phải quy tắc bắt buộc cho mọi REST API; nhiều API tạo có thể trả 201 Created hoặc 200 tùy contract.

Spring MVC thường kích hoạt Jakarta Validation cho `@Valid @RequestBody` sau deserialization. Nếu body sai cú pháp hoặc sai kiểu, Jackson/message converter có thể báo lỗi *trước* validation. Với method có direct constraint trên tham số/return, cơ chế method validation của Spring Framework 6.1+ có thể dẫn tới `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException`; cần test đúng signature và error handler của ứng dụng.

**Điều không đổi:** DTO riêng vẫn cần `@Valid`/provider, `@Valid` tại các field con khi cần cascade, mapping được phép và kiểm tra quyền ở service.

## 8. Tách DTO không đồng nghĩa nhân bản invariant của domain

Một số ràng buộc dành cho input, một số dành cho bản thân dữ liệu nghiệp vụ:

- Create request: `initialCode` bắt buộc để khởi tạo.
- Update request: tên mới không được blank.
- Domain account: quy tắc account được phép đổi tên, đổi email hoặc chuyển trạng thái.
- Database: các constraint lưu trữ/tính toàn vẹn phù hợp.

Nếu tách DTO, đừng copy tất cả business logic ra từng controller. Giữ rule chung ở **domain service / value object / database** theo yêu cầu hệ thống; DTO chỉ kiểm tra đầu vào cụ thể.

Mapping fragment:

```java
// Fragment: Account, repository, exception chưa được định nghĩa.
public Account create(CreateAccountRequest input) {
    Account account = Account.create(
            input.displayName(),
            input.initialCode());
    return repository.save(account);
}

public void update(Long id, UpdateAccountRequest input) {
    Account account = repository.findById(id)
            .orElseThrow(/* exception phù hợp */);
    account.rename(input.displayName());
}
```

Với mapper framework, cần cấu hình field được phép ghi; đừng dùng copy-all-property trên entity managed khi có những field như `role`/`ownerId`/`balance`. Chia sẻ value object và custom constraint nơi hợp lý thay vì gộp mọi request chỉ để tránh lặp một dòng `@NotBlank`.

Nếu dùng composition để chia sẻ nested DTO, nhớ gắn `@Valid` khi muốn cascade và phải chấp nhận shape JSON thay đổi theo cách lồng object. Không dùng inheritance DTO chỉ để tiết kiệm một hoặc hai field nếu nó làm nhiều field không liên quan xuất hiện trên các request khác.

## 9. Ma trận quyết định

Ma trận sau là **heuristic thiết kế**, không phải tiêu chuẩn bắt buộc của Jakarta hay Spring:

| Câu hỏi | Nếu trả lời “có” | Hướng ưu tiên |
| --- | --- | --- |
| Hai thao tác có cùng field, cùng ý nghĩa, chỉ khác vài constraint? | Có | Một DTO + groups có thể hợp lý |
| Một field phải **bị loại khỏi request** ở thao tác khác? | Có | DTO riêng |
| Có secret, role, audit field và nguy cơ bind field không phù hợp? | Có | DTO riêng + authorization/allowlist |
| Create, update, PATCH, response có shape khác nhau? | Có | DTO riêng theo use case |
| Nhiều field null vì “không dùng trong group này”? | Có | DTO riêng |
| Có nhiều group inheritance, conversion, sequence chỉ để phục vụ endpoint? | Có | Xem xét tách |
| Draft và submit sử dụng cùng biểu mẫu, cùng shape? | Có | Groups có thể thích hợp |
| API/schema/client SDK cần tiến hóa riêng theo endpoint? | Có | DTO riêng |
| Tách dẫn đến hàng loạt DTO giống hệt, không có hợp đồng độc lập? | Có | Cân nhắc DTO chung |
| Đã từng có bug bỏ lọt rule do chọn nhầm group? | Có | Tách DTO hoặc đơn giản hóa group/test |

Cách hỏi ngắn:

- **Groups:** “Lần validate này kiểm tra *những ràng buộc nào* trên cùng object?”
- **DTO riêng:** “Use case này *được nhận những field nào*?”
- **Service/domain:** “Thao tác/trạng thái này *có hợp lệ theo nghiệp vụ*?”
- **Authorization:** “*Ai* có quyền làm thao tác này?”

Đừng lấy một trong bốn công cụ thay thế hoàn toàn ba công cụ còn lại.

## 10. Refactor từ một DTO nhiều groups sang nhiều DTO

Trình tự có kiểm soát:

1. **Kiểm kê contract hiện tại:** endpoint, group được chọn, shape JSON/form, field được bind, nested validation, mapper, schema/error response.
2. **Viết characterization tests** cho các request đang được chấp nhận/từ chối; kiểm thử cả absent, null, sai kiểu, bean con, group inheritance và security.
3. **Xác định field được phép theo use case** trước khi tạo DTO mới. Không sao chép mù quáng mọi property của class chung.
4. **Khai báo các DTO mới** với constraint mặc định phù hợp từng thao tác. Riêng PATCH dùng mô hình có thể diễn đạt field presence khi cần.
5. **Mapping theo operation** về command/domain; giữ invariant và authorization ở service.
6. **Thay controller từng endpoint** từ `@Validated(Create.class) SharedRequest` sang `@Valid CreateRequest`, xác nhận không bỏ sót ràng buộc do chuyển nhóm.
7. **Kiểm tra backward compatibility:** thay Java type có thể đổi JSON schema, error message, cách xử lý unknown fields hoặc lỗi deserialize trước validation.
8. **Chạy regression tests** và contract tests: success, validation, field cấm, nested DTO, quyền ghi, response không lộ secret.
9. **Xóa code/group cũ khi không còn caller**, tránh hai đường validate không được test song song.

### Test matrix nên có

| Tình huống | Kiểm tra cần thiết |
| --- | --- |
| Create thiếu tên/mã | Vi phạm ở create contract |
| Update thiếu mã khởi tạo | Không đòi trường vốn chỉ dùng khi create |
| Create gửi ID do client tự chọn | Không sử dụng ID trái contract; hành vi reject/ignore được xác định |
| Update gửi field admin | Không cho cập nhật qua endpoint self-service |
| PATCH không gửi field | Giữ nguyên field |
| PATCH gửi null | Chỉ xóa nếu contract cho phép |
| Dữ liệu JSON sai cú pháp | Xử lý như binding/deserialization error |
| Bean con không hợp lệ | `@Valid` cascade đúng chỗ |
| Response | Không có secret/internal metadata |
| Validation nhóm cũ | Không mất những rule cần thiết sau khi tách DTO |

Lưu ý khi refactor sang Java record/constructor binding: cách Jackson xử lý property thiếu, null hoặc sai kiểu có thể khác JavaBean dùng setter, nên behavior HTTP error có thể thay đổi. Đó là điều cần kiểm thử, không nên tự coi là tương thích 100%.

## 11. Sai lầm phổ biến

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “Lặp `displayName` ở hai DTO luôn là vi phạm DRY” | Hai contract độc lập có thể cố ý trùng một khai báo nhỏ |
| “Group làm field không liên quan biến mất khỏi request” | Group chọn constraint, không chọn field JSON |
| “`@Valid` chạy mọi custom group” | Thông thường nó dùng `Default` |
| “`@Validated(Create.class)` tự bao gồm Default” | Không, nếu không có quan hệ nhóm phù hợp |
| “Tách DTO rồi không cần `@Valid`” | Vẫn phải kích hoạt validation và cascade đúng chỗ |
| “DTO riêng thay cho security/authorization” | Vẫn cần kiểm tra quyền và mapping allowlist |
| “Nhiều DTO phải copy business logic” | Invariant dùng chung ở domain/service/value object |
| “`@NotNull` + groups là đủ cho PATCH” | Không tự phân biệt absent với explicit null |
| “Request có thể dùng làm response nếu đổi group” | Group không điều khiển serialization |
| “Một DTO có vài nhóm luôn sai” | Khi shape thật sự giống nhau, groups có thể đơn giản hơn |
| “`@GroupSequence` giải quyết quyền ghi field” | Sequence điều khiển thứ tự validation, không phân quyền |

## 12. Checklist lựa chọn

- [ ] Đã liệt kê **field được phép** ở từng thao tác?
- [ ] Shape thực sự giống nhau hay DTO hiện tại là superset nhiều contract?
- [ ] Có secret, role, ownerId hoặc audit field không nên bind ở một số endpoint?
- [ ] Nhiều `null` xuất hiện vì field không áp dụng hay vì field tùy chọn thật sự?
- [ ] Một thay đổi trong create có cần độc lập với update không?
- [ ] Có dễ chọn nhầm `@Valid`/`@Validated(Group.class)` không?
- [ ] Group inheritance, sequence hoặc conversion có làm logic khó hiểu?
- [ ] Có nhu cầu PATCH absent/null/value không?
- [ ] DTO riêng có còn ánh xạ rõ vào domain với mapping allowlist không?
- [ ] Có test API contract, parsing, validation, authorization và response không lộ secret?
- [ ] Nếu tách DTO, đã xem xét tác động lên JSON schema và client compatibility?

**Kết luận:** Khi **cùng đối tượng và cùng shape** chỉ cần nhiều mức kiểm tra theo giai đoạn, Bean Validation groups rất hữu ích. Khi các thao tác có **field được phép, quyền ghi, cấu trúc dữ liệu hoặc vòng đời tiến hóa riêng**, ưu tiên nhiều DTO giúp hợp đồng rõ và giảm rủi ro. Nhóm chỉ lựa chọn **constraint nào chạy**; không thay thế contract, mapper, domain invariant hay authorization.

### Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 — Groups, Default, Group Sequence](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 — Grouping Constraints](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — `@ModelAttribute` Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
