# Vận dụng Lean để nhận diện lãng phí và cải thiện dòng giá trị

## 1. Vì sao cần nhìn dòng giá trị thay vì chỉ nhìn tiến độ từng nhóm?

Một nhóm phát triển có thể liên tục tạo Pull Request, hoàn tất nhiều task và không có ai “rảnh”, nhưng người học vẫn phải chờ nhiều tuần để sử dụng được chức năng đăng ký khóa học. Một PBI được bàn giao qua phân tích, thiết kế, frontend, backend, kiểm thử, phê duyệt rồi phát hành. Thời gian viết mã chỉ chiếm một phần nhỏ; phần còn lại có thể nằm trong hàng đợi hoặc những vòng làm lại.

Ví dụ: sau khi Product Owner làm rõ yêu cầu **học viên đăng ký khóa miễn phí còn chỗ**, nhóm có thể làm những việc sau:

- Chờ một cuộc họp tuần sau để thống nhất thông báo khi hết chỗ.
- Chờ một chuyên gia duy nhất chấp thuận thay đổi API.
- Làm đồng thời tám user stories rồi mới tích hợp từng cái.
- Chờ môi trường kiểm thử có dữ liệu phù hợp.
- Phát hiện cuối đợt rằng retry sau timeout tạo đăng ký trùng.
- Chuyển sang vận hành một Increment chưa có cách theo dõi lỗi.

Không phải tất cả các bước trên đều vô ích. Việc kiểm tra quyền, nhất quán dữ liệu hoặc phê duyệt bắt buộc có giá trị bảo vệ người dùng. Tuy nhiên, **chờ vì chưa làm rõ hợp đồng, làm việc dở quá nhiều hoặc phát hiện lỗi muộn** là những cơ hội cải tiến.

**Lean** là một cách tư duy về giá trị, luồng công việc và cải tiến liên tục: hiểu điều khách hàng cần, nhìn toàn bộ dòng giá trị, giảm những hoạt động không tạo giá trị hoặc không bắt buộc, xây chất lượng vào quá trình và liên tục học từ thực tế.

Trong module **AGILE_DEVELOPMENT**, việc vận dụng Lean giúp lựa chọn cách phối hợp phù hợp giữa **user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc**, thay vì mặc định bổ sung thêm quy trình chỉ vì một nhóm đang chậm.

> **Nguyên tắc cốt lõi:** Không tối ưu riêng tốc độ của từng người hoặc số task được đóng. Hãy cải thiện **thời gian, chất lượng và mức giá trị** từ lúc xuất hiện nhu cầu thực tới khi người dùng nhận được kết quả đáng tin cậy.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích giá trị, dòng giá trị và những nguyên tắc Lean trong phát triển phần mềm.
2. Nhận diện **Muda (lãng phí)**, **Mura (không đều)** và **Muri (quá tải)** mà không quy lỗi cá nhân.
3. Phân biệt bảy dạng lãng phí truyền thống và dạng **không khai thác năng lực con người** thường được bổ sung trong mô hình tám loại.
4. Lập **Value Stream Map (VSM)** từ nhu cầu tới kết quả, đo thời gian thực hiện và chờ đợi.
5. Dùng WIP, work item age, throughput, cycle time và flow efficiency để đặt câu hỏi và thử cải tiến.
6. Chọn đối sách như giảm batch size, giới hạn WIP, làm rõ sớm, tự động hóa kiểm chứng, giảm bàn giao hoặc cải tiến kiến trúc.
7. Liên hệ Lean với **Scrum, Kanban, XP**, đồng thời giữ Definition of Done, bảo mật, dữ liệu và an toàn.
8. Thiết kế một thử nghiệm cải tiến có baseline, giả thuyết, thước đo và guardrails.

### 1.2. Lean không phải “cắt người, cắt kiểm thử, cắt tài liệu”

Nhiều lãng phí tồn tại vì hệ thống tổ chức công việc, không phải vì một người nào đó thiếu cố gắng. Đúng tinh thần cải tiến:

- **Loại bỏ chờ đợi không cần thiết**, không phải loại bỏ thời gian nghĩ và học.
- **Giảm làm lại**, không phải bỏ review/test để báo Done sớm.
- **Giảm tài liệu không ai dùng**, không phải bỏ tài liệu quyết định, bảo mật, vận hành hoặc hợp đồng cần thiết.
- **Giảm công việc dở**, không phải ép một người làm liên tục với công suất tối đa.
- **Tôn trọng con người**, tạo điều kiện phản hồi và cải tiến, không dùng “waste” làm nhãn tiêu cực cho nhân viên.

Một thay đổi khiến số task Done tăng nhưng đồng thời **tăng lỗi dữ liệu đăng ký, tăng giờ trực đêm hoặc đẩy việc kiểm thử sang support** không thể được gọi là cải tiến chỉ vì dashboard đẹp hơn.

## 2. Giá trị, dòng giá trị và năm nguyên tắc Lean

### 2.1. Giá trị được xác định từ góc nhìn người nhận

Với nền tảng học trực tuyến, người học thường không yêu cầu “ba endpoint mới” hay “mười hai bảng dữ liệu”. Họ muốn **xem khóa phù hợp, đăng ký thành công và biết chắc mình có thể tham gia**.

| Việc nhóm thực hiện | Output | Giá trị/nguy cơ cần kiểm chứng |
| --- | --- | --- |
| Tạo API ghi đăng ký | Endpoint và code | Có giúp học viên đăng ký chính xác không? |
| Viết test hai người tranh chỗ cuối | Test cases và kết quả CI | Có bảo vệ dữ liệu không vượt sức chứa không? |
| Làm màn hình tra trạng thái | Giao diện | Sau timeout người học có biết tình trạng thật không? |
| Thêm cuộc họp trạng thái | Biên bản/cuộc họp | Có gỡ quyết định hoặc phụ thuộc nào không? |
| Chạy lại test bằng tay nhiều lần vì flaky | Giờ công và log | Có đang che nguyên nhân không ổn định? |

**Output không đồng nghĩa outcome**. Một tính năng được phát hành là output; người học tự hoàn tất tác vụ đáng tin cậy mới là outcome cần quan sát.

### 2.2. Năm nguyên tắc Lean thường dùng

| Nguyên tắc | Ý nghĩa thực hành | Câu hỏi cho đội Agile |
| --- | --- | --- |
| **Specify value – Xác định giá trị** | Hiểu nhu cầu, kết quả và những điều kiện bảo vệ người dùng. | Giá trị nào khiến PBI này đáng làm? |
| **Identify the value stream – Nhận diện dòng giá trị** | Xem mọi bước từ nhu cầu tới việc tạo giá trị, kể cả chờ và làm lại. | Người học phải chờ qua những điểm nào? |
| **Create flow – Tạo dòng chảy** | Giảm ngắt quãng, chuyển giao thừa, batch lớn và blocker. | Có thể đưa phần giá trị qua hệ thống đều hơn không? |
| **Establish pull – Thiết lập kéo việc theo năng lực** | Chỉ bắt đầu việc mới khi có năng lực và điều kiện tiếp nhận phù hợp. | Vì sao ta mở việc mới khi item đang dở chưa Done? |
| **Pursue perfection – Liên tục cải tiến** | Lặp vòng quan sát, giả thuyết, thử nghiệm, học hỏi. | Kết quả thay đổi có thực sự tốt hơn không? |

“Perfection” là **hướng cải tiến liên tục**, không phải lời hứa hệ thống sẽ không bao giờ có lỗi. Không đợi mọi vấn đề được giải quyết mới giao Increment hữu ích, nhưng cũng không hợp thức hóa lỗi nghiêm trọng.

### 2.3. Dòng giá trị và workflow khác nhau ở đâu?

- **Workflow** mô tả các bước xử lý công việc, ví dụ Ready → Developing → Review → Verify → Done.
- **Value stream** nối chuỗi hoạt động rộng hơn tới nhu cầu và giá trị, ví dụ người học gặp vấn đề → ghi nhận nhu cầu → chọn giải pháp → xây/kiểm chứng → phát hành → người dùng sử dụng → học từ phản hồi.
- **Value Stream Mapping (VSM)** là kỹ thuật trực quan hóa các bước, thời gian, hàng đợi, chuyển giao, thông tin và vấn đề để tìm cơ hội cải tiến.

Một nhóm có thể có bảng Kanban rất rõ nhưng chỉ đo từ **lúc bắt đầu code tới lúc merge**. Nó có thể bỏ lỡ hàng tuần chờ quyết định nghiệp vụ ở đầu hoặc chờ release ở cuối. VSM giúp hỏi: **ranh giới nào cần nhìn để hiểu giá trị thật?**

### 2.4. Ba loại hoạt động trong VSM

Một cách phân loại thực dụng:

1. **Tạo giá trị trực tiếp:** thay đổi mà người dùng/khách hàng đánh giá có ích, ví dụ tạo hành vi đăng ký đúng.
2. **Không trực tiếp tạo giá trị nhưng hiện bắt buộc/cần thiết:** kiểm thử bảo mật, đối chiếu dữ liệu, phê duyệt pháp lý hay ghi log theo rủi ro và điều kiện thực.
3. **Lãng phí có thể giảm hoặc loại bỏ:** chờ một thông tin đã có nhưng không được chia sẻ, nhập lại cùng dữ liệu nhiều lần, sửa lỗi do hợp đồng không rõ, hoặc xử lý hàng đợi thừa.

Không phải mọi công việc kỹ thuật **không hiển thị với người dùng** là lãng phí. Refactoring, kiểm thử, observability, bảo trì và học kỹ năng có thể là **đầu tư thiết yếu giúp giá trị được giao tin cậy trong tương lai**.

## 3. Ba nguồn vấn đề của Lean: Muda, Mura, Muri

### 3.1. Muda – lãng phí

**Muda** là hoạt động tiêu tốn nguồn lực mà không tạo giá trị hoặc không cần thiết trong bối cảnh. Trong phát triển phần mềm, nhiều dạng muda khó thấy:

- Thời gian chờ người khác review.
- Test bị chạy lại vì môi trường không ổn định.
- Tạo tính năng mà không ai sử dụng.
- Tài liệu chép tay từ nguồn dữ liệu tự động đã có.
- Quay lại sửa hợp đồng API do không trao đổi sớm.

Khi nhận diện muda cần hỏi **“vì sao hệ thống tạo ra nó?”** thay vì **“ai đã gây ra lãng phí?”**.

### 3.2. Mura – công việc không đều, biến động

**Mura** là sự không đều trong dòng công việc hoặc nhu cầu:

- Đầu Sprint PBI chờ refinement; cuối Sprint test/merge dồn cục.
- Mọi nhóm gửi yêu cầu review vào chiều thứ Sáu.
- Nhiều incident khẩn chen vào khi công việc thường ngày đã đầy WIP.
- Vendor chỉ cấp sandbox một ngày/tháng, tạo batch tích hợp lớn.

Mura có thể góp phần tạo hàng đợi và áp lực. Nhưng không phải mọi biến động đều tránh được: khối lượng công việc tri thức và nhu cầu người dùng có yếu tố bất định. Mục tiêu là **làm biến động có thể nhìn thấy và điều chỉnh công suất, batch, policy và mức dự phòng hợp lý**.

### 3.3. Muri – quá tải

**Muri** là tình trạng yêu cầu vượt khả năng xử lý bền vững của hệ thống hoặc con người:

- Một reviewer duy nhất phải duyệt tất cả PR của ba nhóm.
- Kỹ sư trực sự cố cả đêm nhưng vẫn bị ép hoàn tất nguyên Sprint plan.
- CI runner liên tục xếp hàng vì mức tải vượt công suất.
- Một nhóm mở đồng thời nhiều PBI và đổi ngữ cảnh liên tục.

Tăng công suất sử dụng lên gần 100% **không bảo đảm hoàn tất nhanh hơn**. Khi dòng việc biến động, thiếu khoảng trống để xử lý biến động thường làm hàng đợi lớn, phản hồi chậm và áp lực tăng.

### 3.4. Ba khái niệm liên quan nhưng không đồng nhất

~~~mermaid
flowchart LR
    A["Mura: công việc dồn cục / biến động"] --> B["Muri: quá tải tại một điểm"]
    B --> C["Muda: chờ đợi / làm lại / chuyển ngữ cảnh"]
    C -. "Phản hồi yếu làm tích tụ thêm" .-> A
    D["Cải tiến flow, WIP, capacity và chất lượng"] -. "Giảm cả ba" .-> A
    D -. "Giảm cả ba" .-> B
    D -. "Giảm cả ba" .-> C
~~~

Đây là sơ đồ **quan hệ có thể xảy ra**, không phải quy luật rằng cứ có mura thì luôn sinh muri. Một đội nên **quan sát dữ liệu và điều kiện thực** trước khi quy nguyên nhân.

### 3.5. Tôn trọng con người là một giới hạn của cải tiến

Một thử nghiệm “giảm waste” nhưng buộc Developers bỏ nghỉ, liên tục làm thêm giờ hoặc che đi khả năng nêu lỗi đã **chuyển chi phí từ một chỉ số sang sức khỏe và chất lượng**. Đánh giá cải tiến cần chú ý tải công việc, khả năng xin giúp, thời gian tập trung và chất lượng lâu dài.

## 4. Bảy dạng lãng phí truyền thống và dạng thứ tám thường dùng

Lean sản xuất thường nói tới **bảy dạng lãng phí**: transportation, inventory, motion, waiting, overproduction, overprocessing và defects. Trong nhiều chương trình cải tiến, một dạng thứ tám được bổ sung là **không khai thác tài năng/năng lực con người**. Cách ánh xạ sang phần mềm là **công cụ thảo luận**, không phải phân loại chuẩn duy nhất.

| Loại lãng phí | Biểu hiện trong phát triển phần mềm | Dấu hiệu cần quan sát | Ví dụ đối sách |
| --- | --- | --- | --- |
| **Transportation – Chuyển giao** | PBI qua nhiều nhóm, thông tin qua nhiều hệ thống, mỗi bên phải giải thích lại bối cảnh. | Nhiều handoff, ticket trả đi trả lại. | Nhóm liên chức năng, hợp đồng rõ, cùng refinement. |
| **Inventory – Tồn kho** | Backlog chưa kiểm chứng quá lớn, PR mở lâu, nhiều feature dở, code chờ release. | WIP, item age, số việc làm dở, nhánh sống lâu. | Giới hạn WIP, ưu tiên hoàn tất, giảm batch size. |
| **Motion – Thao tác/tìm kiếm không cần thiết** | Dev tìm log, quyền, tài liệu, build, hỏi nhiều nơi để biết trạng thái. | Thời gian tìm thông tin, nhiều chuyển ngữ cảnh. | Tăng khả năng truy vết, tài liệu đúng chỗ, self-service. |
| **Waiting – Chờ đợi** | Chờ review, CI, môi trường, quyết định, đối tác. | Blocked time, queue age, thời gian idle của PBI. | Làm rõ sớm, capacity dự phòng, policies rõ. |
| **Overproduction – Sản xuất vượt nhu cầu** | Xây tính năng chưa được xác minh cần thiết, tạo hàng loạt báo cáo không ai đọc. | Feature ít sử dụng, backlog tăng không gắn outcome. | Phản hồi sớm, MVP/lát cắt có mục đích, ưu tiên giá trị. |
| **Overprocessing – Xử lý quá mức** | Nhiều vòng phê duyệt tương đương, định dạng lại dữ liệu thủ công, test trùng lặp không tăng phát hiện. | Nhiều bước không có quyết định mới hoặc bằng chứng mới. | Làm rõ mục đích kiểm soát, tự động hóa phù hợp. |
| **Defects – Sai lỗi/làm lại** | Sai nghiệp vụ, lỗi API contract, test flaky, đăng ký trùng, quyền sai. | Rework, escaped defects, sự cố, vòng trả lại. | TDD, CI, test theo rủi ro, DoD, review sớm. |
| **Unused talent – Chưa tận dụng năng lực** | Người thấy lỗi không được nêu, chuyên môn không được dùng, quyết định áp từ trên xuống. | Ý tưởng bị bỏ, skill bottleneck, thiếu tiếng nói người làm. | Tự quản lý, pairing, học hỏi, lãnh đạo phục vụ. |

### 4.1. Transportation khác Motion

Trong môi trường phần mềm:

- **Transportation** chủ yếu liên quan **bàn giao đầu ra, dữ liệu hoặc trách nhiệm giữa các bộ phận/địa điểm xử lý**.
- **Motion** tập trung **những thao tác không cần thiết để tìm, di chuyển, chuyển công cụ hoặc lấy thông tin khi đang làm việc**.

Ví dụ, chuyển một ticket giữa QA → backend → DBA → support là **transportation/handoff**. Developer mất 40 phút tìm đúng dashboard, quyền truy cập và log để điều tra một lỗi là **motion/search overhead**. Hai loại có thể cùng xuất hiện.

### 4.2. Inventory trong phần mềm không chỉ là “code chưa dùng”

Những thứ đang chờ hoàn tất có thể gồm:

- PBI đã bắt đầu nhưng chưa đạt DoD.
- Nhánh mã dài ngày chưa tích hợp.
- PR chờ reviewer.
- Những giả định sản phẩm chưa được kiểm chứng.
- Tính năng đã hoàn thiện nhưng chưa thể release theo điều kiện thực.
- Hàng đợi sửa lỗi hồi quy.

Không nên đếm **mọi PBI chưa chọn trong Product Backlog** là WIP như nhau; **Product Backlog** phản ánh các nhu cầu và lựa chọn được sắp thứ tự, còn **WIP** phải có mốc bắt đầu/kết thúc theo workflow được định nghĩa. Một backlog lớn có thể có chi phí duy trì và rủi ro lỗi thời, nhưng cần phân biệt với item đã bắt đầu.

### 4.3. Overproduction và overprocessing có thể bị nhầm

- **Overproduction:** tạo *thứ chưa có nhu cầu tương ứng* hoặc quá sớm. Ví dụ xây mười biến thể trang đăng ký chưa có bằng chứng người dùng cần.
- **Overprocessing:** làm *quá nhiều bước/độ hoàn thiện* cho một nhu cầu đã chọn mà không tăng giá trị hoặc đảm bảo cần thiết. Ví dụ tạo ba báo cáo giống nhau từ cùng dữ liệu vì ba bộ phận dùng định dạng khác nhưng không cần.

Một hệ thống an toàn có thể cần nhiều lớp kiểm chứng; **không đánh dấu kiểm thử bảo mật là overprocessing chỉ vì mất thời gian**. Cần hỏi liệu bước đó có phát hiện/giảm rủi ro độc lập và là nghĩa vụ bắt buộc hay không.

### 4.4. Defects thường kéo theo các lãng phí khác

Một lỗi **đăng ký trùng** có thể tạo:

1. Ticket support và điều tra (**motion/waiting**).
2. Bản sửa và kiểm thử lại (**defect/rework**).
3. PR mới chờ review (**inventory/waiting**).
4. Đội vận hành phải sửa dữ liệu (**handoff/overprocessing**).
5. Người học mất tin tưởng, không hoàn tất đăng ký (**outcome xấu**).

Do đó giảm lỗi tại nguồn nhiều khi **cắt cả chuỗi lãng phí phía sau**, không phải chỉ làm xanh một báo cáo chất lượng.

## 5. Khi nào một hoạt động là cần thiết, không phải lãng phí?

### 5.1. Kiểm soát bắt buộc phải được phân tích đúng

| Hoạt động | Có thể cần thiết vì | Cách cải thiện đúng |
| --- | --- | --- |
| Kiểm tra phân quyền | Bảo vệ dữ liệu học viên. | Tự động hóa auth tests, làm rõ policy sớm; **không bỏ kiểm tra**. |
| Kiểm thử concurrency | Bảo vệ sức chứa và tính toàn vẹn giao dịch. | Tạo môi trường/test dữ liệu tin cậy, kiểm tra sớm. |
| Review thay đổi nhạy cảm | Giảm rủi ro bảo mật/tuân thủ. | Làm rõ đầu vào, người có quyền, phản hồi kịp thời. |
| Ghi decision log | Truy vết quyết định có ảnh hưởng lâu dài. | Ghi ngắn, dùng link, không lặp dữ liệu không cần. |
| Đào tạo kỹ thuật khó | Giảm phụ thuộc và sai lỗi dài hạn. | Pairing theo việc thật, học theo nhu cầu. |
| Dành năng lực xử lý incident | Bảo đảm vận hành và khôi phục. | Dự phòng công suất, kênh hỗ trợ và runbook rõ. |
| Refactoring | Giữ khả năng thay đổi an toàn. | Làm nhỏ, có test, gắn rủi ro và giá trị về sau. |

“Không trực tiếp tạo feature” **không đồng nghĩa lãng phí**. Lean xem **giá trị của toàn hệ thống và chi phí rủi ro**, không chỉ số giờ bàn phím.

### 5.2. Phân loại cần bối cảnh thực

Một cuộc họp refinement có thể:

- **Tạo giá trị hỗ trợ** nếu giúp phát hiện quy tắc hết chỗ và tránh lỗi đắt đỏ.
- **Là overprocessing** nếu nội dung đã được chốt và không có vấn đề mới.
- **Là waiting** nếu quyết định luôn hoãn sang cuộc họp kế tiếp chỉ vì thiếu người có quyền.

Vì vậy, cần xem **bằng chứng hoạt động đó thực sự đóng góp** và thay đổi nào có thể giảm chi phí mà vẫn giữ lợi ích.

## 6. Chọn một dòng giá trị để lập bản đồ (Value Stream Mapping)

### 6.1. Đặt ranh giới bắt đầu và kết thúc

Nếu mục tiêu là cải thiện khả năng giao giá trị đăng ký khóa học, ranh giới có thể là:

**Bắt đầu:** nhóm chọn một nhu cầu đã hiểu đủ để bắt đầu làm.

**Kết thúc:** người dùng đủ điều kiện có thể thực hiện hành vi đăng ký chính xác trên sản phẩm được phát hành theo policy.

Đây chỉ là một lựa chọn. Để điều tra **idea-to-value lead time**, cần bắt đầu sớm hơn từ lúc vấn đề được ghi nhận. Để điều tra **development cycle time**, có thể dùng Started → Done theo Definition of Workflow. Không được so số liệu từ hai ranh giới khác nhau rồi tuyên bố năng suất tăng.

### 6.2. Đơn vị đo phải đồng nhất

Chọn một loại đơn vị:

- PBI **lát cắt dọc** liên quan cùng hành trình.
- Yêu cầu sửa lỗi có severity tương đương.
- Một thay đổi phần mềm từ code commit tới production.
- Một yêu cầu support từ tiếp nhận tới giải quyết.

**Không trộn không phân loại** một PBI nhỏ một ngày với dự án đổi dữ liệu ba tháng rồi dùng một trung bình duy nhất để mô tả “dòng giá trị”.

### 6.3. Theo dõi một hạng mục thật qua các bước

Một VSM nên ghi:

1. Hoạt động tạo kết quả ở bước nào?
2. Khi nào hạng mục **vào hàng đợi** và khi nào có người bắt đầu?
3. Thời gian làm việc trực tiếp (**touch/process time**) bao lâu?
4. Thời gian chờ theo định nghĩa bao lâu?
5. Ai nhận đầu ra hoặc có quyền quyết định?
6. Có vòng trả lại/defect/rework nào?
7. Bao nhiêu hạng mục đang chờ tại bước ấy?
8. Có chính sách hoặc ràng buộc an toàn nào cần giữ?

Hãy quan sát lịch sử ticket, PR, CI, môi trường, log và trao đổi với người thực hiện. Một bản đồ dựa toàn bộ vào **mô tả quy trình trên giấy** có thể bỏ qua hàng đợi thực tế.

### 6.4. Gemba trong phát triển phần mềm

**Gemba** thường được hiểu là tới nơi công việc thực sự diễn ra. Trong phần mềm, điều đó có thể là:

- Theo một PBI từ khi được chọn tới lúc kiểm chứng trên bản tích hợp.
- Quan sát Developers tìm thông tin khi test bị đỏ.
- Cùng QA xem vì sao một kịch bản phải kiểm tra lại nhiều lần.
- Xem support xử lý ticket “đăng ký thành công chưa?” với dữ liệu được phép.
- Xem người học thực hiện tác vụ trong phiên quan sát có sự đồng ý.

Mục đích là **hiểu hệ thống và giúp người làm giải quyết vấn đề**, không tìm cá nhân “làm lãng phí” để xử phạt.

## 7. Value Stream Map trạng thái hiện tại: nhìn cả thời gian làm và thời gian chờ

### 7.1. Một dòng giá trị minh họa

Xét một lát cắt nghiệp vụ: **học viên đã đăng nhập có thể đăng ký khóa học miễn phí còn chỗ, với trạng thái chính xác và các kiểm tra chất lượng cần thiết**.

Một nhóm đã khảo sát một số hạng mục tương đương và dựng **một ví dụ minh họa** về luồng tuần tự như sau. Những số liệu này **không phải dữ liệu dự án thật**; mục đích là học cách lập bản đồ và tính toán.

| Bước | Touch/process time | Waiting/queue time | Vì sao phải chờ trong ví dụ? |
| --- | ---: | ---: | --- |
| **1. Làm rõ nhu cầu** | 0,5 ngày | 2 ngày | Chờ đúng người ra quyết định hoặc cuộc họp refinement. |
| **2. Thống nhất hợp đồng/thiết kế** | 0,5 ngày | 2,5 ngày | Web và API chuyển yêu cầu nhiều vòng. |
| **3. Phát triển lát cắt** | 1,5 ngày | 2 ngày | Nhiều item cùng mở, đổi ngữ cảnh và thiếu môi trường. |
| **4. Review và CI** | 0,5 ngày | 1,5 ngày | PR chờ người review, CI runner xếp hàng. |
| **5. Tích hợp và kiểm chứng** | 1 ngày | 3 ngày | Sandbox/test data chưa sẵn; lỗi hợp đồng phát hiện muộn. |
| **6. Release và xác minh** | 0,5 ngày | 2 ngày | Chờ cửa sổ được phép và người có quyền quyết. |
| **Tổng, theo giả định tuần tự** | **4,5 ngày** | **13 ngày** | **17,5 ngày lịch/đơn vị thời gian được quy ước**. |

Trong ví dụ, các khoảng **không chồng lấn** và dùng cùng một đơn vị. Nếu thực tế nhóm có làm song song, các khoảng chờ và active không được cộng trực tiếp thành lead time nếu chúng trùng nhau.

### 7.2. Bản đồ dòng giá trị với hai loại thời gian

~~~mermaid
flowchart LR
    A["Làm rõ nhu cầu<br/>Làm 0,5 | Chờ 2"] -->
    B["Hợp đồng<br/>Làm 0,5 | Chờ 2,5"] -->
    C["Phát triển<br/>Làm 1,5 | Chờ 2"] -->
    D["Review / CI<br/>Làm 0,5 | Chờ 1,5"] -->
    E["Tích hợp / kiểm chứng<br/>Làm 1 | Chờ 3"] -->
    F["Release / xác minh<br/>Làm 0,5 | Chờ 2"]
~~~

Trong Markdown/Mermaid, sơ đồ ở đây chỉ thể hiện **thứ tự và thời gian minh họa**, không chứng minh mọi thay đổi thực sẽ đi lần lượt như thế. VSM thực tế nên ghi thêm điểm **quay lại sửa**, số item trong hàng đợi, ai quyết, các ràng buộc và bất định.

### 7.3. Tính flow efficiency (hiệu suất dòng chảy)

Một cách diễn giải thường dùng:

\[
\text{Flow efficiency}
=\frac{\text{Active/process time}}{\text{Total elapsed time}}\times100\%.
\]

Áp dụng cho ví dụ **tuần tự với định nghĩa active time nhất quán**:

\[
\frac{4,5}{4,5+13}\times100\%
=\frac{4,5}{17,5}\times100\%
\approx25,7\%.
\]

Nghĩa là trong **mô hình minh họa**, khoảng một phần tư thời gian từ bắt đầu tới kết thúc là thời gian trực tiếp xử lý hạng mục, còn lại ở trạng thái chờ theo cách chia đã chọn.

**Cảnh báo khi diễn giải:**

- Con số 25,7% **không phải chỉ số năng suất nhân viên**.
- Một khoảng “active” có thể gồm test hoặc kiểm soát bắt buộc; không nên xóa nó để tăng tỉ số.
- Khi có hoạt động song song, cần quy ước cách tính **elapsed time**, không cộng nhân công song song thành thời gian lịch.
- Tỉ số tăng không tự chứng minh **khách hàng nhận giá trị hơn**; phải xem chất lượng, độ tin cậy và outcome.
- Các luồng công việc khác nhau không thể so flow efficiency công bằng nếu định nghĩa thời gian khác.

### 7.4. Chọn điểm nghẽn bằng bằng chứng thay vì cảm giác

Từ bảng trên, nhóm có thể đặt giả thuyết:

1. **Chờ kiểm thử tích hợp 3 ngày** có phải do sandbox/test data?
2. **Chờ hợp đồng 2,5 ngày** có phải do quyết định hoặc ví dụ nghiệp vụ chưa rõ?
3. **Chờ release 2 ngày** có phải là cửa sổ bắt buộc hay lịch duyệt có thể cải tiến?
4. **Chờ phát triển 2 ngày** có liên quan WIP cao và chuyển ngữ cảnh?

Không nên kết luận “người kiểm thử là bottleneck” chỉ vì bước Verify có waiting lớn. Có thể nguyên nhân thực là **môi trường, cách chia PBI hoặc việc ghép muộn**.

### 7.5. Xem vòng làm lại trên bản đồ

~~~mermaid
flowchart LR
    A["Refinement"] --> B["Code + review"]
    B --> C["Integration test"]
    C --> D{"Đạt hành vi và DoD?"}
    D -- "Chưa: lệch contract, lỗi dữ liệu" --> B
    D -- "Đạt" --> E["Increment đủ điều kiện"]
~~~

Nếu một PBI đi qua vòng **Code → Verify → Rework** ba lần, chỉ tính “lần đi cuối” sẽ bỏ qua chi phí học muộn. VSM cần thể hiện các vòng tái xử lý và nguyên nhân, không chỉ chuỗi lý tưởng.

## 8. Thiết kế VSM trạng thái tương lai: cải thiện ở cấp hệ thống

### 8.1. Không được vẽ trạng thái tương lai bằng cách xóa bước bắt buộc

Một future-state map tốt cần trả lời:

1. Bước nào **không tạo giá trị và không bắt buộc**, có thể bỏ?
2. Bước nào cần **giữ** vì chất lượng, dữ liệu, quyền hoặc compliance?
3. Có thể **tự động hóa/đưa kiểm chứng tới sớm** thay vì làm lại sau?
4. Có thể **giảm hàng đợi** bằng cách kéo ít việc hơn và giúp hoàn tất?
5. Có thể **giảm batch size** hoặc thiết kế nhóm/hợp đồng cho ít bàn giao hơn?
6. Nếu giảm chờ một bước, có dồn WIP sang bước khác không?

Không cần áp một “quy trình Lean chuẩn” bất biến. Trạng thái tương lai là **giả thuyết cải tiến có thể thử và điều chỉnh**.

### 8.2. Một phương án tương lai có kiểm soát

Ví dụ nhóm thử:

- Có phiên làm rõ **Three Amigos** ngắn đúng người trước khi bắt đầu một PBI nhiều rủi ro.
- Viết ví dụ nghiệp vụ và hợp đồng API sớm, dùng **contract tests**.
- Giới hạn WIP, ưu tiên giúp hoàn tất item đang chờ.
- Chạy test theo rủi ro và tích hợp thường xuyên, cấp test data/môi trường qua template được phép.
- Tự động hóa review/checks phù hợp nhưng **giữ review bắt buộc**.
- Chuẩn bị release readiness trong quá trình xây, không đợi tới ngày cuối.

Một **trạng thái mục tiêu giả định** (không phải dự báo chắc chắn) có thể là:

| Bước | Active time mục tiêu | Waiting time mục tiêu | Cải tiến thử |
| --- | ---: | ---: | --- |
| **1. Làm rõ** | 0,5 ngày | 0,5 ngày | Quyết định và acceptance examples được làm rõ sớm. |
| **2. Hợp đồng** | 0,5 ngày | 0,5 ngày | Contract rõ, ít vòng hỏi lại. |
| **3. Phát triển** | 1,25 ngày | 1 ngày | Lát cắt nhỏ, WIP thấp và ít đổi ngữ cảnh. |
| **4. Review/CI** | 0,5 ngày | 0,5 ngày | PR nhỏ, người review dự phòng đủ quyền, CI tin cậy. |
| **5. Tích hợp/test** | 0,75 ngày | 1,5 ngày | Kiểm chứng từ sớm, test tự động và môi trường ổn định. |
| **6. Release/xác minh** | 0,5 ngày | 1,5 ngày | Readiness từ đầu, vẫn tôn trọng cửa sổ/quyền bắt buộc. |
| **Tổng mục tiêu, giả định tuần tự** | **4 ngày** | **5,5 ngày** | **9,5 ngày**. |

Flow efficiency mục tiêu theo cùng cách tính:

\[
\frac{4}{9,5}\times100\%\approx42,1\%.
\]

Và lead time mô hình giảm:

\[
17,5-9,5=8\text{ ngày}.
\]

Đây **là những con số thiết kế giả định để đặt mục tiêu học hỏi**, không phải cam kết rằng chỉ cần giới hạn WIP và làm contract tests sẽ giảm đúng tám ngày. Khi thử thực tế, cần quan sát nhiều item có đặc điểm tương đương và guardrails.

### 8.3. Nhận diện cải thiện thực hay “dời hàng đợi”

Ví dụ:

- Frontend giảm chờ review từ 2 ngày xuống 0,5 ngày.
- Backend lại phải review tất cả contract gấp và tồn hàng đợi 5 ngày.
- Tổng thời gian từ nhu cầu tới sản phẩm sử dụng được **không giảm**.

