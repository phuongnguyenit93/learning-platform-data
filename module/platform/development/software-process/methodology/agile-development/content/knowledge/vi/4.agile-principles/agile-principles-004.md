# Cộng tác thường xuyên giữa người làm nghiệp vụ và người phát triển

Trong Agile, phần mềm tạo ra giá trị khi những người hiểu **vấn đề kinh doanh và nhu cầu người dùng** cùng làm việc với những người hiểu **cách thiết kế, xây dựng, kiểm thử và vận hành giải pháp**. Hai nhóm này cần trao đổi thường xuyên từ lúc xác định vấn đề cho đến khi quan sát kết quả sử dụng. Nếu chỉ bàn giao tài liệu yêu cầu ở đầu dự án rồi chờ sản phẩm hoàn tất, những hiểu lầm nhỏ có thể tích tụ thành phần mềm làm đúng đặc tả cũ nhưng chưa giải quyết đúng nhu cầu hiện tại.

Nguyên tắc thứ tư của Tuyên ngôn Agile nhấn mạnh: **người làm nghiệp vụ và người phát triển phải làm việc cùng nhau hằng ngày trong suốt dự án**. Tinh thần cốt lõi là duy trì khả năng trao đổi, làm rõ và quyết định kịp thời. Điều này không bắt buộc mọi người phải tham dự một cuộc họp chung mỗi ngày; nó yêu cầu sự cộng tác liên tục, có trách nhiệm và đủ gần với công việc đang diễn ra để tránh những khoảng chờ kéo dài.

Bài học này thuộc phần **Nguyên tắc Agile** của mô-đun **AGILE_DEVELOPMENT**, liên hệ với user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc. Mục tiêu là hiểu vì sao cộng tác thường xuyên cần thiết, cách thực hiện mà không biến giao tiếp thành gánh nặng và cách biết việc phối hợp có tạo ra kết quả hay không.

## 1. “Người làm nghiệp vụ” và “người phát triển” là ai?

Đây là hai góc nhìn cần được kết nối, không nhất thiết là hai phòng ban tách biệt hoặc hai nhóm có mục tiêu đối lập.

| Góc nhìn | Người thường tham gia | Kiến thức và câu hỏi chủ yếu |
| --- | --- | --- |
| **Nghiệp vụ và giá trị** | Người đại diện sản phẩm, Product Owner, chuyên gia nghiệp vụ, vận hành, bán hàng, chăm sóc khách hàng, người dùng hoặc đại diện người dùng | Ai đang gặp vấn đề? Quy tắc nghiệp vụ là gì? Kết quả nào có giá trị? Ưu tiên nào quan trọng hơn? |
| **Phát triển và tính khả thi** | Lập trình viên, người kiểm thử, thiết kế trải nghiệm, kiến trúc sư, chuyên gia bảo mật, vận hành nền tảng và các thành viên tạo sản phẩm | Có thể xây dựng và kiểm chứng cách nào? Có phụ thuộc hay rủi ro gì? Điều kiện hoàn thành và vận hành an toàn là gì? |

Một người có thể mang nhiều góc nhìn; một số nhóm có thành viên rất am hiểu cả sản phẩm lẫn kỹ thuật. Tuy vậy, không nên mặc định một cá nhân biết mọi chi tiết. **Cộng tác** là cùng đặt câu hỏi, chia sẻ bằng chứng và tìm quyết định có trách nhiệm; không phải một bên “ra lệnh” và bên kia chỉ “thực thi”.

Trong Scrum, **Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog**; Developers chịu trách nhiệm tạo Increment có chất lượng mỗi Sprint. Người làm nghiệp vụ bên ngoài Scrum Team vẫn có thể cung cấp bối cảnh, phản hồi và tri thức chuyên môn. Việc trao đổi trực tiếp với chuyên gia nghiệp vụ cần phù hợp với cách Product Owner giữ Product Backlog minh bạch và có thứ tự.

## 2. Vì sao bàn giao yêu cầu một chiều thường không đủ?

Một tài liệu chi tiết vẫn là tập hợp hiểu biết tại thời điểm viết. Trong quá trình xây dựng, đội phát triển sẽ gặp các trường hợp biên, ràng buộc hệ thống và hành vi thực tế chưa được diễn đạt hết. Đồng thời, thị trường, chính sách và kỳ vọng người dùng có thể thay đổi.

Ví dụ, yêu cầu “khách hàng được áp mã giảm giá” nghe có vẻ đơn giản nhưng còn hàng loạt câu hỏi:

