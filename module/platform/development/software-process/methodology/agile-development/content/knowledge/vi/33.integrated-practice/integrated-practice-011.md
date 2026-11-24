# Xử lý tình huống thay đổi yêu cầu, thời hạn cứng và công việc khẩn cấp

**Tình huống mở đầu.** Một Scrum Team đang phát triển nền tảng đăng ký workshop. Đối tác đã công bố ngày mở đăng ký; người dùng mong đợi một luồng đăng ký đúng, an toàn và có thể kiểm tra trạng thái. Khi chỉ còn 15 ngày làm việc, đối tác đề nghị bổ sung bước xác minh điều kiện học viên. Cùng lúc, nhóm hỗ trợ phát hiện một lỗi phân quyền có thể khiến người dùng đọc thông tin đăng ký của người khác. Một thành viên đang nghỉ phép; môi trường kiểm thử tích hợp lại không ổn định. Product Owner nhận nhiều yêu cầu “ưu tiên số một” và lãnh đạo muốn giữ nguyên cả phạm vi lẫn thời hạn.

Nhóm có thể chọn cách tưởng như nhanh nhất: thêm hai user story mới, yêu cầu Developers làm thêm giờ, chuyển test bảo mật sang Sprint sau và đánh dấu “gần xong”. Nhưng như vậy họ đang **giấu xung đột ràng buộc, tăng WIP và chuyển rủi ro sang người dùng**. Một cách làm Agile có trách nhiệm là xác minh điều gì thực sự bắt buộc, phân loại công việc khẩn, cập nhật dự báo bằng bằng chứng, thương lượng những phần có thể đổi và **không hạ tiêu chuẩn chất lượng để đạt ngày**.

Bài thuộc chương **Thực hành tổng hợp** của module **AGILE_DEVELOPMENT**. Nó kết nối tư duy Agile về phản hồi sớm và sản phẩm tăng dần với **user story, Product Backlog, Scrum, Kanban, XP và các chỉ số dòng công việc**. Khác với việc học từng kỹ thuật riêng rẽ, mục tiêu ở đây là **đưa ra quyết định nhất quán khi thay đổi yêu cầu, thời hạn cứng và sự cố khẩn cấp diễn ra cùng lúc**, đặc biệt lúc không thể làm tất cả mọi thứ.

> **Thông điệp chính:** Tính thích ứng không phải khả năng nhét mọi việc mới vào một lịch đã đầy. Đó là năng lực **thấy thay đổi, hiểu tác động, bảo vệ điều kiện bắt buộc, chọn trade-off có thẩm quyền và kiểm chứng kết quả sớm**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **thay đổi nhu cầu sản phẩm**, **mốc bắt buộc** và **công việc khẩn do sự cố** thay vì gộp tất cả vào một hàng đợi ưu tiên.
2. Thiết lập **nguồn sự thật, ranh giới quyền quyết định, tiêu chí Done và điều kiện phát hành** trước khi tranh luận về kế hoạch.
3. Phân loại yêu cầu mới theo **outcome, mức bắt buộc, rủi ro, chi phí trì hoãn, phụ thuộc và khả năng chia lát cắt**.
4. Triage incident dựa trên **tác động và mức độ khẩn được xác minh**, không theo chức danh người yêu cầu.
5. Tái lập kế hoạch dưới deadline cố định bằng **năng lực thực tế, WIP, throughput, work item age, cycle time và bất định**.
6. Sử dụng đúng **Sprint Goal, Product Backlog, Sprint Backlog, Definition of Done, Increment** và biết giới hạn khi cần thay đổi Sprint.
7. Dùng tư duy Kanban về **class of service, expedite, WIP limit và chính sách kéo việc** để bảo vệ luồng công việc thường lẫn khẩn.
8. Giữ kiểm chứng **dữ liệu, phân quyền, tích hợp, CI, regression, vận hành** theo rủi ro khi phạm vi thay đổi.
9. Đề xuất các phương án **giảm phạm vi, thay cách thực hiện, release theo pha, đàm phán lại cam kết hoặc no-go** một cách trung thực.
10. Thực hiện một bài mô phỏng từ khi nhận ba biến cố đến lúc quyết định go/no-go và cải tiến sau sự kiện.

## 2. Ba dòng biến động cần xử lý riêng nhưng phối hợp

Trong thực tế, nhóm có thể nhận cùng lúc ba loại tín hiệu:

| Dòng biến động | Câu hỏi cốt lõi | Ví dụ workshop | Điều không nên làm |
| --- | --- | --- | --- |
| **Thay đổi yêu cầu** | Người dùng/stakeholder cần điều gì mới, vì sao và cần khi nào? | Đối tác yêu cầu xác minh mã học viên | Tự thêm mọi yêu cầu vào Sprint chỉ vì đến muộn |
| **Thời hạn bắt buộc** | Mốc và điều kiện thành công nào được xác nhận không thể tự đổi? | Ngày D phải cho đối tượng đã cam kết đăng ký hợp lệ | Gọi mọi tiện ích là Must hoặc tự dời hợp đồng |
| **Công việc khẩn cấp** | Có tác động hiện tại cần ứng phó ngay để bảo vệ người dùng/hệ thống không? | Một lỗi phân quyền có thể tiết lộ dữ liệu | Đợi refinement thường kỳ rồi mới xử lý nguy cơ nghiêm trọng |

Chúng liên quan: sự cố lấy đi năng lực dự kiến cho tính năng; yêu cầu mới thay đổi phạm vi Must; deadline giới hạn thời gian học và kiểm chứng. Tuy vậy, **thứ tự điều tra và quyền xử lý của ba dòng không hoàn toàn giống nhau**.

### 2.1. Thay đổi yêu cầu không tự động là khẩn

Một stakeholder nói “đề nghị thêm dashboard ngay” là **yêu cầu ưu tiên**, chưa phải incident. Cần xác minh giá trị, điều kiện hợp đồng, thời điểm cần và tác động lên Product Goal.

### 2.2. Việc khẩn không tự động là tính năng mới

Một lỗ hổng phân quyền đang ảnh hưởng người dùng là vấn đề **an toàn và ứng phó**, có thể cần kích hoạt quy trình incident riêng. Xử lý khẩn không nhất thiết bắt đầu bằng cách viết một user story sản phẩm như mọi việc thường.

### 2.3. Deadline không biến mọi công việc thành Must

Ngay cả khi ngày D không dời được, vẫn có thể có **giao diện lịch nâng cao, email nhắc, báo cáo tùy biến** được hoãn nếu người có thẩm quyền xác nhận chúng không phải điều kiện bắt buộc của mốc.

## 3. Các nguyên tắc dẫn đường khi ba áp lực va nhau

Một nhóm nên giữ các nguyên tắc ra quyết định sau:

1. **Minh bạch thực trạng:** Việc chưa đạt Done không được báo là Done; rủi ro và phụ thuộc cần được hiển thị.
2. **Bảo vệ người dùng:** Không cắt kiểm chứng bắt buộc, phân quyền hoặc tính đúng dữ liệu để tăng tốc.
3. **Ưu tiên outcome:** Hỏi điều người dùng phải làm được vào mốc D, không chỉ đếm số tính năng.
4. **Đón thay đổi có điều kiện:** Xem phản hồi mới là thông tin, không mặc định chấp nhận hoặc từ chối.
5. **Làm ít việc đang mở hơn:** Hoàn tất lát cắt và tháo điểm chờ trước khi kéo việc phụ mới.
6. **Giao nhỏ để nhận phản hồi sớm:** Chia theo hành vi đầu cuối có thể kiểm chứng thay vì chỉ DB/API/UI.
7. **Quản trị quyền đúng:** Product Owner quyết định giá trị/backlog; Developers quyết định cách tạo Increment; chủ cam kết và chức năng an toàn quyết những gì thuộc thẩm quyền của họ.
8. **Dùng dự báo như giả thuyết:** Dữ liệu và năng lực giúp ước lượng khoảng khả thi; không có phương pháp nào đảm bảo chắc tiến độ khi phụ thuộc và sự cố bất định.
9. **Ưu tiên tốc độ phản hồi có trách nhiệm:** Incident nghiêm trọng cần kênh khẩn; các yêu cầu thường cần làm rõ và sắp thứ tự minh bạch.
10. **Học từ kết quả:** Quyết định nào cũng có giả định, tín hiệu kiểm chứng và mốc xem lại.

### 3.1. Agile Manifesto không cổ vũ bỏ kế hoạch

Giá trị **“Responding to change over following a plan”** khuyến khích điều chỉnh dựa trên thực tế, nhưng không phủ nhận việc lập kế hoạch hay cam kết. **“Working software over comprehensive documentation”** không đồng nghĩa bỏ test, tài liệu vận hành hoặc bằng chứng tuân thủ cần thiết.

### 3.2. Chất lượng là ràng buộc, không phải vùng đệm tùy ý

Trong Scrum, **chất lượng không được giảm trong Sprint**. Khi thiếu năng lực, cần thương lượng phạm vi, thứ tự hoặc phương án, **không chuyển lỗi dữ liệu đã biết sang production với lời hứa sửa ở Sprint sau**.

## 4. Xác định sự thật trước khi cập nhật kế hoạch

Trước khi kéo thẻ vào board, nên có một **bản chụp tình trạng thật**:

- **Product Goal:** Hành vi, outcome và nhóm người dùng nào đang được hướng tới?
- **Sprint Goal:** Mục tiêu nào Scrum Team đang cùng cam kết đạt?
- **Phạm vi Must đã xác minh:** Hợp đồng, quy định, an toàn hoặc nghiệp vụ nào thực sự bắt buộc?
- **Định nghĩa Done:** Những kiểm chứng nào là điều kiện để một Increment được coi là hoàn tất?
- **Hiện trạng Increment:** Điều gì đã tích hợp, được kiểm thử, có thể sử dụng; điều gì chỉ “dev xong”?
- **Năng lực còn lại:** Nghỉ phép, on-call, lỗi hệ thống, người review, CI, môi trường, phụ thuộc.
- **Điểm nghẽn:** PBI nào đang già đi, chờ review, đối tác hay quyết định?
- **Quyền quyết định:** Ai xác nhận nghĩa vụ mốc D, ai ưu tiên backlog, ai ra quyết định release/incident?

### 4.1. Bằng chứng cần rõ nguồn và thời điểm

Nếu yêu cầu mới được nói trong chat, lưu **nguồn xác nhận và người có thẩm quyền**. Nếu test không đạt, ghi phiên bản build, điều kiện tái hiện và phạm vi ảnh hưởng. Nếu “chỉ còn ba ngày”, ghi **múi giờ của mốc** và khoảng thời gian cần cho release/rollback, không tự coi cả ngày cuối là ngày viết code.

### 4.2. Không trì hoãn ứng phó khi đang xác minh

Nếu có tín hiệu lộ dữ liệu thực, nhóm cần **kích hoạt đường ứng phó bảo mật** theo chính sách ngay, đồng thời điều tra. “Chưa biết toàn bộ nguyên nhân” không phải lý do để chờ đến cuộc họp lập kế hoạch thông thường trước khi giảm tác động theo thẩm quyền.

## 5. Case study tích hợp: ngày mở đăng ký đã được công bố

Xuyên suốt bài, chúng ta dùng một tình huống **giả định để thực hành**, không mô tả một công ty hoặc cam kết có thật.

### 5.1. Bối cảnh và các vai trò

Nền tảng workshop gồm hành trình:

1. Học viên xem workshop đang mở và điều kiện tham dự.
2. Học viên xác minh điều kiện và yêu cầu đăng ký.
3. Hệ thống giữ đúng số chỗ, lưu một trạng thái xác nhận đáng tin.
4. Học viên xem lại trạng thái; Support có khả năng đối soát khi lỗi.
5. Những tiện ích như email nhắc, lọc nâng cao hoặc lịch tháng đến sau khi có cơ sở ưu tiên.

Những người tham gia:

| Vai trò/chức năng | Mối quan tâm chính | Quyền hoặc trách nhiệm cần làm rõ |
| --- | --- | --- |
| **Product Owner (PO)** | Product Goal, giá trị, thứ tự Product Backlog | Quyết định backlog, đàm phán scope trong Scrum |
| **Developers** | Tạo Increment đúng DoD, thiết kế và dự báo thực thi | Cập nhật Sprint Backlog, bảo vệ chất lượng |
| **Scrum Master** | Hiệu quả Scrum, minh bạch, tháo trở ngại hệ thống | Facilitate, giúp làm rõ chứ không tự xếp lại Product Backlog thay PO |
| **Đại diện đối tác/chủ cam kết** | Phạm vi và ngày mở đăng ký được thỏa thuận | Xác nhận nghĩa vụ hoặc đàm phán lại theo quyền |
| **Security/Privacy** | Quyền truy cập, dữ liệu cá nhân, cách ứng phó lộ lọt | Quy trình và thẩm quyền chấp nhận/khắc phục rủi ro |
| **Operations/Support** | Giám sát, xử lý sự cố và hỗ trợ người học | Incident response, runbook, quyền phát hành |
| **Người học thử phù hợp** | Trải nghiệm và độ chính xác của xác nhận | Cho phản hồi về hành trình, không quyết thay chính sách an toàn |

Các vai trò Security/Operations/chủ cam kết là **cách tổ chức có thể gặp**, không phải accountability được Scrum Guide liệt kê bắt buộc trong một Scrum Team.

### 5.2. Ràng buộc ban đầu

- Mốc **D = ngày 15/12 trong tình huống giả định**; thời điểm cụ thể và múi giờ đã được bên cam kết xác minh.
- Phải có **đăng ký hợp lệ, không vượt sức chứa, trạng thái đáng tin, bảo vệ dữ liệu và đường hỗ trợ phù hợp**.
- Lịch tháng, lọc nâng cao và email nhắc **chưa được xác nhận là nghĩa vụ phải có vào D**.
- Còn **15 ngày làm việc** trước D, trong đó lịch hoạt động có một Sprint đang diễn ra và giai đoạn kiểm chứng/phát hành theo kế hoạch hiện có. **Sprint không được tự kéo dài chỉ vì mốc bên ngoài.**
- Năng lực hiệu quả dự kiến, sau khi trừ họp, on-call thường lệ và nghỉ phép đã biết: **52 ngày-người**. Đây là một **ước lượng năng lực giả định**, không đồng nghĩa 52 ngày lịch hay bảo đảm tất cả công việc chạy song song.

### 5.3. Backlog ban đầu của case

| Mã | Khả năng/điều kiện | Phân loại tạm | Nỗ lực giả định | Rủi ro/phụ thuộc |
| --- | --- | --- | ---: | --- |
| M1 | Xem workshop đúng thông tin và trạng thái | Must | 8 ngày-người | Dữ liệu lịch và sức chứa |
| M2 | Đăng ký không vượt sức chứa, trạng thái chính xác | Must | 12 ngày-người | Giao dịch/đồng thời, retry |
| M3 | Xem đăng ký của chính mình, đúng phân quyền | Must | 6 ngày-người | Kiểm thử hai tài khoản, dữ liệu |
| M4 | Chuẩn bị giám sát, hỗ trợ, kiểm chứng release | Must | 7 ngày-người | Operations, môi trường, runbook |
| S1 | Email nhắc và nội dung thông báo bổ sung | Should nếu không có nghĩa vụ khác | 9 ngày-người | Dịch vụ email/đối tác |
| C1 | Bộ lọc nâng cao và lịch tháng | Could | 10 ngày-người | Trải nghiệm UI và thời gian |

Tổng phần Must ban đầu:

\[
8+12+6+7=33\text{ ngày-người}.
\]

Should và Could cộng thêm \(9+10=19\) ngày-người. Nếu cố làm tất cả, tổng mức nỗ lực thô là **52 ngày-người**, bằng đúng toàn bộ năng lực dự kiến **trước khi có bất kỳ biến động nào**. Đây là kế hoạch **không có dự phòng cho bất định**, trong khi M2 chứa rủi ro giao dịch. Chưa kể phụ thuộc và thời gian chờ có thể làm lịch khác xa tổng nỗ lực.

### 5.4. Ba biến cố đồng thời

Ở đầu tuần đầu tiên của giai đoạn còn lại:

1. **CR-17 — yêu cầu mới:** Đối tác đề nghị xác minh mã học viên với API của họ trước khi xác nhận; nỗ lực thô ban đầu **8 ngày-người**, chưa tính thời gian chờ cấp môi trường và thử tích hợp. Chưa rõ đó là nghĩa vụ hợp đồng hay mong muốn bổ sung.
2. **INC-04 — bảo mật khẩn:** Support báo tài khoản B có thể yêu cầu một mã định danh và thấy thông tin đăng ký của A. Nhóm Security đánh giá mức ảnh hưởng cần điều tra khẩn; ước lượng ứng phó/sửa/kiểm chứng bước đầu **6 ngày-người**, nhưng có thể biến động.
3. **Deadline D giữ nguyên theo thông tin hiện có:** Đối tác chưa đồng ý dời ngày; không vì thế mà các chức năng S1/C1 trở thành Must.