Đó có thể là **tối ưu cục bộ**, không phải Lean cải thiện value stream. Nên đo cả **đầu–cuối**, xem gánh nặng provider, quality và support, rồi mới quyết định duy trì thay đổi.

### 8.4. Lộ trình cải tiến theo rủi ro

Không thay đồng thời mọi bước nếu không cần. Có thể đi từ:

1. Quan sát dữ liệu thật.
2. Chọn một hàng đợi lớn, lặp lại và có thể cải thiện.
3. Đặt giả thuyết cơ chế.
4. Thử ở phạm vi nhỏ với DoD không đổi.
5. So kết quả và yếu tố gây nhiễu.
6. Duy trì/điều chỉnh/hoàn tác, rồi chọn điểm nghẽn tiếp theo.

Một hệ thống cải thiện ở bước này có thể làm **bước khác trở thành bottleneck mới**. Đó là điều bình thường khi phát triển năng lực hệ thống.

## 9. WIP, hàng đợi và giới hạn năng lực

### 9.1. Vì sao mọi người bận chưa chắc công việc hoàn tất nhanh?

Giả sử một team có 4 Developers và 12 PBI đang dở:

- Mỗi người chuyển qua nhiều item mỗi ngày.
- Review nhận batch PR cuối tuần.
- Test tích hợp chờ nhiều phiên bản cùng thay đổi.
- Khi một item bị chặn, người làm kéo item mới thay vì giúp gỡ blocker.

**Số việc mở nhiều** tạo cảm giác luôn bận nhưng giá trị chỉ xuất hiện khi **các hạng mục đáp ứng điều kiện Finished/Done**. WIP cao có thể kéo dài chờ, tăng đổi ngữ cảnh và phát hiện lỗi muộn.

### 9.2. Push và Pull

- **Push:** giao thêm việc vào một bước dù bước tiếp theo chưa có năng lực nhận. Ví dụ cứ mở user story mới khi Verify đã tồn 10 item.
- **Pull:** bước có năng lực phù hợp **kéo** hạng mục tiếp theo theo chính sách rõ. Khi WIP đầy, nhóm ưu tiên giúp hoàn tất, xử lý blocker và cải thiện chất lượng thay vì mở thêm.

**Pull không có nghĩa Developers không bao giờ được làm việc mới khi có một item bị chặn**. Nhóm cần policy cho blocker, mức khẩn, loại việc, phụ thuộc và công suất; mục tiêu là hạn chế quá tải, không tạo ra chờ không cần thiết.

### 9.3. Giới hạn WIP là một giả thuyết điều hành, không phải con số thần kỳ

Ví dụ một nhóm thử **WIP limit = 4** cho vùng Developing + Verify:

1. Định nghĩa rõ item nào được đếm vào vùng.
2. Khi đầy, ưu tiên giúp review/test hoặc gỡ blocker đang tồn tại.
3. Có quy tắc xử lý incident hoặc công việc cấp bách theo thẩm quyền.
4. Công khai trường hợp vượt giới hạn và vì sao.
5. Theo dõi work item age, cycle time, throughput, chất lượng và tải người làm.
6. Điều chỉnh nếu giả thuyết không được dữ liệu ủng hộ.

Số **4** chỉ minh họa, không phải mức Kanban áp dụng cho mọi đội. Việc giới hạn WIP có thể làm **điểm nghẽn hiện ra** trước khi các chỉ số bắt đầu cải thiện.

### 9.4. Cách xử lý khi WIP đầy

~~~mermaid
flowchart TD
    A["Có người sẵn sàng làm việc"] --> B{"WIP vùng liên quan còn chỗ?"}
    B -- "Có" --> C["Kéo item ưu tiên theo chính sách"]
    B -- "Không" --> D["Xem item dở/blocked/đang chờ"]
    D --> E{"Có thể giúp hoàn tất an toàn?"}
    E -- "Có" --> F["Review, pair, test, gỡ blocker"]
    E -- "Chưa" --> G["Nêu trở ngại, cải tiến năng lực; xử lý ngoại lệ hợp lệ"]
    F --> H["Item đạt điều kiện Finished"]
    H --> C
    G --> B
~~~

Sơ đồ định hướng hành động, **không ép nhân viên làm ngoài năng lực hoặc bỏ quy trình an toàn** để “dọn bảng”.

### 9.5. Little's Law và các điều kiện áp dụng

Trong một hệ thống dòng công việc ổn định tương đối, nếu dùng cùng ranh giới và thoả các giả định áp dụng, **Little's Law** liên hệ WIP trung bình, tốc độ hoàn tất trung bình và thời gian trong hệ thống trung bình:

\[
\overline{\text{WIP}}\approx
\text{Throughput rate}\times\overline{\text{Cycle time}}.
\]

Nếu một luồng ổn định có trung bình **8 PBI đang dở** và hoàn tất trung bình **4 PBI/tuần**, cycle time trung bình có thể xấp xỉ:

\[
\overline{\text{Cycle time}}\approx\frac{8}{4}=2\text{ tuần}.
\]

Điều này **không** có nghĩa mọi PBI sẽ xong đúng hai tuần, hoặc cứ giảm một nửa WIP thì mọi PBI lập tức nhanh gấp đôi. Hệ thống cần thỏa điều kiện về ổn định, ranh giới tính, luồng vào/ra và cách đo. Đừng lấy một Sprint ngắn có incident để ngoại suy như định luật dự báo chắc chắn.

### 9.6. Chú ý cả item chưa Done

**Cycle time** thường đo những item đã Finished. Nếu có một item rất già bị chặn vẫn chưa Finished, nó chưa nằm trong tập cycle time của các item hoàn tất. Vì thế cần thêm:

- **Work item age:** tuổi của những item đã Started nhưng chưa Finished.
- **Blocked time:** thời gian chờ có điều kiện/nguồn được ghi rõ.
- **WIP:** số item đang dở theo trạng thái.
- **Throughput:** lượng hoàn tất trong khoảng đo.

Một nhóm có thể tạo nhiều item nhỏ Done và báo cycle time đẹp, trong khi bỏ quên một PBI quan trọng lâu ngày. Lean yêu cầu nhìn **toàn hệ thống**, không chọn mẫu chỉ gồm item đẹp.

## 10. Giảm batch size, handoff và chuyển ngữ cảnh

### 10.1. Batch lớn làm phản hồi đến muộn

Một nhóm gom tám PBI vào một nhánh, chờ tất cả backend xong rồi mới merge/frontend/test có thể gặp:

- Khó biết thay đổi nào phá hợp đồng.
- Review mất nhiều công vì PR lớn.
- Lỗi tích hợp chỉ xuất hiện sau nhiều tuần.
- Sửa một lỗi làm va chạm mã của những phần khác.
- Người dùng chỉ nhìn thấy giá trị khi toàn bộ batch qua hết quy trình.

Nếu chia thành các **lát cắt dọc nhỏ**, nhóm có thể tích hợp và kiểm chứng từng hành vi sớm hơn. Nhưng **nhỏ không có nghĩa bỏ một nửa yêu cầu an toàn**. Lát cắt người dùng được coi hoàn tất phải đáp ứng DoD và ràng buộc nghiệp vụ.

### 10.2. Ví dụ chia user story theo giá trị

Một epic quá lớn:

> “Xây hệ thống quản lý đăng ký, thanh toán, email, thống kê và lịch học hoàn chỉnh.”

Có thể xem các lát cắt:

| Lát cắt | Giá trị và rủi ro | Lưu ý chất lượng |
| --- | --- | --- |
| **Xem khóa còn chỗ** | Người học ra quyết định dựa trên thông tin. | Dữ liệu không gây hiểu nhầm; quyền công khai phù hợp. |
| **Đăng ký khóa miễn phí** | Người học có thể giữ chỗ hợp lệ. | Không vượt sức chứa, không trùng, phân quyền và transaction. |
| **Xác minh trạng thái sau timeout** | Người học không phải mở ticket chỉ để biết kết quả. | Không trả thành công giả hoặc lộ dữ liệu. |
| **Thông báo email khi được xác nhận** | Người học có thêm kênh thông tin. | Idempotent delivery, đúng địa chỉ/riêng tư và handling failures. |
| **Thanh toán khóa có phí** | Mở mô hình giá trị khác. | Rủi ro giao dịch và nghĩa vụ liên quan cần thiết kế riêng. |

Nếu **email xác nhận** là một nghĩa vụ bắt buộc của sản phẩm thật, không thể đơn giản tách nó ra để báo Increment đã Done. Phải làm rõ Product Goal, acceptance criteria, DoD và chính sách áp dụng.

### 10.3. Giảm handoff bằng cộng tác liên chức năng

Những thay đổi có thể thử:

- Product Owner, Developers và kiểm thử làm rõ ví dụ trước coding.
- API và UI thống nhất contract và dữ liệu lỗi sớm.
- Pairing/swarming với một PBI có rủi ro cao thay vì nhiều task rời.
- Một người thực hiện được nhiều bước trong phạm vi đủ năng lực, có review tương xứng.
- Đưa CI/contract/integration tests vào sớm, không “ném sang QA” ở cuối.
- Working agreement giải thích ai quyết và khi nào cần escalation.

Không loại bỏ **kiểm tra độc lập bắt buộc** chỉ để giảm số lần bàn giao. Với kiểm soát dữ liệu/bảo mật quan trọng, có thể cải thiện **đầu vào, công cụ, khả năng truy vết và lịch phản hồi**, không xóa trách nhiệm.

### 10.4. Giảm chuyển ngữ cảnh không phải cấm giúp người khác

**Chuyển ngữ cảnh** có thể tốn công khi một người phải giữ nhiều vấn đề phức tạp trong đầu. Nhưng phối hợp đúng lúc có thể **giảm tổng thời gian hoàn tất**. Khác biệt nằm ở:

- Chuyển không chủ đích giữa nhiều task đang dở vì hàng đợi (thường là tín hiệu Muri/Muda).
- Tập trung ngắn để **giúp hoàn tất một item đang bị chặn**, giúp toàn nhóm bớt WIP (có thể có ích).

Nhìn vào kết quả toàn luồng và mức tải bền vững, không mặc định mọi hình thức chuyển ngữ cảnh đều xấu.

## 11. Tạo chất lượng tại nguồn thay vì chuyển lỗi xuống cuối

### 11.1. Quality at the source

Trong Lean, một quan điểm quan trọng là **ngăn hoặc phát hiện sai lỗi ngay nơi chúng phát sinh**, thay vì cho lỗi đi qua hàng loạt bước rồi sửa khi đã đắt.

Trong phần mềm, ví dụ:

- Làm rõ ví dụ nghiệp vụ trước khi code.
- Viết test cho quy tắc không đăng ký trùng.
- Dùng type/validation và kiểm tra dữ liệu phù hợp.
- Chạy CI trên thay đổi nhỏ và sửa mainline đỏ sớm.
- Làm contract/integration tests trước khi phát hành.
- Quan sát tín hiệu production và lỗi dữ liệu theo quyền.

### 11.2. TDD, CI và refactoring làm ngắn vòng phản hồi

Trong XP, một số thực hành phù hợp Lean:

1. **TDD – Red:** viết test hành vi quan trọng rồi xác minh nó thất bại vì lý do mong đợi.
2. **Green:** triển khai thay đổi nhỏ để test đạt.
3. **Refactor:** cải thiện thiết kế mà test vẫn bảo vệ hành vi.
4. **Continuous Integration:** tích hợp thường xuyên, chạy kiểm chứng tự động để phát hiện xung đột sớm.
5. **Pairing/collective code ownership khi phù hợp:** giúp chia sẻ kiến thức, giảm thời gian chờ một chuyên gia.

Unit tests xanh không chứng minh toàn hệ thống đúng. Với đăng ký khóa, vẫn cần kiểm thử **database transaction, concurrency, idempotency, authn/authz và các tình huống thất bại của mạng** khi liên quan.

### 11.3. Gherkin minh họa kiểm chứng hành vi đăng ký

~~~gherkin
Feature: Đăng ký khóa miễn phí đáng tin cậy

  Scenario: Một học viên đăng ký khóa còn chỗ
    Given học viên A đã đăng nhập và đủ điều kiện
    And khóa X còn chỗ
    When A đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực của A
    And A nhận thông tin xác nhận từ trạng thái đã ghi thật

  Scenario: Gửi lại yêu cầu sau khi mất phản hồi
    Given yêu cầu đăng ký ban đầu của A đã commit thành công
    And phản hồi tới A bị gián đoạn
    When A gửi lại yêu cầu theo cơ chế hệ thống
    Then không tạo đăng ký hiệu lực trùng của A cho khóa X
    And A có thể xác minh trạng thái thật

  Scenario: Hai học viên cùng tranh chỗ cuối
    Given khóa X còn đúng một chỗ
    When hai học viên đủ điều kiện cùng đăng ký
    Then tối đa một đăng ký mới được xác nhận
    And số đăng ký hiệu lực không vượt sức chứa khóa X

  Scenario: Một học viên tra trạng thái của người khác
    Given học viên B không có quyền đọc đăng ký riêng của A
    When B yêu cầu trạng thái đăng ký của A
    Then hệ thống từ chối truy cập ở phía server
    And không tiết lộ dữ liệu riêng của A
~~~

Đây là **đặc tả hành vi minh họa**, không tự trở thành test có thể chạy. Developers cần hiện thực test với hệ thống, dữ liệu và môi trường phù hợp, giữ test bắt buộc trong Definition of Done.

### 11.4. Giảm defect không chỉ bằng tăng số test

Một nguyên nhân lỗi đăng ký trùng có thể do:

- Yêu cầu chưa nói rõ thao tác lặp.
- DB không có ràng buộc hợp lệ.
- Mã xử lý concurrency không có transaction an toàn.
- UI diễn giải timeout thành thất bại chắc chắn.
- Kiểm thử chỉ có happy path.

**Thêm hàng trăm unit test giống nhau** có thể không cải thiện rủi ro thực. Cần **xác định cơ chế sai**, chọn test/thiết kế phù hợp và xác minh trên bản tích hợp.

## 12. Lean không chỉ tối ưu delivery: tránh xây đúng cách một tính năng vô giá trị

### 12.1. Một luồng delivery hoàn hảo vẫn có thể làm sai sản phẩm

Giả sử nhóm giao một dashboard thống kê học viên chỉ trong ba ngày, không lỗi. Nhưng người quản trị không dùng dashboard vì họ cần cảnh báo khóa học sắp đầy. Nếu không hiểu nhu cầu, nhóm đã **tối ưu làm nhanh một output ít giá trị**.

Đây là **overproduction** ở góc nhìn sản phẩm, dù flow của delivery tốt.

### 12.2. Khám phá giá trị bằng phản hồi sớm

Một vòng có thể là:

~~~mermaid
flowchart LR
    A["Quan sát vấn đề người dùng"] --> B["Giả thuyết giá trị"]
    B --> C["Lát cắt / prototype / thí nghiệm an toàn"]
    C --> D["Đo hành vi và phản hồi"]
    D --> E{"Giả thuyết được ủng hộ?"}
    E -- "Một phần / chưa rõ" --> B
    E -- "Có" --> F["Mở rộng có kiểm soát"]
    F --> A
~~~

Ví dụ trước khi xây một màn hình đăng ký phức tạp, nhóm có thể:

- Quan sát người học thực sự gặp khó ở bước nào.
- Phỏng vấn không dẫn dắt và xem ticket support đã được bảo vệ dữ liệu.
- Thử prototype để hiểu thông báo sau timeout.
- Đưa một lát cắt đã kiểm chứng vào sử dụng trong phạm vi được phép.
- Theo dõi tỷ lệ tự hoàn tất, lỗi, số lần phải nhờ support và phản hồi định tính.

**Prototype không được phép thay bằng chứng hệ thống production an toàn**, đặc biệt với quyền, dữ liệu và thanh toán.

### 12.3. Product Goal và Cost of Delay

Một Product Backlog dài có thể có nhiều nhu cầu. Lean khuyến khích hỏi **giá trị và thời gian chờ**:

- Nếu việc sửa đăng ký trùng chậm thêm, thiệt hại/rủi ro là gì?
- Nếu dashboard chưa có người dùng chậm thêm hai tuần, tác động thực là gì?
- Nếu không làm CI reliability, chi phí làm lại và incident tiếp tục bao nhiêu?
- Có phụ thuộc nào cần chuẩn bị sớm để không chặn mục tiêu sau này?

**Cost of Delay** là một cách tư duy về hậu quả kinh tế của trì hoãn. Không cần giả vờ có số tiền chính xác khi dữ liệu chưa có. Có thể dùng mức ước lượng minh bạch, so sánh rủi ro và cập nhật khi học thêm.

### 12.4. Dùng thực hành thay vì biến Lean thành một framework đóng

Lean có thể dùng để **chọn vấn đề cần cải tiến**. Scrum, Kanban hoặc XP cung cấp một số thực hành cụ thể:

- Scrum: vòng kiểm tra–thích ứng và trách nhiệm tạo Increment.
- Kanban: nhìn WIP, flow, policies, giới hạn hàng đợi.
- XP: kỹ thuật giảm defect và phản hồi tích hợp.

