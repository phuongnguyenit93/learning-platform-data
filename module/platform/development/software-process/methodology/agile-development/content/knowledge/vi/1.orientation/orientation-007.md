# Quan hệ giữa Agile, Scrum, Kanban, Lean và Extreme Programming

Trong phát triển phần mềm, năm thuật ngữ **Agile, Scrum, Kanban, Lean và Extreme Programming (XP)** thường xuất hiện cùng nhau. Chúng chia sẻ nhiều mục tiêu nhưng không đồng nghĩa, không nằm trên một cây phân cấp đơn giản và cũng không nhất thiết loại trừ nhau. Một nhóm có thể tư duy theo Agile và Lean, vận hành bằng Scrum, dùng Kanban để nhìn thấy dòng công việc, đồng thời áp dụng các thực hành kỹ thuật của XP.

Bài học thuộc phần **Định hướng** của module **AGILE_DEVELOPMENT**. Mục tiêu là đặt các cách tiếp cận này vào đúng vị trí trước khi đi sâu vào user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc. Điểm chung cần ghi nhớ là **tạo giá trị qua những phần sản phẩm sử dụng được, nhận phản hồi sớm, thích ứng với điều đã học và cải tiến liên tục**.

## 1. Sau bài học, bạn có thể làm gì?

- Phân biệt hệ giá trị, triết lý quản trị, khung làm việc, phương pháp quản lý dòng công việc và phương pháp phát triển phần mềm.
- Giải thích quan hệ và các vùng giao thoa giữa Agile, Lean, Scrum, Kanban và XP mà không đồng nhất chúng.
- Nhận ra mỗi cách tiếp cận giải quyết vấn đề gì, cung cấp cơ chế nào và để ngỏ quyết định nào cho nhóm.
- Minh họa cách phối hợp Scrum, Kanban và XP trong một sản phẩm được giao tăng dần.
- Chọn điểm khởi đầu phù hợp theo tính chất công việc, khả năng phản hồi, chất lượng kỹ thuật và các ràng buộc thực tế.

## 2. Phân biệt năm khái niệm ở cấp độ phù hợp

| Khái niệm | Bản chất | Câu hỏi trọng tâm | Cơ chế hoặc ví dụ tiêu biểu |
| --- | --- | --- | --- |
| **Agile** | Hệ giá trị và nguyên tắc phát triển thích ứng | Chúng ta cộng tác, học từ phản hồi và tạo giá trị như thế nào? | Giao sản phẩm tăng dần, trao đổi thường xuyên, chấp nhận điều chỉnh kế hoạch |
| **Lean** | Triết lý quản trị tập trung vào giá trị và hiệu quả của toàn hệ thống | Điều gì tạo giá trị, lãng phí nằm ở đâu, luồng tạo giá trị bị tắc tại đâu? | Nhìn toàn dòng giá trị, giảm chờ đợi và việc dở dang, cải tiến liên tục |
| **Scrum** | Khung làm việc nhẹ cho công việc phức tạp, dựa trên kinh nghiệm thực tế | Nhóm tổ chức trách nhiệm, mục tiêu, nhịp kiểm tra và thích ứng như thế nào? | Scrum Team, Product Backlog, Sprint, Sprint Review, Sprint Retrospective |
| **Kanban** | Phương pháp quản lý và cải tiến công việc dựa trên dòng chảy | Công việc đang ở đâu, tồn đọng bao nhiêu và làm sao hoàn thành đều đặn hơn? | Trực quan hóa workflow, giới hạn WIP, quản lý luồng, chính sách rõ ràng |
| **Extreme Programming (XP)** | Phương pháp phát triển phần mềm đề cao phản hồi nhanh và kỷ luật kỹ thuật | Làm sao thay đổi mã thường xuyên mà vẫn giữ chất lượng? | TDD, lập trình cặp, tích hợp liên tục, tái cấu trúc, phát hành nhỏ |

**Lưu ý về phạm vi:** Scrum và Kanban không chỉ là bảng công việc; XP cũng không chỉ là một tập hợp mẹo viết mã. Mỗi cách tiếp cận có triết lý và thực hành riêng. Bảng trên nêu trọng tâm dễ phân biệt nhất, không cố đóng khung tuyệt đối.

### Một bản đồ quan hệ, không phải sơ đồ cấp trên–cấp dưới

~~~mermaid
flowchart TB
    A["Agile<br/>Giá trị, nguyên tắc thích ứng"]
    L["Lean<br/>Giá trị, dòng chảy, cải tiến hệ thống"]
    S["Scrum<br/>Khung làm việc theo Sprint"]
    K["Kanban<br/>Phương pháp quản lý dòng công việc"]
    X["XP<br/>Phương pháp và thực hành phát triển phần mềm"]

    A <-->|"Chung mối quan tâm về giá trị,<br/>học hỏi và cải tiến"| L
    A -. "Có thể thể hiện qua" .-> S
    A -. "Có thể thể hiện qua" .-> K
    A -. "Có thể thể hiện qua" .-> X
    L -. "Ảnh hưởng mạnh đến tư duy dòng chảy" .-> K
    S <-. "Có thể phối hợp" .-> K
    S <-. "Có thể phối hợp" .-> X
    K <-. "Có thể phối hợp" .-> X
