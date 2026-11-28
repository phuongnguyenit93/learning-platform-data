# Rà soát chính sách bảo mật (Security Policy Review)

## 1. Rà soát chính sách là gì?

**Rà soát chính sách bảo mật** (*security policy review*) là quá trình đánh giá có hệ thống xem một chính sách đang áp dụng có **còn phù hợp với mục tiêu, rủi ro và nghĩa vụ của tổ chức**, có **đủ rõ để thực thi**, có được quản lý bằng **thẩm quyền và phiên bản chính thức**, và có được chuyển thành các security controls có thể kiểm chứng hay không.

Rà soát không chỉ là đọc lại tài liệu để sửa câu chữ hoặc đổi ngày “đã xem xét”. Một cuộc rà soát có giá trị phải trả lời được các câu hỏi:

1. **Chính sách còn cần thiết và đúng phạm vi không?** Tài sản, threat, yêu cầu kinh doanh và nghĩa vụ áp dụng có thay đổi?
2. **Các quy định có rõ và nhất quán không?** Người triển khai có thể xác định điều bắt buộc, đối tượng áp dụng và tiêu chí đạt?
3. **Có control đáp ứng mỗi yêu cầu quan trọng không?** Ai chịu trách nhiệm, có khoảng trống hoặc xung đột với quy trình khác?
4. **Có bằng chứng về việc thực thi không?** Cấu hình, kiểm thử, audit và dữ liệu vận hành có hỗ trợ kết luận?
5. **Ngoại lệ và phát hiện đã được quản lý chưa?** Có phương án giảm rủi ro, người chịu trách nhiệm và thời hạn hợp lệ?
6. **Cần quyết định gì?** Giữ nguyên, sửa đổi, thay thế, thu hồi chính sách hay sửa control thay vì sửa chính sách?

Trong module **SECURITY_SECURITY_ASSURANCE**, rà soát chính sách gắn trực tiếp với mục tiêu **xây dựng niềm tin có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật**. Chính sách tạo đầu vào cho yêu cầu bảo mật; chương trình assurance thu thập bằng chứng thiết kế và vận hành của control; kết quả kiểm thử, audit và khắc phục lại cung cấp đầu vào để rà soát xem chính sách có còn hiệu quả và khả thi không.

> **Phân biệt quan trọng:** chính sách được viết đúng **không có nghĩa** hệ thống tuân thủ; hệ thống chưa tuân thủ **không mặc định** có nghĩa phải nới lỏng chính sách. Đôi khi việc cần làm là sửa hoặc tăng kiểm thử cho control, không phải đổi quy tắc bảo vệ.

## 2. Mục tiêu và kết quả mong đợi

Một vòng rà soát có thể xem xét đồng thời **tính phù hợp, tính đầy đủ, khả năng áp dụng và chất lượng giám sát**.

| Khía cạnh | Câu hỏi cốt lõi | Bằng chứng hoặc kết quả hữu ích |
| --- | --- | --- |
| **Phù hợp (suitability)** | Chính sách có phản ánh đúng tài sản, threat, rủi ro và mục tiêu hiện tại? | Risk register, threat model, thay đổi kiến trúc, đánh giá ảnh hưởng |
| **Đầy đủ (adequacy)** | Những yêu cầu trọng yếu có được đề cập, không mâu thuẫn và không để khoảng trống? | Bảng đối chiếu mục tiêu–điều khoản–yêu cầu |
| **Rõ ràng (clarity)** | Đối tượng áp dụng hiểu nghĩa vụ và điều kiện ngoại lệ giống nhau? | Phản hồi từ đội thực hiện, ví dụ kiểm thử được |
| **Khả thi (operability)** | Có chủ sở hữu, quy trình, công cụ, nguồn lực và điểm chuyển cấp? | RACI, SOP, control register, kế hoạch vận hành |
| **Triển khai (implementation)** | Control được thực thi ở nơi chính sách yêu cầu? | Cấu hình, mã, bản triển khai, danh mục tài sản |
| **Hiệu quả (effectiveness)** | Control thực sự đạt mục tiêu trong phạm vi đánh giá? | Test, review, audit, diễn tập, log và kết quả retest |
| **Quản trị (governance)** | Có phê duyệt, phiên bản, ngoại lệ, kỳ review và lịch sử quyết định? | Hồ sơ ban hành, decision log, exception register |

Các kết quả có thể khác nhau theo từng điều khoản. Một chính sách có thể vẫn đúng ở cấp quản trị nhưng cần cập nhật **standard/baseline** cho công nghệ mới. Một quy định khác có thể đã lỗi thời vì tài sản, kiến trúc hoặc nghĩa vụ áp dụng thay đổi.

### 2.1. Phân biệt ba lớp cần rà soát

**Lớp 1 – Nội dung chính sách:** mục tiêu, phạm vi, điều khoản, vai trò, yêu cầu bắt buộc và ngoại lệ có đúng, đầy đủ, dễ hiểu không?

**Lớp 2 – Chuyển hóa thành control:** yêu cầu có được ánh xạ tới tiêu chuẩn, cấu hình, quy trình và người chịu trách nhiệm? Có khoảng trống giữa quy định và hệ thống thực tế không?

**Lớp 3 – Hiệu quả được kiểm chứng:** control có hoạt động trên phiên bản/môi trường đang xét? Bằng chứng có đủ, hiện hành, đáng tin và bao phủ kịch bản trọng yếu không?

Chỉ **lớp 1** thường là đối tượng trực tiếp của *policy review*. Hai lớp còn lại cung cấp thông tin để kết luận về sự phù hợp và khả năng áp dụng, nhưng **policy review không thay thế một cuộc đánh giá control, pentest hoặc audit chuyên sâu**.

## 3. Khi nào cần rà soát chính sách?

Tổ chức nên kết hợp **chu kỳ rà soát được phê duyệt** với **rà soát theo sự kiện kích hoạt** (*event-driven review*).

### 3.1. Rà soát định kỳ

Ví dụ một tổ chức chọn kỳ xem xét **hằng năm** cho chính sách cấp tổ chức và kỳ ngắn hơn cho những chuẩn kỹ thuật thay đổi nhanh. Đây chỉ là **ví dụ quản trị**, không phải tần suất bắt buộc cho mọi loại tổ chức. Tần suất thực tế phải dựa vào mức rủi ro, mức biến động, yêu cầu áp dụng và thẩm quyền.

