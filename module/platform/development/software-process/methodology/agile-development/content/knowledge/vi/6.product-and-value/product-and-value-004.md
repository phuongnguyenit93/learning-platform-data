# Kết hợp khám phá nhu cầu với phát triển giải pháp

## 1. Vấn đề: làm đúng giải pháp nhưng có thể vẫn sai nhu cầu

Một nhóm phát triển phần mềm có thể viết mã sạch, triển khai đều đặn, ít lỗi và hoàn thành tất cả user story đúng hạn nhưng vẫn không tạo ra kết quả đáng kể cho người sử dụng. Lý do có thể rất đơn giản: nhóm đã xây dựng một giải pháp tốt cho **vấn đề mà người dùng không thực sự gặp**, hoặc chỉ giải quyết một phần nhỏ của nhu cầu.

Ví dụ, nền tảng học trực tuyến nhận thấy nhiều học viên ngừng học giữa khóa. Một đề xuất nhanh là xây hệ thống huy hiệu, điểm thưởng và bảng xếp hạng. Nhưng nhóm chưa biết vì sao người học rời đi: họ bận, bài học quá dài, nội dung quá khó, không thấy tiến bộ, hay không tìm được phần tiếp theo? Nếu triển khai ngay toàn bộ hệ thống thưởng điểm, nhóm đang đặt cược nhiều thời gian phát triển vào một **giả định chưa được kiểm chứng**.

Trong Agile, việc **bàn giao sản phẩm tăng dần** giúp kiểm tra phần mềm có hoạt động và tạo ra giá trị hay không; **phản hồi sớm** giúp nhóm nhận ra điều nào cần làm khác; **cải tiến liên tục** giúp điều chỉnh cách khám phá, xây dựng và phối hợp. Để ba yếu tố này tạo thành một vòng học hỏi, cần kết hợp:

- **Khám phá sản phẩm (product discovery):** tìm hiểu người dùng, vấn đề, cơ hội và các phương án; giảm bất định trước khi quyết định đầu tư.
- **Phát triển và bàn giao giải pháp (product delivery):** xây dựng, kiểm thử, tích hợp, phát hành và vận hành khả năng sản phẩm đáp ứng tiêu chuẩn chất lượng.
- **Đánh giá giá trị sau bàn giao:** quan sát xem thay đổi có cải thiện kết quả thực tế không, rồi tiếp tục khám phá hoặc điều chỉnh backlog.

Hai hoạt động này **gắn chặt với nhau và có thể diễn ra song song**. Discovery không phải một giai đoạn kéo dài để “chốt toàn bộ yêu cầu” trước khi lập trình; delivery cũng không phải nơi chỉ thực hiện một bản đặc tả bất biến.

> Câu hỏi trung tâm: **Chúng ta có đang giải quyết đúng vấn đề bằng một giải pháp có thể sử dụng, vận hành và tạo tác động đo được không?**

## 2. Phân biệt khám phá, phát triển và kiểm chứng giá trị

| Khía cạnh | Khám phá nhu cầu và giải pháp | Phát triển và bàn giao | Kết nối giữa hai hoạt động |
| --- | --- | --- | --- |
| **Câu hỏi chính** | Ai đang gặp vấn đề? Vì sao? Cách nào đáng thử? | Làm thế nào để khả năng đó vận hành đúng, an toàn và ổn định? | Điều chúng ta bàn giao có giải quyết đúng vấn đề không? |
| **Bằng chứng** | Phỏng vấn, quan sát, dữ liệu hành vi, thử nghiệm ý tưởng, kiểm tra giả định | Test, mã nguồn tích hợp, hiệu năng, bảo mật, phản hồi vận hành | Dữ liệu sử dụng thật, kết quả kinh doanh, phản hồi định tính |
| **Đầu ra thường gặp** | Hiểu biết mới, giả thuyết, lựa chọn được ưu tiên, rủi ro được làm rõ | Increment đạt Definition of Done, bản phát hành phù hợp, hệ thống có thể vận hành | Quyết định tiếp tục, điều chỉnh, mở rộng hoặc dừng |
| **Rủi ro trọng tâm** | Làm sản phẩm người dùng không cần hoặc không thể dùng | Giải pháp lỗi, khó bảo trì, mất an toàn hoặc không triển khai được | Đánh đồng số lượng chức năng với giá trị |
| **Đơn vị công việc** | Câu hỏi, cơ hội, giả thuyết, thí nghiệm | User story, task, increment, release | Kết quả người dùng và bài học dùng để sắp xếp backlog |

**Discovery không chỉ là nghiên cứu UX.** Nó còn cần hiểu tính khả thi kỹ thuật, vận hành, mô hình kinh doanh, dữ liệu, pháp lý và độ rủi ro. **Delivery không chỉ là lập trình.** Nó gồm thiết kế chi tiết, kiểm thử, bảo vệ dữ liệu, triển khai, quan sát hệ thống, hướng dẫn sử dụng và hỗ trợ vận hành.

Một bản prototype có thể giúp đánh giá người dùng có hiểu một luồng tương tác không; nó chưa chứng minh hệ thống có thể xử lý giao dịch thật. Một increment đã chạy trên môi trường sản xuất chứng minh thêm về năng lực delivery; nó vẫn chưa tự chứng minh tính năng làm tăng giá trị. Vì vậy, mỗi loại bằng chứng phải được diễn giải đúng câu hỏi mà nó có thể trả lời.

### Phân biệt đầu ra và kết quả

- **Output (đầu ra):** số màn hình, endpoint, story hoàn tất, phiên bản phát hành hoặc tính năng đã có.
- **Outcome (kết quả đối với người dùng):** học viên tìm được khóa phù hợp nhanh hơn, đăng ký thành công, hoàn thành bài học, giảm thời gian chờ hỗ trợ.
- **Impact (tác động dài hơn):** giữ chân học viên tốt hơn, giảm chi phí hỗ trợ, tăng hiệu quả kinh doanh hoặc cải thiện chất lượng học tập.

