# Làm rõ và phân nhỏ hạng mục trước khi chọn thực hiện

Một nhóm phát triển nền tảng học trực tuyến có hạng mục đầu tiên trong backlog: **“Xây hệ thống đăng ký khóa học”**. Hạng mục được đánh dấu ưu tiên cao vì nhiều học viên cần tính năng này. Trong Sprint Planning, mọi người mới bắt đầu hỏi: đăng ký khóa miễn phí hay trả phí, có cần tài khoản không, khi thanh toán thất bại thì sao, quyền truy cập được cấp khi nào, và có phải kết nối ngay với cổng thanh toán thật không? Cuộc họp kéo dài nhưng nhóm vẫn chưa biết có thể hoàn tất phần nào trong Sprint.

Đây là một vấn đề phổ biến của quản lý yêu cầu thích ứng: **hạng mục có giá trị nhưng còn quá rộng, quá mơ hồ hoặc mang nhiều phụ thuộc để đưa vào thực hiện một cách có trách nhiệm**. Nếu lựa chọn quá sớm, nhóm dễ làm sai nhu cầu, liên tục chờ quyết định, hoặc kết thúc với nhiều phần kỹ thuật chưa tạo được khả năng sử dụng. Ngược lại, cố phân tích mọi hạng mục trong nhiều tháng cũng làm backlog cồng kềnh và tốn công khi ưu tiên thay đổi.

Trong Agile, giải pháp là **làm rõ và phân nhỏ có chọn lọc, đúng thời điểm, vừa đủ để quyết định bước tiếp theo**. Những hạng mục gần được thực hiện cần hiểu sâu hơn; những ý tưởng xa hoặc chưa chắc có giá trị vẫn có thể ở mức tổng quan. Nhóm làm rõ vấn đề, chia theo những lát cắt có thể kiểm chứng, xử lý bất định quan trọng và lựa chọn dựa trên mục tiêu, giá trị, rủi ro, năng lực thực tế.

Bài thuộc chương **Ưu tiên và backlog** của module **AGILE_DEVELOPMENT**. Nội dung kết nối user story và Product Backlog với Scrum, Kanban, các thực hành kỹ thuật của XP và phép đo dòng công việc, giúp đội giao sản phẩm tăng dần, nhận phản hồi sớm và cải tiến liên tục.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **ý tưởng**, **hạng mục backlog**, **backlog refinement**, **ưu tiên**, **lựa chọn thực hiện**, **tiêu chí chấp nhận** và **Definition of Done**.
2. Đặt những câu hỏi cần thiết để làm rõ một hạng mục trước khi nhóm quyết định có đưa vào thực hiện hay không.
3. Nhận biết hạng mục quá lớn, phụ thuộc phức tạp hoặc chưa đủ bằng chứng; chọn cách xử lý phù hợp thay vì ước lượng tùy tiện.
4. Phân nhỏ theo **lát cắt chức năng xuyên suốt** để tạo Increment có thể kiểm tra, đồng thời phân biệt với việc chia ngang theo tầng kỹ thuật.
5. Vận dụng các cách chia theo luồng thao tác, quy tắc nghiệp vụ, biến thể, phạm vi dữ liệu và mức bất định mà vẫn bảo vệ chất lượng.
6. Áp dụng nguyên tắc của Scrum trong refinement và Sprint Planning, đồng thời hiểu cách chính sách replenishment và WIP của Kanban liên quan đến hạng mục sẵn sàng.
7. Sử dụng một ví dụ thực tế để chuyển yêu cầu lớn thành các hạng mục nhỏ, tiêu chí chấp nhận, bằng chứng cần kiểm chứng và quyết định lựa chọn tiếp theo.

## 1. Vì sao phải làm rõ trước khi chọn thực hiện?

**Product Backlog** trong Scrum là danh sách công việc mới nổi, được sắp xếp theo thứ tự, nhằm cải thiện sản phẩm. Nó thay đổi khi nhóm hiểu thêm về người dùng, thị trường, công nghệ, rủi ro và cơ hội. Một hạng mục trong danh sách có thể bắt đầu bằng một ý tưởng ngắn; khi đến gần thời điểm thực hiện, nó cần được làm rõ để Developers có thể đánh giá và triển khai.

Trong một quy trình khác như Kanban, danh sách yêu cầu vẫn cần được làm rõ trước khi được **kéo** vào luồng công việc theo chính sách đã thống nhất, dù không có Sprint. Tên gọi của các cột và buổi họp có thể khác nhau; vấn đề cốt lõi giống nhau: **chỉ bắt đầu khi hiểu đủ việc cần làm và có khả năng tiến đến trạng thái hoàn tất**.

### 1.1. Điều gì xảy ra khi chọn hạng mục quá sớm?

| Dấu hiệu | Hệ quả có thể xảy ra | Ví dụ |
|---|---|---|
| Mục tiêu không rõ | Xây đúng chức năng được yêu cầu nhưng không giải quyết vấn đề | Làm chatbot dù người dùng chủ yếu gặp lỗi thông báo không rõ |
| Phạm vi không có ranh giới | Công việc mở rộng liên tục, khó dự báo | “Thanh toán” bao gồm mọi loại thẻ, hoàn tiền, hóa đơn và đối soát |
| Thiếu tiêu chí chấp nhận | Mỗi người hiểu “xong” khác nhau | Giao diện báo thành công ngay cả khi backend chưa lưu đơn |
| Phụ thuộc chưa phát hiện | Ticket bị chặn giữa lúc đang làm | Cổng thanh toán chưa có môi trường thử nghiệm |
| Bất định kỹ thuật lớn | Ước lượng thiếu căn cứ, sửa lại nhiều | Chưa biết hệ thống cũ có hỗ trợ phân quyền theo khóa hay không |
| Hạng mục chia theo bộ phận | Nhiều việc hoàn tất riêng lẻ nhưng chưa có chức năng chạy xuyên suốt | UI xong ở Sprint này, API xong Sprint sau, kiểm thử tích hợp để cuối quý |
| Quá nhiều việc cùng bắt đầu | Tăng chuyển ngữ cảnh, chờ đợi và giảm khả năng nhận phản hồi sớm | Mười hạng mục đang phát triển, không hạng mục nào hoàn tất |

### 1.2. Làm rõ không phải viết đặc tả hoàn chỉnh cho mọi ý tưởng

Một backlog có thể chứa hàng chục hoặc hàng trăm ý tưởng với độ ưu tiên thay đổi. Nếu đội phân tích chi tiết mọi item rồi mới viết code, nhiều công sức sẽ lãng phí khi giả thuyết sản phẩm thay đổi. **Refinement là hoạt động lặp lại**, được thực hiện theo mức cần thiết đối với những hạng mục có khả năng được chọn sớm.

Một cách phân tầng thực dụng:

- **Ý tưởng xa:** nêu đối tượng, vấn đề và giá trị kỳ vọng; có thể chưa cần AC hay ước lượng chi tiết.
- **Hạng mục đang được cân nhắc:** làm rõ giả thuyết, lợi ích, rủi ro, phụ thuộc và những phương án chia nhỏ.
- **Hạng mục có khả năng được chọn sớm:** thống nhất phạm vi, ví dụ hành vi, tiêu chí chấp nhận, điều kiện chất lượng, điểm chưa chắc và cách kiểm chứng cần thiết.
- **Hạng mục đang làm:** tiếp tục trao đổi và thích ứng khi phát hiện thông tin mới, nhưng minh bạch thay đổi về phạm vi, mục tiêu và chất lượng.

Đừng xem những tầng này là bốn cột bắt buộc của Scrum. Chúng là ví dụ về cách phân bổ công sức làm rõ theo mức độ gần và độ không chắc chắn của quyết định.

## 2. Phân biệt làm rõ, sắp ưu tiên và lựa chọn thực hiện

Ba hoạt động liên quan nhưng có mục đích khác nhau:

| Hoạt động | Câu hỏi chủ đạo | Kết quả mong muốn |
|---|---|---|
| **Làm rõ / refinement** | Chúng ta có hiểu đủ về nhu cầu, phạm vi, tiêu chí, độ lớn và rủi ro của hạng mục không? | Hạng mục minh bạch hơn, được chia nhỏ hoặc bổ sung thông tin để ra quyết định |
| **Sắp xếp ưu tiên / ordering** | Trong các lựa chọn hiện có, cái gì nên được xem xét trước vì giá trị, rủi ro, phụ thuộc hoặc nghĩa vụ? | Một thứ tự có lý do và có thể thay đổi khi có bằng chứng mới |
| **Lựa chọn / selection** | Với mục tiêu và năng lực hiện tại, nhóm nên bắt đầu những hạng mục cụ thể nào? | Công việc được chọn có khả năng tiến đến hoàn tất, tạo phản hồi và phục vụ mục tiêu |

**Ưu tiên cao không tự động nghĩa là sẵn sàng.** Ví dụ, “hỗ trợ thanh toán” có giá trị và cấp bách nhưng chưa có thông tin về đối tác, bảo mật hoặc quy tắc giao dịch. Nhóm có thể ưu tiên một lát cắt kiểm chứng tích hợp hoặc một hoạt động tìm hiểu rủi ro trước, thay vì đưa cả một hạng mục không rõ phạm vi vào Sprint.

**Sẵn sàng cũng không tự động nghĩa là nên làm ngay.** Một thay đổi giao diện rất rõ ràng, dễ ước lượng và có đầy đủ AC vẫn có thể xếp sau việc sửa lỗi truy cập nghiêm trọng hoặc hoàn thiện chức năng phục vụ Product Goal.

### 2.1. Refinement trong Scrum là hoạt động liên tục

Theo Scrum Guide 2020, Product Backlog refinement là việc **chia nhỏ và định nghĩa rõ hơn các Product Backlog Items**. Đây là hoạt động thường xuyên để bổ sung những chi tiết như mô tả, thứ tự và độ lớn. Scrum không quy định một cuộc họp refinement bắt buộc với thời lượng cố định.

Trong Scrum:

- **Product Owner** chịu trách nhiệm quản lý Product Backlog hiệu quả, bao gồm việc phát triển và truyền đạt Product Goal, tạo sự minh bạch và sắp xếp Product Backlog Items.
- **Developers** chịu trách nhiệm xác định độ lớn của Product Backlog Items. Product Owner có thể giúp làm rõ và thương lượng các phương án để giảm độ lớn hoặc rủi ro.
- **Scrum Team** trao đổi với nhau và stakeholders phù hợp để giảm bất định về giá trị, hành vi và khả năng triển khai.
- Những hạng mục có thể được Scrum Team hoàn tất trong một Sprint được coi là đủ điều kiện để lựa chọn tại **Sprint Planning**; hiểu biết về điều này thường được hình thành qua refinement.

