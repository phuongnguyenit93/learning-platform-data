# Mô tả nhu cầu bằng ngôn ngữ người dùng và bối cảnh nghiệp vụ

## 1. Vì sao mô tả nhu cầu đúng lại quan trọng trong Agile?

Trong phát triển phần mềm, một yêu cầu thường đến dưới dạng giải pháp đã được đề xuất: “Thêm một nút”, “Tạo một API”, “Đổi bảng dữ liệu”, “Xây màn hình quản lý”. Những mô tả này có thể giúp đội kỹ thuật hình dung việc cần thực hiện, nhưng chưa chắc cho biết **ai gặp vấn đề, vấn đề xuất hiện khi nào và người dùng cần đạt kết quả gì**.

Ví dụ, một người quản lý nền tảng học trực tuyến nói: “Hãy thêm nút Đăng ký khóa học ở trang chi tiết”. Nhóm có thể hoàn thành đúng yêu cầu đó mà học viên vẫn không thể bắt đầu học: người chưa đăng nhập không biết bước tiếp theo, khóa đã đóng vẫn nhận đăng ký, hoặc nút báo thành công dù hệ thống chưa lưu quyền học.

Hãy diễn đạt lại từ góc nhìn người dùng:

> “Khi đã chọn được một khóa miễn phí đang nhận học viên, tôi muốn đăng ký và biết chắc mình có thể bắt đầu học ngay, không phải liên hệ bộ phận hỗ trợ.”

Câu này cho thấy **bối cảnh** (đã tìm được khóa miễn phí đang mở), **mong muốn** (đăng ký), **kết quả** (bắt đầu học được) và một **nỗi lo thực tế** (không rõ đăng ký đã thành công hay chưa). Nhóm vẫn cần hỏi thêm để hiểu quy tắc đăng ký và cách đo thành công, nhưng đã có cơ sở tốt hơn để lựa chọn giải pháp.

Trong Agile, yêu cầu là điều **có thể được làm rõ và thích ứng khi có thông tin mới**. Viết bằng ngôn ngữ người dùng và bối cảnh nghiệp vụ giúp nhóm:

- Nhận ra khác biệt giữa **nhu cầu** với **giải pháp đề xuất**.
- Đặt đúng câu hỏi khi thông tin còn thiếu, thay vì tự suy đoán quy tắc.
- Trao đổi trên một cách hiểu chung giữa người dùng, Product Owner, thiết kế, lập trình, kiểm thử và vận hành.
- Chia nhỏ phạm vi thành các lát giá trị có thể kiểm chứng, cập nhật Product Backlog theo phản hồi sớm.
- Đánh giá kết quả người dùng nhận được, ngoài việc xác nhận “đã viết xong tính năng”.

> Tư tưởng cốt lõi: **Mô tả điều người dùng cần đạt trong một hoàn cảnh cụ thể trước khi chốt cách hệ thống sẽ làm.** Sau đó, dùng ví dụ nghiệp vụ và tiêu chí chấp nhận để biến nhu cầu thành công việc đủ rõ cho delivery.

## 2. Sáu thành phần của một mô tả nhu cầu có thể hành động

Một mô tả hữu ích không nhất thiết dài. Tuy nhiên, nhóm cần hiểu sáu thành phần sau thông qua story, cuộc trao đổi, tài liệu liên quan hoặc ví dụ cụ thể.

| Thành phần | Câu hỏi cần trả lời | Ví dụ: đăng ký khóa học |
| --- | --- | --- |
| **Người hưởng lợi** | Ai cần kết quả? Họ có vai trò và quyền hạn gì? | Học viên có tài khoản, đang muốn bắt đầu khóa miễn phí |
| **Bối cảnh và tác nhân kích hoạt** | Khi nào nhu cầu xuất hiện? Người đó đang làm gì? | Đang xem trang chi tiết của khóa còn nhận học viên |
| **Khó khăn hiện tại** | Họ chưa làm được điều gì hoặc gặp trở ngại nào? | Phải nhờ hỗ trợ xác nhận đăng ký hoặc không biết mình đã có quyền học |
| **Kết quả mong muốn** | Khi thành công, người đó có thể làm gì khác đi? | Tự đăng ký và mở được bài học đầu tiên |
| **Quy tắc, ràng buộc** | Điều kiện nào phải đúng, không được vi phạm? | Chỉ học viên hợp lệ; không tạo đăng ký trùng; không cấp quyền cho khóa đã đóng |
| **Bằng chứng và cách kiểm chứng** | Vì sao tin đây là nhu cầu? Dấu hiệu nào cho thấy đã giải quyết được? | Phản hồi từ học viên, lượt liên hệ hỗ trợ, tỷ lệ đăng ký và truy cập bài đầu thành công |

**Vai trò không đồng nghĩa một con người cố định.** Một người có thể vừa là học viên vừa là giảng viên; hệ thống cần xét vai trò trong **ngữ cảnh hành động**. Tương tự, một người mua khóa cho nhân viên và người trực tiếp học có thể có mục tiêu khác nhau, nên không nên gộp nhu cầu của họ vào một câu chung chung “người dùng muốn quản lý khóa”.

**Đừng biến mọi thành phần thành một biểu mẫu bắt buộc.** User story có thể rất ngắn nếu cả nhóm đã chia sẻ đủ bối cảnh; tình huống phức tạp cần thêm sơ đồ quy trình, glossary, tiêu chí chấp nhận hoặc ví dụ để tránh hiểu sai.

### Phân biệt sự kiện, giả thuyết và quyết định

Giả sử có báo cáo: “Chỉ 40% người nhấn Đăng ký tiếp tục mở bài đầu”. Đây là **tín hiệu**; nó chưa tự nói vì sao phần còn lại không học. Những nhận định sau cần được phân biệt:

- **Sự kiện đã đo:** trong nhóm và khoảng thời gian được xác định, 40% người đã nhấn Đăng ký có mở bài đầu.
- **Giả thuyết cần kiểm tra:** nhiều người không nhận ra bước tiếp theo hoặc gặp lỗi cấp quyền.
- **Đề xuất giải pháp:** tự động chuyển đến bài đầu sau khi đăng ký thành công.
- **Quyết định:** nhóm có thể thử chuyển hướng tự động trong phạm vi nhỏ sau khi kiểm tra phản hồi, tính khả thi và ràng buộc.

Nếu nhóm xem đề xuất là “yêu cầu bắt buộc” trước khi xác nhận vấn đề, khả năng thích ứng sẽ giảm. **Ngôn ngữ người dùng** giúp giữ trọng tâm vào kết quả, còn **bằng chứng** giúp lựa chọn phương án.

## 3. Lắng nghe người dùng trong bối cảnh nghiệp vụ thật

Người dùng đôi khi nói về một nút bấm, đôi khi nói về một công việc đang làm, đôi khi chỉ mô tả triệu chứng: “Tôi cứ phải kiểm tra lại”, “Không biết đơn đã được chấp nhận chưa”, “Mất nhiều bước”. Nhóm cần tìm hiểu **hành động thật và điều kiện xảy ra**, không chỉ hỏi “Bạn muốn thêm chức năng gì?”.

### 3.1. Những câu hỏi khám phá có ích

Khi gặp một đề xuất “Cần trang quản lý đăng ký”, có thể hỏi:

1. **Lần gần nhất** anh/chị gặp vấn đề này là khi nào? Lúc đó đang cố hoàn thành công việc gì?
2. Điều gì báo hiệu phải thực hiện công việc đó? Dữ liệu hoặc thông tin nào đã có sẵn?
3. Hiện anh/chị thực hiện những bước nào, dùng công cụ gì, trao đổi với ai?
4. Bước nào thường mất thời gian, gây nhầm lẫn hoặc phải làm lại? Có thể xem một tình huống thực tế không?
5. Khi có ngoại lệ (học viên đã đăng ký, khóa đã đóng, mạng yếu), quy trình hiện tại xử lý thế nào?
6. Ai có quyền phê duyệt, hủy hoặc thay đổi đăng ký? Ai chịu hậu quả nếu xử lý sai?
7. Nếu vấn đề được giải quyết tốt, điều gì sẽ thay đổi đáng kể với anh/chị hoặc tổ chức?
8. Có điều kiện nào bắt buộc từ chính sách, bảo mật, dữ liệu hoặc vận hành không?

Nên ưu tiên câu hỏi về **trải nghiệm đã xảy ra**, quan sát thao tác hoặc dữ liệu từ hệ thống; câu trả lời cho câu giả định “Nếu có nút này, anh/chị có dùng không?” dễ tạo kỳ vọng nhưng chưa chắc phản ánh hành vi thực tế.

### 3.2. Phân biệt các nguồn nhu cầu

| Nguồn | Ví dụ | Điểm cần kiểm tra |
| --- | --- | --- |
| **Người dùng trực tiếp** | Học viên muốn biết trạng thái đăng ký | Nhu cầu xuất hiện ở bước nào, tần suất và hệ quả thực tế |
| **Người sử dụng nghiệp vụ nội bộ** | Nhân viên hỗ trợ cần xác định vì sao một đăng ký thất bại | Quyền truy cập, dữ liệu được xem, tác động đến thời gian hỗ trợ |
| **Stakeholder kinh doanh** | Muốn tăng số học viên bắt đầu học | Outcome cần đạt, giả thuyết giải pháp và cách đo tác động |
| **Nhóm vận hành/kỹ thuật** | Muốn giảm lỗi khi xử lý đăng ký đồng thời | Rủi ro hệ thống, độ tin cậy, yêu cầu phục hồi |
| **Quy định/chính sách** | Không được tiết lộ thông tin học viên khác | Phạm vi áp dụng, tiêu chuẩn bắt buộc, cách kiểm chứng |

Một stakeholder có thể đề xuất phương án hợp lý, nhưng **người ra quyết định không nhất thiết là người trực tiếp sử dụng**. Vì vậy, hãy kiểm chứng tác động với cả người thụ hưởng và người chịu ràng buộc.

### 3.3. Dùng job story khi vai trò chưa nói hết bối cảnh

Mẫu user story thông dụng nhấn mạnh vai trò; trong một số tình huống, mô tả theo hoàn cảnh và động lực giúp rõ hơn:

> “Khi vừa hoàn tất bài học và chuẩn bị rời ứng dụng, tôi muốn biết phần học tiếp theo mất khoảng bao lâu, để quyết định học tiếp ngay hay lưu lại cho lần sau.”

Đây là ví dụ **job story**: khi [tình huống], tôi muốn [động lực/hành động], để [kết quả]. Nó hữu ích khi cùng một vai trò có nhu cầu khác nhau ở các thời điểm khác nhau. Không cần ép tất cả nhu cầu phải có cả user story lẫn job story; chọn cấu trúc làm rõ vấn đề tốt nhất.

## 4. Dùng ngôn ngữ nghiệp vụ nhất quán

Một yêu cầu có thể hiểu sai ngay cả khi mọi người đều nói tiếng Việt. Ví dụ, trong nền tảng học, “đăng ký” có thể nghĩa là tạo tài khoản, ghi danh vào khóa, đặt chỗ trong lớp, hoặc thanh toán mua khóa. Nếu một bên gọi “đơn đăng ký” là yêu cầu chờ duyệt nhưng bên khác hiểu là quyền học đã có hiệu lực, nhóm có thể xây hệ thống cấp quyền sai.

