# Quy tắc kế thừa tiền điều kiện và hậu điều kiện trong Jakarta Validation và Spring

## 1. Bối cảnh: hợp đồng phương thức cũng được kế thừa

Một interface công bố hợp đồng cho người gọi: **giá trị đầu vào nào được chấp nhận** và **kết quả nào được bảo đảm**. Khi class triển khai interface, hoặc class con ghi đè phương thức của class cha, các ràng buộc phương thức trong Jakarta Bean Validation phải tôn trọng nguyên lý thay thế Liskov (*Liskov Substitution Principle – LSP*).

Ví dụ, interface cho phép mọi chuỗi, kể cả chuỗi rỗng:

~~~java
public interface LookupService {
    String lookup(String code);
}
~~~

Nếu implementation chỉ chấp nhận chuỗi không rỗng:

~~~java
public class StrictLookupService implements LookupService {
    @Override
    public String lookup(@NotBlank String code) {
        return code;
    }
}
~~~

Người gọi đang làm việc qua kiểu `LookupService` không biết yêu cầu mới của `StrictLookupService`. Jakarta Validation vì thế **không cho khai báo constraint trên tham số của phương thức ghi đè/triển khai**, ngay cả khi interface gốc chưa có constraint. Đây là vấn đề của **khai báo ràng buộc**, không phụ thuộc giá trị đầu vào lúc chạy.

Ngược lại, interface hứa kết quả không `null`; implementation có thể hứa thêm kết quả chứa ít nhất hai phần tử:

~~~java
public interface Catalog {
    @NotNull
    List<String> available();
}

public class DefaultCatalog implements Catalog {
    @Override
    @Size(min = 2)
    public List<String> available() {
        return List.of("A", "B");
    }
}
~~~

Implementation này hợp lệ: người gọi luôn được bảo đảm điều kiện `@NotNull` của interface, đồng thời implementation đáp ứng `@Size(min = 2)` chặt chẽ hơn. Validation engine **tổng hợp** ràng buộc trả về từ cả interface và implementation.

Hai nguyên tắc cốt lõi của Jakarta Validation:

1. **Tiền điều kiện (preconditions) không được mạnh hơn trong subtype.** Ràng buộc tham số của method override/implementation không được khai báo mới, dù “cùng”, “mạnh hơn” hay “có vẻ yếu hơn” so với ràng buộc của supertype.
2. **Hậu điều kiện (postconditions) không được yếu hơn trong subtype.** Subtype được **thêm** return constraints, còn return constraints từ supertypes vẫn được áp dụng khi validate.

Đây là các quy tắc cụ thể của **method/constructor validation** trong Jakarta Validation, khác với việc kế thừa annotation theo cơ chế Java reflection `@Inherited`. Provider tổng hợp metadata từ interface và superclass theo chuẩn Bean Validation.

## 2. Bảng quyết định nhanh

| Tình huống trong hierarchy | Kết luận theo Jakarta Validation | Lý do |
| --- | --- | --- |
| Supertype khai báo `@NotBlank` trên parameter; override **không khai báo** constraint | **Hợp lệ** | Tiền điều kiện từ supertype vẫn có hiệu lực |
| Supertype không constraint parameter; override thêm `@NotBlank` | **Không hợp lệ** | Tăng tiền điều kiện |
| Supertype có `@Max(100)`; override thêm `@Max(50)` | **Không hợp lệ** | Không được tái khai báo parameter constraint trong override |
| Supertype có `@NotBlank`; override cũng viết `@NotBlank` | **Không hợp lệ** | Kể cả khai báo lặp giống hệt cũng bị cấm |
| Supertype có `@Valid` trên parameter; override lại thêm `@Valid` | **Không hợp lệ** | Không được đánh dấu cascade mới trên overridden parameter |
| Supertype có return `@NotNull`; override không nhắc lại annotation | **Hợp lệ** | Return constraint của supertype tiếp tục được đánh giá |
| Supertype có return `@NotNull`; override thêm `@Size(min=2)` | **Hợp lệ** | Bổ sung hậu điều kiện |
| Return `@Valid` ở supertype; override lặp lại `@Valid` | **Không hợp lệ** | Không được đánh dấu cascade cho cùng return value nhiều lần trên một nhánh kế thừa |
| Hai interface **song song** khai báo cùng method, một interface có parameter constraint | **Không hợp lệ** đối với class triển khai cả hai | Tránh hợp đồng đầu vào không nhất quán giữa hai supertypes |
| Constructor ở class con có constraint khác constructor cha | **Không chịu quy tắc override này** | Constructor không ghi đè nhau |

Một constraint khai báo sai thường được provider báo bằng `jakarta.validation.ConstraintDeclarationException` khi phân tích metadata hoặc thực thi validation. **Không nhất thiết xảy ra ngay lúc biên dịch Java hoặc tạo Spring bean**. Có thể viết code biên dịch thành công nhưng lần validate đầu tiên mới phát hiện lỗi.