- Giảm giá tính trên tổng tiền hàng trước hay sau phí vận chuyển?
- Một mã có được dùng cùng ưu đãi thành viên hay không?
- Mã hết hạn theo múi giờ nào? Điều gì xảy ra khi khách bắt đầu thanh toán trước giờ hết hạn nhưng hoàn tất sau đó?
- Nếu hai yêu cầu thanh toán dùng mã giới hạn lượt gần như đồng thời, hệ thống xử lý thế nào?
- Khi dịch vụ kiểm tra mã không phản hồi, giao diện phải nói gì với người mua?

Nếu nhóm kỹ thuật tự đoán, phần mềm có thể chạy đúng nhưng trái chính sách bán hàng. Nếu người làm nghiệp vụ mô tả cách cài đặt quá sớm, nhóm có thể bỏ lỡ một giải pháp đơn giản và đáng tin cậy hơn.

| Cách phối hợp theo bàn giao | Cách cộng tác theo Agile |
| --- | --- |
| Viết toàn bộ yêu cầu, ký duyệt, sau đó chuyển cho kỹ thuật | Chia sẻ mục tiêu, làm rõ dần các hạng mục sắp thực hiện |
| Câu hỏi phát sinh đi qua nhiều tầng phê duyệt | Có người hiểu nghiệp vụ đủ gần để giải thích hoặc đưa ra quyết định |
| Phát hiện hiểu sai khi nghiệm thu cuối kỳ dài | Xem các lát cắt sản phẩm nhỏ, nhận phản hồi sớm |
| Thay đổi bị xem là thất bại của kế hoạch | Đánh giá thay đổi bằng bằng chứng, giá trị và chi phí |
| Thành công được đo bằng số yêu cầu đã hoàn thành | Thành công xét cả chất lượng, khả năng sử dụng và kết quả người dùng |

Agile không phủ nhận tài liệu, hợp đồng hay trách nhiệm phê duyệt. Tài liệu và quy tắc rõ ràng vẫn quan trọng, nhất là trong lĩnh vực có yêu cầu kiểm soát cao. **Điều cần tránh là để tài liệu trở thành kênh trao đổi duy nhất**, khiến câu hỏi chưa rõ bị giữ nguyên cho đến lúc đã tốn nhiều công xây dựng.

## 3. Cộng tác diễn ra qua toàn bộ chu trình làm sản phẩm

Một vòng cộng tác có ích thường đi qua năm hoạt động:

~~~mermaid
flowchart LR
    A["Cùng hiểu vấn đề và người dùng"] --> B["Làm rõ giả định và ưu tiên"]
    B --> C["Thiết kế lát cắt có thể kiểm chứng"]
    C --> D["Xây dựng, kiểm thử và xem kết quả"]
    D --> E["Học từ phản hồi và điều chỉnh backlog"]
    E --> A
~~~

### 3.1. Cùng hiểu vấn đề trước khi chốt giải pháp

Người làm nghiệp vụ giải thích tình huống, tác động, chính sách và mục tiêu. Người phát triển đặt câu hỏi về khả năng quan sát, dữ liệu hiện có, trường hợp biên và chi phí kỹ thuật. Hai bên cùng xác định:

1. **Ai** gặp vấn đề và trong hoàn cảnh nào?
2. **Vì sao** vấn đề đáng giải quyết ngay?
3. **Kết quả nào** cho thấy vấn đề đã được cải thiện?
4. **Giả định nào** đang thiếu bằng chứng?
5. **Giới hạn nào** không được vi phạm: bảo mật, pháp lý, trải nghiệm hoặc độ ổn định?

Thay vì nhận yêu cầu “cần thêm nút nhắc thanh toán”, nhóm có thể phát hiện nhu cầu thực sự là “người mua không biết giao dịch đang xử lý hay đã thất bại”. Một trạng thái giao dịch rõ ràng và thông báo phù hợp có thể giải quyết vấn đề tốt hơn.

### 3.2. Cùng làm rõ công việc sắp triển khai

Trước khi đưa hạng mục vào thực hiện, nhóm thảo luận giá trị, phạm vi và điều kiện kiểm chứng. **Product Backlog refinement** là hoạt động liên tục để chia nhỏ, làm rõ và ước lượng khi cần; nó không nhất thiết phải là một buổi họp cố định. Một vài câu hỏi đúng lúc thường hiệu quả hơn nhiều tài liệu vẫn còn khoảng trống quan trọng.

Tại đây, người phát triển được quyền nêu rủi ro và đề xuất phương án. Người làm nghiệp vụ được quyền sửa giả định, cắt bớt phạm vi hoặc đổi ưu tiên khi đã hiểu đánh đổi.

### 3.3. Giải đáp trong khi phát triển

Khi xuất hiện trường hợp chưa được mô tả, người liên quan cần dễ tiếp cận và có thời gian phản hồi phù hợp mức độ khẩn cấp. Những vấn đề quan trọng có thể trao đổi ngắn trực tiếp; câu hỏi đơn giản có thể xử lý trên công cụ quản lý công việc kèm kết luận rõ ràng.

