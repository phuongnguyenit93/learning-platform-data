# Không đưa dữ liệu đầu vào không tin cậy thành mã SpEL

## 1. Vấn đề cốt lõi: phân biệt **mã chính sách** và **dữ liệu**

Trong Spring Security, SpEL (Spring Expression Language) thường xuất hiện trong `@PreAuthorize`, `@PostAuthorize` và các thành phần authorization tùy biến. Biểu thức là **mã được đánh giá trong ứng dụng**: nó có thể thực hiện so sánh, điều kiện logic, truy cập thuộc tính, gọi phương thức và, tùy `EvaluationContext`, tham chiếu các thành phần Java/Spring khác.

**Quy tắc an toàn:** nguồn không tin cậy chỉ được cung cấp **giá trị dữ liệu** để một chính sách đã được nhà phát triển định nghĩa sử dụng. Không ghép giá trị đó vào chuỗi SpEL rồi đưa chuỗi mới cho `parseExpression(...)` hoặc bộ máy xử lý biểu thức tương đương.

Ví dụ người dùng gửi một chuỗi qua URL, form hoặc JSON. Chuỗi đó có thể là tên tài liệu, giá trị tìm kiếm hay mã tài nguyên. Ứng dụng có thể so sánh nó với dữ liệu đã được xác minh, nhưng **không được cho chuỗi đó quyết định phép toán hay nhánh cấp quyền**.

Mục tiêu bài học:

- Biết đường đi từ dữ liệu bên ngoài đến bộ phân tích biểu thức và nhận diện rủi ro SpEL injection.
- Phân biệt việc **tham chiếu giá trị** bằng tham số/biến với việc **ghép nội dung vào cú pháp biểu thức**.
- Dùng `@PreAuthorize` cố định, bean policy Java và kiểm tra tài nguyên tin cậy để bảo vệ phương thức.
- Hiểu giới hạn của validation, escaping, `SimpleEvaluationContext` và cơ chế phân quyền bằng vai trò.
- Viết kiểm thử cho các chuỗi đầu vào có dấu nháy, toán tử logic và biểu thức giống mã, bảo đảm chúng chỉ là dữ liệu.

## 2. SpEL injection là gì, và vì sao nghiêm trọng?

**SpEL injection** xảy ra khi ứng dụng lấy chuỗi không tin cậy và để chuỗi đó trở thành **một phần cú pháp SpEL được phân tích hoặc đánh giá**. Khi ấy, người cung cấp chuỗi có thể ảnh hưởng đến logic, thay đổi nhánh đúng/sai hoặc, với ngữ cảnh đánh giá có khả năng mạnh, dẫn tới những tương tác không được dự định với đối tượng và phương thức trong ứng dụng.

Tài liệu Spring Framework cảnh báo: SpEL có khả năng gọi phương thức/constructor, đọc ghi thuộc tính và tham chiếu bean tùy cấu hình; vì vậy **không nên đánh giá biểu thức SpEL lấy từ nguồn không tin cậy**. Mức độ tác động thực tế phụ thuộc evaluator, root object, các resolver, biến và phương thức được công bố. Không suy đoán mọi vị trí dùng SpEL đều dẫn tới thực thi lệnh từ xa; nhưng cũng không coi một biểu thức do người dùng cung cấp là vô hại chỉ vì "trông giống điều kiện".

Các nguồn đầu vào cần đánh giá như **không tin cậy** gồm:

- Query parameter, path variable, header, cookie, body JSON, trường upload và WebSocket message.
- Trường `filter`, `sort`, `condition`, `permissionExpression` do client tự gửi.
- Bản ghi database mà người dùng có quyền sửa, nội dung từ queue, file cấu hình nhập từ bên thứ ba, API của đối tác.
- Các chuỗi trong token/claim, ngay cả khi token đã được xác minh chữ ký, nếu nguồn tạo giá trị đó không được phép định nghĩa chính sách thực thi.

Một vai trò hoặc permission hợp lệ trong `Authentication` vẫn chỉ là **dữ liệu quyền do hệ thống tin cậy cấp**; không biến các chuỗi này thành mã SpEL động.