**Mục tiêu bài thực hành:** Không viết “kế hoạch thần kỳ” vừa làm đủ 52 ngày-người ban đầu, thêm 8 ngày-người, xử lý 6 ngày-người incident mà vẫn trong 52 ngày-người. Cần có **quyết định phạm vi và rủi ro minh bạch**.

## 6. Quy trình tổng hợp từ tín hiệu tới quyết định

Sơ đồ dưới đây là **cách tổ chức thực hành**; khi có incident thật, nhóm phải tuân thủ quy trình ứng phó có hiệu lực chứ không đợi hoàn thành tất cả bước quản trị.

~~~mermaid
flowchart TD
    A["Có yêu cầu mới / mốc cứng / tín hiệu khẩn"] --> B["Nhận diện và xác minh nguồn"]
    B --> C{"Đang có nguy cơ nghiêm trọng với người dùng/hệ thống?"}
    C -->|"Có hoặc nghi ngờ đáng kể"| D["Kích hoạt ứng phó incident đúng quyền"]
    D --> E["Giảm tác động, điều tra, lưu bằng chứng"]
    C -->|"Không"| F["Làm rõ giá trị, nghĩa vụ, rủi ro và thời điểm"]
    E --> F
    F --> G["Cập nhật backlog, năng lực và dependencies"]
    G --> H{"Must và DoD khả thi trong deadline?"}
    H -->|"Có, còn bất định"| I["Chọn lát cắt, giảm WIP, kiểm chứng sớm"]
    H -->|"Chưa rõ / không"| J["Đề xuất hoãn scope, thay phương án, đàm phán hoặc no-go"]
    J --> K["Người có thẩm quyền quyết định"]
    K --> I
    I --> L["Theo dõi Increment Done, quality và outcome"]
    L --> M{"Bằng chứng mới làm đổi dự báo?"}
    M -->|"Có"| G
    M -->|"Không"| N["Go/no-go có thẩm quyền, release và phản hồi"]
    N --> O["Review hậu sự kiện, cập nhật backlog/way of working"]
~~~

### 6.1. Hai vòng cần chạy song song

- **Vòng ứng phó khẩn:** Nhận diện → giảm tác động → điều tra → khôi phục/kiểm chứng → thông báo và học hỏi.
- **Vòng thích ứng kế hoạch:** Làm rõ yêu cầu → đánh giá phạm vi/năng lực → thương lượng → thực hiện Increment → cập nhật dự báo.

Nếu vụ việc nguy hiểm đang diễn ra, **vòng thứ nhất có quyền ưu tiên phù hợp theo chính sách**, trong khi PO và nhóm hỗ trợ cập nhật vòng thứ hai để minh bạch tác động tới ngày D.

## 7. Bước 1 — Tiếp nhận yêu cầu mới mà không vội cam kết

Khi đối tác đề nghị xác minh mã học viên, ba câu trả lời đầu tiên không nên là “được” hoặc “không được”, mà là:

1. **Vì sao có yêu cầu?** Chống người không đủ điều kiện, thống kê đối tác hay một quy định mới?
2. **Ai cần gì ở mốc nào?** Có bắt buộc ở D không? Nguồn xác nhận, hợp đồng, chính sách và người quyết định?
3. **Làm thế nào kiểm chứng?** API đối tác có thật, có test account, hợp đồng dữ liệu, điều kiện thất bại và bảo mật?

### 7.1. Mẫu intake yêu cầu thay đổi

~~~text
MA YEU CAU / NGAY NHAN:
NGUOI DE XUAT VA NGUON:
NGUOI SU DUNG / HIEU QUA MONG MUON:
VAN DE HOAC BANG CHUNG:
HANH VI / QUY TAC MOI:
NGAY CAN VA LY DO:
BAT BUOC THEO CAM KET? NGUON VA NGUOI XAC NHAN:
PHAM VI TAC DONG DEN PBI / SYSTEM / DATA:
DEPENDENCY (API, MOI TRUONG, QUYEN, DOI TAC):
RUI RO CHO NGUOI DUNG / SECURITY / VAN HANH:
TIEN DE, GIA DINH CHUA KIEM CHUNG:
CAC PHUONG AN GIAI QUYET:
NGUOI QUYET DINH VA MOC XEM LAI:
~~~

Mẫu này không phải artifact bắt buộc của Scrum; nhóm có thể ghi các thông tin ấy trực tiếp trong công cụ backlog đã chọn.

### 7.2. Không thể ưu tiên chính xác một yêu cầu chưa rõ

“Phải tích hợp API trước ngày D” chưa đủ để ước lượng hoặc thiết kế. Cần biết:

- API trả gì khi mã không tồn tại, lỗi mạng hoặc bị timeout?
- Một học viên có thể đăng ký khi đối tác tạm không phản hồi không?
- Dữ liệu cá nhân nào được truyền và có quyền xử lý không?
- Có yêu cầu lưu vết hoặc đối soát?
- Ai được quyền chọn fail-open/fail-closed? Rủi ro và cam kết nào áp dụng?

**Không tự chọn “cứ cho đăng ký nếu API timeout”** khi điều đó có thể vi phạm quy tắc xác minh. Chính sách lỗi cần được người có thẩm quyền xác nhận và được kiểm thử.

## 8. Bước 2 — Phân loại thay đổi bằng nguồn nghĩa vụ và giá trị

Một cách hỗ trợ thảo luận là chia theo **Must / Should / Could / Won't now** cho **mốc D cụ thể**, kết hợp nguồn ràng buộc và hậu quả nếu thiếu.

| Câu hỏi với CR-17 | Nếu trả lời như sau | Cách xử lý |
| --- | --- | --- |
| Có văn bản/cam kết xác nhận phải xác minh mã trước D? | Có, chủ cam kết xác thực | Xem là Must cho mốc D, đánh giá lại toàn bộ đường khả thi |
| Tính năng giúp giảm gian lận nhưng chưa có nghĩa vụ D? | Có giá trị, có thể triển khai sau | PO ưu tiên cạnh các hạng mục khác, chưa tự gọi là Must |
| API chưa sẵn sàng, đối tác chưa cấp môi trường? | Phụ thuộc lớn chưa được kiểm chứng | Spike/integration path sớm, ghi mốc quyết định |
| Có thể thỏa mãn mục đích bằng cách thay thế an toàn được chấp thuận? | Có, theo người có quyền | Đánh giá lựa chọn và hệ quả, không tự ý lách nghĩa vụ |
| Chưa xác minh nguồn/ngày? | Bất định quan trọng | Escalate làm rõ nhanh và cập nhật dự báo theo kịch bản |

### 8.1. Khi nào một Must mới làm thay đổi phần Must cũ?

Nếu xác minh học viên là bắt buộc để tạo đăng ký hợp lệ, nó cần trở thành **điều kiện chấp nhận của lát cắt đăng ký hoặc PBI phụ thuộc được quản lý rõ**. Nhưng điều đó **không làm kiểm tra quyền, tính đúng giao dịch hoặc xử lý lỗi trở thành Could**. Một yêu cầu Must mới làm **tăng nhu cầu năng lực hoặc buộc chọn phương án khác**, không giảm tiêu chuẩn cũ.

### 8.2. Khi nào cần từ chối yêu cầu ở mốc D?

Nếu CR-17 chỉ là mong muốn, PO có thể quyết định **không đưa vào phạm vi D**, lưu lý do và lộ trình xem lại. “Từ chối ở mốc này” khác với coi nhu cầu không có giá trị.

### 8.3. Kiểm chứng thay đổi bằng ví dụ

Một acceptance example cho CR-17 có thể là:

> “Khi mã học viên hợp lệ và còn chỗ, người học có thể được xác nhận; khi mã không hợp lệ, không có xác nhận. Nếu kết nối đối tác timeout, hệ thống xử lý theo chính sách đã được duyệt, không phát trạng thái thành công mơ hồ.”

Điều kiện cụ thể khi timeout cần **được làm rõ**, không tự đặt trong bài giả định như một luật phổ quát.

## 9. Bước 3 — Phân loại công việc khẩn theo tác động, không theo cảm tính

Một yêu cầu “làm gấp” có thể là:

- **Incident đang diễn ra:** Gây hoặc có nguy cơ gây tác động hiện tại tới bảo mật, dữ liệu, độ sẵn sàng hay người dùng.
- **Vulnerability hoặc rủi ro nghiêm trọng chưa có khai thác xác nhận:** Cần triage/giảm rủi ro theo chính sách, mức khẩn tùy tác động/khả năng khai thác.
- **Deadline rủi ro cao:** Công việc chưa gây tác động hiện tại nhưng có cửa sổ xử lý trước khi phát hành.
- **Expedite vì giá trị kinh doanh:** Có chi phí trì hoãn đặc biệt, được thẩm quyền cho phép ưu tiên.
- **Yêu cầu thường bị gắn nhãn khẩn:** Cần backlog refinement và ưu tiên bình thường.

### 9.1. Tách severity và priority

**Severity** nói về tác động/độ nghiêm trọng của sự cố hoặc lỗi. **Priority** là quyết định sắp thứ tự xử lý dựa trên tác động, khả năng, thời gian, nghĩa vụ và nguồn lực. Hai khái niệm liên quan nhưng **không phải một bảng tên cố định cho mọi tổ chức**.

| Tín hiệu | Tác động cần xác minh | Cách tiếp cận thường phù hợp |
| --- | --- | --- |
| Tài khoản B đọc được dữ liệu riêng của A | Rò rỉ quyền riêng tư, phạm vi tài khoản/số bản ghi | Kích hoạt security incident triage và giảm tác động theo quyền |
| Một trang mô tả UI có lỗi chính tả | Ảnh hưởng hiểu nội dung, có thể không khẩn | Đưa backlog, ưu tiên theo giá trị |
| Đối tác muốn logo mới ngay | Không rõ nghĩa vụ/ảnh hưởng | Xác minh yêu cầu, không tự tạo expedite |
| API thanh toán mất khả năng phục vụ | Tác động giao dịch người dùng | Incident response phù hợp |
| Test CI flaky nhưng chưa làm mất kiểm soát | Gây hàng đợi và rủi ro phát hành | Ưu tiên kỹ thuật theo rủi ro, không mặc định emergency |

### 9.2. Không đợi có đủ bằng chứng khai thác mới giảm tác động

Khi nghi ngờ có rò rỉ dữ liệu đang diễn ra, nhóm được ủy quyền có thể cần **tạm tắt đường truy cập bị ảnh hưởng, hạn chế phạm vi, thu thập log và thông báo theo quy trình**. Những lựa chọn cụ thể phải theo **chính sách, thẩm quyền, mức ảnh hưởng và tình trạng thực tế**; không có một lệnh “tắt hết service” phù hợp mọi tình huống.

### 9.3. Khẩn cấp không có nghĩa bỏ kiểm chứng

Một hotfix vội có thể tạo lỗ hổng khác. Quy trình khẩn có thể **rút gọn tuyến chờ** để giảm thời gian phản ứng, nhưng vẫn cần **review/test theo rủi ro, theo dõi sau thay đổi và đối soát người dùng bị ảnh hưởng**.

## 10. Bước 4 — Kích hoạt incident response đúng kênh

Đối với INC-04, nhóm không nên chỉ viết thêm một thẻ backlog “Fix auth bug — urgent” rồi chờ Sprint Planning. Cần làm rõ **ai đang điều hành ứng phó** và làm gì trước.

### 10.1. Chuỗi ứng phó có thể áp dụng theo chính sách

1. **Ghi nhận và xác định tín hiệu:** Thời gian, nơi phát hiện, phiên bản, endpoint, tài khoản thử đã khử dữ liệu.
2. **Triage tác động:** Dữ liệu gì có thể bị đọc, bao nhiêu người dùng, khả năng đang bị lạm dụng, nghĩa vụ báo cáo.
3. **Kích hoạt incident channel và người chỉ huy/điều phối** nếu mức độ yêu cầu.
4. **Giảm thiểu theo thẩm quyền:** Vô hiệu đường truy cập lỗi, giới hạn quyền hoặc biện pháp phù hợp, không phá hủy bằng chứng.
5. **Điều tra và kiểm chứng sửa:** Tái hiện lỗi với tài khoản được phép, sửa kiểm tra quyền ở nguồn thực thi, test regression.
6. **Khôi phục/mở lại có kiểm soát:** Quyết định theo bằng chứng, giám sát lỗi và tác động.
7. **Thông báo và đối soát:** Security/Privacy/Support xử lý thông tin người dùng và nghĩa vụ theo quy trình.
8. **Học hỏi sau sự cố:** Bổ sung test, runbook, tiêu chuẩn review và action item có người phụ trách.

### 10.2. Không đưa dữ liệu thật vào tài liệu luyện tập

Khi ghi ví dụ lỗi quyền, dùng **tài khoản thử hoặc dữ liệu đã được kiểm soát**. Không sao chép token, cookie, bản ghi người học, email riêng hoặc log nhạy cảm vào backlog công khai để “mọi người dễ sửa”.

### 10.3. Người nghỉ phép không phải phương án trực mặc định

Nếu chuyên gia phân quyền đang nghỉ, nhóm cần dùng **lịch trực, người dự phòng và đường escalation được ủy quyền**. Không mặc định người đang nghỉ luôn phải trả lời chat. Đây là lý do các quyết định và runbook quan trọng cần được chia sẻ trước sự cố.

## 11. Bước 5 — Đánh giá tác động của incident lên kế hoạch, không che đi

Incident sử dụng **năng lực đã từng được dành cho sản phẩm**. Không nên yêu cầu nhóm báo mọi PBI cũ giữ nguyên ngày mặc dù người review, CI và thời gian test đã bị chuyển hướng.

### 11.1. Ghi tác động theo thành phần

| Thành phần | Tín hiệu cần xem | Ví dụ tác động |
| --- | --- | --- |
| **Năng lực trực tiếp** | Ai đang ứng phó, số ngày-người bị chuyển | 6 ngày-người giả định cho điều tra/sửa/test |
| **Thời gian chờ** | Reviewer, quyền và môi trường test có bị chiếm? | PBI M2 chờ specialist đang xử lý INC-04 |
| **Rủi ro chất lượng** | Cần regression mới hoặc thẩm định mở rộng? | Kiểm tra mọi endpoint cùng chính sách quyền |
| **Phạm vi release** | Tính năng nào chưa thể mở an toàn? | Tạm giới hạn truy cập cho tới khi khắc phục |
| **Hỗ trợ và thông báo** | Ai tiếp nhận người dùng bị ảnh hưởng? | Support/Privacy phối hợp theo quy định |
| **Dự báo** | Từ giờ đến D còn năng lực hiệu quả nào? | Giảm năng lực còn lại, tăng độ bất định |

### 11.2. Ước lượng ban đầu không phải sự thật cuối

Con số **6 ngày-người** chỉ là giả định để thực hành. Nếu điều tra cho thấy lỗi tồn tại ở nhiều API, nỗ lực và tác động có thể tăng. **Cập nhật rủi ro và dự báo** là dấu hiệu minh bạch, không phải “đổi kế hoạch tùy tiện”.

### 11.3. Không dùng Sprint Goal để cản ứng phó an toàn

Khi có incident nghiêm trọng, nhóm cần ứng phó theo trách nhiệm hiện hành. Sau đó PO và Developers xem tác động tới Sprint Goal và kế hoạch. **Sprint Goal không phải lý do bỏ qua nguy cơ đang ảnh hưởng người dùng.**

## 12. Bước 6 — Phân biệt các quyền quyết định

Đây là điểm dễ bị nhầm khi deadline làm mọi người căng thẳng: ai đó có quyền xếp Product Backlog **không tự động có quyền miễn kiểm soát bảo mật**; một Incident Commander có thể điều hành ứng phó **không tự động thay đổi nghĩa vụ hợp đồng**.

| Quyết định | Chủ thể chịu trách nhiệm thường gặp | Điều cần lưu ý |
| --- | --- | --- |
| Sắp thứ tự Product Backlog | **Product Owner** trong Scrum | Có thể lắng nghe mọi stakeholder nhưng một accountable PO |
| Lựa chọn cách thực hiện, chia task và cập nhật Sprint Backlog | **Developers** trong Scrum | Chịu trách nhiệm tạo Increment đáp ứng DoD |
| Làm rõ/thương lượng scope trong Sprint | Developers và PO | Không làm nguy hại Sprint Goal hoặc giảm chất lượng |
| Hỗ trợ hiệu quả Scrum, tháo trở ngại | **Scrum Master** | Không phải quản lý phân công từng task |
| Xác nhận/thay đổi cam kết ngày D | Chủ cam kết/người được ủy quyền | PO không tự ý sửa nghĩa vụ ngoài quyền |
| Ứng phó sự cố và giảm tác động | Người được phân quyền trong incident/security process | Có thể cần hành động ngay, ghi bằng chứng |
| Chấp nhận rủi ro an toàn/tuân thủ | Người có thẩm quyền theo chính sách | Không miễn nghĩa vụ pháp lý bằng ý kiến cá nhân |
| Go/no-go hoặc rollout production | Vai trò hoặc hội đồng release được ủy quyền | Dựa trên chứng cứ chất lượng, bảo mật, giá trị và cam kết |

### 12.1. Cần bảng “ai quyết gì”, không nhất thiết một hội đồng cho mọi việc

