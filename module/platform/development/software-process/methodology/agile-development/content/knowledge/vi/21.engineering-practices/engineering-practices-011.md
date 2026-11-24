# Mối liên hệ giữa Agile, DevOps và trách nhiệm vận hành

## 1. Vì sao giao xong tính năng chưa đồng nghĩa tạo xong giá trị?

Hãy tưởng tượng một nhóm phát triển nền tảng học trực tuyến vừa hoàn thành tính năng đăng ký buổi hướng dẫn. Product Owner đã xem bản trình diễn, các kiểm thử cơ bản đều đạt và nhóm báo cáo rằng user story đã hoàn thành. Tuy nhiên, khi mở cho hàng nghìn học viên đăng ký cùng lúc, dịch vụ bắt đầu trả lỗi, một số người nhận email xác nhận dù đăng ký chưa được lưu, còn nhóm trực vận hành không biết phiên bản nào vừa thay đổi quy tắc đặt chỗ.

Trong tình huống đó, **viết xong mã và trình diễn thành công** chưa đủ để bảo đảm người học nhận được giá trị ổn định. Sản phẩm còn phải được **triển khai, vận hành, quan sát, bảo vệ, khôi phục khi lỗi và cải tiến dựa trên hành vi thực tế**.

Đây là nơi tư duy **Agile** và **DevOps** gặp nhau:

- **Agile** hướng đến tạo giá trị qua các phần tăng trưởng nhỏ, cộng tác gần với người dùng, phản hồi sớm và thích ứng với thay đổi.
- **DevOps** nhấn mạnh văn hóa, cách cộng tác và các thực hành kỹ thuật giúp kết nối hoạt động **phát triển (development)** và **vận hành (operations)** thành dòng tạo giá trị liên tục, đáng tin cậy.
- **Trách nhiệm vận hành** bảo đảm những quyết định khi thiết kế và xây dựng sản phẩm không bị tách khỏi hậu quả khi phần mềm thực sự phục vụ người dùng.

**DevOps không phải tên một công cụ, một chức danh bắt buộc hoặc một giai đoạn thực hiện sau Agile.** Nó là cách giải quyết tình trạng phát triển và vận hành tối ưu riêng phần việc của mình nhưng kết quả chung lại chậm, khó dự báo hoặc nhiều sự cố.

Bài học này thuộc chương **Thực hành kỹ thuật** của module **AGILE_DEVELOPMENT**. Mục tiêu là liên kết user story, backlog, Scrum, Kanban và các kỹ thuật XP với việc triển khai, theo dõi, ứng phó sự cố và học hỏi từ môi trường sử dụng thật. Những phương pháp này không loại trừ nhau: chúng hỗ trợ các khía cạnh khác nhau của hành trình **từ một giả thuyết giá trị đến một dịch vụ thực sự hữu ích và đáng tin**.

### Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích mối quan hệ và giới hạn giữa **Agile, DevOps, DevSecOps và Site Reliability Engineering (SRE)**.
2. Phân biệt việc **viết mã, tích hợp, đạt Done, triển khai, phát hành, vận hành và đạt outcome**.
3. Phân tích trách nhiệm phối hợp giữa người phát triển, Product Owner, kiểm thử, bảo mật, nền tảng và vận hành.
4. Mô tả các vòng phản hồi từ **CI/CD, triển khai có kiểm soát, quan sát hệ thống và sự cố production** về Product Backlog.
5. Vận dụng những khái niệm như **SLI, SLO, error budget, incident response, postmortem, DORA metrics** trong bối cảnh thích hợp.
6. Nhận diện các phản mẫu “ném việc qua tường”, chỉ tối ưu số lần triển khai, bỏ qua vận hành và dùng chỉ số để quy trách nhiệm cá nhân.

## 2. Agile, DevOps, DevSecOps và SRE liên hệ thế nào?

### 2.1. Agile: phản hồi sớm về giá trị và cách làm

Agile đặt trọng tâm vào những giá trị như **con người và tương tác**, **phần mềm hoạt động**, **cộng tác với khách hàng** và **phản hồi trước thay đổi**. Điều đó không có nghĩa Agile cấm quy trình, tài liệu, hợp đồng hay kế hoạch; Agile ưu tiên cách sử dụng chúng để hỗ trợ tạo giá trị thực.

Ví dụ, nhóm triển khai một lát tính năng cho phép học viên xem các buổi còn chỗ rồi quan sát phản hồi. Họ có thể phát hiện vấn đề lớn nhất không phải thiếu bộ lọc nâng cao mà là thời gian buổi học bị hiển thị sai múi giờ. Một vòng phản hồi ngắn cho phép đổi thứ tự backlog trước khi xây thêm tính năng ít có ích.

Tuy nhiên, nếu việc đưa một Increment vào sử dụng mất ba tuần, mọi bản phát hành đều phải sửa tay và hệ thống thường ngừng hoạt động, **vòng phản hồi người dùng vẫn rất chậm**. Agile cần một dòng bàn giao đủ tin cậy để biến ý tưởng thành sản phẩm mà người dùng có thể trải nghiệm.

### 2.2. DevOps: giảm khoảng cách từ mã tới dịch vụ đang hoạt động

DevOps quan tâm đến cách các nhóm cùng chịu trách nhiệm về **dòng chảy thay đổi, chất lượng và độ tin cậy của dịch vụ**. Những thực hành phổ biến gồm:

- Tích hợp và kiểm thử thường xuyên.
- Tự động hóa việc xây dựng, phân phối và triển khai phù hợp.
- Quản lý hạ tầng, cấu hình và môi trường một cách có thể kiểm soát.
- Quan sát hệ thống qua tín hiệu vận hành.
- Ứng phó sự cố, khôi phục và học hỏi không đổ lỗi.
- Giảm thời gian chờ, bàn giao thủ công và những công việc vận hành lặp lại.

**DevOps không bảo đảm mọi nhóm phải tổ chức chung vào một phòng ban.** Một số tổ chức có đội sản phẩm trực tiếp vận hành dịch vụ; nơi khác có đội nền tảng hoặc vận hành tập trung cung cấp năng lực dùng chung. Điểm quyết định là **trách nhiệm và cơ chế phối hợp có được kết nối để người dùng không phải gánh hậu quả của ranh giới tổ chức hay không**.

### 2.3. DevSecOps: đưa bảo mật vào dòng tạo sản phẩm

**DevSecOps** nhấn mạnh rằng bảo mật cần được xem xét và kiểm chứng trong quá trình phát triển, phân phối và vận hành, không chỉ thêm một bước kiểm tra sát ngày phát hành.

Ví dụ, một yêu cầu thêm API đọc tiến độ học cần làm rõ ngay **ai có quyền đọc**, dữ liệu nào được trả về, cách bảo vệ thông tin cá nhân và cách phát hiện truy cập bất thường. Những điều này ảnh hưởng thiết kế, kiểm thử, giám sát và ứng phó sự cố.

DevSecOps không có nghĩa mọi lập trình viên trở thành chuyên gia bảo mật hoặc đội bảo mật mất quyền quyết định. Nó đòi hỏi **phối hợp sớm, công cụ và chính sách phù hợp, trách nhiệm xử lý rõ ràng**.

### 2.4. SRE: một cách thực hành kỹ thuật cho độ tin cậy

**Site Reliability Engineering (SRE)** thường áp dụng tư duy kỹ thuật phần mềm vào các vấn đề vận hành như độ sẵn sàng, độ trễ, năng lực, ứng phó sự cố và giảm việc thủ công lặp lại. Các khái niệm thường gặp gồm **Service Level Indicator (SLI), Service Level Objective (SLO), error budget và giảm toil**.

SRE không đơn giản là tên mới của người trực hệ thống, cũng không bắt buộc mọi đội DevOps phải có một nhóm SRE riêng. Có thể coi SRE là **một tập thực hành cụ thể** hỗ trợ mục tiêu độ tin cậy trong một văn hóa cộng tác phát triển–vận hành.

### 2.5. So sánh trọng tâm

| Cách tiếp cận | Câu hỏi nổi bật | Ví dụ trên nền tảng học |
|---|---|---|
| **Agile** | Chúng ta có đang tạo đúng giá trị và học từ phản hồi kịp thời không? | Có nên ưu tiên cải thiện luồng tiếp tục bài học hơn gợi ý khóa học mới? |
| **DevOps** | Làm sao đưa thay đổi vào sử dụng nhanh, an toàn và nhận được phản hồi vận hành? | Có thể kiểm thử và triển khai luồng đăng ký thường xuyên mà không làm hỏng dịch vụ cũ không? |
| **DevSecOps** | Rủi ro bảo mật và tuân thủ được kiểm soát trong toàn dòng thay đổi ra sao? | API có ngăn học viên xem dữ liệu đăng ký của người khác không? |
| **SRE** | Độ tin cậy dịch vụ được định nghĩa, đo và duy trì như thế nào? | Tỷ lệ yêu cầu đăng ký hợp lệ thành công và thời gian phản hồi có đạt mục tiêu không? |

Chúng **bổ sung nhau**, không tạo thành bốn giai đoạn cứng “Agile xong thì DevOps, rồi DevSecOps, sau đó SRE”. Một thay đổi có giá trị cần được đánh giá từ nhiều góc ngay từ đầu.

## 3. Một dòng giá trị: từ ý tưởng đến phản hồi production

Trong phát triển sản phẩm, giá trị thường đi qua nhiều trạng thái:

~~~mermaid
flowchart TD
    A["Vấn đề người dùng và giả thuyết giá trị"] --> B["Product Backlog và phần giá trị ưu tiên"]
    B --> C["Thiết kế, mã hóa và kiểm thử sớm"]
    C --> D["CI: tích hợp và kiểm tra"]
    D --> E["Increment đáp ứng chất lượng"]
    E --> F["Triển khai và phát hành theo chính sách"]
    F --> G["Người dùng sử dụng dịch vụ"]
    G --> H["Quan sát outcome, chất lượng, sự cố"]
    H --> I["Điều chỉnh backlog, kiến trúc và cách làm"]
    I --> B
    D -->|Lỗi hoặc rủi ro| C
    F -->|Không an toàn| E
~~~

Đây là **sơ đồ khái niệm**, không phải pipeline bắt buộc cho mọi tổ chức. Trong thực tế, khám phá sản phẩm, thiết kế, kiểm thử và quan sát có thể diễn ra song song; phản hồi có thể xuất hiện ở nhiều bước.

### 3.1. Các trạng thái cần phân biệt

| Trạng thái | Điều đã có | Điều chưa thể tự kết luận |
|---|---|---|
| **Đã viết mã** | Phần triển khai tồn tại. | Chưa chắc đúng nghiệp vụ, tích hợp hoặc an toàn. |
| **CI xanh** | Các phép kiểm tra đã cấu hình đạt trong lần chạy đó. | Chưa chứng minh không có lỗi chưa được kiểm tra. |
| **PBI/Increment đạt Definition of Done** | Phần sản phẩm đáp ứng tiêu chuẩn chất lượng áp dụng và dùng được theo phạm vi xác định. | Chưa tự chứng minh người dùng sẽ yêu thích hoặc sử dụng nhiều. |
| **Đã deploy** | Bản thay đổi được đưa đến một môi trường cụ thể. | Chưa chắc tính năng đã bật hoặc người dùng đã tiếp cận. |
| **Đã release** | Khả năng được cung cấp cho một nhóm người dùng/khách hàng theo kế hoạch. | Chưa chắc outcome mong đợi đã xảy ra. |
| **Vận hành ổn định** | Các tín hiệu được theo dõi và dịch vụ đang đáp ứng kỳ vọng trong phạm vi quan sát. | Không có nghĩa không thể còn rủi ro hoặc biến động trong tương lai. |
| **Outcome đạt được** | Có bằng chứng người dùng hoặc tổ chức nhận kết quả mong muốn. | Cần cân nhắc chất lượng dữ liệu và tác động dài hạn. |

