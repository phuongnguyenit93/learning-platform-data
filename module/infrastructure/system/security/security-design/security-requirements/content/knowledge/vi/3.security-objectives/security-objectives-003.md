# Availability

## Mục tiêu bài học

**Availability — tính sẵn sàng** là khả năng để chủ thể được phép truy cập thông tin hoặc sử dụng chức năng cần thiết vào thời điểm và trong thời hạn đã xác định. Một máy chủ đang chạy chưa chứng minh người dùng đăng nhập được, tạo giao dịch được hoặc nhận kết quả đúng lúc.

Trong chương Mục tiêu bảo mật, availability được xem từ hậu quả nghiệp vụ: điều gì xảy ra nếu người dùng hợp lệ không thực hiện được công việc? Từ câu trả lời đó, nhóm mới đặt mục tiêu đo được và chuyển thành yêu cầu cho xác thực, phân quyền, xử lý dữ liệu, giới hạn tài nguyên, logging và phục hồi.

Sau bài học, bạn có thể:

- Phân biệt tính sẵn sàng với thời gian tiến trình hoạt động, độ bền dữ liệu và khả năng phục hồi.
- Mô tả một mục tiêu availability có phạm vi, người dùng, thời hạn và điều kiện tải rõ ràng.
- Xây dựng chỉ số đo, mục tiêu dịch vụ và ngân sách lỗi mà không trộn lẫn các cách tính.
- Đặc tả hành vi khi quá tải, phụ thuộc lỗi hoặc hệ thống chuyển sang chế độ suy giảm.
- Liên kết yêu cầu với rủi ro, điểm thực thi kiến trúc, bằng chứng kiểm thử và trách nhiệm vận hành.

Các hệ thống, ngưỡng tải và mốc thời gian trong bài là giả định minh họa. Chúng cần được chủ nghiệp vụ và chủ dịch vụ xác nhận trước khi áp dụng trong dự án thực tế.

## 1. Sẵn sàng cho ai, để làm gì và trong bao lâu?

### 1.1. Bắt đầu từ một năng lực nghiệp vụ

Câu “hệ thống phải luôn sẵn sàng” chưa cho biết phải bảo vệ năng lực nào. Một mô tả tốt cần nêu:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Chủ thể hợp lệ | Ai cần dùng dịch vụ? | Nhân viên thuộc tenant được cấp quyền |
| Chức năng thiết yếu | Công việc nào phải thực hiện được? | Tạo và đọc yêu cầu bảo trì |
| Phạm vi dữ liệu | Tác động lên dữ liệu nào? | Yêu cầu trong tenant và phạm vi phân công |
| Thời hạn | Kết quả phải có trong bao lâu? | Nhận mã yêu cầu đã lưu bền vững trong 2 giây |
| Điều kiện hoạt động | Trong giới hạn tải và phụ thuộc nào? | Hồ sơ tải hợp lệ đã thống nhất |
| Cửa sổ đo | Đánh giá trên khoảng thời gian nào? | Tháng dương lịch theo UTC |
| Hậu quả không đạt | Công việc nào bị đình trệ? | Không tiếp nhận được yêu cầu cần xử lý đúng hạn |

**Tenant** là phạm vi dữ liệu và quyền của một khách hàng trong hệ thống dùng chung. Availability cần xét cả từng nhóm khách hàng quan trọng: một tỷ lệ chung tốt vẫn có thể che giấu việc một tenant bị chặn hoàn toàn.

### 1.2. Những điều dễ bị nhầm với availability

| Khái niệm | Điều nó phản ánh | Vì sao chưa đủ để kết luận dịch vụ sẵn sàng? |
|---|---|---|
| Tiến trình đang chạy | Chương trình chưa dừng | Có thể không kết nối được database hoặc không còn luồng xử lý |
| Endpoint kiểm tra sức khỏe trả thành công | Một điều kiện kiểm tra đã đạt | Có thể không đại diện cho chức năng người dùng cần |
| Độ bền dữ liệu | Khả năng giữ dữ liệu không bị mất | Dữ liệu còn tồn tại nhưng dịch vụ có thể không truy cập được |
| Khả năng phục hồi | Khả năng đưa dịch vụ về trạng thái hoạt động sau sự cố | Cần thời gian; trong lúc phục hồi người dùng vẫn có thể bị gián đoạn |
| Độ trễ thấp ở một số yêu cầu | Một phần giao dịch phản hồi nhanh | Các giao dịch khác có thể bị lỗi, bị treo hoặc không tới được hệ thống |

Một phản hồi HTTP thành công cũng chưa đủ. Nếu API trả mã yêu cầu nhưng dữ liệu chưa được lưu theo hợp đồng, hoặc đọc nhầm dữ liệu tenant khác, kết quả đó không đáp ứng chức năng hợp lệ cần bảo vệ.

## 2. Vì sao availability là mục tiêu bảo mật?

### 2.1. Không chỉ có tấn công từ chối dịch vụ

