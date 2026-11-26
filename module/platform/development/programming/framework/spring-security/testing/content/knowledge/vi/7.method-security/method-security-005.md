# @PreFilter, @PostFilter và dữ liệu được giữ hoặc loại bỏ

## 1. Bài toán: một lời gọi xử lý nhiều đối tượng với quyền khác nhau

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Ngoài việc quyết định một lời gọi có được thực hiện hay không, ứng dụng còn cần lọc từng phần tử trong một tập dữ liệu.

Ví dụ một người dùng gửi danh sách tài liệu để xử lý hàng loạt. Một số tài liệu thuộc người đó, số khác thuộc người dùng khác. Hoặc service truy vấn nhiều tài liệu và chỉ một phần trong đó được phép hiển thị cho principal hiện tại. Nếu chính sách cần **giữ phần tử hợp lệ và loại phần tử không hợp lệ**, Spring Security cung cấp:

- **@PreFilter**: đánh giá từng phần tử của tham số collection trước khi thân phương thức chạy.
- **@PostFilter**: đánh giá từng phần tử của giá trị trả về sau khi thân phương thức đã chạy.

Hai annotation này thực hiện lọc theo biểu thức SpEL. Biến **filterObject** đại diện cho phần tử đang được xét; biểu thức thường dùng **authentication.name**, authority hoặc gọi một policy bean.

Sau bài học, bạn có thể:

- Phân biệt lọc tham số đầu vào và lọc kết quả trả về với kiểm tra quyền trên toàn bộ lời gọi.
- Viết **@PreFilter** cho collection đầu vào, chỉ định **filterTarget** khi có nhiều tham số collection.
- Viết **@PostFilter** cho collection trả về và hiểu cách xử lý **Map.Entry**, array và stream.
- Kiểm thử dữ liệu được giữ, bị loại, tập rỗng và nhiều principal bằng **@WithMockUser**.
- Dùng MockMvc và WebTestClient để kiểm tra đường đi HTTP trong Servlet và Reactive.
- Nhận diện rủi ro khi lọc dữ liệu trong bộ nhớ, xử lý batch một phần, collection không phù hợp và tác dụng phụ đã xảy ra trước khi **@PostFilter** hoàn tất.

> **Phiên bản và kiểu dữ liệu:** Ví dụ chính dùng Spring Security 6.x, Spring Boot 3.x, Java và JUnit 5. Reference Guide 6.5 liệt kê collection, map, array và stream cho các cơ chế lọc; riêng Javadoc PreFilter 6.5.11 mô tả filter target là một Collection khác null, hỗ trợ remove, và ghi rõ không hỗ trợ array. Để có ví dụ ổn định, phần Servlet dùng collection cho **@PreFilter**; hãy đối chiếu Javadoc của đúng phiên bản đã resolve trước khi dùng container khác. **@PostFilter** trong Reference Guide có ví dụ cho collection, map, array và stream còn đang mở.

## 2. Lọc từng phần tử khác với từ chối toàn bộ lời gọi

Hãy phân biệt ba mức quyết định:

| Cơ chế | Thời điểm | Kết quả khi một phần tử không đạt điều kiện |
|---|---|---|
| **@PreAuthorize** | Trước khi thân phương thức chạy | Từ chối toàn bộ lời gọi; phương thức không chạy. |
| **@PreFilter** | Trước khi thân phương thức chạy | Loại phần tử không đạt điều kiện khỏi tham số được lọc; phương thức vẫn chạy với các phần tử còn lại. |
| **@PostFilter** | Sau khi thân phương thức trả kết quả | Loại phần tử không đạt điều kiện khỏi kết quả gửi cho caller; phương thức đã chạy. |

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Caller gửi danh sách"] --> B["Spring method-security proxy"]
    B --> C["@PreFilter: xét filterObject từng phần tử"]
    C --> D["Danh sách đầu vào đã lọc"]
    D --> E["Chạy thân phương thức"]
    E --> F["Danh sách kết quả"]
    F --> G["@PostFilter: xét filterObject từng phần tử"]
    G --> H["Chỉ trả các phần tử được giữ"]
