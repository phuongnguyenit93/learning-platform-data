# Continuity plan: Lập kế hoạch duy trì hoạt động kinh doanh có thể kiểm chứng

Một doanh nghiệp có thể mất quyền truy cập hệ thống định danh, trung tâm dữ liệu, dịch vụ thanh toán hoặc nhà cung cấp SaaS ngay giữa ngày làm việc. Trong những giờ đầu của gián đoạn, câu hỏi quan trọng không chỉ là “khi nào máy chủ hoạt động lại?” mà còn là **nghiệp vụ nào phải tiếp tục, với năng lực tối thiểu bao nhiêu, ai ra quyết định và bằng chứng nào cho thấy phương án dự phòng thực sự dùng được**.

**Continuity plan** (*kế hoạch duy trì hoạt động*, thường nằm trong chương trình Business Continuity Management – BCM) là tài liệu và cơ chế phối hợp để tổ chức duy trì hoặc khôi phục các hoạt động sản phẩm, dịch vụ và quy trình ưu tiên đến mức được chấp nhận khi xảy ra gián đoạn. Kế hoạch bao gồm con người, địa điểm, quy trình, dữ liệu, công nghệ, nhà cung cấp, truyền thông và điều kiện quay lại vận hành bình thường. Nó cần có người chịu trách nhiệm, tiêu chí kích hoạt, phương án hành động thực thi được và cách ghi nhận quyết định.

Trong chương **Business continuity** của module **SECURITY_SECURITY_ASSURANCE**, chúng ta đánh giá kế hoạch bằng **bằng chứng kiểm chứng được**: mục tiêu kinh doanh có căn cứ, các phụ thuộc được nhận diện, phương án đã được thử nghiệm, trách nhiệm rõ ràng, thời gian/phạm vi đáp ứng được đo và các phát hiện được khắc phục. Một tập tài liệu được phê duyệt nhưng chưa từng thử nghiệm chưa đủ chứng minh khả năng duy trì kinh doanh.

Sau bài học, người học có thể thực hiện phân tích tác động kinh doanh (BIA) để xây dựng continuity plan; lựa chọn chiến lược duy trì hoạt động; viết playbook kích hoạt và vận hành thay thế; kiểm chứng bằng diễn tập có kịch bản; đánh giá kế hoạch theo mức rủi ro và theo dõi cải tiến liên tục.

## 1. Kế hoạch duy trì hoạt động phải giải quyết những gì?

Gián đoạn không chỉ bắt nguồn từ hỏng phần cứng. Một số kịch bản tiêu biểu:

- **Ransomware hoặc xâm nhập tài khoản quản trị:** hệ thống vẫn có thể chạy nhưng không đủ độ tin cậy để tiếp tục xử lý dữ liệu.
- **Mất Internet, điện, mạng nội bộ hoặc cơ sở làm việc:** nhân viên không truy cập được công cụ; thiết bị và nơi làm việc thay thế có thể chưa sẵn sàng.
- **Mất dịch vụ cloud, DNS, IdP, thanh toán hoặc SaaS:** hạ tầng ứng dụng của doanh nghiệp có thể khỏe, nhưng phụ thuộc bên ngoài không hoạt động.
- **Sự cố dữ liệu:** database thiếu nhất quán hoặc sao lưu không đủ sạch, buộc dừng nghiệp vụ ghi dù API vẫn phản hồi.
- **Thiếu nhân sự trọng yếu:** người nắm quyền vận hành hoặc phê duyệt không sẵn sàng trong khi hệ thống cần chuyển chế độ.
- **Gián đoạn chuỗi cung ứng và đối tác:** đơn hàng vẫn tiếp nhận được nhưng không thể giao, xuất hóa đơn hoặc thanh toán.

Continuity plan trả lời **hoạt động phải tiếp tục thế nào khi điều kiện bình thường không còn**. Trong nhiều trường hợp, giải pháp là vận hành có giới hạn, dùng quy trình thủ công hoặc chuyển qua nhà cung cấp đã được chuẩn bị; không nhất thiết phải phục hồi ngay toàn bộ hệ thống.

### 1.1. Phân biệt các kế hoạch liên quan

| Thành phần | Trọng tâm | Đầu ra điển hình |
|---|---|---|
| **Business Continuity Plan (BCP)** | Duy trì hoạt động/khả năng cung cấp sản phẩm, dịch vụ ưu tiên ở mức được chấp nhận khi gián đoạn. | Ưu tiên quy trình, kịch bản kích hoạt, cách vận hành thay thế, phân công và giao tiếp. |
| **Disaster Recovery Plan (DRP)** | Phục hồi hệ thống, dữ liệu và hạ tầng công nghệ sau thảm họa/gián đoạn. | Restore, failover, kiểm tra RTO/RPO, runbook kỹ thuật và đường quay lại. |
| **Incident Response Plan (IRP)** | Phát hiện, phân tích, khoanh vùng, xử lý và điều tra sự cố bảo mật. | Quyết định containment, bảo toàn bằng chứng, eradication, recovery an toàn và báo cáo. |
| **Crisis management plan** | Điều hành sự kiện nghiêm trọng ảnh hưởng nhiều bộ phận và các bên liên quan. | Tổ chức chỉ huy, ưu tiên cấp cao, xử lý truyền thông và quyết định chiến lược. |
| **Emergency response / life safety** | Bảo vệ tính mạng, sức khỏe và an toàn tại hiện trường. | Sơ tán, cứu trợ, liên lạc khẩn, kiểm soát nguy hiểm trực tiếp. |

Các kế hoạch **phải phối hợp**, không thay thế nhau. Ví dụ trong sự cố ransomware, IRP có thể yêu cầu cô lập database, DRP tổ chức dựng môi trường sạch, còn BCP cho phép tiếp nhận yêu cầu qua kênh khác và ghi nhận giao dịch để đối soát. Nếu BCP yêu cầu “mở lại ngay” nhưng IRP xác định có nguy cơ tái xâm nhập, các nhóm phải sử dụng cơ chế ra quyết định và chấp nhận rủi ro đã xác định; không bỏ qua điều kiện an toàn.

### 1.2. Kế hoạch là một năng lực vận hành

Một BCP có giá trị khi nhân viên thực sự tìm được nó lúc hệ thống chính bị gián đoạn, biết ai có thẩm quyền kích hoạt, có phương án dự phòng khả thi và có thể ghi lại tình hình. Kế hoạch nên được kiểm thử cùng con người, thiết bị, nhà cung cấp, dữ liệu và quyền truy cập thực tế; cần bản truy cập offline hoặc kênh độc lập theo rủi ro.

## 2. Business Impact Analysis là đầu vào của Continuity plan

**Business Impact Analysis (BIA)** xác định hoạt động nào thiết yếu, hậu quả khi bị gián đoạn thay đổi theo thời gian và nguồn lực tối thiểu để tiếp tục cung cấp dịch vụ. BIA tập trung vào tác động kinh doanh; còn đánh giá rủi ro thường xem cả nguồn đe dọa và khả năng xảy ra. Kế hoạch cần dùng cả hai.

Một vòng BIA có thể bao gồm:

1. Lập danh sách sản phẩm/dịch vụ, quy trình và chủ sở hữu nghiệp vụ.
2. Xác định khách hàng, nghĩa vụ hợp đồng, yêu cầu bảo mật, tính an toàn, hệ quả tài chính/pháp lý/uy tín.
3. Đánh giá tác động nếu gián đoạn kéo dài theo các mốc thời gian thích hợp.
4. Xác định mức vận hành tối thiểu, thời hạn phải phục hồi và giới hạn mất dữ liệu.
5. Ánh xạ phụ thuộc: nhân sự, công nghệ, thông tin, địa điểm, đối tác, thiết bị và nguồn lực thay thế.
6. Phê duyệt ưu tiên và cập nhật khi quy trình hoặc điều kiện rủi ro thay đổi.

### 2.1. Các mục tiêu thời gian và mức dịch vụ

| Thuật ngữ | Ý nghĩa | Cách dùng trong kế hoạch |
|---|---|---|
| **MTPD** (*Maximum Tolerable Period of Disruption*; một số tổ chức dùng MAO – Maximum Acceptable Outage theo thuật ngữ riêng) | Khoảng gián đoạn tối đa mà sau đó tác động trở nên không thể chấp nhận với tổ chức theo tiêu chí đã định. | Xác định giới hạn kinh doanh, có sự tham gia của chủ sở hữu dịch vụ. |
| **RTO** (*Recovery Time Objective*) | Thời gian mục tiêu để khôi phục chức năng hoặc nguồn lực đến mức cần thiết sau gián đoạn. | Hướng dẫn thiết kế chiến lược và kiểm thử thời gian đáp ứng. |
| **RPO** (*Recovery Point Objective*) | Mức mất dữ liệu theo thời gian có thể chấp nhận khi khôi phục dữ liệu. | Quyết định sao lưu/nhân bản, tần suất bảo vệ dữ liệu và đối soát. |
| **MBCO** (*Minimum Business Continuity Objective*) | Mức sản phẩm/dịch vụ tối thiểu có thể chấp nhận trong gián đoạn. | Xác định năng lực xử lý, đối tượng được phục vụ và điều kiện chất lượng. |
| **Thời gian vận hành phương án thay thế** | Khoảng thời gian phương án dự phòng có thể được duy trì an toàn và có nguồn lực. | Kiểm tra nhân sự, chi phí, dữ liệu, giấy phép, thiết bị và rủi ro tích lũy. |

Ví dụ minh họa cho quy trình xử lý đơn hàng: BIA xác định MTPD 8 giờ, RTO 2 giờ, RPO 15 phút và MBCO là tiếp nhận được tối thiểu 40% lượng đơn thường ngày trong 4 giờ đầu, với khả năng gửi xác nhận sau. Những con số này là **giả định để học cách thiết kế**; phải thay bằng phân tích được phê duyệt của tổ chức.

**RTO nên được đặt đủ sớm so với giới hạn kinh doanh**, có xét thời gian phát hiện, kích hoạt, chuyển chế độ, kiểm tra và xử lý độ trễ. MTPD không tự động bằng RTO và RPO không mô tả thời gian khôi phục. Một dịch vụ có thể khôi phục kịp RTO nhưng không đạt MBCO vì chỉ phục vụ được 5% lượng đơn; cũng có thể đáp ứng RTO nhưng thất bại RPO vì mất dữ liệu quá mức.

### 2.2. Mẫu BIA theo tiến trình nghiệp vụ

| Quy trình | Tác động nếu dừng | Phụ thuộc trọng yếu | Mức tối thiểu minh họa | Người xác nhận |
|---|---|---|---|---|
| Nhận đơn | Mất doanh thu, khách hàng không thể đặt mua. | Website/API, định danh, dữ liệu sản phẩm, kênh liên lạc. | Tiếp nhận giới hạn, ghi nhận mã đơn duy nhất và thông báo khả năng giao chậm. | Chủ sản phẩm bán hàng. |
| Thanh toán | Không hoàn tất đơn, nguy cơ thanh toán lặp. | Payment provider, API, ledger, kết nối ngân hàng. | Không ghi nhận “đã thanh toán” khi chưa xác minh; giữ đơn ở trạng thái chờ. | Chủ quy trình tài chính. |
| Giao hàng | Đơn tồn đọng, vi phạm cam kết giao. | Kho, đối tác vận chuyển, địa chỉ, khả năng xuất phiếu. | Xử lý lô ưu tiên có phê duyệt và kiểm soát dữ liệu. | Chủ vận hành logistics. |
| Hỗ trợ khách hàng | Không thể trả lời tình trạng đơn và khiếu nại. | CRM, tổng đài, email, dữ liệu đơn hàng. | Kênh thay thế cung cấp thông tin đã xác minh và nhận yêu cầu. | Trưởng bộ phận hỗ trợ. |

Một BIA thiếu chủ sở hữu hoặc chỉ liệt kê tên ứng dụng sẽ không đủ cho continuity plan. Cần xác định **quy trình kinh doanh** và điều kiện phục vụ khách hàng, rồi mới suy ra hệ thống cần khôi phục.

## 3. Lập bản đồ phụ thuộc và điểm thất bại chung

Một quy trình có thể phụ thuộc vào tài nguyên nhìn thấy và những thành phần ít ai nhớ đến: identity provider, certificate, DNS, hệ thống cấp phép, người phê duyệt, API của đối tác, kết nối MPLS/VPN, message broker hoặc khóa giải mã backup.

~~~mermaid
flowchart TD
    A["Duy trì nhận đơn hàng"] --> B["Nhân sự và kênh hỗ trợ"]
    A --> C["Ứng dụng / API"]
    A --> D["Thanh toán và đối soát"]
    A --> E["Dữ liệu và quản trị"]
    C --> F["DNS / IdP / network / secrets"]
    C --> G["Cloud / containers / CI-CD"]
    D --> H["Nhà cung cấp thanh toán"]
    D --> I["Ledger / message queue"]
    E --> J["Backup / logging / audit"]
    E --> K["Chủ quy trình / phê duyệt"]
~~~

Từ bản đồ này cần hỏi:

- Hệ thống dự phòng có **dùng chung IdP, tenant quản trị, DNS, region, khóa mã hóa hoặc đường Internet** với hệ thống chính không?
- Nhà cung cấp phụ có phụ thuộc cùng một hạ tầng bên thứ ba? Hai hợp đồng khác nhau không bảo đảm tránh cùng một điểm lỗi.
- Nhân viên thay thế có quyền, thiết bị, hướng dẫn và kênh liên lạc khi hệ thống chính bị cô lập không?
- Quy trình thủ công cần dữ liệu nào để bắt đầu và khi nào dữ liệu đó không còn đủ mới?
- Có nguồn lực hạn chế nào: giấy phép, dung lượng, quota, nhân sự trực, năng lực call center hoặc số kết nối tối đa?
- Có hành động dự phòng nào làm tăng nguy cơ lộ dữ liệu, thực hiện giao dịch trùng, mất tính toàn vẹn hoặc bỏ qua kiểm soát phê duyệt?

### 3.1. Dependency register

Ghi từng phụ thuộc cùng người sở hữu, điểm thất bại, lựa chọn thay thế, thời gian chuyển phương án và bằng chứng kiểm thử. Ví dụ: phương án chuyển thanh toán sang đối tác B chỉ khả thi nếu đã kiểm tra pháp lý, cấu hình token, mapping trạng thái giao dịch, đường webhook, đối soát và tải tối thiểu; không được coi “có hợp đồng dự phòng” là bằng chứng chuyển đổi thành công.

