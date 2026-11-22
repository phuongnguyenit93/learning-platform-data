# Lựa chọn hoạt động UAT phù hợp với người dùng và môi trường

## Mục tiêu bài học

Kiểm thử chấp nhận của người dùng (User Acceptance Testing, UAT) giúp xác định liệu sản phẩm có hỗ trợ người dùng hoàn thành công việc thực tế theo nhu cầu và tiêu chí đã thống nhất hay không. UAT thường diễn ra khi sản phẩm hoặc một phần chức năng đã đủ hoàn chỉnh để người dùng đại diện đánh giá. Chất lượng của hoạt động này phụ thuộc nhiều vào việc chọn đúng người tham gia, đúng tình huống nghiệp vụ và môi trường đủ đại diện cho cách sản phẩm sẽ được sử dụng.

Trong chiến lược VALIDATION_TESTING_STRATEGY, UAT không chỉ là yêu cầu người dùng bấm thử vài màn hình rồi hỏi họ có hài lòng hay không. Nhóm cần xác định quyết định nào cần được hỗ trợ: xác nhận một quy trình nghiệp vụ, đánh giá vai trò và quyền hạn, kiểm tra dữ liệu sau di trú, xác nhận khả năng vận hành hay quyết định có chấp nhận phiên bản để phát hành. Mỗi mục tiêu đòi hỏi hoạt động, người tham gia, dữ liệu và môi trường phù hợp.

Sau bài học, người học có thể:

- Phân biệt UAT với kiểm thử hệ thống, kiểm thử chức năng và đánh giá khả năng sử dụng.
- Chọn nhóm người dùng đại diện theo vai trò, kinh nghiệm, nhu cầu và bối cảnh làm việc.
- Chọn hoạt động UAT theo mục tiêu nghiệp vụ và rủi ro cần xác nhận.
- Đánh giá mức độ phù hợp của môi trường, dữ liệu, thiết bị và tích hợp.
- Thiết kế phiên UAT với kịch bản, nhiệm vụ, tiêu chí và cách ghi nhận bằng chứng.
- Phân loại phản hồi thành lỗi, thiếu sót yêu cầu, cải tiến hoặc vấn đề đào tạo.
- Tổng hợp kết quả và đưa ra quyết định chấp nhận có căn cứ.

## 1. UAT xác nhận điều gì?

**UAT** là hoạt động đánh giá sản phẩm từ góc nhìn người dùng hoặc đại diện nghiệp vụ nhằm xác nhận sản phẩm đáp ứng nhu cầu sử dụng, quy trình công việc và tiêu chí chấp nhận đã thống nhất. UAT thường trả lời các câu hỏi:

- Người dùng có thể hoàn thành nhiệm vụ thực tế bằng sản phẩm không?
- Quy trình có phù hợp với chính sách, quy tắc nghiệp vụ và trách nhiệm của từng vai trò không?
- Thông tin được hiển thị, lưu trữ và chuyển tiếp có đủ và chính xác để người dùng ra quyết định không?
- Các trường hợp ngoại lệ và tình huống thường gặp có được xử lý theo cách nghiệp vụ mong đợi không?
- Sản phẩm có thể được đưa vào sử dụng trong môi trường và điều kiện làm việc dự kiến không?
- Những rủi ro còn lại có thể được chấp nhận trước khi phát hành không?

UAT thường được thực hiện sau khi nhóm phát triển và kiểm thử đã hoàn tất các kiểm tra kỹ thuật cần thiết. Người dùng không nên phải phát hiện những lỗi cơ bản như ứng dụng không khởi động, API không phản hồi hoặc chức năng chính chưa được tích hợp. Các vấn đề kỹ thuật đó cần được xử lý trước hoặc được thông báo rõ nếu chúng là giới hạn của phiên UAT.

### 1.1. Phân biệt UAT với các hoạt động khác

| Hoạt động | Câu hỏi chính | Người thực hiện thường gặp | Bằng chứng |
|---|---|---|---|
| Kiểm thử đơn vị, tích hợp và hệ thống | Thành phần và hệ thống có hoạt động đúng theo đặc tả và yêu cầu kỹ thuật không? | Nhà phát triển, kiểm thử viên, chuyên gia kỹ thuật. | Kết quả test, log, báo cáo kỹ thuật, số đo. |
| Kiểm thử chức năng | Chức năng có thực hiện đúng quy tắc và hành vi đã mô tả không? | Kiểm thử viên, nhà phát triển, chuyên gia nghiệp vụ. | Kết quả đạt/trượt theo trường hợp kiểm thử. |
| UAT | Sản phẩm có phù hợp với công việc và tiêu chí chấp nhận của người dùng không? | Người dùng đại diện, chủ sở hữu nghiệp vụ, product owner. | Kết quả nhiệm vụ, phản hồi, sai lệch nghiệp vụ và quyết định chấp nhận. |
| Đánh giá khả năng sử dụng (usability testing) | Người dùng có hiểu và thao tác dễ dàng, hiệu quả không? | Người dùng đại diện, chuyên gia UX/research. | Quan sát, thời gian hoàn thành, lỗi thao tác và phản hồi. |
| Kiểm thử alpha/beta hoặc pilot | Sản phẩm hoạt động và tạo giá trị thế nào trong nhóm thử nghiệm hoặc môi trường sử dụng thực tế? | Nhân viên nội bộ, nhóm khách hàng thử nghiệm hoặc người dùng được chọn. | Dữ liệu sử dụng, sự cố, phản hồi và kết quả theo dõi. |
| Kiểm thử chấp nhận vận hành (operational acceptance) | Đội vận hành có thể triển khai, giám sát, hỗ trợ và phục hồi hệ thống không? | Vận hành, hỗ trợ, quản trị hệ thống và chủ sở hữu dịch vụ. | Runbook, cảnh báo, backup/restore, diễn tập và xác nhận sẵn sàng. |

