# Chính sách nhà cung cấp

Trong chương **Security policy**, **chính sách nhà cung cấp** (*supplier security policy*, *third-party security policy*) quy định cách tổ chức lựa chọn, sử dụng, giám sát và chấm dứt quan hệ với các bên thứ ba sao cho các rủi ro bảo mật được nhận diện, kiểm soát và đánh giá có bằng chứng. Nhà cung cấp có thể vận hành hạ tầng cloud, xử lý dữ liệu, cung cấp SaaS, API, dịch vụ hỗ trợ, phần mềm, thư viện hoặc tham gia phát triển và vận hành hệ thống.

Một nền tảng học trực tuyến có thể bảo vệ tốt API và cơ sở dữ liệu của mình nhưng vẫn gặp sự cố nếu nhà cung cấp phân tích học tập lưu dữ liệu học viên quá lâu, đối tác tích hợp giữ token có quyền quá rộng, dịch vụ gửi email làm lộ danh sách người nhận, hoặc nhà cung cấp cloud bị gián đoạn mà tổ chức không có phương án phục hồi. **Rủi ro đối với mục tiêu bảo mật không dừng ở ranh giới tổ chức**.

Trong module **SECURITY_SECURITY_ASSURANCE**, chính sách nhà cung cấp phải phục vụ mục tiêu xây dựng **lập luận và bằng chứng** rằng hệ thống đáp ứng các yêu cầu bảo mật: từ phân tích rủi ro, xác định security controls đến kiểm thử, audit, khắc phục finding và duy trì assurance liên tục trong phát triển và vận hành. Việc nhà cung cấp có tài liệu chính sách hoặc chứng nhận là một phần dữ liệu đánh giá; tổ chức vẫn cần kiểm chứng **phạm vi, tính áp dụng, trách nhiệm của mình và rủi ro còn lại**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích mục tiêu của chính sách nhà cung cấp, phân biệt chính sách nội bộ, yêu cầu bảo mật trong hợp đồng, thỏa thuận xử lý dữ liệu và bằng chứng assurance.
2. Phân loại nhà cung cấp theo mức rủi ro của dịch vụ, dữ liệu, quyền truy cập, phụ thuộc vận hành và các bên phụ trợ.
3. Xây dựng tiêu chí thẩm định trước lựa chọn (*due diligence*), onboarding, giám sát, đánh giá lại và offboarding.
4. Thiết kế các yêu cầu bảo mật tối thiểu về truy cập, dữ liệu, tích hợp, ứng phó sự cố, tính liên tục, bên thứ tư và quyền đánh giá.
5. Xây dựng chuỗi **risk → requirement → control owner → test/evidence → finding → residual risk** cho một quan hệ nhà cung cấp.
6. Phân biệt trách nhiệm của bên mua, bên cung cấp và bên thầu phụ trong mô hình shared responsibility.
7. Lập hồ sơ đánh giá có bằng chứng, quản lý ngoại lệ có thời hạn và quyết định chấp nhận rủi ro đúng thẩm quyền.

## 2. Phạm vi và thuật ngữ

### 2.1. Nhà cung cấp là ai?

**Supplier/vendor/third party** là cá nhân hoặc tổ chức bên ngoài cung cấp sản phẩm hoặc dịch vụ mà doanh nghiệp dùng trong một hoạt động. Phạm vi có thể gồm:

- Nhà cung cấp **IaaS/PaaS/SaaS**: hạ tầng, cơ sở dữ liệu quản lý, nền tảng học tập phụ trợ, giám sát, email.
- Nhà cung cấp **API và tích hợp**: cổng thanh toán, dịch vụ xác thực, phân tích dữ liệu, xử lý tài liệu.
- Đối tác **outsourcing/managed service**: SOC, vận hành hạ tầng, hỗ trợ kỹ thuật, phát triển phần mềm.
- Nhà cung cấp **phần mềm và thành phần ICT**: ứng dụng thương mại, agent, thư viện, thiết bị, firmware, công cụ CI/CD.
- Nhà thầu có **quyền vật lý hoặc quyền logic** vào mạng, môi trường và dữ liệu của tổ chức.
- **Subcontractor/fourth party**: bên được nhà cung cấp chính sử dụng để thực hiện một phần dịch vụ hoặc xử lý dữ liệu liên quan.

Nhà cung cấp phần mềm sử dụng thư viện mã nguồn mở cũng có rủi ro chuỗi cung ứng, nhưng chính sách **quản trị nhà cung cấp trực tiếp** không tự động thay thế quy trình quản lý dependency, SBOM, provenance và secure build. Tổ chức cần xác định phạm vi quy trình tương ứng và nơi chúng liên kết với nhau.

### 2.2. Chính sách nhà cung cấp khác các tài liệu liên quan thế nào?

| Tài liệu/đối tượng | Vai trò | Ví dụ |
|---|---|---|
| **Supplier security policy** | Quy tắc quản trị nội bộ về yêu cầu, trách nhiệm, quyết định và vòng đời nhà cung cấp | Bên thứ ba truy cập dữ liệu nhạy cảm phải được đánh giá và phê duyệt theo cấp rủi ro |
| **Supplier security standard/baseline** | Chi tiết kỹ thuật và tiêu chí tối thiểu áp dụng theo loại dịch vụ | SSO/MFA cho truy cập đặc quyền; log và điều kiện thu hồi quyền |
| **Security requirements trong hợp đồng/SOW** | Điều khoản ràng buộc trách nhiệm, cam kết và khả năng thực thi giữa các bên | Yêu cầu báo sự cố, hợp tác điều tra, trả/xóa dữ liệu, quản lý nhà thầu phụ |
| **DPA hoặc phụ lục xử lý dữ liệu khi áp dụng** | Điều chỉnh vai trò và nghĩa vụ xử lý dữ liệu cá nhân theo luật/hợp đồng tương ứng | Mục đích xử lý, loại dữ liệu, bên xử lý phụ, thời hạn và biện pháp bảo vệ |
| **SLA/OLA** | Mức dịch vụ, vận hành, phản hồi và/hoặc khôi phục | Điều kiện thời gian hỗ trợ, tính sẵn sàng, phản hồi sự cố |
| **Risk assessment và due diligence** | Đánh giá kịch bản, biện pháp và khoảng trống của nhà cung cấp | Tài sản, mức phơi bày, controls, bằng chứng, residual risk |
| **Assurance evidence** | Tài liệu và kết quả có thể kiểm tra hỗ trợ kết luận | Cấu hình, kết quả test, SOC report, chứng nhận có phạm vi, nhật ký và hồ sơ review |
| **Exception/acceptance record** | Ghi quyết định xử lý sai lệch và rủi ro còn lại theo thẩm quyền | Ngoại lệ tạm khi chưa có SSO, có control bù trừ và hạn khắc phục |

Một chính sách công bố nội bộ **chưa mặc nhiên là nghĩa vụ ràng buộc nhà cung cấp**. Các yêu cầu thực thi phải được chuyển vào hợp đồng, phụ lục, quy trình phê duyệt, thiết kế tích hợp hoặc cơ chế khác phù hợp. Ngược lại, một điều khoản hợp đồng cũng chưa đủ chứng minh control đang hoạt động.

### 2.3. Hai góc nhìn chính sách

Có thể hiểu “chính sách nhà cung cấp” theo hai góc nhìn bổ sung:

1. **Chính sách tổ chức áp dụng khi làm việc với nhà cung cấp:** phân loại, đánh giá, lựa chọn, thỏa thuận, cấp quyền, kiểm tra, theo dõi và chấm dứt.
2. **Yêu cầu bảo mật mà nhà cung cấp phải thực hiện hoặc chứng minh:** các biện pháp về dữ liệu, quyền, thay đổi, nhân sự, bảo mật phần mềm, giám sát, khôi phục, kiểm toán và hợp tác ứng phó.

Bài này chủ yếu xây dựng góc nhìn thứ nhất, đồng thời chỉ cách chuyển nó thành yêu cầu và bằng chứng của góc nhìn thứ hai.

## 3. Vì sao cần chính sách nhà cung cấp?

### 3.1. Mối đe dọa và tác động

| Kịch bản | Đường tác động | Mục tiêu bị ảnh hưởng |
|---|---|---|
| Token tích hợp bên thứ ba bị lộ hoặc cấp quyền quá rộng | Tài khoản/ứng dụng bên ngoài truy cập API hoặc dữ liệu | Confidentiality, integrity |
| Nhà cung cấp lưu hoặc dùng dữ liệu vượt mục đích | Dữ liệu học viên được sao chép, phân tích hoặc chia sẻ không đúng phạm vi | Privacy, confidentiality, compliance |
| Nhà cung cấp ngừng dịch vụ bất ngờ | Phụ thuộc API/cloud ngăn đăng nhập, học tập hoặc thu phí | Availability, business continuity |
| Bản cập nhật hoặc thư viện bị can thiệp | Mã hoặc artifact không đáng tin được đưa vào pipeline/production | Integrity, supply-chain security |
| Tài khoản hỗ trợ của nhà cung cấp không bị thu hồi | Truy cập đặc quyền còn tồn tại sau hết hợp đồng | Access control, accountability |
| Sự cố tại subprocessor không được thông báo kịp | Tổ chức thiếu thời gian điều tra, khắc phục và đáp ứng nghĩa vụ | Incident response, privacy, compliance |
| Một nhà cung cấp tập trung nhiều chức năng thiết yếu | Sự cố chung ảnh hưởng đồng thời nhiều dịch vụ | Concentration risk, resilience |
| Chuyển hoặc xóa dữ liệu khi kết thúc hợp tác không đầy đủ | Nhà cung cấp tiếp tục giữ dữ liệu hoặc khóa/token còn hiệu lực | Data lifecycle, confidentiality |

Không phải tất cả rủi ro đều xuất phát từ việc nhà cung cấp bị tấn công. **Sai hợp đồng, cấu hình sai ở phía bên mua, đánh giá thiếu độ phủ, thay đổi dịch vụ không được báo, hoặc phụ thuộc không có phương án thay thế** cũng có thể tạo rủi ro lớn.

