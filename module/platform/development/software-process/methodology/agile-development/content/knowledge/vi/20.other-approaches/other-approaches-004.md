# DSDM: ưu tiên MoSCoW, timebox và cộng tác nghiệp vụ

## 1. DSDM giải quyết bài toán gì trong phát triển Agile?

Một nhóm phát triển nền tảng học trực tuyến có tám tuần trước ngày khai giảng. Bộ phận kinh doanh muốn có luồng ghi danh, bộ phận đào tạo muốn hiển thị tiến độ học, người học muốn thông báo rõ quyền truy cập, còn giảng viên đề nghị dashboard phân tích. Nếu nhóm nhận tất cả đề xuất như nhau, họ có thể hoàn thành rất nhiều màn hình nhưng **không bảo đảm học viên ghi danh và bắt đầu học an toàn vào ngày khai giảng**.

**DSDM (Dynamic Systems Development Method)** là một cách tiếp cận Agile theo hướng **dự án và bàn giao giải pháp**, được phát triển từ thập niên 1990 và về sau được diễn đạt qua **DSDM Agile Project Framework**. DSDM nhấn mạnh mục tiêu kinh doanh, thời hạn, cộng tác liên tục với người nghiệp vụ và chất lượng giải pháp. Nó đặc biệt hữu ích khi tổ chức cần quản lý một mốc bàn giao có ý nghĩa, nhiều stakeholder hoặc ràng buộc nguồn lực, trong khi yêu cầu chi tiết vẫn còn bất định.

Ba cơ chế nổi bật:

1. **MoSCoW:** phân loại nhu cầu theo mức độ thiết yếu cho mục tiêu của một khoảng bàn giao cụ thể.
2. **Timebox:** cố định một khoảng thời gian ngắn có mục tiêu và cách kết thúc rõ, điều chỉnh nội dung theo ưu tiên thay vì kéo dài vô hạn.
3. **Cộng tác nghiệp vụ chủ động:** người hiểu giá trị, quy tắc và người dùng tham gia ra quyết định thường xuyên, không chỉ gửi tài liệu lúc bắt đầu và nghiệm thu vào cuối.

Trong module **AGILE_DEVELOPMENT**, DSDM là một cách bổ sung cho những kiến thức về user story, Product Backlog, Scrum, Kanban, XP và đo lường luồng công việc. Không cần cho rằng mọi nhóm Agile đều phải sử dụng DSDM, hoặc DSDM chỉ là tên gọi khác của Scrum.

> **Ý tưởng cốt lõi:** Khi ngày bàn giao và tiêu chuẩn chất lượng quan trọng, hãy bảo vệ **kết quả tối thiểu thiết yếu**, làm việc sát với đại diện nghiệp vụ và linh hoạt ở **những phần có thể hoãn**, thay vì tuyên bố mọi tính năng đều bắt buộc.

## 2. DSDM đứng ở đâu trong bức tranh các phương pháp Agile?

Agile không phải một quy trình duy nhất. Những cách tiếp cận phổ biến khác nhau về trọng tâm:

| Cách tiếp cận | Nhấn mạnh | Điều có thể học để hỗ trợ DSDM |
| --- | --- | --- |
| **DSDM** | Quản trị bàn giao theo nhu cầu kinh doanh; timebox, MoSCoW, vai trò nghiệp vụ | Phân loại phạm vi theo mục tiêu, trao quyền ra quyết định đúng lúc |
| **Scrum** | Thực nghiệm với Sprint, ba accountabilities, ba artifacts và các commitments | Kiểm tra Increment, Product Goal, Sprint Goal, Definition of Done |
| **Kanban** | Minh bạch luồng công việc, giới hạn WIP, chính sách kéo và đo flow | Phát hiện thời gian chờ, điểm nghẽn, năng lực thực hiện |
| **Extreme Programming (XP)** | Thực hành kỹ thuật để thay đổi an toàn | TDD, CI, refactoring, kiểm thử và tích hợp thường xuyên |
| **Lean** | Tối đa hóa giá trị và học hỏi, giảm lãng phí trên toàn dòng giá trị | Giảm lô lớn, chờ đợi, handoff và việc làm dở |

DSDM có framework, vai trò và cách làm riêng. Có thể mượn kỹ thuật từ nơi khác khi hợp lý, nhưng **không tự đồng nhất vai trò Business Ambassador của DSDM với Product Owner trong Scrum**, hoặc cho rằng timebox nào cũng là một Sprint đúng nghĩa Scrum.

### Tám nguyên tắc DSDM – bối cảnh cho ba kỹ thuật chính

DSDM thường được mô tả qua tám nguyên tắc:

| Nguyên tắc | Ý nghĩa thực hành |
| --- | --- |
| **Focus on the business need** – Tập trung nhu cầu kinh doanh | Kết quả cần đạt quan trọng hơn số tính năng |
| **Deliver on time** – Bàn giao đúng thời điểm | Quản lý thời hạn bằng ưu tiên, phạm vi và năng lực thật |
| **Collaborate** – Cộng tác | Người nghiệp vụ và kỹ thuật cùng ra quyết định trong quá trình làm |
| **Never compromise quality** – Không thỏa hiệp chất lượng | Bảo vệ các tiêu chí chất lượng đã thống nhất |
| **Build incrementally from firm foundations** – Xây tăng dần từ nền tảng vững | Làm rõ đủ mục tiêu, kiến trúc/rủi ro quan trọng rồi bàn giao từng lát |
| **Develop iteratively** – Phát triển lặp | Điều chỉnh giải pháp qua phản hồi, prototype và kiểm chứng |
| **Communicate continuously and clearly** – Giao tiếp liên tục, rõ ràng | Tránh chờ ký duyệt hoặc truyền đạt qua nhiều lớp |
| **Demonstrate control** – Thể hiện khả năng kiểm soát | Minh bạch tiến độ, rủi ro, quyết định và chất lượng |

“Nền tảng vững” **không có nghĩa thiết kế toàn bộ sản phẩm trước khi code**. Nhóm cần đủ hiểu về mục tiêu, các ràng buộc và rủi ro nền tảng để có thể xây những increment đáng tin cậy, rồi tiếp tục khám phá chi tiết.

## 3. DSDM nhìn phạm vi, thời gian, chi phí và chất lượng như thế nào?

Trong nhiều dự án truyền thống, người ta cố cố định toàn bộ tính năng rồi để thời gian, ngân sách hoặc chất lượng chịu áp lực khi có thay đổi. DSDM đề cao **timeboxing** và **MoSCoW** để cố gắng giữ thời gian, nguồn lực và mức chất lượng đã thống nhất, trong khi **cho phép điều chỉnh phạm vi tính năng theo mức cần thiết**.

| Yếu tố | Cách xử lý trong một dự án DSDM điển hình | Lưu ý thực tế |
| --- | --- | --- |
| **Thời gian** | Timebox và mốc bàn giao được quản lý chặt | Mốc phải khả thi theo năng lực, không chỉ là ngày tuyên bố |
| **Chi phí/nguồn lực** | Nhóm, ngân sách và năng lực được dự tính trong giới hạn | Không được giả định có thể tăng người ngay lập tức để cứu deadline |
| **Chất lượng** | Thước đo chất lượng được thống nhất và không cắt tùy tiện | Bảo mật, dữ liệu, kiểm thử bắt buộc và khả năng vận hành cần được bảo vệ |
| **Phạm vi tính năng** | Xếp MoSCoW để có phần thiết yếu và phần có thể hoãn | Must Have phải thực sự tối thiểu, tránh không còn chỗ linh hoạt |