**Ranh giới tin cậy thực tế:** nhà phát triển hoặc quản trị viên được giao quyền thiết kế chính sách có thể cung cấp biểu thức **đã được kiểm soát**; người sử dụng nghiệp vụ thông thường không có quyền đó. Nếu hệ thống định hỗ trợ "người dùng tự tạo rule", phải thiết kế một ngôn ngữ/DSL hoặc biểu mẫu điều kiện hạn chế và triển khai việc đánh giá bằng code đã kiểm tra, thay vì mở parser SpEL cho mọi biểu thức.

## 3. Anti-pattern: ghép chuỗi đầu vào vào biểu thức

Giả sử một chức năng tùy biến nhận `filter` từ request rồi dùng lại nó như điều kiện quyết định quyền. Dạng code sau là **minh họa anti-pattern**, không phải triển khai được khuyến nghị:

```java
// KHÔNG DÙNG: filter đến trực tiếp từ request.
String filter = request.getParameter("filter");
String expressionText =
    "hasAuthority('document:read') and #sameTenant " + filter;

// Sau đó ứng dụng đưa expressionText vào một SpEL evaluator.
Expression expression = new SpelExpressionParser()
    .parseExpression(expressionText);
```

Đoạn minh họa giả định ứng dụng có một `EvaluationContext` tương ứng với các biến và hàm authorization. Vấn đề xuất hiện **trước** khi xét evaluator: `filter` có quyền thay đổi cấu trúc câu lệnh được parse.

Ví dụ, nếu chuỗi nhập không được giới hạn chỉ là giá trị và có thể mang toán tử `or`, nhánh được ghép thêm có thể làm cả điều kiện đánh giá thành đúng. Đây là **bypass chính sách**, không đơn thuần là một chuỗi tìm kiếm sai định dạng.

Đường đi có rủi ro:

```text
HTTP/JSON/DB do người dùng kiểm soát
            |
            v
Ghép String, String.format hoặc template thành "công thức"
            |
            v
SpelExpressionParser.parseExpression(công thức)
            |
            v
Expression.getValue(context) -> quyết định hoặc hành vi không dự tính
```

Không chỉ phép cộng chuỗi `+` mới nguy hiểm: `String.format(...)`, `MessageFormat`, template engine, ghép các mảnh config, hoặc tự động sinh biểu thức từ cột database đều có thể tạo ra cùng ranh giới sai nếu có phần đến từ nguồn không tin cậy.

**Một lỗi khác:**

```java
// KHÔNG DÙNG: giá trị owner từ request được đặt thẳng trong chuỗi SpEL.
String ownerFromRequest = request.getParameter("owner");
String expressionText =
    "authentication.name == '" + ownerFromRequest + "'";
```

Dấu nháy đơn trong dữ liệu có thể làm thay đổi cách parser đọc một literal. Cố gắng sửa bằng cách thay thế vài ký tự hoặc escape thủ công rất dễ thiếu trường hợp biên, và vẫn duy trì thiết kế "biến dữ liệu thành mã".

## 4. Cách đúng: biểu thức cố định, dữ liệu đi qua biến hoặc tham số

### Trong Spring Security Method Security

Dùng biểu thức **cố định trong mã nguồn**; chỉ đưa ID từ bên ngoài làm tham số phương thức:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "isAuthenticated() and hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Document read(@P("documentId") Long documentId) {
        return documents.findById(documentId).orElseThrow();
    }
}
```

Ở đây:

1. `@PreAuthorize(...)` chứa chính sách do nhà phát triển viết, không chứa nội dung request được nối vào cú pháp.
2. `#documentId` là **giá trị** của tham số Java lúc gọi method; Spring Security không parse lại chuỗi ID như một chương trình SpEL.
3. `authentication` là đối tượng xác thực do Spring Security cung cấp.
4. `@documentPolicy.canRead(...)` gọi một bean policy đã được đăng ký; bean tự đối chiếu người gọi với tài nguyên trong database.
5. `@P("documentId")` giúp đặt tên tham số rõ ràng khi reflection hoặc build chưa giữ tên tham số. Để method security chạy, ứng dụng cần bật `@EnableMethodSecurity`.

