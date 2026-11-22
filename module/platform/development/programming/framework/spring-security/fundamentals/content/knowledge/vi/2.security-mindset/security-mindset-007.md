# Xác thực thành công không đồng nghĩa với được phép truy cập mọi dữ liệu

Một ứng dụng cho phép Mai đăng nhập thành công. Mai mở đường dẫn `GET /api/documents/101` và xem được tài liệu của chính mình. Nếu Mai đổi mã tài liệu thành `102`, ứng dụng **không được tự động trả về tài liệu 102** chỉ vì tài khoản của Mai đã đăng nhập. Tài liệu đó có thể thuộc An, thuộc một tổ chức khác, hoặc chỉ được xem bởi người có quyền đặc biệt.

Đây là một tư duy cốt lõi trong Spring Security: **xác thực (authentication) chứng minh danh tính theo cơ chế được cấu hình; phân quyền (authorization) quyết định danh tính ấy có được thực hiện một thao tác cụ thể trên tài nguyên cụ thể hay không**. Một lần xác thực thành công chỉ là điều kiện đầu vào của nhiều quyết định bảo mật.

Bài này đi từ cách suy nghĩ đến mô hình quyền trên từng dữ liệu, cách áp dụng với Spring Security và ví dụ Java 17+ có thể tự chạy. Trọng tâm là câu hỏi: **người đã đăng nhập được xem hoặc thay đổi chính xác dữ liệu nào, và ai kiểm tra điều đó?**

## 1. Phân biệt ba câu hỏi cần trả lời

Giả sử ứng dụng quản lý tài liệu có ba người dùng: Mai, An và một quản trị viên tổ chức. Mỗi tài liệu có chủ sở hữu và thuộc một tenant (tổ chức/không gian dữ liệu).

| Câu hỏi | Cơ chế thường trả lời | Ví dụ |
| --- | --- | --- |
| **Bạn là ai?** | Authentication | Yêu cầu thuộc tài khoản Mai đã xác thực |
| **Bạn được làm hành động gì?** | Authorization theo chức năng/quyền | Mai có quyền `DOC_READ` nhưng không có `DOC_DELETE` |
| **Bạn được làm điều đó trên dữ liệu nào?** | Authorization theo tài nguyên và ngữ cảnh | Mai chỉ đọc tài liệu thuộc mình trong tenant hiện tại |

Nếu chỉ giải quyết hai câu hỏi đầu, ứng dụng vẫn có thể để lộ dữ liệu khi người dùng đổi `documentId`, `userId`, `orderId`, `tenantId` trong URL hoặc nội dung request.

Một kết quả `Authentication` thường mang principal và các `GrantedAuthority`. Nó cho biết danh tính/những quyền đã được cấp theo cơ chế xác thực; nó **không chứa sẵn một lời đảm bảo rằng mọi bản ghi trong cơ sở dữ liệu đều được xem**. Quyết định cuối cùng còn phụ thuộc hành động, đối tượng, quyền sở hữu, tenant và chính sách của ứng dụng.

~~~text
Request: GET /api/documents/102
                |
                v
  [1] Có Authentication đáng tin cậy?
                |
       Không --> yêu cầu xác thực
                |
               Có
                v
  [2] Có authority DOC_READ?
                |
       Không --> từ chối
                |
               Có
                v
  [3] Document 102 có nằm trong
      phạm vi dữ liệu được phép đọc?
      (tenant, owner, chia sẻ, chính sách)
                |
       Không --> từ chối / che giấu sự tồn tại
                |
               Có
                v
        Trả về dữ liệu được phép
~~~

Điểm quan trọng ở bước [3] là **phải xét chính tài liệu 102**. Việc bước [1] và [2] thành công không thay thế bước kiểm tra phạm vi dữ liệu.

## 2. Từ quyền chung đến quyền trên từng đối tượng

Để thiết kế kiểm soát truy cập, cần phân biệt ba lớp phạm vi có thể kết hợp:

**Quyền theo chức năng (functional authorization).** Tài khoản có được gọi chức năng đọc, sửa, xóa, xuất báo cáo hay quản trị hay không? Ví dụ `DOC_READ` cho phép đi vào chức năng đọc tài liệu; `DOC_DELETE` là quyền riêng. Quyền xem không được tự suy ra quyền sửa.

**Quyền theo đối tượng (object-level authorization).** Người này có được đọc **tài liệu có ID 102** không? Dù cùng có quyền `DOC_READ`, Mai và An vẫn có thể nhìn thấy hai tập tài liệu khác nhau. Điều kiện có thể là tài liệu thuộc về mình, được chia sẻ cho mình, hoặc được giao xử lý.

**Quyền theo phạm vi dữ liệu (data scope).** Yêu cầu chỉ được truy cập tổ chức, dự án, phòng ban hoặc nhóm nào? Một quản trị viên của tenant A không mặc nhiên là quản trị viên dữ liệu tenant B. Quyền `DOC_READ_ALL` nếu được sử dụng trong ví dụ này được định nghĩa rõ là “đọc tất cả tài liệu **trong tenant của mình**”, không phải trong toàn hệ thống.

Một mô hình học tập tối giản:

| Người gọi | Đã xác thực | Authorities | Tenant | Chủ sở hữu tài liệu | Tenant tài liệu | Đọc? |
| --- | --- | --- | --- | --- | --- | --- |
| Mai | Có | `DOC_READ` | A | Mai | A | Có |
| Mai | Có | `DOC_READ` | A | An | A | Không |
| Quản trị A | Có | `DOC_READ`, `DOC_READ_ALL` | A | An | A | Có |
| Quản trị A | Có | `DOC_READ`, `DOC_READ_ALL` | A | An | B | Không |
| Khách chưa đăng nhập | Không | Không đủ | A | Mai | A | Không |

Bảng này là **chính sách được chọn cho ví dụ**, không phải luật có sẵn của Spring Security. Trong sản phẩm khác, tài liệu có thể được chia sẻ cho nhóm hoặc công khai; khi đó chính sách cần mô tả và kiểm tra chính xác quyền chia sẻ tương ứng.

### Đừng coi role là quyền truy cập toàn bộ dữ liệu

`ROLE_USER`, `ROLE_MANAGER`, `ROLE_ADMIN` là nhãn vai trò. Trong Spring Security, `hasRole("ADMIN")` mặc định xét authority `ROLE_ADMIN` (tiền tố có thể cấu hình); `hasAuthority("DOC_READ")` xét chuỗi quyền chính xác. Nhưng kể cả khi `hasRole("ADMIN")` đúng, **phạm vi quản trị vẫn cần được định nghĩa**: quản trị hệ thống, quản trị tenant hay quản trị một dự án?

Hai danh tính cùng role `ROLE_MANAGER` có thể được giao những dự án khác nhau. Một role hoặc authority chung không tự xác định owner, tenant hay quan hệ chia sẻ của từng dữ liệu.

## 3. Rủi ro khi chỉ kiểm tra “đã đăng nhập”

Một controller có thể làm như sau:

~~~java
// Mã minh họa LỖ HỔNG, không dùng trong ứng dụng thật.
@GetMapping("/api/documents/{id}")
public DocumentDto read(@PathVariable long id) {
    return documentService.findById(id);
}
~~~

Nếu cấu hình bảo mật chỉ yêu cầu `anyRequest().authenticated()`, người dùng hợp lệ có thể thử một ID khác. Bộ lọc xác thực đã cho phép yêu cầu đi qua vì tài khoản đã đăng nhập, nhưng `findById(id)` chưa kiểm tra liệu **người gọi có quyền xem chính đối tượng ấy** hay không.