Đặt cấp phê duyệt quá dày cho từng PBI có thể tạo thêm hàng đợi. Mục tiêu là **tự quản trong ranh giới**: những thay đổi thuộc thẩm quyền nhóm được xử lý nhanh, còn thay đổi về hợp đồng, pháp lý, an toàn và phát hành được chuyển đúng nơi.

### 12.2. Khi một người có nhiều vai trò

Trong tổ chức nhỏ, một người có thể đảm nhận nhiều trách nhiệm. Vẫn nên ghi rõ **họ đang quyết với tư cách nào, về phạm vi nào**, để giảm rủi ro “tôi nghĩ người khác đã phê duyệt”.

## 13. Bước 7 — Sắp lại Product Backlog bằng giá trị và ràng buộc

Sau khi phân loại incident và xác minh CR-17, PO cùng nhóm cần xem:

1. Những PBI nào **thật sự bắt buộc** cho ngày D?
2. Những PBI nào **có thể hoãn hoặc bỏ** mà không phá outcome?
3. Yêu cầu mới có thể **chia theo lát cắt có giá trị**, hay phải có đủ một cơ chế?
4. Những phụ thuộc nào cần xử lý **trước khi cam kết**?
5. Có rủi ro nào nếu tiếp tục nhiều PBI song song?
6. Kết quả incident có buộc thay đổi acceptance criteria/DoD hoặc các test khác?

### 13.1. Bảng Product Backlog sau biến cố, khi CR-17 chưa xác minh Must

| Hạng mục | Ưu tiên tạm | Trạng thái | Hành động ngay |
| --- | --- | --- | --- |
| INC-04 — khôi phục phân quyền đúng | **Ứng phó khẩn theo incident process** | Đang triage | Giảm tác động và test |
| M2 — đăng ký đúng và không vượt sức chứa | Must | Rủi ro concurrency | Kiểm thử sớm, tháo blocker |
| M3 — xem trạng thái đúng quyền | Must | Review quyền chưa xong | Kết hợp test regression incident |
| M1 — xem workshop | Must | Lát cắt cơ bản đang làm | Hoàn tất tới DoD, không mở thêm nhiều việc |
| M4 — giám sát/hỗ trợ/release | Must | Cần tham gia Operations | Chuẩn bị song song theo năng lực |
| CR-17 — xác minh mã học viên | **Chờ quyết định nghĩa vụ** | API/contract chưa rõ | Xác minh nguồn, spike và phương án |
| S1 — email nhắc | Should tùy cam kết | Chưa có contract test | Hoãn khi chưa thể cạnh tranh với Must |
| C1 — lọc/lịch nâng cao | Could | Có thể bắt đầu nhưng chưa cần | Không kéo mới khi WIP Must đang cao |

### 13.2. Nếu CR-17 được xác nhận Must

Đánh dấu nó Must và **tính lại đường khả thi**, không thay đổi DoD để “bù”. Có thể làm một lát cắt tích hợp xác minh mã đầu cuối hoặc một PBI phụ thuộc rõ, nhưng không được đánh dấu luồng đăng ký Done nếu điều kiện xác minh bắt buộc chưa đạt.

### 13.3. Nếu CR-17 không bắt buộc cho D

PO có thể ưu tiên nó sau mốc hoặc thiết kế một thử nghiệm giới hạn để học. Ghi rõ với đối tác **điều gì được giữ, điều gì được hoãn và bằng chứng/người quyết định**, tránh hiểu lầm “nhóm đang làm” thành “sẽ có trong release D”.

## 14. Bước 8 — Chia lát cắt để giao và nhận phản hồi sớm

Áp lực deadline thường khiến nhóm chia công việc thành nhiều task theo tầng: “DB”, “API”, “UI”, “QA”. Cách chia ấy hữu ích cho triển khai, nhưng **không đủ để chứng minh giá trị**.

### 14.1. Các lát cắt workshop có thể kiểm chứng

| Lát cắt | Giá trị có thể kiểm chứng | Điều kiện chất lượng quan trọng |
| --- | --- | --- |
| V1. Xem workshop đang mở | Người học hiểu thông tin và chỗ trống | Dữ liệu đúng, phân quyền phù hợp |
| V2. Đăng ký workshop còn chỗ | Học viên hợp lệ nhận đúng trạng thái xác nhận | Concurrent requests, không trùng, xử lý lỗi |
| V3. Xem đăng ký của mình | Học viên kiểm tra trạng thái độc lập | Không xem/sửa dữ liệu của người khác |
| V4. Xác minh điều kiện qua đối tác (nếu Must) | Chỉ người đủ điều kiện được xác nhận | Contract, timeout policy, data handling |
| V5. Email nhắc | Học viên nhận kênh thông tin bổ sung | Không gửi xác nhận sai, retry theo chính sách |

**Không được dùng thứ tự trong bảng để giả định release V2 trước V3/V4 luôn hợp lệ.** Nếu trạng thái hoặc xác minh mã là bắt buộc trước mở đăng ký, phải hoàn tất chúng trong phạm vi release D.

### 14.2. Một PBI có thể gồm nhiều task kỹ thuật

V2 có thể cần schema, API, UI, test và observability. **Từng task đạt trạng thái done không làm V2 thành Increment** nếu giao dịch đồng thời hoặc lỗi vẫn chưa được kiểm chứng.

### 14.3. Giảm kích thước lô bằng XP

Các thực hành có thể hỗ trợ:

- **TDD** hoặc test-first cho quy tắc có thể mô tả bằng ví dụ.
- **Continuous Integration** để phát hiện lỗi ghép thành phần sớm.
- **Pair programming/review sớm** tại nút thắt transaction/authorization.
- **Refactoring an toàn** để giữ khả năng thay đổi mà không làm hỏng hành vi cũ.
- **Small releases** khi guardrail cho phép.

Không dùng một unit test với repository giả để tuyên bố database thực đã xử lý tranh chỗ cuối đúng. Kiểm chứng phải phù hợp với **rủi ro thực của lát cắt**.

## 15. Scrum khi có yêu cầu mới và incident trong Sprint

Scrum tạo một nhịp **kiểm tra và thích ứng** chứ không hứa Sprint không bị xáo trộn. Trách nhiệm cốt lõi vẫn cần giữ:

| Thành phần Scrum | Ý nghĩa trong tình huống tích hợp |
| --- | --- |
| **Product Goal** | Vì sao sản phẩm tồn tại: học viên tự đăng ký an toàn, trạng thái đáng tin |
| **Product Backlog** | Danh sách có thứ tự, cập nhật khi có CR-17, kết quả incident và feedback |
| **Sprint Goal** | Mục tiêu đơn nhất của Sprint hiện tại, không phải danh sách tất cả task |
| **Sprint Backlog** | Sprint Goal, PBI đã chọn và kế hoạch thực hiện do Developers quản lý |
| **Definition of Done** | Ranh giới chất lượng chung để một Increment được coi hoàn tất |
| **Daily Scrum** | Developers kiểm tra tiến độ tới Sprint Goal và thích ứng kế hoạch |
| **Sprint Review** | Xem Increment thực và phản hồi để điều chỉnh Product Backlog |
| **Sprint Retrospective** | Kiểm tra cách phối hợp/kiểm thử/ứng phó và chọn cải tiến cụ thể |

### 15.1. Sprint Goal khác deadline bên ngoài

Giả sử Sprint Goal là:

> **“Học viên đủ điều kiện có thể đăng ký workshop còn chỗ và kiểm tra trạng thái chính xác trong phạm vi đã xác minh.”**

Ngày D là **mốc cam kết với đối tác**, có thể nằm sau Sprint hiện tại. Không phải vì có ngày D mà mọi story Should/Could đều trở thành Sprint Goal, hoặc phải kéo Sprint dài thêm tới D.

### 15.2. Những điều có thể thay đổi trong Sprint

Theo Scrum Guide 2020, trong Sprint:

- Không có thay đổi gây nguy hại **Sprint Goal**.
- **Chất lượng không được giảm.**
- **Product Backlog được refine khi cần.**
- Phạm vi có thể được **làm rõ và thương lượng với Product Owner** khi có kiến thức mới.

Developers có thể cập nhật Sprint Backlog, bỏ task không còn cần và ưu tiên giải quyết blocker. Điều này khác với việc **một quản lý thêm PBI vào Sprint rồi mặc nhiên giữ nguyên mọi cam kết cũ**.

### 15.3. Nếu incident chiếm phần lớn thời gian Sprint

Scrum Team cần kiểm tra còn đường hợp lý tới Sprint Goal không:

1. Cập nhật tình trạng thực của Increment và năng lực.
2. Xem incident có ảnh hưởng trực tiếp tới khả năng sản phẩm đạt mục tiêu hay không.
3. Làm rõ phần phạm vi có thể điều chỉnh với Product Owner.
4. Nếu Sprint Goal vẫn có ý nghĩa nhưng không còn chắc đạt, **minh bạch rủi ro và thích ứng**, không đánh dấu Done giả.
5. Nếu Sprint Goal **trở nên lỗi thời**, Scrum Guide cho phép **hủy Sprint và chỉ Product Owner có thẩm quyền hủy**.

**Một PBI trễ hoặc xuất hiện incident không tự động bắt buộc hủy Sprint**. Cũng không được dùng Sprint Goal như lý do từ chối xử lý rủi ro bảo mật hiện hữu.

### 15.4. Khi PBI chưa đạt Definition of Done

Nó **không được xem là Increment Done**. Phần chưa hoàn tất được đưa lại Product Backlog để xem xét, không tự kéo dài Sprint hoặc mặc định phải làm ngay trong Sprint tiếp theo.

Một demo của giao diện đã bấm được nút chưa chứng minh **luồng đăng ký an toàn** nếu giao dịch, quyền hoặc trạng thái vẫn lỗi.

## 16. Kanban và công việc khẩn: tạo đường xử lý nhưng tránh “expedite everything”

Kanban cung cấp góc nhìn về **dòng công việc**, làm rõ chính sách kéo việc, giới hạn WIP và theo dõi những item đang già đi. Đối với incident khẩn, một số nhóm sử dụng **class of service** và **expedite lane** như chính sách bổ sung.

### 16.1. Một chính sách phân loại minh họa

| Class of service minh họa | Dấu hiệu | Chính sách xử lý | Cạm bẫy |
| --- | --- | --- | --- |
| **Expedite** | Tác động hiện tại nghiêm trọng, nghĩa vụ hoặc chi phí trì hoãn đặc biệt; theo quyền đã định | Kích hoạt người phù hợp, làm trước phần thường, WIP có giới hạn | Mọi stakeholder xin nhãn expedite khiến cả board tắc |
| **Fixed date** | Phải đạt một điều kiện trước ngày cụ thể đã xác minh | Đặt mốc kiểm chứng sớm, theo dõi age/dependency | Chỉ làm sát ngày vì tưởng còn nhiều thời gian |
| **Standard** | Công việc giá trị bình thường | Kéo theo thứ tự ưu tiên và năng lực | Bị ngắt liên tục khiến không bao giờ Done |
| **Intangible / risk reduction** | Hạ tầng, test, kiến thức hoặc phòng ngừa rủi ro có lợi lâu dài | Đặt chính sách dành năng lực theo nhu cầu | Luôn bị hoãn vì không có giao diện mới |

Đây là **cách phân loại thực hành**, không phải toàn bộ tổ chức Kanban bắt buộc dùng đúng bốn lớp hoặc đúng tên.

### 16.2. Ví dụ board có đường khẩn

~~~text
EXPEDITE (chi khi du dieu kien): INC-04 — xu ly lo thong tin dang ky

READY:     M4 runbook (phan con lai), CR-17 can xac minh, S1 email
DOING:     M1 danh sach, M2 dang ky
REVIEW:    M3 quyen xem trang thai
VERIFY:    Kiem chung transaction, incident regression
DONE:      Chi cac lat cat da dat chinh sach Done

POLICY:
- Chi incident lead/nguoi duoc uy quyen kich hoat expedite theo tieu chi
- Ghi ly do, nguoi phu trach, ket qua can co va khi nao dong
- Ho tro hoan tat item cu truoc khi mo item thuong moi
- Neu expedite chiem het nang luc, cap nhat du bao/nguy co tai deadline
~~~

### 16.3. Expedite thường tạo chi phí cơ hội

INC-04 được xử lý trước có thể làm M2/M3 chờ review hoặc khiến S1/C1 không được triển khai. **Đó là sự lựa chọn hợp lý khi bảo vệ người dùng**, nhưng cần **nói thẳng ảnh hưởng tới dự báo**, không yêu cầu dòng thường giữ nguyên tốc độ như chưa có incident.

### 16.4. Giới hạn expedite WIP

Một nhóm có thể thử **tối đa một incident expedite** trong luồng kỹ thuật bình thường, trong khi **quy trình ứng phó nhiều sự cố đồng thời** cần cơ chế điều phối ưu tiên riêng. Không nên đặt “chỉ một expedite” như một luật cứng có thể khiến incident thứ hai nghiêm trọng bị bỏ mặc.

### 16.5. Không dùng Kanban để bỏ ưu tiên sản phẩm

Kanban giúp quản lý flow; việc quyết **hạng mục nào tạo giá trị và Must nào cần làm** vẫn cần trách nhiệm sản phẩm và ràng buộc tổ chức. Board đẹp không thể thay quyết định của Product Owner hoặc chủ cam kết.

## 17. Bốn flow metrics giúp ra quyết định trong tuần nhiều biến cố

| Chỉ số | Cách hiểu | Câu hỏi khi có CR-17 và INC-04 |
| --- | --- | --- |
| **WIP** | Số work item đã bắt đầu nhưng chưa Done trong ranh giới đã định | M2, M3 và incident đang cạnh tranh người review? |
| **Throughput** | Số item thật sự đạt Done trong một khoảng | Trong điều kiện tương tự nhóm thường hoàn tất bao nhiêu lát cắt? |
| **Work item age** | Thời gian item đang mở đã đi qua trong luồng | M2 có bị già đi bất thường do chờ integration test? |
| **Cycle time** | Thời gian một item đã Done đi từ start đến Done | Tích hợp và review có kéo dài hơn thường lệ? |

### 17.1. Thấy điểm nghẽn trước khi đếm thẻ

Nếu tất cả Developers đều đang coding nhưng chỉ có một người hiểu transaction, **WIP nhiều có thể tạo queue dài**. Hành động phù hợp có thể là pairing, review sớm, giảm việc mới hoặc chuẩn bị test để chuyên gia không mất thời gian lặp lại câu hỏi.

### 17.2. Work item age là tín hiệu cảnh báo sớm

Một PBI đang làm quá lâu không có nghĩa người thực hiện thiếu nỗ lực. Nó có thể do phụ thuộc, chờ quyết định, dữ liệu test hoặc sự cố chen ngang. Hãy xem **điểm chờ và hành động tháo blocker**, không dùng số tuổi thẻ để phạt cá nhân.

### 17.3. Throughput phải đo cùng loại công việc

Nếu nhóm chuyển từ user story hành vi sang đóng các task nhỏ “tạo class”, throughput có thể tăng nhưng **không chứng minh Increment tăng**. Định nghĩa Done và loại item phải được giữ minh bạch.

### 17.4. Không lấy một trung bình làm cam kết chắc chắn

Cycle time trung vị tốt nhưng có vài item kéo dài hai tuần có thể báo rủi ro lớn với fixed date. Xem **phân phối, tail, age của item mở, blocked time và dependency**.

## 18. Ước lượng lại năng lực sau khi có incident

Nhắc lại năng lực hiệu quả giả định **52 ngày-người** trong 15 ngày làm việc, sau khi đã trừ overhead dự kiến. Đây là một **khung cân đối nỗ lực**, không phải công cụ xác định chắc ngày hoàn tất.

### 18.1. Kế hoạch ban đầu không có dự phòng

\[
\begin{aligned}
\text{Must ban đầu}&=33\\
\text{Should}&=9\\
\text{Could}&=10\\
\text{Tổng dự kiến}&=52\\
\text{Năng lực hiệu quả}&=52
\end{aligned}
\]

Tổng vừa bằng năng lực **không có nghĩa an toàn**, vì không còn dự phòng cho điều tra, làm lại, review phức tạp hoặc phụ thuộc mới.

### 18.2. Khi INC-04 tiêu tốn 6 ngày-người

Trong mô hình minh họa, giả sử 6 ngày-người ứng phó không nằm trong overhead đã trừ:

\[
\text{Năng lực còn để thực hiện backlog đã dự kiến}
=52-6=46\text{ ngày-người}.
\]

Nếu chỉ giữ **Must ban đầu 33**, phần nỗ lực dự kiến còn lại khoảng:

\[
46-33=13\text{ ngày-người}.
\]

13 không phải **“ngân sách tự do để làm Should”**. M2 có rủi ro chưa giải quyết và khoảng năng lực đó còn phải hấp thụ độ bất định. Nếu không có xác nhận CR-17 là Must, PO vẫn có thể quyết định **hoãn S1/C1** để tạo dư địa.

### 18.3. Khi CR-17 được xác nhận Must, thêm 8 ngày-người

Giả sử các con số không chồng lặp nỗ lực và chưa đổi nhờ giải pháp khác:

\[
\begin{aligned}
\text{Must mới}&=33+8=41\\
\text{Năng lực sau incident}&=46\\
\text{Khoảng nỗ lực còn lại}&=46-41=5
\end{aligned}
\]

Với **5 ngày-người trên giấy** còn lại trước khi cộng bất định, **không có căn cứ để hứa thêm S1 (9) hoặc C1 (10)**. Ngay cả Must 41 cũng **chưa chắc khả thi theo ngày lịch**, vì API đối tác có thể chờ nhiều ngày và test concurrency có thể phát hiện lỗi mới.

### 18.4. Khi CR-17 chỉ là Should

PO có thể giữ Must ban đầu 33 và đưa CR-17 vào thứ tự ưu tiên sau mốc D. Nhưng nếu một phần yêu cầu CR-17 thật sự cần để đăng ký hợp lệ trong phạm vi người dùng được mở, không được gọi nó Should **chỉ để phép tính đẹp**.

### 18.5. Nếu năng lực thực tế giảm thêm

Giả sử môi trường test bị gián đoạn tương đương 4 ngày-người hiệu quả nữa:

\[
52-6-4=42\text{ ngày-người}.
\]

Nếu Must là 41, chỉ còn **1 ngày-người trong mô hình thô**, chưa tính chờ theo lịch và xác suất phát sinh lỗi. Đây là tín hiệu cần **escalate phương án phạm vi/mốc**, không chờ đến ngày D mới báo.

### 18.6. Không cộng nỗ lực trùng

Nếu sửa INC-04 và M3 cùng dùng một regression suite, có phần công việc trùng nhau. Nhóm nên rà soát để **không đếm hai lần**. Ngược lại, nếu phát hiện bug ảnh hưởng nhiều endpoint, nỗ lực incident tăng. **Số liệu phải được cập nhật theo bằng chứng chứ không giữ bất biến chỉ vì bảng ban đầu đẹp.**

## 19. Ngày-người, ngày lịch và critical dependency không giống nhau

**8 ngày-người** có thể là một Developer làm tám ngày hoặc nhiều người phối hợp với kết quả khác nhau; không tự suy thành “hai người làm bốn ngày chắc xong”.

### 19.1. Ví dụ đường phụ thuộc của CR-17

1. Đối tác xác nhận **contract và quy tắc lỗi**.
2. Cấp quyền sandbox/test account.
3. Developers thử tích hợp tối thiểu.
4. Thẩm định truyền dữ liệu và kiểm soát bảo mật.
5. Tích hợp luồng đăng ký, xử lý timeout/retry.
6. Chạy test contract, end-to-end và một số tình huống lỗi.
7. Review kết quả và quyết định release.

Nếu **bước 2 phải chờ đối tác năm ngày lịch**, thêm Developer không tự tạo quyền sandbox sớm hơn. Cần chủ phụ thuộc, mốc phản hồi và phương án escalation.

### 19.2. Bản đồ dependency

~~~mermaid
flowchart LR
    A["Đối tác xác nhận contract"] --> B["Sandbox / quyền test"]
    B --> C["Spike tích hợp API"]
    C --> D["Luồng xác minh trước đăng ký"]
    E["M2: giao dịch giữ chỗ"] --> F["Kiểm chứng end-to-end"]
    D --> F
    G["M3 + sửa INC-04: quyền dữ liệu"] --> F
    F --> H["DoD + kiểm thử hồi quy"]
    H --> I["Go/no-go / release D"]
    J["M4: giám sát, Support, runbook"] --> I
~~~

### 19.3. Hai loại rủi ro kế hoạch

- **Nỗ lực vượt khả năng:** Cần giảm scope, thay cách thực hiện hoặc đầu tư năng lực khi có lợi thật.
- **Đường phụ thuộc theo lịch không kịp:** Cần phối hợp đối tác sớm, thay phương án được chấp thuận hoặc đàm phán; cộng thêm ngày-người có thể không giải được.

### 19.4. Không “giải quyết” bằng ép làm thêm giờ kéo dài

Làm thêm giờ không loại bỏ hàng đợi quyền, review hoặc lỗi tích hợp; còn có thể tăng lỗi ở phần dữ liệu. Nhịp làm việc bền vững là **điều kiện hỗ trợ chất lượng và khả năng ứng phó khẩn cấp**.

## 20. Forecast bằng dữ liệu lịch sử và nêu rõ bất định

Giả sử nhóm quan sát throughput các PBI **đạt Done theo cùng quy tắc** trong sáu tuần trước:

| Tuần | Số PBI đạt Done |
| --- | ---: |
| 1 | 4 |
| 2 | 3 |
| 3 | 5 |
| 4 | 4 |
| 5 | 2 |
| 6 | 4 |

Trung bình mô tả:

\[
\bar{t}=\frac{4+3+5+4+2+4}{6}
=\frac{22}{6}
\approx3{,}67\text{ PBI/tuần}.
\]

### 20.1. Vì sao không dùng 3,67 để hứa giao hết?

Trong 15 ngày làm việc thường tương đương **ba tuần làm việc**, phép nhân sơ bộ:

\[
3\times3{,}67\approx11\text{ PBI}.
\]

Nhưng:

- PBI còn lại có thể lớn/hơn rủi ro so với lịch sử.
- Incident làm đổi thành phần công việc.
- CR-17 có phụ thuộc mới, không giống PBI quen thuộc.
- Cách chia story có thể thay đổi đơn vị đếm.
- Sự cố môi trường và người nghỉ phép làm đổi throughput.
- Số liệu quan sát ít và có biến động.

Vì vậy **11 không phải cam kết**. Đây chỉ là một góc kiểm tra sự hợp lý, không thay phân tích Must và dependency.

### 20.2. Dự báo theo kịch bản

| Kịch bản | Giả định | Hệ quả ra quyết định |
| --- | --- | --- |
| **Thuận lợi** | Incident được khống chế, sandbox tới đúng hẹn, test M2 đạt | Có khả năng tập trung hoàn tất Must, xem Should sau khi guardrail ổn |
| **Cơ sở** | Incident tiêu tốn khoảng 6 ngày-người, CR-17 là Must 8 ngày-người, test không có lỗi lớn mới | Must chiếm gần hết năng lực; cần hoãn Should/Could |
| **Bất lợi** | CR-17 trễ sandbox, môi trường test gián đoạn, lỗi phân quyền lan rộng | Must có thể không đạt D; escalate phương án/đàm phán/no-go sớm |

Đây là **kịch bản điều kiện**, không phải xác suất 70% hay 90% được tính từ một mô hình thống kê. Nếu tổ chức có dữ liệu đủ và phương pháp phù hợp, có thể dùng mô phỏng xác suất, nhưng phải nói rõ cách lấy dữ liệu và các giới hạn.

### 20.3. Cập nhật forecast vào đúng mốc học hỏi

Thay vì mỗi ngày gửi một “phần trăm hoàn thành” không có nghĩa, đặt các cổng:

- Sau xác nhận cam kết CR-17.
- Sau spike API đối tác và cấp sandbox.
- Sau regression/incident containment.
- Sau integration test giao dịch đồng thời.
- Trước quyết định release candidate.

Ở mỗi cổng, cập nhật **giả định nào còn đúng, Must nào Done, rủi ro nào mới và phương án nào còn khả thi**.

## 21. Dùng MoSCoW hoặc các nhóm ưu tiên mà không giấu độ khó

MoSCoW có thể giúp thảo luận Must/Should/Could/Won't cho mốc D, nhưng **gắn nhãn chưa phải kế hoạch**.

### 21.1. Cần giữ tiêu chí cho Must

Một hạng mục Must nếu thiếu sẽ làm **không đạt outcome bắt buộc, vi phạm nghĩa vụ hoặc không bảo đảm an toàn trong phạm vi mở**. Mỗi Must nên có **lý do, người xác nhận, tiêu chí nghiệm thu và dependency**.

### 21.2. Khi Must chiếm quá nhiều

Nếu Must đã gần bằng toàn bộ năng lực còn lại, nhóm không nên:

- Gọi Should là “Must ẩn” để đảm bảo vẫn làm.
- Giảm kiểm thử để “nén Must”.
- Cắt trường hợp bảo mật rồi coi là giảm scope.
- Giữ tiến độ cũ trên dashboard dù có incident.

Thay vào đó, xem có thể **chia giải pháp hợp lệ** hoặc **điều chỉnh cam kết với người có quyền**, rồi cập nhật dự báo.

### 21.3. “Won't this time” không có nghĩa vô giá trị

C1 lọc nâng cao có thể vẫn có giá trị cho trải nghiệm dài hạn. Nhưng nếu nó cạnh tranh với M2 giao dịch chưa đạt test và INC-04 chưa khắc phục, **không kéo C1 vào thực hiện ở mốc D** là một quyết định sản phẩm có căn cứ.

### 21.4. Đối với tiêu chuẩn chất lượng

Chống truy cập trái phép, xác nhận vượt sức chứa và bảo đảm trạng thái đúng **không nên được dán nhãn Could** nếu chúng thuộc điều kiện của tính năng đang mở. Những điều đó là **phần của chất lượng và acceptance**, không phải tiện ích bổ sung.

## 22. Bảng phương án: phải thể hiện lựa chọn thực, không hỏi “có làm hết không?”

Khi incident và yêu cầu mới làm kế hoạch căng, PO cùng chủ cam kết cần có **lựa chọn được trình bày trung thực**.

| Phương án | Mô tả | Lợi ích | Điều kiện/rủi ro | Người có quyền |
| --- | --- | --- | --- | --- |
| **A. Giữ D, chỉ phạm vi Must đã xác minh** | Hoãn email/lọc, ưu tiên đăng ký đúng, xác minh mã nếu Must, an toàn và Support | Tập trung đạt outcome bắt buộc | Must vẫn có rủi ro deadline và dependency | PO + chủ cam kết + release authority |
| **B. Giữ D, giải pháp xác minh khác được phê duyệt** | Thay tích hợp đầy đủ bằng cơ chế đáp ứng mục đích được phép | Có thể giảm phụ thuộc API | Phải chứng minh đúng nghĩa vụ, bảo mật, khả năng vận hành | Chủ cam kết và chức năng liên quan |
| **C. Mở theo pha** | Mở từng nhóm/ngưỡng nếu hợp đồng cho phép | Giới hạn tác động và học sớm | Có thể không thỏa cam kết mở cho toàn bộ; không miễn test | Chủ cam kết + product/release |
| **D. Thỏa thuận lại phạm vi/ngày** | Đàm phán điều kiện D, phạm vi hoặc phương án hậu sự kiện | Giữ chất lượng và tính trung thực | Ảnh hưởng thương mại/trải nghiệm, cần phê duyệt | Người có thẩm quyền đàm phán |
| **E. No-go nếu không có phương án an toàn** | Không mở luồng gây hại, có kế hoạch thông báo/hỗ trợ | Bảo vệ dữ liệu/người dùng | Chưa đạt mốc; xử lý nghĩa vụ và hệ quả | Release/incident và chủ cam kết theo quyền |

### 22.1. Không có phương án nào đúng tuyệt đối

Nếu hợp đồng yêu cầu email xác nhận và mở toàn bộ học viên vào D, phương án A hoặc C như mô tả **có thể chưa hợp lệ**. Nếu test giao dịch đang thất bại, A/B/C **chưa đủ điều kiện release** dù phạm vi ít hơn.

### 22.2. Mỗi phương án cần người quyết và thời điểm

Ví dụ:

- Chủ cam kết xác minh CR-17 trước mốc X.
- Operations/Security xác nhận đường khắc phục INC-04 trước mốc Y.
- Nhóm thực hiện test integration trước mốc Z.
- Quyết định go/no-go dựa trên bằng chứng tại mốc R.

Không đưa lịch X/Y/Z/R như **sự kiện đã chắc xảy ra** nếu phụ thuộc chưa phản hồi; cần ghi rõ owner và phương án nếu quá hạn.

## 23. Đàm phán phạm vi: một cuộc nói chuyện mẫu

> **Đối tác:** “Thêm xác minh mã học viên vào ngày D. Ngày đã công bố thì không đổi.”
>
> **Product Owner:** “Chúng tôi cần xác nhận nghĩa vụ hiện hành và kết quả bắt buộc. Quy định xác minh mã là điều kiện của lần mở đầu hay đề nghị tăng cường? Ai được quyền xác nhận?”
>
> **Chủ cam kết:** “Tôi sẽ đối chiếu hợp đồng và gửi kết luận. Nếu là bắt buộc, phải có bằng chứng tương thích API và xử lý thất bại.”
>
> **Developers:** “Trong 52 ngày-người năng lực dự kiến, Must ban đầu khoảng 33; sự cố phân quyền đang tiêu tốn năng lực và yêu cầu mới cần thử API. Chúng tôi chưa thể bảo đảm toàn bộ email/lịch nâng cao vẫn giao đúng D. Chất lượng đăng ký và phân quyền không thể hạ.”
>
> **Người vận hành:** “Chúng tôi đang giảm tác động của INC-04; trước mở lại luồng phải có regression, quan sát và đường Support.”
>
> **Đối tác:** “Chúng tôi vẫn muốn email nhắc.”
>
> **Product Owner:** “Email có giá trị, nhưng xin phân biệt với điều kiện cần cho ngày D. Chúng tôi đề xuất giữ lõi đăng ký an toàn, xác minh mã nếu được xác nhận Must, rồi xem lại email khi có kết quả tích hợp. Nếu Must không còn khả thi, chúng tôi sẽ đưa phương án khác tới người có quyền trước mốc quyết định.”

### 23.1. Điều cuộc trao đổi đạt được

- Tách **nhu cầu, ràng buộc, giải pháp và mong muốn**.
- Đưa **năng lực và rủi ro** thành dữ kiện, không đổ lỗi.
- Phân biệt **đề xuất scope** với **thay đổi cam kết đã được phê duyệt**.
- Đặt mốc ra quyết định có người phụ trách.
- Không dùng Agile như lý do trốn trách nhiệm.

### 23.2. Tránh nói “sẽ cố” như một quyết định

“Chúng tôi sẽ cố gắng làm hết” không giúp stakeholder biết **cái gì chắc chắn chưa được kiểm chứng, lựa chọn nào cần họ đồng ý và hậu quả nếu không quyết kịp**.

## 24. Giữ Definition of Done và acceptance criteria khi phạm vi đổi

**Acceptance criteria** mô tả hành vi cụ thể của từng PBI. **Definition of Done** là cam kết chất lượng chung của Increment trong Scrum. Cả hai phải được hiểu đúng khi thay đổi phạm vi.

### 24.1. Ví dụ acceptance cho đăng ký workshop

~~~gherkin
Feature: Đăng ký workshop đúng điều kiện

  Scenario: Học viên hợp lệ đăng ký workshop còn chỗ
    Given học viên có tài khoản và đủ điều kiện theo chính sách đang áp dụng
    And workshop đang mở đăng ký và còn chỗ
    When học viên yêu cầu đăng ký
    Then không vượt sức chứa khi lưu xác nhận
    And học viên nhận được trạng thái dựa trên dữ liệu đã lưu

  Scenario: Học viên không đủ điều kiện
    Given học viên không đáp ứng quy tắc xác minh bắt buộc
    When học viên yêu cầu đăng ký
    Then hệ thống không tạo xác nhận thành công
    And học viên nhận phản hồi phù hợp

  Scenario: Một tài khoản cố truy cập đăng ký của tài khoản khác
    Given học viên A có đăng ký riêng
    And học viên B đã đăng nhập
    When B yêu cầu xem đăng ký của A
    Then yêu cầu bị từ chối theo chính sách phân quyền
    And hệ thống không tiết lộ dữ liệu riêng của A
~~~

Đây là **các ví dụ hành vi**, chưa phải mã test thực thi. Kịch bản transaction tranh chỗ cuối phải được kiểm chứng với **cơ chế lưu trữ/đồng thời phù hợp**; không chỉ dùng mock một luồng.

### 24.2. Khi API đối tác timeout

Không tự giả định **“timeout thì cho qua”** hoặc **“timeout thì xóa ngay mọi dữ liệu”**. Để chốt acceptance, cần xác minh:

- Có được lưu yêu cầu ở trạng thái chờ không?
- Có được xác nhận chỗ trước khi xác minh xong không?
- Hạn xử lý, retry và idempotency?
- Thông tin nào được truyền và lưu?
- Người dùng thấy trạng thái gì, Support đối soát thế nào?
- Chính sách nào được bên có quyền chấp thuận?

### 24.3. Cắt tiện ích, không cắt lỗi đã biết

Đúng: “Hoãn bộ lọc nâng cao vì hành trình tìm workshop cơ bản đã có và không là Must cho D.”

Sai: “Tạm bỏ integration test phân quyền và sửa INC-04 sau khi mở cho người dùng.”

### 24.4. Không gọi hotfix thành công chỉ vì lệnh deploy chạy

Hotfix cần kiểm chứng **vấn đề đã được giảm/khắc phục, không gây lỗi mới, dữ liệu người dùng được bảo vệ, hệ thống có thể quan sát và hồi phục**. DoD hoặc quality gate có thể được **triển khai theo quy trình khẩn khác với thường lệ**, nhưng không đồng nghĩa giảm yêu cầu an toàn bắt buộc.

