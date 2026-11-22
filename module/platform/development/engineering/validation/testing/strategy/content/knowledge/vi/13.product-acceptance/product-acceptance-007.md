# Lập lịch tham gia của bên liên quan và xử lý phản hồi

Kiểm thử chấp nhận sản phẩm cần sự tham gia đúng lúc của những người hiểu nhu cầu nghiệp vụ, trực tiếp sử dụng sản phẩm, chịu trách nhiệm vận hành hoặc có quyền quyết định phát hành. Nếu các bên liên quan chỉ được mời vào cuối dự án, họ có thể không còn đủ thời gian để đánh giá kỹ, phản hồi đến muộn hoặc phát hiện những khác biệt lớn giữa sản phẩm và cách công việc thực tế diễn ra.

Lập lịch tham gia giúp nhóm xác định ai cần tham gia, tham gia ở giai đoạn nào, cần chuẩn bị gì và phải dành bao nhiêu thời gian. Xử lý phản hồi giúp biến nhận xét thành thông tin có thể phân loại, điều tra, ưu tiên và theo dõi đến khi có quyết định rõ ràng.

Hai hoạt động này cần được thiết kế cùng nhau. Lịch kiểm thử chỉ hữu ích khi người tham gia hiểu mục tiêu và có cách gửi phản hồi. Phản hồi chỉ có giá trị khi nhóm ghi nhận bối cảnh, đánh giá tác động và thông báo kết quả xử lý cho người đã nêu vấn đề.

## 1. Vai trò của bên liên quan trong kiểm thử chấp nhận

Kiểm thử chấp nhận đánh giá xem sản phẩm có đáp ứng nhu cầu, quy tắc nghiệp vụ và điều kiện sử dụng đã thống nhất hay không. Hoạt động này có thể bao gồm kiểm thử chấp nhận người dùng (UAT), xác nhận nghiệp vụ, đánh giá vận hành, rà soát bảo mật hoặc xác nhận điều kiện hợp đồng tùy loại sản phẩm.

Bên liên quan là cá nhân hoặc nhóm có kiến thức, nhu cầu, trách nhiệm hoặc quyền quyết định liên quan đến sản phẩm. Không phải ai cũng cần tham gia mọi phiên kiểm thử. Nhóm cần xác định đúng người cho từng câu hỏi cần trả lời.

Các nhóm thường gặp:

- **Chủ sản phẩm hoặc đại diện nghiệp vụ:** xác nhận mục tiêu, quy tắc, ưu tiên và tiêu chí chấp nhận.
- **Người dùng đại diện:** thực hiện các nhiệm vụ thực tế và đánh giá mức độ phù hợp với công việc.
- **Chuyên gia nghiệp vụ:** giải thích quy trình, trường hợp ngoại lệ và quy định chuyên ngành.
- **Nhóm phát triển:** giải thích hành vi kỹ thuật, điều tra vấn đề và thực hiện sửa đổi.
- **Nhóm kiểm thử hoặc chất lượng:** chuẩn bị kịch bản, điều phối phiên, ghi nhận bằng chứng và theo dõi lỗi.
- **Nhóm vận hành hoặc hỗ trợ:** đánh giá khả năng triển khai, giám sát, xử lý sự cố và hỗ trợ người dùng.
- **Bảo mật, dữ liệu hoặc tuân thủ:** tham gia khi sản phẩm xử lý dữ liệu nhạy cảm, quyền truy cập hoặc nghĩa vụ đặc thù.
- **Đối tác hoặc khách hàng:** xác nhận tích hợp, quy trình phối hợp và điều kiện nghiệm thu đã cam kết.
- **Người phê duyệt phát hành:** xem xét kết quả, rủi ro còn lại và quyết định chấp nhận.

Một người có thể đại diện cho nhiều vai trò, nhưng cần tránh giả định rằng một đại diện có thể thay mặt mọi nhóm người dùng. Nếu các nhóm sử dụng sản phẩm có quy trình hoặc quyền khác nhau, nên chọn người tham gia phản ánh được sự khác biệt đó.

## 2. Xác định ai cần tham gia và họ cần đóng góp điều gì

Lập danh sách bên liên quan trước khi chốt lịch. Có thể bắt đầu từ hành trình người dùng, yêu cầu, tiêu chí chấp nhận, quy trình vận hành và các quyết định cần được xác nhận.

Với mỗi bên, hãy làm rõ:

- Họ đại diện cho nhóm người dùng hoặc trách nhiệm nào?
- Họ hiểu phần nghiệp vụ hoặc hệ thống nào?
- Họ cần kiểm tra, tư vấn hay phê duyệt?
- Họ có quyền truy cập môi trường và dữ liệu cần thiết không?
- Họ có thể dành thời gian vào giai đoạn nào?
- Ai là người thay thế nếu họ vắng mặt?
- Họ cần nhận kết quả và thông tin theo cách nào?

### Ma trận vai trò và đóng góp

| Bên liên quan | Đóng góp chính | Thời điểm tham gia phù hợp |
|---|---|---|
| Chủ sản phẩm | Xác nhận mục tiêu, tiêu chí chấp nhận và ưu tiên | Khi lập kế hoạch, đầu phiên UAT và khi quyết định kết quả |
| Người dùng đại diện | Thực hiện nhiệm vụ và phản hồi trải nghiệm | Khi môi trường và dữ liệu đã sẵn sàng |
| Chuyên gia nghiệp vụ | Xác nhận quy tắc, dữ liệu và ngoại lệ | Khi thiết kế kịch bản và phân tích phản hồi |
| Nhóm phát triển | Hỗ trợ điều tra và sửa lỗi | Trong suốt thời gian kiểm thử, theo lịch trực |
| Nhóm kiểm thử | Điều phối, ghi nhận và theo dõi bằng chứng | Trước, trong và sau các phiên |
| Nhóm vận hành | Xác nhận quy trình triển khai, giám sát và hỗ trợ | Trước phát hành và trong diễn tập vận hành |
| Bảo mật hoặc tuân thủ | Xem xét yêu cầu kiểm soát đặc thù | Theo các điểm kiểm soát và thay đổi liên quan |
| Khách hàng hoặc đối tác | Xác nhận quy trình tích hợp và điều kiện nghiệm thu | Theo mốc đã thống nhất trong kế hoạch |