Đây là dạng lỗi thường được gọi là **IDOR** (Insecure Direct Object Reference), thuộc nhóm **Broken Object Level Authorization (BOLA)**: ứng dụng cho phép tham chiếu một đối tượng bằng ID mà không kiểm soát quyền tương ứng. ID không nhất thiết là số liên tiếp; dùng UUID ngẫu nhiên có thể khiến đoán ID khó hơn nhưng **không thay thế kiểm tra phân quyền**.

Cần chú ý nhiều đường rò rỉ ngoài trang “xem chi tiết”:

- **GET một bản ghi:** biết ID của người khác rồi đọc nội dung.
- **GET danh sách hoặc tìm kiếm:** API trả về dữ liệu từ tenant khác, kể cả danh sách ID và metadata.
- **Tổng số bản ghi, phân trang, thống kê:** nội dung đã lọc nhưng `totalCount` vẫn đếm dữ liệu không được phép.
- **Sửa/xóa/chuyển trạng thái:** người dùng gửi ID của đối tượng khác trong URL hoặc body.
- **Xuất CSV, tải tệp đính kèm, truy xuất lịch sử:** đường đi phụ bỏ qua quy tắc đã áp dụng trên màn hình chính.
- **Thuộc tính nhạy cảm trong cùng một bản ghi:** được đọc tên tài liệu không nhất thiết được đọc giá nội bộ, thông tin cá nhân hoặc trường bí mật. Đây còn là vấn đề phân quyền ở mức thuộc tính.

Một giao diện ẩn nút “Xóa” hoặc không hiển thị tài liệu lạ chỉ cải thiện trải nghiệm; **yêu cầu trực tiếp đến API vẫn phải được máy chủ xác minh**. Không tin `ownerId` hoặc `tenantId` do trình duyệt tự gửi như bằng chứng cấp quyền.

## 4. Những yếu tố của một quyết định phân quyền

Có thể mô hình hóa một quyết định truy cập thành:

~~~text
ALLOW = policy(subject, action, resource, context)

subject  : principal, authorities, tenant và thuộc tính được xác minh
action   : read / create / update / delete / approve / export
resource : bản ghi, tệp, báo cáo, trường dữ liệu cụ thể
context  : quan hệ owner, chia sẻ, trạng thái, tenant, thời điểm...
~~~

Ví dụ chính sách đọc tài liệu trong bài này:

1. Chủ thể thực sự đã được xác thực.
2. Chủ thể có quyền `DOC_READ`.
3. Tenant của tài liệu trùng tenant đáng tin cậy của chủ thể.
4. Trong tenant đó, người gọi là chủ sở hữu **hoặc** có quyền `DOC_READ_ALL`.

Nếu bất kỳ điều kiện bắt buộc nào không đúng, quyết định là **từ chối**. Quyền `DOC_READ_ALL` không bỏ qua bước kiểm tra tenant. Một hành động `UPDATE` phải có chính sách riêng, chẳng hạn quyền `DOC_EDIT` và điều kiện chủ sở hữu/cấp quản lý phù hợp.

Nguyên tắc nên nhớ:

- **Deny by default:** hành động chưa được định nghĩa quyền thì không tự động cho phép.
- **Least privilege:** chỉ cấp quyền tối thiểu cần cho công việc và phạm vi dữ liệu cần dùng.
- **Complete mediation:** mọi đường xử lý có thể truy cập tài nguyên cần đi qua kiểm soát tương ứng.
- **Server-side enforcement:** quyết định tin cậy diễn ra trên máy chủ từ dữ liệu đã được kiểm tra.

Khi chính sách còn thiếu, hãy định nghĩa rõ ai được phép xem từng lớp dữ liệu; không khắc phục bằng việc tự ý coi mọi người đã đăng nhập là đủ điều kiện.

## 5. Ví dụ Java 17+ tự chạy: đăng nhập thành công vẫn có thể bị từ chối

Ví dụ dùng Java thuần để minh họa phép kiểm tra. Đây là **mô hình chính sách**, không phải một bộ xác thực hoàn chỉnh: cờ `authenticated` và bộ authorities được tạo sẵn cho tình huống học tập. Trong ứng dụng thật, các giá trị này phải lấy từ kết quả xác thực đáng tin cậy.

