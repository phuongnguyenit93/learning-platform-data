# Quản lý thay đổi mà vẫn giữ dấu vết mục tiêu và quyết định

> **Trọng tâm:** Agile chấp nhận yêu cầu thay đổi khi xuất hiện thông tin mới, nhưng mọi thay đổi đáng kể cần trả lời được: **Vì sao đổi? Ai quyết định? Mục tiêu nào được phục vụ? Điều gì đã bị thay thế? Làm sao biết thay đổi tạo ra kết quả mong muốn?** Dấu vết đủ rõ giúp nhóm thích ứng mà không mất định hướng, không lặp lại tranh luận cũ và không đánh đổi chất lượng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **khả năng thích ứng** và **khả năng truy vết quyết định** bổ trợ cho nhau trong phát triển phần mềm Agile.
2. Phân biệt **phản hồi**, **yêu cầu**, **giả thuyết**, **quyết định**, **Product Backlog Item**, **tiêu chí chấp nhận** và **bằng chứng kiểm chứng**.
3. Thiết kế chuỗi liên kết vừa đủ giữa **Product Goal → phản hồi và giả định → quyết định → backlog/user story → kiểm thử → Increment → kết quả sản phẩm**.
4. Xử lý yêu cầu mới trong và ngoài Sprint, làm rõ đánh đổi về phạm vi, giá trị, rủi ro và năng lực thực hiện.
5. Dùng mẫu **nhật ký quyết định** ngắn, lịch sử thay đổi của backlog và liên kết tới kiểm thử để người đến sau hiểu được lý do thay đổi.
6. Phối hợp thực hành **Scrum, Kanban và XP** nhằm giữ mục tiêu rõ, luồng công việc minh bạch và khả năng thay đổi mã an toàn.
7. Đánh giá hiệu quả quản lý thay đổi qua **kết quả sản phẩm, dòng công việc, chất lượng và khả năng tìm lại quyết định**.

## 2. Tại sao Agile vẫn cần dấu vết?

Giả sử nhóm đang làm tính năng kích hoạt tài khoản qua email. Một bên liên quan muốn thêm đăng nhập bằng mạng xã hội; bộ phận hỗ trợ báo nhiều email xác thực đến chậm; kỹ sư vận hành nhận thấy hệ thống gửi lại email đôi khi tạo nhiều liên kết xác thực còn hiệu lực. Cả ba thông tin đều có thể dẫn đến yêu cầu mới, nhưng **mức khẩn cấp, giá trị và tác động không giống nhau**.

Nếu nhóm cố giữ nguyên mọi điều đã lên kế hoạch, họ có thể bỏ qua lỗi ảnh hưởng trực tiếp người dùng. Nếu nhóm nhận tất cả yêu cầu ngay lập tức, Sprint Goal dễ mất ý nghĩa, người làm việc liên tục chuyển ngữ cảnh và không biết yêu cầu nào được ưu tiên vì lý do gì.

Một cách quản lý thay đổi có trách nhiệm phải đồng thời thực hiện hai việc:

- **Cho phép học và điều chỉnh:** phản hồi mới có thể làm thay đổi Product Backlog, tiêu chí chấp nhận, cách triển khai hoặc kế hoạch phát hành.
- **Giữ trí nhớ chung của nhóm:** mục tiêu, lý do chọn phương án, phần phạm vi đổi, rủi ro còn lại và bằng chứng cần kiểm chứng phải dễ tìm.

Tuyên ngôn Agile ưu tiên **phản hồi trước thay đổi hơn là bám sát kế hoạch**. Điều đó không có nghĩa kế hoạch, tài liệu hay sự thống nhất ban đầu vô giá trị. Những thứ đó vẫn hữu ích khi giúp nhóm quyết định và phối hợp. **Truy vết trong Agile phục vụ quyết định và học hỏi**, không nhất thiết phải là một ma trận tài liệu lớn cho mọi chi tiết.

### Minh họa hai kiểu thay đổi

| Tình huống | Cách xử lý thiếu kiểm soát | Cách xử lý có dấu vết |
|---|---|---|
| Người dùng báo email kích hoạt thường đến chậm | Developer sửa ngay ở đâu đó, không rõ nguyên nhân hay phạm vi | Ghi tín hiệu và mức ảnh hưởng; làm rõ mục tiêu; chọn cách khắc phục; cập nhật acceptance criteria, kiểm thử và kết quả quan sát |
| Bên kinh doanh đề xuất đăng nhập mạng xã hội giữa Sprint | Bổ sung vào Sprint vì người đề xuất có vị trí cao | Làm rõ giá trị và thời hạn; so với Sprint Goal; quyết định xử lý ngay hay đưa vào Product Backlog, ghi tác động lên việc đang làm |
| Quy tắc xác thực thay đổi vì yêu cầu an toàn mới | Chỉnh code và thông báo miệng | Liên kết yêu cầu an toàn, người chịu trách nhiệm phê duyệt theo chính sách, điều kiện nghiệm thu, kiểm thử và bản phát hành |
| Một quyết định cũ bị đặt câu hỏi sau ba tháng | Thành viên nhớ khác nhau và tranh luận lại | Tra được bối cảnh, giả định, lựa chọn từng xem xét, quyết định và bằng chứng khiến nhóm đổi hướng |

## 3. Phân biệt các đối tượng trong chuỗi thay đổi

Một lỗi phổ biến là gọi mọi ý kiến hoặc mong muốn là “yêu cầu đã được phê duyệt”. Cần tách các lớp thông tin:

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| **Tín hiệu/phản hồi** | Điều đã được báo cáo hoặc quan sát, chưa đủ để kết luận cách giải quyết | “Người dùng phải chờ email xác thực lâu.” |
| **Vấn đề cần giải quyết** | Tác động thật lên người dùng hay tổ chức | “Một số người không thể hoàn tất kích hoạt đúng lúc.” |
| **Giả định/giả thuyết** | Lời giải thích hoặc dự đoán cần kiểm chứng | “Chậm nhận email là nguyên nhân chính gây bỏ dở đăng ký.” |
| **Mục tiêu (goal/outcome)** | Kết quả nhóm muốn cải thiện, làm tiêu chí ưu tiên | “Người đăng ký mới có thể kích hoạt tài khoản đáng tin cậy.” |
| **Đề xuất thay đổi** | Một lựa chọn giải pháp có thể được đánh giá | “Thêm chức năng gửi lại email có kiểm soát.” |
| **Quyết định** | Lựa chọn có người chịu trách nhiệm, lý do và đánh đổi | “Ưu tiên sửa lỗi gửi lại email; đánh giá social login sau Sprint.” |
| **Product Backlog Item (PBI)/user story** | Công việc sản phẩm được mô tả, sắp thứ tự và làm rõ dần | “Là người đăng ký, tôi muốn gửi lại liên kết xác thực khi chưa nhận được email.” |
| **Acceptance criteria** | Điều kiện nghiệp vụ cụ thể để xác nhận hành vi của PBI | “Gửi lại không tạo cơ hội lạm dụng và liên kết cũ được xử lý theo chính sách.” |
| **Definition of Done (DoD)** | Chuẩn chất lượng chung để Increment được coi là hoàn thành | Kiểm thử thích hợp, tích hợp đạt, kiểm soát an toàn và tài liệu vận hành liên quan |
| **Bằng chứng/kết quả** | Quan sát sau thử nghiệm, kiểm thử hoặc phát hành | Tỷ lệ kích hoạt, thời gian email đến, lỗi phát sinh và phản hồi người dùng |

