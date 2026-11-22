# Quản lý quyền đặc quyền bằng Privileged Identity Management

## 1. Mục tiêu bài học

Trong module Microsoft Azure, danh tính và quyền truy cập là lớp bảo vệ xuyên suốt subscription, resource group, mạng, máy ảo, lưu trữ, dữ liệu và các công cụ vận hành. Người quản trị có thể cần quyền rất mạnh để khắc phục sự cố hoặc thay đổi cấu hình, nhưng việc duy trì quyền này liên tục làm tăng rủi ro nếu tài khoản bị chiếm đoạt hay thao tác nhầm.

Sau bài học, bạn có thể:

- Giải thích nguyên tắc **quyền tối thiểu** (least privilege) và **cấp quyền đúng thời điểm** (just-in-time, JIT).
- Phân biệt vai trò **eligible**, **active**, thời hạn được gán và thời gian kích hoạt.
- Hiểu Microsoft Entra Privileged Identity Management (PIM) quản lý vai trò trong Entra ID, Azure resources và nhóm như thế nào.
- Mô tả cách cấu hình điều kiện kích hoạt, yêu cầu phê duyệt, MFA, lý do, mã phiếu xử lý và thông báo.
- Thực hành quy trình gán vai trò đủ điều kiện, kích hoạt tạm thời, kiểm tra và xem lịch sử hoạt động.
- Nhận diện giới hạn của PIM và kết hợp PIM với RBAC, Conditional Access, giám sát và đánh giá quyền định kỳ.

## 2. Rủi ro của quyền quản trị thường trực

Giả sử một kỹ sư cần vai trò **Owner** ở subscription để xử lý một sự cố hiếm gặp. Nếu vai trò Owner luôn hoạt động, tài khoản của kỹ sư có thể thay đổi tài nguyên, cấp quyền cho người khác hoặc xóa thành phần quan trọng ngay cả ngoài giờ xử lý sự cố. Một lần lộ thông tin đăng nhập sẽ làm tăng đáng kể phạm vi thiệt hại.

Các vấn đề thường gặp của quyền quản trị thường trực gồm:

- **Đặc quyền dư thừa:** người dùng vẫn có quyền sau khi dự án, ca trực hoặc nhiệm vụ kết thúc.
- **Khó kiểm soát thời điểm:** không rõ ai đang thực sự cần quyền cao và để làm gì.
- **Khó truy vết:** việc cấp quyền không gắn với yêu cầu xử lý hoặc người phê duyệt.
- **Tăng tác động khi tài khoản bị xâm nhập:** kẻ tấn công có thể sử dụng ngay vai trò đang hoạt động.
- **Phân quyền quá rộng:** cấp Owner ở subscription khi nhiệm vụ chỉ cần Contributor ở một resource group.

**Microsoft Entra Privileged Identity Management** là dịch vụ quản lý đặc quyền, giúp quản trị việc gán, kích hoạt và giám sát quyền quan trọng. PIM cho phép một người được xác định là đủ điều kiện nhận vai trò, sau đó chỉ kích hoạt vai trò khi thực sự cần và trong thời gian được giới hạn.

PIM không thay thế RBAC. RBAC quyết định **vai trò có những quyền nào và ở scope nào**; PIM bổ sung quy trình **ai có thể kích hoạt vai trò, khi nào, trong bao lâu và dưới điều kiện nào**.

## 3. Những khái niệm cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Privileged role | Vai trò có quyền truy cập hoặc quản trị nhạy cảm | Global Administrator, Privileged Role Administrator, Owner |
| Eligible assignment | Người dùng đủ điều kiện để yêu cầu kích hoạt vai trò | Kỹ sư có thể kích hoạt Contributor tại resource group production |
| Active assignment | Quyền vai trò đang có hiệu lực mà không cần bước kích hoạt cho lần sử dụng đó | Kỹ sư đã kích hoạt Contributor trong 2 giờ |
| Permanent eligible | Tư cách đủ điều kiện không có ngày hết hạn được đặt trước | Kỹ sư có thể kích hoạt khi cần theo chính sách |
| Time-bound eligible | Tư cách đủ điều kiện chỉ tồn tại trong một khoảng thời gian | Được quyền yêu cầu kích hoạt trong 7 ngày dự án |
| Activation | Hành động người dùng thực hiện để chuyển quyền eligible thành quyền hoạt động tạm thời | Kích hoạt Security Reader trong 1 giờ |
| Approval | Bước người phê duyệt xét duyệt yêu cầu kích hoạt nếu chính sách yêu cầu | Trưởng ca chấp thuận phiên xử lý sự cố |
| Role settings | Các điều kiện và giới hạn quản lý việc kích hoạt/gán vai trò | MFA, thời lượng tối đa, lý do, phê duyệt, thông báo |
| Access review | Đánh giá định kỳ việc người dùng còn cần quyền được gán hay không | Rà soát eligible assignment mỗi quý |

