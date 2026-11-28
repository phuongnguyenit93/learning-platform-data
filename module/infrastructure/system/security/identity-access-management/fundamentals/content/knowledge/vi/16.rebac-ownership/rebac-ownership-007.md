# Delegated access

## 1. Truy cập được ủy quyền giải quyết vấn đề gì?

Delegated access là cơ chế cho phép một chủ thể trao cho chủ thể khác một phạm vi quyền có kiểm soát, hoặc cho phép một bên thực hiện công việc dựa trên thẩm quyền được trao. Người nhận dùng danh tính của mình hoặc một danh tính actor đã được nhận diện; hệ thống vẫn biết quyền đến từ đâu, áp dụng cho tài nguyên nào và còn hiệu lực trong điều kiện nào.

Ví dụ, Lan sở hữu một báo cáo và muốn Minh đọc, bổ sung nhận xét trong hai ngày. Lan không cần đưa mật khẩu cho Minh, chuyển quyền sở hữu báo cáo hoặc cấp cho Minh vai trò quản trị toàn hệ thống. Hệ thống tạo một ủy quyền có phạm vi rõ ràng và kiểm tra nó khi Minh truy cập.

Trong ReBAC — Relationship-Based Access Control — quyền có thể được suy ra từ những quan hệ giữa chủ thể và tài nguyên. Delegation bổ sung một loại đường dẫn quyền: Minh được thực hiện một hành động vì có quan hệ ủy quyền hợp lệ nối tới một nguồn thẩm quyền được policy công nhận.

Bài học tập trung vào ba câu hỏi:

- Ai được tạo hoặc thay đổi một ủy quyền?
- Người nhận được làm gì, với tài nguyên nào và trong bao lâu?
- Khi nguồn thẩm quyền thay đổi, quyền phát sinh từ ủy quyền còn hiệu lực thế nào?

Các mô hình dữ liệu, tuple, công thức và mã trong bài là thiết kế minh họa của ứng dụng. Chúng không phải schema bắt buộc cho mọi hệ thống ReBAC hay một giao thức ủy quyền chung.

## 2. Phân biệt ủy quyền, chia sẻ và chuyển ownership

Các sản phẩm có thể dùng cùng nút “Share” để tạo những cơ chế quyền khác nhau. Cần đọc ngữ nghĩa thật sự, thay vì suy ra từ tên trên giao diện.

| Cơ chế | Thay đổi chính | Ví dụ |
|---|---|---|
| Cấp quyền trực tiếp | Policy công nhận quan hệ trực tiếp giữa người dùng và tài nguyên | Quản trị viên thêm Minh vào danh sách viewer |
| Delegation | Một nguồn thẩm quyền được dùng để tạo phạm vi quyền cho người nhận | Lan ủy quyền Minh nhận xét báo cáo đến ngày hết hạn |
| Chuyển ownership | Thay đổi quan hệ chủ sở hữu và các quyền gắn với ownership | Minh trở thành owner mới của báo cáo |
| Chia sẻ bằng liên kết | Khả năng truy cập gắn với liên kết hoặc một điều kiện của liên kết | Người có URL có thể tải tài liệu trong thời hạn |
| Giả danh — impersonation | Một bên được biểu diễn như chủ thể khác trong phạm vi được định nghĩa | Công cụ hỗ trợ mở phiên dưới danh tính người dùng |

Một quan hệ viewer có thể do ủy quyền tạo ra, nhưng chỉ lưu viewer mà không lưu nguồn cấp sẽ làm mất thông tin cần để theo dõi vòng đời ủy quyền.

Delegation cũng không đồng nghĩa chia sẻ mật khẩu hoặc đưa phiên đăng nhập cho người khác. Những cách đó khiến hệ thống khó phân biệt người thực hiện và phá vỡ khả năng thu hồi riêng quyền đã trao.

Cần phân biệt hai dạng thường gặp:

**Ủy quyền quyền truy cập:** Minh nhận quyền nhận xét bằng chính danh tính Minh. Lan là nguồn cấp quyền; người tạo nhận xét vẫn là Minh.

**Ủy quyền thực hiện công việc:** Một dịch vụ hoặc trợ lý thực hiện hành động thay mặt người dùng. Hệ thống cần giữ cả người yêu cầu hoặc người được đại diện và actor thật sự thực thi.

Không tự gán Lan thành danh tính người thực hiện chỉ vì quyền của Minh bắt nguồn từ Lan. Việc thể hiện “thay mặt ai” phụ thuộc hợp đồng của từng luồng nghiệp vụ.

## 3. Ví dụ xuyên suốt: cộng tác trên báo cáo

Giả sử hệ thống quản lý tài liệu của tenant acme có báo cáo document:report-42.

~~~text
Lan   : owner của document:report-42
Minh  : thành viên tenant acme
An    : thành viên tenant acme
Hà    : người dùng thuộc tenant khác
~~~

Lan muốn tạo ủy quyền:

~~~text
Người nhận       : Minh
Tài nguyên       : document:report-42
Hành động        : document:read, document:comment
Bắt đầu          : 26/11/2026 09:00, Asia/Saigon
Kết thúc         : 28/11/2026 09:00, Asia/Saigon
Ủy quyền tiếp    : Không
Chuyển owner     : Không
Quyền xóa        : Không
~~~

Trong hệ thống này, permission document:comment yêu cầu cả quyền đọc. Việc chọn tập hành động phải phù hợp với quy tắc phụ thuộc đó; không giả định mọi ứng dụng đều có cùng quan hệ giữa read và comment.

Một lần cấp thành công tạo bản ghi delegation, không biến Minh thành owner. Nếu Minh gọi API xóa tài liệu, việc có quyền đọc và nhận xét không làm phát sinh quyền xóa.

