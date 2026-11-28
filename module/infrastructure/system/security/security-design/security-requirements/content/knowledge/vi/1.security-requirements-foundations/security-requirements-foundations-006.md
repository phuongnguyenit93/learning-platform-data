# Bảo mật như một quality attribute

## 1. Vì sao bảo mật là thuộc tính chất lượng của hệ thống?

Một hệ thống quản lý hóa đơn có thể tạo hóa đơn, tìm kiếm khách hàng và xuất báo cáo đúng nghiệp vụ nhưng vẫn không đáp ứng nhu cầu sử dụng nếu nhân viên công ty A xem được hóa đơn của công ty B. Chức năng “xem hóa đơn” tồn tại và hoạt động; điều còn thiếu là điều kiện để chức năng đó hoạt động an toàn.

**Quality attribute**, hay **thuộc tính chất lượng**, mô tả một khía cạnh về cách hệ thống vận hành hoặc các tính chất mà hệ thống phải duy trì. Bảo mật là thuộc tính chất lượng liên quan đến việc bảo vệ dữ liệu, hành động và tài nguyên trước việc truy cập, sử dụng, thay đổi hoặc phá hoại trái phép. Thuộc tính này phải được xem xét trong từng chức năng, từng ranh giới tin cậy và trong cả quá trình vận hành, chứ không chỉ ở màn hình đăng nhập.

Trong thiết kế yêu cầu bảo mật, các mục tiêu thường gặp gồm:

| Mục tiêu | Câu hỏi cần trả lời | Ví dụ với hệ thống hóa đơn |
|---|---|---|
| Tính bí mật — confidentiality | Ai được phép biết thông tin nào? | Người dùng chỉ đọc được hóa đơn thuộc tenant mà họ có quyền truy cập. |
| Tính toàn vẹn — integrity | Ai được thay đổi dữ liệu, theo quy tắc nào? | Chỉ người có quyền phê duyệt mới chuyển hóa đơn sang trạng thái đã duyệt. |
| Tính sẵn sàng — availability | Người dùng hợp lệ còn dùng được dịch vụ khi có sự cố hoặc lạm dụng không? | Lưu lượng bất thường từ một tenant không làm các tenant khác mất khả năng tra cứu. |
| Khả năng quy trách nhiệm — accountability | Có xác định và kiểm tra được chủ thể đã thực hiện hành động không? | Thay đổi quyền truy cập có dấu vết về chủ thể, đối tượng, thời điểm và kết quả. |

Các mục tiêu này giúp định hướng nhưng **chưa phải yêu cầu đủ để triển khai**. “Dữ liệu phải bí mật” không xác định người nào được đọc, dữ liệu nào nằm trong phạm vi, các đường xuất dữ liệu hay cách kiểm chứng. Công việc của người đặc tả yêu cầu là chuyển mục tiêu đó thành nghĩa vụ cụ thể của hệ thống.

Không nên đồng nhất chất lượng bảo mật với số lượng cơ chế đã cài đặt. Có xác thực đa yếu tố, mã hóa và tường lửa không tự động chứng minh rằng hệ thống ngăn được truy cập chéo tenant. Cần chứng minh hành vi và tính chất bảo vệ mà các cơ chế đó thực sự tạo ra.

## 2. Quan hệ giữa chức năng, thuộc tính chất lượng và ràng buộc thiết kế

Bảo mật thường được xếp vào nhóm yêu cầu phi chức năng. Cách gọi này hữu ích khi phân loại tài liệu, nhưng dễ gây hiểu nhầm rằng bảo mật không chứa hành vi chức năng. Trong thực tế, một mục tiêu bảo mật có thể cần cả quy tắc nghiệp vụ, hành vi xử lý và tính chất vận hành.

| Loại phát biểu | Ví dụ | Vai trò trong đặc tả |
|---|---|---|
| Chức năng nghiệp vụ | Người dùng mở trang chi tiết hóa đơn. | Xác định khả năng mà sản phẩm cung cấp. |
| Hành vi bảo mật | Hệ thống kiểm tra quyền đọc trên hóa đơn được yêu cầu. | Xác định việc hệ thống phải thực hiện để bảo vệ chức năng. |
| Thuộc tính cần duy trì | Không trả dữ liệu hóa đơn cho người không có quyền, kể cả khi họ biết mã hóa đơn. | Xác định kết quả bảo vệ trên các đường truy cập thuộc phạm vi. |
| Ràng buộc thiết kế | Mọi yêu cầu đọc hóa đơn đi qua điểm kiểm soát truy cập phía máy chủ. | Giới hạn cách thiết kế được phép đáp ứng yêu cầu. |
| Tiêu chí chấp nhận | Bộ ca truy cập chéo tenant không nhận dữ liệu được bảo vệ và không gây tác dụng phụ nghiệp vụ. | Cung cấp cơ sở xác minh. |

