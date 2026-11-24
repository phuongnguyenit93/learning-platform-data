# Kéo công việc theo năng lực còn trống

Một nhóm phát triển nền tảng học trực tuyến có 12 yêu cầu đang triển khai. Người phụ trách sản phẩm thấy lập trình viên A vừa hoàn thành phần code nên giao ngay cho A một yêu cầu mới. Trong khi đó, năm yêu cầu khác đang chờ kiểm thử, hai yêu cầu bị chặn ở khâu tích hợp và người học vẫn chưa sử dụng được tính năng đăng ký khóa mới. Mọi người đều bận, nhưng số công việc **thực sự hoàn tất** rất ít.

Đây là tình huống mà tư duy **kéo công việc (pull)** của Kanban giúp thay đổi cách quyết định. Thay vì đẩy thêm việc vào hệ thống mỗi khi có người rảnh, nhóm **bắt đầu công việc mới khi dòng công việc có năng lực tiếp nhận phù hợp**, theo giới hạn công việc đang thực hiện và các chính sách đã thống nhất. Khi một bước phía sau có thể nhận việc, nó kéo việc đủ điều kiện từ bước trước; việc hoàn tất ở một bước tạo chỗ để bước trước tiếp tục, cho tới khi có thể chọn yêu cầu mới.

Điểm cốt lõi không phải “ai cũng phải luôn có việc”. Kanban hướng tới **dòng giá trị hoàn tất trôi chảy và có thể dự báo**. Đôi khi hành động tốt nhất của một Developer không phải mở thêm ticket, mà là hỗ trợ kiểm thử, giải quyết điểm chặn, làm rõ yêu cầu hoặc sửa lỗi đang ngăn một hạng mục hoàn tất.

Bài thuộc chương **Kanban** của module **AGILE_DEVELOPMENT**, gắn với định hướng học Agile qua phản hồi sớm, giao phần mềm tăng dần và cải tiến liên tục. Các ví dụ liên hệ user story, backlog, Scrum, các thực hành kỹ thuật của XP và các phép đo dòng công việc để làm rõ khi nào nên kéo, khi nào nên dừng và cách kiểm tra tác dụng của việc giới hạn WIP.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **push** và **pull**, giữa “một cá nhân đang rảnh” và “hệ thống đủ khả năng tiếp nhận thêm việc”.
2. Thiết kế một workflow có điểm bắt đầu/kết thúc, các trạng thái, chính sách di chuyển và cách kiểm soát Work in Progress (WIP).
3. Áp dụng nguyên tắc **kéo từ hạ nguồn khi có năng lực**, không đẩy thêm vào công đoạn đã đầy.
4. Xử lý đúng những trường hợp dễ gây nhầm: item bị chặn, công việc sửa lại, yêu cầu khẩn, người có chuyên môn giới hạn, hàng đợi và khoảng thời gian chưa có việc phù hợp để kéo.
5. Sử dụng **WIP, work item age, cycle time, throughput** và **Service Level Expectation (SLE)** để đánh giá dòng công việc thay vì chỉ nhìn số người bận.
6. Kết nối cách kéo việc với Product Backlog, tiêu chí chấp nhận, Definition of Done, Sprint Goal và năng lực kỹ thuật để giao sản phẩm có giá trị.
7. Tổ chức một thử nghiệm giới hạn WIP, thu dữ liệu trước–sau, điều chỉnh chính sách kéo việc và tránh những tối ưu chỉ làm đẹp chỉ số.

## 1. Từ “giao thêm việc” đến “kéo việc khi có năng lực”

### 1.1. Hệ thống đẩy việc (push) hoạt động thế nào?

Trong cách **push**, người điều phối hoặc công đoạn phía trước chủ động chuyển việc sang người hoặc công đoạn sau theo kế hoạch của mình, thường không kiểm tra đầy đủ **khả năng tiếp nhận tại thời điểm đó**.

Ví dụ:

1. Product Owner hoặc quản lý đưa tám item vào trạng thái “Đang làm” vì chúng đều có ưu tiên cao.
2. Developers triển khai xong phần code và chuyển cả tám item sang “Chờ QA”.
3. QA chỉ kiểm chứng được hai item trong cùng khoảng thời gian.
4. Sáu item chờ, phản hồi đến muộn; một số phải quay lại sửa vì phát hiện sai yêu cầu.
5. Developers vẫn mở item mới để “không ai ngồi không”, khiến WIP tiếp tục tăng.

Nếu mọi công đoạn đều tối ưu số việc **bắt đầu**, hệ thống có thể tích lũy nhiều hàng chờ nhưng không đưa được giá trị đến người dùng.

### 1.2. Hệ thống kéo việc (pull) hoạt động thế nào?

Trong cách **pull**, công đoạn nhận việc chỉ lấy item tiếp theo khi:

- Có **chỗ theo chính sách kiểm soát WIP** hoặc điều kiện năng lực tương đương.
- Item từ bước trước đã đạt **chính sách chuyển trạng thái**.
- Có người hoặc nhóm có thể tiếp tục thực hiện thật, không chỉ đổi cột.
- Thứ tự ưu tiên hoặc loại dịch vụ cho phép chọn item đó.
- Việc kéo không làm mất những ràng buộc về chất lượng, bảo mật hoặc nghĩa vụ bắt buộc.

Một công đoạn có thể có slot trống nhưng **chưa có item phù hợp**, hoặc chưa có kỹ năng cần thiết; khi đó không bắt buộc kéo một item chỉ để lấp đầy cột. Người trong nhóm có thể hỗ trợ điểm nghẽn đang cản luồng thay vì giả vờ rằng năng lực luôn sử dụng được 100%.

### 1.3. Bảng so sánh

| Câu hỏi | Tư duy đẩy việc | Tư duy kéo việc |
|---|---|---|
| Khi nào bắt đầu item mới? | Khi có kế hoạch, người rảnh hoặc yêu cầu được giao | Khi hệ thống có chỗ và điều kiện kéo việc phù hợp |
| Điều gì được tối ưu trước? | Mức sử dụng từng người/công đoạn, số việc đã khởi động | Dòng công việc hoàn tất, khả năng phản hồi và chất lượng |
| Khi bước kiểm thử đầy? | Tiếp tục chuyển item tới hàng chờ, mở thêm code | Ưu tiên hỗ trợ hoàn tất, tháo chặn, quản lý hàng chờ và WIP |
| Khi item bị chặn? | Có thể mở thêm nhiều việc cho người đó | Làm rõ và giải quyết chặn trước; nếu phải thay thế, theo chính sách minh bạch |
| Khi không có việc phù hợp để kéo? | Tạo hoặc đẩy việc mới cho đủ năng lực | Chấp nhận chưa kéo; dùng năng lực hợp lý để cải tiến hệ thống |
| Cách hiểu tiến triển | Mỗi người hoàn tất phần việc của mình | Hạng mục đi qua toàn bộ workflow và đạt chính sách hoàn tất |

**Pull không có nghĩa mọi công việc đều do cá nhân tự chọn tùy hứng.** Thứ tự ưu tiên, điểm cam kết, loại dịch vụ, chính sách bảo mật và quyền quyết định vẫn cần rõ. Kanban không bỏ quản lý ưu tiên; nó làm cho quyết định **nhận thêm việc** phụ thuộc vào khả năng hoàn tất thật.

## 2. “Năng lực còn trống” là năng lực của dòng công việc

Một hiểu nhầm lớn là đồng nhất capacity với thời gian rảnh của một người. Một Developer vừa xong code có thể chưa có việc lập trình ngay, nhưng nếu toàn bộ công việc đang nằm ở QA, hệ thống **chưa nhận thêm giá trị** từ việc Developer mở thêm một story.

### 2.1. Phân biệt ba loại năng lực

| Loại năng lực | Câu hỏi | Ví dụ |
|---|---|---|
| **Năng lực cá nhân** | Một người có thời gian và kỹ năng để làm gì? | Kỹ sư frontend có thể viết tiếp một màn hình |
| **Năng lực công đoạn** | Một bước của workflow có thể tiếp nhận bao nhiêu việc theo chính sách? | “Đang kiểm chứng” tối đa hai item |
| **Năng lực hệ thống** | Toàn bộ luồng từ bắt đầu đến hoàn tất có thể nhận thêm mà không tăng tắc nghẽn bất hợp lý không? | QA đang đầy, deploy bị chặn, WIP toàn hệ thống đã chạm giới hạn |

Các năng lực này liên quan nhau nhưng không trùng nhau. **Một người rảnh không đủ để kết luận nên mở item mới**. Ngược lại, còn slot WIP cũng không chứng minh có đủ kỹ năng hoặc dữ liệu để nhận việc.

### 2.2. Bắt đầu ít hơn để hoàn tất nhiều hơn

Giả sử ba Developers đang làm ba PBI khác nhau nhưng QA chỉ có thể kiểm chứng một PBI tại một thời điểm. Developers liên tục mở thêm story sẽ khiến thời gian từ bắt đầu tới Done dài ra. Nếu một Developer hỗ trợ viết test tích hợp hoặc sửa ngay một lỗi QA vừa phát hiện, một PBI có thể hoàn tất sớm hơn và người dùng nhận phản hồi sớm hơn.

Đây không phải chủ trương để nhân sự **ngồi chờ** hoặc mọi người bỏ chuyên môn. Đó là cách phân bổ công sức theo **điểm cần hỗ trợ nhất trong luồng**, với các hoạt động phù hợp kỹ năng và an toàn.

### 2.3. Sử dụng năng lực 100% có thể làm tăng chờ đợi

Trong hệ thống có biến động, khi một công đoạn luôn ở mức sử dụng tối đa, một công việc bất ngờ hoặc một item khó sẽ tạo hàng chờ nhanh chóng. Một ít **năng lực dự phòng** giúp xử lý trường hợp lỗi, hỗ trợ kiểm thử và đáp ứng yêu cầu khẩn có thật.

Không có một tỷ lệ sử dụng “lý tưởng” chung cho mọi đội. Mức dự phòng phụ thuộc loại công việc, độ biến động, nghĩa vụ dịch vụ và mức rủi ro. Cần nhìn kết quả dòng công việc thay vì đặt mục tiêu mọi người phải bận 100% từng giờ.

