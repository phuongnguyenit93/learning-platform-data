# Tenant identity resolution: xác định tenant trước khi xử lý nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **Tenant Isolation** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **tenant identity resolution** là quá trình xác định tenant mà một request hoặc công việc đang yêu cầu thao tác, rồi kiểm chứng rằng nguồn gọi được phép hoạt động trong ngữ cảnh đó.

Tenant có thể là một tổ chức, cửa hàng hoặc đơn vị khách hàng dùng chung nền tảng. Nếu xác định sai tenant, một phép kiểm tra nghiệp vụ tưởng như hợp lệ có thể chạy trên dữ liệu, quyền hoặc hạn mức của tổ chức khác.

Ví dụ, một nhân viên có quyền duyệt hoàn tiền ở tenant A không được sử dụng quyền đó để duyệt refund của tenant B chỉ bằng cách đổi đường dẫn hoặc header.

Sau bài học, bạn có thể:

- Phân biệt tenant selector, tenant đã được nhận diện và tenant context đã được kiểm chứng.
- Xác định nguồn nào được cung cấp gợi ý tenant và nguồn nào có thẩm quyền ràng buộc tenant.
- Giải quyết rõ trường hợp host, path, token hoặc message không thống nhất.
- Tạo ngữ cảnh tenant bất biến cho từng lần thực thi và giữ đúng ngữ cảnh qua các lớp.
- Ngăn nhầm tenant trong thread pool, kết nối cơ sở dữ liệu, cache, worker và retry.
- Kiểm thử các tình huống giả tenant, thiếu tenant hoặc kế thừa ngữ cảnh cũ.

## 2. Ba câu hỏi thường bị gộp thành một

| Câu hỏi | Ví dụ | Điều còn phải kiểm tra |
|---|---|---|
| Caller đang chọn tenant nào? | Path chứa tenant-b | Caller có được chọn tenant-b không |
| Định danh đó ánh xạ tới tenant nội bộ nào? | Slug beta ánh xạ tới tenant-id-42 | Ánh xạ có hợp lệ, tenant còn hoạt động không |
| Caller được hoạt động trong tenant đó không? | Membership của caller ở tenant-id-42 đang active | Có quyền thực hiện action trên đối tượng cụ thể không |

Một giá trị xuất hiện trong URL, subdomain hay body mới là dữ liệu đầu vào. Nó chưa phải quyền hoạt động trong tenant.

Ngược lại, xác định được tenant hợp lệ và có membership vẫn chưa cho phép mọi hành động. Sau đó còn phải kiểm tra quyền theo action, object scope, trạng thái, hạn mức và các bất biến nghiệp vụ.

### 2.1. Tenant selector

Selector là cách chỉ ra tenant mong muốn, ví dụ:

~~~text
/tenants/acme/refunds
acme.example.test
X-Requested-Tenant: acme
tenantId trong một command
~~~

Tùy hợp đồng endpoint, một số selector được chấp nhận, số khác bị từ chối hoặc không được dùng để định tuyến.

Người dùng có nhiều membership có thể hợp lệ khi chủ động chọn tenant khác. Vấn đề bảo mật nằm ở việc server kiểm chứng lựa chọn đó, không phải ở việc mọi selector do client gửi đều bị cấm.

### 2.2. Định danh tenant chuẩn

Hệ thống nên ánh xạ selector về một định danh nội bộ ổn định:

~~~text
tenant slug / custom domain / external organization reference
    → bản ghi tenant có thẩm quyền
    → canonical tenantId
~~~

Tên hiển thị hoặc slug có thể đổi. Định danh nội bộ và các quan hệ nghiệp vụ cần giữ được ý nghĩa qua việc đổi tên.

Không tự suy ra tenant chỉ bằng cách so tên công ty, miền email hoặc cắt một đoạn chuỗi từ objectId.

### 2.3. Tenant context đã được kiểm chứng

Một context có thể chứa:

~~~text
canonical tenantId
principal đang được xác thực
nguồn ràng buộc/chọn tenant
membership hoặc thẩm quyền dịch vụ được dùng
phiên bản/hiệu lực liên quan
requestId hoặc operationId phục vụ liên kết
~~~

Context này được tạo bởi luồng tin cậy, không phải đối tượng bind trực tiếp từ JSON.

Nên có một điểm rõ ràng chuyển từ dữ liệu “tenant được yêu cầu” sang “tenant được phép dùng”. Các lớp xử lý nghiệp vụ nhận context đã kiểm chứng và không tự diễn giải lại header.

## 3. Mối đe dọa khi xác định tenant sai

| Lỗi | Hệ quả nghiệp vụ có thể xảy ra |
|---|---|
| Tin tenantId từ body | Ghi đối tượng hoặc giữ chỗ trong tenant khác |
| Dùng role của tenant A sau khi path đổi sang B | Duyệt, sửa giá hoặc cấp quyền sai tổ chức |
| Không kiểm tra nguồn tenant mâu thuẫn | Các lớp dùng tenant khác nhau cho policy và dữ liệu |
| Thiếu tenant thì dùng tenant mặc định | Request lỗi được xử lý vào một tổ chức ngoài ý định |
| Context cũ còn trong thread pool | Request của B dùng dữ liệu hoặc quyền của A |
| Kết nối DB giữ schema/session tenant của lần trước | Truy vấn chạy trong không gian dữ liệu sai |
| Cache tenant mapping hoặc membership cũ | Alias, domain hoặc quyền đã đổi nhưng tiếp tục áp dụng |
| Worker tin tenant trong message không xác minh | Công việc tác động tới dữ liệu ngoài thẩm quyền |
| Chỉ scope bảng chính, bỏ scope đối tượng liên quan | Refund thuộc A trỏ payment hoặc người nhận thuộc B |