Tấn công từ chối dịch vụ làm người dùng hợp lệ không sử dụng được tài nguyên. Tuy nhiên, những đường gây mất sẵn sàng có thể xuất hiện trong cả thiết kế, triển khai và vận hành.

| Nguồn sự kiện | Kịch bản | Hậu quả nghiệp vụ |
|---|---|---|
| Lạm dụng từ bên ngoài | Gửi nhiều yêu cầu tốn tài nguyên hoặc nhiều lần đăng nhập | Tài nguyên bị chiếm, người dùng thật không được phục vụ |
| Người dùng có tài khoản | Một tenant tạo tác vụ xuất dữ liệu rất lớn | Các tenant khác chờ vì dùng chung worker, database hoặc hạn mức |
| Lỗi ứng dụng | Truy vấn không giới hạn, rò rỉ kết nối, vòng lặp retry | Cạn tài nguyên và kéo dài sự cố |
| Lỗi phụ thuộc | Dịch vụ email hoặc danh tính chậm, database không phản hồi | Luồng nghiệp vụ chờ dây chuyền hoặc không hoàn tất |
| Lỗi thay đổi | Phát hành cấu hình sai, quyền bị thu hồi nhầm | Người dùng hợp lệ bị chặn hoặc thành phần không khởi động |
| Lỗi hạ tầng | Mất máy, mất vùng chạy, hết dung lượng | Dịch vụ gián đoạn hoặc không lưu được dữ liệu |
| Hành vi đặc quyền | Xóa tài nguyên, xóa bản sao lưu hoặc khóa giải mã | Dịch vụ không thể hoạt động hay phục hồi trong thời gian cần thiết |

Mô hình đe dọa giúp tìm đường gây cạn tài nguyên, quyền có thể bị lạm dụng và các ranh giới tin cậy liên quan. Phân tích rủi ro giúp ưu tiên theo mức ảnh hưởng đối với nghiệp vụ, thay vì mặc định mọi thành phần đều cần cùng mức bảo vệ.

### 2.2. Viết rủi ro trước khi chọn công nghệ

Ví dụ:

> Do tác vụ xuất dữ liệu và tạo yêu cầu bảo trì cùng dùng một pool kết nối không có giới hạn riêng, một tenant có thể chiếm phần lớn kết nối, làm các tenant khác không tạo được yêu cầu đúng hạn.

Từ rủi ro này có thể đặt mục tiêu: giữ được năng lực tạo yêu cầu của các tenant còn lại khi một tenant tạo tải bất thường. Chỉ ghi “thêm autoscaling” chưa chứng minh đạt mục tiêu, vì điểm nghẽn có thể nằm ở database dùng chung hoặc quota của phụ thuộc.

## 3. Đặt mục tiêu trước, chọn biện pháp sau

### 3.1. Phân biệt mục tiêu, yêu cầu, giải pháp và bằng chứng

| Lớp | Ví dụ |
|---|---|
| Mục tiêu bảo mật | Người dùng hợp lệ vẫn tạo được yêu cầu khi chức năng gửi email bị lỗi |
| Yêu cầu cụ thể | Việc gửi email không được nằm trên đường đồng bộ quyết định hoàn tất tạo yêu cầu; sự kiện cần gửi phải được lưu bền vững |
| Giải pháp kiến trúc | Lưu yêu cầu và thông tin phát sự kiện theo cơ chế bảo đảm nhất quán, rồi worker gửi email |
| Bằng chứng chấp nhận | Khi chặn phụ thuộc email, yêu cầu vẫn được tạo đúng hợp đồng và thông báo được xử lý lại sau khi phụ thuộc phục hồi |

Một mục tiêu availability có thể được hỗ trợ bởi nhiều biện pháp: giới hạn tài nguyên, tách nhóm xử lý, dự phòng, timeout, retry có kiểm soát, suy giảm chức năng và phục hồi. Không có một công nghệ duy nhất tự đáp ứng toàn bộ mục tiêu.

### 3.2. Ưu tiên chức năng theo tác động

Giả sử cổng bảo trì có ba nhóm:

1. **Thiết yếu:** đăng nhập theo chính sách, tạo yêu cầu và đọc thông tin cần để xử lý.
2. **Có thể trì hoãn:** gửi email xác nhận và tạo báo cáo tổng hợp.
3. **Có thể tạm dừng khi sự cố:** xuất dữ liệu khối lượng lớn hoặc chức năng thống kê phụ.

Nhóm nghiệp vụ phải xác nhận thứ tự ưu tiên và thời gian trì hoãn chấp nhận được. Nhóm kỹ thuật không nên tự quyết định rằng một chức năng ít quan trọng chỉ vì nó khó giữ sẵn sàng.

Việc phân nhóm cũng không cho phép bỏ qua kiểm soát bảo mật. Nếu không thể xác minh quyền đọc, hệ thống không được tự mở dữ liệu cho mọi người để giữ tỷ lệ phản hồi thành công.

## 4. Đo availability bằng SLI, SLO và ngân sách lỗi