## 3. Thiết kế Definition of Workflow trước khi kéo

Theo **The Kanban Guide**, một hệ thống Kanban cần có **Definition of Workflow (DoW)**, tức mô tả cách công việc đi qua hệ thống. Những yếu tố cần làm rõ gồm:

1. Các loại **work item** đi qua workflow.
2. **Điểm bắt đầu** và **điểm hoàn tất** của workflow.
3. Những trạng thái mà work item đi qua từ bắt đầu tới kết thúc.
4. Cách **kiểm soát WIP** giữa hai điểm này.
5. Các **chính sách rõ ràng (explicit policies)** về cách item chuyển qua các trạng thái.
6. **Service Level Expectation (SLE)** — kỳ vọng thời gian hoàn tất cho item, được mô tả bằng một khoảng thời gian và xác suất.

Không nhất thiết mỗi hệ thống đều phải có bảng với cùng số cột hoặc một phần mềm Kanban chuyên dụng. Quan trọng là mọi người hiểu cùng **điểm nào bắt đầu tính WIP, điều kiện nào kéo việc, thế nào là hoàn tất và cách nhìn rủi ro**.

### 3.1. Workflow minh họa cho nhóm phát triển phần mềm

~~~mermaid
flowchart LR
    A["Yêu cầu mới / Backlog"] --> B["Đã làm rõ / Ready"]
    B -->|"Kéo khi có chỗ"| C["Đang phát triển<br/>WIP ≤ 3"]
    C -->|"Đạt chính sách chuyển"| D["Đang kiểm chứng<br/>WIP ≤ 2"]
    D -->|"Đạt điều kiện hoàn tất"| E["Done"]
    D -. "Phản hồi lỗi / làm lại" .-> C
~~~

Các con số **3** và **2** là ví dụ để học, **không phải khuyến nghị WIP áp dụng cho mọi nhóm**. Một workflow thực tế có thể cần bước phân tích, triển khai, phê duyệt hoặc nhiều loại việc. DoW phải mô tả ranh giới phù hợp thực tế, không phải sao chép bảng mẫu.

Ví dụ DoW:

| Thành phần | Quyết định minh họa |
|---|---|
| Work item | User story có thể kiểm chứng, bug, thay đổi vận hành cần hoàn tất; loại việc được ghi rõ |
| Điểm bắt đầu | Khi một PBI được kéo từ Ready sang Đang phát triển |
| Điểm kết thúc | Khi item đáp ứng chính sách Done và các chuẩn chất lượng áp dụng |
| Trạng thái | Ready → Đang phát triển → Đang kiểm chứng → Done |
| Kiểm soát WIP | Đang phát triển tối đa 3; Đang kiểm chứng tối đa 2; có thể thêm giới hạn tổng theo dữ liệu |
| Chính sách kéo | Bước nhận có slot, item đủ điều kiện chuyển và được ưu tiên đúng chính sách |
| Chính sách bị chặn | Hiển thị cờ Blocked; vẫn tính WIP khi nằm trong ranh giới; ưu tiên tháo chặn |
| SLE minh họa | Sau khi có dữ liệu, xác lập kỳ vọng thời gian hoàn tất với xác suất phù hợp |

### 3.2. Phân biệt một cột hàng chờ với một bước đang thực hiện

Các bảng thường có cột “Ready for QA” hoặc “Chờ triển khai”. Nếu item đã **bắt đầu** nhưng đang chờ, nó vẫn nằm trong ranh giới WIP của toàn hệ thống. Không nên chuyển item vào một cột “Chờ” không bị tính để làm đẹp con số công việc đang thực hiện.

Có thể quản lý hàng chờ theo chính sách riêng, nhưng cần nhất quán:

- Item ở cột chờ đó đã được coi là **started** chưa?
- Từ đâu tính cycle time và work item age?
- Có giới hạn tồn đọng trong hàng chờ không?
- Ai chịu trách nhiệm kéo item tiếp theo từ hàng chờ?
- Khi nào cần hỗ trợ gỡ điểm chặn?

Nếu không có những định nghĩa này, hai đội cùng báo “WIP = 5” có thể đang đo hai điều hoàn toàn khác nhau.

### 3.3. “Ready” và “Done” là các chính sách cụ thể, không phải nhãn đẹp

**Ready** có thể là vùng công việc chưa bắt đầu nhưng đủ thông tin để được cân nhắc kéo: đối tượng, giá trị, rủi ro, điều kiện chấp nhận. Nó không tự động là một “Definition of Ready” bắt buộc của Scrum.

**Done** phải biểu thị điều thật sự đã hoàn tất trong phạm vi workflow. Nếu dùng Scrum, Increment chỉ được xem là Done khi đáp ứng **Definition of Done**. Nếu workflow kết thúc ở “đã phát triển xong, chuyển cho đội khác”, hãy gọi đúng giới hạn đó; đừng báo rằng người dùng đã nhận giá trị nếu các bước kiểm chứng hoặc triển khai thiết yếu còn ở ngoài hệ thống.

## 4. Cơ chế kéo việc từ hạ nguồn lên thượng nguồn

**Hạ nguồn (downstream)** là bước gần điểm hoàn tất hơn, chẳng hạn kiểm chứng so với phát triển. **Thượng nguồn (upstream)** là bước trước đó. Trong một pull system, công đoạn hạ nguồn nhận việc khi **có khả năng xử lý**, tạo tín hiệu để công đoạn thượng nguồn tiếp tục làm hoặc chọn item.

### 4.1. Một chuỗi kéo cụ thể

Xét workflow:

~~~text
Ready --> Development (WIP limit 3) --> Verification (WIP limit 2) --> Done
~~~

Tại thời điểm bắt đầu:

| Trạng thái | Item | Số lượng / Giới hạn |
|---|---|---|
| Ready | R1, R2, R3, R4 | Chưa bắt đầu, chờ được cân nhắc kéo |
| Development | D1, D2, D3 | 3/3 — đầy |
| Verification | V1, V2 | 2/2 — đầy |
| Done | Các item đã hoàn tất trước đó | Không còn tính WIP của workflow này |

Giả sử **D1** đã code xong và đủ điều kiện sang kiểm chứng. Không thể tự động chuyển sang Verification vì bước đó đang **2/2**. Developer không nên mở **R1** chỉ vì đã hoàn thành phần code của D1; D1 chưa rời WIP Development theo chính sách hiện tại.

**Chuỗi sự kiện hợp lệ:**

1. **V1** được kiểm chứng xong, đạt tiêu chuẩn Done và rời Verification. Bước Verification còn **1/2**.
2. Verification **kéo D1** đã đủ điều kiện từ Development. Verification lại **2/2**.
3. D1 đã rời Development. Development còn **2/3**.
4. Development có thể **kéo R1** nếu R1 đủ điều kiện, đúng ưu tiên và đội có năng lực thực hiện. Development trở lại **3/3**.
5. Các item khác giữ vị trí; đội theo dõi thời gian chờ và hỗ trợ những item bị chặn.

~~~mermaid
sequenceDiagram
    participant Ready as Ready
    participant Dev as Development (3)
    participant Test as Verification (2)
    participant Done as Done
    Note over Dev,Test: Ban đầu Dev 3/3, Verify 2/2
    Test->>Done: Hoàn tất V1 theo chính sách Done
    Note over Test: Verify còn 1/2
    Dev->>Test: Verify kéo D1 đủ điều kiện
    Note over Dev: Dev còn 2/3
    Ready->>Dev: Dev kéo R1 đủ điều kiện
    Note over Dev,Test: WIP trở lại trong giới hạn
~~~

Đây là **mô hình minh họa một pull system theo công đoạn**, không phải mọi hệ thống đều nhất thiết phải có slot cho từng cột. Một số nhóm đặt giới hạn tổng hoặc chính sách theo loại việc. Mục đích là **điều khiển việc bắt đầu bằng năng lực hoàn tất**, không dùng thao tác chuyển cột để tạo chỉ số đẹp.

### 4.2. Một slot trống không phải mệnh lệnh kéo việc

Giả sử Verification còn một slot nhưng không có item nào đủ điều kiện kiểm tra, hoặc người kiểm thử chưa có quyền truy cập môi trường. Kéo một item chưa sẵn chỉ để điền cột có thể làm tăng chờ đợi, bỏ qua kiểm soát hoặc gây chuyển trạng thái giả.

Lúc đó nhóm có thể:

- Hỗ trợ hoàn tất công việc ở bước trước.
- Chuẩn bị dữ liệu hoặc môi trường kiểm chứng.
- Khám phá một rủi ro đang ảnh hưởng dòng công việc.
- Cải tiến kiểm thử tự động hoặc khả năng quan sát cần thiết.
- Hỗ trợ làm rõ yêu cầu gần được chọn.

Việc lựa chọn phụ thuộc ưu tiên và chính sách. **Không cần giữ mọi cột đầy để chứng minh Kanban hiệu quả.**

### 4.3. Pull không có nghĩa phải kéo từ trái sang phải một cách máy móc

Khi có nhiều item đủ điều kiện ở bước trước, nhóm cần biết **nên kéo item nào trước**. Các tiêu chí có thể gồm:

- Thứ tự ưu tiên được xác định bởi người có trách nhiệm sản phẩm/dịch vụ.
- Loại công việc và mức độ khẩn cấp theo chính sách.
- Work item age; item già tuổi có nguy cơ vượt SLE hoặc mắc điểm chặn.
- Phụ thuộc: việc nào giúp hoàn tất một luồng đang bị kẹt?
- Kỹ năng và môi trường có thể tiếp nhận công việc thật.
- Những nghĩa vụ bắt buộc về bảo mật, dữ liệu hoặc hợp đồng.

Nếu item ưu tiên cao nhất chưa đủ điều kiện, chính sách phải nêu cách xử lý: làm rõ hoặc tháo chặn, chọn item tiếp theo đủ điều kiện, hay xin quyết định từ người có thẩm quyền. **Không tự ý thay thứ tự sản phẩm hoặc bỏ kiểm soát quan trọng** chỉ vì một kỹ sư muốn lấy việc khác.

## 5. Kiểm soát Work in Progress (WIP)

### 5.1. WIP là gì?

