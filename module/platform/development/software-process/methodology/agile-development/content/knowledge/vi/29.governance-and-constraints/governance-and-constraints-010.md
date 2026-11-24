# Cân bằng yêu cầu kiểm soát tổ chức với tốc độ phản hồi của nhóm

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **quản trị (governance), mục tiêu kiểm soát, chính sách bắt buộc, cơ chế thực thi, bằng chứng tuân thủ và thủ tục phê duyệt**; giải thích vì sao Agile không đồng nghĩa bỏ quản trị.
2. Nhận diện các ràng buộc về **bảo mật, quyền riêng tư, dữ liệu, tài chính, kiến trúc, hợp đồng, pháp lý, vận hành và chất lượng**; chọn cách phối hợp tương xứng với mức rủi ro.
3. Thiết kế **guardrails** để nhóm được tự chủ trong những quyết định đủ an toàn, đồng thời giữ trách nhiệm giải trình và khả năng truy vết.
4. Làm rõ quyền quyết định theo **loại thay đổi, tác động và mức rủi ro**, không biến mọi quyết định nhỏ thành một hàng chờ phê duyệt.
5. Đưa kiểm soát vào **backlog refinement, Definition of Done, CI/CD, kiểm thử, phát hành và vận hành**, thu bằng chứng liên tục thay vì dồn tài liệu vào cuối dự án.
6. Phân biệt **Increment đạt DoD, triển khai, phát hành, chấp nhận rủi ro và ngoại lệ**, biết cách ứng xử khi có thay đổi khẩn hoặc kiểm soát không đáp ứng.
7. Đo **thời gian chờ quyết định, tuổi công việc, cycle time, lỗi thoát ra sản phẩm và chất lượng bằng chứng** để thử nghiệm cải tiến quản trị mà không hạ tiêu chuẩn an toàn.

## 1. Quản trị và tốc độ phản hồi có thật sự đối lập?

Một nền tảng học trực tuyến muốn cung cấp chức năng **“Tiếp tục học”**. Người học cần mở đúng bài gần nhất. Nhóm sản phẩm muốn thử nhanh cách bố trí nút trên trang chủ để biết học viên có sử dụng hay không. Tuy nhiên, tổ chức yêu cầu kiểm tra quyền truy cập, bảo vệ dữ liệu học viên, lưu dấu thay đổi và có người được phép quyết định việc phát hành.

Hai cách phản ứng cực đoan đều nguy hiểm:

- **Bỏ kiểm soát để nhanh:** Nhóm tự mở tính năng dù chưa kiểm tra đọc chéo tài khoản, coi quy trình bảo mật là “thủ tục hành chính”.
- **Áp cùng một quy trình nặng cho mọi thay đổi:** Đổi văn bản trên nút cũng phải chờ cùng vòng phê duyệt như migration dữ liệu tiến độ, khiến phản hồi người dùng đến muộn.

Vấn đề cần giải không phải lựa chọn **kiểm soát hoặc tốc độ**, mà là thiết kế **kiểm soát đúng mục đích, đúng rủi ro và đưa bằng chứng đến đúng người quyết định đủ sớm**.

> **Nguyên tắc:** Giữ vững **mục tiêu kiểm soát không thể thương lượng**, nhưng liên tục cải tiến **cách thực hiện kiểm soát** để giảm chờ đợi và phát hiện rủi ro sớm hơn.

Agile nhấn mạnh hợp tác, phần mềm hoạt động, phản hồi sớm và thích nghi. Những giá trị đó không xóa bỏ trách nhiệm của tổ chức với khách hàng, nhân viên, tài sản hay nghĩa vụ áp dụng. Ngược lại, quản trị tốt có thể **giúp nhóm tự tin phát hành phần mềm nhỏ, có thể kiểm chứng và khôi phục được**.

### Ví dụ nhanh

Tổ chức cần bảo đảm “không ai được đọc tiến độ riêng của tài khoản khác”. Đó là **mục tiêu kiểm soát**. Không nhất thiết mọi lần sửa nhãn giao diện đều cần họp bảo mật một giờ; nhưng thay đổi ở logic quyền truy cập cần **bằng chứng và trách nhiệm kiểm tra phù hợp**. Hình thức kiểm soát khác nhau, mục tiêu bảo vệ vẫn giữ nguyên.

## 2. Phân biệt sáu khái niệm nền tảng

| Khái niệm | Câu hỏi nó giải quyết | Ví dụ trong sản phẩm học tập |
| --- | --- | --- |
| **Governance / quản trị** | Ai có quyền quyết định, chịu trách nhiệm và kiểm tra điều gì? | Ai ưu tiên sản phẩm, ai quyết định chính sách bảo mật và điều kiện phát hành? |
| **Control objective / mục tiêu kiểm soát** | Điều không mong muốn nào cần ngăn ngừa, phát hiện hoặc xử lý? | Ngăn đọc/ghi tiến độ trái quyền, phát hiện thay đổi gây lỗi dữ liệu |
| **Policy / chính sách** | Quy tắc bắt buộc hoặc giới hạn hoạt động là gì? | API phải kiểm tra danh tính và quyền ở ranh giới có thẩm quyền |
| **Control / cơ chế kiểm soát** | Làm thế nào đáp ứng mục tiêu? | Kiểm tra phân quyền tại server, test truy cập chéo tài khoản |
| **Evidence / bằng chứng** | Làm sao biết kiểm soát đã hoạt động? | Test report, nhật ký thay đổi, review, kết quả kiểm chứng tích hợp |
| **Approval / phê duyệt** | Khi nào một người hoặc vai trò có thẩm quyền phải quyết định? | Cho phép thay schema ảnh hưởng dữ liệu theo chính sách |

### Điều dễ bị nhầm

**Một chữ ký không tự chứng minh kiểm soát hiệu quả.** Người phê duyệt có thể không nhìn thấy test hoặc không có đủ dữ liệu để đánh giá. Ngược lại, một kiểm thử tự động đáng tin có thể cung cấp bằng chứng tốt cho một phần yêu cầu, nhưng **không tự có quyền thay thế phê duyệt pháp lý hay nghiệp vụ** nếu chúng thực sự bắt buộc.

**Một tài liệu tồn tại không đồng nghĩa quy trình được tuân thủ.** Cần biết tài liệu liên kết với thay đổi nào, có còn đúng phiên bản không, tiêu chí nào được kiểm tra và ai có trách nhiệm xử lý khi không đạt.

### Các giới hạn phải tách rõ

- **Điều bắt buộc:** Luật, hợp đồng, nghĩa vụ an toàn/chất lượng và chính sách tổ chức đang có hiệu lực, trong phạm vi áp dụng.
- **Điều đội được chọn:** Công cụ, cách chia lát cắt, nhịp trao đổi, kỹ thuật kiểm thử và cải tiến workflow trong ranh giới được cho phép.
- **Điều cần xin quyết định:** Ngoại lệ, thay đổi chính sách, mức rủi ro vượt ngưỡng được ủy quyền hoặc cam kết có ảnh hưởng tới bên ngoài.

Không nên tự tuyên bố một điều là “luật yêu cầu” khi chưa có nguồn và người có thẩm quyền xác nhận. Nhiều bước thực tế chỉ là **thủ tục nội bộ có thể cải tiến**, khác với nghĩa vụ pháp lý không được bỏ.

## 3. Giá trị Agile có liên quan gì đến quản trị?

Trong môi trường có kiểm soát, việc tuân thủ không nên chỉ được kiểm tra lúc cuối dự án. Những thực hành Agile có thể **đưa kiến thức về rủi ro vào thời điểm quyết định còn dễ thay đổi**.

| Tư duy Agile | Ứng dụng vào quản trị |
| --- | --- |
| **Tương tác và cộng tác** | Người sản phẩm, phát triển, kiểm thử, bảo mật và vận hành cùng làm rõ tiêu chí sớm |
| **Phần mềm hoạt động** | Kiểm tra hành vi thật, không chỉ hồ sơ tuyên bố “đã tuân thủ” |
| **Hợp tác với khách hàng** | Làm rõ kỳ vọng giá trị, quyền riêng tư, chất lượng và trách nhiệm hợp đồng |
| **Phản hồi với thay đổi** | Điều chỉnh cách thực hiện kiểm soát khi rủi ro/kiến trúc/bối cảnh thay đổi, theo đúng thẩm quyền |
| **Giao tăng dần** | Chọn lát cắt nhỏ, tích hợp và kiểm chứng trước khi triển khai phạm vi lớn |
| **Cải tiến liên tục** | Xem kiểm soát nào giảm rủi ro, kiểm soát nào tạo chờ vô ích hoặc sai lệch |

**Không hiểu Agile là quyền bỏ mọi quy trình.** Tuyên ngôn Agile coi trọng những yếu tố bên trái hơn nhưng không khẳng định các yếu tố bên phải vô giá trị. Tài liệu, hợp đồng, quy trình và kế hoạch vẫn cần thiết ở **mức phục vụ mục tiêu thực tế**.

### Tình huống

Một bộ phận yêu cầu mọi thay đổi có “biên bản kiểm thử”. Đội có thể trao đổi xem **test report có phiên bản build, dữ liệu đầu vào, kết quả và người phụ trách** từ CI có thỏa mãn mục tiêu kiểm toán hay không. Nếu đáp ứng và người có thẩm quyền chấp thuận, tổ chức có thể tránh yêu cầu developer **chụp ảnh màn hình thủ công cho cùng một kết quả** mỗi lần.

Thay đổi cách tạo bằng chứng khác hoàn toàn với việc **bỏ bằng chứng**.

## 4. Bản đồ các nguồn ràng buộc cần xem xét

Ràng buộc đến từ nhiều nguồn và không phải tất cả có cùng người ra quyết định.

| Nguồn | Ví dụ câu hỏi | Bên có thể liên quan |
| --- | --- | --- |
| **Pháp lý/quy định trong phạm vi áp dụng** | Dữ liệu nào được xử lý, lưu giữ, chia sẻ? Có nghĩa vụ báo cáo hay phê duyệt nào? | Pháp chế, tuân thủ, quản lý dữ liệu |
| **Hợp đồng và cam kết dịch vụ** | Đối tác yêu cầu thời gian báo trước, tương thích API hoặc chứng từ nào? | Người quản lý hợp đồng/sản phẩm, vận hành |
| **Bảo mật và quyền riêng tư** | Ai được quyền đọc/ghi; có cần review mối đe dọa? | Bảo mật, người chịu trách nhiệm dữ liệu, Developers |
| **Kiến trúc và kỹ thuật chung** | Thay đổi schema có phá hệ thống khác? Công cụ nào bắt buộc? | Kiến trúc, nhóm nền tảng, nhóm phụ thuộc |
| **Chất lượng sản phẩm** | Definition of Done chung, test rủi ro và điều kiện dùng được? | Scrum Team, người có chuyên môn kiểm thử |
| **Vận hành và an toàn dịch vụ** | Ai trực, ai khôi phục, khi nào cần kế hoạch rollback? | Vận hành, chủ sở hữu dịch vụ |
| **Tài chính và nguồn lực** | Ai có quyền cam kết chi phí, mua dịch vụ, tăng dung lượng? | Người quản lý ngân sách, mua sắm |
| **Sản phẩm và trải nghiệm người dùng** | Phạm vi, thứ tự ưu tiên, cam kết với người dùng là gì? | Product Owner, stakeholders |
| **Đạo đức và tiếp cận** | Có nhóm người dùng bị loại trừ, bị theo dõi quá mức? | Sản phẩm, thiết kế, pháp chế/chuyên gia phù hợp |
| **Tổ chức phối hợp** | Việc nào phải có hai vai trò độc lập, việc nào đội được tự quyết? | Vai trò kiểm soát, quản lý và nhóm thực hiện |

Những dòng trên chỉ là **bản đồ tìm câu hỏi**, không chứng minh một quy định cụ thể có hiệu lực cho sản phẩm nào. Khi cần, phải xác minh **văn bản, phạm vi, phiên bản và chủ thể có thẩm quyền**.

### Đừng gom tất cả thành “bộ phận Compliance”

Nếu việc chờ liên quan tới **contract API**, có thể vấn đề là nhóm cung cấp và sử dụng chưa chốt ngữ nghĩa. Nếu liên quan **quyền truy cập**, cần người am hiểu bảo mật. Nếu liên quan **ngày phát hành**, có thể người sản phẩm hoặc chủ dịch vụ mới là người quyết định. Gửi mọi vấn đề qua một đầu mối chung thường chỉ tạo **một hàng đợi mới**.

