# Shared responsibility trong Cloud Assurance

Khi đưa một hệ thống lên cloud, tổ chức không chuyển toàn bộ trách nhiệm bảo mật cho nhà cung cấp. Nhà cung cấp dịch vụ đám mây (*Cloud Service Provider*, CSP) bảo vệ những thành phần và hoạt động thuộc phạm vi họ kiểm soát; khách hàng vẫn chịu trách nhiệm về cách sử dụng dịch vụ, dữ liệu, định danh, cấu hình và những phần mềm do mình triển khai. **Shared responsibility** là mô hình phân định những nghĩa vụ đó, bao gồm các điểm giao nhau cần phối hợp giữa hai bên.

Trong **security assurance**, biết “ai chịu trách nhiệm” mới là bước đầu. Tổ chức phải chứng minh bằng bằng chứng phù hợp rằng từng biện pháp kiểm soát (*security control*) đã được triển khai, hoạt động hiệu quả và có người xử lý khi phát hiện sai lệch. Một chứng nhận của CSP không thay thế được việc kiểm tra cấu hình tài khoản cloud của khách hàng; ngược lại, quét cấu hình phía khách hàng không kiểm chứng được toàn bộ kiểm soát bên trong trung tâm dữ liệu của CSP.

Sau bài học này, người học có thể xác định ranh giới trách nhiệm theo IaaS, PaaS, SaaS; lập ma trận trách nhiệm đến cấp kiểm soát; thu thập bằng chứng từ cả hai phía; và vận hành quy trình đánh giá, giám sát, khắc phục trong suốt vòng đời dịch vụ.

## 1. Hiểu đúng về ranh giới trách nhiệm

Một cách diễn đạt thường dùng là:

- **Security *of* the cloud**: CSP bảo vệ cơ sở hạ tầng, nền tảng và các thành phần họ vận hành theo phạm vi dịch vụ đã cam kết.
- **Security *in* the cloud**: khách hàng bảo vệ ứng dụng, dữ liệu, danh tính, cấu hình và những tài nguyên mình được quyền quản lý.

Đây là quy tắc định hướng, không phải ranh giới pháp lý hoặc kỹ thuật áp dụng giống nhau cho mọi sản phẩm. Chẳng hạn, CSP có thể vận hành dịch vụ quản lý khóa mã hóa, nhưng khách hàng vẫn phải quản lý chính sách cho phép sử dụng khóa, quyền quản trị và vòng đời khóa theo lựa chọn dịch vụ. Một cơ chế kiểm soát có thể có **nhiều phần việc do các bên khác nhau thực hiện**.

Cần phân biệt bốn khái niệm:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Trách nhiệm** (*responsibility*) | Bên nào phải thực hiện hoặc cung cấp điều gì? | CSP bảo trì máy chủ vật lý; khách hàng cấu hình quyền truy cập vào kho dữ liệu. |
| **Trách nhiệm giải trình** (*accountability*) | Ai phải bảo đảm kết quả cuối cùng được kiểm soát và chấp nhận rủi ro? | Chủ sở hữu hệ thống của tổ chức chịu trách nhiệm trước bộ phận quản trị về việc dùng cloud an toàn. |
| **Quyền kiểm soát** (*control/authority*) | Bên nào thực sự có khả năng thay đổi cấu hình hoặc vận hành thành phần? | Khách hàng chỉnh được chính sách IAM, nhưng không vá được hệ điều hành của máy chủ vật lý CSP. |
| **Bằng chứng assurance** (*assurance evidence*) | Dựa vào đâu để đánh giá nghĩa vụ đã được đáp ứng? | Báo cáo kiểm toán CSP trong phạm vi liên quan, cấu hình IAM xuất từ API, kết quả kiểm tra truy cập. |

Một yêu cầu có thể là trách nhiệm phối hợp nhưng vẫn cần **chia thành các nghĩa vụ nhỏ có chủ sở hữu rõ ràng**. Ví dụ, yêu cầu “chỉ người được phép mới truy cập dữ liệu” bao gồm bảo vệ hạ tầng của CSP, thực thi chính sách truy cập của dịch vụ và phân quyền người dùng do khách hàng quản lý. Ghi chung “hai bên cùng chịu trách nhiệm” sẽ khiến kiểm soát khó được thực thi và kiểm tra.

