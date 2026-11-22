# Liên kết phạm vi với yêu cầu, rủi ro và giới hạn nguồn lực

Phạm vi kiểm thử xác định **những gì sẽ được kiểm tra, ở mức độ nào, trong điều kiện nào và phần nào được chủ động đưa ra ngoài phạm vi**. Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, phạm vi không nên được chọn chỉ bằng cách liệt kê các chức năng hoặc chia đều số lượng test cho từng nhóm. Phạm vi cần xuất phát từ yêu cầu phải đáp ứng, rủi ro nếu sản phẩm thất bại và nguồn lực thực tế có thể huy động.

Ba yếu tố này tạo thành một quyết định có liên hệ trực tiếp. Yêu cầu cho biết hành vi và chất lượng nào cần bằng chứng. Rủi ro cho biết nơi nào cần kiểm tra sâu hoặc sớm hơn. Nguồn lực xác định mức kiểm tra nào có thể thực hiện trong thời gian, nhân lực, môi trường và công cụ hiện có. Khi một phần kiểm thử không thể thực hiện, nhóm cần hiểu rủi ro còn lại và quyết định có chủ đích thay vì âm thầm bỏ qua.

## 1. Phạm vi kiểm thử bao gồm những gì?

Phạm vi kiểm thử là ranh giới của hoạt động kiểm thử trong một sản phẩm, phiên bản, đợt phát hành hoặc thay đổi cụ thể. Nó mô tả cả đối tượng được kiểm tra lẫn cách kiểm tra. Một mô tả phạm vi có thể bao gồm:

- **Đối tượng:** chức năng, dịch vụ, module, API, giao diện, dữ liệu, cấu hình, thiết bị hoặc quy trình nghiệp vụ.
- **Yêu cầu và thuộc tính:** yêu cầu chức năng, quy tắc nghiệp vụ, hiệu năng, độ tin cậy, bảo mật, khả năng sử dụng, khả năng tiếp cận, tương thích và khả năng phục hồi.
- **Mức kiểm thử:** đơn vị, tích hợp, hệ thống, chấp nhận, kiểm thử hồi quy hoặc các mức phù hợp khác.
- **Phương pháp và chiều sâu:** kiểm tra luồng chính, trường hợp biên, dữ liệu bất thường, tải, lỗi phụ thuộc, phân quyền, khả năng khôi phục hoặc thử nghiệm với người dùng.
- **Điều kiện:** môi trường, phiên bản phần mềm, thiết bị, cấu hình, dữ liệu, vai trò người dùng, dịch vụ phụ thuộc và tải thử nghiệm.
- **Ranh giới:** phần nằm trong phạm vi, phần ngoài phạm vi, giả định, giới hạn đã biết và điều kiện cần để bắt đầu kiểm thử.
- **Bằng chứng và tiêu chí hoàn tất:** kết quả cần lưu, yêu cầu cần truy vết, tiêu chí đạt/không đạt và điều kiện dừng hoặc chuyển cấp xử lý.

Phạm vi kiểm thử có thể thay đổi theo mục đích. Phạm vi của một lần kiểm thử đơn vị cho hàm tính giá nhỏ hơn nhiều so với phạm vi kiểm thử chấp nhận của toàn bộ quy trình bán hàng. Một đợt phát hành sửa lỗi cũng có thể cần phạm vi hẹp hơn một lần thay đổi kiến trúc, nhưng vẫn phải xem xét các thành phần phụ thuộc và nguy cơ hồi quy.

### Phân biệt phạm vi kiểm thử và kế hoạch kiểm thử

Phạm vi trả lời câu hỏi *cái gì được kiểm tra và ranh giới ở đâu*. Kế hoạch kiểm thử giải thích cách tổ chức công việc để thực hiện phạm vi đó: lịch, người phụ trách, môi trường, dữ liệu, công cụ, ước lượng, lịch chạy, cách báo cáo và phối hợp. Hai nội dung liên quan nhưng không thay thế nhau.

Ví dụ, “kiểm thử API tạo phiếu nhập kho, bao gồm kiểm tra quyền, quy tắc số lượng, tích hợp tồn kho và xử lý gửi lại yêu cầu” là mô tả phạm vi. “Hai tester thực hiện trong ba ngày trên môi trường staging, dùng bộ dữ liệu X và báo lỗi trên hệ thống theo dõi” là một phần của kế hoạch thực hiện.