## 5. Bắt đầu từ mục tiêu kiểm soát, không từ số bước phê duyệt

Trước khi yêu cầu một biểu mẫu hoặc chữ ký, hãy xác định:

1. **Tài sản/đối tượng cần bảo vệ:** Dữ liệu học viên, hệ thống thanh toán, quyền truy cập, khả năng phục vụ.
2. **Kịch bản gây hại:** Đọc chéo tài khoản, dữ liệu bị ghi lùi, không có khả năng khôi phục, thay đổi trái quyền.
3. **Mức tác động và bất định:** Nếu xảy ra, ai bị ảnh hưởng, mức nghiêm trọng ra sao, có thể phát hiện và đảo ngược không?
4. **Mục tiêu kiểm soát:** Cần phòng ngừa, phát hiện hay có năng lực ứng phó nào?
5. **Cơ chế phù hợp:** Test, xác thực, review độc lập, hạn chế quyền, giám sát, phê duyệt có điều kiện.
6. **Bằng chứng cần giữ:** Ai đã làm gì, phiên bản nào, kết quả ra sao, vì sao quyết định được đưa ra?
7. **Người có thẩm quyền và ngưỡng cần leo thang:** Đội được tự quyết tới đâu?

### Ví dụ chuyển quy tắc mơ hồ thành kiểm soát có nghĩa

**Yêu cầu ban đầu:** “Mọi thay đổi phải qua kiến trúc sư.”

**Câu hỏi cải tiến:** Kiến trúc sư đang giúp kiểm soát điều gì: thay contract công khai, dữ liệu nhạy cảm, chi phí hạ tầng lớn, hiệu năng, hay thống nhất thiết kế?

**Thiết kế có thể phù hợp hơn:**

- Thay đổi nằm trong contract và kiến trúc đã duyệt: kiểm tra tự động, review theo quyền đội đã được ủy quyền.
- Thay đổi API ảnh hưởng consumer: phải có contract review và bằng chứng tương thích.
- Thay đổi hướng lưu dữ liệu hoặc mô hình quyền: cần chuyên môn/độc lập xem xét theo chính sách.

Nếu có một quy định tổ chức thực sự yêu cầu chữ ký riêng **cho mọi thay đổi**, đội không tự ý bỏ. Nhưng có thể **đề xuất sửa chính sách dựa trên rủi ro và bằng chứng**, qua người có thẩm quyền.

## 6. Cách tiếp cận dựa trên rủi ro, không phải cảm giác “việc nhỏ”

**Risk-based governance** điều chỉnh độ sâu kiểm soát theo rủi ro thực. Không nên dùng số dòng code, độ dài PR hoặc số story points làm đại diện duy nhất cho nguy cơ.

### Một kịch bản rủi ro nên ghi

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Điều kiện kích hoạt** | Tình huống nào có thể xảy ra? | Client đổi tài khoản trong khi request trước còn đang chạy |
| **Sự kiện không mong muốn** | Hệ thống làm sai điều gì? | Hiển thị tiến độ của A trong phiên của B |
| **Tác động** | Ai và điều gì bị ảnh hưởng? | Quyền riêng tư, niềm tin, nghĩa vụ bảo vệ dữ liệu |
| **Khả năng xảy ra** | Có cơ chế/dữ liệu nào cho thấy mức rủi ro? | Cache theo thiết bị, response đến muộn; xác suất chưa rõ |
| **Khả năng phát hiện** | Test/giám sát có tìm ra trước khi gây hại không? | Integration test đổi phiên, giám sát lỗi bất thường |
| **Khả năng phục hồi** | Có thể sửa, thu hồi, phục hồi dữ liệu không? | Dữ liệu đã bị xem có thể không thể “thu hồi” hoàn toàn |
| **Ràng buộc** | Có nghĩa vụ không thể bỏ qua không? | Kiểm soát quyền truy cập theo chính sách và yêu cầu áp dụng |

### Bốn yếu tố cần cân nhắc cùng nhau

- **Mức tác động:** Bất tiện nhỏ hay ảnh hưởng nghiêm trọng tới dữ liệu, người dùng và tổ chức?
- **Khả năng xảy ra:** Có bằng chứng, điều kiện kích hoạt hoặc tiền sử sự cố không?
- **Khả năng phát hiện trước khi gây hại:** Kiểm thử/giám sát hiện có có đủ không?
- **Khả năng đảo ngược và mức chưa biết:** Có thể rollback an toàn hay lỗi dữ liệu khó khắc phục?

Một việc chỉ thay **một dòng code** ở logic phân quyền vẫn có thể rủi ro cao. Một thay đổi lớn về nội dung tài liệu có thể ít rủi ro kỹ thuật hơn nhưng cần người có quyền nội dung xác nhận nếu ảnh hưởng cam kết pháp lý.

### Giới hạn của ma trận điểm

Thang thấp/trung bình/cao có thể giúp thảo luận nhưng **không phải phép tính xác suất**. Nếu chưa có dữ liệu, hãy ghi “chưa biết” và chọn biện pháp giảm bất định; không ép một số chính xác giả để một công việc lọt ngưỡng tự động.

## 7. Mô hình phân tầng kiểm soát theo loại thay đổi

Một tổ chức có thể thiết kế các **đường xử lý thay đổi** khác nhau, miễn đúng chính sách và quyền được giao.

| Tầng minh họa | Ví dụ | Kiểm soát có thể phù hợp | Quyền quyết định |
| --- | --- | --- | --- |
| **Đã được ủy quyền, rủi ro thấp** | Sửa lỗi chính tả không đổi nghĩa nghiệp vụ, tài nguyên hoặc quyền | CI, review theo chính sách, DoD; deploy tự động nếu được cho phép | Đội tự thực hiện trong guardrails |
| **Thay đổi thông thường, tác động có kiểm soát** | Bổ sung API không phá contract, thay UI cho một nhóm người dùng | Contract/integration tests, owner review, kế hoạch rollout | Người được ủy quyền tại sản phẩm/dịch vụ |
| **Rủi ro cao hoặc khó đảo ngược** | Thay logic quyền, migration dữ liệu nhạy cảm, thay contract phá tương thích | Đánh giá chuyên môn độc lập theo chính sách, thử khôi phục, bằng chứng rủi ro và phê duyệt cần thiết | Vai trò có thẩm quyền tương ứng |
| **Khẩn cấp** | Vá lỗ hổng nghiêm trọng, phục hồi sự cố production | Quy trình khẩn được định nghĩa trước, người chịu trách nhiệm rõ, kiểm chứng tối thiểu an toàn, hậu kiểm | Vai trò ứng phó khẩn được ủy quyền |

**Bảng này chỉ là ví dụ thiết kế**, không phải chính sách hiện có của bất kỳ tổ chức nào. Mức tầng và thẩm quyền phải được xác nhận với ràng buộc thực tế.

### Nguyên tắc phân tầng

1. **Rủi ro và nghĩa vụ** quyết định mức kiểm soát, không phải chức danh của người viết code.
2. **Bằng chứng có thể tái sử dụng:** Kết quả test/scan đã đủ tốt không nên được chép lại thủ công ở nhiều nơi.
3. **Thời gian quyết định tương xứng:** Không biến thay đổi rủi ro thấp thành việc chờ nhiều ngày vì lịch họp cố định.
4. **Không tự động hóa sự chấp thuận không có thẩm quyền:** Chỉ tự động thực hiện những quyết định đã được ủy quyền bằng chính sách rõ.
5. **Ngoại lệ có dấu vết:** Không tạo một lối tắt ngầm khiến tiêu chuẩn bắt buộc mất hiệu lực.

## 8. Guardrails: quyền tự chủ bên trong giới hạn an toàn

**Guardrail** là giới hạn và tiêu chuẩn giúp đội **tự quyết nhanh về phương pháp**, đồng thời giữ rủi ro và trách nhiệm trong phạm vi được phép.

Ví dụ:

> “Nhóm có thể tự deploy thay đổi thuộc loại đã được ủy quyền khi các kiểm tra bắt buộc đạt, không thay ranh giới quyền dữ liệu, có telemetry và khôi phục phù hợp. Những thay đổi ngoài loại này phải qua quy trình đánh giá theo rủi ro.”

Nguyên tắc này khác với:

> “Nhóm phải xin phép một người quản lý cho mọi lần merge.”

### Bốn yếu tố của guardrail tốt

1. **Phạm vi quyền:** Loại thay đổi, hệ thống, môi trường và mức tác động được tự quyết.
2. **Điều kiện chất lượng:** Test, review, DoD, phân quyền, giám sát hoặc khôi phục cần đạt.
3. **Ngưỡng leo thang:** Khi xuất hiện dữ liệu nhạy cảm, contract breaking, sự cố, chi phí lớn hoặc thiếu bằng chứng.
4. **Minh bạch:** Có dấu vết thay đổi, kết quả kiểm tra, trách nhiệm và cách xem lại quyết định.

### Guardrail không giống quy trình dài

Một guardrail rõ có thể **giảm số bước cần xin phép** vì phần lớn quyết định thông thường đã được ủy quyền. Nhưng guardrail chỉ có ích khi người thực hiện **hiểu điều gì nằm ngoài phạm vi** và không cố phân loại rủi ro thấp để tránh kiểm soát.

## 9. Quyền quyết định: ai được làm gì, ai chịu trách nhiệm?

Một nguyên nhân lớn của chờ đợi là mọi người biết “cần phê duyệt”, nhưng không biết **ai phê duyệt, theo tiêu chí nào và khi nào**.

### Ma trận quyết định minh họa

| Quyết định | Vai trò chịu trách nhiệm chính | Những bên nên tham gia | Điều kiện leo thang |
| --- | --- | --- | --- |
| Ưu tiên Product Backlog | Product Owner trong Scrum | Developers, người dùng, stakeholders | Thay đổi cam kết quan trọng hoặc vượt thẩm quyền |
| Cách hiện thực kỹ thuật trong guardrails | Developers/đội chịu trách nhiệm kỹ thuật | Reviewer, nhóm phụ thuộc | Tác động kiến trúc/contract ngoài phạm vi đã cho |
| Tiêu chuẩn chất lượng chung cho sản phẩm Scrum | Scrum Team/những Scrum Team cùng sản phẩm theo Scrum | Chuyên môn bảo mật, vận hành, tiêu chuẩn tổ chức | Tiêu chuẩn bắt buộc hoặc nghĩa vụ ngoài phạm vi đội |
| Thay chính sách phân quyền | Vai trò được giao quyền bảo mật/chủ thể dữ liệu | Sản phẩm, Developers, vận hành | Rủi ro cao, ảnh hưởng dữ liệu hoặc nghĩa vụ |
| Thay hợp đồng API công khai | Chủ sở hữu hợp đồng/quyền thay đổi được chỉ định | Consumer, provider, người quản lý sản phẩm | Thay đổi phá tương thích hoặc cam kết đối tác |
| Triển khai thay đổi được ủy quyền | Chủ sở hữu dịch vụ/đội theo release policy | CI, vận hành khi cần | Kiểm soát thất bại, thiếu khôi phục, thay đổi ngoài tầng |
| Xử lý sự cố khẩn | Vai trò ứng phó được ủy quyền theo kế hoạch sự cố | Nhóm liên quan, bảo mật khi áp dụng | Vượt mức quyền, nghĩa vụ báo cáo, tác động diện rộng |
| Chấp nhận rủi ro còn lại | Người có **thẩm quyền rủi ro** theo chính sách | Người cung cấp bằng chứng và chủ sở hữu tài sản | Không thể chấp nhận nếu trái nghĩa vụ bắt buộc |

Ma trận này là **ví dụ phương pháp**, không cấp quyền thực tế cho bất kỳ vai trò nào. Trong một tổ chức, quyền ký hợp đồng, chấp nhận rủi ro hoặc phê duyệt production có thể được quy định cụ thể.

### Người được hỏi ý kiến không tự là người có quyền phủ quyết

Một chuyên gia có thể cung cấp ý kiến và bằng chứng. Điều đó không đồng nghĩa mọi thay đổi phải chờ họ ký duyệt nếu họ **không có trách nhiệm phê duyệt theo chính sách**.

Ngược lại, khi cần **separation of duties** (phân tách nhiệm vụ) để tránh cùng một người vừa thực hiện vừa tự phê duyệt một hành động có rủi ro, không được bỏ bước độc lập chỉ vì “nhóm tự quản”.

## 10. Phân tách nhiệm vụ và tính độc lập có mục đích