Nếu Lan sửa thời hạn hoặc thu hồi, những lần truy cập sau phải được đánh giá theo trạng thái mới trong giới hạn độ nhất quán đã cam kết. Quyền đã được dùng để tạo một nhận xét trước đó không mặc nhiên làm mất hiệu lực nhận xét sau khi delegation hết hạn.

## 4. Các chủ thể và thành phần của một ủy quyền

Một mô hình đủ rõ nên phân biệt các vai trò sau:

| Thành phần | Ý nghĩa trong ví dụ |
|---|---|
| Grantor hoặc delegator | Lan, bên tạo ủy quyền dựa trên thẩm quyền được policy công nhận |
| Grantee hoặc delegate | Minh, người nhận phạm vi quyền |
| Actor | Người hoặc workload thực sự gửi yêu cầu và thực hiện hành động |
| Resource | Báo cáo report-42 |
| Action set | Những thao tác được ủy quyền |
| Authority basis | Quan hệ hoặc quyền làm căn cứ để cấp ủy quyền |
| Constraints | Thời gian, tenant, người nhận, mục đích hoặc điều kiện khác |
| Parent grant | Ủy quyền cha khi có ủy quyền tiếp |
| Enforcement point | Nơi kiểm tra rồi cho phép hoặc chặn thao tác |

Grantor và owner có thể là cùng người nhưng không bắt buộc. Một quản trị viên được phép quản lý quyền chia sẻ có thể tạo grant mà không được đọc nội dung tài liệu. Vì vậy, “được ủy quyền những gì” phải dựa trên authority basis được định nghĩa, không chỉ trên tập thao tác mà người đó tự thực hiện được.

Ngược lại, có quyền đọc không mặc nhiên có quyền cấp quyền đọc cho người khác. Nếu cứ có read là được chia sẻ read, một báo cáo nhạy cảm có thể lan truyền ngoài ý định của owner.

Trong thiết kế ví dụ, Lan có quyền document:delegate vì là owner hiện hành. Minh chỉ có các hành động được liệt kê trong grant và không có quyền ủy quyền tiếp.

## 5. Hai lần kiểm tra khác nhau: cấp grant và dùng grant

Hệ thống cần kiểm soát cả việc tạo quan hệ quyền lẫn việc sử dụng quan hệ đó.

### 5.1. Khi tạo ủy quyền

API tạo grant phải xác minh:

1. Danh tính người tạo đã được xác thực.
2. Người tạo có thẩm quyền cấp đúng phạm vi yêu cầu.
3. Người nhận là chủ thể tồn tại và được policy chấp nhận.
4. Tài nguyên và tenant được xác định từ dữ liệu đáng tin cậy.
5. Hành động, thời hạn và khả năng ủy quyền tiếp nằm trong giới hạn được cấp.
6. Các yêu cầu phê duyệt hoặc xác thực mạnh hơn đã được đáp ứng.
7. Việc ghi grant không dựa trên căn cứ quyền đã thay đổi trước lúc commit.

Không chấp nhận trường grantor do client gửi như bằng chứng danh tính. Server lấy người tạo từ principal đã xác thực; nếu có actor thay mặt một người khác, phải kiểm chứng quan hệ đại diện theo hợp đồng.

### 5.2. Khi sử dụng ủy quyền

Khi Minh nhận xét, server phải xác minh:

1. Actor hiện tại đúng người nhận hoặc thành viên hợp lệ của nhóm nhận quyền.
2. Grant đã active, đã bắt đầu và chưa hết hạn.
3. Tài nguyên, tenant và hành động khớp phạm vi grant.
4. Grant và các phụ thuộc của nó chưa bị thu hồi hoặc mất hiệu lực.
5. Điều kiện hiện hành như trạng thái tài khoản, mức bảo đảm phiên vẫn đáp ứng policy.
6. Đường thực thi thật sự bị chặn nếu không đạt yêu cầu.

Một grant đã được kiểm tra lúc tạo vẫn có thể không còn hợp lệ lúc sử dụng. Tài khoản người nhận bị khóa, quan hệ owner thay đổi hoặc grant cha bị thu hồi là những ví dụ.

## 6. Biểu diễn delegation trong đồ thị quan hệ

Một tuple quan hệ tối giản thường được biểu diễn bằng tài nguyên, quan hệ và chủ thể:

~~~text
document:report-42#owner@user:lan
~~~

Trong ký pháp minh họa này, Lan có quan hệ owner đối với báo cáo. Ký pháp không phải API cụ thể của một sản phẩm.

Có thể thêm cạnh trực tiếp:

~~~text
document:report-42#delegated_reader@user:minh
~~~

Tuy nhiên, một cạnh như vậy chưa biểu diễn đầy đủ ai đã cấp, khi nào hết hạn, grant cha là gì hoặc thu hồi theo nguồn cấp nào. Nếu ứng dụng cần quản lý các yếu tố đó, có thể mô hình hóa grant thành một đối tượng có định danh riêng:

~~~text
document:report-42#delegation@grant:dg-101
grant:dg-101#grantor@user:lan
grant:dg-101#grantee@user:minh
grant:dg-101#resource@document:report-42
~~~

Metadata bổ sung:

~~~json
{
  "id": "dg-101",
  "tenantId": "acme",
  "grantor": "user:lan",
  "grantee": "user:minh",
  "resource": "document:report-42",
  "actions": [
    "document:read",
    "document:comment"
  ],
  "notBefore": "2026-11-26T02:00:00Z",
  "expiresAt": "2026-11-28T02:00:00Z",
  "status": "ACTIVE",
  "parentGrantId": null,
  "allowRedelegation": false,
  "remainingDepth": 0,
  "authorityBasis": {
    "kind": "CURRENT_OWNER",
    "subject": "user:lan",
    "resource": "document:report-42"
  },
  "version": 1
}
~~~

Thời gian JSON dùng UTC, tương ứng với ví dụ lúc 09:00 tại Asia/Saigon. Lưu timestamp có múi giờ rõ ràng giúp tránh lệch thời điểm hết hạn giữa các dịch vụ.