Một yêu cầu tốt phân biệt **kết quả cần đạt** với **giải pháp được chọn**. Chẳng hạn, “dùng JWT” là lựa chọn kỹ thuật, không trả lời được token của người dùng tenant A có được dùng để lấy dữ liệu tenant B hay không. “Dùng RBAC” cũng chưa mô tả quyền trên từng đối tượng, phạm vi tenant hay trường hợp một người có nhiều vai trò.

Ràng buộc công nghệ vẫn có thể cần thiết khi kiến trúc, hợp đồng hoặc môi trường triển khai bắt buộc một giải pháp. Khi đó, nên ghi rõ căn cứ của ràng buộc và liên kết nó với yêu cầu bảo vệ, thay vì dùng tên công nghệ thay cho yêu cầu.

Bảo mật cũng không phải một con số duy nhất. Câu “hệ thống đạt bảo mật 99,9%” không có ý nghĩa kiểm chứng nếu không xác định đại lượng, khoảng thời gian, điều kiện và nguồn bằng chứng. Một hệ thống có thể bảo vệ tốt dữ liệu khi truyền nhưng vẫn cho phép người dùng sửa đối tượng mà họ không sở hữu.

## 3. Mô tả bảo mật bằng kịch bản thuộc tính chất lượng

Một cách hiệu quả để làm rõ yêu cầu là viết **kịch bản thuộc tính chất lượng**. Kịch bản mô tả điều gì tác động lên hệ thống, hệ thống phải phản ứng ra sao và quan sát kết quả bằng cách nào.

### 3.1. Sáu thành phần của một kịch bản

| Thành phần | Câu hỏi gợi ý | Ví dụ |
|---|---|---|
| Nguồn kích thích — source | Ai hoặc thành phần nào tạo tác động? | Người dùng đã đăng nhập của tenant A. |
| Kích thích — stimulus | Hành động hoặc sự kiện nào xảy ra? | Gửi yêu cầu đọc hóa đơn của tenant B bằng mã hóa đơn đã biết. |
| Đối tượng chịu tác động — artifact | Phần nào của hệ thống nằm trong phạm vi? | API đọc chi tiết hóa đơn và dữ liệu do API trả về. |
| Môi trường — environment | Hệ thống đang ở trạng thái nào? | Chạy bình thường, có cache, nhiều tenant dùng chung hạ tầng. |
| Phản ứng — response | Hệ thống phải làm gì? | Kiểm tra quyền, từ chối truy cập, không đưa dữ liệu hóa đơn vào phản hồi. |
| Thước đo phản ứng — response measure | Dựa vào đâu để chấp nhận hoặc bác bỏ? | Các ca kiểm thử thuộc phạm vi đều bị từ chối, không có dữ liệu được bảo vệ trong phản hồi; sự kiện được ghi nhận trong giới hạn thời gian đã thống nhất. |

“Đối tượng chịu tác động” có thể là dịch vụ, hàng đợi, bản sao lưu hoặc thành phần kiến trúc khác; không nhất thiết là một tệp đầu ra.

Kịch bản cũng không chỉ dành cho kẻ tấn công bên ngoài. Nguồn kích thích có thể là tài khoản nội bộ bị chiếm quyền, một dịch vụ gọi sai phạm vi, người quản trị thao tác nhầm hoặc sự cố hạ tầng. Không cần khẳng định có động cơ xấu mới xác định được nghĩa vụ bảo vệ.

### 3.2. Một kịch bản hoàn chỉnh

> Khi người dùng đã xác thực thuộc tenant A yêu cầu đọc một hóa đơn thuộc tenant B qua API, trong điều kiện hệ thống vận hành bình thường và cache được bật, hệ thống phải quyết định quyền dựa trên danh tính đã xác minh, tư cách thành viên còn hiệu lực và tenant của hóa đơn. Nếu người dùng không có quyền, hệ thống phải từ chối trước khi trả dữ liệu hóa đơn, không thay đổi trạng thái nghiệp vụ và tạo sự kiện từ chối truy cập. Các ca truy cập chéo tenant được định nghĩa trong bộ kiểm thử phải không nhận được dữ liệu hóa đơn; sự kiện phải truy xuất được từ hệ thống giám sát trong tối đa 60 giây ở môi trường kiểm thử đã thỏa thuận.

Con số 60 giây trong bài là **giá trị minh họa cho hệ thống giả định**, không phải chuẩn bắt buộc. Các ngưỡng thời gian, tải, thời gian phục hồi và mức độ tươi của quyền phải được chốt dựa trên rủi ro, năng lực vận hành và nhu cầu sản phẩm.

