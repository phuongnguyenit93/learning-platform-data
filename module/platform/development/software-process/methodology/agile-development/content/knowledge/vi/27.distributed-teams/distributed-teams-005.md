# Giảm thời gian chờ do múi giờ và bàn giao thiếu bối cảnh

## 1. Vì sao một câu hỏi nhỏ có thể làm công việc chậm hai ngày?

Một nhóm Agile xây nền tảng học trực tuyến gồm thành viên tại Việt Nam, Vương quốc Anh và Hoa Kỳ. Một kỹ sư ở Việt Nam đang làm chức năng **hủy đăng ký buổi hướng dẫn**. Gần cuối ngày, họ gửi:

> “API trả trạng thái lạ. Ai xem giúp?”

Người phụ trách dịch vụ ở Hoa Kỳ bắt đầu làm việc vài giờ sau, nhưng không biết API nào, phiên bản nào, yêu cầu ra sao, kết quả mong muốn là gì hoặc ai được phép quyết định đổi hợp đồng. Họ trả lời: “Bạn gửi thêm log và ví dụ nhé.” Lúc đó kỹ sư Việt Nam đã nghỉ. Sáng hôm sau, người gửi bổ sung ảnh chụp nhưng chưa có ID môi trường và dữ liệu thử có thể tái hiện. Một vòng chờ khác bắt đầu.

**Một lỗi có thể sửa trong ba mươi phút đã mất gần hai ngày lịch chỉ vì thông tin phải đi qua nhiều vòng hỏi–đáp không chồng giờ làm việc.**

Vấn đề không chỉ là “múi giờ khác nhau”, cũng không thể giải quyết bền vững bằng cách yêu cầu mọi người thức khuya hoặc trực tin nhắn liên tục. Hai yếu tố kết hợp tạo ra độ trễ:

1. **Khoảng cách thời gian:** người có thể trả lời không cùng giờ làm hoặc chỉ có một khoảng chồng lấn ngắn.
2. **Bàn giao thiếu bối cảnh:** người nhận không đủ thông tin, thẩm quyền và tiêu chí để tiếp tục mà không phải hỏi lại.

Mục tiêu của bài học là giúp nhóm **giảm số vòng chờ không cần thiết và nâng chất lượng mỗi lần chuyển giao**, đồng thời bảo vệ sự tập trung, chất lượng sản phẩm và nhịp làm việc bền vững.

Chủ đề thuộc chương **Nhóm phân tán** của module **AGILE_DEVELOPMENT**: hiểu giá trị và nguyên tắc Agile thông qua phản hồi sớm, giao sản phẩm tăng dần, cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân tích **thời gian chờ do lệch múi giờ** và **thời gian chờ do thiếu thông tin** như những vấn đề riêng nhưng liên quan.
2. Thiết kế một **bản bàn giao đủ bối cảnh để người nhận có thể tiếp tục công việc**.
3. Thiết lập chính sách giao tiếp bất đồng bộ, kênh khẩn cấp, giờ chồng lấn và cách xử lý các quyết định bị chặn.
4. Phân biệt **owner**, người thực hiện tiếp, người có quyền quyết định và người xác minh kết quả.
5. Áp dụng các thực hành Scrum, Kanban và XP trong nhóm phân tán mà không thêm cuộc họp một cách máy móc.
6. Đo **blocked time, work item age, cycle time và số vòng làm rõ** để biết thay đổi cách bàn giao có thực sự hiệu quả không.
7. Nhận diện tác dụng phụ như làm việc ngoài giờ, phân mảnh tri thức, suy giảm bảo mật hoặc giảm chất lượng kiểm thử.

## 2. Nhìn thời gian chờ như một phần của dòng tạo giá trị

Giả sử một hạng mục mất sáu ngày làm việc từ lúc bắt đầu đến lúc đạt Definition of Done. Thời gian hoạt động kỹ thuật trực tiếp có thể chỉ khoảng hai ngày; còn lại là đợi trả lời, đợi xem xét, đợi môi trường thử và sửa lại sau các quyết định muộn.

| Trạng thái minh họa | Thời lượng | Có đang tạo tiến triển trực tiếp? |
|---|---:|---|
| Làm rõ yêu cầu và viết mã | 1,5 ngày làm việc | Có, nếu dựa trên thông tin đúng. |
| Chờ quyết định nghiệp vụ từ nhóm khác múi giờ | 1,0 ngày làm việc | Chưa; công việc bị chặn. |
| Tích hợp và kiểm thử | 0,5 ngày làm việc | Có. |
| Chờ phản hồi PR và môi trường thử | 2,0 ngày làm việc | Chưa; thông tin hoặc tài nguyên chưa sẵn. |
| Sửa sau review và xác minh lại | 1,0 ngày làm việc | Một phần là làm lại. |
| **Tổng** | **6,0 ngày làm việc** | **2,0 ngày làm việc tạo tiến triển ban đầu; phần khác là chờ/làm lại.** |

Các số trên **hoàn toàn giả định**, chỉ nhằm tách thành phần công việc. Không nên tự động xem mọi thời gian không gõ mã là lãng phí: kiểm thử, phản biện, nghiên cứu và nghỉ ngơi đều có thể thiết yếu cho chất lượng.

### 2.1. Tách các nguồn chờ

- **Waiting for decision:** chờ câu trả lời hoặc phê duyệt nghiệp vụ/kỹ thuật.
- **Waiting for information:** thiếu ví dụ, log, dữ liệu thử hoặc hợp đồng API.
- **Waiting for handoff:** người nhận chưa biết có việc chuyển giao, hoặc chưa rõ người chịu trách nhiệm tiếp.
- **Waiting for capacity:** người nhận có đủ thông tin nhưng không có thời gian xử lý.
- **Waiting for environment:** thiếu quyền, dữ liệu hoặc môi trường kiểm chứng.
- **Waiting for integration:** các thành phần do nhiều nhóm phát triển chưa tương thích.
- **Rework:** hiểu khác nhau và phải sửa khi thông tin đến muộn.

Múi giờ thường **khuếch đại** các nguồn chờ này: mỗi vòng làm rõ có thể kéo dài thêm một ca làm việc. Muốn giảm chờ, nhóm phải xử lý **nguyên nhân của vòng hỏi lại**, không chỉ đặt mục tiêu trả lời tin nhắn nhanh hơn.

### 2.2. Sơ đồ một vòng bàn giao lặp

~~~mermaid
flowchart TD
    A["Người gửi chuyển câu hỏi cuối ca"] --> B{"Người nhận có đủ ngữ cảnh và quyền?"}
    B -->|Không| C["Hỏi lại về mục tiêu, dữ liệu, quyết định"]
    C --> D["Chờ ca tiếp theo"]
    D --> A
    B -->|Có| E["Kiểm tra, thực hiện hoặc quyết định"]
    E --> F["Cập nhật bằng chứng và người tiếp theo"]
    F --> G["Công việc tiến đến trạng thái dùng được"]
~~~

Một bản bàn giao tốt làm tăng khả năng đi từ **B sang E ngay lần đầu**. Không có mẫu bàn giao nào bảo đảm loại bỏ hết câu hỏi, nhưng có thể giảm vòng hỏi lại vô ích.

## 3. Hiểu đúng múi giờ: thời điểm, giờ làm và khoảng chồng lấn

Nhóm phân tán phải phân biệt **một thời điểm chung** với **giờ hiển thị địa phương**. Ví dụ, cùng một thời điểm có thể là buổi chiều ở Việt Nam, buổi sáng ở châu Âu và giữa đêm ở một số nơi tại Hoa Kỳ.

### 3.1. Cùng một thời điểm, ba đồng hồ

Ví dụ **ngày 02/12/2026**, theo chế độ giờ mùa đông áp dụng tại các địa điểm nêu:

| Địa điểm / múi giờ | Giờ địa phương tại cùng một thời điểm |
|---|---|
| TP. Hồ Chí Minh — **Asia/Ho_Chi_Minh** | 16:00, 02/12/2026 |
| London — **Europe/London** | 09:00, 02/12/2026 |
| New York — **America/New_York** | 04:00, 02/12/2026 |
| Mốc chung UTC | 09:00 UTC, 02/12/2026 |

Cuộc họp 16:00 tại Việt Nam hợp lý với nhiều người ở London nhưng **không thể mặc định** là giờ làm của đồng nghiệp New York.

**Quy tắc kỹ thuật:** khi ghi lịch hoặc deadline liên vùng, dùng múi giờ định danh theo vùng (ví dụ **Europe/London**, **America/New_York**) hoặc thời điểm UTC có ký hiệu rõ. Không giả định London hay New York luôn có cùng độ lệch UTC quanh năm: lịch đổi giờ mùa hè có thể làm thay đổi khoảng chồng lấn. Tránh ghi “họp 9 giờ” mà không có ngày và múi giờ.

### 3.2. Giờ chồng lấn là tài nguyên có giới hạn

**Overlap window** là khoảng thời gian các thành viên cần phối hợp cùng đang trong giờ làm việc đã thống nhất. Nó có thể chỉ có với **một số cặp nhóm**, không tồn tại đồng thời cho toàn tổ chức.

Nhóm cần xác định:

- Những quyết định nào thực sự cần nói chuyện đồng thời?
- Những cặp vai trò nào cần chồng giờ làm?
- Khoảng chồng lấn có công bằng, bền vững theo tuần/tháng?
- Việc nào có thể chuẩn bị trước để cuộc trao đổi ngắn tạo ra quyết định?
- Ai thay thế nếu người có thẩm quyền vắng mặt?

Không nên dùng việc một người thường xuyên online ngoài giờ làm làm bằng chứng rằng tổ chức có overlap đủ tốt.

### 3.3. Phân tán không có nghĩa phải vận hành 24/7

Một dịch vụ có thể cần cơ chế ứng phó khẩn xuyên ngày đêm, nhưng phần lớn công việc phát triển **không cần mọi thành viên luôn trực**. Tách rõ:

- **Cộng tác bình thường:** bất đồng bộ là mặc định; trả lời trong khung giờ làm việc.
- **Quyết định đang chặn dòng công việc:** có đường ưu tiên rõ, phù hợp giờ làm và thẩm quyền.
- **Sự cố ảnh hưởng người dùng hoặc an toàn:** theo lịch trực và quy trình khẩn đã được phê duyệt.

Sự bền vững quan trọng không kém độ trễ: một nhóm giảm thời gian chờ bằng cách ép người khác thức đêm có thể tăng lỗi, kiệt sức và giảm hiệu quả về lâu dài.

## 4. Thiết kế giao tiếp bất đồng bộ trước khi thêm cuộc họp

**Async-first** nghĩa là mặc định cung cấp thông tin có thể đọc, kiểm tra và trả lời mà không cần mọi người cùng xuất hiện tại một thời điểm. Nó **không cấm họp, pair programming hoặc thảo luận trực tiếp**.

### 4.1. Chọn kênh theo mục đích

| Nhu cầu | Hình thức thường phù hợp | Cần lưu gì? |
|---|---|---|
| Thông báo tiến độ bình thường | Bình luận PBI/PR, cập nhật ngắn trong kênh chung. | Trạng thái, blocker, bước tiếp và người nhận. |
| Câu hỏi nghiệp vụ cần quyết định | Bình luận có ví dụ, lựa chọn và deadline mong đợi. | Quy tắc đã quyết định, lý do và tiêu chí chấp nhận liên quan. |
| Thảo luận nhiều phương án thiết kế | Tài liệu ngắn có đề xuất; call khi vòng trao đổi bất đồng bộ quá dài. | Quyết định, rủi ro, phương án loại và điều kiện xem lại. |
| Review mã | PR nhỏ, mô tả có bằng chứng, test, vùng rủi ro. | Kết luận review và thay đổi cần thực hiện. |
| Sự cố khẩn | Kênh cảnh báo, trực vận hành và đường tăng cấp riêng. | Dòng thời gian sự cố, hành động và xác minh phục hồi. |
| Chia sẻ học hỏi sau sự cố | Postmortem có thể đọc bất đồng bộ; họp khi cần hợp tác sâu. | Nguyên nhân góp phần, action cải tiến và owner. |

**Một tin nhắn đã được gửi không đồng nghĩa thông tin đã đến đúng người.** Để tránh thất lạc, cần gắn thông tin với artifact đang làm việc và xác định người phải nhận.

### 4.2. Khi nào đồng bộ đáng giá?