Bảng này là điểm khởi đầu. Với từng dự án, cần gắn người hoặc nhóm cụ thể với một nhiệm vụ và kết quả mong đợi. Tránh mời quá nhiều người vào mọi phiên vì điều đó làm tăng chi phí phối hợp và khiến trách nhiệm không rõ.

### Chọn người dùng đại diện

Người dùng tham gia nên phản ánh các nhóm có cách sử dụng khác nhau. Có thể xét:

- Vai trò và quyền truy cập.
- Tần suất và mức độ phức tạp của công việc.
- Kinh nghiệm với sản phẩm hiện tại.
- Khu vực, ngôn ngữ, thiết bị hoặc điều kiện làm việc.
- Nhu cầu tiếp cận và công nghệ hỗ trợ.
- Những tình huống ngoại lệ mà họ thường gặp.

Không nên chỉ chọn người dùng thành thạo nhất hoặc người quen với nhóm phát triển. Người mới có thể phát hiện vấn đề về hướng dẫn và khả năng khám phá; người dùng thường xuyên có thể nhận ra quy trình chậm hoặc thiếu thao tác; chuyên gia nghiệp vụ có thể phát hiện sai lệch quy tắc.

Khi số người tham gia bị giới hạn, hãy ghi rõ nhóm nào được đại diện và nhóm nào chưa có tiếng nói. Kết quả của một nhóm nhỏ không tự động đại diện cho toàn bộ khách hàng.

## 3. Xác định mục tiêu, phạm vi và kết quả của từng phiên

Một phiên tham gia hiệu quả cần có mục tiêu cụ thể. “Mời người dùng kiểm tra sản phẩm” là mô tả quá rộng. Hãy xác định câu hỏi cần trả lời và bằng chứng mong đợi.

Ví dụ:

- Người dùng có thể hoàn thành quy trình tạo đơn mà không cần trợ giúp không?
- Nhân viên có thể tìm và xử lý yêu cầu hoàn tiền theo chính sách không?
- Người quản trị có thể phân quyền đúng cho các nhóm người dùng không?
- Nhóm vận hành có thể triển khai, giám sát và quay lui theo hướng dẫn không?
- Đối tác có thể gửi và nhận dữ liệu theo hợp đồng tích hợp không?

Với mỗi phiên, nên ghi:

- Mục tiêu và phạm vi.
- Người tham gia và vai trò.
- Nhiệm vụ hoặc kịch bản sẽ thực hiện.
- Điều kiện bắt đầu và dữ liệu cần thiết.
- Môi trường, phiên bản và quyền truy cập.
- Thời lượng dự kiến.
- Người điều phối và người ghi nhận.
- Cách gửi phản hồi.
- Kết quả cần có sau phiên.

### Phân biệt các loại phiên tham gia

Không phải mọi cuộc họp đều là một phiên kiểm thử. Có thể chia thành:

- **Phiên định hướng:** giới thiệu mục tiêu, phạm vi, môi trường và cách ghi nhận vấn đề.
- **Phiên thực hiện UAT:** người dùng tự hoàn thành các nhiệm vụ theo kịch bản hoặc mục tiêu.
- **Phiên khám phá:** người tham gia sử dụng sản phẩm theo tình huống thực tế để tìm vấn đề chưa được dự đoán.
- **Phiên rà soát nghiệp vụ:** chuyên gia kiểm tra quy tắc, dữ liệu và trường hợp ngoại lệ.
- **Phiên xác nhận vận hành:** nhóm vận hành kiểm tra hướng dẫn, giám sát, quyền và khả năng phục hồi.
- **Phiên phân loại phản hồi:** các bên liên quan xem xét vấn đề, thống nhất tác động và ưu tiên.
- **Phiên quyết định chấp nhận:** người có thẩm quyền đánh giá bằng chứng và rủi ro còn lại.

Việc tách mục tiêu giúp người tham gia chuẩn bị đúng. Một phiên khám phá cần không gian để thử nghiệm và trao đổi; một phiên xác nhận tiêu chí cần tập trung vào bằng chứng và điều kiện đạt.

## 4. Lập lịch tham gia theo các mốc của dự án

Lịch nên được xây dựng ngược từ ngày cần quyết định chấp nhận hoặc phát hành. Cần dành thời gian cho chuẩn bị, thực hiện, phân loại phản hồi, sửa lỗi, kiểm thử lại và xác nhận cuối cùng.

Không nên xếp toàn bộ UAT sát ngày phát hành. Nếu người dùng phát hiện vấn đề lớn, nhóm cần có thời gian điều tra, sửa và tổ chức kiểm tra lại.

### Các giai đoạn gợi ý

