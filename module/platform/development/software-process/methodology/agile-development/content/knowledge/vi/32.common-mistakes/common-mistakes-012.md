# Mở rộng khuôn tổ chức trước khi giải quyết trở ngại của từng nhóm

Một công ty phát triển nền tảng học trực tuyến có bốn nhóm sản phẩm. Mỗi nhóm đều than phiền rằng user story bị kẹt ở Review/Verify, môi trường thử nghiệm thường xuyên hỏng, Product Owner nhận yêu cầu từ nhiều nguồn và Developers khó tích hợp một lát cắt có thể dùng được. Lãnh đạo kết luận: “Chúng ta có quá nhiều nhóm, phải triển khai ngay một framework Agile quy mô lớn; thêm cấp điều phối, thêm chuỗi sự kiện và chuẩn hóa mọi bảng Sprint”.

Ba tháng sau, tổ chức đã có một hệ thống cuộc họp, biểu mẫu và vai trò mới. Nhưng môi trường thử nghiệm vẫn hỏng, API tiến độ học tập vẫn thiếu kiểm tra tương thích, việc khẩn vẫn chen ngang, còn một chuyên gia phân quyền phải duyệt từng thay đổi nhỏ. **Bộ máy điều phối lớn hơn nhưng trở ngại gốc không biến mất.** Người học vẫn không nhận được chức năng **“Học tiếp”** đúng và an toàn sớm hơn.

Đây là sai lầm **mở rộng khuôn tổ chức trước khi giải quyết trở ngại của từng nhóm**. Khi các nhóm chưa có khả năng tạo Increment đạt chất lượng, chưa hiểu luồng giá trị và chưa làm rõ quyền quyết định, việc nhân rộng nghi thức hoặc tầng quản lý dễ **nhân rộng cả hàng đợi, phụ thuộc và hành vi tối ưu cục bộ**.

Tuy nhiên, bài học **không phải** “mỗi nhóm phải tự giải quyết hết mọi vấn đề rồi tổ chức mới được phối hợp”. Có những trở ngại **vượt khỏi quyền và năng lực của một nhóm**, chẳng hạn ưu tiên xung đột giữa nhiều sản phẩm, nền tảng dùng chung, phê duyệt pháp lý hoặc một API phục vụ nhiều consumer. Những trở ngại ấy **cần trách nhiệm, đầu tư và phối hợp ở cấp phù hợp**. Cách làm đúng là **chẩn đoán nguyên nhân, phân biệt nơi có quyền thay đổi, thử cơ chế tối thiểu đủ dùng rồi mở rộng theo bằng chứng**.

Bài thuộc chương **Sai lầm thường gặp** của module **AGILE_DEVELOPMENT**. Nội dung nối giá trị Agile về hợp tác, phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục với user story, backlog, Scrum, Kanban, Extreme Programming (XP), đo dòng công việc và thiết kế phối hợp nhiều nhóm.

> **Luận điểm trung tâm:** Không nên chọn một “khuôn Agile quy mô lớn” để che các nút thắt chưa hiểu. Hãy bắt đầu từ **giá trị người dùng và trở ngại thật**, cải thiện năng lực ở đúng cấp, rồi bổ sung **mức phối hợp vừa đủ** cho những phụ thuộc không thể xử lý cục bộ.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Nhận diện dấu hiệu **premature scaling**: mở rộng nghi thức, vai trò, bảng báo cáo hoặc sơ đồ tổ chức trước khi hiểu vấn đề.
2. Phân biệt **trở ngại trong nhóm**, **trở ngại giữa các nhóm** và **ràng buộc hệ thống/tổ chức**, không đổ mọi vấn đề cho Developers.
3. Dùng **value-stream mapping**, quan sát work items, WIP, work item age, cycle time, blocked time và chất lượng để tìm chỗ giá trị bị chậm.
4. Phân biệt **kết quả người dùng** với **số team áp dụng framework, số cuộc họp, story points hoặc số ticket Done**.
5. Chọn những cải tiến kỹ thuật/cộng tác cục bộ như **vertical slicing, CI, contract tests, review policies và làm rõ user story**.
6. Xác định lúc cần **điều phối nhiều Scrum Teams, cơ chế pull Kanban, chuyên gia dùng chung, platform self-service hoặc thay quyền quyết định**.
7. Hiểu sự khác biệt giữa **nhiều Scrum Teams trên một sản phẩm** và **nhiều sản phẩm có phụ thuộc**, tránh tạo một backlog giả cho toàn công ty.
8. Đánh giá cơ chế phối hợp theo **giảm độ trễ/phụ thuộc và tăng chất lượng**, không theo số cấp họp hoặc độ đồng nhất tổ chức.
9. Thiết kế thí nghiệm thay đổi có **giả thuyết, owner, baseline, thời hạn, guardrails và quyết định giữ/sửa/dừng**.
10. Lập lộ trình mở rộng có điều kiện, biết khi nào cần dừng việc nhân bản một mô hình chưa chứng minh được giá trị.

## 2. “Mở rộng Agile” có thể chỉ ba việc rất khác nhau

Trong thực tế, cụm từ *scaling Agile* thường bị dùng cho nhiều vấn đề không giống nhau.

| Loại nhu cầu | Câu hỏi gốc | Ví dụ | Hướng tiếp cận |
| --- | --- | --- | --- |
| **Tăng số người/nhóm làm cùng một sản phẩm** | Nhiều nhóm làm sao tạo một Increment tích hợp và Product Goal chung? | Web, backend và phần tiến độ cùng phát triển một sản phẩm học tập | Làm rõ sản phẩm, Product Backlog, DoD, contract, tích hợp và phối hợp cần thiết |
| **Phối hợp nhiều sản phẩm/dịch vụ** | Làm sao giảm chờ khi các sản phẩm có owner và ưu tiên khác nhau? | Dịch vụ identity, nội dung, thanh toán và ứng dụng học viên | Service interfaces, product ownership, ưu tiên liên sản phẩm, platform và chính sách hỗ trợ |
| **Chuyển đổi cách quản lý ở cấp tổ chức** | Các quyết định đầu tư, phê duyệt và đo hiệu suất có hỗ trợ phản hồi nhanh không? | Tài trợ dự án theo scope cố định, mọi việc phải qua nhiều cấp duyệt | Điều chỉnh decision rights, portfolio, cơ chế đo, governance theo rủi ro |

Một tổ chức có thể gặp đồng thời cả ba; nhưng **giải pháp cho mỗi loại khác nhau**. Thêm một cuộc họp đồng bộ Sprint có thể giúp thấy phụ thuộc giữa team trên một sản phẩm, nhưng không tự sửa quyền triển khai bị khóa hoặc portfolio liên tục đổi ưu tiên.

### Framework không phải một “bản nâng cấp” theo quy mô

Scrum, Kanban và XP không tạo thành các tầng “nhỏ → lớn → chuyên nghiệp”. Chúng giải quyết những khía cạnh khác nhau:

- **Scrum** cung cấp cấu trúc trách nhiệm, sự kiện, artifacts và commitments để giải vấn đề phức tạp qua empiricism.
- **Kanban** giúp định nghĩa, quản lý và cải tiến flow bằng WIP control, chính sách rõ và feedback.
- **XP** đưa các thực hành kỹ thuật giúp thay đổi mã và tích hợp an toàn, thường xuyên.
- Các cách tổ chức/phối hợp nhiều nhóm là **lựa chọn thiết kế bổ sung theo nhu cầu**, không tự động thay thế ba yếu tố trên.

Mục tiêu không phải triển khai đủ các nhãn, mà là **giảm thời gian từ nhu cầu tới giá trị đúng và đáng tin, nâng khả năng thích ứng**.

## 3. Nhận biết mở rộng khuôn quá sớm

Một thay đổi ở cấp tổ chức đáng nghi khi những câu hỏi nền tảng chưa có lời đáp nhưng bộ khung đã được chọn sẵn.

| Tín hiệu quan sát | Nguy cơ | Câu hỏi cần đặt |
| --- | --- | --- |
| Mọi team phải dùng cùng số cột, cùng WIP limit hoặc cùng velocity target | Nhầm đồng nhất hình thức với hiệu quả | Workflow, đơn vị giá trị và biến thiên công việc có giống nhau không? |
| Tạo tầng “điều phối điều phối viên” cho mọi thay đổi nhỏ | Handoff và chi phí quyết định tăng | Những việc nào thật sự cần trao đổi đồng bộ? |
| Có nhiều người đại diện nhưng không ai được quyết định thứ tự backlog | Quyền quyết định vẫn mơ hồ | Ai chịu trách nhiệm giá trị và trade-off? |
| Từng team gọi Done nhưng sản phẩm chung không chạy được | Tối ưu cục bộ, chất lượng tích hợp yếu | Có Increment tích hợp và DoD chung khi cùng một sản phẩm không? |
| Platform và chuyên gia phê duyệt mọi PR | Nút thắt tập trung bị tăng tải | Những kiểm tra nào có thể tự phục vụ, tự động hoặc theo rủi ro? |
| Lãnh đạo báo thành công vì 100% team đã được đào tạo | Đo activity thay outcome | Người dùng và flow có được lợi, lỗi có giảm, feedback có sớm hơn? |
| Trở ngại được chuyển sang một bảng “liên nhóm” nhưng không ai sở hữu xử lý | Trực quan hóa không dẫn tới hành động | Owner, thời hạn quyết định và đường escalation là gì? |

### Một dấu hiệu quan trọng: lịch họp tăng nhưng thời gian chờ không giảm

Nếu trước khi “scale” một yêu cầu API phải chờ **bốn ngày**, sau khi scale nó đi qua hai cuộc họp nhưng vẫn chờ **bốn ngày**, bộ máy mới có thể chỉ **đổi hình thức chờ đợi**. Cần đo **time-to-unblock, cycle time, chất lượng và kết quả sản phẩm**, không chỉ tỷ lệ người tham dự.

### Không quy kết mọi mô hình lớn là sai

Một chương trình có nhiều đội, nhiều hệ thống và ràng buộc an toàn thực có thể cần cơ chế quản lý phụ thuộc, hoạch định đầu tư hoặc điều phối release phức tạp hơn. Câu hỏi là **cơ chế đó có giải quyết một vấn đề đã được chứng minh và có chi phí tương xứng không**. Không phải “càng ít cấu trúc càng Agile”.

## 4. Bắt đầu từ giá trị bị chậm, không phải số nhóm hiện có

Một cấu trúc mới chỉ có ý nghĩa khi giúp **người dùng nhận giá trị nhanh, đúng, an toàn hơn**. Vì vậy, trước khi hỏi “cần bao nhiêu Scrum of Scrums”, hãy hỏi người học đang mắc kẹt ở đâu.

### Hành trình minh họa

Người học muốn quay lại đúng bài đang dở:

~~~mermaid
flowchart LR
    A["Người học cần<br/>tiếp tục bài dở"] --> B["Product discovery<br/>và lựa chọn lát cắt"]
    B --> C["Xây UI + API +<br/>quy tắc tiến độ"]
    C --> D["Tích hợp và<br/>kiểm tra phân quyền"]
    D --> E["Increment đạt DoD"]
    E --> F["Rollout an toàn"]
    F --> G["Quan sát task success<br/>và lỗi thật"]
    C -. "Chờ hợp đồng API" .-> H["Blocked time"]
    D -. "Chờ staging/review" .-> H
~~~

Nếu Developers hoàn tất phần UI trong hai ngày nhưng phải đợi data contract và môi trường thử thêm mười ngày, tăng số người code UI **không rút ngắn nút thắt thật**. Nếu API và pipeline đã tốt nhưng người học không tìm thấy nút, tăng cơ chế phối hợp kỹ thuật cũng **không thay thế discovery/UX**.

### Cần phân biệt các mốc

| Mốc | Ý nghĩa | Dễ nhầm với |
| --- | --- | --- |
| **Code complete** | Mã đã được viết theo phạm vi kỹ thuật | Increment đạt chất lượng |
| **Done theo DoD** | Công việc đáp ứng tiêu chuẩn chất lượng áp dụng | Đã phát hành cho tất cả người dùng |
| **Deployed** | Artifact chạy ở môi trường đích | Người dùng đã được exposure |
| **Released/exposed** | Người dùng được phép trải nghiệm theo kế hoạch | Người dùng đã nhận lợi ích |
| **Outcome** | Tác vụ/điều kiện người dùng thực sự cải thiện | Impact dài hạn đã chứng minh |

Mỗi mốc hỗ trợ một quyết định khác nhau. Một cơ chế tổ chức có thể làm code merge nhanh hơn nhưng nếu **time-to-feedback và outcome** không đổi, chưa nên coi “scale” thành công.

## 5. Bản đồ trở ngại: phân biệt phạm vi và quyền xử lý

“Mỗi team có trở ngại” không đồng nghĩa “mỗi team tự chịu trách nhiệm sửa hết”. Hãy phân loại theo **nơi phát sinh, ai có quyền thay đổi và nơi bị ảnh hưởng**.

| Cấp trở ngại | Ví dụ | Bên có thể hành động | Khi nào cần phối hợp rộng? |
| --- | --- | --- | --- |
| **Trong team — kỹ thuật** | PR quá lớn, không có API tests cho logic mình sở hữu | Developers, người hỗ trợ kỹ thuật | Khi cần capability chung hoặc contract ngoài team |
| **Trong team — cách làm việc** | Bắt đầu nhiều story, không rõ DoD cục bộ | Scrum Team/những người làm công việc | Khi policy bị quy định từ cấp trên hoặc chia sẻ workflow |
| **Giữa hai team** | Producer API và consumer hiểu khác semantics | Owners của hai service, Product Owners khi cần | Khi phụ thuộc lặp, cần shared interface |
| **Nhiều team dùng chung** | Staging lỗi, reviewer chuyên môn quá tải | Platform/specialist owner, đội tiêu thụ | Khi cần đầu tư self-service, governance và capacity |
| **Cấp sản phẩm/portfolio** | Các Product Owners được giao ưu tiên mâu thuẫn | Người chịu trách nhiệm product/portfolio và lãnh đạo | Khi trade-off vượt quyền một team |
| **Cấp tổ chức/tuân thủ** | Quyền triển khai, chính sách phê duyệt hoặc bảo mật không rõ | Người có thẩm quyền policy, lãnh đạo kỹ thuật/pháp lý | Khi cần thay quy tắc hoặc đầu tư hệ thống |