Một cuộc trao đổi đồng thời có thể hiệu quả khi:

- Có nhiều giả định xung đột và cần xây hiểu biết chung nhanh.
- Quyết định rủi ro cao cần chuyên môn của nhiều vai trò cùng lúc.
- Bình luận qua lại nhiều vòng mà không làm rõ được tranh chấp.
- Pair hoặc mob programming giúp chẩn đoán lỗi phức tạp.
- Sự cố khẩn cần điều phối thời gian thực.

Nhưng nên **chuẩn bị bối cảnh, câu hỏi và phương án trước**, sau cuộc gọi ghi quyết định ở nơi người vắng mặt đọc được. Nếu buổi họp chỉ để đọc từng ticket, thử cập nhật bất đồng bộ và dành overlap cho blocker thật.

### 4.3. Quy tắc chuyển từ async sang sync

Một thỏa thuận có thể là:

> Nếu câu hỏi đang chặn một hạng mục quan trọng và sau một số vòng phản hồi không tiến gần quyết định, owner đề nghị cuộc trao đổi đồng bộ ngắn giữa **đúng những người có thông tin và quyền quyết định**. Trước cuộc gọi gửi bối cảnh; sau cuộc gọi cập nhật quyết định vào artifact.

Đừng định nghĩa “hai tin nhắn là phải họp” như luật cứng cho mọi trường hợp. Mục tiêu là giảm **tổng thời gian từ câu hỏi tới quyết định đủ dùng**, không tối đa hóa số cuộc họp.

## 5. Working agreement: cùng hiểu kỳ vọng trả lời

Khi làm việc phân tán, một người có thể nghĩ “tôi gửi chiều nay, sáng mai phải có câu trả lời”, trong khi người nhận mới vừa hết ca khi câu hỏi xuất hiện. Thiếu thỏa thuận dẫn đến chờ đợi, trách móc và yêu cầu online ngoài giờ.

Một **working agreement** nên làm rõ:

| Chủ đề | Câu hỏi cần thống nhất |
|---|---|
| Giờ làm và múi giờ | Mỗi người/nhóm có khung làm việc thông thường nào? Thay đổi theo mùa ra sao? |
| Kênh chuẩn | Câu hỏi theo PBI/PR, quyết định API và sự cố được báo ở đâu? |
| Mức ưu tiên | Phân biệt bình thường, đang chặn và sự cố cần ứng phó ra sao? |
| Phản hồi mong đợi | Trong khung giờ làm, bao lâu cần có **acknowledgement** hoặc hướng xử lý ban đầu? |
| Bàn giao | Trước khi kết thúc ca, phải ghi tối thiểu mục tiêu, trạng thái, bằng chứng, blocker và bước tiếp nào? |
| Người nhận | Ai nhận công việc, ai có thẩm quyền quyết định, ai thay khi vắng mặt? |
| Overlap | Dành cho chủ đề nào, ai thực sự cần dự, chính sách luân phiên giờ bất tiện? |
| Ngắt quãng | Khi nào dùng tin nhắn không đồng bộ, khi nào liên hệ trực tiếp? |
| Quyết định | Kết luận được ghi ở đâu và thay đổi API/acceptance criteria được thông báo như thế nào? |
| Xem lại | Khi nào kiểm tra thỏa thuận có giảm chờ và giữ chất lượng không? |

### 5.1. Ví dụ chính sách phản hồi theo cấp

~~~text
THỎA THUẬN MINH HỌA — KHÔNG PHẢI SLA CHUNG

NORMAL
  - Ghi câu hỏi vào artifact chính và gắn đúng người.
  - Mong đợi acknowledgement trong 1 ngày làm việc của người nhận.
  - Không yêu cầu trả lời ngoài giờ.

BLOCKED / NEEDS DECISION
  - Ghi tác động, người chịu trách nhiệm và mốc cần quyết định.
  - Người nhận xác nhận hướng xử lý trong khung phối hợp đã thỏa thuận.
  - Nếu không có quyền quyết định, chuyển đúng đầu mối thay vì hỏi vòng quanh.

INCIDENT / SECURITY
  - Dùng quy trình trực và tăng cấp của tổ chức.
  - Không dùng kênh chat thường hoặc chỉ tiêu phản hồi NORMAL để xử lý sự cố.

AFTER DECISION
  - Ghi câu trả lời, lý do, ví dụ và người nhận việc tiếp theo
    vào PBI/PR/hợp đồng API thích hợp.
~~~

Các thời lượng ở ví dụ là **đề xuất minh họa**, phải được điều chỉnh theo năng lực thật, múi giờ và yêu cầu sản phẩm. **Acknowledgement** nghĩa là “đã nhận và biết bước tiếp”, **không đồng nghĩa quyết định đã hoàn tất**.

### 5.2. Phân biệt SLE, kỳ vọng và cam kết hợp đồng

Trong quản lý dòng công việc, một **Service Level Expectation (SLE)** thường mô tả dự báo khoảng thời gian hoàn thành theo dữ liệu lịch sử và chính sách. Nó không giống một **Service Level Agreement (SLA)** hợp đồng có điều khoản áp dụng.

Ví dụ, “phần lớn yêu cầu review đủ điều kiện nhận phản hồi trong hai ngày làm việc” có thể là kỳ vọng nội bộ được xem lại từ dữ liệu; không tự động là bảo đảm tuyệt đối. Nếu nhóm có nghĩa vụ bảo mật hoặc pháp lý với thời hạn cụ thể, phải tuân thủ các yêu cầu ấy, không thay thế bằng SLE thông thường.

## 6. Bộ bàn giao đủ bối cảnh: người nhận cần gì để tự đi tiếp?

Một **handoff packet** (gói bàn giao ngắn gọn) không cần dài, nhưng phải trả lời những câu hỏi mà người nhận sẽ phải hỏi khi người gửi đã offline.

### 6.1. Mười thành phần cốt lõi

| Thành phần | Câu hỏi người nhận cần được giải đáp |
|---|---|
| **1. Mục tiêu và giá trị** | Chúng ta muốn người dùng đạt điều gì, tại sao hạng mục này quan trọng? |
| **2. Phạm vi và trạng thái hiện tại** | Phần nào xong, phần nào chưa, môi trường/phiên bản nào đang xét? |
| **3. Quy tắc/tiêu chí chấp nhận** | Hành vi đúng là gì, trường hợp biên nào quan trọng? |
| **4. Những gì đã kiểm tra** | Đã thử gì, kết quả và giới hạn kiểm chứng thế nào? |
| **5. Bằng chứng tái hiện** | Bước, dữ liệu thử an toàn, log/trace/commit/PR nào giúp kiểm tra ngay? |
| **6. Quyết định và giả định** | Điều nào đã được thống nhất, điều nào vẫn chưa chắc? |
| **7. Blocker và tác động** | Công việc đang chờ ai/điều gì, ảnh hưởng tới mục tiêu hoặc người dùng ra sao? |
| **8. Việc tiếp theo và tiêu chí xong** | Người nhận nên thực hiện bước nào, làm sao biết hoàn tất? |
| **9. Owner và quyền quyết định** | Ai chịu trách nhiệm xuyên vòng, ai có thể phê duyệt thay đổi hoặc tăng cấp? |
| **10. Mức ưu tiên và mốc xem lại** | Cần phản hồi khi nào, nếu không có câu trả lời thì làm gì? |

Không phải mọi thay đổi nhỏ đều cần mười mục thành mười biểu mẫu. **Thông tin có thể nằm trong PBI, PR, test, issue hoặc tài liệu kỹ thuật rồi được liên kết**, miễn người nhận tìm được mà không phải đoán.

### 6.2. Mẫu bàn giao có thể sao chép

~~~markdown
## HANDOFF — [mã hạng mục và tên ngắn]

Mục tiêu người dùng:
  ...

Trạng thái:
  DONE: ...
  IN PROGRESS: ...
  NOT DONE: ...

Phạm vi:
  Repository / branch / PR / môi trường / phiên bản: ...

Quy tắc và ví dụ:
  Kỳ vọng: ...
  Trường hợp biên: ...

Đã kiểm chứng:
  Tests đã chạy: ...
  Kết quả: ...
  Chưa kiểm chứng / rủi ro: ...

Bằng chứng:
  Link PBI / PR / CI / log an toàn / trace ID: ...
  Cách tái hiện: ...

Quyết định đã chốt:
  ...
Giả định hoặc quyết định còn mở:
  ...

Next action:
  Người nhận: ...
  Bước cụ thể: ...
  Definition of done cho bước tiếp: ...

Blocked bởi:
  ...
Tác động và độ ưu tiên:
  ...

Phản hồi mong đợi:
  Trước mốc: ... (có ngày và múi giờ)
  Nếu không thể xử lý: chuyển tới ...

Owner xuyên suốt:
  ...
~~~

Mẫu này là **công cụ học tập**, không phải định dạng chuẩn bắt buộc. Nếu dùng một template quá dài làm tăng overhead, nhóm có thể rút gọn thành các phần **mục tiêu — hiện trạng — bằng chứng — quyết định — next action — owner**.

### 6.3. Bàn giao là truyền khả năng hành động, không chỉ truyền thông tin

Một mô tả bug rất chi tiết nhưng không có **người tiếp nhận và quyền hành động** vẫn có thể nằm chờ vô thời hạn. Ngược lại, một ticket có tên người phụ trách nhưng không có **bằng chứng tái hiện** lại tạo thêm vòng hỏi lại.

Do đó, đánh giá chất lượng handoff bằng câu hỏi:

> “Nếu người gửi offline hết ca, người nhận có thể thực hiện bước tiếp theo an toàn và biết khi nào cần hỏi thêm không?”

## 7. Từ bàn giao mơ hồ thành bàn giao có thể xử lý

### 7.1. Phiên bản thiếu bối cảnh

> “Backend sửa xong rồi, frontend kiểm tra hộ. Có lỗi timeout đôi khi.”

Người nhận có thể phải hỏi:

- Sửa phiên bản hoặc PR nào?
- Timeout ở endpoint nào?
- Môi trường nào và dữ liệu nào?
- Kết quả mong đợi là gì, đã kiểm tra gì?
- Cần sửa ngay hay chỉ cần phản hồi?
- Ai có quyền đổi hợp đồng API?

Nếu múi giờ không chồng lấn, mỗi câu hỏi có thể tiêu tốn thêm một vòng ca làm.

### 7.2. Phiên bản có ngữ cảnh hành động được

~~~text
HANDOFF: PBI-218 / Xác nhận hủy đăng ký buổi học

Mục tiêu:
  Học viên hủy đăng ký của mình và chỗ được trả lại đúng một lần.

Đã làm:
  - Backend xử lý thao tác gửi lặp theo quy tắc đã thống nhất.
  - PR #418 đã qua unit tests và integration tests theo CI link đính kèm.

Chưa xong:
  - Giao diện chưa hiển thị đúng trạng thái khi API trả kết quả chờ.
  - Chưa có kiểm chứng trên trình duyệt mục tiêu với mạng chậm.

Cách tái hiện (môi trường test, tài khoản giả lập):
  1. Tạo đăng ký hợp lệ của learner-test-01.
  2. Gửi yêu cầu hủy, mô phỏng timeout phía client.
  3. Gửi lại cùng mã yêu cầu thử.
  Expected: số chỗ tăng tối đa một lần, không báo thành công sai.

Bằng chứng:
  - Link issue, PR, bản CI và test case cụ thể trong công cụ chung.
  - Trace ID không chứa dữ liệu cá nhân đã được đính kèm đúng quyền.

Quyết định:
  - API dùng trạng thái "PENDING_CONFIRMATION" khi kết quả chưa rõ.
  - Chưa quyết định wording của thông báo UI; cần PO xác nhận.

Next action:
  Frontend: cập nhật trạng thái và chạy kịch bản lỗi mạng.
  PO: chọn wording thông báo trước phiên kiểm chứng.

Owner:
  Người điều phối PBI vẫn theo dõi đến khi tích hợp đạt DoD.

Phản hồi:
  Ghi kết quả hoặc blocker vào PBI, không chỉ gửi tin nhắn riêng.
~~~

Những mã PBI, PR, tài khoản và trạng thái trong mẫu là **minh họa**, không phải dữ liệu của một hệ thống thật.

### 7.3. Thông tin nào không nên đưa vào handoff?

