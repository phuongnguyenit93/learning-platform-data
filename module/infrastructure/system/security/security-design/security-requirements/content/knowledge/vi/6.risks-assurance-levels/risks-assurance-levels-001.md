# Risk là gì

## Mục tiêu bài học

Trong chương **Rủi ro và mức đảm bảo**, hiểu đúng risk là bước nối giữa mục tiêu an toàn thông tin, mô hình đe dọa và yêu cầu bảo mật. Nếu chỉ ghi “có nguy cơ bị tấn công”, nhóm phát triển chưa biết cần bảo vệ điều gì, ưu tiên ra sao hoặc kiểm chứng bằng cách nào.

Bài học tập trung vào rủi ro an toàn thông tin trong thiết kế hệ thống. Sau bài học, người học có thể:

- Giải thích rủi ro bằng mục tiêu, kịch bản, khả năng xảy ra và hậu quả.
- Phân biệt rủi ro với tài sản, đe dọa, điểm yếu, sự kiện và sự cố.
- Ghi một kịch bản rủi ro đủ cụ thể để phục vụ thiết kế yêu cầu.
- Phân biệt rủi ro trước kiểm soát, rủi ro còn lại và rủi ro mục tiêu.
- Liên kết rủi ro với yêu cầu, quyết định kiến trúc và bằng chứng kiểm chứng.

## 1. Risk là gì?

**Risk, hay rủi ro, là sự bất định có thể ảnh hưởng tới việc đạt mục tiêu.** Trong phạm vi an toàn thông tin của bài học, ta tập trung vào các kịch bản có thể gây hậu quả bất lợi cho dữ liệu, dịch vụ, con người hoặc hoạt động của tổ chức.

Một phát biểu rủi ro cần giúp trả lời ít nhất bốn câu hỏi:

1. Mục tiêu hoặc tài sản nào có thể bị ảnh hưởng?
2. Điều gì có thể xảy ra và trong điều kiện nào?
3. Khả năng xảy ra được đánh giá ra sao trong phạm vi thời gian đã chọn?
4. Nếu xảy ra, hậu quả là gì?

Ví dụ:

> Trong 12 tháng vận hành tới, người dùng đã đăng nhập có thể đọc hồ sơ của khách hàng khác nếu API chỉ kiểm tra trạng thái đăng nhập mà không kiểm tra quyền trên hồ sơ. Điều này có thể làm lộ thông tin cá nhân, gây chi phí xử lý sự cố và làm giảm niềm tin của khách hàng.

Phát biểu này có mục tiêu bảo vệ, chủ thể, hành vi, điều kiện và hậu quả. Nó cụ thể hơn câu “rủi ro lộ dữ liệu”, dù vẫn cần bổ sung phạm vi hồ sơ, bằng chứng về điểm yếu và tiêu chí đánh giá khả năng xảy ra.

Rủi ro không đòi hỏi hậu quả đã xảy ra. Khi đã xác nhận một sự kiện gây ảnh hưởng, tổ chức còn phải xử lý sự cố và đánh giá nguy cơ tiếp diễn hoặc tái diễn.

### 1.1. Vì sao cần mục tiêu?

Một sự kiện chỉ có ý nghĩa rủi ro khi liên hệ được với điều cần bảo vệ.

- Không đọc được một trang giới thiệu trong vài phút có thể có tác động nhỏ.
- Không đọc được hồ sơ cấp cứu trong cùng khoảng thời gian có thể có tác động khác.
- Một tài liệu công khai bị đọc không phải vi phạm bí mật, nhưng tài liệu đó bị thay nội dung có thể là vấn đề toàn vẹn.
- Một bản sao lưu còn nguyên vẫn chưa đáp ứng mục tiêu phục hồi nếu không còn khóa giải mã.

Do đó, không thể đánh giá rủi ro chỉ từ tên công nghệ, số lượng máy chủ hoặc việc một hệ thống “có dữ liệu”.

### 1.2. Bất định không đồng nghĩa với không biết gì

Nhóm thiết kế hiếm khi biết chính xác xác suất một cuộc tấn công sẽ thành công. Tuy vậy, vẫn có thể dùng bằng chứng để đánh giá:

- Hệ thống có tiếp xúc Internet không?
- Có cần tài khoản hoặc đặc quyền trước khi thực hiện hành vi không?
- Điểm yếu đã được tái hiện hay mới là giả thuyết?
- Kiểm soát nào đang hoạt động và đã được thử?
- Dữ liệu nào có thể bị tác động?
- Tổ chức mất bao lâu để phát hiện và hạn chế hậu quả?

Bản đánh giá tốt ghi cả kết luận lẫn độ tin cậy, giả định và thông tin còn thiếu. Một con số rất chi tiết nhưng thiếu cơ sở không làm bất định biến mất.

## 2. Phân biệt các khái niệm liên quan

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Mục tiêu | Điều gì cần được bảo đảm? | Chỉ người được cấp quyền mới đọc hồ sơ khách hàng |
| Tài sản | Điều gì có giá trị cần bảo vệ? | Hồ sơ, quyền truy cập, khóa giải mã, dịch vụ phục hồi |
| Nguồn đe dọa | Ai hoặc yếu tố nào có thể gây ảnh hưởng? | Người dùng ác ý, nhân viên nhầm thao tác, lỗi thiết bị |
| Đe dọa | Hành vi hoặc nguyên nhân tiềm tàng nào có thể gây hại? | Truy cập trái phép, xóa nhầm, gián đoạn hạ tầng |
| Điểm yếu | Điều kiện nào làm sự kiện dễ xảy ra hoặc hậu quả lớn hơn? | Thiếu kiểm tra quyền trên đối tượng, quyền xóa quá rộng |
| Sự kiện | Điều gì xảy ra có liên quan tới an toàn thông tin? | Một yêu cầu đọc hồ sơ khác phạm vi được gửi tới API |
| Sự cố | Sự kiện hoặc chuỗi sự kiện được xác định cần xử lý theo tiêu chí sự cố | Xác nhận hồ sơ đã bị cung cấp cho người không có quyền |
| Kiểm soát | Biện pháp nào thay đổi khả năng xảy ra hoặc hậu quả? | Kiểm tra quyền, giới hạn phạm vi, giám sát, phục hồi |
| Rủi ro | Kịch bản bất định nào có thể ảnh hưởng mục tiêu, với mức tác động nào? | Người dùng khai thác thiếu kiểm tra quyền để đọc hồ sơ khác |

