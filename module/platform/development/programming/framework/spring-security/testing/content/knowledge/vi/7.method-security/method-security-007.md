# Biểu thức SpEL, tên tham số và tùy chọn biên dịch -parameters

## 1. Vì sao tên tham số ảnh hưởng đến quyết định phân quyền?

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive. Nhiều chính sách không chỉ phụ thuộc role hay authority của người gọi mà còn phụ thuộc vào **đối số cụ thể** được truyền cho service.

Ví dụ: một người dùng có authority document:read chỉ được đọc tài liệu thuộc tenant của mình; người có invoice:approve chỉ được duyệt hóa đơn thuộc chi nhánh được cấp quyền. Để viết chính sách gần với nghiệp vụ, ta muốn biểu thức SpEL tham chiếu được tham số như #documentId, #tenantId hoặc #invoice.

Spring Security cần biết tên tham số ở runtime để ánh xạ các biến đó. Tên trong source code không tự động luôn có sẵn trong bytecode. Tùy phiên bản Spring Framework/Spring Security và cách biên dịch, bạn có thể dùng:

- Tên tham số được ghi vào metadata bằng tùy chọn javac -parameters.
- Annotation @P của Spring Security để đặt tên rõ ràng.
- Annotation @Param của Spring Data khi thư viện này có trên classpath.
- Bí danh theo vị trí như #p0 và #a0 khi không cần tên tham số.

Sau bài này, bạn có thể:

- Hiểu cách DefaultSecurityParameterNameDiscoverer tìm tên tham số cho biểu thức method security.
- Cấu hình Maven hoặc Gradle để biên dịch với -parameters.
- Dùng @P và Spring Data @Param khi cần tên rõ ràng, kể cả trên interface.
- Phân biệt tên tham số, vị trí tham số và các biến đặc biệt như authentication, principal, returnObject, filterObject.
- Kiểm thử biểu thức với @WithMockUser, MockMvc và WebTestClient.
- Chẩn đoán lỗi sau khi nâng lên Spring Framework 6.1+, khi debug symbols không còn là phương án dự phòng để tìm tên tham số.

> **Phạm vi phiên bản:** Ví dụ chính sử dụng Spring Security 6.5.x, Spring Framework 6.2.x và Spring Boot 3.x. Spring Framework 6.1 đã loại bỏ LocalVariableTableParameterNameDiscoverer, vì vậy khi biểu thức dùng tên tham số mà không có annotation đặt tên, hãy biên dịch với -parameters. Với Spring Security 7.1, annotation P cũ trong package org.springframework.security.access.method đã bị đánh dấu deprecated để chuyển sang org.springframework.security.core.parameters.P; phần dưới nêu rõ khác biệt import theo phiên bản.

## 2. SpEL trong method security nhìn thấy những gì?

Các annotation @PreAuthorize, @PostAuthorize, @PreFilter và @PostFilter dùng biểu thức SpEL. Biểu thức được đánh giá trong ngữ cảnh method invocation, nơi Spring Security cung cấp thông tin về authentication, đối số và kết quả.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('document:read') and #documentId != null")
public DocumentView read(String documentId) {
    // ...
}
~~~

Biểu thức có hai điều kiện:

1. Authentication phải có đúng authority document:read.
2. Biến #documentId phải có giá trị khác null.

Dấu # trước tên tham số có ý nghĩa: đây là một biến trong EvaluationContext. Nếu Spring Security không tìm được tên documentId từ metadata hoặc annotation, biểu thức không thể sử dụng tên đó như mong đợi.

Các biến và đối tượng thường gặp:

| Cú pháp | Ý nghĩa |
|---|---|
| #documentId | Giá trị của tham số có tên documentId, nếu tên đó được discover. |
| #p0 | Tham số thứ nhất theo vị trí, chỉ số bắt đầu từ 0. |
| #a0 | Bí danh theo vị trí của tham số thứ nhất; tương đương #p0 trong ngữ cảnh này. |
| authentication | Đối tượng Authentication hiện tại. |
| principal | Principal gắn với Authentication. |
| returnObject | Giá trị trả về được dùng trong @PostAuthorize. |
| filterObject | Phần tử hiện tại được xét trong @PreFilter/@PostFilter. |
| @documentPolicy | Bean Spring có tên documentPolicy, có thể gọi method trong SpEL. |

