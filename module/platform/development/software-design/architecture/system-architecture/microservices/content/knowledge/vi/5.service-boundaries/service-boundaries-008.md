# Gộp lại dịch vụ khi ranh giới làm tăng chi phí không cần thiết

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Ranh giới dịch vụ  
> **Mục tiêu:** Nhận diện khi việc phân tách thành nhiều dịch vụ đang làm hệ thống khó thay đổi, tốn công vận hành hoặc giảm độ tin cậy; đánh giá có nên gộp lại hay không; và thực hiện việc gộp có kiểm soát, vẫn bảo vệ những ranh giới nghiệp vụ quan trọng.

## 1. Bối cảnh: chia nhỏ là một quyết định, không phải đích đến

Một hệ thống có nhiều microservice không tự động tốt hơn một hệ thống ít dịch vụ. Giá trị của ranh giới dịch vụ nằm ở việc nó tạo ra sự **độc lập hữu ích**: sở hữu rõ ràng, thay đổi và triển khai độc lập, giới hạn lỗi, mở rộng tải hoặc bảo vệ một miền nghiệp vụ riêng. Mỗi ranh giới chạy qua mạng cũng kéo theo chi phí giao tiếp, quản trị hợp đồng, kiểm thử, triển khai, vận hành, quan sát và xử lý dữ liệu phân tán.

Trong những hệ thống đã phân rã quá mức, một tác vụ đơn giản phải đi qua nhiều API, nhiều pipeline và nhiều nhóm. Lúc đó, dịch vụ có thể tách riêng về tiến trình nhưng vẫn **gắn chặt về nghiệp vụ và chu kỳ thay đổi**. Nếu lợi ích độc lập nhỏ hơn chi phí, gộp lại một số dịch vụ có thể là quyết định kiến trúc hợp lý.

**Gộp dịch vụ** ở đây là hợp nhất một hoặc nhiều đơn vị triển khai/vận hành thành một đơn vị phù hợp hơn, đồng thời chủ động thiết kế lại cách các module và trách nhiệm tương tác. Gộp không nhất thiết biến mọi thứ thành “một khối code không cấu trúc”, và cũng không buộc xóa các **bounded context** đã được xác định đúng. Có thể giữ các context thành những module rõ hợp đồng trong một ứng dụng **modular monolith**.

### Kết quả mong đợi sau bài học

Người học có thể:

- Phân biệt ranh giới miền nghiệp vụ, ranh giới module, ranh giới tiến trình và ranh giới đội ngũ.
- Nhận biết những chi phí phát sinh khi dịch vụ tách rời nhưng phải thay đổi hoặc vận hành cùng nhau.
- Dùng bằng chứng về coupling, độ trễ, độ tin cậy, dữ liệu, release và ownership để đánh giá ứng viên gộp.
- So sánh gộp dịch vụ với các lựa chọn nhẹ hơn như sửa API, giảm lời gọi mạng, caching hoặc thiết kế lại luồng.
- Lập kế hoạch migration, bảo đảm tương thích, quản lý dữ liệu, rollout, giám sát và rollback.
- Tránh phá vỡ những ranh giới cần thiết cho bảo mật, tải, vòng đời dữ liệu hoặc khả năng chịu lỗi.

## 2. Bốn loại ranh giới cần tách bạch

Trước khi tranh luận “có nên gộp hai service?”, phải xác định đang nói đến ranh giới nào.

| Loại ranh giới | Ý nghĩa | Ví dụ | Có bắt buộc trùng ranh giới deploy? |
| --- | --- | --- | --- |
| **Bounded context** | Phạm vi một mô hình/ngôn ngữ nghiệp vụ có nghĩa nhất quán | Payments, Ordering, Inventory | Không |
| **Module/package** | Ranh giới phụ thuộc trong mã nguồn và API nội bộ | commerce.pricing, commerce.promotion | Không |
| **Process/deployable** | Đơn vị được build, chạy, scale, triển khai và theo dõi | pricing-service, promotion-service | Chính là ranh giới deploy |
| **Team/ownership** | Nhóm quyết định và chịu trách nhiệm thay đổi/vận hành | Commerce team, Payment team | Không, nhưng cần khớp trách nhiệm thực tế |

Một bounded context có thể nằm trong cùng tiến trình với context khác mà vẫn giữ dữ liệu, quy tắc và ngôn ngữ tách biệt qua module. Ngược lại, tách hai tiến trình không đảm bảo tách được coupling nếu chúng dùng chung bảng, chuyển tiếp yêu cầu qua nhau hoặc luôn release cùng nhau.

Ví dụ:

~~~text
Trước:
 [Pricing service] <---HTTP---> [Promotion service]
          \                 /
            cùng 1 team
            cùng đợt release

Sau:
 [Commerce deployable]
     |-- Pricing module
     |-- Promotion module
     |-- Contract nội bộ rõ ràng

Các bounded context có thể vẫn được giữ riêng
trong một đơn vị triển khai.
~~~

**Số lượng service không phải chỉ số chất lượng kiến trúc.** Câu hỏi quan trọng là độ độc lập đạt được có xứng đáng với chi phí phân tán hay không.

## 3. Những chi phí ranh giới dịch vụ thường tạo ra

### 3.1. Chi phí giao tiếp và độ trễ

Một lời gọi trong cùng tiến trình thường đơn giản hơn một lần gọi qua mạng. Khi chuyển qua ranh giới tiến trình, hệ thống có thêm serialization, authentication, service discovery, network hop, timeout, retry, circuit breaker, tracing và handling các trường hợp “không biết phía kia đã xử lý hay chưa”.

Nếu một luồng phải gọi tuần tự A → B → C → D, thời gian phản hồi chịu ảnh hưởng từ tất cả bước. Khi các bước có sự cố hoặc tăng độ trễ cùng lúc, tail latency có thể xấu đi rõ rệt. Cache hoặc lời gọi song song có thể giảm một phần chi phí, nhưng không thay thế việc xem lại sự cần thiết của các ranh giới.

Ví dụ giả định: một request tiêu tốn trung bình 35 ms tại A, 50 ms tại B, 40 ms tại C và 60 ms tại D, chưa kể mạng. Nếu tất cả bắt buộc gọi **tuần tự** thì đường xử lý này đã có khoảng 185 ms xử lý nội bộ; tối ưu một service riêng lẻ không giải quyết triệt để độ dài chuỗi phụ thuộc. Con số chỉ là minh họa, không phải công thức trực tiếp để suy ra p95 hoặc p99.

### 3.2. Chi phí độ tin cậy và xử lý lỗi

