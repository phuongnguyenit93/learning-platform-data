# Lập quyết định kiến trúc theo bối cảnh thay vì theo xu hướng

## 1. Vì sao đây là một kỹ năng kiến trúc cốt lõi?

Một quyết định kiến trúc là lựa chọn có ảnh hưởng đáng kể đến **cấu trúc hệ thống, thuộc tính chất lượng, chi phí thay đổi hoặc cách đội ngũ phát triển và vận hành phần mềm**. Ví dụ: chọn modular monolith hay microservices; dùng giao tiếp đồng bộ hay bất đồng bộ; lưu dữ liệu theo mô hình quan hệ hay tài liệu; triển khai trên máy ảo, container hay nền tảng managed; chia ranh giới module theo nghiệp vụ hay theo lớp kỹ thuật.

Những quyết định này thường có nhiều phương án **đều có thể hoạt động**, nhưng mỗi phương án trao đổi một số lợi ích lấy một số chi phí khác. Vì vậy, mục tiêu của người thiết kế không phải là tìm công nghệ “hiện đại nhất” hay “tốt nhất trong mọi trường hợp”, mà là chọn phương án **phù hợp nhất với vấn đề, ràng buộc, mức rủi ro và khả năng thực thi tại thời điểm ra quyết định**.

Ví dụ, một nhóm sáu người đang xây sản phẩm thử nghiệm cần ra mắt trong ba tháng có thể nhận lợi ích lớn từ một **modular monolith** có ranh giới nghiệp vụ rõ. Một tổ chức có hàng chục nhóm, nhiều vùng địa lý và yêu cầu triển khai độc lập thường có động cơ mạnh hơn để dùng các dịch vụ tách rời. Cả hai đều có thể là quyết định đúng trong bối cảnh tương ứng.

**Nguyên tắc trung tâm:** Bắt đầu từ *điều hệ thống phải đạt được* và *điều nhóm thực sự có thể vận hành*, sau đó mới chọn hình thức kiến trúc. Xu hướng công nghệ là nguồn ý tưởng và giả thuyết cần kiểm chứng, không phải bằng chứng tự thân.

### Quyết định kiến trúc khác lựa chọn thư viện thông thường ở đâu?

Một thay đổi nhỏ như đổi thư viện xử lý chuỗi có thể được cô lập và hoàn tác dễ. Ngược lại, chuyển từ một database thống nhất sang nhiều database theo dịch vụ có thể ảnh hưởng đến giao dịch, đồng bộ dữ liệu, khả năng truy vấn, bảo mật và quy trình phát hành. Một cách phân biệt thực dụng là hỏi:

- Quyết định có thay đổi **ranh giới trách nhiệm, sở hữu dữ liệu hoặc hợp đồng giữa các phần** không?
- Quyết định có ảnh hưởng đến các thuộc tính như **độ tin cậy, độ trễ, khả năng mở rộng, bảo mật hoặc khả năng bảo trì** không?
- Nếu sai, việc đảo ngược có tốn nhiều thời gian, dữ liệu, tiền hoặc công phối hợp giữa các nhóm không?
- Quyết định có tạo phụ thuộc dài hạn vào một nhà cung cấp, giao thức, nền tảng hoặc mô hình dữ liệu không?

Không phải mọi quyết định đều cần một buổi đánh giá lớn. Mức độ phân tích phải **tương xứng với hậu quả của sai lầm**.

## 2. “Theo bối cảnh” nghĩa là thu thập những thông tin gì?

Bối cảnh không chỉ là số request mỗi giây. Nó bao gồm mục tiêu kinh doanh, đặc điểm nghiệp vụ, ràng buộc, cách tổ chức nhóm và khả năng vận hành thực tế.

| Góc nhìn | Câu hỏi cần trả lời | Tác động đến quyết định |
| --- | --- | --- |
| Mục tiêu kinh doanh | Cần ra mắt nhanh, giảm chi phí, đáp ứng SLA, mở thị trường hay tăng tốc phát hành? | Xác định tiêu chí ưu tiên |
| Nghiệp vụ | Phần nào thay đổi thường xuyên? Dữ liệu nào phải nhất quán ngay? | Gợi ý ranh giới module/dịch vụ |
| Tải và hành vi sử dụng | Lưu lượng trung bình/đỉnh, số người dùng, kích thước dữ liệu, yêu cầu đọc/ghi? | Định hướng scale, cache, storage |
| Chất lượng dịch vụ | Mức trễ, lỗi, thời gian khôi phục, mức mất dữ liệu chấp nhận được? | Định hướng redundancy, timeout, recovery |
| Bảo mật và pháp lý | Dữ liệu nhạy cảm, vùng lưu trữ, kiểm toán, phân quyền, yêu cầu tuân thủ? | Đặt các điều kiện bắt buộc |
| Tổ chức | Có bao nhiêu nhóm, ai sở hữu phần nào, kinh nghiệm on-call thế nào? | Quyết định chi phí phối hợp và độ tự chủ |
| Công nghệ hiện tại | Codebase, dữ liệu, API, triển khai, khả năng quan sát và kỹ năng sẵn có? | Xác định chi phí chuyển đổi |
| Thời gian và ngân sách | Khi nào cần chạy thật? Có bao nhiêu người, tiền và thời gian cho migration? | Loại bỏ phương án không khả thi |

Một giải pháp hợp lý phải thỏa cả **yêu cầu hiện tại** và khả năng thích ứng với thay đổi có cơ sở. Không nên biến mọi dự báo “một ngày nào đó có thể cần” thành ràng buộc hiện tại.

### 2.1. Phân biệt sự thật, giả định và mong muốn

Khi thảo luận, nên ghi nguồn và độ tin cậy của thông tin:

- **Sự thật đo được:** trong 30 ngày gần đây, p95 latency của endpoint tạo đơn là 180 ms; tỷ lệ lỗi đo được là 0,2%. Số liệu chỉ là ví dụ minh họa.
- **Yêu cầu đã được xác nhận:** luồng thanh toán phải ngăn thu tiền trùng cho cùng một giao dịch nghiệp vụ.
- **Giả định:** khối lượng đặt hàng có thể tăng gấp năm lần dịp khuyến mãi; cần load test hoặc số liệu chiến dịch để kiểm chứng.
- **Mong muốn:** “muốn dùng event sourcing để hệ thống hiện đại hơn” chưa thể tự xem là yêu cầu chất lượng.

Ghi rõ điều chưa biết giúp nhóm tránh xây kiến trúc phức tạp chỉ để bảo vệ một giả định chưa được chứng minh.

### 2.2. Tách yêu cầu chức năng và thuộc tính chất lượng

Yêu cầu chức năng mô tả **hệ thống làm gì**: tạo đơn, giữ hàng, xử lý thanh toán, gửi thông báo. Thuộc tính chất lượng mô tả **hệ thống phải làm điều đó tốt đến đâu hoặc trong điều kiện nào**: tốc độ, độ sẵn sàng, bảo mật, phục hồi, khả năng mở rộng, dễ thay đổi, dễ kiểm thử.

Hai hệ thống có cùng tính năng tạo đơn có thể cần kiến trúc khác hẳn nếu một hệ thống nhận vài trăm đơn/ngày còn hệ thống kia phục vụ flash sale với lượng truy cập đột biến. Nhưng lưu lượng cao tự nó cũng chưa chứng minh cần microservices: tối ưu truy vấn, cache, tách read workload hoặc mở rộng một ứng dụng có thể giải quyết được.

