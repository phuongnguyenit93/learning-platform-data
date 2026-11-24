# Làm rõ chính sách chuyển trạng thái và điều kiện hoàn tất

## 1. Vì sao một bảng Kanban có cột vẫn chưa đủ?

Một nhóm phát triển phần mềm có thể tạo bảng gồm **To Do → In Progress → Review → Done** chỉ trong vài phút. Tuy nhiên, nếu mỗi người hiểu một cách khác nhau về việc thẻ được chuyển cột, bảng sẽ không phản ánh đúng tình trạng công việc:

- Một thành viên đưa thẻ sang **Review** ngay khi tạo pull request; người khác chỉ chuyển sau khi kiểm thử tự động đạt.
- Một người đánh dấu **Done** khi viết xong mã; người khác đợi tích hợp, kiểm thử và phát hành.
- Một thẻ bị chặn được đưa ngược về **To Do** để “không tính WIP”, mặc dù công việc đã bắt đầu.
- Một thẻ ở **Review** nhiều ngày không có người nhận, còn nhóm liên tục kéo thêm việc mới.
- Một lỗi sau khi phát hành được “mở lại” tùy ý, làm thay đổi số liệu throughput đã công bố.

Khi đó, bảng vẫn nhiều màu sắc nhưng không giúp nhóm **kiểm soát luồng công việc (flow)** hay xác định thời điểm có thể bàn giao giá trị.

**Chính sách chuyển trạng thái (workflow policies)** là những quy tắc minh bạch xác định khi nào một hạng mục được nhận, bắt đầu, kéo sang bước tiếp, chờ, xử lý lại hoặc hoàn tất. **Điều kiện hoàn tất** xác định bằng chứng nào cần có trước khi gọi hạng mục là Done. Chúng giúp mọi người hiểu **cùng một sự thật về công việc**, phối hợp dựa trên bằng chứng và cải tiến liên tục.

Trong module **AGILE_DEVELOPMENT**, Kanban hỗ trợ phát triển phần mềm thích ứng bằng cách trực quan hóa công việc, hạn chế việc đang làm dở (WIP), tạo nhịp bàn giao và đo lường dòng công việc. Các chính sách rõ ràng kết nối những mục tiêu này với user story, backlog, phản hồi sớm, thực hành kỹ thuật XP và các cam kết chất lượng mà nhóm đang áp dụng.

> **Thông điệp chính:** Thẻ được chuyển cột vì **điều kiện chuyển trạng thái đã thỏa mãn**, không phải chỉ vì người thực hiện muốn báo rằng mình đang bận hoặc đã hết phần việc cá nhân.

## 2. Kanban quản lý công việc bằng cách nào?

### 2.1. Ba nhóm thực hành cơ bản

Theo cách mô tả trong *The Kanban Guide*, Kanban là chiến lược tối ưu hóa **dòng giá trị** qua quy trình công việc, với ba nhóm thực hành:

1. **Define and visualize a workflow:** định nghĩa và trực quan hóa cách công việc đi từ bắt đầu tới hoàn tất.
2. **Actively manage items in a workflow:** chủ động quản lý các hạng mục đang đi qua luồng, đặc biệt chú ý giới hạn WIP, việc bị chặn và cơ hội hoàn tất.
3. **Improve the workflow:** cải tiến luồng dựa trên quan sát và số đo thực tế.

Kanban **không chỉ là một tấm bảng**. Nhóm cần xác định cách vận hành hệ thống làm việc, thử nó với công việc thật rồi điều chỉnh khi quan sát được sự chờ đợi, tắc nghẽn hoặc lỗi chất lượng.

### 2.2. Definition of Workflow (DoW)

Một **Definition of Workflow (DoW)** mô tả cách nhóm định nghĩa và vận hành dòng công việc. Những yếu tố quan trọng gồm:

| Thành phần | Câu hỏi cần thống nhất | Ví dụ |
| --- | --- | --- |
| **Work items** | Những loại hạng mục nào chảy qua hệ thống? | User story, lỗi sản phẩm, cải tiến kỹ thuật. |
| **Started point** | Khi nào công việc được tính là đã bắt đầu? | Lần đầu được kéo từ Ready vào Developing. |
| **Finished point** | Khi nào công việc rời luồng và được tính là hoàn tất? | Đã kiểm chứng và bàn giao trong môi trường đích theo chính sách. |
| **Workflow states** | Các trạng thái nào tồn tại giữa hai mốc đó? | Developing, Review, Verify. |
| **WIP controls** | Nhóm giới hạn lượng việc chưa xong bằng cách nào? | Tối đa 3 mục ở Developing, 2 ở Review. |
| **Explicit policies** | Quy tắc nhận, chuyển, chặn, xử lý ngoại lệ và hoàn tất là gì? | Chỉ chuyển sang Verify khi review đạt và bản tích hợp dùng để test đã sẵn sàng. |
| **Service Level Expectation (SLE)** | Dự kiến bao lâu một hạng mục có thể hoàn tất, với xác suất nào? | Theo dữ liệu quá khứ: khoảng 85% mục cùng loại hoàn tất trong 8 ngày hoặc ít hơn. |

Đây là **những chính sách của hệ thống công việc**, không phải một tài liệu bất biến. Nhóm có thể bắt đầu gọn, công khai và điều chỉnh dựa trên bằng chứng. Thực hành Kanban không yêu cầu mọi nhóm dùng đúng cùng tên cột, giới hạn WIP hoặc một kiểu tổ chức nhân sự.

### 2.3. Trạng thái làm việc khác trạng thái con người

Cột Kanban nên mô tả **tình trạng của hạng mục trong quá trình tạo giá trị** chứ không chỉ mô tả ai đang nắm ticket.

Ví dụ, “Đang chờ QA” và “Đang kiểm thử” có thể là hai trạng thái khác nhau nếu khoảng chờ là điểm nghẽn quan trọng. Ngược lại, nếu nhóm nhỏ cùng kiểm thử ngay trong bước phát triển, có thể không cần hai cột đó.

Một bảng quá ít trạng thái có thể che giấu thời gian chờ; quá nhiều trạng thái lại tạo công việc hành chính. Chọn độ chi tiết **đủ để nhìn thấy nơi công việc dừng lại và nơi cần quyết định**.

## 3. Vạch rõ điểm bắt đầu, điểm kết thúc và giới hạn hệ thống

Trước khi viết chính sách chuyển trạng thái, hãy thống nhất **đang đo dòng công việc nào**.

### 3.1. Phân biệt yêu cầu chưa nhận làm và công việc đã bắt đầu

Ví dụ nhóm chọn workflow:

~~~mermaid
flowchart LR
    B["Backlog"] --> R["Ready"]
    R --> D["Developing"]
    D --> C["Review"]
    C --> V["Verify"]
    V --> F["Done"]
    C -. "Cần chỉnh sửa" .-> D
    V -. "Không đạt kiểm chứng" .-> D
~~~

**Quy ước minh họa:**

- **Backlog:** nhu cầu hoặc cơ hội chưa được nhận vào luồng thực hiện.
- **Ready:** hạng mục đủ rõ để nhóm có thể kéo vào thực hiện khi có năng lực; chưa tính bắt đầu.
- **Developing:** hạng mục đã được kéo vào làm; **đây là điểm Started**.
- **Review:** kết quả đang chờ/được xem xét theo tiêu chuẩn đã thống nhất.
- **Verify:** đang xác minh hành vi tích hợp và các điều kiện hoàn tất.
- **Done:** hạng mục đã đạt điều kiện bàn giao của workflow; **đây là điểm Finished**.

Nhóm có thể dùng cột trung gian khác. Điều cốt lõi là **điểm Started và Finished rõ ràng, được dùng nhất quán khi ghi số liệu**.

### 3.2. “Done” cụ thể là Done tới đâu?

Từ **Done** có nhiều cách hiểu trong thực tế:

1. Mã đã viết xong.
2. Pull request đã được phê duyệt.
3. Kiểm thử tích hợp hoàn tất trên staging.
4. Sản phẩm sẵn sàng phát hành.
5. Đã phát hành cho người dùng mục tiêu và kiểm chứng hoạt động.

Những mốc đó **không tương đương**. Nhóm phải chọn mốc Finished phù hợp với loại dịch vụ và mục tiêu đo lường.