### Trách nhiệm thay đổi theo những gì?

Trước khi phân công, phải xác định **dịch vụ cụ thể**, mô hình triển khai, tính năng bật/tắt, vùng lưu trữ dữ liệu, hợp đồng/SLA, các tùy chọn managed, phương thức mã hóa và bên thứ ba tham gia. Cùng là “database trên cloud” nhưng trách nhiệm vá hệ điều hành của máy ảo tự quản trị khác với trách nhiệm vá nền tảng của dịch vụ cơ sở dữ liệu được quản lý.

Nhà cung cấp có thể sử dụng nhà thầu phụ (*subservice organization*); tổ chức sử dụng cloud cũng có thể thuê một nhà cung cấp dịch vụ quản trị (*managed service provider*, MSP). Việc thuê ngoài hoạt động không tự động xóa trách nhiệm giải trình của tổ chức. Phải ghi rõ nghĩa vụ trong hợp đồng và kiểm tra bằng chứng từ chuỗi cung ứng liên quan.

## 2. Phân chia điển hình theo IaaS, PaaS và SaaS

| Lớp hoặc hoạt động | IaaS: máy ảo, mạng ảo, đĩa | PaaS: runtime / database được quản lý | SaaS: ứng dụng hoàn chỉnh |
|---|---|---|---|
| Trung tâm dữ liệu, thiết bị vật lý, nền tảng ảo hóa | CSP vận hành và bảo vệ | CSP vận hành và bảo vệ | CSP vận hành và bảo vệ |
| Hệ điều hành và phần mềm hệ thống | Khách hàng quản trị, vá OS của VM; CSP bảo vệ host | CSP thường quản lý OS/runtime nằm trong dịch vụ; khách hàng quản lý thành phần được phép cấu hình | CSP quản lý hạ tầng và ứng dụng SaaS |
| Mã nguồn ứng dụng và thư viện | Khách hàng | Khách hàng đối với ứng dụng tự triển khai; CSP đối với thành phần nền tảng | CSP đối với sản phẩm SaaS; khách hàng đối với mã tích hợp, script và tiện ích bổ sung do mình quản lý |
| Cấu hình mạng và điểm truy cập | Khách hàng cấu hình security group, tuyến mạng, firewall ảo; CSP bảo vệ mạng nền tảng | CSP bảo vệ mạng nền tảng; khách hàng thiết lập public/private endpoint, ACL và kết nối được cung cấp | CSP bảo vệ mạng ứng dụng; khách hàng cấu hình các tùy chọn truy cập, thiết bị, tích hợp khi dịch vụ hỗ trợ |
| Tài khoản, định danh và quyền | CSP bảo vệ dịch vụ IAM; khách hàng cấp quyền, MFA, vòng đời tài khoản | Tương tự; bổ sung danh tính ứng dụng và quyền truy cập dịch vụ | CSP thực thi cơ chế đăng nhập/ủy quyền của sản phẩm; khách hàng quản lý người dùng, nhóm, SSO/MFA và quyền trong tenant |
| Dữ liệu, phân loại, chia sẻ, lưu giữ | Khách hàng quyết định chính sách và cấu hình bảo vệ | Khách hàng quyết định chính sách và tùy chọn dịch vụ; CSP vận hành thành phần dữ liệu được quản lý | Khách hàng chịu trách nhiệm chính sách dữ liệu, chia sẻ và thời hạn lưu giữ trong các giới hạn tính năng/hợp đồng |
| Ghi log, sao lưu và khôi phục | CSP cung cấp khả năng theo dịch vụ; khách hàng bật, cấu hình, giám sát và thử khôi phục phần mình quản lý | Trách nhiệm chia theo dịch vụ, cấp hỗ trợ và chính sách retention đã chọn | Phụ thuộc tính năng, hợp đồng và phạm vi xuất dữ liệu; khách hàng vẫn phải xác định yêu cầu và kiểm tra khả năng đáp ứng |