## 25. Điều kiện release: từ Increment tới người dùng

**Increment đạt DoD** và **quyết định release** liên quan nhưng không hoàn toàn trùng nhau. Một Increment có thể được tích hợp và sử dụng được, trong khi việc mở cho người dùng còn phụ thuộc **cam kết, độ sẵn sàng vận hành, thẩm quyền và an toàn**.

### 25.1. Quality gate minh họa cho ngày D

| Nhóm kiểm chứng | Bằng chứng cần có | Nếu chưa đạt |
| --- | --- | --- |
| **Build/CI** | Artifact, phiên bản và pipeline bắt buộc đạt | Không giả báo release candidate hoàn chỉnh |
| **Giao dịch** | Test không vượt sức chứa, không tạo xác nhận trùng trái chính sách | Không mở đường đăng ký rủi ro |
| **Phân quyền** | Regression trên các endpoint liên quan, truy cập khác chủ bị từ chối | Giữ đường truy cập lỗi bị kiểm soát, xử lý incident |
| **Đối tác** | Contract/API integration và cách xử lý timeout đã duyệt | Dùng phương án hợp lệ hoặc chưa mở phạm vi cần |
| **Hành trình người học** | End-to-end từ chọn buổi tới trạng thái xác nhận | Làm rõ/sửa nếu kết quả mơ hồ |
| **Vận hành** | Alert, logging phù hợp, runbook, người hỗ trợ, quyền | Bổ sung trước khi mở nếu là điều kiện bắt buộc |
| **Bảo mật/riêng tư** | Điều kiện dữ liệu và nghĩa vụ được xác nhận | Không tự miễn rủi ro bằng lời hứa sau này |
| **Cam kết D** | Phạm vi, đối tượng, ngày và các phê duyệt hợp lệ | Đưa chủ cam kết ra quyết định |

### 25.2. Phân biệt feature flag và chất lượng

Feature flag, canary hoặc mở nhóm nhỏ **có thể giúp kiểm soát phạm vi tác động và nhận feedback**, nhưng không hợp thức hóa một lỗi phân quyền đã biết. Không “test trên người dùng thật” khi đã có nguy cơ dữ liệu nghiêm trọng chưa giảm thiểu.

### 25.3. Rollback code có thể không rollback trạng thái

Một thay đổi đã tạo bản ghi đăng ký sai, gửi email hoặc lộ dữ liệu **không được sửa trọn vẹn chỉ bằng deploy phiên bản cũ**. Kế hoạch cần cách đối soát dữ liệu, hỗ trợ người dùng, thông báo theo nghĩa vụ và quyết định có thẩm quyền.

### 25.4. Go/no-go cần ghi lý do và giới hạn

Quyết định **go** phải nói rõ phạm vi mở, bằng chứng, rủi ro được chấp nhận đúng quyền và tín hiệu dừng mở rộng. Quyết định **no-go** phải ghi mức tác động, người được thông báo và phương án tiếp, không chỉ viết “chưa đạt”.

## 26. Timeline ra quyết định: chọn điểm kiểm chứng thay vì đợi ngày cuối

Trong case còn 15 ngày làm việc, có thể lập **timeline tương đối**. Các mốc chỉ minh họa, cần điều chỉnh theo lịch thật và độ dài Sprint hiện có.

| Mốc tương đối | Điều cần xảy ra | Quyết định/Bằng chứng |
| --- | --- | --- |
| **D-15 đến D-13** | Triage INC-04, giảm tác động; xác minh nguồn CR-17 | Severity/phạm vi ảnh hưởng, nghĩa vụ CR-17, owner |
| **D-13 đến D-11** | Thử contract đối tác, kiểm tra quyền/test environment, đóng băng việc mở Could mới | Bằng chứng dependency và forecast cập nhật |
| **D-10 đến D-7** | Hoàn tất lát cắt Must, regression trên quyền và transaction | Những PBI nào thật sự đạt DoD |
| **D-7 đến D-5** | End-to-end, review bảo mật/vận hành, thẩm định phương án D | Có thể tiếp tục, điều chỉnh scope hoặc chuẩn bị no-go |
| **D-5 đến D-2** | Release candidate, vận hành thử, hỗ trợ, decision review | Điều kiện go/no-go và phương án thông báo |
| **D-1 đến D** | Chỉ mở theo phê duyệt, quan sát, ứng phó nếu cần | Người dùng nhận đúng khả năng đã cam kết |
| **Sau D** | Đối soát outcome, incident review, Retrospective | Backlog và quy trình được cải tiến |

**Lưu ý:** D-15 tới D-1 không có nghĩa luôn có đủ 15 ngày để code; có thời gian kiểm thử, quyền đối tác, triển khai và giám sát. Không tự biến giai đoạn release readiness thành “buffer miễn phí” để nhồi tính năng.

### 26.1. Thực tế có thể buộc quyết định sớm hơn

Nếu đối tác cấp sandbox quá muộn khiến CR-17 Must không còn đường kiểm chứng, không nên chờ D-2 mới hỏi chủ cam kết. **Mốc ra quyết định phải trước mốc mất lựa chọn**, không chỉ trước ngày mở một khoảng tùy ý.

### 26.2. Không đóng băng học hỏi

Một lịch phát hành có giai đoạn ổn định không có nghĩa ngừng sửa rủi ro nghiêm trọng hoặc cập nhật forecast. Nó cần **chính sách thay đổi phù hợp mức rủi ro**, không phải “không ai được nói tin xấu”.

## 27. Truyền thông: ba thông điệp cho ba nhóm người nhận

Một bản cập nhật tốt tránh câu “chúng tôi gặp sự cố nhưng vẫn cố giao hết”. Người nhận khác nhau cần thông tin khác nhau.

### 27.1. Với Product Owner và stakeholder

Tập trung:

- Outcome và phạm vi D đã được xác minh.
- Điều gì Done, điều gì chưa đủ chất lượng.
- Yêu cầu mới có Must hay không và nguồn xác nhận.
- Dự báo, lựa chọn và hạn quyết định.
- Rủi ro với người dùng/đối tác, không chỉ % tiến độ.

### 27.2. Với Developers và nhóm phối hợp

Tập trung:

- Sprint Goal và chính sách WIP/expedite.
- Các PBI Must đang bị chặn, người review, contract.
- Acceptance examples và test regression.
- Trạng thái incident, thẩm quyền, thông tin không được chia rộng.
- Lịch kiểm chứng và điều kiện Done.

### 27.3. Với Security, Support, Operations

Tập trung:

- Tác động người dùng, phạm vi rủi ro và tình trạng giảm thiểu.
- Các thay đổi production và đường rollback/đối soát.
- Ai đang trực và thẩm quyền của từng bước.
- Kênh thông báo nếu có nghĩa vụ, dữ liệu nào được phép chia.
- Cách xác nhận chức năng mở lại an toàn.

### 27.4. Mẫu cập nhật một trang

~~~text
NGAY / MOC D / DOI TUONG CAP NHAT:
OUTCOME BAT BUOC:
PHAM VI DA DUOC XAC NHAN:

THUC TRANG:
- Increment/PBI da Done:
- Chua Done va vi sao:
- RUI RO CHO NGUOI DUNG:

THAY DOI MOI:
- CR-17: nghia vu da xac nhan hay chua; dependency:
- INC-04: trang thai ung pho, tac dong vao nang luc:

DU BAO VA GIA DINH:
- Nang luc con lai:
- Must con lai:
- Moc can bang chung:
- Dieu chua biet:

PHUONG AN CAN QUYET:
- Pham vi giu/hoan:
- Alternative/release theo pha neu duoc phep:
- No-go neu khong an toan:

AI CO QUYEN QUYET / HAN:
NGAY CAP NHAT TIEP THEO:
~~~

Một trạng thái **“chưa rõ” được ghi đúng** có giá trị hơn một phần trăm tiến độ có vẻ chắc chắn nhưng không có nguồn.

## 28. Những cuộc họp nào cần, cuộc họp nào chỉ tạo thêm chờ?

Trong giai đoạn căng, thêm họp liên tục có thể lấy mất năng lực quan trọng. Chọn **định dạng phối hợp theo mục đích**.

| Nhu cầu | Hình thức thường phù hợp | Đầu ra |
| --- | --- | --- |
| Ứng phó lộ dữ liệu đang diễn ra | Incident bridge/kênh khẩn theo chính sách | Điều phối, giảm tác động, timeline, quyết định |
| Làm rõ CR-17 | Trao đổi ngắn PO–đối tác–Developers–bảo mật phù hợp | Nghĩa vụ, examples, dependency, người xác nhận |
| Thích ứng kế hoạch Sprint | Developers trong Daily Scrum và phối hợp với PO khi cần | Sprint Backlog thực tế, blocker, scope thương lượng |
| Quyết định đổi cam kết | Hội ý người có thẩm quyền với phương án đã chuẩn bị | Quyết định có lý do và thông báo |
| Review Increment | Sprint Review hoặc buổi feedback phù hợp | Phản hồi sản phẩm và Product Backlog mới |
| Học sau incident/Sprint | Post-incident review, Sprint Retrospective | Hành động cải tiến có owner/điều kiện kiểm chứng |

### 28.1. Không biến Daily Scrum thành status meeting cho mọi quản lý

Daily Scrum là cơ hội để Developers kiểm tra tiến độ tới Sprint Goal và thích ứng kế hoạch. Một báo cáo quản trị về deadline D có thể cần thực hiện **riêng hoặc bất đồng bộ**, không chiếm hết thời gian cùng giải quyết vấn đề của Developers.

### 28.2. Trao đổi bất đồng bộ cũng phải đủ ngữ cảnh

Nếu nhóm khác múi giờ, một tin nhắn “gấp xem API” khó giúp người nhận hành động. Nêu **môi trường, điều đã thử, log đã khử dữ liệu, câu hỏi, hạn phản hồi và kênh escalation khi nghiêm trọng**.

## 29. Giữ sức khỏe nhóm khi công việc khẩn lặp lại

Đối phó một incident có thể cần tập trung cao, nhưng nếu tuần nào cũng phải “expedite tất cả”, tổ chức có thể đang gặp **vấn đề năng lực, nợ kỹ thuật, vận hành hoặc quản trị ưu tiên**.

### 29.1. Các dấu hiệu cảnh báo

- WIP tăng dù số người bận rất cao.
- Mọi stakeholder đặt nhãn “urgent” để chen queue.
- Review, test và security luôn bị hoãn.
- Người trực incident không còn thời gian hồi phục.
- Sprint Goal thường xuyên mất điều kiện nhưng không ai cập nhật cam kết.
- Giờ ngoài lịch kéo dài thành năng lực mặc định.
- Team bị chấm bằng số task/commit thay vì khả năng hoàn tất và chất lượng.

### 29.2. Biện pháp hệ thống

1. Xác định **nguyên nhân lặp lại của incident**, đưa phòng ngừa vào backlog.
2. Chuẩn hóa **triage và class of service** theo mức tác động.
3. Có **năng lực dự phòng hoặc lịch trực phù hợp**, không coi người nghỉ luôn online.
4. Đầu tư vào test, CI, quan sát, runbook và quyền self-service.
5. Giới hạn WIP, swarming khi cần, tránh mở việc mới trong lúc Must bị chặn.
6. Truyền thông forecast khi expedite ăn vào năng lực, không giữ cam kết giả.
7. Đánh giá tác động tới **sức khỏe nhóm và chất lượng sau release**, không chỉ tốc độ phản ứng.

### 29.3. “Nhanh” cần được định nghĩa đúng

Phản ứng nhanh với incident là **giảm tác động và khôi phục đúng cách**. Thực hiện nhanh tính năng là **đưa phần giá trị đạt Done vào sử dụng an toàn**. Cả hai khác với “đóng nhiều thẻ” hoặc “mọi người làm đủ 12 giờ mỗi ngày”.

## 30. Rủi ro và giả định: một register nhỏ đủ để hành động

Không cần tạo hàng trăm ô quản trị. Một bảng rủi ro có thể chứa:

| ID | Rủi ro/giả định | Tín hiệu/ảnh hưởng | Hành động trước hạn | Owner/quyền quyết | Mốc xem lại |
| --- | --- | --- | --- | --- | --- |
| R1 | Lỗi phân quyền chưa được khống chế hoàn toàn | Dữ liệu riêng có thể bị truy cập | Incident triage, giảm tác động, regression | Security/incident lead | Khi có kết quả điều tra |
| R2 | M2 không xử lý concurrency | Xác nhận vượt sức chứa | Test dữ liệu thật, sửa giao dịch | Developers/technical review | Trước release candidate |
| R3 | CR-17 là Must nhưng sandbox trễ | Không xác minh được mã trước D | Xác nhận nghĩa vụ, contract test, escalation | Chủ cam kết/đối tác/Developers | Trước khi mất phương án thay thế |
| R4 | QA/reviewer thành bottleneck | PBI lâu Done, thiếu feedback | Giảm WIP, swarming/review sớm | Team/các nhóm phụ thuộc | Mỗi kỳ kiểm tra flow |
| R5 | Năng lực giảm sau incident | Must chưa khả thi | Dự báo lại, bỏ Should/Could, trình options | PO/chủ cam kết | Khi scope và tác động rõ |
| R6 | Chỉ số bị làm đẹp | Thẻ Done nhưng Increment chưa kiểm chứng | Giữ DoD, xem outcome/flow/quality | Scrum Team | Sprint Review |

### 30.1. Rủi ro phải có hành động và tín hiệu

Một cột “High” không trả lời **ai làm gì trước khi mất cơ hội quyết định**. Với rủi ro quan trọng, cần dấu hiệu kiểm chứng, người phụ trách và đường escalation.

### 30.2. Phân biệt unknown và blocker

CR-17 chưa rõ nghĩa vụ là **bất định cần xác minh**; chưa có sandbox khiến không thể chạy integration test là **blocker đã hiện hữu**. Cần nêu cả hai để không ngầm coi một phần chưa biết là đã ổn.

## 31. Mẫu decision log để người vắng mặt theo kịp

Khi một nhóm phân tán phải thay ưu tiên nhanh, quyết định không nên chỉ tồn tại trong một cuộc gọi.

~~~text
DECISION ID / NGAY GIO:
CHU DE: CR-17 / INC-04 / PHAM VI MOC D
VAN DE / NGUON THONG TIN:
THUC TRANG VA BANG CHUNG:
PHUONG AN A / B / C:
TAC DONG: GIA TRI / TIME / CAPACITY / QUALITY / DATA
NGHIA VU VA QUYEN LIEN QUAN:
QUYET DINH:
LY DO VA GIA DINH:
DIEU KIEN KHONG DUOC VI PHAM:
AI PHE DUYET / VAI TRO / PHAM VI:
AI CAN DUOC THONG BAO:
LINK BACKLOG / TEST / RUNBOOK / CONTRACT:
MOC XEM LAI VA TIN HIEU DOI QUYET DINH:
~~~

### 31.1. Lưu nguồn sự thật, tránh nhiều quyết định “chính”

Nếu PO thay thứ tự backlog, cập nhật **Product Backlog chính**. Nếu Security thay quy trình incident, dùng **kho quy trình có quyền phù hợp**. Decision log nên liên kết tới nguồn này thay vì sao chép nhiều bản mâu thuẫn.

### 31.2. Không ghi bí mật vào bản cập nhật rộng

Decision log dùng cho stakeholder không cần chứa **token đối tác, thông tin người học bị lộ hoặc bước khai thác lỗ hổng**. Thông tin nhạy cảm phải đi theo quy trình phân quyền của tổ chức.

## 32. Bài mô phỏng theo ba vòng: từ tin mới tới release

Đây là **bài thực hành tổng hợp có thể dùng trong lớp hoặc workshop nhóm**. Một nhóm học viên có thể phân vai PO, Developers, Scrum Master, đại diện đối tác, Security/Operations và người quan sát. Các thông số giả định cố ý không đầy đủ để buộc người học **hỏi và ra quyết định theo điều kiện**, không đoán một “đáp án duy nhất”.

### 32.1. Vòng 0 — Kế hoạch xuất phát

Bạn nhận:

- Deadline D: **15 ngày làm việc**.
- Năng lực dự kiến: **52 ngày-người hiệu quả**.
- Must ban đầu **33**, Should **9**, Could **10** ngày-người.
- Sprint Goal hiện tại: “Học viên đủ điều kiện đăng ký đúng chỗ và thấy trạng thái đáng tin”.
- Chất lượng: DoD, kiểm tra giao dịch đồng thời, phân quyền, giám sát và hỗ trợ cần thiết.

**Nhiệm vụ trong 10 phút:**

1. Chỉ ra vì sao kế hoạch **52/52 ngày-người** không có buffer là rủi ro.
2. Chọn một lát cắt cần kiểm chứng sớm vì **rủi ro cao**, không chỉ vì dễ.
3. Ghi một giả định liên quan đối tác hoặc môi trường.
4. Đề xuất một mốc review dự báo trước D.
5. Ghi ai có quyền thay đổi phạm vi và ai bảo vệ quality gate.