Trong ví dụ xuyên suốt của bài này, **Done nghĩa là khả năng đã được triển khai và kiểm chứng cho nhóm học viên thử nghiệm trên môi trường đích đã thỏa thuận**, đáp ứng tiêu chí chấp nhận và những yêu cầu chất lượng bắt buộc. Nếu tổ chức chọn Done ở mốc sẵn sàng phát hành, nên **tách rõ số đo hoàn thành nội bộ khỏi thời gian chờ để người dùng thực sự nhận giá trị**.

Không có quy tắc rằng Kanban bắt buộc Done phải là production; nhưng **cần công bố rõ Done là gì**. Nếu vừa đổi định nghĩa Done, không nên so sánh trực tiếp các kỳ dữ liệu trước và sau mà không chú thích.

### 3.3. Ba điểm cần đo nhất quán

Một item có thể có ba mốc đáng quan tâm:

~~~text
Tạo yêu cầu: 01/06
Started:     04/06  (kéo vào Developing)
Finished:    10/06  (đủ điều kiện chuyển Done)
~~~

Nếu nhóm đo theo ngày lịch và quy ước chênh lệch thời điểm:

- **Thời gian từ tạo yêu cầu đến hoàn tất:** 9 ngày (01/06 → 10/06).
- **Cycle time:** 6 ngày (04/06 → 10/06).
- **Thời gian chờ trước khi bắt đầu:** 3 ngày (01/06 → 04/06).

Các con số này chỉ đúng theo **mốc, lịch tính và độ chính xác đã công bố**. Nhóm khác có thể dùng ngày làm việc hoặc timestamp theo giờ. Không được thay đổi mốc tùy tiện để làm đẹp cycle time.

## 4. Viết chính sách rõ ràng cho từng trạng thái

Một chính sách có ích trả lời được: **khi nào được vào cột**, **khi nào được ra**, **ai/nhóm nào xác minh**, **bằng chứng ở đâu**, và **xử lý ngoại lệ thế nào**. Không cần tạo bản kiểm tra đồ sộ cho mọi thẻ, nhưng với điểm chuyển giao quan trọng, quy tắc phải đủ cụ thể để nhiều người áp dụng giống nhau.

### 4.1. Ví dụ chính sách của một nhóm phát triển web

| Trạng thái | Điều kiện để vào | Điều kiện để ra / chuyển tiếp | Lưu ý |
| --- | --- | --- | --- |
| **Backlog** | Nhu cầu được ghi nhận và có nguồn/bối cảnh. | Được ưu tiên và làm rõ đủ để đưa vào Ready. | Có thể hoãn hoặc loại bỏ ý tưởng không còn giá trị. |
| **Ready** | Có mục tiêu người dùng, hành vi chính, ranh giới và phụ thuộc quan trọng đủ rõ; chưa có trở ngại bắt buộc khiến không thể bắt đầu. | Có năng lực theo WIP, người nhận làm hoặc nhóm phối hợp; kéo vào Developing. | Ready không có nghĩa mọi chi tiết đã được biết. |
| **Developing** | Hạng mục được kéo theo chính sách pull và được ghi nhận Started. | Phần thay đổi đủ điều kiện review, kiểm tra cục bộ/CI thích hợp đã chạy; thông tin và cách kiểm chứng được cung cấp. | Không chuyển chỉ vì đã tạo branch hoặc viết một phần mã. |
| **Review** | Có bản thay đổi và bằng chứng kiểm tra sơ bộ để người khác xem. | Các nhận xét chặn được xử lý, người có trách nhiệm review xác nhận đạt; bản tích hợp phục vụ Verify sẵn sàng. | Nếu cần sửa, quay lại Developing hoặc hiển thị rework theo quy ước. |
| **Verify** | Bản đã review và tích hợp vào môi trường kiểm chứng thích hợp. | Tiêu chí chấp nhận, test cần thiết, quyền truy cập, dữ liệu và điều kiện bàn giao đều đạt. | Nếu test thất bại, quay lại làm/sửa với trạng thái rõ ràng. |
| **Done** | Có bằng chứng mọi điều kiện hoàn tất đã đáp ứng và khả năng được bàn giao tại mốc Finished đã chọn. | Ra khỏi workflow. | Nếu phát hiện lỗi sau Done, áp dụng chính sách ghi nhận lỗi/reopen minh bạch. |

Trong một nhóm vận hành có bước phê duyệt an toàn hoặc phát hành bắt buộc, chính sách có thể thêm trạng thái hay điều kiện phù hợp. Không nên tự bỏ qua các kiểm soát tổ chức chỉ vì muốn giảm số cột.

### 4.2. Cách viết quy tắc có thể kiểm chứng

**Mơ hồ:** “Chuyển Review khi dev làm gần xong”.

**Rõ hơn:** “Chuyển Review khi thay đổi được đẩy lên nhánh cần xem, có mô tả hành vi, bằng chứng unit test hoặc kiểm tra phù hợp và không còn lỗi build đã biết khiến người review không thể kiểm tra”.

**Mơ hồ:** “Đánh dấu Done sau khi QA ok”.

**Rõ hơn:** “Done khi kiểm chứng tiêu chí chấp nhận và các kiểm soát bắt buộc đạt trên bản tích hợp, trạng thái dữ liệu đúng, không còn lỗi nghiêm trọng vi phạm chính sách, và khả năng đã đến môi trường/người dùng được quy định cho Finished”.

Quy tắc nên tránh những từ không thể xác minh như **“cơ bản xong”, “khá ổn”, “gần đạt”, “đã có người xem qua”** nếu chúng là điều kiện duy nhất để chuyển cột.

### 4.3. Bằng chứng không cần luôn là giấy tờ thủ công

Bằng chứng có thể là:

- Kết quả pipeline kiểm thử và đường dẫn bản build.
- Pull request và review có ghi nhận quyết định.
- Kết quả contract/integration test ở môi trường được quy định.
- Tình huống người dùng được xác nhận với Product Owner hoặc chủ sở hữu nghiệp vụ.
- Dấu hiệu triển khai thành công và smoke test trên môi trường đích.
- Ghi chú ngắn về ngoại lệ/giả định còn tồn tại.

Nếu công cụ tự động kiểm tra được điều kiện, nhóm có thể dùng tự động hóa để tránh thao tác lặp. Tuy nhiên, **máy báo xanh không thay thế việc xác nhận đúng nhu cầu nghiệp vụ**, nhất là khi kiểm thử chưa bao phủ hành vi quan trọng.

## 5. Chính sách kéo việc (pull) và giới hạn WIP

### 5.1. Pull là nhận việc khi có năng lực

Trong một hệ thống Kanban với **pull**, người ở bước tiếp theo chỉ nhận hạng mục khi có năng lực phù hợp và điều kiện vào trạng thái đã đạt. Điều này khác với việc **push** thêm công việc sang cột kế tiếp dù nơi nhận đang quá tải.

Ví dụ, Review có giới hạn WIP bằng 2. Nếu hiện đang có hai hạng mục ở Review, nhóm không đơn giản đưa thêm hạng mục thứ ba sang cột đó vì “coding đã xong”. Thay vào đó, họ có thể:

- Ưu tiên hỗ trợ giải quyết review đang chờ.
- Kiểm tra có trở ngại hay người duyệt nào trở thành điểm nghẽn.
- Phối hợp hoàn tất một hạng mục rồi mới kéo tiếp.
- Áp dụng chính sách ngoại lệ minh bạch nếu có tình huống thật sự khẩn cấp.

**Giới hạn WIP là chính sách kiểm soát luồng**, không phải thước đo ai làm nhiều hay ít.

### 5.2. Ví dụ WIP limit ở từng bước

| Trạng thái | Giới hạn minh họa | Đang có | Quyết định |
| --- | ---: | ---: | --- |
| Developing | 3 | 2 | Có thể cân nhắc kéo thêm nếu đủ Ready và năng lực. |
| Review | 2 | 2 | Không kéo thêm vào Review theo chính sách thông thường; hỗ trợ giải quyết review. |
| Verify | 2 | 1 | Có chỗ khi item đáp ứng điều kiện vào. |

Các giới hạn **chỉ để minh họa**; không có con số Kanban bắt buộc. Nhóm có thể dùng giới hạn ở cột, cặp cột, toàn workflow hoặc dạng kiểm soát khác, miễn cách hạn chế WIP rõ và hiệu quả.