Trong một số quy trình, người lập thay đổi và người phê duyệt phải **không phải cùng một người**. Mục tiêu có thể là giảm sai sót, lạm dụng quyền, xung đột lợi ích hoặc rủi ro kiểm toán.

### Câu hỏi trước khi đặt quy tắc độc lập

- Loại thay đổi nào có thể gây tác động không thể tự khôi phục?
- Có yêu cầu độc lập từ hợp đồng, pháp lý, chính sách hoặc đánh giá rủi ro không?
- Cần **kiểm tra kỹ thuật độc lập**, **phê duyệt kinh doanh**, hay cả hai?
- Có thể phân quyền theo nhóm vai trò thay vì chỉ một tên cá nhân?
- Có thể thu bằng chứng tự động trước khi người có thẩm quyền xem xét?
- Nếu người phê duyệt vắng mặt, có **đầu mối dự phòng được ủy quyền** không?

### Ví dụ tránh điểm nghẽn

Tổ chức yêu cầu review độc lập cho thay đổi logic phân quyền. Thay vì chỉ một người duyệt và tạo hàng đợi dài, tổ chức có thể **đào tạo và ủy quyền một nhóm reviewer đủ năng lực**, đặt tiêu chí kiểm tra rõ, dùng test liên quan tự động và giữ lịch sử review. Việc thay đổi cách tổ chức reviewer phải được **người có thẩm quyền chấp thuận**.

**Không đánh đổi độc lập bắt buộc bằng tự động phê duyệt của chính tác giả** nếu cơ chế đó trái mục tiêu kiểm soát.

## 11. Đưa quản trị vào refinement thay vì chờ cuối Sprint

Nhiều vòng phê duyệt chậm vì rủi ro chỉ được nhìn thấy khi code đã xong. Khi ấy lựa chọn sửa đổi thường đắt hơn và deadline gây áp lực bỏ qua tiêu chuẩn.

### Một cuộc refinement theo rủi ro

Với user story “Học viên tiếp tục bài gần nhất”, đội hỏi:

1. **Ai sử dụng và giá trị là gì?** Đúng tài khoản, đúng bài, không cần tìm lại thủ công.
2. **Dữ liệu nào được đọc/ghi?** Tiến độ, quyền khóa, thông tin phiên, nhật ký hoạt động.
3. **Ranh giới nào có rủi ro?** UI–API, xác thực–ủy quyền, cache, request đến muộn, đa thiết bị.
4. **Có chính sách bắt buộc nào?** Phân quyền, dữ liệu, lưu trữ, review và release trong phạm vi sản phẩm.
5. **Cần ai tham gia sớm?** Chuyên môn bảo mật hoặc dữ liệu khi thay đổi làm tăng rủi ro.
6. **Điều kiện chấp nhận cụ thể?** Không trả dữ liệu sai người, không báo đã lưu khi chưa có xác nhận.
7. **Phần nhỏ nhất có thể dùng an toàn?** Mở đúng bài còn quyền, chưa cần đồng bộ vị trí video từng giây.

### Phân biệt ba loại đầu ra của refinement

- **Điều đã xác nhận:** Ví dụ server phải kiểm tra quyền trước khi trả dữ liệu.
- **Giả định chưa chốt:** Ví dụ cách xử lý hai tiến độ ghi cùng lúc.
- **Hành động giảm bất định:** Trao đổi với người có quyền nghiệp vụ, spike kỹ thuật giới hạn hoặc test thử hợp đồng.

Đừng biến mọi câu hỏi chưa rõ thành một giấy phép để code theo suy đoán. Và đừng biến refinement thành một đợt phê duyệt cố định cho mọi story; chỉ mời người đúng theo **tác động rủi ro**.

## 12. Definition of Done và kiểm soát chất lượng chung

Trong Scrum, **Definition of Done (DoD)** mô tả trạng thái Increment khi đáp ứng các tiêu chuẩn chất lượng của sản phẩm. Nếu có tiêu chuẩn DoD ở cấp tổ chức, Scrum Team phải tuân theo ít nhất tiêu chuẩn đó; nếu không có, Scrum Team tạo DoD phù hợp. Nhiều Scrum Team làm trên **cùng một sản phẩm phải cùng định nghĩa và tuân thủ một DoD**.

### Một DoD minh họa

| Chiều | Điều kiện chất lượng chung có thể áp dụng | Bằng chứng |
| --- | --- | --- |
| **Nghiệp vụ** | AC đã được kiểm chứng, kể cả trường hợp lỗi quan trọng | Acceptance tests, ví dụ nghiệp vụ |
| **Tích hợp** | Không phá hợp đồng/Increment có liên quan | CI, contract/integration tests |
| **Quyền và dữ liệu** | Các kiểm soát bắt buộc theo rủi ro đạt | Security/data test, review chuyên môn khi áp dụng |
| **Độ tin cậy** | Không gây lỗi không thể chấp nhận trong trường hợp đã xác định | Kiểm thử lỗi phụ thuộc, retry, migration khi cần |
| **Vận hành** | Các tín hiệu và thông tin cần thiết để hỗ trợ/khôi phục sẵn sàng | Telemetry, runbook hoặc kiểm tra khôi phục phù hợp |
| **Duy trì** | Review và ghi quyết định cần thiết đã thực hiện | PR, test, decision record có phiên bản |

Đây là **DoD ví dụ**, không phải danh sách bắt buộc chung cho mọi sản phẩm. Không phải một thay đổi văn bản giao diện phải chạy mọi kiểm thử migration, nhưng không được bỏ các tiêu chí rủi ro hoặc nghĩa vụ áp dụng.

### Đừng trộn DoD với mọi approval của tổ chức

Phân biệt:

- **Acceptance Criteria:** Hành vi riêng của backlog item.
- **DoD:** Chất lượng chung của Increment, điều kiện để được coi là hoàn thành.
- **Policy gate:** Một kiểm soát hoặc quyền quyết định theo loại thay đổi.
- **Release criteria:** Điều kiện đưa phiên bản/khả năng tới người dùng, có thể gồm lịch, hợp đồng, migration, truyền thông hoặc phê duyệt bổ sung.

**Increment đạt DoD không tự động nghĩa là được phát hành ngay**, và **code đã merge không tự là Increment đạt DoD**. Trong Scrum, Sprint Review không phải cổng bắt buộc để phát hành Increment.

### Khi thiếu tiêu chí bắt buộc

Nếu security integration test còn thất bại, không được sửa trạng thái Done để đẹp báo cáo. Có thể **thu hẹp phạm vi an toàn, sửa kiểm soát, làm rõ bằng chứng, hoặc chưa release**. Một người “chấp nhận rủi ro” không thể hợp pháp hóa việc vi phạm yêu cầu bắt buộc mà họ không có quyền miễn trừ.

## 13. Tự động hóa kiểm soát nhưng không tự động hóa trách nhiệm

Đưa kiểm soát vào công cụ giúp giảm thời gian **chờ người chuyển thông tin** và tạo dấu vết có thể truy xuất.

### Các kỹ thuật thường phù hợp

| Kiểm soát | Có thể tự động hóa phần nào? | Phần vẫn cần con người |
| --- | --- | --- |
| **Kiểm tra code** | Build, test, static checks, dependency checks | Phân tích nghiệp vụ, rủi ro và những vùng test không bao phủ |
| **Bảo mật** | Secret scanning, kiểm tra cấu hình, một số security tests | Đánh giá threat model, ngoại lệ và rủi ro không nhìn thấy qua tool |
| **API/data** | Contract test, schema validation, migration checks | Xác nhận ngữ nghĩa nghiệp vụ, lộ trình consumer và quyền dữ liệu |
| **Bằng chứng release** | Link artifact, test result, commit, reviewer, pipeline, environment | Quyết định trong trường hợp phức tạp và điều kiện hợp đồng |
| **Quyền truy cập** | Role-based permissions, kiểm tra expiry, logs, cảnh báo | Cấp/thu hồi quyền đặc biệt theo thẩm quyền |
| **Observability** | Error rate, latency, alert và telemetry | Phân loại tác động, xử lý sự cố và quyết định khôi phục |

### “Policy as code” là gì?

**Policy as code** là biểu diễn một số quy tắc kiểm soát bằng cấu hình hoặc logic có thể thực thi và kiểm thử tự động, ví dụ:

- Không cho merge khi test phân quyền bắt buộc thất bại.
- Không deploy artifact không có provenance hoặc thông tin build cần thiết.
- Không áp dụng migration nếu chưa có bước xác minh tương thích theo loại thay đổi.
- Chỉ cho role đã được ủy quyền thao tác ở môi trường tương ứng.

Không phải mọi chính sách đều có thể biến thành một biểu thức máy móc. **Ngữ nghĩa nghiệp vụ, mức rủi ro và quyết định có thẩm quyền** đôi khi vẫn cần đánh giá con người.

## 14. Thiết kế một đường kiểm soát trong CI/CD

Đội có thể đưa các kiểm tra có ý nghĩa vào **đường đi thông thường** của thay đổi, thay vì đợi cuối Sprint mới tạo một bộ hồ sơ.

### Một pipeline khái niệm

~~~mermaid
flowchart TD
    A["PBI: mục tiêu + AC + phân loại rủi ro"] --> B["Thay đổi nhỏ + test trong codebase"]
    B --> C["CI: build, unit, contract, kiểm tra bắt buộc"]
    C --> D{"Bằng chứng kỹ thuật đạt?"}
    D -- "Không" --> E["Sửa lỗi hoặc làm rõ rủi ro"]
    E --> B
    D -- "Có" --> F{"Có tác động cần xét độc lập?"}
    F -- "Không, nằm trong quyền đã ủy quyền" --> G["Merge/tích hợp theo policy"]
    F -- "Có" --> H["Review có thẩm quyền + bằng chứng"]
    H --> I{"Quyết định hợp lệ?"}
    I -- "Chưa" --> E
    I -- "Đạt" --> G
    G --> J["Integration tests + DoD"]
    J --> K{"Increment đạt chất lượng?"}
    K -- "Chưa" --> E
    K -- "Đạt" --> L["Release khi đủ điều kiện"]
    L --> M["Giám sát + phản hồi + truy vết"]
    M --> A
~~~

Sơ đồ chỉ là **một mô hình có thể tùy chỉnh**, không khẳng định mọi thay đổi phải đi qua từng ô theo thứ tự cứng. Review bảo mật có thể diễn ra rất sớm, ngay trong refinement; một số kiểm tra chạy song song; release có chính sách khác nhau theo mức rủi ro.

### Pseudocode minh họa điều kiện triển khai

~~~yaml
# Chỉ minh họa quy tắc ra quyết định, KHÔNG phải cấu hình chạy trực tiếp.
change_policy:
  standard_pre_authorized:
    conditions:
      - within_approved_change_scope
      - required_ci_checks_pass
      - required_peer_review_present
      - definition_of_done_met
    action: may_proceed_under_delegated_authority

  sensitive_data_or_breaking_contract:
    conditions:
      - risk_assessment_recorded
      - independent_review_when_required
      - compatibility_and_recovery_evidence
      - definition_of_done_met
    action: authorized_decision_required

  failed_mandatory_control:
    action: stop_and_remediate_or_follow_authorized_exception_process
~~~

**Lưu ý:** Điều kiện tự động hóa phải được **kiểm tra và quản lý phiên bản**. Một trường phân loại do tác giả tự chọn không nên đủ để biến thay đổi dữ liệu nhạy cảm thành “rủi ro thấp”; cần kiểm soát khả năng lạm dụng hoặc phân loại sai.

### Điều cần đảm bảo

- Policy có chủ sở hữu, phiên bản và phạm vi áp dụng.
- Những điều kiện quan trọng được kiểm tra trên **artifact/commit và môi trường thực được phát hành**.
- Không có lối tắt bí mật qua tài khoản đặc quyền hoặc thao tác thủ công ngoài nhật ký.
- Khi kiểm soát đỏ, thông báo nói rõ **điều gì thiếu và làm thế nào khắc phục**.
- Bằng chứng được giữ theo chính sách lưu trữ, không làm rò rỉ secret hoặc dữ liệu cá nhân.

## 15. Bằng chứng tuân thủ liên tục và truy vết quyết định

Một thay đổi có thể đáp ứng chính sách nhưng đội không chứng minh được nếu mất dấu phiên bản test, quyết định và artifact. Ngược lại, hàng chục file đính kèm có thể trông đầy đủ nhưng không chỉ ra **bản nào thực sự được phát hành**.

### Chuỗi bằng chứng có ý nghĩa