**Lưu ý về ranh giới:** không nên sửa thành `hasAuthority(#permissionFromRequest)` nếu ý định là yêu cầu quyền cố định `document:read`. Dùng `#permissionFromRequest` không gây injection cú pháp, nhưng nó có thể tạo **lỗi logic phân quyền**: người gọi được tự chọn quyền nào cần kiểm tra. Phòng SpEL injection và thiết kế policy đúng là hai yêu cầu khác nhau.

### Bean policy dùng dữ liệu có nguồn đáng tin cậy

Ví dụ dưới đây là **đoạn thành phần trong ứng dụng Spring Boot**, giả định `DocumentRepository` và `TenantMembershipService` là các bean đã triển khai; các getter entity và phương thức membership là giao diện nghiệp vụ minh họa:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository documents;
    private final TenantMembershipService membership;

    public DocumentPolicy(
            DocumentRepository documents,
            TenantMembershipService membership) {
        this.documents = documents;
        this.membership = membership;
    }

    public boolean canRead(Authentication auth, Long documentId) {
        if (auth == null || documentId == null) {
            return false;
        }

        return documents.findById(documentId)
            .filter(doc -> membership.canAccess(auth, doc.getTenantId()))
            .filter(doc -> auth.getName().equals(doc.getOwnerUsername()))
            .isPresent();
    }
}
```

Trong ứng dụng thực, `membership.canAccess` phải xác minh membership/tenant từ dữ liệu do server kiểm soát, không chỉ so với header `X-Tenant-Id` do client tự đặt. Service phía trên còn có `isAuthenticated()` để chặn anonymous trước khi gọi. Có thể bổ sung ACL hoặc quyền chia sẻ trong policy theo nghiệp vụ; việc đọc theo ID cần bảo đảm không lộ dữ liệu không được cấp quyền.

Đây là ví dụ cho **quyền sở hữu bắt buộc**. Nếu chủ sở hữu, nhóm, quản trị viên, tenant và quyền chia sẻ có quy tắc khác, viết lại policy Java và kiểm thử rõ ràng; không ghép công thức từ client.

### Khi trực tiếp sử dụng API SpEL

Nếu chức năng thật sự cần SpEL cho **biểu thức do ứng dụng định nghĩa**, parse cú pháp cố định và đưa các giá trị động vào `EvaluationContext` bằng biến:

```java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

ExpressionParser parser = new SpelExpressionParser();

// Tin cậy vì chuỗi do lập trình viên định nghĩa.
Expression fixed = parser.parseExpression("#candidate == #expected");

String rawCandidate = inputFromRequest; // giá trị có thể có dấu nháy, ngoặc...
String expected = valueFromTrustedSource;

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("candidate", rawCandidate);
context.setVariable("expected", expected);

boolean matches =
    Boolean.TRUE.equals(fixed.getValue(context, Boolean.class));
```

Đây là **đoạn trong ứng dụng đã có dependency `spring-expression`**, không phải chương trình Java độc lập. Nội dung `rawCandidate` chỉ được đưa vào biến `#candidate`, không được ghép vào `"#candidate == #expected"` và không được parse lần thứ hai. Với phép so sánh đơn giản, Java thuần như `rawCandidate.equals(expected)` thường còn rõ ràng hơn và không cần SpEL.

**Lưu ý:** `StandardEvaluationContext` hỗ trợ những khả năng mạnh; ví dụ trên chỉ an toàn đối với injection vì **chuỗi biểu thức là cố định và đáng tin cậy**. Không suy luận rằng đặt biến làm mọi hành vi liên quan đến đối tượng hay dữ liệu tự nhiên an toàn. Chức năng authorization vẫn phải dùng nguồn dữ liệu và điều kiện đáng tin cậy.

## 5. Không nhầm ba tình huống bảo mật khác nhau