Không có một vai trò Scrum chính thức tên là “người duyệt Ready”. Một **Definition of Ready** nội bộ có thể là thỏa thuận hữu ích, nhưng Scrum Guide không bắt buộc artifact hoặc commitment như vậy. Đừng biến checklist thành cổng cứng khiến đội từ chối trao đổi hoặc trì hoãn công việc quan trọng.

### 2.2. Trong Kanban, tiêu chí kéo việc phải minh bạch

Nhóm dùng Kanban có thể định nghĩa **điểm cam kết (commitment point)** hoặc chính sách kéo việc vào hệ thống theo cách vận hành của mình. Ví dụ, một yêu cầu chỉ được kéo từ “Lựa chọn” sang “Đang thực hiện” khi:

- Mục tiêu hoặc tác dụng mong muốn đủ rõ.
- Người cần đưa ra quyết định nghiệp vụ đã được xác định.
- Phụ thuộc quan trọng được làm rõ hoặc có cách xử lý.
- Có cách biết công việc hoàn tất theo chính sách chất lượng.
- WIP và năng lực hệ thống cho phép kéo thêm việc.

Chính sách cần được kiểm tra và cải tiến, đặc biệt nếu mục tiêu dịch vụ bị ảnh hưởng bởi quá nhiều chờ đợi hoặc hạng mục mơ hồ. Kanban không đòi hỏi phải có Sprint Planning mới có thể bổ sung công việc vào luồng.

## 3. Bảy nhóm câu hỏi để làm rõ một hạng mục

Khi nhận một yêu cầu như “Làm trang quản lý đơn hàng”, đội có thể dùng bảy nhóm câu hỏi dưới đây. Không cần hỏi tất cả ở mọi hạng mục; chọn những câu phù hợp rủi ro và mục tiêu.

### 3.1. Người dùng, vấn đề và giá trị

- Ai thực sự gặp vấn đề: người mua, nhân viên hỗ trợ, quản trị viên hay đối tác?
- Họ cần hoàn thành **công việc gì**, trong tình huống nào?
- Trở ngại hiện tại đã được quan sát hay chỉ là giả định?
- Nếu giải quyết tốt, hành vi hoặc năng lực nào sẽ thay đổi?
- Có dữ liệu, phản hồi, ticket hỗ trợ hoặc quan sát nào làm căn cứ không?

Một user story minh họa:

> **Là** học viên đã thanh toán, **tôi muốn** tự xem trạng thái đơn đăng ký khóa học **để** biết khi nào có thể bắt đầu học mà không phải liên hệ hỗ trợ.

Story này tạo hướng trao đổi, không phải đặc tả đầy đủ. Nhóm vẫn phải làm rõ “trạng thái đơn” bao gồm những trạng thái nào và ai được xem.

### 3.2. Phạm vi và những gì chưa nằm trong lát cắt

- Hành vi nhỏ nhất có thể dùng hoặc kiểm chứng là gì?
- Những trường hợp nào **bắt buộc** để hành vi này đúng và an toàn?
- Những biến thể nào có thể ưu tiên sau?
- Điều gì chưa được quyết định nhưng có thể ảnh hưởng lớn đến thiết kế?
- Có phạm vi nào được đưa vào vì “sẵn tiện” mà không phục vụ mục tiêu gần?

Ví dụ, bản đầu có thể chỉ hỗ trợ **xem trạng thái của một đơn đã tồn tại**, chưa cần xuất hóa đơn, chỉnh sửa thông tin thanh toán, hoàn tiền hoặc báo cáo đa cửa hàng.

### 3.3. Quy tắc nghiệp vụ và hành vi quan sát được

- Khi thao tác thành công, dữ liệu và giao diện thay đổi thế nào?
- Trạng thái nào là hợp lệ hoặc không hợp lệ?
- Có thao tác lặp, dữ liệu trùng, hết hạn, mất mạng hay lỗi phụ thuộc không?
- Ai được quyền đọc hoặc sửa dữ liệu?
- Có trường hợp ngoại lệ nào nếu bỏ qua sẽ gây lỗi nghiêm trọng?

Các câu trả lời giúp viết **tiêu chí chấp nhận** thay vì chỉ mô tả các nút hoặc thành phần kỹ thuật.

### 3.4. Dữ liệu, tích hợp và phụ thuộc

- Nguồn dữ liệu nào là nguồn sự thật đáng tin?
- Có kết nối API, hệ thống cũ, nhà cung cấp hoặc môi trường thử nghiệm chưa sẵn không?
- Có cần chuyển đổi dữ liệu hoặc giữ tương thích với phiên bản hiện tại?
- Quyền truy cập, cấu hình và đầu mối phối hợp đã sẵn có chưa?
- Nếu phụ thuộc chưa giải quyết kịp, có lát cắt thay thế trung thực và an toàn không?

Ví dụ, nếu muốn hiển thị “Đã thanh toán”, nhóm phải biết trạng thái đáng tin lấy từ đâu. Không thể chỉ giả định rằng người dùng đã nhấn nút “Thanh toán” nghĩa là giao dịch thành công.

### 3.5. Chất lượng và ràng buộc

- Có yêu cầu về bảo mật, riêng tư, khả năng truy cập, hiệu năng hoặc độ tin cậy nào?
- Có nghĩa vụ pháp lý, hợp đồng hoặc tiêu chuẩn tổ chức cần đáp ứng?
- Điều gì thuộc **Definition of Done** chung, điều gì là **tiêu chí chấp nhận** riêng?
- Nếu một kiểm tra chưa thể thực hiện, điều đó ảnh hưởng thế nào đến khả năng gọi Done?

Không nên chọn một lát cắt “nhỏ” bằng cách bỏ phần phân quyền cần thiết hoặc để người dùng thấy trạng thái giao dịch sai.

### 3.6. Bằng chứng kiểm chứng và phản hồi

- Làm thế nào biết hành vi đã đúng: unit, integration, API, end-to-end, kiểm thử khám phá hay kiểm tra accessibility?
- Những dữ liệu hoặc môi trường nào cần có để kiểm chứng?
- Ai sẽ kiểm tra Increment và ở thời điểm nào?
- Sau khi giao, tín hiệu nào cho biết người dùng thực sự được lợi?
- Điều gì sẽ khiến chúng ta đổi thứ tự ưu tiên hoặc giải pháp?

Phần mềm đạt tiêu chí kỹ thuật cho thấy **đầu ra** hoạt động như mong đợi. Kết quả người dùng vẫn phải được quan sát qua hành vi, phản hồi và bối cảnh thực tế.

### 3.7. Độ lớn, bất định và khả năng hoàn tất

- Đội đã hiểu đủ để Developers đánh giá độ lớn chưa?
- Có thể đưa lát cắt này đến chuẩn Done trong khoảng thời gian lựa chọn không?
- Điều gì tạo ra phần lớn bất định: nhu cầu, kỹ thuật, dữ liệu, tích hợp hay phê duyệt?
- Đâu là một thử nghiệm hoặc nhiệm vụ khám phá có thời hạn giúp giảm bất định?
- Nếu mục quá lớn, có cách chia để mỗi phần tạo bằng chứng độc lập không?

Không nên hỏi “ước lượng chính xác bao nhiêu ngày?” khi đội còn chưa thống nhất chức năng. **Độ bất định cao là thông tin quản trị có ích**, không phải lý do chọn một con số cho đủ biểu mẫu.

## 4. Tiêu chí chấp nhận giúp xác định ranh giới “xong”

Một backlog item nhỏ vẫn có thể mơ hồ nếu chưa biết điều gì được xem là đúng. **Acceptance criteria (AC)** nên diễn đạt hành vi có thể quan sát trong bối cảnh cụ thể, bao gồm trường hợp thành công và rủi ro quan trọng.

Ví dụ với hạng mục **“Xem trạng thái đơn đăng ký khóa học”**:

| ID | Tiêu chí chấp nhận minh họa |
|---|---|
| AC-01 | Học viên đã đăng nhập xem được danh sách đơn của chính mình với trạng thái hiện tại theo nguồn dữ liệu đáng tin. |
| AC-02 | Khi đơn đang chờ xác nhận thanh toán, giao diện thể hiện trạng thái “Đang xử lý”, không tự nhận “Đã thanh toán”. |
| AC-03 | Khi thanh toán đã được xác nhận hợp lệ, trạng thái đơn phản ánh kết quả và chỉ hiển thị quyền học khi việc cấp quyền đã hoàn tất theo quy tắc sản phẩm. |
| AC-04 | Học viên không thể xem hoặc truy vấn đơn của tài khoản khác qua giao diện hoặc API liên quan. |
| AC-05 | Khi dịch vụ trạng thái tạm lỗi, giao diện hiển thị tình huống không thể tải và cách thử lại phù hợp, không hiển thị dữ liệu cũ như kết quả chắc chắn mới nhất. |
| AC-06 | Thông tin trạng thái và các điều khiển liên quan đáp ứng yêu cầu khả năng truy cập của sản phẩm. |

Đây là **ví dụ để học**, không phải quy tắc hoàn chỉnh cho sản phẩm thanh toán thực tế. Cần làm rõ các trạng thái cụ thể theo mô hình dữ liệu, chính sách hoàn tiền, giới hạn thời gian đồng bộ, bảo mật và các hệ thống liên quan.

### 4.1. Đặc tả bằng ví dụ Given–When–Then

Khi các bên hiểu khác nhau về hành vi, có thể dùng ví dụ:

~~~gherkin
Feature: Xem trang thai don dang ky khoa hoc

  Scenario: Don dang cho xac nhan thanh toan
    Given hoc vien A da dang nhap
    And don D cua A dang o trang thai cho xac nhan thanh toan
    When A mo trang chi tiet don D
    Then he thong hien thi trang thai dang xu ly
    And he thong khong hien thi rang D da thanh toan

  Scenario: Khong xem duoc don cua tai khoan khac
    Given hoc vien A da dang nhap
    And don E thuoc tai khoan B
    When A co gang truy cap don E
    Then he thong tu choi truy cap theo chinh sach
    And khong de lo thong tin rieng cua don E
~~~

Gherkin ở trên chỉ là **đặc tả minh họa**, chưa chứng minh có bài kiểm thử tự động được thực thi. Bằng chứng cần đến từ các phép kiểm tra thực sự chạy trên phiên bản và môi trường phù hợp.

### 4.2. AC, DoD và outcome có vai trò khác nhau