**Dấu vết không có nghĩa mọi đối tượng đều phải thành một tệp riêng.** Với thay đổi nhỏ, một PBI kèm lý do, tiêu chí chấp nhận và liên kết tới pull request có thể đủ. Với thay đổi kiến trúc, bảo mật, hợp đồng hoặc nhiều nhóm, cần bản quyết định rõ hơn.

### Phân biệt output và outcome

- **Output:** nhóm đã triển khai nút “Gửi lại email”, thêm API hoặc hoàn thành ba story.
- **Outcome:** người dùng kích hoạt thành công dễ hơn và ít phải liên hệ hỗ trợ.

Nếu chỉ ghi “đã hoàn thành yêu cầu” mà không quan sát outcome, nhóm chưa biết quyết định thay đổi có giải quyết đúng vấn đề hay không.

## 4. Mô hình dấu vết nhẹ: từ mục tiêu đến bằng chứng

Một chuỗi liên kết đủ dùng có thể được trình bày như sau:

~~~mermaid
flowchart TD
    A["Product Goal / kết quả người dùng"] --> B["Tín hiệu, phản hồi, giả thuyết"]
    B --> C["Quyết định ưu tiên và đánh đổi"]
    C --> D["Product Backlog Item / user story"]
    D --> E["Acceptance criteria và kiểm thử"]
    E --> F["Increment đạt Definition of Done"]
    F --> G["Phát hành, phản hồi và số liệu thực tế"]
    G --> H["Đánh giá giả thuyết, quyết định tiếp"]
    H --> C
    H --> A
~~~

Sơ đồ này thể hiện **logic truy vết**, không quy định bắt buộc phải làm theo thứ tự cứng nhắc. Có khi phản hồi phát hiện lỗi sản xuất cần xử lý ngay; có khi phải làm spike kỹ thuật hoặc phỏng vấn trước khi tạo PBI. Chuỗi vẫn hữu ích để đặt câu hỏi về mục đích và bằng chứng.

### 4.1. Liên kết những gì có ích, tránh nhân bản tài liệu

Một nhóm dùng issue tracker và Git có thể chọn:

| Nơi lưu | Thông tin nên có | Liên kết hữu ích |
|---|---|---|
| **Product Goal / mục tiêu sản phẩm** | Kết quả muốn đạt, bối cảnh và cách nhận biết tiến triển | Epic/chủ đề backlog và nguồn dữ liệu outcome |
| **PBI hoặc user story** | Ai có nhu cầu, vì sao có giá trị, trạng thái, tiêu chí chấp nhận | Mục tiêu, phản hồi đầu vào, quyết định liên quan |
| **Nhật ký quyết định** | Lựa chọn, lý do, các phương án đã cân nhắc, đánh đổi, ngày và người chịu trách nhiệm | PBI, tài liệu chính sách, thử nghiệm hoặc bằng chứng |
| **Pull request, commit, test** | Điều được thay đổi trong hệ thống và cách kiểm chứng | Mã PBI, acceptance criteria, bản build |
| **Release note / dashboard** | Phần đã phát hành, tác động đã biết và kết quả quan sát | PBI, quyết định và tín hiệu chất lượng/outcome |

Ví dụ một luồng liên kết **hoàn toàn minh họa**:

~~~text
PG-01: Người mới kích hoạt tài khoản thành công
  └── OBS-08: Phản hồi email xác thực đến chậm
      └── DEC-017: Ưu tiên sửa luồng gửi lại, chưa làm social login
          └── PBI-184: Gửi lại liên kết xác thực có kiểm soát
              ├── AC-1: Có phản hồi trạng thái rõ ràng
              ├── AC-2: Chặn lạm dụng gửi lặp
              ├── TEST-184: Kiểm thử hành vi chính và lỗi
              └── PR-245: Thực hiện và kiểm tra thay đổi
                  └── RELEASE-1.8: Bản triển khai có chức năng mới
                      └── METRIC-ACT: Tỷ lệ kích hoạt và lỗi gửi lại
~~~

Các mã ở trên là ví dụ để nhìn thấy **đường dẫn lý do → thực hiện → kiểm chứng**, không phải quy ước bắt buộc. Nếu công cụ đã hỗ trợ đường liên kết hai chiều, tận dụng nó trước khi tự xây bảng Excel hoặc sao chép nội dung sang nhiều nơi.

### 4.2. Cần mức truy vết nào?

| Mức thay đổi | Ví dụ | Dấu vết tối thiểu gợi ý |
|---|---|---|
| **Nhỏ, phạm vi hẹp** | Sửa lỗi chính tả hoặc cải thiện thông báo không đổi logic | Issue/PR, mục đích ngắn và cách xác minh |
| **Có tác động nghiệp vụ** | Đổi quy tắc khóa tài khoản hoặc luồng gửi lại email | PBI, tiêu chí chấp nhận trước/sau, quyết định, kiểm thử, kết quả |
| **Ảnh hưởng nhiều nhóm hoặc kiến trúc** | Thay cơ chế xác thực hoặc hợp đồng API giữa nhiều hệ thống | Bản quyết định riêng, lựa chọn và đánh đổi, người tham vấn, kế hoạch chuyển đổi |
| **An toàn, bảo mật, quy định hoặc giao dịch quan trọng** | Đổi kiểm soát truy cập hay quy tắc lưu dữ liệu | Dấu vết theo chính sách tổ chức và nghĩa vụ áp dụng, bằng chứng kiểm chứng, phê duyệt khi thực sự bắt buộc |

