# Compensating control – Thiết kế, kiểm chứng và quản trị biện pháp kiểm soát bù trừ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **compensating control (biện pháp kiểm soát bù trừ)** trong bối cảnh security assurance và phân biệt nó với security control tiêu chuẩn, defense in depth, ngoại lệ chính sách và việc chấp nhận rủi ro.
- Nhận biết khi nào một control gốc **chưa thể triển khai hoặc chưa đáp ứng yêu cầu**, những điều kiện cần để cân nhắc control bù trừ và trường hợp không thể coi biện pháp đề xuất là đủ.
- Chuyển yêu cầu bảo mật thành **mục tiêu control, kịch bản rủi ro, phạm vi ảnh hưởng, tiêu chí hiệu lực và các test có thể quan sát**.
- Đánh giá một giải pháp bù trừ dựa trên tính phù hợp với đường tấn công, khả năng bị bỏ qua, mức bao phủ, độ độc lập và tác động tới likelihood/impact.
- Tạo chuỗi bằng chứng **risk → requirement → primary control gap → compensating control → test → evidence → residual risk → decision** gắn với phiên bản và môi trường.
- Thiết kế chương trình phê duyệt, giám sát, thời hạn và chuyển đổi từ control tạm thời sang giải pháp xử lý lâu dài trong quá trình phát triển và vận hành.

## 1. Compensating control là gì?

Trong chương **Security control** của module **SECURITY_SECURITY_ASSURANCE**, một **compensating control** là biện pháp được lựa chọn để **giảm rủi ro do một yêu cầu/control dự kiến chưa thể được đáp ứng theo cách thông thường**, bằng một cơ chế khác có khả năng góp phần đạt cùng mục tiêu bảo mật trong **phạm vi và điều kiện xác định**.

Ví dụ: một ứng dụng quản trị cũ chưa hỗ trợ xác thực đa yếu tố (MFA) theo cơ chế hiện đại. Tổ chức không thể nâng cấp ngay vì phụ thuộc hệ thống nghiệp vụ. Thay vì công bố giao diện trực tiếp, tổ chức có thể định tuyến toàn bộ truy cập quản trị qua một **identity-aware access gateway** thực thi MFA, giới hạn thiết bị/người dùng, chặn đường trực tiếp và ghi nhận hoạt động đặc quyền. Đây là **ứng viên** control bù trừ; tính đủ hiệu lực phụ thuộc vào việc không còn đường bypass, danh tính ở ứng dụng được bảo đảm và phép thử thực tế.

Điểm quan trọng: **“không làm được control A nên bật thêm control B” chưa đủ để gọi B là compensating control có hiệu lực.** Phải chứng minh B xử lý đúng phần rủi ro do A để lại.

### Ba câu hỏi nền tảng

1. **Control gốc phải đạt điều gì?** Ví dụ ngăn truy cập trái phép vào giao diện quản trị bằng yêu cầu MFA.
2. **Vì sao control gốc chưa đạt?** Ứng dụng không hỗ trợ giao thức thích hợp, có giới hạn vendor, rủi ro gián đoạn hoặc phụ thuộc cần thời gian khắc phục.
3. **Biện pháp bù trừ có giúp đáp ứng mục tiêu tới mức nào?** Ai được truy cập, qua đường nào, có đường bỏ qua không, thời điểm hết hạn, bằng chứng và rủi ro còn lại.

**Mức “tương đương” không thể mặc định.** Một tiêu chuẩn, hợp đồng hoặc quy định cụ thể có thể có điều kiện riêng về việc dùng control thay thế/bù trừ, thẩm quyền phê duyệt và mức đáp ứng. Bài học trình bày phương pháp security assurance tổng quát; không mặc định bất kỳ giải pháp nào được cơ quan kiểm toán hoặc bên quản lý chấp nhận.

## 2. Phân biệt compensating control với các khái niệm gần nhau

| Khái niệm | Ý nghĩa | Ví dụ | Điểm phân biệt |
| --- | --- | --- | --- |
| **Primary / prescribed control** | Cơ chế dự kiến hoặc được chỉ định nhằm đáp ứng yêu cầu | Ứng dụng quản trị bắt buộc MFA | Mốc để xác định gap |
| **Compensating control** | Cơ chế khác nhằm bù cho gap của primary control và giảm rủi ro cùng mục tiêu | MFA tại gateway với đường trực tiếp bị chặn | Phải chứng minh bao phủ và hiệu lực |
| **Alternative control** | Một cách hiện thực yêu cầu bằng thiết kế khác; không nhất thiết có primary control thất bại | Hai thư viện đã được phê duyệt cho cùng yêu cầu | “Thay thế cách làm” chưa chắc là bù trừ do thiếu hụt |
| **Defense in depth** | Các lớp bảo vệ bổ sung khi control chính vẫn tồn tại | MFA + phân quyền trong ứng dụng + network segmentation | Tăng phòng thủ, không mặc nhiên phát sinh từ exception |
| **Detective control** | Nhận biết và thông báo hoạt động sai lệch | Cảnh báo export dữ liệu bất thường | Có thể bổ trợ nhưng không nhất thiết ngăn hậu quả |
| **Corrective / recovery control** | Giảm thiểu hoặc phục hồi sau sự kiện | Thu hồi token, khôi phục từ backup | Tác động khác với preventive control |
| **Risk acceptance** | Quyết định có thẩm quyền tiếp tục chịu rủi ro tồn dư | Chấp nhận tạm thời với thời hạn và điều kiện | Không phải control kỹ thuật và không chứng minh control đạt |
| **Exception / deviation** | Hồ sơ cho phép không tuân thủ điều kiện cụ thể trong phạm vi đã duyệt | Gia hạn thời gian sửa MFA của ứng dụng | Không tự động làm mất yêu cầu kiểm chứng |

Một biện pháp **phát hiện** không tự động tương đương biện pháp **ngăn chặn**. Ví dụ, cảnh báo sau khi toàn bộ database đã bị xuất ra có thể hỗ trợ điều tra nhưng chưa bảo đảm mục tiêu “ngăn truy cập trái phép trước khi dữ liệu rời hệ thống”. Muốn coi đó là một phần của giải pháp bù trừ, cần chứng minh mức giảm hậu quả thực tế, kết hợp với các control khác nếu cần và xác định rủi ro còn lại.

### Minh họa hai tình huống dễ nhầm

**Trường hợp A:** hệ thống đã có MFA ở ứng dụng; doanh nghiệp thêm VPN giới hạn truy cập quản trị. VPN là lớp **defense in depth**. Nếu MFA vẫn hoạt động, không cần gọi VPN là control bù trừ cho MFA.

**Trường hợp B:** hệ thống không thể áp dụng MFA trực tiếp; truy cập admin được bắt buộc qua gateway xác thực đa yếu tố, đường vào khác bị chặn, tài khoản quản trị được map đáng tin. Lúc này gateway có thể được **đánh giá như compensating control**, nhưng phải chứng minh không bị bypass và đáp ứng yêu cầu áp dụng.

## 3. Bắt đầu từ risk scenario và control objective, không từ công cụ

Trong security assurance, trọng tâm là **mục tiêu bảo mật có thể chứng minh**. Lựa chọn WAF, gateway, EDR, network policy hay giám sát chỉ có ý nghĩa khi chúng xử lý một đường gây hại thực tế.

Một risk scenario tốt nêu:

- **Tài sản:** dữ liệu tài chính, bí mật, tài khoản đặc quyền, khả năng vận hành.
- **Đe dọa:** người ngoài Internet, tài khoản hợp lệ bị chiếm, workload bị lạm dụng, thay đổi sai.
- **Điểm yếu/gap:** MFA không có, không thể vá dependency, mã hóa chưa hỗ trợ, phân quyền thiếu ở một đường.
- **Đường tấn công:** các bước và ranh giới tin cậy dẫn đến hậu quả.
- **Impact và likelihood:** theo phương pháp đánh giá được duyệt, cùng giả định và thời điểm.
- **Phạm vi:** môi trường, phiên bản, endpoint, identity, vùng mạng, dữ liệu và kỳ hiệu lực.
- **Control objective:** hành vi cần ngăn hoặc hạn chế, có tiêu chí kiểm thử.
- **Lỗ hổng bằng chứng:** điều gì chưa quan sát hoặc chưa kiểm tra.

Ví dụ:

> **RISK-COMP-01:** người nắm mật khẩu quản trị ứng dụng cũ có thể truy cập giao diện quản trị từ ngoài vùng được phê duyệt vì ứng dụng chưa hỗ trợ MFA, dẫn đến nguy cơ thay đổi cấu hình và trích xuất báo cáo nhạy cảm.

Tuyên bố `“ứng dụng hiện chưa hỗ trợ MFA”` mô tả **gap**. Tuyên bố `“tất cả quyền admin phải đi qua cơ chế xác thực mạnh và không thể bypass”` mô tả **control objective**. Tuyên bố `“đã bật gateway”` mới là việc triển khai một thành phần, chưa chứng minh objective đã đạt.

### Chuỗi chứng minh

~~~mermaid
flowchart LR
    R["Risk scenario và tài sản"] --> Q["Yêu cầu bảo mật, mục tiêu control"]
    Q --> G["Primary control chưa đạt + nguyên nhân"]
    G --> C["Thiết kế compensating control + giới hạn"]
    C --> T["Kiểm thử đúng đường tấn công"]
    T --> E["Evidence về hiệu lực và trạng thái triển khai"]
    E --> A["Đánh giá residual risk, phê duyệt có thẩm quyền"]
    A --> M["Giám sát, review, thay thế hoặc gỡ control"]
    M --> R
~~~

### Hồ sơ baseline cần thu thập

| Mục | Câu hỏi phải trả lời |
| --- | --- |
| Requirement ID | Yêu cầu nào chưa đạt? Có bắt buộc về cách triển khai cụ thể không? |
| Primary control ID | Control gốc được thiết kế nhằm ngăn/giảm sự kiện gì? |
| Gap description | Thiếu, lỗi, không tương thích hoặc đang triển khai dở ở đâu? |
| Reason/constraint | Vì sao chưa sửa ngay? Có giải pháp xử lý gốc được lên lịch không? |
| Risk IDs | Những tài sản và đường tấn công nào chịu ảnh hưởng? |
| Assessed scope | Environment, service, version, user/role, endpoint, data store cụ thể |
| Decision owner | Ai quyết định mức rủi ro chấp nhận và thời hạn? |
| Assurance criteria | Bằng chứng nào mới đủ để kết luận biện pháp bù trừ đang có hiệu lực? |

## 4. Điều kiện cân nhắc và điều kiện không nên chấp nhận

Một control bù trừ đáng xem xét khi:

1. Có **gap thực tế** giữa yêu cầu và control gốc, đã được xác minh.
2. Có **ràng buộc hợp lý** làm việc triển khai control gốc chưa khả thi trong thời gian cần thiết, được ghi nhận và review.
3. Có một hoặc nhiều control khác **giảm đáng kể cùng rủi ro**, với cơ chế giải thích được.
4. Có cách **kiểm thử, theo dõi và xác minh liên tục**; không chỉ dựa vào tài liệu thiết kế.
5. Có owner, người duyệt, thời hạn, điều kiện kết thúc và kế hoạch khắc phục gap gốc.
6. Không có yêu cầu bên ngoài cấm hoặc giới hạn việc dùng phương án đó, hoặc tổ chức đã hoàn tất việc đánh giá/ủy quyền tương ứng.

**Dấu hiệu cần từ chối hoặc chuyển cấp:**

- Biện pháp chỉ tạo **cảm giác an toàn** nhưng không chặn/giảm kịch bản, ví dụ bật một WAF không có rule cho lỗi logic phân quyền.
- Có thể **truy cập trực tiếp** vào ứng dụng bỏ qua gateway, proxy hoặc API trung gian được đưa ra làm giải pháp.
- Control nằm trên **cùng thành phần hoặc cùng credential** dễ bị tấn công một lần là mất cả hai lớp bảo vệ; chưa xem xét common-cause failure.
- Chỉ theo dõi cảnh báo mà **không có người trực/khả năng phản ứng**, hoặc thời gian phản ứng dài hơn nhiều thời gian gây hậu quả.
- Không có bằng chứng hiệu lực ở **production** nhưng kết luận dựa trên thử nghiệm dev/staging.
- Yêu cầu có tính **bắt buộc về cơ chế** mà giải pháp bù trừ không được phép thay; cần tuân thủ hoặc xin quyết định hợp lệ trước.
- Rủi ro còn lại vượt ngưỡng, không ai có thẩm quyền chịu trách nhiệm hoặc ngoại lệ đã hết hạn.

Không dùng compensating control như một tên gọi khác cho **“chúng ta không có thời gian sửa lỗi”**.

## 5. Thiết kế dựa trên đường tấn công và độ bao phủ

### 5.1. Xác định đường được bù trừ

Ví dụ ứng dụng quản trị `legacy-admin` có trang web cho nhân viên vận hành. Sơ đồ sơ bộ:

~~~mermaid
flowchart LR
    U["Operator"] --> IDP["IdP + MFA"]
    IDP --> G["Identity-aware gateway"]
    G --> APP["Legacy admin app"]
    APP --> DB[("Dữ liệu và cấu hình quan trọng")]
    DIRECT["Internet / mạng khác"] -. "Có thể bypass?" .-> APP
    BOT["Job / API nội bộ / break-glass"] -. "Đường phụ?" .-> APP
~~~

Nếu sơ đồ chỉ thể hiện `Operator → IdP → gateway → app` nhưng không kiểm tra `DIRECT` và `BOT`, kết luận “mọi lần quản trị đều qua MFA” chưa có căn cứ.

### 5.2. Năm câu hỏi để đánh giá hiệu lực

| Tiêu chí | Câu hỏi | Minh chứng cần tìm |
| --- | --- | --- |
| **Alignment** | Biện pháp bù trừ xử lý **cùng control objective** hay chỉ vấn đề khác? | Mapping requirement–risk–behavior |
| **Coverage** | Bao phủ mọi user, protocol, endpoint, nguồn mạng, service account và luồng liên quan không? | Inventory, route/IAM snapshots, negative tests |
| **Enforcement** | Có thật sự chặn điều bị cấm hay chỉ ghi nhận? Fail open hay fail closed? | Test behavior khi hợp lệ, sai quyền, dịch vụ phụ lỗi |
| **Independence** | Một credential/cấu hình/lỗi có thể làm mất cả primary và compensating control không? | Trust boundary, topology, review quyền và quản trị |
| **Durability** | Có theo dõi drift, thay đổi và thời hạn không? | Alert, review schedule, deployment/config evidence |

**Không phải mọi control cần giống control gốc ở cơ chế**, nhưng phải đánh giá được liệu tổ hợp control đạt mục tiêu trong phạm vi yêu cầu hay chỉ giảm một phần rủi ro.

### 5.3. Control phòng ngừa, phát hiện, phản ứng và phục hồi

Trong một thiết kế bù trừ có thể kết hợp nhiều lớp:

- **Preventive:** identity-aware proxy, IAM giới hạn, chặn network path, rate limit, phân tách tenant.
- **Detective:** log đăng nhập thất bại, cảnh báo truy cập bất thường, integrity monitoring, drift detection.
- **Responsive:** khóa credential, chặn route, cô lập workload, xử lý sự cố đã phân công.
- **Recovery:** khôi phục dữ liệu và cấu hình từ bản kiểm chứng, kiểm soát rollback.

Một hệ thống có thể dùng nhiều lớp để giảm rủi ro khi không thể triển khai control gốc. Tuy vậy, cần chỉ ra **mỗi lớp đóng góp ở bước nào** của attack path và giới hạn của lớp đó. Không thể cộng tùy tiện “10% từ WAF + 20% từ monitoring + 50% từ network” thành mức hiệu lực 80% nếu không có mô hình và dữ liệu đáng tin.

## 6. Quy trình lựa chọn và phê duyệt compensating control

Một quy trình dùng được trong thực tế:

### Bước 1 — Xác nhận gap và control gốc

Xác định văn bản yêu cầu, ID control, đối tượng áp dụng, bằng chứng không đạt và sự khác biệt so với thiết kế mong đợi. Ví dụ `REQ-MFA-01` yêu cầu truy cập đặc quyền phải chịu MFA, trong khi `legacy-admin` chỉ kiểm tra username/password.

### Bước 2 — Phân tích rủi ro nếu chưa có biện pháp bù trừ

Xác định actor, đường vào, loại tài khoản, dữ liệu, điều kiện khai thác, likelihood/impact và control còn đang hoạt động. Mức rủi ro này là baseline cho việc đánh giá tác dụng của biện pháp. Không tự coi mọi tình huống là Critical hoặc Low khi chưa có căn cứ.

### Bước 3 — Đưa ra thiết kế và phương án so sánh

Có thể có nhiều lựa chọn: nâng cấp ứng dụng, thay nền tảng, khóa đường public, chuyển tác vụ qua gateway có xác thực mạnh, giới hạn quyền, thêm bước phê duyệt thủ công, thay chức năng nhạy cảm bằng workflow ít phơi lộ hơn.

Cân nhắc **cả phương án sửa trực tiếp**. Biện pháp bù trừ không nhất thiết là lựa chọn lâu dài tối ưu; cần nhìn vào chi phí duy trì, dependency mới, khả năng bị bypass và hậu quả khi control phụ thất bại.

### Bước 4 — Xác lập tiêu chí thành công trước khi triển khai

Ví dụ:
- Mọi user interactive có quyền quản trị phải qua IdP và MFA được phê duyệt.
- Không có đường network/protocol/host khác cho truy cập quản trị không qua gateway.
- Service accounts và break-glass có luồng riêng được kiểm soát, review và có bằng chứng.
- Mất IdP/gateway không tạo đường truy cập admin trực tiếp trái policy.
- Truy cập, từ chối, thay đổi policy và tình trạng log phải được giám sát.

### Bước 5 — Triển khai có quản lý thay đổi

Ghi cấu hình và phiên bản; giới hạn quyền quản trị control mới; bảo vệ secret, TLS, log, và thiết kế failover. Các thay đổi liên quan production cần cơ chế phê duyệt/chuyển cấp theo chính sách.

### Bước 6 — Đánh giá độc lập theo mức rủi ro

Cần test bằng actor, vùng mạng và đường thực, xác minh yêu cầu bị cấm thực sự bị từ chối. Reviewer có thể yêu cầu kiểm thử độc lập khi rủi ro trọng yếu, nhất là khi cùng nhóm thiết kế và triển khai.

### Bước 7 — Kết luận residual risk và quyết định

Ghi mức rủi ro còn lại, cơ sở giảm điểm, khoảng trống, hạn hiệu lực và người được quyền phê duyệt. Quyết định chấp nhận khác với trạng thái control; **gắn `EXCEPTION_APPROVED` không làm `PRIMARY_CONTROL_FAIL` trở thành `PASS`**.

### Bước 8 — Theo dõi và đóng vòng

Giám sát drift, định kỳ retest, ưu tiên xử lý nguyên nhân gốc và xác định lúc control bù trừ cần thay, gỡ hoặc chuyển thành control chuẩn.

## 7. Case study 1: Ứng dụng quản trị cũ chưa hỗ trợ MFA

### Bối cảnh và yêu cầu

Doanh nghiệp có một ứng dụng quản trị Java cũ không hỗ trợ OIDC/SAML hay MFA trực tiếp. Giao diện cho phép đổi cấu hình thanh toán và xuất thông tin người dùng. Việc nâng cấp cần thay kiến trúc, chưa thể hoàn thành trong kỳ phát hành.

**Primary control gap:** `CTRL-MFA-PRIMARY` chưa đạt yêu cầu MFA trên giao diện quản trị.

**Compensating design (đề xuất):** đặt một access gateway bắt buộc IdP MFA cho truy cập tương tác; cô lập ứng dụng trong private network, chỉ cho phép gateway làm điểm vào; dùng identity mapping đáng tin giữa gateway và ứng dụng; hạn chế break-glass; ghi nhận audit và cảnh báo.

### Các ranh giới phải kiểm tra

| Đường tương tác | Rủi ro | Test / bằng chứng |
| --- | --- | --- |
| Operator qua gateway | MFA không áp dụng hoặc bị skip vì session cũ | Test MFA trên tài khoản đại diện, session expiry, policy config |
| Direct access đến IP/port của app | Bypass hoàn toàn gateway | Thử truy cập từ các network zone được duyệt, firewall/ingress snapshots |
| Admin API hoặc port quản trị phụ | API bypass hoặc mở rộng quyền không được thấy | Inventory routes/listeners, thử quyền ở từng giao diện liên quan |
| Header nhận dạng người dùng | Client tự đưa header giả mạo hoặc gateway không ký/không lọc | Kiểm tra không tin header từ client; authn/authz mapping, test reject |
| Break-glass / service account | Lối vào không dùng MFA kéo dài và không được review | Policy, owner, thời hạn, logging và thử quyền theo quy định |
| Mất IdP/gateway | Tự động fallback sang đăng nhập app trực tiếp | Test fault/failure an toàn, runbook và kết quả mô phỏng |
| Log pipeline bị ngắt | Không phát hiện lạm dụng quyền đặc biệt | Synthetic event, collector ID, alert delivery và escalation |

### Điều kiện đối với claim

Một claim có thể viết:

> **CLAIM-COMP-01:** Đối với `legacy-admin` production phiên bản `X`, mọi phiên tương tác quản trị trong các đường truy cập đã kiểm kê đều phải qua access gateway có MFA theo chính sách; không có đường vào không được phép đi trực tiếp đến ứng dụng, và quyền phá vỡ khẩn cấp được kiểm soát riêng.

Claim **không nói** rằng ứng dụng đã “hỗ trợ MFA native”. Nó chỉ kết luận về **mục tiêu bảo vệ và phạm vi thực thi**, với mọi ngoại lệ được nêu rõ. Nếu một service account có thể gọi trực tiếp cùng thao tác quản trị hoặc một route cũ còn public, claim cần bị giới hạn hoặc đánh giá không đạt; không thể che bằng lời giải thích “gateway đã bật”.

### Kết luận cần phân lớp