~~~

Sơ đồ cho biết **những quan hệ thực hành có thể có**, không khẳng định Agile sở hữu Scrum, Lean bao trùm Kanban, hay phải áp dụng tất cả để được xem là Agile. Một nhóm có thể dùng một phương pháp mà chưa thực sự sống theo những giá trị nó hướng tới; ngược lại, nhóm có thể thực hành tinh thần Agile mà không theo Scrum.

## 3. Agile là hướng tư duy: tạo giá trị và học qua phản hồi

Agile phát triển từ nhận thức rằng trong công việc phức tạp, nhu cầu khách hàng, bối cảnh kinh doanh và giải pháp kỹ thuật có thể thay đổi. **Agile Manifesto (2001)** nêu bốn ưu tiên: con người và tương tác; phần mềm hoạt động được; hợp tác với khách hàng; và khả năng đáp ứng thay đổi. Những ưu tiên này không loại bỏ quy trình, tài liệu, hợp đồng hay kế hoạch, mà nhấn mạnh điều cần coi trọng hơn khi xảy ra đánh đổi.

Các nguyên tắc Agile thường dẫn đến cách làm sau:

1. Chia sản phẩm thành những phần nhỏ **có thể kiểm thử và đem lại giá trị**, thay vì chờ hoàn tất toàn bộ mới tìm hiểu người dùng có cần hay không.
2. Hợp tác thường xuyên giữa người hiểu vấn đề kinh doanh, người xây sản phẩm và các bên liên quan.
3. Đón nhận thông tin mới; điều chỉnh ưu tiên và giải pháp dựa trên bằng chứng, thay vì cố giữ nguyên kế hoạch đã không còn phù hợp.
4. Xây dựng chất lượng kỹ thuật và nhịp làm việc bền vững để còn có thể thích ứng ở những lần tiếp theo.
5. Định kỳ xem xét kết quả và cách phối hợp, sau đó thay đổi cụ thể để làm tốt hơn.

**Lặp (iterative)** và **tăng dần (incremental)** là hai ý khác nhau nhưng thường đi cùng. Tăng dần nghĩa là mỗi đợt thêm một phần chức năng sử dụng được; lặp nghĩa là quay lại một ý tưởng hoặc tính năng để cải thiện theo điều đã học. Ví dụ: trước tiên cho học viên lưu tiến độ bài học (tăng dần), sau khi quan sát hành vi lại đơn giản hóa nút “Học tiếp” (lặp).

Agile **không quy định** phải có Sprint hai tuần, bảng cột, Daily Scrum hay TDD. Đó là những lựa chọn ở các mức cụ thể hơn.

## 4. Lean là tư duy tối ưu giá trị và toàn bộ dòng công việc

Lean có nguồn gốc trong tư duy quản trị sản xuất và được vận dụng vào phát triển phần mềm. Trong ngữ cảnh phần mềm, Lean đặt câu hỏi: **Đâu là giá trị khách hàng thực sự nhận được? Những bước nào làm chậm việc mang giá trị đó đến khách hàng?**

Một số góc nhìn quan trọng:

- **Xác định giá trị:** một tính năng được lập trình xong chưa đủ; cần xem nó có giải quyết được nhu cầu người dùng hay không.
- **Nhìn toàn dòng giá trị:** theo dõi từ lúc nhận nhu cầu, làm rõ, thiết kế, viết mã, kiểm thử, triển khai đến khi có thể sử dụng. Tối ưu riêng tốc độ lập trình có thể không giúp giao hàng nhanh hơn nếu việc kiểm thử chờ quá lâu.
- **Giảm lãng phí:** hạn chế chờ duyệt, bàn giao nhiều lần, làm chức năng chưa cần, chuyển đổi ngữ cảnh liên tục, sửa lỗi lặp lại và lượng công việc dở dang quá lớn.
- **Khuyến khích dòng chảy và cơ chế kéo:** hoàn thành công việc đang làm và nhận việc mới theo năng lực thực tế, thay vì đẩy thật nhiều nhiệm vụ vào hệ thống.
- **Tôn trọng con người và cải tiến liên tục:** người trực tiếp làm việc cần được tham gia nhận diện vấn đề, thử thay đổi và đánh giá kết quả.

Ví dụ: nhóm mất ba ngày để viết một thay đổi nhỏ nhưng mất mười ngày chờ kiểm thử và phê duyệt. Chỉ yêu cầu lập trình viên làm nhanh hơn không xử lý điểm nghẽn chính. Nhìn theo Lean, nhóm cần làm rõ tiêu chí kiểm thử sớm, giảm hàng đợi bàn giao hoặc tự động hóa kiểm tra phù hợp.