### Hai câu hỏi chẩn đoán nhanh

1. **Nếu một team thay đổi cách làm của mình ngày mai, trở ngại có thực sự biến mất không?** Nếu không, tìm owner của phụ thuộc bên ngoài.
2. **Nếu thêm một tầng họp chung, ai sẽ có quyền và bằng chứng để gỡ trở ngại?** Nếu không ai, chưa có cơ chế giải quyết.

### Dùng “độ rộng ảnh hưởng” khác “cấp quyền”

Một lỗi CI template có thể ảnh hưởng **mười team** nhưng một platform team có thể sửa trong phạm vi của họ. Một quyết định ưu tiên nhỏ nhưng liên quan **nghĩa vụ pháp lý** có thể cần người có quyền cấp tổ chức. Đừng dùng số team bị ảnh hưởng làm tiêu chí duy nhất để quyết định tầng giải quyết.

## 6. Chẩn đoán nguyên nhân trước khi áp mô hình

Một triệu chứng có thể có nhiều nguyên nhân. “Story không Done trong Sprint” có thể là vấn đề slicing, API dependency, review WIP, chất lượng CI, thay yêu cầu hoặc DoD thiếu rõ.

### Quy trình phân tích thực dụng

1. **Mô tả sự kiện:** “Trong bốn tuần qua, phần lớn feature PBIs bị chờ Review/Verify hơn ba ngày” thay vì “team chưa có tinh thần Agile”.
2. **Xác định ranh giới đo:** một work item bắt đầu/kết thúc khi nào, loại việc nào được xét?
3. **Chọn vài trường hợp thật:** đi theo một story từ lúc bắt đầu đến Done, xem timestamp, blocker, API và build.
4. **Nêu nhiều giả thuyết:** review thiếu người, PR quá lớn, CI flaky, hợp đồng API mơ hồ, WIP quá cao...
5. **Phân loại quyền thay đổi:** trong nhóm, giữa nhóm, platform, policy hay portfolio.
6. **Đánh giá rủi ro/chi phí thử:** chọn biện pháp nhỏ có thể kiểm tra với guardrails.
7. **Đo và quyết định:** giữ, sửa, bỏ hoặc đưa vấn đề lên cấp có thẩm quyền.

### “5 Whys” không phải công thức tìm người có lỗi

Ví dụ:

~~~text
Hiện tượng: Story "Học tiếp" chờ tích hợp 7 ngày.

Vì sao? API checkpoint chưa khớp kỳ vọng UI.
Vì sao? Contract chỉ được trao đổi khi gần Sprint Review.
Vì sao? Refinement chủ yếu tách task frontend/backend riêng.
Vì sao? Các team được đo theo việc hoàn tất task riêng.
Vì sao? Governance và mục tiêu giao hàng tập trung vào
        mức bận từng bộ phận, không nhìn Increment tích hợp.

Giả thuyết:
  Handoff và cách đo tối ưu cục bộ góp phần làm chậm giá trị.
~~~

Đây là **một giả thuyết có thể kiểm chứng**, không phải bằng chứng tuyệt đối. Phải kiểm tra thêm API lịch sử, năng lực team và những trường hợp tương tự trước khi thay cả cấu trúc tổ chức.

## 7. Value-stream mapping: quan sát chỗ giá trị đang nằm chờ

**Value stream** là dòng các hoạt động/điều kiện để biến nhu cầu thành giá trị cho người dùng. Map dòng giá trị giúp phân biệt **thời gian chủ động làm việc** và **thời gian chờ** tại các handoff.

### Ví dụ giả định cho một lát cắt

| Bước | Thời gian chủ động | Thời gian chờ | Câu hỏi cần tìm hiểu |
| --- | ---: | ---: | --- |
| Làm rõ story và ví dụ nghiệp vụ | 0,5 ngày | 2 ngày | Ai có quyền xác nhận quy tắc? |
| Phát triển UI + API nhỏ | 3 ngày | 1 ngày | Có thể làm theo vertical slice không? |
| Review/contract verification | 0,5 ngày | 4 ngày | PR lớn, thiếu reviewer hay phụ thuộc policy? |
| Kiểm thử tích hợp và staging | 1 ngày | 3 ngày | CI/staging dùng chung có đáng tin? |
| Chuẩn bị exposure có kiểm soát | 0,5 ngày | 1 ngày | Có thực sự cần chờ release chung? |
| **Tổng minh họa** | **5,5 ngày** | **11 ngày** | Chờ là phần lớn lead time end-to-end |

Trong bảng giả định, tổng thời gian **16,5 ngày**, trong đó thời gian chờ **11/16,5 ≈ 66,7%**. Nếu chỉ đào tạo Developers code nhanh hơn 20%, mức giảm tối đa ở phần 3 ngày phát triển (giả sử các bước khác giữ nguyên) chỉ **0,6 ngày**; còn những chỗ chờ chưa được giải quyết.

**Đây không phải đề nghị coi toàn bộ thời gian chờ là lãng phí.** Một số kiểm tra, thời gian quan sát dữ liệu hoặc phê duyệt bắt buộc có giá trị an toàn. Cần phân biệt **chờ không tạo ích lợi** với **thời gian cần thiết để giảm rủi ro**, rồi xem có thể thực hiện hiệu quả hơn không.

### Khi bản đồ chỉ ra vấn đề nào

- Nếu **review queue lớn**: thử PR nhỏ, swarming, WIP policy và năng lực reviewer.
- Nếu **CI flaky**: ưu tiên sửa tính đáng tin của feedback, không thêm cuộc họp báo cáo build.
- Nếu **contract được làm rõ muộn**: tổ chức producer–consumer exchange sớm và automated tests.
- Nếu **quyền phê duyệt mơ hồ**: người có thẩm quyền phải công bố policy/ngoại lệ rõ.
- Nếu **môi trường chung luôn lỗi**: đầu tư platform reliability/self-service.
- Nếu **feature được giao nhưng người học không dùng**: quay lại discovery, Product Goal và outcome.

## 8. Dữ liệu flow dùng để phát hiện trở ngại, không để xếp hạng team

Các số đo Kanban giúp nhìn hệ thống; chúng không phải “điểm Agile” của cá nhân.

| Metric | Định nghĩa trong workflow đã công bố | Chỉ ra điều gì? | Cạm bẫy |
| --- | --- | --- | --- |
| **WIP** | Số work items đã bắt đầu, chưa xong | Quá nhiều việc cùng tranh nguồn lực? | Giấu blocked items để WIP giảm |
| **Throughput** | Số work items hoàn tất trong một khoảng | Hệ thống hoàn tất việc theo nhịp nào? | Chia vụn ticket để tăng số lượng |
| **Work item age** | Thời gian một item đang dở đã trải qua | Item nào cần gỡ blocker ngay? | Phạt người giữ item khó |
| **Cycle time** | Thời gian từ start tới finish của item đã hoàn tất | Phân bố thời gian hoàn tất và biến thiên | Đổi định nghĩa Done để số giảm |
| **Blocked/waiting time** | Khoảng chờ được ghi theo policy | Phụ thuộc nào gây trễ nhiều? | Ghi thiếu nếu có cơ chế trừng phạt |
| **Time-to-feedback** | Từ giả thuyết/lát cắt tới bằng chứng kỹ thuật hoặc người dùng | Có thể học và đổi hướng sớm không? | Đếm demo mà không có quyết định |

### Little's Law không chứng minh ai làm nhanh

Trong hệ thống ổn định và có ranh giới/đơn vị nhất quán:

\[
\text{Average WIP}=\text{Average Throughput Rate}\times\text{Average Cycle Time}.
\]

Nếu throughput trung bình **2 items/ngày** và WIP trung bình **10 items**, cycle time trung bình tương ứng khoảng **5 ngày** khi các điều kiện phù hợp. Quan hệ này **không bảo đảm** cứ ép WIP giảm một nửa thì thời gian hoàn tất mọi item giảm một nửa; demand, giới hạn nguồn lực, loại công việc và variability vẫn quan trọng.

### Bằng chứng phải đi với chất lượng và giá trị

Một nhóm có thể đóng nhiều PBIs hơn bằng cách hạ Definition of Done. Cần xem **Increment tích hợp, lỗi nghiêm trọng, khả năng triển khai, người học mở đúng bài và nhịp làm việc bền vững**. Việc tăng tốc toàn hệ thống không có ý nghĩa nếu đánh đổi quyền riêng tư hoặc mất dữ liệu.

## 9. Trở ngại nội bộ nhóm cần xử lý trước khi nhân bản cách làm

Đối với vấn đề **thực sự nằm trong tầm kiểm soát của nhóm**, thường có thể thử cải tiến trực tiếp thay vì chờ chương trình tái tổ chức.

| Trở ngại | Đòn bẩy nhỏ có thể thử | Bằng chứng cần xem |
| --- | --- | --- |
| User stories quá lớn và không tạo lát cắt | Tách theo luồng sử dụng, quy tắc và rủi ro | Time-to-testable-Increment, rework, task outcome |
| Bắt đầu nhiều việc, hoàn tất ít | Giới hạn WIP phù hợp, ưu tiên hoàn tất, swarming | Work item age, cycle time, throughput, tải nhóm |
| Code chỉ tích hợp cuối Sprint | CI thường xuyên, PR nhỏ, contract/API tests | Thời gian phát hiện lỗi, build reliability, regression |
| Chờ review lâu | Explicit review policy, pairing, chia sẻ hiểu biết | Review wait, chất lượng review, lỗi lọt |
| Không rõ Done | Làm rõ DoD/quality criteria và acceptance examples | Increment dùng được, ít đảo trạng thái/rework |
| Daily Scrum thành báo cáo quản lý | Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh kế hoạch | Blocker được gỡ, mục tiêu rõ, bớt handoff |
| Retrospective lặp cùng lời hứa | Một experiment có owner, timebox, metric và guardrails | Chính sách/hiệu quả thực thay đổi |

### Không nhầm “trong team” với “do team gây ra”

Một team có thể có WIP cao vì **ba lãnh đạo liên tục ép bắt đầu việc mới**, không phải vì Developers “thiếu kỷ luật”. Khi quyền ưu tiên ở cấp khác, team cần công khai bằng chứng và **đề nghị sửa cơ chế giao việc**; không thể tự giảm WIP nếu mọi yêu cầu từ trên được coi là lệnh tức thì.

### Kiểm tra cải tiến đã ổn định chưa

Một thỏa thuận tốt nên có **định nghĩa hành vi, bằng chứng và điều kiện xem lại**. Nếu chỉ một Sprint tốt lên vì ít việc hoặc có thêm chuyên gia, cần tránh tuyên bố “đã giải quyết xong, nhân rộng ngay”.

## 10. Trở ngại xuyên nhóm cần giải ở cấp có đủ quyền và năng lực

Một số vấn đề không thể khắc phục chỉ bằng retrospective hoặc WIP limit của một team:

| Trở ngại xuyên nhóm | Vì sao một team không đủ quyền/năng lực? | Biện pháp ở cấp phù hợp |
| --- | --- | --- |
| **Hai Product Owners đưa ưu tiên mâu thuẫn cho cùng chuyên gia** | Không ai có quyền cân đối toàn nguồn lực | Minh bạch trade-off, quyền quyết định cross-product và capacity |
| **API thay đổi phá consumer khác** | Producer không hiểu hết việc dùng ở các nhóm | Interface ownership, contract tests, versioning và compatibility |
| **Staging dùng chung hỏng thường xuyên** | Một team không sở hữu hạ tầng | Platform owner sửa reliability, self-service và kênh hỗ trợ |
| **Một người phê duyệt bảo mật mọi yêu cầu** | Policy hoặc năng lực chuyên gia nằm ngoài team | Review theo mức rủi ro, automation phù hợp, coaching và backup |
| **Release phải chờ nhiều dịch vụ triển khai cùng lúc** | Hệ thống có phụ thuộc phiên bản xuyên nhóm | Compatibility strategy, progressive rollout, migration plan |
| **Tài trợ theo dự án scope cố định khiến backlog không thể đổi** | Quy tắc đầu tư ở cấp lãnh đạo/portfolio | Xem lại cách cấp nguồn lực, Product Goal và quyền điều chỉnh |
| **Nhiều team cùng thay code nhưng không rõ owner** | Ownership và trách nhiệm vận hành không thống nhất | Làm rõ boundaries, contract, incident responsibility và DoD |

### Cấp cao hơn không nhất thiết có nghĩa họp nhiều hơn

Ví dụ, để gỡ hàng chờ tạo môi trường, giải pháp bền vững có thể là **một capability self-service**, một **owner platform rõ** và một **support policy công khai**, thay vì mỗi tuần lập thêm cuộc họp xin cấp quyền. Ngược lại, một thay đổi schema ảnh hưởng nhiều consumer có thể cần **một phiên collaboration ngắn** để thống nhất rủi ro.

### Escalation có ích khi mang theo bằng chứng và quyết định

Một yêu cầu escalation tốt:

~~~text
PROBLEM:
  5 feature PBIs đang chờ staging; 3 team cùng bị ảnh hưởng.

OBSERVED IMPACT:
  Trung vị thời gian chờ môi trường 4 ngày; chất lượng CI chưa xác nhận.

REQUESTED DECISION:
  Ai sở hữu sửa gốc? Có đầu tư tạo staging self-service?
  Cách phục vụ tạm thời khi đang sửa như thế nào?

RISK/GUARDRAIL:
  Không dùng secrets production hoặc bỏ security checks.

OWNER / NEXT REVIEW:
  Platform owner + representatives các team tiêu thụ, mốc kiểm chứng.
~~~

Nó khác “báo lên để sếp biết” vì xác định **người có quyền hành động, lựa chọn, hệ quả và thời điểm xem kết quả**.

## 11. Năng lực kỹ thuật là nền để phối hợp nhiều nhóm hiệu quả

