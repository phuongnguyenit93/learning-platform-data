# Đo thời gian dẫn (lead time) và xác định ranh giới đo

## 1. Tại sao đo lead time quan trọng trong Agile?

Một học viên phản hồi rằng khi quay lại nền tảng học trực tuyến, họ khó tìm đúng bài tiếp theo. Product Owner ghi nhận yêu cầu ngày 2/11. Developers bắt đầu phát triển ngày 5/11, hoàn thành và xác minh Increment ngày 10/11, nhưng tính năng tới ngày 12/11 mới được cung cấp cho học viên. Nhóm báo cáo “chỉ mất năm ngày làm việc để phát triển” trong khi người yêu cầu cảm thấy phải chờ lâu hơn.

Ai đúng? Cả hai có thể đang nhìn những khoảng thời gian **khác nhau**. Người học quan tâm thời gian từ lúc nhu cầu được ghi nhận đến lúc có thể sử dụng. Developers quan tâm thời gian từ khi bắt đầu triển khai đến khi công việc đạt tiêu chí hoàn tất. Nếu không nói rõ điểm bắt đầu và điểm kết thúc, chỉ số **lead time** rất dễ bị dùng sai.

**Lead time (thời gian dẫn)** trong phát triển phần mềm thường diễn tả **thời gian đã trôi qua giữa một sự kiện yêu cầu/đưa công việc vào phạm vi phục vụ và sự kiện giao kết quả**, với ranh giới phải được công bố rõ. Nó giúp trả lời: **“Từ khi có nhu cầu được tính vào luồng đến khi người nhận có kết quả, phải chờ bao lâu?”**

Đo lead time có ích vì:

- Bộc lộ **thời gian chờ** giữa các bước mà số giờ lập trình không cho thấy.
- Giúp người yêu cầu hiểu mức độ tin cậy của thời gian giao kết quả.
- Cho nhóm nhận ra các **điểm nghẽn** như backlog chờ quyết định, code review, kiểm thử tích hợp hoặc phát hành.
- Hỗ trợ **dự báo có xác suất** dựa trên dữ liệu, thay vì hứa chắc ngày giao cho từng story.
- Cho phép kiểm tra liệu cải tiến WIP, slicing, CI và cộng tác nghiệp vụ có làm giá trị đến sớm hơn không.

Trong phạm vi **AGILE_DEVELOPMENT**, lead time không phải điểm số để xếp hạng nhân viên. Nó là **chỉ báo của cả hệ thống giao giá trị**, kết hợp với user story, Product Backlog, Scrum, Kanban, XP và phản hồi người dùng.

> **Ghi nhớ ngay từ đầu:** Con số “lead time = 10 ngày” chưa đủ thông tin. Cần ghi **10 ngày kể từ sự kiện nào, đến sự kiện nào, theo ngày lịch hay ngày làm việc, cho loại hạng mục nào và trong khoảng quan sát nào**.

## 2. Phân biệt lead time, cycle time và những loại thời gian khác

Không có một cách dùng thuật ngữ giống hệt nhau ở mọi tổ chức. Điều có thể giữ nhất quán là **định nghĩa mốc đo theo câu hỏi cần trả lời**.

| Chỉ số | Ranh giới điển hình | Câu hỏi giúp trả lời |
| --- | --- | --- |
| **Customer/request lead time** | Yêu cầu được ghi nhận hoặc chấp nhận theo chính sách → kết quả tới người nhận | Người yêu cầu phải chờ bao lâu? |
| **Commitment-to-delivery lead time** | Nhóm chấp nhận cam kết phục vụ một hạng mục → kết quả được giao | Khi đã nhận việc vào hệ thống cam kết, mất bao lâu để giao? |
| **Cycle time** | Công việc bắt đầu thực hiện → trạng thái Done được định nghĩa | Việc đang thực hiện đi tới hoàn tất mất bao lâu? |
| **Active/touch time** | Tổng các khoảng thời gian thực sự thao tác, điều tra, thiết kế, kiểm thử | Thời gian xử lý trực tiếp là bao nhiêu? |
| **Waiting/blocked time** | Những khoảng chờ quyết định, review, môi trường hoặc phụ thuộc | Công việc mắc trong hàng đợi ở đâu? |
| **Time to restore service** | Sự cố bắt đầu hoặc được phát hiện theo quy ước → dịch vụ được khôi phục | Hệ thống phục hồi nhanh đến mức nào? |
| **Lead time for changes** | Thay đổi mã được commit → chạy trên production theo quy ước đo | Đường đi từ thay đổi kỹ thuật đến triển khai nhanh ra sao? |
| **Time to value/outcome** | Nhu cầu hoặc đầu tư → lợi ích thực tế có bằng chứng | Khi nào người dùng thật sự đạt kết quả? |

### 2.1. Lead time không luôn bắt đầu khi lập trình

Một yêu cầu có thể được nhận từ khách hàng ngày thứ Hai nhưng nằm chờ phân loại, ưu tiên và làm rõ đến thứ Năm. Nếu chỉ tính từ khi Developers chuyển ticket sang “In Progress”, nhóm đã **bỏ qua khoảng người yêu cầu đang chờ**. Con số đó có thể là cycle time hữu ích, nhưng không nên gắn nhãn “thời gian từ yêu cầu đến giao” nếu ranh giới thực tế không bao gồm khâu chờ.

### 2.2. Cycle time cũng cần một mốc Done

Nhóm A dừng đồng hồ khi PR được merge. Nhóm B dừng khi Increment đạt Definition of Done. Nhóm C dừng khi phát hành. Dù cả ba gọi chỉ số là cycle time, **dữ liệu không thể so sánh trực tiếp**. Mỗi nhóm cần đặt tên rõ, chẳng hạn “development-to-DoD cycle time” hoặc “work-start-to-release cycle time”.

### 2.3. Lead time for changes không phải lead time của user story

Trong đo lường delivery kỹ thuật, một chỉ số thường gặp là **lead time for changes**: thời gian từ khi mã thay đổi được commit đến khi thay đổi đó có mặt trên production. Đây là một góc nhìn quan trọng của đường đi CI/CD, nhưng **không bao gồm thời gian khám phá nhu cầu, chờ Product Backlog hoặc làm rõ yêu cầu trước commit**.

Nếu một user story mất 20 ngày từ lúc tiếp nhận đến khi học viên sử dụng, còn mã đi từ commit tới production chỉ hai giờ, hai số liệu **không mâu thuẫn**. Chúng soi hai đoạn khác nhau của cùng hệ thống.

### 2.4. Lead time chưa chứng minh sản phẩm có giá trị

Giao nhanh một tính năng không ai dùng có thể cho lead time rất ngắn nhưng outcome kém. Vì vậy, cần theo dõi thêm **tỷ lệ học viên hoàn thành hành trình, chất lượng, lỗi sau phát hành hoặc guardrail**. Tốc độ là phương tiện giúp học hỏi và giao giá trị, không phải kết quả cuối cùng.

## 3. Chọn câu hỏi đo trước khi chọn mốc trên bảng công việc

Thay vì nhìn bảng Jira/Trello rồi chọn bừa hai trạng thái có sẵn, hãy viết **câu hỏi ra quyết định** trước.

| Câu hỏi | Ranh giới đo ứng viên | Người thường cần thông tin |
| --- | --- | --- |
| “Học viên phải chờ bao lâu từ lúc gửi yêu cầu cải tiến?” | Yêu cầu hợp lệ được tiếp nhận → khả năng có thể sử dụng | Product Owner, stakeholder, người dùng |
| “Sau khi chúng ta nhận làm, bao lâu mới giao?” | Commitment point → giao kết quả | Scrum Team, nhóm dịch vụ, stakeholder |
| “Các PBI đã bắt đầu có bị mắc kẹt quá lâu?” | Bắt đầu thực hiện → Done | Developers, người điều phối dòng công việc |
| “Chậm do review và test hay do viết mã?” | Timestamps vào/ra từng trạng thái | Developers, QA, nhóm vận hành |
| “CI/CD chậm ở đâu?” | Commit → production | Nhóm kỹ thuật và nền tảng |
| “Lần thử nghiệm tính năng tới người dùng nhanh hay chậm?” | Quyết định bắt đầu thử → cohort được tiếp cận | Product Owner, nhóm discovery/delivery |