Lean và Agile có vùng giao nhau rộng: đều coi trọng học hỏi, giá trị và cải tiến. Tuy vậy, **Lean không phải tên khác của Agile**; Lean còn áp dụng ở vận hành, dịch vụ và quản trị ngoài phát triển phần mềm. Cũng không nên hiểu “loại bỏ lãng phí” là cắt bỏ mọi hoạt động chưa tạo ra mã: nghiên cứu nhu cầu, đào tạo và kiểm thử có thể là những đầu tư thiết yếu.

## 5. Scrum đưa ra khung phối hợp để kiểm tra và thích ứng

Scrum là một **framework** dựa trên thực nghiệm (empiricism) và các trụ cột **minh bạch, kiểm tra, thích ứng**. Scrum hữu ích khi nhóm phải giải quyết công việc phức tạp, nơi chỉ có thể học rõ hơn bằng cách tạo ra sản phẩm và kiểm tra kết quả.

### Những thành phần cốt lõi

| Thành phần | Vai trò trong Scrum |
| --- | --- |
| **Scrum Team** | Một nhóm nhỏ, liên chức năng, tự quản, cùng chịu trách nhiệm tạo ra Increment có giá trị; gồm Product Owner, Scrum Master và Developers |
| **Product Owner** | Chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả |
| **Scrum Master** | Chịu trách nhiệm về hiệu quả Scrum, hỗ trợ nhóm và tổ chức hiểu, áp dụng Scrum |
| **Developers** | Những người trong Scrum Team cam kết tạo ra Increment sử dụng được mỗi Sprint; không chỉ giới hạn ở chức danh lập trình viên |
| **Product Backlog** | Danh sách được sắp xếp thứ tự về những gì cần cải thiện sản phẩm; gắn với **Product Goal** |
| **Sprint** | Chu kỳ có độ dài cố định, tối đa một tháng, chứa các sự kiện Scrum và tạo nhịp kiểm tra, thích ứng |
| **Sprint Planning** | Làm rõ vì sao Sprint có giá trị, có thể hoàn thành những gì và sẽ làm như thế nào; tạo **Sprint Goal** và Sprint Backlog |
| **Daily Scrum** | Sự kiện 15 phút để Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch |
| **Sprint Review** | Cùng các bên liên quan kiểm tra kết quả Sprint và thảo luận hướng thích ứng sản phẩm |
| **Sprint Retrospective** | Kiểm tra và cải thiện chất lượng, hiệu quả cách làm việc của Scrum Team |
| **Increment** | Phần sản phẩm đã đạt **Definition of Done**, có thể sử dụng và tích lũy với các Increment trước |

Ba **commitment** gắn với ba artifact trong Scrum là **Product Goal** (Product Backlog), **Sprint Goal** (Sprint Backlog) và **Definition of Done** (Increment). Chúng giúp nhóm minh bạch về đích đến, mục tiêu ngắn hạn và tiêu chuẩn chất lượng.

Scrum **không quy định** ngôn ngữ lập trình, kỹ thuật kiểm thử, cách viết user story hay mô hình bảng Kanban phải dùng. Đây là những quyết định nhóm cần đưa ra. Sprint Review cũng không chỉ là buổi biểu diễn hay xin ký duyệt; đó là lúc học từ kết quả và phản hồi. Increment có thể phát hành ngay khi sẵn sàng, không buộc phải đợi cuối Sprint.

### Ví dụ Scrum

Một nhóm phát triển nền tảng học trực tuyến chọn Sprint hai tuần. Product Goal là giúp học viên hoàn thành lộ trình tự học dễ dàng hơn. Nhóm xác định Sprint Goal: **“Học viên quay lại đúng bài đang học chỉ với một thao tác.”**

Product Owner sắp xếp ưu tiên các mục như lưu tiến độ và hiển thị nút “Học tiếp”. Developers chọn phạm vi phù hợp để tạo Increment đạt Definition of Done, gồm kiểm thử và khả năng sử dụng thực tế. Trong Sprint, nhóm cập nhật Sprint Backlog khi phát hiện điều mới mà vẫn giữ mục tiêu Sprint. Ở Sprint Review, phản hồi chỉ ra người học muốn nhìn thấy tên bài sẽ tiếp tục; nhóm đưa thông tin đó trở lại Product Backlog. Ở Retrospective, nhóm cải tiến cách phối hợp kiểm thử với thiết kế.

Đây là vòng **lập kế hoạch → làm sản phẩm → kiểm tra → thích ứng** được Scrum tạo nhịp rõ ràng.

## 6. Kanban làm rõ luồng công việc và giới hạn việc dở dang