**Ngôn ngữ nghiệp vụ dùng chung (shared domain language)** là tập thuật ngữ, quy tắc và ví dụ mà người am hiểu nghiệp vụ và nhóm phát triển thống nhất khi trao đổi. Trong các cách tiếp cận như Domain-Driven Design, khái niệm *ubiquitous language* nhấn mạnh sử dụng nhất quán ngôn ngữ trong phạm vi một mô hình nghiệp vụ. Với Agile, mục đích thực tế là giảm số lần phải giải thích lại và tránh quyết định kỹ thuật dựa trên từ ngữ mơ hồ.

### Glossary minh họa cho nghiệp vụ học trực tuyến

| Thuật ngữ | Định nghĩa để thảo luận | Điểm dễ nhầm cần làm rõ |
| --- | --- | --- |
| **Tài khoản học viên** | Danh tính dùng để đăng nhập và lưu thông tin người học | Tạo tài khoản khác với ghi danh vào khóa |
| **Khóa học** | Chương trình học có nội dung và chính sách truy cập | Khác một lớp học tổ chức theo lịch cố định |
| **Ghi danh/đăng ký khóa** | Hành động tạo quan hệ học viên – khóa theo quy tắc | Đã yêu cầu, đang chờ duyệt hay đã có hiệu lực? |
| **Quyền truy cập** | Khả năng mở nội dung được phép học | Không mặc nhiên đồng nghĩa đã thanh toán |
| **Khóa đang mở đăng ký** | Khóa cho phép tạo đăng ký mới ở thời điểm xét | Khác trạng thái khóa đang xuất bản hoặc đang diễn ra |
| **Đăng ký trùng** | Nhiều bản ghi hiệu lực không hợp lệ cho cùng học viên và khóa | Cần quy tắc rõ về đăng ký lại sau khi hủy |
| **Hoàn thành bài học** | Trạng thái đạt điều kiện hoàn thành được thống nhất | Khác “đã mở”, “đã xem” hoặc “đã đánh dấu xong” |
| **Hủy đăng ký** | Chấm dứt quan hệ đăng ký theo chính sách | Cần xác định tác động đến lịch sử, tiến độ và hoàn tiền |

Các định nghĩa trên chỉ là **ví dụ minh họa**, không mặc định là quy tắc của một nền tảng cụ thể. Tổ chức có thể dùng thuật ngữ khác; điều quan trọng là định nghĩa được xác nhận với người am hiểu nghiệp vụ.

Nếu cùng một từ có nghĩa khác nhau giữa bộ phận đào tạo và thanh toán, nên nêu rõ **ngữ cảnh áp dụng**, thay vì cố tạo một định nghĩa dùng cho mọi nơi. Ví dụ “hoàn tất” trong nội dung học có thể khác “hoàn tất” trong giao dịch thanh toán.

### Diễn tả quy tắc nghiệp vụ bằng câu có thể kiểm tra

**Mơ hồ:** “Học viên chỉ được đăng ký khóa phù hợp.”

**Rõ hơn:** “Học viên đã đăng nhập có thể ghi danh một lần vào khóa miễn phí còn mở đăng ký. Hệ thống từ chối ghi danh mới khi khóa đã đóng hoặc học viên không đủ điều kiện theo chính sách đã công bố.”

Nhưng câu thứ hai vẫn còn câu hỏi: “đủ điều kiện” theo tiêu chí gì? Nếu yêu cầu trước tiên phải hoàn tất một khóa nhập môn, nhóm cần thêm ví dụ:

> “Khóa Nâng cao yêu cầu người học hoàn tất khóa Nhập môn. Trạng thái chỉ ‘đã mở bài cuối’ chưa đáp ứng điều kiện.”

Nhóm không nên tự đặt chính sách thay cho người có thẩm quyền. Câu hỏi chưa có đáp án cần được ghi rõ và xác nhận trước khi triển khai hành vi phụ thuộc vào nó.

## 5. User story: diễn đạt nhu cầu để trao đổi, không phải bản đặc tả đầy đủ

Mẫu phổ biến:

> **Là** [vai trò/người hưởng lợi], **tôi muốn** [khả năng hoặc kết quả] **để** [lợi ích/mục đích].

Ví dụ:

> “Là học viên đã chọn một khóa miễn phí còn mở, tôi muốn ghi danh vào khóa để có thể bắt đầu học nội dung được phép truy cập.”

Câu này là **điểm khởi đầu cho cuộc trao đổi**, chưa đủ chỉ dẫn triển khai. Người viết và người làm cần thống nhất ý nghĩa của “ghi danh”, các điều kiện và phản hồi thành công/thất bại.

Một khung hữu ích là **3C**:

1. **Card:** mô tả ngắn, dễ nhớ về nhu cầu và lợi ích.
2. **Conversation:** trao đổi với người dùng/người hiểu nghiệp vụ để làm rõ bối cảnh, ngoại lệ và quy tắc.
3. **Confirmation:** xác định tiêu chí chấp nhận bằng những hành vi có thể quan sát, kiểm thử.

### Từ câu kỹ thuật đến câu mô tả giá trị