Tạo tệp `AuthorizationScopeDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public class AuthorizationScopeDemo {

    record User(
            String id,
            String tenant,
            boolean authenticated,
            Set<String> authorities
    ) {}

    record Document(long id, String owner, String tenant) {}

    static boolean canRead(User caller, Document document) {
        return caller.authenticated()
                && caller.authorities().contains("DOC_READ")
                && caller.tenant().equals(document.tenant())
                && (caller.id().equals(document.owner())
                    || caller.authorities().contains("DOC_READ_ALL"));
    }

    public static void main(String[] args) {
        User mai = new User("mai", "tenant-A", true, Set.of("DOC_READ"));
        User adminA = new User(
                "admin-a",
                "tenant-A",
                true,
                Set.of("DOC_READ", "DOC_READ_ALL"));
        User anonymous = new User(
                "guest", "tenant-A", false, Set.of("DOC_READ"));

        Document own = new Document(101, "mai", "tenant-A");
        Document another = new Document(102, "an", "tenant-A");
        Document otherTenant = new Document(103, "an", "tenant-B");

        System.out.println("Mai own=" + canRead(mai, own));
        System.out.println("Mai other=" + canRead(mai, another));
        System.out.println("Admin A other=" + canRead(adminA, another));
        System.out.println("Admin A other tenant="
                + canRead(adminA, otherTenant));
        System.out.println("Anonymous own=" + canRead(anonymous, own));

        List<Long> visibleIds = List.of(own, another, otherTenant)
                .stream()
                .filter(document -> canRead(mai, document))
                .map(Document::id)
                .toList();

        System.out.println("Mai visible IDs=" + visibleIds);
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac AuthorizationScopeDemo.java
java AuthorizationScopeDemo
~~~

Kết quả chuẩn:

~~~text
Mai own=true
Mai other=false
Admin A other=true
Admin A other tenant=false
Anonymous own=false
Mai visible IDs=[101]
~~~

Phân tích từng trường hợp:

- **Mai đọc tài liệu 101:** tài khoản được xác thực, có `DOC_READ`, tenant phù hợp và là owner → `true`.
- **Mai đọc tài liệu 102:** tài khoản vẫn xác thực thành công và có `DOC_READ`, nhưng owner là An, Mai không có `DOC_READ_ALL` → `false`.
- **Admin A đọc tài liệu 102:** có quyền đọc mọi tài liệu trong tenant A → `true`.
- **Admin A đọc tài liệu 103:** dù có `DOC_READ_ALL`, tenant B nằm ngoài phạm vi → `false`.
- **Khách chưa xác thực đọc tài liệu 101:** bị từ chối trước cả khi xét owner, ngay cả khi ví dụ cố tình đưa `DOC_READ` vào bộ dữ liệu giả.

Phép `filter` trong ví dụ chỉ để làm rõ danh sách hiển thị. Với ứng dụng dùng cơ sở dữ liệu và dữ liệu lớn, nên áp dụng bộ lọc quyền ngay trong câu truy vấn dữ liệu được phép: như vậy cả phân trang, tổng số, sắp xếp và tài nguyên lấy từ nơi khác cũng phải dùng đúng phạm vi. Đừng lấy toàn bộ dữ liệu bí mật vào bộ nhớ rồi coi lọc giao diện là hàng rào bảo vệ.

## 6. Áp dụng vào Spring Security theo từng tầng

Spring Security giúp kiểm tra danh tính và yêu cầu quyền ở nhiều vị trí. Với quyền truy cập bản ghi, thường cần kết hợp **quy tắc trên request** với **chính sách ở service/dữ liệu**.

### 6.1. Tầng HTTP: kiểm tra được gọi chức năng hay không

Ví dụ một mảnh cấu hình Spring Security servlet sử dụng `SecurityFilterChain`:

~~~java
// Các import và cấu hình bean khác được lược bỏ:
// @Bean SecurityFilterChain security(HttpSecurity http) throws Exception
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/documents/**")
            .hasAuthority("DOC_READ")
        .anyRequest().denyAll()
);
~~~

Ví dụ chỉ cho phép các request GET tới vùng tài liệu khi có `DOC_READ`, và từ chối những request còn lại chưa được khai báo. **Quy tắc URL này không tự biết tài liệu 101 hay 102 thuộc ai**. Vì vậy `GET /api/documents/102` vẫn cần kiểm tra ở tầng nghiệp vụ.

Các rule trong `authorizeHttpRequests` được xét theo thứ tự, và quy tắc khớp đầu tiên quyết định. Hãy đặt quy tắc cụ thể trước và một quy tắc bao phủ cuối cùng; không mở `permitAll` cho vùng chứa dữ liệu nhạy cảm chỉ vì controller sẽ xử lý sau.

### 6.2. Tầng method: bắt buộc quyền khi gọi nghiệp vụ

Spring Security hỗ trợ method security bằng `@EnableMethodSecurity` và `@PreAuthorize`. Khi đã cấu hình method security và gọi qua cơ chế interceptor phù hợp, có thể viết:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public DocumentDto getDocument(long documentId) {
    // Nội dung hàm còn phải lọc quyền trên documentId.
    return documentService.readAuthorized(documentId);
}
~~~

Đây là **mảnh mã minh họa trong ứng dụng Spring**, chưa có phần khai báo class, import, bean hoặc implementation của `readAuthorized`, nên không chạy độc lập. Chú thích method yêu cầu quyền chức năng `DOC_READ` nhưng **chưa tự kiểm tra quyền sở hữu hay tenant**; `readAuthorized` phải làm việc đó.

Có thể diễn đạt quyền theo đối tượng trong policy bean riêng, ví dụ biểu thức `@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")`, với điều kiện method security được bật, `documentPolicy` được đăng ký, tham số biểu thức phân giải được và hàm policy lấy thông tin/thuộc tính đáng tin cậy. Đây là một hướng thiết kế khi nhiều nơi cùng dùng một chính sách; không có hàm `canRead` sẵn của Spring Security tương ứng với dữ liệu nghiệp vụ riêng của bạn.