Những lỗi này có thể không tạo exception. Dữ liệu vẫn hợp lệ về kiểu và trạng thái nhưng bị xử lý dưới sai biên tổ chức.

## 4. Xác định hợp đồng nguồn tenant cho từng loại endpoint

Không nên để mỗi controller tùy ý thử các nguồn theo kiểu:

~~~text
Nếu header có tenant thì dùng header,
không có thì dùng path,
không có thì lấy token,
không có nữa thì lấy tenant đầu tiên của user.
~~~

Thứ tự fallback như vậy có thể làm dữ liệu do caller kiểm soát ghi đè một ràng buộc có thẩm quyền.

Thay vào đó, cần quy định loại nguồn và ý nghĩa của chúng.

| Nguồn | Vai trò có thể có | Kiểm chứng cần thiết |
|---|---|---|
| Path hoặc query | Selector tenant caller muốn dùng | Ánh xạ và kiểm tra quyền hoạt động |
| Host/subdomain | Selector hoặc ràng buộc của route | Host được hỗ trợ, mapping có thẩm quyền; vẫn cần quyền caller |
| Claim đã xác minh | Có thể ràng buộc tenant theo hợp đồng token | Ý nghĩa claim, issuer, mục đích sử dụng và mapping phù hợp |
| Session server | Tenant đang chọn hoặc một ràng buộc phiên | Session tin cậy và quyền còn hiệu lực |
| Header từ gateway | Ngữ cảnh được gateway xác nhận | Nguồn gateway được xác thực, ngăn caller tự chèn |
| Body | Dữ liệu nghiệp vụ hoặc selector theo thiết kế | Không tự trở thành thẩm quyền tenant |
| Message/job | Tenant mục tiêu đã lưu | Nguồn message, quyền producer, binding operation |
| Registry nhà cung cấp | Mapping tài khoản tích hợp tới tenant | Xác thực nguồn sự kiện và mapping duy nhất phù hợp |

### 4.1. Tenant trong token phải có ngữ nghĩa cụ thể

Một claim về tổ chức có thể biểu thị:

- Tenant ứng dụng mà token được phép dùng.
- Tổ chức gốc của danh tính.
- Tenant đang chọn trong một phiên đa tổ chức.
- Một định danh tổ chức của nhà cung cấp danh tính cần mapping.

Các nghĩa này không tương đương.

Ví dụ, home organization của người dùng không nhất thiết là tenant ứng dụng duy nhất mà họ được tham gia. Server phải hiểu đúng hợp đồng nguồn danh tính và ánh xạ về tenant nội bộ.

Không chỉ đọc một claim có tên trông giống tenant rồi dùng như canonical tenantId của ứng dụng.

### 4.2. Selector khác ràng buộc

Giả sử token được thiết kế để chỉ hoạt động trong tenant A. Caller chọn B trong path. Đây là mâu thuẫn với ràng buộc của token và phải bị chặn theo hợp đồng.

Nếu token chỉ xác định danh tính, còn caller có membership A và B, path B có thể là lựa chọn hợp lệ sau khi server kiểm chứng membership B.

Vì vậy, quy tắc không phải là “mọi trường có chữ tenant phải bằng nhau”. Cần phân loại rõ trường nào ràng buộc tenant, trường nào chọn tenant và trường nào chỉ mô tả nguồn gốc danh tính.

### 4.3. Không có tenant cũng là một trạng thái cần đặc tả

Một số endpoint như đăng nhập, liệt kê các tổ chức caller được tham gia hoặc quản trị nền tảng có thể không dùng cùng hợp đồng tenant như endpoint nghiệp vụ.

Hãy mô hình hóa chúng riêng. Không dùng tenantId=null để khiến repository nghiệp vụ bỏ điều kiện tenant và truy vấn mọi dữ liệu.

Với endpoint bắt buộc có tenant, thiếu hoặc không giải quyết được tenant phải kết thúc xử lý trước hiệu ứng nghiệp vụ.

## 5. Một pipeline xác định tenant có kiểm chứng

Một luồng cho endpoint nghiệp vụ có thể gồm:

~~~text
Hợp đồng route do server xác định
    → xác thực caller
    → đọc các nguồn tenant được hợp đồng cho phép
    → chuẩn hóa và ánh xạ về canonical tenantId
    → kiểm tra các ràng buộc có thẩm quyền không mâu thuẫn
    → kiểm tra tenant được phép nhận loại thao tác này
    → kiểm tra membership hoặc thẩm quyền dịch vụ
    → tạo TenantContext đã kiểm chứng
    → kiểm tra quyền action/object và thực hiện nghiệp vụ
~~~

### 5.1. Chọn hợp đồng trước, không để input chọn chế độ tin cậy

Ví dụ server có thể định nghĩa:

~~~text
TenantPathApi:
  selector chính là path
  token bound-tenant, nếu có, phải khớp
  header tenant từ Internet không được ghi đè

TenantHostApi:
  host ánh xạ tenant qua registry
  selector bổ sung, nếu được hỗ trợ, phải nhất quán

InternalJobApi:
  principal dịch vụ được xác thực
  tenant và operation được ràng buộc qua job/ủy nhiệm tin cậy
~~~

Client không được gửi mode=internal để khiến request đi vào một nhánh tin cậy cao hơn.

### 5.2. Không fallback sau một selector không hợp lệ

