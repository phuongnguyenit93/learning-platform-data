# Thường xuyên nhìn lại và điều chỉnh cách làm

## 1. Nguyên tắc Agile thứ 12: nhìn lại để thay đổi hành vi

Nguyên tắc thứ 12 của Agile đề cập đến việc **định kỳ cùng nhau suy ngẫm cách làm việc để hiệu quả hơn, sau đó điều chỉnh hành vi cho phù hợp**. Điểm quan trọng nằm ở cả hai vế:

1. **Nhìn lại (reflect):** Nhóm xem xét điều đã xảy ra, kết quả đạt được, khó khăn, nguyên nhân và những điều vừa học được.
2. **Điều chỉnh (tune and adjust):** Nhóm chọn thay đổi cụ thể, áp dụng trong công việc tiếp theo và kiểm tra thay đổi đó có giúp ích không.

Nếu chỉ họp tổng kết nhưng không làm gì khác đi, nhóm chưa thực hiện trọn vẹn nguyên tắc này. Ngược lại, nếu liên tục thay đổi quy trình dựa trên cảm tính mà không quan sát kết quả, nhóm dễ tạo ra xáo trộn và khó biết biện pháp nào thực sự hiệu quả.

Nguyên tắc này phù hợp với mục tiêu của module **AGILE_DEVELOPMENT**: phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. User story, product backlog, Scrum, Kanban, Extreme Programming (XP) hay các chỉ số dòng công việc đều có thể cung cấp thông tin để nhóm đưa ra quyết định cải tiến. Tuy nhiên, **không một framework hay chỉ số nào tự động thay thế được việc cùng học hỏi và thay đổi cách làm**.

### Vì sao cần “thường xuyên”?

Công việc phát triển phần mềm chứa nhiều điều chưa biết: yêu cầu thay đổi, độ khó kỹ thuật chỉ lộ ra khi triển khai, sự phụ thuộc giữa thành viên, phản hồi từ người dùng và sự cố khi tích hợp. Nếu chỉ đánh giá sau nhiều tháng, nhóm có thể lặp lại cùng một vấn đề qua nhiều đợt bàn giao.

Nhìn lại theo nhịp phù hợp giúp:

- **Phát hiện vấn đề sớm:** một bước bàn giao thường chậm, nhiều công việc bị chặn hoặc yêu cầu liên tục phải làm rõ.
- **Giữ lại thực hành tốt:** biết vì sao một thay đổi nhỏ đã giúp giảm lỗi hoặc cải thiện giao tiếp.
- **Điều chỉnh theo bối cảnh:** cách phối hợp tốt ở nhóm ba người có thể không còn phù hợp khi nhóm mở rộng hoặc làm việc phân tán.
- **Trao quyền cải tiến:** người trực tiếp thực hiện công việc có cơ hội nêu vấn đề và đề xuất thay đổi.
- **Tăng khả năng thích ứng:** nhóm không chờ một cuộc cải tổ lớn mới sửa cách làm.

“Thường xuyên” không bắt buộc đồng nghĩa với “ngày nào cũng họp hồi tưởng”. Nhóm cần một nhịp đủ ngắn để học kịp thời nhưng đủ dài để quan sát tác động của thay đổi. Trong Scrum, Sprint Retrospective tạo ra một nhịp rõ ràng; với Kanban, nhóm có thể xem lại luồng công việc theo lịch phù hợp với dịch vụ và tốc độ giao hàng.

## 2. Nhìn lại điều gì?

Cải tiến không nên chỉ xoay quanh câu hỏi “Ai làm chậm?”. Một nhóm hiệu quả xem xét **hệ thống làm việc**: mục tiêu, luồng công việc, phối hợp, thực hành kỹ thuật, chất lượng và khả năng nhận phản hồi.

| Khía cạnh | Câu hỏi cần nhìn lại | Ví dụ bằng chứng |
| --- | --- | --- |
| **Giá trị sản phẩm** | Phần đã giao có giúp người dùng làm việc tốt hơn không? | Tỷ lệ hoàn tất tác vụ, phản hồi sử dụng, mức sử dụng tính năng |
| **Làm rõ yêu cầu** | User story và tiêu chí chấp nhận có đủ rõ khi bắt đầu? | Câu hỏi nghiệp vụ bị chờ, số lần phải làm lại do hiểu sai |
| **Product backlog** | Công việc được ưu tiên và chia nhỏ hợp lý chưa? | Hạng mục tồn lâu, việc quá lớn, hạng mục đổi ưu tiên liên tục |
| **Dòng công việc** | Công việc chậm ở bước nào, có quá nhiều việc đang làm không? | Work in Progress (WIP), cycle time, tuổi công việc, thời gian bị chặn |
| **Chất lượng kỹ thuật** | Điều gì làm lỗi lọt qua hoặc tích hợp khó khăn? | Lỗi sau phát hành, kết quả kiểm thử, sự cố CI, nợ kỹ thuật |
| **Cộng tác** | Việc trao đổi và ra quyết định có thông suốt? | Thời gian chờ review, chờ phản hồi, phụ thuộc giữa nhóm |
| **Khả năng duy trì nhịp độ** | Cách làm hiện tại có bền vững đối với con người? | Làm thêm kéo dài, việc gián đoạn, phản hồi về tải công việc |