Kịch bản này làm lộ ra các quyết định thiết kế quan trọng: lấy tenant từ đâu, có kiểm tra quyền trên cache hit hay không, vai trò bị thu hồi được cập nhật thế nào và kiểm chứng sự kiện bằng công cụ nào. Đây là lý do yêu cầu chất lượng nên được viết trước khi chốt kiến trúc chi tiết.

## 4. Từ mục tiêu và mô hình đe dọa đến yêu cầu đo được

Giả sử sản phẩm là dịch vụ quản lý hóa đơn cho nhiều công ty. Mỗi công ty là một tenant, có người dùng và dữ liệu riêng. Một người có thể là thành viên nhiều tenant, nhưng quyền trong tenant này không tự tạo quyền ở tenant khác. Dữ liệu được truy cập qua API, tác vụ xuất tệp và giao diện quản trị hỗ trợ.

Luồng suy luận để hình thành yêu cầu có thể biểu diễn như sau:

```text
Tài sản và mục tiêu bảo vệ
          |
          v
Mối đe dọa + ranh giới tin cậy + giả định
          |
          v
Kịch bản chất lượng có phản ứng và thước đo
          |
          v
Yêu cầu có mã định danh, phạm vi và tiêu chí chấp nhận
          |
          v
Quyết định kiến trúc và cơ chế thực hiện
          |
          v
Kiểm thử, bằng chứng và theo dõi vận hành
```

### 4.1. Xác định tài sản, rủi ro và phạm vi

Tài sản quan trọng gồm nội dung hóa đơn, tệp xuất, thông tin khách hàng, quyền người dùng, nhật ký kiểm toán và dữ liệu sao lưu. Một rủi ro cụ thể là người dùng lấy được hóa đơn của tenant khác bằng cách thay mã đối tượng trong yêu cầu.

Cần nêu ranh giới tin cậy: trình duyệt và các tham số do người dùng gửi không phải nguồn đáng tin để quyết định quyền. Máy chủ phải xác minh chủ thể và đánh giá quyền đối với đối tượng thực tế. Việc một màn hình không hiển thị nút tải xuống không ngăn người dùng gọi trực tiếp API tải tệp.

Cũng phải xác định các quyền đặc biệt. Nếu bộ phận hỗ trợ được phép truy cập nhiều tenant theo quy trình riêng, ngoại lệ đó cần có điều kiện cấp quyền, phạm vi, thời hạn và ghi nhận truy cập rõ ràng. Không được để “quản trị viên được xem tất cả” trở thành ngoại lệ ngầm làm vô hiệu mục tiêu cách ly dữ liệu.

### 4.2. Viết yêu cầu dựa trên kết quả quan sát được

**SEC-QA-01 — Cách ly quyền đọc hóa đơn giữa các tenant**

- **Mục tiêu:** bảo vệ bí mật dữ liệu hóa đơn trước truy cập chéo tenant.
- **Phạm vi:** API chi tiết, danh sách, tìm kiếm, xuất tệp và tải tệp xuất hóa đơn của sản phẩm giả định.
- **Quy tắc:** mỗi lần truy cập phải được cho phép dựa trên chủ thể đã xác minh, quyền đối với hành động và tenant của dữ liệu. Không tin riêng `tenantId` do client cung cấp. Nếu chưa xác định được quyền hợp lệ, không trả dữ liệu hóa đơn.
- **Phản ứng khi từ chối:** không trả nội dung hoặc metadata hóa đơn được bảo vệ; không gây thay đổi trạng thái nghiệp vụ. Hợp đồng phản hồi không tiết lộ hóa đơn ở tenant khác có tồn tại hay không cho người không có quyền. Có thể ghi nhật ký bảo mật cho lần từ chối.
- **Bằng chứng:** kiểm thử tích hợp trên các đường truy cập thuộc phạm vi, có cache hit và cache miss, kết hợp kiểm tra thiết kế về nơi thực thi quyền.
- **Chủ sở hữu:** nhóm phụ trách miền hóa đơn phối hợp với nhóm nền tảng định danh; người chịu trách nhiệm cuối cùng phải được chỉ định trong dự án thực tế.

Quy tắc “mỗi lần truy cập” không buộc mọi hệ thống truy vấn kho quyền từ xa cho từng request. Hệ thống có thể dùng quyết định hoặc dữ liệu quyền được cache nếu đáp ứng yêu cầu về phạm vi, tính đúng đắn và độ trễ thu hồi đã thống nhất. Thiết kế phải giải thích được cách đáp ứng quy tắc đó.

### 4.3. Định nghĩa đo lường cho đủ nghĩa

Một con số chỉ hữu ích khi có ngữ cảnh. Nếu bổ sung yêu cầu “chi phí kiểm tra quyền p95 không quá 30 ms”, cần làm rõ:

- Đo từ lúc bắt đầu đến lúc kết thúc quyết định quyền ở máy chủ hay đo toàn bộ HTTP request.
- Đo trên tải nào, lượng dữ liệu nào và trạng thái cache nào.
- Có bao gồm thời gian gọi dịch vụ quyền từ xa hay không.
- Cửa sổ đo, số mẫu tối thiểu và cách xử lý lỗi.
- Có kiểm tra đồng thời rằng quyết định quyền vẫn đúng hay không.

**p95** là phân vị thứ 95 của tập thời gian quan sát, không có nghĩa mọi yêu cầu đều hoàn thành trong ngưỡng đó. Ngưỡng độ trễ phục vụ đánh giá tác động hiệu năng; nó không cho phép bỏ kiểm tra quyền khi hệ thống chậm.

Không phải mọi thước đo bảo mật đều là thời gian hoặc tỷ lệ. Các tính chất như “không có tác dụng phụ nghiệp vụ khi bị từ chối”, “không lưu token trong log” hoặc “chỉ vai trò được cấp mới được phê duyệt” đều có thể kiểm chứng bằng các quan sát được định nghĩa rõ.

## 5. Một thuộc tính xuyên suốt nhiều nhóm yêu cầu

Cùng một mục tiêu bảo vệ có thể cần nhiều yêu cầu phối hợp. Bảng dưới minh họa các yêu cầu cho hệ thống hóa đơn; các con số là giả định để thực hành đặc tả.

| Mã | Nhóm | Yêu cầu minh họa | Tiêu chí kiểm chứng chính |
|---|---|---|---|
| SEC-AUTH-01 | Xác thực | Trước khi cấp quyền quản trị tenant hoặc phát hành tệp xuất hàng loạt, yêu cầu người thao tác hoàn tất xác thực đa yếu tố còn hiệu lực trong 5 phút gần nhất. | Gọi trực tiếp API khi chưa đáp ứng điều kiện phải bị từ chối; không cấp quyền, không tạo tệp xuất và có hướng dẫn hoàn tất xác thực bổ sung. |
| SEC-QA-01 | Phân quyền | Chỉ trả dữ liệu hóa đơn khi chủ thể có quyền đối với hành động và tenant của hóa đơn. | Các ca truy cập chéo tenant trên API, tìm kiếm, xuất và tải tệp không nhận dữ liệu được bảo vệ; không có tác dụng phụ nghiệp vụ. |
| SEC-DATA-01 | Dữ liệu | Áp dụng chính sách mã hóa đã được phê duyệt cho kênh truyền, kho dữ liệu, tệp xuất và bản sao lưu chứa hóa đơn; giới hạn quyền sử dụng khóa theo vai trò dịch vụ. | Đối chiếu phạm vi lưu trữ với cấu hình và kiểm tra truy cập khóa bằng danh tính được cấp quyền và không được cấp quyền. |
| SEC-LOG-01 | Logging | Ghi nhận thay đổi quyền và lần truy cập hóa đơn bị từ chối với các trường bắt buộc; không ghi mật khẩu, token hay nội dung hóa đơn. | Sự kiện truy xuất được trong 60 giây ở tải đã thỏa thuận; trường bắt buộc đầy đủ và không xuất hiện dữ liệu bị cấm trong các ca kiểm thử. |
| SEC-REC-01 | Phục hồi | Có khả năng phục hồi dữ liệu hóa đơn trong RTO 4 giờ với RPO 15 phút, đồng thời bảo toàn cách ly tenant và quyền truy cập. | Diễn tập phục hồi trên phạm vi đã định, đo thời gian, kiểm tra khoảng mất dữ liệu và thử truy cập hợp lệ/trái phép sau phục hồi. |

Yêu cầu về xác thực đa yếu tố phải bao phủ các đường hoàn tất hành động nhạy cảm, không chỉ giao diện. Việc “đã bật MFA cho tài khoản” khác với việc có bằng chứng xác thực bổ sung đủ mới cho hành động đang thực hiện.

Đối với mã hóa, tài liệu dự án cần chỉ rõ chính sách được tham chiếu, phạm vi, cách quản lý vòng đời khóa và trách nhiệm cấu hình. Mã hóa không thay thế phân quyền: một API có quyền giải mã vẫn có thể trả dữ liệu cho sai người nếu kiểm soát truy cập sai.

**RTO** là mục tiêu về thời gian phục hồi dịch vụ sau sự cố; **RPO** là mục tiêu về khoảng mất dữ liệu tối đa tính theo thời gian. Trong dự án thực tế phải định nghĩa rõ mốc bắt đầu, mốc kết thúc và loại sự cố được áp dụng. Có bản sao lưu chưa chứng minh rằng có thể phục hồi đúng các mục tiêu này.