## 2. Bắt đầu từ yêu cầu và test basis

Yêu cầu là căn cứ đầu tiên để xác định điều gì cần bằng chứng. Nhóm nên thu thập và phân loại các nguồn làm căn cứ kiểm thử (test basis), chẳng hạn:

- Yêu cầu chức năng, user story, tiêu chí chấp nhận và quy tắc nghiệp vụ.
- Đặc tả API, hợp đồng sự kiện, schema dữ liệu và mô hình trạng thái.
- Thiết kế kiến trúc, giao diện, luồng xử lý và cấu hình.
- Yêu cầu phi chức năng, mục tiêu chất lượng, chính sách bảo mật và cam kết dịch vụ.
- Quy trình vận hành, hướng dẫn người dùng, quy định tuân thủ và phản hồi từ các phiên bản trước.

Không phải tài liệu nào cũng có cùng độ tin cậy. Nếu yêu cầu mâu thuẫn, lỗi thời hoặc thiếu tiêu chí đo, nhóm cần làm rõ với chủ sở hữu trước khi lập kết luận kiểm thử. Một yêu cầu chưa rõ không thể được coi là đã kiểm tra đầy đủ chỉ vì có một test case gắn với nó.

### Chuyển yêu cầu thành nội dung kiểm thử

Với mỗi yêu cầu, hãy xác định hành vi mong đợi, điều kiện đầu vào, trạng thái trước và sau, vai trò, dữ liệu, ngoại lệ và bằng chứng cần thu thập. Yêu cầu chức năng thường dẫn đến kiểm tra luồng chính, điều kiện biên và quy tắc nghiệp vụ. Yêu cầu phi chức năng cần nêu điều kiện đo cụ thể, ví dụ tải, môi trường, phân vị độ trễ, cửa sổ đo hoặc mức độ lỗ hổng được chấp nhận.

Một yêu cầu như “nhân viên chỉ được xác nhận phiếu nhập thuộc kho mình phụ trách” có thể được chuyển thành các kiểm tra: người đúng kho được phép xác nhận; người thuộc kho khác bị từ chối; người không có vai trò phù hợp bị từ chối; thay đổi quyền trong phiên làm việc được xử lý theo chính sách; thao tác bị từ chối không làm thay đổi dữ liệu. Như vậy, phạm vi được mô tả bằng hành vi và rủi ro cụ thể thay vì một nhãn chung chung như “test phân quyền”.

### Duy trì truy vết hai chiều

Ma trận truy vết giúp nối yêu cầu với rủi ro, hoạt động kiểm thử và kết quả. Truy vết từ yêu cầu đến test cho biết yêu cầu nào chưa có bằng chứng. Truy vết ngược từ test đến yêu cầu hoặc rủi ro giúp phát hiện test không có mục đích rõ ràng, trùng lặp hoặc chưa được giải thích.

| Mã yêu cầu | Yêu cầu / tiêu chí | Rủi ro liên quan | Nội dung kiểm thử | Bằng chứng |
|---|---|---|---|---|
| REQ-01 | Chỉ nhân viên thuộc kho phụ trách mới được xác nhận phiếu nhập | Người không có quyền thay đổi tồn kho | Kiểm tra quyền hợp lệ, sai kho, sai vai trò và thao tác bị từ chối | Kết quả API/UI, log phân quyền, trạng thái dữ liệu trước/sau |
| REQ-02 | Số lượng nhập phải là số dương và theo đơn vị hợp lệ | Tồn kho sai do dữ liệu không hợp lệ | Kiểm tra 0, số âm, số thập phân, giới hạn lớn và đơn vị không tương thích | Kết quả kiểm tra dữ liệu và bản ghi tồn kho |
| REQ-03 | Xác nhận phiếu nhập chỉ cập nhật tồn kho một lần | Gửi lại yêu cầu làm tăng tồn kho trùng | Gửi lặp, timeout, retry và xử lý đồng thời | Số lần cập nhật, mã giao dịch và log |

Ma trận không nhất thiết phải là một bảng lớn duy nhất. Có thể dùng công cụ quản lý yêu cầu, test management hoặc hệ thống theo dõi công việc. Điều quan trọng là mỗi liên kết có định danh ổn định và có thể cập nhật khi yêu cầu thay đổi.

## 3. Dùng rủi ro để xác định độ sâu và thứ tự