Nếu path chứa tenant không tồn tại, không được âm thầm chuyển sang tenant trong session hoặc tenant đầu tiên trong danh sách membership.

Tương tự, nếu token bound-tenant mâu thuẫn với path, không chọn nguồn “ưu tiên cao hơn” rồi bỏ qua mâu thuẫn. Request phải đáp ứng hợp đồng nhất quán trước khi tiếp tục.

Fallback chỉ được dùng nếu chính sách route định nghĩa rõ trường hợp thiếu nguồn và nguồn thay thế có ý nghĩa tương ứng. Nó không phải cách phục hồi từ input bị sai hoặc có dấu hiệu giả mạo.

### 5.3. So sánh canonical tenantId

Host có thể dùng custom domain, path dùng slug, còn token dùng một external organization reference. Không so sánh trực tiếp ba chuỗi khác định dạng.

Ánh xạ từng nguồn được chấp nhận theo đúng namespace của nó, rồi kiểm tra quan hệ giữa các canonical tenantId.

Nếu slug được đổi tên hoặc domain được thu hồi, mapping cũ không được tiếp tục cấp quyền ngoài thời hạn/chính sách đã định.

### 5.4. Registry và membership là dữ liệu nền để giải quyết tenant

Một số dữ liệu control plane phải được đọc trước khi có tenant context đầy đủ, như mapping domain → tenant hoặc membership của principal đã xác thực.

Điều đó không có nghĩa mọi repository nghiệp vụ được chạy ở chế độ toàn nền tảng. Giới hạn các lookup nền này theo mục đích, dữ liệu và quyền cần thiết.

Nếu endpoint chỉ có resourceId, cần lookup được giới hạn hoặc phép join với các tenant caller được phép dùng. Không nạp toàn bộ entity nhạy cảm trên toàn nền tảng, trả thông tin ra ngoài, rồi mới suy ra tenant để kiểm tra.

## 6. Java minh họa bước resolution

Mã dưới đây dùng interface giả định và không phải chương trình độc lập.

Đầu vào principal đã qua xác thực; contract đến từ cấu hình route phía server. EdgeEvidence chỉ có giá trị khi nguồn gateway và thông tin đính kèm đã được xác minh theo giao thức triển khai.

~~~java
TenantContext resolveTenant(
        VerifiedPrincipal principal,
        RequestMetadata request,
        RouteTenantContract contract,
        VerifiedEdgeEvidence edgeEvidence) {

    var selection = selectors.readAccordingTo(
            contract, request, edgeEvidence);

    var tenant = tenantRegistry.requireUniqueCanonical(
            selection.namespace(), selection.value());

    bindings.requireConsistent(
            principal.tenantBindings(),
            selection,
            tenant.id(),
            contract);

    tenantStatus.requireOperationAllowed(
            tenant, contract.operationClass());

    var authority = tenantAccess.requireAuthority(
            principal,
            tenant.id(),
            contract.entryPointKind());

    return tenantContexts.verified(
            tenant.id(),
            principal.id(),
            selection.provenance(),
            authority.reference(),
            authority.version(),
            clock.instant());
}
~~~

Các helper cần thực hiện đúng hợp đồng:

- selectors không tin mọi header có tên liên quan tenant.
- tenantRegistry không chọn một tenant bất kỳ khi mapping không duy nhất.
- bindings phân biệt claim ràng buộc tenant với thuộc tính chỉ mô tả tổ chức gốc.
- tenantStatus chặn những thao tác không được phép trong trạng thái tenant hiện tại.
- tenantAccess dùng membership hoặc thẩm quyền dịch vụ đúng loại caller, không chỉ so email domain.
- tenantContexts tạo kiểu context nội bộ không được bind trực tiếp từ payload.

Ví dụ không coi constructor riêng tư hoặc tên kiểu Verified là biện pháp xác thực đầy đủ. Giá trị phải thực sự được tạo qua đường kiểm chứng được kiểm soát.

Nếu nguồn membership hoặc registry không đủ tin cậy/không truy cập được, không tạo context hợp lệ bằng dữ liệu mặc định. Tùy hợp đồng, trả lỗi tạm thời hoặc chặn thao tác.

### 6.1. Những gì resolver chưa cho phép

Resolver xác nhận ngữ cảnh tenant. Command handler vẫn phải kiểm tra:

~~~text
actor được thực hiện action nào
đối tượng có thuộc canonical tenantId này không
scope nội bộ của actor trong tenant
trạng thái, revision và hạn mức
phân tách nhiệm vụ nếu có
idempotency và các bất biến khi ghi
~~~

Một người active trong tenant A vẫn có thể chỉ được xem branch-a và không được approve.

### 6.2. Tenant bị khóa hoặc đang kết thúc sử dụng

Chính sách cần nói rõ các loại thao tác còn được phép, như chỉ đọc phục vụ xuất dữ liệu, đối soát nghĩa vụ đã phát sinh hoặc quản trị việc đóng tenant.

Không tạo một fallback cho phép toàn bộ nghiệp vụ khi tenant không còn active. Ngược lại, không bỏ qua việc ghi nhận một kết quả tài chính đã xảy ra chỉ vì luồng nghiệp vụ mới đã bị khóa; xử lý đó cần thẩm quyền và hành động riêng.

## 7. Xử lý mâu thuẫn giữa các nguồn

Bảng sau giả định các nguồn đã được phân loại theo hợp đồng, không phải mọi trường chứa tenant đều có cùng ý nghĩa.