## 3. Biến mục tiêu mơ hồ thành kịch bản có thể kiểm chứng

Một phát biểu như “hệ thống phải nhanh, ổn định và dễ mở rộng” khó dùng để đánh giá các phương án. Hãy viết thành **kịch bản thuộc tính chất lượng**: tác nhân/kích thích, tình huống xảy ra, thành phần bị tác động, phản ứng mong muốn và thước đo.

Ví dụ:

| Thuộc tính | Kịch bản cụ thể | Cách kiểm chứng |
| --- | --- | --- |
| Hiệu năng | Khi có 2.000 người đồng thời đặt hàng trong chiến dịch, API tạo đơn phải trả xác nhận tiếp nhận trong 500 ms tại p95 | Load test với dữ liệu và tỷ lệ request gần thực tế |
| Độ tin cậy | Khi nhà cung cấp thanh toán timeout, hệ thống không được thu tiền lặp và trạng thái đơn phải được đối soát | Fault-injection test, kiểm tra idempotency và reconciliation |
| Khả dụng | Nếu dịch vụ gợi ý sản phẩm bị lỗi, luồng xem sản phẩm và đặt hàng vẫn hoạt động | Thử ngắt dependency và quan sát hành vi |
| Khả năng thay đổi | Bổ sung một cách tính phí vận chuyển mới không cần sửa mã thanh toán | Theo dõi các điểm thay đổi code và contract test |
| Phục hồi | Sau sự cố hạ tầng, dịch vụ trở lại trong RTO được chấp thuận và mất dữ liệu không vượt RPO | Diễn tập restore/failover trên dữ liệu thử |
| Bảo mật | Nhân viên chăm sóc khách hàng chỉ xem thông tin đơn được phép, không xem token thanh toán | Kiểm thử phân quyền và audit log |

Những con số trong bảng là **giả định của tình huống học tập**, không phải giá trị mặc định cho mọi hệ thống. Trong dự án thực, các bên liên quan phải thống nhất mục tiêu, phương pháp đo và chi phí đạt mục tiêu đó.

**RTO (Recovery Time Objective)** là mục tiêu thời gian khôi phục sau sự cố; **RPO (Recovery Point Objective)** là mức dữ liệu có thể mất theo thời gian. **p95 latency** là ngưỡng mà 95% các lần đo có độ trễ nhỏ hơn hoặc bằng, nhưng phải xác định cửa sổ đo và tải kiểm thử.

Khi yêu cầu đã đo được, nhóm có thể hỏi: một modular monolith có đáp ứng không? Hệ quản trị dữ liệu hiện tại có đủ không? Cần thêm queue, cache, replication, background job hoặc tách một dịch vụ cụ thể ở đâu?

## 4. Phân loại ràng buộc: điều bắt buộc và điều có thể thương lượng

Ràng buộc cứng là những điều **bất kỳ phương án nào cũng phải tuân thủ**. Ví dụ: không chuyển dữ liệu khách hàng ra ngoài khu vực được phép; bắt buộc mã hóa kết nối và lưu audit trail; phải tích hợp hệ thống lõi hiện có qua giao thức được duyệt; thời hạn pháp lý không thể lùi.

Ràng buộc mềm là điều có thể tối ưu hoặc đánh đổi: chi phí cloud hàng tháng, tốc độ onboarding kỹ sư, độ dễ bảo trì, thời gian phát hành hay mức lock-in chấp nhận được.

Không nên chấm điểm để “bù” một vi phạm bắt buộc. Một phương án có hiệu năng tốt nhưng không đáp ứng quy định pháp lý phải bị loại hoặc được thiết kế lại **trước** khi so sánh điểm tổng.

### Ví dụ phân loại

| Yêu cầu | Loại | Cách xử lý |
| --- | --- | --- |
| Dữ liệu thanh toán nhạy cảm phải tuân thủ chuẩn và phân quyền đã được phê duyệt | Cứng | Thiết kế và xác minh tuân thủ trước |
| Ngân sách vận hành nên dưới 40 triệu đồng/tháng | Mềm hoặc cứng tùy cam kết | Xác nhận với chủ ngân sách; tính tổng chi phí |
| Muốn dùng Kubernetes vì dễ tuyển người | Giả định cần chứng cứ | Kiểm tra kỹ năng nhóm, chi phí vận hành và yêu cầu triển khai |
| Sản phẩm ra mắt vào một ngày theo hợp đồng | Cứng về tiến độ | Loại phương án chưa thể chuẩn bị và chạy an toàn đúng hạn |
| Mong muốn độc lập triển khai các nhóm | Mục tiêu chất lượng | Đo tần suất release, coupling và nhu cầu phối hợp |

Sự phân loại này nên được chốt với người có thẩm quyền về sản phẩm, vận hành, bảo mật và tài chính; kiến trúc sư không tự biến mọi sở thích kỹ thuật thành quy định bất khả thương lượng.

## 5. Quy trình ra quyết định kiến trúc có bằng chứng

Một quy trình nhẹ nhưng có cấu trúc có thể thực hiện theo chín bước:

1. **Nêu quyết định:** xác định phạm vi và câu hỏi cụ thể, chẳng hạn “trong 12 tháng tới, luồng đặt hàng nên ở modular monolith hay được tách thành các dịch vụ độc lập?”.
2. **Xác nhận mục tiêu và người liên quan:** ưu tiên trải nghiệm khách hàng, tốc độ phát hành, an toàn dữ liệu, chi phí và trách nhiệm vận hành.
3. **Thu thập bối cảnh:** tải đo được, đặc tính giao dịch, ranh giới nghiệp vụ, cấu trúc đội ngũ, nền tảng hiện có, deadline.
4. **Chốt điều kiện bắt buộc và tiêu chí có thể đo:** loại phương án vi phạm ràng buộc cứng; mô tả quality attribute scenarios.
5. **Tạo một số phương án thực sự khác nhau:** gồm một phương án đơn giản có thể triển khai ngay; không chỉ liệt kê các công nghệ đang phổ biến.
6. **So sánh trade-off và tổng chi phí sở hữu:** tính cả xây dựng, vận hành, đào tạo, sự cố, di chuyển dữ liệu và khả năng đảo ngược.
7. **Kiểm chứng giả định rủi ro nhất:** prototype, load test, failure test, contract test, cost model hoặc spike kỹ thuật có giới hạn.
8. **Ghi quyết định bằng ADR:** bối cảnh, phương án, lý do, hệ quả, trạng thái, người quyết định và điều kiện xem lại.
9. **Theo dõi thực tế và điều chỉnh:** đặt các chỉ báo có thể kiểm tra; xem lại khi bối cảnh đổi thay hoặc giả định bị bác bỏ.

~~~mermaid
flowchart TD
    A["Nhu cầu và mục tiêu kinh doanh"] --> B["Bối cảnh, dữ kiện, ràng buộc"]
    B --> C["Kịch bản chất lượng đo được"]
    C --> D["Các phương án khả thi"]
    D --> E{"Đáp ứng ràng buộc cứng?"}
    E -- "Không" --> F["Loại bỏ hoặc thiết kế lại"]
    E -- "Có" --> G["So sánh trade-off, rủi ro, chi phí"]
    G --> H["Kiểm chứng giả định quan trọng"]
    H --> I["Ghi ADR và triển khai"]
    I --> J["Đo kết quả và xem lại theo tín hiệu"]
