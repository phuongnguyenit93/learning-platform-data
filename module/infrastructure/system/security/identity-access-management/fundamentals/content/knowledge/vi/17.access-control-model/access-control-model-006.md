# Coarse-grained access

## 1. Coarse-grained access là gì?

Coarse-grained access là cách kiểm soát truy cập ở phạm vi tương đối rộng, chẳng hạn một ứng dụng, phân hệ, nhóm chức năng hoặc loại thao tác. Thay vì quyết định riêng cho từng bản ghi hoặc từng trường dữ liệu, hệ thống trả lời những câu hỏi như:

- Người dùng có được mở phân hệ thanh toán không?
- Danh tính này có được sử dụng chức năng xuất hóa đơn không?
- Nhân viên hỗ trợ có được truy cập công cụ quản lý ticket không?
- Tài khoản dịch vụ có được gọi nhóm API báo cáo không?

“Coarse” mô tả độ hạt của quyết định, không có nghĩa quyết định đó được triển khai sơ sài. Một quy tắc cho phép đọc toàn bộ tài liệu công khai có thể hoàn toàn phù hợp với yêu cầu. Ngược lại, một kiểm tra vai trò rất ngắn có thể không đủ khi người dùng chỉ được đọc những hồ sơ được giao.

Ví dụ, Lan có permission invoice.read trong tenant A. Kiểm tra permission này cho biết Lan được tham gia chức năng đọc hóa đơn theo hợp đồng của ứng dụng. Nó chưa tự nói Lan được đọc hóa đơn nào nếu quyền dữ liệu còn bị giới hạn theo khách hàng, bộ phận hoặc quan hệ phân công.

Phân biệt chính cần giữ là:

~~~text
Quyền sử dụng chức năng
khác với
quyền trên từng đối tượng và dữ liệu mà chức năng xử lý.
~~~

Trong nền tảng IAM, coarse-grained access thường là một lớp kiểm soát ban đầu giúp giới hạn khả năng sử dụng hệ thống. Với những chức năng có yêu cầu chi tiết hơn, nó được phối hợp với tenant scope, ownership, thuộc tính hoặc quan hệ tài nguyên.

## 2. Độ hạt có nhiều chiều

Không có một số lượng bản ghi cố định để phân loại mọi chính sách thành coarse hay fine. Cần xét điều gì được phân biệt trong quyết định.

| Chiều phân biệt | Quy tắc tương đối coarse | Quy tắc chi tiết hơn |
| --- | --- | --- |
| Chức năng | Được vào phân hệ Billing | Được đọc, điều chỉnh hoặc xuất hóa đơn theo từng action |
| Tài nguyên | Được đọc hóa đơn trong một phạm vi rộng | Chỉ đọc hóa đơn được giao |
| Dữ liệu trả về | Được xem báo cáo | Chỉ xem một số cột hoặc dữ liệu đã che |
| Ngữ cảnh | Có permission hiện hành | Còn cần mức bảo đảm phiên hoặc điều kiện thao tác |
| Phạm vi quản trị | Là admin ứng dụng | Chỉ quản lý thành viên của một tenant cụ thể |

Một chính sách có thể chi tiết theo action nhưng rộng theo dữ liệu. Chẳng hạn invoice.export phân biệt rõ thao tác xuất, nhưng có thể cho phép xuất toàn bộ hóa đơn của tenant khi nghiệp vụ đã cấp phạm vi ấy.

Tên permission không tự định nghĩa độ rộng dữ liệu. Cần mô tả cả action, resource scope và những điều kiện cần thiết.

### 2.1. Ví dụ quyền rộng nhưng hợp lệ

Nhân viên kế toán phụ trách toàn tenant có thể được đọc mọi hóa đơn của tenant đó. Nếu đây là yêu cầu đã được xác nhận, hệ thống không cần giả lập một điều kiện “owner phải là người gọi” chỉ để làm chính sách trông chi tiết hơn.

Tuy nhiên, vẫn phải xác định:

~~~text
Mọi hóa đơn của tenant nào?
Loại dữ liệu nào được đọc?
Có bao gồm hóa đơn lưu trữ hoặc đặc biệt nhạy cảm không?
Có được tải file hoặc xuất hàng loạt không?
Quyền có còn hiệu lực với request hiện tại không?
~~~

Quyền rộng có chủ đích vẫn cần phạm vi rõ ràng. Nó không phải quyền đọc mọi dữ liệu trong toàn nền tảng.

### 2.2. Ví dụ coarse gate chỉ là điều kiện ban đầu

Nhân viên xử lý hóa đơn có invoice.read, nhưng chỉ được xem những hóa đơn được giao. Trong trường hợp này:

~~~text
Có invoice.read
    -> được xét tiếp quyền trên hóa đơn
    -> chỉ trả dữ liệu nếu phân công và những điều kiện khác hợp lệ
~~~

Nếu bỏ kiểm tra phân công, permission ở cấp chức năng đã bị sử dụng vượt ý nghĩa được thiết kế.

## 3. Coarse-grained access khác gì RBAC, ABAC và ReBAC?