Một output có thể là điều kiện cần để tạo outcome, nhưng giữa chúng còn có hành vi người dùng và những yếu tố khác. Nhóm nên theo dõi cả chất lượng bàn giao lẫn kết quả sử dụng, tránh kết luận “đã làm xong tính năng” đồng nghĩa “đã giải quyết được nhu cầu”.

## 3. Bốn loại rủi ro cần xem xét khi chọn giải pháp

Trước khi cam kết phát triển một giải pháp lớn, nhóm nên kiểm tra ít nhất bốn câu hỏi:

1. **Giá trị / tính mong muốn (value risk):** Người dùng có nhu cầu đủ quan trọng và có chọn dùng giải pháp không?
2. **Khả năng sử dụng (usability risk):** Người dùng có hiểu và thực hiện được hành vi mong muốn trong bối cảnh thật không?
3. **Tính khả thi kỹ thuật (feasibility risk):** Nhóm có thể xây dựng, tích hợp, vận hành giải pháp trong những ràng buộc hiện có không?
4. **Tính khả thi kinh doanh / tổ chức (viability risk):** Giải pháp có phù hợp với mục tiêu, chi phí, pháp lý, chính sách và hoạt động của tổ chức không?

| Phương án ví dụ cho nền tảng học | Điều chưa chắc chắn | Phép kiểm tra ban đầu |
| --- | --- | --- |
| Gửi nhắc học mỗi tối | Học viên có muốn nhận nhắc, có thấy phiền không? | Phỏng vấn và thử opt-in với nhóm nhỏ |
| Cho học viên chọn lộ trình ngắn | Liệu người học có hiểu lộ trình và bắt đầu theo được không? | Prototype tương tác và quan sát tác vụ |
| Tự động đánh giá bài bằng AI | Kết quả có đáng tin, bảo vệ dữ liệu và đáp ứng mức chi phí không? | Spike kỹ thuật, đánh giá chất lượng trên bộ dữ liệu phù hợp, xem ràng buộc |
| Tích hợp thanh toán mới | Có đáp ứng đối soát, hoàn tiền và nghĩa vụ của tổ chức không? | Trao đổi với tài chính/vận hành và thử nghiệm tích hợp có kiểm soát |

Khả năng phát triển nhanh không phải lý do đủ để chọn một chức năng. Ngược lại, một nhu cầu người dùng rõ ràng cũng không xóa được các rủi ro bảo mật hoặc tính khả thi. Bốn góc nhìn này cần được đánh giá **trước và trong** quá trình phát triển; khi xuất hiện bằng chứng mới, mức ưu tiên có thể thay đổi.

## 4. Hai vòng lặp liên kết trong cùng một sản phẩm

Mô hình **dual-track Agile** thường được dùng để diễn tả discovery và delivery diễn ra liên tục. “Hai luồng” không có nghĩa là chia thành đội phân tích và đội lập trình biệt lập, hay chuyển giao đặc tả một chiều. Những người hiểu sản phẩm, thiết kế, kỹ thuật, kiểm thử và vận hành cần chia sẻ bối cảnh và cùng chịu trách nhiệm về kết quả.

~~~mermaid
flowchart LR
    O["Mục tiêu và cơ hội sản phẩm"] --> H["Discovery: quan sát và nêu giả thuyết"]
    H --> E["Kiểm tra ý tưởng / giả định rủi ro"]
    E --> P["Ưu tiên lựa chọn có bằng chứng"]
    P --> D["Delivery: xây lát giá trị, test, tích hợp"]
    D --> R["Phát hành phù hợp và quan sát"]
    R --> L["Đo outcome, thu phản hồi và học"]
    L --> O
    L -. "Phát hiện vấn đề mới" .-> H
    D -. "Giới hạn kỹ thuật mới" .-> E
~~~

Vòng discovery tạo ra **quyết định nên làm gì và vì sao**. Vòng delivery tạo ra **phần mềm dùng được và bằng chứng từ sử dụng thực tế**. Việc giải bài toán kỹ thuật trong delivery cũng có thể làm phát sinh câu hỏi discovery mới, ví dụ một ý tưởng tốt nhưng chi phí đồng bộ dữ liệu quá lớn; nhóm sẽ xem lại phương án thay vì chỉ cố thực hiện đến cùng.

### Discovery liên tục có nghĩa là gì?

Discovery liên tục không có nghĩa ngày nào cũng phải phỏng vấn hay chạy A/B test. Nó có nghĩa nhóm duy trì khả năng **hỏi, quan sát và sửa giả định** theo nhịp phù hợp với rủi ro và tốc độ thay đổi của sản phẩm. Có tuần cần nghiên cứu sâu vấn đề; có tuần quan sát bản phát hành; có tuần tập trung xử lý các câu hỏi kỹ thuật.

Một nhóm nhỏ có thể dùng những buổi trao đổi người dùng ngắn, định kỳ xem dữ liệu và refinement backlog. Nhóm lớn có thể cần thêm quy trình tuyển mẫu và nghiên cứu. Hình thức khác nhau, nhưng sản phẩm vẫn cần một nguồn thông tin phản hồi đáng tin cậy.

## 5. Quy trình kết hợp discovery và delivery trong bảy bước

### Bước 1 – Thống nhất mục tiêu sản phẩm và người hưởng lợi

Bắt đầu bằng **vấn đề và kết quả**, tránh bắt đầu từ danh sách tính năng.

**Yêu cầu theo giải pháp:** “Thêm bảng xếp hạng để học viên chăm học hơn.”

**Mục tiêu theo kết quả:** “Giúp học viên mới quay lại và hoàn thành bài học thứ hai trong vòng bảy ngày sau bài đầu, mà không tạo áp lực hoặc hành vi học đối phó.”