Phạm vi kiểm kê nên bao gồm **upstream** (nguồn cần để quy trình chạy) và **downstream** (khách hàng/quy trình khác chịu tác động), kể cả tích hợp SaaS và các chức năng ngoài IT.

## 4. Phân tích rủi ro và chọn continuity strategies

Một chiến lược duy trì hoạt động nên được đánh giá trên khả năng đáp ứng MBCO, RTO/RPO, mức rủi ro bảo mật, tính độc lập của phụ thuộc, chi phí và khả năng duy trì trong khoảng gián đoạn dự kiến.

| Chiến lược | Khi nào phù hợp | Yếu tố cần kiểm chứng |
|---|---|---|
| **Vận hành thủ công có kiểm soát** | Chức năng có thể tiếp tục tạm thời với lưu lượng giới hạn. | Mẫu ghi chép, phân quyền, số người, chất lượng dữ liệu, bảo mật và khả năng đối soát khi hệ thống phục hồi. |
| **Địa điểm/nhân sự thay thế** | Mất tòa nhà, điện, thiết bị hoặc nhóm vận hành chính. | An toàn nhân sự, quyền truy cập, thiết bị, mạng, ca trực, khả năng liên lạc. |
| **Hạ tầng dự phòng/failover** | Dịch vụ công nghệ cần được khôi phục nhanh. | Tính độc lập, dữ liệu đồng bộ, kiểm tra truy cập, capacity, tính an toàn của môi trường dự phòng. |
| **Khôi phục từ backup** | Có thể chấp nhận thời gian phục hồi theo restore. | Backup sạch, có thể giải mã, dữ liệu nhất quán, restore test và RTO/RPO thực tế. |
| **Nhà cung cấp thay thế** | Phụ thuộc chính bị gián đoạn kéo dài. | Hợp đồng, tính khả dụng thực tế, tương thích dữ liệu, quyền truy cập, bảo vệ dữ liệu và thử chuyển đổi. |
| **Giảm mức dịch vụ / ưu tiên khách hàng** | Năng lực tạm thời không đủ cho mọi giao dịch. | Chính sách ưu tiên minh bạch, MBCO, bảo vệ người dùng và cơ chế trở lại bình thường. |
| **Tạm ngừng hành động rủi ro cao** | Dữ liệu/identity hoặc kiểm soát an toàn chưa đáng tin. | Phê duyệt tạm ngừng, thông báo, quy trình xác minh trước khi mở lại. |

**Chiến lược phải giảm thiểu rủi ro tổng thể.** Việc chuyển sang hệ thống dự phòng dùng cùng credential đã bị lộ có thể lan rộng sự cố. Việc lưu dữ liệu khách hàng trong bảng tính cá nhân để tiếp nhận thủ công có thể làm tăng nguy cơ rò rỉ và mất khả năng kiểm toán. Phương án thay thế phải có biện pháp bảo vệ dữ liệu, xác thực, phê duyệt và thu hồi quyền sau gián đoạn.

### 4.1. Nhiều chế độ liên tục thay vì lựa chọn “bật/tắt”

Một dịch vụ có thể vận hành theo các mức:

1. **Normal:** hoạt động và kiểm soát ở mức thông thường.
2. **Degraded:** giữ một phần chức năng an toàn, hạn chế lưu lượng hoặc tạm dừng tác vụ không thiết yếu.
3. **Manual/alternate:** chạy theo quy trình thay thế với năng lực đã được đo.
4. **Suspended for safety:** tạm ngừng chức năng khi không thể bảo đảm tính an toàn/tính chính xác dữ liệu.
5. **Restoring:** kiểm thử và chuyển dần về hệ thống chính.
6. **Normal resumed:** nghiệm thu và đối soát hoàn thành, trách nhiệm được bàn giao.

Một chế độ có thể được kích hoạt riêng cho từng quy trình. Ví dụ xem đơn hàng vẫn khả dụng trong khi chức năng thanh toán bị tạm ngừng để ngăn giao dịch sai.

## 5. Kế hoạch phải có cấu trúc vận hành được

Một continuity plan thực dụng nên đủ chi tiết để người được phân công thực hiện trong điều kiện áp lực mà không phải suy đoán. Các phần tối thiểu:

| Mục kế hoạch | Nội dung bắt buộc | Bằng chứng về tính khả dụng |
|---|---|---|
| **Scope/version/owner** | Dịch vụ, quy trình, tài sản và phạm vi địa lý; phiên bản, người phê duyệt, ngày review. | Control register, lịch phê duyệt, bản phân phối. |
| **Assumptions và giới hạn** | Kịch bản đã bao phủ, phụ thuộc có thể còn thiếu, giới hạn của chiến lược. | BIA, risk assessment, kết quả diễn tập, ngoại lệ. |
| **Activation criteria** | Trigger, cấp độ gián đoạn, điều kiện ra quyết định, quyền kích hoạt. | Decision log, thử kích hoạt theo kịch bản. |
| **Roles và contact tree** | Người chỉ huy, đội triển khai, người thay thế, kênh ngoài băng. | Diễn tập gọi người trực và xác nhận liên lạc. |
| **Recovery priorities** | MBCO, RTO/RPO, thứ tự phục hồi, các điểm phụ thuộc. | BIA được phê duyệt, bản đồ dịch vụ. |
| **Continuity procedures** | Hành động cụ thể, điều kiện trước/sau, điểm kiểm tra, mẫu biểu và rollback. | Runbook, kết quả walkthrough/diễn tập. |
| **Security/data controls** | IAM, xác thực, dữ liệu nhạy cảm, logging, approvals, chống giao dịch trùng. | Bằng chứng cấu hình và kiểm thử kiểm soát. |
| **Communications** | Ai được báo, kênh, tần suất, người phê duyệt thông điệp. | Mẫu thông báo, kết quả thử kênh thay thế. |
| **Return to normal** | Điều kiện phục hồi, đối soát backlog, đóng quyền tạm và bàn giao. | Checklist sign-off, kết quả đối soát, record khôi phục. |
| **Testing và maintenance** | Lịch diễn tập, tiêu chí thành công, người quản lý phát hiện, thay đổi khi có drift. | Exercise report, action tracker, lịch cập nhật. |

Cần chuẩn bị bản kế hoạch có thể truy cập **khi các hệ thống chứa kế hoạch không dùng được**, ví dụ bản sao offline được kiểm soát truy cập hoặc kho độc lập. Bản sao không được phơi bày bí mật đăng nhập, mã khôi phục hoặc thông tin nhạy cảm không cần thiết.

### 5.1. Viết action đủ cụ thể

Viết “liên hệ nhóm hạ tầng để chuyển sang dự phòng” là thiếu. Một bước khả thi nên có:

- Trigger và điều kiện tiền đề.
- Người thực hiện chính và người thay thế.
- Hệ thống/công cụ/tài liệu sẽ dùng, truy cập ở đâu.
- Hành động theo thứ tự, kèm giới hạn không được vượt.
- Kết quả mong đợi và cách kiểm tra.
- Nhánh lỗi, người escalation và điều kiện dừng.
- Bằng chứng phải lưu, thời điểm và người xác nhận.