| Câu ban đầu | Điều đang thiếu | Cách diễn đạt gợi ý |
| --- | --- | --- |
| “Tạo bảng enrollments và endpoint POST /enroll.” | Ai cần, tình huống nào và kết quả gì? | “Là học viên hợp lệ, tôi muốn ghi danh khóa đang mở để có thể vào học.” |
| “Thêm bộ lọc trạng thái đơn hàng.” | Ai tra cứu, gặp khó khăn gì? | “Là nhân viên hỗ trợ, khi có khách hỏi về đơn, tôi muốn tìm các đơn đang chờ xác nhận để trả lời chính xác.” |
| “Làm dashboard tiến độ.” | Quyết định nào phụ thuộc dữ liệu? | “Là giảng viên phụ trách lớp, tôi muốn biết học viên nào chưa bắt đầu bài được giao để hỗ trợ đúng lúc.” |
| “Gửi nhiều thông báo hơn.” | Người dùng cần thông tin gì, khi nào? | “Là học viên có buổi học sắp diễn ra, tôi muốn được nhắc trước giờ học theo kênh đã chọn để không bỏ lỡ.” |
| “Tối ưu truy vấn SQL.” | Ai chịu ảnh hưởng và giới hạn chất lượng nào? | “Khi xem danh sách khóa, học viên cần nhận phản hồi trong ngưỡng hiệu năng đã thống nhất để không bị gián đoạn tra cứu.” |

Các câu viết lại là **đề xuất để bắt đầu xác nhận nhu cầu**, không phải minh chứng rằng vấn đề đó đã tồn tại. Đừng thêm một “lợi ích” không có bằng chứng chỉ để làm câu story nghe có vẻ hoàn chỉnh.

### Khi nào cần mô tả khác user story?

Không phải mọi yêu cầu đều là nhu cầu tương tác trực tiếp. Việc vá lỗ hổng bảo mật, đảm bảo khả năng phục hồi dữ liệu hoặc thực hiện thay đổi bắt buộc theo quy định cũng là công việc có giá trị, dù rất khó viết tự nhiên theo mẫu “Là người dùng, tôi muốn…”.

Với các yêu cầu đó, ghi rõ **rủi ro cần kiểm soát**, hệ thống liên quan, điều kiện chấp nhận và lý do nghiệp vụ; không cần gắn một vai trò người dùng giả tạo. Agile khuyến khích giao tiếp và kiểm chứng, không bắt buộc mọi hạng mục đều có cùng một kiểu câu.

## 6. Bối cảnh nghiệp vụ không nằm trọn trong một câu story

Ngôn ngữ người dùng hữu ích nhất khi đi cùng **luồng hành động, quy tắc và ngoại lệ**. Hãy mô tả một hành trình tối thiểu:

~~~text
Người học tìm khóa → Xem điều kiện → Chọn đăng ký → Hệ thống xác nhận
                                                ↓
                                       Truy cập bài học đầu
~~~

Với hành trình đó, nhóm có thể hỏi:

- Học viên đã đăng nhập chưa? Nếu chưa, sau khi đăng nhập có quay lại khóa vừa chọn không?
- Khóa còn cho phép đăng ký không? Trạng thái cập nhật khi nào?
- Học viên đã có đăng ký hiệu lực chưa? Điều gì xảy ra nếu bấm lại nhiều lần?
- Khóa miễn phí khác khóa trả phí như thế nào? Có tình huống cần chờ duyệt không?
- Khi hệ thống lỗi, người dùng thấy thông báo nào, trạng thái lưu trữ thực tế ra sao?
- Quyền truy cập được cấp ngay hay cần bước xác nhận khác?
- Tác động đến thông tin cá nhân, lịch sử đăng ký và bộ phận hỗ trợ là gì?

### Bốn loại tình huống nên trao đổi

| Loại | Ví dụ | Mục đích |
| --- | --- | --- |
| **Luồng chính** | Học viên hợp lệ đăng ký thành công khóa miễn phí đang mở | Xác nhận kết quả cốt lõi |
| **Biến thể hợp lệ** | Học viên đã ghi danh mở lại khóa học | Hiểu khác biệt hành vi và trạng thái |
| **Ngoại lệ nghiệp vụ** | Khóa đã đóng, học viên chưa đáp ứng điều kiện tiên quyết | Tránh cấp quyền hoặc ghi dữ liệu sai |
| **Lỗi kỹ thuật và khôi phục** | Người dùng bấm lại khi mạng chậm hoặc yêu cầu gửi trùng | Giữ hệ thống nhất quán và thông báo phù hợp |

Hãy ưu tiên những trường hợp có ảnh hưởng lớn đến **kết quả và rủi ro**. Không nên cố liệt kê mọi trường hợp tưởng tượng trước khi có bằng chứng; đồng thời, các ngoại lệ liên quan phân quyền, tiền, dữ liệu và toàn vẹn nghiệp vụ cần được xem xét sớm.

### Quy tắc và quyết định nằm ở đâu?

Một số chi tiết là **quy tắc nghiệp vụ**: học viên đủ điều kiện được ghi danh khi khóa đang mở; trạng thái khóa có ý nghĩa gì. Một số là **lựa chọn thiết kế**: thông báo bằng toast hay trang xác nhận; gọi API theo kiểu nào. Hãy giữ hai loại rõ ràng:

| Quy tắc/kết quả nghiệp vụ | Lựa chọn giải pháp có thể thay đổi |
| --- | --- |
| Học viên biết đăng ký đã thành công và mở được bài đầu | Hiện hộp thoại, chuyển hướng hoặc nút “Vào học” |
| Không cấp quyền học khi đăng ký không hợp lệ | Kiểm tra phân quyền trong service nào, cache ra sao |
| Không tồn tại hai đăng ký hiệu lực trùng nhau theo quy tắc | Dùng khóa duy nhất, transaction hoặc cơ chế idempotency thích hợp |
| Nhân viên hỗ trợ có thể xác định trạng thái đúng của đăng ký | Dùng bảng quản trị, truy vấn báo cáo hoặc công cụ nội bộ |

Lựa chọn kỹ thuật cần được đánh giá cùng nhóm triển khai và ràng buộc hệ thống. Nhưng cách mô tả nhu cầu nên không khóa cứng vào một triển khai khi chưa có lý do chính đáng.

## 7. Viết tiêu chí chấp nhận từ góc nhìn hành vi