### 3.2. Mục tiêu của chính sách

Một supplier security policy hiệu quả cần giúp tổ chức:

- Nhìn thấy **đầy đủ quan hệ và phụ thuộc quan trọng**, kể cả dịch vụ miễn phí, thử nghiệm và bên thứ tư liên quan.
- Bảo đảm **đánh giá tương xứng với rủi ro**, không áp một checklist nặng như nhau cho mọi nhà cung cấp.
- Xác định **security requirements rõ ràng, khả thi và đo được** trước khi cấp dữ liệu/quyền truy cập.
- Quy định **thẩm quyền phê duyệt, ngoại lệ và residual risk**.
- Thu thập **bằng chứng đúng phạm vi** để hỗ trợ các claim assurance, không chỉ tick hộp “đã có chứng chỉ”.
- Giám sát **thay đổi, sự cố, hiệu quả control** trong thời hạn hợp tác.
- Bảo đảm **thu hồi quyền, dữ liệu và phụ thuộc** theo quy trình khi kết thúc dịch vụ.

## 4. Nguyên tắc thiết kế chính sách

Một bộ nguyên tắc có thể áp dụng để thống nhất quyết định:

1. **Risk-based:** độ sâu kiểm tra, điều khoản và tần suất giám sát phụ thuộc tác động và khả năng xảy ra, không chỉ giá hợp đồng.
2. **Least privilege/data minimization:** chỉ chia sẻ dữ liệu và quyền thật sự cần cho mục đích được phê duyệt.
3. **Ownership:** mọi nhà cung cấp trong phạm vi đều có business owner và đầu mối chịu trách nhiệm quản trị.
4. **Security-by-design:** yêu cầu đặt ra **trước khi tích hợp** và được xét cùng kiến trúc, dữ liệu, pháp lý.
5. **Shared responsibility:** phân định control do nhà cung cấp hay bên mua thực thi, gồm các đường ranh giới dễ bỏ sót.
6. **Evidence-based assurance:** phân biệt *control được mô tả*, *control được triển khai*, *control vận hành có hiệu quả*.
7. **Lifecycle management:** đánh giá trước hợp đồng, trong vận hành, khi thay đổi và lúc chấm dứt.
8. **Transparency & escalation:** ghi rủi ro, khoảng trống, finding, quyết định và cơ chế leo thang đúng thẩm quyền.
9. **Proportionality & practicality:** tập trung vào những điều quan trọng với loại dịch vụ; tránh thu gom tài liệu không sử dụng.
10. **Traceability:** giữ liên kết yêu cầu → control → evidence → kết luận → action → quyết định.

**Ví dụ:** nhà cung cấp văn phòng phẩm không truy cập hệ thống thường có rủi ro bảo mật CNTT thấp hơn một nhà cung cấp vận hành identity provider cho toàn bộ người dùng. Tuy nhiên, nếu nhà cung cấp văn phòng phẩm có quyền vật lý vào khu vực chứa máy chủ, cần đánh giá rủi ro theo thực tế.

## 5. Quản trị vai trò và thẩm quyền

### 5.1. Ai chịu trách nhiệm cho quan hệ nhà cung cấp?

| Vai trò | Trách nhiệm chính |
|---|---|
| **Business/vendor owner** | Xác định nhu cầu, mục đích, tài sản liên quan, mức độ quan trọng, giám sát dịch vụ và quyết định kinh doanh trong thẩm quyền |
| **Risk owner** | Chịu trách nhiệm lựa chọn phương án xử lý/chấp nhận residual risk theo ủy quyền |
| **CISO/Security/GRC** | Thiết lập baseline, phương pháp phân loại, review bằng chứng, tư vấn rủi ro, theo dõi finding và báo cáo |
| **Procurement/Vendor management** | Bảo đảm quy trình lựa chọn, quản lý hồ sơ hợp đồng, gia hạn, danh sách nhà cung cấp và nhắc đánh giá |
| **Legal/Privacy/DPO khi có** | Xác định nghĩa vụ pháp lý, điều khoản dữ liệu, thông báo sự cố, trách nhiệm hợp đồng trong phạm vi được giao |
| **Engineering/Architecture/Platform** | Thiết kế tích hợp, quản lý quyền và dữ liệu, kiểm thử kỹ thuật, giám sát, ngừng kết nối khi cần |
| **IT/Identity/Operations** | Cấp/thu hồi tài khoản, cấu hình SSO, theo dõi access, quản lý thiết bị và hỗ trợ vận hành |
| **Supplier security/contact owner** | Cung cấp thông tin và bằng chứng, vận hành control bên mình, thực hiện cam kết và thông báo theo thỏa thuận |
| **Internal audit/assessor** | Đánh giá quy trình và bằng chứng theo nhiệm vụ, mức độc lập thích hợp |
| **Lãnh đạo/ủy ban rủi ro** | Phê duyệt những vấn đề vượt thẩm quyền đơn vị, cấp nguồn lực và giám sát rủi ro tập trung |

Cần phân biệt **người thu thập evidence**, **người đánh giá** và **người phê duyệt residual risk**. Không nên cho phép một người triển khai tích hợp tự tuyên bố rủi ro không đáng kể rồi bỏ qua quy trình thẩm định mà không có cơ chế phù hợp.

### 5.2. Minh họa RACI

R = thực hiện, A = chịu trách nhiệm cuối cùng theo ủy quyền, C = tham vấn, I = được thông báo.

| Hoạt động | Business owner | Security/GRC | Engineering/Platform | Procurement/Legal | Risk owner cấp có quyền |
|---|---|---|---|---|---|
| Đăng ký và xác định mục đích dùng nhà cung cấp | A/R | C | C | I | I |
| Phân tích rủi ro và yêu cầu kiểm soát | C | A/R theo phương pháp được giao | C | C | I |
| Tích hợp, cấp quyền và test | C | C | A/R | I | I |
| Soạn điều khoản hợp đồng và nghĩa vụ dữ liệu | C | C | C | A/R theo phạm vi | I |
| Quyết định sử dụng khi còn residual risk | R đề xuất | C/đưa ý kiến | C | C | A |
| Theo dõi dịch vụ và thay đổi | A/R | C | R với phần kỹ thuật | C | I |
| Chấm dứt và thu hồi quyền/dữ liệu | A | C | R | R với hợp đồng | I |

Bảng này **chỉ minh họa**. Một tổ chức có thể phân công GRC là reviewer thay vì accountable cho assessment, hoặc tách Legal và Procurement thành hai đầu mối. RACI thực tế cần một người chịu trách nhiệm rõ cho từng quyết định, phản ánh cơ cấu được phê duyệt.

## 6. Danh mục nhà cung cấp và phân loại rủi ro

### 6.1. Không thể quản lý những bên không có trong inventory

**Supplier inventory** là danh mục theo dõi nhà cung cấp, dịch vụ, mục đích, hệ thống tích hợp, quyền, dữ liệu, owner, hợp đồng, thời hạn và đánh giá. Cần kết hợp nguồn từ Procurement, chi phí cloud/SaaS, SSO/app registrations, secret management, CMDB, data flow và tích hợp mã nguồn khi phù hợp.

Các trường hữu ích:

- Supplier ID, tên bên ký hợp đồng, dịch vụ/sản phẩm, owner.
- Hệ thống phụ thuộc, mục đích kinh doanh, phạm vi địa lý hoặc bên sử dụng.
- Loại dữ liệu được truy cập, xử lý, lưu hoặc truyền; dữ liệu cá nhân/nhạy cảm nếu có.
- Quyền truy cập vào production, IAM, mạng, mã nguồn, log, backup hoặc tài khoản dịch vụ.
- Phân loại criticality, risk tier, inherent risk và residual risk.
- Subprocessors/fourth parties quan trọng đã biết và cơ chế thông báo thay đổi.
- Hợp đồng, DPA (nếu cần), điều khoản bảo mật, kỳ đánh giá và evidence links.
- Ngoại lệ, finding, hành động khắc phục, ngày hết hạn/renewal, exit plan.

Những ứng dụng SaaS được nhóm nhỏ tự đăng ký (*shadow IT*) cũng có thể xử lý dữ liệu quan trọng, kể cả khi thanh toán bằng thẻ cá nhân hoặc sử dụng gói miễn phí. Chính sách nên thiết kế quy trình khai báo và đánh giá khả thi để giảm tình trạng tích hợp ngoài tầm quan sát.

### 6.2. Đánh giá inherent risk theo loại dịch vụ

Trước khi yêu cầu hàng trăm bằng chứng từ nhà cung cấp, hãy xem dịch vụ có thể gây tác động gì **nếu chưa xét hiệu quả những control đã được chứng minh**.

| Yếu tố | Câu hỏi phân loại | Gợi ý độ rủi ro |
|---|---|---|
| **Độ nhạy dữ liệu** | Có dữ liệu học viên, thanh toán, thông tin xác thực, khóa hoặc dữ liệu bị hạn chế? | Tác động tăng khi dữ liệu nhạy cảm và quy mô lớn |
| **Mức truy cập** | Nhà cung cấp chỉ nhận dữ liệu đầu ra hay có quyền ghi, admin, remote support? | Quyền thay đổi production hoặc đọc nhiều dữ liệu cần đánh giá sâu |
| **Mức phụ thuộc** | Ngừng dịch vụ có làm dừng đăng nhập, giao dịch, học tập, backup? | Phụ thuộc trọng yếu, thiếu phương án thay thế làm tác động tăng |
| **Kết nối/bề mặt tấn công** | Có webhook, VPN, agent, SDK, CI/CD hoặc kết nối trực tiếp vào hạ tầng? | Đường kết nối có quyền cao hoặc nhiều ranh giới cần thêm control |
| **Bên thứ tư** | Có subprocessor/outsourcing, chuỗi cung ứng phức tạp? | Thiếu minh bạch về luồng dữ liệu và kiểm soát làm tăng bất định |
| **Phạm vi pháp lý/hợp đồng** | Có yêu cầu địa bàn, lưu trữ, xử lý dữ liệu, thông báo, đánh giá? | Nghĩa vụ áp dụng có thể yêu cầu biện pháp và điều khoản riêng |
| **Khả năng thay thế** | Có dễ di chuyển dữ liệu hoặc chuyển nhà cung cấp khác không? | Lock-in và tập trung rủi ro ảnh hưởng resilience |
| **Lịch sử và mức độ bất định** | Có sự cố, finding, báo cáo lỗi hoặc evidence bị giới hạn? | Cần điều tra/đánh giá chặt hơn |

