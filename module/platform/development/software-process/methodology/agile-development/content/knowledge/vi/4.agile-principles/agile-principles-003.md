# Bàn giao phần mềm hoạt động được thường xuyên với chu kỳ phù hợp

Một nhóm phát triển có thể dành nhiều tháng để viết tài liệu, thiết kế màn hình, xây API và kiểm thử từng thành phần nhưng vẫn chưa biết liệu **người dùng có hoàn thành được công việc của họ bằng sản phẩm** hay không. Khi phần mềm chỉ được cho người dùng xem ở cuối dự án, những giả định sai về nhu cầu, quy trình hoặc kỹ thuật thường được phát hiện rất muộn.

Một nguyên tắc nền tảng của **Agile** là **bàn giao phần mềm hoạt động được thường xuyên**, ưu tiên khoảng thời gian ngắn và phù hợp với bối cảnh. Nguyên tắc này tạo nhịp học hỏi qua phần mềm thật: nhóm triển khai một phần có ích, quan sát kết quả, nhận phản hồi rồi điều chỉnh các phần tiếp theo.

Trong module **AGILE_DEVELOPMENT**, đây là cầu nối giữa giá trị Agile và thực hành cụ thể như user story, Product Backlog, Scrum, Kanban, XP, đo lường dòng công việc và cải tiến liên tục. Hiểu đúng nguyên tắc giúp nhóm chọn **cách phối hợp và chu kỳ bàn giao** dựa trên giá trị, rủi ro và khả năng phản hồi, thay vì chỉ dựa vào một lịch họp cố định.

## 1. Nguyên tắc này nói điều gì?

