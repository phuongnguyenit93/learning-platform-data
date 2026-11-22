# Phân biệt rủi ro chất lượng sản phẩm với rủi ro thực hiện dự án

Trong chiến lược kiểm thử xác thực (validation testing strategy), phân tích rủi ro giúp nhóm quyết định điều gì cần được chú ý trước, bằng chứng nào cần thu thập và điều kiện nào có thể ảnh hưởng đến kết quả. Hai nhóm rủi ro thường cần được xem xét song song là **rủi ro chất lượng sản phẩm** và **rủi ro thực hiện dự án**. Chúng có liên hệ với nhau nhưng mô tả hai đối tượng khác nhau.

- **Rủi ro chất lượng sản phẩm (product risk):** Khả năng sản phẩm có hành vi sai, thiếu, không an toàn hoặc không đáp ứng một thuộc tính chất lượng trong điều kiện sử dụng dự kiến. Hậu quả thường tác động đến người dùng, dữ liệu, hoạt động kinh doanh, tuân thủ hoặc uy tín.
- **Rủi ro thực hiện dự án (project risk):** Khả năng một sự kiện hoặc điều kiện làm ảnh hưởng đến việc lập kế hoạch, phát triển, kiểm thử hoặc phát hành dự án. Hậu quả thường tác động đến tiến độ, chi phí, phạm vi, nguồn lực, khả năng phối hợp hoặc việc đạt mục tiêu dự án.

Ví dụ, việc hệ thống có thể tính sai số tiền thanh toán là rủi ro chất lượng sản phẩm. Việc môi trường kiểm thử của cổng thanh toán chưa sẵn sàng đúng lịch là rủi ro thực hiện dự án. Rủi ro thứ hai có thể khiến nhóm không kiểm tra được rủi ro thứ nhất trước ngày phát hành. Vì vậy, phân loại đúng giúp chọn biện pháp xử lý phù hợp và tránh bỏ sót mối liên hệ giữa chất lượng sản phẩm với khả năng hoàn thành dự án.

## 1. Hiểu đúng khái niệm rủi ro

Rủi ro là một sự kiện hoặc điều kiện **chưa chắc chắn** mà nếu xảy ra sẽ ảnh hưởng đến mục tiêu. Khi mô tả một rủi ro, nên nêu rõ nguyên nhân, sự kiện có thể xảy ra và hậu quả. Mẫu diễn đạt hữu ích là:

> Do [nguyên nhân], có thể xảy ra [sự kiện], dẫn đến [hậu quả đối với mục tiêu].

Ví dụ:

- Do quy tắc làm tròn thuế chưa được thống nhất, hệ thống có thể tính tổng tiền khác với số tiền của cổng thanh toán, dẫn đến khách hàng bị thu sai hoặc giao dịch bị từ chối.
- Do nhà cung cấp chỉ cấp môi trường sandbox vào cuối giai đoạn kiểm thử, nhóm có thể không đủ thời gian kiểm tra tích hợp, dẫn đến chậm quyết định phát hành hoặc chấp nhận rủi ro chưa được xác minh.

Phân biệt rủi ro với vấn đề đã xảy ra:

- **Rủi ro:** Một khả năng chưa xảy ra, cần đánh giá và chuẩn bị ứng phó. Ví dụ: nhà cung cấp có thể bàn giao API muộn.
- **Vấn đề (issue):** Một sự việc đã xảy ra và cần được xử lý. Ví dụ: nhà cung cấp đã trễ bàn giao API ba ngày.
- **Lỗi (defect):** Sai lệch có thể quan sát được giữa hành vi thực tế và hành vi mong đợi của sản phẩm. Ví dụ: hệ thống cộng phí vận chuyển hai lần.

Một rủi ro có thể trở thành vấn đề; một vấn đề có thể làm phát sinh hoặc làm tăng rủi ro khác. Khi sự kiện đã xảy ra, nhóm cần quản lý nó như vấn đề hiện tại, đồng thời đánh giá những rủi ro tiếp theo do sự kiện đó tạo ra.

## 2. Rủi ro chất lượng sản phẩm

Rủi ro chất lượng sản phẩm tập trung vào điều có thể sai trong chính sản phẩm khi người dùng hoặc hệ thống khác sử dụng nó. Phân tích nhóm rủi ro này cần bắt đầu từ yêu cầu, hành trình người dùng, kiến trúc, dữ liệu, giao diện tích hợp và các thuộc tính chất lượng quan trọng.