- **AC của hạng mục:** Hành vi nghiệp vụ nào cần đúng ở lát cắt này?
- **Definition of Done:** Những tiêu chuẩn chất lượng chung nào áp dụng cho Increment trước khi được gọi là hoàn tất?
- **Outcome:** Sau khi dùng sản phẩm, người dùng có hoàn thành việc của họ tốt hơn không?

Ví dụ, một chức năng hiển thị trạng thái có thể đạt AC và DoD nhưng người dùng vẫn gọi hỗ trợ vì các nhãn “Đang xử lý” hoặc “Đã xác nhận” khó hiểu. Khi đó, **đầu ra có thể hoàn tất**, còn giả thuyết giá trị cần được kiểm tra và điều chỉnh qua backlog.

Không kéo outcome vào DoD theo cách khiến phần mềm không bao giờ có thể hoàn tất nếu chỉ số người dùng cần nhiều tuần để quan sát. Đồng thời, không bỏ qua DoD để sớm giao tính năng “cho có dữ liệu”.

## 5. Phân nhỏ theo lát cắt chức năng xuyên suốt

**Phân nhỏ (splitting)** nhằm biến một hạng mục quá lớn thành những phần có mục tiêu, hành vi và cách kiểm chứng rõ hơn. Cách chia thường hữu ích nhất cho phát triển sản phẩm là **lát cắt dọc (vertical slice)**: một phần nhỏ đi qua các lớp cần thiết để tạo ra một khả năng có thể sử dụng hoặc một giả thuyết có thể kiểm tra.

### 5.1. Lát cắt ngang và lát cắt dọc

Giả sử có hạng mục “Đăng ký một khóa học”.

**Cách chia ngang theo tầng kỹ thuật:**

~~~text
Ticket 1: Xây tất cả màn hình đăng ký
Ticket 2: Viết toàn bộ API đăng ký
Ticket 3: Thiết kế tất cả bảng dữ liệu
Ticket 4: Viết test cho cả hệ thống đăng ký
~~~

Mỗi ticket có thể lớn và phụ thuộc vào những ticket khác. Khi UI đã hoàn tất, người học vẫn chưa đăng ký được; có thể phải chờ nhiều Sprint mới tích hợp và phát hiện lỗi thực tế.

**Cách chia dọc theo hành vi người dùng:**

~~~text
Lát cắt 1: Học viên đăng nhập ghi danh khóa miễn phí
            và thấy khóa trong danh sách học của mình.

Lát cắt 2: Học viên biết rõ khi việc ghi danh thất bại
            hoặc khóa không còn nhận đăng ký.

Lát cắt 3: Học viên đăng ký khóa trả phí qua phương thức
            đã chọn, với xác nhận giao dịch đáng tin.

Lát cắt 4: Học viên xem trạng thái thanh toán đang xử lý,
            hủy/thất bại và xử lý theo chính sách.
~~~

Mỗi lát cắt cần phần giao diện, nghiệp vụ, dữ liệu, kiểm thử và tích hợp tương ứng. **Đạt Done ở lát cắt 1** nghĩa là đã có một luồng ghi danh miễn phí thực sự hoạt động theo phạm vi thống nhất; không có nghĩa hệ thống đăng ký mọi loại khóa đã hoàn tất.

Sơ đồ:

~~~mermaid
flowchart LR
    subgraph H["Chia ngang theo lớp"]
      UI["UI hoàn chỉnh"] --> API["API hoàn chỉnh"] --> DB["Database hoàn chỉnh"]
    end
    subgraph V["Chia dọc theo hành vi"]
      F["Ghi danh khóa miễn phí\nUI + API + dữ liệu + kiểm thử"]
      P["Ghi danh khóa trả phí\nUI + API + dữ liệu + kiểm thử"]
      E["Xử lý trường hợp lỗi\nUI + API + dữ liệu + kiểm thử"]
    end
~~~

Sơ đồ chỉ minh họa hai kiểu chia. Trong thực tế có thể cần công việc kiến trúc hoặc nền tảng riêng; điều quan trọng là **không lấy nhiệm vụ kỹ thuật cô lập làm bằng chứng rằng người dùng đã nhận được khả năng mới**.

### 5.2. Thế nào là một lát cắt đủ nhỏ?

Một lát cắt tốt thường:

1. **Đóng góp rõ vào mục tiêu người dùng** hoặc giảm một bất định/rủi ro cần thiết để tạo giá trị.
2. **Có phạm vi và ranh giới riêng:** người dùng, trạng thái, loại dữ liệu hoặc quy tắc nào được bao gồm.
3. **Có hành vi quan sát được:** có thể thiết kế AC và bằng chứng kiểm chứng.
4. **Có thể hoàn tất theo tiêu chuẩn chất lượng:** không cần hạ DoD hoặc bỏ kiểm soát an toàn.
5. **Đủ độc lập để chọn và dự báo:** phụ thuộc được quản lý, không phải chờ toàn bộ tính năng lớn mới kiểm chứng được.
6. **Có ý nghĩa để nhận phản hồi:** từ người dùng, stakeholders hoặc thử nghiệm kỹ thuật phù hợp.

Một lát cắt không nhất thiết phải tự tạo doanh thu hoặc được công bố ngay cho tất cả khách hàng. Nó có thể được hoàn thiện và kiểm tra trong một môi trường thích hợp, phát hành theo cờ tính năng hoặc cho nhóm dùng thử; cần **nói rõ giới hạn** để không nhầm bản chạy thử với khả năng sản xuất đầy đủ.

## 6. Các kỹ thuật phân nhỏ thường dùng

Không có một công thức phù hợp mọi hạng mục. Hãy chọn chiều phân nhỏ bám vào **hành vi, giá trị và rủi ro**, tránh tự chia chỉ theo tên của thành phần kỹ thuật.

### 6.1. Chia theo bước trong hành trình người dùng

Hạng mục ban đầu: “Quản lý toàn bộ vòng đời đăng ký khóa”.

Có thể tách:

1. Học viên xem thông tin và điều kiện đăng ký.
2. Học viên đăng ký khóa miễn phí khi đủ điều kiện.
3. Học viên xem trạng thái đăng ký.
4. Học viên hủy đăng ký theo quy tắc được phép.
5. Học viên đăng ký khóa trả phí và được cấp quyền hợp lệ.

Không phải mỗi bước đều độc lập hoặc có cùng ưu tiên. Nhóm cần lựa chọn **một luồng nhỏ hoàn chỉnh** làm lát cắt đầu tiên, rồi mở rộng theo bằng chứng.

### 6.2. Chia theo quy tắc nghiệp vụ

Hạng mục ban đầu: “Áp dụng toàn bộ chính sách giảm giá khi mua khóa”.

Có thể bắt đầu từ quy tắc rõ và có ích, rồi mở rộng:

| Lát cắt | Quy tắc được hỗ trợ | Chú ý |
|---|---|---|
| 1 | Một mã giảm giá hợp lệ cho khóa đủ điều kiện | Không được tính sai tổng tiền hoặc bỏ qua bảo mật |
| 2 | Mã hết hạn và không đủ điều kiện | Làm rõ kết quả từ chối, thông báo cho người dùng |
| 3 | Giới hạn số lần sử dụng | Cần xử lý đồng thời và tính đúng đắn dữ liệu |
| 4 | Phối hợp nhiều chương trình khuyến mãi | Làm rõ thứ tự áp dụng và trường hợp xung đột |

Một lát cắt ban đầu đơn giản nhưng vẫn phải **đúng trong phạm vi được tuyên bố**. Không chấp nhận giá sai ở trường hợp bị loại trừ chỉ để nói đã giao phần đầu.

### 6.3. Chia theo loại dữ liệu hoặc nhóm đối tượng

Ví dụ hệ thống tìm kiếm hỗ trợ khóa học, giảng viên và bài viết. Lát cắt đầu có thể cho phép tìm **khóa học** với dữ liệu thật và tiêu chí rõ, sau đó thêm **giảng viên** và **bài viết**.

Hoặc một báo cáo nội bộ ban đầu chỉ phục vụ một vai trò có quyền hạn cụ thể, rồi mới mở rộng thêm các vai trò khác. Trong mọi trường hợp, chính sách phân quyền đối với dữ liệu hiện có vẫn phải đúng; không dùng việc chia theo nhóm người để bỏ qua sự riêng tư của nhóm còn lại.

### 6.4. Chia theo mức phức tạp của trường hợp

Ví dụ chức năng đặt lịch:

- Lát cắt đầu: đặt một khung giờ còn trống theo múi giờ và điều kiện đã thống nhất.
- Lát cắt sau: đổi lịch theo quy tắc cho phép.
- Lát cắt tiếp: xử lý lịch trùng và danh sách chờ.
- Lát cắt kế: lịch định kỳ hoặc đồng bộ lịch ngoài.

Tuy nhiên, **trường hợp lỗi thiết yếu** không nên bị đẩy hết sang các lát cắt sau. Ngay trong phần đầu, phải ngăn đặt trùng không hợp lệ nếu hệ thống đã có nhiều người dùng, xử lý yêu cầu lỗi và bảo vệ quyền truy cập.

### 6.5. Chia theo kênh hoặc thiết bị

Một sản phẩm có thể bắt đầu bằng luồng web được hỗ trợ, rồi mở rộng sang thiết bị di động hoặc ứng dụng native nếu phù hợp. Nhưng khi đã tuyên bố một kênh được hỗ trợ, mức chất lượng và khả năng truy cập áp dụng phải được giữ. Đừng gọi một giao diện trên web đã đủ nếu hành vi sản phẩm bắt buộc phải hỗ trợ nhiều kênh ngay từ đầu theo hợp đồng.

### 6.6. Chia theo hành vi đơn giản rồi mở rộng

Ví dụ phân tích dữ liệu học tập:

1. Học viên xem số bài đã hoàn thành trong một khóa.
2. Học viên xem tiến độ theo từng tuần.
3. Học viên lọc theo giai đoạn.
4. Học viên xem phân tích nâng cao hoặc gợi ý học tập.

Phân nhỏ không có nghĩa xây phiên bản đầu “giả” để hiển thị bất kỳ con số nào. Mỗi lát cắt phải có cách tính chính xác cho **phạm vi nó hỗ trợ**.

### 6.7. Phân nhỏ để kiểm chứng giả thuyết rủi ro

Nếu hạng mục lớn vì đội chưa biết thuật toán đề xuất có đủ chính xác hoặc tích hợp đối tác có khả thi, nên thử một **spike có giới hạn thời gian** hoặc một **thử nghiệm nhỏ** trước khi cam kết toàn bộ triển khai.

Ví dụ:

> Trong tối đa hai ngày, kiểm tra xem API đối tác có cung cấp trạng thái giao dịch đúng yêu cầu bằng môi trường sandbox; ghi lại khả năng, giới hạn, rủi ro và quyết định tiếp theo.

**Spike là công việc học tập**, không tự động là Increment hoàn tất của sản phẩm trong Scrum. Kết quả nên là bằng chứng và quyết định cụ thể, sau đó đội chọn một lát cắt sản phẩm có thể đạt DoD. Nếu kết quả spike không đáng tin, cần nói rõ thay vì dùng một prototype có mock để bảo đảm chắc chắn khả năng tích hợp.

### 6.8. Khi phân nhỏ làm mất tính toàn vẹn

Cần dừng lại khi cách chia khiến:

- Một phần tạo dữ liệu sai hoặc gây mất tính nhất quán.
- Người dùng đi vào luồng chưa thể hoàn tất và hiểu nhầm là thành công.
- Kiểm thử hoặc bảo mật chỉ còn được dự kiến “làm sau” mà không có bảo vệ tối thiểu.
- Phát hành riêng từng phần vi phạm hợp đồng hay quy định.
- Chi phí phụ thuộc lớn hơn lợi ích nhận phản hồi sớm.

Hãy đổi chiều chia, sử dụng feature flag hoặc môi trường thử phù hợp, bổ sung điều kiện kiểm soát và minh bạch khả năng đã được kiểm chứng. **Nhỏ hơn chỉ tốt khi vẫn đúng, an toàn và có ích cho quyết định.**

## 7. Dùng INVEST như câu hỏi gợi ý, không phải luật cứng

**INVEST** là một tập tiêu chí thực dụng để xem xét chất lượng user story:

| Chữ | Ý nghĩa | Câu hỏi khi refinement |
|---|---|---|
| **I — Independent** | Tương đối độc lập | Có thể hoàn tất và kiểm tra story mà không phải đợi toàn bộ epic không? |
| **N — Negotiable** | Có thể thương lượng | Story diễn đạt nhu cầu hay đã khóa một giải pháp kỹ thuật không cần thiết? |
| **V — Valuable** | Có giá trị | Hành vi này có ích cho người dùng/stakeholder hoặc giảm rủi ro cần thiết không? |
| **E — Estimable** | Có thể ước lượng hợp lý | Developers đã hiểu đủ phạm vi, phụ thuộc và bất định để đánh giá độ lớn chưa? |
| **S — Small** | Đủ nhỏ | Nhóm có thể hoàn tất phần này trong khoảng thời gian lựa chọn mà vẫn đạt chất lượng không? |
| **T — Testable** | Có thể kiểm chứng | Có AC và cách quan sát hành vi đúng/sai rõ ràng không? |

INVEST là **heuristic**, không phải một chứng chỉ “đạt chuẩn Agile”. Một story có thể phụ thuộc vào một migration hợp lý, một rủi ro kiến trúc hoặc một quyết định pháp lý. Điều cần làm là **làm rõ và quản lý phụ thuộc**. Không chia giả tạo để đánh dấu đủ sáu chữ.

Ví dụ, “lưu khóa học yêu thích” có giá trị và có thể kiểm chứng; nhưng nếu chưa có khái niệm tài khoản hay lưu trữ người dùng, độ độc lập và độ lớn của nó phải được xem lại. Nhóm có thể chọn một lát cắt tài khoản tối thiểu, hoặc ưu tiên khả năng khác có giá trị hơn trước.

### 7.1. Kích thước và ước lượng là công cụ thảo luận

Hạng mục quá lớn thường chứa nhiều điều chưa rõ. Developers có thể dùng ước lượng tương đối, chia cỡ, xác suất hoặc một phương pháp dự báo khác để trao đổi về độ lớn và rủi ro. **Story point không phải đơn vị thời gian tuyệt đối, không đo giá trị và không phù hợp để so năng suất cá nhân hoặc các đội khác nhau.**

Hãy tách ba câu hỏi:

1. **Có giá trị không?** Product Owner và các bên liên quan cân nhắc tác động và mục tiêu.
2. **Có rõ và đủ nhỏ không?** Developers cùng những người liên quan kiểm tra phạm vi, phụ thuộc và tính khả thi.
3. **Nên chọn lúc nào?** Xem mục tiêu hiện tại, thứ tự backlog, năng lực, chất lượng và rủi ro.

Ước lượng có thể thay đổi khi có thông tin mới. Điều đó không tự chứng minh đội đã làm sai; refinement chính là quá trình giảm bất định trước quyết định.

## 8. Ví dụ xuyên suốt: từ epic lớn đến các lát cắt được chọn

> **Tình huống giả định:** Các hạng mục và số liệu trong ví dụ chỉ phục vụ học tập. Chúng không phải backlog hay kết quả của một sản phẩm thực tế.

Một nền tảng học trực tuyến muốn giúp học viên tự đăng ký và bắt đầu khóa học, giảm số lượt phải liên hệ bộ phận hỗ trợ.

### 8.1. Yêu cầu ban đầu chưa đủ để chọn

**Epic:** “Xây hệ thống đăng ký khóa học hoàn chỉnh”.

Trong cuộc trao đổi đầu, mọi người có cách hiểu khác nhau:

- Product Owner muốn giảm bước thủ công cho người học.
- Developer cho rằng cần triển khai tích hợp thanh toán toàn diện.
- QA nghĩ hệ thống phải xử lý tất cả trạng thái hoàn tiền.
- Nhân viên hỗ trợ muốn người dùng thấy rõ lý do đơn bị từ chối.
- Vận hành lo về việc cấp quyền học trước khi thanh toán được xác nhận.

Nếu giữ hạng mục này thành một story duy nhất và yêu cầu “ước lượng để chọn Sprint”, bất định vừa ở **phạm vi**, vừa ở **quy tắc nghiệp vụ**, vừa ở **tích hợp**. Cách hữu ích hơn là làm rõ mục tiêu, tách lát cắt, nhận diện rủi ro và sắp ưu tiên.

### 8.2. Làm rõ người dùng và kết quả mong muốn

Đội thống nhất:

> **Mục tiêu sản phẩm cho giai đoạn cải thiện:** Người học đủ điều kiện có thể tự đăng ký và bắt đầu khóa học thuận lợi, với trạng thái rõ ràng, phân quyền đúng và ít phải nhờ hỗ trợ.

Tín hiệu có thể theo dõi sau khi phát hành:

- Tỷ lệ người dùng tự hoàn tất luồng đăng ký và vào bài học đầu.
- Thời gian từ lúc bắt đầu đăng ký đến khi có quyền truy cập hợp lệ.
- Tỷ lệ phải liên hệ hỗ trợ vì không hiểu trạng thái.
- Các guardrail về truy cập sai quyền, giao dịch trùng và lỗi cấp quyền.

Các tín hiệu này là **outcome và chất lượng cần quan sát**, chưa phải cam kết rằng mỗi lát cắt sẽ lập tức làm chỉ số tăng.

### 8.3. Tách epic thành các khả năng cụ thể

| Mã minh họa | Hạng mục nhỏ hơn | Phạm vi được tuyên bố | Bằng chứng có thể kiểm tra |
|---|---|---|---|
| **REG-01** | Ghi danh khóa miễn phí | Người học đã đăng nhập, khóa mở và còn nhận đăng ký | Đăng ký thành công, có quyền đúng khóa, không tạo ghi danh trùng |
| **REG-02** | Xử lý tình huống không đủ điều kiện | Khóa đóng đăng ký, tài khoản thiếu quyền hoặc dữ liệu không hợp lệ | Hệ thống từ chối đúng, thông báo rõ và không cấp quyền sai |
| **REG-03** | Hiển thị trạng thái đăng ký | Đơn/ghi danh của chính tài khoản, các trạng thái đã thống nhất | UI và API phản ánh trạng thái đúng; không đọc được đơn của người khác |
| **REG-04** | Thanh toán bằng một phương thức được hỗ trợ | Một luồng thanh toán thật theo điều kiện tích hợp và quy định | Trạng thái giao dịch được xác nhận tin cậy, không cấp quyền quá sớm |
| **REG-05** | Xử lý thanh toán chưa hoàn tất/thất bại | Đang chờ, thất bại, yêu cầu lặp, lỗi phụ thuộc | Không báo thành công giả; người dùng hiểu lựa chọn tiếp theo |
| **REG-06** | Hoàn tiền/hủy theo chính sách | Những trường hợp được phép của giai đoạn sau | Quy tắc dữ liệu và quyền học sau hoàn tiền được kiểm chứng |

Đây là **một cách chia đề xuất**, không mặc định thứ tự triển khai. Nếu nền tảng chỉ bán khóa trả phí, REG-01 có thể không tạo giá trị cho người dùng mục tiêu; đội cần chọn lát cắt khác, chẳng hạn một giao dịch sandbox hoặc một luồng thanh toán giới hạn được kiểm chứng an toàn.

### 8.4. Làm rõ REG-01 đến mức có thể cân nhắc chọn

**User story REG-01**

> Là học viên đã đăng nhập, tôi muốn ghi danh một khóa miễn phí còn nhận đăng ký để có thể bắt đầu học ngay mà không cần liên hệ hỗ trợ.

**Giới hạn lát cắt:** Một khóa miễn phí có thể đăng ký, không liên quan thanh toán. Những khóa trả phí, chờ duyệt hoặc có số chỗ giới hạn phức tạp được để thành các hạng mục khác nếu chưa cần cho lát cắt này.

**AC minh họa:**

| ID | Hành vi mong đợi |
|---|---|
| AC-01 | Khi học viên đủ điều kiện ghi danh khóa miễn phí đang mở, hệ thống tạo quan hệ ghi danh đúng tài khoản và đúng khóa. |
| AC-02 | Sau khi ghi danh thành công, học viên thấy khóa trong danh sách khóa của mình và mở được nội dung được phép. |
| AC-03 | Yêu cầu ghi danh lặp không tạo hai quan hệ ghi danh gây sai dữ liệu hoặc quyền học. |
| AC-04 | Khi khóa đã đóng hoặc người dùng không đủ điều kiện, hệ thống từ chối đúng và không cấp quyền. |
| AC-05 | Tài khoản khác không thể dùng API để tự cấp hoặc thay đổi quyền học không hợp lệ. |
| AC-06 | Khi dịch vụ ghi danh gặp lỗi, giao diện không xác nhận thành công nếu chưa có kết quả đáng tin; có thông báo phù hợp. |

**Các phụ thuộc:** Đã có tài khoản đăng nhập, dữ liệu khóa học và cách cấp quyền học nhất quán. Nếu chưa có, phải xem lại khả năng hoàn tất lát cắt. Có thể cần một việc nền tảng rất nhỏ đi cùng lát cắt hoặc lựa chọn thứ tự khác.