Cộng tác không có nghĩa là lập trình viên bị ngắt quãng liên tục. Nhóm nên thống nhất **kênh liên hệ, đầu mối quyết định, cách ghi câu hỏi và thời gian phản hồi mục tiêu** để vừa duy trì dòng công việc, vừa bảo vệ thời gian tập trung.

### 3.4. Cùng kiểm chứng phần đã hoàn thành

Khi có một Increment hoặc lát cắt chức năng hoạt động, người làm nghiệp vụ không chỉ trả lời “đúng yêu cầu chưa?” mà còn xem “điều này có giúp người dùng hoàn thành việc của họ không?”. Người phát triển trình bày điều có thể làm được, các giới hạn còn lại và rủi ro đã kiểm chứng.

Một buổi xem sản phẩm có ích thường bắt đầu bằng **tình huống người dùng**, để người tham dự thử luồng thao tác và đối chiếu với mục tiêu. Phần chưa rõ được đưa trở lại Product Backlog hoặc kế hoạch kiểm chứng tiếp theo.

### 3.5. Cùng quan sát kết quả sau bàn giao

Phần mềm đã triển khai vẫn có thể chưa mang lại giá trị như dự đoán. Người làm nghiệp vụ và người phát triển cùng đọc phản hồi hỗ trợ, quan sát chỉ số sử dụng, lỗi vận hành và mức đạt mục tiêu. Kết quả có thể dẫn tới việc tiếp tục, điều chỉnh hoặc dừng một hướng triển khai.

**Cộng tác xuyên suốt** nghĩa là người hiểu giá trị không biến mất sau lúc chốt yêu cầu, và người hiểu kỹ thuật không biến mất sau lúc viết xong mã.

## 4. Tạo ngôn ngữ chung bằng user story và tiêu chí chấp nhận

Hai bên có thể dùng một **user story** để bắt đầu cuộc trò chuyện, nhưng user story không phải bản đặc tả hoàn chỉnh. Một cấu trúc thường dùng:

> Là một **[vai trò người dùng]**, tôi muốn **[khả năng]**, để **[lợi ích hoặc mục tiêu]**.

Giá trị của cấu trúc này là giữ cuộc trao đổi gắn với người dùng và mục đích. Tiếp theo, nhóm cùng làm rõ quy tắc nghiệp vụ, trường hợp ngoại lệ và **tiêu chí chấp nhận (acceptance criteria)**. Tiêu chí chấp nhận giúp xác định hành vi mong đợi của một hạng mục; **Definition of Done** là tiêu chuẩn chất lượng chung để Increment được coi là hoàn thành. Hai khái niệm bổ trợ nhau nhưng không thay thế nhau.

### Ví dụ xuyên suốt: áp mã khuyến mãi khi thanh toán

Giả sử một cửa hàng trực tuyến muốn khách áp mã khuyến mãi ngay trên trang thanh toán. Đây là tình huống **giả định để học**, với các quy tắc được nhóm thống nhất cho ví dụ, không phải chính sách của một doanh nghiệp có thật.

**User story:**

> Là người mua hàng, tôi muốn nhập mã khuyến mãi trước khi xác nhận thanh toán, để biết số tiền được giảm và tổng tiền phải trả.

Trong buổi trao đổi ban đầu, ba góc nhìn xuất hiện:

| Người tham gia | Điều quan tâm hoặc câu hỏi |
| --- | --- |
| Đại diện nghiệp vụ | Mã giảm 10% tiền hàng, tối đa 100.000 đồng; chỉ áp dụng khi tiền hàng từ 500.000 đồng; không cộng dồn mã khác |
| Người phát triển | Ngưỡng được tính trước phí vận chuyển? Thời điểm kiểm tra mã? Có cần kiểm tra lại tại bước đặt đơn để tránh dùng dữ liệu cũ? |
| Người kiểm thử / thiết kế trải nghiệm | Trạng thái mã không hợp lệ hiển thị ở đâu? Người mua có hiểu cách tính tổng tiền và giới hạn giảm giá không? |

Nhóm thống nhất cho lát cắt đầu tiên:

1. Điều kiện 500.000 đồng được tính trên **tiền hàng trước phí vận chuyển và trước giảm giá**.
2. Giảm 10% tiền hàng, nhưng tối đa **100.000 đồng**.
3. Một đơn hàng chỉ dùng **một mã khuyến mãi**.
4. Hiển thị rõ tiền hàng, phí vận chuyển, tiền giảm và tổng dự kiến.
5. Mã không hợp lệ hoặc hết hạn phải có thông báo dễ hiểu; hệ thống kiểm tra lại tính hợp lệ tại thời điểm xác nhận đơn.
6. Các quy tắc khác như hoàn hàng, ưu đãi thành viên, thuế hoặc giới hạn lượt sử dụng sẽ phải được làm rõ trước khi triển khai những khả năng liên quan. Không tự suy luận chính sách còn thiếu.

