# Developers tự quản kế hoạch thực hiện và thích ứng hằng ngày

## 1. Bức tranh chung: tự quản không phải làm việc tùy ý

Trong Scrum, **Developers** là những thành viên của Scrum Team cam kết tạo ra bất kỳ khía cạnh nào của một **Increment có thể sử dụng được** ở mỗi Sprint. Từ “Developers” trong Scrum không chỉ giới hạn ở lập trình viên: tùy sản phẩm, nhóm có thể bao gồm người thiết kế, kiểm thử, phân tích, tích hợp, dữ liệu hoặc các chuyên môn cần thiết khác. Họ cùng chịu trách nhiệm tạo ra kết quả của Sprint, thay vì chỉ tối ưu công việc của từng chức danh.

Hai ý then chốt của chủ đề này là:

- **Tự quản kế hoạch thực hiện:** Developers quyết định *làm cách nào* để biến những Product Backlog Item (PBI) đã chọn thành Increment đáp ứng chất lượng; họ tự tổ chức công việc, phối hợp kỹ năng và liên tục cập nhật **Sprint Backlog**.
- **Thích ứng hằng ngày:** Developers quan sát tiến độ hướng đến **Sprint Goal**, nhận diện thông tin mới, trở ngại và rủi ro, rồi điều chỉnh kế hoạch tiếp theo mà không chờ một cấp quản lý phân việc lại.

Điều đó **không đồng nghĩa** Developers được bỏ qua ưu tiên sản phẩm, thay đổi các cam kết một cách âm thầm hoặc tự hạ chuẩn chất lượng. Scrum Team có một Sprint Goal; Product Owner chịu trách nhiệm về giá trị và quản lý hiệu quả Product Backlog; Developers tạo kế hoạch và tổ chức thực hiện; Scrum Master hỗ trợ hiệu quả Scrum.

Ví dụ, nhóm đang phát triển nền tảng học trực tuyến với mục tiêu Sprint là “người học có thể đăng ký một khóa học miễn phí và biết chắc đăng ký thành công”. Nếu API đã viết xong nhưng giao diện và kiểm thử tích hợp còn bị chặn, Developers cần cùng tìm cách hoàn tất luồng giá trị, thay vì mỗi người tiếp tục mở một công việc mới chỉ để báo cáo “phần của mình đã xong”.

Tư duy này phù hợp với mục tiêu module **AGILE_DEVELOPMENT**: giao sản phẩm tăng dần, nhận phản hồi sớm, phối hợp với các bên liên quan và cải tiến liên tục. User story, backlog, Scrum, Kanban và thực hành kỹ thuật XP có thể hỗ trợ Developers làm việc thích ứng; nhưng **Scrum không bắt buộc một cách phân task hay một bảng công cụ cụ thể**.

## 2. Developers chịu trách nhiệm chính thức về điều gì?

Theo Scrum Guide, Developers luôn chịu trách nhiệm về bốn nhóm hoạt động:

1. **Tạo kế hoạch cho Sprint — Sprint Backlog.**
2. **Duy trì chất lượng bằng cách tuân thủ Definition of Done.**
3. **Điều chỉnh kế hoạch hằng ngày hướng tới Sprint Goal.**
4. **Giữ trách nhiệm nghề nghiệp với nhau (holding each other accountable as professionals).**

| Trách nhiệm | Hành vi quan sát được | Điều không nên suy diễn |
| --- | --- | --- |
| Tạo Sprint Backlog | Cùng đánh giá việc đã chọn, xác định cách làm, chia việc khi hữu ích và nêu phụ thuộc | Có một quản lý chỉ định từng task cho từng người |
| Bảo đảm DoD | Kiểm thử, review, tích hợp và xác minh Increment theo chuẩn chất lượng | “Code xong” là “Done” dù còn lỗi tích hợp |
| Thích ứng mỗi ngày | Xem tiến độ tới Sprint Goal, điều chỉnh thứ tự và cách phối hợp | Đợi đến ngày cuối Sprint mới thừa nhận rủi ro |
| Trách nhiệm với đồng đội | Minh bạch tiến độ, hỗ trợ gỡ nghẽn, nêu rủi ro, phản biện chuyên môn có căn cứ | Dùng chỉ số cá nhân để đổ lỗi hoặc cạnh tranh |

**Tự quản** trong Scrum nghĩa là Scrum Team tự quyết bên trong **ai làm gì, khi nào, bằng cách nào** trong phạm vi trách nhiệm của mình. Developers đặc biệt chịu trách nhiệm lập kế hoạch thực hiện chi tiết và biến kế hoạch đó thành Increment. Nhóm vẫn phải làm việc trong giới hạn an toàn, pháp lý, hợp đồng và tiêu chuẩn của tổ chức; tự quản không tự động cấp thẩm quyền đổi các ràng buộc đó.

### 2.1. Nhóm tự quản khác đội chỉ nhận phân việc

| Nhóm chỉ nhận phân việc | Developers tự quản trong Scrum |
| --- | --- |
| Một cấp quản lý phân công cố định “An viết API, Bình kiểm thử”, bất kể tắc nghẽn | Developers trao đổi cách phân công, có thể thay đổi để cùng hoàn tất mục tiêu |
| Tiến độ đo theo số giờ từng người bận | Tiến độ được nhìn theo Sprint Goal, Increment và chất lượng |
| Khi task bị chặn, người thực hiện chờ lệnh | Người thực hiện báo rõ trở ngại, nhóm cùng chọn cách xử lý phù hợp |
| Mọi điều chỉnh phải đợi người quản lý phê duyệt cách làm kỹ thuật | Developers chủ động điều chỉnh kế hoạch trong phạm vi trách nhiệm và thỏa thuận |
| “Xong phần tôi” được coi là đã hoàn thành đóng góp | Cả nhóm quan tâm hạng mục có thực sự đạt DoD và tạo giá trị |

Không phải cá nhân nào cũng cần giỏi tất cả chuyên môn. **Tự quản ở cấp nhóm** đòi hỏi đủ năng lực tổng hợp và phối hợp thực tế: biết khi nào cần chuyên gia kiểm thử, người hiểu nghiệp vụ, người kiểm tra bảo mật hoặc người có quyền truy cập môi trường.

## 3. Phân biệt trách nhiệm Developers, Product Owner và Scrum Master

Scrum có **một Scrum Team**, gồm **một Product Owner, một Scrum Master và Developers**. Không có hệ thống cấp bậc hoặc các nhóm con chính thức *bên trong Scrum Team* theo định nghĩa Scrum, dù tổ chức có thể có các chức danh và quan hệ quản lý nhân sự riêng.