- Token, mật khẩu, khóa API, cookie phiên hoặc dữ liệu người dùng thật không cần thiết.
- Toàn bộ log thô có thể chứa dữ liệu cá nhân nếu không có cơ chế bảo vệ phù hợp.
- Đường dẫn tới hệ thống nội bộ vượt quyền người nhận.
- Nhận định về cá nhân hoặc lịch làm việc riêng tư không cần thiết.
- Phần lịch sử dài không liên quan khiến người nhận khó thấy câu hỏi cần giải quyết.

Handoff tốt **đủ ngữ cảnh nhưng tối thiểu và an toàn**.

## 8. Bàn giao quyết định: không được để giả định biến thành sự thật

Một vấn đề phổ biến trong nhóm phân tán là quyết định chỉ xuất hiện trong cuộc gọi có vài người tham dự. Thành viên ở múi giờ khác tiếp tục viết mã theo giả định cũ.

### 8.1. Phân biệt trạng thái tri thức

Trong mô tả công việc, nên ghi rõ:

- **Đã quan sát:** có log/tình huống chứng minh một hành vi.
- **Giả thuyết:** cách giải thích có thể đúng nhưng chưa kiểm chứng.
- **Đã quyết định:** có người có thẩm quyền thống nhất và ghi kết luận.
- **Đang chờ quyết định:** cần người cung cấp thông tin hoặc phê duyệt.
- **Đã bị thay thế:** kết luận cũ không còn áp dụng; có liên kết tới kết luận mới.

Ví dụ, “frontend sẽ coi trạng thái đang chờ là thành công” có thể là **giả định nguy hiểm** nếu nghiệp vụ chưa xác nhận. Người nhận cần biết có được thực thi giả định đó không hay phải chờ quyết định.

### 8.2. Bản ghi quyết định ngắn

~~~markdown
Quyết định: Phản hồi khi kết quả đăng ký chưa chắc chắn
Ngày/giờ: 2026-12-02T09:00:00Z
Người quyết định: người có quyền nghiệp vụ của luồng đăng ký
Vấn đề: timeout phía client nhưng backend có thể đã lưu thành công
Lựa chọn đã xem:
  A. Báo thành công ngay
  B. Báo trạng thái đang xác minh, hỗ trợ tra cứu lại
Quyết định: B
Lý do: không tạo xác nhận sai khi trạng thái chưa rõ
Ảnh hưởng: API, UI, test cases, nội dung thông báo
Cần cập nhật: PBI, tiêu chí chấp nhận và contract test liên quan
Điều kiện xem lại: khi có cơ chế xác nhận tức thời đáng tin hơn
~~~

Một **decision log** nhỏ cạnh PBI hoặc tài liệu thiết kế giúp người vắng mặt hiểu **điều đã chốt và vì sao**, không chỉ nhìn thấy kết quả cuối.

### 8.3. Tránh nhiều nguồn sự thật

Nếu quy tắc hủy đăng ký tồn tại ở bốn nơi với nội dung khác nhau, việc viết thêm tài liệu không giúp giảm chờ. Hãy chọn **vị trí có thẩm quyền** cho từng loại thông tin (ví dụ acceptance criteria trong PBI, hợp đồng trong API specification, kết quả kiểm thử trong CI). Bàn giao **liên kết tới nguồn đó** thay vì sao chép và để các bản sao lỗi thời.

## 9. Sử dụng user story và ví dụ cụ thể để thay những câu hỏi vòng quanh

Khi cách hiểu nghiệp vụ khác nhau, câu hỏi mở như “hủy có trả chỗ không?” dễ sinh trao đổi dài vì thiếu ngữ cảnh.

### 9.1. Câu hỏi tốt có tình huống cụ thể

Thay vì:

> “Nếu học viên hủy muộn thì sao?”

Hãy hỏi:

> “Buổi hướng dẫn có sức chứa 20 người, đã xác nhận đủ 20. Học viên A hủy 10 phút trước giờ bắt đầu, danh sách chờ có B. Quy tắc có trả chỗ và xác nhận B tự động không? Nếu có, giới hạn thông báo và điều kiện xác nhận là gì?”

Người hiểu nghiệp vụ có thể trả lời **một lựa chọn rõ ràng** thay vì phải phỏng đoán tình huống người hỏi đang nghĩ.

### 9.2. Given–When–Then giảm hiểu sai xuyên ca

~~~gherkin
Feature: Hủy đăng ký và trả chỗ đúng quy tắc

  Scenario: Học viên hủy trước hạn được phép
    Given buổi học còn trong thời hạn cho phép hủy
    And học viên A có một đăng ký đã xác nhận
    When học viên A yêu cầu hủy đăng ký của mình
    Then đăng ký của A chuyển sang trạng thái hủy hợp lệ
    And số chỗ trống tăng đúng một lần

  Scenario: Yêu cầu hủy bị gửi lặp
    Given đăng ký của A đã được hủy thành công
    When cùng yêu cầu hủy hợp lệ được gửi lại
    Then không phát sinh lần trả chỗ thứ hai
    And hệ thống trả trạng thái theo chính sách đã thống nhất
~~~

Những ví dụ này **minh họa một chính sách giả định**, cần người có thẩm quyền nghiệp vụ xác nhận trước khi coi là tiêu chí thật.

### 9.3. Bàn giao ví dụ trước khi viết mã tốn kém

Một nhóm frontend và backend có thể làm rõ các trạng thái **confirmed**, **pending**, **cancelled**, **rejected** cùng ví dụ trước khi chia phần triển khai. Khi đó các bên có thể làm song song một cách an toàn hơn, giảm việc tích hợp xong mới phát hiện hai phía hiểu “thành công” khác nhau.

Đây là ứng dụng của **collaboration và early feedback** trong Agile; ví dụ tốt không thay thế kiểm thử tích hợp nhưng giúp phép kiểm thử bám sát hành vi đã thỏa thuận.

## 10. Owner, next actor và người quyết định không phải một vai trò

Trong nhóm phân tán, cụm “giao cho đội US” thường không đủ. Một hạng mục có thể chuyển giữa nhiều người, nhưng **trách nhiệm phối hợp cho kết quả cuối phải minh bạch**.

| Vai trò | Câu hỏi | Ví dụ |
|---|---|---|
| **End-to-end owner** | Ai theo dõi hạng mục tới khi đạt Done và không để phụ thuộc bị bỏ quên? | Người điều phối PBI thuộc nhóm sản phẩm. |
| **Next actor** | Người nào thực hiện bước tiếp có thể hành động được? | Kỹ sư backend xem trace và tái hiện lỗi. |
| **Decision maker** | Ai có quyền quyết định quy tắc hoặc chấp nhận rủi ro? | Product Owner/người nghiệp vụ có thẩm quyền về cách xử lý hủy. |
| **Verifier** | Ai xác minh kết quả đúng và đủ bằng chứng? | Developers và người có góc nhìn kiểm thử xác minh acceptance criteria/DoD. |
| **Fallback/escalation** | Nếu người nhận vắng hoặc không có quyền, ai tiếp nhận? | Người thay thế đã thỏa thuận, đầu mối nền tảng hoặc vận hành. |

Trong Scrum, những trách nhiệm tổ chức này **không thay thế** các accountability Scrum Team, Product Owner, Scrum Master và Developers. Việc chỉ định owner hành động không có nghĩa tạo một “project manager” chỉ huy mọi lựa chọn kỹ thuật của Developers.

### 10.1. Cần xác nhận đã nhận việc

Gắn tên người nhận không đủ nếu họ nghỉ phép, chuyển nhóm hoặc chưa thấy thông báo. Một quy tắc hợp lý:

1. Người gửi nêu rõ **next actor và mốc mong đợi**.
2. Người nhận xác nhận **đã nhận hoặc chuyển đúng đầu mối** trong khung phù hợp.
3. Nếu không thể nhận, thông báo người thay thế hay quyền quyết định cần thiết.
4. Khi hoàn thành bước, cập nhật bằng chứng và người tiếp theo.

Đây là **acknowledgement và quản lý dòng công việc**, không phải yêu cầu mọi người online tức thời.

### 10.2. Tránh handoff chain không cần thiết

Nếu một user story đi tuần tự qua “Business Analyst → Designer → Backend → Frontend → QA → Ops” và mỗi bước kết thúc bằng thông báo thiếu ngữ cảnh, số lần chờ tăng nhanh.

Thay vào đó, khi rủi ro và cấu trúc nhóm cho phép, có thể:

- Cùng làm rõ ví dụ giữa nghiệp vụ, phát triển và kiểm thử từ sớm.
- Thống nhất API contract trước khi frontend/backend làm song song.
- Dùng pair/cross-review để chuyển kiến thức trong quá trình xây.
- Tích hợp và kiểm thử từng lát nhỏ thay vì đợi toàn bộ lớp kỹ thuật xong.
- Giữ trách nhiệm chất lượng và vận hành xuyên vòng đời.

**Giảm số lần bàn giao không có nghĩa bỏ bước kiểm soát bắt buộc.** Ví dụ, thay đổi dữ liệu nhạy cảm vẫn cần thẩm quyền và kiểm chứng đúng chính sách.

## 11. Giới hạn công việc dở dang để giảm hàng chờ xuyên múi giờ

Giả sử ba kỹ sư ở ba nơi cùng mở tám PBI và mỗi PBI có một câu hỏi gửi sang đội khác. Khi thời gian phản hồi dài, mọi người có xu hướng **mở thêm việc mới để đỡ chờ**. Điều đó làm WIP tăng, ngữ cảnh bị chia nhỏ và nhiều PR tồn đọng hơn.

Kanban cung cấp tư duy hữu ích:

- **Visualize work:** hiển thị công việc và trạng thái chờ thật.
- **Limit WIP:** hạn chế số hạng mục đang thực hiện để tập trung hoàn thành.
- **Manage flow:** đo các thời gian và nút thắt thực.
- **Make policies explicit:** xác định khi nào một việc được chuyển, ai nhận, thế nào là sẵn sàng, thế nào là Done.
- **Feedback loops / improve collaboratively:** xem dữ liệu và cải tiến chính sách.

### 11.1. Ví dụ bảng có blocker rõ

| PBI | Giai đoạn | Đang chờ | Next actor | Bằng chứng còn thiếu | Mốc xem lại |
|---|---|---|---|---|---|
| Đăng ký buổi học | Tích hợp | Quy tắc xử lý request lặp | Người hiểu nghiệp vụ | Ví dụ khi timeout nhưng giao dịch đã ghi | Đầu ca giao nhau tiếp theo |
| Khôi phục tiến độ học | Review | Phản hồi hợp đồng API | Reviewer đã chỉ định | PR, CI, ví dụ trạng thái cũ/mới | Trong ngày làm việc của reviewer |
| Hủy đăng ký | Kiểm thử | Môi trường dữ liệu giả | Người phụ trách môi trường | Quyền test và bộ dữ liệu | Theo chính sách hỗ trợ nội bộ |

Nhóm nhìn thấy **công việc đang chờ điều gì cụ thể**, thay vì chỉ có cột “In Progress” hoặc một thẻ bị gắn nhãn blocked vô hạn.

### 11.2. Có nên tạo cột Waiting riêng?

Có thể, nếu nó giúp nhìn rõ lượng công việc chờ và chính sách xử lý. Tuy nhiên, không nên **chuyển ticket sang Waiting rồi loại nó khỏi WIP/tuổi hạng mục để che thời gian chậm**. Phải định nghĩa nhất quán trạng thái bắt đầu, kết thúc và blocked time.

### 11.3. Đừng coi “mỗi người đều bận” là mục tiêu

Khi một hạng mục đang chờ được gỡ, hỗ trợ người khác hoàn thành có thể tạo giá trị hơn mở thêm ticket. Điều này đặc biệt đúng ở nhóm phân tán: ít việc dở dang hơn thường giúp bàn giao ngắn, ít giả định và review tập trung hơn.

## 12. Chọn cách giảm chờ theo loại phụ thuộc