Một kỳ rà soát dù dẫn đến kết luận **“giữ nguyên nội dung”** vẫn phải ghi ai đã đánh giá, dựa trên thông tin nào, phạm vi gì và khi nào xem xét tiếp. Không chỉ thay ngày review mà không thực hiện đánh giá.

### 3.2. Các sự kiện cần xem xét trước kỳ hạn

| Sự kiện | Vì sao có thể ảnh hưởng chính sách? | Điều nên kiểm tra |
| --- | --- | --- |
| Thay đổi luật, nghĩa vụ hợp đồng hoặc yêu cầu khách hàng có áp dụng | Quy tắc đang có thể thiếu, thừa hoặc mâu thuẫn nghĩa vụ | Phạm vi áp dụng và ý kiến của pháp chế/compliance |
| Tài sản/dữ liệu mới hoặc thay đổi phân loại dữ liệu | Mức nhạy cảm và mục tiêu bảo vệ thay đổi | Điều khoản bảo vệ dữ liệu và giới hạn truy cập |
| Thêm API, cloud, nhà cung cấp, môi trường hay luồng dữ liệu | Ranh giới tin cậy và trách nhiệm khác trước | Policy, tiêu chuẩn và control bị ảnh hưởng |
| Thay đổi hệ thống định danh, quyền hoặc phương thức xác thực | Quy tắc truy cập cũ có thể không đủ | Chính sách quản lý truy cập, phân quyền và ngoại lệ |
| Sự cố nghiêm trọng hoặc near-miss | Lộ giả định sai hoặc control chưa hiệu quả | Điều khoản, trách nhiệm, kiểm thử, giám sát và quy trình phản ứng |
| Kết quả pentest/audit có phát hiện lặp lại | Khoảng trống kiểm soát hoặc yêu cầu không khả thi | Nguyên nhân gốc và hiệu lực triển khai |
| Nhiều ngoại lệ cùng chủ đề | Có thể có khoảng trống công nghệ, ngân sách hoặc quy tắc | Phân tích lý do và đánh giá rủi ro ngoại lệ |
| Thay đổi tổ chức, sáp nhập, phân quyền | Chủ thể chịu trách nhiệm và quyền phê duyệt thay đổi | Policy owner, risk owner, RACI, cấp chuyển tiếp |
| Threat intelligence mới phù hợp bối cảnh | Kịch bản tấn công hoặc khả năng phơi nhiễm có thể thay đổi | Threat model, yêu cầu và test có cần bổ sung? |

**Không phải sự kiện nào cũng đòi hỏi sửa chính sách.** Ví dụ, phát hiện một endpoint thiếu kiểm tra quyền có thể yêu cầu sửa mã và kiểm thử hồi quy trong khi điều khoản “phải kiểm tra quyền” vẫn hoàn toàn phù hợp.

### 3.3. Ưu tiên dựa trên rủi ro

Khi nhiều chính sách cùng đến kỳ, ưu tiên những chính sách liên quan tới:

- Tài sản và dữ liệu có tác động kinh doanh cao.
- Control trọng yếu có phát hiện nghiêm trọng hoặc tái diễn.
- Thay đổi kiến trúc hay mô hình truy cập lớn.
- Ngoại lệ lâu ngày, mất chủ sở hữu, bằng chứng hết hiệu lực.
- Nghĩa vụ bắt buộc có hiệu lực hoặc có thời hạn triển khai.

Có thể ưu tiên theo *mức ảnh hưởng × mức biến động × tình trạng bằng chứng*, nhưng các điểm định tính phải có tiêu chí; không biến thứ hạng thành phép đo rủi ro chính xác giả tạo.

## 4. Phân vai và thẩm quyền trong một kỳ rà soát

| Vai trò | Công việc thường thực hiện | Giới hạn cần làm rõ |
| --- | --- | --- |
| **Policy owner** | Lập kế hoạch, tổ chức rà soát, tổng hợp nhận xét, đề xuất phiên bản mới | Không tự phê duyệt nếu điều lệ giao quyền cho cấp khác |
| **CISO / security governance** | Đánh giá rủi ro, yêu cầu bảo mật, chất lượng control và điểm mù | Tư vấn, phản biện; quyền phê duyệt theo phân quyền |
| **Risk owner / đại diện nghiệp vụ** | Đánh giá tác động kinh doanh và residual risk của các phương án | Chấp nhận rủi ro chỉ trong quyền được giao |
| **Control owner** | Mô tả cách control đáp ứng yêu cầu, phạm vi, sai lệch, bằng chứng | Có trách nhiệm khắc phục control, không tự động được đổi chính sách |
| **Engineering / architecture / SRE** | Cung cấp thực trạng, khó khăn, bản build, kiểm thử, nhật ký, phụ thuộc | Không tự kết luận mọi chính sách đã được tuân thủ |
| **Pháp chế, bảo vệ dữ liệu, compliance** | Xác nhận nghĩa vụ thực tế có áp dụng và các ràng buộc | Không thay thế đánh giá kỹ thuật của control |
| **Assurance reviewer / kiểm toán độc lập** | Đánh giá chất lượng bằng chứng, quan sát về thiết kế và vận hành | Cần bảo vệ tính độc lập khi kiểm tra công việc của mình |
| **Người/cấp phê duyệt** | Phê duyệt sửa đổi, hiệu lực, chuyển tiếp, ngoại lệ theo quyền | Không được phê duyệt bỏ qua nghĩa vụ bắt buộc |

### 4.1. RACI minh họa

*R = Responsible (thực hiện), A = Accountable (chịu trách nhiệm cuối cùng), C = Consulted (tham vấn), I = Informed (thông báo).* Ma trận dưới đây cần điều chỉnh theo điều lệ thực tế.

| Hoạt động | Policy owner | Cấp phê duyệt | Security/governance | Control owner/kỹ thuật | Risk owner | Audit độc lập |
| --- | --- | --- | --- | --- | --- | --- |
| Lập phạm vi và thu thập phản hồi | **A/R** | I | C | C | C | C |
| Đánh giá tính phù hợp và dự thảo sửa | **A/R** | I | R | C | C | C |
| Cung cấp bằng chứng thực thi control | C | I | C | **A/R** | I | C |
| Đánh giá độc lập trong kỳ audit (nếu có) | C | I | C | C | I | **A/R** |
| Phê duyệt phiên bản chính sách mới | R | **A** | C | C | C | I |
| Triển khai thay đổi control theo chính sách mới | C | I | C | **A/R** | C | I |
| Quyết định chấp nhận residual risk thuộc quyền risk owner | C | I | C | C | **A/R** | I |
| Theo dõi kỳ rà soát tiếp theo | **A/R** | I | C | I | I | I |