| Vấn đề | Developers | Product Owner | Scrum Master |
| --- | --- | --- | --- |
| **Giá trị sản phẩm và Product Backlog** | Đóng góp hiểu biết kỹ thuật, rủi ro, phương án chia nhỏ | Chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog, gồm sắp thứ tự | Hỗ trợ hiểu và áp dụng Scrum để quản lý backlog hiệu quả |
| **Sprint Goal** | Cùng Scrum Team xây mục tiêu Sprint thực tế | Cùng Scrum Team làm rõ vì sao Sprint có giá trị | Hỗ trợ sự kiện và cách hợp tác hiệu quả |
| **Chọn PBI cho Sprint** | Chọn thông qua trao đổi với Product Owner, dựa trên năng lực và hiểu biết | Trao đổi ưu tiên, mục tiêu và làm rõ PBI | Hỗ trợ Sprint Planning diễn ra hiệu quả |
| **Cách thực hiện** | Tự quyết kế hoạch kỹ thuật, phối hợp và thứ tự tác vụ trong Sprint | Cung cấp hiểu biết sản phẩm, không tự phân task cho Developers | Hướng dẫn, hỗ trợ tự quản, không điều hành task hằng ngày |
| **Điều chỉnh hằng ngày** | Kiểm tra tiến độ Sprint Goal, cập nhật Sprint Backlog | Làm rõ nhu cầu và trao đổi phạm vi khi cần | Hỗ trợ loại bỏ trở ngại và cải thiện hiệu quả Scrum |
| **Chất lượng Increment** | Tuân thủ Definition of Done và cùng chịu trách nhiệm tạo Increment | Quan tâm tác động đến giá trị và nhu cầu sản phẩm | Hỗ trợ nhóm làm việc đúng Scrum và cải tiến |

**Không nên nhầm “Product Owner quyết định ưu tiên sản phẩm” với “Product Owner quyết định mọi chi tiết công việc của Developers”.** Product Owner đưa ra hướng giá trị và quản lý Product Backlog; Developers lựa chọn những PBI có khả năng hoàn tất trong Sprint và tự xây kế hoạch thực hiện. Hai bên cần cộng tác khi có hiểu biết mới.

**Scrum Master không phải người nhận báo cáo tiến độ hằng ngày để giao việc tiếp.** Scrum Master hỗ trợ nhóm và tổ chức hiểu Scrum, cải thiện tính tự quản, loại bỏ trở ngại và làm cho các sự kiện có giá trị. Nếu Scrum Master hoặc Product Owner thực sự tham gia làm việc trên các hạng mục trong Sprint Backlog, họ có thể tham gia Daily Scrum **với tư cách Developers cho phần công việc đó**, không phải để kiểm soát người khác.

## 4. Sprint Backlog: kế hoạch do Developers tạo và cập nhật

**Sprint Backlog** là một artifact của Scrum, gồm ba phần:

| Thành phần | Câu hỏi | Ai chịu trách nhiệm chính trong cách hình thành? |
| --- | --- | --- |
| **Sprint Goal** | **Vì sao (Why)** Sprint này có giá trị? | Cả Scrum Team cùng xây dựng trong Sprint Planning |
| **Các Product Backlog Item được chọn** | **Làm gì (What)** để hướng tới mục tiêu? | Developers chọn qua trao đổi với Product Owner |
| **Kế hoạch hành động** | **Làm như thế nào (How)** để tạo Increment? | Developers tự tạo, phát triển và điều chỉnh |

Sprint Backlog là **kế hoạch của Developers, dành cho Developers**. Nó cung cấp bức tranh minh bạch theo thời gian thực về công việc Developers dự định làm để đạt Sprint Goal. Khi nhóm học được điều mới, kế hoạch được cập nhật trong Sprint.

### 4.1. Ví dụ Sprint Backlog cho nền tảng học trực tuyến

**Sprint Goal minh họa:**

> “Người học đã đăng nhập có thể đăng ký một khóa miễn phí, nhận xác nhận thành công và thấy khóa trong danh sách học của mình.”

**PBI được chọn sau trao đổi với Product Owner:**

1. Người học đăng ký khóa miễn phí theo quy tắc nghiệp vụ đã làm rõ.
2. Người học nhận trạng thái xác nhận đúng, kể cả khi yêu cầu thất bại.
3. Người học thấy khóa vừa đăng ký trong danh sách khóa của mình.

**Kế hoạch ban đầu do Developers đề xuất:**

| Lát cắt hoặc hoạt động | Kết quả cần đạt | Phụ thuộc / câu hỏi cần kiểm tra |
| --- | --- | --- |
| Thống nhất ví dụ đăng ký hợp lệ và không hợp lệ | Tiêu chí chấp nhận có thể kiểm thử | Quy tắc đăng ký trùng và trạng thái khóa |
| Tạo lát cắt đăng ký từ UI đến dịch vụ và dữ liệu | Đăng ký thành công thực sự, không chỉ giao diện giả | Quyền truy cập, khả năng xử lý thao tác lặp |
| Tích hợp xác nhận và xử lý lỗi | Không báo thành công giả khi dịch vụ lỗi | Trạng thái dữ liệu, lỗi mạng và retry |
| Hiển thị khóa trong danh sách học | Người học thấy kết quả đăng ký | Đồng bộ dữ liệu và quyền theo tài khoản |
| Review, kiểm thử, tích hợp và kiểm tra DoD | Increment có thể sử dụng | CI, hồi quy, bảo mật và tiêu chuẩn chất lượng |

Kế hoạch không nhất thiết phải chia thành các task cố định theo vai trò. Developers có thể làm việc cặp, chia theo lát cắt dọc hoặc cùng chuyển sang hỗ trợ review khi có nghẽn. **Tách giao diện, API và dữ liệu thành ba phần độc lập không phải lúc nào cũng tạo ra giá trị sử dụng được.**

### 4.2. Sprint Backlog không phải hợp đồng đóng băng từ đầu Sprint

Scrum sử dụng **kiểm tra và thích ứng**. Trong Sprint:

- Không thực hiện thay đổi gây nguy hiểm cho Sprint Goal.
- Chất lượng không bị giảm xuống.
- Product Backlog được làm rõ thêm khi cần.
- Phạm vi có thể được làm rõ hoặc thương lượng lại với Product Owner khi học thêm thông tin.

Ví dụ, ban đầu Developers định gửi email xác nhận ngay sau khi đăng ký. Khi tích hợp, họ phát hiện dịch vụ email không ổn định và email không nhất thiết là điều kiện cốt lõi để người học **biết chắc** đăng ký thành công ngay trong ứng dụng. Developers cùng Product Owner trao đổi liệu có thể ưu tiên xác nhận rõ trong giao diện, bảo đảm dữ liệu đúng và đưa email vào hạng mục sau **nếu điều đó phù hợp Sprint Goal và thỏa thuận sản phẩm**.