Không phải yêu cầu nào cũng có hậu quả như nhau khi thất bại. Phân tích rủi ro giúp xác định phần nào cần được kiểm tra kỹ hơn, kiểm tra sớm hơn hoặc có nhiều lớp bảo vệ hơn.

Rủi ro sản phẩm thường được xem xét qua hai thành phần:

- **Khả năng xảy ra:** xác suất hoặc mức độ dễ phát sinh lỗi trong điều kiện cụ thể, dựa trên độ phức tạp, thay đổi gần đây, lịch sử lỗi, phụ thuộc và độ trưởng thành của công nghệ.
- **Mức độ tác động:** hậu quả nếu lỗi xảy ra, chẳng hạn mất dữ liệu, giao dịch sai, gián đoạn vận hành, lộ thông tin, vi phạm tuân thủ, tổn thất tài chính hoặc ảnh hưởng người dùng.

Nhóm có thể xếp hạng rủi ro theo mức thấp, trung bình, cao, nghiêm trọng. Nếu dùng điểm số, chẳng hạn khả năng xảy ra nhân với tác động, hãy coi đó là công cụ hỗ trợ ưu tiên tương đối. Điểm số không phải xác suất chính xác và không thay thế thảo luận về hậu quả hoặc nghĩa vụ bắt buộc.

### Ví dụ bảng đánh giá rủi ro

| Khu vực | Khả năng | Tác động | Mức ưu tiên minh họa | Định hướng kiểm thử |
|---|---|---|---|---|
| Phân quyền xác nhận phiếu nhập | Trung bình | Nghiêm trọng | Rất cao | Kiểm thử dương/âm, vai trò, kho khác, API trực tiếp và log kiểm toán |
| Cập nhật tồn kho khi gửi lại yêu cầu | Cao | Cao | Rất cao | Kiểm thử idempotency, retry, timeout, xử lý đồng thời và phục hồi |
| Định dạng ngày trên màn hình lịch sử | Trung bình | Thấp | Thấp | Kiểm tra định dạng, múi giờ và các trình duyệt được hỗ trợ |
| Xuất báo cáo tồn kho lớn | Trung bình | Trung bình | Trung bình | Kiểm tra dữ liệu lớn, thời gian xử lý, bộ nhớ và quyền tải xuống |

Mức ưu tiên trong bảng chỉ là ví dụ. Nhóm cần dùng tiêu chí thống nhất và điều chỉnh theo bối cảnh. Một lỗi có khả năng xảy ra thấp vẫn có thể cần ưu tiên rất cao nếu hậu quả nghiêm trọng hoặc có yêu cầu pháp lý, bảo mật, an toàn bắt buộc.

### Từ rủi ro đến độ sâu kiểm thử

Rủi ro cao thường cần nhiều loại bằng chứng hơn. Với chức năng cập nhật tồn kho, nhóm có thể kết hợp review logic, kiểm thử đơn vị, tích hợp cơ sở dữ liệu, kiểm thử đồng thời, kiểm tra retry, kiểm thử phục hồi và đối chiếu log. Với định dạng ngày ít tác động, có thể chỉ cần kiểm tra các trường hợp đại diện trên phạm vi trình duyệt được hỗ trợ.

Rủi ro cũng quyết định thứ tự. Các kiểm tra có thể phát hiện lỗi nghiêm trọng nên được chạy sớm, nhất là khi kết quả của chúng ảnh hưởng đến quyết định tiếp tục kiểm thử hoặc phát hành. Kiểm thử khám phá có định hướng rủi ro có thể bổ sung cho test case đã viết, đặc biệt ở các khu vực mới, phức tạp hoặc có nhiều trạng thái.

Không nên hiểu ưu tiên rủi ro là bỏ toàn bộ kiểm tra ở vùng rủi ro thấp. Các yêu cầu cơ bản, tiêu chí tuân thủ và kiểm tra hồi quy tối thiểu vẫn cần được duy trì. Ưu tiên giúp phân bổ độ sâu và thứ tự, đồng thời làm rõ những gì chưa được kiểm tra.

## 4. Đưa giới hạn nguồn lực vào quyết định phạm vi

Nguồn lực không chỉ là số người hoặc số ngày. Những giới hạn thường ảnh hưởng đến phạm vi gồm:

- **Nhân lực và kỹ năng:** số người, kinh nghiệm kiểm thử, kiến thức nghiệp vụ, năng lực tự động hóa, bảo mật, hiệu năng hoặc kiểm thử thiết bị.
- **Thời gian:** ngày phát hành, thời gian chờ build, thời gian sửa lỗi, cửa sổ kiểm thử, lịch của người dùng nghiệm thu và thời gian cần để chạy test dài.
- **Môi trường:** số môi trường khả dụng, mức tương đồng với production, khả năng mô phỏng lỗi, dữ liệu đại diện và quyền truy cập.
- **Công cụ và hạ tầng:** giấy phép, thiết bị, dịch vụ giả lập, công cụ quan sát, năng lực tạo tải và chi phí vận hành.
- **Phụ thuộc:** API bên thứ ba, nhóm khác, dữ liệu từ đối tác, phê duyệt bảo mật, tài khoản thử nghiệm hoặc lịch triển khai của hệ thống liên quan.
- **Tính sẵn sàng của sản phẩm:** build chưa ổn định, yêu cầu thay đổi liên tục, dữ liệu chưa hoàn chỉnh hoặc chức năng chưa tích hợp.

Một phạm vi chỉ khả thi khi các điều kiện cần được xác định. Ví dụ, kiểm thử tích hợp thanh toán với đối tác không thể hoàn tất nếu chưa có sandbox, thông tin xác thực và dữ liệu thử nghiệm hợp lệ. Việc ghi nhận phụ thuộc này giúp tránh coi một hạng mục chưa thể thực hiện là đã được kiểm thử.

### Ước lượng công việc theo hoạt động

Thay vì ước lượng chung “kiểm thử toàn bộ trong năm ngày”, hãy chia thành các hoạt động: phân tích yêu cầu, chuẩn bị dữ liệu, cấu hình môi trường, thiết kế test, tự động hóa, thực thi, điều tra lỗi, kiểm thử lại, hồi quy và báo cáo. Ước lượng cần tính cả thời gian chờ, phối hợp và xử lý kết quả.

Ví dụ, một ngày chạy kiểm thử không có nghĩa chỉ cần một ngày lịch. Nếu môi trường chỉ được cấp vào buổi chiều, dữ liệu cần đội nghiệp vụ chuẩn bị, hoặc build được tạo vào cuối ngày, lịch thực tế phải phản ánh những phụ thuộc này.

### Chọn phương án khi nguồn lực không đủ

Khi năng lực không đáp ứng toàn bộ nhu cầu, nhóm nên cân nhắc các phương án theo thứ tự có kiểm soát:

1. **Giảm trùng lặp:** hợp nhất các kiểm tra có cùng mục tiêu, tái sử dụng dữ liệu và thành phần kiểm thử đáng tin cậy.
2. **Tự động hóa phần lặp lại phù hợp:** ưu tiên hồi quy ổn định, kiểm tra hợp đồng hoặc các trường hợp có tần suất chạy cao; tính cả chi phí xây dựng và bảo trì tự động hóa.
3. **Điều chỉnh thứ tự:** chạy trước kiểm tra rủi ro cao, kiểm tra khói và các điều kiện có thể chặn sớm.
4. **Thu hẹp phạm vi có lý do:** giới hạn phiên bản, thiết bị, dữ liệu hoặc luồng ít rủi ro nếu có cơ sở và ghi rõ phần bị loại trừ.
5. **Bổ sung hoặc điều chuyển nguồn lực:** mượn chuyên gia, thêm môi trường, dùng dịch vụ kiểm thử phù hợp hoặc điều chỉnh lịch.
6. **Chia đợt phát hành hoặc giảm phạm vi sản phẩm:** nếu rủi ro không thể được kiểm soát trong thời hạn hiện tại, cân nhắc phát hành theo phần hoặc hoãn tính năng.

Mọi lựa chọn cần ghi lại tác động và rủi ro còn lại. Không nên giảm kiểm thử một cách cơ học theo tỷ lệ phần trăm hoặc bỏ ngẫu nhiên các trường hợp cuối danh sách. Nếu phải loại một hạng mục, hãy nêu lý do, người chấp thuận, biện pháp thay thế nếu có và thời điểm đánh giá lại.

## 5. Ví dụ xuyên suốt: ứng dụng nhập hàng cho kho