Một nhóm có thể tích hợp và triển khai nhiều lần trong ngày nhưng vẫn chưa tạo giá trị nếu thay đổi không giải quyết được nhu cầu. Ngược lại, một tính năng ít người dùng có thể có giá trị lớn nếu nó khắc phục một lỗi nghiêm trọng hoặc giảm rủi ro đáng kể.

### 3.2. Feedback loop mở rộng về vận hành

Vòng phản hồi Agile không nên kết thúc ở buổi trình diễn. Khi tính năng đã được sử dụng, nhóm còn học được:

- Hành vi thực tế khác gì với giả định khi viết user story?
- Hệ thống có đáp ứng tải, độ trễ và điều kiện mạng của người dùng không?
- Có lỗi hiếm, thao tác lặp, trạng thái đồng thời hoặc vấn đề phân quyền nào lộ ra?
- Nhóm có thể phát hiện và khôi phục khi sự cố xảy ra không?
- Những bài học nào cần trở lại Product Backlog và Definition of Done?

**Vận hành là một nguồn phản hồi về sản phẩm và kỹ thuật**, không chỉ là nơi tiếp nhận phần mềm sau khi các nhóm khác báo hoàn thành.

## 4. Trách nhiệm chung nhưng quyền quyết định vẫn rõ ràng

**Shared responsibility (trách nhiệm chung)** không đồng nghĩa mọi người được quyền tự ý thay đổi production hoặc phải trực hệ thống như nhau. Những quyền hạn và chuyên môn khác nhau vẫn cần được giữ rõ.

| Nhóm/trách nhiệm có thể có | Đóng góp quan trọng | Điều không nên nhầm |
|---|---|---|
| **Product Owner / người chịu trách nhiệm sản phẩm** | Giá trị, ưu tiên backlog, cân bằng tính năng với chất lượng và rủi ro kinh doanh. | Không phải người quyết định mọi cấu hình hạ tầng hoặc tự khắc phục mọi sự cố. |
| **Developers / kỹ sư sản phẩm** | Thiết kế, xây, tích hợp, kiểm thử và hỗ trợ chất lượng/vận hành của thành phần mình tạo. | Không thể xem nhiệm vụ kết thúc ở lúc merge mã nếu còn rủi ro sản phẩm. |
| **Kiểm thử/chất lượng** | Thiết kế cách kiểm chứng, tìm trường hợp biên, đánh giá rủi ro. | Không phải người duy nhất “sở hữu” chất lượng của cả team. |
| **Đội nền tảng** | Cung cấp pipeline, môi trường, quyền truy cập, tiêu chuẩn và dịch vụ tự phục vụ đáng tin. | Không chỉ là nhóm cấp tài khoản rồi chịu mọi lỗi ứng dụng. |
| **Đội vận hành/SRE** | Năng lực quan sát, độ tin cậy, ứng phó, năng lực hệ thống, tự động hóa và phối hợp vận hành. | Không phải “thùng chứa” nhận mọi lỗi sau phát hành. |
| **Đội bảo mật/tuân thủ** | Tiêu chuẩn, tư vấn chuyên môn, kiểm soát và thẩm quyền theo quy định. | Không thể chỉ được mời vào một ngày trước release rồi chịu hết rủi ro. |
| **Hỗ trợ khách hàng và người dùng** | Phản ánh sự cố, tình huống thật và mức ảnh hưởng tới người dùng. | Báo cáo từ họ cần được đưa vào vòng học hỏi thay vì xem là nhiễu. |

Scrum Team có accountability chung đối với việc tạo **Increment có giá trị và hữu ích mỗi Sprint**, trong khi Product Owner, Scrum Master và Developers có accountability riêng theo Scrum. Một tổ chức có thể phân công trách nhiệm triển khai, trực sự cố hoặc phê duyệt khác nhau; điều quan trọng là **không để khoảng trống giữa các nhóm khiến rủi ro bị bỏ qua**.

### 4.1. “You build it, you run it” nên được hiểu theo năng lực

Nguyên tắc thường được diễn đạt là **“you build it, you run it”** nhằm nhấn mạnh người thiết kế và phát triển dịch vụ phải quan tâm đến hậu quả vận hành: lỗi, độ trễ, cảnh báo, dữ liệu và việc phục hồi.

Điều đó **không bắt buộc** mọi lập trình viên trực 24/7, có quyền truy cập production không giới hạn hoặc thực hiện mọi công việc của đội SRE. Tổ chức cần xét năng lực, an toàn, sức khỏe, luật lao động, trách nhiệm bảo mật và chính sách trực vận hành.

Một mô hình phù hợp có thể là:

- Đội sản phẩm sở hữu hiểu biết về hành vi ứng dụng và phối hợp sửa lỗi.
- Đội nền tảng cung cấp môi trường, pipeline, quyền và khả năng giám sát dùng chung.
- Người trực sự cố có thẩm quyền rõ và biết cách gọi chuyên gia sản phẩm khi cần.
- Các quyết định rủi ro được thông báo cho người chịu trách nhiệm sản phẩm và dịch vụ.
- Hậu kiểm tìm cách giảm tái diễn, thay vì chỉ bổ sung người vào lịch trực.

### 4.2. Phải rõ cả trách nhiệm ra quyết định

Khi production có vấn đề, cần biết:

1. Ai có quyền **tạm tắt tính năng**, giảm tải, rollback hoặc kích hoạt phương án dự phòng?
2. Ai chịu trách nhiệm **đánh giá và thông báo ảnh hưởng tới khách hàng**?
3. Ai xác nhận các **điều kiện an toàn để khôi phục**?
4. Ai điều phối nhiều đội khi một sự cố ảnh hưởng API, cơ sở dữ liệu và hạ tầng?
5. Ai sắp lại Product Backlog khi cần hoãn tính năng để xử lý chất lượng?

Những quyết định này có thể được mô tả bằng một ma trận trách nhiệm hoặc playbook ngắn. Không cần dùng một mô hình tổ chức duy nhất, nhưng **trách nhiệm chung không được làm mờ trách nhiệm quyết định cụ thể**.

## 5. Đưa vận hành và chất lượng vào Definition of Done

Trong Scrum, **Increment** là bước tiến cụ thể của sản phẩm hướng tới Product Goal, phải tích hợp với những Increment trước và dùng được. **Definition of Done (DoD)** là commitment mô tả trạng thái chất lượng cần đạt của Increment.

Nếu team tuyên bố tính năng “Đăng ký buổi học” Done khi nút bấm hoạt động nhưng không có cách xác định một đăng ký đã lưu thật hay chưa, phần mềm có thể gây ra hậu quả khi tải tăng. Những yêu cầu vận hành thiết yếu cần được xem xét **ngay trong quá trình thiết kế và làm việc**, không dồn toàn bộ vào một “giai đoạn vận hành” sau này.

### 5.1. Các điều kiện đáng cân nhắc trong DoD

| Khía cạnh | Câu hỏi chất lượng | Bằng chứng minh họa |
|---|---|---|
| **Hành vi nghiệp vụ** | Đăng ký có đúng sức chứa và trạng thái không? | Các tiêu chí chấp nhận và trường hợp biên quan trọng đã được xác minh. |
| **Tích hợp** | Frontend, backend, dữ liệu và dịch vụ liên quan hoạt động cùng nhau không? | Kiểm thử tích hợp/hợp đồng phù hợp đạt. |
| **Bảo mật và dữ liệu** | Người dùng chỉ thấy và sửa dữ liệu mình được phép? | Kiểm tra phân quyền và các kiểm soát bắt buộc. |
| **Xử lý lỗi** | Lỗi mạng hoặc thao tác lặp có tạo trạng thái sai không? | Kiểm tra timeout, retry, idempotency và thông báo đúng thực tế nếu áp dụng. |
| **Khả năng quan sát** | Khi lỗi xảy ra có phát hiện và điều tra được không? | Metric/log/trace cần thiết, không lộ dữ liệu nhạy cảm. |
| **Khả năng triển khai** | Có thể chuyển phiên bản an toàn theo chính sách không? | Kiểm tra cấu hình, migration, chiến lược phục hồi khi cần. |
| **Độ tin cậy** | Có đáp ứng những yêu cầu hiệu năng/khả dụng liên quan? | Các phép kiểm tra phù hợp mức tải và rủi ro. |
| **Vận hành** | Đội ứng phó có đủ thông tin để nhận biết và xử lý vấn đề? | Hướng dẫn/runbook, quyền, dashboard hoặc cảnh báo cần thiết. |
| **Bảo trì** | Thay đổi có khiến đội khó sửa an toàn ở Sprint sau? | Kiểm thử hồi quy, rà soát thay đổi và tài liệu thiết yếu. |

Đây là **danh sách gợi ý để chọn theo bối cảnh**, không phải DoD chuẩn áp dụng cứng cho mọi PBI. Những tiêu chuẩn bảo mật, pháp lý, an toàn hoặc tổ chức bắt buộc vẫn phải được tuân thủ.

### 5.2. DoD, release criteria và outcome khác nhau

- **DoD**: phần sản phẩm đạt chất lượng yêu cầu để được coi Done và usable.
- **Release criteria**: điều kiện quyết định có đưa Increment tới nhóm người dùng cụ thể vào thời điểm này không.
- **Operational readiness**: mức sẵn sàng vận hành phù hợp; những phần bắt buộc để Increment dùng được nên được đưa vào tiêu chuẩn chất lượng áp dụng, còn hoạt động thương mại hoặc phối hợp phát hành có thể là điều kiện riêng.
- **Outcome**: kết quả người dùng hoặc tổ chức đạt được sau khi phần mềm hoạt động trong thực tế.

Ví dụ, dịch vụ đã có tính năng xem buổi còn chỗ, đạt DoD, nhưng tổ chức chưa mở rộng cho tất cả trường học do kế hoạch giới thiệu sản phẩm. Điều đó không tự biến Increment thành chưa Done. Ngược lại, một tính năng đã mở cho người dùng nhưng không đáp ứng kiểm soát dữ liệu **không thể được hợp thức hóa chỉ bằng việc nó đang chạy trên production**.

### 5.3. Tránh biến DoD thành thủ tục hình thức

Nếu checklist ghi “đã có dashboard” nhưng dashboard không phát hiện được giao dịch lỗi, nhóm chỉ tối ưu dấu kiểm. Thay vào đó, hỏi **tín hiệu nào chứng minh chất lượng mong muốn** và kiểm tra rằng công cụ thực sự cung cấp tín hiệu đó.

## 6. CI và phản hồi kỹ thuật sớm

