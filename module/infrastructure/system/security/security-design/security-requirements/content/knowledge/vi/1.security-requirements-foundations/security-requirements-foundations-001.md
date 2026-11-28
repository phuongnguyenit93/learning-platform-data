# Security requirement là gì

## 1. Từ mong muốn “hệ thống an toàn” đến một yêu cầu cụ thể

Một nhóm phát triển có thể cùng đồng ý rằng “ứng dụng phải bảo mật”, nhưng mỗi người lại hiểu câu đó khác nhau. Lập trình viên nghĩ đến mã hóa, người vận hành nghĩ đến giám sát, người phụ trách nghiệp vụ nghĩ đến việc khách hàng không nhìn thấy dữ liệu của nhau. Nếu không làm rõ, nhóm có thể triển khai nhiều biện pháp bảo vệ mà vẫn bỏ sót rủi ro quan trọng.

**Security requirement — yêu cầu bảo mật — là phát biểu về điều kiện hoặc hành vi mà hệ thống, thành phần hay quy trình phải đáp ứng để bảo vệ tài sản trước những rủi ro xác định.** Một yêu cầu dùng được trong phát triển phần mềm cần có phạm vi rõ ràng và bằng chứng để xác định đã đáp ứng hay chưa.

Ví dụ, “dữ liệu khách hàng phải an toàn” mới là một mong muốn. Một yêu cầu cụ thể hơn là:

> Với mọi yêu cầu đọc hồ sơ qua API, hệ thống phải kiểm tra danh tính đã xác thực và quyền đọc của chủ thể đối với đúng hồ sơ được yêu cầu. Khi không có quyền, hệ thống phải từ chối và không trả về nội dung hồ sơ.

Phát biểu thứ hai cho biết đối tượng cần bảo vệ, điểm áp dụng, hành vi mong đợi và điều phải xảy ra khi điều kiện truy cập không được thỏa mãn. Nhóm phát triển có thể thiết kế cơ chế thực hiện; người kiểm thử có thể tạo tài khoản, hồ sơ và tình huống từ chối để thu thập bằng chứng.

Bài học này thuộc phần nền tảng yêu cầu bảo mật: chuyển mục tiêu an toàn thông tin và kết quả mô hình đe dọa thành những cam kết cụ thể, đo được và có thể kiểm chứng, rồi liên kết chúng với thiết kế và kiểm thử trong vòng đời phát triển.

## 2. Yêu cầu bảo mật bảo vệ điều gì?

Yêu cầu bảo mật phải gắn với **tài sản cần bảo vệ**. Tài sản có thể là dữ liệu, chức năng nghiệp vụ, tài khoản, khóa bí mật, bằng chứng giao dịch hoặc khả năng cung cấp dịch vụ. “Có một cơ chế bảo mật” không phải đích đến; đích đến là bảo vệ tài sản ở mức mà tổ chức đã chấp nhận.

Ba thuộc tính thường gặp là:

| Thuộc tính | Ý nghĩa trong hệ thống | Ví dụ yêu cầu |
| --- | --- | --- |
| Bí mật — confidentiality | Thông tin chỉ được tiết lộ cho chủ thể được phép | Người dùng không được đọc hồ sơ của người khác nếu không có quyền được cấp rõ ràng. |
| Toàn vẹn — integrity | Dữ liệu và hành vi chỉ được thay đổi theo quyền và quy tắc hợp lệ | Chỉ người có quyền chấm điểm mới được sửa điểm; hệ thống phải lưu dấu vết của lần sửa. |
| Sẵn sàng — availability | Dịch vụ và dữ liệu có thể được sử dụng theo nhu cầu đã xác định | Dữ liệu đăng ký học phải được khôi phục trong thời gian phục hồi đã được nghiệp vụ chấp thuận. |

Tùy tài sản và bối cảnh, còn cần tính xác thực, khả năng quy trách nhiệm, quyền riêng tư hoặc khả năng phục hồi. Chúng có liên quan nhưng không tự động thay thế nhau. Một bản sao lưu giúp phục hồi dữ liệu, nhưng chưa bảo đảm người truy cập bản sao lưu có quyền đọc dữ liệu đó. Một tài khoản đã đăng nhập đúng cũng chưa chắc có quyền sửa mọi tài nguyên.

**Phạm vi của yêu cầu không chỉ là màn hình hoặc API chính.** Dữ liệu có thể đi qua tác vụ nền, bộ nhớ đệm, tệp xuất, log, bản sao lưu và dịch vụ tích hợp. Nếu tài sản được bảo vệ xuất hiện ở những nơi này, nhóm phải xác định yêu cầu áp dụng đến đâu, thay vì mặc định cơ chế ở API đã bao phủ tất cả.