### 4.1. SLI, SLO và SLA khác nhau thế nào?

- **SLI — Service Level Indicator:** chỉ số quan sát chất lượng dịch vụ, như tỷ lệ thao tác hợp lệ hoàn tất đúng trong thời hạn.
- **SLO — Service Level Objective:** mục tiêu đặt cho SLI trong một cửa sổ và điều kiện cụ thể.
- **SLA — Service Level Agreement:** thỏa thuận mức dịch vụ giữa các bên, có thể sử dụng một số chỉ số và điều kiện riêng. Không nên mặc định con số nội bộ và con số trong thỏa thuận luôn có cùng phạm vi đo.

Ví dụ, SLI cho biết tháng này tỷ lệ yêu cầu đạt là 99,93%; SLO đặt mức tối thiểu 99,9%. Chưa có định nghĩa về tập yêu cầu, cách đo và cửa sổ thì hai con số này chưa đủ để đánh giá.

### 4.2. Cách tính theo yêu cầu

Một SLI có thể được định nghĩa như sau:

```text
SLI khả dụng gắn thời hạn
  = số yêu cầu đủ điều kiện hoàn tất đúng trong 2 giây
    / tổng số yêu cầu đủ điều kiện được quan sát
```

Trong ví dụ tạo yêu cầu bảo trì:

- Đối tượng đo là mỗi lần gọi API tạo yêu cầu tới điểm biên công khai; các lần gọi lại được tính theo cùng quy tắc.
- Đầu vào đủ điều kiện là yêu cầu đúng hợp đồng, do chủ thể có quyền gửi và nằm trong hồ sơ tải đã thống nhất.
- Một kết quả tốt cần trả mã yêu cầu đúng tenant và đã lưu bền vững trong thời hạn 2 giây.
- Lỗi máy chủ, timeout, phản hồi chậm hơn thời hạn hoặc trả thành công nhưng không giữ dữ liệu theo hợp đồng đều không phải kết quả tốt.
- Mọi khoảng bảo trì nằm trong cửa sổ đo vẫn được tính theo chính sách ví dụ.

Phải xác định tính đủ điều kiện độc lập với kết quả thành công. Không được loại một người dùng vốn có quyền ra khỏi phép đo chỉ vì phụ thuộc xác thực đang lỗi và hệ thống đã trả từ chối. Tương tự, trả mã giới hạn lưu lượng cho tải hợp lệ trong mức đã cam kết không tự biến sự từ chối đó thành thành công.

Các yêu cầu sai định dạng, truy cập không có quyền hoặc vượt hạn mức đã công bố có thể được xử lý theo nhóm riêng nếu chính sách đã định nghĩa trước. Không thay đổi cách phân loại sau sự cố để làm đẹp chỉ số.

### 4.3. Đặt cửa sổ và điều kiện tải

Giả sử SLO là:

> Trong mỗi tháng dương lịch theo UTC, ít nhất 99,9% lần gọi API tạo yêu cầu đủ điều kiện tại điểm biên phải hoàn tất đúng trong 2 giây, với hồ sơ tải hợp lệ tối đa 100 yêu cầu/giây cho luồng này và kích thước nội dung tối đa 64 KiB, không gồm tải tệp đính kèm.

Đây là mục tiêu minh họa. Hồ sơ tải thực tế còn cần phân bố tenant, thời gian kéo dài, dữ liệu nền, số kết nối, mẫu truy vấn và các luồng cạnh tranh tài nguyên. Một con số yêu cầu/giây đơn lẻ chưa mô tả đầy đủ chi phí xử lý.

Điều kiện tải dùng để giới hạn phạm vi cam kết và thiết kế kiểm chứng, không phải lý do bỏ qua tấn công. Cần có yêu cầu riêng về hành vi khi vượt tải và mức bảo vệ người dùng hợp lệ trong kịch bản lạm dụng đã chọn.

### 4.4. Ngân sách lỗi và hai cách tính không được trộn lẫn

**Ngân sách lỗi — error budget** là phần không đạt được phép theo SLO trong một cửa sổ. Với SLO 99,9% theo yêu cầu, ngân sách không đạt là 0,1% tổng số yêu cầu đủ điều kiện. Nếu có 1.000.000 yêu cầu như vậy, ngân sách tương ứng là 1.000 yêu cầu không đạt.

Nếu đo theo thời gian, công thức khác:

```text
Availability theo thời gian
  = thời gian dịch vụ đáp ứng tiêu chí sẵn sàng
    / tổng thời gian trong phạm vi đo
```

Với cửa sổ 30 ngày và mục tiêu 99,9% theo thời gian, phần không đạt tương ứng là 43,2 phút. Đây không phải phép đổi mặc định từ ngân sách 1.000 yêu cầu ở trên: lưu lượng thay đổi theo thời gian, và một sự cố có thể chỉ ảnh hưởng một phần người dùng.

Khi không có yêu cầu đủ điều kiện, SLI theo yêu cầu không có mẫu số để kết luận. Cần bổ sung kiểm tra chủ động hoặc chỉ số khác; không tự ghi 100% chỉ vì không quan sát được lỗi.