| Tình huống | Kết quả phù hợp |
|---|---|
| Token chỉ được dùng ở A, path chọn B | Chặn do mâu thuẫn ràng buộc |
| Token chỉ định danh user, user có membership B, path chọn B | Có thể tạo context B nếu các điều kiện khác hợp lệ |
| Host ánh xạ A, path cũng ánh xạ A qua slug khác | Có thể hợp lệ sau chuẩn hóa canonical ID |
| Host ràng buộc A, path chọn B | Chặn theo hợp đồng host-bound |
| API host trung tính, path chọn B | Kiểm tra B theo hợp đồng path-based |
| Path A hợp lệ, body cố ghi tenantId=B | Không để body đổi context; từ chối dữ liệu không hợp lệ theo command |
| Header tenant từ Internet không được hỗ trợ | Bỏ qua hoặc từ chối theo hợp đồng, không dùng làm thẩm quyền |
| Không có selector trong endpoint bắt buộc chọn tenant | Không dùng tenant đầu tiên hoặc context cũ |
| Slug/domain không có mapping duy nhất hợp lệ | Không đoán tenant |
| Membership ở A bị thu hồi nhưng token vẫn còn claim cũ | Xử lý theo cam kết kiểm chứng/thu hồi, không mặc định claim cũ luôn đủ |

Không cần tiết lộ cho caller tenant khác có tồn tại hay không. Response và log nội bộ có thể có độ chi tiết khác nhau theo quyền xem.

## 8. Host, custom domain và header qua proxy

### 8.1. Host là đầu vào cần kiểm chứng

Một host hợp lệ về cú pháp chưa chứng minh caller thuộc tenant tương ứng.

Nếu định tuyến theo subdomain hoặc custom domain:

- Chỉ chấp nhận các dạng host được ứng dụng hỗ trợ.
- Dùng cơ chế phân tích/chuẩn hóa host phù hợp, không tự cắt chuỗi tùy ý.
- Tra registry do hệ thống quản lý.
- Có quy trình xác minh và quản lý vòng đời custom domain.
- Kiểm tra membership/thẩm quyền sau khi giải quyết tenant.
- Từ chối host không biết thay vì dùng một tenant mặc định.

DNS hoặc khả năng đưa tên host vào request không tự cấp quyền trên dữ liệu tenant.

Cần thống nhất cách xử lý các dạng biểu diễn tương đương, cổng và tên miền quốc tế nếu sản phẩm hỗ trợ. Không để gateway và application ánh xạ cùng request sang hai tenant khác nhau do chuẩn hóa khác nhau.

### 8.2. Custom domain có vòng đời riêng

Khi tenant bỏ custom domain, domain được chuyển chủ hoặc mapping được thay đổi, cần thu hồi/invalidate mapping và cache liên quan.

Không để một mapping cũ tiếp tục định tuyến sang dữ liệu tenant trước chỉ vì nó từng hợp lệ.

Định danh tenant ổn định nên độc lập với việc thay domain. Job, receipt và quan hệ dữ liệu không nên dựa duy nhất vào tên miền có thể đổi chủ.

### 8.3. Header chỉ tin được khi nguồn ghi đáng tin cậy

Nếu gateway truyền canonical tenantId vào header, cần:

~~~text
Ngăn caller tự chèn header tin cậy
    → gateway kiểm chứng theo hợp đồng
    → gateway ghi ngữ cảnh đã xác nhận
    → application xác thực nguồn/giao thức gateway
    → application áp dụng kiểm tra thẩm quyền cần thiết
~~~

Việc đặt tên header là X-Verified-Tenant không làm nó đáng tin cậy. Cũng cần ngăn đường truy cập trực tiếp vào application bỏ qua gateway nhưng vẫn tự gửi header đó.

Thông tin forwarded host chỉ được dùng theo chính sách proxy tin cậy. Không mặc định tin mọi X-Forwarded-* do Internet gửi vào.

Một mạng nội bộ chung chưa tự chứng minh mọi dịch vụ trong mạng có quyền giả ngữ cảnh của mọi tenant.

## 9. Giữ tenant context ổn định trong một lần thực thi

### 9.1. Context nên bất biến theo request

Sau khi resolve thành công, các lớp nên dùng cùng canonical tenantId. Không để repository đọc header, service đọc session và policy đọc token theo ba cách khác nhau.

Một dạng context nội bộ có thể là:

~~~java
record TenantContext(
        TenantId tenantId,
        PrincipalId principalId,
        AuthorityReference authority,
        long authorityVersion,
        Instant resolvedAt) {
}
~~~

Đây chỉ là mô hình dữ liệu minh họa. Trong triển khai, cần kiểm soát nơi tạo context để payload không thể tự tạo một context “đã xác minh”.

Nếu quyền thay đổi giữa request, áp dụng cam kết về độ mới và kiểm chứng của hệ thống. Việc context bất biến không có nghĩa mọi quyền trong đó có hiệu lực vô hạn.

### 9.2. Chuyển tenant ở giao diện không được sửa request đang chạy

Một user có thể mở tab A cho tenant A và tab B cho tenant B. Nếu server chỉ dùng một biến activeTenant trong session chung, đổi tenant ở tab B có thể làm form cũ của tab A gửi dữ liệu vào B.

Cần ràng buộc request với tenant đích theo hợp đồng, ví dụ path/context được xác minh. Nếu session có active tenant, kiểm tra tính nhất quán thay vì âm thầm chuyển ý nghĩa request.

Sau khi request bắt đầu, không đọc lại một biến chọn tenant có thể thay đổi để quyết định nơi ghi từng câu lệnh.