RBAC, ABAC và ReBAC mô tả những cách tổ chức căn cứ cấp quyền. Coarse-grained và fine-grained mô tả mức độ phân biệt của quyết định. Hai nhóm khái niệm không phải các lựa chọn loại trừ nhau.

| Mô hình | Có thể dùng ở mức coarse | Có thể dùng ở mức chi tiết |
| --- | --- | --- |
| RBAC | Role BillingViewer có quyền mở phân hệ | Role gắn với một dự án hoặc phạm vi cụ thể |
| ABAC | Cho nhân viên đang hoạt động dùng công cụ nội bộ | Kết hợp thuộc tính chủ thể, hóa đơn và môi trường |
| ReBAC | Member tổ chức được vào workspace | Người được giao hoặc cộng tác viên được đọc tài liệu |
| Permission trực tiếp | Danh tính được gọi API báo cáo | Danh tính được cấp một action trên một tài nguyên |

Không nên đồng nhất “có role” với coarse hoặc “có policy engine” với fine. Một policy engine vẫn có thể đánh giá một cờ isAdmin rất rộng. Một mô hình role theo tài nguyên có thể diễn đạt quyền khá chi tiết.

Cũng cần phân biệt với vị trí triển khai. Một kiểm tra tập trung ở gateway không tự là coarse, và một kiểm tra trong service không tự là fine. Độ hạt phụ thuộc thông tin và ngữ nghĩa được dùng để quyết định.

## 4. Vai trò của coarse access trong kiến trúc IAM

### 4.1. Xác thực trước, phân quyền theo chức năng sau

Xác thực xác định danh tính đang thực hiện yêu cầu. Coarse authorization xác định danh tính đó có được sử dụng nhóm chức năng đang yêu cầu hay không.

Token hợp lệ không có nghĩa mọi endpoint đều được phép gọi. Tương tự, danh tính thuộc tenant A chưa tự có quyền xuất dữ liệu của A.

Một luồng tham khảo là:

~~~mermaid
flowchart TD
    A["Request"] --> B["Xác thực và dựng ngữ cảnh tin cậy"]
    B --> C["Kiểm tra quyền chức năng"]
    C -->|"Không đạt"| D["Không thực hiện thao tác"]
    C -->|"Đạt"| E["Xác định tài nguyên và phạm vi dữ liệu"]
    E --> F["Áp dụng chính sách dữ liệu phù hợp"]
    F -->|"Không đạt hoặc lỗi"| D
    F -->|"Đạt"| G["Thực hiện thao tác và trả dữ liệu được phép"]
~~~

Nếu yêu cầu nghiệp vụ thực sự cho phép toàn bộ dữ liệu trong phạm vi đã xác định, chính sách ở bước dữ liệu có thể kiểm tra đúng phạm vi ấy. Không bắt buộc mỗi tài nguyên phải có một ACL riêng.

### 4.2. Chặn sớm có ích gì?

Một actor không có invoice.export có thể bị chặn trước khi hệ thống xây dựng báo cáo hoặc đọc nhiều dữ liệu. Điều này làm rõ ranh giới chức năng và có thể tránh những xử lý không cần thiết.

Tuy nhiên, “đạt kiểm tra ban đầu” không được ghi nhận như quyết định cuối cùng khi các bước sau vẫn có thể từ chối. Một kết quả gate passed chỉ nói lớp coarse đã đạt.

### 4.3. Quy tắc mặc định

Chức năng mới hoặc permission không được nhận diện cần có cách xử lý rõ ràng. Không nên cấp quyền chỉ vì một route chưa được gán vào bảng permission hoặc một nhánh kiểm tra chưa được viết.