**Kanban** trong môi trường tri thức thường chỉ **Kanban Method**: cách bắt đầu từ quy trình hiện tại rồi từng bước quản lý, cải tiến dịch vụ thông qua dữ liệu về **dòng chảy (flow)**. Một bảng có các cột “To do / Doing / Done” chỉ là công cụ trực quan hóa; chỉ dựng bảng chưa có nghĩa đã quản lý theo Kanban.

Các thực hành phổ biến của Kanban Method bao gồm:

1. **Trực quan hóa công việc và workflow:** làm rõ từng loại công việc, điểm bắt đầu, các bước và trạng thái hoàn thành.
2. **Giới hạn work in progress (WIP):** giới hạn số mục đang được thực hiện để giảm chuyển đổi ngữ cảnh, tồn đọng và việc bị bỏ dở.
3. **Quản lý dòng chảy:** quan sát nơi tắc nghẽn, hỗ trợ công việc hoàn tất thay vì liên tục khởi động việc mới.
4. **Công khai chính sách:** thống nhất điều kiện để nhận việc, chuyển cột, xử lý khẩn cấp và xem là hoàn thành.
5. **Tạo vòng phản hồi:** tổ chức những buổi trao đổi cần thiết về ưu tiên, khả năng đáp ứng và luồng công việc.
6. **Cải tiến cộng tác bằng thử nghiệm:** thay đổi có kiểm soát, quan sát hệ quả rồi giữ hoặc điều chỉnh.

Ví dụ một bảng mô tả dòng công việc:

| Chờ ưu tiên | Sẵn sàng | Đang phát triển — WIP 2 | Đang kiểm tra — WIP 2 | Hoàn tất |
| --- | --- | --- | --- | --- |
| Yêu cầu mới | Việc đã rõ điều kiện bắt đầu | Tối đa 2 việc cùng lúc | Tối đa 2 việc cùng lúc | Đạt điều kiện hoàn tất |

Giả sử cột “Đang kiểm tra” đã đủ hai việc và một việc bị chặn vì thiếu môi trường thử nghiệm. Thay vì mở thêm một tính năng, nhóm có thể cùng tháo gỡ trở ngại, hoàn thành việc đang kiểm tra và chỉ kéo nhiệm vụ mới khi có chỗ. **Giới hạn WIP nhằm tăng khả năng hoàn thành ổn định, không nhằm buộc mọi người lúc nào cũng bận 100%.**

### Nhìn dòng công việc bằng số liệu

| Chỉ số | Cách hiểu thực tế | Câu hỏi hỗ trợ |
| --- | --- | --- |
| **WIP** | Số mục đã bắt đầu nhưng chưa xong tại một thời điểm, theo ranh giới được thống nhất | Có quá nhiều việc đang dở dang không? |
| **Throughput** | Số mục hoàn tất trong một khoảng thời gian | Nhóm đang hoàn thành được bao nhiêu việc mỗi tuần? |
| **Cycle time** | Thời gian một mục đi từ điểm **bắt đầu xử lý** đến điểm **hoàn tất** đã định nghĩa | Mất bao lâu để xử lý một việc đã nhận làm? |
| **Lead time** | Thời gian từ điểm **nhận yêu cầu/đặt hàng** đến lúc giao xong, tùy ranh giới được công bố | Người yêu cầu phải chờ bao lâu? |
| **Work item age** | Thời gian một mục đang mở đã ở trong hệ thống kể từ điểm bắt đầu đo | Việc nào đang già đi và có nguy cơ chậm? |

Cycle time và lead time dễ bị dùng lẫn nhau; hãy **ghi rõ điểm bắt đầu và kết thúc** trước khi so sánh số liệu. Một nhóm có thể dùng phân bố cycle time lịch sử để dự báo khả năng hoàn thành, kèm mức độ tin cậy thay vì hứa một con số chính xác tuyệt đối. Khi hệ thống tương đối ổn định, quan hệ trung bình **WIP ≈ throughput × cycle time** (Định luật Little) giúp nhận ra ảnh hưởng của tồn đọng; không nên áp dụng máy móc khi công việc đến theo đợt mạnh, nhóm thường xuyên bị gián đoạn hoặc ranh giới đo không nhất quán.

Kanban **không bắt buộc** Sprint có thời lượng cố định, các vai trò của Scrum hoặc một nhịp phát hành duy nhất. Nhóm vẫn cần lập kế hoạch năng lực, xử lý ưu tiên và phản hồi với khách hàng; luồng liên tục không đồng nghĩa “cứ lấy việc bất kỳ trên bảng”.

## 7. Extreme Programming (XP) giữ khả năng thay đổi nhờ kỷ luật kỹ thuật

**Extreme Programming** là một phương pháp phát triển phần mềm Agile, nhấn mạnh chu kỳ phản hồi ngắn, cộng tác và chất lượng mã để nhóm có thể đổi hướng thường xuyên với chi phí hợp lý. XP gắn với các giá trị **giao tiếp, đơn giản, phản hồi, can đảm và tôn trọng**.

