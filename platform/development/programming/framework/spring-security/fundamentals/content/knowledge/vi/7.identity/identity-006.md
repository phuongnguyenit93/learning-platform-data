# Vai trò, quyền thao tác và phạm vi token: phân biệt role, permission, scope

Trong Spring Security, ba thuật ngữ **role**, **permission** và **scope** thường cùng xuất hiện ở phần kiểm soát truy cập, nhưng chúng giải quyết những câu hỏi khác nhau. Một người có vai trò ADMIN có thể thực hiện những nghiệp vụ nào? Một thao tác cần quyền orders:write hay chỉ orders:read? Một access token được cấp scope orders.read có cho phép ứng dụng gọi mọi API đơn hàng hay không?

Nếu gom ba khái niệm thành một trường “role” duy nhất, thiết kế dễ cấp quyền quá rộng. Nếu kiểm scope của token mà bỏ qua quyền sở hữu từng đơn, một user hợp lệ vẫn có thể xem đơn của người khác. Nếu viết hasRole("ADMIN") với JWT chỉ mang claim scope, Spring Security có thể trả 403 do không có authority ROLE_ADMIN. Bài học này giải thích **ranh giới giữa danh tính, vai trò, quyền thao tác, phạm vi token và quyền đối với tài nguyên cụ thể**, đồng thời chỉ ra chúng được biến thành GrantedAuthority và kiểm tra như thế nào.

Bài thực hành dùng **Java 17+, Spring Boot 3.3.6, Spring Security 6.x, Spring MVC và MockMvc**. Phần chạy được sử dụng **HTTP Basic + tài khoản in-memory** để minh họa role và permission rõ ràng. Phần OAuth2/JWT là **mô hình triển khai riêng** có nêu dependency và yêu cầu Identity Provider, không dùng JWT giả hoặc bỏ qua xác minh chữ ký.

## 1. Câu hỏi mà từng khái niệm trả lời

| Khái niệm | Câu hỏi cốt lõi | Ví dụ | Ai thường định nghĩa/cấp? |
| --- | --- | --- | --- |
| **Role (vai trò)** | Chủ thể đang đảm nhiệm nhóm trách nhiệm nào trong hệ thống? | USER, SUPPORT, ACCOUNTANT, ADMIN. | Hệ thống quản lý danh tính, nhóm quản trị hoặc nghiệp vụ. |
| **Permission (quyền thao tác)** | Chủ thể được làm hành động cụ thể nào? | orders:read, orders:write, refunds:approve. | Ứng dụng/domain, chính sách phân quyền, quản trị quyền. |
| **Scope (phạm vi token)** | Credential OAuth2 được phát hành cho phép client yêu cầu những loại truy cập nào tại resource server? | orders.read, orders.write, profile. | Authorization Server theo đăng ký client, grant, consent và policy. |
| **Object-level authorization** | Chủ thể được thực hiện hành động trên **đối tượng nào**? | Alice chỉ xem đơn của Alice; người hỗ trợ chỉ thấy khách trong tenant được phân công. | Service/domain, hệ thống quyền dữ liệu, quy tắc tenant/ownership. |

Một cách nhìn hữu ích:

- **Role** là nhóm trách nhiệm ở mức tổng quát.
- **Permission** là hành động có tên rõ ràng trên một loại resource.
- **Scope** giới hạn **năng lực thể hiện trong access token hoặc access grant**. Token scope không tự chứng minh user sở hữu một bản ghi, cũng không tự cho phép API vượt chính sách nội bộ.
- **Quan hệ với resource** (owner, tenant, phòng ban, trạng thái đơn, hạn mức tiền) quyết định liệu quyền trừu tượng có được sử dụng **trên đối tượng cụ thể** hay không.

Các nhóm này **có thể được ánh xạ với nhau theo chính sách đáng tin**, nhưng không phải là ba từ đồng nghĩa. Tên quyền là quy ước do dự án chọn; Spring Security không tự hiểu ý nghĩa nghiệp vụ của chuỗi orders:read.

## 2. Phân biệt authentication và authorization trước

**Authentication (xác thực):** xác minh bằng chứng danh tính theo cơ chế tin cậy. Ví dụ HTTP Basic kiểm cặp user/password; OAuth2 Resource Server kiểm access token theo decoder/introspection và các điều kiện áp dụng.

**Authorization (phân quyền):** sau khi có Authentication hợp lệ, quyết định được gọi method/path và thao tác trên resource nào.

~~~text
HTTP request
    |
    v
Xác thực credential đúng cơ chế
    |
    v
Authentication(principal, authorities, ...)
    |
    +--> Cần role?       ROLE_ADMIN?
    |
    +--> Cần permission? orders:read?
    |
    +--> Cần scope?      SCOPE_orders.read?
    |
    +--> Cần quyền object? ownerId / tenantId / trạng thái?
    |
    v
Được phép --> Controller/Service xử lý
Bị từ chối --> 401 hoặc 403/404 theo ngữ cảnh, không rò dữ liệu
~~~

Lưu ý sơ đồ là **khái niệm**. Trong một ứng dụng, kiểm role/permission/scope có thể ở tầng URL, Service/method hoặc custom AuthorizationManager; chúng không bắt buộc tồn tại trong từng request. Kiểm tra quyền theo đối tượng cần đúng nơi có dữ liệu đáng tin cậy.

Không tin Header X-Role: ADMIN, query userId=alice hoặc phần payload JWT vừa Base64-decode làm bằng chứng về danh tính hay quyền. Cơ chế xác thực phải xác minh credential trước khi ánh xạ thành authorities.

## 3. Role — nhóm vai trò, không phải thao tác cụ thể

Role thường mô tả **nhóm trách nhiệm**:

| Role | Ý nghĩa nghiệp vụ giả định | Quyền dự kiến khi hệ thống quyết định cấp |
| --- | --- | --- |
| USER | Khách/nhân viên dùng chức năng cơ bản. | Đọc đơn hợp lệ của mình. |
| ORDER_EDITOR | Người được phép chỉnh sửa đơn trong phạm vi phụ trách. | Đọc và tạo/cập nhật đơn được phép. |
| SUPPORT | Hỗ trợ khách hàng có giới hạn. | Xem thông tin hỗ trợ theo tenant và mục đích. |
| FINANCE | Nhân viên tài chính. | Xem giao dịch, đề xuất hoặc phê duyệt theo hạn mức. |
| ADMIN | Quản trị viên một phạm vi hệ thống. | Một nhóm thao tác quản trị được quy định cụ thể. |

**Tên role không tự mang quyền trong Spring Security.** Ví dụ ROLE_ADMIN không tự có orders:read, refunds:approve hoặc ROLE_USER. Hệ thống phải cấp các authority tương ứng, cấu hình role hierarchy hoặc có một chính sách explicit nếu muốn ADMIN bao hàm quyền của nhóm khác.

Một role như ADMIN cũng nên **có phạm vi**: ADMIN của tenant A có thể không quản trị tenant B; “SUPER_ADMIN toàn hệ thống” là quyền rất nhạy cảm và cần được giới hạn.

### 3.1. ROLE_ trong Spring Security