Không nên dùng **giá trị hợp đồng** làm đại diện duy nhất cho rủi ro. Một API chi phí nhỏ nhưng được cấp token đọc dữ liệu học viên có thể quan trọng hơn một hợp đồng phần mềm không chạm dữ liệu production.

### 6.3. Phân tầng minh họa

| Tier nội bộ | Đặc điểm minh họa | Cách đánh giá gợi ý |
|---|---|---|
| **Critical** | Nhà cung cấp hỗ trợ dịch vụ cốt lõi, dữ liệu nhạy cảm diện rộng hoặc có quyền đặc biệt và ảnh hưởng nghiêm trọng khi gián đoạn | Thẩm định sâu, điều khoản rõ, review kiến trúc/tích hợp, giám sát thường xuyên, exit/continuity plan |
| **High** | Xử lý dữ liệu nhạy cảm hoặc có tích hợp đáng kể nhưng có giới hạn tác động | Đánh giá control/evidence theo lĩnh vực rủi ro, hợp đồng và kỳ review phù hợp |
| **Moderate** | Dữ liệu/khả năng ảnh hưởng được giới hạn, có thể thay thế hoặc cô lập | Checklist và bằng chứng theo phạm vi, kiểm tra khi thay đổi |
| **Low** | Không truy cập dữ liệu nhạy cảm hay hệ thống trọng yếu và tác động thấp | Sàng lọc tối thiểu, inventory, owner và kiểm soát mua sắm |

Đây là **tier mẫu**, không phải phân loại bắt buộc của một tiêu chuẩn. Tiêu chí, ngưỡng và thẩm quyền phải được định nghĩa nội bộ. Mức **inherent risk** ban đầu định hướng độ sâu đánh giá; chỉ sau khi xác minh control mới kết luận **residual risk**.

### 6.4. Minh họa ba nhà cung cấp

- **Identity provider cho toàn hệ thống:** thường cần đánh giá sâu về bảo vệ danh tính, quyền quản trị, logging, độ sẵn sàng, phục hồi và lock-in do tác động rộng.
- **Dịch vụ gửi email giao dịch:** xem loại dữ liệu chuyển qua template, khóa API, quyền gửi, chống lạm dụng, lưu dữ liệu, nhật ký và cơ chế thay thế khi ngừng dịch vụ.
- **Công cụ khảo sát không nhận dữ liệu cá nhân và không tích hợp production:** có thể đánh giá nhẹ hơn, nhưng phải xác minh phạm vi dữ liệu thực sự trước khi xếp thấp.

Khi một công cụ khảo sát sau này bắt đầu thu thập email học viên hoặc kết nối SSO, đó là **trigger phân loại và thẩm định lại**.

## 7. Thẩm định trước hợp tác (due diligence)

### 7.1. Mục tiêu của thẩm định

Due diligence không phải chỉ là gửi một bảng câu hỏi cho nhà cung cấp và nhận câu trả lời “Yes”. Mục tiêu là hiểu **mô hình dịch vụ, loại dữ liệu, đường kết nối, trách nhiệm, năng lực kiểm soát và bằng chứng** để quyết định có thể dùng nhà cung cấp trong phạm vi dự kiến hay không.

Một quy trình khả thi:

1. **Xác nhận mục đích, dịch vụ, phạm vi và data flow** cùng business owner.
2. **Phân tầng rủi ro vốn có** để chọn độ sâu kiểm tra.
3. **Lập danh sách requirements áp dụng**: quyền, dữ liệu, lưu trữ, logging, availability, incident, subprocessor, exit.
4. **Thu thập và đánh giá bằng chứng** từ bên cung cấp; kiểm tra phạm vi, thời kỳ, ngoại lệ và mức độ đáng tin.
5. **Kiểm tra phần do bên mua quản lý**: thiết kế tích hợp, OAuth scope, API key, network, encryption, backup, logging, quyền cấp.
6. **Ghi phát hiện và kế hoạch khắc phục**: mức rủi ro, owner, deadline, control bù trừ và test.
7. **Đưa ra quyết định được phê duyệt**: dùng, dùng có điều kiện, trì hoãn hay không lựa chọn; lưu căn cứ.
8. **Theo dõi lại sau onboarding** để xác minh trạng thái cấu hình và phạm vi thực tế phù hợp quyết định.

### 7.2. Các nhóm câu hỏi cần chọn theo rủi ro

| Chủ đề | Câu hỏi kiểm tra | Evidence có thể yêu cầu |
|---|---|---|
| Quản trị bảo mật | Ai chịu trách nhiệm, chính sách được review và giám sát thế nào? | Chính sách có phiên bản, vai trò, report đánh giá |
| IAM và nhân sự | Cấp/thu hồi quyền, MFA, privileged access, offboarding và rà soát ra sao? | Cơ chế kiểm soát, sample evidence hoặc kết quả audit thích hợp |
| Dữ liệu và privacy | Dữ liệu nào được xử lý, ở đâu, trong bao lâu, cho mục đích gì? | Data flow, danh sách loại dữ liệu, retention/deletion controls, DPA khi áp dụng |
| Kiến trúc/cloud | Cô lập khách hàng, mã hóa, khóa, cấu hình và quyền admin thế nào? | Architecture overview, policy và đánh giá/kiểm thử có thể chia sẻ |
| Secure development | Thực hiện review code, dependency scan, threat modeling, pentest thế nào? | Quy trình và kết quả đánh giá theo phạm vi, bản tóm tắt finding |
| Logging và monitoring | Có log các sự kiện quan trọng, cảnh báo và xử lý kịp? | Mô tả telemetry, test monitoring, incident process |
| Incident response | Nhận diện, xử lý, bảo toàn bằng chứng và phối hợp thông báo thế nào? | IR plan, kết quả diễn tập, điều khoản hợp tác |
| Continuity/recovery | Bảo đảm dữ liệu và dịch vụ phục hồi đến đâu? | BCP/DR plan, kết quả restore/DR test và giới hạn |
| Subprocessors | Những bên nào tiếp cận dữ liệu/dịch vụ, cơ chế kiểm soát và thay đổi? | Danh sách subprocessor, flow-down requirements, thông báo |
| Assurance/audit | Đã được đánh giá theo phạm vi nào, bởi ai, kỳ nào, finding mở nào? | Audit report, chứng nhận có scope, corrective action status |
| Exit | Có khả năng xuất dữ liệu, thu hồi truy cập và xác minh xóa dữ liệu? | Exit process, data export format, deletion evidence mẫu |

Có thể yêu cầu **bằng chứng thay thế phù hợp** khi nhà cung cấp không thể cung cấp tài liệu nhạy cảm như log khách hàng khác, cấu hình bí mật hoặc báo cáo pentest chi tiết. Từ chối chia sẻ chi tiết nhạy cảm không tự động đồng nghĩa control yếu; điều cần ghi là **khả năng chứng minh claim còn đến đâu** và rủi ro do evidence gap.

### 7.3. Cách sử dụng chứng nhận và báo cáo bên thứ ba

Các ví dụ thường gặp gồm chứng nhận ISO/IEC 27001, báo cáo SOC 2 hoặc tài liệu đánh giá bảo mật độc lập. Khi đọc:

- **Phạm vi (scope):** tổ chức, dịch vụ, địa điểm, hạ tầng hoặc control nào được bao phủ?
- **Tiêu chí và loại báo cáo:** đánh giá điều gì, thiết kế ở một thời điểm hay cả vận hành trong một kỳ?
- **Thời gian:** có phù hợp thời điểm đánh giá, có cần thư cập nhật thông tin cho kỳ trống?
- **Ngoại lệ/finding:** kết quả nào không đạt, xử lý ra sao, ảnh hưởng đến dịch vụ đang dùng?
- **Shared responsibility:** control nào người mua vẫn phải tự vận hành?
- **Subprocessor/subservice:** phần nào được báo cáo bao gồm hoặc loại trừ?
- **Tính xác thực:** nguồn báo cáo và bên đánh giá có đáng tin, phiên bản có được xác nhận không?

**Chứng nhận ISO/IEC 27001** liên quan đến hệ thống quản lý an toàn thông tin trong phạm vi chứng nhận; nó không tự chứng minh mọi tính năng SaaS không có lỗ hổng. **SOC 2 Type I/Type II** có phạm vi và thời kỳ đánh giá khác nhau, không phải bằng chứng phổ quát cho mọi sản phẩm của nhà cung cấp. Báo cáo pentest chỉ phản ánh mục tiêu, phạm vi, điều kiện và thời điểm đã kiểm thử.

Không mặc định yêu cầu mọi nhà cung cấp phải có một chứng chỉ cụ thể. Yêu cầu thích hợp phải dựa vào rủi ro, hợp đồng và tiêu chí chương trình đánh giá đang áp dụng.

## 8. Chuyển chính sách thành yêu cầu bảo mật có thể thực thi

### 8.1. Yêu cầu phải cụ thể, đo được và phân công rõ

So sánh:

- **Mơ hồ:** “Nhà cung cấp phải bảo đảm bảo mật cao.”
- **Có thể kiểm chứng hơn:** “Tài khoản tương tác có quyền quản trị dịch vụ trong phạm vi phải được bảo vệ bằng cơ chế xác thực mạnh theo baseline đã phê duyệt; quyền được gán tối thiểu, ghi log và thu hồi theo quy trình khi không còn nhu cầu.”

Mỗi requirement nên có **ID, nguồn, scope, control owner, tiêu chí đạt, phép kiểm tra, evidence owner, tần suất/trigger và cách xử lý ngoại lệ**.

### 8.2. Các lĩnh vực baseline