Một doanh nghiệp có thể triển khai mô hình điều phối rất chuẩn, nhưng nếu **mỗi lần tích hợp mã đều mất một tuần kiểm thử thủ công**, các team vẫn khó tạo Increment thường xuyên.

### Những năng lực có thể đầu tư trước hoặc song song với điều phối

| Năng lực | Vấn đề được xử lý | Hạn chế cần nhớ |
| --- | --- | --- |
| **Continuous Integration** | Xung đột tích hợp được phát hiện sớm | CI phải chạy checks phù hợp và đáng tin |
| **Unit/API/contract tests** | Quy tắc nghiệp vụ và interface được kiểm chứng | Tests sai expectation vẫn cho kết quả xanh |
| **Automated build/deploy** | Giảm thao tác và chờ môi trường | Phải có bảo mật, audit và kiểm soát rollout |
| **Feature flags/progressive delivery** | Tách deploy khỏi exposure, giới hạn rủi ro | Flags cần owner/vòng đời, không được thành nợ vĩnh viễn |
| **Versioned APIs và compatibility** | Ít phải deploy đồng thời producer/consumer | Một số migration vẫn cần coordination |
| **Observability và runbooks** | Phát hiện và xử lý vấn đề xuyên service sớm | Logging không được lộ dữ liệu người học |
| **Refactoring có tests bảo vệ** | Giảm chi phí thay đổi qua thời gian | Không làm thay đổi hợp đồng công khai tùy tiện |
| **Pairing và chia sẻ kiến thức** | Giảm phụ thuộc một chuyên gia | Có timebox và điều kiện team tự chủ dần |

### Một ví dụ API checkpoint

Trước khi code hai team riêng biệt, họ thống nhất các tình huống:

~~~gherkin
Feature: Truy cập điểm tiếp tục học đúng quyền

  Scenario: Học viên có quyền đọc checkpoint của mình
    Given học viên A có quyền truy cập khóa K
      And checkpoint hợp lệ của A là bài B
    When A yêu cầu tiếp tục khóa K
    Then hệ thống trả điểm tiếp tục hợp lệ cho A

  Scenario: Không đọc checkpoint của tài khoản khác
    Given checkpoint thuộc học viên A
      And học viên B không có quyền đọc checkpoint của A
    When B yêu cầu checkpoint thuộc A
    Then API từ chối theo hợp đồng phân quyền
      And không tiết lộ thông tin tiến độ của A
~~~

Đây là **ví dụ quy tắc để làm rõ**, phải được xác nhận trong domain thực tế. Khi chuyển thành checks chạy ở CI, nhu cầu họp “đã ổn chưa?” giảm vì producer/consumer có **bằng chứng kỹ thuật thường xuyên**. Những quyết định nghiệp vụ hoặc security mới vẫn cần trao đổi thật.

### Đổi biểu đồ tổ chức không thay code quality

Nếu chuyên gia bảo mật vẫn phải duyệt thủ công mọi PR vì hệ thống không có test và policy rõ, việc đổi tên họ thành “architecture enablement” **không xóa hàng đợi**. Nên xem **kiểm tra nào lặp/đủ điều kiện tự động, rủi ro nào cần chuyên môn thật và cơ chế chuyển giao kỹ năng**.

## 12. Scrum nhiều nhóm: bắt đầu từ ranh giới sản phẩm và Increment

Scrum không yêu cầu một tổ chức phải có một bộ tầng chức danh mới chỉ vì số Scrum Teams tăng. Theo **Scrum Guide**, khi nhiều Scrum Teams cùng phát triển **một sản phẩm**, họ cần cùng **Product Goal, Product Backlog, Product Owner và Definition of Done**. Mục tiêu là **tạo Increment tích hợp** có giá trị, không chỉ mỗi nhóm đóng ticket riêng.

### Phân biệt hai bối cảnh

| Bối cảnh | Câu hỏi chủ đạo | Hệ quả phối hợp |
| --- | --- | --- |
| **Nhiều Scrum Teams cùng một sản phẩm** | Làm sao cùng theo một Product Goal và tạo Increment thống nhất? | Cần Product Backlog và DoD chung, phối hợp chọn PBIs, integration và dependencies |
| **Nhiều sản phẩm độc lập nhưng liên hệ** | Làm sao giảm chờ giữa các sản phẩm và dịch vụ? | Mỗi sản phẩm có ownership rõ, API/service contracts, cross-product prioritization khi cần |

**Đừng ép tất cả vào một Product Backlog** chỉ vì muốn “scale Scrum” nếu thực chất có nhiều sản phẩm với khách hàng, vòng đời và quyền quyết định khác nhau. Cũng đừng để ba team trên **một sản phẩm** dùng DoD xung đột rồi gọi các phần rời rạc là Increment hoàn chỉnh.

### Scrum events giúp gì trước khi thêm sự kiện cấp cao?

| Sự kiện | Dùng để nhìn trở ngại nào? | Thay đổi đủ nhỏ nên thử |
| --- | --- | --- |
| **Sprint Planning** | Sprint Goal có bị phụ thuộc API/QA/infra đe dọa? | Làm rõ contract và rủi ro trước khi chọn quá nhiều PBIs |
| **Daily Scrum** | Điều gì cản trở tiến triển tới Sprint Goal? | Developers hỗ trợ nhau gỡ blocker thay vì bắt đầu thêm |
| **Sprint Review** | Increment tích hợp đã tạo giá trị đúng hướng chưa? | Đưa feedback vào Product Backlog, không chỉ demo slides |
| **Sprint Retrospective** | Cách làm việc/chất lượng cần cải thiện gì? | Thử review policy hoặc CI changes có mốc đo |

### Khi nào cần thêm đồng bộ giữa Scrum Teams?

Nếu hai team **thường xuyên thay cùng contract hoặc phụ thuộc về tích hợp**, một nhịp trao đổi ngắn giữa những người trực tiếp có thể giúp phát hiện vấn đề sớm. Nhưng nên hỏi:

- Đồng bộ này tạo **quyết định/đầu ra cụ thể** nào?
- Các bên có đủ thông tin và **quyền hành động** hay chỉ mang status đi báo?
- Có thể thay một phần bằng **contract tests, board phụ thuộc, tích hợp liên tục** không?
- Ai thực hiện quyết định và khi nào xem lại hiệu quả?

Một cuộc họp nhiều nhóm có ích khi nó giải quyết **một phụ thuộc thật**. Nó trở thành overhead khi chỉ tổng hợp bản sao của Daily Scrum.

## 13. Kanban: cải tiến dòng việc trước khi nhân rộng bảng

Kanban cung cấp góc nhìn **Definition of Workflow, WIP control, active flow management và feedback**. Một board chưa phải hệ thống quản lý flow nếu không có **đơn vị công việc, start/finish, chính sách, cách xử lý blocked và cách dùng dữ liệu để cải tiến**.

### Một workflow đơn giản để bắt đầu

~~~text
Ready  →  Developing  →  Review/Verify  →  Done
             │                │
             └── Blocked được đánh dấu và quản lý rõ

Chính sách cần thử:
  - Pull work items có điều kiện hiểu rõ mục tiêu/chất lượng.
  - Khi Review/Verify đầy, ưu tiên hoàn tất trước mở thêm.
  - Có đường xử lý incident khẩn với trách nhiệm minh bạch.
  - Work item age được xem chủ động; không giấu những item lâu.
~~~

### Dữ liệu nào giúp quyết định mở rộng cơ chế flow?

Nếu team A liên tục bị chờ review từ team B, cần xem **nguyên nhân và owner của dòng review**. Có thể một policy cross-team rõ và contract test đủ giải quyết. Nếu nhiều sản phẩm đều có cùng hàng đợi ở platform team, cần **nâng năng lực platform và quản lý demand**, không chỉ áp chung WIP limit trên bảng mỗi team.

### SLE không phải “mọi team phải xong trong 10 ngày”

**Service Level Expectation (SLE)** là kỳ vọng **với một xác suất** về thời gian work item hoàn tất qua workflow đã định nghĩa. Ví dụ minh họa: “85% feature nhỏ cùng loại kỳ vọng hoàn tất trong tối đa 10 ngày làm việc”. Điều này **không phải hạn chắc chắn cho mọi item** hoặc chỉ số xếp hạng team. Dữ liệu khác nhau đòi SLE khác nhau.

### Không biến Kanban thành công cụ che hàng đợi

Khi team dời toàn bộ work items đang bị chặn sang “External Dependencies” ngoài ranh giới đo để giảm WIP và cycle time, báo cáo có thể đẹp nhưng **dòng giá trị không nhanh hơn**. Giữ ranh giới nhất quán; nếu thay policy, phải ghi phiên bản và tác động tới chuỗi dữ liệu.

## 14. XP: nhân rộng năng lực kỹ thuật thay vì nhân rộng sự chờ đợi

Các thực hành XP như **test-first/TDD, continuous integration, refactoring, pair programming, simple design và small releases** giúp giảm chi phí thay đổi và nhận phản hồi kỹ thuật sớm. Chúng không đòi đổi mọi team sang cùng một cấu trúc mới.

| Vấn đề trước khi scale | Thực hành có thể giúp | Cách kiểm chứng |
| --- | --- | --- |
| Merge conflicts, lỗi integration cuối Sprint | CI, tích hợp thay đổi nhỏ | Time-to-feedback, contract failures phát hiện sớm |
| Lỗi checkpoint/phân quyền hồi quy | TDD/API tests theo quy tắc đã rõ | Escaped defects, regression time, reliability |
| Code quá phụ thuộc một chuyên gia | Pairing, knowledge sharing | Blocked time, review age, số người có khả năng hỗ trợ |
| Thay đổi nhỏ kéo theo refactor lớn | Refactoring có test bảo vệ, simple design | Rework, cycle time của thay đổi tương tự |
| Release lớn, khó khôi phục | Small releases, rollout có kiểm soát | Phạm vi change, incidents và thời gian khôi phục |

### Điều không nên hiểu sai

Đầu tư kỹ thuật không phải yêu cầu viết thêm test cho đủ tỷ lệ. Một test suite chậm, flaky hoặc thiếu các kiểm tra rủi ro quan trọng có thể tạo **cảm giác an toàn giả**. Cần chọn **oracle đúng, mức kiểm tra hợp lý, ownership và feedback**.

### Tăng quy mô làm chi phí tích hợp tăng khi nền kỹ thuật yếu

Nếu một codebase có 20 người và không có CI đáng tin, thêm 20 người nữa có thể làm **số tương tác và xung đột tăng**, dù tổng công suất gõ mã lớn hơn. Cách giảm chi phí là **kiểm soát ranh giới phụ thuộc, tự động hóa feedback, contract rõ và team đủ năng lực giao lát cắt**, không chỉ tuyển thêm vị trí hoặc tạo cuộc họp mới.

## 15. Shared specialists và platform: giải nút thắt chung mà không tạo tầng xin phép

Một số phụ thuộc phổ biến là chuyên gia dữ liệu, bảo mật, CI/CD, hạ tầng và môi trường thử. Nếu mọi team đều phải chờ cùng một người thực hiện thao tác thông thường, việc “scale” bằng cách thêm một lịch họp phân bổ chuyên gia có thể chỉ **công khai hóa bottleneck**, chưa giảm nó.

### Các kiểu tương tác có ích

Có thể tham khảo cách phân biệt **X-as-a-Service, facilitating và collaboration** của Team Topologies:

| Interaction mode | Khi phù hợp | Ví dụ | Điều kiện kết thúc |
| --- | --- | --- | --- |
| **X-as-a-Service/self-service** | Nhu cầu lặp, ổn định, có thể chuẩn hóa | Tạo staging, CI template, observability mặc định | Consumer tự thực hiện đúng policy, có support khi lỗi |
| **Facilitating/coaching** | Nhóm thiếu năng lực có thể học để tự chủ | Security specialist pair về authorization | Team xử lý được ca thường lệ, biết khi nào cần escalation |
| **Collaboration có thời hạn** | Bất định cao, cần nhiều bên cùng thiết kế | Đổi schema checkpoint liên quan ba consumer | Contract, migration plan và ownership được xác nhận |

Đây là **các mẫu tương tác**, không phải yêu cầu áp đủ mọi kiểu team hoặc sao chép một mô hình tổ chức. Nhiều trường hợp kết thúc collaboration bằng một **interface ổn định** để giảm nhu cầu họp lặp.

### Platform as a product

Nhóm nền tảng có **người dùng nội bộ** (Developers, QA, SRE, Product teams), vấn đề cần giải, backlog theo giá trị, tài liệu, hỗ trợ, chất lượng và cách lấy feedback. Ví dụ, một golden path cho service Java nên giúp nhóm:

1. Tạo service/môi trường thử được cấp quyền theo policy.
2. Chạy CI với checks cần thiết và artifact định danh.
3. Triển khai, quan sát và gỡ lỗi với tài liệu đủ dùng.
4. Biết kênh support, owner và chính sách deprecation.
5. Gửi phản hồi để platform cải thiện self-service.

**Đo được giá trị nền tảng** khi developer task success, time-to-staging, time-to-unblock và reliability cải thiện — không chỉ vì platform đã phát hành một CLI hoặc đóng nhiều ticket.

### Khi review thủ công vẫn cần

Một thay đổi liên quan **mật mã chuyên sâu, dữ liệu nhạy cảm, kiểm soát theo hợp đồng hoặc rủi ro an toàn cao** có thể cần chuyên gia thực. Nên làm rõ điều kiện review/ngoại lệ, tự động hóa phần lặp và giảm chờ không cần thiết; **không bỏ nghĩa vụ an toàn để tăng số deploy**.

## 16. Quyền quyết định và Product Ownership phải rõ trước khi mở rộng governance

Một chương trình scale dễ tạo thêm danh xưng “leader”, “coordinator”, “release manager” mà không làm rõ **ai được thay thứ tự backlog, ai chọn phương án kỹ thuật, ai chấp nhận rủi ro và ai quyết định đầu tư capacity**.

### Ma trận quyền quyết định minh họa