- **Design:** gateway và network segmentation dự kiến bao phủ tất cả đường interactive.
- **Implementation:** config gateway, IdP MFA, ingress và identity mapping được triển khai.
- **Effectiveness:** thử truy cập hợp lệ/trái quyền, bypass, failover, sự kiện audit trên hệ thống thực.
- **Residual risk:** còn rủi ro cấu hình gateway, quyền break-glass, admin API khác, lỗi IdP hoặc phiên bị chiếm.
- **Decision:** người có thẩm quyền phê duyệt trong thời hạn, kèm kế hoạch hiện đại hóa hoặc thay ứng dụng.

## 8. Case study 2: API không có rate limit ở tầng ứng dụng

**Bối cảnh:** một service Java/Spring Boot nhận request tạo file báo cáo. Vì hạn chế kiến trúc, việc bổ sung rate limiting phân tán trong ứng dụng chưa thể hoàn tất trước release. Endpoint có thể bị lạm dụng làm tăng chi phí CPU, sử dụng queue và làm gián đoạn dịch vụ.

**Mục tiêu:** hạn chế khả năng một actor tạo lượng công việc vượt quota đã định nghĩa và phát hiện khi các giới hạn bị vượt.

**Ứng viên compensating control:** API gateway áp dụng quota theo identity đã xác thực và action; kiểm soát direct ingress để không đi vòng; thêm giới hạn worker concurrency, queue capacity, deadline và monitoring. Đây là **tổ hợp control**, không chỉ một rule IP.

### Vì sao chỉ giới hạn theo IP thường không đủ?

- Người dùng thật có thể chia sẻ NAT/IP; đánh giá sai và ảnh hưởng tính sẵn sàng.
- Một tác nhân có thể sử dụng nhiều IP, nhiều token hoặc nhiều tenant.
- Internal service/worker có thể gọi API qua đường không đi qua gateway.
- Bật quota ở gateway có thể không giới hạn **chi phí mỗi request** nếu job đầu vào phức tạp bất thường.
- Nếu gateway dùng giá trị `X-User-Id` do client tự gửi mà không xác thực, attacker có thể đổi identity để tránh quota.

Do đó yêu cầu phải nói **quota áp dụng trên nguồn identity đáng tin và đúng tập điểm vào**; không ngầm tin header hoặc log.

### Mẫu mô tả control bù trừ

Dữ liệu dưới đây là **đặc tả kiểm soát minh họa**, không phải cú pháp vendor gateway có thể copy dùng ngay:

~~~yaml
compensating_control_id: COMP-RATE-001
primary_gap: "Application does not implement distributed rate limiting"
objective: "Limit report export workload by authenticated actor and tenant"
scope:
  service: report-service
  environment: production
  actions: ["POST /api/reports/export"]
enforcement:
  location: "authenticated-api-gateway"
  identity_source: "validated-token-subject-and-tenant-claims"
  bypass_policy: "direct ingress to service denied"
  example_quota: "10 export requests per actor per minute"
  additional_limits:
    - "max worker concurrency by tenant"
    - "max job size and execution deadline"
verification:
  - "valid actor below quota succeeds"
  - "same actor exceeding quota is rejected"
  - "spoofed user header cannot change quota subject"
  - "direct access outside gateway is denied"
  - "unauthorized tenant cannot create export"
  - "gateway failure does not silently open direct ingress"
  - "alert on excessive rejection and worker pressure"
limitations:
  - "several authenticated accounts may still act together"
  - "quota alone does not prove resource-level authorization"
owner: "<SERVICE_AND_PLATFORM_OWNER>"
reviewer: "<SECURITY_ASSESSOR>"
expiration: "<REVIEW_OR_MIGRATION_DATE>"
~~~

Con số `10 requests/phút` là giả định bài học; hệ thống thật cần thử tải với dữ liệu đại diện, điều kiện đồng thời, người dùng hợp lệ và mức chấp nhận sự cố. API gateway rate limit **không thay thế kiểm tra authorization cấp đối tượng** hay chống tấn công gây cạn tài nguyên ở các đường nội bộ chưa bao phủ.

### Bộ test tích hợp cần ưu tiên

| Test ID | Thao tác | Expected result |
| --- | --- | --- |
| COMP-RATE-T01 | Actor hợp lệ gửi dưới quota | Request được xử lý theo nghiệp vụ |
| COMP-RATE-T02 | Cùng actor vượt quota trong thời gian định nghĩa | Có chính sách từ chối phù hợp, không tạo job vượt giới hạn |
| COMP-RATE-T03 | Thay `X-User-Id` do client gửi | Không thay đổi identity dùng trong quota |
| COMP-RATE-T04 | Gọi trực tiếp service không đi gateway | Truy cập bị chặn theo network/identity policy |
| COMP-RATE-T05 | Dùng token hết hạn/không hợp lệ | Không được cấp quota như actor hợp lệ, request bị từ chối |
| COMP-RATE-T06 | Tenant A tạo job cho dữ liệu tenant B | Authorization ứng dụng từ chối |
| COMP-RATE-T07 | Nhiều request đồng thời tới gateway/workers | Quota/concurrency thực thi nhất quán trong mức sai số thiết kế |
| COMP-RATE-T08 | Gateway hoặc store quota gặp lỗi | Hành vi fail-safe theo yêu cầu; không tự mở truy cập không kiểm soát |
| COMP-RATE-T09 | Một event vượt quota thử | Log và alert tới nơi giám sát có owner |
| COMP-RATE-T10 | Triển khai image mới hoặc thay route | Control vẫn bao phủ đúng endpoint và nguồn identity |

Để dùng kết quả test làm **evidence**, cần biết URL/host, actor, token test đã làm sạch, thời điểm, build/config phiên bản, nơi chạy và kết quả thực quan sát được.

## 9. Khi chưa thể vá lỗ hổng hoặc thay dependency

Một trường hợp phổ biến là **không có bản vá tương thích ngay** cho một thư viện hoặc hệ thống vận hành. Khi đó có thể đánh giá các biện pháp giảm thiểu như:

- Giới hạn đường đi tới thành phần dễ bị tấn công, loại bỏ chức năng không cần thiết.
- Hạn chế identity và quyền mà thành phần có thể sử dụng; cô lập network hoặc workload.
- Bật rule chặn **đúng mẫu khai thác** tại gateway/WAF nếu có bằng chứng đường tấn công đi qua đó.
- Hạn chế outbound connections, quyền dữ liệu và khả năng ghi/chạy mã theo điều kiện ứng dụng.
- Bổ sung telemetry, cảnh báo và kịch bản ứng cứu tương ứng.
- Giám sát advisory và lập kế hoạch nâng cấp, thay thế hoặc tắt tính năng.

**Điều kiện tiên quyết:** phải hiểu **đường khai thác thực tế**. Nếu lỗ hổng xảy ra trong một message consumer nội bộ, bật WAF ở public API có thể không liên quan. Nếu attacker có credential hợp lệ, chặn một mẫu payload HTTP cũng chưa ngăn lạm dụng quyền. Không khẳng định “WAF bảo vệ toàn bộ CVE” chỉ vì rule được bật.

Trong hồ sơ risk, cần tách:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **Unpatched vulnerability** | Lỗ hổng vẫn tồn tại trong code/dependency/phiên bản |
| **Mitigation active** | Biện pháp hạn chế đang được triển khai trong phạm vi định nghĩa |
| **Mitigation effectiveness verified** | Có bằng chứng bài kiểm tra cho thấy đường khai thác tương ứng bị chặn/giảm tác động |
| **Risk accepted / exception approved** | Người có thẩm quyền đồng ý chịu residual risk trong điều kiện nhất định |
| **Patched/replaced and retested** | Thành phần gốc đã được sửa hoặc thay; có kết quả kiểm tra và đối chiếu bản triển khai |