Không phải mọi biến đều dùng được ở mọi annotation. Ví dụ returnObject chỉ có ý nghĩa ở bước hậu kiểm; filterObject dùng khi lọc phần tử. Tên tham số method được dùng khi biểu thức cần truy cập đầu vào.

Một số ví dụ ngắn:

~~~java
// Dựa trên tham số có tên documentId.
@PreAuthorize("hasAuthority('document:read') and #documentId != null")

// Dựa trên tham số đầu tiên, không phụ thuộc tên trong bytecode.
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")

// Dựa trên cả hai tham số theo tên.
@PreAuthorize("#tenantId == authentication.name and #operation == 'READ'")

// Kết hợp tham số đầu vào và đối tượng trả về.
@PostAuthorize("returnObject.owner == #username")
~~~

SpEL là một phần của cấu hình bảo mật, không phải nơi ghép chuỗi tùy ý từ request. Không tạo expression bằng cách nối trực tiếp dữ liệu client gửi vào chuỗi SpEL để thực thi; giữ expression tĩnh trong annotation hoặc cấu hình có kiểm soát.

## 3. Spring Security tìm tên tham số như thế nào?

Spring Security sử dụng **DefaultSecurityParameterNameDiscoverer** để tìm tên tham số cho method security. Trong Spring Security 6.5, tài liệu mô tả các cách chính theo thứ tự:

1. Nếu một tham số có annotation @P của Spring Security, giá trị trong annotation được dùng làm tên tham số.
2. Nếu có annotation @Param của Spring Data trên tham số, giá trị trong annotation được dùng.
3. Nếu code được biên dịch với -parameters, Spring dùng Java reflection API để đọc tên tham số. Cách này hoạt động cho cả class và interface.
4. Trong các tổ hợp framework cũ còn hỗ trợ, tên tham số có thể được tìm từ debug symbols. Tuy nhiên, Spring Framework 6.1 đã loại bỏ LocalVariableTableParameterNameDiscoverer; vì vậy không dựa vào debug symbols như một fallback cho ứng dụng Spring Framework 6.1+.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Method Security cần tên tham số"] --> B{"Có @P trên tham số?"}
    B -- "Có" --> C["Dùng tên trong @P"]
    B -- "Không" --> D{"Có Spring Data @Param?"}
    D -- "Có" --> E["Dùng tên trong @Param"]
    D -- "Không" --> F{"Bytecode có -parameters?"}
    F -- "Có" --> G["Đọc tên bằng Java reflection"]
    F -- "Không" --> H["Phiên bản cũ có thể thử debug symbols"]
    H --> I["Spring Framework 6.1+ không còn fallback LVT"]
~~~

**Khuyến nghị thực tế:** Với Spring Framework 6.1 trở lên, hãy bật -parameters cho các module Java có method security expression dùng tên tham số. Nếu muốn tên biểu thức ổn định dù đổi tên biến Java hoặc khi khai báo method trên interface, dùng @P cho các tham số được tham chiếu.

Không nhầm việc IDE hiển thị được tên biến trong debugger với việc Java reflection có thể đọc tên tham số. Debugger có thể sử dụng thông tin debug riêng; Spring Framework 6.1+ cần metadata phù hợp hoặc annotation hỗ trợ.

## 4. Bật tùy chọn biên dịch -parameters

Tùy chọn -parameters yêu cầu compiler lưu tên tham số vào metadata của class file. Khi runtime gọi Parameter.getName(), Java có thể trả tên gốc và Parameter.isNamePresent() trả true.

### 4.1. Maven

Với Maven, cấu hình maven-compiler-plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Nếu dự án đã quản lý phiên bản plugin qua Spring Boot parent hoặc pluginManagement, không cần thêm version riêng trừ khi dự án yêu cầu. Điểm quan trọng là cấu hình parameters phải được áp dụng cho compile phase của mã nguồn chính, nơi chứa các service có annotation bảo mật.

### 4.2. Gradle Kotlin DSL

Trong build.gradle.kts:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

### 4.3. Gradle Groovy DSL