### 2.1. Có đe dọa chưa đủ để mô tả rủi ro

“Có kẻ tấn công trên Internet” là nhận định về môi trường đe dọa. Nó chưa cho biết hệ thống nào bị ảnh hưởng, đường tấn công nào khả thi và hậu quả gì có thể xảy ra.

Cần nối đe dọa với phạm vi cụ thể. Chẳng hạn, nếu một API công khai có quyền truy cập dữ liệu nhạy cảm, cần xem cách danh tính người gọi được xác thực và ràng buộc với dữ liệu mà API trả về.

### 2.2. Có điểm yếu chưa đủ để kết luận mức rủi ro

“Thư viện có lỗi” là thông tin về một điều kiện kỹ thuật. Để đánh giá rủi ro cần biết:

- Thành phần bị ảnh hưởng có thực sự được triển khai không?
- Đường mã liên quan có thể được gọi trong cấu hình hiện tại không?
- Đối tượng nào có thể tiếp cận đường đó?
- Cần điều kiện hoặc quyền gì trước khi khai thác?
- Nếu khai thác được, tài sản nào bị ảnh hưởng?
- Kiểm soát hiện có có giới hạn được đường tấn công hoặc hậu quả không?

Không nên bỏ qua một điểm yếu chỉ vì chưa thấy sự cố. Cũng không nên mặc định mọi điểm yếu có cùng mức rủi ro ở mọi hệ thống.

### 2.3. Sự cố và rủi ro có quan hệ nhưng khác nhau

Ví dụ, một bản sao dữ liệu đã được chia sẻ nhầm là sự việc đã xảy ra. Đội xử lý cần thu hồi quyền, xác định phạm vi ảnh hưởng và thực hiện các hành động phù hợp.

Đồng thời, vẫn có các câu hỏi rủi ro:

- Người nhận có thể tiếp tục sử dụng bản đã tải về không?
- Cơ chế chia sẻ hiện tại có thể gây sự cố tương tự lần nữa không?
- Các tập dữ liệu khác có cùng điểm yếu không?
- Biện pháp xử lý đã đủ để giảm nguy cơ tiếp diễn chưa?

Không được kết luận “không còn rủi ro” chỉ vì đã đóng một phiếu xử lý sự cố.

## 3. Cấu trúc một kịch bản rủi ro

Có thể dùng mẫu:

> Trong phạm vi và khoảng thời gian xác định, một nguồn đe dọa có thể gây ra sự kiện qua điều kiện hoặc điểm yếu, làm ảnh hưởng tài sản hoặc mục tiêu và dẫn tới hậu quả.

Mẫu này là công cụ diễn đạt, không phải công thức tính toán. Một kịch bản đầy đủ thường có các thành phần sau:

| Thành phần | Nội dung cần ghi |
| --- | --- |
| Phạm vi | Dịch vụ, môi trường, dữ liệu, người dùng và ranh giới liên quan |
| Khoảng thời gian | Ví dụ giai đoạn ra mắt hoặc 12 tháng vận hành tới |
| Mục tiêu | Bí mật, toàn vẹn, sẵn sàng hoặc mục tiêu nghiệp vụ cụ thể |
| Nguồn đe dọa | Chủ thể ác ý, người dùng nhầm thao tác, sự cố hạ tầng hoặc nguyên nhân khác |
| Sự kiện | Hành vi hoặc diễn biến có thể làm sai mục tiêu |
| Điều kiện | Điểm yếu, quyền truy cập, phụ thuộc và giả định cần thiết |
| Hậu quả | Dữ liệu bị lộ, giao dịch sai, mất khả năng phục hồi hoặc tác động tiếp theo |
| Kiểm soát hiện có | Những biện pháp đang thực sự được triển khai |
| Đánh giá | Khả năng xảy ra, mức hậu quả, độ tin cậy và căn cứ |
| Người chịu trách nhiệm | Chủ thể quyết định cách xử lý và theo dõi rủi ro |

### 3.1. Ví dụ chưa đạt và ví dụ rõ hơn

**Chưa đạt:**

> Rủi ro: hacker đánh cắp dữ liệu.

Thiếu hệ thống, tài sản, đường tác động, điều kiện và phạm vi.

**Rõ hơn:**

> Trong dịch vụ hồ sơ khách hàng production, người dùng có tài khoản có thể thay mã hồ sơ trong yêu cầu đọc để truy cập hồ sơ thuộc tổ chức khác nếu dịch vụ chỉ kiểm tra đăng nhập. Việc này có thể làm lộ dữ liệu định danh và nội dung hồ sơ. Phạm vi đánh giá là các API đọc hồ sơ trong 12 tháng tới; khả năng truy cập chéo tổ chức cần được xác minh bằng kiểm thử phân quyền.

Phát biểu mới phân biệt điều đã biết với điều cần xác minh. Nó chưa tuyên bố điểm yếu tồn tại chắc chắn khi chưa có bằng chứng.

### 3.2. Kịch bản không cần luôn có kẻ tấn công

Ví dụ:

> Trong một lần vận hành khôi phục, nhân viên có thể xóa nhầm phiên bản khóa còn cần cho bản sao lưu nếu giao diện không hiển thị phụ thuộc và quyền xóa không được kiểm soát. Hậu quả là dữ liệu trong thời hạn lưu giữ không thể phục hồi khi hệ thống chính mất.

Nguồn gây ảnh hưởng ở đây là thao tác nhầm, không phải đối tượng ác ý. Mô hình đe dọa và yêu cầu bảo mật cần xét cả sai sót, hỏng hóc và phụ thuộc vận hành.

