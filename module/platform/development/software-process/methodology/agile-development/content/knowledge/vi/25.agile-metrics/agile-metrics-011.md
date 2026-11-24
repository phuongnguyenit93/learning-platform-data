# Tránh dùng chỉ số để xếp hạng cá nhân hoặc ép tăng khối lượng đầu ra

Một nhóm phát triển phần mềm đang cố cải thiện tốc độ giao sản phẩm. Quản lý bắt đầu xuất báo cáo hằng tuần gồm **số commit, story points hoàn thành, số bug đóng và số pull request của từng lập trình viên**, rồi xếp hạng người cao nhất. Ban đầu các con số đều tăng. Sau vài Sprint, Developers chia nhỏ commit để được đếm nhiều hơn; người phụ trách hạng mục khó bị đánh giá thấp; ít ai chủ động hỗ trợ đồng đội vì thời gian pairing không hiện trên bảng; người kiểm thử ngại báo lỗi vì điều đó khiến báo cáo trông xấu. Khách hàng vẫn phải chờ lâu hơn và lỗi sau phát hành tăng.

Đây là nghịch lý thường gặp khi **biến thước đo thành mục tiêu thưởng phạt**. Một chỉ số được tạo ra để nhìn thấy vấn đề có thể mất giá trị khi mọi người bị buộc phải tối ưu chính con số ấy. Trong Agile, mục đích của đo lường không phải chứng minh ai “bận nhất”, mà là **tạo bằng chứng để nhóm hiểu dòng công việc, chất lượng và kết quả người dùng, sau đó lựa chọn cải tiến phù hợp**.

Bài thuộc chương **Đo lường Agile** của module **AGILE_DEVELOPMENT**. Những khái niệm như user story, Product Backlog, Scrum, Kanban, XP, phản hồi sớm và giao Increment đều liên quan tới cách đọc số liệu. Nội dung tập trung vào việc **không dùng chỉ số để xếp hạng cá nhân hoặc ép tăng đầu ra**, đồng thời trình bày cách sử dụng dữ liệu có trách nhiệm ở cấp nhóm và hệ thống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **mục đích học hỏi và cải tiến** của các chỉ số Agile.
2. Phân biệt **activity, output, flow, quality, outcome và impact**, nhận ra giới hạn của từng nhóm.
3. Phân tích vì sao **story points, velocity, số commit, số dòng mã, số bug đóng hoặc số PR** không phải thước đo năng suất cá nhân đáng tin.
4. Mô tả các hiện tượng **làm đẹp số liệu, tối ưu cục bộ, mất hợp tác và che giấu rủi ro** khi chỉ số bị biến thành KPI ép buộc.
5. Đọc đúng **WIP, throughput, work item age, cycle time**, phân phối thời gian hoàn tất và những điều kiện của dự báo.
6. Kết hợp chỉ số dòng công việc với **chất lượng, giá trị người dùng, độ tin cậy và nhịp làm việc bền vững**.
7. Thiết kế một chỉ số có **câu hỏi ra quyết định, định nghĩa tính, nguồn dữ liệu, giới hạn, người sử dụng và cách chống lạm dụng**.
8. Trao đổi về hiệu quả làm việc cá nhân dựa trên **bối cảnh, đóng góp và phản hồi đa chiều** thay vì bảng xếp hạng máy móc.
9. Xây dựng thử nghiệm cải tiến nhỏ và đánh giá cả kết quả mong muốn lẫn tác dụng phụ.

## 2. Câu hỏi đầu tiên: đo để quyết định điều gì?

Một dashboard có thể chứa hàng chục biểu đồ nhưng vẫn vô dụng nếu không giúp nhóm đưa ra quyết định. Trước khi chọn chỉ số, hãy hoàn thành câu:

> **“Chúng ta muốn biết ______ để có thể quyết định ______.”**

Ví dụ:

| Câu hỏi muốn trả lời | Chỉ số hoặc bằng chứng hữu ích | Quyết định có thể đưa ra |
| --- | --- | --- |
| Vì sao PBI thường không đạt Done trong Sprint? | Work item age, thời gian chờ, lý do blocked, DoD | Giới hạn WIP, cải thiện review hoặc test sớm |
| Học viên có đăng ký workshop thành công hơn không? | Tỷ lệ hoàn tất hợp lệ, phản hồi người dùng, ticket hỗ trợ | Giữ, sửa hoặc bỏ một thay đổi giao diện |
| Lỗi có bị phát hiện quá muộn không? | Loại lỗi, thời điểm phát hiện, lỗi lọt sau release | Bổ sung test đúng tầng, tăng phản hồi CI |
| Dự báo giao hàng có đáng tin không? | Phân phối cycle time, throughput lịch sử, biến động khối lượng | Chọn phạm vi và mức cam kết phù hợp |
| Nhóm đang quá tải ở đâu? | WIP, số việc bị ngắt, queue time, phản hồi về tập trung | Ngừng mở thêm việc, xử lý nút thắt |
| Một thay đổi có làm hệ thống kém ổn định? | Error rate, độ trễ, sự cố, dữ liệu nghiệp vụ | Dừng mở rộng, rollback khi an toàn, sửa lỗi |

Nếu không biết ai sẽ dùng chỉ số để ra quyết định, nên cân nhắc **không thu thêm dữ liệu chỉ để “có đủ KPI”**. Thu thập cũng có chi phí: triển khai, bảo trì, quyền riêng tư, diễn giải và khả năng người khác sử dụng sai.

### 2.1. Chỉ số là tín hiệu, không phải kết luận

**Cycle time tăng** có thể do hàng đợi review dài, một item phức tạp, vấn đề môi trường hoặc nhóm đang chủ động xử lý rủi ro quan trọng. Con số cho biết **cần điều tra**, không tự nói ai làm việc kém.

**Lỗi được báo tăng** có thể là chất lượng giảm, hoặc kiểm thử đã phát hiện được vấn đề trước khi tới người dùng. Cần nhìn **mức độ, thời điểm, phạm vi và lỗi lọt**, không tự động kết luận người tìm được nhiều lỗi là người “gây cản trở”.

## 3. Phân biệt activity, output, flow, quality và outcome

Các nhóm chỉ số trả lời những câu hỏi khác nhau:

| Nhóm | Đo cái gì? | Ví dụ | Không chứng minh được điều gì? |
| --- | --- | --- | --- |
| **Activity** — hoạt động | Có bao nhiêu hành động được thực hiện? | Commit, giờ họp, PR, lần chạy test | Giá trị hoặc chất lượng công việc |
| **Output** — đầu ra | Có bao nhiêu thứ được tạo/hoàn tất theo định nghĩa? | PBI Done, bản build, chức năng | Người dùng có đạt mục tiêu không |
| **Flow** — dòng công việc | Công việc chảy qua hệ thống như thế nào? | WIP, throughput, work item age, cycle time | Tự thân không đo giá trị sản phẩm |
| **Quality** — chất lượng | Kết quả có đáng tin và đáp ứng rủi ro? | Lỗi lọt, sự cố, test theo rủi ro, DoD | Mọi nhu cầu người dùng đều đúng |
| **Outcome** — kết quả gần người dùng | Hành vi, trải nghiệm hoặc hiệu quả thay đổi ra sao? | Tỷ lệ đăng ký thành công, giảm ticket | Tác động dài hạn tự động được bảo đảm |
| **Impact** — tác động dài hạn | Lợi ích bền vững cho mục tiêu lớn | Tăng khả năng tham gia workshop phù hợp | Có thể gán nhân quả cho một thay đổi riêng lẻ |
| **Sustainability** — bền vững | Hệ thống và con người có thể duy trì nhịp làm việc? | Quá tải, ngắt việc, khả năng phục hồi | Hiệu quả của mọi cá nhân từ một câu trả lời |

**Không có một chỉ số duy nhất đại diện cho “Agile tốt”**. Nhóm cần một bộ bằng chứng cân bằng nhưng đủ gọn để còn hành động được.

### 3.1. Ví dụ output tăng nhưng outcome xấu

Nhóm chia một PBI lớn thành 20 thẻ rất nhỏ, đóng 18 thẻ, công bố throughput tăng. Nhưng luồng đăng ký thật chưa hoàn chỉnh và người dùng không thấy giá trị mới. Nếu chỉ nhìn số thẻ đóng, nhóm có thể bị thưởng vì **tăng số đơn vị đếm**, không phải vì giao sản phẩm tốt hơn.

### 3.2. Ví dụ activity giảm nhưng kết quả tốt hơn

Hai Developers dành thời gian pairing để sửa một lỗi giao dịch khó; số commit cá nhân giảm. Họ đồng thời chia sẻ kiến thức, bổ sung integration test và ngăn lỗi dữ liệu sau phát hành. Báo cáo activity đơn lẻ có thể làm **đóng góp quan trọng trở nên vô hình**.

## 4. Vì sao xếp hạng cá nhân bằng chỉ số Agile gây méo mó?

Phát triển phần mềm là công việc **phụ thuộc và cộng tác**: một thay đổi có thể cần làm rõ nghiệp vụ, thiết kế, viết mã, review, kiểm thử, vận hành và nhận phản hồi. Kết quả cuối cùng khó quy chính xác cho một người chỉ dựa trên dấu vết công cụ.

### 4.1. Số commit không đồng nghĩa năng suất

Một người có thể:

- Tạo 30 commit để thử nhiều cách sửa một lỗi nhỏ.
- Gộp thay đổi thành 2 commit rõ ràng sau khi pairing.
- Review thiết kế và ngăn lỗi nghiêm trọng nhưng không tạo commit.
- Giảm hàng nghìn dòng mã trùng lặp để hệ thống dễ bảo trì hơn.

Nếu thưởng theo **số commit**, hệ thống khuyến khích tăng hoạt động được đếm thay vì tối ưu khả năng hiểu, kiểm chứng và giao sản phẩm.

### 4.2. Số dòng code có thể thưởng cho độ phức tạp

Viết thêm một bộ abstraction không cần thiết tạo nhiều dòng hơn; loại bỏ code chết và refactor tạo ít dòng hơn. **Dòng mã không phải một đơn vị giá trị ổn định**, và sự khác biệt công nghệ, framework hoặc độ phức tạp khiến so sánh càng thiếu ý nghĩa.

### 4.3. Số bug đóng có thể thưởng cho cách chia và ưu tiên sai

Đóng 20 lỗi hiển thị nhỏ không nhất thiết có giá trị hơn sửa một lỗi làm mất dữ liệu. Người kiểm thử tìm nhiều bug có thể khiến số lỗi mở tăng — đó đôi khi là **phản hồi cần thiết**, không phải thất bại cá nhân.

### 4.4. Số PR được merge không phản ánh chất lượng hợp tác

Một PR phức tạp cần thẩm định bảo mật có thể mất lâu hơn nhiều PR chỉnh tài liệu. Pairing, đào tạo người mới, xử lý incident và cải thiện CI cũng tạo giá trị mà số PR không thể hiện.

### 4.5. Story points không phải “đơn vị sản lượng cá nhân”

Story points thường được nhóm dùng như **một cách ước lượng tương đối**, phản ánh quy mô hoặc độ bất định theo quy ước nội bộ. Chúng không phải giờ công, tiền lương, độ giỏi hay chuẩn thống nhất giữa các nhóm.

Nếu một quản lý yêu cầu “mỗi Developer phải hoàn thành 20 points mỗi Sprint”, nhóm có thể:

1. Nâng cách chấm points để cùng một việc có số lớn hơn.
2. Né việc hỗ trợ, review hoặc cải thiện kỹ thuật vì khó gắn points.
3. Chọn PBI dễ, ngại nhận việc rủi ro nhưng quan trọng.
4. Chuyển phần kiểm thử sang người khác để nhìn như đã hoàn tất.
5. Ngại thừa nhận dự báo sai vì sợ đánh giá hiệu suất.

**Story points là công cụ hội thoại về công việc, không phải điểm thi của con người.**

