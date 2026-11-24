# Điều phối chuyên môn dùng chung và nhóm hỗ trợ nền tảng

Một nền tảng học trực tuyến có bốn nhóm phát triển: **Trải nghiệm học viên**, **Nội dung và khóa học**, **Đánh giá năng lực** và **Thanh toán – quyền truy cập**. Cả bốn đều cần cùng một số năng lực: chuyên gia bảo mật xem xét phân quyền, chuyên gia dữ liệu hỗ trợ migration, nhóm vận hành quản lý triển khai, và nhóm nền tảng cung cấp pipeline cùng hạ tầng thử nghiệm. Khi tính năng **“Học tiếp”** sắp hoàn tất, nhóm học viên phát hiện cần thay hợp đồng API tiến độ. Họ gửi yêu cầu tới một chuyên gia chung, nhưng chuyên gia ấy đang hỗ trợ hai nhóm khác. Công việc dừng lại, rồi bị đẩy sang cuối Sprint.

Một phản ứng quen thuộc là thêm họp điều phối, yêu cầu chuyên gia “ưu tiên hơn”, hoặc lập danh sách phê duyệt mới. Những cách này có thể làm **khối lượng phối hợp tăng** mà không giải quyết sự mất cân đối giữa nhu cầu, năng lực và quyền quyết định. Phương án tốt hơn bắt đầu từ việc làm rõ **ai đang cần loại hỗ trợ nào**, **phụ thuộc nào bắt buộc phải có chuyên gia**, **việc nào có thể tự phục vụ**, **cách chọn ưu tiên và giới hạn công việc đang dở**, và **bằng chứng nào cho thấy các nhóm đang giao giá trị nhanh, an toàn hơn**.

**Điều phối chuyên môn dùng chung** là thiết kế cách các nhóm tiếp cận kiến thức và quyết định khan hiếm mà không biến chuyên gia thành nút thắt thường trực. **Nhóm hỗ trợ nền tảng (platform team)** tạo và vận hành những khả năng dùng chung dưới dạng **sản phẩm/dịch vụ nội bộ**, để các nhóm làm sản phẩm tự thực hiện công việc thường lệ với ít phụ thuộc trực tiếp hơn. Hai khái niệm có liên hệ nhưng **không đồng nhất**: một chuyên gia bảo mật tư vấn theo phiên không nhất thiết là một platform team; một platform team trưởng thành không nên chỉ là “đội nhận mọi ticket kỹ thuật”.

Bài thuộc chương **Phối hợp nhiều nhóm** trong module **AGILE_DEVELOPMENT**. Nội dung liên hệ các giá trị Agile về **phản hồi sớm, giao sản phẩm tăng dần, cộng tác, thích ứng và cải tiến liên tục**, đồng thời thực hành user story, Product Backlog, Scrum, Kanban, XP và đo dòng công việc để lựa chọn cách phối hợp phù hợp.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **chuyên môn dùng chung**, **nhóm nền tảng**, **nhóm hỗ trợ phát triển năng lực** và **nhóm sản phẩm** theo trách nhiệm, loại tương tác và giá trị cung cấp.
2. Nhận diện các dạng phụ thuộc: **kiến thức, quyết định, môi trường, API/dữ liệu, công cụ, quyền truy cập và lịch phát hành**.
3. Thiết kế một **service catalog và đường tương tác** giúp nhóm tiêu thụ năng lực dùng chung biết tự làm gì, hỏi ai và kỳ vọng phản hồi ra sao.
4. Phân loại nhu cầu thành **self-service, tư vấn ngắn, hỗ trợ kèm cặp, hợp tác chuyên sâu và sự cố khẩn cấp**; lựa chọn mô hình thay vì đưa mọi việc vào cùng một hàng đợi.
5. Dùng **minh bạch ưu tiên, WIP, work item age, throughput, cycle time và Service Level Expectation (SLE)** để quản lý dòng yêu cầu hỗ trợ.
6. Giải thích **platform as a product**, “golden path”, trải nghiệm lập trình viên và các cơ chế an toàn như policy-as-code, CI/CD, quan sát và contract tests.
7. Đặt ranh giới **quyền quyết định và trách nhiệm chất lượng**, không để quyền sở hữu sản phẩm bị thay bằng phê duyệt tập trung mơ hồ.
8. Điều phối phụ thuộc xuyên nhóm khi xây một Increment tích hợp, bao gồm API contracts, schema migration và rollout.
9. Đánh giá cả **giá trị người dùng, năng lực nhóm tiêu thụ, sức khỏe nền tảng, an toàn và mức tải chuyên gia** bằng bộ chỉ số cân đối.
10. Lập kế hoạch thử nghiệm một chính sách phối hợp, đọc kết quả và điều chỉnh mà không tạo thêm tầng quản trị không cần thiết.

## 2. Tại sao chuyên môn dùng chung trở thành nút thắt?

Khi nhiều nhóm có thể chủ động xây các lát cắt sản phẩm nhưng **cùng chờ một người hoặc một nhóm cung cấp năng lực thiết yếu**, hệ thống dễ xuất hiện các đặc điểm:

- **Hàng đợi ẩn:** yêu cầu nằm trong chat riêng, email hoặc cuộc họp không được phản ánh trên workflow.
- **Chuyển ngữ cảnh:** một chuyên gia phải lần lượt đọc code, kiến trúc và bối cảnh của nhiều đội.
- **Ưu tiên xung đột:** mỗi Product Owner coi yêu cầu của mình là quan trọng nhất, nhưng không có cơ chế xét trade-off chung.
- **Handoff và chờ đợi:** nhóm phát triển “đã code xong” nhưng không thể kiểm chứng hoặc deploy vì thiếu quyền/chuyên môn.
- **Nợ tri thức:** cùng một câu hỏi xuất hiện ở nhiều nhóm vì không có tài liệu hoặc công cụ tự phục vụ.
- **Phụ thuộc cá nhân:** khi một người nghỉ, mọi yêu cầu cùng loại bị dừng.
- **Khả năng giao hàng khó dự báo:** không biết request sẽ được giải quyết ngay hay phải đợi hai tuần.

Điểm nguy hiểm là **cảm giác mọi người đều rất bận** có thể che đi việc **ít giá trị được đưa tới người dùng**. Chuyên gia có thể hoàn thành nhiều ticket tư vấn nhưng các nhóm sản phẩm vẫn không tạo được Increment tích hợp.

### Dòng giá trị nhìn từ người dùng

~~~mermaid
flowchart LR
    A["Người học cần<br/>tiếp tục bài dở"] --> B["Nhóm Trải nghiệm học viên"]
    B --> C["API checkpoint / quyền"]
    C --> D["Môi trường, CI/CD<br/>và dữ liệu"]
    D --> E["Increment tích hợp"]
    E --> F["Kiểm chứng + release"]
    F --> G["Người học nhận giá trị"]
    C -. "Chờ chuyên gia" .-> H["Hàng đợi<br/>bị ẩn"]
    D -. "Chờ nền tảng" .-> H
~~~

Nếu chỉ đo **thời gian lập trình** của từng nhóm, tổ chức có thể bỏ qua thời gian chờ ở H. Cần đo **dòng công việc end-to-end** từ lúc bắt đầu thực hiện lát cắt đến khi đạt chuẩn cần thiết, và phân biệt thời gian tới Done, tới deploy, tới release và tới outcome.

## 3. Phân biệt các kiểu phụ thuộc

Không phải phụ thuộc nào cũng cần một team platform mới hoặc một cuộc họp liên nhóm.

| Phụ thuộc | Dấu hiệu | Ví dụ | Hướng xử lý có thể phù hợp |
| --- | --- | --- | --- |
| **Kiến thức/chuyên môn** | Người làm không biết quy tắc hoặc kỹ thuật | Cần giải thích threat model cho API tiến độ | Tư vấn, pairing, workshop, tài liệu, coaching |
| **Quyền quyết định** | Không rõ ai có thẩm quyền hoặc tiêu chí | Ai duyệt ngoại lệ mã hóa dữ liệu? | Làm rõ policy/decision rights; audit và escalation |
| **Công cụ/môi trường** | Phải gửi ticket cho thao tác thường lệ | Tạo test environment, secret thử nghiệm | Platform self-service, template, automation |
| **API/hợp đồng** | Hai nhóm thay đổi interface khác nhịp | Contract của checkpoint giữa web và service | Consumer-driven contract tests, versioning, trao đổi sớm |
| **Dữ liệu/schema** | Migration ảnh hưởng nhiều consumer | Đổi cấu trúc learning_checkpoint | Expand–migrate–contract, kế hoạch tương thích |
| **Lịch phát hành/triển khai** | Phải chờ đồng bộ release | Hai service không hỗ trợ phiên bản cũ/mới | Backward compatibility, progressive rollout, release plan |
| **Năng lực phục vụ khẩn cấp** | Incident chiếm chuyên gia theo yêu cầu bất ngờ | Lỗi mất tiến độ trên production | Incident policy rõ, on-call/escalation |
| **Nguồn lực đầu tư** | Nhiều nhóm cùng cần một khả năng mới | Muốn xây dịch vụ feature flags dùng chung | Product/platform backlog, trade-off ở cấp thích hợp |

### Phân biệt phụ thuộc cần thiết với phụ thuộc do thiết kế tổ chức

Một kiểm tra bảo mật chuyên sâu cho thay đổi rủi ro cao **có thể cần chuyên gia thực**. Nhưng việc mọi nhóm phải nhắn riêng cho cùng chuyên gia chỉ để tạo tài khoản thử hoặc đọc hướng dẫn phân quyền thường là **phụ thuộc có thể giảm** bằng mẫu, chính sách rõ và self-service.

Mục tiêu không phải **xóa mọi phụ thuộc**. Một số phụ thuộc bảo vệ tính đúng đắn, pháp lý hoặc tính nhất quán. Mục tiêu là **làm rõ, giảm chi phí và xử lý phụ thuộc đúng cách**, tránh biến các tương tác cần thiết thành chờ đợi không dự báo được.

## 4. Ai là ai trong hệ sinh thái nhiều nhóm?

Một cách phân loại thường được nhắc tới trong tư duy **Team Topologies** gồm các kiểu đội **stream-aligned, platform, enabling, complicated-subsystem**. Đây là **mô hình tham khảo về thiết kế tổ chức**, không phải yêu cầu Agile/Scrum bắt buộc mỗi công ty có đủ bốn loại hoặc phải dùng đúng tên.

| Kiểu nhóm/năng lực | Giá trị cung cấp | Mối quan hệ với nhóm làm sản phẩm | Rủi ro nếu hiểu sai |
| --- | --- | --- | --- |
| **Nhóm theo dòng giá trị (stream-aligned)** | Tạo và cải tiến trải nghiệm/sản phẩm cho một luồng người dùng | Sở hữu phần việc end-to-end trong ranh giới phù hợp | Bị lệ thuộc vào nhiều cổng phê duyệt cho từng thay đổi |
| **Platform team** | Nền tảng nội bộ ổn định, dễ tự sử dụng | Cung cấp dịch vụ, “paved/golden path”, tài liệu và hỗ trợ | Trở thành help desk nhận mọi yêu cầu tùy ý |
| **Enabling team/chuyên gia hỗ trợ phát triển năng lực** | Giúp nhóm khác học kỹ thuật hoặc cách giải quyết vấn đề | Facilitation/coaching trong thời gian có mục tiêu | Can thiệp mãi mãi, nhóm nhận không hình thành năng lực |
| **Complicated-subsystem team** | Chuyên trách một thành phần đòi hỏi kiến thức sâu không hợp lý khi phân tán | Giao interface/contract rõ, đáp ứng nhu cầu consumer | “Đội kiến trúc” phê duyệt toàn bộ thay đổi và che giấu ownership |
| **Chuyên gia dùng chung** | Kiến thức/kỹ năng khan hiếm, có thể nằm trong các kiểu nhóm trên | Tư vấn, review theo rủi ro, thực hiện việc chuyên sâu hoặc mentoring | Một người thành single point of failure |

### Chuyên gia dùng chung không phải một team riêng

Chuyên gia có thể là **cá nhân ở nhiều bộ phận**, community of practice, người trực luân phiên hoặc thành viên một nhóm cung cấp dịch vụ. Nếu cứ tạo một “team” cho từng chuyên môn, tổ chức dễ có quá nhiều ranh giới và handoff. Cần cân nhắc **độ thường xuyên của nhu cầu, độ phức tạp và khả năng tự chủ**.

### Platform không phải đội có quyền quyết định mọi kiến trúc

Một platform team có thể sở hữu **quy trình CI/CD, hạ tầng chạy, capability tạo môi trường, cơ chế secrets và monitoring**. Nhưng không vì vậy họ tự động sở hữu **giá trị người học, thứ tự Product Backlog của nhóm Trải nghiệm, logic học tập và mọi quyết định sản phẩm**. Trách nhiệm cần được tách và thống nhất.

## 5. Ba cách tương tác hữu ích: self-service, facilitation và collaboration

Có thể tham khảo ba **interaction modes** của Team Topologies:

1. **X-as-a-Service:** Nhóm tiêu thụ sử dụng capability qua interface ổn định, tài liệu và hỗ trợ theo chính sách; với nền tảng, thường hướng tới **self-service**.
2. **Facilitating:** Chuyên gia giúp một nhóm học cách giải quyết vấn đề, tăng khả năng tự làm về sau.
3. **Collaboration:** Hai nhóm cùng làm sâu trong một thời gian để khám phá hoặc xây khả năng mới, với ranh giới kết thúc rõ.

### Cách chọn theo vấn đề