Giả sử tổ chức triển khai ứng dụng để nhân viên kho tạo và xác nhận phiếu nhập hàng trên thiết bị di động. Hệ thống tích hợp với dịch vụ quản lý tồn kho và hệ thống danh tính. Đợt phát hành này có thời hạn hai tuần, một tester nghiệp vụ, một tester tự động hóa bán thời gian và một môi trường staging.

### Xác định yêu cầu và rủi ro

Nhóm nhận diện các yêu cầu quan trọng:

- Nhân viên chỉ xem và xác nhận phiếu thuộc kho mình được phân công.
- Số lượng nhập phải hợp lệ theo đơn vị sản phẩm.
- Một phiếu đã xác nhận chỉ cập nhật tồn kho một lần, kể cả khi thiết bị gửi lại yêu cầu sau timeout.
- Người dùng phải nhận được trạng thái rõ ràng khi hệ thống tồn kho tạm thời không khả dụng.
- Ứng dụng cần hoạt động trên các phiên bản thiết bị nằm trong danh sách hỗ trợ.

Nhóm đánh giá sai quyền có thể làm thay đổi dữ liệu kho trái phép; gửi lại yêu cầu có thể làm tăng tồn kho trùng; mất kết nối có thể khiến nhân viên không biết phiếu đã được ghi nhận hay chưa. Đây là các rủi ro cao cần kiểm tra sâu. Định dạng một nhãn phụ ít ảnh hưởng hơn và có thể kiểm tra trên một tập đại diện.

### Chốt phạm vi trong và ngoài

| Hạng mục | Quyết định phạm vi | Lý do / điều kiện |
|---|---|---|
| Phân quyền xem và xác nhận phiếu | Trong phạm vi, ưu tiên cao | Rủi ro dữ liệu và truy cập trái phép; kiểm tra qua UI và API |
| Quy tắc số lượng, đơn vị | Trong phạm vi | Ảnh hưởng tính đúng đắn của tồn kho; gồm biên và dữ liệu không hợp lệ |
| Gửi lặp, timeout và cập nhật tồn kho | Trong phạm vi, ưu tiên cao | Rủi ro tạo bản ghi hoặc cập nhật trùng; cần kiểm tra tích hợp và đồng thời |
| Trạng thái khi dịch vụ tồn kho lỗi | Trong phạm vi | Cần kiểm tra thông báo, retry và khả năng tiếp tục an toàn |
| Tương thích thiết bị | Trong phạm vi có giới hạn | Kiểm tra thiết bị đại diện trong danh sách hỗ trợ đã thống nhất |
| Kiểm thử tải quy mô lớn trên toàn hệ thống | Ngoài phạm vi đợt này | Chưa có môi trường và công cụ tạo tải tương đương production; ghi nhận là rủi ro còn lại và lập kế hoạch riêng |
| Phiên bản hệ điều hành ngoài danh sách hỗ trợ | Ngoài phạm vi | Không thuộc cam kết hỗ trợ của phiên bản phát hành |

Việc đưa kiểm thử tải lớn ra ngoài phạm vi không có nghĩa rủi ro hiệu năng đã được loại bỏ. Chủ sở hữu sản phẩm và vận hành cần biết giới hạn này, xác định liệu có thể phát hành với điều kiện hiện tại hay cần bổ sung bằng chứng trước khi quyết định.

### Phân bổ nguồn lực và cách thực hiện

Với một tester nghiệp vụ, nhóm ưu tiên chuẩn bị kịch bản phân quyền, quy tắc số lượng, luồng xác nhận và lỗi kết nối. Tester tự động hóa tập trung vào kiểm thử API, kiểm tra hợp đồng và hồi quy cho các quy tắc ổn định. Môi trường staging được đặt lịch để chạy trước các kiểm tra tích hợp rủi ro cao; dữ liệu được chuẩn bị cho nhiều kho, nhiều vai trò và các trạng thái phiếu khác nhau.

Nhóm có thể chia công việc theo các chặng:

1. Làm rõ yêu cầu và quyền, thống nhất dữ liệu, điều kiện môi trường và tiêu chí đạt.
2. Chạy kiểm tra khói để xác nhận build, đăng nhập, kết nối dịch vụ và dữ liệu cơ bản hoạt động.
3. Kiểm tra phân quyền, quy tắc số lượng, gửi lặp, timeout và phục hồi.
4. Chạy hồi quy trên luồng chính và thiết bị đại diện.
5. Tổng hợp bằng chứng, lỗi còn mở, hạng mục ngoài phạm vi và rủi ro tồn dư để trình quyết định phát hành.