**Lưu ý:** Bảng nêu xu hướng điển hình, không phải cam kết của một CSP. Ví dụ “managed database” có thể được CSP vá engine trong phạm vi nhất định, nhưng khách hàng vẫn phải cấu hình truy cập, tham số bảo mật, mức phiên bản được phép, lịch bảo trì và kiểm tra ảnh hưởng đến ứng dụng. Quyết định cuối cùng phải dựa trên tài liệu trách nhiệm **của chính dịch vụ** và điều khoản có hiệu lực.

Quy tắc thực hành là: **mức trừu tượng hóa dịch vụ càng cao thì CSP thường vận hành nhiều lớp kỹ thuật hơn**, nhưng nghĩa vụ quản trị dữ liệu, phân quyền người dùng, đánh giá rủi ro và tuân thủ của khách hàng vẫn tồn tại.

## 3. Chuyển mô hình trách nhiệm thành kiểm soát có thể kiểm chứng

Một sơ đồ IaaS/PaaS/SaaS chưa đủ để đánh giá assurance. Cần đi từ **mục tiêu bảo mật → thành phần trong phạm vi → nghĩa vụ từng bên → bằng chứng → phép kiểm tra → kết luận**.

Giả sử doanh nghiệp vận hành ứng dụng xử lý đơn hàng, gồm:

- API chạy trên máy ảo IaaS.
- Cơ sở dữ liệu giao dịch dưới dạng managed database.
- Kho object storage chứa hóa đơn và tài liệu khách hàng.
- Hệ thống IAM dùng để cấp quyền cho quản trị viên, ứng dụng và nhân viên.

Ma trận kiểm soát minh họa:

| Mục tiêu kiểm soát | Nghĩa vụ CSP cần làm rõ | Nghĩa vụ khách hàng | Bằng chứng / cách kiểm tra ở phía khách hàng |
|---|---|---|---|
| Hạn chế truy cập đặc quyền | Bảo vệ và vận hành dịch vụ IAM, cơ chế xác thực được cung cấp | Bật MFA, cấp quyền tối thiểu, loại bỏ tài khoản không sử dụng, rà soát định kỳ | Danh sách principal/role, cấu hình MFA, kết quả access review, truy vấn phát hiện quyền quá rộng |
| Bảo vệ hệ điều hành của API | Bảo vệ host và nền tảng ảo hóa IaaS | Vá OS trong VM, cấu hình hardening, EDR và quyền đăng nhập | Báo cáo bản vá, baseline cấu hình, kết quả quét lỗ hổng trên VM |
| Bảo vệ managed database | Vận hành, vá và bảo vệ các lớp CSP quản lý theo phạm vi dịch vụ | Giới hạn kết nối, phân quyền DB, cấu hình TLS, sao lưu, tham số an toàn | Snapshot cấu hình, danh sách DB user, kiểm tra kết nối trái phép, bài thử restore |
| Ngăn công khai hóa tài liệu | Bảo vệ hạ tầng và thực thi các cơ chế chính sách của object storage | Cấm public access, thiết lập policy/ACL, phân loại dữ liệu, kiểm soát chia sẻ | Policy-as-code, bản chụp cấu hình, phép thử truy cập ẩn danh được cho phép |
| Bảo vệ khóa và dữ liệu mã hóa | Vận hành chức năng mã hóa và quản lý khóa theo phương án đã chọn | Chọn chế độ mã hóa, phân quyền dùng khóa, quy định thay đổi/vô hiệu hóa khóa | Cấu hình encryption, key policy, lịch sử thay đổi và kiểm tra truy cập |
| Phát hiện và xử lý sự cố | Ghi nhận, thông báo các sự cố thuộc phạm vi CSP theo quy định dịch vụ/hợp đồng | Bật audit log, chuyển log, phát hiện hành vi bất thường, phản ứng trong tenant | Cấu hình log, sự kiện kiểm thử, cảnh báo SIEM, biên bản diễn tập |
| Khôi phục dịch vụ | Cung cấp khả năng dự phòng/sao lưu của từng dịch vụ như đã cam kết | Đặt RPO/RTO, cấu hình và kiểm tra backup, thực hiện diễn tập khôi phục ứng dụng | Lịch sử backup, báo cáo restore, kết quả đối chiếu dữ liệu và thời gian phục hồi |

