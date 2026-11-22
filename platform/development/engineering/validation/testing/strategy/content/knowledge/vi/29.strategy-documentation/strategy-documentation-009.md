# Quản lý phiên bản, người rà soát và lịch cập nhật

Tài liệu chiến lược kiểm thử chỉ hữu ích khi phản ánh đúng sản phẩm, kiến trúc, rủi ro và cách làm việc hiện tại. Một chiến lược được viết tốt nhưng không được cập nhật có thể khiến nhóm kiểm thử ưu tiên sai, chạy những kiểm tra không còn phù hợp hoặc bỏ sót thay đổi quan trọng. Tài liệu không có chủ sở hữu, không ghi lịch sử thay đổi và không xác định người rà soát cũng khó được tin cậy khi cần đưa ra quyết định phát hành hoặc giải trình sau sự cố.

Quản lý phiên bản, người rà soát và lịch cập nhật tạo thành cơ chế duy trì độ tin cậy của tài liệu. Quản lý phiên bản cho biết nội dung nào đang có hiệu lực, thay đổi ra sao và có thể khôi phục hoặc đối chiếu phiên bản cũ như thế nào. Phân công người rà soát bảo đảm các nội dung được xem xét bởi đúng chuyên môn và người có thẩm quyền. Lịch cập nhật xác định thời điểm rà soát định kỳ và những sự kiện buộc tài liệu phải được xem xét sớm hơn.

Trong chiến lược kiểm thử, tài liệu cần được quản lý như một sản phẩm có vòng đời. Mỗi tài liệu quan trọng cần có mục đích, phạm vi, chủ sở hữu, người rà soát, trạng thái, phiên bản hoặc lịch sử thay đổi, ngày hiệu lực và điều kiện xem xét lại. Cơ chế này giúp nhóm biết tài liệu nào đang được áp dụng, ai chịu trách nhiệm và khi nào cần cập nhật.

## 1. Vì sao cần quản lý vòng đời tài liệu chiến lược?

Chiến lược kiểm thử thường liên quan đến nhiều nhóm và nhiều quyết định: phạm vi kiểm thử, tầng kiểm thử, môi trường, dữ liệu, công cụ, tiêu chí vào/ra, cách quản lý lỗi, chỉ số chất lượng và điều kiện phát hành. Các nội dung này thay đổi theo sản phẩm và tổ chức.

Một tài liệu không được quản lý có thể gặp các vấn đề:

- Nhiều bản sao cùng tồn tại và mỗi nhóm dùng một bản khác nhau.
- Không rõ bản nào đã được phê duyệt hoặc còn hiệu lực.
- Thay đổi quan trọng không có lý do hoặc người chịu trách nhiệm.
- Nội dung kỹ thuật được cập nhật nhưng quy trình liên quan vẫn cũ.
- Người rà soát không có chuyên môn phù hợp hoặc chỉ được thêm tên cho đủ thủ tục.
- Tài liệu đã quá hạn nhưng không ai nhận ra.
- Không thể xác định quyết định nào dựa trên phiên bản tài liệu nào.
- Một bản nháp bị hiểu nhầm là quy định đã có hiệu lực.
- Các ngoại lệ tạm thời không được xem xét lại và trở thành thông lệ.

Quản lý vòng đời giúp giảm các rủi ro này bằng cách tạo một nguồn thông tin có thể truy vết. Khi xảy ra sự cố, nhóm có thể biết chiến lược nào được áp dụng tại thời điểm đó, ai đã rà soát, quyết định nào được phê duyệt và nội dung nào đã thay đổi sau đó.

### Mục tiêu quản lý

Một cơ chế quản lý tốt cần bảo đảm:

1. Có một vị trí chính thức để tìm tài liệu hiện hành.
2. Mỗi tài liệu có chủ sở hữu chịu trách nhiệm về tính phù hợp.
3. Người rà soát được chọn theo nội dung và tác động.
4. Thay đổi có lý do, bằng chứng và lịch sử.
5. Trạng thái nháp, đang rà soát, đã phê duyệt và hết hiệu lực được phân biệt.
6. Tài liệu được xem xét theo lịch và theo sự kiện.
7. Phiên bản cũ vẫn có thể tra cứu khi cần đối chiếu.
8. Người sử dụng biết tài liệu nào áp dụng cho dự án, sản phẩm hoặc phiên bản nào.

## 2. Phân loại tài liệu và mức kiểm soát phù hợp

Không phải tài liệu nào cũng cần quy trình phê duyệt giống nhau. Một ghi chú làm việc của cá nhân không cần cùng mức kiểm soát với chiến lược kiểm thử cấp tổ chức hoặc tiêu chuẩn phát hành.

Có thể phân loại theo mức ảnh hưởng:

| Loại tài liệu | Ví dụ | Mức kiểm soát gợi ý |
|---|---|---|
| Chiến lược cấp tổ chức | Chính sách kiểm thử, nguyên tắc chất lượng, mô hình quản trị | Chủ sở hữu, rà soát liên chức năng, phê duyệt chính thức, lịch định kỳ |
| Chiến lược cấp sản phẩm/dự án | Phạm vi, tầng kiểm thử, môi trường, tiêu chí phát hành | Chủ sở hữu sản phẩm/kỹ thuật, test lead và nhóm phụ thuộc rà soát |
| Quy trình vận hành | Quy trình triage, quản lý test data, release gate | Chủ quy trình, người thực thi và nhóm vận hành rà soát |
| Hướng dẫn kỹ thuật | Cấu hình runner, cách chạy suite, hướng dẫn công cụ | Maintainer kỹ thuật, review theo thay đổi |
| Biểu mẫu và checklist | Test plan, risk register, release readiness checklist | Chủ sở hữu biểu mẫu, rà soát khi quy trình hoặc trường dữ liệu thay đổi |
| Ghi chú tham khảo | Bài học kinh nghiệm, ghi chú điều tra | Người viết và người phụ trách chủ đề; có thể không cần phê duyệt chính thức |

Mức kiểm soát nên tương xứng với hậu quả nếu nội dung sai hoặc lỗi thời. Tài liệu ảnh hưởng đến bảo mật, dữ liệu, tuân thủ hoặc quyền phát hành cần cơ chế rà soát chặt hơn tài liệu hướng dẫn một công cụ ít rủi ro.

