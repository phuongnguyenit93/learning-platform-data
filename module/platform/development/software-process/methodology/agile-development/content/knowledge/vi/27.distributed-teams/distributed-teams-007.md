# Duy trì an toàn tâm lý cùng cơ hội đóng góp công bằng

## 1. Vì sao nhóm Agile phân tán cần cả an toàn tâm lý lẫn cơ hội đóng góp?

Một nhóm phát triển nền tảng học trực tuyến có Product Owner làm việc tại Việt Nam, Developers ở ba múi giờ và một người phụ trách kiểm thử thường tham gia từ xa. Trong Sprint Planning, phần lớn câu chuyện diễn ra giữa những thành viên ngồi cùng văn phòng. Một Developer từ xa phát hiện rằng API ghi danh có thể cấp quyền học cho trạng thái chưa được duyệt, nhưng cuộc họp đã gần hết giờ. Người ấy gửi câu hỏi vào kênh chat; không ai phản hồi trước khi quyết định thiết kế được chốt.

Hai tuần sau, lỗi cấp quyền xuất hiện trong môi trường tích hợp. Nhóm nói rằng “ai cũng có quyền phát biểu”, nhưng quyền phát biểu về mặt hình thức đã không chuyển thành **cơ hội tác động thực sự tới quyết định**. Người nêu rủi ro có thể học rằng lần sau tốt hơn nên im lặng để tránh bị xem là người làm chậm tiến độ.

**An toàn tâm lý (psychological safety)** là mức độ các thành viên cảm thấy có thể chấp nhận **rủi ro trong giao tiếp và cộng tác**, như đặt câu hỏi, thừa nhận chưa biết, nêu lỗi, đưa ý kiến khác hoặc đề nghị hỗ trợ, mà không phải lo bị làm nhục, trừng phạt hoặc bị coi thường một cách tùy tiện. **Cơ hội đóng góp công bằng** là khả năng tham gia tương xứng và có ý nghĩa vào trao đổi, ra quyết định và công việc, kể cả khi thành viên khác nhau về múi giờ, vị trí, ngôn ngữ, điều kiện kết nối, mức thâm niên hoặc quyền lực.

Hai yếu tố liên quan nhưng **không đồng nhất**:

- Một cuộc họp có thể rất thân thiện, không ai công kích nhau, nhưng người tham gia từ xa vẫn không được nghe rõ hoặc không có thời gian đọc tài liệu trước khi biểu quyết.
- Một nhóm có nhiều kênh góp ý, nhưng nếu người đưa cảnh báo luôn bị chế giễu hoặc bị phạt vì báo lỗi, họ sẽ không thấy an toàn để sử dụng các kênh ấy.
- Một nhóm có thể cho mỗi người đúng hai phút phát biểu, nhưng nếu quyết định đã được chốt trước trong một cuộc trao đổi ngoài luồng, thời lượng bằng nhau chưa tạo ra ảnh hưởng công bằng.

Trong **AGILE_DEVELOPMENT**, phản hồi sớm, phát triển tăng dần, Scrum, Kanban, XP và cải tiến liên tục đều cần thông tin thật. Khi thành viên không dám nói **“điều này có thể sai”** hoặc không có con đường để được lắng nghe, nhóm dễ học từ bằng chứng quá muộn.

> **Nguyên tắc cốt lõi:** Không chỉ tạo cảm giác dễ chịu. Hãy xây **một hệ thống cộng tác** trong đó người có thông tin quan trọng có thể nêu lên đúng lúc, ý kiến được xem xét công bằng, quyết định có dấu vết và những bất đồng được xử lý có trách nhiệm.

## 2. An toàn tâm lý là gì và không phải là gì?

An toàn tâm lý không có nghĩa mọi người luôn đồng ý, không bị phê bình hoặc không chịu trách nhiệm về chất lượng công việc. Trong một nhóm làm phần mềm, **đánh giá mã, thử nghiệm giả thuyết, phản biện thiết kế và xử lý sai lệch** là cần thiết; vấn đề nằm ở cách nhóm thực hiện.

| Cách hiểu | Có phù hợp không? | Giải thích |
| --- | --- | --- |
| “Tôi có thể nói mình chưa hiểu một quy tắc nghiệp vụ” | **Có** | Giúp lộ giả định trước khi mã hóa |
| “Tôi có thể báo sự cố do thay đổi của mình gây ra” | **Có** | Cho phép giảm tác động và học từ hệ thống |
| “Tôi có thể phản đối một thiết kế bằng bằng chứng” | **Có** | Bất đồng lành mạnh làm quyết định tốt hơn |
| “Ý tưởng của tôi phải được chấp nhận để tôi thấy an toàn” | **Không** | Được lắng nghe và phản hồi công bằng khác với có quyền quyết định cuối |
| “Không ai được nhận góp ý tiêu cực” | **Không** | Góp ý cụ thể, tôn trọng và có khả năng hành động vẫn rất cần |
| “Sai sót nghiêm trọng sẽ không có hệ quả nào” | **Không** | Nhóm vẫn cần trách nhiệm, tiêu chuẩn chất lượng và quy trình phù hợp |
| “Mọi cuộc trao đổi đều phải công khai với toàn đội” | **Không** | Dữ liệu cá nhân, phản ánh nhạy cảm và thông tin bảo mật cần kênh riêng |
| “Ai im lặng nghĩa là đã đồng ý” | **Không mặc định** | Sự im lặng có thể do thời gian, vị thế, công cụ hoặc thiếu thông tin |

### An toàn tâm lý và trách nhiệm cùng tồn tại

Ví dụ một Developer đưa thay đổi làm sai quyền truy cập. Phản hồi hữu ích là:

> “Chúng ta xác nhận API có thể trả nội dung bị hạn chế khi người học chưa ACTIVE. Hãy giới hạn tác động, thêm kiểm thử tái hiện và xem vì sao kiểm tra quyền ở máy chủ không có trong luồng review.”

Phản hồi gây hại:

> “Lỗi này quá sơ đẳng, người viết chắc không hiểu gì về bảo mật.”

Trường hợp đầu **nêu chuẩn mực và yêu cầu xử lý rõ ràng**. Trường hợp sau công kích năng lực cá nhân, làm giảm động cơ nêu lỗi và chia sẻ rủi ro.

### Không đồng nghĩa với sự thoải mái tuyệt đối

Thảo luận về trade-off của kiến trúc, phát hiện rủi ro bảo mật, đề cập một mục tiêu Sprint có nguy cơ không đạt hoặc phản biện quyết định của người có thâm niên đều có thể khiến người tham gia không thoải mái. **Mục tiêu là cho phép bất đồng được trao đổi an toàn và có trách nhiệm**, không xóa bỏ mọi tình huống khó.

## 3. “Bình đẳng” và “công bằng” trong đóng góp cần được hiểu thế nào?

**Đối xử giống nhau** và **tạo cơ hội thực chất** không phải lúc nào cũng đưa tới kết quả tương đương.

Giả sử cả nhóm được mời họp lúc 16:00 theo giờ của văn phòng chính. Với thành viên ở múi giờ khác, đó có thể là lúc rất sớm hoặc quá muộn. Lời mời giống nhau không bảo đảm mọi người có điều kiện đóng góp giống nhau.

| Khía cạnh | Cách làm có vẻ bình đẳng | Cách tạo cơ hội công bằng hơn |
| --- | --- | --- |
| **Lịch họp** | Luôn chọn giờ thuận tiện cho văn phòng đông người nhất | Dùng cửa sổ chồng lấn, luân phiên gánh nặng, ưu tiên async nếu không cần họp |
| **Phát biểu** | Chỉ hỏi “Ai có ý kiến?” trong 20 giây cuối | Gửi ngữ cảnh trước, cho thời gian viết và mời các góc nhìn liên quan |
| **Ngôn ngữ** | Yêu cầu tất cả phản ứng nhanh bằng ngôn ngữ thứ hai | Có văn bản, từ điển thuật ngữ và khoảng chuẩn bị phù hợp |
| **Thiết bị** | Dùng bảng trắng vật lý ở một phòng họp | Chuyển quyết định sang tài liệu số mọi người có thể đọc và bình luận |
| **Phân công việc** | Ai phản hồi nhanh nhất được chọn nhiệm vụ quan trọng | Phân công minh bạch theo năng lực, sở thích phát triển và cơ hội học tập |
| **Ý tưởng** | Đếm số lần mỗi người nói | Xem lập luận nào được cân nhắc, phản hồi và ghi vào quyết định |
| **Công nhận** | Khen người thuyết trình ở cuộc họp chung | Ghi nhận người phát hiện rủi ro, viết tài liệu, kiểm thử và hỗ trợ từ xa |

**Công bằng không có nghĩa mọi ý kiến có trọng lượng kỹ thuật hoặc nghiệp vụ như nhau trong mọi quyết định**. Người chịu trách nhiệm về sản phẩm, bảo mật hoặc kiến trúc có thể có quyền quyết định riêng. Điều cần minh bạch là **ai có quyền chốt, dựa trên tiêu chí nào và các ý kiến khác đã được xem xét thế nào**.

### Tránh suy diễn đặc điểm cá nhân

Không được mặc định người ít nói thiếu quan tâm, người nói chậm không hiểu vấn đề, hay người chọn góp ý bằng văn bản kém kỹ năng cộng tác. Có thể có nhiều nguyên nhân: văn hóa, tính cách, công cụ, điều kiện kết nối, trách nhiệm chăm sóc gia đình, nhu cầu tiếp cận hoặc đơn giản là cần đọc dữ liệu trước.

Hãy **hỏi về điều kiện giúp người ấy đóng góp tốt**, không gắn nhãn về năng lực hoặc bản sắc chỉ dựa vào hành vi ở một cuộc họp.

## 4. Những rào cản đặc thù của nhóm phân tán và hybrid

Nhóm phân tán không chỉ là nhóm ngồi cách xa nhau. Khó khăn xuất hiện từ **độ trễ giao tiếp, thông tin ngầm, khác biệt điều kiện truy cập và quyền lực không được nhìn thấy**.

### Bảy rào cản thường gặp