Một người có thể có **eligible assignment** tồn tại trong vài tháng nhưng mỗi lần **activation** chỉ được phép trong một hoặc hai giờ. Hai khoảng thời gian này độc lập. Khi hết hạn kích hoạt, quyền đang hoạt động được thu hồi theo cơ chế PIM; khi hết hạn eligible assignment, người dùng không còn đủ điều kiện yêu cầu kích hoạt vai trò đó.

**Eligible không đồng nghĩa active.** Một vai trò eligible chỉ mang lại khả năng gửi yêu cầu kích hoạt. Đến khi kích hoạt thành công, điều kiện chính sách được đáp ứng và hiệu lực được cập nhật, người dùng mới có quyền tương ứng.

## 4. PIM bảo vệ những loại quyền nào?

PIM cung cấp các trải nghiệm quản lý khác nhau. Không nên nhầm vai trò quản trị danh tính với vai trò quản trị tài nguyên Azure.

| Phạm vi | Đối tượng tiêu biểu | Ví dụ nhiệm vụ |
|---|---|---|
| **Microsoft Entra roles** | Global Administrator, Privileged Role Administrator, Security Administrator, User Administrator | Quản lý danh tính, vai trò thư mục và chính sách danh tính |
| **Azure resources** | Vai trò Azure RBAC tại management group, subscription, resource group hoặc resource | Thay đổi cấu hình VM, network, storage hay quyền truy cập tài nguyên |
| **PIM for Groups** | Quyền thành viên hoặc chủ sở hữu của nhóm được đưa vào PIM | Kích hoạt tư cách thành viên nhóm dùng để nhận quyền theo nhóm |

Trong một số môi trường, nhóm có thể được gán vai trò hoặc quyền vào tài nguyên. Khi đó, **PIM for Groups** có thể cung cấp quy trình kích hoạt tư cách thành viên hoặc chủ sở hữu nhóm, qua đó ảnh hưởng đến quyền được cấp thông qua nhóm. Mô hình hỗ trợ, loại nhóm và giới hạn thực tế phụ thuộc tính năng cùng cấu hình tenant; phải kiểm tra trước khi chọn giải pháp.

Ví dụ quan trọng:

- **Global Administrator** là vai trò quản trị thư mục Microsoft Entra ID; nó không mặc nhiên là Owner của mọi Azure subscription.
- **Owner** ở resource group là vai trò Azure RBAC trên phạm vi resource group đó; nó không tự biến người dùng thành Global Administrator.
- **Contributor** có thể quản lý nhiều cấu hình tài nguyên trong scope được cấp, nhưng thông thường không có quyền cấp vai trò Azure RBAC như Owner hoặc User Access Administrator.

Vì vậy, trước khi cấu hình PIM hãy xác định chính xác **loại vai trò, phạm vi quyền và nhiệm vụ cần thực hiện**.

## 5. Cách PIM kết hợp với RBAC và Conditional Access

Một quyết định truy cập đặc quyền có nhiều lớp:

1. **Xác thực:** tài khoản đăng nhập Microsoft Entra ID; các yêu cầu xác thực và Conditional Access có thể được áp dụng.
2. **Tư cách đủ điều kiện:** PIM kiểm tra người dùng có eligible assignment ở vai trò và scope được yêu cầu hay không.
3. **Điều kiện kích hoạt:** chính sách vai trò có thể yêu cầu MFA, authentication context, lý do, thông tin ticket hoặc phê duyệt.
4. **Cấp quyền tạm thời:** khi yêu cầu hợp lệ và được chấp thuận nếu cần, vai trò active trong khoảng thời gian cho phép.
5. **Ủy quyền tác vụ:** dịch vụ đích kiểm tra quyền RBAC hoặc quyền vai trò Entra đang có hiệu lực trước khi cho phép thao tác.
6. **Ghi nhận và kết thúc:** lịch sử kích hoạt, phê duyệt và thay đổi assignment có thể được tra cứu; quyền hết hiệu lực khi phiên kích hoạt kết thúc theo cơ chế của nền tảng.

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A[Người dùng có eligible assignment] --> B[Yêu cầu kích hoạt vai trò]
    B --> C{Đáp ứng điều kiện?}
    C -->|Chưa| D[Thực hiện MFA, nhập lý do hoặc ticket]
    D --> C
    C -->|Có| E{Cần phê duyệt?}
    E -->|Có| F[Người phê duyệt xem yêu cầu]
    F -->|Từ chối| X[Không kích hoạt]
    F -->|Đồng ý| G[Vai trò active có thời hạn]
    E -->|Không| G
    G --> H[Thực hiện công việc theo RBAC]
    H --> I[Hết hạn hoặc kết thúc kích hoạt]
    I --> J[Đối chiếu lịch sử và kiểm toán]
~~~

Luồng thực tế có thể khác tùy vai trò và cài đặt. Ví dụ, điều kiện MFA đã được đáp ứng bởi phiên đăng nhập hợp lệ có thể không luôn tạo thêm màn hình hỏi MFA. Việc cập nhật quyền vào dịch vụ đích cũng có thể cần thời gian lan truyền.

## 6. Chuẩn bị trước khi dùng PIM

Trước khi bật PIM cho một nhóm quản trị, hãy kiểm tra:

**Giấy phép:** PIM là khả năng thuộc các gói Microsoft Entra có quyền sử dụng tính năng quản trị đặc quyền, chẳng hạn Microsoft Entra ID P2 hoặc gói Entra ID Governance phù hợp. Đối tượng cần giấy phép và quyền sử dụng cụ thể phụ thuộc chương trình cấp phép hiện hành. Cần xác minh điều khoản đối với tenant và đối tượng sử dụng thay vì giả định mọi tài khoản Azure đều có PIM.

**Quyền thiết lập:** người cấu hình phải có quyền quản trị PIM và phạm vi vai trò tương ứng. Với vai trò Microsoft Entra, **Privileged Role Administrator** thường là vai trò phù hợp để quản lý assignment và cài đặt vai trò. Với Azure resources, người quản lý cần các quyền thích hợp trên scope Azure, thường là **Owner** hoặc **User Access Administrator**. Một số thao tác có yêu cầu quyền bổ sung; giao diện và vai trò cần thiết phụ thuộc mục tiêu cụ thể.

**Phạm vi:** xác định tenant, subscription, resource group hoặc nhóm cần bảo vệ. Với Azure resources, scope càng hẹp càng giúp hạn chế tác động ngoài ý muốn.

**Danh tính:** người dùng nên có tài khoản cá nhân, thông tin MFA hợp lệ và khả năng hoàn thành yêu cầu Conditional Access. Tránh dùng chung tài khoản quản trị vì làm mất khả năng quy trách nhiệm.

**Người phê duyệt:** nếu yêu cầu approval, chỉ định người có khả năng phản hồi khi xảy ra sự cố; chuẩn bị cơ chế dự phòng khi người phê duyệt chính không sẵn sàng.

**Vận hành khẩn cấp:** thiết kế tài khoản truy cập khẩn cấp theo quy trình bảo mật độc lập, được giám sát chặt và kiểm thử. Không để toàn bộ khả năng khôi phục quyền quản trị phụ thuộc vào một luồng approval có thể bị gián đoạn.

## 7. Cấu hình một vai trò đủ điều kiện

Các nhãn menu có thể thay đổi theo giao diện Microsoft Entra admin center hoặc Azure Portal. Quy trình chung vẫn gồm chọn loại vai trò, scope, người nhận và thiết lập trạng thái eligible/active.

### 7.1. Gán eligible cho Microsoft Entra role

Ví dụ: một thành viên đội an ninh chỉ thỉnh thoảng cần vai trò **Security Administrator**.

