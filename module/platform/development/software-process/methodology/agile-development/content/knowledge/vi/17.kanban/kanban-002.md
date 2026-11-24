# Kanban: Định nghĩa luồng công việc cùng điểm bắt đầu và kết thúc

Một nhóm phát triển phần mềm có bảng công việc gồm các cột **To do – Doing – Done**. Một thành viên đưa mọi yêu cầu vừa nghe vào Doing, người khác chỉ chuyển thẻ khi bắt đầu lập trình, còn nhóm kiểm thử coi Done là “đã kiểm tra” dù bản sửa chưa được tích hợp. Cuối tháng, nhóm muốn biết một yêu cầu thường mất bao lâu để hoàn thành, nhưng không ai thống nhất **thời điểm công việc thực sự bắt đầu** và **khi nào được xem là kết thúc**. Từ cùng một dữ liệu, mỗi người có thể đưa ra một số liệu khác nhau.

Trong **Kanban**, hình ảnh các thẻ trên bảng chỉ hữu ích khi nhóm cùng hiểu **Definition of Workflow (DoW) – định nghĩa luồng công việc**: loại việc đi qua hệ thống, ranh giới bắt đầu và kết thúc, các trạng thái nằm giữa, cách kiểm soát công việc đang thực hiện, chính sách di chuyển và kỳ vọng về thời gian hoàn thành. Những quy ước này cho phép đo và cải thiện dòng công việc thay vì tranh luận cảm tính.

Bài thuộc mô-đun **AGILE_DEVELOPMENT**, tập trung phát triển phần mềm thích ứng bằng phản hồi sớm, giao sản phẩm tăng dần, cải tiến liên tục, user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc. Trọng tâm của bài là **định nghĩa luồng công việc với điểm bắt đầu và kết thúc rõ ràng**; từ đó mới có thể sử dụng WIP, work item age, cycle time và throughput một cách nhất quán để ra quyết định.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Definition of Workflow** và phân biệt luồng công việc thực tế với hình vẽ một bảng Kanban.
2. Xác định đơn vị công việc (*work item*) và những loại yêu cầu nên được theo dõi trong cùng một hệ thống.
3. Đặt ranh giới **started** và **finished** có thể quan sát, dùng được cho mọi thành viên.
4. Phân biệt thời điểm nhận yêu cầu, cam kết xử lý, bắt đầu thực hiện, đạt chuẩn hoàn tất và phát hành giá trị.
5. Thiết kế các trạng thái trung gian, chính sách chuyển trạng thái, cách xử lý blocked và rework.
6. Định nghĩa, kiểm soát và giải thích **Work in Progress (WIP)** dựa trên hai ranh giới đã chọn.
7. Tính đúng **cycle time, work item age, throughput** và diễn giải **Service Level Expectation (SLE)**.
8. Thử xây một DoW cho luồng phát triển user story hoặc sửa lỗi, nhận diện điểm nghẽn và điều chỉnh quy ước bằng dữ liệu.

## 2. Definition of Workflow là gì và vì sao cần nó?

**Definition of Workflow (DoW)** là tập hợp những thỏa thuận mô tả cách **một hạng mục công việc** đi qua hệ thống Kanban từ lúc bắt đầu đến khi kết thúc. Tùy đội và phạm vi dịch vụ, công việc có thể là một user story, lỗi, thay đổi cấu hình, yêu cầu hỗ trợ hoặc một loại work item được xác định rõ.

Một DoW có ích cần làm rõ ít nhất các yếu tố:

| Yếu tố | Câu hỏi cần trả lời | Ví dụ nhóm phát triển ứng dụng workshop |
| --- | --- | --- |
| **Work items** | Loại hạng mục nào được theo dõi? Đơn vị nào đủ nhỏ để thấy tiến triển? | Một lát cắt user story hoặc một lỗi có điều kiện hoàn tất rõ |
| **Started / Finished** | Hạng mục đi vào/ra khỏi dòng đang thực hiện ở đâu? | Started khi kéo thẻ sang Doing; Finished khi bản thay đổi đạt chính sách Done |
| **Trạng thái trong luồng** | Công việc đang ở những bước nào? | Doing, Code review, Verify |
| **Kiểm soát WIP** | Cách hạn chế công việc đã bắt đầu nhưng chưa xong? | Doing tối đa 3, Review tối đa 2, Verify tối đa 2 |
| **Chính sách tường minh** | Điều kiện chọn, chuyển, chặn, hoàn tất và xử lý ngoại lệ? | Không kéo thêm nếu WIP đã đầy; Verify chỉ nhận bản đã qua review và build |
| **SLE** | Dựa trên lịch sử, nhóm kỳ vọng hạng mục thường đi từ started đến finished trong bao lâu? | Mục tiêu dự báo thử: 85% hạng mục cùng loại hoàn tất trong 8 ngày lịch hoặc ít hơn |

Các con số ở ví dụ đều **giả định**. DoW không phải tài liệu viết một lần rồi bất biến; nó được làm rõ và điều chỉnh khi nhóm quan sát hệ thống làm việc.

### 2.1. Bảng Kanban và DoW không phải một

Bảng chỉ có ba cột có thể giúp **trực quan hóa** nhưng chưa chắc đủ để **định nghĩa**. Nếu hai người khác nhau về ý nghĩa “Doing” và “Done”, dữ liệu thời gian không nhất quán, WIP khó kiểm soát, điểm nghẽn không thể thấy chính xác.

Ngược lại, một DoW tốt có thể được thể hiện trên bảng vật lý, phần mềm theo dõi, sơ đồ quy trình hoặc các công cụ phối hợp khác. Công cụ không thay thế sự thống nhất về các ranh giới và chính sách.

### 2.2. Luồng công việc được định nghĩa theo mục đích dịch vụ

Ví dụ, bộ phận tiếp nhận yêu cầu có thể coi “Finished” là **đã phân loại và chuyển tới nhóm thực hiện**. Đội phát triển sản phẩm lại có thể coi “Finished” là **phần mềm đã kiểm thử, tích hợp và sẵn sàng sử dụng**; đội vận hành có thể cần đến **triển khai và xác minh trong môi trường thật**.

Không có một điểm kết thúc chung cho mọi dịch vụ. Điều bắt buộc là **phải nói rõ dịch vụ nào đang đo và giá trị gì được coi là đã giao**.

## 3. Trước tiên xác định đúng work item

Định nghĩa điểm bắt đầu và kết thúc chỉ có ý nghĩa khi nhóm biết **một đơn vị công việc là gì**.

### 3.1. Những đơn vị thường gặp

- **User story:** một hành vi hoặc lát cắt giá trị người dùng có thể kiểm chứng.
- **Bug:** một hành vi sai cần được tái hiện, sửa và kiểm tra theo quy tắc.
- **Thay đổi kỹ thuật:** cải thiện nền tảng, kiểm thử hoặc khả năng vận hành có phạm vi và điều kiện hoàn tất.
- **Yêu cầu hỗ trợ:** một vấn đề khách hàng hoặc bộ phận nội bộ cần xử lý đến kết quả được xác định.
- **Phép thử khám phá:** nghiên cứu có giới hạn nhằm trả lời câu hỏi hoặc giảm bất định, không giả vờ đó là một chức năng sản phẩm đã phát hành.

Nếu một nhóm trộn các yêu cầu 15 phút với chương trình phát triển ba tháng và gọi tất cả là “một ticket”, throughput hoặc cycle time trung bình có thể đánh lừa. Có thể **phân loại theo work item type**, chia hạng mục lớn thành lát cắt đủ dùng hoặc theo dõi các luồng riêng nếu cách xử lý và kỳ vọng rất khác nhau.

### 3.2. Một item cần có ranh giới nội dung

Một user story ví dụ:

> Là học viên đăng ký workshop, tôi muốn nhìn thấy yêu cầu của mình đang chờ hay đã được xác nhận, để không phải nhắn hỏi ban tổ chức sau khi gửi.

Đơn vị công việc này có thể có:
- Người dùng và lợi ích cụ thể.
- Trường hợp thành công và trường hợp lỗi.
- Các quy tắc quyền truy cập và trạng thái.
- Điều kiện kiểm chứng và tiêu chuẩn hoàn tất.
- Người hoặc nhóm chịu trách nhiệm đưa nó qua dòng công việc.