Các quy tắc đã chốt có thể biến thành ví dụ kiểm thử chấp nhận:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tiền hàng 400.000 đồng, nhập mã còn hiệu lực | Không áp dụng vì chưa đạt ngưỡng 500.000 đồng |
| Tiền hàng 700.000 đồng, phí vận chuyển 30.000 đồng, mã hợp lệ | Giảm 70.000 đồng; tổng dự kiến là **660.000 đồng** |
| Tiền hàng 1.500.000 đồng, mã hợp lệ | Giảm tối đa **100.000 đồng**, không giảm 150.000 đồng |
| Mã hết hạn tại thời điểm xác nhận đơn | Từ chối áp dụng và yêu cầu người mua xác nhận lại tổng tiền |
| Người mua đã áp một mã và thử mã thứ hai | Chỉ có một mã được áp dụng; hành vi thay thế phải được xác định rõ với người dùng |

Ví dụ minh họa theo cách viết **Given–When–Then**, phù hợp để cả nghiệp vụ lẫn kỹ thuật đọc và thảo luận:

~~~gherkin
Tính năng: Áp mã giảm giá trong giỏ hàng

  Kịch bản: Áp mã hợp lệ khi tiền hàng đủ ngưỡng
    Cho giỏ hàng có tiền hàng là 700000 VND
    Và phí vận chuyển là 30000 VND
    Và mã đang còn hiệu lực, giảm 10% tối đa 100000 VND
    Khi người mua áp mã khuyến mãi
    Thì số tiền được giảm là 70000 VND
    Và tổng tiền dự kiến là 660000 VND

  Kịch bản: Tiền hàng chưa đạt ngưỡng
    Cho giỏ hàng có tiền hàng là 400000 VND
    Và mã yêu cầu tiền hàng tối thiểu 500000 VND
    Khi người mua áp mã khuyến mãi
    Thì hệ thống không áp dụng giảm giá
    Và hiển thị lý do chưa đạt ngưỡng
~~~

Ví dụ kiểm thử không tự quyết định thay nghiệp vụ. Chúng là **công cụ để phát hiện cách hiểu khác nhau** trước khi lập trình sâu. Khi chính sách thay đổi, nhóm cần cập nhật cả quyết định nghiệp vụ, tiêu chí chấp nhận và các kiểm thử liên quan.

### Khi phát hiện vấn đề mới, hai bên cùng điều chỉnh

Trong lúc phát triển, kỹ thuật phát hiện dịch vụ kiểm tra mã có thể phản hồi chậm. Nghiệp vụ muốn tránh trường hợp khách thấy một khoản giảm rồi đến lúc đặt đơn lại bị từ chối. Thay vì âm thầm chọn cách xử lý, nhóm thống nhất:

- Giao diện có trạng thái “đang kiểm tra mã” và chỉ hiển thị giảm giá đã được xác nhận.
- Nếu kiểm tra thất bại tạm thời, giao diện thông báo không thể xác nhận mã và cho phép thử lại.
- Trước lúc đặt đơn, hệ thống kiểm tra lại; nếu tổng tiền thay đổi, khách cần thấy giá trị mới và xác nhận.
- Nhóm đo lỗi xác nhận mã và phản hồi về mức dễ hiểu của thông báo sau khi phát hành có kiểm soát.

Kết quả không chỉ là tính năng hoạt động. **Nghiệp vụ hiểu rủi ro kỹ thuật, kỹ thuật hiểu tác động đến niềm tin của người mua**, và hai bên quyết định cách xử lý có thể kiểm chứng.

## 5. Phối hợp thường xuyên nhưng không tạo thêm họp vô ích

“Làm việc cùng nhau hằng ngày” là nguyên tắc về **khả năng tiếp cận tri thức và phản hồi kịp thời**, không phải quy định buộc tất cả stakeholder tham dự Daily Scrum hoặc có một cuộc họp dài mỗi ngày.