## 3. Phân biệt mục tiêu, rủi ro, yêu cầu, thiết kế và kiểm thử

Các khái niệm sau thường xuất hiện trong cùng một cuộc thảo luận nhưng trả lời những câu hỏi khác nhau.

| Khái niệm | Câu hỏi chính | Ví dụ với bảng điểm |
| --- | --- | --- |
| Mục tiêu bảo mật | Ta muốn bảo vệ điều gì? | Bảo vệ tính bí mật của điểm cá nhân. |
| Đe dọa | Hành vi hay sự kiện nào có thể gây hại? | Học viên thay mã hồ sơ trong URL để đọc điểm của bạn học. |
| Rủi ro | Tình huống có thể xảy ra với tác động và khả năng nào? | API thiếu kiểm tra quyền trên từng hồ sơ dẫn đến lộ bảng điểm của nhiều học viên. |
| Yêu cầu bảo mật | Hệ thống phải bảo đảm điều gì? | Mỗi lần đọc bảng điểm phải kiểm tra quyền của chủ thể đối với đúng học viên được yêu cầu. |
| Thiết kế hoặc biện pháp kiểm soát | Ta thực hiện yêu cầu bằng cách nào? | Dùng lớp kiểm tra quyền phía máy chủ, lấy chủ thể từ phiên đăng nhập đã xác thực. |
| Tiêu chí chấp nhận và kiểm thử | Dựa vào đâu để kết luận yêu cầu đã đạt? | Tài khoản A gọi API với mã học viên B; hệ thống từ chối và không trả dữ liệu của B. |

Một **lỗ hổng** là điểm yếu có thể bị khai thác, chẳng hạn nhánh xử lý xuất bảng điểm bỏ qua kiểm tra quyền. Nó khác với yêu cầu: yêu cầu mô tả trạng thái cần đạt, còn lỗ hổng mô tả một điểm yếu trong trạng thái thực tế.

Một **chính sách** đặt ra quy tắc ở phạm vi tổ chức, chẳng hạn “truy cập dữ liệu học viên phải theo nhu cầu công việc”. Chính sách này cần được phân rã thành yêu cầu cho từng luồng và từng loại dữ liệu. Việc ghi “tuân thủ chính sách nội bộ” có thể xác định nguồn ràng buộc, nhưng chưa đủ cho người triển khai biết chính xác phải làm gì.

Một **user story** mô tả nhu cầu của người dùng cũng có thể chứa yêu cầu bảo mật trong tiêu chí chấp nhận. Ví dụ: “Là học viên, tôi muốn xem điểm của mình” cần được bổ sung điều kiện ai được xem, khi nào bị từ chối và dữ liệu nào được trả về. Không phải mọi yêu cầu bảo mật đều cần trở thành một user story riêng.

## 4. Đặc điểm của một yêu cầu bảo mật có thể sử dụng

### 4.1. Có đối tượng, phạm vi và điều kiện áp dụng

“Kiểm tra quyền truy cập” thiếu thông tin về việc kiểm tra ở đâu và đối với cái gì. Phát biểu tốt hơn cần chỉ rõ chủ thể, hành động, tài nguyên và bối cảnh liên quan.

Ví dụ:

> Khi học viên yêu cầu tải tệp bài nộp, hệ thống phải kiểm tra quyền tải của học viên đối với bài nộp đó trước khi cung cấp nội dung hoặc đường dẫn tải có thể sử dụng.

Điều kiện “trước khi cung cấp nội dung hoặc đường dẫn tải” giúp tránh một cách hiểu sai: API kiểm tra quyền nhưng lại phát ra một đường dẫn công khai cho phép bỏ qua kiểm tra sau đó.

### 4.2. Có thể xác minh bằng bằng chứng

“Đo được” không có nghĩa mọi yêu cầu đều phải có một con số. Điều kiện “tài khoản không có quyền không được nhận nội dung hồ sơ” có kết quả đạt hoặc không đạt. Ngược lại, “hệ thống phải có bảo mật cao” không cho biết bằng chứng nào là đủ.

Một số yêu cầu cần ngưỡng định lượng, ví dụ thời gian hết hiệu lực của phiên, thời gian phục hồi hay mức mất dữ liệu tối đa. Những ngưỡng này phải có căn cứ từ nhu cầu nghiệp vụ, phân tích rủi ro, kiến trúc và ràng buộc vận hành. Không nên sao chép một con số từ ví dụ rồi xem đó là chuẩn chung.