Quy tắc thực dụng: **càng nhiều người bị ảnh hưởng, chi phí đảo ngược càng cao hoặc rủi ro càng lớn, dấu vết càng cần rõ**. Không biến một thay đổi một dòng văn bản thành hồ sơ phê duyệt nhiều trang.

## 5. Quy trình xử lý yêu cầu thay đổi từ đầu đến cuối

Thay đổi có thể xuất hiện bất kỳ lúc nào; điều quan trọng là nhóm biết **ai có trách nhiệm quyết định và làm thế nào mọi người biết quyết định đó**.

### Bước 1 — Ghi nhận tín hiệu, chưa vội chốt giải pháp

Khi tiếp nhận yêu cầu, hãy nêu rõ:

- **Nguồn:** phản hồi khách hàng, quan sát vận hành, số liệu, nghiên cứu, thay đổi quy định hay giả định nội bộ?
- **Vấn đề:** người dùng bị ảnh hưởng thế nào, mức nghiêm trọng và tần suất ra sao?
- **Thông tin đã xác nhận:** có ví dụ tái hiện, log phù hợp, dữ liệu hoặc liên hệ người nắm nghiệp vụ không?
- **Phần chưa biết:** nguyên nhân, phạm vi ảnh hưởng, lựa chọn khắc phục và rủi ro nào còn là giả định?

Thí dụ, “Cần thêm social login ngay” là **đề xuất giải pháp**, chưa chỉ ra vấn đề đang tồn tại. Câu hỏi tốt hơn: “Nhóm người dùng nào không thể hoàn thành đăng ký bằng phương thức hiện tại, và có bằng chứng gì?”

### Bước 2 — Phân loại mức cần phản ứng

| Loại | Cách ưu tiên xem xét |
|---|---|
| **Sự cố đang gây mất dữ liệu, lỗi nghiêm trọng hoặc rủi ro an toàn** | Kích hoạt cách ứng phó theo chính sách, xử lý ngay với người có trách nhiệm và ghi lại tác động |
| **Thay đổi bắt buộc có thời hạn bên ngoài** | Xác minh ràng buộc, hạn và trách nhiệm; nêu rõ việc nào phải dịch chuyển |
| **Phản hồi làm thay đổi giả thuyết về sản phẩm** | So với Product Goal, cân nhắc điều chỉnh backlog hoặc phạm vi thử nghiệm |
| **Ý tưởng hữu ích nhưng chưa cấp bách** | Đưa vào Product Backlog, bổ sung bằng chứng và sắp xếp thứ tự thích hợp |
| **Chi tiết triển khai kỹ thuật** | Developers trao đổi và điều chỉnh trong phạm vi trách nhiệm, miễn đạt tiêu chí và chuẩn chất lượng |

Phân loại để **chọn nhịp phản ứng**, không để loại bỏ ý kiến của bất kỳ bên nào. Mức khẩn cấp phải có căn cứ; nếu mọi yêu cầu đều được gắn “khẩn”, nhóm sẽ mất khả năng bảo vệ công việc đang diễn ra.

### Bước 3 — Liên hệ với mục tiêu và giả định

Hỏi:

1. Yêu cầu giúp đạt **Product Goal**, mục tiêu người dùng hoặc nghĩa vụ nào?
2. Có liên quan **Sprint Goal** hay chính sách luồng hiện tại không?
3. Nếu không làm lúc này, hậu quả và chi phí cơ hội là gì?
4. Dữ liệu mới có đủ để đổi quyết định trước đây, hay cần thử nghiệm nhỏ?

Không phải yêu cầu nào không liên quan Sprint Goal cũng bị từ chối. Yêu cầu ấy có thể có giá trị lớn cho Product Backlog, cho kế hoạch sau hoặc cho hoạt động khám phá độc lập. Việc xác định **điểm phù hợp trong dòng công việc** giúp tránh chen ngang tùy hứng.

### Bước 4 — Cân nhắc phương án và đánh đổi

Đừng chỉ hỏi “Có làm hay không?”. Một quyết định tốt thường cân nhắc ít nhất các lựa chọn:

- **Thực hiện ngay** và thay đổi các hạng mục đang làm với tác động được công khai.
- **Giải quyết một lát cắt nhỏ** đủ giảm rủi ro hoặc kiểm chứng giả định.
- **Đưa vào backlog** để làm rõ và sắp xếp thứ tự sau.
- **Chưa thực hiện** vì bằng chứng, lợi ích hoặc tính khả thi chưa đủ.

Xem giá trị, mức khẩn, rủi ro, phụ thuộc, năng lực nhóm, cơ hội học hỏi và **công việc buộc phải lùi hoặc bỏ**. Ước lượng vừa đủ để quyết định; không phải mọi đề xuất đều cần một dự án nghiên cứu lớn.

### Bước 5 — Xác nhận quyết định và trách nhiệm

Đối với **Product Backlog**, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog trong Scrum; các bên liên quan đóng góp thông tin. Developers chịu trách nhiệm lập kế hoạch thực hiện và chất lượng công việc trong phạm vi của họ.

Với thay đổi liên quan an toàn, hợp đồng, dữ liệu hoặc quy định, có thể có người/phòng ban khác cần tham vấn hoặc chấp thuận theo chính sách hiện hành. **Không tự coi Product Owner là người được phép miễn trừ mọi ràng buộc.**

Quyết định nên ghi tối thiểu **lựa chọn, lý do, người chịu trách nhiệm, thời điểm và tác động lên kế hoạch/cam kết**.

### Bước 6 — Cập nhật những nơi thực sự chịu ảnh hưởng

Tùy trường hợp, cập nhật:

- Thứ tự và nội dung **Product Backlog**.
- **Sprint Backlog** hoặc chính sách Kanban để phản ánh việc thay đổi thứ tự, phạm vi hay công việc đang thực hiện.
- **User story và acceptance criteria**, ví dụ bình thường, trường hợp biên và lỗi.
- **Kiểm thử**, mã nguồn, tài liệu tích hợp và vận hành liên quan.
- **Bản ghi quyết định** nếu thay đổi giải pháp hoặc ràng buộc có tác động đáng kể.

Không nhất thiết lập lại mọi tài liệu từ đầu. Điều cốt yếu là **không để acceptance criteria đang áp dụng khác với cách code và test được thực hiện mà không có lý do giải thích được**.

### Bước 7 — Kiểm chứng Increment và xem lại outcome

Sau khi thực hiện, cần xác nhận:

- Phần đã giao **đạt Definition of Done** và những ràng buộc chất lượng áp dụng.
- Hành vi mới đáp ứng acceptance criteria đã thống nhất.
- Không phá vỡ các hành vi cần duy trì, đặc biệt với luồng an toàn và nghiệp vụ quan trọng.
- Dữ liệu sau phát hành có xác nhận giả thuyết ban đầu không, có tác dụng phụ không?

Nếu kết quả không đạt, tiếp tục học và cập nhật quyết định thay vì chỉ kết luận “ticket đã Done”.

## 6. Mẫu ghi quyết định ngắn, dễ sử dụng lại

Không cần viết một biên bản dài cho mọi thay đổi. Với quyết định quan trọng, một **decision log/decision record** có thể gói trong một thẻ hoặc trang ngắn:

~~~markdown
## DEC-017 — Ưu tiên ổn định xác thực email

- Ngày: 2026-11-23 (ví dụ minh họa)
- Trạng thái: Đã chọn, chờ kiểm chứng kết quả
- Người chịu trách nhiệm quyết định: Product Owner
- Mục tiêu liên quan: PG-01 — Người đăng ký mới kích hoạt thành công
- Tín hiệu: OBS-08 — Email xác thực đến chậm ở một số trường hợp
- Vấn đề: Người dùng bỏ dở trước khi kích hoạt; nguyên nhân chưa rõ đủ
- Lựa chọn đã xem xét:
  1. Làm social login ngay trong Sprint
  2. Sửa luồng gửi lại email và đo kết quả
  3. Không đổi phạm vi hiện tại
- Quyết định: Chọn (2); đưa social login vào backlog để làm rõ giá trị
- Lý do: Phù hợp Sprint Goal; xử lý tín hiệu đang cản luồng chính
- Đánh đổi: Hoãn đánh giá social login; giảm một phần UI thứ yếu
- Tiêu chí kiểm chứng: PBI-184, AC-1..AC-3, TEST-184
- Theo dõi: Tỷ lệ kích hoạt, lỗi gửi lại, phản hồi hỗ trợ
- Điểm xem lại: Sau khi có dữ liệu sử dụng đủ cho quyết định tiếp
- Liên kết: PBI-184, PR-245, tài liệu vận hành liên quan
~~~

Các mã và ngày trong mẫu đều **minh họa**. Nhóm có thể chỉ giữ 5–7 trường nếu phần còn lại đã nằm trong issue tracker. Quan trọng nhất là ai đọc lại cũng có thể hiểu: **quyết định nào được đưa ra, trên căn cứ nào và khi nào cần xem lại**.

### 6.1. Quyết định có thể thay đổi nhưng lịch sử phải hiểu được

Khi bằng chứng mới xuất hiện, **không âm thầm sửa quyết định cũ thành điều hiện tại** khiến người đọc tưởng nhóm đã luôn biết trước kết quả. Có thể:

- Đánh dấu quyết định cũ là **“được thay thế”** và liên kết tới bản mới.
- Ghi ngắn **bằng chứng mới** khiến nhóm đổi hướng.
- Cập nhật PBI, tiêu chí chấp nhận và kiểm thử liên quan.

Ví dụ: DEC-017 ưu tiên email. Sau khi quan sát đủ, nhóm phát hiện người dùng ở một phân khúc có thể không truy cập email trong thời gian cần thiết; quyết định mới có thể ưu tiên một phương thức xác minh khác. Cả hai quyết định đều có thể **hợp lý ở thời điểm của mình** khi điều kiện và bằng chứng khác nhau.

### 6.2. Phân biệt bản ghi quyết định sản phẩm và kiến trúc

Nếu thay đổi ảnh hưởng giao diện, hành vi người dùng và ưu tiên sản phẩm, quyết định thường liên kết trực tiếp PBI và outcome. Nếu thay đổi liên quan **kiến trúc lâu dài** (chẳng hạn chuyển nền tảng xử lý sự kiện), một **Architecture Decision Record (ADR)** có thể ghi thêm bối cảnh kỹ thuật, phương án, ràng buộc, hệ quả và cách di chuyển.

Không ép mọi câu hỏi nhỏ thành ADR. Cũng không để một quyết định kiến trúc có hệ quả nhiều năm chỉ nằm trong tin nhắn cá nhân.

## 7. Quản lý thay đổi trong Scrum: mục tiêu ổn định, phạm vi được học thêm

Scrum dựa trên **minh bạch, kiểm tra và thích ứng**. Product Backlog là danh sách công việc của sản phẩm được cập nhật khi nhóm hiểu biết hơn. Sprint Backlog gồm Sprint Goal, các PBI được chọn và kế hoạch thực hiện; kế hoạch được Developers điều chỉnh khi học thêm.

### 7.1. Ba điểm cần phân biệt

| Thành phần | Mức độ ổn định và cơ chế điều chỉnh | Ý nghĩa khi yêu cầu đổi |
|---|---|---|
| **Product Goal** | Mục tiêu dài hơn giúp định hướng Product Backlog; được xem xét khi bối cảnh thay đổi quan trọng | Đặt câu hỏi thay đổi có phục vụ kết quả sản phẩm không |
| **Sprint Goal** | Mục tiêu duy nhất của Sprint, tạo tính tập trung | Không chấp nhận thay đổi làm nguy hại Sprint Goal khi Sprint đang diễn ra |
| **Phạm vi chi tiết/Sprint Backlog** | Có thể làm rõ, cập nhật và thương lượng khi hiểu biết tăng | Developers cùng Product Owner có thể thương lượng phạm vi mà vẫn bảo vệ Sprint Goal |

Theo Scrum Guide, **không đưa ra thay đổi gây nguy hại Sprint Goal và chất lượng không được suy giảm**. Nếu Sprint Goal trở nên lỗi thời, **Product Owner có quyền hủy Sprint**. Đây là cơ chế dành cho thay đổi bối cảnh thực sự, không phải cách xử lý mọi yêu cầu chen ngang.

Trong Sprint, một yêu cầu mới nên được xét theo mục tiêu. Ví dụ sửa lỗi gửi email có thể giúp đạt Sprint Goal; thêm social login có thể làm mất tập trung nếu chưa chứng minh nó cần thiết cho kết quả hiện tại.

### 7.2. Trao đổi trong các sự kiện Scrum