**Acceptance criteria** giúp cả nhóm biết khi nào một story đáp ứng đúng hành vi mong muốn. Chúng không thay thế toàn bộ chiến lược kiểm thử hoặc Definition of Done; chúng trả lời chủ yếu **story này cần làm đúng những gì trong các tình huống quan trọng**.

Có thể viết bằng câu ngắn, bảng ví dụ hoặc Gherkin (Given–When–Then). Gherkin hữu ích khi người dùng, người hiểu nghiệp vụ, lập trình viên và kiểm thử cùng thảo luận ví dụ cụ thể.

### Ví dụ: ghi danh khóa học miễn phí

~~~gherkin
Feature: Ghi danh vào khóa học miễn phí

  Scenario: Học viên hợp lệ ghi danh thành công
    Given học viên đã đăng nhập
    And khóa học là khóa miễn phí đang mở đăng ký
    And học viên chưa có đăng ký hiệu lực cho khóa đó
    When học viên xác nhận ghi danh
    Then hệ thống ghi nhận đúng một đăng ký hiệu lực
    And học viên nhận được xác nhận thành công
    And học viên được truy cập nội dung học được phép

  Scenario: Học viên gửi lại yêu cầu ghi danh
    Given học viên đã có đăng ký hiệu lực cho khóa học
    When học viên gửi lại yêu cầu ghi danh
    Then hệ thống không tạo thêm đăng ký hiệu lực trùng
    And học viên nhận được thông tin trạng thái phù hợp

  Scenario: Khóa học đã đóng đăng ký
    Given khóa học không còn nhận đăng ký mới
    When học viên gửi yêu cầu ghi danh
    Then hệ thống từ chối tạo đăng ký hiệu lực mới
    And hiển thị lý do phù hợp với người học

  Scenario: Người dùng không có quyền ghi danh thay học viên khác
    Given người dùng không có quyền hành động thay học viên khác
    When người dùng gửi yêu cầu ghi danh cho tài khoản học viên khác
    Then hệ thống từ chối yêu cầu
    And không thay đổi quyền học của tài khoản đó
~~~

Các tình huống trên là minh họa cho **một chính sách giả định**; nếu nghiệp vụ thật yêu cầu chờ duyệt hoặc đăng ký hộ, tiêu chí phải thay đổi theo chính sách đã xác nhận. Chỉ vô hiệu hóa nút ở giao diện chưa đủ để ngăn yêu cầu trái phép; quyền truy cập và toàn vẹn dữ liệu phải được bảo vệ ở các thành phần có thẩm quyền.

### Tiêu chí tốt có những đặc điểm nào?

1. **Quan sát và kiểm chứng được:** nêu đầu vào, hành động và kết quả có thể xác nhận.
2. **Dùng khái niệm nghiệp vụ rõ ràng:** “đăng ký hiệu lực”, “khóa đang mở”, “có quyền truy cập” cần được định nghĩa.
3. **Bao phủ luồng chính và ngoại lệ có rủi ro:** không chỉ thử trường hợp thành công.
4. **Ít áp đặt cấu trúc kỹ thuật:** không yêu cầu tên bảng, lớp hay framework nếu chúng không phải yêu cầu bên ngoài.
5. **Đủ nhỏ và có giới hạn phạm vi:** nhóm biết biến thể nào sẽ làm sau.

**Mơ hồ:** “Hệ thống xử lý nhanh và chính xác.”

**Có thể kiểm chứng hơn:** “Với điều kiện thử nghiệm và mức tải đã thống nhất, thao tác xác nhận đăng ký phải phản hồi trong ngưỡng hiệu năng được nhóm sản phẩm và kỹ thuật phê duyệt; nếu xử lý chưa hoàn tất, trạng thái hiển thị không được khẳng định sai rằng quyền học đã được cấp.”

Ngưỡng cụ thể cần lấy từ yêu cầu dịch vụ, dữ liệu đo hoặc thỏa thuận có trách nhiệm. Không tự đặt một con số tùy ý rồi coi là quy chuẩn chung.

## 8. Chia nhu cầu lớn thành lát có giá trị và kiểm chứng được

Một yêu cầu như “quản lý toàn bộ việc học của học viên” quá lớn để bàn giao sớm. Nếu chỉ tách thành “xây database”, “viết backend”, “dựng frontend”, từng phần chưa đem lại hành vi sử dụng hoàn chỉnh.

Thay vào đó, áp dụng **story mapping**: mô tả hành trình chính và chọn đường đi tối thiểu có ích.

~~~mermaid
flowchart LR
    A["Khám phá khóa"] --> B["Xem điều kiện"]
    B --> C["Ghi danh"]
    C --> D["Bắt đầu học"]
    D --> E["Quay lại học"]
    C --> F{"Đăng ký hợp lệ?"}
    F -->|"Có"| D
    F -->|"Không"| G["Thông báo và hướng xử lý"]
~~~

Ví dụ chia lát:

| Lát | Nhu cầu người dùng có thể kiểm chứng | Phạm vi chưa đưa vào |
| --- | --- | --- |
| **1. Ghi danh khóa miễn phí** | Học viên hợp lệ tự ghi danh và mở được bài đầu | Thanh toán, mã giảm giá, danh sách chờ |
| **2. Xem các khóa của tôi** | Học viên quay lại và thấy khóa đã ghi danh | Phân tích tiến độ nâng cao |
| **3. Hủy ghi danh theo chính sách** | Học viên đủ điều kiện chủ động ngừng tham gia và hiểu hệ quả | Hoàn tiền cho khóa trả phí |
| **4. Đăng ký khóa có phí** | Học viên thanh toán hợp lệ rồi có quyền học | Nhiều phương thức và chính sách giá phức tạp |