### Phân biệt tài liệu chính thức và tài liệu tham khảo

Tài liệu chính thức quy định hoặc mô tả cách tổ chức cam kết thực hiện. Nó cần chủ sở hữu, trạng thái và quy trình phê duyệt rõ ràng. Tài liệu tham khảo hỗ trợ hiểu biết hoặc cung cấp ví dụ; nó không tự tạo ra nghĩa vụ nếu chưa được chỉ định là chuẩn áp dụng.

Hãy ghi rõ loại tài liệu ở phần đầu. Không nên để một trang wiki chứa nhiều ghi chú không có trạng thái khiến người đọc không biết nội dung nào là quy định và nội dung nào chỉ là gợi ý.

## 3. Thiết lập nguồn lưu trữ chính thức

Tài liệu cần có một vị trí chính thức để tránh nhiều bản sao cạnh tranh. Tùy tổ chức, nguồn chính có thể là repository Git, hệ thống quản lý tài liệu, wiki có kiểm soát phiên bản hoặc nền tảng quản trị chất lượng.

Dù dùng công cụ nào, cần xác định:

- Vị trí chuẩn để tìm bản hiện hành.
- Quyền đọc, sửa, phê duyệt và lưu trữ.
- Cách đề xuất thay đổi.
- Cách ghi lịch sử và so sánh phiên bản.
- Cách gắn tài liệu với sản phẩm, dự án hoặc release.
- Cách tìm bản cũ và xác định trạng thái hiệu lực.
- Cách sao lưu và khôi phục.
- Cách xử lý bản xuất ra PDF hoặc bản sao ngoại tuyến.

### Một nguồn chính, nhiều bản phân phối

Có thể có nhiều định dạng phân phối như Markdown, PDF hoặc bản in, nhưng cần chỉ định một nguồn có thẩm quyền. Bản PDF xuất ra nên ghi phiên bản, ngày tạo và đường dẫn đến nguồn chính. Nếu người dùng sửa bản PDF hoặc bản tải xuống, thay đổi đó không tự động cập nhật nguồn chính.

Không nên để các nhóm tự duy trì những bản sao độc lập mà không có quy trình đồng bộ. Nếu một nhóm cần bản địa hóa hoặc tùy biến, hãy xác định rõ nội dung nào kế thừa từ chuẩn chung, nội dung nào là phần bổ sung và ai chịu trách nhiệm đồng bộ.

### Cấu trúc lưu trữ có thể tìm kiếm

Một cấu trúc thư mục hoặc không gian tài liệu nên phản ánh cách người dùng tìm nội dung, chẳng hạn:

- Cấp tổ chức hoặc lĩnh vực.
- Sản phẩm hoặc dự án.
- Chủ đề như strategy, planning, execution, reporting.
- Loại tài liệu hoặc trạng thái.
- Lịch sử hoặc tài liệu đã hết hiệu lực.

Tránh tạo cấu trúc quá sâu hoặc dùng tên không có ý nghĩa với người sử dụng. Tài liệu nên có tiêu đề, mô tả ngắn, từ khóa và liên kết liên quan để tìm kiếm.

## 4. Xác định chủ sở hữu và vai trò liên quan

Mỗi tài liệu cần có một chủ sở hữu nội dung (document owner). Chủ sở hữu chịu trách nhiệm bảo đảm tài liệu có mục đích rõ, còn phù hợp và được rà soát đúng hạn. Việc một người viết tài liệu không đồng nghĩa người đó luôn là chủ sở hữu lâu dài.

### Các vai trò chính

- **Author (người soạn):** tạo hoặc đề xuất nội dung, giải thích thay đổi và cung cấp bằng chứng.
- **Document owner (chủ sở hữu):** chịu trách nhiệm cuối cùng về tính phù hợp, phạm vi và lịch rà soát.
- **Reviewer (người rà soát):** kiểm tra tính chính xác, đầy đủ, khả thi và tác động trong chuyên môn của mình.
- **Approver (người phê duyệt):** chấp nhận nội dung chính thức theo thẩm quyền được giao.
- **Maintainer (người duy trì):** cập nhật liên kết, metadata, định dạng, công cụ và các sửa đổi nhỏ được ủy quyền.
- **Reader/user (người sử dụng):** áp dụng tài liệu, phản hồi khi phát hiện nội dung sai hoặc khó thực hiện.
- **Records/document controller (người quản lý hồ sơ):** hỗ trợ kiểm soát trạng thái, lưu trữ, quyền truy cập và yêu cầu audit nếu tổ chức có vai trò này.

Trong nhóm nhỏ, một người có thể giữ nhiều vai trò. Tuy nhiên, với tài liệu rủi ro cao, nên có sự rà soát độc lập và người phê duyệt có thẩm quyền phù hợp.

### Trách nhiệm của chủ sở hữu

Chủ sở hữu cần:

1. Xác định mục đích, đối tượng và phạm vi áp dụng.
2. Chọn người rà soát có chuyên môn liên quan.
3. Đảm bảo các giả định và phụ thuộc được ghi rõ.
4. Xem xét ý kiến và xử lý bất đồng.
5. Đề xuất phê duyệt hoặc từ chối thay đổi.
6. Theo dõi lịch cập nhật và trigger ngoài lịch.
7. Xem xét tài liệu khi sản phẩm hoặc quy trình thay đổi.
8. Chuyển giao quyền sở hữu khi thay đổi vai trò.
9. Xác nhận tài liệu cũ được thay thế hoặc lưu trữ đúng cách.

Không nên gán chủ sở hữu cho một nhóm chung chung mà không có người điều phối. Nếu chủ sở hữu là một nhóm, cần chỉ định người đại diện chịu trách nhiệm theo dõi.

## 5. Chọn người rà soát theo nội dung và rủi ro

Người rà soát cần có đủ hiểu biết để đánh giá nội dung thuộc phạm vi của họ. Một tài liệu chiến lược kiểm thử có thể cần nhiều góc nhìn:

- Test lead hoặc QA manager: phạm vi, chiến lược, mức bao phủ và tính khả thi.
- Product owner hoặc business owner: luồng nghiệp vụ, mức ưu tiên và tác động người dùng.
- Technical lead hoặc architect: kiến trúc, phụ thuộc, khả năng tích hợp và rủi ro kỹ thuật.
- Developer/service owner: tính khả thi của test ở từng thành phần và khả năng hỗ trợ.
- DevOps/platform engineer: pipeline, runner, môi trường, observability và rollback.
- Security/privacy specialist: xác thực, phân quyền, dữ liệu, bí mật và yêu cầu bảo mật.
- Operations/SRE: vận hành, độ tin cậy, cảnh báo, khôi phục và readiness.
- Compliance/legal representative: yêu cầu hợp đồng, quy định và lưu trữ khi có liên quan.

Không cần mời tất cả vai trò vào mọi lần sửa. Hãy chọn người dựa trên phần thay đổi. Sửa lỗi chính tả có thể chỉ cần maintainer; thay đổi tiêu chí release gate có thể cần test lead, kỹ thuật, sản phẩm và người có thẩm quyền phát hành.

### Ma trận rà soát gợi ý

| Nội dung thay đổi | Người rà soát chính | Vai trò cần tham vấn |
|---|---|---|
| Phạm vi và ưu tiên kiểm thử | Test lead | Product owner, service owner |
| Tiêu chí vào/ra và release gate | QA manager hoặc release owner | Product, engineering, operations |
| Kiến trúc môi trường và pipeline | Platform/technical lead | Test automation, service owner |
| Test data và quyền truy cập | Data/security owner | QA, privacy, operations |
| Chiến lược bảo mật | Security lead | Architect, product, engineering |
| Performance và resilience | SRE/performance specialist | Architect, service owner |
| Chính sách và tuân thủ | Policy owner | Compliance, legal, security |
| Lịch và metadata tài liệu | Document owner | Maintainer, document controller |

Ma trận này là gợi ý. Cơ cấu thực tế cần phản ánh quyền quyết định của tổ chức. Người được hỏi ý kiến không nhất thiết là người có quyền phê duyệt.

## 6. Dùng RACI hoặc mô hình trách nhiệm tương đương

RACI giúp làm rõ ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai chỉ cần được thông báo.

- **R – Responsible:** trực tiếp thực hiện công việc.
- **A – Accountable:** chịu trách nhiệm cuối cùng và quyết định kết quả.
- **C – Consulted:** cung cấp ý kiến hai chiều trước quyết định.
- **I – Informed:** được thông báo sau hoặc trong quá trình thay đổi.

Ví dụ cho một tài liệu chiến lược kiểm thử:

| Hoạt động | Author | Document owner | Reviewer | Approver | Reader |
|---|---|---|---|---|---|
| Đề xuất thay đổi | R | A | C | I | C |
| Soạn nội dung | R | A | C | I | I |
| Rà soát chuyên môn | C | A | R | I | C |
| Xử lý ý kiến | R | A | C | I | I |
| Phê duyệt | I | R | C | A | I |
| Công bố phiên bản | R | A | I | I | I |
| Rà soát định kỳ | R | A | C | I | C |
| Lưu trữ bản cũ | R | A | I | I | I |

Mỗi hoạt động nên có một vai trò A rõ ràng. Nếu có nhiều người cùng được đánh dấu A, trách nhiệm cuối cùng có thể bị phân tán. Với tài liệu có yêu cầu độc lập, người soạn không nên tự phê duyệt thay đổi ảnh hưởng lớn mà không có review phù hợp.

## 7. Thiết kế quy ước phiên bản

Quy ước phiên bản cần giúp người đọc nhận biết mức độ thay đổi và truy xuất đúng bản. Không có một cách đánh số bắt buộc cho mọi tổ chức, nhưng cần thống nhất và áp dụng nhất quán.

### Phiên bản theo mức thay đổi

Có thể dùng cấu trúc MAJOR.MINOR.PATCH:

- **MAJOR:** thay đổi lớn về chính sách, phạm vi, trách nhiệm, tiêu chí hoặc cách áp dụng; có thể yêu cầu người dùng điều chỉnh quy trình.
- **MINOR:** bổ sung hoặc sửa nội dung có ý nghĩa nhưng không thay đổi nền tảng chính sách.
- **PATCH:** sửa lỗi nhỏ, liên kết, định dạng hoặc diễn đạt mà không làm thay đổi ý nghĩa.

Ví dụ:

- 1.0.0: phiên bản đầu tiên được phê duyệt.
- 1.1.0: bổ sung hướng dẫn kiểm thử contract và trách nhiệm owner.
- 1.1.1: sửa liên kết và lỗi chính tả.
- 2.0.0: thay đổi tiêu chí release gate và mô hình phê duyệt.

Đây là quy ước nội bộ gợi ý. Nếu tổ chức dùng revision number, ngày hiệu lực hoặc mã tài liệu, hãy ghi rõ cách ánh xạ giữa các giá trị.

### Không tăng phiên bản cho mọi thay đổi như nhau

Một sửa lỗi định dạng không cần được đối xử như thay đổi chính sách. Ngược lại, thay đổi tiêu chí chặn phát hành không nên được ghi như một sửa đổi nhỏ. Hãy mô tả mức ảnh hưởng, khả năng tương thích và hành động người sử dụng cần thực hiện.

### Phiên bản tài liệu và phiên bản sản phẩm

Hai loại phiên bản này phục vụ mục đích khác nhau:

- Phiên bản tài liệu cho biết nội dung chiến lược đã thay đổi ra sao.
- Phiên bản sản phẩm cho biết phần mềm hoặc release nào chịu ảnh hưởng.

Một tài liệu có thể áp dụng cho nhiều phiên bản sản phẩm; một release có thể tham chiếu nhiều tài liệu. Hãy ghi phạm vi hiệu lực rõ, ví dụ sản phẩm, dự án, nhánh phát triển, loại release hoặc ngày áp dụng.

### Ngày hiệu lực và ngày rà soát

