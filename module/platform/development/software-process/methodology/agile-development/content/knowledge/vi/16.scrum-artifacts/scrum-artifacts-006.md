# Xây dựng nhiều Increment cùng khả năng tích hợp trong một Sprint

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Increment** trong Scrum là gì, vì sao **một Sprint có thể tạo nhiều Increment** và điều kiện để mỗi Increment được xem là hoàn thành.
2. Phân biệt **Product Backlog Item, task, commit, build, Increment, triển khai (deployment) và phát hành (release)**; không nhầm số lần đẩy code với số Increment có giá trị.
3. Chia một mục tiêu sản phẩm thành các **lát cắt chức năng xuyên suốt** có thể tích hợp, sử dụng và kiểm chứng tăng dần.
4. Vận dụng **Definition of Done, kiểm thử tự động, tích hợp liên tục, quản lý phụ thuộc, kiểm thử hợp đồng và chiến lược triển khai an toàn** để bảo đảm các Increment mới hoạt động cùng các Increment trước.
5. Thiết kế một Sprint có nhiều cơ hội nhận phản hồi nhưng vẫn giữ **Sprint Goal**, minh bạch trạng thái chất lượng, và không biến Sprint Review thành cổng bắt buộc của việc phát hành.

## 1. Tư duy nền tảng: Increment là bước tiến có thể sử dụng

Trong Scrum, **Increment** là một bước tiến cụ thể hướng tới **Product Goal**. Mỗi Increment bổ sung vào những Increment trước đó; các phần phải được **xác minh kỹ lưỡng để hoạt động cùng nhau**. Để mang lại giá trị, Increment phải **sử dụng được** (*usable*).

Một Sprint không bị giới hạn ở **đúng một Increment**. Nhóm có thể tạo **nhiều Increment trong một Sprint**, miễn từng phần được tích hợp, đáp ứng tiêu chuẩn chất lượng và không làm mất khả năng sử dụng của sản phẩm hiện có.

> **Điểm then chốt:** Tạo nhiều Increment không có nghĩa tăng số lần chia task hoặc báo cáo “xong”. Nó có nghĩa tạo ra nhiều bước tiến **đã hoàn thành thật sự**, có thể kiểm tra trong hệ thống tích hợp và góp vào mục tiêu sản phẩm.

### Ví dụ mở đầu

Một Scrum Team phát triển nền tảng học trực tuyến với mục tiêu giúp học viên **tiếp tục bài học đã dừng**:

- **Increment A:** Học viên đã đăng nhập nhìn thấy và mở được bài gần nhất từ trang chủ, trong phạm vi thiết bị và dữ liệu hiện tại.
- **Increment B:** Khả năng này được mở rộng để học viên truy cập tiến độ đã xác nhận khi đăng nhập trên thiết bị khác.
- **Increment C:** Học viên nhận thông tin rõ ràng khi việc lưu tiến độ chưa được xác nhận và có thể thử lại theo quy tắc đã thống nhất.

Đây là ba **lát cắt giá trị tăng dần** có thể được tạo trong cùng một Sprint. Nhưng có một điều kiện bắt buộc: **A phải được bảo vệ phân quyền, dữ liệu và xử lý lỗi an toàn ngay khi hoàn thành**; đội không được để đến C mới khắc phục một nguy cơ làm lộ dữ liệu hoặc thông báo thành công giả. B và C phải hoạt động cùng A, chứ không chỉ demo riêng trong nhánh code khác nhau.

### Vì sao cách làm này phù hợp Agile?

Phát triển sản phẩm thích ứng dựa trên **phản hồi sớm, giao tăng dần và cải tiến liên tục**. Nếu có một phần chức năng dùng được sớm, đội có thể kiểm chứng hành vi, phát hiện rủi ro tích hợp và thay đổi thứ tự Product Backlog dựa trên thông tin mới.

Tuy nhiên, không phải **càng nhiều Increment càng tốt**. Số lượng chỉ có ý nghĩa khi từng Increment đem lại một bước tiến rõ ràng và không tạo chi phí phối hợp hoặc kiểm thử không cần thiết.

## 2. Phân biệt Increment với những thứ dễ bị nhầm

| Thuật ngữ | Là gì? | Có tự động là Increment không? |
| --- | --- | --- |
| **Product Backlog Item (PBI)** | Hạng mục được sắp thứ tự trong Product Backlog, mô tả công việc cần để cải tiến sản phẩm. | **Không.** Một PBI chỉ trở thành một phần của Increment khi hoàn thành theo DoD. |
| **Task kỹ thuật** | Bước thực hiện như tạo bảng dữ liệu, chỉnh API, thiết kế UI, viết test. | **Không.** Xong riêng một lớp kỹ thuật thường chưa tạo ra một bước tiến sản phẩm dùng được. |
| **Commit hoặc pull request** | Thay đổi mã nguồn được lưu hoặc đề nghị nhập vào nhánh chung. | **Không.** Code có thể chưa tích hợp, chưa kiểm thử hoặc chưa thể sử dụng. |
| **Build xanh** | Bản build vượt các kiểm tra đang cấu hình. | **Chưa chắc.** Pipeline có thể thiếu test quan trọng, hoặc build không có giá trị người dùng mới. |
| **Increment** | Bước tiến cụ thể, bổ sung vào sản phẩm, hoạt động cùng những phần trước, sử dụng được và đáp ứng DoD. | **Có**, khi đủ các điều kiện trên. |
| **Deployment** | Đưa một phiên bản phần mềm tới môi trường, ví dụ staging hoặc production. | **Không đồng nhất.** Deploy có thể chỉ là thao tác kỹ thuật, không thêm Increment mới. |
| **Release** | Cho người dùng/bên liên quan sử dụng một khả năng hoặc phiên bản theo chính sách phát hành. | **Không đồng nhất.** Một Increment có thể được phát hành trước Sprint Review; có thể tích lũy nhiều Increment trước một lần release. |

### Ba câu hỏi kiểm tra

Khi nghe “đã có Increment mới”, hãy hỏi:

1. **Sản phẩm hiện làm được điều gì có ích hoặc đáng tin cậy hơn?**
2. **Phần mới có chạy cùng phần sản phẩm đang có và thỏa Definition of Done không?**
3. **Có bằng chứng kiểm chứng trên môi trường tích hợp phù hợp không, hay mới chỉ chạy trên máy cá nhân?**

Việc tạo một API nhưng chưa có luồng sử dụng, chưa tích hợp và chưa được xác minh theo DoD không mặc nhiên được gọi là Increment. Ngược lại, một thay đổi giảm lỗi nghiêm trọng hoặc nâng khả năng vận hành có thể là bước tiến có giá trị dù không thêm nút giao diện, miễn thật sự hoàn tất và phù hợp với mục tiêu sản phẩm.

## 3. Quan hệ giữa Product Goal, Sprint Goal, Increment và DoD

Scrum có ba tạo tác, mỗi tạo tác có một cam kết:

| Tạo tác | Cam kết | Vai trò đối với nhiều Increment |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Chỉ ra hướng đi dài hơn mà các bước tiến cần đóng góp. |
| **Sprint Backlog** | **Sprint Goal** | Cho đội một mục tiêu chung để lựa chọn và điều chỉnh công việc trong Sprint. |
| **Increment** | **Definition of Done** | Tạo chuẩn thống nhất để biết phần sản phẩm nào đã thực sự hoàn thành. |