~~~

Ví dụ principal Alice gửi ba tài liệu: doc-1 của Alice, doc-2 của Bob và doc-3 của Alice. Với biểu thức **filterObject.owner == authentication.name**, **@PreFilter** đưa doc-1 và doc-3 vào phương thức; doc-2 bị loại. Nếu phương thức trả về cả tài liệu Alice và Bob, **@PostFilter** chỉ đưa tài liệu Alice về caller.

Điểm quan trọng: hai annotation **không tự động ném AccessDeniedException chỉ vì có một phần tử bị loại**. Nếu tất cả phần tử bị loại, phương thức có thể vẫn chạy với collection rỗng hoặc caller nhận collection rỗng. Khi nghiệp vụ yêu cầu “chỉ cần một phần tử sai quyền là từ chối toàn bộ batch”, hãy dùng kiểm tra toàn bộ đầu vào bằng policy/validator phù hợp và chủ động ném lỗi nghiệp vụ hoặc từ chối authorization; không coi **@PreFilter** là cơ chế all-or-nothing.

## 3. Điều kiện để annotation được thực thi

Trong ứng dụng Servlet, bật method security bằng một class cấu hình được Spring nạp:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

**@EnableMethodSecurity** kích hoạt các interceptor cho **@PreAuthorize**, **@PostAuthorize**, **@PreFilter** và **@PostFilter** theo cấu hình mặc định hiện đại. Spring Boot Starter Security tự nó không tự bật method-level authorization.

Service cần là Spring bean và caller cần gọi qua tham chiếu bean do Spring inject. Ví dụ sau bỏ qua proxy nên không có gì đảm bảo lọc được áp dụng:

~~~java
DocumentService service = new DocumentService();
service.processBatch(documents);
~~~

Tương tự, lời gọi nội bộ **this.processBatch(...)** trong cùng bean có thể bỏ qua Spring AOP proxy. Hãy kiểm tra bằng cách inject service vào test context và gọi qua bean thật. Nếu chỉ viết unit test cho phương thức Java trực tiếp, test đó không chứng minh method-security interceptor đã hoạt động.

## 4. filterObject và biểu thức SpEL

**filterObject** là biến đặc biệt đại diện cho phần tử hiện tại đang được kiểm tra. Với một collection các tài liệu:

~~~java
@PreFilter("filterObject.owner == authentication.name")
public List<Document> processBatch(List<Document> documents) {
    // Chỉ nhận các document có owner trùng principal.
    return new ArrayList<>(documents);
}
~~~

Với mỗi phần tử, Spring đánh giá **filterObject.owner == authentication.name**. Nếu biểu thức đúng, phần tử được giữ; nếu sai, phần tử bị loại. **owner** ở đây là JavaBean property có getter **getOwner()**.

Một số biểu thức minh họa:

~~~java
// Chỉ giữ đối tượng của principal hiện tại.
@PreFilter("filterObject.owner == authentication.name")

// Chỉ giữ tài liệu có nhãn được phép.
@PostFilter("filterObject.classification != 'INTERNAL'")

// Giữ phần tử khi có authority đọc.
@PostFilter("hasAuthority('document:read')")

// Kiểm tra quyền đọc thông qua policy bean.
@PostFilter("@documentPolicy.canRead(authentication, filterObject.id)")
~~~

Biểu thức cuối hữu ích khi policy phức tạp hơn một phép so sánh thuộc tính. **documentPolicy** phải là bean Spring có tên tương ứng, và logic trong đó nên được kiểm thử riêng. Nếu biểu thức truy cập thuộc tính không tồn tại, gọi bean sai tên hoặc trả kiểu không thể chuyển thành boolean, lời gọi có thể lỗi khi thực thi.

Không lấy owner, tenantId hoặc classification từ dữ liệu do client tự khai rồi xem đó là nguồn tin cậy. Phần tử cần được đối chiếu với dữ liệu nghiệp vụ từ server hoặc policy bean có kiểm tra quyền đáng tin cậy.