~~~

Không phải dự án nào cũng cần một hội đồng nhiều tầng. Với quyết định nhỏ, ghi vài dòng ADR và một phép thử là đủ. Với quyết định khó đảo ngược liên quan nhiều nhóm hoặc dữ liệu quan trọng, cần nhiều bằng chứng, chủ sở hữu và cơ chế review rõ ràng hơn.

## 6. Đánh giá trade-off: mỗi lựa chọn giải quyết và tạo ra vấn đề gì?

**Trade-off** là việc chấp nhận mất một số tính chất để đạt ưu tiên quan trọng hơn. Không có mô hình nào đạt đồng thời mọi thuộc tính với chi phí bằng không.

| Lựa chọn | Lợi ích khi phù hợp | Chi phí hoặc rủi ro cần tính |
| --- | --- | --- |
| Monolith | Triển khai đơn giản, lời gọi nội bộ nhanh, giao dịch cùng database thuận tiện | Nếu thiếu ranh giới dễ coupling; thay đổi toàn app có thể ảnh hưởng nhau |
| Modular monolith | Ranh giới nghiệp vụ rõ, vận hành một ứng dụng, dễ refactor hơn code lẫn lộn | Vẫn thường triển khai/scale theo toàn ứng dụng; phải duy trì kỷ luật module |
| Microservices | Dịch vụ có thể phát hành và scale độc lập, phù hợp nhiều nhóm có ownership rõ | Lỗi mạng, nhất quán phân tán, observability, CI/CD, bảo mật và on-call phức tạp |
| REST/gRPC đồng bộ | Dễ yêu cầu và lấy kết quả trực tiếp; hợp với thao tác cần phản hồi ngay | Phụ thuộc thời gian chạy, latency và sự cố của dịch vụ downstream |
| Event/message bất đồng bộ | Tách thời điểm xử lý, hấp thụ đỉnh tải, hỗ trợ luồng dài | Retry, duplicate, ordering, eventual consistency, dead-letter và debugging |
| SQL quan hệ | Transaction mạnh, ràng buộc dữ liệu, truy vấn linh hoạt | Cần thiết kế schema/index, migration; scaling phụ thuộc đặc tính tải |
| NoSQL dạng tài liệu | Linh hoạt với aggregate/tài liệu thay đổi cấu trúc, phù hợp một số kiểu truy cập | Không tự giải quyết mọi bài toán scale; join, transaction và truy vấn phụ thuộc engine |
| Managed service | Giảm công vận hành hạ tầng và tăng tốc triển khai | Chi phí theo usage, giới hạn nhà cung cấp, dữ liệu, lock-in và kiểm soát nền tảng |
| Tự vận hành | Kiểm soát cấu hình và vòng đời, có thể phù hợp yêu cầu đặc biệt | Cần chuyên môn, trực sự cố, backup, patch bảo mật và kiểm thử phục hồi |

Một lựa chọn có thể rất tốt trong **phạm vi hẹp**. Ví dụ, dùng queue để gửi email sau khi đơn hàng thành công có thể hữu ích ngay cả khi toàn bộ sản phẩm vẫn là modular monolith. Không cần chuyển cả hệ thống sang event-driven architecture để giải quyết một nhu cầu bất đồng bộ đơn lẻ.

### 6.1. Cách đọc một trade-off cho đúng

Nếu đề xuất “microservices giúp scale độc lập”, hãy tiếp tục hỏi:

- Thành phần nào thực sự cần scale theo một đường tải khác?
- Vấn đề hiện tại nằm ở CPU của ứng dụng, truy vấn database, khóa giao dịch hay API ngoài?
- Tách tiến trình có giảm bottleneck đó không, hay chỉ thêm lời gọi mạng?
- Nhóm có khả năng phát hành độc lập không, hay phải phối hợp release vì dữ liệu và API còn coupling?
- Chi phí thiết lập tracing, deployment, on-call, bảo mật và disaster recovery sẽ tăng bao nhiêu?

Nếu “scale độc lập” không giải quyết bottleneck đã được xác định, lập luận đó chưa đủ để biện minh cho một thay đổi kiến trúc lớn.

### 6.2. Không tối ưu đồng thời mọi thuộc tính

Một nhóm thường phải ưu tiên. Ví dụ trong 90 ngày trước launch: **độ tin cậy giao dịch và tốc độ đưa chức năng ra thị trường** có thể quan trọng hơn khả năng triển khai riêng 20 dịch vụ. Với nền tảng đã có nhiều nhóm và release hàng chục lần/ngày, chi phí phối hợp có thể lại là rủi ro lớn nhất.

Việc công khai ưu tiên giúp giải thích vì sao hai dự án cùng dùng Java/Spring Boot và cùng mức tải vẫn có thể chọn kiến trúc khác nhau.

## 7. Công cụ so sánh: ma trận quyết định có trọng số

Ma trận có trọng số giúp cuộc thảo luận trở nên rõ ràng hơn. Nó **không phải công thức chứng minh phương án đúng**, vì điểm số và trọng số vẫn chịu ảnh hưởng của đánh giá chủ quan. Nhưng nó buộc nhóm nêu ra tiêu chí, ưu tiên và giả định có thể tranh luận.

Giả sử nhóm làm nền tảng bán hàng với vài kỹ sư, mục tiêu ra phiên bản ổn định sớm, chưa có đội vận hành hệ thống phân tán. Những ưu tiên minh họa:

| Tiêu chí | Trọng số | Monolith | Modular monolith | Microservices |
| --- | ---: | ---: | ---: | ---: |
| Tốc độ ra mắt | 25% | 5 | 4 | 2 |
| Đơn giản trong vận hành | 20% | 5 | 5 | 2 |
| Cô lập thay đổi nghiệp vụ trong code | 25% | 2 | 5 | 5 |
| Triển khai độc lập | 15% | 1 | 2 | 5 |
| Scale riêng thành phần | 10% | 2 | 3 | 5 |
| Giao dịch nhất quán xuyên chức năng | 5% | 5 | 4 | 2 |
| **Tổng điểm quy đổi** | **100%** | **3,35/5** | **4,05/5** | **3,50/5** |

Mỗi điểm là đánh giá giả định từ **1 = phù hợp kém** đến **5 = phù hợp cao** theo bối cảnh đã nêu. Công thức:

~~~text
Điểm phương án = Σ(trọng số tiêu chí × điểm phương án)
Ví dụ modular monolith:
0,25×4 + 0,20×5 + 0,25×5 + 0,15×2 + 0,10×3 + 0,05×4
= 4,05 / 5
~~~

Trong ví dụ, modular monolith dẫn đầu vì vừa giữ vận hành đơn giản vừa tạo ranh giới code tốt. Điều đó **không có nghĩa modular monolith luôn thắng**. Nếu đổi trọng số để ưu tiên triển khai độc lập và scale từng năng lực, thứ tự có thể khác. Nếu một phương án vi phạm ràng buộc cứng, không được cho nó thắng nhờ điểm tổng cao.