Một Sprint có thể tạo nhiều Increment nhưng **vẫn có một Sprint Goal**. Những Increment đó không nhất thiết phải là các tính năng giống nhau; chúng nên đóng góp cho mục tiêu Sprint hoặc nghĩa vụ cần xử lý một cách minh bạch.

~~~mermaid
flowchart TD
    PG["Product Goal: học viên tiếp tục học đáng tin cậy"] --> PB["Product Backlog: các cơ hội, lỗi, cải tiến"]
    PB --> SP["Sprint Planning: xác định một Sprint Goal"]
    SP --> SB["Sprint Backlog: Goal + item được chọn + kế hoạch"]
    SB --> A["Increment A: mở bài gần nhất"]
    A --> B["Increment B: tiếp tục trên thiết bị khác"]
    B --> C["Increment C: hỗ trợ trạng thái lưu/khôi phục"]
    DOD["Definition of Done"] --> A
    DOD --> B
    DOD --> C
    A --> QA["Tích hợp và xác minh toàn hệ thống"]
    B --> QA
    C --> QA
    QA --> FB["Phản hồi và kiểm tra kết quả"]
    FB --> PB
~~~

Sơ đồ minh họa một cách xây dựng, **không phải quy định A, B, C phải phát triển hoàn toàn tuần tự** hoặc mỗi Increment phải trải qua một Sprint Planning riêng. Các nhóm có thể hợp tác và tích hợp nhiều thay đổi thường xuyên, miễn trạng thái hoàn thành và quan hệ với sản phẩm hiện tại luôn được kiểm chứng.

### Cam kết chất lượng không thể hoãn đến cuối Sprint

Nếu Increment A chỉ chạy được khi tắt kiểm tra phân quyền, A chưa đạt chất lượng cần thiết và **không được gọi là Increment Done**. Không có “DoD tạm” cho phần đầu Sprint và “DoD thật” cho cuối Sprint để che các sai sót.

DoD mô tả trạng thái của Increment khi đáp ứng những tiêu chuẩn chất lượng cần có. Nếu tổ chức đã có chuẩn DoD, Scrum Team phải tuân theo mức tối thiểu đó; nếu chưa có, Scrum Team định nghĩa DoD phù hợp. Nếu nhiều Scrum Team cùng làm một sản phẩm, họ cần **cùng định nghĩa và tuân thủ một DoD**.

## 4. Nhiều Increment không đồng nghĩa nhiều release

Trong Scrum, **nhiều Increment có thể được tạo trong một Sprint**. Tổng các Increment là cơ sở để kiểm tra kết quả tại **Sprint Review**. Một Increment cũng **có thể được giao cho các bên liên quan trước khi Sprint kết thúc**. Sprint Review **không phải cổng bắt buộc** để được release giá trị.

### Các tình huống hợp lệ

| Tình huống | Có thể xảy ra không? | Điều kiện |
| --- | --- | --- |
| Tạo ba Increment trong Sprint, release cả ba ở cuối Sprint | Có | Mỗi Increment đáp ứng DoD, hoạt động cùng các phần trước; release tuân thủ chính sách sản phẩm. |
| Tạo Increment A và giao cho nhóm người dùng thử trước Sprint Review | Có | Đã đạt DoD, có quyền và điều kiện phát hành phù hợp; các yêu cầu pháp lý/vận hành được đáp ứng. |
| Deploy hai lần nhưng không thêm khả năng sản phẩm hoặc bước tiến đạt DoD | Có | Đó có thể chỉ là hoạt động triển khai, không nhất thiết có hai Increment. |
| Hoàn thành năm task nhưng không có luồng tích hợp dùng được | Có thể có nhiều task Done | Chưa đủ bằng chứng để gọi là Increment nếu DoD hoặc tính sử dụng chưa đạt. |
| Merge nhánh mới dù làm hỏng chức năng cũ | Không đáp ứng tiêu chuẩn Increment | Phải sửa lỗi và xác minh hệ thống hoạt động với phần trước. |
| Có Increment đạt DoD nhưng hoãn release vì lịch kinh doanh | Có | Cần minh bạch sự khác biệt giữa “usable increment” và “đã phát hành”; xem xét rủi ro tồn đọng. |

**Increment không có nghĩa mọi thay đổi phải tự động đưa lên production.** Scrum nói về trạng thái sản phẩm và khả năng kiểm tra giá trị; quyết định release còn có thể chịu những nghĩa vụ vận hành, kiểm định, hợp đồng hoặc thời điểm kinh doanh.

### Feature flag có ích nhưng không thay thế DoD

Một đội có thể tích hợp code của khả năng mới dưới **feature flag** để giảm rủi ro triển khai dần. Tuy nhiên:

- Cấu hình đang bật và tắt cần được kiểm thử phù hợp.
- Nếu người dùng được phép sử dụng phần mới, phần đó phải đáp ứng tiêu chuẩn chất lượng áp dụng.
- Không thể gọi một đoạn code chưa dùng được là Increment hoàn thành **chỉ vì đã nằm trong nhánh chính sau feature flag**.
- Cần có người quản lý vòng đời flag, tránh tích lũy điều kiện và nợ cấu hình kéo dài.

## 5. Chia công việc theo lát cắt giá trị xuyên suốt

Muốn có nhiều Increment trong một Sprint, nhóm cần chọn phạm vi có thể **hoàn thiện từ đầu đến cuối** thay vì đợi từng bộ phận giao xong tầng kỹ thuật.

### Chia theo tầng kỹ thuật và theo giá trị

| Chia theo tầng | Vấn đề thường gặp | Chia theo lát cắt xuyên suốt |
| --- | --- | --- |
| Tuần đầu hoàn thành cơ sở dữ liệu; tuần sau API; cuối Sprint mới xây UI | Chưa thể xác minh hành vi người dùng đến rất muộn; lỗi hợp đồng tích hợp bị phát hiện sát hạn | Đầu tiên tạo luồng đọc và mở **một bài hợp lệ** từ UI qua API đến dữ liệu, với kiểm thử cần thiết |
| Tất cả phần backend đều được coi là “Done” dù UI và quyền truy cập chưa hoạt động | Không minh bạch trạng thái Increment | Hạng mục Done khi người dùng/đối tượng nghiệp vụ có khả năng sử dụng đã xác nhận |
| Các đội con tối ưu chỉ tiêu riêng từng tầng | Handover, chờ đợi và sửa lại tăng | Developers phối hợp đa kỹ năng để hoàn thành một lát cắt trước khi khởi động quá nhiều lát cắt khác |

**Lát cắt giá trị** có thể nhỏ nhưng phải thật:

- Một nhóm người dùng được xác định có thể thực hiện một thao tác có ý nghĩa.
- Phần giao diện, dữ liệu, nghiệp vụ, bảo mật và kiểm thử liên quan đã tích hợp.
- Không làm hỏng luồng sản phẩm đang dùng.
- Có thể cho thấy kết quả và nhận phản hồi, kể cả chỉ từ một nhóm người dùng phù hợp.

Một task “tạo endpoint” hoàn toàn có thể cần thiết, nhưng nó là **công việc bên trong lát cắt**, không phải lúc nào cũng là Increment riêng.

### Chiến lược chia nhỏ khả thi