Trong bảng, cụm “CSP cần làm rõ” là điểm phải **đối chiếu tài liệu dịch vụ/hợp đồng**, không phải lời bảo đảm mặc định. Nếu CSP chịu trách nhiệm triển khai một biện pháp, khách hàng có thể không trực tiếp kiểm tra máy chủ CSP; khi đó phải xác định cách nhận bằng chứng độc lập phù hợp và rủi ro còn lại.

### Không dùng “shared” thay cho phân công cụ thể

Ví dụ mục tiêu “mã hóa dữ liệu khi lưu trữ” thường cần tách thành:

1. **CSP:** cung cấp và vận hành cơ chế mã hóa của dịch vụ, bảo vệ thành phần hạ tầng và khóa thuộc phạm vi CSP quản lý.
2. **Khách hàng:** chọn tùy chọn mã hóa phù hợp, cấu hình quyền sử dụng khóa, quản trị khóa do mình kiểm soát nếu chọn customer-managed key.
3. **Nhóm assurance:** kiểm tra bằng chứng về bảo vệ nền tảng của CSP, trạng thái mã hóa trên từng tài nguyên, quyền sử dụng khóa và các ngoại lệ.

Nếu dùng khóa do khách hàng tự quản lý, việc mất khóa hoặc thu hồi nhầm quyền có thể khiến dữ liệu không đọc được dù dịch vụ cloud vẫn hoạt động. Trách nhiệm mã hóa phải bao gồm cả **tính bảo mật lẫn khả năng khôi phục**.

## 4. Hai nguồn bằng chứng: từ CSP và từ chính tenant

### 4.1. Bằng chứng do CSP cung cấp

Tùy mức độ rủi ro, quy định và điều khoản dịch vụ, tổ chức có thể sử dụng:

- Tài liệu **shared responsibility** và phạm vi vận hành riêng của dịch vụ, kèm lịch sử thay đổi.
- Báo cáo đánh giá độc lập như **SOC 2 Type II**, giấy chứng nhận **ISO/IEC 27001**, báo cáo kiểm toán hoặc bản công bố kiểm soát được CSP cho phép tiếp cận.
- Bản mô tả **phạm vi hệ thống**, vùng địa lý, tổ chức phụ trợ, ngoại lệ/ý kiến kiểm toán, thời kỳ được kiểm tra và các biện pháp khách hàng bắt buộc tự thực hiện (*Complementary User Entity Controls* – CUECs, nếu báo cáo có nêu).
- Cam kết hợp đồng về bảo vệ dữ liệu, thông báo sự cố, tính sẵn sàng, bảo mật, hỗ trợ điều tra, vị trí xử lý dữ liệu và quyền tiếp cận bằng chứng.
- Tài liệu kiến trúc và tính năng bảo mật có thể đối chiếu với dịch vụ thực tế đang dùng.

Không thể kết luận “ứng dụng tuân thủ” chỉ vì CSP có chứng nhận. Cần đọc **phạm vi**, **kỳ hiệu lực**, **điều kiện loại trừ**, **các ngoại lệ** và **nghĩa vụ của khách hàng**. Chứng nhận ở cấp tổ chức của CSP cũng không tự chứng minh rằng một tính năng hoặc một cấu hình tenant cụ thể đã được kích hoạt đúng.

Bằng chứng CSP thường chỉ có thể được chia sẻ theo điều khoản bảo mật. Kho lưu trữ assurance phải phân quyền truy cập, ghi nguồn gốc và không đưa các báo cáo mật lên repository công khai.

### 4.2. Bằng chứng khách hàng phải tự tạo

Nhóm cloud/platform, đội phát triển và nhóm bảo mật nên tạo bằng chứng có thể kiểm tra lại:

| Nhóm bằng chứng | Dữ liệu nên lưu | Sai lầm thường gặp |
|---|---|---|
| Cấu hình tài nguyên | Snapshot từ API cloud, IaC, chính sách và thời điểm thu thập | Chỉ chụp màn hình một thời điểm, không truy được tài nguyên/phiên bản |
| Kiểm soát danh tính | Role, policy, MFA, account lifecycle, log cấp/thu hồi quyền | Chỉ liệt kê user mà bỏ qua service account và quyền xuyên tài khoản |
| Kiểm thử kỹ thuật | Kết quả kiểm tra cấu hình, quét lỗ hổng, thử truy cập, thử restore | Có kết quả “PASS” nhưng thiếu tiêu chí, đầu vào và phạm vi thử |
| Vận hành kiểm soát | Audit log, alert, ticket sự cố, kết quả xử lý, phê duyệt thay đổi | Chứng minh đã bật công cụ nhưng không chứng minh đã theo dõi/can thiệp |
| Quản trị và rủi ro | Control owner, đánh giá rủi ro, ngoại lệ có hạn, quyết định chấp nhận rủi ro | Để ngoại lệ vô thời hạn hoặc không gắn với chủ sở hữu |