Ví dụ: “Khi API thanh toán không đáp ứng quá ngưỡng đã phê duyệt, Operations Lead xác nhận tình trạng bằng health check và kênh nhà cung cấp, Finance Owner xác nhận chính sách giữ đơn chờ, Product Owner cho phép chuyển thanh toán sang chế độ pending. Kết quả kỳ vọng: không đánh dấu giao dịch thanh toán thành công nếu chưa có xác nhận; mỗi yêu cầu có mã idempotency duy nhất. Sau khi hệ thống trở lại, Finance Owner đối soát pending transactions trước khi bật chức năng tạo giao dịch mới.”

## 6. Activation, escalation và chỉ huy trong gián đoạn

Quyết định kích hoạt BCP không nên phụ thuộc vào việc nguyên nhân đã được xác định hoàn toàn. Có thể kích hoạt dựa trên **mức ảnh hưởng hiện tại và dự báo**: quy trình trọng yếu dừng quá ngưỡng, hệ thống không thể tin cậy, nguy cơ vượt RTO hoặc dự đoán không thể đạt MBCO.

~~~mermaid
flowchart TD
    A["Ghi nhận gián đoạn và đánh giá tác động"] --> B{"Có nguy cơ vượt ngưỡng BIA?"}
    B -->|Chưa| C["Theo dõi, xử lý vận hành thường"]
    B -->|Có| D["Escalate đến Incident / Continuity Lead"]
    D --> E["Đánh giá an toàn và nguồn lực"]
    E --> F{"Phương án thay thế phù hợp?"}
    F -->|Không| G["Giảm dịch vụ / tạm ngừng chức năng rủi ro"]
    F -->|Có| H["Phê duyệt kích hoạt BCP"]
    H --> I["Phân công, thông báo và thực thi runbook"]
    G --> J["Đánh giá lại theo chu kỳ"]
    I --> J
    J --> K{"Đủ điều kiện trở lại bình thường?"}
    K -->|Chưa| E
    K -->|Có| L["Đối soát, nghiệm thu, bàn giao và cải tiến"]
~~~

### 6.1. Incident/Continuity command

Đặt một đầu mối điều phối, người đưa quyết định nghiệp vụ, người phụ trách an ninh, người thực thi công nghệ, truyền thông và người ghi biên bản. Các nhóm có thể kiêm nhiệm theo quy mô tổ chức, nhưng **thẩm quyền quyết định** cần rõ. Nếu người phụ trách chính không thể liên lạc, kế hoạch phải chỉ rõ người thay thế và ngưỡng escalation.

Với sự cố bảo mật, nhóm IR có quyền đưa ra cảnh báo về trạng thái hệ thống không đáng tin; chủ nghiệp vụ quyết định mức dịch vụ cần duy trì và rủi ro chấp nhận trong phạm vi thẩm quyền. Những mâu thuẫn ảnh hưởng an toàn hoặc tuân thủ phải được đưa đến cơ chế quyết định cấp cao theo kế hoạch.

### 6.2. Mẫu nhật ký quyết định

~~~text
Thời điểm (UTC):
Incident ID:
Tình trạng / phạm vi hiện tại:
Dịch vụ và người dùng bị ảnh hưởng:
Đánh giá nguy cơ vượt RTO/MBCO:
Phương án được xem xét:
Điều kiện an toàn và dữ liệu:
Quyết định (kích hoạt / giới hạn / tạm ngừng):
Người phê duyệt và căn cứ:
Người thực hiện và deadline:
Mốc đánh giá lại:
Liên kết bằng chứng:
~~~

Lưu mốc thời gian, nguồn nhận thông tin và quyết định thay đổi qua các vòng đánh giá. Trong sự cố thực tế, mức độ chắc chắn của thông tin có thể tăng dần; ghi rõ dữ kiện xác nhận, giả định và thông tin chưa biết.

## 7. Bảo vệ dữ liệu và bảo mật trong chế độ dự phòng

Business continuity liên quan trực tiếp đến **confidentiality, integrity và availability**. Chọn phương án dự phòng chỉ dựa trên tính sẵn sàng có thể làm mất bảo mật hoặc sai dữ liệu.

| Tình huống | Rủi ro đặc thù | Kiểm soát cần xác minh |
|---|---|---|
| Nhân viên làm việc từ địa điểm khác | Thiết bị không quản lý, Wi-Fi không tin cậy, chia sẻ dữ liệu trái quy định. | Identity/MFA, thiết bị được phép, kênh liên lạc, phân quyền và logging. |
| Ghi nhận giao dịch thủ công | Sai dữ liệu, trùng giao dịch, người thực hiện không được phê duyệt. | Biểu mẫu có số định danh, hai lớp kiểm tra theo chính sách, lưu an toàn, đối soát và hủy bản sao tạm. |
| Dùng nhà cung cấp dự phòng | Chuyển dữ liệu vượt phạm vi hợp đồng, quyền/API key bị cấp quá rộng. | Điều khoản dữ liệu, quyền tối thiểu, quản trị secret, log thao tác và phương án thu hồi. |
| Chuyển vùng cloud/DR | Backup hoặc quyền dùng chung với vùng bị xâm phạm; vấn đề residency. | Kiểm tra ranh giới tin cậy, quyền, khóa, vị trí xử lý dữ liệu và khả năng giám sát. |
| Tạm bỏ một bước xác thực để duy trì dịch vụ | Tăng khả năng gian lận/chiếm quyền. | Không nới lỏng control trọng yếu tùy tiện; giới hạn chức năng hoặc yêu cầu phê duyệt rủi ro có hạn. |
| Khôi phục dữ liệu sau ransomware | Tái nhiễm, backup lỗi, dữ liệu chưa nhất quán. | Clean rebuild, restore được kiểm thử, rà soát token/quyền, kiểm tra integrity và giám sát tăng cường. |

### 7.1. Phân loại dữ liệu tạm

Khi dùng giấy tờ, bảng tính, file chia sẻ hoặc các kênh truyền thông thay thế, xác định rõ dữ liệu nào được phép ghi, vị trí lưu, ai được truy cập, thời hạn giữ và cách nhập lại hệ thống chính. Tránh lưu số thẻ thanh toán, mật khẩu, token hay dữ liệu cá nhân không cần thiết. Cần chuẩn bị **biểu mẫu được duyệt trước**, không đợi đến lúc gián đoạn mới tự phát tạo bảng dữ liệu.

### 7.2. Ngăn giao dịch trùng và mất toàn vẹn

Với hệ thống phân tán, gián đoạn có thể khiến client không biết một giao dịch đã được xử lý hay chưa. Khi mở chế độ dự phòng, cần dùng mã giao dịch duy nhất, idempotency key nếu có, trạng thái *pending* thay vì suy đoán thành công, và thủ tục reconciliation sau khi nguồn chính phục hồi. Chỉ một bản ghi ở kênh thủ công cũng cần định danh và nguồn xác minh.

### 7.3. Bảo toàn chứng cứ an ninh

Nếu ngừng dịch vụ do nghi ngờ xâm nhập, không dùng BCP làm lý do xóa log, khôi phục đè hoặc mở lại tài khoản đã bị cô lập mà không tham vấn đội IR. Các bước có khả năng làm mất bằng chứng phải tuân theo quyết định điều tra và quyền hạn đã xác định. Một quy trình thay thế có thể được kích hoạt ở vùng độc lập trong khi vùng nghi nhiễm tiếp tục được bảo toàn.

## 8. Quy trình vận hành BCP theo từng giai đoạn

Một kế hoạch dùng được nên mô tả chu kỳ từ trước sự cố đến sau nghiệm thu:

### Giai đoạn A — Preparedness (trước gián đoạn)