| Giai đoạn | Hoạt động | Bên tham gia chính | Kết quả |
|---|---|---|---|
| Lập kế hoạch | Xác định mục tiêu, người đại diện, phạm vi và lịch | Chủ sản phẩm, kiểm thử, nghiệp vụ | Kế hoạch tham gia |
| Chuẩn bị | Hoàn thiện môi trường, tài khoản, dữ liệu và hướng dẫn | Kiểm thử, phát triển, vận hành | Điều kiện sẵn sàng |
| Định hướng | Giải thích nhiệm vụ, cách dùng và cách gửi phản hồi | Người dùng, điều phối viên | Người tham gia sẵn sàng |
| Thực hiện | Chạy kịch bản, khám phá và ghi nhận kết quả | Người dùng, chuyên gia, kiểm thử | Kết quả và phản hồi ban đầu |
| Phân loại | Xác minh, phân loại và ưu tiên vấn đề | Nghiệp vụ, phát triển, kiểm thử | Danh sách hành động |
| Sửa và kiểm tra lại | Sửa lỗi, xác nhận bản sửa và chạy hồi quy | Phát triển, kiểm thử, người xác nhận | Bằng chứng xử lý |
| Chấp nhận | Xem xét tiêu chí, ngoại lệ và rủi ro còn lại | Chủ sản phẩm, người phê duyệt | Quyết định chấp nhận |
| Theo dõi sau phát hành | Thu thập phản hồi và kiểm tra vận hành | Người dùng, hỗ trợ, vận hành | Vấn đề sau triển khai và bài học |

### Ví dụ lịch UAT trong hai tuần

Lịch dưới đây chỉ minh họa cách phân bổ thời gian. Quy mô thực tế phụ thuộc số lượng luồng, người tham gia và mức độ rủi ro.

| Thời điểm | Hoạt động | Người cần có mặt |
|---|---|---|
| Ngày 1 | Chốt phạm vi, tiêu chí và người đại diện | Chủ sản phẩm, nghiệp vụ, kiểm thử |
| Ngày 2–3 | Chuẩn bị môi trường, tài khoản và dữ liệu | Phát triển, kiểm thử, vận hành |
| Ngày 4 | Hướng dẫn và kiểm tra sẵn sàng | Điều phối viên, người dùng |
| Ngày 5–7 | Thực hiện các kịch bản nghiệp vụ chính | Người dùng đại diện, chuyên gia |
| Ngày 8 | Phân loại và ưu tiên phản hồi | Nghiệp vụ, phát triển, kiểm thử |
| Ngày 9–10 | Sửa lỗi và kiểm tra lại | Phát triển, kiểm thử, người xác nhận |
| Ngày 11 | Chạy hồi quy các luồng bị ảnh hưởng | Kiểm thử, người dùng khi cần |
| Ngày 12 | Xem xét kết quả và rủi ro còn lại | Chủ sản phẩm, vận hành, người phê duyệt |
| Ngày 13–14 | Dự phòng, xử lý vấn đề còn mở và quyết định | Các bên theo vấn đề |

Ngày dự phòng rất quan trọng. Lịch không nên giả định mọi kịch bản đều chạy đạt ngay lần đầu hoặc mọi người tham gia đều luôn sẵn sàng.

## 5. Bảo đảm lịch khả thi và tôn trọng thời gian của người tham gia

Người dùng và chuyên gia nghiệp vụ thường có công việc vận hành hàng ngày. Lịch kiểm thử cần được thống nhất sớm và tránh gây gián đoạn không cần thiết.

Các nguyên tắc thực tế:

- Mời người tham gia sớm, nêu rõ mục tiêu và thời lượng cần dành.
- Chia phiên dài thành các phiên ngắn theo hành trình hoặc vai trò.
- Gửi tài liệu, kịch bản và yêu cầu chuẩn bị trước.
- Tránh xếp nhiều phiên có cùng một chuyên gia vào cùng thời điểm.
- Dành thời gian nghỉ và thời gian ghi nhận phản hồi.
- Có người thay thế cho vai trò quan trọng.
- Xác nhận lại lịch khi môi trường hoặc bản dựng thay đổi.
- Dùng phiên không đồng bộ khi người tham gia chỉ cần xem xét tài liệu hoặc gửi nhận xét.
- Không yêu cầu người dùng lặp lại một kịch bản nếu đã có bằng chứng đáng tin cậy và không có thay đổi liên quan.

### Xử lý thay đổi lịch và vắng mặt

Nếu người tham gia không thể tham dự, điều phối viên cần đánh giá vai trò đó có bắt buộc cho phiên hay không. Có thể chuyển lịch, mời người thay thế đủ năng lực hoặc tách phần xác nhận cần thiết sang một phiên khác.

Không nên đánh dấu một tiêu chí nghiệp vụ đã được chấp nhận chỉ vì người có trách nhiệm vắng mặt. Nếu không có người đủ thẩm quyền, ghi trạng thái chờ xác nhận và nêu ảnh hưởng đến quyết định phát hành.

Khi bản dựng hoặc môi trường chưa sẵn sàng, hãy thông báo sớm, nêu rõ điều kiện chưa đạt và đề xuất lịch mới. Không nên để người tham gia dành thời gian vào một phiên mà họ không thể thực hiện nhiệm vụ.

## 6. Chuẩn bị trước khi mời người dùng kiểm thử

Chuẩn bị tốt giúp phiên kiểm thử tập trung vào sản phẩm thay vì mất thời gian giải quyết vấn đề truy cập hoặc dữ liệu.

### Môi trường và bản dựng

Xác nhận:

- Bản dựng đúng phiên bản và có ghi nhận mã phát hành.
- Môi trường ổn định, có thể truy cập từ nơi người tham gia làm việc.
- Các dịch vụ phụ thuộc cần thiết đã sẵn sàng.
- Cấu hình và feature flag phù hợp với phạm vi.
- Có cách khôi phục hoặc đặt lại trạng thái giữa các lần chạy.
- Log và cơ chế thu thập bằng chứng hoạt động.

### Tài khoản và quyền

Chuẩn bị tài khoản theo vai trò thực tế. Mỗi người chỉ nên có quyền cần thiết cho nhiệm vụ. Không chia sẻ tài khoản cá nhân hoặc thông tin xác thực nhạy cảm qua tài liệu chung.

Nếu có nhiều vai trò, chuẩn bị ma trận tài khoản và quyền. Kiểm tra trước việc đăng nhập, hết hạn phiên, đổi mật khẩu hoặc xác thực nhiều yếu tố nếu chúng thuộc phạm vi.