Một số hoạt động có thể có nhiều người *R* nhưng nên xác định rõ **một chủ thể A**. Với thay đổi quan trọng, audit có thể được tham vấn về tính kiểm chứng nhưng không nên tự phê duyệt chính sách mà chính bộ phận đó sẽ đánh giá độc lập.

## 5. Chuẩn bị hồ sơ đầu vào có thể truy vết

Một kỳ rà soát cần một **ảnh chụp phạm vi và thông tin tại thời điểm đánh giá**, thay vì chỉ tập trung vào bản Word/PDF.

### 5.1. Hồ sơ quản trị

- Chính sách hiện hành: ID, phiên bản, ngày hiệu lực, người phê duyệt, chủ sở hữu, kỳ review, nơi công bố.
- Các standard, baseline, procedure và tài liệu liên kết.
- Lịch sử thay đổi và biên bản những quyết định quan trọng.
- Danh sách ngoại lệ: phạm vi, lý do, risk owner, người phê duyệt, hạn, control bù trừ.
- Trách nhiệm và đường chuyển cấp theo điều lệ hiện hành.

### 5.2. Hồ sơ rủi ro và thay đổi

- Danh sách tài sản/dữ liệu và phạm vi sử dụng mới nhất.
- Risk register, threat model, yêu cầu bảo mật và mức chấp nhận rủi ro áp dụng.
- Những thay đổi đã/đang triển khai: API, hạ tầng, IAM, CI/CD, nhà cung cấp, vùng lưu dữ liệu.
- Sự cố, near-miss, phát hiện bảo mật, kết quả audit và bài học từ khắc phục.
- Thay đổi nghĩa vụ pháp lý/hợp đồng **được bộ phận có trách nhiệm xác nhận có áp dụng**.

### 5.3. Bằng chứng thực thi và chất lượng control

| Nguồn | Dùng để trả lời | Giới hạn khi sử dụng |
| --- | --- | --- |
| Sơ đồ thiết kế và security review | Control được thiết kế như thế nào, đáp ứng yêu cầu gì? | Không tự chứng minh cấu hình production đúng |
| Cấu hình, mã, IaC, PR, artifact | Biện pháp đã được triển khai vào thành phần/phiên bản nào? | Có thể khác trạng thái thực tế |
| Integration/security tests | Hành vi được phép và bị từ chối có đúng? | Chỉ hỗ trợ những kịch bản đã chạy |
| Pentest và vulnerability assessment | Đường khai thác và điểm yếu nào được phát hiện? | Phụ thuộc phạm vi, thời điểm và năng lực kiểm thử |
| Log, metrics, cảnh báo, kết quả diễn tập | Control hoạt động thế nào khi vận hành và phục hồi? | Không có cảnh báo không chứng minh không có threat |
| Audit, đánh giá độc lập | Có phát hiện hoặc kết luận nào trong phạm vi được đánh giá? | Không mở rộng kết luận tự động ra mọi môi trường |
| Ticket sửa lỗi và kết quả retest | Sai lệch đã được xử lý và xác minh đến đâu? | Ticket đóng không đủ nếu thiếu kiểm thử lại |

**Metadata quan trọng** với mỗi bằng chứng: nguồn, người/công cụ tạo, ngày giờ, môi trường, phiên bản, hệ thống áp dụng, phạm vi, kết quả, liên kết và người review. Cần giới hạn quyền truy cập, che dữ liệu nhạy cảm và lưu trữ theo chính sách hồ sơ của tổ chức.

### 5.4. Phân loại điều “đã biết” và “chưa biết”

Nên gắn trạng thái:

- **Verified:** đã có bằng chứng phù hợp để hỗ trợ kết luận trong phạm vi.
- **Partially verified:** đã kiểm chứng một phần nhưng chưa bao phủ các hệ thống/đường truy cập còn lại.
- **Unverified:** chưa có bằng chứng hoặc bằng chứng không còn hiện hành.
- **Not applicable:** có lý do, phạm vi và căn cứ đã được chấp nhận rằng yêu cầu không áp dụng.
- **Nonconforming:** có bằng chứng cho thấy một yêu cầu không được đáp ứng.

**Unverified không đồng nghĩa Nonconforming hoặc Compliant.** Đó là tình trạng thiếu cơ sở kết luận; tùy rủi ro có thể cần hành động khẩn cấp bổ sung bằng chứng.

## 6. Quy trình rà soát chính sách từ đầu đến cuối

### Bước 1. Xác lập mục tiêu, phạm vi và baseline phiên bản

Định danh chính sách đang xem xét, **phiên bản chính thức**, nhóm tài sản, tổ chức, hệ thống, loại dữ liệu và thời kỳ có hiệu lực. Phân biệt phạm vi rà soát chính sách cấp tổ chức với phạm vi lấy mẫu hệ thống để đánh giá việc thực thi.

Ví dụ:

- **Policy ID:** POL-ACCESS-001.
- **Phiên bản đang hiệu lực:** 2.3.
- **Phạm vi:** hệ thống xử lý dữ liệu khách hàng.
- **Trigger:** bổ sung endpoint xuất dữ liệu và thay đổi hệ thống định danh.
- **Mục tiêu:** xác định điều khoản phân quyền còn phù hợp hay cần bổ sung chuẩn/test.

Nếu chỉ có bằng chứng của ba ứng dụng, không thể kết luận toàn bộ mười ứng dụng đã thực thi chính sách.

### Bước 2. Đối chiếu mục tiêu và nghĩa vụ hiện tại

Hỏi mỗi điều khoản đang bảo vệ tài sản nào, giải quyết tình huống rủi ro nào, có bắt nguồn từ yêu cầu kinh doanh hoặc nghĩa vụ bắt buộc nào, và các giả định trước đây có còn đúng không.

Một số kết quả có thể là:

- **Giữ nguyên:** yêu cầu vẫn cần thiết và đúng mức bảo vệ.
- **Làm rõ:** quy tắc đúng nhưng cách diễn đạt mơ hồ.
- **Bổ sung:** có rủi ro hoặc đối tượng mới chưa được bao phủ.
- **Đổi phạm vi:** tổ chức/sản phẩm mới cần đưa vào hoặc loại trừ có căn cứ.
- **Sửa hoặc thay thế:** điều khoản không còn phù hợp, xung đột hoặc không đáp ứng mục tiêu.
- **Thu hồi:** chính sách trùng lặp hoặc không còn áp dụng, phải có phương án chuyển giao yêu cầu còn cần thiết.

