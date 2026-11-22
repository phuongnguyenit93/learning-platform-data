# Đọc gần ngôn ngữ miền

Khi thiết kế ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), nhóm phát triển cần hiểu cách cộng đồng trong một lĩnh vực thực sự gọi tên đối tượng, mô tả công việc, phân biệt trạng thái và giải thích quy tắc. Những ý nghĩa này thường được lưu trong tài liệu nội bộ, hội thoại, phiếu yêu cầu, hướng dẫn vận hành, biên bản quyết định và cả những cách nói ngắn gọn mà người trong nhóm mặc nhiên hiểu.

**Đọc gần ngôn ngữ miền** là cách đọc có chủ đích, chậm và có hệ thống một phát biểu hoặc tài liệu thuộc miền để nhận ra chính xác từ ngữ, cấu trúc câu, sắc thái, ngữ cảnh và giả định đang tạo nên ý nghĩa. Người đọc không chỉ hỏi “văn bản nói về điều gì?” mà còn hỏi “tại sao người viết chọn từ này?”, “từ này có nghĩa gì trong tình huống cụ thể?”, “điều kiện nào đang được ngầm hiểu?” và “cách diễn đạt này cho biết cộng đồng tổ chức công việc ra sao?”.

Trong kiến trúc DSL, việc đọc gần giúp khám phá **ngôn ngữ nội bộ** của cộng đồng miền. Kết quả là một hiểu biết có căn cứ về thuật ngữ, cách phân loại, quan hệ, hành động, quy tắc, ngoại lệ và ranh giới ý nghĩa. Đây là cơ sở để xây dựng từ vựng và mô hình miền, rồi mới quyết định cấu trúc DSL nào có thể biểu đạt chúng một cách rõ ràng.

## 1. Đọc gần là gì?

Đọc gần (close reading) là phương pháp diễn giải văn bản bằng cách chú ý đến những chi tiết cụ thể trong chính văn bản và quan hệ giữa các chi tiết đó. Thay vì chỉ tóm tắt nội dung, người đọc xem xét cách từ ngữ được dùng, cấu trúc câu, lựa chọn diễn đạt, sự lặp lại, đối lập, điều kiện, giọng điệu và phần thông tin bị bỏ ngỏ.

Khi áp dụng vào khám phá miền, đối tượng đọc có thể là một quy trình nghiệp vụ, một ticket kỹ thuật, một đoạn hội thoại hỗ trợ, một tiêu chuẩn nội bộ hoặc một ví dụ cấu hình. Người đọc cần giữ nguyên ngữ cảnh của phát biểu, xác định ai đang nói, nói với ai, trong tình huống nào và nhằm mục đích gì.

Đọc gần không phải là đoán ý định của tác giả. Mọi diễn giải quan trọng phải dựa trên dấu hiệu trong văn bản, được đặt trong ngữ cảnh và được xác nhận khi cần. Nếu văn bản không đủ căn cứ, kết quả đúng là ghi nhận một câu hỏi mở thay vì tự bổ sung một quy tắc.

### 1.1. Đọc để hiểu ý nghĩa và đọc để khám phá miền

Đọc một tài liệu thông thường thường hướng đến việc nắm nội dung chính. Đọc gần trong thiết kế DSL còn cần tìm cấu trúc khái niệm ẩn sau cách diễn đạt.

Ví dụ, câu nội bộ:

> Sau khi QA xanh thì đẩy bản vá lên production; nếu health check đỏ thì rollback ngay.

Một bản tóm tắt có thể chỉ ghi “triển khai bản vá và hoàn tác nếu kiểm tra sức khỏe thất bại”. Đọc gần sẽ chú ý thêm:

- “QA xanh” là một trạng thái được xác nhận hay chỉ là cách nói tắt về kết quả kiểm thử?
- “Đẩy” có nghĩa là triển khai tự động, yêu cầu phê duyệt hay thực hiện thủ công?
- “Production” chỉ môi trường chạy thật hay một nhóm cụm máy chủ cụ thể?
- “Health check đỏ” dựa trên chỉ số, ngưỡng và khoảng thời gian nào?
- “Ngay” có nghĩa là tức thì, trong một thời hạn vận hành hay trong ca trực hiện tại?
- Ai được quyền thực hiện rollback và ai xác nhận hệ thống đã phục hồi?

Những câu hỏi này cho thấy phát biểu chứa nhiều khái niệm và quy tắc chưa được nói đầy đủ. Nếu chuyển nguyên câu thành cú pháp DSL mà không làm rõ chúng, ngôn ngữ mới có thể đóng băng một cách hiểu sai.

### 1.2. Vì sao gọi là “đọc gần”?

“Gần” ở đây chỉ mức độ chú ý đến bằng chứng trong văn bản. Người đọc xem xét từng từ và cụm từ trong quan hệ với toàn câu, đoạn, tài liệu, tình huống và cộng đồng sử dụng. Một từ đơn lẻ không tự mang đầy đủ ý nghĩa miền; cách dùng và ngữ cảnh mới xác định ý nghĩa cụ thể.

Đọc gần không có nghĩa là phân tích từng chữ một cách tách rời. Cần di chuyển qua lại giữa chi tiết và toàn thể: một từ được hiểu nhờ câu chứa nó, câu được hiểu nhờ quy trình, còn quy trình được kiểm tra bằng nhiều tài liệu và trường hợp thực tế.

## 2. Vai trò của ngôn ngữ nội bộ trong DSL

**Ngôn ngữ nội bộ** là tập hợp cách gọi, cách viết tắt, biểu thức, quy ước và lối diễn đạt mà một cộng đồng miền sử dụng trong công việc. Nó có thể bao gồm thuật ngữ chính thức, biệt ngữ nghề nghiệp, mã nội bộ, tên trạng thái trong hệ thống và những cách nói ngắn chỉ người trong nhóm mới hiểu.

Ngôn ngữ nội bộ không nhất thiết được chuẩn hóa trong một từ điển. Một số ý nghĩa chỉ xuất hiện trong trao đổi miệng hoặc trong những tình huống lặp lại. Ví dụ, nhóm vận hành có thể nói “đưa lên xanh”, nhóm phát triển nói “merge vào nhánh release”, còn nhóm hỗ trợ nói “mở lại case”. Các cụm này có thể chỉ những hành động khác nhau, dù cùng xuất hiện trong một quy trình phát hành sản phẩm.

DSL cần phản ánh đúng những khái niệm và phân biệt có ý nghĩa đối với người dùng. Nếu ngôn ngữ bỏ qua cách cộng đồng phân biệt “yêu cầu”, “sự cố” và “thay đổi”, người dùng có thể phải chuyển sang cách diễn đạt không tự nhiên hoặc hiểu sai phạm vi câu lệnh.

### 2.1. Ngôn ngữ nội bộ gồm nhiều lớp

Trong một miền, có thể nhận ra các lớp ngôn ngữ sau:

- **Thuật ngữ chính thức:** Tên được quy định trong chính sách, tiêu chuẩn hoặc tài liệu được phê duyệt.
- **Biệt ngữ nghề nghiệp:** Cách gọi quen thuộc giữa những người có cùng chuyên môn.
- **Tên gọi trong công cụ:** Tên trường dữ liệu, trạng thái, nút lệnh, mã lỗi hoặc nhãn trong phần mềm.
- **Từ viết tắt và mã:** Những dạng rút gọn như `SLA`, `PR`, `P0`, `RC` hoặc mã quy trình.
- **Cách nói tắt:** Cụm từ lược bỏ ngữ cảnh vì người trong nhóm đã biết phần còn lại.
- **Ẩn dụ và tiếng lóng:** Cách nói hình tượng như “đóng băng release”, “dọn backlog” hoặc “đẩy nóng”.
- **Cách diễn đạt theo vai trò:** Cùng một đối tượng có thể được bộ phận kỹ thuật, vận hành và kinh doanh gọi bằng tên khác nhau.