Một hạng mục **đã Started nhưng bị chặn vẫn là công việc dở dang** nếu nó chưa tới Finished. Không nên tùy tiện bỏ nó khỏi WIP để mở thêm việc và làm báo cáo trông thông suốt. Nếu nhóm có chính sách đặc biệt về cách thẻ bị chặn chiếm chỗ cột, phải công bố cách đo **tổng WIP thực tế** để không làm mất dấu những việc đã bắt đầu.

### 5.3. Khi mọi người bận nhưng ít việc Done

Nếu Developing liên tục nhận việc mới, trong khi Review và Verify ùn tắc, nhóm có thể tăng số hạng mục đang dở và kéo dài cycle time. Một nguyên tắc hữu ích:

> **Stop starting, start finishing** — hạn chế bắt đầu thêm, ưu tiên hoàn tất công việc đang làm.

Nhóm có thể ghép cặp review, hỗ trợ kiểm thử, xử lý blocker hoặc chia lát cắt nhỏ hơn. Nhưng việc hỗ trợ phải dựa trên quyền và năng lực thực tế; một người chưa được cấp quyền production không thể tự bỏ qua phê duyệt để đẩy thẻ sang Done.

## 6. Xử lý thẻ bị chặn và các trạng thái chờ

### 6.1. Blocked là thông tin luồng, không phải “nơi giấu việc”

Một **blocker** khiến công việc không thể tiến tiếp theo cách dự kiến. Ví dụ:

- API đối tác chưa có hợp đồng hoặc môi trường kiểm thử.
- Pipeline không có quyền dùng sandbox.
- Product Owner chưa xác nhận một quy tắc bắt buộc.
- Test tích hợp thất bại nhưng nhóm chưa xác định nguyên nhân.
- Một quyết định liên quan bảo mật/chính sách chưa được phê duyệt.

Thẻ bị chặn nên **hiển thị rõ ở trạng thái hiện tại**, có dấu hiệu và thời gian bắt đầu bị chặn. Cách thể hiện thường là gắn cờ blocked và ghi nguyên nhân; nhóm có thể chọn swimlane riêng nếu phù hợp. Điều quan trọng là không làm mất lịch sử và tuổi hạng mục.

### 6.2. Chính sách bị chặn đề xuất

Khi đánh dấu blocked, ghi tối thiểu:

| Thông tin | Ví dụ |
| --- | --- |
| **Hạng mục / trạng thái** | KBN-17, ở Verify. |
| **Nguyên nhân cụ thể** | Chưa có quyền chạy kiểm thử tích hợp trên sandbox. |
| **Tác động** | Không thể xác minh luồng đăng ký đã tích hợp. |
| **Đã thử** | Test cục bộ và contract test đạt; sandbox bị từ chối truy cập. |
| **Người phối hợp / xử lý** | Kỹ sư tích hợp phối hợp với chủ sở hữu sandbox. |
| **Bước kế tiếp** | Cấp service account đúng quyền, kiểm tra pipeline. |
| **Mốc cập nhật** | Khi có phản hồi hoặc trong lần xem xét luồng tiếp theo. |
| **Điều kiện gỡ blocked** | CI chạy được test tích hợp bắt buộc trên sandbox. |

Sau khi cờ blocked được gỡ, **hạng mục chưa tự động Done**. Nhóm vẫn cần thực hiện những bước kiểm chứng còn thiếu.

### 6.3. Bị chặn khác chờ có chủ đích

Không phải mọi khoảng thời gian một thẻ đứng yên đều là blocker. Có thể nó đang **chờ review theo chính sách** hoặc **chờ một mốc triển khai đã được thỏa thuận**. Tuy nhiên, thời gian chờ vẫn là phần của luồng và có thể cần cải thiện.

Nếu khoảng chờ là yếu tố lớn, nhóm có thể tạo cột **Ready for Review** và **In Review**, hoặc thêm cờ thể hiện đang xếp hàng. Việc tách cột chỉ đáng làm khi giúp nhóm ra quyết định, không phải để có nhiều trạng thái hơn.

### 6.4. Có thể làm việc khác khi bị chặn không?

Có, nếu một phần việc độc lập giúp đạt mục tiêu và không làm WIP vượt kiểm soát. Nhóm có thể chuẩn bị kịch bản, sửa test liên quan hoặc giúp một item khác sắp Done. Nhưng mở thêm nhiều mục chỉ để “không ai ngồi chờ” có thể làm thời gian hoàn tất cả hệ thống dài hơn.

Người hỗ trợ nhóm/Scrum Master (nếu dùng Scrum) có thể giúp phối hợp vượt ranh giới nhóm. Kanban tự nó **không bắt buộc có vai trò Scrum Master**.

## 7. Xử lý làm lại (rework), quay cột và lỗi sau Done

### 7.1. Rework là một phần cần thấy của workflow

Khi Review hoặc Verify phát hiện lỗi, thẻ có thể phải trở về Developing hoặc đi qua một đường xử lý lại. Chính sách cần rõ:

1. Điều kiện nào khiến một hạng mục phải quay lại?
2. Ai xác nhận thông tin và mức độ nghiêm trọng?
3. Bằng chứng lỗi/kiểm thử thất bại được ghi ở đâu?
4. Sau khi sửa, có cần review và verify lại không?
5. Hạng mục có giữ nguyên ID và mốc Started không?

**Ví dụ chính sách:** “Nếu kiểm thử tích hợp không đạt tiêu chí chấp nhận, giữ cùng hạng mục và thời điểm Started, chuyển lại Developing kèm lỗi có thể tái hiện; sau khi sửa phải qua Review/Verify theo chính sách. Không tạo một item mới chỉ để mục cũ được tính Done.”

Hành vi này giúp cycle time phản ánh **toàn bộ công sức và thời gian chờ để hoàn tất hạng mục**, thay vì chỉ phản ánh lượt chuyển trạng thái cuối cùng.

### 7.2. Phân biệt sửa lỗi trước Done với lỗi phát hiện sau Done

| Tình huống | Cách xử lý thường hợp lý | Tác động đến số liệu |
| --- | --- | --- |
| Test thất bại khi item đang ở Verify | Quay lại sửa trong cùng item, chưa Done. | Cycle time tiếp tục tính từ Started ban đầu. |
| Reviewer phát hiện sai hợp đồng API | Chuyển lại Developing hoặc trạng thái rework theo chính sách. | Không tăng throughput vì chưa đạt Finished. |
| Sản phẩm đã giao đúng điều kiện Done, sau đó lộ lỗi mới | Ghi incident/defect mới, liên kết item gốc; xử lý theo mức nghiêm trọng. | Không tùy tiện sửa lại lịch sử số item đã Finished. |
| Do đánh dấu nhầm, item thực tế chưa đạt điều kiện Done | Sửa dữ liệu theo chính sách audit rõ, nêu lý do. | Cần điều chỉnh số liệu có liên quan và ghi rõ bản sửa. |

Kanban không áp một quy tắc duy nhất về cách **reopen**; nhóm phải định nghĩa cho phù hợp thực tế. Điểm quan trọng là **không đếm một việc hai lần** hoặc xóa thời gian chờ chỉ để cải thiện biểu đồ.

### 7.3. Đừng gọi lỗi chất lượng là “tính năng mới”

Nếu mục tiêu ban đầu là “học viên không thể đăng ký vượt sức chứa” nhưng test phát hiện trường hợp tranh chỗ cuối vẫn sai, đó là vấn đề của hành vi/tiêu chuẩn đã cam kết. Không thể gọi item Done rồi tạo user story “sửa vượt sức chứa” sau chỉ để bảo vệ tiến độ.

Ngược lại, một đề nghị mới như **SMS nhắc lịch** có thể là khả năng bổ sung độc lập. Nó nên được đánh giá và xếp thứ tự riêng, không lặng lẽ làm phình item đăng ký hiện tại.

## 8. Ngoại lệ: việc khẩn cấp, hạn chót và thay đổi chính sách

### 8.1. Tại sao cần chính sách ngoại lệ?

