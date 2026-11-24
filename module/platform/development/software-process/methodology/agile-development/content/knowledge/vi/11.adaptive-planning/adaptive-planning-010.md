# Điều chỉnh kế hoạch khi phạm vi, nguồn lực hoặc giả định thay đổi

> **Chương:** Kế hoạch thích ứng  
> **Học phần:** **AGILE_DEVELOPMENT** — áp dụng giá trị và nguyên tắc Agile để phát triển phần mềm qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; sử dụng user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc theo bối cảnh.

Nhóm phát triển đã lên kế hoạch giao chức năng đặt lịch trực tuyến trong sáu tuần. Sau một vòng thử nghiệm, người dùng cần một bước xác nhận rõ hơn so với giả định ban đầu. Cùng lúc, một thành viên phải hỗ trợ sự cố production, còn API của đối tác không hoạt động như tài liệu mô tả. Nhóm không thể vừa giữ nguyên toàn bộ phạm vi, nguồn lực, ngày giao, thiết kế lẫn mức chất lượng như thể không có gì xảy ra.

**Kế hoạch thích ứng** là khả năng **đánh giá thông tin mới, giữ mục tiêu có giá trị, cập nhật lựa chọn thực hiện và truyền đạt tác động**. Nó không đồng nghĩa “đổi kế hoạch mỗi ngày” hoặc “không cần cam kết”. Một kế hoạch tốt cho thấy những gì đã biết, những gì đang giả định, ràng buộc nào phải giữ, điều kiện nào khiến dự báo cần thay đổi và ai có quyền quyết định.

Giá trị Agile “**Responding to change over following a plan**” (ưu tiên ứng phó thay đổi hơn bám theo kế hoạch) không phủ nhận giá trị của kế hoạch. Điều nhóm cần tránh là biến **bản dự báo ban đầu** thành mục tiêu quan trọng hơn **giá trị thật và chất lượng sản phẩm**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết các tác nhân thay đổi phổ biến: **phạm vi, nguồn lực/năng lực, giả định, phụ thuộc, rủi ro và ngày hạn cố định**.
2. Phân biệt **mục tiêu sản phẩm, phạm vi dự kiến, dự báo, cam kết và chuẩn chất lượng** để không đổi nhầm thứ phải giữ.
3. Thực hiện quy trình điều chỉnh kế hoạch gồm nhận diện tín hiệu, xác minh, phân tích tác động, tạo phương án, quyết định, truyền đạt và kiểm chứng.
4. Lập các phương án đánh đổi **phạm vi – thời gian – năng lực**, thay vì mặc nhiên nhận thêm việc hoặc yêu cầu làm thêm giờ.
5. Áp dụng thực hành Scrum, Kanban và XP để điều chỉnh kế hoạch mà vẫn giao sản phẩm tăng dần và duy trì chất lượng.
6. Sử dụng chỉ số dòng công việc, giả định, bằng chứng và dự báo có mức độ chắc chắn phù hợp để trao đổi với các bên liên quan.

## 2. Kế hoạch là mô hình dự báo, không phải mô tả chắc chắn tương lai

Khi viết “tính năng X sẽ hoàn tất trong hai Sprint”, nhóm thường đang ngầm giả định:

- Yêu cầu đủ rõ và người dùng thật cần chức năng đó.
- Những người có kỹ năng liên quan có đủ thời gian làm việc.
- Hệ thống đối tác, môi trường kiểm thử và dữ liệu sẵn sàng.
- Không có sự cố nghiêm trọng chiếm năng lực ngoài dự kiến.
- Kiểm thử, review, tích hợp và triển khai mất thời gian tương tự các lần trước.
- Chất lượng cần đạt đã được hiểu và không bị bỏ sót trong ước lượng.

Khi một giả định sai, **kế hoạch phải được đánh giá lại**, không phải âm thầm giữ nguyên mọi con số. Tuy nhiên, đổi dự báo cũng cần dựa trên bằng chứng thay vì cảm xúc sau một ngày làm việc không thuận lợi.

### 2.1. Phân biệt những thứ thường bị gộp chung

| Khái niệm | Bản chất | Câu hỏi khi có thay đổi |
| --- | --- | --- |
| **Product Goal / kết quả mong muốn** | Hướng giá trị cần đạt cho người dùng hoặc tổ chức. | Mục tiêu còn phù hợp hay chính giả định về nhu cầu đã sai? |
| **Phạm vi dự kiến** | Những khả năng, hạng mục backlog và lựa chọn giải pháp có thể làm. | Phần nào bắt buộc để đạt mục tiêu, phần nào có thể chia nhỏ, hoãn hoặc bỏ? |
| **Kế hoạch / forecast** | Dự báo về thứ tự thực hiện, phụ thuộc, chi phí và thời gian. | Dữ liệu mới làm thay đổi dự báo ở đâu và mức độ tin cậy bao nhiêu? |
| **Cam kết** | Nghĩa vụ hoặc trách nhiệm đã thống nhất, có thể liên quan hợp đồng, mục tiêu hoặc thời hạn. | Cần thực hiện đúng nghĩa vụ nào, thay đổi gì phải được người có thẩm quyền phê duyệt? |
| **Năng lực khả dụng** | Thời gian, kỹ năng, môi trường và nguồn lực thực sự có thể sử dụng. | Bao nhiêu năng lực còn lại và công việc nào đã bị chiếm dụng? |
| **Chuẩn chất lượng / ràng buộc bắt buộc** | Definition of Done (nếu dùng Scrum), bảo mật, an toàn, pháp lý, tính đúng đắn. | Làm sao bảo vệ chuẩn này khi phạm vi hoặc lịch bị áp lực? |

Ví dụ: **Sprint Goal** trong Scrum tạo mục tiêu chung cho một Sprint; nó không đồng nhất với danh sách từng Product Backlog Item được dự kiến hoàn tất. Một thay đổi có thể khiến nhóm thương lượng lại phạm vi mà vẫn bảo vệ Sprint Goal và chất lượng.

### 2.2. “Tam giác” phạm vi – thời gian – nguồn lực và điều kiện chất lượng

Một cách đơn giản để bắt đầu trao đổi là nhìn ba yếu tố:

1. **Phạm vi:** Bao nhiêu khả năng phải giao, mức phức tạp và phụ thuộc ra sao?
2. **Thời gian:** Khi nào cần kết quả? Mốc nào dự báo, mốc nào thực sự cố định?
3. **Năng lực/chi phí:** Có ai làm, có kỹ năng và thời gian không; ngân sách hạn chế đến đâu?

Khi một yếu tố thay đổi, ít nhất một phần kế hoạch cần được xem lại. **Chất lượng không nên là “van xả” mặc định** để giữ nguyên cả ba yếu tố kia. Bỏ kiểm thử hồi quy, xử lý lỗi dữ liệu hoặc kiểm soát truy cập có thể làm ngày giao trông đẹp hơn nhưng chuyển chi phí và rủi ro sang người dùng.

~~~text
Thêm phạm vi + Giữ ngày giao + Giữ năng lực
              |
              v
     Phải xem lại giả định, chia nhỏ và ưu tiên
     hoặc thương lượng thêm thời gian/năng lực.
     KHÔNG tự động: bỏ kiểm thử, hạ DoD, ép làm thêm giờ.
~~~

Không phải cứ tăng thêm một người thì tiến độ giảm đúng một phần tương ứng: onboarding, phối hợp và phụ thuộc kỹ thuật có thể khiến lợi ích đến chậm. Năng lực **không hoàn toàn thay thế cho nhau** giữa chuyên môn backend, bảo mật, kiểm thử và vận hành.

## 3. Nhận diện các loại thay đổi và câu hỏi cần hỏi