1. **Theo trường hợp sử dụng:** Người dùng mở bài đã lưu; sau đó mở bài từ thiết bị khác.
2. **Theo nhóm người dùng:** Học viên cá nhân trước; sau đó quản trị viên xem báo cáo liên quan, nếu hai luồng có giá trị độc lập và được phân quyền.
3. **Theo biến thể nghiệp vụ:** Một loại khóa học hoặc bài học hợp lệ trước; sau đó mở rộng các loại dữ liệu khác.
4. **Theo mức rủi ro:** Xây khả năng xử lý gửi yêu cầu lặp an toàn trước khi mở rộng đồng bộ offline.
5. **Theo khả năng vận hành:** Thêm cảnh báo hữu ích và kiểm soát lỗi cho luồng đang có như một bước tiến chất lượng được kiểm chứng.

Không chia theo cách **đưa phần nguy hiểm sang Increment sau**. Ví dụ, nếu increment đầu đọc tiến độ thì phải kiểm tra đúng danh tính và quyền truy cập ngay từ đầu.

## 6. Definition of Done: chuẩn chung cho từng Increment

**Definition of Done** làm rõ điều kiện mà một Increment phải đáp ứng để có thể gọi là hoàn thành. Tiêu chí có thể thay đổi theo sản phẩm, nhưng không nên dựa trên việc team có đủ thời gian hay không để “nới chuẩn”.

### Ví dụ DoD cho nền tảng học trực tuyến

| Nhóm điều kiện | Bằng chứng phù hợp | Lưu ý |
| --- | --- | --- |
| **Hành vi nghiệp vụ** | Tiêu chí chấp nhận của PBI được kiểm chứng qua những ví dụ quan trọng | Acceptance criteria là nội dung riêng từng story, không thay DoD chung. |
| **Tích hợp** | Thay đổi đã kết hợp với mã nguồn và các thành phần liên quan, build và test tích hợp đạt | Không chỉ chạy trên máy cá nhân hoặc nhánh tách biệt. |
| **Kiểm thử hồi quy** | Các kiểm thử phù hợp xác nhận hành vi trước vẫn đúng | Lựa chọn lớp test theo rủi ro, không mặc định mọi thứ phải chạy UI E2E. |
| **Dữ liệu và bảo mật** | Quyền truy cập, tính toàn vẹn, xử lý dữ liệu nhạy cảm được kiểm tra trong phạm vi tác động | Không bỏ điều kiện bắt buộc để giữ nhịp giao. |
| **Khả năng vận hành** | Cấu hình, log/metric, giám sát, triển khai và khôi phục được chuẩn bị khi cần | Mức độ phụ thuộc tác động và môi trường. |
| **Tiêu chuẩn kỹ thuật** | Review cần thiết, pipeline đạt, chất lượng mã và yêu cầu tổ chức được đáp ứng | Các kiểm tra phải mang ý nghĩa, không là hộp đánh dấu hình thức. |
| **Tài liệu và nghĩa vụ** | Thông tin hỗ trợ, thay đổi API, migration, hồ sơ bắt buộc được cập nhật nếu liên quan | Tính đúng đắn và nghĩa vụ phải đi kèm từng bước phát hành. |

Đây là **DoD minh họa**, không phải danh sách bắt buộc Scrum Guide quy định cho mọi đội.

### Acceptance Criteria khác DoD

User story:

> **Là** học viên đã đăng nhập, **tôi muốn** mở bài gần nhất từ trang chủ **để** tiếp tục học mà không phải tìm kiếm.

**Tiêu chí chấp nhận riêng:**

- Khi có tiến độ hợp lệ, nút mở đúng bài gần nhất.
- Khi không có tiến độ, không hiển thị bài giả.
- Tài khoản B không nhìn thấy dữ liệu tiến độ riêng của A.

**DoD chung:** Phần thay đổi được tích hợp, có kiểm thử phù hợp, không làm hỏng chức năng cũ, đáp ứng tiêu chuẩn bảo mật và chất lượng sản phẩm.

Một story chỉ được xem hoàn thành khi cả **hành vi riêng** lẫn **chất lượng chung** được đáp ứng.

## 7. Khả năng tích hợp: điều kiện giúp nhiều Increment tồn tại cùng nhau

Nếu Increment A và B chạy riêng nhưng không hoạt động cùng nhau, team chưa có hai bước tiến sản phẩm đúng nghĩa. Vấn đề cốt lõi là **khả năng tích hợp liên tục** (*integration capability*).

### Bảy năng lực thực hành

1. **Mã nguồn chung có kiểm soát:** Tránh để các nhánh sống tách biệt quá lâu, khiến lúc nhập mới thấy xung đột hoặc sai API.
2. **Build có thể tái lập:** Thay đổi được build trong môi trường nhất quán, không phụ thuộc cấu hình riêng không công khai của một máy.
3. **Continuous Integration (CI):** Tích hợp thay đổi thường xuyên, chạy kiểm tra tự động để phát hiện lỗi sớm.
4. **Kiểm thử liên lớp:** Kiểm tra hợp đồng, logic nghiệp vụ, tích hợp dữ liệu và một số luồng sử dụng quan trọng.
5. **Thay đổi dữ liệu tương thích:** Thiết kế migration/schema để các phần cũ và mới hoạt động an toàn trong khoảng chuyển đổi.
6. **Quan sát và xử lý sự cố:** Có tín hiệu giúp biết thay đổi làm lỗi luồng nào, ảnh hưởng ai và khôi phục thế nào.
7. **Phối hợp liên chức năng:** Developers trao đổi về giao diện, API, test, vận hành và quyền truy cập trước khi mỗi phần trở thành điểm chặn.

**CI không bằng CD**, và pipeline xanh không tự chứng minh không có lỗi. CI giúp phát hiện một tập rủi ro đã được thể hiện qua kiểm tra; đội vẫn cần thử nghiệm người dùng, đánh giá bảo mật và những kiểm tra đặc thù.

### Vòng lặp tích hợp ngắn

~~~mermaid
flowchart LR
    A["Lát cắt nhỏ + tiêu chí chấp nhận"] --> B["Thay đổi mã và test"]
    B --> C["Merge vào nhánh tích hợp chung"]
    C --> D["Build + kiểm thử tự động"]
    D --> E{"Kết quả đạt?"}
    E -- "Không" --> F["Sửa hoặc quay lại trạng thái an toàn"]
    F --> B
    E -- "Có" --> G["Kiểm tra hành vi, quyền truy cập, dữ liệu và DoD"]
    G --> H{"Đáp ứng DoD, dùng được?"}
    H -- "Chưa" --> B
    H -- "Rồi" --> I["Increment tích hợp; có thể nhận phản hồi"]
    I --> A
~~~

**Tích hợp thường xuyên** không có nghĩa “bất cứ merge nào cũng được gọi là Increment”. Đôi khi team merge các bước kỹ thuật nhỏ để giữ nhánh chung khỏe mạnh; **chỉ khi một bước tiến sản phẩm dùng được và đạt DoD** mới được xem là Increment hoàn thành.

## 8. Thiết kế API, dữ liệu và migration cho phát triển tăng dần

Nhiều Increment thường đi qua những thành phần có người dùng hoặc dịch vụ khác đang phụ thuộc. Thay đổi thiếu tương thích có thể khiến Increment mới làm hỏng phần trước.

### 8.1. Hợp đồng giao tiếp giữa thành phần

Ví dụ một API:

~~~http
GET /api/me/learning-progress/latest
Authorization: Bearer <token>