## 3. Vì sao không được tăng tiền điều kiện?

### 3.1. Góc nhìn người gọi và kiểu tĩnh

Giả sử API công bố:

~~~java
public interface MessagePort {
    void send(String message);
}
~~~

Người gọi có thể viết:

~~~java
void dispatch(MessagePort port) {
    port.send(""); // Interface không công bố constraint nào.
}
~~~

Nếu `MessagePortImpl` thêm `@NotBlank` ở override, lời gọi hợp đồng hợp lệ theo interface có thể bị validation chặn chỉ vì implementation thay đổi. Đó chính là điều LSP không cho phép: một đối tượng subtype phải thay thế được supertype mà không tạo ra tiền điều kiện bất ngờ.

### 3.2. Cách đặt constraint đúng

Đặt điều kiện lên hợp đồng **từ đầu**:

~~~java
import jakarta.validation.constraints.NotBlank;

public interface MessagePort {
    void send(@NotBlank String message);
}
~~~

Implementation **không cần và không được** đặt lại `@NotBlank` trên parameter của method override:

~~~java
public class MessagePortImpl implements MessagePort {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}
~~~

Khi validation engine kiểm tra `MessagePortImpl.send(...)`, nó nhìn thấy parameter constraint đã khai báo trên `MessagePort.send(...)`. Việc implementation **không có annotation ở tham số** không xóa điều kiện đó.

**Lưu ý:** Jakarta Validation không tự kiểm tra Java method mỗi lần gọi. Cần `ExecutableValidator`, Spring AOP method validation, hoặc framework integration thực sự kích hoạt. Vì vậy một method có khai báo sai có thể chạy “bình thường” khi không có validation; điều đó không làm khai báo ấy trở thành hợp lệ.

### 3.3. Không chỉ có `@NotNull` và `@Size`

Quy tắc tiền điều kiện áp dụng cho:

- Constraint đơn tham số như `@NotBlank`, `@Min`, `@Pattern`, constraint tự viết.
- Constraint trên **type argument của tham số**, như `List<@NotNull Item>`.
- **Cascaded validation** đặt bằng `@Valid` trên tham số hoặc phần tử tham số.
- **Cross-parameter constraint** kiểm tra quan hệ nhiều đối số.

Ví dụ dễ gây hiểu lầm:

~~~java
interface Importer {
    void importItems(List<String> items);
}

class StrictImporter implements Importer {
    @Override
    public void importItems(List<@NotBlank String> items) {
        // ...
    }
}
~~~

Đoạn trên thêm ràng buộc phần tử tham số ở override; theo tinh thần và quy tắc method parameter constraints, hãy khai báo yêu cầu đó ở interface `Importer` thay vì implementation. Ngoài ra, tùy cách sử dụng type-use annotation, Java compiler có quy tắc riêng cho override signatures; khi xử lý lỗi hãy phân biệt lỗi biên dịch Java với `ConstraintDeclarationException` của provider.

**Không cần so sánh xem constraint mới “mạnh” hay “yếu” hơn.** Theo quy tắc mặc định của chuẩn, khai báo parameter constraint mới trên method override là không hợp lệ. Ngay cả `@NotBlank` lặp lại giống hệt annotation ở interface cũng không được xem là cách “ghi đè vô hại”.

### 3.4. Thay đổi nghiệp vụ mà không vi phạm hợp đồng

Nếu một use case thật sự cần yêu cầu đầu vào chặt hơn:

1. **Sửa hợp đồng interface** nếu tất cả implementation và caller phải tuân theo.
2. **Định nghĩa method mới** với tên hoặc signature khác, diễn đạt một nghiệp vụ khác. Một overload mới không override hợp đồng cũ.
3. **Định nghĩa interface hẹp hơn** và dùng nó cho caller có nhu cầu phù hợp, thay vì lén tăng preconditions trên method kế thừa.
4. Với quy tắc chỉ thuộc một tầng nghiệp vụ, kiểm tra tường minh trong thân method và thiết kế API trả lỗi phù hợp; nhưng nếu caller qua hợp đồng cha vẫn phải thay thế được, validation tường minh cũng không nên phá vỡ ngữ nghĩa contract đã hứa.

Không dùng validation group hoặc một annotation tùy chỉnh như thủ thuật để che đi việc thay đổi tiền điều kiện trên override. Việc kích hoạt group khác có thể làm thay đổi tập lỗi lúc chạy, nhưng không tự biến một declaration vi phạm hierarchy thành portable.

## 4. Hậu điều kiện: được bổ sung, không được làm yếu

### 4.1. Return constraints được tổng hợp từ cả hierarchy

Đây là trường hợp **hợp lệ**:

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public interface TicketDirectory {
    @NotNull
    List<String> listTickets();
}

public class TicketDirectoryImpl implements TicketDirectory {
    @Override
    @Size(min = 2)
    public List<String> listTickets() {
        return List.of("T-1", "T-2");
    }
}
~~~