| Nhu cầu | Interaction mode chủ đạo | Ví dụ | Cách biết đã xong? |
| --- | --- | --- | --- |
| Tạo một test environment đã chuẩn hóa | Platform as a service/self-service | Developers dùng template và API | Môi trường được cấp đúng cấu hình, không cần ticket riêng |
| Học cách mô hình hóa authorization | Facilitating | Chuyên gia bảo mật pair cùng team qua hai story | Team tự giải quyết ca thông thường và biết khi nào escalation |
| Thiết kế cơ chế migration dữ liệu lớn | Collaboration có thời hạn | Nhóm dữ liệu + hai consumer cùng tạo chiến lược | Contract và rollout an toàn, ownership vận hành đã rõ |
| Vận hành dịch vụ identity chuyên sâu | Service interface/complicated subsystem | Nhóm identity cung cấp hợp đồng và SLO | Consumer tích hợp theo contract và có kênh incident |
| Một incident mất tiến độ nghiêm trọng | Hợp tác khẩn cấp tạm thời | Product + data + SRE điều tra | Dịch vụ phục hồi, ảnh hưởng được xử lý, hậu kiểm và cải tiến |

**Interaction mode có thể thay đổi theo thời gian.** Khi năng lực mới được xây, hai đội cần collaboration. Khi ổn định, đội platform nên cung cấp **service interface** để người dùng nội bộ tự làm. Khi consumer thiếu kiến thức, bật facilitating có thời hạn, rồi quay về self-service. Không biến một mode tạm thành sự phụ thuộc vĩnh viễn.

### Mẫu hành trình tương tác

~~~mermaid
flowchart TD
    A["Team cần capability"] --> B{"Dịch vụ đã có<br/>self-service?"}
    B -->|Có| C["Dùng tài liệu/API/template"]
    C --> D{"Có đạt mục tiêu?"}
    D -->|Có| E["Tiếp tục giao value<br/>và feedback platform"]
    D -->|Không| F["Gửi support request<br/>kèm bằng chứng"]
    B -->|Không| G{"Thiếu kiến thức<br/>hay thiếu capability?"}
    G -->|Thiếu kiến thức| H["Facilitation / pairing<br/>có timebox"]
    G -->|Thiếu capability| I["Xem product backlog<br/>và hợp tác thiết kế"]
    H --> J["Team tự làm được<br/>khi hỗ trợ kết thúc"]
    I --> K["Capability tối thiểu<br/>được cung cấp"]
    K --> C
    F --> L["Triage/owner<br/>phản hồi theo policy"]
    L --> C
~~~

Điều kiện “đã có dịch vụ” nên xét **khả năng dùng thực tế**, không chỉ “đã có repository và wiki”. Nếu onboarding cần bốn cuộc họp và một chuyên gia làm hộ, capability ấy chưa thật sự self-service.

## 6. Platform as a product: ai là khách hàng nội bộ?

Nhóm nền tảng nên nghĩ như một **nhóm sản phẩm nội bộ**: có người dùng xác định, vấn đề cần giải quyết, backlog theo giá trị, trải nghiệm sử dụng, reliability, phản hồi và lộ trình.

### Khách hàng nền tảng thường là ai?

- **Developers của nhóm sản phẩm** cần build, test, deploy, quan sát và vận hành mà không phải học mọi chi tiết hạ tầng.
- **Test/QA và data engineers** cần môi trường/dữ liệu thử đáng tin và khả năng xác minh.
- **SRE/vận hành** cần nền tảng an toàn, có khả năng khôi phục, giảm những thao tác vận hành lặp lại.
- **Bảo mật và quản trị** cần policy được thực thi nhất quán và có bằng chứng.
- **Product teams** cần năng lực đưa Increment có ích tới người dùng sớm với rủi ro chấp nhận được.

Họ là **người dùng nội bộ** với job-to-be-done thật. “Khách hàng nội bộ” không có nghĩa mọi yêu cầu tùy ý đều tự động được ưu tiên hoặc platform team phải hoàn thành ngay.

### Phân biệt output của platform với outcome

| Output nền tảng | Outcome cần kiểm chứng |
| --- | --- |
| Xây nút “Create staging” | Team có thể tự tạo môi trường phù hợp mà không chờ người khác |
| Phát hành CI template | Thay đổi được kiểm tra thường xuyên và pipeline đáng tin hơn |
| Cung cấp service catalog | Người dùng tìm được cách làm, ownership và kênh hỗ trợ |
| Xây dashboard mới | Team xác định và xử lý lỗi production nhanh, đúng dữ liệu |
| Tạo CLI deploy | Đưa artifact đủ điều kiện lên môi trường an toàn, có truy vết và phục hồi |

### Product thinking áp dụng ra sao?

1. **Khám phá nhu cầu:** Phỏng vấn/quan sát các nhóm tiêu thụ; tìm chỗ họ phải chờ hoặc làm thủ công.
2. **Chọn phân khúc:** Ví dụ nhóm Java backend trước, không cố phục vụ mọi công nghệ ngay.
3. **Giả thuyết giá trị:** “Nếu có template có test/monitoring mặc định thì thời gian đưa một service mới đến staging giảm”.
4. **MVP/Increment nội bộ:** Một golden path chạy được trên một service nhỏ, có hướng dẫn và support.
5. **Đo adoption + outcomes + guardrails:** Người dùng có thực sự tự làm được, nhanh/đáng tin hơn không?
6. **Lấy phản hồi và cải tiến:** Ưu tiên vấn đề làm nhiều team bị kẹt, không chỉ số ticket được đóng.

Platform team cũng phải quản lý **nợ kỹ thuật, vận hành và capacity** của chính mình. “Nền tảng là sản phẩm” không có nghĩa cứ ưu tiên feature mới mà bỏ support, incidents và reliability.

## 7. Self-service, golden path và cognitive load

**Cognitive load** là tải nhận thức mà người làm việc phải gánh để hoàn thành nhiệm vụ. Một nhóm sản phẩm chỉ muốn sửa quy tắc tính tiến độ nhưng phải tự hiểu Kubernetes, IAM, chứng chỉ, pipeline, secret rotation, log ingestion, migration và capacity có thể bị kéo xa khỏi mục tiêu người học.

### Một golden path có ý nghĩa

Golden path/paved road là **con đường được hỗ trợ, dễ dùng và an toàn theo mặc định** cho nhu cầu phổ biến. Nó có thể cung cấp:

- Template tạo service/repository có cấu trúc hợp lý.
- Pipeline CI với kiểm tra và artifact được định danh.
- Mẫu triển khai staging/production phù hợp chính sách.
- Logging, tracing, metrics và cảnh báo mặc định.
- Secrets/identity/access control theo quyền tối thiểu.
- Cách tạo môi trường và dữ liệu thử an toàn.
- Tài liệu “happy path”, ví dụ lỗi thường gặp và kênh hỗ trợ.
- Cơ chế nâng cấp/deprecation có thông báo và tương thích.

### “Golden” không có nghĩa mọi đội bắt buộc dùng một công nghệ

Một nền tảng tốt **giảm quyết định lặp lại không cần thiết**, nhưng cho phép ngoại lệ có căn cứ khi nhu cầu thực khác biệt. Nếu framework bắt buộc không hỗ trợ một loại workload hợp lệ, đội có thể cần **quy trình ngoại lệ rõ** thay vì tự ý phá chính sách hoặc phải chờ vô thời hạn.

### Đo thời gian tự phục vụ

Ví dụ một nhóm mới cần tạo service và có endpoint chạy trên môi trường thử:

| Trạng thái | Trước platform | Sau golden path |
| --- | --- | --- |
| Yêu cầu tài khoản/môi trường | Gửi ticket rồi chờ | Có quyền theo chính sách và tự tạo |
| Build/test | Tự ghép script | Template đã có CI checks |
| Monitoring | Nhờ vận hành cấu hình | Có instrumentation mặc định |
| Lấy hỗ trợ khi lỗi | Hỏi đúng người trong chat | Runbook, support request rõ, escalation |
| Kết quả cần đo | Thời gian tới môi trường hoạt động | Tỷ lệ tự phục vụ thành công, thời gian, số lỗi và trải nghiệm |

Không nên tuyên bố golden path tốt chỉ vì **đã có 50 template**. Hãy quan sát một Developer mới có hoàn thành tác vụ tự phục vụ được không và chất lượng dịch vụ có đạt yêu cầu.

## 8. Service catalog và giao diện phục vụ của platform team

**Service catalog** là điểm bắt đầu để nhóm khác biết platform cung cấp gì, ở đâu, ai chịu trách nhiệm, điều kiện sử dụng và hỗ trợ. Nó cần tập trung vào **hành động người dùng muốn làm**, không chỉ liệt kê tên công cụ.

### Ví dụ catalog

| Capability | Người dùng nội bộ | Hình thức tiếp cận | Điều kiện/chính sách | Đường hỗ trợ |
| --- | --- | --- | --- | --- |
| **Tạo staging service** | Developers | Template/API self-service | Có repo/owner và quota phù hợp | FAQ → support queue → escalation |
| **CI template Java** | Team backend | Starter kit và versioned updates | Mandatory tests và security policies | Kênh tư vấn template |
| **Quản lý secrets** | Services được cấp quyền | Secret manager/API | Least privilege, audit, không log token | Support bảo mật + incident |
| **Migration tư vấn** | Team có thay đổi schema phức tạp | Consultation có timebox | Tài liệu migration plan và rollback/roll-forward | Data specialist intake |
| **Observability tiêu chuẩn** | Team dịch vụ | Dashboards/SDK/alerts | Có owner và ngưỡng theo service | SRE/platform support |
| **Security threat modeling** | Nhóm có thay đổi rủi ro cao | Facilitated session | Phân loại rủi ro, bằng chứng thiết kế | Chuyên gia security |

### Mẫu interface một capability

~~~yaml
# Ví dụ mô tả tài liệu, không phải cấu hình áp dụng trực tiếp
service: java-service-staging
owner_team: platform-engineering
purpose: "Tạo môi trường thử cho dịch vụ Java được cấp quyền"
audience:
  - stream-aligned-product-teams
entrypoint:
  documentation: "Hướng dẫn tự tạo và gỡ lỗi"
  interface: "Template + automation"
requirements:
  - service_owner_defined
  - repository_and_access_policy_valid
  - minimum_security_checks_enabled
support:
  normal: "Hàng đợi hỗ trợ có phân loại"
  urgent: "Incident channel theo severity policy"
  escalation: "Owner trực và nhóm chuyên môn phù hợp"
lifecycle:
  versioned: true
  deprecation_notice: "Có chính sách công bố và hỗ trợ chuyển đổi"
feedback:
  - "Self-service task success"
  - "Time to usable environment"
  - "User feedback"
~~~

**Lưu ý:** Những chuỗi “Hướng dẫn...” chỉ là placeholder để minh họa cấu trúc. Một catalog thật phải có đường dẫn, owner, giới hạn, hỗ trợ và điều kiện được kiểm chứng; không suy ra từ ví dụ rằng hệ thống đã tồn tại.

### API của dịch vụ và interface tổ chức

Một nhóm có thể cung cấp API rất tốt nhưng **interface tổ chức** tệ: không rõ ai trả lời incident, ai duyệt change hoặc khi contract sẽ bị deprecate. Catalog cần bao gồm cả **đường dùng kỹ thuật** và **cách vận hành hỗ trợ**, để việc phối hợp không phụ thuộc trí nhớ một người.

## 9. Intake: không đưa mọi yêu cầu vào cùng một hàng đợi

Một inbox chung chứa sự cố production nghiêm trọng, câu hỏi “cách bật log?”, đề xuất tính năng mới và yêu cầu review migration sẽ tạo **ưu tiên tranh chấp**. Cần có **cửa vào minh bạch, phân loại đủ nhẹ và đường xử lý đúng**.

| Loại nhu cầu | Cách xử lý đề xuất | Đầu ra mong muốn |
| --- | --- | --- |
| **Self-service khả dụng** | Tài liệu/template/API; có đường phản hồi khi lỗi | Người tiêu thụ tự làm được và biết nơi báo vấn đề |
| **Câu hỏi đơn giản** | Hỏi đáp/office hours hoặc support queue | Câu trả lời rõ; vấn đề lặp lại thành docs/FAQ |
| **Consultation chuyên sâu** | Lịch tư vấn có timebox, chuẩn bị context | Quyết định kỹ thuật, risk notes hoặc bước tiếp |
| **Enablement** | Pairing/coaching có kế hoạch chuyển giao | Đội tiêu thụ tăng năng lực tự chủ |
| **Capability mới** | Product/platform backlog, discovery và trade-off | Giá trị/chi phí được đánh giá, ưu tiên minh bạch |
| **Thay đổi contract xuyên nhóm** | Collaboration ngắn giữa producer/consumers | Contract, compatibility và migration plan |
| **Incident nghiêm trọng** | Severity policy, on-call/escalation | Khôi phục an toàn, xử lý hậu quả và hậu kiểm |

### Một request đủ thông tin nên có gì?

~~~text
REQUEST:
  Người/nhóm gửi, link công việc hoặc service bị ảnh hưởng.
PURPOSE:
  Người dùng nội bộ đang muốn hoàn thành điều gì?
IMPACT:
  Đang chặn Increment/production hay chỉ là cải thiện mong muốn?
URGENCY:
  Deadline thực, mức sự cố và điều kiện nào khiến gấp?
CONTEXT:
  Version, logs đã khử secrets, contract và thử nghiệm đã làm.
EXPECTED HELP:
  Self-service issue, 30-min consultation, implementation hay decision?
OWNER & CONTACT:
  Ai bên yêu cầu có thể hợp tác để hoàn tất?
~~~

**Đừng bắt người dùng điền một biểu mẫu dài cho sự cố production đang diễn ra.** Incident phải có đường xử lý ngay; có thể bổ sung metadata sau khi dịch vụ đã được bảo vệ.