Các lớp này có thể cùng tồn tại. Đọc gần cần ghi nhận chúng trước khi chọn tên chuẩn cho DSL.

### 2.2. Ngôn ngữ phản ánh cách cộng đồng phân loại thế giới

Từ ngữ không chỉ đặt tên cho những đối tượng có sẵn; chúng còn cho thấy cộng đồng chia thế giới thành những nhóm nào. Nếu nhóm liên tục phân biệt “lỗi chặn phát hành” với “lỗi có thể theo dõi”, sự phân biệt đó có thể phản ánh một quy tắc quyết định quan trọng.

Ngược lại, hai nhóm có thể dùng cùng một từ nhưng phân loại khác nhau. “Hoàn tất” trong nhóm kỹ thuật có thể nghĩa là code đã merge; với nhóm vận hành, nó có thể nghĩa là thay đổi đã triển khai; với khách hàng, nó có thể nghĩa là kết quả đã được xác nhận. Đọc gần giúp phát hiện những ranh giới khái niệm này.

### 2.3. Ngôn ngữ nội bộ thay đổi theo thời gian

Thuật ngữ có thể thay đổi khi tổ chức đổi quy trình, công cụ hoặc cơ cấu. Một tên trạng thái cũ có thể vẫn xuất hiện trong ticket dù hệ thống mới đã thay thế nó. Một từ viết tắt có thể mang nghĩa khác sau khi sản phẩm mở rộng.

Vì vậy, mỗi phát hiện nên gắn với nguồn và thời điểm. Không nên coi mọi cách diễn đạt từng xuất hiện trong tài liệu là thuật ngữ hiện hành.

## 3. Đối tượng và nguồn để đọc gần

Đọc gần có thể áp dụng cho nhiều dạng tư liệu. Mỗi loại nguồn cho thấy một khía cạnh khác nhau của miền.

| Nguồn | Điều có thể khám phá |
|---|---|
| Chính sách và tiêu chuẩn | Định nghĩa chính thức, nghĩa vụ, điều kiện và ngoại lệ |
| Quy trình và hướng dẫn | Trình tự thao tác, vai trò, điểm bàn giao và trạng thái |
| Ticket và báo cáo sự cố | Cách gọi trong thực tế, trường hợp biên, nguyên nhân và mức độ ưu tiên |
| Hội thoại nội bộ | Cách nói tắt, kiến thức ngầm, bất đồng và cách giải thích |
| Biểu mẫu và checklist | Trường dữ liệu, phân loại, điều kiện bắt buộc và lựa chọn |
| Cấu hình và script hiện có | Từ vựng kỹ thuật, cấu trúc lặp lại và quy ước đang được mã hóa |
| Nhật ký quyết định | Lý do chọn một phương án, các lựa chọn bị loại và giả định |
| Tài liệu đào tạo | Cách tổ chức muốn người mới hiểu và sử dụng thuật ngữ |

Không nguồn nào tự động đại diện cho toàn bộ miền. Chính sách cho biết quy tắc chính thức nhưng có thể không mô tả ngoại lệ thực tế. Ticket cho thấy trường hợp thực tế nhưng có thể dùng từ không chuẩn. Tài liệu đào tạo phản ánh mô hình được truyền đạt nhưng có thể đơn giản hóa chi tiết.

### 3.1. Chọn đoạn văn bản có giá trị phân tích

Nên ưu tiên những đoạn:

- Có thuật ngữ được dùng nhiều hoặc có vẻ mang nghĩa chuyên biệt.
- Mô tả quyết định, điều kiện, ngoại lệ hoặc chuyển trạng thái.
- Có sự bất đồng về cách hiểu.
- Dùng từ viết tắt hoặc cách nói tắt mà người ngoài khó hiểu.
- Liên quan đến thao tác thường xuyên hoặc rủi ro cao.
- Cho thấy một quy trình giữa nhiều vai trò hoặc bộ phận.
- Đã dẫn đến lỗi, tranh luận hoặc cách xử lý khác nhau.

Đọc cả đoạn trước và sau câu được chọn. Một câu riêng lẻ thường không đủ để xác định đại từ, phạm vi điều kiện hoặc đối tượng đang được nhắc đến.

### 3.2. Ghi lại bối cảnh nguồn

Với mỗi trích đoạn, nên ghi nhận tối thiểu:

- Mã hoặc tên nguồn.
- Loại tài liệu và phiên bản.
- Ngày tạo hoặc thời điểm phát biểu.
- Vai trò của người viết hoặc người nói nếu được phép ghi nhận.
- Quy trình hoặc tình huống liên quan.
- Đối tượng đọc ban đầu và mục đích giao tiếp.
- Trạng thái tin cậy hoặc mức độ chính thức của nguồn.

Thông tin này giúp phân biệt một thuật ngữ trong tài liệu được phê duyệt với cách gọi tạm thời trong cuộc trò chuyện.

## 4. Các lớp ý nghĩa cần chú ý

Đọc gần nên quan sát nhiều lớp ý nghĩa cùng lúc. Một cụm từ có thể là tên đối tượng ở lớp từ vựng, biểu đạt một hành động ở lớp nghiệp vụ và mang mức độ bắt buộc ở lớp quy tắc.

### 4.1. Nghĩa từ vựng trong ngữ cảnh

Hãy xác định từ hoặc cụm từ đang chỉ điều gì trong đoạn cụ thể. Không nên dựa duy nhất vào nghĩa từ điển phổ thông.

Ví dụ, “đóng” trong các phát biểu sau không cùng một nghĩa:

- “Đóng ticket sau khi người báo xác nhận.”
- “Đóng băng nhánh release.”
- “Đóng phiên làm việc khi hết thời gian.”

Trong DSL, ba ý nghĩa này có thể cần ba khái niệm hoặc thao tác riêng: kết thúc ticket, ngăn thay đổi nhánh và chấm dứt phiên.

### 4.2. Nghĩa chuyên biệt và cách dùng theo cộng đồng

Một thuật ngữ có thể được cộng đồng dùng theo nghĩa hẹp hơn hoặc khác với nghĩa phổ thông. Ví dụ, “artifact” trong nhóm xây dựng phần mềm có thể chỉ gói đầu ra được tạo bởi pipeline; trong ngữ cảnh khác, nó có thể là bất kỳ sản phẩm hoặc tài liệu nào.

Ghi lại định nghĩa được cộng đồng dùng, ví dụ cụ thể và các trường hợp không thuộc khái niệm. Định nghĩa tốt cần nói được cả điều gì được tính là một trường hợp và điều gì không được tính.

### 4.3. Sắc thái và mức độ chắc chắn

Các từ “có thể”, “thường”, “nên”, “phải”, “chỉ”, “luôn” và “không được” thể hiện mức độ cam kết khác nhau.

So sánh:

- “Nên chạy kiểm thử trước khi merge.” Đây có thể là khuyến nghị.
- “Phải chạy kiểm thử trước khi merge.” Đây là yêu cầu bắt buộc.
- “Chỉ được merge khi kiểm thử đạt.” Đây là điều kiện giới hạn hành động.
- “Thường merge sau khi kiểm thử đạt.” Đây là mô tả thói quen, chưa chắc là quy tắc.

Nếu chuẩn hóa tất cả thành một câu “kiểm thử trước khi merge”, DSL có thể biến khuyến nghị thành ràng buộc hoặc bỏ mất điều kiện bắt buộc.

### 4.4. Hàm ý và kiến thức ngầm

Người trong cộng đồng thường bỏ qua những điều họ cho là hiển nhiên. Câu “đẩy bản vá lên như quy trình chuẩn” có thể dựa vào một quy trình phát hành mà người viết không nhắc lại.