Trong build.gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Đặt cấu hình ở module chứa các class được bảo vệ. Trong multi-module build, bật flag ở module chứa service/interface có method security annotation; chỉ bật ở module test không làm metadata của service đã biên dịch tự xuất hiện.

Sau khi đổi compiler option, cần biên dịch lại class liên quan để tạo metadata mới. Khi build incremental hoặc IDE có output cũ, hãy chạy clean build phù hợp với dự án để tránh kiểm tra nhầm bytecode cũ.

### 4.4. Kiểm tra metadata ở runtime

Có thể kiểm tra bằng Java reflection:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

import org.junit.jupiter.api.Test;

class ParameterMetadataTest {

    @Test
    void compilerPreservesMethodParameterNames() throws Exception {
        Method method = DocumentService.class
            .getMethod("readByName", String.class);

        Parameter parameter = method.getParameters()[0];

        assertTrue(parameter.isNamePresent());
        assertEquals("documentId", parameter.getName());
    }
}
~~~

Test này chỉ kiểm tra bytecode có lưu tên hay không. Nó chưa chứng minh SpEL hoặc method security đã sử dụng tên đó. Để chứng minh toàn bộ đường đi, cần một test gọi bean Spring thật và xác nhận expression cho phép đúng tham số, từ chối tham số không phù hợp.

## 5. Dùng @P để đặt tên tường minh

Annotation @P của Spring Security cho phép gán alias rõ ràng cho một tham số. Điều này hữu ích khi:

- Không thể kiểm soát compiler flags của module hoặc thư viện.
- Method được khai báo trên interface cần tên tham số ổn định.
- Muốn giữ tên biến trong Java khác với tên dùng trong policy.
- Muốn expression không phụ thuộc vào việc refactor tên biến Java.

### 5.1. Import theo phiên bản Spring Security

Với Spring Security 6.5.x, dùng:

~~~java
import org.springframework.security.access.method.P;
~~~

Ví dụ:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('document:read') and #id != null")
public DocumentView read(@P("id") String documentId) {
    // ...
}
~~~

Trong expression, tên được sử dụng là #id, dù tên biến Java là documentId.

Với Spring Security 7.1, org.springframework.security.access.method.P đã deprecated; dùng package mới:

~~~java
import org.springframework.security.core.parameters.P;
~~~

Annotation vẫn có cùng mục đích:

~~~java
@PreAuthorize("hasAuthority('document:read') and #id != null")
public DocumentView read(@P("id") String documentId) {
    // ...
}
~~~

Khi dự án nâng phiên bản, không đổi import một cách máy móc nếu version thực tế chưa cung cấp class mới. Hãy theo Javadoc của đúng artifact Spring Security đang dùng.

### 5.2. Nhiều tham số cần tên tường minh

Nếu expression tham chiếu nhiều tham số, nên đặt alias cho từng tham số được sử dụng:

~~~java
// Import P từ package phù hợp với phiên bản Spring Security.
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "#tenant == authentication.name and " +
    "#documentId != null"
)
public DocumentView read(
        @P("tenant") String tenantId,
        @P("documentId") String id) {
    // ...
}
~~~

Trong ví dụ, tên expression là tenant và documentId; tên biến Java là tenantId và id. Cách đặt alias làm rõ hợp đồng giữa annotation và phương thức.

Một chi tiết cần chú ý: cơ chế discoverer dựa trên annotation có thể giải quyết tên cho method theo tập annotation được hỗ trợ. Nếu chỉ một tham số được gắn @P trong khi expression còn dùng tên của tham số khác, tên còn lại có thể không được discover theo cách bạn mong đợi. Cách an toàn là gắn alias cho mọi tham số cần tham chiếu, hoặc dùng -parameters để cung cấp đầy đủ tên cho method.

## 6. Dùng Spring Data @Param khi có Spring Data

Nếu ứng dụng đã có Spring Data, DefaultSecurityParameterNameDiscoverer cũng nhận biết annotation @Param từ Spring Data:

~~~java
import org.springframework.data.repository.query.Param;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("#owner == authentication.name")
Document findContactByOwner(@Param("owner") String ownerName);
~~~