### Hàng đợi minh bạch không đồng nghĩa tập trung toàn bộ quyền lực

Intake giúp nhìn nhu cầu và quản lý năng lực, nhưng không nên buộc Developers gửi ticket cho **mọi thao tác đã có self-service**. Nó là **công cụ phát hiện vấn đề để giảm phụ thuộc**: những request lặp nhiều và ổn định có thể là ứng viên tự động hóa, không phải lý do tuyển thêm người nhận ticket vĩnh viễn.

## 10. Ưu tiên xuyên nhóm: ai quyết định và trên cơ sở nào?

Nếu ba Product Owners đều coi request của mình là “P0”, chuyên gia khó lựa chọn khách quan. Cần **nguyên tắc trade-off công khai** giữa giá trị sản phẩm, rủi ro, hạn thực, phụ thuộc và năng lực.

### Bộ tiêu chí gợi ý

- **Tác động người dùng:** Có chặn hành trình, mất dữ liệu hoặc ảnh hưởng đáng kể không?
- **An toàn/bảo mật/tuân thủ:** Có nguy cơ phải xử lý ngay hoặc nghĩa vụ bắt buộc không?
- **Độ khẩn có căn cứ:** Deadline bên ngoài, cửa sổ migration hoặc incident nào?
- **Phụ thuộc và chi phí chờ:** Bao nhiêu công việc đang bị chặn, chờ thêm gây điều gì?
- **Khả năng phục vụ:** Công việc có thể tự làm hoặc được hỗ trợ ngắn thay vì triển khai lớn?
- **Năng lực tạo lợi ích lặp lại:** Một platform capability phục vụ bao nhiêu nhóm trong phạm vi xác minh?
- **Chi phí cơ hội:** Nếu chọn việc này, điều gì phải trì hoãn và ai chấp nhận trade-off?

Không nên chọn chỉ bằng điểm số tự tạo cho mọi loại việc. Một incident bảo mật nghiêm trọng phải tuân theo **severity policy**, không xếp chung với cải tiến tài liệu bình thường rồi cộng “business value” để lựa chọn.

### Quyền quyết định nên đặt đúng chỗ

| Quyết định | Bên cần chịu trách nhiệm chính | Phối hợp |
| --- | --- | --- |
| Ưu tiên giá trị của một sản phẩm | Product Owner/người phụ trách sản phẩm theo cấu trúc tổ chức | Developers, stakeholders, nhóm phụ thuộc |
| Product/platform backlog và đầu tư capability | Người/nhóm chịu trách nhiệm sản phẩm nền tảng | Teams tiêu thụ, an toàn, vận hành, tài trợ năng lực |
| Thiết kế triển khai trong ranh giới sở hữu | Developers và owner kỹ thuật phù hợp | Producer/consumer, chuyên môn khi cần |
| Ngoại lệ bảo mật/tuân thủ | Người có thẩm quyền policy/risk cụ thể | Product, engineering, security, compliance |
| Ưu tiên incident nghiêm trọng | Incident commander/on-call theo quy định | Các dịch vụ/team bị ảnh hưởng |
| Trade-off cross-product khi năng lực khan hiếm | Người có quyền cân đối ở cấp thích hợp, với tiêu chí minh bạch | Các Product Owners, platform/specialist owners |

Không thể suy tất cả quyền từ tên chức danh. Tổ chức cần ghi rõ **quyền quyết định theo loại vấn đề**, quy trình escalation, và tránh hội đồng phê duyệt cho mọi thay đổi không cần thiết.

## 11. Quản lý capacity của chuyên gia mà không tối đa hóa mức bận

Một chuyên gia có thể là nút thắt vì nhu cầu **luôn cao hơn năng lực phục vụ**. Cho chuyên gia bận 100% với lịch họp kín khiến request khẩn chen ngang và làm việc đang xử lý bị gián đoạn; thời gian chờ và sai sót có thể tăng.

### Phân bổ capacity theo loại nhu cầu

Ví dụ giả định về một nhóm chuyên gia:

| Loại nhu cầu | Chính sách năng lực minh họa | Điều cần kiểm tra |
| --- | --- | --- |
| **Hỗ trợ thường lệ** | Dành khoảng hỗ trợ đã công bố và giới hạn WIP | Yêu cầu chờ có được xử lý dự báo được không? |
| **Enablement** | Đặt lịch pairing/workshop có mục tiêu | Consumer có tự làm được sau đó không? |
| **Nâng cấp self-service** | Bảo vệ một phần capacity cho việc giảm ticket lặp | Tỷ lệ self-service thành công và support demand có cải thiện? |
| **Reliability/tech debt** | Bảo trì bảo mật, phiên bản, cảnh báo và tài liệu | Dịch vụ còn đáng tin và dễ nâng cấp không? |
| **Incident/bất định** | Có cơ chế trực, escalation và điều chỉnh ưu tiên | Nhóm có phản ứng đủ nhanh mà không làm việc kiệt sức? |

**Không có tỷ lệ phần trăm capacity nào đúng cho mọi nhóm.** Đừng cứng nhắc “20% bắt buộc cho kỹ thuật” khi đang trong sự cố; ngược lại, nếu mọi tuần bị request khẩn chiếm hết và self-service không được cải tiến, vòng phụ thuộc sẽ không bao giờ giảm.

### Giới hạn WIP của chuyên gia

Một chuyên gia đang xử lý 12 vấn đề song song có thể **mất phần lớn ngày làm việc để chuyển ngữ cảnh**. Thử giới hạn số consultation/implementation đang mở, xác định chính sách khi đầy và khuyến khích những đội khác chuẩn bị đầy đủ context để hỗ trợ hiệu quả.

**WIP limit không được dùng để làm lơ incident nghiêm trọng.** Trường hợp khẩn cần đường expedite và quyết định điều gì phải tạm dừng, có dấu vết công khai.

### Xây năng lực dự phòng

Nếu chỉ một người hiểu migration hoặc deployment, việc tăng số slot tư vấn không giải quyết điểm yếu lâu dài. Cân nhắc pairing, review chéo, runbooks, rotation phù hợp, phân quyền theo chính sách, đào tạo và đơn giản hóa đường thực hiện. Mục tiêu là **giảm bus factor**, không biến mọi Developer thành chuyên gia mọi thứ.

## 12. SLE, hàng đợi và công bố kỳ vọng hỗ trợ

Một **Service Level Expectation (SLE)** trong thực hành Kanban là phát biểu về **thời gian kỳ vọng work item đi qua workflow với một xác suất**, dựa trên lịch sử hoặc một ước lượng ban đầu cần được kiểm chứng. Khi áp dụng cho yêu cầu hỗ trợ, phải xác định **đơn vị công việc, mốc bắt đầu/kết thúc và loại dịch vụ**.

### Ví dụ SLE có điều kiện

> “Với yêu cầu tư vấn kỹ thuật thông thường đã cung cấp đủ context, chúng tôi kỳ vọng **85%** yêu cầu có kết quả tư vấn ban đầu trong **tối đa ba ngày làm việc** từ khi được chấp nhận vào workflow hỗ trợ.”

Đây là **minh họa về phát biểu SLE**, không phải thống kê đã kiểm chứng của nền tảng nào. Một SLE nên được tạo từ dữ liệu và điều chỉnh khi điều kiện thay đổi. Nó **không phải lời hứa 100%** hoặc một hợp đồng SLA có phạt theo pháp lý.

### Cần tách response time, resolution time và delivery time

| Mốc | Ý nghĩa | Vì sao dễ nhầm? |
| --- | --- | --- |
| **First response** | Khi người nhận xác nhận đã xem/triage | Trả lời “đã nhận” không có nghĩa đã giải quyết |
| **Time to consultation outcome** | Khi có tư vấn/quyết định đã thống nhất | Có thể cần nhóm tiêu thụ tự thực hiện phần tiếp |
| **Time to unblock** | Khi đội phụ thuộc có thể tiếp tục | Kết quả quan trọng với flow end-to-end |
| **Time to capability delivery** | Khi platform feature mới đạt điều kiện sử dụng | Không thể áp cùng SLE với câu hỏi nhỏ |
| **Time to restoration** | Khi dịch vụ được khôi phục sau incident | Theo severity/incident process riêng |

### Ví dụ tính hàng đợi đơn giản, không phải cam kết

Giả sử có **12 yêu cầu thường lệ** đang chờ và trung bình giải quyết **3 yêu cầu/tuần**, không có yêu cầu mới, mọi việc cùng loại và năng lực không thay đổi. Thời gian xử lý hết lượng tồn tính toán thô là:

\[
\frac{12\ \text{yêu cầu}}{3\ \text{yêu cầu/tuần}}=4\ \text{tuần}.
\]

Đây **không phải SLE cho một yêu cầu cụ thể**: thực tế có request mới, độ khó khác nhau, đổi ưu tiên, interruption và biến thiên. Con số minh họa cho thấy khi **nhu cầu vượt năng lực phục vụ**, chỉ yêu cầu “phản hồi sớm hơn” không tự xóa được hàng đợi.

### Khi nào cần thêm người, khi nào cần giảm nhu cầu?

Nếu các request lặp lại cùng nguyên nhân, giải pháp có thể là **tự phục vụ, tài liệu, automation hoặc enablement**. Nếu nhu cầu thật sự phức tạp và thường xuyên, có thể cần **mở rộng năng lực chuyên gia** hoặc một nhóm chuyên trách. Quyết định cần nhìn **chi phí, rủi ro, nhu cầu dự báo, tác động end-to-end và khả năng duy trì**, không chỉ đếm ticket.

## 13. Trực quan hóa phụ thuộc xuyên nhóm mà không tạo “siêu bảng” quan liêu

Phụ thuộc thường có hai tầng: **công việc nhóm A phải làm** và **điều nhóm A cần từ nhóm B để hoàn tất**. Nếu chỉ theo dõi hai backlog riêng biệt, các bên dễ phát hiện muộn rằng một API contract hoặc môi trường chung chưa sẵn sàng.

Một bảng phụ thuộc tối thiểu có thể giữ các thông tin:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Outcome/Increment cần đạt** | Phụ thuộc phục vụ giá trị nào | Học viên mở lại đúng bài sau khi đăng nhập |
| **Requesting team** | Nhóm cần capability/đầu ra | Trải nghiệm học viên |
| **Providing owner** | Nhóm/người chịu trách nhiệm cung cấp phần phụ thuộc | Nhóm identity hoặc platform |
| **Đầu ra có thể xác nhận** | Giao diện, quyết định, tài liệu hay môi trường nào được cần | API checkpoint bảo vệ quyền và contract version mới |
| **Need-by date và lý do** | Mốc cần thiết gắn với quyết định thực, không tùy tiện | Trước khi E2E kiểm thử lát cắt tích hợp |
| **Tình trạng** | Ready, in progress, blocked, verified hoặc quy tắc phù hợp | Đang chờ điều kiện test phân quyền |
| **Rủi ro/tác động chờ** | Chậm ảnh hưởng công việc nào | Hai PBIs chưa thể đạt DoD |
| **Bước tiếp và kênh escalation** | Ai phải làm gì, khi nào xem lại | Hẹn contract review, chủ sở hữu rõ |

### Một dependency board nhỏ

~~~text
Mục tiêu: Increment "Học tiếp" an toàn

Nhóm Trải nghiệm học viên
  ├── Cần hợp đồng API checkpoint từ Nhóm quyền & tiến độ
  │     └── Chủ sở hữu: API owner | Mốc: trước integration test
  ├── Cần kiểm tra migration từ Data specialist
  │     └── Đầu ra: compatibility plan | Mốc: trước staging rollout
  └── Cần staging + logs từ Platform
        └── Self-service theo catalog | Support khi provisioning lỗi

Điểm quyết định:
  - Contract giữ tương thích old/new consumer?
  - Test phân quyền đạt?
  - Migration an toàn?
  - Ai chịu trách nhiệm nhận và xử lý incident?
~~~

**Không cần nhân bản toàn bộ backlog của mọi team** sang một bảng liên nhóm mới. Chỉ đưa những phụ thuộc có ảnh hưởng tới **khả năng tích hợp, rủi ro hoặc mốc học hỏi**; dùng liên kết tới nguồn công việc gốc để tránh thông tin lệch.

### Kiểm tra phụ thuộc theo nhịp nào?

Phụ thuộc có thể được xem khi **refinement** (phát hiện contract/data/environment cần thiết), **planning/replenishment** (năng lực và điều kiện kéo việc), trong lúc phát triển (blocked/age), trước rollout (version và chất lượng), và sau rollout (học từ sự cố và feedback). Nhịp phối hợp nên dựa vào **tốc độ thay đổi và rủi ro**, không mặc định mỗi nhóm phải cử đại diện tới một cuộc họp dài hằng ngày.

## 14. Điều phối API và hợp đồng dữ liệu: giảm nhu cầu họp đồng bộ

Một phụ thuộc quan trọng trong hệ thống nhiều nhóm là **producer và consumer** của API. Ví dụ nhóm backend thay đổi cấu trúc checkpoint trong khi web/mobile vẫn cần đọc phiên bản cũ.

| Quyết định | Producer cần làm rõ | Consumer cần làm rõ |
| --- | --- | --- |
| **Schema** | Trường bắt buộc/tùy chọn, kiểu dữ liệu, versioning | Trường nào thực sự sử dụng, hành vi khi thiếu dữ liệu |
| **Authentication/authorization** | Ai được gọi, kiểm tra quyền ở đâu | Cách gửi danh tính, hành vi khi không có quyền |
| **Error semantics** | Lỗi 4xx/5xx, checkpoint không hợp lệ | UI hiển thị gì, có retry/fallback thế nào |
| **Consistency** | Khi nào tiến độ được coi là đã lưu | Người học có thể tin trạng thái “Đã lưu” khi nào |
| **Backward compatibility** | Phiên bản cũ hỗ trợ tới mốc nào | Kế hoạch nâng cấp/triển khai |
| **Observability** | Trace/request id, metric và audit phù hợp | Cách phối hợp tìm nguyên nhân lỗi |

