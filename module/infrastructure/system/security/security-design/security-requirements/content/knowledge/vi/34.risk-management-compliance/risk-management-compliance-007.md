# Authorize — Phê duyệt vận hành dựa trên rủi ro bảo mật

## 1. Authorize giải quyết vấn đề gì?

Một hệ thống có thể vượt qua kiểm thử chức năng nhưng vẫn chưa đủ cơ sở để đưa vào vận hành: còn lỗ hổng, chưa chứng minh được khả năng phục hồi, hoặc đang xử lý dữ liệu ngoài phạm vi đã đánh giá. Đội dự án cần một quyết định có người chịu trách nhiệm về những rủi ro còn lại.

Trong chương **Risk management và compliance**, **Authorize** là hoạt động quyết định có cho phép hệ thống vận hành hoặc sử dụng hay không dựa trên rủi ro đã được phân tích. Trong NIST Risk Management Framework (RMF), bước này gắn việc chấp nhận rủi ro an ninh và quyền riêng tư với trách nhiệm của người có thẩm quyền. Tham khảo định nghĩa và phạm vi tại [NIST SP 800-37 Rev. 2, mục 3.6](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=88).

Đối với thiết kế yêu cầu bảo mật, Authorize là nơi kiểm tra xem chuỗi lập luận sau có đủ sức thuyết phục hay chưa:

**Mục tiêu bảo vệ → kịch bản đe dọa → yêu cầu đo được → biện pháp triển khai → bằng chứng đánh giá → rủi ro còn lại → quyết định vận hành.**

Ví dụ, yêu cầu “hệ thống phải an toàn” không giúp người phê duyệt ra quyết định. Yêu cầu “mọi API đọc hồ sơ phải kiểm tra tenant của người gọi; các ca kiểm thử truy cập chéo tenant phải bị từ chối và không trả dữ liệu hồ sơ” tạo ra đối tượng có thể kiểm chứng.

Sau bài học, người học cần có khả năng:

- Phân biệt phê duyệt vận hành với xác thực và phân quyền ở thời điểm xử lý yêu cầu.
- Chuẩn bị hồ sơ đủ để một người có thẩm quyền hiểu và quyết định về rủi ro.
- Nối yêu cầu xác thực, phân quyền, bảo vệ dữ liệu, logging và phục hồi với bằng chứng cụ thể.
- Ghi rõ phạm vi, điều kiện, trách nhiệm và thời điểm xem xét lại quyết định.
- Biến điều kiện phê duyệt thành hoạt động kiểm soát được thực hiện trong vận hành.

## 2. Phân biệt các nghĩa gần nhau của “authorization”

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Authentication — xác thực | Chủ thể đang tương tác là ai? | Người quản trị đăng nhập qua IdP và hoàn thành MFA |
| Access authorization — phân quyền truy cập | Chủ thể được làm hành động gì trên tài nguyên nào? | Nhân viên nhân sự của tenant A chỉ được đọc hồ sơ thuộc tenant A |
| Security authorization — phê duyệt dựa trên rủi ro | Có chấp nhận rủi ro khi vận hành hệ thống trong phạm vi đã nêu không? | Cho phép vận hành bản phát hành đã đánh giá với chức năng xuất dữ liệu hàng loạt bị vô hiệu hóa |
| Release approval — phê duyệt phát hành | Bản phát hành đã đáp ứng điều kiện triển khai của tổ chức chưa? | Hoàn thành kiểm thử, kế hoạch triển khai, trực vận hành và phương án quay lui |
| Compliance review — xem xét tuân thủ | Các nghĩa vụ và yêu cầu áp dụng đã được đáp ứng, chứng minh hoặc xử lý đúng cơ chế chưa? | Có bằng chứng cho yêu cầu lưu giữ, xóa và giới hạn người truy cập dữ liệu |

Một quy trình phát hành có thể yêu cầu cả phê duyệt vận hành dựa trên rủi ro lẫn phê duyệt thay đổi. Hai quyết định có thể nằm trong cùng một công cụ nhưng phải xác định được người có thẩm quyền cho từng việc.

Bài này tập trung vào **security authorization**. Các cơ chế phân quyền API vẫn rất quan trọng vì chúng là một phần của các kiểm soát cần được đánh giá trước khi phê duyệt.

## 3. Authorize đứng ở đâu trong vòng đời?