Trong expression, tên được dùng là #owner, dù tên biến Java là ownerName.

Không thêm Spring Data chỉ để lấy @Param nếu ứng dụng không dùng nó. Với một service không có Spring Data, dùng @P hoặc -parameters là lựa chọn phù hợp hơn. Tránh import nhầm một annotation Param có cùng tên từ thư viện khác; Spring Security chỉ hỗ trợ các annotation parameter name đã được discoverer cấu hình nhận diện.

## 7. Bí danh theo vị trí: #p0 và #a0

Khi không cần đặt tên theo nghiệp vụ, biểu thức có thể truy cập đối số theo chỉ số bắt đầu từ 0:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public DocumentView read(String id) {
    // ...
}
~~~

Hoặc:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #a0)")
public DocumentView read(String id) {
    // ...
}
~~~

#p0 và #a0 cùng chỉ tham số thứ nhất. Với phương thức nhiều tham số, #p1/#a1 là tham số thứ hai, #p2/#a2 là tham số thứ ba.

| Tham số method | Bí danh theo vị trí |
|---|---|
| Tham số thứ nhất | #p0 hoặc #a0 |
| Tham số thứ hai | #p1 hoặc #a1 |
| Tham số thứ ba | #p2 hoặc #a2 |

Ưu điểm của cách này là không cần tên tham số được lưu trong bytecode. Nhược điểm là expression gắn với thứ tự tham số; nếu thêm hoặc đổi vị trí tham số, policy có thể trở nên khó đọc hoặc trỏ nhầm giá trị. Với nghiệp vụ có ý nghĩa rõ ràng như documentId, tenantId, ownerId, tên tham số hoặc @P thường dễ bảo trì hơn.

Không dùng #p0 để né việc hiểu chữ ký method. Khi method có nhiều tham số cùng kiểu String, chỉ số vị trí rất dễ khiến người đọc nhầm id nào đang được kiểm tra.

## 8. Ví dụ hoàn chỉnh: policy theo documentId

Ví dụ này kết hợp named parameter, @P, policy bean và test trực tiếp. Dữ liệu chủ sở hữu được tra cứu ở phía server; không tin ownerId do client tự gửi.

Trước hết, bật method security trong application context:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

### 8.1. Model và policy bean

~~~java
// DocumentView.java
public class DocumentView {

    private final String id;
    private final String owner;

    public DocumentView(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }
}
~~~

~~~java
// DocumentPolicy.java
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final Map<String, String> ownerByDocument = Map.of(
        "doc-1", "alice",
        "doc-2", "bob"
    );

    public boolean canRead(Authentication authentication, String documentId) {
        if (authentication == null || documentId == null) {
            return false;
        }

        String owner = ownerByDocument.get(documentId);
        return owner != null && owner.equals(authentication.getName());
    }
}
~~~

### 8.2. Service dùng -parameters

Phương thức đầu tiên dựa vào tên Java documentId được lưu nhờ compiler flag:

~~~java
// DocumentService.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public DocumentView readByName(String documentId) {
        return new DocumentView(documentId, "alice");
    }
}
~~~

Để expression #documentId hoạt động, class DocumentService phải được biên dịch với -parameters. Nếu không có metadata và không có annotation đặt tên, Spring Framework 6.1+ không thể lấy tên từ LocalVariableTable như các phiên bản cũ.

### 8.3. Service dùng @P

Phương thức thứ hai đặt tên expression độc lập với tên biến Java:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ExplicitDocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #id)"
    )
    public DocumentView read(@P("id") String rawDocumentKey) {
        return new DocumentView(rawDocumentKey, "alice");
    }
}
~~~

Import ở trên dành cho Spring Security 6.5.x. Nếu dự án dùng Spring Security 7.1+, chuyển import sang org.springframework.security.core.parameters.P.

Trong ví dụ, #id là alias được đặt bởi @P("id"); rawDocumentKey là tên Java và không cần trùng với alias.

## 9. Kiểm thử bằng @WithMockUser