- BIA và risk assessment đã được phê duyệt, phân công owner theo quy trình.
- MBCO, RTO/RPO, dependency map và các chế độ thay thế được định nghĩa.
- Nhân sự dự phòng, danh sách liên hệ, thiết bị, giấy phép và kênh liên lạc độc lập đã sẵn sàng.
- Kịch bản và runbook có version, dễ truy cập trong điều kiện hệ thống chính mất.
- Kiểm thử trước đó có kết quả, hạn chế và kế hoạch đóng finding.

### Giai đoạn B — Detection, assessment và activation

- Ghi thời điểm bắt đầu gián đoạn, phạm vi và chất lượng thông tin.
- Dự báo tác động theo các mốc BIA và kích hoạt escalation.
- Kiểm tra rủi ro cho con người, dữ liệu, khách hàng và trạng thái hệ thống đáng tin.
- Quyết định phương án và mức dịch vụ; phân công người phụ trách.
- Thông báo bằng kênh phù hợp, kích hoạt decision log và cadence cập nhật.

### Giai đoạn C — Operate alternate mode

- Chạy runbook ở quy mô đã được phê duyệt.
- Đo thời gian chuyển chế độ, thông lượng, độ trễ, error rate, backlog và ảnh hưởng khách hàng.
- Duy trì kiểm soát quyền, lưu hồ sơ giao dịch, audit và phát hiện sự cố.
- Theo dõi phụ thuộc còn lại và điều kiện phương án thay thế có thể tiếp tục.
- Escalate khi năng lực thấp hơn MBCO hoặc rủi ro vượt mức được duyệt.

### Giai đoạn D — Restore, reconcile, return

- Xác minh hệ thống chính đáng tin, dữ liệu nhất quán và đường trở về được kiểm thử.
- Đồng bộ dữ liệu từ các kênh tạm, phát hiện trùng/mất giao dịch.
- Chuyển traffic và chức năng theo giai đoạn có rollback an toàn.
- Thu hồi quyền tạm, giải phóng thiết bị/nhà cung cấp dự phòng theo quy định.
- Nghiệm thu bởi chủ nghiệp vụ và người phụ trách bảo mật khi liên quan.

### Giai đoạn E — Learning và maintenance

- Đối chiếu mục tiêu với kết quả thực tế, phân tích root cause và hiệu quả BCP.
- Cập nhật BIA, runbook, contact list, hợp đồng và training.
- Đóng những finding bằng retest có bằng chứng, lên lịch diễn tập lại khi có thay đổi đáng kể.
- Theo dõi các rủi ro còn tồn đọng đến khi được xử lý hoặc chấp nhận có hạn.

## 9. Truyền thông và quản lý kỳ vọng

Người vận hành, lãnh đạo, nhân viên, khách hàng, đối tác và các bên có nghĩa vụ báo cáo cần thông tin khác nhau. Kế hoạch phải chỉ định **ai được phép phát ngôn**, nội dung nào đã xác minh, kênh nào khả dụng và nhịp cập nhật.

| Đối tượng | Nội dung trọng tâm | Người chịu trách nhiệm điển hình |
|---|---|---|
| Continuity/Incident command | Tác động, mức phục vụ, rủi ro, quyết định, deadline và phương án thay thế. | Continuity Lead, Incident Lead. |
| Nhân viên nghiệp vụ | Quy trình tạm, hành động được phép/không được phép, biểu mẫu và đầu mối hỗ trợ. | Business Process Owner. |
| Khách hàng | Chức năng bị giới hạn, điều kiện sử dụng, mốc cập nhật tiếp theo và kênh liên lạc thay thế. | Communications/Customer Operations. |
| Nhà cung cấp và đối tác | Phụ thuộc bị ảnh hưởng, phương án chuyển đổi, trách nhiệm, thông tin tối thiểu để phối hợp. | Vendor Owner/Operations. |
| Pháp lý, quyền riêng tư, quản lý tuân thủ | Nghĩa vụ hợp đồng/pháp lý và bằng chứng liên quan khi áp dụng. | Legal/Privacy/Compliance. |

Không dự đoán thời điểm khôi phục như một sự chắc chắn nếu chưa có bằng chứng. Phân biệt **đã xác nhận**, **đang điều tra**, **dự kiến có điều kiện** và **hành động tiếp theo**. Với gián đoạn hệ thống email/chat nội bộ, phải thử kênh thay thế trước: điện thoại, hotline độc lập hoặc cơ chế liên lạc được kiểm soát khác.

### Mẫu thông báo ngắn

~~~text
Mã sự kiện:
Cập nhật lúc:
Dịch vụ bị ảnh hưởng:
Mức hoạt động hiện tại (normal / degraded / alternate / suspended):
Tác động đã xác nhận:
Hướng dẫn hành động an toàn:
Điều chưa xác định:
Điều kiện/mốc cập nhật tiếp theo:
Đầu mối liên hệ:
Người phê duyệt thông báo:
~~~

Kịch bản truyền thông phải kiểm thử cả việc không truy cập được tài khoản quản trị, danh sách liên hệ nằm trong SaaS bị lỗi hoặc cán bộ truyền thông chính vắng mặt.

## 10. Bằng chứng assurance cho Continuity plan

Một bộ security controls liên quan BCP phải được cụ thể hóa thành **mục tiêu → tiêu chí đạt → phương pháp đo → bằng chứng → chủ sở hữu**.

| Control ID minh họa | Mục tiêu kiểm soát | Tiêu chí kiểm chứng và bằng chứng |
|---|---|---|
| **BCP-BIA-01** | Các quy trình trọng yếu có BIA đủ mới và được phê duyệt. | Danh mục quy trình, tác động theo thời gian, MTPD/RTO/RPO/MBCO, chữ ký owner và lịch review. |
| **BCP-DEP-01** | Phụ thuộc quan trọng và điểm thất bại chung được xác định. | Dependency map, kiểm kê nhà cung cấp, phân tích shared identity/network/region và thử nghiệm. |
| **BCP-STR-01** | Chiến lược thay thế có khả năng đạt mức dịch vụ tối thiểu. | Năng lực đã đo, kết quả diễn tập, availability của nguồn lực và phương án fallback. |
| **BCP-ACT-01** | Kế hoạch có thể kích hoạt đúng thẩm quyền khi gián đoạn. | Thử call tree, activation log, decision log và biên bản diễn tập. |
| **BCP-SEC-01** | Chế độ thay thế giữ được kiểm soát an ninh phù hợp. | Kiểm tra IAM, log, bảo vệ dữ liệu, phân quyền giao dịch và kiểm soát bù trừ. |
| **BCP-COM-01** | Bên liên quan nhận hướng dẫn kịp thời qua kênh hoạt động. | Bản ghi gửi/nhận, thử kênh ngoài băng, phê duyệt nội dung. |
| **BCP-EXE-01** | Kế hoạch được diễn tập theo mục tiêu và các kịch bản trọng yếu. | Kịch bản thử, tiêu chí, thời gian đo, kết quả PASS/FAIL/INCONCLUSIVE, phát hiện và retest. |
| **BCP-RET-01** | Chuyển về vận hành bình thường bảo toàn dữ liệu và quyền. | Kết quả reconciliation, thu hồi quyền tạm, nghiệm thu và hậu kiểm. |
| **BCP-MNT-01** | Kế hoạch được cập nhật khi công nghệ, nhà cung cấp hoặc quy trình đổi. | Lịch sử phiên bản, change trigger, owner review và việc phân phối bản mới. |