### Consumer contract và integration tests

~~~gherkin
Feature: Đọc checkpoint của học viên đúng quyền

  Scenario: Người học đủ quyền tiếp tục từ checkpoint hợp lệ
    Given học viên A có quyền học khóa K
      And A có checkpoint tại bài B, vị trí 120 giây
    When A yêu cầu điểm tiếp tục của khóa K
    Then API trả checkpoint hợp lệ của A
      And trả thông tin cần thiết để mở bài B

  Scenario: Không tiết lộ checkpoint của tài khoản khác
    Given A có một checkpoint trong khóa K
      And học viên B không có quyền truy cập checkpoint đó
    When B yêu cầu checkpoint thuộc A
    Then API từ chối theo hợp đồng phân quyền
      And không tiết lộ dữ liệu tiến độ của A
~~~

Các kịch bản là **đề xuất hành vi**, chưa thay việc xác nhận quy tắc thực với người hiểu nghiệp vụ và bảo mật. Khi contract đã thống nhất, automated contract/integration tests giúp hai nhóm biết sớm khi thay đổi phá vỡ consumer.

### Mã giả về version contract

~~~json
{
  "checkpointSchemaVersion": 2,
  "lessonId": "lesson-B",
  "positionSeconds": 120,
  "completionState": "IN_PROGRESS",
  "lastConfirmedAt": "2026-01-01T10:00:00Z"
}
~~~

Ví dụ chỉ minh họa dữ liệu cần cho hành vi; **không đưa token, bí mật hoặc checkpoint của người khác** vào response. Phải xác định owner schema, phiên bản, chính sách tương thích và cách kiểm tra lỗi.

### Contract trước họp, không phải không bao giờ họp

Tài liệu API, ví dụ nghiệp vụ và contract tests giúp giảm sự phụ thuộc vào hội thoại đồng bộ **mỗi lần thay đổi**. Nhưng khi hai bên chưa hiểu yêu cầu hoặc phải chọn trade-off lớn, một **phiên collaboration ngắn** có thể hiệu quả hơn hàng chục bình luận qua ticket. Mục tiêu là **trao đổi đúng lúc, có quyết định, rồi mã hóa điều đã hiểu vào interface/test**.

## 15. Phân quyền sở hữu và trách nhiệm chất lượng end-to-end

Sở hữu một service không giống có quyền quyết định toàn bộ sản phẩm. Khi lỗi phát sinh xuyên lớp, các nhóm cần biết **ai xử lý từng phần** và **ai chịu trách nhiệm khép hành trình người dùng**.

| Công việc/khả năng | Nhóm sản phẩm tiêu thụ | Nhóm cung cấp service/API | Platform team | Shared specialist |
| --- | --- | --- | --- | --- |
| Giá trị và hành trình người học | Dẫn dắt nhu cầu, xác minh outcome | Tham gia contract | Cung cấp telemetry/capability | Tư vấn theo rủi ro |
| Logic checkpoint ở service sở hữu | Kiểm thử consumer | Sở hữu quy tắc, API và tests producer | Cung cấp runtime/pipeline | Hỗ trợ data/security |
| CI và deploy template | Sử dụng, cấu hình và bảo trì code | Sử dụng với service của mình | Sở hữu template, nâng cấp và hỗ trợ | Định nghĩa policy chuyên sâu khi cần |
| Security authorization | Kiểm tra trong hành trình | Bảo vệ endpoint tại server | Cung cấp công cụ/kiểm soát nền | Đánh giá threat model/ngoại lệ |
| Migration schema | Kiểm tra consumer tương thích | Sở hữu migration dữ liệu mình | Cơ chế deploy phù hợp | Review chiến lược rủi ro cao |
| Production incident | Xử lý tác động người học | Xử lý lỗi service | Hỗ trợ hạ tầng và tooling | Chuyên môn sâu khi được gọi |

**Bảng không phải RACI áp đặt.** Thực tế tùy ranh giới service và tổ chức. Cần minh bạch nhất: **ai có quyền sửa/triển khai, ai trực sự cố, ai chấp nhận rủi ro, ai làm việc với người dùng và ai bảo trì capability**.

### Ai “run” dịch vụ?

Tư duy “you build it, you run it” có thể hữu ích nhưng không phải khẩu hiệu áp mọi nơi. Nhóm sản phẩm thường hiểu logic và lỗi code của họ; platform chịu trách nhiệm **hạ tầng/capability được cung cấp**, đồng thời hỗ trợ quan sát. **Runbook và on-call boundaries** phải rõ, nếu không incident thành tranh luận “lỗi của ai”.

### Definition of Done cho nhiều nhóm

Khi nhiều nhóm góp phần vào một sản phẩm, **Increment phải được tích hợp và kiểm chứng**. Với nhiều Scrum Teams trên **cùng một sản phẩm**, Scrum Guide nói tới **cùng Product Goal, Product Backlog, Product Owner và Definition of Done**, không phải mỗi nhóm tự đặt chuẩn xung đột cho Increment chung.

Với **nhiều sản phẩm độc lập**, đừng ép thành một Product Backlog giả cho “giống Scrum”. Hãy làm rõ một sản phẩm nhiều nhóm hay nhiều sản phẩm liên kết bằng contract, rồi thiết kế trách nhiệm phù hợp.

## 16. Phân loại việc hỗ trợ thường lệ và incident

Một chính sách điều phối lành mạnh phải phân biệt **tư vấn thường lệ** với **sự cố nghiêm trọng**.

| Loại nhu cầu | Điều kiện | Cách phục vụ | Rủi ro cần tránh |
| --- | --- | --- | --- |
| **Standard** | Support/tư vấn bình thường | Intake, giới hạn WIP, SLE | Request bị bỏ quên |
| **Fixed-date có căn cứ** | Mốc hợp đồng/migration/cửa sổ phối hợp thực | Lập kế hoạch sớm, rõ phụ thuộc | Ai cũng tự khai “deadline” để chen hàng |
| **Expedite** | Sự cố hoặc tắc nghẽn nghiêm trọng theo chính sách | Ưu tiên tức thì, owner, dừng việc phù hợp | Lạm dụng “urgent” làm mọi việc mất dự báo |
| **Enablement** | Cần tăng năng lực team | Coaching/pairing có timebox | Specialist viết code hộ mãi |
| **Capability investment** | Nhu cầu lặp, lợi ích nhiều team | Platform backlog/discovery | Bị lấn át bởi hỗ trợ ngắn hạn |

Tên lớp dịch vụ là **gợi ý chính sách**, không bắt buộc mọi nhóm dùng một bảng cứng.

### Incident không phải ticket hỗ trợ

Giả sử học viên bị **mất checkpoint sau deployment**. Nhóm phải theo incident policy, bảo vệ dữ liệu, xác định mức ảnh hưởng và khôi phục an toàn. Không yêu cầu người báo lỗi điền form tư vấn trong hai ngày. Sau sự cố, có thể làm hậu kiểm **không đổ lỗi** và cập nhật backlog.

Incident chiếm chuyên gia sẽ ảnh hưởng nhu cầu thường lệ: cần **ghi interruption, cập nhật dự báo và báo người chịu trách nhiệm** thay vì hứa mọi deadline vẫn giữ nguyên.

## 17. Backlog của platform không chỉ là danh sách support tickets

| Loại công việc | Ví dụ | Giá trị tạo ra |
| --- | --- | --- |
| **Capability** | Self-service staging | Nhiều team tự làm, giảm chờ |
| **Developer experience** | Onboarding, CLI báo lỗi rõ | Giảm thời gian hiểu và hoàn thành tác vụ |
| **Reliability** | Sửa pipeline flaky, cập nhật runtime | Nền tảng đáng tin và phục hồi tốt |
| **Security** | Policy-as-code, audit, secret rotation | Bảo vệ nhất quán, có bằng chứng |
| **Support** | Chẩn đoán lỗi môi trường | Gỡ blocker cụ thể |
| **Enablement** | Pairing, workshop | Team tiêu thụ tự chủ hơn |
| **Lifecycle** | Deprecate template cũ | Ít phân mảnh và rủi ro tương lai |

### Ưu tiên theo giá trị và rủi ro

Ba đề xuất cạnh tranh: sửa lỗi staging ảnh hưởng năm team; xây trang web nội bộ mới chưa chứng minh giá trị; tạo kiểm tra security bắt buộc sau phát hiện rủi ro nghiêm trọng. Quyết định phải xét **tác động, nghĩa vụ an toàn, tần suất, chi phí chờ, năng lực và trade-off**, không chỉ tổng số người bình chọn.

Nếu 90% thời gian dùng giải cùng một loại ticket môi trường, giải pháp có thể là **đầu tư vào self-service** chứ không tuyển thêm người nhận ticket vĩnh viễn. Cần bảo vệ một phần năng lực cho **loại bỏ nguyên nhân demand**, song không để incidents/bảo mật thiếu hỗ trợ.

### Roadmap nội bộ cần khám phá người dùng

Platform có thể phỏng vấn Developers, quan sát onboarding, đo support demand và task success, phát hành MVP của golden path rồi cải tiến. **Người gửi yêu cầu lớn tiếng nhất không tự động là người quyết định backlog**; quyền ưu tiên cần rõ, cân bằng lợi ích tổng thể và rủi ro.

## 18. Metrics hiệu quả điều phối và nền tảng

Một nền tảng có thể đóng ticket nhanh nhưng ít team sử dụng, hoặc được dùng nhiều chỉ vì **bắt buộc** dù trải nghiệm tệ. Cần đọc bộ chỉ số cân đối.

| Metric | Câu hỏi | Cạm bẫy |
| --- | --- | --- |
| **Self-service task success** | Consumer tự thực hiện tác vụ đủ điều kiện được không? | Cần định nghĩa “thành công” thật |
| **Time-to-first-use** | Developer mới đưa service mẫu tới staging trong bao lâu? | Không đo reliability dài hạn |
| **Support demand** | Có câu hỏi lặp nên thành docs/automation không? | Ít ticket có thể do khó báo lỗi |
| **Queue/flow** | WIP, age, throughput, response/resolution/unblock time thế nào? | Request khác kích thước/giá trị |
| **Reliability** | Pipeline, staging, monitoring có đáng tin? | Không thay kiểm chứng product outcome |
| **Adoption phù hợp** | Các team có nhu cầu thật có dùng capability không? | Forced adoption không chứng minh giá trị |
| **Developer experience** | Tác vụ có dễ, ít cognitive load hơn không? | Survey cần đối chiếu hành vi |
| **End-to-end product delivery** | Teams giao thay đổi an toàn tới người dùng nhanh hơn? | Nhiều yếu tố ngoài platform |

### Ví dụ tính self-service success

Giả sử có **80 tác vụ tạo staging hợp lệ**, trong đó **60** hoàn tất qua template, môi trường dùng được và không cần người platform thao tác:

\[
\text{Self-service task success}=\frac{60}{80}\times100\%=75\%.
\]

Đây là **75% tác vụ**, không tự đồng nghĩa **75% Developers tự chủ**; một người có thể làm nhiều lượt. Nếu template báo thành công nhưng môi trường không chạy được, phải sửa cách xác định success.

### Tránh Goodhart

- **Số ticket đóng:** có thể tăng bằng cách chia ticket hoặc chuyển trách nhiệm.
- **Adoption:** có thể tăng bằng cách ép tất cả dùng công cụ chưa phù hợp.
- **First response time:** bot trả “đã nhận” nhanh không có nghĩa team đã hết bị chặn.

Tốt hơn là xem **self-service success, time-to-unblock, reliability, developer feedback, product delivery outcomes và tải của người vận hành**. Không dùng số commit hay ticket để xếp hạng cá nhân.

## 19. Shared specialists: chuyển từ “người phê duyệt” sang “năng lực lan tỏa”

Chuyên gia có thể hiểu những hệ thống rất khó thay thế, nhưng nếu mọi thay đổi phải chờ họ **trực tiếp làm hoặc ký duyệt**, hệ thống bị giới hạn bởi lịch của vài người.

| Mẫu hỗ trợ | Khi phù hợp | Đầu ra/điều kiện kết thúc | Rủi ro |
| --- | --- | --- | --- |
| **Office hours** | Câu hỏi thiết kế và kỹ thuật không khẩn | Quyết định/hướng giải quyết rõ | Tư vấn lặp mãi mà không có docs |
| **Review dựa trên rủi ro** | Đổi kiến trúc/dữ liệu/bảo mật quan trọng | Xác nhận những nguy cơ cần chuyên môn | Duyệt tay mọi thay đổi rủi ro thấp |
| **Pairing/coaching** | Consumer có thể tự học kỹ thuật | Team làm được tình huống lặp về sau | Specialist code hộ vô hạn |
| **Community of Practice** | Trao đổi kiến thức xuyên nhóm | Patterns, ví dụ, người liên hệ | Họp nhiều nhưng không giải vấn đề |
| **Rotation/backup** | Một người thành single point of failure | Người thay thế đủ khả năng và quyền | Luân chuyển gây gián đoạn nếu không chuẩn bị |
| **Automation/policy-as-code** | Kiểm tra lặp, oracle rõ | Feedback nhanh và nhất quán | Policy thiếu ngữ cảnh hoặc cứng nhắc |
| **Embedded specialist có thời hạn** | Thay đổi phức tạp cần cùng làm | Chuyển giao năng lực, ownership rõ | Cạn năng lực hỗ trợ các team khác |