Các nhóm thường gặp gồm:

| Nhóm rủi ro | Câu hỏi cần đặt ra | Ví dụ |
|---|---|---|
| Chức năng | Sản phẩm có thể thực hiện sai hoặc bỏ sót quy tắc nghiệp vụ nào? | Mã giảm giá được áp dụng hai lần hoặc không áp dụng khi đủ điều kiện |
| Tính chính xác và toàn vẹn dữ liệu | Dữ liệu có thể bị sai, mất, trùng hoặc không nhất quán ở đâu? | Thanh toán thành công nhưng đơn hàng vẫn ở trạng thái chờ thanh toán |
| Hiệu năng và khả năng mở rộng | Hệ thống có thể chậm hoặc quá tải trong điều kiện nào? | Thời gian phản hồi tăng mạnh khi có nhiều người mua cùng lúc |
| Độ tin cậy và khả năng phục hồi | Hệ thống có thể dừng hoặc phục hồi sai khi xảy ra sự cố nào? | Gửi lại yêu cầu sau khi mất kết nối tạo giao dịch thứ hai |
| Bảo mật và quyền riêng tư | Dữ liệu hoặc thao tác nào có thể bị truy cập trái phép? | Người dùng thay mã đơn hàng trong URL để xem đơn của người khác |
| Khả năng sử dụng và truy cập | Người dùng có thể không hoàn thành tác vụ hoặc không hiểu trạng thái nào? | Biểu mẫu báo lỗi không chỉ ra trường cần sửa; thao tác không dùng được bằng bàn phím |
| Tương thích | Hành vi có thể khác nhau trên nền tảng được hỗ trợ nào? | Nút xác nhận bị che trên một kích thước màn hình hoặc trình duyệt cụ thể |
| Khả năng bảo trì và thay đổi | Một thay đổi có thể gây ảnh hưởng ngoài dự kiến đến phần nào? | Thay đổi mô hình đơn hàng làm hỏng các tích hợp cũ |

Hậu quả của rủi ro chất lượng không chỉ là có thêm lỗi cần sửa. Nó có thể khiến người dùng không hoàn thành công việc, gây thất thoát tiền, mất hoặc lộ dữ liệu, làm gián đoạn dịch vụ, vi phạm cam kết hoặc làm giảm niềm tin vào sản phẩm.

Khi đánh giá, hãy xem xét cả xác suất và tác động. Một lỗi ít có khả năng xảy ra nhưng có thể làm lộ dữ liệu cá nhân hoặc gây thu tiền sai trên diện rộng vẫn có thể cần ưu tiên cao. Ngược lại, một lỗi giao diện dễ nhận thấy nhưng chỉ ảnh hưởng đến một trường hợp hiếm và có cách khắc phục tạm thời có thể được xếp mức thấp hơn, tùy bối cảnh.

## 3. Rủi ro thực hiện dự án

Rủi ro thực hiện dự án tập trung vào những điều có thể cản trở nhóm xây dựng, kiểm thử và đưa sản phẩm đến trạng thái được chấp nhận. Chúng có thể xuất hiện trong suốt vòng đời, từ xác định yêu cầu đến triển khai và bàn giao.

Các nhóm thường gặp gồm:

| Nhóm rủi ro | Câu hỏi cần đặt ra | Ví dụ |
|---|---|---|
| Tiến độ và lịch trình | Công việc hoặc phụ thuộc nào có thể hoàn thành muộn? | API của đối tác bàn giao trễ làm lùi kiểm thử tích hợp |
| Phạm vi và yêu cầu | Thay đổi hoặc thiếu rõ ràng nào có thể làm phát sinh công việc? | Quy tắc hoàn tiền chưa được thống nhất khi nhóm đã bắt đầu viết ca kiểm thử |
| Nguồn lực và kỹ năng | Nhóm có thể thiếu người, thời gian hoặc chuyên môn nào? | Không có chuyên gia bảo mật trong giai đoạn đánh giá xác thực và phân quyền |
| Môi trường và dữ liệu kiểm thử | Điều kiện kiểm thử nào có thể không sẵn sàng hoặc không ổn định? | Staging thường xuyên bị đặt lại dữ liệu, làm gián đoạn kiểm thử hồi quy |
| Công cụ và quy trình | Công cụ hoặc quy trình nào có thể không hỗ trợ công việc? | Pipeline tự động không lưu kết quả, khiến nhóm không truy vết được lần chạy lỗi |
| Phối hợp và giao tiếp | Nhóm hoặc nhà cung cấp nào có thể không thống nhất hoặc phản hồi kịp thời? | Nhóm nghiệp vụ và nhóm phát triển hiểu khác nhau về trạng thái hủy đơn |
| Ước lượng và ngân sách | Khối lượng hoặc chi phí nào có thể vượt dự kiến? | Số lượng nền tảng cần kiểm tra lớn hơn khả năng của lịch phát hành |
| Phát hành và vận hành | Điều kiện triển khai hoặc hỗ trợ sau phát hành nào có thể thiếu? | Chưa có người trực theo dõi hoặc phương án quay lui khi triển khai |

Hậu quả của rủi ro dự án thường thể hiện qua trễ mốc, tăng chi phí, giảm phạm vi, thiếu bằng chứng kiểm thử, quá tải nhân sự hoặc phải thay đổi kế hoạch. Những hậu quả này có thể gián tiếp ảnh hưởng đến chất lượng sản phẩm. Chẳng hạn, lịch bị rút ngắn có thể khiến nhóm bỏ qua kiểm thử hồi quy hoặc không kiểm tra đủ nền tảng.

Không nên coi mọi sự chậm trễ là rủi ro chất lượng sản phẩm. Việc một kỹ sư nghỉ phép là rủi ro nguồn lực của dự án; việc sản phẩm có thể mất dữ liệu khi máy chủ khởi động lại là rủi ro chất lượng. Nếu sự thiếu hụt kỹ sư khiến chức năng phục hồi dữ liệu không được kiểm thử, hai rủi ro có quan hệ nhân quả nhưng vẫn cần được ghi nhận riêng để xử lý đúng.

## 4. So sánh hai nhóm rủi ro

| Tiêu chí | Rủi ro chất lượng sản phẩm | Rủi ro thực hiện dự án |
|---|---|---|
| Đối tượng chịu rủi ro | Sản phẩm và hành vi khi sử dụng | Kế hoạch và hoạt động thực hiện dự án |
| Câu hỏi trọng tâm | Điều gì có thể sai khi sản phẩm được sử dụng? | Điều gì có thể cản trở việc hoàn thành dự án? |
| Hậu quả điển hình | Lỗi nghiệp vụ, mất dữ liệu, sự cố bảo mật, hiệu năng kém, trải nghiệm xấu | Trễ tiến độ, vượt ngân sách, thiếu nguồn lực, giảm phạm vi, thiếu bằng chứng |
| Nguồn nhận diện | Yêu cầu, kiến trúc, luồng nghiệp vụ, dữ liệu, thuộc tính chất lượng, phản hồi người dùng | Kế hoạch, ước lượng, phụ thuộc, lịch nhân sự, môi trường, công cụ, phối hợp |
| Biện pháp chính | Thiết kế kiểm thử, kiểm thử chuyên sâu, sửa lỗi, kiểm soát chất lượng, giám sát sản phẩm | Điều chỉnh kế hoạch, bổ sung nguồn lực, quản lý phụ thuộc, giảm phạm vi có kiểm soát, phương án dự phòng |
| Người tham gia | QA, lập trình viên, chủ sản phẩm, chuyên gia bảo mật, vận hành và người dùng đại diện | Quản lý dự án, trưởng nhóm, QA, lập trình viên, chủ sản phẩm, nhà cung cấp và các nhóm phụ thuộc |
| Dấu hiệu theo dõi | Tỷ lệ lỗi, kết quả kiểm thử, chỉ số hiệu năng, sự cố, sai lệch dữ liệu | Mốc bị trễ, công việc tồn đọng, mức sẵn sàng môi trường, thiếu nhân lực, phụ thuộc chưa hoàn tất |