**Một hệ thống có thể đo nhiều loại thời gian** nếu mỗi loại có mục đích và tên rõ. Không nên tạo một số “lead time tổng hợp” rồi thay đổi điểm đầu/cuối tùy lần báo cáo.

### Chọn một loại việc đủ đồng nhất

Một bug khẩn, một PBI phát triển tính năng, một spike nghiên cứu và một nhiệm vụ di chuyển dữ liệu có thể đi qua **các luồng và chính sách khác nhau**. Nếu trộn tất cả, phân phối lead time khó diễn giải.

Nên bắt đầu với một phân khúc rõ, ví dụ “user story phát triển tính năng tiêu chuẩn hoàn tất trong quý”, sau đó bổ sung các loại việc khác với ranh giới phù hợp. **Không cần mọi loại việc cùng một SLE**.

## 4. Bốn điểm bắt đầu thường gặp và hệ quả của chúng

Một yêu cầu có thể trải qua nhiều cột trước khi Developers bắt tay làm.

| Điểm bắt đầu | Ý nghĩa | Điều được bao gồm | Rủi ro diễn giải |
| --- | --- | --- | --- |
| **Request created** | Người dùng hoặc stakeholder gửi/ghi nhận nhu cầu | Chờ phân loại, nghiên cứu, ưu tiên và triển khai | Các yêu cầu không bao giờ được chọn làm có thể nằm rất lâu; cần phân loại kết quả |
| **Request accepted for service** | Nhóm xác định yêu cầu hợp lệ và đưa vào phạm vi phục vụ | Chờ ưu tiên và thực hiện theo chính sách tiếp nhận | Cần quy tắc acceptance rõ, tránh giữ yêu cầu ngoài hệ thống |
| **Commitment point** | Nhóm chấp nhận trách nhiệm giao một hạng mục trong luồng | Chờ nội bộ sau cam kết, xử lý và bàn giao | Không đại diện toàn bộ thời gian người yêu cầu đã chờ trước cam kết |
| **Work started** | Hạng mục được kéo vào trạng thái đang thực hiện thực sự | Thực hiện, review, test và chờ sau khi bắt đầu | Đo cycle time, bỏ qua toàn bộ hàng đợi trước khi bắt đầu |

Không có điểm đầu nào “đúng nhất” cho mọi mục đích. Ví dụ, một nhóm hỗ trợ có trách nhiệm phản hồi từ lúc nhận yêu cầu nên **request-created lead time** hữu ích. Một đội sản phẩm có hàng nghìn ý tưởng chưa được quyết định có thể cần đo riêng **intake-to-decision** và **commitment-to-delivery**, thay vì gọi tất cả ý tưởng chưa ưu tiên là công việc đang chậm.

### Cam kết (commitment) là một chính sách, không phải nhãn tuỳ ý

Trong hệ thống Kanban, commitment point thường là thời điểm một yêu cầu **được chấp nhận để đưa vào hệ thống phục vụ**. Một nhóm có thể chọn điểm đó ở bước “Ready for Delivery”, một nhóm khác chọn “Selected/Committed”. Quan trọng là các bên biết **ý nghĩa của việc đã chấp nhận làm** và việc đo không bị đổi ngầm để làm số liệu đẹp.

### Tránh đặt điểm bắt đầu quá muộn

Nếu Product Owner chỉ đưa hạng mục sang “Committed” sau khi code gần xong, thời gian đo sẽ rất ngắn nhưng **không cho biết người dùng đã chờ bao lâu**. Chính sách điểm đầu phải phản ánh sự kiện thật, có thể kiểm tra lại.

## 5. Điểm kết thúc: Done, sẵn sàng triển khai hay đã tới người dùng?

Một PBI có thể “xong code”, “qua test”, “đạt DoD”, “đã triển khai” hoặc “đã được học viên dùng”. Đây là những **sự kiện khác nhau**.

| Điểm kết thúc | Ý nghĩa thực tế | Dùng cho mục tiêu nào? |
| --- | --- | --- |
| **Coding complete** | Hoàn thành viết mã theo cách nhóm định nghĩa | Theo dõi một công đoạn; **không đủ** để báo giao giá trị |
| **Merged/integrated** | Mã được hợp nhất vào nhánh/bản tích hợp | Theo dõi integration và CI |
| **Increment đạt DoD** | Phần sản phẩm đạt tiêu chuẩn chất lượng chung, sử dụng được theo định nghĩa Scrum | Đo năng lực hoàn thành Increment |
| **Ready for deployment** | Đủ điều kiện chuẩn bị đưa lên môi trường đích theo chính sách | Theo dõi hàng đợi triển khai |
| **Deployed to production** | Phần mềm đã được triển khai lên production | Đo chuỗi delivery kỹ thuật |
| **Available to intended users** | Người dùng/cộng đồng mục tiêu thực sự có thể truy cập khả năng | Đo lead time giao khả năng cho người nhận |
| **Value/outcome observed** | Có bằng chứng người dùng đạt kết quả mong đợi | Đo tác động; không thay thế mốc delivery |

### Đạt DoD khác được phát hành

Trong Scrum, một Increment đáp ứng DoD phải ở trạng thái **sử dụng được**. Increment **có thể** được phát hành trước Sprint Review, nhưng tổ chức có thể lựa chọn thời điểm rollout. Nếu đã đạt DoD ngày thứ Ba mà đến thứ Năm mới bật cho người dùng, nhóm có thể đo:

- **Time to DoD**: xem tốc độ hoàn tất chất lượng.
- **Time to availability**: xem người dùng phải chờ tới khi dùng được.
- **Release waiting time**: xem phần chờ giữa DoD và availability.

Không nên coi việc bật tính năng chỉ cho nhân viên nội bộ là đã “available to intended users” nếu mục tiêu thực sự là học viên. Nếu đo theo **cohort được chọn**, cần ghi rõ cohort ấy.

### Feature flag và rollout dần

Một thay đổi có thể được deploy lên production nhưng feature flag vẫn tắt cho mọi học viên. Nếu mục tiêu đo là **thời gian từ yêu cầu tới lúc học viên dùng được**, mốc kết thúc **chưa xảy ra**. Nếu flag mở cho 5% học viên, tổ chức phải quyết định đang đo **first-user availability**, **target-cohort availability** hay **general availability**; các mốc này có thể khác nhau nhiều ngày.

## 6. Vẽ ranh giới lên dòng công việc có thật

Giả sử dòng công việc từ nhu cầu tới người dùng:

~~~mermaid
flowchart LR
    A["Request received"] --> B["Triage / discovery"]
    B --> C["Committed / Ready"]
    C --> D["In progress"]
    D --> E["Review / Test"]
    E --> F["Increment đạt DoD"]
    F --> G["Release queue"]
    G --> H["Available to users"]
    H --> I["Feedback / outcome"]
~~~

Để đo một cách có trách nhiệm:

1. Xác định **trạng thái tương ứng với sự kiện**, không chỉ tên cột hiển thị.
2. Ghi rõ thời điểm công việc **bắt đầu được tính** và **kết thúc được tính**.
3. Giữ các khoảng **chờ** trong dữ liệu nếu chúng thuộc ranh giới; không “tạm dừng đồng hồ” tùy ý.
4. Nếu công việc quay lại từ review/test sang development, giữ lịch sử các lần chuyển.
5. Nếu có công việc bị hủy hoặc không bao giờ được nhận làm, đánh dấu **kết quả riêng**, không giả vờ đó là delivery.

### Ví dụ ba chiếc đồng hồ trên cùng một luồng

~~~mermaid
flowchart TD
    A["2/11: nhận yêu cầu"] --> B["5/11: bắt đầu phát triển"]
    B --> C["10/11: Increment đạt DoD"]
    C --> D["12/11: học viên dùng được"]
    A -. "Lead time: request → available" .-> D
    B -. "Cycle time: start → DoD" .-> C
    C -. "Release waiting" .-> D
~~~

Vì điểm cuối khác nhau, **không được tự trừ hai chỉ số có ranh giới khác nhau** để kết luận lượng thời gian chờ. Nếu muốn phân rã lead time, các khoảng thành phần phải nối đúng các mốc với nhau.

## 7. Ví dụ tính lead time từng bước với thời điểm cụ thể