### 4.5. Quan sát từ góc nhìn người dùng

SLI tại điểm biên không nhìn thấy mọi lỗi trước khi yêu cầu tới đó, chẳng hạn lỗi phân giải tên hoặc thiết lập kết nối. Cần ghi rõ giới hạn này và bổ sung kiểm tra hành trình từ bên ngoài: truy cập tên dịch vụ, thiết lập kết nối, đăng nhập theo chính sách, tạo và đọc một yêu cầu thử nghiệm.

Kiểm tra chủ động phải dùng danh tính và dữ liệu thử riêng, không làm lộ dữ liệu thật hoặc tạo tác động nghiệp vụ ngoài ý muốn. Đồng thời theo dõi theo tenant hoặc nhóm khách hàng quan trọng để tránh tỷ lệ tổng hợp che giấu một nhóm bị mất dịch vụ.

## 5. Bảo vệ availability trong kiến trúc

### 5.1. Giới hạn công việc và tách tài nguyên

Những loại giới hạn có thể cần gồm kích thước đầu vào, số bản ghi mỗi trang, số tác vụ đang chờ, số tác vụ chạy đồng thời, thời gian truy vấn và mức sử dụng theo danh tính/tenant.

Mỗi giới hạn cần nêu đối tượng áp dụng, cách xử lý khi chạm ngưỡng và ảnh hưởng tới người dùng hợp lệ. Chỉ giới hạn theo địa chỉ mạng có thể không phân biệt được nhiều người dùng dùng chung một đường ra; chỉ giới hạn theo tài khoản cũng không xử lý được mọi nguồn tải. Phải chọn kết hợp phù hợp với kịch bản đe dọa.

Tách tài nguyên có thể thực hiện bằng nhóm worker, hàng đợi, pool kết nối hoặc miền hạ tầng riêng. Điều cần chứng minh là tải ở một nhóm không tiêu thụ hết năng lực dành cho luồng thiết yếu; tạo hai hàng đợi nhưng vẫn dùng một điểm nghẽn không giới hạn chưa chắc đạt mục tiêu.

### 5.2. Timeout và retry có ngân sách

Timeout ngăn chờ vô hạn, nhưng phải phù hợp với thời hạn của thao tác từ đầu tới cuối. Nếu thao tác phải kết thúc trong 2 giây, tổng thời gian chờ các phụ thuộc, các lần thử lại và xử lý nội bộ phải nằm trong ngân sách ấy.

Retry không giới hạn có thể nhân tải lên một phụ thuộc đang yếu. Yêu cầu cần nêu lỗi nào được thử lại, số lần tối đa, khoảng chờ, điều kiện dừng và giới hạn tổng. Khoảng chờ nên tránh làm mọi bên gọi lại đồng thời theo cùng một nhịp.

Với thao tác ghi, retry còn cần kiểm soát tác dụng phụ. Nếu lần gọi đầu đã lưu dữ liệu nhưng phản hồi bị mất, lần gọi lại không được tạo thêm một yêu cầu nghiệp vụ ngoài ý muốn. Một khóa chống lặp phải có phạm vi tenant/chủ thể, thời hạn và quy tắc khi cùng khóa nhưng nội dung khác; không chỉ thêm một trường tùy chọn rồi coi như đã giải quyết.

### 5.3. Hạn chế lỗi dây chuyền và suy giảm có chủ đích

Có thể ngừng gọi tạm thời một phụ thuộc liên tục lỗi để giảm tải và trả kết quả đã đặc tả. Cách này thường được gọi là cơ chế ngắt mạch. Nó cần điều kiện mở, thời gian kiểm tra lại và hành vi khi phục hồi, không phải một cờ “bỏ qua mọi lỗi”.

Ví dụ, mất email có thể trì hoãn thông báo trong khi vẫn tạo yêu cầu. Mất database cần cho lưu bền vững thì không được trả “đã tạo thành công” nếu chưa có cơ chế nhận bền vững khác được hợp đồng cho phép.

Nếu API dùng phản hồi “đã tiếp nhận” cho xử lý bất đồng bộ, cần phân biệt tiếp nhận bền vững với hoàn tất nghiệp vụ. Theo dõi cả tuổi tác vụ, tỷ lệ hoàn tất và khả năng báo lỗi cuối cùng; không dùng phản hồi tiếp nhận nhanh để che hàng đợi không xử lý được.

### 5.4. Dự phòng và miền lỗi

Nhiều bản chạy có thể giảm ảnh hưởng của lỗi đơn lẻ, nhưng chỉ khi các phụ thuộc và miền lỗi đã được phân tích. Những bản cùng dùng một database, một cấu hình sai hoặc một tài khoản có quyền xóa toàn bộ tài nguyên vẫn có thể cùng mất dịch vụ.