### Dữ liệu kiểm thử

Dữ liệu cần đủ đại diện cho kịch bản và có thể tái tạo. Có thể chuẩn bị:

- Dữ liệu bình thường cho hành trình chính.
- Dữ liệu biên hoặc trường hợp ngoại lệ.
- Dữ liệu ở nhiều trạng thái.
- Dữ liệu liên quan giữa nhiều bản ghi.
- Dữ liệu để kiểm tra quyền và phân tách người dùng.
- Dữ liệu sạch để chạy lại sau khi sửa lỗi.

Dữ liệu cần được bảo vệ phù hợp. Tránh dùng dữ liệu cá nhân hoặc giao dịch thật nếu không có cơ sở và biện pháp kiểm soát thích hợp.

### Kịch bản và hướng dẫn

Kịch bản nên mô tả mục tiêu, điều kiện đầu vào và kết quả mong đợi bằng ngôn ngữ nghiệp vụ. Không nên viết quá chi tiết đến mức buộc người dùng chỉ làm theo từng cú nhấp chuột nếu mục tiêu là đánh giá tính dễ sử dụng.

Ví dụ:

- Mục tiêu: hoàn tất một đơn hàng bằng phương thức thanh toán được hỗ trợ.
- Điều kiện: tài khoản khách hàng hợp lệ, sản phẩm còn hàng và địa chỉ giao hàng hợp lệ.
- Kết quả mong đợi: đơn được tạo, tổng tiền chính xác, giao dịch có trạng thái phù hợp và người dùng nhận được xác nhận.

Người điều phối có thể cung cấp hướng dẫn về cách báo vấn đề, nhưng không nên hướng người dùng đến câu trả lời mong muốn hoặc giải thích thay họ trong lúc đánh giá khả năng sử dụng.

## 7. Điều phối phiên kiểm thử hiệu quả

Người điều phối giữ cho phiên tập trung vào mục tiêu và bảo đảm mọi phản hồi được ghi nhận. Họ không nên áp đặt kết luận hoặc biến phiên UAT thành buổi trình diễn của nhóm phát triển.

Trước phiên:

- Nhắc lại mục tiêu và phạm vi.
- Xác nhận người tham gia, tài khoản, dữ liệu và môi trường.
- Nêu rõ thời lượng và cách yêu cầu hỗ trợ.
- Giải thích cách ghi nhận vấn đề và phân biệt câu hỏi với lỗi.
- Thống nhất cách xử lý nếu môi trường bị gián đoạn.

Trong phiên:

- Để người dùng thực hiện nhiệm vụ theo cách tự nhiên.
- Quan sát nơi họ do dự, hiểu nhầm hoặc cần trợ giúp.
- Ghi lại hành động, kết quả, thời điểm và bối cảnh.
- Hỏi câu hỏi mở để hiểu lý do đằng sau phản hồi.
- Không vội giải thích hoặc sửa thao tác thay người dùng.
- Ghi nhận cả vấn đề kỹ thuật, nghiệp vụ và trải nghiệm.
- Nếu phiên bị chặn, ghi rõ nguyên nhân và quyết định tiếp tục hay dừng.

Sau phiên:

- Xác nhận lại các phát hiện với người tham gia.
- Làm rõ mức độ ảnh hưởng và tần suất nếu có thể.
- Tóm tắt những gì đã hoàn thành và còn bỏ ngỏ.
- Gửi đường dẫn hoặc mã tham chiếu để người tham gia theo dõi.
- Thông báo bước tiếp theo và thời điểm dự kiến phản hồi.

### Cách đặt câu hỏi để thu thập phản hồi

Câu hỏi nên khuyến khích mô tả trải nghiệm, không dẫn dắt người dùng.

Câu hỏi hữu ích:

- Bạn mong đợi điều gì xảy ra ở bước này?
- Điều gì khiến bạn dừng lại hoặc không chắc nên làm gì?
- Kết quả hiển thị có phù hợp với công việc của bạn không?
- Nếu thao tác này thất bại, bạn cần biết điều gì để tiếp tục?
- Bạn thường xử lý tình huống này trong quy trình hiện tại như thế nào?
- Phần nào gây mất thời gian hoặc dễ nhầm lẫn nhất?

Tránh câu hỏi như “Bạn thấy chức năng này tốt chứ?” hoặc “Bạn có đồng ý đây chỉ là lỗi nhỏ không?” vì chúng có thể ảnh hưởng đến câu trả lời.

## 8. Thu thập và ghi nhận phản hồi có cấu trúc

Phản hồi có thể đến từ biểu mẫu, công cụ quản lý lỗi, ghi chú phiên, email nội bộ, cuộc họp hoặc trao đổi trực tiếp. Dù nguồn nào, nhóm cũng cần đưa thông tin vào một nơi có thể theo dõi và liên kết với bản dựng, kịch bản và người gửi.

Một bản ghi phản hồi nên có:

- Mã định danh.
- Người gửi hoặc nhóm đại diện.
- Ngày giờ và phiên kiểm thử.
- Bản dựng, môi trường và thiết bị.
- Kịch bản hoặc nhiệm vụ liên quan.
- Mô tả quan sát được.
- Kết quả mong đợi và thực tế.
- Các bước tái hiện nếu là lỗi.
- Mức độ ảnh hưởng và tần suất.
- Bằng chứng như ảnh chụp, log hoặc video đã được phép lưu.
- Loại phản hồi và trạng thái xử lý.
- Người phụ trách và thời hạn tiếp theo.