### 7.1. Những giới hạn cần nhớ khi chấm điểm

- **Không chấm điểm khi chưa xác định các tiêu chí đo được**: “hiện đại” và “phổ biến” không nói rõ lợi ích kinh doanh.
- **Tránh đếm cùng một lợi ích hai lần**: “đội ngũ tự chủ” và “triển khai độc lập” có thể liên hệ mạnh, cần mô tả rõ.
- **Đừng lấy chênh lệch 0,1 điểm làm bằng chứng chắc chắn**: điểm là công cụ trao đổi, không phải thống kê có độ chính xác cao.
- **Kiểm tra độ nhạy**: khi đổi các trọng số hợp lý, quyết định có còn ổn định không?
- **Loại vi phạm bắt buộc trước khi chấm điểm**: không đánh đổi yêu cầu pháp lý bằng điểm hiệu năng.
- **Ghi người chịu trách nhiệm chấm và dữ kiện hỗ trợ**: tránh kết quả có vẻ khách quan nhưng không có căn cứ.

Các lựa chọn tốt thường còn có **đường thoát**: ví dụ chia module theo bounded context từ sớm để có thể tách dịch vụ sau khi xuất hiện một nhu cầu độc lập cụ thể.

## 8. Ví dụ xuyên suốt: chọn kiến trúc cho nền tảng đặt hàng

### 8.1. Bối cảnh giả định

Một doanh nghiệp đang xây nền tảng bán hàng gồm catalog, giỏ hàng, đơn hàng, tồn kho, thanh toán và thông báo. Đội gồm sáu kỹ sư backend, chưa có SRE chuyên trách. Sản phẩm cần ra mắt trong 12 tuần. Tải hiện tại còn thấp, nhưng có khả năng tăng theo chiến dịch. Giao dịch thanh toán và giữ hàng phải có khả năng xử lý retry an toàn. Đội muốn bổ sung tính năng theo tuần.

Các thông tin này là **dữ kiện giả định cho bài học**. Trước dự án thực, phải đo tải, xác nhận deadline và làm rõ ai chịu trách nhiệm vận hành.

### 8.2. Ba phương án

**A — Monolith ít ranh giới:** một Spring Boot application với package theo controller/service/repository, một database, một pipeline. Triển khai nhanh nhưng dễ tạo các dependency không rõ khi nghiệp vụ lớn lên.

**B — Modular monolith theo nghiệp vụ:** một Spring Boot application với các module catalog, order, inventory, payment; mỗi module giữ quy tắc, API nội bộ và dữ liệu của riêng mình ở mức có thể. Các module nằm trong một deployment, nhưng có thể enforce dependency rule và contract test. Transaction giữa module chỉ dùng khi thực sự cần và có ownership rõ. Tác vụ gửi thông báo có thể dùng background job/outbox.

**C — Microservices ngay từ đầu:** nhiều ứng dụng Spring Boot, database/API riêng, broker/gateway, pipeline từng service, distributed tracing, retry, idempotency và quy trình xử lý sự cố. Có cơ hội release độc lập, nhưng thêm nhiều việc vào deadline ngắn.

### 8.3. Quyết định có lý do

Trong bối cảnh này, nhóm **có thể chọn B: modular monolith** cho giai đoạn đầu. Lý do: giảm chi phí hạ tầng và phối hợp, hỗ trợ giao dịch cục bộ, vẫn xây ranh giới domain để tránh phụ thuộc ngầm. Những điểm cần ghi nhận:

- Không dựa vào việc “monolith nhẹ hơn” như chân lý; đo latency, throughput và độ ổn định của chính hệ thống.
- Bản thân việc đặt package theo domain không bảo đảm module độc lập; cần hạn chế truy cập bảng của nhau, quy định public interface và kiểm tra dependency.
- Payment phải chống xử lý lặp; sự nhất quán nghiệp vụ vẫn cần thiết kế dù các module ở cùng process.
- Nếu email hoặc cập nhật search index là tác vụ nền, queue/outbox nội bộ có thể đủ; không cần tách mọi tác vụ thành service.
- Khi một module cần release/scale độc lập, nhóm có căn cứ để cân nhắc tách module đó bằng hợp đồng ổn định.

### 8.4. Khi nào xem lại?

Một số tín hiệu có thể khiến quyết định thay đổi:

- Catalog hoặc Search cần scale theo tải rất khác Order và đã xác định bottleneck qua profiling, metrics.
- Nhiều nhóm có ownership riêng, release thường xuyên nhưng bị chặn vì một deployment chung.
- Thời gian build, kiểm thử và phát hành tăng vượt ngưỡng nhóm chấp nhận, dù đã cải thiện pipeline và tổ chức module.
- Ranh giới dữ liệu và hợp đồng của một module đã ổn định, rủi ro tách được lượng hóa.
- Đội vận hành có đủ khả năng quan sát, xử lý sự cố và triển khai độc lập.

**Tín hiệu phải gắn với vấn đề thực tế**, không phải mốc “đến 10.000 người dùng thì bắt buộc chuyển microservices”. Hai hệ thống cùng lượng người dùng có kiểu tải, độ phức tạp và yêu cầu độ tin cậy rất khác nhau.

## 9. Tình huống đối lập: khi tách dịch vụ có giá trị

Xét một nền tảng lớn hơn: nhiều đội độc lập phát triển chức năng thanh toán, tìm kiếm, xử lý media, đối soát; mỗi đội có lịch phát hành và yêu cầu vận hành khác nhau. Search nhận số lượng truy vấn cao hơn nhiều so với cập nhật đơn. Media processing cần nhiều CPU hoặc GPU. Thanh toán có tiêu chuẩn bảo mật và nhật ký riêng.

Trong trường hợp này, **microservices có thể là một lựa chọn tốt** ở các ranh giới được chứng minh là độc lập. Search có thể scale và index theo cách riêng; Media Service xử lý batch bất đồng bộ; Payment Service giảm bề mặt truy cập và áp dụng chính sách chặt chẽ.

Tuy nhiên, không nên suy ra phải chia **tất cả** domain thành dịch vụ. Những phần cùng thay đổi, có transaction gắn bó và do một nhóm sở hữu có thể tiếp tục trong một modular monolith. Kiến trúc hỗn hợp là hợp lệ nếu ranh giới và chi phí vận hành được quản lý rõ.

### Tại sao team topology ảnh hưởng đến kiến trúc?

Mỗi service là một trách nhiệm dài hạn: build, deploy, migration, logs, alert, security và on-call. Nếu không có nhóm thật sự sở hữu, một nhóm trung tâm sẽ phải duy trì toàn bộ hệ thống, làm mất nhiều lợi ích “tự chủ” của microservices.

Ngược lại, nếu các nhóm thay đổi cùng một monolith liên tục nhưng có quy tắc quản lý module tốt, họ vẫn có thể làm việc hiệu quả mà chưa cần phân tán runtime. Vì vậy cần xem xét **chi phí phối hợp thực tế** song song với topology kỹ thuật.

## 10. Chọn ranh giới trước khi chọn công nghệ

Một ranh giới tốt đặt những quy tắc thay đổi cùng nhau gần nhau và giảm phụ thuộc không cần thiết. Khi phân tích domain, có thể hỏi:

- Năng lực nào tạo ra giá trị nghiệp vụ độc lập?
- Thuật ngữ và invariant nào chỉ nhất quán trong một **bounded context**?
- Ai sở hữu dữ liệu? Ai có quyền thay đổi trạng thái? Ai chỉ cần đọc bản sao?
- Các thành phần thường thay đổi cùng nhau hay độc lập trong lịch sử yêu cầu?
- Nếu tách, một use case cần bao nhiêu lời gọi qua mạng và bao nhiêu bước bù trừ?
- Có contract đủ ổn định để consumer không bị buộc cập nhật cùng lúc không?

Một bounded context là gợi ý hữu ích cho ranh giới module/service, **không phải mệnh lệnh mỗi context phải là một microservice**. Kích thước ranh giới còn phụ thuộc vào giao dịch, khả năng vận hành và organizational ownership.

Ví dụ tách mỗi bảng Product, ProductPrice, ProductImage thành một service thường khiến thao tác hiển thị sản phẩm phải gọi dây chuyền. Nếu ba phần cùng thay đổi và có invariant chung, một ranh giới lớn hơn có thể đúng hơn.

## 11. Đánh giá dữ liệu và tính nhất quán trước khi phân tán

Khi chuyển từ một ứng dụng và một database sang nhiều service/database, một giao dịch nghiệp vụ có thể trở thành chuỗi giao dịch cục bộ. Trước khi chọn, hãy vẽ **data flow** và đặt câu hỏi về hậu quả khi một bước thất bại.

Ví dụ:

~~~text
Tạo đơn -> Giữ hàng -> Gửi yêu cầu thanh toán -> Xác nhận đơn
                         |
                         +-- timeout / callback lặp / xử lý chậm
~~~

Trong monolith, một số bước có thể nằm trong transaction cục bộ; nhưng thao tác bên ngoài như thanh toán qua nhà cung cấp vẫn không thể rollback bằng SQL. Trong microservices, nhóm còn phải giải quyết network failure và trạng thái trung gian giữa service.

Những kỹ thuật liên quan có thể gồm:

- **Idempotency key:** ngăn cùng một yêu cầu nghiệp vụ tạo tác dụng lặp khi retry.
- **Transactional outbox:** ghi sự kiện cần phát và thay đổi dữ liệu trong cùng transaction cục bộ.
- **Saga:** điều phối nhiều giao dịch cục bộ và hành động bù trừ.
- **Reconciliation:** định kỳ đối soát trạng thái giữa các nguồn để phát hiện và sửa lệch.
- **Read model hoặc cache:** phục vụ truy vấn tổng hợp mà không truy cập database nội bộ của service khác.
- **Versioning schema:** bảo vệ consumer khi cấu trúc message và API thay đổi.

Đó là những **chi phí thiết kế thực**, không chỉ là “thêm một thư viện”. Cũng không nên dùng các kỹ thuật phân tán nếu một transaction cục bộ đơn giản đã giải quyết đúng yêu cầu.

## 12. Kiểm chứng bằng thử nghiệm nhỏ có mục tiêu

Tranh luận lý thuyết thường không thể trả lời các câu hỏi như “database này có đủ tải không?” hoặc “đội có deploy được mỗi dịch vụ một cách độc lập không?”. Hãy chọn **giả định có rủi ro cao nhất** và làm spike/prototype có phạm vi rõ ràng.

Ví dụ một thí nghiệm:

**Giả thuyết:** “Một ứng dụng với database quan hệ hiện tại có thể đáp ứng p95 500 ms ở tải campaign dự kiến; chưa cần tách Order thành service riêng.”

**Phạm vi:** tạo tập dữ liệu đại diện; mô phỏng tỷ lệ request đọc/ghi, số concurrent users và các thao tác transaction quan trọng; cấu hình kết nối và chỉ số như production; giới hạn thời gian thử nghiệm.

**Kết quả cần thu:** p50/p95/p99 latency, throughput, error rate, lock wait, database CPU/IO, số connection, resource saturation. Ghi kết quả theo từng mức tải, không chỉ ở một mức dễ đạt.

**Tiêu chuẩn quyết định:** nếu đáp ứng mục tiêu với headroom hợp lý và có phương án tăng tài nguyên/tối ưu, ưu tiên giữ kiến trúc đơn giản. Nếu không đáp ứng, tìm bottleneck cụ thể rồi so sánh các cách sửa: index, query design, caching, background work, read replica hoặc tách ranh giới hợp lý.

**Cảnh báo:** một prototype không tái hiện đầy đủ production. Kết quả phụ thuộc dữ liệu, latency mạng, cấu hình, tỷ lệ request và các tải nền. Ghi các giới hạn thí nghiệm trước khi dùng để ra quyết định.

### 12.1. Chọn phép thử tương ứng với rủi ro

| Rủi ro chưa rõ | Phép thử phù hợp |
| --- | --- |
| Hệ thống không đạt mức tải | Load/stress test với dữ liệu đại diện, profiling |
| Sự cố dependency gây lỗi dây chuyền | Fault injection: timeout, disconnect, retry, queue lag |
| Hợp đồng giữa các service dễ vỡ | Consumer-driven contract test, backward compatibility test |
| Khó migration dữ liệu | Rehearsal trên snapshot đã ẩn dữ liệu nhạy cảm và đo rollback |
| Chi phí cloud vượt ngân sách | Tính usage theo tải dự kiến và kịch bản tăng trưởng |
| Nhóm thiếu khả năng vận hành | Diễn tập deploy, rollback, xử lý alert và restore |
| Giải pháp gây lock-in | Kiểm tra chi phí xuất dữ liệu, thay API, chạy thay thế |
| Dữ liệu mất khi lỗi | Backup/restore và failover exercise kiểm RPO/RTO |

Một phép thử tốt trả lời **một câu hỏi ảnh hưởng đến quyết định**; tránh tạo proof of concept khổng lồ không có điều kiện thành công cụ thể.

## 13. Ghi quyết định bằng Architecture Decision Record (ADR)

**ADR** là bản ghi ngắn giải thích **đã chọn gì, vì sao, trong bối cảnh nào và đã chấp nhận hệ quả gì**. ADR giúp người mới hiểu lý do của kiến trúc, giúp nhóm tranh luận dựa trên bằng chứng, và tránh lặp lại quyết định khi bối cảnh chưa đổi.

Một mẫu tối thiểu:

~~~markdown
# ADR-00X: <Tên quyết định>

Trạng thái: Proposed | Accepted | Superseded | Deprecated
Ngày: <YYYY-MM-DD>
Người tham gia/quyết định: <vai trò hoặc tên nhóm>

## Bối cảnh
Nhu cầu nghiệp vụ, dữ kiện, giả định, ràng buộc,
mục tiêu chất lượng và các điểm chưa biết.

## Các phương án
- A: Lợi ích, chi phí, rủi ro
- B: Lợi ích, chi phí, rủi ro
- C: Lợi ích, chi phí, rủi ro

## Quyết định
Chọn phương án nào, phạm vi áp dụng, lý do.

## Hệ quả
Điểm được, điểm mất, chi phí vận hành,
phụ thuộc mới và phần việc cần làm.

## Bằng chứng
Số liệu, prototype, load test, đánh giá bảo mật,
các giả định chưa được kiểm chứng.