200 OK
{
  "courseId": "course-x",
  "lessonId": "lesson-4",
  "savedAt": "2026-11-23T08:30:00Z"
}
~~~

Đây chỉ là **minh họa**: endpoint, token, định dạng lỗi và cách xác định “mới nhất” phải được thiết kế theo sản phẩm thật. Các trường hợp cần thảo luận:

- Học viên chưa có bài học gần nhất: API trả trạng thái nào, giao diện hiển thị gì?
- Học viên đã hết quyền truy cập vào bài: bộ lọc được thực hiện tại đâu?
- API cũ và mới cùng tồn tại trong giai đoạn triển khai: hai phía có tương thích không?
- Trường thông tin bị bỏ hoặc đổi tên có làm hỏng client cũ không?
- Nhiều thiết bị cập nhật cùng lúc: quy tắc thứ tự hoặc versioning là gì?

**Contract test** có thể giúp phát hiện việc nhà cung cấp API và bên sử dụng hiểu khác nhau về dữ liệu, trạng thái hoặc hành vi. Cần kiểm tra cả các trường hợp thất bại và không tin tưởng vào HTTP 200 như bằng chứng duy nhất của tính đúng đắn.

### 8.2. Mở rộng – chuyển đổi – thu hẹp (expand/contract)

Khi cần thay đổi schema đang được phần mềm cũ sử dụng, nhóm có thể cân nhắc chiến lược:

1. **Expand:** Thêm cấu trúc mới mà luồng cũ vẫn hoạt động.
2. **Migrate/transition:** Chuyển dần dữ liệu hoặc luồng đọc/ghi, kiểm tra tính nhất quán và khả năng quay lại.
3. **Contract:** Chỉ xóa cấu trúc cũ khi mọi bên liên quan đã chuyển, có bằng chứng phù hợp và đáp ứng nghĩa vụ dữ liệu.

Ví dụ thay bảng lưu một cột “lessonId” bằng bảng lưu tiến độ phiên bản:

| Bước | Hành động | Kiểm chứng |
| --- | --- | --- |
| Expand | Thêm trường/version mới, chưa gỡ khả năng đọc dữ liệu cũ | Luồng đọc bài gần nhất vẫn đúng trên dữ liệu cũ. |
| Transition | Chuyển một phần luồng cập nhật sang dạng mới | Test gửi lặp, rollback, dữ liệu không mất hoặc bị lệch. |
| Contract | Dọn phần cũ sau khi chứng minh không còn phụ thuộc | Kiểm tra API/client liên quan, bảo toàn dữ liệu và phê duyệt cần thiết. |

Nếu migration chưa an toàn hoặc rollback không khả thi, hãy xem đó là **rủi ro cần xử lý trước khi gọi Increment hoàn thành**, không chỉ là task để lại sau Sprint.

## 9. Chiến lược nhánh, tích hợp và feature flag

Một Sprint có nhiều Increment dễ gặp vấn đề khi mọi thành viên phát triển lâu trên nhánh riêng. **Không có quy tắc Scrum bắt buộc một mô hình Git**, nhưng các chiến lược nên hướng tới phát hiện sai lệch và tích hợp sớm.

### Một số lựa chọn

| Thực hành | Lợi ích có thể có | Rủi ro cần quản lý |
| --- | --- | --- |
| **Nhánh ngắn và merge thường xuyên** | Giảm xung đột tích hợp về cuối Sprint, nhận phản hồi từ CI sớm | Cần test và review phù hợp để tránh làm hỏng nhánh chung. |
| **Trunk-based development** | Duy trì một dòng tích hợp chung, tạo điều kiện phát hành nhỏ thường xuyên | Cần kỷ luật giữ main ổn định và kiểm soát thay đổi dở dang. |
| **Feature flag** | Tách việc tích hợp code khỏi quyết định bật chức năng cho người dùng | Cần test các cấu hình quan trọng, kiểm soát quyền và dọn flag cũ. |
| **Branch dài theo từng tính năng** | Có thể cô lập công việc rủi ro trong một số bối cảnh | Dễ tăng merge conflict, chậm phát hiện lỗi hợp đồng và kiểm thử hồi quy. |

Một thay đổi có thể **được merge nhưng chưa đủ điều kiện sử dụng**; đội phải minh bạch trạng thái và không đếm nhánh đã merge là Increment nếu chưa đáp ứng DoD. Khi sử dụng feature flag để phát hành dần, cần xem **cả trạng thái bật/tắt và những thành phần cùng sử dụng dữ liệu**.

### Khi cần rollback

- Có thể hoàn tác code không, hay thay đổi đã ghi dữ liệu không tương thích?
- Có cần tắt flag, giảm lưu lượng hoặc khôi phục dữ liệu?
- Những Increment trước vẫn hoạt động bình thường sau rollback chứ?
- Ai quyết định rollback và dựa trên tín hiệu nào?

Rollback không phải giải pháp cho mọi loại lỗi dữ liệu. Với giao dịch tài chính hoặc tiến độ học quan trọng, đội có thể cần biện pháp phục hồi/đối soát thay vì chỉ cài lại phiên bản cũ.

## 10. Kiểm thử theo lớp để bảo vệ mọi Increment

Khi số Increment tăng, nguy cơ hồi quy cũng tăng nếu mỗi thay đổi chỉ được kiểm tra riêng. Đội cần **kiểm thử ở cấp phù hợp**, không mặc định chạy toàn bộ trường hợp qua UI.

| Lớp kiểm tra | Nên xác minh điều gì? | Ví dụ |
| --- | --- | --- |
| **Unit test** | Quy tắc nhỏ, nhanh, ít phụ thuộc | Bộ chọn bài gần nhất hợp lệ loại những bài hết quyền. |
| **Contract test** | Hai thành phần thống nhất cấu trúc và hành vi API | Trường lessonId và trạng thái lỗi đúng hợp đồng. |
| **Integration test** | Thành phần, dữ liệu và phân quyền hoạt động cùng nhau | Tài khoản A không đọc được tiến độ của B dù gọi trực tiếp API. |
| **End-to-end (E2E) quan trọng** | Một số luồng xuyên hệ thống thật sự dùng được | Học viên đăng nhập, chọn “Tiếp tục học”, mở đúng bài. |
| **Exploratory / usability test** | Khả năng dùng, trường hợp bất ngờ và mục tiêu người dùng | Học viên trên điện thoại có tìm thấy nút và hiểu trạng thái lưu? |
| **Performance / security / resilience test** | Ràng buộc chất lượng không thể chứng minh bằng luồng happy path | Độ trễ khi tải cao; xử lý lỗi mạng; kiểm tra quyền truy cập và dữ liệu. |

Không cần mọi Increment đều chạy **toàn bộ** bộ kiểm thử thủ công nếu rủi ro và pipeline được thiết kế hợp lý. Cần đảm bảo **bằng chứng đủ để đáp ứng DoD**, có thể dùng test tự động và chọn lọc kiểm tra thủ công theo tác động.

### Ví dụ kịch bản chấp nhận

~~~gherkin
Feature: Mở lại bài học gần nhất

  Scenario: Học viên mở lại bài còn quyền truy cập
    Given học viên A đã đăng nhập và có quyền học khóa X
    And bài học gần nhất hợp lệ của A là bài 4 thuộc khóa X
    When A chọn "Tiếp tục học"
    Then ứng dụng mở bài 4 thuộc khóa X

  Scenario: Không lộ tiến độ giữa hai tài khoản
    Given học viên A đã lưu tiến độ vào khóa X
    And học viên B đăng nhập trên thiết bị từng được A sử dụng
    When B mở trang chủ
    Then B không nhìn thấy tiến độ riêng của A
    And B không thể mở nội dung của A nếu B không có quyền truy cập