Test cần gọi service do Spring inject để đi qua method-security proxy. Các test dưới đây chứng minh cùng một biểu thức xử lý đúng tham số và principal.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentParameterSecurityTest {

    @Autowired
    DocumentService documents;

    @Autowired
    ExplicitDocumentService explicitDocuments;

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void namedParameterAllowsAliceToReadOwnedDocument() {
        DocumentView result = documents.readByName("doc-1");

        assertEquals("doc-1", result.getId());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void namedParameterDeniesDifferentOwner() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readByName("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void namedParameterDeniesMissingAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readByName("doc-1"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void explicitAliasAllowsAliceToReadOwnedDocument() {
        DocumentView result = explicitDocuments.read("doc-1");

        assertEquals("doc-1", result.getId());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void explicitAliasDeniesDifferentOwner() {
        assertThrows(AccessDeniedException.class,
            () -> explicitDocuments.read("doc-1"));
    }
}
~~~

Các test này có hai lớp bằng chứng:

- Test readByName kiểm chứng tên documentId được discover từ bytecode khi compile với -parameters.
- Test ExplicitDocumentService kiểm chứng alias id được cung cấp bởi @P, không phụ thuộc tên biến Java rawDocumentKey.

Nếu expression bị đổi thành #wrongName hoặc compiler flag bị bỏ khỏi module service, test tương ứng phải thất bại. Đó là cách kiểm tra cấu hình thật thay vì chỉ nhìn build.gradle hoặc pom.xml.

### Kiểm thử bằng bí danh vị trí

Có thể thêm method sử dụng #p0:

~~~java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #p0)"
)
public DocumentView readByPosition(String key) {
    return new DocumentView(key, "alice");
}
~~~

Sau đó dùng @WithMockUser(username = "alice", authorities = "document:read") để gọi readByPosition("doc-1") thành công, và principal bob để xác nhận bị từ chối. Phép thử này cho thấy #p0 không cần tên tham số được lưu.

## 10. Dùng tham số với @PostAuthorize, @PreFilter và @PostFilter

Parameter discovery không chỉ dành cho @PreAuthorize.

### 10.1. @PostAuthorize

Biểu thức có thể kết hợp tham số đầu vào và giá trị trả về:

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name and " +
    "returnObject.id == #documentId"
)
public DocumentView readDocument(String documentId) {
    // ...
}
~~~

Ở đây returnObject là kết quả trả về; #documentId là tham số method. Tên documentId phải được discover bằng -parameters, @P hoặc cơ chế tương ứng. Nếu chỉ muốn tham chiếu vị trí, có thể dùng #p0.

### 10.2. @PreFilter và filterTarget

Khi method có nhiều collection, filterTarget xác định collection nào cần lọc:

~~~java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public void importDocuments(
        List<Document> documents,
        List<String> labels) {
    // ...
}
~~~

Nếu dùng tên documents trong filterTarget, Spring cần discover được tên tham số đó. Bật -parameters hoặc đặt tên bằng @P theo đúng phiên bản. Khi dùng nhiều tham số có annotation tên, hãy bảo đảm tất cả tham số mà framework cần nhận diện đều có tên rõ ràng.

### 10.3. @PostFilter

@PreFilter/@PostFilter dùng filterObject cho phần tử đang xét; chúng không thay #documentId bằng một biến tên tham số. Tuy vậy, method vẫn có thể dùng tên tham số trong biểu thức nếu chính sách cần kết hợp đầu vào với phần tử:

~~~java
@PostFilter(
    "filterObject.tenantId == #tenantId and " +
    "filterObject.owner == authentication.name"
)
public List<Document> findVisible(String tenantId) {
    // ...
}
~~~

Ở đây #tenantId là tham số method và filterObject là phần tử kết quả hiện tại. Cả hai nguồn dữ liệu cần được kiểm tra theo chính sách; không giả định việc lọc phần tử tự động bảo vệ mọi thông tin khác.

## 11. MockMvc và WebTestClient: tham số đến từ request

Trong một request HTTP, controller nhận path variable hoặc request parameter rồi chuyển giá trị vào service. Parameter discovery xảy ra trên **method được bảo vệ**, không dựa vào tên biến trong URL.

Ví dụ controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/documents")
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{id}")
    public DocumentView read(@PathVariable String id) {
        return documents.readByName(id);
    }
}
~~~