Trong thực tế, một sự cố lộ dữ liệu hoặc lỗi gián đoạn sản xuất cần được xử lý sớm hơn luồng ưu tiên thông thường. Nếu không có cách vận hành rõ, mọi bên liên quan có thể dán nhãn **“gấp”**, phá WIP limit và khiến công việc thường xuyên bị chen ngang.

Một chính sách ngoại lệ có thể quy định:

- **Điều kiện kích hoạt:** loại sự cố, ngưỡng tác động hoặc deadline có hậu quả thực.
- **Người có thẩm quyền xác nhận:** ai được quyết định ưu tiên khẩn cấp?
- **Tác động WIP:** ưu tiên hoàn tất/dừng việc nào, có cho phép vượt một giới hạn cụ thể trong trường hợp thật sự cần không?
- **Cách hiển thị:** swimlane khẩn cấp, cờ ưu tiên và thời điểm bắt đầu.
- **Cách báo tin và kết thúc:** thông báo stakeholder, tiêu chí khôi phục/kiểm chứng và xem lại nguyên nhân.

Ví dụ, một lỗi bảo mật đang bị khai thác phải đi theo **quy trình ứng cứu sự cố thích hợp**, không chờ đủ điểm WSJF hoặc bị giữ ở Backlog chỉ vì Review đã đủ 2 thẻ.

### 8.2. Class of service không phải điều kiện bắt buộc cho mọi đội

Một số hệ thống Kanban dùng **classes of service**, chẳng hạn:

| Nhóm minh họa | Điều kiện | Chính sách gợi ý |
| --- | --- | --- |
| **Standard** | Công việc bình thường, không có hạn chót đặc biệt. | Kéo theo thứ tự và năng lực đã thống nhất. |
| **Fixed date** | Có mốc bên ngoài với hậu quả nếu trễ. | Làm rõ mốc, phụ thuộc và lập kế hoạch đủ sớm. |
| **Expedite** | Sự cố nghiêm trọng cần phản ứng tức thời. | Có người xác nhận, ưu tiên theo quy trình khẩn cấp, minh bạch việc bị ảnh hưởng. |
| **Intangible** | Giá trị bảo vệ tương lai khó nhìn thấy ngay. | Xem tác động nợ kỹ thuật, bảo trì, cải tiến nền tảng. |

Các lớp trên là **cách tổ chức chính sách tùy chọn**, không tự tạo trách nhiệm mới trong Scrum hay Kanban. Tránh dùng nhãn “expedite” để lách tiêu chuẩn chất lượng, phê duyệt bảo mật hoặc mọi WIP control.

### 8.3. Thay đổi chính sách cũng phải minh bạch

Khi quy tắc chuyển trạng thái gây tắc nghẽn, nhóm có thể thử sửa. Ví dụ, thay việc chờ một reviewer cố định bằng review có người thay thế được đào tạo phù hợp. Nên ghi:

1. Vấn đề và dữ liệu dẫn đến thay đổi.
2. Chính sách cũ và chính sách mới.
3. Ngày bắt đầu áp dụng.
4. Kết quả kỳ vọng và cách đo.
5. Điều kiện xem lại hoặc hoàn tác nếu có rủi ro.

Không tự ý đổi quy tắc giữa chừng để hợp thức hóa một hạng mục chưa đạt điều kiện hoàn tất.

## 9. Định nghĩa điều kiện hoàn tất bằng hành vi và chất lượng

### 9.1. “Finished” của workflow và Definition of Done

Trong Kanban, **finished point** là mốc của Definition of Workflow: nó định nghĩa khi nào hạng mục rời luồng được đo. **Definition of Done (DoD)** là một cách mô tả tiêu chuẩn chất lượng của phần sản phẩm hoàn tất, được dùng chính thức trong Scrum và có thể được các nhóm khác áp dụng như một thực hành hữu ích.

Hai khái niệm liên hệ nhưng **không phải một**:

- **Finished point:** ranh giới đo và bàn giao trong workflow.
- **DoD hoặc chính sách chất lượng tương đương:** tiêu chuẩn cho phần sản phẩm được gọi là hoàn tất.
- **Acceptance criteria:** điều kiện riêng của một hạng mục về hành vi người dùng hoặc nghiệp vụ.
- **Release policy:** điều kiện phát hành hoặc kích hoạt cho đối tượng sử dụng khi có quy trình phát hành riêng.

Nếu workflow chọn Finished là sau khi người dùng thử có thể sử dụng, chính sách Done cần bao hàm việc đã triển khai/kiểm chứng ở môi trường đó. Nếu Finished dừng ở giai đoạn chờ release, đó là một loại số đo khác; không được tuyên bố đã giao giá trị tới người dùng khi còn chờ phát hành.

### 9.2. Ví dụ acceptance criteria cho đăng ký khóa học

**User story:**

> Là học viên đã đăng nhập, tôi muốn đăng ký một khóa học miễn phí còn chỗ để tham gia học mà không cần nhờ nhân viên hỗ trợ.

Các trường hợp chấp nhận có thể mô tả gần cú pháp Gherkin:

~~~gherkin
Feature: Học viên đăng ký khóa học miễn phí

  Scenario: Đăng ký thành công
    Given học viên A đã đăng nhập và chưa đăng ký khóa X
    And khóa X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A nhận được trạng thái xác nhận thành công

  Scenario: Gửi lại yêu cầu đăng ký
    Given học viên A đã có đăng ký hiệu lực cho khóa X
    When A gửi lại yêu cầu đăng ký khóa X
    Then hệ thống không tạo đăng ký hiệu lực thứ hai
    And A nhìn thấy trạng thái đăng ký hiện tại

  Scenario: Hai học viên cùng chọn chỗ cuối
    Given khóa X chỉ còn một chỗ
    When hai học viên hợp lệ đồng thời yêu cầu đăng ký
    Then tối đa một yêu cầu được xác nhận
    And tổng đăng ký hiệu lực không vượt sức chứa

  Scenario: Truy cập không đúng quyền
    Given người dùng B không có quyền xem đăng ký của A
    When B yêu cầu xem đăng ký của A
    Then hệ thống từ chối truy cập
~~~

Ví dụ Gherkin chỉ nêu hành vi kỳ vọng. Nó chưa phải bài kiểm thử chạy được nếu chưa có mã và môi trường phù hợp. Khi cần, nhóm xác nhận quy tắc với Product Owner/người có thẩm quyền rồi tự động hóa những kiểm chứng quan trọng.

### 9.3. Điều kiện Done minh họa cho nhóm web

Giả sử Finished được định nghĩa là **đã bàn giao cho nhóm học viên thử nghiệm hợp lệ trên môi trường đích**. Chính sách Done có thể gồm:

- [ ] Hành vi nghiệp vụ và trường hợp lỗi quan trọng đáp ứng acceptance criteria.
- [ ] Mã, giao diện, API và dữ liệu đã được tích hợp ở phiên bản dùng để bàn giao.
- [ ] Build, kiểm thử tự động và kiểm thử tích hợp cần thiết đã chạy đạt.
- [ ] Đã xác minh xử lý lặp, giao dịch đồng thời, quyền truy cập và dữ liệu cá nhân theo rủi ro.
- [ ] Không còn lỗi nghiêm trọng vi phạm chuẩn hoàn tất và chính sách an toàn.
- [ ] Thay đổi đã qua review thích hợp, những ý kiến chặn đã được xử lý.
- [ ] Tài liệu/hợp đồng API/cấu hình, log và hướng dẫn vận hành chịu ảnh hưởng được cập nhật khi cần.
- [ ] Đã triển khai đến môi trường đích theo quy định, smoke test hoặc kiểm tra tương đương đạt.
- [ ] Có bằng chứng kiểm chứng và người phụ trách đã cập nhật trạng thái công việc.

Đây là **chính sách ví dụ**, không phải checklist Kanban áp dụng đồng loạt. Những công việc như cập nhật tài liệu hoặc thay đổi cấu hình có thể có loại bằng chứng khác so với user story phát triển tính năng; nhóm cần quy tắc theo loại công việc mà vẫn giữ các chuẩn tổ chức bắt buộc.

### 9.4. “Done” và “Accepted” không nhất thiết là hai cột

Nếu PO hoặc người dùng đại diện cần xác nhận một quy tắc nghiệp vụ, sự xác nhận ấy phải xuất hiện ở thời điểm phù hợp. Nhưng không nhất thiết mọi hạng mục đều chờ PO bấm nút duyệt trước khi được Done. Nhóm cần phân biệt:

- **Làm rõ hành vi trước và trong lúc xây**, khi kiến thức nghiệp vụ ảnh hưởng thiết kế.
- **Kiểm chứng hành vi và chất lượng** ở các bước review/verify.
- **Kiểm tra giá trị sau bàn giao**, để quyết định cải tiến sản phẩm tiếp theo.

Với các thay đổi có quy định phê duyệt bắt buộc, chính sách cần nêu rõ bước phê duyệt và người có quyền. Với những điều không bắt buộc, tránh biến một chữ ký thành điểm nghẽn không mang lại thêm chất lượng.

## 10. Tình huống xuyên suốt: bảng Kanban cho nền tảng học trực tuyến

### 10.1. Bối cảnh

Một nhóm có luồng việc liên tục: sửa lỗi đăng ký, phát triển tính năng, bảo trì tích hợp và hỗ trợ thử nghiệm. Nhóm chọn Kanban để nhìn thấy công việc đi qua phát triển, review, kiểm thử và bàn giao.

**Mục tiêu làm việc:** hoàn tất những lát cắt đăng ký khóa học đáng tin cậy và đưa chúng tới người dùng thử sớm, thay vì mở nhiều task nhưng ít khả năng thật sự sử dụng được.

Nhóm thống nhất:

| Chính sách | Quy ước minh họa |
| --- | --- |
| **Đầu vào** | Backlog được sắp thứ tự theo giá trị, rủi ro, phụ thuộc và mức cấp thiết. |
| **Ready** | Hành vi và ranh giới đủ rõ; nếu còn giả định trọng yếu thì có bước làm rõ tương ứng. |
| **Started** | Khi item được pull vào Developing. |
| **WIP** | Developing tối đa 3, Review tối đa 2, Verify tối đa 2. |
| **Blocked** | Giữ nhận diện và tuổi item, có nguyên nhân, người phối hợp và điều kiện gỡ chặn. |
| **Rework** | Không tạo item mới khi sửa lỗi phát hiện trước Finished. |
| **Finished/Done** | Đạt tiêu chí chấp nhận và chất lượng bắt buộc, đã bàn giao tới môi trường thử nghiệm đích, có kiểm chứng. |
| **Nhịp xem xét** | Theo dõi hạng mục già/blocked mỗi ngày; xem lại rủi ro, chính sách và dữ liệu flow định kỳ. |

### 10.2. Bảng tại một thời điểm

| Hạng mục | Trạng thái | Tuổi từ Started | Tình huống |
| --- | --- | ---: | --- |
| KBN-01 — Chống đăng ký trùng | Verify | 7 ngày | Test cạnh tranh chỗ cuối chưa đạt. |
| KBN-02 — Hiển thị khóa còn chỗ | Review | 5 ngày | Đang chờ người review đúng chuyên môn. |
| KBN-03 — Thông báo lỗi hết chỗ | Developing | 2 ngày | Có thể tiếp tục phát triển. |
| KBN-04 — Contract test API sức chứa | Review | 4 ngày | Đã có phản hồi yêu cầu chỉnh sửa. |
| KBN-05 — Bộ lọc theo chủ đề | Ready | Chưa started | Có thể kéo khi năng lực cho phép. |

**Nhận xét về luồng:**

- Review đang có **2/2** item, không nhận thêm theo chính sách thông thường.
- KBN-01 ở Verify 7 ngày và test thất bại; việc cần làm là xử lý đúng lỗi, **không chuyển sang Done**.
- KBN-05 đã Ready nhưng không phải vì thế phải bắt đầu ngay; nhóm cân nhắc hỗ trợ hoàn tất KBN-01, KBN-02 và KBN-04 trước.
- Nếu KBN-01 chuyển về Developing để sửa, item giữ thời điểm Started cũ và tiếp tục chiếm WIP theo vị trí mới.

Các tuổi hạng mục chỉ là dữ liệu minh họa; khi làm thật phải dùng timestamp và lịch tính thống nhất.

### 10.3. Một thẻ đi từ Ready đến Done

**KBN-03 — Thông báo lỗi khi khóa vừa hết chỗ**

1. **Backlog → Ready:** Product Owner xác nhận hành vi: khi khóa vừa hết chỗ sau lúc học viên mở trang, hệ thống không ghi đăng ký và hiển thị lời nhắc rõ. Nhóm có ví dụ để kiểm chứng.
2. **Ready → Developing:** còn năng lực theo WIP; người thực hiện kéo thẻ và ghi mốc Started.
3. **Developing → Review:** thay đổi được tích hợp vào nhánh review thích hợp; kiểm tra sơ bộ và mô tả trường hợp lỗi đủ cho reviewer.
4. **Review → Verify:** nhận xét chặn được giải quyết, review đạt; bản tích hợp có thể chạy kiểm thử.
5. **Verify:** test trường hợp khóa hết chỗ, dữ liệu không bị thay đổi sai, quyền truy cập và regression cần thiết đều đạt.
6. **Verify → Done:** phần thay đổi được bàn giao trên môi trường thử nghiệm đích, kiểm chứng đạt các chính sách Done và ghi mốc Finished.

Khi học viên dùng thử phản hồi rằng nội dung vẫn khó hiểu, nhóm có thể đưa **cải tiến mới** vào backlog. Điều đó không nhất thiết làm item cũ “chưa Done” nếu trước đó nó đã đáp ứng chính sách Done và acceptance criteria thật sự được thống nhất; cần phân biệt **phản hồi sản phẩm tiếp theo** với **lỗi vi phạm điều kiện đã cam kết**.

### 10.4. Một thẻ không được phép “nhảy” sang Done

**KBN-01 — Chống đăng ký trùng** có test đơn vị xanh nhưng kiểm thử tích hợp vẫn tạo hai bản ghi khi nhận request đồng thời.

Đội không nên:

- Đánh dấu Done vì đã sửa xong trường hợp một người dùng.
- Xóa thẻ khỏi Verify rồi tạo item mới để số liệu cycle time đẹp.
- Tạm bỏ test cạnh tranh mà không thay đổi ranh giới nghiệp vụ/chính sách đúng thẩm quyền.
- Đưa phần lỗi sang “sẽ sửa sau” và công bố Increment an toàn.

Thay vào đó, giữ bằng chứng lỗi, chuyển về bước sửa theo chính sách, trao đổi với người chịu trách nhiệm kỹ thuật và Product Owner về tác động, bổ sung kiểm thử hồi quy, rồi chỉ Done khi kiểm chứng điều kiện đã đạt.

### 10.5. Ví dụ bản chính sách ngắn có thể đặt ngay cạnh bảng

~~~yaml
# Ví dụ minh họa, không phải định dạng Kanban bắt buộc.
workflow:
  item_types:
    - feature
    - defect
    - technical_improvement
  started_when: "Ready -> Developing"
  finished_when: "Verify -> Done"
  wip_limits:
    Developing: 3
    Review: 2
    Verify: 2
  entry_policies:
    Developing: "Ready, còn năng lực và người phối hợp rõ"
    Review: "Thay đổi có thể xem, kiểm tra sơ bộ đạt"
    Verify: "Review đạt, bản tích hợp sẵn sàng"
  done_policy:
    - "Acceptance criteria và kiểm soát bắt buộc đạt"
    - "Kiểm thử phù hợp đã được thực thi"
    - "Đã bàn giao và kiểm chứng trên môi trường đích"
  blocked_policy: "Giữ mốc Started, nêu lý do và bước gỡ chặn"
  rework_policy: "Giữ cùng item trước Done, kiểm chứng lại"
  expedite_policy: "Chỉ dùng theo tiêu chí sự cố và thẩm quyền đã định"
~~~

Với nhóm thật, nên đặt chính sách ở nơi mọi người có thể dễ dàng đọc và đề xuất điều chỉnh. YAML là cách trình bày ví dụ; nhóm có thể dùng mô tả ngay trên bảng, bảng quy ước hoặc tài liệu ngắn khác.

## 11. Dùng số đo để kiểm tra chính sách có giúp luồng tốt hơn không

Trong Kanban, bốn flow metrics tối thiểu thường được nhấn mạnh là **WIP, throughput, work item age và cycle time**. Chúng giúp nhìn thấy điều gì đang diễn ra và kiểm tra hiệu quả của thay đổi chính sách.