Không nên cộng hoặc nhân tỷ lệ sẵn sàng của các thành phần một cách tùy ý. Một mô hình xác suất chỉ có ý nghĩa khi nêu cấu trúc phụ thuộc, giả định độc lập và điều kiện chuyển đổi. Trong thực tế, lỗi chung và đường phục hồi cần được kiểm chứng bằng các kịch bản cụ thể.

### 5.5. Logging, cảnh báo và vận hành

Log cần giúp nhận biết lỗi theo chức năng, tenant, phụ thuộc và mã liên kết; tránh ghi bí mật hoặc nội dung nhạy cảm không cần thiết. Chính đường ghi log cũng cần giới hạn tài nguyên để không làm cạn đĩa hay khóa luồng phục vụ.

Phân biệt log chẩn đoán với audit bắt buộc của giao dịch nhạy cảm. Nếu giao dịch phải có dấu vết bền vững, cần thiết kế cơ chế đáp ứng cả hai điều kiện; không âm thầm bỏ audit khi kho log lỗi. Khi không thể giữ được điều kiện bắt buộc, phải từ chối thao tác tương ứng và tính ảnh hưởng vào availability theo chính sách đo.

Một cảnh báo chỉ hữu ích khi có nơi nhận, người phản hồi và hướng dẫn xử lý. Mục tiêu phát hiện và thời gian phản hồi không thay thế mục tiêu phục hồi; phát hiện nhanh nhưng không khôi phục được vẫn gây gián đoạn dài.

## 6. Đặc tả chế độ suy giảm mà vẫn giữ bảo mật

| Sự cố | Hành vi có thể chấp nhận trong ví dụ | Điều không được tự ý làm |
|---|---|---|
| Phụ thuộc email lỗi | Lưu tác vụ thông báo bền vững, gửi lại trong giới hạn đã định | Báo email đã gửi khi chưa có bằng chứng |
| Tải xuất báo cáo tăng cao | Giới hạn/tạm dừng báo cáo theo chính sách để giữ luồng thiết yếu | Cho báo cáo chiếm hết kết nối của luồng tạo yêu cầu |
| Không lấy được quyết định quyền cần thiết | Từ chối thao tác cần quyết định đó; giữ các luồng độc lập nếu còn an toàn | Mở quyền cho mọi người hoặc dùng tenant do client tự khai báo |
| Dữ liệu đọc là bản cũ | Chỉ cho phép nếu từng chức năng đã có mức cũ tối đa và cách thông báo | Dùng dữ liệu quyền đã bị thu hồi hoặc trả dữ liệu trái phạm vi |
| Không ghi được audit bắt buộc | Chỉ hoàn tất nếu đã có dấu vết bền vững theo thiết kế được chấp thuận | Bỏ qua dấu vết để giữ tỷ lệ thành công |
| Không bảo đảm lưu bền vững | Trả kết quả lỗi hoặc trạng thái tiếp nhận khác nếu hợp đồng thật sự hỗ trợ | Trả thành công như dữ liệu đã được giữ chắc chắn |

Availability phải được cân bằng với bí mật và toàn vẹn. Tăng số phản hồi thành công bằng cách bỏ xác thực, phân quyền hoặc xác nhận lưu dữ liệu không đáp ứng mục tiêu bảo mật của hệ thống.

## 7. Bộ yêu cầu minh họa cho cổng bảo trì

### AV-REQ-01 — Tạo yêu cầu trong phạm vi dịch vụ đã công bố

Trong cửa sổ tháng và hồ sơ tải nêu ở mục 4, API tạo yêu cầu phải đạt tỷ lệ kết quả tốt tối thiểu 99,9% với thời hạn 2 giây. Kết quả tốt phải gồm mã yêu cầu đúng tenant và dữ liệu đã lưu bền vững. Chỉ số phải được phân tách theo nhóm tenant cần giám sát, ngoài kết quả tổng hợp.

**Nguồn rủi ro:** người dùng hợp lệ không tiếp nhận được yêu cầu bảo trì đúng hạn.

**Bằng chứng:** dữ liệu đo có tử số, mẫu số, thời điểm, phạm vi và quy tắc phân loại; kiểm thử tải kiểm tra cả phản hồi và dữ liệu. Một lần kiểm thử ngắn không tự chứng minh đạt SLO của cả tháng.

### AV-REQ-02 — Quan sát hành trình bên ngoài

Hệ thống giám sát phải kiểm tra hành trình tạo/đọc bằng dữ liệu thử từ ít nhất hai vị trí quan sát độc lập đã xác định, với chu kỳ 30 giây. Trong ví dụ, nếu tại một vị trí có hai lần liên tiếp không đạt, cảnh báo phải tới hàng đợi trực vận hành trong 2 phút tính từ lần không đạt đầu tiên của chuỗi đó.

**Nguồn rủi ro:** dịch vụ không truy cập được từ bên ngoài nhưng chỉ số nội bộ vẫn cho thấy bình thường.

**Bằng chứng:** mô phỏng lỗi đường vào và lỗi phụ thuộc trong phạm vi được phép; đối chiếu mốc kiểm tra, cảnh báo và nơi nhận. Phải theo dõi cả sức khỏe hệ thống giám sát để phân biệt mất quan sát với dịch vụ thực sự đạt.