Mục tiêu có thể có định lượng nếu đã có nền dữ liệu; nếu chưa, nhóm nêu hướng thay đổi mong muốn và xác định cách đo. Cần phân biệt người yêu cầu chức năng với người trực tiếp sử dụng, người vận hành và những người chịu tác động gián tiếp.

### Bước 2 – Lập bản đồ vấn đề và cơ hội

Tập hợp dữ liệu hiện có, phỏng vấn hoặc quan sát hành vi để tìm điểm cản trở. Ví dụ, với hành trình học:

~~~text
Nhận biết khóa → Xem chi tiết → Đăng ký → Bắt đầu học → Quay lại → Hoàn thành
                  ↑                  ↑            ↑
            Chưa hiểu lợi ích    Bài đầu khó   Không biết học tiếp ở đâu
~~~

Mỗi điểm cản trở là **cơ hội để tìm hiểu**, chưa phải kết luận về giải pháp. Một nhóm có thể dùng opportunity solution tree: bắt đầu từ outcome mong muốn, phân nhánh thành cơ hội/nhu cầu đã quan sát, rồi đến các giải pháp ứng viên và thí nghiệm để kiểm tra.

Ví dụ đơn giản:

~~~mermaid
flowchart TD
    A["Outcome: Tăng tỷ lệ học viên quay lại bài thứ hai"] --> B["Cơ hội: Không biết bước học tiếp"]
    A --> C["Cơ hội: Khó sắp xếp thời gian"]
    B --> D["Ý tưởng: Nút Tiếp tục học rõ hơn"]
    B --> E["Ý tưởng: Trang lộ trình cá nhân"]
    C --> F["Ý tưởng: Nhắc học tự chọn"]
    D --> G["Kiểm tra: quan sát thao tác + thử lát nhỏ"]
    F --> H["Kiểm tra: khảo sát nhu cầu + opt-in giới hạn"]
~~~

Sơ đồ giúp giữ nhiều phương án khả thi cho một vấn đề. Đừng chọn một phương án chỉ vì nhóm đã có thư viện hoặc bản thiết kế sẵn.

### Bước 3 – Nêu giả thuyết có thể bác bỏ và ưu tiên bất định

Một giả thuyết hữu ích cần chỉ ra **ai**, **thay đổi gì**, **kết quả kỳ vọng** và **bằng chứng nào có thể khiến nhóm đổi ý**.

> “Với học viên đã học xong bài đầu nhưng chưa mở bài hai, nếu trang khóa học hiển thị rõ nút ‘Tiếp tục bài tiếp theo’, tỷ lệ mở bài thứ hai trong bảy ngày có thể tăng, vì người học giảm thời gian tìm kiếm.”

Giả thuyết này có thể sai. Người học có thể biết nút ở đâu nhưng không có thời gian, nội dung quá khó hoặc không thấy lý do tiếp tục. Vì vậy, nhóm nên ghi lại các giả định phụ và chọn giả định **quan trọng nhất, còn ít bằng chứng nhất** để kiểm tra trước.

Một bảng giả định nhỏ có thể dùng như sau:

| Giả định | Tác động nếu sai | Mức hiểu biết hiện tại | Bước kiểm tra |
| --- | --- | --- | --- |
| Người học muốn tiếp tục nhưng không tìm thấy bài kế | Cao | Thấp | Quan sát một số phiên học, phỏng vấn đúng nhóm bỏ dở |
| Hệ thống lưu tiến độ đủ chính xác | Cao | Trung bình | Kiểm tra dữ liệu thật và trường hợp đăng nhập nhiều thiết bị |
| Hiển thị nút mới có thể triển khai nhanh | Trung bình | Khá rõ | Spike nhỏ nếu còn bất định tích hợp |
| Thay đổi giao diện không làm lộ dữ liệu học tập | Cao | Cần xác nhận | Kiểm tra quyền truy cập và bảo vệ thông tin |

Không nhất thiết chấm điểm chính xác đến hàng thập phân. Mục đích là giúp mọi người hiểu **vì sao kiểm tra điều này trước**.

### Bước 4 – Chọn phương pháp học rẻ và đủ tin cậy

Chọn cách kiểm tra theo câu hỏi, rủi ro và bằng chứng hiện có:

| Muốn biết | Cách kiểm tra phù hợp | Điều kết quả chưa chứng minh |
| --- | --- | --- |
| Người dùng có gặp vấn đề này thật không? | Phỏng vấn về trải nghiệm đã xảy ra, quan sát hành vi, xem ticket hỗ trợ | Chưa chứng minh mọi người dùng đều gặp |
| Người dùng có hiểu cách giải quyết đề xuất không? | Prototype và giao tác vụ cụ thể, quan sát họ thao tác | Chưa chứng minh kỹ thuật vận hành hoàn chỉnh |
| Một lựa chọn có thể xây bằng nền tảng hiện tại không? | Spike kỹ thuật có mục tiêu và thời gian giới hạn, thử tích hợp | Chưa chứng minh người dùng mong muốn |
| Một thay đổi nhỏ có cải thiện hành vi không? | Release giới hạn, theo dõi trước/sau; A/B test nếu phân nhóm và cỡ mẫu phù hợp | So sánh trước/sau đơn thuần chưa chứng minh quan hệ nhân quả |
| Hiệu quả có bền vững không? | Theo dõi nhiều đợt sử dụng và nhóm người dùng | Chưa bảo đảm hiệu quả trong mọi bối cảnh tương lai |

**Đặt thời hạn học tập phù hợp.** Nếu một phép thử kéo dài và tốn gần bằng triển khai sản phẩm đầy đủ, cần hỏi liệu có cách nhỏ hơn để loại bỏ giả định rủi ro không. Tuy nhiên, quyết định về dữ liệu cá nhân, tiền bạc, an toàn hoặc nghĩa vụ pháp lý phải có mức thẩm định tương xứng; “thử nhanh” không miễn trừ những kiểm soát bắt buộc.