Giả sử một luồng bắt buộc bốn thành phần đều hoạt động; nếu từng thành phần độc lập có độ sẵn sàng 99,5% và ta tạm giả định các lỗi **độc lập**, xác suất cả bốn cùng sẵn sàng khoảng:

\[
0{,}995^4 \approx 98{,}01\%
\]

Đây là mô hình minh họa để thấy tác động của chuỗi phụ thuộc, không phải dự đoán availability thực tế: lỗi thường có tương quan, có cache/fallback, thay đổi tải và nhiều loại request. Điểm cốt lõi là một dịch vụ tưởng như nhỏ có thể trở thành điểm phụ thuộc bắt buộc của nhiều giao dịch.

Tách nhiều tiến trình cũng khiến các tình huống khó hơn: nhận response trễ, retry tạo trùng thao tác, idempotency, mạng phân vùng, xử lý lỗi từng phần, phát event nhưng consumer chưa xử lý, hoặc rollback nhiều bước.

### 3.3. Chi phí phát triển và phối hợp

Các dấu hiệu thường gặp:

- Một user story luôn sửa đồng thời hai hoặc ba repo.
- Đội ngũ không dám release A trước khi B chạy phiên bản tương thích.
- Một thay đổi nhỏ phải tạo API contract, mock, integration test, stage test và nhiều pull request.
- Ownership không tách được: cùng một nhóm chịu trách nhiệm tất cả các service nhưng phải duy trì nhiều on-call dashboard, alert, CI/CD.
- Khi cần debug phải ghép log và trace từ nhiều ứng dụng cho một quy tắc nghiệp vụ duy nhất.

**Triển khai độc lập** có giá trị khi các nhóm thật sự có thể thay đổi độc lập. Nếu một cặp service luôn đi cùng một release, phần độc lập trên sơ đồ chưa tạo ra ích lợi.

### 3.4. Chi phí dữ liệu và nhất quán

Khi một quy tắc nghiệp vụ cần dữ liệu từ hai service, nhóm thường phải chọn giữa đồng bộ từ xa, chấp nhận eventual consistency, projection dữ liệu hoặc luồng bù. Mỗi cách có chi phí riêng.

Ví dụ: tính giá cuối cùng cho giỏ hàng cần giá cơ sở, mức giảm áp dụng, điều kiện voucher và ngưỡng miễn phí vận chuyển. Nếu cùng một quyết định nghiệp vụ mà dữ liệu bị chia rời không có lý do rõ ràng, việc điều phối giữa nhiều service có thể gây race condition hoặc khiến người dùng nhận giá không nhất quán.

Tuy nhiên, **khó nhất quán không mặc nhiên có nghĩa phải gộp**. Có trường hợp nhiều chủ sở hữu dữ liệu độc lập là yêu cầu đúng của miền nghiệp vụ; cần đổi quy trình, luồng sự kiện hoặc định nghĩa giao dịch thay vì xóa ranh giới.

### 3.5. Chi phí vận hành và hạ tầng

Mỗi service thường cần image, môi trường chạy, cấu hình, secret, health check, autoscaling, dashboard, alert, log, tracing, pipeline và chính sách phân quyền riêng. Chi phí này có thể nhỏ với nền tảng đã tự động hóa tốt, nhưng rất lớn với đội chưa có năng lực platform engineering.

Gộp có thể giảm một số chi phí cố định. Tuy nhiên, nếu sau gộp cả khối phải scale để xử lý một chức năng tiêu thụ tài nguyên lớn, chi phí compute có thể tăng. Vì vậy phải đo cả **chi phí trước và sau**, không lấy số lượng container làm proxy duy nhất.

## 4. Dấu hiệu ranh giới hiện tại có thể đang không phù hợp

Không có một ngưỡng chung áp dụng cho mọi sản phẩm. Nên xem **mẫu hình nhiều bằng chứng cùng xuất hiện**, không quyết định chỉ từ một metric.

| Dấu hiệu quan sát | Có thể chỉ ra điều gì | Bằng chứng nên tìm |
| --- | --- | --- |
| Hai service thường xuyên sửa cùng một yêu cầu nghiệp vụ | Coupling về chu kỳ thay đổi | Git history, issue, release notes, PR liên quan |
| Chuỗi gọi đồng bộ nhiều hop trong một request | Chi phí độ trễ, điểm lỗi phụ thuộc | Distributed tracing, service map, p95/p99 |
| A gọi B rồi B gọi ngược A để hoàn thành một quyết định | Ranh giới có vòng phụ thuộc hoặc thiếu nguồn quyết định | Call graph, sequence diagram, incident |
| Hai service được deploy cùng lúc và ít khi độc lập | Lợi ích triển khai độc lập chưa xuất hiện | Deployment logs, calendar, change history |
| Cùng một team sở hữu cả hai, trực on-call và quản lý lỗi chung | Overhead của nhiều đơn vị vận hành | Ownership map, lịch on-call, runbook |
| Hai service cần transaction xuyên mạng cho phần lớn use case | Ranh giới cắt ngang một bất biến nghiệp vụ | Quy tắc business, transaction trace, lỗi đền bù |
| Có nhiều event chỉ để chuyển tiếp ngay một lệnh sang service khác | Độ phức tạp phân tán chưa tạo ích lợi | Message flows, event schema, tỷ lệ consumer |
| Đối tượng nghiệp vụ bị chia tùy tiện thành nhiều “CRUD service” | Phân rã theo bảng/danh từ hơn là hành vi | Domain model, command ownership |
| Thời gian khôi phục sự cố tăng vì phụ thuộc vòng tròn | Trách nhiệm vận hành khó phân định | Postmortem, MTTR, escalation log |

Ngược lại, một chuỗi gọi API dài có thể do thiết kế aggregation chưa tốt. Cần phân biệt vấn đề **ranh giới service** với vấn đề **cách tương tác**.

### Những câu hỏi kiểm chứng ban đầu

1. Điều gì yêu cầu hai dịch vụ phải độc lập hôm nay? Lý do ấy còn hiệu lực không?
2. Nếu gộp hai deployment, chức năng nào sẽ mất khả năng scale hoặc release riêng?
3. Quy tắc nghiệp vụ nào thực sự cần transaction cùng chỗ?
4. Các phần có dùng một ngôn ngữ miền thống nhất hay vẫn thuộc những context khác nhau?
5. Một lỗi trong phần A có thể làm sập phần B sau gộp không? Cần giới hạn tài nguyên bằng cơ chế nào?
6. Có yêu cầu pháp lý, phân quyền, lưu trữ hoặc kiểm toán khiến phải giữ ranh giới chạy riêng không?
7. Nếu chưa gộp, có cách giảm phần lớn chi phí bằng sửa API, cache, event flow hoặc ownership không?