**WIP** là số work items đã bắt đầu nhưng chưa hoàn tất trong ranh giới workflow được xác định. Nếu một item đã được nhận vào hệ thống nhưng đang chờ kiểm thử, nó vẫn là WIP cho tới khi đạt điểm kết thúc được công bố.

Giả sử workflow đếm từ lúc một item được kéo vào Development tới lúc Done:

\[
\text{WIP}(t)=\#\{\text{item đã bắt đầu nhưng chưa Done tại thời điểm }t\}
\]

Nếu có 3 item đang Development và 2 item đang Verification, WIP hệ thống là **5**, miễn không có vùng WIP nào khác bị bỏ sót. Nếu có thêm 4 item đang chờ triển khai thuộc ranh giới workflow, WIP phải tính thêm 4 item đó.

### 5.2. Giới hạn WIP là cơ chế kiểm soát, không phải con số trang trí

Một **WIP limit** có thể được đặt:

- Cho một trạng thái, như Verification tối đa 2.
- Cho một nhóm trạng thái, như Development + Review tối đa 4.
- Cho toàn bộ workflow, như tổng started-to-done không vượt 6 theo chính sách.
- Cho một loại công việc hoặc luồng đặc biệt, nếu có lý do quản trị rõ.

**Kanban không quy định mọi cột phải có giới hạn giống nhau hoặc một công thức WIP cố định.** Điều bắt buộc trong định nghĩa workflow là có cách kiểm soát WIP phù hợp và minh bạch. Giới hạn phải là công cụ để thực hiện chính sách, không phải mục tiêu tự thân.

### 5.3. Bắt đầu với giới hạn nào?

Không có con số phổ quát. Cần xem:

1. Lượng việc đang làm và thời gian hoàn tất thực tế.
2. Khả năng xử lý của những bước thường tắc nghẽn.
3. Kích thước, loại việc và mức chờ của work items.
4. Mức biến động do sự cố, hỗ trợ người dùng và phụ thuộc ngoài.
5. Kỹ năng có thể chia sẻ và công cụ kiểm thử/triển khai.
6. Chất lượng và các nghĩa vụ không thể thương lượng.

Ví dụ một đội có hai người thường xuyên kiểm chứng tích hợp, có thể **thử** giới hạn Verification = 2. Sau vài chu kỳ, nếu item nằm lâu trong Verification do chờ môi trường, nhóm cần xử lý năng lực môi trường, không đơn giản tăng limit lên 5 cho đẹp bảng.

### 5.4. Giới hạn WIP không phải chỉ tiêu sử dụng tối đa

Nếu Development limit = 3, trạng thái có 1/3 item vẫn hoàn toàn hợp lệ. Điều cần hỏi là **điều gì giúp luồng tiến gần Done**, không phải làm sao duy trì 3/3 mọi lúc.

Khi WIP dưới limit nhưng một item đang gần vượt kỳ vọng dịch vụ, việc hỗ trợ item ấy có thể tạo giá trị hơn kéo thêm item mới.

### 5.5. WIP giúp bộc lộ điểm nghẽn

Giả sử kiểm chứng thường chậm, khi Development không thể chuyển thêm item sang Verification, đội nhìn thấy tắc nghẽn thay vì giấu nó bằng một hàng chờ không giới hạn. Những lựa chọn cải tiến có thể gồm:

- Đưa QA hoặc người có kỹ năng kiểm thử vào thảo luận tiêu chí trước khi viết code.
- Tạo và chạy kiểm thử tích hợp sớm, nhiều lần.
- Cải thiện dữ liệu thử và môi trường.
- Chia PBI thành lát cắt nhỏ hơn nhưng vẫn đúng, có thể kiểm chứng.
- Giảm công việc bắt đầu song song.
- Đầu tư chuyên môn hoặc thay đổi cơ chế phụ thuộc khi vấn đề vượt phạm vi đội.

**Giới hạn WIP không tự làm biến mất bottleneck.** Nó làm cho năng lực không khớp được nhìn thấy, tạo tín hiệu hành động.

## 6. Chính sách kéo việc cần rõ ràng, không phụ thuộc người nhớ

Một pull system vận hành ổn định khi người tham gia hiểu **được kéo gì, khi nào, bởi ai và theo điều kiện nào**.

### 6.1. Mẫu chính sách kéo từ Ready vào Development

Ví dụ minh họa:

> **Khi Development còn chỗ theo WIP limit**, nhóm cân nhắc item đứng cao nhất đủ điều kiện trong Ready. Item cần có mục tiêu, phạm vi và ví dụ hành vi quan trọng đủ rõ, các phụ thuộc quyết định khả năng hoàn tất đã được xử lý hoặc có kế hoạch khả thi. Người được giao trách nhiệm về thứ tự ưu tiên có thể điều chỉnh trước khi kéo. Nếu không có item phù hợp, nhóm ưu tiên hỗ trợ điểm chặn hoặc hoạt động cải tiến có ích thay vì kéo một item chưa sẵn.

Điều này không đòi hỏi Product Backlog phải viết mọi đặc tả hoàn chỉnh. Chính sách **đủ rõ để tránh bắt đầu mù mờ**, nhưng vẫn cho phép làm rõ tiếp khi xuất hiện thông tin mới.

### 6.2. Mẫu chính sách kéo sang Verification

> Verification nhận item khi còn năng lực theo WIP limit và có phiên bản triển khai/tích hợp cho phép kiểm tra các tiêu chí liên quan. Điều kiện vào có thể gồm kết quả build, dữ liệu thử, mô tả hành vi mong đợi và các kiểm tra tự động sớm. Nếu item chưa đáp ứng, công việc chưa được coi là đã chuyển xong chỉ nhờ thao tác kéo thẻ.

Nếu nhóm dùng chung DoD, cần biết điều gì thuộc **điều kiện qua bước** và điều gì thuộc **tiêu chuẩn Done của Increment**. Một bước Verification có thể trả về lỗi, nhưng không nên dùng “đã vào QA” làm bằng chứng item hoàn tất.

### 6.3. Mẫu chính sách hoàn tất

> Item được chuyển sang Done khi các điều kiện hoàn tất áp dụng đã được kiểm chứng và có bằng chứng phù hợp. Nếu dùng Scrum, Increment phải đáp ứng Definition of Done. Những vấn đề còn mở, kiểm tra bị bỏ qua hoặc rủi ro cần phê duyệt phải được thể hiện trung thực; không chuyển sang Done chỉ để giải phóng WIP.

Chính sách Done phải phù hợp **điểm kết thúc thực sự** của workflow. Nếu nhóm đo tới “sẵn sàng phát hành” mà việc triển khai do bộ phận khác thực hiện, cần truyền đạt rõ. **Kết thúc trên bảng không tự chứng minh người dùng đã nhận giá trị.**

### 6.4. Chính sách cho yêu cầu khẩn

Một số hệ thống cần xử lý lỗi bảo mật, sự cố sản xuất hoặc gián đoạn dịch vụ ngay lập tức. Có thể định nghĩa **class of service** đặc biệt như *expedite*:

- Tiêu chí rõ để một việc được gọi là khẩn (ví dụ sự cố ảnh hưởng nghiêm trọng tới người dùng hoặc nghĩa vụ bắt buộc).
- Vai trò có quyền xác định/ưu tiên tình huống khẩn.
- Giới hạn số việc khẩn cùng lúc, chẳng hạn **một item expedite tại một thời điểm** nếu phù hợp.
- Cách xem tác động tới item khác và công bố dự báo thay đổi.
- Cách xử lý khi việc khẩn vượt mức năng lực thông thường.
- Đánh giá lại sau sự cố để tránh mọi việc đều mang nhãn “khẩn”.

Không nên âm thầm tăng WIP bằng cách gắn nhãn expedite cho những yêu cầu chỉ là “người đề nghị có chức vụ cao”. Cũng không cần giữ WIP limit cứng đến mức bỏ qua một sự cố nghiêm trọng: ngoại lệ phải **có chính sách, minh bạch và trách nhiệm**, không tùy tiện.

### 6.5. Chính sách tránh việc bị bỏ quên vì khó

Nếu đội luôn chọn item dễ nhất để tăng throughput, một item khó có thể già tuổi mãi. Chính sách kéo có thể bao gồm việc xem **work item age**, thời gian đã chờ và tác động người dùng; khi một item gần vượt SLE, nhóm ưu tiên điều tra, hỗ trợ hoặc thương lượng chia lại.

**Không biến tuổi item thành tiêu chí duy nhất**. Có trường hợp nghĩa vụ khẩn, độ nguy hiểm hoặc thay đổi Product Goal cần thay đổi ưu tiên. Điều quan trọng là quyết định được hiểu và ghi rõ.

## 7. Item bị chặn vẫn là công việc đang thực hiện

Một phản mẫu thường gặp:

> “Ticket bị chặn, chuyển nó sang cột Blocked không tính WIP rồi kéo thêm item cho người đang rảnh.”

Nếu item đã bắt đầu và vẫn chưa đạt điểm kết thúc, nó **không biến mất khỏi WIP chỉ vì có nhãn Blocked**. Chuyển nó ra khỏi giới hạn để tạo chỗ giả làm che đi sự chờ đợi của hệ thống.

### 7.1. Cách xử lý item bị chặn

1. **Đánh dấu rõ** trạng thái bị chặn trên bảng, không cất khỏi tầm nhìn.
2. **Ghi điều kiện chặn cụ thể:** đang chờ dữ liệu, quyền truy cập, câu trả lời nghiệp vụ hay môi trường.
3. **Xác định ai có thể tháo chặn** và khi nào cần phản hồi.
4. **Ưu tiên hành động làm chảy lại luồng:** hỗ trợ kiểm tra, liên hệ đầu mối hoặc chia lại phạm vi khi phù hợp.
5. **Theo dõi work item age** và tác động đến SLE/dự báo.
6. **Chỉ kéo việc thay thế theo chính sách rõ**, không tự tạo slot WIP bằng cách đổi nhãn.

Nếu phụ thuộc bên ngoài mất nhiều tuần và đội không thể tác động, cần nêu rõ rủi ro và có quyết định chính thức về việc tạm dừng, thay đổi ranh giới workflow hoặc điều chỉnh kế hoạch. Không dùng thuật ngữ “tạm dừng” để tự động xóa lịch sử đã bắt đầu và làm đẹp cycle time.