**Continuous Integration (CI)** là thực hành tích hợp thay đổi thường xuyên vào codebase chung, kèm kiểm tra tự động phù hợp để phát hiện sai lệch sớm. Một nhánh tồn tại nhiều tuần có thể làm cho kiểm thử của từng người đều xanh nhưng khi kết hợp thì API, schema hoặc cấu hình không còn tương thích.

### 6.1. Những vòng kiểm tra minh họa

~~~text
Thay đổi nhỏ
  -> kiểm tra nhanh tại máy phát triển
  -> tích hợp vào nhánh chung theo chính sách
  -> build, unit tests, static checks
  -> contract/integration tests cho vùng ảnh hưởng
  -> kiểm tra bảo mật và chất lượng cần thiết
  -> tạo bản build có thể truy xuất nguồn gốc
  -> chuyển sang kiểm chứng và triển khai phù hợp
~~~

Không có một danh sách công cụ hoặc thời lượng pipeline bắt buộc cho mọi hệ thống. Mục tiêu là **phản hồi đủ nhanh để sửa khi ngữ cảnh còn mới**, đồng thời không làm suy yếu các kiểm soát bắt buộc.

### 6.2. Tín hiệu pipeline xanh có giới hạn

Pipeline thành công chỉ cho biết **những điều đã được kiểm tra trong phạm vi đã định** đạt kết quả. Nó không chứng minh:

- Mọi trường hợp nghiệp vụ đều đã được nghĩ tới.
- Hai yêu cầu đồng thời không thể làm sai dữ liệu.
- Quyền truy cập đúng với mọi loại tài khoản.
- Hệ thống vẫn hoạt động khi đối tác trả lỗi, mạng chậm hoặc tải tăng đột biến.
- Người dùng hiểu giao diện và thực sự nhận được giá trị.

Vì vậy, nên có nhiều mức kiểm chứng: unit test, contract/integration test, thử hành vi, kiểm thử khám phá, kiểm tra rủi ro và quan sát sau triển khai.

### 6.3. Chất lượng tín hiệu quan trọng hơn số bài kiểm thử

Một bộ kiểm thử chạy rất nhanh nhưng thường thất bại ngẫu nhiên (**flaky tests**) có thể làm nhóm mất niềm tin. Một bộ kiểm thử khác có hàng nghìn bài nhưng bỏ sót xử lý đồng thời có thể tạo ảo giác an toàn.

Khi pipeline báo lỗi, nhóm cần điều tra và xử lý kịp thời. Không nên liên tục chạy lại cho đến khi xanh mà không hiểu nguyên nhân, hoặc tắt kiểm tra quan trọng để đạt chỉ tiêu tốc độ.

### 6.4. Liên hệ với XP

Các thực hành XP như **TDD, pair programming, refactoring và continuous integration** giúp rút ngắn vòng phản hồi kỹ thuật. Khi ghép với DevOps, những kỹ thuật đó không dừng ở mã: chúng hỗ trợ quá trình **đưa thay đổi vào dịch vụ đang sử dụng một cách an toàn, có thể quan sát và sửa chữa**.

## 7. Continuous Delivery, Continuous Deployment và release an toàn

Ba khái niệm dễ bị nhầm:

- **Continuous Integration**: tích hợp và kiểm tra thay đổi thường xuyên.
- **Continuous Delivery**: duy trì khả năng đưa phần mềm ở trạng thái đủ điều kiện phát hành thông qua quy trình lặp lại, đáng tin; quyết định release có thể vẫn do người có thẩm quyền thực hiện.
- **Continuous Deployment**: những thay đổi đáp ứng điều kiện được tự động triển khai tới môi trường sử dụng theo chính sách đã thiết lập.

**Deployment (triển khai)** cũng không luôn trùng với **release (mở khả năng cho người dùng)**. Feature flag hoặc cấu hình theo nhóm người dùng có thể tách hai thời điểm đó.

### 7.1. Những kỹ thuật giảm rủi ro khi phát hành

| Kỹ thuật | Ý tưởng | Lợi ích | Điểm cần kiểm soát |
|---|---|---|---|
| **Feature flag** | Bật/tắt hành vi theo đối tượng hoặc điều kiện. | Triển khai mã trước khi mở rộng sử dụng. | Tổ hợp trạng thái, dọn flag cũ, kiểm soát quyền và kiểm thử. |
| **Canary release** | Mở bản mới cho một phần nhỏ lưu lượng trước. | Quan sát tín hiệu thực trước khi mở rộng. | Mẫu nhỏ có thể không đại diện; cần tiêu chí dừng và khả năng quay lại. |
| **Blue–green deployment** | Chuẩn bị môi trường/phiên bản thay thế để chuyển lưu lượng. | Giảm thời gian chuyển phiên bản nếu thiết kế phù hợp. | Chi phí môi trường, tính nhất quán dữ liệu và chuyển trạng thái. |
| **Rolling deployment** | Thay lần lượt các phiên bản đang phục vụ. | Không cần thay toàn bộ hệ thống cùng lúc. | Tương thích giữa các phiên bản khi cùng tồn tại. |
| **Rollback** | Quay lại phiên bản/đường đi trước theo quy trình an toàn. | Có thể khôi phục nhanh một số loại lỗi. | Schema, dữ liệu đã ghi và các sự kiện đã phát ra không tự quay lại. |
| **Kill switch / tắt luồng nguy hiểm** | Vô hiệu hóa một khả năng gây rủi ro. | Có thể ngăn thiệt hại trước khi sửa đầy đủ. | Phải biết ảnh hưởng, quyền thao tác và phương án phục hồi. |

Không phải mọi hệ thống đều cần sử dụng tất cả các kỹ thuật. Chọn chúng theo **kiến trúc, rủi ro, khả năng giám sát và năng lực ứng phó**.

### 7.2. Một quy trình triển khai có kiểm soát

Ví dụ minh họa cho thay đổi đăng ký buổi học:

1. Tạo bản build đã được kiểm tra và có thông tin phiên bản rõ.
2. Xác nhận những điều kiện chất lượng, bảo mật và tương thích cần thiết.
3. Triển khai theo phạm vi được phép.
4. Theo dõi các tín hiệu trọng yếu như tỷ lệ đăng ký thành công, lỗi ghi dữ liệu và độ trễ.
5. Nếu tín hiệu cho thấy nguy cơ vượt ngưỡng, dừng mở rộng, giảm tác động hoặc quay lại đường đi an toàn theo runbook.
6. Khi ổn định, mở rộng dần và tiếp tục theo dõi.
7. Ghi phản hồi và bài học cho thay đổi tiếp theo.

Không được dùng “canary” như lời biện hộ để thử những thay đổi có khả năng làm lộ dữ liệu hoặc gây thiệt hại không chấp nhận được cho một nhóm người dùng thật.

### 7.3. Database migration cần tương thích

Một ứng dụng có thể chạy đồng thời phiên bản cũ và mới khi triển khai theo phần. Nếu thay đổi schema đột ngột khiến phiên bản cũ không còn đọc/ghi được, rollback mã ứng dụng có thể thất bại.

Một cách tư duy hữu ích là **expand–migrate–contract**:

1. **Expand:** mở rộng schema/hợp đồng theo cách vẫn cho phép phiên bản cũ hoạt động.
2. **Migrate:** cập nhật ứng dụng và dữ liệu có kiểm chứng; xử lý cả trạng thái hỗn hợp trong thời gian chuyển tiếp.
3. **Contract:** chỉ loại bỏ phần cũ khi đã xác nhận không còn phụ thuộc và có phương án vận hành phù hợp.

Đây không phải công thức áp dụng mù quáng cho mọi thay đổi dữ liệu. Những migration có nguy cơ mất dữ liệu cần đánh giá riêng, sao lưu và xác minh phù hợp; **rollback ứng dụng không có nghĩa các thao tác đã ghi xuống dữ liệu tự đảo ngược được**.

## 8. Hạ tầng, cấu hình và nền tảng như một phần của dòng giá trị

**Infrastructure as Code (IaC)** và **configuration management** giúp mô tả, xem xét và thay đổi môi trường bằng những cấu hình có thể kiểm soát, thay vì chỉ dựa vào thao tác thủ công không có dấu vết.

Lợi ích có thể gồm:

- Môi trường thử và môi trường vận hành nhất quán hơn.
- Thay đổi cấu hình có lịch sử, người xem xét và khả năng truy vết.
- Giảm sai lệch giữa các môi trường (**configuration drift**).
- Tái tạo hoặc khôi phục môi trường có kiểm soát.
- Cung cấp tài nguyên theo cách tự phục vụ phù hợp với tiêu chuẩn tổ chức.

### 8.1. IaC không đồng nghĩa tự động an toàn

Một cấu hình viết thành mã vẫn có thể sai: mở quyền mạng quá rộng, đặt bí mật vào nơi công khai, chọn sai tham số sao lưu hoặc tạo quá nhiều tài nguyên. Nhóm cần **rà soát, kiểm tra quyền, quản lý bí mật, kiểm thử và quy trình thay đổi** tương xứng rủi ro.

Không đưa mật khẩu, token hoặc khóa bí mật vào kho mã nguồn chỉ để mọi thành viên triển khai dễ hơn. Sử dụng cơ chế quản lý bí mật, quyền tối thiểu và luân chuyển thông tin xác thực theo tiêu chuẩn tổ chức.

### 8.2. Đội nền tảng và “self-service” hợp lý

Một **platform team** có thể cung cấp đường triển khai đã chuẩn hóa, dịch vụ log/metric, môi trường thử, cơ chế cấp quyền và mẫu cấu hình tốt. Điều này giảm việc mỗi nhóm phải tự giải quyết những vấn đề hạ tầng giống nhau.

Tuy vậy, **nền tảng không nên trở thành một hàng chờ mới cho mọi yêu cầu nhỏ**. Nếu một nhóm phải mở ticket chờ nhiều ngày để tạo môi trường thử, tổ chức cần xem lại API tự phục vụ, thẩm quyền, năng lực và các chính sách an toàn.

### 8.3. Vận hành cần được thiết kế, không chờ tới lúc có sự cố

Đối với một dịch vụ mới, nên làm rõ từ sớm:

- Ai nhận cảnh báo và có quyền hành động?
- Phần nào cần giám sát để biết dịch vụ thật sự phục vụ người dùng?
- Có những tình huống sự cố nào cần runbook?
- Hệ thống có thể khôi phục hoặc chuyển sang trạng thái an toàn như thế nào?
- Dữ liệu cần được sao lưu, lưu giữ và bảo vệ theo chính sách nào?
- Các phụ thuộc bên ngoài, giới hạn năng lực và kịch bản quá tải là gì?

**Operational readiness** là khả năng team biết cách vận hành dịch vụ mình giao, không chỉ một checklist được ký tên sát giờ release.

## 9. Observability: quan sát điều gì đang xảy ra trong production?

**Monitoring (giám sát)** theo dõi những chỉ số, sự kiện hoặc điều kiện đã xác định để phát hiện vấn đề. **Observability (khả năng quan sát)** rộng hơn: từ những tín hiệu hệ thống phát ra, người kỹ sư có thể đặt câu hỏi và điều tra **vì sao** dịch vụ hành xử như vậy, kể cả với trường hợp chưa được dự đoán trước.

Ba loại tín hiệu thường gặp:

- **Metrics:** số đo tổng hợp theo thời gian, như tỷ lệ lỗi, độ trễ, số yêu cầu, số đăng ký thành công.
- **Logs:** các bản ghi sự kiện có cấu trúc phù hợp, giúp hiểu thao tác và trạng thái cụ thể.
- **Traces:** thông tin về hành trình của một yêu cầu qua nhiều dịch vụ, hữu ích khi điều tra độ trễ hoặc lỗi tại một thành phần.

Chúng không thay thế nhau. Một dashboard hiển thị “5% yêu cầu thất bại” giúp phát hiện vấn đề; log và trace phù hợp có thể giúp tìm ra lỗi chỉ xuất hiện khi gọi dịch vụ tồn kho hoặc gửi thông báo.

### 9.1. Quan sát từ góc nhìn người dùng

Thay vì chỉ đo CPU hoặc số container đang chạy, hãy hỏi **người dùng có hoàn thành được tác vụ quan trọng không**.

| Hành trình | Tín hiệu minh họa | Vấn đề có thể phát hiện |
|---|---|---|
| Đăng nhập | Tỷ lệ đăng nhập thành công của yêu cầu hợp lệ, độ trễ. | Dịch vụ xác thực chậm hoặc lỗi. |
| Xem buổi còn chỗ | Tỷ lệ phản hồi đúng, thời gian tải, lỗi API. | Người học không thể chọn buổi dù trang chủ vẫn hoạt động. |
| Đăng ký buổi học | Tỷ lệ đăng ký hợp lệ thành công, lỗi ghi trạng thái, trùng số chỗ. | Hệ thống báo thành công sai hoặc vượt sức chứa. |
| Nhận xác nhận | Tỷ lệ xác nhận đúng sau khi giao dịch đã được ghi nhận. | Gửi mail thiếu, trễ hoặc không khớp trạng thái. |
| Tiếp tục bài học | Tỷ lệ mở lại đúng nội dung và lỗi mất tiến độ. | Người học không thể quay lại bài đang học. |

Cần định nghĩa rõ **yêu cầu hợp lệ**, cách loại trừ lỗi do người dùng nhập sai và điều kiện ghi nhận thành công để chỉ số không bị hiểu nhầm.

### 9.2. Bảo vệ thông tin nhạy cảm trong telemetry

Log chi tiết có thể giúp điều tra nhưng cũng có nguy cơ tiết lộ email, mã truy cập, token, thông tin thanh toán hoặc dữ liệu riêng tư. Nên:

- Giới hạn thông tin thu thập theo mục đích.
- Tránh ghi secrets, token hoặc dữ liệu cá nhân không cần thiết.
- Dùng mã tương quan/trace ID được thiết kế an toàn.
- Kiểm soát quyền truy cập, thời gian lưu và cách xóa theo chính sách.
- Phân biệt dữ liệu thử và dữ liệu thật, đặc biệt trong môi trường phát triển.

**Khả năng quan sát tốt phải tương thích với bảo mật và quyền riêng tư**, không đạt được bằng cách ghi mọi thứ vô hạn.

### 9.3. Alert có ích phải dẫn tới hành động

Một cảnh báo hữu ích trả lời:

1. Điều gì đang vi phạm kỳ vọng và người dùng bị ảnh hưởng ra sao?
2. Ai nhận cảnh báo, trong giờ làm hay qua cơ chế trực?
3. Cần làm gì trước tiên để xác minh và giảm tác động?
4. Khi nào cần tăng cấp hoặc gọi chuyên gia?
5. Làm sao biết sự cố đã được kiểm soát?

Nếu cảnh báo quá nhiều nhưng không có hành động rõ, người trực có thể bỏ qua cả tín hiệu quan trọng. Ngược lại, thiếu cảnh báo về lỗi nghiệp vụ nghiêm trọng khiến người dùng trở thành hệ thống phát hiện lỗi duy nhất.

## 10. SLI, SLO, SLA và error budget

Để quản lý độ tin cậy dựa trên bằng chứng, nhóm cần một ngôn ngữ rõ cho **chất lượng dịch vụ**.

| Khái niệm | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| **SLI — Service Level Indicator** | Một phép đo định lượng về một khía cạnh dịch vụ. | Tỷ lệ yêu cầu đăng ký hợp lệ được xử lý thành công trong ngưỡng thời gian xác định. |
| **SLO — Service Level Objective** | Mục tiêu đặt cho SLI trong một khoảng thời gian. | Ít nhất 99,9% yêu cầu hợp lệ đáp ứng điều kiện trong cửa sổ 30 ngày. |
| **SLA — Service Level Agreement** | Thỏa thuận về mức dịch vụ với các điều khoản và hệ quả cụ thể khi áp dụng. | Cam kết dịch vụ với khách hàng theo hợp đồng. |
| **Error budget** | Phần mức độ không đạt SLO được chấp nhận theo mục tiêu và cửa sổ đo. | Khoảng sai lệch còn lại trước khi vượt ngưỡng SLO đã chọn. |

**SLO không tự động là SLA**; nhiều mục tiêu nội bộ không phải cam kết pháp lý. Một SLI có ý nghĩa cần có cách tính, phạm vi, dữ liệu nguồn và điều kiện loại trừ rõ ràng.

### 10.1. Ví dụ minh họa một SLI theo yêu cầu

Giả sử nhóm định nghĩa:

~~~text
SLI đăng ký thành công (%) =
  Số yêu cầu đăng ký hợp lệ được xử lý đúng và trả kết quả trong ngưỡng
  / Tổng số yêu cầu đăng ký hợp lệ thuộc phạm vi đo
  × 100

SLO minh họa:
  SLI >= 99,9% trong cửa sổ đo 30 ngày.
~~~

Ví dụ này chỉ minh họa cấu trúc phép đo. Cần làm rõ các trường hợp như yêu cầu bị từ chối hợp lệ vì hết chỗ, thao tác gửi lặp và giao dịch đang chờ kết quả; nếu tính tất cả là “lỗi”, SLI sẽ đo sai chất lượng.

### 10.2. Error budget hỗ trợ cân bằng đổi mới và ổn định

Nếu SLO yêu cầu 99,9% yêu cầu hợp lệ đáp ứng tiêu chí, về mặt tỷ lệ, **0,1% còn lại** là phần không đạt mục tiêu cho phép trong phạm vi đo. Error budget không phải giấy phép tạo lỗi, cũng không thay thế yêu cầu an toàn hay pháp lý.

Một nhóm có thể dùng mức tiêu thụ error budget như **tín hiệu quản trị rủi ro**:

- Khi dịch vụ ổn định và các chỉ số còn dư địa, nhóm có thể cân nhắc phát hành những thay đổi có kiểm soát.
- Khi sai lệch tăng hoặc SLO có nguy cơ không đạt, nhóm có thể ưu tiên giảm lỗi, cải thiện độ tin cậy, giới hạn thay đổi rủi ro cao hoặc tăng kiểm chứng.
- Khi lỗi nghiêm trọng ảnh hưởng dữ liệu hoặc an toàn, cần xử lý ngay dù error budget còn nhiều.

Không phải mọi sản phẩm cần SLO giống nhau; đặt mục tiêu gần tuyệt đối mà không xét chi phí, khả năng đo và nhu cầu người dùng có thể làm giảm năng lực tạo giá trị mà không cải thiện trải nghiệm tương xứng.

### 10.3. Độ tin cậy không chỉ là uptime

Một trang vẫn trả HTTP 200 có thể hiển thị số chỗ sai hoặc xác nhận giao dịch chưa thành công. Người dùng có thể xem dịch vụ là **không đáng tin** dù máy chủ “đang chạy”.

Vì vậy, các chỉ số độ tin cậy nên liên hệ **hành trình người dùng và bất biến nghiệp vụ**; có thể cần kết hợp độ sẵn sàng, độ trễ, tính đúng đắn dữ liệu và mức an toàn.

## 11. Incident response: xử lý sự cố như một trách nhiệm sản phẩm

**Incident (sự cố)** là tình huống dịch vụ bị suy giảm hoặc có nguy cơ gây tác động cần được xử lý theo cơ chế ứng phó của tổ chức. Khi sự cố đang gây thiệt hại, ưu tiên là **bảo vệ người dùng và giảm tác động**, sau đó điều tra và cải tiến.

Một chu trình ứng phó minh họa:

~~~mermaid
flowchart TD
    A["Tín hiệu lỗi hoặc báo cáo từ người dùng"] --> B["Xác nhận tác động và kích hoạt ứng phó"]
    B --> C["Điều phối người, quyền và kênh thông tin"]
    C --> D["Giảm tác động: tắt luồng, chuyển hướng, rollback nếu an toàn"]
    D --> E["Xác minh hệ thống và người dùng đã ổn định"]
    E --> F{"Tác động còn tiếp diễn?"}
    F -->|Có| C
    F -->|Không| G["Khắc phục bền vững, theo dõi việc còn lại"]
    G --> H["Hậu kiểm không đổ lỗi và cải tiến"]
    H --> I["Backlog, kiểm thử, quan sát và runbook được cập nhật"]
~~~

Sơ đồ không thay thế playbook bảo mật, tài chính, dữ liệu hoặc an toàn áp dụng trong tổ chức. Với sự cố nghiêm trọng, một số hành động cần bắt đầu **ngay khi có dấu hiệu đủ đáng tin**, không phải đợi hoàn thành mọi bước hành chính.

### 11.1. Phân biệt bốn mốc thời gian

| Mốc | Định nghĩa minh họa | Tại sao cần phân biệt? |
|---|---|---|
| **Detection time** | Khi sự cố bắt đầu đến khi được phát hiện, nếu xác định được. | Đánh giá khả năng quan sát; có sự cố người dùng báo trước dashboard. |
| **Response time** | Từ lúc báo/phát hiện theo định nghĩa đến lúc có người bắt đầu ứng phó. | Đánh giá đường tiếp nhận và lịch trực. |
| **Mitigation time** | Đến khi tác động đang diễn ra được giảm hoặc kiểm soát theo tiêu chí. | Ưu tiên bảo vệ người dùng trong khi chưa sửa tận gốc. |
| **Resolution / recovery time** | Đến khi dịch vụ được phục hồi hoặc nguyên nhân được xử lý theo định nghĩa đã thống nhất. | Cho biết năng lực khôi phục; cần nói rõ mốc “phục hồi”. |

Một sự cố có thể được giảm ảnh hưởng trong thời gian ngắn nhưng cần nhiều ngày đối soát dữ liệu, sửa nguyên nhân và phòng ngừa. Không nên dùng một thời gian duy nhất để che khuất các giai đoạn này.

### 11.2. Phối hợp trong sự cố

Tùy mức độ nghiêm trọng, có thể cần những trách nhiệm:

- **Người điều phối sự cố:** giữ bức tranh chung, quyết định ưu tiên/triệu tập theo quyền hạn.
- **Nhóm kỹ thuật xử lý:** xác minh, giảm tác động, sửa và kiểm tra lại.
- **Người phụ trách thông tin:** thông báo nhất quán cho khách hàng và stakeholder trong phạm vi cho phép.
- **Chuyên gia sản phẩm/nghiệp vụ:** đánh giá hậu quả dữ liệu, tiền, quyền truy cập hoặc hành trình người dùng.
- **Đội bảo mật/tuân thủ:** tham gia khi có dữ liệu nhạy cảm, nghĩa vụ pháp lý hoặc rủi ro chuyên biệt.