### Không cần ai cũng là chuyên gia mọi thứ

Một thuật toán tối ưu đặc biệt, an toàn mật mã chuyên sâu hoặc subsystem quan trọng có thể hợp lý khi một nhóm nhỏ **sở hữu và cung cấp interface chất lượng**. Giảm phụ thuộc không đồng nghĩa **mỗi team phải học mọi lĩnh vực**. Cần cân bằng cognitive load, chiều sâu chuyên môn, chi phí giao tiếp và an toàn.

### Ví dụ bảo mật: giảm yêu cầu review lặp lại

Khi nhiều team thường hỏi “API checkpoint đã kiểm tra quyền tài khoản đúng chưa?”, có thể:

1. Chốt **policy và threat model** với người có thẩm quyền.
2. Pair cùng Developers xây mẫu authorization tests.
3. Đưa những kiểm tra ổn định vào CI hoặc thư viện dùng chung.
4. Xác định **trường hợp mới/ngoại lệ** vẫn phải cần security specialist.
5. Chuyển giao cách đánh giá rủi ro và ví dụ lỗi thường gặp.
6. Đo time-to-unblock, tỷ lệ lỗi quyền lọt, số yêu cầu lặp và trải nghiệm nhóm.

**Không được dùng việc giảm số lần review để hạ mức bảo vệ.** Chuyên gia cần được giải phóng khỏi công việc lặp để tập trung vào **rủi ro thật sự đòi kiến thức sâu**.

## 20. Guardrails chung: bảo mật, tuân thủ và quyền triển khai

Platform có thể cung cấp những kiểm soát an toàn mặc định, nhưng không thể thay trách nhiệm nghiệp vụ của service owners.

| Capability chung | Giá trị | Người tiêu thụ vẫn phải làm |
| --- | --- | --- |
| Secret manager, least-privilege templates | Tránh hardcode secrets, giảm sai cấu hình | Phân quyền service mình theo chức năng thật |
| CI security baseline, dependency scan | Phát hiện nhiều loại rủi ro lặp | Review thiết kế và xử lý rủi ro ứng dụng |
| Artifact provenance, version/digest | Truy vết bản đã deploy | Không deploy bản chưa đạt quality gates |
| Policy-as-code và IaC | Kiểm soát nhất quán | Xác định policy/ngoại lệ có thẩm quyền |
| Logging/tracing/alert templates | Dễ phát hiện và điều tra sự cố | Định nghĩa business guardrails và không log dữ liệu nhạy cảm quá mức |
| Identity/authorization libraries | Giảm code lặp | Kiểm tra quyền **tại server** theo người dùng và resource thật |

### Self-service không đồng nghĩa quyền vô hạn

Developers có thể tự triển khai artifact đã được kiểm tra theo policy, nhưng **không tự ý tắt security gates hoặc sử dụng secrets production để test**. Cơ chế tự phục vụ tốt phải giúp việc đúng **dễ thực hiện nhất**; ngoại lệ có căn cứ cần kênh quyết định và audit.

### Khi quy định đòi phê duyệt thủ công

Nếu pháp lý/hợp đồng yêu cầu review theo từng lần, không bỏ kiểm soát chỉ để đạt danh hiệu “Continuous Deployment”. Có thể **tự động chuẩn bị evidence, tiêu chuẩn hóa điều kiện, giảm vòng hỏi đáp và đo waiting time**, rồi giữ việc phê duyệt cần thiết đúng nơi.

## 21. CI/CD và môi trường dùng chung để tích hợp sớm

Platform giúp giảm handoff bằng cách cung cấp **đường build–test–deploy có thể lặp lại**, trong khi các nhóm phát triển tiếp tục sở hữu mã nghiệp vụ và kiểm thử của service mình.

~~~mermaid
flowchart TD
    A["Team sản phẩm<br/>thay đổi nhỏ + contract"] --> B["CI mỗi service"]
    B --> C["Unit, API, contract,<br/>security checks"]
    C --> D["Artifact định danh"]
    D --> E["Platform deployment capability"]
    E --> F["Staging/integration<br/>logging + tracing"]
    F --> G{"Cross-team<br/>compatibility đạt?"}
    G -->|Không| H["Producer/consumer sửa và<br/>kiểm tra lại"]
    H --> A
    G -->|Có| I["Deploy/rollout theo policy"]
    I --> J["Theo dõi health,<br/>nghiệp vụ, feedback"]
~~~

**CI/CD self-service có điều kiện**: ai cũng có đường được hỗ trợ để xây và triển khai, không có nghĩa được bỏ test hay quyền kiểm soát phù hợp.

### Build once, promote đúng artifact

Một thực hành hữu ích là định danh artifact đã kiểm tra và **dùng cùng bản** qua staging/production, tách secrets/cấu hình theo môi trường. Nếu production chạy bản build khác staging, bằng chứng kiểm thử mất giá trị. Platform có thể chuẩn hóa việc này cho nhiều nhóm.

### Tích hợp sớm khác phát hành đồng bộ bắt buộc

API contracts, compatibility tests và versioning thường giúp các service thay đổi **không phải deploy cùng phút**. Nhưng khi schema/ràng buộc không tương thích, các bên vẫn cần một kế hoạch phối hợp có kiểm chứng. Không đánh đổi đúng dữ liệu để làm mỗi nhóm “tự chủ” trên danh nghĩa.

## 22. Migration và rollout nhiều nhóm: hợp tác đúng nơi cần

Service tiến độ muốn chuyển từ một trường bài cuối đơn giản sang cấu trúc checkpoint mới. Web, mobile, analytics và một số job nền đều có thể phụ thuộc.

### Expand–migrate–contract

| Giai đoạn | Producer/data owner | Consumers | Platform/specialists |
| --- | --- | --- | --- |
| **Expand** | Bổ sung schema mới, vẫn giữ đường cũ tương thích | Xác nhận phiên bản hiện hành vẫn chạy | Migration tools, test/hỗ trợ |
| **Migrate/backfill** | Chuyển dữ liệu có kiểm tra, idempotency theo thiết kế | Quan sát những dữ liệu bất thường | Review rủi ro cao, telemetry |
| **Transition** | Hỗ trợ old/new paths hoặc contract versioned | Cập nhật consumer theo kế hoạch | Progressive deployment, metrics |
| **Contract** | Gỡ đường cũ sau khi không còn phụ thuộc | Xác nhận không còn consumer cũ | Audit, runbook và phục hồi |

### Những bằng chứng cần trước rollout

~~~text
Contract: producer và consumers thống nhất schema/semantics.
Security: authorization tests quan trọng PASS.
Data: migration/backfill checks và giới hạn rollback rõ.
Platform: artifact đúng, environment/pipeline/monitoring sẵn sàng.
Product: Increment có hành vi dùng được và đạt quality criteria.
Rollout: exposure, owner, canary/flag và điều kiện dừng nếu cần.
~~~

**Rollback code không tự hoàn tác dữ liệu đã bị sửa/xóa.** Một thay đổi dữ liệu thật cần kế hoạch bảo vệ/khôi phục riêng. Nếu old/new service cùng chạy, schema và API phải tương thích trong giai đoạn chuyển tiếp.

### Khi nào cần đồng bộ chặt?

Khi một thay đổi thật sự không thể giữ tương thích và có rủi ro chặn consumer, cần phối hợp **trình tự, cửa sổ, dự phòng và khả năng khôi phục**. Đây có thể là dấu hiệu cần cải tiến kiến trúc lâu dài, không phải lý do phủ nhận nhu cầu cộng tác khẩn hiện tại.

## 23. Case study: phối hợp các nhóm để giao “Học tiếp”

Đây là **tình huống giả định dùng cho học tập**, không phải dữ liệu nội bộ của dự án thật.

### 23.1. Các nhóm và năng lực liên quan

| Nhóm/năng lực | Trách nhiệm | Nhu cầu phối hợp |
| --- | --- | --- |
| **Trải nghiệm học viên** | UI web/mobile, đo tác vụ | API checkpoint, flags, staging |
| **Quyền và tiến độ** | Domain checkpoint, authorization và API | Data/schema, identity |
| **Nội dung khóa học** | Lesson metadata, bài đã xóa/hoàn thành | Hợp đồng lesson ID và quyền |
| **Phân tích học tập** | Metrics và sự kiện có quyền phù hợp | Event contract, privacy |
| **Platform engineering** | CI/CD, staging, secrets, observability | Service demands, support |
| **Shared specialists** | Security, data migration, SRE chuyên sâu | Consult/enabling theo rủi ro |

Không nhất thiết doanh nghiệp phải tổ chức đúng sáu đội: bảng mô tả **năng lực và phụ thuộc** để học.

### 23.2. Sprint đầu: bottleneck vô hình

Hai ngày trước Sprint Review:

1. API checkpoint chưa bảo vệ đầy đủ tình huống quyền học hết hạn.
2. Data specialist chưa xem migration compatibility.
3. Staging lỗi secret provisioning; chỉ một platform engineer biết sửa.
4. Chưa thống nhất event nào được xem là “mở đúng bài”.
5. Mọi nhóm đều nghĩ nhóm khác sẽ bật business monitoring.

**Chẩn đoán:** Không chỉ thiếu một người điều phối. Interface và ownership chưa rõ, chuyên môn chung được gọi quá muộn và tất cả yêu cầu xử lý qua quan hệ cá nhân.

### 23.3. Thử cách phối hợp mới

- Product Owner và Developers **làm rõ lát cắt end-to-end** ngay khi refinement nhận diện phụ thuộc.
- Producer/consumer thống nhất **API contract** cho ca hợp lệ và sai quyền trước khi triển khai sâu.
- Platform cung cấp **staging template** với support rõ khi provisioning thất bại.
- Data specialist pair với API team **theo timebox** để đưa ra migration plan thay vì làm hộ toàn bộ.
- Security đưa **mẫu authorization tests** vào CI, vẫn review những ca mới hoặc rủi ro cao.
- Các owner thống nhất ai chịu trách nhiệm **service health, business guardrails và incident**.
- Dependency board chỉ chứa những điều **có thể chặn Increment**, không sao chép toàn bộ backlog.

### 23.4. Một chuỗi tương tác minh họa

~~~mermaid
sequenceDiagram
    participant PO as Product Owner
    participant UX as Team học viên
    participant API as Team tiến độ
    participant PL as Platform
    participant SP as Shared specialist
    PO->>UX: Outcome và acceptance examples
    UX->>API: Consumer contract cho Học tiếp
    API->>SP: Tư vấn quyền và migration
    SP-->>API: Policy, ví dụ test, escalation
    UX->>PL: Tự tạo staging theo golden path
    PL-->>UX: Môi trường + telemetry
    API->>PL: Deploy artifact đã qua checks
    UX->>API: Integration/contract tests
    API-->>UX: Bằng chứng quality & compatibility
    UX->>PO: Increment đã đạt chuẩn + feedback
    PO->>UX: Cập nhật Product Backlog
~~~

Các bước có thể **lặp/diễn ra song song**, không phải một chuỗi thủ tục cứng. Product Owner không phê duyệt từng dòng code: vai trò của họ là định hướng giá trị và Product Backlog theo bối cảnh Scrum.

### 23.5. Một request support được mô tả tốt

~~~text
REQUEST: staging-secret-provisioning
REQUESTER: Team Trải nghiệm học viên
CAPABILITY: java-service-staging
INTENT: chạy integration tests cho luồng Học tiếp
IMPACT: hai PBIs đang bị chặn đạt quality criteria
EVIDENCE: environment version, request id, error code
EXCLUDED: không đưa token/secret thật vào ticket
EXPECTED: template tự chạy lại được hoặc workaround hợp lệ,
          có owner xử lý nguyên nhân gốc
NEXT REVIEW: theo support policy công bố
~~~

**Giải quyết tốt không chỉ là sửa tay một môi trường**. Nếu nhiều team cùng gặp lỗi, platform nên cải tiến template/docs/automation để vấn đề không tiếp tục tái diễn.

### 23.6. Phát hành có kiểm soát

Các nhóm có thể deploy những thay đổi **backward-compatible** riêng theo nhịp service, dùng flag để tách deploy khỏi release, mở cho nhóm người học phù hợp và quan sát **tính đúng checkpoint, phân quyền, reliability và task success**. Đường xử lý incident phải rõ; không buộc mọi nhóm có cùng “ngày release” nếu về mặt kỹ thuật không cần thiết.

### 23.7. Kết quả minh họa sau vài vòng cải tiến

| Metric | Trước thử | Sau thử | Cách đọc |
| --- | ---: | ---: | --- |
| Median time-to-staging của service cùng loại | 3 ngày | 2 giờ | Có thể giảm chờ; kiểm tra điều kiện tương đồng |
| Support requests tạo môi trường/tháng | 20 | 7 | Có thể tốt nếu người dùng vẫn báo vấn đề được |
| Median contract clarification time | 4 ngày | 1 ngày | Phù hợp giả thuyết trao đổi sớm |
| Migration bị chặn sát release | 3 lần | 1 lần | Mẫu nhỏ, chưa khẳng định xu hướng |
| Checkpoint production errors | Theo baseline | Theo cửa sổ mới | Guardrail bắt buộc, cần số liệu thật |
| Tỷ lệ người học mở đúng bài | Chưa biết | Theo exposure | Outcome sản phẩm, không suy từ platform metrics |

Con số là **giả định giảng dạy**, không phải thống kê đã kiểm chứng. Nếu các story ở kỳ sau dễ hơn, time-to-staging hoặc cycle time cũng có thể giảm vì lý do khác.

### 23.8. Hai loại cải tiến khác nhau