Các yêu cầu liên quan cần được nối với nhau. Chẳng hạn, sau khi phục hồi không được khôi phục hiệu lực cho tài khoản đã bị khóa mà không xử lý chênh lệch trạng thái quyền. Khi nhật ký dùng chung hạ tầng nhiều tenant, chính nhật ký cũng trở thành tài sản cần kiểm soát truy cập.

## 6. Yêu cầu bảo mật dẫn dắt kiến trúc như thế nào?

Thuộc tính chất lượng có ảnh hưởng đến kiến trúc vì một quyết định cục bộ thường không đủ để bảo vệ toàn bộ luồng dữ liệu.

### 6.1. Đặt kiểm soát ở ranh giới thực thi phù hợp

Với SEC-QA-01, giao diện chỉ có thể hỗ trợ trải nghiệm người dùng. Quyết định cho phép đọc dữ liệu phải được thực thi ở phía máy chủ, tại các đường xử lý có thể trả dữ liệu. Thiết kế cần trả lời:

- Chủ thể được xác minh bằng cách nào, và thông tin tenant được đối chiếu với quyền ở đâu?
- Mọi đường đọc, kể cả tìm kiếm, xuất tệp, tác vụ nền và hỗ trợ vận hành, có cùng nghĩa phân quyền không?
- Cache được phân vùng và kiểm tra quyền ra sao để dữ liệu tenant này không bị dùng cho tenant khác?
- URL tải tệp được bảo vệ như thế nào khi người dùng chia sẻ liên kết hoặc bị thu hồi quyền?
- Tài khoản dịch vụ có quyền rộng hơn người dùng cuối hay không, và phạm vi đó được giới hạn thế nào?

Câu trả lời có thể dẫn đến điểm thực thi chính sách dùng chung, điều kiện lọc dữ liệu bắt buộc hoặc cách ly kho dữ liệu. Yêu cầu không mặc định chỉ một giải pháp là đúng; giải pháp được chọn phải đáp ứng các kịch bản và ràng buộc đã công bố.

### 6.2. Xử lý lỗi cũng là một phần của yêu cầu

Giả sử dịch vụ phân quyền tạm thời không phản hồi. Nếu tài liệu chỉ nói “kiểm tra quyền trước khi đọc” thì đội triển khai vẫn có thể hiểu khác nhau về hành vi khi kiểm tra thất bại.

Với thao tác đọc hóa đơn nhạy cảm, yêu cầu có thể quy định: **không trả dữ liệu nếu không có cơ sở hợp lệ để cho phép truy cập**. Đây là nguyên tắc từ chối khi không xác lập được quyền, thường gọi là fail closed. Phản hồi có thể cho biết tạm thời chưa xử lý được yêu cầu, theo hợp đồng API, thay vì khẳng định người dùng chắc chắn không có quyền.

Nếu kiến trúc cho phép tiếp tục dùng dữ liệu quyền đã cache trong một số tình huống, giới hạn độ cũ, phạm vi hành động và điều kiện vô hiệu hóa phải được đặc tả. Không dùng yêu cầu sẵn sàng làm lý do ngầm để chấp nhận mọi truy cập khi dịch vụ quyền lỗi.

### 6.3. Làm rõ yêu cầu thu hồi quyền

“Thu hồi quyền có hiệu lực ngay” có thể không đủ rõ trong hệ thống phân tán. Cần xác định cả request đang xử lý, phiên đăng nhập, cache quyền, tác vụ nền và liên kết tải tệp còn hiệu lực.

Một yêu cầu đo được cho ví dụ này có thể là:

> Sau khi thao tác thu hồi quyền đọc được hệ thống xác nhận thành công tại thời điểm t0, mọi yêu cầu đọc mới bắt đầu từ t0 + 60 giây phải bị từ chối trên API, đường tải tệp và tác vụ xuất của người bị thu hồi. Các yêu cầu bắt đầu sớm hơn được xử lý theo chính sách riêng về tác vụ đang chạy; chính sách đó phải được ghi rõ và chấp nhận trước khi triển khai.

Giới hạn 60 giây thể hiện một khoảng trễ được chấp nhận trong ví dụ, vì vậy phải được chủ sở hữu rủi ro cân nhắc. Nếu loại dữ liệu không chấp nhận khoảng trễ này, cần yêu cầu chặt hơn và lựa chọn kiến trúc phù hợp. Không nên diễn giải nó thành bảo đảm “thu hồi tức thời”.

## 7. Cân bằng với các thuộc tính chất lượng khác

Bảo mật tương tác với hiệu năng, khả dụng, khả năng sử dụng, quyền riêng tư và khả năng thay đổi. Phân tích tương tác giúp đưa ra quyết định có căn cứ; không có nghĩa được tự ý hạ yêu cầu bảo vệ.