~~~text
Mục tiêu sản phẩm / yêu cầu kiểm soát
    -> Product Backlog Item và tiêu chí chấp nhận
    -> Thay đổi code / cấu hình / schema cụ thể
    -> Bằng chứng review và kiểm thử theo rủi ro
    -> Artifact/version được build và tích hợp
    -> Điều kiện DoD và quyết định release theo chính sách
    -> Deployment/feature flag và tín hiệu vận hành
    -> Sự cố/ngoại lệ/khắc phục, nếu có
~~~

Mục tiêu của truy vết **không phải tạo 100 liên kết thủ công**. Một hệ thống issue–PR–pipeline–artifact–release có thể tự tạo nhiều liên kết khi tên, ID và quyền được quản lý nhất quán.

### Một bản ghi quyết định ngắn

| Trường | Ví dụ nội dung |
| --- | --- |
| **Decision ID** | GOV-EXAMPLE-014 |
| **Thay đổi** | Bổ sung kiểm tra quyền trước khi trả tiến độ |
| **Loại/tác động** | Có thể ảnh hưởng danh tính và dữ liệu; cần review theo policy |
| **Bằng chứng** | Security integration test, review thiết kế, contract test, kết quả build |
| **Người quyết định** | Vai trò được ủy quyền theo chính sách, không mặc định là tác giả |
| **Quyết định và lý do** | Cho phép sau khi đủ điều kiện, hoặc chưa cho phép vì thiếu bằng chứng |
| **Phiên bản/phạm vi** | Commit, artifact, môi trường và người dùng được mở theo chính sách |
| **Rủi ro còn lại** | Những giới hạn hoặc điều chưa chắc, kế hoạch theo dõi |
| **Ngày xem lại** | Mốc cần xác nhận nếu có điều kiện hoặc ngoại lệ |

### Ba yêu cầu về chất lượng bằng chứng

1. **Đúng đối tượng:** Test và review liên kết với phiên bản/phạm vi thay đổi thực.
2. **Đúng thời điểm:** Bằng chứng chưa hết hiệu lực vì schema, quyền hoặc môi trường đã đổi.
3. **Đủ tin cậy:** Có thể xác minh kết quả, hiểu giới hạn và kiểm tra quyền truy cập dữ liệu bằng chứng.

Không nên in token hoặc thông tin nhận diện học viên vào báo cáo kiểm soát chỉ để auditor có “nhiều bằng chứng”.

## 16. Thủ tục phê duyệt: giảm hàng chờ mà không giảm quyền kiểm soát

Thời gian thực hiện kiểm tra và thời gian **đợi người kiểm tra** là hai phần khác nhau. Một tổ chức có thể giữ nguyên tiêu chuẩn chất lượng nhưng giảm chờ bằng cách tổ chức trách nhiệm tốt hơn.

### Những nguồn chờ phổ biến

| Hiện tượng | Nguyên nhân có thể có | Cách cải tiến cần kiểm chứng |
| --- | --- | --- |
| Mọi thay đổi chờ cuộc họp thứ Sáu | Không phân tầng rủi ro/ủy quyền | Xác định loại thay đổi đã được phê duyệt trước theo policy |
| Chỉ một chuyên gia có thể review | Phụ thuộc cá nhân và thiếu năng lực dự phòng | Đào tạo reviewer, ủy quyền theo tiêu chuẩn, pairing |
| Người duyệt không biết cần xem gì | Bằng chứng hoặc tiêu chí mơ hồ | Checklist rủi ro ngắn, report liên kết với artifact |
| Review ở cuối Sprint mới phát hiện vấn đề | Người có chuyên môn tham gia muộn | Threat/contract/data review từ refinement khi cần |
| Cùng một test report nhập ba hệ thống | Hệ thống thiếu liên kết và tự động hóa | Sinh bằng chứng từ CI và kết nối nơi lưu có kiểm soát |
| Không ai biết ai có quyền chấp nhận ngoại lệ | Trách nhiệm và ngưỡng chưa xác định | Ma trận quyền quyết định, kênh leo thang rõ |
| Mọi thay đổi đều bị coi như sản phẩm mới | Phạm vi kiểm soát quá rộng hoặc chưa cập nhật | Xem lại trigger và điều kiện áp dụng có thẩm quyền |

### Kỹ thuật cải tiến cụ thể

**Pre-approved / standard changes:** Những thay đổi có tính lặp, rủi ro đã hiểu và kiểm soát đã kiểm chứng có thể được người có thẩm quyền **ủy quyền trước** theo điều kiện rõ. Đây không phải “không có phê duyệt”; quyết định đã được thiết kế thành **chính sách có giới hạn**.

**Parallel review:** Khi hai loại review độc lập không phụ thuộc kết quả nhau, có thể thực hiện song song để rút thời gian chờ.

**Reviewer pool:** Nhiều người đủ quyền và năng lực thay cho một cá nhân duy nhất, nếu tiêu chuẩn độc lập vẫn được giữ.

**Review by exception:** Với phạm vi đã được ủy quyền, con người tập trung các trường hợp bất thường, độ bất định cao hoặc kiểm tra tự động thất bại.

**Early engagement:** Người phụ trách bảo mật/dữ liệu có thể tham gia để **thay đổi thiết kế trước code**, thay vì chỉ ký ở cuối sau khi mọi lựa chọn đắt tiền đã chốt.

### Không tối ưu chỉ để “gỡ dấu chờ”

Nếu workflow tự động chuyển mọi yêu cầu sang “Approved” nhưng người có thẩm quyền không xem bằng chứng cần thiết, thời gian chờ có thể giảm còn 0 và rủi ro **tăng lên**. Thử nghiệm phải giữ các guardrail về chất lượng và nghĩa vụ.

## 17. Quản lý ngoại lệ và chấp nhận rủi ro còn lại

Không phải mọi thay đổi đều đi theo đường thông thường. Một kiểm soát có thể chưa đáp ứng vì lý do công nghệ, cần chuyển tiếp hoặc tình huống bất khả kháng. Khi đó cần phân biệt **ngoại lệ được kiểm soát** với **bỏ qua kiểm soát**.

### Hồ sơ ngoại lệ có trách nhiệm

1. **Điều kiện hoặc chính sách đang không đạt:** Nêu cụ thể, không viết “hệ thống hơi rủi ro”.
2. **Lý do:** Vì sao không thể đáp ứng trong thời điểm này, có lựa chọn an toàn khác không?
3. **Tác động và phạm vi:** Dữ liệu, đối tượng người dùng, dịch vụ, thời gian và hậu quả có thể xảy ra.
4. **Biện pháp bù đắp (compensating control):** Giảm nguy cơ thế nào, có thực sự kiểm chứng được không?
5. **Rủi ro còn lại:** Sau bù đắp còn điều gì chưa biết hoặc chưa giải quyết?
6. **Quyền quyết định:** Người được giao quyền xem xét loại ngoại lệ đó, có phải tham vấn ai?
7. **Thời hạn và điều kiện kết thúc:** Ngoại lệ hết hiệu lực khi nào, ai khắc phục, tiêu chí nào để đóng?
8. **Theo dõi và truy vết:** Dấu vết phê duyệt, phạm vi release, cảnh báo và mốc xem lại.

### Ví dụ giả định

Một test end-to-end không ổn định do công cụ test gặp lỗi, trong khi các test bắt buộc khác đạt. Đội không nên tự bấm “skip” và tuyên bố an toàn. Theo chính sách, họ có thể:

- Phân loại test là flaky và xác định những rủi ro mà test vốn bảo vệ.
- Cung cấp kiểm chứng thay thế đáng tin **nếu được phép**, như integration test và kiểm tra thủ công có bằng chứng tương ứng.
- Đề xuất một ngoại lệ **có phạm vi hẹp, thời hạn và owner** cho người có thẩm quyền đánh giá.
- Giữ kế hoạch sửa test và kiểm tra lại trước các thay đổi rủi ro cao.

Nếu test đang thất bại vì **đọc chéo tài khoản thật**, không được lấy lý do test flaky để coi rủi ro đã được giải quyết.

### Những điều không thể “chấp nhận” tùy ý

Một người quản lý, Product Owner hoặc developer không thể đơn phương miễn nghĩa vụ **pháp lý, bảo mật hoặc hợp đồng** ngoài thẩm quyền. Rủi ro không thể chấp nhận theo chính sách phải được xử lý bằng **sửa lỗi, giảm phạm vi an toàn hoặc chưa phát hành**, không phải đổi tên ticket.

## 18. Thay đổi khẩn cấp: nhanh hơn nhưng không vô kiểm soát

Tình huống khẩn thường làm lộ rõ việc tổ chức đã chuẩn bị guardrail tốt hay chưa. Ví dụ phát hiện lỗ hổng cho phép truy cập tiến độ của tài khoản khác cần xử lý nhanh, trong khi quy trình phê duyệt thông thường có thể họp mỗi tuần.

### Một quy trình khẩn có trách nhiệm

| Bước | Mục tiêu | Bằng chứng/điều kiện |
| --- | --- | --- |
| **Kích hoạt** | Xác định tình huống đáp ứng tiêu chí khẩn | Sự cố, ảnh hưởng, mức nghiêm trọng theo chính sách |
| **Trao quyền** | Xác định người chỉ huy/duyệt được ủy quyền | Quyền quyết định và kênh liên lạc đã định nghĩa |
| **Hạn chế tác động** | Cân nhắc vô hiệu hóa đường nguy hiểm, giảm phạm vi hoặc cô lập | Đánh giá không làm phát sinh tác hại lớn hơn |
| **Sửa/khôi phục** | Chọn bản vá nhỏ và kiểm chứng cần thiết | Test ranh giới lỗi, smoke, khả năng khôi phục |
| **Triển khai có kiểm soát** | Thực hiện theo quyền khẩn, giám sát và sẵn sàng ứng phó | Nhật ký thay đổi, người thực hiện và quyết định |
| **Hậu kiểm** | Điều tra nguyên nhân, hoàn thiện bằng chứng và cải tiến | Post-incident review, hành động theo chủ sở hữu |

### Hậu kiểm không thay thế an toàn trước hành động

Quy trình khẩn có thể **rút ngắn hoặc thay thứ tự một số thủ tục thông thường khi được ủy quyền**, nhưng không có nghĩa bỏ qua mọi kiểm tra an toàn. Những kiểm soát tối thiểu và quyền ứng phó khẩn cần được thiết kế **trước khi sự cố xảy ra**, không tùy tiện phát minh trong lúc áp lực.

### Một nguyên tắc quan trọng

Nếu một thay đổi khẩn ảnh hưởng dữ liệu, rollback code chưa chắc khôi phục được dữ liệu đã lộ hoặc ghi sai. Cần đánh giá **khả năng đảo ngược và nghĩa vụ xử lý sự cố**, không chỉ tốc độ merge.

## 19. Phân biệt kiểm soát phòng ngừa, phát hiện và khắc phục

Một tổ chức thường kiểm soát tốt hơn khi không dồn tất cả trách nhiệm vào một “cổng phê duyệt”.

| Nhóm kiểm soát | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Phòng ngừa (preventive)** | Ngăn hành động sai hoặc giảm khả năng lỗi xảy ra | Least privilege, xác thực, bảo vệ nhánh, review theo rủi ro, test bắt buộc |
| **Phát hiện (detective)** | Nhận biết sai lệch đã hoặc đang xảy ra | Integration tests, anomaly alerts, kiểm tra audit logs, đối soát dữ liệu |
| **Khắc phục (corrective)** | Giới hạn hậu quả, phục hồi và ngăn lặp | Runbook, rollback khi khả thi, restore/đối soát, sửa nguyên nhân |

Không thể chỉ dùng **phát hiện sau production** cho những lỗi có thể gây hại không thể khắc phục, như lộ dữ liệu riêng tư. Tương tự, nhiều phê duyệt phòng ngừa không thay được **cảnh báo và năng lực phản ứng** khi hệ thống thật có lỗi.

### Ví dụ ba lớp với lưu tiến độ

- **Phòng ngừa:** API kiểm tra quyền, xử lý idempotency hoặc version theo quy tắc được chốt.
- **Phát hiện:** Test concurrency, cảnh báo lỗi ghi bất thường, đối soát tiến độ khi phù hợp.
- **Khắc phục:** Kế hoạch xử lý request lỗi, phục hồi dữ liệu theo chính sách và thông tin hỗ trợ.

### Nguyên tắc đa lớp không đồng nghĩa vô hạn lớp