RMF gồm các bước Prepare, Categorize, Select, Implement, Assess, Authorize và Monitor. Authorize sử dụng kết quả đánh giá; Monitor cung cấp thông tin mới để tiếp tục xem xét khả năng chấp nhận rủi ro. Cấu trúc này được trình bày trong [NIST SP 800-37 Rev. 2](https://csrc.nist.gov/pubs/sp/800/37/r2/final).

~~~mermaid
flowchart LR
    P[Prepare] --> C[Categorize]
    C --> S[Select]
    S --> I[Implement]
    I --> A[Assess]
    A --> R[Authorize]
    R --> M[Monitor]
    M --> E{Thay đổi hoặc rủi ro mới?}
    E -->|Có| S
    E -->|Tiếp tục theo dõi| M
~~~

Sơ đồ chỉ thể hiện mạch chính. Trong thực tế, việc cập nhật phạm vi hoặc bằng chứng có thể khiến nhóm quay lại nhiều bước khác nhau.

Theo [mục 3.6 của NIST SP 800-37 Rev. 2](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=88), Authorize có năm nhiệm vụ:

| Mã nhiệm vụ RMF | Nội dung | Kết quả cần có |
| --- | --- | --- |
| R-1 | Authorization Package | Hồ sơ được tập hợp để trình phê duyệt |
| R-2 | Risk Analysis and Determination | Nhận định về rủi ro trong bối cảnh tổ chức |
| R-3 | Risk Response | Cách ứng phó với rủi ro được xác định |
| R-4 | Authorization Decision | Quyết định cho phép hoặc từ chối |
| R-5 | Authorization Reporting | Quyết định và thông tin rủi ro được báo cáo đến các bên cần biết |

Các mã R-1 đến R-5 là mã nhiệm vụ của RMF. Những mã như REQ-AUTH-01 hoặc RISK-EXPORT trong ví dụ phía dưới là mã minh họa riêng của bài học.

Không nên để đến sát ngày phát hành mới tìm người ký. Ngay khi đặc tả yêu cầu, đội dự án đã cần biết tiêu chí nào sẽ chặn vận hành, ai có quyền chấp nhận rủi ro và bằng chứng nào phải được tạo.

## 4. Ai chịu trách nhiệm về quyết định?

Trong RMF, **Authorizing Official (AO)** là người có thẩm quyền đưa ra quyết định chấp nhận rủi ro. Việc chuẩn bị, điều phối và phân tích có thể có người hỗ trợ; trách nhiệm chấp nhận rủi ro tường minh thuộc AO và không được ủy quyền cho người khác theo [NIST SP 800-37 Rev. 2, nhiệm vụ R-4](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=92).

Bảng dưới đây là cách phân công thực hành cho một đội phát triển; tên chức danh cụ thể phụ thuộc tổ chức.

| Vai trò | Trách nhiệm trong quy trình | Đầu ra minh họa |
| --- | --- | --- |
| Người có thẩm quyền phê duyệt | Cân nhắc rủi ro và quyết định trong phạm vi thẩm quyền | Quyết định có xác nhận, phạm vi và điều kiện |
| Chủ hệ thống | Tập hợp hồ sơ, giải thích phạm vi, tổ chức thực hiện điều kiện | Hồ sơ hệ thống và kế hoạch xử lý tồn đọng |
| Chủ nghiệp vụ hoặc chủ dữ liệu | Giải thích tác động nghiệp vụ, mức nhạy cảm và nhu cầu xử lý dữ liệu | Đánh giá tác động và giới hạn sử dụng |
| Nhóm bảo mật và quyền riêng tư | Phân tích đe dọa, rà soát yêu cầu, hỗ trợ đánh giá rủi ro | Nhận định về kiểm soát và rủi ro còn lại |
| Người đánh giá kiểm soát | Xác minh hiệu lực kiểm soát bằng phương pháp và bằng chứng phù hợp | Kết quả đạt, không đạt hoặc chưa đủ bằng chứng |
| Đơn vị cung cấp kiểm soát dùng chung | Cung cấp thông tin về kiểm soát mà hệ thống kế thừa | Phạm vi bảo vệ của IdP, KMS hoặc nền tảng logging |
| Đội vận hành | Duy trì cấu hình, giám sát, ứng phó và phục hồi | Runbook, cảnh báo và kết quả diễn tập |
| Pháp chế hoặc phụ trách tuân thủ | Làm rõ nghĩa vụ và cơ chế ngoại lệ được phép | Đối chiếu nghĩa vụ với bằng chứng và điểm chưa đáp ứng |

Chức danh CISO, CTO hoặc trưởng bộ phận không tự động đồng nghĩa với quyền phê duyệt mọi hệ thống. Tổ chức cần chỉ định thẩm quyền phù hợp với mức tác động, loại dữ liệu và phạm vi rủi ro.

Người đánh giá xác nhận trạng thái kiểm soát; người phê duyệt quyết định khả năng chấp nhận rủi ro. Kết quả kiểm thử “đạt” không thay thế quyết định chịu trách nhiệm về rủi ro vận hành.

## 5. Chuẩn bị authorization package

### 5.1. Phần hồ sơ cốt lõi

Theo [NIST CSRC — Authorization package](https://csrc.nist.gov/glossary/term/authorization_package), hồ sơ cung cấp thông tin cần thiết cho người có thẩm quyền quyết định; các thành phần cốt lõi gồm bản tóm tắt điều hành, kế hoạch an ninh và quyền riêng tư, kết quả đánh giá kiểm soát, cùng kế hoạch hành động và mốc hoàn thành liên quan.

Với đội phát triển, có thể tổ chức hồ sơ theo bảng sau. Đây là cách triển khai minh họa, có thể tích hợp vào công cụ quản trị sẵn có thay vì tạo nhiều tài liệu rời.

| Thành phần | Nội dung giúp ra quyết định |
| --- | --- |
| Tóm tắt điều hành | Hệ thống phục vụ ai, lợi ích vận hành, rủi ro đáng chú ý, quyết định đang đề nghị |
| Phạm vi và baseline | Thành phần, môi trường, phiên bản, cấu hình bảo mật, dữ liệu và tích hợp nằm trong đánh giá |
| Kế hoạch bảo vệ | Yêu cầu, kiểm soát được triển khai, kiểm soát kế thừa và trách nhiệm giữa các bên |
| Báo cáo đánh giá | Phương pháp, môi trường, thời điểm, kết quả, giới hạn của kiểm thử và phát hiện |
| Bằng chứng hỗ trợ | Kết quả kiểm thử, cấu hình, log đã xử lý dữ liệu nhạy cảm, biên bản diễn tập |
| Danh sách rủi ro còn lại | Kịch bản gây hại, tác động, khả năng xảy ra, độ tin cậy của nhận định |
| POA&M | Việc cần làm, người chịu trách nhiệm, nguồn lực, hạn hoàn thành và tiêu chí đóng |
| Kế hoạch giám sát | Tín hiệu cần theo dõi, tần suất, ngưỡng xử lý, người phản ứng |
| Đề nghị phê duyệt | Phạm vi cho phép, điều kiện ràng buộc, lịch xem xét và sự kiện kích hoạt xem xét lại |

**POA&M — Plan of Action and Milestones** là kế hoạch hành động và các mốc hoàn thành. Một dòng “sẽ sửa ở sprint sau” chưa cung cấp đủ thông tin để theo dõi.

Ví dụ một mục POA&M:

- Phát hiện: tác vụ xuất dữ liệu bất đồng bộ có nhánh lỗi chưa đáp ứng thời hạn xóa tệp.
- Việc xử lý: bổ sung cơ chế xóa đối soát, kiểm thử nhánh lỗi và kiểm tra tệp tồn.
- Chủ trì: nhóm nền tảng dữ liệu; người xác minh: người đánh giá kiểm soát.
- Hạn hoàn thành: ngày được thống nhất trong quyết định.
- Tiêu chí đóng: kiểm thử các nhánh thành công, lỗi, retry và gián đoạn đều đáp ứng yêu cầu xóa.
- Điều kiện trong thời gian chờ: chức năng bị vô hiệu hóa trong phạm vi được phê duyệt, cấu hình bị giám sát.

### 5.2. Phải gắn bằng chứng với đúng đối tượng được phê duyệt

Mỗi bằng chứng nên trả lời được:

1. Đang kiểm chứng yêu cầu và kịch bản nào?
2. Được tạo trên phiên bản, cấu hình và môi trường nào?
3. Được tạo khi nào, bằng cách nào và ai xác nhận?
4. Có giới hạn, giả định hoặc khu vực chưa đánh giá nào?
5. Thay đổi nào sẽ khiến bằng chứng cần được xem xét lại?

Kết quả kiểm thử trên môi trường một tenant không đủ chứng minh khả năng cách ly nhiều tenant. Bản chụp cấu hình backup không chứng minh dữ liệu có thể được khôi phục. Kết quả của bản phát hành cũ cũng cần được phân tích tác động trước khi tái sử dụng.

Hồ sơ có thể chứa chi tiết lỗ hổng, cấu hình hạ tầng và thông tin riêng tư. Cần giới hạn người đọc, bảo vệ tính toàn vẹn và quản lý phiên bản. Tài liệu tóm tắt cho người quyết định có thể dẫn đến bằng chứng chi tiết được bảo vệ ở nơi phù hợp.

## 6. Truy vết từ rủi ro đến yêu cầu và kết quả đánh giá

Giả sử một hệ thống quản lý hồ sơ nhân sự phục vụ nhiều tenant, tích hợp IdP dùng chung, lưu tài liệu trong object storage, có chức năng xuất báo cáo và cơ chế backup.

Các ngưỡng trong bảng dưới đây là **giả định để học cách đặc tả**, không phải ngưỡng mặc định do NIST hay một quy định pháp luật áp đặt.

| Kịch bản rủi ro | Yêu cầu bảo mật có thể kiểm chứng | Bằng chứng cần có | Điểm quyết định |
| --- | --- | --- | --- |
| Chiếm tài khoản quản trị | REQ-AUTH-01: mọi phiên quản trị phải dùng MFA theo chính sách đã duyệt; không có luồng đăng nhập cục bộ bỏ qua | Kiểm thử các luồng đăng nhập, tài khoản khẩn cấp và cấu hình IdP | Luồng bỏ qua MFA phải được xử lý hoặc được kiểm soát đúng cơ chế riêng đã phê duyệt |
| Đọc hồ sơ tenant khác | REQ-TENANT-02: API danh sách, chi tiết, tìm kiếm, tải tệp và tác vụ nền phải thực thi giới hạn tenant | Kiểm thử âm với nhiều tenant, nhiều vai trò và truy cập trực tiếp object | Một đường đọc chéo tenant còn khai thác được làm vi phạm tiêu chí chặn của ví dụ |
| Lộ dữ liệu lưu trữ | REQ-DATA-03: cơ sở dữ liệu, tệp và backup dùng cơ chế mã hóa và chính sách khóa đã duyệt; quyền dùng khóa được giới hạn | Cấu hình thực tế, kiểm thử quyền dùng khóa, kiểm kê vị trí lưu dữ liệu | Mã hóa không thay thế kiểm soát truy cập vào ứng dụng và khóa |
| Không truy vết được sửa đổi đặc quyền | REQ-LOG-04: ghi chủ thể, tenant, hành động, tài nguyên, thời gian, kết quả và mã tương quan; không ghi token hay nội dung hồ sơ | Kiểm thử sự kiện thành công, bị từ chối và lỗi; thử tình huống mất đường truyền log | Khoảng trống logging và khả năng phát hiện phải được nêu rõ |
| Không phục hồi được sau sự cố | REQ-RECOVERY-05: RTO không quá 4 giờ, RPO không quá 1 giờ cho phạm vi dữ liệu đã định nghĩa | Diễn tập phục hồi có mốc thời gian, kiểm tra tính toàn vẹn và khả năng sử dụng | Chỉ “backup thành công” chưa đủ đáp ứng yêu cầu |
| Tệp xuất tồn quá lâu | REQ-RETENTION-06: tệp xuất tạm và các bản sao thuộc phạm vi phải được xóa trong 24 giờ | Kiểm thử nhánh lỗi, retry, tác vụ dọn dẹp và kiểm tra tồn lưu | Giới hạn thời gian phải có cơ sở nghiệp vụ và được đối chiếu nghĩa vụ áp dụng |

Với REQ-RECOVERY-05:

- **RTO — Recovery Time Objective** là mục tiêu về thời gian khôi phục hoạt động trong phạm vi đã thỏa thuận.
- **RPO — Recovery Point Objective** là mục tiêu về khoảng mất dữ liệu có thể chấp nhận, thể hiện bằng thời gian.

Khi ghi kết quả diễn tập, cần nêu điểm bắt đầu đo, điều kiện kết thúc và dữ liệu được kiểm tra. “Khôi phục database trong ba giờ” chưa cho biết toàn bộ dịch vụ, khóa giải mã và các phụ thuộc đã hoạt động trở lại hay chưa.

Một yêu cầu có thể có nhiều bằng chứng; một bằng chứng cũng có thể hỗ trợ nhiều yêu cầu. Tuy nhiên, liên kết phải chỉ rõ phần nào được chứng minh. Chẳng hạn, kiểm thử API trả 403 không chứng minh object storage đã ngăn truy cập bằng URL trực tiếp.

Các trạng thái đánh giá nên được phân biệt:

- **Đạt:** bằng chứng phù hợp hỗ trợ kết luận đáp ứng yêu cầu trong phạm vi đã đánh giá.
- **Không đạt:** quan sát cho thấy yêu cầu chưa được đáp ứng.
- **Chưa đủ bằng chứng:** chưa thể đưa ra kết luận tin cậy.
- **Không áp dụng:** có lý do và phạm vi rõ ràng được người có trách nhiệm xác nhận.

Không chuyển “chưa đủ bằng chứng” thành “đạt” chỉ để hoàn tất hồ sơ.

## 7. Phân tích rủi ro còn lại và lựa chọn cách ứng phó

### 7.1. Đọc phát hiện trong bối cảnh nghiệp vụ

**Rủi ro còn lại** là rủi ro vẫn tồn tại sau khi tính đến các biện pháp bảo vệ thực sự có hiệu lực. Để phân tích một phát hiện, cần xem xét:

- Tài sản và nhóm người có thể bị ảnh hưởng.
- Đường tiếp cận của tác nhân đe dọa và điều kiện cần để gây hại.
- Tác động đến bí mật, toàn vẹn, sẵn sàng và quyền riêng tư.
- Mức phơi nhiễm: nội bộ, Internet, số tenant, số người dùng, loại dữ liệu.
- Hiệu lực thực tế của kiểm soát chính và kiểm soát bù.
- Độ tin cậy của bằng chứng và các giả định chưa được kiểm chứng.
- Sự phụ thuộc vào hệ thống khác hoặc nhà cung cấp.

Điểm nghiêm trọng của một lỗ hổng là đầu vào hữu ích nhưng không tự quyết định rủi ro vận hành. Cùng một lỗi có thể gây hậu quả khác nhau giữa môi trường thử với dữ liệu tổng hợp và môi trường công khai chứa dữ liệu nhạy cảm.

Cũng không nên cộng hoặc nhân các mức định tính như “cao”, “trung bình”, “thấp” rồi coi kết quả là xác suất thống kê. Nếu dùng thang điểm nội bộ, cần giải thích ý nghĩa và giới hạn của thang.

### 7.2. So với tiêu chí chấp nhận của tổ chức

Tổ chức cần diễn đạt mức rủi ro sẵn sàng chấp nhận và giới hạn dung sai thành tiêu chí sử dụng được. Ví dụ minh họa:

- Không cho phép vận hành nếu còn đường truy cập chéo tenant đã được chứng minh khai thác được.
- Chưa cho xử lý dữ liệu thật khi chưa có bằng chứng phục hồi cho phạm vi dữ liệu thiết yếu.
- Chỉ xem xét giới hạn vận hành khi biện pháp giảm phơi nhiễm đã triển khai và được xác minh.
- Điểm chưa rõ có tác động lớn phải được điều tra thêm trước khi kết luận.

Đây là tiêu chí của tổ chức giả định, cần được quyết định trước và áp dụng nhất quán. Nhãn “critical” hay “high” từ một công cụ không phải quy tắc phê duyệt chung cho mọi hệ thống.

### 7.3. Chọn cách ứng phó

| Cách ứng phó | Cách thể hiện trong yêu cầu và quyết định |
| --- | --- |
| Giảm thiểu | Thêm hoặc sửa kiểm soát, kiểm thử lại và cập nhật rủi ro còn lại |
| Tránh | Không triển khai tính năng hoặc không xử lý loại dữ liệu tạo ra rủi ro |
| Chia sẻ hoặc chuyển giao một phần | Xác định trách nhiệm với bên cung cấp dịch vụ, hợp đồng hoặc bảo hiểm; đánh giá phần rủi ro tổ chức vẫn chịu |
| Chấp nhận | Người có thẩm quyền ghi nhận rủi ro cụ thể trong phạm vi và điều kiện được nêu |

Một WAF chưa được kiểm thử với kịch bản cần chặn không thể tự động được coi là biện pháp bù hiệu quả. Việc mua dịch vụ bên ngoài cũng không chứng minh mọi nghĩa vụ về dữ liệu đã được chuyển cho nhà cung cấp.

Trong quản trị tuân thủ, cần kiểm tra cơ chế ngoại lệ của chính yêu cầu đang áp dụng. Quyết định nội bộ về chấp nhận rủi ro không tự tạo ra quyền bỏ qua một nghĩa vụ bắt buộc. Nếu phạm vi nghĩa vụ chưa rõ, phải làm rõ trước khi coi điểm thiếu là có thể chấp nhận.

## 8. Ra quyết định và ghi rõ điều kiện

### 8.1. Các dạng quyết định trong RMF

[NIST SP 800-37 Rev. 2, Phụ lục F](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=160) phân biệt:

- **Authorization to Operate — ATO:** cho phép hệ thống vận hành.
- **Authorization to Use:** cho phép tổ chức sử dụng hệ thống trên cơ sở xem xét thông tin phê duyệt liên quan.
- **Common Control Authorization:** phê duyệt tập kiểm soát dùng chung để các hệ thống kế thừa.
- **Denial of Authorization:** từ chối phê duyệt.

ATO có thể kèm giới hạn, điều kiện và thời hạn thích hợp. Cách gọi nội bộ “phê duyệt có điều kiện” trong bài này chỉ mô tả một quyết định có ràng buộc; không tạo thêm một loại quyết định chuẩn của RMF.

Nếu hồ sơ còn thiếu, nhóm có thể yêu cầu bổ sung bằng chứng. Trạng thái “chờ bổ sung” của quy trình không được hiểu là đã có quyền đưa hệ thống vào vận hành.

### 8.2. Một quyết định cần cụ thể đến mức nào?

Người đọc quyết định phải xác định được:

1. Ai quyết định, với thẩm quyền nào và vào thời điểm nào?
2. Hệ thống, phiên bản, môi trường, cấu hình và dữ liệu nào thuộc phạm vi?
3. Hồ sơ và phiên bản bằng chứng nào làm cơ sở?
4. Rủi ro nào được chấp nhận; lý do chấp nhận là gì?
5. Điều kiện nào phải hoàn thành trước khi bắt đầu vận hành?
6. Điều kiện nào phải được duy trì trong khi vận hành?
7. Ai xử lý tồn đọng; hạn xử lý và tiêu chí hoàn tất là gì?
8. Khi nào xem xét lại, khi nào hết hiệu lực và sự kiện nào kích hoạt xử lý sớm?

Nội dung về quyết định, điều kiện, thời hạn hoặc tần suất xem xét và sự kiện kích hoạt được mô tả tại [NIST SP 800-37 Rev. 2, Phụ lục F — Authorization Decision Information](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=166).

Câu “đồng ý triển khai, nhóm bảo mật theo dõi thêm” không chỉ ra được rủi ro, phạm vi hay hành động cần thực hiện. Điều kiện có ích phải kiểm tra được, chẳng hạn: “chức năng xuất dữ liệu bất đồng bộ bị vô hiệu hóa; mọi thay đổi bật chức năng phải qua đánh giá và phê duyệt lại trước khi áp dụng”.

## 9. Ví dụ: phê duyệt một phạm vi vận hành giới hạn

### 9.1. Bối cảnh và kết quả đánh giá

Hệ thống nhân sự chuẩn bị chạy thử với 50 người dùng thuộc hai tenant. Cấu hình dự kiến cho phép xuất báo cáo bất đồng bộ.

Kết quả đánh giá giả định:

- REQ-AUTH-01 đạt trong các luồng quản trị đã xác định.
- REQ-TENANT-02 đạt trong phạm vi API, tải tệp và tác vụ nền đã đánh giá.
- REQ-DATA-03 và REQ-LOG-04 có bằng chứng phù hợp với baseline được đề nghị.
- REQ-RECOVERY-05 đạt: diễn tập đo được thời gian phục hồi dịch vụ 3 giờ 20 phút và khoảng mất dữ liệu 35 phút.
- REQ-RETENTION-06 không đạt cho chức năng xuất bất đồng bộ: một nhánh lỗi khiến tệp tồn 36 giờ thay vì giới hạn 24 giờ của ví dụ.

Nhóm không sửa kết quả cuối thành “đạt” để thuận lợi cho phát hành.

### 9.2. Thu hẹp phạm vi trước khi đề nghị phê duyệt

Nhóm đề xuất cấu hình chạy thử không có chức năng xuất bất đồng bộ. Trước khi trình quyết định, họ phải:

1. Vô hiệu hóa cả điểm gọi API lẫn tác vụ nền tương ứng.
2. Xử lý tệp xuất còn tồn và xác minh kết quả theo yêu cầu.
3. Kiểm thử rằng các đường gọi trực tiếp không tạo được tệp xuất.
4. Bổ sung cơ chế phát hiện thay đổi cấu hình bật lại chức năng.
5. Cập nhật phạm vi, mô hình đe dọa và bằng chứng theo cấu hình đã thu hẹp.

Phát hiện của REQ-RETENTION-06 vẫn mở đối với chức năng đầy đủ. Việc vô hiệu hóa chức năng làm giảm đường phơi nhiễm trong phạm vi chạy thử; nó không chứng minh chức năng đã đáp ứng yêu cầu xóa.

Rủi ro còn lại cần cân nhắc gồm khả năng cấu hình bị thay đổi trái quy trình, giới hạn độ bao phủ của kiểm thử và tác động nếu giới hạn chạy thử bị mở rộng.

### 9.3. Bản ghi quyết định minh họa

Các tên, thời gian và mã dưới đây là dữ liệu giả định phục vụ học tập.

~~~yaml
decision_id: AUTHZ-HR-PILOT-01
authorization_type: authorization_to_operate
scope:
  system: HR Portal
  environment: production-pilot
  release: 2.4.0
  configuration_baseline: hr-pilot-no-async-export-v1
  max_users: 50
  max_tenants: 2
  async_export_enabled: false
basis:
  assessment_report: ASSESS-HR-PILOT-v3
  evidence_manifest: EVIDENCE-HR-PILOT-v3
  risk_register: RISK-HR-PILOT-v2
risk_acceptance:
  risk_id: RISK-EXPORT-CONFIG-DRIFT
  rationale: >
    Chap nhan rui ro con lai cua pham vi pilot da thu hep,
    dua tren bang chung vo hieu hoa export va giam sat cau hinh.
preconditions:
  - Verify export API and workers are disabled
  - Verify cleanup of existing temporary export files
  - Verify configuration-change alert delivery
operating_conditions:
  - Do not enable asynchronous export
  - Do not add tenants or exceed the authorized user limit
  - Review configuration drift and security alerts daily
poam:
  item: POAM-HR-06
  owner: Data Platform Team
  due_at: "2027-02-10T18:00:00+07:00"
  closure: Retest all export cleanup scenarios and verify retention
effective_at: "2027-02-01T09:00:00+07:00"
review_at: "2027-02-08T09:00:00+07:00"
expires_at: "2027-02-15T18:00:00+07:00"
review_triggers:
  - Attempt to enable asynchronous export
  - Tenant-isolation control failure
  - Material change to identity, data scope, or storage
approver_role: Designated Authorizing Official
approval_record: Reference to authenticated approval record
~~~

Đây là cấu trúc nội dung minh họa. Trường ghi vai trò hoặc một chuỗi “approved” tự nó không chứng minh đã có phê duyệt. Hồ sơ thực tế phải liên kết đến bằng chứng xác nhận đúng người, đúng thẩm quyền và đúng phiên bản quyết định.

Thời điểm bắt đầu chỉ có ý nghĩa khi các điều kiện trước vận hành đã được đáp ứng. Hạn POA&M không phải thời điểm tự động bật lại chức năng. Sau khi sửa và kiểm thử, việc mở rộng phạm vi vẫn phải theo cơ chế thay đổi và phê duyệt đã quy định.

Nếu sửa lỗi không kịp, người phụ trách phải báo cáo trước hạn. Không tự gia hạn ngày hoặc coi sự im lặng là tiếp tục chấp nhận rủi ro.

## 10. Đưa điều kiện phê duyệt vào SDLC và vận hành

### 10.1. Tạo hồ sơ từ các hoạt động phát triển

Để hồ sơ không trở thành thủ tục dồn vào cuối dự án:

- Khi phân tích: ghi tài sản, nghĩa vụ, tác nhân đe dọa và mức tác động.
- Khi đặc tả: đặt mã yêu cầu, tiêu chí kiểm chứng và điều kiện chặn.
- Khi thiết kế: xác định ranh giới tin cậy, kiểm soát kế thừa và giả định phụ thuộc.
- Khi triển khai: lưu cấu hình và phiên bản kiểm soát cùng bản phát hành.
- Khi đánh giá: tạo bằng chứng liên kết với yêu cầu và baseline.
- Khi phê duyệt: tổng hợp kết quả thành một quyết định rõ phạm vi.
- Khi vận hành: duy trì điều kiện và phản hồi thông tin rủi ro mới.

Một nhóm có thể dùng kho tài liệu, công cụ GRC hoặc hệ thống quản lý thay đổi. Công cụ chỉ hữu ích nếu liên kết dữ liệu có thể kiểm tra và thông tin chưa bị lỗi thời.

### 10.2. Tự động kiểm tra điều kiện có thể đo được

Pipeline triển khai có thể kiểm tra bản ghi phê duyệt để ngăn triển khai ngoài phạm vi:

~~~text
1. Xác minh nguồn và tính toàn vẹn của quyết định.
2. Kiểm tra người phê duyệt có thẩm quyền cho phạm vi hệ thống.
3. Đối chiếu bản phát hành, môi trường và cấu hình với phạm vi cho phép.
4. Kiểm tra quyết định còn hiệu lực và chưa bị thu hồi.
5. Xác nhận các điều kiện trước triển khai đã hoàn tất.
6. Kiểm tra không có sự kiện đang yêu cầu xem xét lại chưa được xử lý.
7. Nếu phù hợp, tiếp tục quy trình triển khai đã được tổ chức cho phép.
~~~

Pipeline hỗ trợ thi hành quyết định. Nó không tự trở thành người chấp nhận rủi ro, và việc tất cả kiểm thử tự động đều xanh không đủ thay cho quyết định của người có thẩm quyền.

Một bản vá nhỏ cũng cần được xét theo mức tác động. Có thể tái sử dụng bằng chứng khi phạm vi liên quan vẫn phù hợp; thay đổi cơ chế xác thực, cách ly tenant hoặc lưu trữ dữ liệu thường đòi hỏi phân tích sâu hơn.

### 10.3. Giám sát điều kiện và xử lý vi phạm

| Điều kiện của ví dụ | Tín hiệu theo dõi | Phản ứng đã định trước |
| --- | --- | --- |
| Không bật xuất bất đồng bộ | Thay đổi cấu hình hoặc tác vụ xuất được kích hoạt | Chặn thay đổi nếu có thể, thông báo chủ hệ thống và yêu cầu xem xét phạm vi |
| Duy trì cách ly tenant | Phát hiện kiểm soát sai hoặc sự kiện truy cập chéo tenant | Kích hoạt ứng phó, cô lập phần ảnh hưởng và báo người có thẩm quyền |
| Không vượt quy mô chạy thử | Số người dùng và tenant được cấp quyền | Chặn mở rộng hoặc yêu cầu phê duyệt thay đổi trước khi cấp thêm |
| Giữ khả năng truy vết | Mất luồng log, thiếu sự kiện hoặc độ trễ vượt ngưỡng nội bộ | Điều tra, phục hồi logging và đánh giá tác động của khoảng trống |
| Hoàn thành POA&M | Trạng thái công việc, bằng chứng kiểm thử lại và hạn xử lý | Báo sớm nguy cơ trễ; xem xét điều kiện vận hành hoặc kết thúc phạm vi |
| Duy trì khả năng phục hồi | Lỗi backup, thay đổi khóa, kết quả kiểm tra phục hồi | Khắc phục phụ thuộc và đánh giá lại khả năng đáp ứng RTO/RPO |

Các hành động ngừng hoặc giới hạn hệ thống phải được quy định trong quyết định và runbook phù hợp. Cần tính đến an toàn nghiệp vụ, tính liên tục và cách bảo vệ dữ liệu khi thực hiện.

## 11. Ongoing authorization và xem xét lại

[NIST SP 800-37 Rev. 2, Phụ lục F](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=158) mô tả **ongoing authorization** là các quyết định tiếp theo về rủi ro và việc chấp nhận rủi ro, dựa trên thông tin giám sát và tần suất hoặc sự kiện đã xác định.

Cần phân biệt:

- **Continuous monitoring:** tạo và cập nhật thông tin về kiểm soát, cấu hình, mối đe dọa và trạng thái hệ thống.
- **Ongoing authorization:** người có thẩm quyền sử dụng thông tin đó để tiếp tục xác định và chấp nhận rủi ro.
- **Reauthorization:** thực hiện lại quyết định phê duyệt khi hoàn cảnh, thời hạn hoặc mức rủi ro yêu cầu.

Có dashboard giám sát không có nghĩa hệ thống tự động được phê duyệt vô thời hạn. Chuyển sang ongoing authorization cần chương trình giám sát đủ tin cậy và cơ chế quyết định được xác định rõ, theo [NIST SP 800-37 Rev. 2, phần điều kiện triển khai ongoing authorization](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf#page=168).

Với hệ thống trong ví dụ, các thay đổi sau nên được đánh giá theo quy trình đã chọn:

- Mở API ra Internet hoặc tích hợp với một đối tác mới.
- Thêm loại dữ liệu nhạy cảm hoặc mục đích sử dụng dữ liệu mới.
- Thay IdP, thay chính sách tenant hoặc cơ chế cấp quyền đặc quyền.
- Bật chức năng đang bị loại khỏi phạm vi phê duyệt.
- Phát hiện đường khai thác mới làm thay đổi nhận định rủi ro.
- Không duy trì được logging, backup hoặc chương trình giám sát đã cam kết.

Không phải mọi thay đổi đều cần làm lại toàn bộ hồ sơ. Cần phân tích tác động, xác định phần bằng chứng còn dùng được và trình đúng người theo quy trình. Những thay đổi vượt phạm vi hoặc làm rủi ro vượt giới hạn chấp nhận phải được xử lý trước khi tiếp tục dựa vào quyết định cũ.

## 12. Những sai sót làm quyết định mất giá trị

| Sai sót | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dựa vào báo cáo quét lỗ hổng | Bỏ sót lỗi nghiệp vụ, quyền riêng tư và khả năng phục hồi | Kết hợp bằng chứng theo từng yêu cầu và kịch bản gây hại |
| Dùng bằng chứng của bản khác mà không phân tích tác động | Không biết kiểm soát còn đúng hay không | Gắn bằng chứng với baseline và ghi lý do tái sử dụng |
| Ghi “chấp nhận mọi rủi ro còn lại” | Không xác định được điều gì đã được cân nhắc | Liệt kê rủi ro, phạm vi, lý do và điều kiện cụ thể |
| Gọi biện pháp dự kiến là kiểm soát có hiệu lực | Đánh giá thấp rủi ro hiện tại | Phân biệt trạng thái đã triển khai, đã kiểm chứng và còn kế hoạch |
| Dùng POA&M để né tiêu chí chặn | Hệ thống vận hành khi điều kiện bắt buộc chưa đạt | Áp dụng tiêu chí chặn và xử lý ngoại lệ đúng thẩm quyền |
| Cho rằng IdP được phê duyệt thì ứng dụng cũng đủ an toàn | Bỏ qua cấu hình tích hợp và kiểm soát riêng của ứng dụng | Đánh giá phần kế thừa, điều kiện sử dụng và phần hệ thống tự chịu trách nhiệm |
| Đổi phạm vi sau khi có chữ ký | Quyết định không còn khớp đối tượng vận hành | Kiểm soát thay đổi và xem xét quyết định trước khi mở rộng |
| Đồng nhất ATO với chứng nhận tuân thủ | Suy diễn vượt phạm vi quyết định | Đối chiếu từng nghĩa vụ với kết quả đánh giá tương ứng |
| Hết hạn nhưng tiếp tục chạy vì chưa ai phản đối | Không còn cơ sở phê duyệt hiện hành theo cơ chế đã chọn | Theo dõi hạn và thực hiện xem xét hoặc kết thúc theo điều kiện đã định |

## 13. Tiêu chí tự rà soát hồ sơ trước khi trình

Đây là bước kiểm tra sự sẵn sàng của hồ sơ, không thay thế đánh giá chuyên môn hoặc quyết định của người có thẩm quyền.

- [ ] Phạm vi chỉ rõ phiên bản, môi trường, dữ liệu, tenant, tích hợp và cấu hình.
- [ ] Các yêu cầu bảo mật quan trọng có tiêu chí đo được và liên kết tới rủi ro.
- [ ] Kết quả xác thực, phân quyền, dữ liệu, logging và phục hồi có bằng chứng phù hợp.
- [ ] Điểm không đạt và điểm chưa đủ bằng chứng được giữ nguyên ý nghĩa.
- [ ] Rủi ro còn lại nêu tác động, giả định, kiểm soát thực tế và giới hạn nhận định.
- [ ] Nghĩa vụ tuân thủ và cơ chế ngoại lệ liên quan đã được làm rõ.
- [ ] Người phê duyệt và thẩm quyền được xác định.
- [ ] Điều kiện trước vận hành, điều kiện duy trì và giới hạn phạm vi kiểm tra được.
- [ ] POA&M có chủ trì, hạn hoàn thành, nguồn lực và tiêu chí xác minh.
- [ ] Quyết định có lịch xem xét, cơ chế hiệu lực và sự kiện kích hoạt xử lý sớm.
- [ ] Đội vận hành biết hành động gì khi điều kiện không còn được duy trì.
- [ ] Hồ sơ và bằng chứng được bảo vệ, quản lý phiên bản và cung cấp đúng người.

## 14. Tài liệu tham khảo

- [NIST SP 800-37 Rev. 2 — trang công bố chính thức](https://csrc.nist.gov/pubs/sp/800/37/r2/final): bối cảnh RMF và mối liên hệ với vòng đời hệ thống.
- [NIST SP 800-37 Rev. 2 — toàn văn](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf): mục 3.6 về Authorize; Phụ lục F về hồ sơ, dạng quyết định và duy trì phê duyệt.
- [NIST CSRC Glossary — Authorization package](https://csrc.nist.gov/glossary/term/authorization_package): thành phần và mục đích của hồ sơ phê duyệt.