| Tình huống | Điều gì có thể sai? | Cách phòng ngừa |
| --- | --- | --- |
| Input trở thành chuỗi được đưa vào `parseExpression` | **SpEL injection**: người dùng thay đổi cấu trúc/hành vi biểu thức | Không parse biểu thức do người dùng tạo; dùng chính sách cố định và biến dữ liệu |
| Input chỉ là biến `#requestedRole` trong biểu thức cố định | Không có cú pháp SpEL bị chèn, nhưng người dùng có thể tự chọn quyền cần kiểm tra | Nhà phát triển xác định quyền yêu cầu; không để client chọn chính sách |
| Input là `#ownerId` rồi so với ID do client tự khai | Không nhất thiết có injection, nhưng có thể có **IDOR / sai kiểm tra sở hữu** | Lấy owner/tenant/ACL thực từ database và xác thực phía server |

Ví dụ đặc biệt nguy hiểm về **logic** dù cú pháp SpEL không bị injection:

```java
// Sai chính sách nếu caller được chọn vai trò phải có:
@PreAuthorize("hasRole(#requestedRole)")
public void execute(String requestedRole) {
    // ...
}
```

Người dùng có thể chọn một role thấp mà mình vốn có, thay vì role cao do nghiệp vụ yêu cầu. Cách đúng khi hành động chỉ dành cho admin:

```java
@PreAuthorize("hasRole('ADMIN')")
public void executeAdminAction() {
    // ...
}
```

Ngược lại, nếu việc kiểm tra dựa trên tài nguyên cụ thể, cố định biểu thức dùng bean policy: `@PreAuthorize("@policy.canRead(authentication, #id)")`. Đừng tự động coi "có dùng `#arg`" là đủ an toàn: phải xem **`#arg` có được tin để quyết định điều gì**.

## 6. Chọn chính sách từ một tập cố định, không nhận mã tùy ý

Giả sử API cho phép người dùng yêu cầu hành động `view` hoặc `download`. Trường `action` là **nhãn lựa chọn** chứ không phải chuỗi biểu thức Spring:

```java
public boolean mayPerform(
        String action,
        Authentication authentication,
        Long documentId) {
    if (action == null) {
        return false;
    }

    return switch (action) {
        case "view" -> policy.canRead(authentication, documentId);
        case "download" -> policy.canDownload(authentication, documentId);
        default -> false;
    };
}
```

Đây là đoạn thuộc một service có bean `policy`, không phải chương trình độc lập. Với nhánh mặc định `false`, hành động lạ bị từ chối. Mỗi hàm Java vẫn thực hiện kiểm tra quyền thực, không chỉ dựa trên việc tên action nằm trong allowlist. Có thể dùng `enum` để loại bỏ chuỗi tự do và xác minh đầu vào trước khi đến service.

Nếu một sản phẩm muốn người dùng lọc danh sách, hãy thiết kế đầu vào dữ liệu có cấu trúc, ví dụ `{field: "status", operator: "eq", value: "OPEN"}`. Server chỉ chấp nhận `field` và `operator` trong danh sách được định nghĩa, chuyển chúng thành tiêu chí truy vấn/query API bằng code. **Không chuyển toàn bộ biểu thức do client cung cấp thành SpEL**. Cần kiểm tra riêng quyền truy cập vào các trường và tài nguyên của từng kết quả.

## 7. `SimpleEvaluationContext`, escaping và validation có thay thế được thiết kế đúng không?

### `StandardEvaluationContext` so với `SimpleEvaluationContext`

- `StandardEvaluationContext` mở đầy đủ nhiều khả năng của ngôn ngữ SpEL và cơ chế phản chiếu; **không dùng để chạy biểu thức đến từ nguồn không tin cậy**.
- `SimpleEvaluationContext` hạn chế tập tính năng và thường được dùng cho bài toán data binding, chẳng hạn bỏ tham chiếu type, constructor, bean; tuy nhiên Spring Framework lưu ý tính hạn chế này không phải **bảo đảm an toàn tuyệt đối** cho biểu thức không tin cậy. Những đối tượng, thuộc tính, phương thức hay hàm được công bố trong context vẫn cần xem xét chặt chẽ.