Các thực hành XP tiêu biểu gồm:

| Thực hành | Mục đích | Minh họa |
| --- | --- | --- |
| **Test-Driven Development (TDD)** | Dùng bài kiểm thử để dẫn dắt những bước thiết kế và lập trình nhỏ | Viết kiểm thử cho quy tắc lưu tiến độ, thấy kiểm thử thất bại, viết mã vừa đủ để qua rồi cải thiện thiết kế |
| **Refactoring** | Cải thiện cấu trúc mã mà không đổi hành vi bên ngoài | Tách logic lưu tiến độ khỏi giao diện khi kiểm thử đã bảo vệ hành vi |
| **Pair programming** | Cùng giải quyết vấn đề và chia sẻ hiểu biết liên tục | Hai người luân phiên viết và xem xét mã cho chức năng khó |
| **Continuous Integration (CI)** | Tích hợp thay đổi thường xuyên và phát hiện xung đột, lỗi sớm | Mỗi thay đổi được kiểm tra tự động trên nhánh chung hoặc quy trình tích hợp phù hợp |
| **Small releases** | Đưa phần giá trị nhỏ đến người dùng sớm để lấy phản hồi | Phát hành nút “Học tiếp” cơ bản trước khi bổ sung gợi ý nâng cao |
| **Simple design, collective code ownership** | Giữ thiết kế đủ đơn giản và tránh nút thắt kiến thức ở một cá nhân | Nhiều thành viên có thể cải thiện khu vực mã khi tuân thủ kiểm thử và quy ước chung |
| **Sustainable pace, close collaboration** | Duy trì tốc độ có thể lặp lại và giảm hiểu sai nhu cầu | Làm rõ tiêu chí chấp nhận cùng người hiểu sản phẩm, tránh dựa vào tăng ca kéo dài |

Vòng **red → green → refactor** của TDD có thể mô tả như sau:

~~~text
Viết một kiểm thử nhỏ đang thất bại (Red)
             ↓
Viết lượng mã tối thiểu để kiểm thử chạy qua (Green)
             ↓
Cải thiện thiết kế trong khi các kiểm thử vẫn chạy qua (Refactor)
             ↓
Tiếp tục với hành vi kế tiếp
~~~

TDD không thay thế kiểm thử tích hợp, kiểm thử hiệu năng hay việc hiểu yêu cầu; nó là một lớp phản hồi kỹ thuật. Tương tự, lập trình cặp không buộc hai người cùng gõ trên một bàn phím mọi lúc, còn CI hiệu quả cần bộ kiểm thử đáng tin và thời gian phản hồi phù hợp.

Scrum mô tả **khi nào** nhóm kiểm tra mục tiêu và sản phẩm, nhưng cố ý không cung cấp đầy đủ cách tạo mã có thể thay đổi an toàn. XP có thể bổ sung năng lực đó. XP cũng có thể được áp dụng trong nhóm quản lý việc theo Kanban; không phải có Scrum thì mới dùng được XP.

## 8. So sánh theo vấn đề cần giải quyết

| Góc nhìn | Agile | Lean | Scrum | Kanban | XP |
| --- | --- | --- | --- | --- | --- |
| Trọng tâm | Giá trị và khả năng thích ứng | Giá trị và hiệu quả toàn hệ thống | Mục tiêu, trách nhiệm, nhịp thực nghiệm | Dòng chảy, giới hạn việc dở dang | Phản hồi kỹ thuật và chất lượng khi thay đổi |
| Đơn vị quan sát thường thấy | Sản phẩm và giá trị cho khách hàng | Dòng giá trị đầu cuối | Product Goal, Sprint Goal, Increment | Work item, workflow, thời gian chờ | Mã, kiểm thử, bản phát hành nhỏ, cộng tác |
| Nhịp làm việc bắt buộc | Không quy định | Không quy định | Sprint tối đa một tháng | Không bắt buộc Sprint; dùng các nhịp phản hồi phù hợp | Khuyến khích chu kỳ phản hồi và phát hành ngắn |
| Vai trò bắt buộc | Không | Không | Ba trách nhiệm: Product Owner, Scrum Master, Developers | Không bắt buộc sao chép vai trò Scrum | Có các cách cộng tác và trách nhiệm theo ngữ cảnh XP |
| Câu hỏi khi có vấn đề | Chúng ta học gì, cần thích ứng ra sao? | Điểm nghẽn của cả hệ thống ở đâu? | Mục tiêu Sprint/sản phẩm thay đổi thế nào? | Việc nào đang kẹt, giới hạn WIP có hợp lý không? | Thay đổi này có được kiểm thử và tích hợp an toàn không? |

Không nên chọn cách làm chỉ từ tên gọi. Một tổ chức có thể có đầy đủ Sprint, backlog và Daily Scrum nhưng vẫn giao phần mềm rất muộn, ít phản hồi và thường xuyên làm lại. Sự hiện diện của nghi thức chưa chứng minh sản phẩm đang được phát triển thích ứng.