### AV-REQ-03 — Cách ly tải lạm dụng khỏi luồng thiết yếu

Nhóm phải xác định giới hạn tài nguyên và quy tắc giới hạn tải theo tenant/danh tính cho tạo yêu cầu và xuất báo cáo. Trong kịch bản minh họa, khi một tenant gửi 500 lần gọi/giây thuộc nhóm vượt hạn mức trong 10 phút, hai tenant khác tạo tổng cộng 50 yêu cầu hợp lệ/giây phải đạt ít nhất 99,9% kết quả tốt theo thời hạn 2 giây trong chính lần kiểm chứng đó.

**Nguồn rủi ro:** một bên chiếm tài nguyên dùng chung khiến những bên khác mất dịch vụ.

**Bằng chứng:** hồ sơ thử ghi đầy đủ loại yêu cầu lạm dụng, bộ dữ liệu, cấu hình, phân bố tenant, điểm nghẽn và kết quả của từng nhóm. Kết quả chỉ chứng minh kịch bản đã thử, không phải khả năng chống mọi quy mô tấn công.

### AV-REQ-04 — Phụ thuộc email và thao tác ghi không gây lỗi dây chuyền

Mất email không được chặn việc tạo yêu cầu hợp lệ. Thông tin cần gửi phải được giữ bền vững cùng kết quả nghiệp vụ theo cơ chế nhất quán đã chọn. Retry phải có giới hạn số lần, khoảng chờ và tổng thời gian xử lý; hết giới hạn phải có trạng thái và người xử lý.

Đối với tạo yêu cầu, hệ thống phải hỗ trợ chống lặp trong phạm vi tenant và danh tính người gọi. Trong ví dụ, cùng khóa và cùng nội dung được lưu giữ kết quả để xử lý gọi lại trong 24 giờ; cùng khóa nhưng nội dung khác phải bị từ chối, không tạo yêu cầu thứ hai. Sau thời hạn này, hành vi phải theo hợp đồng đã công bố.

**Nguồn rủi ro:** chờ phụ thuộc kéo dài, bùng tải retry hoặc tạo dữ liệu trùng khi phản hồi bị mất.

**Bằng chứng:** chặn email, làm mất phản hồi sau khi dữ liệu đã cam kết và gửi lại yêu cầu; xác minh số bản ghi, kết quả trả về, tác vụ thông báo và khả năng phục hồi. Mốc 24 giờ là giả định minh họa về hợp đồng chống lặp, không phải mặc định của mọi API.

### AV-REQ-05 — Phục hồi đạt mục tiêu và giữ đúng quyền

Giả sử chủ dịch vụ chấp thuận RPO không quá 5 phút và RTO không quá 30 phút cho kịch bản mất hệ thống lưu trữ chính, trong khi bản sao lưu, khóa, danh tính cần thiết và môi trường phục hồi vẫn dùng được.

- **RPO — Recovery Point Objective:** mức mất dữ liệu tối đa chấp nhận được biểu diễn bằng thời gian. Điểm dữ liệu phục hồi trong ví dụ phải nằm trong 5 phút trước sự cố đối với dữ liệu thuộc phạm vi đã thống nhất.
- **RTO — Recovery Time Objective:** thời gian mục tiêu khôi phục dịch vụ. Đo từ lúc gián đoạn tới khi người dùng hợp lệ tạo/đọc yêu cầu và truy cập tệp cần thiết đúng quyền, sau các kiểm tra phục hồi bắt buộc.

Phục hồi phải bao phủ dữ liệu, tệp, khóa, cấu hình quyền và trạng thái tác vụ liên quan. Trước khi mở lưu lượng cần đối soát giao dịch đã tạo tác động sang bên ngoài và xử lý việc chạy lại, tránh gửi trùng hoặc tái mở quyền đã bị thu hồi.

**Nguồn rủi ro:** dữ liệu hoặc quy trình không thể trở lại mức vận hành chấp nhận được sau sự cố.

**Bằng chứng:** diễn tập phục hồi ghi mốc sự cố, điểm dữ liệu phục hồi, thời điểm đạt tiêu chí nghiệp vụ và kiểm tra quyền. Lịch sao lưu mỗi 5 phút không tự chứng minh đạt RPO; khởi động được database không tự chứng minh đạt RTO.

Mất cả miền sao lưu hoặc khóa không thuộc giả định trên. Nếu cần bảo vệ trước kịch bản đó, phải bổ sung phân tích và yêu cầu riêng. Người có thẩm quyền phải hiểu giới hạn, thay vì đọc con số RTO như một cam kết cho mọi loại sự cố.

## 8. Ma trận kiểm chứng availability