Đây là **vai trò phục vụ ứng phó**, không phải chức danh DevOps bắt buộc. Khi nhóm nhỏ, một người có thể đảm nhận nhiều trách nhiệm nhưng cần tránh một người vừa điều tra lỗi vừa phải trả lời hàng loạt yêu cầu cập nhật làm họ mất tập trung.

### 11.3. Khôi phục trước, tìm nguyên nhân đủ sâu sau

Khi lỗi đang gây thiệt hại, một giải pháp an toàn như vô hiệu hóa tính năng có thể có giá trị hơn việc chờ viết xong bản sửa kiến trúc hoàn hảo. Nhưng không nên tuyên bố “đã khắc phục hoàn toàn” nếu mới ngăn tác động tạm thời.

Phần sửa bền vững, kiểm tra hồi quy, đối soát dữ liệu bị ảnh hưởng và cải tiến giám sát cần được ghi thành công việc có ưu tiên rõ.

## 12. Postmortem: học từ sự cố mà không đổ lỗi

Sau một sự cố quan trọng, **postmortem / incident review** giúp nhóm hiểu sự kiện đã diễn ra, điều gì giúp hoặc cản trở ứng phó và cách giảm khả năng tái diễn.

**Blameless postmortem (hậu kiểm không đổ lỗi)** không có nghĩa mọi hành động đều được bỏ qua hoặc không có trách nhiệm. Nó có nghĩa tránh kết luận đơn giản rằng “người X sơ suất” trước khi hiểu vì sao hệ thống, công cụ, chính sách, giao diện hoặc áp lực thời gian khiến lỗi có thể xảy ra và tồn tại.

### 12.1. Cấu trúc hậu kiểm có ích

1. **Tác động:** người dùng, dữ liệu, thời gian và mức suy giảm dịch vụ.
2. **Dòng thời gian:** bằng chứng về thay đổi, phát hiện, điều phối, giảm thiệt hại và phục hồi.
3. **Điều kiện góp phần gây ra:** giả định sai, khoảng trống kiểm thử, phụ thuộc, cấu hình, tín hiệu bị thiếu, cơ chế ra quyết định.
4. **Điều đã làm tốt:** cảnh báo có ích, rollback an toàn, giao tiếp nhanh, người hỗ trợ chủ động.
5. **Điều cần cải thiện:** hành động cụ thể, ưu tiên, người phụ trách và cách kiểm tra hiệu quả.
6. **Theo dõi:** các việc phòng ngừa có thực sự được hoàn thành và giảm rủi ro hay không.

### 12.2. Phòng ngừa cần quay lại backlog

Ví dụ, sau sự cố đăng ký trùng, nhóm có thể bổ sung:

- Kiểm thử tích hợp cho hai yêu cầu đăng ký đồng thời.
- Cơ chế cập nhật số chỗ nguyên tử và xử lý yêu cầu gửi lặp.
- Metric phát hiện đăng ký vượt sức chứa và dashboard có người nhận cảnh báo.
- Runbook hỗ trợ đối soát và xử lý trạng thái không chắc chắn.
- Kiểm tra lại chính sách mở rộng phiên bản khi thay đổi cơ sở dữ liệu.

Một postmortem chỉ có bản ghi mà không có hành động được theo dõi là **phản hồi chưa được chuyển thành thích ứng**.

### 12.3. Không dùng báo cáo sự cố như bảng xếp hạng người trực

Nếu nhóm dùng số sự cố của mỗi kỹ sư để phạt, mọi người có động cơ không triển khai, giấu lỗi hoặc trì hoãn thông báo. Nên đánh giá **mức an toàn, chất lượng và khả năng học hỏi của hệ thống**, kết hợp trách nhiệm chuyên môn đúng bối cảnh.

## 13. DevSecOps: bảo mật và tuân thủ từ thiết kế tới vận hành

Bảo mật không phải nút bấm cuối pipeline. Những quyết định trong user story và thiết kế kiến trúc ảnh hưởng trực tiếp đến khả năng bảo vệ dữ liệu khi dịch vụ vận hành.

### 13.1. Phân lớp hoạt động theo vòng đời

| Giai đoạn | Câu hỏi bảo mật | Thực hành minh họa |
|---|---|---|
| **Khám phá/yêu cầu** | Dữ liệu nào nhạy cảm? Ai có quyền thực hiện hành động? | Làm rõ quyền, luật áp dụng, mục tiêu bảo vệ và trường hợp lạm dụng. |
| **Thiết kế** | Điểm tin cậy, phụ thuộc và giới hạn truy cập ở đâu? | Threat modeling ở mức phù hợp; thiết kế quyền tối thiểu. |
| **Phát triển** | Mã có đưa lỗ hổng và bí mật vào hệ thống không? | Rà soát thay đổi, kiểm tra đầu vào, quản lý secrets và dependency. |
| **CI/CD** | Bản build và quy trình phân phối có đáng tin? | Quyền pipeline tối thiểu, kiểm tra thành phần và nguồn gốc bản build khi cần. |
| **Triển khai** | Cấu hình production, quyền truy cập và phương án quay lại có phù hợp? | Quản lý cấu hình, tách quyền, theo dõi thay đổi. |
| **Vận hành** | Làm sao phát hiện sự lạm dụng, khắc phục lỗ hổng và xử lý sự cố? | Cảnh báo an toàn, cập nhật bản vá, quy trình ứng phó và lưu vết. |

Không nhất thiết mọi sản phẩm dùng cùng một công cụ quét hoặc cùng độ sâu threat modeling. Cần **dựa vào rủi ro và nghĩa vụ thực tế**, không coi việc hoàn tất một danh sách công cụ là bằng chứng mọi rủi ro đã biến mất.

### 13.2. Quản lý phụ thuộc và chuỗi cung ứng phần mềm

Ứng dụng dùng thư viện, image, công cụ build và dịch vụ bên ngoài. Những thành phần đó có thể có lỗ hổng hoặc thay đổi gây lỗi.

Nhóm nên có cách:

- Biết thành phần quan trọng nào đang được sử dụng.
- Theo dõi lỗ hổng và bản cập nhật có liên quan.
- Kiểm tra tính tương thích và chất lượng trước khi nâng cấp.
- Giới hạn quyền của pipeline và tài khoản kỹ thuật.
- Bảo vệ bí mật và khóa ký.
- Có đường phản ứng với rủi ro khẩn mà không bỏ kiểm chứng cần thiết.

**Cập nhật nhanh không phải luôn cập nhật an toàn**; cần xét cả độ tin cậy nguồn gốc, thay đổi hành vi và tác động vận hành.

### 13.3. Một lỗ hổng đang bị khai thác cần xử lý theo rủi ro

Nếu có dấu hiệu xâm nhập hoặc lộ dữ liệu, team phải dùng cơ chế ứng phó bảo mật thích hợp. Không nên chờ đến Sprint tiếp theo hay một kỳ duyệt backlog định kỳ chỉ vì yêu cầu chưa được viết thành user story.

Ngược lại, việc một thư viện đã cũ nhưng chưa rõ ảnh hưởng cần được đánh giá và ưu tiên theo bằng chứng, không tự động coi mọi cảnh báo máy quét là mức khẩn cấp như nhau.

## 14. Công việc vận hành, nợ kỹ thuật và nhịp phát triển bền vững

Nếu backlog chỉ chứa tính năng mới, những công việc như sửa lỗi, cập nhật hạ tầng, làm rõ cảnh báo, cải tiến khả năng khôi phục hoặc giảm nợ kỹ thuật thường bị xem là “ngoài kế hoạch”. Điều đó có thể tạo **nợ vận hành** khiến vòng phản hồi tương lai chậm và rủi ro tăng.

### 14.1. Không phải mọi công việc giá trị đều là user story chức năng

Một backlog thực tế có thể chứa:

| Loại hạng mục | Ví dụ | Giá trị/rủi ro được giải quyết |
|---|---|---|
| **Tính năng người dùng** | Xem và đăng ký buổi hướng dẫn. | Tăng khả năng tự phục vụ của học viên. |
| **Bug** | Khắc phục email xác nhận sai trạng thái. | Giảm nhầm lẫn và khiếu nại. |
| **Technical enabler** | Chuẩn hóa cơ chế xử lý yêu cầu lặp an toàn. | Giảm rủi ro nhiều chức năng tạo dữ liệu sai. |
| **Reliability improvement** | Cảnh báo sớm tỷ lệ đăng ký thất bại. | Giảm thời gian phát hiện sự cố. |
| **Security/compliance** | Sửa quyền đọc dữ liệu đăng ký. | Bảo vệ dữ liệu và đáp ứng nghĩa vụ bắt buộc. |
| **Spike/nghiên cứu có giới hạn** | Kiểm tra khả năng chịu tải khi mở đăng ký đồng thời. | Giảm bất định trước khi quyết định kiến trúc. |
| **Toil reduction** | Tự động hóa bước đối soát thường phải làm tay. | Giảm việc lặp, lỗi thao tác và thời gian vận hành. |

Đừng ép mọi hạng mục vào khuôn “Với vai trò là người dùng...” nếu đó là công việc kỹ thuật thuần túy. Hãy mô tả đúng **đầu ra, lý do, rủi ro và cách kiểm chứng** của từng loại.

### 14.2. Toil là gì?

Trong ngữ cảnh SRE, **toil** thường được hiểu là công việc vận hành mang tính **lặp lại, thủ công, có thể tự động hóa, ít tạo giá trị lâu dài và có xu hướng tăng theo quy mô dịch vụ**.

Ví dụ, mỗi lần triển khai kỹ sư phải vào năm máy và sửa cấu hình bằng tay; khi có thêm máy, số lần thao tác cũng tăng. Việc tự động hóa một quy trình đã được kiểm tra có thể giải phóng năng lực để cải thiện độ tin cậy.

Không phải mọi công việc vận hành thủ công đều là toil. Điều tra sự cố mới, hỗ trợ người dùng với vấn đề chưa từng gặp hoặc một quyết định phức tạp có thể đem lại học hỏi quan trọng.

### 14.3. On-call cần bền vững

Văn hóa trách nhiệm chung không nên được thực hiện bằng lịch trực quá tải, cảnh báo vô nghĩa hoặc kỳ vọng mọi nhân viên luôn sẵn sàng. Cần:

- Phân công và thay thế rõ ràng.
- Công cụ, quyền hạn và runbook đủ dùng.
- Cơ chế tăng cấp khi thiếu chuyên môn.
- Theo dõi gánh nặng trực, gián đoạn và thời gian phục hồi.
- Cải tiến cảnh báo để tránh đánh thức người trực không cần thiết.
- Bảo vệ thời gian nghỉ và tuân thủ quy định liên quan.

Một đội “triển khai nhanh” nhưng liên tục kiệt sức và sinh lỗi mới **không có khả năng phát triển bền vững** theo tinh thần Agile.

## 15. Đo lường: kết hợp DORA, dòng công việc, độ tin cậy và outcome

Nhiều nhóm dùng **DORA metrics** để quan sát khả năng phân phối và độ ổn định khi thay đổi phần mềm. Những chỉ số kinh điển thường được nhắc tới gồm:

1. **Deployment frequency:** tần suất đưa thay đổi vào môi trường production theo định nghĩa.
2. **Lead time for changes:** khoảng thời gian từ khi mã được commit đến khi thay đổi chạy trên production theo cách đo phù hợp.
3. **Change failure rate:** tỷ lệ lần triển khai/thay đổi gây ra lỗi cần khắc phục theo định nghĩa.
4. **Time to restore service / failed deployment recovery time:** thời gian phục hồi sau những sự cố hoặc thất bại liên quan đến thay đổi; tên gọi và phạm vi phép đo có thể khác giữa các phiên bản khung đo.

Các khung DORA đã được phát triển và mở rộng qua thời gian; khi áp dụng, team nên **nói rõ phiên bản, định nghĩa, đơn vị và nguồn dữ liệu** thay vì xem bốn cái tên là tiêu chuẩn số học cố định cho mọi tổ chức.

### 15.1. Hiểu đúng mục đích từng chỉ số

| Tín hiệu | Câu hỏi cải tiến | Bẫy diễn giải |
|---|---|---|
| **Deployment frequency** | Có thể bàn giao những thay đổi nhỏ thường xuyên không? | Deploy nhiều nhưng không có giá trị hoặc dùng kỹ thuật tách phiên bản để làm đẹp số liệu. |
| **Lead time for changes** | Từ thay đổi mã đến production mất thời gian ở đâu? | Không phản ánh toàn bộ thời gian từ ý tưởng, nghiên cứu và chờ quyết định nghiệp vụ. |
| **Change failure rate** | Thay đổi có làm dịch vụ suy giảm hoặc cần khắc phục không? | Giấu sự cố hoặc không ghi thay đổi thất bại để tỷ lệ đẹp hơn. |
| **Recovery time** | Có thể giảm tác động/khôi phục dịch vụ nhanh không? | Đổi mốc bắt đầu/kết thúc hoặc chỉ đo sự cố dễ sửa. |
| **WIP, cycle time, work item age** | Hạng mục bị chờ và dở dang nhiều ở đâu? | Chỉ đếm ticket mà bỏ qua kích thước và chất lượng. |
| **SLI/SLO** | Người dùng nhận mức dịch vụ phù hợp không? | Chọn SLI chỉ đo máy chủ sống thay vì tác vụ quan trọng. |
| **Escaped defects / incidents** | Những lỗi nào lọt qua kiểm chứng trước release? | Phạt người báo lỗi khiến lỗi bị giấu. |
| **Outcome** | Sản phẩm có giải quyết đúng vấn đề? | Nhầm correlation với causation hoặc bỏ qua tác động ngoài phần mềm. |

### 15.2. DORA khác thời gian từ yêu cầu đến giá trị

Lead time for changes theo cách đo kỹ thuật thường **bắt đầu từ commit**, trong khi người dùng có thể đã chờ nhiều tuần ở giai đoạn nghiên cứu, quyết định hoặc sắp backlog. Để hiểu đầy đủ hành trình giá trị, nhóm có thể đo thêm **lead time từ lúc yêu cầu được tiếp nhận đến khi có phần sản phẩm có thể sử dụng**, với định nghĩa nhất quán.

Tương tự, việc rút thời gian triển khai từ hai ngày xuống hai giờ có thể rất tốt, nhưng nếu nhóm phải chờ ba tuần để Product Owner xác nhận một quy tắc thì nút thắt chính chưa được giải quyết.

### 15.3. Ví dụ dữ liệu giả định

| Chỉ số minh họa | Giai đoạn A | Giai đoạn B | Giai đoạn C |
|---|---:|---:|---:|
| Thời gian từ commit đến production trung vị (giờ) | 30 | 14 | 6 |
| Lần triển khai production trong giai đoạn | 8 | 13 | 18 |
| Lần triển khai gây lỗi cần khắc phục | 2 | 2 | 1 |
| Thời gian khôi phục sau thay đổi lỗi trung vị (phút) | 90 | 55 | 25 |
| Cycle time hạng mục Standard trung vị (ngày) | 12 | 10 | 8 |

**Đây là số liệu giả định để học cách đọc chỉ số**, không phải bằng chứng nghiên cứu. Một xu hướng có vẻ tích cực không tự chứng minh nguyên nhân là CI/CD: quy mô thay đổi, mức tải, nhân sự, cách ghi nhận lỗi và sản phẩm có thể đã khác.

Nhóm nên xem dữ liệu qua đủ giai đoạn, kết hợp quan sát định tính và outcome người dùng. Không nên đặt mục tiêu “tăng deployment frequency” nếu sản phẩm không cần thay đổi với nhịp đó, hoặc so sánh thứ hạng các đội có bối cảnh và mức độ hệ trọng khác nhau.

### 15.4. Đo để cải tiến, không để đổ lỗi

Nếu một đội bị yêu cầu hạ change failure rate bằng mọi giá, họ có thể giảm phát hành, gộp thay đổi lớn hoặc không ghi nhận sự cố. Nếu chỉ thưởng số lần triển khai, họ có thể chia một thay đổi vô nghĩa thành nhiều lần deploy.

Chỉ số nên được dùng như **tín hiệu để đặt câu hỏi về hệ thống làm việc**, không phải thước đo duy nhất về giá trị hay năng lực của cá nhân.

## 16. Scrum, Kanban và XP hỗ trợ trách nhiệm vận hành ra sao?

### 16.1. Scrum: kiểm tra–thích ứng trên cả giá trị và chất lượng

Trong Scrum, **Product Backlog** có thể chứa cả tính năng, lỗi, cải tiến độ tin cậy và yêu cầu bảo mật. Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả backlog; Developers chịu trách nhiệm tạo Increment dùng được theo DoD; Scrum Master hỗ trợ hiệu quả Scrum Team và việc tháo trở ngại.

Các sự kiện tạo nhịp:

- **Sprint Planning:** xét năng lực thực, rủi ro vận hành, phụ thuộc và mục tiêu giá trị.
- **Daily Scrum:** Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch, kể cả khi có blocker kỹ thuật.
- **Sprint Review:** kiểm tra Increment, phản hồi người dùng, thay đổi bối cảnh và bằng chứng production liên quan.
- **Sprint Retrospective:** tìm cải tiến trong tích hợp, kiểm thử, phối hợp release và ứng phó sự cố.

Sự cố production nghiêm trọng **không cần chờ Daily Scrum hoặc Sprint Review** mới được xử lý. Khi điều kiện thay đổi, Developers và Product Owner làm rõ/thương lượng phạm vi để bảo vệ Sprint Goal và chất lượng; Scrum không yêu cầu giảm DoD để giữ tất cả các ticket đã chọn.

### 16.2. Kanban: minh bạch dòng công việc và trách nhiệm dịch vụ

Kanban giúp nhìn thấy công việc tính năng, sửa lỗi và vận hành đi qua hệ thống, với các chính sách rõ về:

- Lúc nào nhận hoặc kéo việc mới.
- Hạng mục nào đang bị chặn, bị chặn bởi điều gì.
- WIP limit và cách gỡ tắc nghẽn.
- Lớp dịch vụ cho việc khẩn (**Expedite**) hoặc việc có hạn thực (**Fixed Date**) khi phù hợp.
- Định nghĩa hoàn thành và kỳ vọng thời gian dịch vụ (**SLE**) theo bối cảnh.

Nếu mọi sự cố đều được gắn nhãn “khẩn”, công việc thường và cải tiến phòng ngừa sẽ bị đói năng lực. Cần **chính sách phân loại có bằng chứng**, cơ chế ứng phó riêng cho sự cố nghiêm trọng và cách xem xét chi phí chen ngang.

### 16.3. XP: phản hồi kỹ thuật đủ nhanh để triển khai an toàn

XP đóng góp các thực hành như **TDD, CI, refactoring, pair programming và small releases**. Chúng làm cho codebase dễ thay đổi và giúp phát hiện lỗi trước khi tác động tới người dùng.

Ví dụ, TDD có thể kiểm tra quy tắc đăng ký một chỗ còn trống; kiểm thử tích hợp đồng thời cần xác minh rằng hai request không tạo hai xác nhận cho cùng chỗ. **Unit test xanh không chứng minh hệ thống thực tế xử lý cạnh tranh an toàn**.

### 16.4. Cần kết hợp có mục đích

Một nhóm có thể dùng Scrum để định hướng mục tiêu, Kanban để quản lý flow, XP để kiểm chứng mã và DevOps/SRE để đưa phần mềm vào sử dụng đáng tin cậy. Không nhất thiết áp tất cả nghi thức, vai trò hoặc công cụ của từng cách tiếp cận.

**Chọn thực hành theo nút thắt:** nếu thường hiểu sai yêu cầu, ưu tiên trao đổi nghiệp vụ; nếu lỗi tích hợp muộn, cải thiện CI; nếu sự cố chỉ được phát hiện bởi người dùng, cải thiện observability; nếu lỗi đã được biết nhưng không có người điều phối, làm rõ trách nhiệm vận hành.

## 17. Case study: đăng ký buổi hướng dẫn bị lỗi khi mở rộng sử dụng

**Toàn bộ tình huống, mốc và số liệu sau đây đều giả định** để minh họa cách kết hợp Agile, DevOps và trách nhiệm vận hành. Đây không phải quy trình production bắt buộc cho một hệ thống cụ thể.

### 17.1. Bối cảnh và mục tiêu

Một Scrum Team phát triển nền tảng học lập trình. Product Goal là **giúp học viên tìm và đăng ký buổi hướng dẫn một cách đáng tin, không cần xử lý thủ công**.

Nhóm đã hoàn thành các lát:

1. Xem danh sách buổi còn chỗ.
2. Chọn một buổi và xác nhận đăng ký.
3. Xem trạng thái đăng ký.
4. Nhận email xác nhận khi đăng ký được ghi nhận.

Trong một buổi mở đăng ký số lượng lớn, nhiều học viên nhấn “Đăng ký” gần như đồng thời. Hệ thống bắt đầu trả lỗi; một số người thấy thông báo thành công dù bản ghi chưa được xác nhận. Dashboard chỉ có CPU và số request tổng, không có tín hiệu trực tiếp về **đăng ký được lưu đúng**.

### 17.2. Vấn đề bắt nguồn từ nhiều lớp

| Lớp | Điều quan sát | Khoảng trống cần điều tra |
|---|---|---|
| **Nghiệp vụ** | Khái niệm “đăng ký thành công” chưa được định nghĩa rõ khi xử lý đang chờ. | Tiêu chí chấp nhận và quy tắc trạng thái. |
| **Ứng dụng** | Retry từ giao diện có thể gửi cùng yêu cầu nhiều lần. | Idempotency và cách phản hồi trạng thái. |
| **Dữ liệu** | Hai yêu cầu cùng đọc số chỗ còn lại rồi ghi. | Cơ chế cập nhật nguyên tử/nhất quán. |
| **Kiểm thử** | Unit test qua, nhưng chưa thử kịch bản cạnh tranh có tải đại diện. | Kiểm thử tích hợp, đồng thời và trường hợp lỗi. |
| **CI/CD** | Pipeline chỉ kiểm tra luồng thành công ở tải thấp. | Phạm vi kiểm chứng trước triển khai. |
| **Quan sát** | Không có chỉ số “đăng ký hợp lệ được xác nhận đúng”. | SLI, metric nghiệp vụ và cảnh báo. |
| **Vận hành** | Đội trực chưa có cách tắt riêng luồng đăng ký. | Quyền giảm thiểu và phương án an toàn. |