Hãy ghi nhận phần bị lược bỏ dưới dạng câu hỏi: quy trình chuẩn nào, ai có quyền khởi chạy, cần phê duyệt gì, điều kiện dừng là gì? Không được biến hàm ý thành quy tắc chính thức nếu chưa có nguồn xác nhận.

### 4.5. Nghĩa hàm ẩn và sắc thái đánh giá

Các từ như “sạch”, “đỏ”, “nóng”, “nặng”, “ổn”, “nhẹ” có thể là nhãn đánh giá hoặc thuật ngữ nội bộ. Chúng có thể chứa thông tin hữu ích nhưng không phải lúc nào cũng có tiêu chí đo lường rõ.

Ví dụ, “build sạch” có thể có nghĩa không có lỗi biên dịch, không có cảnh báo, vượt qua toàn bộ test hoặc không còn lỗi nghiêm trọng. Cần xác định tiêu chí cụ thể trước khi biến từ này thành trạng thái máy.

### 4.6. Nghĩa theo vai trò

Người nói và người nhận có thể không dùng thuật ngữ giống nhau. Một kỹ sư có thể nói “rollback”, trong khi quản lý nói “khôi phục bản trước” và nhân viên hỗ trợ nói “đưa dịch vụ về trạng thái ổn định”. Các cách nói có thể chỉ cùng một hành động ở góc nhìn khác nhau hoặc thực sự chỉ những thao tác khác nhau.

Hãy ghi nhận vai trò của người dùng và tình huống. DSL có thể cần một thuật ngữ chuẩn, nhưng giao diện hướng dẫn hoặc tài liệu có thể giải thích các cách gọi tương ứng.

## 5. Đọc cấu trúc câu để tìm quy tắc miền

Ngữ nghĩa miền thường nằm trong cách các thành phần của câu liên kết với nhau. Chỉ trích xuất từ khóa sẽ bỏ qua điều kiện, tác nhân, phạm vi và thứ tự.

### 5.1. Chủ thể và tác nhân

Xác định ai hoặc thành phần nào thực hiện hành động. Câu chủ động thường nêu rõ tác nhân; câu bị động có thể che khuất người chịu trách nhiệm.

Ví dụ:

- “Quản lý phê duyệt thay đổi.” Tác nhân được nêu rõ là quản lý.
- “Thay đổi được phê duyệt.” Không rõ ai phê duyệt.
- “Hệ thống tự động đóng ticket.” Tác nhân là hệ thống, hành động được tự động hóa.

Nếu quyền hạn là một phần của miền, cần xác định tác nhân và vai trò chứ không chỉ ghi nhận động từ.

### 5.2. Đối tượng và phạm vi tác động

Xác định hành động tác động đến đối tượng nào, một đối tượng hay một tập hợp. Ví dụ “khóa tài khoản bị nghi ngờ” khác với “khóa tất cả tài khoản thuộc nhóm bị nghi ngờ”. Cụm từ chỉ số lượng và phạm vi có thể thay đổi đáng kể ngữ nghĩa.

### 5.3. Điều kiện và ngoại lệ

Các từ “nếu”, “khi”, “chỉ khi”, “trừ khi”, “ngoại trừ”, “miễn là” và “trong trường hợp” thường mở đầu hoặc giới hạn một quy tắc.

Hãy tách câu thành:

1. Hành động hoặc kết quả.
2. Điều kiện kích hoạt.
3. Điều kiện cần hoặc đủ.
4. Ngoại lệ.
5. Thứ tự ưu tiên nếu nhiều quy tắc cùng áp dụng.

Ví dụ “triển khai khi tất cả kiểm thử bắt buộc đạt, trừ bản vá khẩn cấp đã được người trực phê duyệt” chứa một quy tắc chung và một ngoại lệ có điều kiện riêng. DSL cần biểu diễn được mối quan hệ đó.

### 5.4. Trình tự và quan hệ thời gian

Những từ “trước khi”, “sau khi”, “đồng thời”, “trong vòng”, “cho đến khi” và “ngay lập tức” gợi ý quan hệ thời gian.

Ví dụ “sau khi merge, chạy pipeline rồi mới phát hành” mô tả thứ tự các sự kiện. Nhưng cần hỏi pipeline có phải hoàn tất thành công mới được phát hành hay chỉ cần bắt đầu chạy. Từ “sau” không tự động hàm ý “sau khi thành công”.

### 5.5. Phủ định và lượng từ

Các từ “không”, “chưa”, “mọi”, “mỗi”, “một số”, “ít nhất một”, “không có” có thể thay đổi phạm vi quy tắc.

Ví dụ:

- “Không triển khai khi có test thất bại.”
- “Chỉ triển khai khi không còn test thất bại.”

Hai câu có vẻ gần nhau nhưng có thể khác nếu hệ thống có test chưa chạy hoặc trạng thái chưa xác định. Cần làm rõ cách xử lý dữ liệu không đầy đủ.

### 5.6. Điều kiện cần và điều kiện đủ

“A chỉ khi B” thường nói B là điều kiện cần của A. “Nếu B thì A” thường diễn đạt B là điều kiện đủ để suy ra A trong phạm vi phát biểu. Không nên xem hai cấu trúc này là tương đương.

Ví dụ:

- “Chỉ được phát hành khi QA đạt” không khẳng định QA đạt là đủ để phát hành; có thể còn cần phê duyệt.
- “Nếu QA đạt thì tự động phát hành” mô tả QA đạt là điều kiện kích hoạt phát hành, trừ khi có quy tắc khác.

Khi đọc các câu có quan hệ logic, nên viết lại thành điều kiện tường minh và đưa ví dụ phản chứng để kiểm tra.

## 6. Đọc các dấu hiệu đặc thù của ngôn ngữ nội bộ

Ngôn ngữ nội bộ thường chứa những dạng diễn đạt không xuất hiện trong tài liệu chính thức. Chúng có thể cho thấy cách tổ chức công việc, lịch sử của hệ thống hoặc kiến thức mà người trong nhóm chia sẻ.

### 6.1. Từ viết tắt

Một từ viết tắt có thể có nhiều cách giải nghĩa trong các nhóm khác nhau. Không nên mở rộng dựa trên kiến thức phổ thông nếu ngữ cảnh chưa đủ.

Ví dụ `RC` có thể được dùng cho release candidate, request change hoặc một mã quy trình nội bộ. Hãy tìm lần xuất hiện đầu tiên, tiêu đề tài liệu, trường dữ liệu liên quan và hỏi người dùng nếu vẫn chưa rõ.

### 6.2. Mã và tên định danh

Mã như `P0`, `SEV1`, `R42` hoặc `ENV-PROD` có thể mã hóa mức độ ưu tiên, mức nghiêm trọng, phiên bản hoặc môi trường. Cần phân biệt mã định danh với khái niệm mà mã đại diện.

Nếu DSL hỗ trợ mã, cần định nghĩa miền giá trị, quy tắc kiểm tra và khả năng thay đổi. Không nên để người dùng phải nhớ một danh sách mã khó hiểu nếu có thể cung cấp tên miền dễ đọc hơn.

### 6.3. Tên gọi lịch sử

Một thuật ngữ có thể bắt nguồn từ công cụ cũ hoặc quy trình đã thay thế. Người dùng vẫn tiếp tục dùng tên cũ vì thói quen. Cần ghi nhận cả tên lịch sử và khái niệm hiện tại để tránh nhầm lẫn trong chuyển đổi.

### 6.4. Ẩn dụ và tiếng lóng

Các cách nói như “đóng băng nhánh”, “dọn backlog”, “đẩy nóng”, “mở cửa sổ” có thể là ẩn dụ đã ổn định trong cộng đồng. Hãy tìm hành động hoặc trạng thái thực tế mà ẩn dụ chỉ đến.

Không nên đưa tiếng lóng vào cú pháp chính thức chỉ vì nó phổ biến trong một nhóm nhỏ. Có thể dùng nó làm từ đồng nghĩa trong tài liệu, trong khi DSL sử dụng thuật ngữ chuẩn được xác nhận.