| Tình huống | Điều cần quan sát | Kết luận cần chứng minh |
|---|---|---|
| Tải hợp lệ đúng hồ sơ | Tỷ lệ đạt, thời hạn, trạng thái dữ liệu, phân bố tenant | Luồng thiết yếu đáp ứng mục tiêu trong điều kiện đã nêu |
| Một tenant vượt hạn mức | Kết quả từng tenant, hàng đợi, kết nối, CPU và các điểm nghẽn | Giới hạn không chỉ đẩy lỗi sang người dùng khác |
| Phụ thuộc phản hồi rất chậm | Tổng thời gian, số lần gọi lại, tài nguyên bị giữ | Timeout/retry không tạo chờ vô hạn hoặc bùng tải |
| Email ngừng hoạt động | Tạo yêu cầu, sự kiện chờ, tuổi tác vụ, xử lý sau phục hồi | Chức năng có thể trì hoãn không làm hỏng chức năng thiết yếu |
| Phản hồi tạo bị mất sau cam kết | Khóa chống lặp, số bản ghi, tác dụng phụ | Gọi lại không tạo yêu cầu ngoài ý muốn |
| Một bản ứng dụng bị dừng | Phát hiện, chuyển lưu lượng, kết quả của người dùng | Dự phòng hoạt động theo phạm vi thiết kế |
| Đường xác minh quyền không dùng được | Kết quả truy cập, dữ liệu trả về, log | Không đánh đổi cách ly dữ liệu để tăng tỷ lệ thành công |
| Kho log chẩn đoán hoặc audit lỗi | Tài nguyên, trạng thái giao dịch, dấu vết bền vững | Hành vi đúng chính sách của từng loại log |
| Phục hồi từ bản sao cũ | Mốc thời gian, điểm dữ liệu, quyền, tệp và tác vụ | Đạt RPO/RTO trong kịch bản và giữ đúng điều kiện bảo mật |

Kịch bản cần được thực hiện trong môi trường và phạm vi được cho phép, với cấu hình đại diện cho yêu cầu đang kiểm chứng. Ghi rõ điểm khác biệt với sản xuất và giới hạn của bằng chứng. Một bài thử tải không có đầy đủ kiểm soát quyền hoặc phụ thuộc cần thiết không thể đại diện cho toàn bộ hành vi thực tế.

Không chỉ đo CPU thấp hoặc số bản sao đang chạy. Kết quả chính phải phản ánh điều người dùng hợp lệ làm được; chỉ số hạ tầng giúp giải thích nguyên nhân và năng lực còn lại.

## 9. Quản lý mục tiêu trong vòng đời phát triển

### Trước triển khai

Chủ nghiệp vụ xác nhận chức năng thiết yếu, mức ảnh hưởng gián đoạn và thời gian chấp nhận. Chủ dịch vụ xác nhận khả năng đo, điều kiện tải và nguồn lực. Nhóm thiết kế ghi điểm thực thi và giả định phụ thuộc; nhóm kiểm thử xác định cách thu bằng chứng.

Yêu cầu nên có mã, phiên bản, nguồn rủi ro, phạm vi, chỉ số, cửa sổ, người chịu trách nhiệm và tiêu chí đạt. Các giới hạn hoặc ngoại lệ phải được quyết định trước, không thêm sau khi chỉ số không đạt.

### Trong phát triển và phát hành

Những thay đổi như thêm bước gọi đồng bộ, tăng kích thước dữ liệu, thêm tenant lớn hoặc đổi chính sách xác thực có thể làm đổi thời gian và tài nguyên cần thiết. Cần xem xét lại yêu cầu liên quan và kiểm chứng phần bị ảnh hưởng.

Khi phát hành, chuẩn bị cách phát hiện bản lỗi và khôi phục phiên bản/cấu hình phù hợp. Quay lui ứng dụng không luôn quay lui được dữ liệu; khả năng tương thích và tác động lên dữ liệu cần có kế hoạch riêng.

### Trong vận hành

Theo dõi SLI theo đúng định nghĩa, phân tích tốc độ tiêu thụ ngân sách lỗi và xử lý sự cố theo mức ảnh hưởng. Tổ chức có thể đặt chính sách hạn chế thay đổi rủi ro khi ngân sách lỗi đã cạn; đó là quyết định quản trị cần được thống nhất, không phải một hệ quả tự động của phép tính.

Sau sự cố, cập nhật mô hình đe dọa, giả định tải, yêu cầu và bằng chứng theo điều đã học được. Tỷ lệ tốt của tháng trước không chứng minh tháng sau sẽ đạt nếu đường triển khai, dữ liệu hoặc phụ thuộc đã thay đổi.

Rủi ro còn lại cần nêu kịch bản chưa bao phủ, hậu quả, kiểm soát đã có và người có thẩm quyền chấp nhận. Mục tiêu 99,9% không có nghĩa không thể có sự cố; nó tạo một mức đánh giá cụ thể trong phạm vi đã thống nhất.

## 10. Những cách viết cần sửa