Vì vậy, **không đổi từ `StandardEvaluationContext` sang `SimpleEvaluationContext` rồi kết luận đã an toàn để cho người dùng nhập SpEL tùy ý**. Hướng ưu tiên là không parse input như ngôn ngữ biểu thức. Nếu một yêu cầu đặc biệt bắt buộc phải dùng tập biểu thức do bên ngoài cung cấp, cần mô hình đe dọa chuyên biệt, lớp đánh giá hạn chế, đối tượng chuyên dùng, danh sách tính năng được phép và thẩm định bảo mật; vẫn phải nhận thức rủi ro còn lại.

### Vì sao chỉ escape dấu nháy là không đủ?

Một giải pháp vá nhanh thường là:

```java
// Không coi đây là cơ chế phòng ngừa SpEL injection hoàn chỉnh.
String sanitized = userInput.replace("'", "''");
String expression = "someProperty == '" + sanitized + "'";
```

Ngay cả khi việc quote tạo được một string literal đúng trong trường hợp nhất định, thiết kế này vẫn dễ hỏng khi có nhiều nơi ghép input (ngoặc, tên thuộc tính, tên hàm, thứ tự toán tử, lồng template...) và không ngăn lỗi logic cấp quyền do người dùng tự chọn chính sách. **Sử dụng biến hoặc Java API đã định kiểu thay cho dựng chuỗi biểu thức** là lựa chọn mặc định.

Validation cũng không phải "bật tắt" quyền thực thi: giới hạn độ dài, định dạng, danh sách action là kiểm tra hữu ích cho dữ liệu, nhưng **không cấp quyền biến một chuỗi tự do thành mã SpEL**. Khi phát hiện cấu hình rule bị lỗi, nên từ chối và ghi nhận có kiểm soát, không tự trả `true` hay nới điều kiện để hệ thống vẫn chạy.

## 8. Annotation tĩnh và template của Spring Security

Có một phân biệt dễ nhầm: annotation Java thông thường dùng giá trị được xác định khi biên dịch:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public Invoice readInvoice(Long invoiceId) {
    // ...
}
```

Chuỗi trên **không tự nối giá trị tham số HTTP vào mã annotation**. `#invoiceId` là một biến của ngữ cảnh phương thức. Không thể truyền một giá trị request bất kỳ thành giá trị annotation tại thời điểm chạy theo cách Java annotation thông thường hoạt động.

Spring Security cũng hỗ trợ **templating meta-annotation** khi cấu hình `AnnotationTemplateExpressionDefaults`. Ví dụ tài liệu chính thức có pattern:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface HasRole {
    String value();
}
```

Với `@HasRole("ADMIN")` trong mã nguồn, placeholder `{value}` đến từ metadata annotation do nhà phát triển kiểm soát. Khi dùng template:

- Xác nhận nguồn của mọi phần thay thế là **metadata được kiểm soát**; không mở giao diện cho client/bản ghi do user sửa để điền trực tiếp nội dung thành SpEL.
- Chú ý quote literal đúng theo cú pháp template và các kiểu giá trị (chuỗi đơn, danh sách, tên biến); kiểm thử kết quả sau khi template expand.
- Nếu nguồn cấu hình bên ngoài chứa các rule nghiệp vụ, nên chuyển chúng thành enum/cấu trúc dữ liệu và xử lý bằng policy Java hoặc authorization manager có kiểm soát.

Không coi cú pháp `{value}` của template là bằng chứng rằng Spring đã tự "parameterize" mọi nội dung: **template replacement sinh ra mã biểu thức**, khác với việc truyền giá trị runtime vào biến `#value`.

## 9. Ví dụ Java 17 chạy độc lập: dữ liệu độc hại không được thi hành