## 5. Khi nào không nên gộp

Việc gộp chỉ hợp lý nếu lợi ích ròng rõ ràng và rủi ro có thể kiểm soát. Những trường hợp cần giữ độc lập hoặc đánh giá đặc biệt thận trọng:

- **Nhu cầu scale khác biệt:** xử lý video, machine learning inference hoặc dữ liệu streaming cần nhiều CPU/GPU trong khi API nghiệp vụ nhẹ, có yêu cầu latency khác.
- **Giới hạn lỗi quan trọng:** hệ thống gửi thông báo hoặc tính report có thể bị nghẽn và không được làm sập luồng thanh toán.
- **Ranh giới bảo mật/tuân thủ:** Payment có vùng kiểm soát dữ liệu thẻ, secret và quyền truy cập riêng. Gộp vào ứng dụng chung có thể mở rộng phạm vi cần kiểm soát.
- **Vòng đời triển khai độc lập đã được chứng minh:** hai team có roadmap, release cadence và SLA khác nhau, thậm chí phụ thuộc nhau nhưng qua hợp đồng ổn định.
- **Khác biệt rõ về ngôn ngữ và quy tắc nghiệp vụ:** việc hợp nhất code làm một mô hình chung sẽ phá tính đúng của bounded context.
- **Quy mô tổ chức hoặc nhiều tenant:** yêu cầu cô lập hiệu năng, vùng dữ liệu hoặc thay đổi ở các đơn vị kinh doanh.
- **Tải giao tiếp thấp và vận hành đã tối ưu:** không có chi phí đủ lớn để biện minh cho một cuộc migration nhiều rủi ro.

Đôi khi đúng là giữ hai deployable nhưng cải thiện contract, batching, caching hoặc chuyển một bước sang xử lý không đồng bộ. Nên so sánh lựa chọn đó bằng cùng hệ tiêu chí với phương án gộp.

## 6. Khung quyết định dựa trên bằng chứng

Một đánh giá có thể thực hiện qua năm chiều: **business coupling, deployment coupling, runtime coupling, data consistency, operational cost**.

### 6.1. Business coupling

Hỏi:

- Các quy tắc và thuật ngữ có thay đổi cùng nhau không?
- Cùng người/nhóm nghiệp vụ quyết định tính đúng đắn không?
- Có chung hành trình nghiệp vụ cốt lõi hay chỉ thường dùng dữ liệu của nhau?
- Hợp nhất có khiến một context phải dùng mô hình không đúng của context khác không?

Nếu cùng một quyết định nghiệp vụ liên tục bị cắt ngang hai process và không có chủ thể sở hữu rõ ràng, đó là dấu hiệu mạnh để xem lại ranh giới.

### 6.2. Deployment coupling

Đo trong một khoảng đại diện (ví dụ 8–12 tuần hoặc một vài release cycle, tùy nhịp sản phẩm):

- Tỷ lệ thay đổi ở A buộc B phải thay đổi cùng.
- Số deployment A/B độc lập so với deployment phối hợp.
- Số contract break hoặc incident do version lệch.
- Lead time từ lúc thay đổi được chấp thuận tới lúc chạy sản xuất.
- Số team và handoff cần có cho một user story.

Không coi “hai repo cùng merge một ngày” là bằng chứng đủ mạnh: các thay đổi có thể độc lập về nghiệp vụ. Cần xác định quan hệ nhân quả.

### 6.3. Runtime coupling

Tìm trên trace thực tế:

- Phần trăm request của A bắt buộc gọi B.
- Số hop tuần tự ở critical path, fan-out và timeout.
- Latency theo endpoint, p95/p99 và service dependency.
- Số lần retry, lỗi transitive, failover và degraded mode.
- Tỷ trọng network/serialization so với thời gian xử lý nghiệp vụ.

Không cộng trực tiếp các p95 cá thể để khẳng định p95 của chuỗi. Ưu tiên trace end-to-end và phân tích phân phối thực tế.

### 6.4. Data và consistency coupling

Hỏi:

- Quy tắc bất biến phải cập nhật nguyên tử qua A/B thường xuyên đến đâu?
- Service nào sở hữu dữ liệu gốc của từng thực thể?
- B có chỉ là bản sao CRUD của A mà không có quyết định nghiệp vụ riêng?
- Những luồng bù/saga hiện tại xuất hiện do nhu cầu miền nghiệp vụ hay do ranh giới triển khai tùy ý?
- Đang có shared database hoặc join trực tiếp xuyên sở hữu không?

Một cơ sở dữ liệu dùng chung không mặc nhiên có nghĩa nên gộp service. Có thể cần sửa quyền sở hữu dữ liệu, bổ sung API/projection hoặc di chuyển từng capability.

### 6.5. Operational coupling

Theo dõi:

- Chi phí hạ tầng, môi trường và tài nguyên tối thiểu cho từng service.
- Công duy trì pipeline, secret, dashboard, alert và dependency update.
- Số incident cần cùng nhiều nhóm xử lý; MTTR thực tế.
- Mức độ dễ thực hiện rollback và tìm nguyên nhân lỗi.
- Chi phí phát triển và vận hành do việc đồng bộ phiên bản.

Định lượng cần tránh “giả chính xác”. Có thể dùng điểm định tính kèm bằng chứng, nhưng không coi điểm số là công thức bắt buộc.

### 6.6. Ma trận quyết định tham khảo

| Tiêu chí | Khả năng nghiêng về gộp | Khả năng nghiêng về giữ riêng |
| --- | --- | --- |
| Thay đổi nghiệp vụ | Luôn cùng thay đổi, cùng chủ quyết định | Thay đổi và release độc lập rõ ràng |
| Runtime | Nhiều lời gọi đồng bộ trên critical path | Giao tiếp ít, ổn định, chịu trễ tốt |
| Data | Một bất biến bị cắt ngang hai service liên tục | Hai nguồn sự thật và lifecycle khác biệt |
| Vận hành | Overhead lớn hơn lợi ích cô lập | On-call, SLO và trách nhiệm độc lập hiệu quả |
| Scale | Mức tải gần tương tự | Có một phần cần scale cực khác biệt |
| Fault isolation | Lỗi thường lan qua cả hai vì phụ thuộc chặt | Có thể cô lập lỗi thành công khi tách |
| Security | Không có miền tin cậy khác biệt đáng kể | Có kiểm soát bảo mật/tuân thủ riêng |