| Cách viết ban đầu | Vấn đề | Cách làm rõ |
|---|---|---|
| “Luôn sẵn sàng 24/7” | Không có chức năng, chỉ số hoặc điều kiện đo | Chỉ rõ hành trình, tập yêu cầu, thời hạn, cửa sổ và mục tiêu |
| “Uptime 99,9%” | Chưa biết đo tiến trình, thời gian hay yêu cầu | Định nghĩa tử số, mẫu số, điểm quan sát và ngoại lệ |
| “Có autoscaling nên chống được quá tải” | Không biết điểm nghẽn và giới hạn phụ thuộc | Đặt kịch bản tải, yêu cầu cách ly và kết quả người dùng cần đạt |
| “Retry đến khi thành công” | Có thể nhân tải và tạo tác dụng phụ | Giới hạn retry, ngân sách thời gian và chống lặp |
| “Trả thành công rồi xử lý sau” | Có thể che mất dữ liệu hoặc tác vụ không hoàn tất | Đặc tả tiếp nhận bền vững, trạng thái cuối và chỉ số hoàn tất |
| “Mất dịch vụ quyền thì cho qua” | Tăng phản hồi bằng cách phá kiểm soát bảo mật | Xác định luồng nào được suy giảm và điều kiện nào vẫn bắt buộc |
| “Có backup là phục hồi được” | Chưa chứng minh dữ liệu, khóa, quyền và thời gian | Diễn tập theo kịch bản RPO/RTO và tiêu chí nghiệp vụ |
| “Tỷ lệ tổng hợp đạt nên mọi khách hàng đều ổn” | Có thể che một tenant mất hoàn toàn dịch vụ | Theo dõi phân nhóm quan trọng và kịch bản cách ly tải |

## 11. Bài tập vận dụng

Một hệ thống cho phép người dùng tải tệp đính kèm lớn và tạo yêu cầu bảo trì bằng văn bản. Cả hai luồng dùng chung giới hạn kết nối và ổ đĩa tạm. Trong giờ cao điểm, một tenant tải nhiều tệp, khiến tenant khác không tạo được yêu cầu dù chỉ gửi nội dung ngắn.

Hãy thực hiện:

1. Viết một kịch bản rủi ro có điều kiện, hành vi và hậu quả nghiệp vụ.
2. Xác định chức năng thiết yếu và hành vi suy giảm được phép cho tải tệp.
3. Viết một SLI cho tạo yêu cầu: tập đủ điều kiện, kết quả tốt, thời hạn và điểm quan sát.
4. Đề xuất yêu cầu giới hạn/cách ly tài nguyên có bằng chứng đo cho từng tenant.
5. Nêu chính sách khi tệp mới được tải một phần nhưng kết nối bị ngắt; bao gồm bản tạm và thao tác gọi lại.
6. Chỉ ra điều kiện xác thực, phân quyền và lưu dữ liệu không được bỏ qua trong lúc quá tải.

**Gợi ý tự đối chiếu:** rủi ro xuất phát từ tài nguyên chung, không chỉ tổng lưu lượng. Cần đo kết quả của tenant không gây tải và chứng minh những giới hạn được thực thi ở nơi tài nguyên thật sự được tiêu thụ. Có thể trì hoãn hoặc từ chối tải tệp vượt chính sách, nhưng không được trả thành công cho một tệp chưa lưu hợp lệ hay cho phép tải tệp trái quyền.

## 12. Checklist bàn giao yêu cầu availability

- [ ] Có người dùng hợp lệ, chức năng thiết yếu và hậu quả gián đoạn rõ ràng.
- [ ] SLI có điểm quan sát, tử số, mẫu số và quy tắc phân loại từ trước.
- [ ] SLO có cửa sổ đo, điều kiện tải và cách xử lý khoảng bảo trì.
- [ ] Có kiểm tra hành trình từ bên ngoài và phân nhóm khách hàng quan trọng.
- [ ] Ngân sách lỗi theo thời gian và theo yêu cầu không bị trộn lẫn.
- [ ] Giới hạn tài nguyên, timeout và retry có phạm vi, ngưỡng và hành vi khi chạm giới hạn.
- [ ] Chế độ suy giảm vẫn giữ điều kiện xác thực, phân quyền và toàn vẹn cần thiết.
- [ ] Các thao tác ghi/gọi lại có chính sách chống lặp và trạng thái kết quả rõ ràng.
- [ ] Dự phòng đã xét phụ thuộc và nguyên nhân lỗi chung.
- [ ] Log, audit, cảnh báo và người phản hồi được xác định.
- [ ] RPO/RTO gắn với kịch bản và được kiểm chứng bằng phục hồi quy trình thực.
- [ ] Yêu cầu có liên kết rủi ro, kiến trúc, bằng chứng và người chịu trách nhiệm rủi ro còn lại.

Availability có giá trị khi người dùng được phép thực hiện đúng công việc trong thời hạn cần thiết, kể cả khi có tải bất thường hoặc sự cố trong phạm vi đã thiết kế. Đặc tả rõ cách đo, hành vi suy giảm và điều kiện phục hồi giúp biến mục tiêu đó thành yêu cầu có thể triển khai và kiểm chứng.