Ví dụ, khi Sprint thường xuyên không đạt mục tiêu, nhóm có thể phát hiện câu chuyện thực tế không phải “lập trình viên ước lượng kém”, mà là:

- Product Backlog Item quá lớn, chỉ tích hợp được vào cuối Sprint.
- Tiêu chí chấp nhận chỉ được làm rõ sau khi đã viết mã.
- Công việc đang thực hiện quá nhiều, mọi người liên tục chuyển ngữ cảnh.
- Phản hồi của người có thẩm quyền đến muộn.
- Kiểm thử hồi quy thủ công khiến thời gian hoàn tất khó dự đoán.

Nhìn vào quy trình và điều kiện làm việc giúp nhóm nhận diện **điểm có thể cải thiện**, thay vì quy lỗi mặc định cho một cá nhân.

## 3. Chu trình cải tiến liên tục

Một vòng nhìn lại có thể diễn đạt thành **quan sát → hiểu → chọn thay đổi → thử → đo → điều chỉnh**.

~~~mermaid
flowchart TD
    A["Quan sát công việc và kết quả thực tế"]
    B["Cùng nhìn lại điều tốt, điều chưa tốt"]
    C["Tìm nguyên nhân và chọn vấn đề ưu tiên"]
    D["Đề xuất một cải tiến nhỏ có thể thử"]
    E["Áp dụng trong một khoảng thời gian rõ ràng"]
    F["Kiểm tra tác động và rút kinh nghiệm"]
    A --> B --> C --> D --> E --> F
    F -->|"Tiếp tục, sửa hoặc dừng thử nghiệm"| A
~~~

### Bước 1: Thu thập dữ liệu và tình huống cụ thể

Nên kết hợp **dữ liệu định lượng** (thời gian chờ review, số công việc còn dang dở, lỗi sau phát hành) và **quan sát định tính** (một tình huống giao tiếp bị hiểu nhầm, trải nghiệm của thành viên, phản hồi người dùng).

Đừng bắt đầu bằng kết luận “nhóm thiếu kỷ luật” nếu chưa chỉ ra được điều gì đã xảy ra. Ví dụ quan sát cụ thể hơn là: “Trong sáu hạng mục hoàn thành muộn của đợt vừa rồi, bốn hạng mục chờ làm rõ tiêu chí chấp nhận hơn một ngày”.

### Bước 2: Tạo không gian để mọi người cùng nói

Mọi thành viên liên quan cần cơ hội mô tả sự việc và đưa góc nhìn của mình. Người điều phối nên tách **sự kiện** khỏi **suy đoán**, hạn chế việc một người có tiếng nói lớn áp đặt cách giải thích.

Một cuộc nhìn lại chỉ hữu ích khi mọi người đủ an toàn để nói về sai sót và khó khăn mà không sợ bị làm nhục hoặc trừng phạt vì đã lên tiếng. Điều này không loại bỏ trách nhiệm cá nhân; nó giúp tìm và xử lý nguyên nhân hiệu quả hơn.

### Bước 3: Tìm nguyên nhân có thể tác động

Đi từ triệu chứng đến cơ chế gây ra vấn đề. Ví dụ: “Kiểm thử luôn dồn cuối đợt” có thể liên quan tới user story quá lớn, thiếu dữ liệu kiểm thử, hệ thống CI không ổn định hoặc giới hạn về môi trường. **Không giả định nguyên nhân đầu tiên được nêu ra là đúng**.

Các kỹ thuật như “5 Whys” giúp đào sâu vấn đề, nhưng cần đối chiếu bằng chứng và chấp nhận có **nhiều nguyên nhân đồng thời**. Một chuỗi hỏi “tại sao” quá đơn giản có thể che khuất nguyên nhân hệ thống.

### Bước 4: Chọn một thay đổi đủ nhỏ

Thay vì kết luận “cần giao tiếp tốt hơn”, hãy thử một hành động có thể quan sát:

> “Trong hai tuần tới, mỗi user story được đưa vào trạng thái đang làm cần có ví dụ về trường hợp thành công và thất bại; nếu còn câu hỏi nghiệp vụ quan trọng, nhóm sẽ làm rõ trước khi bắt đầu phần phụ thuộc vào câu trả lời.”