Ngày tài liệu được sửa không nhất thiết là ngày nó có hiệu lực. Có thể một chính sách được phê duyệt hôm nay nhưng chỉ áp dụng từ đầu chu kỳ tiếp theo. Ghi riêng:

- Ngày tạo.
- Ngày cập nhật nội dung.
- Ngày phê duyệt.
- Ngày hiệu lực.
- Ngày rà soát gần nhất.
- Ngày rà soát tiếp theo.

Các mốc này giúp tránh áp dụng nhầm chính sách chưa có hiệu lực hoặc tiếp tục dùng bản đã hết hiệu lực.

## 8. Ghi nhận lịch sử thay đổi có thể truy vết

Mỗi thay đổi có ý nghĩa cần trả lời: thay đổi gì, vì sao, ai đề xuất, ai rà soát, ai phê duyệt và khi nào có hiệu lực.

Một change log có thể có các trường:

| Trường | Nội dung |
|---|---|
| Version | Phiên bản tài liệu |
| Date | Ngày thay đổi hoặc hiệu lực |
| Change summary | Nội dung thay đổi |
| Reason | Lý do và bối cảnh |
| Impact | Nhóm, quy trình hoặc release bị ảnh hưởng |
| Author | Người đề xuất/soạn |
| Reviewer | Người rà soát |
| Approver | Người phê duyệt |
| Reference | Ticket, incident, ADR hoặc yêu cầu liên quan |
| Status | Draft, approved, effective, superseded |

Ví dụ:

| Version | Ngày hiệu lực | Thay đổi | Lý do |
|---|---|---|---|
| 1.0.0 | 2026-01-15 | Ban hành chiến lược kiểm thử ban đầu | Thiết lập cách kiểm thử cho sản phẩm |
| 1.1.0 | 2026-04-01 | Bổ sung contract test và owner cho API | Thêm dịch vụ tích hợp |
| 1.1.1 | 2026-04-08 | Sửa liên kết và thuật ngữ | Chuẩn hóa tài liệu |
| 2.0.0 | 2026-09-01 | Thay đổi release gate và cơ chế phê duyệt | Điều chỉnh quy trình phát hành |

Ngày và phiên bản trong bảng chỉ minh họa cách ghi. Dữ liệu thực tế phải lấy từ lịch sử thay đổi đã được phê duyệt.

### Ghi lý do thay đổi

Một dòng “updated testing section” không đủ để hiểu tác động. Lý do nên liên hệ với sự kiện hoặc bằng chứng, chẳng hạn:

- Thay đổi kiến trúc hoặc ranh giới dịch vụ.
- Incident hoặc defect đã xảy ra.
- Thay đổi mức rủi ro hoặc yêu cầu khách hàng.
- Kết quả đo lường cho thấy chính sách hiện tại không hiệu quả.
- Công cụ hoặc nền tảng hết hỗ trợ.
- Kết quả audit hoặc yêu cầu tuân thủ.
- Thay đổi vai trò, tổ chức hoặc quy trình phát hành.

Liên kết đến ticket hoặc quyết định kỹ thuật giúp người đọc tìm bằng chứng gốc mà không cần chép toàn bộ nội dung vào change log.

## 9. Quy trình đề xuất, rà soát và phê duyệt thay đổi

Một quy trình thống nhất giúp thay đổi tài liệu có thể kiểm tra và không bị công bố nhầm.

### Các bước điển hình

1. **Đề xuất:** người dùng hoặc owner nêu vấn đề, lý do và phạm vi thay đổi.
2. **Phân loại:** xác định tài liệu, mức ảnh hưởng và nhóm cần tham gia.
3. **Soạn thảo:** author cập nhật bản nháp, đánh dấu nội dung thay đổi và liên kết bằng chứng.
4. **Rà soát:** reviewer đánh giá tính chính xác, đầy đủ, khả thi và tác động.
5. **Xử lý ý kiến:** author trả lời, sửa hoặc giải thích vì sao không áp dụng góp ý.
6. **Phê duyệt:** approver xác nhận nội dung, phiên bản và ngày hiệu lực.
7. **Công bố:** cập nhật nguồn chính thức, metadata, change log và liên kết.
8. **Thông báo:** gửi thông tin đến người bị ảnh hưởng qua kênh nội bộ phù hợp.
9. **Theo dõi áp dụng:** xác nhận nhóm đã biết thay đổi và xử lý các phụ thuộc.
10. **Lưu trữ:** giữ phiên bản cũ ở trạng thái superseded hoặc archived.

### Tiêu chí hoàn tất rà soát

Một thay đổi chỉ nên chuyển sang phê duyệt khi:

- Mục đích và phạm vi rõ ràng.
- Nội dung không mâu thuẫn với phần khác của tài liệu.
- Các thuật ngữ và vai trò được dùng nhất quán.
- Bằng chứng hoặc lý do thay đổi có thể truy xuất.
- Tác động đến quy trình, công cụ và nhóm liên quan đã được đánh giá.
- Các ý kiến quan trọng đã được xử lý.
- Metadata và change log đã sẵn sàng.
- Ngày hiệu lực và kế hoạch thông báo đã xác định.

Không cần biến mọi sửa lỗi chính tả thành một cuộc họp lớn. Quy trình có thể phân luồng theo mức rủi ro, nhưng phải giữ được lịch sử và trách nhiệm.

## 10. Quản lý trạng thái tài liệu

Trạng thái giúp người đọc biết nội dung có thể được áp dụng hay chưa. Cần định nghĩa trạng thái và điều kiện chuyển trạng thái.

| Trạng thái | Ý nghĩa | Có được dùng làm chuẩn hiện hành? |
|---|---|---|
| Draft | Đang soạn, chưa được rà soát đầy đủ | Không |
| In review | Đang được người được chỉ định rà soát | Không |
| Approved | Đã được phê duyệt, chờ ngày hiệu lực nếu có | Theo ngày hiệu lực |
| Effective/Published | Đang có hiệu lực và là bản chính thức | Có |
| Superseded | Đã được phiên bản mới thay thế | Không |
| Archived | Lưu để tra cứu lịch sử, không còn áp dụng | Không |
| Withdrawn | Bị rút do không còn phù hợp hoặc có vấn đề | Không |