1. Đăng nhập **Microsoft Entra admin center** bằng tài khoản có quyền cấu hình vai trò.
2. Mở **Identity Governance → Privileged Identity Management**.
3. Chọn mục quản lý **Microsoft Entra roles** và danh sách **Assignments** hoặc chức năng thêm assignment tương ứng.
4. Chọn vai trò **Security Administrator**, sau đó chọn người dùng cần cấp.
5. Chọn trạng thái **Eligible**; đặt thời điểm bắt đầu và kết thúc của tư cách eligible nếu chính sách yêu cầu.
6. Xem lại phạm vi, người nhận và thời hạn trước khi lưu.
7. Kiểm tra danh sách assignment để xác nhận người dùng đã được gán eligible theo đúng yêu cầu.

Việc gán eligible **không trao quyền Security Administrator ngay lập tức**. Người dùng sẽ cần kích hoạt vai trò khi có công việc và đáp ứng các điều kiện đã cấu hình.

### 7.2. Gán eligible cho vai trò Azure RBAC

Ví dụ: một kỹ sư cần **Contributor** trong resource group có tên **rg-prod-app** để triển khai bản vá, nhưng không cần quyền ở toàn subscription.

1. Trong trải nghiệm PIM, chọn **Azure resources**.
2. Chọn subscription hoặc resource group cần quản lý. Tùy cấu hình, có thể phải khám phá và đưa tài nguyên vào phạm vi quản lý PIM trước.
3. Vào phần **Roles** hoặc **Assignments** của scope đã chọn.
4. Chọn vai trò **Contributor**, người dùng nhận quyền và loại assignment **Eligible**.
5. Đặt khoảng thời gian đủ điều kiện và xác nhận assignment.
6. Kiểm tra vai trò, resource ID/scope và loại assignment sau khi lưu.

Nếu chỉ cần thao tác trên **rg-prod-app**, gán Contributor tại đúng resource group giúp giới hạn quyền tốt hơn so với Contributor tại subscription. Không nên gán Owner chỉ để sửa cấu hình ứng dụng khi Contributor đã đáp ứng nhiệm vụ.

### 7.3. Phân biệt eligible và active khi gán

| Hình thức | Người dùng sử dụng quyền khi nào? | Trường hợp cân nhắc |
|---|---|---|
| Eligible | Sau khi kích hoạt và đáp ứng điều kiện PIM | Quản trị theo nhu cầu, bảo trì, trực vận hành |
| Active có thời hạn | Quyền hoạt động trực tiếp trong khoảng thời gian được gán | Một nhiệm vụ ngắn cần liên tục trong thời gian xác định |
| Active lâu dài | Quyền hoạt động liên tục trong thời gian assignment còn hiệu lực | Chỉ cân nhắc khi có căn cứ vận hành rõ ràng và cơ chế kiểm soát tương ứng |

Mục tiêu là giảm số quyền hoạt động thường trực và giảm scope cấp quyền. Tuy nhiên, không nên cưỡng ép mọi loại tài khoản, dịch vụ hoặc quy trình tự động vào cùng một cách kích hoạt dành cho người dùng tương tác.

## 8. Thiết lập chính sách kích hoạt vai trò

Các thiết lập có thể được quản lý **theo vai trò và phạm vi**. Cấu hình cho vai trò Microsoft Entra và vai trò Azure resource không nhất thiết nằm ở cùng một trang.

| Thiết lập | Tác dụng | Ví dụ chính sách nội bộ |
|---|---|---|
| Maximum activation duration | Giới hạn một lần kích hoạt được kéo dài bao lâu | Contributor: tối đa 2 giờ |
| Require MFA | Yêu cầu mức xác thực phù hợp khi kích hoạt | Bắt buộc xác thực đa yếu tố |
| Conditional Access authentication context | Áp điều kiện xác thực theo chính sách liên quan | Chỉ kích hoạt khi đạt mức xác thực yêu cầu |
| Require justification | Buộc nhập lý do sử dụng quyền | “Khắc phục lỗi triển khai phiên bản 2.3” |
| Ticket information | Yêu cầu mã hoặc thông tin yêu cầu xử lý | “INC-2026-0427” |
| Require approval | Buộc một người có trách nhiệm phê duyệt kích hoạt | Trưởng ca SRE chấp thuận |
| Activation notifications | Gửi thông báo về sự kiện kích hoạt theo cấu hình | Thông báo tới người quản trị liên quan |
| Assignment settings | Giới hạn hình thức và thời hạn gán quyền | Eligible tối đa trong giai đoạn dự án |