Không coi mong muốn “dễ triển khai hơn” là lý do đủ để hạ mức bảo vệ khi chưa đánh giá rủi ro và thẩm quyền.

### Bước 3. Kiểm tra cấu trúc, câu chữ và mâu thuẫn

Mỗi điều khoản nên rõ:

1. **Ai/điều gì** phải tuân thủ: hệ thống, loại tài khoản, nhóm dữ liệu?
2. **Hành vi bắt buộc hoặc cấm:** dùng từ nhất quán như *phải, không được, chỉ khi*.
3. **Phạm vi và thời điểm:** mọi request, thay đổi sản xuất, chu kỳ review hay tình huống cụ thể?
4. **Quan hệ với chuẩn khác:** đã viện dẫn đúng tài liệu và phiên bản/chủ quản chưa?
5. **Ngoại lệ:** có điều kiện, thẩm quyền và thời hạn rõ không?
6. **Khả năng kiểm chứng:** có thể đưa ra tiêu chí đạt hoặc không đạt không?

Ví dụ **mơ hồ**: “Hệ thống cần phân quyền phù hợp.”

Ví dụ **kiểm chứng được**: “Mọi thao tác đọc dữ liệu khách hàng qua API phải xác minh danh tính và quyền của chủ thể trên tài nguyên được yêu cầu; nếu không được cấp quyền, API không trả nội dung tài nguyên.”

Khi yêu cầu kỹ thuật thay đổi nhanh, nên giữ mục tiêu bắt buộc trong **policy** và đặt chi tiết ở **standard/baseline** được quản trị riêng. Không đưa mọi câu cấu hình framework vào chính sách cấp tổ chức nếu chúng không cần cố định.

### Bước 4. Lập ma trận truy vết yêu cầu–control–evidence

Với mỗi điều khoản trọng yếu, ghi:

| Điều khoản chính sách | Requirement có thể kiểm chứng | Control / owner | Evidence tối thiểu | Trạng thái |
| --- | --- | --- | --- | --- |
| Chỉ người có quyền được đọc dữ liệu khách hàng | Kiểm tra quyền trên **từng tài nguyên** ở mỗi đường đọc | Object authorization / Orders API owner | Test A/B, review query, kết quả bản build | Cần xác minh export API mới |
| Tài khoản quản trị phải có MFA theo tiêu chuẩn | Không có đường đăng nhập tương tác quản trị bỏ qua MFA trái quy định | IdP, application owners | Cấu hình và thử tài khoản quản trị | Đã xác minh một phần |
| Thao tác trọng yếu phải truy vết được | Event có actor, thời điểm, hành động và đối tượng phù hợp | Audit logging owner | Test audit event, cấu hình bảo vệ log | Đang đánh giá |
| Dữ liệu có khả năng phục hồi theo mục tiêu | Có backup và khôi phục đạt RTO/RPO đã phê duyệt | Platform/SRE owner | Kết quả diễn tập restore | Chưa đủ bằng chứng |

Các trạng thái trên **chỉ là ví dụ giả định**. Một yêu cầu có thể có nhiều control; một control có thể hỗ trợ nhiều điều khoản. Phải rõ phạm vi bên nào sở hữu phần dùng chung, phần tích hợp và nơi tạo kết luận tổng hợp.

### Bước 5. Đánh giá bằng chứng: thiết kế, triển khai và vận hành

Đối với control quan trọng, tách ba nhận định:

- **Design effectiveness:** nếu thực hiện như thiết kế, control có giải quyết threat/rủi ro mà policy nhắm tới không?
- **Implementation:** control đã được triển khai tại các thành phần và phiên bản trong phạm vi chưa?
- **Operating effectiveness:** control có thực sự vận hành như yêu cầu và được phát hiện sai lệch trong khoảng quan sát không?

Ví dụ, policy yêu cầu kiểm tra quyền trên tài nguyên. Tài liệu kiến trúc nói “dùng Spring Security” chỉ cho biết dự kiến có cơ chế bảo vệ; mã và cấu hình cho biết có triển khai; **test A đọc đơn B bị từ chối** cùng review các đường đọc mới chứng minh thêm về hành vi trong phạm vi test.

Không yêu cầu chính bản thân policy review chứng minh mọi control bằng tất cả phương pháp. Khi kiểm tra chuyên sâu vượt phạm vi, cần tạo **hành động assurance bổ sung** với owner và thời hạn.

### Bước 6. Phân loại phát hiện trước khi đề xuất giải pháp

Một phát hiện cần được xếp đúng loại để không giải quyết sai nguyên nhân:

| Nhóm phát hiện | Ví dụ | Hướng xử lý chính |
| --- | --- | --- |
| **Policy gap** | Chính sách chưa nhắc việc bảo vệ dữ liệu qua API export | Bổ sung/làm rõ điều khoản và yêu cầu liên quan |
| **Policy conflict** | Hai chính sách có điều khoản cấp quyền mâu thuẫn | Thống nhất cấp ưu tiên và sửa tài liệu |
| **Implementation gap** | Policy yêu cầu phân quyền; endpoint mới không kiểm tra | Sửa mã/cấu hình, bổ sung test và retest |
| **Evidence gap** | Control có nhưng không có test hoặc bằng chứng từ production | Thiết kế đánh giá, thu thập bằng chứng hợp lệ |
| **Ownership gap** | Không rõ ai quản lý authorization của service dùng chung | Cập nhật RACI, control register và bàn giao |
| **Exception governance gap** | Ngoại lệ không có hạn hoặc thiếu phê duyệt đúng quyền | Xem lại/thu hồi ngoại lệ, chuyển cấp và xử lý rủi ro |
| **Outdated reference** | Policy trỏ tới baseline đã bị thay thế | Sửa liên kết, kiểm tra ảnh hưởng và công bố phiên bản |

Một hệ thống có thể có **nhiều loại gap** cùng lúc. Chẳng hạn, chuẩn phân quyền quá chung (policy/standard gap), endpoint không kiểm tra quyền (implementation gap) và thiếu test (evidence gap). Mỗi gap cần người xử lý và tiêu chí đóng riêng.

### Bước 7. Đánh giá tác động, chọn phương án và trình phê duyệt

Khi đề xuất sửa chính sách, cần nêu:

- Lý do, bằng chứng và kịch bản rủi ro liên quan.
- Điều khoản hiện tại và dự thảo thay đổi, kèm giải thích **tác động đối với người thực thi**.
- Danh sách tài sản, dịch vụ, bên thứ ba và quy trình chịu ảnh hưởng.
- Nghĩa vụ áp dụng và sự nhất quán với các policy/standard khác.
- Chi phí, phụ thuộc, mức ưu tiên, thời hạn chuyển đổi.
- Residual risk của thời gian chuyển tiếp, biện pháp bù trừ và cấp phê duyệt phù hợp.
- Cách kiểm tra thực thi và chứng minh yêu cầu mới đã được đáp ứng.

**Chính sách chưa được phê duyệt không trở thành bản chính thức chỉ vì đã sửa trong repository.** Người hoặc cấp có quyền phải xác nhận theo cơ chế quản trị của tổ chức.

### Bước 8. Phê duyệt, công bố và quản lý chuyển tiếp

Khi chính sách thay đổi:

1. Ghi **người phê duyệt, ngày hiệu lực, phiên bản và lịch sử thay đổi**.
2. Cập nhật nguồn chính thức; đánh dấu bản cũ hết hiệu lực theo quy trình.
3. Xác định nhóm chịu ảnh hưởng và kênh truyền thông/đào tạo.
4. Cập nhật standard, baseline, procedure, control register, tài liệu thiết kế và yêu cầu kiểm thử liên quan.
5. Lập kế hoạch chuyển tiếp rõ người làm, hạn, phụ thuộc và cách xử lý hệ thống cũ.
6. Kiểm soát ngoại lệ hợp lệ trong quá trình chuyển đổi; không tự gia hạn vô thời hạn.
7. Đặt kỳ xem xét tiếp theo hoặc trigger đánh giá lại.

Nếu kết luận **không sửa văn bản**, vẫn ghi biên bản review, bằng chứng xem xét và quyết định giữ nguyên cùng các hành động khắc phục control (nếu có).

### Bước 9. Theo dõi thực thi và kiểm chứng sau rà soát

Kết thúc review không có nghĩa các thay đổi đã có hiệu lực vận hành. Theo dõi:

- Các yêu cầu mới đã được ánh xạ tới control và owner chưa?
- Bản sửa đã được triển khai trên hệ thống/vùng cần thiết chưa?
- Kiểm thử và audit có kiểm chứng đúng tiêu chí, đúng bản phát hành không?
- Những phát hiện nào còn mở, vì sao, có được chuyển cấp đúng thời hạn?
- Risk owner đã có đủ thông tin và thẩm quyền để ra quyết định về residual risk chưa?
- Những giả định của review có cần thay đổi dựa vào bằng chứng mới không?

Đây là điểm nối trở lại chương trình **security assurance liên tục**: các thay đổi chính sách dẫn đến thay đổi control, rồi cần **bằng chứng xác minh** trước khi nâng mức tin cậy hoặc đóng phát hiện.

## 7. Quy trình quyết định: sửa policy hay sửa control?

~~~mermaid
flowchart TD
    A["Bắt đầu kỳ rà soát: phạm vi và phiên bản"] --> B["Tập hợp rủi ro, yêu cầu và bằng chứng"]
    B --> C{"Chính sách còn phù hợp, rõ và đủ?"}
    C -- "Không" --> D["Đề xuất sửa policy / standard, đánh giá tác động"]
    C -- "Có" --> E["Ánh xạ yêu cầu tới control và owner"]
    D --> F["Trình phê duyệt theo đúng thẩm quyền"]
    F --> G["Ban hành, thông báo và chuyển tiếp"]
    G --> E
    E --> H{"Có bằng chứng hiệu quả control?"}
    H -- "Chưa đủ" --> I["Yêu cầu test/review/audit bổ sung"]
    I --> H
    H -- "Có nhưng không đạt" --> J["Ghi phát hiện, giảm thiểu, sửa control"]
    J --> K["Retest và cập nhật rủi ro"]
    K --> H
    H -- "Đạt trong phạm vi" --> L["Kết luận có giới hạn và cập nhật record"]
    L --> M["Theo dõi thay đổi, ngoại lệ, kỳ review tiếp"]
    M --> A
~~~

Trong tình huống có tác động có thể nghiêm trọng, **thiếu bằng chứng không có nghĩa được tiếp tục không hành động**; cần cân nhắc biện pháp giảm thiểu tạm thời hoặc chuyển cấp ngay. Sơ đồ mô tả logic quản trị, không thay thế kế hoạch ứng cứu sự cố khi có nguy cơ đang diễn ra.

## 8. Ví dụ chuyên sâu: rà soát Access Control Policy cho Orders API Java/Spring Boot

### 8.1. Bối cảnh thay đổi

Một công ty có chính sách truy cập dữ liệu khách hàng:

> “Dữ liệu khách hàng chỉ được truy xuất bởi các chủ thể đã được xác thực và có quyền phù hợp với tài nguyên được yêu cầu.”

Dịch vụ **Orders API** viết bằng **Java/Spring Boot** đang có endpoint đọc từng đơn hàng:

~~~http
GET /api/orders/841
Authorization: Bearer <token-cua-user-A>
~~~

Nhóm sản phẩm bổ sung một endpoint **xuất hàng loạt đơn hàng** để phục vụ báo cáo. Trong buổi review, một kỹ sư nhận thấy control phân quyền ở endpoint đọc đơn đơn lẻ được kiểm tra, nhưng luồng export chưa có test chứng minh không trả đơn của khách hàng khác.

Thông tin này mới chứng minh **evidence gap**; cần kiểm thử/học cách service lọc dữ liệu để xác định liệu có **implementation gap** hay không.

### 8.2. Phân tích từng lớp

| Lớp rà soát | Câu hỏi | Nhận định ban đầu |
| --- | --- | --- |
| **Policy** | Yêu cầu “chỉ chủ thể có quyền” có còn đúng với API export không? | Vẫn đúng về mục tiêu; có thể cần làm rõ mọi đường đọc kể cả batch/export |
| **Standard** | Tiêu chí kiểm tra quyền với truy vấn hàng loạt có rõ chưa? | Cần bổ sung tiêu chí cho từng bản ghi hoặc toàn tập kết quả theo chính sách |
| **Implementation** | Export có lọc dữ liệu theo danh tính/quyền không? | **Chưa xác minh** cho đến khi review và chạy test |
| **Evidence** | Có test A export dữ liệu của B bị từ chối hoặc lọc đúng không? | Thiếu bằng chứng trên phiên bản mới |
| **Risk** | Nếu có truy cập chéo, hậu quả gì? | Có thể lộ dữ liệu nhiều khách hàng; cần đánh giá phạm vi và impact |
| **Owner** | Ai giải quyết? | Orders API owner điều phối test/sửa; risk owner chịu trách nhiệm xử lý residual risk |