Một tài liệu ở trạng thái Approved có thể chưa có hiệu lực nếu ngày áp dụng nằm trong tương lai. Hệ thống lưu trữ nên hiển thị rõ trạng thái và ngày để người dùng không hiểu nhầm.

### Không xóa lịch sử cũ

Khi một tài liệu bị thay thế, giữ lại phiên bản cũ cùng metadata và đường dẫn đến phiên bản thay thế. Điều này hỗ trợ audit, điều tra incident và hiểu vì sao một quyết định trước đây được đưa ra.

Nếu nội dung cũ chứa thông tin nhạy cảm hoặc sai nghiêm trọng, áp dụng chính sách sửa/thu hồi có kiểm soát và giữ dấu vết cần thiết theo yêu cầu lưu trữ của tổ chức.

## 11. Rà soát định kỳ theo mức độ rủi ro

Lịch cập nhật nên phản ánh tốc độ thay đổi và hậu quả nếu tài liệu lỗi thời. Không nên đặt cùng chu kỳ cho mọi loại tài liệu.

Ví dụ về chu kỳ gợi ý:

| Loại tài liệu | Chu kỳ xem xét gợi ý | Lý do |
|---|---|---|
| Chiến lược kiểm thử cấp tổ chức | 6–12 tháng | Thay đổi chậm hơn nhưng ảnh hưởng rộng |
| Chiến lược sản phẩm/dự án | Mỗi release lớn hoặc 3–6 tháng | Kiến trúc và phạm vi sản phẩm thay đổi thường xuyên hơn |
| Release gate và tiêu chí chất lượng | Mỗi quý hoặc khi thay đổi quy trình | Ảnh hưởng trực tiếp quyết định phát hành |
| Hướng dẫn pipeline và môi trường | 1–3 tháng hoặc sau thay đổi nền tảng | Công cụ và cấu hình có thể thay đổi nhanh |
| Quy trình dữ liệu và bảo mật | Theo chu kỳ chính sách, tối thiểu theo yêu cầu kiểm soát | Có thể chịu yêu cầu tuân thủ hoặc rủi ro cao |
| Biểu mẫu và checklist | 6 tháng hoặc khi phát sinh nhu cầu mới | Cần phù hợp với dữ liệu và quy trình hiện tại |

Đây là ví dụ để thiết kế lịch, không phải quy định mặc định. Tổ chức cần chọn chu kỳ theo mức độ rủi ro, tần suất thay đổi và yêu cầu pháp lý/hợp đồng.

### Định nghĩa ngày rà soát tiếp theo

Mỗi tài liệu nên có ngày rà soát tiếp theo hoặc quy tắc tính ngày đó. Khi đến hạn, owner cần xác nhận một trong các kết quả:

- Reviewed, no change: đã rà soát và chưa cần sửa.
- Updated: đã cập nhật và chuyển qua quy trình phê duyệt.
- Review deferred: hoãn có lý do, người chấp nhận và ngày mới.
- Superseded: tài liệu đã được thay thế.
- Withdrawn: tài liệu bị rút.

Không cập nhật ngày rà soát mới chỉ để làm dashboard hết cảnh báo nếu thực tế chưa có hoạt động xem xét.

## 12. Cập nhật theo sự kiện, không chỉ theo lịch

Một số thay đổi có thể làm tài liệu lỗi thời ngay sau lần rà soát định kỳ. Vì vậy, cần có trigger yêu cầu xem xét ngoài lịch.

Các trigger thường gặp:

- Thay đổi kiến trúc, ranh giới dịch vụ hoặc luồng dữ liệu.
- Thêm hoặc loại bỏ chức năng quan trọng.
- Thay đổi nền tảng CI/CD, runner, môi trường hoặc công cụ kiểm thử.
- Thay đổi API, schema, giao thức hoặc dịch vụ tích hợp.
- Incident nghiêm trọng hoặc lỗi lọt production.
- Thay đổi tiêu chí phát hành, SLA hoặc mức rủi ro.
- Thay đổi luật, hợp đồng, chính sách bảo mật hoặc yêu cầu audit.
- Thay đổi cơ cấu nhóm, owner hoặc quyền phê duyệt.
- Chỉ số chất lượng vượt ngưỡng trong nhiều kỳ.
- Công cụ hoặc phiên bản runtime hết hỗ trợ.
- Phát hiện tài liệu mâu thuẫn, không thể thực hiện hoặc không còn được sử dụng.

### Trigger cần gắn với quy trình thay đổi khác

Ví dụ, khi một ADR thay đổi kiến trúc, ticket hoặc mẫu ADR có thể có bước xác định tài liệu kiểm thử liên quan cần xem xét. Khi incident được đóng, phần post-incident review có thể ghi rõ chiến lược, checklist hoặc release gate nào cần cập nhật.

Nếu không gắn trigger với quy trình đang diễn ra, việc cập nhật phụ thuộc vào trí nhớ của cá nhân và dễ bị bỏ sót.

### Phân biệt rà soát và cập nhật

Không phải mọi lần rà soát đều phải thay đổi nội dung. Owner có thể kết luận tài liệu vẫn phù hợp và ghi nhận ngày, người rà soát, bằng chứng đã xem. Điều quan trọng là chứng minh việc xem xét đã diễn ra, không phải tạo ra một diff cho mỗi kỳ.

## 13. Lập lịch và điều phối hoạt động rà soát

Lịch rà soát cần được nhìn thấy và có thể thực hiện. Có thể dùng calendar, issue tracker, repository automation hoặc hệ thống quản lý tài liệu.

Một lịch nên ghi:

- Tài liệu và phiên bản hiện hành.
- Owner.
- Reviewer dự kiến.
- Ngày rà soát đến hạn.
- Mức rủi ro hoặc mức ưu tiên.
- Trigger gần nhất.
- Trạng thái công việc.
- Ngày phê duyệt hoặc ngày hiệu lực dự kiến.
- Liên kết đến ticket và tài liệu.

### Lên lịch ngược từ ngày đến hạn

Hãy dành thời gian cho việc mời reviewer, thu thập ý kiến, xử lý bất đồng và phê duyệt. Nếu chỉ đặt lịch đúng ngày hết hạn, owner có thể không còn đủ thời gian để hoàn tất quy trình.