Cách xác minh có thể là kiểm thử hành vi, kiểm tra cấu hình, xem xét thiết kế hoặc diễn tập vận hành. Kiểm thử đơn lẻ không chứng minh toàn bộ hệ thống an toàn; nó cung cấp bằng chứng cho những điều kiện đã được xác định trong phạm vi kiểm tra.

### 4.3. Rõ cách xử lý khi điều kiện không được đáp ứng

Yêu cầu cần nói cả hành vi thành công lẫn hành vi khi không có quyền, thiếu thông tin tin cậy hoặc không thể xác định quyền.

Ví dụ:

> Nếu không xác định được quyền truy cập hồ sơ, hệ thống phải từ chối yêu cầu và không gửi dữ liệu hồ sơ cho bên gọi.

Với chức năng nhạy cảm, không thể chỉ quy định “khi thành công thì ghi log” mà bỏ qua chuyện gì xảy ra khi ghi log thất bại. Nhóm cần quyết định rõ giao dịch có được tiếp tục hay không, bằng chứng được lưu ở đâu và người vận hành được thông báo như thế nào. Quyết định cụ thể phụ thuộc hậu quả nghiệp vụ; không có một cách xử lý duy nhất phù hợp cho mọi sự kiện.

### 4.4. Đủ tập trung để kiểm tra và thay đổi

Một câu như “hệ thống phải xác thực, phân quyền, mã hóa, ghi log và sao lưu an toàn” chứa quá nhiều cam kết. Khi có lỗi, rất khó biết phần nào chưa đạt và ai chịu trách nhiệm.

Nên tách thành các yêu cầu có mã riêng. Các yêu cầu có thể tham chiếu một quy tắc chung để tránh mâu thuẫn, nhưng mỗi yêu cầu vẫn cần có mục đích và bằng chứng xác minh đủ rõ.

### 4.5. Khả thi và truy vết được

Một yêu cầu phải có khả năng thực hiện trong bối cảnh đã chọn, được bên liên quan thống nhất và có đường liên kết về lý do tồn tại. Yêu cầu không khả thi cần được thương lượng lại cùng rủi ro còn lại, thay vì âm thầm bỏ qua khi triển khai.

Truy vết giúp trả lời hai hướng: “Rủi ro này đã được xử lý bởi yêu cầu nào?” và “Yêu cầu này tồn tại vì tài sản, rủi ro hay ràng buộc nào?”. Nếu không trả lời được cả hai, nhóm dễ bỏ sót rủi ro hoặc duy trì những kiểm soát không còn phù hợp.

## 5. Cấu trúc mô tả một yêu cầu

Có thể bắt đầu bằng mẫu câu:

> Trong **[phạm vi/điều kiện]**, **[hệ thống hoặc thành phần]** phải **[hành vi quan sát được]** đối với **[tài sản/chủ thể]**, với **[giới hạn hoặc kết quả]**.

Sau đó bổ sung thông tin quản lý và xác minh. Không bắt buộc mọi thông tin phải nằm trong cùng một câu.

| Thành phần | Nội dung cần làm rõ |
| --- | --- |
| Mã yêu cầu | Định danh ổn định để tham chiếu trong thiết kế, công việc và kiểm thử. |
| Phát biểu | Hệ thống phải thực hiện hoặc ngăn chặn hành vi gì. |
| Phạm vi | Luồng, tài nguyên, giao diện và điều kiện áp dụng. |
| Nguồn và lý do | Tài sản, rủi ro, mục tiêu hoặc ràng buộc đã dẫn đến yêu cầu. |
| Tiêu chí chấp nhận | Những kết quả quan sát được để quyết định đạt hay chưa đạt. |
| Phương pháp xác minh | Kiểm thử, kiểm tra cấu hình, xem xét thiết kế hay diễn tập. |
| Liên kết và trách nhiệm | Thành phần thiết kế, người phụ trách và nơi lưu bằng chứng. |

Ví dụ một bản ghi yêu cầu:

```text
Mã: SR-GRADE-READ-01
Tên: Giới hạn quyền đọc bảng điểm của học viên

Phát biểu:
Khi chủ thể có vai trò học viên đọc bảng điểm qua API dành cho học viên,
hệ thống phải chỉ cho phép đọc bảng điểm gắn với hồ sơ học viên của
chủ thể đó. Hệ thống phải từ chối yêu cầu đọc bảng điểm của học viên khác
và không trả nội dung bảng điểm trong phản hồi bị từ chối.

Phạm vi:
API đọc bảng điểm dạng JSON và API xuất bảng điểm thành tệp dành cho học viên.
Quyền truy cập của giảng viên và quản trị viên được đặc tả bằng yêu cầu riêng.

Lý do:
Ngăn học viên thay mã đối tượng để đọc điểm của người khác.

Tiêu chí chấp nhận:
- Học viên A được đọc bảng điểm của A trong trạng thái tài khoản hợp lệ.
- Học viên A không nhận được bảng điểm của B khi thay mã đối tượng.
- Quy tắc trên áp dụng cho cả phản hồi JSON và luồng xuất tệp.

Xác minh:
Kiểm thử tích hợp qua từng API trong phạm vi, với hai học viên có dữ liệu
riêng và các trường hợp được phép, bị từ chối.
```