| Quyết định | Quyền/trách nhiệm cần đặt ở đâu? | Điều phối khi nào? |
| --- | --- | --- |
| **Giá trị và thứ tự Product Backlog của một sản phẩm** | Product Owner hoặc người phụ trách sản phẩm phù hợp | Khi phụ thuộc mục tiêu hoặc quyết định portfolio |
| **Cách triển khai và chất lượng Increment** | Developers và owners kỹ thuật theo phạm vi | Khi đổi public contract, security hoặc shared subsystem |
| **Chính sách flow trong team** | Những người vận hành workflow trong quyền được trao | Khi ảnh hưởng trực tiếp consumer/providing teams |
| **Product/platform backlog** | Owner của platform capability | Khi trade-off giữa người dùng nội bộ và rủi ro hệ thống |
| **Incident production** | Incident roles theo severity policy | Ngay khi dịch vụ/người dùng nhiều nhóm bị ảnh hưởng |
| **Ngoại lệ pháp lý/bảo mật** | Người có thẩm quyền được chỉ định | Theo mức rủi ro và yêu cầu kiểm soát |
| **Đầu tư cross-product** | Người có thẩm quyền cân đối portfolio/capacity | Khi nhu cầu vượt quyền một Product Owner |

Tên chức danh có thể khác theo tổ chức; bảng mô tả **bản chất của quyền**. Nếu người có quyền không ở phòng họp, cuộc họp thêm tầng chỉ gom status rồi chờ quyết định vòng sau.

### Một sản phẩm hay nhiều sản phẩm?

Trước khi áp mô hình có tầng cấp, hãy trả lời: **đâu là đơn vị giá trị và ownership của sản phẩm?** Hai service phụ thuộc nhau **không mặc định** là cùng một sản phẩm. Ngược lại, ba Scrum Teams chia frontend/backend/database của **cùng một trải nghiệm sản phẩm** không nên tự tạo ba Product Goals cạnh tranh rồi bỏ việc tích hợp cho đội khác.

### Trách nhiệm không được trôi qua ranh giới

Khi có lỗi Học tiếp, cần biết:

- Ai là **service owner** cho API checkpoint?
- Ai có quyền **dừng rollout** hoặc mở incident?
- Ai bảo vệ **Definition of Done và quality checks**?
- Ai trao đổi với **người học/bên liên quan**?
- Ai phân bổ **capacity của chuyên gia hoặc platform** để sửa nguyên nhân gốc?

Nếu các câu trả lời chưa rõ, lập thêm một “bộ phận điều phối Agile” có thể tăng chờ thay vì tăng trách nhiệm.

## 17. Cơ chế phối hợp tối thiểu: chọn thứ giúp quyết định thật

Cơ chế càng lớn càng có chi phí: chuẩn bị, chuyển ngữ cảnh, tài liệu, hội họp và nguy cơ chờ phê duyệt. Điều phối tốt là **đủ để xử lý loại phụ thuộc đang có**.

| Phụ thuộc thực | Cơ chế nhỏ có thể dùng | Khi nào nên tăng mức điều phối? |
| --- | --- | --- |
| Hai team đổi một API | Contract review ngắn + versioned tests | Có nhiều consumer/rủi ro migration phức tạp |
| Một team chờ chuyên gia định kỳ | Office hours, intake minh bạch, pairing | Nhu cầu vượt capacity thường xuyên hoặc policy cấp tổ chức |
| Môi trường tạo thủ công | Catalog + self-service template | Cần đầu tư platform và ownership nhiều service |
| Hai Scrum Teams cùng một Increment | Tích hợp liên tục + trao đổi người liên quan | Phụ thuộc lặp khiến Sprint Goal/DoD bị đe dọa |
| Nhiều sản phẩm cùng tranh một platform capability | Backlog minh bạch + người có quyền trade-off | Capacity/investment cần quyết định portfolio |
| Schema đổi không tương thích | Collaboration có timebox + expand–migrate–contract | Có rủi ro dữ liệu/hợp đồng cao và rollback phức tạp |
| Sự cố production nhiều service | Incident response theo severity với owners rõ | Phối hợp cấp tổ chức và nghĩa vụ thông báo nếu cần |

### “Thêm họp” có thể là biện pháp tạm, không phải đích đến

Một buổi sync có thể cần để **xác nhận contract hoặc quyết định phụ thuộc**. Khi các bên đã đồng thuận và có automated tests, phần lớn cập nhật có thể **bất đồng bộ**. Nếu cuộc họp kéo dài vô hạn dù những vấn đề cũ đã được giải, nên **xem lại mục đích và bỏ phần không còn ích**.

### Tránh báo cáo chéo trùng lặp

Không nhất thiết sao chép toàn bộ Product Backlog của mỗi team sang một “master board” rồi yêu cầu cập nhật lại. Một **dependency map** chỉ ghi việc chặn Increment, owner, đầu ra cần và thời điểm đánh giá thường đủ hơn.

## 18. Thiết kế ranh giới nhóm theo dòng giá trị và cognitive load

Một sơ đồ tổ chức thường được chia theo chuyên môn: frontend, backend, database, QA, vận hành. Mô hình này có thể hợp lý trong một số hoàn cảnh, nhưng nếu **mỗi user story nhỏ phải xếp hàng qua bốn phòng ban**, chi phí handoff có thể lớn hơn thời gian làm việc hữu ích.

### Hai cực đoan nên tránh

1. **Tập trung mọi chuyên môn:** Nhóm sản phẩm không thể tự giao Increment vì mọi thay đổi đều chờ chuyên gia bên ngoài.
2. **Mỗi nhóm phải tự biết mọi thứ:** Cognitive load tăng quá mức; team phải tự vận hành hạ tầng, bảo mật, dữ liệu và mọi subsystem chuyên sâu dù nhu cầu lặp có thể chuẩn hóa.

Một lựa chọn cân bằng là **nhóm có khả năng tạo giá trị end-to-end trong phạm vi phù hợp**, được hỗ trợ bởi **các capability nền tảng và các giao diện chuyên môn rõ ràng**.

### Dùng mô hình tham khảo một cách đúng đắn

Tư duy **Team Topologies** đề cập các kiểu team như **stream-aligned, platform, enabling và complicated-subsystem**, cùng những tương tác X-as-a-Service, facilitating và collaboration. Đây là **mô hình tham khảo** hữu ích để giảm cognitive load và tăng flow, không phải quy tắc “bắt buộc chia thành đúng bốn phòng”.

| Câu hỏi | Nếu câu trả lời là “chưa” | Cải tiến cần cân nhắc |
| --- | --- | --- |
| Một nhóm có thể tạo lát cắt giá trị nhỏ tương đối độc lập không? | Phụ thuộc nhiều handoff chuyên môn | Làm rõ ownership, tăng năng lực cross-functional hoặc thay boundary |
| Team tiêu thụ có thể tự tạo môi trường thường lệ không? | Platform thành help desk thao tác thủ công | Self-service/golden path |
| Nhóm có biết khi nào cần gọi specialist không? | Xin review tràn lan hoặc không review khi rủi ro cao | Policy theo rủi ro, coaching và escalation |
| Shared subsystem có interface ổn định không? | Họp đồng bộ mỗi lần consumer thay đổi | Contract, versioning và service ownership |
| Người làm có đủ thời gian học/thực hiện phần việc chính không? | Cognitive load và chuyển ngữ cảnh cao | Giảm biến thể, nền tảng hóa việc lặp, phân quyền rõ |

### Không đổi cơ cấu chỉ vì thích một tên gọi

Một nhóm có thể **đã cross-functional đủ tốt** nhưng bị kẹt vì policy deploy. Đổi họ thành “stream-aligned squad” không tự sửa quyền triển khai. Ngược lại, một kiến trúc và ownership tạo handoff cố hữu có thể cần **đổi ranh giới nhóm** sau khi đã có bằng chứng. Cách quyết định phải gắn với **giảm phụ thuộc thực và bảo vệ chất lượng**.

## 19. Đếm hàng đợi và năng lực trước khi thêm cấp quản lý

Khi nhiều nhóm yêu cầu một chuyên gia xem API security, hàng đợi tăng do **nhu cầu đến và năng lực phục vụ không cân bằng**, không đơn thuần do “thiếu quy trình”.

### Ví dụ minh họa về tải phục vụ

Một specialist có thể hoàn thành trung bình **6 yêu cầu tư vấn chuẩn/tuần**, trong khi nhu cầu trung bình đến **9 yêu cầu/tuần**. Nếu mọi thứ giữ nguyên:

\[
\text{Tăng backlog dự kiến}\approx 9-6=3\ \text{yêu cầu/tuần}.
\]

Sau bốn tuần, lượng yêu cầu chưa xử lý có thể tăng khoảng **12**, nếu các giả định về loại việc và capacity đủ phù hợp. **Không có lượng cuộc họp điều phối nào tự làm năng lực 6 trở thành 9**.

### Có nhiều cách giải quyết khác nhau

- **Giảm demand:** self-service cho ca lặp, tài liệu, mẫu/automation.
- **Tăng capacity phù hợp:** đào tạo người dự phòng, bổ sung chuyên gia khi nhu cầu thật đủ lớn.
- **Phân loại rủi ro:** chỉ review chuyên sâu với những thay đổi cần thiết.
- **Giảm kích thước yêu cầu:** chuẩn bị context, PR/contract nhỏ và rõ hơn.
- **Thay cách tương tác:** coaching thay cho việc chuyên gia trực tiếp làm hộ mãi.
- **Minh bạch trade-off:** điều gì được ưu tiên và việc nào phải chờ.

### Đừng tối đa hóa utilization 100%

Nếu lịch specialist kín tuyệt đối, một incident nghiêm trọng sẽ **chen ngang** và làm các yêu cầu thường lệ mất khả năng dự báo. Năng lực xử lý bất định, phối hợp và cải tiến là **một phần của công việc**, không phải dấu hiệu “đang rảnh”.

### Đo thời gian bị chặn của bên tiêu thụ

Một specialist trả lời trong 10 phút bằng “đọc hướng dẫn này” nhưng team vẫn không thể triển khai có thể khiến **first response time tốt** mà **time-to-unblock không đổi**. Đánh giá phối hợp bằng **kết quả của toàn hệ thống**, không chỉ tốc độ xử lý request của provider.

## 20. Khi nào thực sự cần một khuôn mở rộng Agile?

Một khung phối hợp có cấu trúc hơn đáng được cân nhắc khi **phụ thuộc lặp lại đủ lớn** và **các biện pháp nhỏ đã được thử hoặc được xác định là không đủ**.

### Điều kiện nên có trước quyết định

| Điều kiện | Câu hỏi kiểm chứng |
| --- | --- |
| **Giá trị cần đạt rõ** | Sản phẩm/dòng giá trị nào cần giao tốt hơn? Thành công đo bằng gì? |
| **Ranh giới sản phẩm** | Một sản phẩm nhiều nhóm hay nhiều sản phẩm liên kết? |
| **Trở ngại có bằng chứng** | Handoff/approval/contract nào thật sự chiếm thời gian hoặc tạo rủi ro? |
| **Năng lực nền tảng đủ** | Team có thể tạo Increment đạt DoD và tích hợp sớm ở mức nào? |
| **Quyền quyết định rõ** | Ai sắp backlog, cấp capacity, xử lý portfolio và chấp nhận rủi ro? |
| **Cơ chế nhẹ đã được xem xét** | CI, hợp đồng API, board phụ thuộc, office hours và policy có thể giải quyết được bao nhiêu? |
| **Giá trị tăng thêm của cơ chế mới** | Tầng phối hợp thêm giảm chờ, rủi ro hoặc tăng feedback ở đâu? |
| **Chi phí/giới hạn** | Cần thêm bao nhiêu thời gian họp, điều phối, công cụ, đào tạo; rủi ro Goodhart? |
| **Có cách thử và quay lại** | Phạm vi pilot, baseline, metrics, guardrails và điều kiện dừng? |

### Thảo luận các lựa chọn một cách công bằng

Các framework/approaches như **Nexus, LeSS, Scrum@Scale, SAFe** hay mô hình tự thiết kế cung cấp những cấu trúc, phạm vi và cơ chế khác nhau để hỗ trợ nhiều team. **Không framework nào tự chữa được CI hỏng, ownership mơ hồ hoặc backlog thiếu định hướng**, và một số lựa chọn có chi phí triển khai/quản trị lớn hơn tùy bối cảnh.

Nên xem tài liệu chính thức để hiểu **điều kiện áp dụng và vai trò** của từng lựa chọn, rồi đánh giá bằng **trở ngại đã quan sát**. Không chọn theo mức độ phổ biến, nhãn chứng nhận, số người được đào tạo hay vì tổ chức đã mua công cụ.

### Bảng đánh giá thay vì tranh cãi theo tên framework

| Phương án | Cơ chế được kỳ vọng | Bằng chứng thử nghiệm | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **Giữ cấu trúc, tăng CI và contract tests** | Ít lỗi tích hợp, ít họp đồng bộ | Time-to-integration, lỗi interface, quality | Cần đầu tư kỹ thuật/ownership |
| **Sync phụ thuộc nhẹ** | Các bên phát hiện blocker sớm | Time-to-unblock, ít trễ DoD | Thêm lịch, có nguy cơ chỉ báo cáo |
| **Platform self-service** | Giảm ticket/handoff lặp | Developer task success, staging wait, reliability | Chi phí sản phẩm nội bộ, support lâu dài |
| **Đổi ranh giới nhóm** | Ít handoff để giao vertical slice | End-to-end cycle time, cognitive load | Gián đoạn kiến thức/nhân sự, chuyển ownership |
| **Framework đa nhóm chính thức** | Rõ governance, cadence và phối hợp cho phụ thuộc phức tạp | Outcome sản phẩm, tích hợp, flow, an toàn | Đào tạo, vai trò, họp, nguy cơ hình thức hóa |

### Không yêu cầu “ổn định hoàn hảo” trước khi mở rộng

Nếu tổ chức thực sự có hàng chục nhóm cần xử lý **rủi ro liên sản phẩm ngay bây giờ**, có thể cần cơ chế phối hợp ở cấp rộng **đồng thời** sửa CI, backlog và quy tắc làm việc tại team. “Làm tốt hết mọi thứ trong từng team rồi mới được scale” cũng là một cực đoan. Nguyên tắc là **không bỏ qua nguyên nhân, không tạo cấu trúc lớn hơn mức cần thiết**.