| Lĩnh vực | Yêu cầu ví dụ | Cần xác minh |
|---|---|---|
| Quản trị và trách nhiệm | Có đầu mối bảo mật, quy trình rủi ro và phản hồi yêu cầu đánh giá | RACI, liên hệ bảo mật, record review |
| Identity & privileged access | Xác thực phù hợp, least privilege, phân vai, rà soát và offboarding | Config, phân quyền, test và kết quả review |
| Phân tách dữ liệu/tenant | Không truy cập chéo khách hàng/tenant ngoài thẩm quyền | Kiến trúc cô lập, negative tests, kết quả đánh giá |
| Data protection | Chỉ xử lý dữ liệu cần thiết, bảo vệ trong lưu trữ/truyền, retention/deletion theo thỏa thuận | Data mapping, key/crypto control, deletion procedures và test |
| Secure development | Quản lý lỗ hổng, dependencies, thay đổi và kiểm thử bảo mật theo rủi ro | SDLC evidence, scan, pentest summary, finding/retest |
| Logging và incident | Ghi sự kiện quan trọng, bảo vệ log, phản ứng và thông báo theo điều khoản | Log/control description, test alert, IR drill, report |
| Availability và continuity | Có khả năng phục hồi phù hợp mức phụ thuộc của doanh nghiệp | Kế hoạch BCP/DR, kết quả diễn tập, RPO/RTO liên quan |
| Subsupplier/fourth party | Thông báo và ràng buộc yêu cầu bảo mật tương ứng cho bên phụ trợ | Supplier list, flow-down clauses, cơ chế quản lý thay đổi |
| Audit/assurance | Cho phép hình thức đánh giá và cung cấp evidence phù hợp phạm vi | Báo cáo kiểm toán, quyền review, kế hoạch khắc phục |
| Exit/transition | Trả/xóa dữ liệu, thu hồi quyền, bàn giao trong giới hạn thời hạn thỏa thuận | Exit test, export, xác nhận thu hồi/xóa và ngoại lệ lưu trữ |

Những yêu cầu trong bảng là **mẫu chính sách nội bộ**, không tự mang hiệu lực của một luật hoặc chứng nhận. Tổ chức phải điều chỉnh theo dữ liệu, loại dịch vụ, quốc gia, hợp đồng và chương trình kiểm tra.

## 9. Điều khoản bảo mật trong hợp đồng

### 9.1. Vì sao hợp đồng quan trọng?

Chính sách nội bộ giúp tổ chức **quyết định và kiểm tra**. Hợp đồng giúp quy định **quyền và nghĩa vụ giữa các bên**, nhất là khi xảy ra sự cố, thay đổi nhà cung cấp hoặc phát sinh tranh chấp.

Nhóm Security cần phối hợp Procurement và Legal để bảo đảm yêu cầu được chuyển thành điều khoản phù hợp thay vì chỉ gửi một checklist mà không có cơ chế thực thi.

### 9.2. Những nhóm điều khoản thường cần xem xét

1. **Phạm vi dịch vụ, dữ liệu và mục đích xử lý:** nhà cung cấp được phép làm gì, với loại dữ liệu nào, bên nào chịu trách nhiệm xác định mục đích/phương thức.
2. **Security measures:** chuẩn tối thiểu và quyền yêu cầu giải thích/đối chiếu hiệu quả biện pháp trong phạm vi.
3. **Access và personnel:** kiểm soát nhân sự, đặc quyền, nhà thầu, offboarding và confidentiality.
4. **Incident notification/cooperation:** loại sự cố cần thông báo, thời hạn cụ thể theo thỏa thuận và quy định áp dụng, kênh liên hệ, thông tin phải cung cấp, phối hợp điều tra/khắc phục.
5. **Vulnerability/change management:** xử lý lỗ hổng theo rủi ro, thông báo thay đổi quan trọng ảnh hưởng control hoặc service.
6. **Subprocessors:** điều kiện sử dụng bên phụ trợ, cập nhật danh sách, yêu cầu flow-down và cơ chế phản đối/đánh giá khi có thay đổi nếu áp dụng.
7. **Data location/retention/deletion:** giới hạn địa điểm, lưu giữ, bản sao lưu, trả dữ liệu, xóa theo yêu cầu và ngoại lệ lưu trữ bắt buộc.
8. **Audit/evidence rights:** báo cáo độc lập, quyền hỏi, kiểm tra hoặc đánh giá trong giới hạn bảo mật và quy định hợp đồng.
9. **Availability/BCP/DR:** mục tiêu dịch vụ và khả năng hỗ trợ phục hồi, điều kiện thông báo gián đoạn.
10. **Termination/transition:** hỗ trợ di chuyển dịch vụ/dữ liệu, định dạng xuất, trả hoặc xóa dữ liệu, hủy credential và xác nhận kết thúc.
11. **Liability và xử lý vi phạm:** phân chia trách nhiệm, biện pháp khắc phục, thông báo và phối hợp theo tư vấn pháp lý.
12. **Thay đổi nghĩa vụ/tiêu chí:** cách cập nhật điều khoản khi dịch vụ, loại dữ liệu hoặc phạm vi pháp lý thay đổi.

Không có một **số giờ thông báo sự cố, thời gian lưu log, thời gian xóa dữ liệu, yêu cầu mã hóa** mặc định đúng cho mọi giao dịch. Các mốc này phải xác định theo rủi ro, nhu cầu ứng phó, luật/hợp đồng áp dụng và khả năng thực thi, rồi đưa vào tiêu chí kiểm chứng tương ứng.

### 9.3. Ví dụ diễn đạt ở mức mục tiêu

Một điều khoản hướng mục tiêu có thể nói: nhà cung cấp phải **thông báo không chậm trễ theo mốc đã thỏa thuận** khi biết sự cố bảo mật liên quan đến dịch vụ hoặc dữ liệu trong phạm vi; cung cấp thông tin ban đầu đã biết, cập nhật diễn biến và phối hợp điều tra, hạn chế tác động, đáp ứng các nghĩa vụ thông báo mà tổ chức phải thực hiện.

Khi triển khai thật, Legal và các bên cần thay lời mô tả bằng **định nghĩa sự cố, điều kiện kích hoạt, mốc thời gian, trách nhiệm, ngoại lệ và cơ chế thực thi cụ thể**. Không dùng một đoạn mô tả chung làm hợp đồng chính thức.

## 10. Shared responsibility: phân định ai phải thực hiện control

Một nguyên nhân thường gặp của rủi ro bên thứ ba là tổ chức nghĩ nhà cung cấp “đã lo bảo mật” nên bỏ qua phần control của chính mình.

### 10.1. Ví dụ theo loại dịch vụ

| Mô hình | Nhà cung cấp thường đảm nhiệm | Bên sử dụng thường vẫn đảm nhiệm |
|---|---|---|
| **IaaS** | Hạ tầng vật lý/nền tảng cloud theo dịch vụ và hợp đồng | Cấu hình VM/network/IAM, phần mềm khách hàng, dữ liệu và quản lý secret |
| **PaaS/managed DB** | Một phần vận hành nền tảng hoặc engine theo cam kết | Quyền kết nối, cấu hình dịch vụ cho phép, dữ liệu, truy cập của ứng dụng và policy bảo vệ |
| **SaaS** | Phần lớn vận hành ứng dụng/nền tảng SaaS | Tenant configuration, cấp/thu hồi user, chia sẻ dữ liệu, quyền tổ chức và cách tích hợp |
| **External API** | Endpoint/dịch vụ API và hạ tầng phía nhà cung cấp | API key/OAuth scope, request data, validation, quota, xử lý lỗi, kiểm soát dữ liệu |
| **Outsourced operations** | Công việc được giao và control nội bộ bên cung cấp | Phê duyệt quyền, giám sát công việc, kiểm tra kết quả, phân quyền giữa hai tổ chức |

Bảng là cách mô tả thường gặp; **ranh giới thật phụ thuộc hợp đồng, kiến trúc và cấu hình**. Có nhà cung cấp quản lý cả thành phần mà ví dụ mặc định do khách hàng vận hành, hoặc ngược lại. Cần tạo shared responsibility matrix cho dịch vụ cụ thể.

### 10.2. Những khoảng trống trách nhiệm dễ bỏ sót

- Nhà cung cấp bảo vệ cloud platform; tổ chức tự cấp token API quá rộng.
- Nhà cung cấp vận hành logging; tổ chức không bật audit event hoặc không kiểm tra log ingest.
- Nhà cung cấp có backup; tổ chức chưa biết backup có bao phủ tập dữ liệu mình cần khôi phục không.
- Nhà cung cấp có chức năng SSO/MFA; tổ chức không bật hoặc bỏ sót tài khoản đặc biệt.
- Nhà cung cấp bảo vệ dữ liệu khi lưu; tổ chức gửi dữ liệu không cần thiết qua integration.
- Nhà cung cấp hỗ trợ xóa dữ liệu; tổ chức không yêu cầu hoặc không kiểm chứng xóa khi kết thúc.

Một review tốt phải đánh giá **đường tiếp giáp** giữa control của hai bên, không chỉ đối chiếu một bộ tài liệu của nhà cung cấp.

## 11. Bảo vệ tích hợp kỹ thuật và quyền truy cập nhà cung cấp

### 11.1. API keys, OAuth và tài khoản dịch vụ

Khi tích hợp hệ thống Java hoặc cloud service với vendor API:

- Xác định **chủ sở hữu credential** và mục đích sử dụng rõ ràng.
- Chỉ cấp **scope/quyền cần thiết** cho luồng công việc thực tế.
- Lưu secret bằng cơ chế phù hợp, tránh ghi vào source code, log hoặc ticket.
- Thiết lập vòng đời **cấp, giám sát, rotation/revocation** theo rủi ro và khả năng nền tảng.
- Phân tách credential cho môi trường thử nghiệm và production khi phù hợp.
- Kiểm soát cách xác thực webhook/callback và nội dung thông điệp, chống xử lý lặp khi nghiệp vụ yêu cầu.
- Giới hạn truy cập mạng, số request/quota hoặc khối lượng dữ liệu khi có cơ sở về rủi ro.
- Có cách **ngắt tích hợp** khi lộ khóa, phát hiện lạm dụng hoặc kết thúc hợp đồng.
- Giám sát hành vi vượt phạm vi hợp lệ nhưng không đưa credential hay dữ liệu nhạy cảm vào log.