## Điều kiện xem lại
Tín hiệu, ngưỡng hoặc thay đổi bối cảnh kích hoạt review.
~~~

### 13.1. Ví dụ ADR ngắn có thể sử dụng

~~~markdown
# ADR-007: Dùng modular monolith cho luồng đặt hàng giai đoạn đầu

Trạng thái: Accepted (ví dụ minh họa)
Bối cảnh: 6 backend engineer; launch sau 12 tuần;
chưa có SRE chuyên trách; tải chưa chứng minh cần scale riêng.
Độ tin cậy giao dịch và tốc độ phát hành là ưu tiên hiện tại.

Phương án:
1. Monolith không có ranh giới module rõ.
2. Modular monolith theo Catalog/Order/Inventory/Payment.
3. Tách microservices ngay từ đầu.

Quyết định: Chọn (2).
- Public interface của từng module được quy định rõ.
- Không truy cập trực tiếp bảng sở hữu bởi module khác
  nếu đã có ranh giới dữ liệu được thỏa thuận.
- Kiểm thử dependency giữa module và contract tại CI.
- Thanh toán dùng idempotency; tác vụ nền có cơ chế
  retry và theo dõi trạng thái.

Hệ quả tích cực: Ít thành phần vận hành hơn; dễ kiểm thử
giao dịch cục bộ; có ranh giới để phát triển dài hạn.

Hệ quả phải chấp nhận: Triển khai cùng ứng dụng;
không scale độc lập từng module trong giai đoạn đầu.

Xem lại khi: có dữ liệu chứng minh một module cần scale
riêng, release chung tạo nút thắt định lượng, hoặc nhiều
nhóm có khả năng vận hành dịch vụ độc lập.
~~~

Với hệ thống thật, nên đính kèm đường dẫn tới số liệu, ticket hoặc kết quả thử nghiệm. ADR không cần mô tả mọi class hay thay thế tài liệu thiết kế chi tiết. Khi quyết định đổi, ghi ADR mới và đánh dấu bản cũ được thay thế, để giữ lịch sử lý do.

## 14. Không biến ADR thành tài liệu hình thức

Một ADR tốt phải cho người đọc trả lời được:

- Quyết định giải quyết **vấn đề cụ thể** nào?
- Tại sao lựa chọn khác **không phù hợp với bối cảnh hiện tại**, dù vẫn có ưu điểm?
- Những giả định nào nếu sai sẽ khiến quyết định cần xem lại?
- Ai chịu trách nhiệm đo kết quả và chi phí chuyển đổi?
- Đâu là điều kiện đủ để cân nhắc thay đổi, tránh cả bảo thủ lẫn thay công nghệ liên tục?

Tránh ADR chỉ ghi “Chọn Kafka vì scalable” hoặc “Chọn microservices vì cloud native” mà không nói về event volume, độ trễ, yêu cầu durability, kỹ năng vận hành, lựa chọn đơn giản hơn và rủi ro mạng.

Cũng tránh viết ADR sau khi đã triển khai mọi thứ rồi dùng nó để hợp thức hóa một sở thích. Có thể lập ADR dạng **Proposed** trước khi làm proof of concept và đổi trạng thái khi có dữ kiện.

## 15. Chống thiên kiến công nghệ khi thảo luận

Một nhóm dễ bị ảnh hưởng bởi kinh nghiệm gần nhất, bài viết nổi tiếng, sự hấp dẫn của công nghệ mới hoặc mong muốn tối ưu CV. Những thiên kiến này không có nghĩa công nghệ đang được đề xuất là xấu; chúng chỉ có nghĩa **cần kiểm chứng bằng tiêu chí độc lập với danh tiếng công nghệ**.

| Thiên kiến | Biểu hiện | Cách giảm |
| --- | --- | --- |
| Popularity bias | “Nhiều công ty lớn dùng nên mình cũng phải dùng” | So sánh tải, tổ chức và ràng buộc thực tế |
| Recency bias | Vừa đọc bài mới về event sourcing nên đề xuất cho mọi domain | Yêu cầu use case và mô hình chi phí cụ thể |
| Confirmation bias | Chỉ tìm benchmark ủng hộ lựa chọn yêu thích | Tìm dữ kiện bác bỏ và yêu cầu người khác phản biện |
| Sunk cost | Giữ kiến trúc cũ chỉ vì đã đầu tư nhiều năm | So chi phí tương lai, không coi chi phí đã mất là lợi ích |
| Premature optimization | Phân tán từ đầu để phục vụ hàng triệu user chưa có | Tách điều cần ngay khỏi khả năng mở rộng theo tín hiệu |
| Resume-driven development | Chọn stack để có thêm công nghệ trong hồ sơ | Liên hệ công nghệ với SLO, chi phí và năng lực nhóm |
| One-size-fits-all | “Mọi hệ thống phải theo Clean Architecture/CQRS” | Giới hạn phạm vi pattern ở nơi nó giải quyết vấn đề |

Các câu hỏi phản biện hữu ích:

1. Nếu bỏ tên công nghệ, **vấn đề cần giải quyết** vẫn là gì?
2. Có phương án đơn giản hơn nào đạt cùng mục tiêu trong giai đoạn này không?
3. Những số liệu nào có thể khiến chúng ta **đổi ý**?
4. Nếu cần hoàn tác sau sáu tháng, chi phí và rủi ro thế nào?
5. Nhóm nào sẽ trực xử lý sự cố vào ban đêm, và họ có đủ năng lực không?

Kiến trúc sư có trách nhiệm nêu rõ chi phí của phương án mình đề xuất, ngay cả khi phương án đó hấp dẫn về mặt kỹ thuật.

## 16. Quyết định có thể đảo ngược và khó đảo ngược

Không phải mọi quyết định đều cần mức phân tích như nhau. Có thể chia thành hai nhóm tương đối:

**Dễ đảo ngược:** đổi thư viện trong một module có interface tốt; điều chỉnh cấu hình autoscale; thêm cache có cơ chế invalidation rõ; tối ưu một endpoint riêng. Có thể thử nhỏ, đo, rollback.

**Khó đảo ngược:** chọn phân vùng dữ liệu và khóa chính, chia database theo service, chọn nền tảng cloud với managed API đặc thù, công bố public API có nhiều consumer, di chuyển khối lượng dữ liệu lớn, thay kiến trúc giao dịch lõi.

Với quyết định khó đảo ngược, đầu tư thêm vào option analysis, migration plan, compatibility, dữ liệu thử và phương án thất bại. Với quyết định dễ đảo ngược, nhiều khi **thử nhanh có đo đạc** tốt hơn tranh luận quá lâu.

### 16.1. Thiết kế để trì hoãn ràng buộc không cần thiết

Trì hoãn một quyết định chưa đủ dữ liệu không có nghĩa là bỏ qua kiến trúc. Ta có thể:

- Giữ interface ổn định ở các dependency dễ thay đổi.
- Tách module, giới hạn quyền truy cập dữ liệu và kiểm tra dependency.
- Sử dụng schema migration an toàn và hợp đồng tương thích.
- Đo tải và chi phí ngay từ sớm để biết khi nào cần thay đổi.
- Tránh xây một abstraction tổng quát chỉ để che giấu mọi khác biệt tưởng tượng giữa các nền tảng.