## 21. Lộ trình cải tiến theo các tầng: giải đúng trở ngại rồi mới mở rộng

Một lộ trình có thể dùng **bốn giai đoạn kiểm chứng**, không coi đó là lịch bắt buộc cho mọi tổ chức.

| Giai đoạn | Câu hỏi | Hoạt động | Điều kiện để đi tiếp |
| --- | --- | --- | --- |
| **1. Quan sát hệ thống** | Giá trị bị chậm/sai ở đâu? | Chọn value stream, map workflow, xác minh baseline | Có trở ngại và owner thực, không chỉ ý kiến chung |
| **2. Khôi phục năng lực gần nguồn** | Team có thể tự sửa gì? | Story slicing, DoD, CI, WIP, review, refinement | Có tín hiệu flow/quality cải thiện hoặc biết rõ lý do chưa |
| **3. Gỡ phụ thuộc liên nhóm** | Điều gì ngoài quyền team vẫn chặn? | Contract, platform, specialist capacity, quyết định portfolio | Service interface/ownership rõ, time-to-unblock tiến bộ |
| **4. Chuẩn hóa và mở rộng có chọn lọc** | Mẫu nào thực sự hữu ích ở bối cảnh khác? | Thử tại team khác, điều chỉnh governance hoặc topology khi có căn cứ | Có bằng chứng end-to-end và guardrails, không chỉ adoption |

### Chu kỳ PDCA trong từng giai đoạn

**Plan:** Phát biểu vấn đề, giả thuyết và cách đo.  
**Do:** Thử trong phạm vi phù hợp, không làm thay đổi cả tổ chức khi chưa cần.  
**Check:** Xem flow, quality, outcome và chi phí điều phối.  
**Act:** Giữ, sửa, dừng, mở rộng hoặc thay giả thuyết.

**Act không phải tự động mở rộng.** Nếu thử một buổi sync thêm mà waiting time không đổi, hãy tìm lý do; có thể cần **bỏ cuộc họp** thay vì mời thêm cấp lãnh đạo.

### Các thay đổi phải có khả năng dừng

Một số thay đổi dễ hoàn tác (giới hạn WIP, format cuộc họp); những thay đổi khác khó đảo ngược (đổi reporting lines, ownership và cơ chế cấp ngân sách). Trước khi quyết định tái cấu trúc lớn, cần kiểm tra **mức độ đảo ngược, tác động tới con người, an toàn vận hành và phương án chuyển tiếp**.

## 22. Phát biểu một giả thuyết cải tiến có thể kiểm chứng

Một thẻ thử nghiệm tốt nên có **vấn đề, cơ chế, phạm vi, metric, guardrail, owner và ngưỡng quyết định**.

~~~text
TITLE:
  Giảm hàng chờ review API checkpoint.

OBSERVED PROBLEM:
  Nhiều PBIs đang chờ review 3–5 ngày và tích hợp muộn.

HYPOTHESIS:
  Nếu producer/consumer thống nhất ví dụ API sớm,
  chia PR nhỏ và Developers giúp hoàn tất Review/Verify,
  thì thời gian chờ tích hợp sẽ giảm mà lỗi quyền không tăng.

CHANGE:
  Một contract review sớm; CI contract checks;
  chính sách WIP phù hợp tại Review/Verify.

SCOPE:
  Feature PBIs liên quan tiến độ trong hai vòng làm việc.

OWNER:
  Owners của API và consumer, cùng người hỗ trợ flow.

EVIDENCE:
  Review waiting, work item age, cycle time, throughput,
  integration failures, developer feedback, task outcome.

GUARDRAILS:
  Không bỏ authorization checks/DoD; không tăng làm thêm giờ.

NEXT DECISION:
  Giữ/sửa/dừng policy; chỉ xem mở rộng khi kết quả đáng tin.
~~~

### Giả thuyết có thể bị bác bỏ

Nếu review waiting giảm nhưng **integration failures tăng mạnh**, có thể chính sách review mới quá hời hợt hoặc contract tests chưa bao phủ rủi ro. Nếu work item age không đổi vì **staging vẫn hỏng**, cần xử lý platform, không tiếp tục siết quy tắc review. Một thử nghiệm tốt cho phép thấy **điều kiện nào không được xác nhận**.

### Dữ liệu phải có cùng định nghĩa

Nếu trước thử “Done” là code merged, sau thử “Done” là Increment tích hợp, không thể nối hai chuỗi cycle time như một phép so sánh trực tiếp. Ghi **Definition of Workflow, ranh giới thời gian, loại work item và thay đổi policy**.

## 23. Case study: từ “scale ngay” sang giải nút thắt của luồng Học tiếp

Đây là **tình huống giả định phục vụ học tập**, các số liệu chỉ minh họa cách nghĩ, không phải dữ liệu thật hoặc kiểm chứng nghiên cứu.

### 23.1. Bối cảnh tổ chức

Nền tảng học trực tuyến có các nhóm:

| Nhóm/năng lực | Phần giá trị hoặc dịch vụ | Khó khăn quan sát |
| --- | --- | --- |
| **Trải nghiệm học viên** | UI web/mobile và hành trình tiếp tục bài | Story chờ API, UI và backend nghiệm thu riêng |
| **Quyền và tiến độ học** | Checkpoint, enrollment, authorization | Contract chưa ổn, phụ thuộc dữ liệu |
| **Nội dung/khóa học** | Lesson metadata, bài đã xóa, quyền khóa | Cách xử lý lesson ID thay đổi |
| **Đánh giá/analytics** | Events và kết quả học tập | Nhiều định nghĩa “tiếp tục học” khác nhau |
| **Platform engineering** | CI, staging, secrets, observability | Support requests lặp, provisioning thủ công |
| **Chuyên gia dùng chung** | Bảo mật, data migration, vận hành | Một người phải review nhiều yêu cầu nhỏ |

Tổ chức đang cân nhắc lập **một tầng điều phối nhiều nhóm, bộ họp mới và chuẩn hóa tất cả Sprint boards** để giao tính năng “Học tiếp”.

### 23.2. Chẩn đoán hiện trạng trước khi chọn khuôn

Với một số feature PBIs liên quan tiến độ có ranh giới rõ, các quan sát ban đầu giả định là:

- **Median cycle time:** 16 ngày làm việc từ lúc bắt đầu đến Increment đạt DoD.
- **Median waiting ở Review/Verify:** 5 ngày.
- **WIP trung bình:** 13 items cho dòng feature liên quan.
- **Contract/API checks trước tích hợp:** áp dụng không đều, các trường hợp phân quyền ít được bao phủ.
- **Time-to-staging:** phụ thuộc một platform engineer; thường đợi vài ngày.
- **Người học:** nhiều báo cáo mở sai bài hoặc không nhận ra đường quay lại.

**Chưa đủ cơ sở** để kết luận tất cả nguyên nhân là do số nhóm. Thông tin được kiểm tra bằng cách theo dấu PBIs, xem CI logs, quan sát người học và trao đổi với owners của từng interface.

### 23.3. Những nguyên nhân được phân tầng

| Trở ngại | Cấp giải quyết | Vì sao? |
| --- | --- | --- |
| PBIs quá lớn, thiếu lát cắt end-to-end | Team sản phẩm với Product Owner/Developers | Có thể sửa cách refinement và slicing |
| Review/Verify bị đầy, nhiều việc đang dở | Team và những reviewer liên quan | Có thể thử WIP/pull và chia sẻ review capacity |
| API checkpoint producer/consumer hiểu khác | Hai nhóm cùng service contract | Phải cùng xác nhận behavior và version |
| Staging/provisioning phải nhờ một người | Platform và người cấp capacity | Không phải việc một team tự sửa |
| Security specialist duyệt mọi PR | Policy owner và specialist | Cần phân tầng rủi ro, tests, coaching |
| Product priorities liên tục bị nhiều lãnh đạo thay | Product/portfolio governance | Quyền ưu tiên không nằm trong Developers |
| Người học mobile khó tìm Học tiếp | Product discovery/UX | Phải kiểm chứng hành vi người dùng, không chỉ flow |

### 23.4. Phương án ban đầu bị loại

Tạo **ba buổi sync liên nhóm mỗi tuần** và yêu cầu mọi team chuẩn hóa báo cáo velocity có thể làm các vấn đề được nhắc đến thường xuyên hơn; nhưng **không tự sửa CI, hợp đồng API, self-service hoặc quyền Product Owner**. Các cuộc họp chỉ có ích nếu mang tới **quyết định rõ và người đủ thẩm quyền hành động**.

### 23.5. Thử nghiệm lần một — cải thiện trong nhóm

Trong hai vòng làm việc ngắn:

1. Product Owner và Developers chọn **một lát cắt Học tiếp đủ dùng**, không bắt đầu cả trang tiến độ lớn.
2. Làm rõ **acceptance examples cho checkpoint hợp lệ, không có checkpoint và sai quyền**.
3. Developers thử **ưu tiên Review/Verify trước khi kéo thêm PBIs**, đồng thời ghi blocked age.
4. Đưa **API/authorization checks** chạy trong CI ở những luồng quan trọng.
5. Nhìn Sprint Goal hoặc flow goal, DoD, defects và outcome, thay vì target tăng story points.

**Kết quả giả định:** Review waiting giảm nhưng một số story vẫn không Done vì staging chưa hoạt động ổn định. Đây là **bằng chứng quan trọng**, giúp tránh tiếp tục ép nhóm “cố tốt hơn” đối với nút thắt ở ngoài quyền của họ.

### 23.6. Thử nghiệm lần hai — giải trở ngại xuyên nhóm

Các owners đưa ra những thay đổi có mục đích:

- Producer/consumer thống nhất **versioned contract và API tests** cho Học tiếp.
- Platform ưu tiên một **staging self-service path** cho service Java thường lệ, có support/escalation.
- Security specialist pair với Developers xây **tests/policy mẫu**, giữ review sâu cho ngoại lệ.
- Product/portfolio owner công bố **quy tắc ưu tiên và chi phí cơ hội** khi yêu cầu mới chen ngang.
- Một **dependency sync ngắn có timebox** chỉ được gọi khi có quyết định version/migration hoặc blocked cần nhiều owner.

### 23.7. Kết quả giả định sau khi có bằng chứng

| Metric | Trước | Sau các thử nghiệm | Diễn giải phù hợp |
| --- | ---: | ---: | --- |
| Median cycle time feature | 16 ngày | 10 ngày | Có tín hiệu tốt; cần xem loại PBIs và phân bố |
| Median review waiting | 5 ngày | 2 ngày | Phù hợp giả thuyết ưu tiên hoàn tất |
| WIP trung bình | 13 | 8 | Ít việc dở hơn, cần bảo đảm không giấu blockers |
| Median time-to-staging | 3 ngày | 4 giờ | Self-service có thể giảm phụ thuộc thao tác |
| Lỗi checkpoint nghiêm trọng | Chưa có baseline tin cậy | Có tests và monitoring tốt hơn | Không tuyên bố giảm tỷ lệ lỗi từ số liệu thiếu |
| Task success Học tiếp trên mobile | Theo cohort ban đầu | Theo nhóm exposure phù hợp | Phải kiểm chứng trực tiếp outcome người học |
| Giờ làm thêm ngoài kế hoạch | Nhiều theo phản hồi | Ít hơn theo mẫu theo dõi | Cần xác nhận tính bền vững, không dùng một khảo sát |

**Không thể suy ngay quan hệ nhân quả chắc chắn** từ hai kỳ trước/sau khi có nhiều thay đổi đồng thời. Nhưng dữ liệu giúp thấy **những trở ngại nào đã giảm, nút thắt nào còn tồn tại và lựa chọn tiếp theo có hợp lý không**.

### 23.8. Khi nào cân nhắc cơ chế điều phối rộng hơn?

Sau vài vòng, tổ chức nhận thấy **nhiều sản phẩm khác nhau cùng tranh chuyên gia migration và quy tắc release**, thường xuyên tạo xung đột cấp portfolio. Lúc này có căn cứ để thiết kế một **cơ chế quyền quyết định liên sản phẩm và kế hoạch năng lực**, thử ở phạm vi vừa đủ. Bài học không phải “không cần phối hợp đa nhóm”, mà là **chỉ scale cơ chế giải quyết đúng phụ thuộc đã được nhận diện**.

### 23.9. Nếu người học vẫn không dùng tính năng?

Flow và CI tốt hơn không bảo đảm UI tạo giá trị. Nếu người học mobile vẫn không nhìn thấy nút, Product Owner cần **đổi giả thuyết và Product Backlog**, không tiếp tục mở rộng cùng một framework để cố đạt outcome bằng nghi thức. **Product discovery và delivery capability là hai vòng phản hồi bổ sung nhau**.

## 24. Đo hiệu quả của cơ chế phối hợp chứ không đo mức áp dụng framework

Một chương trình mở rộng Agile thường có dashboard về **bao nhiêu team đã áp dụng, bao nhiêu người được cấp chứng nhận, bao nhiêu buổi họp được tổ chức**. Những số ấy có thể giúp điều hành hoạt động thay đổi, nhưng **không chứng minh hệ thống tạo giá trị tốt hơn**.

### Bốn lớp bằng chứng

| Lớp | Ví dụ | Giá trị và giới hạn |
| --- | --- | --- |
| **Activity** | Đào tạo 100 Developers, thêm ba nhịp sync liên nhóm | Chỉ xác nhận đã làm hoạt động |
| **Output** | Có dependency board, service catalog, CI template | Đầu ra có tồn tại nhưng chưa biết dùng được không |
| **Capability/flow outcome** | Nhóm có thể tự triển khai; item chờ review ít hơn; tích hợp sớm hơn | Cần định nghĩa workflow và so sánh tương đồng |
| **Product/quality outcome** | Người học mở đúng bài; ít lỗi sai quyền; có thể nhận phản hồi sớm | Cần nguồn đo người dùng, chất lượng và kiểm tra độ bất định |

### Bộ chỉ số cân bằng gợi ý