Trong mô hình này, quyền không được suy ra chỉ từ việc tồn tại grant:dg-101. Bộ đánh giá còn cần kiểm tra metadata, authority basis và trạng thái tài khoản. Một engine đồ thị thuần quan hệ có thể cần điều kiện, dữ liệu bổ sung hoặc một tầng policy phối hợp để thực hiện các kiểm tra đó.

Sơ đồ nguồn quyền:

~~~mermaid
flowchart LR
    L["Lan"] -->|owner| D["Báo cáo report-42"]
    G["Grant dg-101"] -->|grantor| L
    G -->|resource| D
    G -->|grantee| M["Minh"]
    G --> C["read, comment; có thời hạn; không ủy quyền tiếp"]
~~~

Trong sản phẩm cho phép cấp quyền tới nhóm, grantee có thể là một tập người dùng qua quan hệ membership. Khi đó, cần xác định membership được chụp tại lúc cấp hay được đánh giá tại lúc dùng. Bài này dùng người nhận trực tiếp để giữ rõ luồng cơ bản.

## 7. Quy tắc giới hạn quyền: không khuếch đại thẩm quyền

Hệ thống phải ngăn việc một chuỗi grant tạo ra nhiều thẩm quyền hơn nguồn cấp cho phép.

Với mô hình ủy quyền phụ thuộc động vào nguồn cấp của bài, tập quyền có hiệu lực tại thời điểm t có thể mô tả:

~~~text
EffectiveActions(grant, actor, resource, t)
  = RequestedAndGrantedActions(grant)
    ∩ DelegableActions(authorityBasis, t)
    ∩ AllowedActions(globalPolicy, actor, resource, t)
~~~

Công thức chỉ là một phần của điều kiện cấp quyền. Grant còn phải hợp lệ về người nhận, tài nguyên, tenant, thời gian và toàn bộ chuỗi phụ thuộc.

DelegableActions là những hành động authority basis cho phép trao cho người khác. Nó không nhất thiết bằng quyền sử dụng trực tiếp của grantor. Ví dụ, quản trị viên quyền chia sẻ có thể được phép cấp read nhưng bản thân không được đọc nội dung.

Các chiều giới hạn cần xem xét độc lập:

| Chiều | Ví dụ giới hạn |
|---|---|
| Hành động | Được read và comment, không được delete |
| Tài nguyên | Chỉ report-42, không phải toàn bộ thư mục |
| Chủ thể nhận | Chỉ Minh, không phải mọi người cùng tenant |
| Thời gian | Hết hiệu lực sau hai ngày |
| Môi trường | Chỉ khi mức bảo đảm phiên đáp ứng yêu cầu |
| Ủy quyền tiếp | Không được tạo grant con |
| Phạm vi tổ chức | Không chia sẻ ra ngoài tenant nếu chưa được phê duyệt |

Phép so sánh tập con của scope không phải lúc nào cũng là so sánh chuỗi. Nếu phạm vi cha là “các tài liệu thuộc dự án P”, phạm vi con “mọi tài liệu của tổ chức” rõ ràng rộng hơn dù dùng một tên ngắn hơn.

Với tập tài nguyên biến động, cần định nghĩa delegation áp dụng cho các thành viên hiện hành của tập hay chỉ các tài nguyên có tại thời điểm cấp. Một grant “đọc cả thư mục” có thể bao gồm tài liệu được thêm vào sau, nếu policy mô tả như vậy. Người cấp cần thấy được ngữ nghĩa đó.

Nếu policy có điều kiện phức tạp, không tự giả định rằng server có thể chứng minh mọi biểu thức con đều hẹp hơn biểu thức cha. Có thể giới hạn người dùng vào các mẫu scope đã biết cách so sánh, hoặc luôn kiểm tra đồng thời điều kiện cha và con khi sử dụng.

## 8. Khi nào một grant còn phụ thuộc người cấp?

Không có một ngữ nghĩa vòng đời duy nhất cho mọi delegation. Cần chọn rõ mô hình trước khi viết logic thu hồi.

### 8.1. Grant phụ thuộc động vào nguồn thẩm quyền

Grant còn hiệu lực khi authority basis vẫn cho phép quyền được ủy. Nếu Lan không còn là owner và đó là căn cứ duy nhất của dg-101, dg-101 không còn làm căn cứ truy cập.

Đây là mô hình chính của ví dụ. Nó thuận tiện khi tổ chức muốn quyền phát sinh biến mất theo nguồn cấp.

### 8.2. Cấp quyền độc lập sau khi được phê duyệt

Một người có thẩm quyền có thể thực hiện hành động quản trị để tạo quyền bền vững cho người khác. Sau khi cấp thành công, quyền đó do policy quản trị sở hữu và không nhất thiết phụ thuộc việc người cấp còn giữ vai trò cũ.

Ví dụ, quản trị viên dự án cấp một vai trò theo quy trình phê duyệt chính thức. Người quản trị rời vị trí không tự xóa vai trò đã cấp nếu hợp đồng quản trị quy định quyền độc lập.

### 8.3. Grant gắn với nhiệm vụ hoặc sự kiện

Một ủy quyền có thể chấm dứt khi công việc kết thúc, hợp đồng hết hiệu lực hoặc tài nguyên chuyển giai đoạn, ngay cả khi thời hạn lịch chưa tới.

Ba mô hình có thể cùng tồn tại, nhưng phải được thể hiện bằng loại grant hoặc policy đủ rõ. Không dùng trường grantor chỉ phục vụ audit rồi lại giả định nó tự tạo ra cơ chế thu hồi theo chuỗi.

Với dg-101, hệ thống cần đánh giá lại authorityBasis CURRENT_OWNER. version trong bản ghi grant phục vụ phát hiện thay đổi grant; nó không tự chứng minh Lan vẫn là owner hiện hành.

## 9. Vòng đời của một ủy quyền