~~~

Các kịch bản trên giúp kiểm chứng hành vi, nhưng hệ thống vẫn cần kiểm thử thực thi **phân quyền phía dịch vụ**; chỉ ẩn nút ở giao diện không đủ để ngăn truy cập trái quyền.

### Định nghĩa “xanh” theo đúng phạm vi

Đội nên biết pipeline nào chạy ở mỗi pull request, pipeline nào kiểm tra thêm trước release, và những kiểm tra thủ công hoặc phê duyệt nào còn bắt buộc. “CI xanh” chỉ có ý nghĩa nếu **bộ kiểm tra đủ liên quan và đủ tin cậy** với thay đổi đang thực hiện.

## 11. Tình huống hoàn chỉnh: ba Increment trong một Sprint

### 11.1. Bối cảnh và Sprint Goal

Một Scrum Team chọn **Sprint dài hai tuần**. Product Goal là giúp học viên học liên tục trên nhiều thiết bị. Sprint Goal:

> **“Học viên có thể tìm và mở lại bài học hợp lệ gần nhất, kể cả sau khi đăng nhập trên thiết bị khác, với tiến độ được lưu và thông báo đáng tin cậy.”**

Năng lực đội và trạng thái API đã được trao đổi ở Sprint Planning. Ví dụ sau **không phải lịch chuẩn** áp dụng cho mọi đội; nó chỉ minh họa cách tạo nhiều Increment có giá trị và kiểm tra tích hợp.

### 11.2. Kế hoạch tăng dần

| Giai đoạn minh họa | Phạm vi sản phẩm | Điều kiện Done | Lợi ích và phản hồi |
| --- | --- | --- | --- |
| **Increment A — những ngày đầu** | Học viên đăng nhập thấy và mở lại đúng bài gần nhất từ dữ liệu đã lưu, trên luồng hiện tại. | Hoạt động qua UI–API–dữ liệu, kiểm tra quyền, trường hợp trống/lỗi an toàn, test và DoD đạt. | Có thể quan sát học viên có tìm lại đúng bài không. |
| **Increment B — giai đoạn giữa** | Lưu/đọc tiến độ đã xác nhận qua tài khoản để mở bài từ thiết bị khác; xử lý gửi lại request theo phạm vi đã chốt. | A vẫn chạy, dữ liệu không bị trộn giữa tài khoản, test liên thiết bị và hồi quy đạt, DoD đạt. | Kiểm chứng khả năng liên tục giữa thiết bị. |
| **Increment C — giai đoạn sau** | Bổ sung trạng thái lưu rõ ràng, thao tác thử lại có kiểm soát và tín hiệu hỗ trợ khi lỗi mạng; không hứa đã lưu khi chưa xác nhận. | A và B không hỏng, xử lý lỗi an toàn, quan sát hệ thống/khôi phục và DoD đạt. | Học viên hiểu tình trạng tiến độ; đội vận hành có dữ liệu để hỗ trợ. |

**Lưu ý:** Ở Increment A và B, hệ thống vẫn phải xử lý lỗi theo một **mức tối thiểu an toàn**; C cải thiện khả năng giao tiếp trạng thái và phục hồi, không phải “bây giờ mới bổ sung an toàn”.

### 11.3. Cách tổ chức tích hợp

Đội có thể tạo một chuỗi kiểm tra:

~~~text
Product Goal: Học liên tục, tiến độ đáng tin cậy
  |
Sprint Goal: Mở lại đúng bài qua thiết bị, trạng thái lưu rõ
  |
  +-- Increment A: Mở bài gần nhất hợp lệ
  |     - UI + API + dữ liệu + phân quyền + test hồi quy
  |     - Đạt DoD; chạy được cùng sản phẩm hiện tại
  |
  +-- Increment B: Đọc/lưu tiến độ qua thiết bị
  |     - Kiểm tra hợp đồng API + gửi lại request + phân quyền
  |     - A vẫn chạy; B đạt DoD
  |
  +-- Increment C: Trạng thái lưu và thử lại
        - Lỗi mạng, thông báo, hỗ trợ quan sát
        - A/B vẫn chạy; C đạt DoD
~~~

Đây là **một hướng phát triển khả thi**. Nếu kiểm thử B cho thấy kiến trúc đồng bộ không an toàn trong phạm vi Sprint, nhóm không được báo B Done hoặc để B làm hỏng A. Developers cần minh bạch, tìm phương án hợp lý và trao đổi với Product Owner khi cần thương lượng phạm vi để bảo vệ Sprint Goal và DoD.

### 11.4. Ví dụ kiểm tra sau Increment B

Một ma trận kiểm chứng có thể gồm:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| A lưu bài 4 trên laptop, đăng nhập điện thoại | A có thể xem và mở bài 4 theo tiến độ đã được xác nhận. |
| B dùng điện thoại trước đó có tài khoản A | B không nhìn thấy hoặc đọc được dữ liệu riêng của A. |
| Khóa học hết quyền sau khi lưu | Không mở nội dung trái quyền; hiển thị hướng xử lý phù hợp. |
| Hai request lưu đến gần đồng thời | Xử lý theo quy tắc xung đột/phiên bản đã thống nhất, không mất dữ liệu sai quy tắc. |
| Mạng mất khi ghi tiến độ | Ứng dụng không báo thành công giả; trạng thái được xử lý an toàn. |
| Người dùng chưa có tiến độ | Không hiển thị bài giả, có hướng bắt đầu phù hợp. |
| Cập nhật API mới | Luồng Increment A và phần sản phẩm cũ vẫn qua kiểm thử liên quan. |

Nếu một quy tắc như **xung đột tiến độ** chưa được xác nhận, đó là câu hỏi cần giải quyết trước khi tuyên bố tính năng đồng bộ hoàn thành.

### 11.5. Điều gì được xem ở Sprint Review?

Scrum Team có thể cho các bên liên quan xem:

- Increment A/B/C nào đã đạt DoD và đang hoạt động cùng nhau.
- Phần nào đã được phát hành hoặc chỉ sẵn sàng phát hành; lý do nếu khác nhau.
- Kết quả thử nghiệm người dùng, lỗi phát hiện, chỉ số vận hành và bất định còn lại.
- Tác động đến Product Goal và những cơ hội nên ưu tiên trong Product Backlog.

Nếu Increment A đã được giao cho người dùng từ giữa Sprint, đó vẫn là dữ kiện hữu ích cho Sprint Review. **Review không phải cổng bắt buộc cho release**, cũng không cho phép gọi PBI chưa đạt DoD là Done để demo.

## 12. Các sự kiện Scrum hỗ trợ nhịp tạo nhiều Increment