Ngược lại, “nâng cấp toàn bộ hệ thống đăng ký” quá lớn và khó dự báo như một work item duy nhất. Trước khi dùng số liệu Kanban, cần chọn kích thước hạng mục phù hợp với dịch vụ.

### 3.3. Một vấn đề có thể tạo nhiều work item nhưng không được đếm trùng

Một yêu cầu ban đầu có thể được chia thành **xem trạng thái**, **xác nhận chỗ**, **thông báo khi trạng thái thay đổi**. Nếu đây là những phần có giá trị và điều kiện hoàn tất riêng, chúng có thể được theo dõi là nhiều item.

Tuy nhiên, không nên vừa đếm “epic đăng ký” như một item hoàn tất vừa đếm ba story con như ba item độc lập trong cùng thống kê throughput khi mục tiêu là đếm **đơn vị giao giá trị ở cùng mức**. Cần xác định **mức công việc nào được đưa vào tập đo**.

## 4. Xác định điểm bắt đầu: khi nào công việc thực sự vào luồng?

**Started point** là thời điểm một work item được xem là đã bắt đầu theo DoW. Nó là ranh giới thống nhất để tính **WIP**, **work item age** và **cycle time**.

Nhiều nhóm nhầm ba thời điểm khác nhau:

1. **Nhận yêu cầu (arrival):** khách hàng gửi phản hồi hoặc một ý tưởng xuất hiện.
2. **Chọn/cam kết sẽ xử lý (commitment hoặc selection):** nhóm quyết định ưu tiên và có thể đưa vào hàng chờ sẵn sàng.
3. **Bắt đầu theo DoW (started):** work item vượt ranh giới được định nghĩa và được tính vào WIP.

Các mốc này **có thể trùng nhau hoặc khác nhau** tùy hệ thống. Không thể nhìn nhãn “To do” rồi khẳng định công việc đã bắt đầu nếu DoW chưa nói rõ.

### 4.1. Ví dụ định nghĩa started khi kéo vào Doing

Nhóm workshop đặt chính sách:

> **Started = thời điểm một PBI đã đủ rõ được Developers kéo từ Ready vào Doing, có khả năng thực sự được xử lý và bắt đầu tính trong giới hạn WIP.**

Trong quy ước này:
- Mục trong **Intake** và **Ready** **chưa started**.
- Mục trong **Doing**, **Review**, **Verify** đều **đã started**.
- Mục bị **blocked** sau khi started **vẫn tính WIP** và tiếp tục già đi theo thời gian.
- Ngày nhận ý tưởng không được tự động dùng làm ngày started.

Định nghĩa này có thể phù hợp khi nhóm muốn đo thời gian thực hiện sau khi đã đủ điều kiện bắt đầu. Nó **không đo toàn bộ thời gian khách hàng chờ** từ lúc gửi yêu cầu; để làm điều đó cần ghi thêm mốc arrival và định nghĩa chỉ số tương ứng.

### 4.2. Một lựa chọn khác: started tại điểm cam kết

Một nhóm xử lý sự cố có thể chọn **Started = khi chấp nhận yêu cầu vào hệ thống dịch vụ đang quản lý** dù item còn chờ phân công. Trong trường hợp này hàng đợi **sau điểm cam kết** cũng nằm trong WIP, nếu work item đã started.

Hai lựa chọn đều có thể có mục đích hợp lý; nhưng **dữ liệu sẽ khác**. Không được dùng cycle time của lựa chọn thứ nhất để so trực tiếp với lựa chọn thứ hai rồi kết luận nhóm nào nhanh hơn.

### 4.3. Những câu hỏi cần giải quyết khi chọn started

1. Đâu là **dịch vụ** đang được đo: sàng lọc, phát triển, phát hành hay hỗ trợ?
2. Trước ranh giới, ai sở hữu việc ra quyết định ưu tiên?
3. Khi item vượt ranh giới, nhóm có thật sự nhận trách nhiệm đưa nó đến finished?
4. Những trạng thái hàng chờ nào nằm **sau started**?
5. Blocked, chuyển người thực hiện hoặc chờ xác nhận có khiến item quay về trạng thái “chưa started” không? Thông thường **không nên xóa lịch sử bắt đầu** để làm đẹp số liệu.
6. Hệ thống có thể ghi nhận dấu thời gian started đáng tin không?

**Dấu hiệu tốt:** mọi thành viên có thể trả lời nhất quán “item này đã bắt đầu chưa?” chỉ bằng trạng thái và chính sách đã công bố.

## 5. Xác định điểm kết thúc: khi nào hạng mục thực sự finished?

**Finished point** là thời điểm item thoát khỏi dòng theo một **điều kiện hoàn tất rõ ràng**. Ranh giới này quyết định thời gian kết thúc cho cycle time và hạng mục nào được tính trong throughput.

### 5.1. “Code complete”, “Done” và “delivered” có thể khác nhau

Một thay đổi phần mềm có thể trải qua:

| Mốc | Ý nghĩa | Có luôn là finished không? |
| --- | --- | --- |
| **Code complete** | Lập trình viên đã viết xong mã dự kiến | Không; review, tích hợp, kiểm thử có thể còn thiếu |
| **Review complete** | Mã đã được rà soát theo chính sách | Không nếu còn kiểm thử hoặc công việc khác |
| **Meets DoD** | Increment đạt chuẩn chất lượng chung theo định nghĩa của nhóm | Có thể là finished nếu DoW đo tới trạng thái sẵn sàng bàn giao |
| **Released / deployed** | Thay đổi đã được triển khai tới môi trường/nhóm người dùng xác định | Có thể là finished nếu DoW đo tới phát hành |
| **Verified in use** | Bản triển khai được xác minh hoạt động theo yêu cầu trong phạm vi đã định | Có thể là finished nếu dịch vụ bao gồm xác minh sau phát hành |
| **Outcome achieved** | Người dùng thực sự nhận lợi ích kỳ vọng | Thường cần đo riêng theo thời gian; không nên buộc mọi work item chờ kết quả dài hạn mới finished |

Với nhóm vận hành sản phẩm cần biết **người dùng có thể sử dụng thay đổi khi nào**, finished có thể là “đã triển khai và xác minh”. Với nhóm phát triển tạo Increment đáp ứng DoD và bàn giao cho đội phát hành riêng, finished có thể là “sẵn sàng phát hành”. Phải **nêu rõ phạm vi và tránh gọi một mốc này bằng tên mốc kia**.

### 5.2. Ví dụ chính sách finished đủ kiểm chứng

Nhóm workshop quyết định đo **dịch vụ phát triển và phát hành một lát cắt**:

> **Finished = thay đổi đã đạt Definition of Done, được đưa vào môi trường phục vụ người dùng mục tiêu và bước xác minh sau triển khai theo chính sách đã hoàn tất.**

DoW của nhóm vì thế cần chứa trạng thái hoặc hoạt động phát hành và xác minh ở phía trước finished. Một story mới chỉ “đã merge” sẽ **chưa finished** theo quy ước này.

Nếu nhóm khác chỉ đo tới “sẵn sàng phát hành”, cần dùng nhãn và chỉ số riêng, không mặc định hai ranh giới tương đương.

### 5.3. Điều gì xảy ra với hạng mục bị hủy hoặc không còn cần?

Một work item có thể được **hủy, loại vì trùng, hoặc trở nên không còn phù hợp** trước khi hoàn tất giá trị.

Đừng đếm việc hủy như **completed throughput** nếu hệ thống đo số yêu cầu đã được phục vụ. Nên có kết quả phân biệt:
- **Finished successfully:** đạt điều kiện hoàn tất của loại item.
- **Cancelled/withdrawn:** có quyết định bỏ vì không còn giá trị, trùng hoặc thay đổi bối cảnh.
- **Superseded/merged:** được thay bởi mục khác và có liên kết.
- **Rejected:** không đủ điều kiện tiếp nhận hoặc không phù hợp dịch vụ.

Nếu mục tiêu đo là **thời gian xử lý yêu cầu sàng lọc**, quyết định từ chối cũng có thể được xem là kết thúc thành công của **dịch vụ sàng lọc**. Vì thế phải xác định chính xác dịch vụ và tập item đo, tránh coi mọi nhãn “Closed” là cùng một loại hoàn tất.

### 5.4. Công việc phải làm lại sau khi Finished