**Bằng chứng:** Kiểm tra hành vi UI–API–dữ liệu, kiểm thử quyền truy cập và lặp yêu cầu, kết quả chạy trên build/môi trường đã thống nhất; sau phát hành quan sát tỷ lệ tự ghi danh và lỗi thực tế.

**DoD:** Áp dụng chuẩn chất lượng chung của sản phẩm, gồm tích hợp, kiểm thử liên quan và các yêu cầu an toàn thích hợp. **Chỉ pass AC chưa chắc đã đạt DoD** nếu còn vi phạm tiêu chuẩn chất lượng chung.

### 8.5. Đánh giá độ sẵn sàng mà không đánh tráo ưu tiên

Sau làm rõ, đội có thể thấy:

| Hạng mục | Giá trị / tính cấp bách | Độ rõ và khả năng hoàn tất | Quyết định minh họa |
|---|---|---|---|
| REG-01 — Ghi danh khóa miễn phí | Cao nếu có nhiều khóa miễn phí | Tương đối rõ; có thể kiểm chứng end-to-end | Cân nhắc chọn sớm nếu phù hợp Product Goal |
| REG-02 — Không đủ điều kiện | Quan trọng cho tính đúng đắn và an toàn | Có thể đi cùng REG-01 ở những trường hợp thiết yếu | Giữ điều kiện bảo vệ bắt buộc trong lát cắt đầu, tách biến thể nâng cao nếu hợp lý |
| REG-03 — Xem trạng thái | Có ích, giảm câu hỏi hỗ trợ | Cần thống nhất nguồn dữ liệu và trạng thái | Làm rõ thêm rồi chọn theo giá trị |
| REG-04 — Thanh toán | Có thể là giá trị cốt lõi, thậm chí cấp bách nhất | Tích hợp đối tác chưa biết có hỗ trợ yêu cầu không | Ưu tiên kiểm tra rủi ro tích hợp hoặc lát cắt giao dịch giới hạn |
| REG-05/06 — Ngoại lệ thanh toán/hoàn tiền | Có trường hợp bắt buộc về tính đúng đắn hoặc pháp lý | Nhiều quy tắc và phụ thuộc | Tách phần thiết yếu khỏi phần nâng cao, tham vấn nghiệp vụ và an toàn |

Không được bỏ các kiểm soát thanh toán trọng yếu chỉ vì muốn chia phần ngoại lệ để làm sau. Nếu một luồng trả phí bắt buộc có xác nhận giao dịch và chống xử lý trùng, đó phải là một phần của tiêu chuẩn tối thiểu để luồng chạy đúng.

### 8.6. Ra quyết định chọn cho Sprint tiếp theo

Giả sử mục tiêu Sprint có thể là: **“Học viên đã đăng nhập có thể tự ghi danh khóa miễn phí hợp lệ và bắt đầu học”**.

Trong Sprint Planning:

1. Scrum Team cùng làm rõ **vì sao Sprint có giá trị** và xác định Sprint Goal phù hợp.
2. Developers lựa chọn các Product Backlog Items cần thiết, xem năng lực, Definition of Done, công việc còn dở và các yếu tố ảnh hưởng.
3. Developers lập kế hoạch để tạo Increment đạt chất lượng; Product Owner giúp làm rõ ưu tiên và thương lượng phạm vi khi thích hợp.
4. Nếu còn phụ thuộc khiến REG-01 chưa có khả năng hoàn tất, nhóm điều chỉnh lựa chọn hoặc giải quyết bất định trước.

Thành công của Sprint là **Increment thực sự đáp ứng DoD và giúp tiến gần Sprint Goal**. “Đã xây UI 100% và API 80%” không tương đương việc học viên ghi danh thành công.

### 8.7. Dùng phản hồi để quyết định lát cắt tiếp

Sau khi có phần mềm hoạt động được, đội có thể phát hiện học viên không tìm được nút đăng ký, hoặc hệ thống gửi thông báo chậm dù ghi danh thành công. Dữ liệu mới có thể làm đội ưu tiên sửa luồng hiện tại trước khi mở thanh toán. Ngược lại, nếu xác nhận luồng miễn phí ít người dùng và doanh nghiệp đang cần bán khóa trả phí, Product Owner có thể điều chỉnh thứ tự backlog.

**Refinement và lựa chọn không phải quyết định một lần cho cả quý.** Chúng được cập nhật khi có bằng chứng sản phẩm, thay đổi nhu cầu hoặc rủi ro mới.

## 9. Dùng story mapping để nhìn toàn bộ hành trình rồi chia lát cắt

**User story mapping** là cách sắp xếp những nhu cầu hoặc hoạt động của người dùng theo trình tự hành trình, sau đó đặt các biến thể hoặc hạng mục chi tiết bên dưới để xác định những lát cắt phát hành phù hợp.

Một sơ đồ văn bản đơn giản:

~~~text
HÀNH TRÌNH:      Tìm khóa       Chọn khóa        Ghi danh           Bắt đầu học
                   |              |                 |                    |
Đầu tiên:       Xem chi tiết -> Chọn miễn phí -> Ghi danh hợp lệ -> Mở bài đầu tiên
                   |              |                 |                    |
Mở rộng:        Lọc nâng cao -> Khóa trả phí -> Thanh toán       -> Quản lý quyền học
                   |              |                 |                    |
Thêm:           Gợi ý khóa   -> Mã giảm giá    -> Hoàn tiền        -> Theo dõi tiến độ
~~~

Lưu ý sơ đồ không có nghĩa nhóm được bỏ các trường hợp lỗi hoặc bảo mật tối thiểu ở hàng “Đầu tiên”. Những điều kiện bắt buộc để luồng đầu đúng phải được tích hợp trong lát cắt đó.

### 9.1. Khi nào story mapping hữu ích?

- Epic bao gồm nhiều bước hành trình và các nhóm hiểu khác nhau về phạm vi.
- Có quá nhiều backlog items rời rạc, khó liên hệ với nhu cầu người dùng.
- Cần chọn một **phiên bản đầu có thể kiểm chứng** mà vẫn nhìn thấy con đường mở rộng.
- Có những phụ thuộc khiến một thứ tự phân phối tưởng hợp lý lại không thể tạo luồng chạy được.

Story map là công cụ thảo luận, không bảo đảm tự động có hạng mục độc lập hoặc đúng thứ tự ưu tiên. Phải tiếp tục kiểm tra kỹ thuật, giá trị và chất lượng.

## 10. Làm rõ bất định và phụ thuộc trước khi ước lượng

Một hạng mục có thể dài vì công việc nhiều, hoặc vì đội **chưa biết mình cần làm gì**. Hai trường hợp cần xử lý khác nhau.

### 10.1. Phân loại bất định

| Loại bất định | Dấu hiệu | Bước giảm bất định phù hợp |
|---|---|---|
| **Nhu cầu** | Chưa rõ người dùng cần tính năng hay vấn đề nằm ở nơi khác | Phỏng vấn, quan sát tác vụ, prototype hoặc thử nghiệm giá trị |
| **Nghiệp vụ** | Các bên hiểu khác nhau về trạng thái, quyền, giá hoặc điều kiện ngoại lệ | Thảo luận ví dụ nghiệp vụ, thống nhất AC và quy tắc |
| **Kỹ thuật** | Chưa biết API, hiệu năng, kiến trúc hoặc thư viện có đáp ứng | Spike có thời hạn, proof of concept và phép đo phù hợp |
| **Dữ liệu** | Không chắc chất lượng, nguồn dữ liệu, migration hoặc nhất quán | Kiểm tra mẫu đại diện, truy vết nguồn, thử chuyển đổi có kiểm soát |
| **Phụ thuộc ngoài** | Đối tác, đội khác, quyền truy cập, pháp lý hoặc môi trường chưa sẵn | Xác định đầu mối, điều kiện, mốc quyết định và phương án thay thế |
| **Phát hành/vận hành** | Chưa rõ giám sát, rollback, phân quyền hoặc quy trình xử lý sự cố | Làm rõ DoD, diễn tập trong môi trường phù hợp, kiểm tra triển khai |

### 10.2. Khi nào nên làm spike?

Spike hữu ích khi một câu hỏi **không thể trả lời hợp lý bằng trao đổi hoặc đọc tài liệu sẵn có**, và câu trả lời ảnh hưởng lớn đến lựa chọn hoặc ước lượng.

Ví dụ:

> Trong một khoảng thời gian cố định, thử kết nối API thanh toán sandbox để xác định các trạng thái callback, tính idempotency và giới hạn môi trường. Kết quả cần có: thử nghiệm được ghi lại, danh sách giới hạn, rủi ro và đề xuất lát cắt triển khai.

Kết quả có thể là **“chưa đủ dữ liệu”** nếu môi trường thử không đại diện. Điều đó vẫn hữu ích nếu nhóm biết mình thiếu gì và cần tiếp tục ra quyết định thế nào.

Đừng biến mọi item mơ hồ thành spike riêng. Nhiều điều chưa rõ có thể được giải quyết nhanh bằng cách hỏi đúng người hoặc quan sát một luồng người dùng.

### 10.3. Không dùng chia nhỏ để che giấu phụ thuộc

Giả sử màn hình “Đã thanh toán” cần tín hiệu xác nhận từ cổng thanh toán. Một ticket frontend có thể hoàn tất hiển thị trạng thái giả, nhưng nếu Product Owner hoặc nhóm gọi đó là năng lực thanh toán hoàn tất, báo cáo sẽ sai.

Có thể làm một prototype nhằm thử giao diện; cần đánh dấu nó là **bằng chứng về cách hiển thị**, chưa phải Increment thanh toán đầy đủ. Nếu mục tiêu Sprint là giao luồng thanh toán chạy được, phải đảm bảo nguồn xác nhận giao dịch và các kiểm soát cần thiết đã tích hợp.

## 11. Tiêu chí để cân nhắc một hạng mục trước khi chọn

Không có “checklist Ready” chính thức áp dụng mọi đội Agile. Dưới đây là **những câu hỏi hỗ trợ trao đổi**, không phải cổng phê duyệt bắt buộc.