Mọi kết luận nên dựa trên bối cảnh cụ thể và phải ghi rõ giả định.

## 7. So sánh chi phí tổng thể trước khi chọn phương án

Có thể dùng một mô hình suy nghĩ thay vì chỉ đếm dịch vụ:

~~~text
Tổng chi phí kiến trúc theo thời gian
  = chi phí vận hành
  + chi phí thay đổi và phối hợp
  + tổn thất do lỗi/độ trễ
  + chi phí dữ liệu và tính nhất quán
  + chi phí chuyển đổi/di trú
  + chi phí mất những lợi ích độc lập
~~~

Trong đánh giá, nên phân tách **chi phí một lần** (migration) và **chi phí lặp lại** (CI/CD, hỗ trợ on-call, latency, incident, phát triển chức năng). Một phương án gộp có thể tiết kiệm mỗi tháng nhưng quá rủi ro nếu phá cơ chế cô lập mà sản phẩm thật sự cần.

### Ví dụ định lượng mang tính giả định

Giả sử hai service **Pricing** và **Promotion** do một team duy trì:

| Chỉ số giả định trong 90 ngày | Quan sát |
| --- | --- |
| Các user story làm thay đổi cả Pricing và Promotion | 21/25 story liên quan định giá |
| Đợt release phải phối hợp hai service | 14/16 đợt |
| Request tính tổng tiền phải gọi qua cả hai | 93% |
| Incident có liên quan lỗi tích hợp/version giữa hai service | 5 incident |
| Hai service có yêu cầu bảo mật và scale tương đương | Đúng trong phạm vi đo |
| Lợi ích về team ownership độc lập | Chưa có, cùng một team |

Các số này **không phải dữ liệu thực tế**. Chúng thể hiện một tình huống có nhiều bằng chứng tương hợp cho phương án hợp nhất deployable. Nhưng trước khi gộp, vẫn cần chứng minh SLO không xấu đi, không phát sinh nghẽn tài nguyên, module giữ được quy tắc riêng và có đường di chuyển dữ liệu an toàn.

Một business case thực tế nên ghi *baseline → phương án A/B/C → chỉ số kỳ vọng → rủi ro → điều kiện dừng*, không chỉ nêu “giảm từ hai service xuống một”.

## 8. Những phương án cần so sánh trước khi hợp nhất

Giữa trạng thái hiện tại và gộp toàn bộ có nhiều mức can thiệp.

| Phương án | Cách làm | Khi phù hợp | Giới hạn |
| --- | --- | --- | --- |
| Giữ service, sửa API | Hợp nhất endpoint nhiều lần gọi, batch request, giảm chatty calls | Coupling chính là giao tiếp kém hiệu quả | Vẫn có runtime/deployment boundary |
| Giữ service, thay cách truyền dữ liệu | Cache, projection, async event, query model | Có thể chịu eventual consistency hoặc dữ liệu đọc lặp | Thêm invalidation/schema complexity |
| Giữ service, tối ưu platform | Template, shared observability, CI/CD, version policy | Overhead vận hành do thiếu tự động hóa | Không chữa business coupling |
| Gộp triển khai nhưng vẫn module hóa | Một deployable, các module có API nội bộ rõ | Team chung, release luôn cùng, cần giảm chi phí phân tán | Scale/release không còn riêng |
| Gộp cả ranh giới mô hình | Một module/aggregate hoặc một quy tắc chủ sở hữu | Ranh giới nghiệp vụ cũ thực sự sai | Có thể tạo mô hình quá lớn nếu kết luận vội |
| Giữ một ranh giới, sửa ownership | Xác lập team và trách nhiệm, hợp đồng | Hai domain độc lập nhưng team/process đang rối | Không giảm số process |

Không nên “gộp để hết gọi mạng” rồi tạo các import chéo, dùng bảng chung và một module khổng lồ không kiểm soát. Gộp tiến trình có thể là hợp lý, nhưng **phụ thuộc mã nguồn phải tiếp tục có hướng và luật rõ ràng**.

## 9. Ví dụ chính: gộp Pricing và Promotion trong nền tảng thương mại điện tử

### 9.1. Hiện trạng

Sơ đồ giả định:

~~~text
             [Checkout API]
                   |
                   v
            [Pricing service]
                   |
           HTTP: áp dụng voucher
                   v
           [Promotion service]
                   |
            HTTP: lấy giá gốc
                   v
            [Pricing service]
~~~

Pricing sở hữu bảng giá; Promotion sở hữu các điều kiện giảm giá. Nhưng một số quy tắc tính tổng tiền cần cả giá và khuyến mãi để quyết định. Có vòng gọi, thêm biến động do timeout, đồng thời mọi thay đổi nghiệp vụ định giá thường kéo theo chỉnh sửa cả hai service. Cả hai do một Commerce team trực on-call và triển khai.

**Vấn đề không chỉ là hai service**: vòng gọi cho thấy chưa rõ nơi nào chịu trách nhiệm quyết định “giá thanh toán cuối cùng”. Cần xác định điều đó trước khi chọn cách gộp.

### 9.2. Ranh giới đích

Một thiết kế ứng viên:

~~~text
[Checkout API]
      |
      v
[Commerce deployable]
   +--------------------------------------+
   | Checkout-facing Pricing Application  |
   |     |                    |           |
   |     v                    v           |
   | Pricing module    Promotion module   |
   |  (giá cơ sở)      (điều kiện ưu đãi) |
   |     \                    /           |
   |      v                  v            |
   |     Quote/Price Decision             |
   +--------------------------------------+

Bên ngoài nhìn thấy hợp đồng báo giá ổn định.
Module bên trong có trách nhiệm và dependency rõ.
~~~

Các lựa chọn cần chốt trong domain:

- Ai chịu trách nhiệm xác định **số tiền cuối cùng** và thuật ngữ “báo giá có hiệu lực”?
- Giá đã báo cho khách được giữ bao lâu? Giá mới có ảnh hưởng đơn đã đặt không?
- Một voucher được áp dụng nhiều lần không? Điều kiện giới hạn usage áp dụng tại thời điểm nào?
- Có cần snapshot kết quả tính giá gắn vào Order trước khi chuyển sang Payment không?
- Tính năng khuyến mãi có phải bounded context thật sự độc lập hay là một policy trong Pricing?

Nếu Promotion có mô hình nghiệp vụ riêng đủ mạnh, có thể giữ **Promotion module** bên trong cùng deployable và giao tiếp qua interface. Việc gộp hạ tầng không buộc xóa ngôn ngữ và bất biến của Promotion.

### 9.3. Cấu trúc module ví dụ bằng Java