Các lát này là **ứng viên**, không phải trình tự bắt buộc. Nếu dữ liệu cho thấy khó khăn lớn nhất xảy ra ở việc tìm khóa, nhóm có thể ưu tiên cải thiện khám phá trước. Story mô tả nhu cầu là cơ sở để **thương lượng phạm vi**, không phải cam kết giữ nguyên kế hoạch bất kể phản hồi.

Một story hữu ích thường đáp ứng gợi ý **INVEST**: Independent (hạn chế phụ thuộc), Negotiable (có thể trao đổi), Valuable (có giá trị), Estimable (đủ rõ để ước lượng), Small (đủ nhỏ), Testable (có thể kiểm chứng). Đây là công cụ gợi ý, không phải điều kiện tuyệt đối; các phụ thuộc kỹ thuật thực tế cần được thể hiện minh bạch.

## 9. Từ ngôn ngữ nghiệp vụ đến phối hợp kỹ thuật và backlog

Agile nhấn mạnh hợp tác liên tục: người hiểu nghiệp vụ cần tham gia giải thích **vì sao**, đội phát triển cần làm rõ **cái gì có thể thực hiện và rủi ro nào**, người kiểm thử giúp chuyển những câu chưa rõ thành ví dụ có thể kiểm chứng.

### Một buổi làm rõ story hiệu quả

Trước khi bắt đầu, Product Owner hoặc người sở hữu nhu cầu chuẩn bị câu chuyện người dùng, mục tiêu và thông tin đã có. Buổi trao đổi có thể đi theo trình tự:

1. **Đặt bối cảnh:** Ai đang cần kết quả, khi nào và vì sao?
2. **Nêu ví dụ cụ thể:** Một trường hợp thành công, một biến thể, một ngoại lệ.
3. **Làm rõ thuật ngữ:** Những từ có thể hiểu khác nhau được định nghĩa và ghi lại.
4. **Xác định ranh giới:** Điều kiện bắt buộc, dữ liệu liên quan, cách xử lý quyền và lỗi.
5. **Chọn lát nhỏ nhất:** Phạm vi nào đủ để người dùng thực hiện một hành vi có ý nghĩa?
6. **Thống nhất tiêu chí chấp nhận:** Cách quan sát kết quả, cả trường hợp không thành công.
7. **Ghi câu hỏi mở:** Ai xác nhận chính sách, thời điểm nào và điều gì sẽ xảy ra nếu chưa có câu trả lời?

Kỹ thuật **example mapping** có thể dùng các nhóm thông tin: story, quy tắc, ví dụ và câu hỏi chưa rõ. Ví dụ với “hủy ghi danh”:

| Nhóm | Nội dung thảo luận |
| --- | --- |
| Story | Học viên muốn hủy ghi danh khi không tiếp tục học |
| Quy tắc | Chỉ được tự hủy khi trạng thái và chính sách khóa cho phép |
| Ví dụ | Chưa học bài nào; đã hoàn thành một phần; khóa đã kết thúc |
| Câu hỏi mở | Tiến độ có được giữ lại nếu ghi danh lại? Có hoàn phí không? |

Không cần giải quyết mọi câu hỏi trong một cuộc họp, nhưng không được **giả vờ đã rõ** những quy tắc có thể gây hậu quả. Nhóm có thể tách lát đầu chỉ hỗ trợ trường hợp đủ rõ, đồng thời nhờ người có thẩm quyền xác nhận các ngoại lệ trước khi phát triển tiếp.

### Definition of Ready và Definition of Done

Một nhóm có thể đặt **chính sách sẵn sàng để bắt đầu**: hiểu kết quả, có tiêu chí chấp nhận chính, biết rủi ro quan trọng và phạm vi hợp lý. Chính sách này giúp phối hợp, nhưng **Definition of Ready không phải thành phần bắt buộc của Scrum** và không nên trở thành cổng giấy tờ làm ngừng mọi trao đổi.

**Definition of Done (DoD)** nói về mức chất lượng bắt buộc để một increment được xem là hoàn tất. Acceptance criteria của story giải thích hành vi nghiệp vụ riêng của story; DoD bao gồm các yêu cầu chung như kiểm thử, review, tích hợp, bảo mật hoặc vận hành phù hợp. Một story thỏa tiêu chí giao diện nhưng chưa đảm bảo phân quyền chưa thể được xem là increment hoàn chỉnh.

### Scrum, Kanban và XP hỗ trợ ra sao?

| Cách làm | Liên hệ với mô tả nhu cầu |
| --- | --- |
| **Scrum** | Product Owner làm rõ và sắp xếp Product Backlog; Scrum Team kiểm tra kết quả, nhận phản hồi qua Sprint Review và thích ứng kế hoạch. Refinement giúp story tiến tới mức hiểu biết đủ để chọn vào Sprint. |
| **Kanban** | Minh bạch những hạng mục còn thiếu thông tin, công việc bị chặn và chính sách luồng; giới hạn WIP để ưu tiên hoàn tất thay vì mở nhiều story mơ hồ. |
| **XP** | Trao đổi thường xuyên với người hiểu nhu cầu; kiểm thử, tích hợp liên tục và refactoring giúp thay đổi giải pháp theo phản hồi mà vẫn duy trì chất lượng. |

Các phương pháp này khác nhau về nhịp phối hợp, nhưng cùng hưởng lợi từ **cách nói rõ giá trị, bối cảnh và hành vi cần kiểm chứng**.

## 10. Ví dụ xuyên suốt: yêu cầu “thêm thông báo” được làm rõ thế nào?

### 10.1. Đề xuất ban đầu

Nhân viên hỗ trợ báo: “Học viên cứ hỏi tại sao chưa thấy khóa đã đăng ký, nên cần gửi thêm email xác nhận.” Đó là một tín hiệu có ích, nhưng chưa đủ kết luận email là giải pháp tốt nhất.

