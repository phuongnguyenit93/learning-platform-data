# Biểu thức cho dữ liệu null, dữ liệu thiếu và điều kiện không xác định

## 1. Vì sao đây là vấn đề bảo mật?

Một biểu thức phân quyền thường đọc dữ liệu từ principal, claim trong token, tham số phương thức, bản ghi hoặc dịch vụ kiểm tra quyền. Mỗi nguồn có thể thiếu giá trị vì nhiều lý do: người dùng chưa đăng nhập, không có claim tenant, request không truyền ID, trường của đối tượng là `null`, dữ liệu chưa đồng bộ hoặc dịch vụ quyền bị lỗi.

Nếu biểu thức được viết với giả định mọi giá trị đều tồn tại, kết quả có thể là lỗi đánh giá SpEL, trả kết quả không mong muốn hoặc nghiêm trọng hơn là **cấp quyền khi thiếu căn cứ**.

Ví dụ sai về ý nghĩa:

~~~java
@PreAuthorize("#documentId == null or hasAuthority('document:read')")
~~~

Khi `documentId == null`, vế trái đúng và toàn biểu thức đúng, dù người dùng **không** có quyền đọc. Thiếu dữ liệu đã vô tình trở thành lý do cho phép.

Ví dụ có ý nghĩa rõ hơn:

~~~java
@PreAuthorize("#documentId != null and hasAuthority('document:read')")
~~~

Biểu thức sau chỉ là ví dụ về điều kiện cần; quyền `document:read` vẫn chưa chứng minh người dùng được đọc **tài liệu cụ thể**. Nếu đó là tài nguyên riêng, cần thêm kiểm tra owner, tenant hoặc ACL thực tế.

**Quy tắc cốt lõi:** chỉ cấp quyền khi có đủ bằng chứng hợp lệ để kết luận **ALLOW**. Giá trị thiếu, `null`, không xác minh được hoặc hệ thống đánh giá lỗi **không được tự biến thành ALLOW**. Có thể từ chối hoặc báo lỗi kỹ thuật tùy hợp đồng API, nhưng không tiếp tục thao tác đặc quyền.

## 2. Ba trường hợp phải phân biệt

| Trường hợp | Ý nghĩa | Ví dụ | Cách xử lý khi dùng làm điều kiện cấp quyền |
|---|---|---|---|
| `null` | Có biến/trường nhưng giá trị Java là `null` | `request.ownerId() == null` | Kiểm tra rõ; thiếu thuộc tính bắt buộc thì từ chối |
| Dữ liệu **thiếu** | Không có khóa, claim, tham số được bind hoặc bản ghi | JWT không có claim `tenant_id`; map không có khóa | Phân biệt absent với present-null khi cần log/validate, nhưng không suy ra quyền |
| Điều kiện **chưa xác định** (indeterminate) | Chưa thể kết luận quyền vì phụ thuộc chưa có hoặc kiểm tra lỗi | Permission service timeout; nguồn ACL không truy cập được | Không cấp quyền; chọn DENY hoặc báo sự cố có kiểm soát theo chính sách |

Chúng không phải một khái niệm duy nhất:

- `null` là một giá trị/đối tượng tham chiếu trong Java và SpEL.
- “Thiếu” có thể là lỗi bind tham số SpEL, thiếu key trong `Map`, thiếu claim trong token, hoặc không tìm thấy tài nguyên. Một số API ánh xạ “thiếu” thành `null`; một số ném exception.
- “Không xác định” là **trạng thái quyết định nghiệp vụ** khi bằng chứng chưa đủ. Spring Security không mặc định có toán tử SpEL ba giá trị `ALLOW/DENY/UNKNOWN`; ứng dụng phải xác định rõ cách xử lý.

Đừng nhầm “không có quyền” với “không biết có quyền hay không”. Cả hai đều **không đủ điều kiện cấp quyền**, nhưng phân loại khác nhau giúp trả mã HTTP, theo dõi lỗi vận hành và kiểm thử đúng.

## 3. SpEL xử lý null như thế nào?

Trong method security, các annotation như `@PreAuthorize` và `@PostAuthorize` dùng Spring Expression Language (SpEL). SpEL hỗ trợ literal `null`, phép so sánh, logic boolean, toán tử ba ngôi, Elvis `?:` và truy cập an toàn `?.`.

### 3.1. Kiểm tra hiện diện trước khi dùng dữ liệu

~~~spel
#documentId != null and hasAuthority('document:read')
~~~

Nếu ID bắt buộc, hãy từ chối sớm khi thiếu. Với số nguyên, tiếp tục kiểm tra hợp lệ (ví dụ ID dương); với chuỗi, kiểm tra rỗng hoặc chỉ chứa khoảng trắng nếu policy yêu cầu.

Ví dụ điều kiện lồng:

~~~spel
#request != null and #request.owner != null
    and #request.owner.id != null
    and #request.owner.id == authentication.name
~~~

Toán tử logic `and`/`or` hoạt động theo cơ chế **short-circuit**: nếu vế đầu của `and` sai, phần sau không cần đánh giá. Điều này giúp tránh truy cập thuộc tính trên `null` khi viết các guard theo đúng thứ tự.

Ngược lại, viết:

~~~spel
#request.owner.id == authentication.name and #request != null
~~~

là sai thứ tự: truy cập `#request.owner` xảy ra **trước** khi kiểm tra `#request != null`.

### 3.2. Truy cập an toàn bằng ?.

~~~spel
#request?.owner?.id
~~~

Nếu `request` hoặc `owner` là `null`, chuỗi trên trả `null` thay vì ném lỗi do dereference tại những vị trí đã có `?.`.

**Quan trọng:** `?.` không “lan” qua toàn bộ chuỗi biểu thức. Ví dụ:

~~~spel
#request?.owner.id
~~~

có thể vẫn lỗi khi `request` là `null`: phần `#request?.owner` trả `null`, nhưng phép truy cập `.id` phía sau tiếp tục được đánh giá. Hãy dùng `#request?.owner?.id` hoặc guard đầy đủ.

`?.` chỉ bảo vệ **tham chiếu null ở phép truy cập tương ứng**. Nó không tự giải quyết thuộc tính không tồn tại trên kiểu object, getter ném exception, quyền thiếu, dữ liệu không hợp lệ, hoặc lỗi dịch vụ từ xa.

Để dùng làm điều kiện bảo mật, ưu tiên tạo kết quả boolean rõ ràng:

~~~spel
#request?.owner?.id != null
    and #request.owner.id == authentication.name
~~~

Ở đây phép so sánh đầu loại bỏ trường hợp chuỗi null; phép so sánh sau chỉ chạy khi đủ dữ liệu. Với chính sách phức tạp, viết trong bean Java sẽ dễ bảo trì và dễ test hơn.

### 3.3. Elvis ?: và giá trị mặc định

~~~spel
#displayName ?: 'Anonymous'
~~~

SpEL Elvis trả giá trị bên phải khi bên trái là `null` **hoặc chuỗi rỗng**. Nó hữu ích khi tạo text/hiển thị, nhưng rất dễ nguy hiểm khi dùng làm **giá trị để cấp quyền**.

Ví dụ nguy hiểm:

~~~spel
#tenantId ?: 'public'
~~~

Nếu tenant chưa được xác minh, tự gán tenant mặc định có thể gây truy cập chéo ranh giới. Tương tự, mặc định `true` hoặc mặc định quyền “reader” khi thiếu claim là dạng **fail-open**.

Chỉ dùng default khi đặc tả nghiệp vụ thực sự định nghĩa giá trị mặc định đó là hợp lệ, được kiểm soát độc lập và **không nâng quyền**. Đối với dữ liệu bắt buộc cho authorization, thiếu giá trị nên dẫn đến từ chối hoặc lỗi xác thực/validation phù hợp.

### 3.4. Toán tử so sánh với null không thay cho kiểm tra hợp lệ

SpEL có quy tắc so sánh thứ tự với `null`: `null` được coi là “không có gì”, khác với so sánh số 0. Vì vậy, với một giá trị không null, phép `value > null` có thể trả `true`; không nên dùng `> null` để phát biểu “đã đủ điều kiện”.

Nếu policy đòi mức tuổi, hạn mức hoặc độ ưu tiên, hãy viết kiểm tra có ý nghĩa:

~~~spel
#minimumAge != null and #minimumAge >= 18
~~~

Đừng viết `#minimumAge > null` hay dựa vào chuyển kiểu/ép kiểu ngầm. Với thời gian, tiền, số nguyên dài hoặc enum, chuẩn hóa và validate đúng kiểu trước khi đánh giá.

### 3.5. Ternary có thể dùng nhưng phải xác định rõ nhánh thiếu

~~~spel
#request?.ownerId != null
    ? #request.ownerId == authentication.name
    : false
~~~

Nhánh `false` diễn đạt chính sách: **thiếu owner ID thì không cấp quyền**. Đối với biểu thức dài nhiều nhánh, thay bằng `@policyBean.can...(...)` để giảm lỗi cấu trúc.

## 4. “Không có Authentication” khác “người dùng anonymous”

Một request không được xác thực có thể đi qua các cơ chế của Spring Security theo nhiều cách:

- `Authentication` có thể không có trong security context ở một số đường gọi.
- Ứng dụng có bật anonymous authentication có thể cung cấp `AnonymousAuthenticationToken` với principal như `anonymousUser`. Vì vậy, chỉ kiểm tra `authentication != null` hoặc `principal != null` **không đủ** để kết luận đã đăng nhập.
- Một số ứng dụng dùng remember-me; yêu cầu nhạy cảm có thể cần trạng thái xác thực đầy đủ thay vì chỉ được nhận diện bằng remember-me.