| Nhóm câu hỏi | Cách tự kiểm tra |
|---|---|
| Giá trị | Hạng mục có liên hệ rõ với Product Goal, nhu cầu hoặc rủi ro ưu tiên? |
| Người dùng và bối cảnh | Biết ai sử dụng, trong điều kiện nào, kết quả mong muốn là gì? |
| Phạm vi | Biết phần nào được bao gồm, phần nào để sau, và ranh giới đó có hợp lý? |
| Hành vi | Có ví dụ/AC đủ để những người liên quan hiểu điều đúng và sai? |
| Chất lượng | Có thể thực hiện theo DoD và tiêu chuẩn an toàn, bảo mật, khả năng truy cập áp dụng? |
| Phụ thuộc | Những phụ thuộc có nguy cơ chặn việc đã được nhận diện và có cách xử lý? |
| Độ lớn | Developers có thể đánh giá hợp lý và dự kiến hoàn tất trong khoảng lựa chọn? |
| Kiểm chứng | Có cách kiểm tra Increment và lấy phản hồi thích hợp? |
| Quyền quyết định | Biết ai làm rõ nghiệp vụ, ai sắp thứ tự ưu tiên, ai quyết phương án kỹ thuật? |
| Công việc đang mở | Chọn việc mới có làm xấu WIP và kéo dài công việc gần hoàn tất không? |

Nếu thiếu thông tin, đội có thể **làm rõ thêm, chia nhỏ hơn, chọn một thử nghiệm hoặc thay đổi thứ tự**. Không nên ép mọi item phải đủ tất cả mô tả trước khi thảo luận, và cũng không nên kéo item lớn mơ hồ vào thực hiện vì “đã đến lượt”.

### 11.1. Một thỏa thuận làm việc gọn

~~~text
TRUOC KHI CHON:
  - Hieu nguoi dung va gia tri du kien.
  - Co pham vi nhat quan va vi du hanh vi quan trong.
  - Biet rui ro, phu thuoc, quyet dinh con mo.
  - Developers danh gia co the hoan tat lat cat theo DoD.
  - Co cach kiem chung va nhan phan hoi.

NEU CHUA DU:
  - Lam ro / chia nho / kiem tra bat dinh / doi thu tu.

TRONG KHI LAM:
  - Minh bach dieu moi hoc duoc.
  - Dieu chinh ke hoach va pham vi theo quyen han.
  - Khong tu y ha Definition of Done.
~~~

Đây chỉ là mẫu chính sách của nhóm. Scrum không quy định một Definition of Ready bắt buộc; mọi thỏa thuận nên được xem lại nếu nó trở thành trở ngại hơn là giúp tăng khả năng hoàn tất.

## 12. Ưu tiên hạng mục đã làm rõ theo giá trị, rủi ro và khả năng hoàn tất

Làm rõ là điều kiện giúp lựa chọn tốt hơn, **không phải cách tự động quyết định ưu tiên**. Sau khi hiểu các lựa chọn, Product Owner và các bên liên quan cần cân nhắc các yếu tố cụ thể.

| Yếu tố | Câu hỏi | Ví dụ |
|---|---|---|
| Giá trị người dùng | Ai được lợi và mức độ trở ngại hiện tại ra sao? | Lỗi không đăng nhập được có ảnh hưởng nhiều học viên không? |
| Mục tiêu sản phẩm | Hạng mục góp phần vào mục tiêu hiện tại thế nào? | Cải thiện luồng kích hoạt tài khoản trước tính năng phụ |
| Mức cấp bách / chi phí chậm trễ | Nếu trì hoãn, hệ quả nào xảy ra? | Hạn tuân thủ, một sự cố đang ảnh hưởng người dùng |
| Giảm rủi ro / tạo thông tin | Hạng mục giúp kiểm tra giả thuyết lớn nào? | Tích hợp sandbox trước khi cam kết toàn bộ thanh toán |
| Độ lớn và cơ hội giao sớm | Có thể hoàn tất một lát cắt có giá trị với năng lực hiện tại không? | Một luồng ghi danh hoàn chỉnh thay vì hàng loạt phần UI |
| Phụ thuộc | Hạng mục có mở khóa công việc quan trọng khác không? | Quy tắc cấp quyền cần hoàn thiện trước cấp quyền tự động |
| Chất lượng và nghĩa vụ | Có lỗi hoặc yêu cầu bắt buộc phải xử lý không? | Vá lỗi phân quyền vượt trên tính năng trang trí |

Có thể dùng phương pháp như **MoSCoW**, so sánh giá trị/nỗ lực hoặc các mô hình chi phí chậm trễ nếu tổ chức thấy hữu ích. Các điểm số vẫn chứa giả định và dễ tạo độ chính xác giả; không nên xem chúng là công thức thay thế phán đoán và trách nhiệm ra quyết định.

### 12.1. Ví dụ một bảng quyết định đơn giản

| Hạng mục | Giá trị kỳ vọng | Bất định chính | Cách tiếp cận hợp lý |
|---|---|---|---|
| Sửa lỗi không cấp được quyền sau thanh toán | Rất cao, ảnh hưởng năng lực sử dụng cốt lõi | Nguyên nhân tích hợp | Ưu tiên điều tra và sửa theo mức độ nghiêm trọng |
| Ghi danh khóa miễn phí end-to-end | Cao nếu có đủ đối tượng sử dụng | Thấp hoặc vừa khi phụ thuộc sẵn | Chọn lát cắt nhỏ để giao và nhận phản hồi |
| Thanh toán bằng nhà cung cấp mới | Cao nhưng rủi ro tích hợp lớn | API và điều kiện pháp lý | Làm rõ/phê duyệt và kiểm chứng rủi ro trước cam kết triển khai rộng |
| Đổi màu thẻ khóa học | Thấp hoặc chưa rõ | Có thể rất dễ | Giữ trong backlog, chưa cần chọn chỉ vì “dễ” |

**Bảng trên minh họa logic thảo luận**, không phải một thứ tự áp dụng cho mọi sản phẩm. Với sản phẩm chỉ bán khóa trả phí, mức ưu tiên có thể rất khác. Hãy quay về nhu cầu và ràng buộc của sản phẩm cụ thể.

## 13. Scrum và Kanban chọn hạng mục theo cách nào?

### 13.1. Trong Sprint Planning của Scrum

Sprint Planning giải quyết ba chủ đề:

1. **Vì sao Sprint có giá trị?** Product Owner đề xuất cách sản phẩm có thể tăng giá trị; Scrum Team cùng xác định Sprint Goal.
2. **Có thể hoàn tất những gì trong Sprint?** Qua trao đổi với Product Owner, Developers chọn các Product Backlog Items để đưa vào Sprint; khả năng lựa chọn dựa trên hiểu biết về năng lực, hiệu suất trước đây, DoD và thông tin hiện có.
3. **Làm công việc đã chọn bằng cách nào?** Developers lập kế hoạch tạo Increment đạt DoD; chi tiết kế hoạch có thể được điều chỉnh khi học thêm.

Backlog refinement giúp mục gần được lựa chọn có đủ thông tin cho cuộc trao đổi ấy; nó **không loại bỏ việc lập kế hoạch và thương lượng trong Sprint Planning**.

Nếu Developers phát hiện một item được đánh giá nhỏ nhưng thực ra quá lớn, họ có thể thương lượng lại phạm vi với Product Owner mà vẫn giữ Sprint Goal và chất lượng. **Sprint Goal là điểm tập trung**, không phải lời hứa phải hoàn tất bằng mọi giá tất cả chi tiết của kế hoạch ban đầu.

### 13.2. Trong Kanban, kéo việc theo chính sách và năng lực

Một nhóm phát triển bảo trì dịch vụ liên tục có thể không dùng Sprint. Họ định nghĩa rõ **dòng công việc**, chính sách kéo từ hàng chờ và giới hạn WIP.

Ví dụ:

~~~text
Yeu cau duoc ghi nhan
          |
          v
   Can lam ro / chia nho
          |
          v
   Du dieu kien can nhac
          |
      Chon theo muc tieu,
      rui ro, chinh sach
          |
          v
   Dang thuc hien  --(WIP gioi han)-->
          |
          v
   Kiem chung / dat chinh sach hoan tat
~~~

Nếu WIP đã đầy, việc hợp lý có thể là **giúp hoàn tất hoặc tháo điểm chặn** cho mục đang xử lý, dù hàng chờ có những yêu cầu đã rõ. Các thước đo như **work item age, cycle time, throughput và WIP** giúp phát hiện chờ đợi và cải thiện khả năng dự báo.

Thời gian hoàn tất nhanh hơn không tự chứng minh người dùng nhận nhiều giá trị hơn. Đội vẫn cần gắn chính sách kéo việc với mục tiêu dịch vụ, mức chất lượng và phản hồi thực tế.

### 13.3. XP giúp lát cắt nhỏ có thể hoàn tất an toàn

Một backlog được chia tốt vẫn dễ mắc kẹt nếu tích hợp mất nhiều tuần hoặc kiểm thử hồi quy quá chậm. Các thực hành kỹ thuật gắn với XP như **tích hợp liên tục, kiểm thử có mục đích, TDD khi phù hợp, refactoring, lập trình cặp khi cần và phát hành nhỏ** giúp giảm chi phí tạo Increment.

Ví dụ, một lát cắt tính giá sau giảm giá cần unit test cho quy tắc, integration test cho dữ liệu/đơn và kiểm tra tình huống giao dịch phù hợp. Nếu mỗi lát cắt gây lỗi cho phần trước, nhóm không thực sự đang giao tăng dần bền vững.

## 14. Đo xem refinement và splitting có giúp giao hàng tốt hơn không

Không nên đánh giá refinement chỉ bằng **số giờ họp**, **số user story mới** hoặc **tỷ lệ ticket có đầy đủ trường dữ liệu**. Mục đích là giúp nhóm chọn công việc sáng suốt hơn và hoàn tất dòng giá trị với ít chờ đợi, ít làm lại.

| Tín hiệu | Có thể cho biết điều gì? | Giới hạn cần nhớ |
|---|---|---|
| **Work item age** | Item đang xử lý nào tồn tại quá lâu cần hỗ trợ hoặc chia lại? | Phải phân biệt loại công việc và thời điểm bắt đầu |
| **Cycle time** | Sau khi bắt đầu, việc mất bao lâu để đạt trạng thái hoàn tất? | Một item nhỏ không nhất thiết có giá trị tương đương item khác |
| **WIP** | Có đang bắt đầu quá nhiều việc mà không hoàn tất? | WIP thấp không tự chứng minh chất lượng hoặc giá trị |
| **Throughput** | Có bao nhiêu item hoàn tất trong một khoảng thời gian? | Chia ticket giả tạo có thể tăng throughput mà không tăng giá trị |
| **Công việc bị chặn** | Phụ thuộc nào thường không được làm rõ trước khi chọn? | Cần tìm nguyên nhân, không thưởng/phạt theo số điểm chặn |
| **Làm lại vì hiểu sai yêu cầu** | AC, ví dụ nghiệp vụ hoặc trao đổi trước khi làm có đủ rõ không? | Không phải mọi thay đổi do học thêm đều là lãng phí |
| **Increment đạt DoD** | Những khả năng sản phẩm nào đã thực sự hoàn tất? | Cần thêm phản hồi người dùng để đánh giá giá trị |
| **Thời gian đến phản hồi hữu ích** | Có nhận được thông tin để điều chỉnh ưu tiên sớm hơn không? | Phản hồi phải đủ đáng tin và liên quan tới mục tiêu |