### Bước 5 – Chuyển phát hiện thành user story và backlog

Khi đã có tín hiệu đủ để chọn hướng, Product Owner hoặc người chịu trách nhiệm sản phẩm đưa lựa chọn vào Product Backlog theo thứ tự ưu tiên. Một user story nên nói rõ nhu cầu và giá trị:

> Là học viên đã hoàn thành bài đầu, tôi muốn mở ngay bài tiếp theo từ trang khóa học để có thể tiếp tục học mà không phải tìm lại vị trí đang dở.

Story cần được trao đổi cùng người hiểu nghiệp vụ, thiết kế, kỹ thuật và kiểm thử; mô tả ngắn không thay thế tiêu chí chấp nhận. Một số tiêu chí minh họa:

~~~gherkin
Feature: Tiếp tục học từ vị trí hiện tại

  Scenario: Học viên có bài tiếp theo
    Given học viên đã đăng nhập và có quyền học khóa này
    And bài đầu đã được ghi nhận hoàn tất
    When học viên mở trang khóa học
    Then hệ thống hiển thị hành động "Tiếp tục học"
    And khi chọn hành động, học viên được mở đúng bài tiếp theo

  Scenario: Học viên chưa có quyền truy cập
    Given người dùng không có quyền học khóa này
    When người dùng thử mở liên kết trực tiếp đến bài học
    Then hệ thống không cấp quyền truy cập nội dung bị hạn chế
~~~

Story trên là một **lát dọc** nếu hoàn tất hành trình thật từ hiển thị, xác định tiến độ, kiểm tra quyền và điều hướng. Task “thiết kế nút”, “viết API tiến độ”, “thêm cột dữ liệu” có thể nằm bên trong story; riêng từng task chưa đủ chứng minh giá trị.

Backlog nên là **danh sách lựa chọn cần được cập nhật theo điều đã học**, không phải hợp đồng phải xây mọi ý tưởng được nêu từ đầu. Những giả thuyết bị bác bỏ có thể được loại khỏi backlog hoặc giữ trong nhật ký học hỏi, tránh xuất hiện lại như nhu cầu đã được xác nhận.

### Bước 6 – Phát triển, kiểm thử và bàn giao increment

Discovery giảm rủi ro chọn sai giải pháp; delivery giải quyết rủi ro xây sai và vận hành không an toàn. Nhóm cần một **Definition of Done** phù hợp: mã được review, kiểm thử hành vi và trường hợp biên, tích hợp được, đáp ứng bảo mật/trợ năng/hiệu năng liên quan, có thể triển khai và quan sát lỗi.

Các thực hành XP như kiểm thử tự động, tích hợp liên tục, pair programming khi phù hợp và refactoring hỗ trợ khả năng bàn giao thay đổi nhỏ mà vẫn giữ chất lượng. Một nhóm sử dụng Scrum có thể hoàn thành increment qua Sprint; nhóm Kanban có thể hoàn thành và phát hành theo dòng công việc liên tục. Không framework nào yêu cầu đợi đến khi tất cả ý tưởng discovery thành tài liệu hoàn chỉnh.

**Hoàn thành increment**, **triển khai** và **bật cho người dùng** là ba quyết định liên quan nhưng khác nhau. Nhóm có thể tích hợp mã thường xuyên, phát hành có kiểm soát bằng feature flag và mở dần để quan sát. Cần xem xét cách rollback, thay đổi dữ liệu, tính tương thích và quyền truy cập; tắt cờ không tự động đảo ngược dữ liệu đã ghi hay thông báo đã gửi.

### Bước 7 – Kiểm chứng giá trị và quyết định bước tiếp theo

Khi người dùng thật đã trải nghiệm, nhóm kiểm tra:

1. Người dùng **có thực sự sử dụng** khả năng mới không?
2. Họ có **đạt kết quả cần thiết** không?
3. Có tác động ngoài ý muốn về lỗi, tốc độ, trợ năng, bảo mật hoặc trải nghiệm nhóm khác không?
4. Bằng chứng đã đủ để mở rộng, điều chỉnh, tiếp tục nghiên cứu hay dừng?

Quyết định phải quay lại backlog và cách thực hiện. Nếu nút “Tiếp tục học” được nhấn nhiều nhưng số người hoàn thành bài hai không tăng, vấn đề có thể nằm ở nội dung bài hoặc thời lượng, nên cần khám phá thêm thay vì chỉ thay màu nút.

## 6. Ví dụ xuyên suốt: từ “thêm huy hiệu” đến “giúp người học tiếp tục”

### 6.1. Bài toán ban đầu

Nhóm giả định một sản phẩm học trực tuyến có **1.000 học viên mới hoàn thành bài đầu** trong một tuần, nhưng chỉ **320 học viên mở bài thứ hai trong bảy ngày**. Tỷ lệ quay lại theo định nghĩa này là 32%. Đây là **số liệu giả định để minh họa**, không phải kết quả khảo sát thực tế.

Một stakeholder đề xuất xây hệ thống huy hiệu vì cho rằng học viên thiếu động lực. Product Owner đặt lại câu hỏi: “Vì sao học viên ngừng học, và kết quả nào quan trọng đối với họ?”. Nhóm xem dữ liệu, phỏng vấn một số người hoàn thành và chưa quay lại, đồng thời quan sát thao tác trên trang khóa học.

### 6.2. Những phát hiện và giới hạn

Nhóm ghi nhận ba tín hiệu ban đầu:

- Một số học viên không nhận ra nút dẫn đến bài tiếp theo vì nó nằm dưới danh sách tài nguyên dài.
- Một số học viên hiểu cách điều hướng nhưng thấy bài thứ hai quá dài để bắt đầu.
- Những người khác không quay lại vì bận, dù trải nghiệm giao diện không có vấn đề.