Điều này **không** có nghĩa có thể bỏ bất kỳ chức năng nào để báo “đúng hạn”. Nếu thiếu một Must Have khiến giải pháp không thể sử dụng hợp lệ, nhóm phải báo rủi ro, thay đổi chiến lược hoặc thương lượng lại ràng buộc bằng quyết định có thẩm quyền. Không được gọi một bản không an toàn là “đã đạt Must”.

### Ví dụ về lựa chọn phạm vi

Ngày khai giảng đã xác định, mục tiêu tối thiểu là **học viên được ghi danh hợp lệ và mở được bài đầu**. Một dashboard thống kê nâng cao có thể rất hữu ích nhưng nếu hoãn mà mục tiêu trên vẫn đạt, dashboard chưa chắc là Must Have cho mốc này.

Ngược lại, **kiểm soát quyền học phía máy chủ** không nên bị đẩy sang Could Have chỉ vì giao diện đã chạy. Nó là một điều kiện chất lượng và an toàn của sản phẩm; nếu hành vi bảo vệ quyền là bắt buộc để giải pháp hợp lệ thì nó phải được bảo đảm trong phạm vi thiết yếu/tiêu chuẩn chất lượng.

## 4. MoSCoW: bốn mức ưu tiên có ý nghĩa thực tế

**MoSCoW** là cách nhóm và stakeholder cùng phân loại nhu cầu trong **một mục tiêu hoặc khoảng bàn giao được xác định rõ**. Các chữ “o” chỉ giúp dễ đọc từ viết tắt; bốn nhóm chính là Must, Should, Could, Won't.

| Nhóm | Câu hỏi kiểm tra | Ý nghĩa với mốc đang xem xét |
| --- | --- | --- |
| **M – Must Have** | Nếu không có, giải pháp còn dùng được, an toàn và đạt mục đích tối thiểu không? | **Bắt buộc** để mốc bàn giao được coi là khả thi/đúng mục tiêu |
| **S – Should Have** | Rất quan trọng, nhưng có giải pháp tạm chấp nhận được nếu hoãn không? | Nên có nếu năng lực cho phép; bỏ có ảnh hưởng đáng kể nhưng không làm mất tính khả thi cốt lõi |
| **C – Could Have** | Có ích nhưng tác động của việc bỏ ở mốc này tương đối nhỏ? | Chỉ thực hiện khi còn năng lực, là vùng linh hoạt/contingency |
| **W – Won't Have this time** | Có đồng thuận rằng không nằm trong phạm vi lần bàn giao này? | Loại khỏi cam kết hiện tại; có thể được xem xét lại ở mốc khác |

### 4.1. Must Have không phải “stakeholder muốn nhất”

Một hạng mục thuộc Must Have khi **nếu thiếu nó, mục tiêu bàn giao không còn khả thi hoặc không đáp ứng ràng buộc bắt buộc**. Ví dụ:

- Người học không thể ghi danh hoặc được cấp quyền đúng quy tắc.
- Một cơ chế tuân thủ pháp lý/bảo mật bắt buộc còn thiếu.
- Hệ thống không thể mở bài đầu cho người dùng hợp lệ vào thời điểm bàn giao.

“Giám đốc rất thích dashboard này” **không đủ** để khiến dashboard trở thành Must. Cần hỏi điều gì thật sự xảy ra nếu tạm hoãn và có phương án thay thế hợp lệ hay không.

### 4.2. Should Have quan trọng nhưng có thể sống thiếu tạm thời

Ví dụ: học viên nhận email xác nhận ghi danh với nội dung đầy đủ, trong khi giao diện đã hiển thị trạng thái và bộ phận hỗ trợ có thể tra cứu khi cần. Email có thể là Should nếu thiếu nó **không làm hỏng tính hợp lệ của việc ghi danh**, vẫn bảo đảm thông báo cần thiết bằng phương án khác. Nếu hợp đồng hoặc chính sách yêu cầu email bắt buộc thì phải phân loại lại.

Should **không** đồng nghĩa công việc không cần thiết. Nó là ứng viên quan trọng, thường được ưu tiên sau Must khi còn năng lực và không xuất hiện rủi ro mới.

### 4.3. Could Have tạo vùng thích ứng

Ví dụ: thêm bộ lọc màu sắc cho danh sách khóa, huy hiệu chào mừng hoặc hiệu ứng giao diện không ảnh hưởng khả năng ghi danh. Những việc này có thể tạo trải nghiệm tốt hơn nhưng không phải điều kiện của mốc khai giảng.

Could thường là nơi điều chỉnh phạm vi khi timebox gặp vấn đề. **Bỏ Could đã được dự kiến trước** khác với bỏ kiểm thử hoặc bỏ Must ở phút cuối.

### 4.4. Won't Have this time là quyết định phạm vi, không phải bác bỏ mãi mãi

Ví dụ: “Gợi ý khóa học bằng AI sẽ **không làm trong đợt khai giảng này**; xem lại khi có dữ liệu nhu cầu và chính sách dữ liệu phù hợp”. Nói rõ Won't giúp người liên quan không kỳ vọng một ý tưởng sẽ âm thầm xuất hiện vào cuối thời hạn.

Won't là một quyết định có phạm vi thời gian/mốc cụ thể. Ở mốc sau, có thể xét lại bằng chứng và ưu tiên, **không có cam kết tự động** rằng mọi Won't sẽ được triển khai.

## 5. Cách đặt câu hỏi để phân loại MoSCoW có căn cứ

Một cách thực hành là yêu cầu mọi đề xuất trả lời những câu hỏi sau, thay vì mỗi phòng ban tự dán nhãn “Must”:

1. **Mục tiêu lần bàn giao này là gì?** Ai cần giải pháp và kết quả tối thiểu là gì?
2. **Nếu thiếu hạng mục, chuyện gì xảy ra?** Giải pháp không dùng được, vi phạm nghĩa vụ, hay chỉ giảm tiện lợi?
3. **Có phương án thay thế tạm thời hợp lệ không?** Phương án có rủi ro, chi phí vận hành hoặc hạn chế nào?
4. **Phụ thuộc nào khiến hạng mục thiết yếu?** Một Should có thật sự là tiền điều kiện cho Must không?
5. **Chất lượng bắt buộc là gì?** Không được biến việc bỏ một kiểm tra quan trọng thành “điều chỉnh scope”.
6. **Bằng chứng về giá trị đến từ đâu?** Phản hồi người dùng, hợp đồng, dữ liệu hay chỉ ý kiến?
7. **Cần bao nhiêu năng lực và bất định?** Có đủ thông tin để thực hiện trong timebox không?
8. **Ai có quyền xác nhận ưu tiên?** Quyết định cần được ghi rõ và truyền đạt nhất quán.

### Ví dụ phân biệt giá trị với mức bắt buộc

| Nhu cầu | Mức MoSCoW minh họa cho đợt khai giảng | Giải thích |
| --- | --- | --- |
| Học viên đăng nhập và ghi danh khóa miễn phí đang mở | **Must** | Không có thì chưa đạt hành trình tối thiểu |
| Học viên được cấp đúng quyền mở bài đầu | **Must** | Cần để chức năng dùng được và an toàn |
| Tránh tạo hai đăng ký hiệu lực khi gửi lặp | **Must / chất lượng bắt buộc** | Ngăn dữ liệu sai và quyền học không nhất quán |
| Email xác nhận với mẫu trình bày nâng cao | **Should** nếu có kênh thông báo hợp lệ khác | Cải thiện trải nghiệm, nhưng có thể tạm hoãn trong giả định này |
| Bộ lọc yêu thích và sắp xếp tùy chỉnh | **Could** | Hữu ích nhưng chưa ảnh hưởng hành trình tối thiểu |
| Hệ thống gợi ý khóa học cá nhân hóa bằng AI | **Won't this time** | Chưa cần cho mốc này; còn rủi ro dữ liệu và giả thuyết giá trị |