Một vòng đời minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Cần phê duyệt hoặc người nhận chấp nhận
    Pending --> Active: Đạt điều kiện kích hoạt
    Pending --> Rejected: Không được chấp thuận
    Active --> Revoked: Thu hồi
    Active --> Expired: Hết thời hạn
    Active --> Suspended: Nguồn quyền hoặc điều kiện không còn
    Suspended --> Active: Khôi phục nếu policy cho phép
    Revoked --> [*]
    Expired --> [*]
    Rejected --> [*]
~~~

Không phải hệ thống nào cũng cần mọi trạng thái. Một ứng dụng cộng tác nội bộ có thể tạo Active ngay; một ứng dụng chia sẻ dữ liệu nhạy cảm có thể yêu cầu phê duyệt trước.

Cần phân biệt trạng thái lưu trữ và hiệu lực tại lúc đánh giá. Bản ghi có status ACTIVE nhưng thời gian hiện tại đã vượt expiresAt vẫn phải bị coi là không hợp lệ. Không chờ một job dọn dữ liệu chuyển status sang EXPIRED mới chặn truy cập.

Trong ví dụ, khoảng hiệu lực là:

~~~text
notBefore <= thời điểm đánh giá < expiresAt
~~~

Đúng tại expiresAt, grant đã hết hiệu lực. Dùng nguồn thời gian phía server và quy định rõ cách xử lý sai lệch đồng hồ; thời gian do client tự gửi không quyết định grant còn sống.

Nếu cho phép mở rộng thời hạn hoặc tăng hành động, đó là thay đổi quyền cần phân quyền lại. API sửa grant không được biến thành lối đi vòng qua kiểm soát của API tạo grant.

## 10. Ủy quyền tiếp và kiểm tra chuỗi

Ở grant dg-101 ban đầu, allowRedelegation bằng false. Minh không được tạo dg-102 để cấp quyền cho An chỉ vì Minh có thể đọc tài liệu.

Để minh họa một biến thể cho phép ủy quyền tiếp, giả sử Lan tạo một grant khác có:

~~~text
actions            = read, comment
allowRedelegation  = true
remainingDepth     = 1
~~~

Minh có thể tạo grant con cho An theo quy định của ứng dụng:

~~~text
parentGrantId      = grant của Lan cấp cho Minh
grantor            = Minh
grantee            = An
actions            = read
allowRedelegation  = false
remainingDepth     = 0
expiresAt          <= expiresAt của grant cha
~~~

Quan hệ phụ thuộc:

~~~text
Nguồn thẩm quyền của Lan
    -> Grant cha: Lan cấp cho Minh
        -> Grant con: Minh cấp cho An
            -> An đọc đúng báo cáo
~~~

Ứng dụng cần kiểm tra cạnh cha–con, không chỉ kiểm tra từng bản ghi riêng lẻ:

- Người cấp grant con là người nhận hợp lệ của grant cha.
- Grant cha cho phép ủy quyền tiếp.
- Tài nguyên và tenant không được mở rộng.
- Hành động của grant con nằm trong phạm vi cha có thể ủy.
- Khoảng thời gian của con nằm trong khoảng của cha.
- Các điều kiện cha vẫn được áp dụng, kể cả khi con không chép lại chúng.
- remainingDepth của con không lớn hơn remainingDepth của cha trừ một.
- Không có vòng lặp hoặc chuỗi vượt giới hạn hệ thống.

Trong quy ước này, remainingDepth bằng 1 cho phép tạo thêm một cấp con; con phải có remainingDepth bằng 0. Định nghĩa phải thống nhất ở API, kho dữ liệu và bộ đánh giá, tránh mỗi nơi hiểu “độ sâu” khác nhau.

Nếu parentGrantId trỏ đến một grant bất kỳ, attacker có thể ghép grant đang dùng vào nguồn quyền không liên quan. Vì vậy, kiểm tra cha tồn tại chưa đủ; phải xác minh quan hệ nguồn cấp và phạm vi.

Với grantee là nhóm, quy tắc “grantor con bằng grantee cha” không thể chỉ so sánh hai chuỗi. Cần chứng minh người tạo grant con là thành viên hợp lệ được phép đại diện nhóm theo policy. Không nên tự mở rộng thuật toán dành cho người nhận trực tiếp sang nhóm mà bỏ phần chứng minh này.

## 11. Minh họa kiểm tra chuỗi bằng Java

Đoạn mã sau chỉ tập trung vào đường sử dụng delegation dành cho người nhận trực tiếp. Các interface và kiểu dữ liệu là hợp đồng minh họa, không phải SDK của một engine ReBAC và chưa phải ứng dụng chạy độc lập.

~~~java
public final class DelegatedAccessEvaluator {

    private final DelegationStore store;
    private final AuthorityPolicy authorityPolicy;
    private final GlobalAccessPolicy globalPolicy;
    private final java.time.Clock clock;
    private final int maxChainLength;

    public DelegatedAccessEvaluator(
            DelegationStore store,
            AuthorityPolicy authorityPolicy,
            GlobalAccessPolicy globalPolicy,
            java.time.Clock clock,
            int maxChainLength) {
        this.store = store;
        this.authorityPolicy = authorityPolicy;
        this.globalPolicy = globalPolicy;
        this.clock = clock;
        this.maxChainLength = maxChainLength;
    }