### 3.3. Chọn mức chi tiết có thể hành động

“Lộ mọi dữ liệu” thường quá rộng để giao trách nhiệm hoặc viết kiểm thử. “Một trường JSON thiếu thuộc tính” có thể quá hẹp nếu không chỉ ra hậu quả.

Mức phù hợp là một kịch bản có:

- Đường tác động và hậu quả đủ thống nhất.
- Một hoặc một nhóm chủ sở hữu có thể xử lý.
- Các kiểm soát và tiêu chí kiểm chứng xác định được.

Nếu một phát biểu chứa cả truy cập trái phép, mã độc, mất điện và xóa nhầm, nên tách thành các kịch bản có điều kiện và biện pháp xử lý riêng.

## 4. Khả năng xảy ra là gì?

**Khả năng xảy ra** diễn đạt mức có thể xuất hiện của sự kiện hoặc kịch bản trong phạm vi đánh giá. Nó phải gắn với điều kiện và khoảng thời gian; “cao” mà không có ngữ cảnh rất khó dùng.

Không nên chỉ hỏi “có thể bị tấn công không?”. Cần xem cả chuỗi điều kiện:

1. Nguồn đe dọa có thể tiếp cận hệ thống không?
2. Có khả năng hoặc cơ hội thực hiện hành vi không?
3. Điểm yếu có thể được tận dụng trong cấu hình hiện tại không?
4. Các kiểm soát có ngăn hoặc giới hạn thành công không?
5. Sự kiện có thể dẫn tới hậu quả đang đánh giá không?

### 4.1. Căn cứ thường dùng

| Nhóm căn cứ | Câu hỏi |
| --- | --- |
| Mức tiếp xúc | Giao diện công khai, nội bộ hay chỉ qua đường quản trị? |
| Điều kiện ban đầu | Cần tài khoản, quyền đặc biệt, truy cập mạng hay thao tác vật lý? |
| Độ khó | Cần phối hợp nhiều điều kiện hay có thể thực hiện bằng hành động đơn giản? |
| Khả năng của nguồn đe dọa | Có động cơ, thời gian, quyền hoặc năng lực phù hợp không? |
| Tính lặp lại | Hành vi có thể thử nhiều lần với chi phí thấp không? |
| Kiểm soát hiện có | Đã triển khai ở đúng đường xử lý và có bằng chứng hiệu lực chưa? |
| Dữ liệu vận hành | Có sự kiện liên quan, kết quả diễn tập hoặc kiểm thử nào hỗ trợ đánh giá? |

Không có log tấn công không chứng minh không có tấn công, nhất là khi hệ thống chưa ghi đủ sự kiện. Tương tự, một bản kiểm thử thành công cho thấy đường tác động khả thi trong điều kiện thử; nó không tự cung cấp xác suất chính xác trong một năm.

### 4.2. Ví dụ thang định tính

Một nhóm có thể dùng ba mức sau cho một phạm vi đánh giá đã thống nhất:

| Mức | Cách diễn giải minh họa |
| --- | --- |
| Thấp | Cần nhiều điều kiện hạn chế; các đường chính đã có kiểm soát được kiểm chứng; cơ hội tiếp cận ít |
| Trung bình | Có cơ hội tiếp cận và điều kiện khả thi, nhưng vẫn có rào cản hoặc thiếu bằng chứng về một số bước |
| Cao | Đường tác động dễ tiếp cận, điều kiện đơn giản hoặc đã tái hiện; kiểm soát quan trọng thiếu hay không hiệu lực |

Đây là thang minh họa, không phải chuẩn áp dụng chung. Tổ chức cần định nghĩa cách xử lý các trường hợp mâu thuẫn và ghi rõ căn cứ cho từng kết luận.

“Chưa biết” không nên tự động được đổi thành “thấp”. Có thể giữ mức tạm thời cùng độ tin cậy thấp và một hành động thu thập bằng chứng có thời hạn.

## 5. Hậu quả và mức tác động

**Hậu quả** là kết quả có thể xảy ra đối với mục tiêu khi kịch bản thành hiện thực. **Mức tác động** là cách tổ chức đánh giá độ nghiêm trọng của hậu quả đó.

Cần xem nhiều chiều:

- **Bí mật:** loại dữ liệu nào bị lộ, của ai, số lượng bao nhiêu và có thể thu hồi thông tin không?
- **Toàn vẹn:** dữ liệu hay quyền nào bị sửa, có gây giao dịch sai hoặc quyết định sai không?
- **Sẵn sàng:** chức năng nào ngừng, trong bao lâu, tại thời điểm nghiệp vụ nào?
- **Con người:** có ảnh hưởng tới quyền lợi, an toàn hoặc khả năng tiếp cận dịch vụ thiết yếu không?
- **Hoạt động và tài chính:** chi phí gián đoạn, xử lý, phục hồi và ảnh hưởng tới khách hàng là gì?
- **Nghĩa vụ và niềm tin:** có nghĩa vụ hợp đồng hoặc yêu cầu áp dụng nào cần xem xét không?

Không mặc định rằng một loại nghĩa vụ hoặc mức thiệt hại áp dụng cho mọi tổ chức. Phải xác định theo phạm vi thực tế.

### 5.1. Tách hậu quả trực tiếp và hậu quả kéo theo

Với truy cập chéo hồ sơ:

```text
Thiếu kiểm tra quyền trên hồ sơ
              |
              v
Người dùng đọc được hồ sơ ngoài phạm vi
              |
              +-> Lộ thông tin của khách hàng
              +-> Phải điều tra và hạn chế sự cố
              +-> Có thể gián đoạn chức năng để xử lý
              +-> Có thể phát sinh ảnh hưởng hợp đồng và niềm tin
```

Không nên cộng các hậu quả trùng nhau để làm mức rủi ro tăng giả tạo. Cũng không nên chỉ ghi hậu quả kỹ thuật “API trả dữ liệu” mà bỏ qua dữ liệu đó có ý nghĩa gì.