Phát biểu trên chưa quyết định lớp Java nào hay thư viện nào sẽ được dùng. Tuy nhiên, nó đã tạo ra nghĩa vụ thiết kế rõ ràng: kiểm tra phải diễn ra ở ranh giới tin cậy phía máy chủ và bao phủ các đường truy cập đã nêu. Việc chỉ ẩn nút trên giao diện không đáp ứng yêu cầu này.

## 6. Chuyển mục tiêu và mô hình đe dọa thành yêu cầu

Một quy trình thực tế có thể bắt đầu với sáu bước sau.

1. **Xác định tài sản và hành vi nghiệp vụ.** Ai tạo, đọc, sửa hoặc xóa dữ liệu? Hệ thống nào giữ dữ liệu? Khi tài sản bị lộ, bị sửa sai hoặc không sử dụng được thì hậu quả là gì?
2. **Làm rõ chủ thể và ranh giới tin cậy.** Dữ liệu nào đến từ trình duyệt hoặc bên ngoài? Thành phần nào thực sự xác minh danh tính và quyền? Luồng nào đi sang một dịch vụ khác?
3. **Mô tả kịch bản đe dọa.** Viết hành vi cụ thể, chẳng hạn học viên thay mã bài nộp, kẻ lấy được token tiếp tục sử dụng token sau khi bị thu hồi, hoặc nhân viên xuất quá nhiều dữ liệu.
4. **Đánh giá và ưu tiên rủi ro.** Xem tác động và khả năng xảy ra trong bối cảnh thực tế. Không chỉ chọn yêu cầu vì chúng dễ triển khai hoặc quen thuộc.
5. **Đặc tả hành vi phải có.** Với rủi ro được chọn để giảm thiểu, viết yêu cầu có phạm vi, điều kiện và kết quả quan sát được. Một kịch bản có thể cần nhiều yêu cầu phối hợp.
6. **Gắn thiết kế và bằng chứng.** Xác định thành phần chịu trách nhiệm, cách xác minh và điều kiện xem là đạt. Ghi nhận các giả định, phụ thuộc và rủi ro còn lại.

Chuỗi liên kết có thể biểu diễn như sau:

```text
Tài sản + mục tiêu bảo vệ
          |
          v
Kịch bản đe dọa + đánh giá rủi ro
          |
          v
Yêu cầu bảo mật
          |
          v
Thiết kế + triển khai + cấu hình
          |
          v
Tiêu chí chấp nhận + bằng chứng xác minh
```

Đây không phải chuỗi chỉ đi một chiều. Khi kiểm thử phát hiện một đường tải tệp chưa được mô hình hóa, nhóm cần cập nhật phạm vi đe dọa và yêu cầu. Khi kiến trúc chuyển từ lưu tệp nội bộ sang kho lưu trữ ngoài, cần xem lại nơi thực thi quyền và vòng đời đường dẫn tải.

Không phải mọi rủi ro đều phải được giải quyết bằng một yêu cầu kỹ thuật mới. Tổ chức có thể tránh một chức năng, thay đổi quy trình, chuyển giao một phần trách nhiệm theo thỏa thuận hoặc chấp nhận rủi ro còn lại bằng quyết định có trách nhiệm. Dù chọn cách nào, quyết định cần được ghi nhận; bỏ sót và chấp nhận rủi ro là hai việc khác nhau.

## 7. Ví dụ xuyên suốt: nền tảng học tập

Giả sử một nền tảng có các chức năng đăng nhập, xem bảng điểm, nộp bài và quản lý lớp. Ba nhóm người dùng là học viên, giảng viên và quản trị viên. Dữ liệu đáng chú ý gồm thông tin tài khoản, bài nộp, bảng điểm và dấu vết thay đổi.

Bảng dưới minh họa cách đi từ rủi ro đến yêu cầu. Những yêu cầu này là ví dụ trong phạm vi đã mô tả, không phải một danh mục đủ để bảo vệ mọi nền tảng học tập.