Nếu hai bước review lặp đúng cùng một câu hỏi, không có thông tin mới và đều không có quyền quyết định, chúng có thể là **trùng lặp thủ tục**. Nhưng hai kiểm soát kiểm tra **những failure mode khác nhau** có thể bổ sung nhau dù nhìn bề ngoài giống nhau.

## 20. Quản trị chi phí, kiến trúc và phụ thuộc bên ngoài

Không phải mọi ràng buộc nằm trong code. Đội có thể muốn thử một dịch vụ mới nhưng bị giới hạn ngân sách, hợp đồng, vị trí lưu dữ liệu hoặc khả năng hỗ trợ.

### Những quyết định cần làm rõ sớm

| Loại ràng buộc | Ví dụ câu hỏi | Thực hành Agile có ích |
| --- | --- | --- |
| **Ngân sách/tài chính** | Chi phí API theo lượt gọi có vượt ngưỡng ủy quyền không? | Spike đo tải/chi phí, chọn phạm vi nhỏ, kiểm soát mức sử dụng |
| **Mua sắm/hợp đồng** | Đối tác cần thời gian xem điều khoản, bảo mật dữ liệu? | Làm rõ yêu cầu trước khi khóa chặt kiến trúc |
| **Kiến trúc dùng chung** | Công nghệ mới có làm tăng phụ thuộc hoặc vi phạm chuẩn? | ADR ngắn, thử nghiệm có giới hạn, review có trọng tâm |
| **Tài nguyên vận hành** | Dịch vụ mới có người trực và giám sát không? | Chọn khả năng nhỏ, observability và runbook theo rủi ro |
| **Dữ liệu** | Quyền xử lý, lưu giữ và xóa đã rõ? | Privacy review sớm và data minimization |
| **Nhiều nhóm** | Một quyết định của đội này có phá contract đội khác? | Contract tests, cùng lên kế hoạch chuyển đổi |

### Tránh khóa chặt vào giải pháp trước khi biết ràng buộc

Ví dụ nhóm đề xuất một công cụ phân tích đám mây để theo dõi hành trình học viên. Trước khi tích hợp hàng nghìn event và dữ liệu thật, nên hỏi:

1. Mục tiêu phân tích cụ thể nào cần đạt?
2. Có thể thử bằng dữ liệu tổng hợp hoặc quy mô nhỏ được phép không?
3. Chi phí, quyền truy cập, khả năng xóa và hợp đồng đã được đánh giá?
4. Ai có thẩm quyền chọn nhà cung cấp và cam kết tài chính?
5. Có phương án không phụ thuộc vào một công cụ ngay từ đầu không?

Một **spike** để đánh giá khả thi và nghĩa vụ có thể giúp giảm quyết định sai, nhưng kết quả spike **không phải Increment sản phẩm hoàn thành** nếu chưa đáp ứng DoD của sản phẩm.

## 21. Phát hành theo mức rủi ro và phản hồi sớm

Kiểm soát tốt không bắt tổ chức phải chờ tới cuối quý mới nhận phản hồi. Khi Increment đã đạt DoD, đội có thể lựa chọn **phạm vi release** theo chính sách và rủi ro.

### Những cách phân phối có điều kiện

| Cách | Có thể có ích khi | Guardrail cần kiểm tra |
| --- | --- | --- |
| **Internal preview với dữ liệu hợp lệ** | Muốn xem tác vụ và phản hồi sớm | Không dùng dữ liệu thật ngoài quyền; không gọi prototype là Done |
| **Pilot nhóm nhỏ** | Muốn quan sát hành vi sản phẩm thực trong phạm vi được phép | Increment/DoD đạt, quyền và điều kiện tham gia rõ |
| **Feature flag** | Muốn tách deploy khỏi bật khả năng | Bảo vệ server-side auth, test trạng thái flag, quyền bật/tắt |
| **Canary/staged rollout** | Muốn kiểm soát mức phơi nhiễm khi release | Metric lỗi, quyết định mở rộng/dừng và khôi phục |
| **Release theo mốc hợp đồng** | Có ràng buộc bên ngoài về thời điểm hoặc phối hợp | Thông báo, tương thích và phê duyệt áp dụng |

**Không phải mọi rủi ro được phép đưa ra production để “học bằng A/B test”.** Một biến thể đã biết có lỗi đọc chéo dữ liệu không được xem là thí nghiệm sản phẩm hợp lệ.

### Increment, deployment, release và outcome

- **Increment đạt DoD:** Phần sản phẩm có thể sử dụng với chất lượng đã xác định.
- **Deployment:** Đưa artifact vào môi trường.
- **Release:** Cung cấp khả năng cho đối tượng người dùng.
- **Outcome:** Kết quả người dùng/tổ chức thật sự đạt; cần bằng chứng sau khi sử dụng.

Không nên tăng số lần deploy để chứng minh quản trị đã hiệu quả nếu tỷ lệ lỗi và thời gian xử lý sự cố cũng tăng.

## 22. Đo thời gian chờ quản trị một cách chính xác

Một quy trình có thể tốn một giờ **đánh giá rủi ro thực chất** nhưng hạng mục phải chờ ba ngày **trước khi được xem**. Hai loại thời gian cần được phân biệt.

### Các thành phần thời gian

| Thành phần | Cách hiểu | Ví dụ |
| --- | --- | --- |
| **Active work time** | Thời gian thực sự làm thay đổi có giá trị hoặc kiểm chứng | Viết code, test, xem bằng chứng |
| **Approval queue time** | Chờ tới lượt người có thẩm quyền xem | PR đã sẵn sàng nhưng chờ reviewer |
| **Decision processing time** | Thời gian người có thẩm quyền thực hiện đánh giá | Đọc threat model, đối chiếu contract |
| **Rework time** | Sửa/kiểm tra lại do yêu cầu hoặc lỗi được phát hiện | Sửa phân quyền, test migration |
| **Integration wait** | Chờ API, môi trường hoặc nhóm liên quan | Contract chưa chốt hoặc CI không sẵn |
| **Lead time/cycle time** | Từ mốc bắt đầu tới hoàn tất theo ranh giới thống nhất | Tùy hệ thống đo, phải công khai start/finish |

Không cộng một khoảng bị chặn vì **hai nguyên nhân đồng thời** thành gấp đôi thời gian thực. Cần lấy hợp khoảng chờ nếu đo duration item.

### Ví dụ phép đo giả định

Giả sử có năm thay đổi **cùng loại**, được ghi theo quy tắc đơn giản: mỗi item có một khoảng làm việc chủ động và một khoảng chờ phê duyệt **không chồng lấp**; bỏ qua những loại thời gian khác để minh họa.

| Thay đổi | Hoạt động chủ động | Chờ phê duyệt | Tổng trong phạm vi ví dụ |
| --- | ---: | ---: | ---: |
| A | 2 ngày | 1 ngày | 3 ngày |
| B | 1 ngày | 4 ngày | 5 ngày |
| C | 3 ngày | 0,5 ngày | 3,5 ngày |
| D | 1 ngày | 3 ngày | 4 ngày |
| E | 2 ngày | 2 ngày | 4 ngày |
| **Tổng** | **9 ngày-item** | **10,5 ngày-item** | **19,5 ngày-item** |

Tỷ lệ chờ trong **tổng duration item được chọn**:

\[
\frac{10{,}5}{19{,}5}\times100\% \approx 53{,}8\%
\]

Đây là số **minh họa**, không phải dữ liệu của một tổ chức. Không được diễn giải rằng “53,8% nhân viên ngồi không”, vì item có thể chờ trong lúc con người làm việc khác; cũng không được dùng tỷ lệ này để bỏ các phê duyệt cần thiết.

### Câu hỏi cải tiến đúng

> “Trong 10,5 ngày-item chờ phê duyệt này, phần nào do thiếu thông tin, thiếu quyền ủy nhiệm, lịch họp cố định hoặc kiểm soát cần được giữ? Có thể giảm chờ mà bằng chứng và mức rủi ro vẫn tốt không?”

Không chọn giải pháp “bỏ hết approvals” trước khi biết **mục tiêu của từng approval**.

## 23. Bộ chỉ số cân bằng tốc độ và chất lượng quản trị

Chỉ số đơn lẻ dễ tạo hành vi tối ưu sai. Nên theo dõi **dòng công việc, hiệu quả kiểm soát, chất lượng sản phẩm và khả năng phản ứng** cùng nhau.

| Nhóm | Ví dụ tín hiệu | Câu hỏi cần xem |
| --- | --- | --- |
| **Tốc độ học hỏi** | Thời gian từ giả thuyết tới phản hồi người dùng có ích | Kiểm soát có làm đội chờ quá lâu để biết điều cần học? |
| **Flow** | WIP, work item age, cycle time, blocked time theo nguyên nhân | Việc còn mở ở đâu, có cần gỡ blocker trước khi kéo thêm? |
| **Quản trị** | Approval queue time, số lần phải bổ sung bằng chứng, quyết định bị trả lại | Có chính sách mơ hồ, hồ sơ thiếu hoặc reviewer quá tải? |
| **Chất lượng kỹ thuật** | Test pass có ý nghĩa, lỗi CI, flaky, contract/rework | Sai lệch có được phát hiện trước khi phát hành? |
| **Chất lượng sản phẩm** | Lỗi nghiêm trọng, sai dữ liệu, incident, khả năng khôi phục | Tốc độ tăng có đi kèm an toàn không? |
| **Hiệu quả kiểm soát** | Kiểm soát thất bại được phát hiện, ngoại lệ quá hạn, bằng chứng thiếu | Những điều phải bảo vệ có thực sự được bảo vệ? |
| **Giá trị** | Task success, phản hồi định tính, outcome phù hợp Product Goal | Người dùng nhận kết quả hay chỉ có nhiều release? |
| **Bền vững** | Overtime, phụ thuộc reviewer duy nhất, mức gián đoạn | Kết quả tốt có bền hay đến từ quá tải? |

### Cẩn thận với một số chỉ số

- **Số ngoại lệ tăng** có thể do rủi ro tăng, nhưng cũng có thể do đội bắt đầu ghi trung thực hơn.
- **Số lỗi được phát hiện tăng** có thể do kiểm tra tốt hơn, không tự chứng minh phần mềm xấu hơn.
- **Thời gian approval giảm** có thể nhờ ủy quyền đúng, hoặc do người duyệt bỏ bước quan trọng.
- **Số release tăng** không chứng minh người dùng nhận giá trị nếu tính năng ít được sử dụng.
- **Throughput tăng** do chia ticket nhỏ không nhất thiết nâng outcome.

Đo lường Agile nên giúp đội **ra quyết định dựa trên thực tế**, không trở thành bảng xếp hạng người duyệt hay developer.

### Kỳ vọng thời gian quyết định

Tổ chức có thể xác định mục tiêu phản hồi cho loại thay đổi, ví dụ một mục tiêu nội bộ về thời gian đưa quyết định. Nhưng cần phân biệt **mục tiêu kỳ vọng/SLO nội bộ** với một **SLA hợp đồng**, và tránh tự bịa ngưỡng khi chưa có dữ liệu hoặc người có thẩm quyền.

## 24. Cải tiến quản trị bằng thử nghiệm nhỏ, có guardrail

Thay vì một chương trình “loại bỏ mọi thủ tục”, hãy chọn một điểm chờ có bằng chứng và thử thay đổi đủ nhỏ.

### Mẫu thử nghiệm

~~~text
VẤN ĐỀ:
  Những thay đổi đã được phân loại rủi ro thấp chờ review nhiều ngày.

MỤC TIÊU KIỂM SOÁT:
  Giữ chất lượng, quyền truy cập, truy vết và khả năng khôi phục.

GIẢ THUYẾT:
  Nếu những thay đổi đủ điều kiện được ủy quyền trước
  với CI checks và peer review bắt buộc, thời gian chờ
  có thể giảm mà không tăng sự cố.

PHẠM VI:
  Chỉ những thay đổi đã được chính sách cho phép.
  Không gồm quyền, dữ liệu nhạy cảm, breaking contract hoặc migration.

ĐIỀU KIỆN:
  Người có thẩm quyền phê duyệt chính sách ủy quyền.
  Pipeline và bằng chứng được kiểm chứng.

BẰNG CHỨNG:
  Approval wait, cycle time, rework, lỗi production,
  ngoại lệ, kiểm tra audit evidence và phản hồi đội.

GUARDRAIL:
  DoD, phân quyền, chất lượng, dữ liệu và trách nhiệm giải trình.