~~~text
commerce/
  application/
    QuoteService.java
  pricing/
    api/
      PricingPort.java
    domain/
      PriceRule.java
      PriceAmount.java
  promotion/
    api/
      PromotionPort.java
    domain/
      PromotionPolicy.java
      VoucherEligibility.java
  checkout/
    api/
      CheckoutFacade.java
  infrastructure/
    persistence/
    http/
~~~

Trong cùng process, application service phối hợp hai module qua interface đã định nghĩa:

~~~java
public final class QuoteService {
    private final PricingPort pricing;
    private final PromotionPort promotion;

    public QuoteService(PricingPort pricing, PromotionPort promotion) {
        this.pricing = pricing;
        this.promotion = promotion;
    }

    public Quote quote(QuoteRequest request) {
        BasePrice base = pricing.resolveBasePrice(request.items());
        Discount discount = promotion.evaluate(
            request.customerId(), request.voucher(), base);
        return Quote.from(base, discount);
    }
}
~~~

Đây là pseudo-implementation để minh họa hướng phụ thuộc. Quy tắc voucher dùng nhiều lần, bất biến thanh toán và transaction boundary cần thiết kế riêng. Code dùng interface nội bộ, không yêu cầu service Pricing gọi HTTP sang Promotion rồi gọi ngược.

### 9.4. Cần đo điều gì sau gộp?

- Latency của **tính tổng tiền end-to-end**, không chỉ đo một phương thức Java.
- Số lỗi do timeout/contract mismatch và retry trong luồng báo giá.
- Lead time và số deployment cần thiết cho một tính năng giá/khuyến mãi.
- Chi phí bộ nhớ/CPU của deployable mới khi có chiến dịch lớn.
- Độ độc lập thay đổi giữa pricing và promotion module qua module boundary checks.
- Tính đúng của giá báo, thứ tự áp dụng giảm giá, rounding và trường hợp voucher hết hạn.

Nếu một chiến dịch voucher tạo tải rất khác báo giá thông thường, nên cân nhắc tách riêng khâu phân tích chiến dịch hoặc tính toán nặng trong nền/background. Gộp không có nghĩa mọi workload bắt buộc chạy trong một luồng đồng bộ.

## 10. Phản ví dụ: vì sao có cặp service vẫn nên giữ tách

### 10.1. Ordering và Payments

Ordering cần biết khoản thanh toán đã được chấp nhận, nhưng Payments sở hữu việc tương tác với cổng thanh toán, hoàn tiền, đối soát và quyền truy cập vào dữ liệu nhạy cảm. Hai context có thể có tiêu chuẩn bảo mật, quy trình kiểm toán, runbook và failure mode rất khác nhau.

Ngay cả khi một luồng đặt hàng luôn gọi Payments, đây chưa phải căn cứ đủ để gộp. Một lựa chọn tốt có thể là:

- Ordering phát lệnh yêu cầu thanh toán qua hợp đồng rõ ràng.
- Payments ghi nhận kết quả thực và công bố event phù hợp.
- Ordering phản ứng và cập nhật trạng thái đơn.
- Khi kết quả tạm thời chưa rõ, UI phản ánh trạng thái chờ/đối soát.
- Thử lại và hủy phải có idempotency/timeout rõ ràng.

Điều cần sửa có thể là giao thức và quy tắc kết thúc đơn, không phải ranh giới triển khai.

### 10.2. Reporting và luồng giao dịch

Reporting đọc rất nhiều dữ liệu và chấp nhận độ trễ, còn Checkout phải phản hồi trong vài trăm mili giây. Việc gộp reporting nặng vào checkout có thể gây cạnh tranh CPU/connection pool và khuếch đại sự cố. Nếu chỉ vì hai nhóm dùng cùng dữ liệu mà gộp, hệ thống có thể tệ hơn.

Giải pháp thường là dữ liệu projection/read model, bất đồng bộ hoặc kho phân tích tách biệt.

## 11. Quy trình gộp dịch vụ có kiểm soát

Quá trình migration phải được thiết kế như một sự thay đổi có thể quan sát, dừng lại và khôi phục được. Không nên đổi toàn bộ API, database và runtime cùng lúc nếu có thể đi theo từng bước.

### Giai đoạn 1 — Xác định vấn đề và baseline

Thu thập số liệu trước khi thay đổi:

1. Danh sách capability, API, consumer, job, event, database, secret và các service phụ thuộc.
2. Đường đi end-to-end của các use case quan trọng.
3. Release cadence, lead time, tần suất thay đổi phối hợp, incident và MTTR.
4. p50/p95/p99, error rate, throughput, CPU, memory, queue lag.
5. Chi phí vận hành hiện tại, các SLO và giới hạn bảo mật.
6. Điều kiện thành công/điều kiện dừng và người chịu trách nhiệm cutover.

**Không ghi “microservice quá nhiều” thành vấn đề**; viết một phát biểu có thể kiểm chứng, chẳng hạn: “Luồng báo giá có ba hop đồng bộ bắt buộc, nhóm Commerce phải phối hợp release 80% thay đổi về giá và gặp lỗi version mismatch nhiều lần”.

### Giai đoạn 2 — Làm rõ miền nghiệp vụ và ranh giới đích

Tổ chức workshop với kỹ sư và chuyên gia nghiệp vụ; sử dụng Event Storming, context mapping hoặc các luồng use case có dữ liệu thật:

- Xác định command, event, quy tắc, aggregate và invariant.
- Chỉ rõ source of truth cho từng khái niệm.
- Tách **hợp nhất deployable** khỏi **hợp nhất domain model**.
- Xác định package/module API, chiều phụ thuộc và chủ sở hữu.
- Khoanh dữ liệu sẽ di chuyển và phần nào giữ nguyên.

Một kết quả có thể là một deployable gồm hai module riêng schema; hoặc một module chung vì thật sự chỉ có một mô hình nghiệp vụ. Hai phương án không tương đương.

### Giai đoạn 3 — Lập inventory hợp đồng hiện hữu

Không chỉ liệt kê các REST endpoint đã biết. Cần bao gồm:

| Loại hợp đồng | Ví dụ | Điểm cần kiểm |
| --- | --- | --- |
| API đồng bộ | POST /quotes, GET /prices | Client nào gọi, timeout, version, auth, error semantics |
| Async event | PriceChanged, PromotionActivated | Producer/consumer, schema, replay, ordering |
| Batch/job | Đồng bộ bảng giá theo ngày | Lịch chạy, retry, idempotency |
| Data access | Bảng giá, voucher usage | Data owner, transaction, retention, migration |
| Operational contract | Health check, metric, log, alert | Dashboard, on-call, runbook |
| Security boundary | OAuth scope, secret, network policy | Quyền truy cập và kiểm soát tuân thủ |