Không nên lấy việc “vendor API dùng HTTPS” làm bằng chứng đủ cho authorization, data minimization hoặc vòng đời token.

### 11.2. Quyền nhân sự hỗ trợ bên ngoài

Với người của nhà cung cấp cần hỗ trợ hệ thống:

1. Yêu cầu tài khoản **định danh riêng** và nguồn phê duyệt.
2. Giới hạn quyền, thời gian và tài sản có thể truy cập; dùng truy cập khẩn cấp khi có quy trình.
3. Xác thực theo baseline phù hợp và ghi nhận các thao tác nhạy cảm.
4. Tránh dùng chung admin account hoặc token không xác định chủ sở hữu.
5. Kiểm tra quyền khi nhân sự nhà cung cấp thay đổi, hết nhiệm vụ, kết thúc hợp đồng.
6. Thu hồi session, token, VPN, certificate và quyền dữ liệu liên quan khi không còn nhu cầu.
7. Có khả năng kiểm tra lịch sử thay đổi và liên hệ đầu mối khi phát hiện bất thường.

Điểm cần chứng minh không chỉ là “có danh sách tài khoản”, mà còn là **ai được phê duyệt, có quyền gì, trong kỳ nào, có đúng mục đích và đã thu hồi khi cần chưa**.

### 11.3. Dữ liệu và trách nhiệm về quyền riêng tư

Dữ liệu học viên được chuyển sang SaaS có thể được lưu trong bản sao, log, bộ nhớ tạm, analytics pipeline và backup theo kiến trúc dịch vụ. Trước khi tích hợp cần:

- Xác định **dữ liệu tối thiểu cần chia sẻ** và mục đích xử lý.
- Xác định bên quyết định mục đích/phương thức và bên xử lý theo **khung pháp lý áp dụng**; không đoán vai trò chỉ từ tên trong hợp đồng.
- Xem xét nơi xử lý/lưu dữ liệu và cách cung cấp cho subprocessor.
- Thiết lập quy tắc retention, deletion, export và bảo vệ trong truyền/lưu.
- Xác định quyền truy cập của nhân viên vendor và log/audit phù hợp.
- Kiểm tra thủ tục xử lý yêu cầu của chủ thể dữ liệu và phối hợp thông báo sự cố khi áp dụng.
- Phối hợp Legal/Privacy/DPO nếu được chỉ định hoặc theo yêu cầu.

**Cùng một vendor** có thể đóng các vai trò khác nhau đối với những luồng dữ liệu khác nhau. Scope đánh giá phải gắn với hoạt động xử lý thực tế.

## 12. Supplier assurance: từ lời khẳng định đến bằng chứng

Trong security assurance, một nhà cung cấp có thể nói “chúng tôi bảo vệ dữ liệu bằng mã hóa và kiểm soát quyền”. Để đưa vào quyết định, cần tách **claim**, **argument** và **evidence**.

### 12.1. Mô hình Claim–Argument–Evidence

- **Claim:** “Trong phạm vi dịch vụ phân tích học tập được ký hợp đồng, tài khoản vendor không có quyền đọc dữ liệu ngoài những tập dữ liệu được phê duyệt.”
- **Argument:** Kiến trúc tách tenant, IAM role và data access policy hạn chế scope; các thay đổi quyền được quản lý và kiểm tra; test/monitoring xác nhận hành vi đúng.
- **Evidence:** Sơ đồ data flow có phiên bản, role/policy export, negative authorization tests, bằng chứng access review, log và report đánh giá độc lập trong phạm vi liên quan.

Một claim **không nên rộng hơn bằng chứng**: nếu báo cáo SOC chỉ bao phủ dịch vụ lưu trữ của vendor, không thể dùng nó để kết luận ứng dụng phân tích học tập hoặc tích hợp bên mua được bảo vệ đầy đủ.

### 12.2. Đánh giá ba lớp hiệu quả control

| Lớp | Câu hỏi | Evidence ví dụ |
|---|---|---|
| **Design effectiveness** | Control được thiết kế có xử lý đúng kịch bản rủi ro không? | Sơ đồ kiến trúc, control description, threat model, tiêu chí review |
| **Implementation effectiveness** | Control đã triển khai đúng cho dịch vụ, tenant và đường tích hợp đang dùng chưa? | Cấu hình, role và scope runtime, kết quả thử truy cập |
| **Operating effectiveness** | Control hoạt động ổn định trong kỳ, kể cả khi thay đổi và phát sinh sự kiện? | Access review định kỳ, lịch sử thay đổi, log, audit/test report và retest |

Ví dụ ảnh chụp giao diện bật MFA có thể hỗ trợ kiểm tra cấu hình tại một thời điểm. Nó chưa tự chứng minh tất cả tài khoản đặc quyền của vendor, bao gồm emergency và support, đã được bảo vệ trong cả kỳ.

### 12.3. Chất lượng bằng chứng

Cần xác minh tối thiểu sáu thuộc tính:

1. **Liên quan (relevance):** evidence chứng minh đúng requirement và claim nào?
2. **Đúng phạm vi (scope):** dịch vụ, tenant, môi trường, nhân sự, subservice nào thuộc đánh giá?
3. **Đúng thời điểm/kỳ (freshness/period):** evidence đã cũ, có thay đổi quan trọng sau đó không?
4. **Nguồn gốc và toàn vẹn (provenance/integrity):** ai tạo, ngày nào, có thể đối chiếu nguồn gốc không?
5. **Đủ bao phủ (completeness/representativeness):** lấy toàn bộ hay mẫu, ngoại lệ có được công bố?
6. **Có thể kiểm tra lại (repeatability):** người được phép có thể kiểm tra bằng nguồn hoặc phép thử tương đương không?

Nếu chỉ có bản tự khai “Yes” mà không có bằng chứng hoặc cơ sở kiểm chứng thích hợp, cần ghi nhận **evidence gap**. Không phải lúc nào phải kết luận “vendor không bảo mật”; kết luận phù hợp có thể là **chưa đủ bằng chứng để đạt mức assurance cần thiết cho tier này**.

### 12.4. Chuỗi truy vết của supplier assurance

~~~mermaid
flowchart TD
    A["Dịch vụ vendor, dữ liệu và mục tiêu"] --> B["Risk scenario và phân tầng"]
    B --> C["Policy requirement / contract control"]
    C --> D["Phân chia control owner hai phía"]
    D --> E["Thiết kế, triển khai, vận hành"]
    E --> F["Evidence, test và assessment"]
    F --> G{"Đạt tiêu chí, bằng chứng đủ?"}
    G -->|"Có"| H["Assurance claim có phạm vi và giới hạn"]
    G -->|"Không"| I["Finding / action / ngoại lệ"]
    I --> E
    H --> J["Residual risk và quyết định có thẩm quyền"]
    J --> K["Monitoring / change / reassessment"]
    K --> B
~~~

## 13. Chính sách giám sát nhà cung cấp đang hoạt động

### 13.1. Không dừng ở lần phê duyệt đầu tiên

Rủi ro thay đổi khi nhà cung cấp:

- Mở tính năng mới hoặc thay mô hình triển khai/dữ liệu.
- Đổi subprocessor, trung tâm dữ liệu, vùng xử lý hoặc nhà cung cấp hạ tầng.
- Bị sự cố bảo mật, ngừng dịch vụ hoặc công bố lỗ hổng liên quan.
- Thay chính sách cấp quyền, cơ chế SSO, API, quyền hỗ trợ hoặc phạm vi log.
- Mở rộng lượng dữ liệu hoặc quyền mà bên mua chuyển sang.
- Hết hạn chứng nhận/báo cáo hoặc xuất hiện finding audit chưa xử lý.
- Có thay đổi hợp đồng, nghĩa vụ pháp lý, giá và điều kiện exit ảnh hưởng rủi ro.

**Continuous supplier assurance** là lựa chọn nhịp đánh giá dựa trên rủi ro và thay đổi; không có nghĩa liên tục đòi mọi vendor gửi một bộ tài liệu đầy đủ mỗi ngày.

### 13.2. Kế hoạch giám sát theo rủi ro

| Tín hiệu | Phương pháp kiểm tra | Hành động khi không đạt |
|---|---|---|
| Hợp đồng, phê duyệt và yêu cầu đang còn hiệu lực | Inventory, contract/renewal tracking | Rà soát và điều chỉnh điều khoản hoặc phạm vi |
| Báo cáo assurance mới và finding chưa đóng | Review report, exception, corrective action | Cập nhật residual risk và remediation |
| Thay đổi quyền tích hợp/credential | Diff IAM, OAuth app, service account review | Thu hồi quyền dư, rotate token, test lại |
| Drift tại tenant cấu hình của bên mua | Kiểm tra config qua API/portal, policy test | Sửa config và xác minh đã khôi phục |
| Độ ổn định và phục hồi | Theo dõi SLA, incident và DR/restore evidence | Mở risk/BCP action, kiểm tra phụ thuộc |
| Sự cố nhà cung cấp | Security advisory, notification, incident triage | Đánh giá dữ liệu/đường tác động, cô lập theo runbook |
| Subprocessor và data location | Đối chiếu thông báo/danh sách và data flow | Privacy/security review, thay điều kiện nếu cần |
| Tái đánh giá tier và concentration risk | Đánh giá hệ thống phụ thuộc và khả năng thay thế | Điều chỉnh mức ưu tiên, exit/continuity plan |

Tần suất cụ thể (mỗi release, hằng tháng/quý/năm hoặc khi có sự kiện) phải do chính sách xác định theo **risk tier, loại control, độ biến động và nghĩa vụ áp dụng**. Không tự giả định có một tần suất do mọi framework bắt buộc.

### 13.3. Kiểm chứng nghĩa vụ thông báo sự cố