## 9. Chúng có thể kết hợp như thế nào?

Hãy xét nhóm sáu người đang phát triển chức năng **“Tiếp tục học”** cho nền tảng học trực tuyến. Nhiều học viên bỏ dở khóa học vì khó tìm lại bài đang xem. Nhóm cần giải pháp sớm nhưng chưa biết vị trí nút nào thực sự hữu ích.

### Bước 1 — Agile: đặt giả thuyết giá trị và lấy phản hồi

Nhóm nêu giả thuyết: “Nếu học viên nhìn thấy bài gần nhất và có thể mở lại bằng một thao tác, tỷ lệ quay lại học sẽ tăng”. Thay vì thiết kế toàn bộ hệ thống gợi ý học tập, nhóm chọn lát cắt nhỏ: lưu tiến độ và đặt nút “Học tiếp” trên trang khóa học. Sau khi có người dùng thực, nhóm quan sát cách sử dụng rồi quyết định có cần cải thiện hay không.

Ví dụ user story:

> **Là** học viên đang học dở một khóa, **tôi muốn** mở lại bài chưa hoàn thành **để** tiếp tục học mà không phải tìm thủ công.

Tiêu chí chấp nhận minh họa: khi học viên đã xem một phần của bài và quay lại trang khóa học, hệ thống hiển thị đúng bài đang học; khi nhấn “Học tiếp”, bài đó mở tại tiến độ đã lưu. Nhóm còn phải làm rõ các trường hợp như bài đã hoàn tất, nhiều thiết bị hoặc kết nối bị ngắt.

### Bước 2 — Scrum: tạo nhịp giao sản phẩm và học hỏi

Product Owner sắp xếp các nhu cầu theo giá trị; Scrum Team chọn Sprint Goal “Khôi phục hành trình học dở trong một thao tác”. Developers chia nhỏ công việc để tạo Increment hoàn chỉnh, bao gồm kiểm thử phù hợp và triển khai được. Tại Sprint Review, nhóm mời người dùng/bên liên quan xem kết quả, hỏi trải nghiệm thực tế và điều chỉnh Product Backlog. Tại Retrospective, nhóm tìm cách giảm thời gian chờ phản hồi thiết kế.

Scrum mang lại **nhịp kiểm tra mục tiêu**; nó không tự động bảo đảm giao hàng tốt nếu các yêu cầu chưa rõ hoặc mã khó kiểm thử.

### Bước 3 — Kanban: thấy hàng đợi và hoàn thành trước khi nhận thêm

Nhóm dùng workflow **Ready → Developing → Review/Test → Done** ngay trong Sprint Backlog và đặt giới hạn WIP cho các bước đang xử lý. Nếu nhiều thẻ dồn ở Review/Test, nhóm cùng hỗ trợ kiểm thử, sửa lỗi hoặc cải thiện môi trường trước khi kéo thêm việc. Nhóm quan sát cycle time và work item age để nhìn ra nơi tắc nghẽn.

**Scrum và Kanban có thể cùng tồn tại:** Sprint vẫn cung cấp mục tiêu và các sự kiện Scrum; Kanban làm rõ dòng chảy bên trong hoặc xuyên qua các Sprint. Việc bổ sung một bảng và giới hạn WIP không tự động thay thế các trách nhiệm, artifact hoặc mục tiêu của Scrum.

### Bước 4 — XP: giữ thay đổi nhỏ và an toàn

Khi viết dịch vụ lưu tiến độ, Developers dùng kiểm thử tự động để kiểm tra hành vi quan trọng, tích hợp thường xuyên và tái cấu trúc phần mã khó hiểu. Với đoạn xử lý nhiều trường hợp biên, hai người có thể lập trình cặp. Chất lượng kỹ thuật giúp nhóm dễ sửa nút “Học tiếp” theo phản hồi mà không liên tục làm hỏng chức năng cũ.

### Bước 5 — Lean: đánh giá toàn bộ thời gian từ ý tưởng đến giá trị

Sau lần phát hành đầu, nhóm phát hiện việc chờ xác nhận dữ liệu và chờ môi trường kiểm thử chiếm nhiều thời gian hơn khâu viết mã. Nhóm thử làm rõ dữ liệu mẫu sớm, tự động hóa bước kiểm tra và giảm số mục mở đồng thời. Nhóm đánh giá hiệu quả bằng thời gian hoàn thành và phản hồi người dùng, đồng thời giữ chất lượng.

Qua ví dụ này, năm khái niệm đóng những vai trò **bổ sung, có giao thoa**: Agile định hướng học hỏi; Lean giúp nhìn toàn luồng giá trị; Scrum tạo khuôn khổ cộng tác; Kanban cải thiện dòng công việc; XP tăng khả năng thay đổi phần mềm an toàn.

## 10. Chọn điểm khởi đầu theo tình huống

