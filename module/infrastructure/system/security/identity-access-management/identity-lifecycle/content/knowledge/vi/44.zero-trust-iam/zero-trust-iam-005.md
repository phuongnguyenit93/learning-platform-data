# Continuous authentication — Xác thực liên tục trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Continuous authentication (xác thực liên tục và đánh giá lại mức tin cậy của phiên)  
> **Phạm vi:** Quản lý vòng đời danh tính trong IAM theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi vai trò thay đổi. Nội dung liên hệ IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, người học có thể:

1. Giải thích **continuous authentication** theo cách tiếp cận Zero Trust và phân biệt với **đăng nhập một lần**, **xác thực lại**, **step-up authentication** và **continuous access evaluation**.
2. Xác định những tín hiệu ảnh hưởng đến **độ tin cậy của một phiên** theo thời gian: trạng thái danh tính, sự kiện JML, phương thức và thời điểm xác thực, thiết bị, phiên, rủi ro và hành động được yêu cầu.
3. Phác thảo luồng phối hợp giữa **IdP/SSO**, **PEP/PDP**, hệ thống quản lý vòng đời, nguồn rủi ro, SCIM và ứng dụng.
4. Thiết kế phản ứng tương xứng cho các biến cố: tiếp tục phiên, yêu cầu xác thực tăng cường, từ chối một hành động hoặc thu hồi phiên và credential.
5. Mô tả giới hạn thu hồi đối với **JWT access token**, **refresh token**, phiên ứng dụng và tài khoản đích khi xảy ra Mover/Leaver.
6. Vận dụng nguyên tắc vào người dùng, nhà thầu, **service account/workload identity**, đồng thời thiết kế kiểm thử, kiểm toán và chỉ số phù hợp.

## 2. Vì sao xác thực một lần không đủ?

Người dùng Mai đăng nhập lúc 08:00 qua IdP bằng phương thức đáp ứng chính sách MFA. Ở thời điểm đăng nhập, Mai có quyền xem tài liệu nhóm Sales. Đến 10:00, Mai chuyển sang Finance; đến 10:15, thiết bị Mai được đánh dấu không còn đáp ứng yêu cầu bảo mật. Nếu ứng dụng tiếp tục cho phép mọi thao tác dựa vào phiên SSO khởi tạo lúc 08:00, **thông tin tin cậy đã cũ** sẽ được sử dụng cho những hành động mới.

**Continuous authentication** trong ngữ cảnh Zero Trust là cách duy trì và **đánh giá lại mức bảo đảm của danh tính, phiên và ngữ cảnh** trong quá trình sử dụng hệ thống. Khi xuất hiện hành động nhạy cảm hoặc tín hiệu quan trọng thay đổi, hệ thống phải quyết định có thể tiếp tục sử dụng phiên, cần xác thực tăng cường, hay phải giới hạn/thu hồi truy cập.

Điều này không có nghĩa máy chủ yêu cầu mật khẩu hoặc MFA cho **mọi HTTP request**. Một mô hình hiệu quả kết hợp:

- **Xác thực ban đầu đủ mạnh**, gắn với danh tính rõ ràng và phiên được quản lý.
- **Kiểm tra hợp lệ của credential** ở nơi xử lý request.
- **Đánh giá lại theo sự kiện hoặc theo rủi ro** với các phiên/tài nguyên cần bảo vệ.
- **Step-up authentication** cho hành động nhạy cảm hoặc khi mức tin cậy hiện tại chưa đủ.
- **Quản lý tuổi phiên, trạng thái token, thu hồi và cấp lại quyền** khi danh tính, vai trò hoặc rủi ro thay đổi.

Hệ thống cần cân bằng giữa độ mới của tín hiệu, bảo mật, hiệu năng, quyền riêng tư và trải nghiệm người dùng. Không có một chu kỳ tái xác thực duy nhất phù hợp cho mọi dữ liệu hay công việc.

### Câu hỏi cốt lõi tại thời điểm request

> “Danh tính này đã được xác thực trước đó. **Các bằng chứng hiện tại có còn đủ để cho phép hành động cụ thể này trên tài nguyên cụ thể này không?**”

Một access token có chữ ký hợp lệ có thể chứng minh bên phát hành và những claim đã được cấp. Nó không tự chứng minh thiết bị **vẫn an toàn**, nhân viên **vẫn giữ vai trò cũ** hoặc thao tác **vẫn nằm trong phạm vi được ủy quyền**.

## 3. Phân biệt các cơ chế dễ bị nhầm lẫn

| Khái niệm | Câu hỏi giải quyết | Khi nào sử dụng? |
|---|---|---|
| **Identity proofing** | Chủ thể khai báo có đúng là người/đối tượng đang đăng ký không? | Thiết lập danh tính, khôi phục danh tính ở mức rủi ro phù hợp |
| **Authentication (AuthN)** | Bên đang đăng nhập có chứng minh được quyền sử dụng danh tính không? | Đăng nhập, tạo phiên, xác thực API client/workload |
| **Session management** | Phiên được duy trì, ràng buộc và kết thúc thế nào? | Trong suốt thời gian dùng ứng dụng |
| **Reauthentication** | Có cần người dùng chứng minh lại danh tính sau một khoảng thời gian/sự kiện không? | Phiên quá cũ, đổi credential, hành động nhạy cảm |
| **Step-up authentication** | Có cần **mức bảo đảm cao hơn hoặc mới hơn** cho hành động này không? | Xuất dữ liệu, duyệt thanh toán, thay chính sách IAM |
| **Continuous authentication** | Mức tin cậy của người dùng/phiên có còn đủ qua thời gian không? | Khi ngữ cảnh và rủi ro thay đổi, hoặc khi chính sách cần đánh giá lại |
| **Continuous access evaluation** | Quyết định **tiếp tục cho phép truy cập** có còn hợp lệ khi quyền/ngữ cảnh thay đổi không? | Sự kiện JML, thu hồi phiên, thiết bị không tuân thủ, thay đổi quyền |
| **Authorization (AuthZ)** | Chủ thể có được thực hiện action trên resource này không? | Tại điểm thực thi chính sách của ứng dụng/API |

**Xác thực liên tục và đánh giá truy cập liên tục có liên hệ chặt chẽ nhưng khác phạm vi.** Một phiên có thể vẫn xác thực đúng là Mai, trong khi quyền đọc dữ liệu Sales đã bị thu hồi do Mover; kết quả phải là **deny**, không cần giả định Mai là kẻ giả mạo. Ngược lại, Mai có thể còn quyền Finance hợp lệ nhưng phiên chưa đáp ứng mức xác thực cho việc duyệt thanh toán; lúc đó có thể yêu cầu **step-up**.

Đối với **workload không có người đăng nhập tương tác**, “liên tục” thường thể hiện qua đánh giá credential, định danh workload, audience, trạng thái triển khai và quyền theo mỗi yêu cầu hoặc sự kiện, thay vì hiển thị màn hình MFA.