Trong expression root của Spring Security:

~~~java
@PreAuthorize("isAuthenticated() and hasAuthority('document:read')")
~~~

`isAuthenticated()` có ý nghĩa là người dùng đã được xác thực theo quy tắc Spring Security; khác với việc kiểm tra đối tượng Java không null. Với use case cần loại cả remember-me, cân nhắc `isFullyAuthenticated()` theo đúng cơ chế xác thực của ứng dụng.

Khi truy cập claim hoặc thuộc tính riêng của principal, đừng mặc định `principal` luôn là `Jwt`, `UserDetails` hoặc một class tùy biến. Principal có thể khác nhau tùy cơ chế JWT, session, OAuth2 login, anonymous hoặc test security context.

Ví dụ ngắn để minh họa rủi ro:

~~~spel
principal.tenantId == #tenantId
~~~

Nếu principal không có thuộc tính `tenantId` hoặc bị đổi kiểu, có thể xảy ra lỗi SpEL. Giải pháp ổn định là chuẩn hóa principal thành **access scope** trong Java hoặc dùng bean chính sách kiểm tra kiểu, claim và trust trước khi so sánh.

## 5. Tham số phương thức có thể null hoặc “mất tên”

Trong `@PreAuthorize`, biến `#documentId` là **tên tham số method mà Spring Security tìm được**, không phải mọi lần đều tự xuất hiện. Khả năng tìm tên phụ thuộc metadata như `-parameters`, annotation `@P` hoặc các cơ chế khám phá tham số được hỗ trợ.

Để biểu thức rõ nghĩa khi code biên dịch, có thể chỉ định tên tường minh:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentCommandService {
    @PreAuthorize("#documentId != null and hasAuthority('document:read')")
    public String read(@P("documentId") Long id) {
        return "document-" + id;
    }
}
~~~

Ví dụ trên là **đoạn mã tích hợp Spring**. Nó chỉ minh họa binding và kiểm tra quyền thao tác, **không đủ** làm phân quyền theo từng bản ghi. Nếu thiếu tên tham số trong expression, biến có thể không được resolve như dự kiến hoặc expression không hoạt động đúng; không nên “sửa” bằng cách biến trường hợp thiếu thành cho phép.

Các trường hợp cần kiểm thử riêng:

1. Tham số thực tế được truyền `null` và expression đánh giá `#documentId == null`.
2. Tên tham số không discover được, expression tham chiếu sai tên hoặc sai case.
3. Tham số là object khác kiểu dự kiến hoặc nested property không tồn tại.
4. Annotation bị bỏ qua do self-invocation qua `this.method()` thay vì gọi qua Spring proxy.
5. Bean policy chưa được đăng ký hoặc expression bean reference bị sai.

Không nên quy hết các trường hợp này về “người dùng không có quyền”; lỗi cấu hình hoặc lỗi expression có thể cần được phát hiện như lỗi hệ thống qua log/monitoring, trong khi hành động đặc quyền vẫn không được phép thực thi.

## 6. Dữ liệu thiếu trong Map, JSON và JWT claims

Một map có ít nhất ba trạng thái quan trọng:

~~~java
Map<String, String> claims = new HashMap<>();
// 1. claims.containsKey("tenant_id") == false: thiếu khóa
claims.put("tenant_id", null);
// 2. claims.containsKey("tenant_id") == true, get(...) == null
claims.put("tenant_id", "north");
// 3. khóa tồn tại với giá trị "north"
~~~

`Map.get(key) == null` không phân biệt trường hợp 1 và 2. Nếu chính sách cần thống kê, validation hoặc migration dữ liệu, dùng `containsKey` và kiểm tra value riêng. Với quyết định quyền, cả hai trạng thái thiếu giá trị tenant hợp lệ đều phải **không đủ điều kiện cấp quyền**.

Một biểu thức minh họa khi `claims` là Map tin cậy được đặt vào evaluation context:

~~~spel
#claims != null
    and #claims.containsKey('tenant_id')
    and #claims['tenant_id'] != null
    and #claims['tenant_id'] == #trustedTenant
~~~

Đây là **cú pháp SpEL minh họa**; biến `#claims` và `#trustedTenant` chỉ tồn tại nếu code thực sự bind chúng vào evaluation context. Không giả định hai biến có sẵn trong mọi `@PreAuthorize`. Ngoài việc hiện diện, nguồn claim phải được xác thực chữ ký, issuer/audience và nghĩa của claim theo cấu hình ứng dụng.

Đối với JWT, không sử dụng dữ liệu header hoặc payload **chưa được xác minh** làm authority/tenant scope. Khi claim tenant thiếu, không được lấy tenant từ query parameter do client gửi để thay thế mà không kiểm tra membership/quyền.