Nếu sản phẩm sau khi finished có lỗi mới, nhóm có thể tạo một bug liên kết. Nếu item bị đưa trở lại trước ranh giới finished vì phát hiện chưa thực sự đạt chính sách hoàn tất, cần ghi nhận đó là **reopen** theo quy ước và sửa dữ liệu phù hợp; không xóa dấu vết hoặc tạo throughput giả.

Nhóm nên thống nhất:
- Reopen trước hay sau khi thực sự hoàn tất?
- Item mới hay cùng một item?
- Cách ghi lịch sử để không đếm hai lần?
- Chất lượng sản phẩm được theo dõi ra sao?

## 6. Vẽ dòng công việc thực tế từ started tới finished

Một DoW cần chứa **các trạng thái mà item đi qua**, trong đó **điểm bắt đầu và kết thúc được đánh dấu rõ ràng**.

### 6.1. Ví dụ luồng phần mềm có cả bước phát hành

~~~mermaid
flowchart LR
    A[Intake: tiếp nhận] --> B[Ready: đủ rõ]
    B -->|Started| C[Doing: phát triển]
    C --> D[Review]
    D --> E[Verify: tích hợp, kiểm thử]
    E --> F[Release: triển khai, xác minh]
    F -->|Finished| G[Done]
    D -->|Cần sửa| C
    E -->|Lỗi phát hiện| C
~~~

Với luồng này:

- **Intake và Ready** ở **trước started**, không nằm trong WIP của dịch vụ phát triển đã định nghĩa.
- **Doing, Review, Verify, Release** nằm **sau started và trước finished**, nên đều thuộc WIP.
- **Done** nằm **sau finished**, không còn thuộc WIP.
- Quay lại Doing do lỗi không tạo một lần bắt đầu mới; **tuổi work item tiếp tục**.
- Chờ review hoặc chờ release có thể là **trạng thái hàng đợi** đáng phân biệt nếu dữ liệu cho thấy đó là điểm nghẽn.
- Nếu phát hành không thuộc trách nhiệm nhóm, cần điều chỉnh finished và tên luồng cho đúng phạm vi đang quản lý.

Sơ đồ không nói rằng mọi sản phẩm đều phải có đúng bảy trạng thái. **Chọn trạng thái đủ để nhìn thấy dòng việc và có quyết định phù hợp**, không thiết kế một bảng với hàng chục cột chỉ để mô phỏng mọi thao tác nhỏ.

### 6.2. Một bảng Kanban minh họa

~~~text
TRƯỚC STARTED                 ĐÃ STARTED / ĐANG TÍNH WIP                  SAU FINISHED
+---------+---------+     +----------+----------+----------+----------+     +-------+
| Intake  | Ready   | --> | Doing    | Review   | Verify   | Release  | --> | Done  |
|         |         |     | WIP <= 3 | WIP <= 2 | WIP <= 2 | WIP <= 1 |     |       |
+---------+---------+     +----------+----------+----------+----------+     +-------+
                                ^ Bắt đầu                           Kết thúc ^
~~~

Các giới hạn **3, 2, 2, 1** là ví dụ do nhóm thử, không phải “quy định Kanban”. Nếu một item bị blocked trong Review thì nó **vẫn chiếm WIP Review** theo chính sách minh họa này. Cách hiển thị blocked nên rõ, chẳng hạn gắn dấu và ghi lý do/ngày bắt đầu chờ.

### 6.3. Đừng chỉ vẽ quy trình lý tưởng

Để định nghĩa DoW phản ánh sự thật, nhóm nên đi theo **hai hoặc ba hạng mục vừa hoàn thành**:
- Chúng thực sự đi qua những ai/bước nào?
- Có chờ tích hợp, kiểm thử, triển khai hoặc xác nhận từ bên ngoài?
- Những chỗ “đang làm” thực chất chỉ là xếp hàng đợi?
- Có vòng sửa lại nào thường xuyên xảy ra?
- Có hạng mục bỏ bảng để xử lý qua chat hoặc nhảy thẳng sang Done?

Nếu bỏ những chỗ chờ thật ra khỏi DoW, số liệu có thể đẹp nhưng nhóm không nhìn thấy nguyên nhân giao hàng chậm.

## 7. Chính sách chuyển trạng thái: rõ ràng hơn tên cột

Một DoW cần **chính sách tường minh** để mọi người biết khi nào một item đủ điều kiện chuyển sang trạng thái tiếp theo. Chính sách có thể ngắn nhưng phải có thể quan sát và kiểm tra.

| Chuyển tiếp | Chính sách ví dụ | Vì sao cần |
| --- | --- | --- |
| Intake → Ready | Người dùng/vấn đề đã xác định, có ví dụ cơ bản và quyền ưu tiên rõ | Tránh kéo một yêu cầu quá mơ hồ vào xử lý |
| Ready → Doing (**started**) | WIP Doing còn chỗ, item là lựa chọn tiếp theo theo chính sách, người thực hiện sẵn sàng | Kiểm soát việc bắt đầu và ghi dấu thời gian đáng tin |
| Doing → Review | Thay đổi có mã hoặc sản phẩm cần review, có kiểm thử phù hợp và mô tả rõ | Không đẩy một việc chưa đủ điều kiện cho người review |
| Review → Verify | Review đạt, phần thay đổi đã được tích hợp theo chính sách | Kiểm thử trên trạng thái nhất quán |
| Verify → Release | Điều kiện chấp nhận, DoD và chuẩn phát hành liên quan được đáp ứng | Bảo vệ chất lượng trước khi người dùng nhận thay đổi |
| Release → Done (**finished**) | Triển khai và kiểm tra sau triển khai thành công trong phạm vi đã thống nhất | Finished gắn với dịch vụ đã định nghĩa |
| Bất kỳ trạng thái đang làm → Blocked | Có trở ngại khiến item không thể tiến triển theo chính sách; ghi lý do và người xử lý | Nhìn thấy rủi ro thay vì che trong cột Doing |
| Review/Verify → Doing | Phát hiện cần sửa; ghi kết quả và nguyên nhân, giữ ngày started gốc | Không coi việc làm lại là item mới hoặc tự “reset” cycle time |

Bảng là gợi ý áp dụng. Nếu sản phẩm yêu cầu kiểm soát bảo mật, quy định nghiệp vụ hoặc kiểm thử hiệu năng ở mức cụ thể, phải làm rõ điều đó trong DoD và chính sách vận hành phù hợp; không được suy rằng vài dòng điều kiện ở ví dụ đủ cho mọi hệ thống.

### 7.1. Chính sách “Ready” cần cân bằng

Quá dễ: mọi ý tưởng, kể cả câu “làm app tốt hơn”, đều được đưa vào Ready. Hệ quả là Developers bắt đầu rồi chờ làm rõ.

Quá khó: nhóm đòi viết tài liệu dài và thiết kế toàn bộ hệ thống trước khi Ready. Hệ quả là trì hoãn phản hồi và tích lũy công việc chuẩn bị không tạo giá trị.

Một chính sách hợp lý có thể yêu cầu **vấn đề, đối tượng, ví dụ nghiệp vụ và rủi ro chính**, đồng thời cho phép tiếp tục trao đổi khi làm việc. Tính đủ rõ thay đổi theo loại item; sửa lỗi có thể cần bước tái hiện, story chức năng cần ngữ cảnh người dùng.

### 7.2. Quy tắc pull và điều kiện WIP

**Pull** nghĩa là nhóm kéo một item mới vào phần có năng lực xử lý khi có điều kiện phù hợp, thay vì liên tục được “đẩy” thêm từ bên ngoài bất chấp WIP.

Ví dụ khi Review đã đạt giới hạn hai item, một item mới ở Doing **không nên được chuyển sang Review chỉ để làm đầy cột** mà cần hợp tác giúp giải phóng khả năng review hoặc điều chỉnh kế hoạch theo chính sách. Nếu Doing đã có ba item, không bắt đầu item thứ tư chỉ vì một cá nhân có thời gian trống trong khi các item cũ đang bị chặn.

Chính sách phải nói rõ **ai có quyền kéo, trạng thái nào có giới hạn, việc khẩn được xử lý ra sao**. Mục tiêu là **hoàn tất công việc hữu ích trước khi bắt đầu thêm**, không phải khiến mỗi cá nhân lúc nào cũng “bận”.

## 8. WIP: kết quả trực tiếp của ranh giới started/finished

**Work in Progress (WIP)** là **số work items đã bắt đầu nhưng chưa kết thúc** theo DoW tại một thời điểm.

Công thức khái niệm:

~~~text
WIP(t) = số item có started_at <= t và chưa finished tại t
~~~

Công thức minh họa giả định tất cả item vẫn được theo dõi trong dịch vụ; việc hủy/chuyển ra khỏi luồng cần có chính sách riêng để tránh cộng nhầm.

### 8.1. Một ví dụ đếm WIP

Bảng tại thời điểm kiểm tra:

| Item | Trạng thái | Started? | Finished? | Tính WIP? |
| --- | --- | --- | --- | --- |
| WK-01 | Intake | Không | Không | Không |
| WK-02 | Ready | Không | Không | Không |
| WK-03 | Doing | Có | Không | **Có** |
| WK-04 | Review | Có | Không | **Có** |
| WK-05 | Verify, bị blocked | Có | Không | **Có** |
| WK-06 | Release | Có | Không | **Có** |
| WK-07 | Done | Có | Có | Không |
| **Tổng WIP** | | | | **4** |

**Blocked vẫn là WIP** vì khách hàng chưa nhận kết quả và thời gian vẫn đang trôi. Nếu nhóm tự động chuyển blocked về Ready trước started chỉ để giảm WIP, bảng có thể che mất thời gian chờ thật. Trường hợp hủy hoặc tạm dừng dài hạn cần được ghi bằng chính sách rõ thay vì làm biến mất item.

### 8.2. WIP limit là cơ chế học hỏi, không phải mức tối đa đạo đức

Một giới hạn WIP phù hợp giúp:
- Giảm số việc bị mở cùng lúc nhưng không hoàn tất.
- Khuyến khích hỗ trợ review, kiểm thử hoặc gỡ chặn.
- Làm điểm nghẽn lộ ra thay vì tích lũy hàng chờ ẩn.
- Giảm chuyển ngữ cảnh và tạo cơ hội giao giá trị thường xuyên.

Nhưng đặt giới hạn quá thấp mà không xét năng lực, loại công việc hoặc phụ thuộc có thể tạo ràng buộc không hữu ích. DoW cần được thử nghiệm, quan sát và điều chỉnh theo dữ liệu.

### 8.3. Tổng WIP và giới hạn từng trạng thái

Nếu nhóm có giới hạn Doing 3, Review 2, Verify 2 và Release 1, **tổng năng lực trạng thái tối đa theo cấu hình là 8**, nhưng không phải lúc nào WIP thực tế cũng là 8. Có thể đặt thêm **giới hạn WIP toàn luồng** nếu hữu ích, tuy nhiên phải ghi rõ chính sách khi các giới hạn tương tác với nhau.

Ví dụ, muốn giảm tình trạng mở quá nhiều việc, nhóm có thể thử WIP tổng bằng 5 trong khi vẫn giữ các giới hạn cột. Khi đó tổng 5 mới là ngưỡng toàn luồng cần quan sát; không được hiểu bốn giới hạn cột như bốn mục tiêu phải luôn đạt.

## 9. Các số đo dòng công việc bắt nguồn từ ranh giới đã định nghĩa

Theo cách đo Kanban, bốn số liệu dòng công việc thường được quan sát là **WIP, throughput, work item age, cycle time**. Các số liệu này chỉ có ý nghĩa nếu **started và finished được dùng nhất quán**.

### 9.1. Cycle time

**Cycle time** là **thời gian đã trôi qua** từ started đến finished của một item **đã hoàn tất**.

~~~text
Cycle time = finished_at - started_at
~~~

Nếu item bắt đầu lúc 09:00 ngày 3 và finished lúc 09:00 ngày 7 cùng một tháng, cycle time là **4 ngày lịch**. Nếu item chờ review 2 ngày trong đó, **2 ngày chờ vẫn nằm trong cycle time**, vì khách hàng chưa nhận kết quả theo điểm finished đã định nghĩa.

Cần ghi rõ đơn vị là **ngày lịch**, **giờ**, hay **ngày làm việc**. Không dùng lẫn 4 ngày lịch với 4 ngày làm việc; cùng một item có thể cho kết quả khác nhau theo hai cách đếm.

### 9.2. Work item age

**Work item age** là thời gian đã trôi qua từ started đến **thời điểm quan sát hiện tại** của một item **chưa finished**:

~~~text
Work item age(t) = t - started_at, nếu item chưa finished
~~~

Age trả lời: “Item đang làm này đã tồn tại bao lâu trong hệ thống?”. Nó khác cycle time vì item chưa kết thúc nên **không biết cycle time cuối cùng của nó**.

Một item có age 9 ngày trong khi hầu hết item cùng loại hoàn tất trong 5 ngày cần được kiểm tra. Điều đó không tự chứng minh có ai làm sai; có thể là phụ thuộc bên ngoài, phạm vi lớn, lỗi chất lượng hoặc một loại công việc khác.

### 9.3. Throughput

**Throughput** là **số work items đạt finished** trong một khoảng thời gian đã định nghĩa.

~~~text
Throughput tuần = số item finished trong tuần đó
~~~

Đếm đúng tập item đã định nghĩa. Nếu tuần có ba story hoàn tất và hai yêu cầu được đóng vì trùng, throughput của **dịch vụ giao phần mềm** thường là **3**, không phải 5. Nếu nhóm đo **dịch vụ phân loại yêu cầu** và closed-duplicate là một kết quả hợp lệ của dịch vụ ấy, cần định nghĩa bộ đếm riêng.

### 9.4. Lead time của khách hàng có thể khác cycle time đã chọn

Nhóm có thể theo dõi thời gian từ **arrival** đến **finished** để hiểu mức độ chờ của khách hàng. Trong nhiều ngữ cảnh, đó được gọi là *customer lead time* hoặc *lead time*, nhưng phải ghi rõ hai mốc.

Nếu started được đặt sau hàng chờ Ready, thì:

~~~text
Thời gian từ arrival tới finished
  = thời gian trước started + cycle time từ started tới finished
~~~

Điều này chỉ đúng khi các mốc được ghi theo cùng đơn vị thời gian và không có cách xử lý đặc biệt làm thay đổi tính toán.

**Quan trọng:** Kanban không yêu cầu một cách gọi “lead time” duy nhất cho mọi tổ chức. Khi chia sẻ số liệu, nên ghi rõ **từ sự kiện nào đến sự kiện nào** thay vì chỉ đưa ra con số.

### 9.5. Bảng dữ liệu mẫu với ranh giới nhất quán

Giả định nhóm dùng mốc **ngày số 1, 2, 3...** tính theo thời gian lịch, mọi dấu thời gian ở cùng giờ trong ngày:

| Item | Arrival | Started | Finished / quan sát | Kết quả tính |
| --- | --- | --- | --- | --- |
| WK-101 | Ngày 1 | Ngày 3 | Finished ngày 7 | Cycle time = 4 ngày; từ arrival = 6 ngày |
| WK-102 | Ngày 2 | Ngày 4 | Finished ngày 9 | Cycle time = 5 ngày; từ arrival = 7 ngày |
| WK-103 | Ngày 4 | Ngày 5 | **Chưa finished**, quan sát ngày 12 | Work item age = 7 ngày; chưa có cycle time cuối cùng |

Tại **thời điểm ngày 12**, nếu chỉ có ba item trên và không có việc nào khác đang mở, **WIP = 1** (WK-103); **throughput toàn khoảng quan sát đến ngày 12 = 2** (WK-101 và WK-102). Khi báo throughput cần nói rõ thời gian bắt đầu của khoảng báo cáo để người khác tái tạo được.

Các con số là **minh họa**. Nếu đổi started từ ngày 3 sang ngày 1 cho WK-101, cycle time sẽ đổi từ 4 thành 6 ngày dù người dùng không nhận kết quả sớm hay muộn hơn; đó là thay đổi **ranh giới đo**, không phải thay đổi hiệu suất thật.

## 10. Service Level Expectation (SLE): kỳ vọng dựa trên lịch sử

**SLE** là kỳ vọng về **thời gian từ started đến finished** của một work item theo DoW, thường được diễn đạt bằng **một khoảng thời gian và tỷ lệ phần trăm**.

Ví dụ:

> **“Theo dữ liệu lịch sử hiện có, khoảng 85% story thuộc loại này hoàn tất trong 8 ngày lịch hoặc ít hơn kể từ khi started.”**