Mỗi bằng chứng nên có ít nhất **control ID, asset/service ID, môi trường, người chịu trách nhiệm, thời điểm, phạm vi, phương pháp thu thập, kết quả và nơi lưu an toàn**. Với kiểm soát liên tục, cần xác định tuổi tối đa của bằng chứng. Thông tin chứa bí mật, token, dữ liệu cá nhân hoặc chi tiết nhạy cảm phải được ẩn/lọc và kiểm soát quyền truy cập trước khi lưu.

## 5. Quy trình Cloud Assurance dựa trên trách nhiệm được chia sẻ

Có thể triển khai quy trình sau như một vòng lặp trong phát triển và vận hành:

1. **Lập phạm vi:** kiểm kê tài khoản/subscription/project, region, dịch vụ, tài nguyên, luồng dữ liệu, mức phân loại dữ liệu, kết nối với hệ thống bên ngoài và nhà cung cấp phụ trợ. Chỉ ra nơi CSP kết thúc quyền kiểm soát và nơi khách hàng bắt đầu.
2. **Xác định mục tiêu và kiểm soát:** xuất phát từ yêu cầu bảo mật, pháp lý, hợp đồng và đánh giá rủi ro. Có thể tham chiếu NIST CSF, NIST SP 800-53 hoặc CSA Cloud Controls Matrix; không thay thế việc kiểm tra thực tế bằng việc “đã ánh xạ framework”.
3. **Phân công công việc:** tạo ma trận theo từng control/tài nguyên; chỉ rõ bên thực hiện, người chịu trách nhiệm giải trình phía tổ chức, bên cần phối hợp, cơ chế bàn giao và nghĩa vụ CUEC nếu có.
4. **Xác định tiêu chí đạt:** viết tiêu chí kiểm chứng được, ví dụ “mọi tài khoản quản trị tương tác đều dùng MFA”, “không có bucket chứa dữ liệu nhạy cảm cho phép truy cập công khai”, “khôi phục DB đáp ứng RTO/RPO đã phê duyệt”. Đặt ngưỡng dựa trên chính sách của tổ chức, không xem các ví dụ là chuẩn bắt buộc cho mọi môi trường.
5. **Thu thập và xác minh bằng chứng:** rà soát báo cáo CSP theo đúng phạm vi, kiểm tra cấu hình tenant qua API/IaC, thực hiện thử nghiệm được phép và đối chiếu dữ liệu quan sát với tiêu chí.
6. **Ghi kết luận và xử lý phát hiện:** phân loại đạt/không đạt/chưa đủ bằng chứng/không áp dụng; gán owner, mức ưu tiên, thời hạn sửa, bằng chứng retest. Đánh giá rủi ro còn lại và phê duyệt ngoại lệ bằng người có thẩm quyền.
7. **Giám sát khi có thay đổi:** kiểm tra ở pull request và pipeline triển khai, định kỳ rà soát quyền và báo cáo CSP, cảnh báo cấu hình trôi (*configuration drift*), đánh giá lại khi thay đổi vùng, dịch vụ, hợp đồng hoặc nhà cung cấp.

Một kiểm soát **không đủ bằng chứng** không nên được đánh dấu “PASS”. Thiếu bằng chứng phải hiển thị thành một trạng thái cần xử lý riêng, đặc biệt ở các bước phát hành có yêu cầu assurance.

### RACI ở bên khách hàng

Với mỗi kiểm soát, cần xác định ai **thực hiện** (*Responsible*), ai **chịu trách nhiệm giải trình** (*Accountable*), ai **được tham vấn** (*Consulted*) và ai **được thông báo** (*Informed*). Thông thường chỉ nên có một đầu mối accountable trong tổ chức cho một quyết định cụ thể, dù có nhiều người thực hiện. RACI nội bộ không thay thế nghĩa vụ của CSP trong hợp đồng.