Trong thực tế, consumer “vô hình” như báo cáo, ETL, automation hoặc script tích hợp thường là nguồn rủi ro. Không chỉ đọc code trong hai service mà cần xác nhận những client đang dùng hợp đồng công khai.

### Giai đoạn 4 — Tạo cấu trúc module mới và giữ hợp đồng bên ngoài

Một chiến lược ít rủi ro là xây **đơn vị triển khai mới với API tương thích**, chuyển dần logic của từng phần vào module có interface rõ. Duy trì contract cũ trong một thời gian qua gateway hoặc adapter nếu client chưa thể đổi.

Ví dụ:

~~~text
Client A/B
   |
   v
API Gateway
   |             giai đoạn chuyển tiếp
   +-- /prices ------> Commerce / Pricing module
   +-- /promotions --> Commerce / Promotion module

Internal:
   Pricing API <-> Application orchestration <-> Promotion API
   Không gọi HTTP vòng giữa 2 module
~~~

Sau khi client cập nhật, có thể đơn giản hóa API/public contract; không cần xóa một endpoint chỉ vì service cũ đã biến mất.

**Định nghĩa rõ module interface:** một module chỉ công bố những thao tác mà context khác được phép dùng. Không truy cập trực tiếp class hoặc bảng “nội bộ” của module khác chỉ vì đang cùng JVM.

### Giai đoạn 5 — Thiết kế kế hoạch di chuyển dữ liệu

Đây thường là phần khó nhất. Cần nắm nguồn sự thật và cách chuyển quyền ghi:

- Chọn nơi chứa dữ liệu đích: cùng database nhưng tách schema, database riêng, hoặc hợp nhất cấu trúc khi thực sự đúng miền.
- Xác định các bảng/record thuộc quyền sở hữu của từng module.
- Thiết lập mapping ID, khóa duy nhất, encoding, rounding số tiền và ràng buộc dữ liệu.
- Chọn phương án snapshot + catch-up/CDC hoặc di chuyển có cửa sổ bảo trì, tùy lượng dữ liệu và downtime cho phép.
- Xác nhận cách xử lý sự kiện, job, webhook đang chạy khi cutover.
- Có phương án đối soát: record count, checksum hợp lý, tổng tiền, invariant nghiệp vụ và các bản ghi ngoại lệ.

**Không tạo hai writer độc lập cho cùng một sự thật mà thiếu cơ chế bảo vệ.** Dual-write trực tiếp giữa hai database dễ dẫn đến tình trạng một bên thành công, bên còn lại thất bại. Nếu phải đồng bộ trong thời gian chuyển tiếp, cần định rõ nguồn ghi chính, chiến lược replication, idempotency, reconciliation và tiến trình chuyển quyền sở hữu.

Gộp process không tự động đòi hỏi gộp toàn bộ bảng dữ liệu. Giữ schema/ownership riêng trong modular monolith có thể giúp giảm coupling mã nguồn và dễ tách lại sau này.

### Giai đoạn 6 — Di chuyển hành vi từng lát nhỏ

Chọn một vertical slice có phạm vi kiểm soát được, ví dụ tính giá cho giỏ không có voucher, rồi đến các loại khuyến mãi. Mỗi lát cần giữ hợp đồng và hành vi tương thích đã thống nhất.

Một thứ tự tham khảo:

1. Đưa logic nghiệp vụ tương đương vào module mới và xây adapter tương thích.
2. Chạy kiểm tra đặc tính quan trọng và so sánh kết quả dựa trên dữ liệu/kịch bản thật đã ẩn danh.
3. Với thao tác **đọc thuần túy**, cân nhắc shadow read và so sánh mà không ảnh hưởng kết quả gửi người dùng.
4. Với thao tác **ghi hoặc có tác dụng phụ**, không shadow-write tùy tiện; dùng dữ liệu thử hoặc cơ chế kiểm soát nghiêm ngặt để tránh tính tiền/giữ hàng hai lần.
5. Chuyển một tỷ lệ traffic nhỏ hoặc một nhóm client khi có cơ chế routing tương ứng.
6. Theo dõi latency, lỗi, sai lệch dữ liệu và resource contention trước khi mở rộng.

Không nên gộp tất cả endpoint trong một cutover lớn nếu có thể giảm rủi ro bằng bước chuyển tiếp.

### Giai đoạn 7 — Cutover, giám sát và sẵn sàng phục hồi

Thiết lập trước:

- **Feature flag/routing switch** cho mỗi tuyến quan trọng, với quyền thao tác rõ.
- Dashboard so sánh hệ thống cũ/mới: business success, p95/p99, error rate, CPU, memory, queue lag, bất biến dữ liệu.
- Alert riêng cho tác vụ hậu cutover, không chỉ theo dõi HTTP 5xx.
- Điểm dừng khi sai lệch giá, double charge, lỗi không thể khôi phục hoặc vượt SLO.
- Runbook cho timeout, retry, reconcile và sự cố hạ tầng.

**Rollback code không đồng nghĩa rollback dữ liệu.** Nếu đã chuyển nguồn ghi hoặc đổi schema không tương thích, quay về binary cũ có thể sai. Với các migration khó đảo ngược, cần ưu tiên tương thích theo mô hình **expand → migrate → contract** hoặc có hướng **forward recovery** đã thử nghiệm.

### Giai đoạn 8 — Decommission có bằng chứng

Sau khi traffic và consumer đã chuyển:

- Xác minh không còn client, job hoặc event consumer đang sử dụng endpoint cũ.
- Chờ hết thời gian retry, TTL, backlog và retention phù hợp.
- Đối soát lần cuối dữ liệu đã chuyển và trạng thái các message chưa xử lý.
- Chuyển dashboard/on-call/runbook, xóa cấu hình bí mật không dùng nữa theo quy trình.
- Chỉ tắt service và giải phóng hạ tầng khi các phụ thuộc đã được kiểm chứng.
- Cập nhật sơ đồ kiến trúc, catalog service và ADR.

Nếu service cũ bị tắt quá sớm, lỗi có thể chỉ lộ ra ở batch cuối tháng hoặc ở client chạy phiên bản cũ.

## 12. Kiểm soát chất lượng module sau khi gộp

Một modular monolith là lựa chọn hữu ích khi giữ được **modularity thật**, không chỉ đặt code vào những thư mục khác nhau.

### Hướng phụ thuộc và API công khai

Ví dụ quy ước:

~~~text
commerce.pricing.api       <- application sử dụng
commerce.pricing.internal  <- chỉ pricing truy cập

commerce.promotion.api     <- application sử dụng
commerce.promotion.internal<- chỉ promotion truy cập

Không cho promotion.internal import pricing.internal
Không cho checkout đọc trực tiếp bảng voucher
~~~

Có thể áp dụng package visibility, module boundaries, ArchUnit hoặc kiểm tra dependency graph trong CI để ngăn import nội bộ xuyên module. Mục đích là làm **coupling hiển thị và có luật**, không tự động tái tạo distributed architecture trong một process.

### Chỉ rõ transaction boundary

Việc dùng cùng process và database có thể giúp một số hành động trở thành transaction cục bộ. Nhưng không nên gom mọi command từ nhiều context vào một transaction lớn. Quy tắc miền nghiệp vụ nào cần bất biến tức thời thì đưa vào ranh giới phù hợp; thao tác bên ngoài (payment gateway, email) vẫn cần timeout, retry và xử lý failure riêng.

Một transaction dài giữ lock hoặc gọi mạng có thể gây nghẽn toàn deployable. Gộp service không giải quyết được tất cả dạng consistency.

### Kiểm soát tài nguyên

Khi nhiều module chung JVM/process, cần chú ý:

- Thread pool, connection pool và memory dùng chung.
- Workload chậm hoặc batch nặng chiếm tài nguyên của API nhạy latency.
- Garbage collection, cold start và kích thước artifact.
- Cơ chế giới hạn concurrency, bulkhead ở mức luồng/worker, backpressure.
- Scale toàn deployable khi chỉ một module tăng tải.

Nếu một phần đòi hỏi cô lập mạnh, có thể giữ nó là worker/process riêng mà vẫn thuộc cùng codebase hoặc ownership; không nhất thiết tạo lại toàn bộ dịch vụ phân tán như trước.

### Trách nhiệm thay đổi

Trong team chung, vẫn có thể định người phụ trách kỹ thuật cho module pricing/promotion. Việc gộp không xóa code review, API version discipline, telemetry hay kỷ luật thay đổi hợp đồng.

## 13. Anti-pattern trong quá trình gộp

| Anti-pattern | Vì sao nguy hiểm | Cách tránh |
| --- | --- | --- |
| **Big-bang merge** toàn bộ code, dữ liệu, API trong một lần | Khó tìm nguyên nhân và rollback | Migration theo lát, adapter tương thích, checkpoint |
| **Shared-everything monolith** sau khi gộp | Mất ranh giới trách nhiệm, sửa đâu ảnh hưởng đó | Module API, data owner, dependency rule |
| **Ẩn API call bằng gọi phương thức nhưng giữ logic vòng** | Coupling nghiệp vụ vẫn tồn tại, chỉ bớt network | Thiết kế lại nơi ra quyết định và hướng phụ thuộc |
| **Xóa event vì “giờ cùng process”** | Consumer khác vẫn cần hợp đồng hoặc audit | Inventory tất cả producer/consumer trước |
| **Dual-write không điều phối** | Dữ liệu lệch khi một bên ghi lỗi | Chọn source of truth, outbox/CDC/reconciliation khi cần |
| **Dùng transaction để ôm cả external call** | Lock dài và kết quả bất định khi mạng lỗi | Tách giao dịch cục bộ khỏi thao tác ngoài |
| **Đo thành công bằng giảm pod/container** | Có thể tăng latency, tải hoặc chi phí thay đổi | Đo business outcome, SLO, lead time, run cost |
| **Bỏ qua security boundary cũ** | Mở rộng quyền truy cập và phạm vi rủi ro | Threat model, phân quyền theo module/process phù hợp |
| **Không gỡ endpoint/job cũ** | Duy trì trùng logic và rò chi phí lâu dài | Danh sách consumer, thời hạn decommission, ownership |
| **Gộp theo sơ đồ tổ chức tạm thời** | Team thay đổi làm thiết kế nhanh lỗi thời | Dựa trên cohesion nghiệp vụ và mức độc lập cần thiết |

## 14. Kế hoạch đánh giá minh họa theo 4 tuần

Đây là lịch giả định để lập kế hoạch, không phải thời gian bắt buộc cho mọi dự án:

| Giai đoạn | Hoạt động | Điều kiện chuyển bước |
| --- | --- | --- |
| Tuần 1: quan sát | Thu thập trace, incident, coupling release, contract inventory | Có phát biểu vấn đề và baseline đủ tin cậy |
| Tuần 2: thiết kế | Workshop domain, chọn ranh giới đích, ADR, plan dữ liệu | Hiểu data owner, external consumer, recovery path |
| Tuần 3: thử nghiệm | Chuyển một vertical slice, chạy đối chiếu, benchmark và security review | Hành vi đúng, SLO không xấu, có cách dừng |
| Tuần 4: rollout nhỏ | Routing/canary, monitoring, đối soát dữ liệu, chuẩn bị decommission | Không còn sai lệch trọng yếu; có bằng chứng ổn định |

Với hệ thống thanh toán, dữ liệu lớn hoặc hợp đồng nhiều đối tác, tiến trình có thể cần nhiều tháng. Không dùng lịch mẫu để ép bỏ kiểm tra kỹ thuật quan trọng.

## 15. Mẫu ADR cho quyết định gộp dịch vụ

~~~markdown
# ADR: Hợp nhất deployable Pricing và Promotion

## Bối cảnh
- Pricing và Promotion do cùng Commerce team sở hữu.
- Trong 90 ngày, đa số tính năng tính giá cần sửa cả hai.
- Đường xử lý quote có HTTP dependency bắt buộc giữa hai service.
- Vẫn cần giữ riêng quy tắc giá cơ sở và điều kiện khuyến mãi.

## Lựa chọn
- Hợp nhất thành Commerce deployable.
- Giữ Pricing module và Promotion module, mỗi module có API nội bộ.
- Một Quote Application Service chịu trách nhiệm tổng hợp quyết định báo giá.
- Giữ endpoint công khai tương thích trong giai đoạn migration.
- Chuyển quyền ghi và dữ liệu theo kế hoạch có đối soát.

## Phương án đã so sánh
A. Giữ hai service và batch/cache.
B. Gộp deployable nhưng giữ hai module.
C. Hợp nhất toàn bộ domain model vào một module.

## Lý do
Chọn B vì giảm runtime/deployment coupling trong khi bảo vệ
ngôn ngữ và các quy tắc chưa thật sự đồng nhất.