| Rào cản | Biểu hiện | Rủi ro đối với Agile |
| --- | --- | --- |
| **Múi giờ ít chồng lấn** | Một người phải thức khuya để dự cuộc họp quan trọng | Mệt mỏi, ít phát biểu, quyết định chậm |
| **Nhóm con cùng văn phòng** | Quyết định hình thành trong hành lang, người từ xa chỉ được thông báo sau | Thiếu transparency và thiếu tiếng nói phản biện |
| **Ngôn ngữ và tốc độ nói** | Người dùng ngôn ngữ thứ hai không theo kịp thảo luận trực tiếp | Bỏ qua rủi ro, đồng ý hình thức |
| **Kết nối/thiết bị không đồng đều** | Âm thanh trễ, camera gián đoạn, bảng trắng không truy cập được | Người tham gia bị loại khỏi dòng quyết định |
| **Chênh lệch thâm niên/quyền lực** | Thành viên mới không dám phản biện kiến trúc của lead | Sai giả định không được nêu sớm |
| **Kênh chat phân mảnh** | Quyết định nằm trong tin nhắn riêng hoặc nhóm nhỏ | Người vắng mặt thiếu ngữ cảnh, khó truy vết |
| **Khác biệt về giờ làm và nghĩa vụ cá nhân** | Tin nhắn khẩn giả khiến người ở nơi khác phải luôn trực | Kiệt sức, phản hồi vội, mất tính bền vững |

### Ví dụ rủi ro bị ẩn

Nhóm có một cuộc họp trực tiếp giữa ba Developers gần nhau và một người tham gia từ xa. Họ thống nhất cách ánh xạ trạng thái ghi danh, rồi gửi tin: **“Bọn mình đã quyết định dùng PENDING và ACTIVE như nhau ở UI”**.

Người kiểm thử từ xa không được tham gia đặt câu hỏi **“ACTIVE mới cấp quyền học, vậy UI có được nói ‘Đã ghi danh’ khi chỉ PENDING không?”**. Không phải vì người ấy thiếu trách nhiệm; cơ hội phản biện đã **bị tước đi ở giai đoạn có thể thay đổi quyết định**.

### Nhóm hybrid cần nhìn cả hai chiều

Không chỉ người ở xa chịu thiệt. Người ở văn phòng có thể bị yêu cầu luôn làm người dẫn cuộc họp, xử lý thiết bị, ghi biên bản hoặc trực hỗ trợ; công việc ấy cũng có chi phí. Chính sách công bằng cần thấy **gánh nặng phối hợp của mọi nơi**, rồi phân bổ có chủ đích.

## 5. Xác định ai đang được nghe và ai đang bị bỏ ngoài luồng

Trước khi áp dụng một loạt “mẹo remote”, nhóm nên quan sát **đường đi của thông tin và quyền quyết định**.

### Bản đồ cơ hội đóng góp

Một cách đơn giản là hỏi cho từng loại quyết định:

1. **Ai biết vấn đề sớm nhất?** Người dùng, QA, Developers, vận hành hay người nghiệp vụ?
2. **Ai có bằng chứng quan trọng?** Người hiểu dữ liệu cũ, quyền học, hợp đồng API, khả năng truy cập?
3. **Ai đang có quyền chốt?** Product Owner, Developers trong phạm vi kỹ thuật, người phụ trách bảo mật hay người có thẩm quyền khác?
4. **Ai dễ bị lỡ thông tin?** Người làm ca khác, người mới, người vắng họp, người chỉ có thiết bị di động?
5. **Ai chịu hậu quả của quyết định?** Học viên, người hỗ trợ, nhóm vận hành, thành viên trực sự cố?
6. **Kênh phản hồi nào thực sự hoạt động?** Bình luận tài liệu, issue, cuộc họp, 1:1 hoặc kênh bảo mật?

### Phân biệt mức tham gia

| Mức | Dấu hiệu | Cách cải thiện |
| --- | --- | --- |
| **Biết thông tin** | Được nhận tài liệu/quyết định | Gửi bản tóm tắt rõ, dễ tìm, có thời hạn bình luận |
| **Có thể phản hồi** | Có kênh và thời gian góp ý trước khi chốt | Tránh chỉ nhận bình luận sau khi quyết định đã triển khai |
| **Được xem xét** | Ý kiến được trả lời bằng lý do, bằng chứng | Ghi disposition: chấp nhận, điều chỉnh hoặc không chọn vì sao |
| **Có thể ảnh hưởng** | Phản hồi hợp lý có thể thay đổi phương án | Cho thấy quyết định đã thay khi có bằng chứng |
| **Được chia sẻ cơ hội học và dẫn dắt** | Không chỉ người ở cùng văn phòng được giao việc quan trọng | Luân phiên điều phối, trình bày, ownership và pairing có hỗ trợ |

**Mọi người không cần tham gia mọi quyết định.** Quá nhiều người bị kéo vào tất cả cuộc họp sẽ làm tăng WIP và làm chậm delivery. Mục tiêu là **những người có liên quan được tham gia đúng lúc**, và những người khác có bản ghi đủ để hiểu hoặc phản hồi theo chính sách.

## 6. Thiết lập Working Agreement về giao tiếp và ứng xử

**Working Agreement** là thỏa thuận vận hành mà nhóm cùng tạo, thử và cập nhật. Đối với nhóm phân tán, nên viết rõ những hành vi có thể quan sát được thay vì chỉ dùng khẩu hiệu “tôn trọng nhau”.

### Mẫu Working Agreement cho Scrum Team phân tán

~~~text
1. Phản biện ý tưởng và bằng chứng, không công kích con người.
2. Thừa nhận chưa biết, báo lỗi và đề nghị hỗ trợ được khuyến khích.
3. Quyết định quan trọng có bản ghi: bối cảnh, lựa chọn, người chốt, lý do.
4. Tài liệu và yêu cầu bình luận được gửi trước một khoảng hợp lý.
5. Không coi sự im lặng ngoài giờ làm là đồng ý hoặc từ chối.
6. Tin nhắn thường có thời gian phản hồi kỳ vọng; khẩn cấp dùng kênh riêng.
7. Cuộc họp có mục tiêu, agenda và kết quả; người từ xa được dùng chung công cụ.
8. Góp ý trực tiếp có thể bằng lời hoặc văn bản; không bắt ép bật camera.
9. Trường hợp nhạy cảm có đường hỗ trợ và xử lý riêng, không đưa lên chat công khai.
10. Mỗi Retrospective xem lại một điều trong thỏa thuận đã giúp/cản trở.
~~~

### Thỏa thuận cần cụ thể về thời gian phản hồi

Ví dụ:

| Loại trao đổi | Kênh gợi ý | Kỳ vọng theo chính sách nhóm |
| --- | --- | --- |
| **Thông tin không khẩn** | Tài liệu/issue/chat công khai của nhóm | Trả lời trong một khoảng giờ làm việc phù hợp, ví dụ trước ngày làm việc kế tiếp |
| **Câu hỏi đang chặn PBI** | Issue có owner + thông báo trong cửa sổ chồng lấn | Phản hồi sớm theo mức chặn, có kênh nâng cấp rõ |
| **Quyết định sản phẩm** | Bản ghi quyết định và người chốt | Có deadline góp ý, không tự xem im lặng là đồng thuận |
| **Sự cố nghiêm trọng** | Quy trình incident/on-call đã thỏa thuận | Kênh khẩn được định nghĩa riêng, gắn với người thực sự trực |
| **Phản ánh nhạy cảm** | 1:1 hoặc kênh báo cáo phù hợp | Tôn trọng bảo mật, không đưa chi tiết lên kênh rộng |

Các mốc trên là **ví dụ để nhóm tự thống nhất**, không phải cam kết chuẩn cho mọi múi giờ. Một chính sách tốt phải **thực tế với giờ làm, năng lực hỗ trợ và rủi ro sản phẩm**.

### Không áp dụng thỏa thuận như công cụ ép buộc

Nếu một Developer có việc cá nhân hoặc mất kết nối, không thể mặc định họ thiếu cam kết vì không trả lời chat ngay. Cần có **cơ chế dự phòng**, người thay thế khi blocker quan trọng và quy tắc escalation. Thỏa thuận cần được điều chỉnh khi thay đổi thành viên, địa điểm hoặc phương thức phát triển.

## 7. Async-first: trao cơ hội góp ý trước khi chốt quyết định

**Async-first** là xu hướng ưu tiên chia sẻ ngữ cảnh và thu phản hồi theo cách không đòi hỏi mọi người trực tuyến cùng lúc, khi điều đó phù hợp. Nó **không phải cấm các cuộc họp**: những vấn đề mơ hồ, bất đồng khó giải quyết hoặc tình huống khẩn vẫn cần nói chuyện trực tiếp.

Một quyết định thiết kế có thể đi qua ba bước:

1. **Đề xuất có ngữ cảnh:** ghi vấn đề, mục tiêu, lựa chọn, hệ quả và câu hỏi cần phản hồi.
2. **Cửa sổ góp ý:** các thành viên có liên quan có thời gian hợp lý để đọc, phản biện và đề nghị phương án khác.
3. **Quyết định và phản hồi:** người có quyền chốt ghi lựa chọn, lý do, các ý kiến chính được xem xét và điều kiện xem lại.

~~~mermaid
flowchart TD
    A["Vấn đề / câu hỏi cần quyết định"] --> B["Viết đề xuất ngắn + bằng chứng"]
    B --> C["Mời các vai trò có liên quan góp ý"]
    C --> D["Khoảng phản hồi phù hợp múi giờ"]
    D --> E{"Có bất đồng/rủi ro chưa giải quyết?"}
    E -->|"Có"| F["Trao đổi trực tiếp có điều phối, bổ sung bằng chứng"]
    F --> G["Người có thẩm quyền đưa quyết định"]
    E -->|"Không"| G
    G --> H["Ghi quyết định + lý do + cách xem lại"]
    H --> I["Thực hiện theo lát và quan sát kết quả"]
~~~

### Mẫu một đề xuất bất đồng bộ

~~~text
Vấn đề: Khi học viên đang PENDING, UI hiển thị gì?
Mục tiêu: Không gây hiểu lầm rằng yêu cầu đã được duyệt.
Sự thật đã xác nhận: Chỉ ACTIVE có quyền mở nội dung hạn chế.
Phương án A: Hiển thị "Đang chờ duyệt".
Phương án B: Hiển thị "Đã gửi yêu cầu" kèm bước tiếp theo.
Rủi ro: Người học tưởng đã được cấp quyền; hỗ trợ nhận thêm yêu cầu.
Ai cần góp ý: Product Owner/đại diện nghiệp vụ, UI, API, tester.
Hạn góp ý: Theo cửa sổ giờ làm việc đã thỏa thuận.
Người có quyền quyết định: Product Owner về hành vi/trải nghiệm.
Ngày xem lại: Sau thử nghiệm/feedback học viên nếu cần.
~~~

### Im lặng không mặc định là đồng thuận