Đừng chuyển trạng thái lỗ hổng sang **FIXED** chỉ vì đã kích hoạt rule tại mạng. Đó là **MITIGATED** trong phạm vi được chứng minh, trừ khi tiêu chí đóng của tổ chức định nghĩa khác và được phê duyệt phù hợp.

## 10. Khi control bù trừ không tương đương control gốc

### 10.1. Mã hóa và tokenization

Giả sử yêu cầu bảo vệ một trường dữ liệu nhạy cảm khi lưu. Hệ thống cũ không hỗ trợ mã hóa cấp trường. Một nhóm đề xuất **disk encryption + network segmentation + access logging**. Những biện pháp này có thể giảm rủi ro trong một số kịch bản (ví dụ mất phương tiện lưu trữ hoặc truy cập qua mạng trái quyền), nhưng **không mặc nhiên thay thế bảo vệ trường dữ liệu trước người có quyền đọc database hoặc quản trị OS**.

Nếu mục tiêu là bảo vệ giá trị ngay cả trước một số quyền quản trị, cần đánh giá giải pháp như **tokenization trước khi ghi**, dịch vụ xử lý nhạy cảm tách biệt, quản lý khóa độc lập và phạm vi quyền giải mã. Ngay cả tokenization cũng cần xem **kho mapping, quyền đổi ngược, dữ liệu trong log/backup và các luồng truy vấn**.

Một kết luận có thể đúng là: “giải pháp đã giảm một phần exposure nhưng **chưa đáp ứng mục tiêu yêu cầu**”. Khi đó phải ghi residual risk và quyết định theo thẩm quyền, không gắn nhãn PASS vì có nhiều công cụ.

### 10.2. Backup và availability

Một ứng dụng không có high availability đang được đề nghị “bù” bằng backup hằng ngày. Backup hữu ích để khôi phục dữ liệu và có thể giúp đạt **RPO** trong phạm vi; nhưng không tự bảo đảm **RTO ngắn** khi dịch vụ bị dừng. Nếu requirement là khôi phục chức năng trong vài phút, cần xem xét failover, redundancy và bài diễn tập có đo thời gian. Không đánh đồng “có bản backup” với “dịch vụ vẫn sẵn sàng”.

### 10.3. Logging và non-repudiation

Một hệ thống thiếu xác nhận/chữ ký có giá trị theo mô hình nghiệp vụ không thể mặc nhiên “bù” bằng cách ghi log nhiều hơn. Log cần bảo vệ tính toàn vẹn, nguồn gốc, danh tính, đồng bộ thời gian và quyền sửa; một người có đặc quyền có thể thay hoặc xóa log nếu control không đủ. Tùy mục tiêu chống chối bỏ, có thể phải dùng cơ chế xác thực mạnh, ký số, bằng chứng phê duyệt hoặc bên tin cậy; chỉ logging có thể không đạt yêu cầu.

**Kết luận thực hành:** cần kiểm chứng **thuộc tính bảo mật** mà yêu cầu đòi hỏi, không đếm số biện pháp đã thêm.

## 11. Đánh giá residual risk: không giảm điểm theo cảm tính

Nếu tổ chức dùng ma trận `Likelihood × Impact`, người đánh giá có thể so sánh trước và sau khi áp dụng control bù trừ **trong cùng một phương pháp và phạm vi**.

Giả sử tình huống admin thiếu MFA được chấm theo thang nội bộ minh họa:

| Trạng thái | Likelihood (1–5) | Impact (1–5) | Score | Ý nghĩa |
| --- | ---: | ---: | ---: | --- |
| Primary control gap chưa xử lý | 4 | 5 | **20** | Mức ban đầu giả định, truy cập có thể bị lạm dụng |
| Đã cấu hình gateway, chưa kiểm chứng bypass | 4 | 5 | **20** | Chưa đủ căn cứ hạ điểm theo bằng chứng |
| Gateway/IdP/MFA và đường bypass được test, có evidence | 2 | 5 | **10** | Residual minh họa khi reviewer chấp nhận lập luận |
| Sau nâng cấp ứng dụng với MFA native và retest | Cần đánh giá lại | Cần đánh giá lại | Chưa suy ra | Kết quả mới tùy thiết kế/thực tế |

Các con số chỉ dùng **để giảng giải**, không phải đánh giá sản phẩm thật. Có thể giảm likelihood khi khả năng truy cập trái phép đã được hạn chế; impact vẫn cao nếu một lần truy cập thành công vẫn có thể gây hậu quả nghiêm trọng.

**Thang 1–5 mang tính thứ bậc**, không được suy luận score 10 “an toàn gấp đôi” score 20. Nếu chưa có bằng chứng về coverage, độ tin cậy của kết luận phải thể hiện rõ, có thể ghi **INCONCLUSIVE** thay vì giả định control đạt.

### Phép kiểm tra logic

Một bản ghi residual risk có chất lượng phải trả lời:

1. Đường gây hại nào đã bị chặn hoặc mức hậu quả nào đã giảm?
2. Tại sao thay đổi đó liên quan trực tiếp tới likelihood/impact?
3. Bằng chứng kỹ thuật đến từ đâu, vào thời điểm nào và trên môi trường nào?
4. Control có thể bị bypass, vô hiệu hóa hoặc suy giảm khi thay đổi cấu hình không?
5. Rủi ro còn lại có ở trong mức **risk appetite/tolerance** được phê duyệt không?
6. Ai có thẩm quyền chấp nhận, trong bao lâu và dựa vào điều kiện nào?

## 12. Bằng chứng security assurance cho compensating control

Security assurance không thể dựa trên câu “gateway đang bật” hay “Ops xác nhận đã có rule”. Cần **assurance case** mô tả mối liên hệ giữa claim và evidence.

### Chuỗi truy vết minh họa

~~~text
RISK-COMP-01
  -> OBJ-AUTHN-01: Giảm truy cập quản trị trái phép
  -> REQ-MFA-01: Truy cập tương tác đặc quyền phải qua MFA
  -> PRIMARY-CTRL-MFA: App native MFA chưa thể triển khai
  -> GAP-COMP-01: Legacy app chỉ hỗ trợ password
  -> COMP-CTRL-01: Access gateway + IdP MFA + chặn đường trực tiếp
  -> COMP-TEST-01: Allowed/denied/bypass/failure/break-glass tests
  -> COMP-EV-01: Config + test + deployment + runtime verification
  -> COMP-FIND-01: Nếu phát hiện route bypass hoặc claim mismatch
  -> COMP-RISK-REVIEW-01: Residual risk, quyết định và hạn review
~~~

### Ba cấp độ bằng chứng

| Cấp | Ví dụ | Chưa chứng minh điều gì |
| --- | --- | --- |
| **Design evidence** | Kiến trúc gateway, threat model, risk assessment, security requirement | Chưa chứng minh control đã được triển khai hoặc đang hoạt động |
| **Implementation evidence** | IaC, access policy, source/review, CI test, bản phát hành | Chưa chứng minh production thực chạy đúng state, không có route khác |
| **Operational effectiveness evidence** | Effective config, negative access tests, event thử từ client tới alert, drift monitoring | Chưa tự chứng minh mọi tương lai hay mọi actor ngoài scope đều được kiểm tra |

Một bài test từ mạng công ty bị chặn không chứng minh đường từ một vùng khác cũng bị chặn. Một test MFA bằng account thường chưa chứng minh break-glass hoặc service account tương ứng. **Scope của claim không được rộng hơn scope của evidence**.

### Mẫu hồ sơ biện pháp bù trừ

Dữ liệu trong dấu `<...>` là placeholder, không phải chứng cứ thực tế hoặc sự phê duyệt đã xảy ra:

~~~yaml
compensating_control_id: COMP-CTRL-01
title: "MFA gateway cho ứng dụng quản trị cũ"
system: legacy-admin
environment: production
standard_requirement_id: REQ-MFA-01
primary_control_id: PRIMARY-CTRL-MFA
gap_id: GAP-COMP-01
gap_reason: "Native MFA not available in supported legacy release"
risk_ids:
  - RISK-COMP-01
objective: "Block unauthorized interactive privileged access"
scope:
  protocols: ["HTTPS"]
  roles: ["interactive-administrators"]
  interfaces: ["admin-web", "admin-api-under-review"]
  network_zones: ["<ASSESSED_ZONES>"]
design:
  enforcement:
    - "IdP MFA at mandatory access gateway"
    - "Direct ingress denied"
    - "Trusted identity mapping and authorization"
  detective:
    - "Privileged session/access event pipeline"
  recovery:
    - "Documented emergency-access and isolation procedure"
limitations:
  - "<UNTESTED_BYPASS_PATHS>"
  - "<BREAK_GLASS_SCOPE>"
evidence_refs:
  design: ["<THREAT_MODEL_AND_ARCHITECTURE>"]
  configuration: ["<EFFECTIVE_GATEWAY_IDP_AND_NETWORK_POLICIES>"]
  tests: ["<POSITIVE_NEGATIVE_BYPASS_AND_FAILURE_TESTS>"]
  runtime: ["<DEPLOYMENT_AND_AUDIT_LOG_CHECK>"]
assessment:
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<AUTHORIZED_REVIEWER>"
  reviewed_at: "<ISO_8601_UTC>"
residual_risk:
  likelihood: "<REVIEWED_LEVEL>"
  impact: "<REVIEWED_LEVEL>"
  rationale: "<EVIDENCE_BASED_REASONING>"
decision:
  status: "<PROPOSED_APPROVED_REJECTED_EXPIRED>"
  approving_authority: "<RISK_OWNER_OR_GOVERNANCE_AUTHORITY>"
  decision_ref: "<APPROVAL_RECORD>"
  valid_until: "<EXPIRATION_DATE>"
  primary_remediation_plan: "<LEGACY_MODERNIZATION_WORK_ITEM>"
  next_review_trigger: "<CHANGE_INCIDENT_DRIFT_OR_DATE>"
~~~

Tách rõ **assessment.result** với **decision.status**. Một biện pháp có thể đã được approved cho hoạt động tạm thời nhưng kiểm thử gần đây báo FAIL: không được tự giữ báo cáo PASS, cần xử lý finding và xem xét lại quyết định.

### Chất lượng bằng chứng

Đối với mọi hiện vật, nên có ID, nguồn, thời điểm, người thu thập, actor thử nghiệm, phiên bản code/config, môi trường, expected/observed result, tình trạng dữ liệu nhạy cảm, vị trí lưu có kiểm soát, giới hạn và người review. Với control ảnh hưởng production, nên đối chiếu **artifact digest/deployment ID và cấu hình runtime** khi kết luận.

## 13. Kiểm thử biện pháp bù trừ theo đường bypass và tình huống lỗi

Kiểm thử cần chứng minh **điều kiện được phép hoạt động**, **điều kiện bị cấm bị chặn**, và cơ chế vẫn đáng tin khi các dependency gặp lỗi.

| Nhóm test | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Positive path** | Người dùng/dịch vụ hợp lệ có tiếp tục hoạt động không? | Operator qua IdP MFA truy cập chức năng được phân quyền |
| **Negative authorization** | Actor không hợp lệ, thiếu quyền bị chặn không? | User thường không vào admin dù đã qua gateway |
| **Bypass** | Có đường đi vòng qua control không? | IP trực tiếp, cổng phụ, legacy URL, internal job, old DNS |
| **Identity integrity** | Dữ liệu danh tính có thể bị giả mạo qua header/token không? | Header client tự gửi không được gateway/app tin |
| **Failure modes** | Mất gateway, IdP, config store hay network thì xảy ra gì? | Không tự động mở đường quản trị không có MFA |
| **Change/regression** | Bản deploy mới, thay ingress/IAM có phá control không? | CI + runtime checks sau thay đổi |
| **Detect-and-respond** | Event có đến đúng nơi và có người xử lý? | Synthetic alert tới on-call, diễn tập xử lý |
| **Resilience** | Control bù trừ gây gián đoạn hoặc điểm lỗi đơn mới không? | Test failover, tải, mức ảnh hưởng người dùng hợp lệ |
| **Ownership/expiry** | Ngoại lệ quá hạn, owner đổi, vendor nâng cấp thì sao? | Trigger review và finding khi hết hạn |

**Test có kiểm soát** trên các vùng mạng/actor được cấp phép, dùng dữ liệu thử và không làm gián đoạn dịch vụ. Một bộ test chỉ có trường hợp “happy path” không đủ căn cứ để đánh giá cơ chế bù trừ.

### Ví dụ Java 17: kiểm soát vòng đời phê duyệt

Trong hệ thống quản lý security assurance, có thể dùng mã đơn giản để nhận biết **control bù trừ cần đánh giá lại**. Đoạn code không quyết định control đạt hiệu lực và không tự phê duyệt ngoại lệ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class CompensatingControlReview {
    public enum ReviewState {
        CURRENT,
        REVIEW_REQUIRED,
        EXPIRED
    }

    public record Approval(
            String controlId,
            Instant validUntil,
            Instant lastVerifiedAt,
            boolean materialChangeSinceVerification) {}

    public static ReviewState review(Approval approval, Clock clock) {
        Objects.requireNonNull(approval, "approval");
        Objects.requireNonNull(clock, "clock");

        Instant now = clock.instant();
        // Không đủ metadata hoặc chưa có bằng chứng kiểm chứng.
        if (approval.validUntil() == null ||
                approval.lastVerifiedAt() == null) {
            return ReviewState.REVIEW_REQUIRED;
        }
        // Biên thời gian: hết hiệu lực ngay tại validUntil.
        if (!now.isBefore(approval.validUntil())) {
            return ReviewState.EXPIRED;
        }
        if (approval.materialChangeSinceVerification()) {
            return ReviewState.REVIEW_REQUIRED;
        }
        return ReviewState.CURRENT;
    }
}
~~~

Một số unit tests minh họa với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class CompensatingControlReviewTest {
    private final Clock clock = Clock.fixed(
            Instant.parse("2026-11-28T00:00:00Z"),
            ZoneOffset.UTC);

    @Test
    void expiredAtBoundary() {
        var approval = new CompensatingControlReview.Approval(
                "COMP-CTRL-01",
                Instant.parse("2026-11-28T00:00:00Z"),
                Instant.parse("2026-11-20T00:00:00Z"), false);
        assertEquals(
                CompensatingControlReview.ReviewState.EXPIRED,
                CompensatingControlReview.review(approval, clock));
    }

    @Test
    void changeRequiresReassessment() {
        var approval = new CompensatingControlReview.Approval(
                "COMP-CTRL-01",
                Instant.parse("2026-12-01T00:00:00Z"),
                Instant.parse("2026-11-27T00:00:00Z"), true);
        assertEquals(
                CompensatingControlReview.ReviewState.REVIEW_REQUIRED,
                CompensatingControlReview.review(approval, clock));
    }

    @Test
    void noVerificationRequiresReview() {
        var approval = new CompensatingControlReview.Approval(
                "COMP-CTRL-01",
                Instant.parse("2026-12-01T00:00:00Z"), null, false);
        assertEquals(
                CompensatingControlReview.ReviewState.REVIEW_REQUIRED,
                CompensatingControlReview.review(approval, clock));
    }
}
~~~