### Phân biệt các loại phản hồi

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Lỗi chức năng | Hành vi khác yêu cầu hoặc quy tắc đã thống nhất | Đơn hàng không lưu sau khi thanh toán |
| Vấn đề dữ liệu | Dữ liệu sai, thiếu, trùng hoặc không nhất quán | Tổng tiền trong hóa đơn khác tổng tiền đơn |
| Vấn đề trải nghiệm | Người dùng khó hiểu, khó tìm hoặc khó hoàn thành nhiệm vụ | Nút xác nhận không rõ ý nghĩa |
| Yêu cầu cải tiến | Đề xuất thay đổi để tăng giá trị hoặc hiệu quả | Bổ sung bộ lọc thường dùng |
| Câu hỏi hoặc làm rõ | Người dùng chưa hiểu quy tắc hoặc cách sử dụng | Không rõ khi nào đơn được coi là hoàn tất |
| Vấn đề môi trường | Không thể thực hiện do cấu hình hoặc phụ thuộc | Không đăng nhập được vì dịch vụ thử nghiệm ngừng hoạt động |
| Rủi ro hoặc lo ngại | Hành vi có thể gây hậu quả nhưng cần xác minh thêm | Người dùng lo rằng dữ liệu của nhóm khác có thể bị xem |

Không nên phân loại mọi phản hồi là lỗi. Một đề xuất cải tiến có thể có giá trị nhưng không phải vi phạm tiêu chí chấp nhận hiện tại. Một câu hỏi có thể chỉ ra tài liệu chưa rõ hoặc thiết kế khó hiểu. Nhóm cần giữ nguyên ý kiến của người gửi trước khi diễn giải hoặc phân loại.

## 9. Phân loại và ưu tiên phản hồi

Sau khi tiếp nhận, nhóm cần triage để quyết định phản hồi nào cần sửa ngay, phản hồi nào cần điều tra, phản hồi nào là đề xuất và phản hồi nào cần làm rõ.

### Xác minh trước khi ưu tiên

Với một phản hồi, hãy hỏi:

- Có thể tái hiện không?
- Hành vi có khác yêu cầu hoặc tiêu chí chấp nhận không?
- Phạm vi ảnh hưởng là một người dùng, một vai trò hay nhiều người dùng?
- Có ảnh hưởng đến dữ liệu, tiền, quyền truy cập hoặc vận hành không?
- Vấn đề xuất hiện thường xuyên hay chỉ trong một điều kiện cụ thể?
- Có cách làm việc thay thế an toàn không?
- Đây là vấn đề mới hay đã được ghi nhận?
- Cần ai tham gia để xác nhận cách diễn giải?

Không nên bác bỏ phản hồi chỉ vì người gửi không cung cấp đầy đủ bước tái hiện. Có thể cần hỗ trợ họ bổ sung thông tin hoặc quan sát lại hành vi.

### Ưu tiên theo tác động và mức khẩn cấp

Có thể dùng các mức sau:

| Mức | Tiêu chí tham khảo | Hành động |
|---|---|---|
| Khẩn cấp | Chặn quy trình cốt lõi, gây mất dữ liệu, giao dịch sai hoặc lộ thông tin nghiêm trọng | Dừng hoặc hạn chế phát hành, điều tra ngay |
| Cao | Ảnh hưởng đáng kể đến nghiệp vụ hoặc nhiều người dùng, không có cách thay thế phù hợp | Ưu tiên sửa trước chấp nhận |
| Trung bình | Ảnh hưởng một phần, có cách thay thế hoặc phạm vi hạn chế | Lập kế hoạch xử lý và xác nhận rủi ro |
| Thấp | Tác động nhỏ, chủ yếu về trình bày hoặc cải tiến | Đưa vào backlog hoặc xem xét sau |

Mức ưu tiên cần dựa trên bối cảnh. Một lỗi giao diện có thể có mức ảnh hưởng cao nếu nó khiến người dùng không thể hoàn thành giao dịch. Một lỗi chỉ xuất hiện ở một vai trò ít dùng vẫn có thể nghiêm trọng nếu vai trò đó xử lý dữ liệu nhạy cảm.

### Phân biệt mức ưu tiên với thứ tự xử lý

Mức ưu tiên phản ánh tầm quan trọng của vấn đề. Thứ tự xử lý còn phụ thuộc vào quan hệ phụ thuộc, khả năng sửa, thời gian cần xác minh và lịch tham gia của người dùng. Một lỗi cao có thể cần điều tra trước; một lỗi khác có thể được sửa nhanh và kiểm tra ngay để giảm rủi ro.

Mọi quyết định hạ mức ưu tiên hoặc trì hoãn vấn đề ảnh hưởng đến tiêu chí chấp nhận cần được ghi lại cùng lý do và người chấp thuận.

## 10. Điều tra và chuyển phản hồi thành hành động

Một phản hồi đã được phân loại cần có bước tiếp theo rõ ràng. Không nên để vấn đề ở trạng thái “đã nhận” mà không có người phụ trách.

Quy trình xử lý có thể gồm:

1. **Tiếp nhận:** tạo bản ghi và xác nhận với người gửi.
2. **Làm rõ:** bổ sung bối cảnh, dữ liệu, bước tái hiện và mức ảnh hưởng.
3. **Phân loại:** xác định lỗi, vấn đề dữ liệu, trải nghiệm, yêu cầu cải tiến, câu hỏi hoặc môi trường.
4. **Ưu tiên:** đánh giá tác động, khẩn cấp và rủi ro còn lại.
5. **Giao xử lý:** chỉ định nhóm hoặc cá nhân chịu trách nhiệm.
6. **Điều tra:** xác định nguyên nhân và phạm vi ảnh hưởng.
7. **Quyết định:** sửa, thay đổi yêu cầu, chấp nhận có điều kiện, hoãn hoặc từ chối có giải thích.
8. **Kiểm tra lại:** xác minh bản sửa trong môi trường phù hợp.
9. **Hồi quy:** chạy các kiểm thử liên quan để tìm tác động dây chuyền.
10. **Phản hồi lại:** thông báo kết quả cho người gửi và cập nhật trạng thái.