### 7.2. Khi lỗi kiểm chứng buộc item quay lại bước trước

Một item được Verification phát hiện lỗi có thể cần quay lại Development. Nếu Development đang đầy, nhóm phải có **chính sách làm lại**:

- Ai hỗ trợ sửa và kiểm chứng lại?
- Có tạm ngừng kéo item mới để xử lý lỗi của item gần Done không?
- Nếu bước trước đã đầy, có cần làm việc vượt WIP giới hạn tạm thời theo ngoại lệ rõ không?
- Thời gian item đi ngược có được giữ trong cycle time và work item age không?

Thông thường, **nên sửa item đang mở thay vì mở thêm nhiều item mới**. Nếu chỉ số cycle time được tính lại từ đầu mỗi lần item quay về bước trước, dữ liệu sẽ che giấu chi phí làm lại.

### 7.3. Năng lực hỗ trợ không đồng nghĩa ai cũng làm được mọi việc

Trong phát triển phần mềm, Developers có thể hỗ trợ viết test hoặc tái hiện lỗi, nhưng không nhất thiết được phép thay một chuyên gia tuân thủ hoặc thực hiện phê duyệt pháp lý. Cần phân biệt:

- Việc có thể chia sẻ sau khi hướng dẫn và kiểm tra chất lượng.
- Việc cần chuyên môn đặc biệt nhưng nhóm có thể chuẩn bị điều kiện sớm.
- Việc chỉ người có thẩm quyền bên ngoài được quyết định.

Pull khuyến khích cộng tác liên chức năng, **không xóa bỏ trách nhiệm, quyền truy cập hoặc chuẩn chuyên môn**.

## 8. Quyết định kéo item nào: ưu tiên, loại công việc và điểm cam kết

**Capacity** trả lời *có thể nhận thêm hay không*; **priority** trả lời *nếu nhận thì nhận item nào*. Hai quyết định cần được kết nối, không đồng nhất.

### 8.1. Replenishment và điểm cam kết

Nhiều hệ thống Kanban phân biệt:

- **Upstream/backlog:** yêu cầu được thu thập, nghiên cứu và làm rõ; chưa chắc đã được cam kết bắt đầu.
- **Replenishment:** hoạt động bổ sung và lựa chọn yêu cầu cho phần workflow tiếp theo.
- **Commitment point:** thời điểm hệ thống chấp nhận xử lý một yêu cầu theo chính sách đã xác định; ranh giới này có thể trùng hoặc khác điểm bắt đầu đo cycle time tùy DoW.
- **Delivery point:** thời điểm dịch vụ được xem là hoàn tất theo định nghĩa áp dụng.

Trong thực tế, **điểm bắt đầu và kết thúc phải được công bố**, không suy từ tên cột. Với các chính sách riêng, một backlog item có thể “được cam kết sẽ xem xét” trước khi thực sự bắt đầu phát triển; hai nghĩa vụ đó cần được phân biệt.

### 8.2. Chính sách chọn việc khi nhiều item cạnh tranh

Giả sử có một slot Development trống và ba item:

| Item | Bối cảnh | Quyết định cần cân nhắc |
|---|---|---|
| A — Sửa lỗi học viên không mở được khóa đã mua | Tác động trực tiếp lớn, có dữ liệu tái hiện | Có thể ưu tiên cao; kiểm tra mức nghiêm trọng và điều kiện an toàn |
| B — Thêm bộ lọc khóa học | Có ích nhưng không khẩn, AC đã rõ | Có thể kéo nếu mục tiêu/ưu tiên cho phép và A chưa thể bắt đầu |
| C — Tích hợp thanh toán mới | Giá trị lớn nhưng sandbox chưa sẵn, phụ thuộc chưa rõ | Ưu tiên giảm bất định/điều kiện tích hợp, tránh kéo cả item triển khai mơ hồ |

Không chọn B chỉ vì B dễ, cũng không nhận C mù mờ chỉ vì C “rất quan trọng”. Người chịu trách nhiệm thứ tự giá trị và nhóm thực thi cần cùng hiểu **khả năng thực hiện, giá trị, rủi ro và nghĩa vụ**.

### 8.3. Các loại dịch vụ có thể có chính sách khác nhau

Trong một số nhóm, công việc được chia thành các *classes of service* như:

- **Expedite:** xử lý khẩn theo tiêu chí nghiêm trọng đã công bố.
- **Fixed date:** có hạn ràng buộc thật, cần dự báo và ưu tiên phù hợp trước ngày đó.
- **Standard:** yêu cầu thông thường, được kéo theo thứ tự và chính sách.
- **Intangible:** công việc tạo giá trị hoặc giảm rủi ro dài hạn, khó thấy ngay qua một tính năng.

Đây là **cách phân loại thực hành có thể hữu ích**, không phải danh sách bắt buộc của The Kanban Guide. Nhóm có thể chọn cách phân loại khác hoặc không cần nếu nhu cầu đơn giản. Quan trọng là chính sách phản ánh **rủi ro trì hoãn và tác động thực**, không phải chỉ dựa vào mức độ ồn ào của yêu cầu.

## 9. Đo dòng công việc để đánh giá pull có tác dụng không

The Kanban Guide nêu bốn flow metrics tối thiểu: **WIP, throughput, work item age và cycle time**. Các chỉ số này trả lời những câu hỏi khác nhau; nên đọc cùng bối cảnh và chất lượng.

| Chỉ số | Định nghĩa | Câu hỏi hữu ích |
|---|---|---|
| **WIP** | Số item đã bắt đầu nhưng chưa hoàn tất tại thời điểm đo | Hệ thống có đang mang quá nhiều việc chưa hoàn thành không? |
| **Throughput** | Số item hoàn tất trong một khoảng thời gian | Luồng đang tạo được bao nhiêu kết quả hoàn tất theo định nghĩa nhất quán? |
| **Work item age** | Thời gian một item chưa hoàn tất đã ở trong workflow từ khi bắt đầu | Item nào đang già tuổi và cần can thiệp ngay? |
| **Cycle time** | Thời gian một item đã hoàn tất đi từ bắt đầu tới kết thúc | Các item hoàn tất mất bao lâu và phân phối có biến động không? |

Nếu sản phẩm còn công việc trước điểm bắt đầu, **lead time** từ lúc yêu cầu được ghi nhận tới lúc cung cấp kết quả có thể dài hơn cycle time. Phải nêu rõ ranh giới đo, không so hai chỉ số theo tên gọi mà bỏ qua cách định nghĩa.

### 9.1. Ví dụ dữ liệu cycle time

Giả sử sáu item cùng loại đã hoàn tất với cycle time như sau:

| Item | Cycle time (ngày) |
|---|---:|
| K1 | 3 |
| K2 | 5 |
| K3 | 4 |
| K4 | 6 |
| K5 | 4 |
| K6 | 8 |

Trung bình là:

\[
\overline{CT}=\frac{3+5+4+6+4+8}{6}=5\ \text{ngày}
\]

**5 ngày là trung bình của mẫu nhỏ này, không phải cam kết mọi item sẽ hoàn tất trong 5 ngày.** Với mẫu 6 item, kết luận về phân phối dài hạn còn rất hạn chế. Ngoài trung bình, nên xem từng giá trị, phân phối, loại công việc và item nào mất thời gian do chờ.

Một item đang mở 7 ngày có **work item age = 7 ngày** theo ranh giới đo, nhưng nó chưa có **cycle time cuối cùng**, vì chưa hoàn tất. Việc chỉ tính cycle time cho item Done có thể che giấu những item vẫn đang mắc kẹt; vì vậy cần xem work item age.

### 9.2. Throughput và dự báo một nhóm item

Giả sử throughput của một nhóm theo tuần là:

| Tuần | Item Done |
|---|---:|
| 1 | 4 |
| 2 | 3 |
| 3 | 5 |
| 4 | 4 |
| 5 | 4 |
| **Tổng** | **20** |

Trung bình là:

\[
\frac{20\text{ item}}{5\text{ tuần}}=4\text{ item/tuần}
\]

Nếu có 12 item tương đối tương đồng còn lại, phép chia thô cho kết quả **khoảng 3 tuần** tại throughput trung bình đó. Đây chỉ là **dự báo minh họa có điều kiện**: kích thước item, năng lực, mức WIP, phụ thuộc và loại việc có thể đổi. Không dùng trung bình này để bảo đảm lịch giao cho một tích hợp lớn chưa làm rõ.

### 9.3. Service Level Expectation (SLE)

**SLE** là dự báo thời gian một item đi qua workflow, thường diễn đạt dưới dạng **thời gian và xác suất**. Ví dụ minh họa:

> “Theo dữ liệu lịch sử đã kiểm tra, khoảng 85% item thuộc loại này hoàn tất trong vòng 9 ngày từ khi bắt đầu.”

Đây **không phải ngưỡng chuẩn cho mọi hệ thống** và không có nghĩa mọi item sẽ hoàn tất trước ngày thứ chín. Nếu chưa có dữ liệu lịch sử, nhóm có thể đặt SLE ban đầu từ kỳ vọng có căn cứ và tiếp tục hiệu chỉnh theo thực tế, đồng thời ghi rõ mức chưa chắc chắn.

Khi item đang mở đến ngày thứ tám và có nguy cơ vượt SLE, nhóm nên **xem xét ngay lý do chờ và khả năng hỗ trợ**, thay vì đợi quá hạn rồi mới nói “đã trễ”.

### 9.4. Little's Law và giới hạn khi suy luận

Trong lý thuyết hàng đợi, **Little's Law** mô tả quan hệ giữa lượng việc trung bình trong hệ thống, tốc độ hoàn tất trung bình và thời gian trung bình một item ở trong hệ thống, dưới các điều kiện phù hợp về hệ thống ổn định và ranh giới đo:

\[
L=\lambda W
\]

Trong ngữ cảnh Kanban có thể diễn giải gần đúng:

\[
\text{WIP trung bình}\approx\text{Throughput bình quân}\times\text{Cycle time bình quân}
\]

Ví dụ giả định: nếu một hệ thống ổn định có **WIP trung bình = 8 item** và **throughput = 2 item/ngày**, thời gian ở hệ thống trung bình theo quan hệ này là:

\[
W\approx\frac{8}{2}=4\text{ ngày}
\]