Không cần “chuyển sang Lean” như đổi logo framework nếu nhóm có thể **áp dụng nguyên tắc Lean vào cách làm đang hiệu quả**.

## 13. Tình huống xuyên suốt: cải thiện dòng giá trị đăng ký khóa học

### 13.1. Bối cảnh: mỗi nhóm đều bận nhưng học viên chờ lâu

Một nhóm sản phẩm giáo dục quản lý hành trình học viên đăng ký khóa miễn phí. Sau một số đợt phát hành, họ ghi nhận:

- User stories mở nhiều hơn số đạt Done.
- API và UI thường ghép ở cuối Sprint.
- Nhiều PR chờ reviewer có quyền.
- Bộ kiểm thử tích hợp thường xuyên thiếu dữ liệu hợp lệ.
- Sau khi release, support nhận ticket “không biết đăng ký thành công chưa”.
- Product Owner khó biết **khi nào một hành vi thật sự sẵn sàng cho người dùng**.

Đây là **tình huống minh họa**, không phải dữ liệu thật của một tổ chức. Nhóm cần phân biệt triệu chứng đang quan sát và nguyên nhân chưa được kiểm chứng.

### 13.2. Bắt đầu từ kết quả người dùng

**Trạng thái mong muốn:**

> Học viên đủ điều kiện có thể tự đăng ký khóa miễn phí còn chỗ, nhận trạng thái chính xác trong điều kiện mạng thông thường, và tự xác minh kết quả khi phản hồi bị gián đoạn; không phát sinh đăng ký trùng, vượt sức chứa hoặc truy cập trái quyền.

Một số chỉ báo **outcome**:

- Tỷ lệ học viên hoàn tất tác vụ tự đăng ký theo định nghĩa.
- Số ticket hỏi trạng thái trên một mẫu người dùng có thao tác, cùng quy tắc đo.
- Sự cố sai dữ liệu/vượt chỗ hoặc truy cập trái quyền.
- Mức người học hiểu thông báo, qua quan sát hoặc phản hồi được phép.

Những chỉ báo này không đồng nghĩa flow metrics nội bộ. Nhóm cần **cả hai** để biết mình tạo giá trị sớm **và** đáng tin cậy.

### 13.3. Theo một PBI từ lúc được chọn tới lúc người dùng sử dụng

Một dòng giá trị có thể được mô tả:

~~~mermaid
flowchart LR
    A["PBI được chọn"] --> B["Refinement"]
    B --> C["Contract UI/API"]
    C --> D["Develop & CI"]
    D --> E["Review"]
    E --> F["Integrated verification"]
    F --> G["Release"]
    G --> H["Học viên sử dụng"]
    H --> I["Support / feedback"]
    F -. "Lỗi nghiệp vụ / API" .-> C
    H -. "Lỗi thực tế" .-> I
    I -. "Backlog / cải tiến" .-> B
~~~

Nhóm không chỉ ghi thời gian ở từng cột, mà còn theo:

| Phần luồng | Quan sát thực cần tìm | Câu hỏi Lean |
| --- | --- | --- |
| PBI được chọn → làm rõ | Thời gian chờ quyết định, số câu hỏi quay lại | Vì sao bắt đầu trước khi có ví dụ rõ? |
| Contract → code | Số vòng đổi schema, người chịu trách nhiệm | Có thể giảm bàn giao bằng ví dụ chung không? |
| Code → review | PR size, thời gian chờ reviewer, số lần trả lại | Reviewer là bottleneck hay PR quá lớn? |
| Review → test tích hợp | Sẵn môi trường, tỷ lệ flaky, thời điểm test thật lần đầu | Vì sao bằng chứng tích hợp đến muộn? |
| Done → release | Cửa sổ bắt buộc, việc bàn giao vận hành | Chờ này có thể giảm qua readiness sớm không? |
| Release → người dùng | Tỷ lệ hoàn tất, lỗi thực, ticket support | Có giao đúng thứ người dùng cần không? |

### 13.4. Phát hiện nguyên nhân phải có bằng chứng

Giả sử ban đầu nhóm cho rằng **“QA chậm”** vì thẻ ở Verify lâu. Khi quan sát thực:

- QA nhận một batch lớn vào cuối Sprint.
- Nhiều PBI chưa có test data phù hợp.
- API response chưa thống nhất khi hết chỗ.
- Các test điều kiện đồng thời chỉ được thiết kế sau khi triển khai.
- Chỉ một môi trường staging được nhiều nhóm chia sẻ.

Giả thuyết hợp lý hơn là **kích thước batch lớn, làm rõ muộn và hạ tầng test không sẵn** gây chờ và rework. Nhưng ngay cả giả thuyết ấy vẫn cần kiểm chứng bằng lịch sử hạng mục, CI và thử nghiệm.

### 13.5. Lãng phí liên quan các triệu chứng

| Triệu chứng | Dạng lãng phí có thể liên quan | Cơ chế cần kiểm tra |
| --- | --- | --- |
| UI và API hiểu khác nhau về lỗi hết chỗ | Defects, transportation, overprocessing | Contract/acceptance examples đến muộn. |
| Nhiều PBI dở và cuối Sprint mới test | Inventory, waiting, mura/muri | WIP cao, không có chính sách tập trung hoàn tất. |
| Mỗi người phải tự tìm dashboard/build | Motion | Tài liệu/observability phân tán, quyền truy cập thiếu rõ. |
| Mọi PR phải chờ một chuyên gia | Waiting, muri | Quyền review và khả năng dự phòng không phù hợp. |
| Người dùng hỏi support sau timeout | Defects/rework và có thể overprocessing | Trạng thái kết quả chưa rõ hoặc thiếu đường tra an toàn. |
| Tính năng bổ sung không có bằng chứng dùng | Overproduction | Product discovery chưa kiểm chứng giá trị. |

**Một triệu chứng có thể liên quan nhiều dạng waste.** Bảng chỉ giúp nêu câu hỏi, không thay việc phân tích nguyên nhân.

### 13.6. Chọn một thử nghiệm cải tiến nhỏ

Nhóm đặt giả thuyết:

> Nếu **làm rõ trạng thái đăng ký, retry và hết chỗ trước coding**, đồng thời viết contract/integration examples từ refinement, thời gian chờ và làm lại tại Verify sẽ giảm vì sai khác giữa các thành phần được phát hiện sớm; **DoD và kiểm thử quyền/dữ liệu không được hạ**.

Một thử nghiệm trên **hai PBI cùng loại**, nếu có đủ điều kiện:

1. PO, Developers, người kiểm thử và đầu mối API chọn ví dụ chấp nhận quan trọng.
2. Ghi contract cho success, already enrolled, no seats, unauthorized, timeout.
3. Viết contract tests và chuẩn bị test data/môi trường sớm.
4. Chia thay đổi thành PR nhỏ, tích hợp thường xuyên.
5. Theo dõi waiting time ở Verify và vòng rework vì lệch hợp đồng.
6. Xem security/concurrency tests và lỗi sau release như **guardrails**.

Không thay toàn bộ tổ chức hoặc dựng công cụ mới ngay để giải quyết giả thuyết này.

### 13.7. Bằng chứng giả định sau thử

| Dấu hiệu | Kỳ nền (giả định) | Kỳ thử (giả định) | Cách hiểu thận trọng |
| --- | ---: | ---: | --- |
| Số PBI tương tự đã Finished | 8 | 9 | Số lượng nhỏ, chưa thể suy năng suất toàn đội. |
| Thời gian chờ Verify trung vị | 3 ngày | 1,5 ngày | Có tín hiệu giảm hàng đợi; cần kiểm tra loại việc và môi trường. |
| Số vòng sửa contract đã ghi | 6 | 2 | Có thể contract-first hữu ích, nhưng còn yếu tố gây nhiễu. |
| Cycle time trung vị | 12 ngày | 9 ngày | Gợi ý kết quả toàn luồng cải thiện trong mẫu. |
| Lỗi dữ liệu nghiêm trọng quan sát | 0 | 0 | Không chứng minh không còn rủi ro với mẫu nhỏ. |

Đây là **dữ liệu tạo để học cách phân tích**. Cần hỏi có thay đổi công suất, lịch nghỉ, loại PBI, cách đếm, mức hỗ trợ của các nhóm hay không. Nếu chỉ hai PBI được áp dụng thực sự, không thể coi cả bảng kỳ thử là hiệu ứng riêng của hai PBI mà không phân loại; phải **giữ phạm vi quan sát và phạm vi thử nhất quán**.

### 13.8. Quyết định sau thử

Có thể:

- **Duy trì** làm rõ bằng ví dụ và contract tests nếu bằng chứng hữu ích, rủi ro chấp nhận và chi phí hợp lý.
- **Điều chỉnh** nếu mất quá nhiều thời gian họp hoặc cùng một vấn đề vẫn lặp lại.
- **Thử tiếp trên nhóm PBI khác** nếu còn bất định.
- **Hoàn tác một bước không hiệu quả** nếu nó chỉ tăng quá trình mà không giảm chờ hoặc sai lỗi.

Sau đó xem **điểm nghẽn mới**: nếu Verify nhanh hơn nhưng release vẫn chờ hai tuần vì môi trường, nhóm chuyển vòng cải tiến sang điều kiện release thay vì tiếp tục tối ưu một bước đã đủ tốt.

## 14. Tổ chức một buổi Value Stream Mapping có giá trị

### 14.1. Chọn đúng người và đúng phạm vi

Một buổi VSM có thể mời những người **thực sự nhìn thấy các phần của luồng**:

- Product Owner/người hiểu mục tiêu và phản hồi người dùng.
- Developers tham gia code, review, tích hợp.
- Kiểm thử hoặc người phụ trách chất lượng.
- Nền tảng/CI/vận hành nếu hàng đợi ở môi trường hoặc release.
- Support/đại diện người dùng nếu flow cần nhìn tới kết quả sau phát hành.
- Người có thẩm quyền về rủi ro/đối tác nếu một điều kiện quan trọng nằm ngoài nhóm.

Không cần mọi quản lý tham dự mọi buổi. **Thiếu người trực tiếp làm công việc** thường gây sai lệch lớn hơn thiếu một bảng biểu đẹp.

### 14.2. Quy trình workshop tham khảo

**Bước 1 — Chốt câu hỏi:** ví dụ “vì sao lát cắt đăng ký từ Started tới được sử dụng mất lâu?” Không bắt đầu bằng “chứng minh QA đang là bottleneck”.

**Bước 2 — Chọn item mẫu:** lấy hạng mục thực có đặc điểm tương tự, gồm cả item bị chặn hoặc làm lại, không chỉ những item đẹp.

**Bước 3 — Vẽ bước và mốc:** xác định đầu vào, đầu ra, chính sách chuyển, người quyết, nơi ghi dữ liệu.

**Bước 4 — Ghi hoạt động và chờ:** touch time, queue time, WIP, blocked, vòng rework; nêu phần chưa có dữ liệu.

**Bước 5 — Chỉ ra Muda/Mura/Muri:** phân loại như giả thuyết, hỏi nguồn gốc hệ thống và điều kiện bắt buộc.

**Bước 6 — Tìm một hướng cải tiến:** so mức tác động giá trị, chi phí/rủi ro và khả năng thử nhỏ.

**Bước 7 — Vẽ future state có điều kiện:** mô tả cách làm mới, nguyên tắc bảo vệ và tín hiệu sẽ thay đổi.

**Bước 8 — Chọn thử nghiệm và owner:** đặt baseline, giả thuyết, metric, guardrails, thời điểm xem lại.

**Bước 9 — Theo dõi bằng dữ liệu thật:** không kết thúc ở việc đã “tổ chức VSM”.

### 14.3. Một mẫu VSM có thể dùng ngay

~~~text
Value stream: [Tên hành trình giá trị]
Người nhận giá trị: [Ai?]
Kết quả mong muốn: [Hành vi/outcome]
Bắt đầu: [Mốc/điều kiện Started]
Kết thúc: [Mốc/điều kiện nhận giá trị]
Loại item: [PBI / defect / service request ...]
Khoảng quan sát: [Từ ... tới ...]
Nguồn dữ liệu: [Bảng/CI/log/phỏng vấn ...]

Bước | Bên chịu trách nhiệm | Active time | Waiting time
     | WIP | Điều kiện chuyển | Rework / blocker / ràng buộc
...

Tổng elapsed time: [...]
Tổng active time theo định nghĩa: [...]
Phần chờ / giới hạn đo: [...]
Những giả thuyết lãng phí chính: [...]
Những kiểm soát bắt buộc phải giữ: [...]
Các câu hỏi còn thiếu bằng chứng: [...]

Future state hypothesis: [...]
Experiment nhỏ: [...]
Metric chính: [...]
Guardrails: [...]
Owner: [...]
Ngày xem lại: [...]
Quyết định: Giữ / Chỉnh / Hoàn tác / Tiếp tục kiểm tra
~~~

### 14.4. Bốn lỗi thường gặp khi làm VSM

- **Dùng quy trình lý tưởng**, không theo hạng mục thật, bỏ qua hàng đợi ngầm.
- **Vẽ sơ đồ phòng ban**, không thể hiện luồng nhu cầu tới kết quả người dùng.
- **Không phân biệt thời gian làm/chờ và các mốc đo**, khiến số liệu không so được.
- **Không dẫn tới thử nghiệm**, chỉ dán ảnh bản đồ lên tài liệu rồi để đó.

Một VSM đơn giản nhưng cập nhật từ công việc thực thường hữu ích hơn sơ đồ phức tạp không có owner hoặc dữ liệu.

## 15. Chọn đối sách Lean: loại bỏ, giảm, đơn giản hóa hay tự động hóa?

### 15.1. Đừng tự động hóa một bước không cần tồn tại

Thứ tự câu hỏi có ích:

1. **Có cần bước này không?** Nếu không tạo giá trị, không bảo vệ rủi ro và không bắt buộc, thử loại bỏ.
2. **Có thể giảm yêu cầu/batch size không?** Nếu cần, giữ mức tối thiểu đủ kiểm chứng.
3. **Có thể làm sớm và tự phục vụ không?** Đưa feedback về gần điểm tạo công việc.
4. **Có thể tự động hóa an toàn không?** Chỉ khi quy tắc đủ rõ và có kiểm chứng.
5. **Có thể giảm việc quay lại không?** Thiết kế test/hợp đồng làm rõ trước.
6. **Có thể thay ranh giới sở hữu/kiến trúc không?** Khi phụ thuộc lặp lại và đủ bằng chứng.

Ví dụ, tự động gửi ba email nhắc một bước phê duyệt trùng lặp có thể **tăng output thông báo** nhưng không rút ngắn luồng. Hãy hỏi trước liệu bước phê duyệt đó **có phải điều kiện cần hoặc có thể thay bằng kiểm soát tự động hợp lệ** không.

### 15.2. Ma trận đối sách theo dạng waste

| Dấu hiệu | Nguyên nhân cần xác minh | Thử nghiệm ưu tiên |
| --- | --- | --- |
| PR chờ review lâu | Reviewer duy nhất, PR lớn, tiêu chí mơ hồ. | Reviewer dự phòng đủ quyền; chia PR hẹp và rõ rủi ro. |
| Integration lỗi cuối Sprint | Ghép muộn, contract thiếu test, test data yếu. | Contract-first, CI liên tục, test từ refinement. |
| WIP tăng, throughput không tăng | Mở nhiều item khi bước Verify đã nghẽn. | Giới hạn WIP, swarming hoàn tất, xem blocker. |
| Support hỏi cùng câu sau timeout | Thông báo UI mơ hồ hoặc thiếu tra trạng thái. | Quan sát người dùng, cải thiện trạng thái và test retry an toàn. |
| Dashboard ít ai dùng | Không kiểm chứng nhu cầu thực. | Phỏng vấn tác vụ, prototype, thử outcome nhỏ. |
| Lặp ghi dữ liệu giữa công cụ | Nhiều bản sao thủ công và quy trình bàn giao. | Một nguồn sự thật, tự động hóa truyền dữ liệu hợp lệ. |
| Một môi trường test bị tranh chấp | Công suất, quyền hoặc cách cấp môi trường. | Self-service có guardrails, cách ly và lịch phù hợp. |
| Một chuyên gia liên tục quá tải | Kiến thức và quyền tập trung. | Pairing, documentation theo việc, người dự phòng có thẩm quyền. |

Một đối sách phải có **cơ chế tác động**. Không nên mua công cụ chỉ vì “có vẻ Lean”.

### 15.3. Chọn thử nghiệm bằng giá trị, rủi ro và khả năng học

Giả sử nhóm có ba ý tưởng:

| Ý tưởng | Giá trị nếu đúng | Rủi ro/chi phí | Khả năng thử nhỏ |
| --- | --- | --- | --- |
| Chốt contract API bằng ví dụ sớm | Có thể giảm rework và waiting | Thấp–vừa, cần đúng người | Cao |
| Mua nền tảng quản lý công việc mới toàn công ty | Chưa rõ có xử lý bottleneck | Chi phí và gián đoạn lớn | Thấp |
| Bỏ hết integration tests để giảm CI time | Tăng tốc báo cáo nhưng có nguy cơ lỗi | Rủi ro chất lượng cao, có thể không hợp lệ | **Không chấp nhận** |