### 6.5. Từ mượn và trộn ngôn ngữ

Trong các nhóm kỹ thuật, một câu có thể trộn tiếng Việt và tiếng Anh: “rebase branch rồi resolve conflict trước khi merge”. Cần xác định các từ này là thuật ngữ có nghĩa chuyên biệt hay chỉ là cách diễn đạt thuận tiện.

Nếu DSL hỗ trợ tên tiếng Anh, tiếng Việt hoặc cả hai, cần có quy ước nhất quán về từ khóa, định danh và tài liệu. Tránh để cùng một khái niệm có nhiều cách viết không kiểm soát.

### 6.6. Danh từ hóa và cách nói rút gọn

Người dùng thường biến hành động thành danh từ như “phê duyệt”, “triển khai”, “đối soát” hoặc “rollback”. Danh từ hóa có thể che khuất tác nhân và trình tự.

Ví dụ “chờ phê duyệt” chưa cho biết ai phê duyệt, phê duyệt điều gì và điều kiện để chuyển sang bước tiếp theo. Đọc gần cần phục hồi cấu trúc hành động từ cụm danh từ này.

## 7. Quy trình đọc gần một tài liệu miền

Một quy trình thực hành có thể chia thành nhiều lượt đọc. Mỗi lượt tập trung vào một nhóm câu hỏi để tránh bỏ sót chi tiết.

### 7.1. Lượt đọc thứ nhất: nắm tình huống và mục đích

Đọc toàn bộ tài liệu mà chưa vội chuẩn hóa thuật ngữ. Xác định:

- Tài liệu được tạo ra để giải quyết vấn đề gì?
- Ai là người viết và người đọc dự kiến?
- Tài liệu mô tả quy trình, quy tắc, sự cố hay quyết định?
- Phần nào là hướng dẫn bắt buộc, phần nào là ví dụ hoặc giải thích?
- Tài liệu thuộc phiên bản và thời điểm nào?

Ghi một mô tả ngắn về ngữ cảnh để các lượt đọc sau không tách câu khỏi mục đích ban đầu.

### 7.2. Lượt đọc thứ hai: đánh dấu thuật ngữ và biến thể

Đánh dấu các danh từ, cụm danh từ, từ viết tắt, mã và cụm từ được lặp lại. Ghi nguyên văn cách viết, không sửa ngay về tên chuẩn.

Với mỗi mục, ghi vị trí xuất hiện và câu chứa nó. Nếu một từ xuất hiện nhiều lần với sắc thái khác nhau, giữ các trường hợp riêng để so sánh.

### 7.3. Lượt đọc thứ ba: đánh dấu hành động và quan hệ

Tìm động từ, cụm động từ và các từ thể hiện quan hệ. Xác định tác nhân, đối tượng, trạng thái trước, trạng thái sau và kết quả.

Ví dụ, “kỹ sư chuyển ticket sang trạng thái chờ xác nhận” chứa tác nhân `kỹ sư`, hành động `chuyển trạng thái`, đối tượng `ticket` và trạng thái đích `chờ xác nhận`.

### 7.4. Lượt đọc thứ tư: tìm quy tắc, điều kiện và ngoại lệ

Đánh dấu các từ chỉ nghĩa vụ, quyền hạn, phủ định, điều kiện, thứ tự và thời hạn. Viết lại quy tắc thành cấu trúc dễ kiểm tra, nhưng giữ nguyên phát biểu gốc bên cạnh.

Nếu câu thiếu chủ thể hoặc điều kiện, ghi câu hỏi mở. Không tự điền những phần bị lược bỏ.

### 7.5. Lượt đọc thứ năm: tìm điểm mơ hồ và mâu thuẫn

So sánh các lần dùng cùng thuật ngữ, các câu trong cùng tài liệu và các nguồn khác nhau. Ghi lại:

- Từ có nhiều nghĩa.
- Nhiều từ có thể chỉ cùng một khái niệm.
- Hai phát biểu có vẻ mâu thuẫn.
- Điều kiện hoặc ngưỡng chưa được định nghĩa.
- Quy tắc có ngoại lệ nhưng ngoại lệ chưa rõ.
- Trạng thái hoặc hành động không có định nghĩa.

Không nên xóa mâu thuẫn bằng cách chọn một phát biểu mà chưa hiểu vì sao chúng khác nhau. Có thể chúng mô tả các phiên bản quy trình hoặc vai trò khác nhau.

### 7.6. Lượt đọc thứ sáu: diễn giải và kiểm chứng

Tổng hợp phát hiện thành các giả thuyết về khái niệm và quy tắc. Đưa chúng cho chuyên gia miền xem lại bằng ví dụ cụ thể.

Hỏi người tham gia xem cách diễn giải có đúng trong trường hợp bình thường, trường hợp biên và ngoại lệ không. Nếu có bất đồng, ghi lại từng cách hiểu, người đưa ra và quyết định có thẩm quyền.

## 8. Kỹ thuật chú giải văn bản

Chú giải (annotation) giúp biến việc đọc cá nhân thành kết quả có thể trao đổi và kiểm tra. Có thể dùng màu, ký hiệu, bảng tính hoặc công cụ quản lý yêu cầu, miễn là quy ước được thống nhất.

### 8.1. Nhóm nhãn gợi ý

| Nhãn | Đánh dấu nội dung |
|---|---|
| TERM | Thuật ngữ hoặc cụm từ miền |
| ENTITY | Thực thể hoặc đối tượng được theo dõi |
| VALUE | Giá trị, đơn vị hoặc miền giá trị |
| ACTION | Hành động hoặc thao tác |
| EVENT | Sự kiện đã hoặc sẽ xảy ra |
| STATE | Trạng thái của đối tượng hoặc quy trình |
| RELATION | Quan hệ giữa các khái niệm |
| CONDITION | Điều kiện hoặc biểu thức logic |
| RULE | Quy tắc hoặc ràng buộc |
| EXCEPTION | Ngoại lệ hoặc điều kiện loại trừ |
| ROLE | Tác nhân, vai trò hoặc chủ thể có quyền |
| TIME | Thời điểm, thời hạn hoặc thứ tự |
| AMBIGUOUS | Cách diễn đạt có nhiều cách hiểu |
| ASSUMPTION | Giả định chưa được xác nhận |
| QUESTION | Điểm cần hỏi chuyên gia |

Một cụm từ có thể nhận nhiều nhãn. Ví dụ “chỉ quản lý được phép phê duyệt” chứa vai trò `quản lý`, hành động `phê duyệt` và quy tắc quyền hạn.

### 8.2. Giữ nguyên văn bản và thêm diễn giải riêng

Không nên sửa câu gốc để làm nó “đẹp” hơn rồi dùng bản đã sửa làm bằng chứng. Hãy giữ nguyên trích đoạn, sau đó thêm phần diễn giải, câu hỏi và trạng thái xác nhận.

Ví dụ một bản ghi chú giải:

| Trường | Nội dung minh họa |
|---|---|
| Trích đoạn | “QA xanh thì đẩy bản vá lên production.” |
| Thuật ngữ | QA xanh; bản vá; production |
| Hành động | Đẩy bản vá / triển khai |
| Điều kiện | QA xanh |
| Diễn giải tạm thời | Kết quả kiểm thử đạt là điều kiện để triển khai bản vá |
| Điểm chưa rõ | “QA xanh” gồm những kiểm thử nào? Ai phê duyệt? |
| Nguồn | Hướng dẫn phát hành, mục 4.2 |
| Trạng thái | Cần chuyên gia xác nhận |

### 8.3. Chú giải theo cụm thay vì chỉ theo từ