| Rủi ro hoặc nhu cầu bảo vệ | Yêu cầu minh họa | Bằng chứng phù hợp |
| --- | --- | --- |
| Kẻ chưa đăng nhập gọi API đọc dữ liệu riêng | Mỗi API đọc hồ sơ và bảng điểm riêng phải yêu cầu một ngữ cảnh xác thực còn hiệu lực; yêu cầu không thỏa mãn phải bị từ chối trước khi trả dữ liệu. | Kiểm thử không có thông tin xác thực, thông tin hết hiệu lực và thông tin hợp lệ. |
| Học viên đổi mã hồ sơ để đọc điểm người khác | API dành cho học viên phải kiểm tra quyền đọc trên đúng hồ sơ được yêu cầu ở mỗi lần truy cập. | Hai tài khoản độc lập; kiểm thử thay mã đối tượng trên cả luồng JSON và xuất tệp. |
| Nhân viên bị thu hồi quyền vẫn tiếp tục sửa điểm | Sau khi thao tác thu hồi quyền hoàn tất, hệ thống phải áp dụng quyền mới cho mỗi yêu cầu sửa điểm được bắt đầu sau thời điểm đó. | Thu hồi quyền khi phiên vẫn tồn tại, sau đó gửi yêu cầu sửa mới qua từng đường truy cập trong phạm vi. |
| Dữ liệu đăng nhập bị lộ qua nhật ký ứng dụng | Các sự kiện ghi vào log ứng dụng phải loại bỏ mật khẩu và token truy cập còn nguyên giá trị trước khi gửi tới nơi lưu log. | Dùng dữ liệu thử có dấu nhận diện; kiểm tra log của cả nhánh thành công và nhánh lỗi trong các luồng đã xác định. |
| Không xác định được ai sửa điểm | Mỗi lần sửa điểm thành công phải tạo bản ghi audit gắn với người thực hiện, đối tượng bị sửa, thời điểm, hành động và mã liên kết giao dịch. | Sửa điểm rồi đối chiếu bản ghi audit; kiểm tra quyền truy cập và khả năng bảo vệ bản ghi khỏi sửa trái phép. |
| Sự cố làm mất dữ liệu đăng ký học | Dữ liệu đăng ký học phải có bản sao có thể phục hồi, đáp ứng RPO và RTO được nghiệp vụ phê duyệt cho kịch bản sự cố đã chọn. | Diễn tập khôi phục, kiểm tra dữ liệu và đo thời gian phục hồi theo kịch bản. |

### 7.1. Xác thực và phân quyền là hai nghĩa vụ khác nhau

**Xác thực** trả lời “chủ thể này là ai hoặc đang chứng minh quyền kiểm soát thông tin xác thực nào?”. **Phân quyền** trả lời “chủ thể đó có được thực hiện hành động này trên tài nguyên này không?”.

Kiểm thử “đăng nhập thành công” không đủ để kết luận yêu cầu phân quyền đã đạt. Một học viên đăng nhập hợp lệ vẫn phải bị từ chối khi yêu cầu sửa bảng điểm. Vì vậy, yêu cầu nên mô tả rõ cả danh tính hợp lệ và quyền cần có đối với hành động, đối tượng cụ thể.

Trong thực tế, phiên và token còn có vòng đời: tạo, sử dụng, hết hiệu lực, đăng xuất, thu hồi. Nếu rủi ro liên quan đến phiên còn dùng được sau khi thu hồi quyền, đặc tả phải làm rõ thời điểm áp dụng. Trường hợp yêu cầu đang xử lý trước thời điểm thu hồi cũng cần một quyết định riêng khi nó có thể ảnh hưởng đến nghiệp vụ.

### 7.2. Yêu cầu bảo vệ dữ liệu phải theo luồng dữ liệu

Câu “mã hóa dữ liệu” chưa xác định dữ liệu nào, ở đâu và cần bảo vệ trước ai. Cần phân biệt dữ liệu trên đường truyền, dữ liệu lưu trữ, bản sao lưu và dữ liệu xuất ra ngoài.

Ví dụ, đối với luồng tải bảng điểm qua mạng, nhóm có thể yêu cầu dữ liệu chỉ được truyền qua kênh có mã hóa và xác thực đầu cuối phù hợp với kiến trúc. Nếu TLS kết thúc ở một thành phần trung gian, cần làm rõ các chặng tiếp theo. Đối với bản sao lưu, ngoài việc mã hóa còn cần xác định ai có quyền đọc và ai có quyền sử dụng khóa giải mã.

Trong bài nền tảng, điểm quan trọng là cách đặt phạm vi và kết quả bảo vệ. Thuật toán, cấu hình và cách quản lý khóa cụ thể phải được lựa chọn và kiểm chứng ở thiết kế tương ứng; chỉ ghi tên thuật toán chưa đủ tạo thành một yêu cầu hoàn chỉnh.