Spring Security biểu diễn quyền đã cấp bằng **GrantedAuthority**, thường là chuỗi trong SimpleGrantedAuthority. Với cấu hình prefix mặc định:

~~~java
// Các mảnh expression dùng trong SecurityFilterChain hoặc @PreAuthorize:
hasRole("ADMIN")                  // kiểm authority "ROLE_ADMIN"
hasAuthority("ROLE_ADMIN")        // kiểm đúng chuỗi "ROLE_ADMIN"
hasAuthority("ADMIN")             // kiểm đúng chuỗi "ADMIN", khác hai dòng trên
~~~

Trong Spring Security, **hasRole("ADMIN") thường là shortcut kiểm ROLE_ADMIN**. Tiền tố role có thể được cấu hình lại; bài này dùng mặc định ROLE_. Đừng viết hasRole("ROLE_ADMIN") khi API đang mong tên role chưa có prefix; hãy chọn hasRole("ADMIN") hoặc hasAuthority("ROLE_ADMIN") đúng ý nghĩa.

Trong UserDetailsBuilder, **roles("ADMIN")** thường thêm ROLE_ADMIN. **authorities("ROLE_ADMIN", "orders:read")** cấp danh sách authority đúng như các chuỗi đã liệt kê. Nếu dùng kết hợp roles() và authorities(), cần hiểu builder có thể thay thế tập authority đã thiết lập; trong ví dụ hoàn chỉnh bên dưới ta dùng **authorities(...) một lần** để tránh nhầm.

### 3.2. Role-based access control (RBAC)

RBAC tổ chức phân quyền qua quan hệ:

~~~text
User / Service Account
    |
    v
Assigned Roles
    |
    v
Role -> Permissions (policy của ứng dụng)
    |
    v
Hành động được phép trên loại resource
    |
    v
Kiểm điều kiện bổ sung trên resource cụ thể
~~~

RBAC giúp quản lý người dùng theo trách nhiệm và đơn giản hóa việc cấp quyền. Nhưng với nghiệp vụ nhiều tenant/owner/hạn mức, role một mình không đủ. Một role SUPPORT không có nghĩa được đọc mọi hồ sơ của mọi khách hàng.

**Role hierarchy** chỉ hoạt động khi được cấu hình có chủ đích. Ví dụ quan hệ ADMIN > STAFF > USER có thể được dùng trong hệ thống, nhưng không phải mặc định Spring Security. Cần test quyền phát sinh từ hierarchy và tránh cho role cấp thấp kế thừa đặc quyền ngoài ý muốn.

## 4. Permission — quyền thao tác theo chức năng

Permission mô tả **loại hành động được phép**, nên dễ kiểm soát hơn role quá rộng. Một quy ước đặt tên có thể là:

~~~text
orders:read
orders:write
orders:cancel
refunds:request
refunds:approve
users:invite
users:disable
reports:export
~~~

Đây là **tên được thiết kế trong ứng dụng**, không phải danh sách do Spring Security định nghĩa. Chúng ta sẽ dùng dấu hai chấm trong permission để phân biệt với dấu chấm trong OAuth scope của ví dụ. Không có cơ chế đặc biệt nào được kích hoạt chỉ vì chuỗi chứa dấu hai chấm.

Một permission tốt cần có **hành động và đối tượng cấp loại** đủ rõ:

- orders:read: đọc thông tin đơn trong phạm vi được cấp.
- orders:write: tạo/cập nhật đơn nếu nghiệp vụ cho phép.
- refunds:approve: phê duyệt hoàn tiền trong phạm vi công việc.
- reports:export: xuất báo cáo; có thể cần điều kiện thêm về lượng dữ liệu hoặc role.

### 4.1. Permission so với role

Giả sử Alice là USER và Bob là ORDER_EDITOR. Nếu cả hai có ROLE_USER, kiểm tra duy nhất hasRole("USER") không phân biệt được người đọc và người sửa. Bạn có thể cấp:

| Principal | Authorities đã xác thực | Hệ quả |
| --- | --- | --- |
| alice | ROLE_USER, orders:read | Được đọc loại tài nguyên hợp lệ; chưa có quyền ghi. |
| bob | ROLE_USER, orders:read, orders:write | Được đọc, có quyền gọi thao tác ghi khi thỏa điều kiện dữ liệu. |
| viewer | ROLE_USER | Có role USER nhưng chưa được cấp orders:read. |
| admin | ROLE_ADMIN, orders:read, orders:write, refunds:approve | Được thực hiện các thao tác liệt kê, nhưng vẫn tuân theo chính sách đối tượng/tenant. |

**ROLE_USER không tự bao hàm orders:read**. Nếu chính sách muốn USER có quyền đọc thì hệ thống cấp thêm orders:read khi tạo Authentication, hoặc định nghĩa ánh xạ role → permission một cách rõ ràng.

### 4.2. hasAuthority và hasPermission khác nhau

**hasAuthority("orders:write")** kiểm xem Authentication có GrantedAuthority mang chuỗi chính xác đó hay không. Nếu có, nó cho phép qua điều kiện authority. Nó **không tra bảng đơn** và cũng **không kiểm số tiền/hạn mức**.

**hasPermission(...)** trong method-security expression là một hook dành cho **PermissionEvaluator** hoặc cơ chế được tùy biến để kiểm quyền ở cấp đối tượng. Nó **không tự biết** owner, tenant hoặc quy tắc nghiệp vụ nếu chưa có implementation phù hợp.

Ví dụ minh họa:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
public OrderView readOrder(long id) {
    // Chỉ kiểm permission chung; còn cần owner/tenant check.
    throw new UnsupportedOperationException("illustration only");
}
~~~

Đây là **mảnh code minh họa không độc lập**, vì phần tra đơn và check owner chưa được viết. Trong bài chạy được bên dưới, ta đặt kiểm tra owner trong Service và chỉ trả dữ liệu khi cả permission lẫn quyền theo đối tượng đều thỏa mãn.

### 4.3. Hạn chế của permissions chỉ dựa vào chuỗi

Nếu hàng nghìn permission động được ghi thẳng vào JWT hoặc session, việc thu hồi quyền giữa vòng đời token có thể bị chậm. Các quyền nhạy cảm như hoàn tiền cần xét trạng thái hiện thời, tenant, hạn mức, phê duyệt kép, thời gian và audit. Không nên mô hình hóa tất cả quy tắc động chỉ bằng một danh sách string lâu hạn.

## 5. Scope — phạm vi truy cập của token OAuth2

**Scope là khái niệm của OAuth 2.0.** Nó mô tả phạm vi truy cập mà client được cấp trong một access grant/access token. Authorization Server quyết định scope dựa trên client registration, grant type, consent và policy; Resource Server dùng thông tin token đã xác minh để giới hạn thao tác.

Ví dụ một client được cấp:

~~~text
orders.read
orders.write
profile
~~~

Các scope trên là **tên minh họa**. Tên scope thật phụ thuộc hợp đồng API và Authorization Server. Token có scope orders.read nghĩa là nó có thể đáp ứng **một điều kiện truy cập theo scope** của API, chứ không có quyền vượt qua toàn bộ business authorization.