- **Sprint Planning:** dùng phản hồi và các quyết định ưu tiên để xác định vì sao Sprint có giá trị, lựa chọn công việc và lập kế hoạch đạt Sprint Goal.
- **Daily Scrum:** Developers kiểm tra tiến độ tới Sprint Goal, nhận diện điểm bị chặn và điều chỉnh kế hoạch. Không biến sự kiện thành buổi xin phép mọi thay đổi kỹ thuật.
- **Sprint Review:** cùng bên liên quan kiểm tra Increment và bối cảnh hiện tại; thông tin mới có thể dẫn đến điều chỉnh Product Backlog.
- **Sprint Retrospective:** kiểm tra hiệu quả cách phối hợp, gồm cách yêu cầu mới đến nhóm, thời gian chờ quyết định và tác động của việc đổi ưu tiên; chọn cải tiến có thể thực hiện.

Ghi chú: **Backlog refinement** có thể diễn ra thường xuyên để làm rõ và chia nhỏ PBI, nhưng không phải một sự kiện chính thức cố định trong Scrum Guide.

## 8. Quản lý thay đổi với Kanban và XP

### 8.1. Kanban: minh bạch tác động lên dòng công việc

Khi công việc đến liên tục, nhóm có thể dùng bảng:

~~~text
Chưa ưu tiên -> Sẵn sàng -> Đang thực hiện -> Kiểm chứng -> Hoàn thành
                    |            WIP            |
                    +--- Việc bị chặn được hiển thị ---+
~~~

Tên cột và mức WIP là **thỏa thuận tùy ngữ cảnh**, không phải mẫu bắt buộc. Khi một yêu cầu gấp xuất hiện, hỏi:

1. Có thực sự cần ưu tiên vượt các công việc hiện tại không?
2. Nếu nhận ngay, **việc nào phải dừng/chờ** và ai cần biết?
3. Việc đang xử lý bị chặn do thiếu quyết định nào?
4. Chính sách xử lý việc khẩn có được ghi rõ và áp dụng nhất quán không?

Kanban có thể giúp đo **WIP, cycle time, throughput và work item age**. Một thay đổi ưu tiên tưởng là “nhanh” nhưng khiến nhiều việc già đi hoặc tăng chuyển ngữ cảnh cần được nhìn thấy. Không dùng số việc hoàn thành làm tiêu chí duy nhất để ép nhóm nhận thêm yêu cầu.

### 8.2. XP: thay đổi yêu cầu nhưng vẫn bảo vệ hành vi

Thay đổi yêu cầu thường dẫn đến thay đổi code. Các thực hành của **Extreme Programming (XP)** giúp giảm chi phí và rủi ro:

- **Kiểm thử hành vi và TDD khi phù hợp:** thể hiện quy tắc mới qua ví dụ kiểm chứng được.
- **Continuous Integration:** phát hiện nhanh xung đột và hồi quy khi nhiều thay đổi được tích hợp.
- **Refactoring:** giữ cấu trúc mã dễ sửa mà không vô tình đổi hành vi còn hợp lệ.
- **Pair programming/code review:** chia sẻ cách hiểu và làm rõ ranh giới nghiệp vụ/thiết kế.
- **Phát hành từng phần và quan sát:** giới hạn ảnh hưởng của thay đổi khi hệ thống hỗ trợ.

Không phải cứ có nhiều kiểm thử tự động là đã xác nhận **giá trị sản phẩm**. Kiểm thử kỹ thuật xác nhận hệ thống hoạt động theo quy tắc; số liệu và phản hồi sau phát hành giúp kiểm tra quy tắc đó có giải quyết đúng vấn đề người dùng hay không.

## 9. Tình huống xuyên suốt: yêu cầu mới xuất hiện giữa Sprint

### 9.1. Bối cảnh trước thay đổi

Một nhóm đang phát triển nền tảng học trực tuyến. **Product Goal** hiện tại là giúp người học mới kích hoạt tài khoản và bắt đầu bài học đầu tiên dễ dàng. Trong Sprint hai tuần, **Sprint Goal** là:

> “Người đăng ký mới có thể xác thực email theo một luồng rõ ràng, tin cậy và biết cách xử lý khi chưa nhận được thư.”

Các PBI liên quan đang gồm: hiển thị trạng thái xác thực, gửi lại email có kiểm soát và thông báo lỗi dễ hiểu. Nhóm đã thống nhất Definition of Done cho kiểm thử, an toàn và khả năng vận hành.

Giữa Sprint xuất hiện **hai tín hiệu**:

- **Tín hiệu A:** bộ phận hỗ trợ đưa ra các trường hợp email xác thực đến muộn hoặc gửi lại gây nhầm lẫn.
- **Tín hiệu B:** bộ phận kinh doanh đề xuất thêm đăng nhập bằng mạng xã hội vì một khách hàng doanh nghiệp quan tâm.

Hai tín hiệu đều đáng nghe, nhưng **không đương nhiên trở thành công việc ngay trong Sprint**.

### 9.2. Phân tích và lựa chọn

| Phương án | Liên hệ mục tiêu | Tác động/rủi ro | Đề xuất |
|---|---|---|---|
| Giữ nguyên mọi chi tiết kế hoạch, bỏ qua phản hồi A | Giữ danh sách ban đầu nhưng có thể bỏ qua vấn đề trực tiếp | Rủi ro giao chức năng vẫn gây khó khăn | Không ưu tiên |
| Làm social login ngay vì có đề xuất B | Có thể có giá trị cho sản phẩm về sau; hiện chưa rõ tác động lên Sprint Goal | Thêm tích hợp, an toàn, kiểm thử, phụ thuộc và chuyển ngữ cảnh | Làm rõ nhu cầu, đưa vào Product Backlog |
| Làm rõ A và điều chỉnh luồng gửi lại email trong phạm vi Sprint Goal | Gắn trực tiếp với kết quả hiện tại | Cần cập nhật tiêu chí và kiểm thử; có thể giảm một phần UI phụ | **Ưu tiên sau khi kiểm tra mức ảnh hưởng** |
| Dừng Sprint để thay toàn bộ hướng đi | Chỉ cần cân nhắc khi Sprint Goal thực sự lỗi thời | Gián đoạn lớn; hiện không có bằng chứng như vậy | Chưa có căn cứ |

**Quyết định minh họa:** Product Owner và Developers trao đổi, chọn kiểm tra và xử lý những trường hợp gửi lại email ảnh hưởng Sprint Goal. Nhóm thương lượng phạm vi một phần giao diện thứ yếu để bảo đảm đủ công kiểm thử tích hợp. Product Owner đưa ý tưởng social login vào Product Backlog để xác định giá trị, ràng buộc và thời điểm ưu tiên phù hợp.

### 9.3. Cập nhật user story và acceptance criteria

**User story đã làm rõ:**