**Không được suy diễn:** “Giảm WIP từ 8 xuống 4 thì mọi item chắc chắn hoàn tất sau 2 ngày.” Thay đổi WIP có thể làm throughput đổi; hệ thống có thể không ổn định, item không tương đồng, yêu cầu đến theo đợt hoặc tồn đọng tăng. Quan hệ trên không xác định thời gian từng item và không thay thế quan sát thực nghiệm.

Ý nghĩa quản trị là: **WIP có liên hệ với thời gian dòng công việc**, nên cần xem chúng cùng nhau thay vì cố giữ mọi người luôn có việc.

### 9.5. Đừng tối ưu chỉ số bằng cách đổi cách đếm

Những cách làm sai thường gặp:

- Chia một item thành năm ticket rời rạc để tăng throughput nhưng người dùng chưa có khả năng mới.
- Chuyển item blocked khỏi WIP để con số giảm dù thời gian chờ vẫn tồn tại.
- Chỉ tính cycle time từ khi QA bắt đầu, bỏ qua nhiều ngày item đã chờ từ lúc Development.
- Đóng ticket chưa đạt chất lượng rồi tạo ticket sửa riêng.
- Bỏ các trường hợp khó khỏi thống kê mà không nói rõ.
- Xếp hạng Developers theo số ticket Done dù phụ thuộc và rủi ro khác nhau.

Chỉ số chỉ đáng tin khi **định nghĩa nhất quán, chất lượng hoàn tất rõ và có thể đối chiếu với giá trị người dùng**.

## 10. Tư duy pull trong kiểm thử, code review và triển khai

Pull không chỉ là cách kéo thẻ trên bảng. Nó có thể giúp giảm tắc nghẽn ở các bước kỹ thuật thường xảy ra chờ đợi.

### 10.1. Code review

Nếu Developers mở nhiều pull requests cùng lúc nhưng không ai review, thời gian chờ tăng, xung đột code lớn và phản hồi đến muộn. Một số cách xử lý:

- Giới hạn số thay đổi lớn đang chờ review theo năng lực thực.
- Làm thay đổi nhỏ, tích hợp thường xuyên và kiểm thử sớm.
- Khi review là điểm nghẽn, dành năng lực phù hợp để review hoặc pair programming có chủ đích.
- Định nghĩa những kiểm tra cần trước khi một PR được xem là đủ điều kiện review.
- Đo thời gian chờ, tránh biến “đã gửi PR” thành “đã Done”.

Không nhất thiết mọi nhóm phải có cột riêng “Code Review”; nếu có, chính sách kéo và WIP cần phản ánh dòng công việc thực.

### 10.2. Kiểm thử tích hợp

Một nhóm có hai người thường xuyên kiểm thử nhưng năm Developers liên tục hoàn tất code sẽ tạo hàng chờ nếu mọi kiểm thử dồn cuối. Có thể:

1. Làm rõ AC và ví dụ hành vi từ khi chọn item.
2. Bổ sung unit/API/integration tests phù hợp để phát hiện sớm lỗi.
3. Tạo môi trường và dữ liệu thử có thể sử dụng khi cần.
4. Chia lát cắt nhỏ để kiểm tra từng luồng, không đợi cả epic.
5. Khi QA đầy, ưu tiên cùng xử lý lỗi và điều kiện kiểm chứng hơn mở thêm item.

**Tự động hóa không có nghĩa loại bỏ chuyên môn kiểm thử.** Các hoạt động kiểm thử khám phá, bảo mật, khả năng truy cập hoặc đánh giá rủi ro vẫn cần phối hợp phù hợp.

### 10.3. Triển khai và vận hành

Nếu workflow tính Done khi phần mềm đã được triển khai và đáp ứng chính sách vận hành, bước phát hành cũng có năng lực giới hạn: lịch môi trường, phê duyệt, dữ liệu migration hoặc kiểm soát an toàn.

Kanban giúp **nhìn thấy** những giới hạn đó. Nhóm có thể cải thiện bằng CI/CD, chuẩn hóa kiểm tra, feature flags, triển khai từng phần và cơ chế rollback thích hợp, tùy rủi ro. Nhưng **không kéo vượt qua một bước phê duyệt bắt buộc chỉ để giảm WIP**.

### 10.4. Liên hệ với XP

Những thực hành kỹ thuật thường gắn với XP như **TDD, tích hợp liên tục, refactoring, phát hành nhỏ và lập trình cặp khi phù hợp** giúp rút ngắn độ trễ từ triển khai tới phản hồi. Chúng bổ sung cho chính sách pull:

- Pull hạn chế mở quá nhiều thay đổi chưa hoàn tất.
- Tích hợp sớm giúp phát hiện xung đột khi mỗi thay đổi còn nhỏ.
- Kiểm thử tin cậy giúp item đạt điều kiện Done thay vì chờ một đợt hardening dài.
- Refactoring giảm chi phí thay đổi cho các item về sau.

Kanban không tự chỉ định phải dùng XP; đội chọn các thực hành kỹ thuật từ vấn đề chất lượng và khả năng giao hàng thực tế.

## 11. Kanban cùng Scrum: kéo việc mà vẫn theo đuổi Sprint Goal

Kanban có thể được dùng để cải thiện dòng công việc trong một Scrum Team. Hai điều không mâu thuẫn:

- **Scrum** cung cấp Product Goal, Sprint Goal, các accountability, events, artifacts và Definition of Done.
- **Kanban** giúp định nghĩa workflow, kiểm soát WIP, quản lý dòng công việc và dùng dữ liệu thực nghiệm để cải thiện tính dự báo.

### 11.1. Trong Sprint Planning

Developers chọn các Product Backlog Items phù hợp khả năng, Sprint Goal và DoD; Product Owner làm rõ giá trị và ưu tiên. Nhóm có thể dựa vào throughput, thời gian hoàn tất và công việc còn dở để **dự báo thực tế hơn**.

Một giới hạn WIP trong Sprint không có nghĩa chỉ được chọn đúng số PBI bằng WIP limit. **Số item được chọn cho Sprint** và **số item đang triển khai đồng thời** là hai quyết định khác nhau. Ví dụ Sprint có thể dự kiến hoàn tất sáu PBI nhưng chỉ cho phép hai PBI ở trạng thái Development cùng lúc.

### 11.2. Trong Daily Scrum

Daily Scrum là sự kiện 15 phút của Developers để kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog. Một nhóm dùng Kanban có thể nhìn bảng **từ phải sang trái**:

1. Việc nào gần Done nhất và còn trở ngại gì?
2. Item nào bị chặn hoặc work item age cao?
3. Bước nào đang ở WIP limit?
4. Ai có thể hỗ trợ hoàn tất thay vì mở thêm?
5. Khi có chỗ, item nào đủ điều kiện được kéo tiếp theo?

Đây là một **cách tổ chức trao đổi minh họa**, không phải kịch bản Daily Scrum bắt buộc. Điều quan trọng là Developers rời cuộc trao đổi với kế hoạch thích ứng hướng Sprint Goal, không chỉ danh sách ai đã làm gì hôm qua.

### 11.3. Trong Sprint Review

Scrum Team và stakeholders kiểm tra Increment và tiến triển tới Product Goal. Dữ liệu dòng công việc giúp giải thích **khả năng hoàn tất** và điểm chờ; dữ liệu sử dụng giúp đánh giá **giá trị thực**.

Ví dụ throughput tăng nhưng người học vẫn không vào được bài đầu vì sai phân quyền. Khi đó không thể gọi cải tiến dòng công việc là thành công sản phẩm; cần ưu tiên sửa chất lượng và giả thuyết liên quan.

### 11.4. Trong Sprint Retrospective

Nhóm có thể quan sát rằng Verification đã quá tải trong ba Sprint và thử giảm Development WIP hoặc đưa kiểm thử tích hợp vào sớm. Sau đó so sánh:

- Work item age và cycle time của nhóm item tương tự.
- Số item bị chặn ở Verification.
- Increment thực sự đạt DoD.
- Lỗi hồi quy và chất lượng sau phát hành.
- Mức độ bền vững của tải công việc.

Nếu giảm WIP khiến item thường xuyên bị bỏ mặc hoặc làm năng lực bị lệch, nhóm cần điều chỉnh chính sách. **WIP limit là giả thuyết vận hành có thể cải tiến**, không phải một con số vĩnh viễn.

### 11.5. Điều không được nhầm giữa hai khung

| Khái niệm | Trong Scrum | Trong Kanban |
|---|---|---|
| Mục tiêu chính | Tạo giá trị qua Increment hướng Product Goal trong Sprint | Tối ưu dòng giá trị qua workflow được định nghĩa |
| Thời điểm chọn | Developers lựa chọn PBI tại Sprint Planning, có thể điều chỉnh kế hoạch trong Sprint | Kéo/bổ sung item theo chính sách và năng lực luồng |
| Giới hạn WIP | Không phải thành phần bắt buộc nêu riêng trong Scrum Guide | Cách kiểm soát WIP là thành phần của Definition of Workflow |
| Hoàn tất | Increment đáp ứng Definition of Done | Item đạt điểm kết thúc và chính sách hoàn tất đã định nghĩa |
| Đo lường | Scrum không bắt buộc velocity hay một chart cụ thể | WIP, throughput, work item age, cycle time là các flow metrics tối thiểu |

**Áp dụng Kanban cùng Scrum không có nghĩa bỏ Sprint Goal hoặc DoD.** Nếu Scrum Team sử dụng pull, nó vẫn giữ các accountability và các ràng buộc của Scrum.

## 12. Tình huống xuyên suốt: từ “ai cũng bận” đến “mỗi tuần có luồng hoàn tất”

> **Ví dụ giả định phục vụ học tập.** Các lượng việc, giới hạn, thời gian và kết quả ở phần này là dữ liệu minh họa, không phải số đo của đội thực tế hoặc một ngưỡng Kanban bắt buộc.

Một nhóm sáu người phát triển tính năng ghi danh và hỗ trợ học viên. Nguồn yêu cầu gồm:

- Bug về quyền truy cập khóa học.
- User story cho các luồng đăng ký mới.
- Yêu cầu cải thiện thông báo lỗi.
- Công việc kỹ thuật giúp kiểm thử và vận hành.

