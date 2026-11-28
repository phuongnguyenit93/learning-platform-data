# Thu thập security requirement

## 1. Mục đích của hoạt động thu thập

**Thu thập yêu cầu bảo mật — security requirements elicitation** là quá trình làm rõ hệ thống cần bảo vệ điều gì, trước những tình huống gây hại nào, trong điều kiện vận hành nào và theo những ràng buộc nào. Đầu ra là các yêu cầu có nguồn gốc, phạm vi và cơ sở để tiếp tục đặc tả, thiết kế và kiểm chứng.

Việc thu thập bao gồm trao đổi với các bên liên quan, quan sát công việc thực tế, phân tích tài liệu và xem xét các kịch bản sử dụng sai. Người dùng thường mô tả điều họ muốn làm; nhóm phát triển phải cùng họ phát hiện những điều cần ngăn chặn, những dữ liệu cần bảo vệ và những hành vi cần truy vết.

Ví dụ, câu “nhân viên hỗ trợ cần xem phiếu của khách hàng” chưa trả lời được:

- Nhân viên được xem phiếu của khách hàng thuộc tenant nào?
- Có cần được phân công vào nhóm xử lý không?
- Tệp đính kèm, bản xuất và tác vụ nền có cùng giới hạn truy cập không?
- Khi nhân viên chuyển nhóm hoặc nghỉ việc, quyền cũ còn tồn tại bao lâu?
- Ai được xem lịch sử truy cập và dữ liệu nào xuất hiện trong log?

Trong module thiết kế yêu cầu bảo mật, hoạt động này tạo mối liên hệ ban đầu giữa **mục tiêu an toàn thông tin, mô hình đe dọa, rủi ro, kiến trúc và tiêu chí kiểm thử**. Xác thực, phân quyền, bảo vệ dữ liệu, logging và phục hồi cần được đặt vào bối cảnh nghiệp vụ cụ thể.