Ví dụ với một tài liệu cần rà soát trong tháng:

1. Trước hạn 3 tuần: owner xác nhận phạm vi và người rà soát.
2. Trước hạn 2 tuần: gửi bản nháp và bằng chứng.
3. Trước hạn 1 tuần: hoàn tất review và xử lý góp ý.
4. Trước hạn 2 ngày: phê duyệt, cập nhật change log và thông báo.
5. Ngày đến hạn: xác nhận trạng thái và lưu bằng chứng rà soát.

Thời gian này chỉ là ví dụ. Tài liệu phức tạp hoặc cần nhiều bên có thể cần chu kỳ dài hơn.

### Tránh dồn tất cả tài liệu vào cùng một thời điểm

Nếu hàng trăm tài liệu cùng đến hạn cuối quý, owner và reviewer có thể quá tải. Phân tán lịch theo nhóm sản phẩm, mức rủi ro hoặc tháng. Tài liệu rủi ro cao nên có ưu tiên và nguồn lực phù hợp.

## 14. Quản lý tài liệu phụ thuộc và tính nhất quán

Một chiến lược kiểm thử thường liên kết với nhiều tài liệu khác: kiến trúc, test plan, release plan, quy trình incident, security policy, hướng dẫn CI và tiêu chuẩn dữ liệu. Thay đổi một tài liệu có thể khiến tài liệu khác không còn nhất quán.

### Tạo bản đồ phụ thuộc

Với tài liệu quan trọng, ghi các liên kết:

- Tài liệu nguồn hoặc chính sách cấp cao hơn.
- Tài liệu triển khai chi tiết.
- Quy trình được tài liệu này tham chiếu.
- Nhóm hoặc vai trò áp dụng.
- Công cụ hoặc hệ thống có cấu hình phụ thuộc.
- Tài liệu cần xem xét khi nội dung thay đổi.

Ví dụ, thay đổi release gate có thể ảnh hưởng đến test strategy, release checklist, pipeline configuration, hướng dẫn triage và mẫu báo cáo readiness.

### Phân tích tác động trước khi phê duyệt

Khi thay đổi nội dung, hãy hỏi:

1. Có tài liệu nào khác dựa vào quy tắc này không?
2. Có pipeline hoặc công cụ nào cần cấu hình lại không?
3. Có nhóm nào cần được thông báo hoặc đào tạo không?
4. Có dữ liệu, dashboard hoặc báo cáo nào cần đổi định nghĩa không?
5. Có quyết định hoặc ngoại lệ cũ nào không còn hợp lệ không?

Không nên sửa một tài liệu chính thức rồi để các tài liệu liên quan tiếp tục chỉ dẫn cách làm cũ.

### Quản lý thuật ngữ và định nghĩa

Nếu nhiều tài liệu dùng các thuật ngữ như release ready, smoke test, flaky test hoặc severity, cần có định nghĩa thống nhất hoặc liên kết đến glossary chính thức. Khi một thuật ngữ thay đổi nghĩa, xem xét các tài liệu sử dụng nó để tránh mâu thuẫn.

## 15. Kiểm soát phiên bản trong Git và quy trình pull request

Với tài liệu dạng văn bản như Markdown, Git hỗ trợ lịch sử, diff, review và liên kết với mã nguồn. Có thể quản lý tài liệu cùng repository sản phẩm hoặc trong repository riêng tùy phạm vi và quyền truy cập.

### Quy trình đề xuất thay đổi

1. Tạo branch hoặc change request.
2. Sửa đúng tài liệu và metadata.
3. Kiểm tra diff để bảo đảm thay đổi đúng phạm vi.
4. Mở pull request với mục đích, lý do, tác động và reviewer.
5. Nhận review và xử lý comment.
6. Được approver chấp thuận theo quy định.
7. Merge vào nhánh chính thức.
8. Gắn tag hoặc phiên bản tài liệu nếu cần.
9. Công bố đường dẫn và thông báo thay đổi.
10. Lưu liên kết giữa PR, commit, ticket và quyết định.

### Review tài liệu cũng cần có chất lượng

Người review nên kiểm tra:

- Nội dung có đúng với thực tế kỹ thuật và nghiệp vụ không?
- Người đọc có thể thực hiện được không?
- Phạm vi và ngoại lệ có rõ không?
- Thuật ngữ có nhất quán không?
- Ví dụ và code có còn hợp lệ không?
- Link và tham chiếu có hoạt động không?
- Có dữ liệu nhạy cảm hoặc thông tin không nên công khai không?
- Thay đổi có ảnh hưởng tài liệu hoặc quy trình khác không?

Review tài liệu không nên chỉ sửa câu chữ. Với tài liệu chiến lược, điều quan trọng là tính đúng, tính áp dụng và hệ quả của quy tắc.

### Quy tắc bảo vệ nhánh

Tài liệu chính thức có thể dùng branch protection hoặc cơ chế tương đương:

- Yêu cầu ít nhất một review phù hợp.
- Yêu cầu reviewer chuyên môn cho phần nhạy cảm.
- Chặn merge khi còn comment bắt buộc chưa xử lý.
- Ghi nhận người phê duyệt.
- Giới hạn quyền merge hoặc publish.
- Dùng CODEOWNERS hoặc danh sách owner nếu phù hợp.

Không nên áp dụng cơ chế kỹ thuật một cách máy móc. Quyền và số lượng review cần phù hợp với mức rủi ro và cách tổ chức vận hành.

## 16. Quản lý tài liệu hết hiệu lực và thay thế

Tài liệu cũ cần được xử lý có chủ đích để người dùng không tiếp tục áp dụng nhầm.

### Khi nào cần thay thế hoặc rút tài liệu?

- Nội dung được hợp nhất vào tài liệu khác.
- Sản phẩm hoặc quy trình không còn tồn tại.
- Chính sách mới thay thế hoàn toàn quy tắc cũ.
- Nội dung sai hoặc có thể gây hành động nguy hiểm.
- Không còn owner và không thể xác nhận tính phù hợp.
- Yêu cầu pháp lý hoặc hợp đồng thay đổi.