| Tương tác | Mâu thuẫn có thể xảy ra | Cách thể hiện thành quyết định kiểm chứng được |
|---|---|---|
| Bảo mật và hiệu năng | Kiểm tra quyền từ xa làm tăng độ trễ. | Đặt ngân sách độ trễ cho quyết định quyền; nếu dùng cache thì kèm giới hạn thu hồi và kiểm thử tính đúng. |
| Bảo mật và sẵn sàng | Phụ thuộc xác thực hoặc phân quyền lỗi làm người dùng không truy cập được. | Định nghĩa chế độ lỗi, năng lực dự phòng và điều kiện dùng trạng thái quyền còn hợp lệ. |
| Bảo mật và trải nghiệm | Xác thực bổ sung quá thường xuyên gây gián đoạn công việc. | Chỉ rõ thao tác nhạy cảm, mức độ mới của xác thực và luồng hoàn tất hoặc hủy hành động. |
| Khả năng điều tra và quyền riêng tư | Log chi tiết giúp điều tra nhưng có thể chứa dữ liệu nhạy cảm. | Quy định trường được ghi, dữ liệu bị cấm, thời hạn lưu, đối tượng được đọc và cách che dữ liệu. |
| Bảo mật và khả năng thay đổi | Chính sách rải rác khiến một API mới dễ thiếu kiểm soát. | Định nghĩa nơi quản lý chính sách, điểm thực thi bắt buộc và tiêu chí nghiệm thu khi thêm đường truy cập. |

Ví dụ, dùng cache quyết định quyền có thể giảm độ trễ nhưng tăng thời gian quyền cũ còn được chấp nhận. Quyết định đó chỉ đầy đủ khi ghi lại cả lợi ích, phạm vi áp dụng, khoảng trễ thu hồi, cách vô hiệu hóa và bằng chứng thử nghiệm.

Tương tự, logging không chỉ là “ghi càng nhiều càng tốt”. Ghi toàn bộ request có thể làm lộ token hoặc dữ liệu khách hàng. Ghi quá ít lại khiến việc điều tra không xác định được chủ thể và hành động. Yêu cầu cần mô tả dữ liệu tối thiểu đủ phục vụ mục đích, với quyền đọc và thời hạn lưu rõ ràng.

## 8. Kiểm chứng: từ yêu cầu đến bằng chứng

### 8.1. Phân biệt nghĩa vụ bảo vệ với phạm vi kiểm thử

“Nghiêm cấm đọc dữ liệu trái phép” là nghĩa vụ của hệ thống. “100% ca kiểm thử được định nghĩa đều bị từ chối đúng” là kết quả của một tập kiểm thử hữu hạn. Kết quả đó cần thiết nhưng không chứng minh rằng mọi đường tấn công có thể có đã được loại bỏ.

Vì vậy, nên kết hợp các nguồn bằng chứng phù hợp:

| Nguồn bằng chứng | Điều có thể xác minh |
|---|---|
| Xem xét yêu cầu và thiết kế | Phạm vi dữ liệu, ranh giới tin cậy, giả định và điểm thực thi quyền có được nhận diện không. |
| Kiểm thử đơn vị cho chính sách | Các tổ hợp vai trò, tenant, hành động và trạng thái đối tượng có được quyết định đúng không. |
| Kiểm thử tích hợp | API, truy vấn dữ liệu, cache và tác vụ nền có cùng thực thi yêu cầu không. |
| Kiểm thử có chủ đích theo mối đe dọa | Thay mã đối tượng, giả tenant, bỏ qua giao diện hoặc dùng quyền đã thu hồi có vượt kiểm soát không. |
| Đối chiếu cấu hình và vận hành | Mã hóa, quyền dịch vụ, đường đi của log và cấu hình sao lưu có khớp đặc tả không. |
| Diễn tập phục hồi | Có khôi phục được dịch vụ, dữ liệu và kiểm soát truy cập trong điều kiện đã đặt ra không. |

Mục tiêu là có bằng chứng phù hợp với bản chất yêu cầu. Kiểm tra rằng một hàm `checkPermission()` đã được gọi không đủ để chứng minh rằng người dùng không nhận dữ liệu trái phép.

### 8.2. Ví dụ tiêu chí chấp nhận cho SEC-QA-01

```gherkin
Tính năng: Cách ly dữ liệu hóa đơn giữa các tenant

  Kịch bản: Người dùng tenant A đọc hóa đơn tenant B
    Cho trước người dùng U đang có phiên hợp lệ
    Và U chỉ có quyền đọc hóa đơn thuộc tenant A
    Và hóa đơn INV-B thuộc tenant B
    Khi U gọi trực tiếp API chi tiết cho INV-B
    Thì phản hồi không chứa nội dung hoặc metadata hóa đơn được bảo vệ
    Và phản hồi tuân theo hợp đồng không tiết lộ sự tồn tại của INV-B
    Và không có thay đổi trạng thái nghiệp vụ của hóa đơn
    Và có sự kiện từ chối gắn với chủ thể và mã tương quan
```