## 4. Những tín hiệu thay đổi theo thời gian

Một quyết định truy cập có thể mô tả:

**Decision(t) = Policy(subject(t), session(t), device(t), resource, action, context(t))**

Ký hiệu **t** nhấn mạnh: một số tín hiệu có thể đổi sau thời điểm đăng nhập. Công thức là mô hình tư duy, không phải một giao diện API tiêu chuẩn.

| Nhóm tín hiệu | Ví dụ | Nguồn phù hợp | Điều cần cân nhắc |
|---|---|---|---|
| **Danh tính/vòng đời** | Active/disabled, loại hợp đồng, phòng ban, role, ngày hiệu lực | HRIS, hệ thống quản trị danh tính, IdP, workflow JML | Độ trễ đồng bộ và độ mới; nguồn nào là authoritative |
| **Bằng chứng xác thực** | Phương thức đăng nhập, mức bảo đảm, thời điểm xác thực, xác thực lại | IdP/SSO, thông tin phiên có xác minh | Các claim như auth_time, amr, acr có ngữ nghĩa theo IdP và cấu hình |
| **Phiên/token** | Token còn hạn, đã bị thu hồi, audience, scope, sender constraint | IdP, phiên ứng dụng, introspection/revocation, resource server | JWT tự chứa và cache có thể giữ quyền cũ |
| **Thiết bị/client** | Tuân thủ chính sách, thiết bị được quản trị, dấu hiệu mất bảo vệ | MDM/EDR/thiết bị hoặc hệ thống quản trị endpoint | Tín hiệu có thể trễ, thiếu hoặc không áp dụng cho mọi loại client |
| **Rủi ro** | Phiên có dấu hiệu bất thường, hành vi API đột biến, thay đổi phương thức MFA | Risk engine, giám sát IdP/API/SIEM | Một tín hiệu yếu không đủ kết luận chiếm quyền |
| **Tài nguyên** | Tenant, chủ sở hữu, phân loại dữ liệu, trạng thái nghiệp vụ | Backend và hệ thống sở hữu tài nguyên | Không tin tenant/owner do client tự khẳng định |
| **Hành động** | Read, export, approve, create-key, assume-role | API và chính sách nghiệp vụ | Action nhạy cảm cần mức kiểm tra khác hành động thông thường |

### Độ mới quan trọng hơn số lượng tín hiệu

Đọc nhiều thuộc tính không giúp ích nếu chúng đã lỗi thời. Với từng tín hiệu, thiết kế cần trả lời:

1. **Nguồn phát hành và tính xác thực:** tín hiệu đến từ đâu, có thể bị giả mạo không?
2. **Phạm vi và ràng buộc:** tín hiệu nói về user, thiết bị, session hay workload nào?
3. **Thời điểm hiệu lực:** được quan sát khi nào, còn được phép dùng trong bao lâu?
4. **Thay đổi và vô hiệu hóa:** nguồn phát thông báo ra sao khi role, thiết bị hay phiên thay đổi?
5. **Xử lý khi không có dữ liệu:** ứng dụng từ chối, yêu cầu xác minh thêm hay dùng cache còn hạn theo chính sách?

Không nên coi trạng thái “compliant” của thiết bị quan sát từ nhiều ngày trước tương đương trạng thái đang được cập nhật, nhất là ở tác vụ yêu cầu bảo đảm cao.

## 5. Những sự kiện nào kích hoạt đánh giá lại?

Các hệ thống thực tế thường kết hợp **đánh giá tại request**, **theo thời gian**, **theo sự kiện** và **theo hành vi**.

| Loại kích hoạt | Ví dụ | Phản ứng có thể phù hợp |
|---|---|---|
| Đăng nhập hoặc tạo phiên mới | Người dùng mở ứng dụng Finance | Xác thực theo chính sách; tạo phiên với thời hạn/ràng buộc phù hợp |
| Hành động có rủi ro cao | Export dữ liệu số lượng lớn, tạo API key, thay role | Kiểm tra quyền và mức xác thực; yêu cầu step-up/phê duyệt nếu cần |
| Sự kiện **Mover** | User chuyển Sales → Finance | Đánh giá lại quyền, thu hồi scope cũ, cập nhật phiên/token hoặc từ chối theo quyền hiện tại |
| Sự kiện **Leaver** | Người dùng kết thúc hợp đồng hoặc bị chấm dứt truy cập khẩn cấp | Chặn đăng nhập, kết thúc phiên/refresh token, vô hiệu hóa quyền ở đích, kiểm chứng thu hồi |
| Tín hiệu thiết bị | Thiết bị mất trạng thái tuân thủ | Chặn thao tác nhạy cảm, yêu cầu thiết bị đủ điều kiện hoặc giới hạn phiên |
| Tín hiệu phiên | Phiên bị nghi chiếm, thay phương thức MFA bất thường | Đánh giá mức rủi ro, bắt xác thực lại, thu hồi hoặc cô lập phiên |
| Token/phiên quá cũ | Hết TTL hoặc vượt tuổi xác thực cho thao tác | Tái xác thực/cấp phiên mới theo chính sách |
| Thay đổi chính sách | Owner dữ liệu giảm scope hoặc cập nhật SoD | Kiểm tra phiên/yêu cầu đang hoạt động với chính sách mới |
| Workload thay đổi | Job bị hủy, service decommission, credential nghi lộ | Thu hồi workload identity, giảm scope, xoay credential |

**Step-up phải gắn với lý do cụ thể.** Nếu hệ thống liên tục gửi yêu cầu MFA không có ngữ cảnh, người dùng có thể bị mệt mỏi vì thông báo xác thực (MFA fatigue), còn hệ thống vẫn không chặn được quyền sai tenant. Chỉ tăng cường xác thực khi điều đó giải quyết đúng mức bảo đảm còn thiếu.

## 6. Kiến trúc thực thi: IdP, PEP, PDP và nguồn tín hiệu

Trong Zero Trust IAM, quá trình đánh giá lại thường đi qua hai đường khác nhau:

- **Control plane:** nhận sự kiện vòng đời từ HRIS/hợp đồng, cập nhật IdP và chính sách, provisioning qua SCIM/API, gửi tín hiệu thu hồi.
- **Data plane:** ứng dụng/API kiểm tra token/phiên, yêu cầu quyết định phân quyền và thực thi trên tài nguyên thực.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / Client
    participant I as IdP / SSO
    participant A as API / PEP
    participant P as PDP / Policy
    participant S as Nguồn trạng thái & rủi ro
    participant R as Tài nguyên
    participant L as Audit

    U->>I: Đăng nhập, tạo phiên với AuthN
    I-->>U: Phiên / access token phù hợp
    U->>A: Request action trên resource
    A->>A: Kiểm tra token, issuer, audience, thời hạn
    A->>P: Subject, action, resource, context
    P->>S: Lấy role hiện tại, JML, phiên, thiết bị, rủi ro
    S-->>P: Tín hiệu có thời điểm và độ tin cậy
    P-->>A: Allow / Deny / Need stronger AuthN
    alt Allow
        A->>R: Kiểm tra thêm quyền đối tượng và xử lý
        R-->>U: Dữ liệu được phép
    else Need stronger AuthN
        A-->>U: Yêu cầu step-up theo chính sách
        U->>I: Xác thực lại / tăng mức bảo đảm
        I-->>U: Bằng chứng mới
    else Deny
        A-->>U: Từ chối thao tác
    end
    A->>L: Ghi quyết định, policy, thời điểm
    Note over S,P: Mover/Leaver hoặc tín hiệu mới làm thay đổi đánh giá tiếp theo
~~~

PEP/PDP là **vai trò kiến trúc**, không bắt buộc là hai sản phẩm riêng. PEP có thể nằm trong gateway, API, service mesh hoặc ứng dụng; PDP có thể là policy engine tập trung hoặc phần logic trong backend. Mô hình NIST SP 800-207 còn mô tả Policy Administrator (PA) để quản lý việc thiết lập/chấm dứt đường truy cập theo quyết định.

**Điều quan trọng:** gateway đã xác thực token vẫn chưa bảo đảm API kiểm tra quyền trên **đúng tài nguyên**. Backend cần kiểm tra tenant, chủ sở hữu, loại dữ liệu và action tại nơi có dữ liệu đáng tin.

### Tín hiệu từ IdP có thể được truyền tới ứng dụng bằng cách nào?

Kiến trúc có thể dùng các phương thức phù hợp với sản phẩm:

1. **Request-time lookup / token introspection:** API hoặc thành phần chính sách hỏi nguồn đáng tin về trạng thái khi cần.
2. **Phiên/token có thời hạn ngắn:** giảm thời gian quyền cũ có thể được dùng, kết hợp refresh flow an toàn.
3. **Sự kiện thay đổi trạng thái:** IdP hoặc hệ thống IAM thông báo khi tài khoản bị khóa, quyền bị thu hồi hoặc rủi ro phiên tăng.
4. **Session/claim version:** API kiểm tra phiên hoặc phiên bản quyền có còn phù hợp với trạng thái mới; cần nguồn tin cậy để so sánh.
5. **Cache có giới hạn:** lưu quyết định/tín hiệu nhằm giảm tải nhưng buộc có TTL, phạm vi và cơ chế invalidation thích hợp.

Các hệ sinh thái có thể hỗ trợ **Continuous Access Evaluation (CAE)** hoặc chia sẻ tín hiệu bảo mật qua giao thức như **Shared Signals/CAEP**, nhưng tên gọi và khả năng giữa nhà cung cấp khác nhau. Không được giả định “bật CAE” sẽ làm mọi ứng dụng, token tự chứa và tài khoản cục bộ lập tức tuân theo chính sách mới.

## 7. Từ đánh giá lại đến quyết định cụ thể

Có thể mô tả trạng thái phiên theo một máy trạng thái đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ChuaXacThuc
    ChuaXacThuc --> PhienDuDieuKien: Xác thực thành công
    PhienDuDieuKien --> PhienDuDieuKien: Request đủ quyền và ngữ cảnh
    PhienDuDieuKien --> CanXacThucTangCuong: Hành động nhạy cảm / mức tin cậy thiếu
    CanXacThucTangCuong --> PhienDuDieuKien: Step-up thành công
    CanXacThucTangCuong --> GioiHan: Không đạt chính sách
    PhienDuDieuKien --> GioiHan: Rủi ro tăng / quyền bị giảm
    GioiHan --> PhienDuDieuKien: Điều kiện mới được xác minh và cho phép
    PhienDuDieuKien --> ThuHoi: Leaver / xác nhận chiếm phiên / hết hạn
    CanXacThucTangCuong --> ThuHoi: Thu hồi theo chính sách
    GioiHan --> ThuHoi: Thu hồi hoặc hết hiệu lực
    ThuHoi --> [*]
~~~

Sơ đồ chỉ là mô hình trạng thái logic. Một hệ thống có thể có nhiều phiên trên nhiều thiết bị và nhiều ứng dụng; cần xác định rõ **thu hồi phiên nào, token nào và principal nào**.

### Ma trận ra quyết định minh họa

| Tình huống | Danh tính/quyền | Phiên/ngữ cảnh | Phản ứng |
|---|---|---|---|
| Nhân viên đọc ticket được phân công | Active, đúng role và tenant | Phiên đủ mức yêu cầu | **Allow** |
| Nhân viên mở chức năng export nhạy cảm | Active, có quyền export | Lần xác thực phù hợp đã quá cũ | **Step-up** hoặc deny theo policy |
| Nhân viên mở hóa đơn tenant khác | Active, MFA tốt | Sai phạm vi tài nguyên | **Deny**, MFA mới cũng không tạo thêm quyền |
| Người dùng vừa Mover khỏi Sales | Role Sales đã bị thu hồi | JWT cũ còn claim Sales | **Deny** khi nguồn quyền hiện tại được áp dụng |
| Người dùng Leaver | Danh tính inactive | Token có thể vẫn hợp lệ về mặt chữ ký | **Deny** nếu đường chặn hiện hành đã có hiệu lực |
| Thiết bị bị đánh dấu không compliant | Quyền nghiệp vụ còn | Không đạt điều kiện thiết bị cho dữ liệu nhạy cảm | **Deny/giới hạn** cho thao tác yêu cầu thiết bị compliant |
| Workload đúng danh tính | Scope chỉ đọc | Thử tạo quyền IAM admin | **Deny** vì không có authorization |

**Một kết quả deny không nhất thiết cần yêu cầu người dùng xác thực lại.** Nếu thiếu quyền, sai tenant hoặc đã hết hợp đồng, giải pháp là chính sách và cấp quyền hợp lệ; MFA không thể khắc phục việc không được ủy quyền.

## 8. Xác thực liên tục qua Joiner–Mover–Leaver

Việc duy trì mức tin cậy của phiên phụ thuộc vào **vòng đời danh tính**. Thông tin chỉ đúng lúc tạo tài khoản sẽ không còn đáng tin sau khi vai trò, hợp đồng hoặc quyền sở hữu thay đổi.

### 8.1. Joiner: đặt nền tảng cho các quyết định tiếp theo

Một nhân viên mới cần được liên kết với **subject ID ổn định**, nguồn nhân sự/hợp đồng đáng tin, người quản lý, đơn vị, ngày hiệu lực và các phương thức xác thực phù hợp.

Quy trình ví dụ:

1. Nguồn nhân sự xác nhận người tham gia, vai trò, thời điểm bắt đầu và phạm vi làm việc.
2. IAM tạo user tại IdP và cấp quyền chuẩn tối thiểu theo RBAC/ABAC.
3. Quy trình đăng ký phương thức đăng nhập đáp ứng mức bảo đảm phù hợp với tài nguyên dự kiến.
4. SCIM/API đồng bộ tài khoản và nhóm tới ứng dụng, có xác nhận hoàn tất và xử lý lỗi.
5. Khi người dùng bắt đầu phiên, API vẫn kiểm tra trạng thái active, quyền và điều kiện của tài nguyên thực.

Với nhà thầu thời hạn ngắn, **ngày hết hợp đồng** phải là điều kiện có thể làm quyền/phiên ngừng hợp lệ; không chờ người quản lý nhớ gửi yêu cầu thu hồi.

### 8.2. Mover: xử lý quyền thay đổi giữa phiên

Giả sử nhân viên Linh chuyển từ Support sang Finance lúc 09:00. Linh đăng nhập SSO lúc 08:40 và nhận access token CRM có hạn tới 10:40.

| Thời điểm | Sự kiện | Khả năng tác động |
|---|---|---|
| 08:40 | Token CRM được cấp khi Linh còn role Support | Token phản ánh quyền tại thời điểm phát hành |
| 09:00 | HRIS ghi Mover có hiệu lực | Quyền Support cần bị đánh giá lại |
| 09:01 | IdP cập nhật nhóm và role mới | Dữ liệu IdP đổi, token cũ có thể chưa đổi |
| 09:02 | SCIM đẩy thay đổi, CRM nhận chậm | Quyền ứng dụng đích có thể lệch desired state |
| 09:05 | Linh gọi API đọc dữ liệu Support | Nếu API dựa duy nhất vào claim cũ, có thể vẫn allow |
| 09:06 | API đánh giá quyền theo trạng thái mới | Deny quyền Support, audit lý do thu hồi |

Thiết kế nên có:

- Luồng tính lại **desired entitlements** và đối soát **actual/effective permissions**.
- Xóa role, group, quyền trực tiếp và quyền kế thừa không còn phù hợp; rà SoD khi cấp role mới.
- Cơ chế giảm khoảng hở của **token/phiên**: kiểm tra quyền hiện tại, version hoặc revoke khi nền tảng hỗ trợ.
- Kiểm soát chính sách tại API: **role + action + resource + tenant**.
- Theo dõi lỗi provisioning, retry và bằng chứng ứng dụng đích đã áp dụng quyền mới.

**Thành công của SCIM không đồng nghĩa mọi token đã cũ tự bị vô hiệu hóa.** Cần xác nhận việc truy cập bằng token/phiên cũ đã bị chặn trong SLA.

### 8.3. Leaver: kết thúc phiên và mọi đường truy cập còn lại

Khi người dùng rời tổ chức, nhiệm vụ không kết thúc ở bước disable user tại IdP. Một quy trình hoàn chỉnh cần:

- Chặn đăng nhập mới và hạn chế những phiên đang hoạt động.
- Thu hồi refresh token/ủy quyền, xử lý session tại IdP và ứng dụng.
- Vô hiệu hóa quyền và tài khoản đích qua SCIM/API, bao gồm local account không dùng SSO.
- Thu hồi hoặc quay vòng API key, PAT, SSH key, chứng chỉ, secret và delegation gắn với người rời đi.
- Xem xét bot/service account do người đó quản lý; chuyển ownership cho nhóm hợp lệ hoặc ngừng tài khoản.
- Kiểm tra thực tế các endpoint nhạy cảm, theo dõi mọi đích chưa xác nhận và lưu audit theo chính sách.

**Phân biệt rõ:** tài khoản bị vô hiệu hóa, phiên bị kết thúc, quyền bị thu hồi và dữ liệu được lưu/xóa là các thao tác khác nhau. Hồ sơ nghiệp vụ và bằng chứng kiểm toán có thể vẫn phải được bảo quản trong khi quyền truy cập đã bị chặn.

## 9. JWT, refresh token và giới hạn thu hồi

Đây là phần quyết định khả năng ứng dụng phản ứng với sự kiện xác thực/truy cập thay đổi.

### 9.1. Khi nhận access token, API phải kiểm tra gì?

Với một JWT access token đã ký, các kiểm tra thường cần gồm:

1. **Chữ ký và thuật toán được chấp nhận**, với khóa của issuer đã cấu hình tin cậy.
2. **Issuer (iss)** và **audience (aud)** đúng nguồn phát hành và API đích.
3. **Hạn hiệu lực** như exp/nbf khi áp dụng, loại token và các ràng buộc giao thức khác.
4. **Scope hoặc quyền ban đầu**, theo cách resource server diễn giải và chính sách.
5. **Trạng thái hiện tại của subject/phiên** khi cần để đáp ứng SLA thu hồi và rủi ro.
6. **Authorization tại tài nguyên**: hành động, tenant, owner, classification và điều kiện phù hợp.

Với **opaque token**, API có thể cần xác minh qua introspection hoặc cơ chế tương ứng. **ID token** của OIDC phục vụ client và thông tin xác thực; không dùng nó như access token mặc định của API.

### 9.2. Vì sao “revoke ở IdP” có thể chưa đủ?

JWT tự chứa được API kiểm tra offline có thể còn được chấp nhận đến **exp**, ngay cả khi IdP đã disable user, nếu resource server không có cách nhận thay đổi trạng thái. Thu hồi **refresh token** ngăn lấy access token mới theo cơ chế tương ứng nhưng không tự bảo đảm access token cũ hết hạn trước thời điểm được phát hành.

Các cách giảm khoảng hở:

| Cơ chế | Ưu điểm | Giới hạn và điều kiện |
|---|---|---|
| **Access token ngắn hạn** | Giảm cửa sổ sử dụng token cũ | Không thu hồi tức thời; phải cân nhắc tải refresh và UX |
| **Introspection hoặc kiểm tra quyền hiện tại** | Có thể thấy trạng thái thay đổi nhanh hơn | Phụ thuộc độ sẵn sàng của nguồn; cần thiết kế cache/fail-closed |
| **Event-driven revocation / continuous access evaluation** | Đẩy thay đổi quyền/phiên tới điểm thực thi phù hợp | Chỉ hiệu quả ở hệ thống nhận và thực thi sự kiện đúng cách |
| **Session/token version hoặc revocation list** | Cho phép so sánh với trạng thái cập nhật | Cần phối hợp version, lưu trữ, TTL và chống bỏ sót event |
| **Sender-constrained token** | Giảm khả năng replay token bị lấy cắp nếu bên tấn công không có khóa | Không thay thế phân quyền; cần quản lý khóa và hỗ trợ giao thức |
| **Step-up authentication** | Tăng mức bảo đảm trước thao tác nhạy cảm | Không chữa được quyền sai scope hoặc tài khoản đã bị thu hồi |