Lưu ý về proxy: với cách method security dựa trên Spring AOP, lời gọi một method có annotation **từ chính đối tượng đó** (self-invocation) có thể không đi qua interceptor. Khi thiết kế ranh giới bảo mật, cần kiểm tra đường gọi thực tế và đặt logic xác minh trong service/policy được gọi đáng tin cậy; tránh xem annotation chỉ như một nhãn trang trí.

### 6.3. Tầng dữ liệu: giới hạn đối tượng ngay trong truy vấn

Ý tưởng an toàn cho API đọc tài liệu là:

~~~text
Authentication đáng tin cậy
   -> lấy userId, tenantId và authorities đã được xác minh
   -> kiểm tra quyền DOC_READ
   -> lấy dữ liệu theo documentId + tenantId + owner/chia sẻ/quyền đọc mở rộng
   -> chỉ trả DTO cho tài liệu trong phạm vi
~~~

Một truy vấn SQL minh họa cho chính sách trong bài:

~~~sql
SELECT d.id, d.title, d.content
FROM documents d
WHERE d.id = :documentId
  AND d.tenant_id = :trustedTenantId
  AND (
       d.owner_user_id = :trustedUserId
       OR :canReadAllInsideTenant = TRUE
  );
~~~

Ở đây các tham số có tiền tố `trusted` phải được lấy từ ngữ cảnh đã được máy chủ kiểm tra, không mặc nhiên lấy từ `?tenantId=` trong URL hay body của client. Giá trị `:canReadAllInsideTenant` do server tính bằng cách đối chiếu authority hợp lệ, sau khi đã có quyền đọc cơ bản. SQL là mẫu ý tưởng: cú pháp tham số và boolean tùy lớp truy cập dữ liệu/hệ quản trị.