Sự cố không nên được giản lược thành “một lập trình viên viết sai dòng if”. Nhiều điều kiện trong yêu cầu, kiểm chứng, dữ liệu và vận hành có thể cùng góp phần tạo ra hậu quả.

### 17.3. Ứng phó trước mắt

Khi phát hiện tín hiệu nghiêm trọng, người có thẩm quyền kích hoạt ứng phó theo quy trình:

1. **Xác minh:** số lượng phiên bị ảnh hưởng, tình trạng dữ liệu, phạm vi và mức độ thiệt hại; phân biệt thông tin đã biết với giả thuyết.
2. **Giảm tác động:** nếu cần, tạm ngừng tạo đăng ký mới hoặc chuyển sang chế độ an toàn theo quyền hạn, không tiếp tục phát xác nhận không đáng tin.
3. **Phối hợp:** mời kỹ sư ứng dụng, dữ liệu, người hiểu nghiệp vụ, người phụ trách dịch vụ và hỗ trợ khách hàng khi liên quan.
4. **Thông tin:** có đầu mối cập nhật nhất quán; không để người đang sửa phải trả lời nhiều kênh cùng lúc.
5. **Xác minh hồi phục:** kiểm tra chức năng thật, tính đúng trạng thái dữ liệu và ảnh hưởng còn tồn tại trước khi mở lại.

Việc tắt một luồng đăng ký có thể làm giảm khả năng phục vụ tạm thời, nhưng nếu luồng đang tạo dữ liệu sai, **bảo vệ tính toàn vẹn và người dùng có thể quan trọng hơn giữ giao diện tiếp tục nhận yêu cầu**.

### 17.4. Cải tiến kỹ thuật có kiểm chứng

Giả sử điều tra cho thấy ứng dụng kiểm tra số chỗ bằng một phép đọc, sau đó ghi đăng ký ở một thao tác tách biệt. Hai yêu cầu có thể cùng thấy còn một chỗ và đều ghi thành công.

Nhóm cần thiết kế cơ chế bảo toàn bất biến:

> **Số đăng ký được xác nhận không vượt sức chứa và một yêu cầu lặp không được tạo nhiều đăng ký có hiệu lực ngoài quy tắc.**

Tùy kiến trúc, giải pháp có thể liên quan đến giao dịch dữ liệu nguyên tử, khóa/điều kiện cập nhật, ràng buộc dữ liệu, idempotency key, cơ chế sự kiện và đối soát trạng thái. Không có một lệnh SQL hoặc đoạn mã mẫu nào tự động giải quyết an toàn cho tất cả cách triển khai.

Bộ kiểm chứng cần bao gồm:

- Đăng ký thành công khi còn chỗ.
- Từ chối hợp lệ khi hết chỗ.
- Hai hoặc nhiều yêu cầu cạnh tranh.
- Gửi lặp cùng yêu cầu, timeout và retry.
- Ghi dữ liệu thất bại hoặc trạng thái kết quả chưa rõ.
- Không gửi email thành công nếu chưa có bằng chứng đăng ký được xác nhận.
- Kiểm tra quyền đọc/sửa đăng ký của người dùng khác.

**Bài kiểm tra đơn vị của hàm “còn chỗ” vẫn hữu ích, nhưng phải được bổ sung bằng kiểm tra tích hợp và trạng thái thực phù hợp**.

### 17.5. Triển khai lại an toàn

Sau khi sửa và đạt kiểm chứng cần thiết, nhóm lập kế hoạch mở lại có kiểm soát:

| Bước | Điều cần làm | Tín hiệu để quyết định tiếp |
|---|---|---|
| Bản build | Xác nhận phiên bản, kết quả CI và các kiểm tra bắt buộc. | Có bằng chứng chất lượng, không có lỗi chặn sử dụng. |
| Môi trường thử | Kiểm tra tương thích dữ liệu và kịch bản cạnh tranh. | Luồng thành công/lỗi đúng với quy tắc. |
| Mở thử có kiểm soát | Mở cho phạm vi được phép, có người trực và phương án dừng. | SLI đăng ký hợp lệ, lỗi ghi, độ trễ và dữ liệu nhất quán. |
| Mở rộng | Tăng phạm vi nếu tín hiệu đủ tin và rủi ro được chấp nhận. | Không có dấu hiệu sai trạng thái hoặc suy giảm không chấp nhận được. |
| Theo dõi sau mở | Quan sát và tiếp nhận phản hồi từ hỗ trợ/người dùng. | Duy trì chất lượng và bổ sung thông tin cho backlog. |

**Không dùng rollout nhỏ để thử những hành vi có thể gây hậu quả an toàn không chấp nhận được.** Phạm vi thí điểm phải đạt tiêu chuẩn và điều kiện rủi ro tương ứng.

### 17.6. Postmortem và điều chỉnh Product Backlog

Sau sự cố, Scrum Team và các bên liên quan xác định một số hành động:

| Hạng mục sau sự cố | Loại công việc | Cách kiểm chứng |
|---|---|---|
| Sửa cơ chế ghi để không vượt sức chứa. | Bug / reliability. | Kiểm thử tích hợp đồng thời đạt, giám sát không thấy sai lệch trong phạm vi đủ tin. |
| Chuẩn hóa phản hồi khi kết quả đăng ký chưa rõ. | User story / quality. | Người dùng không được thông báo thành công sai và biết bước tiếp an toàn. |
| Bổ sung metric đăng ký hợp lệ thành công. | Observability enabler. | Dashboard/alert kiểm tra bằng tình huống lỗi kiểm soát được. |
| Cải thiện pipeline kiểm tra kịch bản cạnh tranh quan trọng. | Engineering practice. | Kiểm thử chạy ổn định và phát hiện được lỗi mô phỏng phù hợp. |
| Viết runbook dừng/mở lại luồng đăng ký. | Operational readiness. | Người được phân công có thể làm theo trong điều kiện thử an toàn. |
| Kiểm tra lại thiết kế ưu tiên và lịch trực khi mở đăng ký lớn. | Process improvement. | Trách nhiệm, tín hiệu và khả năng ứng phó rõ. |

Product Owner xem tác động tới giá trị và ưu tiên; Developers góp hiểu biết kỹ thuật; Scrum Master hỗ trợ nhóm cải tiến; chuyên gia vận hành/bảo mật tham gia theo nghĩa vụ. **Đây là vòng phản hồi DevOps quay lại Agile**: vấn đề được quan sát trong production trở thành quyết định sản phẩm, chất lượng và cách làm mới.

### 17.7. Outcome cần quan sát sau đó

Nhóm có thể theo dõi:

- Người học có đăng ký được buổi phù hợp không?
- Có bao nhiêu yêu cầu hợp lệ được xử lý đúng trong ngưỡng thời gian?
- Có phát sinh trạng thái trùng, sai sức chứa hoặc thông báo sai không?
- Người trực có phát hiện và giảm sự cố nhanh hơn không?
- Việc đầu tư vào kiểm chứng/quan sát có giảm lỗi lặp lại và thời gian chờ không?

Không thể kết luận thành công chỉ vì pipeline xanh hay một lần mở thử không có lỗi. Cần xem **phạm vi quan sát, lượng dữ liệu, mức tải và rủi ro chưa được kiểm chứng**.

## 18. Những ngộ nhận và phản mẫu thường gặp

| Phản mẫu | Vì sao có hại? | Hướng thực hành tốt hơn |
|---|---|---|
| **“DevOps là tên đội sửa lỗi production.”** | Phát triển và vận hành vẫn tách trách nhiệm. | Kết nối thiết kế, chất lượng, phát hành, quan sát và ứng phó. |
| **“Agile xong mới tới DevOps.”** | Phản hồi vận hành đến muộn, kiến trúc thiếu khả năng phục hồi. | Xem vận hành và an toàn ngay khi làm rõ yêu cầu và DoD. |
| **“You build it, you run it” nghĩa là tất cả dev phải trực 24/7.** | Thiếu an toàn, tăng quá tải và quyền truy cập không phù hợp. | Thiết kế trách nhiệm, lịch trực, quyền và phối hợp phù hợp tổ chức. |
| **“CI xanh nghĩa là production sẽ không lỗi.”** | Giấu lỗ hổng kiểm tra tích hợp, tải và dữ liệu. | Kiểm tra theo rủi ro, quan sát sau triển khai. |
| **“CD nghĩa là tự động đẩy tất cả lên production.”** | Nhầm delivery với deployment và bỏ qua quyền quyết định. | Phân biệt CI, Continuous Delivery, Continuous Deployment và release. |
| **“Deploy nhiều lần luôn tốt hơn.”** | Tối ưu chỉ số thay vì giá trị và độ tin cậy. | Đo cả lead time, chất lượng thay đổi, recovery và outcome. |
| **“Canary làm mọi thay đổi trở nên an toàn.”** | Người dùng thí điểm vẫn có thể chịu thiệt hại. | Kiểm soát rủi ro trước, có tiêu chí dừng và quan sát phù hợp. |
| **“Rollback luôn khôi phục toàn bộ trạng thái.”** | Dữ liệu, sự kiện và schema có thể đã thay đổi không đảo ngược. | Lập kế hoạch tương thích và phục hồi dữ liệu riêng. |
| **“Chỉ cần monitoring CPU là biết dịch vụ tốt.”** | Máy chủ sống nhưng người dùng không hoàn thành tác vụ. | Chọn SLI theo hành trình người dùng, bổ sung log/trace an toàn. |
| **“Càng nhiều alert càng an toàn.”** | Nhiễu cảnh báo và bỏ lỡ tín hiệu quan trọng. | Cảnh báo có chủ sở hữu, hành động và tiêu chí giảm tác động. |
| **“Error budget còn nên có thể bỏ qua lỗi bảo mật.”** | Hiểu sai công cụ cân bằng độ tin cậy. | Tuân thủ mọi kiểm soát an toàn và nghĩa vụ bắt buộc. |
| **“Bảo mật là việc sau khi build.”** | Phải làm lại thiết kế hoặc phát hành muộn. | Tích hợp security vào yêu cầu, thiết kế, pipeline và vận hành. |
| **“Sự cố là do người viết dòng mã cuối.”** | Không học từ điều kiện hệ thống và có xu hướng giấu lỗi. | Hậu kiểm theo bằng chứng, trách nhiệm đúng và cải tiến phòng ngừa. |
| **“Fix tạm xong là đóng hết việc.”** | Nguyên nhân, dữ liệu và phòng ngừa bị bỏ quên. | Tách và ưu tiên công việc còn lại trong backlog. |
| **“SLO càng gần 100% càng tốt.”** | Chi phí có thể vượt lợi ích, cản trở thay đổi cần thiết. | Chọn mục tiêu theo nhu cầu, rủi ro và khả năng đo. |
| **“Nợ kỹ thuật và observability không tạo giá trị.”** | Giảm độ tin cậy và khiến các Sprint sau chậm hơn. | Gắn công việc kỹ thuật với rủi ro và năng lực tạo giá trị. |
| **“DORA là bảng xếp hạng cá nhân.”** | Kích thích thao túng số liệu hoặc tránh báo sự cố. | Dùng như tín hiệu cải tiến hệ thống theo bối cảnh. |
| **“Trực liên tục là minh chứng tinh thần trách nhiệm.”** | Tăng mệt mỏi, lỗi và suy giảm sức khỏe. | Thiết kế vận hành bền vững và giảm toil/cảnh báo nhiễu. |