Các hoạt động có thể kết hợp trong cùng một chương trình chấp nhận, nhưng cần ghi rõ mục tiêu và người chịu trách nhiệm. Một phiên UAT có thể phát hiện vấn đề khả năng sử dụng; điều đó không biến UAT thành một nghiên cứu UX đầy đủ. Tương tự, người dùng có thể xác nhận quy trình nghiệp vụ nhưng không thay thế đánh giá bảo mật chuyên môn.

## 2. Chọn đúng người tham gia UAT

Người tham gia cần đại diện cho những người sẽ sử dụng hoặc chịu ảnh hưởng bởi sản phẩm. Chọn người chỉ vì họ sẵn sàng tham gia có thể khiến kết quả thiên lệch: người đó có thể không hiểu quy trình, không có quyền thực hiện nhiệm vụ hoặc không gặp các tình huống mà sản phẩm cần hỗ trợ.

### 2.1. Xác định nhóm người dùng theo vai trò

Bắt đầu bằng việc lập danh sách vai trò và công việc của họ:

- Người thực hiện nghiệp vụ hằng ngày.
- Người phê duyệt hoặc kiểm soát.
- Người quản lý cần xem báo cáo và đưa ra quyết định.
- Nhân viên hỗ trợ hoặc xử lý ngoại lệ.
- Quản trị viên cấu hình người dùng, quyền và dữ liệu.
- Khách hàng hoặc đối tác tương tác qua cổng bên ngoài.
- Người dùng có nhu cầu tiếp cận đặc thù hoặc sử dụng thiết bị hỗ trợ.

Không phải phiên UAT nào cũng cần tất cả vai trò. Hãy chọn theo phạm vi thay đổi và rủi ro. Nếu phiên bản thay đổi quy trình phê duyệt, cần có cả người tạo yêu cầu và người phê duyệt. Nếu thay đổi chỉ liên quan đến báo cáo của quản lý, người thực hiện nghiệp vụ có thể không phải nhóm tham gia chính.

### 2.2. Chọn người có tính đại diện

Xem xét các yếu tố sau:

| Yếu tố | Câu hỏi lựa chọn |
|---|---|
| Vai trò và quyền hạn | Người tham gia có thực hiện đúng nhiệm vụ hoặc quyết định nằm trong phạm vi UAT không? |
| Kinh nghiệm | Có cả người dùng thành thạo và người dùng mới nếu cả hai nhóm đều thuộc đối tượng sử dụng không? |
| Quy mô và tần suất công việc | Người tham gia có hiểu các trường hợp phổ biến và các giai đoạn cao điểm không? |
| Địa điểm và điều kiện làm việc | Có khác biệt giữa chi nhánh, khu vực, ca làm việc hoặc môi trường kết nối không? |
| Thiết bị và khả năng tiếp cận | Có sử dụng thiết bị, trình duyệt, ngôn ngữ hoặc công nghệ hỗ trợ khác nhau không? |
| Xử lý ngoại lệ | Có người thường xử lý trường hợp bất thường, khiếu nại hoặc điều chỉnh thủ công không? |
| Mức độ độc lập | Người tham gia có thể đưa ra phản hồi trung thực mà không chịu áp lực phải xác nhận sản phẩm đạt không? |

Một nhóm nhỏ nhưng đại diện đúng các vai trò quan trọng có thể cung cấp bằng chứng tốt hơn một nhóm đông nhưng chỉ gồm người dùng quen thuộc với dự án. Với sản phẩm phục vụ nhiều nhóm người dùng, nên tổ chức nhiều phiên hoặc chia mẫu theo vai trò thay vì yêu cầu mọi người thực hiện cùng một kịch bản.

### 2.3. Tránh thiên lệch khi tuyển chọn

- Không chỉ chọn người đã tham gia thiết kế sản phẩm; họ có thể biết trước cách thao tác mà người dùng mới không biết.
- Không chỉ chọn quản lý; người trực tiếp thực hiện nghiệp vụ thường nhìn thấy các bước và ngoại lệ thực tế.
- Không chỉ chọn người dùng thành thạo; người mới có thể phát hiện hướng dẫn hoặc thuật ngữ khó hiểu.
- Không ép người tham gia đồng ý với kết luận của nhóm dự án.
- Giải thích rõ phản hồi được dùng để cải thiện sản phẩm, không phải đánh giá hiệu suất cá nhân.
- Nếu cần đánh giá khả năng tiếp cận, mời người dùng có nhu cầu và công nghệ hỗ trợ tương ứng tham gia với sự chuẩn bị phù hợp.

## 3. Chọn hoạt động UAT theo mục tiêu

Không có một phương pháp UAT phù hợp cho mọi loại sản phẩm. Hãy bắt đầu từ quyết định cần đưa ra và chọn hoạt động giúp người tham gia cung cấp bằng chứng cho quyết định đó.