| Bối cảnh quan sát được | Cách tiếp cận đáng thử | Điều cần xác nhận |
| --- | --- | --- |
| Sản phẩm mới, nhiều điều chưa chắc về nhu cầu, nhóm liên chức năng có thể cùng hướng đến mục tiêu | Dùng tư duy Agile, cân nhắc Scrum để có mục tiêu và nhịp học rõ | Có Product Owner thực sự quyết định ưu tiên và bên liên quan cung cấp phản hồi không? |
| Nhóm vận hành, hỗ trợ, bảo trì; việc đến không đều và khó gom thành Sprint Goal ổn định | Cân nhắc Kanban, công khai chính sách xử lý và giới hạn WIP | Đã xác định điểm bắt đầu/kết thúc và quy tắc ưu tiên việc khẩn cấp chưa? |
| Nhóm giao chậm do chờ bàn giao, xếp hàng duyệt, kiểm thử thủ công | Dùng góc nhìn Lean kết hợp số liệu flow từ Kanban | Điểm nghẽn nằm ở toàn hệ thống hay chỉ là cảm giác của từng bộ phận? |
| Sản phẩm thay đổi liên tục nhưng lỗi hồi quy tăng, triển khai đáng sợ | Bổ sung XP: kiểm thử tự động, TDD phù hợp, CI, refactoring, phát hành nhỏ | Bộ kiểm thử có đáng tin, nhóm có thời gian cải thiện thiết kế không? |
| Nhóm đã dùng Scrum nhưng nhiều việc dang dở cuối Sprint | Giữ mục tiêu Scrum, thử trực quan hóa workflow và giới hạn WIP theo Kanban | Các mục backlog có đủ nhỏ, Definition of Done có áp dụng thực sự không? |
| Công việc có quy định, yêu cầu bảo mật hay kiểm toán | Kết hợp phương pháp phù hợp, đưa tiêu chuẩn tuân thủ vào quy trình và Definition of Done | Có bằng chứng kiểm tra, truy vết, phê duyệt cần thiết trong mỗi Increment không? |

Một vài quy tắc ra quyết định hữu ích:

1. **Bắt đầu từ vấn đề hiện có.** Cần khắc phục lỗi hồi quy, trễ do hàng đợi hay thiếu phản hồi khách hàng? Mỗi vấn đề cần cơ chế khác nhau.
2. **Phân biệt nguyên tắc và công cụ.** Có thể dùng user story mà không cần Scrum, dùng bảng trực quan mà chưa áp dụng đủ Kanban, hoặc có Sprint mà vẫn thiếu tính Agile.
3. **Không áp dụng tất cả nghi thức cùng lúc.** Chọn thử nghiệm nhỏ, xác định dấu hiệu thành công, kiểm tra sau vài chu kỳ và điều chỉnh.
4. **Đánh giá cả kết quả lẫn dòng công việc.** Số lượng thẻ xong nhiều chưa chắc tạo giá trị; tính năng có giá trị nhưng thường lỗi cũng không bền vững.
5. **Tôn trọng ràng buộc và năng lực đội ngũ.** Một framework không thay thế kỹ năng kỹ thuật, quyền quyết định sản phẩm hay sự hỗ trợ của tổ chức.

## 11. Những nhầm lẫn phổ biến cần tránh

**“Agile = Scrum.”** Scrum là một cách hiện thực hóa một số nguyên tắc Agile. Agile không yêu cầu mọi nhóm phải dùng Scrum, còn Scrum có thể được áp dụng hình thức mà không tạo phản hồi thực chất.

**“Scrum là chạy Sprint hai tuần và họp Daily.”** Sprint có thể dài tối đa một tháng; giá trị của Scrum đến từ mục tiêu, Increment đạt Done, minh bạch, kiểm tra và thích ứng. Chỉ tổ chức các cuộc họp không đủ.

**“Kanban chỉ là bảng To do / Doing / Done.”** Bảng là điểm khởi đầu để nhìn thấy công việc. Quản lý flow còn cần ranh giới rõ, WIP, chính sách xử lý, phản hồi và cải tiến.

**“Kanban không cần kế hoạch và không thể dự báo.”** Kanban vẫn cần sắp xếp ưu tiên, quản lý năng lực và hẹn kỳ vọng phục vụ; dữ liệu lịch sử giúp dự báo theo xác suất.

**“Lean đồng nghĩa cắt giảm nhân sự hoặc bỏ hết tài liệu.”** Lean tìm cách giảm hoạt động không tạo giá trị trong toàn hệ thống. Việc đầu tư vào năng lực, tài liệu cần thiết, kiểm thử và an toàn có thể giảm chi phí tổng thể.

**“XP nghĩa là cứ viết mã thật nhanh, không cần thiết kế.”** XP đề cao thiết kế đơn giản và cải tiến thường xuyên dựa trên phản hồi từ kiểm thử, tích hợp và cộng tác. Kỷ luật kỹ thuật là điều kiện để thay đổi bền vững.