**Không nên nộp câu trả lời “Mọi việc sẽ hoàn tất nếu ai cũng làm 100% công suất”.** Một hệ thống có phụ thuộc và bất định không thể dự báo trung thực bằng mức sử dụng công suất tuyệt đối.

### 32.2. Vòng 1 — Có yêu cầu mới CR-17

Người đóng vai đối tác nhận tờ tình huống:

> “Chúng tôi muốn bổ sung xác minh mã học viên trước khi đăng ký. Theo trao đổi miệng, việc này rất quan trọng, nhưng chưa kiểm tra phụ lục hợp đồng. Sandbox API chưa cấp tài khoản. Đề nghị xong trước ngày D.”

**Nhiệm vụ trong 15 phút:**

1. Viết ít nhất **sáu câu hỏi làm rõ** trước khi ước lượng chắc.
2. Chọn trạng thái tạm **Must chưa xác minh, Should hoặc unknown**; giải thích vì sao không thể bỏ qua nguồn nghĩa vụ.
3. Thiết kế một **spike/integration experiment nhỏ** để kiểm chứng API.
4. Nêu hai phương án nếu sandbox đến muộn.
5. Chọn người cần xác nhận quyền và mốc quyết định.

**Đầu ra:** Change intake record ngắn, acceptance examples sơ bộ và một giả thuyết forecast có điều kiện.

### 32.3. Vòng 2 — INC-04 phân quyền khẩn

Người đóng vai Security đưa tin:

> “Một tài khoản thử có thể truy cập dữ liệu đăng ký của tài khoản thử khác qua một đường API. Chưa biết lỗi chỉ ở một endpoint hay nhiều nơi. Có nguy cơ người dùng thật bị ảnh hưởng. Triage cần bắt đầu ngay.”

**Nhiệm vụ trong 15 phút:**

1. Phân loại đây là **incident/rủi ro bảo mật đang cần xác minh**, không chỉ request sản phẩm.
2. Kích hoạt **đúng kênh và người có thẩm quyền**, chọn việc giảm tác động phù hợp.
3. Nêu thông tin **không được đưa vào chat/backlog rộng**.
4. Đặt policy cho expedite để không làm mọi việc khác tự động thành khẩn.
5. Nêu những PBI và điều kiện DoD có thể bị ảnh hưởng.
6. Tính lại năng lực nếu incident dùng 6 ngày-người và CR-17 được xác nhận Must.

**Đầu ra:** Incident triage card, forecast sơ bộ và bảng trade-off.

### 32.4. Vòng 3 — Có bằng chứng mới trước release

Facilitator chọn một trong ba thẻ:

- **Thẻ A — tốt:** Security xác nhận lỗ hổng đã được giảm/khắc phục và regression đạt; đối tác cấp sandbox; tích hợp được kiểm chứng; Must đạt DoD.
- **Thẻ B — chưa rõ:** Đối tác chưa cấp sandbox; quy tắc timeout chưa được xác nhận; phần còn lại sản phẩm đã Done.
- **Thẻ C — xấu:** Sau hotfix, integration test cho thấy vẫn có đường truy cập trái phép hoặc xác nhận vượt sức chứa.

**Nhiệm vụ trong 15 phút:**

1. Với từng thẻ, đề xuất **go/no-go hoặc quyết định có điều kiện**, không lẫn giả định với bằng chứng.
2. Nếu chọn A, nêu scope và guardrail cần theo dõi khi mở.
3. Nếu chọn B, trình phương án hợp lệ để chủ cam kết quyết; không tự gọi CR-17 Done.
4. Nếu chọn C, xác định lý do không mở đường gây hại và thông báo cần gửi.
5. Ghi **mốc sau release** để học từ outcome và incident.

**Tiêu chí đánh giá:** Đội học viên phải làm rõ **điều kiện, dữ liệu, quyền quyết định và rủi ro**; không được thưởng thêm điểm vì “giao nhiều task nhất”.

## 33. Đáp án tham khảo cho bài mô phỏng

Không có một thứ tự triển khai duy nhất. Đáp án dưới đây mô tả **logic ra quyết định đáng tin**, không bắt buộc mọi tổ chức phải làm đúng một mẫu quy trình.

### 33.1. Vòng 0

- Kế hoạch 52/52 đã tiêu hết năng lực giả định, không có dự phòng.
- M2 concurrency và M3 phân quyền cần kiểm chứng sớm; M4 chuẩn bị release không phải việc “sau khi code xong”.
- Nên có mốc kiểm tra phụ thuộc/giá trị trước ngày cuối, không chỉ deadline delivery.
- PO quyết định thứ tự Product Backlog; Developers quyết định kế hoạch và chất lượng; quyền release/cam kết do cơ chế tổ chức.

### 33.2. Vòng 1

- CR-17 chưa được xác minh là Must, không tự coi là câu hỏi đã chốt.
- Cần xác nhận mục đích, nghĩa vụ, chính sách timeout, dữ liệu truyền, quyền sandbox, contract, acceptance examples, thời điểm quyết định và phương án thay thế.
- Spike nên có **câu hỏi rõ, timebox và bằng chứng**: test API sandbox, contract errors, giới hạn rate, timeout và kết quả khi không đủ điều kiện.
- Nếu API chưa sẵn sàng, có thể xin sandbox sớm, dùng contract stub để phát triển có kiểm soát nhưng **không coi stub là bằng chứng tích hợp thật**. Phương án khác chỉ hợp lệ khi chủ cam kết chấp thuận và vẫn đạt kiểm soát an toàn.

### 33.3. Vòng 2

- Ưu tiên **giảm tác động bảo mật hiện tại** theo incident process, thu thập bằng chứng phù hợp và bảo vệ dữ liệu cá nhân.
- Không đưa thông tin riêng, token hoặc cách khai thác chi tiết vào kênh rộng.
- Expedite theo tác động và quyền, không theo người gắn nhãn “gấp”.
- Theo giả định nỗ lực: \(52-6=46\) cho backlog; nếu CR-17 Must, Must \(33+8=41\); còn **5 ngày-người trên giấy** trước bất định. S1 9 và C1 10 **không thể được hứa chắc**.
- Nếu lỗi lan rộng hoặc sandbox trễ, phải **đánh giá lại forecast**, không bám vào phép tính 5 như dự phòng bảo đảm.

### 33.4. Vòng 3

- **Thẻ A:** Chỉ xem go khi toàn bộ scope đã được chủ cam kết xác nhận, DoD, Security/Operations/quality gate và release authority đạt; vẫn cần theo dõi sau mở.
- **Thẻ B:** Bất định contract có thể khiến không đủ điều kiện cho một Must. Cần quyết định có quyền về giải pháp khác, phạm vi hợp lệ hoặc điều chỉnh cam kết; nếu chưa có, không tuyên bố đạt.
- **Thẻ C:** Không mở luồng với lỗi dữ liệu/bảo mật đã biết. Kích hoạt ứng phó, no-go hoặc phương án bảo vệ người dùng theo thẩm quyền; truyền thông trung thực.

### 33.5. Mẫu kết luận sau mô phỏng

> “Nhóm đã giảm WIP để hoàn tất các lát cắt Must, phân loại INC-04 bằng mức ảnh hưởng thay vì ưu tiên cá nhân và chưa cam kết CR-17 trước khi xác minh nghĩa vụ. Theo năng lực giả định, Must chiếm gần hết phần còn lại nên nhóm hoãn S1/C1, đặt cổng tích hợp/quality và trình phương án nếu dependency không đạt. Quyết định release chỉ được đưa ra khi có đủ bằng chứng và thẩm quyền.”

Đây là một **đáp án có điều kiện**: nếu nguồn nghĩa vụ hoặc dữ liệu mới thay đổi, kết luận cũng cần thay đổi.

## 34. Bài thử ưu tiên: phân biệt quan trọng, khẩn và bắt buộc

Một cách luyện nhận diện là phân loại các yêu cầu mới theo **mức tác động và thời gian**, sau đó hỏi về quyền và bằng chứng.

| Tình huống | Nhóm xử lý sơ bộ | Câu hỏi cần làm rõ |
| --- | --- | --- |
| Báo tài khoản khác đọc được dữ liệu đăng ký | Security incident triage / expedite theo chính sách | Phạm vi, tác động, khắc phục, quyền? |
| PO muốn thêm giao diện lịch tháng đẹp hơn | Backlog ưu tiên thông thường | Giá trị, deadline thực, điều gì phải hoãn? |
| Đối tác thông báo API cũ ngừng hoạt động ngày D | Fixed-date dependency đã được xác minh | Contract, sandbox, kế hoạch chuyển đổi và thời gian test? |
| Pipeline CI đang đỏ với security tests quan trọng | Blocker chất lượng cần xử lý sớm | Phạm vi lỗi, có ảnh hưởng release hay không? |
| Giám đốc yêu cầu đổi màu nút ngay trong ngày | Chưa chắc là khẩn | Có ràng buộc/ảnh hưởng nào được chứng minh? |
| Học viên báo thanh toán bị trừ tiền nhưng đăng ký không xác nhận | Incident/ticket tác động tài chính cần triage | Tác động, đối soát, kênh support/incident? |
| Nâng cấp thư viện hết hạn hỗ trợ cuối tháng | Rủi ro fixed date/phòng ngừa | CVE, tương thích, môi trường, thẩm quyền và mốc? |
| Một Developer yêu cầu refactor lớn để “code sạch” | Enabler/risk reduction cần đánh giá | Rủi ro/giá trị, scope, test, dependency và ưu tiên? |

### 34.1. “Khẩn” và “bắt buộc” có thể giao nhau

Một nghĩa vụ phải hoàn tất trước D chưa chắc cần **đứt mọi việc ngay hôm nay**, nếu còn cửa sổ hợp lý để chuẩn bị. Ngược lại, một lỗ hổng đang tác động người dùng có thể cần **hành động ngay** dù không xuất hiện trong hợp đồng.

### 34.2. Hỏi “điều gì xảy ra nếu chờ?”

Đây là câu hỏi tốt để đánh giá **chi phí trì hoãn** nhưng phải kết hợp:

- Ai bị ảnh hưởng, trong bao lâu?
- Tác động có đảo ngược được không?
- Có gây vi phạm nghĩa vụ hoặc mất dữ liệu?
- Có ảnh hưởng năng lực giải quyết những việc quan trọng khác?
- Thông tin về khả năng xảy ra có đáng tin không?

Không tự tạo một con số chi phí trì hoãn chính xác chỉ từ cảm nhận.

## 35. Một bảng điều phối tối thiểu cho tuần áp lực

Nhóm có thể nhìn kết hợp **mục tiêu, flow, phụ thuộc và rủi ro** trên một trang:

| Luồng | Item | Mức yêu cầu | Trạng thái Done | Rủi ro / blocked | Hành động tiếp |
| --- | --- | --- | --- | --- | --- |
| Incident | INC-04 quyền dữ liệu | Theo mức impact | Chưa đóng | Chưa xác định hết phạm vi | Giảm tác động, regression, người có quyền |
| Fixed date | M2 giữ chỗ đúng | Must | Chưa Done | Test concurrency cần chuyên gia | Review, tích hợp và test |
| Fixed date | M3 xem trạng thái | Must | Chưa Done | Ảnh hưởng bởi auth bug | Test phân quyền, kết hợp hotfix |
| Fixed date | M1 xem workshop | Must | Đang review | Cần dữ liệu còn chỗ chính xác | Hoàn tất tới DoD |
| Fixed date | M4 vận hành/release | Must | Chưa Done | Runbook và Support | Diễn tập/chuẩn bị theo rủi ro |
| Change request | CR-17 mã học viên | Chờ xác nhận Must | Chưa Done | Sandbox/contract | Xác minh và spike |
| Standard | S1 email | Should | Ready | Cạnh tranh năng lực | Giữ chưa kéo |
| Standard | C1 lịch/lọc nâng cao | Could | Ready | Không cần ở D theo giả định | Hoãn |

### 35.1. Không dùng một cột “Percent Complete” để che sự thật

M2 có thể đã có 90% code, nhưng nếu test đồng thời thất bại thì **chưa có bằng chứng hành vi đăng ký đúng**. Trạng thái theo ranh giới Done và blocker hữu ích hơn số phần trăm tự gán.

### 35.2. Không làm board quá phức tạp

Nếu board có 20 trạng thái và mỗi quyết định phải nhập năm biểu mẫu, nhóm sẽ mất thời gian vào công cụ. Chọn **đủ thông tin giúp kéo việc và ra quyết định**; dữ liệu incident nhạy cảm nằm ở nơi phân quyền phù hợp.

## 36. Buổi diễn tập go/no-go: năm câu hỏi không được bỏ

Trước mốc D, người có thẩm quyền cần xác minh:

1. **Cam kết:** Hành vi, đối tượng, ngày và điều kiện bắt buộc đã được xác nhận?
2. **Increment:** Mỗi phần Must đã thực sự đạt DoD trên đúng artifact/môi trường liên quan?
3. **An toàn:** INC-04 và các rủi ro giao dịch/phân quyền đã được khắc phục hoặc kiểm soát hợp lệ? Có bằng chứng gì?
4. **Vận hành:** Có observability, Support, quyền xử lý, runbook và kế hoạch đối soát/giảm tác động phù hợp?
5. **Quyền quyết định:** Ai phê duyệt go/no-go, những rủi ro tồn dư nào được chấp nhận đúng thẩm quyền và ai sẽ theo dõi?

### 36.1. Mẫu quyết định

~~~text
RELEASE / MOC:
PHAM VI BAT BUOC VA DOI TUONG:
BUILD/ARTIFACT:

MUST DAT DONE:
- PBI:
- Bang chung CI/integration/e2e:
- Security, data va authorization:

INCIDENT / RUI RO TON DU:
- Trang thai INC-04:
- Tac dong nguoi dung:
- Phuong an theo doi/giam tac dong:

VAN HANH:
- Alert/log/runbook/Support:
- Quyen truy cap va escalation:
- Rollback/code va doi soat du lieu:

CAM KET / PHE DUYET:
- Xac nhan scope va dieu kien:
- Nguoi quyet dinh:
- GO / NO-GO / DIEU KIEN CAN THEM:
- Ly do va bang chung:

NEU GO:
- Nhom nguoi dung duoc mo:
- Tin hieu dung mo rong:
- Nguoi giam sat:

NEU NO-GO:
- Tac dong cam ket:
- Thong bao va duong ho tro:
- Dieu kien xet lai:
~~~

### 36.2. “Go có điều kiện” phải có điều kiện thật

Không viết “Go nhưng test giao dịch sẽ làm sau”. Một quyết định có điều kiện có thể là **“Chưa mở; sau khi test X đạt, Security/Operations xác nhận Y và chủ cam kết duyệt Z, mới xem go lại”**. Điều kiện nào bắt buộc thì không được xem là khuyến nghị tùy ý.

### 36.3. Một quyết định No-go vẫn là hành động

Nếu không đủ an toàn để mở, cần **chủ động thông báo, bảo vệ dữ liệu, xử lý nghĩa vụ và chuẩn bị phương án hợp lệ**. Không được im lặng rồi để người dùng tự phát hiện hệ thống không hoạt động.

## 37. Sau khi phát hành: quan sát outcome và phản ứng trước rủi ro

Nếu quyết định go được phê duyệt, công việc **không kết thúc khi deploy thành công**. Nhóm cần theo dõi:

| Nhóm tín hiệu | Ví dụ quan sát | Phản ứng nếu bất thường |
| --- | --- | --- |
| **Outcome người dùng** | Tỷ lệ đăng ký hợp lệ thành công, người dùng hiểu trạng thái | Điều tra hành trình, thông tin và business rules |
| **Dữ liệu và chất lượng** | Xác nhận trùng/vượt chỗ, sai trạng thái | Incident triage, giảm tác động, đối soát |
| **Bảo mật** | Yêu cầu truy cập trái phép, alert quyền, audit | Security response theo chính sách |
| **Độ tin cậy** | Error rate, timeout, latency, dependency availability | Theo dõi dependency và áp cơ chế giảm tác động hợp lệ |
| **Vận hành/Support** | Ticket khó hiểu trạng thái, yêu cầu hoàn/đổi | Support phối hợp Product/Developers, cập nhật hướng dẫn |
| **Flow nhóm** | WIP, age, cycle time, blocked time | Chọn cải tiến hàng đợi và phụ thuộc |
| **Nhịp bền vững** | Quá tải/giờ trực, việc khẩn lặp | Điều chỉnh on-call, năng lực, kỹ thuật phòng ngừa |

### 37.1. Ví dụ outcome cần định nghĩa rõ

\[
\text{Tỷ lệ xác nhận đăng ký thành công}
=\frac{\text{Số hành trình hợp lệ nhận xác nhận đúng}}
{\text{Tổng hành trình đăng ký hợp lệ bắt đầu}}\times100\%.
\]

Định nghĩa cần làm rõ **thế nào là hành trình hợp lệ, thế nào là thành công, xử lý retry/duplicate ra sao, trong khoảng thời gian và nhóm người dùng nào**. Không đếm một thông báo frontend “Success!” là giao dịch thành công khi database chưa xác nhận.

### 37.2. Thay đổi số liệu không tự chứng minh nguyên nhân