| Hoạt động | Mục tiêu phù hợp | Khi nên chọn | Bằng chứng cần thu thập |
|---|---|---|---|
| Kiểm thử theo kịch bản nghiệp vụ | Xác nhận một quy trình đầu-cuối đáp ứng quy tắc và kết quả mong đợi. | Quy trình rõ, có tiêu chí chấp nhận và các bước cần phối hợp. | Kết quả từng bước, dữ liệu đầu ra, sai lệch và ngoại lệ. |
| Kiểm thử theo nhiệm vụ (task-based) | Xem người dùng có tự hoàn thành công việc thực tế không. | Cần đánh giá tính phù hợp của thao tác và kết quả công việc. | Tỷ lệ hoàn thành, thời gian, lỗi thao tác, trợ giúp cần dùng. |
| Phiên khám phá có hướng dẫn (exploratory UAT) | Tìm vấn đề chưa được dự đoán trong cách sử dụng thực tế. | Yêu cầu có nhiều ngoại lệ hoặc quy trình chưa được mô tả đầy đủ. | Quan sát, tình huống phát hiện, dữ liệu và phản hồi. |
| Walkthrough quy trình | Đánh giá quy trình, trách nhiệm, điểm bàn giao và quyết định. | Nhiều vai trò cùng tham gia hoặc quy trình thay đổi đáng kể. | Điểm nghẽn, bước thiếu, quyền không phù hợp và quyết định nghiệp vụ. |
| UAT theo vai trò và quyền | Xác nhận mỗi vai trò nhìn thấy và thực hiện đúng phần việc được phép. | Thay đổi phân quyền, dữ liệu nhạy cảm hoặc quy trình phê duyệt. | Kết quả thao tác hợp lệ và bị từ chối, dữ liệu hiển thị theo quyền. |
| Đối soát và xác nhận dữ liệu | Xác nhận dữ liệu được nhập, di trú, tính toán hoặc báo cáo đúng. | Thay đổi schema, chuyển hệ thống, quy tắc tính hoặc báo cáo. | Số liệu đối chiếu, mẫu bản ghi, sai lệch và cách xử lý. |
| Pilot hoặc thử nghiệm có giới hạn | Đánh giá sản phẩm trong điều kiện làm việc thực tế với phạm vi được kiểm soát. | Môi trường staging không mô phỏng hết quy trình hoặc cần dữ liệu sử dụng thật. | Chỉ số vận hành, phản hồi, sự cố và quyết định mở rộng. |
| Xác nhận sẵn sàng vận hành | Xác nhận tổ chức có thể hỗ trợ và duy trì dịch vụ. | Phát hành ảnh hưởng quy trình vận hành hoặc trách nhiệm hỗ trợ. | Runbook, cảnh báo, quy trình hỗ trợ, backup/restore và kết quả diễn tập. |

### 3.1. Kiểm thử theo kịch bản nghiệp vụ

Kịch bản mô tả một mục tiêu công việc có điểm bắt đầu, điều kiện, các bước và kết quả mong đợi. Ví dụ: nhân viên tiếp nhận yêu cầu hoàn tiền, kiểm tra điều kiện, gửi phê duyệt và theo dõi trạng thái.

Kịch bản nên dùng ngôn ngữ nghiệp vụ, tránh yêu cầu người dùng kiểm tra chi tiết kỹ thuật như tên endpoint hoặc câu SQL. Nó cần bao gồm:

- Vai trò thực hiện.
- Mục đích công việc.
- Điều kiện và dữ liệu ban đầu.
- Các bước hoặc quyết định quan trọng.
- Kết quả mong đợi.
- Trường hợp ngoại lệ cần đánh giá.
- Tiêu chí chấp nhận và bằng chứng cần lưu.

Kịch bản tốt không nhất thiết mô tả từng lần nhấp chuột. Nó cho người tham gia đủ mục tiêu và bối cảnh để thực hiện công việc theo cách tự nhiên, đồng thời cho người quan sát biết điều gì cần xác nhận.

### 3.2. Kiểm thử theo nhiệm vụ

Trong hoạt động task-based, người tham gia được giao một nhiệm vụ, chẳng hạn “Tìm đơn hàng của khách hàng và xác định lý do giao hàng bị trễ”. Người điều phối quan sát xem họ có hoàn thành được không, có phải hỏi trợ giúp hay không và có hiểu kết quả hiển thị không.

Nếu mục tiêu là đánh giá khả năng sử dụng, nên hạn chế hướng dẫn từng bước. Nếu người điều phối phải chỉ đường liên tục, đó là tín hiệu về vấn đề trong giao diện hoặc quy trình. Nếu mục tiêu là xác nhận quy trình nghiệp vụ, có thể cung cấp thông tin về vai trò và quy tắc nhưng vẫn để người dùng tự thực hiện thao tác.

### 3.3. Phiên khám phá có hướng dẫn

Không phải mọi hành vi đều có thể dự đoán trước. Phiên khám phá cho phép người dùng thử các trường hợp gần với công việc của họ, đặt câu hỏi và chỉ ra điều bất thường.

Người điều phối có thể đưa ra một mục tiêu rộng và quan sát cách người dùng tiếp cận. Hãy ghi lại dữ liệu, điều kiện, hành động và kết quả thay vì chỉ ghi nhận nhận xét chung như “khó dùng”. Khi phát hiện vấn đề, hỏi người tham gia điều gì họ mong đợi và tại sao điều đó quan trọng với công việc.

### 3.4. Walkthrough quy trình nhiều vai trò

Với quy trình có nhiều người tham gia, walkthrough giúp kiểm tra điểm bàn giao. Ví dụ, nhân viên tạo hồ sơ, quản lý phê duyệt, bộ phận vận hành thực hiện và khách hàng nhận kết quả. Nhóm cần xác nhận:

- Thông tin nào được chuyển từ vai trò này sang vai trò khác?
- Người nhận có đủ dữ liệu để tiếp tục công việc không?
- Trách nhiệm và quyền quyết định có rõ ràng không?
- Trạng thái quy trình có phản ánh đúng tiến độ không?
- Có bước nào bị bỏ qua hoặc lặp lại?
- Khi có ngoại lệ, ai xử lý và người khác nhìn thấy thông tin gì?

## 4. Chọn môi trường UAT phù hợp

Môi trường cần đủ đại diện để kết quả có ý nghĩa, đồng thời bảo vệ dữ liệu và tránh tác động không mong muốn đến hoạt động thật. Không phải mọi UAT đều cần chạy trên production. Nhóm cần xác định điều kiện nào phải giống production và điều kiện nào có thể mô phỏng an toàn.

### 4.1. Các lựa chọn môi trường