| Tình huống | Hình thức cộng tác gợi ý | Kết quả cần có |
| --- | --- | --- |
| Vướng một quy tắc nghiệp vụ ảnh hưởng việc đang làm | Trao đổi ngắn giữa người liên quan, ghi quyết định vào story | Câu hỏi được giải đáp, nhóm tiếp tục được |
| Hạng mục sắp bắt đầu còn nhiều cách hiểu | Trao đổi refinement với ví dụ cụ thể, cùng chia lát cắt | Phạm vi, giá trị và điều kiện chấp nhận rõ hơn |
| Có một phần sản phẩm dùng thử được | Người nghiệp vụ và người dùng xem, thao tác, phản hồi | Bằng chứng và đề xuất điều chỉnh backlog |
| Cần xử lý phụ thuộc nhiều bộ phận | Bảng công việc chung, người phụ trách rõ, thống nhất thời hạn phản hồi | Thấy nút thắt và người có thể gỡ |
| Một quyết định có ảnh hưởng rộng hoặc dài hạn | Buổi thảo luận tập trung, ghi các phương án và đánh đổi | Quyết định, người chịu trách nhiệm, lý do và thời điểm xem lại |
| Mọi người làm việc khác múi giờ | Câu hỏi bất đồng bộ kèm ngữ cảnh, ví dụ, hạn cần trả lời | Quyết định có thể tra cứu, giảm chờ đợi qua nhiều ca làm |

### Quy tắc thực hành để giảm gián đoạn

**Gửi câu hỏi đủ ngữ cảnh:** nêu story đang xử lý, tình huống cụ thể, phương án đã nghĩ tới, tác động nếu chờ và thời điểm cần quyết định. Câu hỏi “trường hợp khách dùng hai mã thì sao?” dễ trả lời hơn khi kèm ví dụ, màn hình và ràng buộc hiện tại.

**Tạo một nguồn sự thật dễ tìm:** ghi kết luận tại user story, tiêu chí chấp nhận hoặc tài liệu quyết định ngắn; không để quyết định quan trọng chỉ nằm trong tin nhắn riêng hoặc trí nhớ người tham dự.

**Phân biệt giải thích và quyết định:** người có kinh nghiệm nghiệp vụ có thể giải thích quy tắc, nhưng thay đổi chính sách hoặc ưu tiên cần đúng người có quyền chấp thuận. Tương tự, thay đổi ảnh hưởng bảo mật, kiến trúc hoặc vận hành cần người có chuyên môn tham gia.

**Đặt thời gian phản hồi phù hợp:** câu hỏi đang chặn một Increment cần được giải quyết sớm hơn ý tưởng cải tiến chưa đến kỳ. Mọi người có thể thống nhất khung giờ trao đổi, đầu mối thay thế và cách báo khi một câu hỏi bị chặn.

**Ưu tiên ví dụ và phần mềm hoạt động:** khi có hai cách hiểu trái ngược, hãy mô tả tình huống, cho xem luồng thực tế hoặc thử bản mẫu. Những tranh luận trừu tượng thường được giải quyết nhanh hơn khi có ví dụ cụ thể.

## 6. Áp dụng nguyên tắc trong Scrum, Kanban và XP

Agile là tập hợp giá trị và nguyên tắc; Scrum, Kanban và XP cung cấp những cơ chế khác nhau để thực hành cộng tác.

### Scrum: cộng tác để kiểm tra và thích ứng sản phẩm

- **Product Owner** làm rõ mục tiêu sản phẩm, sắp xếp Product Backlog và tạo điều kiện để đội hiểu giá trị của từng hướng triển khai. Product Owner là **một người chịu trách nhiệm**, dù có thể nhận đóng góp từ nhiều stakeholder.
- **Sprint Planning** giúp Scrum Team thống nhất mục tiêu Sprint và chọn công việc khả thi dựa trên ưu tiên, năng lực và hiểu biết hiện tại.
- **Trong Sprint**, Developers và Product Owner có thể trao đổi khi xuất hiện quy tắc mới, vấn đề kỹ thuật hay điều cần làm rõ; không cần chờ đến cuối Sprint.
- **Sprint Review** là dịp Scrum Team và stakeholder cùng xem kết quả, thảo luận diễn biến thị trường hoặc nhu cầu và điều chỉnh hướng đi. Đây là hoạt động làm việc với sản phẩm, không chỉ là buổi trình diễn tiến độ.
- **Sprint Retrospective** tập trung cải thiện cách nhóm làm việc, gồm cả cách gỡ phụ thuộc và nhận câu trả lời từ người liên quan.

**Lưu ý:** Daily Scrum theo Scrum Guide là sự kiện 15 phút dành cho **Developers của Scrum Team** để kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch. Không nên sử dụng nguyên tắc cộng tác hằng ngày làm lý do bắt tất cả người làm nghiệp vụ dự Daily Scrum. Hãy tạo kênh phối hợp thích hợp bên cạnh các sự kiện Scrum.

### Kanban: nhìn rõ dòng công việc và chờ đợi

Một nhóm vận hành nhiều yêu cầu đến liên tục có thể sử dụng bảng Kanban để nhìn thấy:

~~~text
Ý tưởng / Yêu cầu
      ↓
Cần làm rõ nghiệp vụ
      ↓
Sẵn sàng thực hiện
      ↓