### Quy trình đóng vòng đời

1. Owner đề xuất supersede hoặc withdraw.
2. Xác định tài liệu thay thế hoặc lý do rút.
3. Xác định người dùng và nhóm bị ảnh hưởng.
4. Thông báo ngày hết hiệu lực.
5. Cập nhật liên kết từ tài liệu cũ sang bản mới.
6. Lưu bản cũ theo chính sách lưu trữ.
7. Gỡ tài liệu khỏi danh sách tài liệu hiện hành.
8. Cập nhật các liên kết, template và quy trình phụ thuộc.

Không xóa bản cũ ngay khi có bản mới. Lịch sử có thể cần cho audit hoặc điều tra một quyết định trong quá khứ.

### Tránh liên kết chết và bản sao không kiểm soát

Nếu tài liệu cũ được tải xuống hoặc in ra, trang chính thức nên có thông báo rằng bản sao có thể lỗi thời và chỉ nguồn chính thức mới xác định trạng thái hiện hành. Với bản in, có thể ghi version, ngày xuất và trạng thái kiểm soát bản sao theo chính sách tổ chức.

## 17. Đo hiệu quả quản lý tài liệu

Quản lý tài liệu cũng cần được đo để biết quy trình có hoạt động hay không. Chỉ đếm số tài liệu đã cập nhật không cho biết chúng có đúng, hữu ích hoặc được người dùng áp dụng.

Một số chỉ số có thể theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Review on-time rate | Tỷ lệ tài liệu được rà soát đúng hạn |
| Overdue document count | Số tài liệu quá hạn |
| Owner coverage | Tỷ lệ tài liệu quan trọng có owner rõ ràng |
| Reviewer coverage | Tỷ lệ thay đổi quan trọng có review phù hợp |
| Approval lead time | Thời gian từ đề xuất đến phê duyệt |
| Change adoption | Mức độ nhóm liên quan đã tiếp nhận thay đổi |
| Stale reference count | Số liên kết hoặc hướng dẫn đã lỗi thời |
| Superseded document usage | Tần suất người dùng còn truy cập hoặc sử dụng tài liệu cũ |
| Review action closure | Tỷ lệ hành động sau review được đóng đúng hạn |

### Diễn giải chỉ số cẩn trọng

Review on-time rate cao không bảo đảm nội dung chính xác nếu reviewer chỉ xác nhận hình thức. Approval lead time dài có thể do quy trình phức tạp, reviewer thiếu thời gian hoặc thay đổi không đủ rõ. Cần kết hợp chỉ số định lượng với phản hồi người dùng, kết quả audit, incident và chất lượng thực thi.

Không nên tạo mục tiêu khiến owner chỉ cập nhật ngày rà soát để tránh tài liệu bị đánh dấu quá hạn. Mục tiêu cần khuyến khích đánh giá thực chất và giải quyết các hành động được phát hiện.

## 18. Ví dụ thực hành: cập nhật chiến lược kiểm thử sau thay đổi kiến trúc

Giả sử một sản phẩm chuyển từ kiến trúc nguyên khối sang nhiều dịch vụ và thêm message broker. Chiến lược kiểm thử hiện tại tập trung vào API test và E2E, chưa mô tả rõ contract test, kiểm thử sự kiện, retry và tính idempotent.

### Xác định trigger và phạm vi

Thay đổi kiến trúc là trigger ngoài lịch. Document owner mở change request và xác định các phần cần xem xét:

- Phân tầng kiểm thử và trách nhiệm theo dịch vụ.
- Contract test giữa producer và consumer.
- Kiểm thử message ordering, duplicate và retry.
- Dữ liệu test và cách cô lập queue/topic.
- Readiness của broker và worker.
- Observability, correlation ID và bằng chứng điều tra.
- Tiêu chí phát hành khi có nhiều dịch vụ triển khai độc lập.

### Chọn reviewer

- Test lead rà soát phạm vi và độ bao phủ.
- Architect rà soát ranh giới dịch vụ và hợp đồng.
- Platform engineer rà soát môi trường broker và pipeline.
- Service owner rà soát cách kiểm tra consumer/producer.
- SRE rà soát quan sát, retry và khả năng phục hồi.
- Release owner rà soát tác động đến gate phát hành.

Mỗi reviewer được giao câu hỏi cụ thể và thời hạn. Chủ sở hữu xử lý các ý kiến mâu thuẫn và ghi lý do nếu không áp dụng một đề xuất.

### Ghi phiên bản và hiệu lực

Nếu thay đổi bổ sung một tầng kiểm thử và hướng dẫn mới nhưng không thay đổi nguyên tắc phát hành cốt lõi, tổ chức có thể dùng minor version theo quy ước đã chọn. Nếu thay đổi tiêu chí release gate hoặc quyền quyết định, có thể cần major version.

Phiên bản, ngày phê duyệt, ngày hiệu lực và các nhóm bị ảnh hưởng được ghi vào metadata và change log. Tài liệu cũ được đánh dấu superseded khi bản mới có hiệu lực.

### Theo dõi áp dụng

Sau công bố, owner theo dõi:

- Các nhóm dịch vụ đã cập nhật test plan.
- Pipeline có job contract/integration mới.
- Checklist release đã tham chiếu đúng quy tắc.
- Nhóm vận hành đã có dashboard và cảnh báo cần thiết.
- Các vấn đề phát sinh khi áp dụng được ghi thành hành động.

Sau một chu kỳ phát hành, owner đánh giá liệu tài liệu có giúp phát hiện lỗi tích hợp và hỗ trợ vận hành tốt hơn không. Kết quả đó trở thành đầu vào cho lần rà soát tiếp theo.

## 19. Những sai lầm thường gặp