### 9.3. ThreadLocal không tự giải quyết lifecycle và bất đồng bộ

Nếu dùng context gắn với thread, phải gỡ/khôi phục nó khi xử lý xong kể cả khi có exception.

Một pattern minh họa:

~~~java
try (var scope = tenantScope.openVerified(tenantContext)) {
    return application.handle(command, tenantContext);
}
~~~

tenantScope trong ví dụ phải đóng đúng cách, khôi phục context trước đó nếu có hoặc loại bỏ context của request hiện tại theo hợp đồng.

Không để một worker thread xử lý tenant A xong rồi giữ nguyên A cho request B. Cũng không mặc định ThreadLocal tự truyền đúng qua executor, callback hoặc luồng xử lý bất đồng bộ.

Truyền context tường minh là một lựa chọn giúp nhìn rõ phụ thuộc. Nếu framework quản lý context, vẫn cần kiểm chứng việc lan truyền và dọn dẹp trong các đường async, lỗi và hủy.

Thiếu context tại repository nghiệp vụ phải bị phát hiện; không diễn giải nó thành quyền toàn nền tảng.

## 10. Đưa canonical tenantId tới đúng kho dữ liệu

### 10.1. Mô hình lưu trữ khác nhau vẫn cần cùng một nguồn quyết định

| Mô hình | Tenant context được dùng để làm gì |
|---|---|
| Chung bảng, có tenant_id | Ràng buộc mọi dòng đọc/ghi và quan hệ liên quan |
| Schema riêng | Chọn schema từ registry/cấu hình tin cậy |
| Database riêng | Chọn kết nối từ registry/cấu hình tin cậy |
| Kết hợp nhiều mô hình | Định tuyến theo canonical tenantId và loại dữ liệu |

Không xây tên schema, chuỗi kết nối hoặc địa chỉ dịch vụ trực tiếp từ input client. Mapping tới hạ tầng là dữ liệu cấu hình có thẩm quyền.

Tách database cũng không ngăn lỗi nếu resolver chọn nhầm database. Chung bảng cũng không thể an toàn nếu một đường query bỏ điều kiện tenant.

### 10.2. Đọc và ghi đều phải bị ràng buộc

Ví dụ query khái niệm:

~~~sql
SELECT *
FROM refund
WHERE tenant_id = :verified_tenant_id
  AND id = :refund_id;
~~~

verified_tenant_id lấy từ context đã kiểm chứng, không từ một trường allowedTenant do client gửi.

Với INSERT, server xác lập tenant_id theo context. Với UPDATE/DELETE, điều kiện ghi phải giữ biên tenant và kiểm tra số dòng tác động theo hợp đồng.

Không nạp dữ liệu tenant khác rồi trả lỗi sau khi đã phát notification, ghi audit nhạy cảm hoặc tạo job.

### 10.3. Đối tượng liên quan phải cùng biên phù hợp

Một refund có tenant_id=A nhưng payment_id trỏ sang payment của B là dữ liệu mâu thuẫn dù query refund đã lọc đúng tenant.

Có thể dùng khóa/constraint phù hợp, chẳng hạn quan hệ tham chiếu theo cặp tenant_id và payment_id, kết hợp kiểm tra nghiệp vụ.

Nếu hệ thống cho phép một quan hệ xuyên tenant, đó phải là loại quan hệ có thẩm quyền và quy tắc riêng; không được hình thành do thiếu kiểm tra liên kết.

Biết canonical tenantId giải quyết điểm xuất phát. Nó không tự làm mọi foreign key và phép join tuân thủ tenant isolation.

### 10.4. Kết nối pool có trạng thái phải được kiểm soát

Nếu tenant được gắn vào schema hoặc biến session của DB, connection tái sử dụng có thể còn trạng thái của tenant trước.

Cần thiết lập đúng ngữ cảnh và dọn/khôi phục theo cơ chế cơ sở dữ liệu, thư viện kết nối và transaction đang dùng. Nếu có cơ chế scope theo transaction phù hợp, vẫn phải kiểm chứng khi commit, rollback, exception và tái sử dụng connection.

Không dùng giả định “request luôn mở connection mới” làm lớp bảo vệ duy nhất.

### 10.5. Cache và idempotency phải phân biệt tenant

Các đối tượng có cùng ID cục bộ ở hai tenant không được dùng chung cache entry:

~~~text
Cache key phù hợp với mô hình:
  tenantId + resourceType + resourceId
~~~

Còn cần các chiều quyền, phiên bản hoặc projection nếu nội dung cache phụ thuộc chúng. Có tenant trong key không thay kiểm tra quyền người nhận response.

Receipt/idempotency cũng phải giữ đúng phạm vi tenant, caller và action theo thiết kế. Một khóa giống nhau ở A và B không được khiến caller B nhận kết quả bí mật của A.

Khi resolver cache mapping alias/domain hoặc membership, cần vô hiệu hóa/độ mới phù hợp. Không cache một kết luận “được hoạt động trong tenant” vô thời hạn.

## 11. Worker, message và retry

### 11.1. Ghi tenant chuẩn trước khi enqueue

Khi command được chấp nhận, job/outbox nên chứa định danh đã được server xác lập:

~~~text
canonical tenantId
operationId ổn định
loại command/event
resourceId và revision liên quan
người khởi tạo và nguồn thẩm quyền cần giữ
phiên bản schema của message
~~~

Việc tạo ý định công việc cần nhất quán với transaction nghiệp vụ liên quan.

Không lưu duy nhất slug hoặc domain rồi resolve lại theo tên hiện tại khi worker chạy. Tên có thể đã đổi hoặc được chuyển sang tổ chức khác.