Không có một kỹ thuật đơn lẻ giải quyết mọi trường hợp. Một số hệ thống cần kết hợp token giới hạn, event, quyền hiện tại và kiểm tra object-level theo rủi ro.

### 9.3. Ví dụ policy phiên mang tính mô tả

~~~yaml
# Pseudocode chính sách; không phải cấu hình trực tiếp của IdP hay PDP nào.
policy_id: finance.payment.approve
default: deny
subject:
  required_status: active
  required_role: finance_approver
resource:
  tenant: same_as_subject_approved_tenant
  created_by: different_from_subject
session:
  access_token_audience: finance-api
  authentication_strength: phishing_resistant_mfa
  authentication_age_max_minutes: 10
  must_not_be_revoked: true
context:
  device_compliance: required
  risk_level_at_most: medium
on_missing_required_signal: deny
on_policy_unavailable: deny
outcomes:
  success: allow
  insufficient_authentication: step_up
  missing_authorization: deny
~~~

**“10 phút” và “medium” chỉ là giá trị minh họa**, phải được quyết định qua phân loại tài nguyên và mức rủi ro của tổ chức. Một policy engine cụ thể có thể chỉ trả Permit/Deny/Indeterminate; ứng dụng tự triển khai quy trình step-up khi kết quả cho biết mức xác thực chưa đủ.

## 10. Thiết kế tích hợp SSO và step-up đúng cách

Giả sử ứng dụng Finance cho phép analyst xem hóa đơn mà không cần xác thực lại thường xuyên, nhưng yêu cầu **MFA chống phishing và phiên vừa xác thực** trước khi duyệt thanh toán.

Luồng hợp lý:

1. Người dùng đăng nhập qua IdP; ứng dụng thiết lập phiên và giữ những thông tin cần để đánh giá phương thức/thời điểm xác thực.
2. Khi yêu cầu **invoice.read**, backend xác minh token và quyền tài nguyên. Nếu policy đạt, cho phép.
3. Khi yêu cầu **payment.approve**, backend phát hiện mức bảo đảm hiện tại chưa đạt. Ứng dụng khởi tạo **step-up qua IdP** bằng cơ chế được giao thức và nền tảng hỗ trợ.
4. IdP xác thực theo phương thức cần thiết và trả bằng chứng mới; ứng dụng kiểm tra phản hồi đúng phiên, đúng client và các điều kiện an toàn của giao thức.
5. Backend **đánh giá lại authorization** cho payment cụ thể, nhất là SoD, tenant, trạng thái lệnh và thời gian hiệu lực.
6. Chỉ khi tất cả điều kiện đạt mới cho phép duyệt; ghi audit của step-up và decision mà không log token.

**Step-up tăng mức xác thực, không tự động tăng role.** Người chỉ có quyền xem hóa đơn không được phê duyệt thanh toán sau khi hoàn thành MFA.

### Lưu ý về claim auth_time, acr, amr

Các hệ thống OIDC có thể cung cấp thông tin thời điểm hoặc mức xác thực theo claim như **auth_time**, **acr**, **amr**, nếu cấu hình và luồng hỗ trợ. Tuy nhiên:

- Không suy đoán từ tên claim rằng mức đảm bảo đã đủ cho mọi chính sách; cần biết ý nghĩa do IdP công bố.
- Không tin giá trị do frontend tự điền vào header hoặc request body.
- Cần liên kết kết quả step-up với phiên/request phù hợp, kiểm tra các ràng buộc bảo mật của luồng OIDC.
- Khi IdP không cung cấp bằng chứng đủ độ tin cậy, không tự coi thao tác là đã step-up.

## 11. Adaptive authentication và hành vi có thể thay đổi

Một hệ thống theo dõi rủi ro có thể quan sát:

- Xác thực từ thiết bị mới hoặc thiết bị vừa mất tuân thủ.
- Một phiên gọi API nhanh và nhiều hơn hoạt động thông thường.
- Thay đổi phương thức MFA, recovery factor hoặc tạo credential mới.
- Request export dữ liệu số lượng lớn ở tenant không thường sử dụng.
- Nhiều lần bị từ chối do sai scope hoặc cố truy cập tính năng quyền cao.
- Một access token hoặc service principal được sử dụng ở ngữ cảnh không phù hợp với lần cấp phát.

Các tín hiệu cần được kết hợp, đánh giá độ tin cậy và giảm **false positive**. Ví dụ vị trí mạng thay đổi có thể do VPN hoặc công tác; một cảnh báo đơn lẻ không chứng minh tài khoản bị chiếm.

| Mức rủi ro theo chính sách nội bộ | Hành động minh họa | Lưu ý |
|---|---|---|
| Thấp, bằng chứng đủ | Tiếp tục request trong phạm vi quyền | Vẫn kiểm tra authorization |
| Trung bình, thiếu mức xác thực | Step-up hoặc hạn chế thao tác nhạy cảm | Người dùng có đường hoàn thành công việc hợp lệ |
| Cao, có dấu hiệu nghi chiếm quyền | Chặn action, giảm scope, thu hồi phiên phù hợp, điều tra | Ghi lý do và mốc thời gian; cân nhắc ảnh hưởng hoạt động |
| Không xác định vì mất nguồn tín hiệu quan trọng | Fail closed cho tài nguyên nhạy cảm hoặc dùng quyết định đã cache nếu được cho phép rõ ràng | Tránh suy diễn “không thấy rủi ro = an toàn” |

**Không nên dùng “risk score” như nguồn sự thật duy nhất.** Quyền nghiệp vụ, tenant và trạng thái hợp đồng phải được kiểm tra độc lập. Một người có điểm rủi ro thấp vẫn không được phép xem tài nguyên ngoài quyền.

## 12. Continuous authentication cho workload/service account

Danh tính máy không thể nhập MFA tương tác trên mỗi request. Áp dụng tư duy tương đương: **workload nào, ở môi trường nào, được cấp credential ra sao, đang có quyền gì và còn hợp lệ không?**

### Các lớp kiểm soát

- **Workload identity riêng:** xác định service principal theo ứng dụng/môi trường; có owner, mục đích, hệ thống nguồn và vòng đời.
- **Credential phù hợp:** ưu tiên federation hoặc token ngắn hạn/mTLS khi nền tảng hỗ trợ; hạn chế secret dài hạn và dùng chung.
- **Xác minh ở request:** audience, issuer, chữ ký/chứng chỉ, sender constraint và scope của credential; kiểm tra authorization tới tài nguyên.
- **Đánh giá theo sự kiện:** ngừng job, xóa namespace, thay owner, thay policy, lộ secret hoặc service decommission cần làm credential/quyền cũ mất hiệu lực theo quy trình.
- **Giới hạn phạm vi:** service A gọi service B không vì cùng cluster mà được phép đọc dữ liệu mọi tenant.
- **Audit:** dùng workload ID và correlation ID để phát hiện sử dụng ngoài hành vi mong đợi.