Nếu email là cam kết bắt buộc của đợt này hoặc cần theo ràng buộc bên ngoài, không được tự ý bỏ. Nhóm phải làm rõ quyền quyết định và ảnh hưởng của thay đổi.

## 5. Daily Scrum: điểm kiểm tra và thích ứng của Developers

**Daily Scrum** là sự kiện của Developers trong Scrum Team, được **timebox 15 phút**, tổ chức **cùng thời gian và địa điểm mỗi ngày làm việc của Sprint** để giảm độ phức tạp khi phối hợp.

Mục đích của Daily Scrum là:

> **Kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần, từ đó cập nhật kế hoạch công việc sắp tới.**

Daily Scrum không phải buổi “điểm danh” hay báo cáo từng cá nhân cho quản lý. Các Developers được quyền lựa chọn **cấu trúc và kỹ thuật** của buổi trao đổi, miễn tập trung vào tiến độ hướng tới Sprint Goal và tạo ra một kế hoạch có thể hành động cho ngày làm việc tiếp theo.

### 5.1. Những gì nên được kiểm tra trong Daily Scrum

1. **Sprint Goal còn khả thi tới đâu?** Kết quả nào đã được kiểm chứng, điều gì vẫn thiếu để người dùng nhận được giá trị?
2. **Công việc nào đang gần Done?** Có thể ưu tiên hoàn tất, review, kiểm thử hoặc tích hợp thay vì mở việc mới không?
3. **Có trở ngại hoặc thay đổi giả định nào?** Ví dụ môi trường thử nghiệm ngừng hoạt động, quy tắc nghiệp vụ chưa rõ, yêu cầu bảo mật mới.
4. **Kế hoạch hôm nay cần thay đổi thế nào?** Ai phối hợp với ai, thứ tự công việc mới, cách gỡ nghẽn hoặc câu hỏi cần trao đổi với Product Owner.
5. **Thông tin nào cần minh bạch trên Sprint Backlog?** Task mới, công việc bị chặn, rủi ro và điều chỉnh kế hoạch.

### 5.2. Ba câu hỏi truyền thống không phải luật bắt buộc

Một số nhóm quen với ba câu hỏi:

1. Hôm qua tôi đã làm gì?
2. Hôm nay tôi sẽ làm gì?
3. Tôi có trở ngại gì?

Những câu hỏi này có thể hữu ích trong bối cảnh cụ thể, nhưng **Scrum Guide không yêu cầu bắt buộc dùng mẫu ba câu hỏi**. Nếu cả nhóm chỉ đọc lại những gì mình đã làm mà không kiểm tra tác động tới Sprint Goal hoặc điều chỉnh kế hoạch, buổi họp đã lệch mục đích.

Một cách thảo luận thay thế, dựa trên công việc:

> “Để đạt Sprint Goal, những hạng mục nào còn thiếu? Chúng ta nên cùng hoàn tất hạng mục nào trước? Điều gì đang bị chặn? Kế hoạch trong 24 giờ làm việc tới cần khác hôm qua ở điểm nào?”

Với đội làm việc phân tán, có thể xem Sprint Backlog trực tiếp hoặc cập nhật các hạng mục trước khi họp để dành 15 phút cho **ra quyết định** thay vì đọc báo cáo. Tuy vậy, cập nhật bất đồng bộ không tự thay thế Daily Scrum khi nhóm đang thực hành Scrum.

### 5.3. Ví dụ một Daily Scrum tập trung vào mục tiêu

**Sprint Goal:** Người học đăng ký được khóa miễn phí và thấy xác nhận thành công.

**Tình hình trước cuộc trao đổi:**

- API đăng ký đã tích hợp với cơ sở dữ liệu và vượt qua kiểm thử đơn vị.
- Kiểm thử luồng từ giao diện đến hệ thống phát hiện bấm đăng ký hai lần có thể tạo bản ghi trùng.
- Một PBI về giao diện danh sách khóa đang chờ review.
- Một thành viên dự định bắt đầu tính năng tìm kiếm mới, ít liên quan tới Sprint Goal hiện tại.

**Cuộc trao đổi minh họa:**

> **Developer A:** “Luồng đăng ký chưa đạt DoD vì vẫn có bản ghi trùng khi gửi lại yêu cầu. Nếu không sửa, Sprint Goal chưa đạt.”  
> **Developer B:** “Tôi đang chuẩn bị bắt đầu phần tìm kiếm, nhưng có thể hỗ trợ kiểm thử thao tác lặp và review thay đổi đăng ký.”  
> **Developer C:** “Tôi sẽ xử lý tính nhất quán ở dịch vụ; cần một người thử với dữ liệu tích hợp và thiết bị di động.”  
> **Developer D:** “Tôi sẽ hoàn tất review danh sách khóa, sau đó phối hợp kiểm thử xuyên hệ thống.”  
> **Cả nhóm:** “Hôm nay ưu tiên làm luồng đăng ký đủ Done; chưa mở phần tìm kiếm. Cập nhật Sprint Backlog với hai bước sửa lỗi và kiểm thử.”

**Đầu ra mong muốn:** Có hành động và người phối hợp rõ ràng, kế hoạch được cập nhật. Cuộc trao đổi không cần biến thành buổi tìm nguyên nhân lỗi 45 phút; Developers có thể hẹn làm việc chi tiết ngay sau đó với những người cần tham gia.

### 5.4. Daily Scrum không phải thời điểm duy nhất được điều chỉnh

Nếu lỗi bảo mật nghiêm trọng xuất hiện lúc 14:00, Developers không cần chờ đến Daily Scrum sáng hôm sau mới phản ứng. Trong Sprint, họ thường xuyên trao đổi thêm để thích ứng với thông tin mới và có thể điều chỉnh kế hoạch trong ngày.

Điểm cần phân biệt:

- **Daily Scrum:** Sự kiện kiểm tra và điều chỉnh kế hoạch hằng ngày có timebox.
- **Làm việc chi tiết sau Daily Scrum:** Có thể trao đổi kỹ thuật, xử lý lỗi, review, thiết kế hoặc làm rõ yêu cầu với các bên cần thiết.
- **Sprint Retrospective:** Xem lại và cải tiến *cách nhóm làm việc* giữa các Sprint, khác với việc điều chỉnh kế hoạch thực hiện hằng ngày.
- **Sprint Review:** Cùng các bên liên quan xem kết quả và thích ứng hướng sản phẩm, không thay thế Daily Scrum.

## 6. Một chu trình thích ứng hằng ngày khả thi

Developers có thể dùng vòng lặp sau để giữ công việc hướng tới Sprint Goal:

~~~mermaid
flowchart TD
    A["Nhìn Sprint Goal và Sprint Backlog hiện tại"]
    B["Kiểm tra Increment, tiến độ và dữ liệu thực"]
    C["Nhận diện việc bị chặn, rủi ro, thay đổi"]
    D["Chọn hành động để tiến gần Sprint Goal"]
    E["Cập nhật Sprint Backlog và phối hợp thực hiện"]
    F["Review, kiểm thử và tích hợp theo DoD"]
    A --> B --> C --> D --> E --> F
    F -->|"Phản hồi hoặc thông tin mới"| A
~~~

### Bước 1 — Bám mục tiêu trước khi nhìn danh sách task

Hỏi: “Nếu tất cả những công việc đang làm riêng rẽ đều hoàn thành, người học đã đăng ký được khóa chưa?”. Nếu câu trả lời là chưa, cần nhận diện **lát cắt giá trị** còn thiếu, không chỉ đếm task.

### Bước 2 — Kiểm tra bằng chứng thực tế

Điều gì đã chạy qua kiểm thử? Có Increment nào thực sự đạt DoD? Có lỗi tích hợp đang chặn luồng chính? Tốc độ hoàn tất công việc ra sao? Tránh dựa chỉ vào % hoàn thành do từng người tự báo.

### Bước 3 — Nêu trở ngại cùng tác động

Thay vì “Tôi đang bị block”, hãy trình bày:

> “Kiểm thử đăng ký không chạy được trên môi trường tích hợp vì chưa có tài khoản dịch vụ. Điều này cản trở xác minh luồng chính và DoD. Nhóm cần quyền truy cập hoặc một môi trường thay thế được phê duyệt.”

Thông tin cụ thể giúp người khác biết nên làm gì.

### Bước 4 — Quyết định thay đổi đủ nhỏ

Developers có thể chuyển một người sang hỗ trợ review, cùng chia một PBI quá lớn, thêm kiểm thử tích hợp sớm, điều chỉnh thứ tự tác vụ hoặc tổ chức trao đổi với người giải đáp nghiệp vụ. Nếu cần thay đổi phạm vi PBI, cộng tác với Product Owner.

### Bước 5 — Cập nhật Sprint Backlog

Ghi lại kế hoạch mới ở mức cần thiết: task nào thêm/bớt, ai đang phối hợp, trở ngại, rủi ro và bước tiếp theo. Sprint Backlog không nhất thiết là một hệ thống ticket phức tạp; bảng vật lý, bảng điện tử hoặc công cụ phù hợp đều có thể dùng, miễn **minh bạch và dễ cập nhật**.

### Bước 6 — Kiểm chứng Increment, không chỉ hoạt động

Thực hiện và xem kết quả: mã đã tích hợp chưa, kiểm thử phù hợp có đạt không, tiêu chí chấp nhận có được đáp ứng không, DoD có đạt không? Nếu không, kế hoạch phải tiếp tục thích ứng.

## 7. Ra quyết định khi công việc lệch khỏi kế hoạch

### 7.1. Một PBI quá lớn so với dự kiến

Giả sử story “Đăng ký khóa học” lớn hơn ước tính do quy tắc xử lý trùng phức tạp. Developers có thể:

- Chia thành các lát cắt dọc tạo giá trị và kiểm chứng được.
- Cùng xem giải pháp đơn giản nhất đáp ứng yêu cầu bắt buộc.
- Nhờ Product Owner làm rõ giá trị và thứ tự phạm vi.
- Đổi kế hoạch cộng tác hoặc tăng thời gian xử lý nút nghẽn bằng cách hoãn việc ít quan trọng.

**Không nên** gọi giao diện “code xong” là Done nếu phần bảo vệ dữ liệu quan trọng vẫn chưa xong. Nếu phải bỏ một phần chức năng, cần thảo luận với Product Owner và bảo vệ Sprint Goal, DoD cùng các cam kết bên ngoài.

### 7.2. Một thay đổi nghiệp vụ xuất hiện giữa Sprint

Người dùng thử nghiệm cho biết muốn nhận xác nhận đăng ký qua giao diện thay vì chỉ email. Developers nên hỏi:

1. Thay đổi này có giúp hoặc thay đổi ý nghĩa của Sprint Goal không?
2. Quy tắc cốt lõi nào cần xác nhận với Product Owner và người có thẩm quyền?
3. Phần nào có thể làm trong năng lực còn lại, với DoD không đổi?
4. Nếu đưa yêu cầu này vào, công việc nào bị ảnh hưởng?
5. Có thể giao phần giá trị nhỏ, nhận phản hồi rồi làm tiếp ở Sprint sau không?

Scrum không khuyến khích âm thầm đổi Sprint Goal theo từng yêu cầu mới. Nhưng cũng không yêu cầu giữ nguyên từng chi tiết PBI khi nhóm học thêm. **Phạm vi có thể được làm rõ và thương lượng lại với Product Owner**, miễn không gây nguy hiểm cho Sprint Goal và không giảm chất lượng.

### 7.3. Một thành viên vắng mặt đột xuất

Nhóm tự quản không mặc định ép người vắng mặt làm thêm sau đó. Developers cần cập nhật năng lực thực tế, chia lại việc khả thi, chuyển giao thông tin cần thiết và kiểm tra tác động tới Sprint Goal. Nếu không thể đạt phạm vi đã chọn, trao đổi sớm với Product Owner.

Điều này cho thấy vì sao **kiến thức không nên tập trung tuyệt đối ở một người**, nhưng cũng không có nghĩa mỗi cá nhân buộc phải biết tất cả. Làm việc cặp, review, tài liệu vừa đủ và học chéo có thể giảm rủi ro theo thời gian.

### 7.4. Sự cố production khẩn cấp

Nhóm có thể phải xử lý sự cố nghiêm trọng theo chính sách ứng cứu được phê duyệt. Developers cần xác định năng lực bị sử dụng, ảnh hưởng đến Sprint Goal, công việc đang dở và yêu cầu phối hợp với Product Owner hoặc các vai trò vận hành. Không coi sự cố là phần việc “miễn phí” rồi mặc định làm thêm giờ để bù.

### 7.5. Sprint Goal thật sự trở nên lỗi thời

Nếu Sprint Goal trở nên **không còn giá trị**, Scrum cho phép **hủy Sprint**, và chỉ **Product Owner** có thẩm quyền hủy. Đây là trường hợp khác với việc một task bị chậm hoặc một PBI cần chia nhỏ; Developers không tự tuyên bố hủy Sprint chỉ vì tiến độ khó khăn.

## 8. Bảo vệ Definition of Done khi thích ứng

Trong Scrum, **Definition of Done** là mô tả chính thức về trạng thái của Increment khi đáp ứng các thước đo chất lượng cần thiết của sản phẩm. Nếu một PBI chưa đáp ứng DoD, nó **không được coi là một phần của Increment**.

Với story đăng ký khóa học, một số yêu cầu minh họa có thể là:

| Mục | Cần kiểm tra | Sai lầm dễ gặp |
| --- | --- | --- |
| Hành vi chính | Người học đăng ký thành công, thấy khóa trong danh sách | Chỉ kiểm thử thao tác nhấp nút |
| Xử lý lỗi | Không tạo đăng ký trùng, không báo thành công giả | Dùng “happy path” để che lỗi biên quan trọng |
| Quyền truy cập | Người dùng chỉ thay đổi đăng ký thuộc quyền của mình | Chỉ ẩn nút ở UI mà không kiểm tra dịch vụ |
| Tích hợp | Giao diện, API, dữ liệu và xác nhận hoạt động cùng nhau | Mỗi thành phần chạy riêng nhưng luồng thật chưa chạy |
| Kiểm thử và chất lượng | Các kiểm tra, rà soát và yêu cầu chất lượng áp dụng đã đạt | Đẩy kiểm thử bắt buộc sang Sprint sau |
| Vận hành | Có khả năng quan sát lỗi và các bước triển khai cần thiết theo chuẩn | Chỉ chạy trên máy cá nhân |

Đây là **các ví dụ**, không phải một Definition of Done phổ quát do Scrum áp đặt. Nếu tổ chức có chuẩn DoD áp dụng, Scrum Team phải đáp ứng mức đó; nếu chưa có chuẩn tổ chức, Scrum Team tạo DoD phù hợp cho sản phẩm. Khi có nhiều Scrum Team cùng làm một sản phẩm, họ phải cùng định nghĩa và tuân thủ một Definition of Done chung.

**Thích ứng có trách nhiệm** thường có nghĩa:

- Giảm hoặc điều chỉnh **phạm vi** khi cần, không giảm **tiêu chuẩn chất lượng**.
- Tập trung hoàn tất một lát cắt có ích thay vì mở nhiều lát cắt chưa Done.
- Kiểm thử và tích hợp xuyên suốt Sprint, không coi chúng là công việc phát sinh vào ngày cuối.
- Nhận diện nợ kỹ thuật hoặc rủi ro thật, làm rõ thời điểm cần xử lý và tác động đến kế hoạch.

Nếu một PBI chưa đạt DoD, nó không được trình bày như một phần Increment đã hoàn tất và không được phát hành hoặc trình bày như kết quả Done chỉ vì Sprint kết thúc. Nhóm cần minh bạch tình trạng, làm rõ công việc còn lại và điều chỉnh backlog phù hợp.

## 9. Dữ liệu nào giúp Developers thích ứng hằng ngày?

Một Sprint Backlog có ích phải minh bạch tiến độ thật. Ngoài trao đổi trực tiếp, Developers có thể quan sát các tín hiệu:

| Tín hiệu | Câu hỏi giúp quyết định | Giới hạn cần nhớ |
| --- | --- | --- |
| **Số PBI đạt DoD** | Đã có Increment nào đủ chất lượng để hỗ trợ Sprint Goal? | Không phải mọi PBI đều có giá trị hoặc kích thước như nhau |
| **Work in Progress (WIP)** | Có đang mở quá nhiều công việc cùng lúc không? | Cần xác định ranh giới trạng thái nhất quán |
| **Work item age** | Công việc đang làm lâu bất thường ở đâu? | Tuổi dài cần điều tra nguyên nhân, không tự kết luận ai chậm |
| **Cycle time** | Hạng mục đi từ bắt đầu đến Done trong bao lâu? | Dữ liệu lịch sử không bảo đảm thời gian của story riêng |
| **Công việc bị chặn** | Điều gì đang khiến hạng mục không thể tiến gần Done? | Cần ghi tác động và người có thể hỗ trợ |
| **Hàng chờ review / kiểm thử** | Có thể chuyển năng lực để hoàn tất việc gần xong không? | Nếu chỉ tối ưu số ticket đóng, dễ làm sai mục tiêu |
| **Tình trạng CI và lỗi tích hợp** | Có rủi ro chất lượng cản trở Increment không? | Pipeline xanh chưa tự bảo đảm giá trị nghiệp vụ |
| **Phản hồi người dùng hoặc Product Owner** | Có hiểu biết mới làm đổi thứ tự hay cách thực hiện? | Phải đánh giá tác động tới Sprint Goal và thẩm quyền |

**Burndown chart, burnup chart, bảng Kanban hoặc số story point** có thể hỗ trợ nếu nhóm thấy hữu ích, nhưng Scrum không bắt buộc một biểu đồ tiến độ cụ thể. Chỉ số là phương tiện quan sát, không thay thế trao đổi chuyên môn và kiểm tra Increment thực tế.

### 9.1. Ví dụ phát hiện rủi ro sớm

Giả sử Sprint kéo dài 10 ngày làm việc. Vào ngày thứ sáu, nhóm thấy:

- Ba PBI đã Done nhưng chưa tạo được **luồng đăng ký hoàn chỉnh**.
- Hai PBI còn dở đang chờ review và kiểm thử tích hợp.
- Một hạng mục mới vừa được mở, chưa đóng góp trực tiếp tới Sprint Goal.

Thông báo “đã hoàn thành 3/6 PBI” nghe có vẻ 50% nhưng **không đủ để kết luận Sprint Goal tiến triển 50%**. Developers nên nhìn xem những phần đã Done kết hợp được thành kết quả người dùng cần chưa, rồi điều chỉnh kế hoạch để hoàn tất luồng còn thiếu.

### 9.2. Tránh dùng velocity làm thước đo cá nhân

Trong Scrum, **velocity và story point không phải chỉ số bắt buộc**. Nếu sử dụng để hỗ trợ dự báo, không nên biến chúng thành KPI thưởng/phạt từng người. Developers cần có động lực giúp nhau hoàn tất, chia sẻ kiến thức và nêu rủi ro thật; so sánh cá nhân bằng số điểm đóng có thể khuyến khích giấu khó khăn hoặc chia việc giả tạo.

## 10. Tự quản qua một Sprint giả định

Hãy theo dõi Sprint hai tuần của một Scrum Team xây tính năng đăng ký khóa học. Bốn Developers có các kỹ năng về giao diện, dịch vụ, kiểm thử và tích hợp; Product Owner thường xuyên làm rõ nghiệp vụ; Scrum Master hỗ trợ phương pháp và trở ngại.

**Sprint Goal:** “Người học đã đăng nhập đăng ký được khóa miễn phí và nhận được xác nhận đáng tin cậy.”

### Ngày 1 — Lập kế hoạch ban đầu

Developers chọn những PBI có thể hoàn thành sau trao đổi với Product Owner. Cả Scrum Team xây dựng Sprint Goal; Developers phác thảo các lát cắt kiểm chứng được và kế hoạch review, tích hợp, kiểm thử.

**Rủi ro:** Quy tắc đăng ký lại một khóa đã học chưa rõ. Developers ghi câu hỏi và hẹn trao đổi với Product Owner, không mặc định tự đặt quy tắc sản phẩm.