Đây là **phân loại giả định để học phương pháp**. Trong dự án thật, quy tắc nghiệp vụ, đối tượng học viên, nghĩa vụ pháp lý và khả năng thay thế có thể khiến một mục phải đổi nhóm.

### MoSCoW là ưu tiên tương đối, không phải độ khẩn cấp của một lỗi riêng lẻ

Một bug bảo mật có thể cần xử lý ngay theo quy trình sự cố, bất kể bảng phân loại tính năng đã chuẩn bị trước. Một chức năng Could có thể trở thành Must khi phát hiện phụ thuộc thực sự hoặc ràng buộc mới. Khi có bằng chứng, nhóm cần **tái đánh giá minh bạch**, không cố giữ nhãn cũ để hợp báo cáo.

## 6. Tránh “mọi thứ đều Must” bằng giới hạn năng lực và sự linh hoạt

MoSCoW chỉ hữu ích khi tập Must **đủ nhỏ để có thể thực hiện với mức tin cậy hợp lý**, đồng thời còn chỗ để điều chỉnh. Nếu toàn bộ backlog bị gán Must, nhóm không còn biến số để bảo vệ thời gian và chất lượng.

Một số hướng dẫn DSDM dùng **quy tắc kinh nghiệm** về mức công sức của Must và vùng contingency cho Could. Tuy nhiên, **không nên xem một tỷ lệ phần trăm đơn lẻ là định luật** áp dụng cho mọi nhóm. Tỷ trọng phù hợp phụ thuộc dữ liệu năng lực, độ khó, phụ thuộc, thời gian và mức rủi ro; một Must lớn, chưa rõ không trở nên khả thi chỉ nhờ chia số đẹp.

### Ví dụ về phân bổ năng lực minh họa

Giả sử sau khi tính thời gian làm rõ, tích hợp, kiểm thử và các gián đoạn dự kiến, một timebox có **20 đơn vị công sức tương đối** theo cách đánh giá nội bộ:

| Mức | Các hạng mục ứng viên | Tổng công sức minh họa |
| --- | --- | ---: |
| **Must** | Ghi danh hợp lệ, cấp quyền, chống đăng ký trùng | 12 |
| **Should** | Thông báo trạng thái nâng cao, cải thiện xử lý lỗi | 4 |
| **Could** | Bộ lọc giao diện, tùy chọn hiển thị | 4 |
| **Won't** | Gợi ý khóa bằng AI, báo cáo phân tích nâng cao | Ngoài timebox |
| **Tổng được xem xét** | Must + Should + Could | **20** |

Trong ví dụ này, Must chiếm **60%**, Should **20%**, Could **20%** tổng công sức ước lượng. Đây là **minh họa cách để lại phạm vi linh hoạt**, không bảo đảm nhóm sẽ giao đúng 20 đơn vị hoặc số lượng thực tế bất biến. Nếu có thêm rủi ro, việc giảm Could hoặc hoãn một số Should có thể giúp bảo vệ Must; nhưng **không được bỏ kiểm thử, quyền truy cập hoặc tiêu chuẩn chất lượng bắt buộc**.

Nếu việc ước lượng Must đã vượt năng lực hoặc cần phụ thuộc chưa được xác nhận, hành động đúng là **chia lại mục tiêu, giảm ranh giới Must một cách hợp lệ, xử lý rủi ro, hoặc báo người có thẩm quyền điều chỉnh cam kết**. Không được im lặng kéo dài timebox hoặc đưa một giải pháp không dùng được ra ngoài.

## 7. Timebox: giới hạn thời gian để tập trung vào kết quả

**Timebox** là một khoảng thời gian cố định dành cho một mục tiêu đã được thống nhất. Khi tổ chức theo DSDM, timebox giúp nhóm làm việc theo nhịp ngắn, kiểm tra thực tế thường xuyên và kết thúc đúng lúc với phần giải pháp đáp ứng các điều kiện đã xác nhận.

Một timebox tốt làm rõ:

- **Mục tiêu nghiệp vụ:** nhóm cần tạo hoặc kiểm chứng kết quả gì?
- **Thời lượng:** khi nào bắt đầu, kết thúc; ai tham gia?
- **Phạm vi ưu tiên:** Must/Should/Could/Won't dành cho timebox này.
- **Chất lượng:** các tiêu chí không được bỏ qua.
- **Cách phối hợp:** người nghiệp vụ sẵn sàng trả lời và xác nhận hành vi.
- **Cách kiểm tra kết quả:** demo, kiểm thử, đánh giá Increment và quyết định sau timebox.
- **Cơ chế xử lý rủi ro:** khi Must bị đe dọa, ai quyết định và khi nào cần báo?

Timebox **không có nghĩa** mọi hạng mục thuộc cả ba nhóm Must, Should, Could đều là cam kết chắc chắn. Mục tiêu là giữ khả năng hoàn thành phần thiết yếu, học sớm và điều chỉnh phần thấp hơn khi cần.

### Timebox có giống Sprint của Scrum?

Cả hai tạo nhịp làm việc ngắn và phản hồi thường xuyên, nhưng **không đồng nhất**.

| Khía cạnh | DSDM timebox | Scrum Sprint |
| --- | --- | --- |
| **Khung phương pháp** | DSDM với quy tắc ưu tiên và các vai trò/hoạt động DSDM | Scrum với accountabilities, events, artifacts và commitments |
| **Trọng tâm kế hoạch** | Kết quả cần đạt trong thời gian cố định, phạm vi MoSCoW linh hoạt | Sprint Goal; Developers chọn PBI và xây Sprint Backlog |
| **Hoạt động bên trong** | Có thể dùng timebox có cấu trúc hoặc tổ chức linh hoạt theo DSDM | Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective |
| **Ưu tiên** | MoSCoW thường là công cụ chủ đạo để quản lý phạm vi | Scrum không bắt buộc MoSCoW |
| **Chất lượng** | Không thỏa hiệp chất lượng theo các tiêu chí đã thống nhất | Increment phải đáp ứng Definition of Done |
| **Kết quả học hỏi** | Cùng nghiệp vụ kiểm tra khả năng và điều chỉnh bước tiếp | Kiểm tra/thích ứng thông qua các Scrum events và Increment |

Một nhóm có thể tham khảo MoSCoW khi sử dụng Scrum, nhưng việc dùng cùng một từ **không tự biến timebox thành Sprint** hay ngược lại. Cần giữ trách nhiệm và cơ chế ra quyết định của phương pháp được chọn một cách rõ ràng.

## 8. Cấu trúc một timebox DSDM có thể thực hành

DSDM mô tả kiểu **structured timebox** với những chặng như **Kick-off, Investigation, Refinement, Consolidation và Close-out**. Các hoạt động này giúp người nghiệp vụ và kỹ thuật liên tục kiểm tra giải pháp; thời lượng từng chặng có thể được điều chỉnh theo độ dài và mục tiêu thực tế.