### 5.2. Ví dụ thang tác động

| Mức | Mô tả minh họa |
| --- | --- |
| Thấp | Ảnh hưởng hẹp, dễ sửa, không tác động đáng kể tới dữ liệu nhạy cảm hay hoạt động chính |
| Trung bình | Ảnh hưởng một nhóm người dùng hoặc chức năng, cần xử lý có phối hợp nhưng phục hồi trong khả năng dự kiến |
| Cao | Lộ dữ liệu nhạy cảm, sai giao dịch quan trọng hoặc gián đoạn đáng kể hoạt động chính |
| Rất cao | Ảnh hưởng diện rộng, khó đảo ngược, mất dữ liệu trọng yếu hoặc gây hậu quả nghiêm trọng cho con người và tổ chức |

Muốn dùng trong thực tế, thang cần có tiêu chí cụ thể hơn theo từng chiều: loại dữ liệu, quy mô, thời gian, phạm vi dịch vụ và khả năng phục hồi. Không dùng bảng minh họa này thay cho quyết định nghiệp vụ.

Nếu tổ chức lấy mức nghiêm trọng nhất trong các chiều làm mức tác động chung, cần ghi rõ quy tắc đó. Nếu dùng cách khác, cũng phải giải thích; không cộng tùy ý các nhãn định tính.

## 6. Kết hợp khả năng xảy ra và tác động

Nhiều nhóm dùng ma trận để xếp thứ tự ưu tiên. Ma trận là công cụ hỗ trợ quyết định, không phải phép đo tự nhiên có độ chính xác tuyệt đối.

Ví dụ ma trận nội bộ minh họa:

| Khả năng xảy ra / Tác động | Thấp | Trung bình | Cao | Rất cao |
| --- | --- | --- | --- | --- |
| Thấp | Thấp | Thấp | Trung bình | Cao |
| Trung bình | Thấp | Trung bình | Cao | Rất cao |
| Cao | Trung bình | Cao | Rất cao | Rất cao |

Cần lưu ý:

- Hai tổ chức có thể đặt ngưỡng khác nhau vì mục tiêu và mức chịu đựng khác nhau.
- Một kịch bản hiếm nhưng hậu quả rất lớn vẫn có thể cần xử lý hoặc chuyển cấp.
- Hai kịch bản cùng ô không nhất thiết có cùng hành động xử lý.
- Chi phí, tính khả thi, nghĩa vụ bắt buộc và mức bất định cũng ảnh hưởng quyết định.
- Phải giữ thông tin kịch bản gốc; một nhãn “cao” không thay thế hồ sơ rủi ro.

### 6.1. Vì sao không coi mọi phép nhân là xác suất?

Một nhóm có thể gán số cho các mức rồi tính điểm khả năng nhân điểm tác động. Nếu các số chỉ là mã thứ bậc, tích của chúng là **điểm xếp hạng theo quy ước**, không phải xác suất, giá trị thiệt hại kỳ vọng hoặc tỷ lệ phần trăm an toàn.

Ví dụ, điểm 12 không tự nói một kịch bản nguy hiểm gấp đôi điểm 6. Không nên suy diễn quan hệ định lượng khi thang đo chưa hỗ trợ.

Đánh giá định lượng đòi hỏi mô hình, dữ liệu, đơn vị và cách biểu diễn bất định phù hợp. Chỉ thêm chữ số thập phân vào bảng điểm không biến một đánh giá định tính thành đo lường chính xác.

### 6.2. Tránh công thức đơn giản hóa sai

Không có công thức số học chung kiểu “đe dọa nhân điểm yếu nhân tài sản” có thể thay thế việc mô tả kịch bản. Các yếu tố đó giúp phân tích nguyên nhân và điều kiện, nhưng chỉ có thể đưa vào một mô hình tính khi từng biến đã được định nghĩa rõ và mô hình phù hợp mục đích.

Một bản đánh giá tốt có thể hoàn toàn định tính, miễn là nhất quán, có căn cứ và dẫn tới quyết định có thể kiểm chứng.

## 7. Rủi ro trước kiểm soát, còn lại và mục tiêu

### 7.1. Rủi ro trước kiểm soát

**Rủi ro trước kiểm soát**, thường gọi là inherent risk, là đánh giá trước khi tính đến một tập kiểm soát được xác định.

Cần nói rõ tập kiểm soát nào đang được loại khỏi đánh giá. Trong một hệ thống thực tế, giả định “không có bất kỳ kiểm soát nào” có thể không hữu ích vì hệ thống luôn có những ràng buộc nền tảng.

Ví dụ:

> Đánh giá kịch bản truy cập chéo hồ sơ trước khi tính đến kiểm tra quyền trên đối tượng và ràng buộc tổ chức; vẫn giữ giả định người gọi phải đăng nhập.

Định nghĩa phạm vi như vậy giúp người đọc hiểu vì sao khả năng xảy ra được chấm ở mức đã chọn.

### 7.2. Rủi ro còn lại

**Rủi ro còn lại**, hay residual risk, là rủi ro sau khi tính đến các kiểm soát thực sự đang áp dụng trong phạm vi đánh giá.

Không nên giảm mức rủi ro chỉ vì một kiểm soát:

- Đã được ghi trong tài liệu.
- Đã tạo tác vụ triển khai nhưng chưa hoàn tất.
- Hoạt động ở một đường API nhưng chưa có ở đường xuất dữ liệu.
- Đã có mã xử lý nhưng chưa biết cấu hình production có bật không.
- Được nhà cung cấp quảng bá nhưng chưa xác định phạm vi áp dụng.

Mức giảm phải có lý do: kiểm soát ngăn bước nào, giới hạn hậu quả nào và bằng chứng gì hỗ trợ kết luận.

### 7.3. Rủi ro mục tiêu

**Rủi ro mục tiêu** là mức dự kiến sau khi thực hiện một kế hoạch xử lý. Đây là dự báo phục vụ quyết định, chưa phải trạng thái đã đạt.