Platform self-service tốt hơn nhưng học viên vẫn không nhận ra nút “Học tiếp” trên mobile là **vấn đề sản phẩm/UX**. Ngược lại, người học thích tính năng nhưng staging liên tục hỏng là **vấn đề nền tảng/dòng kỹ thuật**. Không đánh đồng hai loại outcome, nhưng cần xem chúng ảnh hưởng nhau ra sao.

## 24. Nhịp phối hợp tối thiểu để khép vòng phản hồi

| Thời điểm | Tương tác | Đầu ra |
| --- | --- | --- |
| **Trước khi làm lát cắt phụ thuộc** | Producer/consumer và specialist nếu rủi ro đòi | Contract, owner, điều kiện sẵn sàng |
| **Trong lúc phát triển** | Trao đổi theo blocker/age, CI feedback | Gỡ phụ thuộc sớm, code tích hợp được |
| **Trước rollout** | Owner sản phẩm, service, platform và incident | Kế hoạch, guardrails, trách nhiệm |
| **Sau rollout** | Product Owner, Developers và bên liên quan | Outcome, lỗi và điều chỉnh backlog |
| **Khi cải tiến hệ thống** | Review support demand, queues, developer experience | Giảm phụ thuộc, nâng self-service |

Không phải tất cả đều là **cuộc họp cố định**. Nhiều tình huống chỉ cần contract versioned, notification, dashboard và support ticket có owner. Họp đồng bộ dành cho quyết định phức tạp, bất định cao hoặc incident cần hợp tác ngay.

### Phối hợp chặt vẫn có lúc cần

Khi nhiều nhóm thay đổi data/identity không giữ được tương thích trong giai đoạn chuyển đổi, cần phối hợp sâu **trình tự migration, quyền, thời điểm và phục hồi**. Đừng hiểu “ít họp” thành “mỗi team tự deploy những phần không tương thích mà không hỏi ai”.

## 25. Scrum nhiều nhóm: phối hợp quanh Product Goal và Increment

Scrum không yêu cầu mọi thành viên làm tất cả mọi thứ hoặc mọi đội độc lập hoàn toàn về kỹ thuật. Khi **nhiều Scrum Teams cùng phát triển một sản phẩm**, các nhóm cần chia sẻ **Product Goal, Product Backlog, Product Owner và Definition of Done**, đồng thời tạo **Increment tích hợp** có thể sử dụng.

### Phân biệt hai tình huống tổ chức

| Tình huống | Đặc điểm | Cách phối hợp phù hợp |
| --- | --- | --- |
| **Nhiều Scrum Teams trên một sản phẩm** | Cùng mục tiêu và backlog sản phẩm | Cùng hiểu Product Goal/DoD, phối hợp PBIs và tích hợp xuyên nhóm |
| **Nhiều sản phẩm có phụ thuộc** | Có mục tiêu và backlog khác nhau, service contracts giữa các sản phẩm | Phân quyền product ownership, service interface, chính sách hỗ trợ và trade-off cross-product |

Không nên vì “cần đồng bộ Agile” mà tạo một Product Backlog khổng lồ bao gồm cả các sản phẩm thật sự độc lập. Ngược lại, nếu đang cùng tạo **một Increment**, không được giả định mỗi team xong riêng là sản phẩm đã sẵn sàng.

### Product Owner và platform owner có mâu thuẫn?

Một platform capability có thể là **sản phẩm nội bộ** với người chịu trách nhiệm ưu tiên và mục tiêu riêng. Product Owner của sản phẩm học viên quyết định giá trị/ưu tiên của **sản phẩm họ**, không tự nhiên có quyền điều khiển lịch làm việc của platform team. Hai bên phải trao đổi theo **service interface, ưu tiên có căn cứ, rủi ro và capacity**.

Nếu platform team cũng vận hành bằng Scrum, họ có thể có Product Goal/Backlog và Sprint Goal của mình. Nhưng nếu **tổ chức xác định tất cả cùng phát triển một sản phẩm**, cần tuân thủ cách thiết kế trách nhiệm Scrum phù hợp thay vì tùy tiện tách ownership mâu thuẫn.

### Các sự kiện Scrum giúp gì?

| Sự kiện | Câu hỏi liên nhóm nên xuất hiện khi cần |
| --- | --- |
| **Sprint Planning** | Có phụ thuộc quyết định/API/môi trường nào đe dọa Sprint Goal không; cách xử lý đã rõ? |
| **Daily Scrum** | Điều gì đang cản trở tiến triển tới Sprint Goal; Developers có thể điều chỉnh kế hoạch/gỡ phụ thuộc? |
| **Sprint Review** | Increment tích hợp có tạo giá trị? Những vấn đề platform/contract có làm thay đổi backlog? |
| **Sprint Retrospective** | Handoff, wait, pipeline và cộng tác cần cải tiến gì, đo kết quả ra sao? |

**Không phải mọi Scrum Team phải tham dự toàn bộ sự kiện của mọi team khác.** Chọn đúng các tương tác theo phụ thuộc; nếu cần xem thay đổi cross-team, có thể dùng **đồng bộ ngắn hoặc tích hợp liên tục**, không mặc định thêm một tầng quản trị báo cáo.

### Khi chuyên gia dùng chung tham gia Sprint

Nếu một Sprint Goal phụ thuộc vào review migration từ specialist, team nên làm rõ **đầu ra cần, mức rủi ro, availability, lead time và phương án khi blocked** trước khi tự cam kết kết quả quá mạnh. Không biến specialist thành “người nhận mọi PBI” nếu họ không thuộc Scrum Team ấy và không chịu trách nhiệm với mục tiêu đó.

### Sprint Review không phải cổng triển khai bắt buộc

Increment đáp ứng Definition of Done có thể được giao trước Sprint Review khi phù hợp. Platform hỗ trợ **CI/CD, test và khả năng deploy**, còn quyết định exposure giá trị do người chịu trách nhiệm sản phẩm và chính sách rủi ro. Không đồng nhất “đã deploy” với “đã tạo outcome”.

## 26. Kanban: quản lý luồng hỗ trợ và việc phụ thuộc

Kanban giúp mô tả **Definition of Workflow**, trực quan hóa công việc, kiểm soát WIP, quản lý work item và cải tiến flow. Một nhóm chuyên gia/Platform thường có dòng nhu cầu không đều, vì vậy cần đặc biệt chú ý **work item age, hàng đợi và lớp dịch vụ**.

### Hai workflow có thể liên quan

~~~text
Product team workflow:
  Ready → Developing → Verify → Done
                  |
             Blocked: cần contract

Shared service workflow:
  Request accepted → Triage → Working → Resolved

Liên hệ:
  Request resolved mới hữu ích nếu product item được bỏ chặn
  và có thể tiến tới Done đúng chất lượng.
~~~

Nếu platform đóng support ticket với kết quả “đã hướng dẫn” nhưng team tiêu thụ vẫn không tạo môi trường được, **support resolution time** có thể đẹp nhưng **time-to-unblock** không cải thiện. Phải đo kết quả ở **cả hai luồng** khi cần.

### WIP và pull policies

Ví dụ một nhóm platform có WIP limit 3 cho implementation requests, một nhóm consultation theo lịch, và một đường incident riêng. Số 3 chỉ minh họa. Khi WIP đầy, nhóm cần **hoàn tất, chia nhỏ, gỡ blocker, phối hợp hoặc đưa ra trade-off**, không tự giấu request và coi hệ thống đã ổn.

### Work item age hỗ trợ phản ứng sớm

Nếu SLE cho support thường lệ có xác suất 85% hoàn tất tư vấn ban đầu trong ba ngày, một request đã **2,5 ngày** có thể cần kiểm tra ngay: còn thiếu dữ liệu, bị gián đoạn hay chờ quyền quyết định? Đây không phải bằng chứng chắc chắn trễ; nó là tín hiệu **nên quản lý flow chủ động**.

### Đừng tối ưu một hàng đợi bằng cách làm hàng đợi khác dài ra

Ví dụ platform yêu cầu mọi công việc phải qua review của họ; queue platform có thể gọn vì họ trả lời rất nhanh, nhưng nhóm sản phẩm vẫn mất thêm hai vòng chuyển giao. Cần nhìn **cycle time end-to-end, số lần handoff, rủi ro và chất lượng**.

## 27. XP: kỹ thuật giảm nhu cầu phối hợp lặp lại

Extreme Programming (XP) cung cấp những thực hành làm **thay đổi nhỏ, tích hợp sớm và nhận phản hồi kỹ thuật nhanh**, giảm mức độ cần đồng bộ thủ công trong nhiều trường hợp.

| Thực hành XP/kỹ thuật | Tác động đối với phối hợp nhiều nhóm | Điểm cần tránh |
| --- | --- | --- |
| **Continuous Integration** | Contract và integration breaks được phát hiện sớm | Chỉ chạy build mà bỏ API/security checks quan trọng |
| **Test-first/TDD** | Quy tắc và kỳ vọng được thể hiện thành kiểm tra | Tự viết expectation khi chưa thống nhất nghiệp vụ |
| **Pair programming** | Chuyển giao hiểu biết giữa người chuyên môn và team | Chuyên gia pair mãi không có kế hoạch team tự làm |
| **Refactoring** | Ranh giới và interfaces đơn giản hơn qua thời gian | Thay interface phá tương thích không có migration plan |
| **Small releases** | Chia nhỏ thay đổi, khoanh vùng lỗi và học sớm | Dồn nhiều “small commits” vào một release chưa tích hợp |
| **Simple design** | Giảm cognitive load và chi phí phối hợp | Đơn giản hóa đến mức bỏ quy tắc an toàn bắt buộc |

### Chia theo vertical slice thay vì chia theo phòng ban

Một anti-pattern là “team frontend làm toàn bộ UI, team backend làm toàn bộ API, team QA chờ cuối, platform deploy một lần”. Khi mỗi story phải đi qua **nhiều hàng đợi chuyên môn**, feedback bị trì hoãn.

Cân nhắc chia thành những **lát cắt end-to-end nhỏ** để Developers có khả năng thực hiện phần chính của hành trình, với những năng lực dùng chung phục vụ dưới dạng **contract, tool và hỗ trợ tập trung theo rủi ro**. Điều này không yêu cầu xóa mọi ranh giới chuyên môn; nó giảm handoff không cần thiết cho giá trị nhỏ.

### Test automation để giảm phê duyệt lặp

Chẳng hạn cùng một policy “không trả checkpoint tài khoản khác” có thể được **mã hóa thành API test** chạy ở CI. Security specialist vẫn review threat model cho thay đổi rủi ro mới, nhưng không cần tự thao tác cùng checklist thủ công hàng chục lần cho đường triển khai chuẩn. Điều này bảo vệ chất lượng đồng thời giảm tải chuyên gia.

## 28. Chọn mô hình điều phối nào trong bối cảnh thực?

Không có mô hình “tập trung” hoặc “phi tập trung” luôn đúng. Quyết định phụ thuộc loại chuyên môn, chi phí lặp lại, mức rủi ro, quy mô tổ chức, độ ổn định nhu cầu và quyền tự chủ của nhóm sản phẩm.

| Bối cảnh | Mẫu tương tác nên cân nhắc | Vì sao? |
| --- | --- | --- |
| Nhiều team cần tạo môi trường giống nhau mỗi ngày | **Platform self-service** | Nhu cầu lặp, có thể đóng gói và chuẩn hóa |
| Team mới thiếu hiểu biết authorization | **Facilitating/coaching** | Cần tăng năng lực, không giải hộ mãi |
| Hai service phải thay một contract phức tạp | **Collaboration có timebox** | Bất định cao, cần cùng thiết kế |
| Một thuật toán đặc thù cần chuyên gia hiếm | **Complicated-subsystem owner với interface** | Tránh phân tán kiến thức sâu không hiệu quả |
| Đổi schema ảnh hưởng nhiều consumer | **Contract + compatibility plan + specialist review theo rủi ro** | Cần an toàn và rollout phối hợp |
| Production incident ảnh hưởng dữ liệu người dùng | **Incident response xuyên team** | Cần bảo vệ người dùng ngay, không đợi backlog |
| Nhu cầu support lặp và có hướng xử lý ổn định | **Tài liệu + automation + self-service** | Loại bỏ nguyên nhân ticket thay vì tăng hỗ trợ |
| Một số yêu cầu cố định nhưng hiếm | **Consultation được chuẩn bị và hẹn trước** | Xây platform product riêng có thể không đáng chi phí |

### Quy trình chọn trong sáu câu hỏi

1. **Người dùng nội bộ muốn làm gì và vì sao?** Mô tả job-to-be-done cụ thể.
2. **Nhu cầu có lặp, ổn định và phù hợp tự động hóa không?**
3. **Rủi ro và thẩm quyền nào phải được bảo vệ?**
4. **Nếu hỗ trợ trực tiếp, team tiêu thụ có học được cách tự làm lần sau không?**
5. **Interface kỹ thuật/tổ chức có thể rõ hơn để giảm cuộc họp không?**
6. **Đo gì để biết tổng flow, quality và product outcome tốt hơn, chứ không chỉ platform ticket nhanh hơn?**

Một capability mới có thể bắt đầu bằng **collaboration**, đi qua **facilitation** và ổn định thành **X-as-a-Service**. Nếu nhu cầu thay đổi bất thường, không cố ép self-service bằng giao diện quá cứng.

## 29. Các phản mẫu thường gặp

### 29.1. “Platform là nhóm nhận mọi ticket”

Platform bị kéo vào mọi request tùy ý, không còn capacity nâng self-service. **Cải tiến:** service catalog, intake phân loại, product backlog rõ và phân biệt support với capability investment.