Thay đổi tốt có **đối tượng áp dụng, người thúc đẩy, thời gian thử và dấu hiệu kiểm chứng**. Nếu vấn đề nằm ngoài quyền xử lý của nhóm, cần ghi rõ ai có thể giúp gỡ vướng và cách chuyển vấn đề tới họ.

### Bước 5: Thử trong công việc thật

Đưa hành động vào bảng công việc hoặc nơi nhóm vẫn theo dõi nhiệm vụ; nhắc lại vào thời điểm phù hợp. Quan sát tác động trong quá trình làm, không đợi đến cuộc hồi tưởng tiếp theo mới nhớ rằng nhóm đã thống nhất thay đổi gì.

### Bước 6: Đánh giá và quyết định

Ở lần nhìn lại tiếp theo, hỏi: **“Chúng ta đã thực sự thử chưa? Kết quả nào thay đổi? Bằng chứng đủ thuyết phục chưa? Có tác dụng phụ nào?”**

Sau đó quyết định **tiếp tục**, **điều chỉnh** hoặc **dừng** thử nghiệm. Nếu thay đổi chưa được thực hiện, không thể kết luận nó vô hiệu; cần xem điều gì ngăn việc áp dụng.

## 4. Ví dụ thực tế: cải thiện luồng hoàn thành user story

Một nhóm xây dựng nền tảng học trực tuyến gồm người phát triển, người kiểm thử và Product Owner. Nhóm thường khởi động nhiều user story cùng lúc nhưng gần cuối Sprint vẫn còn nhiều việc chờ kiểm thử. Một số hạng mục được báo “code xong” song chưa đáp ứng Definition of Done.

### Trước khi nhìn lại

Ở một Sprint kéo dài hai tuần, nhóm thấy:

- Mở cùng lúc tám user story nhưng chỉ bốn story đáp ứng Definition of Done vào cuối Sprint.
- Nhiều pull request chờ phản hồi đến ngày cuối.
- Kiểm thử bắt đầu muộn vì tính năng được tích hợp theo từng khối lớn.
- Nhóm khó đánh giá tiến độ khi mỗi thành viên đều có rất nhiều việc “đang làm”.

Đó là **dữ liệu của ví dụ giả định**, không phải ngưỡng đánh giá chung cho mọi nhóm. Nhóm cần kiểm tra bối cảnh và định nghĩa “hoàn thành” nhất quán.

### Trong buổi nhìn lại

Nhóm đặt câu hỏi: “Điều gì khiến công việc dồn về cuối?” và lập sơ đồ:

~~~text
User story lớn
    ↓
Phát triển nhiều ngày mới có phiên bản tích hợp
    ↓
Pull request lớn và khó review
    ↓
Kiểm thử bắt đầu muộn
    ↓
Phát hiện lỗi lúc gần hết Sprint
    ↓
Nhiều việc dở dang, khó hoàn tất đúng hạn
~~~

Sau khi đối chiếu một số hạng mục, nhóm đồng ý thử **hai thay đổi nhỏ** trong Sprint tiếp theo:

1. Chia user story thành các lát cắt dọc có thể kiểm thử và tích hợp, thay vì tách riêng toàn bộ giao diện, API và cơ sở dữ liệu thành những phần không sử dụng được.
2. Hạn chế mở công việc mới khi đã có quá nhiều hạng mục đang phát triển hoặc chờ review; ưu tiên cùng hoàn tất việc gần xong.

Nhóm gắn người phụ trách thúc đẩy từng thử nghiệm và cùng thống nhất cách quan sát: số hạng mục đang làm, thời gian chờ review, tỷ lệ hạng mục đáp ứng Definition of Done và việc có phải làm thêm cuối Sprint hay không.

### Ở lần nhìn lại sau

Nếu số hạng mục tồn cuối Sprint giảm và không xuất hiện dấu hiệu giảm chất lượng, nhóm có cơ sở tiếp tục thực hành mới. Nếu thời gian review vẫn dài dù pull request đã nhỏ, cần xem thêm lịch làm việc, quy tắc phân công reviewer hoặc độ phức tạp kỹ thuật.

**Bài học:** Cải tiến được xác nhận bằng thay đổi của cách làm và kết quả, không bằng số lượng ý kiến hay hành động được liệt kê trong biên bản.

## 5. Tổ chức một buổi nhìn lại hiệu quả

Buổi nhìn lại, thường gọi là *retrospective*, là một cách thực hành nguyên tắc 12. Nó không nhất thiết phải trang trọng, nhưng nên có cấu trúc giúp mọi người đi đến hành động.

### Một chương trình mẫu trong 50 phút