Nếu có di chuyển/ghép tenant, phải có quy trình và mapping chuyển đổi được quản lý riêng, không tự diễn giải mọi job cũ sang tenant mới.

### 11.2. Tenant trong message chưa đủ làm bằng chứng

Consumer cần xác minh:

- Message đến từ nguồn/producer được phép theo giao thức.
- Producer có quyền tạo loại công việc trong tenant đó.
- Operation và resource thực sự thuộc tenant được khai.
- Context cho worker phù hợp với quyền dịch vụ và chính sách công việc.
- Payload không thể đổi tenant/đối tượng ngoài ý định đã ghi.

Một producer nội bộ được xác thực không mặc nhiên được tạo công việc cho mọi tenant.

Nếu message được giao lại, retry/dead-letter vẫn giữ canonical tenantId và operationId. Không bỏ tenant khi chuyển sang đường xử lý lỗi hoặc chọn một tenant mặc định để “cho job chạy tiếp”.

### 11.3. Không mang nguyên token người dùng làm trạng thái lâu dài

Công việc bất đồng bộ cần mô hình thẩm quyền rõ: kiểm tra khi nhận, điều kiện kiểm tra lại khi thực thi và quyền dịch vụ được ủy nhiệm.

Không lưu nguyên thông tin xác thực của người dùng vào message chỉ để worker hoạt động giống request gốc.

Nếu membership người khởi tạo thay đổi, job tiếp tục hay bị chặn phụ thuộc chính sách công việc. Trong mọi trường hợp, worker không được đổi sang tenant khác để khắc phục lỗi quyền.

## 12. Webhook và mapping tenant từ hệ thống ngoài

Một callback thanh toán thường không mang danh tính người dùng ứng dụng. Cần giải quyết tenant theo nguồn tích hợp đã được kiểm chứng.

Một pipeline có thể là:

~~~text
Nhận gợi ý external account / operation
    → chọn ngữ cảnh kiểm chứng từ cấu hình tin cậy
    → xác thực nguồn và tính toàn vẹn sự kiện
    → đối chiếu provider account, môi trường và operation
    → ánh xạ về canonical tenantId
    → tạo context dịch vụ bị giới hạn
    → nạp đúng operation trong tenant
    → kiểm tra số tiền, currency, trạng thái và xử lý trùng
~~~

### 12.1. Gợi ý để tìm khóa kiểm chứng chưa phải tenant đã xác nhận

Một field accountId chưa được xác minh có thể được dùng để tìm một tập cấu hình kiểm chứng giới hạn. Chỉ sau khi xác minh và đối chiếu theo hợp đồng nhà cung cấp, nó mới góp phần ràng buộc tenant.

Không nhận tenantId từ callback rồi dùng ngay để sửa payment. Một chữ ký hợp lệ về nguồn cũng phải được đối chiếu với đúng account/operation; không chỉ chứng minh “sự kiện có vẻ đến từ nhà cung cấp”.

Nếu phải gọi lại nhà cung cấp để xác nhận, dùng cấu hình endpoint/tài khoản đã quản lý, không dùng URL tùy ý từ payload.

### 12.2. Namespace và quan hệ mapping phải đủ phân biệt

Một external account reference có thể cần được hiểu theo bộ:

~~~text
provider + environment + external account
~~~

Không trộn môi trường thử nghiệm với production hoặc hai nhà cung cấp có cùng chuỗi accountId.

Nếu một provider account dùng chung cho nhiều tenant, accountId chưa đủ xác định tenant. Cần operation reference do server tạo và quan hệ được lưu, hoặc một căn cứ được xác thực khác phù hợp.

Mapping mơ hồ phải dừng xử lý/chuyển đối soát, không chọn tenant đầu tiên.

### 12.3. Sự kiện đến muộn vẫn thuộc operation gốc

Nếu domain, slug hoặc membership đã đổi sau khi gửi thanh toán, callback vẫn phải được đối chiếu với canonical tenantId và operation đã lưu.

Việc tenant không còn nhận giao dịch mới không có nghĩa được bỏ qua kết quả tài chính đã xảy ra. Luồng đối soát phải có thẩm quyền phù hợp để ghi nhận và xử lý nghĩa vụ, đồng thời không mở lại toàn bộ quyền nghiệp vụ cho tenant.

## 13. Xử lý lỗi và ghi dấu quá trình resolution

### 13.1. Lỗi resolution phải kết thúc trước hiệu ứng nghiệp vụ

Với endpoint bắt buộc có tenant, các tình huống sau không được tạo context dùng được:

~~~text
thiếu selector theo hợp đồng
selector không hợp lệ hoặc mapping mơ hồ
ràng buộc tenant mâu thuẫn
membership/thẩm quyền không hợp lệ
tenant không cho phép loại thao tác
nguồn kiểm chứng bắt buộc chưa xác định được
~~~

Không tạo refund, reservation, outbox hoặc job rồi mới phát hiện tenant không hợp lệ.

Nếu nguồn membership bị lỗi tạm thời, không dùng tenant mặc định hoặc dữ liệu rỗng để cho phép. Phân biệt nội bộ lỗi phụ thuộc với việc caller không có quyền, đồng thời giữ response ngoài phù hợp chính sách tiết lộ.

### 13.2. Không biến lỗi thành công cụ dò tenant

Caller không được biết mọi chi tiết về tenant hoặc membership ngoài phạm vi.

Response có thể dùng thông báo an toàn và mã tham chiếu. Nhân viên có quyền điều tra mới xem các reason code như:

~~~text
TENANT_SELECTOR_MISSING
TENANT_BINDING_CONFLICT
TENANT_MAPPING_UNRESOLVED
TENANT_AUTHORITY_NOT_ACTIVE
TENANT_OPERATION_NOT_ALLOWED
TENANT_AUTHORITY_SOURCE_UNAVAILABLE
~~~

Các mã là ví dụ thiết kế, không phải chuẩn bắt buộc.

Endpoint liệt kê tenant phải chỉ trả các tenant caller được phép thấy theo chính sách, không trở thành danh bạ toàn nền tảng. Việc phân biệt các lỗi và giới hạn tần suất tra cứu cần được thiết kế nhất quán.

### 13.3. Dữ liệu quan sát cần phân biệt requested và resolved

Một bản ghi resolution có thể chứa:

~~~text
resolutionId, requestId hoặc operationId
principal đã xác thực
loại hợp đồng endpoint
loại selector và nguồn đã được xác nhận
canonical tenantId nếu giải quyết được
tham chiếu authority/membership và phiên bản
kết quả, reason code, thời điểm
~~~

Không ghi raw token, bí mật webhook hoặc toàn bộ header chỉ để truy vết tenant.

Giữ được nguồn giúp điều tra vì sao policy và repository đã dùng tenant đó. Một dòng tenant=A không giải thích được A đến từ path, gateway, mapping tích hợp hay context còn sót.

Log ghi tenantId không thay thế kiểm chứng; nhãn “verified” chỉ có ý nghĩa nếu đường xử lý thực sự đã xác minh nguồn.

## 14. Kiểm thử tenant identity resolution

### 14.1. Ma trận đầu vào và nguồn tin cậy

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Token bound-tenant A, path B | Không tạo context B hoặc fallback sang một tenant khác |
| Token định danh user, membership B hợp lệ, path B | Có thể resolve B theo hợp đồng đa tenant |
| Caller có quyền duyệt ở A, chỉ được xem ở B | Resolve B không mang theo quyền duyệt của A |
| Host và path là hai alias hợp lệ của cùng tenant | So sánh canonical ID, không từ chối chỉ vì chuỗi khác |
| Host ràng buộc A, path B | Chặn mâu thuẫn trước hiệu ứng nghiệp vụ |
| Caller tự gửi header mang tên verified tenant | Không có thêm độ tin cậy chỉ vì tên header |
| Truy cập thẳng application để né gateway | Không dùng được ngữ cảnh gateway chưa xác minh |
| Path/host không resolve được | Không chọn tenant đầu tiên hoặc tenant mặc định |
| User có nhiều membership nhưng endpoint thiếu selector bắt buộc | Không đoán ý định |
| Membership chỉ là lời mời đang chờ hoặc đã thu hồi | Không coi là quyền hoạt động active |
| Source membership lỗi | Không tự cấp quyền bằng fallback |
| Body cố đổi tenantId sau resolution | Không thay context hoặc tenant_id được ghi |
| ID đối tượng thuộc tenant khác | Resolution không thay cho kiểm tra object binding; đối tượng không được xử lý |
| Tenant bị khóa với nghiệp vụ mới | Không mở giao dịch mới bằng luồng thông thường |
| Context không có tại repository nghiệp vụ | Lỗi rõ ràng, không truy vấn toàn nền tảng |
| Alias/domain đổi chủ hoặc bị thu hồi | Cache/mapping không tiếp tục mở dữ liệu tenant cũ |
| Job retry sau khi slug đổi | Giữ đúng canonical tenantId và operation gốc |
| Producer/message không đủ thẩm quyền tenant | Không thực thi chỉ vì payload có tenantId |
| Webhook có account/operation không khớp | Không chọn tenant theo một field tùy ý |
| Hai tenant có cùng resourceId cục bộ | Không nhầm query, cache hoặc receipt |

### 14.2. Kiểm thử không có hiệu ứng sau resolution thất bại

Chuẩn bị hai tenant A và B, mỗi tenant có payment và refund riêng. Dùng caller chỉ có thẩm quyền ở A rồi yêu cầu xử lý B bằng selector giả/mâu thuẫn.

Đọc lại dữ liệu qua một đường kiểm thử có quyền quan sát phù hợp:

~~~text
refund của A không đổi
refund của B không đổi
không có reservation mới ở cả hai tenant
không có decision nghiệp vụ mới
không có outbox/job thực hiện request bị chặn
không có receipt tiết lộ kết quả của tenant kia
~~~

Security event về lần thử có thể được ghi theo thiết kế.

Không chỉ assert response code. Một handler có thể trả lỗi sau khi đã enqueue công việc sai tenant; ca kiểm thử phải phát hiện phần hiệu ứng đó.

### 14.3. Kiểm thử rò context trong thread pool

Dùng một pool có một worker để buộc tái sử dụng thread:

1. Xử lý request của A và tạo một exception sau khi context được gắn.
2. Kết thúc request bằng đường dọn dẹp bình thường của framework.
3. Chạy request kế tiếp thiếu tenant context, nếu endpoint bắt buộc có tenant.
4. Xác nhận request thứ hai bị chặn, không thừa hưởng A.
5. Chạy request hợp lệ của B.
6. Xác nhận policy, repository và audit đều dùng B.

Kiểm thử thêm callback hoặc tác vụ async theo cơ chế framework đang dùng. Một ca chạy đồng bộ thành công không chứng minh context được truyền đúng qua executor khác.

### 14.4. Kiểm thử connection pool có trạng thái tenant