Khi không tìm thấy bản ghi trong phạm vi cho phép, service có thể trả lỗi phù hợp theo chính sách, chẳng hạn `404 Not Found` để không tiết lộ sự tồn tại của tài liệu không được phép xem. Với hành động đã xác thực nhưng thiếu quyền, `403 Forbidden` là phản hồi thường gặp. Cách dùng 403 hay 404 cho đối tượng không thuộc phạm vi phải nhất quán với yêu cầu bảo mật và trải nghiệm của hệ thống.

**Danh sách và phân trang:** dùng cùng điều kiện quyền cho truy vấn danh sách, `COUNT`, báo cáo, xuất file và các API tìm kiếm. Nếu `SELECT` đã lọc theo tenant nhưng `COUNT(*)` chưa lọc, tổng số vẫn có thể tiết lộ dữ liệu.

**Ghi dữ liệu:** kiểm tra quyền ghi cần gắn với chính đối tượng và trạng thái hiện hành. Nếu có thay đổi đồng thời, cân nhắc gộp điều kiện owner/tenant vào truy vấn `UPDATE`/`DELETE` hoặc dùng giao dịch/khóa phù hợp để tránh khoảng trống giữa bước kiểm tra quyền và bước ghi.

### 6.4. Vì sao nên có cả HTTP rule và kiểm tra nghiệp vụ?

Tầng HTTP giúp chặn sớm thao tác không được cấp quyền. Tầng method/service giữ quy tắc gần hành động thực sự, kể cả khi service được gọi qua đường khác hoặc có nhiều controller. Tầng dữ liệu giới hạn đúng tập bản ghi được đọc/sửa. Các tầng bổ sung cho nhau; chính sách trên mỗi tầng cần thống nhất.

Không nên dựa riêng vào việc frontend ẩn đường dẫn, nút bấm, hoặc mã hóa ID. Cũng không nên lấy `Authentication#getName()` làm user ID nghiệp vụ nếu hệ thống dùng tên hiển thị có thể đổi hoặc nhiều provider có quy ước tên khác nhau. Hãy ánh xạ principal đáng tin thành định danh ổn định trong ứng dụng.

## 7. Các dạng phân quyền cần tách bạch

### 7.1. Truy cập ngang: người dùng này sang dữ liệu người dùng khác

Hai người cùng vai trò `ROLE_USER` nhưng khác chủ sở hữu. Mai được xem đơn hàng của Mai, không được xem đơn hàng của An. Quyền chức năng không cho phép tự vượt qua ranh giới sở hữu.

### 7.2. Truy cập dọc: người dùng thường sang quyền quản trị

Một người có `DOC_READ` không được gọi API `DELETE /api/documents/101` khi chưa có quyền xóa và điều kiện tương ứng, dù họ sở hữu tài liệu. Tài khoản thuộc tenant A cũng không được trở thành quản trị tenant B chỉ bằng cách đổi tham số.

### 7.3. Phạm vi dự án và tenant

Với phần mềm phục vụ nhiều tổ chức, mỗi record thường gắn một tenant. Mọi truy vấn và thao tác cần duy trì ranh giới tenant, kể cả tài khoản có vai trò quản trị trong tenant của họ. Đọc tệp ở kho đối tượng, chạy job nền hoặc lấy dữ liệu từ cache cũng cần giữ cùng phạm vi này.

### 7.4. Quyền ở mức trường dữ liệu

Một người có thể được phép đọc tên và trạng thái hồ sơ nhưng không được đọc trường `salary`, `personalIdentifier` hoặc khóa nội bộ. Áp dụng chính sách ở lúc xây dựng DTO/response hoặc bằng truy vấn chỉ lấy những cột được phép. Không trả toàn bộ entity rồi trông chờ giao diện bỏ qua trường nhạy cảm.