Các ID và tiêu chí này là ví dụ phục vụ giảng dạy. Kỳ đánh giá, ngưỡng thời gian và phạm vi phải dựa trên rủi ro/biên bản phê duyệt của tổ chức, không phải mặc định theo một tiêu chuẩn.

### Kết luận đánh giá

- **PASS:** có bằng chứng đúng phạm vi, đủ mới và chứng minh tiêu chí bắt buộc được đáp ứng trong bài kiểm tra.
- **FAIL:** phép thử hoặc thực tế cho thấy yêu cầu không đạt, ví dụ chuyển sang phương án thay thế mất 3 giờ trong khi RTO là 2 giờ hoặc không bảo đảm kiểm soát dữ liệu.
- **INCONCLUSIVE:** không đủ bằng chứng, kịch bản chưa kiểm tra, dependency chưa xác minh, dữ liệu đo chưa tin cậy.
- **NOT_APPLICABLE:** tiêu chí thật sự không áp dụng và lý do được xác nhận.

Một quyết định **chấp nhận rủi ro** có thể cho phép kế hoạch vận hành có điều kiện nhưng không tự biến FAIL thành PASS. Hạn chế phải có owner, thời hạn, biện pháp bù trừ và lịch đánh giá lại.

## 11. Diễn tập Continuity plan và đo kết quả

**Diễn tập là cách chủ yếu để kiểm chứng tính thực thi.** Đọc lại tài liệu giúp phát hiện lỗi logic nhưng chưa chứng minh con người, thiết bị, dữ liệu và đối tác có thể thực hiện trong điều kiện thực.

| Loại kiểm thử | Cách thực hiện | Giá trị và giới hạn |
|---|---|---|
| **Checklist review / walkthrough** | Người phụ trách đọc từng bước, xác minh liên hệ và tài liệu. | Tìm lỗi thiếu bước; chưa chứng minh được khả năng thực thi dưới tải. |
| **Tabletop exercise** | Các vai trò thảo luận tình huống, quyết định và luồng escalation. | Kiểm tra quyền quyết định, giả định và phối hợp; ít kiểm chứng tốc độ hệ thống thật. |
| **Functional drill** | Thực hiện một chức năng cụ thể như gọi call tree, chuyển hỗ trợ qua hotline, đối soát mẫu. | Đo thao tác thực tế của một phần kế hoạch. |
| **Technical recovery/failover test** | Thử khôi phục, chuyển vùng hoặc thay đổi hạ tầng có kiểm soát. | Đo năng lực công nghệ; chưa đủ để chứng minh quy trình nghiệp vụ đầu cuối. |
| **End-to-end continuity exercise** | Kết hợp nhân sự, nghiệp vụ, đối tác, công nghệ và dữ liệu theo kịch bản giới hạn rõ. | Gần điều kiện thực hơn nhưng chi phí/rủi ro cao; cần giám sát và cơ chế dừng. |

### 11.1. Kịch bản thử phải có giả định và tình huống phát sinh

Một bài tập tốt thường gồm: mất dịch vụ chính, người chủ chốt vắng mặt, kênh chat nội bộ không dùng được, một phụ thuộc dự phòng hoạt động không đúng hoặc sự kiện bảo mật khiến nguồn backup cần kiểm tra thêm. Kịch bản phải có **mục tiêu**, **trạng thái đầu**, **thời gian bắt đầu**, **inject**, **hành động mong đợi**, **giới hạn an toàn** và **bằng chứng đầu ra**.

Ví dụ diễn tập call tree cần đo thời gian kích hoạt, tỷ lệ liên lạc thành công, người thay thế có nhận nhiệm vụ không và nội dung chỉ dẫn có chính xác không. Một tabletop được đánh giá PASS về phân công chưa chứng minh được RTO của hệ thống vì không thực sự chuyển dữ liệu hoặc mở dịch vụ.

### 11.2. Điều kiện an toàn khi diễn tập

Không chủ động tắt toàn bộ dịch vụ production hay xóa dữ liệu chỉ để “thử giống thật” nếu chưa có phê duyệt, kế hoạch quay lui và biện pháp giới hạn tác động. Có thể dùng môi trường thử nghiệm đại diện, giả lập dependency failure hoặc chạy chức năng thay thế với dữ liệu an toàn. Ghi rõ sai khác so với production để kết luận không vượt quá bằng chứng.

### 11.3. Bảng đo và finding

| Thước đo | Kỳ vọng minh họa | Bằng chứng |
|---|---|---|
| Activation latency | Trước ngưỡng được kế hoạch xác định. | Sự kiện kích hoạt, decision log có timestamp. |
| Contact success | Các vai trò bắt buộc và dự phòng nhận được thông báo. | Acknowledgement/call log theo quy định. |
| Time to MBCO | Quy trình đạt năng lực tối thiểu trước RTO. | Tỷ lệ đơn xử lý, log hoạt động, đối soát số giao dịch. |
| Data integrity | Không có giao dịch thiếu/trùng chưa được quản trị theo tiêu chí. | Transaction ID, reconciliation report, kết quả kiểm tra. |
| Security control continuity | Quyền và audit của chế độ thay thế đáp ứng các tiêu chí. | IAM check, synthetic audit, kiểm tra quyền thực tế. |
| Customer communication | Thông báo được gửi/nhận đúng đối tượng và mốc quy định. | Nội dung được duyệt, kênh, log gửi và xác nhận. |
| Return-to-normal readiness | Đã đối soát backlog và đóng quyền tạm. | Business sign-off, change/ticket, báo cáo hậu kiểm. |

### 11.4. Rủi ro của kết luận giả

Một phép thử chỉ đo rằng hotline đổ chuông không chứng minh nhân viên đủ năng lực tiếp nhận toàn bộ lượng cuộc gọi. Một cuộc diễn tập có hướng dẫn trước có thể đo thời gian nhanh hơn khi xảy ra sự cố bất ngờ. Vì vậy, báo cáo cần nêu **khối lượng, tập dữ liệu, người tham gia, thời gian, độ trễ được giả lập và những phần không được kiểm tra**.

## 12. Mẫu Continuity plan có cấu trúc

Ví dụ YAML dưới đây mô tả một continuity plan cho dịch vụ xử lý đơn hàng, dùng để hình dung những trường cần thiết. Đây **không phải schema chuẩn hay tập lệnh triển khai** của một phần mềm.

~~~yaml
plan:
  id: "BCP-ORDERS-EXAMPLE-005"
  version: "1.0"
  status: "APPROVED_FOR_EXERCISE"
  business_service: "Order processing"
  environment: "production"
  owner: "Head of Commerce Operations"
  approved_at_utc: "2026-11-28T04:00:00Z"
  next_review: "after-major-change-or-scheduled-review"

bia:
  mtpd_minutes: 480
  rto_minutes: 120
  rpo_minutes: 15
  mbco:
    minimum_capacity_percent: 40
    allowed_functions:
      - "Nhận đơn có mã định danh duy nhất"
      - "Tra cứu trạng thái đã xác nhận"
    suspended_functions:
      - "Xác nhận thanh toán chưa được đối soát"
  priority: "HIGH"