Nếu phản hồi là yêu cầu thay đổi phạm vi, cần đưa qua quy trình quản lý thay đổi. Không nên tự động thêm vào bản phát hành chỉ vì một người tham gia đề xuất. Hãy đánh giá giá trị, chi phí, rủi ro và ảnh hưởng đến tiêu chí chấp nhận.

### Khi các bên có ý kiến khác nhau

Bất đồng có thể xuất hiện khi người dùng cho rằng hành vi không phù hợp, còn nhóm phát triển cho rằng hệ thống làm đúng đặc tả. Trong trường hợp đó:

- Ghi lại cả hành vi quan sát được và kỳ vọng của người dùng.
- Xác định nguồn yêu cầu hoặc quy tắc đã thống nhất.
- Làm rõ liệu vấn đề nằm ở sản phẩm, đặc tả hay cách truyền đạt.
- Mời chủ sản phẩm hoặc chuyên gia nghiệp vụ quyết định quy tắc.
- Ghi nhận quyết định và lý do.
- Cập nhật tiêu chí, tài liệu hoặc kiểm thử nếu cần.

Không nên kết luận rằng người dùng sai chỉ vì hành vi phù hợp với tài liệu hiện tại. Phản hồi có thể cho thấy tài liệu hoặc yêu cầu đã không phản ánh đúng công việc thực tế.

## 11. Kiểm tra lại bản sửa và xác nhận với người tham gia

Sau khi sửa, cần xác minh vấn đề đã được giải quyết trong điều kiện có thể tái hiện. Với vấn đề ảnh hưởng đến người dùng hoặc quy tắc nghiệp vụ, nên mời người gửi hoặc người đại diện phù hợp xác nhận lại khi cần.

Việc kiểm tra lại gồm:

- Xác nhận phiên bản chứa bản sửa.
- Dùng lại dữ liệu và điều kiện liên quan.
- Thực hiện lại các bước gây ra vấn đề.
- Kiểm tra kết quả mong đợi.
- Chạy hồi quy ở các luồng hoặc thành phần có liên quan.
- Ghi lại bằng chứng và người xác nhận.
- Cập nhật trạng thái phản hồi.

Cần phân biệt “đã sửa mã” với “đã xác minh bản sửa”. Một công việc phát triển hoàn tất chưa chứng minh người dùng không còn gặp vấn đề.

Nếu người gửi không thể tham gia kiểm tra lại, có thể dùng người đại diện cùng vai trò hoặc bằng chứng kiểm thử phù hợp. Báo cáo cần ghi rõ ai xác nhận và điều kiện xác nhận. Với vấn đề có tác động cao, không nên tự đánh dấu được chấp nhận chỉ vì người gửi chưa phản hồi.

### Xử lý khi bản sửa chưa đạt

Nếu lỗi vẫn tái hiện:

- Mở lại vấn đề hoặc tạo vấn đề liên quan.
- Ghi lại khác biệt giữa kết quả thực tế và mong đợi.
- Cập nhật mức ưu tiên nếu tác động thay đổi.
- Yêu cầu điều tra bổ sung.
- Điều chỉnh lịch kiểm thử và quyết định chấp nhận nếu cần.

Nếu bản sửa giải quyết lỗi nhưng làm thay đổi quy tắc nghiệp vụ, cần xác nhận lại yêu cầu với người có thẩm quyền. Không nên coi mọi thay đổi sau phản hồi là một bản sửa kỹ thuật đơn thuần.

## 12. Quản lý phản hồi ngoài phạm vi và rủi ro còn lại

Không phải mọi đề xuất đều có thể xử lý trong bản phát hành hiện tại. Một số phản hồi có thể được chuyển sang backlog, một số cần thay đổi phạm vi và một số có thể được chấp nhận có điều kiện.

Khi trì hoãn hoặc không thực hiện, cần ghi:

- Nội dung phản hồi và người gửi.
- Lý do chưa xử lý.
- Ảnh hưởng nếu giữ nguyên hành vi.
- Biện pháp thay thế hoặc giảm thiểu.
- Người có thẩm quyền quyết định.
- Thời điểm hoặc điều kiện xem xét lại.
- Kế hoạch thông báo cho người bị ảnh hưởng.

Không nên dùng trạng thái “đã đóng” cho một đề xuất chỉ vì nhóm không định thực hiện. Có thể dùng các trạng thái riêng như “đưa vào backlog”, “không thuộc phạm vi”, “đã chấp nhận rủi ro” hoặc “không thực hiện có lý do”.

Với lỗi nghiêm trọng hoặc vấn đề liên quan đến bảo mật, dữ liệu và giao dịch, cần đánh giá ảnh hưởng đến quyết định phát hành. Một ngoại lệ phải có người chấp nhận và cơ sở rõ ràng.

## 13. Theo dõi trạng thái và truyền đạt tiến độ

Một quy trình phản hồi cần có trạng thái thống nhất để mọi người biết vấn đề đang ở đâu.

Ví dụ:

| Trạng thái | Ý nghĩa |
|---|---|
| Mới tiếp nhận | Đã ghi nhận nhưng chưa phân loại |
| Cần làm rõ | Thiếu thông tin để xác minh hoặc ưu tiên |
| Đang triage | Đang đánh giá loại và mức độ ảnh hưởng |
| Đã giao xử lý | Có người hoặc nhóm chịu trách nhiệm |
| Đang điều tra | Đang tìm nguyên nhân hoặc phạm vi |
| Đang sửa | Đã xác định hướng xử lý |
| Chờ kiểm tra lại | Có bản sửa hoặc thay đổi cần xác minh |
| Đã xác minh | Bằng chứng cho thấy hành động đáp ứng kỳ vọng |
| Đã đóng | Có quyết định cuối cùng và thông tin đã được thông báo |
| Đã hoãn hoặc chấp nhận | Chưa xử lý trong phạm vi hiện tại, có lý do và quyết định |