| Môi trường | Phù hợp với | Hạn chế và kiểm soát |
|---|---|---|
| Môi trường UAT/staging riêng | Kịch bản nghiệp vụ, kiểm thử vai trò, dữ liệu đại diện và xác nhận trước phát hành. | Cần giữ cấu hình, phiên bản và tích hợp gần với production; ghi rõ khác biệt còn lại. |
| Sandbox của nhà cung cấp | Kiểm tra thanh toán, định danh, gửi thông báo hoặc API bên ngoài. | Có thể khác production về dữ liệu, giới hạn, độ trễ và hành vi; cần kiểm tra thêm các rủi ro chưa mô phỏng. |
| Pilot trong môi trường thực tế có giới hạn | Xác nhận quy trình hoặc hành vi chỉ quan sát được trong điều kiện vận hành thật. | Cần phê duyệt, giới hạn người dùng và dữ liệu, giám sát, kế hoạch dừng và hỗ trợ. |
| Production với phạm vi kiểm soát | Chỉ khi mục tiêu không thể xác minh đủ trong môi trường khác và có kiểm soát phù hợp. | Rủi ro tác động thật; cần quyền hạn, dữ liệu, tài khoản, thời gian và kế hoạch phục hồi được phê duyệt. |

Môi trường UAT nên được chuẩn bị như một phần của kế hoạch, không phải đợi đến ngày người dùng tham gia mới phát hiện tài khoản không đăng nhập được hoặc tích hợp chưa sẵn sàng.

### 4.2. Mức độ giống production

Không phải mọi cấu hình đều phải giống tuyệt đối, nhưng các yếu tố ảnh hưởng đến mục tiêu UAT cần được mô phỏng đủ sát:

- Phiên bản ứng dụng và cấu hình liên quan.
- Vai trò, quyền truy cập và quy trình xác thực.
- Các hệ thống tích hợp và cách xử lý lỗi.
- Thiết bị, trình duyệt, kích thước màn hình và mạng.
- Múi giờ, ngôn ngữ, tiền tệ và định dạng dữ liệu.
- Dung lượng dữ liệu, trạng thái hồ sơ và khối lượng công việc.
- Quy trình thông báo, phê duyệt và xử lý ngoại lệ.

Hãy lập danh sách khác biệt giữa môi trường UAT và production. Nếu sandbox không gửi SMS thật, phiên UAT có thể xác nhận nội dung và trạng thái thông báo nhưng không chứng minh khả năng gửi SMS qua nhà mạng. Rủi ro còn lại cần được kiểm tra riêng hoặc xác nhận trong pilot có kiểm soát.

### 4.3. Quản lý dữ liệu UAT

Dữ liệu cần đủ thực tế để người dùng đánh giá nhưng phải an toàn và có thể tái tạo.

- Dùng dữ liệu tổng hợp hoặc dữ liệu đã được ẩn danh khi phù hợp.
- Không sao chép dữ liệu cá nhân hoặc bí mật từ production vào môi trường không được phép.
- Tạo đủ trường hợp bình thường, biên và ngoại lệ.
- Chuẩn bị dữ liệu riêng cho từng phiên hoặc người tham gia để tránh ảnh hưởng lẫn nhau.
- Xác định cách khôi phục trạng thái sau phiên kiểm thử.
- Ghi rõ dữ liệu nào là giả lập, dữ liệu nào được đồng bộ từ nguồn được phê duyệt.
- Không dùng tài khoản hoặc thông tin thanh toán thật nếu sandbox có thể đáp ứng mục tiêu.

Nếu cần dùng dữ liệu production trong một pilot, phải có phê duyệt và biện pháp bảo vệ phù hợp với chính sách dữ liệu của tổ chức. Không nên xem sự thuận tiện của người tham gia là lý do đủ để bỏ qua kiểm soát dữ liệu.

## 5. Chọn phương thức tổ chức phiên UAT

UAT có thể diễn ra trực tiếp, từ xa, tự phục vụ hoặc theo nhóm. Phương thức nên phù hợp với địa điểm, kỹ năng số, mức độ phức tạp và khả năng quan sát công việc.

| Phương thức | Khi phù hợp | Cần chuẩn bị |
|---|---|---|
| Trực tiếp có điều phối | Quy trình phức tạp, cần quan sát tương tác hoặc thảo luận nhiều vai trò. | Phòng, thiết bị, dữ liệu, người điều phối, người ghi nhận và kịch bản. |
| Từ xa có điều phối | Người dùng ở nhiều địa điểm hoặc cần giảm thời gian di chuyển. | Công cụ họp, chia sẻ màn hình, quyền truy cập, hướng dẫn bảo mật và phương án ghi chú. |
| Tự phục vụ theo kịch bản | Nhiệm vụ rõ, người tham gia có thể tự thao tác và gửi phản hồi. | Hướng dẫn, tài khoản, dữ liệu riêng, biểu mẫu phản hồi và kênh hỗ trợ. |
| Workshop nhiều vai trò | Quy trình liên phòng ban hoặc cần thống nhất quyết định và trách nhiệm. | Bản đồ quy trình, tình huống, người có quyền quyết định và biên bản. |
| Pilot có giám sát | Cần xác nhận trong điều kiện sử dụng thực tế. | Nhóm tham gia giới hạn, tiêu chí mở rộng/dừng, giám sát và hỗ trợ. |

### 5.1. Trực tiếp và từ xa

Phiên trực tiếp có lợi khi người điều phối cần quan sát cách người dùng làm việc, trao đổi tài liệu hoặc xử lý tình huống phức tạp. Phiên từ xa có thể tiếp cận người dùng ở nhiều địa điểm và phản ánh thiết bị, kết nối thực tế hơn.

Với phiên từ xa, cần kiểm tra trước đường dẫn, quyền truy cập, chia sẻ màn hình, tài khoản và dữ liệu. Không yêu cầu người dùng chia sẻ mật khẩu hoặc thông tin nhạy cảm. Nếu ghi âm hoặc ghi hình, cần thông báo mục đích, phạm vi lưu trữ và xin sự đồng ý theo quy định áp dụng.