| Nút thắt | Cách can thiệp có thể thử | Điều cần kiểm chứng |
|---|---|---|
| Thiếu thông tin ngay lúc nhận việc | Chuẩn hóa gói bàn giao ngắn có next action và bằng chứng. | Số vòng hỏi lại và blocked time có giảm không? |
| Người có quyền quyết định ở múi giờ khác | Định nghĩa quyền quyết định và người thay thế; chuẩn bị lựa chọn trước overlap. | Thời gian tới quyết định có giảm, quyết định có đúng không? |
| Frontend/backend hiểu khác API | Contract-first phù hợp, ví dụ Given–When–Then và test hợp đồng. | Lỗi tích hợp và rework có giảm không? |
| PR tồn chờ reviewer | Chọn reviewer có năng lực/phù hợp giờ, PR nhỏ, chính sách review rõ. | Thời gian tới phản hồi có giảm mà chất lượng không suy giảm? |
| Mỗi lần hỏi lại mất một ca | Cung cấp bước tái hiện, log an toàn, kết quả CI và lựa chọn cần xác nhận. | Người nhận có thể hành động trong lần đọc đầu? |
| Quá nhiều cuộc họp | Chuyển cập nhật trạng thái sang async, dùng overlap cho quyết định khó. | Tổng thời gian chờ và tải cuộc họp có giảm? |
| Bàn giao dài không ai đọc | Tóm tắt quyết định/next action đầu trang, liên kết nguồn chi tiết. | Thời gian tìm thông tin, lỗi hiểu sai và số câu hỏi lặp? |
| Không biết ai nhận việc | Hiển thị owner, next actor, fallback và mốc nhận. | Hạng mục bị treo không chủ sở hữu có giảm? |
| Người nhận quá tải | Giảm WIP, giới hạn số PR đồng thời, điều phối năng lực. | Tuổi hàng chờ, cycle time và sức khỏe team? |

**Không có giải pháp đơn lẻ cho mọi nguồn chờ.** Một nhóm thiếu năng lực kiểm thử không thể giải quyết hoàn toàn chỉ bằng template handoff; một nhóm thiếu quyền quyết định cần làm rõ governance chứ không chỉ nhắc tin nhắn nhiều lần.

## 13. Đo thời gian chờ: định nghĩa trước khi vẽ biểu đồ

Nhóm cần phân biệt:

- **Lead time:** từ một điểm cam kết/tiếp nhận công việc đến lúc hoàn thành theo chính sách đã chọn.
- **Cycle time:** từ lúc công việc bắt đầu tiến hành đến Done theo định nghĩa cụ thể.
- **Blocked time:** tổng thời gian hạng mục nằm trong trạng thái chờ xác định.
- **Work item age:** thời gian đã trôi qua kể từ lúc bắt đầu cho hạng mục chưa hoàn thành.
- **Throughput:** số hạng mục hoàn thành trong một khoảng thời gian.
- **SLE:** kỳ vọng thời gian hoàn thành được rút ra từ dữ liệu và chính sách, không phải lời bảo đảm tuyệt đối.

Không có một cách chọn mốc đo duy nhất cho mọi hệ thống. Quan trọng là **nhất quán và gắn với quyết định muốn hỗ trợ**.

### 13.1. Ví dụ tính tỷ lệ chờ trong cycle time

Giả sử một PBI có **cycle time 6 ngày làm việc**, trong đó **2,5 ngày làm việc** được ghi nhận ở trạng thái blocked:

~~~text
Blocked-time ratio = Blocked time / Cycle time × 100%
                   = 2,5 / 6 × 100%
                   ≈ 41,7%
~~~

Đây là **số liệu giả định**. Tỷ lệ chỉ có ý nghĩa khi hai đại lượng dùng **cùng loại thời gian** và chính sách cộng thời gian phù hợp. Nếu cycle time dùng ngày lịch còn blocked time dùng giờ làm việc, phải chuẩn hóa trước; không chia hai số với đơn vị khác nhau.

### 13.2. Đo độ trễ quyết định và vòng hỏi lại

Để biết handoff cải thiện không, có thể đo:

- **Time to actionable response:** từ lúc người nhận được yêu cầu **đủ điều kiện**, đến khi có phản hồi có thể hành động.
- **Time to decision:** từ lúc câu hỏi cần quyết định được ghi, đến khi người có quyền chốt và cập nhật kết luận.
- **Clarification rounds:** số vòng hỏi lại **vì thiếu bối cảnh thiết yếu**, không tính tranh luận chuyên môn cần thiết.
- **Handoff completeness:** tỷ lệ bàn giao có đủ thông tin tối thiểu theo chính sách, nhưng **không coi chỉ số checklist là outcome**.
- **Rework due to misunderstanding:** số lần làm lại do giả định sai hoặc quyết định không được truyền đạt.
- **Unowned blocked items:** số việc bị chặn nhưng không có next actor/owner hoặc mốc xử lý.

Một bản bàn giao có tất cả mục checklist mà người nhận vẫn không hành động được có thể cần **sửa nội dung template**, không phải bổ sung thêm dấu kiểm.

### 13.3. Phân biệt tốc độ phản hồi và chất lượng phản hồi

Một comment “đã nhận” trong năm phút có thể đáp ứng mục tiêu acknowledgement nhưng chưa giúp công việc tiến. Ngược lại, một phân tích chuyên sâu sau hai giờ có thể tiết kiệm nhiều ngày làm lại.

Để tránh metric gaming, xem cả:

1. Thời gian tới **câu trả lời đủ dùng**.
2. Số vòng làm rõ.
3. Tỷ lệ lỗi/điều chỉnh sau quyết định.
4. Tác động tới cycle time và giá trị giao được.

**Tối ưu tổng thời gian và chất lượng dòng công việc**, không chỉ số phút trả lời chat.

## 14. Đo thời gian theo múi giờ mà không làm sai dữ liệu

Chỉ số chờ cần một đồng hồ thống nhất. Một số lưu ý:

1. **Lưu mốc dưới dạng thời điểm UTC** hoặc dạng có offset đáng tin; khi hiển thị chuyển sang múi giờ người xem.
2. **Giữ định danh múi giờ của đội** (như Asia/Ho_Chi_Minh, Europe/London) khi tính giờ làm và lịch nghỉ.
3. **Phân biệt thời gian lịch và thời gian làm việc**. Ví dụ yêu cầu gửi cuối thứ Sáu không có nghĩa người nhận đã chờ ba ngày làm việc đến sáng thứ Hai.
4. **Tính tới DST và ngày nghỉ khác nhau**; đừng dùng offset cố định cho vùng thay đổi giờ.
5. **Định nghĩa thời điểm bắt đầu chờ**: lúc comment được gửi hay lúc người nhận vào giờ làm, tùy câu hỏi đo lường.
6. **Không thay đổi định nghĩa giữa hai kỳ** rồi tuyên bố cải tiến.

### 14.1. Hai phép đo có thể cùng hợp lý

Với yêu cầu gửi lúc người nhận đang nghỉ:

- **Elapsed calendar time** phản ánh tổng thời gian PBI không tiến về mặt sản phẩm.
- **Recipient business-hours response time** phản ánh độ trễ trong thời gian người nhận có trách nhiệm xử lý theo chính sách.

Chúng trả lời **hai câu hỏi khác nhau**. Không nên dùng thời gian lịch để đổ lỗi người đang nghỉ, cũng không nên chỉ báo giờ làm để che việc sản phẩm phải chờ qua nhiều ngày lịch. Khi cải tiến, có thể xem cả hai.

### 14.2. Ví dụ thời điểm và đơn vị

~~~text
handoff_sent_at_utc:   2026-12-02T09:00:00Z
first_seen_at_utc:     2026-12-02T13:00:00Z
actionable_reply_utc:  2026-12-02T15:00:00Z

Calendar elapsed to actionable reply: 6 giờ.
Recipient working-hours elapsed: tính theo lịch làm việc đã thống nhất.
~~~

Không thể suy ra “6 giờ làm việc” chỉ từ ba timestamp UTC nếu chưa biết giờ làm và ngày nghỉ của người nhận.

## 15. Thời gian chờ không chỉ là chỉ số vận hành

Giảm blocked time có thể tạo những lợi ích khác:

- Người phát triển nhận phản hồi khi ngữ cảnh còn mới.
- Tích hợp các lát giá trị nhỏ hơn, phát hiện sai sớm hơn.
- Giảm lỗi do bản quyết định cũ được truyền miệng.
- Hạn chế chuyển đổi ngữ cảnh và làm lại.
- Người dùng nhận Increment đủ chất lượng sớm hơn.

Nhưng **giảm chờ chưa tự chứng minh outcome người dùng tăng**. Nếu nhóm chuyển hạng mục sai ưu tiên nhanh hơn, giá trị vẫn thấp. Do đó, khi xem cải tiến, nối flow metrics với Product Goal, chất lượng và phản hồi thực.

### 15.1. Ba tầng bằng chứng nên đặt cạnh nhau

| Tầng | Ví dụ |
|---|---|
| **Thực hành/đầu ra** | Mẫu handoff được dùng; quyết định được ghi vào artifact; có next actor rõ. |
| **Process outcome** | Ít vòng hỏi lại, blocked time và cycle time giảm, review không bị dồn. |
| **Product outcome/guardrail** | Ít lỗi tích hợp, thời gian giao giá trị ngắn hơn, không suy giảm bảo mật hoặc trải nghiệm. |

Nếu template được điền đầy đủ nhưng blocked time không đổi, đội nên kiểm tra liệu **nút thắt thật là thiếu bối cảnh, thiếu thẩm quyền hay thiếu năng lực xử lý**.

## 16. Ghi nhớ nguyên tắc bàn giao “tiếp tục được dù người gửi vắng mặt”

Một thay đổi nhỏ trong thói quen hàng ngày là dành vài phút cuối ca cập nhật **trạng thái thực và bước có thể làm ngay tiếp theo**.

Trước khi rời ca, người gửi tự hỏi:

1. Người nhận có nhìn thấy **mục tiêu PBI** mà không phải gọi tôi không?
2. Họ có phân biệt **đã làm — chưa làm — đang giả định — đang chờ quyết định**?
3. Bằng chứng kiểm chứng và cách tái hiện có đủ, an toàn và còn truy cập được?
4. Có một **next action** cụ thể, người nhận và tiêu chí hoàn thành bước đó?
5. Nếu người nhận không thể làm, có **fallback/escalation** hợp lý?
6. Khi quyết định thay đổi, có nơi cập nhật để các nhóm khác không dùng thông tin cũ?

**Không phải mọi việc cần bàn giao xuyên múi giờ.** Nếu người thực hiện sẽ tiếp tục vào sáng mai, có thể chỉ cần ghi trạng thái cho chính họ và những người phụ thuộc. Đừng tạo thủ tục chuyển tay không cần thiết cho tất cả PBI.

## 17. Scrum trong nhóm phân tán: giữ kiểm tra–thích ứng, thay cách phối hợp

Scrum không yêu cầu mọi người làm việc cùng một văn phòng. Tuy nhiên, Scrum Team phân tán cần điều chỉnh cách trao đổi để **mục tiêu chung, trạng thái Increment và trở ngại** vẫn minh bạch.

### 17.1. Sprint Goal quan trọng hơn cố đồng bộ mọi task

Một Scrum Team có thành viên ở nhiều múi giờ vẫn cần **Sprint Goal** thể hiện mục tiêu đáng theo đuổi trong Sprint. Khi mỗi nhóm tối ưu ticket riêng mà không thấy mục tiêu chung, họ dễ chuyển việc “đã xong phần mình” rồi mặc kệ lỗi tích hợp.

Ví dụ Sprint Goal:

> Học viên có thể hủy đăng ký một buổi hướng dẫn còn trong thời hạn cho phép và thấy trạng thái cuối cùng chính xác, trong phạm vi người dùng đã thống nhất.

Nếu backend đã merge nhưng frontend chưa hiển thị trạng thái đúng, hoặc tính năng chưa đạt Definition of Done, nhóm **chưa nên coi lát sản phẩm tương ứng là Done**. Không có “Done theo múi giờ của đội backend” thay thế chất lượng của Increment đã tích hợp.

### 17.2. Các sự kiện Scrum khi thời gian chồng lấn ngắn

| Sự kiện | Mục đích cần bảo toàn | Điều chỉnh phù hợp phân tán |
|---|---|---|
| **Sprint Planning** | Thống nhất giá trị Sprint, Sprint Goal và kế hoạch thực hiện ban đầu. | Chuẩn bị câu hỏi/backlog sớm; dành giờ chung cho quyết định và phụ thuộc quan trọng. |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch. | Dùng thông tin trạng thái cập nhật trước, trao đổi đồng bộ ngắn nếu khả thi; không biến thành buổi báo cáo cho người quản lý. |
| **Sprint Review** | Scrum Team và stakeholder kiểm tra Increment và bối cảnh, thích ứng hướng tiếp theo. | Gửi bản dùng thử, mục tiêu và câu hỏi trước; thu phản hồi async từ người không tham dự rồi thảo luận cùng những người cần quyết định. |
| **Sprint Retrospective** | Cải tiến chất lượng và hiệu quả cách làm của Scrum Team. | Thu phản hồi trước bằng văn bản; xem blocked time, handoff và tải ngoài giờ; chọn thí nghiệm có owner và mốc Check. |