Với JSON tree, thư viện có thể phân biệt “missing node”, “null node” và giá trị chuỗi rỗng. Đây là khác biệt ở **cấu trúc dữ liệu nguồn**; không phải ba cấp quyền mặc định. Chuẩn hóa thành một mô hình domain với trường bắt buộc được validate trước khi tính toán quyền.

## 7. Optional, chuỗi rỗng và giá trị sentinel

### Optional không đồng nghĩa null

Trong Java, `Optional.empty()` là một object có tồn tại nhưng không chứa giá trị; khác với tham chiếu `null`. Không nên viết expression gọi `#maybeOwner.get()` khi chưa chắc có phần tử; nó có thể ném `NoSuchElementException`.

Hành vi safe navigation trên `Optional` phụ thuộc phiên bản Spring Framework: cơ chế tự unwrap `Optional` trong các phép null-safe được giới thiệu ở Spring Framework 7.0. Nếu ứng dụng dùng Spring Framework 6.x, **đừng giả định** `#optional?.name` hoạt động như khi Optional tự được mở. Với quyền quan trọng, hãy unwrap và kiểm tra tường minh trong Java hoặc bean policy, rồi trả một `boolean` rõ ràng.

~~~java
Optional<String> owner = repository.findOwnerName(documentId);
boolean ownerMatches = owner
        .map(name -> name.equals(authenticatedUsername))
        .orElse(false);
~~~

Đây là đoạn Java minh họa khi `repository` và `authenticatedUsername` đã được xác định tin cậy; không phải chương trình độc lập. Điều kiện owner khớp chỉ đủ nếu chính sách owner-only thật sự đúng và tenant/resource scope cũng được kiểm tra đầy đủ.

### Chuỗi rỗng không giống vắng mặt trong mọi ngữ cảnh

Các giá trị `null`, `""`, `"   "` và `"unknown"` có thể cần cách xử lý khác nhau:

- `null` và chuỗi rỗng: thông thường không có ID/tenant hợp lệ.
- Chỉ có khoảng trắng: cũng không phải định danh hợp lệ nếu không có quy tắc chuẩn hóa.
- `"unknown"`, `"N/A"`, `"guest"`: có thể là **giá trị thật** trong dữ liệu, không phải null; phải xử lý theo contract rõ ràng, tránh tình cờ trùng một principal hoặc tenant hợp lệ.

Không dùng sentinel chung như `"public"` hay `"default"` để cấp quyền đọc khi tenant/owner bị thiếu. Nếu tài nguyên thật sự public, phải có **cờ/chính sách public được quản trị**, không suy ra “public” từ một trường owner null.

## 8. Không nhầm SpEL với logic ba giá trị của SQL

Trong SQL, biểu thức liên quan `NULL` có thể cho ra `UNKNOWN` theo **three-valued logic**:

| Biểu thức SQL | Kết quả |
|---|---|
| `5 = NULL` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `UNKNOWN AND FALSE` | `FALSE` |
| `UNKNOWN OR TRUE` | `TRUE` |
| `NOT UNKNOWN` | `UNKNOWN` |

Trong mệnh đề `WHERE`, SQL chỉ giữ các hàng mà predicate là `TRUE`; `FALSE` và `UNKNOWN` đều không được chọn. Ví dụ:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_user;
~~~

Nếu `tenant_id` hoặc `owner_username` của một hàng là NULL, các điều kiện so sánh bằng thông thường sẽ không đúng và bản ghi không xuất hiện. Đây có thể hỗ trợ hướng fail-closed, **nếu** bản thân các bind parameter là phạm vi quyền được xác minh.

Nhưng SQL `UNKNOWN` **không phải** quyết định `INDETERMINATE` của permission service. Một loại là kết quả toán tử SQL với NULL; loại còn lại là thiếu bằng chứng hoặc lỗi truy vấn/quyết định chính sách ở tầng ứng dụng.

Không tự thêm:

~~~sql
WHERE owner_username = :authenticated_user
   OR owner_username IS NULL
~~~

trừ khi đặc tả thực sự định nghĩa **các tài liệu owner NULL là public** và đã có quy định bảo vệ khác. “NULL không thuộc ai” không có nghĩa “ai cũng được đọc”.

## 9. Các annotation thường gặp và cách kiểm tra null

### 9.1. @PreAuthorize: kiểm tra trước hành động

~~~java
@PreAuthorize(
    "isAuthenticated() and #request != null " +
    "and #request.documentId != null " +
    "and hasAuthority('document:write') " +
    "and @documentPolicy.canWrite(authentication, #request)"
)
public void update(@P("request") UpdateDocumentRequest request) {
    documentService.update(request);
}
~~~