Đang phát triển → Đang kiểm thử → Sẵn sàng bàn giao
      ↓
Đã bàn giao và quan sát phản hồi
~~~

Khi nhiều thẻ nằm ở “Cần làm rõ nghiệp vụ”, đó là tín hiệu nhóm cần điều chỉnh cách tiếp cận người ra quyết định hoặc cách mô tả công việc. **Giới hạn WIP** ở các trạng thái thực hiện giúp giảm đa nhiệm, tránh mở thêm nhiều hạng mục trong khi những hạng mục gần xong đang bị chặn. Tùy hệ thống, nhóm có thể ghi rõ trạng thái “Blocked” hoặc lý do bị chặn mà không làm mất khả năng nhìn tổng thể dòng công việc.

Kanban khuyến khích **chính sách làm việc rõ ràng** và các vòng phản hồi phù hợp. Nhóm có thể đo thời gian chờ trả lời nghiệp vụ, cycle time hoặc thời gian từ lúc yêu cầu được đưa vào đến lúc bàn giao để thấy vấn đề phối hợp; không nên xem số cuộc họp là thước đo chính.

### Extreme Programming (XP): đưa phản hồi nghiệp vụ đến gần việc xây dựng

XP đề cao trao đổi gần giữa người hiểu nhu cầu và người lập trình. Cách thực hành thường gắn với ý tưởng **khách hàng sẵn sàng trả lời** (on-site customer), ví dụ chấp nhận được và kiểm thử sớm. Những kỹ thuật như lập trình cặp, phát triển hướng kiểm thử (TDD), tích hợp liên tục và tái cấu trúc giúp nhóm kiểm chứng kỹ thuật nhanh, từ đó có thêm khả năng phản hồi khi hiểu biết nghiệp vụ thay đổi.

“Khách hàng gần nhóm” không nhất thiết phải là người ngoài đến ngồi tại văn phòng mỗi ngày. Điều quan trọng là **có đại diện hiểu vấn đề đủ sẵn sàng và đủ thẩm quyền** để nhóm không phải suy đoán yêu cầu. Kiểm thử chấp nhận dựa trên ví dụ có thể là ngôn ngữ chung, giúp người nghiệp vụ và kỹ thuật cùng kiểm tra một kỳ vọng.

Một nhóm có thể kết hợp Sprint Review của Scrum, bảng công việc Kanban và thực hành kiểm thử tự động của XP nếu chúng giúp giải quyết nhu cầu thực tế. Không nên đo độ “Agile” bằng số thực hành đã áp dụng.

## 7. Trách nhiệm rõ ràng giúp cộng tác nhanh hơn

Cộng tác hiệu quả không có nghĩa là mọi người đồng ý với mọi quyết định. Mỗi vấn đề cần có người đóng góp tri thức và **đầu mối đưa ra quyết định** khi xảy ra bất đồng.

| Loại quyết định | Nguồn đóng góp quan trọng | Trách nhiệm ra quyết định cần làm rõ |
| --- | --- | --- |
| Mục tiêu sản phẩm và thứ tự ưu tiên | Người dùng, stakeholder, dữ liệu kinh doanh, Developers | Product Owner với Product Backlog trong Scrum |
| Chính sách nghiệp vụ, quyền lợi khách hàng | Chuyên gia nghiệp vụ, pháp chế hoặc bộ phận có thẩm quyền nếu liên quan | Người hoặc cấp được tổ chức giao quyền về chính sách |
| Cách thực hiện kỹ thuật, ước lượng và chất lượng | Developers, kiểm thử, bảo mật, vận hành | Nhóm và người chịu trách nhiệm kỹ thuật theo cơ chế đã thống nhất |
| Phạm vi một lát cắt bàn giao | Product Owner, Developers và các bên liên quan | Thống nhất mục tiêu và đánh đổi; tránh đơn phương áp yêu cầu vượt khả năng |
| Chấp nhận rủi ro ảnh hưởng lớn | Người chịu trách nhiệm sản phẩm, chuyên gia kỹ thuật và các bên có quyền quyết định | Cấp có thẩm quyền theo phạm vi rủi ro |

Khi có xung đột, hãy tách **mục tiêu** khỏi **phương án**. Chẳng hạn, “khách cần hoàn tất thanh toán nhanh” là mục tiêu; “phải bỏ mọi bước xác nhận” là phương án có thể tạo rủi ro. Cả hai phía nên trao đổi bằng dữ liệu, ví dụ thực tế và giới hạn bắt buộc.

Một quyết định ngắn có thể ghi:

~~~text
Vấn đề: Mã hết hạn giữa lúc người mua nhập thông tin thanh toán.
Các lựa chọn: (A) Giữ giá cũ; (B) Kiểm tra lại khi xác nhận đơn.
Ràng buộc: Phải tuân thủ chính sách thời hạn mã.
Quyết định: Chọn B; hiển thị tổng mới và yêu cầu xác nhận lại.
Người chốt: Người phụ trách chính sách khuyến mãi.
Việc tiếp theo: Bổ sung tiêu chí chấp nhận và kiểm thử tình huống hết hạn.
~~~

Mẫu này không cần trở thành tài liệu nặng nề. Nó giúp nhóm hiểu **vì sao** đã chọn phương án đó, và biết phải trao đổi với ai khi hoàn cảnh thay đổi.

## 8. Đo chất lượng phối hợp bằng kết quả và dòng công việc

Một nhóm có nhiều cuộc họp chưa chắc cộng tác tốt. Hãy xem sự phối hợp có làm **giảm việc chờ làm rõ, giảm hiểu sai và tăng tốc độ kiểm chứng giá trị** hay không.

| Tín hiệu | Cách quan sát | Điều cần tránh khi diễn giải |
| --- | --- | --- |
| **Thời gian chờ trả lời nghiệp vụ** | Từ lúc có câu hỏi chặn việc đến lúc có quyết định sử dụng được | Thúc ép trả lời nhanh nhưng chưa đủ căn cứ |
| **Công việc bị chặn vì thiếu quyết định** | Số hạng mục và thời gian bị chặn, phân theo nguyên nhân | Gán lỗi cho một cá nhân khi vấn đề nằm ở cơ chế phối hợp |
| **Làm lại do hiểu sai yêu cầu** | Ghi nhận những thay đổi phải thực hiện lại vì khác cách hiểu | Đánh đồng mọi thay đổi học được với thất bại |
| **Cycle time / lead time** | Theo dõi thời gian hạng mục đi qua dòng công việc với mốc thống nhất | Cải thiện con số bằng cách bỏ qua kiểm thử hoặc tách việc thiếu giá trị |
| **Phản hồi sau mỗi phần bàn giao** | Bao lâu mới có nhận xét hoặc dữ liệu sử dụng đủ để quyết định? | Chỉ đếm số buổi demo mà không xem quyết định sau demo |
| **Kết quả người dùng** | Tỷ lệ hoàn thành tác vụ, lỗi nghiệp vụ, phản hồi hỗ trợ hoặc chỉ số gắn mục tiêu | Mặc định số tính năng làm xong chính là giá trị |

Ví dụ, nhóm có thể phát hiện một story chỉ mất hai ngày lập trình nhưng chờ năm ngày để xác nhận chính sách. Việc rút ngắn **khoảng chờ quyết định** có thể cải thiện thời gian bàn giao rõ hơn so với yêu cầu lập trình nhanh hơn. Đây là một giả thuyết cải tiến cần được theo dõi qua nhiều hạng mục, không phải kết luận chỉ từ một trường hợp.

Nên kiểm tra cả mặt định tính: người làm nghiệp vụ có hiểu được đánh đổi kỹ thuật không, Developers có hiểu người dùng cần đạt điều gì không, và các quyết định có dễ tra cứu khi thành viên mới tham gia không.

## 9. Những phản mẫu thường gặp

### “Nghiệp vụ đã ký tài liệu rồi, kỹ thuật cứ thế làm”

**Vấn đề:** Khi chi tiết mới xuất hiện, nhóm có xu hướng tự suy đoán hoặc tạo thêm vòng phê duyệt dài.  
**Cải thiện:** Ghi nhận câu hỏi gần với hạng mục đang làm, định rõ người trả lời, thống nhất ví dụ và cập nhật tiêu chí chấp nhận.

### “Agile nghĩa là họp với tất cả mọi người mỗi ngày”

**Vấn đề:** Giao tiếp dày đặc làm gián đoạn việc tập trung, trong khi các quyết định quan trọng vẫn chưa rõ.  
**Cải thiện:** Dùng trao đổi ngắn theo nhu cầu, công cụ bất đồng bộ và các buổi xem sản phẩm có mục tiêu; chỉ mời người có thông tin hoặc quyền quyết định liên quan.

### “Người làm nghiệp vụ phải đưa ra giải pháp kỹ thuật”

**Vấn đề:** Cách cài đặt được chốt quá sớm trước khi hiểu chi phí, giới hạn hoặc phương án khác.  
**Cải thiện:** Nghiệp vụ nêu vấn đề và kết quả cần đạt; kỹ thuật đề xuất khả năng thực hiện; hai bên cùng cân nhắc đánh đổi.

### “Lập trình viên cứ hỏi cho tới khi không còn bất định”

**Vấn đề:** Không thể biết mọi tình huống ngay từ đầu; phân tích vô hạn làm chậm học hỏi.  
**Cải thiện:** Làm rõ đủ cho lát cắt nhỏ và an toàn, đánh dấu giả định còn lại, sau đó kiểm chứng bằng sản phẩm hoạt động và dữ liệu.