| Tín hiệu | Ví dụ | Điều cần xác minh | Phương án thường có |
| --- | --- | --- | --- |
| **Phạm vi tăng** | Bên liên quan yêu cầu thêm thông báo SMS và bộ lọc địa điểm. | Có gắn Product Goal? Điều gì bắt buộc? Chi phí trì hoãn? | Sắp lại backlog, chia lát cắt, thương lượng ngày hoặc hoãn mục ít giá trị. |
| **Phạm vi đổi bản chất** | Người dùng không cần bộ lọc mà cần xác nhận lịch rõ hơn. | Bằng chứng và độ đại diện có đủ? | Thay giải pháp, cập nhật user story và tiêu chí chấp nhận. |
| **Năng lực giảm** | Thành viên nghỉ đột xuất hoặc bị điều sang sự cố. | Mất kỹ năng gì, trong bao lâu, có việc đang dở? | Giảm phạm vi, chuyển giao tri thức, xử lý điểm nghẽn, cập nhật dự báo. |
| **Năng lực tăng** | Có thêm người tham gia hoặc công cụ tự động hóa. | Khả năng hòa nhập, phụ thuộc, lợi ích thực tế? | Bổ sung việc có thể làm độc lập, giữ giới hạn WIP, xem lại sau. |
| **Giả định kỹ thuật sai** | API không có chức năng retry an toàn như dự kiến. | Tài liệu, kết quả thử nghiệm, phương án thay thế? | Spike có giới hạn, đổi thiết kế, giảm hoặc hoãn phạm vi. |
| **Phụ thuộc trễ** | Đối tác không cấp quyền sandbox kịp. | Có thể thử độc lập phần nào? Khi nào có đầu vào? | Chuyển thứ tự việc, mock có kiểm soát, làm rõ rủi ro tích hợp. |
| **Sự cố/luật mới** | Lỗ hổng bảo mật hoặc hạn tuân thủ xuất hiện. | Mức độ khẩn cấp, phạm vi và thẩm quyền? | Kích hoạt ứng cứu hoặc ưu tiên nghĩa vụ, công khai ảnh hưởng tới kế hoạch khác. |
| **Chỉ số sản phẩm đổi** | Tỷ lệ hoàn tất luồng giảm sau khi giao một phần tính năng. | Có lỗi đo, thay đổi mẫu hay tác động thật? | Kiểm chứng, thử lát cắt sửa, xem lại ưu tiên giải pháp. |

Không phải thay đổi nào cũng cần lập lại toàn bộ roadmap. Nhóm nên xác định **tầm ảnh hưởng**: thay đổi kế hoạch ngày, Sprint, lần phát hành, hay chiến lược sản phẩm.

### 3.1. Trigger: khi nào bắt buộc xem lại kế hoạch?

Nhóm nên định nghĩa trước một số **tín hiệu kích hoạt xem lại**, ví dụ:

- Bằng chứng làm giả định cốt lõi trong thiết kế trở nên không còn đáng tin.
- Năng lực khả dụng giảm đủ để ảnh hưởng Sprint Goal hoặc mốc phụ thuộc.
- Một hạng mục bắt buộc tăng phạm vi hoặc có ngày hạn mới.
- Sự cố khiến hệ thống không còn đạt điều kiện an toàn/chất lượng.
- Chỉ số flow cho thấy công việc bị chặn liên tục hoặc dự báo không còn phù hợp.
- Phần mềm đã giao chứng minh một tính năng tiếp theo ít giá trị hơn dự kiến.

Trigger không phải quy tắc “cứ một ngày chậm là phải báo đổi ngày giao”. Một ngày biến động thông thường có thể nằm trong bất định của dự báo; điều quan trọng là **tác động thực chất** tới mục tiêu và khả năng giao.

## 4. Quy trình điều chỉnh kế hoạch có kiểm soát

~~~mermaid
flowchart TD
    A["Thay đổi hoặc bằng chứng mới"] --> B["Xác minh dữ kiện và mức khẩn cấp"]
    B --> C{"Có sự cố / nghĩa vụ cần hành động ngay?"}
    C -->|Có| D["Ứng cứu hoặc xử lý theo thẩm quyền"]
    C -->|Không| E["Đánh giá mục tiêu, phạm vi, năng lực, phụ thuộc"]
    D --> E
    E --> F["Tạo phương án và dự báo có giả định"]
    F --> G["Người có trách nhiệm chọn / thương lượng"]
    G --> H["Cập nhật backlog và kế hoạch, truyền đạt tác động"]
    H --> I["Giao lát cắt an toàn, đo và kiểm tra lại"]
    I --> B
~~~

### Bước 1 — Ghi nhận sự thay đổi mà không vội chọn giải pháp

Ghi rõ:

- **Điều gì mới?** Yêu cầu, dữ liệu, sự cố, rủi ro, thay đổi nhân sự hay phụ thuộc?
- **Nguồn:** Dữ liệu sản phẩm, người dùng, tài liệu đối tác, log kỹ thuật, chính sách?
- **Phần đã biết và chưa biết:** Quan sát cụ thể khác với suy luận như thế nào?
- **Mức khẩn cấp:** Có thiệt hại đang xảy ra hay ngày hạn bắt buộc không?
- **Quyết định bị ảnh hưởng:** Cần đổi phạm vi, phương án, thứ tự, mốc giao hay cả mục tiêu?

Ví dụ: “API gửi xác nhận mất trung bình 2,4 giây trong 30 phép đo ở sandbox” là quan sát có điều kiện; “production sẽ luôn mất hơn hai giây” là suy diễn chưa đủ bằng chứng. Không nên đổi toàn bộ roadmap chỉ dựa trên một phép thử chưa đại diện.

### Bước 2 — Khôi phục bức tranh kế hoạch hiện tại

Trước khi thay đổi, cần có **baseline**:

1. Mục tiêu hiện tại và kết quả cần chứng minh.
2. Những Product Backlog Item quan trọng, công việc dở dang và phụ thuộc.
3. Dự báo thời gian/năng lực còn lại cùng các giả định.
4. Tiêu chí chấp nhận, DoD hoặc yêu cầu chất lượng khác.
5. Các cam kết hợp đồng, mốc pháp lý, hạn triển khai đối tác.

Không có baseline, rất khó giải thích “đổi kế hoạch” đã đổi điều gì. Một ghi chú ngắn đủ để so sánh trước và sau, không cần tạo bản kế hoạch mới hàng chục trang.

### Bước 3 — Phân tích tác động trên ba trục

| Trục | Điều cần làm rõ |
| --- | --- |
| **Giá trị/phạm vi** | Những khả năng nào mất/được; khách hàng có thể nhận giá trị sớm bằng lát cắt nhỏ hơn không? |
| **Năng lực/dòng công việc** | Ai còn khả dụng; kỹ năng nào là nút thắt; WIP, công việc bị chặn và chuyển ngữ cảnh ra sao? |
| **Thời gian/rủi ro** | Dự báo mốc bàn giao thay đổi thế nào; có hạn bắt buộc, chi phí trì hoãn hoặc nguy cơ vận hành nào? |

Nếu giả định thay đổi, đánh giá **độ tin cậy của thông tin mới** và xem có cần khảo sát có giới hạn (*timeboxed spike*) hay không. Nếu mất năng lực, phân tích những mục phụ thuộc vào kỹ năng bị thiếu; đừng chỉ trừ một tỷ lệ phần trăm khỏi toàn bộ thời gian như thể mọi công việc có thể thay thế nhau.

### Bước 4 — Thiết kế các phương án chứ không chỉ công bố một ngày mới

Ít nhất nên thử so sánh các lựa chọn hợp lệ:

- **Giữ ngày, giảm phạm vi:** Giao một lát cắt dọc đủ tạo giá trị và đạt chất lượng; hoãn phần không thiết yếu.
- **Giữ phạm vi, đổi dự báo thời gian:** Khi chức năng đã cam kết quan trọng hơn mốc có thể thương lượng.
- **Giữ mục tiêu, thay giải pháp:** Bằng chứng cho thấy cách khác đơn giản và ít rủi ro hơn.
- **Tăng năng lực có mục tiêu:** Chỉ khi người bổ sung có kỹ năng, thời gian hòa nhập và khả năng làm việc độc lập phù hợp.
- **Tạm dừng để giảm rủi ro:** Spike ngắn hoặc ứng cứu sự cố khi tiếp tục triển khai có thể gây thiệt hại lớn.
- **Dừng/loại bỏ công việc:** Nếu giả định giá trị đã bị bác bỏ.

Điều nên tránh là “phương án duy nhất: mọi người cố gắng hơn”. Làm thêm giờ liên tục hoặc bỏ chất lượng không phải kế hoạch rủi ro thấp.

### Bước 5 — Chọn phương án với quyền quyết định rõ

Trong Scrum, **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog; **Developers** lập kế hoạch thực hiện Sprint, điều chỉnh Sprint Backlog, bảo đảm chất lượng và tạo Increment; **Scrum Master** giúp Scrum Team và tổ chức thực hành Scrum hiệu quả. Những ràng buộc an toàn, ngân sách, hợp đồng hoặc phát hành có thể thuộc các thẩm quyền khác trong tổ chức.