Khi `ExecutableValidator.validateReturnValue(...)` kiểm tra return của `TicketDirectoryImpl.listTickets()`, cả `@NotNull` từ interface và `@Size(min=2)` từ implementation được xét. Nếu return là `null`, `@NotNull` thất bại (trong khi `@Size` thường xem null hợp lệ). Nếu trả list một phần tử, `@Size` thất bại. Hai điều kiện bổ sung cho nhau.

Nếu implementation bỏ `@NotNull` trong source code, điều kiện từ interface **không biến mất**. Đây là điều khác với một số trực giác khi nhìn chỉ annotation của method implementation bằng reflection thông thường: metadata chuẩn Bean Validation đã hợp nhất ràng buộc từ supertypes.

### 4.2. Có thể thêm nhiều return constraints

~~~java
interface NameLookup {
    @NotNull
    String name();
}

class NameLookupImpl implements NameLookup {
    @Override
    @NotBlank
    @Size(min = 3)
    public String name() {
        return "Alice";
    }
}
~~~

`@NotNull` từ interface vẫn có hiệu lực. `@NotBlank` và `@Size(min=3)` trên implementation tăng chất lượng cam kết với caller. Code trên **được phép về mặt quy tắc inheritance**; các ràng buộc phải thực tế thỏa được trong nghiệp vụ.

Cẩn thận khi tự thêm constraint mâu thuẫn, chẳng hạn supertype có `@NotNull` mà subtype thêm `@Null`. Về mặt inheritance, thêm return constraint không bị cấm theo cùng cách với parameter constraints; tuy nhiên tập hậu điều kiện có thể **không tồn tại giá trị nào thỏa đồng thời**, khiến method luôn thất bại. Validation provider không nhất thiết tìm mâu thuẫn logic này lúc khởi tạo. Nên kiểm tra bằng test cho các giá trị hợp lệ.

### 4.3. Kiểu trả về covariant

Java cho phép subtype trả về kiểu con khi override, ví dụ:

~~~java
class Document {}
class PdfDocument extends Document {}

interface DocumentStore {
    @NotNull
    Document fetch();
}

class PdfStore implements DocumentStore {
    @Override
    @NotNull
    public PdfDocument fetch() {
        return new PdfDocument();
    }
}
~~~

Ở đây việc ghi lại `@NotNull` ở **return value** về nguyên tắc là được phép; đó là return constraint, khác với việc lặp annotation trên parameter. Nhưng không cần lặp để giữ điều kiện của interface; nếu giữ lại vì muốn thể hiện ý đồ thì test sẽ giúp xác nhận số lượng violation kỳ vọng. Với return type khác nhau, provider vẫn phải tổng hợp metadata ràng buộc của hierarchy một cách đúng đắn.

### 4.4. Return `@Valid`: có giới hạn đặc biệt

`@Valid` yêu cầu cascade vào object trả về. Ta có thể **bắt đầu** cascade ở subtype nếu supertype chưa đánh dấu:

~~~java
interface CustomerSource {
    Customer load();
}

class ValidatingCustomerSource implements CustomerSource {
    @Override
    @Valid
    public Customer load() {
        return new Customer("An");
    }
}
~~~

Nhưng nếu supertype **đã có `@Valid` trên return**, subtype **không được đánh dấu `@Valid` lại** trên cùng nhánh kế thừa:

~~~java
interface CustomerSource {
    @Valid
    Customer load();
}

class DuplicateCascadeSource implements CustomerSource {
    @Override
    @Valid // Không hợp lệ: trùng cascaded return trên cùng nhánh.
    public Customer load() {
        return new Customer("An");
    }
}
~~~

Hai ví dụ trên là **hai phương án riêng biệt**, không được chép nguyên cả hai định nghĩa `CustomerSource` vào một Java file. Khi interface đã khai báo cascade, implementation chỉ override method và trả object; provider vẫn kiểm tra sâu các property của object ấy.

Vì sao hạn chế này tồn tại? Một lần return validation phải có cơ chế cascade nhất quán; đặt lại `@Valid` và các chuyển đổi group trên override có thể làm người dùng hiểu sai hoặc khiến phương thức có nhiều cấu hình cascade mâu thuẫn.

**Group conversion:** `@ConvertGroup` chỉ hợp lệ ở nơi có `@Valid`; thêm/chỉnh group conversion ở override khi return cascade đã được thiết lập ở ancestor có những hạn chế để bảo đảm không thay đổi hậu điều kiện từ supertype. Với phương thức nhận từ nhiều interface song song và return cascade trên một nhánh, không khai báo tùy tiện group conversion mới trên return của các nhánh song song. Nếu cần đổi group, xem xét thiết kế hợp đồng tại nơi khai báo cascade ban đầu và test metadata/violation.

## 5. Hai interface song song: bẫy nghiêm ngặt hơn override thông thường

### 5.1. Ví dụ sai

~~~java
interface FastSender {
    void send(@NotBlank String text);
}