### 7.3. Logging và audit cũng có yêu cầu bảo mật riêng

Log phục vụ chẩn đoán và audit phục vụ truy vết hành động có thể có nhu cầu khác nhau. Một hệ thống có nhiều log chưa chắc đã có bằng chứng cần thiết để điều tra việc sửa điểm.

Yêu cầu cần xác định loại sự kiện phải ghi, dữ liệu được ghi, dữ liệu phải loại bỏ, ai được đọc, ai được quản trị, thời gian lưu và cách xử lý khi ghi thất bại. Khi cần liên kết sự kiện giữa nhiều dịch vụ, mã liên kết phải có quy tắc sử dụng thống nhất. Thời gian sự kiện cũng cần có ý nghĩa đủ rõ để đối chiếu.

Không nên ghi toàn bộ nội dung yêu cầu HTTP chỉ để “đủ dấu vết”, vì cách làm đó có thể đưa mật khẩu, token hoặc dữ liệu cá nhân vào log. Ngược lại, cấm mọi thông tin ngữ cảnh có thể làm mất khả năng điều tra. Yêu cầu cần cân bằng hai mục tiêu bằng cách nêu rõ tập dữ liệu phù hợp.

### 7.4. Phục hồi cần có ngưỡng và diễn tập

Hai khái niệm thường dùng là:

- **RPO — Recovery Point Objective:** mục tiêu giới hạn khoảng dữ liệu có thể mất, xét theo thời gian giữa điểm dữ liệu khôi phục được và thời điểm sự cố.
- **RTO — Recovery Time Objective:** mục tiêu giới hạn thời gian phục hồi dịch vụ theo mốc bắt đầu và kết thúc đã được thống nhất.

Ví dụ giả định: nghiệp vụ chấp nhận RPO tối đa 15 phút và RTO tối đa 2 giờ cho dữ liệu đăng ký học trong một kịch bản mất cơ sở dữ liệu chính. Khi đó, yêu cầu phải chỉ rõ kịch bản, tập dữ liệu, mốc đo và tiêu chí dữ liệu sau phục hồi. Hai con số này chỉ phục vụ ví dụ; chúng không phải khuyến nghị chung.

Có một tệp sao lưu hoặc một lịch sao lưu thành công chưa chứng minh đáp ứng yêu cầu. Bằng chứng cần đến từ khả năng khôi phục dữ liệu sử dụng được trong điều kiện đã quy định. Nếu mất cả khóa giải mã hoặc quyền truy cập bản sao lưu trong cùng sự cố, kế hoạch phục hồi cũng cần tính đến các phụ thuộc đó.

## 8. Tiêu chí chấp nhận: làm rõ thế nào là đạt

Tiêu chí chấp nhận cụ thể hóa yêu cầu thành điều kiện có thể quan sát. Một yêu cầu có thể cần nhiều tiêu chí, gồm trường hợp được phép, bị từ chối và các ranh giới có ý nghĩa.

Với yêu cầu `SR-GRADE-READ-01`, có thể viết theo dạng Given–When–Then:

```gherkin
Feature: Giới hạn quyền đọc bảng điểm của học viên

  Scenario: Học viên đọc bảng điểm của chính mình
    Given học viên A có phiên hợp lệ và có bảng điểm A
    When A gọi API dành cho học viên để đọc bảng điểm A
    Then hệ thống trả về bảng điểm A theo phạm vi dữ liệu được phép

  Scenario: Học viên thay mã để đọc bảng điểm người khác
    Given học viên A có phiên hợp lệ
    And bảng điểm B thuộc về một học viên khác
    When A gọi API dành cho học viên để đọc bảng điểm B
    Then hệ thống từ chối yêu cầu
    And phản hồi không chứa nội dung bảng điểm B

  Scenario: Học viên xuất bảng điểm của người khác thành tệp
    Given học viên A có phiên hợp lệ
    And bảng điểm B thuộc về một học viên khác
    When A yêu cầu xuất bảng điểm B qua API dành cho học viên
    Then hệ thống từ chối yêu cầu
    And không cung cấp tệp hoặc đường dẫn tải sử dụng được của bảng điểm B
```

Đây là mô tả hành vi kiểm thử, chưa phải một bộ kiểm thử có thể chạy ngay. Khi triển khai, nhóm còn cần dữ liệu thử, cách gọi API, kết quả mong đợi của giao thức và cách quan sát các đầu ra liên quan.

Đừng biến tiêu chí chấp nhận thành một bản sao của giải pháp duy nhất. “Hàm `checkPermission` được gọi” chứng minh một chi tiết triển khai, nhưng chưa chứng minh người không có quyền không nhận dữ liệu. Kiểm tra nội bộ vẫn có thể hữu ích, song bằng chứng cần hướng tới thuộc tính bảo vệ đã yêu cầu.