## 5. Khi một chỉ số thành mục tiêu, hành vi sẽ đổi

Trong quản trị đo lường thường nhắc tới nguyên lý liên quan đến **Goodhart's law**: khi một chỉ số trở thành mục tiêu tối ưu chính, quan hệ giữa chỉ số và điều ta thật sự muốn có thể bị suy yếu. Trong phần mềm, vấn đề không nằm ở con số tự nó, mà ở **cách dùng con số làm động cơ thưởng phạt**.

### 5.1. Chuỗi hệ quả thường gặp

~~~mermaid
flowchart TD
    A["Chọn chỉ số đại diện: số story hoàn tất"] --> B["Biến thành bảng xếp hạng/thưởng phạt"]
    B --> C["Mọi người tối ưu thứ được đếm"]
    C --> D["Chia giả việc, né rủi ro, giấu lỗi, giảm hỗ trợ"]
    D --> E["Con số tăng nhưng chất lượng/hợp tác có thể giảm"]
    E --> F["Quyết định quản lý dựa trên dữ liệu méo"]
    F --> B
~~~

Không phải mọi mục tiêu đều gây méo mó. Rủi ro tăng khi **một số đo thiếu ngữ cảnh được dùng như đại diện toàn bộ kết quả**, đặc biệt khi quyền lợi cá nhân phụ thuộc trực tiếp vào nó.

### 5.2. Các kiểu “gaming” thường xảy ra

| KPI bị ép | Cách làm đẹp số có thể xuất hiện | Tác dụng phụ |
| --- | --- | --- |
| Số PBI Done | Chia hạng mục thành nhiều thẻ nhỏ hoặc hạ điều kiện Done | Không giao được lát cắt có giá trị |
| Story points/Developer | Nâng điểm ước lượng, nhận việc dễ | Khó dự báo, né rủi ro và phá hợp tác |
| Số bug đóng | Ưu tiên lỗi dễ, đóng rồi mở lại | Lỗi nghiêm trọng kéo dài |
| Tỷ lệ test pass | Xóa/skip test flaky, sửa assert cho xanh | Mất khả năng phát hiện hồi quy |
| Coverage bắt buộc thật cao | Viết test không kiểm chứng điều có ý nghĩa | Tốn chi phí, vẫn lọt lỗi |
| Thời gian review thật thấp | Approve qua loa, bỏ trao đổi khó | Rủi ro thiết kế và bảo mật |
| Độ sử dụng nhân lực 100% | Không để chỗ cho hỗ trợ, học, sự cố | Hàng đợi và kiệt sức |
| Số incident phải về 0 | Giảm báo cáo, đổi cách phân loại | Sự cố vẫn xảy ra nhưng khó nhìn thấy |
| Số deployment tăng | Tạo phát hành không có giá trị hoặc chia giả | Tăng hoạt động mà không có outcome |

### 5.3. Hành vi tốt có thể làm chỉ số xấu đi tạm thời

- Nhóm bắt đầu kiểm thử sớm, số bug phát hiện **tăng**.
- Nhóm ngừng mở việc mới để sửa lỗi tồn, throughput ngắn hạn **giảm**.
- Nhóm giảm WIP, tỷ lệ “ai cũng bận” **giảm** nhưng cycle time cải thiện.
- Nhóm nhận một PBI phức tạp có giá trị, số story Done **ít hơn**.
- Nhóm làm refactor, thời gian chưa tạo tính năng mới **tăng** nhưng lỗi lặp giảm.

**Nếu chỉ số được dùng để phán xét quá nhanh, nhóm có thể bị phạt vì đang làm điều đúng.**

## 6. Đo ở cấp hệ thống và cấp nhóm, không dùng để gán điểm cá nhân

Phần lớn flow metrics có ý nghĩa nhất khi xem **toàn bộ hệ thống tạo và giao giá trị**. Kết quả phụ thuộc vào nhiều yếu tố không thuộc một cá nhân: quy tắc Product Backlog, môi trường kiểm thử, phê duyệt, độ phức tạp, sự cố, phụ thuộc và cách chia PBI.

### 6.1. Ví dụ “năng suất” khó quy về từng người

Giả sử một hạng mục đăng ký workshop gồm:

- Product Owner làm rõ chính sách đăng ký.
- Developer A viết API.
- Developer B cùng A thiết kế giao dịch đồng thời.
- Developer C xây kiểm thử tích hợp.
- Người có chuyên môn bảo mật kiểm tra quyền truy cập.
- Một reviewer khác phát hiện nguy cơ không nhất quán dữ liệu.
- Nhóm vận hành chuẩn bị cảnh báo.

Hỏi “ai tạo ra bao nhiêu phần trăm giá trị” từ số commit là câu hỏi **không có đáp án đáng tin bằng dữ liệu này**. Giá trị được tạo ra bởi **một luồng hợp tác**.

### 6.2. Cá nhân vẫn cần được phản hồi và phát triển

**Không dùng số liệu để xếp hạng cá nhân không có nghĩa bỏ đánh giá hiệu quả làm việc.** Phản hồi nghề nghiệp có thể dựa trên:

- Chất lượng quyết định kỹ thuật và cách xử lý rủi ro có bằng chứng.
- Khả năng giao công việc phù hợp vai trò và mức hỗ trợ sẵn có.
- Mức độ hợp tác, review, mentoring, chia sẻ kiến thức.
- Trách nhiệm khi xảy ra sự cố hoặc khi có thông tin bất lợi.
- Năng lực học hỏi và cải thiện theo thời gian.
- Quan sát công việc thực, phản hồi nhiều chiều và bối cảnh.

Các tín hiệu từ công cụ **có thể hỗ trợ một cuộc trao đổi cụ thể**, ví dụ giúp một Developer nhận biết mình đang bị chặn quá lâu. Nhưng **không nên tự động chuyển chúng thành bảng điểm hoặc công thức thưởng phạt** thiếu xem xét con người.

### 6.3. Phân biệt trách nhiệm với đổ lỗi

Một Developer cần có trách nhiệm với thay đổi do mình tạo; nhóm cần có cách điều tra, sửa và học từ lỗi. Nhưng nếu tổ chức tính “số bug bị tìm thấy trên code của ai” làm hình phạt, mọi người có động cơ **giấu hoặc chuyển lỗi sang người khác**.

Trách nhiệm phù hợp hướng tới **sửa tác động, minh bạch bằng chứng và cải thiện hệ thống**.

## 7. Scrum và giới hạn của velocity, story points

Scrum là khung thực nghiệm với **Product Goal, Sprint Goal, Increment, các artifact, event và accountability**. Scrum Guide không bắt buộc mỗi Scrum Team phải dùng story points hoặc velocity; nhóm có thể dùng nhiều phương pháp dự báo dựa trên dữ liệu phù hợp.

### 7.1. Velocity là gì khi nhóm chọn sử dụng?

Trong một số nhóm, **velocity** là lượng story points của các PBI **đã đạt Definition of Done** trong một Sprint, tính theo hệ thống ước lượng nội bộ.

Ví dụ:

| Sprint | Points của PBI thực sự Done |
| --- | ---: |
| 1 | 18 |
| 2 | 22 |
| 3 | 17 |
| 4 | 21 |

Trung bình mô tả:

\[
\bar{v}=\frac{18+22+17+21}{4}=19{,}5\ \text{points/Sprint}.
\]

Con số này có thể hỗ trợ **thảo luận phạm vi Sprint sắp tới trong cùng bối cảnh**, nhưng không nói Sprint 2 “giỏi nhất” hay từng cá nhân phải đạt 19,5 points.

### 7.2. Vì sao không so velocity giữa các nhóm?

Hai nhóm có thể đánh giá cùng một PBI lần lượt **3 points** và **8 points**, vì thang ước lượng và thông tin nền khác nhau. Nhóm có nhiều test bắt buộc, legacy code hoặc phụ thuộc còn khó đo hơn.

Ngay cả **cùng nhóm**, velocity cũng bị ảnh hưởng bởi:

- Nghỉ phép, on-call, sự cố và hỗ trợ.
- Thay đổi mức chất lượng/DoD.
- Mức độ bất định và số lượng PBI chưa từng làm loại tương tự.
- Cách chia PBI và cách ước lượng.
- Thay đổi đội hình hoặc công nghệ.

**Dùng velocity để xếp hạng hoặc ép tăng thường làm mất ý nghĩa của chính ước lượng.**

### 7.3. Burndown chart cũng không phải bảng thi đua

Một Sprint Burndown có thể giúp nhóm nhìn lượng công việc dự kiến còn lại, nhưng không cho biết mọi PBI có đang thật sự đạt DoD, có gặp nút thắt hay có phản hồi mới cần thay đổi Sprint Backlog.

Nếu buộc biểu đồ phải luôn giảm đẹp, Developers có thể né cập nhật công việc mới phát hiện hoặc bỏ những bước kiểm chứng cần thiết. Scrum khuyến khích **minh bạch, kiểm tra và thích ứng**, không yêu cầu một đường đồ thị lý tưởng.

### 7.4. Cách sử dụng thận trọng

- Dùng dữ liệu của **chính nhóm** để hỗ trợ dự báo, không so con người.
- Ghi rõ thay đổi đội hình, loại việc và tiêu chuẩn hoàn tất.
- Xem **Sprint Goal và Increment có giá trị** trước số điểm.
- Không tự cộng điểm cho code chưa đạt DoD.
- Khi kế hoạch sai, hỏi “điều gì học được?” thay vì “ai làm ít points?”.

## 8. Kanban: bốn thước đo dòng công việc cốt lõi

Kanban giúp nhóm quản lý luồng bằng việc **hiển thị công việc, giới hạn WIP, quy tắc kéo và kiểm tra dữ liệu thực**. Các chỉ số phổ biến gồm:

| Chỉ số | Định nghĩa thực dụng | Câu hỏi hữu ích |
| --- | --- | --- |
| **WIP (Work in Progress)** | Số work item đã bắt đầu theo chính sách nhưng chưa hoàn tất | Có mở quá nhiều việc cùng lúc không? |
| **Throughput** | Số work item hoàn tất trong một đơn vị thời gian | Hệ thống thực sự hoàn tất được bao nhiêu item? |
| **Work item age** | Thời gian một work item đang mở đã đi qua từ lúc bắt đầu | Item nào có nguy cơ chờ quá lâu? |
| **Cycle time** | Thời gian một item đã hoàn tất đi từ điểm bắt đầu tới điểm kết thúc đã định nghĩa | Mất bao lâu để hoàn tất một item theo phân phối thực tế? |

### 8.1. Phải định nghĩa ranh giới đo

Nếu nhóm A tính cycle time từ lúc **bắt đầu code** tới **merge**, còn nhóm B tính từ **bắt đầu PBI** tới **đạt DoD**, hai con số không đo cùng hành trình.

Ngay trong một nhóm, thay đổi định nghĩa Done hoặc cách tách item có thể khiến biểu đồ biến đổi **mà chưa có cải tiến thật**. Mọi phân tích cần ghi:

- Điểm bắt đầu và kết thúc.
- Loại work item được tính.
- Chính sách đối với blocked time và item bị hủy.
- Khoảng thời gian quan sát.
- Những thay đổi trong luồng công việc hoặc tiêu chuẩn hoàn tất.

### 8.2. Throughput không phải “năng suất từng Developer”

Throughput **5 PBI/tuần** không thể chia theo số người để ra năng suất cá nhân nếu các PBI khác nhau độ lớn hoặc phụ thuộc. Nó hữu ích khi hỏi **“Luồng này thường hoàn tất bao nhiêu loại việc trong điều kiện tương tự?”**

### 8.3. WIP là dấu hiệu của lựa chọn hệ thống

Khi 10 PBI được mở nhưng chỉ 2 PBI đạt Done, việc thêm người vào bước phát triển có thể khiến queue kiểm thử phình hơn. Nhóm nên xem **nút thắt và thời gian chờ**, không mặc định Developers thiếu nỗ lực.