Một số tổ chức dùng quy tắc **“không có phản đối trong thời hạn thì tiếp tục”** cho quyết định rủi ro thấp. Nếu áp dụng, phải **công bố trước** điều kiện này và bảo đảm những người cần tham gia có thời gian, thông tin và cách nâng cấp vấn đề. Với bảo mật, quyền truy cập, dữ liệu hoặc thay đổi khó đảo ngược, không nên suy từ sự im lặng rằng các chuyên gia đã chấp thuận.

### Async vẫn có thể thiếu công bằng

Một thread dài 200 bình luận, toàn thuật ngữ nội bộ và không có người chốt cũng là một rào cản. Tài liệu nên có **tóm tắt, câu hỏi cụ thể, hạn phản hồi, người quyết định và kết luận**, không phải chỉ “đăng link cho mọi người đọc”.

## 8. Thiết kế cuộc họp giúp người tham gia từ xa có ảnh hưởng thực chất

Cuộc họp có thể là nơi xây niềm tin hoặc nơi khiến người tham gia ngại nói. Đặc biệt trong môi trường hybrid, người từ xa thường phải cạnh tranh với tốc độ và ngôn ngữ cơ thể của người cùng phòng.

### Trước cuộc họp

- Có **mục tiêu và câu hỏi cần quyết định**, không chỉ tiêu đề “Đồng bộ”.
- Gửi agenda, dữ liệu và bản nháp **đủ sớm** để các múi giờ có thời gian chuẩn bị.
- Nêu rõ ai **cần tham gia để ra quyết định** và ai chỉ cần nhận thông tin.
- Sử dụng tài liệu và bảng số chung, có quyền truy cập phù hợp.
- Kiểm tra âm thanh, caption hoặc hình thức tiếp cận cần thiết trong phạm vi công cụ.
- Cho phép gửi câu hỏi/bình luận trước khi họp; không bắt người có ý kiến khác phải tranh luận ứng khẩu.

### Trong cuộc họp

| Thực hành | Giá trị | Điều cần tránh |
| --- | --- | --- |
| **Người điều phối mời nhiều góc nhìn** | Giảm độc quyền phát biểu của nhóm có mặt trực tiếp | Gọi bất ngờ và ép người ít nói trả lời ngay |
| **Thời gian viết im lặng ngắn** | Cho người cần suy nghĩ hoặc dùng ngôn ngữ thứ hai có cơ hội chuẩn bị | Coi ghi chú là biểu quyết đã chốt |
| **Round-robin có quyền bỏ lượt** | Mở cửa cho những người ít có vị trí trong cuộc họp | Bắt buộc mọi người phải nói hoặc tiết lộ chuyện riêng |
| **Một người nói một lúc** | Người từ xa và caption theo kịp | Nói chồng và trao đổi riêng không được truyền vào mic |
| **Theo dõi chat song song** | Nhận câu hỏi từ người ngại ngắt lời | Chỉ trả lời những người nói to nhất |
| **Hiển thị dữ liệu và quyết định trên tài liệu chung** | Mọi người thấy cùng ngữ cảnh | Chỉ vẽ bảng vật lý khó đọc qua camera |
| **Tóm tắt lựa chọn và lập luận** | Tránh hiểu nhầm “đã đồng thuận” | Kết luận bằng “mọi người biết rồi nhé” |

### Sau cuộc họp

Đăng **quyết định, lý do, người chịu trách nhiệm và vấn đề còn mở** ở nơi mọi người truy cập được. Nếu một thành viên không thể dự vì ngoài giờ, cần xác định họ có thể phản hồi trong phạm vi nào **trước khi quyết định khó đảo ngược** được thực hiện.

### Camera không phải thước đo cam kết

Camera có thể hữu ích cho một số cuộc trò chuyện, nhưng không bật camera **không chứng minh người ấy không tham gia**. Kết nối yếu, môi trường riêng tư, khả năng tiếp cận và nhu cầu cá nhân có thể khiến video không phù hợp. Đo sự tham gia qua **kết quả đóng góp, phản hồi có ý nghĩa và trách nhiệm thực tế**, không qua thời gian hiện mặt trên màn hình.

## 9. Công bằng về múi giờ: chia gánh nặng thay vì chuyển cho một nhóm nhỏ

Một lịch họp cố định có thể biến một vùng địa lý thành **người tham dự hạng hai**. Không có một giờ hoàn hảo cho mọi nhóm ở nhiều châu lục; cần quyết định minh bạch về **chi phí đồng bộ**.

### Nguyên tắc chọn lịch

1. **Ưu tiên async** khi mục đích chỉ là cập nhật trạng thái hoặc thu ý kiến độc lập.
2. Nếu cần họp, xem **giờ làm thông thường và cửa sổ chồng lấn thực tế**, không chỉ chuyển giờ bằng máy.
3. **Luân phiên** những cuộc họp không có giờ thuận lợi cho tất cả, thay vì luôn yêu cầu một địa điểm hi sinh.
4. **Ghi lại kết quả** để người vắng mặt theo kịp mà không cần xem video dài.
5. Có **chính sách nghỉ bù hoặc xử lý giờ bất thường** theo quy định tổ chức khi thực sự cần.
6. **Đừng mặc định người online muộn là luôn sẵn sàng**, đặc biệt với chat thông thường.

### Ví dụ thỏa thuận ba vùng

Giả sử nhóm có thành viên ở Đông Nam Á, châu Âu và Bắc Mỹ. Thay vì luôn tổ chức mọi cuộc họp theo giờ thuận tiện của trụ sở:

- **Sprint Planning cần trao đổi trực tiếp:** chọn cửa sổ chồng lấn khả thi, phân bổ phần chuẩn bị trước bằng tài liệu và giới hạn thời lượng đồng bộ.
- **Refinement:** thu câu hỏi và ví dụ trước bằng văn bản; chỉ gọi cuộc trao đổi trực tiếp khi có bất đồng quan trọng.
- **Daily coordination:** dùng bảng công việc và cập nhật async cho những người không có giờ chồng lấn; phần đồng bộ cần giữ mục tiêu rõ.
- **Sự cố production:** dùng người trực và quy trình escalation, không đánh thức toàn nhóm vì mọi cảnh báo nhỏ.
- **Retrospective:** chọn nhịp luân phiên hợp lý hoặc phiên kết hợp async/sync sao cho mọi thành viên có kênh góp ý an toàn.

Không bắt buộc tất cả thành viên phải tham gia mọi cuộc họp bằng video để được coi là một Scrum Team có trách nhiệm. Nhưng nếu nhóm áp dụng Scrum, vẫn cần bảo đảm **mục đích các Scrum events được đáp ứng và những người có trách nhiệm được tham gia theo cách hiệu quả**; không thay một sự kiện bằng bảng báo cáo hình thức.

### Đo gánh nặng múi giờ có chừng mực

Có thể xem số cuộc họp **ngoài khung giờ bình thường** theo vùng, tỷ lệ quyết định quan trọng được đưa ra khi một bên không có cơ hội phản hồi và sự hài lòng về lịch phối hợp. Không dùng dữ liệu ấy để suy diễn tình trạng sức khỏe hoặc hoàn cảnh gia đình cá nhân; ưu tiên thông tin **ở cấp nhóm và tự nguyện**.

## 10. Đảm bảo ý kiến được xem xét trong quá trình ra quyết định

An toàn tâm lý không thể duy trì nếu người đưa phản hồi hợp lý liên tục thấy ý kiến **biến mất mà không có lời giải thích**. Nhóm cần phân biệt **quyền lên tiếng, quyền quyết định và trách nhiệm thực hiện**.

### Một quy trình quyết định minh bạch

| Thành phần | Cần ghi | Ví dụ |
| --- | --- | --- |
| **Vấn đề** | Điều cần chốt và hệ quả | Chọn cơ chế đồng bộ tiến độ hai thiết bị |
| **Lựa chọn** | Các phương án khả thi và trade-off | Invalidate cache, versioned reads, thay luồng ghi |
| **Bằng chứng** | Quan sát, thử nghiệm, giả thuyết chưa chắc | Test đa phiên, dấu vết cache, rủi ro dữ liệu |
| **Ý kiến phản biện** | Rủi ro và phương án thay thế đã được nêu | QA cảnh báo đọc stale data; vận hành cảnh báo tải tăng |
| **Người quyết định** | Ai có quyền chốt phạm vi/thiết kế | Developers trong quyết định kỹ thuật; PO xác nhận yêu cầu |
| **Lý do** | Vì sao chọn phương án, hạn chế nào đã chấp nhận | Giữ tương thích, chi phí vận hành, độ nhất quán |
| **Điều kiện xem lại** | Tín hiệu nào cho thấy quyết định cần đổi | Lỗi tiến độ, độ trễ, tỷ lệ cache miss bất thường |

### Không đánh đồng “ý kiến được lắng nghe” với “mọi ý kiến được chọn”

Một Developer phản đối dùng thư viện mới vì rủi ro bảo trì. Sau khi xem benchmark và mức hỗ trợ, nhóm vẫn chọn thư viện ấy. Đây **có thể** là quy trình công bằng nếu người phản biện được nghe, lý do phản đối được xem xét và quyết định có tiêu chí rõ. Bất công xuất hiện khi ý kiến bị loại vì **người đưa ra ít thâm niên, ở xa hoặc không thuộc nhóm thân cận**, bất kể nội dung.

### Đừng biến consensus thành yêu cầu ngầm cho mọi việc

Không phải quyết định nào cũng cần sự đồng thuận tuyệt đối. Với thiết kế kỹ thuật có thể đảo ngược, nhóm có thể chọn một người chịu trách nhiệm, lấy ý kiến liên quan và thực hiện thử nhỏ. Với vấn đề quyền học hoặc an toàn dữ liệu, cần người có chuyên môn và thẩm quyền phù hợp. **Người chốt có trách nhiệm phản hồi những phản biện quan trọng**, không dùng danh nghĩa “đã quyết” để chặn thông tin mới.

### Decision log ngắn, dễ truy cập

~~~text
Quyết định: Giữ trạng thái PENDING khác ACTIVE trong API ghi danh
Vì sao cần chốt: Tránh cấp quyền học trước khi được duyệt
Phương án đã cân nhắc: Gộp trạng thái / giữ trạng thái riêng
Ý kiến đáng chú ý: Tester từ xa cảnh báo đường dẫn truy cập trực tiếp
Người chốt: Theo phân quyền sản phẩm + kỹ thuật đã thống nhất
Lý do: Quy tắc nghiệp vụ và an toàn yêu cầu phân biệt trạng thái
Tác động: Bổ sung acceptance criteria và API authorization tests
Điều kiện xem lại: Khi chính sách ghi danh được thay đổi chính thức
~~~