## 9. Yêu cầu bảo mật có phải chỉ là yêu cầu phi chức năng?

Yêu cầu bảo mật thường được xếp vào nhóm yêu cầu chất lượng hoặc yêu cầu phi chức năng, nhưng cách phân loại đó không bao quát mọi trường hợp.

- “Người quản trị có thể thu hồi phiên của tài khoản bị xâm nhập” mô tả một khả năng chức năng.
- “Mọi yêu cầu đọc hồ sơ đều phải kiểm tra quyền theo đối tượng” là ràng buộc áp dụng xuyên nhiều chức năng.
- “Mật khẩu không được xuất hiện trong log ứng dụng” là ràng buộc xử lý dữ liệu.
- “Khôi phục trong RTO đã thống nhất” liên quan đến chất lượng vận hành và khả năng phục hồi.

Không cần tranh luận nhãn phân loại trước khi viết được yêu cầu. Điều quan trọng hơn là xác định nghĩa vụ của hệ thống, phạm vi và bằng chứng đáp ứng. Nhãn “phi chức năng” không được dùng làm lý do để trì hoãn bảo mật đến cuối dự án.

Cũng không phải lúc nào yêu cầu chỉ nên nói “cần đạt gì” và tuyệt đối tránh “làm bằng cách nào”. Có trường hợp hợp đồng hoặc nền tảng tích hợp bắt buộc một giao thức, một cơ chế hay một vùng lưu trữ cụ thể. Khi đó, hãy ghi rõ đây là ràng buộc thiết kế bắt buộc và nguồn của nó, thay vì trình bày như một lựa chọn tùy ý.

## 10. Liên kết yêu cầu với kiến trúc và vòng đời phát triển

Yêu cầu bảo mật phải xuất hiện trước khi các quyết định thiết kế quan trọng đóng lại, rồi tiếp tục được duy trì khi hệ thống thay đổi.

| Giai đoạn | Vai trò của yêu cầu bảo mật |
| --- | --- |
| Khám phá và phân tích | Làm rõ tài sản, tác động, chủ thể và điều kiện cần bảo vệ. |
| Thiết kế | Xác định ranh giới tin cậy, thành phần thực thi và cách đáp ứng yêu cầu. |
| Triển khai | Chuyển yêu cầu thành mã, cấu hình, xử lý lỗi và quy trình cụ thể. |
| Kiểm thử | Tạo bằng chứng cho từng tiêu chí chấp nhận và đường truy cập trong phạm vi. |
| Phát hành và vận hành | Kiểm tra cấu hình thực tế, theo dõi hiệu lực kiểm soát và thực hiện diễn tập cần thiết. |
| Thay đổi và xử lý sự cố | Cập nhật yêu cầu khi tài sản, kiến trúc, đe dọa hoặc giả định thay đổi. |

Ví dụ ma trận truy vết tối giản:

| Rủi ro | Yêu cầu | Nơi thực hiện trong thiết kế | Bằng chứng |
| --- | --- | --- | --- |
| R-01: Đọc điểm bằng cách đổi mã học viên | SR-GRADE-READ-01 | Kiểm tra quyền phía máy chủ trên API đọc và xuất bảng điểm | Kết quả kiểm thử truy cập chéo giữa hai tài khoản trên cả hai luồng |
| R-02: Sửa điểm sau khi bị thu hồi quyền | SR-GRADE-WRITE-02 | Cơ chế áp dụng thay đổi quyền trước khi chấp nhận yêu cầu sửa mới | Kết quả kiểm thử thu hồi quyền khi phiên còn tồn tại |
| R-03: Mất dữ liệu đăng ký học | SR-RECOVERY-01 | Luồng sao lưu, quản lý quyền và quy trình khôi phục | Biên bản diễn tập, thời gian đo và kết quả đối soát dữ liệu |

Một yêu cầu có thể được thực hiện bởi nhiều thành phần; một thành phần cũng có thể phục vụ nhiều yêu cầu. Ma trận giúp phát hiện chỗ chưa có người chịu trách nhiệm, nhưng việc có đủ ô trong bảng không tự chứng minh yêu cầu đã được thực hiện đúng.

Khi cần thay đổi, phải phân biệt **sửa yêu cầu** với **báo lỗi triển khai**. Nếu yêu cầu cấm truy cập chéo nhưng API vẫn trả dữ liệu, đó là lỗi triển khai. Nếu xuất hiện một loại chia sẻ bảng điểm mới được nghiệp vụ cho phép, nhóm cần cập nhật mô hình quyền và yêu cầu liên quan, rồi bổ sung bằng chứng phù hợp.