### 5.2. Tự phục vụ và có điều phối

Tự phục vụ phù hợp khi nhiệm vụ đơn giản, tiêu chí rõ và người dùng có thể thực hiện độc lập. Tuy nhiên, phản hồi tự do có thể thiếu bối cảnh. Cần yêu cầu người tham gia ghi nhiệm vụ, bước đã thực hiện, kết quả mong đợi, kết quả thực tế và ảnh chụp hoặc mã tham chiếu khi phù hợp.

Phiên có điều phối phù hợp với quy trình mới, nhiều ngoại lệ hoặc cần hiểu lý do người dùng chọn một cách thao tác. Người điều phối nên đặt câu hỏi trung lập và tránh hướng dẫn người tham gia đến câu trả lời mong muốn.

## 6. Thiết kế kế hoạch và kịch bản UAT

Một kế hoạch UAT nên kết nối mục tiêu chấp nhận với người tham gia, hoạt động và môi trường.

### 6.1. Nội dung kế hoạch tối thiểu

- Mục tiêu và phạm vi UAT.
- Phiên bản, chức năng và giới hạn chưa được kiểm tra.
- Nhóm người dùng và vai trò cần đại diện.
- Người chịu trách nhiệm điều phối, ghi nhận và ra quyết định.
- Hoạt động và kịch bản cần thực hiện.
- Môi trường, thiết bị, dữ liệu và tài khoản.
- Tiêu chí đạt, mức độ nghiêm trọng của phát hiện và điều kiện dừng.
- Cách ghi nhận phản hồi, lỗi và yêu cầu thay đổi.
- Lịch, thời lượng và kênh hỗ trợ.
- Quy trình tổng hợp kết quả và phê duyệt.

### 6.2. Mẫu kịch bản

~~~text
Mã kịch bản:
Tên nghiệp vụ:
Vai trò người dùng:
Mục tiêu công việc:
Điều kiện ban đầu:
Dữ liệu cần dùng:
Các bước hoặc nhiệm vụ:
Kết quả mong đợi:
Trường hợp ngoại lệ:
Tiêu chí chấp nhận:
Bằng chứng cần lưu:
Môi trường/thiết bị:
~~~

Kịch bản cần đủ rõ để có thể lặp lại nhưng không nên biến người dùng thành người thực hiện một chuỗi thao tác máy móc nếu mục tiêu là xem họ có thể tự hoàn thành công việc hay không.

### 6.3. Bao phủ trường hợp thực tế

Kịch bản nên có sự cân bằng giữa:

- Luồng thường gặp có giá trị nghiệp vụ cao.
- Trường hợp biên có thể gây hậu quả đáng kể.
- Luồng ngoại lệ như từ chối, hủy, sửa, hoàn tác hoặc chuyển cấp.
- Tình huống nhiều vai trò và bàn giao.
- Trạng thái dữ liệu trước và sau khi thực hiện.
- Điều kiện vận hành như mạng chậm, thiết bị khác nhau hoặc ca làm việc.

Không cần đưa mọi tổ hợp dữ liệu vào UAT. Kiểm thử kỹ thuật có thể bao phủ nhiều trường hợp chi tiết; UAT nên tập trung vào tính phù hợp của công việc và các quyết định mà người dùng cần đưa ra.

## 7. Tiêu chí chấp nhận và cách đánh giá kết quả

Tiêu chí chấp nhận cần được thống nhất trước phiên UAT. Nếu chỉ hỏi người tham gia “bạn thấy ổn không?”, nhóm sẽ khó đưa ra quyết định nhất quán.

Một tiêu chí có thể bao gồm:

- Nhiệm vụ quan trọng hoàn thành đúng kết quả nghiệp vụ.
- Dữ liệu được hiển thị và lưu đúng theo quy tắc đã thống nhất.
- Vai trò thực hiện được nhiệm vụ được phép và không truy cập vượt quyền.
- Các ngoại lệ trọng yếu được xử lý hoặc có hướng dẫn rõ.
- Người dùng hiểu trạng thái và bước tiếp theo cần thực hiện.
- Không có lỗi nghiêm trọng chưa được xử lý trong phạm vi chấp nhận.
- Rủi ro còn lại có chủ sở hữu và được người có thẩm quyền chấp nhận.
- Các yêu cầu hỗ trợ, vận hành và đào tạo cần thiết đã sẵn sàng.

Có thể dùng tiêu chí định lượng khi phù hợp, chẳng hạn tỷ lệ hoàn thành nhiệm vụ, số lỗi nghiêm trọng, thời gian xử lý hoặc mức độ sai lệch dữ liệu. Không nên áp dụng một ngưỡng chung cho mọi sản phẩm. Ngưỡng cần phản ánh mục tiêu nghiệp vụ và mức rủi ro.

### 7.1. Phân loại kết quả

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| Đạt | Nhiệm vụ đáp ứng tiêu chí và không có sai lệch trọng yếu. | Lưu bằng chứng và chuyển sang đánh giá tổng thể. |
| Không đạt do lỗi | Hành vi sản phẩm sai so với yêu cầu hoặc tiêu chí đã thống nhất. | Ghi lỗi, ưu tiên, điều tra và kiểm thử lại sau sửa. |
| Không đạt do thiếu yêu cầu | Nhu cầu hoặc quy tắc nghiệp vụ chưa được làm rõ hoặc chưa được triển khai. | Làm rõ với chủ sở hữu nghiệp vụ, xác định lỗi hay thay đổi phạm vi. |
| Cần cải tiến | Sản phẩm đáp ứng yêu cầu nhưng người dùng đề xuất cách làm tốt hơn. | Ghi backlog, đánh giá giá trị và ưu tiên riêng. |
| Vấn đề môi trường/dữ liệu | Phiên UAT không thể đánh giá vì môi trường, tài khoản hoặc dữ liệu sai. | Khắc phục điều kiện, chạy lại phần bị ảnh hưởng; không kết luận sản phẩm đạt. |
| Vấn đề đào tạo/hướng dẫn | Người dùng chưa hiểu quy trình hoặc thuật ngữ, nhưng hành vi sản phẩm có thể đúng. | Xem lại nội dung hướng dẫn, đào tạo và khả năng sử dụng; xác minh nguyên nhân trước khi phân loại. |