Nếu sau ngày D tỷ lệ thành công tăng, có thể do chất lượng sản phẩm cải thiện, loại workshop mới, số chỗ nhiều hơn, chiến dịch truyền thông hoặc API đối tác ổn định. Dữ liệu giúp mở **câu hỏi và thử nghiệm tiếp**, không tự cho phép tuyên bố “Scrum/Kanban làm conversion tăng X%”.

## 38. Cải tiến sau incident và sau Sprint: tìm nguyên nhân hệ thống

Khi có sự cố, một cuộc review chỉ hỏi “ai viết bug?” dễ làm nhóm che lỗi. Cần hỏi **hệ thống phối hợp, kiểm chứng và quyết định đã để bug lọt thế nào**.

### 38.1. Những câu hỏi sau INC-04

- Vì sao kiểm tra quyền không diễn ra ở ranh giới thực thi?
- Có endpoint nào dùng lại chính sách quyền sai?
- Test với **hai tài khoản độc lập** đã tồn tại chưa?
- Code review và DoD có đề cập phân quyền tương ứng mức rủi ro?
- Trong deployment, tín hiệu nào giúp phát hiện sớm?
- Support biết kênh báo và dữ liệu cần giữ không?
- Runbook và quyền incident có sẵn cho người dự phòng không?
- Việc xử lý incident có cho thấy **WIP, CI hoặc reviewer bottleneck** mới?

### 38.2. Những hành động cải tiến có thể kiểm chứng

| Hành động | Bằng chứng hoàn tất | Chỉ báo sau đó |
| --- | --- | --- |
| Bổ sung test phân quyền theo nhóm API | Regression suite chạy trên pipeline phù hợp | Lỗi cùng lớp được phát hiện sớm hơn |
| Chuẩn hóa cách xác định chủ sở hữu dữ liệu | Review/rule rõ và test có ví dụ | Giảm nguy cơ truy cập trái phép |
| Cải thiện runbook incident | Người dự phòng thử chẩn đoán trong môi trường an toàn | Giảm thời gian chờ thông tin |
| Kiểm tra chính sách expedite | Policy có tiêu chí và người quyết | Ít yêu cầu “urgent” giả chen hàng |
| Xem lại kế hoạch capacity | Có dự phòng rủi ro và forecast có điều kiện | Ít cam kết 100% công suất không căn cứ |
| Làm rõ contract change intake | Có nguồn nghĩa vụ và mốc quyết định | Ít CR chưa rõ lọt thẳng vào Sprint |

### 38.3. Sprint Retrospective không thay incident response

Với lỗi đang gây hại, giảm tác động và khắc phục phải diễn ra **theo quy trình khẩn**, không đợi hết Sprint. Retrospective giúp **học và thay đổi hệ thống**, không phải nơi đầu tiên được phép phản ứng với sự cố.

### 38.4. Không nhất thiết mọi thứ đều cần thêm tài liệu

Nếu nguyên nhân là thiếu test, hành động có giá trị có thể là **bổ sung một test regression tự động**. Nếu nguyên nhân là quyền phê duyệt quá chậm, cần **đổi quy trình/ủy quyền hợp lệ**. Nếu người mới không biết cách xử lý, có thể cần **runbook và diễn tập**, không phải hàng trăm trang wiki.

## 39. Những sai lầm thường gặp khi ba áp lực đồng thời xuất hiện

| Sai lầm | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Thấy yêu cầu mới là thêm ngay vào Sprint | Sprint Goal và capacity bị che | Intake, xác minh giá trị và quyền PO |
| Gọi mọi đề nghị từ lãnh đạo là emergency | Dòng thường luôn bị ngắt | Triage theo tác động và thời gian |
| Cho rằng fixed date = fixed scope | Không còn trade-off hợp lệ | Tách outcome bắt buộc khỏi tiện ích |
| Tự dời ngày đã cam kết | Vi phạm thẩm quyền và niềm tin | Đàm phán bằng người có quyền |
| Xem mọi story là Must | Không ưu tiên được | Mỗi Must có lý do và nguồn xác nhận |
| Không xác minh CR-17 với chủ hợp đồng | Có thể làm thiếu hoặc thừa nghĩa vụ | Chốt nguồn, acceptance và mốc |
| Gọi API stub là tích hợp thật | Dependency lộ quá muộn | Contract/integration test phù hợp |
| Bỏ chính sách timeout đối tác | Trạng thái xác minh mơ hồ | Làm rõ fail behavior với người có quyền |
| Dùng Sprint Goal để từ chối incident | Người dùng tiếp tục bị ảnh hưởng | Kích hoạt incident process ngay |
| Hủy Sprint vì một PBI trễ | Hiểu sai điều kiện Scrum | Chỉ PO hủy khi Sprint Goal lỗi thời |
| Quản lý phân task thay Developers | Giảm tự quản, tăng chuyển giao | Rõ quyền và hỗ trợ tháo blocker |
| Cắt DoD để tăng throughput | Số liệu đẹp nhưng chất lượng giảm | Giữ quality gate và tích hợp thật |
| Chấm Done khi PR merge | Chưa có Increment đáng tin | Kiểm tra acceptance và DoD |
| Bỏ regression khi hotfix | Dễ gây lỗi mới | Kiểm chứng rủi ro theo quy trình khẩn |
| Đưa dữ liệu thật vào ticket công khai | Tăng rủi ro lộ lọt | Phân quyền, khử dữ liệu, lưu bằng chứng đúng nơi |
| Người nghỉ phép mặc nhiên phải trực | Tập trung tri thức và quá tải | Người dự phòng, on-call, runbook |
| Tất cả ticket được đặt expedite | Expedite không còn ý nghĩa | Chính sách và quyền kích hoạt |
| Giới hạn expedite quá cứng | Có thể bỏ mặc incident nghiêm trọng thứ hai | Điều phối nhiều incident theo mức ảnh hưởng |
| Mở nhiều PBI Should khi Must bị chặn | WIP/queue tăng | Swarm và hoàn tất Must |
| Dùng ngày-người như ngày lịch | Không thấy dependency và thời gian chờ | Bản đồ đường phụ thuộc |
| Giữ forecast cũ sau sự cố | Cam kết giả, mất quyền lựa chọn | Cập nhật theo sự thật mới |
| Tính nỗ lực incident trùng mà không biết | Dự báo quá bi quan | Xem chồng lặp và bằng chứng |
| Không tính chi phí phối hợp người mới | Hứa tăng năng lực tuyến tính | Đánh giá kỹ năng/onboarding/bottleneck |
| Làm thêm giờ kéo dài thành kế hoạch | Tăng lỗi và kiệt sức | Giảm scope và quản lý nhịp bền vững |
| Lấy số task Done làm % nghĩa vụ | Hành vi bắt buộc có thể chưa xong | Đo Increment/DoD/outcome |
| Dùng feature flag để mở bug đã biết | Người dùng thử chịu rủi ro | Chỉ mở khi đạt điều kiện an toàn |
| Nghĩ rollback code hồi phục mọi dữ liệu | Bản ghi và tác động vẫn tồn tại | Đối soát và kế hoạch hỗ trợ |
| “Go có điều kiện” nhưng thiếu điều kiện | Thực tế là go mù | Nêu rõ điều kiện bắt buộc trước mở |
| Chỉ nói tin tốt với đối tác | Không còn thời gian đàm phán | Báo sớm bằng phương án và bằng chứng |
| Incident review chỉ đi tìm người mắc lỗi | Giấu lỗi, không học hệ thống | Phân tích điều kiện và test/guardrail |
| Chỉ đo tốc độ xử lý mà không đo người dùng | Tối ưu activity thay outcome | Theo dõi flow, quality và outcome |
| Giữ mọi cuộc họp dài vì “khẩn” | Mất năng lực tập trung | Tối giản họp, tăng async có ngữ cảnh |
| Không ghi lại quyết định scope | Người vắng mặt dùng kỳ vọng cũ | Decision log liên kết nguồn chính |

## 40. Checklist xử lý thay đổi, deadline và việc khẩn

Đây là **checklist đào tạo**, không phải biểu mẫu bắt buộc của Scrum hoặc Kanban. Chọn những câu hỏi quan trọng theo rủi ro, không biến nó thành thủ tục ký duyệt cho mọi thẻ nhỏ.

~~~text
THUC TRANG / MUC TIEU
[ ] Product Goal va Sprint Goal ro va co the giai thich?
[ ] Muc D co nguon, gio/mui gio va nguoi xac nhan?
[ ] Outcome Must va nghia vu duoc tach khoi tien ich?
[ ] Increment nao da dat Done, item nao chi dev xong?
[ ] Capacity va dependency thuc te da duoc cap nhat?

THAY DOI YEU CAU
[ ] CR co nguoi dung, van de, hanh vi, gia tri ro?
[ ] Co xac minh nguon bat buoc/hop dong?
[ ] Co acceptance examples va timeout/failure policy?
[ ] Da kiem tra du lieu, bao mat, phan quyen, dependency?
[ ] Co nguoi co tham quyen quyet scope/priority?
[ ] Neu chap nhan CR, dieu gi duoc hoan bo?

CONG VIEC KHAN
[ ] Incident da duoc triage theo tac dong/tham quyen?
[ ] Co giam tac dong va luu bang chung dung cho?
[ ] Co nguoi chi huy/kenh/duong escalation phu hop?
[ ] Expedite duoc kich hoat theo policy, khong tu y?
[ ] Test regression va nhung API lien quan duoc xem?
[ ] Thong tin nhay cam khong lo trong ticket/chat rong?
[ ] Capacity bi incident chiem da phan anh vao forecast?

DONG CONG VIEC / SCRUM / KANBAN
[ ] Developers co the thich ung Sprint Backlog thuc te?
[ ] Neu doi scope Sprint, co trao doi voi PO va giu Sprint Goal?
[ ] Khong giam Definition of Done de kip ngay?
[ ] WIP va work item age cua Must duoc theo doi?
[ ] Co ho tro nut that review/test/contract truoc khi mo Could?
[ ] Throughput/velocity khong bi dung de xep hang ca nhan?

DEADLINE / FORECAST / RELEASE
[ ] Effort khong bi nham voi ngay lich va dependency?
[ ] Co du bao theo kich ban va muc do bat dinh?
[ ] Co quyet dinh hoan/giup/doi phuong an/no-go?
[ ] Chu cam ket va release authority da duoc tham gia?
[ ] CI, transaction, authorization, integration, support dat gate?
[ ] Pilot/canary/flag neu co duoc phe duyet dung pham vi?
[ ] Rollback va doi soat du lieu duoc len ke hoach?
[ ] Co thong bao trung thuc, thoi diem xem lai?

SAU SU KIEN
[ ] Da quan sat outcome, reliability va ticket support?
[ ] Incident duoc review va action item duoc kiem chung?
[ ] Product Backlog, runbook, test va quyet dinh da cap nhat?
[ ] Nhom co cai tien de it bi lap lai viec khan gia tao?
~~~

### 40.1. Thử checklist bằng một câu hỏi duy nhất

> **“Nếu hiện tại không thể giao đủ tất cả, nhóm có biết chính xác điều gì không được vi phạm, ai có quyền chọn trade-off và bằng chứng nào cho thấy người dùng sẽ an toàn?”**

Nếu chưa trả lời được, đừng coi một bản kế hoạch với nhiều thẻ Done là đã giải quyết vấn đề.

## 41. Bài tập 1 — Thay đổi yêu cầu ngay giữa Sprint

**Đề bài:** Scrum Team đang ở ngày thứ tư của Sprint mười ngày. Sprint Goal là **“Học viên tìm và đăng ký workshop theo điều kiện hiện hành, với trạng thái xác nhận chính xác”**. Product Owner nhận ba đề nghị:

1. **R1:** Đổi màu nút đăng ký vì stakeholder thích màu mới.
2. **R2:** Thêm quy tắc không cho người học chưa đủ điều kiện được xác nhận; đối tác nói đây là nghĩa vụ trước ngày D nhưng chưa đưa văn bản.
3. **R3:** Học viên không hiểu chữ “Đang xử lý”; Support báo nhiều yêu cầu hỏi trạng thái, có log/feedback.

Developers đang làm hai PBI Must; rủi ro test đồng thời chưa giải quyết. Một quản lý yêu cầu đưa cả ba vào Sprint và giữ nguyên mọi kế hoạch.

### Nhiệm vụ

1. Phân biệt **yêu cầu mới, bằng chứng người dùng và nguồn nghĩa vụ chưa xác minh**.
2. R1 có phải khẩn không? Cần bằng chứng gì để thay đổi ưu tiên?
3. Với R2, viết ba câu hỏi để làm rõ **quy tắc, thẩm quyền và hành vi khi lỗi**.
4. Với R3, đề xuất một **lát cắt nhỏ có thể kiểm chứng** thay vì làm lại toàn bộ UI.
5. Nếu một R cần vào Sprint, Developers và PO nên làm gì với scope và Sprint Goal?
6. Nêu hai việc **không được cắt** để tạo chỗ cho R2.
7. Khi nào việc thêm R2 có thể khiến Sprint Goal trở nên lỗi thời? Ai được hủy Sprint?
8. Viết một quyết định backlog có lý do và mốc xem lại.

### Hướng giải tham khảo

- **R1** là thay đổi mong muốn thông thường nếu không có nghĩa vụ/tác động khác. Không tự chèn lên Must đang rủi ro.
- **R2** cần xác minh nguồn và điều kiện; nếu là Must, nó ảnh hưởng trực tiếp tới tiêu chí chấp nhận của luồng đăng ký. Không tự chọn fail-open khi API không phản hồi.
- **R3** có dữ liệu Support và có thể cải tiến **nhãn trạng thái, hướng dẫn và cách xem lại trạng thái** thành lát cắt đủ nhỏ, đồng thời kiểm tra nguồn trạng thái backend đúng.
- **Trong Sprint**, Developers cập nhật kế hoạch và thương lượng scope với PO, không làm nguy hại Sprint Goal hoặc hạ DoD. **Sprint chỉ có thể bị hủy khi Sprint Goal trở nên lỗi thời và chỉ PO có quyền hủy**, không vì một request mới đến muộn.
- Không bỏ test phân quyền hoặc bảo vệ giao dịch đồng thời để thêm R2.

## 42. Bài tập 2 — Tính lại năng lực và giới hạn của phép tính

**Đề bài định lượng:** Nhóm có **52 ngày-người năng lực hiệu quả** còn lại. Phần Must ban đầu **33**, Should **9**, Could **10**. Incident mới tiêu tốn **6**. Yêu cầu mới có thể thêm **8** ngày-người nếu được xác nhận Must. Môi trường kiểm thử có nguy cơ làm mất thêm **4** ngày-người.

### Câu hỏi

1. Nỗ lực backlog ban đầu tổng bao nhiêu? Buffer là bao nhiêu?
2. Sau incident, còn bao nhiêu ngày-người cho các PBI ban đầu?
3. Nếu CR-17 là Must, tổng Must mới và phần năng lực thô còn lại là bao nhiêu?
4. Nếu môi trường test làm mất thêm bốn ngày-người hiệu quả, phần còn lại là bao nhiêu?
5. Có nên cam kết giao thêm Should 9 ngày-người khi phần còn lại là 5? Vì sao?
6. Có thể chắc chắn hoàn tất Must 41 trong 46 ngày-người không? Kể ít nhất bốn lý do.
7. Điều gì xảy ra nếu 6 ngày-người incident có phần trùng với công việc M3?
8. Nếu API đối tác mất năm ngày lịch chờ quyền, thêm ba Developers có tự giải quyết được không?
9. Hãy viết **một câu dự báo có điều kiện** thay cho lời hứa tuyệt đối.

### Lời giải và diễn giải

| Phép tính | Kết quả |
| --- | ---: |
| Must + Should + Could ban đầu | \(33+9+10=52\) ngày-người |
| Buffer thô ban đầu | \(52-52=0\) |
| Năng lực sau incident | \(52-6=46\) |
| Must nếu CR-17 được xác nhận Must | \(33+8=41\) |
| Khoảng năng lực thô còn lại sau Must mới | \(46-41=5\) |
| Năng lực sau incident và gián đoạn test giả định | \(52-6-4=42\) |
| Khoảng còn lại sau Must 41 | \(42-41=1\) |

Các con số **không phải bảo đảm có 5 hay 1 ngày-người thực sự sử dụng được**. Chúng dựa trên nỗ lực giả định, chưa mô hình hóa lịch, phân bổ chuyên môn, dependency, sai số và các công việc chồng lặp.

Một cách nói phù hợp:

> “Với dữ liệu hiện có, incident đã sử dụng một phần năng lực. Nếu CR-17 là Must, tổng nỗ lực Must dự kiến khoảng 41 ngày-người so với 46 còn lại sau incident, nên gần như không còn dư địa cho email/lịch nâng cao. Mức hoàn tất đúng ngày vẫn bất định do API đối tác, test giao dịch và môi trường. Nhóm đề xuất hoãn Should/Could, đặt cổng xác minh sớm và trình phương án nếu Must không đạt.”

## 43. Bài tập 3 — Triage một tuần có bốn yêu cầu “khẩn”

**Đề bài:** Trong cùng buổi sáng, nhóm nhận:

- **T1:** Support phát hiện một đường API có thể trả dữ liệu người học sai chủ thể.
- **T2:** Bộ phận marketing cần đổi banner chiến dịch vào buổi chiều.
- **T3:** Đối tác xác nhận API cũ ngừng hoạt động vào ngày D+7, hợp đồng tích hợp mới chưa được thử.
- **T4:** CI ngẫu nhiên fail khiến PR phải chạy lại nhiều lần, PBI Must bắt đầu chờ.

Một thành viên gửi tin “cứ đưa cả bốn vào expedite lane, ai xong gì thì làm tiếp”.

### Nhiệm vụ

1. Phân loại bốn item theo **tác động, mốc cố định, flow risk và yêu cầu sản phẩm**.
2. Item nào cần kênh incident ngay? Tại sao?
3. Đối với T3, cần đặt mốc kiểm chứng nào **trước khi API cũ ngừng hoạt động**?
4. T4 có nhất thiết là incident Severity 1 không? Vì sao?
5. Bạn sẽ mô tả policy **khi nào được gắn expedite** thế nào?
6. Nếu T2 thực ra liên quan nghĩa vụ quảng cáo đã ký, thông tin nào làm đổi quyết định?
7. Trong Scrum, ai ưu tiên việc sản phẩm; Developers cập nhật kế hoạch ra sao?
8. Nêu một guardrail cho mỗi item.
9. Viết một cập nhật cuối ngày cho PO và Operations.

### Hướng giải tham khảo

- **T1** có dấu hiệu rủi ro dữ liệu riêng tư, cần security triage và biện pháp giảm tác động theo thẩm quyền; không chờ Sprint Planning.
- **T3** là fixed-date dependency; cần contract, sandbox, integration path và mốc kiểm tra sớm, không đợi D+6.
- **T4** là blocker kỹ thuật làm giảm flow và độ tin cậy; mức khẩn cần đánh giá theo ảnh hưởng release, không mặc định Sev1.
- **T2** là change request thông thường trừ khi có nghĩa vụ/tác động được xác minh.
- Không cho phép mọi người tự đặt “expedite” nếu không rõ tiêu chí, vì điều đó làm mất ý nghĩa chính sách.

## 44. Bài tập 4 — Chọn phương án với deadline cứng và phần Must chưa đạt

**Bối cảnh:** Còn hai ngày làm việc tới D. Phần danh sách và xem trạng thái đã đạt DoD. Luồng đăng ký có lỗi khi hai yêu cầu tranh chỗ cuối; Security vừa hoàn tất giảm tác động của INC-04 nhưng regression trên một nhóm endpoint chưa đạt. Đối tác muốn giữ ngày đã công bố và đề xuất “mở cho 10% học viên trước”.

### Yêu cầu

1. Điều gì đã đạt Done, điều gì chưa?
2. Vì sao việc mở 10% **không tự làm an toàn** cho lỗi tranh chỗ cuối hoặc phân quyền đã biết?
3. Feature flag giúp giảm rủi ro gì, và giới hạn gì?
4. Ai được quyền xác nhận thay đổi “mở cho 10%” có đáp ứng cam kết?
5. Liệt kê ba lựa chọn hợp lệ để trình người có thẩm quyền.
6. Nếu không có lựa chọn nào đáp ứng DoD/quality gate, quyết định gì phù hợp?
7. Kế hoạch rollback cần bổ sung điều gì về **dữ liệu đã ghi và Support**?
8. Viết một đoạn thông báo **không đổ lỗi, có bằng chứng và mốc xem lại**.

### Gợi ý đáp án

**Không mở đường có lỗi dữ liệu/quyền đã biết** chỉ vì số người dùng nhỏ. Cần ưu tiên sửa và kiểm chứng, đánh giá phương án thay thế an toàn được phê duyệt, hoặc trình điều chỉnh phạm vi/cam kết. Nếu không còn đường release an toàn, cần **no-go có kế hoạch** và truyền thông theo nghĩa vụ.

Thông báo mẫu:

> “Luồng xem workshop và xem trạng thái đã đạt điều kiện hoàn tất. Luồng xác nhận chỗ cuối chưa đạt test concurrent; regression phân quyền của incident vẫn còn điểm chưa đạt. Việc mở nhóm 10% chưa được xác nhận là đáp ứng cam kết và không loại bỏ rủi ro dữ liệu. Nhóm đang hoàn tất điều tra/test, đồng thời trình phương án giới hạn phạm vi hợp lệ hoặc điều chỉnh cam kết. Nếu không đạt quality gate trước mốc quyết định, chúng tôi đề xuất không mở đường đăng ký gây hại và kích hoạt thông báo/hỗ trợ.”

## 45. Bài tập 5 — Dùng số liệu Kanban mà không đánh lừa bản thân

**Dữ liệu giả định:** Trước một tuần nhiều incident, nhóm có sáu PBI đã bắt đầu:

| Item | Work item age hiện tại | Trạng thái | Ghi chú |
| --- | ---: | --- | --- |
| M1 | 3 ngày | Review | Chờ một reviewer |
| M2 | 8 ngày | Test | Đã phát hiện lỗi concurrency |
| M3 | 5 ngày | Development | Chờ hợp nhất sửa phân quyền |
| M4 | 2 ngày | In progress | Chuẩn bị runbook |
| S1 | 7 ngày | Blocked | Chờ email sandbox |
| C1 | 4 ngày | Development | Lịch tháng đang được làm |

Trong tuần trước nhóm đã đóng 12 **task kỹ thuật**, nhưng chỉ **một PBI đạt DoD**. Ba PBI khác được ghi “dev complete”.

### Câu hỏi

1. WIP cấp PBI đang là bao nhiêu? Có nên coi task “dev complete” là Done không?
2. PBI nào cần thảo luận trước vì **age và rủi ro**? Vì sao?
3. Nếu chỉ một reviewer chuyên nghiệp, mở thêm PBI mới có tác dụng gì với hàng đợi?
4. Vì sao 12 task Done không thể dùng trực tiếp làm throughput PBI?
5. Chọn một **giới hạn WIP** để thử và nêu điều kiện ngoại lệ khẩn.
6. Với S1 đang blocked, có nên ưu tiên nó hơn M2 chỉ vì age 7 ngày không?
7. Bạn sẽ báo stakeholder về “1 PBI Done” như thế nào mà không che tiến độ kỹ thuật?
8. Nếu sau một tuần throughput PBI vẫn thấp, điều gì cần điều tra trước khi ép tăng năng suất cá nhân?

### Hướng giải tham khảo

WIP cấp PBI là **6 item** nếu cả sáu đã vượt điểm bắt đầu theo chính sách. Cần xem M2 vì age 8 và rủi ro giao dịch; M3 vì phân quyền; M1 vì reviewer bottleneck. S1 age 7 nhưng nếu không bắt buộc D, không tự vượt M2 chỉ nhờ tuổi.

**12 task Done không phải 12 Increment**. Thử giảm WIP và ưu tiên hoàn tất Must có thể hợp lý; giới hạn số cụ thể cần dựa trên năng lực/loại việc và không ngăn ứng phó incident nghiêm trọng. Nếu kết quả chưa tốt, kiểm tra **review, test, dependency, cách chia lát cắt và chính sách Done** trước khi đổ lỗi cá nhân.

## 46. Bài tập 6 — Thiết kế một thông báo thay đổi có trách nhiệm

**Đề bài:** Đối tác xác nhận CR-17 thật sự bắt buộc trước ngày D, nhưng môi trường sandbox chưa được cấp. Nhóm đã xử lý tác động trước mắt của INC-04; việc kiểm thử hồi quy vẫn còn. PO muốn đề xuất hoãn email nhắc và lịch tháng, giữ đường đăng ký tối thiểu an toàn. Chủ cam kết chưa chấp thuận phương án thay thế nếu API tới muộn.

### Nhiệm vụ

Viết hai thông báo:

1. **Thông báo cho stakeholder/chủ cam kết:** Không quá 200 từ, nêu nghĩa vụ, trạng thái Done, rủi ro, những lựa chọn cần quyết và hạn phản hồi.
2. **Thông báo cho Developers/Operations:** Không quá 150 từ, nêu tác vụ cần kiểm chứng, policy expedite, dependency, guardrail và đường escalation.

Đồng thời, xác định:

- Thông tin nào **không đưa vào thông báo rộng** vì dữ liệu riêng tư/bảo mật?
- Thông tin nào phải liên kết tới **nguồn sự thật** thay vì copy?
- Ai được quyền kết luận scope đã được thay chính thức?
- Điều gì khiến forecast cần được cập nhật lại ngay?

### Ví dụ thông báo cho stakeholder

> **Chủ đề: Phạm vi và điều kiện mở đăng ký ngày D.** CR-17 đã được xác nhận là điều kiện bắt buộc nhưng sandbox đối tác chưa sẵn sàng, nên chúng tôi chưa có bằng chứng tích hợp đạt. INC-04 đã được giảm tác động ban đầu; kiểm thử hồi quy phân quyền vẫn đang hoàn tất. Nhóm ưu tiên luồng đăng ký an toàn, đối soát trạng thái và vận hành, đề nghị hoãn email nhắc cùng lịch tháng nếu không thuộc nghĩa vụ D. Chúng tôi cần chủ cam kết xác nhận phương án khi sandbox tới muộn và thời điểm chốt phạm vi. Nếu các điều kiện Must/quality gate không đạt, chúng tôi sẽ trình no-go hoặc điều chỉnh cam kết, không phát hành đường đăng ký có rủi ro đã biết. Cập nhật tiếp theo dựa trên kết quả kiểm chứng và quyết định có thẩm quyền.

### Ví dụ thông báo cho nhóm thực hiện

> **Ưu tiên:** Hoàn tất triage/regression INC-04 theo incident channel; không chia dữ liệu người học trong thread công khai. M2 cần test đồng thời trên cơ chế lưu trữ phù hợp; M3 cần xác nhận phân quyền trên các endpoint liên quan; CR-17 đang bị chặn bởi sandbox đối tác. Giữ WIP Must ở mức nhóm xử lý nổi, không kéo S1/C1 mới. Điều kiện Done vẫn giữ; chưa có bằng chứng không được đánh dấu hoàn tất. Nếu dependency trễ qua mốc quyết định hoặc phát hiện rủi ro mới, thông báo PO, chủ cam kết và Security/Operations theo đường escalation đã xác nhận.

## 47. Câu hỏi tự kiểm tra

1. Ba dòng biến động “thay đổi yêu cầu, thời hạn cứng, công việc khẩn” khác nhau ở đâu?
2. Vì sao không nên xếp mọi yêu cầu “urgent” vào cùng một class of service?
3. Điều gì phải xác minh trước khi gọi CR-17 là Must?
4. Những nguồn nào chứng minh một deadline không được nhóm kỹ thuật tự thay?
5. Nếu không có nguồn nghĩa vụ rõ, có nên giả định mọi thứ Must không?
6. Một incident lộ dữ liệu có cần chờ Sprint Planning mới được xử lý không?
7. Severity và priority khác nhau thế nào?
8. Expedite policy cần những thành phần nào để tránh lạm dụng?
9. Khi incident lấy đi năng lực, vì sao forecast ban đầu phải được xem lại?
10. Vì sao 52 ngày-người nỗ lực không đồng nghĩa hoàn tất trong 15 ngày lịch?
11. Với 52 năng lực, 6 incident và Must mới 41, còn bao nhiêu nỗ lực thô trên giấy?
12. Vì sao 5 ngày-người còn trên giấy không phải buffer chắc chắn?
13. Thời gian chờ sandbox tác động tới đường găng như thế nào?
14. Mục tiêu của một spike API đối tác là gì?
15. Vì sao contract stub không thay test tích hợp thật?
16. Acceptance criteria và Definition of Done bảo vệ điều gì khác nhau?
17. Trong Scrum, điều gì không được đổi trong Sprint theo nghĩa gây nguy hại mục tiêu hoặc giảm chất lượng?
18. Ai có thẩm quyền hủy Sprint, và khi nào?
19. Sprint Backlog thuộc trách nhiệm của ai?
20. Product Owner có tự bỏ mọi yêu cầu pháp lý/bảo mật được không?
21. Lát cắt dọc khác việc chia theo DB/API/UI ở điểm nào?
22. Nếu M2 đã “code complete” nhưng test đồng thời thất bại, có được gọi Done không?
23. Những chỉ số nào cho biết PBI Must đang bị mắc kẹt?
24. Vì sao throughput task không thể tự chuyển thành throughput giá trị?
25. Có nên xếp hạng Developers bằng số commit/story points khi incident xuất hiện?
26. Một phương án mở cho 10% người dùng có tự đáp ứng hợp đồng mở cho toàn bộ không?
27. Feature flag giúp gì và không giúp gì đối với lỗi phân quyền đã biết?
28. Vì sao rollback code không tự khôi phục dữ liệu đã ghi sai?
29. Ai có quyền go/no-go và phải xem loại bằng chứng nào?
30. Khi không còn đường phát hành an toàn, phản ứng có trách nhiệm là gì?
31. Một thông báo scope thay đổi phải có những thông tin gì?
32. Khi nào nên dùng incident bridge thay vì chat async thông thường?
33. Vì sao Daily Scrum không phải cuộc họp báo cáo trạng thái cho mọi stakeholder?
34. Làm sao người vắng mặt hiểu quyết định trong tình huống khẩn?
35. Một Retrospective có thể cải thiện gì sau khi incident đã được xử lý?
36. Làm sao nhận ra “urgent liên tục” là dấu hiệu vấn đề hệ thống?
37. Chỉ số outcome nào phù hợp luồng đăng ký workshop? Cần định nghĩa mẫu số thế nào?
38. Nếu một chỉ số tốt lên, có thể lập tức kết luận thực hành Agile là nguyên nhân không?
39. Ba kết quả khác nhau của bài mô phỏng dẫn tới những quyết định phát hành nào?
40. Bạn sẽ nói gì với stakeholder khi dữ kiện hiện có **không cho phép cam kết chắc chắn**?

## 48. Ghi nhớ: phản ứng nhanh với sự thật, không nhanh bằng cách che rủi ro

Trong phát triển phần mềm thích ứng, **thay đổi yêu cầu, thời hạn cố định và công việc khẩn cấp thường không xảy ra lần lượt theo thứ tự dễ chịu**. Chúng có thể xuất hiện đồng thời, cạnh tranh cùng năng lực, dependency và quyền quyết định. Đây là lúc những nguyên tắc Agile cần thể hiện qua hành động: **làm rõ, ưu tiên, giới hạn WIP, giao Increment nhỏ, kiểm chứng chất lượng, nhận feedback và cập nhật kế hoạch trung thực**.

Hãy giữ mười điểm:

1. **Không gộp mọi biến động vào một queue mơ hồ:** Change request cần làm rõ; fixed date cần quản trị điều kiện; incident cần ứng phó theo tác động.
2. **Xác minh nguồn của điều bắt buộc:** Deadline, phạm vi, hợp đồng, an toàn và nghĩa vụ có người quyết định phù hợp.
3. **Bắt đầu từ người dùng và outcome:** Hỏi điều gì phải hoạt động đúng tại D, không đếm số tính năng trên slide.
4. **Phân biệt cấp độ Done:** Task xong không bằng PBI hoàn tất; Increment phải đạt DoD và điều kiện phát hành thích hợp.
5. **Coi incident là chi phí và cơ hội học hỏi thật:** Ưu tiên giảm tác động, sau đó cập nhật capacity, forecast, test và cách làm.
6. **Dùng Scrum đúng mục đích:** Giữ Sprint Goal/DoD, cho phép scope được làm rõ/thương lượng, chỉ PO hủy Sprint khi Goal trở nên lỗi thời.
7. **Dùng Kanban để thấy flow và việc khẩn:** WIP, age, throughput, cycle time và expedite policy giúp thấy bottleneck, không phải xếp hạng người.
8. **Dùng thực hành XP để giảm rủi ro tích hợp:** CI, test-first/TDD, review, pairing và refactoring hỗ trợ giao nhỏ nhưng đáng tin.
9. **Đưa ra trade-off có thẩm quyền và bất định rõ:** Hoãn tiện ích, thay phương án, release theo pha nếu hợp lệ hoặc no-go khi chưa an toàn.
10. **Khép kín vòng phản hồi:** Theo dõi người dùng, chất lượng và vận hành sau D; đưa bài học vào Product Backlog, runbook, test và cải tiến nhóm.

Trước khi nhận một yêu cầu khẩn mới vào kế hoạch đã đầy, hãy hỏi:

> **“Tác động thực và nghĩa vụ là gì; chúng ta đang lấy năng lực từ đâu; điều kiện Done nào không được hạ; ai có quyền quyết định thay phạm vi/ngày; và bằng chứng nào sẽ khiến chúng ta tiếp tục, đổi hướng hoặc dừng?”**

Một nhóm Agile trưởng thành không được nhận diện bởi khả năng **nói “có” với mọi yêu cầu**, mà bởi khả năng **đưa ra quyết định có căn cứ, bảo vệ người dùng, giao phần giá trị có thể kiểm chứng và học nhanh khi thực tế thay đổi**.