| Chặng | Mục đích | Đầu ra hoặc quyết định hữu ích |
| --- | --- | --- |
| **Kick-off – khởi động** | Thống nhất mục tiêu, phạm vi MoSCoW, người tham gia và ràng buộc | Mọi người hiểu cùng kết quả tối thiểu và cách làm việc |
| **Investigation – tìm hiểu** | Làm rõ nhu cầu và các phương án trước khi xây sâu | Ví dụ nghiệp vụ, rủi ro, cách kiểm chứng |
| **Refinement – tinh chỉnh/phát triển** | Xây dựng, thử, nhận phản hồi và điều chỉnh giải pháp theo lát | Các phần chạy được, đã được người nghiệp vụ xem xét |
| **Consolidation – củng cố** | Tích hợp, đánh giá mức hoàn tất, xử lý điểm còn thiếu theo tiêu chuẩn chất lượng | Kết quả có thể sử dụng/đánh giá cùng các giới hạn còn lại |
| **Close-out – kết thúc** | Xác nhận kết quả của timebox, ghi điều học được và quyết định tiếp | Những điều đạt/chưa đạt, lựa chọn cho timebox sau |

Chặng Consolidation **không nên biến thành “đợi đến cuối mới kiểm thử”**. Chất lượng, tích hợp và phản hồi cần xuất hiện trong toàn timebox. Nhóm cũng có thể dùng timebox linh hoạt khi công việc phù hợp hơn; điều cốt lõi là **có mục tiêu, nhịp kiểm tra và kết thúc minh bạch**, không phải phải dành đúng tỷ lệ giờ cho mỗi chặng.

~~~mermaid
flowchart LR
    A["Kick-off\nMục tiêu + MoSCoW"] --> B["Investigation\nLàm rõ vấn đề"]
    B --> C["Refinement\nXây + thử + phản hồi"]
    C --> D["Consolidation\nTích hợp + xác minh"]
    D --> E["Close-out\nKết luận + học hỏi"]
    E --> F["Điều chỉnh ưu tiên timebox tiếp theo"]
    C -. "Điều chưa rõ" .-> B
    D -. "Cần sửa hành vi" .-> C
~~~

### Vì sao phải có mốc kết thúc thật?

Nếu timebox thường xuyên tự kéo dài “thêm hai ngày”, tổ chức mất khả năng so sánh kế hoạch với thực tế và tạo áp lực hạ chất lượng. Khi gần hết thời gian, nhóm cần:

1. Kiểm tra Must còn thiếu, rủi ro và mức chất lượng.
2. Xem Should/Could nào có thể hoãn đúng với MoSCoW đã thống nhất.
3. Thống nhất quyết định sớm với người nghiệp vụ có thẩm quyền.
4. Kết thúc minh bạch, không gọi công việc dang dở là Done.
5. Học từ nguyên nhân để lập kế hoạch timebox tiếp theo tốt hơn.

Giữ timebox cố định giúp minh bạch, **không phải bảo đảm phép màu rằng mọi mục tiêu không thực tế sẽ tự hoàn thành**.

## 9. Kết hợp MoSCoW và timebox trong thực tế

MoSCoW cho biết **cái gì có thể linh hoạt**; timebox làm rõ **khi nào phải kiểm tra và quyết định**. Hai kỹ thuật hoạt động cùng nhau chứ không thay thế nhau.

### 9.1. Trước timebox: thống nhất kết quả tối thiểu

Ví dụ một timebox hai tuần cho hành trình đăng ký khóa miễn phí:

> “Đến cuối timebox, học viên hợp lệ có thể ghi danh một khóa miễn phí đang mở, nhận trạng thái chính xác và truy cập bài đầu với quyền phù hợp.”

Các bên cùng xác nhận Must gồm việc đăng ký, cấp quyền đúng và không tạo dữ liệu trùng. Should có thể là cách giải thích lỗi chi tiết hơn; Could là tùy chỉnh thông báo. Những nhu cầu lớn như đề xuất khóa bằng AI được để ngoài timebox.

### 9.2. Trong timebox: kiểm tra tiến độ theo kết quả, không chỉ task

Nếu nhóm đã làm xong UI nhưng API cấp quyền chưa được tích hợp, không nên báo “đạt 70% Must” chỉ vì số task tăng. Câu hỏi đúng là **học viên đã đi được trọn hành trình cần thiết và đáp ứng chất lượng chưa?**

Nhóm theo dõi những điều có thể làm Must không đạt: lỗi dữ liệu, môi trường kiểm thử, đối tác tích hợp, thiếu người xác nhận quy tắc. Việc thiếu thông tin nghiệp vụ cần được giải quyết ngay, thay vì chờ đến chặng cuối.

### 9.3. Khi có nguy cơ trễ: dùng tính linh hoạt đã thống nhất

Giả sử một lỗi tích hợp làm mất hai ngày công sức. Nếu Must vẫn khả thi, nhóm **hoãn Could** theo chính sách và tập trung hoàn tất các hành vi thiết yếu. Có thể cân nhắc một phần Should sau khi biết năng lực còn lại.

Nếu Must không còn khả thi, nhóm **không được tự đổi Must thành Should** để báo thành công. Cần đánh giá phương án thay thế, tác động tới kết quả, thỏa thuận với Business Visionary/đại diện có thẩm quyền và cập nhật rủi ro hoặc điều kiện bàn giao.

~~~mermaid
flowchart TD
    A["Timebox với mục tiêu + MoSCoW"] --> B["Làm việc theo lát và kiểm tra chất lượng"]
    B --> C{"Must còn khả thi trước hạn?"}
    C -->|"Có"| D["Bảo vệ Must; chọn Should/Could theo năng lực"]
    C -->|"Không rõ"| E["Làm rõ phụ thuộc, năng lực và rủi ro ngay"]
    E --> C
    C -->|"Không"| F["Báo sớm người có thẩm quyền; thương lượng mục tiêu/ràng buộc"]
    D --> G["Kết thúc timebox, kiểm tra kết quả và điều học được"]
    F --> G
~~~

## 10. Cộng tác nghiệp vụ: ai tham gia, ai quyết định?

DSDM nhấn mạnh **cộng tác trực tiếp** giữa người hiểu nhu cầu, người xây giải pháp và người chịu trách nhiệm điều hành. Các tên vai trò được dùng trong DSDM thường bao gồm Business Sponsor, Business Visionary, Business Ambassador, Business Advisor, Project Manager, Technical Coordinator, Team Leader, Business Analyst, Solution Developer, Solution Tester và các vai trò hỗ trợ.

Trong phạm vi bài này, điều quan trọng không phải học thuộc tất cả chức danh mà là hiểu **quyền quyết định và thời điểm cần người nghiệp vụ tham gia**.

| Vai trò DSDM tiêu biểu | Trách nhiệm nổi bật đối với MoSCoW/timebox |
| --- | --- |
| **Business Sponsor** | Bảo trợ ở mức kinh doanh, nguồn lực và tính hợp lý của việc đầu tư |
| **Business Visionary** | Dẫn dắt tầm nhìn kinh doanh và sự thống nhất về giá trị tổng thể |
| **Business Ambassador** | Đại diện nghiệp vụ làm việc thường xuyên cùng nhóm giải pháp, làm rõ quy tắc và phản hồi kịp thời |
| **Business Advisor** | Chuyên gia nghiệp vụ cung cấp kiến thức chuyên sâu khi cần |
| **Project Manager** | Phối hợp quản lý dự án, rủi ro, tiến độ và các ràng buộc |
| **Team Leader** | Hỗ trợ đội làm việc hiệu quả, phối hợp việc bàn giao trong timebox |
| **Technical Coordinator** | Giữ sự nhất quán và rủi ro kỹ thuật ở mức giải pháp |
| **Business Analyst** | Hỗ trợ khám phá, phân tích và truyền đạt nhu cầu giữa các bên |
| **Solution Developer / Solution Tester** | Xây dựng, tích hợp và xác minh giải pháp đáp ứng tiêu chuẩn chất lượng |