Thường nên thử thay đổi nhỏ có **lý do rõ, bằng chứng quan sát được và guardrails**, thay vì cố thực hiện một chương trình tái cấu trúc lớn khi chưa có giả thuyết tốt.

### 15.4. Theory of Constraints hỗ trợ nhìn nút thắt

**Theory of Constraints (TOC)** là một cách nhìn liên quan nhưng **không đồng nhất Lean**: hệ thống có ràng buộc chi phối khả năng tạo ra thông lượng. Có thể dùng tư duy này để:

1. Nhận diện **ràng buộc hiện tại** dựa trên quan sát.
2. Tận dụng nó hợp lý, tránh lãng phí năng lực khan hiếm.
3. Điều chỉnh các bước khác theo khả năng hệ thống, không đẩy hàng đợi vô hạn vào ràng buộc.
4. Cân nhắc nâng năng lực ràng buộc khi có đủ bằng chứng.
5. Quan sát ràng buộc mới khi hệ thống thay đổi.

Ví dụ nếu một môi trường integration là bottleneck, **tăng gấp đôi số PR mới** không làm môi trường test xử lý nhanh hơn. Cần giảm hàng đợi, ưu tiên test theo rủi ro hoặc cải thiện khả năng cấp môi trường an toàn.

### 15.5. Không nên tối ưu từng bước một cách mù quáng

Khi review nhanh gấp đôi nhưng bộ kiểm thử tích hợp chậm thêm, **cycle time toàn luồng** có thể không cải thiện. Hãy kiểm tra:

- VSM từ đầu tới cuối.
- WIP và tuổi ở các bước liền kề.
- Lỗi, rework và thời gian phục hồi.
- Tải của các nhóm cung cấp.
- Outcome người dùng sau khi phát hành.

Lean cần **tối ưu hệ thống**, không chỉ làm đẹp một cột hoặc một nhóm.

## 16. PDCA/Kaizen: biến quan sát lãng phí thành thử nghiệm có kiểm chứng

### 16.1. Chu trình PDCA

| Bước | Câu hỏi | Đầu ra |
| --- | --- | --- |
| **Plan** | Vấn đề nào? Baseline nào? Cơ chế giả thuyết? Cách thử và rủi ro? | Bản ghi thử nghiệm, metric và guardrails. |
| **Do** | Thực hiện thay đổi nhỏ ở đâu, ai làm và điều gì xảy ra? | Bằng chứng thực thi, sai lệch kế hoạch. |
| **Check** | Kết quả có khớp dự đoán? Tác động phụ? Giới hạn dữ liệu? | So sánh quan sát với giả thuyết, bất định. |
| **Act** | Giữ, điều chỉnh, hoàn tác hay thử giả thuyết khác? | Quyết định và bước học kế tiếp. |

Biến thể **PDSA (Plan–Do–Study–Act)** nhấn mạnh việc **nghiên cứu điều quan sát được** thay vì chỉ tích dấu thành công/thất bại. Một vòng cải tiến có thể dùng tên PDCA hay PDSA miễn là kiểm chứng giả thuyết thực sự.

### 16.2. Mẫu giả thuyết

~~~text
Chúng tôi quan sát: [sự kiện, phạm vi, thời gian, nguồn]
Khoảng cách cần cải thiện: [trạng thái hiện tại -> trạng thái mục tiêu]
Chúng tôi giả định: [cơ chế có thể sai]

Nếu thử [thay đổi nhỏ, có quyền, phạm vi rõ],
thì [metric chính] sẽ thay đổi theo [dự đoán],
vì [cơ chế kỳ vọng].

Baseline: [...]
Metric chính: [...]
Guardrails: [DoD, lỗi, bảo mật, riêng tư, workload...]
Yếu tố có thể gây nhiễu: [...]
Người thực hiện / người quyết: [...]
Thời điểm xem: [...]
Điều kiện dừng / hoàn tác: [...]

Kết quả: [...]
Điều còn chưa chắc: [...]
Quyết định và việc tiếp: [...]
~~~

### 16.3. Ví dụ: giảm review waiting time

**Quan sát giả định:** Trong hai tuần, 7/12 PR đủ điều kiện review chờ hơn một ngày làm việc.

**Giả thuyết:** Nếu có người review dự phòng đủ chuyên môn và PR được mở nhỏ sớm, thời gian chờ tới review có ích sẽ giảm vì bớt phụ thuộc một người và giảm chi phí nhận ngữ cảnh.

**Thử:** áp dụng trên một loại PR có rủi ro vừa trong hai tuần; giữ quy tắc review bắt buộc.

**Metric:** thời gian Ready for Review → review có ích.

**Guardrails:** lỗi sau merge, mức độ review, tải reviewer và giờ làm thêm.

**Cách học:** Nếu thời gian chờ không giảm nhưng log cho thấy phần lớn thời gian là **chờ CI**, đổi giả thuyết sang CI capacity thay vì ép reviewer trả lời nhanh hơn.

### 16.4. Giả thuyết có thể thất bại vẫn hữu ích

Một nhóm thử thêm buổi họp để “giảm lệch thông tin” nhưng:

- Thời gian chờ vẫn như cũ.
- Người tham gia mất thời gian tập trung.
- Contract mismatch chỉ giảm khi nhóm bắt đầu có test.

Đó là một **bài học có giá trị**: buổi họp không phải cơ chế chính. Nhóm có thể ngừng họp thử và tập trung vào hợp đồng/tích hợp. Cần phân biệt **thử nghiệm được kiểm soát, có học hỏi** với thay đổi bất cẩn gây hại cho người dùng.

### 16.5. Kaizen và tôn trọng người làm

**Kaizen** nhấn mạnh cải tiến thường xuyên từ hiểu biết của người trực tiếp làm việc. Nhân viên support, QA, Developers, Product Owner và vận hành đều có thể nhìn thấy những lãng phí mà dashboard chưa thể hiện.

Cải tiến tốt không nên:

- Yêu cầu người báo lỗi phải tự gánh toàn bộ việc sửa.
- Biến chỉ số lãng phí thành danh sách người “kém năng suất”.
- Giữ một quy trình chỉ vì cấp trên từng chọn nó.
- Buộc mọi cải tiến nhỏ xin thêm một tầng phê duyệt không cần thiết.

Cần có **quyền nêu vấn đề, sự minh bạch, trách nhiệm và điều kiện thử nghiệm an toàn**. Tôn trọng con người không loại bỏ trách nhiệm chuyên môn hay nghĩa vụ giải quyết lỗi.

## 17. Đo lường Lean: tránh tối ưu chỉ số thay vì giá trị

### 17.1. Ba lớp chỉ số

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Activity/output** | Chúng ta đã làm gì? | Viết contract tests, giảm số cuộc họp, tạo automation. |
| **Flow/process** | Giá trị đi qua hệ thống có tốt hơn không? | Cycle time, blocked time, WIP, work item age. |
| **Outcome/quality** | Người dùng có được lợi và hệ thống có đáng tin cậy hơn không? | Hoàn tất tự đăng ký, ít lỗi dữ liệu, ít phải nhờ support. |

Một thử nghiệm có thể tăng số integration tests (**output**) nhưng không cải thiện chất lượng vì test trùng hoặc flaky. Một thay đổi có thể giảm cycle time (**flow**) bằng cách bỏ test, nhưng làm outcome/quality xấu đi. Cần đo các lớp **đúng với giả thuyết** và có guardrails.

### 17.2. Định nghĩa metrics nhất quán

~~~text
Value stream: Đăng ký khóa miễn phí
Loại item: PBI lát cắt dọc đã chọn
Started: Khi Developers bắt đầu xử lý item
Finished: Khi item đạt chính sách Done đã công bố
Lead time người dùng: Từ một mốc nhu cầu xác định tới khả năng sử dụng
Cycle time: Started tới Finished theo Definition of Workflow
Work item age: Started tới hiện tại cho item chưa Finished
Throughput: Số item Finished trong một khoảng đo
Blocked time: Các khoảng không thể tiến triển do blocker đã ghi
Flow efficiency: Active time / elapsed time theo cách đếm thống nhất
Quality guardrails: DoD, lỗi hậu phát hành, dữ liệu, phân quyền
User outcome: Học viên tự hoàn tất/tra trạng thái theo định nghĩa
~~~

**Mốc Started/Finished không nên thay trong quá trình đo chỉ để số tốt hơn**. Nếu chính sách Done đổi (ví dụ từ “code merge” thành “đạt test tích hợp”), phải ghi đây là **đứt gãy định nghĩa**; dữ liệu hai kỳ không so trực tiếp.

### 17.3. Ví dụ dashboard đủ gọn để quyết định

| Metric | Mục đích | Cách dùng hợp lý |
| --- | --- | --- |
| Work item age lớn nhất | Phát hiện item mắc kẹt lâu | Hỏi vì sao, giúp gỡ blocker, không phạt người sở hữu. |
| WIP theo bước | Thấy hàng đợi và quá tải | Thử pull policies hoặc tăng năng lực ở bottleneck. |
| Cycle time phân bố | Thấy thời gian hoàn tất và biến động | Phân loại loại việc, tránh chỉ nhìn trung bình. |
| Throughput theo thời gian | Thấy nhịp hoàn tất | Xem cùng WIP, tuổi item, giá trị và chất lượng. |
| Blocked time theo nguyên nhân | Chọn lãng phí ưu tiên | Xác minh điểm nghẽn thay vì quy lỗi cá nhân. |
| Rework/escaped defects | Bảo vệ chất lượng | Kiểm tra liệu cải tiến tốc độ có tạo lỗi mới. |
| Tỷ lệ học viên tự hoàn tất | Đo giá trị sản phẩm | Kết hợp với hiểu hành vi, hỗ trợ và quyền riêng tư. |
| Tải công việc và hỗ trợ | Bảo vệ tính bền vững | Tránh đẩy work sang QA/on-call hoặc giờ làm thêm. |

Không cần dựng tất cả dashboard cùng lúc. Chọn **chỉ số chính, một vài chỉ báo nguyên nhân và guardrails**, rồi cập nhật khi học thêm.

### 17.4. Các kiểu lệch metric

- **Velocity thành quota:** nhóm tăng story points bằng đổi cách ước lượng, không tăng giá trị.
- **Số ticket Done thành năng suất:** tách task giả nhỏ, bỏ item khó.
- **CI speed thành mục tiêu đơn:** tắt test chậm nhưng quan trọng.
- **Flow efficiency tăng bằng cách bỏ active time cần thiết:** bỏ security review rồi báo “ít process hơn”.
- **Không đếm item dở:** cycle time của item Done đẹp nhưng các item chờ vendor già đi.
- **So nhóm khác nhau như một bảng xếp hạng:** bỏ qua loại việc, quy tắc Done, rủi ro và bối cảnh.

Metrics dùng để **hỏi và học**, không thay đánh giá chuyên môn hoặc dùng như thước đo phẩm chất con người.

### 17.5. Yếu tố gây nhiễu và dữ liệu nhỏ

Nếu cycle time giảm từ 12 ngày xuống 8 ngày sau thử WIP limit, có thể:

- WIP limit góp phần giảm chờ.
- PBI ở kỳ sau nhỏ hơn.
- Một reviewer vừa trở lại sau nghỉ.
- Môi trường kiểm thử đã được sửa cùng lúc.
- DoD hoặc quy tắc ghi thời gian đã đổi.

Kết luận trung thực:

> “Cycle time quan sát giảm trong mẫu theo cách đo đã công bố. Biện pháp WIP limit có thể góp phần, nhưng cần xem loại việc, thay đổi môi trường và chất lượng trước khi khẳng định tác dụng ổn định.”

Một mẫu nhỏ **có thể đủ để nhận thấy tín hiệu và chọn thử nghiệm kế tiếp**, nhưng không chứng minh quan hệ nhân quả tuyệt đối. Nếu quyết định có hậu quả lớn, cần bằng chứng và đánh giá tương xứng.

## 18. Áp dụng Lean trong Scrum mà không làm sai Scrum

### 18.1. Scrum và Lean có thể bổ sung nhau

**Scrum** là framework nhẹ nhằm giúp con người/nhóm/tổ chức tạo giá trị qua giải pháp thích ứng cho vấn đề phức tạp. **Lean** hỗ trợ nhìn giá trị và lãng phí trong toàn hệ thống. Scrum dựa trên thực nghiệm và tư duy Lean; hai cách nhìn không cạnh tranh trong mọi bối cảnh.

| Thành phần Scrum | Cơ hội dùng tư duy Lean | Cạm bẫy cần tránh |
| --- | --- | --- |
| **Product Goal** | Đảm bảo nhóm không tối ưu tốc độ xây thứ ít giá trị. | Thay goal bằng KPI số task hoặc story points. |
| **Product Backlog** | Sắp thứ tự theo giá trị, rủi ro, thời gian chờ và chi phí trì hoãn. | Làm tất cả item chỉ vì đã được yêu cầu từ lâu. |
| **Sprint Planning** | Chọn mục tiêu có thể tạo Increment, xem WIP/phụ thuộc, chia lát cắt. | Đổ đầy “công suất” bằng task bất chấp khả năng Done. |
| **Sprint Backlog** | Minh bạch kế hoạch và điều chỉnh cách đạt Sprint Goal khi học thêm. | Dùng backlog như danh sách nhiệm vụ cố định do quản lý áp. |
| **Daily Scrum** | Nhìn blocker, phối hợp hoàn tất, giảm hàng đợi. | Biến thành cuộc họp báo cáo trạng thái cho cấp trên. |
| **Sprint Review** | Kiểm tra Increment và phản hồi thực tế về giá trị. | Chỉ trình diễn slide về số việc đã làm. |
| **Sprint Retrospective** | Chọn một thử nghiệm loại lãng phí có thể đo. | Ghi danh sách ý tưởng nhưng không theo dõi kết quả. |
| **Definition of Done** | Giữ chất lượng tại nguồn và tránh đẩy lỗi về sau. | Hạ DoD để “giảm bước thừa” và tăng velocity. |

### 18.2. Ví dụ Retrospective theo PDCA

**Quan sát:** cuối ba Sprint liên tiếp, nhiều PBI ở Verify chưa đạt DoD.

**Giả thuyết:** những PBI này được chia theo backend–frontend–QA và tích hợp muộn.

**Thử nghiệm Sprint kế:** chọn hai PBI có thể chia lát cắt dọc; người hiểu API và test làm rõ ví dụ trước khi bắt đầu; chạy smoke integration test từ sớm.

**Đo:** thời điểm test đầu tiên chạy trên bản tích hợp, blocked time, work item age, số lần rework.

**Guardrails:** không bỏ test quyền/nhất quán dữ liệu, không tăng lỗi sau release hoặc tải QA.

**Kiểm tra ở Retro sau:** xem giả thuyết có được ủng hộ không; nếu bottleneck thực là staging hỏng, thử cải tiến môi trường thay vì mở thêm cuộc họp.

Một thử nghiệm có giá trị **không cần phải chờ một Sprint mới để xử lý blocker nghiêm trọng**. Developers có thể điều chỉnh kế hoạch trong Sprint và xử lý sự cố theo rủi ro ngay khi cần.

### 18.3. Sprint Goal khác mục tiêu làm đầy lịch

Một Sprint Goal hữu ích:

> “Học viên có thể tự đăng ký khóa miễn phí còn chỗ trên Increment đã tích hợp, không ghi trùng hoặc vượt sức chứa.”

Một “mục tiêu” dễ làm sai:

> “Mỗi Developer hoàn tất tối thiểu tám task và sử dụng đủ 100% thời gian.”

Câu thứ hai khuyến khích tối ưu **mức độ bận và số đầu ra cục bộ**, không định nghĩa giá trị. Nhóm có thể tạo nhiều task Done trong khi không có Increment dùng được.

### 18.4. DoD là tiêu chuẩn chất lượng, không phải một hàng đợi nên xóa

Nếu một PBI chờ kiểm thử tính nhất quán dữ liệu, Lean yêu cầu xem **vì sao kiểm thử bị chờ** và cách làm sớm hơn, chứ không nói “để cải thiện flow efficiency, bỏ test concurrency”.

Khi nhiều Scrum Team cùng làm một sản phẩm, họ phải chia sẻ **một Product Goal, một Product Backlog, một Product Owner và một Definition of Done**. Việc nhiều nhóm đóng task riêng **không tự cộng thành Increment Done** nếu chưa tích hợp đáp ứng tiêu chuẩn chung.

## 19. Áp dụng Lean trong Kanban: từ trực quan hóa tới dòng công việc ổn định

### 19.1. Kanban là công cụ nhìn thấy flow, không chỉ bảng cột

Một Definition of Workflow (DoW) có thể xác định:

- **Work item type:** PBI, defect, incident, service request.
- **Started và Finished:** ranh giới để tính cycle time/WIP.
- **Trạng thái:** bước nào đang thực hiện, bước nào đang chờ.
- **Explicit policies:** điều kiện kéo việc, chuyển trạng thái, xử lý blocked.
- **WIP control:** giới hạn/điều chỉnh lượng việc dở.
- **Service Level Expectation (SLE):** kỳ vọng thời gian hoàn tất theo dữ liệu phù hợp.

Một bảng có nhiều cột chưa chắc cho biết flow nếu item liên tục bị kéo sang bảng khác hoặc cột Done chỉ nghĩa là “code merge”.

### 19.2. Vẽ workflow có điểm chờ và rework

~~~mermaid
flowchart LR
    A["Ready"] --> B["Developing"]
    B --> C["Review / CI"]
    C --> D["Integrated Verify"]
    D --> E["Done"]
    C -. "Rework" .-> B
    D -. "Defect / contract mismatch" .-> B
    D -. "Blocked environment" .-> D
~~~

Vòng rework và trạng thái blocked cần được **ghi rõ nguyên nhân**, không chỉ chuyển thẻ qua lại khiến dữ liệu lịch sử khó phân tích.

### 19.3. Work item age dùng để hành động sớm

Giả sử một PBI đã dở 11 ngày, trong khi nhiều item cùng loại thường hoàn tất sớm hơn theo lịch sử. Thay vì chỉ hỏi “bao giờ xong?”:

1. Item đang ở bước nào và có blocked thật không?
2. Phụ thuộc nào chưa đáp ứng, ai có quyền quyết định?
3. Có thể giúp hoàn tất mà không mở thêm WIP không?
4. Test/DoD nào đang chờ, có thể chuẩn bị môi trường ngay?
5. Có cần chia scope hợp lệ hoặc xem rủi ro Product Goal không?

**SLE** là kỳ vọng có tính xác suất từ dữ liệu, không tự là **SLA hợp đồng** hay thời hạn cứng để bỏ kiểm thử. Cần tránh dùng SLE như một cây gậy trừng phạt thành viên.

### 19.4. Cumulative Flow Diagram giúp nhìn tích lũy

Một **Cumulative Flow Diagram (CFD)** thể hiện lượng item ở các trạng thái theo thời gian. Nếu dải của bước Verify nở rộng, đó có thể là tín hiệu hàng đợi/tích lũy. Nhưng cần xem:

- Quy tắc chuyển trạng thái có thay đổi không?
- Có item khẩn chen vào?
- Có tắc nghẽn thật hay chỉ nhiều item được ghi lại rõ hơn?
- Có batch từ bước trước đổ dồn xuống không?

CFD là **bằng chứng trực quan cần diễn giải**, không tự xác định nguyên nhân.

### 19.5. Kanban phù hợp khi công việc đến không đều

Một đội xử lý lỗi vận hành, yêu cầu tích hợp API hoặc support có thể nhận công việc không theo nhịp Sprint rõ. **Kanban với pull, policies, WIP và flow metrics** giúp quản lý hàng đợi. Đội vẫn có thể dùng PDCA/Kaizen và các kỹ thuật XP.

Không nhất thiết bỏ Scrum nếu tổ chức đang có Sprint Goal/feedback loop phù hợp. Có thể áp dụng **Kanban practices trong một Scrum Team** để cải thiện flow. Chọn cách làm dựa trên loại giá trị và nhu cầu phối hợp, không dựa vào tên framework.

## 20. Lean kết hợp XP: tối ưu tốc độ học hỏi kỹ thuật

### 20.1. Phản hồi kỹ thuật ngắn làm giảm chi phí sai lỗi

**XP (Extreme Programming)** có các thực hành phù hợp với dòng giá trị:

| Thực hành | Lãng phí có thể giảm | Điều cần giữ |
| --- | --- | --- |
| **TDD** | Phát hiện lỗi muộn, rework. | Test đúng hành vi, không chỉ làm xanh unit tests giả. |
| **Continuous Integration** | Tích hợp dồn cục, xung đột nhánh, waiting. | Check bắt buộc có ý nghĩa, pipeline tin cậy. |
| **Refactoring** | Thiết kế gây sửa nhiều nơi, overprocessing dài hạn. | Test hồi quy và kiểm soát rủi ro thay đổi. |
| **Pair programming** | Hàng đợi review, hiểu sai kiến trúc, phụ thuộc một người. | Năng lực, sự đồng thuận và chi phí phù hợp. |
| **Small releases** | Batch lớn, chậm feedback người dùng. | DoD, rollout và khả năng khôi phục. |
| **Collective code ownership khi phù hợp** | Phụ thuộc chuyên gia duy nhất. | Trách nhiệm chất lượng và quyền/kiểm soát hợp lệ. |
| **Simple design** | Xây quá nhiều khả năng chưa cần. | Không hy sinh yêu cầu phi chức năng quan trọng. |

### 20.2. Ví dụ: tối ưu CI 35 phút nhưng vẫn giữ chất lượng

Một nhóm thấy pipeline bắt buộc mất **35 phút** từ push tới kết quả; Developers phải chờ hoặc chuyển ngữ cảnh. Họ cân nhắc bỏ integration tests. Đây là **cách giảm thời gian báo cáo nhưng tăng rủi ro**.

Thử nghiệm hợp lý hơn:

1. Tách **queue time chờ runner**, setup time và test execution time.
2. Chạy unit/static checks nhanh sớm.
3. Chạy song song những integration tests thực sự độc lập với dữ liệu test cách ly.
4. Cache những thành phần cho phép cache mà không làm sai tính tái lập.
5. Sửa flaky tests dựa trên nguyên nhân thay vì rerun tới khi xanh.
6. Giữ mọi test bắt buộc trước merge/release theo chính sách.

Metric chính: thời gian từ push tới kết quả kiểm chứng cần thiết.

Guardrails: test bắt buộc vẫn chạy; tỷ lệ lỗi sau merge, mainline đỏ, flaky rate và chi phí runner không vượt mức chấp nhận.

Nếu kết quả giả định giảm từ **35 xuống 19 phút**, đó là **tín hiệu feedback time cải thiện**, chưa tự là bằng chứng sản phẩm có ít lỗi hơn. Cần xem chất lượng dài hạn.

### 20.3. Lean và kỹ thuật phải song hành

Giới hạn WIP mà không có test tích hợp đáng tin cậy có thể làm ít task đang dở hơn nhưng các PBI vẫn mắc kẹt trước Done. Ngược lại, CI rất nhanh mà Product Owner liên tục chọn tính năng không có giá trị có thể tạo **overproduction nhanh hơn**.

Lean giúp chọn **đúng điểm nghẽn và giá trị**, XP giúp cải tiến **độ tin cậy của vòng phản hồi kỹ thuật**, Kanban giúp thấy luồng và Scrum giúp tổ chức vòng kiểm tra–thích ứng quanh giá trị.

## 21. Khi nào nên chọn Lean làm cách tiếp cận cải tiến?

### 21.1. Nhận diện hoàn cảnh phù hợp

Lean đặc biệt hữu ích như **lăng kính cải tiến hệ thống** khi:

- Một nhu cầu phải đi qua **nhiều bước và nhiều nhóm**.
- Hầu hết thời gian là **waiting/handoff/rework**, không phải làm trực tiếp.
- Có WIP cao, nhiều việc chưa Done hoặc nhiều điểm nghẽn lặp.
- Thành viên liên tục bận nhưng người dùng không nhận kết quả sớm.
- Defects sau release tạo nhiều vòng hỗ trợ/sửa lại.
- Có công suất không đều, batch lớn và quá tải.
- Tổ chức cần chọn cải tiến **có bằng chứng** thay vì áp thêm quy trình.

Lean cũng có ích trong **Product Discovery** để tránh xây những khả năng không có nhu cầu, nhưng cần kết hợp với hiểu người dùng, đánh giá giá trị và thực nghiệm sản phẩm.

### 21.2. Lean không thay thế những năng lực gì?

| Nhu cầu | Lean đóng góp gì? | Cần bổ sung gì? |
| --- | --- | --- |
| Điều phối một Scrum Team | Nhận diện waste và cải thiện flow/quality. | Scrum accountabilities, events, artifacts/commitments nếu dùng Scrum. |
| Quản lý yêu cầu đến liên tục | Nhìn hàng đợi và giả thuyết cải tiến. | Kanban DoW, policies, WIP và flow metrics. |
| Giảm lỗi code/tích hợp | Xác định chi phí rework và chậm feedback. | TDD, CI, review, contract/integration/security tests. |
| Quyết định feature có giá trị không | Tránh overproduction, xem outcome. | Product discovery, nghiên cứu người dùng, quyết định Product Goal/backlog. |
| Hệ thống cần kiểm soát an toàn/pháp lý | Tìm cách giảm chờ không cần thiết trong kiểm chứng. | Chuyên môn, nghĩa vụ và thẩm quyền bảo mật/pháp lý. |
| Nhiều vendor có nhịp khác nhau | Nhìn dependency/queue end-to-end. | Hợp đồng, versioning, vận hành, escalation và chiến lược tích hợp. |
| Tổ chức thiếu niềm tin/tự chủ | Khuyến khích gemba và tôn trọng con người. | Lãnh đạo, thay đổi hành vi, xây năng lực và quyền phù hợp. |

Lean **không phải một bộ vai trò, sự kiện hoặc tool duy nhất bắt buộc**. Có thể vận dụng tốt với Scrum, Kanban, XP hoặc một cách phối hợp khác khi dựa trên bối cảnh thực.

### 21.3. Bảng chọn hướng xử lý dựa trên triệu chứng

| Triệu chứng chính | Góc nhìn ưu tiên | Thực hành có thể thử |
| --- | --- | --- |
| Không rõ người dùng cần gì | **Giá trị/outcome** | Phỏng vấn, prototype, user story mapping, kiểm chứng giả thuyết. |
| Nhiều hạng mục bị chặn và già | **Dòng công việc** | Kanban visualization, WIP limits, work item age, blocker policy. |
| Sai lỗi chỉ xuất hiện khi ghép cuối | **Chất lượng tại nguồn** | XP/TDD, CI, contract/integration tests, vertical slices. |
| Cuộc họp Retro không dẫn tới cải thiện | **Vòng học hỏi** | PDCA/PDSA, thử nghiệm nhỏ có owner và guardrails. |
| Nhiều nhóm bàn giao qua lại | **Cấu trúc value stream** | VSM, đội liên chức năng, hợp đồng rõ, giảm coupling. |
| Người thực hiện quá tải liên tục | **Muri/Mura/công suất** | Giới hạn WIP, chia sẻ kỹ năng, dự phòng năng lực và ưu tiên. |
| Nhiều đợt phê duyệt gây chờ | **Kiểm soát và overprocessing** | Phân biệt bắt buộc với thừa, làm rõ quyền, tự động hóa an toàn. |
| Feature được giao nhanh nhưng không ai dùng | **Overproduction** | Đo usage/outcome, dừng hoặc điều chỉnh Product Backlog. |

Đây là **gợi ý để bắt đầu điều tra**, không phải kết luận nguyên nhân từ một biểu hiện. Ví dụ cycle time dài chưa đủ để khẳng định WIP cao là nguyên nhân duy nhất.

### 21.4. Chọn theo đặc điểm hệ thống, không theo phong trào

Một đội tạo sản phẩm mới với nhiều bất định cần học về **giá trị người dùng**; một đội bảo trì dịch vụ quan trọng cần ưu tiên **flow, reliability, incident response**; một đội nhiều vấn đề kỹ thuật cần **chất lượng tại nguồn**. Cả ba đều có thể dùng Lean nhưng chọn thử nghiệm khác nhau.

**Đừng áp WIP limit cực thấp hoặc xóa mọi tài liệu** cho một hệ thống cần kiểm chứng nghiêm ngặt chỉ vì muốn mô phỏng một công ty nổi tiếng.

## 22. Những ràng buộc cần bảo vệ khi loại lãng phí

### 22.1. Phân biệt công việc bắt buộc với quy trình được thêm do thói quen

Trong môi trường có bảo mật, dữ liệu học viên, giao dịch hoặc đối tác:

| Câu hỏi | Ví dụ |
| --- | --- |
| Bước nào bảo vệ người dùng hoặc là nghĩa vụ? | Kiểm tra phân quyền trước khi mở API tra đăng ký. |
| Bước nào được tạo để thực hiện nghĩa vụ ấy? | Review thay đổi đặc biệt bởi người có thẩm quyền. |
| Bước nào có thể đơn giản hóa mà vẫn giữ mục tiêu? | Chuẩn hóa đầu vào review, test tự động và người dự phòng hợp lệ. |
| Bước nào là chờ không có giá trị mới? | Yêu cầu đủ thông tin nhưng phải đợi lịch họp định kỳ không cần thiết. |
| Ai có quyền quyết định thay đổi bước đó? | Service/security owner, người phụ trách hợp đồng hoặc Product Owner theo đúng phạm vi. |

Không phải Scrum Master hay Developers có thể tự tuyên bố một yêu cầu pháp lý **“không Lean”** rồi bỏ nó.

### 22.2. Rủi ro chuyển lãng phí sang đối tác hoặc vận hành

Một đội có thể:

- Bỏ một bước kiểm thử nội bộ và bắt QA xử lý sau release.
- Merge nhanh nhưng đẩy lỗi sang on-call.
- Tăng throughput bằng cách đưa mọi yêu cầu nhỏ tới Platform team không còn công suất.
- Giảm số ticket trực tiếp bằng cách làm người dùng bỏ cuộc trước khi mở ticket.

Các thay đổi ấy có thể làm **metric cục bộ tốt hơn trong khi tổng chi phí hệ thống tăng**. Hãy quan sát người dùng, support, công suất liên nhóm và sự cố sau phát hành.

### 22.3. Vendor có nhịp riêng cũng là một phần của value stream

Nếu nhóm phụ thuộc dịch vụ định danh bên ngoài có lịch nâng cấp theo quý, có thể:

- Chốt hợp đồng API/version hiện hành.
- Làm contract tests và adapter để giảm coupling.
- Đặt lịch sandbox trước mốc cần biết.
- Tách tính năng tương lai nếu nó không bắt buộc cho giá trị hiện tại.
- Duy trì khả năng rollback/forward fix và support.

Nhưng không ép vendor bỏ phê duyệt an toàn hoặc tự dùng một version hết hỗ trợ để “giảm wait time”. Cần hợp đồng và quyền quyết định phù hợp.

### 22.4. Bảo vệ năng lực và sự phát triển của con người

Mục tiêu không phải có 100% thời gian “productive” theo biểu mẫu. Cần có năng lực cho:

- Học kỹ thuật mới và pairing.
- Quan sát người dùng/support.
- Sửa nợ kỹ thuật gây rủi ro.
- Phân tích incident, thử nghiệm và cải tiến hệ thống.
- Hỗ trợ review, test, gỡ blocker.
- Nghỉ ngơi và làm việc bền vững.

Nếu không dành năng lực cho những hoạt động này, hệ thống có thể **tối ưu quá ngắn hạn, tích lũy defects và giảm khả năng thích ứng**.

## 23. Các phản mẫu khi vận dụng Lean