Các mốc sau **chỉ là ví dụ**; mọi timestamp được giả định vào 09:00 theo múi giờ Việt Nam (UTC+07:00), không có ngày nghỉ lễ trong khoảng quan sát.

| Sự kiện | Thời điểm minh họa | Ý nghĩa |
| --- | --- | --- |
| Yêu cầu được ghi nhận hợp lệ | Thứ Hai, **02/11/2026 09:00** | Request received |
| Được lựa chọn/cam kết phục vụ | Thứ Tư, **04/11/2026 09:00** | Commitment point |
| Developers bắt đầu thực hiện | Thứ Năm, **05/11/2026 09:00** | Work started |
| Increment đạt DoD | Thứ Ba, **10/11/2026 09:00** | Quality-complete |
| Học viên mục tiêu sử dụng được | Thứ Năm, **12/11/2026 09:00** | Available to users |

### 7.1. Tính theo ngày lịch (calendar days)

~~~text
Request → Available          = 02/11 → 12/11 = 10 ngày lịch
Commitment → Available       = 04/11 → 12/11 =  8 ngày lịch
Work started → Available     = 05/11 → 12/11 =  7 ngày lịch
Work started → DoD           = 05/11 → 10/11 =  5 ngày lịch
DoD → Available              = 10/11 → 12/11 =  2 ngày lịch
Request → Work started       = 02/11 → 05/11 =  3 ngày lịch
~~~

Nếu dùng **cùng điểm kết thúc là Available**, có thể phân rã:

~~~text
Lead time Request → Available
  = Thời gian trước khi bắt đầu
    + Thời gian từ bắt đầu đến Available
  = 3 + 7 = 10 ngày lịch
~~~

Nếu chọn điểm kết thúc là DoD, chuỗi khác:

~~~text
Request → DoD = 3 ngày trước bắt đầu + 5 ngày từ bắt đầu đến DoD
              = 8 ngày lịch
~~~

Đây là lý do **“mất 5 ngày làm việc” và “người học chờ 10 ngày” không nhất thiết mâu thuẫn**: một số có thể là thời gian tới DoD, số khác đo tới khả năng thực sự sử dụng được.

### 7.2. Ngày làm việc cho cùng ví dụ

Nếu quy tắc là chỉ tính **thứ Hai đến thứ Sáu** và mỗi mốc đúng 09:00, khoảng từ 02/11 đến 12/11 gồm **8 ngày làm việc theo độ dài thời gian**, thay vì 10 ngày lịch. Khoảng từ 05/11 đến 10/11 gồm **3 ngày làm việc**, thay vì 5 ngày lịch.

**Ngày làm việc** không nhất thiết là “giờ một lập trình viên thực sự viết mã”. Nó chỉ loại trừ những khoảng thời gian nằm ngoài lịch làm việc đã chọn. Nếu nhóm có ca trực, khách hàng toàn cầu hoặc ngày nghỉ lễ, cách tính phải điều chỉnh.

### 7.3. Đừng làm tròn mất độ chính xác

Nếu yêu cầu đến lúc 16:30 và được giao ngày hôm sau lúc 09:00, thời gian trôi qua không phải “hai ngày” chỉ vì có hai ngày xuất hiện trên lịch. Nên lưu **timestamp đầy đủ**, tính chênh lệch thời gian rồi mới làm tròn khi trình bày. Ngày lịch khác **số ngày có phát sinh một phần thời gian**.

## 8. Chọn đơn vị thời gian: calendar time, business time hay touch time?

| Đơn vị | Khi nào hữu ích | Cần ghi rõ |
| --- | --- | --- |
| **Giờ/ngày lịch** | Thể hiện thời gian người yêu cầu thực sự chờ; phù hợp service hoạt động liên tục | Múi giờ, thời điểm đầu/cuối, quy tắc đổi sang ngày |
| **Giờ/ngày làm việc** | Phân tích năng lực của nhóm có lịch làm việc xác định | Lịch làm việc, lễ/tết, ca trực và múi giờ |
| **Giờ xử lý chủ động (touch time)** | Tìm tỷ trọng thao tác so với chờ đợi | Cách ghi thời gian xử lý, tránh tự ước lượng thiếu căn cứ |
| **Số Sprint/tuần** | Thảo luận ở cấp kế hoạch dài hơn | Sprint có độ dài khác nhau thì không nên dùng như đơn vị thời gian tuyệt đối |

### Khi nào nên ưu tiên ngày lịch?

Nếu khách hàng gửi yêu cầu tối thứ Sáu và phải chờ đến thứ Hai, cuối tuần **vẫn là thời gian chờ thật của khách hàng**. Đối với dịch vụ số có người dùng mọi lúc, báo lead time bằng ngày lịch thường dễ giải thích hơn. Song song, nhóm vẫn có thể đo ngày làm việc để tìm vấn đề năng lực nội bộ.

### Không tự động loại thời gian bị chặn

Giả sử story chờ API của nhóm khác ba ngày. **Blocked time vẫn thuộc lead time**, vì người dùng vẫn đang chờ. Có thể tạo chỉ số riêng về blocked time để tìm nguyên nhân, nhưng không nên trừ nó khỏi lead time chính rồi báo “chúng ta giao nhanh” nếu nhu cầu thực tế chưa được phục vụ.

## 9. Thu dữ liệu bằng sự kiện và timestamp thay vì nhớ lại thời gian

Đo một lần có thể xem lịch sử trạng thái thủ công. Để theo dõi xu hướng, cần xác định **sự kiện đo có thể trích xuất đáng tin** từ công cụ quản lý công việc và triển khai.

### 9.1. Bộ trường tối thiểu

| Trường dữ liệu | Ý nghĩa | Quy tắc chất lượng |
| --- | --- | --- |
| **work_item_id** | Định danh ổn định của hạng mục | Không thay khi đổi tên story |
| **work_item_type** | Story, bug, spike, sự cố, nhiệm vụ khác | Không trộn tùy tiện các loại việc |
| **created_at/requested_at** | Thời điểm yêu cầu được ghi nhận | Là sự kiện thật, không sửa để làm số đẹp |
| **accepted_at/committed_at** | Thời điểm nhóm nhận trách nhiệm phục vụ | Cần chính sách commitment nhất quán |
| **started_at** | Thời điểm bắt đầu công việc theo định nghĩa | Không mặc định từ lúc ticket được gán |
| **done_at** | Thời điểm đạt DoD hoặc trạng thái hoàn tất đã định nghĩa | Phải có quy tắc Done kiểm chứng được |
| **available_at** | Thời điểm người dùng/cohort mục tiêu truy cập được | Không lấy deploy timestamp nếu feature còn tắt |
| **cancelled_at** | Hạng mục bị hủy/không tiếp tục | Phân loại riêng, không giả là delivered |
| **reopened events** | Lịch sử quay lại làm việc sau khi đóng | Không mất các lần mở/đóng trước |
| **blocked intervals** | Các khoảng bị chặn và lý do | Là thông tin bổ sung, không tự trừ khỏi lead time |
| **service/class-of-service** | Loại luồng hoặc mức phục vụ | Hỗ trợ phân tích riêng các loại công việc |

Nên lưu timestamps với múi giờ rõ ràng (thường dùng UTC trong hệ thống), chỉ đổi sang múi giờ địa phương khi trình bày. Nếu hai hệ thống có đồng hồ hoặc timezone khác nhau, cần kiểm tra trước khi tính.

### 9.2. Ví dụ sự kiện có thể lưu

~~~json
{
  "work_item_id": "LEARN-142",
  "work_item_type": "story",
  "event": "AVAILABLE_TO_TARGET_COHORT",
  "occurred_at": "2026-11-12T02:00:00Z",
  "scope": "learners-v1",
  "source": "release-management"
}
~~~

Timestamp UTC ở trên tương ứng **09:00 ngày 12/11/2026 tại UTC+07:00**. Đây chỉ là ví dụ về một mốc; một hạng mục còn cần các sự kiện bắt đầu và mốc trung gian nếu muốn đo nhiều đoạn khác nhau.

### 9.3. Đổi trạng thái bảng không luôn phản ánh sự kiện thực

Một người có thể kéo ticket sang Done sau hai ngày dù Increment đã hoàn tất trước đó; hoặc ticket được đánh Done khi QA chưa xong. Do đó, cần xem **chính sách cập nhật trạng thái**. Có thể nối dữ liệu work tracker với CI/release logs khi thích hợp, nhưng không tự cho rằng một commit hay deployment duy nhất luôn tương ứng một story.