## 9. Cycle time phải được đọc như phân phối

Một giá trị trung bình có thể che các item bị kẹt lâu. Ví dụ tám PBI hoàn tất với cycle time (ngày):

~~~text
2, 3, 3, 4, 5, 5, 8, 18
~~~

Trung bình:

\[
\bar{c}=\frac{2+3+3+4+5+5+8+18}{8}=6\ \text{ngày}.
\]

Nhưng **7/8 item hoàn tất không quá 8 ngày**, còn một item mất 18 ngày. Việc chỉ công bố “cycle time trung bình là 6 ngày” bỏ qua trường hợp chờ dài đáng điều tra.

### 9.1. Service Level Expectation (SLE) có điều kiện

Một nhóm có thể dựa trên dữ liệu lịch sử để nói:

> “Trong nhóm PBI có đặc điểm tương tự, khoảng **85% item đã hoàn tất trong không quá 9 ngày** ở giai đoạn quan sát trước.”

Đây là **kỳ vọng dịch vụ mang tính xác suất**, không phải cam kết rằng mọi item chắc chắn xong trong chín ngày. Cần ghi rõ dữ liệu, loại item, tiêu chuẩn Done và bất định. Không nên áp một con số từ tám item nhỏ lên dự án nhiều rủi ro.

### 9.2. Work item age giúp hành động trước khi quá muộn

Cycle time chỉ biết đầy đủ **sau khi item hoàn tất**. Work item age nhìn **item chưa xong**, giúp nhóm phát hiện:

- PBI đang chờ reviewer quá lâu.
- Kiểm thử tích hợp bị chặn bởi môi trường.
- Quy tắc nghiệp vụ chưa được xác nhận.
- Một item khó nhưng chưa ai hỗ trợ.

Khi một item già đi, hãy hỏi **“điều gì cần được tháo gỡ?”** thay vì “người phụ trách có làm đủ nhanh không?”.

### 9.3. Không chuyển việc sang trạng thái khác để làm đẹp age

Nếu nhóm reset ngày bắt đầu mỗi khi chuyển cột hoặc đóng rồi mở lại item, chỉ số work item age/cycle time có thể giảm giả tạo. Cần một chính sách đo nhất quán và nhìn **toàn bộ luồng tạo giá trị**.

## 10. Little's Law: hiểu hàng đợi, không biến thành KPI cá nhân

Trong mô hình dòng công việc ổn định về mặt thống kê, **Little's Law** liên hệ số công việc trung bình trong hệ thống, tốc độ hoàn tất trung bình và thời gian đi qua hệ thống:

\[
\text{WIP trung bình}\approx\text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Ví dụ một luồng tương đối ổn định có throughput **4 item/tuần** và cycle time trung bình **2 tuần**; WIP trung bình có thể xấp xỉ:

\[
4\times2=8\ \text{item}.
\]

### 10.1. Điều kiện cần hiểu

Quan hệ này chỉ có ý nghĩa khi:

- Ranh giới hệ thống và đơn vị đo nhất quán.
- Dòng vào/dòng ra được quan sát đủ dài, không tích tụ vô hạn.
- Số liệu bình quân đại diện trạng thái ổn định tương đối.
- Không trộn tùy tiện loại việc hoặc những quãng thời gian rất khác nhau.

**Không được lấy công thức để yêu cầu cá nhân “xử lý thêm hai item mỗi ngày”**. Nếu hệ thống đang tắc ở kiểm thử, tăng số item bắt đầu có thể chỉ làm tăng WIP và thời gian chờ.

### 10.2. Diễn giải cải tiến

Giảm WIP không tự động biến mọi vấn đề thành đơn giản. Nhưng với cùng loại việc và chính sách hoàn tất, **hạn chế mở việc mới và ưu tiên hoàn tất** thường là giả thuyết đáng thử để giảm thời gian chờ.

Một thử nghiệm tốt cần đo **cycle time, lỗi, blocked time và kết quả người dùng** trước/sau, không chỉ WIP.

## 11. Dự báo không phải chỉ tiêu bắt buộc tăng sản lượng

Một tổ chức cần dự báo khi có mốc kinh doanh, sự kiện hoặc phụ thuộc. Dữ liệu lịch sử là hữu ích, nhưng dự báo **không đồng nghĩa một lời hứa rằng con người phải làm cho số liệu đạt bằng mọi giá**.

### 11.1. Ví dụ dự báo theo throughput

Giả sử một nhóm hoàn tất trong sáu tuần gần nhất:

| Tuần | Item đạt Done theo chính sách |
| --- | ---: |
| 1 | 4 |
| 2 | 6 |
| 3 | 3 |
| 4 | 5 |
| 5 | 4 |
| 6 | 6 |

Trung bình:

\[
\frac{4+6+3+5+4+6}{6}\approx4{,}67\ \text{item/tuần}.
\]

Nếu còn 20 item gần tương đồng, một phép chia đơn giản đưa ra **khoảng 4,3 tuần ở tốc độ trung bình lịch sử**. Đây **không phải ngày hoàn tất được bảo đảm**, vì item còn lại có thể lớn hơn, nhiều lỗi hoặc bị phụ thuộc.

### 11.2. Làm dự báo đáng tin hơn

- Phân loại item theo độ lớn/loại rủi ro khi có khác biệt đáng kể.
- Nhìn phân phối throughput, không chỉ trung bình.
- Xem mùa vụ, ngày nghỉ, incident, đội hình và chính sách Done.
- Cân nhắc mô phỏng xác suất từ dữ liệu lịch sử khi mẫu đủ và điều kiện phù hợp.
- Đưa ra **kịch bản, giả định và mức tin cậy**, không tạo cảm giác chính xác giả.
- Khi có bằng chứng mới, **cập nhật dự báo công khai**.

**Không dùng dự báo để ép nhóm “bù đủ số item” bằng cách hạ chất lượng hoặc tăng giờ làm kéo dài.**

## 12. Chỉ số chất lượng: điều kiện bảo vệ khi cải thiện tốc độ

Nếu chỉ theo dõi throughput hoặc velocity, nhóm có thể tăng đầu ra bằng cách **đẩy lỗi sang cuối Sprint hoặc sau phát hành**. Vì vậy cần xem cùng các bằng chứng chất lượng.

| Tín hiệu chất lượng | Có thể cho biết điều gì? | Hạn chế |
| --- | --- | --- |
| **Lỗi lọt sau phát hành** | Rủi ro chưa được phát hiện trước khi tới người dùng | Phụ thuộc mức sử dụng và kênh báo lỗi |
| **Lỗi nghiêm trọng còn mở** | Những rủi ro cần xử lý đúng thẩm quyền | Không thể cộng mọi mức độ như nhau |
| **Tỷ lệ phải làm lại** | Công việc quay lại vì hiểu sai, thiếu test, lỗi tích hợp | Một số vòng lặp là học hỏi hợp lý |
| **CI/build failure** | Thay đổi phá bước kiểm chứng | Có lỗi hạ tầng và flaky |
| **Độ tin cậy kiểm thử** | Có thể dùng tín hiệu test để quyết định không | Pass không bao phủ điều chưa kiểm |
| **Coverage** | Phần mã được chạy bởi test | Không đo chất lượng assert hoặc toàn bộ rủi ro |
| **DoD compliance** | Increment có đáp ứng tiêu chuẩn hoàn tất? | Cần DoD phù hợp, không hạ để làm đẹp số |
| **Sự cố và phục hồi** | Hệ thống chịu ảnh hưởng và khôi phục thế nào | Cần ngữ cảnh và phân loại nhất quán |

### 12.1. Nhiều bug được báo có thể là tín hiệu tích cực

Giả sử trước đây nhóm chỉ kiểm thử cuối Sprint, nay đã chạy integration test khi merge. Số bug được phát hiện **trong lúc phát triển** tăng từ 8 lên 15, nhưng lỗi lọt production giảm. Không nên kết luận chất lượng xấu đi chỉ vì “bug count cao hơn”.

Hãy xem **lỗi nằm ở đâu trong vòng đời, mức nghiêm trọng, thời gian sửa và ảnh hưởng người dùng**.

### 12.2. Không đo “bug do từng người gây ra”

Lỗi thường có nhiều nguyên nhân: yêu cầu mơ hồ, thiết kế, môi trường test, phụ thuộc và review. Đếm số bug gắn tác giả commit để xếp hạng có thể dẫn đến:

- Né nhận việc khó hoặc mã legacy.
- Chuyển lỗi sang nhóm khác.
- Giấu phát hiện và không bổ sung test.
- Cãi nhau về “lỗi của ai” thay vì phòng ngừa.

Chất lượng nên được đánh giá **trên hệ thống tạo sản phẩm và ảnh hưởng thực tế**, không bằng bảng phạt số bug cá nhân.

## 13. Chỉ số outcome: liên hệ với giá trị người dùng

Một user story “Là học viên, tôi muốn đăng ký workshop” có thể đã hoàn tất về mặt kỹ thuật, nhưng giá trị vẫn cần được quan sát khi sử dụng.

### 13.1. Giả thuyết outcome

> “Nếu luồng đăng ký được đơn giản hóa và trạng thái xác nhận rõ ràng, học viên đủ điều kiện sẽ hoàn tất đăng ký dễ hơn, ít phải liên hệ hỗ trợ và không gặp lỗi dữ liệu.”

Các tín hiệu:

| Loại | Ví dụ |
| --- | --- |
| **Outcome chính** | Tỷ lệ hành trình đăng ký hợp lệ có xác nhận thành công |
| **Trải nghiệm** | Quan sát người học thực hiện tác vụ, mức hiểu trạng thái |
| **Hỗ trợ** | Ticket “Tôi đã có chỗ chưa?” theo lượng sử dụng |
| **Guardrail chất lượng** | Không đăng ký vượt sức chứa; không lộ dữ liệu |
| **Guardrail vận hành** | Tỷ lệ timeout và độ trễ ở mức chấp nhận |
| **Bằng chứng từ nhóm** | Test đúng rủi ro, phản hồi từ review và vận hành |

### 13.2. Tỷ lệ phải có tử số và mẫu số

Ví dụ:

\[
\text{Tỷ lệ hoàn tất}=
\frac{\text{Số hành trình bắt đầu hợp lệ có đăng ký được xác nhận}}
{\text{Tổng hành trình đăng ký bắt đầu hợp lệ}}\times100\%.
\]

Cần làm rõ retry, hành trình nhiều ngày, yêu cầu hết chỗ, người không đủ điều kiện, bot, dữ liệu thiếu và cách xác nhận trạng thái nguồn sự thật.

Không nên dùng **số click nút** làm số đăng ký thành công vì người dùng có thể bấm nhiều lần sau lỗi.

### 13.3. Outcome và mối quan hệ nhân quả

Tỷ lệ hoàn tất tăng sau khi phát hành có thể do giao diện mới, nhưng cũng có thể do:

- Workshop còn nhiều chỗ hơn.
- Thay đổi nhóm học viên, thiết bị hoặc kênh đến.
- Chiến dịch truyền thông hoặc mùa vụ.
- Logic ghi sự kiện mới đếm khác trước.
- Hệ thống ít lỗi hơn vì đã sửa một dependency.

**Không suy ra nhân quả chỉ từ biến động trước/sau.** Cần quan sát, nghiên cứu hoặc thử nghiệm có thiết kế phù hợp và nêu bất định.

## 14. Chỉ số vận hành và hiệu quả phát hành: đừng xếp hạng cá nhân

Nhóm vận hành phần mềm có thể theo dõi các tín hiệu như **tần suất triển khai, lead time của thay đổi, tỷ lệ thay đổi gây lỗi/sự cố và thời gian phục hồi sau thất bại**, thường xuất hiện trong thảo luận về hiệu năng delivery/operations, cùng với độ tin cậy dịch vụ.

### 14.1. Các tín hiệu phải đọc ở cấp hệ thống

| Tín hiệu | Câu hỏi hệ thống | Không được suy ra |
| --- | --- | --- |
| **Deployment frequency** | Chúng ta có thể đưa thay đổi nhỏ vào môi trường mục tiêu thường xuyên thế nào? | Ai deploy nhiều hơn thì giỏi hơn |
| **Change lead time** | Thay đổi mất bao lâu từ mốc đã định tới môi trường sử dụng? | Người có lead time ngắn nhất viết mã tốt nhất |
| **Change failure rate** | Bao nhiêu thay đổi gây thất bại cần khắc phục theo định nghĩa? | Một cá nhân có tỷ lệ lỗi cao hơn chắc chắn kém hơn |
| **Time to restore service** | Khi có gián đoạn, tổ chức phục hồi nhanh tới mức nào? | Người trực on-call phải sửa mọi sự cố trong một số phút cố định |
| **Reliability/SLO** | Dịch vụ có đáp ứng nhu cầu người dùng và mục tiêu đã thống nhất? | Uptime cao có nghĩa mọi chức năng đều hữu ích |

Những tín hiệu này cần định nghĩa đúng phạm vi, thường là **dịch vụ hoặc đội tạo/vận hành hệ thống**, không phải KPI lương thưởng theo tên người commit.

### 14.2. Ví dụ vì sao so đội cũng dễ sai

Nhóm A vận hành một dịch vụ giao diện rủi ro thấp, có thể deploy vài lần mỗi ngày. Nhóm B quản lý dịch vụ dữ liệu nhạy cảm cần kiểm chứng và điều phối nhà cung cấp; có thể deploy ít hơn nhưng giữ mức tin cậy cao.

So **số lượt deploy** rồi xếp B thấp hơn A bỏ qua mục tiêu, độ phức tạp, trách nhiệm pháp lý và kiến trúc. Thậm chí cùng dịch vụ, việc chia một thay đổi thành ba deployment không tự tạo thêm giá trị.

## 15. Nhịp làm việc bền vững và trải nghiệm Developer

Một nhóm có thể tăng throughput ngắn hạn bằng **làm thêm giờ liên tục, giảm nghỉ ngơi hoặc bỏ việc học**. Đó không nhất thiết là hiệu quả bền vững.

### 15.1. Tín hiệu cần nhìn cùng kết quả

- Số lần bị ngắt vì sự cố hoặc công việc khẩn.
- Thời gian chờ quyền truy cập, môi trường, review và quyết định.
- Khả năng có khoảng tập trung đủ để giải quyết việc khó.
- Dấu hiệu quá tải và nhịp làm việc không thể duy trì.
- Khả năng chia sẻ kiến thức, hỗ trợ người mới và thay thế khi cần.
- Chất lượng build/test và công cụ hằng ngày.
- Mức rõ ràng của mục tiêu, quyền quyết định và ưu tiên.

### 15.2. Đừng dùng khảo sát cảm nhận để xếp hạng

Một khảo sát ẩn danh “Mức độ tập trung bị gián đoạn tuần này?” có thể giúp cả nhóm cải tiến nếu:

- Mục đích và cách sử dụng được giải thích trước.
- Mẫu đủ lớn để hạn chế suy ra danh tính.
- Không ép công khai thông tin cá nhân nhạy cảm.
- Người trả lời không bị trả đũa khi phản ánh vấn đề.
- Kết quả dẫn tới hành động như giảm họp, cải thiện môi trường hoặc chính sách trực.

Ngược lại, lấy kết quả khảo sát của từng người làm tiêu chí thưởng phạt **phá chính khả năng thu phản hồi chân thật**.

### 15.3. Mục tiêu không phải luôn giữ “100% utilization”

Khi mọi người đều kín lịch và có nhiều item đang mở, một yêu cầu khẩn có thể phải chờ rất lâu. Hệ thống cần **đủ khả năng phản ứng với biến động, hỗ trợ, học hỏi và xử lý lỗi**, không chỉ tối đa hóa số giờ “được phân bổ”.

## 16. Bộ chỉ số cân bằng: đủ để học, không nhiều đến mức gây áp lực

Một nhóm không cần hàng chục KPI. Có thể bắt đầu từ **một mục tiêu người dùng**, một hoặc hai chỉ số dòng công việc và một số guardrail chất lượng.

| Câu hỏi | Bằng chứng minh họa | Cách đọc |
| --- | --- | --- |
| **Có tạo kết quả người dùng?** | Tỷ lệ đăng ký hợp lệ thành công; phản hồi trải nghiệm | Outcome, kiểm tra mẫu số và tính đại diện |
| **Có giao được lát cắt hoàn chỉnh?** | PBI đạt DoD/Sprint Goal | Output có chất lượng, không chỉ code complete |
| **Dòng công việc bị kẹt ở đâu?** | WIP, work item age, queue time, cycle time | Điều tra nút thắt, không quy lỗi cá nhân |
| **Chất lượng có được bảo vệ?** | Lỗi nghiêm trọng, lỗi lọt sau release, dữ liệu đúng | Guardrail để tránh tăng throughput bằng cắt kiểm chứng |
| **Khả năng vận hành có ổn?** | Error rate, độ trễ, tình trạng sự cố | Không chấp nhận outcome tăng bằng rủi ro hệ thống |
| **Cách làm có bền vững?** | Khảo sát an toàn, thời gian ngắt, quá tải | Cải thiện hệ thống và nhịp làm việc |

**Chỉ số tốt không nhất thiết tăng mãi.** WIP giảm có thể là tốt; lỗi báo sớm tăng có thể là tốt; throughput ổn định trong lúc chất lượng cải thiện có thể là tiến bộ đáng kể.

### 16.1. Tạo sự cân bằng trước khi đặt mục tiêu

Nếu nhóm muốn giảm cycle time, hỏi:

- Có tăng lỗi sau release không?
- Có mở rộng định nghĩa Done theo cách làm mất chất lượng không?
- Có tăng giờ làm hoặc phụ thuộc cá nhân?
- Người dùng có nhận giá trị sớm hơn không?

Nếu không có các câu hỏi này, một tối ưu cục bộ có thể tạo **nợ chất lượng và mất hợp tác** trong dài hạn.

## 17. Chỉ số phải có “hợp đồng đo lường”

Để chống hiểu sai hoặc lạm dụng, mỗi metric quan trọng nên có một ghi chú định nghĩa.

~~~text
TEN CHI SO:
MUC DICH / CAU HOI CAN QUYET DINH:
DOI TUONG DO: Team / service / product / luong cong viec
DON VI: Item, ngay, ty le, su co, hanh trinh nguoi dung...
DIEM BAT DAU / KET THUC:
TU SO / MAU SO (NEU LA TY LE):
NGUON DU LIEU:
LOAI WORK ITEM / NHOM NGUOI DUNG DUOC TINH:
TRUONG HOP LOAI TRU / RETRY / HUY:
KHOANG THOI GIAN VA TAN SUAT XEM:
GIOI HAN VA DO KHONG CHAC CHAN:
NGUOI SO HUU CHAT LUONG DU LIEU:
QUYET DINH DUOC HO TRO:
GUARDRAIL CAN XEM CUNG:
NHUNG CACH SU DUNG KHONG DUOC PHEP:
MOC XEM LAI DINH NGHIA:
~~~

### 17.1. Ví dụ định nghĩa throughput

**Tên:** Throughput PBI đạt DoD mỗi tuần.

**Ranh giới:** Từ các item được hệ thống xác nhận Done theo chính sách chung; chỉ đếm một lần khi hoàn tất thật. Item bị hủy hoặc tách được ghi theo quy tắc đã thống nhất.

**Dùng để:** Xem năng lực hoàn tất tương đối trong thời kỳ ổn định, hỗ trợ quyết định WIP, dự báo phạm vi.

**Không được dùng để:** Xếp hạng Developers; so teams có DoD hoặc cách chia PBI khác nhau; trả thưởng theo số item.

**Guardrail:** Lỗi sau release, thời gian chờ, sức khỏe nhóm và kết quả người dùng.

**Giới hạn:** Số item không đại diện độ lớn; thay cách chia PBI có thể thay đổi số lượng mà chưa đổi tổng giá trị.

### 17.2. Ví dụ định nghĩa cycle time

**Tên:** Cycle time cho PBI tính từ lúc bắt đầu thực hiện tới lúc đạt DoD.

**Dùng để:** Tìm item có thời gian chờ lớn, đọc phân phối, chọn SLE có căn cứ.

**Không dùng để:** Tuyên bố người A mất 7 ngày nên kém người B mất 3 ngày khi họ làm hai vấn đề khác nhau.

**Giới hạn:** Cần tách loại việc nếu mức độ phức tạp khác đáng kể, ghi thay đổi DoD hoặc thay đổi luồng.

## 18. Quyền riêng tư và sự tin tưởng khi thu thập dữ liệu

Công cụ phát triển thường lưu commit author, thời điểm online, số review, lịch trao đổi và hoạt động bàn phím. **Có dữ liệu không đồng nghĩa tổ chức nên dùng nó để giám sát năng suất cá nhân**.

### 18.1. Nguyên tắc thực hành có trách nhiệm

1. **Mục đích rõ:** Thu dữ liệu để giải quyết câu hỏi gì?
2. **Tối thiểu cần thiết:** Có thể đo hiệu quả luồng ở cấp nhóm mà không lưu lịch sử thao tác chi tiết của từng người không?
3. **Minh bạch:** Người tham gia biết dữ liệu nào được thu và cách dùng.
4. **Phân quyền:** Ai được truy cập dữ liệu thô và báo cáo?
5. **Giới hạn lưu trữ:** Không giữ dữ liệu nhạy cảm vô thời hạn.
6. **Tránh suy diễn:** Không dùng trạng thái online, số keystroke hoặc thời gian mở IDE như bằng chứng năng suất.
7. **Bảo vệ khỏi trả đũa:** Báo cáo lỗi, khó khăn và phản hồi không trở thành lý do trừng phạt người phản ánh.
8. **Tuân thủ chính sách/law áp dụng:** Xem nghĩa vụ về lao động, dữ liệu và quyền riêng tư theo tổ chức, không mặc định một công cụ quản trị được quyền làm mọi thứ.

### 18.2. “Ẩn danh” không tự bảo đảm không thể nhận diện

Một nhóm chỉ có ba người, nếu dashboard hiển thị “người sửa module A vào đêm Chủ Nhật” thì những người trong nhóm có thể đoán được danh tính dù đã bỏ tên. Cần xem **kích thước nhóm, khả năng kết hợp các dữ liệu và mức chi tiết hiển thị**.

### 18.3. Ranh giới giữa quản lý rủi ro và giám sát quá mức

Truy vết ai phê duyệt thay đổi bảo mật hoặc ai thực hiện triển khai là cần thiết cho **audit, ứng phó sự cố và trách nhiệm kỹ thuật**. Nhưng **truy vết phục vụ an toàn** khác với suy ra “người commit lúc 22 giờ chăm hơn người commit lúc 15 giờ”.

Thời điểm hoạt động không cho biết độ khó công việc, hoàn cảnh cá nhân hay đóng góp hợp tác.

## 19. Đặt câu hỏi trong cuộc họp mà không biến số liệu thành công cụ đổ lỗi

Cùng một dữ liệu, cách trao đổi có thể thúc đẩy **học hỏi** hoặc tạo **phòng thủ**.

### 19.1. Cặp câu hỏi so sánh

| Cách hỏi gây áp lực cá nhân | Cách hỏi giúp cải tiến hệ thống |
| --- | --- |
| “Ai có cycle time lâu nhất tuần này?” | “Những hạng mục nào đang già đi và vì sao chúng bị chặn?” |
| “Vì sao A làm ít points hơn B?” | “Sprint Goal đang gặp rủi ro gì và nhóm cần hỗ trợ ra sao?” |
| “Ai làm ra nhiều bug nhất?” | “Loại lỗi nào thường lọt qua kiểm chứng và nên phòng ngừa ở bước nào?” |
| “Tại sao ai cũng không đủ 8 giờ code/ngày?” | “Chúng ta đang mất tập trung bởi phụ thuộc, sự cố hay chuyển ngữ cảnh nào?” |
| “Team này chỉ deploy hai lần, sao team kia mười lần?” | “Chúng ta có thể giảm kích thước lô thay đổi an toàn ở hệ thống này không?” |
| “Làm sao tăng số PBI Done thêm 30% tháng sau?” | “Điều gì đang giới hạn khả năng hoàn tất và kết quả người dùng mong muốn?” |
| “Sao QA tạo thêm 12 bug?” | “Nhờ kiểm thử sớm, chúng ta đã phát hiện rủi ro nào trước khi đến người dùng?” |

### 19.2. Mẫu hội thoại dựa trên dữ liệu

> **Người điều phối:** “Trong ba tuần gần đây, work item age của các PBI chờ review tăng. Chúng ta có dữ liệu nào để hiểu nguyên nhân?”
>
> **Developers:** “Hai PBI liên quan dữ liệu cần chuyên gia review; các PR quá lớn và một reviewer phải trực sự cố.”
>
> **Product Owner:** “Mục tiêu quan trọng nhất là giao luồng đăng ký đúng. Có thể tạm dời bộ lọc phụ để giải phóng năng lực kiểm chứng.”
>
> **Nhóm:** “Tuần tới, thử chia PR nhỏ hơn và tổ chức review sớm các thay đổi dữ liệu. Ta sẽ theo dõi age, lỗi lọt và ảnh hưởng Sprint Goal.”

Cuộc hội thoại này **không né trách nhiệm**, nhưng tránh quy chậm trễ cho một cá nhân khi nguyên nhân có thể nằm ở năng lực hệ thống.

### 19.3. Đừng ép một lời giải thích ngay trên dashboard

Một dấu hiệu bất thường có thể cần điều tra trước khi kết luận. Nếu một nhóm hỏi “vì sao throughput hôm qua giảm?”, câu trả lời hợp lý đôi khi là **chưa đủ dữ liệu**, đặc biệt với mẫu nhỏ hoặc item có độ lớn khác nhau.

## 20. Nhịp kiểm tra chỉ số: đủ thường xuyên để hành động

Chỉ số có chu kỳ phản hồi khác nhau. Quan sát không đúng nhịp có thể khiến nhóm **phản ứng quá mức với nhiễu ngẫu nhiên** hoặc **chậm xử lý rủi ro khẩn**.

| Nhịp/điểm quyết định | Nên xem gì? | Quyết định thường phù hợp |
| --- | --- | --- |
| **Hằng ngày hoặc khi luồng bị tắc** | Work item age, WIP, blocker, CI đỏ, lỗi quan trọng | Giúp hoàn tất việc cũ, sửa lỗi, tháo phụ thuộc |
| **Trong Sprint** | Tiến độ tới Sprint Goal, PBI gần DoD, rủi ro mới | Thích ứng Sprint Backlog trong trách nhiệm Developers |
| **Sprint Review** | Increment đạt DoD, Product Goal, phản hồi người dùng/stakeholder | Product Backlog và ưu tiên tiếp theo |
| **Sprint Retrospective** | Hàng đợi, lỗi lặp, độ tin cậy test, phối hợp | Thử cải tiến cách làm có thể kiểm chứng |
| **Theo tuần/tháng tùy dịch vụ** | Phân phối cycle time, xu hướng lỗi, độ tin cậy release | Sửa nút thắt, điều chỉnh năng lực và quy tắc |
| **Sau sự cố nghiêm trọng** | Tác động, thời gian phát hiện/phục hồi, điều kiện gây lỗi | Ứng phó và cải tiến phòng ngừa ngay, không chờ Sprint |
| **Theo chu kỳ nghiên cứu sản phẩm** | Outcome, trải nghiệm, giữ chân, hành vi thực | Giữ/sửa/bỏ giả thuyết, thay thứ tự backlog |

Không cần bắt mọi người tham gia tất cả cuộc họp. Điều quan trọng là **bằng chứng tới đúng người có quyền và khả năng hành động**.

### 20.1. Dữ liệu hằng ngày không phải điểm danh năng suất

Daily Scrum của Developers nhằm kiểm tra tiến độ tới Sprint Goal và thích ứng kế hoạch. Nó không phải nơi mỗi người phải chứng minh số giờ lao động hoặc số commit trước quản lý.

Nhóm có thể hỏi: **“Hôm nay ta cần phối hợp để PBI nào đạt DoD?”** thay vì “Hôm qua bạn đóng bao nhiêu thẻ?”.

### 20.2. Tránh kết luận từ một ngày xấu

Nếu throughput giảm trong một ngày, nguyên nhân có thể là chưa có item nào hoàn tất ở đúng thời điểm đếm. Xem **xu hướng qua nhiều chu kỳ**, loại việc và rủi ro; không áp chỉ tiêu “phải có ít nhất ba thẻ Done mỗi ngày” gây chia giả công việc.

## 21. Thiết kế dashboard hỗ trợ quyết định thay vì bảng xếp hạng

Một dashboard tốt không nhất thiết có nhiều biểu đồ. Nó cần **trả lời câu hỏi, lộ ra ngoại lệ và kết nối tới hành động**.

### 21.1. Cấu trúc dashboard thực dụng

| Vùng | Nội dung | Người sử dụng | Câu hỏi |
| --- | --- | --- | --- |
| **Mục tiêu giá trị** | Outcome người dùng chính, phản hồi hỗ trợ | Product Owner, Developers, stakeholder | Có giải quyết vấn đề thật không? |
| **Khả năng giao** | Throughput, phân phối cycle time, work item age | Nhóm làm việc, người lập kế hoạch | Luồng bị chờ ở đâu? |
| **Chất lượng** | Lỗi nghiêm trọng, lỗi lọt, trạng thái CI, DoD | Developers, kiểm thử, vận hành | Có đang tăng tốc bằng cách bỏ kiểm chứng không? |
| **Độ tin cậy dịch vụ** | Error rate, latency, sự cố và cảnh báo | Developers, vận hành, sản phẩm | Bản mới có gây hại không? |
| **Năng lực bền vững** | Phản hồi về môi trường, phụ thuộc, quá tải ở mức tổng hợp | Nhóm và người hỗ trợ cải tiến | Điều gì ngăn nhóm học và duy trì nhịp? |
| **Quyết định gần nhất** | Giả thuyết, thử nghiệm, chủ sở hữu, ngày xem lại | Các bên được giao trách nhiệm | Dữ liệu đã dẫn tới hành động gì? |

### 21.2. Những thành phần nên tránh

- Bảng **“Top 10 Developers theo commit”**.
- Danh sách người “đóng bug ít nhất” nhưng không có mức độ/hoàn cảnh.
- Xếp hạng các Scrum Team bằng tổng story points.
- Bảng heatmap giờ online của từng thành viên.
- Đếm mỗi lần review hoặc comment rồi thưởng/phạt.
- Một chỉ số tổng hợp “Agile Score 0–100” không minh bạch cách tính và mục đích.

Các thành phần này dễ khuyến khích **tối ưu dấu vết công cụ thay vì kết quả** và làm giảm sự sẵn sàng báo cáo vấn đề.

### 21.3. Ví dụ sơ đồ quyết định từ dashboard

~~~mermaid
flowchart TD
    A["Tín hiệu thay đổi trên dashboard"] --> B{"Dữ liệu/định nghĩa đáng tin?"}
    B -->|"Chưa"| C["Kiểm tra nguồn, mẫu, ranh giới đo"]
    B -->|"Có"| D{"Có rủi ro nghiêm trọng cho người dùng?"}
    D -->|"Có"| E["Ứng phó ngay theo thẩm quyền"]
    D -->|"Không"| F["Phân tích ngữ cảnh + phản hồi định tính"]
    F --> G["Đề xuất giả thuyết cải tiến nhỏ"]
    G --> H["Thực hiện + đo guardrail"]
    H --> I["Kiểm chứng kết quả và cập nhật quyết định"]
    I --> A
    C --> A
~~~

Dashboard không tạo giá trị nếu nó kết thúc ở bước **“màu đỏ → gọi tên người chịu trách nhiệm”** mà không đưa tới điều tra và cải tiến.

## 22. Tình huống xuyên suốt: nhóm phát triển đăng ký workshop

**Bối cảnh:** Một Scrum Team gồm những người tạo giải pháp từ nghiệp vụ tới kiểm thử và vận hành đang phát triển khả năng tự đăng ký workshop cho học viên. Product Goal hướng tới việc học viên đăng ký đúng chỗ, nhận trạng thái rõ và giảm khối lượng xử lý thủ công.

Quản lý thấy Sprint trước nhóm chỉ đạt **18 story points** thay vì 25 như dự báo, nên muốn:

1. Công bố bảng điểm points và commit của từng Developer.
2. Yêu cầu mỗi người tăng 20% output trong Sprint kế.
3. Tạm dời một số integration tests để “tránh chậm”.
4. Coi số story Done là thước đo thành công chủ yếu.

### 22.1. Phân tích đề xuất

| Đề xuất | Rủi ro | Cách trao đổi thay thế |
| --- | --- | --- |
| Ranking cá nhân bằng points/commit | Điểm không đại diện giá trị; người làm khó, pairing, review bị thiệt | Đánh giá hệ thống, trao đổi trách nhiệm nghề nghiệp theo bối cảnh |
| Ép tăng output 20% | Tăng WIP, né rủi ro, bỏ chất lượng và số liệu bị làm đẹp | Tìm nguyên nhân thời gian chờ, thử cải tiến nhỏ |
| Bỏ integration test | Không phát hiện lỗi giao dịch đồng thời hoặc phân quyền | Chọn lát cắt nhỏ, giữ test rủi ro cao, cải thiện pipeline |
| Chỉ đếm story Done | Dễ chia giả PBI và che outcome | Xem DoD, chất lượng, thời gian giao và kết quả học viên |

Nếu có lỗi **hai học viên tranh chỗ cuối**, một integration test thất bại chính là phản hồi giúp nhóm bảo vệ người dùng. Việc bỏ test để đạt points nhanh hơn là **đổi rủi ro người dùng lấy một KPI đẹp**.

### 22.2. Đặt lại câu hỏi

Nhóm thống nhất câu hỏi thực tế:

> “Làm cách nào học viên nhận được một luồng đăng ký đáng tin **sớm hơn**, trong khi giảm chờ review/tích hợp và giữ chất lượng?”

Từ đó, dữ liệu cần thu không còn xoay quanh **ai làm nhiều**, mà xoay quanh:

- Có bao nhiêu lát cắt **thật sự đạt DoD**?
- PBI nào đang già đi và vì sao?
- Review, test và môi trường chờ bao lâu?
- Những loại lỗi nào phát hiện muộn?
- Học viên có đăng ký thành công và hiểu trạng thái hơn không?
- Team có phải tăng giờ làm để giữ con số không?

### 22.3. Hai thời kỳ quan sát giả định

Dữ liệu dưới đây **chỉ là ví dụ minh họa**, không phải kết quả một nghiên cứu:

| Chỉ số trong mỗi khoảng bốn tuần | Giai đoạn A — trước cải tiến | Giai đoạn B — sau cải tiến |
| --- | ---: | ---: |
| PBI đạt DoD | 18 | 20 |
| Cycle time trung vị (ngày) | 11 | 8 |
| Cycle time ở phân vị cao được quan sát (ngày) | 20 | 14 |
| Hạng mục chờ review/test ở thời điểm cuối kỳ | 9 | 4 |
| Lỗi nghiêm trọng lọt tới production | 4 | 1 |
| Hành trình đăng ký hợp lệ bắt đầu | 400 | 480 |
| Hành trình được xác nhận thành công | 230 | 360 |
| Ticket liên quan trạng thái đăng ký | 24 | 16 |
| Số ngày có làm thêm giờ kéo dài | 8 | 3 |

Lưu ý **chu kỳ đo cần được giữ nhất quán**, loại PBI có thể đã khác và hai thời kỳ không nhất thiết chỉ khác nhau bởi một cải tiến.

### 22.4. Phân tích output

PBI Done tăng từ **18 lên 20 trong bốn tuần**, tăng khoảng:

\[
\frac{20-18}{18}\times100\%\approx11{,}1\%.
\]

Nhưng **không thể kết luận nhóm làm việc hơn 11,1%** vì item có thể khác quy mô, rủi ro và cách chia. Con số chỉ gợi ý khả năng hoàn tất trong bối cảnh được quan sát.

### 22.5. Phân tích flow

Cycle time trung vị giảm từ 11 xuống 8 ngày; nhiều item đi qua luồng nhanh hơn trong giai đoạn B. Tuy nhiên cần:

- Xem ranh giới bắt đầu/kết thúc có đổi không.
- Đối chiếu độ lớn và loại PBI.
- Điều tra item bị chờ review/test.
- Kiểm tra phân vị cao được tính từ đủ số item và cùng phương pháp.

**Một bảng giảm thời gian chờ không chứng minh mọi cá nhân đã gõ mã nhanh hơn.**

### 22.6. Phân tích outcome

Tỷ lệ hoàn tất đăng ký giai đoạn A:

\[
\frac{230}{400}\times100\%=57{,}5\%.
\]

Giai đoạn B:

\[
\frac{360}{480}\times100\%=75\%.
\]

Chênh lệch mô tả là **17,5 điểm phần trăm**. Kết quả có vẻ cải thiện, nhưng cần xác minh event, mùa vụ, nguồn người dùng, số workshop còn chỗ và các thay đổi đồng thời.

### 22.7. Phân tích quality và sustainability

Lỗi nghiêm trọng lọt production giảm từ 4 xuống 1, còn số ngày làm thêm giờ kéo dài giảm. Hai xu hướng này có thể hỗ trợ nhận định nhóm cải tiến **khả năng giao bền vững**, nhưng mẫu nhỏ và phương pháp đo cần kiểm tra.

Nếu chỉ đếm PBI Done, ta sẽ bỏ qua phần có thể quan trọng hơn: **người học đăng ký thuận lợi hơn, rủi ro giảm và nhóm ít phải trả chi phí làm thêm giờ**.

## 23. Làm thế nào xác minh cải tiến thay vì chỉ nhìn biểu đồ đẹp?

Giả sử nhóm đã thử:

- Chia PBI thành lát cắt nhỏ có giá trị.
- Giới hạn WIP ở vùng review/test.
- Tổ chức trao đổi ba góc nhìn nghiệp vụ–kỹ thuật–kiểm thử trước khi code.
- Bổ sung integration test cho tranh chỗ cuối.
- Tạo nhịp review sớm và tích hợp liên tục.

### 23.1. Cơ chế nào có thể giải thích kết quả?

| Thay đổi | Cơ chế kỳ vọng | Tín hiệu kiểm tra |
| --- | --- | --- |
| Giảm WIP | Ít công việc chờ hơn, tập trung hoàn tất | Work item age, blocked time, cycle time |
| PBI nhỏ hơn | Nhận feedback sớm, giảm làm lại lớn | Kích thước item, thời điểm đạt DoD, lỗi cuối kỳ |
| Làm rõ nghiệp vụ sớm | Giảm hiểu sai acceptance criteria | Số vòng sửa vì sai yêu cầu, phỏng vấn team |
| Integration test phù hợp | Bắt lỗi dữ liệu sớm hơn | Lỗi tại CI so với lỗi production |
| Review sớm | Rút ngắn thời gian chờ và cải thiện thiết kế | Queue time, PR size, lỗi sau merge |

Đây là **giả thuyết về cơ chế**, chưa phải chứng minh nhân quả. Có thể còn tác động từ thay đổi đội hình, nguồn lực, phụ thuộc hoặc độ phức tạp.

### 23.2. Giữ cả tín hiệu không thuận lợi

Nếu sau cải tiến, cycle time giảm nhưng **test flaky tăng**, nhóm cần nói ra. Nếu tập trung PBI nhỏ làm **chi phí tích hợp tăng**, đó là vấn đề đáng điều tra. Một quyết định tốt không loại dữ liệu chỉ vì nó đi ngược câu chuyện thành công.

### 23.3. Kết luận phù hợp

> “Các chỉ số của giai đoạn B cho thấy **xu hướng cải thiện** về thời gian hoàn tất, outcome và lỗi lọt trong mẫu quan sát. Chúng ta sẽ tiếp tục theo dõi qua nhiều chu kỳ, kiểm tra tính nhất quán dữ liệu và giữ guardrail chất lượng, thay vì dùng kết quả để nâng chỉ tiêu points cho từng người.”

Đây là kết luận cẩn trọng và **hướng tới hành động tiếp theo**.

## 24. Khi lãnh đạo muốn mục tiêu định lượng: cách đề xuất có trách nhiệm

Một tổ chức có nhu cầu hợp lý về dự báo, ngân sách và kết quả. **Không xếp hạng cá nhân** không có nghĩa từ chối mọi mục tiêu đo được. Cần phân biệt:

| Loại mục tiêu | Ví dụ | Cách bảo vệ |
| --- | --- | --- |
| **Mục tiêu người dùng** | Nhiều học viên hoàn tất đăng ký hợp lệ hơn | Định nghĩa mẫu số, chất lượng và phân đoạn |
| **Mục tiêu cải thiện hệ thống** | Giảm thời gian chờ review qua thử nghiệm | Xem WIP, lỗi, trải nghiệm đội nhóm |
| **Mục tiêu độ tin cậy** | Giảm lỗi phân quyền hoặc sự cố dữ liệu | Không làm đẹp bằng cách giấu sự cố |
| **Mục tiêu học hỏi** | Kiểm chứng giả thuyết vì sao người dùng bỏ dở | Chấp nhận kết quả “giả thuyết sai” |
| **Mục tiêu dự báo** | Làm rõ xác suất đạt mốc với phạm vi đã chọn | Trình bày giả định, khoảng tin cậy và rủi ro |

### 24.1. Mục tiêu phù hợp khác KPI thưởng phạt ra sao?

Một mục tiêu như “Giảm thời gian chờ review của các PBI có phụ thuộc lớn” có ích nếu:

- Nhóm hiểu **lý do kinh doanh**.
- Có quyền cải tiến quy trình và giải quyết trở ngại.
- Không bị yêu cầu sửa số liệu để đạt ngưỡng.
- Có guardrail chất lượng và nhịp làm việc bền vững.
- Các bên xem lại mục tiêu khi hoàn cảnh thay đổi.

Ngược lại, **“Mỗi Developer phải tăng 20% PR đã merge”** là một proxy dễ bị tối ưu sai, thiếu căn cứ về giá trị.

### 24.2. Khi mục tiêu không đạt

Một cuộc đánh giá tốt cần hỏi:

1. Giả định nào ban đầu không đúng?
2. Có yếu tố mới như sự cố, yêu cầu bảo mật, thay đổi đội hình?
3. Có giảm chất lượng hoặc tăng làm lại không?
4. Nhóm có thực sự được hỗ trợ tháo trở ngại?
5. Cần đổi phạm vi, kế hoạch, thước đo hay cách làm?

**Không đạt một con số trong bối cảnh thay đổi chưa đủ để kết luận cá nhân thiếu nỗ lực.**

## 25. So sánh các nhóm: đôi khi cần, nhưng rất dễ sai

Lãnh đạo có thể muốn biết **nơi nào cần đầu tư**. Việc so sánh các luồng để tìm điểm chờ chung là khác với **xếp hạng hơn kém**.

### 25.1. Những khác biệt phải tính tới

- Mục tiêu sản phẩm và mức độ thay đổi nhu cầu.
- Loại hệ thống: ứng dụng giao diện, dữ liệu cốt lõi, nền tảng, tích hợp.
- Rủi ro an ninh, pháp lý, hiệu năng và vận hành.
- Độ trưởng thành công nghệ và nợ kỹ thuật.
- Tính sẵn sàng của môi trường test, nhà cung cấp và các nhóm phụ thuộc.
- Cách định nghĩa item, cycle time và Done.
- Đội hình, giai đoạn học việc hoặc thay đổi cấu trúc.

### 25.2. So sánh để phát hiện hệ thống hỗ trợ chưa đủ

Ví dụ ba nhóm đều chờ môi trường staging chung. Dữ liệu chờ cao của cả ba nhóm gợi ý **nút thắt hạ tầng cần đầu tư**, không chứng minh nhóm nào thiếu năng lực.

Tương tự, một nhóm có thời gian xử lý sự cố cao vì không được cấp quyền xem log có thể cần **quy trình truy cập an toàn hơn**, không phải một chỉ tiêu cá nhân nghiêm ngặt hơn.

### 25.3. Không biến benchmark thành chuẩn trừng phạt

Benchmark hữu ích khi có định nghĩa và ngữ cảnh tương đồng; nếu không, nó tạo cảm giác chính xác giả. Số liệu ngành cũng không tự trở thành **mức phải đạt cho mọi nhóm, mọi loại hệ thống và mọi thời điểm**.

## 26. Đánh giá đóng góp cá nhân một cách công bằng hơn

Cần phân biệt **đo hiệu quả hệ thống** với **phát triển năng lực nghề nghiệp của một người**.

### 26.1. Những yếu tố có thể thảo luận

| Góc nhìn | Ví dụ minh chứng thích hợp | Cần tránh |
| --- | --- | --- |
| **Giải quyết vấn đề** | Phân tích rủi ro, quyết định thiết kế có lý do, kết quả kiểm chứng | Đếm số vấn đề nhỏ được giao |
| **Chất lượng** | Test phù hợp, review cẩn thận, sửa nguyên nhân sự cố | Đếm bug “gây ra” không xét bối cảnh |
| **Hợp tác** | Pairing, mentoring, hỗ trợ team đạt mục tiêu chung | Phạt vì thời gian không tạo commit |
| **Tự chủ và học hỏi** | Nhận phản hồi, cập nhật kế hoạch, cải thiện kỹ năng | Thưởng người tuyên bố chắc chắn dù thiếu bằng chứng |
| **Ảnh hưởng tích cực** | Giảm điểm chờ, cải thiện kiến thức chia sẻ, bảo vệ người dùng | Tự gán mọi outcome của team cho một cá nhân |
| **Trách nhiệm** | Minh bạch khi gặp lỗi, phối hợp sửa và rút bài học | Tạo môi trường sợ báo cáo vấn đề |

### 26.2. Phản hồi có ví dụ, không phải nhãn người

Thay vì **“Bạn năng suất thấp vì chỉ có 6 commit”**, một trao đổi có thể là:

> “Trong hai hạng mục tích hợp gần đây, những phụ thuộc quan trọng chưa được báo tới nhóm cho đến khi sát mốc. Ta cùng xem trường hợp cụ thể, điều kiện dẫn tới việc đó và cách hỗ trợ bạn làm rõ sớm hơn.”

Ngược lại, nếu người đó đã báo rủi ro sớm nhưng phải chờ quyền truy cập từ bộ phận khác, cuộc trao đổi cần tập trung **tháo nút thắt hệ thống**.

### 26.3. Không lấy việc “khó đo” làm lý do bỏ công nhận

Mentoring, hỗ trợ xử lý sự cố, refactor và xây môi trường test có thể tạo giá trị lớn dù chưa trực tiếp thành PBI sản phẩm. Tổ chức có thể ghi nhận các đóng góp này qua **bằng chứng và phản hồi đa chiều**, không phải ép quy đổi tất cả thành story points.

## 27. Thử nghiệm cải tiến hai Sprint không ép tăng output

**Vấn đề:** Các PBI thường chờ review và integration test sát cuối Sprint; lãnh đạo định yêu cầu tăng velocity.

**Giả thuyết thay thế:** Nếu giới hạn WIP, chia lát cắt nhỏ và cho kiểm thử tham gia từ đầu, nhóm có thể **giao Increment đáp ứng DoD sớm và đáng tin hơn** mà không tăng giờ làm hoặc bỏ kiểm chứng.

### 27.1. Kế hoạch minh họa

| Thời điểm | Hoạt động | Bằng chứng |
| --- | --- | --- |
| Trước Sprint 1 | Chốt định nghĩa Done, ranh giới cycle time, dữ liệu hiện có và bảo vệ quyền riêng tư | Baseline và giới hạn dữ liệu |
| Đầu Sprint 1 | Chọn một luồng có vấn đề, ví dụ đăng ký workshop | Sprint Goal và giả thuyết nhỏ |
| Trong Sprint 1 | Giới hạn WIP, review sớm, tích hợp và test theo lát cắt | WIP, age, blocked time, lỗi |
| Cuối Sprint 1 | Kiểm tra Increment đạt DoD, phản hồi của Product Owner và người dùng nếu có | Output có chất lượng và outcome bước đầu |
| Sprint 2 | Điều chỉnh thử nghiệm dựa trên bằng chứng, không mở rộng máy móc | Độ ổn định, khả năng học hỏi |
| Cuối Sprint 2 | So sánh theo cùng định nghĩa; ghi điều không chắc chắn | Quyết định giữ/sửa/bỏ hoặc tiếp tục thử |

### 27.2. Các guardrail

Không coi thử nghiệm thành công nếu:

- Lỗi nghiêm trọng hoặc lỗi dữ liệu tăng.
- Test bắt buộc bị bỏ hay DoD hạ xuống chỉ để đạt số.
- Người trong nhóm phải làm thêm giờ kéo dài.
- Product Owner không còn nhận Increment có giá trị.
- Số thẻ tăng vì item được chia giả thay vì giao lát cắt hoàn chỉnh.

### 27.3. Câu hỏi Retrospective

1. Điều gì giúp item đạt Done sớm hơn?
2. Có item nào bị chặn bởi quyền quyết định hoặc môi trường?
3. Cách chia PBI có làm phản hồi tới sớm hơn thật không?
4. Lỗi nào vẫn chỉ phát hiện cuối Sprint?
5. Nhịp làm việc có bền vững không?
6. Chúng ta cần **ngừng làm điều gì** thay vì thêm một quy trình mới?

## 28. Mẫu chính sách sử dụng chỉ số Agile

Một chính sách ngắn có thể giúp ngăn mục đích cải tiến bị biến thành giám sát hoặc bảng thi đua.

~~~text
MUC DICH:
  Dung chi so de hieu dong cong viec, chat luong va ket qua nguoi dung.
  Ho tro quyet dinh cai tien va du bao co dieu kien.

DOI TUONG:
  Team / san pham / dich vu / luong cong viec duoc dinh nghia.

NGUYEN TAC:
  [ ] Moi chi so phai gan mot cau hoi ra quyet dinh
  [ ] Cong khai dinh nghia, nguon va gioi han
  [ ] Xem chi so trong boi canh va kem guardrail
  [ ] Ket hop du lieu voi trao doi dinh tinh
  [ ] Khong dung metric proxy lam bang xep hang ca nhan
  [ ] Khong dung story points de so sanh cac nhom
  [ ] Khong ep tang throughput bang cach ha DoD / bo test
  [ ] Khong danh gia ca nhan qua gio online / so keystroke
  [ ] Bao ve du lieu nhay cam va quyen truy cap
  [ ] Cho phep nhom neu van de va sua metric khi bi gaming

KHI CHI SO BAT THUONG:
  1. Kiem tra du lieu va dinh nghia
  2. Hoi boi canh, rui ro, thay doi ve loai viec
  3. Chon gia thuyet cai tien nho
  4. Quy dinh guardrail va nguoi phoi hop
  5. Do tac dong, ghi gioi han va xem lai

QUYET DINH KHONG DUOC DUYET:
  - Thuong/phat truc tiep theo so commit, points, bug, PR
  - Xep hang cong khai nhan su dua tren luong dau ra tho
  - Giau loi hoac sua du lieu de dat chi tieu
  - Cong bo du lieu ca nhan khi khong can cho muc dich do

CHU SO HUU CHINH SACH:
NGAY XEM LAI:
~~~

Đây là **mẫu học tập**, không phải một tiêu chuẩn pháp lý hay quy định bắt buộc của Scrum/Kanban. Chính sách thực tế cần phù hợp tổ chức, thẩm quyền và quy định bảo vệ dữ liệu liên quan.

## 29. Các hiểu lầm và phản ví dụ thường gặp

| Hiểu lầm | Hậu quả có thể xảy ra | Cách hiểu phù hợp |
| --- | --- | --- |
| “Ai nhiều story points hơn thì giỏi hơn” | Chấm điểm thay vì dự báo, né việc khó | Points là ước lượng theo quy ước nhóm, không đo cá nhân |
| “Team có velocity cao hơn thì trưởng thành hơn” | So hai thang đo không tương thích | Xem mục tiêu, Increment và điều kiện từng nhóm |
| “Số commit = năng suất” | Chia commit giả, bỏ mentor/review | Dùng commit để truy vết thay đổi kỹ thuật |
| “Viết nhiều dòng code là đóng góp nhiều” | Tăng code thừa, giảm refactor | Đánh giá cấu trúc, tính đúng và khả năng thay đổi |
| “Ít bug được báo là chất lượng tốt” | Có thể do không ai dám báo lỗi | Xem lỗi lọt, điều kiện phát hiện và độ tin cậy |
| “Coverage cao là bảo đảm không có bug” | Bỏ test rủi ro chưa được nghĩ tới | Coverage là một tín hiệu, không phải chứng nhận |
| “PR được approve nhanh là code tốt” | Review hời hợt | Cân bằng độ trễ và chất lượng review |
| “Mọi người phải luôn bận 100%” | WIP, hàng đợi và kiệt sức tăng | Tối ưu luồng và khả năng phản ứng, không tối ưu bận rộn |
| “Dự báo là hợp đồng phải đạt bằng mọi giá” | Hạ chất lượng và làm đẹp dữ liệu | Dự báo là thông tin có bất định; cập nhật khi học thêm |
| “Throughput tăng thì chắc chắn có giá trị” | Đóng thẻ nhỏ nhưng chưa có hành vi dùng được | Xem DoD, outcome và guardrail |
| “Cycle time cá nhân cho biết năng lực” | Không xét rủi ro, phụ thuộc, độ khó | Dùng cycle time để phân tích luồng |
| “Không được dùng bất kỳ dữ liệu nào trong đánh giá nghề nghiệp” | Bỏ cả phản hồi có bằng chứng | Dữ liệu cụ thể có thể hỗ trợ hội thoại, không là bảng điểm máy móc |
| “Cải tiến nào cũng phải tăng một chỉ số” | Không nhìn chi phí/guardrail | Có thể ưu tiên giảm lỗi hoặc tăng tin cậy khi output ổn định |
| “Khảo sát an toàn tâm lý để chấm nhân viên” | Mất tin tưởng, phản hồi không trung thực | Dùng dữ liệu tổng hợp, bảo vệ quyền riêng tư |
| “Dashboard càng nhiều chỉ số càng tốt” | Không biết hành động từ đâu, tăng gánh nặng | Chọn ít chỉ số gắn câu hỏi và quyết định |
| “Một tuần tốt chứng minh phương pháp luôn tốt” | Kết luận sớm từ mẫu nhỏ | Quan sát nhiều chu kỳ và ghi giới hạn |
| “Bảng xếp hạng sẽ tạo hợp tác bằng cạnh tranh” | Mọi người có động cơ giữ việc dễ và tránh giúp nhau | Khuyến khích mục tiêu chung, trách nhiệm chia sẻ |
| “Giảm tiêu chuẩn Done để tăng tốc là cải tiến” | Chuyển nợ chất lượng sang người dùng | Giữ DoD, giảm phạm vi tùy chọn hoặc cải thiện luồng |
| “Người làm đêm hiệu quả hơn người làm giờ hành chính” | Giám sát quá mức, thiên lệch | Thời gian online không là thước đo đóng góp |
| “Không xếp hạng nên không cần quản lý hiệu quả” | Thiếu phản hồi cá nhân và hướng phát triển | Đánh giá nghề nghiệp bằng minh chứng, bối cảnh và hỗ trợ |

## 30. Bài tập 1 — Bảng xếp hạng Developer có công bằng không?

**Đề bài:** Quản lý xuất bảng:

| Người | Commit | PR merge | Story points gắn với PBI | Bối cảnh |
| --- | ---: | ---: | ---: | --- |
| A | 36 | 12 | 23 | Làm nhiều chỉnh sửa nhỏ và các PBI quen thuộc |
| B | 8 | 3 | 10 | Cùng xử lý lỗi dữ liệu khó và mentoring người mới |
| C | 15 | 5 | 14 | Trực sự cố, sửa build và review các thay đổi bảo mật |

Quản lý định **xếp A tốt nhất, B kém nhất** theo tổng số hoạt động.

### Câu hỏi

1. Những số liệu nào là activity, output hoặc ước lượng, và mỗi chỉ số có giới hạn gì?
2. Vì sao không thể kết luận B kém hơn A?
3. Những đóng góp nào không hiện đầy đủ trên bảng?
4. Nếu A có lỗi nghiêm trọng sau release còn B không có, có thể đảo bảng xếp hạng đơn giản không? Vì sao?
5. Cần bằng chứng nào để thảo luận hiệu quả nghề nghiệp của từng người **mà không tự động gán điểm**?
6. Đề xuất một dashboard cấp nhóm giúp cải tiến luồng thay vì ranking cá nhân.

### Gợi ý trả lời

Không có cơ sở để xếp A/B/C bằng số commit hoặc points vì **loại việc, kỹ năng áp dụng, rủi ro và đóng góp hợp tác khác nhau**. Kể cả số bug, cũng không thể gán toàn bộ chất lượng của một Increment cho một người từ một biến số. Thay vì bảng điểm, nên xem **Sprint Goal, DoD, lỗi lọt, thời gian chờ, khả năng chia sẻ kiến thức và phản hồi công việc cụ thể**.

Không xếp hạng không có nghĩa mọi hành vi đều tốt ngang nhau. Nếu có vấn đề về trách nhiệm, phản hồi cần chỉ ra **trường hợp cụ thể, tác động, bối cảnh và cách cải thiện**, không dựa vào proxy thô.

## 31. Bài tập 2 — Khi throughput tăng nhưng chất lượng giảm

**Đề bài:** Trong hai giai đoạn bốn tuần:

| Chỉ báo | Trước thay đổi KPI | Sau khi thưởng theo số PBI |
| --- | ---: | ---: |
| PBI Done được báo | 24 | 39 |
| PBI thực sự đạt DoD sau kiểm tra lại | 22 | 23 |
| Lỗi nghiêm trọng phát hiện sau phát hành | 2 | 7 |
| PBI phải mở lại vì chưa kiểm chứng | 3 | 14 |
| Work item age trung vị của item đang mở | 6 ngày | 11 ngày |
| Lượng ticket người dùng phải liên hệ hỗ trợ | 15 | 31 |

### Câu hỏi

1. Chỉ báo nào có vẻ cải thiện nếu chỉ nhìn bảng đầu ra?
2. Vì sao khoảng cách giữa **Done được báo** và **thực sự đạt DoD** đáng quan tâm?
3. Có thể xác định chắc thưởng theo PBI **gây ra** mọi vấn đề từ bảng này không?
4. Chọn ba guardrail nên theo dõi cùng throughput.
5. Bạn sẽ đề xuất thay đổi **cách dùng chỉ số** và **quy trình chất lượng** thế nào?
6. Cần trao đổi ra sao để người báo lỗi hoặc phản ánh số liệu sai không bị trả đũa?

### Gợi ý trả lời

Số PBI được báo tăng từ 24 lên 39, nhưng **PBI thật sự đạt DoD chỉ tăng từ 22 lên 23**; lỗi lọt và ticket hỗ trợ lại cao hơn. Đây là dấu hiệu **chỉ số đầu ra đã có thể bị tối ưu sai hoặc tiêu chuẩn hoàn thành không được giữ**.

Từ bảng nhỏ chưa thể kết luận nguyên nhân duy nhất là thưởng theo số PBI vì có thể còn nhiều biến động khác. Tuy nhiên đủ cơ sở để **ngừng dùng KPI đơn lẻ làm bảng thưởng/phạt**, xác minh chính sách Done, kiểm tra nút thắt và điều tra các lỗi nghiêm trọng trước khi ép tăng tốc.

## 32. Bài tập 3 — Dự báo và đọc dòng công việc

**Đề bài:** Một nhóm có throughput sáu tuần: **4, 6, 3, 5, 4, 6 item/tuần**. Có 20 item còn lại trong backlog sắp được lựa chọn. Nhóm có tám PBI đã hoàn tất với cycle time: **2, 3, 3, 4, 5, 5, 8, 18 ngày**.

### Câu hỏi

1. Tính throughput trung bình lịch sử.
2. Tính cycle time trung bình, giải thích vì sao trung bình có thể che item 18 ngày.
3. Nếu chia 20 cho throughput trung bình, kết quả có ý nghĩa như thế nào?
4. Những điều kiện nào có thể làm dự báo thiếu tin cậy?
5. Nếu một item đang mở đã 15 ngày, nhóm nên hỏi gì thay vì chấm năng suất người phụ trách?
6. Có nên dùng một SLE chung cho mọi loại PBI không?
7. Nếu WIP tăng nhanh nhưng throughput không đổi, hiện tượng gì có thể xảy ra với thời gian chờ?

### Gợi ý trả lời

Throughput trung bình xấp xỉ **4,67 item/tuần**; phép chia đơn giản cho 20 item là **khoảng 4,3 tuần trong điều kiện tương tự**, **không phải ngày cam kết**. Cycle time trung bình là **6 ngày**, nhưng phân phối có một item 18 ngày, nên cần xem phần đuôi, tuổi item đang mở và lý do blocked.

Thay loại việc, DoD, đội hình, phụ thuộc hoặc môi trường có thể làm dữ liệu quá khứ ít đại diện. Dữ liệu hữu ích để **cập nhật lựa chọn phạm vi và giải quyết rào cản**, không để ra chỉ tiêu cứng cho từng người.

## 33. Bài tập 4 — Thiết kế metric không khuyến khích làm đẹp số

**Tình huống:** Product Owner muốn biết giao diện mới có giúp học viên đăng ký workshop dễ hơn không; vận hành quan tâm timeout; Developers lo CI lỗi không đáng tin; quản lý muốn một KPI duy nhất.

### Yêu cầu

1. Chọn **một outcome chính** ở cấp sản phẩm, định nghĩa tử số/mẫu số.
2. Chọn **hai guardrail** về chất lượng và vận hành.
3. Chọn **hai chỉ số flow** giúp nhóm phát hiện hàng đợi.
4. Nêu một nguồn phản hồi **định tính**.
5. Chỉ ra một cách chỉ số có thể bị làm đẹp và cách phòng tránh.
6. Ghi rõ ai có quyền ra quyết định thay đổi phạm vi và ai ứng phó sự cố.
7. Nêu khi nào và bằng bằng chứng gì nhóm sẽ **xem lại giả thuyết**.
8. Viết một câu giải thích vì sao **không nên dùng outcome này để chấm từng Developer**.

### Gợi ý trả lời

Một bộ chỉ số hợp lý:

- **Outcome:** Tỷ lệ hành trình đăng ký bắt đầu hợp lệ được xác nhận thành công, định nghĩa rõ retry và thời gian đo.
- **Guardrail:** Không ghi đăng ký vượt sức chứa; tỷ lệ timeout và rủi ro phân quyền không vượt điều kiện chấp nhận.
- **Flow:** Work item age và thời gian chờ review/test; có thể bổ sung cycle time.
- **Định tính:** Quan sát người học xác minh trạng thái, ticket hỗ trợ hoặc phỏng vấn.
- **Chống gaming:** Đối chiếu trạng thái backend với event UI, không dùng số click thay cho đăng ký thực.

Kết quả thuộc về **luồng sản phẩm và bối cảnh sử dụng**, không thể quy chính xác cho một Developer từ số commit hoặc số user story.

## 34. Checklist trước khi đưa một chỉ số vào dashboard

Checklist này giúp đánh giá **mục đích và rủi ro khi sử dụng**, không phải artifact bắt buộc của Scrum hay Kanban.

~~~text
MUC DICH
[ ] Co mot cau hoi / quyet dinh cu the can du lieu?
[ ] Co cach de nhom thuc su hanh dong tu tin hieu?
[ ] Co can them metric moi hay du lieu hien tai da du?

DINH NGHIA / CHAT LUONG DU LIEU
[ ] Don vi do va ran gioi bat dau/ket thuc ro?
[ ] Tu so/mau so ro neu la ty le?
[ ] Loai viec / phan doan nguoi dung / thoi gian do ro?
[ ] Co kiem tra missing, duplicate, retry va thay doi schema?
[ ] Gioi han va do bat dinh duoc ghi?

CAN BANG
[ ] Co outcome hoac muc tieu gia tri?
[ ] Co flow metric de thay nut that?
[ ] Co quality/security/operations guardrail?
[ ] Co xem tac dong toi nhom va nhip lam viec?
[ ] Co ket hop du lieu dinh tinh va phan tich nguyen nhan?

KHONG LAM DUNG
[ ] Khong dung commit / PR / bug / story points de ranking ca nhan?
[ ] Khong dung velocity de so cac nhom?
[ ] Khong de thuong/phat khuyen khich chia gia, giau loi, ha DoD?
[ ] Khong luu/chi tiet hoa du lieu ca nhan qua muc can thiet?
[ ] Co quy trinh xu ly khi metric bi gaming?
[ ] Co noi de nhom phan hoi mot ket luan thieu boi canh?

CAI TIEN
[ ] Co nguoi so huu chat luong du lieu?
[ ] Co thoi diem xem lai metric va gia thuyet?
[ ] Neu metric xau di, uu tien dieu tra truoc khi phan quy trach nhiem?
[ ] Co ghi quyet dinh va kiem chung tac dong sau thay doi?
~~~

Nếu checklist làm nhóm ngại đo lường, hãy bắt đầu đơn giản bằng **một câu hỏi quan trọng, một hoặc hai tín hiệu và một hành động nhỏ**. Mục đích là tạo tin cậy và học hỏi, không sinh thêm một tầng phê duyệt hình thức.

## 35. Câu hỏi tự kiểm tra

1. Vì sao số commit, số dòng code và số PR không phản ánh năng suất cá nhân một cách đáng tin?
2. Phân biệt **activity, output, flow, quality, outcome và impact** bằng ví dụ.
3. Khi một metric trở thành mục tiêu thưởng phạt, những hành vi thích nghi nào có thể làm hỏng giá trị đo?
4. Story points có phải chuẩn năng lực chung giữa Scrum Team không? Vì sao?
5. Scrum Guide có yêu cầu mọi nhóm dùng velocity hay story points không?
6. Velocity có thể giúp nhóm thảo luận dự báo trong điều kiện nào?
7. Bốn flow metrics WIP, throughput, work item age, cycle time khác nhau thế nào?
8. Vì sao work item age giúp phát hiện vấn đề trước khi item hoàn tất?
9. Little's Law cần những giả định gì? Vì sao không nên biến nó thành chỉ tiêu cá nhân?
10. Khi cycle time trung bình giảm, cần kiểm tra những guardrail và điều kiện dữ liệu nào?
11. Một nhóm giảm số bug production nhưng tăng bug phát hiện trong CI có thể đang cải thiện điều gì?
12. Vì sao coverage cao không chứng minh test đã bao phủ mọi rủi ro?
13. DORA-style metrics có thể được lạm dụng ra sao nếu dùng để xếp hạng cá nhân hoặc nhóm khác bối cảnh?
14. Hãy nêu ba biểu hiện của tối ưu cục bộ trong luồng phát triển phần mềm.
15. Vì sao cần đo **nhịp bền vững** cùng throughput?
16. Khi so sánh hai nhóm, những yếu tố nào làm con số không tương thích?
17. “Không xếp hạng bằng metric” có đồng nghĩa “không cần phản hồi hiệu quả cá nhân” không?
18. Một hợp đồng đo lường cần định nghĩa những thông tin gì?
19. Khi dashboard báo chỉ số xấu, bước đầu tiên nên là tìm người chịu trách nhiệm hay kiểm tra nguồn/định nghĩa dữ liệu?
20. Làm sao thiết kế thước đo vừa giúp ra quyết định vừa hạn chế xâm phạm quyền riêng tư?
21. Vì sao cần ghép dữ liệu định lượng với phỏng vấn, review và phản hồi vận hành?
22. Làm sao kiểm chứng một cải tiến giảm cycle time thực sự không làm tăng lỗi hoặc kiệt sức?
23. Khi quản lý yêu cầu tăng story points 20% mỗi người, bạn sẽ đề xuất cách đặt mục tiêu khác thế nào?
24. Vì sao một chỉ số **không thay đổi** vẫn có thể đi cùng một kết quả cải tiến?

## 36. Tổng kết: đo để học và cải tiến, không đo để tạo áp lực sai

Trong Agile, **chỉ số là một công cụ học hỏi**, không phải phép đo đầy đủ giá trị con người. Story points, số commit, số dòng mã, số bug đóng và số PR có thể hữu ích cho một số hoạt động kỹ thuật hoặc truy vết, nhưng **không nên dùng trực tiếp để xếp hạng nhân sự hay ép tăng sản lượng**. Khi làm vậy, tổ chức dễ khuyến khích chia giả việc, né rủi ro, giảm hợp tác và che giấu vấn đề.

Đo lường có trách nhiệm cần:

1. Bắt đầu từ **mục tiêu sản phẩm hoặc câu hỏi cải tiến cụ thể**.
2. Phân biệt **hoạt động, đầu ra, dòng công việc, chất lượng và kết quả người dùng**.
3. Dùng **WIP, throughput, work item age và cycle time** để hiểu hệ thống, không phán xét cá nhân.
4. Đọc **phân phối, ranh giới đo và độ bất định** thay vì chỉ trung bình hoặc một Sprint đơn lẻ.
5. Kết hợp **guardrail chất lượng, độ tin cậy, bảo mật và nhịp làm việc bền vững**.
6. Giữ **định nghĩa Done nhất quán** để không tăng số lượng bằng cách đẩy công việc chưa hoàn tất sang người dùng.
7. Tôn trọng quyền riêng tư, minh bạch mục đích và khuyến khích báo cáo vấn đề trung thực.
8. Đưa dữ liệu trở lại **trao đổi, quyết định, thử nghiệm và kiểm chứng tác động**.

Khi xem một biểu đồ, hãy tự hỏi: **“Con số này đang giúp chúng ta hiểu điều gì về giá trị và dòng công việc, có yếu tố nào bị che khuất, hành vi sai nào nó có thể khuyến khích nếu trở thành KPI, và chúng ta sẽ thử cải tiến gì mà không đánh đổi chất lượng?”** Đó là tinh thần đo lường Agile: **dùng bằng chứng để phối hợp tốt hơn, giao Increment có giá trị và cải tiến liên tục — không dùng số liệu để tạo bảng xếp hạng con người**.