QUYẾT ĐỊNH SAU THỬ:
  Giữ / điều chỉnh / dừng / thu thêm dữ liệu.
  Ghi yếu tố cùng thay đổi và rủi ro còn lại.
~~~

### Vì sao cần giữ phép đo nhất quán?

Nếu cùng lúc đổi cách chia ticket, thêm reviewer, thay công cụ CI và sửa chính sách chờ, chỉ số trước/sau có thể thay đổi mà **không biết cơ chế nào tạo tác động**. Cần công khai những thay đổi cùng kỳ và độ bất định, không quy nhân quả tùy ý.

### Một thử nghiệm tốt có điều kiện dừng

Nếu test phân quyền bắt buộc bắt đầu bị bỏ qua, evidence chain bị đứt hoặc xảy ra sự cố chất lượng nghiêm trọng liên quan thay đổi mới, đội cần **dừng hoặc điều chỉnh theo chính sách** thay vì tiếp tục đến đủ thời gian thử để đạt KPI.

## 25. Tình huống xuyên suốt: ba thay đổi, ba cách kiểm soát

### 25.1. Bối cảnh

Một tổ chức phát triển nền tảng học tập có Product Goal:

> “Học viên có thể học liên tục và tiếp tục từ đúng tiến độ đã lưu, với dữ liệu và quyền truy cập được bảo vệ.”

Tổ chức muốn giảm thời gian từ lúc có phản hồi của học viên tới lúc cải thiện sản phẩm. Tuy nhiên, nền tảng có dữ liệu người dùng, nhiều phiên bản client và trách nhiệm vận hành sau release.

Ba thay đổi được đề xuất:

| ID | Thay đổi | Mục đích | Rủi ro cần chú ý |
| --- | --- | --- | --- |
| **C1** | Đổi văn bản nút từ “Học tiếp” thành “Tiếp tục học” | Người học hiểu tác vụ hơn | Khả năng sử dụng, khả năng tiếp cận, nghĩa nội dung |
| **C2** | Thay logic chọn tiến độ theo tài khoản và quyền | Mở đúng bài hợp lệ | Phân quyền, cache, response cũ đến muộn, dữ liệu nhạy cảm |
| **C3** | Chuyển schema để lưu số phiên bản tiến độ | Tránh ghi lùi giữa nhiều thiết bị | Migration, tương thích client cũ, mất dữ liệu, khôi phục |

Ba thay đổi **không nên mặc định** dùng cùng mức phê duyệt. Nhưng việc phân tầng phải căn cứ chính sách hiện hành, không tự đặt loại rủi ro để tránh kiểm soát.

### 25.2. Phân tích thay đổi C1: câu chữ trên giao diện

Đội xác minh:

- Không đổi logic xác thực, API hoặc xử lý dữ liệu.
- Câu chữ không thay đổi cam kết pháp lý/hợp đồng hoặc thông tin người dùng phải được phê duyệt chuyên biệt.
- Có test UI phù hợp và review nội dung/khả năng tiếp cận nếu chính sách yêu cầu.
- Thay đổi đạt DoD chung.

Nếu đáp ứng các điều kiện của **loại thay đổi đã được ủy quyền**, đội có thể đi qua pipeline thông thường mà không cần một cuộc họp bảo mật riêng.

**Điểm cần nhớ:** “Chỉ đổi chữ” không tự đồng nghĩa rủi ro thấp. Nếu câu chữ là nội dung đồng ý xử lý dữ liệu hoặc một tuyên bố pháp lý, quyền quyết định có thể khác.

### 25.3. Phân tích C2: logic quyền và tiến độ

Rủi ro quan trọng:

1. API đọc dữ liệu theo một accountId do client tùy chọn.
2. Khi B đăng nhập trên thiết bị từng dùng bởi A, response của A đến muộn.
3. Quyền khóa học bị thu hồi nhưng cache chưa cập nhật.
4. Một lỗi được UI hiển thị như “chưa từng học”, gây hiểu lầm.

**Điều kiện kiểm chứng có thể cần:**

- Thống nhất ranh giới danh tính và quyền với người có chuyên môn.
- Unit/integration/security tests cho truy cập trực tiếp API, đổi phiên và cache.
- Review độc lập hoặc quyết định có thẩm quyền nếu chính sách yêu cầu.
- Không đưa dữ liệu thật trái phép vào log hoặc môi trường thử.
- Có cách quan sát lỗi và phản ứng sau release.

Đội không được bỏ test phân quyền chỉ vì Product Owner muốn có phản hồi của học viên nhanh. Có thể **thu hẹp chức năng** nhưng phải bảo vệ chất lượng.

### 25.4. Phân tích C3: migration tiến độ

Một lỗi migration có thể ảnh hưởng dữ liệu đã được xác nhận của nhiều học viên. Quyết định cần trả lời:

- Client và API phiên bản nào còn phải được hỗ trợ?
- Có thể dùng chiến lược **expand–migrate–contract** với kiểm chứng tương thích không?
- Có cách backup/restore/đối soát đã được thử không?
- Ai được phép thực hiện và ai phải duyệt thay đổi khó đảo ngược?
- Nếu migration thất bại giữa chừng, hệ thống sẽ phục vụ người dùng thế nào?

Lộ trình có thể gồm: thêm schema tương thích → kiểm chứng đọc/ghi cũ–mới → chuyển dữ liệu từng bước → đối soát → chuyển consumer → chỉ xóa cấu trúc cũ khi đủ điều kiện.

**Rollback code không tự phục hồi dữ liệu đã biến đổi.** Vì thế C3 có thể cần kiểm soát sâu hơn C1, bất kể số dòng thay đổi có thể ít hơn.

### 25.5. Bảng quyết định tổng hợp

| Nội dung | C1: Văn bản UI | C2: Quyền tiến độ | C3: Migration |
| --- | --- | --- | --- |
| **Giá trị** | Rõ thao tác | Đúng bài và bảo vệ dữ liệu | Đồng bộ tiến độ đáng tin |
| **Tác động chính** | Trải nghiệm | Danh tính/quyền riêng tư | Toàn vẹn/tương thích dữ liệu |
| **Test quan trọng** | UI, nội dung, accessibility theo rủi ro | Auth/API/cache security integration | Schema/version/concurrency/recovery |
| **Độc lập/phê duyệt** | Theo loại thay đổi được ủy quyền | Theo chính sách bảo mật và rủi ro | Theo chính sách dữ liệu/production |
| **Điều kiện phát hành** | Đạt DoD và policy liên quan | Đạt DoD và bảo vệ quyền, giám sát | Đạt DoD, migration/recovery, lịch và quyền |
| **Phản hồi sau release** | Người dùng hiểu và dùng nút? | Có mở đúng bài, không sai quyền? | Dữ liệu còn đúng và không mất tiến độ? |

Đây là **ma trận giảng dạy**, không phải quyết định phê duyệt thực tế. Trong môi trường học tập, phải xác nhận quyền và chính sách đang có hiệu lực.

### 25.6. Khi một yêu cầu kiểm soát làm chậm C1

Giả sử C1 mất một ngày để thực hiện, nhưng chờ năm ngày tới phiên họp chung. Đội không tự bỏ phê duyệt. Họ:

1. Hỏi **mục tiêu kiểm soát thực sự** của phiên họp đối với loại thay đổi này.
2. Thu dữ liệu thay đổi tương tự và số sự cố để đánh giá mức rủi ro.
3. Đề xuất loại thay đổi **được ủy quyền trước** với AC/DoD, review và CI rõ.
4. Xin người có thẩm quyền điều chỉnh quy trình và giữ bằng chứng.
5. Thử theo kỳ, theo dõi lỗi, approval wait và phản hồi nội dung.

Nếu đề xuất không được chấp thuận, đội vẫn phải theo chính sách hiện hành, đồng thời có thể **làm rõ yêu cầu trước để giảm thời gian xử lý hồ sơ**.

## 26. Tình huống thứ hai: quyền tự chủ nhóm và ngân sách dịch vụ

### Bối cảnh

Một nhóm muốn thử dịch vụ phân tích mới để hiểu nơi học viên bỏ dở hành trình “Tiếp tục học”. Nhà cung cấp tính phí theo lượng event. Dữ liệu có thể liên quan tài khoản học viên và hợp đồng yêu cầu tổ chức xem xét dịch vụ mới.

**Cách làm dễ gây vấn đề:**

> “Đội Agile phải tự chủ, nên cứ thêm SDK, gửi toàn bộ event trước rồi xin duyệt sau.”

Điều này có thể tạo **chi phí, phụ thuộc nhà cung cấp và nguy cơ xử lý dữ liệu ngoài quyền** trước khi tổ chức hiểu tác động.

### Cách tiếp cận có phản hồi nhanh và giữ kiểm soát

1. Nêu câu hỏi sản phẩm: “Học viên được thấy nút nhưng tại sao không mở bài?”
2. Xác định những event thực sự cần, đơn vị đếm và cách bảo vệ riêng tư.
3. Kiểm tra có công cụ/hệ thống hiện tại đủ trả lời câu hỏi không.
4. Nếu cần dịch vụ mới, dùng dữ liệu tổng hợp hoặc môi trường thử **trong phạm vi được phép** để đánh giá khả thi.
5. Thu thập ước tính chi phí, khả năng xóa dữ liệu, giới hạn lưu giữ và quyền truy cập.
6. Đưa đánh giá tới người có quyền về mua sắm, hợp đồng, dữ liệu và kỹ thuật **sớm**.
7. Chỉ kết nối production sau khi đủ điều kiện và có phương án giám sát chi phí/sự cố.

### Bài học

Quản trị có thể **ngăn đội khóa chặt vào một dịch vụ không phù hợp**. Tốc độ phản hồi không nhất thiết đến từ deploy mọi ý tưởng ngay; nó có thể đến từ một **spike ngắn và an toàn** làm rõ quyết định trước khi chi phí sửa đổi tăng.

## 27. Tình huống thứ ba: vá lỗi khẩn ngoài nhịp phê duyệt thông thường

### Bối cảnh

Một lỗi cache khiến người dùng có nguy cơ nhìn thấy dữ liệu của phiên trước. Có nhiều học viên đang sử dụng nền tảng. Quy trình thay đổi thông thường yêu cầu trình hồ sơ tại cuộc họp theo lịch.

### Thứ tự xử lý theo chính sách khẩn

1. **Xác định mức nghiêm trọng** và kích hoạt cơ chế phản ứng đã được ủy quyền.
2. **Giảm tác động ngay nếu an toàn**: cô lập đường lỗi, tắt khả năng hoặc giới hạn phạm vi theo chính sách.
3. **Phối hợp đúng quyền**: incident lead, nhóm sở hữu dịch vụ, bảo mật và người có thẩm quyền khi áp dụng.
4. **Sửa lỗi có kiểm chứng:** Test tái hiện tình huống cache/phiên và kiểm thử hồi quy thiết yếu.
5. **Phát hành bản vá theo quy trình khẩn:** Giữ artifact, quyết định, người thực hiện và tín hiệu theo dõi.
6. **Đánh giá hệ quả dữ liệu:** Việc đổi code có thể chưa giải quyết dữ liệu đã bị lộ hoặc sai; xem nghĩa vụ thông báo/khắc phục trong phạm vi áp dụng.
7. **Hậu kiểm và cải tiến:** Xem vì sao lỗi không phát hiện sớm, cập nhật test, DoD, runbook hoặc cơ chế review khi cần.

### Hai ngộ nhận

**“Khẩn nên không cần bất kỳ kiểm soát nào.”** Sai: chính thay đổi khẩn có thể gây hại mới. Cần những kiểm soát tối thiểu và thẩm quyền đã định nghĩa.

**“Cứ chờ đúng lịch họp mới được vá.”** Cũng có thể nguy hiểm nếu chính sách có đường ứng phó khẩn nhưng đội không biết dùng. Tổ chức nên diễn tập để đường khẩn thực sự hoạt động, không chỉ tồn tại trên giấy.

## 28. Scrum, Kanban và XP đóng góp gì cho quản trị hiệu quả?

Không có một phương pháp duy nhất tự giải quyết mọi ràng buộc. Có thể kết hợp những khả năng phù hợp theo bối cảnh.