### “Mọi góp ý của stakeholder đều thành hạng mục phải làm”

**Vấn đề:** Backlog mất trọng tâm, ưu tiên bị đổi liên tục, nhóm khó hoàn thành công việc.  
**Cải thiện:** Phân biệt phản hồi, nhu cầu và đề xuất giải pháp; đánh giá tác động, bằng chứng và chi phí trước khi quyết định thứ tự backlog.

### “Chờ Sprint Review mới báo vướng mắc”

**Vấn đề:** Câu hỏi đang chặn công việc bị tồn đọng đến cuối Sprint.  
**Cải thiện:** Có kênh hỏi đáp và cơ chế xử lý trở ngại trong Sprint. Sprint Review dùng để xem kết quả và điều chỉnh hướng sản phẩm ở mức rộng hơn.

## 10. Bài tập thực hành: cải thiện cộng tác trong một Sprint

Giả sử nhóm đang phát triển chức năng đặt lịch tư vấn trực tuyến. Người làm nghiệp vụ yêu cầu “chỉ cho khách chọn lịch trống”, nhưng chưa thống nhất lịch có được giữ chỗ khi khách đang điền thông tin hay không.

Hãy thực hành theo trình tự:

1. **Viết vấn đề bằng ngôn ngữ người dùng:** “Khách cần thấy khung giờ có thể đặt và được xác nhận chính xác, không gặp tình trạng hai người cùng được hẹn vào một chỗ.”
2. **Nêu câu hỏi có ảnh hưởng cao:** Một khung giờ có bao nhiêu chỗ? Đơn đang nhập thông tin có giữ chỗ không? Giữ trong bao lâu? Nếu hai yêu cầu cùng gửi thì xử lý thế nào?
3. **Xác định người trả lời:** Người sở hữu quy tắc đặt lịch quyết định chính sách; Developers đề xuất cơ chế chống đặt trùng; người kiểm thử chuẩn bị ví dụ cạnh tranh đồng thời.
4. **Chia lát cắt đầu tiên:** Cho khách chọn một khung giờ còn chỗ, gửi yêu cầu đặt và nhận kết quả xác nhận hoặc từ chối rõ ràng; các tính năng nhắc lịch hoặc đổi lịch có thể đến sau nếu không cần cho mục tiêu ban đầu.
5. **Cùng xem phần dùng được:** Đại diện nghiệp vụ thử trường hợp chỗ cuối cùng bị hai khách chọn gần đồng thời, đối chiếu kết quả với quy tắc đã quyết định.
6. **Ghi lại phản hồi và cập nhật backlog:** Nếu khách không hiểu vì sao bị từ chối, đưa ra cách cải thiện thông điệp; nếu số lần từ chối cao, xem lại cơ chế giữ chỗ với dữ liệu thực tế.

Trong một hoặc hai Sprint tiếp theo, nhóm có thể thử một cải tiến phối hợp: **mọi story đang bị chặn vì quy tắc nghiệp vụ phải có người trả lời và thời điểm cần quyết định rõ ràng**. Theo dõi thời gian chờ và số lần phải làm lại vì hiểu sai, rồi đánh giá xem cải tiến có giúp luồng công việc thông suốt hơn không.

### Câu hỏi tự kiểm tra

1. Vì sao một yêu cầu đã viết rất chi tiết vẫn cần trao đổi với người làm nghiệp vụ trong lúc phát triển?
2. Nguyên tắc làm việc hằng ngày có bắt buộc mọi stakeholder dự Daily Scrum không? Vì sao?
3. Trong ví dụ mã khuyến mãi, câu hỏi nào cần quyết định nghiệp vụ và câu hỏi nào cần phân tích kỹ thuật?
4. User story, tiêu chí chấp nhận và Definition of Done hỗ trợ cuộc trao đổi theo những cách khác nhau như thế nào?
5. Nếu một story thường xuyên chờ duyệt quy tắc, Kanban giúp nhìn ra vấn đề gì?
6. Dấu hiệu nào cho thấy các cuộc trao đổi đang cải thiện kết quả người dùng thay vì chỉ tăng số buổi họp?

**Ghi nhớ:** Cộng tác thường xuyên trong Agile là năng lực **đưa tri thức nghiệp vụ và tri thức kỹ thuật vào cùng một quyết định đúng lúc**. Khi người làm nghiệp vụ và người phát triển cùng hiểu vấn đề, làm rõ bằng ví dụ, bàn giao phần nhỏ, quan sát phản hồi và điều chỉnh backlog, nhóm giảm hiểu sai, phát hiện rủi ro sớm và có cơ hội tạo giá trị thực tế qua từng Increment.