**Không phải mỗi dự án cần một người riêng cho mọi vai trò**; cách phân công phải rõ trách nhiệm và tránh xung đột quyền quyết định. Đồng thời, không nên “đơn giản hóa” đến mức không còn ai có quyền trả lời câu hỏi nghiệp vụ hoặc quyết định phạm vi.

### Business Ambassador phải thực sự sẵn sàng

Nếu mỗi câu hỏi về ghi danh phải chờ hai tuần để qua ba cấp quản lý, timebox rất khó bảo vệ. Người đại diện nghiệp vụ cần có:

- Hiểu biết thực tế về hành trình người dùng và quy tắc.
- Khả năng trao đổi thường xuyên với nhóm kỹ thuật.
- Quyền quyết định trong phạm vi đã được ủy quyền.
- Kênh nâng cấp quyết định khi vượt quyền hoặc có xung đột giữa stakeholder.
- Trách nhiệm kiểm tra giải pháp đang hình thành, không chỉ ký biên bản cuối dự án.

Việc “có người nghiệp vụ trong danh sách người tham gia” chưa đủ. Phải có **thời gian, quyền và khả năng phản hồi** tương xứng với nhịp timebox.

## 11. Một vòng cộng tác nghiệp vụ theo ví dụ

Giả sử giảng viên và học viên có cách hiểu khác nhau về “ghi danh thành công”:

- Học viên nghĩ đã bấm nút là có quyền học ngay.
- Bộ phận đào tạo cho rằng một số khóa cần duyệt.
- Developers đang xây API chỉ có trạng thái SUCCESS/FAILED.

Nếu không có cuộc trao đổi sớm, nhóm có thể xây một trạng thái “thành công” mơ hồ, rồi sửa lại khi thử nghiệm.

### Thay handoff bằng cuộc trao đổi có ví dụ

Một cuộc làm rõ ngắn có thể đi theo các bước:

1. Business Ambassador nêu **mục đích nghiệp vụ**: học viên phải biết mình đã được cấp quyền hay còn chờ.
2. Developers và Solution Tester hỏi **trường hợp chính và ngoại lệ**.
3. Các bên thống nhất **ngôn ngữ chung**: “đã nhận yêu cầu”, “chờ duyệt”, “đã cấp quyền”, “bị từ chối”.
4. Người có thẩm quyền xác nhận **quy tắc chuyển trạng thái**.
5. Nhóm chuyển ví dụ thành acceptance criteria, có thể dùng Gherkin.
6. Nhóm xây một lát nhỏ, đưa người nghiệp vụ xem sớm.
7. Phản hồi được dùng để điều chỉnh trước khi phạm vi bị hiểu sai lan rộng.

### Ví dụ tiêu chí chấp nhận (chính sách minh họa)

~~~gherkin
Feature: Ghi danh khóa học

  Scenario: Học viên ghi danh khóa miễn phí không cần duyệt
    Given học viên đã đăng nhập và đủ điều kiện
    And khóa miễn phí đang mở và không yêu cầu duyệt
    When học viên xác nhận ghi danh
    Then hệ thống tạo đúng một đăng ký hiệu lực
    And học viên được cấp quyền mở nội dung theo chính sách
    And giao diện hiển thị trạng thái đã ghi danh

  Scenario: Khóa yêu cầu xét duyệt
    Given học viên đủ điều kiện gửi yêu cầu vào khóa cần duyệt
    When học viên gửi yêu cầu ghi danh
    Then hệ thống ghi nhận trạng thái chờ duyệt
    And chưa cấp quyền học cho đến khi có quyết định hợp lệ
    And giao diện giải thích rõ bước tiếp theo

  Scenario: Gửi lại yêu cầu khi đã có đăng ký hiệu lực
    Given học viên đã có đăng ký hiệu lực cho khóa
    When học viên gửi lại yêu cầu ghi danh cùng khóa
    Then hệ thống không tạo thêm đăng ký hiệu lực trùng
    And trả trạng thái phù hợp
~~~

Những tình huống này cần được kiểm tra với quy tắc thật của dự án. **Gherkin không tự quyết định chính sách nghiệp vụ**; nó là cách ghi lại ví dụ để các bên có cùng cách hiểu và có thể kiểm chứng.

### Khi hai stakeholder không đồng ý thì sao?

Không nên để Developers tự quyết định theo cảm giác rồi im lặng triển khai. Ghi rõ điểm bất đồng, tác động tới Must, phương án lựa chọn, ai có quyền chốt và thời hạn cần có quyết định để timebox không bị chặn. Nếu không có câu trả lời kịp thời cho một Must, đó là **rủi ro bàn giao cần được nâng cấp**, không chỉ là một câu hỏi “để sau”.

## 12. Cộng tác qua workshop, prototype và kiểm tra theo lát

Một workshop DSDM có ích khi nó giải quyết được **một vấn đề quyết định**, chẳng hạn:

> “Trong 45 phút, thống nhất trạng thái ghi danh tối thiểu cho mốc khai giảng, xác định quy tắc cấp quyền và người xử lý hai trường hợp ngoại lệ.”

Người điều phối làm rõ vấn đề, thành phần tham gia, kết quả cần đạt và timebox. Mọi người xem ví dụ, sơ đồ trạng thái hoặc prototype; tránh biến workshop thành cuộc họp báo cáo quá khứ mà không có quyết định.

### Ví dụ trạng thái nghiệp vụ

~~~mermaid
stateDiagram-v2
    [*] --> ChuaGui
    ChuaGui --> ChoDuyet: Gửi yêu cầu cho khóa cần duyệt
    ChuaGui --> DaGhiDanh: Ghi danh hợp lệ không cần duyệt
    ChoDuyet --> DaGhiDanh: Được duyệt hợp lệ
    ChoDuyet --> TuChoi: Bị từ chối
    DaGhiDanh --> [*]: Theo chính sách hoàn tất/không còn hiệu lực
    TuChoi --> [*]
~~~

Sơ đồ chỉ minh họa **những trạng thái cần làm rõ**; dự án thật có thể có hủy ghi danh, thanh toán, hết hạn quyền học hoặc chuyển trạng thái khác. Điểm quan trọng là không nhầm **yêu cầu đã nhận** với **quyền học đã được cấp**.

### Prototype không nhất thiết là Increment đã hoàn tất

Một bản nháp giao diện giúp kiểm tra cách người dùng hiểu thông báo. Nhưng bản nháp chưa tích hợp với kiểm tra quyền hoặc dữ liệu thật không nên được trình bày như tính năng production đã đạt chất lượng. Nhóm cần phân biệt **đầu ra để học hỏi** và **giải pháp sử dụng được**.

### Dùng phản hồi để điều chỉnh ưu tiên

Nếu workshop cho thấy trạng thái “chờ duyệt” rất phổ biến và cần tránh cấp quyền sai, phần xử lý nó có thể trở thành Must đối với khóa cần duyệt. Ngược lại, tính năng đổi màu trạng thái có thể vẫn là Could. MoSCoW cần được cập nhật **theo hiểu biết mới**, không chỉ được phân loại một lần rồi đóng băng.