## 11. Những cách viết thường gây hiểu nhầm

| Cách viết chưa đủ rõ | Vấn đề | Hướng làm rõ |
| --- | --- | --- |
| “Ứng dụng phải bảo mật.” | Không có tài sản, phạm vi hoặc kết quả kiểm tra. | Nêu hành vi phải được bảo vệ trên một tài nguyên và điều kiện cụ thể. |
| “Dùng JWT để bảo đảm an toàn.” | Chọn định dạng token chưa xác định nghĩa vụ xác thực hay phân quyền. | Đặc tả cách chấp nhận, hết hiệu lực, thu hồi và sử dụng ngữ cảnh danh tính; sau đó đánh giá thiết kế token phù hợp. |
| “Chỉ admin được thao tác.” | Không rõ thao tác nào và admin trong phạm vi nào. | Nêu quyền, hành động, loại tài nguyên và điều kiện giới hạn. |
| “Mã hóa mọi dữ liệu.” | Không rõ dữ liệu và trạng thái cần bảo vệ, đối tượng được phép giải mã. | Xác định dữ liệu, luồng truyền hoặc nơi lưu, quyền dùng khóa và cách xác minh. |
| “Ghi log tất cả.” | Có thể lộ bí mật và vẫn thiếu sự kiện có giá trị điều tra. | Chỉ rõ sự kiện, trường dữ liệu, dữ liệu loại bỏ, quyền đọc và quy tắc lưu giữ. |
| “Sao lưu mỗi ngày.” | Chỉ mô tả một hoạt động, chưa chứng minh khả năng phục hồi cần có. | Gắn lịch sao lưu với RPO, RTO, tập dữ liệu và diễn tập khôi phục. |
| “Không có lỗ hổng.” | Không xác định được phạm vi hoặc bằng chứng đủ để chứng minh tuyệt đối. | Viết các yêu cầu cụ thể theo rủi ro, xác định phương pháp đánh giá và quản lý phát hiện còn lại. |

Các câu ngắn trên có thể xuất hiện trong ghi chú ban đầu. Vấn đề xảy ra khi nhóm dùng chúng như yêu cầu đã sẵn sàng để triển khai và nghiệm thu mà chưa làm rõ phần còn thiếu.

## 12. Tự kiểm tra mức độ sẵn sàng của một yêu cầu

Trước khi đưa yêu cầu vào công việc phát triển, người viết có thể trả lời các câu hỏi sau:

1. Tài sản hoặc thuộc tính nào đang được bảo vệ?
2. Rủi ro, mục tiêu hoặc ràng buộc nào là lý do của yêu cầu?
3. Chủ thể, hành động, tài nguyên và điều kiện áp dụng đã đủ rõ chưa?
4. Người triển khai có biết hệ thống phải làm gì khi điều kiện bảo mật không được đáp ứng không?
5. Có thể đưa ra bằng chứng đạt hoặc không đạt mà không dựa vào nhận xét “có vẻ an toàn” không?
6. Các ngưỡng định lượng đã có căn cứ và được bên liên quan thống nhất chưa?
7. Đã xác định các đường truy cập và thành phần chịu trách nhiệm trong phạm vi chưa?
8. Khi kiến trúc hoặc quyền nghiệp vụ thay đổi, có biết yêu cầu và bằng chứng nào phải xem lại không?

Nếu một câu trả lời còn thiếu, hãy bổ sung vào phát biểu, phạm vi hoặc tiêu chí chấp nhận tương ứng. Mục đích là làm cho cùng một cam kết được hiểu nhất quán giữa nghiệp vụ, phát triển, kiểm thử và vận hành.

## 13. Các ý chính cần nhớ

Security requirement biến mong muốn bảo vệ thành nghĩa vụ có thể triển khai và xác minh. Nó kết nối một tài sản và rủi ro cụ thể với hành vi hệ thống phải bảo đảm, đồng thời xác định điều kiện để đánh giá kết quả.

Một yêu cầu tốt nêu rõ phạm vi, có tiêu chí chấp nhận và truy vết được về lý do tồn tại. Thiết kế lựa chọn cách đáp ứng; kiểm thử và các hình thức xác minh khác cung cấp bằng chứng; vận hành duy trì hiệu lực trong môi trường thực tế.

Khi bắt đầu viết, có thể dùng câu hỏi: **“Trong tình huống nào, hệ thống phải bảo đảm điều gì cho tài sản nào, và ta dựa vào bằng chứng nào để biết đã đạt?”** Trả lời đủ câu hỏi đó là bước đầu để biến bảo mật thành một phần có thể quản lý của vòng đời phát triển.