**Giới hạn:** `CURRENT` chỉ có nghĩa hồ sơ chưa hết hạn và chưa đánh dấu thay đổi trọng yếu; nó **không chứng minh gateway, IAM, WAF hay security control còn hiệu lực ở runtime**. Hệ thống thật phải liên kết cùng control status, evidence validity, approval authority và trigger review, không chỉ dựa vào lịch.

## 14. Giám sát drift và duy trì assurance liên tục

Biện pháp bù trừ có thể hỏng mà không ai sửa ứng dụng gốc:

- Gateway đổi route, tạo đường truy cập cũ không qua MFA.
- Policy IAM được nới để xử lý sự cố nhưng quên thu hẹp.
- DNS, load balancer hoặc ingress mới công bố endpoint trực tiếp.
- IdP thay session policy, yếu tố xác thực hoặc trusted device rule.
- WAF rule bị tắt, đổi thứ tự hoặc không được áp dụng ở một vùng.
- Log pipeline dừng gửi sự kiện, alert bị mute hoặc on-call không có người nhận.
- Vendor nâng cấp tạo giao diện mới nằm ngoài coverage đã test.
- Một exception hết hạn nhưng không được review hoặc lộ trình xử lý gốc liên tục bị trì hoãn.

### Lịch và trigger đề xuất

| Khi nào | Việc cần làm | Evidence |
| --- | --- | --- |
| Mỗi thay đổi liên quan app/gateway/IAM/ingress | Xác định có thay đổi đường attack/bypass không, chạy test liên quan | Change record, config diff, test run |
| Sau deploy hoặc bật feature flag | Kiểm tra actual routes, identity và phiên bản đúng | Deployment ID, runtime snapshot |
| Khi control phụ hoặc monitoring lỗi | Tạo finding, đánh giá residual risk và kích hoạt ứng phó | Alert, incident/finding, outage timeline |
| Khi có thông tin exploit/advisory mới | Xem lại điều kiện khai thác và khả năng rule hiện tại chặn được | Threat assessment, control retest |
| Theo chu kỳ đã phê duyệt | Review quyền, phạm vi, risk owner, hạn hiệu lực và giải pháp xử lý gốc | Review sign-off, evidence register |
| Khi primary control được sửa hoặc thay | Reevaluate requirement, bỏ ngoại lệ đúng quy trình, quyết định giữ lớp defense-in-depth nào | Primary test, release, migration record |
| Khi audit phát hiện gap | Cập nhật claim, finding, kế hoạch remediation và retest | Audit report, owner, due date, evidence mới |

### Chỉ số cần tránh hiểu sai

Có thể theo dõi **số compensating controls còn hiệu lực**, số exception quá hạn, tỷ lệ control có negative/bypass tests còn hiệu lực, số lần drift, thời gian phát hiện và khắc phục control failure, tỷ lệ kế hoạch sửa primary control hoàn thành đúng hạn.

Tuy nhiên, **ít exception hơn không tự chứng minh hệ thống an toàn hơn** nếu nhóm đóng ticket khi chưa retest hoặc đổi tên ngoại lệ. **Nhiều log/alert hơn không đồng nghĩa giảm risk**, cần xem độ đúng của cảnh báo, phản ứng và khả năng ngăn hậu quả.

## 15. Vai trò, RACI và thẩm quyền xử lý

| Hoạt động | Developer / Service Team | Ops / Platform | Security / AppSec | Risk / Service Owner | Audit / Assessor |
| --- | --- | --- | --- | --- | --- |
| Phát hiện và mô tả primary gap | **R** | C | C | **A** | I |
| Thiết kế compensating control | R/C | R/C | **R** | **A** | C |
| Triển khai và vận hành control | R (ứng dụng) | **R** (hạ tầng) | C | **A** | I |
| Kiểm thử kỹ thuật và cung cấp evidence | R | R | C | **A** | C |
| Review assurance độc lập khi yêu cầu | C | C | C | I | **R/A** |
| Quyết định chấp nhận residual risk / exception | C | C | C | **R/A** | I |
| Lập kế hoạch sửa primary gap và retest | **R** | R/C | C | **A** | I |

R = Responsible (thực hiện), A = Accountable (chịu trách nhiệm cuối cùng), C = Consulted (tham vấn), I = Informed (được thông báo). Đây chỉ là **ma trận minh họa**, không phải tổ chức bắt buộc; khi có nhiều nhóm cùng được ghi R, cần phân rõ work item và **một bên accountable cuối cùng** cho từng quyết định.

Đặc biệt, **Developer không tự động có quyền chấp nhận rủi ro**, Ops không tự phê duyệt nới chính sách vì muốn ổn định dịch vụ, và assessor không chỉ dựa vào lời tự xác nhận của nhóm đã triển khai control.

### Thời hạn và điều kiện kết thúc

Một control bù trừ tạm thời nên có:

- **Start date** và lý do thiếu primary control.
- **Scope** rõ ràng: service, môi trường, identity, data, đường truy cập.
- **Owner, reviewer, risk acceptor** và quyền quyết định.
- **Test plan**/định kỳ review và trạng thái bằng chứng.
- **Valid until**, trigger phát sinh review trước hạn và tiêu chí revoke.
- **Target remediation**: sửa/đổi primary control, phiên bản dự kiến, kế hoạch thử nghiệm, kiểm chứng rollout.
- **Exit criteria**: khi nào primary control đạt yêu cầu và có đủ bằng chứng để đóng exception.

Khi gỡ control bù trừ, cũng cần review đường tấn công mới phát sinh. Một proxy từng thực thi MFA không nên bị tháo trước khi xác minh MFA native thật sự bao phủ các đường interactive tương đương.

## 16. Quy trình khắc phục phát hiện liên quan control bù trừ

Ví dụ assessor phát hiện `legacy-admin` vẫn có cổng quản trị trực tiếp ở một network segment, bỏ qua gateway MFA. Phải coi đây là **finding về hiệu lực** của compensating control, không chỉ “lỗi cấu hình mạng nhỏ”.

~~~mermaid
flowchart TD
    A["Finding: có thể bypass compensating control"] --> B["Xác định tài sản, đường truy cập, môi trường và thời gian"]
    B --> C["Đánh giá khẩn cấp hậu quả và trạng thái claim"]
    C --> D{"Có cần cô lập/chặn đường rủi ro?"}
    D -- "Có" --> E["Thực hiện containment theo quy trình được duyệt"]
    D -- "Không" --> F["Lập kế hoạch xử lý được review"]
    E --> F
    F --> G["Sửa cấu hình/control và kiểm tra mọi đường tương tự"]
    G --> H["Retest positive, negative, bypass và failure modes"]
    H --> I{"Evidence đủ và control đạt?"}
    I -- "Không" --> F
    I -- "Có" --> J["Đối chiếu deployment, reviewer, residual risk và expiry"]
    J --> K["Đóng finding có căn cứ, tiếp tục giám sát"]
~~~

Một finding nên có: ảnh hưởng, cách tái hiện an toàn với dữ liệu test, effective configuration, risk/requirement/control ID, người xử lý, hạn, trạng thái trước/sau, retest evidence, review và quyết định rủi ro tồn dư. Nếu có dấu hiệu thực sự bị khai thác, chuyển quy trình incident response theo thẩm quyền, tránh thao tác phá hỏng bằng chứng.

**Vấn đề được xử lý khi kết quả control và risk được đánh giá lại, không chỉ khi ticket đã chuyển sang “Done”.**