Nếu kiến trúc dùng schema/session context của DB, có thể giới hạn pool còn một connection trong kiểm thử:

~~~text
Request A thiết lập ngữ cảnh A.
Một đường xử lý lỗi/rollback xảy ra.
Connection quay về pool.
Request B lấy lại connection.
~~~

Xác nhận B chỉ thấy và ghi vào B, đồng thời request thiếu context không dùng trạng thái của A.

Kiểm thử trên cơ chế thực tế. Mock repository không phát hiện trạng thái còn sót trong connection.

### 14.5. Kiểm thử cache và định danh cục bộ

Tạo cùng resourceId=42 ở A và B với giá trị phân biệt được. Đọc A trước để làm nóng cache, rồi đọc B.

Kết quả B phải thuộc B và tuân thủ quyền actor trong B. Không chỉ kiểm tra objectId vì nó cố ý giống nhau.

Lặp ý tưởng đó với idempotency key giống nhau ở hai tenant để phát hiện receipt hoặc kết quả bị dùng chéo.

### 14.6. Kiểm thử mapping thay đổi

Tạo job với canonical tenant A rồi thay slug/domain của A. Nếu một alias cũ được chuyển theo chính sách sang tenant B, job cũ vẫn phải tham chiếu A hoặc bị chặn theo một quy trình migration rõ ràng.

Không được resolve lại alias cũ rồi thực thi job của A vào B.

Với webhook, kiểm thử account dùng chung nhiều tenant để xác nhận operation reference thực sự phân biệt được tenant; không chỉ thử mô hình mỗi tenant có một account riêng.

## 15. Tình huống thực hành: hai tab, hai tenant

Lan có membership ở A và B. Lan được approve trong A nhưng chỉ có quyền READ ở B. Cả hai tenant đều có refundId cục bộ là 42.

Chuỗi thao tác:

~~~text
1. Tab A mở refund 42 của tenant A.
2. Tab B chuyển lựa chọn tenant trong session sang B.
3. Tab A gửi form approve cũ.
~~~

Một thiết kế lỗi có thể:

~~~text
Đọc activeTenant từ session → B.
Đọc role của Lan không giữ scope tenant → APPROVER.
Nạp refund 42 trong B.
Approve sai đối tượng.
~~~

Có hai lớp sai độc lập: không giữ đúng tenant đích của request và dùng quyền A trong B.

Thiết kế phù hợp cần:

- Request biểu đạt/ràng buộc tenant đích theo hợp đồng, chẳng hạn đường dẫn tenant A.
- Resolver xác minh lựa chọn và các binding liên quan.
- Context không bị đổi bởi thao tác ở tab khác trong lúc xử lý.
- Policy lấy thẩm quyền của Lan trong chính tenant đã resolve.
- Query nạp refund theo cặp tenant và định danh đối tượng.
- Command kiểm tra version, trạng thái và các bất biến trước khi commit.

Nếu hợp đồng coi session đang chọn B là binding bắt buộc, request cũ của A có thể bị từ chối để người dùng chọn lại. Nếu path là selector hợp lệ và session không phải binding, server có thể xử lý A sau kiểm chứng. Trong cả hai thiết kế, không được âm thầm chuyển nội dung form A thành thao tác ở B.

Hãy thử thêm body có tenantId=B hoặc một header giả chỉ tới B. Các trường đó không được thay đổi tenant đã được quyết định theo hợp đồng.

## 16. Khung đặc tả resolver

Trước khi triển khai, hãy ghi rõ:

~~~text
Loại endpoint và caller:
Có bắt buộc tenant không:
Selector được chấp nhận:
Nguồn nào là binding có thẩm quyền:
Namespace và mapping tới canonical tenantId:
Cách chuẩn hóa và phát hiện mơ hồ/mâu thuẫn:

Membership hoặc service authority cần có:
Trạng thái tenant cho phép loại thao tác:
Độ mới và hành vi khi nguồn kiểm chứng lỗi:
Kiểu TenantContext và nơi được phép tạo:

Cách truyền context qua app/async/DB:
Quy tắc cache, job, retry và webhook:
Biên query/ghi dữ liệu sau resolution:
Cleanup khi exception, rollback, hủy và tái sử dụng tài nguyên:
Log an toàn và ca kiểm thử chéo tenant:
~~~

## 17. Câu hỏi tự kiểm tra

1. Tenant selector khác thẩm quyền hoạt động trong tenant như thế nào?
2. Vì sao home organization trong một danh tính không tự bằng tenant hiện tại của ứng dụng?
3. Khi token bound-tenant khác path, tại sao chọn một nguồn theo ưu tiên là chưa đủ?
4. Trường hợp nào user được chọn tenant khác một cách hợp lệ?
5. Một request thiếu context có thể vô tình trở thành truy vấn toàn nền tảng ở đâu?
6. Thread pool và connection pool của bạn dọn trạng thái tenant như thế nào khi có exception?
7. Vì sao job nên lưu canonical tenantId thay vì chỉ slug/domain?
8. Một chữ ký webhook hợp lệ còn cần được đối chiếu với account và operation ra sao?
9. Quyền action trong tenant A có thể bị dùng nhầm ở B qua những bộ nhớ đệm hoặc mô hình role nào?

Một resolver có thể tin cậy phải tạo ra **một tenant đích đã được kiểm chứng cho đúng lần thực thi**, rồi giữ ngữ nghĩa đó qua các lớp. Mọi quyền theo đối tượng, transaction và cơ chế chống trùng sau đó đều phải hoạt động bên trong đúng biên tenant ấy.