SLE có thể được dùng để:
- Giúp người có liên quan hiểu khả năng hoàn tất **theo xác suất**, không phải một ngày chắc chắn.
- Nhận diện item có **work item age** đang tiệm cận hoặc vượt mức thường thấy.
- Hỗ trợ thảo luận loại công việc hoặc điểm nghẽn cần ưu tiên giải quyết.
- Kiểm tra liệu chính sách WIP và các bước trong luồng có hỗ trợ dự báo đáng tin hơn không.

### 10.1. Tạo SLE từ dữ liệu quá khứ

Giả sử nhóm có **40 story cùng loại** đã finished và có dấu started/finished đáng tin. Có **34 story** hoàn tất trong **8 ngày lịch hoặc ít hơn**.

~~~text
Tỷ lệ quan sát = 34 / 40 = 0,85 = 85%
SLE tham khảo = 85% story hoàn tất trong <= 8 ngày lịch
~~~

Đây là **ước lượng kinh nghiệm** dựa trên 40 item, không phải bảo đảm rằng cứ 20 item tới sẽ có đúng 17 item hoàn tất trước hạn. Nếu loại việc, chất lượng dữ liệu, chính sách started hoặc năng lực thay đổi, kỳ vọng cần được xem lại.

### 10.2. Phân biệt SLE, SLA và deadline

| Thuật ngữ | Vai trò | Điểm cần tránh nhầm |
| --- | --- | --- |
| **SLE (Service Level Expectation)** | Kỳ vọng dự báo thời gian hoàn tất dựa trên dữ liệu của dòng việc | Không mặc nhiên là lời hứa hợp đồng hoặc hạn chót mỗi item |
| **SLA (Service Level Agreement)** | Thỏa thuận mức dịch vụ giữa các bên, có thể kèm nghĩa vụ cụ thể | Không tự suy từ một percentile thống kê thành nghĩa vụ pháp lý |
| **Deadline** | Thời điểm mà một hạng mục cụ thể cần được xử lý theo mục tiêu/ràng buộc | Không phải mọi item cùng loại đều có deadline bằng SLE |

Ví dụ một lỗi an toàn phải xử lý trong ngày theo quy trình sự cố có thể cần chính sách riêng, dù SLE thường lệ của bug là một tuần. Không nên áp dụng SLE thông thường như lý do trì hoãn rủi ro đang gây hại.

### 10.3. Dùng SLE để kiểm tra các hạng mục đang già đi

Nếu SLE là “85% trong 8 ngày” và một story đang có age 10 ngày, nhóm nên hỏi:
- Nó bị chặn ở trạng thái nào và từ bao giờ?
- Phạm vi có lớn hơn story thông thường?
- Cần phối hợp review, test hay làm rõ nghiệp vụ?
- Liệu có cần trao đổi lại thứ tự hoặc cách xử lý với người phụ trách ưu tiên?
- Phải báo bên liên quan điều gì về bất định còn lại?

Không nên tự coi “age 10 > SLE 8” là một cá nhân vi phạm cam kết. **SLE dùng để phát hiện và thảo luận rủi ro**, không thay thế trách nhiệm chất lượng.

## 11. Xem điểm nghẽn qua bảng và dòng công việc

Khi DoW đã có các trạng thái, ranh giới và chính sách, nhóm có thể quan sát **dòng việc thực** để cải tiến.

### 11.1. Hàng chờ có thể là phần lớn cycle time

Giả sử một story:
- Doing: 1 ngày.
- Chờ và thực hiện Review: 3 ngày.
- Verify: 1 ngày.
- Chờ triển khai và xác minh: 3 ngày.

Tổng cycle time theo DoW từ Doing tới finished là **8 ngày lịch** (giả định các giai đoạn nối tiếp, không chồng lấp). Chỉ tối ưu 1 ngày lập trình có thể không đem lại cải thiện lớn bằng việc xử lý hàng chờ Review hoặc Release. **Đừng chỉ hỏi người lập trình làm sao nhanh hơn**; hãy hỏi item đang chờ ở đâu.

### 11.2. Phân biệt Doing và Waiting khi có ích

Một trạng thái “Review” có thể chứa:
- Một item đang chờ người nhận review.
- Một item đang được review.
- Một item đã review nhưng chờ chỉnh sửa.

Nếu việc chờ là vấn đề lặp lại, nhóm có thể tách **Waiting for review** và **Review in progress**, hoặc dùng nhãn/tín hiệu để đo trạng thái chờ. Không nhất thiết tạo thêm hai cột ngay; chỉ bổ sung độ chi tiết khi dữ liệu giúp điều hành dòng việc.

### 11.3. Phân tích blocked

Một thẻ blocked nên có:
1. Lý do và loại cản trở.
2. Thời điểm bắt đầu bị chặn.
3. Người/nhóm cần phối hợp.
4. Hành động tiếp theo và mốc kiểm tra.
5. Ảnh hưởng đến thời gian giao và hạng mục khác.

Nếu blocked chỉ là một nhãn màu đỏ nhưng không ai chịu trách nhiệm gỡ chặn, bảng vẫn thiếu chính sách hoạt động. Blocked **không tự dừng đồng hồ cycle time** trừ khi nhóm định nghĩa một chỉ số phụ riêng và nói rõ cách đo.

### 11.4. Biểu đồ dòng công việc

Khi dữ liệu đủ tin cậy, nhóm có thể dùng:
- **Cumulative Flow Diagram (CFD):** diện tích/vệt giữa các đường trạng thái giúp quan sát công việc tích lũy và chỗ tắc.
- **Cycle time scatterplot:** mỗi item hoàn tất là một điểm theo thời gian và cycle time; xem độ phân tán, xu hướng và ngoại lệ.
- **Ageing WIP chart:** quan sát những item đang mở có tuổi lớn so với mức thường thấy.
- **Throughput chart:** đếm số item finished theo tuần hoặc khoảng thích hợp.

Biểu đồ chỉ có ý nghĩa khi trạng thái phản ánh thực tế và chính sách đo ổn định. Nếu nhóm chuyển các thẻ sang Done hàng loạt vào thứ Sáu dù công việc hoàn tất nhiều ngày trước, thời gian trong biểu đồ bị biến dạng.

## 12. Vận hành DoW cùng ưu tiên, rủi ro và công việc ngoài luồng

Một bảng Kanban phải đối diện với yêu cầu gấp, công việc bất ngờ, nhiều loại việc và các quyết định ưu tiên thay đổi.

### 12.1. Định nghĩa dịch vụ cho bug và user story

Nếu bug và user story có luồng, thời gian và mức rủi ro khác nhau, nhóm có thể:

- Dùng cùng bảng nhưng gắn **work item type** rõ ràng, phân tích dữ liệu theo loại.
- Có **chính sách ưu tiên** riêng cho bug nghiêm trọng hoặc sự cố production.
- Thống nhất tiêu chí Ready/Finished theo từng loại mà không làm mơ hồ ranh giới đo.
- Tách luồng khi các yêu cầu thật sự đi qua các dịch vụ khác nhau.

Một lỗi sản xuất nghiêm trọng không nên bị xếp hàng vô thời hạn sau hàng chục story chỉ vì Ready đang đông. Cần chính sách ứng phó phù hợp và minh bạch tác động đến WIP hoặc thứ tự công việc.

### 12.2. Expedite: ngoại lệ rõ, không phải con đường dành cho mọi yêu cầu

Nhóm có thể cho phép một lớp phục vụ **expedite** dành cho việc thật sự cấp bách. Một chính sách thử:

1. Nêu mức tác động và người có quyền xác định expedite.
2. Giới hạn số expedite chạy đồng thời, chẳng hạn **tối đa một** đối với công việc thông thường, ngoại trừ ứng phó sự cố theo quy trình riêng.
3. Hiển thị rõ nó đang chiếm năng lực ở bước nào và việc nào bị lùi.
4. Vẫn bảo vệ chất lượng và các kiểm tra bắt buộc.
5. Sau khi kết thúc, đánh giá nguyên nhân, thời gian xử lý và ảnh hưởng lên các item khác.

Giới hạn “một expedite” là **ví dụ do nhóm đặt ra**, không phải luật chung. Nếu mọi yêu cầu từ quản lý đều được gọi là expedite, dòng công việc thông thường có thể bị bỏ đói và SLE sẽ kém đáng tin.

### 12.3. Không làm biến mất công việc ngoài luồng