| Câu hỏi | Metric/quan sát | Guardrail hoặc giới hạn |
| --- | --- | --- |
| **Cơ chế mới có giảm phụ thuộc?** | Time-to-unblock, số handoff thực, blocked age | Không chuyển công việc ra ngoài board để số đẹp |
| **Increment có đến Done sớm hơn?** | Cycle time distribution, work item age, throughput | Giữ DoD và loại work item nhất quán |
| **Tích hợp giữa nhóm có an toàn hơn?** | Contract failures phát hiện sớm, escaped defects, CI reliability | Không bỏ kiểm tra phân quyền/dữ liệu |
| **Nền tảng có giảm thao tác lặp?** | Self-service task success, time-to-staging, support demand theo loại | Không coi ít ticket là tốt nếu người dùng không thể báo lỗi |
| **Người học có nhận giá trị?** | Task success, thời gian mở đúng bài, phản hồi người học | Segments/cohort, không tự quy nhân quả |
| **Độ tin cậy có giữ không?** | Incidents, failure impact, recovery ability | Chưa có baseline không được tuyên bố giảm lỗi |
| **Chi phí điều phối có hợp lý?** | Thời gian họp để ra quyết định, chờ owner, cảm nhận cognitive load | Không dùng tổng giờ họp làm kết luận duy nhất |
| **Nhóm có làm việc bền vững?** | Interruption, overtime trends, phản hồi môi trường làm việc | Bảo vệ riêng tư, không xếp hạng cá nhân |

### Không so sánh velocity các nhóm

Story points là ước lượng nội bộ của một team, không phải đơn vị năng suất xuyên nhóm. Sau khi scale, nếu mỗi team bị ép tăng 20% velocity, họ có thể **đổi thang điểm hoặc chia ticket nhỏ hơn**; tổ chức sẽ mất công cụ dự báo ban đầu mà không có thêm giá trị.

### Một dashboard tốt dẫn tới quyết định

Dashboard cần giải thích:

1. **Vấn đề nào đang được kiểm chứng?**
2. **Dữ liệu có cùng định nghĩa và đủ tin cậy không?**
3. **Có những trường hợp bất lợi nào bị số tổng che đi?**
4. **Cơ chế mới có làm hàng đợi khác dài thêm?**
5. **Ai có quyền đổi chính sách, capacity hoặc backlog?**
6. **Giữ, sửa, dừng hay mở rộng thử nghiệm nào?**

Nếu các câu hỏi không được trả lời, thêm biểu đồ chỉ tăng **chi phí báo cáo**, không tạo empiricism.

## 25. Đánh giá chi phí điều phối và lợi ích trước khi chuẩn hóa rộng

Một cơ chế phối hợp không miễn phí, dù tất cả mọi người gọi nó là “Agile ceremony”. Cần nhìn **giá trị thời gian chờ giảm** cùng **chi phí hội họp, chuẩn bị, chuyển ngữ cảnh và duy trì vai trò/công cụ**.

### Phép tính minh họa — không phải ROI đã kiểm chứng

Giả sử tổ chức định thêm một cuộc họp liên nhóm:

- 8 người tham dự, **45 phút** mỗi lần.
- Tổ chức **2 lần/tuần**.
- Thời gian tham dự trực tiếp: \(8\times0{,}75\times2=12\) **giờ-người/tuần**.
- Chưa tính thời gian chuẩn bị, thay đổi ngữ cảnh, chi phí cơ hội của những người tham gia.

Giả sử cơ chế giúp giảm tổng **20 giờ-người chờ/điều phối gây trì hoãn** trong cùng thời gian. Về số học có thể có lợi ích, nhưng **20 giờ chờ không tự đồng nghĩa 20 giờ làm việc được tiết kiệm** — người đang chờ có thể làm việc khác, hoặc sự chờ kéo dài mốc release gây chi phí cơ hội lớn hơn giờ công. Cần đo cả **thời gian tới giá trị, số quyết định được thực thi và rủi ro**.

### Mẫu đánh giá một cơ chế mới

~~~text
COORDINATION CHANGE:
  [Tên sync/cơ chế/service interface]

PROBLEM:
  [Một phụ thuộc đã chứng minh]

EXPECTED VALUE:
  [Giảm chờ, tăng quality, giảm rủi ro, nhận feedback sớm]

DIRECT COST:
  [Người tham gia, thời gian, công cụ, onboarding]

INDIRECT COST:
  [Chuyển ngữ cảnh, thêm approvals, maintenance]

TRIAL:
  [Phạm vi, timebox, owner]

METRICS:
  [Time-to-unblock, cycle time, incidents, outcomes]

DECISION:
  [Giữ / sửa / dừng / mở rộng]
~~~

### Đừng tối ưu chi phí họp một cách máy móc

Một cuộc workshop ba giờ giúp ngăn **migration xóa nhầm tiến độ học viên** có thể hoàn toàn đáng giá; một cuộc sync 15 phút không có người đủ quyền quyết định có thể hoàn toàn vô ích. Đánh giá **mục đích, mức rủi ro và kết quả**, không chỉ số phút.

### Khi thay đổi tổ chức khó hoàn tác

Gộp/tách team, đổi reporting lines hoặc chuyển ownership của nhiều service có chi phí **học lại domain, bàn giao hệ thống, thay quyền truy cập, vận hành và tâm lý nhân sự**. Nếu chưa hiểu nguyên nhân, nên thử các biện pháp **dễ hoàn tác** như contract, WIP policy, shared service interface và cải thiện kỹ thuật trước; ngoại lệ là khi vấn đề an toàn/sở hữu nghiêm trọng đòi hành động tổ chức ngay.

## 26. Quản trị thay đổi: nhân rộng nguyên tắc, không nhân bản mọi nghi thức

Một pilot cho kết quả tốt thường kích thích quyết định: “Từ tháng sau, mọi nhóm dùng cùng cách làm!”. Đây là lúc một cải tiến có thể biến thành **áp đặt hình thức**.

### Điều gì có thể chuẩn hóa chung?

| Có thể cần nhất quán rộng | Thường cần thích ứng theo bối cảnh |
| --- | --- |
| Chính sách bảo vệ dữ liệu, phân quyền, tiêu chí an toàn bắt buộc | WIP limit và flow states của từng loại dịch vụ |
| Trách nhiệm khi nhiều Scrum Teams làm cùng một sản phẩm | Cách team tổ chức thảo luận ngắn hoặc workshop |
| Cách định nghĩa/kiểm tra artifact CI quan trọng | Công nghệ triển khai và mức tự phục vụ theo workload |
| Quy tắc báo incident, thông tin tối thiểu và escalation | Nhịp feedback của feature, maintenance hay discovery |
| Contract versioning, service ownership | Kích thước lát cắt theo kỹ năng và mức bất định |
| Mục đích đo end-to-end và guardrails | Target cycle time/throughput giữa các hệ thống khác nhau |

### Giai đoạn một: chứng minh trong một phạm vi

Ví dụ một team giảm review waiting bằng PR nhỏ và swarming. Cần ghi lại: **loại công việc, số người, phụ thuộc, baseline, quality guardrails và những biến đồng thời**. Không suy rằng đó là policy phù hợp cho team incident hoặc nghiên cứu thuật toán.

### Giai đoạn hai: kiểm tra ở nơi tương đồng

Thử cách làm với nhóm có nhu cầu tương tự nhưng không được “ưu ái” toàn bộ nguồn lực như pilot. Xem **năng lực thực thi, văn hóa báo blocker, kiến trúc và policy** có khác gì. Nếu kết quả khác, tìm nguyên nhân trước khi ép adoption.

### Giai đoạn ba: thống nhất mức thiết yếu

Chuẩn hóa những thứ giúp **an toàn và hợp tác**: cách phát hành code đã kiểm chứng, API contracts, nơi xem owner và sự cố, tiêu chí quan sát. Giữ **quyền lựa chọn cách làm cục bộ** trong những giới hạn rõ.

### Giai đoạn bốn: duy trì học hỏi

Khi nhu cầu sản phẩm hoặc công nghệ đổi, chính sách đã hiệu quả hôm trước có thể không còn phù hợp. Tổ chức cần nhịp **review tác động của cơ chế**, không biến “mô hình tổ chức phiên bản 1” thành quy định bất biến.

### Phân biệt phổ biến thực hành với chuyển đổi thật

**Adoption:** “Tám team đã dùng cùng tool.”  
**Capability:** “Các team đủ năng lực tạo Increment tích hợp an toàn.”  
**Outcome:** “Thời gian tới giá trị và chất lượng của sản phẩm đã cải thiện trong bối cảnh được đo.”  

Chỉ dùng **adoption** có thể khiến tổ chức ép tất cả team cài tool mà vẫn không gỡ trở ngại. Dùng cả ba lớp bằng chứng giúp biết **việc nào cần tiếp tục đầu tư**.

## 27. Những phản mẫu khi mở rộng khuôn tổ chức quá sớm

### 27.1. “Cứ thêm cuộc họp là phụ thuộc sẽ biến mất”

Cuộc họp tạo thêm nơi báo cáo nhưng không tạo quyền quyết định. **Cách sửa:** mỗi tương tác phải gắn một dependency, đầu ra và owner; đo time-to-unblock, bỏ nhịp không còn giá trị.

### 27.2. “Chọn framework trước rồi tìm vấn đề phù hợp”

Mọi team phải dùng cùng cấu trúc dù luồng feature, support và incident khác nhau. **Cách sửa:** xác định vấn đề và ranh giới sản phẩm trước; chọn cơ chế theo nhu cầu, không theo nhãn.

### 27.3. “Team không Done nghĩa là cần điều phối cấp cao”

Nguyên nhân có thể là PR lớn, thiếu CI, user story mơ hồ. **Cách sửa:** theo dấu vài work items thật, thử cải tiến gần nguồn trước khi thêm cấp.

### 27.4. “Mỗi nhóm hoàn tất ticket tức là sản phẩm hoàn tất”

Frontend, backend, QA đều báo xanh nhưng chưa có Increment tích hợp. **Cách sửa:** DoD và kế hoạch tích hợp end-to-end; với nhiều Scrum Teams trên một sản phẩm, hiểu các commitments chung.

### 27.5. “Mỗi team có một Product Owner nên toàn sản phẩm được điều phối tốt”

Nếu tất cả cùng một sản phẩm, nhiều backlog độc lập có thể tạo ưu tiên xung đột. **Cách sửa:** xác định product boundary và trách nhiệm Product Owner theo Scrum Guide; nếu nhiều sản phẩm, dùng service/portfolio interfaces phù hợp.

### 27.6. “Một master board chi tiết sẽ giải quyết mọi blocker”

Sao chép dữ liệu sang board mới làm cập nhật trùng và dễ lệch. **Cách sửa:** dependency board chỉ ghi phụ thuộc quan trọng với owner và next action, liên kết tới nguồn gốc.

### 27.7. “Mọi team phải có cùng WIP limit”

Không xét nhu cầu, số người, loại việc và workflow. **Cách sửa:** chọn giới hạn theo dữ liệu và khả năng của mỗi flow; theo dõi tác động trên cycle time/quality.

### 27.8. “Tăng velocity của từng team thì tổ chức sẽ nhanh hơn”

Thang points không thống nhất; tạo động lực chia ticket và bỏ việc khó. **Cách sửa:** đo end-to-end outcomes, flow và chất lượng; không xếp hạng teams/nhân viên theo velocity.

### 27.9. “Chuyên gia dùng chung là cấp phê duyệt cho mọi thay đổi”

Review queue dài và single point of failure. **Cách sửa:** risk-based review, authorization/API checks tự động, coaching và backup phù hợp.

### 27.10. “Platform có thể nhận mọi ticket nên không cần thay cách làm”

Platform trở thành help desk, không còn capacity loại bỏ request lặp. **Cách sửa:** platform as a product, self-service và support policy theo loại nhu cầu.

### 27.11. “Có golden path tức là mọi người tự chủ”

Template đã tạo nhưng phải nhắn người quen để được cấp môi trường. **Cách sửa:** quan sát developer task success từ đầu đến cuối, tài liệu và escalation phải dùng được.

### 27.12. “Đổi tên bộ phận thành squad là đã chuyển đổi”

Reporting lines khác nhưng phê duyệt, backlog và CI không thay đổi. **Cách sửa:** xác định rào cản, quyền quyết định và outcome trước khi đổi cơ cấu.

### 27.13. “Một team tốt có thể tự xử lý mọi vấn đề”

Team bị yêu cầu sửa policy portfolio, CI chung hoặc an toàn pháp lý mà họ không có quyền. **Cách sửa:** escalation có bằng chứng và quyết định; leadership chịu trách nhiệm gỡ trở ngại hệ thống.

### 27.14. “Tất cả trở ngại phải giải xong cục bộ mới được phối hợp rộng”

Chờ đợi vô hạn trong khi contract và incident liên sản phẩm cần xử lý ngay. **Cách sửa:** cải tiến gần nguồn **song song** với những thay đổi cấp rộng có căn cứ và owner.

### 27.15. “Mỗi lần tích hợp đều chờ một ngày release chung”

Khối thay đổi lớn, nhiều phần không tương thích và khó rollback. **Cách sửa:** contract versioning, CI, progressive delivery và migration plan; chỉ phối hợp đồng bộ khi rủi ro thực đòi hỏi.

### 27.16. “Definition of Done có thể hạ để đạt mục tiêu scale”

Mỗi team trông nhanh hơn, lỗi lại đổ vào sản phẩm chung. **Cách sửa:** giữ quality standard, điều chỉnh phạm vi/capacity và đầu tư kiểm tra.

### 27.17. “Quyền Product Owner có thể thay bằng hội đồng duyệt backlog”

Quyết định sản phẩm chạy qua nhiều cửa khiến feedback khó thay ưu tiên. **Cách sửa:** làm rõ ai chịu trách nhiệm giá trị, ai cần tham vấn, giới hạn rủi ro và trade-off cấp phù hợp.

### 27.18. “Số người có chứng chỉ Agile chứng minh chuyển đổi thành công”

Đếm đào tạo mà chưa biết năng lực giao hàng hoặc kết quả người học. **Cách sửa:** liên kết hoạt động đào tạo với hành vi, capability, flow, quality và outcome.

### 27.19. “Dữ liệu flow toàn công ty có thể so trực tiếp giữa mọi nhóm”