> Là người vừa đăng ký tài khoản, tôi muốn biết phải làm gì nếu chưa nhận được email xác thực để có thể hoàn tất kích hoạt mà không bị gửi những liên kết gây nhầm lẫn.

**Ví dụ tiêu chí chấp nhận sau trao đổi:**

~~~gherkin
Tính năng: Gửi lại email xác thực có kiểm soát

Kịch bản: Người dùng chưa xác thực yêu cầu gửi lại
  Cho trước tài khoản đang ở trạng thái chưa xác thực
  Và người dùng đủ điều kiện gửi lại theo chính sách hiện hành
  Khi người dùng yêu cầu gửi lại email xác thực
  Thì hệ thống xác nhận đã tiếp nhận yêu cầu theo cách không tiết lộ dữ liệu nhạy cảm
  Và lưu kết quả xử lý để có thể theo dõi lỗi

Kịch bản: Yêu cầu gửi liên tiếp vượt giới hạn
  Cho trước người dùng đã vượt giới hạn gửi lại theo chính sách hiện hành
  Khi người dùng tiếp tục yêu cầu gửi
  Thì hệ thống không thực hiện gửi không giới hạn
  Và hiển thị hướng dẫn phù hợp mà không tiết lộ thông tin bảo mật

Kịch bản: Tài khoản đã xác thực
  Cho trước tài khoản đã được xác thực thành công
  Khi có yêu cầu gửi lại liên kết xác thực
  Thì hệ thống không cấp một luồng xác thực mới không cần thiết
  Và hiển thị trạng thái tài khoản phù hợp

Kịch bản: Dịch vụ gửi gặp lỗi
  Cho trước hệ thống gửi email gặp lỗi tạm thời
  Khi một yêu cầu gửi lại được xử lý
  Thì hệ thống ghi nhận lỗi và xử lý theo chính sách thử lại
  Và không báo thành công đã gửi khi chưa có bằng chứng tương ứng
~~~

Các giới hạn gửi, chính sách hiệu lực của token, khả năng kiểm chứng và thông điệp lỗi phải được thống nhất theo yêu cầu an toàn thực tế. Đừng tự đưa giá trị cụ thể như “gửi tối đa ba lần trong một giờ” nếu nhóm chưa xác minh ràng buộc nghiệp vụ và bảo mật.

### 9.4. Ghi dấu vết trước/sau

| Câu hỏi truy vết | Trước khi có phản hồi | Sau quyết định |
|---|---|---|
| **Mục tiêu** | Người mới xác thực email tin cậy | **Giữ nguyên** |
| **Thông tin mới** | Chưa có ví dụ chi tiết về lỗi gửi lại | Bổ sung tín hiệu A và trường hợp tái hiện |
| **Phạm vi** | Luồng hiển thị, gửi lại cơ bản, thông báo lỗi | Làm rõ xử lý trùng, quá giới hạn và thất bại; hoãn UI phụ |
| **Đề xuất khác** | Chưa có social login trong Sprint | Ghi tín hiệu B, lưu ở Product Backlog để nghiên cứu |
| **Acceptance criteria** | Chưa mô tả rõ trạng thái lỗi và gửi lặp | Bổ sung trường hợp biên và cách phản hồi phù hợp |
| **Kiểm thử** | Chủ yếu luồng thành công | Thêm kiểm thử gửi lặp, tài khoản đã xác thực, lỗi dịch vụ |
| **Quyết định** | Kế hoạch Sprint trước khi nhận phản hồi | Ghi người quyết định, lý do, tác động, liên kết PBI/test |
| **Bằng chứng kết quả** | Chưa có dữ liệu sau thay đổi | Dự kiến đo tỷ lệ xác thực, lỗi gửi lại, phản hồi hỗ trợ |

### 9.5. Kiểm tra kết quả sau phát hành

Nhóm không kết luận thành công chỉ vì nút “Gửi lại” hoạt động. Cần quan sát, chẳng hạn:

- Tỷ lệ tài khoản mới kích hoạt trong khoảng thời gian được định nghĩa nhất quán.
- Tỷ lệ lỗi khi gửi lại, số yêu cầu gửi lặp và tín hiệu lạm dụng.
- Số yêu cầu hỗ trợ liên quan email xác thực, có phân biệt thời gian và lượng người dùng.
- Lỗi nghiêm trọng phát sinh, độ ổn định dịch vụ gửi và phản hồi thực tế.

Nếu số liệu tốt lên, nhóm có thêm bằng chứng giữ hoặc mở rộng giải pháp. Nếu lỗi gửi ít hơn nhưng tỷ lệ kích hoạt không thay đổi, có thể phải xem lại giả thuyết về nguyên nhân bỏ dở và khám phá các bước khác của luồng đăng ký.

**Điều học được:** dấu vết là một chuỗi giải thích được từ **tín hiệu → mục tiêu → quyết định → hành vi → bằng chứng**, không chỉ là lịch sử chỉnh sửa ticket.

## 10. Tránh hai cực đoan: thay đổi tùy hứng và quản trị quá nặng

| Cực đoan | Dấu hiệu | Hệ quả | Cách điều chỉnh |
|---|---|---|---|
| **Thay đổi tùy hứng** | Yêu cầu chen thẳng vào việc đang làm qua tin nhắn cá nhân | WIP tăng, thiếu ưu tiên, không ai biết vì sao phạm vi đổi | Tạo nguồn công việc chung và quyết định ưu tiên minh bạch |
| **Đóng băng yêu cầu** | Thông tin mới quan trọng bị bỏ qua vì “đã chốt tài liệu” | Giao đúng đặc tả cũ nhưng sai nhu cầu hiện tại | Xem xét thay đổi theo bằng chứng và giá trị |
| **Ghi chép quá ít** | Quyết định chỉ tồn tại trong cuộc gọi | Người vắng mặt hiểu khác nhau; lặp lại tranh luận | Tóm tắt lý do, người quyết định, tác động và liên kết tại nơi dễ tìm |
| **Ghi chép quá nhiều** | Mọi sửa chữ đều yêu cầu nhiều biểu mẫu | Thời gian chờ tăng, tài liệu trùng và lỗi thời | Chọn mức dấu vết theo rủi ro và tác động |
| **Ưu tiên theo quyền lực** | Người nói lớn nhất đưa mọi việc lên đầu | Mục tiêu và Product Backlog mất ý nghĩa | Yêu cầu nêu vấn đề, bằng chứng và đánh đổi |
| **Đổi acceptance criteria sau khi xong để hợp thức hóa** | Tiêu chí được viết lại nhằm biến việc chưa đạt thành “Done” | Không còn căn cứ khách quan để đánh giá | Thảo luận thay đổi công khai, giữ lịch sử và kiểm chứng lại |
| **Đổi mã nhưng bỏ cập nhật kiểm thử** | Hành vi mới không có trường hợp xác nhận | Lỗi hồi quy và hiểu lầm tái phát | Đồng bộ story, acceptance criteria và test liên quan |
| **Coi mọi thay đổi là khẩn cấp** | Quy tắc ưu tiên bị vượt liên tục | Tắc nghẽn luồng, không thể dự báo | Làm rõ lớp dịch vụ/chính sách khẩn và hậu kiểm |