**Lưu ý:** Bảng trên là ví dụ thiết kế chính sách. Các mức thời gian và tùy chọn cụ thể phải kiểm tra trong giao diện/dịch vụ và theo hạn mức của loại vai trò. Không có một “chính sách PIM mặc định tốt nhất” cho mọi tenant.

Khi cấu hình:

1. Chọn đúng vai trò và scope.
2. Xác định mức nhạy cảm của quyền cùng rủi ro thao tác.
3. Quy định thời lượng kích hoạt phù hợp với nhiệm vụ thực tế.
4. Bật điều kiện xác thực, justification và approval theo chính sách.
5. Kiểm tra người phê duyệt và luồng thông báo bằng một tài khoản thử nghiệm có quyền phù hợp.
6. Xác minh khả năng kết thúc quyền sau khi hết phiên và khả năng truy xuất audit.

Approval có thể làm tăng thời gian xử lý sự cố, nên đội vận hành cần quy định người phê duyệt dự phòng và đường xử lý trường hợp khẩn cấp. Ngược lại, bỏ yêu cầu xác thực và approval cho các vai trò nhạy cảm có thể làm mất ý nghĩa của mô hình JIT.

## 9. Người dùng kích hoạt vai trò như thế nào?

Giả sử người dùng đã có eligible assignment **Contributor** ở **rg-prod-app** và cần triển khai bản vá.

1. Truy cập Microsoft Entra PIM từ Portal hoặc Entra admin center.
2. Mở **My roles**, chọn phạm vi **Azure resources**; với vai trò thư mục, chọn **Microsoft Entra roles**.
3. Tìm vai trò eligible cần dùng và chọn **Activate**.
4. Chọn thời lượng, nhập justification và ticket nếu chính sách yêu cầu.
5. Hoàn thành các điều kiện xác thực. Nếu cần approval, chờ người được chỉ định phê duyệt.
6. Khi PIM xác nhận activation thành công, kiểm tra vai trò đang **Active** và thời gian hết hạn.
7. Thực hiện đúng công việc được giao; kết thúc phiên kích hoạt sớm nếu không cần tiếp tục sử dụng quyền và giao diện/chính sách hỗ trợ.
8. Kiểm tra lịch sử kích hoạt để bảo đảm hành động được ghi nhận.

Một số vai trò có thể chưa sử dụng được ngay sau khi PIM báo thành công vì quyền đang lan truyền hoặc công cụ đang dùng còn giữ phiên/token cũ. Khi cần, làm mới phiên đăng nhập hoặc phiên quản lý và kiểm tra lại quyền trên dịch vụ đích. Không nên tự nâng quyền ở scope rộng hơn để “khắc phục” vấn đề lan truyền.

Nếu yêu cầu bị từ chối, người dùng nên đọc lý do, kiểm tra thông tin ticket/scope rồi gửi lại theo quy trình; không coi việc có eligible assignment là quyền bỏ qua approval.

## 10. Ví dụ xuyên suốt: xử lý sự cố ứng dụng production

Một ứng dụng chạy trên Azure dùng VM, virtual network và storage account trong resource group **rg-prod-app**. Kỹ sư vận hành cần cập nhật cấu hình VM trong sự cố sản xuất, nhưng phần lớn thời gian chỉ cần quyền Reader.

**Trạng thái bình thường:**

- Kỹ sư có Reader tại scope phù hợp để giám sát và xem cấu hình.
- Kỹ sư có eligible assignment Contributor tại **rg-prod-app**.
- Chính sách Contributor yêu cầu MFA, justification, mã ticket, approval và thời lượng tối đa 2 giờ.
- Không cấp Owner nếu nhiệm vụ không cần quản lý phân quyền.

**Trong sự cố:**