Ví dụ, nếu các hạng mục liên tục đọng ở cột “Kiểm thử tích hợp”, đội có thể cần chia theo luồng đầu-cuối sớm hơn hoặc đầu tư môi trường kiểm tra. Nếu nhiều item bị chặn vì thiếu quyết định nghiệp vụ, đội có thể mời người hiểu nghiệp vụ tham gia refinement sớm hơn.

**Không biến “story càng nhỏ càng tốt” thành mục tiêu.** Khi chỉ số đếm item được thưởng, đội có thể chia thành hàng chục việc không độc lập. Điều cần đánh giá là tốc độ và độ tin cậy của những **khả năng có ý nghĩa** đã hoàn tất.

## 15. Những sai lầm phổ biến và cách xử lý

### Sai lầm 1: Chọn theo độ dễ thay vì giá trị

Một item đổi màu nút rất rõ, trong khi lỗi phân quyền phức tạp. Đội chọn item dễ để có nhiều ticket Done.

**Cách xử lý:** Xem Product Goal, mức độ tác động người dùng, rủi ro và nghĩa vụ trước. Sự rõ ràng và nhỏ gọn giúp thực thi, nhưng không tự quyết định thứ tự.

### Sai lầm 2: Gọi một epic là user story chỉ vì viết đúng mẫu

“Là khách hàng, tôi muốn quản lý mọi giao dịch để hoàn tất hành trình mua hàng” vẫn có thể bao gồm hàng chục quy tắc và hệ thống.

**Cách xử lý:** Xác định hành vi và nhóm trường hợp cụ thể; phân theo những lát cắt có thể kiểm chứng.

### Sai lầm 3: Chia thành frontend, backend, database rồi gọi đó là các story độc lập

Các nhiệm vụ kỹ thuật cần thiết nhưng có thể không đem lại năng lực người dùng riêng khi hoàn tất.

**Cách xử lý:** Sử dụng nhiệm vụ kỹ thuật bên trong một lát cắt chức năng; bảo đảm Increment cuối cùng tích hợp được.

### Sai lầm 4: Đẩy toàn bộ trường hợp lỗi sang Sprint sau

Lát cắt đầu “hoàn thành” nhưng cấp quyền học sai hoặc xử lý trùng giao dịch.

**Cách xử lý:** Đưa các trường hợp lỗi và kiểm soát bắt buộc vào lát cắt hiện tại; chỉ trì hoãn những biến thể không cần thiết trong phạm vi công bố.

### Sai lầm 5: Ép ước lượng khi chưa có thông tin

Đội bị yêu cầu đưa một con số chính xác cho tích hợp chưa từng thử và chưa biết API của đối tác.

**Cách xử lý:** Nêu rõ bất định, làm rõ phụ thuộc hoặc chạy thử có thời hạn trước khi dự báo.

### Sai lầm 6: Dùng Definition of Ready làm cổng quan liêu

Item cần ký qua nhiều phòng ban dù người có chuyên môn đang có thể phối hợp và làm rõ trực tiếp.

**Cách xử lý:** Xem checklist như thỏa thuận hỗ trợ trao đổi; điều chỉnh chính sách theo rủi ro, quyền quyết định và hiệu quả thực tế. Scrum không yêu cầu Definition of Ready chính thức.

### Sai lầm 7: Quá nhiều refinement cho việc chưa chắc sẽ làm

Đội viết AC và test case chi tiết cho mọi tính năng trong lộ trình xa, rồi phải xóa khi ưu tiên thay đổi.

**Cách xử lý:** Refinement theo độ gần, rủi ro và mức độ bất định. Giữ hạng mục xa ở mức đủ định hướng.

### Sai lầm 8: Nhầm AC với DoD

Story đáp ứng yêu cầu nghiệp vụ nhưng chưa tích hợp, chưa kiểm tra bảo mật hoặc chưa đạt chuẩn chất lượng chung.

**Cách xử lý:** Giữ AC cho hành vi riêng, DoD cho chất lượng áp dụng toàn Increment; chỉ công nhận Done khi tiêu chuẩn liên quan được thỏa.

### Sai lầm 9: Coi việc “đã chia nhỏ” là đã giải quyết phụ thuộc

Một chuỗi ticket nhỏ vẫn có thể mắc kẹt vì tất cả chờ API của đối tác.

**Cách xử lý:** Nhìn đường đi từ yêu cầu đến Increment, xác định điểm chặn, người chịu trách nhiệm và bước kiểm chứng phụ thuộc.

### Sai lầm 10: Backlog refinement trở thành buổi giao task

Người quản lý chia việc đến từng người trước khi Developers cùng bàn cách tạo Increment.

**Cách xử lý:** Trong Scrum, giữ Product Owner chịu trách nhiệm ưu tiên, Developers chịu trách nhiệm độ lớn và kế hoạch thực hiện; refinement giúp hiểu sản phẩm và công việc, không thay cơ chế tự quản lý của Developers.

### Sai lầm 11: Không sửa backlog khi học được thông tin mới

Người dùng đã chỉ ra nhu cầu khác, nhưng đội vẫn thực hiện toàn bộ danh sách ban đầu chỉ vì nó đã được phân nhỏ.

**Cách xử lý:** Xem backlog là danh sách đang tiến hóa; điều chỉnh thứ tự, mô tả hoặc dừng hạng mục khi bằng chứng cho thấy hướng khác có giá trị hơn.

### Sai lầm 12: Dùng số lượng ticket làm mục tiêu năng suất

Đội chia công việc thành 40 ticket rất nhỏ để tăng số lượng Done, gây thêm chuyển giao và khó thấy luồng sử dụng hoàn chỉnh.

**Cách xử lý:** Nhìn Increment, thời gian đến phản hồi, chất lượng và giá trị đạt được; dùng chỉ số flow để cải tiến hệ thống, không để so năng suất cá nhân.

## 16. Quy trình thực hành trong một buổi refinement

Đây là một kịch bản **minh họa 50–60 phút** cho một hạng mục có khả năng được chọn sớm. Có thể khác theo độ phức tạp và cách làm việc của đội; Scrum không bắt buộc có đúng buổi họp hoặc thời lượng này.

| Thời lượng | Hoạt động | Kết quả cần có |
|---|---|---|
| 0–10 phút | Nhắc lại người dùng, vấn đề, mục tiêu và bằng chứng hiện có | Nhóm hiểu vì sao hạng mục đáng xem xét |
| 10–20 phút | Làm rõ quy tắc và ví dụ hành vi, các ngoại lệ thiết yếu | Các câu hỏi chưa rõ được phát hiện và ghi lại |
| 20–35 phút | Story mapping hoặc chia lát cắt theo giá trị/rủi ro | Một số phương án nhỏ, có phạm vi riêng |
| 35–45 phút | Xem AC, DoD, phụ thuộc, phương án kiểm chứng | Biết phần nào có thể hoàn tất và rủi ro còn lại |
| 45–55 phút | Developers đánh giá độ lớn; Product Owner thảo luận giá trị và thứ tự | Có cơ sở lựa chọn, không ép ước lượng giả |
| 55–60 phút | Ghi quyết định, người theo dõi câu hỏi và thời điểm xem lại | Backlog được cập nhật, biết bước tiếp theo |

Đừng để buổi refinement kết thúc chỉ với “cần thêm thông tin” mà không biết **thông tin gì, ai có thể cung cấp và khi nào cần để ra quyết định**.

### 16.1. Mẫu mô tả hạng mục sau khi được làm rõ

~~~text
ID / TEN:
NGUOI DUNG / VAN DE:
GIA TRI DU KIEN / LIEN HE MUC TIEU:

PHAM VI LAT CAT:
  Bao gom:
  Khong bao gom:

VI DU / TIEU CHI CHAP NHAN:
  AC-01:
  AC-02:
  AC-03:

CHAT LUONG / RANG BUOC:
  DoD ap dung:
  Bao mat / rieng tu / accessibility / hieu nang:

PHU THUOC:
  Da biet:
  Chua ro:
  Ai phu trach lam ro:

BANG CHUNG CAN CO:
  Test / moi truong / phan hoi:

DO LON / BAT DINH:
  Danh gia cua Developers:
  Rui ro va gia dinh:

QUYET DINH:
  Tiep tuc lam ro / chia nho / chon / de sau:
  Ly do:
  Moc xem lai:
~~~

Mẫu này không phải artifact bắt buộc của Scrum. Đội chỉ nên giữ những trường thực sự giúp giảm hiểu nhầm và hỗ trợ quyết định, ưu tiên dùng liên kết tới thông tin đã có trong công cụ thay vì sao chép trùng lặp.

## 17. Bài tập vận dụng

### Bài tập A — Phát hiện hạng mục chưa đủ rõ

Backlog có item: **“Cải thiện tìm kiếm khóa học, ưu tiên cao, 8 story point, làm trong Sprint tới.”**

Hãy nêu:

1. Ít nhất năm câu hỏi cần làm rõ trước khi Developers dự báo khả năng hoàn tất.
2. Một mục tiêu người dùng cụ thể hơn.
3. Hai lát cắt có thể kiểm chứng.
4. Một điều kiện chất lượng hoặc rủi ro không được bỏ qua.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi người dùng tìm loại khóa nào, khó khăn hiện tại là gì, tìm theo từ khóa hay bộ lọc, dữ liệu và quyền truy cập nào được phép hiển thị, định nghĩa kết quả liên quan ra sao, trường hợp không có kết quả xử lý thế nào, nguồn dữ liệu và độ trễ chấp nhận được. Mục tiêu có thể là “học viên tìm được khóa phù hợp với chủ đề cần học mà ít phải thử lại”. Hai lát cắt: tìm kiếm theo tên khóa học với dữ liệu thật; lọc kết quả theo một nhóm chủ đề có giá trị. Cần bảo đảm không hiển thị khóa riêng tư sai quyền; kiểm thử hành vi và chất lượng tích hợp. Đánh giá 8 điểm không đủ căn cứ nếu chưa hiểu phạm vi.

</details>

### Bài tập B — Chia ngang hay chia dọc?

Một nhóm đề xuất ba user story:

- “Xây frontend của thanh toán.”
- “Xây backend của thanh toán.”
- “Tạo bảng database thanh toán.”

**Yêu cầu:** Giải thích nhược điểm nếu coi đây là ba story độc lập. Đề xuất một lát cắt dọc nhỏ và ba tiêu chí chấp nhận quan trọng.

<details>
<summary>Gợi ý đáp án</summary>

Ba việc đều cần thiết nhưng không tự tạo luồng thanh toán có thể sử dụng. Một lát cắt dọc có thể là giao dịch thanh toán thử trong sandbox với một phương thức, lưu trạng thái đáng tin và hiển thị kết quả đúng. Tiêu chí: giao dịch thành công chỉ được đánh dấu sau xác nhận từ nguồn đáng tin; giao dịch thất bại/đang chờ không được cấp quyền học sai; thao tác hoặc callback lặp không tạo xử lý trùng; thông tin nhạy cảm được bảo vệ theo quy định. Phải nói rõ sandbox mới là kiểm chứng tích hợp, chưa chứng minh khả năng nhận giao dịch thực tế.

</details>

### Bài tập C — Ưu tiên cao nhưng chưa sẵn sàng

Một tính năng tích hợp đối tác có tác động kinh doanh lớn. Đội chưa có tài khoản sandbox, chưa biết cách đối tác gửi sự kiện và chưa rõ cơ chế xác nhận giao dịch. Stakeholder yêu cầu đưa toàn bộ tính năng vào Sprint vì “ưu tiên số một”.

**Yêu cầu:** Nêu hành động thay thế có trách nhiệm và các điều kiện để chọn lát cắt triển khai thực tế.

<details>
<summary>Gợi ý đáp án</summary>

Nhóm có thể ưu tiên làm rõ quyền truy cập, người liên hệ đối tác, yêu cầu bảo mật và spike có thời hạn kiểm tra API/callback. Product Owner vẫn giữ tính cấp bách ở backlog, nhưng Developers không cần giả định mọi bất định đã biến mất. Khi biết các trạng thái và giới hạn tích hợp, chia một luồng giao dịch có kiểm chứng với AC, DoD, phương án lỗi và rủi ro bắt buộc. Nếu ràng buộc pháp lý hoặc đối tác chưa đủ, nêu rõ dự báo và điều kiện phụ thuộc thay vì nhận một cam kết không có căn cứ.

</details>

### Bài tập D — Đọc trạng thái Done trong Kanban

Bảng công việc có tám mục “Đang xử lý”, ba mục “Chờ kiểm thử” và không có mục đạt Done tuần này. Trong khi đó, năm yêu cầu mới đã có AC rất rõ.

**Yêu cầu:** Bạn có kéo năm mục mới vào ngay không? Đề xuất hai thay đổi chính sách và hai chỉ số theo dõi.

<details>
<summary>Gợi ý đáp án</summary>

Không nên mặc định kéo cả năm khi WIP đang cao. Có thể ưu tiên hỗ trợ hoàn tất mục ở bước kiểm thử, đặt hoặc điều chỉnh giới hạn WIP phù hợp, hiển thị rõ mục bị chặn và lý do chờ, thống nhất tiêu chí chuyển sang Done. Theo dõi work item age, cycle time và WIP để đánh giá thay đổi. Nếu có sự cố nghiêm trọng cần xử lý ngay, dùng chính sách khẩn cấp rõ và xem ảnh hưởng tới các việc đang mở.

</details>

### Bài tập E — Viết lại AC chưa kiểm chứng được

Story: “Là học viên, tôi muốn nhận kết quả đăng ký nhanh và thân thiện.”

AC hiện tại: “Trang hiển thị đẹp, xử lý nhanh, không có lỗi.”

**Yêu cầu:** Viết lại ba AC có thể quan sát và nêu thông tin nào cần bổ sung trước khi đo hiệu năng.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ: khi đăng ký hợp lệ, người dùng thấy trạng thái ghi danh đúng và khóa xuất hiện trong danh sách học; khi khóa đóng đăng ký, hệ thống từ chối rõ và không tạo quyền học; khi dịch vụ bị lỗi, giao diện không báo thành công giả và có cách thử lại. Với hiệu năng, cần làm rõ ngưỡng, cách đo, mức tải, dữ liệu và môi trường trước khi xác nhận “nhanh”. “Đẹp” cần được thay bằng tiêu chí thiết kế/khả năng sử dụng hoặc kết quả đánh giá với người dùng phù hợp, tránh kết luận chủ quan.

</details>

### Bài tập F — Kết quả mới làm đổi thứ tự backlog

Đội đã refinement kỹ hạng mục “Video hướng dẫn đăng ký” nhưng chưa bắt đầu. Thử nghiệm với học viên cho thấy vấn đề lớn nhất là liên kết xác minh email hết hạn và không thể yêu cầu lại.

**Yêu cầu:** Có nên chọn video vì đã làm rõ xong không? Đề xuất lựa chọn tiếp theo và cách kiểm chứng.

<details>
<summary>Gợi ý đáp án</summary>

Không nên chọn chỉ vì đã tốn công refinement. Product Owner có thể đưa việc xử lý liên kết hết hạn lên trước theo tác động người dùng, xác định lát cắt cho phép yêu cầu liên kết mới an toàn, viết AC về trạng thái hết hạn, giới hạn yêu cầu lại và không lộ thông tin tài khoản. Developers kiểm tra khả năng hoàn tất theo DoD và phụ thuộc email. Sau khi phát hành, theo dõi tỷ lệ tự xác minh thành công và lỗi liên quan, đồng thời đánh giá liệu video còn cần thiết không.

</details>

## 18. Checklist tự đánh giá trước khi chọn thực hiện

Với một backlog item có khả năng được chọn sớm, nhóm có thể cùng trả lời:

1. Hạng mục phục vụ vấn đề hoặc mục tiêu sản phẩm nào, có bằng chứng ban đầu không?
2. Ai là người dùng hoặc người nhận giá trị? Họ cần hoàn thành việc gì?
3. Phạm vi của lát cắt đã rõ; các phần để sau có được ghi minh bạch không?
4. Có thể chia nhỏ hơn mà vẫn tạo hành vi đúng, an toàn và kiểm chứng được không?
5. Những trường hợp thành công, lỗi và ràng buộc quan trọng đã được thảo luận chưa?
6. Có tiêu chí chấp nhận quan sát được và cách thu bằng chứng kiểm chứng phù hợp không?
7. Đội hiểu ranh giới giữa AC riêng của item và Definition of Done chung không?
8. Có phụ thuộc kỹ thuật, dữ liệu, đối tác hoặc quyết định nào có thể làm việc bị chặn không?
9. Nếu rủi ro lớn, bước thử nghiệm hoặc spike nhỏ nhất có thể giảm bất định là gì?
10. Developers đã hiểu đủ để đánh giá độ lớn và khả năng hoàn tất không?
11. Hạng mục có đang được ưu tiên vì giá trị và rủi ro, hay chỉ vì dễ làm hoặc đã được mô tả chi tiết?
12. Nếu dùng Scrum, hạng mục đóng góp thế nào vào Sprint Goal có thể đề xuất?
13. Nếu dùng Kanban, chính sách kéo việc và giới hạn WIP hiện tại có cho phép bắt đầu không?
14. Khi Increment được kiểm tra, phản hồi nào có thể dẫn đến thay đổi Product Backlog?
15. Nếu chưa đủ rõ, có người và thời điểm cụ thể để làm rõ điều còn thiếu không?

Không nhất thiết cần câu trả lời hoàn hảo cho toàn bộ checklist trước mọi thay đổi nhỏ. Mục đích là **nhìn thấy sự thật về nhu cầu, phạm vi, khả năng hoàn tất và bất định**, để chọn công việc có trách nhiệm.

## 19. Ghi nhớ

- **Refinement là làm rõ và chia nhỏ liên tục**, tập trung vào những hạng mục có khả năng được chọn, theo mức bất định và rủi ro. Không cần đặc tả toàn bộ backlog từ đầu.
- **Ưu tiên, sẵn sàng và lựa chọn là ba quyết định khác nhau.** Một việc rất có giá trị có thể cần kiểm chứng rủi ro trước; một việc rất rõ chưa chắc đáng làm ngay.
- **Chia theo lát cắt dọc giúp tạo Increment hoạt động được.** Đừng đánh đồng các nhiệm vụ frontend, backend, database riêng lẻ với những khả năng người dùng đã hoàn tất.
- **Tiêu chí chấp nhận và DoD cần bổ sung cho nhau.** Lát cắt nhỏ vẫn phải đáp ứng hành vi đúng, tính toàn vẹn dữ liệu và chất lượng bắt buộc.
- **Độ lớn và ước lượng phải dựa trên hiểu biết thực tế.** Khi chưa biết rõ, hãy đặt câu hỏi, làm spike có thời hạn hoặc chia lại; tránh dự báo với độ chính xác giả.
- **Trong Scrum**, Product Owner chịu trách nhiệm thứ tự backlog, Developers xác định độ lớn và lựa chọn công việc phù hợp trong Sprint Planning; refinement không phải sự kiện bắt buộc hay cổng Definition of Ready chính thức.
- **Trong Kanban**, tiêu chí kéo việc, giới hạn WIP và chính sách hoàn tất giúp dòng công việc tiến đến giá trị; đừng kéo thêm việc chỉ vì backlog đã được làm rõ.
- **Giao phần nhỏ để học sớm.** Sau mỗi Increment, phản hồi mới có thể làm đội điều chỉnh thứ tự, mô tả hoặc phương án phát triển.

Trước khi chuyển một backlog item sang “Đang thực hiện”, hãy hỏi: **“Chúng ta hiểu rõ ai cần gì và vì sao chưa? Phần nhỏ nhất có thể hoàn tất đúng chuẩn là gì? Điều gì còn chưa biết? Bằng chứng nào sẽ giúp quyết định việc tiếp theo?”** Một hạng mục được làm rõ đúng mức giúp đội tránh tiến độ ảo và đưa giá trị tới người dùng sớm hơn.

## Tài liệu tham khảo định hướng

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Backlog refinement, trách nhiệm Product Owner và Developers, Sprint Planning, Sprint Goal và Definition of Done.
- [Manifesto for Agile Software Development — Principles](https://agilemanifesto.org/principles.html): giao phần mềm hoạt động được thường xuyên, phản hồi thay đổi và hợp tác.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): định nghĩa dòng công việc, WIP, chính sách và phép đo dòng công việc.
- [Agile Alliance — Glossary](https://agilealliance.org/agile101/agile-glossary/): thuật ngữ user story, backlog refinement, INVEST và những thực hành hỗ trợ.