### 9.4. Ví dụ tính bằng SQL (PostgreSQL)

Giả sử tổ chức đã có bảng dữ liệu phân tích riêng, một hàng ứng với một story đã được giao; các cột thời gian có kiểu **timestamptz**, được làm sạch theo ranh giới đã chọn.

~~~sql
-- Ví dụ minh họa: lead time từ yêu cầu đến available, theo ngày lịch
WITH delivered AS (
    SELECT
        work_item_id,
        EXTRACT(EPOCH FROM (available_at - requested_at))
            / 86400.0 AS lead_days
    FROM analytics_work_items
    WHERE work_item_type = 'story'
      AND requested_at IS NOT NULL
      AND available_at IS NOT NULL
      AND available_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND available_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
      AND available_at >= requested_at
)
SELECT
    COUNT(*) AS delivered_items,
    AVG(lead_days) AS mean_lead_days,
    PERCENTILE_CONT(0.50) WITHIN GROUP
        (ORDER BY lead_days) AS median_lead_days,
    PERCENTILE_DISC(0.85) WITHIN GROUP
        (ORDER BY lead_days) AS p85_discrete_lead_days
FROM delivered;
~~~

Đây là **mẫu logic phân tích**, không phải lệnh để chạy ngay trên mọi dự án. Nó cần đúng schema, xử lý hạng mục hủy/đóng lại, quyền truy cập và sự kiện availability đáng tin. **PERCENTILE_CONT** nội suy giữa các quan sát; **PERCENTILE_DISC** chọn một giá trị quan sát theo quy tắc phân vị rời rạc. Nếu công cụ sử dụng cách tính phân vị khác, kết quả có thể khác nhau một chút; cần ghi công thức.

## 10. Xử lý hạng mục hủy, mở lại, chia nhỏ và chuyển luồng

Chất lượng dữ liệu của lead time không chỉ ở timestamps. Các tình huống ngoại lệ có thể làm số liệu sai lớn nếu không có chính sách trước.

| Tình huống | Vấn đề | Chính sách đo minh bạch gợi ý |
| --- | --- | --- |
| **Hạng mục bị hủy trước khi giao** | Không có thời điểm delivered | Ghi kết quả Cancelled và thời gian tới quyết định hủy riêng; không xem là giao thành công |
| **Yêu cầu chưa được nhận làm** | Có thể chờ rất lâu trong intake | Theo dõi intake age và tỷ lệ quyết định; không dùng như cycle time của việc đã bắt đầu |
| **Hạng mục tách thành hai story** | Nguy cơ “đặt lại đồng hồ” mất thời gian chờ ban đầu | Giữ liên kết parent/child và định nghĩa khi nào nhu cầu gốc được phục vụ |
| **Gộp hai yêu cầu thành một PBI** | Hai người yêu cầu có hai mốc bắt đầu khác nhau | Lưu quan hệ yêu cầu nguồn; không giả định một mốc đại diện cho mọi người |
| **Reopen trước khi thật sự giao** | Trạng thái Done được đánh quá sớm | Định nghĩa sự kiện Done hợp lệ; giữ lịch sử và cập nhật mốc theo chính sách |
| **Lỗi phát hiện sau khi đã giao hợp lệ** | Có bug mới sau release | Ghi defect và ảnh hưởng, không âm thầm viết lại mọi lead time cũ |
| **Đổi mức ưu tiên hoặc đội phụ trách** | Sự kiện phục vụ thay đổi | Giữ yêu cầu gốc và lịch sử chuyển; phân tích chờ theo bước |
| **Feature được rollout theo cohort** | Có nhiều thời điểm khả dụng | Định nghĩa cohort đích hoặc đo riêng first/general availability |
| **Hotfix/expedite** | Luồng ưu tiên khác việc thông thường | Phân tích riêng class of service thay vì dùng nó làm chuẩn cho mọi story |

### 10.1. Hạng mục chưa hoàn tất không nên biến mất khỏi góc nhìn

Một bảng phân tích chỉ có các item đã Done có thể báo lead time rất đẹp trong lúc **nhiều item cũ đang mắc kẹt**. Cần xem thêm **work item age (tuổi công việc đang thực hiện)** và những yêu cầu chờ quyết định.

### 10.2. Reopen sau giao và sửa lỗi

Giả sử story đã đạt DoD, được người học dùng, sau đó một lỗi mới được phát hiện. Lead time lịch sử mô tả **thời điểm giao khả năng ban đầu**; defect sau giao cần được ghi ở hệ thống chất lượng, với lead time khắc phục riêng nếu phù hợp. Không nên sửa timestamp cũ để làm biến mất sự kiện đã xảy ra. Nếu trước đó đánh Done sai theo DoD, cần **đính chính dữ liệu và minh bạch lý do**.

## 11. Vì sao dùng trung bình chưa đủ để hiểu lead time?

Hai đội có cùng lead time trung bình nhưng trải nghiệm người yêu cầu có thể rất khác. Một số story đến rất nhanh, trong khi vài story bị kẹt nhiều tuần.

Giả sử tám user story cùng loại, đều đo **từ request accepted đến available**, theo ngày lịch:

| Story | Lead time |
| --- | ---: |
| A | 4 ngày |
| B | 6 ngày |
| C | 7 ngày |
| D | 8 ngày |
| E | 11 ngày |
| F | 13 ngày |
| G | 17 ngày |
| H | 22 ngày |

### 11.1. Trung bình và trung vị

~~~text
Các giá trị đã sắp xếp: 4, 6, 7, 8, 11, 13, 17, 22
Tổng = 88 ngày
Mean (trung bình) = 88 / 8 = 11 ngày
Median (trung vị) = (8 + 11) / 2 = 9,5 ngày
Min = 4 ngày
Max = 22 ngày
~~~

Trung bình **11 ngày** không có nghĩa một story mới “sẽ xong trong 11 ngày”. Nếu người yêu cầu tin chắc vào ngày 11, những hạng mục kéo dài 17–22 ngày có thể tạo bất ngờ lớn.

### 11.2. Phân vị và đuôi phân phối

Một phân vị giúp mô tả **bao nhiêu phần trăm hạng mục đã hoàn tất trong hoặc dưới ngưỡng thời gian**. Với cách tính phân vị rời rạc **nearest-rank** cho mẫu tám quan sát:

~~~text
P85: vị trí = ceil(0,85 × 8) = ceil(6,8) = 7
Giá trị ở vị trí thứ 7 trong dãy sắp xếp = 17 ngày
Số story có lead time ≤ 17 ngày = 7 / 8 = 87,5%
~~~

Như vậy, dữ liệu lịch sử nhỏ này cho thấy **7/8 story (87,5%)** được giao trong **17 ngày hoặc nhanh hơn**. Cách tính phân vị nội suy có thể cho con số khác, nên báo cáo cần công bố phương pháp tính.

**Cảnh báo quan trọng:** tám quan sát quá ít để ước lượng phân phối đáng tin cậy. Kết quả chỉ giúp học cách đọc số liệu, **không phải bằng chứng rằng 85% story tương lai chắc chắn xong trong 17 ngày**.

### 11.3. Những cách nhìn cần đi cùng nhau

| Cách nhìn | Lợi ích | Giới hạn |
| --- | --- | --- |
| **Trung bình** | Dễ theo dõi mức chung theo thời gian | Nhạy với hạng mục rất dài |
| **Trung vị** | Diễn tả một điểm giữa phân phối | Không nói rõ đuôi dài |
| **P85/P95 theo quy tắc đã chọn** | Hữu ích để thảo luận mức độ tin cậy và hạng mục chậm | Cần đủ dữ liệu, định nghĩa ổn định |
| **Histogram/phân phối** | Thấy cụm nhanh/chậm và đuôi phân phối | Ít mẫu dễ gây ngộ nhận |
| **Scatterplot theo ngày hoàn tất** | Nhìn xu hướng, outlier và thay đổi chính sách | Cần phân loại và chú thích sự kiện |
| **Tuổi hạng mục chưa Done** | Thấy rủi ro đang phát sinh trước khi hoàn tất | Không thể tính như lead time đã hoàn tất |