| Phản mẫu | Vì sao nguy hiểm? | Hướng sửa |
| --- | --- | --- |
| **“Lean nghĩa là cắt bớt nhân sự”** | Bỏ qua lãng phí hệ thống, làm người làm giấu vấn đề. | Tập trung flow, chất lượng, cải tiến và tôn trọng con người. |
| **Coi mọi test/review/tài liệu là lãng phí** | Hạ chuẩn, tăng lỗi và rủi ro sau release. | Phân biệt kiểm soát cần thiết với bước không tạo giá trị. |
| **Tối ưu số task cá nhân** | Có nhiều Done cục bộ nhưng Increment không dùng được. | Đo toàn chuỗi giá trị và chất lượng. |
| **Làm VSM trên sơ đồ quy trình lý tưởng** | Không phát hiện waiting/rework thực. | Theo một số item thật, xem lịch sử và gemba. |
| **Đo lead time và cycle time cùng tên** | So số liệu sai ranh giới. | Công bố Started/Finished, loại item và phạm vi. |
| **Flow efficiency thành KPI cá nhân** | Khuyến khích bỏ hoạt động cần thiết hoặc ghi active tùy tiện. | Dùng chỉ số để thảo luận cải tiến hệ thống. |
| **Tăng WIP vì muốn ai cũng bận** | Tăng đổi ngữ cảnh, hàng đợi, rework. | Pull, WIP policies, giúp hoàn tất item già. |
| **Đặt WIP limit mà không có cách xử lý blocked** | Người làm không biết nên làm gì, bottleneck bị che. | Explicit policies, owner và escalation. |
| **Chỉ nhìn item Done** | Bỏ quên item đang dở lớn/quan trọng. | Theo dõi work item age và blocked time. |
| **Lấy một trung vị để dự báo mọi loại PBI** | Trộn item nhỏ/lớn và rủi ro không tương đồng. | Phân loại, xem phân bố và mức bất định. |
| **Giảm waiting một bước bằng chuyển sang nhóm khác** | Tối ưu cục bộ, tổng lead time không cải thiện. | VSM end-to-end, xem tải provider/support. |
| **Mua công cụ trước khi biết nguyên nhân** | Tạo thêm chi phí và chuyển đổi mà không giảm waste. | Quan sát, giả thuyết và thử đối sách nhỏ. |
| **Automate một quy trình không cần thiết** | Lãng phí chạy nhanh hơn, tăng complexity. | Xem mục đích và loại bỏ bước thừa trước. |
| **PR thật nhỏ nhưng chẻ giả** | Số PR đẹp, tăng rework/handoff. | Chia theo thay đổi có thể kiểm chứng, không theo KPI số dòng. |
| **Mock xanh được coi là Increment tích hợp** | Không có bằng chứng provider thật/data integrity. | Contract/integration/E2E tests theo rủi ro. |
| **Xóa blocked state khỏi bảng** | WIP giảm giả, item bị lãng quên. | Giữ tuổi item và lý do chờ minh bạch. |
| **Đổi tiêu chí Done để cycle time đẹp** | Không còn so được chất lượng/metric. | Giữ DoD/định nghĩa công bố; ghi thay đổi nếu hợp lệ. |
| **Retrospective tạo 30 action items** | WIP cải tiến lớn, không theo dõi hiệu quả. | Chọn ít thử nghiệm có owner, metric và mốc xem. |
| **Tuyên bố thành công sau một tuần ít dữ liệu** | Ngẫu nhiên hoặc loại việc khác có thể gây chênh lệch. | Ghi yếu tố gây nhiễu, xem nhiều chu kỳ phù hợp. |
| **Tối ưu delivery mà không hỏi người dùng** | Giao nhanh những tính năng ít giá trị. | Product discovery và outcome. |
| **Giảm support ticket bằng làm kênh liên hệ khó dùng** | Người dùng bị bỏ rơi, số liệu đẹp giả. | Đo khả năng hoàn tất tác vụ và tác động tới người dùng. |
| **Xem mura/muri là lỗi cá nhân** | Thiếu an toàn tâm lý, khó tìm bottleneck thật. | Tìm nguyên nhân hệ thống và bảo vệ năng lực bền vững. |
| **Ép nhà cung cấp chạy đúng Sprint đội mình** | Không giải quyết giới hạn hợp đồng/quyền. | Tách nhịp, contract tests, milestones và phương án thích ứng. |
| **Coi công thức Little's Law là dự báo chắc chắn** | Bỏ qua bất ổn, loại việc và mốc đo. | Chỉ dùng khi điều kiện áp dụng phù hợp, kiểm tra dữ liệu. |
| **Không cập nhật future-state map sau thử nghiệm** | Sơ đồ thành tài liệu lỗi thời. | Theo dõi điều đã học, thay giả thuyết và chính sách. |

## 24. Bài tập thực hành và đáp án gợi ý

### Bài tập 1 — Giá trị, output và outcome

Một đội giao ba endpoint API đăng ký mới, thêm hai dashboard nội bộ và đóng 18 task. Trong kỳ quan sát, học viên vẫn hỏi support “đã đăng ký thành công chưa?” với số lượng không giảm.

**Yêu cầu:**

1. Nêu ba output trong tình huống.
2. Viết một outcome gắn với hành trình người học.
3. Đề xuất hai cách lấy bằng chứng về outcome mà không vi phạm riêng tư.
4. Giải thích vì sao output tăng không chứng minh giá trị tăng.

**Gợi ý:** API, dashboard và task Done là output/hoạt động. Outcome có thể là tỷ lệ học viên **tự xác minh trạng thái đúng** sau timeout tăng, số yêu cầu hỗ trợ cùng loại giảm **trên tập người dùng thao tác được định nghĩa**, không tăng đăng ký trùng. Có thể dùng số liệu aggregate được phép và quan sát tác vụ với sự đồng ý; không thu thêm dữ liệu cá nhân chỉ để làm báo cáo đẹp.

### Bài tập 2 — Phân loại tám dạng lãng phí

Xét các tình huống:

1. Một PBI được chuyển qua năm nhóm, mỗi nhóm hỏi lại bối cảnh.
2. Có 16 PR mở chờ review.
3. Một Developer phải mở bảy hệ thống để tìm đúng log.
4. QA chờ dữ liệu tích hợp ba ngày.
5. Đội tạo tính năng xuất file không có bằng chứng nhu cầu.
6. Hai bộ phận yêu cầu hai mẫu báo cáo giống nhau, nhập thủ công.
7. Retry gây ghi hai đăng ký hiệu lực.
8. Người thấy rủi ro DB nhưng không được tham gia thảo luận.

**Yêu cầu:** ghép với transportation, inventory, motion, waiting, overproduction, overprocessing, defects và unused talent.

**Đáp án gợi ý:** (1) chuyển giao, (2) tồn kho, (3) thao tác/tìm kiếm, (4) chờ, (5) sản xuất vượt nhu cầu, (6) xử lý quá mức, (7) lỗi và làm lại, (8) chưa khai thác năng lực. Một tình huống có thể thuộc nhiều nhóm; mục đích là **mở giả thuyết điều tra**, không tranh luận nhãn cho đúng một ô.

### Bài tập 3 — Muda, Mura và Muri

Nhóm đang rảnh tương đối trong ba ngày đầu Sprint. Ngày cuối, 12 PR vào Review cùng lúc, một chuyên gia phải duyệt và test team nhận nhiều hạng mục chưa tích hợp.

**Yêu cầu:** chỉ ra ví dụ của Mura, Muri, Muda. Đề xuất một cách cải tiến **không yêu cầu làm thêm giờ**.

**Gợi ý:** công việc dồn cuối Sprint là Mura; một reviewer và nhóm test bị quá tải là Muri; chờ review/test, làm lại và chuyển ngữ cảnh là Muda. Có thể thử PR nhỏ, tích hợp/test sớm, làm rõ acceptance examples và giới hạn WIP. Cần đo tuổi item, blocked time, lỗi và tải người.

### Bài tập 4 — Tính thời gian và flow efficiency hiện tại

Một Value Stream Map giả định có:

| Bước | Active time | Waiting time |
| --- | ---: | ---: |
| Làm rõ | 0,5 ngày | 2 ngày |
| Hợp đồng | 0,5 ngày | 2,5 ngày |
| Code | 1,5 ngày | 2 ngày |
| Review/CI | 0,5 ngày | 1,5 ngày |
| Integration | 1 ngày | 3 ngày |
| Release | 0,5 ngày | 2 ngày |

**Giả sử tất cả khoảng tuần tự, không chồng lấn.** Tính total active time, total waiting time, lead time theo ranh giới đã chọn và flow efficiency.

**Đáp án:**

\[
\text{Active}=0,5+0,5+1,5+0,5+1+0,5=4,5\text{ ngày}.
\]

\[
\text{Waiting}=2+2,5+2+1,5+3+2=13\text{ ngày}.
\]

\[
\text{Lead time}=4,5+13=17,5\text{ ngày}.
\]

\[
\text{Flow efficiency}=4,5/17,5\times100\%\approx25,7\%.
\]

Nếu các hoạt động chồng lấn, không được cộng active person-days thành elapsed days; cần xem dữ liệu thời gian thực.

### Bài tập 5 — So sánh current state và future state

Một future-state map đặt mục tiêu **4 ngày active + 5,5 ngày chờ**, vẫn giữ DoD và kiểm soát bắt buộc. Current state theo bài 4 là **17,5 ngày**.

**Yêu cầu:**

1. Tính total time và flow efficiency tương lai.
2. Tính mức giảm tổng thời gian trong mô hình.
3. Giải thích vì sao chưa thể cam kết chắc chắn các con số này.
4. Nêu ít nhất ba guardrails.

**Đáp án gợi ý:** total = **9,5 ngày**; flow efficiency \(\approx42,1\%\); mức giảm mô hình = **8 ngày**. Future state mới là **giả thuyết**, phụ thuộc loại việc, WIP, môi trường, rework và rủi ro. Guardrails gồm DoD không giảm, không tăng lỗi đăng ký trùng, không lộ dữ liệu, không tăng giờ làm thêm/support burden.

### Bài tập 6 — Phân biệt lead time và cycle time

Một nhu cầu được ghi nhận ngày 1, chọn bắt đầu phát triển ngày 8, code merge ngày 12, đạt DoD ngày 15, phát hành cho người dùng ngày 18.

**Yêu cầu:** xác định ba khoảng thời gian có thể được gọi là **idea-to-user lead time**, **development cycle time** và **merge-to-release wait**, nếu định nghĩa phù hợp. Vì sao phải ghi mốc?

**Gợi ý:** nếu dùng **chênh lệch thời điểm** theo đơn vị ngày, idea-to-user = ngày 18 trừ ngày 1 = **17 ngày**, development cycle = ngày 15 trừ ngày 8 = **7 ngày**, merge-to-release = ngày 18 trừ ngày 12 = **6 ngày**. Đây là quy ước **elapsed time giữa mốc**, không đếm số ngày theo lịch bao gồm cả ngày đầu/cuối. Không nên so những chu kỳ đo khác nhau mà không nêu định nghĩa, lịch làm việc, timezone và loại item.

### Bài tập 7 — Little's Law trong phạm vi áp dụng

Một workflow ổn định tương đối có trung bình **8 PBI đang dở** và hoàn tất trung bình **4 PBI/tuần**.

**Yêu cầu:** suy ra thời gian trung bình theo Little's Law và nêu ba điều kiện khiến không thể dùng nó như dự báo chắc chắn một PBI.

**Gợi ý:**

\[
\text{Cycle time trung bình}\approx8/(4\text{ PBI/tuần})=2\text{ tuần}.
\]

Giới hạn: hệ thống không ổn định do incident, thay ranh giới Started/Finished, loại PBI quá khác nhau, dữ liệu chưa đủ, hoặc luồng vào–ra không cân bằng trong kỳ ngắn. Không kết luận mọi PBI xong sau hai tuần.

### Bài tập 8 — Đánh giá bottleneck khi WIP tăng

Developing có hai item chờ Review, trong khi Review đang có sáu item chờ một reviewer. Người làm Development định mở bốn PBI mới để không bị “rảnh”.

**Câu hỏi:**

1. Vì sao mở thêm việc có thể làm tổng flow xấu hơn?
2. Những hành động nào nhóm có thể thử trước?
3. Cần những metrics nào để kiểm tra hiệu quả?

**Gợi ý:** mở thêm tăng WIP và chuyển ngữ cảnh, không giải quyết năng lực review. Có thể giúp chuẩn bị review, chia PR nhỏ, người review dự phòng **đủ thẩm quyền**, cải thiện CI hoặc xử lý blockers. Xem work item age, blocked time, cycle time, throughput, lỗi review và tải nhân sự.

### Bài tập 9 — Một bước kiểm soát có phải lãng phí?

Nhóm muốn bỏ test phân quyền vì nó chạy lâu và “người dùng không nhìn thấy”. PBI liên quan API tra lịch sử đăng ký riêng.

**Yêu cầu:** phân loại kiểm thử đó, phân biệt **cải tiến quá trình kiểm thử** và **loại bỏ kiểm soát**, đề xuất hai cách giảm thời gian mà vẫn an toàn.

**Gợi ý:** kiểm tra quyền là hoạt động cần thiết bảo vệ dữ liệu và DoD. Có thể tối ưu setup/dữ liệu giả, chạy song song khi độc lập, cải thiện CI runner hoặc đưa contract/security tests sớm. Không bỏ phép kiểm chứng quyền để chỉ số flow tốt hơn.

### Bài tập 10 — Viết giả thuyết PDCA

Nhóm quan sát **7/12 PR** trong hai tuần chờ reviewer hơn một ngày. Một người đề nghị mua một công cụ quản lý PR mới.

**Yêu cầu:** viết giả thuyết theo mẫu **Nếu… thì… vì…**; nêu baseline, metric chính, hai guardrails và điều kiện làm nhóm thay đổi giả thuyết.

**Ví dụ:**

> “Nếu một reviewer dự phòng đủ chuyên môn cùng chính sách chọn PR nhỏ được áp dụng cho các thay đổi API rủi ro vừa, thời gian chờ review sẽ giảm so với kỳ nền, vì bớt hàng đợi ở một người và giảm chi phí đọc ngữ cảnh.”

Metric chính: thời gian ready-to-useful-review. Guardrails: escaped defects và tải/giờ làm thêm reviewer. Nếu lịch sử cho thấy phần lớn thời gian thực là chờ CI, cần chuyển giả thuyết sang CI chứ không vội mua công cụ.

### Bài tập 11 — Lean và Scrum

Một Scrum Team đóng 32 task trong Sprint nhưng không có Increment tích hợp đáp ứng DoD. Sprint Review chỉ có slide. Retrospective ghi “QA chậm” nhưng không có dữ liệu.

**Yêu cầu:** đề xuất ba thay đổi cụ thể liên quan **Sprint Goal, Sprint Review và Retrospective**, kèm bằng chứng kiểm chứng.

**Gợi ý:**

- Sprint Goal hướng **một kết quả người dùng** thay vì số task.
- Review kiểm tra Increment thực và lấy phản hồi về Product Goal, không chỉ slide.
- Retro theo một PBI qua flow, xem blocked/rework, thử contract-first/CI sớm.

Không hạ DoD hoặc biến Daily Scrum thành báo cáo quản lý để cải thiện “tiến độ”.

### Bài tập 12 — Lean và Kanban

Bảng có Ready → Developing → Verify → Done. Một PBI ở Verify **12 ngày** chưa Finished, nhưng median cycle time của các item Done gần đây chỉ **3 ngày**.

**Câu hỏi:** vì sao median đẹp không bảo đảm flow tốt? Chỉ số nào giúp nhóm hành động sớm, và điều nên làm là gì?

**Gợi ý:** PBI chưa Done chưa có trong median cycle time item hoàn tất, có thể bị bỏ quên. Cần **work item age, blocked reason, WIP, throughput và phân bố cycle time**. Tìm điều kiện chặn và giúp hoàn tất an toàn, không chuyển Done giả.

### Bài tập 13 — Lean và XP: CI nhanh nhưng mất chất lượng

Một nhóm giảm pipeline từ 35 xuống 12 phút bằng cách bỏ toàn bộ integration tests. Sau đó lỗi ghi đăng ký trùng tăng.

**Yêu cầu:** giải thích sự đánh đổi bị bỏ qua và đề xuất một thí nghiệm cải tiến khác.

**Gợi ý:** giảm thời gian chờ CI nhưng chuyển lỗi sang production, tăng rework/support và phá mục tiêu chất lượng. Thử parallelization phù hợp, isolate data, test phân tầng, sửa flaky tests và tăng runner capacity theo bằng chứng; giữ test bắt buộc. Đo feedback time cùng escaped defects và mainline reliability.

### Bài tập 14 — VSM qua nhiều nhóm và vendor

PBI phải qua Web, API, DB, kiểm thử, provider Identity và Release. Một vendor chỉ có sandbox hai ngày/tháng. Tất cả nhóm báo hoàn tất task trước ngày mở sandbox nhưng lúc đó contract mismatch xuất hiện.

**Yêu cầu:** đề xuất một kế hoạch giảm chờ mà không yêu cầu vendor chạy cùng Sprint.

**Gợi ý:** chốt version/contract sớm, viết contract tests, mock có ghi giới hạn, đặt sandbox trước, giữ adapter, tích hợp bản provider thật trong cửa sổ được phép, chuẩn bị test data, có đường fallback/đổi phạm vi khi an toàn. Không coi mock xanh là chứng cứ cuối; không đổi lịch vendor bằng lời hứa trong Sprint Planning.

### Bài tập 15 — Tranh luận về overproduction

Team Product muốn xây ngay 20 báo cáo mới dù chỉ có hai báo cáo được người dùng truy cập thường xuyên. Engineering cho rằng có thể làm nhanh bằng code generator.

**Yêu cầu:** phân biệt **chi phí xây thấp** với **giá trị được kiểm chứng**. Thiết kế một cách học sớm trước khi làm cả 20.

**Gợi ý:** code generator không làm tính năng vô giá trị trở nên có giá trị. Hãy hỏi tác vụ người dùng, kiểm tra mức sử dụng theo quyền được phép, phỏng vấn, thử một báo cáo có mục tiêu và đo outcome. Nếu nhiều báo cáo bắt buộc theo pháp lý/hợp đồng, cần xác minh nghĩa vụ trước khi kết luận đó là waste.

### Bài tập 16 — Đọc cải tiến trước–sau có yếu tố gây nhiễu

Trong hai kỳ cùng dài hai tuần, nhóm ghi:

| Kỳ | PBI Finished | Cycle time trung vị | Lỗi hậu phát hành |
| --- | ---: | ---: | ---: |
| Trước WIP limit | 10 | 9 ngày | 1 |
| Sau WIP limit | 12 | 6 ngày | 2 |

Kỳ thứ hai còn có một người review trở lại sau nghỉ và tập PBI nhỏ hơn.

**Yêu cầu:** viết một kết luận đúng, nêu hai dữ liệu cần thu thêm và cách xử lý nếu hai lỗi mới nghiêm trọng.