## 13. Bản kế hoạch mẫu: dự án tám tuần với nhiều timebox

Giả sử nền tảng học sẽ mở khóa nhập môn sau tám tuần. Bảng dưới là **ví dụ học thuật**, không phải một lịch DSDM chuẩn áp dụng cho mọi tổ chức.

| Giai đoạn/nhịp minh họa | Mục đích | Bằng chứng hoặc kết quả cần có |
| --- | --- | --- |
| **Làm rõ mục tiêu và nền tảng** | Xác định đối tượng, quy tắc ghi danh, kiến trúc/rủi ro quan trọng, MoSCoW cấp dự án | Kết quả tối thiểu có thể đo, ranh giới và người ra quyết định |
| **Timebox A – hành trình ghi danh cơ bản** | Học viên đủ điều kiện gửi yêu cầu và có trạng thái chính xác | Luồng end-to-end đạt chất lượng tối thiểu |
| **Timebox B – cấp quyền và bắt đầu học** | Hoàn thiện điều kiện quyền, mở bài đầu và tình huống lỗi quan trọng | Học viên hợp lệ dùng được; không cấp quyền trái phép |
| **Timebox C – ổn định, mở rộng và phản hồi** | Xử lý phản hồi, dữ liệu cũ, khả năng vận hành và Should/Could phù hợp | Giải pháp dùng được, giám sát và quy tắc chuyển giao rõ |
| **Chuẩn bị triển khai theo mốc** | Đánh giá điều kiện phát hành, vận hành và nghĩa vụ liên quan | Quyết định phát hành có trách nhiệm và kế hoạch hỗ trợ |

Độ dài từng giai đoạn được chọn theo rủi ro và năng lực; **không đợi tới Timebox C mới bắt đầu kiểm thử hoặc bảo mật**. Mỗi lát có thể dùng được cần được tích hợp và xác minh trong quá trình phát triển. Phần Should/Could chỉ được lựa chọn khi Must và chất lượng không bị đe dọa.

### Nếu kế hoạch đang đi lệch

Giả sử hết nửa Timebox B, API cấp quyền hoạt động trong unit test nhưng lỗi khi tích hợp thực tế. Nhóm có thể:

- Tập trung sửa quyền và kiểm thử tích hợp, tạm dừng một Could về giao diện.
- Làm rõ với Business Ambassador kịch bản cấp quyền và thu hồi quyền.
- Cập nhật rủi ro và ảnh hưởng đến mốc khai giảng.
- Đưa ra phương án tiếp tục hoặc thay đổi phạm vi hợp lệ với người có quyền quyết định.

Không nên tuyên bố “đã làm xong backend” rồi coi Must đã đạt. **Kết quả tối thiểu là hành trình người dùng hoàn chỉnh, không phải tổng task của từng chuyên môn.**

## 14. Kiểm tra tiến độ: kiểm soát bằng kết quả, rủi ro và luồng

DSDM khuyến khích thể hiện khả năng kiểm soát, nhưng **kiểm soát không đồng nghĩa yêu cầu từng cá nhân báo cáo từng giờ**. Một dự án có thể minh bạch bằng tiến triển Must, chất lượng giải pháp, phản hồi nghiệp vụ, rủi ro và năng lực bàn giao.

### Bộ thông tin gọn cho một timebox

| Tín hiệu | Câu hỏi quản lý | Lưu ý |
| --- | --- | --- |
| **Must đã đáp ứng tới mức nào?** | Các hành vi thiết yếu nào đã có thể sử dụng, đạt tiêu chí? | Tránh báo phần trăm chỉ theo task con |
| **Should/Could còn phù hợp?** | Có cần hoãn để bảo vệ mục tiêu và chất lượng? | Quyết định minh bạch cùng người nghiệp vụ |
| **Rủi ro và phụ thuộc** | Điều gì có thể ngăn giao Must đúng mốc? | Nêu người xử lý và thời điểm phải quyết định |
| **Chất lượng** | Kiểm thử, quyền, dữ liệu, vận hành đã đáp ứng ràng buộc chưa? | Không hạ tiêu chuẩn để tăng tiến độ giả |
| **WIP/work item age** | Việc gì đang làm dở quá lâu hoặc kẹt vì chờ? | Giúp giảm mở việc mới và tháo điểm nghẽn |
| **Cycle time/throughput** | Dòng công việc có đủ ổn định để dự báo? | Cần cùng định nghĩa đầu-cuối và loại việc |
| **Phản hồi nghiệp vụ/người dùng** | Giải pháp có giải quyết đúng vấn đề chưa? | Phân biệt dữ liệu quan sát với giả thuyết |

### Ví dụ một bản ghi quyết định ngắn

~~~text
Mục tiêu timebox: Học viên hợp lệ ghi danh và mở được bài đầu
Must: Ghi danh, trạng thái chính xác, kiểm soát quyền, chống trùng
Should: Thông báo trạng thái nâng cao
Could: Bộ lọc giao diện và một số tiện ích
Rủi ro mới: Callback tích hợp đôi khi đến lặp
Bằng chứng: Test tích hợp phát hiện dữ liệu không nhất quán
Quyết định: Ưu tiên xử lý idempotency, hoãn Could
Người xác nhận nghiệp vụ: Business Ambassador theo phân quyền
Khi nào xem lại: Sau kiểm thử tích hợp và đánh giá khả năng đạt Must
Guardrail: Không cấp sai quyền, không tạo đăng ký hiệu lực trùng
~~~

Khi tiến độ vẫn chưa khả thi dù đã điều chỉnh Could/Should, cần **nâng cấp quyết định sớm**. Bản ghi ngắn giúp người liên quan hiểu vì sao scope đổi và điều gì vẫn phải được bảo vệ.

## 15. DSDM phối hợp với user story, Scrum, Kanban và XP

### User story và backlog: biến mục tiêu thành lát giá trị

MoSCoW nên áp dụng trên những nhu cầu đủ rõ để đánh giá hệ quả nếu hoãn. Một epic như “Nâng cấp trải nghiệm học viên” quá lớn để gắn Must rồi coi là một cam kết duy nhất. Có thể chia thành các user story: ghi danh hợp lệ, xem trạng thái, mở bài đầu, xem khóa đã đăng ký và các tiện ích nâng cao.

Một user story tốt diễn đạt **người hưởng lợi – khả năng – giá trị**, còn acceptance criteria nêu những trường hợp để kiểm chứng. MoSCoW giúp sắp xếp các story **theo mốc bàn giao**, không thay thế việc làm rõ yêu cầu.

### Scrum: học hỏi từ timebox nhưng giữ ranh giới framework

Nếu một Scrum Team dùng MoSCoW để trao đổi ưu tiên, Product Owner vẫn chịu trách nhiệm quản lý Product Backlog; Developers chịu trách nhiệm ước lượng/kích thước hóa các PBI khi dùng Scrum và tự tổ chức thực hiện. Sprint Goal là mục tiêu của Sprint, Definition of Done bảo vệ chất lượng Increment. **Không được tự thay thế Sprint Goal bằng danh sách Must** hoặc bỏ các Scrum events vì đã có timebox DSDM.

DSDM và Scrum đều có cách kiểm tra và thích ứng, nhưng có bộ vai trò/hoạt động khác nhau. Một tổ chức nên nói rõ **cách tiếp cận chính** và những kỹ thuật được bổ sung, tránh gây mâu thuẫn quyền quyết định.