### 29.2. “Chuyên gia dùng chung phải duyệt mọi PR”

Một người thành hàng đợi bắt buộc ngay cả khi rủi ro thấp. **Cải tiến:** review dựa trên rủi ro, mẫu/CI checks và coaching, vẫn duy trì phê duyệt bắt buộc nếu có căn cứ.

### 29.3. “Mọi request đều P0”

Không còn khả năng dự báo, incident bị lẫn với tư vấn bình thường. **Cải tiến:** severity/service class có điều kiện, trade-off công khai và quyền quyết định rõ.

### 29.4. “Platform tạo công cụ, các team tự tìm cách dùng”

Có sản phẩm kỹ thuật nhưng thiếu tài liệu, onboarding và hỗ trợ. **Cải tiến:** đo self-service task success và trải nghiệm người dùng nội bộ, xem service interface gồm cả vận hành.

### 29.5. “Có catalog là có self-service”

Catalog chỉ liệt kê link, cuối cùng vẫn phải nhắn người quen để cấp quyền. **Cải tiến:** quan sát tác vụ thực tế, tự động hóa đường chuẩn, lỗi và escalation dễ hiểu.

### 29.6. “Nhiều team adoption nghĩa là platform tốt”

Adoption do bắt buộc có thể che UX tệ và lỗi. **Cải tiến:** ghép adoption với time-to-task-success, reliability, feedback và chất lượng.

### 29.7. “Đóng ticket nghĩa là team tiêu thụ hết bị chặn”

Support bảo đã hướng dẫn nhưng môi trường vẫn lỗi. **Cải tiến:** thống nhất điều kiện resolved/unblocked và theo dõi kết quả cả hai phía.

### 29.8. “Mọi thứ dùng cùng SLE ba ngày”

Incident, tư vấn 15 phút và capability hai tháng khác nhau. **Cải tiến:** phân loại dịch vụ; công bố SLE, response và resolution đúng đơn vị.

### 29.9. “Càng nhiều cuộc họp liên nhóm càng Agile”

Lịch họp dày nhưng thiếu owner/contract. **Cải tiến:** ưu tiên interface/test/board minh bạch, họp khi có quyết định thực.

### 29.10. “Mỗi team tự chủ nên không cần tích hợp sớm”

Phát hiện lỗi hợp đồng dữ liệu khi production đã chạy. **Cải tiến:** contract tests, compatibility và feedback tích hợp liên tục.

### 29.11. “Tất cả service phải deploy cùng ngày”

Release train lớn tăng rủi ro kết hợp. **Cải tiến:** thay đổi backward-compatible, flags và rollout độc lập khi khả thi; phối hợp chặt khi thật sự cần.

### 29.12. “Platform sở hữu toàn bộ lỗi production”

Che ranh giới trách nhiệm và làm platform thành người sửa mọi logic nghiệp vụ. **Cải tiến:** service ownership, incident roles và runbook rõ.

### 29.13. “Chỉ cần xếp hạng Product Owners bằng điểm ưu tiên”

Điểm số tùy tiện có thể che nghĩa vụ an toàn và chi phí chờ thật. **Cải tiến:** tiêu chí minh bạch, rủi ro và quyền trade-off ở cấp thích hợp.

### 29.14. “Tập trung specialist làm giảm chi phí vì ai cũng bận 100%”

Không còn năng lực cho incident, mentoring hay self-service, làm wait time tăng. **Cải tiến:** WIP, đệm năng lực, hỗ trợ dự phòng và theo dõi tải bền vững.

### 29.15. “Chỉ người đó mới biết, thế mới bảo đảm chất lượng”

Single point of failure kéo dài. **Cải tiến:** pairing, docs, rotation, kiến thức chung và interface được kiểm chứng; vẫn giữ review chuyên sâu cho ngoại lệ.

### 29.16. “Đổi tổ chức trước rồi mới định nghĩa sản phẩm”

Tạo team platform, enabling hoặc subsystem không dựa vào nhu cầu thật. **Cải tiến:** bắt đầu từ value stream, cognitive load, phụ thuộc và mục tiêu người dùng.

### 29.17. “Self-service nghĩa là ai cũng có mọi quyền”

Tạo nguy cơ production, secrets và dữ liệu cá nhân. **Cải tiến:** đường tự phục vụ có policy, least privilege, audit và escalation.

### 29.18. “Platform KPI tốt thì sản phẩm người dùng chắc chắn tốt”

Deploy nhanh chưa nói nút Học tiếp được học viên sử dụng có ích. **Cải tiến:** đọc song song developer experience, flow, quality và product outcome.

### 29.19. “Sự cố sẽ được xử lý trong hàng đợi tư vấn”

Một sự cố mất dữ liệu bị trì hoãn vì rule FIFO. **Cải tiến:** incident severity/on-call, bảo vệ người dùng ngay và thông báo trade-off các việc bị gián đoạn.

### 29.20. “Không có ticket thì không có nhu cầu”

Người dùng nội bộ có thể bỏ cuộc hoặc tự dùng workaround rủi ro. **Cải tiến:** nghiên cứu tác vụ, quan sát onboarding, khảo sát có bối cảnh và kênh feedback dễ dùng.

## 30. Lộ trình cải tiến phối hợp nhiều nhóm theo từng bước

Không cần xây một platform lớn rồi mới cho các nhóm dùng. Một lộ trình có thể bắt đầu bằng **hiểu phụ thuộc đang gây mất giá trị**, giảm nhu cầu lặp và mở rộng dựa trên bằng chứng.

### Bước 1 — Quan sát luồng giá trị hiện tại

Chọn một hành trình thật, ví dụ “Học viên nhấn Học tiếp và mở đúng bài”. Từ khi Product Backlog item được bắt đầu tới lúc Increment đạt chuẩn, ghi:

- Nhóm nào sở hữu từng service/interface.
- Những nơi phải chờ chuyên gia, quyền hoặc môi trường.
- Những thao tác lặp lại có thể tự phục vụ.
- Những lỗi tích hợp, chất lượng hoặc security phát hiện muộn.
- Các kênh không chính thức như chat riêng hoặc một người duy nhất biết làm.
- Các loại thay đổi và incident xảy ra trong cửa sổ quan sát.

**Kết quả:** một bản đồ value stream nhỏ và 2–3 giả thuyết về điểm nghẽn, không phải một sơ đồ tổ chức mới được quyết định từ đầu.

### Bước 2 — Làm rõ ownership và service interface

Với một capability thường gặp, công bố **owner, người dùng nội bộ, đường tự phục vụ, giới hạn quyền, chính sách, hỗ trợ và escalation**. Đặt một tập ví dụ tác vụ để kiểm tra interface.

**Kết quả:** những người cần capability biết **tự làm gì** và **gặp ai khi rủi ro/ngoại lệ**. Không chỉ có một trang wiki chưa ai dùng.

### Bước 3 — Tách support khỏi capability investment

Phân loại request, dùng WIP/SLE có cơ sở cho luồng thường lệ, có incident policy riêng. Chọn một loại request lặp lại để **tự động hóa hoặc chuyển giao kỹ năng**.

**Kết quả:** support không bị bỏ quên và platform vẫn có năng lực giải quyết **nguyên nhân gây demand**.

### Bước 4 — Thử một golden path có phạm vi

Ví dụ chỉ hỗ trợ **một mẫu Java service** với CI, staging và logging chuẩn. Có tài liệu hướng dẫn, mẫu lỗi và đường phản hồi. Quan sát Developers mới tự làm, đo thời gian tới môi trường hoạt động, số lần cần specialist can thiệp và chất lượng.

**Kết quả:** một sản phẩm nội bộ đủ dùng và có feedback, không chỉ bản demo đẹp.

### Bước 5 — Giảm phụ thuộc contract và kiến thức

Tạo versioned API contracts, automated checks, coaching/office hours và ownership rõ cho những chỗ có rủi ro. Ghi lại những trường hợp **không nên chuyển thành self-service** vì cần chuyên môn/duyệt thực.

**Kết quả:** thay đổi thường lệ có thể giao nhanh, còn ngoại lệ được hỗ trợ đúng người đúng lúc.

### Bước 6 — Đo toàn hệ thống và điều chỉnh

So trước/sau trên **cùng ranh giới và loại công việc**; xem thời gian bị blocked, self-service task success, reliability, product lead time, lỗi, sức khỏe nhóm và outcome người học. Nêu giới hạn suy luận nhân quả khi có thay đổi môi trường/nhân sự/mẫu.

**Kết quả:** giữ, sửa hoặc bỏ chính sách; chọn một vấn đề tiếp theo từ dữ liệu. Đây là **continuous improvement**, không phải “lên platform v2” chỉ vì roadmap đã vẽ.

## 31. Workshop 75–90 phút: thiết kế điều phối shared specialists và platform

Đây là **bài thực hành gợi ý**, không phải sự kiện bắt buộc của Scrum/Kanban hoặc tiêu chuẩn tổ chức.

**Tình huống:** Năm nhóm sản phẩm cùng dùng một chuyên gia bảo mật và một nhóm platform ba người. Thời gian từ lúc story bắt đầu tới lúc đạt DoD tăng, đặc biệt ở chỗ chờ staging và kiểm tra quyền. Platform nhận 40 ticket/tháng; 24 ticket hỏi về tạo môi trường, 10 yêu cầu tư vấn kiến trúc thường lệ và 6 yêu cầu khác. Một sự cố dữ liệu nghiêm trọng gần đây phải xử lý khẩn.

| Bước | Thời lượng gợi ý | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Xác định giá trị** | 10 phút | Chọn hành trình người học và một Increment đang bị chặn | Outcome và value stream có ranh giới |
| **2. Phân loại phụ thuộc** | 10 phút | Tách kiến thức, quyền, tool, contract và incident | Dependency map và owners |
| **3. Chọn interaction mode** | 15 phút | Self-service, facilitation, collaboration hay subsystem interface | Mỗi nhu cầu có cách phục vụ phù hợp |
| **4. Viết service interface** | 15 phút | Catalog entry cho staging/authorization | Entry point, policy, support, escalation |
| **5. Ưu tiên và WIP** | 10 phút | Phân loại standard/expedite/capability, trade-off | Intake và cách xử lý khi hàng đợi đầy |
| **6. Chọn metric/guardrails** | 10–15 phút | Đo time-to-unblock, self-service và quality | Thí nghiệm có baseline và giới hạn |
| **7. Đọc kết quả giả định** | 10–15 phút | Xem số sau thử, quyết định giữ/sửa/dừng | Decision log với owner và mốc xem lại |

### Dữ liệu để thảo luận

Giả sử 24 ticket tạo môi trường có cùng lỗi cấu hình và được xử lý thủ công trong **20 phút thao tác mỗi ticket** (không kể chờ). Khi tạo được self-service phù hợp, có thể **giảm một phần** tải thao tác thường lệ:

\[
24\times20=480\text{ phút}=8\text{ giờ thao tác/tháng}.
\]

Con số 8 giờ **không phải toàn bộ lợi ích**: giá trị lớn có thể là **giảm thời gian chờ của các nhóm sản phẩm**; cũng không phải toàn bộ chi phí vì xây/bảo trì template, onboarding và support vẫn tiêu tốn năng lực.

### Quyết định cần thảo luận

1. Nhu cầu 24 ticket lặp lại nên đi theo self-service, office hours hay tuyển thêm người nhận ticket? Vì sao?
2. Chuyên gia bảo mật nên giúp các nhóm viết quyền đúng qua coaching hay duyệt toàn bộ endpoint?
3. Incident dữ liệu khẩn có đi theo cùng hàng đợi standard không?
4. Ai quyết định khi một Product Owner muốn capability riêng nhưng platform backlog có việc bảo mật quan trọng?
5. Đường nào giúp biết service catalog đã **thực sự dùng được**?
6. Nếu support tickets giảm nhưng Developers bắt đầu sử dụng workaround thiếu quyền, đánh giá cải tiến thế nào?
7. Vì sao phải đo thời gian bị blocked của product items, không chỉ số ticket platform?

**Tiêu chí đạt:** Nhóm mô tả được **ít nhất một self-service candidate, một trường hợp chuyên gia phải cộng tác thật, một chính sách intake/incident, trách nhiệm và một phép đo kiểm chứng giá trị**.

## 32. Bài tập tự kiểm tra và gợi ý

### Bài tập A — Nhận dạng phụ thuộc

Xếp các tình huống vào **kiến thức, quyền quyết định, môi trường/tooling, hợp đồng API, dữ liệu, vận hành/incident hoặc đầu tư capability**:

1. Developers phải đợi một người tạo namespace thử mỗi lần có service mới.
2. Hai service hiểu khác nhau về trạng thái “khóa học hoàn tất”.
3. Một nhóm muốn biết cách triển khai threat modeling phù hợp.
4. Schema thay đổi khiến app cũ không đọc được checkpoint.
5. Production phát hiện người học bị trả sai dữ liệu tài khoản.
6. Ba nhóm đề nghị xây feature flag service dùng chung.

**Gợi ý:** (1) môi trường/tooling; (2) hợp đồng và quy tắc nghiệp vụ; (3) kiến thức; (4) dữ liệu/contract; (5) incident/an toàn; (6) capability investment. Một tình huống có thể chạm nhiều loại; phải chỉ rõ **hành động nào giúp bỏ chặn**.

### Bài tập B — Chọn interaction mode

Một nhóm mới chưa biết cách thiết kế authorization cho API; nhóm khác chỉ muốn tạo staging theo mẫu đã có; hai nhóm còn lại cần đổi schema không tương thích.

Hãy chọn giữa **facilitation, X-as-a-Service và collaboration** cho từng nhu cầu, giải thích **điều kiện kết thúc** và **khi nào đổi mode**.