1. Hệ thống giám sát báo lỗi và tạo ticket **INC-2026-0427**.
2. Kỹ sư kiểm tra log và xác định cần sửa cấu hình của một VM.
3. Kỹ sư mở PIM và yêu cầu kích hoạt Contributor ở **rg-prod-app** trong 60 phút.
4. Kỹ sư hoàn tất xác thực, nhập ticket và nêu lý do.
5. Trưởng ca kiểm tra yêu cầu, scope và tác động dự kiến rồi phê duyệt.
6. Sau khi kích hoạt thành công, kỹ sư sửa cấu hình trong scope được cấp và kiểm tra ứng dụng.
7. Khi xử lý xong, kỹ sư kết thúc phiên kích hoạt nếu có thể; quyền cũng được thiết kế để tự hết hạn.
8. Đội vận hành đối chiếu ticket, lịch sử PIM, Azure Activity Log và các log cần thiết để phục vụ hậu kiểm.

**Điểm cần phân biệt:** nhật ký PIM giúp trả lời **ai yêu cầu hoặc kích hoạt quyền, lúc nào và theo điều kiện nào**. Azure Activity Log và log của dịch vụ đích giúp điều tra **tài nguyên đã bị thay đổi ra sao**. Muốn có bức tranh đầy đủ, phải kết hợp các nguồn này.

## 11. Giám sát, kiểm toán và rà soát quyền

Cấp quyền JIT mới là một nửa vòng đời quản trị. Nửa còn lại là phát hiện quyền dư thừa, theo dõi kích hoạt bất thường và kiểm tra định kỳ.

### 11.1. Những gì cần kiểm tra

| Dữ liệu | Câu hỏi cần trả lời |
|---|---|
| Role assignments | Ai đang eligible hoặc active đối với vai trò nào, ở scope nào? |
| Activation history | Ai đã kích hoạt, trong bao lâu và với lý do gì? |
| Approval history | Ai phê duyệt hoặc từ chối yêu cầu? |
| Audit history | Assignment hay role settings đã thay đổi khi nào và bởi ai? |
| Alerts | Có dấu hiệu số lượng quản trị viên đặc quyền quá nhiều hoặc assignment bất thường không? |
| Access reviews | Người dùng còn có nhu cầu giữ assignment không? |

Tùy loại tài nguyên và khả năng tích hợp, dữ liệu có thể xem trong các trang lịch sử, audit hoặc alerts của PIM; để phân tích tập trung có thể cần cấu hình xuất nhật ký và thời gian lưu trữ phù hợp. Không mặc định rằng mọi nhật ký đều được giữ vô thời hạn.

### 11.2. Quy trình đánh giá quyền định kỳ

1. Liệt kê các vai trò nhạy cảm và mọi assignment eligible/active liên quan.
2. Xác minh owner của tài khoản, công việc hiện tại và sự cần thiết của từng vai trò.
3. Kiểm tra các assignment có scope quá rộng, không có thời hạn hoặc không còn người chịu trách nhiệm.
4. Yêu cầu quản lý hoặc chủ hệ thống xác nhận giữ hay thu hồi quyền.
5. Thu hồi eligible assignment không còn cần thiết theo quy trình.
6. Lưu bằng chứng về quyết định, thời điểm và người phê duyệt.

Access review giúp đánh giá **quyền có còn cần thiết hay không**, còn lịch sử activation cho thấy **quyền đã được sử dụng như thế nào**. Cả hai đều hữu ích và phục vụ mục đích khác nhau.

## 12. Vận hành PIM cho nhóm

PIM for Groups được cân nhắc khi tổ chức quản lý quyền thông qua nhóm thay vì gán trực tiếp mọi vai trò cho từng cá nhân. Ví dụ, một nhóm bảo trì được gán quyền ở resource group nhất định; người dùng chỉ trở thành thành viên active của nhóm trong phiên xử lý đã được cho phép.

Quy trình khái niệm:

1. Xác định nhóm đủ điều kiện được quản lý bằng PIM và cách nhóm đang được dùng để cấp quyền.
2. Thiết lập eligible membership hoặc ownership cho các cá nhân phù hợp.
3. Cấu hình giới hạn thời gian và điều kiện kích hoạt.
4. Người dùng kích hoạt tư cách thành viên/owner khi có nhiệm vụ.
5. Kiểm tra quyền hiệu lực trong hệ thống đích, kể cả độ trễ đồng bộ hoặc token.
6. Rà soát tư cách eligible và lịch sử activation.