interface GeneralSender {
    void send(String text);
}

class CombinedSender implements FastSender, GeneralSender {
    @Override
    public void send(String text) {
        // ...
    }
}
~~~

Hai interface **không mở rộng lẫn nhau**, nhưng cùng khai báo `send(String)`. Method trong implementation ghi đè/triển khai cả hai hợp đồng. Vì `FastSender` có parameter constraint trong khi `GeneralSender` không có, người gọi qua `GeneralSender` có thể bị áp điều kiện bất ngờ.

Quy tắc chuẩn: nếu một method được thừa kế/triển khai từ **nhiều supertypes song song**, **không supertypes nào trong các nhánh liên quan được khai báo parameter constraints/cascade trên method đó**, kể cả khi các nhánh tình cờ dùng cùng một constraint. Chỉ xóa annotation ở `CombinedSender.send` không đủ để sửa ví dụ; phải thay đổi hợp đồng từ các supertypes.

### 5.2. Ví dụ đúng

Một cách thiết kế là đưa yêu cầu chung lên **một ancestor chung**, để các nhánh không còn là hai nguồn parameter contracts độc lập:

~~~java
interface BaseSender {
    void send(@NotBlank String text);
}

interface AuditedSender extends BaseSender {
    // Không tái khai báo send(String).
}

interface RetryingSender extends BaseSender {
    // Không tái khai báo send(String).
}

class CombinedSender implements AuditedSender, RetryingSender {
    @Override
    public void send(String text) {
        // ...
    }
}
~~~

Trong sơ đồ này, có **một nơi** khai báo parameter constraint (`BaseSender`), các interface còn lại chỉ thừa kế cùng hợp đồng đó và implementation không khai báo lại constraint. Đây là cách giảm rủi ro xung đột trong thiết kế đa interface. Khi framework vẫn phát hiện metadata từ những kiểu song song, test integration trên chính kiểu implementation là cách xác nhận cấu trúc hierarchy cụ thể đang sử dụng.

Một cách khác là đổi tên hoặc signature các method thực sự có tiền điều kiện khác nhau, tránh buộc một implementation duy nhất đáp ứng hai contract khác nghĩa.

### 5.3. Khi nào không bị quy tắc song song?

Nếu `ChildContract extends ParentContract`, hai interface đó có **quan hệ kế thừa trực tiếp**, nên đây là một nhánh hierarchy, không phải hai interface độc lập. Constraint tham số khai báo ở `ParentContract` được áp dụng trên method triển khai ở class con; `ChildContract` không được bổ sung constraint trên method override.

Phân biệt này giúp tránh kết luận sai rằng “Java class triển khai hai interface thì luôn cấm parameter constraint”: chỉ những method có **chữ ký và hierarchy chồng chéo** với constraint ở các nhánh song song mới gặp vấn đề.

## 6. Ví dụ chạy được: Java 17 + Spring Boot 3.5 + JUnit

Phần này chứa một project Maven tối giản kiểm tra ràng buộc được **kế thừa đúng** trong service Spring và chứng minh các khai báo **không hợp lệ** bằng Jakarta `ExecutableValidator`. Nó dùng Java 17, Spring Boot 3.5.7 (Spring Framework 6.2) và namespace `jakarta.validation.*`.

Các file:

~~~text
pom.xml
src/main/java/com/example/demo/
  DemoApplication.java
  CodePolicy.java
  DefaultCodePolicy.java
src/test/java/com/example/demo/
  CodePolicyIntegrationTest.java
  HierarchyRulesTest.java
~~~

### 6.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-hierarchy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-validation` mang Bean Validation provider để thực thi constraint; `spring-boot-starter-aop` bảo đảm có AOP infrastructure cần cho service method validation; `spring-boot-starter-test` cung cấp JUnit 5, AssertJ và tiện ích kiểm thử khác. Không cần web server hay database.

### 6.2. Spring Boot application

~~~java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    // Test @SpringBootTest chỉ cần một @SpringBootApplication trên classpath.
}
~~~

### 6.3. Interface là nguồn hợp đồng

~~~java
// src/main/java/com/example/demo/CodePolicy.java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public interface CodePolicy {

    // Parameter constraint được khai báo đúng ở interface.
    String generate(@NotBlank String prefix);

    // Interface bảo đảm giá trị trả về khác null.
    @NotNull
    List<String> availableCodes();
}
~~~

Các annotation **trên tham số** và **giá trị trả về** được Jakarta Bean Validation provider tổng hợp cho method triển khai tương ứng.

### 6.4. Implementation chỉ bổ sung hậu điều kiện

~~~java
// src/main/java/com/example/demo/DefaultCodePolicy.java
package com.example.demo;

import jakarta.validation.constraints.Size;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
import java.util.List;

@Service
@Validated
public class DefaultCodePolicy implements CodePolicy {

    @Override
    public String generate(String prefix) {
        return prefix + "-1";
    }