Đây là **những giả thuyết xuất phát từ quan sát**, chưa đủ để kết luận nguyên nhân phổ biến nhất trong toàn bộ tệp người dùng. Nhóm cần kiểm tra mẫu nghiên cứu có đại diện cho người học trên thiết bị di động, người mới, người học ở tốc độ khác nhau và những người đã bỏ dở hay không.

### 6.3. Các lựa chọn thay thế

| Phương án | Vấn đề dự kiến giải quyết | Cách kiểm chứng trước khi đầu tư nhiều |
| --- | --- | --- |
| Đưa nút “Tiếp tục học” lên vị trí dễ thấy | Khó tìm bài tiếp theo | Quan sát người dùng làm tác vụ; thử một lát nhỏ |
| Chia bài dài thành các phần ngắn | Người học khó bắt đầu vì ít thời gian | Phỏng vấn, thử một bài được chia phần và xem tỷ lệ học tiếp |
| Nhắc học tự chọn | Người học muốn quay lại nhưng quên | Kiểm tra mong muốn nhận nhắc và thử opt-in giới hạn |
| Huy hiệu và điểm thưởng | Người học cần động lực bên ngoài | Kiểm chứng giả thuyết động lực và rủi ro học đối phó trước khi xây lớn |

Nhóm chọn kiểm tra **khả năng tìm bài tiếp theo** trước vì quan sát ban đầu chỉ ra điểm nghẽn cụ thể và có thể kiểm chứng bằng bước tương đối nhỏ. Điều này không chứng minh các phương án khác vô giá trị; chúng vẫn là ứng viên để xem lại khi có bằng chứng mới.

### 6.4. Từ kiểm tra ý tưởng đến increment có thể sử dụng

**Discovery:** Nhóm cho người học thử prototype vị trí nút mới bằng một tác vụ: “Hãy mở bài tiếp theo sau khi bạn vừa học xong bài đầu”. Họ quan sát liệu người dùng tìm được thao tác và có hiểu nhãn hay không. Một prototype thành công chỉ là tín hiệu về khả năng sử dụng.

**Delivery:** Nhóm tạo story triển khai nút thật, lấy tiến độ và quyền học từ hệ thống, điều hướng đúng bài, xử lý trường hợp không còn bài tiếp theo, kiểm thử và theo dõi lỗi. Lát đầu không cần bao gồm huy hiệu hay nhắc học đa kênh.

**Kiểm chứng sau phát hành:** Nếu có khả năng phân nhóm phù hợp, nhóm thử nghiệm có đối chứng. Cần xác định cách đếm theo **học viên duy nhất**, thời gian quan sát sau khi hoàn tất bài đầu, nhóm đủ điều kiện và guardrail trước khi xem kết quả.

Giả sử số liệu minh họa:

| Nhóm thử nghiệm | Học viên đủ điều kiện | Học viên mở bài 2 trong 7 ngày | Tỷ lệ |
| --- | ---: | ---: | ---: |
| A – giao diện hiện tại | 250 | 80 | 32% |
| B – có nút mới | 250 | 98 | 39,2% |

Chênh lệch quan sát được là **7,2 điểm phần trăm**, tương ứng khoảng **22,5% tăng tương đối** so với nhóm A. Tuy nhiên, **500 người trong ví dụ không tự động bảo đảm khác biệt có ý nghĩa thống kê**. Cần xem cách phân nhóm, dữ liệu mất mát, độ bất định, thời gian thử, biến động theo loại khóa và điều kiện dừng đã thống nhất. Không nên tuyên bố chắc chắn “nút mới khiến tỷ lệ tăng” chỉ dựa trên bảng số liệu minh họa.

### 6.5. Kết quả nào dẫn đến quyết định nào?

- Nếu người dùng tìm nút dễ hơn và bằng chứng sử dụng thực tế cho thấy cải thiện đủ tin cậy, nhóm có thể mở rộng dần.
- Nếu tìm nút dễ nhưng học viên vẫn không mở bài, nhóm xem lại giả định; tiếp tục khám phá vấn đề về thời gian, mức khó hoặc động lực.
- Nếu tính năng gây lỗi truy cập, làm tăng nhầm lẫn hoặc tạo sự cố dữ liệu, nhóm xử lý rủi ro trước khi mở rộng.
- Nếu phát hiện vấn đề lớn nhất là bài quá dài, Product Backlog cần ưu tiên thí nghiệm nội dung thay vì tiếp tục tối ưu giao diện.

Như vậy, một **lát delivery** không chỉ đem lại chức năng; nó còn tạo bằng chứng mới cho **discovery tiếp theo**.

## 7. Đo lường đúng để tránh tối ưu nhầm

Nhóm nên đặt trước **một kết quả chính**, cùng các tín hiệu hỗ trợ và điều kiện bảo vệ:

| Loại chỉ số | Ví dụ | Vai trò |
| --- | --- | --- |
| **Outcome chính** | Tỷ lệ học viên mở bài 2 trong 7 ngày kể từ khi hoàn thành bài 1 | Trả lời vấn đề người dùng mà nhóm muốn cải thiện |
| **Chỉ số dẫn dắt** | Tỷ lệ nhìn thấy/nhấn “Tiếp tục học”, tỷ lệ tìm bài thành công trong thử tác vụ | Giúp giải thích cơ chế thay đổi |
| **Guardrail** | Tỷ lệ lỗi điều hướng, lỗi phân quyền, phản hồi tiêu cực, thời gian tải | Cảnh báo tác động không chấp nhận được |
| **Chất lượng delivery** | Lỗi sau phát hành, kiểm thử thất bại, thời gian khôi phục sự cố | Đảm bảo sản phẩm vận hành đáng tin |
| **Luồng công việc** | WIP, cycle time, throughput, work item age | Nhận biết tắc nghẽn trong quá trình tạo increment |
| **Tác động dài hạn** | Tỷ lệ hoàn thành khóa, mức hài lòng, mức duy trì sử dụng | Kiểm tra giá trị có bền vững hay không |

