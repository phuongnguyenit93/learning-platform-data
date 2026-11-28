# Policy enforcement point

## 1. PEP là nơi quyết định quyền trở thành hành vi thực tế

Policy enforcement point (PEP) là thành phần kiểm soát đường truy cập tài nguyên và thực thi quyết định phân quyền. Khi người dùng yêu cầu xem một hóa đơn, PEP phải giữ yêu cầu lại, lấy quyết định phù hợp, rồi chỉ cho dữ liệu đi qua nếu các điều kiện cấp quyền đã được đáp ứng. NIST mô tả PEP trong ngữ cảnh ABAC là nơi thực thi quyết định do policy decision point đưa ra. Xem [định nghĩa PEP của NIST](https://csrc.nist.gov/glossary/term/policy_enforcement_point).

Một phép kiểm tra trả về kết quả “được phép” chưa đủ để bảo vệ tài nguyên. Nếu ứng dụng vẫn đọc và trả dữ liệu khi kết quả là từ chối, gọi nhầm tài nguyên, hoặc có một đường khác không đi qua kiểm tra, hệ thống vẫn có lỗi phân quyền. Giá trị của PEP nằm ở khả năng ràng buộc quyết định với đúng hành động sẽ thực hiện.

Trong module nền tảng IAM, PEP kết nối danh tính đã xác thực với quyền truy cập cụ thể. Phiên đăng nhập, MFA, vai trò, thuộc tính tổ chức và trạng thái tài khoản là dữ kiện đầu vào; PEP dùng kết quả phân quyền để điều khiển một thao tác như đọc hồ sơ, sửa quyền hay xuất báo cáo.

Sau bài này, người học cần có thể:

- Xác định PEP trên đường đi của một yêu cầu.
- Phân biệt trách nhiệm của PEP với PDP và các nguồn thuộc tính.
- Chọn vị trí thực thi phù hợp với độ chi tiết của tài nguyên.
- Xử lý quyết định từ chối, lỗi đánh giá và nghĩa vụ đi kèm quyết định.
- Nhận diện đường truy cập bỏ qua PEP, quyết định hết hạn và thay đổi quyền giữa lúc kiểm tra với lúc sử dụng.

## 2. Quan hệ giữa PEP, PDP, PIP và PAP

ABAC đánh giá quyền dựa trên thuộc tính của chủ thể, tài nguyên, thao tác và điều kiện môi trường. Đây là cách mô tả nền tảng trong [NIST SP 800-162](https://csrc.nist.gov/pubs/sp/800/162/upd2/final). Với một ứng dụng cụ thể, có thể phân chia trách nhiệm như sau:

| Thành phần | Câu hỏi hoặc công việc chính | Ví dụ trong dịch vụ hóa đơn |
|---|---|---|
| PEP — Policy Enforcement Point | Thao tác có thực sự được đi tiếp không? | Chặn việc trả hóa đơn trước khi có quyền đọc |
| PDP — Policy Decision Point | Với ngữ cảnh này, policy cho kết quả gì? | Đánh giá nhân viên có cùng tenant và phòng ban với hóa đơn |
| PIP — Policy Information Point | Thuộc tính cần để đánh giá lấy từ đâu? | Nguồn trạng thái nhân viên, metadata hóa đơn, mức bảo đảm phiên |
| PAP — Policy Administration Point | Ai quản lý và phát hành policy? | Quy trình duyệt, kiểm thử và triển khai bộ policy |

Bảng trên là cách phân vai để thiết kế ví dụ của bài. Bốn vai trò không bắt buộc là bốn tiến trình hoặc bốn sản phẩm riêng. Một thư viện trong cùng JVM có thể vừa chứa bộ đánh giá policy vừa được gọi bởi lớp PEP. Một dịch vụ từ xa cũng có thể cung cấp PDP cho nhiều ứng dụng.

Việc tách vai trò giúp xác định lỗi:

- Policy đúng nhưng API không chặn yêu cầu bị từ chối: kiểm tra phần thực thi.
- API chặn đúng theo kết quả nhưng nhân viên sai phòng ban vẫn được cho phép: kiểm tra policy và dữ kiện đánh giá.
- Kết quả thay đổi bất thường vì thuộc tính tenant lấy từ request body: kiểm tra nguồn và cách dựng ngữ cảnh.
- Policy mới không xuất hiện ở các dịch vụ: kiểm tra quy trình phát hành và đồng bộ phiên bản.

PEP không nên sao chép toàn bộ luật nghiệp vụ của PDP thành một bộ if/else thứ hai. Tuy vậy, PEP vẫn phải biết hợp đồng của quyết định, những nghĩa vụ nó hỗ trợ và cách từ chối khi hợp đồng không được đáp ứng.

## 3. Ví dụ xuyên suốt: xem hóa đơn trong hệ thống nhiều tenant

Giả sử ứng dụng quản lý hóa đơn cho nhiều doanh nghiệp. Mỗi hóa đơn có các thuộc tính:

~~~text
id               = inv-2048
tenantId         = tenant-a
department       = finance
classification   = confidential
securityVersion  = 17
~~~

Người dùng Lan có danh tính đã được hệ thống xác thực:

~~~text
subjectId        = user-lan
tenantId         = tenant-a
department       = finance
accountStatus    = active
attributeVersion = 42
sessionAssurance = mfa
~~~

Luật ví dụ cho thao tác invoice:read:

~~~text
Cho phép khi:
  tài khoản đang active
  VÀ tenant của chủ thể bằng tenant của hóa đơn
  VÀ phòng ban của chủ thể bằng phòng ban của hóa đơn
  VÀ phiên đáp ứng mức bảo đảm cần cho mức phân loại tài liệu.

Nếu được đọc nhưng chưa có quyền xem mã số thuế:
  kèm nghĩa vụ MASK_TAX_ID.
~~~

Đây là policy minh họa của ứng dụng, không phải policy bắt buộc của một tiêu chuẩn. Một tổ chức khác có thể dùng quyền theo quan hệ dự án, phạm vi hợp đồng hoặc ủy quyền có thời hạn.

PEP trong ví dụ phải làm nhiều hơn việc kiểm tra Lan đã đăng nhập:

1. Nhận diện Lan từ ngữ cảnh xác thực đáng tin cậy.
2. Lấy thuộc tính hiện hành và metadata của đúng hóa đơn.
3. Yêu cầu đánh giá đúng thao tác invoice:read.
4. Chặn mọi kết quả không đủ điều kiện cấp quyền.
5. Nếu có nghĩa vụ che mã số thuế, biến đổi dữ liệu trước khi xuất ra ngoài.
6. Bảo đảm dữ liệu trả về vẫn tương ứng với tài nguyên và phiên bản bảo mật đã được kiểm tra.

Nếu người dùng sửa URL từ inv-2048 sang inv-9000, PEP phải dựng yêu cầu mới cho inv-9000. Quyền xem một hóa đơn không tự chuyển thành quyền xem mọi hóa đơn trong cùng endpoint.

## 4. Luồng yêu cầu đi qua PEP

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Lớp xác thực
    participant E as PEP tại dịch vụ
    participant I as Nguồn thuộc tính
    participant D as PDP
    participant R as Kho tài nguyên

    C->>A: Yêu cầu đọc hóa đơn
    A->>E: Danh tính đã xác minh và invoiceId
    E->>I: Lấy thuộc tính và metadata cần thiết
    I-->>E: Ngữ cảnh tin cậy và phiên bản
    E->>D: Subject, resource, action, environment
    D-->>E: Quyết định và nghĩa vụ
    alt Có Permit hợp lệ và thực thi được nghĩa vụ
        E->>R: Đọc đúng tài nguyên, ràng buộc phiên bản
        R-->>E: Dữ liệu
        E->>E: Che trường dữ liệu và kiểm tra trước khi xuất
        E-->>C: Kết quả được phép công bố
    else Từ chối, lỗi hoặc nghĩa vụ không thực thi được
        E-->>C: Không cấp dữ liệu
    end
~~~

Nguồn thuộc tính trong sơ đồ là một vai trò logic. Ứng dụng có thể lấy metadata tài nguyên trước khi hỏi PDP, hoặc PDP có thể gọi nguồn thuộc tính của nó. Cần quy định rõ nơi chịu trách nhiệm về độ mới, tính tin cậy và lỗi khi thiếu dữ kiện.

Đọc metadata để quyết định quyền khác với công bố toàn bộ dữ liệu cho client. Một dịch vụ có thể cần biết tenant và mức phân loại của bản ghi trước khi phân quyền. Chỉ lấy phần metadata cần thiết, giữ nó bên trong ranh giới tin cậy và áp dụng cách xử lý không làm lộ sự tồn tại của tài nguyên ngoài ý muốn.

Với thao tác thay đổi dữ liệu, thứ tự phải bảo đảm việc ghi không xảy ra trước khi được cấp quyền. Ghi xong rồi kiểm tra và cố gắng hoàn tác không tương đương với kiểm soát quyền trước thao tác: thông báo, sự kiện, thanh toán hoặc tác động bên ngoài có thể đã phát sinh.

## 5. Đặt PEP ở đâu?

Vị trí phù hợp phụ thuộc vào dữ kiện mà nơi đó nhìn thấy và tài nguyên mà nó thực sự kiểm soát.

| Vị trí | Có thể kiểm soát tốt | Giới hạn cần nhận diện |
|---|---|---|
| Frontend | Trạng thái giao diện và cách hiển thị chức năng | Client có thể bị sửa hoặc bị bỏ qua |
| API gateway | Tuyến API, phương thức, danh tính đầu vào, giới hạn truy cập thô | Có thể không biết owner hoặc trạng thái hiện hành của từng bản ghi |
| Filter hoặc middleware của backend | Các yêu cầu qua cùng chuỗi xử lý | Đường gọi nội bộ hoặc tác vụ nền có thể không đi qua middleware |
| Lớp service nghiệp vụ | Hành động nghiệp vụ và metadata tài nguyên cụ thể | Cần bảo đảm caller không đi thẳng vào kho dữ liệu |
| Cơ sở dữ liệu hoặc kho đối tượng | Hàng dữ liệu, đối tượng hoặc thao tác ở tầng lưu trữ | Phải cấu hình danh tính, quyền kết nối và quyền đặc biệt phù hợp |

Ẩn nút “Xem hóa đơn” giúp trải nghiệm người dùng nhất quán nhưng không tạo ra rào cản phía server. Backend vẫn phải kiểm tra yêu cầu được gửi trực tiếp.

Một gateway có thể yêu cầu token hợp lệ trước khi cho đi vào InvoiceService. Dịch vụ tiếp tục kiểm tra quyền đọc đúng hóa đơn. Hai lần kiểm tra có phạm vi khác nhau: qua cửa dịch vụ và truy cập một đối tượng nghiệp vụ.

Cũng cần xét đường đi tới dữ liệu sau lần kiểm tra đầu tiên. Nếu API trả một URL tải tệp công khai tồn tại vô thời hạn, kiểm soát tại API không còn chi phối những lần tải sau. Với URL ký có thời hạn, phải xác định rõ tài nguyên, phương thức, thời gian sống và khả năng thu hồi; quyền sở hữu URL đó có thể trở thành khả năng truy cập dữ liệu trong thời gian hiệu lực.

Khi dùng nhiều PEP, nên mô tả rõ tầng nào sở hữu kiểm tra nào. Trong thiết kế minh họa này, mọi tầng bắt buộc trên đường truy cập đều phải cho phép; một tầng cho phép không được vô hiệu hóa sự từ chối ở tầng khác.

## 6. Dựng ngữ cảnh tin cậy trước khi hỏi quyền

Một PDP không thể tự biến thuộc tính giả thành sự thật. Nếu PEP gửi tenantId do client tự khai như thể đó là tenant đã được xác minh, policy so sánh tenant dù viết đúng vẫn có thể cho kết quả sai.

| Dữ kiện | Nguồn phù hợp trong ví dụ | Không dùng trực tiếp làm bằng chứng quyền |
|---|---|---|
| subjectId | Principal do lớp xác thực tạo | subjectId trong JSON request |
| Trạng thái tài khoản | Dịch vụ danh tính hoặc bản sao có cơ chế cập nhật | Cờ active do client gửi |
| Tenant được phép hoạt động | Danh tính và membership đã xác minh | Chỉ header X-Tenant-Id |
| Tenant và owner của hóa đơn | Metadata do backend kiểm soát | Thuộc tính tài nguyên trong request body |
| Mức bảo đảm phiên | Kết quả xác thực có nguồn gốc được kiểm chứng | Header X-MFA: true |
| IP nguồn, trạng thái thiết bị | Chuỗi proxy và nguồn quản lý đã thiết lập tin cậy | Header bất kỳ từ Internet |

Client vẫn có thể chọn tenant muốn làm việc, nhưng PEP phải xác minh lựa chọn đó nằm trong membership được cấp. Giá trị lựa chọn và bằng chứng quyền là hai dữ kiện khác nhau.

JWT đã xác minh chữ ký cũng không tự giải quyết mọi vấn đề về độ mới. Thuộc tính trong token có thể phản ánh thời điểm phát hành, trong khi tài khoản đã bị khóa hoặc membership vừa bị thu hồi. Ứng dụng cần chính sách về tuổi token, dữ liệu trạng thái bổ sung và giới hạn thời gian chấp nhận thay đổi chưa đồng bộ.

Một hợp đồng thuộc tính nên nêu rõ:

- Tên và kiểu dữ liệu, ví dụ tenantId là chuỗi chuẩn hóa, không phải danh sách tùy ý.
- Nguồn cấp và nơi kiểm chứng.
- Thời điểm lấy, phiên bản hoặc thời hạn sử dụng.
- Hành vi khi thiếu, sai kiểu hoặc có nhiều giá trị mâu thuẫn.
- Dữ liệu nào được gửi tới PDP và dữ liệu nào phải giữ tại dịch vụ.

Không tự biến “không có thuộc tính department” thành “mọi department”, hoặc biến lỗi tra cứu membership thành tenant mặc định. Khi một policy cần thuộc tính mà hệ thống chưa có, đó phải là trạng thái được xử lý rõ ràng.

## 7. Hợp đồng giữa PEP và PDP

Một lời gọi boolean như isAllowed(user, resource) thường không thể diễn đạt đủ yêu cầu khi hệ thống có nhiều tenant, nhiều thao tác và nghĩa vụ xử lý dữ liệu.

Đây là yêu cầu JSON minh họa do ứng dụng tự định nghĩa; nó không phải request chuẩn XACML:

~~~json
{
  "requestId": "authz-8f42",
  "subject": {
    "id": "user-lan",
    "tenantId": "tenant-a",
    "attributeVersion": 42,
    "sessionAssurance": "mfa"
  },
  "resource": {
    "type": "invoice",
    "id": "inv-2048",
    "tenantId": "tenant-a",
    "securityVersion": 17
  },
  "action": "invoice:read",
  "environment": {
    "purpose": "interactive-view",
    "deviceAssessmentVersion": 9
  }
}
~~~

Phản hồi minh họa:

~~~json
{
  "requestId": "authz-8f42",
  "decision": "Permit",
  "policyVersion": "invoice-policy-r7",
  "contextFingerprint": "fingerprint-of-canonical-authorization-input",
  "validUntil": "2026-11-26T04:00:30Z",
  "obligations": [
    {
      "id": "MASK_TAX_ID",
      "parameters": {}
    }
  ]
}
~~~

Các trường requestId, contextFingerprint và validUntil là lựa chọn thiết kế của ví dụ. Không được mặc định rằng mọi PDP đều trả các trường này hoặc áp đặt cùng định dạng thời hạn.

PEP cần xác minh phản hồi thuộc đúng yêu cầu, đúng phiên bản hợp đồng và đến từ PDP được tin cậy. Fingerprint chỉ hữu ích khi hai bên thống nhất cách chuẩn hóa đầu vào và đưa vào đó tất cả dữ kiện ảnh hưởng đến quyền. Một giá trị hash không xác thực người gửi và không thay thế kênh liên lạc được bảo vệ.

Không tái sử dụng Permit khi hành động đổi từ invoice:read sang invoice:export, khi resourceId đổi, hoặc khi ngữ cảnh quyền đã thay đổi. Việc gắn một requestId đơn lẻ không đủ nếu nó chỉ dùng để ghi log mà không được kiểm tra tương quan thực sự.

Nếu PDP ở ngoài tiến trình, adapter của PEP còn phải kiểm tra kiểu dữ liệu, giới hạn kích thước phản hồi, số lượng nghĩa vụ và các giá trị enum. HTTP 200 chỉ nói lời gọi ở tầng vận chuyển đã thành công; nó không có nghĩa người dùng được cấp quyền.

## 8. Chuyển kết quả đánh giá thành hành vi

XACML 3.0 có bốn kết quả quyết định: Permit, Deny, NotApplicable và Indeterminate. Tiêu chuẩn còn phân biệt cách PEP xử lý theo bias; deny-biased PEP chỉ cấp quyền khi có Permit và có thể thực hiện các obligation đi kèm. Advice là thông tin bổ sung có thể bỏ qua. Xem [OASIS XACML 3.0, mục 7.2 và 5.48](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html).

Trong dịch vụ hóa đơn của bài, ta chọn hợp đồng thực thi theo hướng mặc định không cấp quyền:

| Kết quả hoặc tình huống | Hành vi của PEP trong ví dụ |
|---|---|
| Permit, còn hiệu lực, ràng buộc đúng ngữ cảnh, nghĩa vụ được đáp ứng | Tiếp tục thao tác được chỉ định |
| Deny | Chặn thao tác |
| NotApplicable | Chặn vì chưa có căn cứ cấp quyền cho yêu cầu này |
| Indeterminate | Chặn; ghi nhận lỗi đánh giá để điều tra |
| Timeout, lỗi kết nối, phản hồi sai cấu trúc | Chặn; phân loại lỗi phụ thuộc |
| Permit nhưng không hiểu nghĩa vụ bắt buộc | Chặn |
| Permit nhưng sai request hoặc đã hết hiệu lực | Chặn |

Bảng này là quy ước của ứng dụng minh họa, không phải khẳng định mọi PEP hoặc mọi tiêu chuẩn đều có cùng chiến lược xử lý lỗi.

Không gộp tất cả thành “người dùng thiếu quyền” trong dữ liệu vận hành. Deny theo policy và lỗi PDP có thể đều không cấp dữ liệu, nhưng cách khắc phục khác nhau. API có thể ánh xạ việc thiếu quyền sang 403, còn lỗi phụ thuộc sang 503, tùy hợp đồng API và yêu cầu không tiết lộ thông tin. Khi chưa xác thực, ứng dụng xử lý tại lớp xác thực theo hợp đồng riêng.

Ở phía client, không trả thông tin policy nội bộ quá chi tiết. Ở phía vận hành, cần giữ mã lý do đủ để phân biệt sai quyền, thiếu thuộc tính và lỗi hệ thống.

## 9. Nghĩa vụ thực thi là một phần của quyền được cấp

Trong ví dụ hóa đơn, Permit kèm MASK_TAX_ID nghĩa là ứng dụng được công bố phiên bản hóa đơn đã che trường đó. Nếu PEP trả dữ liệu nguyên vẹn, kết quả thực tế không còn phù hợp với quyền được đánh giá.

Có thể chia công việc thực thi trong ứng dụng thành các giai đoạn:

| Giai đoạn | Ví dụ | Điều kiện phải bảo đảm |
|---|---|---|
| Trước thao tác | Kiểm tra bằng chứng MFA đủ mới | Không thực hiện thao tác nếu chưa đạt yêu cầu |
| Khi truy xuất hoặc biến đổi | Giới hạn hàng dữ liệu, che trường, thêm watermark | Không để dữ liệu thô thoát qua nhánh khác |
| Khi hoàn tất | Ghi nhận kết quả thực hiện, phát sự kiện kiểm toán | Có hợp đồng về độ bền và lỗi sau thao tác |

Cách chia này là mô hình triển khai của bài, không phải tên nhóm nghĩa vụ bắt buộc của XACML.

Nếu policy yêu cầu xác thực mạnh hơn, PEP có thể trả tín hiệu để bắt đầu quy trình step-up. Yêu cầu ban đầu vẫn bị giữ lại hoặc bị từ chối. Sau khi có bằng chứng xác thực mới, hệ thống phải đánh giá lại với ngữ cảnh mới; không đổi Permit chỉ vì client nói đã hoàn tất MFA.

Nếu nghĩa vụ yêu cầu ghi bằng chứng bền vững trước khi xuất dữ liệu, việc chỉ đặt sự kiện trong bộ nhớ rồi trả kết quả không đáp ứng hợp đồng đó. Có thể chọn kho audit bền vững, hàng đợi bền vững được chấp thuận hoặc một thiết kế giao dịch phù hợp. Ngược lại, log debug phục vụ quan sát thông thường không mặc nhiên phải trở thành điều kiện chặn mọi yêu cầu.

Danh sách nghĩa vụ được hỗ trợ nên có phiên bản và kiểm tra cả tham số. Biết tên MASK_TAX_ID nhưng bỏ qua một tham số bắt buộc mới cũng có thể làm sai ý nghĩa. Nghĩa vụ không nhận diện được không được tự hạ thành lời khuyên để tiếp tục cấp quyền.

## 10. Ví dụ Java: PEP tại ranh giới đọc hóa đơn

Đoạn mã sau minh họa vị trí kiểm soát trong lớp service. Đây là mã rút gọn để giải thích thiết kế; các kiểu repository, audit và adapter PDP là hợp đồng ứng dụng được mô tả bên dưới, chưa phải một ứng dụng có thể chạy độc lập.

~~~java
public final class InvoiceReadBoundary {

    private final InvoiceRepository invoices;
    private final PolicyClient policies;
    private final RequiredAudit audit;
    private final java.time.Clock clock;

    public InvoiceReadBoundary(
            InvoiceRepository invoices,
            PolicyClient policies,
            RequiredAudit audit,
            java.time.Clock clock) {
        this.invoices = invoices;
        this.policies = policies;
        this.audit = audit;
        this.clock = clock;
    }

    public InvoiceView read(
            VerifiedSubject subject,
            String invoiceId,
            TrustedEnvironment environment) {

        // Chỉ là metadata nội bộ, chưa trả dữ liệu cho client.
        InvoiceFacts facts =
                invoices.loadFacts(subject.tenantId(), invoiceId);

        AuthorizationInput input = new AuthorizationInput(
                subject,
                facts,
                "invoice:read",
                environment
        );

        final PolicyDecision decision;
        try {
            // Adapter kiểm tra cấu trúc, nguồn và tương quan phản hồi.
            decision = policies.evaluate(input);
        } catch (PolicyServiceUnavailable ex) {
            throw new AuthorizationUnavailable(
                    "Cannot evaluate invoice access", ex);
        }

        if (decision.effect() != Effect.PERMIT) {
            throw new AccessRejected("Invoice access not granted");
        }

        // equals có nghĩa so sánh toàn bộ snapshot bất biến của ví dụ.
        if (!input.equals(decision.boundInput())) {
            throw new AuthorizationUnavailable(
                    "Decision does not match authorization input");
        }

        if (!clock.instant().isBefore(decision.validUntil())) {
            throw new AuthorizationUnavailable("Decision expired");
        }

        java.util.Set<String> supported =
                java.util.Set.of("MASK_TAX_ID");

        for (String obligation : decision.obligations()) {
            if (!supported.contains(obligation)) {
                throw new AuthorizationUnavailable(
                        "Unsupported mandatory obligation");
            }
        }

        // Phải bảo đảm payload và metadata thuộc cùng securityVersion.
        // Khi không đáp ứng được, repository báo xung đột, không trả payload.
        InvoicePayload payload = invoices.loadAtSecurityVersion(
                facts.tenantId(),
                facts.invoiceId(),
                facts.securityVersion()
        );

        InvoiceView view = InvoiceView.from(payload);

        for (String obligation : decision.obligations()) {
            if ("MASK_TAX_ID".equals(obligation)) {
                view = view.withMaskedTaxId();
            }
        }

        // Đọc và biến đổi có thể mất thời gian: kiểm tra lại trước khi xuất.
        if (!clock.instant().isBefore(decision.validUntil())) {
            throw new AuthorizationUnavailable("Decision expired");
        }

        // Ứng dụng ví dụ yêu cầu ghi bền vững trước khi công bố.
        audit.recordDisclosureReady(
                input,
                decision.policyVersion()
        );

        // Audit cũng có thể làm phát sinh độ trễ.
        if (!clock.instant().isBefore(decision.validUntil())) {
            throw new AuthorizationUnavailable("Decision expired");
        }

        return view;
    }
}
~~~

Những hợp đồng cần hiểu để không đọc nhầm ý nghĩa đoạn mã:

- VerifiedSubject do lớp xác thực và tầng dựng ngữ cảnh đáng tin cậy tạo ra. Việc đặt tên kiểu là VerifiedSubject không tự xác minh dữ liệu; constructor và đường tạo đối tượng phải được kiểm soát.
- InvoiceFacts chứa invoiceId, tenantId, các thuộc tính bảo mật và securityVersion. Nó không chứa toàn bộ nội dung cần công bố.
- AuthorizationInput và các thành phần bên trong là snapshot bất biến có phép so sánh theo giá trị. Mọi thuộc tính thật sự được policy sử dụng phải có mặt trong snapshot hoặc được ràng buộc qua phiên bản của nguồn dữ liệu.
- PolicyDecision chứa effect, boundInput, policyVersion, validUntil và danh sách nghĩa vụ. Adapter từ chối phản hồi thiếu trường, sai kiểu hoặc không tương quan với yêu cầu. boundInput là cách minh họa ràng buộc, không phải định dạng giao thức bắt buộc.
- Trong ví dụ rút gọn, MASK_TAX_ID không có tham số. Nếu sản phẩm thêm tham số, adapter và PEP phải kiểm tra schema cùng ý nghĩa của chúng.
- InvoiceView là đối tượng đầu ra tách khỏi thực thể nội bộ. Phương thức withMaskedTaxId tạo đầu ra đã che dữ liệu; không để serializer vẫn nhìn thấy một field thô khác.
- RequiredAudit ghi bền vững một sự kiện “sẵn sàng công bố”, không khẳng định client đã thực sự nhận dữ liệu. Nếu ghi thất bại, phương thức không trả view.
- Các exception phải chấm dứt đường thực thi. Không có tầng phía trên bắt AccessRejected rồi gọi thẳng repository để “thử lại”.

Đoạn mã dùng một chính sách audit bắt buộc riêng cho luồng minh họa. Nó không có nghĩa mọi bản ghi log của hệ thống đều phải được ghi đồng bộ.

loadAtSecurityVersion là một yêu cầu về tính nhất quán, không chỉ là tên phương thức. Cách triển khai có thể đọc bản ghi kèm điều kiện phiên bản hoặc dùng transaction có cơ chế phù hợp. Nếu metadata đọc được ở phiên bản 17 nhưng payload đã mang phân loại bảo mật của phiên bản 18, repository phải báo xung đột để đánh giá lại.

Ví dụ này minh họa một thao tác đọc có đầu ra hữu hạn, không giải quyết hoàn chỉnh các yêu cầu về thu hồi quyền ngay tức thời hay bảo vệ luồng dữ liệu kéo dài. Điểm kiểm soát cuối trong service cũng chỉ là thời điểm bàn giao view cho tầng HTTP; nếu yêu cầu bảo mật áp dụng tới lúc ghi từng phần response, PEP phải phối hợp với tầng ghi response.

## 11. Khoảng cách giữa kiểm tra quyền và sử dụng tài nguyên

Time of check to time of use (TOCTOU) xuất hiện khi dữ kiện làm cơ sở cấp quyền thay đổi trước lúc hành động xảy ra.

Ví dụ:

~~~text
T0: Hóa đơn ở phòng finance, securityVersion = 17.
T1: PDP cấp Permit cho Lan dựa trên phiên bản 17.
T2: Hóa đơn chuyển sang nhóm restricted, securityVersion = 18.
T3: Backend đọc bản mới và trả cho Lan dựa trên Permit cũ.
~~~

PEP đã hỏi quyền nhưng hành vi thực tế không còn tương ứng với dữ kiện đã đánh giá.

Với thao tác ghi, một cách thiết kế là gắn thao tác với phiên bản đã kiểm tra:

~~~sql
UPDATE invoice
SET status = :new_status,
    security_version = security_version + 1
WHERE id = :invoice_id
  AND tenant_id = :tenant_id
  AND security_version = :authorized_security_version;
~~~

Câu SQL minh họa khóa lạc quan; nó không tự đánh giá toàn bộ policy ABAC. Nếu số hàng bị ảnh hưởng bằng 0, không được coi là cập nhật thành công. Ứng dụng cần xác định tài nguyên không tồn tại, bị đổi phiên bản hay không còn thuộc phạm vi; có thể đọc lại và đánh giá lại trong giới hạn retry được thiết kế.

securityVersion chỉ có giá trị khi mọi thay đổi liên quan đến quyền đều cập nhật nó. Nếu đổi owner hoặc classification mà giữ nguyên phiên bản, điều kiện so sánh không phát hiện được thay đổi cần thiết.

Ngoài thuộc tính tài nguyên, tài khoản và membership của chủ thể cũng có thể thay đổi. Nếu subject.attributeVersion chỉ được đọc lúc đầu, nó không tự chứng minh membership vẫn còn tại thời điểm commit. Độ chặt cần thiết phụ thuộc vào yêu cầu:

- Chấp nhận một cửa sổ thay đổi có giới hạn: định nghĩa rõ độ mới của thuộc tính và thời hạn quyết định.
- Yêu cầu cập nhật quyền phải có hiệu lực trước thao tác ghi quan trọng: cần kiểm tra phiên bản hoặc cơ chế phối hợp chặt hơn sát thời điểm thực thi.
- Phụ thuộc nhiều nguồn ngoài giao dịch: phải thiết kế giao thức nhất quán phù hợp, không tuyên bố một transaction cơ sở dữ liệu đã bao phủ mọi nguồn.

Đối với stream hoặc phiên tương tác dài, quyền cấp ở đầu kết nối không mặc nhiên cho phép truyền dữ liệu mãi mãi. Có thể phải đánh giá lại theo thời gian, sự kiện thay đổi quyền hoặc từng đơn vị dữ liệu; đồng thời xác định lượng dữ liệu có thể được gửi trước khi lệnh thu hồi tới nơi.

## 12. Bao phủ mọi đường truy cập: nguyên tắc complete mediation

Một PEP tốt vẫn có thể bị vô hiệu nếu có một lối khác đi tới cùng tài nguyên.

Trong ví dụ InvoiceService, hãy lập danh sách các đường truy cập:

~~~text
Web UI -> REST API -> invoice read boundary
Mobile -> REST API -> invoice read boundary
GraphQL resolver -> invoice read boundary
Scheduled export -> export authorization boundary
Queue consumer -> command authorization boundary
Admin endpoint -> privileged authorization boundary
Direct database connection -> database permissions and controls
~~~

Danh sách này là bản kiểm kê đường truy cập, không yêu cầu mọi nơi gọi cùng một hàm. Mỗi hành động có thể cần policy riêng. Điểm cần bảo đảm là đường nào cũng có cơ chế kiểm soát phù hợp trước khi tài nguyên bị đọc, thay đổi hoặc xuất ra.

Các lỗi thường gặp:

- REST controller có PEP nhưng GraphQL resolver gọi repository trực tiếp.
- Tác vụ xuất báo cáo sử dụng quyền của service account mà bỏ qua phạm vi dữ liệu người yêu cầu.
- API quản trị giả định rằng mọi người vào được mạng nội bộ đều có quyền quản trị.
- Consumer xử lý thông điệp chứa subjectId và tenantId như bằng chứng ủy quyền mà không kiểm chứng nguồn.
- API mới sao chép logic cũ nhưng quên lớp middleware phân quyền.
- Tài khoản ứng dụng có quyền truy cập kho lưu trữ quá rộng khiến lập trình viên vô tình bỏ qua ranh giới service.

Với kiến trúc Java, có thể giới hạn khả năng truy cập repository bằng cấu trúc package, API nội bộ và quyền truy cập thành phần. Những cơ chế này giúp giảm đường vòng, nhưng vẫn cần xem xét các đường thực thi thật sự trong runtime.

Đánh giá PEP bằng vị trí kiểm soát tài nguyên, không chỉ bằng số annotation bảo mật. Một annotation có thể không có hiệu lực trên đường gọi không đi qua interceptor tương ứng.

## 13. Danh tính workload, ủy quyền và nguy cơ dùng nhầm quyền

Một yêu cầu tới backend thường có ít nhất hai danh tính:

- Danh tính workload của dịch vụ đang gọi.
- Danh tính người dùng hoặc bên yêu cầu mà workload đang hành động thay mặt.

Ví dụ ReportService được phép gọi InvoiceService bằng chứng thư workload của nó. Điều đó chỉ chứng minh ReportService là caller được nhận diện. Nếu ReportService đang tạo báo cáo cho Lan, InvoiceService vẫn cần biết phạm vi dữ liệu và sự ủy quyền phù hợp cho công việc đó.

Nếu dùng mọi quyền của ReportService để trả dữ liệu bất kỳ cho Lan, dịch vụ có thể trở thành nơi thực hiện hành động vượt quyền theo yêu cầu của người dùng.

Ngữ cảnh phân quyền cho tình huống này có thể bao gồm:

~~~text
actorWorkload       = report-service
effectiveSubject    = user-lan
delegatedAction     = invoice:export
delegatedTenant     = tenant-a
delegationExpiresAt = thời hạn của quyền được ủy
jobId               = export-job-519
~~~

Đây là hợp đồng minh họa. Các giá trị phải được truyền bằng cơ chế đã xác thực và kiểm chứng, không phải bằng một header “on-behalf-of” mà mọi client đều tự đặt được.

PEP phải kiểm tra workload được phép sử dụng cơ chế ủy quyền đó, người dùng được phép thực hiện hành động, phạm vi đúng tenant và quyền ủy còn hiệu lực. Một lịch sử đã cấp quyền tạo job không tự thay thế quyền tải kết quả về sau.

Đối với công việc nền không đại diện cho người dùng, effectiveSubject có thể chính là danh tính workload với quyền được cấp riêng. Cần định nghĩa rõ trường hợp này để tránh tự gán người dùng giả hoặc âm thầm nâng mọi tác vụ nền thành quyền quản trị.

## 14. Cache quyết định và xử lý khi PDP không sẵn sàng

Cache có thể giảm độ trễ, nhưng một Permit được cache vẫn chỉ đúng trong ngữ cảnh và thời gian mà nó được đánh giá.

Một cache key chỉ gồm subjectId là không đủ. Lan có thể được đọc inv-2048 nhưng không được xuất inv-9000. Cache key minh họa cần phản ánh ít nhất các dữ kiện có liên quan:

~~~text
subjectId
subjectAttributeVersion
tenantId
resourceType + resourceId + resourceSecurityVersion
action
relevantEnvironmentFingerprint
policyVersion
~~~

Nếu policy còn sử dụng thuộc tính không có trong key hoặc trong dữ liệu phiên bản hóa, cache có nguy cơ trả quyết định sai. Có thể tắt cache cho một nhóm thao tác nhạy cảm hoặc khi chưa xác định được đầy đủ sự phụ thuộc.

Thời hạn cache cũng phải tính tới hạn của nguồn thuộc tính, quyết định và phiên xác thực. Nếu policy chỉ cho phép đến cuối ca làm việc, TTL cố định kéo dài qua thời điểm đó là sai ngay cả khi không có sự kiện thu hồi nào.

Cache Deny cũ có thể chặn người vừa được cấp quyền. Cache Permit cũ có thể tiếp tục cho truy cập sau khi thu hồi. Vì vậy, chọn TTL là quyết định về độ mới và tác động nghiệp vụ, không chỉ là tối ưu hiệu năng.

Khi PDP lỗi, ứng dụng ví dụ không mở quyền mặc định. Để tăng khả năng phục vụ mà vẫn có căn cứ cấp quyền, có thể thiết kế:

- Bộ đánh giá local sử dụng policy đã xác minh và dữ liệu còn trong giới hạn độ mới.
- Quyết định cache còn hiệu lực, gắn đúng ngữ cảnh và được phép dùng theo hợp đồng.
- Giới hạn thời gian chờ, circuit breaker và hàng đợi có hạn để bảo vệ tài nguyên hệ thống.

Không coi việc dùng lại một Permit đã hết hạn là cache hợp lệ. Circuit breaker mở cũng không có nghĩa thay kết quả bằng Permit.

Nếu tổ chức có quy trình truy cập khẩn cấp, đó phải là một luồng quyền riêng có người chịu trách nhiệm, phạm vi, thời hạn và kiểm toán. Không nên ẩn nó dưới nhánh catch lỗi mạng của PDP.

## 15. Danh sách, bulk API và xuất dữ liệu

Quyền truy cập một endpoint trả danh sách không tự động cho phép xem mọi phần tử mà endpoint truy vấn được.

Với GET /invoices, cần xác định policy đang cấp:

- Quyền gọi chức năng tìm kiếm.
- Phạm vi các hóa đơn được nhìn thấy.
- Những field có thể được công bố.
- Quyền xem tổng số kết quả hoặc thông tin tổng hợp.

Một thiết kế có thể dịch phạm vi quyền thành điều kiện truy vấn được kiểm soát tại server. Một thiết kế khác đánh giá từng tài nguyên theo lô. Dù dùng cách nào, cần giữ đúng ngữ nghĩa policy và ánh xạ từng kết quả về đúng tài nguyên.

Ví dụ, lọc dữ liệu sau khi đã phân trang có thể tạo ra trang thiếu phần tử và tổng số chứa thông tin của tenant khác. Đếm trước khi lọc cũng có thể làm lộ sự tồn tại của dữ liệu. Phải thiết kế quyền cho cả kết quả, metadata phân trang và dữ liệu tổng hợp.

Với bulk API, một quyết định cho inv-2048 không được áp cho toàn bộ mảng invoiceIds. Hợp đồng cần nêu rõ xử lý từng phần hay từ chối toàn bộ batch, thứ tự kết quả và cách xử lý khi một bản ghi đổi phiên bản.

Với export chạy nền, có ít nhất ba mốc cần xem xét:

1. Người dùng yêu cầu tạo tác vụ.
2. Tác vụ đọc và tạo tập dữ liệu.
3. Người dùng tải kết quả đã tạo.

Quyền tại mốc đầu tiên không tự giải quyết hai mốc sau. Có thể dùng ủy quyền giới hạn cho job, kiểm tra quyền lại tại lúc chạy và bảo vệ chính tệp kết quả. Cần định nghĩa hành vi nếu người dùng bị thu hồi quyền trong khi tác vụ đang đợi.

## 16. Quan sát hoạt động mà không làm lộ dữ liệu nhạy cảm

PEP là vị trí thuận lợi để ghi nhận hành vi thực thi vì nó biết quyết định nào đã được dùng và thao tác nào thật sự được cho đi tiếp.

Một sự kiện audit minh họa:

~~~json
{
  "event": "authorization_enforced",
  "requestId": "authz-8f42",
  "subjectId": "user-lan",
  "actorWorkload": "invoice-api",
  "resourceType": "invoice",
  "resourceId": "inv-2048",
  "action": "invoice:read",
  "effect": "Permit",
  "enforcementResult": "disclosure_ready",
  "policyVersion": "invoice-policy-r7",
  "resourceSecurityVersion": 17,
  "obligationIds": ["MASK_TAX_ID"]
}
~~~

Không ghi access token, cookie phiên hoặc toàn bộ payload hóa đơn để phục vụ việc giải thích một lần cấp quyền. Bản thân audit log có thể chứa thông tin danh tính và quan hệ với tài nguyên, nên cần kiểm soát người đọc và thời gian lưu.

Tách các trạng thái sau trong dữ liệu vận hành:

| Trạng thái | Ý nghĩa |
|---|---|
| Policy đánh giá Permit | PDP thấy ngữ cảnh đáp ứng policy |
| PEP chặn vì nghĩa vụ không được hỗ trợ | Chưa có quyền thực thi an toàn theo hợp đồng |
| Thao tác bắt đầu | Đường thực thi đã được mở |
| Giao dịch commit | Thay đổi dữ liệu đã thành công trong phạm vi giao dịch |
| Response được ghi ra | Tầng vận chuyển đã xuất dữ liệu ở mức theo dõi được |

Không ghi “người dùng đã tải thành công” chỉ vì PDP trả Permit. Một lỗi mạng có thể xảy ra sau khi PEP cấp quyền; ngược lại, một phần stream có thể đã được gửi trước khi kết nối thất bại.

Các chỉ số hữu ích gồm thời gian đánh giá quyền, tỷ lệ lỗi nguồn thuộc tính, lỗi PDP, số lần nghĩa vụ thất bại, số lần xung đột phiên bản và độ trễ cập nhật quyền. Cần tránh gắn subjectId hoặc resourceId trực tiếp làm nhãn metric có số lượng giá trị không giới hạn.

## 17. Những tình huống cần kiểm thử

Kiểm thử PEP phải quan sát được tài nguyên có bị truy cập hoặc tác động hay không. Chỉ assert rằng phương thức evaluate đã được gọi không chứng minh quyết định đã được thực thi.

| Tình huống | Kết quả cần xác minh trong thiết kế ví dụ |
|---|---|
| Đúng tenant, đủ thuộc tính, Permit còn hiệu lực | Chỉ tài nguyên được chỉ định được trả |
| Khác tenant | Không công bố dữ liệu của tenant khác |
| SubjectId trong body khác principal | Body không thay thế danh tính đã xác thực |
| PDP trả Deny | Không gọi thao tác ghi hoặc xuất dữ liệu |
| PDP timeout | Không có nhánh cấp quyền dự phòng vô điều kiện |
| NotApplicable hoặc Indeterminate | Không trả payload theo hợp đồng mặc định từ chối |
| Phản hồi thuộc một request khác | PEP từ chối sử dụng quyết định |
| Permit cho invoice:read được dùng để export | Bị từ chối vì khác hành động |
| Nghĩa vụ chưa được hỗ trợ | Không công bố dữ liệu |
| Che mã số thuế thành công | Response không còn trường thô hoặc đường dẫn phụ làm lộ dữ liệu |
| Tài nguyên đổi securityVersion | Phát hiện xung đột, không trả bản chưa được đánh giá |
| Quyết định hết hạn trong lúc xử lý | Không tiếp tục công bố theo thời điểm hiệu lực đã định nghĩa |
| Membership vừa bị thu hồi | Hành vi phù hợp cửa sổ thu hồi và cơ chế độ mới đã cam kết |
| Gọi qua GraphQL, consumer hoặc job nền | Mỗi đường thực thi đều có kiểm soát tương ứng |
| Bulk request có một tài nguyên không được phép | Kết quả đúng quy ước từng phần hoặc toàn bộ |
| Audit bắt buộc bị lỗi | Không công bố nếu nghĩa vụ chưa được đáp ứng |

Với thao tác cập nhật, nên xác minh không có thay đổi cơ sở dữ liệu và không phát sinh sự kiện nghiệp vụ khi quyền bị từ chối. Với thao tác đọc, có thể cho phép việc đọc metadata nội bộ tối thiểu theo thiết kế, nhưng phải xác minh nội dung được bảo vệ không đi tới client, log hoặc sự kiện ngoài ý muốn.

Các bài kiểm thử này giúp làm rõ yêu cầu khi triển khai PEP. Chúng không thay thế kiểm thử riêng cho tính đúng đắn của policy, độ tin cậy của nguồn danh tính và cấu hình bảo vệ kho dữ liệu.

## 18. Phân tích một lỗi thực tế theo tư duy PEP

Giả sử hệ thống có biểu hiện: Lan chỉ được xem hóa đơn của phòng finance nhưng vẫn tải được hóa đơn phòng legal qua chức năng xuất CSV.

Đừng chỉ hỏi “policy có sai không?”. Hãy lần theo thao tác thực tế:

1. Xác định đường xuất CSV có đi qua PEP hay chỉ đường xem từng hóa đơn có kiểm tra.
2. Kiểm tra action gửi đến PDP: invoice:read hay invoice:export.
3. Kiểm tra tài nguyên được đánh giá là đúng từng hóa đơn, tập dữ liệu có phạm vi hay chỉ tên endpoint.
4. Kiểm tra tenant và department lấy từ nguồn nào.
5. Kiểm tra quyết định cấp cho ai: Lan hay tài khoản có quyền rộng của job xuất dữ liệu.
6. Kiểm tra nghĩa vụ che field có được áp dụng ở CSV như ở JSON hay không.
7. Kiểm tra cache có phân biệt action, phạm vi dữ liệu và phiên bản thuộc tính.
8. Kiểm tra tệp kết quả có được bảo vệ sau khi tạo xong.

Ví dụ, nếu job dùng toàn quyền của report-service và chỉ kiểm tra “Lan được tạo export job”, sửa điều kiện department trong policy đọc từng bản ghi có thể không tác động tới đường lỗi. Cần đưa phạm vi ủy quyền và điểm thực thi vào đúng đường xuất dữ liệu.

Một cách sửa có thể là tạo policy riêng cho invoice:export, dựng phạm vi dữ liệu từ membership đã xác minh, ràng buộc job với quyền được ủy và kiểm soát quyền tải tệp kết quả. Cách sửa cụ thể phụ thuộc vào hợp đồng sản phẩm, nhưng bằng chứng hoàn thành phải gắn với đường truy cập từng bị bỏ sót.

## 19. Tự kiểm tra kiến thức

**Câu 1: PDP trả Permit có đồng nghĩa thao tác đã được phép thực hiện vô điều kiện không?**

Không. PEP còn phải kiểm tra quyết định gắn đúng ngữ cảnh, còn trong thời hạn áp dụng và có thể thực hiện các nghĩa vụ bắt buộc. Việc thực thi phải đúng tài nguyên và hành động đã được đánh giá.

**Câu 2: Vì sao đặt PEP tại gateway có thể chưa đủ để kiểm soát từng hóa đơn?**

Gateway có thể không có metadata hiện hành của từng hóa đơn hoặc không nhìn thấy mọi đường gọi nội bộ. Cần đặt kiểm soát ở nơi có đủ ngữ cảnh và thực sự bảo vệ thao tác nghiệp vụ, đồng thời xác định phần việc gateway vẫn đảm nhiệm.

**Câu 3: Có thể nhận tenantId từ client không?**

Có thể nhận như một giá trị lựa chọn. PEP vẫn phải kiểm chứng chủ thể được hoạt động trong tenant đó và tài nguyên thực sự thuộc phạm vi tương ứng.

**Câu 4: Vì sao TTL ngắn không tự giải quyết mọi lỗi cache quyền?**

Một key thiếu action hoặc resourceId có thể trả sai quyết định ngay trong mili giây đầu tiên. TTL chỉ giới hạn tuổi dữ liệu; nó không sửa sự thiếu hụt trong ngữ cảnh.

**Câu 5: So sánh securityVersion đã giải quyết hoàn toàn TOCTOU chưa?**

Chưa. Phiên bản phải thay đổi đúng khi thuộc tính bảo mật đổi, được kiểm tra tại thao tác sử dụng và bao phủ dữ kiện cần bảo vệ. Các nguồn như trạng thái tài khoản bên ngoài còn cần cơ chế về độ mới hoặc phối hợp riêng.

**Câu 6: Một lời gọi service nội bộ đã có mTLS thì có thể bỏ phân quyền người dùng không?**

Không thể suy ra như vậy. Danh tính workload và quyền hành động thay mặt một người dùng cần được xác định trong hợp đồng phân quyền của đường gọi.

## 20. Những điểm cần nhớ khi thiết kế

PEP phải đứng trên đường thao tác thật sự đi tới tài nguyên. Đặt một phép kiểm tra ở nơi thuận tiện nhưng để đường khác đi vòng sẽ không bảo vệ đầy đủ tài nguyên.

Ngữ cảnh dùng để cấp quyền phải có nguồn đáng tin cậy, đúng mức chi tiết và có độ mới phù hợp. Quyết định phải gắn với đúng chủ thể, hành động, tài nguyên và dữ kiện đã đánh giá.

Permit kèm nghĩa vụ chỉ có ý nghĩa khi nghĩa vụ được thực hiện đúng. Lỗi đánh giá, phản hồi không hợp lệ và quyết định đã hết hiệu lực cần có hành vi rõ ràng; chúng không tự tạo ra căn cứ cấp quyền.

Với hệ thống nhiều tenant, workload, job nền và dữ liệu xuất ra ngoài, hãy theo dõi quyền tới tận nơi dữ liệu được đọc, thay đổi hoặc công bố. PEP là trách nhiệm thực thi xuyên suốt những ranh giới đó.

## Tài liệu tham khảo

- [NIST CSRC — Policy enforcement point](https://csrc.nist.gov/glossary/term/policy_enforcement_point): định nghĩa vai trò thực thi quyết định truy cập.
- [NIST SP 800-162 — Guide to Attribute Based Access Control](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): nền tảng khái niệm ABAC.
- [OASIS — XACML Version 3.0](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html): tham chiếu các kiểu kết quả, PEP bias, obligation và advice; đặc biệt các mục 5.48 và 7.2.