Một phép tự kiểm tra hữu ích là hỏi: **Nếu sự kiện xảy ra, điều gì bị ảnh hưởng trực tiếp?** Nếu sản phẩm có thể không đáp ứng nhu cầu hoặc thuộc tính chất lượng, đó là rủi ro chất lượng. Nếu khả năng thực hiện hoặc hoàn thành dự án bị ảnh hưởng, đó là rủi ro dự án. Nếu cả hai mục tiêu bị ảnh hưởng, hãy ghi nhận hai rủi ro có liên hệ và mô tả mối liên hệ giữa chúng.

## 5. Rủi ro có thể liên quan đến cả sản phẩm và dự án

Trong thực tế, một nguyên nhân có thể tạo ra nhiều rủi ro. Không nên cố ép một sự kiện phức tạp vào một nhãn duy nhất nếu nó ảnh hưởng đến cả chất lượng lẫn khả năng thực hiện.

Ví dụ với môi trường kiểm thử không ổn định:

1. **Rủi ro dự án:** Môi trường staging thường xuyên gián đoạn, khiến nhóm không hoàn thành lịch kiểm thử tích hợp.
2. **Rủi ro chất lượng:** Do thiếu thời gian và lần chạy đáng tin cậy, lỗi đồng bộ trạng thái giữa các dịch vụ có thể không được phát hiện trước phát hành.
3. **Mối liên hệ:** Rủi ro môi trường làm giảm khả năng thu thập bằng chứng về rủi ro chất lượng tích hợp.
4. **Ứng phó:** Nhóm vận hành cần cải thiện độ ổn định hoặc chuẩn bị môi trường thay thế; nhóm QA cần lập kế hoạch kiểm thử lại và ghi rõ phần chưa được xác minh.

Một số cặp ví dụ khác:

| Tình huống gốc | Rủi ro dự án | Rủi ro chất lượng liên quan |
|---|---|---|
| Yêu cầu thay đổi sát ngày phát hành | Lịch thiết kế và kiểm thử bị nén, phải sắp xếp lại nguồn lực | Tính năng mới có thể chưa được kiểm tra đầy đủ hoặc gây hồi quy |
| Thiếu dữ liệu thử nghiệm đại diện | Công việc chuẩn bị dữ liệu kéo dài, phụ thuộc vào nhóm dữ liệu | Lỗi với dữ liệu biên hoặc dữ liệu thực tế có thể không được phát hiện |
| Chuyên gia bảo mật không sẵn sàng | Hoạt động đánh giá bảo mật có thể bị trì hoãn | Lỗ hổng phân quyền hoặc xử lý dữ liệu nhạy cảm có thể còn tồn tại |
| Nhà cung cấp thay đổi hợp đồng API | Phải cập nhật kế hoạch tích hợp và phân công sửa đổi | Sản phẩm có thể xử lý sai phản hồi, lỗi hoặc trạng thái từ đối tác |

Việc tách hai rủi ro giúp nhóm có thể giao đúng người phụ trách. Quản lý dự án hoặc người quản lý phụ thuộc có thể chịu trách nhiệm giải quyết lịch bàn giao; chủ sở hữu kỹ thuật và QA chịu trách nhiệm xác định cách kiểm tra hành vi tích hợp. Một người có thể giữ nhiều vai trò, nhưng hành động và kết quả mong đợi của từng rủi ro phải rõ ràng.

## 6. Nhận diện và ghi nhận rủi ro có cấu trúc

Rủi ro nên được nhận diện từ nhiều nguồn thay vì chỉ dựa vào kinh nghiệm của một cá nhân. Nhóm có thể tổ chức rà soát yêu cầu, phân tích kiến trúc, xem xét dữ liệu sự cố trước đây, trao đổi với người dùng, kiểm tra phụ thuộc và tổ chức phiên thảo luận với các bên liên quan.

Các câu hỏi gợi ý:

- Người dùng có thể hoàn thành sai hoặc không hoàn thành tác vụ nào?
- Dữ liệu nào quan trọng, có thể bị sai, mất, trùng hoặc truy cập trái phép?
- Thành phần hoặc tích hợp nào có độ phức tạp cao hay mới được thay đổi?
- Điều kiện tải, thiết bị, mạng hoặc quyền hạn nào có thể làm thay đổi hành vi?
- Công việc, quyết định hoặc dịch vụ bên ngoài nào có thể bị trễ?
- Nhóm có đủ kỹ năng, dữ liệu, công cụ, môi trường và thời gian để kiểm thử không?
- Nếu một kiểm thử bị chặn, nhóm còn cách nào thu thập bằng chứng thay thế không?