### Scrum: trách nhiệm và thực nghiệm theo Sprint

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog.
- **Developers** chịu trách nhiệm tạo Increment sử dụng được, chất lượng theo DoD và lập/điều chỉnh Sprint Backlog.
- **Scrum Master** hỗ trợ thiết lập Scrum và cải thiện hiệu quả Scrum Team; không tự trở thành người ký duyệt mọi yêu cầu sản phẩm.
- **Sprint Planning** là nơi các yêu cầu, rủi ro và phụ thuộc cần làm rõ đủ mức để chọn mục tiêu Sprint.
- **Daily Scrum** giúp Developers kiểm tra tiến triển hướng Sprint Goal và điều chỉnh kế hoạch.
- **Sprint Review** kiểm tra kết quả Sprint và phản hồi, không phải cổng bắt buộc để release.
- **Sprint Retrospective** là nơi đánh giá chất lượng, hiệu quả và những thủ tục đang gây trở ngại.

Quản trị tổ chức có thể đưa điều kiện bắt buộc vào chính sách/DoD, nhưng **không biến Sprint Review thành một hội đồng chỉ ký duyệt demo**.

### Kanban: minh bạch dòng chảy và chính sách

Kanban giúp:

- Vẽ rõ workflow và **những chính sách xử lý thay đổi theo loại**.
- Giới hạn WIP để tránh nhiều hạng mục cùng nằm chờ reviewer.
- Theo dõi **work item age, cycle time, throughput, blocked duration** và lý do chờ.
- Dùng những buổi điều phối theo luồng để giải quyết hàng đợi quyết định.
- Thử thay đổi quy trình nhỏ và đánh giá dữ liệu trước/sau với giới hạn rõ.

Đội không nhất thiết phải dùng Sprint để hưởng lợi từ quản lý luồng. Một Scrum Team cũng có thể dùng thực hành Kanban mà vẫn giữ trách nhiệm, sự kiện và cam kết Scrum.

### XP và thực hành kỹ thuật: kiểm soát chất lượng trong công việc

| Thực hành | Cách hỗ trợ mục tiêu kiểm soát | Giới hạn |
| --- | --- | --- |
| **TDD** | Phát hiện sai logic sớm, ghi quy tắc thành test | Không thay kiểm chứng hợp đồng và phân quyền thực |
| **Pair programming** | Chia sẻ tri thức, nhận feedback khi thay đổi còn nhỏ | Không mặc định thay thế review độc lập nếu chính sách yêu cầu |
| **Continuous Integration** | Kiểm tra thường xuyên, tránh lỗi dồn cuối kỳ | Pipeline xanh không chứng minh mọi rủi ro đã được bao phủ |
| **Refactoring** | Giảm phức tạp và rủi ro thay đổi về sau | Cần test và kiểm chứng hành vi không đổi |
| **Small releases** | Giảm phạm vi ảnh hưởng, tăng khả năng quan sát | Vẫn phải đáp ứng chất lượng và quyền phát hành |

### Phương pháp không thay quyền quyết định

Scrum, Kanban hay XP không cho phép tổ chức **bỏ luật, hợp đồng hoặc bảo vệ dữ liệu**. Cũng không bắt mọi tổ chức dùng cùng một quy trình phê duyệt. Hãy giữ **nguyên tắc giá trị và khả năng phản hồi**, đồng thời thiết kế kiểm soát đúng theo thực tế.

## 29. Quy trình tám bước thiết kế quản trị thích ứng

### Bước 1 — Chọn một vấn đề có bằng chứng

Ví dụ: “Những thay đổi rủi ro thấp đã vượt tất cả kiểm tra nhưng vẫn chờ phê duyệt bốn ngày.” Nêu loại item, start/finish, kỳ đo và dữ liệu ban đầu.

### Bước 2 — Phân biệt nghĩa vụ với thủ tục

Đối chiếu các yêu cầu đang áp dụng và chủ sở hữu chính sách. Tách **mục tiêu kiểm soát không thể bỏ** khỏi các bước tổ chức cụ thể có thể đề xuất cải tiến.

### Bước 3 — Vẽ dòng công việc và điểm chờ

Từ ý tưởng, refinement, thiết kế, code, test, review, release đến giám sát. Nêu nơi có hàng chờ, người quyết định, các vòng làm lại và dữ liệu bị thiếu.

### Bước 4 — Phân tầng loại thay đổi

Dựa trên tài sản, mức tác động, khả năng xảy ra, bất định và khả năng phục hồi. Không dùng cảm giác hoặc số dòng code như tiêu chí duy nhất.

### Bước 5 — Đặt guardrails và quyền

Quy định thay đổi nào có thể tự xử lý sau những điều kiện đã được ủy quyền; trường hợp nào cần review độc lập, phê duyệt cao hơn hoặc đường khẩn. Cấp quyền theo chính sách chứ không tự suy đoán.

### Bước 6 — Đưa kiểm soát vào dòng kỹ thuật

Đưa AC/DoD, tests, CI, security checks, contract verification và liên kết evidence tới đúng thay đổi. Giữ những việc không thể tự động hóa cho người có chuyên môn và thẩm quyền.

### Bước 7 — Thử cải tiến có guardrail

Giảm một hàng chờ hoặc trùng lặp bằng chứng trong phạm vi an toàn. Theo dõi approval wait cùng lỗi, rework, ngoại lệ, chất lượng và trải nghiệm người dùng.

### Bước 8 — Kiểm tra, thích nghi và cập nhật chính sách

Nếu số liệu cải thiện nhưng sự cố tăng, dừng hoặc điều chỉnh. Nếu hiệu quả tích cực và kiểm soát vẫn đạt, có thể đề xuất mở rộng qua người có thẩm quyền. Cập nhật tài liệu, pipeline, runbook và ví dụ để đội khác áp dụng phù hợp.

## 30. Kế hoạch cải tiến trong bốn tuần

Đây là **lịch thử nghiệm minh họa**, không phải chu kỳ chuẩn Agile hoặc một yêu cầu kiểm toán.

| Tuần | Mục tiêu | Việc làm | Đầu ra |
| --- | --- | --- | --- |
| **1 – Hiểu hệ thống** | Định nghĩa vấn đề và rủi ro | Vẽ workflow, phân loại thay đổi, lấy baseline, xác nhận chủ sở hữu chính sách | Bản đồ kiểm soát và điểm chờ |
| **2 – Thiết kế** | Đề xuất giảm chờ có trách nhiệm | Thử quy tắc phân tầng, pre-approved path có ủy quyền, bằng chứng CI | Giả thuyết và điều kiện thử |
| **3 – Quan sát** | Xem tác động thực | Thu wait time, lỗi, rework, phản hồi, kiểm tra bằng chứng và ngoại lệ | Nhật ký quyết định, điểm cần sửa |
| **4 – Đánh giá** | Giữ, sửa hoặc dừng | Đối chiếu trước/sau, xem confounders và guardrail, xin quyết định mở rộng nếu cần | Kết luận có giới hạn và chính sách cập nhật |

### Một ví dụ báo cáo kết quả có trách nhiệm

> “Trong nhóm thay đổi có phạm vi được ủy quyền, thời gian chờ giảm so với kỳ trước và bằng chứng CI được liên kết đầy đủ. Tuy nhiên, cỡ mẫu nhỏ và cùng kỳ đã tăng số reviewer nên chưa thể quy toàn bộ kết quả cho đường xử lý mới. Chúng ta chưa thấy lỗi nghiêm trọng mới trong kỳ quan sát, nhưng điều đó chưa chứng minh rủi ro bằng không. Cần tiếp tục xem chất lượng, tính độc lập và các ngoại lệ trước khi mở rộng.”

**Không báo cáo “giảm 100% thủ tục = Agile thành công”.** Giá trị nằm ở **phản hồi nhanh hơn với kiểm soát hiệu quả hơn hoặc ít nhất không suy giảm**.

## 31. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| **Agile nghĩa là không cần kiểm soát** | Rủi ro dữ liệu, hợp đồng và vận hành bị bỏ | Giữ mục tiêu kiểm soát và trách nhiệm giải trình |
| **Mọi thay đổi đều cần cùng một chuỗi phê duyệt** | Hàng chờ lớn, feedback chậm | Phân tầng theo tác động và thẩm quyền được ủy quyền |
| **Số dòng code ít nghĩa là rủi ro thấp** | Một dòng phân quyền có thể gây hại lớn | Đánh giá kịch bản tác động và khả năng khôi phục |
| **Có chữ ký nghĩa là chất lượng đã đạt** | Hồ sơ đẹp nhưng lỗi chưa được kiểm chứng | Gắn phê duyệt với evidence thật |
| **Dùng “policy as code” để thay mọi quyết định** | Bỏ mất phán đoán về ngữ nghĩa và nghĩa vụ | Tự động hóa phần kiểm tra được, giữ quyền phù hợp |
| **Mời tất cả chuyên gia vào mọi user story** | Tốn năng lực và thời gian | Tham gia theo trigger rủi ro và yêu cầu thực |
| **Chỉ kiểm tra tuân thủ ngay trước release** | Phát hiện muộn, tạo rework và áp lực | Làm rõ từ refinement, kiểm chứng trong CI |
| **Làm giả trạng thái Done để qua cổng** | Mất ý nghĩa DoD và chất lượng | Chỉ Done khi đạt DoD; thu hẹp lát cắt an toàn |
| **Sao chép chữ ký giữa các phiên bản** | Evidence không gắn artifact thật | Truy vết commit, build, môi trường và quyết định |
| **Bỏ kiểm soát độc lập vì đội tự quản** | Mất separation of duties bắt buộc | Đào tạo reviewer dự phòng, giữ thẩm quyền |
| **Mọi ngoại lệ đều tồn tại vô hạn** | Rủi ro còn lại bị quên | Phạm vi, owner, thời hạn, biện pháp bù đắp và xem lại |
| **Lỗi nghiêm trọng xử lý bằng đường thường** | Phản ứng chậm gây tăng tác động | Kích hoạt chính sách khẩn được ủy quyền |
| **Khẩn thì được bỏ mọi kiểm chứng** | Bản vá có thể gây hậu quả mới | Giữ kiểm soát tối thiểu, quyết định và hậu kiểm |
| **Rollback code đủ cứu mọi migration** | Dữ liệu có thể không khôi phục | Kiểm chứng backup, restore và đối soát |
| **Đo số approval thay vì thời gian và hiệu quả** | Tối ưu bỏ chữ ký không giảm rủi ro | Xem queue time, chất lượng và bằng chứng |
| **Tự ý nhận một “risk acceptance”** | Vượt quyền hoặc vi phạm nghĩa vụ | Dùng đúng quyền quyết định và chính sách |
| **Đếm tất cả feedback thành KPI tuân thủ** | Dữ liệu người dùng bị thu quá mức | Data minimization và mục đích xử lý rõ |
| **So sánh cycle time giữa đội khác loại công việc** | Xếp hạng sai, che rủi ro | So theo nhóm item, bối cảnh và phép đo |
| **Đổi nhiều yếu tố cùng lúc rồi tuyên bố nguyên nhân** | Kết luận thiếu căn cứ | Ghi confounders và độ bất định |
| **Không có vòng phản hồi từ audit/incident** | Lặp lại lỗi và thủ tục không hiệu quả | Cập nhật backlog, CI, chính sách và học hỏi |

## 32. Bài tập thực hành

### Bài tập 1 — Phân biệt mục tiêu và thủ tục

Tổ chức yêu cầu mọi PR có chữ ký của một người quản lý. Bạn chưa biết vì sao.

**Yêu cầu:** Liệt kê ít nhất năm câu hỏi để xác định mục tiêu kiểm soát, quyền và phạm vi áp dụng; đề xuất một cách có thể giảm chờ **mà không tự ý bỏ quy định**.

**Gợi ý:** Cần biết người ký đang kiểm soát quyền, chi phí, hợp đồng, kiến trúc hay đơn thuần là một bước lịch sử.

### Bài tập 2 — Phân tầng rủi ro

Xét ba thay đổi:

A. Đổi nhãn nút không thay nghĩa cam kết.

B. Sửa cách API kiểm tra quyền tài khoản.

C. Migration dữ liệu tiến độ với nhiều phiên bản client.

**Yêu cầu:** Nêu rủi ro, kiểm tra, bằng chứng, quyền quyết định và điều kiện phát hành khác nhau. Ghi rõ mọi phân loại chỉ là giả định cho đến khi đối chiếu chính sách thật.

### Bài tập 3 — Tách AC, DoD và release gate

Phân loại:

1. “Người dùng không thể mở bài trái quyền.”
2. “Increment đã tích hợp và test chất lượng chung đạt.”
3. “Phát hành sau khi migration được diễn tập và quyền quyết định được xác nhận.”
4. “Nhóm đã có commit trên nhánh chính.”

**Gợi ý:** (1) có thể là AC cụ thể; (2) thuộc DoD; (3) điều kiện release; (4) chưa đủ để gọi Increment hoàn thành.

