# Tránh chu trình, quyền bao hàm quá rộng và vai trò quản trị vượt dự kiến

> **Module:** Spring Security – authorization  
> **Chủ đề cha:** Role hierarchy  
> **Mục tiêu:** Thiết kế và kiểm thử đồ thị kế thừa vai trò không có chu trình; tránh việc một cạnh `ROLE_A > ROLE_B` vô tình mở rộng hàng loạt quyền; kiểm soát rủi ro tài khoản quản trị, quyền nhạy cảm và phân quyền trên từng đối tượng.

## 1. Bài toán: một cạnh mới có thể cấp thêm nhiều quyền

Giả sử ứng dụng xử lý đơn hàng và có bốn vai trò:

- `ROLE_VIEWER`: xem đơn hàng thông thường.
- `ROLE_SUPPORT`: xử lý hỗ trợ khách hàng; bao gồm các quyền của người xem.
- `ROLE_ADMIN`: quản trị một số tính năng hệ thống; bao gồm quyền hỗ trợ.
- `ROLE_PRIVACY_OFFICER`: xuất dữ liệu cá nhân theo quy trình riêng.

Hierarchy dự kiến:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read

ROLE_PRIVACY_OFFICER > pii:export
~~~

Ký hiệu `A > B` đọc là **A bao hàm B**. Người có `ROLE_ADMIN` có thể được xem như có `ROLE_SUPPORT`, `ROLE_VIEWER` và `order:read` **khi cơ chế authorization đang sử dụng RoleHierarchy này**. Nhưng admin **không tự động có `pii:export`**, vì permission đó thuộc nhánh riêng.

Một thay đổi tưởng nhỏ:

~~~text
ROLE_SUPPORT > pii:export
~~~

bỗng làm cả `ROLE_SUPPORT` **và mọi vai trò phía trên nó**, gồm `ROLE_ADMIN`, nhận quyền xuất dữ liệu cá nhân. Đây là **quyền bao hàm quá rộng**. Có thể không ai sửa một endpoint `/export`, không ai thêm `pii:export` trực tiếp cho admin, nhưng **đường đi bắc cầu trong đồ thị** vẫn làm privilege tăng lên.

Bài học cần ba năng lực:

1. Đọc được **đồ thị quyền hiệu lực**, không chỉ các cạnh khai báo trực tiếp.
2. Phát hiện và ngăn **chu trình** như `ADMIN > SUPPORT > VIEWER > ADMIN`.
3. Giữ **least privilege** và **separation of duties**: admin không mặc định là siêu chủ thể có tất cả chức năng nhạy cảm.

## 2. Role hierarchy trong Spring Security hoạt động ra sao?

Trong Spring Security, một `Authentication` có tập `GrantedAuthority` trực tiếp. Ví dụ tài khoản được cấp:

~~~text
Authentication.getAuthorities():
  ROLE_ADMIN
~~~

`RoleHierarchy` biểu diễn quan hệ một authority/role bao hàm các authority khác. API quan trọng:

~~~java
Collection<? extends GrantedAuthority>
getReachableGrantedAuthorities(
    Collection<? extends GrantedAuthority> authorities);
~~~

Với hierarchy:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read
~~~

đầu vào gồm `ROLE_ADMIN` có thể được mở rộng thành:

~~~text
ROLE_ADMIN
ROLE_SUPPORT
ROLE_VIEWER
order:read
~~~

Đây là **bao đóng bắc cầu** (*transitive closure*) của đồ thị. Người viết cấu hình có thể không thấy một cạnh trực tiếp `ROLE_ADMIN > order:read`, nhưng vẫn có đường đi qua hai vai trò trung gian, nên permission nằm trong tập quyền có thể đạt tới.

### 2.1. Ký hiệu `>` là “bao hàm”, không phải thứ tự quản lý nhân sự

~~~text
ROLE_ADMIN > ROLE_USER
~~~

Nghĩa kỹ thuật là user có `ROLE_ADMIN` cũng thỏa những kiểm tra quyền mà hierarchy ánh xạ qua `ROLE_USER`. Nó **không** mặc định có nghĩa mọi admin phải làm được mọi việc của mọi người dùng trong thực tế.

Ví dụ quyền tự xem trang cá nhân của mình là một hành vi “user-level” hợp lý; nhưng “duyệt giao dịch của chính mình”, “xuất thông tin khách hàng không cần phê duyệt”, “thay đổi thông tin chứng từ đã khóa” không nên tự động cấp cho admin chỉ vì tên vai trò có vẻ cao hơn.

### 2.2. Authority trực tiếp và authority reachable khác nhau

Phân biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Direct granted authority | `ROLE_ADMIN` | Giá trị được đưa vào `Authentication` từ cơ chế xác thực |
| Hierarchy edge | `ROLE_ADMIN > ROLE_SUPPORT` | Quan hệ được cấu hình trong `RoleHierarchy` |
| Reachable authority | `ROLE_VIEWER`, `order:read` | Quyền thấy được sau mở rộng bắc cầu |
| Authorization decision | `hasAuthority("order:read")` | Kiểm tra cụ thể tại HTTP/method policy |
| Object-level authorization | “được đọc đơn hàng 42 thuộc tenant A” | Chính sách trên tài nguyên, không tự phát sinh từ hierarchy |

Một số cơ chế Spring Security có thể sử dụng hierarchy để đánh giá policy; **không được giả định mọi đoạn code gọi thủ công `authentication.getAuthorities().contains(...)` đều tự thấy các quyền mở rộng**. Nếu code tự đọc tập authority trực tiếp, phải hiểu nó có áp dụng `RoleHierarchy` hay không.

## 3. Đồ thị có hướng: nguyên nhân của privilege escalation

Hãy coi mỗi role/authority là một đỉnh, mỗi cạnh `A > B` là một cạnh có hướng từ A sang B.

~~~text
ROLE_ADMIN
    |
    v
ROLE_SUPPORT
    |
    v
ROLE_VIEWER
    |
    v
order:read

ROLE_PRIVACY_OFFICER
    |
    v
pii:export
~~~

Khi một người được gán `ROLE_ADMIN`, tập quyền hiệu lực gồm mọi đỉnh có thể đi tới theo các cạnh. Thêm cạnh mới có thể ảnh hưởng **tất cả đỉnh tổ tiên**, không chỉ nút nằm trực tiếp ở đầu cạnh.

Ví dụ thêm:

~~~text
ROLE_SUPPORT > pii:export
~~~

Tập quyền của `ROLE_ADMIN` sẽ có thêm `pii:export`. Điều này có thể vượt khỏi ý định của người sửa cấu hình: họ nghĩ chỉ cấp cho nhóm hỗ trợ dữ liệu, nhưng thật ra đã cấp cho toàn bộ người sở hữu các role bao hàm `ROLE_SUPPORT`.