### 5.1. Scope có phải role của người dùng không?

**Không.** Một access token có thể đại diện cho:

- Một user qua authorization code flow hoặc dạng delegated authorization khác.
- Một service/client qua **client credentials** mà không có end-user nào.
- Một bên gọi được ủy quyền cho một tập scope hạn chế.

Ví dụ, dịch vụ đồng bộ số liệu có scope reports.read nhưng không có vai trò USER như một người dùng; ngược lại, một nhân viên có role ADMIN trong hệ thống A không mặc nhiên nhận access token có scope của hệ thống B.

Một resource server phải phân biệt **danh tính user**, **danh tính client**, **audience/đối tượng nhận token** và **scope**. Tránh tự suy ra ownerId của đơn bằng client_id khi token không đại diện user. Nếu nghiệp vụ yêu cầu người dùng, hãy xác minh luồng delegation và principal thật.

### 5.2. Scope không thể hiện đủ quyền dữ liệu

Giả sử access token của Alice hợp lệ, có scope orders.read và được phát hành cho orders-api. Alice yêu cầu GET /api/orders/102 nhưng đơn 102 thuộc Bob.

Để cho phép, cần **đồng thời** thỏa:

1. Token được xác minh, chưa hết hạn và dành cho resource server đúng mục đích.
2. Token có scope phù hợp với API, ví dụ orders.read.
3. Nếu API yêu cầu permission nội bộ hoặc chính sách vai trò, principal đáp ứng được điều kiện đó theo mapping tin cậy.
4. Alice được xem **đúng đơn 102** theo owner/tenant/policy; ở ví dụ này là **không**.

Có scope không biến user thành chủ sở hữu. Cũng không có nghĩa token mang scope orders.write được đọc mọi đơn nếu API chỉ quy định write. Các quan hệ read/write phải được định nghĩa rõ; không giả định write tự bao hàm read.

### 5.3. Scope thường xuất hiện ở đâu?

Trong JWT access token, Authorization Server có thể phát hành claim:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

JSON trên chỉ **minh họa claim**, không phải một JWT có chữ ký hợp lệ. Giá trị token thật còn có các trường như exp, iat, nbf và cấu trúc header.payload.signature tùy chuẩn/thiết kế. Một số provider dùng claim **scp** dưới dạng danh sách; Resource Server cần map theo chuẩn và cấu hình thực tế.

**JWT chỉ được Base64-decode không chứng minh gì về độ tin cậy.** Phải xác minh chữ ký hoặc introspection theo định dạng token, issuer, thời hạn và các điều kiện audience/client/scopes của ứng dụng. Scope trong token gửi tới API sai audience không được chấp nhận chỉ vì chuỗi scope trùng.

## 6. Role, permission, scope cùng đi vào GrantedAuthority như thế nào?

Trong Spring Security, **GrantedAuthority** là hợp đồng chung để framework kiểm các quyền ở runtime. Những chuỗi có nguồn gốc khác nhau có thể cùng nằm trong Authentication#getAuthorities() **nếu cơ chế xác thực/converter đã tạo chúng**.

| Nguồn | Giá trị nguồn | Authority trong mô hình ví dụ | Điều kiện kiểm |
| --- | --- | --- | --- |
| UserDetails role | roles("ADMIN") | ROLE_ADMIN | hasRole("ADMIN") hoặc hasAuthority("ROLE_ADMIN"). |
| UserDetails permission | authorities("orders:read") | orders:read | hasAuthority("orders:read"). |
| JWT scope đã xác minh | scope = "orders.read" | SCOPE_orders.read theo converter mặc định | hasAuthority("SCOPE_orders.read"). |
| JWT scope đã xác minh | scp = ["orders.write"] | SCOPE_orders.write khi converter nhận định dạng phù hợp | hasAuthority("SCOPE_orders.write"). |
| JWT custom roles | roles = ["ADMIN"] | **Không tự động** biến thành ROLE_ADMIN theo cấu hình mặc định | Cần converter nếu ứng dụng quyết định tin claim này. |
| User's ownership | ownerId = alice trong DB | **Không tự động** thành một GrantedAuthority | Kiểm tra object-level trong domain/Service. |

**hasRole**, **hasAuthority** và **scope mapping** là các thao tác khác nhau:

~~~java
// Mảnh biểu thức trong cấu hình/annotation (không phải file Java chạy riêng).
hasRole("ADMIN")                        // đòi ROLE_ADMIN
hasAuthority("orders:read")             // đòi chính xác orders:read
hasAuthority("SCOPE_orders.read")       // đòi chính xác SCOPE_orders.read
~~~

Đừng viết hasRole("orders.read") để kiểm OAuth2 scope. Cũng đừng viết hasAuthority("orders.read") và kỳ vọng Resource Server mặc định tự bỏ prefix SCOPE_.

### 6.1. Vì sao prefix quan trọng?

Một ứng dụng có thể nhận ba authority hợp lệ:

~~~text
ROLE_ADMIN
orders:read
SCOPE_orders.read
~~~

Chúng là **ba chuỗi khác nhau**. Spring Security không suy ra quan hệ giữa chúng nếu bạn không định nghĩa mapping hoặc policy rõ. Prefix giúp phân biệt **role nội bộ** với **scope có nguồn gốc từ token**, đồng thời giảm nguy cơ cho một scope có tên ADMIN bị hiểu nhầm thành vai trò quản trị.

Đổi authority prefix sang ROLE_ cho mọi scope có thể gây cấp quyền cao hơn dự kiến. Chỉ thay đổi conversion khi đã xem xét issuer, audience, cấu trúc claim, cách cấp token và chính sách đích.

### 6.2. Spring Security không tự biến custom JWT roles thành role nội bộ

Nếu JWT có:

~~~json
{
  "roles": ["ADMIN"],
  "scope": "orders.read"
}
~~~

Một JWT converter mặc định thường tạo authority từ scope/scp như **SCOPE_orders.read**, không mặc nhiên lấy claim roles để tạo **ROLE_ADMIN**. Nếu Identity Provider có claim roles được đảm bảo tin cậy và ứng dụng muốn dùng, bạn phải định nghĩa converter phù hợp và kiểm lại role mapping qua tests.

Quan trọng: **đừng đọc roles từ một JWT chưa được xác minh**. Việc thêm ROLE_ADMIN cho token bất kỳ có claim roles=ADMIN là lỗ hổng nghiêm trọng.

## 7. Mô hình phân quyền theo nhiều lớp

Một chính sách vững vàng thường có các lớp:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Authentication: Basic / session / verified access token"]
    B --> C["Endpoint policy: authenticated / role / permission / scope"]
    C --> D["Service policy: thao tác, trạng thái, hạn mức"]
    D --> E["Object policy: ownerId, tenantId, quan hệ được cấp"]
    E --> F["Action allowed"]
    C --> G["Denied"]
    D --> G
    E --> G
~~~

Ví dụ ứng dụng đơn hàng:

| Hành động | Điều kiện tổng quát | Điều kiện tài nguyên cụ thể |
| --- | --- | --- |
| Xem đơn | Permission orders:read hoặc scope orders.read, tùy API và identity model. | Đơn thuộc user/tenant hoặc có quyền đọc thay mặt hợp lệ. |
| Tạo đơn | Permission orders:write hoặc scope tương ứng. | Giá, sản phẩm, trạng thái khách và tenant hợp lệ; không tin giá do client tự gửi. |
| Chỉnh sửa đơn | Permission orders:write. | Đơn đang ở trạng thái cho phép sửa và caller có quan hệ được cấp. |
| Hoàn tiền | Permission refunds:approve; có thể yêu cầu role hoặc cấp độ xác thực cao hơn. | Hạn mức, segregation of duties, trạng thái thanh toán, phê duyệt, audit. |
| Quản trị người dùng | Role ADMIN và permission users:manage (nếu policy yêu cầu). | Cùng tenant/phạm vi quản lý; tránh tự nâng quyền. |

**Nhiều điều kiện là AND**, trừ khi nghiệp vụ chủ động thiết kế OR: có role phù hợp **và** permission cụ thể **và** quyền trên object nếu tất cả được yêu cầu. Khi dùng một biểu thức có OR, phải chứng minh rằng một nhánh không bỏ qua các ràng buộc trọng yếu.

Trong hệ thống đa tenant, thường cần **RBAC + ABAC/ReBAC**: role/permission cho khả năng chung, thuộc tính resource và mối quan hệ cho phạm vi dữ liệu. Chỉ dựa vào một chuỗi role trong token là chưa đủ.

## 8. Ví dụ chạy được: Role và permission trong Spring Boot

Demo này tập trung vào **hai khái niệm role/permission** bằng HTTP Basic, sau đó phần 11 giải thích scope/JWT như một cơ chế token riêng. Nhờ vậy bạn có thể thực thi test mà không cần IdP hoặc ký JWT giả.

**Yêu cầu:** JDK 17+, Maven 3.9+, port 8080. Spring Boot 3.3.6 được dùng cố định cho bài lab; khi triển khai thật nên chọn dòng được hỗ trợ và cập nhật bản vá.

~~~text
role-permission-demo/
  pom.xml
  src/main/java/com/example/roleperm/
    RolePermissionApplication.java
    OrderView.java
    OrderService.java
    ApiController.java
    SecurityConfig.java
  src/test/java/com/example/roleperm/
    AuthorizationTests.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>role-permission-demo</artifactId>
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

### 8.2. RolePermissionApplication.java

~~~java
package com.example.roleperm;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RolePermissionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RolePermissionApplication.class, args);
    }
}
~~~

Lớp main ở package gốc com.example.roleperm, nên Spring Boot tìm các bean Controller, Service và Configuration trong package này.

### 8.3. OrderView.java

~~~java
package com.example.roleperm;

public record OrderView(long id, String owner, String status) {
}
~~~

Java record có sẵn ở Java 17. Đây là DTO cho dữ liệu demo, không phải entity JPA. Trong ứng dụng thật, tránh trả thẳng entity có dữ liệu mật hoặc các trường mà caller không được phép đọc.

### 8.4. OrderService.java

~~~java
package com.example.roleperm;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final Map<Long, OrderView> orders = Map.of(
        101L, new OrderView(101L, "alice", "CREATED"),
        102L, new OrderView(102L, "bob", "PAID")
    );

    @PreAuthorize("hasAuthority('orders:read')")
    public OrderView read(long id, Authentication authentication) {
        OrderView order = orders.get(id);
        if (order == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found");
        }

        boolean isAdmin = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        if (!isAdmin && !order.owner().equals(authentication.getName())) {
            throw new AccessDeniedException("Order access denied");
        }
        return order;
    }

    @PreAuthorize("hasAuthority('orders:write')")
    public String create(Authentication authentication) {
        // Demo chỉ chứng minh quyền gọi, không ghi database.
        return "created:" + authentication.getName();
    }

    @PreAuthorize("hasAuthority('refunds:approve')")
    public String approveRefund() {
        // Demo chỉ chứng minh quyền gọi, không thực hiện hoàn tiền.
        return "refund-approved";
    }
}
~~~

**Vì sao kiểm hai lần?**

- Annotation **@PreAuthorize** kiểm permission chung trước khi thực thi phương thức Service: orders:read, orders:write hoặc refunds:approve.
- Hàm read(...) còn kiểm **owner**: alice có orders:read vẫn không được xem đơn thuộc bob. ADMIN trong demo được cho xem cả hai đơn, nhưng đây là **quyết định nghiệp vụ minh họa**; nếu có tenant boundary, ngay cả ADMIN cũng phải bị giới hạn theo tenant được quản lý.
- Nếu không có đơn, Service trả 404. Nếu thiếu quyền đọc đơn của người khác, Service phát AccessDeniedException, dẫn tới xử lý từ chối quyền theo cấu hình Spring Security.
- Hai hàm create và approveRefund chỉ trả string để test permission; không tạo tác động ghi hoặc hoàn tiền thật.

Bảo vệ ở tầng Service giúp cùng một nghiệp vụ vẫn có rule khi được gọi từ nhiều Controller. Với tác vụ chạy ngoài HTTP (job, message consumer), phải xác định principal/service identity hoặc policy phù hợp; đừng dựa vào một Authentication vắng mặt để bỏ qua quyền.

**@PreAuthorize chỉ hoạt động khi bật method security** và lời gọi đi qua Spring bean proxy theo mô hình hỗ trợ. Self-invocation bên trong cùng class có thể bỏ qua proxy; test qua đường gọi thật.

### 8.5. ApiController.java

~~~java
package com.example.roleperm;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    private final OrderService orders;

    public ApiController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/orders/{id}")
    public OrderView readOrder(
            @PathVariable long id, Authentication authentication) {
        return orders.read(id, authentication);
    }

    @PostMapping("/orders")
    public String createOrder(Authentication authentication) {
        return orders.create(authentication);
    }

    @PostMapping("/refunds")
    public String approveRefund() {
        return orders.approveRefund();
    }
}
~~~

Controller không tự đọc role từ header do client gửi. Nó chuyển Authentication đã được Spring Security xác thực đến Service, nơi permission và quyền trên object được áp dụng.

### 8.6. SecurityConfig.java

~~~java
package com.example.roleperm;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
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
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .authorities("ROLE_USER", "orders:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-bob"))
            .authorities("ROLE_USER", "orders:read", "orders:write")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("demo-viewer"))
            .authorities("ROLE_USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .authorities(
                "ROLE_ADMIN",
                "orders:read",
                "orders:write",
                "refunds:approve"
            )
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, viewer, admin
        );
    }
}
~~~

**Các điểm cần kiểm:**