## 8. Trạng thái HTTP và cách xử lý khi bị từ chối

| Tình trạng | Ý nghĩa thường gặp trong API yêu cầu xác thực | Phản hồi phù hợp |
| --- | --- | --- |
| Chưa có thông tin xác thực hợp lệ | Không thiết lập được danh tính cần thiết | Thường là `401 Unauthorized` |
| Đã xác thực nhưng thiếu quyền thực hiện hành động | Không đủ authority/chính sách | Thường là `403 Forbidden` |
| Đã xác thực, có quyền chung nhưng đối tượng không nằm trong phạm vi nhìn thấy | Không được xem nội dung của đối tượng ấy | `403` hoặc `404` theo chính sách che giấu sự tồn tại |
| Có đủ quyền và đối tượng trong phạm vi | Cho phép thao tác | `200`, `204` hoặc trạng thái thành công thích hợp |

Đây là quy ước giải thích, không phải một ánh xạ cố định cho mọi cơ chế Spring Security; authentication entry point, access-denied handler, giao thức và chính sách của ứng dụng có thể tạo phản hồi khác.

Khi từ chối, tránh đính kèm nội dung tài liệu bị chặn hoặc thông tin nhạy cảm trong lỗi. Nhật ký nội bộ có thể ghi dấu vết quyết định (actor, action, resource identifier được xử lý an toàn, kết quả) để điều tra, nhưng không in mật khẩu/token hoặc toàn bộ dữ liệu riêng tư.

## 9. Kiểm thử cần bao gồm cả trường hợp “đăng nhập thành công nhưng không có quyền”

Chỉ kiểm thử “chưa đăng nhập bị chặn” và “đăng nhập thành công nhận 200” là chưa đủ. Nên kiểm tra ít nhất:

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Chưa xác thực đọc tài liệu riêng tư | Bị từ chối |
| Đã xác thực, không có `DOC_READ` | Bị từ chối |
| Đã xác thực, có `DOC_READ`, đọc tài liệu của mình | Được phép |
| Đã xác thực, có `DOC_READ`, đổi sang ID của người cùng tenant | Bị từ chối nếu không có quyền chia sẻ |
| Quản trị tenant A đọc tài liệu người khác cùng tenant A | Được phép nếu chính sách cấp `DOC_READ_ALL` |
| Quản trị tenant A đổi sang ID thuộc tenant B | Bị từ chối |
| Có quyền đọc nhưng gọi chức năng sửa/xóa | Bị từ chối nếu thiếu quyền ghi |
| Gọi API danh sách/tìm kiếm/tổng số | Chỉ thấy dữ liệu và số lượng thuộc phạm vi |
| Gọi API tải file hoặc xuất báo cáo | Áp dụng cùng giới hạn dữ liệu |
| Thao tác với tài liệu không tồn tại hoặc bị cấm | Không để lộ nội dung không được phép |

Spring Security có công cụ hỗ trợ kiểm thử request/method (ví dụ MockMvc, `@WithMockUser`). Tuy nhiên một bài test chỉ giả lập authorities thường **chưa đủ** để kiểm chứng owner và tenant: cần chuẩn bị nhiều tài khoản, nhiều bản ghi cùng/khác tenant và assert đúng dữ liệu phản hồi. Trường hợp nguy hiểm nhất là hai người dùng **đều đăng nhập hợp lệ** nhưng một người truy cập dữ liệu của người còn lại.

Nếu dùng `@PreAuthorize`, cần kiểm tra method security thực sự được bật và đường gọi đi qua cơ chế bảo vệ. Nếu dùng truy vấn có tenant, cần kiểm thử cả trường hợp trùng `documentId` theo quy ước dữ liệu và khác tenant; không suy luận rằng `tenantId` từ request là đáng tin.

## 10. Những cách nghĩ sai cần loại bỏ