Nếu staging không thể mô phỏng đồng thời nhiều yêu cầu, nhóm không được suy ra rằng hành vi đồng thời đã được kiểm chứng. Cần ghi rõ giới hạn, đề xuất môi trường hoặc phương pháp bổ sung và xem xét mức rủi ro trước khi phát hành.

## 6. Ghi rõ phần ngoài phạm vi và rủi ro tồn dư

Phần ngoài phạm vi cần được mô tả cụ thể như phần trong phạm vi. Một ghi chú tốt trả lời được:

- Hạng mục hoặc điều kiện nào không được kiểm thử?
- Vì sao bị loại: không thuộc phiên bản, thiếu môi trường, thiếu dữ liệu, thiếu công cụ, phụ thuộc chưa sẵn sàng hay rủi ro thấp hơn các ưu tiên khác?
- Hậu quả có thể xảy ra nếu hạng mục đó có lỗi?
- Có biện pháp thay thế nào, chẳng hạn review, kiểm tra thủ công, giám sát tăng cường, giới hạn tính năng hoặc triển khai theo giai đoạn?
- Ai chấp thuận rủi ro còn lại và khi nào cần đánh giá lại?

Không dùng những câu như “không kiểm thử các phần ít quan trọng” mà không định nghĩa phần nào và dựa trên tiêu chí gì. Phạm vi loại trừ cũng không nên được hiểu là miễn trách nhiệm: nếu có nghĩa vụ pháp lý, hợp đồng hoặc chính sách bắt buộc, nhóm phải xử lý theo quy trình có thẩm quyền.

Rủi ro tồn dư là phần rủi ro vẫn còn sau các hoạt động kiểm soát và kiểm thử đã thực hiện. Báo cáo phạm vi nên nêu rõ rủi ro này thay vì chỉ liệt kê số test pass. Ví dụ: “Chưa kiểm thử tải cao điểm trên môi trường tương đương production vì môi trường chưa sẵn sàng; rủi ro nghẽn dịch vụ dưới tải cao vẫn còn; chủ sở hữu vận hành cần đánh giá trước khi mở rộng lưu lượng.”

## 7. Quản lý thay đổi phạm vi

Phạm vi thường thay đổi khi yêu cầu mới xuất hiện, lỗi nghiêm trọng được phát hiện, kiến trúc thay đổi, build trễ hoặc nguồn lực bị điều chuyển. Mỗi thay đổi có thể làm tăng hoặc giảm rủi ro, vì vậy cần đánh giá lại thay vì chỉ thêm hoặc xóa test case.

Khi có thay đổi, thực hiện các bước sau:

1. Ghi nhận yêu cầu thay đổi và lý do.
2. Xác định yêu cầu, thành phần, giao diện và dữ liệu bị ảnh hưởng.
3. Đánh giá lại rủi ro mới và rủi ro hồi quy ở các phần liên quan.
4. Ước lượng tác động đến thời gian, nhân lực, môi trường và công cụ.
5. Đề xuất điều chỉnh phạm vi, lịch hoặc nguồn lực; nêu rõ phần nào bị hoãn hoặc loại trừ.
6. Xin quyết định từ người có thẩm quyền và cập nhật ma trận truy vết, kế hoạch cùng báo cáo trạng thái.

Ví dụ, thay đổi cách tính số lượng quy đổi từ thùng sang đơn vị lẻ có thể ảnh hưởng đến dữ liệu, API, giao diện, báo cáo và tồn kho hiện tại. Phạm vi hồi quy cần dựa trên các đường đi dữ liệu và quy tắc phụ thuộc, không chỉ kiểm tra màn hình vừa thay đổi.

## 8. Tiêu chí hoàn tất và báo cáo phạm vi

Phạm vi cần gắn với tiêu chí hoàn tất có thể đánh giá. Một bộ tiêu chí thường xem xét:

- Các yêu cầu bắt buộc có liên kết đến bằng chứng kiểm thử hoặc có ghi rõ lý do chưa kiểm tra.
- Các rủi ro cao đã được kiểm tra theo chiều sâu đã thống nhất, hoặc có quyết định chấp nhận rủi ro đúng thẩm quyền.
- Các lỗi nghiêm trọng và lỗi chặn phát hành được xử lý theo chính sách.
- Kết quả được lưu cùng phiên bản build, môi trường, dữ liệu, cấu hình và thời điểm chạy.
- Các hạng mục ngoài phạm vi, giới hạn nguồn lực và rủi ro tồn dư được báo cáo.
- Các bên chịu trách nhiệm đã xem xét kết quả trước quyết định phát hành.

Không nên dùng riêng tỷ lệ test pass làm tiêu chí hoàn tất. Tỷ lệ này có thể cao dù những yêu cầu quan trọng chưa có test, hoặc các test chỉ bao phủ luồng thuận lợi. Cần xem cả độ bao phủ yêu cầu, mức bao phủ rủi ro, chất lượng bằng chứng và các ngoại lệ.

### Mẫu tóm tắt phạm vi

| Trường | Nội dung cần ghi |
|---|---|
| Phiên bản / đợt phát hành | Định danh build, phạm vi thay đổi và thời gian áp dụng |
| Đối tượng trong phạm vi | Module, API, quy trình, thiết bị, vai trò và thuộc tính chất lượng |
| Căn cứ kiểm thử | Yêu cầu, tiêu chí chấp nhận, thiết kế, chính sách và phiên bản tài liệu |
| Ưu tiên rủi ro | Rủi ro cao, vừa, thấp và lý do xếp hạng |
| Phương pháp / chiều sâu | Mức kiểm thử, loại test, dữ liệu, điều kiện và số lần chạy |
| Ngoài phạm vi | Hạng mục bị loại, lý do, tác động và biện pháp thay thế |
| Nguồn lực / phụ thuộc | Người, kỹ năng, lịch, môi trường, công cụ và điều kiện chờ |
| Tiêu chí hoàn tất | Bằng chứng bắt buộc, điều kiện lỗi, ngưỡng và phê duyệt |
| Rủi ro tồn dư | Điều chưa được kiểm tra, ảnh hưởng và người chấp nhận |

## 9. Những sai lầm thường gặp

**Chỉ liệt kê chức năng mà không gắn với yêu cầu.** Danh sách màn hình hoặc module không chứng minh được mục tiêu kiểm thử. Hãy liên kết từng hạng mục với yêu cầu, tiêu chí chấp nhận hoặc rủi ro cần kiểm soát.

**Chia đều nỗ lực cho mọi hạng mục.** Cách làm này có thể dành quá nhiều thời gian cho phần ít tác động và thiếu bằng chứng ở luồng có hậu quả nghiêm trọng. Hãy ưu tiên theo khả năng xảy ra, tác động và nghĩa vụ bắt buộc.

**Đồng nhất phạm vi với những gì có thể kiểm tra ngay.** Việc môi trường hoặc dữ liệu chưa sẵn sàng là một giới hạn cần được báo cáo và giải quyết; nó không tự làm biến mất yêu cầu hoặc rủi ro.

**Không ghi phần ngoài phạm vi.** Người đọc có thể hiểu nhầm rằng toàn bộ sản phẩm đã được kiểm tra. Hãy nêu rõ điều kiện, lý do, tác động và người chấp thuận.

**Ước lượng chỉ dựa trên thời gian chạy test.** Phân tích, chuẩn bị dữ liệu, cấu hình, điều tra lỗi, kiểm thử lại và hồi quy đều tiêu tốn nguồn lực. Hãy tính toàn bộ vòng đời công việc.

**Tự động hóa mọi thứ khi thiếu nhân lực.** Tự động hóa cần thời gian xây dựng, dữ liệu ổn định và bảo trì. Ưu tiên các kiểm tra lặp lại, có giá trị và có thể tự động hóa tin cậy; giữ kiểm thử khám phá hoặc đánh giá trải nghiệm cho nơi cần phán đoán của con người.

**Coi mọi rủi ro thấp là không cần kiểm tra.** Rủi ro có thể thay đổi khi có dữ liệu mới hoặc thay đổi kiến trúc. Duy trì kiểm tra cơ bản và xem xét lại đánh giá khi bối cảnh thay đổi.

**Thay đổi phạm vi mà không cập nhật truy vết và quyết định.** Điều này làm báo cáo không còn phản ánh công việc thực tế. Mọi thay đổi cần có lý do, đánh giá tác động và người phê duyệt.