Một cụm như “trong vòng hai ngày làm việc kể từ khi nhận đủ hồ sơ” mang ý nghĩa thời hạn đầy đủ. Nếu chỉ đánh dấu từ “hai ngày”, sẽ mất mốc bắt đầu và điều kiện “nhận đủ hồ sơ”.

Tương tự, cụm “không được triển khai trừ khi có phê duyệt khẩn cấp” phải được giữ như một cấu trúc logic thống nhất, không tách thành các từ độc lập.

### 8.4. Phân biệt bằng chứng và nhận định

Nên có quy ước để phân biệt:

- **Trích dẫn:** Nội dung nguyên văn từ nguồn.
- **Quan sát:** Điều có thể chỉ ra trực tiếp trong văn bản.
- **Diễn giải:** Ý nghĩa mà nhà phân tích suy ra từ quan sát.
- **Giả thuyết:** Cách hiểu tạm thời cần kiểm tra.
- **Quyết định:** Cách hiểu đã được người có thẩm quyền xác nhận.

Phân biệt này giúp người đọc sau biết điều gì là bằng chứng, điều gì là suy luận và điều gì đã được thống nhất.

## 9. Phân biệt thuật ngữ, biến thể và khái niệm

Một phần quan trọng của đọc gần là xác định mối quan hệ giữa các cách gọi. Không nên giả định rằng từ giống nhau luôn cùng nghĩa hoặc từ khác nhau luôn chỉ những khái niệm khác nhau.

### 9.1. Đồng nghĩa theo miền

Hai cụm từ có thể được cộng đồng dùng thay thế cho nhau trong một ngữ cảnh. Ví dụ “yêu cầu thay đổi” và “change request” có thể là hai cách gọi cùng một loại hồ sơ.

Để xác nhận đồng nghĩa, hãy kiểm tra xem chúng có cùng thuộc tính, vòng đời, người chịu trách nhiệm và quy tắc xử lý không. Nếu chỉ giống nhau trong một số trường hợp, nên ghi là gần nghĩa hoặc có quan hệ thay vì gộp hoàn toàn.

### 9.2. Từ đa nghĩa

Một từ có thể chỉ nhiều khái niệm. Ví dụ “release” có thể là bản phát hành, hành động phát hành hoặc một mốc trong quy trình. Cần dựa vào vai trò ngữ pháp và ngữ cảnh để xác định nghĩa cụ thể.

### 9.3. Từ gần nghĩa nhưng khác ranh giới

“Lỗi”, “sự cố” và “cảnh báo” có thể cùng xuất hiện trong một báo cáo nhưng không nhất thiết là một loại đối tượng. Lỗi có thể là sai sót trong phần mềm; sự cố là gián đoạn dịch vụ; cảnh báo là tín hiệu cần chú ý. Một lỗi có thể gây ra sự cố, còn một cảnh báo có thể xuất hiện mà không có lỗi.

Nếu DSL cần biểu diễn các khái niệm này, phải giữ ranh giới mà miền thực sự sử dụng.

### 9.4. Tên chuẩn và bí danh

Sau khi xác nhận các biến thể, nhóm có thể chọn một tên chuẩn cho mô hình và DSL, đồng thời lưu bí danh để hỗ trợ tra cứu hoặc chuyển đổi tài liệu cũ.

Ví dụ:

| Tên chuẩn | Bí danh hoặc cách gọi khác | Ghi chú |
|---|---|---|
| Môi trường production | prod, môi trường thật | Chỉ môi trường phục vụ người dùng thực |
| Yêu cầu thay đổi | change request, CR | Hồ sơ đề nghị thay đổi có kiểm soát |
| Khôi phục phiên bản | rollback, quay lui | Cần phân biệt với khôi phục dữ liệu |

Tên chuẩn phải được cộng đồng chấp nhận. Nhà thiết kế không nên chọn thuật ngữ chỉ vì nó thuận tiện với mã nguồn.

## 10. Đọc gần các quy tắc và phát biểu chuẩn tắc

Tài liệu nội bộ thường chứa phát biểu quy định điều gì được phép, bắt buộc hoặc bị cấm. Những câu này có ảnh hưởng trực tiếp đến ngữ nghĩa của DSL.

### 10.1. Từ chỉ nghĩa vụ và quyền

Hãy phân biệt:

- **Bắt buộc:** “phải”, “bắt buộc”, “không được bỏ qua”.
- **Cho phép:** “có thể”, “được phép”, “có quyền”.
- **Khuyến nghị:** “nên”, “khuyến khích”.
- **Mô tả thực tế:** “thường”, “đôi khi”, “đa số trường hợp”.
- **Cấm:** “không được”, “nghiêm cấm”.

Một DSL chính sách có thể cần biểu diễn mức độ bắt buộc khác nhau, thay vì chỉ có điều kiện đúng hoặc sai.

### 10.2. Phạm vi áp dụng

Một quy tắc có thể áp dụng cho mọi đối tượng, một nhóm đối tượng, một vai trò, một môi trường hoặc một khoảng thời gian. Những cụm như “đối với dự án mới”, “trong môi trường production”, “chỉ với tài khoản quản trị” xác định phạm vi của quy tắc.

Nếu bỏ phạm vi, DSL có thể áp dụng quy tắc quá rộng. Hãy xác định đối tượng, vai trò, môi trường và thời điểm hiệu lực.

### 10.3. Thứ tự ưu tiên

Hai quy tắc có thể cùng áp dụng nhưng đưa ra hành động khác nhau. Tài liệu có thể dùng các cụm “ưu tiên”, “ngoại lệ”, “trừ trường hợp”, “theo quyết định của quản lý” để xác định cách giải quyết.

Đọc gần cần tìm xem thứ tự ưu tiên được nói rõ hay chỉ được hiểu ngầm. Nếu chưa rõ, ghi câu hỏi thay vì tự chọn quy tắc có vẻ hợp lý.

### 10.4. Hiệu lực và phiên bản

Phát biểu “từ đợt phát hành tháng 7, tất cả thay đổi phải có phê duyệt” chứa mốc hiệu lực. Cần xác định ngày bắt đầu, múi giờ, phạm vi hệ thống và cách xử lý các yêu cầu đã tạo trước mốc đó.

Tài liệu nội bộ cũ có thể vẫn được dùng để giải thích lịch sử nhưng không còn là nguồn quy tắc hiện hành. Phiên bản và ngày hiệu lực là phần của ngữ cảnh, không phải metadata tùy chọn.

## 11. Ví dụ đọc gần một đoạn ngôn ngữ nội bộ

Xét đoạn trao đổi giả định trong nhóm phát triển:

> Khi ticket P1 đã có owner và reproduction rõ ràng thì chuyển sang In Progress. Nếu chưa tái hiện được trên staging, giữ ở Needs Info. Fix phải qua regression test; chỉ merge khi CI xanh. Với hotfix production, người trực có thể bỏ qua bước chờ review nhưng phải ghi incident link và báo lại sau khi ổn định.

Đoạn này có vẻ dễ hiểu với người trong nhóm, nhưng chứa nhiều khái niệm, trạng thái, điều kiện và ngoại lệ. Đọc gần giúp tách chúng ra.

### 11.1. Nhận diện thuật ngữ nội bộ

| Cụm từ | Loại ứng viên | Câu hỏi cần làm rõ |
|---|---|---|
| Ticket P1 | Hồ sơ và mức ưu tiên | P1 được định nghĩa theo tác động hay thời hạn? |
| Owner | Vai trò chịu trách nhiệm | Một ticket có đúng một owner không? |
| Reproduction rõ ràng | Điều kiện chất lượng báo lỗi | Cần các bước, dữ liệu hay môi trường nào? |
| In Progress | Trạng thái | Ai được phép chuyển trạng thái? |
| Staging | Môi trường | Môi trường staging nào được dùng để tái hiện? |
| Needs Info | Trạng thái chờ thông tin | Ai phải cung cấp thông tin và có thời hạn không? |
| Regression test | Loại kiểm thử | Tập test bắt buộc nào được áp dụng? |
| CI xanh | Điều kiện pipeline | Những job nào phải thành công? |
| Hotfix production | Loại thay đổi khẩn cấp | Tiêu chí nào xác định hotfix? |
| Người trực | Vai trò | Lịch trực và phạm vi quyền hạn được xác định ở đâu? |
| Incident link | Tham chiếu | Loại incident nào được chấp nhận? |