### Ngày 2–3 — Nhận phản hồi kỹ thuật sớm

Giao diện và dịch vụ được kết nối cho một lát cắt nhỏ; kiểm thử phát hiện khả năng tạo bản ghi trùng. Developers bổ sung kiểm thử và điều chỉnh cách xử lý ở tầng dịch vụ. Sprint Backlog cập nhật công việc và tác động.

**Quyết định tự quản:** Chưa bắt đầu một story giao diện ít cấp thiết; hai người phối hợp sửa luồng đăng ký.

### Ngày 4 — Phụ thuộc nghiệp vụ xuất hiện

Product Owner cho biết một người học có thể đăng ký lại sau khi bị hủy theo một số quy tắc. Developers đề nghị ví dụ cho trường hợp chính và ngoại lệ, xem tác động tới acceptance criteria và kiểm thử.

**Quyết định cộng tác:** Product Owner làm rõ quy tắc; Developers chọn cách triển khai phù hợp và cập nhật Sprint Backlog. Nếu khối lượng tăng, hai bên trao đổi phạm vi chứ không giả định mọi yêu cầu mới đều được thêm miễn phí.

### Ngày 5–6 — Hàng chờ review tăng

Hai pull request đang chờ review làm kiểm thử tích hợp bị chặn. Daily Scrum xác định đây là rủi ro của Sprint Goal. Developers chuyển năng lực sang hỗ trợ review, giảm WIP và cùng hoàn tất những lát cắt gần Done.

**Kết quả mong đợi:** Bớt việc dở dang và có luồng đăng ký được xác nhận qua môi trường tích hợp.

### Ngày 7 — Sự cố môi trường

Môi trường kiểm thử không thể kết nối dịch vụ đăng ký. Developers ghi tác động, thử phương án môi trường hợp lệ và nhờ hỗ trợ đúng người có thẩm quyền. Scrum Master hỗ trợ nhóm xử lý trở ngại tổ chức khi phù hợp.

**Điều không nên làm:** Đánh dấu story Done trước khi kiểm thử bắt buộc chạy được.

### Ngày 8–9 — Hoàn tất lát cắt chính

Nhóm xác nhận luồng đăng ký, lỗi thao tác lặp và quyền truy cập. Một ý tưởng phụ “gửi email nhắc học” chưa đạt DoD và không thiết yếu cho Sprint Goal; nhóm cùng Product Owner quyết định xử lý ưu tiên ở backlog phù hợp.

**Bằng chứng:** Có Increment đáp ứng DoD cho hành vi cốt lõi.

### Ngày 10 — Review và Retrospective

Tại Sprint Review, Scrum Team cùng các bên liên quan kiểm tra kết quả và trao đổi phản hồi về trải nghiệm đăng ký. Tại Sprint Retrospective, nhóm xem vì sao review bị nghẽn và môi trường kiểm thử thiếu ổn định để chọn cải tiến cho Sprint sau.

**Bài học:** Kế hoạch đã thay đổi nhiều lần nhưng không phải vì nhóm “không biết lập kế hoạch”; nhóm **đã thích ứng dựa trên điều học được**, tập trung Sprint Goal và giữ chất lượng.

## 11. Scrum, Kanban và XP hỗ trợ nhau như thế nào?

Các cách tiếp cận không đồng nhất. Scrum xác định trách nhiệm, sự kiện và artifact; Kanban cung cấp các cách trực quan hóa và cải thiện dòng chảy; XP chú trọng phản hồi nhanh và kỷ luật kỹ thuật.

| Thực hành | Hỗ trợ Developers tự quản ra sao? | Điều cần phân biệt |
| --- | --- | --- |
| **Scrum: Sprint Backlog** | Làm minh bạch kế hoạch do Developers tạo, cập nhật theo tiến độ tới Sprint Goal | Là artifact của Scrum, không phải danh sách task do quản lý phân |
| **Scrum: Daily Scrum** | Tạo nhịp kiểm tra và điều chỉnh kế hoạch mỗi ngày làm việc | Không phải cuộc họp trạng thái cho Product Owner/manager |
| **Kanban: WIP limit** | Khuyến khích hoàn tất công việc đang làm và giảm hàng chờ | Không có giới hạn WIP cố định bắt buộc cho mọi Scrum Team |
| **Kanban: Work item age, cycle time** | Chỉ ra hạng mục đang tồn lâu hoặc nơi luồng chậm | Cần giữ ranh giới đo nhất quán; không dùng để kết tội cá nhân |
| **XP: Pair programming** | Giúp cộng tác, chia sẻ kiến thức và xử lý phần khó | Không bắt buộc mọi task phải lập trình cặp |
| **XP: TDD và kiểm thử tự động** | Cho phản hồi sớm về thay đổi và giảm lỗi hồi quy | Không thay thế acceptance criteria và DoD |
| **XP: CI, refactoring, small releases** | Giảm rủi ro tích hợp, giúp điều chỉnh kế hoạch an toàn | Cần phù hợp hệ thống và các quy tắc phát hành |

Nhóm có thể dùng bảng Kanban để hiển thị Sprint Backlog, theo dõi WIP và tận dụng kiểm thử tự động trong một Scrum Team. **Việc áp dụng các thực hành bổ sung không làm thay đổi trách nhiệm chính thức của Scrum**, miễn chúng hỗ trợ chứ không phá vỡ các yếu tố cốt lõi.

## 12. Tự quản trong nhóm phân tán hoặc đa chuyên môn

Một Scrum Team làm việc từ xa, khác múi giờ hoặc chia sẻ môi trường với nhóm khác vẫn có thể tự quản, nhưng cần làm rõ:

- **Mục tiêu và trạng thái có thể nhìn thấy:** Sprint Goal cùng Sprint Backlog dễ truy cập, các quyết định quan trọng được ghi lại.
- **Nhịp phối hợp:** Daily Scrum ở thời điểm và địa điểm nhất quán theo thỏa thuận phù hợp; cập nhật công việc không phải chỉ dành cho giờ họp.
- **Trở ngại:** Có kênh ghi việc bị chặn, người có thể hỗ trợ và cách chuyển vấn đề vượt quyền xử lý.
- **Thời gian tập trung:** Không mặc định mọi tin nhắn đều phải được trả lời ngay ngoài giờ làm.
- **Chất lượng chung:** Tất cả các chuyên môn cùng hướng tới Increment đáp ứng DoD, tránh chuyển giao “code xong” rồi bỏ mặc kiểm thử.
- **Quyền quyết định:** Developers tự quyết cách làm; Product Owner giúp làm rõ giá trị/phạm vi; vấn đề bảo mật, hợp đồng hoặc vận hành vượt thẩm quyền được chuyển đúng nơi.