Nhóm cùng hỗ trợ và Product Owner xem một số tình huống thực tế. Họ phát hiện có ít nhất ba trường hợp khác nhau:

1. Học viên đã ghi danh thành công nhưng không biết mở khóa tại đâu.
2. Học viên chưa hoàn tất bước thanh toán nên chưa có quyền học.
3. Học viên gặp lỗi tạm thời, giao diện hiển thị thông báo dễ gây hiểu nhầm.

Đây là **các tình huống giả định để minh họa cách phân tích**. Ở sản phẩm thật, nhóm cần kiểm tra tần suất và bằng chứng từng trường hợp, tránh kết luận từ một số cuộc gọi riêng lẻ.

### 10.2. Viết lại ba nhu cầu thay vì một giải pháp

| Bối cảnh | Nhu cầu bằng ngôn ngữ người dùng | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Đã ghi danh thành công | “Tôi muốn biết ngay mình đã có quyền học và mở khóa ở đâu.” | Xem được trạng thái hiệu lực và vào được khóa |
| Thanh toán chưa xác nhận | “Tôi muốn biết giao dịch đang ở trạng thái nào và cần làm gì tiếp.” | Không nhầm trạng thái chờ với hoàn tất; không bị thu tiền/cấp quyền sai |
| Hệ thống lỗi | “Tôi muốn nhận thông báo đúng tình trạng thay vì thấy đăng ký thành công giả.” | Thông điệp phù hợp dữ liệu thật và có hướng xử lý |

Thay vì mặc định ba nhu cầu đều cần email, nhóm có thể kiểm chứng giao diện trạng thái trước; email là một **phương án bổ sung** nếu người dùng thật sự cần thông tin ngoài ứng dụng.

### 10.3. Chọn lát và tiêu chí chấp nhận

Một lát có thể là: **sau khi học viên ghi danh thành công, trang khóa thể hiện rõ trạng thái đã ghi danh và đường dẫn vào học**. Nếu thanh toán có trạng thái chờ, hệ thống không báo “đã đăng ký” khi quyền học chưa hiệu lực.

Điều kiện chấp nhận gồm:

- Trạng thái trình bày nhất quán với dữ liệu nguồn tại thời điểm hiển thị, có xử lý khi chưa cập nhật.
- Học viên không thấy thông tin đăng ký của người khác.
- Khi quyền học chưa được cấp, hệ thống không hiển thị thông điệp khẳng định đã có quyền.
- Khi có lỗi tạm thời, người dùng biết cần thử lại hoặc liên hệ hỗ trợ theo kênh phù hợp.

### 10.4. Kiểm chứng giá trị sau bàn giao

Nhóm có thể đo tỷ lệ học viên đã ghi danh **mở được bài đầu**, thời gian từ ghi danh đến lần mở đầu tiên và tỷ lệ liên hệ hỗ trợ chỉ để hỏi trạng thái. Đồng thời theo dõi lỗi cấp quyền, lỗi trạng thái và phản hồi định tính. Việc số cuộc gọi giảm sau phát hành là tín hiệu tích cực nhưng chưa tự chứng minh quan hệ nhân quả: có thể còn thay đổi lưu lượng truy cập, chiến dịch hỗ trợ hoặc mùa học.

Nếu học viên vẫn không tìm thấy khóa dù trạng thái đã rõ, nhóm điều chỉnh backlog để cải thiện điều hướng. Nếu nhiều trường hợp phát sinh do xác nhận thanh toán chậm, nhóm ưu tiên làm rõ luồng giao dịch. **Nhu cầu được diễn đạt tốt giúp thay đổi giải pháp mà vẫn giữ mục tiêu người dùng.**

## 11. Các phản mẫu thường gặp khi mô tả yêu cầu

| Phản mẫu | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| “Người dùng muốn hệ thống hiện đại, dễ dùng.” | Không xác định được hành vi cần cải thiện | Nêu tình huống, bước đang vướng và kết quả có thể quan sát |
| User story chỉ thay “Tạo API X” thành “Là người dùng, tôi muốn API X” | Vẫn là task kỹ thuật ngụy trang | Hỏi ai hưởng lợi từ API, công việc nào trở nên khả thi |
| Chỉ phỏng vấn người yêu cầu tính năng | Có thể bỏ qua nhu cầu của người sử dụng thực tế | Quan sát các nhóm chịu ảnh hưởng và kiểm tra bằng chứng |
| Dùng từ mơ hồ như “đã đăng ký”, “hoàn tất”, “được duyệt” | Các bên xây và kiểm thử những trạng thái khác nhau | Thống nhất glossary và ví dụ phân biệt trạng thái |
| Viết story quá lớn như “Quản lý học viên” | Không biết ranh giới và khó nhận phản hồi sớm | Tách theo hành trình hoặc biến thể có giá trị hoàn chỉnh |
| Chỉ mô tả luồng thành công | Bỏ sót quyền truy cập, retry và ngoại lệ nghiệp vụ | Bổ sung các ví dụ quan trọng và tiêu chí chấp nhận |
| Đưa toàn bộ thiết kế UI/database vào tiêu chí nghiệp vụ | Hạn chế khả năng tìm giải pháp tốt hơn | Tách kết quả bắt buộc khỏi phương án triển khai |
| Không ghi câu hỏi chưa rõ | Nhóm tự suy chính sách; dễ tạo dữ liệu sai | Ghi câu hỏi, người có thẩm quyền và mốc xác nhận |
| Coi story đã viết là hợp đồng bất biến | Không thích ứng dù có phản hồi mới | Xem story là đơn vị đối thoại và sắp xếp lại backlog khi cần |
| Dùng số lượng story đã đóng làm bằng chứng giá trị | Có nhiều output nhưng người dùng vẫn gặp vấn đề | Đo outcome và xem xét nguyên nhân sau mỗi lần bàn giao |