**Một cạnh mới phải được review như một thay đổi cấp quyền**, không phải chỉ là chỉnh sửa sơ đồ tổ chức.

### 3.1. Phân biệt “cao hơn” và “được phép rộng hơn”

Trong nhiều tổ chức, chức danh “ADMIN” có quyền quản trị cấu hình nhưng **không nên** duyệt thanh toán, đọc nội dung mật, hoặc thực hiện thao tác kiểm toán nhạy cảm. Một hierarchy tuyến tính:

~~~text
ROLE_SUPER_ADMIN > ROLE_ADMIN > ROLE_MANAGER > ROLE_STAFF > ROLE_USER
~~~

ngầm tạo giả định mỗi vai trò bên trái được làm **mọi việc** mà vai trò bên phải được làm. Đây là giả định rất mạnh, dễ sai khi chức năng có giới hạn pháp lý, tính riêng tư, nghiệp vụ hoặc quy trình phê duyệt.

Thiết kế tốt hơn thường tách:

~~~text
ROLE_SUPPORT > ROLE_VIEWER
ROLE_FINANCE_APPROVER > payment:approve
ROLE_PRIVACY_OFFICER > pii:export
ROLE_INFRA_ADMIN > infra:configure
~~~

Các nhánh không bắt buộc nằm trong một chuỗi kế thừa tổng. Nhiều quyền nhạy cảm nên được cấp riêng, có audit và điều kiện tại thời điểm sử dụng.

## 4. Chu trình là gì và vì sao phải tránh?

Một **chu trình có hướng** xuất hiện nếu từ một đỉnh có thể đi theo các cạnh để quay lại chính đỉnh đó:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > ROLE_ADMIN
~~~

Biểu diễn:

~~~text
ADMIN --> SUPPORT --> VIEWER --> ADMIN
  ^                            |
  +----------------------------+
~~~

Hậu quả:

- Ý nghĩa “role cao bao hàm role thấp” bị phá vỡ: một role ở cuối đường lại có khả năng chạm tới role ở đầu.
- Một người chỉ được cấp `ROLE_VIEWER` có thể đạt tới `ROLE_ADMIN` thông qua các cạnh, tùy implementation và điểm áp dụng hierarchy.
- Khó review, khó giải thích quyền và khó tạo test kỳ vọng.
- Nếu có thuật toán duyệt đồ thị tự viết không đánh dấu đỉnh đã thăm, có thể gây vòng lặp vô tận.
- Một số phiên bản/implementation có thể phát hiện và từ chối hierarchy có chu trình; **không dựa vào điều đó thay cho bước kiểm tra cấu hình trước triển khai**.

### 4.1. Chu trình trực tiếp và gián tiếp

Hai ví dụ nguy hiểm:

~~~text
# Chu trình tự thân:
ROLE_USER > ROLE_USER

# Chu trình hai chiều:
ROLE_A > ROLE_B
ROLE_B > ROLE_A
~~~

Và chu trình dài:

~~~text
ROLE_A > ROLE_B
ROLE_B > ROLE_C
ROLE_C > ROLE_D
ROLE_D > ROLE_A
~~~

Một đồ thị lớn có thể chứa chu trình dù không có hai dòng liền kề tạo ra cặp đối xứng. Vì vậy regex tìm kiếm `A > B` và `B > A` **không đủ**. Cần thuật toán phát hiện chu trình trên toàn bộ tập cạnh.

### 4.2. DAG là một ràng buộc thiết kế hữu ích

Đồ thị vai trò được đề xuất nên là **DAG – Directed Acyclic Graph**, tức đồ thị có hướng không có chu trình.

DAG cho phép:

1. Diễn giải hướng “bao hàm” nhất quán.
2. Tính tập authority reachable có thể kiểm toán.
3. Tạo topology và trình bày sơ đồ bằng thứ tự topo.
4. Review tác động khi thêm một cạnh.
5. Viết unit test rằng một role thấp không đạt được role cao.

DAG **chưa đủ bảo đảm an toàn**. Một DAG hoàn toàn không có chu trình vẫn có thể có cạnh quá rộng, ví dụ `ROLE_USER > payment:approve`. Vì vậy phải kết hợp **cycle validation** với **least-privilege audit**.

## 5. Ví dụ cấu hình Spring Security: hierarchy minh bạch