| Số đo | Định nghĩa trong workflow | Câu hỏi hỗ trợ |
| --- | --- | --- |
| **WIP** | Số item đã Started nhưng chưa Finished ở một thời điểm. | Có quá nhiều việc đang dở hoặc chờ? |
| **Throughput** | Số item Finished trong một khoảng thời gian. | Nhóm đang hoàn tất bao nhiêu item với chính sách hiện tại? |
| **Work item age** | Thời gian item đang WIP đã trôi qua từ Started. | Item nào đang già đi bất thường và cần hỗ trợ? |
| **Cycle time** | Thời gian đã trôi qua từ Started đến Finished của item đã Done. | Những item cùng loại thường mất bao lâu để hoàn tất? |

### 11.1. Ví dụ tính đơn giản

Giả sử tại thời điểm cuối ngày có:

- **2** item ở Developing.
- **2** item ở Review.
- **1** item ở Verify.
- Không có các item đã Started khác ở trạng thái blocked riêng.

Khi đó:

\[
\text{WIP} = 2+2+1=5\ \text{items}.
\]

Trong một tuần nhóm chuyển **4 item thực sự đạt Finished** sang Done, throughput tuần là **4 item/tuần**. Đừng tính thêm số lần item bị quay lại hoặc số lần tạo pull request.

Một item Started lúc 09:00 thứ Hai và Finished lúc 09:00 thứ Năm có **cycle time = 3 ngày lịch**. Nếu đến sáng thứ Tư nó vẫn chưa Finished, **work item age = 2 ngày lịch**. Những tính toán này chỉ có ý nghĩa khi dùng cùng cách xác định Started/Finished và đơn vị thời gian.

### 11.2. SLE: kỳ vọng theo xác suất, không phải lời hứa chắc chắn

**Service Level Expectation (SLE)** mô tả kỳ vọng về thời gian một item đi từ Started tới Finished, thường thể hiện **khoảng thời gian và xác suất**.

Ví dụ minh họa:

> “Dựa trên các item gần đây có loại và workflow tương tự, khoảng **85%** được Finished trong **8 ngày lịch hoặc ít hơn**.”

Điều đó **không có nghĩa mọi item phải xong trong 8 ngày**, cũng không chứng minh nhóm có thể cam kết chắc chắn với từng khách hàng trong 8 ngày. SLE là công cụ dự báo để nhóm điều hành công việc, chú ý item có work item age gần hoặc vượt kỳ vọng, và cải thiện luồng.

Nếu dữ liệu còn ít hoặc workflow vừa thay đổi, nhóm cần nêu rõ mức bất định, có thể dùng dự báo tạm và cập nhật khi thu được dữ liệu phù hợp. Tránh lấy một SLE của lỗi nhỏ để hứa thời gian cho một tích hợp phức tạp hoàn toàn khác.

### 11.3. Nhận diện điểm nghẽn và dòng công việc bất ổn

Quan sát có thể bao gồm:

- **Review luôn đầy**, Developers vẫn mở thêm item: có thể cần tăng khả năng review hoặc thay đổi cách chia lát cắt.
- **Verify thường bị chặn bởi môi trường:** cần cải thiện quyền, dữ liệu test hoặc pipeline.
- **Work item age tăng liên tục ở một loại việc:** xem lại kích thước, phụ thuộc, rework và chất lượng đầu vào.
- **Throughput tăng nhưng lỗi production cũng tăng:** cần xem liệu chính sách Done có bị nới lỏng hoặc thiếu kiểm chứng.
- **Ít item Done nhưng ai cũng bận:** xem WIP và khả năng swarm để hoàn tất.

Chỉ số nên được sử dụng để **đặt câu hỏi cho hệ thống**, không để phạt cá nhân vì một item khó. Số ticket có thể bị thao túng bằng cách chia nhỏ giả tạo nếu được dùng làm KPI cá nhân.

### 11.4. Little's Law chỉ hữu ích khi hiểu giả định

Một quan hệ thường được dùng để tư duy về luồng là:

\[
\text{WIP trung bình} \approx \text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Đây là cách biểu đạt của **Little's Law** cho hệ thống ổn định với ranh giới đo và đơn vị nhất quán, cùng các điều kiện áp dụng. Nó **không có nghĩa cứ giảm WIP một nửa là cycle time chắc chắn giảm một nửa** trong mọi tình huống. Sự thay đổi về loại công việc, tắc nghẽn, ưu tiên khẩn cấp và chất lượng có thể làm điều kiện quan sát không còn phù hợp.

Nhóm nên xem đây là một **mô hình gợi ý về tác động của lượng việc dở dang lên thời gian hoàn tất**, rồi kiểm tra bằng dữ liệu thật.

## 12. Cách vận hành chính sách trong các buổi phối hợp

Kanban không bắt buộc một bộ cuộc họp có tên và timebox cố định như Scrum. Nhóm có thể dùng các nhịp tương tác phù hợp để **chủ động quản lý workflow**.

### 12.1. Xem luồng hằng ngày

Thay vì lần lượt hỏi mọi người “hôm qua làm gì?”, nhóm có thể đi từ **Done về phía công việc đang chờ**, tập trung vào việc sắp hoàn tất:

1. Có item nào ở Verify nhưng chưa đạt điều kiện Done?
2. Review nào đã gần/vượt SLE hoặc đang bị chặn?
3. Mục nào cần phối hợp để giải quyết phụ thuộc?
4. Có thể hỗ trợ hoàn tất trước khi kéo thêm việc mới?
5. Có sự cố thật sự khẩn cấp cần kích hoạt chính sách ngoại lệ?

Những câu hỏi này là **gợi ý điều hành luồng**, không phải nghi thức bắt buộc. Nếu phát hiện blocker quan trọng giữa ngày, nhóm có thể xử lý ngay thay vì đợi cuộc họp kế tiếp.

### 12.2. Xem xét backlog và replenishment

Khi cần bổ sung việc vào Ready, nhóm và người có thẩm quyền ưu tiên (ví dụ Product Owner nếu đang dùng Scrum) cần cân nhắc:

- Giá trị, rủi ro, chi phí trì hoãn và phụ thuộc.
- Loại hạng mục và mức rõ ràng để bắt đầu.
- Năng lực của các bước downstream, không chỉ của người bắt đầu code.
- Những nghĩa vụ bắt buộc và deadline có hậu quả thực tế.
- Cơ hội chia item lớn thành lát cắt dùng được.

**Replenishment** không nhất thiết là “đổ đầy Ready”; nó là hoạt động bảo đảm hệ thống có **việc phù hợp để kéo khi có năng lực**.

### 12.3. Review hệ thống và cải tiến chính sách

Định kỳ, nhóm có thể xem:

- Cột nào thường xuyên đầy WIP và nguyên nhân?
- Những loại rework nào lặp lại?
- Có bước chuyển trạng thái nào không tạo giá trị kiểm soát?
- Chính sách Done có phản ánh chất lượng thực sự và điều người dùng nhận được?
- SLE có còn phản ánh dữ liệu gần đây?
- Cần thử thay đổi nhỏ nào và đo trong bao lâu?

Ví dụ, nhóm thử **để người review phụ trách sớm từ khi PBI gần hoàn tất** thay vì chờ tới khi thẻ bị đẩy vào Review. Sau vài tuần, họ so thời gian chờ review, số lần rework và lỗi sau phát hành. Nếu cải tiến không đem lại tác dụng mong đợi, nhóm có thể sửa hoặc hoàn tác chính sách.

## 13. Kanban dùng chung với Scrum, XP và cách làm Agile khác

### 13.1. Scrum và Kanban có thể bổ sung nhau

Scrum có **Sprint Goal, Sprint Backlog, Increment, Definition of Done và các sự kiện**. Kanban giúp trực quan hóa workflow, kiểm soát WIP, theo dõi work item age/cycle time và quản lý chuyển trạng thái.

Một Scrum Team có thể đặt các Product Backlog Items đã chọn trên bảng Kanban bên trong Sprint và dùng chính sách như:

- Chỉ chuyển một PBI sang Verify khi bản tích hợp sẵn sàng.
- Không gọi PBI Done khi **Definition of Done** của Scrum Team chưa đạt.
- Hạn chế WIP để tập trung bảo vệ Sprint Goal.
- Hiển thị blocker ngay, không đợi Sprint Review.

Điều này **không thay thế** Sprint Goal hay thay đổi trách nhiệm của Product Owner/Developers/Scrum Master. Ngược lại, nhóm Kanban không sử dụng Scrum **không bị bắt buộc** tạo Sprint, Sprint Planning hoặc Scrum Master.

### 13.2. Thực hành XP giúp điều kiện Done trở nên khả thi

Những thực hành thường gắn với **Extreme Programming (XP)** có thể tạo phản hồi kỹ thuật sớm:

| Thực hành | Hỗ trợ chính sách chuyển trạng thái / Done |
| --- | --- |
| **Continuous integration** | Phát hiện lỗi build/tích hợp trước khi chuyển Review/Verify. |
| **Test-driven development** | Làm rõ quy tắc và kiểm tra hồi quy khi triển khai. |
| **Pair programming và code review** | Chia sẻ kiến thức, nhận phản hồi sớm về thay đổi. |
| **Refactoring có test bảo vệ** | Giữ thiết kế dễ thay đổi mà không phá hành vi đã cam kết. |
| **Kiểm thử tự động theo rủi ro** | Cung cấp bằng chứng nhất quán cho các điều kiện Done. |

Kanban không tự động tạo chất lượng; **chính sách tốt cần được hỗ trợ bằng năng lực kỹ thuật và cách phối hợp phù hợp**.

### 13.3. Chất lượng và giá trị không phải hai lựa chọn đối lập

Khi backlog có nhiều việc, nhóm có thể chịu áp lực “đẩy thẻ nhanh hơn”. Nhưng một thẻ Done mà người dùng không thể sử dụng, dữ liệu không đúng hoặc rủi ro bảo mật chưa xử lý có thể làm hại giá trị lâu dài.

Chính sách cần giúp nhóm **bàn giao phần tăng trưởng nhỏ nhưng thật**, thu phản hồi sớm, và thay đổi thứ tự backlog khi bằng chứng cho thấy điều khác có giá trị hơn.

## 14. Những phản mẫu cần tránh

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Mỗi người tự quyết thế nào là Done** | Số liệu và kỳ vọng lệch nhau. | Công khai Finished point, acceptance criteria và chuẩn chất lượng. |
| **Chuyển cột vì “tôi đã làm xong”** | Việc còn lại bị đẩy sang người khác, tăng chờ đợi. | Ghi điều kiện vào/ra bằng bằng chứng có thể xác minh. |
| **WIP limit có nhưng không áp dụng** | Mở quá nhiều việc, ít kết quả hoàn tất. | Kiểm soát pull, ưu tiên hỗ trợ các bước đang nghẽn. |
| **Đưa item blocked ra khỏi WIP và quên nó** | Che giấu thời gian chờ, dự báo sai. | Giữ mốc Started và hiển thị blocked minh bạch. |
| **Thẻ Verify không đạt vẫn được Done** | Phần mềm sai, lỗi tràn sang người dùng. | Rework theo chính sách, kiểm chứng lại trước Finished. |
| **Chia một lỗi thành nhiều ticket mới để tạo throughput** | Số item Done tăng giả tạo, chất lượng không đổi. | Giữ item trong workflow trước Finished; minh bạch lỗi sau Done. |
| **Dùng quá nhiều cột và phê duyệt không cần thiết** | Tăng handoff và thời gian chờ. | Chỉ giữ những trạng thái hỗ trợ kiểm soát hoặc quan sát luồng. |
| **Không có chính sách ưu tiên khẩn cấp** | Mọi yêu cầu gấp đều chen ngang, WIP mất kiểm soát. | Định nghĩa điều kiện, thẩm quyền và cách đánh đổi rõ ràng. |
| **Lách review/bảo mật để đạt SLE** | Hạ chất lượng và có thể vi phạm nghĩa vụ. | Giữ kiểm soát bắt buộc, cải tiến cách phối hợp và hệ thống. |
| **Đo cycle time nhưng không thống nhất Started/Finished** | So sánh không có ý nghĩa. | Công bố ranh giới, lịch tính và quản lý thay đổi định nghĩa. |
| **Coi SLE là bảo đảm 100%** | Kỳ vọng sai, gây áp lực đóng ticket sớm. | Dùng xác suất và lịch sử công việc tương đương. |
| **Không điều chỉnh chính sách sau khi có dữ liệu mới** | Điểm nghẽn lặp lại dù bảng đẹp. | Thử nghiệm cải tiến nhỏ, theo dõi chất lượng và flow. |
| **Bảng chỉ phục vụ giám sát cá nhân** | Thành viên ngại báo blocked và lỗi. | Dùng bảng để phối hợp, giúp việc hoàn tất và cải thiện hệ thống. |

## 15. Bài tập thực hành

### Bài tập 1 — Viết lại chính sách chuyển cột mơ hồ

Nhóm hiện dùng:

> “Khi dev xong thì kéo sang Review; khi QA nói OK thì kéo Done.”

**Yêu cầu:** viết lại điều kiện vào/ra cho ba cột Developing, Review, Verify và định nghĩa mốc Finished. Nêu hai bằng chứng cần có trước Done và một trường hợp phải quay lại làm.

**Gợi ý:**

- Developing → Review khi có thay đổi để review, mô tả hành vi và các kiểm tra sơ bộ đạt.
- Review → Verify khi nhận xét chặn đã xử lý, review đạt, bản tích hợp sẵn sàng.
- Verify → Done khi acceptance criteria, các kiểm soát chất lượng và bàn giao tới môi trường đích đã đạt.
- Nếu test tích hợp sai dữ liệu, quay Developing trong cùng item và giữ mốc Started cũ.

### Bài tập 2 — Quyết định kéo việc khi WIP đầy

Một bảng có WIP limit **Developing = 3, Review = 2, Verify = 2**. Hiện:

- Developing: 2 item.
- Review: 2 item.
- Verify: 1 item, trong đó item duy nhất bị chặn quyền sandbox.
- Ready: 5 item.

**Câu hỏi:**

1. Có nên kéo ngay thêm item từ Ready vào Developing chỉ vì Developing còn một chỗ?
2. Có nên đẩy item mới từ Developing vào Review khi Review vẫn đầy?
3. Item bị chặn có còn được tính là WIP không?
4. Nhóm nên tập trung vào những hành động nào để cải thiện luồng?

**Gợi ý:** còn chỗ WIP không đồng nghĩa nhất thiết phải kéo việc. Cần xét khả năng downstream; Review đầy nên ưu tiên xử lý review trước. Item bị chặn vẫn là WIP nếu đã Started và chưa Finished. Phối hợp cấp quyền sandbox, giải quyết review, hỗ trợ hoàn tất và chỉ kéo thêm việc khi phù hợp năng lực/chính sách.

### Bài tập 3 — Tính các số đo cơ bản

Theo quy ước **ngày lịch** và chênh lệch thời điểm:

| Item | Started | Finished / trạng thái hiện tại |
| --- | --- | --- |
| A | 01/07 | 06/07 — Done |
| B | 02/07 | 05/07 — Done |
| C | 03/07 | Đang Verify tại 08/07 |
| D | 04/07 | Đang Review tại 08/07 |

**Yêu cầu:**

1. Tính cycle time của A và B.
2. Tính work item age của C và D tại 08/07.
3. Tính WIP của bốn item tại 08/07.
4. Nếu chỉ có A và B đạt Finished trong tuần, throughput trong phạm vi dữ liệu này là bao nhiêu?

**Đáp án tham khảo:** cycle time A = **5 ngày**, B = **3 ngày**; work item age C = **5 ngày**, D = **4 ngày**; WIP tại 08/07 = **2** (C và D); throughput của các item được liệt kê đạt Finished trong tuần = **2 item/tuần**. Phải dùng cùng mốc Started, Finished, thời điểm chụp và lịch tính đã thống nhất.

### Bài tập 4 — Kiểm chứng điều kiện Done

Hạng mục “Học viên tự đăng ký khóa học miễn phí” đang ở Verify. Nhóm có:

- Build và unit tests đạt.
- Một học viên đăng ký thành công trong demo.
- Kiểm thử đồng thời chỗ cuối chưa chạy được do thiếu môi trường.
- Tài khoản của một học viên có thể xem đăng ký của người khác.
- Chưa triển khai đến môi trường đích đã định nghĩa cho Finished.

**Câu hỏi:** hạng mục có thể chuyển Done không? Liệt kê những điều kiện chưa đạt, bước xử lý và người có thể hỗ trợ.

**Gợi ý:** không. Cần khắc phục lỗi phân quyền, có môi trường để kiểm chứng đồng thời, thực hiện các kiểm soát bắt buộc và xác nhận bàn giao theo chính sách. Nhóm chủ động giải quyết; người có quyền cấp môi trường và người phụ trách bảo mật có thể hỗ trợ theo đúng thẩm quyền.

### Bài tập 5 — Soạn chính sách cho rework và lỗi production

Đề xuất chính sách ngắn cho:

1. Reviewer phát hiện API trả mã lỗi không đúng trước Done.
2. Test tích hợp thất bại sau khi item sang Verify.
3. Một tuần sau khi item Done, production xuất hiện lỗi mới liên quan.
4. Item bị đánh dấu Done nhầm do người cập nhật trạng thái.

**Gợi ý:** (1)–(2) giữ item và mốc Started, chuyển lại bước phù hợp và kiểm chứng lại. (3) tạo incident/defect riêng, liên kết item gốc và xử lý theo chính sách; không tùy tiện thay đổi số đo lịch sử. (4) sửa dữ liệu có dấu vết/audit và điều chỉnh các số đo nếu cần.

### Bài tập 6 — Thử nghiệm cải tiến một điểm nghẽn

Nhóm có dữ liệu cho thấy Review thường chiếm phần lớn cycle time, trong khi số lỗi sau phát hành vẫn cao. Hãy thiết kế một thử nghiệm cải tiến:

- Một giả thuyết về nguyên nhân thời gian chờ.
- Một thay đổi nhỏ ở chính sách hoặc cách phối hợp.
- Các số đo trước/sau: work item age, thời gian chờ review, rework, throughput và lỗi.
- Một điều kiện khiến nhóm giữ, điều chỉnh hoặc hoàn tác chính sách mới.

**Gợi ý:** thử ghép cặp/review sớm cho thay đổi phức tạp, giới hạn kích thước thay đổi và thống nhất người review dự phòng. Không chỉ tối ưu thời gian review; chất lượng sau tích hợp phải được kiểm tra cùng.

## 16. Checklist áp dụng cho một workflow Kanban

### Định nghĩa hệ thống

- [ ] Nhóm biết loại item nào đi qua workflow và ranh giới công việc đang quản lý.
- [ ] **Started point** và **Finished point** được công bố rõ.
- [ ] Mỗi trạng thái có ý nghĩa thực tế, không chỉ phản ánh tên phòng ban.
- [ ] Điều kiện vào/ra và người có trách nhiệm xác minh được hiểu chung.
- [ ] Có chính sách **pull** và cách kiểm soát WIP phù hợp.
- [ ] Các item blocked, chờ review và rework không bị che giấu.
- [ ] Ngoại lệ khẩn cấp có điều kiện kích hoạt và thẩm quyền rõ.
- [ ] Có SLE hoặc cách dự báo tương xứng với dữ liệu hiện có.

### Kiểm chứng hoàn tất và cải tiến

- [ ] Done được xác định bằng **bằng chứng**, không chỉ trạng thái “code xong”.
- [ ] Acceptance criteria và tiêu chuẩn chất lượng/an toàn bắt buộc được đáp ứng.
- [ ] Nếu Finished có nghĩa đã giao cho người dùng, điều kiện triển khai/kiểm chứng được ghi rõ.
- [ ] Item chưa Finished được giữ đúng mốc Started và WIP khi bị chặn/làm lại.
- [ ] Lỗi sau Done được xử lý theo quy tắc tránh đếm trùng và sai lịch sử.
- [ ] Nhóm đo WIP, throughput, work item age và cycle time nhất quán.
- [ ] Các chính sách được xem lại dựa trên tắc nghẽn, rủi ro, chất lượng và phản hồi.
- [ ] Mục tiêu sau cùng vẫn là **giao giá trị đáng tin cậy**, không chỉ đẩy thẻ đi nhanh.

Checklist này hỗ trợ cuộc trao đổi; nó không yêu cầu mọi hệ thống phải có đủ sáu cột hoặc nhiều bước duyệt. Một workflow ít trạng thái nhưng có chính sách rõ và có khả năng kiểm chứng có thể tốt hơn bảng phức tạp nhưng nhiều quy tắc không ai thực hiện.

## 17. Ghi nhớ

**Kanban là chiến lược quản lý và cải thiện dòng công việc.** Để bảng Kanban đáng tin cậy, nhóm cần công khai **Definition of Workflow**, các điểm Started/Finished, quy tắc pull, giới hạn WIP, chính sách chuyển trạng thái, xử lý blocked/rework và điều kiện gọi Done.

**Chuyển trạng thái** có nghĩa là bằng chứng đủ để công việc tiến sang bước tiếp. **Hoàn tất** có nghĩa hạng mục đã đạt những yêu cầu hành vi, chất lượng và bàn giao được xác định tại Finished point. **Một item bị chặn hoặc bị trả lại để sửa vẫn là công việc dở dang** cho tới khi thực sự Finished.

Những số đo như **WIP, work item age, cycle time, throughput** và kỳ vọng **SLE** giúp nhóm nhìn thấy chờ đợi và kiểm tra hiệu quả cải tiến. Nhưng số đo chỉ có ý nghĩa khi định nghĩa mốc không thay đổi tùy tiện và chất lượng không bị hy sinh để báo cáo đẹp.

Trong phát triển phần mềm Agile, mục tiêu là tạo các Increment nhỏ, đúng đắn, có thể sử dụng, nhận phản hồi sớm và liên tục cải thiện luồng. **Một chính sách tốt không cản trở thích ứng; nó làm rõ cách nhóm thích ứng mà vẫn giữ sự minh bạch và trách nhiệm.**

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Kanban** | Chiến lược tối ưu hóa dòng giá trị qua quy trình công việc với các thực hành định nghĩa, quản lý và cải tiến workflow. |
| **Definition of Workflow (DoW)** | Các quy tắc chung mô tả loại item, ranh giới Started/Finished, trạng thái, kiểm soát WIP, chính sách và SLE. |
| **Workflow state** | Một trạng thái mô tả tình trạng công việc trong luồng. |
| **Explicit policy** | Quy tắc được công khai để mọi người hiểu và áp dụng cùng cách. |
| **Entry/exit criteria** | Điều kiện cần thỏa trước khi nhận item vào hoặc chuyển khỏi một trạng thái. |
| **Pull system** | Cách nhận công việc dựa trên năng lực và điều kiện của bước tiếp theo. |
| **WIP (Work in Progress)** | Số item đã Started nhưng chưa Finished. |
| **WIP limit** | Cơ chế giới hạn lượng công việc đang dở trong hệ thống/bước công việc. |
| **Started point / Finished point** | Các mốc xác định bắt đầu/kết thúc workflow để quản lý và đo luồng. |
| **Blocked item** | Item đã gặp điều kiện ngăn nó tiến tiếp theo hướng dự kiến. |
| **Rework** | Công việc phải thực hiện lại/sửa sau khi kiểm tra phát hiện sai lệch. |
| **Cycle time** | Thời gian từ Started đến Finished của một item hoàn tất. |
| **Work item age** | Thời gian từ Started đến thời điểm quan sát của một item chưa Finished. |
| **Throughput** | Số item Finished trong một khoảng thời gian. |
| **Service Level Expectation (SLE)** | Kỳ vọng thời gian hoàn tất kèm xác suất dựa trên dữ liệu hoặc giả định được công bố. |
| **Acceptance criteria** | Điều kiện riêng mô tả hành vi mong đợi của một hạng mục. |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng của phần sản phẩm hoàn tất; là cam kết chính thức của Increment trong Scrum. |
| **Class of service** | Cách phân loại công việc để dùng chính sách xử lý phù hợp, khi nhóm lựa chọn áp dụng. |
| **Vertical slice** | Lát cắt chức năng đi qua những thành phần cần thiết để tạo hành vi dùng được. |