Ví dụ một job đối soát hàng đêm chỉ cần đọc hóa đơn tenant A và ghi kết quả vào vùng báo cáo. Nếu job bị chiếm, token chỉ có quyền hẹp sẽ hạn chế thiệt hại hơn một API key quyền admin không hết hạn.

### Kịch bản credential bị lộ

Giả sử API key của một bot bị phát hiện trong kho mã công khai. Việc chỉ khóa tài khoản của lập trình viên tạo bot không giải quyết vấn đề: bot là **danh tính độc lập**. Tổ chức cần xác định owner, thu hồi hoặc xoay key của bot, đánh giá quyền, giám sát các lần dùng sau sự kiện và cập nhật cơ chế cấp phát credential. Nếu có thể, chuyển sang workload identity với token ngắn hạn và scope giới hạn.

## 13. Xử lý mất tín hiệu, cache và khả năng sẵn sàng

Continuous authentication phụ thuộc nhiều nguồn; không thể yêu cầu mọi API call chờ toàn bộ HRIS, IdP, EDR và risk engine trả lời trực tiếp. Cần thiết kế:

1. **Phân loại quyền nhạy cảm:** thao tác thường, thao tác có dữ liệu nhạy cảm, và hành động đặc quyền.
2. **Độ mới theo tín hiệu:** trạng thái Mover/Leaver thường cần phản ánh nhanh hơn metadata ít thay đổi.
3. **TTL/cache/invalidation:** mỗi quyết định cache có phạm vi tài nguyên và thời hạn; có cơ chế xử lý sự kiện thu hồi.
4. **Giới hạn tác động lỗi:** timeout, circuit breaker và dự phòng phù hợp; không mặc định allow khi nguồn chính sách lỗi.
5. **Hành vi thiếu tín hiệu:** fail closed cho hành động nhạy cảm; chỉ dùng cache theo điều kiện đã được phê duyệt rõ ràng.
6. **Bảo vệ luồng sự kiện:** xác thực nguồn, chống giả mạo và replay, xử lý idempotent, thứ tự/sự kiện trễ và đối soát khi mất event.
7. **Quan sát lỗi:** ghi nhận hệ thống đích không áp dụng event, trạng thái tín hiệu cũ, số phiên chưa thu hồi và số request fail-closed.

Ví dụ sự kiện Mover đến hai lần không được tạo hai grant mới. Nếu sự kiện “role cũ” đến sau sự kiện “role mới”, hệ thống phải có version hoặc mốc hiệu lực để tránh **khôi phục quyền đã thu hồi**. Khi nguồn sự kiện không sẵn sàng, reconciliation định kỳ vẫn phải phát hiện khác biệt desired–actual.

### Dòng thời gian minh họa

~~~text
08:50  Access token CRM được phát hành, có hạn đến 10:50.
09:00  HRIS phát Mover: nhân viên không còn vai trò Support.
09:01  IdP cập nhật nhóm và gửi sự kiện thay đổi.
09:02  Ứng dụng A nhận event, invalidate cache, từ chối quyền Support.
09:03  Ứng dụng B mất kết nối đến luồng event.
09:05  Người dùng dùng token cũ gọi API Support ở cả hai ứng dụng.
09:05  A từ chối theo trạng thái mới; B có nguy cơ allow nếu chỉ dựa vào claim.
09:07  Reconciliation phát hiện B chưa cập nhật, đánh dấu sự cố và áp dụng chặn phù hợp.
~~~

Để đánh giá đúng, phải đo **thời điểm cuối cùng request còn được cho phép trái quyền hiện tại** và **thời điểm quyền không còn dùng được**, chứ không chỉ tính từ lúc IdP xác nhận cập nhật group.

## 14. An toàn và quyền riêng tư của tín hiệu liên tục

Việc đánh giá rủi ro không phải giấy phép thu thập mọi dữ liệu cá nhân. Nguyên tắc phù hợp:

- **Data minimization:** chỉ lấy tín hiệu cần cho quyết định cụ thể; tránh dùng định vị chính xác nếu không thật sự cần.
- **Purpose limitation:** dùng tín hiệu theo mục đích bảo mật đã được thông báo và kiểm soát; hạn chế tái sử dụng vào mục đích không liên quan.
- **Không lưu bí mật vào log:** access/refresh token, mật khẩu, private key và dữ liệu nghiệp vụ nguyên văn không thuộc log quyết định.
- **Giới hạn retention/quyền xem:** log chứa lịch sử truy cập phải có thời hạn lưu giữ và kiểm soát truy cập phù hợp.
- **Giải thích quyết định:** lưu reason code, policy ID/version và nguồn tín hiệu theo mức cần thiết để điều tra false deny.
- **Hạn chế MFA fatigue:** step-up theo rủi ro, kết hợp phương thức chống phishing, có quy trình khôi phục khi thiết bị/phương thức xác thực không còn dùng được.
- **Tránh thiên lệch và tín hiệu yếu:** đánh giá chất lượng rủi ro, kể cả người làm việc từ xa, mạng di động và trường hợp thay thiết bị hợp lệ.

Một phiên bị hạn chế vì thiếu tín hiệu thiết bị nên có hướng khắc phục rõ ràng cho người dùng hợp lệ; đồng thời hệ thống vẫn thực thi quyền nghiệp vụ và yêu cầu bảo vệ dữ liệu.

## 15. Audit: chứng minh quyết định dựa trên bằng chứng nào

Để kiểm chứng continuous authentication, sự kiện audit nên cho biết:

| Trường | Ý nghĩa |
|---|---|
| Timestamp, correlation ID | Liên kết request với phiên, event JML và điều tra |
| Subject/workload ID | Ai hoặc tiến trình nào yêu cầu |
| Application, resource, action, tenant scope | Tài nguyên và hành động đang xét |
| Authentication context | Mức/tuổi xác thực hoặc tham chiếu ngữ cảnh đủ để chứng minh chính sách |
| Identity/lifecycle state/version | Trạng thái quyền nào đã được sử dụng khi ra quyết định |
| Risk/device signals | Tín hiệu nào ảnh hưởng đến kết quả; không cần lưu dữ liệu nhạy cảm nguyên văn |
| Policy ID/version | Quy tắc nào được áp dụng |
| Decision, reason code | Allow, deny, yêu cầu step-up hoặc thu hồi, kèm lý do |
| Event/target confirmation | Hệ thống nào nhận và hoàn thành sự kiện thu hồi |

Ví dụ:

~~~json
{
  "timestamp": "2026-11-23T09:05:11Z",
  "event_type": "access_decision",
  "correlation_id": "req-c519",
  "subject_id": "usr-592",
  "session_ref": "session-hash-example",
  "application": "crm-api",
  "action": "customer.export",
  "resource_scope": "tenant-A",
  "lifecycle_version": 18,
  "authentication_age_seconds": 7500,
  "device_compliance": "unknown",
  "policy_id": "crm.customer.export",
  "policy_version": 8,
  "decision": "deny",
  "reason_code": "ROLE_REVOKED"
}
~~~