Việc sửa môi trường CI, hỗ trợ xử lý sự cố hoặc giúp người khác gỡ chặn có thể chiếm nhiều thời gian. Nhóm nên có chính sách **ghi nhận khi công việc phát sinh ảnh hưởng đáng kể đến WIP, khả năng giao hoặc ưu tiên**.

Không nhất thiết tạo ticket cho mỗi câu hỏi hai phút; nhưng nếu công việc phát sinh khiến một story mất thêm ba ngày, phải làm rõ vì sao dữ liệu thay đổi. Không nên âm thầm thay started hoặc finished để bỏ qua thời gian gián đoạn.

### 12.4. Hệ thống có thể bao gồm vòng phản hồi sản phẩm

Theo Agile, giao phần mềm tăng dần chỉ hữu ích nếu nhóm kiểm tra xem **người dùng có nhận được lợi ích**. Finished của DoW có thể là “phần mềm đã bàn giao theo chính sách”, còn kết quả người dùng (*outcome*) thường được quan sát riêng. Ví dụ sau khi giao chức năng xem trạng thái, nhóm vẫn cần biết học viên có thực sự bớt hỏi lại ban tổ chức không.

Không nên kéo dài mọi work item vô hạn tới lúc chỉ số kinh doanh cuối cùng thay đổi; hãy **định nghĩa điểm finished phù hợp**, đồng thời duy trì một vòng học sản phẩm ngoài chỉ số dòng việc.

## 13. Kanban và Scrum: ranh giới luồng không phụ thuộc tên phương pháp

Kanban không yêu cầu Sprint cố định hay đúng một bộ cột. Một nhóm có thể áp dụng thực hành Kanban trong dòng công việc liên tục hoặc dùng chúng để hỗ trợ làm việc theo Scrum.

### 13.1. Nếu nhóm dùng Scrum

Nhóm Scrum có:
- **Product Backlog** chứa các Product Backlog items có thứ tự.
- **Sprint Backlog** gồm Sprint Goal, những PBIs được chọn và kế hoạch thực hiện.
- **Increment** đáp ứng Definition of Done.

Nếu nhóm muốn dùng DoW của Kanban, cần chọn rõ:
- **Started** có phải là lúc Developers bắt đầu thực hiện PBI hay ngay khi chọn vào Sprint Backlog?
- **Finished** có trùng “đạt DoD” hay bao gồm bước phát hành sau đó?
- Các trạng thái đang làm và WIP được kiểm soát thế nào?
- Sprint Goal chịu ảnh hưởng khi công việc bị chặn ra sao?

**Chọn vào Sprint** không tự động đồng nghĩa started theo DoW trừ khi nhóm cố tình định nghĩa như vậy. Nếu dùng ngày bắt đầu triển khai, những PBI đã chọn nhưng chưa được đụng tới không nằm trong WIP đã bắt đầu; nhưng chúng vẫn thuộc kế hoạch Sprint và cần được theo dõi với một góc nhìn phù hợp.

### 13.2. Nếu nhóm không dùng Scrum

Nhóm vẫn có thể dùng Kanban để xử lý luồng liên tục: nhận yêu cầu, ra quyết định ưu tiên, kéo việc theo WIP, quan sát hoàn tất và cải tiến chính sách. Không cần tạo “Sprint giả” chỉ để đo throughput.

Nhóm có thể tổ chức **replenishment**, **delivery planning**, **service delivery review** hoặc những nhịp kiểm tra phù hợp, nhưng những sự kiện này không thay đổi ý nghĩa started/finished đã thống nhất. Việc chọn sự kiện phải phục vụ nhu cầu điều phối và học hỏi, không phải tô thêm nghi thức.

### 13.3. XP hỗ trợ luồng hoàn tất có chất lượng

**Pair programming**, **test-driven development**, **continuous integration** và **refactoring** có thể giúp giảm lỗi, làm lại và thời gian chờ tích hợp. Một item đi từ Doing tới Finished nhanh hơn chỉ đáng mừng khi vẫn đạt điều kiện chất lượng và tạo giá trị.

Nếu bỏ review hoặc kiểm thử để giảm cycle time, nhóm đang thay đổi **định nghĩa finished** hoặc đánh đổi chất lượng, không nhất thiết cải thiện luồng thực.

## 14. Tình huống thực hành xuyên suốt: nhóm workshop định nghĩa lại DoW

### 14.1. Bối cảnh

Một nhóm bốn Developers cùng Product Owner và người hỗ trợ Scrum đang xây hệ thống đăng ký workshop. Backlog có các user story, lỗi và công việc giảm rủi ro. Hiện bảng chỉ gồm **To do – Doing – Done**.

Các thành viên có cách hiểu khác nhau:
- Minh coi Doing bắt đầu ngay khi Product Owner yêu cầu một tính năng.
- Thảo coi Doing chỉ bắt đầu khi viết dòng code đầu tiên.
- Huy đưa thẻ sang Done khi đã merge.
- Lan chỉ coi Done khi thử xong trên môi trường dành cho học viên.

Khi một học viên hỏi “từ lúc đăng ký yêu cầu đến lúc có chức năng mất bao lâu?”, nhóm không thể trả lời nhất quán.

### 14.2. Xác định dịch vụ và người dùng của số liệu

Nhóm chọn dịch vụ để cải thiện là **phát triển và phát hành các lát cắt tính năng phục vụ học viên**. Người dùng của luồng là học viên cần chức năng chạy được; Product Owner cần dự báo đáng tin; Developers cần biết đang tắc ở đâu.

Nhóm đồng ý **không gộp yêu cầu chăm sóc khách hàng ngắn hạn** vào cùng phân tích cycle time của các lát cắt phát triển. Những việc hỗ trợ vẫn được ghi nhận nếu chiếm năng lực đáng kể.

### 14.3. Định nghĩa started và finished

Nhóm thống nhất:

> **Started:** khi Developers kéo một user story đã có tình huống nghiệp vụ cơ bản từ Ready vào Doing và ghi thời điểm; item bắt đầu chiếm WIP.
>
> **Finished:** khi story đạt DoD, được triển khai tới môi trường người dùng mục tiêu và đã xác minh luồng chính sau triển khai theo chính sách.

Với định nghĩa này, việc một thẻ nằm trong Ready bảy ngày **không được tính vào cycle time từ started**, nhưng có thể đo riêng để hiểu thời gian chờ người dùng từ lúc gửi yêu cầu.

### 14.4. DoW đầy đủ để nhóm thử

| Thành phần | Chính sách thử trong 2 tuần |
| --- | --- |
| Work item | Một user story có hành vi có thể kiểm chứng; bug ghi loại riêng |
| Before started | Intake → Ready; ưu tiên và câu hỏi nghiệp vụ được làm rõ |
| Started | Kéo item vào Doing theo chính sách pull |
| Trạng thái thực hiện | Doing → Review → Verify → Release |
| Finished | Kiểm tra sau triển khai đạt; item chuyển Done |
| WIP | Doing tối đa 3, Review tối đa 2, Verify tối đa 2, Release tối đa 1 |
| Blocked | Vẫn tính WIP, ghi lý do, thời điểm chặn và người cần hỗ trợ |
| Rework | Quay về bước phù hợp, không reset started |
| Cancelled | Ghi quyết định và liên kết; không tính completed throughput |
| SLE sơ bộ | Tạm dùng kịch bản từ dữ liệu đo thử; chưa tuyên bố percentile khi chưa có lịch sử đáng tin |
| Kiểm tra lại | Xem work item age mỗi ngày; họp cải tiến chính sách sau 2 tuần |

Đây là ví dụ tổ chức **để học từ dữ liệu**, không phải quy tắc cố định cho mọi nhóm Kanban.

### 14.5. Một item đi qua dòng công việc

User story WK-142:

> Là học viên đã gửi yêu cầu đăng ký, tôi muốn xem trạng thái đúng của đăng ký thuộc về mình, để biết đang chờ hay đã có chỗ.

Dòng công việc giả định:

1. **Intake:** Product Owner ghi nhận phản hồi nhiều học viên hỏi lại trạng thái.
2. **Ready:** nhóm làm rõ quyền truy cập, trạng thái và trường hợp ngoại lệ.
3. **Started ở Doing:** Developers bắt đầu lát cắt nhỏ, ghi mốc thời gian.
4. **Review:** phát hiện việc kiểm tra quyền truy cập chưa đúng; item quay lại Doing.
5. **Verify:** kiểm thử trường hợp đúng quyền và không có quyền.
6. **Release:** triển khai và xác minh trạng thái hiển thị đúng cho người dùng mục tiêu.
7. **Finished ở Done:** item đáp ứng toàn bộ điều kiện kết thúc; thời gian từ Doing đầu tiên đến Done được tính là cycle time.