Ví dụ, trước khi chọn broker cho một luồng email ít tải, có thể thiết kế một port cho việc enqueue và bắt đầu bằng worker/job queue phù hợp. Khi yêu cầu throughput, durability hoặc multi-consumer thực sự xuất hiện, nhóm có dữ kiện để chọn hạ tầng tiếp theo.

## 17. Quyết định kiến trúc là một vòng lặp, không phải một lần chọn vĩnh viễn

Một hệ thống thay đổi cùng sản phẩm và đội ngũ. Một ADR được chấp nhận hôm nay vẫn có thể trở nên kém phù hợp khi các giả định của nó không còn đúng. Điều cần tránh là **đổi công nghệ chỉ vì công nghệ mới xuất hiện** và **giữ nguyên thiết kế dù số liệu chứng minh nó cản trở sản phẩm**.

Theo dõi các tín hiệu gắn trực tiếp với quyết định:

| Quyết định | Tín hiệu cần theo dõi | Lý do |
| --- | --- | --- |
| Modular monolith | Lead time, thời gian build/test, tỷ lệ module thay đổi cùng nhau | Phát hiện coupling và chi phí phát hành chung |
| Tách Search Service | Query latency, index freshness, CPU/IO, sự cố dependency | Kiểm tra lợi ích scale/ownership riêng |
| Giao tiếp bất đồng bộ | Queue depth, lag, duplicate handling, thời gian hoàn tất workflow | Phát hiện nghẽn và eventual consistency quá dài |
| Cache | Cache hit rate, stale data, memory, invalidation errors | Đánh giá hiệu quả và rủi ro dữ liệu cũ |
| Managed database | Chi phí usage, thời gian restore, giới hạn connection, failover | Kiểm tra tính phù hợp khi tải tăng |
| Multi-region | Thời gian failover, RPO/RTO, độ trễ liên vùng, chi phí | Kiểm tra mục tiêu phục hồi có đạt |

Có thể dùng **fitness function**: một phép kiểm tra tự động giúp kiến trúc giữ thuộc tính đã chọn. Ví dụ build thất bại nếu module Order phụ thuộc trực tiếp package implementation của Inventory; contract test phát hiện thay đổi API breaking; một kiểm thử độ trễ cảnh báo khi p95 vượt giới hạn đã thỏa thuận. Fitness function là cách đưa quyết định vào quy trình kỹ thuật, thay vì chỉ để trong tài liệu.

Không phải fitness function nào cũng tự động hóa được: khả năng sở hữu service, năng lực xử lý sự cố hay chi phí đào tạo cần cả đánh giá định tính.

## 18. Quan hệ giữa kiến trúc và tổ chức

Một hệ thống được xây và vận hành bởi con người. Quyết định hợp lý về sơ đồ kỹ thuật có thể thất bại nếu không tương thích với cấu trúc nhóm và quá trình phát hành.

Hãy kiểm tra bốn điểm:

**Ownership:** mỗi phần quan trọng có người/nhóm chịu trách nhiệm về code, dữ liệu, triển khai, alert và sự cố hay chưa?

**Cognitive load:** một kỹ sư mới phải hiểu bao nhiêu service, broker, gateway, dashboard và công cụ để sửa một use case?

**Coordination cost:** một thay đổi thường cần bao nhiêu nhóm phê duyệt, phát hành hoặc sửa contract cùng lúc?

**Operational readiness:** nhóm có đủ CI/CD, rollback, log, tracing, backup/restore, secret management và hướng dẫn xử lý sự cố không?

Nếu chưa có năng lực vận hành phân tán, microservices có thể làm giảm tốc độ thay vì tăng. Nếu ownership và ranh giới nghiệp vụ đã rõ, các nhóm có quy trình kỹ thuật mạnh, một vài service độc lập có thể tạo ra lợi ích đáng kể.

## 19. Đánh giá chi phí sở hữu thay vì chỉ chi phí viết code

**Total Cost of Ownership (TCO)** của một lựa chọn không chỉ gồm thời gian viết tính năng ban đầu. Nó còn bao gồm:

- **Chi phí phát triển:** build, kiểm thử, code review, data migration và tích hợp.
- **Chi phí vận hành:** compute, storage, network, broker, observability, backup, bảo mật và on-call.
- **Chi phí thay đổi:** cập nhật contract, triển khai phối hợp, refactor, đào tạo và khắc phục nợ kỹ thuật.
- **Chi phí sự cố:** downtime, mất dữ liệu, thời gian điều tra, bù trừ nghiệp vụ và ảnh hưởng đến khách hàng.
- **Chi phí thoát:** chuyển dữ liệu, thay dịch vụ managed, loại bỏ dependency hoặc hợp nhất service.

Một giải pháp managed có phí sử dụng cao hơn phần mềm tự vận hành nhưng vẫn có TCO thấp hơn nếu giảm đáng kể công sức vận hành. Ngược lại, mua một nền tảng quá lớn cho tải nhỏ có thể tạo chi phí cố định vượt lợi ích. Cần **ước lượng theo kịch bản sử dụng**, không chỉ so giá niêm yết.

### 19.1. So sánh theo kịch bản

Ít nhất nên xem ba kịch bản:

1. **Hiện tại:** tải, đội ngũ và ngân sách đã biết.
2. **Tăng trưởng hợp lý:** biến động theo dự báo có căn cứ, bao gồm đỉnh tải.
3. **Sự cố hoặc thay đổi lớn:** dependency ngoài gián đoạn, tăng dữ liệu bất ngờ, migration hoặc thay đổi yêu cầu pháp lý.

Nếu giải pháp tối ưu chỉ khi giả định tăng trưởng rất cao trở thành sự thật, nhóm phải cân nhắc xác suất, chi phí chờ đợi và khả năng mở rộng dần.

## 20. Sai lầm thường gặp và cách sửa lập luận

**Sai lầm 1: “Microservices luôn scalable hơn monolith.”**  
Hệ thống không chỉ bị giới hạn bởi số process. Database lock, query, cache miss, network hay API ngoài có thể là bottleneck chính. Hãy profiling rồi giải quyết đúng chỗ nghẽn.

**Sai lầm 2: “Dùng event-driven thì mọi thứ tự nhất quán.”**  
Thông điệp có thể trùng, trễ, sai thứ tự và bị kẹt. Cần idempotency, consistency model, retry policy, monitoring và đối soát nghiệp vụ.

**Sai lầm 3: “SQL cũ, NoSQL mới.”**  
Chọn theo query, transaction, ràng buộc dữ liệu, scale pattern, vận hành và kỹ năng. Một database quan hệ có thể phục vụ tải rất lớn khi thiết kế đúng; một document database không tự loại bỏ vấn đề consistency.

**Sai lầm 4: “Cứ thêm Kubernetes là cloud native.”**  
Orchestrator giúp quản lý container nhưng tạo thêm vận hành và cấu hình. Nếu yêu cầu đơn giản, một nền tảng deploy có quản lý khác có thể kinh tế hơn.

**Sai lầm 5: “Clean Architecture giải quyết mọi vấn đề.”**  
Các nguyên tắc cô lập dependency và nghiệp vụ có ích, nhưng số lượng layer/interface nên theo độ phức tạp. Thêm abstraction không được dùng sẽ làm code khó hiểu.