Nhóm nên công bố cách xem trạng thái, thời gian phản hồi dự kiến và đầu mối liên hệ. Không nên hứa thời hạn sửa trước khi đánh giá mức độ và độ phức tạp; có thể cam kết thời điểm cập nhật tiếp theo nếu chưa thể đưa ra thời hạn hoàn tất.

### Nhịp cập nhật

Tùy quy mô, có thể dùng:

- Cập nhật nhanh hằng ngày trong giai đoạn UAT tập trung.
- Phiên triage định kỳ để xử lý vấn đề mới.
- Báo cáo giữa kỳ về số lượng, mức độ và vấn đề đang chặn.
- Tổng kết cuối phiên về những gì đã xác minh và còn bỏ ngỏ.
- Cập nhật sau phát hành về vấn đề đã được xử lý hoặc phát sinh mới.

Thông tin cần ngắn gọn, nhất quán và có đường dẫn đến bản ghi chi tiết. Người tham gia không nên phải hỏi nhiều lần mới biết phản hồi của họ đã được tiếp nhận hay chưa.

## 14. Tiêu chí hoàn tất tham gia và chấp nhận

Một đợt UAT không hoàn tất chỉ vì lịch đã kết thúc hoặc người dùng đã tham dự đủ số phiên. Cần xác định điều kiện kết thúc dựa trên bằng chứng và quyết định.

Các tiêu chí có thể gồm:

- Những nhóm người dùng hoặc vai trò bắt buộc đã tham gia hoặc có đại diện được chấp nhận.
- Các luồng và tiêu chí chấp nhận ưu tiên đã được kiểm tra.
- Kết quả, phản hồi và vấn đề được ghi nhận có thể truy vết.
- Các vấn đề nghiêm trọng đã được giải quyết hoặc có quyết định chấp nhận rủi ro hợp lệ.
- Các bản sửa quan trọng đã được kiểm tra lại.
- Rủi ro còn lại, phần ngoài phạm vi và giới hạn môi trường đã được thông báo.
- Người có thẩm quyền đã xem xét bằng chứng và đưa ra quyết định.
- Các bên liên quan biết kết quả và bước tiếp theo.

### Không dùng số lượng phản hồi làm tiêu chí duy nhất

Ít phản hồi không đồng nghĩa sản phẩm tốt. Người dùng có thể không có đủ thời gian, không hiểu cách gửi vấn đề hoặc không đại diện đúng nhóm. Nhiều phản hồi cũng không nhất thiết có nghĩa sản phẩm kém; phiên khám phá có thể làm lộ các điểm cải tiến mà trước đó chưa được hỏi đến.

Hãy xem xét chất lượng phản hồi, mức bao phủ nhiệm vụ, mức độ tham gia của các vai trò và bằng chứng cho từng tiêu chí.

## 15. Ví dụ: lập lịch và xử lý phản hồi cho hệ thống đặt lịch dịch vụ

Giả sử một sản phẩm cho phép khách hàng đặt lịch, nhân viên quản lý lịch và quản trị viên cấu hình dịch vụ. Nhóm chuẩn bị UAT trước khi triển khai.

### Xác định người tham gia

| Người tham gia | Vai trò | Nhiệm vụ |
|---|---|---|
| Chủ sản phẩm | Quyết định nghiệp vụ | Xác nhận chính sách đặt, đổi và hủy lịch |
| Khách hàng đại diện | Người dùng cuối | Tìm dịch vụ, chọn giờ và thay đổi lịch |
| Nhân viên phục vụ | Người dùng nghiệp vụ | Xem lịch, xác nhận và cập nhật trạng thái |
| Quản trị viên | Quản lý cấu hình | Tạo dịch vụ, thời lượng và khung giờ |
| Nhóm vận hành | Vận hành hệ thống | Kiểm tra giám sát, cảnh báo và quy trình xử lý sự cố |
| Nhóm phát triển và kiểm thử | Hỗ trợ kỹ thuật | Chuẩn bị môi trường, điều tra và kiểm tra lại |

### Lập lịch tham gia

- Buổi đầu: chủ sản phẩm và chuyên gia nghiệp vụ xác nhận chính sách.
- Buổi thứ hai: nhóm kỹ thuật chuẩn bị môi trường, tài khoản và dữ liệu.
- Hai buổi tiếp theo: khách hàng và nhân viên thực hiện các nhiệm vụ riêng.
- Một buổi triage: nhóm cùng phân loại phản hồi và thống nhất ưu tiên.
- Thời gian sửa và kiểm tra lại: dành cho các vấn đề quan trọng.
- Buổi cuối: chủ sản phẩm, vận hành và người phê duyệt xem xét kết quả.

### Ví dụ phản hồi và cách xử lý

| Phản hồi | Phân loại | Hành động |
|---|---|---|
| Hai khách hàng có thể chọn cùng một khung giờ | Lỗi chức năng hoặc toàn vẹn dữ liệu | Ưu tiên cao, kiểm tra đồng thời và cơ chế giữ chỗ |
| Nhân viên không thấy lịch vừa được khách hàng đổi | Vấn đề đồng bộ hoặc thông báo | Điều tra sự kiện và cập nhật trạng thái |
| Khách hàng không hiểu múi giờ hiển thị | Vấn đề trải nghiệm | Làm rõ quy tắc, sửa nội dung và kiểm tra lại với người dùng |
| Quản trị viên muốn thêm bộ lọc theo địa điểm | Yêu cầu cải tiến | Đánh giá giá trị và đưa vào kế hoạch sản phẩm |
| Môi trường UAT không gửi được tin nhắn | Vấn đề môi trường | Ghi nhận giới hạn, khôi phục phụ thuộc hoặc dùng phương án thử nghiệm đã thống nhất |