**Thời gian quay lại Doing do lỗi phải được giữ trong cycle time**. Nếu lờ nó đi, dữ liệu sẽ không phản ánh chi phí phải làm lại và nhóm có thể bỏ qua một vấn đề chất lượng quan trọng.

### 14.6. Quan sát sau hai tuần

Nhóm nhận thấy nhiều item bị chặn ở Review vì chỉ một người quen hệ thống phân quyền. Họ có thể thử:
- Chia sẻ kiến thức về kiểm tra quyền, review theo cặp.
- Thực hiện kiểm thử tự động cho tình huống không có quyền.
- Giới hạn số việc mới bắt đầu khi Review đang đầy.
- Kiểm tra thay đổi cycle time, WIP và lỗi trong các kỳ tiếp theo.

Không nên kết luận ngay “đội làm chậm vì review” nếu chưa xem loại item và các phụ thuộc. Chính sách mới cần được **kiểm chứng bằng kết quả**, không chỉ bằng số thẻ chuyển cột.

## 15. Các phản ví dụ và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi “đã đưa vào backlog” là started mà không công bố | Cycle time lẫn thời gian chờ trước khi làm | Chọn ranh giới started theo dịch vụ và ghi rõ |
| Mỗi thành viên có tiêu chuẩn started riêng | Dữ liệu không tái lập được | Dùng chính sách chuyển trạng thái có điều kiện quan sát |
| Coi “code complete” là finished trong khi nhóm đo tới phát hành | Báo giao sớm hơn thực tế | Đưa kiểm thử, release và xác minh vào luồng hoặc đổi phạm vi đo minh bạch |
| Chuyển blocked ra khỏi WIP | Che thời gian chờ và sức chứa bị chiếm | Giữ started, hiển thị blocked và hành động gỡ chặn |
| Reset ngày started khi item quay về Doing | Cycle time trông ngắn giả tạo | Giữ dấu mốc đầu tiên, ghi rõ vòng làm lại |
| Đếm item hủy/trùng như giao giá trị | Throughput tăng nhưng người dùng không nhận thêm gì | Tách loại kết quả theo dịch vụ |
| Dùng cùng SLE cho bug khẩn và story thường | Dự báo không phản ánh loại dịch vụ | Phân loại và lập kỳ vọng thích hợp |
| Có WIP limit nhưng luôn phá khi có yêu cầu mới | Bắt đầu nhiều, hoàn tất chậm, khó dự báo | Công khai chính sách pull và expedite |
| Bảng quá ít cột, chỗ chờ bị ẩn | Không tìm ra điểm nghẽn | Thêm tín hiệu hoặc trạng thái chờ khi có nhu cầu |
| Bảng quá nhiều cột, mọi bước đều bị quản lý vi mô | Chi phí cập nhật cao, ít giá trị quyết định | Đơn giản hóa theo các điểm chuyển có ý nghĩa |
| Đổi ranh giới mà vẫn so biểu đồ cũ như nhau | Tưởng cải tiến dù chỉ đổi cách đo | Ghi ngày thay đổi DoW, giải thích lại dữ liệu trước/sau |
| Đánh đổi kiểm thử lấy cycle time thấp | Giảm chất lượng, gây sửa lại và mất niềm tin | Giữ tiêu chuẩn finished, theo dõi lỗi và outcome |
| Chỉ nhìn cycle time các item đã finished | Bỏ sót item đang mắc lâu, gây thiên lệch | Xem cả work item age của WIP hiện tại |
| Ép tất cả công việc vào một item type | Trung bình và SLE thiếu ý nghĩa | Phân loại loại việc hoặc chia theo dịch vụ |
| Tự động hóa bảng nhưng không xác nhận trạng thái thật | Dữ liệu không đáng tin | Kiểm tra thói quen cập nhật và vết thời gian |
| Xem cải thiện số liệu là mục tiêu cuối | Flow nhanh hơn nhưng chức năng không có giá trị | Kết nối với nhu cầu người dùng, chất lượng và phản hồi sản phẩm |

## 16. Bài thực hành: tự định nghĩa một luồng Kanban

### 16.1. Bài A – Chọn ranh giới (15 phút)

Một nhóm nhận yêu cầu sửa lỗi từ bộ phận hỗ trợ. Quy trình thực tế:

1. Khách hàng gửi lỗi vào hệ thống hỗ trợ.
2. Nhân viên xác nhận thông tin cơ bản.
3. Product Owner sắp thứ tự trong backlog.
4. Developers kéo item và bắt đầu điều tra.
5. Có lúc chờ người khác xác nhận nguyên nhân.
6. Mã được review, tích hợp và kiểm thử.
7. Thay đổi được triển khai, kiểm tra với người dùng phù hợp.
8. Nhóm đóng item.

Hãy đề xuất **hai DoW khác nhau**:
- **Luồng A:** dịch vụ phát triển và triển khai, started ở bước 4, finished ở bước 7/8 theo chính sách.
- **Luồng B:** dịch vụ tiếp nhận và phân loại, started khi yêu cầu vào bước 1, finished khi có quyết định phân loại/điều hướng rõ ràng ở bước 3 hoặc mốc đã thống nhất.

Giải thích vì sao cycle time của hai luồng **không nên so trực tiếp** và người dùng mỗi luồng muốn biết thông tin gì.

### 16.2. Bài B – Đếm WIP và tìm điểm nghẽn (15 phút)

Nhóm có các trạng thái sau, started khi kéo vào Doing và finished khi xác minh triển khai:

| Trạng thái | Work items |
| --- | --- |
| Intake | A, B |
| Ready | C, D |
| Doing | E, F |
| Review | G, H (H bị blocked) |
| Verify | I |
| Release | J |
| Done | K, L |

Yêu cầu:
1. Xác định item nào đã started nhưng chưa finished.
2. Tính **WIP tại thời điểm quan sát**.
3. Nếu Review có WIP limit bằng 2, nhóm nên phản ứng thế nào khi muốn đẩy E sang Review?
4. H có nên được loại khỏi WIP vì blocked không?
5. Nếu đội có khả năng hỗ trợ review, hành động nào giúp **hoàn tất việc đã bắt đầu** hơn là kéo thêm item?

**Gợi ý:** WIP gồm **E, F, G, H, I, J = 6 item**. Review có G và H, đã đạt giới hạn 2. Nhóm nên ưu tiên gỡ chặn hoặc hoàn tất một item trong Review theo chính sách; **H vẫn tính WIP**.

### 16.3. Bài C – Tính thời gian từ mốc chuẩn (15 phút)

Giả định các ngày là mốc **ngày lịch**, cùng giờ:

| Item | Arrival | Started | Finished / hiện tại |
| --- | ---: | ---: | --- |
| P | 1 | 3 | 8 |
| Q | 2 | 5 | 11 |
| R | 4 | 7 | Chưa finished, hiện là ngày 13 |

Yêu cầu:
1. Tính **cycle time** cho P và Q.
2. Tính thời gian từ **arrival đến finished** của P và Q.
3. Tính **work item age** của R tại ngày 13.
4. Có được đưa R vào phân bố cycle time của các item đã finished không?
5. Nếu nhóm bắt đầu tính started ngay từ arrival từ tháng sau, cần làm gì khi so sánh lịch sử?

**Gợi ý:** P cycle time **8 − 3 = 5 ngày**, từ arrival **8 − 1 = 7 ngày**. Q cycle time **11 − 5 = 6 ngày**, từ arrival **11 − 2 = 9 ngày**. R work item age **13 − 7 = 6 ngày**. R chưa có cycle time cuối cùng; phải theo dõi như WIP đang mở. Thay đổi started là **thay đổi định nghĩa đo**, cần ghi nhận và không so trực tiếp như chuỗi số liệu hoàn toàn nhất quán.

### 16.4. Bài D – Diễn giải SLE (15 phút)

Nhóm có 30 hạng mục cùng loại đã finished, trong đó 24 mục hoàn tất trong **6 ngày lịch hoặc ít hơn** kể từ started.