Bộ kiểm thử cần có cả ca được phép để tránh hệ thống “đạt bảo mật” chỉ bằng cách từ chối mọi người. Với cùng người dùng U, yêu cầu đọc một hóa đơn thuộc tenant A phải trả đúng dữ liệu nếu các điều kiện quyền khác đều thỏa mãn.

Các chiều kiểm thử cần được xác định từ phạm vi yêu cầu:

- Chủ thể: chưa xác thực, được phép, sai tenant, bị thu hồi quyền, tài khoản dịch vụ.
- Đường dữ liệu: chi tiết, danh sách, tìm kiếm, xuất, tải tệp và tác vụ nền.
- Trạng thái: cache hit, cache miss, quyền vừa thay đổi, phụ thuộc phân quyền bị lỗi.
- Kết quả: dữ liệu trả về, tác dụng phụ nghiệp vụ, sự kiện bảo mật và hợp đồng lỗi.

Không cần tạo toàn bộ tích Descartes một cách máy móc. Có thể chọn tổ hợp theo rủi ro, nhưng phải nêu các trường hợp quan trọng đã bao phủ và phần còn lại dựa trên giả định nào.

### 8.3. Kiểm chứng logging mà không tạo thêm rò rỉ

Một sự kiện từ chối truy cập có thể chứa thời điểm, mã tương quan, định danh chủ thể dạng nội bộ, tenant của chủ thể, hành động, loại tài nguyên, kết quả và mã lý do. Có ghi định danh đối tượng bị yêu cầu hay không phải dựa trên chính sách dữ liệu của log; người không có quyền không được đọc log để suy ra dữ liệu tenant khác.

Tiêu chí chấp nhận nên tách “sự kiện được tạo ở ứng dụng” với “sự kiện đã truy vấn được tại nơi phục vụ điều tra”. Nếu yêu cầu là truy xuất được trong 60 giây thì cần đo cả đường chuyển và lập chỉ mục, với điểm bắt đầu đo được quy định rõ, chẳng hạn thời điểm máy chủ ghi nhận quyết định từ chối.

Nếu đường chuyển log lỗi, yêu cầu phải chỉ rõ khả năng đệm, cảnh báo và hành vi của thao tác liên quan. Không mặc định mọi thao tác đều phải dừng, cũng không mặc định được phép làm mất dấu vết; lựa chọn phụ thuộc loại hành động và rủi ro đã được chấp nhận.

## 9. Truy vết trong vòng đời phát triển

Yêu cầu bảo mật chỉ phát huy vai trò thuộc tính chất lượng khi được duy trì qua thiết kế, triển khai, phát hành và vận hành. Một ma trận truy vết nhỏ có thể giúp tránh việc mất liên kết giữa rủi ro ban đầu với bằng chứng cuối cùng.

| Rủi ro | Yêu cầu | Điểm kiến trúc cần đáp ứng | Bằng chứng dự kiến |
|---|---|---|---|
| R-01: truy cập hóa đơn chéo tenant | SEC-QA-01 | Điểm thực thi quyền, lớp truy vấn dữ liệu, cache, luồng xuất tệp | Kết quả kiểm thử các đường dữ liệu và xem xét thiết kế cách ly |
| R-02: chiếm tài khoản để làm thao tác quản trị | SEC-AUTH-01 | Luồng xác thực bổ sung và API thực hiện hành động nhạy cảm | Kiểm thử API với bằng chứng xác thực thiếu, hết hạn và hợp lệ |
| R-03: không điều tra được việc thay đổi quyền | SEC-LOG-01 | Phát sự kiện, vận chuyển log và kho truy vấn có kiểm soát | Kiểm thử đủ trường, dữ liệu bị cấm và độ trễ truy xuất |
| R-04: mất dữ liệu hoặc phục hồi sai quyền | SEC-REC-01 | Sao lưu, phục hồi, khóa mã hóa và đồng bộ trạng thái quyền | Biên bản diễn tập với RTO, RPO và kiểm tra quyền sau phục hồi |

Mỗi yêu cầu nên có người chịu trách nhiệm, phiên bản, phạm vi áp dụng và liên kết bằng chứng. Một yêu cầu có thể liên quan nhiều rủi ro, và một rủi ro thường cần nhiều yêu cầu cùng xử lý. Ma trận không nên ép các quan hệ đó thành một đối một.