Một bản ghi như vậy cho thấy **cơ hội đóng góp có tác dụng thật** và giúp thành viên ở múi giờ khác hiểu quyết định mà không cần dự lại cuộc họp.

## 11. Góp ý code review mà không làm mất an toàn tâm lý

Code review là môi trường dễ xảy ra bất đồng vì các nhận xét liên quan trực tiếp công việc của người khác. Với nhóm phân tán, văn bản thiếu giọng điệu và ngữ cảnh có thể khiến một nhận xét ngắn bị hiểu thành chỉ trích cá nhân.

### Chuyển từ đánh giá con người sang đánh giá hành vi và rủi ro

| Nhận xét nên tránh | Nhận xét hướng vào vấn đề |
| --- | --- |
| “Đây là code dở, viết lại đi” | “Hàm này kiểm tra quyền sau khi đọc tiến độ. Có thể kiểm tra quyền trước để không để lộ dữ liệu không?” |
| “Ai cũng biết cách này sai” | “Trường hợp hai request ghi danh đồng thời có thể tạo trùng. Mình đề xuất thêm integration test cho bất biến duy nhất” |
| “Sao bạn không hiểu PR đơn giản này?” | “Mình chưa thấy cách trường hợp khóa đóng được xử lý; có thể bổ sung ví dụ để cùng xác nhận không?” |
| “Thay ngay theo ý tôi” | “Đây là yêu cầu vì hợp đồng API phải tương thích; phần naming là gợi ý có thể cân nhắc” |
| “LGTM” khi chưa kiểm tra rủi ro | “Mình đã xem luồng chính và test liên quan; phần migration dữ liệu cần người có chuyên môn rà thêm” |

### Phân biệt mức bắt buộc của nhận xét

Một chính sách đơn giản:

- **Blocking:** sai quyền, mất dữ liệu, vi phạm hợp đồng hoặc tiêu chuẩn chất lượng bắt buộc.
- **Question:** cần làm rõ giả định/hành vi.
- **Suggestion:** có cách đơn giản hơn hoặc dễ bảo trì hơn, chưa bắt buộc.
- **Nit:** chi tiết phong cách nhỏ, tốt nhất được xử lý qua linter/formatter.

Không biến mọi sở thích cá nhân thành nhận xét Blocking. Người nhận PR cần hiểu **điều gì là tiêu chuẩn, điều gì là đề xuất**.

### Phản hồi hai chiều

Tác giả PR có thể giải thích ràng buộc hoặc đưa bằng chứng khác mà không bị coi là chống đối. Người review cũng cần sẵn sàng nói **“Tôi đã bỏ sót ngữ cảnh; nhận xét trước của tôi không còn đúng”**. Hành vi thừa nhận sai này tạo tín hiệu mạnh rằng đưa câu hỏi và cập nhật quan điểm là bình thường.

### Pair programming và mob programming từ xa

Các thực hành XP có thể giúp chia sẻ hiểu biết nếu nhóm đặt nguyên tắc rõ: thay phiên điều khiển, hỏi trước khi sửa mã của người khác, giải thích ngữ cảnh, cho phép nghỉ và giữ quyền nêu bất đồng. Pairing không nên trở thành hoạt động người có thâm niên **độc chiếm bàn phím** còn người mới chỉ quan sát thụ động.

## 12. Thừa nhận lỗi, near miss và retro không đổ lỗi

Một nhóm Agile cần **phản hồi trung thực** khi có lỗi. Nếu thành viên sợ bị bêu tên vì làm hỏng pipeline hoặc phát hiện sai quyền, vấn đề có thể bị che cho tới lúc ảnh hưởng người dùng.

### Cách phản ứng khi có báo lỗi

1. **Cảm ơn người đã nêu thông tin**, không vội đánh giá đúng/sai hoặc tìm người có lỗi.
2. **Xác định mức ảnh hưởng và bảo vệ người dùng**, đặc biệt với quyền truy cập, bảo mật, thanh toán và dữ liệu.
3. **Tách hiện tượng khỏi giả thuyết:** điều đã quan sát được là gì, điều nào còn chưa kiểm chứng?
4. **Làm rõ quyết định và bối cảnh** tại thời điểm người thực hiện chọn cách làm.
5. **Tìm các điều kiện hệ thống góp phần gây lỗi**: yêu cầu mơ hồ, thiếu test, giao tiếp muộn, WIP cao, pipeline không ổn định.
6. **Theo dõi hành động phòng ngừa có thể kiểm chứng**, không dừng ở “lần sau cẩn thận”.

~~~mermaid
flowchart TD
    A["Một thành viên nêu rủi ro/lỗi/near miss"] --> B["Lắng nghe và xác nhận thông tin, không bêu tên"]
    B --> C{"Có rủi ro khẩn với người dùng/dữ liệu?"}
    C -->|"Có"| D["Ứng phó sự cố và giảm tác động ngay"]
    C -->|"Không"| E["Làm rõ bằng chứng và phạm vi"]
    D --> E
    E --> F["Phân tích cơ chế + điều kiện hệ thống"]
    F --> G["Chọn biện pháp phòng ngừa, owner và guardrail"]
    G --> H["Thử/triển khai và kiểm tra hiệu quả"]
    H --> I["Cập nhật working agreement, DoD hoặc backlog"]
~~~

### Blameless không phải miễn trách nhiệm

Một postmortem **không đổ lỗi** nhằm cho phép mô tả trung thực điều đã xảy ra. Nó không cấm kiểm tra hành vi vi phạm chính sách, che giấu dữ liệu hoặc cố tình gây hại theo quy trình tổ chức. Điều cần tránh là **kết luận về lỗi đạo đức từ một sai sót kỹ thuật bình thường** hoặc đưa quyết định kỷ luật vào cuộc họp Retrospective công khai.

### Khi người quản lý cũng tham gia Retrospective

Chênh lệch quyền lực có thể làm một số người ngại chia sẻ. Nhóm nên nêu rõ mục đích sự kiện, cách dùng thông tin, ai được truy cập bản ghi và kênh trao đổi riêng khi cần. Không thể **bảo đảm ẩn danh** nếu nhóm chỉ có ba người và mọi câu chuyện đều dễ nhận ra nguồn. Tránh hứa bí mật tuyệt đối hoặc dùng phiếu “ẩn danh” cho vấn đề nhạy cảm mà không thể bảo vệ danh tính.

### Retrospective không thay thế kênh xử lý hành vi gây hại

Quấy rối, phân biệt đối xử, đe dọa hoặc hành vi trả đũa cần **kênh báo cáo và xử lý phù hợp** theo chính sách tổ chức/pháp luật. Không nên yêu cầu người bị ảnh hưởng phải kể lại chi tiết trước toàn Scrum Team rồi cùng “bỏ phiếu hòa giải”. Người điều phối cần biết **ranh giới của mình**, tôn trọng quyền riêng tư và chuyển đúng quy trình có thẩm quyền.

## 13. Xử lý bất đồng và xung đột một cách có trách nhiệm

Trong nhóm phân tán, một câu ngắn qua chat như “Không ổn” có thể gây hiểu lầm nghiêm trọng. Không nên vì sợ xung đột mà tránh tranh luận; cần chuyển bất đồng từ **đối đầu cá nhân** sang **câu hỏi có thể kiểm chứng**.

### Quy trình bốn bước

1. **Nêu quan sát và ảnh hưởng:** “API hiện trả ACTIVE ngay khi tạo yêu cầu chờ duyệt; theo quy tắc đã xác nhận, quyền học chỉ được cấp sau khi duyệt”.
2. **Hỏi cách hiểu và điều kiện ràng buộc:** “Có chính sách mới hoặc phụ thuộc nào mà mình chưa thấy không?”.
3. **Đề xuất lựa chọn và cách kiểm chứng:** “Giữ PENDING, bổ sung test quyền trực tiếp; hoặc nếu nghiệp vụ đổi, cập nhật acceptance criteria trước”.
4. **Xác nhận quyết định và trách nhiệm:** ghi ai có quyền chốt, điều gì được thay đổi, ai kiểm tra kết quả.

### Mẫu câu hỗ trợ bất đồng

~~~text
Mình có thể đang thiếu ngữ cảnh về <vấn đề>.
Điều mình quan sát là <sự kiện/bằng chứng>.
Mối lo là <rủi ro/ảnh hưởng đối với người dùng hoặc DoD>.
Chúng ta có thể kiểm tra <dữ liệu/test/phương án> trước khi chốt không?
Ai cần xác nhận phần nghiệp vụ hoặc bảo mật này?
~~~

Mẫu này không phải quy tắc bắt người có vị thế thấp phải “xin phép” mới được nêu lỗi. Nó chỉ giúp mở cuộc trao đổi theo cách **không quy kết ý đồ**. Khi thấy rủi ro nghiêm trọng, thành viên cần được phép **nêu rõ và nâng cấp ngay**, không phải mềm hóa đến mức tín hiệu bị bỏ qua.

### Khi bất đồng không giải quyết qua chat

Nếu thread kéo dài, hai người liên tục hiểu sai nhau hoặc cần lựa chọn giữa nhiều trade-off, hãy chuyển sang cuộc trao đổi đồng bộ ngắn có điều phối và chia sẻ tài liệu chung. Sau đó **ghi kết luận bất đồng bộ** để những người không tham dự vẫn thấy lý do và cơ hội phản hồi còn lại.

### Khi quyền lực làm bất đồng mất cân bằng

Nếu một lead kỹ thuật thường ngắt lời người mới, người điều phối có thể **đặt lại quy tắc phát biểu**, yêu cầu nghe trọn ý kiến và chuyển nội dung sang đánh giá bằng chứng. Nếu hành vi tiếp tục hoặc có dấu hiệu trả đũa, cần **cơ chế quản lý và báo cáo phù hợp**, không chỉ trông đợi người bị ảnh hưởng tự mạnh dạn hơn.

## 14. Scrum trong nhóm phân tán: minh bạch và kiểm tra thực nghiệm

Scrum được xây trên **transparency, inspection và adaptation**. Những nguyên tắc này khó vận hành nếu các thành viên không thể nêu rủi ro hoặc thiếu cơ hội tham gia sự kiện đúng mục đích.

### Sprint Planning

- Product Owner truyền đạt mục tiêu, bối cảnh Product Backlog Items và giá trị cần đạt.
- Developers cùng thảo luận khả năng thực hiện và cách tạo Increment; không để một nhóm ở cùng phòng **quyết hộ tất cả**.
- Câu hỏi về acceptance criteria, phụ thuộc và rủi ro được thu trước bằng văn bản.
- Sprint Goal cần được hiểu chung, không chỉ dịch thành danh sách task giao cho từng địa điểm.