### Bài tập 4 — Vẽ quyền quyết định

Một đội có Product Owner, Developers, chuyên gia bảo mật, người phụ trách dữ liệu và vận hành. Cả năm người đều được CC mọi quyết định.

**Yêu cầu:** Chọn bốn loại thay đổi, xác định ai **quyết định**, ai **tham vấn**, ai **được thông báo**, và những trường hợp cần reviewer độc lập theo chính sách.

### Bài tập 5 — Tự động hóa bằng chứng

Mỗi release đội phải chụp màn hình kết quả CI, chép tên người review, điền commit hash và phiên bản artifact vào ba biểu mẫu.

**Yêu cầu:** Thiết kế evidence chain từ issue–PR–CI–artifact–deployment, nêu trường nào tự động liên kết được, trường nào cần quyết định con người và điều kiện bảo vệ dữ liệu.

### Bài tập 6 — Policy as code

Đội muốn cho tự động deploy những thay đổi được ủy quyền nhưng ngăn các thay đổi phân quyền hoặc schema khi chưa có review cần thiết.

**Yêu cầu:** Viết pseudocode của các điều kiện kiểm tra, xác định cách tránh tác giả tự gắn nhãn “risk thấp” để bypass, và giải thích giới hạn của policy as code.

### Bài tập 7 — Approval wait

Năm thay đổi có thời gian làm việc **2, 1, 3, 1, 2 ngày**; thời gian chờ phê duyệt **1, 4, 0,5, 3, 2 ngày**, không chồng lấp.

**Yêu cầu:** Tính tổng thời gian hai loại, tỷ lệ chờ trong tập và nêu lý do không được diễn giải đó là phần trăm nhân viên nhàn rỗi.

**Gợi ý:** Active **9 ngày-item**, wait **10,5 ngày-item**, tổng **19,5 ngày-item**; tỷ lệ wait khoảng **53,8%**.

### Bài tập 8 — Thiết kế một ngoại lệ có thời hạn

Một test môi trường không ổn định trước ngày release; đội đề nghị tạm bỏ test đó.

**Yêu cầu:** Viết hồ sơ ngoại lệ: rủi ro test vốn bảo vệ, lý do, biện pháp thay thế, người có quyền, phạm vi, thời hạn, bằng chứng và điều kiện dừng. Phân biệt test flaky với lỗi sản phẩm thật.

### Bài tập 9 — Quy trình khẩn

Sản phẩm phát hiện nguy cơ đọc chéo dữ liệu và cuộc họp phê duyệt thường còn ba ngày nữa mới diễn ra.

**Yêu cầu:** Thiết kế đường ứng phó khẩn theo quyền đã được ủy quyền: giảm tác động, sửa/test, ghi quyết định, release, giám sát, trách nhiệm xử lý dữ liệu và hậu kiểm.

### Bài tập 10 — Hợp đồng và giá trị người dùng

Product Owner muốn thử một API bên thứ ba để gợi ý bài học; pháp chế, tài chính và bảo mật còn câu hỏi chưa được giải quyết.

**Yêu cầu:** Đề xuất một spike an toàn để thu bằng chứng kỹ thuật/giá trị mà không ký hợp đồng, chi tiền hoặc chuyển dữ liệu thật ngoài quyền. Nêu giới hạn kết luận của spike.

### Bài tập 11 — Ma trận preventive/detective/corrective

Với rủi ro “request lưu tiến độ lặp gây ghi lùi”, hãy đề xuất:

- Hai cơ chế phòng ngừa.
- Hai cơ chế phát hiện.
- Hai cơ chế khắc phục.

**Gợi ý:** Không gọi rollback code là cơ chế chắc chắn phục hồi dữ liệu.

### Bài tập 12 — Đọc dashboard quản trị có trách nhiệm

Sau cải tiến, approval wait giảm 30%, số release tăng, nhưng rework và sự cố production cũng tăng; cùng kỳ nhóm thay đổi cách ghi lỗi.

**Yêu cầu:** Viết nhận định phân biệt quan sát với nguyên nhân, đặt bốn câu hỏi về phép đo/nguồn gây nhiễu, đề xuất guardrail và quyết định cần kiểm chứng.

### Bài tập 13 — Kanban và WIP ở hàng chờ phê duyệt

Đội có mười yêu cầu chờ một reviewer được chỉ định; reviewer chỉ làm trong một buổi mỗi tuần.

**Yêu cầu:** Đề xuất hai thay đổi được phép cân nhắc để giảm age/blocked time (ví dụ reviewer pool hoặc phân tầng), nhưng giải thích điều gì cần được **người có thẩm quyền** xác nhận trước.

### Bài tập 14 — Sprint Review không phải release gate

Một Scrum Team có Increment đạt DoD vào giữa Sprint, nhưng tổ chức có lịch phát hành theo hợp đồng. Người quản lý nói “Scrum bắt buộc chờ Sprint Review mới được release”.

**Yêu cầu:** Phân biệt quy tắc của Scrum và quy định phát hành của tổ chức, đề xuất cách minh bạch trạng thái Done/Release và nhận phản hồi sớm khi có thể.

### Bài tập 15 — Một chính sách quá rộng

Một nhóm thay nội dung hướng dẫn bình thường cũng phải làm threat model mới, diễn tập migration và đi qua phê duyệt kiến trúc cấp cao. Đội mất nhiều ngày, song chưa thấy lý do từng bước áp dụng.

**Yêu cầu:** Đề xuất cách đối chiếu **trigger theo rủi ro**, chính sách bắt buộc và bằng chứng có thể tái sử dụng. Không tự bỏ bất kỳ bước nào trước khi có quyết định hợp lệ.

### Bài tập 16 — Thử nghiệm bốn tuần

Bạn được giao giảm thời gian chờ kiểm soát của đội mà vẫn bảo vệ dữ liệu học viên.

**Yêu cầu:** Xây một kế hoạch bốn tuần gồm baseline, phân loại thay đổi, giả thuyết, can thiệp, metrics, guardrails, quyền quyết định và kết luận sau thử. Nêu ít nhất hai confounders có thể làm kết quả sai lệch.

## 33. Checklist cân bằng quản trị và tốc độ phản hồi

Trước khi thay đổi một quy trình kiểm soát hoặc quyết định phát hành:

- [ ] Đã nêu **người dùng/mục tiêu sản phẩm** và quyết định cần hỗ trợ?
- [ ] Đã phân biệt **governance, mục tiêu kiểm soát, chính sách, cơ chế, evidence và approval**?
- [ ] Nguồn ràng buộc có **thẩm quyền, phạm vi và phiên bản** rõ?
- [ ] Không nhầm thủ tục nội bộ lịch sử với nghĩa vụ pháp lý khi chưa kiểm chứng?
- [ ] Đã mô tả kịch bản rủi ro, tài sản, tác động, khả năng xảy ra và mức chưa biết?
- [ ] Có xem khả năng phát hiện, đảo ngược và khôi phục, không chỉ độ lớn code?
- [ ] Những điều kiện bảo mật, dữ liệu, hợp đồng và chất lượng bắt buộc được giữ?
- [ ] Đã phân tầng loại thay đổi theo chính sách đã được xác nhận?
- [ ] Đội biết **quyền tự chủ trong guardrail** và khi nào phải leo thang?
- [ ] Có ma trận ai quyết định, ai tham vấn và ai được thông báo?
- [ ] Separation of duties hoặc review độc lập được giữ nơi cần thiết?
- [ ] Người phê duyệt có đủ **bằng chứng đúng phiên bản và phạm vi**?
- [ ] Những kiểm soát có thể tự động hóa đã được xem xét, không chép lại thủ công vô ích?
- [ ] Policy as code có kiểm thử, quản lý phiên bản và chống bypass?
- [ ] Những đánh giá cần con người/thẩm quyền không bị tự động hóa giả?
- [ ] Từ refinement đã làm rõ AC, DoD, dữ liệu, quyền và phụ thuộc?
- [ ] Nếu có nhiều Scrum Team cùng sản phẩm, họ có và tuân thủ **DoD chung**?
- [ ] Không nhầm merge, Increment, deployment, release và outcome?
- [ ] Điều kiện release liên quan rollout, migration, telemetry và khôi phục đã được kiểm tra?
- [ ] Có quy trình ngoại lệ với owner, rủi ro còn lại, biện pháp bù đắp, thời hạn và quyền phù hợp?
- [ ] Có đường ứng phó khẩn được ủy quyền và hậu kiểm, không bỏ an toàn?
- [ ] Bằng chứng tuân thủ có thể truy vết từ yêu cầu tới artifact và deployment?
- [ ] Có bảo vệ quyền riêng tư khi thu log, audit evidence hoặc dữ liệu sử dụng?
- [ ] Đã đo **queue time riêng với processing time**, dùng start/finish và kỳ đo rõ?
- [ ] Khi blocker chồng lấp, không cộng trùng duration?
- [ ] Chỉ số được xem cùng lỗi nghiêm trọng, rework, quality và outcome?
- [ ] Không dùng số approval, số PR hoặc story point để xếp hạng cá nhân?
- [ ] Có thử nghiệm cải tiến nhỏ, guardrail, thời điểm xem lại và điều kiện dừng?
- [ ] Đã ghi nguồn gây nhiễu khi so trước/sau và không phóng đại quan hệ nhân quả?
- [ ] Khi phát hiện kiểm soát kém hiệu quả, có người có quyền cập nhật policy và bài học dùng chung?
- [ ] Quá trình mới giúp đội **phản hồi nhanh hơn mà không làm mất trách nhiệm giải trình**?

Checklist là công cụ **đặt câu hỏi có trọng tâm**, không phải thủ tục bổ sung cho mọi story. Độ sâu kiểm chứng phải theo **rủi ro thực, nghĩa vụ và mức bất định**, đồng thời ưu tiên bằng chứng đã được tạo trong dòng làm việc.

## 34. Tổng kết

- **Agile và governance không đối lập.** Agile giúp nhận phản hồi sớm, giao tăng dần và thay đổi cách làm; quản trị xác định trách nhiệm, quyền và những điều phải bảo vệ.
- **Mục tiêu kiểm soát cần ổn định hơn hình thức thủ tục.** Kiểm tra đúng quyền và bảo vệ dữ liệu là yêu cầu cốt lõi; số biểu mẫu, lịch họp hoặc cách thu bằng chứng có thể cải tiến theo quyền cho phép.
- **Phân tầng theo rủi ro** giúp thay đổi thấp rủi ro được xử lý trong guardrails đã được ủy quyền, trong khi thay đổi dữ liệu, bảo mật hoặc khó đảo ngược được đánh giá sâu hơn.
- **Tự chủ phải đi cùng trách nhiệm:** Ai quyết định, theo điều kiện nào, bằng chứng gì và khi nào cần leo thang phải minh bạch; không bỏ kiểm soát độc lập bắt buộc.
- **Kiểm soát liên tục trong backlog, DoD và CI/CD** thường hữu ích hơn kiểm tra dồn cuối dự án. Chữ ký, pipeline xanh hoặc document riêng lẻ không thay thế kiểm chứng hành vi và chất lượng.
- **Ngoại lệ và thay đổi khẩn cần đường đi rõ**, không phải lối tắt vô hạn. Rủi ro còn lại phải được xử lý bởi người có thẩm quyền, có điều kiện và thời hạn xem lại.
- **Tốc độ phản hồi cần được đo cùng chất lượng:** Approval wait, work item age, cycle time, rework, sự cố, chất lượng bằng chứng và outcome giúp nhận ra thủ tục nào có ích hoặc gây chờ.
- **Scrum, Kanban và XP bổ sung nhau:** Scrum làm rõ trách nhiệm, mục tiêu và DoD; Kanban minh bạch dòng việc và chính sách; XP tạo phản hồi kỹ thuật sớm bằng test, CI, pairing và refactoring.
- **Cải tiến có căn cứ là con đường bền vững:** Thử thay đổi nhỏ, không hạ tiêu chuẩn an toàn, xem tác động và điều chỉnh qua quyền quản trị thực tế.

Khi một nhóm nói **“Quy trình phê duyệt đang làm chúng ta chậm”**, câu hỏi cần đặt không phải “Bỏ được bao nhiêu bước?”, mà là: **“Mỗi bước đang bảo vệ rủi ro nào, có bằng chứng nào chứng minh điều đó và liệu chúng ta có thể đạt cùng mục tiêu kiểm soát nhanh hơn, đáng tin hơn bằng cách khác không?”**