Người quyết định cần biết **đánh đổi và bằng chứng**, không chỉ nhận lời đề nghị “xin lùi hai tuần”. Nếu thay đổi ảnh hưởng cam kết với khách hàng, cần trao đổi và thương lượng đúng thẩm quyền. Một buổi thảo luận có nhiều người tham gia **không tự động chuyển quyền chốt** từ người chịu trách nhiệm sang người điều phối.

### Bước 6 — Cập nhật tài liệu làm việc và công khai phần bị đổi

Cập nhật **những nơi nhóm thực sự dùng để làm việc**:

- Product Backlog: thứ tự, phạm vi, mô tả, phụ thuộc và tiêu chí chấp nhận.
- Kế hoạch Sprint hoặc workflow Kanban: mục tiêu, WIP, công việc bị chặn, chính sách kéo việc.
- Roadmap/mốc phát hành: kết quả dự kiến, khoảng thời gian và mức chắc chắn.
- Bảng rủi ro/giả định: điều cần kiểm chứng, trách nhiệm, ngày xem lại.
- Quyết định với bên liên quan: ai chốt, phương án nào được chọn, phần nào hoãn và vì sao.

Không nên cập nhật chỉ một slide báo cáo rồi để các ticket và mục tiêu thực thi giữ nguyên. Đó là nguồn tạo hai “sự thật” khác nhau cho cùng một dự án.

### Bước 7 — Giao phần nhỏ, quan sát và điều chỉnh lần tiếp

Triển khai theo lát cắt đủ giá trị và an toàn; dùng kiểm thử tự động, CI, review, feature flag hoặc rollout có kiểm soát khi phù hợp. Sau đó kiểm tra **outcome**, lỗi, độ tin cậy và flow. Nếu dữ liệu mới lại phủ nhận giả định, kế hoạch tiếp tục được xem xét. Mục tiêu là **học và thích ứng nhanh hơn chi phí sai hướng**, không phải đạt một kế hoạch vĩnh viễn chính xác.

## 5. Điều chỉnh khi **phạm vi** thay đổi

Thay đổi phạm vi có thể là **bổ sung yêu cầu**, **đổi hành vi mong muốn**, **bỏ một khả năng không còn giá trị**, hoặc **làm rõ trường hợp biên vốn đã cần để đạt chất lượng**. Các trường hợp này khác nhau về nghĩa vụ và cách xử lý.

### 5.1. Phân loại trước khi nhận hoặc từ chối

| Loại thay đổi | Ví dụ | Cách xử lý phù hợp |
| --- | --- | --- |
| Tính năng mới không gắn với mục tiêu gần | Thêm giao diện chọn màu lịch. | Ghi nhận giá trị, đưa vào Product Backlog để sắp thứ tự; không tự động chen vào Sprint đang chạy. |
| Điều kiện bắt buộc để hành vi đúng | Không cho hai khách cùng chiếm một khung giờ. | Xử lý như điều kiện tính đúng đắn; điều chỉnh kế hoạch nhưng không hạ chất lượng. |
| Phản hồi người dùng làm đổi giả định | Người dùng cần trạng thái xác nhận rõ thay vì bộ lọc. | Kiểm tra bằng chứng, đổi thứ tự hoặc giải pháp và cập nhật tiêu chí chấp nhận. |
| Nghĩa vụ mới | API đối tác sẽ ngừng phiên bản cũ trong một tháng. | Xác minh ngày hạn, phụ thuộc, nguồn lực; sắp kế hoạch trước hạn. |
| Yêu cầu chưa đủ bằng chứng | “Cần AI để hiện đại hơn.” | Làm rõ nhu cầu, giả thuyết và khảo sát giới hạn nếu chi phí đầu tư lớn. |

### 5.2. Dùng chia lát cắt dọc để giữ mục tiêu

Giả sử kế hoạch ban đầu gồm “đặt lịch, tự đổi lịch, thông báo email, thông báo SMS, lọc nhiều địa điểm”. Nếu phạm vi cần giảm để kịp mốc có ý nghĩa, nhóm có thể ưu tiên **đặt lịch hợp lệ và xác nhận trên màn hình**, rồi phát triển tự đổi lịch và thông báo mở rộng sau. Đây là lựa chọn theo **giá trị và phụ thuộc**, không phải chia phần bằng cách xây toàn bộ database Sprint này, toàn bộ API Sprint sau và UI ở cuối rồi gọi mỗi lần là một bản giao người dùng sử dụng được.

Một user story có thể diễn đạt:

> “Là khách cần tư vấn, tôi muốn chọn một khung giờ đang trống và nhận xác nhận đặt lịch, để biết yêu cầu của mình đã được ghi nhận.”

Tiêu chí chấp nhận phải rõ với giờ hết chỗ, mạng chậm, yêu cầu gửi lặp và dữ liệu cá nhân cần bảo vệ. **Giảm phạm vi không có nghĩa giảm những điều kiện tối thiểu để chức năng đã chọn hoạt động an toàn.**

### 5.3. Không áp dụng “phạm vi cố định” với mọi thứ

Một hạn tuân thủ có thể bắt buộc một số chức năng; một chương trình thử nghiệm thị trường có thể linh hoạt nhiều hơn với phạm vi. Hãy đánh dấu điều **bắt buộc**, **nên có** và **có thể hoãn** trong ngữ cảnh mục tiêu cụ thể. Có thể dùng MoSCoW để thảo luận, nhưng nếu mọi yêu cầu đều được gọi “Must have”, công cụ không giúp phân biệt.

### 5.4. Đối phó với hiện tượng mở rộng phạm vi âm thầm

Một yêu cầu mới có thể “chỉ thêm nút này” nhưng đòi sửa API, dữ liệu, quyền truy cập và kiểm thử. Để ngăn **scope creep**, nhóm cần:

1. Làm rõ vấn đề và tiêu chí chấp nhận trước khi ước lượng.
2. Kiểm tra phụ thuộc và rủi ro, gồm triển khai/vận hành.
3. Chọn phương án: thay thế một mục khác, hoãn yêu cầu, đổi thời gian hoặc cấp năng lực thật sự.
4. Cập nhật backlog và thông báo rõ lựa chọn.

Không cần thành lập hội đồng xét thay đổi cho mọi chỉnh sửa nhỏ. Mục đích là **tránh để việc mới tăng mà kế hoạch cũ giả vờ không bị ảnh hưởng**.

## 6. Điều chỉnh khi **nguồn lực hoặc năng lực** thay đổi

Nói “nhóm thiếu một người” mới chỉ là tín hiệu. Muốn lập lại kế hoạch, cần biết **năng lực nào bị mất**, thời lượng, công việc đang bị chặn và điều có thể làm thay.

### 6.1. Phân biệt số người và năng lực có thể dùng

Năng lực thực tế chịu ảnh hưởng bởi:

- Ngày làm việc, nghỉ phép, hỗ trợ khách hàng và trực vận hành.
- Kỹ năng/tri thức chuyên môn: người biết hệ thống tích hợp đối tác có thể là điểm nghẽn riêng.
- Review, kiểm thử, deploy và thời gian chờ quyết định.
- WIP và chi phí chuyển ngữ cảnh giữa nhiều hạng mục.
- Khả năng sẵn sàng của môi trường, dữ liệu thử, quyền truy cập, nhà cung cấp.
- Onboarding và phối hợp khi có người mới.

Nếu một người có kiến thức duy nhất về API nghỉ đột xuất, kế hoạch có thể cần **chuyển công việc liên quan sang sau**, **pair programming để chia sẻ tri thức** hoặc **giảm phụ thuộc**. Không thể kết luận chỉ cần thêm 20% thời gian cho mọi task.

### 6.2. Bài toán năng lực minh họa

Giả sử Scrum Team có **4 Developers** trong một Sprint 10 ngày làm việc, tổng thời gian lịch lý thuyết là **40 người-ngày**. Sau khi xét hoạt động phối hợp, hỗ trợ thường xuyên và thời gian nghỉ đã biết, nhóm dự báo **32 người-ngày** có thể phân bổ cho những việc dự kiến; các con số chỉ nhằm minh họa, không là tiêu chuẩn.