    public Decision check(
            VerifiedAccessRequest request,
            String leafGrantId) {

        // Đọc chuỗi và dữ kiện quyền theo hợp đồng nhất quán của ứng dụng.
        DelegationSnapshot snapshot = store.loadSnapshot(
                request.tenantId(), leafGrantId);

        java.util.List<Grant> chain = snapshot.leafToRoot();

        if (!snapshot.complete()
                || chain.isEmpty()
                || chain.size() > maxChainLength) {
            return Decision.deny("INVALID_CHAIN");
        }

        Grant leaf = chain.get(0);

        if (!leaf.granteeId().equals(request.actorId())) {
            return Decision.deny("WRONG_GRANTEE");
        }

        java.time.Instant now = clock.instant();
        java.util.Set<String> visited = new java.util.HashSet<>();

        for (int i = 0; i < chain.size(); i++) {
            Grant current = chain.get(i);

            if (!visited.add(current.id())) {
                return Decision.deny("CYCLE");
            }

            if (!current.activeAt(now)
                    || !current.covers(request)) {
                return Decision.deny("GRANT_NOT_APPLICABLE");
            }

            if (!globalPolicy.allowsGrantLink(
                    current, request, snapshot)) {
                return Decision.deny("GRANT_LINK_RESTRICTED");
            }

            if (i + 1 < chain.size()) {
                Grant parent = chain.get(i + 1);

                if (!current.parentGrantId().equals(parent.id())
                        || !parent.granteeId().equals(current.grantorId())
                        || !parent.allowRedelegation()
                        || !current.isValidNarrowingOf(parent)) {
                    return Decision.deny("INVALID_PARENT_LINK");
                }
            } else {
                if (current.parentGrantId() != null) {
                    return Decision.deny("MISSING_PARENT");
                }

                if (!authorityPolicy.mayDelegate(
                        current.grantorId(),
                        current.authorityBasis(),
                        request,
                        snapshot)) {
                    return Decision.deny("ROOT_AUTHORITY_LOST");
                }
            }
        }

        if (!globalPolicy.allowsUse(request, snapshot)) {
            return Decision.deny("GLOBAL_POLICY_RESTRICTED");
        }

        return Decision.permit(
                snapshot.revision(),
                leaf.id(),
                snapshot.validUntil()
        );
    }
}
~~~

Các hợp đồng quan trọng của đoạn mã:

**VerifiedAccessRequest** chứa actor đã được xác thực, tài nguyên, tenant và action do backend ánh xạ. leafGrantId là một lựa chọn grant, không phải bằng chứng đủ để cấp quyền.

**DelegationSnapshot** chứa chuỗi từ lá tới gốc và dữ kiện phục vụ phân quyền. complete bằng false khi thiếu parent, dữ liệu bị cắt hoặc không thể tạo snapshot theo hợp đồng. Lỗi đọc snapshot phải kết thúc mà không tạo Permit.

**activeAt** kiểm tra trạng thái sử dụng được và khoảng thời gian. **covers** kiểm tra đúng tài nguyên, tenant và action ở mỗi grant.

**isValidNarrowingOf** bao gồm tập hành động, tài nguyên, thời gian, độ sâu và các quy tắc làm hẹp phạm vi. Trong mô hình tài nguyên đơn của bài, con phải trỏ đúng tài nguyên cha. Điều kiện bổ sung của cha vẫn được đánh giá khi duyệt qua cha.

**allowsGrantLink** áp dụng các giới hạn cho từng mắt xích, chẳng hạn policy không cho phép tiếp tục dùng grant qua một chủ thể đã bị vô hiệu hóa. **allowsUse** kiểm tra actor thực tế và điều kiện của yêu cầu hiện tại.

**mayDelegate** kiểm chứng nguồn thẩm quyền gốc theo dữ kiện trong snapshot. Nó không được suy ra thẩm quyền của Lan bằng chính grant đang cần chứng minh, vì như vậy sẽ tạo lập luận vòng tròn.

**Decision.permit** là kết quả đánh giá, chưa tự công bố hoặc sửa tài nguyên. PEP phải ràng buộc quyết định với request, revision và thời hạn phù hợp trước khi thực hiện thao tác.

Một triển khai thật cần kiểm tra null, kiểu dữ liệu và cấu trúc grant tại biên nạp dữ liệu; không để bản ghi sai cấu trúc trở thành một đường bỏ qua điều kiện. Nếu evaluator gặp lỗi hoặc hết ngân sách duyệt, kết quả của luồng đó không được chuyển thành Permit.

Thuật toán này đánh giá một đường quyền đã chọn. Người dùng có thể có đường cấp quyền khác độc lập. Ví dụ, dg-101 bị thu hồi nhưng Minh vẫn là viewer trực tiếp theo một quyền riêng. Khi kiểm tra quyền tổng thể, ứng dụng có thể tìm đường khác hợp lệ; phải ghi nhận đúng nguồn quyền đã được sử dụng.

## 12. Tạo grant phải chống thay đổi nguồn quyền giữa chừng

Một lỗi dễ gặp nằm ở khoảng thời gian giữa kiểm tra quyền cấp và ghi grant:

~~~text
T0: Lan là owner của báo cáo.
T1: API xác nhận Lan có thể ủy quyền.
T2: Ownership chuyển sang người khác.
T3: API vẫn ghi một grant mới dựa trên căn cứ cũ.
~~~

Nếu hợp đồng yêu cầu người tạo vẫn có thẩm quyền tại lúc grant được ghi, cần ràng buộc việc tạo với phiên bản hoặc trạng thái nguồn cấp.

Một quy trình minh họa:

~~~text
1. Đọc tài nguyên và revision của quan hệ owner.
2. Kiểm tra người tạo được cấp đúng scope, người nhận và thời hạn.
3. Mở giao dịch hoặc dùng thao tác có điều kiện phù hợp với kho dữ liệu.
4. Xác minh revision làm căn cứ chưa đổi.
5. Ghi grant cùng nguồn cấp, parent và phiên bản.
6. Commit, phát sự kiện vòng đời theo cơ chế bảo đảm của ứng dụng.
~~~

Nếu nguồn quan hệ và kho grant nằm ở hai hệ thống khác nhau, một transaction cục bộ không tự bao phủ cả hai. Cần cơ chế điều phối hoặc phải chấp nhận một mô hình nhất quán được định nghĩa rõ, kèm đánh giá lại nguồn quyền khi sử dụng.