Một biểu đồ lead time nên có **đơn vị, ranh giới đo, loại việc, cửa sổ hoàn tất và số lượng mẫu**. Không đủ các thông tin ấy, biểu đồ có thể đẹp nhưng khó hỗ trợ quyết định.

## 12. Service Level Expectation: dùng lead time để dự báo có xác suất

Trong thực hành Kanban, **Service Level Expectation (SLE)** là kỳ vọng về thời gian một hạng mục có thể hoàn tất, thường diễn đạt bằng **một khoảng thời gian và một xác suất**. SLE giúp nhóm đối thoại về rủi ro thời gian, không phải cam kết tuyệt đối cho mọi hạng mục.

Ví dụ cách nói:

> “Với loại user story tiêu chuẩn đã được chấp nhận vào luồng và được giao cho cohort mục tiêu, chúng tôi kỳ vọng khoảng 85% hạng mục hoàn thành trong không quá 17 ngày lịch, theo dữ liệu và chính sách đo hiện tại.”

Đây là **mẫu phát biểu**, không phải SLE thực tế của một nhóm. Cần đủ dữ liệu cùng loại và kiểm tra tính ổn định trước khi công bố như kỳ vọng đáng tin.

### SLE phải gắn với cùng điểm bắt đầu và kết thúc

Nếu SLE được xây từ **started → Done**, không thể dùng nó trực tiếp để hứa **request created → production**. Cần đo thêm thời gian chờ trước khi start và các bước tới availability. SLE cũng không tự chuyển thành xác suất cho một epic lớn, một hotfix hoặc một spike có tính bất định khác hẳn.

### Dùng SLE với Work Item Age

Giả sử SLE lịch sử gợi ý khoảng 85% story tiêu chuẩn hoàn tất trong 17 ngày. Một story đang mở có **tuổi 15 ngày** (cùng ranh giới start với SLE) chưa Done. Nhóm có thể xem đây là **tín hiệu cần kiểm tra blocker và phạm vi**, không đợi tới khi nó vượt 17 ngày mới tìm hiểu.

Nhưng không được suy luận rằng story đó “chắc chắn còn hai ngày nữa” hoặc “vì đã qua 15 ngày nên chỉ còn hai ngày”. **Tuổi hiện tại và xác suất hoàn tất còn lại** cần dữ liệu về những item đang còn trong hệ thống và phân phối phù hợp; không thể lấy ngưỡng SLE trừ tuổi rồi coi là dự báo chắc chắn.

### Một quy ước theo dõi trực quan minh họa

| Tuổi hạng mục trong luồng đã chọn | Cách thảo luận |
| --- | --- |
| Nhỏ hơn phần lớn quan sát lịch sử | Theo dõi bình thường, tháo blocker khi có |
| Tiệm cận vùng đuôi phân phối | Hỏi phụ thuộc, kích thước, nguy cơ kéo dài và cách hỗ trợ |
| Vượt SLE đã thống nhất | Làm rõ nguyên nhân, trao đổi kỳ vọng và điều chỉnh kế hoạch |

Không nên dùng màu đỏ/đánh giá tiêu cực để **phạt một người phụ trách**. Hạng mục bị già thường phản ánh sự kết hợp của phạm vi, phụ thuộc, năng lực và chính sách hệ thống.

## 13. Work Item Age: thấy vấn đề trước khi item đạt Done

**Lead time của hạng mục đã giao** chỉ xuất hiện sau khi có sự kiện kết thúc. **Work Item Age** là thời gian từ **điểm bắt đầu được chọn** đến **thời điểm hiện tại** của hạng mục vẫn chưa hoàn tất.

Ví dụ:

~~~text
Story LEARN-231
Work started: 11/11/2026 09:00 +07
Thời điểm xem: 23/11/2026 09:00 +07
Work item age: 12 ngày lịch
Trạng thái: Review/Test, đang chờ môi trường tích hợp
~~~

Nếu nhóm chỉ xem những story đã hoàn thành, hạng mục này **chưa xuất hiện trong biểu đồ cycle time của việc Done**. Nhưng nó đã tồn tại 12 ngày và có thể còn già hơn nếu không gỡ trở ngại.

### Tuổi công việc không phải lead time cuối cùng

Khi chưa có mốc giao, không thể khẳng định lead time là 12 ngày. Ta chỉ biết **nếu giữ ranh giới từ lúc bắt đầu, lead time cuối cùng phải ít nhất bằng 12 ngày**; các ngày tiếp theo sẽ làm nó tăng. Điều đó quan trọng khi so sánh với SLE hoặc thời gian các hạng mục tương tự.

### Aging WIP giúp hỏi đúng câu hỏi

- Hạng mục có quá lớn và cần chia lát vẫn tạo được giá trị riêng không?
- Đang chờ kiểm tra quyền, database, approval hay môi trường?
- Có cách chuyển một người đang mở việc mới sang giúp hoàn tất item già không?
- Có thể giảm vòng bàn giao hay hợp nhất review không cần thiết không?
- Nếu phát hiện yêu cầu đã hết giá trị, ai quyết định hủy và ghi trạng thái minh bạch?

Không nên đóng ticket rồi mở ticket mới cùng nội dung **chỉ để reset tuổi**. Việc ấy che giấu dòng chảy thực tế và làm các số liệu kém tin cậy.

## 14. Tách thời gian thực hiện khỏi thời gian chờ để tìm điểm nghẽn

Một lead time dài có thể do công việc phức tạp, nhiều phụ thuộc, chờ phản hồi nghiệp vụ hoặc kiểm thử tích hợp. **Muốn cải tiến, cần phân tích từng đoạn trong ranh giới** thay vì chỉ thúc người viết code.

Giả sử một loại user story có lịch sử thời gian trung bình sau, **mỗi hàng mô tả những khoảng không chồng lấp nhau**:

| Đoạn trong lead time đã chọn | Thời gian xử lý chủ động | Thời gian chờ | Tổng |
| --- | ---: | ---: | ---: |
| Intake và làm rõ nhu cầu | 0,5 ngày | 3 ngày | 3,5 ngày |
| Chờ ưu tiên/năng lực rồi bắt đầu | 0 ngày | 4 ngày | 4 ngày |
| Phát triển và code review | 2 ngày | 2,5 ngày | 4,5 ngày |
| Kiểm thử tích hợp và hoàn thiện | 1 ngày | 2 ngày | 3 ngày |
| Từ DoD tới availability | 0,5 ngày | 1,5 ngày | 2 ngày |
| **Tổng** | **4 ngày** | **13 ngày** | **17 ngày** |

Theo giả định trên, **13/17 ngày (~76,5%)** được ghi nhận là thời gian chờ. Con số này chỉ mô tả mẫu minh họa; nó **không tự chứng minh 76,5% thời gian là lãng phí** vì một số thời gian chờ có thể liên quan nghĩa vụ hợp lệ hoặc giới hạn hạ tầng.

### Chọn nơi can thiệp có tác động

Nếu nhóm tối ưu một phép tính từ 2 giờ còn 1 giờ nhưng để story chờ năm ngày review, tác động lên lead time tổng thể có thể rất nhỏ. Nếu cải thiện cách chuẩn bị story, giảm WIP và tích hợp sớm giúp cắt vài ngày chờ, khách hàng có thể nhận giá trị nhanh hơn **mà không phải ép viết mã nhanh hoặc bỏ test**.

### Flow efficiency dùng thế nào?

Một cách tính trong phân tích dòng là:

~~~text
Flow efficiency = Thời gian được định nghĩa là hoạt động tạo giá trị
                  / Tổng thời gian trong cùng ranh giới
                  × 100%
~~~

Nếu dùng **touch time / elapsed time**, cần gọi đúng là tỷ lệ thời gian xử lý chủ động, không tự đồng nhất với tỷ lệ thời gian **thật sự tạo giá trị**. Kiểm thử bảo mật hoặc phê duyệt pháp lý có thể là điều kiện cần để bảo vệ giá trị dù không trực tiếp tạo thêm tính năng.

## 15. WIP, throughput và Little's Law liên quan thế nào?

Trong dòng công việc ổn định, **Little's Law** liên hệ số hạng mục trung bình trong hệ thống, thông lượng và thời gian trung bình ở trong hệ thống:

~~~text
Average WIP ≈ Average Throughput × Average Time in System