## 10. Checklist xác định phạm vi kiểm thử

Khi bắt đầu:

- [ ] Đã xác định phiên bản, thay đổi và mục tiêu của đợt kiểm thử.
- [ ] Đã thu thập test basis và kiểm tra tính rõ ràng, nhất quán của yêu cầu.
- [ ] Đã xác định đối tượng, giao diện, dữ liệu, môi trường, vai trò và thuộc tính chất lượng liên quan.
- [ ] Mỗi yêu cầu quan trọng có tiêu chí hoặc bằng chứng cần thu thập.

Khi ưu tiên và phân bổ nguồn lực:

- [ ] Rủi ro được đánh giá theo khả năng xảy ra và mức độ tác động.
- [ ] Hạng mục rủi ro cao và yêu cầu bắt buộc được ưu tiên về độ sâu hoặc thứ tự.
- [ ] Nhân lực, kỹ năng, thời gian, môi trường, dữ liệu, công cụ và phụ thuộc đã được xác nhận.
- [ ] Ước lượng gồm cả chuẩn bị, thực thi, điều tra, kiểm thử lại và báo cáo.
- [ ] Phần ngoài phạm vi có lý do, tác động và người chấp thuận rõ ràng.

Trước khi kết thúc:

- [ ] Truy vết yêu cầu, rủi ro, test và kết quả được cập nhật.
- [ ] Tiêu chí hoàn tất và điều kiện phát hành được đánh giá.
- [ ] Giới hạn kiểm thử và rủi ro tồn dư được báo cáo minh bạch.
- [ ] Các thay đổi phạm vi đã được phê duyệt và cập nhật tài liệu liên quan.
- [ ] Người có thẩm quyền đã xem xét bằng chứng trước khi quyết định phát hành.

## 11. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một thay đổi nhỏ ở màn hình phiếu nhập cũng cập nhật API và quy tắc tồn kho. Nếu chỉ kiểm tra giao diện, phạm vi chưa phản ánh đầy đủ rủi ro. Cần truy vết thay đổi đến API, dữ liệu, quyền và các luồng phụ thuộc để chọn kiểm thử hồi quy phù hợp.

**Tình huống 2:** Nhóm không có môi trường để kiểm thử tải cao điểm. Hạng mục này có thể được ghi ngoài phạm vi của đợt hiện tại, nhưng phải nêu rõ lý do, rủi ro hiệu năng còn lại, biện pháp thay thế nếu có và người chịu trách nhiệm quyết định phát hành. Không được báo cáo rằng hiệu năng cao điểm đã đạt.

**Tình huống 3:** Một lỗi phân quyền có khả năng xảy ra thấp nhưng có thể cho phép nhân viên sửa tồn kho của kho khác. Tác động nghiêm trọng khiến rủi ro vẫn cần ưu tiên cao. Nhóm nên kiểm tra cả quyền ở giao diện lẫn API và xác minh dữ liệu không đổi khi thao tác bị từ chối.

**Tình huống 4:** Chỉ còn một ngày trước phát hành và có nhiều test hồi quy chưa chạy. Nhóm cần xem xét rủi ro của từng luồng, ưu tiên kiểm tra bắt buộc và rủi ro cao, đánh giá khả năng chia đợt hoặc hoãn phát hành. Việc bỏ test phải được ghi nhận như giới hạn và rủi ro tồn dư, có quyết định đúng thẩm quyền.

Khi xác định phạm vi, hãy tự hỏi: **yêu cầu nào cần bằng chứng, điều gì có thể xảy ra nếu nó thất bại, và nguồn lực hiện có cho phép kiểm tra đến mức nào?** Trả lời rõ ba câu hỏi này giúp phạm vi có cơ sở, có thể thực hiện và minh bạch về rủi ro.

## Kết luận

Phạm vi kiểm thử cần liên kết yêu cầu với rủi ro và khả năng thực hiện. Yêu cầu xác định điều cần chứng minh; rủi ro quyết định mức ưu tiên và chiều sâu; nguồn lực giúp nhóm chọn cách triển khai khả thi và nhận diện giới hạn. Khi truy vết được các mối liên hệ, ghi rõ phần trong và ngoài phạm vi, đồng thời báo cáo rủi ro tồn dư, nhóm có cơ sở đáng tin cậy hơn để đánh giá chất lượng và ra quyết định phát hành.