### Kanban: nhìn dòng công việc và vùng chờ

Kanban giúp nhìn Must đang kẹt ở đâu: chờ xác nhận nghiệp vụ, chờ review hay chờ kiểm thử tích hợp. Giới hạn WIP và chính sách kéo giúp nhóm **hoàn thành hành trình thiết yếu trước khi bắt đầu thêm nhiều Could**. Các số liệu cycle time, throughput và work item age hỗ trợ dự báo, nhưng không tự chứng minh người dùng đã nhận giá trị.

### XP: làm cho “không thỏa hiệp chất lượng” khả thi

Kiểm thử tự động, TDD khi phù hợp, tích hợp liên tục, refactoring và thiết kế đơn giản giúp đội giảm lỗi khi phát triển tăng dần. Nếu phải chờ nhiều tuần để biết hai API có tương thích không, timebox ngắn cũng khó tạo phản hồi. Thực hành kỹ thuật tốt biến cam kết chất lượng thành **khả năng thực thi**, không chỉ một câu trong tài liệu.

### Lean: tối ưu từ nhu cầu đến giá trị thật

Lean bổ sung câu hỏi “Trong toàn bộ hành trình từ ý tưởng đến người dùng, bước nào tạo thời gian chờ và làm lại?”. Một timebox có thể hoàn tất đúng ngày nhưng không tạo giá trị nếu hạng mục Must được xác định sai. Vì vậy, ngoài giao đúng hạn, cần đo **outcome người dùng** và liên tục rà soát giả thuyết.

## 16. Những sai lầm thường gặp khi áp dụng DSDM

| Phản mẫu | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| **Mọi stakeholder đều đánh dấu Must** | Không có phạm vi linh hoạt, timebox trở thành cam kết bất khả thi | Yêu cầu nêu hệ quả cụ thể nếu thiếu; đánh giá Must theo mục tiêu mốc |
| **MoSCoW không có mốc thời gian** | Won't/Should bị hiểu như quyết định vĩnh viễn | Nêu rõ ưu tiên cho lần bàn giao/timebox nào |
| **Đổi Must thành Could vào ngày cuối** | Che việc mục tiêu không đạt, giảm minh bạch | Nâng cấp rủi ro và thương lượng hợp lệ với người có thẩm quyền |
| **Bỏ test hoặc phân quyền để kịp timebox** | Vi phạm chất lượng và tăng thiệt hại dữ liệu | Bảo vệ chất lượng; điều chỉnh tính năng có thể hoãn |
| **Business Ambassador chỉ dự họp khởi động** | Quy tắc nghiệp vụ phải chờ nhiều cấp, vòng phản hồi dài | Dành quyền và thời gian trao đổi thường xuyên |
| **Lấy số ticket Done thay cho Must đạt** | Nhiều task hoàn tất nhưng luồng người dùng vẫn không chạy | Kiểm tra increment/hành trình nghiệp vụ đầy đủ |
| **Timebox luôn kéo dài “vì còn chút nữa”** | Mất tính dự báo, không kiểm tra lại năng lực | Kết thúc đúng nhịp, minh bạch phần chưa đạt và quyết định tiếp |
| **Không chừa vùng contingency** | Mọi sai lệch nhỏ phá vỡ kế hoạch | Ước lượng có điều kiện và giữ Should/Could thực sự linh hoạt |
| **Chỉ tối ưu thời hạn, không đo giá trị** | Giao đúng ngày nhưng xây sai nhu cầu | Đo outcome, phản hồi và rủi ro theo mốc |
| **Workshop không có quyền chốt** | Mỗi cuộc họp tạo thêm câu hỏi nhưng không có quyết định | Xác định người có thẩm quyền, tiêu chí quyết định và đường nâng cấp |
| **Đồng nhất DSDM với Scrum** | Vai trò và quyền ưu tiên bị chồng chéo | Nêu rõ framework đang theo và kỹ thuật nào đang mượn |
| **Cho rằng Won't nghĩa là không bao giờ** | Stakeholder hiểu sai định hướng sản phẩm | Ghi “this time”, điều kiện xem lại và quyết định mới nếu cần |
| **Bắt đầu nhiều Could khi Must đang bị chặn** | WIP tăng, mục tiêu thiết yếu gặp rủi ro | Ưu tiên tháo blocker Must và hoàn tất việc đang dở |
| **Tài liệu quá nặng để chứng minh kiểm soát** | Thời gian chờ quyết định lớn, ít phản hồi thật | Chọn bằng chứng, quyết định và báo cáo vừa đủ phục vụ điều hành |

## 17. Bài thực hành: tổ chức MoSCoW và timebox cho đợt khai giảng

### 17.1. Bối cảnh

Một nền tảng đào tạo cần cho học viên mới ghi danh khóa nhập môn và mở bài đầu trong **sáu tuần**. Có các đề xuất:

1. Đăng nhập và xác nhận quyền học viên.
2. Ghi danh khóa miễn phí đang mở.
3. Không tạo đăng ký hiệu lực trùng khi người học gửi yêu cầu nhiều lần.
4. Hiển thị trạng thái đăng ký chính xác.
5. Gửi email với mẫu thông báo nâng cao.
6. Tự động nhắc học qua nhiều kênh.
7. Dashboard phân tích chi tiết hành vi học.
8. Cho phép giáo viên phê duyệt khóa cần xét duyệt, nhưng chưa rõ đợt đầu có khóa kiểu này hay không.
9. Bộ lọc yêu thích, nhãn màu và cách sắp xếp khóa.
10. Kiểm thử phân quyền và bảo vệ dữ liệu học viên theo tiêu chuẩn tổ chức.

Nhóm có năng lực giới hạn, một môi trường tích hợp đang không ổn định, và bộ phận đào tạo chỉ có một người có thể xác nhận quy tắc ghi danh.

### 17.2. Yêu cầu

1. Viết **mục tiêu bàn giao tối thiểu** cho sáu tuần; xác định học viên nào được phục vụ.
2. Phân loại mười mục theo **Must, Should, Could, Won't this time**; nêu giả định và câu hỏi cần xác nhận.
3. Giải thích vì sao mục 10 **không thể trở thành Could** chỉ để rút thời gian.
4. Phác thảo **hai timebox ngắn** với mục tiêu, đầu ra có thể kiểm chứng và quy tắc hoãn Should/Could.
5. Nêu người nghiệp vụ cần tham gia thường xuyên và **phạm vi quyền quyết định** của họ.
6. Viết **ba acceptance criteria** cho ghi danh, gồm gửi lặp và thiếu quyền.
7. Đề xuất **một tín hiệu tiến độ, một outcome và hai guardrail**.
8. Nếu sau timebox đầu mục 2 còn thiếu tích hợp, bạn sẽ điều chỉnh thế nào mà không báo Done giả?

### 17.3. Gợi ý lời giải

**Mục tiêu:** “Đến ngày khai giảng, học viên đủ điều kiện có thể đăng nhập, ghi danh khóa miễn phí đang mở và truy cập bài đầu với trạng thái chính xác, dữ liệu không trùng và quyền học được bảo vệ.”

**Phân loại đề xuất theo giả định đợt đầu chỉ có khóa không cần duyệt:**