Ví dụ này mô phỏng chính sách Java với dữ liệu tài nguyên từ server. Nó **không chạy SpEL** và không cần Spring, nhằm chứng minh một chuỗi có hình dạng toán tử vẫn là dữ liệu khi chương trình không đem nó đi parse.

Lưu mã đúng tên `TrustBoundaryDemo.java`:

```java
import java.util.Set;

public class TrustBoundaryDemo {
    record Actor(String username, String tenantId, Set<String> authorities) {}
    record Document(long id, String tenantId, String ownerUsername) {}

    static boolean canRead(Actor actor, Document document) {
        return actor.authorities().contains("document:read")
            && actor.tenantId().equals(document.tenantId())
            && actor.username().equals(document.ownerUsername());
    }

    public static void main(String[] args) {
        String untrustedText = "or true";
        Actor bob = new Actor(
            "bob", "tenant-a", Set.of("document:read"));
        Actor alice = new Actor(
            "alice", "tenant-a", Set.of("document:read"));

        Document aliceDoc = new Document(1, "tenant-a", "alice");
        Document otherTenantDoc = new Document(2, "tenant-b", "alice");

        System.out.println("Untrusted input: " + untrustedText);
        System.out.println("Bob reads Alice doc: "
            + canRead(bob, aliceDoc));
        System.out.println("Alice reads own doc: "
            + canRead(alice, aliceDoc));
        System.out.println("Alice reads other tenant doc: "
            + canRead(alice, otherTenantDoc));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac TrustBoundaryDemo.java
java TrustBoundaryDemo
```

Stdout:

```text
Untrusted input: or true
Bob reads Alice doc: false
Alice reads own doc: true
Alice reads other tenant doc: false
```

Không có nơi nào ghép `untrustedText` vào code để phân tích. Giá trị được in ra nhưng không được dùng làm quyền, và kết quả từ chính sách vẫn phụ thuộc vào authority, tenant, owner tin cậy. Điều này cũng cho thấy rằng **kiểm tra đầu ra không có injection** và **xác thực quyền tài nguyên** là hai việc phải cùng đạt được.

## 10. Kiểm thử quan trọng cho ứng dụng thật

### Test đường parse và các giá trị đặc biệt

Với chức năng chấp nhận chuỗi từ client, gửi các trường hợp: dữ liệu trống, `null`, dấu nháy đơn/đôi, dấu ngoặc, chuỗi `and`/`or`/`not`, tên property, nội dung giống lệnh gọi hàm, khoảng trắng dài và chuỗi Unicode. Kỳ vọng:

1. Những chuỗi đó được xử lý như **giá trị**, không làm thay đổi quy tắc phân quyền.
2. Parser `parseExpression` **không được nhận** nội dung có nguồn từ request hay từ dữ liệu người dùng có thể sửa.
3. Input không hợp lệ bị từ chối theo quy tắc dữ liệu; không có fallback "lỗi parse thì cho phép".
4. Không lộ stack trace, dữ liệu context, tên bean hoặc thông tin tài nguyên nhạy cảm cho client.
5. Cùng một danh tính và tài nguyên nhưng khác chuỗi input không được tự động nâng quyền.

Với đoạn SpEL cố định `#candidate == #expected`, test đưa một chuỗi giống mã vào biến `candidate` phải cho kết quả như phép so sánh chuỗi thông thường; không có việc parse lại nội dung biến.

### Test quyền thực tế

Tạo dữ liệu kiểm thử gồm nhiều tenant, owner, role và authority; kiểm tra cho phép/từ chối theo bảng:

| Người gọi | Authority | Tài nguyên | Kết quả mong đợi |
| --- | --- | --- | --- |
| Alice | `document:read` | Tài liệu của Alice, cùng tenant | Cho phép |
| Bob | `document:read` | Tài liệu của Alice, cùng tenant | Từ chối theo chính sách owner |
| Alice | `document:read` | Tài liệu tenant khác | Từ chối |
| Alice | Không có `document:read` | Tài liệu của Alice | Từ chối |
| Anonymous | Không có quyền | Bất kỳ tài liệu | Từ chối |