    @Override
    @Size(min = 2, message = "Danh sách cần ít nhất hai mã")
    public List<String> availableCodes() {
        return List.of("A"); // Cố tình sai @Size để test return.
    }
}
~~~

Hai điều quan trọng:

1. `DefaultCodePolicy.generate` **không ghi lại `@NotBlank`**, nhưng người gọi qua Spring validation vẫn bị kiểm tra khi truyền chuỗi trống.
2. `DefaultCodePolicy.availableCodes` bổ sung `@Size(min=2)` hợp lệ. Constraint `@NotNull` trên `CodePolicy.availableCodes` vẫn tồn tại và tham gia validation.

`@Validated` trên bean service kích hoạt Spring method validation qua proxy. Việc gắn `@Validated` không thay đổi quy tắc thừa kế của Jakarta Validation; nó chỉ thiết lập **khi nào** các constraints được thực thi trong Spring.

### 6.5. Spring integration test

~~~java
// src/test/java/com/example/demo/CodePolicyIntegrationTest.java
package com.example.demo;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CodePolicyIntegrationTest {

    @Autowired
    CodePolicy service; // Bean nhận qua Spring, có method validation proxy.

    @Test
    void acceptsValidInheritedPrecondition() {
        assertEquals("ORD-1", service.generate("ORD"));
    }

    @Test
    void inheritedParameterConstraintIsEnforced() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.generate(" "));
        assertEquals(1, ex.getConstraintViolations().size());
    }

    @Test
    void additionalReturnConstraintIsEnforced() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                service::availableCodes);
        assertEquals(1, ex.getConstraintViolations().size());
    }

    @Test
    void parentNotNullStillAppliesWithoutRepeatAnnotation()
            throws Exception {
        DefaultCodePolicy target = new DefaultCodePolicy();
        Method method = DefaultCodePolicy.class
                .getMethod("availableCodes");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var errors = factory.getValidator()
                    .forExecutables()
                    .validateReturnValue(target, method, null);

            // @NotNull ở interface báo lỗi; @Size cho phép null.
            assertEquals(1, errors.size());
        }
    }
}
~~~

Ở test `service.generate(" ")`, không có annotation tại implementation parameter, nhưng vẫn có violation vì constraint được **kế thừa từ interface**. Ở test return, list có một phần tử nên `@Size(min=2)` bị vi phạm; `@NotNull` từ interface vẫn hợp lệ với list đó. Test cuối chủ động truyền `null` cho `ExecutableValidator.validateReturnValue(...)` để chứng minh `@NotNull` từ interface vẫn hoạt động, dù implementation không lặp annotation.

### 6.6. Test quy tắc sai bằng `ConstraintDeclarationException`

Tạo thêm file test này. Các class/interface bên trong test cố tình mô tả những tình huống sai, **không được đăng ký làm Spring beans**; test dùng `ExecutableValidator` để kiểm tra trực tiếp.

~~~java
// src/test/java/com/example/demo/HierarchyRulesTest.java
package com.example.demo;

import jakarta.validation.ConstraintDeclarationException;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HierarchyRulesTest {

    public interface PlainApi {
        String normalize(String value);
    }

    public static class IllegalOverride implements PlainApi {
        @Override
        public String normalize(@NotBlank String value) {
            return value;
        }
    }

    public interface StrictSender {
        void send(@NotBlank String text);
    }

    public interface PlainSender {
        void send(String text);
    }

    public static class IllegalParallel
            implements StrictSender, PlainSender {
        @Override
        public void send(String text) {
        }
    }

    public static class Customer {
        @NotBlank
        private final String name;

        public Customer(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public interface CustomerSource {
        @Valid
        Customer load();
    }

    public static class InheritedCascade implements CustomerSource {
        @Override
        public Customer load() {
            return new Customer("");
        }
    }

    public static class DuplicateCascade implements CustomerSource {
        @Override
        @Valid // Sai: supertype đã có @Valid trên return.
        public Customer load() {
            return new Customer("");
        }
    }

    @Test
    void addingParameterConstraintInOverrideIsIllegal()
            throws Exception {
        IllegalOverride target = new IllegalOverride();
        Method method = IllegalOverride.class
                .getMethod("normalize", String.class);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            assertThrows(
                    ConstraintDeclarationException.class,
                    () -> factory.getValidator().forExecutables()
                            .validateParameters(
                                    target, method, new Object[]{"ABC"}));
        }
    }

    @Test
    void parameterConstraintAcrossParallelInterfacesIsIllegal()
            throws Exception {
        IllegalParallel target = new IllegalParallel();
        Method method = IllegalParallel.class
                .getMethod("send", String.class);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            assertThrows(
                    ConstraintDeclarationException.class,
                    () -> factory.getValidator().forExecutables()
                            .validateParameters(
                                    target, method, new Object[]{"ABC"}));
        }
    }

    @Test
    void inheritedReturnCascadeStillWorks() throws Exception {
        InheritedCascade target = new InheritedCascade();
        Method method = InheritedCascade.class.getMethod("load");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var violations = factory.getValidator()
                    .forExecutables()
                    .validateReturnValue(target, method, target.load());

            assertEquals(1, violations.size());
        }
    }

    @Test
    void repeatingReturnCascadeInOverrideIsIllegal()
            throws Exception {
        DuplicateCascade target = new DuplicateCascade();
        Method method = DuplicateCascade.class.getMethod("load");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            assertThrows(
                    ConstraintDeclarationException.class,
                    () -> factory.getValidator().forExecutables()
                            .validateReturnValue(
                                    target, method, target.load()));
        }
    }
}
~~~