1. **“Đã login thì có quyền truy cập toàn bộ.”** Sai: login là xác thực danh tính, chưa xác định quyền cho từng tài nguyên.
2. **“Đường dẫn đã yêu cầu `authenticated()` là đủ.”** Sai với dữ liệu riêng tư: cần kiểm tra owner, tenant và quyền hành động.
3. **“Có `ROLE_ADMIN` nên được xem mọi tenant.”** Sai nếu hệ thống chỉ định vai trò quản trị trong từng tổ chức.
4. **“Dùng UUID thay ID số là hết lỗi IDOR.”** Sai: biết hoặc lấy được UUID vẫn phải qua kiểm tra quyền.
5. **“Ẩn nút là chặn được API.”** Sai: phía khách có thể gửi request trực tiếp.
6. **“Chỉ cần lọc danh sách trên frontend.”** Sai: dữ liệu đã bị gửi đến client trước khi lọc.
7. **“Controller đã kiểm tra thì mọi nơi dùng service đều an toàn.”** Không chắc: một đường gọi khác có thể bỏ qua controller. Bảo vệ nghiệp vụ tại ranh giới phù hợp.
8. **“Không có chi tiết tài liệu nhưng lộ tổng số thì vẫn an toàn.”** Chưa chắc: tổng số, ID, tên file và metadata cũng có thể là dữ liệu nhạy cảm.
9. **“Quyền đọc tự bao gồm quyền sửa.”** Không đúng nếu chính sách không cấp quyền tương ứng.
10. **“Đã kiểm tra quyền trước khi query thì việc cập nhật luôn an toàn.”** Chưa chắc: chủ sở hữu/trạng thái có thể thay đổi giữa kiểm tra và ghi; bảo vệ điều kiện trong giao dịch hoặc câu lệnh ghi khi cần.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** An và Mai có cùng `ROLE_USER` và cùng `DOC_READ`. Tại sao Mai không tự động được đọc tài liệu của An?

*Trả lời:* Quyền chức năng `DOC_READ` chỉ là một điều kiện. Chính sách còn phải kiểm tra chủ sở hữu/chia sẻ và tenant của tài liệu được yêu cầu.

**Câu 2.** Quản trị viên tenant A có `DOC_READ_ALL`. Họ có được đọc tài liệu tenant B không?

*Trả lời:* Theo chính sách trong bài, không. “ALL” chỉ mở rộng phạm vi owner bên trong tenant A; kiểm tra tenant vẫn bắt buộc.

**Câu 3.** Nếu một API đã dùng `requestMatchers("/api/**").authenticated()` và controller gọi `findById(id)`, điều gì còn thiếu?

*Trả lời:* Kiểm tra quyền hành động và phạm vi truy cập đối tượng `id`, cũng như bảo vệ các đường gọi khác ở tầng service/dữ liệu.

**Câu 4.** Có thể coi `tenantId` gửi trong request body là bằng chứng người dùng thuộc tenant ấy không?

*Trả lời:* Không. Máy chủ phải xác định tenant được phép từ thông tin xác thực và quan hệ thành viên đáng tin cậy. Tenant mà client yêu cầu chỉ là một tham số để đối chiếu.

**Câu 5.** Trường hợp nào cần được kiểm thử kỹ hơn: khách chưa đăng nhập xem tài liệu hay hai người đã đăng nhập đọc tài liệu của nhau?

*Trả lời:* Cả hai đều cần test; nhưng trường hợp thứ hai đặc biệt quan trọng để phát hiện lỗi phân quyền cấp đối tượng mà kiểm thử đăng nhập thông thường bỏ sót.

Khi thiết kế một API Spring Security, đừng chỉ hỏi **“request này có Authentication không?”**. Hãy tiếp tục hỏi **“người này có được thực hiện hành động đó trên chính bản ghi, trường dữ liệu, tenant và trạng thái này không?”**. Chỉ khi tất cả điều kiện bắt buộc đều đúng, ứng dụng mới nên tiết lộ hoặc thay đổi dữ liệu.

### Tài liệu đối chiếu

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