| Sự kiện | Câu hỏi cần kiểm tra | Liên hệ với Increment |
| --- | --- | --- |
| **Sprint Planning** | Sprint này có giá trị vì đâu, chọn những lát cắt nào, kế hoạch tích hợp ra sao? | Xác định một Sprint Goal; Developers lập Sprint Backlog có thể điều chỉnh. |
| **Daily Scrum** | Phần nào đang thực sự tiến gần Sprint Goal? Việc gì chặn tích hợp hoặc DoD? | Developers ưu tiên kết thúc và tích hợp việc có giá trị, điều chỉnh kế hoạch. |
| **Sprint Review** | Những Increment dùng được cho thấy điều gì? Người dùng cần gì tiếp? | Kiểm tra sản phẩm thật và cập nhật hướng Product Backlog. |
| **Sprint Retrospective** | Điều gì cản việc tạo Increment đáng tin thường xuyên? | Cải thiện phối hợp, test, CI, DoD, luồng review và năng lực kỹ thuật. |

Sprint bao chứa các sự kiện trên và dài **tối đa một tháng**. Việc một Sprint có nhiều Increment không bắt buộc tổ chức thêm “mini Sprint Review” chính thức sau mỗi phần; đội có thể lấy phản hồi khi cần và giữ các sự kiện Scrum đúng mục đích.

### Daily Scrum tập trung vào việc hoàn tất

Ví dụ:

> “Increment A đã đạt DoD. Increment B đang bị chặn ở quy tắc cập nhật cạnh tranh; test tích hợp vừa phát hiện dữ liệu bị ghi đè. Hôm nay hai Developers phối hợp giải quyết và chạy lại hồi quy; nhóm chưa bắt đầu hạng mục giao diện C để không tăng WIP. Nếu rủi ro vượt phạm vi, sẽ trao đổi với Product Owner.”

Thông điệp này tốt hơn “Tôi làm xong 80% API” vì cho thấy **giá trị tích hợp, trở ngại và hành động hướng Sprint Goal**.

### Retrospective cải thiện dòng giao hàng

Nếu Sprint nào cũng chỉ tích hợp vào ngày cuối, có thể thử:

- Giảm kích thước nhánh và tần suất tích hợp.
- Thêm contract test trước khi kết nối API mới.
- Thống nhất một lát cắt xuyên suốt làm ưu tiên hoàn tất.
- Giảm số việc đang làm đồng thời.
- Đầu tư cho pipeline đủ nhanh và tin cậy.

Mỗi cải tiến nên có giả thuyết, cách quan sát và thời điểm xem lại; không cần áp dụng đồng loạt mọi kỹ thuật.

## 13. Khi có nhiều Scrum Team cùng làm trên một sản phẩm

Một sản phẩm lớn có thể do nhiều Scrum Team đóng góp. Nếu mỗi đội có DoD khác nhau hoặc các Increment không tích hợp, việc mỗi đội báo “Done” sẽ không phản ánh **một sản phẩm dùng được**.

### Những điểm cần thống nhất

1. **Một Product Goal và Product Backlog của sản phẩm**, do một Product Owner chịu trách nhiệm theo Scrum.
2. **Definition of Done chung** cho sản phẩm, đáp ứng tiêu chuẩn tổ chức.
3. Giao diện, dữ liệu, contract test, quy ước phiên bản và đường tích hợp phù hợp.
4. Cơ chế thấy rõ phụ thuộc, lỗi xuyên đội, chất lượng và khả năng triển khai.
5. Trách nhiệm phối hợp và gỡ trở ngại trước khi chúng làm hỏng khả năng giao giá trị.

### Ví dụ hai đội

Đội A xây API tiến độ; đội B xây trang học. Nếu A đổi tên trường **lessonId** thành **itemId** mà B chưa biết, hai phần có thể đều “xanh” trong môi trường riêng nhưng **tính năng tích hợp bị lỗi**.

Cách giảm rủi ro:

- Thỏa thuận hợp đồng và cách quản lý thay đổi.
- Chạy contract test trước khi nhập code.
- Có môi trường tích hợp hoặc kiểm tra phù hợp để xem A và B cùng hoạt động.
- Chỉ gọi Increment hoàn thành khi đáp ứng **DoD chung** và tương thích với phần đã có.

Việc có nhiều đội không đồng nghĩa hình thành “Scrum of Scrums” bắt buộc hoặc tăng số thủ tục cố định. Mục tiêu là một sản phẩm minh bạch và các Increment có thể sử dụng.

## 14. Dùng dữ liệu để đánh giá khả năng tích hợp

Đếm số Increment trong Sprint **không đủ** để đánh giá hiệu quả. Hai đội có số Increment khác nhau có thể phục vụ sản phẩm và mức rủi ro rất khác nhau. Hãy kết hợp các tín hiệu:

| Tín hiệu | Ý nghĩa có thể rút ra | Điều cần tránh |
| --- | --- | --- |
| **Tần suất tích hợp/CI** | Nhóm có giảm độ trễ phản hồi kỹ thuật không? | Đếm mọi commit như một Increment. |
| **Lead time từ thay đổi đến môi trường kiểm chứng** | Bao lâu sau khi thay đổi, đội biết nó hoạt động với hệ thống? | Chỉ xem build xanh khi không có test tích hợp liên quan. |
| **Tỷ lệ build/test thất bại và thời gian khôi phục** | Pipeline và cách xử lý lỗi có ổn định không? | Dùng chỉ số để đổ lỗi cá nhân khiến mọi người che lỗi. |
| **Work in Progress (WIP)** | Có quá nhiều lát cắt bắt đầu nhưng chưa tích hợp? | Cắt WIP máy móc mà không xem phụ thuộc. |
| **Cycle time của PBI** | Thời gian từ bắt đầu đến đạt DoD đang tăng hay giảm? | So sánh những hạng mục khác hẳn nhau như thể đồng nhất. |
| **Lỗi thoát ra môi trường sử dụng** | Các bước tích hợp và kiểm thử có bỏ sót rủi ro quan trọng? | Chỉ đếm lỗi mà bỏ qua mức nghiêm trọng và tác động người dùng. |
| **Phản hồi người dùng và outcome** | Increment có giúp người dùng hoàn thành mục tiêu tốt hơn không? | Đánh đồng số lần release với giá trị sản phẩm. |

### Ví dụ nhận diện điểm nghẽn

Một đội có 15 pull request được merge trong Sprint nhưng **không tạo được luồng tích hợp qua UI–API** cho người dùng. Dữ liệu “15 merge” không chứng minh đội có 15 Increment. Câu hỏi hữu ích hơn là:

> “Những thay đổi đã merge còn thiếu điều gì để tạo ra một bước tiến đạt DoD? Phụ thuộc, kiểm thử tích hợp hay cách chia lát cắt đang cản trở?”

Nếu các item nằm ở trạng thái “Chờ kiểm thử” nhiều ngày, giới hạn WIP và hoàn thành một lát cắt trước khi bắt đầu thêm có thể là hướng thử nghiệm. Nếu lỗi API xuất hiện trễ, contract test và tích hợp sớm có thể có tác động lớn hơn.

## 15. Những phản ví dụ và cách khắc phục