### Daily Scrum

- Mục đích là để **Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh kế hoạch**, không phải điểm danh hay báo cáo lên quản lý.
- Với thành viên phân tán, bảng Sprint Backlog rõ ràng giúp người vắng một cuộc trao đổi nhỏ vẫn hiểu tình trạng.
- Không yêu cầu mọi người trực tuyến suốt ngày để chứng minh làm việc; blocker cần kênh nêu rõ.
- Nếu thời gian chồng lấn rất hạn chế, có thể bổ trợ bằng cập nhật async, nhưng phải bảo đảm mục đích kiểm tra và thích ứng được thực hiện, không biến Daily Scrum thành những tin nhắn rời rạc không ai phản hồi.

### Sprint Review

- Tạo cơ hội cho stakeholder ở các nơi **xem Increment, đặt câu hỏi và đưa bằng chứng**.
- Không chỉ trình chiếu một demo do trụ sở điều khiển; có thể thu phản hồi trước/sau theo cửa sổ hợp lý.
- Ghi nhận người đã phát hiện rủi ro chất lượng và phản hồi ngoài cuộc họp.
- Product Backlog được điều chỉnh theo kết quả và phản hồi, không chỉ nhận lời khen từ người có mặt.

### Sprint Retrospective

- Tạo không gian để nói về cách làm, chất lượng và hiệu quả mà không công kích cá nhân.
- Thu đầu vào bằng nhiều hình thức: viết riêng, thảo luận nhỏ, tài liệu chung, kênh hỗ trợ khi nhạy cảm.
- Chọn **ít hành động cải tiến** có owner, thời hạn và cách xem hiệu quả, không chỉ biểu quyết cho “vấn đề lớn nhất”.
- Kiểm tra liệu các action trước đã giúp người ít có cơ hội phát biểu **được nghe và có ảnh hưởng hơn** hay chưa.

### Các trách nhiệm trong Scrum không bị thay đổi

Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog; Developers chịu trách nhiệm tạo Increment đạt Definition of Done; Scrum Master hỗ trợ hiệu quả Scrum Team và Scrum. **An toàn tâm lý là trách nhiệm cộng tác của cả nhóm**, không phải lý do chuyển mọi quyết định sang Scrum Master hoặc yêu cầu Product Owner duyệt từng lựa chọn kỹ thuật.

## 15. Kanban giúp minh bạch công việc và giảm bất bình đẳng về thông tin

Một bảng Kanban tốt cho phép thành viên ở nhiều địa điểm **nhìn cùng một luồng công việc** thay vì phải hỏi người ngồi gần leader để biết việc gì đang xảy ra.

### Thiết kế chính sách luồng dễ tiếp cận

| Chính sách | Lợi ích với nhóm phân tán |
| --- | --- |
| **Định nghĩa rõ Ready/In Progress/Review/Done** | Người ở múi giờ khác hiểu khi nào công việc thực sự chuyển trạng thái |
| **WIP limits** | Giảm mở việc mới khi người khác đang chờ review hoặc hỗ trợ |
| **Blocked flag có lý do** | Người từ xa có thể báo phụ thuộc mà không cần chờ cuộc họp |
| **Explicit policies** | Tránh “luật ngầm” chỉ những người làm cùng văn phòng mới biết |
| **Work Item Age** | Thấy hạng mục tồn tại lâu dù owner ít phát biểu |
| **Cycle time và throughput** | Theo dõi flow của hệ thống, không dùng số việc để chấm cá nhân |
| **Class of service cho việc khẩn** | Biết khi nào phải dùng escalation và ai trực, tránh spam khẩn mọi nơi |

### Ví dụ một chính sách Review

~~~text
Khi một PR ở Ready for Review:
  - Tác giả cung cấp mục đích, phạm vi, rủi ro và cách kiểm tra.
  - Reviewer trong cửa sổ làm việc của mình phản hồi theo SLA nội bộ.
  - Nếu quá hạn, board đánh dấu blocker và dùng kênh nhờ hỗ trợ.
  - Người review ghi rõ blocking issue và suggestion.
  - Không coi việc tác giả chưa trả lời ngoài giờ là không hợp tác.
  - Khi có bất đồng khó giải quyết bằng văn bản, tổ chức trao đổi ngắn
    và ghi quyết định trở lại PR.
~~~

SLA nội bộ là **thỏa thuận phối hợp có điều kiện**, không phải quy định bắt mọi người online ngoài giờ. Một hạng mục bị chặn lâu có thể cần **thay đổi năng lực, chính sách WIP hoặc phụ thuộc**, không phải thêm áp lực cho người đang ở xa.

## 16. XP và các thực hành kỹ thuật tạo cơ hội đóng góp thực chất

Những thực hành của Extreme Programming giúp các thành viên cộng tác qua **bằng chứng có thể chạy và mã có thể xem xét**, giảm phụ thuộc vào lời nói của người có vị thế cao.

### Test-Driven Development và Automated Acceptance Tests

- **TDD** giúp thể hiện một quy tắc nhỏ bằng test trước khi viết mã; thảo luận dựa trên ví dụ có thể kiểm tra.
- **ATDD/BDD** hỗ trợ người nghiệp vụ, Developers và tester thống nhất các trường hợp chấp nhận trước khi triển khai.
- **CI** cho tín hiệu chung: một thay đổi phá hợp đồng sẽ bị phát hiện mà không cần người ở cùng văn phòng “nói có vẻ ổn”.

Nhưng công cụ **không tự tạo an toàn tâm lý**. Nếu người viết test âm báo lỗi bị chê là “phá sprint”, hoặc pipeline đỏ bị giấu để tránh phê bình, nhóm vẫn thiếu an toàn trong giao tiếp.

### Pairing và luân phiên ownership

Pair/mob programming có thể giúp người mới hoặc người ở múi giờ khác hiểu module quan trọng. Thực hành tốt gồm:

- Chọn cặp và thời gian theo khả năng chồng lấn thực tế.
- Thay phiên điều khiển, đọc mã và giải thích; cho phép xin nghỉ.
- Nêu rõ mục tiêu buổi làm, không biến pairing thành giám sát năng suất cá nhân.
- Khuyến khích hỏi “vì sao?” và kiểm chứng bằng test.
- Ghi lại quy tắc quan trọng và quyết định để người không dự pairing vẫn tiếp cận được.

**Collective code ownership** không nghĩa ai cũng thay mã quan trọng mà không review hoặc bỏ quy trình bảo mật. Nó tạo cơ hội góp phần vào toàn sản phẩm với các tiêu chuẩn chất lượng và phối hợp rõ ràng.

### Kết nối kỹ thuật với cơ hội phát triển

Nếu chỉ một nhóm ở trụ sở được làm kiến trúc lõi còn người từ xa chỉ nhận task giao diện nhỏ, cơ hội đóng góp và học hỏi có thể mất cân bằng. Có thể luân phiên **dẫn dắt thử nghiệm, trình bày quyết định, hỗ trợ review và làm việc với module quan trọng** theo năng lực và mong muốn của thành viên, có mentoring thích hợp.

## 17. Onboarding, tài liệu và khả năng tiếp cận cho thành viên mới

Người mới trong nhóm phân tán không thể dựa vào việc ngồi cạnh đồng nghiệp để nghe toàn bộ quy tắc ngầm. Nếu thông tin thiết yếu chỉ tồn tại trong trí nhớ hoặc cuộc trò chuyện hành lang, họ có thể **không biết phải hỏi gì hoặc hỏi ai**.

### Bộ thông tin onboarding tối thiểu

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| **Mục tiêu sản phẩm và người dùng** | Chúng ta đang tạo giá trị gì, những rủi ro nào là quan trọng? |
| **Vai trò và quyền quyết định** | Ai xác nhận nghiệp vụ, ai chốt kiến trúc, ai điều phối incident? |
| **Working Agreement** | Giờ phối hợp, kênh thông thường/khẩn, cách nêu blocker là gì? |
| **Luồng công việc** | Ready, In Progress, Review, Done nghĩa là gì? |
| **Definition of Done** | Những kiểm tra chất lượng nào bắt buộc trước khi gọi Increment Done? |
| **Thiết lập môi trường** | Làm sao chạy test cục bộ và CI, tìm help khi bị chặn? |
| **Quyết định cũ** | ADR/decision log nằm đâu, tại sao dùng lựa chọn hiện tại? |
| **Kênh phản ánh** | Nếu cảm thấy bị gạt ra ngoài hoặc gặp hành vi không phù hợp, tìm hỗ trợ ở đâu? |
| **Bạn đồng hành** | Ai hỗ trợ trong những tuần đầu, lịch trao đổi có phù hợp múi giờ không? |

### Tài liệu dễ đọc và cập nhật

Một bản ghi ngắn, có tên rõ, có ví dụ và liên kết tới nguồn chính thường hữu ích hơn nhiều trang không ai duy trì. Khi người mới hỏi một câu lặp lại, đó có thể là tín hiệu **tài liệu hoặc điểm truy cập chưa rõ**, không phải bằng chứng họ “không tự tìm hiểu”.

### Khả năng tiếp cận và nhiều hình thức đóng góp

Để hỗ trợ người có điều kiện nghe/nhìn, ngôn ngữ hoặc kết nối khác nhau, nhóm có thể:

- Cung cấp agenda và kết luận bằng văn bản.
- Dùng caption hoặc transcript có kiểm soát khi công cụ và quyền riêng tư cho phép.
- Tránh dựa hoàn toàn vào màu sắc hoặc cử chỉ trên bảng vật lý.
- Cho phép tham gia qua bình luận tài liệu, chat hoặc audio.
- Gửi tài liệu ở định dạng có thể tìm kiếm và đọc bằng công cụ hỗ trợ.
- Kiểm tra quyền truy cập trước khi yêu cầu phản hồi.

Không cần yêu cầu thành viên tiết lộ **tình trạng sức khỏe hoặc thông tin riêng tư** để nhóm đáp ứng một nhu cầu tiếp cận hợp lý. Hỏi “Bạn cần cách tham gia nào để làm việc hiệu quả?” thường đủ để bắt đầu.

## 18. Phản hồi nhạy cảm, quyền riêng tư và chống trả đũa

Một nhóm không thể tự tuyên bố an toàn tâm lý chỉ bằng khẩu hiệu. Khi ai đó báo hành vi quấy rối, loại trừ khỏi quyết định hoặc trả đũa sau khi nêu lỗi, nhóm phải có **đường hỗ trợ có thẩm quyền** và tránh làm tình hình tệ hơn.