### 11.2. Tách cấu trúc quy tắc

Có thể viết lại các ý chính dưới dạng phân tích trung gian:

| Quy tắc | Điều kiện | Hành động hoặc kết quả |
|---|---|---|
| R1 | Ticket có mức P1, có owner và reproduction rõ | Chuyển sang `In Progress` |
| R2 | Chưa tái hiện được trên staging | Giữ hoặc chuyển sang `Needs Info` |
| R3 | Fix cần được kiểm tra regression | Chạy regression test trước khi merge |
| R4 | CI chưa xanh | Không cho merge theo quy trình chuẩn |
| R5 | Là hotfix production và người thực hiện là người trực | Có thể bỏ qua bước chờ review theo ngoại lệ |
| R6 | Đã dùng ngoại lệ hotfix | Phải ghi incident link và báo lại sau khi ổn định |

Đây là cách diễn giải tạm thời. Cần xác nhận liệu R2 là trạng thái giữ nguyên hay hành động chuyển trạng thái, R3 có yêu cầu test đạt hay chỉ yêu cầu chạy test, và R5 có cần phê duyệt bổ sung hay không.

### 11.3. Phát hiện cấu trúc logic

Trong câu “chỉ merge khi CI xanh”, CI xanh là điều kiện cần. Câu này không nói CI xanh là điều kiện đủ để merge; có thể còn cần review hoặc các điều kiện khác.

Trong câu “người trực có thể bỏ qua bước chờ review”, từ “có thể” biểu đạt quyền hoặc ngoại lệ được phép. Nó không có nghĩa người trực luôn phải bỏ qua review. Cần làm rõ khi nào nên dùng ngoại lệ và liệu có yêu cầu phê duyệt sau đó.

Trong câu “phải ghi incident link và báo lại sau khi ổn định”, có hai nghĩa vụ được kích hoạt bởi việc sử dụng ngoại lệ. Cần xác định thời điểm “sau khi ổn định” và người chịu trách nhiệm báo lại.

### 11.4. Bản ghi chú giải

Một bản ghi chi tiết cho cụm “CI xanh” có thể như sau:

```text
Term: CI xanh
Context: Điều kiện trước khi merge fix
Literal evidence: "chỉ merge khi CI xanh"
Working interpretation: Các kiểm tra CI bắt buộc đều đạt
Unknowns:
  - Những job nào được xem là bắt buộc?
  - Job bị bỏ qua có được tính là xanh không?
  - Trạng thái đang chạy được xử lý thế nào?
  - Có ngoại lệ cho hotfix không?
Validation: Cần xác nhận với maintainer của pipeline
```

### 11.5. Từ phân tích đến biểu diễn DSL

Sau khi các định nghĩa được xác nhận, nhóm có thể thiết kế một cấu trúc DSL minh họa:

```text
quy_trinh xu_ly_ticket {
    khi ticket.priority == P1
         va ticket.owner != null
         va ticket.reproduction == CLEAR {
        chuyen_trang_thai ticket den IN_PROGRESS
    }

    chi_cho_phep_merge khi {
        regression_test == PASSED
        va ci_status == GREEN
    }

    ngoai_le hotfix_production {
        khi nguoi_thuc_hien.role == ON_CALL
        cho_phep bo_qua buoc_cho_review
        yeu_cau incident_link
        yeu_cau bao_cao_sau_khi_on_dinh
    }
}
```

Đây là bản nháp để minh họa mối liên hệ giữa phát biểu, mô hình miền và cấu trúc ngôn ngữ. Cú pháp cuối cùng cần dựa trên các định nghĩa đã thống nhất, đặc biệt là quyền hạn, trạng thái pipeline và cách xử lý ngoại lệ.

## 12. Từ kết quả đọc gần đến mô hình ngôn ngữ miền

Đọc gần tạo ra nhiều ghi chú và giả thuyết. Để dùng chúng trong thiết kế DSL, cần tổ chức thành những sản phẩm ổn định hơn.

### 12.1. Bảng thuật ngữ có ngữ cảnh

Mỗi thuật ngữ nên có:

- Tên nguyên văn và tên chuẩn dự kiến.
- Định nghĩa trong miền.
- Vai trò hoặc nhóm sử dụng.
- Ngữ cảnh và ví dụ xuất hiện.
- Từ đồng nghĩa, bí danh và từ dễ nhầm.
- Các thuộc tính hoặc quan hệ liên quan.
- Nguồn bằng chứng và phiên bản.
- Trạng thái xác nhận.

### 12.2. Bản đồ khái niệm

Nhóm các thuật ngữ thành thực thể, giá trị, trạng thái, hành động, sự kiện, vai trò và quy tắc. Nối chúng bằng quan hệ đã được xác nhận.

Ví dụ, trong quy trình ticket, có thể có `Ticket`, `Owner`, `Priority`, `Environment`, `Build`, `PipelineRun`, `Review` và `Incident`. Nhưng cần xác định `Build` và `PipelineRun` là đối tượng riêng hay chỉ là thuộc tính của ticket trong phạm vi DSL.

### 12.3. Danh mục quy tắc

Mỗi quy tắc nên được lưu dưới dạng có cấu trúc:

| Trường | Nội dung |
|---|---|
| ID | Mã quy tắc ổn định |
| Mô tả | Câu diễn giải ngắn |
| Điều kiện | Điều kiện cần và đủ đã xác định |
| Hành động | Hành động hoặc kết quả |
| Ngoại lệ | Trường hợp không áp dụng hoặc xử lý khác |
| Ưu tiên | Quan hệ với các quy tắc khác |
| Nguồn | Trích đoạn và tài liệu hỗ trợ |
| Chủ sở hữu | Người hoặc vai trò xác nhận |
| Hiệu lực | Phiên bản và thời điểm áp dụng |
| Trạng thái | Đề xuất, cần làm rõ hoặc đã xác nhận |

### 12.4. Danh sách câu hỏi mở

Những điều chưa rõ nên được gom thành danh sách có thể xử lý. Mỗi câu hỏi cần nói rõ thuật ngữ hoặc quy tắc liên quan, vì sao câu trả lời ảnh hưởng đến DSL và ai có thể xác nhận.

Không nên để câu hỏi quan trọng chỉ nằm trong ghi chú cá nhân hoặc bình luận rời rạc.

### 12.5. Ma trận truy xuất

Ma trận truy xuất nối nguồn ngôn ngữ với mô hình và cấu trúc DSL:

```text
Nguồn văn bản
    -> Trích đoạn
        -> Thuật ngữ / Quy tắc
            -> Khái niệm miền
                -> Cấu trúc DSL
                    -> Kiểm thử ngữ nghĩa
```

Khi thuật ngữ thay đổi hoặc tài liệu được cập nhật, nhóm có thể tìm các thành phần DSL và kiểm thử bị ảnh hưởng.

## 13. Kiểm chứng cách diễn giải

Đọc gần không hoàn tất khi nhà phân tích đã viết xong ghi chú. Cần kiểm tra diễn giải với cộng đồng miền và các nguồn liên quan.

### 13.1. Hỏi lại bằng ví dụ cụ thể

Thay vì hỏi “định nghĩa này đúng không?”, hãy hỏi điều gì xảy ra trong trường hợp cụ thể. Ví dụ, nếu “CI xanh” là điều kiện merge, hãy đưa ra trường hợp một job tùy chọn bị lỗi nhưng mọi job bắt buộc đều đạt. Người dùng có vẫn gọi đó là xanh không?