1. **@EnableMethodSecurity** kích hoạt các annotation như @PreAuthorize trên OrderService. Không bật annotation này, URL chỉ yêu cầu authenticated() và có nguy cơ user vượt qua rule permission của Service.
2. **GET /api/public** là public theo chủ đích; các method khác trên path đó không tự được phép.
3. **GET /api/admin** yêu cầu ROLE_ADMIN tại tầng URL. Trong ví dụ, ADMIN không cần được gán ROLE_USER.
4. **/api/** còn lại yêu cầu authenticated() trước khi Controller chạy; permission chi tiết nằm trên Service.
5. **anyRequest().denyAll()** ngăn đường mới ngoài phạm vi định nghĩa tự mở quyền.
6. Các principal được cấp **authority đúng chuỗi**: ROLE_USER/ROLE_ADMIN và orders:read/orders:write/refunds:approve. Không có mapping tự động.
7. HTTP Basic dùng credential demo trong bộ nhớ; mật khẩu lưu thành hash BCrypt trong UserDetails. Chỉ thử trên localhost, không dùng account demo ngoài bài học.
8. **CSRF bảo vệ POST theo cấu hình mặc định.** Test dùng csrf() khi muốn kiểm riêng permission, vì POST thiếu CSRF token có thể bị 403 trước cả @PreAuthorize. Không tắt CSRF chỉ để các lệnh POST chạy được.
9. Khi cần một role hierarchy hoặc mô hình permissions từ DB/IdP, phải khai báo mapping và test. Không tự giả định ADMIN có mọi quyền.

### 8.7. Chạy demo và thử bằng curl

Trong thư mục chứa pom.xml:

~~~bash
mvn test
mvn spring-boot:run
~~~

Trên Windows PowerShell dùng curl.exe; Linux/macOS thường dùng curl.

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/orders/101
curl.exe -i -u alice:demo-alice http://localhost:8080/api/orders/101
curl.exe -i -u alice:demo-alice http://localhost:8080/api/orders/102
curl.exe -i -u viewer:demo-viewer http://localhost:8080/api/orders/101
curl.exe -i -u bob:demo-bob http://localhost:8080/api/orders/102
curl.exe -i -u bob:demo-bob http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

Kết quả **dự kiến**:

| Request | HTTP | Nguyên nhân |
| --- | --- | --- |
| GET /api/public ẩn danh | 200 | Public theo permitAll(). |
| GET /api/orders/101 ẩn danh | 401 | Cần danh tính hợp lệ. |
| Alice đọc đơn 101 | 200 | Có orders:read và là owner; JSON có id=101, owner=alice. |
| Alice đọc đơn 102 | 403 | Có permission chung nhưng không sở hữu đơn Bob. |
| Viewer đọc đơn 101 | 403 | Có ROLE_USER nhưng thiếu orders:read. |
| Bob đọc đơn 102 | 200 | Có orders:read và là owner. |
| Bob vào /api/admin | 403 | ROLE_USER không đồng nghĩa ROLE_ADMIN. |
| Admin vào /api/admin | 200 | Có ROLE_ADMIN. |

HTTP Basic dùng Base64, **không bảo mật credential khi truyền qua HTTP**. Các lệnh dùng http://localhost và mật khẩu giả chỉ để học; với kết nối qua mạng thật dùng HTTPS. Không chụp hay đưa mật khẩu/token thật vào command history/log.

Với POST /api/orders hoặc /api/refunds, một lệnh curl có Basic hợp lệ **nhưng thiếu CSRF token** có thể bị trả 403 từ CsrfFilter. Đây chưa chắc là thiếu permission. Bộ test ở mục sau dùng csrf() để kiểm permission, tách khỏi lý do từ chối do CSRF.

## 9. Kiểm thử quyền bằng MockMvc và Spring Security Test

Tạo file **src/test/java/com/example/roleperm/AuthorizationTests.java**:

~~~java
package com.example.roleperm;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void protectedResourceNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/orders/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/101")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceCannotReadBobsOrder() throws Exception {
        mvc.perform(get("/api/orders/102")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleUserDoesNotAutomaticallyGrantReadPermission()
            throws Exception {
        mvc.perform(get("/api/orders/101")
                .with(httpBasic("viewer", "demo-viewer")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/102")
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void aliceCannotCreateOrderWithoutWritePermission()
            throws Exception {
        mvc.perform(post("/api/orders")
                .with(httpBasic("alice", "demo-alice"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanCreateOrderWhenCsrfIsValid() throws Exception {
        mvc.perform(post("/api/orders")
                .with(httpBasic("bob", "demo-bob"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:bob"));
    }

    @Test
    void bobCannotApproveRefund() throws Exception {
        mvc.perform(post("/api/refunds")
                .with(httpBasic("bob", "demo-bob"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanApproveRefund() throws Exception {
        mvc.perform(post("/api/refunds")
                .with(httpBasic("admin", "demo-admin"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("refund-approved"));
    }

    @Test
    void userRoleIsNotAdminRole() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanReadAdminPage() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Mười ba test** kiểm tra public/authentication, role, permission, quyền sở hữu và trường hợp POST bị chặn bởi CSRF. Tất cả là các bài test có thể chạy theo dự án đã khai báo; không yêu cầu JWT hay IdP thật.

**Cần hiểu giới hạn test:** MockMvc với HTTP Basic thực hiện xác thực trong application test, nhưng không chứng minh TLS, proxy, identity provider production, cache hoặc quyền sở hữu trong DB thật đã an toàn. Với hệ thống có thao tác ghi, test denied còn phải xác minh DB và message queue **không đổi**; demo create/refund cố ý không tạo side effect.

### 9.1. Ma trận quyền rút ra từ demo

| Người gọi | ROLE_ADMIN? | orders:read? | orders:write? | refunds:approve? | Đọc đơn người khác? |
| --- | --- | --- | --- | --- | --- |
| alice | Không | Có | Không | Không | Không. |
| bob | Không | Có | Có | Không | Không. |
| viewer | Không | Không | Không | Không | Không. |
| admin | Có | Có | Có | Có | Có trong bản demo; ứng dụng thật thường còn giới hạn tenant và mục đích. |

Đây là **ma trận cấp quyền cụ thể của demo**, không phải mặc định Spring Security cho mọi role. Thêm một role mới không làm nó tự có permission cũ.

## 10. Kiểm soát quyền tài nguyên cụ thể (BOLA/IDOR)

**BOLA (Broken Object Level Authorization)** hoặc **IDOR** xảy ra khi server cho phép một chủ thể truy cập đối tượng không thuộc quyền của họ, thường qua path ID hoặc query. Một user có quyền orders:read với loại resource đơn hàng vẫn chưa chắc được đọc **đơn số 102**.

Ví dụ request:

~~~http
GET /api/orders/102 HTTP/1.1
Host: localhost:8080
Authorization: Basic <demo-credentials>

~~~

Nếu Alice được xác thực và có orders:read nhưng order 102 thuộc Bob, Service phải từ chối. Cần lấy principal từ SecurityContext/Authentication đã xác thực; **không tin userId do client gửi** để xác định quyền sở hữu.

Trong hệ thống thật có database, một cách tránh truy cập nhầm là truy vấn theo **orderId + tenantId/ownerId được rút ra từ danh tính tin cậy**, hoặc gọi một policy engine/Service check trước khi trả object. Trả 403 hay 404 tùy chính sách bảo mật, nhưng không trả nội dung của Bob và không tạo side effect.

**Điều kiện động** có thể quan trọng hơn role: một nhân viên tài chính chỉ phê duyệt refund dưới một hạn mức, trong giờ làm việc, hoặc phải khác người tạo lệnh. Không nên cấp refunds:approve như một quyền vĩnh viễn không giới hạn nếu nghiệp vụ đòi thêm điều kiện.

### 10.1. Khi nào cần PermissionEvaluator hoặc custom AuthorizationManager?

Với logic đơn giản, hasAuthority("orders:read") cộng với kiểm owner trong Service là đủ rõ. Nếu nhiều module cần cùng một quy tắc phức tạp, có thể tạo bean authorization policy hoặc PermissionEvaluator, rồi gọi từ @PreAuthorize hay AuthorizationManager phù hợp.

Ví dụ **mảnh method-security minh họa**:

~~~java
@PreAuthorize(
    "hasAuthority('orders:read') and @orderPolicy.canRead(authentication, #id)"
)
public OrderView read(long id) {
    // @orderPolicy phải là bean Spring thực sự được triển khai.
    return null;
}
~~~

Code trên **không phải file Java độc lập** và cố ý không định nghĩa orderPolicy; nó cho thấy cách kết hợp một permission tổng quát với chính sách owner/tenant. Ở production, quyết định quyền phải dựa trên dữ liệu tin cậy và xử lý đúng khi object không tồn tại hoặc đã thay đổi trong thời gian request.

## 11. OAuth2/JWT: ánh xạ scope riêng cho Resource Server

Phần này là **biến thể kiến trúc khác** với project HTTP Basic ở mục 8. Không chèn trực tiếp cấu hình Bearer vào project đó rồi dùng cùng các test Basic: nguồn Authentication và authority có thể khác, và chính sách Service phải được thiết kế lại cho token.

### 11.1. Cấu hình tối thiểu cho Resource Server

Với Spring Boot Servlet/MVC, thêm dependency **spring-boot-starter-oauth2-resource-server** (thay cho cấu hình HTTP Basic trong một project Resource Server thực tế). Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Khai báo issuer tin cậy theo **Identity Provider đã triển khai thật**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test
~~~

Domain trên chỉ là ví dụ, **không phải một IdP sẵn sàng hoạt động**. Resource Server cần metadata và public keys được cung cấp theo chuẩn. Với JWT, Spring Security xác minh chữ ký và các claim liên quan theo cấu hình; ứng dụng còn phải ràng buộc **audience được cấp cho API**, scope, yêu cầu tenant/client, expiry và các chính sách nghiệp vụ. Không coi issuer-uri mẫu là cấu hình production đầy đủ.

Một SecurityFilterChain riêng cho Resource Server có thể có dạng:

~~~java
// Mảnh bean dành cho project Resource Server độc lập,
// với dependency + issuer-uri hoặc JwtDecoder tin cậy.
@Bean
SecurityFilterChain resourceServer(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

**Cần import** các kiểu Bean, HttpSecurity, HttpMethod, SecurityFilterChain và Customizer từ Spring; đây là mảnh cấu hình, không phải project tự chạy. Nếu muốn dùng cùng Controller/Service ở mục 8, phải phối hợp lại policy và Authentication/permission mapping thay vì chỉ sao chép bean.

### 11.2. Mapping JWT scope sang SCOPE_*

Trong Spring Security OAuth2 Resource Server, với JWT access token hợp lệ có claim **scope** (chuỗi cách nhau bởi dấu cách) hoặc **scp** (cách biểu diễn được converter hỗ trợ), converter mặc định thường tạo:

~~~text
Token claim: "scope": "orders.read orders.write"
          |
          v
GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
~~~

Vì vậy **hasAuthority("SCOPE_orders.read")** kiểm authority từ scope. **hasAuthority("orders:read")** trong project Basic ở mục 8 lại kiểm permission nội bộ khác; **chúng không tương đương tự động**.

Một endpoint dùng token có scope orders.read nhưng Service vẫn có:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
~~~

có thể bị **403** dù đã qua rule URL SCOPE_orders.read. Phải quyết định rõ: Service kiểm scope trực tiếp theo token, hay convert scope tin cậy thành permission nội bộ bằng một policy mapping cụ thể. Không thêm hai rule mâu thuẫn rồi nới lỏng chúng bằng permitAll().

### 11.3. Tùy chỉnh converter cần hiểu phần bị thay thế

Nếu một provider phát hành claim permissions thay vì scope, Spring Security có **JwtGrantedAuthoritiesConverter** và **JwtAuthenticationConverter**. Ví dụ mảnh cấu hình:

~~~java
// Mảnh bean dành cho project Resource Server, không ghép vào demo Basic.
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
        new JwtGrantedAuthoritiesConverter();

    granted.setAuthoritiesClaimName("permissions");
    granted.setAuthorityPrefix("");

    JwtAuthenticationConverter result =
        new JwtAuthenticationConverter();

    result.setJwtGrantedAuthoritiesConverter(granted);
    return result;
}
~~~

Cần import hai lớp từ **org.springframework.security.oauth2.server.resource.authentication** và Bean từ Spring. Nếu muốn dùng converter này, cấu hình JWT DSL cần được nối tới converter phù hợp, ví dụ:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))
)
~~~

Đây là mảnh DSL **dành riêng cho cấu hình Resource Server**. Nó chỉ an toàn khi **issuer/audience/key/claim** đã được xác minh và các giá trị permission thật sự do nguồn đáng tin cấp. Đồng thời việc thay converter mặc định như ví dụ có thể làm **mất các authority SCOPE_*** nếu không chủ động kết hợp chúng; muốn hỗ trợ cả scope và permissions phải xây converter hợp nhất và test.

Không mặc nhiên map mọi claim roles/permissions từ mọi tenant thành đặc quyền cao. Có thể cần chuẩn hóa namespace, kiểm authorized party/client, audience, issuer và giới hạn những role nào được chấp nhận. **Cấp ROLE_ADMIN dựa trên một claim tùy tiện là nguy hiểm.**

### 11.4. Scope trong access token khác ID token

**Access token** được dùng để gọi Resource Server theo chính sách được cấp. **ID token** của OpenID Connect cung cấp thông tin xác thực cho client trong luồng OIDC, không phải credential thay thế access token để gọi mọi API.

Nếu hệ thống dùng **opaque token**, Resource Server thường gọi introspection thay vì tự giải mã JWT; scope/authorities vẫn cần mapping và kiểm tra phù hợp. Không yêu cầu mọi token phải là JWT.

### 11.5. Những kiểm tra không thể bỏ qua

- **Chữ ký và thuật toán**: chỉ chấp nhận chữ ký/khóa/algorithms được tin cậy theo cấu hình.
- **Issuer (iss)**: token do nguồn được ủy quyền cấp.
- **Thời hạn (exp, nbf)** và skew: token chưa hết hạn và đã tới thời điểm hợp lệ.
- **Audience (aud)**: token được cấp cho API nhận nó. Không dùng token cho API A để tự động truy cập API B.
- **Scope/authority**: token được cấp quyền gọi thao tác đó.
- **Chủ thể và client**: phân biệt delegated user với service-only client; principal có quan hệ với resource không?
- **Tenant và object policy**: kiểm ngay tại Service/domain với nguồn dữ liệu hiện thời.
- **Thu hồi/quyền thay đổi**: JWT đã phát hành có thể tiếp tục chứa claim cũ tới khi hết hạn; thiết kế TTL, revoke/introspection hoặc kiểm tra policy động cho tác vụ nhạy cảm.

**Token mang scope là một giới hạn quan trọng, không phải giấy thông hành toàn hệ thống.**

## 12. Status 401 và 403 khi role, permission, scope không đủ

| Tình huống | HTTP điển hình | Lý do |
| --- | --- | --- |
| Không gửi credential tới API cần xác thực | **401** | Chưa có Authentication hợp lệ. |
| HTTP Basic gửi sai mật khẩu | **401** | Chứng cứ xác thực không hợp lệ. |
| Bearer token thiếu/hết hạn/sai chữ ký | **401** | Token không vượt qua xác thực; response/challenge tùy cơ chế. |
| User đã đăng nhập nhưng thiếu ROLE_ADMIN | **403** | Authenticated nhưng bị từ chối role. |
| User có ROLE_USER nhưng thiếu orders:read | **403** | Thiếu permission cần thiết. |
| Token hợp lệ nhưng thiếu scope orders.read | Thường **403**, có thể có Bearer insufficient_scope challenge phù hợp | Token được xác thực nhưng thiếu authority mà API yêu cầu. |
| Token có scope nhưng user không sở hữu orderId | **403 hoặc 404** theo policy | Scope không thay thế phân quyền theo object. |
| Cơ chế cookie/session gửi POST thiếu CSRF token khi CSRF áp dụng | Thường **403** | Bị CSRF protection từ chối trước logic permission. |

**Không suy luận chỉ từ 403 rằng role bị thiếu.** Có thể là permission, scope, CSRF, tenant hoặc chính sách khác. Dùng request ID/log bảo mật có kiểm soát để xác định rule nào từ chối, tránh ghi raw token hoặc session cookie.

Với Bearer Resource Server, **WWW-Authenticate: Bearer** có thể chứa thông tin lỗi theo chuẩn; tuy nhiên response cụ thể phụ thuộc cấu hình và không nên làm lộ dữ liệu policy nhạy cảm. Với form login, request chưa xác thực có thể bị redirect 302 thay vì 401; hãy xác định AuthenticationEntryPoint và client.

## 13. Những lỗi thiết kế quyền phổ biến

### 13.1. Dùng role quá rộng cho mọi nghiệp vụ

**hasRole("ADMIN")** để cho phép hoàn tiền có vẻ đơn giản, nhưng có thể cấp quyền hoàn tiền cho quản trị viên kỹ thuật không có trách nhiệm tài chính. Nên dùng permission **refunds:approve**, kèm hạn mức/approval, rồi quản lý role nào có permission đó.

### 13.2. Tin rằng quyền ghi tự bao hàm quyền đọc

**orders:write** và **orders:read** là hai chuỗi độc lập. Nếu muốn write tự cho phép read, phải cấp cả hai hoặc triển khai policy/hierarchy rõ ràng và kiểm thử. Điều tương tự áp dụng với scope orders.write và orders.read.

### 13.3. Đổi scope thành ROLE_ADMIN

Một scope có tên admin không nên tự chuyển thành authority ROLE_ADMIN chỉ vì trùng nhãn. Scope gắn với quyền của token/client, còn vai trò quản trị thuộc policy và danh tính được tin cậy. Nếu có business case mapping đặc biệt, cần chốt issuer, audience, tenant, client và danh mục role được phép.

### 13.4. Chỉ kiểm permission ở Controller

Nếu một Service được gọi qua batch job, message listener hoặc một Controller khác mà thiếu kiểm soát, cùng nghiệp vụ có thể bị vượt quyền. Đặt rule ở Service/domain hoặc một policy engine dùng chung khi phù hợp, đồng thời giữ URL policy để ngăn request sớm.

### 13.5. Chỉ kiểm scope trên endpoint rồi bỏ quyền theo object

Đây là nguồn lỗi IDOR/BOLA: Alice có scope orders.read và truy cập orderId của Bob. Bổ sung kiểm owner/tenant và test cross-user/cross-tenant.

### 13.6. Không kiểm audience hoặc nguồn claim

Token được phát hành cho service khác có thể có scope tên giống nhau. Chỉ dùng scope để quyết định quyền mà không xác minh token dành cho resource server hiện tại có thể tạo lỗ hổng token confusion. Không tin custom roles claim khi issuer/tenant không được ủy quyền cấp role đó.

### 13.7. Cấp quyền qua giá trị client tự nhập

Role, permission, tenant hoặc owner phải lấy từ nguồn đã xác thực và policy backend. Request body {"role":"ADMIN"} hoặc header X-Role: ADMIN không phải bằng chứng. Với cập nhật user, tránh mass assignment làm người gọi tự sửa trường role/permissions.

### 13.8. JWT giữ quyền cũ quá lâu

Một nhân viên bị thu hồi refunds:approve nhưng JWT còn sống nhiều giờ có thể vẫn chứa claim cũ. Xem xét TTL ngắn, token revocation/introspection, kiểm tra quyền động cho hành động nhạy cảm và audit.

### 13.9. Bật method security nhưng gọi method nội bộ sai cách

Spring method security thường dựa trên Spring AOP proxy. **Self-invocation** qua this.someSecuredMethod() có thể bỏ qua proxy, và object tự new không phải bean do Spring quản lý. Test qua Controller hoặc Spring bean được container cấp.

### 13.10. Trả 403 sau khi đã tạo side effect

Nếu Service ghi DB hoặc phát message rồi mới kiểm permission/owner, trả 403 vẫn không an toàn. Đưa authorization trước thay đổi và dùng transaction/idempotency phù hợp.

### 13.11. Quyền trong cache không gắn principal

Nếu trả dữ liệu người A từ cache cho người B vì cache key chỉ dựa trên URL, thì kiểm role/scope ở API có thể vẫn chưa bảo vệ dữ liệu. Với response nhạy cảm, cache policy và phân tách theo principal/tenant cần được thiết kế riêng.

### 13.12. Coi CORS là phân quyền

CORS giới hạn JavaScript trong browser đọc cross-origin response theo policy; curl và backend client không chịu cùng hạn chế. Không thay authentication, role, permission, scope hoặc CSRF bằng Access-Control-Allow-Origin.

## 14. Cách thiết kế role/permission/scope cho dự án

### 14.1. Bắt đầu bằng ma trận hành động

Trước hết liệt kê **resource + action + phạm vi dữ liệu + mức độ nhạy cảm**, không bắt đầu bằng danh sách vai trò mơ hồ.

| Use case | Permission nội bộ | Scope ở API token nếu cần | Điều kiện bổ sung |
| --- | --- | --- | --- |
| Đọc đơn | orders:read | orders.read | Owner hoặc quyền đọc thay mặt đúng tenant. |
| Tạo đơn | orders:write | orders.write | Giá do server kiểm, quota và trạng thái account. |
| Hủy đơn | orders:cancel | orders.cancel | Đơn chưa hoàn tất, đúng owner, có audit. |
| Phê duyệt refund | refunds:approve | refunds.approve | Hạn mức, separation of duties, MFA theo policy. |
| Xuất báo cáo | reports:export | reports.export | Phạm vi tenant, số lượng dữ liệu, mục đích sử dụng. |

Sau đó gán role vào permissions theo nghiệp vụ. Một ADMIN của hệ thống vận hành có thể có reports:export nhưng không có refunds:approve; một FINANCE chuyên trách có thể có refunds:approve với hạn mức.

### 14.2. Tách quyền người dùng và quyền service

Nếu service gọi API bằng **client credentials**, principal là client/service. Nó không có ownerId của end-user theo mặc định. Thiết kế API machine-to-machine riêng hoặc policy service identity rõ ràng; khi cần đại diện user, dùng cơ chế delegation/token exchange được cấp phép. Không đưa userId do client tự gửi rồi coi đó là quyền xem tài nguyên.

### 14.3. Ghi rõ nguồn cấp và độ tin cậy

Với mỗi authority, ghi:

- **Tên** và ý nghĩa chính xác.
- **Ai được cấp** và ai có quyền thu hồi.
- **Nguồn**: DB, role store, verified IdP claim hay OAuth scope.
- **Chu kỳ cập nhật**: theo mỗi request, session hay JWT lifetime.
- **Ranh giới**: tenant, resource owner, môi trường, service/client audience.
- **Chỗ kiểm**: URL, Service/method, database query, policy engine.
- **Test phủ định**: chủ thể thấp quyền, khác tenant, token sai audience, quyền vừa thu hồi.

### 14.4. Dùng deny-by-default và nguyên tắc quyền tối thiểu

Tầng HTTP nên có policy rõ cho public, authenticated, role/scope/permission và **fallback denyAll** ở phạm vi cần bảo vệ. Tầng Service từ chối khi thiếu quyền hoặc thiếu dữ liệu tin cậy. Không tạo một exception “admin bypass mọi thứ” nếu nghiệp vụ không đòi hỏi và chưa qua review.

### 14.5. Kiểm thay đổi trước khi deploy

Khi thêm scope mới, hãy kiểm tương tác với permission nội bộ. Khi thêm role mới, kiểm các authority được gán. Khi chuyển HTTP Basic sang Bearer, kiểm ánh xạ authority và test API trong cùng ma trận. Không sửa một lỗi 403 bằng cách gỡ hết điều kiện phân quyền.

## 15. Bài tập tự đánh giá

1. **Role:** Một user có authority ROLE_USER nhưng không có orders:read. hasRole("USER") và hasAuthority("orders:read") trả kết quả giống nhau không? **Gợi ý:** không; hai authority khác nhau.
2. **Permission:** Alice có orders:read nhưng gọi đơn của Bob. Vì sao vẫn bị từ chối? **Gợi ý:** quyền thao tác chung không bằng quyền sở hữu object.
3. **Scope:** Access token có scope orders.read nhưng được cấp cho API khác. Có nên chấp nhận không? **Gợi ý:** không; cần kiểm audience và token trust.
4. **Converter:** JWT chứa roles=["ADMIN"] nhưng không có ROLE_ADMIN trong Authentication. Điều gì đang thiếu? **Gợi ý:** mapping JWT custom role claim có kiểm chứng và an toàn.
5. **Prefix:** hasAuthority("SCOPE_orders.read") có tương đương hasAuthority("orders:read") không? **Gợi ý:** không, trừ khi mapping có chủ đích.
6. **Client credentials:** Một service token có reports.read có tự mang user identity để lọc đơn của Alice không? **Gợi ý:** không; cần mô hình service identity/delegation.
7. **Role hierarchy:** ROLE_ADMIN có tự kế thừa ROLE_USER không? **Gợi ý:** không, nếu chưa cấp cả hai authority hoặc cấu hình hierarchy.
8. **CSRF:** Bob POST /api/orders với Basic đúng nhưng không kèm CSRF token và nhận 403. Có thể khẳng định Bob thiếu orders:write không? **Gợi ý:** không; cần kiểm CSRF filter.
9. **Method security:** Vì sao @PreAuthorize trên method của object tự tạo bằng new có thể không bảo vệ cuộc gọi? **Gợi ý:** method security dùng Spring-managed proxy.
10. **Quyền động:** JWT chứa refunds:approve nhưng quyền đã bị thu hồi tại DB. Cần cân nhắc cơ chế nào? **Gợi ý:** TTL, revoke, introspection hoặc kiểm quyền theo dữ liệu hiện tại.
11. **Thiết kế:** Hãy lập ma trận quyền cho ba role CUSTOMER, SUPPORT, FINANCE và ba permission orders:read, orders:cancel, refunds:approve, kèm giới hạn owner/tenant/approval.
12. **Kiểm thử:** Viết thêm test admin có ROLE_ADMIN nhưng bị từ chối thao tác mới chưa được gán permission; chứng minh role không mang “siêu quyền” tự động.

### Checklist ghi nhớ

- **Role** = nhóm trách nhiệm; thường biểu diễn thành ROLE_* theo quy ước Spring Security.
- **Permission** = quyền thao tác nghiệp vụ; có thể biểu diễn thành authority như orders:read.
- **Scope** = phạm vi được cấp cho access token OAuth2; converter mặc định thường tạo authority SCOPE_*.
- **Không có mapping tự động** giữa ba loại authority; cấu hình và test quyết định quan hệ của chúng.
- **hasRole("ADMIN") khác hasAuthority("ADMIN") và hasAuthority("SCOPE_admin")**.
- **Có scope/permission vẫn cần owner/tenant/resource-level policy**.
- **JWT phải được xác minh issuer, chữ ký, thời hạn và audience phù hợp**; không tin claim tự giải mã.
- **@EnableMethodSecurity** là điều kiện để dùng @PreAuthorize trong app demo.
- **CSRF, CORS, HTTPS, cache và quản lý secret** là các cơ chế bổ sung, không thay authorization.
- **Kiểm thử quyền bị từ chối và side effects**, không chỉ trường hợp 200.

## Tài liệu tham khảo

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authorities, roles và thiết kế phân quyền.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): requestMatchers, hasAuthority, hasRole và fallback rules.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity, @PreAuthorize và policy theo method.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): scope/scp, SCOPE_ authority và JWT conversion.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): auto-configuration và cách bật method security.

## Kết luận

**Role** mô tả nhóm trách nhiệm, **permission** mô tả thao tác cụ thể và **scope** mô tả phạm vi truy cập được cấp qua OAuth2 access token. Trong Spring Security, cả ba có thể được biểu diễn bằng GrantedAuthority theo nguồn và converter đáng tin, nhưng **ROLE_ADMIN, orders:read và SCOPE_orders.read là các điều kiện khác nhau**. Thiết kế bảo mật tốt cần kiểm chứng credential, giữ mapping authority có chủ đích, kiểm đúng hành động và **quyền trên đối tượng/tenant cụ thể**, rồi kiểm thử cả trường hợp đủ quyền lẫn bị từ chối trước khi có side effects.