Một hợp đồng quy định nhà cung cấp thông báo sự cố trong một thời hạn có thể kiểm chứng bằng:

- Có đầu mối nhận thông tin, kênh liên hệ và người dự phòng ở cả hai bên.
- Đã thử/diễn tập đường liên lạc ở mức phù hợp.
- Với sự cố thực tế, có timeline: nhà cung cấp biết từ khi nào, thông báo khi nào, thông tin cập nhật khi nào.
- Đã phối hợp xác định dữ liệu/hệ thống bị ảnh hưởng, giới hạn bằng chứng và bước khắc phục.
- Có issue khi không đạt và cơ chế sửa quy trình.

Một điều khoản được ký là bằng chứng **cam kết**, không tự chứng minh **khả năng thực thi** lúc xảy ra sự cố.

## 14. Quản lý finding, ngoại lệ và residual risk

### 14.1. Kết quả đánh giá nên phân loại rõ

Một bộ trạng thái nội bộ minh họa:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| **Đạt** | Control đáp ứng tiêu chí trong scope/kỳ và evidence đủ | Tiếp tục monitoring và đánh giá lại |
| **Không đạt** | Có sai lệch được chứng minh | Ghi finding, đánh giá impact, remediation và retest |
| **Chưa đủ bằng chứng** | Không thể kết luận do thiếu dữ liệu/độ phủ/kiểm thử | Yêu cầu evidence bổ sung, giới hạn claim hoặc risk decision |
| **Không áp dụng** | Requirement không liên quan trong scope có căn cứ | Ghi lý do, review khi có thay đổi |
| **Ngoại lệ có điều kiện** | Sai lệch nội bộ được cho phép trong phạm vi và thời hạn cụ thể | Theo dõi control bù trừ, hạn, trigger; không biến fail thành pass |

Trạng thái khi báo cáo audit hoặc chứng nhận phải tuân theo quy tắc của chương trình đánh giá đó; các nhãn trên chỉ là ví dụ quản trị nội bộ.

### 14.2. Xử lý sai lệch

Khi phát hiện vendor thiếu control quan trọng:

1. **Ghi finding:** requirement ID, phạm vi, điều kiện quan sát, bằng chứng, tác động và kỳ đánh giá.
2. **Đánh giá rủi ro:** dịch vụ/tài sản nào chịu ảnh hưởng, có dữ liệu nhạy cảm hay production access?
3. **Giao owner:** business/vendor owner, control owner phía nhà cung cấp/bên mua, deadline và người review.
4. **Chọn phương án:** khắc phục, giảm phạm vi quyền/dữ liệu, tạm dừng tích hợp, thay nhà cung cấp hoặc xin ngoại lệ theo quy định.
5. **Kiểm chứng control bù trừ:** có tác động thực sự tới risk path không, đã triển khai/test chưa?
6. **Retest:** kiểm tra nguyên nhân và trạng thái sau sửa; chỉ đóng khi đủ điều kiện.
7. **Cập nhật supplier record và residual risk:** để lãnh đạo nhìn thấy rủi ro tồn đọng.

### 14.3. Chấp nhận rủi ro phải đúng thẩm quyền

CISO/Security có thể tư vấn và phản biện, Procurement quản lý hợp đồng, Engineering kiểm soát tích hợp; **risk owner/cấp được ủy quyền** quyết định chấp nhận rủi ro còn lại trong giới hạn. Một nhà cung cấp có chứng nhận không tự miễn mọi phát hiện. Một risk acceptance nội bộ **không xóa nghĩa vụ pháp luật hoặc điều khoản bắt buộc**.

Hồ sơ chấp nhận cần có scope, risk scenario, likelihood/impact hoặc phương pháp tương ứng, evidence, giả định, điều kiện, control bù trừ, người duyệt, thời hạn/chu kỳ review, trigger và kế hoạch giảm rủi ro nếu tạm thời.

Ví dụ, tổ chức đồng ý dùng dịch vụ email chưa hỗ trợ SSO cho người quản trị trong giai đoạn ngắn. Nếu chính sách cho phép ngoại lệ và nghĩa vụ liên quan không cấm, có thể xem xét biện pháp hạn chế quyền, xác thực mạnh theo khả năng dịch vụ, giám sát, quy trình cấp/thu hồi và kế hoạch chuyển đổi. Phải **chứng minh hiệu quả control**, không mặc định có một biện pháp bù trừ luôn tương đương SSO/MFA.

## 15. Quy trình onboarding và quyết định go/no-go

Một quy trình tổng quát có thể thiết kế như sau:

~~~mermaid
flowchart TD
    A["Nhu cầu sử dụng vendor"] --> B["Đăng ký inventory, owner, data flow"]
    B --> C["Phân loại inherent risk và yêu cầu"]
    C --> D["Due diligence, contract và shared responsibility"]
    D --> E["Security assessment và evidence review"]
    E --> F{"Đáp ứng điều kiện dùng?"}
    F -->|"Có"| G["Phê duyệt scope và tích hợp"]
    F -->|"Không / thiếu dữ liệu"| H["Finding, action, giảm phạm vi hoặc lựa chọn khác"]
    H --> E
    G --> I["Kiểm tra cấu hình, quyền và test sau onboarding"]
    I --> J["Monitoring, thay đổi, audit, reassessment"]
    J --> K["Renewal hoặc offboarding"]
~~~

### Những điều kiện nên được kiểm tra trước khi mở quyền

- Business owner xác nhận **mục đích sử dụng và loại dữ liệu**.
- Vendor đã có inventory và được xếp tier phù hợp.
- Legal/Privacy xác định **nghĩa vụ và thỏa thuận** cần thiết khi liên quan.
- Security review và thẩm định đã xác định finding, evidence gap, control của hai bên.
- Có **quyết định sử dụng/ngoại lệ** đúng thẩm quyền.
- Engineering/IT chỉ cấp quyền, khóa, mạng và dữ liệu **đúng scope được duyệt**.
- Có test tích hợp để kiểm tra deny ngoài quyền, log, tình huống lỗi và hành động thu hồi.
- Có quy trình incident contact, giám sát và các **trigger đánh giá lại**.
- Với nhà cung cấp trọng yếu, có kế hoạch liên tục/exit phù hợp tác động.

Tổ chức nên kiểm tra lại **trạng thái production thực tế** sau tích hợp. Việc hợp đồng có quy định least privilege không chứng minh secret production đã được tạo đúng quyền.

## 16. Ví dụ xuyên suốt: nhà cung cấp phân tích học tập

### 16.1. Bối cảnh

Một nền tảng học trực tuyến vận hành backend Java, database và API. Nhóm Product muốn dùng dịch vụ SaaS bên ngoài để thống kê tiến độ học tập và đề xuất nội dung. SaaS cần dữ liệu sự kiện: học viên nào đã tham gia khóa nào, điểm tổng hợp và thời điểm truy cập. Nhà cung cấp đề xuất tích hợp bằng API token có quyền đọc báo cáo dữ liệu và tự động tải dữ liệu hằng ngày.

**Use case hợp lệ:** thu thập dữ liệu đã được phê duyệt để tạo dashboard cải thiện chất lượng học tập.

**Risk scenario:** token tích hợp hoặc cấu hình export bị lạm dụng, nhà cung cấp nhận cả hồ sơ học viên ngoài mục đích; dữ liệu được lưu quá lâu hoặc chia sẻ với subprocessor mà đội Product chưa biết.

### 16.2. Phân loại và due diligence

| Khía cạnh | Câu hỏi | Phân tích ban đầu |
|---|---|---|
| Tài sản | Dữ liệu học viên, điểm và thông tin hoạt động có nhạy cảm không? | Cần phân loại theo dữ liệu thật, tránh giả định là dữ liệu công khai |
| Scope | SaaS cần trường nào và khối lượng bao nhiêu? | Giới hạn trường, thời gian, khóa học, quyền truy vấn |
| Access | Có cần quyền đọc trực tiếp database hoặc admin không? | Ưu tiên API/dataset scope tối thiểu thay quyền rộng |
| Data flow | SaaS xử lý, lưu, sao chép và gửi subprocessor ở đâu? | Cần data map, retention và thỏa thuận thích hợp |
| Security controls | Nhà cung cấp cô lập tenant, bảo vệ IAM, log và ứng phó ra sao? | Yêu cầu evidence có scope, xem finding/ngoại lệ |
| Availability | Mất SaaS có làm ngừng học tập hay chỉ mất dashboard? | Phân biệt criticality của tính năng chính/phụ |
| Exit | Có thể thu hồi token, ngừng export, xóa dữ liệu hoặc chuyển dịch vụ? | Cần kiểm tra quy trình và điều khoản phù hợp |

Không thể kết luận một nhà cung cấp “High” hay “Moderate” chỉ từ tên dịch vụ. Kết quả phụ thuộc dữ liệu, quyền, mục đích, kiến trúc và ngưỡng phân loại của tổ chức.

### 16.3. Mapping mục tiêu sang yêu cầu và bằng chứng

| Mục tiêu/rủi ro | Requirement | Owner | Verification/evidence |
|---|---|---|---|
| Không chuyển dữ liệu ngoài mục đích | API export chỉ chứa trường và tập học viên được phê duyệt | Data/Backend owner | Data mapping, payload sample đã che nhạy cảm, test phạm vi |
| Không cấp quyền quá rộng | Token chỉ có scope đọc dataset phù hợp, có vòng đời quản lý | IAM/Platform | Policy export, negative test, rotation/revocation test |
| Không dùng dữ liệu quá thời hạn | Retention/deletion theo thỏa thuận áp dụng | Vendor + Privacy owner | Điều khoản, quy trình xóa, evidence review |
| Có thể phát hiện trích xuất bất thường | Log và cảnh báo theo mức rủi ro/khối lượng | Platform/SecOps | Synthetic event, log sample, alert/ticket |
| Có thể ứng phó khi vendor bị sự cố | Liên hệ, kênh thông báo, cách tắt tích hợp và phối hợp điều tra | Vendor owner + Security | Runbook, kiểm tra liên hệ, revoke/disable drill |
| Khi hết hợp tác không còn truy cập | Thu hồi token, dừng job, xuất/xóa dữ liệu theo nghĩa vụ | IT/Backend + Vendor | Deprovisioning test, data return/deletion confirmation |