| Thời lượng gợi ý | Hoạt động | Đầu ra mong muốn |
| --- | --- | --- |
| 5 phút | Nhắc mục tiêu, nguyên tắc trao đổi và hành động cải tiến kỳ trước | Cùng hiểu buổi họp nhằm học hỏi và thay đổi |
| 10 phút | Mỗi người ghi điều tốt, khó khăn và dữ liệu quan sát | Có đủ góc nhìn trước khi thảo luận |
| 15 phút | Gom nhóm, làm rõ tình huống, chọn vấn đề ưu tiên và tìm nguyên nhân | Nhóm đồng ý vấn đề đáng xử lý nhất |
| 10 phút | Đề xuất phương án, chọn một hoặc hai thử nghiệm khả thi | Hành động cụ thể với người thúc đẩy và hạn thử |
| 10 phút | Thống nhất cách theo dõi, tiêu chí kiểm chứng và cách chia sẻ kết quả | Biết khi nào, bằng gì sẽ đánh giá hiệu quả |

Đây là **ví dụ bố trí thời gian**, không phải khuôn mẫu bắt buộc. Với nhóm lớn hoặc vấn đề phức tạp, có thể cần thời gian khác; một số vấn đề nhạy cảm nên được trao đổi trước qua kênh phù hợp để tránh gây áp lực công khai.

### Quy tắc giúp thảo luận an toàn và thực chất

- **Nói về sự kiện và tác động:** “Ba pull request chờ review hơn hai ngày” hữu ích hơn “Ai đó không hỗ trợ đồng đội”.
- **Giả định mọi người đã hành động trong giới hạn thông tin và điều kiện họ có:** sau đó kiểm tra điều kiện nào cần thay đổi.
- **Cho mọi người thời gian suy nghĩ độc lập:** có thể viết ý kiến trước khi thảo luận để hạn chế việc nhóm đi theo người lên tiếng đầu tiên.
- **Cho phép bất đồng có căn cứ:** tìm sự hiểu biết chung, không cần ép đồng thuận giả tạo.
- **Tôn trọng điều cần bảo mật:** vấn đề nhân sự nhạy cảm hoặc thông tin khách hàng không nhất thiết phải công khai trên bảng retrospective.
- **Theo dõi điều đã thống nhất:** đầu buổi sau quay lại xem tiến độ cải tiến của buổi trước.

Người điều phối có thể là Scrum Master, một thành viên nhóm hoặc người phù hợp khác. Điều quan trọng là họ giúp duy trì cuộc trao đổi cân bằng và hướng vào hành động, không dùng buổi họp để đánh giá thành tích cá nhân.

## 6. Những kỹ thuật nhìn lại có thể sử dụng

Các kỹ thuật sau là **công cụ tổ chức thảo luận**, không phải yêu cầu bắt buộc của Agile. Chọn kỹ thuật phù hợp với vấn đề và mức độ trưởng thành của nhóm.

| Kỹ thuật | Cách thực hiện ngắn gọn | Khi nào hữu ích |
| --- | --- | --- |
| **Start – Stop – Continue** | Liệt kê việc nên bắt đầu, dừng và tiếp tục | Nhóm mới làm retrospective, muốn đi đến hành động nhanh |
| **4Ls: Liked, Learned, Lacked, Longed for** | Ghi điều thích, điều học được, điều thiếu, điều mong có | Muốn nhận diện cả học hỏi và nhu cầu hỗ trợ |
| **Timeline** | Đặt sự kiện quan trọng theo thời gian, so sánh góc nhìn | Đợt làm việc có nhiều thay đổi hoặc sự cố khó nhớ |
| **5 Whys** | Hỏi nhiều lần vì sao hiện tượng xảy ra, kiểm chứng từng giả thuyết | Có một vấn đề nổi bật cần đào sâu |
| **Sơ đồ luồng công việc** | Vẽ từ yêu cầu đến bàn giao, đánh dấu nơi chờ đợi | Lead time dài, công việc bị tắc hoặc nhiều lần bàn giao |
| **Health check / khảo sát nhóm** | Thành viên đánh giá cảm nhận về mục tiêu, tập trung, phối hợp, học hỏi | Muốn theo dõi tình trạng nhóm qua thời gian |

Ví dụ với **Start – Stop – Continue**:

| Start — Bắt đầu | Stop — Dừng | Continue — Tiếp tục |
| --- | --- | --- |
| Thêm ví dụ kiểm thử vào user story trước khi bắt đầu | Mở thêm hạng mục mới khi bảng đang nghẽn ở bước review | Tích hợp mã hằng ngày và trao đổi sớm khi có trở ngại |

Sau khi thu thập ý kiến, nhóm **phải ưu tiên**: không phải mọi dòng trong ba cột đều trở thành hành động. Nên chọn ít thay đổi nhưng thực hiện đến nơi đến chốn.