dependencies:
  required:
    - "Identity provider"
    - "Order ledger / data store"
    - "Messaging and customer communications"
  external:
    - "Payment service provider"
  shared_failure_checks:
    - "Kiểm tra quyền IdP của phương án dự phòng"
    - "Kiểm tra đường kết nối và nhà cung cấp DNS"

activation:
  trigger: "Nguy cơ không đạt MBCO/RTO hoặc nguồn chính không đáng tin"
  decision_owner: "Continuity Lead"
  security_consulted: "Incident Response Lead"
  alternate_mode: "restricted-order-intake"
  communication_channel: "approved-out-of-band-channel"

operation:
  accountable: "Commerce Service Owner"
  responsible_team: "Business Operations"
  data_recording: "approved-restricted-form"
  unique_transaction_id_required: true
  do_not_mark_payment_success_without_confirmation: true
  escalation_on_capacity_drop: true

return_to_normal:
  prerequisites:
    - "Hệ thống chính được nghiệm thu về chức năng và an toàn"
    - "Các đơn tạm đã được đối soát"
    - "Log và cảnh báo của hệ thống chính hoạt động"
  revoke_temporary_access: true
  business_signoff_required: true

exercise:
  scenario: "Payment provider outage plus identity outage"
  last_result: "NOT_TESTED"
  evidence_location: "restricted-evidence-store/BCP-ORDERS-EXAMPLE-005"
  finding_owner: "Business Continuity Coordinator"
~~~

Các mốc thời gian, tỷ lệ 40%, ID, người phụ trách và những trường được chọn đều **giả định**. Giá trị `APPROVED_FOR_EXERCISE` chỉ nói mẫu này đã được phép dùng cho diễn tập; `NOT_TESTED` cho thấy chưa đủ bằng chứng về khả năng hoạt động thực. Không được coi kế hoạch đã sẵn sàng vận hành thật chỉ vì các trường đã được điền.

### 12.1. Thêm runbook con cho từng quy trình

Tài liệu chính không nên chứa một danh sách lệnh quá dài khó duy trì. Mỗi quy trình thay thế có thể liên kết đến một **runbook phiên bản hóa** gồm điều kiện khởi động, lệnh hoặc thao tác được phê duyệt, biểu mẫu, điểm kiểm tra dữ liệu, cách liên hệ và phương án hoàn nguyên. Cần bảo đảm mọi đường dẫn/tài liệu phụ đều truy cập được trong điều kiện gián đoạn đã nêu.

Nếu sử dụng công cụ quản lý tài liệu, giữ bản đã phê duyệt và lịch sử thay đổi. Khi cập nhật liên hệ khẩn hoặc URL, cần xác minh người thực thi thật có bản mới; kế hoạch “đúng trên repository” nhưng nhân viên chỉ có bản in cũ vẫn là một rủi ro.

## 13. Giám sát liên tục, chỉ số và duy trì kế hoạch

Một BCP có thể trở nên lỗi thời sau một lần thay đổi kiến trúc, chuyển nhà cung cấp, mở thị trường, đổi nhân sự hoặc dữ liệu được phân loại lại. Cần review theo lịch và khi có sự kiện kích hoạt.

Các chỉ số nên theo dõi:

- **BIA coverage:** tỷ lệ quy trình trọng yếu có BIA được duyệt và còn hiệu lực.
- **Plan coverage:** tỷ lệ quy trình có kế hoạch và runbook đáp ứng tiêu chí tối thiểu, xác định chủ sở hữu.
- **Dependency coverage:** tỷ lệ phụ thuộc trọng yếu có phương án xử lý và mức tin cậy được xác nhận.
- **Exercise completion:** tỷ lệ bài thử dự kiến đã được thực hiện trong kỳ, nêu rõ mức thử và phạm vi.
- **Objective achievement:** số bài thử đạt RTO, RPO và MBCO tương ứng trên phạm vi được đo.
- **Communication readiness:** tỷ lệ vai trò liên lạc/đại diện dự phòng được xác nhận trong kỳ.
- **Action closure:** tỷ lệ phát hiện diễn tập được xử lý và retest, số overdue theo mức rủi ro.
- **Evidence freshness:** thời gian kể từ kiểm chứng mới nhất so với chu kỳ rủi ro đã duyệt.

Ví dụ, có 20 quy trình trọng yếu, 18 có kế hoạch được duyệt, nhưng chỉ 12 quy trình đã được thử đủ phần hành động và mức dịch vụ trong kỳ. Có thể báo **plan coverage = 18/20 = 90%** và **tested coverage = 12/20 = 60%** theo định nghĩa. Không được kết luận “90% quy trình sẵn sàng” nếu chưa chứng minh 18 kế hoạch có thể thực thi.

### Khi nào cần cập nhật ngoài lịch?

- Thay đổi RTO/RPO/MBCO hoặc ưu tiên kinh doanh.
- Triển khai hệ thống, cloud account, region, identity provider hoặc dịch vụ SaaS mới.
- Đổi đối tác thanh toán, vận chuyển, nhà cung cấp hạ tầng hay phương thức liên lạc.
- Thay quyền, nhóm trực, chủ quy trình, sơ đồ tổ chức hoặc nơi làm việc.
- Phát hiện mới từ incident, tabletop, restore test, penetration testing hoặc audit.
- Thay đổi chính sách bảo vệ dữ liệu, nghĩa vụ hợp đồng hoặc yêu cầu hoạt động liên quan.

Cập nhật kế hoạch phải dẫn đến **đào tạo hoặc thông báo** tới người liên quan và thử lại những bước bị ảnh hưởng, không chỉ thay một ngày “last reviewed” trong header.

## 14. Tình huống thực hành: Gián đoạn thanh toán và hệ thống định danh

Một doanh nghiệp thương mại điện tử dùng cloud để xử lý đơn hàng, dịch vụ định danh tập trung để đăng nhập quản trị và một nhà cung cấp thanh toán bên ngoài. Trong ngày khuyến mại, cổng thanh toán gặp lỗi kéo dài, đồng thời IdP bị gián đoạn khiến nhóm vận hành không đăng nhập được console. Một số khách hàng nhìn thấy trạng thái “đang xử lý” nhưng chưa nhận xác nhận thanh toán. Chủ doanh nghiệp yêu cầu tiếp tục nhận đơn vì lượng truy cập cao.

BIA giả định xác định:

- **MTPD:** 8 giờ cho quy trình tiếp nhận đơn.
- **RTO:** 2 giờ để cung cấp mức dịch vụ tối thiểu.
- **MBCO:** ít nhất 40% năng lực tiếp nhận đơn, có thông báo rõ trạng thái đơn.
- **RPO:** 15 phút cho dữ liệu đơn hàng được xác nhận.
- Có phương án tiếp nhận tạm bằng hệ thống độc lập nhưng chưa thử đầy đủ.
- Danh sách liên lạc khẩn nằm trong ứng dụng SaaS đang đăng nhập qua chính IdP bị lỗi.

### 14.1. Câu hỏi

1. Có nên cho khách hàng tiếp tục nhận thông báo “thanh toán thành công” khi chưa xác minh từ payment provider không?
2. Ai có quyền kích hoạt phương án tiếp nhận hạn chế và cần thông tin gì?
3. Làm sao kiểm tra phương án dự phòng có thực sự độc lập với IdP bị gián đoạn?
4. Bằng chứng nào chứng minh đạt hoặc chưa đạt MBCO, RTO và RPO?
5. Những bước nào cần thực hiện khi nhà cung cấp thanh toán khôi phục để tránh thanh toán hoặc đơn hàng bị lặp?