| Trạng thái | Ví dụ | Cách ghi đúng |
| --- | --- | --- |
| Trước kiểm soát được chọn | Chưa tính đến kiểm tra quyền trên hồ sơ | Nêu giả định và mức đánh giá ban đầu |
| Hiện tại | Một số API có kiểm tra nhưng API xuất còn thiếu | Đánh giá rủi ro còn lại theo phạm vi đang tồn tại |
| Mục tiêu | Dự kiến áp dụng kiểm tra thống nhất và kiểm thử từ chối | Ghi mức kỳ vọng cùng điều kiện cần đạt |
| Sau xác minh | Kiểm soát đã triển khai và có bằng chứng đủ trong phạm vi | Cập nhật rủi ro còn lại, giữ giới hạn của bằng chứng |

### 7.4. Kiểm soát tác động vào đâu?

- **Phòng ngừa:** làm giảm khả năng thực hiện hành vi hoặc ngăn chuyển sang hậu quả, như kiểm tra quyền trước khi trả dữ liệu.
- **Phát hiện:** giúp nhận ra hành vi hoặc dấu hiệu bất thường, như phát hiện truy cập hàng loạt ngoài mẫu thông thường.
- **Ứng phó và khắc phục:** hạn chế thời gian hoặc phạm vi ảnh hưởng, như thu hồi quyền và phục hồi dữ liệu.
- **Giảm phạm vi:** giới hạn số dữ liệu hoặc hệ thống bị ảnh hưởng, như phân tách miền quyền và dữ liệu.

Một biện pháp có thể hỗ trợ nhiều mục đích. Tuy vậy, chỉ có log không tự ngăn lần đọc trái phép đầu tiên. Cảnh báo chỉ giúp giảm hậu quả nếu có người hoặc cơ chế xử lý kịp thời.

Tương tự, bản sao lưu có thể giảm hậu quả mất dữ liệu nếu khôi phục được. Nó không tự ngăn đọc trộm dữ liệu và có thể tạo thêm bản sao cần bảo vệ.

## 8. Quyết định xử lý rủi ro

Những hướng xử lý thường gặp gồm:

| Hướng xử lý | Ý nghĩa | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| Tránh | Thay đổi hoặc ngừng hoạt động tạo ra kịch bản | Không thu thập trường nhạy cảm không cần thiết | Phải xem mục tiêu nghiệp vụ còn đạt được không |
| Giảm | Thay đổi khả năng xảy ra hoặc hậu quả | Kiểm tra quyền, giới hạn phạm vi, diễn tập phục hồi | Có thể vẫn còn rủi ro |
| Chia sẻ hoặc chuyển một phần | Phân bổ trách nhiệm, dịch vụ hoặc hậu quả theo thỏa thuận | Dùng dịch vụ chuyên trách với trách nhiệm rõ ràng | Không tự xóa rủi ro kỹ thuật hay trách nhiệm còn giữ |
| Chấp nhận | Quyết định chịu rủi ro còn lại trong điều kiện xác định | Chấp nhận một hạn chế có thời hạn và theo dõi | Cần người có thẩm quyền, căn cứ và điều kiện xem xét lại |

Một rủi ro có thể cần kết hợp nhiều hướng. Ví dụ, tổ chức không lưu một số trường, dùng dịch vụ ngoài cho một bước xử lý, triển khai phân quyền và chấp nhận phần bất định còn lại theo quy trình.

### 8.1. Chấp nhận không có nghĩa là bỏ quên

Một quyết định chấp nhận nên ghi:

- Kịch bản và mức rủi ro còn lại được chấp nhận.
- Lý do, phương án thay thế và giới hạn đã xem xét.
- Chủ thể có thẩm quyền quyết định.
- Điều kiện vận hành và các kiểm soát phải duy trì.
- Thời hạn hoặc thời điểm xem xét lại.
- Sự kiện làm quyết định hết phù hợp.

Người triển khai kỹ thuật không mặc nhiên có quyền chấp nhận mọi hậu quả nghiệp vụ. Chủ sở hữu rủi ro cần có thẩm quyền tương ứng; nhóm kỹ thuật cung cấp phân tích và bằng chứng.

### 8.2. Mức sẵn lòng và giới hạn chịu đựng

**Khẩu vị rủi ro** diễn đạt loại và mức rủi ro tổ chức sẵn sàng theo đuổi hoặc giữ để đạt mục tiêu. **Ngưỡng chịu đựng** cụ thể hóa giới hạn có thể chấp nhận cho phạm vi hoặc mục tiêu nhất định.

Ví dụ, một dịch vụ có thể có giới hạn về thời gian gián đoạn hoặc phạm vi dữ liệu bị ảnh hưởng. Các giới hạn này cần được chủ sở hữu xác định và thống nhất; nhóm phát triển không nên tự suy ra từ màu của một ô ma trận.

Một rủi ro vượt ngưỡng có thể cần chuyển cấp, thay đổi phạm vi phát hành hoặc bổ sung biện pháp. Không nên hạ điểm để làm cho kế hoạch trông phù hợp hơn.

## 9. Từ rủi ro đến yêu cầu bảo mật

### 9.1. Chuỗi truy vết

```text
Mục tiêu nghiệp vụ và tài sản
             |
             v
Kịch bản rủi ro + căn cứ + mức bất định
             |
             v
Quyết định xử lý
             |
             v
Yêu cầu bảo mật có tiêu chí chấp nhận
             |
             v
Thành phần kiến trúc và triển khai
             |
             v
Bằng chứng kiểm thử, vận hành, diễn tập
             |
             v
Đánh giá rủi ro còn lại và quyết định tiếp theo
```

Không có quan hệ một đối một bắt buộc. Một rủi ro có thể cần nhiều yêu cầu; một yêu cầu có thể hỗ trợ nhiều rủi ro. Quan trọng là giữ được lý do và phạm vi để khi hệ thống thay đổi, nhóm biết cần đánh giá lại điều gì.

### 9.2. Ví dụ rủi ro truy cập chéo tổ chức