### Ví dụ: quyết định bất đồng bộ không gây lệch hiểu

Khi hai Developers không cùng múi giờ, một người có thể đăng vào Sprint Backlog:

> “Luồng xác nhận đăng ký đang bị chặn vì dịch vụ trả về trạng thái không nhất quán. Tôi đề xuất trước mắt viết kiểm thử tái hiện và xử lý trạng thái ở tầng dịch vụ. Cần người làm việc với hệ thống tích hợp xác nhận thời điểm môi trường sẵn sàng. Việc này ảnh hưởng PBI đăng ký và Sprint Goal.”

Người ở múi giờ khác có thể thấy vấn đề, chuẩn bị kiểm thử và phản hồi trong thời gian làm việc của họ. Khi quyết định ảnh hưởng nghiệp vụ, nhóm ghi rõ phần cần Product Owner làm rõ, tránh suy đoán từ sự im lặng.

Tự quản không phải “tự lo một mình”. Nó đòi hỏi nhóm chủ động **yêu cầu hỗ trợ, ra quyết định trong phạm vi có quyền và minh bạch khi cần chuyển cấp**.

## 13. Những hiểu lầm thường gặp

**1. “Developers chỉ là lập trình viên.”** Trong Scrum, Developers là accountability của những người tạo Increment; có thể bao gồm các chuyên môn khác cần thiết để tạo kết quả sản phẩm.

**2. “Tự quản nghĩa là không cần Product Owner.”** Developers vẫn cần hiểu giá trị sản phẩm, thứ tự Product Backlog và các quy tắc nghiệp vụ do người có trách nhiệm phù hợp làm rõ.

**3. “Product Owner phân task hằng ngày để bảo đảm tiến độ.”** Scrum trao quyền tổ chức và kế hoạch thực hiện cho Developers; Product Owner quản lý hiệu quả Product Backlog và tối đa hóa giá trị.

**4. “Daily Scrum là buổi báo cáo cho Scrum Master.”** Sự kiện nhằm Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh Sprint Backlog; Scrum Master hỗ trợ, không phải người nhận status.

**5. “Bắt buộc trả lời ba câu hỏi hôm qua/hôm nay/trở ngại.”** Đây chỉ là một kỹ thuật có thể chọn. Scrum không bắt buộc cấu trúc này.

**6. “Đã lập Sprint Backlog thì không được thay đổi.”** Kế hoạch được Developers cập nhật khi học thêm; thay đổi phạm vi cần phối hợp với Product Owner và bảo vệ Sprint Goal, DoD.

**7. “Mỗi người chỉ cần hoàn thành task của mình.”** Scrum hướng vào Increment dùng được; giảm hàng chờ review, kiểm thử và tích hợp là trách nhiệm hợp tác của Developers.

**8. “Tăng % hoàn thành task có nghĩa Sprint Goal chắc chắn đạt.”** Số task không thể thay thế đánh giá giá trị và phần Increment đã Done.

**9. “Chất lượng có thể hạ xuống để kịp Sprint.”** Trong Scrum, chất lượng không được giảm trong Sprint; công việc chưa đạt DoD không thuộc Increment hoàn tất.

**10. “Mọi vấn đề phải chờ Daily Scrum.”** Developers có thể cộng tác, điều chỉnh kế hoạch và xử lý sự cố khi cần trong ngày, không chỉ tại một sự kiện.

**11. “Scrum Master chịu trách nhiệm sửa mọi lỗi kỹ thuật.”** Scrum Master hỗ trợ hiệu quả Scrum và việc loại bỏ trở ngại; Developers tự tổ chức công việc kỹ thuật và tìm hỗ trợ phù hợp khi cần.

**12. “Nếu Sprint Goal khó đạt thì Developers tự hủy Sprint.”** Chỉ Product Owner có quyền hủy Sprint khi Sprint Goal trở nên lỗi thời. Khó khăn tiến độ trước hết cần được kiểm tra, thích ứng và trao đổi đúng trách nhiệm.

**13. “Velocity là KPI đánh giá từng Developer.”** Velocity không phải yêu cầu bắt buộc của Scrum và không đo trực tiếp giá trị cá nhân; dùng nó để gây áp lực dễ làm méo hành vi cộng tác.

**14. “Scrum cấm dùng Kanban hay XP.”** Nhóm có thể bổ sung kỹ thuật quản lý luồng và kỹ thuật chất lượng phù hợp, miễn không làm sai vai trò, sự kiện, artifact và commitments của Scrum.

## 14. Bài tập tình huống: Daily Scrum đang trở thành buổi báo cáo

Một Scrum Team phát triển chức năng học trực tuyến có bốn Developers, một Product Owner và một Scrum Master. **Sprint Goal** của Sprint hai tuần là:

> “Người học đã đăng nhập có thể hoàn tất bài kiểm tra ngắn và xem kết quả chính xác.”

Ở ngày làm việc thứ sáu:

- Developer A đã viết xong API chấm điểm nhưng chưa kiểm thử tích hợp với giao diện.
- Developer B đã hoàn thành giao diện nộp bài, phát hiện dữ liệu trả về khác định dạng đã thống nhất.
- Developer C đang viết thêm báo cáo thống kê nâng cao, chưa thiết yếu cho Sprint Goal.
- Developer D chuẩn bị kiểm thử nhưng đang chờ môi trường và dữ liệu kiểm tra.
- Daily Scrum do một quản lý điều hành với câu hỏi “Hôm qua ai làm bao nhiêu giờ? Hôm nay ai phải làm task nào?”, Scrum Master chỉ ghi tên người bị chậm.

### Câu hỏi

1. Những dấu hiệu nào cho thấy Daily Scrum đang lệch mục đích?
2. Developers nên thay đổi kế hoạch trong ngày để tăng khả năng đạt Sprint Goal như thế nào?
3. Ai có trách nhiệm ra quyết định về **cách tích hợp API với giao diện**? Ai giúp làm rõ **ý nghĩa điểm số và quy tắc chấm bài**?
4. Điều gì phải được kiểm chứng trước khi story bài kiểm tra được coi là Done?
5. Nếu có thêm yêu cầu “gửi email bảng điểm” vào giữa Sprint, nhóm nên xử lý ra sao?
6. Hãy viết một bản cập nhật Sprint Backlog ngắn, có hành động cụ thể cho ngày tiếp theo.

### Gợi ý lời giải

**Câu 1:** Buổi trao đổi tập trung vào giờ làm cá nhân và việc quản lý giao task, thay vì kiểm tra tiến độ hướng tới Sprint Goal và tạo kế hoạch hành động của Developers. Các rủi ro tích hợp/kiểm thử chưa được đưa thành hành động chung.