**Lưu ý về phạm vi của test:** `IllegalOverride` và `IllegalParallel` cố ý có metadata không hợp lệ. Spring Boot không quét chúng thành `@Component`, vì vậy việc khởi tạo context cho service hợp lệ vẫn độc lập. Trong test, exception có thể xảy ra khi provider phân tích metadata của method để thực thi `validateParameters`/`validateReturnValue`; các khối `assertThrows` kiểm tra chính hợp đồng đó.

Chạy toàn bộ:

~~~bash
mvn test
~~~

Kỳ vọng: **8 test PASS** (4 test tích hợp Spring, 4 test `ExecutableValidator`), không có assertion failures khi dự án có dependencies đúng. Kết quả này là kỳ vọng theo semantics của Jakarta Validation và Spring Boot, không phải lời khẳng định đã thực thi Maven trên máy của bạn. Không ghi nguyên văn stdout/log Maven vì chúng phụ thuộc môi trường.

## 7. Các trường hợp phải suy xét kỹ

### 7.1. Interface con kế thừa interface cha

~~~java
interface BaseApi {
    void update(@NotBlank String id);
}

interface ExtendedApi extends BaseApi {
    // Chỉ thừa kế update, không khai báo lại constraint.
}

class ExtendedApiImpl implements ExtendedApi {
    @Override
    public void update(String id) {
        // ...
    }
}
~~~

Đây là một chuỗi kế thừa, khác hai interface song song độc lập. Constraint từ `BaseApi` tiếp tục có hiệu lực. Nếu `ExtendedApi` khai báo lại `update(@NotBlank String id)`, đó vẫn là method override có parameter constraint mới nên không portable theo chuẩn.

### 7.2. Overload không phải override

~~~java
class Encoder {
    String encode(String value) {
        return value;
    }

    String encode(@NotBlank String value, int mode) {
        return mode + ":" + value;
    }
}
~~~

Hai method có **khác số lượng tham số**, nên là overload. Mỗi signature có hợp đồng riêng. Constraint của overload mới không tăng tiền điều kiện của method `encode(String)` đã tồn tại. Nhưng nếu subtype override một overload đã có trong supertype, quy tắc method override vẫn áp dụng cho chính signature đó.

### 7.3. Covariant return và Java visibility

Java override yêu cầu kiểu trả về compatible/covariant và không được giảm visibility của method. Jakarta Validation **không thay thế** các quy tắc biên dịch Java này: trước tiên code phải compile như một override hợp lệ, sau đó provider mới xử lý constraints.

Khi return type được thu hẹp từ `Object` sang subtype, constraints từ method supertype vẫn được xét khi validate instance subtype. Khi thay đổi API, test riêng kiểu trả về mới và các return constraints từ tất cả supertypes liên quan.

### 7.4. Constructor không có thừa kế hợp đồng theo override

~~~java
class BaseJob {
    BaseJob(@NotNull String name) {
    }
}

class DetailedJob extends BaseJob {
    DetailedJob(String name, @Min(1) int priority) {
        super(name);
    }
}
~~~

`DetailedJob` không override constructor của `BaseJob`. Theo Jakarta Validation, khi `validateConstructorParameters(...)` được gọi trên constructor của `DetailedJob`, **chỉ constraints khai báo trực tiếp trên constructor đó** được dùng. `@NotNull` của constructor `BaseJob` không tự chuyển thành parameter constraint trên constructor con. Tương tự, constructor return validation áp dụng constraints trực tiếp trên constructor đang được xét.

Đây là metadata validation, không phải lời khẳng định `super(name)` không chạy: Java vẫn gọi constructor cha theo cơ chế object construction.

### 7.5. Cross-parameter constraint và container element

Một constraint liên tham số đặt trên method có `ValidationTarget.PARAMETERS` được xem là **tiền điều kiện**. Không thêm nó ở method override để yêu cầu subtype phải đáp ứng quy tắc mới. Tương tự, `@Valid` hoặc `@NotNull` trong phần tử type argument của parameter cũng là phần hợp đồng input.

Ví dụ annotation đúng ở interface, không lặp trong implementation:

~~~java
interface BatchWriter {
    void write(List<@NotBlank String> names);
}

class BatchWriterImpl implements BatchWriter {
    @Override
    public void write(List<String> names) {
        // ...
    }
}
~~~