Đây chỉ là một cấu trúc minh họa, không phải schema bắt buộc. **Không log token hoặc session identifier nguyên văn nếu chúng có thể bị lạm dụng.** Audit cần bảo đảm toàn vẹn, đồng bộ thời gian, quyền đọc/sửa và thời hạn lưu thích hợp. Dữ liệu “lifecycle_version” chỉ có giá trị nếu ứng dụng thật sự lấy từ nguồn tin cậy.

## 16. Kiểm thử và chỉ số vận hành

### Ma trận kiểm thử

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| C1 | Phiên còn hạn, user active, đúng quyền, thiết bị đạt yêu cầu | Cho phép action hợp lệ |
| C2 | Analyst đọc hóa đơn đúng tenant, không yêu cầu mức xác thực mới | Allow, tránh MFA không cần thiết |
| C3 | Cùng analyst yêu cầu duyệt thanh toán nhưng không có role approve | Deny; step-up không tạo role mới |
| C4 | Approver đủ quyền nhưng phiên thiếu mức MFA hoặc quá tuổi quy định | Step-up hoặc deny theo policy |
| C5 | Người dùng vừa Mover, token cũ còn role trước đây | Deny quyền cũ trong SLA thu hồi |
| C6 | Người dùng Leaver, IdP đã disable nhưng app có local session | Session/đường truy cập bị chặn trong SLA đã đặt |
| C7 | Token có audience của API A đem gọi API B | Deny |
| C8 | Đúng role, sai tenant/owner của tài nguyên | Deny ở backend |
| C9 | Thiết bị bị mất compliance giữa phiên | Reevaluate và giới hạn action nhạy cảm |
| C10 | Risk engine không có dữ liệu bắt buộc | Không ngầm allow; phản ứng theo chính sách |
| C11 | Event Mover trễ, duplicate hoặc sai thứ tự | Không tái cấp quyền cũ; có đối soát/lỗi quan sát được |
| C12 | Một workload bị retire nhưng token còn hạn | Chặn truy cập khi trạng thái/thu hồi có hiệu lực |
| C13 | Credential bot bị nghi lộ | Có thể revoke/rotate, audit, xác nhận API không tiếp tục allow |
| C14 | PDP/IdP tạm mất kết nối | Fail closed với action nhạy cảm, tránh mở quyền ngoài ý muốn |

**Kiểm thử C5/C6 phải gọi thử endpoint thực tế trong môi trường có ủy quyền**, bằng token/phiên được chuẩn bị cho kiểm thử; chỉ xem group ở IdP hoặc trạng thái SCIM “đã gửi” chưa chứng minh quyền đã mất hiệu lực tại API.

### Các chỉ số cần đo

| Chỉ số | Cách đo | Mục đích |
|---|---|---|
| **Revocation latency** | Từ thời điểm Mover/Leaver/revoke có hiệu lực đến khi quyền không còn sử dụng được ở API/ứng dụng đích | Đo khoảng hở do token, event và provisioning; theo dõi p95/p99 |
| **Session-risk response time** | Từ alert rủi ro được xác nhận đến khi phiên/action bị hạn chế | Đo tốc độ phản ứng khi điều kiện thay đổi |
| **Step-up success/failure/abandonment** | Tỷ lệ người dùng hoàn thành hoặc bỏ dở step-up theo loại hành động | Tìm vấn đề UX, lỗi tích hợp hoặc MFA fatigue |
| **False deny/false challenge** | Các quyết định bị từ chối hoặc yêu cầu thêm một cách không phù hợp sau điều tra | Đánh giá chất lượng tín hiệu và chính sách |
| **Stale-signal exposure** | Số request hoặc thời lượng mà policy dùng trạng thái vượt TTL đã quy định | Phát hiện cache, event lag và nguồn không đồng bộ |
| **JML propagation lag** | Thời gian từ sự kiện nguồn đến các đích xác nhận nhận/applied | Khoanh vùng điểm nghẽn trong hệ thống |
| **Policy coverage** | Tỷ lệ action/tài nguyên nhạy cảm có kiểm tra AuthZ + ngữ cảnh phù hợp | Tránh chỉ triển khai ở điểm đăng nhập |
| **Orphaned sessions/credentials** | Số phiên, key và service account còn active sau khi chủ thể/owner không còn hợp lệ | Đánh giá quyền tồn dư |

Cần định nghĩa mốc đo rõ ràng, có người phụ trách và hành động khắc phục nếu vượt SLA. **Số lần MFA được kích hoạt** không phải thước đo trực tiếp chất lượng continuous authentication.

## 17. Bài tập tình huống: một phiên có còn được tin cậy không?

### Bối cảnh

Công ty vận hành hệ thống CRM và Finance với IdP/SSO chung, SCIM để đồng bộ tài khoản. Nhân viên An đăng nhập lúc 08:00 bằng phương thức MFA đáp ứng chính sách thông thường. Diễn biến:

1. **09:00:** An chuyển từ Support sang Finance theo HRIS; IdP cập nhật nhóm mới lúc 09:01.
2. **09:05:** CRM chưa xử lý SCIM Mover, trong khi access token CRM cấp lúc 08:00 còn hạn đến 10:00.
3. **09:10:** Thiết bị của An được đánh dấu **compliance = unknown** do mất kết nối MDM.
4. **09:15:** An cố export 20.000 bản ghi khách hàng trong CRM bằng token cũ.
5. **09:20:** An mở Finance và yêu cầu đọc một hóa đơn đúng tenant.
6. **09:25:** An yêu cầu duyệt một khoản thanh toán mà chính An đã tạo trước đó.
7. **09:30:** Risk engine ghi nhận một số request từ phiên CRM có hành vi bất thường; chưa có bằng chứng chắc chắn bị chiếm quyền.

### Yêu cầu

- A. Với ba hành động lúc 09:15, 09:20 và 09:25, chọn allow/deny/step-up và giải thích dựa trên quyền, phiên, ngữ cảnh.
- B. Nêu ít nhất ba nơi cần đồng bộ hoặc đánh giá lại để quyền Support cũ không tiếp tục dùng được.
- C. Nếu SCIM/MDM có độ trễ, hệ thống nên xử lý thiếu tín hiệu ra sao để không mở quyền nhạy cảm?
- D. Những dữ liệu kiểm toán nào giúp phân biệt Mover hợp lệ, độ trễ kỹ thuật và khả năng chiếm phiên?
- E. Đề xuất hai chỉ số và một bộ kiểm thử để chứng minh việc cải tiến đã có hiệu lực.

### Gợi ý đáp án

**A. Quyết định theo action:**