### 13.2. Dùng trường hợp biên

Kiểm tra giá trị ngay dưới, đúng bằng và ngay trên ngưỡng; trạng thái đang chạy, thất bại và bị bỏ qua; vai trò được phép và không được phép; trường hợp thiếu thông tin.

Trường hợp biên giúp phát hiện các định nghĩa chỉ đúng trong tình huống thông thường.

### 13.3. So sánh nhiều người dùng

Đưa cùng một phát biểu cho những vai trò khác nhau. Nếu kỹ sư, quản lý và nhân viên vận hành hiểu khác nhau, cần xác định đó là bất đồng thực sự, khác biệt góc nhìn hay sự khác nhau về quyền hạn.

### 13.4. Đối chiếu tài liệu chính thức

Khi lời nói và quy định mâu thuẫn, cần ghi nhận cả hai. Có thể quy trình thực tế đã thay đổi nhưng tài liệu chưa cập nhật, hoặc người nói đang mô tả ngoại lệ. Người có thẩm quyền phải xác định nguồn quy tắc chuẩn cho DSL.

### 13.5. Ghi nhận quyết định và bất đồng

Không xóa dấu vết của cách hiểu đã bị bác bỏ nếu nó giải thích vì sao có quyết định thiết kế. Lưu lại quyết định, lý do, người xác nhận và ngày hiệu lực giúp nhóm tránh tranh luận lại khi ngữ cảnh thay đổi.

## 14. Phối hợp đọc gần trong nhóm

Đọc gần có yếu tố diễn giải, vì vậy nhiều người có thể nhận ra những chi tiết khác nhau. Làm việc cộng tác giúp giảm phụ thuộc vào cách hiểu của một cá nhân.

### 14.1. Đọc độc lập trước khi thống nhất

Với một số đoạn quan trọng, có thể yêu cầu hai người chú giải độc lập. Sau đó so sánh các nhãn, định nghĩa và câu hỏi. Những điểm không thống nhất thường cho thấy thuật ngữ mơ hồ hoặc kiến thức ngầm chưa được nói rõ.

### 14.2. Thống nhất quy ước chú giải

Nhóm cần có hướng dẫn ngắn về cách gắn nhãn, cách trích dẫn và cách đánh dấu giả định. Nếu mỗi người dùng một cách phân loại, kết quả khó tổng hợp.

### 14.3. Có sự tham gia của chuyên gia miền

Nhà phân tích có thể phát hiện cấu trúc ngôn ngữ nhưng không tự quyết định ý nghĩa nghiệp vụ. Chuyên gia miền cần xác nhận các định nghĩa, ngưỡng, quyền hạn và ngoại lệ.

### 14.4. Quản lý bất đồng có căn cứ

Khi hai người đưa ra cách hiểu khác nhau, hãy đặt cạnh nhau trích đoạn hỗ trợ, ngữ cảnh và hệ quả nếu chọn mỗi cách. Tránh giải quyết bằng biểu quyết về từ ngữ nếu vấn đề thực chất là khác biệt quy trình hoặc quyền hạn.

## 15. Đọc gần và các phương pháp phân tích khác

Đọc gần có thể kết hợp với phỏng vấn, phân tích nội dung, phân tích diễn ngôn và xử lý ngôn ngữ tự nhiên. Tuy nhiên, mỗi phương pháp tập trung vào một khía cạnh khác nhau.

| Phương pháp | Trọng tâm | Giá trị đối với DSL |
|---|---|---|
| Đọc gần | Chi tiết từ ngữ, cấu trúc, ngữ cảnh và hàm ý của một văn bản | Làm rõ nghĩa thuật ngữ và quy tắc |
| Phỏng vấn | Kinh nghiệm, mục tiêu và cách giải thích của người tham gia | Bổ sung kiến thức ngầm và xác nhận ý nghĩa |
| Phân tích nội dung | Mẫu chủ đề và tần suất trong tập văn bản | Nhận ra chủ đề và nhóm khái niệm phổ biến |
| Phân tích diễn ngôn | Cách ngôn ngữ gắn với vai trò, quyền lực và thực hành xã hội | Hiểu vì sao các nhóm dùng cách gọi khác nhau |
| NLP | Tự động xử lý, gán nhãn và trích xuất văn bản | Hỗ trợ tìm kiếm và mở rộng quy mô phân tích |

Đọc gần có thể phát hiện một câu ngoại lệ rất hiếm nhưng có ý nghĩa lớn. Phân tích tần suất có thể bỏ qua câu đó. Ngược lại, phân tích tập văn bản lớn có thể phát hiện một thuật ngữ được dùng theo nhiều ngữ cảnh mà việc đọc một tài liệu riêng lẻ không cho thấy.

### 15.1. Kết hợp với NLP

NLP có thể gợi ý cụm từ, thực thể, động từ và quan hệ để người phân tích kiểm tra. Kết quả tự động nên được xem là chỉ dẫn tìm kiếm, không phải kết luận cuối cùng.

Ví dụ, công cụ có thể nhận diện “production” trong nhiều ticket. Đọc gần từng ngữ cảnh giúp xác định từ này chỉ môi trường triển khai, dữ liệu sản xuất hay một phiên bản đang phục vụ người dùng.

### 15.2. Kết hợp với phỏng vấn

Khi gặp một cụm từ khó hiểu, nhà phân tích có thể mang trích đoạn vào buổi phỏng vấn và hỏi người dùng diễn giải. Cần giữ nguyên câu gốc để tránh việc câu hỏi của nhà phân tích dẫn dắt người tham gia đến một cách hiểu đã định sẵn.

## 16. Chuyển phát hiện thành quyết định thiết kế DSL

Không phải mọi từ xuất hiện trong tài liệu đều cần trở thành từ khóa. Đọc gần cung cấp bằng chứng để quyết định khái niệm nào cần được thể hiện và ở mức trừu tượng nào.

### 16.1. Chọn thuật ngữ chuẩn

Chọn tên có nghĩa ổn định trong cộng đồng, được hiểu nhất quán và phù hợp với người dùng mục tiêu. Lưu bí danh để hỗ trợ tra cứu, nhưng tránh có nhiều từ khóa đồng nghĩa nếu chúng gây khó học hoặc làm tăng độ phức tạp parser.

### 16.2. Giữ những phân biệt có ý nghĩa

Nếu cộng đồng phân biệt `sự_cố` với `lỗi`, DSL nên cân nhắc giữ hai khái niệm. Nếu các biến thể chỉ là cách nói khác nhau của cùng một đối tượng, có thể dùng một tên chuẩn.

Quyết định phải dựa trên sự khác biệt về thuộc tính, vòng đời, quyền hạn hoặc quy tắc chứ không chỉ dựa trên hình thức từ ngữ.

### 16.3. Chuyển cách nói mơ hồ thành cấu trúc tường minh

Những cụm như “nhanh”, “sớm”, “đỏ”, “đầy đủ” hoặc “khẩn cấp” cần tiêu chí nếu chúng điều khiển hành vi. Có thể biểu diễn bằng ngưỡng, enum, trạng thái hoặc một hàm miền đã được định nghĩa.

Không nên biến một cách nói định tính thành số liệu cụ thể khi chưa được chuyên gia xác nhận.

### 16.4. Biểu diễn ngoại lệ và mức độ nghĩa vụ

Nếu miền phân biệt bắt buộc, cho phép, khuyến nghị và ngoại lệ, DSL cần có cách biểu đạt phù hợp. Không phải mọi chính sách đều chỉ là một điều kiện boolean.

### 16.5. Giữ cú pháp gần với tư duy miền