Đây là mẫu tích hợp, phụ thuộc các bean/class domain của ứng dụng. Cần bảo đảm bean policy **không tin** tenant/owner từ request do client tự nhập và thực hiện kiểm tra resource thật tại nguồn. SpEL `and` dùng short-circuit nên bean không bị gọi nếu các điều kiện cần trước đó sai.

Khi policy phức tạp, chuyển phần kiểm tra nested property, định danh, tenant và ACL vào một phương thức Java để giảm số lần lặp và cải thiện test.

### 9.2. @PostAuthorize: dữ liệu trả về null

~~~java
@PostAuthorize(
    "returnObject != null " +
    "and returnObject.ownerUsername == authentication.name"
)
public DocumentView findOne(Long id) {
    return documentService.findOne(id);
}
~~~

`returnObject` là giá trị sau khi method chạy. Guard trước thuộc tính ngăn lỗi truy cập null. Tuy nhiên, cần phân biệt **không tìm thấy bản ghi** và **không có quyền xem** theo hợp đồng API, cân nhắc đặt predicate tenant/ACL trong truy vấn detail để không tải dữ liệu ngoài quyền từ đầu. `@PostAuthorize` có thể từ chối toàn bộ kết quả, không lọc từng trường.

### 9.3. @PostFilter: phần tử null trong danh sách

~~~java
@PostFilter(
    "filterObject != null " +
    "and filterObject.ownerUsername != null " +
    "and filterObject.ownerUsername == authentication.name"
)
public List<DocumentView> findSmallPreview() {
    return previewService.loadBoundedPreview();
}
~~~

Guard trên ngăn phần tử null gây lỗi dereference. Nó không làm collection an toàn nếu nguồn trả dữ liệu nhạy cảm đã bị đưa vào cache/log; không tự sửa tổng số hay phân trang của truy vấn. Chỉ dùng sau khi đã biết kiểu collection được hỗ trợ và tập đã **hữu hạn, nhỏ**.

### 9.4. @PreFilter: tham số collection có phần tử null

~~~java
@PreFilter(
    "filterObject != null " +
    "and filterObject.ownerUsername == authentication.name"
)
public void process(List<DocumentInput> inputs) {
    // inputs chỉ còn phần tử thỏa biểu thức theo interceptor
}
~~~

Mã trên minh họa annotation ở ranh giới Spring method security, không phải ứng dụng runnable độc lập. Hãy kiểm tra kiểu collection, mutability và contract của method; việc lọc có thể thay đổi hoặc tạo collection theo cơ chế framework. Với thao tác ghi hàng loạt, **lọc im lặng** các phần tử bị từ chối không phải lúc nào cũng phù hợp: nhiều API cần từ chối **toàn bộ yêu cầu** nếu có bất kỳ item không hợp lệ để tránh người gọi hiểu nhầm rằng toàn bộ batch đã xử lý.

## 10. Đưa policy phức tạp vào bean với kết quả boolean rõ ràng

Khi dữ liệu nullable đến từ nhiều hệ thống, biểu thức dài như `#request?.user?.membership?.tenant?.id` khó kiểm soát. Một bean chính sách giúp tách **kiểm tra cấu trúc**, **nguồn tin cậy**, **quyền nghiệp vụ** và **xử lý lỗi**.

Ví dụ Spring Security với bean policy:

~~~java
import java.util.UUID;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final TrustedTenantResolver tenantResolver;
    private final DocumentPermissionService permissionService;

    public DocumentPolicy(
            TrustedTenantResolver tenantResolver,
            DocumentPermissionService permissionService) {
        this.tenantResolver = tenantResolver;
        this.permissionService = permissionService;
    }

    public boolean canWrite(
            Authentication authentication, UpdateDocumentRequest request) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken
                || request == null
                || request.documentId() == null
                || request.documentId() <= 0) {
            return false;
        }

        UUID tenantId = tenantResolver.resolveVerifiedTenant(authentication);
        if (tenantId == null) {
            return false;
        }

        Boolean granted = permissionService.canWrite(
                tenantId, authentication.getName(), request.documentId());
        return Boolean.TRUE.equals(granted);
    }
}
~~~

Đây là mã tích hợp vào một dự án Spring, giả định ứng dụng định nghĩa `TrustedTenantResolver`, `DocumentPermissionService` và `UpdateDocumentRequest`. Nếu request là Java record, `request.documentId()` hợp lệ; nếu dùng POJO, đổi sang accessor tương ứng.

Hợp đồng bắt buộc:

- `TrustedTenantResolver` chỉ nhận tenant từ danh tính/token được xác minh hoặc mapping server tin cậy; thiếu tenant trả null hoặc báo lỗi theo hợp đồng.
- `DocumentPermissionService.canWrite(...)` phải kiểm tra quyền đối với **đúng document trong đúng tenant**, không chỉ kiểm tra user có một role chung.
- `Boolean.TRUE.equals(granted)` chỉ cấp quyền nếu kết quả là `Boolean.TRUE`; `false` và `null` không được cấp.
- Với lỗi I/O, timeout hoặc dịch vụ quyền mất kết nối, đừng bắt mọi exception rồi trả `true`. Có thể trả quyết định từ chối hoặc báo lỗi hệ thống phù hợp, nhưng thao tác ghi không được diễn ra nếu chưa có bằng chứng cho phép.
- Chặn lời gọi nội bộ bypass proxy nếu phụ thuộc `@PreAuthorize`: test qua Spring bean được quản lý hoặc đưa policy thành guard tường minh trong luồng không đi qua proxy.

Ở endpoint, mã của controller/service phải validate request schema và phân biệt lỗi input thiếu bắt buộc với từ chối quyền. Lời gọi policy không nên “đoán” user/tenant từ dữ liệu còn thiếu.

## 11. Quyết định ba trạng thái ở tầng domain

Với quyền dựa trên dịch vụ ngoài, một boolean đôi khi không đủ để giải thích kết quả. Domain có thể giữ trạng thái:

- **ALLOW:** có đầy đủ bằng chứng, chính sách cho phép.
- **DENY:** bằng chứng rõ ràng không thỏa chính sách hoặc thiếu trường bắt buộc.
- **INDETERMINATE:** chưa thể có quyết định vì hệ thống phụ thuộc lỗi hoặc chưa cung cấp được kết quả.

Tầng thực thi vẫn phải map thành “cấp quyền?” theo tiêu chí duy nhất: **chỉ ALLOW mới được thực hiện**. Nên giữ lý do `INDETERMINATE` trong log/metrics an toàn (không đính kèm token hoặc dữ liệu nhạy cảm), có thể báo 503/5xx cho sự cố dịch vụ quyền thay vì nói dối rằng người dùng chắc chắn bị cấm. Tuy nhiên, lỗi kỹ thuật không được trở thành một đường **bypass** authorization.

Ví dụ Java 17 **độc lập**, không cần Spring, để minh họa:

Tệp `NullPolicyDemo.java`:

~~~java
public class NullPolicyDemo {
    enum Decision { ALLOW, DENY, INDETERMINATE }

    record Input(
            String actor,
            String tenant,
            String owner,
            Boolean permissionVerified) {
    }

    static Decision decide(Input input) {
        if (input == null
                || input.actor() == null || input.actor().isBlank()
                || input.tenant() == null || input.tenant().isBlank()
                || input.owner() == null || input.owner().isBlank()) {
            return Decision.DENY;
        }

        if (!input.actor().equals(input.owner())) {
            return Decision.DENY;
        }

        if (input.permissionVerified() == null) {
            return Decision.INDETERMINATE;
        }
        return input.permissionVerified()
                ? Decision.ALLOW
                : Decision.DENY;
    }

    static void printDecision(String label, Input input) {
        Decision decision = decide(input);
        System.out.println(label + ": " + decision
                + ", grant=" + (decision == Decision.ALLOW));
    }