## 12. Bài thực hành: chuyển yêu cầu từ ngôn ngữ giải pháp sang nhu cầu

**Bối cảnh:** Một nền tảng học lập trình có nhiều người học đã mua khóa nhưng liên hệ hỗ trợ để hỏi “Tôi đã học đến đâu?”. Người quản lý đề xuất: “Xây dashboard tiến độ với biểu đồ tròn, thêm ba endpoint và gửi thông báo hàng ngày”.

Hãy thực hiện các bước:

1. Viết lại **vấn đề của người học** bằng một hoặc hai câu, chỉ rõ bối cảnh.
2. Đặt **năm câu hỏi khám phá** để phân biệt người học muốn xem vị trí đang học, số phần đã hoàn thành hay kết quả đánh giá.
3. Viết một **user story** hoặc **job story** theo kết quả người dùng mong muốn.
4. Đề xuất **ba tiêu chí chấp nhận**: luồng chính, một ngoại lệ và một điều kiện quyền truy cập.
5. Chia thành **lát đầu** đủ nhỏ để học viên dùng được; nêu những ý tưởng sẽ để sau.
6. Chọn **tín hiệu kiểm chứng** rằng giải pháp hữu ích, không chỉ xác nhận dashboard đã xuất hiện.

### Gợi ý lời giải

**Vấn đề giả định:** Khi quay lại một khóa đang học, học viên khó xác định bài tiếp theo cần mở. Họ phải dò lại danh sách bài hoặc hỏi hỗ trợ, làm gián đoạn quá trình học.

**Câu hỏi khám phá:** Lần gần nhất học viên gặp vấn đề là khi nào? Họ có thể tự mở lại khóa không? Họ tìm bài theo thứ tự, theo tên hay theo trạng thái? Có trường hợp học ở nhiều thiết bị không? Thông tin “đang học”, “đã xem” và “hoàn thành” được hiểu thế nào?

**Story:**

> “Là học viên đang học dở một khóa, khi quay lại sau vài ngày, tôi muốn biết bài tiếp theo phù hợp để có thể tiếp tục ngay từ vị trí trước đó.”

**Tiêu chí chấp nhận ví dụ:**

- Với học viên có quyền học và tiến độ hợp lệ, trang khóa hiển thị hành động tiếp tục đúng bài theo quy tắc đã thống nhất.
- Với học viên chưa bắt đầu, hệ thống chỉ dẫn rõ cách mở bài đầu tiên; không tạo tiến độ giả.
- Một người không có quyền không thể xem thông tin tiến độ của học viên khác, kể cả khi dùng liên kết trực tiếp.

**Lát đầu:** hiển thị “Tiếp tục học” từ trang khóa và điều hướng đúng bài. Biểu đồ tròn, bảng xếp hạng và thông báo hàng ngày chỉ được ưu tiên nếu có nhu cầu đã kiểm chứng. Cần kiểm tra quy tắc chọn bài tiếp theo khi học viên được phép học không theo thứ tự.

**Tín hiệu kết quả:** tỷ lệ học viên quay lại mở được bài tiếp theo, thời gian tìm bài và số liên hệ hỗ trợ về vị trí học; đồng thời quan sát lỗi tiến độ. Nếu người dùng vẫn lạc trong nội dung, cần tiếp tục phỏng vấn và xem lại mô hình điều hướng thay vì mặc định thêm biểu đồ.

Không có một lời giải duy nhất. Chất lượng bài làm nằm ở việc **làm rõ nhu cầu và bối cảnh, nêu đúng bất định, xác định hành vi có thể kiểm chứng và cho phép điều chỉnh giải pháp**.

## 13. Checklist trước khi đưa yêu cầu vào thực hiện

- [ ] Người hưởng lợi và người chịu ảnh hưởng đã được xác định rõ?
- [ ] Mô tả có **bối cảnh kích hoạt, khó khăn hiện tại và kết quả mong muốn**?
- [ ] Đã phân biệt **sự kiện có bằng chứng, giả thuyết và đề xuất giải pháp**?
- [ ] Người dùng/người am hiểu nghiệp vụ có cơ hội giải thích tình huống thật?
- [ ] Các từ dễ hiểu khác nhau đã có **định nghĩa và ví dụ nghiệp vụ**?
- [ ] Đã mô tả luồng chính, biến thể và ngoại lệ có rủi ro quan trọng?
- [ ] **User story/job story** diễn đạt giá trị mà không khóa cứng một công nghệ tùy ý?
- [ ] **Tiêu chí chấp nhận** đủ cụ thể để người sản phẩm, phát triển và kiểm thử cùng xác nhận?
- [ ] Yêu cầu chất lượng, phân quyền và dữ liệu quan trọng đã được nêu rõ?
- [ ] Những câu hỏi chưa có đáp án đã được giao người xác nhận và theo dõi?
- [ ] Phạm vi đã được chia thành **lát hoàn chỉnh có thể sử dụng hoặc kiểm chứng**?
- [ ] Nhóm biết **đo outcome** sau bàn giao và cập nhật backlog theo phản hồi?

**Ghi nhớ:** Một yêu cầu tốt không được đánh giá bằng độ dài bản đặc tả hay số lượng ticket. Nó giúp nhóm **hiểu đúng con người, công việc và quy tắc trong bối cảnh thật**, chuyển hiểu biết đó thành hành vi có thể kiểm chứng và điều chỉnh giải pháp khi học được điều mới. Đó là nền tảng để user story, backlog, Scrum, Kanban và các thực hành kỹ thuật XP hỗ trợ **phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục**.