Nhóm từng giao item mới cho bất kỳ Developer nào vừa hoàn tất phần code. QA nhận nhiều việc vào cuối tuần, lỗi bị phát hiện muộn và phần mềm không thể phát hành như dự báo.

### 12.1. Vẽ hiện trạng và định nghĩa dòng công việc

Nhóm thống nhất:

~~~text
Product Backlog -> Ready -> Development -> Verification -> Done
                              WIP 3            WIP 2
~~~

Chính sách minh họa:

| Nội dung | Thỏa thuận của nhóm |
|---|---|
| Điểm bắt đầu | Khi item được kéo từ Ready vào Development |
| Điểm kết thúc | Khi đạt chuẩn chất lượng của sản phẩm và chính sách Done |
| Development | Tối đa 3 item |
| Verification | Tối đa 2 item |
| Item blocked | Gắn cờ và vẫn tính WIP cho tới khi rời hệ thống theo chính sách |
| Thứ tự kéo | Theo ưu tiên sản phẩm và rủi ro dịch vụ; item đủ điều kiện mới được kéo |
| Việc khẩn | Có chính sách xử lý riêng khi tác động nghiêm trọng, công bố phần việc bị ảnh hưởng |
| Kiểm tra dòng | Nhóm xem hằng ngày item gần Done, điểm chặn và tuổi item; định kỳ điều chỉnh chính sách |

Đội không mặc định WIP tổng = 5 sẽ phù hợp mãi. Đây là mức để **thử** vì quy mô và năng lực kiểm chứng hiện tại. Cần xem kết quả trước khi giữ hoặc thay đổi.

### 12.2. Một buổi sáng với bảng đầy

Tại đầu ngày:

| Cột | Item | Tình trạng |
|---|---|---|
| Ready | R1 — thông báo khi ghi danh lỗi; R2 — bổ sung bộ lọc; R3 — tối ưu email | Chưa bắt đầu |
| Development | D1 — quyền vào bài; D2 — trạng thái đăng ký; D3 — tích hợp email | 3/3, D3 bị chặn bởi môi trường |
| Verification | V1 — ghi danh miễn phí; V2 — phân quyền danh sách khóa | 2/2 |

Một Developer vừa xong phần code của D1 đề nghị kéo R1. Theo chính sách, **chưa thể**: D1 chưa rời Development và Verification đang đầy.

Nhóm quyết định:

1. Hỗ trợ hoàn tất V1 bằng cách sửa nhanh một lỗi test dữ liệu.
2. Khi V1 đạt chính sách Done, Verification còn một slot.
3. Verification kéo D1 đã đủ điều kiện.
4. Development có một slot trống và kéo R1 nếu R1 đủ điều kiện theo thứ tự ưu tiên.
5. D3 vẫn bị chặn và tiếp tục tính WIP; nhóm phân công người xử lý vấn đề môi trường.

Nhờ vậy, việc bắt đầu mới được nối với **một bước hoàn tất thực**, không chỉ cảm giác người viết code đang rảnh.

### 12.3. Ưu tiên công việc gần Done

V2 phát hiện lỗi phân quyền: tài khoản A có thể thấy một mục của tài khoản B. Đây là rủi ro nghiêm trọng. Nhóm không được chuyển V2 sang Done để giải phóng Verification. Tùy chính sách, Developers phối hợp sửa, đánh giá ảnh hưởng và chạy lại kiểm chứng.

Việc này có thể làm chậm R2, nhưng nó bảo vệ kết quả người dùng và chất lượng sản phẩm. **Pull không thay thế việc đánh giá rủi ro**, càng không hợp thức hóa bỏ kiểm tra để tăng throughput.

### 12.4. Sau vài tuần, nhóm đọc dữ liệu

Giả sử trước khi thay đổi, dữ liệu của những item tương đối tương đồng cho thấy nhiều item mở hơn 12 ngày, thường chờ ở Verification. Sau khi kiểm soát WIP và cải thiện môi trường, nhóm thấy tỷ lệ item có work item age cao giảm và nhiều item đạt Done đều hơn. Dù vậy cần kiểm tra:

- Các loại item được so sánh có tương đồng không?
- Cách xác định started và Done có giữ nguyên không?
- Có thay đổi nhân sự, ưu tiên hoặc mức sự cố đồng thời không?
- Các phép kiểm tra chất lượng có tiếp tục được thực hiện đầy đủ không?
- Người học có ít bị lỗi cấp quyền hoặc hoàn tất đăng ký dễ hơn không?

Không thể kết luận **chỉ việc giảm WIP gây ra toàn bộ cải thiện** nếu nhóm đồng thời sửa môi trường và tăng kiểm thử tự động. Có thể kết luận thực dụng hơn rằng **gói thay đổi đã cho tín hiệu tốt**, rồi tiếp tục thử và theo dõi.

### 12.5. Nếu kéo việc làm một người không còn task chuyên môn?

Một Developer frontend có thể không còn story UI sẵn sàng để kéo trong khi luồng đang tắc ở kiểm chứng API. Nhóm có thể trao đổi:

- Có thể hỗ trợ tái hiện bug UI–API hoặc chuẩn bị dữ liệu test không?
- Có thể pair với người chuyên môn khác để học một phần kiểm chứng có giới hạn không?
- Có code review, tài liệu quyết định hay nợ kỹ thuật liên quan luồng hiện tại cần giải quyết không?
- Có việc cải tiến quan trọng phù hợp kỹ năng, nhưng không gây thêm WIP sản phẩm chưa hoàn tất không?

Nếu không có việc phù hợp ngay, điều đó là **thông tin về phân bố năng lực và thiết kế workflow**. Không nên giả tạo một item thấp giá trị để giữ biểu đồ sử dụng nhân sự luôn đầy.

### 12.6. Báo cáo cho người liên quan

Thay vì:

> “Tất cả Developers đều bận; đã bắt đầu 15 tính năng.”

Nhóm có thể báo:

> **Đã hoàn tất:** các luồng ghi danh và phân quyền đạt tiêu chuẩn Done.  
> **Đang xử lý:** 5 item trong hệ thống theo giới hạn WIP.  
> **Điểm nghẽn:** môi trường tích hợp email và kiểm tra quyền truy cập.  
> **Quyết định:** ưu tiên tháo điểm nghẽn và hoàn tất item đang mở trước khi kéo thêm công việc mới.  
> **Dự báo:** dựa trên throughput/cycle time và các giả định hiện tại; cập nhật sau khi xử lý phụ thuộc.  
> **Giá trị cần quan sát:** người học đăng ký và vào bài đầu đúng quyền, ít phải liên hệ hỗ trợ.

Báo cáo này giúp lãnh đạo hiểu **điều gì tạo ra giá trị, điều gì đang chặn và hỗ trợ nào cần thiết**, thay vì chỉ xem số người đang làm việc.

## 13. Bài tập thiết kế pull system cho nhóm của bạn

### 13.1. Chọn phạm vi thử nghiệm nhỏ

Một đội mới bắt đầu với Kanban không cần lập tức thay toàn bộ quy trình. Có thể chọn **một dòng công việc**: sửa bug ảnh hưởng người dùng, phát triển một loại user story hoặc thay đổi vận hành.

Ghi:

1. Loại work items nào đi qua luồng?
2. Khi nào một item chính thức bắt đầu và hoàn tất?
3. Những trạng thái và chờ đợi nào đang có thật?
4. Hiện WIP bao nhiêu, item thường bị chặn ở đâu?
5. Ai có quyền quyết định ưu tiên và loại việc khẩn?
6. Những điều kiện gì để bước sau nhận item?
7. Chất lượng và nghĩa vụ nào cần giữ?
8. Thu được dữ liệu gì trong vài tuần để đánh giá?

### 13.2. Một chính sách kéo việc có thể áp dụng ngay

~~~text
TEN DONG CONG VIEC:
  [Vi du: Bug va user story cho luong ghi danh]

BAT DAU:
  [Khi item duoc keo tu Ready sang Development]

HOAN TAT:
  [Khi item dat chinh sach Done / DoD ap dung]

TRANG THAI VA WIP:
  Ready:
  Development: limit __
  Verification: limit __
  Done:
  Tong WIP (neu co): __

DIEU KIEN KEO:
  - Buoc nhan co nang luc/chỗ theo chinh sach.
  - Item truoc do dat dieu kien chuyen.
  - Uu tien va loai cong viec phu hop.
  - Khong bo qua kiem soat chat luong/an toan.

KHI BLOCKED:
  - Danh dau ro, giu trong WIP theo ranh gioi.
  - Ghi ly do, nguoi co the go chan, moc xem lai.
  - Khong tu dong keo viec thay the vuot limit.

KHI KHAN:
  - Dinh nghia khi nao expedite duoc dung.
  - Ai co quyen xac nhan.
  - Cach bao tac dong den viec dang mo.

DO LUONG:
  - WIP, throughput, work item age, cycle time.
  - Chat luong va ket qua nguoi dung lien quan.

MOC XEM LAI:
  [Sau bao nhieu chu ky / khi xuat hien tin hieu nao]
~~~

Đây là **mẫu thực hành**, không phải biểu mẫu bắt buộc của Kanban. Nhóm cần điền chính sách theo bối cảnh, tránh sao chép con số giới hạn của ví dụ.

### 13.3. Kế hoạch thử trong bốn tuần

| Tuần | Việc làm | Bằng chứng cần quan sát |
|---|---|---|
| **1 — Nhìn thấy thực tế** | Vẽ workflow, điểm bắt đầu/kết thúc, số item WIP, thời gian chờ và chất lượng Done | Tình trạng hiện tại được hiểu chung; phát hiện nơi chờ hoặc WIP ẩn |
| **2 — Kiểm soát bắt đầu mới** | Thử WIP limit và chính sách kéo từ hạ nguồn; đánh dấu blocked đúng | Ít mở mới khi bước sau đầy; hành động hỗ trợ hoàn tất rõ hơn |
| **3 — Cải tiến điểm nghẽn** | Chọn một rào cản có tác động lớn: môi trường, test, phê duyệt, chia item | Bằng chứng về thời gian chờ, lỗi hoặc khả năng hoàn tất |
| **4 — Xem lại và điều chỉnh** | Đọc WIP, age, cycle time, throughput, chất lượng và phản hồi người dùng | Quyết định giữ/đổi limit, chính sách hoặc ranh giới workflow |