OWASP khuyến nghị mặc định từ chối và xác minh quyền cho mỗi request. [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Điều đó không có nghĩa mỗi request cần gọi một máy chủ IAM từ xa. Kiểm tra có thể dùng một snapshot quyền còn hiệu lực, thư viện hoặc dịch vụ tùy kiến trúc; yêu cầu là cơ chế thực thi giữ đúng hợp đồng quyền và độ mới dữ liệu.

## 5. Thiết kế permission ở cấp chức năng

### 5.1. Gọi tên theo khả năng nghiệp vụ

Một bộ permission minh họa cho phân hệ hóa đơn:

~~~text
billing.access
invoice.read
invoice.adjust
invoice.export
membership.manage
~~~

Ý nghĩa cần được mô tả:

- billing.access cho phép mở phần chức năng Billing theo thiết kế, không tự cấp quyền đọc mọi hóa đơn.
- invoice.read là điều kiện sử dụng chức năng đọc; phạm vi hóa đơn được phép còn do chính sách dữ liệu xác định.
- invoice.adjust cho phép xét thao tác điều chỉnh, không mặc nhiên cho phép sửa mọi hóa đơn ở mọi trạng thái.
- invoice.export là quyền riêng cho thao tác xuất.
- membership.manage quản lý thành viên trong phạm vi được cấp, không tự trao quyền nghiệp vụ kế toán.

Đây là quy ước của ví dụ, không phải danh sách permission chuẩn cho mọi hệ thống.

Không nhất thiết phải có cả permission mở phân hệ và permission của mọi thao tác. Nếu billing.access chỉ phục vụ điều hướng giao diện, backend vẫn phải kiểm tra các action thực sự có tác động đến dữ liệu.

### 5.2. Ánh xạ role sang permission

| Role trong tenant | Permission minh họa |
| --- | --- |
| BillingViewer | billing.access, invoice.read |
| BillingOperator | billing.access, invoice.read, invoice.adjust |
| BillingExporter | billing.access, invoice.read, invoice.export |
| MembershipAdmin | membership.manage |

Role chỉ là cách gom những permission phù hợp với công việc. Role MembershipAdmin không tự có invoice.read chỉ vì tên chứa Admin.

Role assignment cần gắn với phạm vi. Lan có BillingViewer ở tenant A không có nghĩa Lan mang cùng role ở tenant B.

Nếu một người có nhiều role, việc hợp permission phải tuân theo chính sách đã chọn. Sự tồn tại của một permission cũng chưa giải quyết những điều kiện tách biệt nhiệm vụ, chẳng hạn người tạo điều chỉnh không được tự phê duyệt điều chỉnh đó.

### 5.3. Tránh permission “làm mọi thứ”

Một permission như billing.manage có thể dễ triển khai ban đầu nhưng khó duy trì khi phân hệ phát triển thêm xóa hàng loạt, hoàn tiền hoặc đổi tài khoản nhận tiền.

Nếu mọi chức năng mới tự được đưa vào một wildcard hiện hữu, người đã được cấp role cũ có thể nhận thêm quyền mà không qua đánh giá lại.

Nên định nghĩa rõ action nào thuộc permission rộng, cách thay đổi phạm vi và ai có quyền duyệt. Không cần tạo permission cho từng nút giao diện, nhưng những thao tác khác biệt đáng kể về tác động cần được phân biệt phù hợp.

## 6. Ví dụ xuyên suốt: quyền đọc hóa đơn

Xét ba nhân viên cùng tenant A:

| Người dùng | Quyền chức năng | Phạm vi dữ liệu được cấp |
| --- | --- | --- |
| Lan | invoice.read | Những hóa đơn được giao cho Lan |
| Minh | invoice.read | Mọi hóa đơn của tenant A theo nghiệp vụ |
| Hà | invoice.export nhưng không có invoice.read | Theo quy định riêng của tác vụ xuất |

Bảng chỉ minh họa việc tách quyền chức năng và phạm vi dữ liệu. Các điều kiện trạng thái tài khoản, phiên và tenant vẫn phải hợp lệ.

### 6.1. Cùng coarse permission, khác quyền dữ liệu

Lan và Minh đều vượt qua kiểm tra invoice.read. Khi đọc hóa đơn inv-42:

~~~text
Lan:
    có invoice.read
    AND inv-42 thuộc tenant A
    AND inv-42 được giao cho Lan

Minh:
    có invoice.read
    AND được cấp data scope TENANT_INVOICES trong A
    AND inv-42 thuộc tenant A
~~~

Nếu inv-42 được giao cho người khác, Lan có thể bị từ chối còn Minh được phép. Kết quả này không mâu thuẫn: coarse permission giống nhau, chính sách dữ liệu khác nhau.

TENANT_INVOICES là tên scope do ví dụ đặt. Scope ấy phải đến từ grant được quản trị và được giới hạn ở tenant A. Không lấy một cờ đọc mọi hóa đơn do client tự gửi làm bằng chứng.

### 6.2. Khi coarse policy là chính sách phù hợp

Một hệ thống đơn giản có thể quy định mọi người được cấp BillingViewer đều đọc được tất cả hóa đơn của tenant nơi role được gán. Khi đó, không cần thêm phân công theo từng hóa đơn nếu nghiệp vụ không yêu cầu.

Quyền cuối vẫn phải giữ đúng ý nghĩa: role trong A, tài nguyên thuộc A, đúng thao tác đọc và đúng tập dữ liệu đã được cấp. Không bỏ tenant lookup vì role đã là điều kiện rộng.

Khi phát sinh yêu cầu “chỉ được đọc khách hàng mình phụ trách”, cần thay đổi hoặc bổ sung chính sách dữ liệu. Không giữ nguyên logic đọc toàn tenant rồi chỉ lọc danh sách ở giao diện.

### 6.3. Các action không tự bao hàm nhau

Hà có invoice.export không nhất thiết được dùng endpoint đọc hóa đơn tương tác. Quan hệ giữa export và read phải được định nghĩa trong chính sách.

Nếu tổ chức muốn export bao hàm read, cần cấu hình điều đó một cách rõ ràng. Nếu không, không tự suy ra từ tên action hoặc từ việc cả hai đều lấy dữ liệu.

Tương tự, có invoice.adjust không tự có invoice.export. Quyền ghi, xem và xuất có những tác động khác nhau.

## 7. Java minh họa cổng kiểm tra chức năng

Đoạn code sau dùng Java 17 trở lên và chỉ minh họa coarse gate. Nó không xác thực token, không tải role assignment và không triển khai chính sách dữ liệu trên từng hóa đơn.

Tên TrustedContext biểu diễn tiền điều kiện: ngữ cảnh phải được backend dựng từ những nguồn đã kiểm chứng. Constructor không tự làm một dữ liệu do client gửi trở nên đáng tin cậy.

~~~java
import java.util.Objects;
import java.util.Set;

public class CoarseAccessExample {
    enum Permission {
        INVOICE_READ,
        INVOICE_ADJUST,
        INVOICE_EXPORT
    }

    enum GateDecision {
        DENIED,
        OBJECT_POLICY_REQUIRED
    }

    record TrustedContext(
            String subjectId,
            String tenantId,
            boolean active,
            Set<Permission> permissions) {

        TrustedContext {
            Objects.requireNonNull(subjectId, "subjectId");
            Objects.requireNonNull(tenantId, "tenantId");
            if (subjectId.isBlank() || tenantId.isBlank()) {
                throw new IllegalArgumentException(
                        "subjectId and tenantId must not be blank");
            }
            permissions = Set.copyOf(
                    Objects.requireNonNull(permissions, "permissions"));
        }
    }

    static GateDecision evaluateFeatureGate(
            TrustedContext context,
            Permission required) {

        if (context == null || required == null) {
            return GateDecision.DENIED;
        }
        if (!context.active()) {
            return GateDecision.DENIED;
        }
        if (!context.permissions().contains(required)) {
            return GateDecision.DENIED;
        }
        return GateDecision.OBJECT_POLICY_REQUIRED;
    }

    public static void main(String[] args) {
        var lan = new TrustedContext(
                "user-lan",
                "tenant-a",
                true,
                Set.of(Permission.INVOICE_READ));

        System.out.println(evaluateFeatureGate(
                lan, Permission.INVOICE_READ));
        System.out.println(evaluateFeatureGate(
                lan, Permission.INVOICE_EXPORT));

        var inactiveLan = new TrustedContext(
                "user-lan",
                "tenant-a",
                false,
                Set.of(Permission.INVOICE_READ));

        System.out.println(evaluateFeatureGate(
                inactiveLan, Permission.INVOICE_READ));
    }
}
~~~

Kết quả kỳ vọng của ví dụ theo thứ tự:

~~~text
OBJECT_POLICY_REQUIRED
DENIED
DENIED
~~~

OBJECT_POLICY_REQUIRED được chọn để nhấn mạnh rằng vượt gate chưa phải quyết định đọc tài nguyên. Trong mô hình khác, tên kết quả có thể khác, nhưng ranh giới trách nhiệm vẫn cần rõ.

Set.copyOf giữ tập permission bất biến ở mức collection của ví dụ và từ chối phần tử null. Nó không xác minh permission có còn hiệu lực, đến từ tenant đúng hay được cấp bởi ai; những điều đó thuộc bước dựng ngữ cảnh.

### 7.1. Kết hợp với thao tác đọc tài nguyên

Một luồng service bằng mã giả:

~~~text
readInvoice(session, selectedTenant, invoiceId):
    context = resolveAuthenticatedTenantContext(
        session, selectedTenant
    )

    gate = evaluateFeatureGate(context, INVOICE_READ)
    require gate == OBJECT_POLICY_REQUIRED

    invoice = repository.findByTenantAndId(
        context.tenantId, invoiceId
    )
    require invoice exists in that scope

    dataDecision = invoicePolicy.evaluate(
        context, action="invoice.read", resource=invoice
    )
    require dataDecision == ALLOWED

    return allowedInvoiceProjection(context, invoice)
~~~

Nếu chính sách dữ liệu cho phép toàn tenant, invoicePolicy kiểm tra grant phạm vi đó và những điều kiện liên quan. Nếu chỉ cho phép hóa đơn được giao, nó kiểm tra quan hệ phân công.

Không dùng một tham số khác chưa kiểm tra để chọn hóa đơn ở bước trả dữ liệu. Quyết định cần bảo vệ đúng tài nguyên được sử dụng.

### 7.2. Phân biệt lỗi đánh giá với thiếu quyền

Không có permission là một kết quả phân quyền. Không tải được snapshot quyền hoặc policy service timeout là một lỗi không đánh giá được.

Cả hai có thể khiến thao tác không được thực hiện, nhưng audit và phản hồi vận hành cần phân biệt. Không đổi lỗi hạ tầng thành quyền đọc mặc định hoặc coi một tập permission rỗng do lỗi là bằng chứng rằng tài khoản thực sự không có quyền nào.

Ví dụ Java nhận một tập quyền đã được cung cấp thành công. Nó không định nghĩa mã HTTP hoặc toàn bộ cơ chế xử lý lỗi của ứng dụng.

## 8. Coarse gate nên được thực thi ở đâu?

### 8.1. Giao diện phục vụ trải nghiệm

Ẩn menu Billing hoặc nút Export giúp người dùng không thấy chức năng không phù hợp. Điều đó không ngăn họ gọi endpoint trực tiếp.

Backend phải thực thi quyền tương ứng. Cũng không nên tải toàn bộ dữ liệu về trình duyệt rồi dựa vào việc ẩn cột hoặc ẩn tab để giữ bí mật.

### 8.2. Gateway và lớp route

Gateway hoặc middleware có thể kiểm tra danh tính, audience phù hợp, quyền gọi nhóm API hoặc action được ánh xạ từ route. Đây là vị trí hữu ích cho những điều kiện chung.

Tuy nhiên, một gateway thường không có đủ thông tin về phân công, trạng thái tài nguyên hoặc dữ liệu cụ thể. Nếu yêu cầu cần những điều kiện đó, service bảo vệ tài nguyên phải đánh giá tiếp.

Nếu service còn có đường gọi nội bộ, tác vụ nền hoặc một endpoint khác, cần bảo đảm các đường đó cũng thực thi chính sách. Không dựa vào giả định mọi request đều đi qua một route đã được kiểm tra khi kiến trúc không bảo đảm điều ấy.

### 8.3. Service nghiệp vụ

Service có thể xác định action thực sự và tài nguyên sẽ được đọc hoặc thay đổi. Một method nghiệp vụ được nhiều controller sử dụng nên có ranh giới phân quyền phù hợp, tránh chỉ bảo vệ một controller rồi bỏ sót các đường gọi khác.

Không nhất thiết lặp lại cùng một lệnh kiểm tra ở mọi tầng. Cần xác định tầng nào bảo đảm điều kiện nào và không để một đường thực thi bỏ qua điều kiện bắt buộc.

Ngữ cảnh actor truyền giữa các dịch vụ phải được bảo vệ theo cơ chế tin cậy của hệ thống. Một header tự đặt role=Admin từ client không trở thành quyền chỉ vì service nhận được nó.

## 9. Scope OAuth có phải coarse permission không?

Một scope như invoices.read hoặc reports.export thường được sử dụng để giới hạn khả năng mà access token đại diện. Nó có thể tham gia kiểm tra chức năng ở resource server.

OAuth 2.0 quy định scope là những chuỗi có ý nghĩa do authorization server xác định; không có một danh sách quyền nghiệp vụ chung áp dụng cho mọi API. [RFC 6749, mục 3.3](https://www.rfc-editor.org/rfc/rfc6749.html#section-3.3).

Vì vậy, cần phân biệt:

~~~text
Token được dùng cho API và scope phù hợp
khác với
người hoặc ứng dụng được quyền trên mọi hóa đơn được yêu cầu.
~~~

Trong một luồng đại diện người dùng, quyết định có thể còn phụ thuộc quyền của người dùng và phạm vi ủy quyền cho ứng dụng. Với workload tự hành động, phải xét grant của chính workload theo tenant và resource scope được cấp.

Không yêu cầu mọi access token phải chứa toàn bộ role, ownership hoặc graph quan hệ. Có thể tra thêm dữ liệu ở phía resource server theo thiết kế.

Tên scope cũng không thay thế kiểm tra tính hợp lệ và đối tượng nhận của token. Một token có chuỗi invoices.read từ nguồn không được tin cậy không phải bằng chứng phân quyền.

## 10. Hai loại lỗi mà coarse check dễ bị hiểu nhầm

### 10.1. Vượt quyền ở cấp chức năng

Nếu một người chỉ được đọc hóa đơn nhưng vẫn gọi được endpoint quản lý thành viên hoặc endpoint xuất dành riêng cho nhóm khác, hệ thống đã thiếu hoặc áp dụng sai kiểm tra quyền chức năng.

OWASP mô tả truy cập những chức năng không được phép, đặc biệt chức năng quản trị, trong Broken Function Level Authorization. [OWASP API5:2023](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/).

Không suy ra endpoint an toàn chỉ từ đường dẫn có chữ admin. Cũng không mặc định tất cả HTTP GET đều là đọc ít nhạy cảm hoặc tất cả POST đều có cùng permission.

### 10.2. Vượt quyền trên đối tượng

Lan được sử dụng endpoint đọc hóa đơn nhưng chỉ được đọc hóa đơn được giao. Nếu thay invoiceId thành một hóa đơn của người khác mà vẫn được đọc, coarse gate có thể đã hoạt động đúng còn kiểm tra object bị thiếu.

OWASP mô tả rủi ro thao túng object ID để truy cập đối tượng không được phép trong Broken Object Level Authorization. [OWASP API1:2023](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

ID ngẫu nhiên hoặc khó đoán không thay thế quyền object. Khi người dùng biết ID qua email, log hoặc một liên kết, backend vẫn phải xử lý đúng phạm vi.

Hai nhóm lỗi cần được kiểm tra riêng. Chặn được endpoint quản trị không chứng minh mọi object bên trong endpoint đọc đều được bảo vệ.

## 11. Khi nào nên dùng quyền coarse?

### 11.1. Những trường hợp phù hợp

Coarse-grained access phù hợp khi các đối tượng trong phạm vi có cùng yêu cầu quyền đối với nhóm được cấp, hoặc khi cần một lớp điều kiện chung trước các kiểm tra khác.

Ví dụ:

- Nhân viên đang hoạt động được đọc một bộ hướng dẫn nội bộ dùng chung.
- Một nhóm kế toán được đọc toàn bộ báo cáo tiêu chuẩn của tenant mình phụ trách.
- Chỉ operator được mở công cụ vận hành, sau đó từng thao tác vẫn có chính sách riêng.
- Một tài khoản dịch vụ được dùng chức năng tạo báo cáo trong một tập tenant được cấp.

Điều cần xác nhận là phạm vi rộng có phản ánh yêu cầu thật hay chỉ là giải pháp tạm vì hệ thống chưa lưu ownership hoặc phân công.

### 11.2. Những dấu hiệu cần bổ sung độ chi tiết

Nếu câu trả lời cho một trong những câu hỏi sau khác nhau giữa các tài nguyên hoặc ngữ cảnh, quyền chức năng đơn lẻ có thể chưa đủ:

~~~text
Có được đọc hồ sơ của khách hàng khác không?
Có được chỉnh sửa sau khi hồ sơ đã duyệt không?
Có được xem số tài khoản đầy đủ không?
Có được thực hiện thay người dùng khác không?
Có được truy cập dữ liệu ở tenant khác không?
Có được xuất cùng dữ liệu mà mình được xem từng bản ghi không?
~~~

Không nhất thiết giải quyết tất cả bằng cách tạo thêm hàng trăm role. Có thể giữ role cho chức năng và dùng điều kiện dữ liệu, grant theo phạm vi hoặc quan hệ tài nguyên cho phần còn lại.

### 11.3. Chi phí và lợi ích cần cân bằng

| Khía cạnh | Quyền coarse rõ phạm vi | Quyền chi tiết hơn |
| --- | --- | --- |
| Hiểu danh mục chức năng | Thường dễ đọc và giao tiếp | Cần thêm diễn giải về dữ liệu và điều kiện |
| Số lượng assignment | Có thể gom theo nhóm công việc | Có thể cần grant hoặc quan hệ riêng |
| Khả năng diễn đạt ngoại lệ | Hạn chế nếu chỉ có vài cờ quyền | Biểu diễn khác biệt giữa các object hoặc ngữ cảnh |
| Nguy cơ cấp quá rộng | Cao nếu phạm vi không được mô tả | Vẫn tồn tại nếu policy hoặc dữ liệu sai |
| Kiểm thử | Tập trung ma trận chức năng và phạm vi | Cần thêm tổ hợp đối tượng, thuộc tính và quan hệ |
| Vận hành | Cần quản lý role, scope và thu hồi | Còn phải quản lý dữ liệu phục vụ quyết định |

Không thể kết luận mọi coarse check đều nhanh hoặc mọi fine check đều chậm. Một kiểm tra role vẫn có thể phải gọi nhiều nguồn từ xa; một policy chi tiết có thể chạy trên snapshot cục bộ hoặc được đẩy vào truy vấn dữ liệu.

Chọn độ hạt theo yêu cầu quyền trước, rồi tối ưu cách thực thi mà vẫn giữ ngữ nghĩa.

## 12. Cache và vòng đời quyền chức năng

### 12.1. Snapshot permission không có hiệu lực vô thời hạn

Một access token hoặc session có thể chứa role tại thời điểm phát hành. Nếu người dùng đổi công việc hoặc bị gỡ khỏi tenant, snapshot đó có thể không còn phản ánh quyền hiện tại.

Cần quy định độ mới được chấp nhận, thời hạn cache và cách xử lý thu hồi. Chữ ký token chứng minh nguồn phát hành và tính toàn vẹn theo cơ chế đã kiểm chứng; nó không chứng minh mọi assignment bên ngoài chưa thay đổi sau đó.

Với thao tác nhạy cảm như điều chỉnh hoặc xuất dữ liệu lớn, thiết kế có thể cần kiểm tra trạng thái mới hơn hoặc yêu cầu mức bảo đảm phiên phù hợp. Điều này là một phần chính sách của thao tác, không tự được cung cấp bởi coarse permission.

### 12.2. Không cache nhầm kết quả gate thành quyền tài nguyên

Một khóa coarse gate có thể phụ thuộc:

~~~text
subject identity
+ tenant scope
+ permission required
+ authorization state version
+ những điều kiện ngữ cảnh được dùng trong gate
~~~

Kết quả đó chỉ áp dụng cho gate. Không dùng nó như quyền đọc một invoiceId bất kỳ nếu chính sách dữ liệu còn yêu cầu kiểm tra phân công.

Cache của quyết định object cần tính thêm object và mọi đầu vào ảnh hưởng đến quyết định. Hai lớp cache có phạm vi khác nhau và cần được đặt tên, ghi log đúng ý nghĩa.

Cũng cần quản lý quyền mới được cấp: một cache Deny quá lâu có thể khiến người dùng tiếp tục bị chặn. TTL là một giới hạn thời gian, không tự bảo đảm cập nhật tức thời.

### 12.3. Cấp quyền và review định kỳ

Quyền coarse thường mở một tập chức năng đáng kể, nên quá trình cấp cần có căn cứ công việc và phạm vi rõ ràng.

Có thể ghi nhận ai cấp role, tenant được áp dụng, lý do, thời điểm và thời hạn nếu có. Khi nhân viên chuyển bộ phận, cần xem lại những role tích lũy, thay vì chỉ thêm role mới.

Không dùng một role Admin duy nhất làm cách xử lý mọi yêu cầu thiếu quyền. Những yêu cầu lặp lại có thể cho thấy mô hình cần tách action hoặc data scope, chứ không phải người dùng cần quyền toàn hệ thống.

## 13. Mở rộng từ coarse sang chính sách chi tiết

Giả sử phiên bản đầu cho BillingViewer đọc mọi hóa đơn của tenant. Sau đó sản phẩm cần nhân viên xử lý chỉ được đọc hóa đơn được giao, còn kế toán tổng hợp vẫn đọc toàn tenant.

Một hướng thay đổi tham khảo:

1. Mô tả chính xác hai phạm vi dữ liệu: được giao và toàn tenant.
2. Xác định dữ liệu nguồn cho quan hệ phân công và grant đọc toàn tenant.
3. Giữ kiểm tra invoice.read làm điều kiện chức năng nếu còn phù hợp.
4. Bổ sung policy dữ liệu vào mọi đường đọc liên quan.
5. Kiểm tra danh sách, xem chi tiết, file đính kèm, tìm kiếm và tác vụ export.
6. Xem lại các grant cũ trước khi gán chúng vào phạm vi mới.
7. Theo dõi cả các quyền bị thu hẹp có chủ đích và các trường hợp nghiệp vụ hợp lệ bị chặn.

Không thể thu hẹp quyền thực sự bằng cách chỉ thay nhãn role hoặc bổ sung một trường scope nhưng không dùng nó khi truy vấn.

Cũng không nên coi mọi grant cũ đều đã được phê duyệt cho quyền toàn tenant mới nếu ý nghĩa cũ vốn không rõ ràng. Cần xác định lại căn cứ và phạm vi theo yêu cầu đã thống nhất.

### 13.1. Giữ sự nhất quán giữa các đường truy cập

Nếu trang danh sách đã lọc theo phân công nhưng endpoint xem chi tiết vẫn chỉ kiểm tra role, người dùng có thể bỏ qua danh sách và gọi trực tiếp.

Nếu xem chi tiết đã kiểm tra phân công nhưng export vẫn lấy toàn tenant, quyền dữ liệu mới chưa được thực thi đồng nhất.

Có thể xây dựng một thành phần policy dùng chung hoặc đẩy điều kiện vào truy vấn phù hợp. Dù cách triển khai nào, cần bảo đảm chính sách áp dụng trên mọi đường thực hiện thao tác.

### 13.2. Không đánh mất ngữ nghĩa khi kết hợp policy

Một mẫu kết hợp trong ví dụ là:

~~~text
quyền chức năng
AND tenant scope hợp lệ
AND chính sách dữ liệu
AND điều kiện thực thi bổ sung
~~~

Nếu đổi một phép AND thành OR, người có role chức năng có thể bỏ qua điều kiện dữ liệu hoặc người đúng phân công có thể bỏ qua quyền chức năng. Việc kết hợp phải phản ánh yêu cầu nghiệp vụ, không chỉ ghép những boolean thuận tiện.

Một số hệ thống có nhiều grant thay thế hợp lệ, chẳng hạn owner hoặc người được giao. Các nhánh ấy có thể được kết hợp bằng OR bên trong policy dữ liệu, trong khi những ràng buộc bắt buộc như tenant vẫn nằm ngoài theo thiết kế.

## 14. Kiểm thử và audit

### 14.1. Ma trận kiểm thử tham khảo

Các kết quả dưới đây là kỳ vọng của bài học, không phải báo cáo thực thi một ứng dụng cụ thể.

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Chưa xác thực gọi chức năng được bảo vệ | Không được thực hiện thao tác |
| Có danh tính nhưng thiếu invoice.read | Không vượt gate đọc |
| Có invoice.read nhưng thiếu invoice.export | Không vượt gate export nếu không có quy tắc bao hàm |
| Role chỉ được gán ở tenant A | Không dùng role ấy trong tenant B |
| Lan có invoice.read, hóa đơn không được giao | Policy dữ liệu từ chối theo phạm vi của Lan |
| Minh được đọc toàn tenant A | Đọc được hóa đơn hợp lệ của A theo grant đã cấp |
| Minh yêu cầu hóa đơn của B | Không sử dụng grant A để đọc B |
| Có quyền mở menu nhưng thiếu action thực sự | Backend vẫn chặn action |
| Thay HTTP method hoặc dùng route khác | Không bỏ qua quyền của thao tác thực sự |
| Route mới chưa có ánh xạ permission | Không tự được cấp quyền |
| Snapshot quyền không tải được | Không chuyển lỗi thành Allow |
| Role bị thu hồi nhưng cache còn dữ liệu cũ | Hết hiệu lực theo cam kết freshness |
| Endpoint danh sách được lọc đúng | Endpoint chi tiết và export vẫn được kiểm tra riêng |
| Workload gọi API | Dùng grant đúng của workload và phạm vi ủy quyền |
| Chỉ có tenant membership | Không tự có toàn bộ chức năng nghiệp vụ |

Kiểm thử cần đi qua backend, không chỉ kiểm tra menu được ẩn. Các ca âm có giá trị vì chúng chỉ ra chính xác nơi quyền rộng phải dừng lại.

### 14.2. Ghi log đúng tầng quyết định

Một sự kiện coarse gate có thể ghi:

~~~json
{
  "request_id": "request-218",
  "subject_id": "user-lan",
  "tenant_id": "tenant-a",
  "required_permission": "invoice.read",
  "authorization_version": "permissions-42",
  "stage": "FUNCTION_GATE",
  "result": "PASSED",
  "next_step": "DATA_POLICY"
}
~~~

Đây là schema minh họa. PASSED không đồng nghĩa invoice đã được trả về.

Một sự kiện thực thi cuối cần phản ánh tài nguyên, action, kết quả policy dữ liệu và hành vi thực sự. Khi Lan vượt gate nhưng bị từ chối vì không được giao hóa đơn, log không nên nói “đã cho phép đọc” chỉ dựa trên sự kiện đầu.

Nguyên nhân thiếu permission và lỗi nguồn quyền nên được phân biệt nội bộ. Không ghi access token, mật khẩu hoặc dữ liệu hóa đơn đầy đủ vào log chỉ để giải thích một coarse decision.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Coi đăng nhập là được vào mọi chức năng | Người dùng gọi được action không được cấp | Kiểm tra permission chức năng |
| Coi role Admin là toàn quyền ở mọi phạm vi | Quyền tenant hoặc nghiệp vụ bị mở rộng | Gắn role với scope và action rõ ràng |
| Vượt coarse gate là được đọc mọi object | Bỏ qua ownership hoặc phân công | Áp dụng chính sách dữ liệu theo yêu cầu |
| Chỉ ẩn menu hoặc nút | Có thể gọi trực tiếp endpoint | Thực thi ở backend |
| Dùng một wildcard cho mọi tính năng tương lai | Grant cũ tự nhận thêm quyền nhạy cảm | Review phạm vi khi bổ sung action |
| Chỉ bảo vệ đường gọi qua gateway | Đường nội bộ hoặc job bỏ qua kiểm tra | Bảo vệ mọi đường thực thi liên quan |
| Cache permission như một quyền object | Kết quả bị dùng quá phạm vi | Phân biệt gate cache và object decision |
| Gộp lỗi hạ tầng với thiếu quyền | Khó điều tra và có thể xử lý sai | Giữ hợp đồng kết quả và lỗi rõ ràng |

## 16. Bài tập vận dụng

### Bài 1: Quyền đọc và quyền xuất

Lan có invoice.read, không có invoice.export. Nút Export bị ẩn nhưng một URL export vẫn gọi được nếu sửa request.

Xác định đây là thiếu kiểm tra ở tầng nào và vì sao việc đã kiểm tra quyền đọc hóa đơn chưa đủ để cấp quyền xuất.

### Bài 2: Cùng role, khác tài nguyên

Lan có role đọc hóa đơn trong A. Một hóa đơn thuộc A được giao cho Lan, một hóa đơn khác được giao cho Hà.

Hãy xác định khi nào coarse policy đủ để cho Lan đọc cả hai, và khi nào bắt buộc phải thêm kiểm tra phân công. Câu trả lời phải dựa vào nghĩa của grant, không dựa vào tên role đơn lẻ.

### Bài 3: Một permission quá rộng

Hệ thống dùng billing.manage cho xem hóa đơn, điều chỉnh, hoàn tiền và đổi tài khoản thanh toán. Một nhóm nhân viên chỉ cần xem và xuất báo cáo.

Đề xuất cách tách action và phạm vi phù hợp, đồng thời giải thích vì sao không cần tạo một role riêng cho từng hóa đơn.

### Bài 4: Gate pass nhưng request bị từ chối

Audit cho thấy gate invoice.read của Lan là PASSED, nhưng response không trả dữ liệu vì hóa đơn thuộc tenant khác.

Giải thích vì sao hai kết quả không mâu thuẫn. Xác định những trường thông tin cần có để phân biệt quyền chức năng, phạm vi dữ liệu và kết quả thực thi cuối.

Coarse-grained access có giá trị khi quyền chức năng và phạm vi của nó được định nghĩa đúng. Trong những luồng cần phân biệt tài nguyên hoặc ngữ cảnh, hãy dùng kết quả coarse như một điều kiện của quyết định đầy đủ, rồi thực thi đúng chính sách trên dữ liệu thực sự được sử dụng.