Tương đương:
Average Time in System ≈ Average WIP / Average Throughput
~~~

**Ví dụ:** một luồng đang thực hiện ổn định có **WIP trung bình = 9 item** và **throughput trung bình = 3 item/tuần**. Khi các điều kiện của hệ thống và ranh giới đo phù hợp, thời gian trung bình từ điểm vào WIP đến điểm ra xấp xỉ:

~~~text
9 item / (3 item/tuần) = 3 tuần/item
~~~

Đây là quan hệ giữa **trung bình**, không phải công thức hứa một PBI cụ thể sẽ xong sau ba tuần. Hệ thống không ổn định, thay đổi phạm vi lớn, có nhiều loại việc không đồng nhất hoặc số liệu thiếu có thể làm phép ước tính không đáng tin.

### Ranh giới của WIP phải khớp với ranh giới của thời gian

Nếu WIP chỉ tính các item **đã bắt đầu phát triển**, trong khi lead time bắt đầu từ **lúc khách hàng gửi yêu cầu**, không thể lấy WIP của development chia throughput rồi cho rằng đã tính **toàn bộ customer lead time**. Phải đo số item nằm **trong đúng phạm vi từ yêu cầu đến giao** hoặc dùng các đoạn luồng riêng.

### Tại sao hạn chế WIP có thể giảm thời gian chờ?

Nếu nhóm liên tục bắt đầu nhiều story nhưng không đủ người review/test, hàng đợi phát triển lớn dần. Giới hạn WIP và chính sách **hoàn tất trước khi bắt đầu thêm** có thể giúp giảm chuyển ngữ cảnh, giảm việc chờ và phát hiện lỗi tích hợp sớm. Nhưng hiệu quả cần được **đo lại**, không phải cứ áp một con số WIP nhỏ là lead time chắc chắn giảm.

### Throughput không đo giá trị một cách trực tiếp

Throughput là số item hoàn thành trong khoảng thời gian. Nếu nhóm chia hạng mục rất nhỏ chỉ để tăng số ticket Done, throughput có thể tăng mà **outcome người học không đổi**. Cần giữ chính sách slicing có ý nghĩa và dùng **lead time + chất lượng + outcome** cùng nhau.

## 16. Lead time trong Scrum, Kanban, XP và Lean

### 16.1. Với Scrum

Scrum không bắt buộc đội sử dụng một định nghĩa lead time hay một ngưỡng phân vị cụ thể. Tuy nhiên, số liệu dòng công việc có thể giúp:

- Product Owner xem thời gian từ một nhu cầu được chấp nhận tới Increment/khả năng được giao.
- Developers phát hiện thời gian chờ review, tích hợp và kiểm thử làm Sprint Goal gặp rủi ro.
- Scrum Team dùng Sprint Review để đối chiếu tốc độ giao với **outcome và phản hồi stakeholder**.
- Sprint Retrospective chọn cải tiến làm hệ thống ổn định hơn, thay vì chỉ tăng story point.

**DoD phải không đổi về ý nghĩa khi đo cùng một luồng.** Nếu hôm qua Done nghĩa là đã tích hợp và kiểm thử, hôm nay Done chỉ nghĩa là code complete, lead time giảm giả tạo và Increment chưa chắc dùng được.

Một Sprint có thể tạo nhiều Increment. Việc đo lead time **không bắt buộc** kết thúc vào cuối Sprint; Increment có thể được phát hành trước Sprint Review khi thích hợp.

### 16.2. Với Kanban

Kanban đặc biệt quan tâm tới **trực quan hóa luồng, giới hạn WIP, quản lý work item age, throughput và cycle time**. Nhóm có thể dùng **SLE** và biểu đồ phân tán để thấy thời gian hoàn tất, đồng thời quan sát hàng đợi để điều chỉnh chính sách.

Đừng đồng nhất “Kanban = không kế hoạch”. Dữ liệu lịch sử cùng chính sách làm việc có thể tạo **kỳ vọng giao hàng xác suất** tốt hơn cam kết cảm tính.

### 16.3. Với XP

Các thực hành như **TDD, CI, refactoring và tích hợp thường xuyên** giúp tìm lỗi sớm, giảm thời gian làm lại và tránh lô thay đổi lớn. Chúng có thể giảm một số đoạn trong cycle/lead time khi chất lượng tín hiệu tốt, nhưng hiệu quả phải được quan sát cả ở **dòng giá trị tổng thể**, không chỉ số test chạy hay số commit.

### 16.4. Với Lean

Lean thúc đẩy nhìn **end-to-end** và giảm công việc dở dang, chuyển tác vụ, bàn giao không cần thiết cùng thời gian chờ. Một nhóm backend tăng tốc gấp đôi nhưng QA trở thành hàng đợi dài thì **lead time của người dùng có thể không giảm**. Số liệu giúp nhận ra sự khác biệt giữa tối ưu cục bộ và cải thiện toàn hệ thống.

## 17. Thiết kế một thử nghiệm cải tiến lead time có trách nhiệm

Một chỉ số chỉ hữu ích khi dẫn tới **quyết định hoặc hành động có thể kiểm tra**.

### Ví dụ: giảm chờ code review

**Quan sát:** với các story tương tự trong bốn tuần, phần lớn thời gian sau khi code xong là chờ review. Nhiều Developers cùng lúc mở ba đến bốn PR. Các PR lớn khiến review lâu và thường phải chỉnh sửa nhiều vòng.

**Giả thuyết:** nếu chia thay đổi thành PR nhỏ hơn, giới hạn số story đang phát triển và ưu tiên review trước khi kéo việc mới, **request-to-available lead time sẽ giảm** mà không tăng lỗi hồi quy.

**Thử nghiệm:**

1. Ghi đường cơ sở: loại story, ranh giới đo, lead time, review waiting time, WIP và lỗi sau release.
2. Thống nhất chính sách: người đang rảnh ưu tiên giúp kết thúc PR đã mở trước khi kéo thêm story.
3. Chia một số story thành **lát giá trị dọc** đủ nhỏ, vẫn giữ DoD và acceptance criteria.
4. Trong giai đoạn thử, thu dữ liệu cùng cách đo; ghi các ngoại lệ như sự cố lớn hoặc thay đổi thành viên.
5. Xem kết quả theo **trung vị/phân vị, tuổi item đang dở, thời gian chờ và chất lượng**.
6. Giữ, chỉnh hoặc dừng chính sách nếu bằng chứng cho thấy lợi ích hoặc tác dụng phụ.

### Điều không nên làm

- Bỏ kiểm thử tích hợp để nhanh đưa ticket sang Done.
- Chia một story thành ba ticket “UI Done”, “API Done”, “DB Done” rồi tính ba lần giao giá trị khi hành trình chưa sử dụng được.
- Đổi điểm bắt đầu từ Request sang Work Started mà không đổi tên metric.
- Đẩy hạng mục khó sang cột “Waiting External” để loại chúng khỏi báo cáo.
- Chỉ so sánh trung bình của hai tuần có vài item rồi tuyên bố cải tiến đã chứng minh thành công.

### Luôn có guardrail

| Mục tiêu flow | Guardrail gợi ý |
| --- | --- |
| Giảm request-to-available lead time | Không tăng lỗi production và sự cố dữ liệu |
| Giảm thời gian review | Không giảm mức chất lượng review, không tạo PR khó bảo trì |
| Tăng tần suất release | Không cấp sai quyền hoặc làm mất tiến độ |
| Giảm WIP | Không bỏ mặc sự cố khẩn hoặc yêu cầu có hạn chót bắt buộc |
| Rút ngắn CI | Các kiểm thử bảo vệ rủi ro quan trọng vẫn được thực thi đáng tin |

## 18. Case study: hai đội nhìn cùng một tính năng nhưng báo lead time khác

### 18.1. Bối cảnh

Một nền tảng học trực tuyến có ba nhóm cùng tham gia lát “Tiếp tục học”:

- **Identity:** xác minh quyền học.
- **Learning:** cập nhật và đọc tiến độ.
- **Experience:** hiển thị nút và điều hướng.

Product Owner nhận yêu cầu từ học viên. Mỗi nhóm kỹ thuật báo task Done theo phần việc riêng. Tuy nhiên, hành trình thực tế chỉ có thể sử dụng khi ba phần được tích hợp và quyền truy cập được xác minh.