Cần phân biệt **quyền thành viên nhóm** với **vai trò Entra/Azure được gán cho nhóm**. Kích hoạt thành viên chỉ trao các quyền mà nhóm thực sự có trong phạm vi tương ứng. Việc người dùng trở thành member của một nhóm không mặc nhiên tạo quyền Owner hay Global Administrator.

## 13. Các giới hạn và tình huống cần chú ý

**PIM dành cho quản trị đặc quyền, không xử lý mọi loại danh tính.** Service principal, managed identity, tài khoản ứng dụng và các hình thức ủy quyền máy với máy có mô hình riêng. Không giả định rằng chỉ bật PIM là tự động kiểm soát vòng đời bí mật, quyền API hoặc quyền của workload identity.

**Hết hạn activation không luôn đồng nghĩa mọi kết nối bị cắt tức thì.** Hệ thống đích có thể dùng token, cache hoặc độ trễ đồng bộ quyền. Khi kiểm thử, hãy kiểm tra cả trạng thái trong PIM và khả năng thực hiện hành động thực tế.

**RBAC quá rộng vẫn là rủi ro.** PIM giới hạn thời gian nhưng không làm quyền Owner trở nên tương đương Reader. Hãy thu hẹp role và scope trước khi thêm quy trình kích hoạt.

**Có thể tồn tại đường cấp quyền khác.** Người dùng có thể nhận quyền qua assignment active trực tiếp, nhóm khác hoặc vai trò ở scope cha. Thu hồi một eligible assignment không nhất thiết xóa mọi đường truy cập tương đương.

**MFA và Conditional Access cần được vận hành đồng bộ.** Cấu hình kích hoạt có điều kiện nhưng thiếu phương thức xác thực hoặc chặn sai đối tượng có thể gây gián đoạn. Kiểm thử bằng tài khoản và luồng người dùng thực tế.

**Approval không thay thế đánh giá tác động thay đổi.** Người phê duyệt quyền nên biết người yêu cầu, lý do và phạm vi; việc thay đổi một hệ thống production vẫn có thể cần quy trình change management riêng.

**Quyền truy cập khẩn cấp phải được quản lý cẩn thận.** Có phương án dự phòng tránh khóa toàn bộ tổ chức, nhưng phải bảo vệ chứng thực, ghi nhận hoạt động và kiểm thử định kỳ.

## 14. So sánh kiểm soát quyền thường trực và PIM

| Tiêu chí | Vai trò active thường trực | Eligible qua PIM |
|---|---|---|
| Quyền sẵn sàng sử dụng | Thường có sẵn ngay khi đăng nhập và quyền được áp dụng | Phải kích hoạt trước khi sử dụng |
| Giới hạn thời gian sử dụng đặc quyền | Không có theo phiên nếu không được cấu hình khác | Có thể giới hạn thời gian từng activation |
| Lý do sử dụng quyền | Không tự phát sinh ở bước truy cập | Có thể yêu cầu justification/ticket |
| Phê duyệt trước khi sử dụng | Không tự phát sinh | Có thể đặt approval |
| Kiểm tra lịch sử | Cần kết hợp audit của hệ thống đích | Có dữ liệu về yêu cầu, kích hoạt, approval và thay đổi assignment |
| Rủi ro khi tài khoản bị lộ | Đặc quyền có thể đã hoạt động | Kẻ tấn công còn phải vượt qua điều kiện kích hoạt, nếu được cấu hình đúng |
| Độ phức tạp vận hành | Ít bước cho người dùng, nguy cơ đặc quyền tồn dư | Cần quản lý policy, người duyệt, MFA và đường xử lý sự cố |

PIM giúp giảm bề mặt tấn công của quyền cao, nhưng hiệu quả phụ thuộc cách thiết kế chính sách, xác thực, scope và khả năng giám sát.

## 15. Thực hành có hướng dẫn trong môi trường thử nghiệm

**Bối cảnh:** Bạn quản lý một resource group thử nghiệm và muốn một kỹ sư chỉ được quyền Contributor trong một phiên bảo trì ngắn.