Không nên tuyên bố rằng **chỉ một bản cập nhật chat tự động thay thế đầy đủ mọi sự kiện Scrum**. Nhóm áp dụng Scrum cần duy trì mục đích và các quy tắc của framework; cách tổ chức cụ thể nên phục vụ tương tác thật thay vì sao chép lịch họp của đội đồng địa điểm.

### 17.3. Backlog refinement nên giảm quyết định muộn

Refinement không phải một sự kiện bắt buộc có timebox riêng trong Scrum, nhưng hoạt động làm rõ Product Backlog là cần thiết. Với nhóm phân tán, những điều đáng chuẩn bị trước khi bắt đầu PBI gồm:

- Ví dụ nghiệp vụ và trường hợp biên cần người có quyền xác nhận.
- Những thay đổi hợp đồng API và phụ thuộc tới hệ thống khác.
- Ràng buộc về dữ liệu, bảo mật, hiệu năng và khả năng truy cập.
- Người có thể trả lời khi xuất hiện giả định chưa rõ.
- Các tiêu chuẩn chất lượng của Definition of Done.

Một đội có thể dùng một **checklist sẵn sàng trao đổi** để tránh thiếu bối cảnh, nhưng không nên tự khẳng định Scrum bắt buộc phải có một **Definition of Ready** chính thức. Nếu checklist biến thành cổng phê duyệt chậm, nó có thể gây thêm thời gian chờ.

### 17.4. Self-management không có nghĩa không có owner

Developers tự quản cách thực hiện công việc trong phạm vi Scrum, nhưng việc xác định **người nhận bàn giao kế tiếp, người theo dõi blocker và đầu mối quyết định nghiệp vụ** vẫn giúp giảm mơ hồ. Cần phân biệt trách nhiệm phối hợp với việc áp đặt quản lý vi mô hoặc làm thay quyền quyết định chính thức của Product Owner.

## 18. Kanban: làm rõ chính sách chuyển giao và quan sát hàng chờ

Kanban đặc biệt hữu ích khi nhóm hỗ trợ nhiều công việc có tính liên tục, phụ thuộc xuyên múi giờ hoặc có nhiều việc đang chờ.

### 18.1. Định nghĩa trạng thái để thấy cả nơi chờ

Một workflow minh họa:

~~~mermaid
flowchart LR
    A["Ready: đủ ngữ cảnh để bắt đầu"] --> B["In Progress"]
    B --> C["Review / Integration"]
    C --> D["Verification"]
    D --> E["Done theo chính sách"]
    B -.->|Cần quyết định| F["Blocked: có owner, lý do, mốc xem lại"]
    C -.->|Thiếu người review| F
    F -. "Gỡ blocker" .-> B
~~~

Lưu ý: các trạng thái này chỉ là **một mô hình minh họa**, không phải số cột Kanban chuẩn. Đội có thể giữ hạng mục trong trạng thái gốc và gắn nhãn blocker thay vì tạo cột riêng.

### 18.2. Quy tắc chuyển giao phải rõ

Ví dụ chính sách để một PBI đi từ **In Progress** sang **Review**:

1. PR có phạm vi và mục tiêu rõ.
2. Tác giả mô tả thay đổi, vùng rủi ro và đường kiểm thử.
3. CI bắt buộc đã chạy với kết quả hiện có được minh bạch.
4. Reviewer hoặc nhóm nhận đã được xác định.
5. Có cách tái hiện hoặc ví dụ cho hành vi không hiển nhiên.
6. Có mốc xem lại nếu review chưa đến.

Một chính sách không nên bắt thành viên viết nhiều trang cho sửa lỗi chính tả nhỏ. Hãy định nghĩa **thông tin tối thiểu theo loại và mức độ rủi ro của công việc**.

### 18.3. Review queue cần chính sách công bằng

Nếu reviewer ở một múi giờ là người duy nhất có quyền xem mọi thay đổi, họ có thể trở thành nút thắt. Các lựa chọn:

- Mở rộng khả năng review qua chia sẻ tri thức, pair review hoặc mentoring.
- Phân loại PR cần chuyên gia theo rủi ro.
- Tách PR lớn thành thay đổi nhỏ có thể kiểm chứng.
- Đặt chính sách ưu tiên rõ khi có nhiều PR chờ.
- Điều phối năng lực review như **một phần công việc**, không giả định review được thực hiện “lúc rảnh”.

Chỉ giảm thời gian phản hồi bằng cách duyệt qua loa sẽ làm mất mục đích review. Cần giữ guardrails về chất lượng, bảo mật và tính đúng nghiệp vụ.

### 18.4. WIP và tuổi hạng mục giúp nhận ra nguy cơ

Một PBI chưa Done nhưng đã ở In Progress lâu hơn đa số các PBI cùng loại cần được xem xét: thiếu thông tin, người nhận vắng, phụ thuộc chưa rõ hay vấn đề kỹ thuật thực sự khó?

**Work item age** giúp đặt câu hỏi trước khi hạng mục trễ, trong khi **cycle time** của các hạng mục đã Done giúp đánh giá dòng công việc đã xảy ra. Đừng chỉ nhìn throughput: nếu tăng số ticket Done bằng cách chia nhỏ ticket hoặc hạ Definition of Done, dòng giá trị có thể không cải thiện.

## 19. XP: phản hồi kỹ thuật nhanh giảm số lần hỏi lại xuyên ca

Những thực hành **Extreme Programming (XP)** hỗ trợ nhóm phân tán vì giúp biến một số câu hỏi thành **bằng chứng kỹ thuật tự kiểm tra được**.

### 19.1. Contract test thay nhiều vòng trao đổi API

Nếu frontend và backend đã thống nhất hợp đồng trạng thái, một bộ contract tests có thể phát hiện sai lệch sớm, trước khi người dùng ở nơi khác phải thức dậy và thử thủ công.

Ví dụ các trạng thái:

| Tình huống | Backend trả | Giao diện kỳ vọng |
|---|---|---|
| Đăng ký đã ghi thành công | **CONFIRMED** | Thông báo đã xác nhận, có chi tiết buổi. |
| Kết quả chưa rõ sau timeout | **PENDING_CONFIRMATION** | Không báo thành công; cho phép kiểm tra lại an toàn. |
| Buổi hết chỗ | **REJECTED_CAPACITY** | Giải thích còn hết chỗ và lựa chọn phù hợp. |
| Người dùng không có quyền | Từ chối theo chính sách | Không để lộ dữ liệu của người khác. |

Các giá trị trạng thái chỉ là **ví dụ thiết kế giả định**. Contract và hành vi phải được thống nhất bởi người có thẩm quyền và bảo đảm tương thích với hệ thống thật.

### 19.2. TDD và CI giảm phụ thuộc vào người gửi

Một bài kiểm thử rõ có thể thể hiện **hành vi mong đợi và cách tái hiện** khi tác giả đã offline. TDD và CI giúp người nhận biết thay đổi có làm hỏng bất biến quan trọng không mà không phải chờ tác giả tự chạy lại.

Tuy nhiên, pipeline xanh chỉ cho biết các phép kiểm tra đã cấu hình đạt; nó **không chứng minh** mọi trường hợp tích hợp, tải, phân quyền hay truy cập đã an toàn. Handoff vẫn cần ghi những gì **chưa kiểm chứng**.

### 19.3. Pair programming từ xa khi nào đáng thử?

Pair programming có thể giúp chuyển giao kiến thức nhanh khi:

- Cả hai cần hiểu vùng mã khó hoặc rủi ro cao.
- Sự cố tích hợp có nhiều giả thuyết và việc đọc log đơn lẻ mất thời gian.
- Một thành viên mới cần học hợp đồng, test và quyết định thiết kế.

Nhưng không nên bắt hai người ở múi giờ không chồng lấn phải ghép cặp bằng cách thường xuyên làm ngoài giờ. Có thể chọn **một khoảng overlap ngắn, luân phiên cặp trong vùng phù hợp** và ghi kết luận/bài test sau buổi ghép cặp.

### 19.4. Refactoring giúp handoff dễ hơn, nếu giữ bằng chứng

Một codebase đơn giản, naming nhất quán và test hồi quy tốt giúp người nhận hiểu thay đổi mà không phải hỏi tác giả. Ngược lại, refactoring lớn không có test đáng tin có thể làm tăng rủi ro và số vòng trao đổi khi hai người sửa cùng vùng mã khác ca.

## 20. Follow-the-sun: cơ hội và giới hạn

**Follow-the-sun** là cách tổ chức công việc để các nhóm ở nhiều vùng nối tiếp nhau theo ca, qua đó một số việc có thể tiến triển khi nhóm khác nghỉ.

Nó không tự tạo ra năng suất 24 giờ/ngày; cần **chất lượng bàn giao, quyền quyết định, tiêu chuẩn chung và khả năng nhận việc thực**.

### 20.1. Ví dụ ba khu vực trong tháng 12/2026

Giả sử giờ làm việc minh họa là **09:00–17:00 theo giờ địa phương**:

| Nhóm | Múi giờ vào ngày 02/12/2026 | Khoảng UTC tương ứng của ca |
|---|---|---|
| Việt Nam | Asia/Ho_Chi_Minh, UTC+07 | 02:00–10:00 UTC |
| London | Europe/London, UTC+00 | 09:00–17:00 UTC |
| New York | America/New_York, UTC−05 | 14:00–22:00 UTC |

Từ đó:

- **Việt Nam–London:** chồng khoảng **09:00–10:00 UTC** (16:00–17:00 tại Việt Nam; 09:00–10:00 tại London).
- **London–New York:** chồng khoảng **14:00–17:00 UTC** (14:00–17:00 tại London; 09:00–12:00 tại New York).
- **Việt Nam–New York:** không có overlap trong giả định giờ làm này.

**Đây là ví dụ tại một ngày mùa đông**, không phải bản lịch cố định cho cả năm. Giờ mùa hè, ngày nghỉ, chính sách cá nhân và giờ làm không giống nhau sẽ làm thay đổi kết quả.

### 20.2. Một chuỗi chuyển giao khả thi

1. Cuối ca Việt Nam, nhóm cập nhật issue, PR, kiểm thử, các quyết định đã chốt và next action.
2. London nhận trong giờ làm, thực hiện phần có thể hành động hoặc làm rõ phụ thuộc đã chuẩn bị.
3. Khi chuyển sang New York, London bàn giao trạng thái mới cùng bằng chứng kiểm chứng và quyền cần thiết.
4. New York xử lý phần phù hợp; kết quả được ghi lại để Việt Nam xem vào ca tiếp theo.

Đây là **một khả năng phối hợp**, không phải yêu cầu mỗi đội phải cầm cùng một ticket qua từng ca. Với công việc nhiều ngữ cảnh và phức tạp, chuyển tay liên tục có thể làm hại hơn lợi.

### 20.3. Khi nào follow-the-sun không phù hợp?

- Công việc đòi hỏi hiểu biết sâu, khó chia thành bước độc lập.
- Bằng chứng không thể chia sẻ qua quyền và quy định dữ liệu.
- Người nhận cần nhiều thời gian thiết lập môi trường hoặc đọc kiến trúc.
- Các quyết định không được phân quyền, phải chờ cùng một người.
- Giao diện hợp đồng chưa ổn định, thay đổi liên tục.
- Chênh lệch ca tạo nguy cơ một người phải làm ngoài giờ để “khâu nối”.

Trong các trường hợp đó, **giữ một owner làm liên tục qua vài ngày** và giảm phụ thuộc có thể tốt hơn chuyền hạng mục như dây chuyền.

### 20.4. Đừng tối ưu tỷ lệ sử dụng nhân sự

Nếu mục tiêu là “mọi ca đều phải có ticket để làm”, tổ chức có thể mở thêm nhiều việc dở dang, tăng review queue và sai lệch ngữ cảnh. Nên tối ưu **dòng hoàn thành phần giá trị**, không tối ưu hình ảnh tất cả thành viên đều bận.

## 21. Xử lý phụ thuộc xuyên nhóm trước khi chúng trở thành blocker