**Nguyên tắc thực hành:** thay đổi nhanh ở nơi có thể đảo ngược với rủi ro thấp; ghi nhận và kiểm chứng kỹ hơn ở nơi gây tác động lớn, khó đảo ngược hoặc cần tuân thủ ràng buộc cụ thể.

## 11. Đo hiệu quả quản lý thay đổi

Số change request được “đóng” không tự chứng minh rằng nhóm quản lý thay đổi tốt. Cần xem **độ rõ của quyết định, tác động lên dòng công việc, chất lượng và giá trị sản phẩm**.

| Tín hiệu | Câu hỏi nó giúp trả lời | Cách dùng thận trọng |
|---|---|---|
| **Thời gian chờ quyết định** | Yêu cầu có đủ thông tin phải chờ bao lâu để biết sẽ làm gì? | Tách thời gian chờ thực sự khỏi thời gian cần nghiên cứu |
| **Số/tuổi hạng mục bị chặn vì yêu cầu mơ hồ** | Nhóm có thường bị kẹt vì thiếu người quyết định hay tiêu chí? | Xem phân loại nguyên nhân, tránh quy lỗi cá nhân |
| **WIP, cycle time, throughput** | Việc ưu tiên lại có khiến luồng nghẽn, chuyển ngữ cảnh nhiều không? | Giữ định nghĩa đo ổn định và xem đặc tính từng loại việc |
| **Tần suất mở lại do hiểu sai yêu cầu** | Có bao nhiêu việc phải làm lại vì quyết định hoặc tiêu chí thiếu rõ? | Phân biệt làm lại do hiểu sai với thay đổi hợp lý nhờ phản hồi mới |
| **Lỗi sau phát hành** | Việc đổi yêu cầu có kéo theo lỗi hồi quy hoặc rủi ro mới? | Cân nhắc độ nghiêm trọng, phạm vi và thời gian quan sát |
| **Mức độ truy xuất quyết định** | Thành viên mới có tìm được vì sao một quy tắc tồn tại không? | Kiểm tra bằng một số quyết định quan trọng, không yêu cầu ghi mọi thao tác |
| **Outcome sản phẩm** | Thay đổi có cải thiện vấn đề người dùng đã nêu không? | Xem số liệu trước/sau, phân khúc, yếu tố gây nhiễu và độ tin cậy |
| **Mức gián đoạn Sprint Goal** | Các thay đổi có liên tục khiến nhóm mất mục tiêu không? | Không coi mọi thay đổi trong Sprint là sai; xem nguyên nhân và giá trị |

### Một phép thử cải tiến quy trình

**Quan sát:** nhóm phải hỏi lại quy tắc nghiệp vụ ở nhiều PBI; có những quyết định chỉ nằm trong tin nhắn riêng.

**Giả thuyết:** với các PBI có ảnh hưởng nghiệp vụ cao, ghi ngắn **mục tiêu, người quyết định, hai trường hợp biên và liên kết đến kiểm thử** sẽ giảm thời gian chờ làm rõ và việc mở lại do hiểu sai.

**Thử nghiệm:** áp dụng mẫu ghi nhẹ ở một số PBI trong hai vòng làm việc, không bắt tất cả yêu cầu nhỏ tạo hồ sơ mới.

**Đo:** thời gian chờ, số lần mở lại do tiêu chí mơ hồ, lỗi liên quan và thời gian nhóm tốn cho ghi chép.

**Đánh giá:** nếu thời gian ghi tăng nhưng không giảm việc hỏi lại hay lỗi, cần điều chỉnh mẫu hoặc cách làm; không tự mặc định thêm tài liệu sẽ có lợi.

Thời lượng và số liệu ở đây là **gợi ý thiết kế thử nghiệm**, không phải tiêu chuẩn chung cho mọi nhóm.

## 12. Checklist thực hành khi nhận thay đổi

Dùng các câu hỏi sau trước khi đưa thay đổi vào phạm vi đang làm:

1. **Vấn đề thật là gì?** Có ví dụ, tín hiệu hoặc bằng chứng nào; phần nào chỉ là giả định?
2. **Liên quan mục tiêu nào?** Product Goal, Sprint Goal, outcome người dùng hoặc ràng buộc bắt buộc nào?
3. **Mức khẩn cấp ra sao?** Nếu chưa làm ngay, hậu quả thực tế là gì?
4. **Ai chịu trách nhiệm quyết định?** Những ai cần được tham vấn?
5. **Các lựa chọn và đánh đổi là gì?** Việc nào phải hoãn, bỏ, chia nhỏ hoặc chuyển hướng?
6. **Cần ghi gì để người đến sau hiểu được?** Lý do, ngày, trạng thái, liên kết PBI, quyết định bị thay thế?
7. **Hành vi và kiểm thử thay đổi thế nào?** Acceptance criteria, Definition of Done và rủi ro hồi quy đã được xét chưa?
8. **Khi nào xem lại kết quả?** Dữ liệu nào xác nhận thay đổi tạo giá trị; tín hiệu nào buộc phải dừng hoặc điều chỉnh?

Nếu không biết mục tiêu của yêu cầu, hãy làm rõ trước khi đầu tư lớn. Nếu có sự cố nghiêm trọng, vẫn hành động khẩn cấp theo trách nhiệm nhưng ghi lại lý do, rủi ro và hậu kiểm ở mức phù hợp.

## 13. Bài tập vận dụng

### Bài tập 1 — Phân loại yêu cầu giữa Sprint

Nhóm đang có Sprint Goal “Người mới có thể đăng ký và xác thực tài khoản thành công”. Có ba yêu cầu:

1. Phát hiện một số liên kết xác thực có thể bị dùng lại trái với chính sách an toàn.
2. Bộ phận marketing muốn đổi màu biểu tượng trên trang chủ.
3. Khách hàng đề xuất thêm đăng nhập bằng mạng xã hội nhưng chưa có thông tin về số người bị ảnh hưởng.