Đối với method security, chạy test qua **Spring-managed bean/proxy** vì lời gọi nội bộ `this.method()` có thể bỏ qua advice. Khi dùng `@WithMockUser` hoặc test security context, xác minh đúng authority và response của method, không chỉ gọi trực tiếp hàm policy trong một unit test.

### Rà soát codebase

Tìm những nơi tạo và đánh giá SpEL, đặc biệt đường dữ liệu truyền từ controller, request, database, queue hoặc cấu hình bên ngoài tới:

- `SpelExpressionParser` / `ExpressionParser.parseExpression(...)`.
- `Expression.getValue(...)`, `EvaluationContext`, `StandardEvaluationContext`, các bean resolver hay method resolver tùy biến.
- `String.format(...)`, phép `+`, `StringBuilder` hoặc template tạo ra chuỗi chính sách.
- Authorization manager tự viết, biểu thức đọc từ database, tính năng rule builder và meta-annotation template.

Việc nhìn thấy `parseExpression` **không đủ** để kết luận có lỗ hổng; cần truy ngược nguồn tạo expression text và quyền của người cung cấp. Tương tự, một `@PreAuthorize` tĩnh dùng `#arg` không tự động bị injection. Tuy nhiên, mọi nơi nhận **cú pháp expression** từ nguồn không tin cậy phải được coi là một điểm cần sửa trước khi sử dụng cho phân quyền.

## 11. Hướng xử lý khi phát hiện code đang parse input người dùng

1. **Dừng xem input là công thức:** xác định dữ liệu người dùng cần cung cấp thực sự là gì: ID, từ khóa, operator lọc, loại hành động hay mã quyền.
2. **Định nghĩa lại hợp đồng API:** nhận giá trị nguyên thủy, enum hoặc JSON có schema rõ; bỏ trường cho nhập "SpEL tùy ý".
3. **Chuyển chính sách sang code đáng tin cậy:** dùng `@PreAuthorize` cố định, bean Java policy hoặc AuthorizationManager được triển khai và review.
4. **Ràng buộc quyền với tài nguyên:** lấy owner, tenant, membership/ACL từ server/database; áp dụng điều kiện quyền trong truy vấn nếu danh sách lớn.
5. **Không dùng evaluator mạnh cho input tự do:** đặc biệt không đưa chuỗi user vào `StandardEvaluationContext` dưới dạng expression. Giới hạn context chỉ là biện pháp bổ trợ và không thay thế việc bỏ parse input.
6. **Xử lý lỗi theo hướng từ chối:** rule lạ, action lạ, thiếu dữ liệu quyền hoặc lỗi xác minh phải dẫn đến từ chối an toàn theo hợp đồng ứng dụng.
7. **Kiểm thử hồi quy:** thêm case chuỗi có dấu nháy/toán tử, case cross-tenant, role không đủ, và kiểm tra bằng công cụ tĩnh hoặc review đường đi tới parser.
8. **Theo dõi phiên bản:** cập nhật Spring Framework, Spring Security và thành phần liên quan theo advisory chính thức; nâng cấp giúp sửa lỗ hổng sản phẩm, nhưng không thay thế việc thiết kế lại đường input→expression sai trong ứng dụng.

### Quy tắc nhớ nhanh

**Cú pháp authorization do ứng dụng kiểm soát; dữ liệu request chỉ là đối số.** Dùng `#argument` hoặc biến context để truyền giá trị vào một biểu thức cố định; tốt hơn nữa, viết kiểm tra quyền tài nguyên bằng Java và truy vấn dữ liệu đáng tin cậy. Không cho client, bản ghi có thể sửa hoặc payload từ đối tác quyết định **mã SpEL sẽ được parse và chạy**.

## Tài liệu chính thức

- [Spring Framework — SpEL Evaluation, mục Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html): phân biệt `StandardEvaluationContext` và `SimpleEvaluationContext`, cảnh báo về biểu thức không tin cậy.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): cú pháp SpEL, biến và thành phần của biểu thức.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `#argument`, bean policy và template meta-annotation.