### 18.2. Dòng thời gian minh họa

| Mốc | Ngày | Quan sát |
| --- | --- | --- |
| Yêu cầu được tiếp nhận | 02/11 | Người dùng báo không tìm được bài tiếp theo |
| Làm rõ và xếp ưu tiên xong | 04/11 | Ba nhóm thống nhất acceptance criteria |
| Bắt đầu phát triển | 05/11 | Các nhóm tạo các task kỹ thuật |
| UI riêng lẻ báo code complete | 07/11 | Chưa tích hợp với quyền và tiến độ thật |
| Hành trình tích hợp đạt DoD | 10/11 | Quyền, tiến độ và UI hoạt động cùng nhau |
| Học viên mục tiêu sử dụng được | 12/11 | Feature được bật cho cohort đã xác định |

Nếu nhóm Experience báo **2 ngày từ 05/11 tới 07/11**, đó chỉ là **thời gian code complete cho một phần kỹ thuật**. Nếu cả sản phẩm báo **10 ngày từ 02/11 tới 12/11**, đó là **request-to-availability lead time của lát giá trị** trong ví dụ này.

Hai số có thể cùng đúng trong những ranh giới riêng. Sai lầm là **coi việc hoàn tất task của từng nhóm là hoàn tất user story ở mức sản phẩm**, hoặc cộng nhiều task thành nhiều Increment có giá trị độc lập.

### 18.3. Cùng một story có thể có nhiều “điểm đến”

Product Owner cần biết học viên đã **sử dụng được** hay chưa. Developers cần biết phần mềm đã **đạt DoD** và đang chờ rollout hay chưa. Nhóm vận hành quan tâm **deployment latency** và dữ liệu lỗi. Một dashboard có thể hiển thị cả ba, nhưng phải đặt nhãn đầy đủ:

- **Request → DoD**
- **DoD → Available**
- **Request → Available**

Ba chỉ số cùng mốc sẽ giúp phân rã tổng thời gian. Nếu muốn đo **bài học được mở thành công**, cần thêm outcome/telemetry; không thể suy từ việc flag đã bật.

### 18.4. Ví dụ tiêu chí chấp nhận làm rõ điểm hoàn tất

~~~gherkin
Feature: Tiếp tục học trên nhiều thiết bị

  Scenario: Học viên đủ điều kiện tiếp tục học
    Given học viên có quyền học khóa tuyến tính ba bài
    And học viên đã hoàn thành bài đầu theo quy tắc
    When học viên mở trang khóa và chọn "Tiếp tục học"
    Then hệ thống mở đúng bài thứ hai

  Scenario: Đã hoàn tất bài cuối
    Given học viên có quyền học và đã hoàn tất cả ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không điều hướng đến bài không tồn tại

  Scenario: Không có quyền học
    Given người dùng không có quyền truy cập nội dung khóa
    When người dùng gửi yêu cầu mở bài học trực tiếp
    Then hệ thống từ chối cấp nội dung bị hạn chế
~~~

Các tiêu chí này giúp xác định **Increment có hành vi dùng được**, nhưng riêng Gherkin không quyết định mốc availability; cần thêm bằng chứng rollout tới cohort mục tiêu. Chất lượng chung vẫn phải theo DoD.

## 19. Những phản mẫu khi sử dụng lead time

| Phản mẫu | Vì sao gây sai lệch | Cách làm tốt hơn |
| --- | --- | --- |
| **Báo lead time mà không nói mốc đầu/cuối** | Người nghe không biết đang đo điều gì | Ghi tên sự kiện, đơn vị, loại việc và cohort |
| **Đổi Work Started thành Created giữa hai kỳ** | Xu hướng không còn cùng định nghĩa | Giữ phiên bản metric hoặc tính lại lịch sử khi cần |
| **Chỉ đo item Done, bỏ qua item già đang dở** | Báo cáo đẹp khi hệ thống bị kẹt | Theo dõi Work Item Age và intake aging |
| **Bỏ thời gian blocked ra khỏi lead time** | Che phần thời gian khách hàng vẫn chờ | Giữ elapsed time, đo blocked time riêng |
| **Coi code complete là giao cho người dùng** | Bỏ qua tích hợp, DoD và phát hành | Chọn điểm cuối đúng mục tiêu đo |
| **Trộn bug khẩn với feature chuẩn** | Phân phối khó diễn giải | Phân đoạn theo loại việc/class of service |
| **Dùng mỗi trung bình** | Không thấy những item chậm ở đuôi | Xem trung vị, phân vị, phân phối và outlier |
| **Coi P85 là lời hứa ngày hoàn thành** | Quên tính xác suất và bất định của item cụ thể | Dùng SLE như kỳ vọng có điều kiện, trao đổi rủi ro |
| **Đếm item hủy là delivered** | Giảm lead time giả và sai throughput | Ghi cancellation với kết quả riêng |
| **Đóng/reopen ticket để reset đồng hồ** | Mất lịch sử nhu cầu và WIP | Giữ sự kiện gốc, ghi reopening minh bạch |
| **Chia ticket chỉ để tăng throughput** | Đo output giả thay vì giá trị | Bảo vệ lát giá trị end-to-end |
| **Lấy WIP phát triển chia throughput để tính request lead time** | Ranh giới WIP không khớp | Dùng cùng phạm vi hệ thống cho Little's Law |
| **So sánh các nhóm không cùng DoD** | Đội gắn Done sớm hơn có số đẹp giả | Thống nhất ý nghĩa Done trước khi so sánh |
| **Đặt mục tiêu giảm số ngày bằng mọi giá** | Có thể bỏ review, kiểm thử hoặc ghi nhận muộn | Kèm chất lượng và outcome làm guardrail |
| **Dùng lead time xếp hạng cá nhân** | Khuyến khích chọn việc dễ và che blocker | Đo hệ thống, cải thiện sự phối hợp |
| **Bỏ qua timezone hoặc giờ trong ngày** | Đếm nhầm ngày và thứ tự sự kiện | Lưu timestamp có múi giờ, tính elapsed time |
| **Dùng mẫu quá nhỏ để công bố SLE chắc chắn** | Phân vị nhiễu, dự báo thiếu cơ sở | Tăng số quan sát, làm rõ độ bất định |
| **Đo thay đổi kỹ thuật rồi gọi là thời gian người dùng chờ** | Commit-to-prod bỏ qua nhiều khâu trước commit | Đặt nhãn tách biệt change lead time và customer lead time |

## 20. Bài thực hành: xác định ranh giới và đưa ra dự báo có điều kiện

### 20.1. Bài toán

Một nhóm phát triển nền tảng học muốn đo tốc độ giao user story **từ khi được chấp nhận phục vụ đến khi học viên mục tiêu dùng được**. Những hạng mục đã hoàn tất có lead time theo ngày lịch:

~~~text
4, 6, 7, 8, 11, 13, 17, 22
~~~

Ngoài ra, một story mới có mốc:

~~~text
Request accepted : 02/11/2026 09:00 +07
Work started     : 05/11/2026 09:00 +07
DoD achieved     : 10/11/2026 09:00 +07
Available        : 12/11/2026 09:00 +07
~~~

Một story khác bắt đầu thực hiện ngày 11/11 nhưng **vẫn chưa Done** vào 23/11 lúc 09:00. Nhóm còn phát hiện sáu ticket phụ về UI, API và database đã “Done cục bộ” nhưng chưa tích hợp thành hành trình dùng được.

### 20.2. Nhiệm vụ

1. Định nghĩa chính xác **ranh giới** lead time phục vụ người yêu cầu, gồm sự kiện start/end và đơn vị.
2. Tính **request-to-available lead time**, **work-start-to-DoD cycle time** và **DoD-to-available waiting time** của story thứ nhất.
3. Giải thích vì sao **work-start-to-DoD** không thể được lấy trực tiếp làm thời gian chờ của học viên.
4. Tính **mean, median, P85 nearest-rank** cho tám hạng mục đã giao.
5. Viết một câu **SLE ứng viên** có xác suất, phạm vi và cảnh báo về độ tin cậy.
6. Tính **Work Item Age** của story thứ hai tại thời điểm quan sát; giải thích vì sao nó chưa có lead time cuối cùng.
7. Đề xuất cách xử lý **sáu ticket Done cục bộ** trong dashboard.
8. Nêu hai cách cải tiến dòng công việc, một **chỉ số chất lượng** và một **outcome** để kiểm tra hiệu quả.
9. Nếu một story bị hủy giữa chừng, bạn sẽ ghi trạng thái và đưa vào báo cáo thế nào?
10. Nếu Product Owner đổi điểm bắt đầu từ “Request accepted” sang “Work started”, những so sánh nào cần chú thích hoặc tính lại?