Bốn tuần có thể chưa đủ dữ liệu để tính SLE xác suất đáng tin. Trong giai đoạn đầu, ưu tiên **đo nhất quán và minh bạch giả định** trước khi trình bày các con số thống kê như lời hứa.

## 14. Những ngộ nhận thường gặp

### Ngộ nhận 1: “Kéo việc khi còn người rảnh”

Một người rảnh không có nghĩa bước tiếp theo hoặc toàn hệ thống còn năng lực. Kéo thêm khi QA đầy thường chỉ tăng hàng chờ.

**Điều chỉnh:** Xem WIP, bước nghẽn và item gần hoàn tất trước khi chọn việc mới.

### Ngộ nhận 2: “Kanban nghĩa là có bảng cột To Do–Doing–Done”

Bảng trực quan là hữu ích nhưng không đủ nếu thiếu chính sách, cách kiểm soát WIP, điểm bắt đầu/kết thúc và phép đo dòng công việc.

**Điều chỉnh:** Công bố Definition of Workflow và thực hiện chính sách kéo thật.

### Ngộ nhận 3: “Mỗi cột phải luôn đạt đúng WIP limit”

WIP limit là giới hạn trên hoặc cơ chế kiểm soát, không phải chỉ tiêu lấp đầy. Có thể hợp lý khi một cột dưới limit.

**Điều chỉnh:** Tập trung hoàn tất item có giá trị và xử lý điểm nghẽn; đừng kéo item chưa sẵn để đầy cột.

### Ngộ nhận 4: “Blocked thì không tính WIP”

Item bị chặn vẫn đã bắt đầu và chưa hoàn tất theo ranh giới workflow.

**Điều chỉnh:** Đánh dấu rõ, giữ trong WIP và xử lý nguyên nhân; nếu thay đổi chính sách, nêu rõ tác động tới số đo.

### Ngộ nhận 5: “Cột kiểm thử đầy thì đẩy item sang đó và mở việc mới”

Làm vậy chuyển công việc sang hàng đợi vô hạn, tăng work item age và phản hồi muộn.

**Điều chỉnh:** Khi bước sau không nhận, hỗ trợ gỡ nghẽn hoặc chờ tín hiệu pull phù hợp.

### Ngộ nhận 6: “Pull nghĩa là lấy item bất kỳ mình thích”

Năng lực trống là điều kiện cần, không phải quyết định ưu tiên. Tác động người dùng, rủi ro và nghĩa vụ vẫn chi phối lựa chọn.

**Điều chỉnh:** Dùng chính sách replenishment và quyền quyết định thứ tự minh bạch.

### Ngộ nhận 7: “WIP càng thấp càng tốt”

Giới hạn quá thấp hoặc không phù hợp với loại việc có thể gây gián đoạn, thiếu phối hợp hoặc mất khả năng xử lý sự cố.

**Điều chỉnh:** Xem limit như giả thuyết; điều chỉnh dựa trên throughput, cycle time, chất lượng và năng lực thực.

### Ngộ nhận 8: “Mọi việc khẩn đều được vượt limit”

Khi ai cũng có thể gắn nhãn khẩn, chính sách WIP mất ý nghĩa và công việc bình thường bị gián đoạn liên tục.

**Điều chỉnh:** Định nghĩa expedite và ngoại lệ, quyền quyết định, giới hạn và tác động rõ.

### Ngộ nhận 9: “Thời gian trung bình là cam kết cho mọi item”

Cycle time trung bình không mô tả biến động, item đang mở hoặc trường hợp cực đoan.

**Điều chỉnh:** Xem phân phối, work item age và SLE có xác suất; nêu giới hạn dữ liệu.

### Ngộ nhận 10: “Throughput tăng nghĩa là giá trị tăng”

Chia ticket nhỏ hơn, bỏ kiểm thử hoặc đóng sớm có thể làm throughput tăng mà người dùng không nhận thêm giá trị.

**Điều chỉnh:** Giữ định nghĩa Done và xem outcome, lỗi sau phát hành cùng flow metrics.

### Ngộ nhận 11: “Kanban bắt buộc bỏ Scrum và Sprint”

Một Scrum Team có thể dùng phương pháp Kanban để tăng minh bạch dòng công việc trong khi vẫn giữ Sprint Goal, DoD và các sự kiện Scrum.

**Điều chỉnh:** Chọn thực hành phục vụ vấn đề, không thay khung chỉ vì xu hướng.

### Ngộ nhận 12: “Kanban tự sửa được một bottleneck tổ chức”

WIP limit giúp nhìn rõ rằng môi trường QA thiếu hoặc phê duyệt đang chậm; nó không tự cung cấp hạ tầng hay quyền quyết định.

**Điều chỉnh:** Đưa dữ liệu tới người có thẩm quyền, đầu tư kỹ thuật, thay chính sách và theo dõi kết quả.

### Ngộ nhận 13: “Nếu không kéo việc mới, nhân viên không đóng góp gì”

Hỗ trợ sửa lỗi, kiểm thử, review, tháo chặn hoặc cải tiến hệ thống có thể tạo giá trị nhiều hơn mở thêm code.

**Điều chỉnh:** Đánh giá kết quả hệ thống và khả năng phối hợp thay vì chỉ số bận rộn cá nhân.

### Ngộ nhận 14: “Cứ chuyển thẻ là hoàn tất luồng”

Một item có thể chuyển cột nhưng vẫn chưa được tích hợp, kiểm chứng hoặc triển khai phù hợp.

**Điều chỉnh:** Chính sách di chuyển phải dựa trên hành vi và bằng chứng thực, không chỉ thao tác bảng.

### Ngộ nhận 15: “Có giới hạn WIP rồi thì không cần làm rõ backlog”

Pull giúp kiểm soát bắt đầu, nhưng nếu item được kéo quá lớn, mơ hồ hoặc không có giá trị thì hệ thống vẫn chậm.

**Điều chỉnh:** Kết hợp refinement, chia lát cắt, tiêu chí chấp nhận và chính sách chọn việc với quản lý WIP.

## 15. Bài tập vận dụng

### Bài tập A — Có nên kéo item mới?

Một hệ thống có **Development limit = 3**, **Verification limit = 2**. Trên bảng:

- Development: D1, D2, D3 (đầy); D1 đã code xong và chờ kiểm chứng.
- Verification: V1, V2 (đầy).
- Ready: R1 ưu tiên cao, đủ thông tin.

Developer làm D1 nói mình “rảnh” và muốn kéo R1.

**Yêu cầu:** Theo chính sách kéo ở bài, R1 có nên được kéo ngay không? Hãy mô tả một chuỗi sự kiện cho phép R1 đi vào Development hợp lệ.

<details>
<summary>Gợi ý đáp án</summary>

Không kéo ngay vì Development đang 3/3 và Verification 2/2. Đầu tiên hỗ trợ để V1 hoặc V2 thực sự đạt Done; Verification tạo một slot, sau đó kéo D1 nếu D1 đủ điều kiện. Development còn 2/3, lúc đó mới cân nhắc R1 theo ưu tiên và năng lực. Việc Developer đã xong phần code không đồng nghĩa D1 đã rời workflow hoặc đạt DoD.

</details>

### Bài tập B — Blocked có giải phóng WIP không?

Development limit = 2, có D1 và D2. D2 bị chặn do chờ quyền truy cập hệ thống đối tác. Người quản lý đề nghị chuyển D2 sang cột “Blocked ngoài bảng”, coi Development còn 1/2 và kéo thêm R1.

**Yêu cầu:** Điều gì sai trong lập luận này? Đề xuất ba hành động có trách nhiệm.

<details>
<summary>Gợi ý đáp án</summary>

Nếu D2 đã bắt đầu và chưa Done, nó vẫn tính WIP trong ranh giới workflow, dù có nhãn Blocked. Cất khỏi bảng làm giảm số liệu giả và che thời gian chờ. Nhóm nên gắn cờ D2, xác định người có quyền cấp truy cập và mốc phản hồi, hỗ trợ tháo chặn hoặc thay đổi phạm vi có thẩm quyền. Nếu cần nhận việc thay thế, phải áp dụng chính sách ngoại lệ rõ, công bố WIP và tác động; không âm thầm xóa lịch sử.

</details>

### Bài tập C — Giải thích Little's Law

Một nhóm có WIP trung bình khoảng 10 item và throughput trung bình 2 item/ngày trong một giai đoạn tương đối ổn định.

**Yêu cầu:** Tính thời gian ở hệ thống trung bình theo Little's Law. Có thể kết luận rằng giới hạn WIP xuống 5 sẽ chắc chắn làm mọi item xong sau 2,5 ngày không?

<details>
<summary>Gợi ý đáp án</summary>

Theo quan hệ trung bình L = λW, thời gian trung bình xấp xỉ 10/2 = 5 ngày nếu điều kiện về ổn định, ranh giới và dữ liệu phù hợp. Không thể kết luận giảm WIP xuống 5 sẽ bảo đảm mọi item sau 2,5 ngày: throughput có thể thay đổi, công việc biến động và Little's Law không dự báo riêng từng item. Cần thử chính sách, xem cycle time thực tế, throughput, WIP và chất lượng.

</details>

### Bài tập D — SLE và item gần quá hạn

SLE minh họa của một loại item là **85% hoàn tất trong 9 ngày**. Một item đang mở ngày thứ tám, chưa xong vì chờ kiểm thử bảo mật.

**Yêu cầu:** Có thể tuyên bố item chắc chắn trễ hoặc tự bỏ kiểm thử để đạt ngày thứ chín không? Nhóm nên làm gì?

<details>
<summary>Gợi ý đáp án</summary>

Không. SLE là kỳ vọng xác suất, không phải deadline tuyệt đối của từng item. Nhóm cần quan sát work item age, lý do chờ, khả năng phối hợp hoặc chuẩn bị kiểm thử sớm và cập nhật dự báo nếu cần. Không bỏ các kiểm soát bảo mật áp dụng để cải thiện chỉ số. Nếu phụ thuộc thuộc thẩm quyền tổ chức, phải báo cho người có quyền tháo gỡ.

</details>