Trong 12 nguyên tắc hỗ trợ [Tuyên ngôn Agile](https://agilemanifesto.org/principles.html), nguyên tắc về giao phần mềm thường xuyên đề cập khoảng thời gian **từ vài tuần đến vài tháng**, đồng thời **ưu tiên chu kỳ ngắn hơn**. Đó là cách diễn đạt trong bối cảnh hình thành Agile; với công cụ và hạ tầng hiện nay, một nhóm có thể tạo Increment hoặc triển khai phần mềm nhiều lần trong một ngày nếu việc đó thực sự hữu ích và an toàn.

Có bốn ý quan trọng:

1. **Bàn giao (*delivery*):** Đưa một kết quả đủ cụ thể cho người có liên quan sử dụng, chạy thử hoặc đánh giá; có bằng chứng về phần mềm đang làm được gì.
2. **Phần mềm hoạt động được (*working software*):** Tính năng đủ hoàn chỉnh và được tích hợp để thực hiện một luồng sử dụng có ý nghĩa, đáp ứng các tiêu chuẩn chất lượng đã thống nhất.
3. **Thường xuyên (*frequently*):** Tạo nhiều cơ hội nhận thông tin và điều chỉnh trong suốt quá trình phát triển, không dồn toàn bộ việc kiểm chứng đến cuối.
4. **Chu kỳ phù hợp:** Chọn nhịp bàn giao đủ ngắn để giảm rủi ro phản hồi muộn nhưng khả thi với yêu cầu chất lượng, triển khai, người dùng và những ràng buộc thực tế.

Vì vậy, **giao thường xuyên không đồng nghĩa giao thật nhiều màn hình, cũng không đồng nghĩa đẩy bất kỳ mã nguồn nào lên production càng nhiều lần càng tốt**. Mỗi lần bàn giao nên giúp nhóm trả lời rõ hơn câu hỏi: *Sản phẩm hiện đã tạo được giá trị gì, điều gì còn chưa đúng và chúng ta nên làm gì tiếp theo?*

### Cần phân biệt một số thuật ngữ

| Khái niệm | Ý nghĩa | Ví dụ về tính năng đăng ký workshop |
| --- | --- | --- |
| **Commit / merge mã nguồn** | Đưa thay đổi vào kho mã; có thể chưa tạo thành hành vi dùng được | Bổ sung hàm kiểm tra số chỗ còn trống |
| **Build / kiểm thử thành công** | Mã được đóng gói hoặc qua các bước kiểm tra kỹ thuật | Pipeline tạo bản build và chạy kiểm thử |
| **Increment hoàn chỉnh** | Phần sản phẩm tích hợp được với trạng thái hiện có, đạt tiêu chuẩn hoàn thành và có thể sử dụng | Người học xem workshop, đăng ký một chỗ hợp lệ và nhận xác nhận |
| **Delivery / bàn giao** | Đưa Increment tới môi trường hoặc đối tượng có thể đánh giá, sử dụng | Cho bộ phận nghiệp vụ và một nhóm học viên trải nghiệm phiên bản mới |
| **Deployment / triển khai** | Cài đặt một phiên bản phần mềm vào môi trường vận hành, có thể chưa mở cho người dùng | Đưa phiên bản có tính năng mới lên production nhưng tạm tắt qua feature flag |
| **Release / phát hành** | Cho một nhóm người dùng truy cập hành vi hoặc tính năng mới | Mở chức năng đăng ký cho tất cả học viên đủ điều kiện |

Những khái niệm trên **có thể trùng thời điểm**, nhưng không phải một việc. Một nhóm có thể triển khai nhiều lần mà chưa phát hành tính năng mới; cũng có thể cho người dùng thử Increment trong môi trường giới hạn trước khi phát hành rộng. Ngược lại, bản trình chiếu hoặc mô phỏng chưa tích hợp có thể hữu ích để khám phá yêu cầu nhưng **không thay thế bằng chứng từ phần mềm hoạt động được**.

## 2. Như thế nào là “phần mềm hoạt động được”?

Từ *hoạt động được* phải được đánh giá theo **hành vi người dùng và mức chất lượng cần thiết**, không chỉ theo việc chương trình chạy được trên máy lập trình viên.

Xét một nền tảng học tập đang xây chức năng đăng ký workshop:

- Một trang danh sách workshop đẹp nhưng nút **Đăng ký** chưa lưu dữ liệu là phần giao diện chưa hoàn tất.
- Một API đăng ký đã viết xong nhưng chưa được kết nối với màn hình, cơ sở dữ liệu và xử lý lỗi chưa tạo thành luồng người dùng hoàn chỉnh.
- Một chức năng cho phép đăng ký nhưng có thể nhận quá số chỗ, mất dữ liệu hoặc lộ thông tin cá nhân **chưa đủ an toàn để phát hành**, dù có vẻ chạy được trong bản demo.
- Một luồng nhỏ cho phép xem workshop, chọn một chỗ hợp lệ và nhận trạng thái xác nhận rõ ràng, đã qua kiểm thử cần thiết, là một ứng viên tốt cho Increment hoàn chỉnh.

Không phải mọi Increment đều phải bao gồm đầy đủ tầm nhìn cuối cùng của sản phẩm. Increment có thể nhỏ về **phạm vi tính năng** nhưng vẫn cần đúng về **hành vi, dữ liệu và chất lượng** trong phạm vi đó.

Một thỏa thuận **Definition of Done (DoD)** có thể bao gồm:

| Chiều chất lượng | Ví dụ kiểm tra |
| --- | --- |
| Chức năng và nghiệp vụ | Đăng ký đúng số chỗ; trạng thái xác nhận nhất quán; xử lý trường hợp workshop đầy |
| Tích hợp | Giao diện, API, cơ sở dữ liệu và các dịch vụ liên quan chạy cùng nhau |
| Kiểm thử | Kiểm thử tự động và kiểm tra thủ công cần thiết cho các rủi ro đã xác định |
| Bảo mật và quyền riêng tư | Kiểm soát quyền truy cập; không lộ dữ liệu nhạy cảm; xác thực đầu vào |
| Khả năng sử dụng và tiếp cận | Thông báo lỗi rõ ràng; luồng chính dùng được trên thiết bị mục tiêu |
| Vận hành | Có thông tin quan sát lỗi và cách khôi phục khi phát hành gặp sự cố |
| Tài liệu cần thiết | Hướng dẫn vận hành, ghi chú thay đổi hoặc hợp đồng API được cập nhật phù hợp |

DoD cụ thể phụ thuộc sản phẩm và tổ chức. Không cần gắn một số lượng kiểm thử tùy ý cho mọi tính năng, nhưng không thể bỏ các điều kiện cần thiết để gọi Increment là hoàn chỉnh.

## 3. Tại sao nhịp bàn giao thường xuyên tạo khác biệt?

### 3.1. Nhận phản hồi khi chi phí thay đổi còn thấp

Giả sử nhóm tin rằng học viên muốn chọn workshop từ lịch tháng. Nếu cho học viên dùng luồng đăng ký cơ bản sau một chu kỳ ngắn, nhóm có thể sớm phát hiện họ chỉ muốn thấy các workshop còn chỗ và thời gian bắt đầu. Phát hiện này giúp tránh đầu tư quá sâu vào giao diện không tạo giá trị.

Khi nhiều tháng trôi qua trước lần sử dụng đầu tiên, cùng một phát hiện có thể đòi hỏi sửa giao diện, API, hướng dẫn và kế hoạch kiểm thử. **Bàn giao sớm giúp giảm thời gian tồn tại của giả định chưa kiểm chứng.**

### 3.2. Rút ngắn khoảng cách từ ý tưởng đến kết quả quan sát

Một nhu cầu chỉ được viết trong backlog vẫn là giả thuyết. Khi học viên thực sự đăng ký, nhóm mới quan sát được họ có tìm đúng workshop không, thao tác nào gây nhầm lẫn, có bao nhiêu yêu cầu đăng ký thất bại và vì sao.

Nhịp bàn giao đều đặn biến việc trao đổi với người dùng thành **chuỗi quyết định dựa trên bằng chứng**, thay vì chỉ thành cuộc họp xác nhận ý tưởng.

### 3.3. Giảm kích thước lô công việc và độ khó tích hợp

Những thay đổi nhỏ được tích hợp và kiểm thử liên tục thường dễ xác định nguồn gốc lỗi hơn những thay đổi lớn được gộp vào một lần bàn giao. Nhóm cũng sớm thấy vấn đề ở môi trường thực: cấu hình, phân quyền, dữ liệu, hiệu năng, tương thích hoặc phụ thuộc dịch vụ.

Tần suất cao **không tự động** làm hệ thống ổn định. Lợi ích chỉ xuất hiện khi nhóm duy trì kiểm thử phù hợp, giới hạn việc đang làm, kiểm soát thay đổi và có khả năng quan sát, xử lý sự cố.

### 3.4. Tạo khả năng đổi ưu tiên mà vẫn có giá trị sử dụng

Nếu ngân sách hoặc mục tiêu thay đổi ở tuần thứ ba, một nhóm đã có ba Increment dùng được thường có nhiều lựa chọn hơn nhóm chỉ mới hoàn thành ba tầng kỹ thuật rời rạc. Những phần đã hoàn thành có thể tiếp tục được dùng, đánh giá hoặc mở rộng theo hướng mới.

### 3.5. Minh bạch tiến độ bằng kết quả thực tế

Phần mềm chạy được là bằng chứng cụ thể về khả năng tạo giá trị. Số lượng tác vụ được đóng, tài liệu đã viết hay phần trăm tiến độ có thể hữu ích để điều phối, nhưng không thay thế được việc thấy một luồng nghiệp vụ hoạt động trong điều kiện phù hợp.

## 4. Ví dụ xuyên suốt: Xây chức năng đăng ký workshop

Một nhóm đang phát triển nền tảng đào tạo. Mục tiêu nghiệp vụ là **học viên tự tìm và đăng ký workshop phù hợp, biết rõ mình đã có chỗ hay chưa, đồng thời ban tổ chức không phải xử lý trùng chỗ bằng tay**.

Ban đầu, bên liên quan đề nghị cả một gói tính năng: lịch tháng, bộ lọc chủ đề, trang đăng ký, danh sách chờ, email, hủy đăng ký, mã ưu đãi và dashboard quản trị. Nhóm có thể chọn xây tuần tự từng tầng giao diện, API, dữ liệu rồi chỉ giao toàn bộ sau nhiều tuần. Nhưng khi đó người dùng chưa thể thử luồng chính.

### Chia thành những lát cắt có thể bàn giao

Ví dụ minh họa dưới đây giả định nhóm có khả năng tích hợp, kiểm thử và người đánh giá sẵn sàng tham gia. Mỗi chu kỳ trong bảng kéo dài **một tuần để minh họa cách chia việc**, không phải chuẩn chung áp dụng cho mọi đội.

| Chu kỳ minh họa | Phần có thể bàn giao | Phản hồi hoặc rủi ro muốn kiểm chứng |
| --- | --- | --- |
| **1** | Học viên xem một workshop, đăng ký trong giới hạn chỗ còn lại và nhận trạng thái thành công hoặc thất bại rõ ràng | Luồng cơ bản có dễ hiểu? Kiểm tra chống vượt số chỗ hoạt động đúng không? |
| **2** | Học viên xem đăng ký của mình và tự hủy đúng chính sách; số chỗ được cập nhật nhất quán | Quy trình hủy có giảm việc hỗ trợ thủ công? Có tình huống dữ liệu sai lệch không? |
| **3** | Bổ sung thông báo xác nhận và nhắc lịch, có cơ chế xử lý lỗi gửi thông báo | Người học có bỏ lỡ workshop ít hơn? Thông báo có được gửi đúng người, đúng lúc? |
| **4** | Mở rộng tìm kiếm/lọc workshop và khả năng quản trị theo những nhu cầu đã quan sát | Nhu cầu lọc nào thực sự giúp học viên chọn được workshop? |

Trong chu kỳ 1, không nên vì muốn “ra nhanh” mà bỏ kiểm tra quyền truy cập hoặc xử lý hai học viên cùng đăng ký một chỗ cuối. Nhóm có thể giới hạn số workshop hoặc nhóm người dùng thử để **giảm phạm vi phát hành**, nhưng vẫn giữ yêu cầu đúng đắn cho luồng đã mở.

Sau chu kỳ 2, nếu số lượt hủy thấp nhưng người học phàn nàn không biết mình đã được xác nhận chưa, nhóm có thể ưu tiên cải thiện trạng thái và thông báo trước khi thêm dashboard quản trị. Đây là giá trị của **bàn giao thường xuyên kết hợp phản hồi**: kế hoạch được cập nhật theo những điều học được.

### Sơ đồ vòng lặp từ bàn giao đến học hỏi

~~~mermaid
flowchart LR
    A["Xác định kết quả cần đạt"] --> B["Chọn lát cắt giá trị nhỏ"]
    B --> C["Xây dựng, tích hợp, kiểm thử"]
    C --> D["Bàn giao Increment hoạt động được"]
    D --> E["Quan sát sử dụng và nhận phản hồi"]
    E --> F["Đánh giá kết quả và điều chỉnh backlog"]
    F --> B
~~~

Nếu bước **quan sát và điều chỉnh backlog** bị bỏ qua, nhóm chỉ đang lặp lại việc sản xuất tính năng; chưa khai thác đầy đủ mục đích học hỏi của Agile.

## 5. Chia nhỏ theo giá trị sử dụng, không chia theo tầng kỹ thuật

Một sai lầm dễ gặp là gọi mỗi giai đoạn làm xong một tầng hệ thống là một “Increment”:

| Cách chia theo tầng (*horizontal slicing*) | Hạn chế |
| --- | --- |
| Tuần 1: thiết kế toàn bộ giao diện đăng ký | Người dùng thấy màn hình nhưng chưa thực hiện đăng ký thật |
| Tuần 2: viết toàn bộ API | API có thể chưa tích hợp với giao diện và dữ liệu |
| Tuần 3: hoàn tất cơ sở dữ liệu | Chưa có hành vi nghiệp vụ hoàn chỉnh để đánh giá |
| Tuần 4: tích hợp và sửa lỗi | Lúc này mới phát hiện các giả định sai giữa các tầng |

Cách chia theo **lát cắt dọc (*vertical slice*)** ưu tiên một luồng nhỏ đi qua các tầng cần thiết:

~~~mermaid
flowchart TD
    A["Học viên chọn workshop"] --> B["Giao diện nhập yêu cầu"]
    B --> C["API xác thực và kiểm tra nghiệp vụ"]
    C --> D["Lưu đăng ký nhất quán"]
    D --> E["Trả trạng thái xác nhận"]
    E --> F["Học viên biết kết quả"]
~~~

Lát cắt đầu tiên có thể chỉ hỗ trợ **một** workshop, **một** phương thức đăng ký và **một** luồng xác nhận, nếu điều đó đủ để một nhóm người dùng có thể hoàn thành tác vụ. Các lựa chọn khác được thêm theo mức độ ưu tiên.

### Kỹ thuật chia lát cắt thực dụng

- **Theo kịch bản:** Bắt đầu với trường hợp phổ biến, sau đó bổ sung tình huống hiếm hoặc phức tạp; không trì hoãn xử lý lỗi có thể gây mất dữ liệu hay vi phạm ràng buộc.
- **Theo nhóm người dùng hoặc phạm vi sử dụng:** Phát hành cho một nhóm học viên hoặc một loại workshop trước rồi mở rộng khi đã có bằng chứng.
- **Theo mức độ quy tắc:** Hỗ trợ đăng ký miễn phí trước; thanh toán và hoàn tiền được triển khai thành các luồng hoàn chỉnh riêng khi cần.
- **Theo quyết định cần học:** Nếu chưa biết học viên muốn danh sách hay lịch tháng, kiểm chứng bằng bản mẫu trước khi đầu tư lớn; sau đó chọn lát cắt phần mềm cần xây.
- **Theo đầu cuối hành trình:** Một user story phải có tiêu chí chấp nhận nêu rõ hành vi người dùng, dữ liệu và các tình huống ngoại lệ quan trọng.

Một user story minh họa:

> **Là** học viên muốn tham gia workshop, **tôi muốn** đăng ký một chỗ còn trống và nhận trạng thái xác nhận, **để** biết chắc mình có thể tham dự.

Tiêu chí chấp nhận có thể là:

~~~gherkin
Feature: Dang ky workshop
  Scenario: Dang ky thanh cong khi con cho
    Given workshop A con cho va hoc vien du dieu kien
    When hoc vien gui yeu cau dang ky hop le
    Then he thong luu dang ky va hien thi trang thai da xac nhan

  Scenario: Hai yeu cau tranh cho cuoi cung
    Given workshop A chi con mot cho
    When hai hoc vien khac nhau yeu cau dang ky gan nhu dong thoi
    Then he thong khong xac nhan qua so cho cho phep
    And yeu cau khong thanh cong nhan thong bao ro rang
~~~

Đây là mô tả hành vi để thảo luận và kiểm thử, chưa quy định một cách triển khai cụ thể. Trong hệ thống thật, cần xác định rõ chính sách giữ chỗ, giới hạn tham dự, yêu cầu idempotency, quyền hủy và các trường hợp cạnh tranh đồng thời.

## 6. Chọn chu kỳ bàn giao như thế nào cho phù hợp?

Không tồn tại một độ dài chu kỳ tối ưu cho mọi nhóm. **Độ dài tốt là độ dài tạo được phản hồi hữu ích với chi phí và rủi ro chấp nhận được.** Chu kỳ càng ngắn càng có nhiều cơ hội kiểm chứng, nhưng nếu ngắn đến mức nhóm luôn cắt bỏ chất lượng, không đủ thời gian đánh giá hoặc phát hành gây gián đoạn, cách làm đó phản tác dụng.

### Sáu yếu tố cần xem xét

| Yếu tố | Câu hỏi giúp quyết định | Hệ quả với chu kỳ |
| --- | --- | --- |
| **Mức không chắc chắn về nhu cầu** | Giả định nào cần kiểm chứng sớm để tránh làm sai? | Nhu cầu thay đổi nhanh thường khuyến khích vòng phản hồi ngắn |
| **Thời gian để tạo một lát cắt giá trị** | Có thể chia nhỏ tới đâu mà vẫn giữ hành vi hoàn chỉnh? | Lát cắt lớn là tín hiệu nên xem lại cách chia công việc hoặc phụ thuộc |
| **Khả năng tích hợp và kiểm thử** | Có thể xây, kiểm thử, triển khai và khôi phục tin cậy không? | Nếu phát hành khó hoặc nguy hiểm, đầu tư cải thiện năng lực kỹ thuật |
| **Khả năng cung cấp phản hồi** | Ai đánh giá? Bao lâu có dữ liệu sử dụng có ý nghĩa? | Nhịp phát hành và nhịp đánh giá có thể khác nhau |
| **Chi phí, tác động đến người dùng** | Thay đổi gây gián đoạn, cần đào tạo hay chuyển đổi dữ liệu không? | Có thể gom một số thay đổi vào cửa sổ phát hành phù hợp |
| **Ràng buộc bên ngoài** | Có bước nghiệm thu, kiểm soát an toàn hoặc phối hợp hệ thống khác không? | Giữ quy trình bắt buộc; tìm cách rút ngắn thời gian chờ và tạo Increment kiểm chứng nội bộ |

### Một số nhịp thường gặp

| Nhịp minh họa | Khi nào có thể hợp lý | Cách tránh rủi ro |
| --- | --- | --- |
| Nhiều lần mỗi ngày hoặc theo nhu cầu | Dịch vụ số có kiểm thử, tự động hóa và khả năng triển khai/khôi phục tốt | Giám sát vận hành, triển khai dần, feature flag và kiểm soát thay đổi |
| Hằng tuần hoặc mỗi 1–2 tuần | Nhóm sản phẩm có thể tạo luồng giá trị nhỏ và nhận phản hồi tương đối nhanh | Dành thời gian kiểm tra Increment và kết quả sử dụng |
| Vài tuần theo một đợt phát hành | Sản phẩm phụ thuộc lịch khách hàng, phê duyệt hoặc nhiều hệ thống | Vẫn tích hợp và kiểm thử thường xuyên bên trong đợt; đừng để tồn đọng đến ngày phát hành |
| Chu kỳ dài hơn do ràng buộc đặc thù | Thiết bị, quy trình pháp lý, lịch chuyển đổi hoặc bảo trì hạn chế | Duy trì bản build chạy được, thử nghiệm, đánh giá trung gian; chủ động giảm phụ thuộc nếu có thể |

Đây là **ví dụ về các phương án**, không phải quy định “Agile = 2 tuần”. Nhóm nên bắt đầu bằng một nhịp có thể duy trì, đo hậu quả thực tế, rồi điều chỉnh.

### Ba câu hỏi kiểm tra độ dài chu kỳ

1. **Nếu giả định quan trọng đang sai, nhóm mất bao lâu để phát hiện?** Chu kỳ quá dài sẽ giữ rủi ro tiềm ẩn lâu hơn.
2. **Có thể hoàn thiện ít nhất một lát cắt nhỏ trong chu kỳ mà không hạ tiêu chuẩn chất lượng không?** Nếu không, cần chia nhỏ hoặc xử lý điểm nghẽn.
3. **Phản hồi sau bàn giao có kịp thay đổi quyết định tiếp theo không?** Nếu nhận phản hồi sau khi toàn bộ backlog đã xây, tác dụng của nhịp ngắn sẽ bị hạn chế.

## 7. Hai nhịp cần phối hợp: tạo Increment và học từ sử dụng

Không phải mọi thay đổi đều cần được phát hành công khai ngay lập tức. Có thể hình dung hai nhịp:

- **Nhịp kỹ thuật:** Tích hợp mã, kiểm thử, tạo bản build, giữ sản phẩm ở trạng thái sẵn sàng bàn giao. Nhịp này nên diễn ra liên tục hoặc đủ thường xuyên để lỗi tích hợp không tích tụ.
- **Nhịp giá trị/phản hồi:** Đưa Increment tới người đánh giá phù hợp, quan sát sử dụng, phân tích kết quả và quyết định ưu tiên tiếp theo.

Ví dụ nhóm có thể tích hợp và kiểm thử mỗi ngày, đưa bản chạy được cho nhân viên nghiệp vụ mỗi tuần, phát hành một tính năng mới cho người dùng theo từng đợt nhỏ. **Không cần ép ba hoạt động này xảy ra cùng một ngày** nếu mục đích và điều kiện khác nhau.

Tuy nhiên, nếu nhóm chỉ tích hợp liên tục mà người dùng không bao giờ nhận giá trị hoặc phản hồi không ảnh hưởng kế hoạch, nhóm mới giải quyết được một phần của nguyên tắc.

### Phản hồi nào thực sự hữu ích?

Cần kết hợp nhiều nguồn thông tin:

| Nguồn phản hồi | Điều giúp nhóm học được | Điều cần cẩn trọng |
| --- | --- | --- |
| Người dùng thử luồng mới | Họ có hoàn thành tác vụ, hiểu thông báo và gặp khó khăn ở đâu không? | Số ít người thử có thể chưa đại diện toàn bộ tập người dùng |
| Phản hồi từ người làm nghiệp vụ | Quy tắc và trường hợp ngoại lệ đã được xử lý đúng chưa? | Ý kiến của một cá nhân không thay thế quan sát người dùng cuối |
| Dữ liệu sản phẩm | Tỷ lệ hoàn tất, lỗi nghiệp vụ, thời gian thực hiện, yêu cầu hỗ trợ | Một chỉ số cần có bối cảnh; tăng số lượt sử dụng chưa chắc đã tạo giá trị |
| Dữ liệu kỹ thuật và vận hành | Lỗi, độ trễ, tính ổn định, khả năng khôi phục | Chỉ tập trung độ ổn định có thể bỏ sót vấn đề “xây đúng thứ cần xây” |

Một vòng phản hồi có ích kết thúc bằng **quyết định có thể hành động**: giữ nguyên, điều chỉnh, ưu tiên kiểm chứng thêm hoặc dừng một phương án.

## 8. Khả năng bàn giao thường xuyên cần nền tảng kỹ thuật

Tăng nhịp bàn giao chỉ bền vững khi chi phí xác minh và phát hành không tăng vượt khả năng của nhóm.

### Tích hợp liên tục và kiểm thử phù hợp

Tích hợp liên tục (*Continuous Integration, CI*) giúp phát hiện bất tương thích khi thay đổi còn nhỏ. Tùy sản phẩm, bộ kiểm tra có thể gồm kiểm thử đơn vị, tích hợp, hợp đồng API, bảo mật hoặc vài kịch bản đầu cuối quan trọng. Không cần cố định một tỷ lệ bao phủ kiểm thử cho mọi tình huống; điều quan trọng là **các rủi ro đáng kể được bảo vệ bởi kiểm tra đáng tin cậy**.

### Thiết kế cho khả năng thay đổi

Mã dễ hiểu, các ranh giới trách nhiệm rõ, cấu trúc dữ liệu có chiến lược chuyển đổi và thói quen *refactoring* giúp nhóm đưa thay đổi mới vào mà không làm hỏng phần đã có. XP nhấn mạnh thực hành kỹ thuật như kiểm thử, tích hợp thường xuyên và cải tiến thiết kế để hỗ trợ tốc độ thay đổi lâu dài.

### Triển khai và khôi phục có kiểm soát

Khi phát hành tới người dùng thật, nhóm cần cân nhắc giám sát, sao lưu, điều kiện kích hoạt chức năng, triển khai theo nhóm nhỏ và phương án xử lý sự cố. *Feature flag* cho phép tách triển khai khỏi việc mở tính năng, nhưng cờ cần được quản lý và dọn dẹp để tránh tích lũy nhiều nhánh hành vi khó kiểm thử.

### Definition of Done và tiêu chí chấp nhận

**Tiêu chí chấp nhận** giải thích một user story phải thể hiện hành vi nào. **Definition of Done** xác định mức chất lượng chung để công việc trở thành một Increment hoàn chỉnh. Hai khái niệm bổ trợ nhau: đáp ứng hành vi nhưng chưa đạt chất lượng chưa thể coi là xong; đạt kiểm tra kỹ thuật nhưng sai nhu cầu người dùng cũng không tạo kết quả mong muốn.

### Giữ công việc đang làm ở mức kiểm soát được

Nhóm làm đồng thời quá nhiều hạng mục sẽ kéo dài thời gian chờ kiểm tra, tích hợp và phản hồi. Giới hạn *work in progress (WIP)*, hoàn thành việc đang làm trước khi bắt đầu nhiều việc mới và xử lý điểm nghẽn giúp rút ngắn thời gian từ lúc bắt đầu tới khi bàn giao.

## 9. Vận dụng trong Scrum, Kanban và XP

### Scrum: Sprint tạo nhịp kiểm tra và thích ứng

Trong Scrum, Sprint có độ dài **một tháng hoặc ngắn hơn** và tạo nhịp đều để nhóm hướng tới Sprint Goal. Increment phải đáp ứng Definition of Done. Nhóm có thể tạo **nhiều Increment trong một Sprint**, và có thể giao giá trị **trước khi Sprint kết thúc** nếu thích hợp.

**Sprint Review không phải cổng phê duyệt bắt buộc để phát hành.** Đây là dịp Scrum Team và các bên liên quan xem xét kết quả, trao đổi điều đã học và điều chỉnh hướng đi. Một Sprint dài hai tuần không có nghĩa chỉ được phát hành đúng hai tuần một lần.

### Kanban: Quản lý dòng công việc liên tục

Kanban không bắt buộc tất cả công việc phải chờ một đợt Sprint mới được bàn giao. Nhóm có thể kéo công việc theo năng lực, giới hạn WIP và cải thiện dòng chảy. Cần nhìn vào **thời gian hoàn tất từng hạng mục**, điểm chờ và tính ổn định của việc bàn giao; có thể tổ chức buổi đánh giá và bổ sung backlog theo nhịp riêng.

### XP: Làm cho những thay đổi nhỏ vẫn an toàn

Extreme Programming (XP) góp phần bằng thực hành kiểm thử, tích hợp liên tục, *refactoring*, thiết kế đơn giản và phản hồi nhanh từ khách hàng. Mục đích là giảm chi phí đổi hướng và giữ hệ thống trong trạng thái có thể phát triển tiếp.

Các cách tiếp cận có thể kết hợp: nhóm dùng Scrum để phối hợp mục tiêu và trao đổi với bên liên quan, áp dụng kỹ thuật XP để giữ Increment đáng tin cậy, đồng thời sử dụng cách quan sát dòng công việc của Kanban để nhận diện tắc nghẽn.

## 10. Đo lường để cải thiện chu kỳ bàn giao

Nguyên tắc bàn giao thường xuyên cần được kiểm chứng bằng **dòng công việc, chất lượng và kết quả người dùng**, thay vì chạy theo một chỉ số đơn lẻ.

| Nhóm đo lường | Chỉ số gợi ý | Câu hỏi có thể trả lời |
| --- | --- | --- |
| Dòng công việc | **Lead time** từ lúc nhận yêu cầu đến khi hoàn tất theo định nghĩa thống nhất | Người yêu cầu phải chờ bao lâu mới nhận được giá trị? |
| Dòng công việc | **Cycle time** từ lúc bắt đầu làm tới lúc hoàn tất | Việc đã bắt đầu mất bao lâu để đi qua quy trình? |
| Dòng công việc | **Throughput** theo đơn vị thời gian; **WIP** hiện tại | Nhóm đang hoàn tất đều hay tắc nghẽn do làm quá nhiều việc cùng lúc? |
| Khả năng phát hành | Tần suất triển khai; thời gian từ thay đổi mã đến môi trường mục tiêu | Nhóm có thể đưa thay đổi đã xác minh tới môi trường sử dụng nhanh tới đâu? |
| Độ tin cậy | Tỷ lệ thay đổi gây lỗi nghiêm trọng; thời gian khôi phục dịch vụ | Nhịp phát hành có đi kèm vận hành ổn định không? |
| Giá trị cho người dùng | Tỷ lệ hoàn tất đăng ký, số lỗi trùng chỗ, yêu cầu hỗ trợ, mức độ hài lòng | Phần mềm đã giúp người dùng làm việc tốt hơn chưa? |

Các định nghĩa thời điểm bắt đầu/kết thúc cần được thống nhất trước khi so sánh số liệu. Ví dụ, nếu một nhóm tính lead time từ lúc yêu cầu được tạo còn nhóm khác tính từ lúc bắt đầu phát triển, hai con số không trực tiếp so sánh được.

### Ví dụ cách đọc số đo

Giả sử trong bốn tuần liên tiếp, một nhóm **triển khai thường xuyên hơn** nhưng **cycle time tăng** và các sự cố sau phát hành cũng tăng. Kết luận hợp lý không phải “đội đang Agile hơn vì deploy nhiều”, mà là cần kiểm tra kích thước công việc, WIP, hàng đợi kiểm thử và chất lượng thay đổi.

Ngược lại, nếu chu kỳ dài hơn đôi chút nhưng người dùng nhận được lát cắt hoàn chỉnh, tỷ lệ hoàn thành tác vụ tăng và sự cố giảm, nhóm có cơ sở xem xét giữ nhịp đó. Không nên dùng số lượt deploy hay story point như bảng xếp hạng năng suất cá nhân: điều này dễ thúc đẩy chia việc giả tạo hoặc bỏ qua chất lượng.

## 11. Các phản ví dụ dễ nhầm với bàn giao thường xuyên

| Biểu hiện | Vì sao chưa đạt mục đích | Điều chỉnh |
| --- | --- | --- |
| Mỗi tuần trình chiếu các màn hình chưa nối vào hệ thống | Chưa kiểm chứng một luồng phần mềm hoạt động được | Ưu tiên lát cắt đầu cuối có thể chạy và kiểm thử |
| Mỗi Sprint báo “xong” nhiều đầu việc nhưng không có Increment đạt DoD | Tiến độ tác vụ không đồng nghĩa giá trị bàn giao | Thống nhất DoD, hoàn thành từng lát cắt trước khi mở thêm việc |
| Phát hành liên tục nhưng người dùng không được hỏi và dữ liệu không được xem xét | Nhịp phát hành chưa tạo nhịp học hỏi | Thiết lập thời điểm đánh giá, người nhận phản hồi và quyết định từ kết quả |
| Ép mọi tính năng phải lên production theo lịch ngắn | Có thể vi phạm yêu cầu phê duyệt, gây gián đoạn hoặc tăng rủi ro | Giữ Increment sẵn sàng, tách deployment khỏi release và tôn trọng ràng buộc |
| Để sửa lỗi, tài liệu và kiểm thử sang một “Sprint chất lượng” cuối dự án | Các Increment trước chưa thực sự hoàn chỉnh | Kết hợp công việc chất lượng vào từng lát cắt và DoD |
| Chờ toàn bộ tính năng hoàn tất mới thử với người dùng | Phản hồi đến muộn, chi phí thay đổi lớn | Cho thử bản mẫu sớm và đưa phần mềm nhỏ nhưng thật vào sử dụng khi an toàn |
| Đo số lần phát hành như mục tiêu duy nhất | Dễ tăng số lần deploy mà không tăng giá trị | Đo thêm hiệu quả sử dụng và độ tin cậy |

Đặc biệt, **bản mẫu** và **Increment** có mục đích khác nhau. Bản mẫu có thể nhanh chóng kiểm tra giả định về giao diện hoặc quy trình, nhưng nếu chưa tích hợp và chưa đạt tiêu chuẩn chất lượng, nó không được tính là tính năng sẵn sàng sử dụng. Cả hai đều hữu ích tại thời điểm phù hợp.

## 12. Quy trình áp dụng vào một nhóm đang phát triển

### Bước 1. Chọn một kết quả người dùng đủ cụ thể

Ví dụ: “Học viên có thể tự đăng ký một workshop còn chỗ và nhận kết quả rõ ràng”, thay vì mục tiêu chung chung “Hoàn thành chức năng workshop”. Nêu rõ những ràng buộc quan trọng như số chỗ, quyền truy cập và điều kiện đăng ký.

### Bước 2. Lập Product Backlog theo giá trị và rủi ro

Tách những nhu cầu khác nhau thành các hạng mục có thể ưu tiên. Việc nào quan trọng với kết quả mong muốn hoặc có giả định rủi ro cao nên được kiểm chứng sớm. Backlog là công cụ điều chỉnh, không phải bản cam kết mọi hạng mục sẽ được xây bất kể phản hồi.

### Bước 3. Chia một lát cắt có thể hoàn tất trong chu kỳ

Đặt câu hỏi: *Sau chu kỳ này, một người dùng hay bên liên quan có thể thực sự làm được điều gì mà trước đó họ chưa làm được?* Nếu câu trả lời chỉ là “đã xong giao diện” hoặc “đã xong cơ sở dữ liệu”, hãy xem lại cách chia.

### Bước 4. Chốt tiêu chí chấp nhận và Definition of Done

Làm rõ hành vi cần có, các trường hợp lỗi quan trọng, chất lượng, tích hợp và yêu cầu bảo mật. Những điều này giúp cả nhóm hiểu giống nhau về chữ **hoàn thành**.

### Bước 5. Tích hợp, kiểm thử và giữ Increment có thể bàn giao

Không để các nhánh mã thay đổi độc lập quá lâu, phát hiện bất tương thích thường xuyên, thực hiện review và kiểm thử tương ứng với rủi ro. Khi phát hiện lỗi nghiêm trọng, ưu tiên sửa trước khi công bố tính năng mới.

### Bước 6. Bàn giao cho đúng đối tượng và lấy bằng chứng

Chọn môi trường và nhóm người đánh giá phù hợp: nhân viên nghiệp vụ, người dùng thử có kiểm soát hoặc người dùng rộng rãi. Đo hành vi và chất lượng, ghi nhận điều cần kiểm chứng tiếp theo. Nếu không thể phát hành công khai, vẫn tìm cơ hội đánh giá Increment vận hành trong điều kiện đại diện.

### Bước 7. Quyết định và điều chỉnh nhịp

Từ phản hồi, nhóm có thể giữ phương án, sửa một luồng, thay đổi ưu tiên backlog hoặc ngừng phần chưa tạo giá trị. Xem lại chu kỳ có đủ thường xuyên để phát hiện sai lệch không, công việc bị mắc ở bước nào và chất lượng có đang suy giảm không.

## 13. Bài tập ứng dụng

**Tình huống:** Nhóm có sáu tuần để phát triển chức năng **theo dõi tiến độ học**. Bên liên quan ban đầu muốn có dashboard biểu đồ, huy hiệu, email nhắc nhở, bảng xếp hạng và báo cáo cho giáo viên. Nhiều học viên hiện không biết mình đã hoàn thành bao nhiêu bài và nên học bài nào tiếp theo.

Hãy thử thiết kế **ba lần bàn giao liên tiếp** theo các câu hỏi:

1. Mục tiêu người dùng cốt lõi là gì? Thành phần nào trong danh sách chỉ là một phương án giải quyết?
2. Lát cắt đầu tiên cần đi qua những tầng kỹ thuật nào để học viên nhìn thấy tiến độ **thật**?
3. Các tiêu chí nào phải có để gọi lát cắt đó là “hoạt động được”?
4. Sau mỗi lần bàn giao, ai sẽ phản hồi và nhóm sẽ quan sát điều gì?
5. Nếu chu kỳ dự tính là hai tuần nhưng một hạng mục bị kẹt ở kiểm thử, nhóm nên tìm cách chia nhỏ, sửa điểm nghẽn hay bỏ qua bước kiểm tra? Vì sao?

**Gợi ý hướng giải:** Lần đầu có thể cho học viên thấy danh sách bài đã hoàn thành và bài tiếp theo dựa trên dữ liệu thật, có kiểm thử tính đúng đắn và phân quyền. Lần hai bổ sung trạng thái tiến độ chi tiết và khả năng tiếp tục bài đang học, rồi kiểm tra người dùng có tìm được bài tiếp theo nhanh hơn không. Lần ba thử một hình thức nhắc học có kiểm soát nếu dữ liệu cho thấy cần. Dashboard nhiều biểu đồ hoặc bảng xếp hạng chưa nhất thiết là ưu tiên đầu tiên. Nếu kiểm thử trở thành điểm nghẽn, nhóm nên giảm quy mô hạng mục, cải thiện tự động hóa hoặc điều phối năng lực; **bỏ kiểm tra chất lượng để giữ lịch bàn giao là đánh đổi nguy hiểm**.

## 14. Ghi nhớ và tự kiểm tra

Nguyên tắc **bàn giao phần mềm hoạt động được thường xuyên với chu kỳ phù hợp** không đặt mục tiêu tạo thật nhiều bản phát hành. Nó yêu cầu đội ngũ liên tục biến hiểu biết thành **phần mềm có thể kiểm chứng**, đưa phần mềm tới người đánh giá phù hợp, nhận bằng chứng và cập nhật quyết định. Mỗi lần bàn giao cần đủ hoàn chỉnh trong phạm vi nhỏ, được bảo vệ bằng chất lượng kỹ thuật và diễn ra với nhịp tạo ra giá trị thực.

Tự kiểm tra:

1. Một bản demo chỉ có giao diện và dữ liệu giả khác gì với Increment hoạt động được?
2. Vì sao một Sprint dài hai tuần không bắt buộc đội phải chỉ phát hành đúng một lần sau hai tuần?
3. Nếu nhóm đưa mã lên production hằng ngày nhưng không nhận phản hồi người dùng, nguyên tắc này đã được đáp ứng đầy đủ chưa?
4. Khi hệ thống có quy trình kiểm soát phát hành nghiêm ngặt, nhóm vẫn có thể rút ngắn vòng học hỏi bằng những cách nào?
5. Hãy phân biệt **tiêu chí chấp nhận**, **Definition of Done**, **deployment** và **release** trong một ví dụ cụ thể.
6. Vì sao cần xem xét cả cycle time, lỗi sau phát hành và kết quả sử dụng thay vì chỉ đếm số lượt triển khai?

Khi thực hành nguyên tắc này, hãy đặt câu hỏi thường xuyên: **“Chúng ta có thể giao phần giá trị nhỏ nhất nào một cách an toàn, và phản hồi sau lần giao đó sẽ giúp quyết định điều gì?”** Chính câu hỏi ấy kết nối nhịp phát triển tăng dần với khả năng thích ứng và cải tiến liên tục của Agile.