Giả sử cổng hồ sơ khách hàng có API đọc chi tiết, tìm kiếm và xuất tệp. Rủi ro được định danh là **R-01**:

> Người dùng của tổ chức A có thể nhận hồ sơ thuộc B nếu một đường truy cập không kiểm tra quyền trên hồ sơ và phạm vi tổ chức, dẫn tới lộ dữ liệu ngoài phạm vi được cấp.

Các yêu cầu có thể rút ra:

| ID | Yêu cầu | Thành phần thực thi | Tiêu chí chấp nhận |
| --- | --- | --- | --- |
| SEC-REQ-01 | Mọi đường đọc hồ sơ phải xác thực danh tính và xác định phạm vi tổ chức từ nguồn tin cậy | Cơ chế xác thực và dịch vụ nghiệp vụ | Không xác thực thì bị từ chối; tham số do người gọi tự đổi không mở rộng phạm vi |
| SEC-REQ-02 | Đọc chi tiết, tìm kiếm và xuất phải kiểm tra quyền trên dữ liệu trước khi trả kết quả | Dịch vụ hồ sơ, truy vấn và tác vụ xuất | Người A không nhận dữ liệu B khi đổi ID, bộ lọc, tham số phân trang hoặc loại đầu ra |
| SEC-REQ-03 | Tệp xuất phải được ràng buộc với chủ thể và phạm vi đã được cấp tại thời điểm truy cập theo chính sách | Kho tệp và đường tải | Người khác hoặc chủ thể đã mất quyền không tải được theo quy tắc thu hồi đã định |
| SEC-REQ-04 | Các hành vi truy cập bị từ chối thuộc phạm vi phải tạo sự kiện truy vết không chứa nội dung hồ sơ nhạy cảm | Ứng dụng và nơi lưu log | Ca từ chối có chủ thể, đối tượng tham chiếu, thời gian và kết quả; không ghi bản hồ sơ |
| SEC-REQ-05 | Quy trình thu hồi quyền phải có thời hạn hiệu lực và bao quát phiên, cache cùng tác vụ nền liên quan | Danh tính, dịch vụ hồ sơ và tác vụ nền | Đo được thời gian từ sự kiện thu hồi hợp lệ đến lúc các đường thuộc phạm vi ngừng cung cấp dữ liệu |

SEC-REQ-05 chưa được coi là đặc tả hoàn tất nếu chỉ dừng ở câu “có thời hạn”. Cần điền ngưỡng đã được chủ sở hữu chấp thuận, mốc bắt đầu và kết thúc đo, cùng hành vi của tác vụ đang chạy.

Ví dụ minh họa:

> Sau khi hệ thống nhận sự kiện thu hồi quyền hợp lệ, các đường đọc hồ sơ và tải tệp thuộc phạm vi phải ngừng cấp dữ liệu theo quyền đó trong tối đa 10 phút, bao gồm trường hợp phiên đang tồn tại và quyền được cache.

Mốc 10 phút là giả định học tập, không phải ngưỡng mặc định cho mọi dịch vụ.

### 9.3. Không nhầm tên sản phẩm với yêu cầu

“Dùng sản phẩm quản lý danh tính X” là một lựa chọn giải pháp. Nó chưa bảo đảm mọi API kiểm tra đúng tổ chức, mọi tệp xuất có quyền phù hợp hoặc quyền bị thu hồi đúng hạn.

Yêu cầu nên nêu hành vi cần đạt. Quyết định kiến trúc chỉ ra thành phần thực thi. Bằng chứng cho biết thành phần đó có đạt hành vi trong phạm vi thực tế không.

Tương tự, câu “bật mã hóa” không trực tiếp xử lý thiếu phân quyền nếu ứng dụng vẫn được giải mã và trả hồ sơ cho người sai.

## 10. Một hồ sơ rủi ro hoàn chỉnh ở mức thiết kế

Ví dụ sau mô tả cách ghi nhận **R-02: mất khả năng phục hồi hồ sơ**, bổ sung cho rủi ro lộ dữ liệu ở trên. Các mức và mục tiêu là minh họa.

```yaml
riskId: R-02
title: cannot-restore-customer-records
scope:
  service: customer-record-service
  environment: production
  assessmentHorizon: next-12-months
objective: restore-required-records-after-primary-region-loss
scenario: >
  Sau khi mất vùng chính, nhóm vận hành có thể không phục hồi được
  hồ sơ vì bản sao lưu chưa được thử cùng khóa giải mã, danh tính
  và chính sách truy cập cần thiết.
consequences:
  - prolonged-service-interruption
  - inability-to-access-retained-records
currentControls:
  - scheduled-data-backups
evidenceGaps:
  - no-end-to-end-restore-drill
  - key-access-in-recovery-region-not-verified
assessment:
  likelihood: medium
  impact: high
  priority: high
  confidence: low
treatment: reduce
riskOwner: customer-record-service-owner
actionOwners:
  - storage-operations-team
  - identity-and-key-platform-team
requiredEvidence:
  - isolated-restore-drill
  - data-integrity-checks
  - key-and-identity-recovery-test
reviewTrigger: completed-drill-or-recovery-architecture-change
```

Hồ sơ là mô hình nội dung, không phải cấu hình chạy được. Trong công việc thực tế cần bổ sung ngày đánh giá, hạn hoàn thành, người quyết định và tham chiếu yêu cầu.

### 10.1. Giải thích căn cứ đánh giá

- Tác động được đánh giá cao vì không truy cập được hồ sơ cần cho hoạt động chính.
- Khả năng xảy ra tạm ở mức trung bình do chưa có diễn tập đầy đủ, không phải vì đã đo được một xác suất cụ thể.
- Độ tin cậy thấp phản ánh thiếu bằng chứng; cần ưu tiên thu thập bằng chứng phục hồi.
- Có sao lưu theo lịch là kiểm soát hiện có, nhưng không chứng minh toàn bộ đường phục hồi hoạt động.