| Hạng mục dự kiến | Công sức tương đối minh họa |
| --- | ---: |
| Sửa luồng xác nhận và kiểm thử hồi quy | 8 người-ngày |
| Tính năng chọn giờ trống | 10 người-ngày |
| Spike API xác nhận đối tác | 4 người-ngày |
| Cải thiện log và cảnh báo đặt lịch | 4 người-ngày |
| Dự phòng cho bất định đã biết trong phạm vi dự báo | 6 người-ngày |
| **Tổng dự báo** | **32 người-ngày** |

Giữa Sprint, một Developer phải dành bốn ngày hỗ trợ sự cố, làm năng lực dành cho công việc dự kiến giảm **4 người-ngày**, còn khoảng **28 người-ngày** theo mô hình minh họa. Nếu sự cố làm đứt quãng cả nhóm, tác động thực tế có thể **lớn hơn bốn** vì thời gian phối hợp và chuyển ngữ cảnh.

**Ba lựa chọn cần thảo luận:**

1. **Giảm phạm vi:** Hoãn một phần cải thiện log chưa bắt buộc hoặc chia tính năng chọn giờ thành lát cắt nhỏ hơn, vẫn giữ các điều kiện chất lượng thiết yếu.
2. **Đổi thứ tự:** Ưu tiên công việc không phụ thuộc Developer bị điều đi; giữ mục tiêu khả thi.
3. **Đổi dự báo:** Nếu phần còn lại bắt buộc, minh bạch nguy cơ không hoàn tất trong Sprint và thương lượng phạm vi với Product Owner.

Không tự động chọn “tất cả làm thêm một ngày” để bù vào con số. **Người-ngày là mô hình công sức**, không bảo đảm công việc có thể chia đều hoặc kết thúc trước ngày cố định.

### 6.3. Khi bổ sung người chưa chắc giải ngay điểm nghẽn

Một người mới cần quyền truy cập, hiểu kiến trúc và thời gian onboarding. Nếu công việc đã sát ngày giao, việc bổ sung người có thể làm tăng nhu cầu review và hỗ trợ trong ngắn hạn. Hỏi:

- Có hạng mục nào **độc lập, rõ ràng và ít phụ thuộc** để người mới nhận?
- Ai chịu trách nhiệm hướng dẫn và review?
- Khi nào hiệu quả thực sự bắt đầu tăng?
- Liệu hỗ trợ tự động hóa hoặc tháo phụ thuộc có tác động lớn hơn thêm người?

Giải pháp bền vững bao gồm chia sẻ tri thức, pair programming, kiểm thử tự động và giảm điểm nghẽn, không chỉ thay đổi số lượng thành viên.

## 7. Điều chỉnh khi **giả định** hoặc phụ thuộc thay đổi

Kế hoạch Agile là quá trình liên tục xác minh giả định. Một thay đổi về giả định có thể **đáng kể hơn** thay đổi phạm vi nhỏ vì nó làm sai cơ sở chọn giải pháp.

### 7.1. Bắt đầu bằng danh sách giả định có tác động

| Giả định | Bằng chứng hiện tại | Rủi ro nếu sai | Cách kiểm tra |
| --- | --- | --- | --- |
| Người dùng muốn tự đổi lịch hơn là gọi tổng đài. | Phản hồi từ bộ phận hỗ trợ, chưa có khảo sát hành vi. | Xây chức năng ít dùng. | Phỏng vấn theo tác vụ thật, đo yêu cầu đổi lịch và thử bản mẫu. |
| API đối tác hỗ trợ khóa chống yêu cầu lặp. | Đọc tài liệu, chưa kiểm tra timeout. | Lịch trùng hoặc kết quả không xác định. | Spike có timebox thử retry, timeout và yêu cầu đồng thời. |
| Thời gian review trung bình dưới một ngày. | Dữ liệu từ chu kỳ trước, chưa tính nhân sự nghỉ. | Tắc luồng, trễ tích hợp. | Xem WIP và cycle time theo trạng thái trong các tuần gần. |
| Môi trường sandbox có hành vi tương tự production. | Chưa được đối tác xác nhận. | Lỗi chỉ xuất hiện sau phát hành. | Xác minh hợp đồng, thử điều kiện có thể mô phỏng, rollout có giám sát. |

Khi một giả định bị bác bỏ, hãy xác định **quyết định nào phụ thuộc vào nó**. Không cần khảo sát mọi bất định trước khi phát triển. Ưu tiên những giả định **chưa chắc và nếu sai sẽ gây hậu quả lớn**.

### 7.2. Spike có giới hạn để ra quyết định, không phải nghiên cứu vô hạn

Ví dụ một spike:

~~~yaml
name: "Kiểm chứng API chống đặt lịch trùng"
decision_blocked: "Chọn thiết kế retry khi timeout"
assumption: "API đối tác hỗ trợ idempotency key"
question: "Cùng một yêu cầu gửi lại có tạo lịch thứ hai không?"
timebox: "Tối đa 1 ngày làm việc với 2 người, xem kết quả cuối ngày"
in_scope:
  - "Đọc hợp đồng API và xác nhận phiên bản sandbox"
  - "Thử gửi lặp tuần tự, đồng thời và timeout"
out_of_scope:
  - "Xây toàn bộ hệ thống đặt lịch production"
  - "Kiểm thử tải quy mô lớn"
stop_when: "Đủ cơ sở chọn phương án hoặc hết timebox"
deliverable: "Bằng chứng, giới hạn thử nghiệm, rủi ro còn lại, quyết định backlog"
~~~

Ví dụ timebox trên là giả định để học. Khi hết timebox, nhóm có thể chọn phương án có kiểm soát, thực hiện khảo sát bổ sung được phê duyệt hoặc thay đổi kế hoạch. **Không bảo đảm tìm ra câu trả lời trong timebox** và không coi mã prototype chưa đạt chuẩn là Increment có thể phát hành.

### 7.3. Phụ thuộc bị trễ: thay thứ tự thay vì đứng chờ

Nếu nhà cung cấp chưa cấp API key, nhóm có thể:

- Làm rõ hợp đồng API và tiêu chí chấp nhận nghiệp vụ.
- Viết kiểm thử hợp đồng và dùng mock phù hợp để làm rõ giao diện tích hợp.
- Triển khai lát cắt độc lập không phụ thuộc môi trường đối tác.
- Xác định rủi ro mà mock **không thể chứng minh**, đặc biệt hành vi production, quota và lỗi mạng.
- Đặt mốc cần quyền truy cập thật trước khi công bố tính năng sẵn sàng.

Mock giúp tiến triển nhưng không thay thế kiểm thử tích hợp thật. Đưa phụ thuộc và tình trạng bị chặn lên bảng công việc để không che sự chậm trễ.

## 8. Bản kế hoạch minh họa trước và sau khi thông tin đổi

Giả sử nhóm phát triển ứng dụng đặt lịch tư vấn và có mục tiêu: **khách đặt lịch hợp lệ trên điện thoại, nhận được trạng thái rõ và tránh lịch trùng**. Kế hoạch ban đầu hướng tới lần phát hành giới hạn sau **ba Sprint**, mỗi Sprint hai tuần.

### 8.1. Baseline trước khi thay đổi

| Giai đoạn | Dự kiến kết quả | Giả định nền |
| --- | --- | --- |
| Sprint 1 | Khách xem giờ trống, gửi yêu cầu và nhận xác nhận trên màn hình. | API hỗ trợ tạo lịch và giữ nhất quán. |
| Sprint 2 | Đổi/hủy lịch cơ bản, thông báo email, kiểm thử hồi quy mở rộng. | Đối tác cho thay đổi lịch qua API. |
| Sprint 3 | Lọc địa điểm, thông báo SMS, rollout rộng hơn. | Có đủ năng lực kiểm thử/vận hành và luồng cơ bản ổn định. |

Đây là **kế hoạch minh họa**, không phải cam kết rằng mọi Sprint nhất thiết phải hoàn thành danh sách trên.

### 8.2. Ba thông tin mới xuất hiện

1. **Thay đổi giả định:** API đối tác không hỗ trợ sửa lịch trực tiếp như dự kiến; việc đổi lịch phải hủy và tạo mới với rủi ro cạnh tranh.
2. **Năng lực giảm:** Người phụ trách tích hợp có bốn ngày hỗ trợ sự cố.
3. **Thay đổi phạm vi theo phản hồi:** Người dùng thử luồng đặt lịch chưa hiểu trạng thái khi mạng chậm; yêu cầu làm rõ xác nhận trở nên quan trọng hơn SMS.

Nhóm lập bảng tác động:

| Hạng mục | Kết quả khi đánh giá lại | Quyết định minh họa |
| --- | --- | --- |
| Đặt lịch và chống trùng khi retry | Ảnh hưởng trực tiếp tính đúng đắn, có rủi ro cao. | Ưu tiên kiểm thử và thiết kế phương án an toàn trước rollout. |
| Trạng thái xác nhận khi mạng chậm | Phản hồi trực tiếp về khả năng hoàn tất tác vụ. | Chia thành một lát cắt nhỏ để thử ở vòng gần. |
| Đổi/hủy lịch | Giải pháp ban đầu không khả thi như dự báo. | Spike ngắn + xem lại phạm vi; không cam kết nguyên phương án cũ. |
| Email xác nhận | Có ích nhưng phải không làm chậm khả năng xác nhận đúng. | Giữ trong backlog, chọn thời điểm phù hợp. |
| SMS và bộ lọc nhiều địa điểm | Chưa cấp bách so với lỗi và bất định cốt lõi. | Hoãn để bảo vệ mục tiêu và năng lực. |

### 8.3. Kế hoạch điều chỉnh theo giá trị và mức tin cậy

| Khoảng thời gian | Mục tiêu/lát cắt tiếp theo | Điều kiện để tiến tiếp |
| --- | --- | --- |
| Vòng gần nhất | Chống đặt trùng, hiển thị trạng thái rõ; đo kết quả trên nhóm thử. | Kiểm thử hồi quy, xử lý timeout, không vi phạm điều kiện chất lượng. |
| Vòng kế tiếp | Thử phương án đổi/hủy lịch sau kết quả spike. | Có bằng chứng tích hợp thật, đánh giá rủi ro và khả năng khôi phục. |
| Sau khi luồng ổn định | Mở rộng email/SMS hoặc bộ lọc theo thứ tự giá trị mới. | Tỷ lệ đặt lịch hợp lệ, tải hỗ trợ và độ ổn định đạt mức chấp nhận. |

Nhóm **không gọi vòng gần nhất là “Sprint 1 mới phải làm toàn bộ những việc này” nếu năng lực không đủ**. Scrum Team phải chọn Sprint Goal khả thi theo bối cảnh thực tế; Developers lập kế hoạch để đạt mục tiêu và làm rõ phạm vi khi học thêm.

### 8.4. Đánh giá tác động bằng số liệu, không dựa vào cảm giác

Giả sử trong một vòng kiểm chứng giới hạn, nhóm ghi nhận số liệu **giả định**:

| Tín hiệu | Trước thay đổi | Sau khi thử cải tiến |
| --- | ---: | ---: |
| Tỷ lệ lượt bắt đầu đặt lịch hợp lệ hoàn tất | 46% | 55% |
| Tỷ lệ yêu cầu tạo lịch bị lỗi | 2,1% | 1,2% |
| Thời gian chờ review trung vị | 1,5 ngày | 0,8 ngày |

Những con số này chỉ minh họa, **không phải số liệu thực** và không tự chứng minh cải tiến là nguyên nhân: mẫu người dùng, cách đo, lượng truy cập và thời gian thử có thể khác nhau. Nếu cần kết luận nhân quả về kết quả sản phẩm, nhóm nên cân nhắc thiết kế thử nghiệm đối chứng phù hợp. Chỉ số lỗi và chất lượng là điều kiện bảo vệ, không được bỏ qua dù tỷ lệ hoàn tất tăng.

**Bài học:** Kế hoạch đổi theo ba hướng cùng lúc, nhưng Product Goal vẫn rõ. Phần ít giá trị được hoãn, giả định sai được khảo sát trong giới hạn và năng lực mất đi được phản ánh trong dự báo thay vì che giấu.

## 9. Dự báo có mức bất định: tránh hứa hẹn chính xác giả

Một kế hoạch có thể minh bạch mà không khẳng định “chắc chắn hoàn tất ngày 14”. Hãy mô tả **căn cứ, khoảng dự báo, điều kiện và mức độ tin cậy** tương xứng với dữ liệu.

### 9.1. Phân biệt ước lượng công sức, thời gian lịch và throughput

- **Effort (công sức):** Lượng công việc người hoặc nhóm cần bỏ ra; thường được ước lượng tương đối hoặc bằng người-ngày.
- **Elapsed time (thời gian lịch):** Khoảng thời gian từ bắt đầu tới hoàn tất, bao gồm chờ review, đối tác và quyết định.
- **Throughput:** Số mục hoàn tất mỗi khoảng thời gian theo định nghĩa nhất quán.
- **Cycle time:** Thời gian một mục đã bắt đầu đến khi hoàn tất trong workflow định nghĩa.
- **Lead time:** Thời gian từ một mốc yêu cầu được tiếp nhận đến khi hoàn tất; cần thống nhất mốc đo.
- **WIP:** Số mục đã bắt đầu nhưng chưa hoàn tất.

Tổng effort 20 người-ngày **không có nghĩa** chắc chắn hoàn thành trong năm ngày với bốn người. Phụ thuộc và giới hạn WIP quyết định khả năng chạy song song thực tế.

### 9.2. Ví dụ dự báo theo throughput

Giả sử một nhóm có lịch sử hoàn tất **4, 5, 3, 5, 4** backlog item mỗi tuần trong năm tuần gần đây, với cách chia kích thước tương đối nhất quán. Mức hoàn tất quan sát dao động từ **3 tới 5 mục/tuần**. Nếu còn **12 mục tương tự**, dự báo thô có thể cho thấy cần khoảng **3–4 tuần** trong điều kiện gần giống lịch sử.

Đây **không phải khoảng tin cậy thống kê** và không phải lời hứa. Khi thay đổi loại công việc, kích thước mục, năng lực, WIP hoặc phụ thuộc, lịch sử trên có thể không còn đại diện. Với đủ dữ liệu phù hợp, mô phỏng Monte Carlo dựa trên throughput hoặc cycle time có thể tạo dự báo xác suất; cần công bố giả định và không diễn giải con số xác suất như một bảo đảm.

### 9.3. Cách nói dự báo có trách nhiệm

**Chưa tốt:** “Chúng tôi cam kết 12 story này chắc chắn xong vào cuối tháng, dù hiện tại chưa có môi trường tích hợp.”

**Tốt hơn:** “Với cách chia việc và năng lực hiện tại, chúng tôi dự báo khoảng 3–4 tuần cho 12 mục tương tự các tuần trước. Dự báo chưa tính nguy cơ API đối tác trễ; chúng tôi sẽ kiểm tra lại sau khi có quyền tích hợp vào thứ Tư và báo ngay ảnh hưởng nếu giả định không còn đúng.”

Đối với ngày hạn hợp đồng hoặc pháp lý, tổ chức vẫn cần **quản lý cam kết** và kế hoạch giảm rủi ro chủ động. Minh bạch bất định không có nghĩa được đơn phương bỏ nghĩa vụ.

## 10. Scrum: điều chỉnh kế hoạch nhưng không làm mất mục tiêu Sprint

Scrum hỗ trợ thích ứng bằng các Sprint có giới hạn thời gian, Product Goal, Sprint Goal, Product Backlog và kiểm tra thường xuyên.

### 10.1. Trước Sprint

- **Product Backlog refinement:** Làm rõ mục, chia story, kiểm tra phụ thuộc, đánh giá thay đổi về giá trị và rủi ro.
- **Sprint Planning:** Scrum Team xác định Sprint Goal; Developers lập kế hoạch các mục và cách thực hiện dựa trên thông tin, năng lực hiện tại.
- **Chia nhỏ việc:** Ưu tiên các lát cắt có hành vi kiểm chứng được, thay vì tạo một “story lớn phải làm hết” không thể điều chỉnh.

### 10.2. Trong Sprint khi thông tin đổi

Theo Scrum Guide 2020, trong Sprint:

1. **Không thực hiện thay đổi gây nguy hiểm cho Sprint Goal**.
2. **Chất lượng không được suy giảm**.
3. Product Backlog được làm rõ khi cần.
4. Phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi nhóm học thêm.

Developers thường xuyên kiểm tra tiến độ tới Sprint Goal và điều chỉnh Sprint Backlog. Nếu một story phức tạp hơn dự báo, họ có thể thương lượng lại phạm vi để giữ mục tiêu, thay đổi thứ tự công việc hoặc tìm phương án kỹ thuật phù hợp.