Sau khi sửa lỗi đặt trùng lịch, nhóm kiểm thử lại tình huống hai khách hàng chọn cùng một khung giờ. Người dùng đại diện có thể xác nhận rằng thông báo và hành vi mới dễ hiểu. Chủ sản phẩm xác nhận quy tắc nghiệp vụ; nhóm kỹ thuật cung cấp bằng chứng về tính nhất quán dữ liệu. Chỉ khi các bằng chứng cần thiết đã có, nhóm mới cập nhật trạng thái và đưa vấn đề vào quyết định chấp nhận.

## 16. Mẫu kế hoạch tham gia và lịch UAT

Có thể dùng mẫu sau để chuẩn bị một đợt tham gia:

~~~text
MỤC TIÊU UAT:
Bản dựng / phiên bản:
Môi trường:
Thời gian bắt đầu và kết thúc:

BÊN LIÊN QUAN:
- Nhóm người dùng đại diện:
- Chủ sản phẩm:
- Chuyên gia nghiệp vụ:
- Phát triển / kiểm thử:
- Vận hành / bảo mật / tuân thủ:
- Người phê duyệt:
- Người thay thế:

PHẠM VI:
- Luồng nghiệp vụ:
- Tiêu chí chấp nhận:
- Ngoài phạm vi:
- Rủi ro cần chú ý:

CHUẨN BỊ:
- Tài khoản và quyền:
- Dữ liệu:
- Hướng dẫn:
- Công cụ ghi nhận:
- Người hỗ trợ:
- Điều kiện sẵn sàng:

LỊCH:
- Phiên định hướng:
- Phiên thực hiện:
- Phiên triage:
- Thời gian sửa:
- Phiên kiểm tra lại:
- Phiên quyết định:

KẾT QUẢ:
- Nhiệm vụ đã hoàn thành:
- Phản hồi đã ghi nhận:
- Vấn đề còn mở:
- Rủi ro còn lại:
- Quyết định và người phê duyệt:
~~~

## 17. Mẫu ghi nhận và theo dõi phản hồi

~~~text
MÃ PHẢN HỒI:
NGƯỜI GỬI / NHÓM:
NGÀY GIỜ:
PHIÊN UAT:
BẢN DỰNG / MÔI TRƯỜNG:

LOẠI:
Lỗi chức năng / Dữ liệu / Trải nghiệm / Cải tiến /
Câu hỏi / Môi trường / Rủi ro

MÔ TẢ:
NHIỆM VỤ LIÊN QUAN:
CÁC BƯỚC TÁI HIỆN:
KẾT QUẢ MONG ĐỢI:
KẾT QUẢ THỰC TẾ:
TẦN SUẤT / PHẠM VI ẢNH HƯỞNG:
BẰNG CHỨNG:

MỨC ƯU TIÊN:
NGƯỜI / NHÓM PHỤ TRÁCH:
HÀNH ĐỘNG:
THỜI HẠN CẬP NHẬT:
KẾT QUẢ KIỂM TRA LẠI:
NGƯỜI XÁC NHẬN:
TRẠNG THÁI CUỐI:
THÔNG TIN ĐÃ GỬI LẠI CHO NGƯỜI PHẢN HỒI:
~~~

Mẫu cần được điều chỉnh cho công cụ quản lý hiện có. Không nên bắt người dùng điền quá nhiều trường kỹ thuật; điều phối viên có thể bổ sung phiên bản, log và thông tin môi trường sau khi tiếp nhận.

## 18. Những sai lầm thường gặp

- **Mời người dùng quá muộn:** không còn thời gian để xử lý phản hồi quan trọng.
- **Chỉ mời người quen thuộc với nhóm phát triển:** góc nhìn người dùng mới hoặc nhóm ít được đại diện bị bỏ sót.
- **Không xác định mục tiêu từng phiên:** người tham gia không biết cần đánh giá điều gì.
- **Lịch không có thời gian dự phòng:** một lỗi lớn có thể làm toàn bộ mốc nghiệm thu bị trễ.
- **Môi trường và dữ liệu chưa sẵn sàng:** thời gian tham gia bị lãng phí vào vấn đề chuẩn bị.
- **Điều phối dẫn dắt người dùng:** phản hồi bị ảnh hưởng bởi cách nhóm giải thích sản phẩm.
- **Gộp mọi phản hồi thành lỗi:** đề xuất cải tiến, câu hỏi và vấn đề môi trường bị xử lý sai.
- **Không có người sở hữu phản hồi:** vấn đề bị ghi nhận nhưng không được điều tra hoặc cập nhật.
- **Chỉ sửa mà không kiểm tra lại:** chưa có bằng chứng rằng vấn đề đã được giải quyết.
- **Không thông báo kết quả cho người gửi:** người tham gia mất niềm tin và có thể không phản hồi trong lần sau.
- **Đóng UAT theo lịch thay vì theo bằng chứng:** các tiêu chí quan trọng có thể vẫn chưa được xác nhận.
- **Coi im lặng là đồng ý:** không có phản hồi không đồng nghĩa người dùng đã chấp nhận.

## Kết luận

Lập lịch tham gia và xử lý phản hồi là phần thiết yếu của kiểm thử chấp nhận. Nhóm cần xác định đúng người đại diện, mục tiêu của từng phiên, điều kiện chuẩn bị, thời gian thực hiện, thời gian phân loại và kiểm tra lại. Lịch cần phản ánh công việc thực tế của người tham gia và có dự phòng cho vấn đề phát sinh.

Mỗi phản hồi cần được ghi nhận, xác minh, phân loại, ưu tiên, giao người xử lý và theo dõi đến khi có kết quả hoặc quyết định rõ ràng. Khi người tham gia nhận được thông tin về cách phản hồi của họ được xử lý, nhóm có thể duy trì sự tin cậy và sử dụng bằng chứng UAT để đưa ra quyết định chấp nhận sản phẩm có cơ sở.