Một review chất lượng **không vội sửa chính sách thành “cho phép export không kiểm tra quyền”** để tránh phát hiện. Đội cần xác minh và, nếu chính sách đang thiếu rõ, cập nhật standard hoặc điều khoản tương ứng.

### 8.3. Control và test cần kiểm chứng

Một control phù hợp cho endpoint đọc đơn đơn lẻ là truy vấn với điều kiện giới hạn theo chủ thể đã được xác thực:

~~~java
@Service
public class OrderReadService {
    private final OrderRepository orders;
    private final CurrentCustomer currentCustomer;

    public OrderReadService(OrderRepository orders,
                            CurrentCustomer currentCustomer) {
        this.orders = orders;
        this.currentCustomer = currentCustomer;
    }

    @Transactional(readOnly = true)
    public OrderView readOne(long orderId) {
        long customerId = currentCustomer.customerId();

        return orders.findByIdAndCustomerId(orderId, customerId)
                .map(OrderView::from)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đây là **đoạn mã minh họa**, không phải chương trình hoàn chỉnh; các kiểu OrderRepository, CurrentCustomer, OrderView cần triển khai thực tế. **CurrentCustomer** phải lấy danh tính từ context xác thực đã kiểm chứng, không tin customer ID do client tùy ý gửi. Phải có quy tắc rõ cho vai trò được ủy quyền. Việc trả 403 hay 404 khi thiếu quyền tùy theo chính sách API; trong mọi trường hợp không được tiết lộ dữ liệu ngoài quyền.

**Điểm thiếu đối với export:** một query riêng trả về danh sách có thể không dùng cùng hàm readOne. Vì vậy phải áp dụng điều kiện quyền **cho toàn bộ tập kết quả** và kiểm tra khi phân trang, lọc và xuất file. Một control cho endpoint đơn lẻ **không chứng minh** đường export đạt.

Ma trận kiểm tra gợi ý:

| Test case | Kết quả kỳ vọng | Bằng chứng cần lưu |
| --- | --- | --- |
| A đọc đơn A | Trả dữ liệu theo đúng quyền | Kết quả test được phép |
| A đọc đơn B | Không trả dữ liệu đơn B | Kết quả test âm |
| A export danh sách thuộc A | Chỉ trả bản ghi A được xem | Kết quả test với tập dữ liệu hỗn hợp |
| A export khi dữ liệu chứa đơn B | Không có bản ghi hay trường nhạy cảm của B | Kết quả nội dung file, đã che dữ liệu thật |
| Role quản trị được ủy quyền | Chỉ xem đúng scope theo chính sách riêng | Test positive/negative cho role |
| Token không hợp lệ/hết hạn | Request bị từ chối | Test xác thực |
| Chính sách quyền thay đổi | Kết quả truy vấn phản ánh quyền đúng theo quy tắc | Test hồi quy |
| Bản build được triển khai | Test/cấu hình tương ứng đúng phiên bản, môi trường | Build ID, run ID, thời điểm, người review |

### 8.4. Khi kiểm thử cho thấy vấn đề

Giả sử **test giả định** xác nhận A xuất được đơn hàng B. Nhóm phải:

1. Ghi phát hiện có phiên bản, endpoint, test run và mức phơi nhiễm đã được xác nhận.
2. Đánh giá rủi ro với risk owner; xem cần vô hiệu hóa export/hoãn ra mắt hoặc giới hạn phạm vi hay không.
3. Giao kỹ thuật sửa quyền truy vấn/định dạng kết quả; rà soát export tương tự ở dịch vụ khác.
4. Bổ sung test âm và kiểm tra hồi quy; chạy lại trên bản sửa trong môi trường phù hợp.
5. Cập nhật control register, risk register và bằng chứng kiểm chứng.
6. Quyết định giữ nguyên hoặc làm rõ policy/standard trên căn cứ đã thu thập.
7. Chỉ đóng phát hiện khi đạt tiêu chí xác minh; chuyển cấp rủi ro còn lại ngoài thẩm quyền.

**Phân biệt kết luận:** policy có thể vẫn phù hợp; việc triển khai export **không tuân thủ** policy; và tiêu chuẩn kiểm thử export có thể thiếu chi tiết. Ba kết luận dẫn đến **ba hành động khác nhau**.

### 8.5. Hồ sơ review minh họa

~~~yaml
review_id: "POL-REVIEW-DEMO-010"
policy_id: "POL-ACCESS-DEMO"
policy_title: "Access Control Policy"
review_scope: "Orders API va endpoint export moi"
policy_version_under_review: "2.3"
review_type:
  - "EVENT_DRIVEN"
  - "PERIODIC_IF_DUE"
review_trigger: "Them endpoint export du lieu"
review_owner: "Nguoi so huu policy truy cap"
status: "IN_REVIEW"
evidence:
  - ref: "ARCH-DEMO-EXPORT"
    purpose: "Xac minh luong export va boundary"
  - ref: "TEST-DEMO-AUTHZ-EXPORT"
    purpose: "Test tai khoan A/B voi du lieu hon hop"
    validation_status: "PENDING"
findings:
  - id: "GAP-DEMO-01"
    type: "EVIDENCE_GAP"
    description: "Chua co test cho export tren build moi"
    action_owner: "Orders API team"
    closure_criteria: "Retest quyen xuat du lieu tren ban duoc trien khai"
recommendation:
  policy: "Giu muc tieu phan quyen, xem xet lam ro pham vi batch/export"
  standard: "Bo sung test rule cho tung ban ghi va file export"
  control: "Xac minh truoc, sua neu phat hien control thieu"
decision:
  state: "NOT_APPROVED"
  approver: null
  effective_date: null
next_review_trigger: "Co ket qua test hoac thay doi quy tac phan quyen"
~~~

Mẫu này **không phải bằng chứng từ một hệ thống thật**. Trạng thái **IN_REVIEW, PENDING, NOT_APPROVED** cố ý tránh gây hiểu nhầm rằng đã kiểm tra và phê duyệt. Hồ sơ thực tế cần có ngày giờ, người đánh giá, phiên bản, kết quả thực thi có thể truy vết, quyết định của cấp có quyền và nơi lưu trữ bảo vệ thích hợp.

## 9. Xử lý ngoại lệ trong kỳ rà soát

Ngoại lệ (*exception/waiver*) có thể xuất hiện khi hệ thống cũ chưa đáp ứng chính sách trong một thời gian. Cần phân biệt:

- **Ngoại lệ hợp lệ:** được người có thẩm quyền phê duyệt, có đánh giá rủi ro, phạm vi, thời hạn, điều kiện, control bù trừ và lịch tái đánh giá.
- **Sai lệch chưa được phê duyệt:** hệ thống không đáp ứng nhưng chưa có quyết định hợp lệ; vẫn là vấn đề phải xử lý/chuyển cấp.
- **Bằng chứng thiếu:** chưa rõ có đáp ứng hay không; cần điều tra/kiểm thử, không tự đánh dấu ngoại lệ hoặc tuân thủ.
- **Yêu cầu không áp dụng:** cần bằng chứng và lý do về phạm vi; không chỉ ghi “N/A” để giảm số phát hiện.

Trong kỳ review, kiểm tra mỗi ngoại lệ:

1. Chính sách/điều khoản nào bị lệch; asset và hệ thống nào chịu ảnh hưởng?
2. Ai là **risk owner**? Ai phê duyệt theo phân quyền?
3. Giả định về threat, mức phơi nhiễm và residual risk có còn đúng?
4. Control bù trừ có bằng chứng hiệu quả và hoạt động đúng phạm vi?
5. Ngoại lệ còn hiệu lực đến khi nào; có đang gia hạn liên tục không?
6. Có kế hoạch đưa hệ thống về tuân thủ, owner, milestone và tiêu chí retest không?
7. Có nghĩa vụ bắt buộc không thể được miễn trừ bằng quyết định nội bộ không?

Nếu một điều khoản dẫn tới ngoại lệ ở nhiều hệ thống, cần xem **nguyên nhân gốc**: yêu cầu bất khả thi về kỹ thuật, thiếu nguồn lực, standard quá hẹp hay quản lý triển khai chưa tốt. Không nên tự hạ chính sách nếu chưa chứng minh giảm mức bảo vệ là phù hợp với rủi ro và nghĩa vụ.

## 10. Chỉ số đo chất lượng rà soát

Chỉ đo “100% chính sách đã review” là chưa đủ. Các chỉ số nên giúp tìm vấn đề và kiểm tra **kết quả sau quyết định**.

| Chỉ số | Diễn giải | Giới hạn |
| --- | --- | --- |
| Tỷ lệ policy đến hạn được rà soát và có hồ sơ hợp lệ | Số policy có review record đầy đủ / số policy đến hạn | Không chứng minh control đang hiệu quả |
| Tỷ lệ điều khoản trọng yếu được ánh xạ tới control/owner | Đo mức độ triển khai trách nhiệm và phạm vi | Có ánh xạ trên giấy chưa có nghĩa đã triển khai |
| Tỷ lệ control trọng yếu có bằng chứng còn hiệu lực | Đo khả năng đưa kết luận assurance | Phải xét đúng môi trường, phiên bản, scope và claim |
| Thời gian từ trigger đến quyết định review | Giám sát khả năng phản ứng với thay đổi | Review nhanh mà thiếu bằng chứng có thể không có giá trị |
| Tỷ lệ hành động sau review được **xác minh hoàn tất** | Đo việc đưa kết luận thành sửa đổi thực tế | Không tính đóng ticket nhưng thiếu retest |
| Số ngoại lệ quá hạn/chưa được tái đánh giá | Cho thấy khoảng trống quản trị còn tồn tại | Phải xem rủi ro và điều kiện, không chỉ đếm |
| Số phát hiện tái diễn liên quan điều khoản cũ | Gợi ý thiếu hiệu quả ở thiết kế, triển khai hoặc đào tạo | Không mặc định mọi lỗi tái diễn do policy sai |
| Tỷ lệ policy sửa được truyền thông đúng đối tượng | Kiểm tra người thực thi có biết yêu cầu mới | Đã gửi email không chứng minh hiểu và áp dụng đúng |

Ví dụ minh họa: trong kỳ có **12** chính sách đến hạn, **10** có hồ sơ rà soát hợp lệ. Tỷ lệ hoàn thành review là **10/12 = 83,3%**. Điều này **không có nghĩa 83,3% hệ thống an toàn**. Hai chính sách chưa review có thể liên quan các control trọng yếu nhất; nhóm nên báo cả mức rủi ro, ngoại lệ, phát hiện và hành động tồn đọng.

### 10.1. Thế nào là “review hoàn tất”?

Nên định nghĩa tối thiểu:

- Có phiên bản tài liệu, phạm vi, ngày review và những người đánh giá.
- Có danh sách nguồn dữ liệu/rủi ro/thay đổi đã xem.
- Có kết luận rõ **giữ nguyên, sửa, thay, thu hồi** hoặc **chờ bằng chứng**, cùng lý do.
- Nếu sửa, có quyết định và phê duyệt đúng thẩm quyền.
- Có backlog triển khai, owner, hạn và tiêu chí xác minh.
- Có nơi lưu biên bản/bằng chứng và kỳ/trigger review tiếp theo.

Khi **thiếu bằng chứng quyết định**, nên giữ trạng thái **chưa hoàn tất** hoặc ghi rõ hạn chế thay vì chỉ cập nhật trường ngày review.

## 11. Các sai lầm thường gặp

### 11.1. Đổi ngày rà soát nhưng không phân tích

Chỉ thay “Next review” hoặc “Reviewed on” khiến hồ sơ trông đầy đủ nhưng không phản ánh thay đổi rủi ro. **Khắc phục:** lưu input, kết luận theo từng nhóm điều khoản và người xem xét.

### 11.2. Coi việc compliance checklist đạt là assurance đầy đủ

Một checklist chứng minh một số bước thủ tục được thực hiện, nhưng có thể không bao phủ lỗi phân quyền nghiệp vụ hay control đang hoạt động. **Khắc phục:** đánh giá thiết kế và vận hành control với bằng chứng phù hợp.

### 11.3. Sửa policy để che giấu implementation gap

API không tuân thủ là vấn đề của hệ thống; đổi câu chính sách để hợp thức hóa hành vi yếu đi có thể làm tăng rủi ro. **Khắc phục:** phân loại gap, yêu cầu sửa control hoặc trình phân tích điều chỉnh có căn cứ và thẩm quyền.

### 11.4. Không có người chịu trách nhiệm hoặc đúng quyền phê duyệt

Cuộc họp có nhiều người tham gia nhưng không ai quyết định và không ai khắc phục. **Khắc phục:** ghi rõ policy owner, control owner, risk owner, action owner và approval authority.

### 11.5. Bỏ qua các hệ thống mới, nhánh phụ và nhà cung cấp

Chỉ review ứng dụng chính mà bỏ qua API export, worker, service-to-service, hệ thống cũ có thể khiến mức độ tuân thủ bị đánh giá quá cao. **Khắc phục:** đối chiếu danh mục tài sản, luồng dữ liệu, ranh giới tin cậy và danh mục nhà cung cấp; nêu phạm vi mẫu kiểm tra.

### 11.6. Ngoại lệ hết hạn nhưng không đánh giá lại

Việc gia hạn bằng email hoặc ticket không đủ khi quy chế đòi hỏi phê duyệt của người có quyền và bằng chứng control bù trừ. **Khắc phục:** có exception register, trigger hết hạn, kiểm chứng điều kiện và chuyển cấp.

### 11.7. Tuyên bố tuân thủ dựa trên kết quả test cũ

Test của build trước hoặc môi trường staging có thể không phản ánh cấu hình production. **Khắc phục:** gắn bằng chứng với build, môi trường, phạm vi và các thay đổi buộc retest.

### 11.8. Không đóng vòng phản hồi từ audit và sự cố

Phát hiện lặp lại dù chính sách đã sửa nhiều lần. **Khắc phục:** kiểm tra nguyên nhân gốc, khả năng thực thi của standard, owner, test hồi quy, nguồn lực và giám sát thực tế.

### 11.9. Nhầm phê duyệt nội bộ với quyền miễn trừ nghĩa vụ pháp lý

Một cuộc họp hoặc chữ ký không tự cho phép tổ chức bỏ qua luật hoặc cam kết bắt buộc. **Khắc phục:** xác nhận nghĩa vụ với bộ phận có trách nhiệm và chuyển cấp khi yêu cầu vượt quyền.

## 12. Checklist thực hành cho người rà soát

- [ ] Đã xác định **policy ID, bản đang hiệu lực, owner, người phê duyệt** và ngày review.
- [ ] Mục đích, hệ thống, môi trường, tài sản và phạm vi rà soát được ghi rõ.
- [ ] Đã xem risk register, threat model, thay đổi kiến trúc và sự cố/phát hiện quan trọng.
- [ ] Đã xác nhận nghĩa vụ hợp đồng/pháp lý **thực sự áp dụng** với bộ phận liên quan.
- [ ] Các yêu cầu bắt buộc có đối tượng, phạm vi và tiêu chí kiểm chứng rõ.
- [ ] Đã kiểm tra xung đột, trùng lặp hoặc tham chiếu standard/baseline hết hiệu lực.
- [ ] Các điều khoản trọng yếu được ánh xạ tới control, owner và tiêu chí đánh giá.
- [ ] Có bằng chứng về **thiết kế, triển khai và vận hành** trong phạm vi phù hợp.
- [ ] Đã phân loại policy gap, implementation gap, evidence gap và ownership gap.
- [ ] Bằng chứng có nguồn, ngày, phiên bản, môi trường và phạm vi rõ ràng.
- [ ] Ngoại lệ có thẩm quyền, thời hạn, rủi ro, control bù trừ và kế hoạch khắc phục.
- [ ] Có quyết định giữ/sửa/thay/thu hồi chính sách dựa trên phân tích có căn cứ.
- [ ] Nếu sửa, có phê duyệt, bản chính thức, kế hoạch chuyển tiếp và thông báo.
- [ ] Mọi hành động có owner, thời hạn và **tiêu chí xác minh**.
- [ ] Đã xác định review tiếp theo hoặc trigger đánh giá lại khi có thay đổi.
- [ ] Hồ sơ, biên bản và bằng chứng được lưu đúng quyền và thời hạn áp dụng.

Checklist hỗ trợ nhất quán, **không thể tự thay thế** đánh giá độc lập hoặc kết quả kiểm thử đối với control rủi ro cao.

## 13. Câu hỏi tự kiểm tra

1. Tại sao rà soát chính sách không chỉ là chỉnh sửa văn bản hoặc cập nhật ngày?
2. Hãy phân biệt **policy gap**, **implementation gap** và **evidence gap** qua ví dụ API đọc đơn hàng.
3. Khi nào nên rà soát ngoài chu kỳ? Hãy nêu ba thay đổi kiến trúc hoặc vận hành có thể làm policy không còn phù hợp.
4. Vì sao báo cáo CI “100% test PASS” chưa đủ để kết luận điều khoản phân quyền được đáp ứng?
5. Nếu chỉ có bằng chứng của một số ứng dụng, cách diễn đạt kết luận review như thế nào để không suy rộng quá phạm vi?
6. Một ngoại lệ hết hạn nhưng chưa có retest; policy owner và risk owner cần làm gì?
7. Ai có quyền phê duyệt chính sách mới? Control owner có tự chấp nhận residual risk hay không?
8. Rà soát thấy policy vẫn đúng nhưng 3 dịch vụ không áp dụng control. Cần quyết định gì và những ai chịu trách nhiệm?
9. Trường hợp nào phải sửa standard/baseline thay vì nội dung policy cấp tổ chức?
10. Sau khi policy được phê duyệt mới, bằng chứng nào cần thu thập để chứng minh các control đã đáp ứng yêu cầu?
11. Một chính sách không thay đổi sau review có được coi là hoàn thành không? Cần những hồ sơ gì?
12. Vì sao tỷ lệ “90% policy được review” không có nghĩa “hệ thống an toàn 90%”?

## 14. Tổng kết

**Rà soát chính sách bảo mật** là việc **xác minh chính sách còn phù hợp, đủ rõ, thực thi được và được quản trị đúng quyền**, dựa trên thay đổi rủi ro, kiến trúc, nghĩa vụ và **bằng chứng của các security controls**. Quy trình chất lượng phải phân biệt **sai sót của văn bản** với **lỗi triển khai control** và **thiếu bằng chứng**; đưa ra quyết định giữ nguyên, sửa hoặc thay thế đúng thẩm quyền; quản lý ngoại lệ, chuyển tiếp và theo dõi khắc phục đến khi **được kiểm thử/xác minh lại**. Trong chương trình **security assurance liên tục**, mỗi kỳ rà soát là một vòng phản hồi giúp yêu cầu bảo mật, kiểm thử, audit và vận hành bám sát hệ thống thực tế.