### 16.4. Ví dụ security invariant và phép thử

**Invariant 1:** SaaS chỉ nhận các trường dữ liệu đã được phê duyệt, không nhận địa chỉ nhà riêng hoặc dữ liệu tài khoản khi mục tiêu chỉ cần thống kê tổng hợp.

**Test:** sinh bộ dữ liệu kiểm thử có cả trường được phép và không được phép; xác nhận payload gửi vendor chỉ chứa đúng danh sách trường và scope, không dựa duy nhất vào việc UI không hiển thị trường nhạy cảm.

**Invariant 2:** Token của SaaS không thể đọc endpoint không nằm trong quyền đã cấp.

**Test:** gọi các endpoint ngoài scope trong môi trường kiểm soát; xác minh kết quả từ chối và không có side effect. Đối chiếu scope/token thực tế của bản production với hồ sơ đã phê duyệt.

**Invariant 3:** Khi thu hồi quan hệ hoặc khóa tích hợp, không còn job gửi dữ liệu sang vendor.

**Test:** thực hiện quy trình revoke trong môi trường tương đương, kiểm tra request mới bị từ chối, job queue bị dừng/loại bỏ thích hợp và audit record được tạo. Khi thực hiện trên production cần bảo đảm không gây gián đoạn ngoài phạm vi.

### 16.5. Tình huống thay đổi làm kết luận cũ không còn đủ

Ba tháng sau, dịch vụ SaaS giới thiệu tính năng dự đoán điểm bằng mô hình học máy và đề xuất thu thập bài nộp dạng tự do thay vì chỉ điểm tổng hợp. Đây là **thay đổi loại dữ liệu, mục đích xử lý và bề mặt rủi ro**. Phê duyệt ban đầu không tự áp dụng cho phạm vi mới. Cần xác định yêu cầu privacy/hợp đồng, cập nhật data flow, đánh giá lại control và quyết định trước khi mở luồng dữ liệu mới.

Đồng thời, nếu nhà cung cấp đổi subprocessor có quyền xử lý dữ liệu, cơ chế thông báo và review trong hợp đồng cần được kích hoạt theo điều kiện đã thỏa thuận.

## 17. Mẫu hồ sơ supplier assurance

Ví dụ YAML sau dành cho chương trình quản trị **nội bộ**; ID, kỳ và kết quả đều là giả định, không khẳng định một nhà cung cấp thực tế đã được đánh giá.

~~~yaml
supplier_id: VND-LEARN-ANALYTICS-01
service: "Learning Analytics SaaS"
business_owner: "Learning Product"
risk_owner: "Owner dịch vụ học tập theo phân quyền"
scope:
  environment: "production"
  data: ["course-id", "learner-pseudonymous-id", "progress-summary"]
  excluded: ["raw-assignment-content", "payment-card-data"]
  integration: "Outbound API export"
inherent_tier: "High - minh họa"
risk_scenarios:
  - id: R-VND-01
    description: "Token có thể truy xuất dữ liệu ngoài mục đích"
  - id: R-VND-02
    description: "Vendor có thể giữ hoặc chia sẻ dữ liệu ngoài kỳ được phê duyệt"
security_requirements:
  - id: REQ-VND-01
    claim: "Token chỉ có quyền đọc dataset đã duyệt"
    control_owner: "Platform IAM"
    evidence: ["IAM policy snapshot", "Negative access test"]
  - id: REQ-VND-02
    claim: "Dữ liệu xuất nằm trong danh sách trường đã duyệt"
    control_owner: "Backend/Data"
    evidence: ["Export schema", "Data mapping", "Payload test"]
  - id: REQ-VND-03
    claim: "Retention và deletion được kiểm soát theo thỏa thuận"
    control_owner: "Vendor + Privacy owner"
    evidence: ["Contract terms", "Deletion process assessment"]
assessment:
  period: "Kỳ đánh giá nội bộ minh họa"
  status: "Chưa được kết luận nếu evidence chưa được kiểm tra"
  evidence_gaps: ["Cần xác minh control vận hành ở vendor"]
  limitations: ["Không bao gồm dữ liệu hoặc tính năng mới"]
approval:
  authority: "Risk owner được ủy quyền"
  decision: "Chỉ đưa ra sau assessment"
monitoring:
  triggers:
    - "Thay dữ liệu, OAuth scope, subprocessor hoặc API export"
    - "Vendor incident hoặc finding trọng yếu"
    - "Thay chức năng phân tích, lưu trữ hoặc retention"
exit_controls:
  - "Thu hồi credential"
  - "Dừng lịch xuất dữ liệu"
  - "Đối chiếu dữ liệu trả/xóa theo điều khoản áp dụng"
~~~

**Đừng sao chép kết quả “High” hoặc “Đạt” từ mẫu vào record thật.** Việc phân loại và quyết định cần dựa trên dữ liệu, bằng chứng và thẩm quyền của tổ chức.

## 18. Chấm dứt quan hệ và exit assurance

Kết thúc hợp đồng không đồng nghĩa rủi ro đã biến mất. Đôi khi vendor vẫn giữ dữ liệu trong backup, tài khoản support vẫn truy cập được hoặc job tích hợp vẫn gửi dữ liệu.

### 18.1. Checklist offboarding

1. **Xác định phạm vi kết thúc:** dịch vụ, môi trường, tài khoản, tích hợp, dữ liệu và subprocessor.
2. **Lập kế hoạch chuyển đổi:** owner, thời hạn, thứ tự chuyển dữ liệu, khả năng khôi phục, tác động đến người dùng.
3. **Xuất/đối chiếu dữ liệu cần giữ:** cấu trúc, toàn vẹn, tính đầy đủ, quyền truy cập và khả năng sử dụng sau di chuyển.
4. **Dừng luồng dữ liệu:** webhooks, scheduled jobs, event subscriptions, ETL, API exports và chia sẻ file.
5. **Thu hồi quyền:** SSO app, OAuth grants, API keys, VPN, service accounts, certificates, support roles và session liên quan.
6. **Yêu cầu trả/xóa dữ liệu theo nghĩa vụ:** xác định thời hạn, dữ liệu backup, ngoại lệ lưu trữ, subprocessor và khả năng xác nhận.
7. **Kiểm tra evidence:** danh sách quyền bị thu hồi, log thay đổi, xác nhận xử lý dữ liệu, kết quả test không thể truy cập.
8. **Kết thúc risk/finding phù hợp:** đóng hoặc chuyển owner những rủi ro còn lại; lưu hồ sơ theo chính sách lưu trữ.
9. **Cập nhật inventory và dependency maps:** tránh tiếp tục phụ thuộc hoặc tự động mua/gia hạn khi đã chấm dứt.

### 18.2. Giới hạn bằng chứng xóa dữ liệu

Một email của vendor xác nhận “đã xóa dữ liệu” có thể là bằng chứng về **tuyên bố và trách nhiệm hợp đồng**, nhưng không tự chứng minh mọi bản sao, backup và subprocessor đều đã xóa. Cần đánh giá theo rủi ro và điều khoản: khả năng cung cấp log/xác nhận quy trình, thời hạn xóa backup, kiểm toán độc lập hoặc evidence thay thế. Những bản sao phải giữ do nghĩa vụ hợp pháp cần được ghi rõ phạm vi, quyền truy cập, thời hạn và cách bảo vệ.

## 19. Đo lường chất lượng chương trình supplier security

| Chỉ số | Ý nghĩa quản trị | Hạn chế cần nhớ |
|---|---|---|
| Tỷ lệ vendor có owner, scope, tier và ngày review | Độ đầy đủ inventory và trách nhiệm | Inventory thiếu shadow IT làm tỷ lệ gây hiểu lầm |
| Tỷ lệ vendor critical/high được đánh giá trong kỳ | Độ phủ chương trình assurance | Assessment có thể chỉ dựa trên self-attestation |
| Tỷ lệ requirement có evidence hợp lệ | Độ tin cậy của kiểm tra | Evidence cũ/sai scope vẫn phải loại khỏi kết luận |
| Số finding trọng yếu quá hạn theo supplier | Nợ remediation và rủi ro tồn đọng | Đóng ticket khi chưa retest làm méo số |
| Số exception hết hạn/gia hạn nhiều lần | Dấu hiệu rủi ro được giữ quá lâu | Cần xem tác động, không chỉ số lượng |
| Tỷ lệ quyền vendor được rà soát/thu hồi đúng hạn | Hiệu quả access lifecycle | Có checklist không chứng minh quyền runtime đã bị gỡ |
| Thời gian từ supplier incident đến triage của bên mua | Năng lực phối hợp ứng phó | Chỉ đo sự cố được phát hiện/thông báo |
| Tỷ lệ exit có bằng chứng revoke và xử lý dữ liệu | Hiệu quả kết thúc hợp tác | Vendor declaration có thể cần kiểm chứng bổ sung |
| Tập trung rủi ro ở một nhà cung cấp | Mức phụ thuộc và khả năng gián đoạn chung | Cần xem substitutability, DR và các phụ thuộc ẩn |

Không nên báo cáo “100% vendor có chứng nhận” như một chỉ số thay thế cho an toàn. Chất lượng chương trình thể hiện ở **quản trị rủi ro thực, khả năng phát hiện/control, bằng chứng, quyết định và xử lý đúng hạn**.

## 20. Những sai lầm thường gặp

**“Đã ký NDA là đã giải quyết mọi rủi ro vendor.”** NDA chỉ giải quyết một phần nghĩa vụ bảo mật thông tin; chưa tự xác định quyền truy cập, kỹ thuật bảo vệ, xử lý sự cố, phục hồi hoặc xóa dữ liệu.

**“Nhà cung cấp có ISO 27001 hoặc SOC 2 nên không cần đánh giá.”** Báo cáo/chứng nhận có phạm vi, kỳ, tiêu chí, ngoại lệ và trách nhiệm phía khách hàng. Cần đọc đúng điều được chứng minh.