### 14.2. Hướng giải quyết

**Bước 1 — Kích hoạt điều phối:** ghi thời điểm phát hiện, đánh giá tác động và dự báo nguy cơ vượt RTO/MBCO. Dùng kênh ngoài băng đã được phê duyệt để thông báo các vai trò chính và người thay thế. Nếu chỉ có danh bạ trong SaaS không truy cập được, đó là một finding về contact readiness.

**Bước 2 — Phân định chức năng có thể duy trì:** cho phép khách hàng gửi đơn hoặc nhận xác nhận “đã tiếp nhận, chưa xác nhận thanh toán” nếu hệ thống và dữ liệu có thể vận hành an toàn. Không thông báo thanh toán thành công khi chưa có chứng cứ từ provider. Có thể tạm ngừng chức năng thu tiền mới nếu không thể bảo đảm tránh giao dịch lặp.

**Bước 3 — Kiểm tra nguồn độc lập:** xác minh vùng hoạt động thay thế, tài khoản quản trị, kênh xác thực, quyền truy cập, DNS, network, message queue và khóa dùng chung. Nếu hệ thống dự phòng vẫn lệ thuộc IdP mất khả dụng, cần phương án quyền khẩn được quản trị trước, có kiểm tra danh tính, giới hạn đặc quyền, log và thu hồi sau sự cố.

**Bước 4 — Triển khai có kiểm soát:** đặt giới hạn tải, dùng mã đơn/idempotency, ghi trạng thái pending, bảo vệ dữ liệu và bật telemetry. Operations Lead đo năng lực tiếp nhận, Product Owner xác minh trải nghiệm khách hàng, Security/IR kiểm tra quyền và giám sát.

**Bước 5 — Theo dõi mục tiêu:** tính thời gian từ mốc sự cố đã quy định đến lúc phương án tối thiểu hoạt động; đo số đơn xử lý thành công so với nhu cầu; xác minh trạng thái dữ liệu và mức mất dữ liệu thực tế. Không gộp tỷ lệ hoạt động của API với năng lực xử lý đơn. Một hệ thống đạt 2 giờ nhưng chỉ tiếp nhận 20% lượng đơn thì **không đạt MBCO 40%**.

**Bước 6 — Đối soát khi phục hồi:** lấy danh sách giao dịch từ provider, kiểm tra đối ứng với ledger, phân loại thành công/thất bại/chưa rõ, xử lý retry theo idempotency và phê duyệt của tài chính. Nhập dữ liệu tạm vào hệ thống chính bằng quy trình kiểm tra trùng/lỗi. Thu hồi quyền khẩn và dừng thu thập dữ liệu ngoài hệ thống chuẩn khi không còn cần.

**Bước 7 — Ghi findings:** ví dụ danh sách liên lạc chỉ nằm trong IdP bị lỗi, hệ thống dự phòng chưa thử tải đủ MBCO hoặc chưa có kịch bản reconciliation. Gán owner, deadline và retest. Không đánh dấu hoàn tất chỉ vì payment provider báo đã hoạt động.

### 14.3. Bảng quyết định minh họa

| Điều kiện | Kết quả quan sát giả định | Kết luận |
|---|---|---|
| Kích hoạt và liên lạc | Người thay thế không có danh sách liên hệ ngoài băng | FAIL đối với tiêu chí liên lạc khẩn. |
| MBCO 40% | Chỉ đo được năng lực tiếp nhận 30% | FAIL đối với mức dịch vụ tối thiểu. |
| RTO 2 giờ | Hoàn thành chuyển chế độ sau 90 phút | PASS về thời gian nếu đạt tiêu chí chức năng đã định nghĩa; không suy ra đạt MBCO. |
| RPO 15 phút | Chưa đối soát đơn hàng trong khoảng gián đoạn | INCONCLUSIVE về mất dữ liệu thực tế. |
| Xác nhận thanh toán | Không ghi thành công khi provider chưa trả kết quả | Kiểm soát an toàn được duy trì trong phạm vi đã thử. |
| Quay lại bình thường | Chưa kiểm tra lặp giao dịch và quyền khẩn | Chưa đủ điều kiện nghiệm thu đầy đủ. |

Qua tình huống, ta thấy **BCP phải được đánh giá theo nhiều điều kiện độc lập**. Một chỉ số đạt không bù được cho dữ liệu chưa chính xác, rủi ro IAM chưa xử lý hoặc mức phục vụ tối thiểu chưa đạt.

## 15. Checklist đánh giá một Continuity plan

Trước khi chấp nhận kế hoạch là đủ để sử dụng, người làm security assurance cần kiểm tra:

1. **Mục tiêu:** Những quy trình/sản phẩm nào phải tiếp tục, vì sao, với MTPD/RTO/RPO/MBCO nào được chủ nghiệp vụ phê duyệt?
2. **Phạm vi:** Inventory tài sản, vị trí, nhân sự, dữ liệu, nhà cung cấp và downstream dependencies đã đủ chưa?
3. **Điểm lỗi chung:** Phương án dự phòng có phụ thuộc cùng IdP, tài khoản cloud, mạng, DNS, khóa hoặc nhóm trực với hệ thống chính không?
4. **Chiến lược:** Mức dịch vụ thay thế có năng lực, dữ liệu và nguồn lực thực tế đáp ứng BIA trong thời gian dự kiến không?
5. **Activation:** Trigger, quyền kích hoạt, escalation, người thay thế và decision log đã được xác định và thử nghiệm chưa?
6. **Runbook:** Hành động, điểm kiểm tra, điều kiện lỗi, giới hạn và người chịu trách nhiệm có đủ rõ để thực thi dưới áp lực không?
7. **Bảo mật:** IAM, MFA, logging, bảo vệ dữ liệu, phân quyền nghiệp vụ và controls bù trừ còn vận hành trong chế độ thay thế không?
8. **Liên lạc:** Danh sách liên hệ và kênh thông tin có truy cập được khi hệ thống chính gián đoạn không? Nội dung đã được phê duyệt?
9. **Dữ liệu và giao dịch:** Có quy trình ghi nhận, định danh, đối soát và tránh trùng khi chuyển lại hệ thống bình thường không?
10. **Thử nghiệm:** Có bài diễn tập theo kịch bản, tiêu chí, kết quả đo, giới hạn, người tham gia và bằng chứng đủ mới không?
11. **Kết luận:** PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE có gắn control ID, phạm vi, evidence và chủ sở hữu không?
12. **Khắc phục:** Finding có thời hạn, người xử lý, kế hoạch retest; ngoại lệ rủi ro có thẩm quyền và ngày hết hiệu lực không?
13. **Duy trì:** Kế hoạch có version, chủ sở hữu, lịch cập nhật khi thay đổi và bản có thể truy cập lúc mất công cụ chính không?
14. **Bàn giao:** Có điều kiện return-to-normal, phê duyệt nghiệp vụ, đóng quyền tạm, kiểm tra dữ liệu và post-incident review không?

**Một Continuity plan có giá trị security assurance khi tổ chức chứng minh được rằng các hoạt động trọng yếu có thể tiếp tục ở mức đã thống nhất, bằng phương án an toàn, có người chịu trách nhiệm, có bằng chứng thử nghiệm và có cơ chế khắc phục khi thực tế chưa đáp ứng mục tiêu.**