## 5. @PreFilter với collection đầu vào

### 5.1. Ví dụ service đơn giản

Dùng một đối tượng tài liệu nhỏ:

~~~java
// Document.java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Document {

    private final String id;
    private final String owner;
    private final String title;

    @JsonCreator
    public Document(
            @JsonProperty("id") String id,
            @JsonProperty("owner") String owner,
            @JsonProperty("title") String title) {
        this.id = id;
        this.owner = owner;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Service nhận một collection và trả về danh sách phần tử mà thân phương thức thực sự nhận được:

~~~java
// DocumentBatchService.java
import java.util.ArrayList;
import java.util.List;

import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentBatchService {

    @PreFilter("filterObject.owner == authentication.name")
    public List<Document> processBatch(List<Document> candidates) {
        // Minh họa phần nghiệp vụ nhìn thấy dữ liệu đã lọc.
        return new ArrayList<>(candidates);
    }
}
~~~

Nếu caller là Alice và gửi danh sách gồm tài liệu của Alice lẫn Bob, phương thức chỉ nhận những phần tử có owner là Alice. Collection là tham số duy nhất cần lọc nên không cần khai báo **filterTarget**.

**Chọn collection phù hợp:** Javadoc của **@PreFilter** yêu cầu filter target là một **Collection** khác null và hỗ trợ thao tác **remove**. Vì vậy, dùng một collection có thể chỉnh sửa như **ArrayList** là lựa chọn rõ ràng cho ví dụ:

~~~java
List<Document> submitted = new ArrayList<>(List.of(
    new Document("doc-1", "alice", "Kế hoạch A"),
    new Document("doc-2", "bob", "Kế hoạch B"),
    new Document("doc-3", "alice", "Kế hoạch C")
));
~~~

Không mặc định mọi collection đều có thể bị lọc. **List.of(...)**, **Collections.unmodifiableList(...)** và một số collection bất biến không đáp ứng hợp đồng có thể chỉnh sửa mà **@PreFilter** yêu cầu. Đừng dựa vào việc truyền collection bất biến rồi mong Spring tự tạo bản thay thế theo cách giống nhau ở mọi phiên bản. Kiểm tra đúng implementation và dùng collection phù hợp.

### 5.2. Nhiều tham số collection và filterTarget

Khi method có nhiều tham số collection, Spring cần biết collection nào là mục tiêu lọc. Dùng thuộc tính **filterTarget** để chỉ rõ tên tham số:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentImportService {

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public List<Document> importDocuments(
            @P("documents") List<Document> documents,
            List<String> requestedTags) {

        // documents đã được lọc; requestedTags vẫn giữ nguyên.
        return new ArrayList<>(documents);
    }
}
~~~

Trong ví dụ, chỉ tham số **documents** bị lọc. **requestedTags** không bị tác động bởi biểu thức đó. **@P("documents")** giúp khai báo tên tham số cho Spring Security; dự án cũng cần cấu hình giữ tên tham số phù hợp, chẳng hạn biên dịch với **-parameters**, theo cách nhận diện tham số của phiên bản đang dùng.

Nếu không chỉ định đúng **filterTarget** khi có nhiều tham số collection, Spring có thể không xác định được tham số nào cần lọc và ném lỗi lúc gọi method. Đây là lỗi nên được phát hiện bằng test cho chính chữ ký phương thức thực tế.

### 5.3. Kết quả khi mọi phần tử đều bị loại

Với Alice, nếu collection chỉ có tài liệu của Bob, biểu thức không giữ lại phần tử nào. Phương thức vẫn được gọi với collection rỗng. Đây là hành vi lọc, không phải từ chối toàn bộ lời gọi.

Điều này phù hợp với một số nghiệp vụ nhập batch có chủ đích chấp nhận phần hợp lệ. Nhưng nếu hệ thống phải bảo đảm toàn bộ batch được xử lý nguyên tử, hãy kiểm tra tất cả phần tử trước khi bắt đầu xử lý và từ chối khi có bất kỳ phần tử không hợp lệ nào. Nếu phương thức ghi database, cân nhắc transaction cho phần nghiệp vụ được phép; transaction không thay thế quyết định authorization.

## 6. @PostFilter với collection trả về

**@PostFilter** đánh giá từng phần tử sau khi phương thức đã chạy và trước khi kết quả được trả về caller:

~~~java
// DocumentQueryService.java
import java.util.ArrayList;
import java.util.List;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {

    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> findAll() {
        // Dữ liệu mô phỏng: một phần thuộc Alice, một phần thuộc Bob.
        List<Document> result = new ArrayList<>();
        result.add(new Document("doc-1", "alice", "Kế hoạch A"));
        result.add(new Document("doc-2", "bob", "Kế hoạch B"));
        result.add(new Document("doc-3", "alice", "Kế hoạch C"));
        return result;
    }
}
~~~

Khi Alice gọi **findAll()**, caller chỉ nhận doc-1 và doc-3. Thân phương thức đã thực thi và đã tạo danh sách gồm ba phần tử trước khi interceptor áp dụng biểu thức lọc.

Một số kiểu dữ liệu được Reference Guide mô tả:

| Kiểu trả về | filterObject đại diện | Lưu ý |
|---|---|---|
| **Collection<Document>** | Từng **Document** | Đây là dạng phổ biến nhất. |
| **Map<String, Document>** | Từng **Map.Entry** | Truy cập giá trị qua **filterObject.value**; khóa qua **filterObject.key**. |
| **Document[]** | Từng **Document** | **@PostFilter** tạo mảng mới chỉ chứa phần tử được giữ. |
| **Stream<Document>** | Từng **Document** | Stream phải còn mở khi lọc và chỉ được tiêu thụ một lần. |

Ví dụ lọc map:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> findByKeys() {
    Map<String, Document> result = new LinkedHashMap<>();
    result.put("a", new Document("doc-1", "alice", "Kế hoạch A"));
    result.put("b", new Document("doc-2", "bob", "Kế hoạch B"));
    return result;
}
~~~

Vì **filterObject** là **Map.Entry**, biểu thức phải dùng **filterObject.value.owner**. Viết **filterObject.owner** sẽ không đúng kiểu phần tử đang được xét. Nếu muốn kiểm tra key, dùng **filterObject.key**.

Ví dụ array:

~~~java
@PostFilter("filterObject.owner == authentication.name")
public Document[] findArray() {
    return new Document[] {
        new Document("doc-1", "alice", "Kế hoạch A"),
        new Document("doc-2", "bob", "Kế hoạch B")
    };
}
~~~

Đối với array, kết quả được lọc là một array mới. Với **Stream**, cần giữ stream ở trạng thái mở cho đến khi quá trình lọc/tiêu thụ hoàn tất; không tái sử dụng một stream đã được tiêu thụ.

**Lưu ý về collection dùng chung:** Không trả trực tiếp một collection mutable đang được chia sẻ trong cache hoặc dùng chung cho nhiều request rồi dựa vào filter. Hãy trả một kết quả riêng cho mỗi lần gọi (ví dụ bản sao từ repository/cache). Điều này giúp tránh việc lọc của một principal ảnh hưởng đến dữ liệu mà caller khác sẽ đọc, đồng thời tránh phụ thuộc vào danh tính hoặc khả năng sửa đổi của collection gốc.

Các wrapper như **Optional<T>** hoặc **Page<T>** không phải là collection đơn giản được nêu trong danh sách kiểu hỗ trợ. Không gắn **@PostFilter** vào một kiểu trả về bất kỳ rồi giả định Spring sẽ tự lọc phần tử bên trong. Với **Page<T>**, nên lọc ở truy vấn dữ liệu để phân trang, tổng số bản ghi và thứ tự vẫn đúng.

## 7. Kiểm thử bằng @WithMockUser

Các test phải gọi bean thật từ Spring context. Ví dụ dưới đây kết hợp **DocumentBatchService** và **DocumentQueryService** ở trên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentFilteringTest {

    @Autowired
    DocumentBatchService batchService;

    @Autowired
    DocumentQueryService queryService;

    @Test
    @WithMockUser(username = "alice")
    void preFilterKeepsOnlyDocumentsOwnedByAlice() {
        List<Document> input = new ArrayList<>(List.of(
            new Document("doc-1", "alice", "A"),
            new Document("doc-2", "bob", "B"),
            new Document("doc-3", "alice", "C")
        ));

        List<Document> processed = batchService.processBatch(input);

        assertEquals(
            List.of("doc-1", "doc-3"),
            processed.stream()
                .map(Document::getId)
                .collect(Collectors.toList())
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilterReturnsOnlyDocumentsOwnedByAlice() {
        List<Document> visible = queryService.findAll();

        assertEquals(
            List.of("doc-1", "doc-3"),
            visible.stream()
                .map(Document::getId)
                .collect(Collectors.toList())
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilterReturnsOnlyDocumentsOwnedByBob() {
        List<Document> visible = queryService.findAll();

        assertEquals(
            List.of("doc-2"),
            visible.stream()
                .map(Document::getId)
                .collect(Collectors.toList())
        );
    }

    @Test
    @WithMockUser(username = "carol")
    void postFilterCanReturnAnEmptyCollection() {
        assertTrue(queryService.findAll().isEmpty());
    }
}
~~~

Các test trên cho thấy cùng một phương thức có thể trả về tập phần tử khác nhau tùy **authentication.name**. Đặc biệt, test principal Carol xác minh kết quả rỗng hợp lệ khi không có phần tử nào thuộc về người đó.

**@WithMockUser** thiết lập Authentication thử nghiệm trong SecurityContext. Nó phù hợp để kiểm tra biểu thức authorization/filter với username và authorities đã định trước; nó không xác minh mật khẩu, chữ ký JWT hoặc quá trình đăng nhập với identity provider thật. Nếu biểu thức còn yêu cầu **hasAuthority('document:read')**, hãy khai báo authority đó trong annotation, ví dụ **@WithMockUser(username = "alice", authorities = "document:read")**.

### Kiểm thử filterTarget

Với method có nhiều collection tham số, thêm test gọi đúng chữ ký **importDocuments(documents, requestedTags)** và xác minh chỉ **documents** bị lọc. Nên đặt một phần tử của collection thứ hai có giá trị dễ nhận biết để bảo đảm nó không bị thay đổi. Nếu tên tham số không được Spring nhận diện hoặc **filterTarget** sai, test sẽ phát hiện lỗi khi method được gọi.

### Kiểm thử method body nhận dữ liệu đã lọc

Một test có thể kiểm chứng kích thước batch mà thân phương thức quan sát được. Ví dụ service ghi nhận **documents.size()** vào một dependency hoặc trả về chính các phần tử đã nhận. Test phải gọi qua bean Spring proxy. Không chỉ gọi helper lọc tự viết trong unit test, vì điều đó không xác minh **@PreFilter** interceptor.

## 8. Kiểm thử HTTP Servlet bằng MockMvc

Để kiểm tra đường đi từ HTTP đến service, controller inject bean thật:

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/documents")
public class DocumentController {

    private final DocumentBatchService batchService;
    private final DocumentQueryService queryService;

    public DocumentController(
            DocumentBatchService batchService,
            DocumentQueryService queryService) {
        this.batchService = batchService;
        this.queryService = queryService;
    }

    @GetMapping
    public List<Document> findAll() {
        return queryService.findAll();
    }

    @PostMapping("/batch")
    public List<Document> process(@RequestBody List<Document> documents) {
        return batchService.processBatch(documents);
    }
}
~~~

Để cô lập method filtering trong bài thực hành, có thể cấu hình HTTP filter chain cho phép request tới controller. Ví dụ này không phải cấu hình production hoàn chỉnh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

MockMvc test với Spring Boot 3.x:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentFilteringHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getDocumentsReturnsOnlyCurrentUsersDocuments() throws Exception {
        mvc.perform(get("/documents").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value("doc-1"))
            .andExpect(jsonPath("$[1].id").value("doc-3"))
            .andExpect(jsonPath("$[2]").doesNotExist());
    }

    @Test
    void postBatchProcessesOnlyOwnedDocuments() throws Exception {
        String payload = """
            [
              {"id":"doc-1","owner":"alice","title":"A"},
              {"id":"doc-2","owner":"bob","title":"B"}
            ]
            """;

        mvc.perform(post("/documents/batch")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(payload))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value("doc-1"))
            .andExpect(jsonPath("$[1]").doesNotExist());
    }
}
~~~

**GET** trong ví dụ không cần CSRF token; **POST** có **csrf()** để không bị CSRF filter chặn trước khi đi vào controller. Test này giả định HTTP config và controller như trên. Trong ứng dụng thực tế, URL policy có thể yêu cầu xác thực, CSRF, bearer token hoặc handler riêng; status HTTP phụ thuộc cấu hình đó.

Nếu dùng **@WebMvcTest** và mock service, bạn chỉ kiểm tra controller gọi mock như mong đợi; bạn không chứng minh **@PreFilter** hoặc **@PostFilter** trên service thật hoạt động. Với mục tiêu xác minh method security, dùng Spring context có bean service thật, hoặc thiết kế test slice để import đầy đủ hạ tầng method security và service thật.

## 9. Reactive WebFlux và WebTestClient

Spring Security Reactive có các interceptor riêng cho **@PreFilter** và **@PostFilter**. Với WebFlux, bật method security reactive và bảo đảm Authentication có mặt trong Reactor Context. Ví dụ dưới đây dùng **Flux<Document>**: **@PreFilter** lọc từng phần tử của publisher đầu vào trước khi service xử lý; **@PostFilter** lọc từng phần tử publisher trả về trước khi caller nhận.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveSecurityConfig {
}
~~~

Service Reactive:

~~~java
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReactiveDocumentService {

    @PreFilter("filterObject.owner == authentication.name")
    public Flux<Document> processBatch(Flux<Document> candidates) {
        // Publisher đã được lọc trước khi đi vào thân method.
        return candidates;
    }

    @PostFilter("filterObject.owner == authentication.name")
    public Flux<Document> findAll() {
        return Flux.just(
            new Document("doc-1", "alice", "Kế hoạch A"),
            new Document("doc-2", "bob", "Kế hoạch B"),
            new Document("doc-3", "alice", "Kế hoạch C")
        );
    }
}
~~~

Controller WebFlux:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/reactive/documents")
public class ReactiveDocumentController {

    private final ReactiveDocumentService service;

    public ReactiveDocumentController(ReactiveDocumentService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Document> findAll() {
        return service.findAll();
    }

    @PostMapping(
        path = "/batch",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Flux<Document> process(@RequestBody Flux<Document> documents) {
        return service.processBatch(documents);
    }
}
~~~

Trong cấu hình Reactive đầy đủ, cần có **SecurityWebFilterChain**. Để cô lập method filtering trong bài thực hành, request được phép đi tới controller:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class DemoReactiveHttpConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .anyExchange().permitAll())
            .build();
    }
}
~~~

Test với WebTestClient và reactive mock user:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class ReactiveDocumentFilteringTest {

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
    void postFilterKeepsOnlyAliceDocuments() {
        client.mutateWith(mockUser("alice"))
            .get().uri("/reactive/documents")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Document.class)
            .value(documents -> {
                org.junit.jupiter.api.Assertions.assertEquals(
                    List.of("doc-1", "doc-3"),
                    documents.stream().map(Document::getId).toList()
                );
            });
    }

    @Test
    void preFilterRemovesBobDocumentBeforeProcessing() {
        List<Document> input = List.of(
            new Document("doc-1", "alice", "A"),
            new Document("doc-2", "bob", "B")
        );

        client.mutateWith(mockUser("alice"))
            .post().uri("/reactive/documents/batch")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Document.class)
            .hasSize(1)
            .value(documents ->
                org.junit.jupiter.api.Assertions.assertEquals(
                    "doc-1", documents.get(0).getId()
                )
            );
    }
}
~~~