[OWASP SAMM — Software Requirements](https://owaspsamm.org/model/design/security-requirements/stream-a/) khuyến khích xuất phát từ chức năng, mục tiêu bảo vệ và góc nhìn sử dụng sai để tìm yêu cầu phù hợp. Các yêu cầu cần cụ thể, đo được và liên quan đến ứng dụng.

Sau bài học, người học cần có thể:

1. Xác định người và nguồn thông tin cần tham gia thu thập.
2. Đặt câu hỏi để phát hiện tài sản, quyền hạn, rủi ro và tình huống ngoại lệ.
3. Chuyển phát biểu ban đầu thành yêu cầu ứng viên có thể tiếp tục làm rõ.
4. Ghi lại nguồn, giả định, mâu thuẫn và người chịu trách nhiệm xác nhận.
5. Chuẩn bị đầu vào đủ rõ cho các bước đặc tả và quản lý yêu cầu tiếp theo.

## 2. Phân biệt thông tin thu được

Một buổi trao đổi thường tạo ra nhiều loại thông tin. Ghi tất cả vào danh sách “security requirement” sẽ làm nhóm khó thiết kế và kiểm thử đúng điều cần bảo vệ.

| Loại thông tin | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Mục tiêu bảo vệ | Ngăn nhân viên đọc dữ liệu khách hàng ngoài phạm vi được giao | Cơ sở để suy ra yêu cầu chi tiết |
| Sự kiện nghiệp vụ | Nhân viên có thể chuyển từ nhóm xử lý này sang nhóm khác | Đầu vào cho vòng đời quyền truy cập |
| Tài sản | Nội dung phiếu hỗ trợ, tệp đính kèm, thông tin liên hệ | Xác định đối tượng cần bảo vệ |
| Kịch bản đe dọa | Người đã đăng nhập đổi mã phiếu để đọc dữ liệu tenant khác | Cơ sở cho yêu cầu kiểm soát truy cập |
| Yêu cầu ứng viên | Mọi đường đọc phiếu phải kiểm tra quyền của chủ thể đối với tenant và phiếu | Đưa vào danh sách để làm rõ và xác nhận |
| Giải pháp đề xuất | Dùng một thư viện policy engine cụ thể | Ghi riêng để xem xét ở bước thiết kế |
| Ràng buộc đã có hiệu lực | Ứng dụng phải tích hợp IdP do tổ chức chỉ định | Ghi nguồn, phạm vi và người xác nhận ràng buộc |
| Giả định | Nhà cung cấp email không lưu nội dung quá thời gian cần thiết | Cần bằng chứng; chưa được coi là sự thật |
| Câu hỏi mở | Phiếu đã đóng phải được giữ trong bao lâu? | Giao người trả lời và hạn phản hồi |
| Bằng chứng về hiện trạng | Báo cáo cho thấy một tài khoản cũ vẫn có thể tải tệp | Đầu vào để xác định khoảng trống và rủi ro |

Tách yêu cầu khỏi giải pháp giúp giữ rõ mục đích. “Mọi API đọc phiếu phải thực thi chính sách truy cập đã xác định” diễn đạt kết quả cần đạt. “Dùng thư viện X” là một lựa chọn triển khai, trừ khi tổ chức đã ban hành nó thành ràng buộc có nguồn rõ ràng.

Cũng cần phân biệt:

- **Yêu cầu chức năng bảo mật:** chức năng xác thực, quản lý quyền, ghi sự kiện hoặc thu hồi phiên.
- **Thuộc tính chất lượng có ý nghĩa bảo mật:** giới hạn mất dữ liệu, khả năng phục hồi hoặc tính sẵn sàng trong điều kiện đã xác định.
- **Yêu cầu quy trình và nhà cung cấp:** cách bàn giao bằng chứng, xử lý sự cố hoặc thông báo thay đổi dịch vụ.

Không nên đặt mọi yêu cầu bảo mật vào một nhóm “phi chức năng” rồi bỏ qua việc đặc tả hành vi.

## 3. Xác định phạm vi trước khi phỏng vấn

Trước khi hỏi hệ thống phải an toàn như thế nào, cần thống nhất đang nói đến hệ thống nào.

Một bản mô tả phạm vi ban đầu nên có:

- Mục đích nghiệp vụ và các hành trình người dùng chính.
- Nhóm người dùng, quản trị viên, tài khoản dịch vụ và đối tác tích hợp.
- Môi trường dự kiến: thử nghiệm, chạy thử, vận hành chính thức.
- Dữ liệu xử lý, nơi phát sinh, nơi lưu và bên nhận dữ liệu.
- Các giao diện: web, API, email, webhook, tác vụ nền, xuất nhập dữ liệu.
- Hệ thống phụ thuộc: IdP, lưu trữ, quản lý khóa, logging, backup và dịch vụ bên ngoài.
- Phần thuộc phạm vi dự án và các giả định về phần bên ngoài.
- Những thay đổi dự kiến có thể mở rộng rủi ro.

### Ví dụ xuyên suốt

Nhóm xây dựng **cổng hỗ trợ khách hàng nhiều tenant**. Mỗi tenant là một tổ chức khách hàng. Người dùng tạo phiếu và tải tệp; nhân viên hỗ trợ xử lý phiếu theo nhóm; quản trị viên tenant quản lý thành viên. Hệ thống có API, tác vụ gửi email, lưu tệp, xuất báo cáo và backup.

Phạm vi thu thập phải bao gồm các đường xử lý phía sau giao diện. Nếu chỉ phỏng vấn về màn hình xem phiếu, nhóm có thể bỏ sót quyền tải tệp trực tiếp, tác vụ xuất báo cáo hoặc dữ liệu chuyển sang nhà cung cấp email.

“Nhà cung cấp chịu trách nhiệm” không làm một rủi ro biến mất khỏi phạm vi tìm hiểu. Nhóm vẫn cần xác định phần nhà cung cấp bảo vệ, điều kiện sử dụng và phần ứng dụng tự chịu trách nhiệm.

## 4. Xác định bên liên quan và điều cần hỏi

Người đặt hàng không nhất thiết biết hết quy trình vận hành. Nhân viên xử lý công việc hằng ngày có thể biết các bước thủ công và ngoại lệ chưa xuất hiện trong tài liệu.

| Bên liên quan | Thông tin cần thu thập | Câu hỏi gợi mở |
| --- | --- | --- |
| Chủ sản phẩm hoặc chủ nghiệp vụ | Mục tiêu, tổn thất cần tránh, hành vi chấp nhận được | Sự cố nào khiến quy trình kinh doanh không thể tiếp tục? |
| Người dùng trực tiếp | Cách làm thực tế, ngoại lệ và thao tác ngoài hệ thống | Khi không đủ quyền hoặc hệ thống bị lỗi, hiện tại anh/chị xử lý thế nào? |
| Chủ dữ liệu | Độ nhạy cảm, mục đích sử dụng, người được truy cập | Ai cần từng trường dữ liệu và vì mục đích gì? |
| Nhóm bảo mật | Đe dọa, chính sách, phát hiện và kiểm soát hiện có | Những đường gây hại nào chưa có yêu cầu tương ứng? |
| Kiến trúc sư và lập trình viên | Luồng dữ liệu, giao diện, giới hạn kỹ thuật | Có tác vụ nền hoặc đường truy cập nào khác giao diện người dùng không? |
| QA hoặc người đánh giá | Khả năng kiểm chứng, môi trường và dữ liệu kiểm thử | Làm thế nào phân biệt hành vi đạt với không đạt? |
| Vận hành, SRE, SOC | Phát hiện sự cố, trực vận hành, phục hồi | Khi mất IdP, mất log hoặc mất kho dữ liệu, cần duy trì hành vi nào? |
| Pháp chế, quyền riêng tư, tuân thủ | Nghĩa vụ, hợp đồng và điều kiện áp dụng | Yêu cầu nào thực sự áp dụng cho loại dữ liệu và phạm vi triển khai này? |
| Mua sắm và nhà cung cấp | Cam kết dịch vụ, phụ thuộc, quyền đánh giá và bàn giao | Bằng chứng nào được cung cấp và ai xử lý khi cam kết không đạt? |

Người điều phối cần ghi rõ:

- Ai cung cấp thông tin.
- Ai có quyền xác nhận quy tắc nghiệp vụ hoặc nghĩa vụ liên quan.
- Ai sẽ thực hiện yêu cầu.
- Ai sẽ xác minh kết quả.

Một người có thể đảm nhiệm nhiều vai trò, nhưng không được suy rằng người phát biểu đầu tiên có quyền quyết định mọi nội dung.

## 5. Tìm yêu cầu từ nhiều nguồn

### 5.1. Các nhóm nguồn cần xem xét

[NIST SSDF 1.1, thực hành PO.1](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf) đề cập việc xác định yêu cầu từ nguồn nội bộ và bên ngoài, duy trì chúng trong vòng đời và truyền đạt yêu cầu cho bên cung cấp có liên quan.

Với cổng hỗ trợ khách hàng, có thể lập danh mục nguồn như sau. Các mã chỉ phục vụ ví dụ trong bài học.

| Mã nguồn | Nguồn | Thông tin có thể phát hiện |
| --- | --- | --- |
| SRC-BIZ-01 | Phỏng vấn chủ nghiệp vụ và nhân viên hỗ trợ | Quy tắc phân công phiếu, hành vi bị cấm, ngoại lệ hỗ trợ |
| SRC-DATA-01 | Kiểm kê dữ liệu cùng chủ dữ liệu | Nội dung nhạy cảm, bản sao, thời hạn sử dụng và đối tượng được nhận |
| SRC-ARCH-01 | Sơ đồ bối cảnh và luồng dữ liệu | Ranh giới tin cậy, tác vụ nền, tích hợp và đường tải tệp |
| SRC-POL-01 | Chính sách bảo mật nội bộ | Yêu cầu xác thực, tài khoản đặc quyền và quản lý sự kiện |
| SRC-OBL-01 | Nghĩa vụ áp dụng được người phụ trách xác nhận | Ràng buộc về xử lý dữ liệu, hợp đồng và báo cáo sự cố |
| SRC-THREAT-01 | Buổi phân tích đe dọa | Truy cập chéo tenant, chiếm tài khoản, lạm dụng xuất dữ liệu |
| SRC-OPS-01 | Trao đổi với vận hành và dữ liệu diễn tập | Khả năng phục hồi, khoảng trống giám sát và phụ thuộc |
| SRC-INC-01 | Báo cáo sự cố và phát hiện trước đây | Các quy tắc còn thiếu hoặc không phù hợp với thực tế |
| SRC-SUP-01 | Tài liệu và cam kết nhà cung cấp | Phạm vi dịch vụ, giới hạn bảo vệ và trách nhiệm phối hợp |

Mỗi nguồn nên có tên, phiên bản hoặc ngày ghi nhận, người cung cấp và phạm vi áp dụng. Với tài liệu chỉ được truy cập hạn chế, lưu tham chiếu và kết luận phù hợp thay vì sao chép toàn bộ nội dung nhạy cảm vào backlog.

### 5.2. Dùng tiêu chuẩn để phát hiện khoảng trống

[OWASP ASVS](https://asvs.owasp.org/) cung cấp các yêu cầu làm cơ sở thiết kế, phát triển và kiểm chứng kiểm soát bảo mật cho ứng dụng web và dịch vụ web. Khi tham chiếu một yêu cầu ASVS, cần ghi phiên bản để tránh nhầm lẫn khi mã hoặc nội dung thay đổi.

Cách sử dụng trong thu thập:

1. Chọn nhóm nội dung liên quan đến ứng dụng.
2. Đối chiếu với chức năng, dữ liệu và rủi ro thực tế.
3. Ghi yêu cầu ứng viên có phạm vi và cách kiểm chứng phù hợp.
4. Ghi lý do nếu một mục không áp dụng.
5. Đưa vấn đề chưa rõ vào danh sách cần xác nhận.

Danh mục chuẩn hỗ trợ đặt câu hỏi. Nó không tự cung cấp quy tắc ai được xem phiếu nào, thời gian thu hồi quyền hoặc tổn thất nghiệp vụ có thể chấp nhận.

[OWASP Developer Guide — Requirements in practice](https://devguide.owasp.org/en/03-requirements/01-requirements/) cũng phân biệt các nguồn yêu cầu về phần mềm, nhà cung cấp và nghĩa vụ áp dụng. Việc thu thập cần bao phủ đúng những nguồn có liên quan đến dự án.

## 6. Chọn kỹ thuật thu thập phù hợp

Quy trình dưới đây là một cách thực hành minh họa. Nhóm có thể điều chỉnh hình thức theo quy mô hệ thống và mức rủi ro.

### 6.1. Phỏng vấn theo kịch bản cụ thể

Bắt đầu từ một hành trình thực tế, chẳng hạn “nhân viên hỗ trợ mở tệp đính kèm của phiếu”, rồi đi qua:

- Điều kiện trước khi thực hiện.
- Ai khởi tạo, ai được hưởng lợi và ai có thể chịu thiệt hại.
- Những tài nguyên và dữ liệu được sử dụng.
- Hành vi cho phép và hành vi cần từ chối.
- Trường hợp thay đổi quyền, hết phiên hoặc dữ liệu không còn hợp lệ.
- Điều cần quan sát để biết hành động đã xảy ra đúng.
- Cách xử lý khi một dịch vụ phụ thuộc bị lỗi.

Tránh chỉ hỏi “có cần phân quyền không?”. Câu hỏi đó thường chỉ tạo câu trả lời “có”. Câu hỏi “một nhân viên vừa chuyển nhóm có được tải lại tệp của nhóm cũ không?” giúp phát hiện quy tắc cụ thể.

### 6.2. Quan sát công việc và walkthrough

Mời người thực hiện đi qua quy trình hiện tại bằng dữ liệu mẫu. Quan sát:

- Bảng tính hoặc thư mục dùng để trao đổi ngoài hệ thống.
- Tài khoản dùng chung và thao tác hỗ trợ khẩn cấp.
- Bước cấp quyền thủ công.
- Bản xuất được tải về máy hoặc gửi qua email.
- Tình huống người dùng phải nhờ người khác làm thay.

Việc quan sát không tự chứng minh quy trình hiện tại là đúng. Nó cho thấy rủi ro hoặc nhu cầu mà yêu cầu mới phải giải quyết.

### 6.3. Workshop liên chức năng

Workshop hữu ích khi quy tắc cần nhiều bên cùng xác nhận, ví dụ logging vừa liên quan điều tra sự cố vừa liên quan bảo vệ dữ liệu.

Một buổi làm việc có thể gồm:

1. Chốt phạm vi và luồng đang xem xét.
2. Xác định tài sản và những hành vi cần bảo vệ.
3. Đi qua luồng bình thường và ngoại lệ.
4. Đặt các tình huống sử dụng sai.
5. Ghi yêu cầu ứng viên, mâu thuẫn và câu hỏi mở.
6. Đọc lại kết luận, chỉ định người xác nhận và hạn phản hồi.

Người điều phối phải tạo cơ hội cho các vai trò khác nhau nêu ý kiến. Việc nhiều người im lặng không đồng nghĩa họ đã đồng ý với quy tắc vừa được đề xuất.

### 6.4. Phân tích tài liệu và hiện trạng

Đọc tài liệu có liên quan trong phạm vi được phép: chính sách, hợp đồng, thiết kế, tài liệu vận hành và báo cáo sự cố. Với từng phát biểu, kiểm tra:

- Đây là quy tắc hiện hành, mục tiêu tương lai hay mô tả hiện trạng?
- Có áp dụng cho hệ thống này không?
- Có điều kiện hoặc ngoại lệ nào không?
- Ai có thẩm quyền giải thích?
- Có mâu thuẫn với nguồn khác không?

Ảnh chụp màn hình cũ hoặc tài liệu không có phiên bản chỉ nên được ghi nhận với mức tin cậy tương ứng.

### 6.5. Phân tích đe dọa và tình huống lạm dụng

Với mỗi chức năng, tìm cách nó có thể gây hại do người ngoài, người đã đăng nhập, người nội bộ hoặc tích hợp bị chiếm quyền.

Ví dụ chức năng “xuất báo cáo phiếu” dẫn đến các câu hỏi:

- Người có quyền xem một phiếu có được xuất toàn bộ tenant không?
- Bản xuất được tạo dưới danh tính và phạm vi quyền nào?
- Quyền thay đổi trong lúc chờ tác vụ có được xét lại không?
- Người tải bản xuất có phải người đã yêu cầu không?
- Tệp tồn ở đâu và bao lâu?
- Có giới hạn số lượng, tốc độ và dấu vết truy vết không?

Kết quả là các yêu cầu ứng viên; chưa cần chọn toàn bộ thuật toán hoặc công nghệ triển khai ngay trong buổi thu thập.

## 7. Khám phá tài sản, luồng dữ liệu và ranh giới tin cậy

### 7.1. Tìm dữ liệu ở cả đường chính và các bản sao

| Vị trí | Điều cần thu thập |
| --- | --- |
| Cơ sở dữ liệu nghiệp vụ | Trường dữ liệu, độ nhạy cảm, chủ dữ liệu và quyền truy cập |
| Tệp đính kèm | Chủ sở hữu, kiểm soát tải lên/tải xuống, phạm vi chia sẻ |
| Cache và chỉ mục tìm kiếm | Dữ liệu sao chép, thời gian tồn, đồng bộ khi thu hồi hoặc xóa |
| Log và dữ liệu giám sát | Trường sự kiện, dữ liệu cần loại bỏ, người được xem |
| Tệp xuất và thư mục tạm | Người tạo, người nhận, thời hạn tồn và cơ chế dọn dẹp |
| Email và dịch vụ bên ngoài | Dữ liệu được chuyển, mục đích và giới hạn nhà cung cấp |
| Backup và bản sao phục hồi | Phạm vi dữ liệu, quyền khôi phục, thời hạn và cách xử lý yêu cầu xóa |
| Môi trường phát triển và kiểm thử | Nguồn dữ liệu mẫu, mức che giấu và quyền tiếp cận |

Không nên suy rằng xóa bản ghi chính đã xóa mọi bản sao. Cũng không nên hứa một thời hạn xóa nếu chưa làm rõ backup, nghĩa vụ giữ lại và khả năng thực hiện.

### 7.2. Vẽ sơ đồ đủ để đặt câu hỏi

~~~mermaid
flowchart LR
    U[Người dùng và nhân viên hỗ trợ] --> W[Web và API]
    W --> IDP[IdP]
    W --> DB[(Dữ liệu phiếu)]
    W --> OBJ[(Tệp đính kèm)]
    W --> Q[Hàng đợi]
    Q --> JOB[Tác vụ nền]
    JOB --> MAIL[Nhà cung cấp email]
    JOB --> EXP[(Bản xuất tạm)]
    W --> LOG[Hệ thống logging]
    JOB --> LOG
    DB --> BAK[(Backup)]
    OBJ --> BAK
~~~

Các mũi tên mô tả luồng minh họa, chưa phải thiết kế bảo mật đầy đủ. Khi walkthrough, cần đánh dấu những nơi thay đổi danh tính, phạm vi tenant, quyền truy cập hoặc đơn vị chịu trách nhiệm.

Tại mỗi ranh giới, tìm hiểu:

- Bên gửi được xác thực bằng cách nào?
- Bên nhận có thể tin những thuộc tính nào và dựa vào nguồn nào?
- Quyền của người dùng có được truyền đúng sang tác vụ nền không?
- Dữ liệu có bị lưu thêm hoặc chuyển sang đơn vị khác không?
- Điều gì xảy ra khi dữ liệu, danh tính hoặc thông điệp không hợp lệ?
- Cần từ chối, thử lại, cảnh báo hoặc chuyển xử lý thủ công trong tình huống nào?

Không mặc định “nằm trong mạng nội bộ” hoặc “đến từ hàng đợi” là đủ cơ sở tin cậy.

## 8. Bộ câu hỏi theo nhóm yêu cầu

### 8.1. Xác thực và vòng đời danh tính

Cần thu thập về người dùng, tài khoản dịch vụ và các cơ chế khôi phục:

- Ai tạo tài khoản, xác nhận danh tính và cấp quyền ban đầu?
- Hoạt động nào cần MFA hoặc xác thực tăng cường?
- Phiên, token và tài khoản dịch vụ bị thu hồi trong các tình huống nào?
- Thời gian thu hồi hiệu lực tối đa là bao lâu, tính từ sự kiện nào?
- Khi IdP không khả dụng, chức năng nào được tiếp tục và dựa trên điều kiện gì?
- Quy trình khôi phục tài khoản có tạo đường bỏ qua bảo vệ không?
- Tài khoản khẩn cấp do ai quản lý, sử dụng và kiểm tra?

Không chỉ thu thập hành vi đăng nhập thành công. Đăng xuất, vô hiệu hóa người dùng, thay đổi nhóm, mất thiết bị và khôi phục tài khoản thường làm lộ các yêu cầu còn thiếu.

### 8.2. Phân quyền và cách ly dữ liệu

Cần làm rõ quan hệ **chủ thể — hành động — tài nguyên — điều kiện**:

- Những vai trò nào tồn tại và quyền của từng vai trò là gì?
- Người dùng có thể đồng thời thuộc nhiều tenant hoặc nhóm không?
- Quyền đọc, sửa, xóa, xuất và cấp quyền có khác nhau không?
- Có quyền truy cập hỗ trợ xuyên tenant không; ai phê duyệt, trong bao lâu?
- Tác vụ nền, tải tệp, tìm kiếm và bản xuất có dùng cùng quy tắc không?
- Khi quyền thay đổi, các yêu cầu đang chạy được xử lý như thế nào?
- Hành vi mặc định khi không xác định được quyền là gì?

Một ma trận quyền ban đầu có thể phát hiện mâu thuẫn sớm. Tuy nhiên, ma trận vai trò cần bổ sung các điều kiện như tenant, nhóm được phân công, trạng thái tài nguyên và quyền được ủy nhiệm.

### 8.3. Dữ liệu và quyền riêng tư

Cần biết dữ liệu nào thật sự cần thiết, thay vì mặc định thu thập mọi trường có thể có:

- Mỗi trường phục vụ mục đích nào?
- Ai cần xem giá trị đầy đủ, ai chỉ cần thông tin đã giảm chi tiết?
- Dữ liệu được truyền và lưu tại những đâu?
- Yêu cầu bảo vệ áp dụng cho bản chính, bản xuất, log và backup như thế nào?
- Thời hạn giữ lại dựa trên nhu cầu và nghĩa vụ nào?
- Ai xác nhận yêu cầu sửa, xóa hoặc hạn chế sử dụng dữ liệu?
- Có trường hợp giữ lại đặc biệt nào cần được quản lý riêng?
- Những khóa, thông tin bí mật và thông tin xác thực nào phải được bảo vệ?

Ghi rõ căn cứ của yêu cầu. Một thời hạn do nhóm tự đề xuất phải được phân biệt với thời hạn đã được người có trách nhiệm xác nhận.

### 8.4. Logging, phát hiện và điều tra

Cần thu thập:

- Sự kiện nào phải ghi: thay đổi quyền, xuất dữ liệu, truy cập đặc quyền, hành động bị từ chối.
- Trường nào cần để liên kết chủ thể, tenant, hành động, tài nguyên, thời gian và kết quả.
- Dữ liệu nào phải loại bỏ hoặc giảm chi tiết: mật khẩu, token, nội dung nhạy cảm.
- Ai được đọc, sửa, xóa hoặc xuất log.
- Cách bảo vệ log khỏi mất mát và thay đổi trái phép.
- Khoảng trễ chấp nhận được và cách xử lý khi đường truyền log bị gián đoạn.
- Ai nhận cảnh báo và có trách nhiệm phản ứng.
- Thời hạn lưu giữ và căn cứ của thời hạn đó.

Yêu cầu “ghi đầy đủ log” dễ tạo cả thiếu bằng chứng lẫn lộ dữ liệu. Phải làm rõ mục đích điều tra và những thông tin tối thiểu cần thiết.

### 8.5. Tính sẵn sàng, ứng phó và phục hồi

Cần hỏi nghiệp vụ về hậu quả của gián đoạn và mất dữ liệu:

- Chức năng nào thiết yếu, có thứ tự phục hồi ra sao?
- Gián đoạn bao lâu bắt đầu gây tổn thất không chấp nhận được?
- Khoảng mất dữ liệu nào có thể chấp nhận?
- Có cần khôi phục riêng từng tenant hoặc từng phiếu không?
- Cần những phụ thuộc nào để dịch vụ thật sự hoạt động trở lại?
- Ai có quyền khởi động phục hồi và xác nhận kết quả?
- Có cần duy trì chế độ đọc hoặc quy trình thủ công khi gặp sự cố không?
- Bằng chứng diễn tập nào sẽ được yêu cầu?

**RTO** là mục tiêu về thời gian khôi phục hoạt động trong phạm vi đã định nghĩa. **RPO** là mục tiêu về khoảng mất dữ liệu có thể chấp nhận, thể hiện bằng thời gian.

Một lịch backup không tự xác định RTO/RPO, và chưa chứng minh dữ liệu khôi phục được.

### 8.6. Lạm dụng, tích hợp và nhà cung cấp

Tìm hiểu thêm:

- Tác vụ nào có thể bị lặp lại để gây tốn tài nguyên hoặc trích xuất dữ liệu?
- Cần giới hạn khối lượng, tốc độ hoặc phạm vi theo chủ thể nào?
- Thông điệp trùng lặp, đến muộn hoặc sai thứ tự ảnh hưởng gì?
- Nhà cung cấp nào nhận dữ liệu và hỗ trợ điều tra khi có sự cố?
- Khi ngừng dịch vụ, dữ liệu và quyền truy cập được bàn giao hoặc hủy ra sao?
- Cam kết nào cần thể hiện trong hợp đồng hoặc tiêu chí nghiệm thu?

Các câu hỏi này giúp thu thập yêu cầu cho cả ứng dụng và quan hệ phụ thuộc, thay vì chỉ tập trung vào mã nguồn.

## 9. Chuyển phát biểu thô thành yêu cầu ứng viên

### 9.1. Một ví dụ từ phỏng vấn

Nhân viên hỗ trợ phát biểu:

> Tôi chỉ cần thấy phiếu của nhóm mình. Trưởng nhóm có thể điều chuyển phiếu, nhưng người ngoài công ty khách hàng không được thấy tệp đính kèm.

Phát biểu này chứa ít nhất ba vấn đề cần tách:

1. Quyền đọc theo nhóm được phân công.
2. Quyền điều chuyển phiếu.
3. Cách ly tenant đối với tệp đính kèm.

Các điểm cần làm rõ gồm:

- “Nhóm mình” là nhóm hiện tại hay cả nhóm từng tham gia?
- Trưởng nhóm được chuyển phiếu trong cùng tenant hay sang tenant khác?
- Quản trị viên tenant có quyền xem mọi phiếu không?
- Người dùng khách hàng được xem phiếu do mình tạo hay mọi phiếu của tổ chức?
- URL tải tệp có thể được chia sẻ hoặc sử dụng sau khi mất quyền không?
- Có quy trình hỗ trợ đặc biệt xuyên tenant không?

Chưa đủ câu trả lời thì giữ trạng thái cần làm rõ. Không tự điền một mô hình quyền quen thuộc rồi xem đó là yêu cầu đã được nghiệp vụ chấp nhận.

### 9.2. Cấu trúc diễn đạt ban đầu

Có thể dùng mẫu:

**Trong [phạm vi/điều kiện], [hệ thống hoặc thành phần] phải [hành vi bảo vệ] đối với [chủ thể, hành động, tài nguyên], với [giới hạn đo được nếu cần]; kết quả có thể kiểm chứng bằng [quan sát hoặc bằng chứng dự kiến].**

Mẫu này giúp phát hiện chỗ trống; không phải mọi yêu cầu đều cần một con số.

Ví dụ ứng viên sau khi các vai trò liên quan đã xác nhận quy tắc:

**SR-AC-02:** Khi một chủ thể yêu cầu đọc phiếu hoặc tải tệp của phiếu, hệ thống phải chỉ trả dữ liệu nếu chủ thể có quyền trong tenant sở hữu phiếu và đáp ứng quy tắc truy cập của vai trò: nhân viên hỗ trợ thuộc nhóm đang được phân công, quản trị viên tenant trong tenant của mình, hoặc khách hàng đối với phiếu do mình tạo. Trường hợp không xác định được quyền phải bị từ chối.

Đây là quy tắc giả định của ví dụ, không phải mô hình quyền mặc định cho mọi cổng hỗ trợ.

Nếu có quy trình hỗ trợ xuyên tenant, cần yêu cầu riêng mô tả điều kiện cấp quyền, người phê duyệt, thời hạn và dấu vết truy vết. Không tạo ngoại lệ ngầm trong SR-AC-02.

### 9.3. Ghi ý định kiểm chứng ngay khi thu thập

| Tình huống dự kiến | Kết quả mong đợi |
| --- | --- |
| Nhân viên đúng tenant, đúng nhóm được phân công | Đọc được phiếu và tệp trong phạm vi quyền |
| Nhân viên đúng tenant nhưng không thuộc nhóm và không có vai trò cho phép khác | Bị từ chối; không trả nội dung phiếu hoặc tệp |
| Chủ thể tenant A yêu cầu tài nguyên của tenant B | Bị từ chối; không rò rỉ dữ liệu thuộc tenant B |
| Khách hàng yêu cầu phiếu do khách hàng khác tạo | Bị từ chối theo quy tắc của ví dụ |
| Chủ thể gọi đường tải tệp trực tiếp | Vẫn chịu giới hạn quyền đã xác định |
| Không xác định được thuộc tính quyền cần thiết | Không cấp quyền dựa trên dữ liệu thiếu |

Bảng này là ý định kiểm chứng để các bên hiểu cùng một yêu cầu. Kế hoạch đánh giá chi tiết, dữ liệu thử và trường hợp mở rộng sẽ được phát triển ở bước sau.

## 10. Ghi nhận yêu cầu với đủ ngữ cảnh

### 10.1. Các trường nên có

| Trường | Mục đích |
| --- | --- |
| Mã và tên | Nhận diện ổn định để trao đổi và liên kết |
| Phát biểu yêu cầu | Hành vi hoặc thuộc tính bảo vệ cần đạt |
| Tài sản và phạm vi | Dữ liệu, giao diện, môi trường và chủ thể liên quan |
| Nguồn | Phỏng vấn, chính sách, nghĩa vụ hoặc phân tích đe dọa |
| Lý do và rủi ro | Giải thích tổn thất cần tránh |
| Người xác nhận | Vai trò có trách nhiệm quyết định nội dung |
| Ý định kiểm chứng | Bằng chứng hoặc quan sát giúp xác định kết quả |
| Mức ưu tiên đề xuất | Cơ sở để phân tích tiếp, chưa đồng nghĩa được quyền bỏ qua |
| Giả định và phụ thuộc | Điều kiện cần xác nhận hoặc hệ thống cần phối hợp |
| Câu hỏi mở | Nội dung chưa đủ rõ, người trả lời và hạn phản hồi |
| Trạng thái nội dung | Đề xuất, cần làm rõ hoặc đã xác nhận làm đầu vào đặc tả |
| Phiên bản và lịch sử | Biết điều gì thay đổi và vì sao |

Không cần biểu mẫu phức tạp cho mọi nhóm. Tuy nhiên, bỏ nguồn, người xác nhận hoặc ý định kiểm chứng sẽ khiến nhóm khó phân biệt điều đã thống nhất với suy đoán.

### 10.2. Bản ghi minh họa

~~~text
Mã: SR-AC-02
Tên: Giới hạn đọc phiếu và tệp theo tenant và quyền nghiệp vụ

Phạm vi:
- API danh sách, chi tiết, tìm kiếm và tải tệp của cổng hỗ trợ.
- Luồng xuất dữ liệu phải tham chiếu cùng chính sách và được làm rõ riêng.

Nguồn:
- SRC-BIZ-01: quy tắc phân công và vai trò được chủ nghiệp vụ xác nhận.
- SRC-ARCH-01: đường đọc và tải tệp.
- SRC-THREAT-01: tình huống truy cập chéo tenant.

Rủi ro:
- Lộ nội dung phiếu hoặc tệp của khách hàng khác.

Người xác nhận nội dung:
- Chủ nghiệp vụ và chủ dữ liệu.
- Nhóm bảo mật hỗ trợ phân tích; QA làm rõ khả năng kiểm chứng.

Ý định kiểm chứng:
- Có trường hợp được phép và bị từ chối cho từng vai trò.
- Bao gồm yêu cầu chéo tenant và đường tải tệp trực tiếp.

Câu hỏi mở:
- Chính sách đối với tác vụ đã bắt đầu trước khi người dùng mất quyền.
- Cơ chế hỗ trợ xuyên tenant nếu nghiệp vụ thực sự cần.

Trạng thái:
- Cần làm rõ các câu hỏi mở trước khi chốt phạm vi đầy đủ.
~~~

Bản ghi không che giấu điều chưa biết. Một phần quy tắc có thể đã được xác nhận trong khi phần khác vẫn cần làm rõ.

### 10.3. Danh sách ứng viên ban đầu

| Mã | Chủ đề ứng viên | Nguồn chính | Thông tin còn cần xác nhận |
| --- | --- | --- | --- |
| SR-ID-01 | Thu hồi quyền truy cập khi vô hiệu hóa tài khoản hoặc đổi nhóm | SRC-POL-01, SRC-BIZ-01 | Giới hạn thời gian và cách áp dụng cho phiên, token, tác vụ nền |
| SR-AC-02 | Giới hạn đọc phiếu và tệp theo tenant, vai trò, phân công | SRC-BIZ-01, SRC-THREAT-01 | Ngoại lệ hỗ trợ và các yêu cầu đang chạy |
| SR-DATA-03 | Bảo vệ dữ liệu phiếu trên các kênh truyền và nơi lưu | SRC-DATA-01, SRC-ARCH-01 | Phạm vi bản sao, quản lý khóa và trách nhiệm nhà cung cấp |
| SR-LOG-04 | Ghi sự kiện thay đổi quyền và xuất dữ liệu, tránh đưa bí mật vào log | SRC-OPS-01, SRC-POL-01 | Danh sách trường, thời hạn lưu, quyền đọc và ngưỡng gián đoạn |
| SR-REC-05 | Khôi phục chức năng thiết yếu và dữ liệu theo mục tiêu nghiệp vụ | SRC-BIZ-01, SRC-OPS-01 | RTO/RPO, phạm vi sự cố và cách đo |
| SR-LIFE-06 | Quản lý thời hạn lưu và xóa dữ liệu phiếu cùng các bản sao | SRC-DATA-01, SRC-OBL-01 | Căn cứ thời hạn, backup và tình huống giữ lại đặc biệt |
| SR-SUP-07 | Yêu cầu phối hợp bảo mật với nhà cung cấp email và lưu trữ | SRC-SUP-01, SRC-OBL-01 | Bằng chứng, thời gian phản hồi và trách nhiệm khi ngừng dịch vụ |
| SR-ABUSE-08 | Giới hạn lạm dụng tạo phiếu, tải tệp và xuất dữ liệu | SRC-THREAT-01, SRC-OPS-01 | Đơn vị giới hạn, ngưỡng và ảnh hưởng đến người dùng hợp lệ |

Danh sách trên chưa phải baseline đã phê duyệt. Nó giúp nhóm thấy phạm vi cần làm rõ và tránh bỏ quên trách nhiệm.

## 11. Xử lý ngưỡng chưa biết, mâu thuẫn và yêu cầu quá rộng

### 11.1. Không biến giả định thành con số bắt buộc

Nếu nghiệp vụ nói “thu hồi quyền ngay”, nhóm cần xác định:

- Sự kiện bắt đầu tính thời gian.
- Những đường truy cập phải ngừng.
- Có cho phép hoàn thành tác vụ đang chạy không.
- Tác động nếu có độ trễ.
- Cơ chế quan sát kết quả.

Nhóm kỹ thuật có thể đề xuất giới hạn **5 phút** cho một phạm vi cụ thể, nhưng phải ghi đây là đề xuất minh họa cần xác nhận. Không tự xem con số đó là yêu cầu của tiêu chuẩn hoặc sự đồng ý của chủ dữ liệu.

Tương tự, khi RTO/RPO chưa biết, ghi người xác định và căn cứ cần thu thập. Không lấy lịch backup hiện tại làm đáp án cho nhu cầu nghiệp vụ.

### 11.2. Giải quyết mâu thuẫn bằng phạm vi và mục đích

Ví dụ, vận hành muốn lưu nội dung request để điều tra; chủ dữ liệu muốn giảm sao chép thông tin khách hàng.

Nhóm cần cùng xác định:

1. Loại sự cố nào cần điều tra.
2. Trường nào thật sự cần để liên kết sự kiện.
3. Có thể dùng mã tài nguyên thay cho nội dung hay không.
4. Ai cần truy cập thông tin chi tiết và trong bao lâu.
5. Dữ liệu nào vẫn có thể liên kết đến cá nhân dù đã giảm chi tiết.
6. Nghĩa vụ và chính sách nào áp dụng.
7. Ai có quyền xác nhận cách giải quyết.

Kết quả có thể là yêu cầu logging theo nhóm sự kiện, quyền truy cập và thời hạn riêng. Không nên chọn “ghi tất cả” hoặc “không ghi gì” chỉ vì dễ triển khai.

### 11.3. Ghi nhận nghĩa vụ đúng mức chắc chắn

Đối với pháp luật, hợp đồng và chính sách:

- Ghi văn bản, phiên bản, điều khoản và phạm vi áp dụng được xác nhận.
- Phân biệt nội dung gốc với cách diễn giải thành yêu cầu phần mềm.
- Giao người có trách nhiệm xác nhận điểm chưa rõ.
- Ghi điều kiện áp dụng và cơ chế ngoại lệ nếu có.

Một yêu cầu có vẻ “thường gặp” chưa đủ để kết luận nó bắt buộc với mọi hệ thống. Ngược lại, đánh dấu ưu tiên thấp không làm một nghĩa vụ áp dụng trở thành tùy chọn.

### 11.4. Tách yêu cầu quá rộng

“Bảo vệ mọi dữ liệu” cần được chia theo tài sản, luồng và hành vi:

- Bảo vệ dữ liệu khi truyền.
- Kiểm soát truy cập khi đọc hoặc sửa.
- Bảo vệ dữ liệu lưu trữ và khóa.
- Giảm dữ liệu trong log và bản xuất.
- Kiểm soát vòng đời và việc xóa.
- Khôi phục dữ liệu trong phạm vi được phép.

Các yêu cầu con cần giữ liên kết về mục tiêu gốc. Việc tách nhỏ không được làm mất các đường xử lý dùng chung hoặc trách nhiệm xuyên thành phần.

## 12. Ưu tiên bước đầu và bàn giao

Thu thập chưa kết thúc chỉ vì đã có nhiều dòng trong backlog. Nhóm cần biết điều nào đã rõ, điều nào có thể gây quyết định sai và ai sẽ tiếp tục xử lý.

### 12.1. Cơ sở ưu tiên

Có thể xem xét:

- Tác động nếu yêu cầu không được đáp ứng.
- Mức phơi nhiễm và khả năng xảy ra tình huống gây hại.
- Nghĩa vụ đã được xác định là áp dụng.
- Tính thiết yếu của chức năng.
- Mức phụ thuộc của thiết kế vào câu trả lời.
- Chi phí sửa lại nếu phát hiện muộn.
- Độ bất định của thông tin hiện có.

Câu hỏi chưa rõ về cách ly tenant có thể cần xử lý trước một yêu cầu giao diện đã rõ, vì nó tác động đến mô hình dữ liệu và mọi đường truy cập.

Chi phí thực hiện là đầu vào lập kế hoạch. Nó không tự quyết định việc chấp nhận rủi ro hoặc bỏ qua nghĩa vụ. Những quyết định đó cần đúng người và đúng quy trình.

### 12.2. Gói đầu ra có thể bàn giao

Một gói đầu ra thu thập nên gồm:

1. Mô tả phạm vi và sơ đồ bối cảnh hoặc luồng dữ liệu phù hợp.
2. Danh sách bên liên quan và người xác nhận từng nhóm nội dung.
3. Danh mục tài sản, dữ liệu và nguồn thông tin.
4. Mục tiêu bảo vệ và kịch bản đe dọa đáng chú ý.
5. Danh sách yêu cầu ứng viên có nguồn và ý định kiểm chứng.
6. Giả định, mâu thuẫn, câu hỏi mở và người phụ trách.
7. Mức ưu tiên đề xuất cùng lý do.
8. Các thay đổi hoặc thông tin mới cần theo dõi.

Nhóm tiếp theo dùng đầu ra này để đặc tả chi tiết, phân tích phụ thuộc, thống nhất tiêu chí nghiệm thu và thiết lập baseline. Không cần chờ mọi chi tiết của toàn hệ thống hoàn tất mới làm rõ một phạm vi chức năng; cần kiểm soát phần chưa biết và mức ảnh hưởng của nó.

## 13. Các lỗi thường gặp khi thu thập

| Lỗi | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ hỏi chủ sản phẩm | Bỏ sót vận hành thực tế và nghĩa vụ dữ liệu | Lập danh sách vai trò, mời người thực hiện và người chịu trách nhiệm |
| Bắt đầu bằng chọn công cụ | Yêu cầu bị giới hạn theo tính năng sản phẩm | Hỏi về kết quả bảo vệ và rủi ro trước khi đánh giá giải pháp |
| Sao chép nguyên checklist | Có nhiều mục nhưng thiếu quy tắc nghiệp vụ | Đối chiếu từng mục với tài sản, chức năng và phạm vi |
| Chỉ xét luồng thành công | Bỏ sót thu hồi quyền, retry và lỗi phụ thuộc | Đi qua ngoại lệ, thao tác trực tiếp và tác vụ nền |
| Coi “nội bộ” là đủ an toàn | Bỏ qua tài khoản bị chiếm và lạm dụng nội bộ | Xem xét từng danh tính, quyền và ranh giới tin cậy |
| Ghi “nhanh”, “đầy đủ”, “an toàn” | Không thống nhất được kết quả đạt | Làm rõ điều kiện, quan sát và ngưỡng có căn cứ |
| Chốt con số khi chưa có người xác nhận | Giả định trở thành ràng buộc sai | Gắn nhãn đề xuất, ghi nguồn và giao người quyết định |
| Không ghi câu hỏi mở | Các đội tự diễn giải khác nhau | Duy trì danh sách vấn đề cùng người xử lý và hạn phản hồi |
| Dùng dữ liệu thật không cần thiết trong workshop | Tăng sao chép và người tiếp cận thông tin nhạy cảm | Dùng dữ liệu mẫu hoặc đã giảm chi tiết phù hợp |
| Xem yêu cầu nhà cung cấp là ngoài dự án | Không rõ trách nhiệm khi kiểm soát thất bại | Thu thập cam kết, bằng chứng và giới hạn dịch vụ |
| Không xác nhận lại biên bản | Phát biểu bị hiểu sai hoặc mất điều kiện đi kèm | Đọc lại kết luận và ghi người xác nhận |
| Chỉ thu thập một lần | Yêu cầu lỗi thời khi dữ liệu hoặc kiến trúc đổi | Xác định các sự kiện kích hoạt thu thập bổ sung |

## 14. Tiêu chí hoàn thành một vòng thu thập

Đây là tiêu chí về mức sẵn sàng của thông tin để chuyển sang bước tiếp theo. Nó chưa chứng minh hệ thống đã an toàn hoặc yêu cầu đã được triển khai.

- [ ] Phạm vi, tài sản, dữ liệu và các giao diện quan trọng đã được mô tả.
- [ ] Các vai trò nghiệp vụ, kỹ thuật, vận hành và quản trị liên quan đã được xem xét.
- [ ] Có nguồn cho các yêu cầu ứng viên quan trọng.
- [ ] Đã đi qua luồng bình thường, ngoại lệ và tình huống sử dụng sai.
- [ ] Xác thực, phân quyền, dữ liệu, logging và phục hồi đã được đặt vào bối cảnh hệ thống.
- [ ] Tác vụ nền, bản xuất, bản sao và nhà cung cấp không bị bỏ quên.
- [ ] Mỗi yêu cầu quan trọng có phạm vi và ý định kiểm chứng ban đầu.
- [ ] Giải pháp đề xuất được phân biệt với kết quả bảo vệ cần đạt.
- [ ] Các ngưỡng chưa xác nhận, giả định và nghĩa vụ chưa rõ được ghi minh bạch.
- [ ] Mâu thuẫn và câu hỏi mở có người xử lý.
- [ ] Người có trách nhiệm đã xác nhận nội dung thuộc thẩm quyền của mình.
- [ ] Đầu ra đủ để nhóm tiếp theo tiếp tục đặc tả mà không phải tự đoán các quy tắc trọng yếu.

Vòng thu thập cần mở lại khi có thay đổi đáng kể về mục tiêu nghiệp vụ, dữ liệu, vai trò người dùng, tích hợp, kiến trúc, nghĩa vụ hoặc thông tin đe dọa. Những yêu cầu mới phải tiếp tục giữ nguồn gốc và liên kết với phạm vi đã thay đổi.

## 15. Tài liệu tham khảo

- [OWASP SAMM — Security Requirements](https://owaspsamm.org/model/design/security-requirements/): phạm vi thực hành yêu cầu bảo mật cho phần mềm và nhà cung cấp.
- [OWASP SAMM — Software Requirements](https://owaspsamm.org/model/design/security-requirements/stream-a/): cách tìm và tổ chức yêu cầu theo chức năng, mục tiêu bảo vệ và các nguồn thông tin.
- [OWASP Application Security Verification Standard](https://asvs.owasp.org/): nguồn tham chiếu yêu cầu và hướng dẫn ghi phiên bản khi dẫn mã yêu cầu.
- [OWASP Developer Guide — Requirements in practice](https://devguide.owasp.org/en/03-requirements/01-requirements/): các nhóm nguồn yêu cầu trong phát triển phần mềm.
- [NIST SP 800-218 — SSDF Version 1.1](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf): thực hành PO.1 về xác định, duy trì và truyền đạt yêu cầu bảo mật.