Nguyên tắc tương tự áp dụng cho grant con. Không được kiểm tra cha đang active rồi tạo con sau khi cha đã bị thu hồi mà vẫn tuyên bố grant con độc lập hợp lệ.

Trong mô hình phụ thuộc động, việc kiểm tra lại chuỗi ở thời điểm sử dụng giúp ngăn grant tạo muộn trở thành quyền tồn tại lâu dài. Nó không thay thế kiểm tra đúng khi tạo, vì grant sai vẫn có thể gây nhiễu audit, gửi thông báo hoặc bị dùng qua những đường khác chưa được bảo vệ.

## 13. Thu hồi grant và hiệu ứng đối với các quyền phát sinh

Thu hồi là thay đổi khả năng sử dụng grant, không chỉ xóa một dòng trên giao diện.

Giả sử có:

~~~text
dg-201: Lan -> Minh, read + comment, cho phép ủy quyền tiếp
dg-202: Minh -> An, read, parent = dg-201
~~~

Khi dg-201 bị thu hồi, dg-202 phải mất hiệu lực nếu policy quy định grant con phụ thuộc cha. Có hai cách triển khai thường có thể phối hợp:

| Cách | Cơ chế | Điểm cần xử lý |
|---|---|---|
| Kiểm tra phụ thuộc khi sử dụng | Mỗi lần đánh giá xác minh mọi grant cha còn hợp lệ | Cần kiểm soát độ trễ, độ nhất quán và chi phí duyệt |
| Cập nhật các grant phát sinh | Đánh dấu hoặc vô hiệu hóa các grant con khi thu hồi cha | Cần chỉ mục phụ thuộc và xử lý sự kiện bền vững |

Đánh dấu grant cha bị thu hồi rồi kiểm tra đầy đủ chuỗi có thể chặn quyền trước khi mọi bản ghi con được cập nhật. Nếu chỉ dựa vào một job cập nhật con chạy sau, cần xác định khoảng thời gian mà con vẫn có thể được chấp nhận.

Không tự xóa toàn bộ quyền của An. An có thể còn một grant khác do owner cấp trực tiếp. Thu hồi theo nguồn cần giữ lại các nguồn quyền độc lập được policy công nhận.

Một API “thu hồi grant dg-201” và một API “gỡ mọi quyền của An trên tài liệu” có phạm vi khác nhau. Giao diện quản trị nên nói rõ hành động nào đang được thực hiện và những đường quyền nào còn tồn tại.

Grant đã REVOKED không nên tự sống lại khi Lan nhận lại vai trò owner. Nếu muốn khôi phục, phải dùng quy trình được phân quyền và lưu lịch sử. Tạm mất điều kiện nguồn rồi phục hồi có thể được xử lý bằng trạng thái suspended trong một mô hình khác, nhưng cần phân biệt với thu hồi có chủ đích.

Thu hồi quyền truy cập cũng không lấy lại được nội dung mà người nhận đã tải trước đó. Với dữ liệu đã công bố, hệ thống cần chính sách sử dụng và kiểm soát dữ liệu riêng; không mô tả revocation như cơ chế xóa trí nhớ hoặc thu hồi mọi bản sao ngoài hệ thống.

## 14. Độ nhất quán, cache và thời hạn hiệu lực

Một mô hình thu hồi đúng trên giấy vẫn có thể hoạt động sai nếu bộ kiểm tra dùng dữ liệu quan hệ cũ.

Ví dụ, dịch vụ A đã ghi dg-201 là REVOKED nhưng dịch vụ B đọc bản sao chưa cập nhật và tiếp tục chấp nhận dg-202. Cần nêu rõ cam kết: quyền bị thu hồi có hiệu lực ngay sau phản hồi API, sau một mốc revision hay trong một khoảng trễ tối đa.

Cache quyết định delegation phải xét các phụ thuộc liên quan:

~~~text
actor
resource + resource authorization version
action
leaf grant id + grant version
ancestor grant versions hoặc revision bao phủ chúng
authority basis revision
policy version
các điều kiện ảnh hưởng đến quyền
~~~

Chỉ cache theo leafGrantId không phát hiện cha bị thu hồi. Chỉ thêm expiresAt của leaf cũng chưa đủ nếu cha hết hạn sớm hơn hoặc policy cho phép quyền thay đổi vì điều kiện khác.

Thời hạn sử dụng một quyết định không được vượt quá mốc gần nhất mà một phụ thuộc bắt buộc hết hiệu lực. Ví dụ, nếu grant con còn một ngày nhưng phiên xác thực chỉ được chấp nhận thêm mười phút, không được dùng cùng quyết định mà bỏ qua hạn của phiên.

Một cache key có đủ trường vẫn không tự giải quyết độ mới. Cần cơ chế biết phiên bản mới, sự kiện vô hiệu hóa hoặc giới hạn thời gian chấp nhận dữ liệu cũ.

Với yêu cầu thu hồi chặt, có thể cần đọc theo revision đủ mới trước thao tác nhạy cảm. Revision chỉ có ý nghĩa theo hợp đồng của kho quan hệ; không tự gán một bộ đếm cục bộ thành bằng chứng nhất quán xuyên mọi dịch vụ.

Khi kho quan hệ hoặc nguồn trạng thái không truy cập được, hệ thống chỉ được dùng bằng chứng còn hợp lệ theo chính sách đã định nghĩa. Lỗi truy vấn không trở thành “không có giới hạn delegation”.

## 15. Delegation trong ReBAC và token OAuth

ReBAC mô tả nguồn quyền và các quan hệ. Token là một phương tiện truyền bằng chứng hoặc kết quả cấp quyền qua ranh giới hệ thống. Hai phần cần ánh xạ rõ nhưng không thay thế nhau.

[RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html) phân biệt delegation với impersonation: delegation giữ actor riêng với chủ thể được đại diện. Token Exchange hỗ trợ phát hành token cho các ngữ nghĩa này; claim act có thể biểu diễn actor. Giao thức không tự bảo đảm thu hồi token đầu vào sẽ làm token đầu ra mất hiệu lực. Việc lan truyền thu hồi cần cơ chế của triển khai.

Trong ứng dụng của bài, có thể chọn:

- Token nhận diện Minh, còn backend kiểm tra grant trong kho quan hệ ở mỗi lần truy cập.
- Token chứa định danh grant và phạm vi cần thiết; backend vẫn kiểm tra các điều kiện hiện hành theo hợp đồng.
- Dịch vụ nhận token dành cho một hành động thay mặt người dùng, rồi ánh xạ sang kiểm tra quan hệ và phạm vi nghiệp vụ.

Không mặc định claim sub luôn là grantor. Với quyền truy cập được trao cho Minh, sub có thể nhận diện Minh; grantor Lan là nguồn thẩm quyền được lưu riêng. Với một luồng dịch vụ thay mặt người dùng, cách biểu diễn subject và actor cần tuân thủ giao thức và hợp đồng token đang dùng.

Một chuỗi actor hoặc một grantId trong token không tự chứng minh mọi mắt xích còn thẩm quyền. Server phải xác minh token và áp dụng mô hình quyền phù hợp. Không lấy các header tự khai như X-Acting-For làm bằng chứng.

[RFC 9700, mục 2.3](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.3) khuyến nghị giới hạn đặc quyền access token ở mức cần thiết và giới hạn audience. Resource server phải từ chối token không dành cho mình. Đây là cơ sở để tránh dùng một token được cấp cho dịch vụ tài liệu như quyền gọi mọi backend.

Trong thiết kế delegation, cần kiểm soát cả scope giao thức và phạm vi tài nguyên. Scope document:read không nhất thiết liệt kê từng document được đọc; backend có thể vẫn cần ReBAC để quyết định Minh được đọc report-42 nhưng không được đọc report-99.

Token còn hạn nhưng grant đã bị thu hồi là tình huống phải được thiết kế trước. Nếu backend chỉ kiểm tra chữ ký và exp của token, độ trễ thu hồi sẽ khác với một thiết kế đọc trạng thái grant khi dùng. Không hứa thu hồi tức thời nếu đường thực thi không có cơ chế đáp ứng lời hứa đó.

## 16. Danh tính workload và nguy cơ dùng quyền quá rộng

Giả sử Minh yêu cầu ReportService tạo bản xuất của báo cáo được ủy quyền. ReportService có tài khoản workload truy cập nhiều tài liệu để phục vụ hệ thống.

Nếu dịch vụ chỉ dùng quyền rộng của mình rồi trả dữ liệu theo tài nguyên Minh yêu cầu, nó có thể thực hiện hành động vượt quá delegation của Minh. Đây là một tình huống dịch vụ có thẩm quyền bị dẫn dắt thực hiện công việc cho bên không đủ quyền.

Ngữ cảnh cần giữ rõ:

~~~text
actorWorkload    = report-service
requestingUser   = user:minh
delegationId     = dg-101
resource         = document:report-42
requestedAction  = document:export
~~~

Trong grant ban đầu, dg-101 chỉ có read và comment. Backend không được tự coi export là read nếu policy phân biệt hai thao tác. Việc service có thể đọc file trong kho không làm phát sinh quyền cho Minh xuất file đó.

Cần phân quyền đúng các mốc:

1. Minh yêu cầu tạo job.
2. Job thực sự đọc và xuất tài liệu.
3. Minh hoặc người khác tải tệp kết quả.

Nếu delegation hết hạn trước khi job bắt đầu, policy của ví dụ yêu cầu kiểm tra lại và chặn. Nếu sản phẩm muốn tạo một quyền thực hiện job độc lập ngay khi nhận yêu cầu, phải mô hình hóa quyền đó, thời hạn và cơ chế hủy một cách rõ ràng.

Không giữ nguyên toàn bộ token người dùng trong log hoặc thông điệp hàng đợi chỉ để “đỡ mất context”. Có thể dùng định danh công việc và bằng chứng ủy quyền được bảo vệ theo thiết kế, đồng thời hạn chế quyền của chính workload.

## 17. Audit phải giữ được nguồn quyền và người thực hiện

Một hệ thống delegation cần trả lời được ai đã cấp quyền, ai đã dùng và quyền nào được dùng làm căn cứ.

Sự kiện tạo grant minh họa:

~~~json
{
  "event": "delegation_created",
  "grantId": "dg-101",
  "grantor": "user:lan",
  "grantee": "user:minh",
  "resource": "document:report-42",
  "actions": ["document:read", "document:comment"],
  "authorityBasis": "CURRENT_OWNER",
  "parentGrantId": null,
  "allowRedelegation": false,
  "grantVersion": 1
}
~~~

Sự kiện sử dụng quyền minh họa:

~~~json
{
  "event": "delegated_access_enforced",
  "actor": "user:minh",
  "resource": "document:report-42",
  "action": "document:comment",
  "grantId": "dg-101",
  "decision": "Permit",
  "enforcementResult": "comment_committed",
  "relationRevision": "revision-782",
  "requestId": "req-619"
}
~~~

Các giá trị event và revision ở đây do ứng dụng tự định nghĩa. Chỉ ghi comment_committed sau khi thay đổi đã commit theo hợp đồng giao dịch; PDP trả Permit chưa chứng minh thao tác thành công.

Với chuỗi nhiều cấp, cần lưu hoặc có khả năng truy xuất chuỗi nguồn quyền tại thời điểm quyết định. Chỉ giữ leaf grant hiện tại có thể không đủ nếu bản ghi cha bị chỉnh hoặc xóa sau đó.

Audit log cũng chứa quan hệ nhạy cảm giữa người dùng và tài liệu. Không công bố toàn bộ đồ thị quyền cho người chỉ được đọc một tài liệu, và không ghi token hoặc thông tin phiên vào log.