## 7. Viết hành động cải tiến sao cho có thể kiểm chứng

Một biên bản retrospective dễ thất bại nếu chỉ viết “cải thiện giao tiếp”, “review nhanh hơn” hoặc “nâng cao chất lượng”. Những câu này mô tả mong muốn, chưa nói nhóm sẽ làm gì khác.

Hãy dùng mẫu:

> **Vấn đề quan sát được → thay đổi sẽ thử → người thúc đẩy → thời gian áp dụng → tín hiệu đánh giá → ngày xem lại.**

Ví dụ:

| Thành phần | Nội dung |
| --- | --- |
| Vấn đề | Nhiều user story bị chặn vì câu hỏi về quy tắc nghiệp vụ chưa được giải đáp |
| Giả thuyết | Làm rõ trường hợp ngoại lệ trước khi bắt đầu sẽ giảm chờ đợi khi triển khai |
| Thử nghiệm | Trước khi đưa story vào làm, người phát triển và đại diện nghiệp vụ cùng xem ví dụ đầu vào, kết quả kỳ vọng và trường hợp lỗi |
| Người thúc đẩy | Một thành viên được nhóm đồng ý theo dõi việc tổ chức trao đổi; các thành viên liên quan cùng thực hiện |
| Thời gian | Thử trong hai tuần tiếp theo |
| Tín hiệu | Số story bị chặn vì câu hỏi nghiệp vụ, thời gian chờ làm rõ, số lần phải làm lại do hiểu sai |
| Xem lại | Retrospective tiếp theo: tiếp tục, chỉnh sửa hay dừng thử nghiệm |

Không nhất thiết áp dụng cứng một mẫu hành động cho mọi vấn đề. Nhưng ít nhất nhóm cần trả lời được: **“Tuần tới ai sẽ làm gì khác, và làm sao biết việc đó có ích?”**

### Đưa việc cải tiến vào công việc hằng ngày

Tùy cách quản lý, nhóm có thể ghi hành động vào bảng Kanban, Sprint Backlog, danh sách hành động nhóm hoặc một khu vực cải tiến riêng. Nếu hành động tiêu tốn công sức đáng kể, hãy làm rõ năng lực cần dành cho nó khi lập kế hoạch; nếu không, cải tiến thường bị công việc tính năng đẩy xuống cuối danh sách.

Đôi khi hành động thuộc phạm vi kỹ thuật: tăng độ tin cậy của pipeline CI, bổ sung kiểm thử tự động cho luồng thường lỗi, hoặc điều chỉnh quy tắc review. Đôi khi đó là thay đổi tổ chức: cần người quyết định rõ hơn hoặc giảm phụ thuộc vào nhóm khác. **Chọn giải pháp dựa trên nguyên nhân**, không cố biến mọi vấn đề thành một cuộc họp mới.

## 8. Đo kết quả cải tiến mà không biến chỉ số thành mục tiêu sai

Chỉ số giúp nhóm kiểm chứng giả thuyết, nhưng chúng có giới hạn. Cần thống nhất định nghĩa, khoảng thời gian và bối cảnh trước khi so sánh.

| Chỉ số hoặc tín hiệu | Diễn giải | Lưu ý khi sử dụng |
| --- | --- | --- |
| **Cycle time** | Thời gian từ khi bắt đầu thực hiện một hạng mục đến khi hoàn tất theo ranh giới quy trình đã định | Giữ nhất quán điểm bắt đầu/kết thúc; xem phân bố, không chỉ số trung bình |
| **Lead time** | Thời gian từ khi ghi nhận yêu cầu theo điểm bắt đầu đã thống nhất đến khi đáp ứng hoặc bàn giao | Phải nêu rõ điểm mốc vì các tổ chức định nghĩa khác nhau |
| **Work in Progress (WIP)** | Số hạng mục đang nằm trong các trạng thái thực hiện | WIP cao có thể liên quan đến nhiều chuyển ngữ cảnh và thời gian hoàn tất dài |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian | Cần để ý kích thước hạng mục; không dùng để xếp hạng thành tích cá nhân |
| **Thời gian bị chặn** | Hạng mục chờ quyết định, quyền truy cập, môi trường, review hoặc phụ thuộc | Giúp nhận diện nút nghẽn ngoài công việc lập trình |
| **Lỗi sau phát hành** | Lỗi được phát hiện sau khi tính năng đến môi trường hoặc người dùng đã định nghĩa | Đọc cùng mức độ nghiêm trọng và thay đổi quy mô phát hành |
| **Tỷ lệ hoàn tất tác vụ người dùng** | Người dùng có đạt được mục đích trên phần đã giao? | Cần kịch bản và cách đo nhất quán |
| **Phản hồi từ thành viên** | Mức rõ ràng mục tiêu, tải công việc, khả năng được hỗ trợ | Không nên xem một khảo sát cảm nhận đơn lẻ là kết luận đầy đủ |