Không nên gộp mọi phản hồi thành lỗi phần mềm. Ngược lại, không nên gọi một hành vi sai đã vi phạm tiêu chí chấp nhận là “vấn đề đào tạo” để tránh sửa sản phẩm.

## 8. Điều phối và quan sát phiên UAT

Người điều phối cần tạo điều kiện để người tham gia thực hiện công việc tự nhiên và phản hồi trung thực.

Một phiên có thể diễn ra theo trình tự:

1. Giới thiệu mục tiêu, phạm vi, thời gian và cách ghi nhận.
2. Xác nhận người tham gia có đúng vai trò và quyền cần thiết.
3. Kiểm tra tài khoản, môi trường, thiết bị và dữ liệu.
4. Giao nhiệm vụ hoặc kịch bản với ngôn ngữ dễ hiểu.
5. Quan sát mà không hướng dẫn quá mức.
6. Hỏi người tham gia giải thích điều họ mong đợi và điều họ quan sát được.
7. Ghi lại sai lệch, bằng chứng và mức độ ảnh hưởng.
8. Tổng kết phát hiện, xác nhận cách hiểu và bước tiếp theo.

### 8.1. Câu hỏi trung lập

Nên hỏi:

- “Bạn đang cố gắng hoàn thành công việc gì?”
- “Bạn mong đợi điều gì sẽ xảy ra ở bước này?”
- “Thông tin nào giúp bạn quyết định bước tiếp theo?”
- “Có điều gì khiến bạn phải dừng lại hoặc hỏi người khác không?”
- “Trong công việc thực tế, bạn xử lý trường hợp này thế nào?”
- “Nếu kết quả này xuất hiện trong ngày làm việc bình thường, tác động sẽ ra sao?”

Tránh hỏi theo cách dẫn dắt như “Bạn có thấy chức năng này tiện hơn không?” hoặc “Bạn đồng ý rằng quy trình đã đúng chứ?”. Những câu hỏi đó có thể tạo phản hồi thiên lệch.

### 8.2. Ghi nhận bằng chứng

Mỗi phát hiện nên có:

- Mã phiên và kịch bản liên quan.
- Vai trò người dùng, không nhất thiết ghi danh tính cá nhân nếu không cần.
- Phiên bản, môi trường, thiết bị và thời điểm.
- Điều kiện và dữ liệu ban đầu.
- Hành động đã thực hiện.
- Kết quả mong đợi và thực tế.
- Ảnh chụp, log hoặc mã tham chiếu nếu phù hợp và an toàn.
- Tác động đến công việc và mức độ ưu tiên.
- Phân loại ban đầu và người tiếp nhận xử lý.

Bằng chứng cần đủ để nhóm tái hiện và đánh giá, nhưng không thu thập thông tin cá nhân hoặc nội dung nhạy cảm vượt quá mục đích UAT.

## 9. Xử lý UAT theo môi trường và điều kiện sử dụng

### 9.1. Khác biệt thiết bị và trình duyệt

Nếu người dùng thực tế làm việc trên nhiều thiết bị, UAT cần chọn thiết bị đại diện theo mức sử dụng và rủi ro. Ví dụ, một ứng dụng nội bộ chủ yếu chạy trên máy tính tại quầy có thể ưu tiên trình duyệt và độ phân giải tại quầy; ứng dụng khách hàng có thể cần thêm thiết bị di động và kích thước màn hình phổ biến.

Không nên để người tham gia dùng một thiết bị thuận tiện cho nhóm dự án nếu thiết bị đó không đại diện cho môi trường làm việc thật.

### 9.2. Mạng và địa điểm

Với sản phẩm sử dụng ở nhiều chi nhánh hoặc khu vực có chất lượng mạng khác nhau, cần xem xét điều kiện kết nối. Có thể tổ chức phiên tại địa điểm đại diện hoặc mô phỏng độ trễ, gián đoạn và băng thông hạn chế trong môi trường kiểm thử.

Nếu chỉ kiểm tra trên mạng nội bộ tốc độ cao, nhóm có thể bỏ sót vấn đề đồng bộ, timeout hoặc mất kết nối mà người dùng thực tế gặp phải.

### 9.3. Ngôn ngữ, múi giờ và quy trình địa phương

Sản phẩm phục vụ nhiều khu vực cần kiểm tra định dạng ngày giờ, tiền tệ, số, ngôn ngữ, thông báo và quy tắc nghiệp vụ theo địa phương. Người tham gia cần hiểu quy trình địa phương và có khả năng xác nhận nội dung phù hợp.

### 9.4. Khả năng tiếp cận

Nếu sản phẩm phục vụ người dùng có nhu cầu tiếp cận khác nhau, cần chọn hoạt động và người tham gia phù hợp. Có thể kết hợp UAT theo nhiệm vụ với việc dùng bàn phím, trình đọc màn hình, phóng to nội dung hoặc các công nghệ hỗ trợ khác. Chuyên gia accessibility có thể đánh giá tiêu chuẩn kỹ thuật; người dùng thực tế giúp xác nhận khả năng hoàn thành công việc trong bối cảnh của họ.

## 10. Khi nào nên dùng pilot hoặc môi trường production có kiểm soát?