- **09:15 export CRM:** **deny** vì quyền Support/export cũ phải được thu hồi theo Mover, dù token chưa hết hạn. Thiết bị unknown và hành động export lớn cũng cần kiểm tra theo policy nhưng không phải lý do duy nhất.
- **09:20 đọc invoice:** có thể **allow** nếu role Finance đã được phê duyệt, hóa đơn đúng tenant và chính sách đọc cho phép phiên/thiết bị hiện tại. Nếu Finance yêu cầu thiết bị compliant cho dữ liệu này, phải **deny hoặc yêu cầu khắc phục**, không giả định unknown là compliant.
- **09:25 duyệt payment do chính mình tạo:** **deny** theo SoD, bất kể MFA đủ hay không. Step-up không giải quyết xung đột người tạo/người duyệt.

**B. Đường đồng bộ/đánh giá lại:** trạng thái nhóm/quyền hiện tại tại IdP và hệ thống IAM; quyền thực tế tại CRM qua SCIM/API; phiên/token CRM và điểm kiểm tra API; dữ liệu tenant/ownership ở backend; kiểm tra các quyền trực tiếp, local account hoặc key phụ nếu tồn tại.

**C. Tín hiệu trễ:** ghi nhận nguồn và độ mới; dùng nguồn quyền hiện hành hoặc cơ chế chặn thích hợp cho export, theo dõi SCIM lỗi/lag; fail closed với hành động nhạy cảm nếu không xác minh được điều kiện bắt buộc. Không ngầm allow dựa vào token cũ hoặc device status unknown.

**D. Audit:** sự kiện Mover và ngày hiệu lực, trạng thái user/role/version được dùng, SCIM command/ack/error, time của token/phiên, subject, resource/action, device status và timestamp, risk signal, policy decision/reason code, correlation ID. Không thu thập credential hoặc dữ liệu khách hàng nguyên văn vào log.

**E. Đo/kiểm thử:** revocation latency p95 và tỷ lệ request dùng quyền cũ được chặn sau Mover; test token cũ tại CRM, kiểm tra quyền chéo tenant, test thiếu MDM, SCIM lỗi và request payment vi phạm SoD. Xác nhận kết quả **ở API thực**, không chỉ trên màn hình IAM.

## 18. Checklist triển khai và nguồn học thêm

### Checklist

- [ ] Mô tả được sự khác nhau giữa AuthN, AuthZ, continuous authentication, access evaluation và step-up.
- [ ] IdP/SSO phát hành bằng chứng với thời hạn, mức bảo đảm và ràng buộc phù hợp.
- [ ] API xác minh issuer, audience, thời hạn và loại token; thực thi quyền theo action/resource/tenant.
- [ ] Có tín hiệu đáng tin về trạng thái JML, thiết bị, phiên và rủi ro; biết độ mới/giới hạn của từng tín hiệu.
- [ ] Có điều kiện rõ để đánh giá lại, step-up, hạn chế action và thu hồi phiên.
- [ ] Quyền sau Mover/Leaver phản ánh ở những điểm truy cập quan trọng trong SLA.
- [ ] Hiểu giới hạn JWT tự chứa, refresh token, cache, local session và SCIM bất đồng bộ.
- [ ] Khi tín hiệu/policy không khả dụng, không mặc định mở quyền nhạy cảm.
- [ ] Workload/service account có identity, owner, scope, lifecycle và credential riêng được quản lý.
- [ ] Sự kiện thay đổi được xác minh nguồn, có version/idempotency và đối soát nếu mất hoặc đảo thứ tự.
- [ ] Có audit cho trạng thái bằng chứng, policy decision, step-up và revocation mà không lộ credential.
- [ ] Đo được độ trễ thu hồi, lỗi step-up, false deny và chênh lệch quyền hiện hành.

### Thuật ngữ cần nhớ

| Thuật ngữ | Giải thích |
|---|---|
| **Continuous authentication** | Duy trì/đánh giá lại mức tin cậy của danh tính và phiên theo thời gian, rủi ro và hành động |
| **Adaptive/risk-based authentication** | Điều chỉnh yêu cầu xác thực theo tín hiệu rủi ro phù hợp |
| **Step-up** | Yêu cầu xác thực mạnh hơn hoặc mới hơn cho thao tác cụ thể |
| **Continuous Access Evaluation (CAE)** | Đánh giá lại truy cập khi trạng thái và tín hiệu thay đổi; khả năng tùy nền tảng |
| **AuthN / AuthZ** | Xác thực chủ thể / phân quyền hành động trên tài nguyên |
| **IdP / SSO / SCIM** | Nguồn xác thực tập trung / đăng nhập liên kết / đồng bộ vòng đời user/group |
| **RBAC / ABAC** | Quyền theo vai trò / quyền theo thuộc tính và ngữ cảnh |
| **PEP / PDP** | Thành phần thực thi / ra quyết định theo chính sách |
| **Reauthentication** | Thực hiện lại bước chứng minh danh tính trong phiên hoặc sau sự kiện |
| **Revocation latency** | Độ trễ đến lúc quyền/phiên đã bị thu hồi không còn dùng được ở điểm truy cập |
| **Session/token freshness** | Độ mới của bằng chứng phiên/token so với yêu cầu bảo đảm của hành động |

### Tài liệu tham khảo để học sâu

- **NIST SP 800-207 — Zero Trust Architecture:** ra quyết định truy cập theo chính sách, tín hiệu ngữ cảnh và sự thay đổi của mức tin cậy.
- **NIST SP 800-63 — Digital Identity Guidelines:** khái niệm về bằng chứng danh tính, xác thực, quản lý phiên và thời điểm xác thực lại.
- **OpenID Connect Core:** các thành phần xác thực liên kết, ID token và thông tin về phương thức/thời điểm xác thực.
- **OAuth 2.0 và hướng dẫn bảo mật liên quan:** access token, resource server, sender constraint và thực hành quản lý phiên phù hợp.
- **RFC 7643/RFC 7644 — SCIM:** mô hình dữ liệu và giao thức đồng bộ user/group qua vòng đời.
- **NIST SP 800-207A (nếu nghiên cứu ứng dụng cloud-native) và OWASP API Security Top 10:** định hướng thực thi chính sách và giảm lỗi authorization tại API.

**Điểm cần ghi nhớ:** Continuous authentication giúp hệ thống không mặc định tin rằng **một lần xác thực đúng sẽ mãi đúng cho mọi hành động**. Khi vai trò, trạng thái phiên, thiết bị hoặc rủi ro đổi, chính sách phải có khả năng đánh giá lại và phản ứng tương xứng. Trong vòng đời IAM, giá trị thực tế của cơ chế này được thể hiện ở **truy cập còn đúng quyền sau Joiner, giảm quyền đúng lúc sau Mover và chặn được mọi đường truy cập cần thu hồi sau Leaver**.