Mỗi mục ghi nhận nên mô tả được:

| Trường | Nội dung |
|---|---|
| Mã và tên rủi ro | Mã duy nhất và mô tả ngắn |
| Phân loại | Chất lượng sản phẩm, thực hiện dự án hoặc có liên hệ cả hai |
| Nguyên nhân | Điều kiện có thể làm rủi ro xuất hiện |
| Sự kiện | Điều chưa chắc chắn có thể xảy ra |
| Hậu quả | Mục tiêu, người dùng hoặc hoạt động bị ảnh hưởng |
| Khả năng xảy ra | Đánh giá xác suất theo thang đã thống nhất |
| Mức độ tác động | Đánh giá mức thiệt hại hoặc ảnh hưởng nếu xảy ra |
| Mức ưu tiên | Kết quả đánh giá tổng hợp và lý do xếp hạng |
| Biện pháp ứng phó | Hành động giảm khả năng, giảm tác động hoặc chuẩn bị phương án dự phòng |
| Người phụ trách | Người theo dõi và điều phối hành động |
| Dấu hiệu cảnh báo | Chỉ báo cho thấy khả năng xảy ra đang tăng hoặc sự kiện đã gần kề |
| Rủi ro còn lại | Mức rủi ro sau khi áp dụng biện pháp |

Không nên viết rủi ro dưới dạng một nhãn chung như “hiệu năng”, “nhân sự” hoặc “tích hợp”. Hãy mô tả sự kiện và hậu quả cụ thể để người đọc hiểu tại sao nó quan trọng và cần làm gì.

## 7. Đánh giá và ưu tiên rủi ro

Một cách đánh giá phổ biến là xem xét **khả năng xảy ra** và **mức độ tác động**. Nhóm có thể dùng thang định tính như thấp, trung bình, cao hoặc thang điểm số, miễn là định nghĩa mỗi mức rõ ràng và áp dụng nhất quán.

Ví dụ về thang đánh giá:

| Mức | Khả năng xảy ra | Tác động |
|---|---|---|
| 1 – Thấp | Hiếm gặp trong điều kiện đã biết | Ảnh hưởng nhỏ, có cách khắc phục đơn giản |
| 2 – Trung bình | Có thể xảy ra trong một số điều kiện | Ảnh hưởng đáng kể đến một nhóm người dùng hoặc một phần công việc |
| 3 – Cao | Có dấu hiệu rõ hoặc có khả năng lặp lại | Ảnh hưởng lớn đến người dùng, nghiệp vụ hoặc mục tiêu dự án |

Nhóm có thể nhân điểm khả năng với điểm tác động để hỗ trợ sắp xếp thứ tự. Ví dụ, điểm 3 × 3 = 9 có thể được ưu tiên cao hơn 1 × 2 = 2 trong cùng một hệ thống thang đo. Tuy nhiên, phép nhân chỉ là công cụ hỗ trợ thảo luận, không phải xác suất thống kê chính xác. Một rủi ro có hậu quả đặc biệt nghiêm trọng, chẳng hạn lộ dữ liệu nhạy cảm hoặc vi phạm pháp lý, có thể cần được ưu tiên dù điểm tổng không cao.

Khi đánh giá **rủi ro chất lượng**, tác động nên được nhìn từ góc độ người dùng và tổ chức: mức mất mát, số người bị ảnh hưởng, thời gian gián đoạn, khả năng khôi phục, yêu cầu tuân thủ và uy tín. Khi đánh giá **rủi ro dự án**, hãy xem xét tác động đến mốc bàn giao, chi phí, phạm vi, năng lực nhóm, chất lượng bằng chứng và khả năng phát hành.

Ngoài điểm số, hãy xem xét:

- **Mức độ không chắc chắn:** Nhóm có đủ dữ liệu để ước lượng hay chỉ đang phỏng đoán?
- **Khả năng phát hiện:** Nếu sự kiện bắt đầu xảy ra, nhóm có nhận biết sớm không?
- **Phạm vi lan truyền:** Rủi ro có thể ảnh hưởng đến một thành phần hay nhiều luồng và nhóm phụ thuộc?
- **Thời điểm:** Rủi ro có thể xuất hiện ở giai đoạn nào và còn bao nhiêu thời gian để ứng phó?
- **Khả năng chấp nhận:** Có thể chấp nhận rủi ro còn lại hay cần điều kiện phê duyệt đặc biệt?