Ví dụ, sau khi giới hạn WIP, nhóm thấy cycle time giảm. Đây là tín hiệu đáng mừng, nhưng cần xem có sự thay đổi khác đồng thời không: hạng mục nhỏ hơn, ít sự cố hơn, số thành viên khác đi hoặc quy tắc tính “Done” đã đổi. **Tương quan chưa đủ chứng minh nguyên nhân**; một thử nghiệm nhỏ, có quan sát trước/sau và ghi rõ bối cảnh sẽ giúp nhóm học đáng tin cậy hơn.

Các số liệu dùng để cải thiện hệ thống làm việc không nên trở thành công cụ gây áp lực cá nhân. Khi người ta bị thưởng/phạt chỉ theo số story đóng hoặc velocity, họ có động lực chia việc giả tạo, tránh việc khó hoặc giảm chất lượng, làm chỉ số đẹp nhưng kết quả sản phẩm xấu hơn.

## 9. Áp dụng nguyên tắc trong Scrum, Kanban và XP

### Scrum: Sprint Retrospective

Trong Scrum, **Sprint Retrospective** là sự kiện để Scrum Team lập kế hoạch tăng chất lượng và hiệu quả. Nhóm xem Sprint vừa qua về con người, tương tác, quy trình, công cụ và **Definition of Done**; nhận diện điều đã tốt, những vấn đề gặp phải và phương án cải thiện. Những cải tiến có tác động lớn có thể được triển khai sớm nhất có thể, thậm chí đưa vào Sprint Backlog của Sprint tiếp theo.

Cần phân biệt với hai hoạt động dễ bị nhầm:

| Hoạt động | Câu hỏi trung tâm | Trọng tâm |
| --- | --- | --- |
| **Sprint Review** | Sản phẩm tạo ra giá trị gì, môi trường và ưu tiên đã thay đổi thế nào? | Kiểm tra kết quả sản phẩm, trao đổi với các bên liên quan, điều chỉnh hướng đi |
| **Sprint Retrospective** | Scrum Team có thể cải thiện cách làm việc thế nào? | Kiểm tra và điều chỉnh quy trình, tương tác, chất lượng, hiệu quả làm việc |
| **Daily Scrum** | Tiến độ đến Sprint Goal ra sao, cần điều chỉnh kế hoạch ngắn hạn thế nào? | Kiểm tra tiến độ để thích ứng hằng ngày, không thay thế retrospective |

Ví dụ, tại Sprint Review, khách hàng chỉ ra người học khó tìm khóa phù hợp. Đây là phản hồi về **sản phẩm**. Tại Sprint Retrospective, Scrum Team nhận thấy phản hồi thử nghiệm thường đến quá muộn do chỉ cho người học xem vào cuối Sprint. Nhóm thống nhất thử kiểm tra bản mẫu sớm hơn. Đây là cải tiến **cách làm** giúp nhận phản hồi sản phẩm tốt hơn.

### Kanban: cải thiện dòng chảy dựa trên quan sát

Kanban không yêu cầu mọi đội phải tổ chức Sprint. Nhóm có thể cải tiến liên tục qua việc xem bảng công việc, chính sách luồng, các hạng mục bị chặn và các cuộc đánh giá theo nhịp phù hợp.

Ví dụ, khi nhận ra cột “Đang review” luôn có nhiều hạng mục, nhóm xem lại chính sách WIP, cách phân phối người review, độ lớn pull request và thời gian chờ. Nhóm thử giới hạn thêm công việc mới khi review đang nghẽn, rồi quan sát cycle time và chất lượng. Mục tiêu là cải thiện luồng công việc **dựa trên bằng chứng của hệ thống**, không chỉ “làm mọi người bận hơn”.

### Extreme Programming (XP): cải thiện cả thực hành kỹ thuật

XP chú trọng phản hồi nhanh, chất lượng và khả năng thay đổi an toàn. Các thực hành như lập trình cặp, phát triển hướng kiểm thử, tích hợp liên tục, tái cấu trúc mã và giao bản nhỏ có thể trở thành **đối tượng được đánh giá và điều chỉnh** khi nhóm quan sát thấy vấn đề.

Chẳng hạn, nếu lỗi hồi quy xuất hiện sau mỗi lần tích hợp, nhóm có thể thử bổ sung kiểm thử tự động cho những luồng quan trọng, rút ngắn thời gian từ lúc thay đổi mã đến lúc có kết quả CI và đánh giá lại sau một số đợt giao hàng.