Ở đây validation của container element được khai báo ở interface. Provider cần extractor cho container, nhưng `List` đã được hỗ trợ phổ biến. Lưu ý chỉ `@NotBlank` trên element không cấm `names == null`; nếu danh sách bắt buộc, thêm `@NotNull` **trên parameter ở interface**.

### 7.6. Validation groups

Những constraint trong một nhóm tùy chỉnh như `UpdateGroup` chỉ chạy khi group đó được yêu cầu. Điều này không thay đổi quy tắc khai báo hierarchy: subtype **không được thêm parameter constraint** ngay cả khi nó thuộc group mà ứng dụng “hiếm khi” gọi.

Khi cần groups khác nhau cho use case, định nghĩa contract riêng hoặc cấu trúc nhóm ở nguồn khai báo hợp đồng. Đừng dùng `@Validated(SomeGroup.class)` trên subclass như cách lách việc thêm `@NotBlank(groups=SomeGroup.class)` lên overridden parameter; provider vẫn có thể xem declaration đó là vi phạm.

### 7.7. Getters và property validation

`@NotNull` trên một getter có thể được hiểu là constraint cho JavaBean property khi dùng `Validator#validate(bean)`, đồng thời method có thể được kiểm tra bằng `ExecutableValidator#validateReturnValue(...)`. Hai cách validate có **phạm vi và lifecycle khác nhau**; không gọi cả hai rồi cộng số lỗi nếu không hiểu chúng có thể chạm cùng một ràng buộc.

Với method override, provider thu thập constraints từ hierarchy. Nếu thiết kế vừa field-level vừa getter-level cho cùng dữ liệu, cần test để tránh các báo lỗi trùng không mong muốn.

### 7.8. Spring proxy không làm mất hoặc sửa hợp đồng hierarchy

Trong Spring Framework, service `@Validated` thường được kiểm tra qua Spring AOP proxy. Violation đầu vào có thể trở thành `ConstraintViolationException`; khi không có proxy, lời gọi trực tiếp `new` hoặc self-invocation `this.method(...)` thường không được chặn. Spring Boot 3.x với `MethodValidationPostProcessor` có cấu hình adaptation riêng, nên tùy trường hợp exception có thể khác.

**Quy tắc kế thừa vẫn thuộc Jakarta Validation**, không do Spring tùy ý cho phép parameter constraint trên override. Dù class biên dịch hoặc Spring context chạy được, hãy test với validator thật trên chính method để kiểm tra metadata.

Riêng controller Spring MVC 6.1+, có built-in handler method validation và `HandlerMethodValidationException`; `@Validated` cấp class có thể chuyển controller sang AOP method validation. Các lựa chọn framework tác động **điểm kích hoạt và cách báo lỗi**, không làm thay đổi quy tắc LSP của Bean Validation.

## 8. Tùy chọn Hibernate Validator nới lỏng quy tắc: dùng rất thận trọng

Hibernate Validator cung cấp **các tùy chọn đặc thù provider** có thể nới quy tắc mặc định:

- `hibernate.validator.allow_parameter_constraint_override`: cho phép constraint tham số trên override.
- `hibernate.validator.allow_parallel_method_parameter_constraint`: cho phép parameter constraints từ nhánh song song.
- `hibernate.validator.allow_multiple_cascaded_validation_on_result`: cho phép lặp cascade trên return.

Các cờ này mặc định **false** khi tuân thủ quy tắc chuẩn. Có thể cấu hình thông qua `validation.xml` hoặc API bootstrap riêng của Hibernate Validator. Khi bật, ứng dụng không còn hoàn toàn portable giữa Jakarta Validation providers; những khác biệt về việc tập hợp constraint, inheritance và group conversion phải được kiểm tra theo đúng phiên bản provider.

Nếu mục tiêu là một thư viện Java/Spring có thể dùng rộng rãi, hãy **sửa interface/hierarchy** để đúng Jakarta Validation thay vì bật cờ nới lỏng. Chỉ cân nhắc extension khi đang duy trì hệ thống legacy, hiểu rõ tác động, có test bao phủ phương thức từ các kiểu caller khác nhau và chấp nhận phụ thuộc Hibernate Validator.

## 9. Chẩn đoán `ConstraintDeclarationException`

Một tình huống phổ biến: ứng dụng chạy tới request hoặc test validation, rồi báo lỗi có nhắc đến overriding method, parallel interfaces hoặc multiple cascaded return values. Cách xử lý tuần tự:

1. **Xác định method signature** trong exception: tên method và danh sách tham số, không chỉ tên class được log.
2. **Kiểm tra tất cả supertypes** có khai báo/implement cùng signature: interfaces, superclass, interface cha. Với cấu trúc song song, cần xem cả hai nhánh.
3. **Tách parameter và return**: annotation ở method return thường hợp lệ khi bổ sung; annotation trên overridden parameter thì không.
4. **Tìm `@Valid` lặp** trên return dọc nhánh kế thừa; tìm `@Valid` trên overridden parameter; xem thêm `@ConvertGroup` liên quan.
5. **Tìm container element/cross-parameter constraint** dù không thấy `@NotNull` trực tiếp trên parameter.
6. **Sửa tại nguồn hợp đồng**: chuyển parameter constraint lên supertype thích hợp; bỏ annotation ở override; hợp nhất các interface song song khi cần.
7. **Test với `ExecutableValidator`** trên concrete class và method thực tế; gọi `validateParameters(...)` và `validateReturnValue(...)` để xác nhận metadata.
8. **Test Spring integration** nếu ứng dụng dùng `@Validated`: bảo đảm lời gọi qua proxy hoặc handler MVC và kiểm tra exception mapping tại tầng HTTP.

Đừng nhầm `ConstraintDeclarationException` (khai báo/hierarchy của constraint không hợp lệ) với `ConstraintViolationException` (constraint hợp lệ nhưng dữ liệu thực tế không thỏa). Hai exception cần hướng xử lý khác nhau: lỗi khai báo phải được developer sửa trong code/config; lỗi dữ liệu có thể được trả về caller bằng thông báo phù hợp.

## 10. Các lỗi thiết kế thường gặp

1. **Lặp lại `@NotBlank` ở implementation vì muốn “tài liệu hóa” interface**: vẫn không hợp lệ theo chuẩn. Viết JavaDoc ở implementation nếu cần ghi rõ, để constraint ở contract.
2. **Không thấy annotation tại implementation nên cho rằng ràng buộc đã mất**: provider tổng hợp từ hierarchy; hãy dùng `ExecutableValidator` để kiểm tra.
3. **Đặt `@Valid` trên parameter override vì chỉ muốn cascade sâu hơn**: đó là thay đổi tiền điều kiện; đặt đúng trên khai báo gốc.
4. **Hai interface có cùng method và một nhánh có parameter constraint**: cấu trúc song song có thể không hợp lệ dù implementation không thêm gì.
5. **Lặp `@Valid` return ở cả base và override**: rule cấm double cascaded return trên một nhánh; xóa `@Valid` ở override.
6. **Đổi `@NotNull` return sang `@NotBlank` rồi nghĩ đã thay thế ràng buộc cũ**: return constraints từ base vẫn còn; constraint mới được thêm.
7. **Tạo hai return constraints đối nghịch**: có thể không có kết quả nào hợp lệ. Bổ sung phải phù hợp logic nghiệp vụ.
8. **Trông chờ compile báo lỗi Jakarta Validation**: lỗi hierarchy thường do provider ném lúc đọc metadata/validate, không phải Java compiler mặc định.
9. **Trộn `javax.validation.*` với Spring Boot 3.x**: Boot 3 dùng `jakarta.validation.*` và provider tương thích.
10. **Quên điểm kích hoạt method validation trong Spring**: proxy, `@Validated` và bean lifecycle phải được thiết lập. Annotation của Jakarta không tự ném lỗi khi gọi Java method.
11. **Bật Hibernate Validator extension để “sửa nhanh”**: có thể phá tính di động và nguyên lý thay thế. Ưu tiên sửa hợp đồng API.
12. **Hiểu nhầm constructor override**: constructor không được kế thừa theo cơ chế method override; chỉ constraints trực tiếp trên constructor được xét.

## 11. Checklist review pull request

- [ ] Constraints trên parameter (kể cả `@Valid`, container elements, cross-parameter) được khai báo ở nơi thiết kế hợp đồng đầu vào phù hợp, **không thêm trên override**.
- [ ] Không có phương thức chung của các interface song song mang parameter constraints trong hierarchy không tương thích.
- [ ] Return constraints mới ở implementation bổ sung được cho constraints của supertypes, không mâu thuẫn logic.
- [ ] Return `@Valid` chỉ được khai báo một lần trên cùng nhánh; các group conversions không làm biến đổi không hợp lệ hợp đồng inherited cascade.
- [ ] Đã phân biệt overload với override và constructor với method.
- [ ] Có test `ExecutableValidator` kiểm tra metadata hợp lệ/sai, không chỉ test các case dữ liệu bình thường.
- [ ] Với Spring, test gọi bean được quản lý qua proxy và kiểm tra trường hợp parameter/return; không kết luận từ `new` hoặc self-invocation.
- [ ] Không cần bật cờ nới lỏng đặc thù Hibernate Validator để chạy đúng hợp đồng chuẩn.

## Tài liệu tham khảo

- Jakarta Validation 3.1 Specification, `5.6.5 “Method constraints in inheritance hierarchies”: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#method-constraints-in-inheritance-hierarchies
- Hibernate Validator Reference Guide, `3.1.4 “Method constraints in inheritance hierarchies”: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-method-constraints-inheritance
- Hibernate Validator Reference Guide, “Relaxation of requirements for method validation in class hierarchies”: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-method-validation-configuration
- Spring Boot 3.5 Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Framework 6.2 Method Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