| Sai lầm | Tác hại | Điều chỉnh |
| --- | --- | --- |
| **Đếm số commit hoặc pull request là số Increment** | Số liệu tăng nhưng sản phẩm chưa có thêm bước tiến dùng được | Chỉ ghi nhận khi phần sản phẩm tích hợp, usable và đạt DoD. |
| **Chia nhỏ chỉ theo backend/database/frontend** | Mỗi phần riêng chưa thể kiểm tra kết quả người dùng | Tổ chức lát cắt xuyên suốt từ UI/API/dữ liệu đến kiểm thử. |
| **“Increment A sẽ thiếu phân quyền, B bổ sung sau”** | Cố tình chuyển rủi ro cho người dùng | Giữ chuẩn chất lượng ngay ở A; hoãn sử dụng nếu chưa an toàn. |
| **Mỗi hạng mục chỉ chạy trên nhánh cá nhân** | Lỗi tích hợp phát hiện muộn, merge khó | Tích hợp sớm vào dòng code chung theo chính sách kiểm tra. |
| **Pipeline xanh nghĩa là luôn an toàn** | Bộ test có thể thiếu phạm vi hoặc môi trường không giống thực tế | Kết hợp kiểm thử hợp đồng, tích hợp, bảo mật và thử nghiệm phù hợp. |
| **Feature flag đồng nghĩa tính năng đã Done** | Code có thể bị che vì chưa hoàn chỉnh hoặc không thể sử dụng | Phân biệt tích hợp dở dang, Increment đạt DoD và trạng thái bật cho người dùng. |
| **Đợi Sprint Review mới được giao giá trị** | Phản hồi bị trì hoãn không cần thiết | Release Increment sớm khi đáp ứng DoD và điều kiện phát hành. |
| **Cố tạo ba Increment dù không có lát cắt có ích** | Tăng chi phí phối hợp và test mà không tạo giá trị | Chọn nhịp giao theo nhu cầu và rủi ro, không tối ưu số đếm. |
| **Increment mới làm hỏng luồng cũ** | Phá tính cộng dồn của sản phẩm | Kiểm thử hồi quy và tương thích với mọi phần trước. |
| **Dùng DoD tùy tiện theo từng đội** | Không có chuẩn chung để đánh giá một sản phẩm | Cùng định nghĩa và tuân thủ DoD khi nhiều đội làm cùng sản phẩm. |
| **Báo phần trăm hoàn thành task thay vì tình trạng tích hợp** | Che nợ kỹ thuật và rủi ro cuối Sprint | Minh bạch Increment thực tế, DoD, trở ngại và bước kế tiếp. |
| **Đổi phạm vi giữa Sprint nhưng bỏ Sprint Goal** | Đội mất tập trung và khó hoàn thành giá trị | Thương lượng phạm vi theo mục tiêu; xử lý yêu cầu mới theo quyền quyết định. |

## 16. Quy trình thực hành tạo nhiều Increment an toàn

Nhóm có thể áp dụng một chu trình gọn với mỗi lát cắt:

### Bước 1 — Chọn kết quả người dùng nhỏ nhưng có ý nghĩa

Làm rõ ai dùng, thay đổi mong đợi và giá trị liên quan Product Goal/Sprint Goal. Nếu hạng mục có quá nhiều loại hành vi, hãy chia nhỏ.

### Bước 2 — Chốt ví dụ và ranh giới chất lượng

Thống nhất tiêu chí chấp nhận, các tình huống lỗi/phân quyền quan trọng, điều kiện vận hành và DoD. Không hoãn những điều kiện làm cho bước tiến đầu tiên không an toàn.

### Bước 3 — Kiểm tra hợp đồng và phụ thuộc trước khi code nhiều

Xác định thành phần phải thay đổi, môi trường tích hợp, quyền truy cập dữ liệu, API của đội khác và rủi ro migration. Làm một technical spike có giới hạn nếu bất định cản trở quyết định.

### Bước 4 — Thay đổi nhỏ và tích hợp thường xuyên

Developers phối hợp để code, review và chạy CI. Tránh giữ nhánh tách biệt quá lâu. Khi lỗi tích hợp xuất hiện, ưu tiên khôi phục dòng code chung hoạt động ổn định.

### Bước 5 — Xác minh tính dùng được cùng các Increment trước

Không chỉ chạy test của tính năng mới. Kiểm tra luồng cũ, dữ liệu và tương tác giữa các phần; đánh giá tiêu chí chấp nhận và DoD.

### Bước 6 — Ghi nhận Increment và nhận phản hồi phù hợp

Khi đạt DoD, nhóm có một Increment có thể sử dụng. Tùy chính sách, có thể giao cho người dùng hoặc trình diễn trên môi trường phù hợp trước Sprint Review. Công khai rõ **đã hoàn thành**, **đã phát hành** và **chưa có bằng chứng về outcome dài hạn** là ba điều khác nhau.

### Bước 7 — Điều chỉnh Sprint Backlog và Product Backlog có trách nhiệm

Developers kiểm tra tiến triển hướng Sprint Goal qua Daily Scrum và các trao đổi cần thiết; Product Owner điều chỉnh Product Backlog khi có bằng chứng mới; Scrum Team cải tiến cách làm tại Retrospective.

**Lặp lại với lát cắt kế tiếp** mà không đánh đổi DoD. Nếu không có phương án an toàn và khả thi trong Sprint, minh bạch điều chưa hoàn thành tốt hơn cố gắn nhãn Done.

## 17. Bài tập thực hành

### Bài tập 1 — Có phải Increment không?

Một Scrum Team mô tả năm kết quả cuối tuần:

1. Code endpoint đọc bài gần nhất đã merge; chưa tích hợp UI và chưa có kiểm thử quyền truy cập.
2. Luồng mở bài hợp lệ từ trang chủ đã chạy qua UI–API–dữ liệu, đáp ứng DoD và tương thích phần trước.
3. Pipeline build xanh nhưng không có thay đổi sản phẩm hoặc khả năng vận hành mới.
4. Một thay đổi sửa lỗi mất dữ liệu đã qua test tích hợp, đáp ứng DoD, hoạt động với sản phẩm hiện có.
5. Một tính năng demo được trên nhánh riêng, nhưng fail test tích hợp khi nhập với main.

**Yêu cầu:** Phân loại trường hợp nào có cơ sở coi là Increment; giải thích điều còn thiếu của các trường hợp khác.

**Gợi ý:** (2) và (4) có cơ sở nếu thật sự là bước tiến usable và đáp ứng DoD; các trường hợp còn lại chưa đủ bằng chứng. Không tự đồng nhất merge, build hoặc demo với Increment.

### Bài tập 2 — Chia một yêu cầu thành ba lát cắt giá trị

Yêu cầu: “Học viên học tiếp trên mọi thiết bị, cả khi mất mạng và có khả năng đồng bộ vị trí video.”

**Yêu cầu:** Đề xuất ít nhất ba lát cắt có thể tích hợp và dùng được, mỗi lát cắt viết:

- Người dùng và kết quả nhận được.
- Tiêu chí chấp nhận quan trọng.
- Điều kiện chất lượng phải có ngay từ lát cắt đó.
- Những phần có thể để sang lát cắt tiếp theo.

**Gợi ý:** Không để phân quyền sang phần sau; có thể hoãn việc hỗ trợ mọi loại nội dung offline trong khi xác minh nhu cầu và bản quyền.

### Bài tập 3 — Lập ma trận kiểm thử tích hợp

Increment A cho phép mở bài gần nhất; Increment B thêm đồng bộ qua thiết bị.

**Yêu cầu:** Viết ít nhất sáu kịch bản test xác minh **B hoạt động cùng A**. Bắt buộc có: cùng tài khoản, khác tài khoản, hết quyền, không có tiến độ, mạng lỗi và hai cập nhật gần đồng thời.

**Gợi ý:** Mỗi kịch bản phải nêu dữ liệu, hành động và kết quả có thể xác minh. Nếu quy tắc xung đột chưa có, ghi câu hỏi để Product Owner và Developers cùng làm rõ trước khi hoàn thành B.