Khác loại việc và start/finish khiến so sánh sai. **Cách sửa:** dùng metric contracts, phân khúc/loại công việc và xem cải thiện trong bối cảnh.

### 27.20. “Càng nhiều team sử dụng platform thì platform càng tốt”

Adoption có thể do bắt buộc; trải nghiệm và an toàn vẫn tệ. **Cách sửa:** đo self-service success, reliability, time-to-unblock và feedback người dùng nội bộ.

### 27.21. “Bỏ toàn bộ governance để các nhóm tự chủ”

Có thể xung đột rủi ro pháp lý, dữ liệu và ownership. **Cách sửa:** tự chủ trong các guardrails rõ, risk-based approval và quyền quyết định minh bạch.

### 27.22. “Sau khi scale, mọi người phải bận 100%”

Không ai có capacity review, swarming hoặc xử lý sự cố; chờ tăng. **Cách sửa:** quản lý WIP, xem biến thiên demand và tạo năng lực dự phòng.

### 27.23. “Pilot thành công nên nhân bản y hệt cho 50 team”

Khác bối cảnh, phụ thuộc, kỹ năng và mức đầu tư. **Cách sửa:** mô tả điều kiện của pilot, thử ở nơi khác có baseline riêng và cho phép thích ứng.

### 27.24. “Việc có thêm tầng quyết định không cần đo lại”

Overhead tích tụ vì cơ chế một thời có ích không được xem lại. **Cách sửa:** định kỳ kiểm tra chi phí, kết quả, loại vấn đề đã hết và loại bỏ những bước không còn tạo giá trị.

## 28. Workshop 90 phút: tìm trở ngại trước khi chọn cách mở rộng

Workshop này là **gợi ý giảng dạy**, không phải một sự kiện bắt buộc trong Scrum/Kanban. Mời những người có **kiến thức thực về dòng công việc** và **người có quyền gỡ các phụ thuộc**; tránh chỉ tập hợp các chức danh để đủ “thành phần”.

### Tình huống đầu vào

Bốn nhóm phát triển nền tảng học trực tuyến cùng dùng một staging environment. CI thường fail do flaky tests, ba nhóm đợi một chuyên gia review quyền, và mỗi Sprint nhiều PBIs chưa đạt DoD. Lãnh đạo định lập **hai cấp đồng bộ liên nhóm, một master backlog và cùng velocity target**.

| Bước | Thời lượng | Công việc | Đầu ra |
| --- | ---: | --- | --- |
| **1. Xác định giá trị** | 10 phút | Chọn hành trình Học tiếp, xác định outcome người dùng | Mục tiêu giá trị và giới hạn chất lượng |
| **2. Theo dấu một story** | 15 phút | Vẽ các bước start–Done–release, ghi chờ/hoạt động | Map flow và nguồn chờ đáng nghi |
| **3. Phân tầng trở ngại** | 10 phút | Phân nhóm local, cross-team, platform, policy/portfolio | Impediment map có owner |
| **4. Tạo giả thuyết** | 10 phút | Tìm 2–3 giải thích khác nhau cho bottleneck | Các giả thuyết có thể kiểm chứng |
| **5. Đề xuất cơ chế tối thiểu** | 15 phút | Thử WIP, CI/contract, self-service hoặc sync khi cần | Kế hoạch thay đổi phạm vi nhỏ |
| **6. Đánh giá scale options** | 10 phút | So cơ chế mới với chi phí/giá trị dự kiến | Không chọn framework chỉ vì tên |
| **7. Thiết kế metric/guardrails** | 10 phút | Chọn flow, quality, outcome, sustainability | Baseline cần thu và tiêu chí đánh giá |
| **8. Ra quyết định thử** | 10 phút | Ai sở hữu, timebox, khi nào dừng/mở rộng? | Decision log và mốc review |

### Dữ liệu thực hành giả định

| Quan sát | Trước thử | Sau cải tiến cục bộ và contract sớm |
| --- | ---: | ---: |
| Median review waiting | 5 ngày | 2 ngày |
| Median cycle time feature | 15 ngày | 11 ngày |
| WIP trung bình | 13 | 9 |
| Median time-to-staging | 4 ngày | 4 ngày |
| Build reliability | Flaky thường xuyên | Vẫn flaky ở một số job |
| Task success Học tiếp mobile | Chưa được đo tốt | Đang xác định cohort/định nghĩa |

**Câu hỏi bắt buộc:** Có nên triển khai ngay thêm lớp quản trị nhiều team khi Review đã cải thiện nhưng staging vẫn chờ bốn ngày? Cần xác định **platform owner, nguyên nhân kỹ thuật, quyền đầu tư và điều kiện tự phục vụ**, thay vì mặc định một cuộc họp mới sửa được môi trường.

### Tiêu chí hoàn thành workshop

1. Mọi người có thể mô tả **vấn đề và người chịu ảnh hưởng** thay vì phán “chưa Agile”.
2. Có ít nhất **một trở ngại local và một trở ngại systemic** được phân biệt đúng.
3. Mỗi đề xuất có **cơ chế giải quyết**, không chỉ tên framework.
4. Có quyết định **cơ chế nào cần ngay, cơ chế nào chưa nên triển khai**.
5. Có **owner đúng quyền, baseline, guardrails, timebox và mốc xem lại**.
6. Tuyên bố kết quả **không vượt bằng chứng**; ghi điều chưa biết.

## 29. Bài tập tự kiểm tra và gợi ý

### Bài tập A — Phân cấp trở ngại

Cho các tình huống:

1. PR của một team rất lớn nên review chậm.
2. Producer API thay schema làm ba consumer lỗi.
3. Platform team cần phê duyệt thủ công để tạo mọi staging environment.
4. Product Owners nhận hai yêu cầu ưu tiên xung đột từ hai lãnh đạo.
5. Sprint Review chỉ demo mock vì các nhóm chưa tích hợp.
6. Một quy định bảo mật bắt buộc được diễn giải khác nhau ở từng phòng.

Xếp mỗi tình huống vào **local, cross-team hoặc systemic/organization** và đề xuất owner phù hợp.

**Gợi ý:** (1) phần lớn local; (2) cross-team; (3) platform/systemic; (4) governance; (5) có thể bắt đầu từ local slicing nhưng thường liên quan integration nhiều nhóm; (6) policy owner cấp phù hợp. **Một triệu chứng có thể có nhiều nguyên nhân**, không chỉ một nhãn.

### Bài tập B — Chọn điều phối nhẹ hay framework rộng

Hai team cùng một sản phẩm thường đợi một API contract không rõ. Họ đã có CI và muốn giao một lát cắt Học tiếp. Lãnh đạo đề nghị bổ sung ba cuộc họp liên nhóm mỗi tuần.

1. Thử biện pháp nhỏ nào trước?
2. Điều kiện nào cho thấy các biện pháp nhỏ không đủ?
3. Ai cần tham gia quyết định contract?
4. Đo hiệu quả bằng gì ngoài số người tham dự họp?

**Gợi ý:** Contract examples, owner, version/test, time-to-unblock và quality; tăng nhịp/cơ chế khi phụ thuộc lặp vẫn cản Increment.

### Bài tập C — Tính waiting share

Một value stream có **6 ngày làm việc chủ động** và **9 ngày chờ**. Hãy tính tổng lead time và tỷ lệ chờ. Nếu chỉ tăng tốc bước coding đang mất 3 ngày lên **nhanh gấp đôi**, nhưng chờ không đổi, tổng giảm bao nhiêu?

**Gợi ý:** Tổng = 15 ngày; chờ = \(9/15=60\%\). Coding giảm 3 xuống 1,5 ngày, tổng còn **13,5 ngày** nếu các bước khác không đổi, giảm 1,5 ngày (10% tổng). Đây là phép tính minh họa, thực tế các bước có thể phụ thuộc nhau.

### Bài tập D — Little's Law

Một workflow ổn định giả định có throughput trung bình 4 items/ngày và WIP 20 items. Cycle time trung bình suy ra bao nhiêu? Có thể bảo đảm cycle time giảm nửa khi WIP giảm nửa không?

**Gợi ý:** \(20/4=5\) ngày. Không bảo đảm vì throughput, biến thiên, loại work item và điều kiện hệ thống có thể thay đổi.

### Bài tập E — Scrum trên một sản phẩm

Ba Scrum Teams cùng làm một sản phẩm học tập; mỗi team có Product Backlog, Product Owner và DoD khác nhau. Họ đóng nhiều PBIs nhưng chưa có Increment tích hợp.

1. Theo Scrum Guide, nên làm rõ những commitment và artifact nào?
2. Một cuộc sync mới có đủ không nếu CI vẫn hỏng?
3. Khi nào cần hợp đồng API hoặc đổi cách chia story?

**Gợi ý:** Cùng Product Goal, Product Backlog, Product Owner và DoD khi cùng một sản phẩm; cải tiến integration, CI và ownership.

### Bài tập F — Nhiều sản phẩm phụ thuộc

Ứng dụng học viên và dịch vụ thanh toán là **hai sản phẩm có vòng đời, người dùng và owners riêng**, nhưng cùng cần một capability identity.

1. Có nên ép vào một Product Backlog chỉ vì cả hai dùng identity?
2. Capability chung nên có service interface thế nào?
3. Ai quyết định khi identity backlog bị tranh capacity?
4. Cần đo thêm time-to-unblock và security như thế nào?

**Gợi ý:** Không mặc định một backlog. Làm rõ platform/identity ownership, versioning, hỗ trợ, ưu tiên cross-product và người có thẩm quyền.

### Bài tập G — Shared specialist và demand

Một specialist xử lý 6 request/tuần nhưng demand trung bình 9 request/tuần, giả định cùng loại và ổn định.

1. Backlog sẽ biến động ra sao nếu không thay hệ thống?
2. Thêm một buổi họp triage có tự giải quyết được không?
3. Đề xuất một giải pháp **giảm demand**, một giải pháp **tăng năng lực**.
4. Guardrail nào cần để bảo mật không giảm?

**Gợi ý:** Tồn có xu hướng tăng 3 request/tuần. Tự phục vụ cho việc lặp, coaching/backups hoặc capacity bổ sung, risk-based review đúng policy.

### Bài tập H — Đánh giá một platform template

Platform phát hành golden path tạo staging, nhưng Developers vẫn phải gửi ticket cấp quyền và mất hai ngày mới dùng được.

1. Output và outcome khác nhau ở đâu?
2. Cần đo self-service task success như thế nào?
3. Cải tiến interface nào giúp bỏ chặn?
4. Khi nào vẫn phải có review quyền thủ công?

**Gợi ý:** Template tồn tại là output; môi trường tạo và sử dụng an toàn không cần thao tác hộ mới là capability/outcome. Quyền theo policy và ngoại lệ bảo mật vẫn được bảo vệ.

### Bài tập I — Scale pilot và sự thiên lệch

Một pilot được tăng hai chuyên gia và chỉ nhận story nhỏ; median cycle time giảm từ 18 xuống 8 ngày. Lãnh đạo muốn ép 30 team dùng y hệt mô hình.

1. Điều gì là tín hiệu tích cực?
2. Có những yếu tố nào khiến không thể suy rộng?
3. Nên thử ở đâu tiếp theo?
4. Chọn guardrails nào cho lần mở rộng?

**Gợi ý:** Ghi rõ điều kiện được cấp thêm capacity, mix công việc, DoD, quality và team context; đánh giá nhân rộng theo cơ chế có ích.

### Bài tập J — Kế hoạch migration xuyên nhóm

Producer checkpoint muốn xóa trường dữ liệu cũ trong khi mobile app chưa nâng cấp và có người học offline.

1. Vì sao chỉ một cuộc họp “đồng ý deploy thứ Sáu” không đủ?
2. Phác thảo expand–migrate–contract có kiểm tra phiên bản.
3. Ai sở hữu dữ liệu, contract, consumer, platform và rollback?
4. Nếu migration đã xóa dữ liệu, rollback code có khôi phục dữ liệu không?

**Gợi ý:** Phải tính tương thích old/new, backfill, observability và phục hồi dữ liệu riêng; rollback code không tự phục hồi dữ liệu.

### Bài tập K — Chi phí một cuộc họp mới

Một cuộc sync có 10 người × 30 phút × 3 lần/tuần. Tính giờ-người tham dự/tuần. Nêu ba điều ngoài con số giờ để đánh giá cơ chế có ích không.

**Gợi ý:** \(10\times0{,}5\times3=15\) giờ-người/tuần; xem time-to-unblock, chất lượng quyết định, ảnh hưởng Sprint Goal, rủi ro, chuẩn bị và chuyển ngữ cảnh.

### Bài tập L — Viết giả thuyết thay vì khẩu hiệu

Chuyển câu “Công ty cần SAFe/LeSS/Nexus ngay vì có nhiều team” thành một **thẻ thử nghiệm** gồm vấn đề, cơ chế, phạm vi, owner, metric, guardrails và mốc review.

**Gợi ý:** Có thể bắt đầu “Trong luồng Học tiếp, 40% thời gian item bị chờ do contract API chưa rõ; thử contract review khi refinement + automated checks trên một producer/consumer pair; đo waiting time, lỗi tích hợp và time-to-DoD.” Con số 40% chỉ dùng nếu đã quan sát thật; nếu chưa có, cần ghi kế hoạch baseline.

### Bài tập M — Trở ngại không thể giải cục bộ

Developers đã thử CI và story slicing, nhưng tất cả releases vẫn phải qua một cổng phê duyệt mơ hồ; đồng thời có yêu cầu audit theo hợp đồng.

1. Team có quyền tự bỏ cổng phê duyệt không?
2. Người nào có thể phân biệt nghĩa vụ thật với bước thừa?
3. Có thể tự động chuẩn bị bằng chứng nào?
4. Đo improvement mà vẫn bảo vệ audit bằng cách nào?

**Gợi ý:** Cần người có thẩm quyền policy/pháp lý; làm rõ điều kiện và evidence, đo waiting time và mức tuân thủ, không bỏ kiểm soát bắt buộc.

### Bài tập N — Outcome sản phẩm không đổi

Sau ba tháng scale, cycle time feature giảm nhưng người học mobile vẫn khó tìm Học tiếp.