Một lựa chọn khác có thể là giữ mức khả năng “chưa xác định” nếu phương pháp của tổ chức cho phép. Điều quan trọng là không trình bày giả định như sự thật đã xác minh.

### 10.2. Yêu cầu và bằng chứng cần thiết

Có thể đặc tả yêu cầu phục hồi với:

- Kịch bản: mất vùng chính, không dùng được hệ thống chính để đọc dữ liệu.
- Phạm vi: bộ hồ sơ ưu tiên và các thành phần phụ thuộc.
- Mục tiêu thời gian phục hồi và mức mất dữ liệu được phép.
- Khả năng sử dụng khóa, danh tính, chính sách và cấu hình tại nơi phục hồi.
- Cách kiểm tra tính đầy đủ và toàn vẹn của dữ liệu.
- Điều kiện để mở lại dịch vụ cho người dùng.

**RTO** là mục tiêu thời gian khôi phục. **RPO** là mục tiêu mức mất dữ liệu chấp nhận được, thường biểu diễn bằng khoảng thời gian. Cả hai cần có mốc đo và phạm vi cụ thể.

Nếu diễn tập thành công trong một kịch bản, bằng chứng đó hỗ trợ đánh giá cho kịch bản tương ứng. Nó không chứng minh khả năng phục hồi trước mọi loại mất dữ liệu hoặc mọi sự cố nhà cung cấp.

## 11. Rủi ro và mức đảm bảo có quan hệ thế nào?

**Mức đảm bảo** trong ngữ cảnh bài học là mức tin cậy có căn cứ rằng yêu cầu và kiểm soát đạt mục tiêu trong phạm vi xác định.

Hai câu hỏi cần phân biệt:

- **Rủi ro:** điều gì có thể sai, khả năng và hậu quả là gì?
- **Đảm bảo:** có bằng chứng nào để tin rằng kiểm soát ngăn hoặc hạn chế được điều đó?

Ví dụ:

| Tuyên bố | Bằng chứng hiện có | Kết luận phù hợp |
| --- | --- | --- |
| “API có phân quyền” | Chỉ có một đoạn mô tả thiết kế | Có ý định kiểm soát, chưa đủ căn cứ về hiệu lực triển khai |
| “API từ chối đọc chéo tổ chức” | Kiểm thử có các danh tính và đường truy cập thuộc phạm vi | Có bằng chứng cho các điều kiện đã thử, cần giữ giới hạn phạm vi |
| “Dịch vụ phục hồi được” | Chỉ thấy bản sao lưu tồn tại | Chưa chứng minh đường phục hồi hoàn chỉnh |
| “Kịch bản mất vùng đáp ứng mục tiêu” | Diễn tập có dữ liệu, khóa, danh tính và phép đo | Tăng mức tin cậy cho kịch bản đã diễn tập |

Mức rủi ro cao thường là lý do cần bằng chứng mạnh hơn, bao phủ tốt hơn hoặc kiểm tra độc lập phù hợp. Tuy vậy, không nên tự đặt quan hệ như “rủi ro cao luôn tương đương mức đảm bảo số 3” khi chưa có khung đã được định nghĩa.

Một đợt kiểm thử tốt cũng có thể phát hiện thiếu sót và làm mức rủi ro được đánh giá tăng lên. Đó là hiểu biết được cải thiện, không phải kiểm thử đã tự tạo ra rủi ro mới.

Không dùng câu “đã kiểm thử nên rủi ro bằng không”. Bằng chứng luôn có phạm vi, điều kiện và thời điểm; hệ thống cùng môi trường đe dọa có thể thay đổi.

## 12. Khi nào cần xem xét lại rủi ro?

Rủi ro là nhận định theo bối cảnh, không phải nhãn gắn một lần rồi giữ mãi. Cần đánh giá lại khi có:

- Dữ liệu nhạy cảm mới hoặc tăng đáng kể số người bị ảnh hưởng.
- Giao diện mới, mở ra Internet hoặc tích hợp đối tác.
- Thay đổi mô hình danh tính, phân quyền hoặc ranh giới tin cậy.
- Thay đổi nhà cung cấp, vùng triển khai, khóa hoặc đường phục hồi.
- Điểm yếu mới, sự cố, kiểm thử thất bại hoặc dấu hiệu lạm dụng.
- Kiểm soát bị tắt, cấu hình lệch hoặc bằng chứng đã quá cũ.
- Mục tiêu nghiệp vụ, ngưỡng chịu đựng hoặc nghĩa vụ áp dụng thay đổi.
- Đến hạn xem xét của một quyết định chấp nhận.

Việc xem xét nên giữ được lịch sử: đánh giá cũ dựa trên giả định nào, điều gì thay đổi và vì sao quyết định mới khác trước.

Các chỉ số như số truy cập bị từ chối, độ trễ thu hồi quyền hoặc kết quả diễn tập giúp theo dõi điều kiện kiểm soát. Không coi chúng tự động là số đo đầy đủ của rủi ro; ít cảnh báo có thể do ít hành vi, cũng có thể do giám sát thiếu.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao có vấn đề | Cách cải thiện |
| --- | --- | --- |
| Ghi rủi ro là “SQL injection” hoặc tên một lỗi | Mới nêu kỹ thuật hoặc điểm yếu, chưa có phạm vi và hậu quả | Viết kịch bản tác động tới tài sản và mục tiêu cụ thể |
| Chấm mọi thứ là cao | Không giúp ưu tiên hoặc phân bổ bằng chứng | Dùng tiêu chí nhất quán và giải thích căn cứ |
| Chưa thấy sự cố nên chấm thấp | Có thể thiếu quan sát hoặc chưa gặp điều kiện | Xem mức tiếp xúc, điểm yếu, kiểm soát và khoảng trống bằng chứng |
| Nhân điểm rồi coi là xác suất | Thang thứ bậc không tự hỗ trợ suy diễn định lượng | Ghi rõ đây là điểm xếp hạng theo quy ước |
| Giảm rủi ro vì đã có kế hoạch sửa | Kế hoạch chưa thay đổi hiệu lực hiện tại | Tách rủi ro hiện tại với rủi ro mục tiêu |
| Có log nghĩa là đã ngăn tấn công | Phát hiện khác phòng ngừa | Nêu bước kiểm soát tác động và quy trình ứng phó |
| Thuê ngoài nghĩa là hết rủi ro | Phụ thuộc, cấu hình và trách nhiệm vẫn tồn tại | Ghi phần chia sẻ và phần tổ chức còn chịu |
| Đạt một kiểm thử nghĩa là an toàn tuyệt đối | Bằng chứng có phạm vi và điều kiện | Ghi giới hạn, duy trì kiểm chứng khi thay đổi |
| Kỹ thuật viên tự chấp nhận mọi rủi ro | Có thể vượt thẩm quyền chịu hậu quả nghiệp vụ | Xác định chủ sở hữu và người quyết định phù hợp |
| Chỉ lưu màu rủi ro | Mất kịch bản, giả định và căn cứ | Giữ hồ sơ truy vết từ mục tiêu đến bằng chứng |