**Không nên hiểu:** “Mỗi Sprint là hợp đồng bắt buộc giao đủ mọi story đã chọn”. Đồng thời cũng không nên hiểu Scrum cho phép Product Owner liên tục chen yêu cầu làm mục tiêu Sprint thất bại.

### 10.3. Khi Sprint Goal thực sự lỗi thời

Theo Scrum Guide, **chỉ Product Owner có thẩm quyền hủy Sprint** nếu Sprint Goal trở nên lỗi thời. Đây là tình huống đặc biệt, không phải phản xạ trước mọi yêu cầu mới. Với thay đổi thông thường, nhóm cần trao đổi, thương lượng phạm vi và tiếp tục tập trung vào mục tiêu có giá trị.

### 10.4. Sau Sprint

Trong **Sprint Review**, Scrum Team và các bên liên quan xem Increment, tiến độ tới Product Goal và những thay đổi từ bối cảnh để điều chỉnh hướng sản phẩm. Trong **Sprint Retrospective**, nhóm xem cách làm có thể cải tiến: dự báo sai vì sao, WIP và điểm chờ ở đâu, kiểm thử hoặc phối hợp nào cần cải thiện.

Review không chỉ là báo cáo “đã đóng bao nhiêu ticket”. Retrospective cũng không phải buổi tìm người đã ước lượng sai để quy trách nhiệm.

## 11. Kanban: điều chỉnh thứ tự mà giữ dòng công việc thông suốt

Kanban có ích khi nhóm xử lý dòng việc liên tục: feature nhỏ, lỗi, hỗ trợ vận hành, khám phá và công việc cải tiến. Việc **trực quan hóa, giới hạn WIP và công khai chính sách** làm rõ giá của việc đổi ưu tiên.

~~~text
Ý tưởng / yêu cầu -> Sẵn sàng -> Đang làm [WIP: 3] -> Review [WIP: 2] -> Xong
                                          |                  |
                                     Bị chặn?           Đang đầy?
~~~

Giới hạn WIP trong ví dụ chỉ minh họa. Khi một yêu cầu mới xuất hiện:

1. Kiểm tra mức khẩn cấp và chính sách tiếp nhận.
2. Xem WIP hiện tại, mục gần hoàn tất và hàng đợi review.
3. Nếu không khẩn cấp, sắp lại thứ tự đầu vào và **kéo** việc khi có năng lực.
4. Nếu khẩn cấp thực sự, dùng chính sách expedite hoặc ứng cứu, công khai việc nào bị gián đoạn.
5. Đo lại cycle time, throughput, thời gian bị chặn và tỷ lệ việc ngoài kế hoạch.

**Bắt đầu nhiều việc không đồng nghĩa hoàn thành nhanh hơn.** Khi mất một thành viên, hạ WIP để tập trung hoàn tất phần có giá trị có thể tốt hơn vẫn giữ cùng số cột “Đang làm” như trước.

Một số nhóm dùng **classes of service** (khẩn cấp, ngày hạn cố định, tiêu chuẩn) để xử lý loại việc có yêu cầu khác nhau. Đây là chính sách có thể thiết kế, không phải danh sách bắt buộc của Agile. Nếu mọi việc đều được gắn khẩn cấp, chính sách mất tác dụng.

## 12. XP và năng lực kỹ thuật giúp kế hoạch thay đổi an toàn

Khi sửa phạm vi hoặc giải pháp, **chi phí kỹ thuật của việc đổi hướng** phụ thuộc vào chất lượng mã, kiểm thử và thiết kế. Các thực hành **Extreme Programming (XP)** có thể hỗ trợ:

| Thực hành | Lợi ích khi kế hoạch thay đổi |
| --- | --- |
| **Test-driven development (TDD)** | Thể hiện hành vi kỳ vọng bằng kiểm thử; phát hiện lỗi hồi quy khi yêu cầu đổi. |
| **Continuous integration (CI)** | Tích hợp thường xuyên, thấy sớm lỗi liên quan và tránh đợi đến mốc phát hành. |
| **Refactoring** | Giữ cấu trúc mã dễ sửa khi hiểu biết mới xuất hiện, không thay đổi hành vi quan sát được. |
| **Pair programming** | Chia sẻ tri thức, giảm phụ thuộc vào một cá nhân khi năng lực thay đổi. |
| **Thiết kế đơn giản** | Tránh đầu tư lớn vào những tính năng tương lai chưa có bằng chứng. |
| **Bước tiến nhỏ** | Giảm kích thước thay đổi và chi phí phục hồi, thuận tiện cho phát hành giới hạn. |

**Ví dụ:** Nếu cần đổi cơ chế chống lịch trùng từ phía giao diện sang kiểm soát giao dịch phía server, hệ thống có kiểm thử tình huống gửi lặp và cạnh tranh đồng thời giúp nhóm sửa an toàn hơn. Nếu logic phân tán nhiều nơi và không có kiểm thử, replan chỉ trên giấy không đủ để đổi hướng nhanh.

Đừng dùng áp lực thời hạn mới làm lý do bỏ CI hoặc Definition of Done. Chất lượng kỹ thuật là **điều kiện để kế hoạch còn có thể thích ứng trong những vòng sau**.

## 13. Truyền đạt thay đổi kế hoạch mà không gây hiểu lầm

Thông báo “tính năng trễ vì bận” thường chưa đủ để bên liên quan ra quyết định. Một bản cập nhật tốt cần chỉ ra **điều mới, tác động, lựa chọn, quyết định và thời điểm xem lại**.

### 13.1. Mẫu cập nhật ngắn cho bên liên quan

~~~text
Mục tiêu hiện tại : Cho khách đặt lịch hợp lệ và có xác nhận tin cậy.
Kế hoạch trước    : Rollout giới hạn sau Sprint 2 gồm đặt/đổi lịch và email.
Thông tin mới     : API không hỗ trợ đổi lịch trực tiếp; 1 Developer hỗ trợ
                    sự cố 4 ngày; thử nghiệm cho thấy bước xác nhận khó hiểu.
Tác động          : Phương án đổi lịch và dự báo năng lực hiện tại không còn phù hợp.
Phương án A       : Giữ lần rollout giới hạn, chỉ giao đặt lịch an toàn; hoãn đổi lịch.
Phương án B       : Giữ phạm vi đổi lịch, điều chỉnh mốc theo kết quả spike.
Chất lượng giữ    : Không tạo lịch trùng, kiểm thử hồi quy, bảo mật dữ liệu.
Quyết định        : Ưu tiên A; Product Owner xác nhận thứ tự backlog,
                    người có thẩm quyền phát hành xác nhận điều kiện rollout.
Việc bị hoãn      : Đổi lịch nâng cao, SMS, bộ lọc địa điểm.
Tín hiệu xem lại  : Kết quả spike API, tỷ lệ đặt thành công và lỗi sau rollout.
Thời điểm cập nhật: Sau khi có kết quả thử nghiệm tích hợp đã hẹn.
~~~

Mẫu trên chỉ là ví dụ, không quy định tất cả nhóm phải tạo cùng biểu mẫu. Điều quan trọng là để người đọc **phân biệt thông tin đã xác minh, giả định còn mở và quyết định đã được phê duyệt**.

### 13.2. Nói rõ trạng thái của ngày dự kiến

Các từ nên dùng nhất quán:

- **Mốc bắt buộc:** Có cơ sở hợp đồng, pháp lý hoặc phụ thuộc không thể bỏ qua.
- **Mốc mục tiêu:** Nhóm đang cố gắng đạt và theo dõi rủi ro.
- **Dự báo:** Ước lượng thời điểm dựa trên dữ liệu, điều kiện và mức bất định.
- **Mốc kiểm tra:** Ngày xem lại bằng chứng để quyết định bước tiếp theo.

Tránh gắn nhãn “cam kết” cho mọi dự báo; cũng tránh dùng “chỉ là dự báo” để né trách nhiệm đã hứa với khách hàng.

### 13.3. Ghi lịch sử quyết định vừa đủ

~~~text
ID quyết định     : PLAN-12
Ngày ghi          : ...
Người quyết định  : ...
Thông tin mới     : ...
Giả định bị ảnh hưởng: ...
Phương án đã cân nhắc: ...
Phương án được chọn : ...
Lý do / rủi ro   : ...
Backlog thay đổi  : ...
Cam kết bị ảnh hưởng: ...
Người cần thông báo: ...
Tín hiệu và ngày xem lại: ...
~~~