Với Spring Security 6.x/7.x, có thể tạo bean `RoleHierarchy` theo cú pháp chuỗi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
class RoleHierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_SUPPORT
                ROLE_SUPPORT > ROLE_VIEWER
                ROLE_VIEWER > order:read
                ROLE_PRIVACY_OFFICER > pii:export
                """);
    }
}
~~~

Đây là **class cấu hình trong dự án Spring Security**, không phải chương trình Java độc lập. Cú pháp text block hỗ trợ từ Java 15, nên Java 17 chạy được khi có dependencies Spring phù hợp.

Dữ liệu được diễn giải theo hướng **trái bao hàm phải**. Người được gán trực tiếp `ROLE_ADMIN` có thể đạt `ROLE_SUPPORT`, `ROLE_VIEWER` và `order:read`; không đạt `pii:export` từ hierarchy này.

### 5.1. Builder API

Với Spring Security 6.3+ có thể dùng builder, phù hợp khi chỉ có role mang tiền tố mặc định `ROLE_`:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withDefaultRolePrefix()
            .role("ADMIN").implies("SUPPORT")
            .role("SUPPORT").implies("VIEWER")
            .build();
}
~~~

Builder áp dụng prefix mặc định, nghĩa là `ADMIN` đại diện cho `ROLE_ADMIN` theo API này. Kiểm tra tài liệu đúng phiên bản trước khi dùng `withRolePrefix(...)` nếu hệ thống thay đổi tiền tố.

Khi một cạnh bao hàm **permission không phải role**, cú pháp chuỗi `RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > some:permission")` dễ mô tả hơn và được tài liệu Spring Security dùng trong ví dụ method authorization. Tuy nhiên điều đó cũng làm việc review **role → permission** càng quan trọng, vì một cạnh có thể trực tiếp cấp hành động nhạy cảm cho nhiều user.

### 5.2. ROLE_ và cách đọc `hasRole`/`hasAuthority`

Giả sử `Authentication` có `ROLE_ADMIN` và hierarchy có:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
~~~

- `hasRole("VIEWER")` thường tìm authority `ROLE_VIEWER` sau áp dụng hierarchy theo cấu hình.
- `hasAuthority("ROLE_VIEWER")` tìm chính chuỗi authority đó khi authorization manager/handler sử dụng hierarchy.
- `hasAuthority("order:read")` chỉ đúng nếu có authority đó trực tiếp hoặc được mở rộng qua một cạnh liên quan trong hierarchy **và** checker sử dụng hierarchy.
- `hasRole("ROLE_VIEWER")` có thể khác nhau giữa các API expression và manager; theo quy ước mặc định, ứng dụng thường truyền tên role **không có** tiền tố cho `hasRole`.

Không trộn tùy tiện `ROLE_VIEWER`, `VIEWER`, `SCOPE_read` và `order:read`. Định nghĩa namespace authority rõ ràng; thay đổi prefix giữa Spring versions/configurations phải có test.

### 5.3. Kích hoạt hierarchy đúng điểm kiểm tra

Spring Security hỗ trợ hierarchy cho nhiều cơ chế kiểm tra HTTP/method, nhưng cách cấu hình chi tiết phụ thuộc phiên bản.

Ví dụ khi ứng dụng dùng **pre/post method security expressions**, tài liệu Spring Security minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(roleHierarchy);
    return handler;
}
~~~

Đoạn trên là **snippet đặt trong configuration class**; để áp dụng method security cần có `@EnableMethodSecurity` và Spring-managed methods đi qua interceptor/proxy. Bean method security handler cần được công bố đủ sớm theo hướng dẫn của phiên bản đang dùng.

Với HTTP `authorizeHttpRequests` và các kiểu `AuthorizationManager` tùy chỉnh, cần xác minh **manager sử dụng bean RoleHierarchy hay không** trong chính Spring Security version đang chạy. Tài liệu Spring Security 7.x còn có `AuthorizationManagerFactory` để tùy biến role hierarchy, prefix và trust resolver. Không giả định “đã khai báo một bean RoleHierarchy nên mọi helper custom tự động sử dụng nó”.

## 6. Rủi ro khi dùng hierarchy cho mọi permission

Một số đội triển khai viết:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_USER
ROLE_USER > profile:read
ROLE_USER > orders:read
ROLE_SUPPORT > pii:export
ROLE_SUPPORT > refunds:approve
ROLE_ADMIN > users:manage
~~~

Đồ thị này **không cần có chu trình** để nguy hiểm:

- `ROLE_SUPPORT` có `pii:export` và `refunds:approve`.
- `ROLE_ADMIN` bao hàm `ROLE_SUPPORT` nên cũng có hai permission nhạy cảm đó.
- Một user có `ROLE_ADMIN` có thể được qua endpoint `hasAuthority("refunds:approve")` nếu manager áp dụng hierarchy, dù người thiết kế chỉ nghĩ admin làm “quản trị hệ thống”.
- Nếu controller/service thiếu ownership/tenant/approval policy, permission có thể bị sử dụng vượt phạm vi.

### 6.1. Một bảng so sánh “trước và sau”

Với đồ thị an toàn:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read
ROLE_PRIVACY_OFFICER > pii:export
~~~

| Direct role | order:read | pii:export | Ý nghĩa |
|---|---|---|---|
| `ROLE_VIEWER` | Có | Không | Chỉ đọc đơn |
| `ROLE_SUPPORT` | Có | Không | Kế thừa quyền xem |
| `ROLE_ADMIN` | Có | Không | Quản trị không tự có quyền xuất PII |
| `ROLE_PRIVACY_OFFICER` | Không từ hierarchy này | Có | Nhánh xử lý PII riêng |

Sau khi thêm `ROLE_SUPPORT > pii:export`:

| Direct role | order:read | pii:export | Thay đổi |
|---|---|---|---|
| `ROLE_VIEWER` | Có | Không | Không đổi |
| `ROLE_SUPPORT` | Có | **Có** | Mở quyền xuất PII |
| `ROLE_ADMIN` | Có | **Có** | **Mở quyền gián tiếp**, dễ bị bỏ sót |
| `ROLE_PRIVACY_OFFICER` | Không từ hierarchy này | Có | Không đổi |

Từ góc độ review, không chỉ hỏi “đã thêm cạnh nào?”, mà phải hỏi “**mọi role tổ tiên** của nguồn cạnh sẽ nhận thêm những quyền gì?”.

### 6.2. Phân quyền theo chức năng khác phân quyền trên từng bản ghi

Ngay cả khi quyền `order:read` được bao hàm có chủ đích, nó **không** cho phép một admin xem mọi đơn hàng của mọi tenant. Còn phải xét:

- Tenant membership và phạm vi tổ chức.
- Owner hoặc quan hệ chia sẻ.
- Trạng thái tài nguyên, quyền tạm khóa, thời hạn truy cập.
- Đối tượng là dữ liệu nhạy cảm/PII hay dữ liệu thông thường.
- Điều kiện workflow, ví dụ hai người phê duyệt.
- Các yêu cầu xác thực mạnh, step-up/MFA hoặc thiết bị đáng tin.

Hierarchy trả lời “chủ thể có authority hiệu lực nào”; policy tài nguyên trả lời “authority đó có áp dụng cho **resource này**, **action này**, **context này** không”.

## 7. Role quản trị không nên là “được làm tất cả”

Thiết kế `ROLE_SUPER_ADMIN > ROLE_EVERYTHING` có vẻ thuận tiện nhưng dễ làm **quyền quản trị hệ thống** tràn sang **quyền thao tác kinh doanh**.

Cân nhắc tách các nhánh:

~~~text
ROLE_SUPPORT_LEAD > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read

ROLE_FINANCE_APPROVER > payment:approve
ROLE_PRIVACY_OFFICER > pii:export
ROLE_INFRA_ADMIN > infra:configure
ROLE_USER_ADMIN > users:manage
~~~

Ở đây:

- Support lead có các quyền hỗ trợ thông thường.
- Finance approver có quyền phê duyệt thanh toán theo workflow.
- Privacy officer có khả năng xuất PII **khi thỏa điều kiện nghiệp vụ**.
- Infra admin quản lý hạ tầng nhưng không vì vậy trở thành finance approver.
- User admin quản lý tài khoản/role theo phạm vi được giao, không mặc nhiên đọc dữ liệu riêng tư.

Điều này làm hierarchy không phải một tháp vai trò duy nhất mà là **một đồ thị nhánh theo trách nhiệm**.

### 7.1. Separation of duties – tách nhiệm vụ quan trọng

Ví dụ quy trình hoàn tiền:

1. Nhân viên A tạo đề nghị hoàn tiền.
2. Nhân viên B, được ủy quyền, phê duyệt.
3. Hệ thống ngăn A phê duyệt đề nghị do chính mình tạo, kể cả A có role quản trị.
4. Giao dịch lớn có thể đòi hai người phê duyệt khác nhau.
5. Hành động được ghi audit và có thể yêu cầu xác thực tăng cường.

Chỉ có `hasAuthority("refund:approve")` chưa đủ cho điều kiện “người duyệt phải khác người tạo”. Điều kiện này thuộc **object/context-level policy**.

**Không giải quyết separation of duties chỉ bằng hierarchy**. Ngược lại, một hierarchy cấp `refund:create` và `refund:approve` cho cùng role rất dễ làm quy trình mất ranh giới độc lập.

### 7.2. Emergency/break-glass access

Trong một số hệ thống, quản trị viên khẩn cấp cần quyền đặc biệt. Thay vì nhét toàn bộ permission nhạy cảm vào `ROLE_ADMIN` thường trực, có thể dùng:

- Quy trình phê duyệt hoặc escalation riêng.
- Quyền tạm thời có thời hạn ngắn.
- Step-up authentication/MFA theo mức rủi ro.
- Scope hành động và tài nguyên bị giới hạn.
- Audit, cảnh báo và review sau sử dụng.
- Cơ chế tự hết hạn và thu hồi.

`ROLE_BREAK_GLASS` không tự an toàn chỉ vì đặt tên như vậy. Nếu đưa vào hierarchy theo hướng mọi admin đều bao hàm nó, toàn bộ thiết kế kiểm soát khẩn cấp bị phá vỡ.

## 8. Chu trình có thể biến role thấp thành role cao

Xem một cấu hình bị lỗi:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > ROLE_ADMIN
~~~

Nếu một authorization checker tính reachability trên đồ thị không ngăn chu trình, thì:

- Bắt đầu ở `ROLE_ADMIN`, đi đến `ROLE_SUPPORT` và `ROLE_VIEWER`.
- Bắt đầu ở `ROLE_VIEWER`, cũng có đường đi đến `ROLE_ADMIN`.
- Ý nghĩa role thấp/hạn chế bị mất: user được cấp viewer có thể đáp ứng kiểm tra “admin reachable”.

**Cảnh báo thực hành:** implementation/phiên bản Spring Security hiện tại có thể phát hiện chu trình trong lúc xây dựng hierarchy hoặc xử lý khác; không nên khẳng định mọi version đều sẽ chấp nhận và cấp quyền. Nhưng về mặt **thiết kế policy**, khai báo có chu trình phải bị coi là lỗi và pipeline phải chặn trước khi triển khai.

Nên viết validation riêng ở CI hoặc test startup để không phụ thuộc “phiên bản này may mắn từ chối”. Sau nâng cấp Spring Security, test lại behavior của các cấu hình lỗi; tuyệt đối không tắt test vì một version đã ném exception.

## 9. Cách phát hiện chu trình trong đồ thị

Một cách phổ biến là **depth-first search với ba trạng thái**:

| Trạng thái đỉnh | Nghĩa |
|---|---|
| 0 / chưa thăm | Chưa bắt đầu xử lý |
| 1 / đang thăm | Đang nằm trong nhánh DFS hiện tại |
| 2 / đã xử lý | Nhánh con đã hoàn thành an toàn |

Quy tắc:

1. Với từng đỉnh chưa thăm, đánh dấu đang thăm.
2. Đi theo các cạnh xuống đỉnh con.
3. Nếu gặp một đỉnh **đang thăm** (state 1), có một cạnh quay vào đường đang duyệt → **chu trình**.
4. Nếu gặp đỉnh đã xử lý (state 2), bỏ qua vì đã xác minh.
5. Duyệt xong các con, đánh dấu state 2.

Độ phức tạp với adjacency list là **O(V + E)** cho V đỉnh, E cạnh. Thuật toán **Kahn/topological sort** cũng phát hiện chu trình: nếu không thể xuất đủ V đỉnh trong thứ tự topo thì đồ thị có chu trình. Dùng một trong hai cách ở CI là đủ, miễn có test tự vòng, vòng hai chiều và vòng dài.

### 9.1. Không chỉ kiểm tra chu trình

Sau khi xác minh DAG, nên tính bao đóng bắc cầu (effective privileges) cho từng role được cấp trực tiếp và chạy thêm:

- **Forbidden reachability**: role nào tuyệt đối không được đạt permission nào?
- **Sensitive permission review**: có role nào bất ngờ đạt `payment:approve`, `pii:export` hoặc `users:grant-admin`?
- **Separation-of-duties review**: có role nào có cả quyền tạo và quyền duyệt hành động không?
- **Privilege delta**: so sánh quyền hiệu lực trước và sau pull request.
- **Orphan/missing rule**: role/permission chưa khai báo hoặc gõ sai có làm deny sai?
- **Path-independent coverage**: endpoint còn policy service/object-level không?

Một đồ thị không chu trình nhưng chứa `ROLE_EVERYONE > admin:grant` vẫn nguy hiểm. Vì vậy DAG chỉ là **điều kiện cần về cấu trúc**, không phải chứng minh toàn bộ chính sách đúng.

## 10. Java 17 độc lập: audit đồ thị, detect cycle và quyền mở quá rộng

Chương trình sau chạy bằng **Java chuẩn, không cần Spring**, giúp tự hiểu graph, transitive closure và một ca quyền nhạy cảm phát sinh ngoài dự kiến. Nó không phải mã nguồn `RoleHierarchyImpl` và **không thay thế** Spring integration test. Dùng `TreeMap`/`TreeSet` để output có thứ tự ổn định.

Tạo file `RoleGraphAuditDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class RoleGraphAuditDemo {
    static Map<String, Set<String>> graph(List<String> edges) {
        Map<String, Set<String>> result = new TreeMap<>();
        for (String edge : edges) {
            String[] parts = edge.split("\\s*>\\s*");
            if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
                throw new IllegalArgumentException("Invalid edge: " + edge);
            }
            result.computeIfAbsent(parts[0], key -> new TreeSet<>())
                    .add(parts[1]);
            result.computeIfAbsent(parts[1], key -> new TreeSet<>());
        }
        Map<String, Integer> state = new HashMap<>();
        for (String role : result.keySet()) {
            check(role, result, state);
        }
        return result;
    }

    static void check(String node, Map<String, Set<String>> edges,
                      Map<String, Integer> state) {
        if (state.getOrDefault(node, 0) == 1) {
            throw new IllegalArgumentException("Cycle at " + node);
        }
        if (state.getOrDefault(node, 0) == 2) {
            return;
        }
        state.put(node, 1);
        for (String next : edges.getOrDefault(node, Set.of())) {
            check(next, edges, state);
        }
        state.put(node, 2);
    }

    static Set<String> reachable(Map<String, Set<String>> graph, String start) {
        Set<String> found = new TreeSet<>();
        ArrayDeque<String> queue = new ArrayDeque<>();
        queue.add(start);
        while (!queue.isEmpty()) {
            String current = queue.removeFirst();
            if (found.add(current)) {
                queue.addAll(graph.getOrDefault(current, Set.of()));
            }
        }
        return found;
    }

    public static void main(String[] args) {
        List<String> safeEdges = List.of(
                "ROLE_ADMIN > ROLE_SUPPORT",
                "ROLE_SUPPORT > ROLE_VIEWER",
                "ROLE_VIEWER > order:read",
                "ROLE_PRIVACY_OFFICER > pii:export"
        );
        Map<String, Set<String>> safe = graph(safeEdges);
        System.out.println("SAFE admin: " + reachable(safe, "ROLE_ADMIN"));
        System.out.println("SAFE privacy: "
                + reachable(safe, "ROLE_PRIVACY_OFFICER"));
        System.out.println("SAFE admin may export PII: "
                + reachable(safe, "ROLE_ADMIN").contains("pii:export"));

        List<String> badEdges = new ArrayList<>(safeEdges);
        badEdges.add("ROLE_SUPPORT > pii:export");
        Map<String, Set<String>> bad = graph(badEdges);
        System.out.println("BAD admin may export PII: "
                + reachable(bad, "ROLE_ADMIN").contains("pii:export"));

        List<String> cyclicEdges = new ArrayList<>(safeEdges);
        cyclicEdges.add("ROLE_VIEWER > ROLE_ADMIN");
        try {
            graph(cyclicEdges);
            System.out.println("CYCLE unexpectedly accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("CYCLE blocked: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 RoleGraphAuditDemo.java
java RoleGraphAuditDemo
~~~

Output đã được kiểm thử:

~~~text
SAFE admin: [ROLE_ADMIN, ROLE_SUPPORT, ROLE_VIEWER, order:read]
SAFE privacy: [ROLE_PRIVACY_OFFICER, pii:export]
SAFE admin may export PII: false
BAD admin may export PII: true
CYCLE blocked: Cycle at ROLE_ADMIN
~~~

### Diễn giải output

- **SAFE admin:** có quyền cấp trực tiếp và các quyền reachable, không có `pii:export`.
- **SAFE privacy:** vai trò riêng có `pii:export`, không phải do kế thừa từ admin.
- **SAFE admin may export PII: false:** test âm tính chứng minh không có đường ngầm cấp quyền.
- **BAD admin may export PII: true:** chỉ thêm một cạnh `ROLE_SUPPORT > pii:export` đã đưa permission nhạy cảm lên cả role admin.
- **CYCLE blocked:** thêm cạnh `ROLE_VIEWER > ROLE_ADMIN` tạo chu trình; DFS phát hiện vì gặp lại đỉnh đang duyệt.

Đây là ví dụ mang tính giáo dục: parser của demo nhận danh sách cạnh do tác giả cung cấp và dùng `split` đơn giản. Khi áp dụng CI cho dữ liệu thật, phải xác định format cấu hình, loại bỏ giá trị không hợp lệ, xử lý case/prefix, trùng lặp và nguồn role/permission. Với đồ thị lớn và dữ liệu không tin, cân nhắc traversal lặp để tránh đệ quy quá sâu.

## 11. Kiểm thử bằng Spring Security: authority reachable thật

Sau khi test đồ thị thuần Java, cần một test dùng **Spring Security dependency thực tế**, để tránh suy đoán API version và semantics role prefix.

Ví dụ test JUnit 5 trong module có Spring Security:

~~~java
import java.util.Collection;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RoleHierarchyTest {
    private final RoleHierarchy hierarchy =
            RoleHierarchyImpl.fromHierarchy("""
                    ROLE_ADMIN > ROLE_SUPPORT
                    ROLE_SUPPORT > ROLE_VIEWER
                    ROLE_VIEWER > order:read
                    ROLE_PRIVACY_OFFICER > pii:export
                    """);

    private Set<String> effective(String role) {
        Collection<? extends GrantedAuthority> reached =
                hierarchy.getReachableGrantedAuthorities(
                        Set.of(new SimpleGrantedAuthority(role)));
        return reached.stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void adminInheritsReadButNotPiiExport() {
        assertTrue(effective("ROLE_ADMIN").contains("order:read"));
        assertTrue(effective("ROLE_ADMIN").contains("ROLE_VIEWER"));
        assertFalse(effective("ROLE_ADMIN").contains("pii:export"));
    }

    @Test
    void viewerDoesNotBecomeAdmin() {
        assertFalse(effective("ROLE_VIEWER").contains("ROLE_ADMIN"));
    }

    @Test
    void privacyOfficerHasItsOwnPermission() {
        assertTrue(effective("ROLE_PRIVACY_OFFICER")
                .contains("pii:export"));
        assertFalse(effective("ROLE_PRIVACY_OFFICER")
                .contains("ROLE_ADMIN"));
    }
}
~~~

Đoạn này là **test class phụ thuộc JUnit 5 và Spring Security**, không phải chương trình Java thuần. Kết quả mong đợi chỉ đúng nếu version thực cung cấp API như ví dụ. Nó chứng minh bao đóng bắc cầu theo Spring `RoleHierarchyImpl`, nhưng chưa chứng minh HTTP rule hoặc method interceptor trong runtime đã **sử dụng chính hierarchy đó**.

### 11.1. Integration test cho HTTP và method security

Ở tầng HTTP:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/orders/**").hasAuthority("order:read")
        .anyRequest().denyAll());
~~~

Khi cấu hình `RoleHierarchy` được gắn đúng vào authorization infrastructure, test phải xác minh một user chỉ có `ROLE_ADMIN` có thể qua rule `order:read` **nếu đó là hành vi thiết kế**, nhưng không thể qua rule `pii:export`. Ngoài ra, user chỉ có `ROLE_VIEWER` phải bị từ chối ở `/api/admin/**`.

Ở tầng method:

~~~java
@PreAuthorize("hasAuthority('order:read')")
public OrderDto read(long id) {
    return orderService.read(id);
}
~~~

Phải bật `@EnableMethodSecurity`, cấu hình expression handler/hierarchy phù hợp, gọi service qua Spring proxy/interceptor (không self-invocation) và kiểm tra quyền trên đối tượng. Không được suy ra annotation chắc chắn bảo vệ self-call trong cùng instance khi method security dùng proxy.

**Các test cần chạy qua security chain thật**, không chỉ test `getReachableGrantedAuthorities`. Đừng dùng một mock user với tất cả authorities rồi cho rằng hierarchy hoạt động; người dùng trong test nên có **chỉ role trực tiếp** để chứng minh quyền bắc cầu thực sự.

## 12. Test matrix: quyền không mong muốn là trọng tâm

| Test case | Direct authority | Policy hỏi | Kỳ vọng |
|---|---|---|---|
| Admin đọc đơn bình thường | `ROLE_ADMIN` | `order:read` | Cho phép ở tầng role nếu hierarchy đã cấu hình đúng |
| Viewer đọc đơn | `ROLE_VIEWER` | `order:read` | Cho phép ở tầng role |
| Viewer vào admin URL | `ROLE_VIEWER` | `ROLE_ADMIN` | Từ chối |
| Support vào admin URL | `ROLE_SUPPORT` | `ROLE_ADMIN` | Từ chối |
| Admin xuất dữ liệu PII | `ROLE_ADMIN` | `pii:export` | **Từ chối** trong mô hình an toàn |
| Privacy officer xuất PII | `ROLE_PRIVACY_OFFICER` | `pii:export` | Cho phép ở tầng authority, vẫn phải đáp ứng quy trình |
| Admin đọc đơn tenant khác | `ROLE_ADMIN` | Permission + object policy | Từ chối nếu không có tenant scope |
| Người tạo tự phê duyệt | Vai trò có `refund:approve` | Workflow separation-of-duties | Từ chối nếu policy cấm self-approve |
| Role giả mạo từ request | Header/body `ROLE_ADMIN` | Authentication | Không được tin |
| Hierarchy có chu trình | Bất kỳ | Build/CI validation | Từ chối cấu hình trước release |
| Thêm cạnh mở `pii:export` | `ROLE_ADMIN` | Effective-permission diff | Test regression phải thất bại |
| Session/JWT chưa cập nhật quyền | Authority cũ | Quyền nhạy cảm mới thu hồi | Phải phù hợp chiến lược revocation/freshness |

**Đừng chỉ test các ca allow**. Bảo vệ hiệu quả nhất trước privilege escalation là **test deny** ở mọi role không được phép, đặc biệt với những permission có rủi ro cao.

## 13. Áp dụng trong CI: audit thay đổi đồ thị như thay đổi API bảo mật

Một pipeline kiểm thử hierarchy nên làm theo thứ tự:

~~~text
Đọc danh sách cạnh ROLE/permission từ cấu hình
    |
    v
Kiểm tra cú pháp, prefix, tên role hợp lệ
    |
    v
Xây đồ thị có hướng
    |
    +--> Phát hiện self-loop / cycle --> FAIL BUILD
    |
    v
Tính reachable authorities cho các direct roles
    |
    +--> So sánh forbidden permissions --> FAIL BUILD
    |
    +--> So sánh separation-of-duties --> REVIEW/FAIL
    |
    +--> So sánh trước/sau PR --> REPORT DELTA
    |
    v
Chạy Spring Security unit + HTTP/method integration tests
    |
    v
Security review với người sở hữu nghiệp vụ
    |
    v
Triển khai, audit runtime và cảnh báo thay đổi quyền
~~~

### 13.1. Quyền hiệu lực thay đổi như thế nào?

Đối với mỗi role `R`, tính:

~~~text
effective_before(R)
effective_after(R)

newly_granted(R) = effective_after(R) - effective_before(R)
removed(R)       = effective_before(R) - effective_after(R)
~~~

Ví dụ một thay đổi thêm `ROLE_SUPPORT > pii:export`:

~~~text
newly_granted(ROLE_SUPPORT) = {pii:export}
newly_granted(ROLE_ADMIN)   = {pii:export}
newly_granted(ROLE_VIEWER)  = {}
~~~

Điểm then chốt: **review phải thấy cả role tổ tiên** được mở quyền. Nếu tool chỉ in cạnh trực tiếp vừa thêm, người review dễ đánh giá thấp phạm vi tác động.

### 13.2. Danh sách permission nhạy cảm

Có thể tạo một allowlist/denylist tường minh theo chính sách:

~~~text
ROLE_ADMIN:
  FORBID pii:export
  FORBID refund:self_approve

ROLE_SUPPORT:
  FORBID user:grant_admin
  FORBID payment:approve

ROLE_VIEWER:
  FORBID write:orders
  FORBID pii:export
  FORBID infra:configure
~~~

Đây là **minh họa policy**, không phải cú pháp chuẩn Spring Security. Permission thực tế phải được thống nhất giữa các nhóm bảo mật và nghiệp vụ. Không nên xây một blacklist nhỏ rồi coi mọi quyền khác đều an toàn: vẫn cần mô hình **allowlist quyền được phép** và review thay đổi.

### 13.3. Phê duyệt thay đổi đặc quyền

Những thay đổi tạo cạnh đến `users:grant_admin`, `pii:export`, `payment:approve` hoặc `infra:configure` nên yêu cầu review riêng, thậm chí hai người phê duyệt theo chính sách tổ chức. Audit cần lưu ai đề xuất, ai duyệt, tập role bị ảnh hưởng và kết quả test.

Một lỗi “typo” trong file hierarchy có thể là thay đổi cấp quyền nguy hiểm ngang với sửa annotation `@PreAuthorize`. Code review không nên coi hierarchy chỉ là metadata giao diện.

## 14. Những ràng buộc không biểu diễn tốt bằng role hierarchy

Hierarchy hữu ích cho quan hệ quyền **tĩnh và toàn cục**; nó không đủ cho các điều kiện động:

| Điều kiện | Vì sao hierarchy không đủ | Cách xử lý |
|---|---|---|
| User thuộc tenant A không được đọc tenant B | Role không mang ràng buộc tài nguyên cụ thể | Service policy, tenant-scoped query |
| Người tạo không được tự duyệt | Phụ thuộc chủ thể và người tạo của bản ghi | Separation-of-duties policy |
| Chỉ phê duyệt dưới một hạn mức tiền | Phụ thuộc giá trị giao dịch | Contextual authorization |
| Quyền chỉ có hiệu lực trong ca trực | Phụ thuộc thời gian / lịch trực | Policy động, thời hạn ủy quyền |
| Chỉ admin đã MFA được thao tác nguy hiểm | Phụ thuộc authentication assurance | Step-up/MFA policy |
| User bị khóa sau khi login | Trạng thái account có thể đã thay đổi | Session/token revocation, real-time check |
| Không được xem PII trừ mục đích cụ thể | Phụ thuộc mục đích truy cập/audit | Purpose-bound authorization, workflow |
| Cần hai người đồng ý | Phụ thuộc sự kiện và actor khác nhau | Transaction workflow / approval service |

Có thể kết hợp role/permission với `@PreAuthorize` hoặc custom `AuthorizationManager` nhưng logic theo tài nguyên nên gần service/use-case boundary. Đừng cố biến hàng nghìn object IDs thành hàng nghìn role/authority trong hierarchy.

### 14.1. Nếu hệ thống cần ABAC hoặc ReBAC

Khi chính sách phụ thuộc attribute của chủ thể, tài nguyên, context hoặc mối quan hệ, cân nhắc **ABAC (Attribute-Based Access Control)** hay **ReBAC (Relationship-Based Access Control)** kết hợp RBAC.

Ví dụ:

~~~text
allow read(order) nếu:
  actor authenticated
  AND actor có order:read
  AND actor.tenantId == order.tenantId
  AND (actor là owner OR actor được share OR actor có quyền đặc biệt theo tenant)
~~~

Hierarchy có thể cung cấp `order:read`, nhưng hai điều kiện tenant và quan hệ vẫn phải kiểm tra. Một admin hệ thống không nên tự động bỏ qua mọi điều kiện nếu không có yêu cầu được phê duyệt và audit.

## 15. Vai trò quản trị vượt dự kiến: các đường leo thang khác

Ngay cả khi DAG không cấp thẳng quyền nhạy cảm, quản trị viên có thể **gián tiếp** giành quyền nếu nó có quyền quản lý tài khoản, role, cấu hình hoặc credential quá rộng.

Ví dụ:

- `ROLE_ADMIN > users:grant_role`: admin có thể tự gán `ROLE_FINANCE_APPROVER` nếu service không chặn self-grant.
- `ROLE_ADMIN > policies:edit`: admin có thể chỉnh rule phân quyền để thêm quyền cho bản thân.
- `ROLE_ADMIN > token:mint`: có thể tạo token mang scope cao nếu issuance policy không khóa.
- `ROLE_ADMIN > audit:disable`: có thể tắt dấu vết của một hành động nhạy cảm.
- `ROLE_ADMIN > backup:download`: gián tiếp đọc toàn bộ dữ liệu/PII qua bản sao lưu.
- `ROLE_ADMIN > users:impersonate`: có thể hành động dưới principal của người khác nếu thiếu kiểm soát.

Vì vậy **effective privilege audit** phải xem xét cả **quyền dẫn tới khả năng cấp thêm quyền**, không chỉ permission “đọc/ghi” trực tiếp. Đôi khi một quyền quản trị cấu hình có khả năng thực tế mạnh hơn quyền xuất PII.

### 15.1. Guardrail cho grant/impersonation

Một số ràng buộc đáng xem xét:

1. Người được cấp quyền quản lý user **không được tự tăng quyền** nếu không có quy trình độc lập.
2. Không thể cấp một role cao hơn phạm vi ủy quyền của mình.
3. Cấp quyền cao cần xác thực mạnh và audit.
4. Quyền impersonation có scope/expiry, hiển thị rõ actor gốc và subject được impersonate.
5. Không cho phép thay đổi policy/audit hoặc tắt logging một cách im lặng.
6. Kiểm tra quyền ở **service** ngay cả khi UI ẩn nút quản trị.
7. Không để gateway/header tự xưng role thay thế authentication.
8. Tài khoản break-glass được giới hạn, giám sát và thu hồi theo quy trình.

Những guardrail này thuộc nghiệp vụ và hạ tầng, không tự xuất hiện khi thêm `ROLE_ADMIN` vào hierarchy.

## 16. Runtime freshness: authority hiệu lực có thể đã cũ

Một hệ thống có session hoặc JWT:

~~~text
09:00  Lan đăng nhập; authentication chứa ROLE_ADMIN.
09:05  Cấu hình hierarchy được thay đổi để ROLE_ADMIN bao hàm quyền mới.
09:07  Request dùng authentication ROLE_ADMIN cũ.
~~~

Tùy nơi hierarchy được áp dụng và thời điểm nạp cấu hình, request có thể nhìn thấy quyền mới dù token/session không thay đổi, vì **quan hệ bao hàm mới** được dùng tại lúc authorization. Ngược lại, nếu hệ thống materialize authorities vào token khi phát hành, token cũ có thể vẫn giữ quyền cũ cho tới lúc làm mới.

Điều này nhấn mạnh **thay đổi hierarchy là thay đổi authorization ở runtime**, không chỉ thay đổi dữ liệu user.

Khi thu hồi một quyền:

- Kiểm tra hierarchy mới có thật sự loại được đường reachable đến permission đó không.
- Kiểm tra user có được cấp permission trực tiếp ngoài hierarchy không.
- Kiểm tra session/token, role cache, method security cache và AuthorizationManager liên quan.
- Thiết kế token expiry, revocation hoặc permission source cập nhật khi quyền nhạy cảm cần hiệu lực nhanh.
- Kiểm tra mọi service cùng phiên bản policy, đặc biệt hệ thống nhiều microservices.

**Không đồng nhất** “đã sửa role trong database” với “mọi request hiện tại đều mất quyền ngay”. Cơ chế lưu authentication và nơi áp dụng hierarchy quyết định độ mới của quyền.

## 17. Dấu hiệu cấu hình có vấn đề

| Dấu hiệu | Vì sao đáng lo | Cách sửa |
|---|---|---|
| Có `ROLE_A > ROLE_A` | Self-cycle, ngữ nghĩa vô lý | Chặn từ CI |
| Có `ADMIN > USER > ADMIN` | Cycle làm role thấp chạm role cao | Detect cycles, thiết kế lại |
| Một role bao hàm hàng chục permission nhạy cảm khác nhóm nghiệp vụ | Privilege creep | Tách nhánh role, cấp permission hẹp |
| `ROLE_ADMIN > ROLE_FINANCE_APPROVER` mà không có nhu cầu | Admin có khả năng duyệt tiền | Bỏ cạnh, áp policy riêng |
| `ROLE_USER > pii:export` | Quyền xuất PII mở cho số lượng lớn user | Review cấp quyền và hạn chế |
| Role cao kế thừa mọi role thấp | SoD có thể bị phá | Phân nhóm theo trách nhiệm |
| Chỉ test admin được phép mọi thứ | Không phát hiện role thấp leo thang | Test deny cho viewer/support |
| Dùng một quyền `users:manage` cho mọi thao tác user | Có thể tự grant admin | Tách `users:view`, `users:update`, `roles:grant`, self-grant policy |
| Cho phép gán role qua header client | Giả mạo quyền | Authentication từ nguồn tin cậy |
| Có hierarchy bean nhưng method check không dùng nó | Behavior không như kỳ vọng | Test manager/handler integration |
| Không xem effective permissions khi sửa cạnh | Bỏ sót quyền bắc cầu | Diff reachable cho mọi role |
| Auth JWT/session không được refresh khi thu hồi | Quyền còn tồn tại ngoài ý muốn | Revocation/freshness strategy |
| Chỉ check role, không check tenant/owner | BOLA/IDOR | Policy theo resource |
| Đưa mọi permission vào hierarchy thay cho object authorization | Policy quá tĩnh | ABAC/ReBAC/workflow |

## 18. Hướng dẫn review một pull request thêm cạnh

Giả sử PR có diff:

~~~diff
 ROLE_ADMIN > ROLE_SUPPORT
 ROLE_SUPPORT > ROLE_VIEWER
+ROLE_SUPPORT > pii:export
~~~

Người review nên yêu cầu câu trả lời:

**A. Lý do nghiệp vụ:** Vì sao **mọi** support cần `pii:export`? Có quy định pháp lý/tuân thủ liên quan dữ liệu riêng tư?

**B. Các vai trò tổ tiên:** Có những role nào bao hàm `ROLE_SUPPORT` trực tiếp hoặc gián tiếp? Role admin, supervisor, temporary role, service accounts có nằm trong đó không?

**C. Permission delta:** Tập quyền mới của từng role là gì? Có thêm quyền nhạy cảm cho người không dự kiến không?

**D. Quyền ở đối tượng:** Permission đó có cho phép xuất PII của mọi tenant hoặc cần purpose, scope, thời hạn, owner approval?

**E. Separation of duties:** Người có role đó có thể vừa cấp quyền, vừa phê duyệt, vừa thực thi xuất dữ liệu mà không có review độc lập không?

**F. Kiểm thử:** Có negative tests cho admin thường, support thường và viewer? Có cycle test? Có integration test với phiên bản Spring Security thật?

**G. Quan sát:** Audit, cảnh báo sử dụng permission mới và khả năng rollback có đủ không?

Một PR được chấp nhận **không chỉ vì build không báo lỗi cycle**. Nó cần chứng minh thay đổi quyền có chủ đích và theo nguyên tắc quyền tối thiểu.

## 19. Checklist bắt buộc trước khi phát hành

- [ ] Mọi cạnh `A > B` có ý nghĩa “A bao hàm B” được thống nhất trong mô hình.
- [ ] Tên authority/prefix `ROLE_`/permission chính xác; không trùng tên mơ hồ.
- [ ] Đồ thị không có self-loop, chu trình hai chiều hay chu trình dài.
- [ ] Có công cụ CI tính bao đóng bắc cầu cho mỗi role trực tiếp.
- [ ] Có báo cáo quyền **mới được cấp** cho từng role sau thay đổi.
- [ ] Những permission nhạy cảm có allowlist/negative test riêng.
- [ ] Admin hạ tầng không mặc nhiên là approver, auditor hay privacy officer.
- [ ] Tài khoản có quyền grant/impersonation được kiểm soát chống self-escalation.
- [ ] Những action cần hai người phê duyệt có service/workflow policy riêng.
- [ ] Tenant/owner/relationship policy được kiểm tra ở tầng dữ liệu.
- [ ] Các cơ chế HTTP/method đang dùng cùng hierarchy đúng phiên bản.
- [ ] Test direct role và derived role; tránh test user được cấp sẵn tất cả authorities.
- [ ] Test anonymous và role thấp không được vào endpoint admin.
- [ ] Test admin không thể sử dụng `pii:export` nếu đó không thuộc quyền admin.
- [ ] Chính sách JWT/session/cache và thu hồi quyền được xác minh.
- [ ] Có audit, monitoring và rollback khi hierarchy thay đổi.

**Nguyên tắc ngắn:** *Không chu trình, không quyền ngầm quá rộng, không admin toàn năng mặc định, và luôn kiểm tra quyền trên tài nguyên thật.*

## 20. Câu hỏi tự kiểm tra

**1. `ROLE_ADMIN > ROLE_SUPPORT` có nghĩa support được quyền admin không?**  
Không. Hướng `>` là admin bao hàm support, không phải chiều ngược lại.

**2. Nếu thêm `ROLE_SUPPORT > pii:export`, admin có thể được cấp permission đó không?**  
Có, nếu admin bao hàm support và checker sử dụng hierarchy; quyền được truyền theo bắc cầu.

**3. Đồ thị không có chu trình có bảo đảm an toàn chưa?**  
Chưa. Một DAG vẫn có thể cấp `payment:approve` cho role không đúng nghiệp vụ.

**4. Vì sao `ROLE_VIEWER > ROLE_ADMIN` trong hierarchy trên phải bị chặn?**  
Nó tạo chu trình khiến viewer có thể đạt tới role admin trong mô hình reachable, phá vỡ nguyên tắc phân cấp.

**5. Kiểm tra chu trình nên làm ở đâu?**  
Trong CI/startup validation bằng DFS/Kahn cùng test cấu hình; không chỉ đợi request đầu tiên phát hiện lỗi.

**6. Vì sao role admin không nên bao hàm tất cả quyền?**  
Vì quản trị cấu hình khác phê duyệt tiền, xử lý PII, audit và nhiệm vụ có tách trách nhiệm.

**7. Có `order:read` nghĩa là có thể xem mọi đơn hàng của mọi tenant?**  
Không. Service phải kiểm tra quyền trên từng resource, owner và tenant.

**8. Chỉ kiểm tra `authentication.getAuthorities()` có chắc thấy quyền do hierarchy mở rộng không?**  
Không. Tập authorities trực tiếp và tập reachable khác nhau; checker phải dùng hierarchy đúng cách.

**9. Có cần test user chỉ được cấp `ROLE_VIEWER` không?**  
Có. Test âm tính viewer không đạt admin là cách phát hiện hướng cạnh sai hoặc chu trình.

**10. Thay đổi hierarchy có thể ảnh hưởng quyền của session/JWT hiện có không?**  
Có thể, tùy hierarchy được áp dụng ở thời điểm authorization hay authorities được materialize sẵn. Cần test freshness và revocation.

## 21. Tài liệu tham khảo chính thức

- Spring Security – **Authorization Architecture**, phần *Hierarchical Roles* và integration với HTTP/method authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **RoleHierarchyImpl JavaDoc**, `fromHierarchy`, `withDefaultRolePrefix`, `getReachableGrantedAuthorities`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security – **RoleHierarchy JavaDoc**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchy.html
- Spring Security – **Method Security**, đặc biệt role hierarchy và permission expressions: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Servlet Authentication Architecture**, `GrantedAuthority`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