**“Nhà cung cấp lớn thì không có rủi ro.”** Quy mô không thay thế đánh giá data flow, incident history, shared responsibility, concentration và lock-in.

**“Vấn đề xảy ra ở bên thứ ba nên doanh nghiệp không chịu ảnh hưởng.”** Chủ sở hữu hệ thống/dữ liệu vẫn có thể chịu tác động về vận hành, khách hàng, hợp đồng và nghĩa vụ pháp lý theo phạm vi áp dụng.

**“Vendor đã ký cam kết báo sự cố nên sẽ luôn thông báo đúng.”** Cam kết là tiêu chí; phải có cơ chế liên hệ, thử quy trình và review dữ liệu thực tế khi phát sinh sự cố.

**“Nhà cung cấp chịu trách nhiệm hết về bảo mật SaaS.”** Cấu hình tenant, cấp user, API token, phạm vi dữ liệu và quyền tích hợp thường vẫn là trách nhiệm phía sử dụng theo hợp đồng/thực tế.

**“Checklist trả lời Yes là bằng chứng control hiệu quả.”** Self-attestation có giá trị thông tin nhưng mức tin cậy thường khác với test thực tế hoặc báo cáo kiểm toán phù hợp.

**“Lúc ký hợp đồng đã đánh giá, các năm sau không cần làm lại.”** Dữ liệu, quyền, subprocessor, threat và dịch vụ thay đổi; phải có trigger và kỳ review theo rủi ro.

**“Rủi ro có thể chấp nhận thì không cần ghi finding.”** Ngoại lệ/acceptance không tự biến test fail thành pass, không xóa lịch sử sai lệch hoặc nghĩa vụ bắt buộc.

**“Chấm dứt hợp đồng nghĩa là không còn dữ liệu và quyền.”** Phải kiểm tra token, job, backup, subprocessor, lưu trữ và evidence xử lý dữ liệu theo phạm vi.

**“Mọi vendor phải đi qua cùng một bảng hỏi 300 câu.”** Thủ tục giống nhau không bảo đảm đúng mức độ rủi ro; nên chọn độ sâu kiểm tra dựa trên tác động và quyền/dữ liệu.

## 21. Bài tập áp dụng

### Bài tập A — Phân loại ba nhà cung cấp

Một nền tảng học trực tuyến đang xem xét:

- **Vendor A:** nền tảng xác thực cho toàn bộ học viên và nhân sự, lưu thông tin định danh và quyền đăng nhập.
- **Vendor B:** dịch vụ gửi email, nhận địa chỉ email và mẫu nội dung giao dịch; token hiện tại có thể gửi không giới hạn.
- **Vendor C:** công cụ tạo biểu đồ trong môi trường thử nghiệm, không nhận dữ liệu thật theo thiết kế ban đầu.

Hãy đánh giá sơ bộ **inherent risk tier** theo phương pháp nội bộ tự nêu. Với mỗi vendor ghi:

1. Tài sản, mục tiêu và loại dữ liệu bị ảnh hưởng.
2. Tác động khi bị chiếm quyền, lộ dữ liệu hoặc ngừng dịch vụ.
3. Đường truy cập, quyền và phụ thuộc cần xác minh.
4. Due diligence và evidence tối thiểu.
5. Owner, điều kiện onboarding và trigger review.
6. Một cách giảm tác động hoặc exit phù hợp.

**Gợi ý:** Vendor A thường có ảnh hưởng rộng và cần kiểm tra continuity, identity, backup/phương án thay thế. Vendor B cần đánh giá token, quota, data handling và detection; chi phí hợp đồng thấp không đồng nghĩa rủi ro thấp. Vendor C chỉ được xếp nhẹ nếu xác minh đúng rằng không có dữ liệu thật, production integration hoặc quyền nhạy cảm.

### Bài tập B — Đọc đúng báo cáo assurance

Một vendor gửi chứng nhận ISO/IEC 27001 và báo cáo SOC 2 Type II. Procurement muốn ký ngay, nhưng nhóm kỹ thuật dự kiến cấp token đọc toàn bộ dữ liệu học viên cho một API export mới.

Hãy trả lời:

- Hai tài liệu nói trên cần kiểm tra **scope, kỳ, tiêu chí, ngoại lệ** nào?
- Có bằng chứng nào chứng minh token của **tổ chức** sẽ chỉ có quyền cần thiết không?
- Security invariant và negative tests nào cần thiết cho API export?
- Business owner và risk owner cần quyết định điều gì trước khi mở production?
- Nếu báo cáo không bao gồm dịch vụ API mới, kết luận assurance phải viết thế nào?

**Định hướng:** Báo cáo vendor không chứng minh tự động cấu hình tenant, quyền API và data minimization phía khách hàng. Cần assessment đường tích hợp riêng và nêu evidence gap.

### Bài tập C — Điều tra một finding nhà cung cấp

Sau khi triển khai dịch vụ phân tích học tập, nhóm SOC thấy một API token của vendor gọi endpoint ngoài scope. Vendor nói “không có sự cố”, nhưng chưa cung cấp log chi tiết.

Hãy lập hồ sơ:

1. Finding, scope và bằng chứng quan sát được.
2. Kịch bản risk và impact có thể xảy ra.
3. Hành động tức thời theo quyền hạn: giới hạn token, điều tra, bảo vệ log.
4. Thông tin và bằng chứng cần yêu cầu vendor.
5. Trách nhiệm Engineering, Security, Privacy/Legal, business/risk owner.
6. Điều kiện khôi phục tích hợp và các phép retest.
7. Cách cập nhật residual risk, contract record và trigger tái đánh giá.

**Gợi ý:** Chưa đủ thông tin để khẳng định đã lộ dữ liệu; cũng không đủ để mặc định không có incident. Cần kiểm tra response, data scope, log coverage và điều kiện sử dụng token, rồi báo cáo với mức độ bất định rõ ràng.

### Bài tập D — Offboarding có kiểm chứng

Công ty ngừng hợp tác với nhà cung cấp gửi thông báo. Business owner nhận được email “đã hủy tài khoản”, nhưng hệ thống vẫn còn scheduled job dùng API key cũ và vendor lưu bản sao địa chỉ email trong backup.

Hãy đề xuất thứ tự xử lý và evidence:

- Dừng job/luồng dữ liệu, thu hồi token và xóa các cấu hình còn liên kết.
- Kiểm tra API key cũ có thể hoạt động sau thu hồi hay không.
- Làm rõ chính sách xóa dữ liệu trong backup và các ngoại lệ lưu giữ.
- Đối chiếu danh sách subprocessor liên quan và trách nhiệm xử lý.
- Cập nhật inventory, nghĩa vụ hợp đồng, finding và risk register.
- Định nghĩa điều kiện có thể kết luận offboarding hoàn tất trong phạm vi xác định.

## 22. Checklist để đánh giá một supplier security policy

Dùng checklist để rà soát **mức độ hoàn chỉnh của chương trình**, không xem số ô được đánh dấu là chứng nhận bảo mật:

- [ ] Chính sách xác định mục tiêu, phạm vi vendor, loại dịch vụ, dữ liệu và quyền truy cập.
- [ ] Có supplier inventory và người chịu trách nhiệm cho mỗi quan hệ.
- [ ] Có phương pháp phân tầng theo tác động, quyền, dữ liệu, phụ thuộc và bất định.
- [ ] Có due diligence tương xứng tier và tiêu chí approval trước khi cấp quyền.
- [ ] Có danh sách security requirements, control owner và evidence owner.
- [ ] Có điều khoản bảo mật/hợp đồng, nghĩa vụ dữ liệu và incident phù hợp phạm vi áp dụng.
- [ ] Có shared responsibility matrix hoặc cách phân định rõ hai phía.
- [ ] Có cơ chế cấp/thu hồi IAM, token, secret, network và quyền hỗ trợ bên ngoài.
- [ ] Có cách đánh giá báo cáo bên thứ ba theo scope, kỳ, ngoại lệ và bằng chứng.
- [ ] Có finding, remediation, retest, exception và quyết định residual risk đúng thẩm quyền.
- [ ] Có review định kỳ và trigger khi đổi subprocessor, chức năng, dữ liệu hoặc sự cố.
- [ ] Có quy trình xử lý incident, phối hợp truyền thông, nghĩa vụ thông báo và đầu mối.
- [ ] Có kế hoạch BCP/DR và exit cho các phụ thuộc trọng yếu.
- [ ] Có offboarding gồm ngắt kết nối, thu hồi quyền, trả/xóa dữ liệu và bằng chứng.
- [ ] Có báo cáo metrics trọng yếu, giới hạn bằng chứng và rủi ro tồn đọng cho lãnh đạo.

## 23. Ghi nhớ

- **Chính sách nhà cung cấp** điều chỉnh cách quản lý rủi ro và yêu cầu bảo mật của bên thứ ba trong **toàn bộ vòng đời quan hệ**, từ lựa chọn đến chấm dứt.
- Phải **phân loại theo tài sản, dữ liệu, quyền truy cập, phụ thuộc, nghĩa vụ và độ bất định**, không chỉ theo tên thương hiệu, giá hợp đồng hoặc chứng nhận.
- **Chính sách, hợp đồng, control và evidence** phục vụ các chức năng khác nhau; một lời cam kết chưa phải bằng chứng vận hành hiệu quả.
- **Shared responsibility** phải được diễn giải cho dịch vụ và tích hợp cụ thể; tổ chức dùng dịch vụ vẫn có control cần tự thực hiện.
- Bảo đảm cần chuỗi **risk → requirement → control owner → assessment/test/evidence → finding/remediation → residual risk** có phạm vi, kỳ và giới hạn rõ.
- Nhà cung cấp và môi trường thay đổi liên tục nên cần **giám sát, kiểm thử lại, quản lý ngoại lệ và quyết định lại khi có trigger**.
- Kết thúc hợp đồng chỉ hoàn tất khi **quyền, luồng dữ liệu, phụ thuộc và nghĩa vụ xử lý dữ liệu** được kiểm soát và có evidence tương ứng.