Nhóm phân tán thường còn phụ thuộc theo **kiến trúc và quyền sở hữu hệ thống**, không chỉ theo múi giờ.

Một thay đổi có thể đòi hỏi:

- Backend đổi hợp đồng API.
- Frontend cập nhật trạng thái hiển thị.
- Data team duy trì schema/tính nhất quán.
- Platform team cấp môi trường thử.
- Security xem kiểm soát truy cập.
- Product Owner xác nhận quy tắc nghiệp vụ.

Nếu chỉ phát hiện những phụ thuộc này vào ngày cuối Sprint, handoff dù tốt vẫn có thể không cứu được kế hoạch.

### 21.1. Vẽ mạng phụ thuộc cho lát giá trị

~~~mermaid
flowchart TD
    A["Lát giá trị: hủy đăng ký an toàn"] --> B["Quy tắc nghiệp vụ và quyền"]
    A --> C["Hợp đồng API"]
    A --> D["Luồng frontend và thông báo"]
    A --> E["Tính nhất quán dữ liệu"]
    A --> F["Kiểm thử và vận hành"]
    B --> G["Decision maker nghiệp vụ"]
    C --> H["Contract tests / tương thích"]
    E --> I["Kiểm tra đồng thời/idempotency"]
    F --> J["CI, cảnh báo, phương án phục hồi"]
~~~

Sơ đồ giúp nhóm thấy **điểm nào cần quyết định sớm** và **phần nào có thể triển khai song song sau khi giao diện/tiêu chí đã ổn định**.

### 21.2. Dependency card tối giản

~~~text
DEPENDENCY: API trạng thái hủy đăng ký
Consumer: giao diện học viên
Provider: dịch vụ đăng ký

Needed by:
  mốc tích hợp đã thống nhất, có ngày và múi giờ

Contract:
  link hợp đồng và ví dụ phản hồi mong đợi

Current state:
  ba trạng thái đã chốt, một trạng thái cần PO quyết định

Blocking question:
  khi timeout nhưng backend đã ghi, client nên thông báo gì?

Provider contact:
  người có thể cung cấp thông tin kỹ thuật
Decision maker:
  người có thẩm quyền nghiệp vụ

Fallback:
  tiếp tục xử lý các trạng thái đã chốt; không tự đoán trạng thái còn mở

Validation:
  contract test và integration test tương ứng
~~~

Điều quan trọng là **đường ra của phụ thuộc có thể nhìn thấy**. Không nên chuyển thông tin quan trọng vào cuộc trao đổi riêng giữa hai thành viên rồi bỏ những người còn phụ thuộc ở trạng thái cũ.

## 22. Code review và CI trong nhóm khác giờ làm việc

Review là nguồn phản hồi kỹ thuật quan trọng nhưng có thể trở thành hàng chờ lớn khi người xem không cùng giờ.

### 22.1. Một PR dễ review từ xa

Nên chứa:

1. **Mục đích:** thay đổi giải quyết vấn đề nào?
2. **Phạm vi:** thay đổi những thành phần nào, có gì cố ý không làm?
3. **Bằng chứng:** test đã chạy, liên kết kết quả CI và ví dụ hành vi.
4. **Rủi ro:** bảo mật, dữ liệu, hiệu năng, khả năng truy cập, tương thích.
5. **Cần quyết định gì:** câu hỏi cụ thể mà reviewer phải trả lời.
6. **Cách kiểm tra:** đường chạy an toàn hoặc dữ liệu thử, không yêu cầu secrets.
7. **Người nhận và mốc:** reviewer phù hợp và kỳ vọng phản hồi theo giờ làm.

Một mô tả “please review” gửi cùng PR dài hàng nghìn dòng khiến người nhận cần thời gian hiểu ngữ cảnh và dễ phải hỏi lại. **Nhỏ, nhất quán và có test** thường giúp review đáng tin hơn.

### 22.2. Tránh hai loại review giả

- **Approval rất nhanh nhưng không kiểm tra rủi ro:** chỉ số thời gian tốt, chất lượng giảm.
- **Review quá muộn và quá sâu với mọi thay đổi nhỏ:** pipeline kéo dài vì mọi thứ phải qua cùng chuyên gia.

Nhóm nên phân loại theo rủi ro và năng lực. Có thể cần review bắt buộc của chuyên gia cho thay đổi an toàn hoặc dữ liệu; không nên bỏ bước đó chỉ để tăng tốc độ.

### 22.3. CI là bàn giao bằng chứng máy kiểm chứng

CI có thể tự phát hiện lỗi compile, unit test, contract test và tích hợp ở một mức phù hợp ngay cả khi tác giả đã offline. Nhưng người nhận vẫn phải biết:

- Kết quả CI thuộc **commit nào**?
- Kiểm tra nào đã chạy, kiểm tra nào chưa?
- Test thất bại do lỗi mã, lỗi môi trường hay flaky test đang điều tra?
- Có migration hoặc cấu hình nào cần đồng bộ?
- Có thể khôi phục trạng thái an toàn nếu thay đổi ảnh hưởng production không?

CI **giảm vòng hỏi lại kỹ thuật**, không thay thế hoàn toàn quyết định nghiệp vụ hoặc trách nhiệm chất lượng.

## 23. Chất lượng giao tiếp: ngôn ngữ, mức rõ ràng và quyền được lên tiếng

Nhóm phân tán còn khác nhau về ngôn ngữ mẹ đẻ, cách diễn đạt, thói quen phản biện và khả năng tham gia cuộc gọi.

### 23.1. Viết để người khác hành động, không chỉ đọc cho biết

Một thông điệp tốt nên:

- Dùng tiêu đề thể hiện **hạng mục và yêu cầu**.
- Tách **Facts / Hypotheses / Decisions / Questions**.
- Tránh viết tắt nội bộ chưa được giải thích.
- Dùng ví dụ cụ thể thay cho “như hôm trước”, “cái API đó”.
- Ghi ngày và múi giờ khi cần thời hạn.
- Dẫn liên kết tới đúng nguồn thay vì yêu cầu người đọc tự tìm.
- Kết thúc bằng **next action và người nhận**.

Nếu người đọc không dùng tiếng Việt hoặc tiếng Anh là ngôn ngữ mẹ đẻ, một bản tóm tắt ngắn, câu rõ và ví dụ có cấu trúc thường dễ hiểu hơn một đoạn chat nhiều thành ngữ và ẩn ý.

### 23.2. An toàn tâm lý khi hỏi điều chưa rõ

Người nhận cần được phép nói **“Tôi chưa có đủ dữ liệu để làm bước này an toàn”**, thay vì buộc tự đoán để không bị đánh giá là chậm. Người gửi cũng cần được hỏi lại một cách tôn trọng, tập trung vào **thiếu thông tin nào**, không phán xét năng lực cá nhân.

Nếu thành viên ngại báo blocker, số liệu blocked time có thể đẹp giả trong khi rework tăng. **Văn hóa báo sự thật** là điều kiện để đo flow chính xác.

### 23.3. Tránh ưu tiên người ở cùng văn phòng

Một nhóm hybrid có thể quyết định quan trọng khi vài người tình cờ gặp nhau trong phòng rồi chỉ tóm tắt sơ sài trên chat. Những thành viên làm từ xa phải chờ hoặc bị loại khỏi khả năng phản biện.

Giải pháp không phải cấm nói trực tiếp, mà là:

- Ghi kết luận và tác động sau trao đổi.
- Mời đúng người có kiến thức/quyền nếu quyết định liên quan họ.
- Cho người vắng mặt cơ hội phản hồi trong khung hợp lý khi quyết định chưa khẩn.
- Phân biệt quyết định tạm với quyết định đã được xác nhận.

## 24. Bảo vệ giờ làm và phân phối bất tiện công bằng

Giảm chờ không nên được đánh đổi bằng việc **một nhóm phải luôn họp đêm còn nhóm khác luôn họp sáng thuận tiện**.

### 24.1. Các nguyên tắc thiết kế lịch

- **Dùng UTC hoặc múi giờ định danh** trong lịch mời; để hệ thống chuyển sang giờ địa phương.
- **Xem ngày nghỉ và DST** trước khi đặt lịch lặp.
- **Luân phiên giờ không thuận tiện** cho các cuộc trao đổi thật sự cần mọi khu vực, khi chính sách cho phép.
- **Giảm số người phải dự:** chỉ mời người có thông tin hoặc quyền quyết định thiết yếu.
- **Chuẩn bị và kết luận bằng văn bản** để người không dự vẫn hành động được.
- **Bảo vệ thời gian tập trung:** không coi async-first là quyền gửi tin nhắn khẩn liên tục.
- **Tách sự cố trực vận hành:** những trường hợp khẩn có quy trình, bù đắp và quyền hạn riêng.

### 24.2. “Công bằng” không nhất thiết nghĩa chia đều từng tuần

Giờ sinh hoạt, hoàn cảnh cá nhân, quy định lao động và nhu cầu vận hành khác nhau. Một thỏa thuận tốt cần được **thảo luận với người chịu ảnh hưởng** và xem lại dựa trên dữ liệu về thời gian họp ngoài giờ, tải trực và khả năng tham gia, thay vì áp dụng một phép chia cơ học.

### 24.3. Một phương án khi không có overlap ba khu vực

Thay vì ép cả Việt Nam, London và New York tham gia một buổi daily sync:

1. Gửi cập nhật mục tiêu, blocker và next action vào artifact trước khi kết thúc ca.
2. Dùng overlap **Việt Nam–London** cho quyết định cần hai nhóm này.
3. Dùng overlap **London–New York** cho quyết định của hai nhóm đó.
4. Các quyết định ảnh hưởng cả ba được viết với bối cảnh, phương án, hạn phản hồi hợp lý và cơ chế chốt rõ.
5. Tổ chức phiên toàn nhóm hiếm hơn khi thực sự cần và điều chỉnh giờ công bằng.

London không tự động trở thành “người phiên dịch thường trực” miễn phí giữa hai vùng; cần phân bổ năng lực phối hợp và lưu kết luận để mọi người tiếp cận.

## 25. Bàn giao trong vận hành và sự cố cần giao thức khác công việc bình thường

Một lỗi giao diện ít nghiêm trọng có thể chờ ca hôm sau; **sự cố production đang gây mất dữ liệu hoặc rủi ro bảo mật** có thể không được phép chờ theo chính sách bình thường.

### 25.1. Handoff trực sự cố cần ưu tiên tác động và quyền hành động

Một bàn giao on-call thường cần:

- Trạng thái sự cố: đang diễn ra, đã giảm tác động, đang quan sát hay đã phục hồi.
- Người dùng và hệ thống nào bị ảnh hưởng; điều gì đã được **xác minh**.
- Dòng thời gian UTC của các mốc quan trọng.
- Biện pháp giảm tác động đã thực hiện, giới hạn và rủi ro còn lại.
- Những giả thuyết chưa được xác nhận.
- Các dashboard, trace, công cụ và quyền truy cập an toàn có liên quan.
- Các hành động **không được thực hiện** nếu chưa có thẩm quyền.
- Người đang điều phối, người trực tiếp nhận và đường tăng cấp.
- Mốc cập nhật tiếp theo và tiêu chí khôi phục.

Một thông điệp “server đang chậm, ca sau theo dõi” không đủ để tiếp nhận trách nhiệm ứng phó an toàn.

### 25.2. Quy trình ứng phó không phải một chuỗi chat

Khi sự cố nghiêm trọng xảy ra, nhóm cần sử dụng **playbook ứng phó, thẩm quyền và chính sách thông tin** đã được tổ chức xác lập. Có thể cần phối hợp thời gian thực, không đợi phản hồi bất đồng bộ. Sau sự cố, nhóm xem lại nơi handoff hoặc cảnh báo thiếu ngữ cảnh và đưa cải tiến về backlog.

### 25.3. Không bàn giao bí mật qua kênh không phù hợp

Không gửi token, mật khẩu, khóa riêng, dữ liệu người dùng nhạy cảm hoặc log thô không kiểm soát vào tin nhắn chung. Hãy dùng hệ thống quản lý secrets, quyền hạn, liên kết có kiểm soát và quy trình lưu vết theo chính sách tổ chức.

## 26. Tình huống xuyên suốt: ba khu vực cùng xây luồng đăng ký buổi học