Một decision log ngắn giúp nhóm tránh tranh luận lại từ đầu khi có người mới tham gia hoặc khi dữ liệu tiếp tục thay đổi. Không cần ghi lại mọi quyết định rất nhỏ như một thủ tục nặng nề.

## 14. Đo chất lượng của việc lập lại kế hoạch

Đừng dùng **số lần đổi kế hoạch** làm thước đo “mức độ Agile”. Một nhóm đổi liên tục có thể thiếu định hướng; một nhóm ít đổi có thể do giả định của họ còn phù hợp hoặc vì họ không thu nhận phản hồi.

| Góc nhìn | Tín hiệu có ích | Điều không nên suy ra |
| --- | --- | --- |
| **Kết quả sản phẩm** | Tỷ lệ hoàn tất tác vụ, mức sử dụng, giảm vấn đề người dùng, phản hồi định tính. | Giao đủ chức năng theo lịch không chứng minh tạo giá trị. |
| **Chất lượng/độ ổn định** | Lỗi nghiêm trọng, lỗi hồi quy, độ trễ, sự cố, thời gian phục hồi. | Số bug ít có thể do ghi nhận kém. |
| **Dòng công việc** | WIP, lead time, cycle time, throughput, thời gian bị chặn. | Số mục hoàn tất không đo trực tiếp độ phức tạp hay năng suất cá nhân. |
| **Độ tin cậy của dự báo** | Dự báo so với kết quả, mức lệch và các giả định gây lệch. | Một lần sai dự báo không chứng minh nhóm lập kế hoạch kém. |
| **Khả năng học hỏi** | Giả định được xác minh/bác bỏ, backlog thay đổi có lý do, thời gian tới phản hồi. | Số cuộc họp hoặc số spike không tự chứng minh học hỏi có ích. |
| **Năng lực bền vững** | Tỷ lệ việc khẩn, WIP và nút thắt kéo dài, thời gian hỗ trợ ngoài kế hoạch. | Có thể đạt throughput cao ngắn hạn nhưng tích lũy nợ kỹ thuật. |

### 14.1. Hỏi “dự báo sai vì sao?” thay vì “ai ước lượng sai?”

Có thể phân loại các nguyên nhân:

- Giả định về nhu cầu không đúng.
- Rủi ro kỹ thuật/chất lượng chưa thấy.
- Năng lực bị sự cố chiếm dụng hoặc kỹ năng bị giới hạn.
- Phụ thuộc, quyết định ngoài nhóm trễ.
- Mục quá lớn, WIP cao, chờ review hoặc kiểm thử.
- Thay đổi ưu tiên do thông tin có giá trị mới.

Mỗi nguyên nhân cần một hành động khác: discovery sớm, kiểm thử, giảm WIP, tháo phụ thuộc hoặc cải thiện cách truyền đạt. Gộp tất cả thành “ước lượng kém” sẽ không giúp đội ngũ tiến bộ.

### 14.2. DORA và chỉ số outcome

Các nghiên cứu và hướng dẫn của **DORA** giúp xem khả năng giao thay đổi phần mềm và độ ổn định vận hành. Chúng bổ sung cho chỉ số **outcome** sản phẩm, không thay thế nó. Nếu nhóm đưa code lên production nhanh hơn nhưng người dùng vẫn không hoàn tất đặt lịch, kế hoạch cần đánh giá lại lựa chọn giá trị chứ không chỉ tăng tốc triển khai.

**Velocity/story point**, nếu được dùng để hỗ trợ dự báo nội bộ, không phải chỉ số giá trị người dùng hoặc căn cứ so sánh năng suất giữa các nhóm. Khi phạm vi thay đổi, so sánh số point không giải thích đầy đủ tác động.

## 15. Những lỗi thường gặp khi điều chỉnh kế hoạch

| Ngộ nhận hoặc hành vi | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| “Agile không cần kế hoạch, cứ làm cái mới nhất.” | Thiếu mục tiêu, ưu tiên đảo liên tục, công việc dở dang tăng. | Duy trì mục tiêu và Product Backlog có thứ tự; thay đổi dựa trên bằng chứng. |
| “Kế hoạch đã chốt thì không được sửa.” | Tiếp tục xây tính năng ít giá trị hoặc giải pháp không còn đúng. | Xem kế hoạch là dự báo, công khai điều kiện cần điều chỉnh. |
| “Thêm một story nhỏ không ảnh hưởng gì.” | Scope creep âm thầm, WIP tăng và lịch không đáng tin. | Làm rõ tác động và việc bị thay thế hoặc hoãn. |
| “Mất 25% nhân sự thì mọi mục đều trễ đúng 25%.” | Bỏ qua kỹ năng, phụ thuộc và năng lực không thể thay thế. | Xem bottleneck, khả năng song song, bàn giao tri thức và WIP. |
| “Cứ thêm người là chắc chắn kịp.” | Onboarding và review tăng, lợi ích ngắn hạn không như dự kiến. | Chọn hạng mục độc lập; hỗ trợ chia sẻ tri thức, kiểm chứng tác động. |
| “Để giữ ngày giao, bỏ vài kiểm thử.” | Lỗi production và nợ kỹ thuật tăng, giảm khả năng đổi tiếp. | Giảm phạm vi hoặc thương lượng thời gian; giữ DoD và chuẩn bắt buộc. |
| “Kế hoạch mới chỉ cần đổi ngày trên slide.” | Backlog và kế hoạch triển khai tiếp tục mâu thuẫn. | Đồng bộ mục tiêu, backlog, phụ thuộc, forecast và thông tin bên liên quan. |
| “Bất kỳ biến động nào cũng phải tái lập toàn bộ roadmap.” | Tốn công, gây hoang mang và giảm sự tập trung. | Đánh giá phạm vi tác động, thay đổi đúng tầng kế hoạch cần thiết. |
| “Một phép thử nhỏ chứng minh giả định đã chắc chắn.” | Đầu tư lớn dựa trên bằng chứng không đại diện. | Ghi giới hạn mẫu/điều kiện, thử tiếp nếu rủi ro cao. |
| “Đã đổi kế hoạch nên Sprint Goal cũng đổi liên tục.” | Mất mục tiêu ngắn hạn và nhịp kiểm tra có ý nghĩa. | Bảo vệ Sprint Goal; thương lượng phạm vi. Chỉ PO được hủy Sprint khi Goal lỗi thời. |
| “Tất cả các bên phải nhất trí mới được thay đổi.” | Trì hoãn ngay cả quyết định có trách nhiệm rõ. | Lắng nghe tác động, phân quyền chốt, thông báo minh bạch. |
| “Giữ mọi cam kết bằng làm thêm giờ kéo dài.” | Kiệt sức, lỗi tăng và dự báo các vòng sau kém. | Giữ nhịp bền vững; thương lượng lựa chọn và giảm công việc không cần thiết. |

## 16. Bài tập và tình huống thực hành

### Tình huống A — Phạm vi tăng nhưng ngày phát hành cố định

Nhóm đã dự báo phát hành luồng đăng ký cơ bản trong hai tuần. Bộ phận kinh doanh yêu cầu thêm đăng nhập mạng xã hội và tùy biến giao diện trước ngày công bố. Các yêu cầu này chưa có bằng chứng liên quan tới tỷ lệ hoàn tất đăng ký.

**Câu hỏi:**

1. Product Goal và lát cắt tối thiểu cần giữ là gì?
2. Làm sao phân biệt yêu cầu bắt buộc với mong muốn mới?
3. Nếu phải giữ ngày, ba lựa chọn phạm vi nào có thể trình bày?
4. Quyết định cần có bằng chứng và thẩm quyền nào?

**Hướng xử lý tham khảo:** Kiểm tra kết quả cần đạt và nghĩa vụ của mốc phát hành. Giữ luồng đăng ký cơ bản đúng và an toàn, đưa hai khả năng mới vào Product Backlog; cân nhắc thử nghiệm nhỏ nếu giá trị chưa rõ. Nêu rõ việc hoãn hoặc cần đổi thời gian nếu muốn giữ đủ cả ba khả năng. Không bỏ kiểm thử đăng ký để lấy thời gian tô màu giao diện.

### Tình huống B — Nguồn lực giảm giữa Sprint

Sprint Goal là “cho phép khách hàng đặt được một lịch hợp lệ và nhận xác nhận”. Một Developer phụ trách tích hợp phải hỗ trợ sự cố trong ba ngày; một story phụ về lịch sử tìm kiếm vẫn đang làm.

**Câu hỏi:**