Các chỉ số cần có định nghĩa rõ. Ví dụ:

~~~text
Tỷ lệ mở bài thứ hai trong 7 ngày
= Số học viên duy nhất hoàn tất bài 1 và mở bài 2 trong 7 ngày
  / Số học viên duy nhất hoàn tất bài 1 và đủ điều kiện học bài 2
~~~

Phải thống nhất cùng khoảng thời gian và tập đủ điều kiện. Nếu khóa chỉ có một bài hoặc học viên bị hạn chế quyền truy cập, họ không nên đi vào mẫu số của phép đo trên. Cần kiểm tra dữ liệu sự kiện có bị ghi trùng khi người học đổi thiết bị hay tải lại trang không.

**Đọc số liệu kết hợp bối cảnh:** tỷ lệ nhấn nút tăng có thể phản ánh nút nổi bật hơn, nhưng chưa chắc việc học hiệu quả hơn. Tỷ lệ hoàn thành bài tăng có thể đến từ thay đổi nội dung, mùa thi hoặc nguồn học viên. Để đưa ra khẳng định nhân quả, phép thử phải được thiết kế và đánh giá phù hợp; nếu không, chỉ nên gọi là tín hiệu quan sát được.

### Không biến công cụ đo thành mục tiêu sai

- Số **story hoàn thành** phản ánh sản lượng công việc, không tự phản ánh lợi ích người dùng.
- **Velocity** trong Scrum, nếu có dùng story point, phục vụ dự báo nội bộ của nhóm; không phải đơn vị đo giá trị hay cơ sở so sánh năng suất cá nhân giữa các nhóm.
- **Cycle time** giúp tìm tắc nghẽn và cải thiện dòng công việc; thời gian ngắn hơn không biện minh cho bỏ kiểm thử hoặc chia story thành mẩu không có giá trị.
- **Số lượt tương tác** không phải lúc nào càng nhiều càng tốt: người học phải nhấn năm lần để mở bài có thể là dấu hiệu trải nghiệm kém.

## 8. Tổ chức sự hợp tác giữa sản phẩm, thiết kế và kỹ thuật

Để discovery và delivery hỗ trợ nhau, cần làm rõ người ra quyết định và cơ chế cộng tác. Một nhóm có thể duy trì sự phối hợp thường xuyên giữa **người chịu trách nhiệm sản phẩm, người nghiên cứu/thiết kế trải nghiệm và người đại diện kỹ thuật**. Đây là một cách tổ chức thường gặp, không phải vai trò bắt buộc của mọi framework.

| Câu hỏi | Trách nhiệm cần làm rõ | Đóng góp liên chức năng |
| --- | --- | --- |
| Vấn đề nào đáng giải quyết trước? | Product Owner hoặc người chịu trách nhiệm chiến lược sản phẩm | Nghiên cứu, dữ liệu, kỹ thuật, vận hành cung cấp bằng chứng và rủi ro |
| Người dùng thực sự làm gì? | Người thực hiện nghiên cứu/thiết kế phối hợp với nhóm | Phát triển và kiểm thử tham gia quan sát, tránh diễn giải sai |
| Giải pháp nào đáng thử? | Nhóm đề xuất nhiều phương án; chủ sản phẩm quyết định ưu tiên giá trị | Thiết kế kiểm tra khả năng dùng; kỹ thuật kiểm tra tính khả thi |
| Làm thế nào để xây và vận hành? | Những người tạo sản phẩm quyết định cách thực hiện trong ràng buộc chung | Người sản phẩm làm rõ tiêu chí; bảo mật/vận hành xác nhận yêu cầu |
| Bằng chứng nào đủ để tiếp tục? | Người chịu trách nhiệm quyết định đặt ngưỡng phù hợp rủi ro | Cả nhóm phản biện dữ liệu, tác động và phương án dự phòng |

Trong **Scrum**, Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; Developers chịu trách nhiệm tạo increment đạt Definition of Done; Scrum Master hỗ trợ hiệu quả của Scrum. Scrum không định nghĩa một giai đoạn discovery bắt buộc riêng biệt. Nhóm có thể đưa công việc khám phá vào hoạt động thường xuyên, phối hợp với Sprint Goal và thích ứng backlog khi có thông tin mới.

Trong **Kanban**, nhóm trực quan hóa cả các công việc khám phá và phát triển nếu điều đó giúp phát hiện ùn tắc; đồng thời tránh dùng một cột “Discovery” như kho chứa vô hạn ý tưởng không được quyết định. Có thể quản lý các loại việc bằng chính sách rõ ràng, giới hạn WIP và nhịp replenishment phù hợp.

Trong **XP**, các thực hành kỹ thuật như test-first khi thích hợp, tích hợp liên tục, refactoring và làm việc cùng nhau giúp chuyển giả thuyết đã chọn thành phần mềm có thể thử nhanh mà ít tích lũy rủi ro. Kết hợp kỹ thuật tốt với khám phá nhu cầu giúp nhóm duy trì khả năng đổi hướng khi phản hồi thay đổi.

### Một nhịp làm việc minh họa trong tuần

Nhịp dưới đây chỉ để tham khảo, cần điều chỉnh theo quy mô và loại sản phẩm:

1. **Đầu tuần:** xem outcome và tín hiệu sản phẩm; chọn giả thuyết/rủi ro quan trọng nhất cần học.
2. **Trong tuần:** quan sát hoặc trao đổi với người dùng; kiểm tra ý tưởng; nhóm delivery hoàn tất các lát đã đủ rõ; chủ động nêu bất định mới.
3. **Khi có phát hiện:** cập nhật lựa chọn, làm rõ story và tiêu chí chấp nhận; bỏ hoặc chia nhỏ ý tưởng không còn phù hợp.
4. **Khi có increment:** trình diễn, kiểm thử, phát hành phù hợp, thu thập số liệu và hỗ trợ người dùng.
5. **Cuối chu kỳ phù hợp:** kiểm tra cả outcome và luồng công việc; chọn một thay đổi quy trình có thể đánh giá được.

Nhóm tránh biến đây thành các cuộc họp cố định không có quyết định. Quan trọng hơn nhịp họp là **đường đi ngắn từ thông tin mới đến thay đổi có trách nhiệm**.

## 9. Quản lý backlog để ưu tiên học hỏi và tạo giá trị

Một Product Backlog hiệu quả nên làm rõ **lý do ưu tiên**, chứ không chỉ mức “High/Medium/Low”. Khi xem xét một ứng viên, có thể hỏi:

1. Nó phục vụ mục tiêu sản phẩm hay kết quả người dùng nào?
2. Mức độ bằng chứng về nhu cầu và giải pháp hiện có đến đâu?
3. Điều gì sẽ xảy ra nếu nhóm không làm, hoặc làm muộn?
4. Các rủi ro về tính khả thi, bảo mật, dữ liệu và vận hành là gì?
5. Có lát nhỏ hơn hoặc phép kiểm tra rẻ hơn trước khi cam kết lớn không?
6. Cần phối hợp với ai và điều kiện hoàn tất là gì?

Những ý tưởng khám phá có thể được giữ trong **opportunity backlog / danh sách giả thuyết**, trong khi Product Backlog tập trung vào công việc sản phẩm được sắp xếp để hỗ trợ mục tiêu. Đây là một cách quản lý tùy chọn; không bắt buộc tạo hai hệ thống ticket. Điều quan trọng là phân biệt **ý tưởng chưa kiểm chứng**, **công việc khám phá cần thực hiện** và **increment đủ rõ để phát triển**.

Một hạng mục nghiên cứu có đầu ra hữu ích khi trả lời được câu hỏi cụ thể. Ví dụ: “Kiểm tra vì sao người học không quay lại sau bài đầu, bằng 6–8 buổi quan sát/phỏng vấn và dữ liệu funnel; tóm tắt các giả thuyết còn lại cùng mức tin cậy”. Con số buổi là minh họa, không bảo đảm tính đại diện thống kê; mẫu và phương pháp phải phù hợp câu hỏi.

### Khi nào một story sẵn sàng để delivery?

Không có yêu cầu Agile phải biết mọi chi tiết. Tuy nhiên, nhóm thường cần đủ thông tin để tự tin bắt đầu:

- Hiểu người dùng, kết quả mong muốn và tiêu chí chấp nhận chính.
- Có phạm vi đủ nhỏ để hoàn thành, kiểm thử và tích hợp.
- Biết những ràng buộc an toàn, nghiệp vụ và phụ thuộc quan trọng.
- Có phương án xử lý những câu hỏi chưa rõ trong khi thực hiện.
- Biết cách xác định story đã đạt Definition of Done và đo tín hiệu sau phát hành.

Nếu một giả định cốt lõi về nhu cầu còn rất yếu, có thể nên ưu tiên một phép kiểm tra trước. Nếu rủi ro kỹ thuật chưa rõ nhưng có thể giải quyết bằng spike ngắn, nhóm thực hiện spike để giảm bất định. Không nên bắt mọi story viết tài liệu chi tiết quá mức mới được làm; cũng không nên gọi “cứ làm rồi biết” để biện minh cho đầu tư lớn chưa có căn cứ.

## 10. Các sai lầm khiến discovery và delivery đứt kết nối

| Phản mẫu | Hệ quả | Cách sửa |
| --- | --- | --- |
| **Discovery diễn ra một lần đầu dự án** | Giả định cũ được giữ nguyên dù hành vi và thị trường thay đổi | Duy trì vòng quan sát và điều chỉnh sau mỗi đợt có bằng chứng |
| **Nhà nghiên cứu chuyển tài liệu rồi rời dự án** | Nhóm phát triển thiếu bối cảnh, hiểu sai động cơ và kịch bản | Cùng tham gia trao đổi, review lựa chọn và phản hồi từ sản phẩm |
| **Đồng nhất phỏng vấn với xác nhận giá trị** | Người dùng nói thích nhưng có thể không sử dụng | Kết hợp lời nói với hành vi và đo kết quả sau phát hành |
| **Chỉ tối ưu velocity và số story** | Ra nhiều chức năng không chắc giúp người dùng | Theo dõi outcome, chất lượng và luồng công việc cùng nhau |
| **Mở rộng giải pháp trước khi kiểm tra giả định rủi ro** | Chi phí thay đổi lớn khi phát hiện không phù hợp | Thử prototype, spike hoặc lát dọc có kiểm soát trước |
| **Prototype được giới thiệu như sản phẩm hoàn chỉnh** | Đánh giá sai về vận hành, dữ liệu và tích hợp | Nêu rõ mục đích kiểm tra, mức hoàn thiện và giới hạn bằng chứng |
| **Mọi ý tưởng nghiên cứu đều đưa thành cam kết backlog** | Nhóm không có chỗ học và điều chỉnh ưu tiên | Đánh dấu giả thuyết, bỏ lựa chọn không còn giá trị |
| **A/B test mọi thứ dù ít người dùng** | Kết quả nhiễu, kết luận thiếu cơ sở | Chọn phương pháp theo câu hỏi, cỡ mẫu và rủi ro; dùng nghiên cứu định tính khi hợp lý |
| **Chỉ đo tác động tích cực, bỏ qua tác động xấu** | Cải thiện một chỉ số nhưng gây lỗi, phiền nhiễu hoặc vi phạm quyền riêng tư | Đặt guardrail và điều kiện dừng từ trước |
| **Nhận phản hồi nhưng không thay quyết định** | Discovery trở thành hoạt động hình thức | Ghi kết luận, chủ quyết định, hành động và thời điểm kiểm tra lại |