Một số hành vi chỉ có thể đánh giá đầy đủ khi sản phẩm tương tác với dữ liệu, thiết bị, quy trình và con người trong điều kiện thật. Khi đó, pilot có thể phù hợp hơn một phiên staging thuần túy.

Pilot cần có:

- Mục tiêu và phạm vi rõ ràng.
- Nhóm người dùng, địa điểm hoặc giao dịch được giới hạn.
- Phê duyệt của chủ sở hữu nghiệp vụ và các bên cần thiết.
- Dữ liệu và quyền truy cập được kiểm soát.
- Người hỗ trợ và kênh báo sự cố.
- Chỉ số theo dõi và ngưỡng dừng.
- Kế hoạch tắt tính năng, quay lại quy trình cũ hoặc phục hồi.
- Tiêu chí mở rộng sau khi có bằng chứng.

Production có kiểm soát không phải lựa chọn mặc định. Chỉ dùng khi môi trường khác không thể tạo bằng chứng đủ tin cậy và các rủi ro được quản lý. Nếu có giao dịch thật, thông báo thật hoặc dữ liệu thật, cần giới hạn tác động và bảo đảm có khả năng đối soát.

### 10.1. Ví dụ về tiêu chí pilot

Một hệ thống quản lý yêu cầu nội bộ được triển khai cho một chi nhánh trước. Nhóm có thể xác định:

- Chỉ nhân viên của chi nhánh được bật tính năng.
- Mọi yêu cầu tạo mới có mã theo dõi và có thể đối soát.
- Tỷ lệ tạo yêu cầu thành công phải nằm trong ngưỡng đã thống nhất.
- Không có lỗi nghiêm trọng về quyền truy cập hoặc mất dữ liệu.
- Nhân viên có thể hoàn thành các nhiệm vụ chính mà không cần quy trình ngoài hệ thống không được phê duyệt.
- Có thể chuyển về quy trình cũ nếu phát sinh sự cố vượt ngưỡng.
- Chủ sở hữu nghiệp vụ xem xét kết quả trước khi mở rộng sang chi nhánh tiếp theo.

Các ngưỡng cụ thể phải được dự án xác định theo mức độ ảnh hưởng và khối lượng công việc.

## 11. Ví dụ thực tế: UAT cho hệ thống phê duyệt chi phí

Một tổ chức thay thế quy trình phê duyệt chi phí qua email bằng ứng dụng quản lý yêu cầu. Các vai trò gồm nhân viên tạo yêu cầu, quản lý phê duyệt, bộ phận tài chính đối soát và quản trị viên cấu hình hạn mức.

### 11.1. Chọn người tham gia

- Nhân viên thường xuyên gửi yêu cầu công tác phí.
- Quản lý có trách nhiệm phê duyệt theo hạn mức.
- Nhân viên tài chính xử lý đối soát và ngoại lệ.
- Quản trị viên cấu hình vai trò và chính sách.
- Một số người dùng mới để đánh giá khả năng hiểu hướng dẫn.

### 11.2. Chọn hoạt động

| Hoạt động | Mục tiêu |
|---|---|
| Kịch bản nghiệp vụ | Xác nhận quy trình tạo, gửi, phê duyệt, từ chối và hoàn tất yêu cầu. |
| UAT theo vai trò | Xác nhận nhân viên, quản lý và tài chính chỉ thấy và thao tác đúng quyền. |
| Đối soát dữ liệu | So sánh số tiền, hạn mức, trạng thái và báo cáo với quy tắc đã thống nhất. |
| Phiên khám phá | Tìm trường hợp ngoại lệ như yêu cầu thiếu chứng từ, vượt hạn mức hoặc người phê duyệt vắng mặt. |
| Pilot tại một đơn vị | Xác nhận quy trình trong ca làm việc và điều kiện mạng thực tế. |

### 11.3. Chọn môi trường

Giai đoạn đầu sử dụng staging với dữ liệu tổng hợp đại diện và tài khoản theo từng vai trò. Tích hợp email được thay bằng sandbox để xác nhận nội dung thông báo. Sau khi các tiêu chí staging đạt, tổ chức pilot giới hạn tại một đơn vị với quyền và dữ liệu được phê duyệt.

### 11.4. Đánh giá kết quả

UAT không chỉ hỏi ứng dụng có chạy hay không. Nhóm cần xác nhận:

- Nhân viên có gửi đúng loại yêu cầu và biết hồ sơ đang ở trạng thái nào không?
- Quản lý có nhìn thấy đủ thông tin để ra quyết định không?
- Quy tắc hạn mức và phân cấp phê duyệt có được áp dụng đúng không?
- Tài chính có đối soát được số liệu và tìm được chứng từ không?
- Khi người phê duyệt vắng mặt, quy trình có cách xử lý được phê duyệt không?
- Người dùng có cần hướng dẫn bổ sung hoặc thay đổi giao diện không?

Nếu ứng dụng hoạt động đúng nhưng quy trình mới yêu cầu một bước phê duyệt chưa được thống nhất, đó là vấn đề nghiệp vụ cần quyết định. Nếu hệ thống cho phép nhân viên phê duyệt yêu cầu của chính mình trái với chính sách, đó là lỗi hoặc rủi ro nghiêm trọng cần xử lý trước khi chấp nhận.

## 12. Tổng hợp kết quả và quyết định chấp nhận

Kết thúc UAT, nhóm cần tổng hợp bằng chứng theo phạm vi, vai trò và mức độ ảnh hưởng. Không nên chỉ ghi “UAT pass” nếu có kịch bản chưa chạy, môi trường có sai khác hoặc lỗi còn mở.

Báo cáo nên gồm:

- Phạm vi, phiên bản và môi trường đã đánh giá.
- Vai trò và nhóm người dùng tham gia.
- Kịch bản và nhiệm vụ đã thực hiện.
- Kết quả đạt, không đạt và chưa thực hiện.
- Lỗi, yêu cầu cải tiến, vấn đề môi trường và nhu cầu đào tạo.
- Mức độ nghiêm trọng và tác động đến nghiệp vụ.
- Rủi ro còn lại, biện pháp giảm thiểu và người chấp nhận.
- Sai khác giữa môi trường UAT và production.
- Khuyến nghị chấp nhận, chấp nhận có điều kiện hoặc chưa chấp nhận.

### 12.1. Các trạng thái quyết định

| Quyết định | Khi phù hợp | Điều kiện cần ghi nhận |
|---|---|---|
| Chấp nhận | Tiêu chí quan trọng đạt, không còn lỗi chặn và rủi ro còn lại nằm trong ngưỡng cho phép. | Bằng chứng, phạm vi đã kiểm tra và người phê duyệt. |
| Chấp nhận có điều kiện | Còn vấn đề giới hạn có biện pháp giảm thiểu, chủ sở hữu và thời hạn xử lý rõ. | Ngoại lệ, rủi ro, giới hạn sử dụng, điều kiện theo dõi và thời hạn. |
| Chưa chấp nhận | Có lỗi hoặc thiếu bằng chứng ảnh hưởng đến mục tiêu nghiệp vụ hoặc rủi ro không thể chấp nhận. | Vấn đề cần xử lý, kiểm thử lại và điều kiện để đánh giá lại. |
| Hoãn quyết định | Môi trường, dữ liệu hoặc người tham gia chưa đủ để đánh giá hợp lệ. | Điều kiện còn thiếu, người chịu trách nhiệm và lịch thực hiện lại. |

Quyền chấp nhận thuộc về người hoặc vai trò được tổ chức chỉ định, thường là chủ sở hữu nghiệp vụ hoặc đại diện có thẩm quyền. Người điều phối UAT tổng hợp bằng chứng và khuyến nghị; không tự thay thế người chịu trách nhiệm chấp nhận rủi ro.

## 13. Những sai lầm thường gặp

- **Chỉ mời người quản lý tham gia:** bỏ qua cách người trực tiếp thực hiện công việc sử dụng sản phẩm.
- **Chỉ kiểm tra luồng thành công:** bỏ sót ngoại lệ, bàn giao, từ chối, hủy và xử lý sai dữ liệu.
- **Dùng kịch bản quá chi tiết:** người tham gia chỉ làm theo chỉ dẫn, không bộc lộ vấn đề trong cách hiểu và cách thực hiện công việc.
- **Dùng môi trường quá khác production:** kết quả không phản ánh cấu hình, quyền, tích hợp hoặc điều kiện sử dụng thật.
- **Dùng dữ liệu không đại diện:** các trường hợp biên và khối lượng thực tế không được đánh giá.
- **Để người điều phối dẫn dắt câu trả lời:** phản hồi có thể thiên lệch và che giấu vấn đề.
- **Gộp lỗi với yêu cầu cải tiến:** làm sai lệch mức độ ưu tiên và quyết định chấp nhận.
- **Coi UAT thay thế kiểm thử kỹ thuật:** người dùng không có trách nhiệm xác minh mọi thuộc tính bảo mật, hiệu năng hoặc tính toàn vẹn kỹ thuật.
- **Không xác định tiêu chí trước phiên:** nhóm tranh luận về kết quả sau khi đã quan sát thay vì dựa trên thỏa thuận.
- **Không ghi nhận sai khác môi trường:** một phiên đạt trong staging có thể không đủ bằng chứng cho production.
- **Không có quyết định và người phê duyệt rõ ràng:** kết quả UAT không chuyển thành quyết định phát hành có trách nhiệm.

## 14. Checklist trước khi tổ chức UAT

- [ ] Mục tiêu chấp nhận và phạm vi phiên bản đã được xác định.
- [ ] Người tham gia đại diện cho vai trò và nhóm người dùng chịu ảnh hưởng.
- [ ] Có cả người thực hiện nghiệp vụ và người xử lý ngoại lệ khi cần.
- [ ] Hoạt động được chọn phù hợp với câu hỏi cần xác minh.
- [ ] Kịch bản và nhiệm vụ dùng ngôn ngữ nghiệp vụ, có kết quả mong đợi rõ.
- [ ] Tiêu chí đạt, điều kiện dừng và quyền quyết định đã thống nhất.
- [ ] Môi trường, cấu hình, tích hợp, thiết bị và mạng đủ đại diện.
- [ ] Dữ liệu kiểm thử an toàn, có tính đại diện và có thể tái tạo.
- [ ] Tài khoản, quyền và hỗ trợ cho người tham gia đã sẵn sàng.
- [ ] Có cách ghi nhận phản hồi và bằng chứng mà không thu thập dữ liệu không cần thiết.
- [ ] Có quy trình phân loại lỗi, cải tiến, vấn đề môi trường và nhu cầu đào tạo.
- [ ] Có kế hoạch pilot, giám sát và phục hồi nếu cần sử dụng môi trường thật.
- [ ] Có mẫu báo cáo và người có thẩm quyền phê duyệt kết quả.

## Kết luận

UAT có giá trị khi người tham gia đại diện đúng cho công việc thực tế, hoạt động được chọn phù hợp với mục tiêu chấp nhận và môi trường đủ đại diện để tạo bằng chứng đáng tin cậy. Hãy chọn kịch bản nghiệp vụ, nhiệm vụ, khám phá, walkthrough, đối soát hoặc pilot theo rủi ro và quyết định cần đưa ra. Chuẩn bị người dùng, dữ liệu, thiết bị, quyền và tiêu chí trước phiên; ghi nhận rõ lỗi, cải tiến, giới hạn và rủi ro còn lại. Quyết định chấp nhận cần dựa trên bằng chứng và do người có thẩm quyền chịu trách nhiệm.