    public static void main(String[] args) {
        printDecision("complete",
                new Input("an", "tenant-1", "an", true));
        printDecision("other-owner",
                new Input("an", "tenant-1", "binh", true));
        printDecision("missing-owner",
                new Input("an", "tenant-1", null, true));
        printDecision("unknown-permission",
                new Input("an", "tenant-1", "an", null));
        printDecision("no-input", null);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac NullPolicyDemo.java
java NullPolicyDemo
~~~

Stdout:

~~~text
complete: ALLOW, grant=true
other-owner: DENY, grant=false
missing-owner: DENY, grant=false
unknown-permission: INDETERMINATE, grant=false
no-input: DENY, grant=false
~~~

Ví dụ cố ý đơn giản hóa chính sách owner + tenant có giá trị + tín hiệu permission. Trong hệ thống thật còn phải xác minh actor, mối liên hệ user–tenant, document–tenant, nguồn permission và hiệu lực cập nhật. Ý chính là **chỉ một trường hợp ALLOW được chuyển thành `grant=true`**.

## 12. Bảng quyết định: thiếu dữ liệu trong các loại policy

| Dữ liệu đầu vào | Kỳ vọng khi dùng để cấp quyền | Diễn giải |
|---|---|---|
| Người dùng chưa đăng nhập | Không cấp; luồng web thường yêu cầu xác thực | Không coi `principal != null` là dấu hiệu đủ |
| Anonymous token có principal tên `anonymousUser` | Không cấp quyền riêng tư | Dùng predicate xác thực đúng nghĩa |
| Thiếu claim tenant bắt buộc | Không cấp | Không lấy tenant do client tự khai làm default |
| Đã có claim tenant nhưng chữ ký/issuer/audience không hợp lệ | Không cấp | Token chưa đáng tin dù trường có mặt |
| Tham số ID của resource null hoặc không hợp lệ | Không cấp; có thể trả lỗi input | Validation và authorization là hai bước khác nhau |
| Owner null trong record riêng tư | Không cấp theo policy owner-only | Không coi null owner là public |
| ACL trả false | Không cấp | Quyết định DENY rõ ràng |
| ACL trả null hoặc không thể trả lời | Không cấp; xử lý lỗi/INDETERMINATE | Không tự suy đoán “chắc là được” |
| Permission service timeout | Không thực hiện thao tác | Có thể dùng retry/circuit breaker phù hợp, không fail-open |
| Có flag `isPublic=true` được quản trị hợp lệ | Có thể cấp theo policy public thực tế | Public phải là điều kiện tường minh, không suy ra từ trường thiếu |
| Admin có authority phù hợp | Cấp chỉ trong phạm vi quy định | Admin trong tenant không tự thành admin mọi tenant |
| Dữ liệu null ở field chỉ dùng để hiển thị | Có thể có default an toàn | Null của UI khác null trong quyết định quyền |

Với HTTP API, một cách phân loại thông dụng là: request thiếu dữ liệu cấu trúc → 400; chưa xác thực → 401; đã xác thực nhưng không đủ quyền → 403; tài nguyên không tìm thấy → 404; dịch vụ quyền lỗi → 5xx phù hợp. Mã trả về cụ thể phụ thuộc thiết kế và chính sách hạn chế lộ sự tồn tại của tài nguyên. Không giả định mọi lỗi đánh giá SpEL sẽ tự chuyển thành một mã HTTP duy nhất; cần exception handling/test trong stack thực tế.

## 13. Những lỗi logic dễ biến thiếu dữ liệu thành quyền

### Sai: điều kiện OR với nhánh “thiếu”

~~~spel
#documentId == null or hasAuthority('document:read')
~~~

Nếu ID null, vế trái là true nên toàn biểu thức cho phép. **Sửa:** dùng `#documentId != null and ...`.

### Sai: mặc định tenant khi không tìm được

~~~spel
#tenantId ?: 'public'
~~~

Nếu giá trị này được dùng trực tiếp làm phạm vi đọc, thiếu tenant có thể dẫn đến đọc nhầm dữ liệu công khai hoặc xuyên tenant. **Sửa:** không tạo phạm vi quyền bằng default từ dữ liệu không xác minh.

### Sai: kiểm tra principal khác null để kết luận đã đăng nhập

~~~spel
principal != null
~~~

Anonymous authentication có thể có principal. **Sửa:** dùng `isAuthenticated()` hoặc kiểm tra authentication domain tin cậy.

### Sai: chỉ safe navigation đoạn đầu

~~~spel
#request?.owner.id == authentication.name
~~~

Nếu request null, `.id` có thể vẫn gây lỗi. **Sửa:** `#request?.owner?.id != null and ...` hoặc guard đầy đủ.

### Sai: `Map.get(...) == null` được diễn giải luôn là key absent

Một key có mặt nhưng value null cho kết quả `get` giống key thiếu. **Sửa:** dùng `containsKey` nếu cần phân biệt, rồi kiểm tra giá trị/trust.

### Sai: dùng null để đại diện cho quyết định “allow”

~~~java
return permissionService.check(id) == null;
~~~

Nếu `null` nghĩa là chưa biết, điều kiện trên lại cấp quyền khi không có kết quả. **Sửa:** chỉ cho phép khi kết quả là `Boolean.TRUE` hoặc enum `ALLOW`.

### Sai: bắt mọi lỗi của policy và cho qua

~~~java
try {
    return policyService.canRead(resourceId);
} catch (Exception ignored) {
    return true;
}
~~~

Đây là **fail-open** trước sự cố mạng, bug hoặc dữ liệu thiếu. **Sửa:** từ chối hoặc chuyển thành lỗi vận hành đã kiểm soát; không thực hiện hành động nhạy cảm.

### Sai: dùng null-safe để che giấu lỗi mô hình

`#request?.owner?.id` tránh NullPointerException, nhưng không chứng minh owner hoặc tenant hợp lệ. Nếu owner bắt buộc theo nghiệp vụ, cần validate cấu trúc và ghi nhận lỗi upstream; không chỉ âm thầm fallback.

## 14. Kiểm thử với dữ liệu null và thiếu

Nên lập ma trận test theo **giá trị đầu vào** và **kết quả dự kiến**, tránh chỉ test một trường hợp happy path:

| Tình huống | Quyết định bảo mật kỳ vọng |
|---|---|
| Authenticated user, ID hợp lệ, tenant + owner + ACL đúng | ALLOW |
| ID null | DENY / input error |
| ID bằng 0 hoặc âm nếu ID bắt buộc dương | DENY / input error |
| Owner null | DENY đối với policy owner-only |
| Tenant claim absent | DENY |
| Tenant claim present-null hoặc rỗng | DENY |
| Principal anonymous nhưng khác null | DENY đối với tài nguyên private |
| Principal khác kiểu dự kiến | DENY / cấu hình lỗi rõ ràng |
| Bean policy trả `Boolean.FALSE` | DENY |
| Bean policy trả `null` | Không cấp |
| Dependency timeout | Không cấp; xử lý sự cố |
| SpEL bind sai biến/tham số | Không thực hiện thao tác; báo lỗi cấu hình |
| Resource đã bị xóa hoặc chuyển tenant | Không cấp cho ID cũ |
| Một object trong `@PostFilter` là null | Không giữ phần tử null theo policy |
| User trong tenant A yêu cầu tài nguyên tenant B | DENY kể cả owner name trùng |

Với Spring Security, kiểm thử annotation qua bean/proxy thực sự bằng security test context có user/role khác nhau. Kết hợp unit test cho bean policy nullable và integration test để phát hiện thiếu claim/nhầm tenant ở database.

Ví dụ khung kiểm thử annotation (mã minh họa trong một dự án có Spring Security Test, không phải chương trình Java độc lập):

~~~java
@WithMockUser(username = "an", authorities = "document:read")
@Test
void shouldRejectMissingId() {
    assertThatThrownBy(() -> documentCommandService.read(null))
            .isInstanceOf(AccessDeniedException.class);
}
~~~

Các import và fixture test phụ thuộc dự án (JUnit 5, AssertJ, Spring Security Test và service được quản lý); cần cấu hình `@EnableMethodSecurity`. Vì `read(null)` có thể bị request validation chặn trước trong một đường gọi HTTP khác, test ở đây nhằm kiểm tra **method security interceptor** trên bean, không khẳng định mã HTTP cụ thể.

Nên có thêm test dùng principal anonymous, thiếu claim, SpEL variable typo, đối tượng trả về null, `Optional.empty()` (đúng hành vi ở phiên bản), permission service lỗi và trường hợp request thay đổi ngay giữa kiểm tra quyền và thao tác.

## 15. Checklist thực hành

Trước khi đưa một biểu thức phân quyền vào production:

1. Liệt kê mọi nguồn nullable/thiếu: method argument, claim, principal, record field, bean trả về, remote permission.
2. Phân loại mỗi trường bắt buộc hay tùy chọn. **Trường bắt buộc thiếu phải không được cấp quyền**.
3. Dùng `and` + guard theo đúng thứ tự hoặc `?.` xuyên suốt từng cấp cần bảo vệ.
4. Tránh dùng `?:` để mặc định owner, tenant, role, permission hoặc flag public mà không có policy rõ.
5. Xác minh principal và scope bằng security context đáng tin; anonymous không được coi là user đã xác thực chỉ vì object khác null.
6. Với map/JWT, phân biệt missing key, present-null và giá trị hợp lệ khi cần, đồng thời xác minh nguồn claim.
7. Nếu biểu thức cần nhiều điều kiện, chuyển logic sang bean policy trả boolean rõ ràng hoặc kiểu quyết định domain, với **chỉ ALLOW mới grant**.
8. Không coi lỗi đánh giá SpEL hoặc sự cố permission service là “cho phép”.
9. Kiểm tra Spring Framework/Security version, nhất là hỗ trợ safe navigation cho `Optional`.
10. Test cả dữ liệu đầy đủ, null, absent, sai kiểu, anonymous, timeout, thiếu variable, self-invocation và ranh giới tenant.
11. Tách lỗi input, từ chối quyền, không tìm thấy tài nguyên và sự cố vận hành trong telemetry/HTTP, không làm lộ thông tin nhạy cảm.
12. Áp dụng cùng nguyên tắc trong query, method security, API detail, batch và các đường gọi ngoài HTTP.

Một chính sách phân quyền an toàn phải có **chứng cứ dương tính để cấp quyền**. `null`, dữ liệu thiếu hoặc kết quả chưa xác định là tín hiệu cần xử lý rõ ràng, không phải một cách vượt qua bước kiểm tra.

## Tài liệu tham khảo

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): SpEL trong `@PreAuthorize`/`@PostAuthorize`, expression root, `@P`, tham số method và proxy.
- [Spring Framework 6.2 – Safe Navigation](https://docs.spring.io/spring-framework/reference/6.2/core/expressions/language-ref/operator-safe-navigation.html): cách dùng `?.` và chuỗi compound expression.
- [Spring Framework 6.2 – Elvis Operator](https://docs.spring.io/spring/reference/6.2/core/expressions/language-ref/operator-elvis.html): `?:` với null và chuỗi rỗng.
- [Spring Framework – SpEL Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html): các toán tử và so sánh với null.