1. Công việc nào ảnh hưởng trực tiếp Sprint Goal?
2. Nhóm có thể làm gì để giảm WIP và điểm phụ thuộc?
3. Developers và Product Owner cần phối hợp thế nào?
4. Điều gì cần cập nhật trong dự báo cho các bên liên quan?

**Hướng xử lý tham khảo:** Xem phần việc còn lại và kỹ năng khả dụng. Ưu tiên luồng đặt lịch hợp lệ, kiểm thử và xác nhận; cân nhắc dừng/hoãn story lịch sử tìm kiếm nếu không giúp đạt mục tiêu. Developers điều chỉnh Sprint Backlog và thương lượng phạm vi với Product Owner khi cần, không hạ chất lượng. Công khai sự cố, tác động và rủi ro còn lại.

### Tình huống C — Giả định API bị bác bỏ muộn

Sau hai tuần thiết kế, nhóm phát hiện hệ thống đối tác không hỗ trợ cập nhật đơn hàng trực tiếp; mọi thay đổi phải tạo đơn mới và hủy đơn cũ. Đối tác chưa cam kết giới hạn thời gian xử lý và khả năng rollback.

**Câu hỏi:**

1. Quyết định thiết kế nào phụ thuộc vào giả định cũ?
2. Spike giới hạn nào có giá trị nhất?
3. Có thể giao lát cắt nào độc lập để nhận phản hồi?
4. Khi nào bắt buộc thương lượng lại phạm vi hoặc mốc giao?

**Hướng xử lý tham khảo:** Ghi rủi ro tính nhất quán và giao dịch lặp; kiểm tra hợp đồng và thử kịch bản timeout/cạnh tranh trong sandbox. Không khẳng định production an toàn từ mock. Giao hành vi xem trạng thái hoặc đặt đơn cơ bản nếu độc lập và an toàn; nếu phần đổi đơn bắt buộc nhưng chưa có phương án đủ tin cậy, cần đổi dự báo và thông báo đúng người quyết định.

### Tình huống D — Kế hoạch có vẻ đúng lịch nhưng không tạo giá trị

Nhóm đã hoàn thành 90% ticket cho một chức năng tìm kiếm nâng cao. Thử nghiệm sớm cho thấy người dùng cần tìm theo mã đơn hàng đơn giản, còn bộ lọc mới hầu như không giúp hoàn tất tác vụ.

**Câu hỏi:**

1. Vì sao “đã làm 90%” không đủ để tiếp tục đầu tư?
2. Nên so chi phí nào từ **thời điểm hiện tại** trở đi?
3. Những phương án nào có thể bảo vệ giá trị khách hàng?

**Hướng xử lý tham khảo:** Nhìn chi phí còn lại, giá trị dự báo và rủi ro, không bị chi phí chìm chi phối. Có thể dừng mở rộng bộ lọc, giao tìm theo mã đơn, đo kết quả và cập nhật backlog. Hoàn tất đúng ticket cũ không có ý nghĩa nếu vấn đề người dùng đã được hiểu khác.

### Bài tập nhóm — Tái lập kế hoạch trong 20 phút

Cho kế hoạch minh họa:

- Mục tiêu: khách hoàn tất đặt lịch hợp lệ.
- Năng lực dự báo: 30 người-ngày.
- Công việc còn lại: luồng xác nhận 10; email 5; chống lịch trùng 6; bộ lọc 7; kiểm thử tích hợp 4 người-ngày.
- Thông tin mới: mất 5 người-ngày do hỗ trợ sự cố; nghiên cứu người dùng cho thấy email ít cấp bách hơn xác nhận rõ.

**Yêu cầu:**

1. Tính tổng công sức dự kiến (**32 người-ngày**) và năng lực mới (**25 người-ngày**). Khoảng chênh **7 người-ngày** chỉ là tín hiệu ban đầu; cần xét phụ thuộc và mức chắc chắn của ước lượng.
2. Đề xuất ít nhất **hai kế hoạch khác nhau**: một ưu tiên ngày giao, một ưu tiên phạm vi.
3. Nêu rõ hạng mục được hoãn, điều kiện chất lượng không được bỏ, phụ thuộc và rủi ro.
4. Viết một thông báo cho bên liên quan gồm quyết định, lý do và thời điểm xem lại.
5. Chọn hai chỉ số kết quả/chất lượng để kiểm chứng sau lần giao.

**Gợi ý đáp án:** Có thể giữ luồng xác nhận (10), chống lịch trùng (6) và kiểm thử tích hợp (4), tổng 20 người-ngày theo dự báo thô; dành 5 người-ngày cho bất định/việc liên quan trước ngày giao, hoãn email và bộ lọc. Đây chỉ là **một phương án** và có thể cần thay đổi nếu phụ thuộc thực tế không cho phép. Phương án giữ toàn bộ phạm vi đòi hỏi thương lượng ngày hoặc năng lực thực sự khả dụng. Không dùng chênh 7 người-ngày làm lý do bỏ kiểm thử bắt buộc.

## 17. Checklist thực hiện khi có thay đổi

### Trước khi đổi kế hoạch

- [ ] Có tín hiệu cụ thể và nguồn bằng chứng, phân biệt dữ kiện với suy diễn.
- [ ] Đã xác minh có sự cố/điều kiện an toàn hoặc nghĩa vụ bắt buộc cần xử lý ngay không.
- [ ] Mục tiêu cần giữ, phạm vi dự kiến, forecast và cam kết đã được phân biệt.
- [ ] Biết nguồn lực thực sự khả dụng và những kỹ năng/phụ thuộc đang tắc.
- [ ] Đã đánh giá ảnh hưởng tới giá trị, năng lực, thời gian, rủi ro và chất lượng.
- [ ] Có ít nhất một phương án giảm phạm vi/chia lát cắt và một phương án thay dự báo hoặc giải pháp.

### Khi chốt và triển khai

- [ ] Người có thẩm quyền quyết định đã xem bằng chứng và đánh đổi.
- [ ] Đã xác định việc nào bị hoãn, giảm hoặc loại bỏ khi thêm ưu tiên mới.
- [ ] Đã cập nhật Product Backlog, Sprint Backlog/workflow, phụ thuộc và forecast ở đúng nơi nhóm dùng.
- [ ] Các bên liên quan hiểu điều đã quyết định, còn bất định và mốc xem lại.
- [ ] Definition of Done, an toàn, bảo mật và tính đúng đắn không bị hy sinh để giữ ngày.
- [ ] Các hạng mục được chia đủ nhỏ để kiểm chứng giá trị, không tăng WIP không cần thiết.
- [ ] Có chỉ số về outcome, chất lượng và dòng công việc để học sau lần giao.

## 18. Ghi nhớ cốt lõi

**Điều chỉnh kế hoạch Agile không phải lập lại lịch cho đẹp.** Đó là việc đưa thông tin mới vào quyết định: khi **phạm vi** đổi, xem lại giá trị và chia lát cắt; khi **nguồn lực** đổi, đánh giá năng lực/kỹ năng thật cùng điểm nghẽn; khi **giả định** sai, kiểm chứng phần rủi ro nhất và cập nhật giải pháp. Các thay đổi ấy phải được phản ánh trong backlog, dự báo và thông tin cho bên liên quan.

Một nhóm thích ứng tốt **không hứa rằng mọi thứ giữ nguyên bất kể điều kiện**, mà biết giải thích điều gì đáng giữ, điều gì có thể thương lượng, điều gì chưa chắc chắn và tín hiệu nào sẽ khiến họ đổi quyết định tiếp. Scrum tạo nhịp kiểm tra và mục tiêu, Kanban làm hiện rõ dòng công việc và WIP, XP giảm chi phí thay đổi bằng chất lượng kỹ thuật. Kết hợp phù hợp các thực hành đó giúp nhóm giao phần mềm tăng dần, có ích và đáng tin cậy.

### Tài liệu nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — giá trị đáp ứng thay đổi hơn bám theo kế hoạch.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — đón nhận thay đổi, giao phần mềm thường xuyên, nhịp làm việc bền vững.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal, Sprint Goal, Sprint Backlog, trách nhiệm Scrum Team, điều chỉnh phạm vi và hủy Sprint.
- [The Kanban Guide](https://kanbanguides.org/) — workflow, WIP và các chỉ số dòng công việc.
- [DORA](https://dora.dev/) — nghiên cứu về năng lực giao thay đổi phần mềm và độ ổn định vận hành.