Ví dụ với cấu hình object storage: platform team viết chính sách mặc định, product team phân loại dữ liệu và phê duyệt nhu cầu chia sẻ, security team kiểm tra độc lập, service owner chịu trách nhiệm chấp nhận rủi ro đối với tài nguyên của mình. Nếu phát hiện public access trái quy định, ticket phải có owner và bằng chứng đóng lỗi.

## 6. Ví dụ hồ sơ assurance cho một kiểm soát

Một biểu ghi nhỏ có thể gắn trong control register hoặc hệ thống GRC, giúp tránh đánh giá chung chung theo tên sản phẩm:

~~~yaml
control_id: CLOUD-DATA-ACCESS-01
asset_id: order-invoices
environment: production
service_model: object-storage
objective: "Chỉ danh tính được cấp phép mới đọc hóa đơn"

provider:
  obligation: "Vận hành cơ chế lưu trữ và thực thi chính sách truy cập"
  evidence_required: "Tài liệu dịch vụ và bằng chứng assurance trong phạm vi"

customer:
  accountable: "Order Service Owner"
  responsible: "Cloud Platform Team"
  obligations:
    - "Chặn truy cập công khai"
    - "Áp dụng quyền tối thiểu cho ứng dụng và người vận hành"
    - "Ghi log truy cập theo chính sách"

verification:
  criteria:
    - "Không có cấu hình công khai trái chính sách"
    - "Không có quyền đọc ngoài các principal được phê duyệt"
    - "Audit log đã bật và được chuyển tới nơi lưu theo quy định"
  method: "IaC scan, cloud API check và thử truy cập có kiểm soát"
  frequency: "Mỗi lần triển khai và theo lịch rà soát"
  evidence_location: "Kho bằng chứng nội bộ có kiểm soát quyền"
  result: "PENDING"

remediation:
  owner: "Cloud Platform Team"
  tracking_ticket: null
~~~

Đây là **ví dụ về cấu trúc dữ liệu**, không phải cấu hình để triển khai trực tiếp. Các chuỗi tên nhóm, tên tài nguyên, kiểm soát và tần suất cần thay bằng giá trị thực tế. Trạng thái ban đầu là PENDING; chỉ chuyển PASS khi có bằng chứng đáp ứng tất cả tiêu chí.

Giả sử pipeline phát hiện kho hóa đơn bị cấu hình public. CSP vẫn có thể bảo vệ máy chủ lưu trữ, mạng lõi và cơ chế policy đúng cam kết. Tuy nhiên, **khách hàng đã vi phạm nghĩa vụ cấu hình quyền**, nên kết luận assurance cho kiểm soát truy cập là FAIL. Cách khắc phục gồm chặn quyền công khai, kiểm tra log để đánh giá khả năng dữ liệu đã bị truy cập, xử lý sự cố nếu cần, sửa IaC/baseline và chạy lại kiểm tra. Bằng chứng đóng phát hiện phải thể hiện cả cấu hình mới lẫn kết quả retest.

## 7. Các điểm giao nhau dễ bị bỏ sót

### Định danh và truy cập

CSP thường cung cấp IAM, token service hoặc tính năng SSO. Khách hàng phải bảo vệ tài khoản gốc/quản trị, chọn chính sách xác thực, kiểm soát service principal, workload identity, quyền liên tài khoản và khóa API. Nếu dùng dịch vụ danh tính bên thứ ba, kiểm tra cả đường đi khi đồng bộ nhóm, thu hồi quyền và xử lý sự cố. Việc CSP hỗ trợ MFA **không có nghĩa** MFA đã được bật cho tất cả đối tượng cần bảo vệ.

### Mã hóa và quản lý khóa

Cần xác định rõ mã hóa khi truyền, mã hóa khi lưu, khóa do CSP quản lý hay khách hàng quản lý, quyền sử dụng khóa, rotation, logging và thủ tục khôi phục. Cấu hình mã hóa mặc định không đủ để kết luận bảo vệ dữ liệu nếu tài khoản có quyền truy cập quá rộng hoặc sao lưu không cùng mức bảo vệ. Không được coi “có encryption” là bằng chứng tự động cho tính bí mật đầu cuối.