**Yêu cầu:** phân loại mức cần phản ứng, xác định ai cần tham gia quyết định, nêu ảnh hưởng lên Sprint Goal và chọn nơi ghi lại kết quả.

**Gợi ý:** (1) có thể cần ưu tiên xử lý ngay theo mức rủi ro và chính sách; (2) thường vào backlog để sắp xếp sau nếu không có ràng buộc khác; (3) trước tiên làm rõ vấn đề và bằng chứng, rồi mới quyết định ưu tiên.

### Bài tập 2 — Vẽ dấu vết từ mục tiêu tới kiểm chứng

Một hệ thống đặt vé có Product Goal là “Giảm số giao dịch đặt vé không hoàn thành”. Người dùng báo giá vé thay đổi sau khi nhập thông tin thanh toán. Nhóm quyết định hiển thị rõ giá cuối và yêu cầu xác nhận trước bước trả tiền.

**Yêu cầu:** lập chuỗi liên kết gồm:

- Product Goal và tín hiệu ban đầu.
- Quyết định, lý do và một phương án đã cân nhắc nhưng chưa chọn.
- Một user story và ít nhất ba acceptance criteria.
- Kiểm thử liên quan và dữ liệu sau phát hành cần xem.

**Gợi ý:** cần nêu cách xử lý khi giá thay đổi hoặc nguồn giá không khả dụng; không xác nhận thanh toán bằng mức giá mà người dùng chưa chấp thuận.

### Bài tập 3 — Viết bản ghi quyết định có thể được thay thế

Giả sử nhóm đang dùng email xác thực và có đề xuất thay bằng mã OTP SMS. Hãy viết bản ghi quyết định tối đa 200 từ gồm: bối cảnh, mục tiêu, phương án, rủi ro an toàn và chi phí, người quyết định, lý do, tiêu chí kiểm chứng và điều kiện xem lại.

Sau một tháng, giả sử bằng chứng mới cho thấy SMS không phù hợp với một nhóm người dùng. Hãy bổ sung **một bản quyết định mới có liên kết về bản cũ**, tránh xóa lý do lịch sử.

### Bài tập 4 — Phát hiện quy trình quá nặng

Nhóm áp dụng yêu cầu mọi thay đổi câu chữ trên giao diện phải có biên bản năm trang và ba cấp phê duyệt. Nhiều lỗi thông báo đơn giản phải chờ hơn một tuần; nhưng những thay đổi bảo mật lớn lại không có liên kết tới kiểm thử.

**Yêu cầu:** đề xuất chính sách ghi dấu vết **theo rủi ro**, phân biệt sửa nhỏ, đổi nghiệp vụ và thay đổi an toàn. Nêu hai số liệu để kiểm tra chính sách mới có hiệu quả hay không.

**Gợi ý:** việc nhỏ có thể dùng issue/PR; việc ảnh hưởng cao cần record và bằng chứng; đo thời gian chờ quyết định cùng lỗi hoặc việc làm lại.

### Bài tập 5 — Tự kiểm tra một thay đổi thực tế

Chọn một yêu cầu từng đổi trong dự án của bạn và điền mẫu:

~~~text
Yêu cầu ban đầu:
Product Goal / vấn đề người dùng:
Thông tin mới khiến cần xem lại:
Phần đã biết / phần còn giả định:
Các phương án đã cân nhắc:
Quyết định và người chịu trách nhiệm:
Lý do, đánh đổi, việc bị dời/bỏ:
PBI và acceptance criteria bị ảnh hưởng:
Kiểm thử/tài liệu/phát hành cần cập nhật:
Bằng chứng sau thay đổi cần quan sát:
Thời điểm và điều kiện xem lại quyết định:
~~~

**Tiêu chí tự đánh giá:** một thành viên chưa tham dự cuộc họp ban đầu có thể dùng dấu vết này để giải thích **vì sao yêu cầu đổi, cái gì đang đúng, và phải kiểm chứng kết quả ra sao** hay chưa?

## 14. Tổng kết

Agile không quản lý thay đổi bằng cách phủ nhận kế hoạch, cũng không giữ kế hoạch nguyên vẹn bất chấp phản hồi. Một nhóm làm việc thích ứng cần **đường đi rõ từ mục tiêu tới quyết định và từ quyết định tới kết quả**.

Hãy nhớ:

- **Tách phản hồi khỏi yêu cầu đã được chọn:** nghe người dùng, làm rõ vấn đề, kiểm tra bằng chứng và cân nhắc phương án.
- **Giữ mục tiêu làm điểm tựa:** Product Goal và Sprint Goal giúp biết khi nào cần đổi phạm vi và khi nào cần bảo vệ sự tập trung.
- **Ghi lý do và đánh đổi ở mức vừa đủ:** quyết định, người chịu trách nhiệm, liên kết và thời điểm đánh giá lại quan trọng hơn số trang tài liệu.
- **Đồng bộ hành vi với tiêu chí và kiểm thử:** thay đổi phải đi qua acceptance criteria, Definition of Done và kiểm chứng phù hợp.
- **Làm lộ chi phí của việc chen ngang:** Kanban và các chỉ số dòng công việc giúp nhóm thấy tác động lên WIP, thời gian chờ và khả năng hoàn tất việc.
- **Dùng kỹ thuật XP để đổi hướng an toàn:** CI, kiểm thử, refactoring và cộng tác kỹ thuật giảm rủi ro hồi quy.
- **Khép vòng phản hồi:** quan sát outcome sau phát hành, giữ lịch sử và sẵn sàng thay thế quyết định cũ khi có bằng chứng tốt hơn.

> **Câu hỏi ghi nhớ:** “Nếu sáu tháng sau có người hỏi vì sao nhóm chọn cách này thay vì cách khác, họ có thể tìm được mục tiêu, bằng chứng, người quyết định, thay đổi đã thực hiện và kết quả để tự đánh giá hay không?”

### Tài liệu tham khảo

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giá trị phản hồi trước thay đổi, hợp tác, giao phần mềm tăng dần và cải tiến liên tục.
- [The Scrum Guide](https://scrumguides.org/scrum-guide.html) — Product Goal, Product Backlog, Sprint Goal, Sprint Backlog, kiểm tra/thích ứng, Definition of Done và trách nhiệm trong Scrum.
- [The Kanban Guide](https://kanbanguides.org/) — định nghĩa workflow, chính sách luồng, WIP và các phép đo theo dõi công việc.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — thực hành kỹ thuật giảm chi phí thay đổi và tăng phản hồi sớm.