1. Điều gì có thể đã cải thiện?
2. Vì sao product outcome chưa chắc tốt?
3. Cần thay giả thuyết UX hoặc Product Backlog như thế nào?
4. Có nên tiếp tục tăng số buổi họp coordination không?

**Gợi ý:** Có thể giữ các cải tiến flow/technical hữu ích, nhưng phải kiểm chứng tác vụ và thay thiết kế; thêm họp chỉ có ích khi giải quyết được một phụ thuộc thực.

## 30. Checklist trước khi quyết định mở rộng khuôn tổ chức

### A. Vấn đề và giá trị thực

- [ ] Có **người dùng/dòng giá trị xác định** mà chương trình phối hợp cần phục vụ.
- [ ] Có thể mô tả **trở ngại bằng quan sát**, không dùng “team chưa đủ Agile” như kết luận nguyên nhân.
- [ ] Phân biệt **activity/output/capability/outcome** trong mục tiêu chương trình.
- [ ] Đã xem **time-to-feedback và product outcome**, không chỉ tiến độ code.
- [ ] Những vấn đề an toàn/dữ liệu quan trọng được ưu tiên theo **severity**, không chờ hoàn tất quá trình tái tổ chức.

### B. Chẩn đoán và dữ liệu

- [ ] Đã theo dấu một số **work items thật** qua các bước và handoff quan trọng.
- [ ] Có **Definition of Workflow** hoặc ranh giới start/finish rõ cho mỗi số đo.
- [ ] Biết những nơi có **WIP cao, review waiting, blocked age và phụ thuộc lặp**.
- [ ] Đã xem chất lượng CI, DoD, integration và production incidents với bối cảnh phù hợp.
- [ ] Không kết luận chỉ từ một median, một cuộc khảo sát hoặc một Sprint đặc biệt.
- [ ] Có kiểm tra **work item types, độ biến thiên và nguyên nhân ngoài dự kiến**.
- [ ] Không dùng velocity/story points để so sánh hiệu suất xuyên team.
- [ ] Không đổi nghĩa Done hoặc chuyển blocked items ra ngoài để làm dashboard đẹp hơn.

### C. Quyền giải quyết đúng cấp

- [ ] Mỗi trở ngại được phân biệt **local, cross-team, platform/specialist hoặc systemic**.
- [ ] Mỗi trở ngại quan trọng có **owner đủ quyền** và đầu ra cần xác nhận.
- [ ] Team được phép tự cải tiến cách làm trong **quality/risk guardrails**.
- [ ] Những vấn đề ngoài quyền team có **escalation bằng bằng chứng**, không đổ lỗi hoặc để chờ vô hạn.
- [ ] Nếu nhiều Scrum Teams cùng một sản phẩm, **Product Goal, Product Backlog, Product Owner và DoD** chung được hiểu đúng.
- [ ] Nếu nhiều sản phẩm độc lập, có **service/product ownership và hợp đồng tương tác** rõ.
- [ ] Quyền đầu tư platform và xử lý priority conflicts được công bố.
- [ ] Sự cố nghiêm trọng có **incident roles, đường escalation và khả năng khôi phục**.

### D. Năng lực kỹ thuật và phối hợp

- [ ] User stories có thể được **chia theo lát cắt giá trị** thay vì chỉ lớp kỹ thuật.
- [ ] Có **CI/integration feedback** đáng tin và kiểm tra rủi ro quan trọng.
- [ ] Producer/consumer có **contract, versioning và policy tương thích** khi cần.
- [ ] Platform capability lặp có ứng viên **self-service/golden path** với support thực.
- [ ] Specialist được dùng cho vấn đề cần chiều sâu, có **coaching/backup** cho trường hợp có thể chuyển giao.
- [ ] Không biến review thủ công thành cổng bắt buộc khi rủi ro thấp và có phương án an toàn tốt hơn.
- [ ] Các cuộc họp cross-team tạo **quyết định hoặc gỡ blocker**, không chỉ đọc lại status.
- [ ] Dependency board chỉ chứa **việc thật sự chặn Increment**, có owner và next action.
- [ ] Chất lượng, phân quyền và tính đúng dữ liệu **không bị hạ** để tăng tốc.

### E. Quyết định scale và đánh giá

- [ ] Đã thử hoặc đánh giá khách quan **cơ chế nhẹ hơn** trước khi triển khai cấu trúc lớn.
- [ ] Có lý do rõ vì sao framework/cơ chế được chọn **giải quyết được trở ngại đã quan sát**.
- [ ] Đã tính **chi phí hội họp, phối hợp, đào tạo, tool và thay đổi reporting lines**.
- [ ] Có **pilot hoặc cách thử an toàn**, baseline, owner, timebox và guardrails.
- [ ] Có cơ chế **dừng, sửa hoặc bỏ** quy trình không tạo giá trị.
- [ ] Khi mở rộng, chọn **nguyên tắc có bằng chứng** và cho phép team thích ứng.
- [ ] Đã ghi **điều kiện đặc biệt của pilot** trước khi suy rộng.
- [ ] Có thể giải thích outcome người dùng, flow, quality và sustainability **đã thay đổi ra sao**.
- [ ] Mọi thay đổi ở cấp rộng có **người được trao thẩm quyền và cách kiểm tra hiệu quả**, không chỉ chỉ định vai trò.

**Nếu checklist có nhiều ô chưa đạt, không nhất thiết phải trì hoãn mọi phối hợp.** Hãy xác định **rủi ro nào phải xử lý ngay**, rào cản nào có thể thử giải trong nhóm và quyết định nào cần cấp cao hơn; sau đó chọn **bước nhỏ có giá trị nhất với bằng chứng rõ nhất**.

## 31. Hỏi đáp nhanh

### Có phải mỗi nhóm phải “làm Scrum chuẩn” rồi mới được phối hợp nhiều nhóm?

**Không.** Đội cần có năng lực và trách nhiệm phù hợp để tạo Increment đáng tin, nhưng những phụ thuộc liên nhóm hoặc nghĩa vụ tổ chức có thể cần xử lý ngay. Điều quan trọng là **không dùng mô hình cấp rộng để che những vấn đề cục bộ có thể giải trực tiếp**.

### Có phải số lượng team tăng đến một ngưỡng cố định thì phải dùng framework mở rộng?

**Không có ngưỡng tuyệt đối đúng mọi nơi.** Số team là một yếu tố; còn phụ thuộc kiến trúc, ranh giới sản phẩm, quyền quyết định, rủi ro và khả năng tự chủ quyết định **chi phí phối hợp**. Một số nhóm có interface tốt có thể ít cần họp hơn một tập nhỏ nhưng phụ thuộc chặt.

### Framework như SAFe, LeSS, Nexus hoặc Scrum@Scale có sai không?

**Không thể kết luận chỉ từ tên framework.** Chúng có những giả định/cơ chế tổ chức và chi phí khác nhau. Cần đánh giá **vấn đề cụ thể, điều kiện, rủi ro, quyền quyết định và kết quả có thể kiểm chứng**, không áp theo trào lưu hoặc phủ nhận máy móc.

### Vì sao không thể chỉ “nhân bản Scrum Team tốt”?

Vì hiệu quả có thể phụ thuộc **sản phẩm, kiến trúc, kỹ năng, thẩm quyền và hỗ trợ chuyên môn**. Nếu team pilot có CI tốt nhưng team mới chưa có môi trường thử, áp cùng lịch Scrum có thể **không tạo cùng kết quả**.

### Một team bị platform cản có nên tự khắc phục bằng cách bỏ phê duyệt không?

**Không nếu phê duyệt là nghĩa vụ hợp lệ hoặc vượt quyền.** Cần ghi ảnh hưởng, tìm policy owner và đề xuất **tự động hóa bằng chứng, tiêu chí theo rủi ro hoặc self-service có guardrails**. Tự chủ không đồng nghĩa bỏ kiểm soát an toàn.

### Nếu chỉ một nhóm bị chậm, có chắc không cần thay hệ thống?

**Chưa chắc.** Một lỗi hệ thống có thể chỉ xuất hiện ở nhóm đầu tiên sử dụng một capability hoặc một sản phẩm có rủi ro cao. Cần kiểm tra **nguyên nhân và độ rộng ảnh hưởng tiềm ẩn**, không dùng số team bị ảnh hưởng làm tiêu chí duy nhất.

### Nhiều Scrum Teams cùng một sản phẩm có cần chung Product Backlog?

Theo Scrum Guide, **có**: cùng một sản phẩm, nhiều Scrum Teams cần cùng Product Goal, Product Backlog, Product Owner và Definition of Done. Nếu thực chất là nhiều sản phẩm độc lập có phụ thuộc, cần thiết kế quan hệ giữa **các sản phẩm**, không ép ghép một backlog hình thức.

### Nếu đã có dependency board và số cuộc họp tăng mà blocker chưa giảm?

Đừng tự động thêm một cấp quản trị nữa. Hãy hỏi **owner có quyền quyết định không, thông tin còn thiếu gì, capacity nào đang bị vượt và cơ chế kỹ thuật nào có thể loại bỏ phụ thuộc**. Dữ liệu waiting time và những trường hợp thật sẽ chỉ ra bước tiếp.

### Khi nào tái cấu trúc team là lựa chọn hợp lý?

Khi có bằng chứng rằng **ranh giới hiện tại liên tục tạo handoff/tắc nghẽn**, và những biện pháp thấp rủi ro hơn không đủ hoặc không thể áp dụng. Cần kế hoạch chuyển ownership, vận hành, kiến thức và đo lại **flow, quality, cognitive load và product outcome**.

### Cách nào biết mình đang nhân rộng kết quả thay vì nhân rộng nghi thức?

Theo dõi **khả năng tạo Increment tích hợp, thời gian tới feedback, blocked age, chất lượng, giá trị người dùng và tính bền vững**. Nếu chỉ đếm số nhóm có role mới, số buổi planning hoặc giấy chứng nhận, bạn mới đo **mức áp dụng hình thức**.

## 32. Tài liệu tham khảo và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/) và [12 nguyên tắc Agile](https://agilemanifesto.org/principles.html): ưu tiên giá trị, hợp tác, giao phần mềm hoạt động, phản hồi và cải tiến liên tục.
- [The Scrum Guide](https://scrumguides.org/): Product Goal, Product Backlog, Product Owner, Sprint Goal, Definition of Done, Increment và các điều kiện khi nhiều Scrum Teams cùng phát triển một sản phẩm.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, work item age, cycle time, Service Level Expectation và quản lý flow.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): TDD, CI, refactoring, pairing và small releases.
- Matthew Skelton và Manuel Pais, *Team Topologies: Organizing Business and Technology Teams for Fast Flow* (2019): thiết kế ranh giới nhóm, cognitive load và interaction modes.
- Nicole Forsgren, Jez Humble và Gene Kim, *Accelerate: The Science of Lean Software and DevOps* (2018): các năng lực kỹ thuật/đo lường hỗ trợ hiệu suất giao phần mềm.
- Gene Kim, Jez Humble, Patrick Debois và John Willis, *The DevOps Handbook* (2016): flow, feedback và các cải tiến phát triển–vận hành.
- Mary và Tom Poppendieck, *Lean Software Development: An Agile Toolkit* (2003): tối ưu toàn hệ thống và loại bỏ lãng phí.
- Donald G. Reinertsen, *The Principles of Product Development Flow* (2009): hàng đợi, biến thiên, batch size và chi phí chậm trễ.
- [DORA](https://dora.dev/): nghiên cứu và tài nguyên về năng lực giao phần mềm, độ tin cậy, feedback kỹ thuật và cải tiến liên tục.
- [Google SRE Books](https://sre.google/books/): reliability, trách nhiệm service, monitoring và incident response.
- [Nexus Guide](https://www.scrum.org/resources/nexus-guide), [LeSS](https://less.works/), [Scrum@Scale](https://www.scrumatscale.com/), [SAFe](https://scaledagileframework.com/): tài liệu để nghiên cứu điều kiện và cơ chế mở rộng cụ thể; không phải danh sách bắt buộc triển khai.

### Năm nguyên tắc cần ghi nhớ

1. **Giá trị trước sơ đồ tổ chức.** Hãy tìm hành trình người dùng hoặc dòng công việc đang bị chậm, sai hay có rủi ro.
2. **Nguyên nhân trước framework.** Trở ngại có thể nằm trong team, giữa team, ở platform hoặc trong governance. Không có một cấp họp nào sửa hết.
3. **Năng lực kỹ thuật đi cùng phối hợp.** CI, tests, contract, DoD và lát cắt tích hợp thường tạo tiền đề cho phản hồi sớm; thiếu chúng, “scale” dễ chỉ làm chi phí đồng bộ tăng.
4. **Đúng quyền và vừa đủ cấu trúc.** Team giải việc trong quyền của mình; hệ thống cung cấp owner/capacity và quyết định cho những phụ thuộc vượt tầm team; không bỏ trách nhiệm an toàn.
5. **Mở rộng theo bằng chứng.** Đo flow, quality, product outcome và chi phí điều phối; giữ điều hữu ích, sửa điều chưa tốt, bỏ điều vô ích, rồi thử ở bối cảnh khác.

**Kết luận:** Sai lầm không nằm ở việc tổ chức có nhiều nhóm hoặc muốn phối hợp ở quy mô lớn. Sai lầm là **mặc định thêm khuôn tổ chức sẽ tạo hiệu quả khi chưa biết điều gì đang ngăn từng nhóm giao giá trị**. Một hệ thống Agile trưởng thành **giải trở ngại tại nơi có đủ quyền và bằng chứng, không buộc mọi team phải giống nhau**, đồng thời duy trì các cơ chế phối hợp cần thiết cho rủi ro và phụ thuộc thật.

**Điểm cần nhớ:** **Đừng mở rộng sự chờ đợi; hãy mở rộng khả năng học hỏi và giao giá trị.** Bắt đầu bằng một nút thắt có thật, thử cải tiến an toàn, kiểm tra kết quả người dùng và dòng công việc, rồi chỉ bổ sung cấu trúc khi chứng minh được rằng nó **giảm phụ thuộc, bảo vệ chất lượng và giúp phản hồi sớm hơn**.