### 20.3. Đáp án và lời giải tham khảo

**Câu 1 – Ranh giới:** lead time đo từ **timestamp khi yêu cầu hợp lệ được chấp nhận phục vụ** tới **timestamp khả năng đã sẵn có cho cohort học viên được xác định**, tính bằng **ngày lịch theo thời gian đã trôi qua**. Những khoảng chờ trong phạm vi không bị loại trừ; nhóm báo riêng những chỉ số con khi cần.

**Câu 2 – Chênh lệch:**

~~~text
Request accepted → Available = 10 ngày lịch
Work started → DoD           =  5 ngày lịch
DoD → Available              =  2 ngày lịch
Work started → Available     =  7 ngày lịch
Request accepted → Started   =  3 ngày lịch
~~~

**Câu 3 – Vì sao khác nhau?** Học viên còn chờ trước lúc bắt đầu và sau khi DoD tới khi được sử dụng. Thời gian viết mã hoặc thời gian tới DoD không tự bao gồm hai đoạn này.

**Câu 4 – Thống kê:**

~~~text
Tổng = 88 ngày; n = 8
Mean = 88 / 8 = 11 ngày
Median = (8 + 11) / 2 = 9,5 ngày
P85 theo nearest-rank = phần tử thứ ceil(0,85 × 8) = thứ 7
                         = 17 ngày
Tỷ lệ quan sát ≤ 17 ngày = 7/8 = 87,5%
~~~

**Câu 5 – SLE ứng viên:** “Đối với user story tiêu chuẩn đo từ Request accepted tới Available cho nhóm học viên mục tiêu, có thể **tạm tham khảo** mốc 17 ngày lịch với mức kỳ vọng khoảng 85%, dựa trên tám quan sát hiện có; cần thêm dữ liệu trước khi dùng để cam kết hay dự báo nghiêm túc”. Không được nói “mọi story sẽ xong sau 17 ngày”.

**Câu 6 – Work Item Age:** từ 11/11 tới 23/11 lúc 09:00 là **12 ngày lịch**. Item vẫn chưa Done nên **chưa có lead time cuối cùng**; cần xem blocker, phạm vi và vị trí trên luồng, không lấy 12 ngày làm thời gian đã giao.

**Câu 7 – Done cục bộ:** có thể ghi các task kỹ thuật đã hoàn thành để điều phối, nhưng **không đếm chúng là sáu user story đã delivered**. Story/hành trình chỉ được ghi nhận ở mốc kết thúc đã định nghĩa và đáp ứng chất lượng. Nếu thực sự có nhiều Increment độc lập sử dụng được, phải chứng minh và xác định chúng là những hạng mục giá trị riêng.

**Câu 8 – Cải tiến:** (1) giới hạn WIP và ưu tiên hoàn tất review/tích hợp trước khi mở nhiều task mới; (2) chuẩn hóa acceptance criteria liên nhóm và tự động hóa kiểm thử hợp đồng/luồng quan trọng để giảm chờ sửa lỗi. **Guardrail** có thể là lỗi production về quyền/tiến độ; **outcome** là tỷ lệ học viên đủ điều kiện mở đúng bài tiếp theo.

**Câu 9 – Hủy:** ghi Cancelled với timestamp và lý do riêng; có thể đo **time to cancellation** nếu cần hiểu chi phí chờ quyết định. Không coi đó là item đã delivered hoặc gán lead time bằng 0.

**Câu 10 – Đổi ranh giới:** số liệu trước và sau **không còn cùng nghĩa**. Nhóm phải ghi phiên bản định nghĩa, tính lại lịch sử nếu có timestamp đầy đủ hoặc báo hai chuỗi riêng; tuyệt đối không vẽ một đường xu hướng duy nhất rồi kết luận cải tiến.

### 20.4. Bài tập mở rộng: nhìn thời gian chờ có ý nghĩa

Giả sử một team đo được WIP trung bình là 9 item **từ work started đến Done**, throughput trung bình 3 item/tuần trong giai đoạn đủ ổn định. Theo Little's Law, thời gian trung bình trong luồng này xấp xỉ **3 tuần**. Hãy giải thích tại sao đây **không phải** ước tính thời gian từ lúc học viên gửi yêu cầu đến khi dùng được và cần thu thêm những timestamp nào.

Gợi ý: phải bổ sung các mốc **request/accepted/commitment** trước work started và **availability** sau Done, đồng thời giữ chính sách phân đoạn dữ liệu nhất quán. Đây là bài thực hành về **ranh giới đo**, không chỉ về phép chia.

## 21. Checklist trước khi công bố và sử dụng lead time

- [ ] Nhóm đã viết rõ **câu hỏi ra quyết định** mà lead time nhằm trả lời?
- [ ] Đã chọn **sự kiện bắt đầu và kết thúc** có ý nghĩa với người dùng hoặc nhóm phục vụ?
- [ ] Mỗi metric có **tên riêng** cho request lead time, commitment lead time, cycle time hoặc change lead time?
- [ ] **Definition of Done** và điều kiện availability được hiểu và áp dụng nhất quán?
- [ ] Có nêu rõ **cohort mục tiêu** khi rollout theo feature flag/canary?
- [ ] Dữ liệu có timestamp đầy đủ, timezone, nguồn sự kiện và lịch sử thay đổi?
- [ ] Đã thống nhất **calendar days hoặc working days** và quy tắc làm tròn?
- [ ] Thời gian blocked/waiting trong ranh giới vẫn được tính, đồng thời đo riêng nguyên nhân chờ?
- [ ] Có chính sách với **cancelled, reopened, split, merged và hạng mục chưa hoàn tất**?
- [ ] Báo cáo được phân đoạn theo **loại công việc hoặc class of service** khi khác biệt đáng kể?
- [ ] Dùng mean đi cùng **median/phân vị/phân phối**, không chỉ một số trung bình?
- [ ] Phương pháp tính P85/P95 đã được công bố, kể cả **nội suy hay nearest-rank**?
- [ ] SLE nêu **ngưỡng thời gian, xác suất, ranh giới và điều kiện áp dụng**, không phải lời hứa tuyệt đối?
- [ ] Có theo dõi **Work Item Age** của những việc chưa Done, không chỉ item đã hoàn tất?
- [ ] Khi dùng Little's Law, **WIP, throughput và thời gian trong hệ thống** có cùng ranh giới?
- [ ] Cải tiến lead time không được đạt bằng cách **hạ chất lượng, đổi điểm đo hoặc reset ticket**?
- [ ] Có thể truy tìm điểm nghẽn thực tế như **chờ ưu tiên, review, test, tích hợp, release**?
- [ ] Các thử nghiệm cải tiến có **đường cơ sở, giả thuyết, thời điểm đo lại và guardrail**?
- [ ] Lead time được xem cùng **lỗi sản phẩm, chất lượng, outcome và phản hồi học viên**?
- [ ] Chỉ số dùng để **cải thiện dòng công việc của hệ thống**, không để xếp hạng hay gây áp lực không lành mạnh lên cá nhân?
- [ ] Nếu thay đổi ranh giới đo, đã **ghi phiên bản chính sách và chú thích dữ liệu lịch sử**?

**Ghi nhớ:** **Lead time đo thời gian từ một sự kiện đầu vào được xác định đến một sự kiện giao kết quả được xác định**; giá trị của chỉ số phụ thuộc trước hết vào **ranh giới đo rõ ràng và nhất quán**. Hãy phân biệt yêu cầu tới người dùng với thời gian triển khai kỹ thuật, quan sát cả phân phối lẫn công việc đang dở, và dùng SLE như một kỳ vọng xác suất có điều kiện. Khi kết hợp lead time với WIP, throughput, DoD, kiểm thử, Scrum, Kanban, XP và outcome người dùng, nhóm Agile có thể **giảm thời gian chờ thực sự, dự báo minh bạch và giao giá trị tăng dần một cách đáng tin cậy**.