Ưu tiên rủi ro cần được cập nhật khi có thông tin mới. Một rủi ro từng được xếp thấp có thể tăng mức nếu xuất hiện lỗi liên quan, thay đổi kiến trúc hoặc dấu hiệu từ môi trường sử dụng.

## 8. Chọn cách ứng phó theo loại rủi ro

Mục tiêu của ứng phó là đưa rủi ro về mức có thể quản lý và bảo đảm người có thẩm quyền hiểu phần rủi ro còn lại. Một số cách ứng phó thường dùng:

- **Tránh (avoid):** Thay đổi kế hoạch hoặc thiết kế để loại bỏ nguyên nhân hay hoạt động tạo ra rủi ro.
- **Giảm thiểu (mitigate):** Giảm khả năng xảy ra hoặc giảm tác động bằng biện pháp phòng ngừa, kiểm soát hay kiểm thử bổ sung.
- **Chuyển giao/chia sẻ (transfer/share):** Phân bổ một phần trách nhiệm hoặc tác động cho bên có năng lực phù hợp thông qua hợp đồng, bảo hiểm hoặc thỏa thuận dịch vụ. Việc chuyển giao không xóa bỏ trách nhiệm quản lý rủi ro của tổ chức.
- **Chấp nhận (accept):** Ghi nhận rủi ro và quyết định không thực hiện thêm biện pháp, thường vì chi phí xử lý lớn hơn lợi ích hoặc mức rủi ro nằm trong giới hạn cho phép. Cần có người có thẩm quyền chấp thuận khi phù hợp.

Với rủi ro chất lượng sản phẩm, biện pháp có thể là bổ sung kiểm thử ở vùng rủi ro cao, sửa thiết kế, thêm kiểm soát dữ liệu, cải thiện phân quyền, chạy kiểm thử tải hoặc tăng khả năng giám sát. Với rủi ro dự án, biện pháp có thể là đặt mốc kiểm tra phụ thuộc sớm, chuẩn bị nhà cung cấp hoặc môi trường thay thế, điều chỉnh thứ tự công việc, bổ sung chuyên môn hoặc dự phòng thời gian.

Mỗi biện pháp cần có người phụ trách, thời hạn và dấu hiệu xác nhận hiệu quả. “Theo dõi thêm” không đủ nếu không nói rõ ai theo dõi, theo dõi chỉ báo nào và khi nào phải hành động.

## 9. Liên kết rủi ro với chiến lược kiểm thử

Rủi ro chất lượng sản phẩm là đầu vào trực tiếp để quyết định nội dung và mức độ kiểm thử. Rủi ro càng cao thường cần bằng chứng mạnh hơn, phạm vi bao phủ phù hợp hơn hoặc kiểm tra độc lập hơn. Ví dụ, rủi ro giao dịch trùng có thể cần kiểm thử tích hợp, kiểm thử hệ thống, mô phỏng mất kết nối và gửi lại yêu cầu, kiểm tra tính duy nhất của giao dịch và đối soát dữ liệu.

Rủi ro dự án định hình cách nhóm có thể thực hiện chiến lược. Nếu môi trường chỉ sẵn sàng trong một khoảng thời gian ngắn, nhóm cần lên lịch các kiểm thử tích hợp quan trọng, chuẩn bị dữ liệu trước và xác định phương án thu thập bằng chứng thay thế. Nếu thiếu chuyên gia bảo mật, nhóm cần xử lý phụ thuộc này sớm hoặc ghi rõ phần đánh giá chưa thể thực hiện và người có thẩm quyền xem xét.

Có thể dùng ma trận sau để nối rủi ro với hoạt động:

| Loại rủi ro | Hướng ưu tiên kiểm thử hoặc quản lý |
|---|---|
| Chất lượng: tính toán sai tiền | Kiểm thử quy tắc nghiệp vụ, giá trị biên, bảng quyết định và đối soát |
| Chất lượng: truy cập trái phép | Kiểm thử xác thực, phân quyền, kiểm tra quyền ở API và các vai trò khác nhau |
| Chất lượng: hiệu năng giảm khi tải cao | Kiểm thử tải, kiểm thử sức chịu đựng và theo dõi phân vị thời gian phản hồi |
| Dự án: môi trường không ổn định | Theo dõi mức sẵn sàng, chuẩn bị môi trường thay thế và bố trí lịch kiểm thử theo phụ thuộc |
| Dự án: yêu cầu thay đổi muộn | Quản lý thay đổi, phân tích tác động và cập nhật bộ kiểm thử hồi quy |
| Dự án: thiếu dữ liệu | Xác định dữ liệu cần thiết sớm, chỉ định người cung cấp và chuẩn bị dữ liệu tổng hợp an toàn |

Không nên dùng số lượng ca kiểm thử đã chạy làm thước đo duy nhất cho việc kiểm soát rủi ro. Điều quan trọng là các rủi ro ưu tiên có được kiểm tra bằng phương pháp phù hợp, bằng chứng có đáng tin cậy và rủi ro còn lại đã được xử lý hoặc chấp nhận rõ ràng hay chưa.

## 10. Ví dụ xuyên suốt: dự án xây dựng chức năng thanh toán

Giả sử nhóm chuẩn bị phát hành chức năng thanh toán cho một cửa hàng trực tuyến. Một số rủi ro có thể được ghi nhận như sau:

| Mã | Phân loại | Mô tả rủi ro | Hậu quả | Ứng phó chính |
|---|---|---|---|---|
| P-01 | Chất lượng sản phẩm | Khi người dùng gửi lại yêu cầu sau khi mất kết nối, hệ thống có thể tạo giao dịch trùng | Khách hàng bị thu tiền hai lần, phát sinh hoàn tiền và mất niềm tin | Kiểm thử idempotency, mô phỏng timeout và gửi lại, đối soát mã giao dịch |
| P-02 | Chất lượng sản phẩm | Quy tắc thuế và giảm giá có thể được áp dụng sai thứ tự | Tổng tiền trên đơn hàng khác với số tiền thanh toán | Bảng quyết định, kiểm thử giá trị biên và đối soát nhiều tổ hợp dữ liệu |
| P-03 | Chất lượng sản phẩm | API có thể cho phép tài khoản không sở hữu đơn hàng truy cập thông tin | Rò rỉ thông tin cá nhân và đơn hàng | Kiểm thử phân quyền theo vai trò và quyền sở hữu trên API |
| D-01 | Thực hiện dự án | Nhà cung cấp thanh toán có thể cấp sandbox muộn | Kiểm thử tích hợp bị dồn vào cuối lịch | Xác nhận mốc bàn giao, kiểm tra hợp đồng API sớm và chuẩn bị mô phỏng có kiểm soát |
| D-02 | Thực hiện dự án | Dữ liệu thử nghiệm có thể không bao phủ mã giảm giá, thuế và trạng thái lỗi | Nhóm mất thời gian bổ sung dữ liệu và giảm phạm vi kiểm thử | Chốt danh sách dữ liệu theo rủi ro, chỉ định người chuẩn bị và kiểm tra sẵn sàng trước khi chạy |
| D-03 | Thực hiện dự án | QA phụ trách tích hợp có thể không sẵn sàng trong tuần kiểm thử | Mốc kiểm thử quan trọng bị trễ hoặc thiếu người phân tích kết quả | Bố trí người dự phòng, chia sẻ tài liệu và xác định đầu mối hỗ trợ |

Nhóm cần xử lý cả hai loại rủi ro. Đối với P-01 đến P-03, QA và nhóm phát triển xác định kịch bản, dữ liệu, phương pháp và bằng chứng để đánh giá hành vi sản phẩm. Đối với D-01 đến D-03, người quản lý phụ thuộc và trưởng nhóm theo dõi mốc, chuẩn bị phương án thay thế và điều phối nguồn lực. Nếu D-01 xảy ra, nhóm phải đánh giá lại khả năng thu thập bằng chứng cho P-01 và P-02; không thể kết luận hai rủi ro chất lượng đã được kiểm soát chỉ vì các ca kiểm thử khác đều đạt.