### Log, giám sát và điều tra

CSP thường sở hữu log nội bộ của nền tảng; khách hàng thấy tập telemetry do dịch vụ cung cấp. Tổ chức phải quyết định loại log nào cần bật, thời hạn lưu, nguồn đồng bộ, cảnh báo, người phản hồi và yêu cầu phục vụ điều tra. Khi xảy ra sự cố, cần quy trình phối hợp để nhận thông tin từ CSP, bảo toàn bằng chứng phía tenant và phân định các bước xử lý.

### Sao lưu, khôi phục và tính sẵn sàng

Độ bền dữ liệu (*durability*) hoặc SLA uptime của một dịch vụ không đồng nghĩa khả năng khôi phục toàn bộ ứng dụng sau lỗi cấu hình, xóa nhầm hoặc ransomware. Cần phân biệt khả năng CSP cung cấp với chính sách backup, bản sao độc lập nếu cần, retention, kiểm tra restore và phương án DR của khách hàng. Kiểm chứng bằng thử nghiệm RPO/RTO thực tế theo mức yêu cầu đã phê duyệt.

### Bảo vệ dữ liệu cá nhân và tuân thủ

CSP có thể cung cấp hợp đồng xử lý dữ liệu, chức năng chọn vùng và thông tin về nhà cung cấp phụ trợ. Tổ chức vẫn phải xác định mục đích xử lý, phân loại dữ liệu, căn cứ tuân thủ áp dụng, quyền truy cập, thời gian lưu, quy trình xóa và cách xử lý yêu cầu của chủ thể dữ liệu. Phạm vi tuân thủ phụ thuộc luật, vai trò của các bên và hợp đồng cụ thể; **chứng nhận CSP không tự chuyển thành chứng nhận tuân thủ cho khách hàng**.

### Đa đám mây, hybrid và dịch vụ bên thứ ba

Với hệ thống kết nối nhiều CSP, mạng on-premises, CDN, SIEM, công cụ CI/CD hoặc MSP, cần mô tả từng **giao diện chuyển giao trách nhiệm**: ai quản lý chứng chỉ kết nối, ai theo dõi log luồng dữ liệu, ai vô hiệu hóa khóa khi sự cố, ai chịu trách nhiệm sao lưu khi dữ liệu đã rời hệ thống gốc. Các khoảng trống thường xuất hiện ở chính nơi hai bên đều cho rằng bên còn lại sẽ làm.

## 8. Sai lầm thường gặp và tác động đến assurance

| Nhận định sai | Vì sao sai | Cách kiểm chứng đúng |
|---|---|---|
| “Dùng cloud nghĩa là CSP chịu mọi trách nhiệm bảo mật.” | Khách hàng vẫn quản lý nhiều cấu hình, tài khoản, dữ liệu và workload. | Đọc ranh giới theo từng dịch vụ và tạo ma trận đến mức kiểm soát. |
| “CSP có SOC 2/ISO 27001, vậy hệ thống đã an toàn.” | Báo cáo có phạm vi/kỳ đánh giá riêng, không kiểm chứng cấu hình tenant. | Rà soát phạm vi, ngoại lệ, CUECs; thu thập thêm bằng chứng từ tenant. |
| “Managed service đồng nghĩa không phải cấu hình hay cập nhật gì.” | Khách hàng thường còn quyền quyết định policy, phiên bản, endpoint, truy cập và thay đổi tương thích. | Kiểm tra mục “customer responsibilities” của chính dịch vụ và các tùy chọn đã chọn. |
| “Đã bật log tức là có giám sát.” | Log có thể không đủ nguồn, không được giữ, không có cảnh báo hoặc không được xử lý. | Gửi sự kiện kiểm thử, truy dấu đến alert/ticket và đánh giá quy trình phản hồi. |
| “Có backup tức là có thể phục hồi.” | Backup có thể hỏng, quá cũ hoặc không khôi phục được toàn bộ phụ thuộc của ứng dụng. | Diễn tập restore và đo RPO/RTO. |
| “Kiểm tra một lần lúc go-live là đủ.” | Quyền, cấu hình, phiên bản và phạm vi dịch vụ thay đổi liên tục. | Gắn kiểm tra vào CI/CD và lịch đánh giá lại khi có thay đổi. |