- **Không có owner:** mọi người nghĩ người khác sẽ cập nhật và tài liệu bị bỏ quên.
- **Một người tự soạn và tự phê duyệt mọi thay đổi:** thiếu góc nhìn độc lập với nội dung rủi ro cao.
- **Đánh số phiên bản tùy tiện:** người đọc không biết thay đổi có ảnh hưởng đến cách áp dụng hay không.
- **Không ghi ngày hiệu lực:** bản đã phê duyệt nhưng chưa áp dụng bị dùng nhầm.
- **Chỉ rà soát theo lịch:** bỏ lỡ thay đổi kiến trúc, incident hoặc yêu cầu mới.
- **Chỉ cập nhật ngày rà soát:** không có bằng chứng nội dung đã được xem xét.
- **Lưu nhiều bản chính thức:** tạo mâu thuẫn và không rõ nguồn nào có thẩm quyền.
- **Xóa phiên bản cũ:** mất khả năng đối chiếu quyết định và audit.
- **Không đánh giá tài liệu phụ thuộc:** thay đổi một quy tắc nhưng các hướng dẫn khác vẫn cũ.
- **Review chỉ tập trung vào câu chữ:** bỏ qua tính đúng và khả năng thực hiện.
- **Mời quá nhiều reviewer không có mục tiêu:** kéo dài phê duyệt và làm loãng trách nhiệm.
- **Không xử lý comment bắt buộc:** merge nội dung khi các vấn đề quan trọng vẫn mở.
- **Không thông báo thay đổi:** người dùng tiếp tục làm theo phiên bản cũ.
- **Không theo dõi ngoại lệ:** ngoại lệ tạm thời trở thành chính sách không chính thức.
- **Đo số lượng thay đổi thay vì chất lượng:** khuyến khích sửa vụn vặt để đạt chỉ tiêu.

## 20. Mẫu metadata và change log cho tài liệu chiến lược

Có thể dùng một phần đầu tài liệu theo mẫu sau:

~~~yaml
document_id: TEST-STRATEGY-001
title: Chiến lược kiểm thử sản phẩm
document_type: strategy
scope:
  product: order-platform
  applies_to: release-and-maintenance
owner: quality-engineering-lead
maintainer: test-platform-team
version: 2.1.0
status: effective
created_date: 2025-11-01
approved_date: 2026-05-20
effective_date: 2026-06-01
last_reviewed_date: 2026-05-20
next_review_date: 2026-11-20
reviewers:
  - role: architecture
  - role: platform-engineering
approver:
  role: engineering-director
source_of_truth: internal-document-repository
~~~

Đây là ví dụ minh họa. Tên trường, cách định danh, định dạng ngày và vai trò phải theo quy ước tài liệu của tổ chức. Không đưa thông tin cá nhân hoặc dữ liệu truy cập nhạy cảm vào metadata công khai.

### Mẫu change log

~~~text
Version:
Date:
Status:
Author:
Document owner:
Reviewers:
Approver:
Reason for change:
Summary of changes:
Impact on users/processes:
Related tickets or decisions:
Effective date:
Next review date:
Supersedes:
~~~

Mẫu cần đủ gọn để được sử dụng thường xuyên. Nếu biểu mẫu quá dài hoặc trùng dữ liệu với hệ thống quản lý thay đổi, có thể lưu metadata trong công cụ và chỉ liên kết từ tài liệu.

## 21. Danh sách kiểm tra quản lý phiên bản, reviewer và lịch cập nhật

**Nguồn chính và trạng thái**

- Có một nguồn chính thức cho bản hiện hành không?
- Tài liệu có phân biệt draft, review, approved, effective, superseded và archived không?
- Có ngày phê duyệt, ngày hiệu lực và ngày rà soát không?
- Phiên bản cũ có thể tra cứu mà không bị nhầm là bản hiện hành không?

**Vai trò và rà soát**

- Mỗi tài liệu quan trọng có document owner cụ thể không?
- Người soạn, reviewer, approver và maintainer có trách nhiệm rõ không?
- Reviewer có chuyên môn phù hợp với nội dung thay đổi không?
- Thay đổi rủi ro cao có review độc lập và phê duyệt đúng thẩm quyền không?
- Có cách xử lý ý kiến bất đồng và comment chưa giải quyết không?

**Phiên bản và lịch sử**

- Quy ước version có được định nghĩa và áp dụng nhất quán không?
- Thay đổi có lý do, tác động, người thực hiện và liên kết bằng chứng không?
- Ngày hiệu lực có được phân biệt với ngày sửa không?
- Tài liệu có change log hoặc lịch sử Git có thể truy vết không?
- Bản PDF hoặc bản phân phối có tham chiếu nguồn chính không?

**Lịch cập nhật và trigger**

- Chu kỳ rà soát có phù hợp với mức rủi ro và tốc độ thay đổi không?
- Có ngày rà soát tiếp theo và owner theo dõi không?
- Các trigger như incident, thay đổi kiến trúc, công cụ hoặc chính sách có được liên kết với quy trình cập nhật không?
- Lịch có đủ thời gian cho review, sửa đổi và phê duyệt không?
- Việc hoãn rà soát có lý do, người chấp nhận và ngày mới không?

**Tính nhất quán và cải thiện**

- Tài liệu phụ thuộc đã được xem xét khi có thay đổi chưa?
- Người dùng bị ảnh hưởng có được thông báo và hướng dẫn áp dụng không?
- Tài liệu hết hiệu lực có được đánh dấu và lưu trữ đúng cách không?
- Có theo dõi review on-time, owner coverage, approval lead time và hành động sau review không?
- Có thu thập phản hồi và kết quả sử dụng thực tế để cải thiện tài liệu không?

## Kết luận

Quản lý phiên bản, người rà soát và lịch cập nhật giúp tài liệu chiến lược kiểm thử duy trì giá trị theo thời gian. Mỗi tài liệu cần có nguồn chính thức, chủ sở hữu, vai trò rà soát và phê duyệt, quy ước phiên bản, trạng thái, ngày hiệu lực và lịch xem xét. Rà soát định kỳ cần được bổ sung bằng trigger từ thay đổi kiến trúc, incident, công cụ, chính sách và rủi ro mới. Khi change log ghi rõ lý do và tác động, reviewer được chọn đúng chuyên môn, phiên bản cũ được lưu có kiểm soát và người dùng được thông báo, tổ chức có thể truy vết quyết định, tránh áp dụng tài liệu lỗi thời và duy trì chiến lược kiểm thử phù hợp với thực tế.