**Điều kiện chuẩn bị:** tenant đã có quyền sử dụng PIM; có tài khoản quản lý PIM/role assignment với quyền phù hợp; có resource group thử nghiệm; người dùng thử nghiệm có thể hoàn thành MFA và approval nếu bật.

**Nhiệm vụ:**

1. Xem các role assignment hiện tại của resource group để tránh cấp trùng quyền qua một assignment active khác.
2. Cấu hình Contributor dưới dạng eligible cho người dùng thử nghiệm tại resource group.
3. Thiết lập thời gian kích hoạt ngắn, yêu cầu justification và ít nhất một điều kiện xác thực phù hợp chính sách thử nghiệm.
4. Đăng nhập bằng tài khoản người dùng thử nghiệm; xác nhận không thể thực hiện một thao tác ghi yêu cầu Contributor khi vai trò chưa active và không tồn tại quyền khác cho phép.
5. Yêu cầu activation với lý do “Bảo trì thử nghiệm”, hoàn tất điều kiện và approval nếu bật.
6. Xác minh vai trò active và thực hiện **một thao tác ghi có thể hoàn tác** trên tài nguyên thử nghiệm theo quyền đã cấp.
7. Kết thúc hoặc chờ hết thời gian kích hoạt; làm mới phiên/token khi cần, rồi kiểm tra lại khả năng thao tác ghi.
8. Mở lịch sử PIM, đối chiếu thời điểm activation và hoạt động của resource group.
9. Gỡ eligible assignment thử nghiệm khi hoàn thành bài thực hành, theo quyền và quy trình được cho phép.

**Kết quả mong đợi:** người dùng có thể kích hoạt Contributor trong thời hạn cấu hình, các điều kiện được kiểm tra, và sự kiện kích hoạt được ghi nhận. Không kết luận bài thực hành thành công chỉ vì PIM hiện trạng thái Active; hãy kiểm tra quyền thực tế và khả năng hết hiệu lực.

Nếu môi trường chưa có giấy phép hoặc bạn không có quyền quản lý assignment, có thể dùng bài tập thiết kế trên giấy: lập một bảng gồm vai trò, scope, lý do, thời gian tối đa, MFA, approver, người nhận thông báo và quy trình xử lý khẩn cấp. Không cần cố gắng thay đổi cấu hình tenant khi chưa đủ điều kiện.

## 16. Câu hỏi tự kiểm tra

1. Một người có eligible assignment Global Administrator có tự động được thực hiện thay đổi người dùng ngay không? Vì sao?
2. Vai trò Owner ở một resource group khác Global Administrator ở điểm nào?
3. Vì sao thời hạn của eligible assignment và thời lượng activation cần được cấu hình riêng?
4. Nếu người dùng báo đã activate Contributor nhưng Azure vẫn trả lỗi thiếu quyền, bạn cần kiểm tra những vấn đề gì?
5. Tại sao không thể chỉ dựa vào lịch sử PIM để biết toàn bộ thay đổi cấu hình đã diễn ra?
6. Khi một assignment được thu hồi nhưng người dùng vẫn có quyền, những đường cấp quyền thay thế nào cần kiểm tra?

**Gợi ý:** tập trung vào trạng thái eligible/active, loại role, scope, quyền kế thừa hoặc nhóm, độ trễ truyền quyền, token và dữ liệu kiểm toán từ hệ thống đích.

## 17. Tổng kết

Microsoft Entra Privileged Identity Management đưa nguyên tắc **least privilege** và **just-in-time** vào quản lý vai trò đặc quyền. Với PIM, tổ chức có thể gán quyền dưới dạng eligible, yêu cầu kích hoạt có thời hạn, thêm điều kiện MFA/Conditional Access, justification, ticket, phê duyệt và ghi nhận hoạt động. PIM có các phạm vi riêng cho Microsoft Entra roles, Azure resource roles và nhóm, vì vậy phải chọn đúng vai trò cùng scope trước khi cấu hình.

Trong kiến trúc Azure, PIM là một lớp quản trị danh tính hỗ trợ bảo vệ subscription, resource group và quyền vận hành hạ tầng. Khi kết hợp với RBAC, giám sát, audit, access review và quy trình khẩn cấp, nó giúp giảm quyền thường trực mà vẫn duy trì khả năng xử lý công việc hợp lệ.