## 9. Bộ câu hỏi rà soát trước khi kết luận

Dùng những câu hỏi này trong design review, cloud onboarding, kiểm toán nội bộ hoặc trước khi phát hành:

- **Phạm vi:** Đã biết những dịch vụ/region/tài khoản và luồng dữ liệu liên quan chưa? Có nhà thầu phụ hoặc tích hợp bên ngoài không?
- **Trách nhiệm:** Mỗi nghĩa vụ có bên thực hiện và owner nội bộ không? Các điểm “shared” đã tách thành phần việc kiểm chứng được chưa?
- **Bằng chứng CSP:** Tài liệu/báo cáo có bao phủ dịch vụ, thời gian và phạm vi đang dùng không? Có ngoại lệ hoặc CUEC chưa được đáp ứng không?
- **Bằng chứng khách hàng:** Cấu hình, quyền, log, kết quả kiểm thử và restore có chứng minh được mục tiêu không? Bằng chứng có đủ mới và truy xuất được không?
- **Phát hiện:** Những trường hợp FAIL, chưa đủ bằng chứng và ngoại lệ có người xử lý, thời hạn, mức rủi ro và kế hoạch retest không?
- **Liên tục:** Có cơ chế phát hiện drift và đánh giá lại khi thêm dịch vụ, thay đổi hợp đồng, region, quyền hoặc kiến trúc không?

**Tiêu chí hoàn thành một đánh giá:** Từng kiểm soát trong phạm vi có kết luận dựa trên bằng chứng, chỉ rõ trách nhiệm, hạn chế của bằng chứng và trạng thái xử lý rủi ro. Các điểm chưa kiểm chứng phải được giữ lại để theo dõi, không được ngầm xem là đạt.

## 10. Bài tập tình huống

Một nhóm phát triển chuyển ứng dụng nhân sự từ máy chủ tự quản lý sang SaaS. Nhà cung cấp thông báo có mã hóa dữ liệu, chứng nhận bảo mật và sao lưu định kỳ. Trong quá trình kiểm tra, nhóm phát hiện người dùng có thể chia sẻ hồ sơ nhân sự ra ngoài tổ chức qua đường liên kết công khai.

**Câu hỏi:** Nhà cung cấp đã có các kiểm soát bảo mật nêu trên, vậy trách nhiệm đối với việc chia sẻ sai là của ai? Cần bằng chứng gì để kết luận và khắc phục?

**Gợi ý đáp án:**

1. Xác định tính năng chia sẻ và chính sách quyền thực tế của SaaS; kiểm tra tài liệu/hợp đồng để biết CSP vận hành cơ chế gì và khách hàng có quyền cấu hình gì.
2. Nếu khách hàng quản lý chính sách chia sẻ, nhóm quản trị tenant phải chặn chia sẻ trái quy định, hạn chế quyền, rà soát những liên kết đã tạo và xác định phạm vi dữ liệu có thể bị lộ. CSP chịu trách nhiệm vận hành cơ chế thực thi theo cam kết; nếu có dấu hiệu cơ chế đó hoạt động sai, mở yêu cầu điều tra với CSP.
3. Thu thập cấu hình chia sẻ trước/sau, danh sách liên kết và quyền, log truy cập/xuất dữ liệu sẵn có, biên bản phân loại ảnh hưởng, ticket khắc phục và kết quả thử lại. Bảo vệ dữ liệu cá nhân trong quá trình thu thập chứng cứ.
4. Bổ sung chính sách mặc định, quy trình phê duyệt chia sẻ, cảnh báo và kiểm tra định kỳ. Không dùng chứng nhận CSP làm lý do bỏ qua phát hiện ở cấp tenant.

Bài tập thể hiện nguyên tắc cốt lõi của **Cloud Assurance**: trách nhiệm luôn phải được gắn với một thành phần và hành động cụ thể; mức độ bảo đảm chỉ được kết luận từ bằng chứng cho cả những phần CSP thực hiện lẫn những nghĩa vụ mà tổ chức sử dụng cloud phải đáp ứng.