**Tình huống và số liệu trong phần này hoàn toàn giả định**, dùng để luyện cách phân tích phụ thuộc và thiết kế thử nghiệm cải tiến. Không phải mô tả đội thật hay quy trình bắt buộc của Agile.

### 26.1. Bối cảnh và mục tiêu

Một Scrum Team làm việc tại **TP. Hồ Chí Minh**, **London** và **New York** để xây chức năng hủy đăng ký cho nền tảng học lập trình.

**Product Goal:** học viên có thể tự quản lý lịch tham gia buổi hướng dẫn, không cần liên hệ bộ phận hỗ trợ cho các thao tác thông thường.

**Sprint Goal minh họa:** cho phép học viên hủy đăng ký hợp lệ và nhìn thấy trạng thái cuối cùng chính xác, đồng thời bảo toàn số chỗ và quyền truy cập.

Công việc gồm: làm rõ chính sách hủy, xử lý API, giao diện, kiểm thử gửi lặp và quyền, rồi chuẩn bị phát hành có kiểm soát.

### 26.2. Trạng thái ban đầu: chờ vì thiếu bối cảnh

Trong một khoảng quan sát, team ghi nhận:

| Tín hiệu giả định | Giá trị ban đầu | Giải thích |
|---|---:|---|
| PBI hoàn thành trong mẫu | 12 | Mẫu nhỏ; không đại diện cho mọi giai đoạn. |
| Cycle time trung vị | 8,5 ngày làm việc | Được tính theo chính sách trạng thái đã thống nhất. |
| Blocked time trung vị trên một PBI | 2,4 ngày làm việc | Nhiều blocker liên quan quyết định/handoff. |
| Số vòng yêu cầu bổ sung bối cảnh trên mỗi handoff | Trung bình 2,1 | Tính theo định nghĩa vòng làm rõ của nhóm. |
| PBI phải làm lại do hiểu sai quy tắc/hợp đồng | 4/12 | Cần xem mức ảnh hưởng của từng trường hợp. |
| Giờ họp ngoài khung làm việc bình thường | 6 giờ/người/tháng ở nhóm chịu ảnh hưởng | Guardrail sức khỏe và công bằng. |

Điều tra cho thấy nhiều handoff chỉ ghi “backend done” hoặc “need QA” mà thiếu commit, ví dụ, trạng thái quyết định và người nhận. Một số quyết định API nằm trong tin nhắn riêng. Team cũng có nhiều PBI đồng thời nên reviewer khó ưu tiên.

### 26.3. Giả thuyết cải tiến

> Nếu nhóm chuẩn hóa **thông tin tối thiểu để người nhận hành động**, ghi quyết định cạnh artifact, xác định next actor và giới hạn số hạng mục đang chờ review, thì số vòng hỏi lại và blocked time sẽ giảm mà không tăng làm việc ngoài giờ hoặc giảm chất lượng.

Đây là **giả thuyết có thể bị bác bỏ**, không phải kết luận đã đúng.

### 26.4. Chọn ba thay đổi nhỏ

| Thử nghiệm | Việc thực hiện | Owner/đầu mối | Bằng chứng đầu ra |
|---|---|---|---|
| **Handoff tối thiểu** | Dùng mục tiêu, trạng thái, test, blocker, next action cho PR/PBI chuyển người. | Một thành viên được team giao điều phối; người gửi thực hiện. | PR/PBI mẫu có đủ ngữ cảnh thực sự đọc được. |
| **Decision log gần PBI** | Ghi quy tắc hủy và xử lý trạng thái chờ; thông báo tới consumer API. | Người có thẩm quyền nghiệp vụ chốt, người điều phối cập nhật. | Quy tắc, ví dụ và hợp đồng liên kết nhất quán. |
| **Review queue rõ chính sách** | Chọn reviewer, thời điểm mong đợi, giảm PR quá lớn và giới hạn việc đang review. | Developers tự tổ chức theo năng lực. | Chính sách công bố, review có người nhận và CI evidence. |

Không cần lập thêm ba cuộc họp mỗi ngày. Team chọn một khoảng overlap **đúng người** cho vấn đề chưa giải quyết được bằng văn bản.

### 26.5. Ví dụ một lượt handoff qua các vùng

Tại cuối ca Việt Nam, kỹ sư cập nhật:

~~~text
PBI: CXL-42 / Hủy đăng ký và trả chỗ
Status: backend behavior implemented, integration not Done
PR: linked; CI: unit passed, integration scenario #3 still failing

Observed:
  On duplicate cancellation request, seat count is not duplicated in
  isolated tests; integration scenario shows an intermittent mismatch.

Hypothesis:
  Event consumer might process cancellation twice.
  NOT YET CONFIRMED.

Needed from London:
  Review idempotency and event contract;
  reproduce integration scenario with attached safe test data;
  annotate whether new contract is backward compatible.

Needed from Product Owner:
  Confirm UI state when result is unknown after timeout.

Next actor: London integration reviewer.
Owner: PBI coordination remains with Scrum Team.
Next check: overlap or next agreed working window.
~~~

Người London nhận được **bằng chứng, giả thuyết và việc cần làm**, không phải chỉ một lời nhờ “xem hộ”. Sau khi xử lý, họ cập nhật kết luận và chuyển phần có thể hành động tới New York hoặc quay về nhóm ban đầu theo chính sách. **Không chuyển một hạng mục đang có lỗi chưa rõ sang trạng thái Done** chỉ vì ca trước đã kết thúc.

### 26.6. Kết quả giả định sau giai đoạn thử

| Tín hiệu | Trước | Sau |
|---|---:|---:|
| PBI hoàn thành được quan sát | 12 | 15 |
| Cycle time trung vị (ngày làm việc) | 8,5 | 6,7 |
| Blocked time trung vị (ngày làm việc) | 2,4 | 1,3 |
| Vòng hỏi lại trung bình mỗi handoff | 2,1 | 0,9 |
| PBI làm lại do hiểu sai quy tắc/hợp đồng | 4/12 | 2/15 |
| Giờ họp ngoài khung làm việc bình thường của nhóm chịu ảnh hưởng (giờ/người/tháng) | 6 | 3 |

Các con số minh họa cho thấy xu hướng có thể tốt lên:

~~~text
Mức giảm blocked-time median = 2,4 - 1,3 = 1,1 ngày làm việc

Mức giảm tương đối so với baseline =
    (2,4 - 1,3) / 2,4 × 100% ≈ 45,8%
~~~

**Không thể từ bảng này kết luận chắc rằng các thỏa thuận handoff gây ra toàn bộ cải thiện.** Hai mẫu nhỏ và có thể khác nhau về kích thước PBI, nhân sự, kiến trúc, ngày nghỉ, tải sự cố hoặc mức phức tạp. Cần xem dữ liệu theo thời gian và thu phản hồi định tính.

### 26.7. Kiểm tra guardrails

Team hỏi:

- Các kịch bản phân quyền và gửi lặp có đạt tiêu chuẩn chất lượng không?
- Số lỗi tích hợp quan trọng hoặc sự cố sau release có tăng không?
- Các giờ họp bất tiện có giảm ở **mọi vùng** hay chỉ bị chuyển từ người này sang người khác?
- Người nhận có cảm thấy đủ ngữ cảnh, hay chỉ đang điền template cho đủ?
- Quyết định nghiệp vụ có được cập nhật ở đúng nguồn và đến đúng consumer?
- Cycle time giảm có giúp học viên nhận phần giá trị ổn định sớm hơn không?

Ví dụ, nếu blocked time giảm nhưng lỗi dữ liệu tăng, không thể coi cải tiến thành công toàn diện.

### 26.8. Kết luận và thử nghiệm tiếp

Giả sử dữ liệu và phản hồi ủng hộ việc giữ handoff tối thiểu, nhưng người London báo họ trở thành đầu mối quyết định cho quá nhiều PBI. Team nên:

1. Giữ nguyên những phần bàn giao đã chứng minh hữu ích.
2. Mở rộng khả năng review hoặc làm rõ quyền quyết định để giảm phụ thuộc một người.
3. Giới hạn số hạng mục đang chờ chuyên gia.
4. Kiểm tra lại blocked time và tải làm việc sau một cửa sổ phù hợp.

Mục tiêu của vòng cải tiến không phải có template hoàn hảo, mà là **hệ thống cộng tác tốt hơn một cách có thể kiểm chứng và bền vững**.

## 27. Một lộ trình triển khai trong nhóm phân tán

Các bước sau là **gợi ý cải tiến**, không phải quy trình bắt buộc của Scrum, Kanban hay XP.

### Bước 1 — Chọn một loại chờ có ảnh hưởng lớn

Đừng giải quyết tất cả cuộc họp, PR và dependency cùng lúc. Bắt đầu từ một nút thắt như “PBI thường chờ quyết định nghiệp vụ qua hai ca”.

Thu vài ví dụ thật: câu hỏi ban đầu, các lượt hỏi lại, thời điểm và hậu quả.

### Bước 2 — Vẽ đường đi của thông tin và quyền quyết định

Ai phát hiện vấn đề? Ai có dữ liệu? Ai có thể trả lời? Ai có quyền quyết định? Người nào thực hiện tiếp? Có đường thay thế khi vắng mặt không?

Nếu mọi quyết định đều phải chờ một người, cần xử lý **nút thắt thẩm quyền**; thêm chat bot hay mẫu ticket không đủ.

### Bước 3 — Xác định giờ làm, overlap và loại thông tin cần đồng bộ

Dùng múi giờ định danh và ngày cụ thể. Bảo vệ giờ nghỉ, ghi chính sách khẩn tách biệt và chuẩn bị câu hỏi trước phiên overlap.

### Bước 4 — Chọn một mẫu bàn giao tối thiểu

Mỗi handoff trong phạm vi thử có **mục tiêu, trạng thái, bằng chứng, quyết định/giả định, next action, người nhận và mốc**. Không cần nhân bản thông tin đã có trong hệ thống khác; liên kết tới nguồn có thẩm quyền.

### Bước 5 — Làm rõ chính sách flow

Xác định thời điểm kéo việc, trạng thái blocked, reviewer nhận, cách tăng cấp và khi nào work item được xem là Done. Tránh mở thêm hàng loạt hạng mục chỉ vì một PBI đang chờ.

### Bước 6 — Tạo vòng phản hồi kỹ thuật nhanh

Đối với sự phụ thuộc API, thử contract tests và tích hợp thường xuyên. Với bug khó tái hiện, yêu cầu ví dụ, phiên bản và kết quả CI. Đối với rủi ro cao, giữ kiểm tra và quyền quyết định bắt buộc.

### Bước 7 — Đo cả chờ, chất lượng và tải con người

Chọn blocked time hoặc time to actionable decision làm chỉ số chính; bổ sung số vòng hỏi lại, rework và guardrails như lỗi sau merge, giờ họp ngoài giờ, tải review. Thu baseline nhất quán trước khi so sánh.

### Bước 8 — Kiểm tra, thích ứng và loại bỏ thủ tục thừa

Sau cửa sổ có đủ dữ liệu, hỏi:

- Phần nào giảm chờ thật?
- Phần nào chỉ khiến mọi người điền biểu mẫu nhiều hơn?
- Có ai bị quá tải khi làm cầu nối giữa các vùng?
- Có thể mở rộng thực hành nào, cần bỏ hoặc sửa phần nào?

Một vòng cải tiến thành công có thể làm **ít họp, ít handoff không cần thiết và ít dữ liệu trùng lặp hơn**, không nhất thiết tăng số công cụ đang dùng.

## 28. Bài tập thực hành: sửa một bàn giao gây chờ hai ca

Giả sử team làm việc tại Việt Nam và Đức, một số thành viên hỗ trợ từ Hoa Kỳ. Một kỹ sư gửi:

> “UI chưa ổn, backend chắc đổi rồi. Ngày mai ai test lại nhé.”

### Bài tập 1 — Xác định thông tin còn thiếu

Hãy nêu ít nhất sáu thông tin người nhận cần trước khi hành động.

**Gợi ý:** PBI và mục tiêu, phiên bản/PR, hành vi hiện tại và kỳ vọng, bước tái hiện, dữ liệu/môi trường thử, test đã chạy, quyết định API, người nhận, việc tiếp theo, mốc phản hồi và mức độ rủi ro.

### Bài tập 2 — Viết lại handoff trong 10–12 dòng

**Gợi ý mẫu:**