## 17. Những sai lầm thường gặp

| Nhận định sai | Vì sao sai? | Cách làm tốt hơn |
| --- | --- | --- |
| “Đã bật WAF, mọi lỗ hổng ứng dụng đều được bù trừ.” | WAF không kiểm tra hết logic nghiệp vụ, quyền IAM hay đường nội bộ | Mapping threat scenario; test rule với đúng đường tấn công |
| “Cảnh báo truy cập đủ để thay MFA.” | Detective control có thể phát hiện sau khi hành động đã xảy ra | Ưu tiên kiểm soát truy cập thật, đánh giá thời gian phản ứng và residual risk |
| “Có VPN nghĩa là không cần phân quyền ứng dụng.” | User đã vào VPN vẫn có thể vượt quyền đối tượng/tenant | Authorization theo actor/resource/action, negative tests |
| “Gateway có MFA nghĩa là mọi admin path được bảo vệ.” | Có thể có API/port cũ và direct ingress | Inventory, bypass tests ở các network zone được duyệt |
| “Cứ thêm ba control là chắc chắn tương đương primary.” | Số lượng không chứng minh cùng mục tiêu và độ hiệu lực | Lập luận theo đường gây hại, điều kiện và bằng chứng |
| “Compensating control được phê duyệt = primary control PASS.” | Decision acceptance khác trạng thái kỹ thuật | Tách gap/status, compensating assessment và risk decision |
| “Có cấu hình IaC là production đã áp dụng.” | Runtime drift, route hoặc policy không cùng version | Kiểm tra actual state và deployment |
| “Bài test chạy pass tại staging đủ cho production.” | Môi trường, identity, ingress và data có thể khác | Gắn evidence đúng environment/version và test runtime phù hợp |
| “Nếu đã được duyệt ngoại lệ, có thể giữ mãi.” | Risk và threat thay đổi, owner/hạn hiệu lực có thể hết | Review trigger, expiry và kế hoạch khắc phục primary |
| “Đã merge PR thì finding được đóng.” | Control có thể chưa deploy hoặc đường bypass còn tồn tại | Negative/bypass retest, xác nhận bản chạy, review |
| “Không có alert nghĩa là control còn hoạt động.” | Log/alert có thể đứt hoặc không bao phủ actor | Synthetic event, health và kiểm chứng pipeline |
| “Risk score giảm là bằng chứng control đạt.” | Con số đánh giá có thể dựa trên giả định chưa test | Rationale, test reports, config/runtime evidence và giới hạn |

## 18. Bài tập thực hành

**Tình huống:** nhóm vận hành một dịch vụ Java/Spring Boot để xuất hóa đơn. Một thư viện parser đã có vấn đề bảo mật; chưa thể nâng cấp ngay vì bản vá gây thay đổi định dạng dữ liệu đối tác. Dịch vụ nhận file qua API gateway và qua một queue nội bộ từ đối tác. Nhóm Security đề xuất WAF rule ở gateway, network segmentation, quyền tối thiểu cho parser worker, giới hạn input và cảnh báo bất thường. Đội dự án muốn đánh dấu lỗi “đã sửa”.

Hãy thực hiện:

1. Viết một **risk scenario** nêu actor, điểm vào, đường đến parser và hậu quả; phân biệt hai đường API và queue.
2. Chỉ ra **primary gap** và những control hiện tại chưa đáp ứng yêu cầu; xác định phần nào có thể bù trừ bằng WAF, network, worker sandbox, input validation và monitoring.
3. Đánh giá **ít nhất ba đường bypass/failure**. Ví dụ: message đi thẳng vào queue không qua gateway; admin credential của worker bị lộ; WAF rule không bao phủ file nén hoặc format mới.
4. Viết **năm security acceptance criteria** có test tích cực/tiêu cực và phương pháp kiểm chứng trực tiếp.
5. Liệt kê bằng chứng thiết kế, triển khai và vận hành trước khi kết luận giảm residual risk.
6. Đề xuất hồ sơ ngoại lệ có thẩm quyền, thời hạn, trách nhiệm và kế hoạch nâng cấp/đổi thư viện.
7. Khi bản vá tương thích được triển khai, cần chứng minh thêm điều gì để **đóng gap gốc** và điều chỉnh control bù trừ?

### Hướng dẫn lời giải

| Câu hỏi | Điểm cốt lõi |
| --- | --- |
| **1** | Có ít nhất hai đường đưa input không đáng tin tới parser: public API và internal queue; cùng có thể ảnh hưởng đến worker, dữ liệu và availability. |
| **2** | WAF có thể chặn một số payload qua API, không che được queue. Worker identity giới hạn và sandbox có thể giảm blast radius; input validation/rate limit giảm kênh lạm dụng; monitoring hỗ trợ phát hiện. Không có biện pháp nào mặc định vá thư viện. |
| **3** | Kiểm tra route cũ, upload trực tiếp và queue producer ACL; lỗi dependency và fail modes; cách kiểm tra đúng identity nguồn. |
| **4** | Ví dụ: chỉ producer được phê duyệt gửi queue, tệp không hợp lệ bị từ chối an toàn, worker không có quyền đọc dữ liệu ngoài phạm vi, event thử dẫn đến alert, đường API không bypass gateway. |
| **5** | Threat model, dependency/version, IaC/permission policy, CI tests, runtime path and IAM, negative tests, log/alert test, reviewer và limitations. |
| **6** | Risk owner phê duyệt điều kiện hoạt động tạm, owner sửa lỗi và hạn; cập nhật residual risk khi có thay đổi, không coi trạng thái lỗ hổng là FIXED. |
| **7** | Kiểm tra parser đã lên version đúng trên artifact/deployment, security regression tests và compatibility tests đều đạt, các đường input được bảo vệ; chỉ sau đó mới đóng finding theo quy trình. |

**Bài thực hành bổ sung:** thiết kế một control bù trừ cho hệ thống quản trị cũ chưa có MFA. Vẽ DFD gồm gateway, IdP, app, admin API, đường break-glass và các actor. Liệt kê ba bằng chứng chứng minh **không thể bypass gateway**, một tình huống failover, một trường hợp ngoại lệ không được phê duyệt và các điều kiện đánh giá lại.

## Ghi nhớ

- **Compensating control** là biện pháp nhằm bù cho gap của một yêu cầu/control gốc, nhưng phải **chứng minh giảm đúng rủi ro trong phạm vi cụ thể**, không chỉ đặt tên một công cụ.
- **Defense in depth, detective control, exception và risk acceptance** là những khái niệm liên quan nhưng không tự động đồng nghĩa control bù trừ có hiệu lực.
- Thiết kế đúng bắt đầu từ **control objective, risk scenario và attack path**, sau đó kiểm tra coverage, bypass, failure modes, tính độc lập, độ bền vận hành.
- **Bằng chứng** phải gắn với claim, control, test, artifact/config version, môi trường, thời điểm, người review và hạn chế; chỉ cấu hình hoặc CI pass không đủ kết luận production được bảo vệ.
- **Mitigated không đồng nghĩa fixed**. Một lỗ hổng/thành phần gốc có thể vẫn tồn tại trong lúc control bù trừ giảm exposure.
- Biện pháp bù trừ phải có **owner, phê duyệt rủi ro có thẩm quyền, thời hạn, trigger review, theo dõi drift và lộ trình giải quyết gap**; ngoại lệ không biến control FAIL thành PASS.
- Security assurance cần **duy trì liên tục từ phân tích rủi ro đến vận hành**, kiểm thử và audit, khắc phục finding, retest và đánh giá lại khi các điều kiện thay đổi.