| Mục | Phân loại gợi ý | Lý do |
| --- | --- | --- |
| 1. Đăng nhập/quyền | **Must** | Điều kiện để xác định và bảo vệ người học |
| 2. Ghi danh miễn phí | **Must** | Hành trình nghiệp vụ cốt lõi |
| 3. Chống đăng ký trùng | **Must / chất lượng** | Giữ dữ liệu và quyền nhất quán |
| 4. Trạng thái chính xác | **Must** | Người học cần biết kết quả thực tế |
| 5. Email trình bày nâng cao | **Should** nếu không bắt buộc theo hợp đồng | Có thể sử dụng trạng thái trên sản phẩm thay thế tạm |
| 6. Nhắc học đa kênh | **Won't this time** hoặc Could nếu rất nhỏ | Không cần cho khả năng bắt đầu học |
| 7. Dashboard phân tích | **Won't this time** | Chưa phục vụ trực tiếp mốc khả dụng tối thiểu |
| 8. Quy trình phê duyệt | **Chờ xác nhận**; Must nếu đợt đầu có khóa cần duyệt | Phụ thuộc quyết định nghiệp vụ, không được đoán |
| 9. Bộ lọc/giao diện tùy chọn | **Could** | Cải thiện tiện lợi nhưng không chặn mục tiêu |
| 10. Kiểm thử quyền và bảo vệ dữ liệu | **Tiêu chuẩn chất lượng bắt buộc** | Không thể cắt để “giữ hạn” |

**Hai timebox ứng viên:** timebox A tập trung đăng nhập và trạng thái ghi danh chính xác trên một luồng tích hợp; timebox B tập trung cấp quyền mở bài đầu, xử lý gửi lặp và kiểm chứng an toàn end-to-end. Phần việc cần được chia nhỏ để mỗi timebox có kết quả có thể kiểm tra; với sáu tuần tổng thể, còn phải dự liệu thời gian cho chuẩn bị, phụ thuộc và phát hành phù hợp. Không thể khẳng định các timebox chắc chắn đủ chỉ từ danh sách này.

**Người nghiệp vụ:** phân công Business Ambassador hiểu quy tắc ghi danh, có thời gian trả lời trong ngày và được ủy quyền quyết định biến thể trong phạm vi đã thống nhất. Nếu có tranh cãi về việc khóa có cần phê duyệt, Business Visionary hoặc người có thẩm quyền phải chốt trước khi nhóm xây sai luồng.

**Acceptance criteria minh họa:** học viên đủ điều kiện ghi danh thành công và có đúng một đăng ký hiệu lực; gửi yêu cầu lặp không tạo thêm đăng ký; người không có quyền không thể ghi danh thay tài khoản khác hoặc mở nội dung bị hạn chế. Những điều kiện này cần xác nhận với chính sách thực tế.

**Đo lường:** tín hiệu tiến độ là số hành trình Must đạt tiêu chí trên bản tích hợp và không còn blocker quan trọng; outcome là tỷ lệ học viên đủ điều kiện ghi danh rồi mở bài đầu trong khoảng thời gian xác định; guardrail là không cấp sai quyền và không tạo dữ liệu đăng ký trùng/mất nhất quán.

**Khi Must chưa hoàn tất:** minh bạch rằng hành trình chưa Done, dừng Could đang làm, ưu tiên tháo môi trường tích hợp và gọi quyết định nghiệp vụ cần thiết. Nếu mốc cuối không còn khả thi, báo rủi ro sớm để người có thẩm quyền lựa chọn giải pháp hợp lệ; không giảm chất lượng hoặc đổi nhãn âm thầm.

### 17.4. Bài tập mở rộng: điều chỉnh ưu tiên theo bằng chứng mới

Giả sử ngay sau timebox A, bộ phận đào tạo xác nhận **30% khóa của đợt đầu cần phê duyệt**. Hãy trả lời:

- Phần nào của mục 8 giờ trở thành Must, phần nào vẫn có thể hoãn?
- Story nào cần chia để hỗ trợ đúng hai luồng “cần duyệt” và “không cần duyệt”?
- Business Ambassador có đủ quyền thay đổi phân loại, hay cần Business Visionary quyết định lại phạm vi?
- Có cách nào giữ mốc bàn giao mà không cấp quyền sai và không làm một quy trình phê duyệt quá lớn?

Gợi ý: mô tả trước **quy tắc trạng thái tối thiểu** của cả hai loại khóa, làm rõ người có quyền duyệt, tiêu chí cấp quyền và bằng chứng hoàn tất. Không tự cam kết giao toàn bộ công cụ quản trị nâng cao nếu chỉ cần một cơ chế duyệt tối thiểu an toàn cho mốc đầu.

## 18. Checklist trước khi áp dụng DSDM trong dự án thật

- [ ] Mục tiêu kinh doanh và **giải pháp tối thiểu có thể sử dụng** được phát biểu rõ?
- [ ] Timebox có **mốc bắt đầu, kết thúc, phạm vi, điều kiện chất lượng** và cách kiểm tra kết quả?
- [ ] MoSCoW được xác định **cho một mốc cụ thể**, không phải nhãn vĩnh viễn?
- [ ] Mỗi Must có **lý do thiết yếu** hoặc ràng buộc bắt buộc có thể giải thích?
- [ ] Tập Must đủ nhỏ để nhóm có thể giao với năng lực thực tế và rủi ro đã biết?
- [ ] Should/Could tạo được **vùng linh hoạt thật**, không là danh sách Must trá hình?
- [ ] Won't this time được truyền đạt minh bạch cùng điều kiện xem lại nếu cần?
- [ ] Các tiêu chí về bảo mật, chất lượng, dữ liệu và vận hành **không bị cắt** để giữ hạn?
- [ ] Business Ambassador có **thời gian, hiểu biết và quyền quyết định** cần thiết?
- [ ] Khi phát sinh bất đồng vượt quyền, có **cơ chế nâng cấp quyết định** rõ?
- [ ] Người nghiệp vụ tham gia **kiểm tra theo lát**, không chỉ ký duyệt cuối kỳ?
- [ ] Những user story gần thực hiện có tiêu chí chấp nhận và dữ liệu nghiệp vụ rõ?
- [ ] Nhóm xây dựng **Increment tích hợp, dùng được**, không chỉ hoàn thành task rời rạc?
- [ ] Khi Must gặp nguy cơ, nhóm ưu tiên tháo blocker và **điều chỉnh phần có thể hoãn**?
- [ ] Tiến độ được xem qua **kết quả Must, rủi ro, chất lượng và phản hồi** chứ không chỉ tổng ticket?
- [ ] Việc thay đổi phân loại có **bằng chứng, người chốt và hệ quả với mốc**?
- [ ] Có phối hợp các thực hành Kanban/XP/Lean khi chúng giải quyết điểm nghẽn quan sát được?
- [ ] Sau timebox, nhóm có **kết luận rõ điều đạt/chưa đạt và cải tiến** cho vòng sau?

**Ghi nhớ:** DSDM giúp tổ chức Agile giao giải pháp có giá trị trong các ràng buộc thực tế bằng ba thói quen phối hợp: **MoSCoW phân biệt phần bắt buộc với phần có thể hoãn; timebox tạo nhịp kiểm tra và giới hạn thời gian rõ; cộng tác nghiệp vụ giúp quyết định đúng xuất hiện khi nhóm cần**. Không được biến sự linh hoạt của phạm vi thành lý do cắt chất lượng, cũng không nên biến mọi mong muốn thành Must. Khi kết hợp với user story, backlog, kiểm thử, Scrum, Kanban, XP và đo lường luồng, DSDM hỗ trợ **bàn giao tăng dần, phản hồi sớm và điều chỉnh có trách nhiệm**.
