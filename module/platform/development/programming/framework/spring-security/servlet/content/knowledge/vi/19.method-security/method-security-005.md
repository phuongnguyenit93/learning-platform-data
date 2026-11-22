# @PreFilter, @PostFilter và giới hạn khi lọc tập dữ liệu lớn trong Spring Security Servlet

## 1. Mục tiêu và bối cảnh

Trong ứng dụng **Spring Boot 3.x / Spring Security 6.x dùng Servlet**, việc bảo vệ phương thức không chỉ là câu hỏi “ai được gọi phương thức này?” mà đôi khi còn là “những phần tử nào của một tập dữ liệu được phép đi vào hoặc đi ra khỏi phương thức?”.

Spring Security cung cấp hai annotation phục vụ việc lọc phần tử:

- **`@PreFilter`**: đánh giá biểu thức cho **từng phần tử của một tham số tập hợp trước khi method body chạy**; chỉ những phần tử đạt điều kiện được chuyển tiếp.
- **`@PostFilter`**: đánh giá biểu thức cho **từng phần tử của kết quả trả về sau khi method body chạy**; loại các phần tử không đạt trước khi caller nhận kết quả.

Ví dụ ý tưởng: phương thức nhận danh sách tài liệu cần xem trước; người dùng alice chỉ được xem các tài liệu của alice. Hoặc một service trả một tập tài liệu nhỏ và `@PostFilter` bỏ tài liệu của người khác.

~~~text
@PreFilter:
caller đưa List<Document> vào
     |
     v
Method-security proxy kiểm tra filterObject từng phần tử
     |
     v
List chỉ còn phần tử hợp lệ
     |
     v
method body được thực thi với List đã lọc

@PostFilter:
caller gọi method
     |
     v
method body tải/tạo kết quả (ví dụ 1000 Document)
     |
     v
Method-security proxy kiểm tra filterObject trên kết quả
     |
     v
caller chỉ thấy phần tử đạt điều kiện
~~~

**Cảnh báo trung tâm của bài:** `@PostFilter` **không tự biến một truy vấn lấy tất cả bản ghi thành truy vấn database có điều kiện phân quyền**. Nếu service tải một triệu bản ghi rồi Spring Security lọc ở Java, database, network, CPU, heap và garbage collector đã phải gánh chi phí trước khi caller nhận kết quả. Với dữ liệu lớn, đa tenant hoặc nhạy cảm, nên **đẩy điều kiện phân quyền xuống truy vấn hoặc lớp truy cập dữ liệu**, kiểm tra ownership/tenant ở server và phân trang **sau khi** áp điều kiện.

Bài dùng **Java 17+, Spring Boot 3.3.13, Spring Security 6 và Spring MVC** làm ví dụ học tập. Các ví dụ độc lập đều được ghi đầy đủ file, còn snippet tách riêng sẽ được chú thích rõ. Kết quả HTTP/test nêu trong bài là **kỳ vọng khi chạy**, không phải bằng chứng đã thực thi Maven.

## 2. Bật method security trước khi sử dụng

Các annotation filter không được hiểu như annotation của MVC. Chúng thuộc **method security**, thường hoạt động thông qua Spring AOP/method-security interceptors.

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Đây là snippet chỉ gồm lớp cấu hình và annotations; cần imports `Configuration` và `EnableMethodSecurity`. Trong project hoàn chỉnh phần 9, chúng được đặt trong `SecurityConfig` với các beans khác.