### Nguyên tắc xử lý

1. **Lắng nghe và ghi nhận vừa đủ:** không đòi người báo phải kể chi tiết cho toàn nhóm.
2. **Phân biệt kênh:** góp ý quy trình bình thường có thể thảo luận tại Retro; phản ánh nhạy cảm cần kênh được chỉ định.
3. **Không hứa bí mật tuyệt đối:** giải thích trung thực thông tin có thể cần được chia sẻ với người có trách nhiệm xử lý.
4. **Giảm nguy cơ trả đũa:** không dùng thông tin từ phản ánh để phạt người nêu vấn đề theo cách không phù hợp.
5. **Bảo vệ dữ liệu:** giới hạn quyền truy cập và thời gian lưu bản ghi nhạy cảm theo chính sách.
6. **Không ép hòa giải trực tiếp:** có những tình huống cần quản lý/nhân sự hoặc chuyên môn pháp lý xử lý.
7. **Theo dõi kết quả:** xem người phản ánh có còn gặp rào cản hoặc hành vi gây hại, trong phạm vi quyền và bảo mật cho phép.

### Nơi xử lý một vấn đề rất quan trọng

- **“Chúng ta thường chốt API mà chưa đọc ý kiến người kiểm thử ở ca khác”**: phù hợp để cải tiến quy trình và decision log ở Retro.
- **“Một thành viên thường xuyên chế giễu giọng nói/ngôn ngữ của tôi”**: cần kênh hỗ trợ và xử lý hành vi; không nên biến thành một cuộc biểu quyết ai đúng.
- **“Tôi vừa phát hiện lỗ hổng cho phép truy cập dữ liệu người học”**: cần kênh báo rủi ro bảo mật/incident ngay, đồng thời sau đó rút bài học về giao tiếp và kiểm thử.

An toàn tâm lý cần **cả thói quen hằng ngày lẫn cơ chế bảo vệ khi có vấn đề nghiêm trọng**. Một nhóm làm tốt cuộc họp nhưng thiếu đường xử lý trả đũa vẫn chưa đủ.

## 19. Đo an toàn tâm lý và sự công bằng mà không biến nó thành KPI cá nhân

Đây là những khái niệm khó đo trực tiếp. Một khảo sát đơn giản có thể cho tín hiệu, nhưng câu trả lời dễ chịu ảnh hưởng bởi **nỗi lo bị nhận diện, quan hệ quyền lực, thời điểm sự cố và cách đặt câu hỏi**.

### Bộ câu hỏi pulse survey minh họa

Có thể hỏi tự nguyện theo thang mức đồng ý, với lựa chọn **“Không muốn trả lời”**:

1. “Trong nhóm, tôi có thể nói **‘tôi chưa hiểu’** hoặc đề nghị giúp đỡ mà không bị làm nhục”.
2. “Khi phát hiện rủi ro ảnh hưởng người dùng, tôi có thể **nêu sớm** mà không lo bị quy kết tùy tiện”.
3. “Tôi có **cách góp ý hữu hiệu** về quyết định liên quan công việc dù không dự được cuộc họp trực tiếp”.
4. “Các ý kiến bất đồng được **xem xét bằng lý do và bằng chứng**, không chỉ theo chức danh hoặc nơi làm việc”.
5. “Lịch và kênh phối hợp cho phép tôi tham gia **bền vững** mà không thường xuyên phải làm ngoài giờ”.

Đây là **câu hỏi thực hành do nhóm tự lựa chọn**, không được trình bày như một thang đo tâm lý đã được chuẩn hóa. Nếu tổ chức muốn dùng một công cụ đánh giá khoa học, cần xem hướng dẫn chuyên môn phù hợp và điều kiện bảo mật trước khi triển khai.

### Theo dõi cả hành vi và quy trình, không chỉ cảm nhận

| Tín hiệu | Câu hỏi hữu ích | Rủi ro khi diễn giải |
| --- | --- | --- |
| **Cơ hội phản hồi trước khi chốt** | Quyết định quan trọng có cửa sổ góp ý và người liên quan được mời không? | Gửi link không có nghĩa người khác đủ thời gian đọc |
| **Ý kiến được phản hồi có lý do** | Bất đồng được ghi nhận và trả lời thế nào? | Không nên đặt mục tiêu tất cả ý kiến đều được chọn |
| **Phân bố cuộc họp ngoài giờ** | Một khu vực có phải chịu phần lớn gánh nặng? | Tránh suy diễn hoàn cảnh cá nhân |
| **Thời gian chờ quyết định nghiệp vụ** | Người ở nơi khác có chờ lâu vì thiếu quyền chốt? | Cần đo theo loại vấn đề và giờ làm thực tế |
| **Work item age và blocker** | Hạng mục do những người khác nhau phụ trách có cơ hội tháo blocker công bằng? | Không dùng số này đánh giá năng lực cá nhân |
| **Near miss/defect reports** | Nhóm có dám và có thể nêu sớm rủi ro? | Số báo cáo tăng ban đầu có thể là tín hiệu phát hiện tốt hơn |
| **Pulse survey tự nguyện** | Thành viên thấy an toàn và có tiếng nói hơn theo thời gian không? | Mẫu nhỏ, định danh dễ lộ và hiệu ứng thời điểm |
| **Cơ hội lãnh đạo/chia sẻ kiến thức** | Ai được dẫn dắt thảo luận, ownership và thử nghiệm? | Không áp quota cơ học cho từng cá nhân |

### Quy tắc riêng tư khi đo

Trong nhóm năm người, chia kết quả khảo sát theo **múi giờ, giới tính, thâm niên hoặc văn phòng** có thể khiến câu trả lời bị nhận diện. Cần giới hạn dữ liệu, báo cáo tổng hợp khi đủ an toàn, nêu mục đích sử dụng và có cơ chế không tham gia mà không bị bất lợi.

**Không đo số lần phát biểu hay số tin nhắn như điểm năng suất của cá nhân.** Một người viết một bình luận ngắn phát hiện lỗi quyền quan trọng có thể đóng góp nhiều hơn mười người nói liên tục mà không tạo quyết định.

### Tín hiệu xấu cần kéo theo hành động

Nếu nhiều thành viên nói rằng **“ý kiến của tôi chỉ được hỏi sau khi quyết định đã chốt”**, hành động có thể là thay đổi RFC/decision log và lịch góp ý, rồi xem lại phản hồi sau vài chu kỳ. Nếu khảo sát chỉ được thu nhưng không ai làm gì, niềm tin có thể giảm hơn trước.

## 20. Thử nghiệm cải tiến: từ im lặng trong họp đến phản hồi có ảnh hưởng

Nhóm nhận thấy ở ba Sprint gần đây, các câu hỏi từ người tham gia từ xa thường xuất hiện **sau cuộc họp quyết định**. Không có bằng chứng họ thiếu quan tâm; vấn đề có thể nằm ở **thiếu tài liệu trước họp, giờ bất lợi và nhóm con chốt sớm**.

### Đặt giả thuyết

> “Nếu mọi quyết định nghiệp vụ/kỹ thuật quan trọng có một bản đề xuất ngắn, cửa sổ phản hồi phù hợp múi giờ và bản ghi quyết định, chúng ta sẽ phát hiện thêm rủi ro trước khi triển khai và giảm việc phải sửa vì hiểu sai, mà không làm thời gian ra quyết định tăng quá mức”.

### Kế hoạch thử trong hai chu kỳ

| Yếu tố | Cách thực hiện minh họa |
| --- | --- |
| **Phạm vi** | Những quyết định về quyền học, trạng thái ghi danh và giao tiếp API giữa các nhóm |
| **Đường cơ sở** | Trong 8 quyết định gần nhất, 5 quyết định không có tài liệu cho người từ xa góp ý trước khi chốt |
| **Hành động** | Tạo mẫu RFC/decision log ngắn; mời đúng người; đặt hạn phản hồi theo giờ làm |
| **Owner** | Một Developer điều phối kỹ thuật, phối hợp PO/tester và nhóm liên quan |
| **Cách phản hồi** | Bình luận tài liệu hoặc trao đổi ngắn nếu có bất đồng/rủi ro cao |
| **Tín hiệu đầu ra** | Tỷ lệ quyết định có ngữ cảnh, cửa sổ góp ý và kết luận |
| **Outcome kỳ vọng** | Ít quyết định phải sửa vì thiếu ý kiến của người liên quan |
| **Guardrail** | Không tăng thời gian chờ quyết định quá mức; không che lỗi an toàn hoặc ép làm ngoài giờ |
| **Mốc đánh giá** | Retrospective sau hai chu kỳ; thêm dữ liệu nếu chưa đủ kết luận |

### Kết quả minh họa cần diễn giải thận trọng

Giả sử trong 10 quyết định sau thử, 9 có đề xuất viết trước; ba rủi ro được chỉ ra trong bình luận từ xa, hai được xử lý trước khi lập trình. Đây là **bằng chứng các kênh phản hồi đang được sử dụng và có tác động**, nhưng chưa chứng minh **an toàn tâm lý toàn nhóm đã tăng**. Cần kết hợp phản hồi tự nguyện, số lần làm lại, chất lượng quyết định và gánh nặng phối hợp.

### Khi thử nghiệm tạo tác dụng phụ

Nếu mọi quyết định nhỏ đều phải chờ ba ngày để đủ “công bằng”, lead time có thể tăng không cần thiết. Nhóm có thể điều chỉnh:

- **Quyết định rủi ro thấp, dễ đảo ngược:** thời gian góp ý ngắn, một người chịu trách nhiệm chốt.
- **Quyết định ảnh hưởng dữ liệu/quyền hoặc khó đảo ngược:** cần đúng chuyên gia và bằng chứng trước khi triển khai.
- **Sự cố khẩn:** xử lý theo kênh khẩn và công bố bản ghi sau, không đợi cửa sổ async thông thường.

Công bằng **không đồng nghĩa trì hoãn mọi quyết định**. Nó nghĩa là **điều kiện tham gia và quyền quyết định được thiết kế minh bạch, phù hợp hậu quả**.

## 21. Case study: cảnh báo từ QA ở múi giờ khác bị bỏ qua

### 21.1. Bối cảnh

Nhóm phát triển một nền tảng học trực tuyến với:

- Product Owner tại một văn phòng chính.
- Ba Developers thường xuyên làm việc cùng nhau.
- Hai Developers và một tester tham gia từ xa ở các múi giờ khác.
- Một nhóm vận hành chịu trách nhiệm rollout và quan sát production.