**Gợi ý:** Authorization thiếu năng lực → coaching có timebox; staging thường lệ → tự phục vụ; schema không tương thích → collaboration để thống nhất và chuyển sang contract versioned khi ổn định.

### Bài tập C — Đọc số liệu self-service

Trong hai tuần có 120 lần bắt đầu tác vụ tạo staging hợp lệ. 90 lần hoàn tất, trong đó 75 lần không cần can thiệp của platform. Có 15 lần hoàn tất nhưng phải gọi chuyên gia và 30 lần chưa xong.

1. Tỷ lệ **tác vụ hoàn tất** là bao nhiêu?
2. Tỷ lệ **self-service success trên tổng tác vụ** là bao nhiêu?
3. Tại sao không nên báo 75/90 như “tỷ lệ thành công self-service của mọi tác vụ”?
4. Có thể kết luận bao nhiêu **Developers** tự chủ không?

**Gợi ý:** 90/120 = 75% tác vụ hoàn tất; 75/120 = 62,5% tác vụ tự hoàn tất trong mẫu. 75/90 = 83,3% **trong số tác vụ đã hoàn tất**, bỏ qua những lần thất bại; chưa biết số người duy nhất.

### Bài tập D — Ưu tiên yêu cầu

Platform team có:

- Một incident mất checkpoint của nhóm học viên.
- Một câu hỏi cách sử dụng CLI đã có tài liệu.
- Một yêu cầu xây dashboard nội bộ mới.
- Một migration liên quan ba consumer, có hạn thực theo hợp đồng.
- Một việc cập nhật runtime có cảnh báo bảo mật.

Hãy trình bày **nguyên tắc triage**, không chỉ xếp 1–5 một cách tùy tiện. Ai có quyền quyết định trade-off? Khi incident làm gián đoạn, thông báo gì với những người đang chờ?

**Gợi ý:** Incident/security và nghĩa vụ bắt buộc theo policy, không chung điểm số với feature mong muốn; có kênh self-service cho câu hỏi thường lệ; làm rõ chi phí chờ và tác động của các mốc thực.

### Bài tập E — SLE không phải SLA

Một nhóm specialist nói “85% yêu cầu tư vấn thường lệ có kết quả ban đầu trong ba ngày làm việc”. Một yêu cầu đã chờ 2,5 ngày; một yêu cầu khác là incident production.

1. Yêu cầu đầu đã chắc chắn trễ chưa?
2. Work item age có ích thế nào?
3. Incident có nên chờ cùng SLE ba ngày không?
4. Vì sao first response và time-to-unblock khác nhau?

**Gợi ý:** SLE là kỳ vọng xác suất; xem blocker/tiến triển chủ động. Incident theo policy riêng. Trả lời “đã nhận” chưa giúp team tiếp tục.

### Bài tập F — Contract và phiên bản

Producer muốn xóa trường checkpoint cũ vào thứ Sáu, nhưng mobile app chưa cập nhật và có người dùng offline nhiều ngày.

Hãy thiết kế:

- Điều gì phải được xác minh trước khi xóa trường?
- Contract test nào giúp phát hiện consumer chưa tương thích?
- Có thể dùng expand–migrate–contract thế nào?
- Ai cần tham gia quyết định và giám sát?
- Rollback code liệu có khôi phục dữ liệu bị xóa không?

**Gợi ý:** Chú ý thời gian cập nhật mobile và job nền, backward compatibility, giữ schema cũ trong giai đoạn chuyển tiếp, dữ liệu và phương án phục hồi.

### Bài tập G — Scrum nhiều nhóm

Ba Scrum Teams cùng làm **một sản phẩm** nhưng mỗi nhóm có Product Backlog và Definition of Done riêng. Một team gọi Done khi API merged, team khác khi UI demo được; Increment tổng vẫn không kiểm thử được.

1. Có điểm nào không phù hợp hướng dẫn Scrum cho nhiều nhóm trên một sản phẩm?
2. Cần làm rõ ownership và điều kiện Done thế nào?
3. Một platform team cung cấp CI/CD có thay Product Owner quyết định giá trị không?
4. Các phụ thuộc nên được phát hiện trong những thời điểm nào?

**Gợi ý:** Cùng Product Goal, Product Backlog, Product Owner, DoD cho một sản phẩm và có Increment tích hợp; platform hỗ trợ năng lực kỹ thuật, không quyết định giá trị thay Product Owner.

### Bài tập H — Tìm anti-pattern sau khi thêm platform

Sau sáu tháng, số ticket hỗ trợ giảm 50% nhưng Develop­ers phàn nàn tài liệu khó dùng, nhiều người đang giữ secret cục bộ và pipeline thường xuyên bị retry vì flaky tests.

1. Có thể tuyên bố platform thành công chỉ từ số ticket không?
2. Metrics và phương pháp nghiên cứu nào cần bổ sung?
3. Những guardrails nào đang có nguy cơ xấu?
4. Một thí nghiệm cải tiến nhỏ, có thời hạn và owner là gì?

**Gợi ý:** Quan sát task success, time-to-first-use, developer feedback, secrets policy và pipeline reliability. Giảm ticket có thể do người dùng bỏ cuộc hoặc làm workaround.

### Bài tập I — Đánh giá shared specialist

Một security specialist bị lên lịch review toàn bộ PR của bảy team. Họ không còn thời gian threat modeling cho tính năng mới và phải làm thêm giờ.

Hãy đề xuất:

- Điều kiện nào **bắt buộc** review chuyên sâu?
- Kiểm tra nào có thể tự động hóa theo policy?
- Kỹ năng nào cần chuyển giao qua coaching/pairing?
- Chỉ số nào đo sự cải thiện mà không giảm mức bảo mật?
- Làm gì khi specialist vắng mặt?

**Gợi ý:** Phân tầng rủi ro, authorization tests và policy-as-code cho đường chuẩn, review ngoại lệ; có backup/knowledge-sharing, đo time-to-unblock và security incidents, không dùng số PR đã duyệt làm năng suất.

### Bài tập J — Chọn đầu tư giữa self-service và tăng người hỗ trợ

Có 300 request/tháng: 220 request tạo môi trường giống nhau, 50 request tư vấn sâu và 30 request liên quan sự cố/nghiên cứu. Team nhỏ liên tục quá tải.

1. Loại request nào có khả năng **tự phục vụ hóa**?
2. Loại nào phù hợp **facilitation hoặc chuyên môn sâu**?
3. Cần tính **chi phí xây/duy trì** và giá trị giảm wait như thế nào?
4. Nếu tự động hóa 220 request nhưng vẫn cần người hỗ trợ ngoại lệ, có phải thất bại không?

**Gợi ý:** Nhu cầu lặp có oracle rõ phù hợp automation; tư vấn sâu có thể cần người. Không đặt mục tiêu “support tickets về 0”; ưu tiên **consumer tự hoàn tất tác vụ đúng chuẩn**.

## 33. Checklist phối hợp shared specialists và platform teams

- [ ] Đã xác định **dòng giá trị và người dùng cuối** mà phối hợp nhiều nhóm cần phục vụ.
- [ ] Phân biệt **một sản phẩm nhiều team** với **nhiều sản phẩm liên kết** trước khi thiết kế backlog/ownership.
- [ ] Mọi phụ thuộc quan trọng có **requester, provider, đầu ra xác nhận và điều kiện giải quyết**.
- [ ] Các phụ thuộc được phân loại: kiến thức, quyết định, môi trường, API, dữ liệu, phát hành, vận hành.
- [ ] Không dùng “phải họp nhiều hơn” làm lời giải mặc định.
- [ ] Chuyên gia dùng chung không thành **single point of failure** cho tác vụ lặp.
- [ ] Shared specialist có đường **tư vấn/coaching/review rủi ro cao** và quyền escalation rõ.
- [ ] Các tương tác có thể chọn **self-service, facilitation hoặc collaboration có timebox**.
- [ ] Những capability lặp đã được xem xét cho **tự phục vụ và golden path**.
- [ ] Platform team có **người dùng nội bộ, product/capability backlog và phản hồi thực tế**.
- [ ] Service catalog nêu **mục đích, owner, cách dùng, policy, hỗ trợ, escalation và vòng đời**.
- [ ] Quyền, secrets và bảo mật được **bảo vệ trên đường tự phục vụ**.
- [ ] Ticket thường lệ, capability investment, enablement và incident **không bị trộn chính sách**.
- [ ] Có tiêu chí ưu tiên công khai xét giá trị, rủi ro, thời hạn thực, chi phí chờ và năng lực.
- [ ] Đã làm rõ **quyền quyết định cross-product** khi nhiều Product Owners cùng cần specialist/platform.
- [ ] WIP, work item age, throughput, cycle time được dùng **với định nghĩa workflow rõ**.
- [ ] SLE, first response, resolution, time-to-unblock và incident recovery **không bị nhầm**.
- [ ] Có năng lực xử lý khẩn, người trực và cách công bố tác động khi incident chiếm capacity.
- [ ] Thời gian nâng cấp self-service, bảo trì, tài liệu và độ tin cậy **không bị support nuốt hết**.
- [ ] Producer/consumer có **API contract và versioning** phù hợp khi tương tác lặp.
- [ ] Những thay đổi schema rủi ro cao có **migration/compatibility plan**, không xóa đường cũ sớm.
- [ ] Các service có trách nhiệm **code, deploy, quality, incident và product outcome** rõ.
- [ ] Có CI/contract/integration tests và khả năng quan sát đủ để phát hiện lỗi xuyên nhóm sớm.
- [ ] Không tự gọi từng team Done khi **Increment chung chưa tích hợp/đáp ứng DoD**.
- [ ] Nếu nhiều Scrum Teams trên một sản phẩm, cùng hiểu **Product Goal, Product Backlog, Product Owner và Definition of Done**.
- [ ] Khi dùng Kanban, workflow/feedback và service classes phù hợp loại nhu cầu thật.
- [ ] Các thực hành XP giúp **giảm lặp giao tiếp và hồi quy kỹ thuật**, không thay trao đổi nghiệp vụ cần thiết.
- [ ] Có guardrails về **dữ liệu, quyền riêng tư, bảo mật, reliability và sức khỏe nhóm**.
- [ ] Không đánh đồng số ticket đóng, adoption hay first response với **giá trị nền tảng**.
- [ ] Đo **self-service task success, time-to-unblock, reliability và trải nghiệm người dùng nội bộ**.
- [ ] Đo **flow và outcome người dùng cuối** để biết năng lực nền tảng có chuyển thành giá trị không.
- [ ] Có thời điểm **xem lại policies, docs, interaction modes và backlog** dựa trên bằng chứng.
- [ ] Mọi cải tiến quan trọng có **giả thuyết, owner, thời hạn đánh giá, điều kiện dừng và hành động tiếp theo**.

## 34. Tài liệu đọc tiếp và kết luận

- [Agile Manifesto](https://agilemanifesto.org/): giá trị hợp tác, giao phần mềm hoạt động và thích ứng bằng phản hồi.
- [The Scrum Guide](https://scrumguides.org/): trách nhiệm Scrum Team, Product Goal, Product Backlog, Product Owner, Definition of Done và nhiều Scrum Teams trên một sản phẩm.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, cycle time, work item age, Service Level Expectation và cải tiến dòng.
- Matthew Skelton và Manuel Pais, *Team Topologies: Organizing Business and Technology Teams for Fast Flow* (2019): các kiểu team và interaction modes; cách giảm cognitive load để tăng flow.
- Nicole Forsgren, Jez Humble và Gene Kim, *Accelerate: The Science of Lean Software and DevOps* (2018): năng lực giao phần mềm, chất lượng và kết quả tổ chức.
- Gene Kim, Jez Humble, Patrick Debois và John Willis, *The DevOps Handbook* (2016): flow, feedback và cải tiến giữa phát triển – vận hành.
- Jez Humble và David Farley, *Continuous Delivery* (2010): pipeline, tự động hóa, kiểm thử và khả năng giao an toàn.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): CI, TDD, refactoring, pairing và small releases.
- [DORA](https://dora.dev/): nghiên cứu và tài nguyên về hiệu suất giao phần mềm, độ ổn định và cải tiến liên tục.
- [Google SRE Books](https://sre.google/books/): SLO, trách nhiệm vận hành, monitoring và xử lý sự cố dịch vụ.

**Kết luận:** Điều phối chuyên môn dùng chung và nhóm hỗ trợ nền tảng không phải bài toán lập thêm một tầng quản lý hoặc dồn toàn bộ yêu cầu vào một hàng đợi. Trọng tâm là **làm rõ ranh giới trách nhiệm, tương tác theo đúng nhu cầu, giảm phụ thuộc lặp và tạo năng lực tự phục vụ an toàn**.

**Chuyên gia dùng chung** cần tập trung vào những vấn đề thật sự cần chiều sâu, đồng thời **lan tỏa tri thức và giảm phụ thuộc cá nhân** qua coaching, mẫu và kiểm tra tự động. **Platform team** nên cung cấp năng lực như **sản phẩm nội bộ** có người dùng, giao diện, vòng đời, quality guardrails và bằng chứng về hiệu quả — không chỉ đóng thật nhiều ticket.

**Điểm cần nhớ:** Một cơ chế phối hợp chỉ được coi là tốt khi **các nhóm sản phẩm có thể giao Increment tích hợp, an toàn và nhận phản hồi người dùng sớm hơn**, không đánh đổi dữ liệu, bảo mật hay sức khỏe đội ngũ. Hãy quan sát nơi công việc đang chờ, chọn một phụ thuộc đáng giảm, thiết kế đúng interaction mode, đo kết quả và điều chỉnh. Đó là cách phối hợp nhiều nhóm hỗ trợ Agile **thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục**.