### Bài tập 4 — Release sớm hay đợi Sprint Review?

Ngày thứ sáu của Sprint hai tuần, Increment A đã đạt DoD. Đội vận hành xác nhận có thể triển khai an toàn. Product Owner muốn nhận phản hồi sớm từ một nhóm học viên thử, nhưng một thành viên cho rằng “Scrum chỉ cho release trong Sprint Review”.

**Yêu cầu:** Giải thích cách Scrum nhìn nhận thời điểm release, điều kiện phải xét và cách phản hồi từ A có thể ảnh hưởng B/C mà vẫn bảo vệ Sprint Goal.

**Gợi ý:** Review không phải cổng phát hành. Cần phân biệt trạng thái Increment, quyền quyết định release, nghĩa vụ sản phẩm, kế hoạch rollback và phạm vi phản hồi.

### Bài tập 5 — Xử lý lỗi tích hợp giữa Sprint

Increment A đã Done. Developers đang làm B thì phát hiện thay đổi schema khiến A không thể mở bài. Product Owner muốn báo B là “90% xong” để giữ tiến độ báo cáo.

**Yêu cầu:** Nêu trạng thái thực tế của B, rủi ro đối với sản phẩm, các hành động kỹ thuật và cách báo cáo ở Daily Scrum. Hãy trình bày phương án sửa hoặc rollback và cách xác minh không làm hỏng A.

**Gợi ý:** B chưa được coi là Increment. Phải bảo vệ sản phẩm tích hợp và chất lượng; không dùng phần trăm task để hợp thức hóa một thay đổi phá chức năng cũ.

### Bài tập 6 — Hai Scrum Team cùng một sản phẩm

Team API và Team UI cùng đóng góp cho luồng “Tiếp tục học”. Team API có DoD chỉ yêu cầu unit test; Team UI yêu cầu E2E test trên môi trường tích hợp. Mỗi team đều báo Done nhưng kết hợp thì trả sai bài học.

**Yêu cầu:** Đề xuất một DoD chung, chính sách hợp đồng API và cách kiểm chứng Increment tích hợp. Nêu ai cần trao đổi để tránh tiếp tục chuyển lỗi qua lại.

**Gợi ý:** Một sản phẩm cần DoD thống nhất. Contract test, integration test và kiểm tra quyền truy cập là các cơ chế có thể phù hợp; cần người có trách nhiệm về chất lượng sản phẩm và Developers của các team phối hợp.

### Bài tập 7 — Chọn tín hiệu cải tiến phù hợp

Trong ba Sprint gần đây, đội tăng số pull request từ 12 lên 26, nhưng số lỗi tích hợp và thời gian chờ kiểm thử cũng tăng. Không có thay đổi rõ về khả năng người dùng nhận được.

**Yêu cầu:** Nêu vì sao số pull request không chứng minh có nhiều Increment giá trị hơn; đề xuất hai tín hiệu dòng công việc, hai tín hiệu chất lượng và một outcome người dùng để theo dõi thử nghiệm cải tiến.

**Gợi ý:** Có thể quan sát cycle time, WIP, thời gian pipeline phục hồi, lỗi lọt ra môi trường sử dụng và tỷ lệ học viên mở lại đúng bài. Không dùng kết quả để đổ lỗi cá nhân.

## 18. Checklist kiểm tra một Sprint có nhiều Increment

Trước khi gọi một lát cắt là Increment hoàn thành, Scrum Team có thể hỏi:

- [ ] Lát cắt tạo ra **khả năng hoặc bước tiến cụ thể** hướng Product Goal?
- [ ] Công việc có liên quan đến Sprint Goal và được đưa vào kế hoạch minh bạch?
- [ ] Phần mới có **sử dụng được**, chứ không chỉ là task, commit hoặc build?
- [ ] Increment mới **hoạt động cùng mọi Increment trước** trong phạm vi sản phẩm liên quan?
- [ ] Các tiêu chí chấp nhận quan trọng của lát cắt đã được kiểm chứng?
- [ ] Phần thay đổi đã đáp ứng **Definition of Done chung** của sản phẩm?
- [ ] Quyền truy cập, dữ liệu, bảo mật và các điều kiện an toàn liên quan đã được bảo vệ?
- [ ] CI và những kiểm thử tích hợp/hồi quy thích hợp đã đạt?
- [ ] Nếu có migration hay API change, các phiên bản và dữ liệu tương thích trong quá trình chuyển đổi?
- [ ] Những trạng thái feature flag cần thiết đã được kiểm tra; phần chưa dùng được không bị gọi là Done?
- [ ] Có cách quan sát lỗi, xử lý sự cố và khôi phục/rollback phù hợp?
- [ ] Đã phân biệt rõ **Increment đạt DoD**, **đã triển khai** và **đã phát hành**?
- [ ] Có thể nhận phản hồi sớm mà không chờ Sprint Review nếu điều kiện phù hợp?
- [ ] Product Owner và Developers đã trao đổi minh bạch khi phạm vi hoặc rủi ro thay đổi?
- [ ] Các vấn đề tích hợp được ưu tiên hoàn thành hơn là khởi động thêm nhiều việc dang dở?
- [ ] Đội đang đo **giá trị và chất lượng**, không chỉ đếm số Increment hoặc pull request?

Đây là checklist hỗ trợ thảo luận, không phải yêu cầu Scrum phải tạo biểu mẫu cho mọi thay đổi. Những điều bắt buộc đến từ DoD và các tiêu chuẩn sản phẩm/tổ chức đã thống nhất.

## 19. Ghi nhớ

- **Increment là một bước tiến cụ thể, có thể sử dụng, bổ sung vào phần sản phẩm hiện có và đáp ứng Definition of Done.** Commit, merge, build hoặc demo không tự động là Increment.
- **Một Sprint có thể tạo nhiều Increment.** Chúng phải hoạt động cùng nhau; có thể được giao trước Sprint Review khi điều kiện phát hành phù hợp, và Sprint Review không phải cổng bắt buộc để release.
- **Một Sprint vẫn có một Sprint Goal.** Nhiều Increment là những bước tiến hướng mục tiêu chung, không phải lý do để gom các công việc không liên quan hoặc hạ chất lượng.
- **Chia theo lát cắt giá trị xuyên suốt** giúp tạo bằng chứng sớm. Tránh chỉ chia theo tầng dữ liệu, backend và frontend rồi chờ tích hợp vào ngày cuối.
- **CI, kiểm thử hợp đồng, kiểm thử tích hợp, migration tương thích, feature flag và thực hành XP** có thể tăng khả năng thay đổi an toàn, nhưng không thay thế đánh giá giá trị và DoD.
- **Không chuyển rủi ro cốt lõi sang Increment sau**: bảo mật, quyền truy cập, tính toàn vẹn dữ liệu và chất lượng bắt buộc phải được giữ ở mọi Increment được gọi là Done.
- **Đánh giá bằng kết quả và khả năng tích hợp thực**: dùng được, đạt DoD, thời gian phản hồi, lỗi, năng lực vận hành và outcome người dùng; không chỉ đếm task/PR/release.

Khi một Scrum Team nói “Sprint này chúng ta đã tạo ba Increment”, hãy hỏi: **“Ba bước tiến ấy có thực sự dùng được, đáp ứng cùng một tiêu chuẩn chất lượng và cùng vận hành tốt trong sản phẩm hiện tại không?”**