~~~text
PBI-88: Hiển thị trạng thái hủy đăng ký
Goal: không báo thành công khi API chưa xác nhận giao dịch
Current: UI hiển thị CONFIRMED cho PENDING_CONFIRMATION
Scope: frontend PR #152, backend contract v3 trong liên kết issue
Reproduce: môi trường test, tài khoản giả, request timeout theo test #7
Expected: hiển thị đang xác minh, không khẳng định hủy thành công
Checked: unit xanh; integration test #7 thất bại
Open decision: wording thông báo cần PO chốt
Next actor: reviewer frontend được chỉ định
Next action: cập nhật UI, chạy integration test và ghi kết quả vào PBI
Owner: người điều phối PBI; mốc check có ngày và múi giờ
~~~

Không cần đưa thông tin nhạy cảm hoặc hàng trăm dòng log trực tiếp vào thông điệp.

### Bài tập 3 — Chọn sync hay async

Một lỗi CSS nhỏ với ví dụ rõ có cần toàn bộ ba khu vực họp cùng nhau không?

**Gợi ý:** thường không. Một bình luận/PR có bằng chứng đủ và next actor thích hợp hơn. Nếu có mâu thuẫn quy tắc nghiệp vụ ảnh hưởng nhiều nhóm, nên chuẩn bị lựa chọn trước một cuộc trao đổi ngắn với đúng người có quyền quyết định.

### Bài tập 4 — Đọc hai cách tính thời gian

Một PBI có cycle time **8 ngày làm việc**, bị chặn **3 ngày làm việc** vì ba lượt hỏi lại. Tính tỷ lệ chờ:

~~~text
3 / 8 × 100% = 37,5%
~~~

Nếu nhóm làm lại template, blocked time còn **1,5 ngày làm việc** với cycle time **6 ngày làm việc**, tỷ lệ mới là:

~~~text
1,5 / 6 × 100% = 25%
~~~

Nhận xét đúng là **tỷ lệ chờ giảm 12,5 điểm phần trăm** trong hai ví dụ. Nhưng cần thêm dữ liệu để biết cải tiến có hiệu quả ổn định trong toàn bộ dòng công việc.

### Bài tập 5 — Xem tác dụng phụ

Giả sử số vòng hỏi lại giảm, nhưng người phụ trách London phải tham gia họp ngoài giờ thêm bốn tối mỗi tháng. Team nên làm gì?

**Gợi ý:** xem lại trách nhiệm làm cầu nối, kênh quyết định, người thay thế và giờ họp luân phiên; kiểm tra liệu việc giảm chờ có thể duy trì bằng tài liệu, phân quyền hoặc overlap ngắn hơn. Đừng tuyên bố cải tiến thành công nếu giá trị đạt được bằng **tải ngoài giờ không bền vững**.

### Bài tập 6 — Chọn tiêu chí Done cho lát giá trị

Backend ở một khu vực nói “phần tôi đã xong”, trong khi frontend hiển thị trạng thái đăng ký sai. Có thể coi user story Done không?

**Gợi ý:** không, nếu hành vi tích hợp và chất lượng chưa đạt Definition of Done áp dụng. Có thể ghi phần backend đã hoàn thành như tiến độ kỹ thuật, nhưng phải minh bạch phần giá trị còn thiếu.

## 29. Những phản mẫu phổ biến

| Phản mẫu | Vì sao gây chờ hoặc rủi ro? | Thực hành thay thế |
|---|---|---|
| **“Ai rảnh thì xem nhé.”** | Không có next actor, trách nhiệm trôi. | Chỉ định người hoặc nhóm nhận với cơ chế xác nhận và thay thế. |
| **“Backend xong, frontend tự hiểu.”** | Hợp đồng và trạng thái chưa được làm rõ. | Ghi ví dụ, quyết định, test và hợp đồng API. |
| **Thông tin nằm trong DM cá nhân.** | Người vắng mặt không biết quyết định. | Tóm tắt và liên kết tại artifact có thẩm quyền. |
| **Mọi tin nhắn đều khẩn.** | Tăng gián đoạn và bỏ qua cảnh báo thật. | Phân loại thường, blocked và incident. |
| **Cả đội phải họp ở một giờ bất tiện cố định.** | Một nhóm chịu tải ngoài giờ kéo dài. | Async trước, overlap theo cặp, luân phiên phiên cần toàn đội. |
| **Đếm giờ trả lời chat là năng suất.** | Khuyến khích câu trả lời rỗng và online liên tục. | Đo actionable response, outcome và guardrails. |
| **Bàn giao dài nhưng không có câu hỏi cụ thể.** | Người đọc mất thời gian tìm bước tiếp. | Tóm tắt mục tiêu, blocker, next action ở đầu. |
| **Mỗi nhóm cập nhật một bản quy tắc riêng.** | Quyết định mâu thuẫn giữa vùng. | Một nguồn sự thật và liên kết tới kết luận mới. |
| **Tạo thêm handoff để mọi ca đều có việc.** | Tăng chuyển ngữ cảnh và lỗi. | Chỉ chuyển khi việc đủ độc lập và người nhận có năng lực. |
| **Follow-the-sun nghĩa là một ticket bắt buộc qua ba khu vực.** | Chuyển tay không cần thiết, mất tri thức. | Giữ owner ổn định, phân chia theo phụ thuộc hợp lý. |
| **Dùng UTC offset cố định cho cả năm.** | Lỗi lịch khi vùng khác đổi giờ mùa hè. | Dùng định danh vùng và ngày, kiểm tra DST. |
| **PR lớn chờ chuyên gia duy nhất.** | Queue dài và rủi ro thiếu năng lực thay thế. | Chia nhỏ thay đổi, chia sẻ tri thức, chính sách review theo rủi ro. |
| **Đưa vào Waiting để loại khỏi WIP.** | Che thời gian chờ, báo flow đẹp giả. | Định nghĩa WIP, cycle time và blocked time nhất quán. |
| **Coi mọi câu hỏi lại là lỗi của người gửi.** | Người nhận ngại hỏi, tự đoán dẫn tới lỗi. | Khuyến khích làm rõ cần thiết, cải tiến mẫu từ câu hỏi lặp. |
| **Bỏ kiểm thử để giảm thời gian bàn giao.** | Lỗi tích hợp và dữ liệu đi tới người dùng. | CI, contract tests và DoD đáng tin. |
| **Báo “Done” theo từng bộ phận.** | Increment cuối không thể dùng được. | Tách tiến độ kỹ thuật khỏi trạng thái Done của phần sản phẩm. |
| **Quên quyền riêng tư khi gửi log.** | Lộ dữ liệu hoặc secrets trên kênh không phù hợp. | Liên kết dữ liệu đã bảo vệ với quyền truy cập phù hợp. |
| **Không ghi quyết định sau cuộc gọi.** | Người không dự lại hỏi, vòng chờ tái diễn. | Cập nhật PBI/ADR/hợp đồng và thông báo người liên quan. |
| **Trả lời quá nhanh bằng phỏng đoán.** | Rework và rủi ro chất lượng tăng. | Ghi rõ giả thuyết, người có quyền xác nhận và bước kiểm chứng. |
| **Cải tiến bằng thêm họp mà không đo kết quả.** | Mọi người bận hơn, chờ vẫn dài. | Đặt baseline, thử thay đổi nhỏ, xem flow và tải con người. |

## 30. Checklist trước khi chuyển việc sang người khác múi giờ

### Mục tiêu và trạng thái

- [ ] Hạng mục có mục tiêu người dùng hoặc kết quả kỹ thuật rõ?
- [ ] Đã phân biệt phần xong, phần chưa xong và phần đang bị chặn?
- [ ] Có ghi rõ môi trường, phiên bản, PR/commit và phạm vi thay đổi?
- [ ] Có nguồn chuẩn cho acceptance criteria, hợp đồng API và quyết định liên quan?

### Ngữ cảnh để hành động

- [ ] Người nhận có đủ bước tái hiện và dữ liệu thử **an toàn**?
- [ ] Đã ghi điều quan sát, điều suy đoán và điều đã được quyết định?
- [ ] Test đã chạy, kết quả CI và giới hạn kiểm chứng rõ?
- [ ] Có một bước tiếp theo có thể hành động và tiêu chí để biết xong?
- [ ] Người nhận có thể thực hiện bước đó **khi người gửi offline**?

### Quyền và thời điểm

- [ ] Có next actor cụ thể, được thông báo và có đường xác nhận nhận việc?
- [ ] Người có thẩm quyền quyết định nghiệp vụ/kỹ thuật đã rõ?
- [ ] Nếu người nhận vắng hoặc không có quyền, có fallback phù hợp?
- [ ] Mốc phản hồi có ngày, múi giờ và mức ưu tiên thực tế?
- [ ] Đã phân biệt yêu cầu thường với sự cố cần ứng phó khẩn?
- [ ] Có tôn trọng giờ làm, ngày nghỉ và DST của người nhận?

### Flow, chất lượng và bảo mật

- [ ] Handoff không tạo thêm chuyển tay khi không cần thiết?
- [ ] Work item bị chặn vẫn hiển thị trong flow và có mốc xem lại?
- [ ] Không hạ Definition of Done hoặc bỏ kiểm tra bắt buộc để kịp ca?
- [ ] Thông tin nhạy cảm, secrets và dữ liệu cá nhân được bảo vệ?
- [ ] Sau khi quyết định, artifact và các consumer liên quan được cập nhật?

## 31. Checklist đánh giá một cải tiến của nhóm phân tán

- [ ] Vấn đề chờ cụ thể và nguồn chứng cứ ban đầu đã được xác định?
- [ ] Đã tách chờ do **múi giờ, thiếu thông tin, thiếu thẩm quyền và thiếu năng lực**?
- [ ] Nhóm có giả thuyết vì sao thay đổi đề xuất sẽ giúp?
- [ ] Có phạm vi thử đủ nhỏ, owner, người thực hiện và mốc Check?
- [ ] Có định nghĩa thời gian chờ rõ, nhất quán giữa trước và sau?
- [ ] Có xem số vòng hỏi lại, blocked time, cycle time và work item age khi phù hợp?
- [ ] Có guardrails cho lỗi tích hợp, dữ liệu, bảo mật và Definition of Done?
- [ ] Có xem thời gian họp ngoài giờ, tải review, tập trung và sức khỏe đội?
- [ ] Kết quả có được đọc cùng mẫu, biến động, ngày nghỉ và rủi ro thay đổi?
- [ ] Nếu dữ liệu trái kỳ vọng, nhóm có thể **sửa hoặc dừng thí nghiệm** mà không đổ lỗi?
- [ ] Những bước mới có thực sự giúp người nhận hành động, hay chỉ tăng tài liệu?
- [ ] Có quyết định duy trì, thay đổi hoặc bỏ cách làm và mốc xem lại tiếp theo?

Checklist giúp thảo luận và kiểm tra thực tế, **không phải quy trình chứng nhận một đội Agile phân tán**. Nếu câu trả lời là “chưa”, hãy chọn một cải tiến nhỏ rồi kiểm tra bằng chứng thay vì bổ sung nhiều nghi thức.

## 32. Kết luận

Trong nhóm phân tán, **múi giờ làm lộ rõ chi phí của những câu hỏi thiếu bối cảnh và những quyết định chưa có người chịu trách nhiệm**. Một thông điệp không có mục tiêu, bằng chứng, người nhận và bước tiếp theo có thể khiến một lỗi nhỏ kéo dài nhiều ngày, dù thời gian sửa kỹ thuật thực tế ngắn.

Để giảm chờ bền vững, nhóm cần **thiết kế giao tiếp bất đồng bộ có chủ đích, dùng giờ chồng lấn cho quyết định thật sự cần đồng bộ, bàn giao đủ thông tin để người nhận tiếp tục an toàn, minh bạch owner/decision maker và giữ các nguồn sự thật nhất quán**. Scrum hỗ trợ mục tiêu và kiểm tra–thích ứng; Kanban giúp nhìn hàng chờ và quản lý WIP; XP giúp tạo phản hồi kỹ thuật sớm; những thực hành vận hành bảo vệ chất lượng khi phần mềm tới người dùng.

Kết quả cần hướng tới không phải mọi người trả lời tin nhắn ngay lập tức hoặc mọi múi giờ đều có người đang mở ticket. **Đó là công việc ít bị chặn vô ích hơn, quyết định đúng đến sớm hơn, Increment có giá trị được giao an toàn hơn và các thành viên có thể phối hợp hiệu quả mà vẫn duy trì nhịp làm việc lành mạnh.**