## 18. Tình huống kiểm thử cần có

Kiểm thử delegation cần bao phủ việc tạo, sử dụng, thay đổi và thu hồi.

| Tình huống | Kết quả mong đợi theo mô hình của bài |
|---|---|
| Owner cấp read và comment trong thời hạn cho phép | Tạo grant đúng scope và lưu nguồn cấp |
| Viewer tự cấp quyền cho người khác | Từ chối nếu viewer không có authority để ủy quyền |
| Client tự khai grantor là owner | Không thay thế principal đã xác thực |
| Người nhận truy cập đúng tài nguyên, action và thời gian | Cho phép qua một đường quyền hợp lệ |
| Người nhận dùng cùng grant để xóa hoặc export | Từ chối nếu hành động không được cấp |
| Actor khác dùng grantId của Minh | Không cấp quyền theo grant dành riêng cho Minh |
| Grant chưa tới notBefore hoặc đúng tại expiresAt | Không cho sử dụng |
| Minh ủy quyền tiếp khi allowRedelegation bằng false | Không tạo grant con |
| Grant con mở rộng tài nguyên, action hoặc thời hạn | Từ chối |
| Grant con trỏ tới một parent không liên quan | Từ chối |
| Chuỗi có vòng lặp hoặc quá giới hạn duyệt | Không cấp Permit cho đường đó |
| Grant cha bị thu hồi | Grant con không còn căn cứ trong mô hình phụ thuộc |
| Lan mất ownership | Grant phụ thuộc CURRENT_OWNER không còn hợp lệ |
| Quyền của An có thêm một nguồn độc lập | Thu hồi một chuỗi không xóa nguồn độc lập |
| Grant thay đổi trong lúc tạo con | Phát hiện xung đột hoặc đánh giá lại theo hợp đồng |
| Cache còn dữ liệu cha cũ | Hành vi thu hồi đáp ứng cam kết về độ mới |
| Job dùng service account quyền rộng | Vẫn kiểm tra phạm vi người yêu cầu và grant |
| Token còn hạn nhưng grant bị thu hồi | Hành vi đúng với mô hình kiểm tra trạng thái đã công bố |
| Kho quan hệ bị lỗi | Không tự cho phép vì thiếu dữ kiện |

Ở kiểm thử API, cần xác minh không chỉ mã trạng thái mà cả tác động: grant không hợp lệ có bị ghi không, dữ liệu có bị xuất không và sự kiện nghiệp vụ có được phát nhầm không.

Đối với thu hồi, nên kiểm tra trên chính đường truy cập có cache, bản sao dữ liệu hoặc job nền. Chạy kiểm thử trực tiếp vào kho chính không chứng minh mọi PEP trong hệ thống nhìn thấy thay đổi đúng thời hạn.

## 19. Tự kiểm tra kiến thức

**Có quyền đọc tài liệu thì được ủy quyền quyền đọc cho người khác không?**

Không thể suy ra như vậy. Policy phải cấp riêng thẩm quyền tạo delegation hoặc xác định rõ quan hệ nào cho phép việc đó.

**Ủy quyền có bắt buộc thay owner không?**

Không. Owner có thể giữ nguyên; người nhận chỉ có tập hành động trong phạm vi được cấp.

**Vì sao lưu một cạnh delegated_reader có thể chưa đủ?**

Cạnh đó chưa thể hiện đầy đủ nguồn cấp, thời hạn, grant cha và quy tắc thu hồi. Nếu sản phẩm cần các yếu tố này, mô hình và bộ đánh giá phải bổ sung chúng.

**Khi grant cha bị thu hồi, có cần xóa mọi grant con trước khi chặn không?**

Không nhất thiết. Nếu bộ đánh giá luôn kiểm tra phụ thuộc theo dữ liệu đủ mới, grant con có thể bị chặn ngay khi cha mất hiệu lực. Nếu chỉ dựa vào cập nhật con bất đồng bộ, phải xử lý khoảng trễ tương ứng.

**Owner được thay đổi rồi trở lại, grant đã revoked có tự active không?**

Trong mô hình của bài, không. Thu hồi có chủ đích khác với tạm ngừng vì điều kiện nguồn chưa đáp ứng.

**Một token có scope document:read chứng minh được đọc mọi tài liệu không?**

Không. Scope có thể chỉ là một phần của quyết định; hệ thống còn phải kiểm tra tài nguyên, quan hệ, tenant và các điều kiện liên quan.

**Vì sao cần ghi cả actor và nguồn thẩm quyền?**

Actor cho biết ai thực hiện. Nguồn thẩm quyền giải thích tại sao hành động được cấp quyền. Hai thông tin phục vụ các câu hỏi kiểm toán khác nhau.

## 20. Áp dụng vào thiết kế IAM

Delegated access cần được thiết kế như một quan hệ quyền có nguồn gốc, phạm vi và vòng đời. Trước khi triển khai, hãy xác định rõ loại authority được phép tạo grant, những giới hạn phải giữ qua mỗi cấp và hành vi khi nguồn cấp thay đổi.

Khi grant được sử dụng, hệ thống phải kiểm tra người thực hiện, tài nguyên, hành động, thời gian và chuỗi phụ thuộc theo ngữ nghĩa đã chọn. Sự tồn tại của bản ghi, ID grant hoặc token có chữ ký chưa tự thay thế quá trình kiểm tra đó.

PEP phải bảo vệ đường thực thi thực tế, từ API tương tác đến workload và job nền. Audit cần giữ được nguồn quyền đã dùng; cache và cơ chế thu hồi phải đáp ứng thời gian hiệu lực mà sản phẩm cam kết.

## Tài liệu tham khảo

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): tham chiếu delegation, impersonation, actor và giới hạn về liên kết vòng đời token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security, mục 2.3](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.3): giới hạn đặc quyền và audience của access token.