### Bài tập E — Việc khẩn chen vào

Đội đang giữ WIP đúng giới hạn. Xuất hiện sự cố nghiêm trọng khiến một nhóm học viên nhìn thấy dữ liệu không thuộc quyền. Đồng thời một quản lý cấp cao yêu cầu đổi màu trang chủ ngay hôm nay.

**Yêu cầu:** Việc nào có thể thuộc loại expedite? Cần chính sách gì để không biến mọi yêu cầu từ cấp cao thành sự cố khẩn?

<details>
<summary>Gợi ý đáp án</summary>

Lỗi lộ dữ liệu trái quyền có thể là sự cố khẩn vì ảnh hưởng bảo mật và người dùng; cần phản ứng theo cơ chế xử lý sự cố và người có thẩm quyền. Đổi màu trang chủ không tự thành expedite chỉ vì người đề nghị có chức vụ cao. Chính sách cần tiêu chí mức nghiêm trọng, quyền xác nhận, giới hạn việc khẩn, cách tạm ngừng/điều chỉnh công việc đang mở, thông báo tác động và đánh giá sau sự cố.

</details>

### Bài tập F — Đo đúng khi chuyển từ push sang pull

Trong bốn tuần trước khi giới hạn WIP, nhóm hoàn tất nhiều ticket nhỏ nhưng người dùng vẫn chờ tính năng đăng ký hoạt động. Sau khi giới hạn WIP, số ticket Done giảm nhẹ nhưng một luồng ghi danh end-to-end đạt chất lượng đã được đưa ra dùng thử.

**Yêu cầu:** Có thể kết luận pull system kém hiệu quả vì throughput ticket giảm không? Nêu ít nhất bốn tín hiệu cần đọc cùng nhau.

<details>
<summary>Gợi ý đáp án</summary>

Không. Số ticket có thể thay đổi theo cách chia, định nghĩa Done và độ lớn. Nên xem cycle time của những item tương đồng, WIP và work item age, số Increment thật đạt DoD, lỗi hậu triển khai, tỉ lệ người dùng hoàn tất đăng ký và khả năng nhận phản hồi sớm. Nếu nhóm đã đổi cách chia item, phải nêu rõ điều đó khi so sánh throughput.

</details>

### Bài tập G — Kết hợp pull và Scrum

Scrum Team chọn sáu PBI trong Sprint Planning, có Sprint Goal rõ. Nhóm cũng đặt Development WIP limit = 2.

**Yêu cầu:** Có mâu thuẫn vì đã chọn sáu PBI nhưng chỉ cho phép hai PBI đang Development không? Daily Scrum nên nhìn điều gì?

<details>
<summary>Gợi ý đáp án</summary>

Không mâu thuẫn. Sáu PBI là các hạng mục được lựa chọn theo dự báo cho Sprint; limit = 2 kiểm soát số PBI ở trạng thái Development cùng lúc. Developers kéo thêm khi có chỗ, theo Sprint Goal và chính sách. Daily Scrum có thể nhìn từ item gần Done về các bước trước, xử lý item bị chặn, WIP và work item age, rồi điều chỉnh Sprint Backlog để đạt Sprint Goal; không phải chỉ báo cáo cá nhân.

</details>

### Bài tập H — Chọn một WIP limit khởi đầu

Nhóm có ba Developers, một chuyên gia kiểm thử, một môi trường tích hợp dùng chung và luồng yêu cầu nhiều biến động. Họ hỏi “Nên đặt mọi cột limit bằng số nhân sự không?”.

**Yêu cầu:** Đề xuất quá trình tìm limit khởi đầu và cách kiểm tra sau vài tuần. Vì sao không có công thức một người = một item cho mọi nhóm?

<details>
<summary>Gợi ý đáp án</summary>

Trước hết làm rõ điểm bắt đầu/kết thúc, các trạng thái, số item đang mở, điểm chặn, năng lực kiểm thử và loại việc. Thử một giới hạn theo dòng thực và bottleneck đã quan sát, công bố chính sách kéo; theo dõi WIP, item age, cycle time, throughput và chất lượng. Khi kiểm thử là bottleneck, đặt mọi cột limit theo đầu người có thể làm hàng chờ vẫn tích tụ. Hơn nữa, mỗi item có độ lớn/độ khó khác nhau, người dùng chung tài nguyên, có hoạt động hỗ trợ và năng lực dự phòng.

</details>

## 16. Checklist tự đánh giá hệ thống kéo công việc

Hãy dùng những câu sau với **một luồng công việc thật**, không chỉ với bảng được thiết kế đẹp:

1. Đội có biết loại work items nào thuộc workflow đang theo dõi không?
2. Điểm bắt đầu và điểm kết thúc có rõ để tính WIP, cycle time và work item age không?
3. Các trạng thái trên bảng có phản ánh bước công việc và thời gian chờ thực không?
4. Chính sách kéo sang từng bước có được hiểu và áp dụng nhất quán không?
5. Có kiểm soát WIP rõ ràng thay vì chỉ dùng cột Doing không giới hạn không?
6. Khi một bước đầy, đội có ưu tiên giúp hoàn tất hoặc gỡ chặn thay vì đẩy việc sang không?
7. Một người rảnh có tự động kéo thêm việc bất kể năng lực toàn hệ thống không?
8. Item bị chặn có vẫn được nhìn thấy và tính WIP theo ranh giới đã công bố không?
9. Hàng chờ “Chờ QA” hoặc “Chờ deploy” có đang giấu WIP chưa hoàn tất không?
10. Khi có slot trống nhưng item chưa sẵn, đội có xử lý trung thực thay vì chuyển trạng thái giả không?
11. Có chính sách thứ tự ưu tiên và người có quyền ra quyết định không?
12. Công việc khẩn có định nghĩa, quyền xác nhận và cách quản lý ngoại lệ rõ không?
13. Team có chủ động xem work item age trước khi item trở thành vấn đề nghiêm trọng không?
14. SLE, nếu dùng, có căn cứ hoặc được công bố là kỳ vọng ban đầu cần hiệu chỉnh không?
15. Throughput được tính từ các item Done theo chính sách nhất quán chứ?
16. Việc chia nhỏ ticket hoặc chuyển cột có đang làm đẹp chỉ số mà không tăng giá trị không?
17. Các bước kiểm thử, bảo mật và vận hành có được phản ánh trong điều kiện hoàn tất không?
18. Nếu dùng Scrum, Sprint Goal và Definition of Done có tiếp tục được tôn trọng không?
19. Kỹ năng liên chức năng và các phụ thuộc tổ chức có được xem xét khi giới hạn WIP không?
20. Sau khi thử chính sách mới, đội có đánh giá kết quả trên dữ liệu và điều chỉnh có chủ đích không?

Nếu nhiều câu trả lời chưa có bằng chứng, hãy bắt đầu từ **một điểm chặn thường xuyên hoặc một cột WIP cao**. Làm rõ một chính sách kéo, thử một giới hạn phù hợp, xem lại kết quả và mở rộng khi cách làm thật sự hữu ích.

## 17. Ghi nhớ

- **Kéo công việc (pull)** nghĩa là bắt đầu hoặc chuyển tiếp khi bước nhận và hệ thống có năng lực phù hợp theo chính sách, thay vì đẩy việc theo nhu cầu giữ người luôn bận.
- **Năng lực cá nhân khác năng lực công đoạn và năng lực hệ thống.** Một Developer rảnh không chứng minh QA hoặc toàn bộ workflow có thể nhận thêm.
- **Definition of Workflow** cần làm rõ loại việc, điểm bắt đầu/kết thúc, trạng thái, cách kiểm soát WIP, chính sách chuyển việc và SLE. Kanban không yêu cầu mọi bảng giống nhau.
- **WIP limit giúp lộ điểm nghẽn**, không phải mục tiêu phải lấp đầy; nó cần được điều chỉnh từ bằng chứng thực. Item bị chặn vẫn là việc đã bắt đầu chưa hoàn tất trong ranh giới đo.
- **Ưu tiên và capacity là hai quyết định khác nhau:** có chỗ chưa chắc có item phù hợp để kéo; item cấp bách chưa chắc sẵn sàng triển khai toàn bộ.
- **Dùng bốn flow metrics cùng nhau:** WIP, throughput, work item age, cycle time. SLE và Little's Law hỗ trợ suy luận nhưng không tạo cam kết chắc chắn cho từng item.
- **Đưa kiểm thử, tích hợp, bảo mật và chất lượng vào dòng công việc.** Chuyển thẻ không tự tạo Increment hoàn tất hoặc giá trị người dùng.
- **Kanban có thể bổ sung cho Scrum và XP:** quản lý luồng và WIP trong khi vẫn giữ Sprint Goal, DoD và các thực hành kỹ thuật giúp phản hồi sớm.
- **Hệ thống tốt không phải hệ thống bắt đầu nhiều nhất.** Hãy quan sát phần mềm thật sự hoàn tất, thời gian chờ, chất lượng và khả năng người dùng đạt mục tiêu.

Khi chuẩn bị lấy thêm một hạng mục, hãy hỏi: **“Bước nhận đã có chỗ và đủ khả năng xử lý chưa? Item có đủ điều kiện, đúng ưu tiên và có thể đi tới Done không? Hay chúng ta nên giúp hoàn tất một việc đã bắt đầu trước?”** Đó là cách kéo công việc theo năng lực còn trống để giảm tắc nghẽn, nhận phản hồi sớm và giao giá trị đều hơn.

## Tài liệu tham khảo định hướng

- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, kiểm soát WIP, explicit policies, SLE và bốn flow metrics tối thiểu.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): coi trọng phần mềm hoạt động, cộng tác với khách hàng và khả năng phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao sản phẩm thường xuyên, chất lượng kỹ thuật và phát triển bền vững.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Goal, Sprint Goal, Definition of Done và sự tự quản lý của Scrum Team khi kết hợp Kanban.
- [Kanban University — Kanban Method](https://kanban.university/kanban-guide/): nguồn tìm hiểu thêm về thực hành pull, các chính sách dịch vụ và cải tiến tiến hóa trong bối cảnh tổ chức.
- [Agile Alliance — Glossary](https://agilealliance.org/agile101/agile-glossary/): khái niệm Agile, flow và những thực hành bổ trợ.