Khi thêm API xuất hóa đơn mới, cần kiểm tra lại SEC-QA-01, SEC-DATA-01 và SEC-LOG-01 trên đường mới. Khi thay đổi cách cache quyền, cần xem lại giới hạn thu hồi. Khi đổi nơi lưu bản sao lưu, phải xem lại khả năng phục hồi và quyền sử dụng khóa. Đây là hoạt động quản lý thay đổi yêu cầu, không phải chỉ cập nhật một danh sách kiểm tra lúc phát hành.

Nếu dự án chấp nhận ngoại lệ tạm thời, hồ sơ ngoại lệ cần chỉ rõ yêu cầu bị ảnh hưởng, rủi ro còn lại, biện pháp bù đắp, người chấp nhận và thời điểm xem xét lại. Không đổi một ca kiểm thử thất bại thành đạt bằng cách xóa nó mà không có quyết định thay đổi yêu cầu.

## 10. Các lỗi đặc tả thường gặp và cách sửa

| Phát biểu chưa đủ | Vấn đề | Hướng viết lại |
|---|---|---|
| “Hệ thống phải an toàn.” | Không xác định tài sản, chủ thể, hành động hay kết quả. | Viết kịch bản cụ thể theo nguồn kích thích, môi trường, phản ứng và thước đo. |
| “Có đăng nhập là đủ.” | Xác thực không quyết định quyền trên từng tài nguyên. | Gắn mỗi hành động nhạy cảm với chủ thể, phạm vi dữ liệu và điều kiện cho phép. |
| “Dùng HTTPS nên dữ liệu được bảo vệ.” | Chỉ đề cập một phần đường đi của dữ liệu. | Xác định kênh truyền, nơi lưu, tệp xuất, sao lưu và người được truy cập. |
| “Mọi truy cập đều được log.” | Không rõ sự kiện, trường, độ trễ, quyền đọc và dữ liệu bị cấm. | Đặc tả nhóm sự kiện cần ghi cùng hợp đồng dữ liệu và tiêu chí truy xuất. |
| “Không bao giờ bị tấn công.” | Không phải cam kết có thể chứng minh bằng một quy trình hữu hạn. | Định nghĩa nghĩa vụ bảo vệ, mô hình đe dọa và phạm vi bằng chứng; ghi rõ giả định. |
| “Thu hồi quyền ngay lập tức.” | Không rõ mốc thời gian, request đang chạy và các bản sao trạng thái. | Nêu mốc hiệu lực, độ trễ tối đa, đường truy cập và cách đo. |
| “Kiểm thử bảo mật đã đạt.” | Không truy được yêu cầu, phiên bản và phạm vi đã thử. | Liên kết kết quả với mã yêu cầu, cấu hình, dữ liệu và ca kiểm thử cụ thể. |

## 11. Bài tập áp dụng

Một công ty muốn thêm chức năng chia sẻ tệp xuất hóa đơn qua liên kết tải xuống. Tệp có dữ liệu khách hàng và có thể được tạo bởi tác vụ nền. Người dùng có thể mất quyền đọc hóa đơn sau khi tệp đã được tạo.

Hãy thực hiện các bước sau:

1. Xác định tài sản, chủ thể hợp lệ và ít nhất hai mối đe dọa, bao gồm truy cập bằng liên kết bị chuyển tiếp và sử dụng liên kết sau khi mất quyền.
2. Viết một kịch bản sáu thành phần cho thao tác tải tệp, nêu rõ môi trường và phản ứng khi quyền không còn hợp lệ.
3. Đề xuất yêu cầu về quyền tải, thời hạn liên kết, dữ liệu trong log và độ trễ thu hồi. Ghi rõ các con số là đề xuất cần được chấp nhận theo rủi ro.
4. Nêu ít nhất một tương tác với hiệu năng hoặc trải nghiệm người dùng, rồi ghi quyết định và điều kiện kiểm chứng.
5. Viết ca được phép, ca bị từ chối và ca kiểm tra sau thu hồi; xác định bằng chứng cần thu cho từng yêu cầu.

Một hướng lập luận tốt sẽ làm rõ liên kết là phương tiện mang quyền tải hay chỉ là tham chiếu đến tài nguyên còn phải kiểm tra quyền. Hai thiết kế này có rủi ro khác nhau khi liên kết bị chuyển tiếp. Không thể quyết định tiêu chí kiểm thử chỉ từ việc URL có khó đoán hay không.

Sau bài học, người học cần có khả năng giải thích bảo mật như một tính chất xuyên suốt hệ thống; viết được yêu cầu có phạm vi, điều kiện, phản ứng và tiêu chí kiểm chứng; đồng thời nối được yêu cầu đó với rủi ro, quyết định kiến trúc và bằng chứng trong vòng đời phát triển.