**Sai lầm 6: “Cần thiết kế hoàn chỉnh cho 10 năm.”**  
Phần lớn dự báo dài hạn chứa nhiều bất định. Hãy bảo vệ những ranh giới và invariant khó đổi, giữ các quyết định dễ đảo ngược, và đặt tín hiệu để xem lại.

**Sai lầm 7: “Chỉ một người giỏi quyết định là đủ.”**  
Architecture có tác động đến sản phẩm, bảo mật, dữ liệu, tài chính và vận hành. Quyết định cần tiếng nói của người chịu hậu quả và quyền chốt rõ ràng, tránh vừa độc đoán vừa không ai chịu trách nhiệm.

**Sai lầm 8: “Chọn một mẫu kiến trúc cho toàn công ty.”**  
Mẫu chung có thể giúp consistency ở security/observability nhưng không nên ép mọi sản phẩm cùng granularity, storage và runtime khi nhu cầu khác biệt.

## 21. Mẫu câu hỏi dùng trong một buổi design review

Một nhóm có thể dùng tập câu hỏi sau trước khi phê duyệt phương án:

1. **Bài toán:** Người dùng hoặc doanh nghiệp đang gặp vấn đề gì? Có số liệu nào chứng minh?
2. **Mục tiêu:** Những thuộc tính chất lượng nào quan trọng nhất và đo ra sao?
3. **Ràng buộc:** Phần nào bất khả thương lượng? Ai xác nhận?
4. **Phương án:** Có ít nhất một lựa chọn đơn giản, một lựa chọn trung gian và lựa chọn đề xuất không?
5. **Trade-off:** Lợi ích nào có thể đo được; chi phí và tác động vận hành là gì?
6. **Dữ liệu:** Ai sở hữu dữ liệu, invariant nào cần transaction, lúc lỗi cần trạng thái gì?
7. **Sự cố:** Dependency timeout, request lặp, mất kết nối hoặc deploy lỗi thì điều gì xảy ra?
8. **Đội ngũ:** Ai build, deploy, theo dõi, rollback và trực hỗ trợ?
9. **Bằng chứng:** Giả định nào chưa kiểm chứng, làm phép thử nhỏ nào để giải đáp?
10. **Điều chỉnh:** Khi nào xem lại, tín hiệu nào có thể khiến thay quyết định?
11. **Dấu vết:** ADR đặt ở đâu, ai chốt, hệ quả và phương án thay thế được ghi rõ chưa?

Nếu mọi người chỉ thảo luận tên công nghệ mà không trả lời được các câu hỏi này, cuộc họp chưa thực sự là một buổi ra quyết định kiến trúc.

## 22. Bài tập thực hành

### Bài tập A — Chọn hình thức triển khai

Một nhóm bốn lập trình viên đang làm ứng dụng quản lý đặt lịch cho vài phòng khám, dữ liệu có tính riêng tư, lượng người dùng chưa lớn. Hệ thống cần phân quyền chặt, lưu lịch sử thay đổi, đảm bảo không đặt trùng một khung giờ và ra mắt sớm.

Hãy:

1. Liệt kê ít nhất năm dữ kiện cần xác minh trước khi quyết định.
2. Viết ba quality attribute scenarios cụ thể về bảo mật, tính nhất quán lịch và thời gian phản hồi.
3. So sánh monolith, modular monolith và microservices bằng ít nhất năm tiêu chí có trọng số.
4. Đề xuất phương án giai đoạn đầu, giải thích điều kiện đổi ý.
5. Viết một ADR ngắn, nêu cả hậu quả bất lợi phải chấp nhận.

Điểm mấu chốt cần suy nghĩ: **lịch khám không bị đặt trùng** là invariant nghiệp vụ quan trọng; việc chia nhiều service có thể làm kiểm soát invariant khó hơn nếu làm thiếu thiết kế.

### Bài tập B — Phản biện đề xuất công nghệ

Một kỹ sư nói: “Nên dùng event sourcing cho toàn bộ đơn hàng vì đây là hướng hiện đại, dễ audit và scale.”

Hãy hỏi về: yêu cầu audit thực tế, quyền truy cập lịch sử sự kiện, mô hình projection, nhu cầu sửa dữ liệu nhạy cảm, idempotency, migration, retention, replay, kỹ năng vận hành và lựa chọn đơn giản hơn như audit log bất biến trong database giao dịch.

Hãy nêu **một trường hợp event sourcing có giá trị rõ** và **một trường hợp chi phí của nó vượt nhu cầu**, dựa trên bối cảnh.

### Bài tập C — Thay đổi giả định

Ở ví dụ nền tảng bán hàng, sau một năm:

- Có năm nhóm độc lập phát triển các năng lực khác nhau.
- Search thường cần scale riêng và có chu kỳ index phức tạp.
- Việc phát hành chung gây trì hoãn đáng kể.
- Đội đã có CI/CD, observability và năng lực on-call.

Hãy cập nhật trọng số, ghi nhận dữ kiện mới và xác định liệu nên tách riêng Search, Payment hay cả hệ thống. Không được kết luận “tách tất cả” chỉ vì một vài điều kiện thay đổi.

## 23. Tự kiểm tra kiến thức

1. Thế nào là quyết định kiến trúc theo bối cảnh? Vì sao “công ty lớn X đang dùng” chưa phải bằng chứng đủ?
2. Phân biệt ràng buộc cứng, tiêu chí ưu tiên và giả định cần kiểm chứng bằng ví dụ.
3. Biến phát biểu “dịch vụ phải ổn định” thành một kịch bản có tác nhân, tình huống, phản ứng và thước đo.
4. Vì sao cần xét team ownership và khả năng on-call khi lựa chọn microservices?
5. Khi điểm số giữa hai phương án gần nhau, nên kiểm tra điều gì trước khi chốt?
6. Vì sao một giao dịch thanh toán đi qua nhiều dịch vụ thường cần idempotency và đối soát?
7. Một ADR cần ghi điều gì để người mới hiểu quyết định mà không phải hỏi người thiết kế ban đầu?
8. Hãy đưa ra một fitness function tự động cho ranh giới module và một tín hiệu vận hành cần theo dõi thủ công.
9. Tại sao một phương án vi phạm điều kiện pháp lý không được thắng bằng điểm tổng cao?
10. Khi nào nên trì hoãn quyết định công nghệ, và khi nào trì hoãn trở thành rủi ro?

## 24. Kết luận

Lập quyết định kiến trúc theo bối cảnh là quá trình **chuyển nhu cầu thực tế thành tiêu chí kiểm chứng được, so sánh phương án bằng trade-off và bằng chứng, ghi nhận lựa chọn cùng hệ quả, rồi điều chỉnh khi dữ kiện thay đổi**.

Một thiết kế tốt không nhất thiết có nhiều dịch vụ, nhiều pattern, nhiều tầng trừu tượng hay công cụ mới. Nó cần giải quyết **đúng vấn đề, trong ràng buộc hiện tại, với chi phí chấp nhận được và đường thay đổi hợp lý**. Chọn kiến trúc là chọn cả những khó khăn mà nhóm sẵn sàng chịu trách nhiệm; mô hình phù hợp hôm nay có thể cần được xem lại khi sản phẩm, tải và tổ chức thực sự thay đổi.