**“Scrum và Kanban đối lập, chỉ được chọn một.”** Có thể áp dụng thực hành Kanban trong Scrum hoặc chọn Kanban làm phương pháp vận hành chính. Quan trọng là các quy tắc không mâu thuẫn và nhóm hiểu mục đích từng cơ chế.

**“Velocity hay số ticket là năng suất của từng người.”** Velocity chủ yếu hữu ích cho việc lập kế hoạch nội bộ của một nhóm Scrum nếu nhóm dùng ước lượng. Throughput và cycle time mô tả dòng công việc; tất cả đều cần bối cảnh. Không nên dùng các chỉ số này để xếp hạng con người hoặc thay thế kết quả sản phẩm.

**“Agile có nghĩa là được đổi mọi thứ bất kỳ lúc nào.”** Thích ứng đòi hỏi minh bạch về chi phí và mục tiêu. Trong Scrum, phạm vi Sprint có thể được làm rõ, điều chỉnh cùng Product Owner khi học được điều mới, nhưng cần bảo vệ Sprint Goal và Definition of Done.

## 12. Câu hỏi tự kiểm tra

1. Một nhóm tổ chức Sprint đều đặn nhưng đến cuối quý mới có phần mềm sử dụng được. Nhóm đã có những dấu hiệu Scrum nào, và thiếu dấu hiệu Agile nào?
2. Một nhóm hỗ trợ có hàng chục yêu cầu chờ Review dù lập trình viên liên tục bắt đầu việc mới. Thực hành Kanban và góc nhìn Lean nào có thể hữu ích?
3. Nhóm nhận phản hồi người dùng nhanh nhưng mỗi thay đổi đều gây lỗi hồi quy. Những thực hành XP nào nên được cân nhắc?
4. Vì sao Scrum Team có thể dùng bảng Kanban và WIP limit mà vẫn giữ Sprint Goal, Sprint Review và Sprint Retrospective?
5. Khi giảm cycle time, vì sao vẫn phải kiểm tra chất lượng và giá trị người dùng thay vì chỉ đếm việc hoàn thành?

**Gợi ý đối chiếu:** (1) Nghi thức Scrum chưa đủ; cần Increment dùng được và phản hồi sớm. (2) Trực quan hóa hàng đợi, giới hạn WIP, hỗ trợ Review/Test, tìm điểm nghẽn toàn luồng. (3) Kiểm thử tự động phù hợp, TDD, CI, refactoring, cộng tác kỹ thuật. (4) Scrum và Kanban nhắm vào những cơ chế bổ trợ, miễn không làm mất các cam kết Scrum. (5) Hoàn thành nhanh việc ít giá trị hoặc có nhiều lỗi không làm sản phẩm tốt hơn.

## 13. Thuật ngữ và tài liệu đọc tiếp

- **Increment:** phần sản phẩm tích lũy, sử dụng được và đáp ứng Definition of Done.
- **Sprint Goal:** mục tiêu đơn nhất tạo định hướng cho Sprint, giúp nhóm đưa ra quyết định khi phạm vi chi tiết thay đổi.
- **Backlog:** danh sách công việc hoặc nhu cầu đã ghi nhận; trong Scrum, Product Backlog và Sprint Backlog có ý nghĩa, người chịu trách nhiệm và commitment cụ thể.
- **Flow:** cách công việc dịch chuyển qua các bước từ khi bắt đầu đến khi hoàn thành.
- **WIP (Work in Progress):** lượng công việc đã bắt đầu nhưng chưa hoàn tất.
- **Feedback loop:** cơ chế quan sát kết quả, trao đổi và điều chỉnh dựa trên điều đã học.
- **Definition of Done:** mô tả chính thức về trạng thái Increment khi đáp ứng các tiêu chí chất lượng cần thiết.

Để đọc định nghĩa gốc và đối chiếu những phần dễ nhầm, xem [Agile Manifesto](https://agilemanifesto.org/), [Scrum Guide](https://scrumguides.org/), [Kanban Guides](https://kanbanguides.org/) và các tài liệu về **Extreme Programming** của Kent Beck. Các tài liệu này tập trung vào những phạm vi khác nhau; khi áp dụng trong nhóm thực tế, nên giải thích rõ thuật ngữ và các quy tắc đang sử dụng.

**Điều cần mang sang các bài tiếp theo:** Agile giúp xác định *vì sao* cần phản hồi và thích ứng; Lean đặt câu hỏi về *giá trị và toàn hệ thống*; Scrum cung cấp *khung cộng tác và kiểm tra theo Sprint*; Kanban cho thấy *công việc đang chảy thế nào*; XP giúp *phần mềm có thể thay đổi liên tục mà vẫn giữ chất lượng*. Chọn và kết hợp chúng theo vấn đề cần giải quyết, sau đó đo lường, học hỏi và cải tiến.