1. Tính tỷ lệ quan sát.
2. Viết một câu SLE có nêu đơn vị và tỷ lệ.
3. Một item hiện age 8 ngày, đang chờ review. Nhóm nên làm gì?
4. SLE 80% trong 6 ngày có nghĩa tất cả item trễ ngày thứ bảy đều “vi phạm hợp đồng” không?
5. Cần thu thêm dữ liệu nào trước khi áp dụng SLE đó cho các lỗi khẩn?

**Gợi ý:** 24/30 = **80%**. Có thể phát biểu “Trong lịch sử 30 item cùng loại, 80% hoàn tất từ started đến finished trong 6 ngày lịch hoặc ít hơn.” Đây là **kỳ vọng có điều kiện theo dữ liệu**; không phải SLA pháp lý hay lời hứa cho mọi item.

### 16.5. Bài E – Phác thảo DoW của chính nhóm (20 phút)

Làm theo nhóm nhỏ. Viết một DoW có:
- Dịch vụ đang đo và người dùng kết quả.
- Loại work item và quy tắc chia kích thước.
- Điểm **started** cụ thể, có thể ghi dấu thời gian.
- Điểm **finished** cụ thể, có điều kiện chất lượng.
- Tối thiểu ba trạng thái có ý nghĩa trong luồng.
- Chính sách chuyển trạng thái, pull và WIP.
- Cách xử lý blocked, rework, cancellation và expedite.
- Một đề xuất SLE nếu dữ liệu lịch sử đủ tin cậy, hoặc kế hoạch thu thập dữ liệu nếu chưa đủ.
- Hai chỉ số dòng việc và một tín hiệu giá trị người dùng.
- Mốc xem lại DoW sau khi dùng thử.

Yêu cầu một nhóm khác **đọc DoW rồi tự phân loại năm thẻ giả định**. Nếu hai người khác nhau về started/finished, hãy sửa chính sách để rõ hơn.

### 16.6. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Ranh giới công việc** | Không rõ work item hoặc lẫn nhiều loại | Loại item rõ, có started/finished quan sát được | Chọn ranh giới theo dịch vụ và tách các mốc khác khi cần |
| **Chính sách luồng** | Chỉ có tên cột | Có điều kiện chuyển, WIP và blocked | Có phương án rework, hủy, expedite và quyền quyết định |
| **Đo lường** | Dùng số liệu nhưng không rõ mốc | Tính đúng WIP, age, cycle time, throughput | Có SLE kèm điều kiện, giải thích được sai lệch |
| **Cải tiến** | Tối ưu làm nhanh cho từng cá nhân | Nhìn hàng chờ, WIP và ưu tiên hoàn tất | Thử thay đổi có thể kiểm chứng bằng flow, chất lượng và outcome |
| **Gắn Agile** | Chỉ tối ưu bảng công việc | Kết nối với giao lát cắt có giá trị | Dùng phản hồi sản phẩm và kỹ thuật để thay đổi DoW có căn cứ |

## 17. Mẫu có thể dùng ngay

### 17.1. Definition of Workflow một trang

~~~text
Tên dịch vụ / phạm vi:
Đối tượng nhận kết quả:
Các loại work item:
Điều kiện để work item đủ nhỏ và rõ:
Trước started có những trạng thái nào:
STARTED = sự kiện nào, ai ghi, thời điểm nào:
Trạng thái từ started tới finished:
FINISHED = sự kiện nào, tiêu chuẩn chất lượng nào:
Các trạng thái sau finished (nếu có):
WIP limit theo cột / toàn luồng:
Chính sách pull và ưu tiên:
Điều kiện chuyển trạng thái:
Cách đánh dấu blocked và gỡ chặn:
Cách ghi rework / reopen / cancelled:
Chính sách expedite hoặc xử lý sự cố:
Dữ liệu cần ghi: arrival, started, finished, trạng thái, blocker:
SLE: tỷ lệ, ngưỡng thời gian, đơn vị, loại việc, nguồn dữ liệu:
Khi nào kiểm tra lại và ai cùng tham gia:
~~~

### 17.2. Phiếu phân tích một item bị chậm

~~~text
Mã và loại item:
Đối tượng/nghiệp vụ nhận giá trị:
Arrival:
Started:
Trạng thái hiện tại:
Work item age hiện tại:
SLE áp dụng (nếu có):
Bước đang chờ và thời điểm bắt đầu chờ:
Phụ thuộc / blocker:
Điều kiện để tiến lên bước kế tiếp:
Người có thể phối hợp:
Quyết định hôm nay:
Ngày xem lại:
Cần cập nhật người liên quan thế nào:
~~~

### 17.3. Phiếu kiểm tra chất lượng số liệu

~~~text
Khoảng thời gian phân tích:
Dịch vụ và work item type:
Definition of Workflow phiên bản nào:
Started là mốc gì:
Finished là mốc gì:
Thời gian tính theo lịch hay ngày làm việc:
Hạng mục chưa finished được xử lý thế nào:
Hạng mục hủy/trùng có được tách không:
Có item reopened hay chuyển loại không:
Có thay đổi trạng thái hoặc quy ước trong kỳ không:
Đã kiểm tra dữ liệu bị thiếu/sai thời gian chưa:
Điều có thể và chưa thể kết luận từ các số liệu:
~~~

## 18. Checklist trước khi dùng bảng và số liệu Kanban

**Định nghĩa dịch vụ và ranh giới:**

- [ ] Nhóm biết dịch vụ nào đang được cải thiện và ai nhận kết quả.
- [ ] Work item có loại và mức kích thước phù hợp để theo dõi.
- [ ] Điểm **started** là một sự kiện cụ thể, được mọi người hiểu giống nhau.
- [ ] Điểm **finished** có điều kiện hoàn tất và chất lượng rõ.
- [ ] Arrival, commitment, started, đạt DoD và released không bị đánh đồng khi chúng khác nhau.
- [ ] Các trạng thái trước started và sau finished được phân biệt khỏi WIP.
- [ ] Luồng đã phản ánh hàng chờ và việc làm lại thực tế, không chỉ quy trình lý tưởng.

**Vận hành dòng công việc:**

- [ ] Các chính sách chuyển trạng thái có thể quan sát và kiểm tra.
- [ ] Có cách điều phối pull và kiểm soát WIP tại những bước cần thiết.
- [ ] Item bị blocked vẫn được nhìn thấy và xử lý theo chính sách.
- [ ] Rework không làm mất ngày started hoặc tạo completed throughput giả.
- [ ] Hủy, trùng, chuyển phạm vi và mở lại có kết quả/nhãn rõ.
- [ ] Công việc khẩn và ngoài luồng có cách tiếp nhận, không âm thầm phá WIP.
- [ ] Các loại công việc rất khác nhau có thể được đo riêng nếu cần.

**Đo lường và cải tiến:**

- [ ] WIP được đếm từ started đến trước finished.
- [ ] Cycle time chỉ tính sau khi item finished; work item age dành cho item còn mở.
- [ ] Throughput đếm item finished trong khoảng thời gian và tập item nhất quán.
- [ ] Đơn vị ngày lịch/giờ/ngày làm việc được ghi rõ khi tính thời gian.
- [ ] SLE có tỷ lệ, ngưỡng, loại item và nguồn dữ liệu; không gọi đó là lời hứa chắc chắn.
- [ ] Khi thay started/finished hoặc chính sách, nhóm ghi nhận thay đổi và diễn giải lịch sử đúng.
- [ ] Nhóm xem các item già đi và điểm nghẽn thay vì chỉ báo cáo item đã hoàn tất.
- [ ] Cải tiến WIP/chính sách được kiểm tra bằng thời gian giao, chất lượng và giá trị người dùng.
- [ ] Bảng Kanban tạo cơ sở cộng tác và ra quyết định, không trở thành công cụ chấm điểm cá nhân.

**Kết luận:** Một luồng Kanban đáng tin bắt đầu bằng câu hỏi **“Công việc nào đang được theo dõi, nó bắt đầu được tính từ đâu và kết thúc thực sự ở đâu?”**. Khi những ranh giới này được định nghĩa cùng trạng thái, WIP, chính sách và kỳ vọng thời gian hoàn tất, nhóm có thể nhìn thấy việc chờ, đo tiến triển nhất quán, xử lý tắc nghẽn và cải tiến liên tục. Giá trị của Kanban không nằm ở số cột hay số thẻ chuyển sang Done, mà ở khả năng **đưa công việc có ích qua hệ thống một cách minh bạch, dự báo tốt hơn và nhận phản hồi sớm mà vẫn bảo vệ chất lượng**.