**Gợi ý:** có tín hiệu cycle time giảm và số item Finished tăng, nhưng chưa thể quy hoàn toàn cho WIP limit do loại việc và năng lực review đã thay đổi. Cần xem work item age/blocked time và mức độ lỗi/DoD, phân bố loại item. Nếu lỗi nghiêm trọng, ưu tiên khắc phục và bảo vệ người dùng, dừng mở rộng biện pháp có liên quan theo đánh giá rủi ro.

### Bài tập 17 — Vẽ VSM cho tình huống thật

Chọn một hành trình có thể quan sát trong dự án hoặc tình huống học tập, ví dụ:

- Từ báo lỗi đăng nhập tới bản sửa được sử dụng.
- Từ user story đăng ký tới Increment Done/release.
- Từ ticket hỗ trợ “trạng thái khóa học không rõ” tới giải quyết.
- Từ thay đổi API tới kiểm chứng với nhà cung cấp bên ngoài.

**Yêu cầu tạo một bản VSM đủ dùng:**

1. Định nghĩa rõ **bắt đầu, kết thúc, loại item và người nhận giá trị**.
2. Vẽ ít nhất năm bước và các vòng rework nếu có.
3. Ghi touch time, waiting time, WIP và phần **chưa có dữ liệu**.
4. Phân loại ít nhất ba dấu hiệu Muda/Mura/Muri **với lý do và nguồn**.
5. Chọn **một** đối sách nhỏ, cơ chế kỳ vọng và guardrails.
6. Vẽ future state giả định, không trình bày như dự báo chắc chắn.
7. Thiết kế PDCA có owner, mốc xem và nhánh quyết định giữ/điều chỉnh/hoàn tác.

**Tiêu chí đánh giá bài làm:**

| Tiêu chí | Bài làm đạt khi |
| --- | --- |
| **Giá trị rõ** | Có người nhận giá trị và outcome, không chỉ task kỹ thuật. |
| **Ranh giới đúng** | Started/Finished, loại item, đơn vị thời gian nhất quán. |
| **Bằng chứng thật/giả định rõ** | Không biến con số đoán thành dữ liệu thực. |
| **Nhìn toàn luồng** | Có waiting/handoff/rework, không chỉ coding time. |
| **Phân loại có lý do** | Waste gắn với điều kiện hệ thống, không đổ lỗi cá nhân. |
| **Giải pháp có cơ chế** | Có giả thuyết có thể kiểm chứng và thử nhỏ. |
| **Giữ guardrails** | Không bỏ DoD, bảo mật, dữ liệu hoặc nghĩa vụ bắt buộc. |
| **Biết học từ kết quả** | Có cách thu bằng chứng và hành động sau thử. |

## 25. Checklist vận dụng Lean trong một dòng giá trị Agile

### A. Hiểu giá trị trước khi tối ưu

- [ ] Xác định được **người nhận giá trị** và hành vi/kết quả mong muốn.
- [ ] Phân biệt **activity, output, outcome** trong mục tiêu cải tiến.
- [ ] Biết Product Goal hoặc mục tiêu nghiệp vụ mà cải tiến sẽ phục vụ.
- [ ] Có bằng chứng người dùng thực sự cần khả năng định xây, thay vì chỉ giả định.
- [ ] Xác định các điều kiện **không được đánh đổi**: dữ liệu, bảo mật, an toàn, vận hành, nghĩa vụ.
- [ ] Không dùng số ticket/commit/story points thay outcome người dùng.
- [ ] Nếu chưa đủ bằng chứng giá trị, cân nhắc khám phá/kiểm chứng sớm trước khi xây batch lớn.

### B. Vẽ Value Stream Map hiện tại

- [ ] Chọn **một loại hạng mục** đủ đồng nhất để phân tích.
- [ ] Định nghĩa mốc **bắt đầu, kết thúc và đơn vị thời gian**.
- [ ] Theo công việc thực qua phân tích, code, test, review, release và phản hồi khi phù hợp.
- [ ] Có đầu vào/đầu ra, owner và điều kiện chuyển của từng bước.
- [ ] Ghi **active/process time** và **waiting/queue time** theo định nghĩa.
- [ ] Ghi những vòng **rework**, retry, lỗi hợp đồng và phụ thuộc.
- [ ] Thấy WIP/blocked work, không chỉ những item Done đẹp.
- [ ] Biết phần nào là quan sát thực, phần nào mới là giả định.
- [ ] Dữ liệu từ bảng công việc, CI, vận hành và người trực tiếp làm được đối chiếu khi cần.
- [ ] Không cộng khoảng chồng lấn như thể thời gian lịch tuần tự.

### C. Nhận diện lãng phí và nguyên nhân

- [ ] Xét transportation, inventory, motion, waiting, overproduction, overprocessing, defects và unused talent trong đúng ngữ cảnh.
- [ ] Xem Muda cùng **Mura (không đều)** và **Muri (quá tải)**.
- [ ] Phân biệt **bước bắt buộc/cần thiết** với lãng phí có thể bỏ.
- [ ] Hỏi vì sao quy trình tạo hàng đợi, không kết luận do cá nhân “lười” hoặc “chậm”.
- [ ] Xem contract, kiến trúc, test, quyền, công suất, chính sách và mục tiêu sản phẩm.
- [ ] Kiểm tra các **nguyên nhân thay thế**, không coi phân loại waste là chứng minh nhân quả.
- [ ] Ưu tiên bottleneck ảnh hưởng flow/outcome thật, không chỉ bước có nhiều task.

### D. Thiết kế trạng thái tương lai

- [ ] Vẽ **future state như giả thuyết** có điều kiện, không hứa chính xác thời gian.
- [ ] Cân nhắc loại bỏ bước thừa **trước** khi tự động hóa.
- [ ] Xem khả năng giảm WIP, batch size, chuyển giao và đổi ngữ cảnh.
- [ ] Đưa làm rõ nghiệp vụ/contract/test sớm hơn trong dòng giá trị.
- [ ] Thử capability tự phục vụ có phân quyền thay các hàng đợi cấp tài nguyên lặp lại.
- [ ] Chọn cách tích hợp/release tương thích để giảm chờ mà không tăng rủi ro.
- [ ] Giữ những phép kiểm tra bắt buộc và Definition of Done tương ứng.
- [ ] Xem khả năng công việc dồn sang nhóm/vendor/support khác.

### E. Thử nghiệm cải tiến

- [ ] Có **problem statement** gắn với sự kiện quan sát.
- [ ] Giả thuyết có cấu trúc **Nếu… thì… vì…** và có thể sai.
- [ ] Thử nghiệm đủ nhỏ, có phạm vi, owner và mốc xem kết quả.
- [ ] Có **baseline** theo cách đo nhất quán.
- [ ] Có **metric chính** đúng với vấn đề và một số guardrails cần thiết.
- [ ] Có điều kiện dừng/điều chỉnh hoặc hoàn tác cho tác động bất lợi.
- [ ] Không thay thước đo sau thử chỉ để gọi kết quả là “thành công”.
- [ ] Ghi yếu tố gây nhiễu: loại PBI, kỳ nghỉ, môi trường, mức tải, DoD thay đổi.
- [ ] Không thí nghiệm vô trách nhiệm trên dữ liệu thật hoặc người dùng khi chưa đáp ứng quyền/điều kiện.

### F. Đo lường theo luồng và bảo vệ chất lượng

- [ ] Theo dõi WIP, work item age, cycle time, throughput theo **Definition of Workflow** phù hợp.
- [ ] Dùng blocked time/queue time để tìm điểm nghẽn có cơ chế rõ.
- [ ] Biết phân biệt **lead time từ nhu cầu** với **cycle time từ Started**.
- [ ] Chỉ tính flow efficiency với định nghĩa active/elapsed và giả định thích hợp.
- [ ] Khi dùng Little's Law, ghi các giả định về ổn định và mốc đo.
- [ ] Xem quality guardrails: DoD, escaped defects, rework, dữ liệu và bảo mật.
- [ ] Xem outcome người dùng, không chỉ delivery speed.
- [ ] Đừng bỏ quên item chưa Done hoặc item rủi ro cao trong thống kê.
- [ ] Không dùng metric để xếp hạng cá nhân khác loại công việc.
- [ ] Xem mức tải của QA, reviewer, support, on-call và các nhóm ngoài.

### G. Kết thúc một vòng cải tiến

- [ ] Đối chiếu kết quả với **dự đoán ban đầu**, không chọn lại tiêu chí cho đẹp.
- [ ] Phân biệt tín hiệu quan sát với khẳng định nhân quả.
- [ ] Ghi hạn chế dữ liệu và những trường hợp chưa được kiểm chứng.
- [ ] Quyết định **duy trì, điều chỉnh, hoàn tác hoặc thử tiếp**.
- [ ] Nếu hữu ích, cập nhật working agreement, DoW, CI, test, runbook hoặc backlog đúng quyền.
- [ ] Có người theo dõi sau khi chuẩn hóa, nhất là khi loại việc hoặc quy mô đổi.
- [ ] Nhóm biết **vì sao chính sách hiện tại tồn tại**, không chỉ làm theo thói quen.
- [ ] Chọn điểm nghẽn hoặc giả thuyết tiếp theo dựa trên giá trị còn thiếu.

Checklist nhằm hỗ trợ **học hỏi và quyết định**, không cần biến thành một tầng phê duyệt thủ công mới. Với thay đổi nhỏ, một thẻ thử nghiệm có thể đủ; với hệ thống rủi ro cao, cần bằng chứng và thẩm quyền tương xứng.

## 26. Tổng kết

**Vận dụng Lean để nhận diện lãng phí và cải thiện dòng giá trị** là cách giúp đội Agile hiểu vì sao nhiều hoạt động được thực hiện nhưng giá trị vẫn tới người dùng chậm, khó kiểm chứng hoặc thiếu tin cậy.

Thực hành tốt cần nhớ:

1. **Bắt đầu từ giá trị:** người dùng cần kết quả gì, không chỉ nhóm đang bận việc gì.
2. **Nhìn dòng giá trị đầu–cuối:** nhu cầu → lựa chọn → triển khai → tích hợp/kiểm chứng → sử dụng/phản hồi; ghi cả chờ và làm lại.
3. **Nhận diện lãng phí có bối cảnh:** bảy/tám dạng Muda và tác động của Mura/Muri, không dùng chúng để quy lỗi con người.
4. **Giữ hoạt động bảo vệ chất lượng:** DoD, kiểm thử phân quyền/dữ liệu và nghĩa vụ là những điều kiện cần cải tiến cách làm, không phải bỏ đi.
5. **Giảm WIP, batch size và thời gian chờ:** tạo khả năng hoàn tất, tích hợp thường xuyên và phát hiện rủi ro sớm.
6. **Đo đúng ranh giới:** lead time, cycle time, blocked time, work item age, throughput, flow efficiency và chất lượng không thay thế nhau.
7. **Chỉ chọn biện pháp có cơ chế:** contract-first, pull policies, self-service, automation hoặc đội liên chức năng tùy nguyên nhân.
8. **Thử nhỏ, học thật:** baseline, giả thuyết, metric chính, guardrails, yếu tố gây nhiễu, quyết định tiếp theo.
9. **Không tối ưu cục bộ:** giảm hàng đợi ở frontend nhưng chuyển quá tải sang QA hoặc support chưa phải cải thiện hệ thống.
10. **Kết hợp cách tiếp cận:** Scrum tạo vòng kiểm tra–thích ứng theo mục tiêu, Kanban giúp nhìn flow, XP tạo phản hồi kỹ thuật nhanh, Lean giữ trọng tâm giá trị và hệ thống.

Một nhóm thành công với Lean không nhất thiết có **ít bước nhất, nhiều tự động hóa nhất hoặc mọi người bận nhất**. Họ có khả năng **tạo giá trị đúng, sớm, đáng tin cậy và bền vững hơn**, đồng thời liên tục thay đổi cách làm khi bằng chứng cho thấy điều gì chưa hiệu quả.

### Bảng thuật ngữ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Lean** | Tư duy xác định giá trị, nhìn dòng giá trị, tạo flow, pull và cải tiến liên tục. |
| **Value** | Lợi ích/khả năng đáp ứng nhu cầu của người nhận giá trị trong bối cảnh. |
| **Value stream** | Toàn chuỗi hoạt động từ nhu cầu tới kết quả người dùng theo phạm vi xác định. |
| **Value Stream Mapping (VSM)** | Kỹ thuật trực quan hóa hoạt động, hàng đợi, thời gian và rework trong chuỗi giá trị. |
| **Current state / Future state** | Bản đồ hiện trạng / trạng thái mục tiêu giả định cần kiểm chứng. |
| **Muda** | Lãng phí, hoạt động không tạo giá trị hoặc không cần thiết theo bối cảnh. |
| **Mura** | Sự không đều/biến động của luồng công việc và nhu cầu. |
| **Muri** | Quá tải của người hoặc năng lực xử lý hệ thống. |
| **Seven wastes** | Transportation, inventory, motion, waiting, overproduction, overprocessing, defects. |
| **Unused talent** | Dạng lãng phí thứ tám thường được bổ sung: không khai thác ý tưởng/năng lực con người. |
| **Transportation / Motion** | Chuyển giao công việc/đầu ra / thao tác, tìm kiếm và di chuyển không cần thiết. |
| **Inventory / WIP** | Tồn kho/việc đang dở theo phạm vi đã định nghĩa. |
| **Waiting / Blocked time** | Chờ đợi / thời gian hạng mục không thể tiến triển theo điều kiện đã ghi. |
| **Overproduction / Overprocessing** | Tạo quá nhiều/quá sớm điều không cần / xử lý quá mức không tăng giá trị. |
| **Defects / Rework** | Sai lỗi / công việc phải làm lại để đáp ứng điều đúng. |
| **Touch time / Process time** | Thời gian thực hiện công việc trực tiếp theo cách đo đã chọn. |
| **Queue time** | Thời gian item chờ trước hoặc giữa các bước xử lý. |
| **Flow efficiency** | Tỷ lệ active/process time trên elapsed time theo ranh giới đo phù hợp. |
| **Lead time** | Thời gian từ mốc nhu cầu/đặt yêu cầu được xác định tới mốc kết thúc tương ứng. |
| **Cycle time** | Thời gian Started → Finished của item theo Definition of Workflow. |
| **Work item age** | Thời gian một item đang dở đã tồn tại từ Started tới hiện tại. |
| **Throughput** | Số item Finished trong một khoảng thời gian. |
| **Pull system** | Cách nhận/kéo việc dựa trên năng lực hiện có và policy thay vì đẩy việc bất chấp hàng đợi. |
| **WIP limit** | Chính sách giới hạn lượng công việc dở trong một vùng workflow. |
| **Batch size** | Kích thước nhóm thay đổi/hạng mục được thực hiện hoặc chuyển tiếp cùng một đợt. |
| **Bottleneck / Constraint** | Điểm giới hạn năng lực hoặc điều kiện ràng buộc khả năng hoàn tất toàn hệ thống. |
| **Little's Law** | Quan hệ giữa WIP, throughput và thời gian trung bình khi các điều kiện áp dụng được thỏa. |
| **Gemba** | Quan sát nơi công việc/giá trị thực sự diễn ra để hiểu hệ thống. |
| **Kaizen** | Cải tiến liên tục có sự tham gia và tôn trọng người làm. |
| **PDCA / PDSA** | Plan–Do–Check/Study–Act: lập kế hoạch, thử, kiểm tra/học và điều chỉnh. |
| **Quality at the source** | Ngăn/phát hiện sai lỗi gần nơi phát sinh thay vì đẩy lỗi qua nhiều bước. |
| **Definition of Done (DoD)** | Cam kết chất lượng để một Increment được coi hoàn tất trong Scrum. |
| **Product Goal / Sprint Goal** | Mục tiêu dài hạn sản phẩm / mục tiêu thống nhất của Sprint. |
| **Definition of Workflow (DoW)** | Ranh giới và policy điều hành luồng công việc trong Kanban. |
| **Service Level Expectation (SLE)** | Kỳ vọng thời gian hoàn tất có tính xác suất dựa trên dữ liệu workflow. |
| **TDD / CI / XP** | Test-driven development / continuous integration / Extreme Programming. |
| **Vertical slice** | Lát cắt đi qua các tầng cần thiết để tạo hành vi có giá trị và kiểm chứng được. |
| **Contract test** | Kiểm tra kỳ vọng giao tiếp giữa những thành phần/consumer–provider. |
| **Outcome / Output** | Kết quả thực tế người dùng / sản phẩm hoặc khả năng được tạo ra. |
| **Cost of Delay** | Hậu quả kinh tế hoặc giá trị bị mất khi trì hoãn một kết quả. |
| **Theory of Constraints (TOC)** | Cách tư duy về ràng buộc chi phối thông lượng hệ thống, có liên quan nhưng không đồng nhất Lean. |
| **Guardrail metric** | Chỉ số/điều kiện bảo vệ an toàn, chất lượng hoặc tác động phụ của một cải tiến. |
| **Confounder** | Yếu tố khác có thể khiến cách diễn giải kết quả trước–sau bị sai lệch. |