DSL nên giúp người dùng diễn đạt ý định bằng khái niệm họ quen thuộc. Tuy nhiên, cú pháp dễ đọc không đủ để bảo đảm đúng nghĩa. Mỗi cấu trúc cần có định nghĩa, quy tắc kiểu, hành vi và thông báo lỗi rõ ràng.

## 17. Sai lầm thường gặp khi đọc ngôn ngữ miền

### 17.1. Chỉ đọc tiêu đề hoặc phần tóm tắt

Tiêu đề cho biết chủ đề nhưng thường bỏ qua điều kiện và ngoại lệ. Cần đọc phần thân, ví dụ, ghi chú và ngữ cảnh tham chiếu.

### 17.2. Tách từ khỏi câu và tình huống

Một thuật ngữ không có nghĩa ổn định khi đứng riêng. Cần giữ câu, đoạn, vai trò và mục đích giao tiếp.

### 17.3. Coi cách nói tắt là định nghĩa đầy đủ

Người trong nhóm có thể nói “CI xanh” vì họ đã biết bộ job cần kiểm tra. DSL cần định nghĩa rõ job nào, trạng thái nào và cách xử lý khi một job không chạy.

### 17.4. Nhầm thói quen với quy tắc

“Thường làm như vậy” không đồng nghĩa “bắt buộc phải làm như vậy”. Phân biệt mô tả, khuyến nghị và nghĩa vụ.

### 17.5. Đồng nhất thuật ngữ giữa các bộ phận

Một từ có thể có nghĩa khác theo vai trò. Cần ghi ngữ cảnh sử dụng trước khi chọn tên chuẩn.

### 17.6. Xóa bỏ sự mơ hồ bằng suy đoán

Nếu không rõ “ngay”, “đủ”, “xanh” hoặc “khẩn cấp” nghĩa là gì, hãy ghi câu hỏi. Một DSL không nên biến phỏng đoán thành hành vi máy.

### 17.7. Chuẩn hóa quá sớm

Sửa tất cả biến thể về một thuật ngữ ngay từ đầu có thể làm mất dấu hiệu về vai trò, lịch sử hoặc quy trình khác nhau. Lưu cách dùng gốc trước khi quyết định hợp nhất.

### 17.8. Xem tài liệu cũ là hiện hành

Luôn kiểm tra phiên bản, ngày hiệu lực và nguồn xác nhận. Cách gọi lịch sử vẫn hữu ích để hiểu dữ liệu cũ nhưng không nhất thiết nên xuất hiện trong DSL hiện tại.

### 17.9. Chỉ dựa vào một người đọc

Diễn giải cá nhân có thể bỏ sót kiến thức hoặc cách dùng của nhóm khác. Với thuật ngữ và quy tắc quan trọng, nên có đọc chéo và xác nhận chuyên gia.

## 18. Quyền riêng tư và sử dụng tài liệu nội bộ

Ngôn ngữ nội bộ có thể chứa thông tin nhạy cảm như tên khách hàng, dữ liệu sự cố, thông tin bảo mật, cấu hình hạ tầng hoặc đánh giá nhân sự. Việc đọc gần cần tuân thủ quyền truy cập và mục đích sử dụng của tổ chức.

Một số nguyên tắc cần thực hiện:

- Chỉ dùng nguồn mà nhóm có quyền truy cập và quyền phân tích.
- Chỉ giữ thông tin nhận dạng khi thực sự cần cho mục tiêu miền.
- Ẩn danh dữ liệu cá nhân trong ví dụ và tài liệu chia sẻ.
- Không đưa bí mật, token, mật khẩu hoặc thông tin truy cập vào bảng thuật ngữ hay ví dụ DSL.
- Ghi rõ tài liệu nào được phép dùng trong công cụ phân tích tự động.
- Giới hạn quyền xem bản chú giải nếu nó chứa trích đoạn nhạy cảm.
- Tuân thủ chính sách lưu trữ, xóa và phiên bản hóa của tổ chức.

Mục tiêu là hiểu cấu trúc ngôn ngữ và quy tắc miền. Phần lớn trường hợp không cần lưu danh tính hoặc bí mật vận hành trong mô hình DSL.

## 19. Bộ câu hỏi thực hành khi đọc gần

Khi đọc một đoạn tài liệu, có thể dùng các câu hỏi sau để định hướng. Đây là công cụ tư duy, không phải biểu mẫu bắt buộc cho mọi đoạn.

**Về nguồn và ngữ cảnh:**

- Ai tạo ra phát biểu và dành cho ai?
- Nó thuộc quy trình, phiên bản và thời điểm nào?
- Đây là quy định, mô tả, ví dụ, giả định hay ý kiến?

**Về thuật ngữ:**

- Từ nào có nghĩa chuyên biệt?
- Có viết tắt, bí danh hoặc cách gọi lịch sử không?
- Cùng một từ có được dùng theo nhiều nghĩa không?
- Hai từ khác nhau có thật sự chỉ hai khái niệm khác nhau không?

**Về cấu trúc:**

- Ai thực hiện hành động nào trên đối tượng nào?
- Trạng thái trước và sau là gì?
- Điều kiện, ngoại lệ, phủ định và lượng từ nằm ở đâu?
- Có mốc thời gian, thứ tự hoặc phạm vi áp dụng không?

**Về ngữ nghĩa:**

- Từ nào thể hiện bắt buộc, cho phép hoặc khuyến nghị?
- Có kiến thức ngầm hoặc phần bị lược bỏ không?
- Có trường hợp biên làm thay đổi cách hiểu không?
- Những phần nào chưa đủ căn cứ để kết luận?

**Về DSL:**

- Khái niệm nào cần có trong mô hình miền?
- Phân biệt nào cần được giữ trong cú pháp hoặc kiểu dữ liệu?
- Quy tắc nào có thể kiểm tra tự động?
- Cần hỏi ai trước khi đưa cấu trúc vào ngôn ngữ?

## 20. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Close Reading (đọc gần) | Phương pháp đọc kỹ từ ngữ, cấu trúc và ngữ cảnh để diễn giải ý nghĩa có căn cứ |
| Internal Language (ngôn ngữ nội bộ) | Cách gọi, quy ước và lối diễn đạt của một cộng đồng miền |
| Domain Vocabulary | Tập thuật ngữ được dùng để nói về các khái niệm miền |
| Jargon (biệt ngữ) | Từ ngữ chuyên môn hoặc cách nói quen thuộc trong một nhóm |
| Register (ngữ vực) | Cách dùng ngôn ngữ gắn với vai trò, tình huống và mục đích giao tiếp |
| Annotation (chú giải) | Gắn nhãn và ghi nhận diễn giải cho đoạn văn bản |
| Ambiguity (mơ hồ) | Tình trạng một phát biểu có nhiều cách hiểu hợp lý |
| Connotation (hàm ý sắc thái) | Sắc thái hoặc liên tưởng đi kèm cách dùng từ |
| Normative Statement | Phát biểu quy định điều bắt buộc, được phép hoặc bị cấm |
| Alias (bí danh) | Tên gọi khác được dùng để tham chiếu cùng một khái niệm |
| Traceability (truy xuất nguồn gốc) | Khả năng nối khái niệm hoặc quy tắc với nguồn bằng chứng |
| Domain Model | Mô hình biểu diễn khái niệm, quan hệ và quy tắc của miền |

Đọc gần ngôn ngữ miền giúp nhóm thiết kế DSL hiểu không chỉ những từ cộng đồng sử dụng mà cả cách các từ đó tạo thành khái niệm, hành động và quy tắc trong công việc. Khi giữ nguyên bằng chứng, phân tích ngữ cảnh, đánh dấu điều chưa rõ và xác nhận với người có hiểu biết miền, nhóm có thể xây dựng một từ vựng nhất quán và một mô hình đủ chính xác. Từ nền tảng đó, cú pháp DSL mới có thể phản ánh cách tư duy của người dùng và diễn đạt những quy tắc mà hệ thống cần thực hiện.