Các test trên yêu cầu ứng dụng thật sự chạy WebFlux, nạp **ReactiveSecurityConfig**, **DemoReactiveHttpConfig**, controller và service. **@EnableReactiveMethodSecurity(useAuthorizationManager = true)** là cấu hình được dùng trong ví dụ 6.x; đối chiếu annotation của đúng phiên bản nếu dùng nhánh Spring Security khác. WebTestClient gửi request và subscribe publisher nên có thể quan sát các phần tử đã lọc. Khi test trực tiếp **Flux**, dùng StepVerifier hoặc subscriber trong Reactor Context thích hợp; chỉ tạo publisher mà không subscribe thì chưa quan sát kết quả.

Không trộn **@EnableMethodSecurity** Servlet và **@EnableReactiveMethodSecurity** vào cùng một ví dụ rồi suy đoán cơ chế nào đang chạy. Chọn đúng application type và security context của stack đang kiểm thử.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách kiểm tra/sửa |
|---|---|---|
| Phương thức nhận cả phần tử không thuộc principal. | Chưa bật method security, bean không qua proxy hoặc test tạo service bằng **new**. | Inject bean thật, viết test với một phần tử đúng và một phần tử sai. |
| **@PreFilter** báo lỗi khi truyền collection. | Collection không hỗ trợ **remove**, target null hoặc filterTarget không hợp lệ. | Dùng collection mutable, không truyền null và chỉ định đúng **filterTarget**. |
| Có nhiều collection tham số nhưng không biết lọc tham số nào. | Thiếu **filterTarget**. | Chỉ định tên tham số cần lọc; kiểm tra tên được Spring nhận diện. |
| Tất cả phần tử bị loại nhưng method vẫn chạy. | Đây là semantics của lọc từng phần tử. | Nếu cần từ chối cả batch, dùng authorization/validation all-or-nothing. |
| **@PostFilter** trả về danh sách rỗng. | Không phần tử nào thỏa biểu thức. | Kiểm tra principal, dữ liệu owner và authority; xác định empty result có đúng nghiệp vụ. |
| **Map** không lọc đúng. | **filterObject** là **Map.Entry**, nhưng expression truy cập như một entity trực tiếp. | Dùng **filterObject.value.owner** hoặc **filterObject.key**. |
| Stream bị lỗi hoặc không có dữ liệu. | Stream đã đóng hoặc đã bị tiêu thụ trước khi filter. | Trả stream mới, giữ mở đến khi caller tiêu thụ và không dùng lại stream. |
| **Page<T>** hoặc wrapper khác gây lỗi. | Kiểu trả về không nằm trong container được hỗ trợ. | Lọc trong repository/query layer thay vì áp **@PostFilter** lên wrapper. |
| MockMvc trả 403 nhưng service filter không được thực thi. | CSRF hoặc URL rule chặn request trước controller. | Gửi CSRF khi cần và kiểm thử service trực tiếp bằng bean thật. |
| WebFlux test trả đủ phần tử dù có annotation. | Sai reactive method-security config hoặc thiếu Reactor SecurityContext. | Dùng reactive security config và WebTestClient **mockUser()**/**springSecurity()**. |
| Kết quả của request này ảnh hưởng request khác. | Phương thức trả collection mutable dùng chung hoặc dữ liệu cache bị chia sẻ. | Trả bản sao riêng cho từng lời gọi; không đưa cache dùng chung qua filter. |

## 11. Khi nào nên lọc ở tầng dữ liệu?

**@PostFilter** rất tiện cho tập dữ liệu nhỏ, nhưng nó không thay thế truy vấn dữ liệu có điều kiện. Giả sử database có 100.000 tài liệu và một principal chỉ được đọc 200 tài liệu. Nếu repository tải cả 100.000 bản ghi rồi **@PostFilter** loại phần lớn trong bộ nhớ, ứng dụng đã tốn tài nguyên truy vấn, network, heap và CPU cho dữ liệu caller không thể sử dụng.

Với phân trang, vấn đề còn rõ hơn. Nếu repository lấy 20 bản ghi đầu rồi **@PostFilter** chỉ giữ lại 2, caller nhận một trang có 2 phần tử dù có thể còn nhiều tài liệu hợp lệ ở trang kế tiếp. Tổng số bản ghi, số trang và điều kiện sắp xếp cũng không phản ánh đúng tập dữ liệu mà người dùng được phép xem.

Vì vậy:

- Dùng **@PreFilter** cho batch đầu vào vừa phải, khi nghiệp vụ chủ đích loại riêng từng phần tử trước khi xử lý.
- Dùng **@PostFilter** cho tập kết quả nhỏ hoặc khi việc lọc tại service thực sự là ranh giới thuận tiện.
- Với truy vấn lớn, tenant isolation, ACL hoặc phân trang, đưa điều kiện owner/tenant/permission xuống repository hoặc query layer.
- Với lệnh ghi cần tất cả hoặc không gì cả, kiểm tra toàn bộ quyền trước khi thực hiện; không để lọc im lặng tạo ra một batch chỉ được xử lý một phần ngoài ý muốn.
- Tránh để dữ liệu bị loại xuất hiện trong log, cache, event hoặc response phụ trước khi filter hoàn tất.

Một policy bean có thể giúp giữ logic truy cập nhất quán, nhưng nếu policy cần query từng phần tử trong một danh sách lớn thì vẫn có nguy cơ N+1 query. Hãy cân nhắc truy vấn theo tập ID, join hoặc predicate ở tầng dữ liệu.

## 12. Bài thực hành và tiêu chí hoàn thành

1. Tạo **Document**, **DocumentBatchService** và **DocumentQueryService**; bật **@EnableMethodSecurity**.
2. Với **@PreFilter**, gửi collection có tài liệu của Alice và Bob dưới principal Alice. Chứng minh method body chỉ nhận tài liệu Alice.
3. Thêm một tham số collection thứ hai và chỉ định **filterTarget**. Xác minh collection thứ hai không bị lọc.
4. Thử collection không hỗ trợ **remove**, quan sát hành vi của phiên bản đang dùng và điều chỉnh input thành collection phù hợp.
5. Với **@PostFilter**, trả về danh sách Alice/Bob/Carol và kiểm tra từng principal chỉ nhận các phần tử hợp lệ. Thử trường hợp kết quả rỗng.
6. Tạo method trả **Map<String, Document>** và dùng **filterObject.value.owner**. So sánh với truy cập **filterObject.owner** để hiểu phần tử được đánh giá là **Map.Entry**.
7. Tạo controller và kiểm thử GET/POST bằng MockMvc. Với POST, gửi CSRF token hợp lệ để không nhầm lỗi filter HTTP với kết quả method filtering.
8. Trên WebFlux, dùng **Flux<Document>**, reactive method security và WebTestClient để kiểm chứng **@PreFilter** đầu vào và **@PostFilter** đầu ra dưới principal giả lập.
9. Đánh giá một endpoint có phân trang và giải thích vì sao lọc sau khi lấy page có thể làm sai kích thước trang và tổng số kết quả; đề xuất predicate ở repository.

**Tiêu chí hoàn thành:** Người học chứng minh được phần tử hợp lệ được giữ, phần tử không hợp lệ bị loại ở đúng thời điểm, và phân biệt rõ lọc từng phần tử với từ chối toàn bộ lời gọi. Các phép thử phải gọi bean Spring thật hoặc WebTestClient/MockMvc tích hợp security đúng stack, có cả principal cho kết quả không rỗng và principal cho kết quả rỗng.

## Tài liệu tham khảo

- [Spring Security 6.5 — Method Security (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5.11 — PreFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreFilter.html)