Nhóm chuẩn bị release luồng **ghi danh khóa học cần xét duyệt**. Trong buổi refinement, trụ sở chọn cách dùng chung nhãn **“Đã ghi danh”** cho trạng thái PENDING và ACTIVE để giảm công việc UI. Tester từ xa gửi câu hỏi: **“Nếu PENDING chưa cấp quyền học, nhãn này có làm người học hiểu sai? API có kiểm soát quyền ở máy chủ không?”**.

Vì cuộc họp đã kết thúc, câu hỏi không được xem xét. Developers làm theo kết luận từ cuộc họp. Khi test tích hợp, một đường dẫn trực tiếp vẫn mở được bài học khi học viên chưa ACTIVE. Nhóm phải sửa gấp và lùi một phần rollout.

### 21.2. Phân tích nguyên nhân theo góc nhìn hệ thống

| Quan sát | Cơ chế góp phần | Điều không nên kết luận vội |
| --- | --- | --- |
| Quyết định hình thành trong cuộc họp một địa điểm | Người ở xa không có cơ hội phản biện đúng lúc | “Tester không đủ chủ động” |
| Câu hỏi quan trọng bị bỏ trong chat | Không có owner xử lý bình luận sau họp | “Người gửi chỉ nói quá muộn” |
| Nhãn PENDING/ACTIVE mơ hồ | Thiếu ví dụ nghiệp vụ phân biệt quyền và trạng thái | “UI luôn là nguyên nhân gốc” |
| API thiếu test truy cập trái quyền | DoD/kiểm thử chưa bảo vệ rủi ro quyền tương xứng | “Chỉ cần họp thân thiện hơn” |
| Không có decision log | Nhóm không thấy ý kiến nào đã được cân nhắc | “Ai đó chắc đã đọc tin nhắn rồi” |

**Bài học:** sự cố không thể được ngăn chỉ bằng yêu cầu người tester “mạnh dạn hơn”. Nhóm cần **thay đổi cơ chế phản hồi và bằng chứng kiểm thử**.

### 21.3. Biện pháp ở nhiều lớp

1. **Ứng phó lỗi:** ngăn cấp quyền sai, kiểm tra dữ liệu/người dùng ảnh hưởng, khắc phục và rollout an toàn.
2. **ATDD:** làm rõ ví dụ trạng thái PENDING và ACTIVE; tiêu chí cho API truy cập trái quyền.
3. **Decision log:** quyết định ảnh hưởng quyền phải có chuyên gia liên quan góp ý hoặc được chốt theo quy trình escalated đã xác định.
4. **Cơ hội async:** gửi đề xuất trước, có cửa sổ góp ý cho người ở múi giờ khác.
5. **Facilitation:** người điều phối kiểm tra ý kiến trong tài liệu/chat trước khi kết luận.
6. **Kiểm thử:** bổ sung integration/security tests ở máy chủ, không chỉ xác nhận UI ẩn nút.
7. **Retrospective:** hỏi về điều kiện khiến rủi ro không được nghe, không truy tìm “ai là người im lặng”.
8. **Theo dõi:** đánh giá liệu các quyết định rủi ro cao về sau có ghi nhận và xử lý phản biện đúng lúc.

### 21.4. Ví dụ acceptance criteria sau khi làm rõ

~~~gherkin
Feature: Quyền học sau khi gửi yêu cầu ghi danh

  Scenario: Học viên đang chờ xét duyệt
    Given học viên đã gửi yêu cầu ghi danh khóa cần duyệt
    And yêu cầu có trạng thái PENDING
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái đang chờ duyệt
    And không hiển thị rằng quyền học đã được cấp

  Scenario: Người chưa được duyệt thử mở bài trực tiếp
    Given học viên có yêu cầu PENDING cho khóa
    When học viên gửi yêu cầu API truy cập bài bị hạn chế
    Then hệ thống từ chối cấp nội dung bị hạn chế

  Scenario: Học viên đã được duyệt hợp lệ
    Given học viên có đăng ký ACTIVE và đáp ứng điều kiện truy cập
    When học viên yêu cầu mở bài được phép
    Then hệ thống cho phép truy cập theo chính sách
~~~

Các tình huống chỉ là **quy tắc minh họa cần người nghiệp vụ xác nhận**. Gherkin giúp các bên có cùng cách hiểu; test thực thi ở tầng API/integration phù hợp mới xác minh rằng quyền được kiểm soát đúng.

### 21.5. Thế nào là cải tiến thành công?

Không phải “từ nay mọi người nói nhiều hơn”. Bằng chứng có thể gồm:

- Người có chuyên môn phù hợp **được mời góp ý trước quyết định**, dù ở múi giờ khác.
- Những câu hỏi liên quan quyền, dữ liệu hoặc DoD **có người xử lý và kết luận**.
- Rủi ro quan trọng được phát hiện **trước khi code hoặc rollout**.
- Ít làm lại do hiểu sai quy tắc, nhưng không tăng hàng đợi quyết định vô ích.
- Thành viên tự nguyện phản hồi rằng **họ có thể nêu bất đồng mà không bị công kích**.

Nếu lỗi production giảm nhưng thành viên vẫn sợ phản ánh, nhóm cần tiếp tục cải thiện cơ chế an toàn. Nếu cảm giác an toàn tốt hơn nhưng hành vi trái quyền vẫn xuất hiện, nhóm phải tiếp tục nâng chất lượng kỹ thuật. **Cả hai mục tiêu đều cần thiết**.

## 22. Những phản mẫu dễ làm giảm an toàn tâm lý và sự công bằng

| Phản mẫu | Vì sao gây hại | Hướng cải thiện |
| --- | --- | --- |
| **“Ai cũng có quyền nói” nhưng quyết định đã chốt trước** | Cơ hội đóng góp chỉ mang tính hình thức | Mời phản hồi trước mốc quyết định, ghi disposition |
| **Người ở cùng phòng quyết hộ người từ xa** | Thông tin ngầm trở thành quyền lực | Dùng tài liệu chung và decision log |
| **Luôn họp theo giờ trụ sở** | Một vùng phải gánh ngoài giờ kéo dài | Luân phiên, async-first, rút ngắn phần đồng bộ |
| **Bắt buộc bật camera để chứng minh tham gia** | Có thể loại trừ người có hạn chế kết nối/riêng tư | Cho nhiều hình thức đóng góp |
| **Lấy số lần nói làm thước đo hiệu quả** | Thưởng cho người nói nhiều, phạt người suy nghĩ sâu | Xem chất lượng đóng góp và ảnh hưởng thực tế |
| **Không ai phản hồi câu hỏi từ xa** | Người nêu học rằng ý kiến không có giá trị | Gắn owner trả lời và hạn xử lý |
| **Chat riêng chứa quyết định quan trọng** | Thành viên ngoài nhóm nhỏ mất ngữ cảnh | Tóm tắt về kênh/chỗ ghi quyết định chính |
| **Đồng ý im lặng mặc định** | Người vắng họp hoặc ngoài giờ bị coi là đã chấp thuận | Có quy tắc phản hồi và ngoại lệ cho rủi ro cao |
| **Code review công kích cá nhân** | Làm người khác tránh đưa mã và nêu câu hỏi | Phản hồi dựa trên hành vi, tiêu chuẩn và test |
| **Mọi góp ý đều được gọi là blocking** | Quyền review thành áp lực và sở thích cá nhân | Phân biệt yêu cầu bắt buộc với gợi ý |
| **Retrospective thành họp truy lỗi cá nhân** | Thành viên giấu vấn đề và near miss | Điều tra điều kiện hệ thống, chọn action có bằng chứng |
| **Khảo sát “ẩn danh” trong nhóm rất nhỏ** | Người trả lời dễ bị nhận diện | Giảm thu thập, giải thích giới hạn riêng tư |
| **Bắt mọi người kể chuyện nhạy cảm trong Retro** | Gây thêm tổn hại và mất niềm tin | Kênh riêng và quy trình có thẩm quyền |
| **Chỉ tập trung tâm trạng, bỏ trách nhiệm** | Rủi ro chất lượng không được xử lý | Kết hợp an toàn với DoD, hành vi và quyết định rõ |
| **Cố đạt consensus tuyệt đối mọi việc** | Quyết định chậm, thiếu quyền chốt | Minh bạch phân quyền và điều kiện xem lại |
| **Quá nhiều cuộc họp “để công bằng”** | Người ở xa kiệt sức và ít thời gian deep work | Gửi ngữ cảnh async, chỉ họp khi cần trao đổi thật |
| **Giao việc lõi chỉ cho người ở trụ sở** | Cơ hội học và ảnh hưởng bất cân xứng | Ownership có chủ đích, mentoring và luân phiên phù hợp |
| **Coi sự khác biệt quan điểm là thiếu tinh thần đội nhóm** | Mất phản biện, nhóm dễ đồng thuận giả | Khuyến khích phản biện bằng bằng chứng |
| **Không có quy trình chống trả đũa** | Người chịu ảnh hưởng không dám phản ánh | Kênh xử lý riêng, bảo vệ thông tin và quyền |
| **Dùng khảo sát để xếp hạng người quản lý/nhân viên** | Phản hồi bị méo, rủi ro riêng tư tăng | Dùng chỉ báo để cải thiện hệ thống, không chấm cá nhân |

## 23. Bài thực hành: thiết kế một Sprint Planning công bằng cho nhóm phân tán

### 23.1. Bối cảnh

Một Scrum Team gồm chín người phát triển nền tảng học. Một nửa thành viên làm việc ở cùng văn phòng, những người còn lại phân tán ở các địa điểm có giờ làm ít chồng lấn. Sprint vừa qua:

1. Hai PBI phải làm lại vì acceptance criteria về quyền học chưa rõ.
2. Một tester từ xa gửi cảnh báo qua chat nhưng không ai trả lời trước khi merge.
3. Một Developer mới nói rằng họ chỉ được mời vào cuộc họp sau khi kiến trúc đã quyết định.
4. Sprint Planning luôn diễn ra vào thời gian bất lợi cho cùng một nhóm nhỏ.
5. Người cùng văn phòng trao đổi miệng, không ghi lý do chọn giải pháp.
6. Khi thảo luận trực tiếp, một thành viên có thâm niên thường ngắt lời người khác.
7. Scrum Team muốn giữ Sprint Goal và DoD, nhưng không muốn tăng số giờ họp.

### 23.2. Nhiệm vụ