## 19. Lộ trình bắt đầu áp dụng tư duy Agile–DevOps

Một nhóm chưa có nhiều tự động hóa hoặc khả năng quan sát không cần xây toàn bộ nền tảng trong một lần. Nên bắt đầu từ **một hành trình người dùng quan trọng**, tìm nút thắt và cải tiến theo từng vòng có thể kiểm tra.

### Bước 1 — Chọn một outcome và một dịch vụ cần cải thiện

Ví dụ: “Học viên có thể đăng ký buổi học một cách đáng tin”. Làm rõ điều người dùng cần đạt, các ràng buộc chất lượng và rủi ro lớn nhất.

### Bước 2 — Vẽ dòng công việc từ yêu cầu đến production

Xác định hạng mục phải chờ ở đâu: làm rõ nghiệp vụ, kiểm thử, phê duyệt, môi trường, triển khai hoặc điều tra sự cố. Ghi mốc bắt đầu/kết thúc đủ rõ cho các chỉ số cần dùng.

### Bước 3 — Kết nối trách nhiệm phát triển và vận hành

Thống nhất người sở hữu dịch vụ, quyền deploy/rollback, đường gọi chuyên gia, tiêu chí hoàn thành và đầu mối thông báo. Nếu có đội nền tảng, bảo mật hoặc SRE, làm rõ đầu ra và phụ thuộc của mỗi bên.

### Bước 4 — Cải thiện một vòng kiểm chứng

Ví dụ, bổ sung kiểm thử tích hợp cho hành vi gửi lặp, rút thời gian chờ CI hoặc tạo môi trường thử đáng tin. Đừng chọn một công cụ chỉ vì đang phổ biến; chọn theo **lỗi hoặc thời gian chờ quan sát được**.

### Bước 5 — Tạo khả năng triển khai và phục hồi an toàn

Chuẩn hóa bản build, cấu hình, kiểm tra trước triển khai và kế hoạch quay lại trạng thái an toàn theo rủi ro. Nếu có database migration, kiểm tra tương thích giữa phiên bản cũ/mới.

### Bước 6 — Đo một hành trình người dùng trong production

Chọn SLI phản ánh giá trị hoặc độ tin cậy, như tỷ lệ đăng ký hợp lệ được xác nhận đúng; thiết lập tín hiệu và quyền truy cập phù hợp. Định nghĩa cảnh báo dẫn tới hành động rõ.

### Bước 7 — Tập một tình huống ứng phó

Kiểm tra ai nhận cảnh báo, ai có quyền tắt luồng nguy hiểm, cách liên hệ chuyên gia và làm sao xác nhận phục hồi. Một bài diễn tập có kiểm soát có thể bộc lộ thiếu sót trước khi sự cố thật xảy ra.

### Bước 8 — Xem lại dữ liệu và điều chỉnh backlog

So sánh cycle time, thời gian phản hồi pipeline, lỗi sau phát hành, mức sử dụng, thời gian phục hồi và tải trực. Chọn cải tiến tiếp theo dựa trên rủi ro/giá trị. Đừng coi việc đã cài một công cụ là kết thúc hành trình.

## 20. Bài tập thực hành: thiết kế trách nhiệm vận hành cho một story

Giả sử Scrum Team chuẩn bị triển khai:

> Với vai trò là học viên, tôi muốn hủy đăng ký một buổi học để có thể thay đổi lịch và trả chỗ cho người khác.

Quy tắc nghiệp vụ:

- Chỉ chủ sở hữu đăng ký hoặc người có quyền hợp lệ được hủy.
- Nếu hủy thành công, chỗ được trả lại **đúng một lần**.
- Nếu request bị gửi lặp, không được tăng số chỗ nhiều lần.
- Khi cập nhật thất bại, không thông báo rằng đã hủy thành công.
- Có thể có danh sách chờ cần được cập nhật theo quy tắc.

### Bài tập 1 — Thiết kế DoD có góc nhìn vận hành

**Câu hỏi:** Ngoài tiêu chí chấp nhận, cần kiểm tra điều gì để hạng mục dùng được?

**Gợi ý:** kiểm thử quyền, tích hợp cập nhật trạng thái, yêu cầu lặp và cạnh tranh; trường hợp lỗi và khôi phục; metric và log không lộ dữ liệu; những điều kiện triển khai/giám sát bắt buộc theo sản phẩm. Không cần chép mọi mục vào DoD nếu không áp dụng, nhưng không được bỏ tiêu chuẩn thiết yếu.

### Bài tập 2 — Thiết kế triển khai an toàn

**Câu hỏi:** Nếu ứng dụng cũ chưa hiểu trạng thái mới “CANCEL_PENDING”, cần làm gì?

**Gợi ý:** xem tương thích API, schema và dữ liệu khi hai phiên bản cùng chạy; chuẩn bị migration theo bước nếu cần; xác định tiêu chí bật/mở, cách kiểm tra và phương án phục hồi. Rollback mã không tự đảo trạng thái đã ghi.

### Bài tập 3 — Chọn SLI phản ánh nhu cầu người dùng

**Câu hỏi:** Đo CPU trung bình có đủ để biết việc hủy đăng ký hoạt động đúng không?

**Gợi ý:** chưa đủ. Có thể đo tỷ lệ yêu cầu hủy hợp lệ được ghi nhận đúng và trả kết quả trong ngưỡng, số lỗi cập nhật chỗ, sự kiện trùng và độ trễ; cần định nghĩa rõ yêu cầu hợp lệ và những trường hợp từ chối đúng quy tắc.

### Bài tập 4 — Xử lý sự cố khi chỗ được trả hai lần

**Câu hỏi:** Sau khi phát hiện mất nhất quán dữ liệu, đội làm gì trước?

**Gợi ý:** kích hoạt ứng phó phù hợp, xác định phạm vi, ngăn việc ghi sai tiếp tục theo quyền hạn, thông báo rõ và kiểm tra dữ liệu trước khi mở lại. Sau đó mới làm sửa bền vững, đối soát và hậu kiểm.

### Bài tập 5 — Đưa bài học về backlog

**Câu hỏi:** Có nên chỉ tạo một bug “sửa hủy trùng” rồi tiếp tục toàn bộ roadmap cũ?

**Gợi ý:** bug là cần thiết nhưng chưa đủ nếu còn khoảng trống về kiểm thử đồng thời, quan sát, playbook hoặc khả năng tích hợp. Product Owner và team cân nhắc các hạng mục phòng ngừa theo rủi ro, giá trị và năng lực; tránh biến hậu kiểm thành tài liệu không có hành động.

## 21. Checklist áp dụng trong nhóm

### Trước khi bắt đầu và trong lúc phát triển

- [ ] User story/hạng mục nêu rõ **giá trị người dùng**, ràng buộc nghiệp vụ và giả thuyết chưa kiểm chứng chưa?
- [ ] Những yêu cầu về dữ liệu, phân quyền, an toàn và độ tin cậy đã được bàn sớm chưa?
- [ ] Các thành viên biết hệ thống sẽ được triển khai, vận hành và giám sát bởi ai không?
- [ ] Có cách liên hệ người hiểu nghiệp vụ, chuyên gia nền tảng và bảo mật khi cần không?
- [ ] CI cung cấp phản hồi nhanh **và đáng tin** cho thay đổi quan trọng chưa?
- [ ] Kiểm tra tích hợp, trạng thái đồng thời, timeout, retry và hành vi lỗi có phù hợp rủi ro không?
- [ ] Definition of Done có bao gồm khả năng vận hành thiết yếu theo sản phẩm và tiêu chuẩn tổ chức không?
- [ ] Bí mật và quyền truy cập kỹ thuật có được bảo vệ đúng không?

### Trước khi phát hành

- [ ] Đã phân biệt **Done, deploy, release và outcome** chưa?
- [ ] Có bằng chứng tương thích API, schema và phiên bản cũ khi cần không?
- [ ] Có phương án triển khai, dừng mở rộng hoặc quay về trạng thái an toàn phù hợp không?
- [ ] Những chỉ số và cảnh báo quan trọng có người phụ trách, có hành động rõ không?
- [ ] Có xác nhận được ai chịu trách nhiệm ứng phó và thông báo khi sự cố xảy ra không?
- [ ] Các điều kiện bảo mật, quyền riêng tư, pháp lý và vận hành bắt buộc đã được đáp ứng chưa?

### Sau khi đưa vào sử dụng

- [ ] Có quan sát được **hành trình người dùng** thay vì chỉ hạ tầng không?
- [ ] Dữ liệu log, metric, trace có đủ hữu ích mà không tiết lộ thông tin nhạy cảm không?
- [ ] SLI/SLO nếu có được định nghĩa và đọc cùng bối cảnh đúng không?
- [ ] Khi lỗi xảy ra, nhóm có thể phát hiện, giảm tác động và khôi phục phù hợp không?
- [ ] Postmortem có tạo hành động phòng ngừa thực và được kiểm tra lại không?
- [ ] Công việc vận hành, toil, nợ kỹ thuật và độ tin cậy có được ưu tiên trong backlog không?
- [ ] Flow metrics, chỉ số triển khai và outcome có được dùng để cải tiến chứ không xếp hạng cá nhân không?
- [ ] Lịch trực, khối lượng gián đoạn và nhịp làm việc có bền vững không?

Checklist nhằm hỗ trợ trao đổi và quyết định, **không phải cổng phê duyệt máy móc**. Với hạng mục rủi ro cao, có thể cần chứng cứ sâu hơn; với thay đổi rất nhỏ, nên tối giản những bước không mang lại tín hiệu hữu ích nhưng vẫn giữ tiêu chuẩn bắt buộc.

## 22. Kết luận

**Agile** giúp nhóm học nhanh về giá trị cần tạo và thích ứng với thay đổi; **DevOps** giúp giảm khoảng cách giữa phát triển, triển khai và vận hành để những phần giá trị được đưa vào sử dụng **thường xuyên, an toàn và đáng tin**. **DevSecOps** mở rộng góc nhìn trách nhiệm bảo mật xuyên suốt; **SRE** cung cấp những thực hành và thước đo cụ thể để quản lý độ tin cậy.

Trách nhiệm vận hành không bắt đầu sau ngày release. Nó hiện diện từ lúc làm rõ yêu cầu, chọn kiến trúc, thiết kế kiểm thử, định nghĩa chất lượng, chuẩn bị pipeline và quan sát hành vi hệ thống. Các tín hiệu từ production, sự cố và người dùng cần quay lại **Product Backlog, Definition of Done và cách nhóm phối hợp**, để mỗi vòng thay đổi an toàn hơn.

Không nên đánh giá thành công bằng số ticket đã đóng, số lần deploy, dashboard xanh hay việc đội vận hành “chịu trận” giỏi đến đâu. Kết quả đáng hướng tới là **người dùng nhận được giá trị thực, dịch vụ có độ tin cậy phù hợp, rủi ro được minh bạch và đội ngũ duy trì khả năng thay đổi một cách bền vững**.