## 14. Bài tập tự kiểm tra

### Bài tập 1: phân biệt rủi ro và điểm yếu

Một API có thể đọc hồ sơ theo mã do người gọi cung cấp. Hiện mới biết API yêu cầu đăng nhập; chưa rõ có kiểm tra tổ chức hay không.

Hãy phân biệt:

1. Thông tin đã biết.
2. Điểm yếu đang được giả định.
3. Kịch bản rủi ro.
4. Bằng chứng cần thu thập.
5. Yêu cầu có thể cần bổ sung nếu giả định được xác nhận.

**Gợi ý:** chưa nên tuyên bố chắc chắn có lộ dữ liệu. Kịch bản cần nêu khả năng đọc ngoài phạm vi nếu thiếu kiểm tra quyền. Bằng chứng gồm xem đường xử lý và kiểm thử các danh tính khác phạm vi. Yêu cầu phải bao quát cả chi tiết, tìm kiếm và xuất nếu chúng cùng cung cấp hồ sơ.

### Bài tập 2: đánh giá kiểm soát

Một đội cho rằng rủi ro mất dữ liệu đã thấp vì “có backup mỗi ngày”. Chưa từng phục hồi thử và chưa rõ khóa giải mã có ở nơi dự phòng hay không.

Hãy nêu:

- Kiểm soát hiện có thực sự chứng minh điều gì.
- Khoảng trống bằng chứng.
- Những yêu cầu phục hồi cần đặc tả.
- Vì sao chưa thể lấy mức rủi ro mục tiêu làm rủi ro còn lại.

**Gợi ý:** lịch sao lưu không chứng minh phục hồi thành công. Cần kiểm tra dữ liệu, khóa, danh tính, chính sách và thời gian trong một kịch bản cụ thể. Mục tiêu giảm rủi ro chỉ trở thành đánh giá hiện tại khi có căn cứ về hiệu lực kiểm soát.

### Bài tập 3: diễn giải điểm rủi ro

Một bảng nội bộ cho điểm kịch bản A là 12, kịch bản B là 6. Có thể nói A có xác suất gây thiệt hại gấp đôi B không?

**Gợi ý:** không thể kết luận như vậy nếu điểm chỉ là tích của các mức thứ bậc. Cần đọc kịch bản, thang đo và quy tắc quyết định. Điểm ưu tiên không tự trở thành xác suất hoặc thiệt hại kỳ vọng.

### Bài tập 4: viết một chuỗi truy vết

Chọn mục tiêu “người bị thu hồi quyền không tiếp tục tải hồ sơ nhạy cảm”. Viết:

- Một kịch bản rủi ro có phạm vi.
- Các điều kiện như phiên đang tồn tại, cache hoặc liên kết tải.
- Một yêu cầu có thời hạn hiệu lực được định nghĩa rõ.
- Ca kiểm thử từ chối và bằng chứng cần giữ.
- Rủi ro còn lại, chẳng hạn bản đã tải xuống trước đó.

**Gợi ý:** chặn tải mới không thu hồi thông tin đã được sao chép. Phải phân biệt khả năng hệ thống kiểm soát với hậu quả đã xảy ra ngoài ranh giới quản lý.

## 15. Mẫu ghi nhận ngắn để áp dụng

```text
RISK-ID:
  Mã định danh ổn định.

MỤC TIÊU VÀ PHẠM VI:
  Tài sản, dịch vụ, môi trường, nhóm người dùng và khoảng thời gian.

KỊCH BẢN:
  Nguồn đe dọa có thể gây sự kiện nào,
  qua điều kiện nào, dẫn tới hậu quả gì.

CĂN CỨ:
  Điều đã biết, giả định, bằng chứng và thông tin còn thiếu.

ĐÁNH GIÁ:
  Khả năng xảy ra, tác động, quy tắc ưu tiên và độ tin cậy.

KIỂM SOÁT HIỆN CÓ:
  Kiểm soát đang áp dụng, phạm vi và bằng chứng hiệu lực.

XỬ LÝ:
  Tránh, giảm, chia sẻ hoặc chấp nhận; người quyết định và thời hạn.

YÊU CẦU VÀ KIẾN TRÚC:
  ID yêu cầu, hành vi cần đạt, thành phần thực thi và người phụ trách.

KIỂM CHỨNG:
  Ca kiểm thử, phép đo, diễn tập và bằng chứng chấp nhận.

RỦI RO CÒN LẠI:
  Điều chưa được loại bỏ và điều kiện để tiếp tục vận hành.

XEM XÉT LẠI:
  Thời điểm, sự kiện kích hoạt và người chịu trách nhiệm.
```

Một phát biểu rủi ro hữu ích giúp nhóm thiết kế giải thích được vì sao cần một yêu cầu bảo mật, kiểm soát đó thay đổi kịch bản như thế nào và phải có bằng chứng gì trước khi kết luận rằng phần rủi ro còn lại có thể được chấp nhận.