## Hệ quả và rủi ro
- Mất khả năng triển khai Pricing/Promotion riêng.
- Workload promotion có thể ảnh hưởng latency báo giá.
- Cần kỷ luật dependency và giới hạn tài nguyên trong process.

## Thước đo thành công
- Latency, error rate của báo giá đạt SLO đã thỏa thuận.
- Giảm các release bắt buộc phối hợp và lỗi contract mismatch.
- Không phát sinh lỗi double apply voucher hoặc sai tổng tiền.
- Chi phí duy trì vận hành giảm sau khi decommission.

## Phục hồi
Có routing switch, migration tương thích và runbook xử lý dữ liệu.
Không được rollback binary cũ sau khi đã chuyển source of truth
nếu chưa xác nhận khả năng tương thích dữ liệu.

## Điều kiện xem lại
Team/scale/compliance thay đổi, hoặc một module cần cô lập
về tài nguyên hay lịch triển khai có bằng chứng rõ.
~~~

Một ADR tốt ghi cả **mất mát** khi gộp. Điều đó giúp người sau hiểu tại sao kiến trúc hiện tại có hình dạng ấy và điều kiện nào sẽ dẫn đến việc tách lại.

## 16. Bài tập tình huống

Một sản phẩm SaaS quản lý thuê bao có bốn dịch vụ:

1. **Plan service:** định nghĩa gói và hạn mức.
2. **Discount service:** tính ưu đãi theo gói và chiến dịch.
3. **Subscription service:** quản lý trạng thái đăng ký/gia hạn.
4. **Billing service:** tạo hóa đơn, kết nối nhà cung cấp thanh toán.

Các số liệu giả định:

- Plan và Discount cùng một team, hơn 75% thay đổi về gói cần sửa cả hai.
- Subscription cần gọi Plan, rồi Discount để tính mức phí gia hạn.
- Billing phải duy trì kiểm soát quyền và đối soát riêng.
- Mùa khuyến mãi có nhiều truy vấn về ưu đãi nhưng số giao dịch thanh toán ít thay đổi.
- Đã từng có lỗi gia hạn vì Subscription nhìn thấy giá mới và discount cũ.

**Câu hỏi:**

1. Những tín hiệu nào ủng hộ việc gộp Plan và Discount? Tín hiệu nào chưa đủ?
2. Có nên gộp Billing vào cùng deployable không? Vì sao?
3. Bất biến nghiệp vụ nào cần được xác định khi tính phí gia hạn?
4. Phương án giữ các service nhưng đổi API/query model có đủ không? Cần đo điều gì?
5. Hãy đề xuất target architecture, module API và owner cho kết quả tính phí.
6. Liệt kê ít nhất năm bước migration, bao gồm data owner, compatibility, rollout và recovery.
7. Viết ba metric thành công và hai điều kiện dừng rollout.

### Một hướng giải thích

Có thể hợp nhất Plan và Discount trong một **Subscription Catalog deployable** với các module riêng, nhưng chỉ sau khi thống nhất ai chịu trách nhiệm tạo **quote gia hạn cố định tại một thời điểm**. Subscription có thể yêu cầu quote từ ranh giới công khai duy nhất thay vì tự ghép dữ liệu của hai service và chịu nguy cơ version lệch.

Billing thường nên tiếp tục độc lập nếu sở hữu điều kiện bảo mật, đối soát và failure mode khác biệt. Tuy nhiên, không thể kết luận chỉ từ tên dịch vụ; phải xác minh hợp đồng dữ liệu, SLO, ownership và các quy tắc thực tế.

Một hướng khác là giữ hai service Plan/Discount nhưng triển khai API tính giá thống nhất và projection dữ liệu có version. So sánh hai lựa chọn qua cùng metric về latency, change coupling, sai lệch tính phí và chi phí vận hành.

## 17. Checklist khi đưa quyết định vào dự án

**Trước quyết định**

- [ ] Mô tả chi phí cụ thể do ranh giới gây ra bằng số liệu hoặc sự cố.
- [ ] Phân biệt coupling nghiệp vụ, runtime, deployment, dữ liệu và tổ chức.
- [ ] Đã hỏi lý do chính đáng để tiếp tục giữ ranh giới: scale, bảo mật, resilience, ownership.
- [ ] Đã so sánh ít nhất một phương án nhẹ hơn gộp deployable.
- [ ] Đã xác nhận bounded context và data owner, không chỉ nhìn tên repository.

**Trước migration**

- [ ] Có inventory API, event, job, consumer, database và external integration.
- [ ] Có ranh giới module, hợp đồng nội bộ và hướng phụ thuộc rõ.
- [ ] Có baseline SLO và mục tiêu đo lường thay đổi.
- [ ] Có kế hoạch chuyển dữ liệu, xử lý in-flight request và rollback/forward recovery.
- [ ] Có hướng duy trì tương thích cho client không thể cập nhật tức thời.
- [ ] Có kiểm soát security, resource contention và triển khai từng lát.

**Trong và sau rollout**

- [ ] Đã đối chiếu kết quả nghiệp vụ tại các luồng quan trọng.
- [ ] Đã giám sát latency end-to-end, error rate, throughput, tài nguyên và incident.
- [ ] Có điều kiện dừng/canary switch vận hành được.
- [ ] Không còn dual writer hoặc consumer treo sau cutover.
- [ ] Đã decommission đúng hạn các thành phần không còn dùng.
- [ ] ADR, service catalog, runbook và ownership được cập nhật.

## 18. Ghi nhớ

**Ranh giới service là một công cụ tạo quyền tự chủ và giới hạn thay đổi, nhưng cũng là điểm phát sinh chi phí phân tán.** Khi các service thường xuyên thay đổi cùng nhau, gọi đồng bộ liên tục, chia cắt một quyết định nghiệp vụ và tiêu tốn quá nhiều công vận hành, nên nghiêm túc xem xét gộp.

Quyết định tốt thường là **đơn giản hóa triển khai nhưng vẫn giữ cấu trúc miền nghiệp vụ**: hợp nhất deployable khi hợp lý, bảo vệ module boundary, nguồn sở hữu dữ liệu và hợp đồng công khai. Đưa ra quyết định bằng bằng chứng về thời gian thay đổi, độ trễ, mức độ tin cậy, quy tắc nghiệp vụ và chi phí tổng thể; sau đó migration từng bước với monitoring và phương án phục hồi.

Kiến trúc được phép tiến hóa. Tách khi lợi ích độc lập vượt chi phí; gộp khi chi phí ranh giới vượt lợi ích và có thể bảo vệ những ràng buộc quan trọng bằng một thiết kế đơn giản hơn.