Với cấu hình mặc định, `@EnableMethodSecurity` bật các annotation pre/post, trong đó có `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Đừng vô tình dùng `@EnableMethodSecurity(prePostEnabled = false)` rồi kỳ vọng bốn loại annotation này tiếp tục hoạt động.

Quá trình khái niệm:

~~~text
HTTP request / Scheduler / Messaging / bean khác
                 |
                 v
      Spring-managed service proxy
                 |
                 +-- @PreFilter: lọc input collection
                 +-- @PreAuthorize: kiểm tra trước khi gọi
                 |
                 v
             method body
                 |
                 +-- @PostAuthorize: kiểm tra kết quả/quyền sau khi gọi
                 +-- @PostFilter: lọc phần tử của output
                 |
                 v
            caller nhận giá trị
~~~

Sơ đồ không cam kết thứ tự chính xác của tất cả interceptors khi nhiều annotation cùng áp dụng; Spring Security có thứ tự interceptor được định nghĩa theo cấu hình/phiên bản. Điều cần nhớ là **pre** xảy ra trước method body, **post** xảy ra sau method body. Việc kết hợp nhiều policy cần được test thay vì suy luận từ thứ tự ngẫu nhiên.

### 2.1. Proxy và self-invocation

Nếu một method trong cùng bean gọi thẳng method khác của `this`, lời gọi có thể **không đi qua Spring proxy**, nên annotation method security ở method được gọi không được thực thi.

~~~java
@Service
public class ExampleService {
    public void outerCall() {
        restrictedMethod(); // self-invocation: có thể bypass proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void restrictedMethod() {
        // ...
    }
}
~~~

Đây là **snippet minh họa**, không phải project chạy đầy đủ. Tránh dùng self-invocation như một đường bảo vệ; tách service được bảo vệ sang **bean khác** và gọi qua dependency injection. Trong project chạy được ở phần 9, controller gọi service bean riêng để đi qua proxy.

Không dựa vào `@PreFilter` trên `private` method, `final` method/class hoặc method không được Spring AOP intercept phù hợp; hãy thiết kế public service boundary có kiểm thử. Method security bổ sung cho, không thay thế hoàn toàn, HTTP security và kiểm tra dữ liệu tại database.

## 3. filterObject, authentication và biểu thức SpEL

Cả hai annotation dùng biểu thức SpEL đánh giá **mỗi phần tử**. Những biến/đối tượng hay gặp:

| Tên trong biểu thức | Ý nghĩa |
| --- | --- |
| `filterObject` | Phần tử hiện đang được kiểm tra |
| `authentication` | `Authentication` hiện tại trong security context |
| `authentication.name` | Tên người dùng/principal theo Authentication |
| `principal` | Principal hiện tại, tùy loại Authentication |
| `hasRole('USER')`, `hasAuthority('...')` | Các hàm kiểm quyền của method-security expression context |

Giả sử có Java record:

~~~java
public record Document(long id, String owner, String title) {
}
~~~

Và user alice đã xác thực. Biểu thức:

~~~text
filterObject.owner() == authentication.name
~~~

so sánh owner của một phần tử với user hiện tại. `owner()` là accessor của Java record; dùng method call rõ ràng để không phụ thuộc quy tắc truy cập property tùy biến. Trong SpEL, phép `==` trên các chuỗi được đánh giá theo semantics so sánh giá trị thích hợp, không phải lỗi Java `==` so sánh reference string.

**Cẩn trọng về nguồn dữ liệu:**
- Nếu owner đến từ **record do server đã xác minh/tải từ database**, điều kiện có thể là một phần của kiểm tra quyền sở hữu.
- Nếu owner là một field trong **JSON do client tự gửi**, client có thể đặt `"owner":"alice"` tùy ý. Khi đó lọc theo field này **không chứng minh** chủ sở hữu thật.
- `authentication.name` phải đến từ authentication mechanism đáng tin; không chấp nhận header `X-Username` hoặc query `?user=alice` làm danh tính.
- Phân quyền đa tenant thường cần kiểm tra cả tenant ID **đáng tin** và ownership/permission theo object thực. So chuỗi username là ví dụ học tập, không phải toàn bộ policy production.

Khi biểu thức tham chiếu field null hoặc record khác cấu trúc, có thể phát sinh lỗi đánh giá. Viết policy null-safe và test cho dữ liệu thực, đặc biệt với collection chứa phần tử null.

## 4. @PreFilter: lọc tham số trước khi method chạy

### 4.1. Ví dụ cốt lõi

~~~java
@PreFilter("filterObject.owner() == authentication.name")
public List<Document> preview(List<Document> candidates) {
    return List.copyOf(candidates);
}
~~~

Đây là **snippet** của một method trong Spring-managed service có `@EnableMethodSecurity`, không phải class Java hoàn chỉnh. Với một tham số collection, `@PreFilter` biết tập cần lọc.

Giả sử caller đưa một danh sách *mutable*:

~~~text
Input trước proxy:
[Doc(1, "alice"), Doc(2, "bob"), Doc(3, "alice")]

User authenticated: alice

Input mà method body nhận sau @PreFilter:
[Doc(1, "alice"), Doc(3, "alice")]
~~~

Các phần tử không khớp expression được loại **trước** khi logic trong method body xử lý chúng. Trong nhiều cách triển khai, Spring Security thao tác trực tiếp với collection tham số để loại phần tử; **không giả định đối tượng input sẽ giữ nguyên** và đừng truyền collection immutable nếu filter cần loại phần tử.

### 4.2. filterTarget khi có nhiều tham số có khả năng lọc

Ví dụ một service nhận cả chuỗi hành động và danh sách tài liệu:

~~~java
@PreFilter(
    value = "filterObject.owner() == authentication.name",
    filterTarget = "candidates"
)
public List<Document> preview(String purpose, List<Document> candidates) {
    return List.copyOf(candidates);
}
~~~

Đây là snippet để minh họa `filterTarget`, không phải method thuộc project phần 9. Khi có nhiều collection/map/array hoặc tham số khiến việc chọn target không rõ, `filterTarget` xác định **tên tham số muốn lọc**. Việc tham chiếu tên tham số Java có thể cần metadata biên dịch `-parameters`; dùng build setup phù hợp (Spring Boot Maven parent thường cấu hình hỗ trợ parameter names) hoặc kiểm tra cách đặt tên được phiên bản hỗ trợ. Không dùng `filterTarget` như tên biến request JSON.

### 4.3. Mutable collection và side effect

Một số cách viết dễ gặp vấn đề:

~~~java
List<Document> items = List.of(
    new Document(1L, "alice", "A"),
    new Document(2L, "bob", "B")
);
service.preview(items);
~~~

`List.of(...)` trả một danh sách **không thể sửa**. Khi `@PreFilter` cố loại phần tử không được phép, tùy kiểu collection/implementation có thể xảy ra `UnsupportedOperationException`. Ở caller, dùng một **defensive mutable copy**:

~~~java
List<Document> safeCopy = new ArrayList<>(items);
List<Document> visible = service.preview(safeCopy);
~~~

Snippet này cần import `List` và `ArrayList`, cùng method/kiểu Document trong project phù hợp. Điều quan trọng không phải “mọi List đều sẽ lỗi” mà là **đừng bắt một filter cần thay đổi collection phải làm việc trên immutable/unmodifiable input**.

Nếu list gốc được chia sẻ giữa nhiều threads, đừng để prefilter sửa cùng một instance mà những request khác cũng đang dùng. Tạo bản sao cục bộ theo request, hoặc chuyển sang một API trả tập mới được tạo có kiểm soát. Bất kỳ cập nhật collection qua prefilter nào cũng phải được xét theo concurrency và ownership.

### 4.4. @PreFilter không giống @PreAuthorize

- `@PreAuthorize` thường quyết định **cho/không cho gọi toàn bộ method**.
- `@PreFilter` loại **từng phần tử** của một tham số.

Ví dụ write batch có 10 yêu cầu, trong đó một yêu cầu không thuộc user. Nếu bạn dùng prefilter, method body có thể chỉ xử lý 9 yêu cầu và trả thành công. Đây có thể là **hành vi sai hợp đồng** hoặc vi phạm transaction atomicity.

Đối với các thao tác ghi quan trọng, thường nên **kiểm tra toàn bộ batch** và **từ chối trọn request** nếu có một phần tử trái quyền, thay vì âm thầm bỏ phần tử:

~~~java
// Snippet chính sách nghiệp vụ, minh họa - không phải class đầy đủ.
boolean allAuthorized = items.stream().allMatch(
    item -> documentPolicy.canWrite(authentication, item.id())
);
if (!allAuthorized) {
    throw new AccessDeniedException("Không được sửa một hoặc nhiều tài liệu");
}
~~~

`documentPolicy.canWrite` phải kiểm tra quyền theo dữ liệu **được lấy từ nguồn tin cậy** và tenant của chủ thể; không tin `owner` được client tự khai. Trong dịch vụ transaction, phải xác định trước hành vi rollback, locking và kiểm tra lại quyền trước lúc ghi.

**Quy tắc:** chọn `@PreFilter` khi nghiệp vụ thật sự cho phép **bỏ qua phần tử không thỏa điều kiện**. Chọn `@PreAuthorize`/policy service khi yêu cầu phải **cho phép hoặc từ chối toàn bộ thao tác**.

## 5. @PostFilter: lọc các phần tử của kết quả trả về

### 5.1. Ví dụ cốt lõi

~~~java
@PostFilter("filterObject.owner() == authentication.name")
public List<Document> listVisibleFromSmallSample() {
    return new ArrayList<>(documentStore.all());
}
~~~

Đây là snippet service minh họa, cần dependency injection và imports đầy đủ. Method **chạy trước**, tạo danh sách tài liệu, **sau đó** method-security interceptor lọc theo biểu thức trên phần tử.

Với danh sách:

~~~text
Result do method body tạo:
[Doc(1, "alice"), Doc(2, "bob"), Doc(3, "alice")]

User authenticated: alice

Result cuối cùng caller nhìn thấy:
[Doc(1, "alice"), Doc(3, "alice")]
~~~

`@PostFilter` không “chặn từ đầu” việc method đọc dữ liệu của bob. Nó chỉ ảnh hưởng **giá trị trả về qua lời gọi được intercept**. Nếu method đã ghi log dữ liệu bob, gửi event, cập nhật cache, gọi service ngoài, hoặc thực hiện side effect, annotation không thể hoàn tác những việc đó.

### 5.2. Collection trả về cần có thể lọc

Trong ví dụ hoạt động ở phần 9, repository demo trả một `new ArrayList<>(...)` để Spring Security có collection mà interceptor có thể lọc. Không mặc định rằng `List.of(...)`, `List.copyOf(...)`, `Collections.unmodifiableList(...)` hay mọi custom collection đều có thể bị sửa tại chỗ.

Hỗ trợ cụ thể cho array, map, stream và các loại return type khác có thể khác tùy phiên bản và API. Khi cần dùng `Page<T>`, `Slice<T>`, một reactive publisher hoặc stream lớn, **không suy diễn rằng @PostFilter hoạt động và phân trang đúng**; phải xác nhận kiểu được hỗ trợ và đặc biệt đánh giá chi phí materialization. Với Spring WebFlux, cơ chế là một nhánh khác, không dùng mặc định ví dụ Servlet này.

### 5.3. Không thay thế bảo vệ dữ liệu trong method body

Một anti-pattern:

~~~java
@PostFilter("filterObject.owner() == authentication.name")
public List<Document> exportAllDocuments() {
    List<Document> all = repository.findAll();

    auditLogAllDocuments(all); // dữ liệu bí mật đã được đọc và log trước lọc
    return all;
}
~~~

Đây là **pseudo-code minh họa**, không phải class biên dịch: repository và auditLogAllDocuments chưa được định nghĩa. Dù caller chỉ nhận danh sách lọc, hàm đã đọc và có thể log dữ liệu vượt quyền. Với dữ liệu nhạy cảm, truy vấn hoặc policy truy cập **nên lọc trước khi tải**, tránh đưa toàn bộ record vào memory và những side effects trước filter.

### 5.4. @PostFilter không giống @PostAuthorize

- `@PostAuthorize("returnObject.owner() == authentication.name")`: đánh giá **một kết quả** (ví dụ một Document) và quyết định có cho phép trả object hay từ chối toàn bộ lời gọi.
- `@PostFilter("filterObject.owner() == authentication.name")`: đánh giá **từng phần tử trong một tập kết quả** và loại phần tử không phù hợp.

Cả hai chạy sau method body, nên có chung hạn chế: dữ liệu đã được đọc/tính toán, side effects có thể đã xảy ra, và việc quyết định quá muộn không giúp tránh chi phí truy vấn. Với truy cập một object theo ID, **`@PreAuthorize` kết hợp query ràng buộc owner/tenant** thường phù hợp hơn khi có thể kiểm tra điều kiện sớm; cần cân nhắc TOCTOU giữa bước kiểm và bước đọc.

## 6. So sánh bốn annotation pre/post

| Annotation | Thời điểm | Đối tượng kiểm tra | Kết quả |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước method body | Quyền gọi toàn bộ method | Cho gọi hoặc từ chối |
| `@PreFilter` | Trước method body | Mỗi phần tử của một tham số collection/map được hỗ trợ | Method nhận tập đầu vào đã lọc |
| `@PostAuthorize` | Sau method body | Quyền trả kết quả/returnObject | Cho trả hoặc từ chối |
| `@PostFilter` | Sau method body | Mỗi phần tử của kết quả collection được hỗ trợ | Caller nhận tập đầu ra đã lọc |

Ví dụ một service phức tạp có thể sử dụng cả `@PreAuthorize` và `@PostFilter` để từ chối người chưa xác thực, sau đó lọc tập nhỏ trong bộ nhớ. Tuy nhiên nhiều annotation **không tự kết hợp thành bảo vệ database an toàn**; nếu data query đã sai phạm vi thì chi phí và nguy cơ lộ ở các side effects vẫn tồn tại.

### 6.1. HTTP security vẫn là lớp riêng

`SecurityFilterChain` / `authorizeHttpRequests` bảo vệ request HTTP đi vào app. `@EnableMethodSecurity` bảo vệ lời gọi method được Spring proxy intercept. Chúng có thể chạy cùng nhau:

~~~text
GET /api/docs
     |
     v
HTTP SecurityFilterChain: authenticated()
     |
     v
DocumentController
     |
     v
DocumentService proxy: @PreAuthorize + @PostFilter
     |
     v
DocumentStore
     |
     v
Kết quả lọc theo user hiện tại
~~~

Không dùng HTTP URL matcher như biện pháp duy nhất để bảo vệ service có thể được gọi từ scheduler, message consumer, endpoint khác hoặc một phần ứng dụng không qua cùng web security chain. Đồng thời không dựa vào method annotation để cấu hình CORS/CSRF/headers.

### 6.2. Khi chưa authenticated

Biểu thức `authentication.name` chỉ có ý nghĩa theo Authentication hiện tại. Trong web chain có thể tồn tại anonymous Authentication; trạng thái anonymous không giống một user đã đăng nhập. Nếu method cần user thật, thêm `@PreAuthorize("isAuthenticated()")` hoặc policy tương đương và bảo đảm HTTP entry point thích hợp.

Không viết filter expression như:

~~~text
filterObject.owner() == request.getParameter("user")
~~~

rồi coi `user` do client gửi là danh tính tin cậy. Quyền phải dựa trên server-validated Authentication và owner/tenant thật.

## 7. Giới hạn quan trọng khi lọc tập dữ liệu lớn

### 7.1. Độ phức tạp và overfetch

Giả sử bảng `documents` có **1.000.000** dòng, trong đó user alice được phép xem **40** dòng. Nếu service thực thi:

~~~java
List<Document> all = repository.findAll(); // 1.000.000 dòng
return all; // @PostFilter cuối cùng chỉ trả 40 dòng
~~~

Bạn đã:
- Yêu cầu database đọc/serialize một triệu bản ghi.
- Truyền nhiều dữ liệu từ DB về app.
- Tạo một triệu entity/DTO/objects hoặc materialize kết quả.
- Áp predicate cho từng phần tử ở Java.
- Gây áp lực heap, GC và CPU; có thể gây OOM hay timeout.
- Có nguy cơ vô tình log/cache các bản ghi trước lọc.

Nếu predicate kiểm mỗi phần tử là O(1), riêng vòng lọc phải xét **O(N)** phần tử. Chi phí tổng còn có truy vấn, chuyển dữ liệu, object mapping, lazy loading và hoạt động trong method. Mô hình chi phí không đơn giản là “Java rất nhanh nên lọc sau vẫn ổn”.

~~~text
Cách overfetch:
DB: 1.000.000 rows --network--> JVM: 1.000.000 objects
                                      |
                                 @PostFilter
                                      |
                                      v
                               40 rows trả client

Cách query scoped:
DB: WHERE owner_id = current_user AND tenant_id = current_tenant
    ORDER BY id DESC LIMIT 20
                                      |
                                 network
                                      v
                             JVM: 20 rows đúng quyền
~~~

Các con số chỉ là tình huống giả định để phân tích, không phải benchmark thực đo. Trong hệ thống lớn, nếu lấy hết N dòng rồi lọc, chi phí có thể tăng tuyến tính theo tổng dữ liệu của **mọi user/tenant**, thay vì theo số dòng mà user thực sự được xem.

### 7.2. Pagination bị sai khi lọc sau

Giả sử truy vấn:

~~~sql
SELECT id, owner_id, title
FROM documents
ORDER BY id DESC
LIMIT 20 OFFSET 0;
~~~

DB trả 20 dòng đầu toàn hệ thống; `@PostFilter` bỏ 18 dòng của user khác và chỉ giữ 2 dòng. Client nhận “trang 1 có 2 dòng” dù database có thể còn hàng trăm dòng của user nằm ở các trang sau.

Những vấn đề kéo theo:
- **Page size sai** (20 yêu cầu nhưng 2 kết quả).
- **Total count sai** (đếm toàn bảng thay vì tập user được phép xem).
- **Trang rỗng giả** dù người dùng vẫn còn dữ liệu hợp lệ.
- **Cursor/offset có thể bỏ qua bản ghi hợp lệ** khi client duyệt theo dữ liệu sau lọc.
- **Sort và aggregation** có thể phản ánh dữ liệu toàn hệ thống trước khi security được áp.
- Một số lớp repository trả `Page<T>` không thể được filter an toàn như List; ngay cả khi có adapter, metadata pagination vẫn phải lấy từ tập được phép trước đó.

**Thứ tự đúng:** filter theo quyền ở DB → sort → pagination → map DTO → serialize response. Không làm “pagination → @PostFilter” cho dữ liệu user-scoped lớn.

### 7.3. Lazy loading và N+1 queries

Một SpEL expression như:

~~~text
filterObject.owner.id == authentication.principal.id
~~~

có thể truy cập quan hệ lazy-loaded. Nếu collection có 5.000 entities, việc kiểm owner có thể kích hoạt nhiều query riêng lẻ (vấn đề **N+1**). Nếu persistence context đã đóng, có thể gặp lỗi lazy initialization. Mỗi expression đơn giản trên giấy không nhất thiết có chi phí nhỏ trong ORM.

Cách xử lý:
- Sử dụng ownerId/tenantId đã được xác định trong query.
- Tránh gọi quan hệ lazy trong policy trên toàn tập.
- Dùng projections/DTO đủ trường cần thiết.
- Kiểm soát số query và fetch plan khi cần.
- Không mở transaction quá rộng chỉ để “chữa” một cách lọc sau kém hiệu quả.

### 7.4. @PreFilter cũng không tự giảm chi phí lấy dữ liệu

Một điểm dễ bị bỏ sót: `@PreFilter` xảy ra **trước method body được annotation**, nhưng nếu caller đã làm `repository.findAll()` rồi truyền list vào service, DB vẫn đã tải toàn bộ dữ liệu trước khi prefilter chạy.

~~~text
Controller: repository.findAll() -> 1.000.000 objects
                                  |
                                  v
                 service.preview(@PreFilter List)
                                  |
                                  v
                        chỉ 40 objects vào method body
~~~

Method body xử lý ít phần tử hơn nhưng **chi phí tải/khởi tạo một triệu phần tử đã xảy ra**. Vì vậy “đổi @PostFilter thành @PreFilter” không tự giải quyết bài toán large-data. Cần thay **nơi lọc** và **query thực tế**, không chỉ thay annotation.

### 7.5. Lộ dữ liệu gián tiếp và side effects

Ngay cả khi response không chứa tài liệu ngoài quyền, dữ liệu có thể đã đi qua:
- Logs/traces/metrics chứa field nhạy cảm.
- Cache dùng key chung không có tenant/user scope.
- Domain events xuất trước khi lọc.
- File tạm/export/import staging.
- Async tasks xử lý tập trước khi caller nhận kết quả.
- Exception messages chứa thông tin của record không được phép.
- Thống kê count/aggregate hoặc timing khác nhau giúp suy ra dữ liệu của người khác.

Security filter sau method body không phải “vùng cách ly” của dữ liệu. Khi cần confidentiality mạnh, chỉ đọc những record mà caller có quyền tiếp cận và kiểm tra truy cập trước khi tạo side effect.

### 7.6. Tập immutable, parallel và shared mutable state

Filtering ở proxy có thể cần sửa collection hiện có. Những tình huống đáng tránh:
- `List.of(...)` / unmodifiable collection.
- Danh sách được cache/được chia sẻ giữa requests và sau đó bị sửa.
- Danh sách được đọc song song ở thread khác.
- Stream/lazy result gắn với transaction đã đóng.
- Collection custom có thứ tự hoặc semantics remove khác mặc định.

Ưu tiên **defensive copy** cho demo, và **query-scoped results** cho production. Không để một user làm thay đổi collection dùng chung chỉ vì method security filter đã remove phần tử.

## 8. Hướng kiến trúc production: lọc ngay tại database và policy

### 8.1. Ràng buộc owner/tenant tại repository

Với truy vấn phân trang, về mặt khái niệm nên làm:

~~~sql
SELECT id, owner_id, tenant_id, title
FROM documents
WHERE tenant_id = :trustedTenantId
  AND owner_id = :authenticatedUserId
  AND deleted = false
ORDER BY id DESC
LIMIT :pageSize OFFSET :pageOffset;
~~~

Các named parameters ở đây đại diện giá trị **server bind bằng prepared parameters**, không được nối chuỗi SQL từ client. `trustedTenantId` và `authenticatedUserId` phải lấy từ principal/session đã được xác minh cùng membership/tenant scope đáng tin; không coi `?tenantId=...` hoặc `?ownerId=...` là nguồn quyền.

Spring Data JPA cũng có thể diễn đạt truy vấn có scope bằng repository method:

~~~java
// Snippet của một Spring Data JPA repository,
// cần entity DocumentEntity và imports theo project thực tế.
Page<DocumentEntity> findByTenantIdAndOwnerIdAndDeletedFalse(
    UUID tenantId, UUID ownerId, Pageable pageable
);
~~~

Đây là **snippet**, không phải project runnable ở phần 9 (project demo chỉ dùng in-memory store). Với database thật, bảo đảm index phù hợp, xử lý soft delete, row-level permissions, multi-tenant isolation và count query cùng scope. Không truyền ownerId tùy ý từ client vào hàm rồi nghĩ signature đã bảo mật.

### 8.2. Kiểm một tài liệu theo ID

Đối với `GET /api/docs/123`, có thể truy vấn:

~~~sql
SELECT id, owner_id, tenant_id, title
FROM documents
WHERE id = :documentId
  AND owner_id = :authenticatedUserId
  AND tenant_id = :trustedTenantId
  AND deleted = false;
~~~

Nếu không có kết quả, policy có thể trả **404** để không tiết lộ tài liệu có tồn tại hay không, hoặc **403** theo hợp đồng hệ thống. Quan trọng là không tải tài liệu của tenant khác rồi vô tình làm lộ nó trước khi từ chối. Khi thao tác ghi, cân nhắc check-and-update atomically, transaction isolation, optimistic locking và concurrency để tránh **TOCTOU** (check permission ở thời điểm khác với thời điểm cập nhật).

### 8.3. Query authorization là nguồn bảo vệ, PostFilter là lớp bổ sung

Bạn có thể giữ một `@PostFilter` trên một danh sách nhỏ do DB đã lọc như **defense in depth** hoặc kiểm một điều kiện UI bổ sung, nhưng:
- Không dựa vào nó như hàng rào duy nhất trước dữ liệu đa tenant.
- Không xem nó là cơ chế ẩn bất kỳ lỗi repository query nào.
- Luôn test negative cases (không thấy record của user khác) tại **API và repository/service**.
- Kiểm tra cache key, paging/count, export và các entry point khác.

### 8.4. Từ chối toàn bộ batch thay vì tự động bỏ qua

Với batch update/delete, thông thường việc bỏ phần tử không được phép là **nguy hiểm** nếu client nghĩ đã xử lý đủ. Nên kiểm quyền cho tất cả resource, rồi xử lý atomically hoặc trả danh sách lỗi rõ ràng theo contract. Trong nhiều hệ thống, **request có một phần tử trái quyền phải bị từ chối**, không tự “lọc cho qua”.

`@PreFilter` phù hợp hơn với các thao tác có semantics “chỉ xử lý những mục người dùng được phép”, như preview hoặc chọn dữ liệu nhỏ cho một phép tính an toàn, khi caller đã chấp nhận filtered subset. Nếu sử dụng nó trên dữ liệu client gửi, phải biết field được lọc có thể bị giả mạo.

### 8.5. Pessimistic vs optimistic authorization

Ở môi trường dữ liệu biến động, trạng thái owner/tenant/permission có thể thay đổi ngay giữa bước kiểm và bước đọc/ghi. Với tài nguyên nhạy cảm, thiết kế operation sao cho điều kiện quyền xuất hiện trong chính câu lệnh thao tác hoặc được bảo vệ bằng transaction/locking phù hợp. Ví dụ SQL cập nhật có thể kèm `WHERE id=... AND owner_id=... AND tenant_id=...`, rồi kiểm `rowsAffected` thay vì tin một check tách biệt chạy trước đó lâu.

## 9. Ví dụ đầy đủ: Spring Boot 3.3.13, Security 6, Java 17, MockMvc

Project minh họa rõ **hai thời điểm lọc**, sử dụng tập tài liệu nhỏ **được server tạo ra** để không tin owner giả từ JSON client:

1. `GET /api/docs` gọi method có `@PostFilter`: method tạo List gồm tài liệu alice và bob, rồi filter output theo user.
2. `GET /api/preview` gọi method có `@PreFilter`: controller lấy một bản sao List **mutable** của store trước khi gọi service; filter input trước khi method body nhận danh sách.
3. `GET /api/docs/{id}` dùng `@PreAuthorize` và một policy bean kiểm owner của tài liệu theo ID trước khi service trả dữ liệu; minh họa một lựa chọn phù hợp hơn với truy cập một object.
4. `GET /health` không cần authentication; mọi `/api/**` yêu cầu HTTP Basic.
5. Test MockMvc cho alice, bob, charlie (không có tài liệu), anonymous, truy cập ID trái quyền và fallback deny.

**Mục đích học tập:** store có 3 bản ghi trong bộ nhớ, không phải database, không áp dụng pagination, không có write operation. Việc gọi `store.all()` để học về prefilter/postfilter **cố ý không phải mô hình truy vấn production**. Với dữ liệu thật/khối lượng lớn, dùng repository query có owner/tenant scope từ phần 8.

### 9.1. Cấu trúc project

~~~text
method-filter-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/methodfilter/
    │       ├── MethodFilterApplication.java
    │       ├── SecurityConfig.java
    │       ├── DocumentStore.java
    │       ├── DocumentPolicy.java
    │       ├── DocumentService.java
    │       └── DocumentController.java
    └── test/
        └── java/com/example/methodfilter/
            └── MethodFilterTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-filter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/methodfilter/MethodFilterApplication.java`**

~~~java
package com.example.methodfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodFilterApplication.class, args);
    }
}
~~~

### 9.2. SecurityConfig: bật method security và HTTP Basic

**`src/main/java/com/example/methodfilter/SecurityConfig.java`**

~~~java
package com.example.methodfilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF vẫn bật mặc định; project chỉ gọi GET.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("charlie")
                .password(hash)
                .roles("USER")
                .build()
        );
    }
}
~~~

Cấu hình này dùng HTTP Basic để dễ kiểm thử authentication thật; password demo chỉ dành cho localhost. HTTP Basic truyền password dưới dạng Base64 trong Authorization header, **không mã hóa mật khẩu**. Production cần HTTPS và cơ chế quản lý credentials phù hợp.

### 9.3. DocumentStore: dữ liệu nhỏ, trả bản sao mutable

**`src/main/java/com/example/methodfilter/DocumentStore.java`**

~~~java
package com.example.methodfilter;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    public record Doc(long id, String owner, String title) {
    }

    private final List<Doc> data = List.of(
        new Doc(1L, "alice", "Design"),
        new Doc(2L, "bob", "Finance"),
        new Doc(3L, "alice", "Notes")
    );

    public List<Doc> all() {
        // Spring Security có thể loại phần tử trong collection.
        return new ArrayList<>(data);
    }

    public boolean ownedBy(long id, String owner) {
        return data.stream().anyMatch(d ->
            d.id() == id && d.owner().equals(owner));
    }

    public Doc byId(long id) {
        return data.stream()
            .filter(d -> d.id() == id)
            .findFirst()
            .orElseThrow();
    }
}
~~~

`data` cố ý là immutable `List.of` để tránh service vô tình sửa kho dữ liệu toàn cục. Mỗi lần đọc `all()` tạo `new ArrayList<>(data)` riêng, nên pre/post filtering có thể loại phần tử mà **không làm thay đổi dữ liệu gốc**. Đây là kỹ thuật **đúng cho demo rất nhỏ**, không phải lý do để tải cả database vào ArrayList.

### 9.4. DocumentPolicy: kiểm ownership theo ID từ store

**`src/main/java/com/example/methodfilter/DocumentPolicy.java`**

~~~java
package com.example.methodfilter;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentStore store;

    public DocumentPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long id) {
        return authentication != null
            && store.ownedBy(id, authentication.getName());
    }
}
~~~

Policy đọc owner từ **store phía server**, không tin field do client gửi. Trong code production, cần áp dụng owner **và tenant** (nếu có) tại query, không truy vấn toàn bộ rồi lọc. Một document ID không tồn tại trong store sẽ trả false, dẫn đến access denial trước khi service trả dữ liệu — minh họa một lựa chọn tránh tiết lộ sự tồn tại của tài liệu.

### 9.5. DocumentService: ba kiểu bảo vệ

**`src/main/java/com/example/methodfilter/DocumentService.java`**

~~~java
package com.example.methodfilter;

import java.util.List;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

import com.example.methodfilter.DocumentStore.Doc;

@Service
public class DocumentService {

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("isAuthenticated()")
    @PostFilter("filterObject.owner() == authentication.name")
    public List<Doc> listSmallSample() {
        // Method chạy rồi mới lọc; chỉ dùng với 3 phần tử demo.
        return store.all();
    }

    @PreAuthorize("isAuthenticated()")
    @PreFilter("filterObject.owner() == authentication.name")
    public List<Doc> previewFromCandidates(List<Doc> candidates) {
        // Đến method body thì các phần tử không khớp đã bị loại.
        // Trả immutable copy SAU khi @PreFilter đã thực hiện.
        return List.copyOf(candidates);
    }

    @PreAuthorize("isAuthenticated() and @documentPolicy.canRead(authentication, #p0)")
    public Doc findOwned(long id) {
        return store.byId(id);
    }
}
~~~

Phân biệt ba lời gọi:

- `listSmallSample()`: method trả danh sách có đủ alice/bob trước; `@PostFilter` lọc **sau**.
- `previewFromCandidates(...)`: caller truyền List mutable; `@PreFilter` lọc **trước**; method có thể lấy `List.copyOf` sau khi input đã lọc.
- `findOwned(id)`: không tải toàn bộ list để postfilter; `@PreAuthorize` gọi một policy của server kiểm quyền của ID trước khi method body đọc record.

Biểu thức `#p0` là cách tham chiếu **tham số thứ nhất** trong SpEL, tránh phụ thuộc tên biến được compiler lưu. `@documentPolicy` là bean có tên tường minh trong `@Component("documentPolicy")`. `isAuthenticated()` bảo đảm anonymous không được coi là user thật cho các method này.

Với production, cách `canRead` kiểm store rồi `byId` đọc lại vẫn có khả năng **TOCTOU** nếu quyền/dữ liệu thay đổi giữa hai bước. Trong ví dụ store bất biến, không có vấn đề đó; với DB thật dùng repository query có điều kiện owner/tenant và transaction/locking phù hợp.

### 9.6. DocumentController: gọi qua service proxy

**`src/main/java/com/example/methodfilter/DocumentController.java`**

~~~java
package com.example.methodfilter;

import java.util.List;
import java.util.Map;

import com.example.methodfilter.DocumentStore.Doc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;
    private final DocumentStore store;

    public DocumentController(DocumentService service, DocumentStore store) {
        this.service = service;
        this.store = store;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/docs")
    public List<Doc> docs() {
        return service.listSmallSample();
    }

    @GetMapping("/api/preview")
    public List<Doc> preview() {
        // Bản sao mutable; chỉ có ba record do server tạo.
        return service.previewFromCandidates(store.all());
    }

    @GetMapping("/api/docs/{id}")
    public Doc one(@PathVariable long id) {
        return service.findOwned(id);
    }
}
~~~

Controller gọi `DocumentService` qua **Spring-managed bean được inject**, không tự gọi một method trong cùng class. Đây là điều kiện quan trọng để annotations trên service thực sự được method security intercept.

`/api/preview` cố ý vẫn tải cả ba record trước khi `@PreFilter` — đúng để thấy rõ **prefilter không tối ưu query**. Với dữ liệu lớn, controller không được dùng `store.all()` kiểu này; phải gọi repository query đã scoped theo user/tenant.

### 9.7. Test bằng Spring Security MockMvc

**`src/test/java/com/example/methodfilter/MethodFilterTests.java`**

~~~java
package com.example.methodfilter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodFilterTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublicButDocumentsRequireAuthentication()
            throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        mvc.perform(get("/api/docs"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void postFilterKeepsOnlyAlicesDocuments() throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].owner").value("alice"))
            .andExpect(jsonPath("$[0].id").value(1))
            .andExpect(jsonPath("$[1].owner").value("alice"))
            .andExpect(jsonPath("$[1].id").value(3));
    }

    @Test
    void preFilterKeepsOnlyBobsDocument() throws Exception {
        mvc.perform(get("/api/preview")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].owner").value("bob"))
            .andExpect(jsonPath("$[0].id").value(2));
    }

    @Test
    void noMatchingElementsIsAnEmptyList() throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("charlie", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));

        mvc.perform(get("/api/preview")
                .with(httpBasic("charlie", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void policyProtectsIndividualDocuments() throws Exception {
        mvc.perform(get("/api/docs/1")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        mvc.perform(get("/api/docs/1")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/docs/2")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void missingDocumentIdDoesNotRevealAnotherRecord()
            throws Exception {
        mvc.perform(get("/api/docs/999")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedUrlIsDenied() throws Exception {
        mvc.perform(get("/unexpected")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Điểm QA trong tests:**

- Test anonymous 401 đi qua HTTP Basic và HTTP authorization.
- Test alice chỉ nhận id 1, 3 (không thấy bob) từ `@PostFilter`.
- Test bob chỉ nhận id 2 từ `@PreFilter`.
- Test charlie cho thấy **kết quả rỗng không phải exception**, nếu method hợp lệ và không có phần tử thuộc owner.
- Test `/api/docs/{id}` kiểm policy trước khi trả một object: alice không đọc được id 2 và bob không đọc được id 1.
- Test fallback deny, giúp phát hiện API ngoài chính sách.
- Không dùng `@WithMockUser` để bỏ qua kiểm tra password: `httpBasic` giúp test đi qua authentication thật ở config demo.

Mã HTTP **403** khi ID không thuộc owner/không tồn tại là lựa chọn policy của demo. Hệ thống production có thể trả 404 khi muốn giảm rò rỉ sự tồn tại resource, nhưng phải thống nhất contract và kiểm soát error messages.

### 9.8. Lệnh chạy và output dự kiến

Cần **JDK 17+, Maven**, và khả năng tải dependency lần đầu:

~~~bash
mvn test
mvn spring-boot:run
~~~

Kết quả **mong đợi** của test suite khi project đã được tạo đúng và dependency hợp lệ là `BUILD SUCCESS`. Các lệnh này được cung cấp để người học tự chạy, **chưa được thực thi trong tài liệu**.

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/health
# Dự kiến 200, {"status":"ok"}

curl -i http://localhost:8080/api/docs
# Dự kiến 401, HTTP Basic challenge

curl -i -u alice:demo-pass http://localhost:8080/api/docs
# Dự kiến 200, JSON gồm id=1 và id=3

curl -i -u bob:demo-pass http://localhost:8080/api/preview
# Dự kiến 200, JSON chỉ có id=2

curl -i -u charlie:demo-pass http://localhost:8080/api/docs
# Dự kiến 200, []

curl -i -u bob:demo-pass http://localhost:8080/api/docs/1
# Dự kiến 403

curl -i -u alice:demo-pass http://localhost:8080/api/docs/1
# Dự kiến 200, JSON tài liệu id=1
~~~

Trên Windows PowerShell có thể dùng `curl.exe`. HTTP Basic trên Internet phải đi qua HTTPS; chỉ dùng HTTP localhost cho học tập và không đưa password demo vào sản phẩm.

## 10. Đo hiệu năng đúng cách: không chỉ thấy response ít dòng

### 10.1. Đừng đánh giá bằng số phần tử JSON trả ra

Một endpoint trả 20 phần tử không có nghĩa database chỉ truy vấn 20 dòng. Hãy đo:

- Query SQL thực và **số dòng DB đọc/trả**.
- Thời gian DB và network.
- Số entity/DTO được tạo.
- Tổng số query (bao gồm lazy loading/N+1).
- Heap allocation, GC, CPU và p95/p99 latency.
- Khả năng chịu tải khi số records của tenant tăng.
- Các paths export/search/pagination ngoài endpoint đang test.

Nếu dữ liệu lớn hoặc user chỉ được quyền một phần nhỏ, hỏi cụ thể: “Câu SQL có predicate scope bằng principal/tenant và có LIMIT/OFFSET sau khi lọc không?”. Nếu câu trả lời là không, việc dùng `@PostFilter` có thể chỉ **che** dữ liệu ở response, chưa tối ưu hay hoàn thiện bảo mật.

### 10.2. Ví dụ so sánh số lượng

| Tiêu chí | Lọc sau bằng @PostFilter | Lọc tại DB trước phân trang |
| --- | --- | --- |
| Rows DB phải xem | Có thể toàn bộ tập N | Tập khớp scope, dùng index phù hợp |
| Rows truyền tới app | Có thể N | Tối đa kích thước trang cần thiết |
| Java objects tạo | Có thể N | Thường tỷ lệ với page size |
| Số phần tử phải duyệt ở Java để kiểm owner | Có thể N | Có thể kiểm bổ sung trên page nhỏ |
| Page total/count đúng scope | Dễ sai nếu không thiết kế thêm | Có thể tính đúng khi query count cùng WHERE |
| Nguy cơ dữ liệu ngoài quyền lọt log/cache | Cao hơn nếu xử lý trước filter | Giảm khi query không tải dữ liệu ngoài scope |
| Hiệu quả khi N lớn | Dễ gặp bottleneck/OOM | Khả năng mở rộng tốt hơn nếu query/index đúng |

Bảng chỉ mang tính mô hình hóa; database vẫn phải lập kế hoạch query, scan/index theo cấu trúc và predicate. Điều quan trọng là **đừng chuyển toàn bộ dữ liệu lên JVM chỉ để lọc bằng SpEL**.

### 10.3. Tests cần bổ sung khi dùng database thật

1. User A không thấy record của B ở page đầu và **mọi page sau**.
2. Tổng số bản ghi/`totalElements` chỉ tính record user được phép xem.
3. Thứ tự sort/cursor không thay đổi sai do filter sau.
4. Tenant A không nhận record tenant B dù cùng owner ID hoặc tên người dùng.
5. Query không gọi `findAll()` toàn bảng khi client yêu cầu page nhỏ.
6. Owner/permission bị đổi trong lúc request vẫn không gây cập nhật trái quyền.
7. Không có log/cache/event chứa record ngoài quyền của caller.
8. Test với lượng dữ liệu đủ lớn để quan sát heap, latency và số query.

## 11. Những lỗi dễ gặp khi áp dụng @PreFilter/@PostFilter

| Hiểu nhầm / lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên `@EnableMethodSecurity` | Annotation không được method-security interceptor áp dụng như mong muốn | Bật method security và có integration test |
| Gọi method annotated bằng `this.method()` trong cùng bean | Bypass Spring AOP proxy | Gọi qua bean khác/proxy đã được quản lý |
| Dùng private/final method làm boundary | Proxy có thể không intercept | Thiết kế public service boundary phù hợp |
| `@PreFilter` nhận `List.of(...)` | Có thể gặp UnsupportedOperationException | Dùng defensive mutable collection hoặc query đúng scope |
| Filter một List chia sẻ giữa requests | Cross-request mutation/data race | Không chia sẻ mutable input, tạo copy cục bộ |
| Nghĩ `@PreFilter` tự giảm số dòng query | Caller có thể đã findAll trước đó | Đặt scope trong repository query |
| Nghĩ `@PostFilter` lọc trước khi DB đọc | DB/app đã xử lý dữ liệu ngoài quyền | Query WHERE owner/tenant trước khi tải |
| Dùng PostFilter sau LIMIT/OFFSET | Trang thiếu, count/cursor sai | WHERE security scope trước paging |
| Dùng list đã bị lọc để chứng minh batch update đủ toàn bộ | Âm thầm bỏ thao tác, vi phạm atomicity | Với writes, kiểm toàn bộ rồi reject/transaction |
| Dùng owner từ body JSON làm bằng chứng quyền | Client tự giả owner | So với owner lưu server-side |
| Dùng `authentication.getName()` nhưng auth đến từ header tự khai | Identity không đáng tin | Xác minh credentials/token trước |
| Truy cập lazy relations trong SpEL cho N records | N+1/lazy-loading/timeout | Scope query, projection, index |
| Trả `Page` rồi mong PostFilter tự sửa total count | Metadata paging sai | Pagination trên tập đã authorized tại DB |
| Dùng annotation để “xóa” log/event đã phát | Dữ liệu đã lộ trước khi filter | Không fetch/emit dữ liệu ngoài scope |
| Trộn `@PostAuthorize` và `@PostFilter` như hai tên đồng nghĩa | Lệch semantic allow/deny vs per-item filtering | Chọn đúng annotation theo contract |
| Dùng chỉ HTTP matcher cho mọi policy dữ liệu | Không kiểm owner/tenant của record | Bảo vệ ở service/repository |
| Tắt CSRF vì endpoint trả JSON | Cookie-auth write endpoint dễ có CSRF risk | Đánh giá credentials và giữ CSRF phù hợp |

### 11.1. Trường hợp SpEL không nhận đúng filterObject

Đầu tiên kiểm kiểu phần tử thực tế trong List. Nếu List chứa `Map.Entry` thay vì record `Doc`, biểu thức `filterObject.owner()` sẽ không tồn tại. Nếu object có getter JavaBean, dùng accessor đúng; nếu là record, dùng `owner()`. Đừng bắt exception rồi `permitAll` chỉ để tránh 403/500.

### 11.2. Kết quả không được lọc dù có annotation

Kiểm tra:
- `@EnableMethodSecurity` đã được áp dụng?
- Method nằm trên Spring bean và lời gọi thực sự đi qua proxy?
- Annotation đặt trên method được intercept, không phải self-invocation?
- Có cấu hình `prePostEnabled=false`?
- Caller đang test đúng method/bean hay gọi trực tiếp đối tượng tự tạo bằng `new`?
- Nếu dùng async/threads khác, `SecurityContext` có được propagate theo cách an toàn, hay authentication đã mất?

Không sửa bằng cách tự gọi `SecurityContextHolder.setContext(...)` tùy tiện trong thread pool mà thiếu cleanup; có cơ chế security-context propagation được Spring hỗ trợ cho tác vụ async.

### 11.3. PostFilter và exceptions

Nếu method body ném exception trước khi trả List, postfilter **không thể tạo một List an toàn để trả về**. Hãy xử lý lỗi repository/service đúng loại, không bắt mọi exception rồi trả danh sách rỗng để che lỗi hệ thống. Một response rỗng vì không có quyền/không có dữ liệu khác với một database outage.

## 12. Chiến lược chọn annotation theo use case

| Use case | Cách ưu tiên |
| --- | --- |
| Cho phép/từ chối toàn bộ method trước khi thực thi | `@PreAuthorize` |
| Từ chối/cho phép một object trả về dựa trên returnObject | `@PostAuthorize` khi cần; cân nhắc check sớm |
| Preview từ một collection **nhỏ**, cho phép bỏ phần tử | `@PreFilter` |
| Lọc tập kết quả **nhỏ, in-memory**, không chứa dữ liệu nhạy cảm trước filter | `@PostFilter` có thể phù hợp |
| Đọc hàng chục nghìn / hàng triệu records của nhiều user | Query scoped theo owner/tenant tại DB, phân trang |
| Đọc record theo id | Repository query ID + owner/tenant; method policy bổ sung |
| Batch update/delete yêu cầu atomicity | Authorize toàn bộ batch, reject nếu có item trái quyền |
| Dữ liệu cần row-level security chặt chẽ | Policy server-side + DB/RLS/query scope + tests |
| Report tổng hợp/counters | Tính aggregation trên tập được phép ở DB, không aggregate trước PostFilter |
| Async/stream processing lượng lớn | Authorization scoped tại nguồn, streaming có giới hạn và kiểm soát context |

Một mô hình ổn định cho production thường là **HTTP authentication + method-level coarse permission + repository-level owner/tenant scope + service business-policy checks**. Không dùng một annotation để thay cả bốn lớp.

## 13. Checklist trước khi đưa vào production

**Tính đúng đắn và bảo mật:**

1. `@EnableMethodSecurity` đang hoạt động và có test gọi xuyên qua proxy.
2. Phân biệt filter từng phần tử với authorize toàn method.
3. Không dùng owner/tenant từ client làm bằng chứng quyền.
4. Với batch write, xác định rõ **filter subset** hay **reject all**; không âm thầm mất phần tử.
5. Method security không bypass vì self-invocation/private/final.
6. Không đưa dữ liệu ngoài quyền qua log, cache, message bus hoặc export trước khi lọc.
7. HTTP authorization/CSRF đúng với authentication mechanism.
8. Có test user A/B, anonymous, permission thiếu, tenant khác và collection rỗng.

**Hiệu năng và data lifecycle:**

9. Không dùng `findAll()` trên bảng lớn rồi PostFilter để trả một page.
10. Ràng buộc owner/tenant ở query và index phù hợp.
11. Query count/cursor/sort dùng **cùng scope** với query trả dữ liệu.
12. Tránh N+1/lazy expressions trong SpEL trên tập lớn.
13. Không prefilter trên collection shared/unmodifiable nếu cần loại phần tử.
14. Đo số rows/query, allocation, latency và memory ở quy mô lớn.
15. Có chiến lược cập nhật quyền/tenant tránh TOCTOU khi ghi dữ liệu.
16. Lỗi hạ tầng được phân biệt với không có bản ghi/không có quyền; không nuốt exceptions.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `@PreFilter` chạy trước hay sau method body?

**Đáp:** Trước method body, trên các phần tử của tham số tập hợp được chọn. Phần tử không đạt expression bị loại khỏi input method nhận được.

**Câu 2.** `@PostFilter` chạy trước hay sau database query bên trong method?

**Đáp:** Sau khi method body hoàn thành và tạo kết quả. Nếu method query toàn bảng, việc tải dữ liệu đã xảy ra trước khi lọc.

**Câu 3.** `filterObject` là gì?

**Đáp:** Là phần tử hiện đang được đánh giá trong input/output tập hợp, không phải toàn bộ List.

**Câu 4.** Với List gồm alice, bob, alice và user alice, expression lọc theo owner trả gì?

**Đáp:** Hai phần tử của alice; ví dụ trong bài là id 1 và id 3. Với user charlie không có phần tử, kết quả có thể là List rỗng.

**Câu 5.** Nếu caller dùng `List.of(...)` làm input cho `@PreFilter` thì cần chú ý gì?

**Đáp:** List đó immutable. Việc filter có thể cần loại phần tử, nên nên dùng defensive mutable copy hoặc thiết kế query phù hợp.

**Câu 6.** Khi batch có một item trái quyền, dùng `@PreFilter` rồi trả thành công có luôn đúng không?

**Đáp:** Không. Nó có thể bỏ lặng lẽ item, làm sai atomicity và contract. Thao tác ghi quan trọng thường cần reject toàn batch khi có item trái quyền.

**Câu 7.** Đọc 1.000.000 rows rồi `@PostFilter` còn 40 có hiệu quả không?

**Đáp:** Không. DB, network và JVM vẫn phải xử lý một triệu bản ghi; cần scope tại query rồi phân trang.

**Câu 8.** Tại sao LIMIT 20 trước PostFilter có thể làm page sai?

**Đáp:** Vì 20 dòng đầu toàn bảng có thể chỉ chứa vài dòng thuộc user; count/cursor/pageSize không còn phản ánh tập được phép.

**Câu 9.** `@PreFilter` có tự tối ưu truy vấn trước đó ở caller không?

**Đáp:** Không. Nếu caller đã gọi findAll, dữ liệu đã bị tải. Prefilter chỉ chạy khi lời gọi method annotated được intercept.

**Câu 10.** Vì sao `this.filteredMethod()` trong cùng bean đáng nghi?

**Đáp:** Lời gọi có thể bypass Spring AOP proxy nên method-security interceptor không chạy.

**Câu 11.** Khi lọc `filterObject.owner() == authentication.name`, owner field từ JSON client có đủ đáng tin không?

**Đáp:** Không. Client có thể giả mạo owner; phải đối chiếu quyền sở hữu thực từ dữ liệu server-side hoặc DB.

**Câu 12.** `@PostAuthorize` khác `@PostFilter` thế nào?

**Đáp:** PostAuthorize quyết định cho phép/từ chối kết quả/toàn method, còn PostFilter lọc từng phần tử của collection output.

**Câu 13.** Có thể thay tenant isolation bằng `@PostFilter` cho tất cả API không?

**Đáp:** Không. Cần query/policy giới hạn tenant trước khi dữ liệu rời DB, kể cả pagination và các đường dữ liệu khác.

**Câu 14.** Một POST dùng session cookie bị 403 dù method có `@PreFilter` đúng. Có thể vì sao?

**Đáp:** CSRF filter có thể từ chối trước khi đến method. Phải phân tích security filter chain và CSRF, không mặc định do expression lọc phần tử.

**Câu 15.** Với method trả Page, có nên kỳ vọng PostFilter tự điều chỉnh total count không?

**Đáp:** Không. Để pagination chính xác và mở rộng tốt, hãy áp authorization WHERE trước khi DB sort/limit/count, sau đó trả Page theo tập đã được phép.

**Ghi nhớ:** **`@PreFilter` giảm phần tử đầu vào method, `@PostFilter` giảm phần tử đầu ra caller nhận, nhưng cả hai không thay thế truy vấn có điều kiện quyền tại nguồn dữ liệu. Với tập lớn, cần lọc owner/tenant ngay trong DB, thực hiện phân trang sau lọc, giữ service authorization và tránh side effects trước khi filter.**