**Câu 2:** Developers có thể tạm dừng công việc báo cáo thống kê chưa thiết yếu, cùng thống nhất định dạng API, sửa và kiểm thử luồng “làm bài → nộp → chấm → xem kết quả”. Hai người phối hợp tạo dữ liệu và gỡ môi trường cho kiểm thử; cập nhật WIP và công việc bị chặn.

**Câu 3:** Developers tự lựa chọn cách giải quyết tích hợp kỹ thuật trong các tiêu chuẩn hệ thống. Product Owner hoặc đại diện nghiệp vụ phù hợp giúp làm rõ quy tắc chấm điểm và kết quả người học phải thấy. Nếu có thẩm quyền phê duyệt đặc biệt, nhóm cần phối hợp đúng người.

**Câu 4:** Đối chiếu acceptance criteria cho các tình huống chính và lỗi, xác minh điểm số chính xác, phân quyền và hành vi khi nộp lại, kiểm thử tích hợp và các yêu cầu chất lượng của Definition of Done. Chỉ “API chạy” và “giao diện hiển thị” riêng rẽ không đủ.

**Câu 5:** Trao đổi giá trị và độ cấp thiết với Product Owner, xem tác động tới Sprint Goal, năng lực và DoD. Có thể đưa vào backlog hoặc điều chỉnh phạm vi đã chọn nếu phù hợp. Không tự thêm rồi mặc định tăng giờ làm hoặc bỏ kiểm thử.

**Câu 6 — Mẫu cập nhật:**

| Hạng mục | Trạng thái mới | Bước tiếp theo do Developers phối hợp |
| --- | --- | --- |
| API chấm điểm | Đang tích hợp | A và B thống nhất định dạng và chạy luồng xuyên hệ thống |
| Giao diện nộp bài | Đang kiểm tra | B sửa cách xử lý phản hồi lỗi; A hỗ trợ kiểm tra dữ liệu |
| Kiểm thử chấm bài | Bị chặn một phần | D và C chuẩn bị dữ liệu thử, làm rõ quyền truy cập môi trường |
| Báo cáo thống kê nâng cao | Hoãn xem xét | C hỗ trợ gỡ nghẽn kiểm thử; trao đổi ưu tiên với Product Owner |
| Sprint Goal | Có rủi ro, đang tập trung xử lý | Kiểm tra lại luồng hoàn tất và DoD vào lần phối hợp tiếp theo |

Mẫu bảng này thể hiện hành động thực tế; **không phải hình thức Sprint Backlog bắt buộc**. Các quyết định phải được Developers thống nhất và cập nhật khi có thông tin mới.

## 15. Bài tập tự thực hành: dẫn dắt 15 phút Daily Scrum

Giả sử nhóm của bạn dùng một bảng:

~~~text
To Do:       Bổ sung email nhắc học
In Progress: Tạo đăng ký | Hiển thị xác nhận | Danh sách khóa
Review:      Kiểm tra quyền truy cập
Blocked:     Kiểm thử luồng đăng ký vì thiếu dữ liệu mẫu
Done:        Tạo bản ghi đăng ký cơ bản
~~~

Sprint Goal là “người học đăng ký được khóa và biết kết quả đăng ký một cách đáng tin cậy”.

Trong vòng **15 phút**, hãy thử thực hiện:

1. Mô tả bằng một câu kết quả người dùng vẫn còn thiếu để đạt Sprint Goal.
2. Chỉ ra hai hạng mục đang làm cần ưu tiên hoàn tất trước khi kéo việc mới.
3. Chọn một trở ngại quan trọng, nêu tác động, người hỗ trợ và bước gỡ.
4. Nêu một thay đổi kế hoạch cụ thể: ai phối hợp với ai, để kiểm tra kết quả gì.
5. Ghi lại cách nhóm kiểm chứng **Done**, thay vì chỉ số task được chuyển cột.

**Ví dụ đáp án:** Đăng ký đã tạo bản ghi cơ bản nhưng chưa có xác nhận tin cậy và chưa kiểm tra quyền truy cập. Nhóm ưu tiên tích hợp hiển thị xác nhận, hoàn tất review phân quyền và tạo dữ liệu kiểm thử luồng đăng ký; chưa mở email nhắc học. Hai Developers phối hợp kiểm thử luồng từ giao diện tới dữ liệu; người có quyền môi trường hỗ trợ chuẩn bị dữ liệu; các kết quả được đối chiếu với acceptance criteria và DoD trước khi đánh dấu Done.

## 16. Danh sách kiểm tra cho Developers mỗi ngày

Trước khi kết thúc Daily Scrum hoặc một lần điều chỉnh kế hoạch, tự hỏi:

1. **Sprint Goal còn rõ và còn giá trị không?** Các thành viên có hiểu mục đích chung?
2. **Điều gì đã Done thật?** Có Increment đáp ứng DoD hay chỉ có công việc kỹ thuật riêng lẻ?
3. **Rủi ro lớn nhất hôm nay là gì?** Có phụ thuộc, sự cố, môi trường hoặc câu hỏi nghiệp vụ nào chặn mục tiêu?
4. **Có quá nhiều WIP không?** Nên giúp hoàn tất việc gần Done trước khi bắt đầu việc mới?
5. **Kế hoạch cần khác hôm qua ở điểm nào?** Có hành động, người phối hợp và bước kiểm chứng cụ thể?
6. **Sprint Backlog đã cập nhật chưa?** Người vắng mặt có thể hiểu trạng thái thật và quyết định mới?
7. **Có cần trao đổi với Product Owner không?** Thay đổi nào ảnh hưởng giá trị, phạm vi hoặc thứ tự ưu tiên?
8. **Có trở ngại cần Scrum Master hoặc người khác hỗ trợ không?** Nhóm đã ghi rõ tác động và điều kiện cần giải quyết?
9. **Chất lượng có được bảo vệ không?** Có đang bỏ qua kiểm thử, tích hợp, phân quyền hoặc DoD để làm đẹp tiến độ?
10. **Có tiếp tục học từ phản hồi không?** Phần tăng dần đã đưa ra cơ hội kiểm chứng với người dùng và cải tiến tiếp theo?

**Ghi nhớ:** Developers trong Scrum không chỉ “nhận task và báo cáo”. Họ **tạo và cập nhật Sprint Backlog, tuân thủ Definition of Done, kiểm tra tiến độ tới Sprint Goal mỗi ngày và cùng chịu trách nhiệm chuyên môn**. Daily Scrum giúp họ tự điều chỉnh kế hoạch; cộng tác với Product Owner và Scrum Master giúp gỡ ranh giới giữa giá trị, cách thực hiện và trở ngại. Tự quản hiệu quả nghĩa là **tự quyết cách làm trong phạm vi trách nhiệm, minh bạch điều chưa chắc chắn, ưu tiên hoàn tất giá trị và bảo vệ chất lượng** — nhờ đó nhóm có thể giao sản phẩm tăng dần và thích ứng liên tục.