1. Phân biệt **ít nhất ba vấn đề về an toàn tâm lý** và **ba rào cản cơ hội đóng góp công bằng** trong bối cảnh.
2. Đề xuất **Working Agreement** có tối thiểu sáu hành vi quan sát được.
3. Thiết kế Sprint Planning gồm các phần **trước họp – trong họp – sau họp**.
4. Phác thảo một **RFC/decision log** cho quy tắc cấp quyền PENDING/ACTIVE.
5. Xác định **ai có quyền quyết định nghiệp vụ, ai quyết định giải pháp kỹ thuật và ai bảo đảm chất lượng** trong Scrum.
6. Nêu cách xử lý khi tester báo một nguy cơ cấp quyền trái phép **ngay trước khi release**, không chờ Retrospective.
7. Đề xuất một cách **luân phiên gánh nặng múi giờ** mà không ép mọi người thường xuyên làm ngoài giờ.
8. Viết ba câu hỏi khảo sát tự nguyện và một quy tắc **bảo vệ riêng tư** của nhóm nhỏ.
9. Chọn một thử nghiệm cải tiến trong hai Sprint: giả thuyết, owner, baseline, outcome và guardrail.
10. Nếu sau thử mọi người gửi nhiều bình luận hơn nhưng lead time tăng và vẫn có phản hồi bị bỏ qua, nhóm cần làm gì?

### 23.3. Gợi ý lời giải – vấn đề và cơ chế

**Về an toàn tâm lý:** hành vi ngắt lời gây khó nêu bất đồng; tester thấy cảnh báo không được xem xét; thành viên mới có thể ngại nói vì quyết định đã được người có thâm niên chốt trước. Không nên quy kết ngay rằng người bị ngắt lời “nhút nhát”.

**Về cơ hội công bằng:** lịch họp làm một nhóm phải gánh ngoài giờ; quyết định miệng không có bản ghi cho người ở xa; quy trình mời góp ý đến sau khi chốt; kênh chat không có owner xử lý phản biện.

**Working Agreement ứng viên:**

- Mọi PBI có rủi ro quyền/dữ liệu phải có ví dụ chấp nhận rõ trước khi triển khai.
- Đề xuất quan trọng được gửi dưới dạng tài liệu chung trước thời điểm chốt.
- Có người theo dõi và trả lời bình luận còn mở, kể cả bình luận ở ngoài cuộc họp.
- Người điều phối không cho một người chiếm mọi lượt, có quyền bỏ lượt khi được mời.
- Bất đồng được giải thích theo dữ liệu và tiêu chuẩn, không công kích con người.
- Cuộc họp quan trọng được chọn trong giờ chồng lấn hoặc luân phiên phù hợp; không mặc định làm ngoài giờ.
- Quyết định được ghi lại: người chốt, lý do, rủi ro và điều kiện xem lại.
- Khi có rủi ro an toàn/bảo mật, dùng kênh sự cố chuyên biệt ngay.

### 23.4. Gợi ý thiết kế Sprint Planning

**Trước:** Product Owner cung cấp các PBI ưu tiên, Product Goal liên quan, tiêu chí chấp nhận/điểm chưa rõ; Developers nêu phụ thuộc và rủi ro trong tài liệu chung. Mọi thành viên có cơ hội gửi câu hỏi theo múi giờ của họ. Nếu cần trao đổi riêng, kết luận được ghi lại.

**Trong:** Scrum Team thảo luận Sprint Goal và các PBI phù hợp. Người điều phối gọi đúng chuyên gia khi gặp rủi ro quyền/dữ liệu, theo dõi chat và cho thời gian viết ngắn. Developers cùng quyết định cách tạo Increment và điều chỉnh kế hoạch theo năng lực thực tế. Không bắt người từ xa phải phản ứng lập tức nếu câu hỏi cần đọc dữ liệu.

**Sau:** công khai Sprint Goal, Sprint Backlog, các phụ thuộc và quyết định còn mở; ghi người chịu trách nhiệm trả lời những câu hỏi chưa rõ cùng thời điểm cần chốt. Nếu phát hiện thay đổi trong Sprint, nhóm kiểm tra lại và thích ứng theo Scrum.

### 23.5. Ví dụ bản ghi quyền truy cập

~~~text
Vấn đề: Học viên đã gửi yêu cầu khóa cần duyệt nhưng chưa ACTIVE.
Quy tắc nghiệp vụ cần xác nhận: PENDING không cấp quyền nội dung hạn chế.
Ý kiến tester: Phải kiểm tra API truy cập trực tiếp, không chỉ ẩn nút UI.
Kỹ thuật cần xác minh: Authorization ở máy chủ và test tích hợp.
Người chốt nghiệp vụ: Product Owner/đại diện nghiệp vụ có quyền.
Người chịu trách nhiệm thiết kế/triển khai: Developers.
Tiêu chí chất lượng: Increment đáp ứng DoD; không cấp sai quyền.
Trạng thái: Chưa chốt nếu còn rủi ro bắt buộc cần xác minh.
~~~

**Khi phát hiện nguy cơ ngay trước release:** phải báo và xử lý qua kênh phù hợp, xác nhận ảnh hưởng, kiểm thử, giới hạn hoặc dừng rollout khi cần. **Sprint Retrospective chỉ là nơi rút kinh nghiệm sau đó**, không thay ứng phó an toàn.

### 23.6. Thử nghiệm và đo kết quả

**Giả thuyết:** trong hai Sprint, nếu các quyết định liên quan quyền/dữ liệu có bản đề xuất và cửa sổ phản hồi trước khi chốt, sẽ giảm những lần làm lại do thiếu ý kiến liên quan mà không làm tăng thời gian chờ đáng kể.

**Baseline:** xem số quyết định gần đây không có tài liệu trước họp, số phản biện bị bỏ qua và thời gian chờ quyết định, với các định nghĩa rõ.

**Owner:** một Developer đầu mối, phối hợp Product Owner, tester, Scrum Master và người có thẩm quyền liên quan.

**Outcome:** những rủi ro quan trọng được nêu và xử lý trước code/rollout; giảm rework do sai quy tắc. **Guardrail:** không tăng lead time không cần thiết, không làm ngoài giờ quá mức, không bỏ các kiểm thử DoD bắt buộc.

**Nếu bình luận tăng nhưng vấn đề chưa giảm:** tìm xem phản hồi có được trả lời/chuyển thành quyết định không, quy trình có tạo quá nhiều tài liệu, liệu thiếu quyền chốt hoặc thời gian đọc có phải nút thắt. Chỉ tăng số tin nhắn **không phải bằng chứng về công bằng**; điều chỉnh phạm vi và chính sách trước khi mở rộng.

## 24. Checklist duy trì an toàn tâm lý và cơ hội đóng góp công bằng

- [ ] Nhóm hiểu **an toàn tâm lý là có thể đặt câu hỏi, nêu lỗi, phản biện mà không bị làm nhục**, không phải tránh mọi bất đồng?
- [ ] Có phân biệt **được nói, được nghe, được xem xét và có thể ảnh hưởng đến quyết định**?
- [ ] Working Agreement có hành vi cụ thể, được đồng thuận và xem lại định kỳ?
- [ ] Người ở các múi giờ có **cửa sổ phản hồi đủ dùng trước quyết định quan trọng**?
- [ ] Quyết định không bị chốt hoàn toàn trong cuộc trò chuyện ngoài luồng của nhóm cùng văn phòng?
- [ ] Tài liệu, bản ghi và board ở nơi mọi người có quyền truy cập phù hợp?
- [ ] Lịch họp và gánh nặng ngoài giờ được phân bổ minh bạch, không mặc định một vùng hi sinh?
- [ ] Cuộc họp có agenda, mục tiêu, người điều phối, kênh bình luận và kết luận?
- [ ] Người tham gia từ xa nghe/đọc được cùng thông tin và có cách góp ý không phải video?
- [ ] Không ép bật camera hoặc dùng thời lượng nói làm điểm đánh giá cá nhân?
- [ ] Ngôn ngữ, thuật ngữ và tài liệu đủ rõ để người dùng ngôn ngữ thứ hai theo kịp?
- [ ] Một câu hỏi chưa rõ về quyền, dữ liệu hoặc API có owner xử lý trước khi triển khai?
- [ ] Người có quyền quyết định được nêu rõ; ý kiến phản biện được phản hồi bằng bằng chứng và lý do?
- [ ] Code review tập trung hành vi, rủi ro và chất lượng, phân biệt Blocking/Question/Suggestion?
- [ ] Thành viên mới có tài liệu onboarding, người hỗ trợ và cơ hội đóng góp vào phần việc có ý nghĩa?
- [ ] Các thành viên có thể báo **near miss, lỗi và blocker** sớm mà không bị công kích cá nhân?
- [ ] Có kênh riêng và quy trình có thẩm quyền cho hành vi quấy rối, trả đũa hoặc vấn đề nhạy cảm?
- [ ] Không hứa ẩn danh/bảo mật tuyệt đối nếu điều kiện thực tế không bảo đảm?
- [ ] Các Scrum events vẫn phục vụ **minh bạch, kiểm tra và thích ứng**, không thành điểm danh?
- [ ] Kanban board, WIP và policy giúp người ở xa nhìn được tình trạng thật, không phụ thuộc thông tin miệng?
- [ ] TDD, ATDD, CI và DoD cung cấp bằng chứng khách quan cho bất đồng kỹ thuật?
- [ ] Pulse survey và dữ liệu tham gia được dùng **tự nguyện, bảo vệ riêng tư, không xếp hạng cá nhân**?
- [ ] Khi cải thiện cách góp ý, nhóm theo dõi cả **chất lượng quyết định, lead time và outcome/guardrail**?
- [ ] Hành động cải tiến có owner, mốc xem lại, bằng chứng và quyết định giữ/đổi/dừng?
- [ ] Những người trước đây ít có cơ hội phát biểu **thực sự thấy ý kiến được xem xét và phản hồi**, không chỉ được mời thêm cuộc họp?

**Ghi nhớ:** Nhóm Agile phân tán cần **an toàn tâm lý để sự thật và rủi ro được nói ra**, đồng thời cần **cơ hội đóng góp công bằng để những thông tin ấy có thể tác động tới công việc và quyết định**. Điều này được tạo bởi những thực hành hằng ngày: lịch phối hợp bền vững, phản hồi bất đồng bộ có trách nhiệm, họp có điều phối, quyết định minh bạch, code review tôn trọng và đường xử lý riêng cho vấn đề nhạy cảm. Khi kết hợp với **Scrum, Kanban, XP, DoD và cải tiến liên tục**, nhóm có thể nhận phản hồi sớm, phát triển Increment an toàn và giữ nhịp cộng tác hiệu quả **mà không phụ thuộc vào việc mọi người phải cùng ngồi trong một phòng**.