**Điểm chung:** Dù nhóm dùng Scrum, Kanban, XP hay phối hợp các thực hành, nguyên tắc thứ 12 vẫn là duy trì vòng học hỏi thực tế rồi chuyển thành cải tiến có thể kiểm chứng. Không cần đổi tên cuộc họp cho “đúng Agile” nếu cách làm hiện tại đã đáp ứng được mục tiêu đó.

## 10. Khi nhóm phân tán hoặc làm việc với nhiều nhóm khác

Nhóm làm việc từ xa có thể thu thập ý kiến bất đồng bộ trước buổi họp, dùng bảng trực tuyến để mọi người cùng thấy dữ liệu, rồi thảo luận có thời hạn. Điều phối viên cần chú ý sự khác biệt múi giờ, khả năng phát biểu và ngôn ngữ, tránh coi sự im lặng là đồng thuận.

Với nhiều nhóm cùng phát triển một sản phẩm, có những vấn đề **nằm ngoài phạm vi một nhóm**, như môi trường kiểm thử chung, phụ thuộc tích hợp hoặc quy trình phê duyệt phát hành. Một retrospective cấp nhóm vẫn có thể mô tả bằng chứng và đề xuất cải tiến, nhưng cần chỉ rõ ai có quyền giải quyết và cách phối hợp liên nhóm.

Không nên đưa mọi vấn đề lên lãnh đạo hoặc mở một cuộc họp mới. Ưu tiên xử lý ở cấp có thể tác động trực tiếp, chỉ chuyển cấp những trở ngại thực sự vượt quyền quyết định hoặc nguồn lực của nhóm.

## 11. Những sai lầm thường gặp

**1. Họp hồi tưởng đều đặn nhưng không thực hiện hành động.** Mỗi lần họp lại nghe những vấn đề giống nhau. Cách khắc phục là mở đầu bằng việc xem lại hành động kỳ trước, giới hạn số cải tiến mới và chọn tín hiệu kiểm chứng rõ.

**2. Biến retrospective thành buổi đổ lỗi.** Tập trung vào “ai gây lỗi” làm thành viên che giấu vấn đề và hạn chế học hỏi. Nên xem điều kiện quy trình, thông tin và kỹ thuật đã góp phần gây lỗi thế nào; trách nhiệm cụ thể vẫn có thể được xử lý qua kênh phù hợp.

**3. Liệt kê quá nhiều hành động.** Danh sách dài khiến không hành động nào có đủ thời gian hoặc người thúc đẩy. Chọn một hoặc hai cải tiến có giá trị cao và khả thi trong đợt tiếp theo.

**4. Chọn giải pháp trước khi hiểu nguyên nhân.** Ví dụ mọi khó khăn giao tiếp đều dẫn tới quyết định “họp hằng ngày thêm 30 phút”. Nếu nguyên nhân thật là thiếu người ra quyết định, nhiều cuộc họp hơn có thể chỉ làm gián đoạn công việc.

**5. Chỉ đo hoạt động, không đo kết quả.** Số buổi họp, số đề xuất hoặc số action được ghi không bảo đảm lead time giảm hay chất lượng cải thiện. Đo thay đổi ở vấn đề ban đầu và xem cả tác dụng phụ.

**6. Chỉ nhận xét điều tiêu cực.** Nếu nhóm không nhận diện điều đang hoạt động tốt, họ có thể vô tình bỏ đi thực hành hữu ích. Cần hỏi cả “điều gì giúp chúng ta thành công, nên giữ lại?”.

**7. Chờ đến cuối dự án mới nhìn lại.** Khi dự án kết thúc, nhiều cơ hội sửa lỗi đã mất. Thực hiện nhìn lại ở nhịp phù hợp và bổ sung khi có sự cố hoặc thay đổi lớn.

**8. Coi một công thức retrospective là bắt buộc.** Mỗi nhóm có bối cảnh khác nhau. Có thể đổi kỹ thuật, độ dài hoặc cách thu thập phản hồi, miễn là vẫn học và có điều chỉnh hành vi rõ ràng.

**9. Thay đổi mọi thứ quá nhanh.** Nếu nhóm liên tục thay WIP, cách chia story, lịch họp và tiêu chí Done trong cùng một tuần, khó xác định thay đổi nào hữu ích. Ưu tiên thử nghiệm nhỏ, quan sát đủ lâu và ghi rõ bối cảnh.

## 12. Bài tập tình huống

Một nhóm phát triển ứng dụng thương mại điện tử thường kết thúc Sprint với nhiều hạng mục “gần xong”. Trong ba Sprint gần đây, kiểm thử phát hiện lỗi tích hợp ở cuối Sprint. Thành viên nói rằng:

- Người phát triển đợi đến khi tính năng “đủ lớn” mới mở pull request.
- Người kiểm thử chỉ nhận bản có thể kiểm tra vào ngày áp chót.
- Một số câu hỏi về quy tắc giảm giá chưa có người quyết định kịp thời.
- Các buổi retrospective trước đều ghi “cần cải thiện giao tiếp”, nhưng chưa có thay đổi cụ thể.

**Câu hỏi 1:** Những quan sát trên gợi ý ít nhất ba nguyên nhân hoặc điểm nghẽn nào?  
**Câu hỏi 2:** Hãy đề xuất **một** thử nghiệm cải tiến thực hiện trong Sprint tiếp theo.  
**Câu hỏi 3:** Ai cần tham gia, cần quan sát tín hiệu gì và khi nào quyết định giữ hay điều chỉnh?  
**Câu hỏi 4:** Nhóm nên làm gì nếu nguyên nhân chính là thiếu người có quyền quyết định quy tắc giảm giá?

### Gợi ý lời giải

Có thể nhận diện ba nhóm vấn đề: **lô công việc quá lớn và tích hợp muộn**, **kiểm thử bắt đầu muộn**, **chờ quyết định nghiệp vụ**. Chúng có thể tác động lẫn nhau; cần xem dữ liệu thực tế để phân biệt nguyên nhân với hiện tượng.

Một phương án thử nghiệm:

> “Trong Sprint tới, chia các hạng mục thay đổi quy tắc giảm giá thành lát cắt có thể kiểm thử; mở pull request nhỏ và chạy kiểm thử tích hợp khi một lát cắt sẵn sàng, thay vì chờ đến cuối Sprint.”

Nhóm có thể giao một thành viên thúc đẩy việc chia nhỏ và một người phối hợp làm rõ yêu cầu với Product Owner hoặc đại diện nghiệp vụ. Tín hiệu quan sát gồm **thời gian chờ review, thời điểm có bản tích hợp để kiểm thử, số lỗi tích hợp phát hiện gần cuối Sprint** và việc các hạng mục có đáp ứng Definition of Done hay không.

Trong Sprint Retrospective tiếp theo, cả nhóm xem thử nghiệm có được thực hiện, kết quả thay đổi ra sao và có tác dụng phụ không. Nếu vấn đề chính là người có quyền quyết định không sẵn sàng, nhóm nên làm rõ cơ chế phản hồi và **chuyển trở ngại đúng nơi có thẩm quyền**; không thể giải quyết hoàn toàn bằng việc yêu cầu lập trình viên họp nhiều hơn.

### Tự luyện: biến nhận xét mơ hồ thành hành động

Hãy viết lại ba phát biểu sau dưới dạng thử nghiệm có người thúc đẩy, thời hạn và tín hiệu đánh giá:

1. “Chúng ta cần giao tiếp tốt hơn.”
2. “Review code phải nhanh hơn.”
3. “Cần giảm lỗi production.”

Ví dụ với câu 2: “Trong hai tuần tới, nhóm sẽ dành một khung thời gian review ngắn mỗi ngày làm việc và ưu tiên pull request đã chờ lâu; một thành viên ghi nhận thời gian chờ từ lúc yêu cầu review đến lúc có phản hồi đầu tiên. Retrospective tiếp theo kiểm tra xu hướng và quyết định duy trì hay điều chỉnh.” Đây chỉ là **giả thuyết thử nghiệm**, không phải quy định cố định rằng mọi nhóm phải có khung review mỗi ngày.

## 13. Kiểm tra nhanh trước khi kết thúc một lần nhìn lại

Hãy đối chiếu năm câu hỏi:

1. **Có bằng chứng cụ thể không?** Nhóm nhìn vào tình huống, kết quả hoặc dữ liệu nào?
2. **Đã hiểu nguyên nhân đến mức đủ hành động chưa?** Còn giả thuyết nào chưa kiểm chứng?
3. **Có thay đổi nhỏ, khả thi không?** Công việc tiếp theo sẽ khác trước ở điểm nào?
4. **Có người thúc đẩy và thời điểm xem lại không?** Ai giúp hành động không bị quên?
5. **Có cách biết cải tiến thành công hay thất bại không?** Nhóm dự kiến đo hoặc quan sát dấu hiệu gì?

Nguyên tắc **“Thường xuyên nhìn lại và điều chỉnh cách làm”** biến cải tiến liên tục thành hoạt động có thể thực hiện: **quan sát trung thực, cùng học hỏi, thử một thay đổi có chủ đích và kiểm tra tác động**. Sản phẩm được cải thiện qua phản hồi của người dùng; chính **cách nhóm tạo ra sản phẩm** cũng cần được cải thiện qua phản hồi của những người thực hiện công việc.