MockMvc kiểm tra service nhận đúng id và biểu thức SpEL đánh giá đúng:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentParameterHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerCanReadDocument() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("alice").authorities(
                    new org.springframework.security.core.authority.SimpleGrantedAuthority(
                        "document:read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("doc-1"));
    }

    @Test
    void anotherUserGetsForbidden() throws Exception {
        mvc.perform(get("/documents/doc-1")
                .with(user("bob").authorities(
                    new org.springframework.security.core.authority.SimpleGrantedAuthority(
                        "document:read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Các status giả định HTTP filter chain cho request tới controller và service thật có method security. Nếu URL policy chặn trước controller, test 403 không chứng minh tham số đã được truyền tới service; hãy kết hợp test service trực tiếp.

Trên WebFlux, nguyên tắc parameter discovery cũng áp dụng cho method được bảo vệ. Reactive SecurityContext được truyền qua Reactor Context, nên dùng WebTestClient với mockUser để kiểm thử request và subscription:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Mono<DocumentView> read(@P("documentId") String id) {
        return Mono.just(new DocumentView(id, "alice"));
    }
}
~~~

Trong ví dụ Reactive với Spring Security 6.5.x, import @P theo package org.springframework.security.access.method.P. Khi dùng Spring Security 7.1+, dùng package mới org.springframework.security.core.parameters.P. Phần test WebTestClient cần một WebFlux controller gọi ReactiveDocumentService và SecurityWebFilterChain phù hợp; dùng mockUser("alice").authorities(...) cho ca được phép và mockUser("bob") cho ca bị từ chối.

Ví dụ cấu hình và controller tối thiểu cho một ứng dụng WebFlux riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchange -> exchange
            .anyExchange().permitAll()).build();
    }
}
~~~

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveDocumentController {

    private final ReactiveDocumentService documents;

    public ReactiveDocumentController(ReactiveDocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/reactive/documents/{id}")
    public Mono<DocumentView> read(@PathVariable String id) {
        return documents.read(id);
    }
}
~~~

Test tích hợp WebTestClient:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class ReactiveDocumentParameterTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void ownerCanRead() {
        client.mutateWith(mockUser("alice").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-1");
    }

    @Test
    void anotherUserIsDenied() {
        client.mutateWith(mockUser("bob").authorities(
                new SimpleGrantedAuthority("document:read")))
            .get().uri("/reactive/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Ở đây permitAll() chỉ giúp request đi tới controller để cô lập method authorization trong bài học; nó không bỏ qua @EnableReactiveMethodSecurity. Ứng dụng thực tế cần SecurityWebFilterChain theo yêu cầu riêng.

Đừng gọi Mono rồi bỏ đó trong test trực tiếp: publisher cần được subscribe để quyết định method security Reactive được thực thi trong Reactor Context phù hợp. WebTestClient tự subscribe khi exchange; test service thuần có thể dùng StepVerifier với security context được thiết lập cho test.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| #documentId không được đánh giá như mong đợi. | Bytecode không có tên tham số và method không có annotation đặt tên. | Bật -parameters hoặc dùng @P/@Param. |
| Dự án chạy được trên framework cũ nhưng lỗi sau nâng Spring Framework 6.1. | Dự án dựa vào debug symbols/LocalVariableTableParameterNameDiscoverer. | Biên dịch với -parameters; không dựa vào fallback LVT đã bị loại bỏ. |
| Reflection trả arg0 thay vì documentId. | Parameter.isNamePresent() là false. | Kiểm tra compile options ở module chứa service và biên dịch lại class. |
| @P import không tồn tại sau nâng Spring Security. | Package annotation đã thay đổi/deprecated theo phiên bản. | Spring Security 6.5 dùng org.springframework.security.access.method.P; Spring Security 7.1 dùng org.springframework.security.core.parameters.P. |
| Một tham số có @P nhưng tham số khác không tìm thấy tên. | AnnotationParameterNameDiscoverer có thể chỉ trả tên cho tham số được annotate. | Đặt @P cho mọi tham số được dùng hoặc dùng -parameters cho toàn method. |
| #p0 chạy nhưng #documentId không chạy. | Bí danh vị trí không cần metadata tên; tên documentId chưa được discover. | Bật -parameters hoặc đặt alias rõ ràng. |
| #p1 trỏ sai dữ liệu. | Chỉ số tham số bắt đầu từ 0 hoặc chữ ký method đã đổi. | Đối chiếu thứ tự tham số; ưu tiên named alias nếu method có nhiều tham số cùng kiểu. |
| Test @WithMockUser cho phép cả id sai. | Test không gọi bean Spring proxy, policy bean trả true sai hoặc expression dùng nhầm tham số. | Inject service thật, thêm test negative và kiểm tra policy bean. |
| Test MockMvc trả 403 dù method đúng. | URL rule hoặc CSRF chặn request trước service. | Kiểm tra filter chain và gọi service trực tiếp để cô lập SpEL. |
| JWT test có authentication nhưng policy từ chối. | Principal name hoặc authority trong token khác dữ liệu test giả định. | Kiểm tra Authentication#getName và GrantedAuthority thực tế; mock đúng dữ liệu cần thử. |
| Interface method không discover tên qua debug symbols. | Interface không mang LocalVariableTable của implementation; framework mới còn bỏ fallback LVT. | Dùng -parameters hoặc @P trên interface/method. |

Khi expression báo lỗi, hãy điều tra theo thứ tự: kiểm tra chữ ký method, xác định tên expression đang dùng, xem import @P đúng phiên bản, xác nhận compiler option được áp dụng, rồi kiểm tra test có gọi bean qua Spring proxy hay không. Không sửa expression sang một biến tùy ý để làm test xanh khi chưa biết giá trị mà biến đó đang tham chiếu.

## 13. Bài thực hành và tiêu chí hoàn thành

1. Tạo method có @PreAuthorize tham chiếu #documentId. Chạy test reflection để kiểm tra Parameter.isNamePresent() và tên thực tế.
2. Bật -parameters trong Maven hoặc Gradle. Biên dịch lại module chứa service và chứng minh test với tên documentId hoạt động.
3. Tạo method dùng @P("id") nhưng biến Java tên rawDocumentKey. Chứng minh expression #id vẫn hoạt động.
4. Nếu dự án dùng Spring Data, thử @Param("owner") và xác minh Spring Security discover tên owner.
5. Thử #p0 và #a0 trên method không có -parameters. So sánh với #documentId và giải thích vì sao bí danh vị trí vẫn hoạt động.
6. Tạo method có hai tham số được tham chiếu trong cùng expression. Dùng @P cho từng tham số hoặc -parameters; kiểm tra việc annotate một tham số đơn lẻ không làm mất tên của tham số còn lại.
7. Tạo MockMvc endpoint chuyển path variable vào service và kiểm tra người có document:read đọc được doc-1, người khác bị từ chối.
8. Trên WebFlux, dùng ReactiveDocumentService và WebTestClient mockUser để kiểm chứng biểu thức tham chiếu documentId trong Reactor Context.
9. Nâng một nhánh thử nghiệm từ framework cũ lên Spring Framework 6.1+, bỏ phụ thuộc debug symbols và xác minh giải pháp bằng -parameters hoặc @P.

**Tiêu chí hoàn thành:** Người học giải thích được cách Spring Security discover tên tham số, cấu hình đúng -parameters ở module biên dịch service, dùng @P/@Param hoặc #p0/#a0 khi cần, và chứng minh biểu thức SpEL cho phép/từ chối dựa trên đúng giá trị đầu vào bằng test Spring bean thật.

## Tài liệu tham khảo

- [Spring Security 6.5 — Method Security: Using Method Parameters](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — DefaultSecurityParameterNameDiscoverer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/parameters/DefaultSecurityParameterNameDiscoverer.html)
- [Spring Security 6.5 — AnnotationParameterNameDiscoverer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/parameters/AnnotationParameterNameDiscoverer.html)
- [Spring Security 6.5 — Migrating to Spring Security 7: Compile With -parameters](https://docs.spring.io/spring-security/reference/6.5/migration-7/authorization.html)
- [Spring Framework 6.2 — MethodBasedEvaluationContext API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/expression/MethodBasedEvaluationContext.html)
- [Spring Security 7.1 — P annotation API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/method/P.html)