## 11. Bài thực hành: thiết kế vòng khám phá – bàn giao

**Tình huống:** Một nền tảng học lập trình ghi nhận nhiều học viên xem trang khóa Java cơ bản nhưng ít người bắt đầu bài đầu tiên. Nhóm nhận được đề xuất: “Hãy xây chatbot AI để tư vấn người mới”. Hiện chưa biết nguyên nhân là lựa chọn khóa khó hiểu, yêu cầu đăng nhập rườm rà, thông tin đầu vào quá nhiều hay người học không chắc khóa phù hợp.

**Yêu cầu thực hành:**

1. Viết một câu **outcome** gắn với người học thay vì tên tính năng.
2. Nêu ít nhất ba **giả thuyết nguyên nhân**, phân biệt dữ kiện đã thấy và điều chưa biết.
3. Chọn **hai phép kiểm tra discovery** có chi phí tương đối thấp, cùng lý do lựa chọn.
4. Đề xuất **một vertical slice** có thể bàn giao, kèm hai hoặc ba tiêu chí chấp nhận và một guardrail.
5. Định nghĩa **chỉ số outcome**, cách đo và quyết định nếu tín hiệu không cải thiện.

### Một phương án tham khảo

**Outcome:** Tăng tỷ lệ người mới đủ điều kiện mở bài Java đầu tiên trong vòng một ngày sau khi xem trang giới thiệu khóa, đồng thời bảo đảm họ hiểu yêu cầu và cấp độ của khóa.

**Giả thuyết:** (a) nội dung giới thiệu chưa nói rõ kiến thức cần có; (b) thao tác “Bắt đầu học” chưa nổi bật; (c) người dùng lo ngại phải trả tiền hoặc cần thẻ dù khóa có phần miễn phí. Đây là các giả thuyết phải kiểm tra, không được ghi thành kết luận.

**Discovery:** Quan sát người mới làm tác vụ “Tìm khóa Java phù hợp rồi mở bài đầu” và phỏng vấn về quyết định đã xảy ra; kết hợp kiểm tra dữ liệu funnel để nhận biết bước rời bỏ. Mẫu nên có người đã bắt đầu và người chưa bắt đầu; dữ liệu phải định nghĩa rõ “xem trang”, “bắt đầu học” và cách đếm người duy nhất.

**Lát đầu nếu phát hiện nút bắt đầu là điểm cản trở:** người dùng có quyền học thấy một hành động bắt đầu rõ ràng trên trang khóa và mở được bài đầu trong một luồng hoàn chỉnh. Tiêu chí chấp nhận: (1) thao tác dẫn đến bài hợp lệ; (2) quyền truy cập được kiểm tra ở máy chủ; (3) trạng thái và thông báo rõ khi bài không khả dụng. Guardrail: không tăng lỗi mở bài hoặc cấp quyền sai.

**Đo outcome:** số người duy nhất mở bài đầu trong một ngày / số người duy nhất đủ điều kiện đã xem trang khóa ở cùng tập đo. Theo dõi thêm liệu họ học được bao lâu, có hiểu cấp độ khóa không và có quay lại bài tiếp theo không. Nếu cách đặt nút không tạo cải thiện rõ ràng, nhóm tìm hiểu sâu hơn về nội dung và rào cản trước khi xây chatbot toàn diện.

Phương án trên chỉ hợp lý **nếu bằng chứng khám phá thực sự chỉ ra** rào cản thao tác. Nếu người dùng chủ yếu phân vân về lộ trình học, nhóm nên thử cách giúp hiểu lộ trình trước. Một câu trả lời tốt thể hiện khả năng **thay đổi phương án theo điều học được**, không phải luôn bảo vệ giải pháp ban đầu.

## 12. Checklist tích hợp discovery với delivery

- [ ] Nhóm có **outcome rõ ràng** và biết ai là người hưởng lợi?
- [ ] Các **sự kiện, giả thuyết và điều chưa biết** đã được phân biệt?
- [ ] Đã xác định **giả định rủi ro nhất** và phép kiểm tra phù hợp?
- [ ] Có nhiều **phương án giải quyết** trước khi chọn một hướng?
- [ ] Người phụ trách sản phẩm, thiết kế, kỹ thuật và kiểm thử **chia sẻ cùng bối cảnh**?
- [ ] Các phát hiện discovery có làm thay đổi **thứ tự Product Backlog** khi cần?
- [ ] Story được chia thành **lát giá trị có thể kiểm chứng**, với tiêu chí chấp nhận rõ?
- [ ] Increment đáp ứng **Definition of Done**, các ràng buộc bảo mật và chất lượng?
- [ ] Đã thống nhất **cách phát hành, đo outcome, guardrail và điều kiện dừng**?
- [ ] Nhóm có quyết định cụ thể **tiếp tục, điều chỉnh, kiểm tra thêm hoặc dừng** dựa trên bằng chứng?
- [ ] Nhóm xem lại cả **giá trị với người dùng** và **dòng công việc nội bộ** để cải tiến liên tục?

**Ghi nhớ:** Khám phá nhu cầu giúp nhóm quyết định **điều gì đáng xây và vì sao**; phát triển giải pháp giúp nhóm tạo ra **phần mềm đúng, an toàn và có thể vận hành**; kiểm chứng sau bàn giao cho biết **giải pháp thực sự tạo ra kết quả nào**. Khi ba hoạt động này liên tục trao đổi bằng chứng và điều chỉnh backlog, Agile mới chuyển từ việc “giao nhiều chức năng” sang **học sớm, giao tăng dần và tạo giá trị thích ứng với thay đổi**.