Trước khi phát hành, báo cáo nên trình bày riêng kết quả kiểm thử sản phẩm, tình trạng các rủi ro dự án, phần chưa thể kiểm tra, biện pháp giảm thiểu và rủi ro còn lại. Người ra quyết định cần biết rõ điều gì đã được xác minh, điều gì chưa được xác minh và ai chấp nhận phần rủi ro còn tồn tại.

## 11. Theo dõi rủi ro trong suốt vòng đời

Danh sách rủi ro cần được xem xét định kỳ và khi có thay đổi đáng kể. Các sự kiện kích hoạt việc rà soát có thể gồm yêu cầu mới, thay đổi kiến trúc, lỗi nghiêm trọng, sự cố từ môi trường sử dụng, thay đổi nhà cung cấp, trễ mốc, thiếu nguồn lực hoặc kết quả kiểm thử bất thường.

Khi rà soát, nhóm nên:

1. Kiểm tra xem nguyên nhân, khả năng xảy ra và tác động có thay đổi không.
2. Cập nhật trạng thái: mới nhận diện, đang theo dõi, đang ứng phó, đã xảy ra, đã đóng hoặc được chấp nhận.
3. Xác nhận hành động giảm thiểu đã hoàn thành và có hiệu quả bằng bằng chứng nào.
4. Đánh giá rủi ro còn lại sau biện pháp và xác định người có thẩm quyền chấp nhận.
5. Liên kết rủi ro với yêu cầu, ca kiểm thử, lỗi, mốc dự án hoặc phụ thuộc liên quan.
6. Chia sẻ thay đổi với những người cần ra quyết định hoặc thực hiện hành động tiếp theo.

Không nên đóng một rủi ro chỉ vì đã chạy một ca kiểm thử. Cần xác định bằng chứng có bao phủ đúng tình huống, điều kiện và hậu quả đã mô tả hay không. Tương tự, không nên đóng rủi ro dự án chỉ vì mốc đã được cập nhật; cần kiểm tra phụ thuộc hoặc nguồn lực đã thực sự sẵn sàng.

## 12. Những nhầm lẫn thường gặp

- **Gọi mọi vấn đề là rủi ro:** Vấn đề đã xảy ra cần được xử lý ngay; rủi ro là điều chưa chắc chắn cần được dự báo và ứng phó.
- **Chỉ lập danh sách rủi ro sản phẩm:** Dự án có thể thất bại trong việc tạo bằng chứng nếu bỏ qua lịch, môi trường, dữ liệu và nguồn lực.
- **Chỉ lập danh sách rủi ro dự án:** Dự án có thể đúng tiến độ nhưng phát hành sản phẩm không đáp ứng nhu cầu hoặc có lỗi nghiêm trọng.
- **Dùng một biện pháp cho hai loại rủi ro:** Tăng số ca kiểm thử không giải quyết được việc thiếu môi trường; bổ sung nhân sự không tự khắc phục được lỗi thiết kế sản phẩm.
- **Đánh giá chỉ bằng điểm số:** Điểm ưu tiên cần đi cùng mô tả hậu quả, căn cứ đánh giá và yếu tố đặc biệt nghiêm trọng.
- **Không ghi người chịu trách nhiệm:** Rủi ro không có người theo dõi thường không dẫn đến hành động đúng thời điểm.
- **Bỏ qua rủi ro còn lại:** Biện pháp giảm thiểu có thể làm giảm nhưng không loại bỏ hoàn toàn rủi ro; phần còn lại cần được ghi nhận và quyết định rõ ràng.
- **Đồng nhất hoàn thành kiểm thử với an toàn phát hành:** Kết quả kiểm thử chỉ có ý nghĩa trong phạm vi và điều kiện đã thực hiện; quyết định phát hành phải cân nhắc cả giới hạn bằng chứng và rủi ro chưa xử lý.

Phân biệt rủi ro chất lượng sản phẩm với rủi ro thực hiện dự án giúp nhóm nhìn rõ hai câu hỏi: sản phẩm có thể gây ra vấn đề gì khi được sử dụng, và điều gì có thể ngăn nhóm xây dựng, kiểm thử hoặc phát hành sản phẩm đúng kế hoạch. Khi hai nhóm được nhận diện, đánh giá và liên kết với nhau, chiến lược kiểm thử có thể ưu tiên đúng nơi, quản lý phụ thuộc chủ động và cung cấp bằng chứng rõ ràng cho quyết định chất lượng.
