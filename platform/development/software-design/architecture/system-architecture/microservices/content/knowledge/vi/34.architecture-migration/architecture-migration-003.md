# Chọn dịch vụ đầu tiên theo giá trị, rủi ro và khả năng tách

Khi chuyển một hệ thống nguyên khối hoặc một kiến trúc liên kết chặt sang microservices, câu hỏi khó đầu tiên thường không phải là dùng Kubernetes, chọn message broker hay viết API bằng framework nào. Câu hỏi quan trọng hơn là: **nên tách phần nào trước, và bằng chứng nào cho thấy lựa chọn đó đáng làm?**

Tách sai thành phần có thể tạo thêm một service nhưng không giảm coupling: service mới vẫn truy cập chung database, phải phát hành cùng ứng dụng cũ, phụ thuộc vào các bảng nội bộ và cần một nhóm khác sửa code mỗi lần thay đổi. Tổ chức khi đó nhận thêm network hop, deployment pipeline, alert, chi phí vận hành và failure modes mà chưa đạt được lợi ích về tốc độ thay đổi hoặc quyền sở hữu.

Một ứng viên phù hợp cần cân bằng ba chiều:

- **Giá trị (value):** việc tách có giải quyết vấn đề kinh doanh hoặc kỹ thuật quan trọng, có kết quả đo được và tạo lợi ích đủ lớn không?
- **Rủi ro (risk):** nếu tách sai hoặc xảy ra sự cố, tác động tới khách hàng, dữ liệu, bảo mật và hoạt động vận hành lớn đến mức nào?
- **Khả năng tách (separability):** miền nghiệp vụ, dữ liệu, hợp đồng, vòng đời phát hành và ownership có thể được tách với mức phối hợp chấp nhận được không?

Mục tiêu không phải tìm service nhỏ nhất hay dễ viết lại nhất. Mục tiêu là chọn một lát cắt tạo giá trị, giới hạn blast radius, kiểm chứng được giả thuyết kiến trúc và giúp tổ chức học được cách tách những phần tiếp theo.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao lựa chọn dịch vụ đầu tiên ảnh hưởng lớn tới chi phí và kết quả của chương trình chuyển đổi.
2. Phân biệt giá trị kinh doanh, giá trị kỹ thuật và lợi ích tổ chức của một ứng viên.
3. Nhận diện rủi ro theo criticality, dữ liệu, consistency, security, dependency và năng lực vận hành.
4. Đánh giá khả năng tách dựa trên bounded context, quyền sở hữu dữ liệu, contract, deployment autonomy và coupling.
5. Dùng scorecard có trọng số nhưng không biến điểm số thành quyết định máy móc.
6. So sánh các ứng viên bằng evidence, baseline và chi phí vòng đời.
7. Xác định khi nào nên giữ modular monolith hoặc cải thiện ranh giới nội bộ trước khi tách service.
8. Thiết kế extraction theo từng bước với facade, anti-corruption layer, strangler routing, data migration và rollout.
9. Đặt tiêu chí dừng, rollback, success metrics và điều kiện chọn ứng viên tiếp theo.
10. Tổ chức pilot để vừa tạo kết quả thực tế vừa tích lũy năng lực chuyển đổi.

## 2. Vì sao dịch vụ đầu tiên là quyết định chiến lược?

Dịch vụ đầu tiên thường tạo ra khuôn mẫu cho nhiều quyết định sau đó:

- Cách xác định service boundary và quyền sở hữu domain.
- Cách một team thiết kế API/event contract.
- Cách quản lý dữ liệu khi không còn truy cập trực tiếp vào database chung.
- Cách triển khai độc lập, quan sát, rollback và xử lý incident.
- Cách đo chi phí nền tảng và lợi ích của autonomy.
- Cách phối hợp giữa product, architecture, security, operations và platform team.

Nếu ứng viên đầu tiên quá phức tạp, dự án có thể tiêu tốn nhiều tháng vào migration dữ liệu, transaction phân tán và phối hợp nhiều team trước khi có kết quả. Nếu ứng viên quá nhỏ hoặc không có nhu cầu thực, nhóm chỉ chứng minh được khả năng tạo một HTTP service mới, không chứng minh được chuyển đổi kiến trúc đã giải quyết vấn đề gì.

Một pilot tốt phải trả lời được hai câu hỏi khác nhau:

1. **Kết quả sản phẩm:** người dùng hoặc doanh nghiệp nhận được lợi ích gì sau thay đổi?
2. **Kết quả năng lực:** tổ chức học được gì về cách tách, phát hành, vận hành và quản trị service?

Không nên đánh giá thành công chỉ bằng số lượng microservices tăng lên. Tách thêm service mà lead time, reliability và ownership không cải thiện có thể làm kiến trúc tệ hơn.

## 3. Bắt đầu từ vấn đề, không bắt đầu từ sơ đồ tổ chức

Một yêu cầu như “chúng ta cần microservices để scale” chưa đủ để chọn ứng viên. Cần cụ thể hóa vấn đề:

- Một phần nghiệp vụ có release chậm vì phải chờ toàn bộ monolith?
- Một module có tải tăng đột biến và cần scale khác phần còn lại?
- Một domain có quy tắc thay đổi liên tục, bị nhiều nhóm sửa cùng lúc?
- Một thành phần có yêu cầu bảo mật, residency hoặc availability khác biệt?
- Một integration với đối tác thường xuyên lỗi, cần isolation và retry riêng?
- Một batch job chiếm CPU/IO làm ảnh hưởng request tương tác?
- Một nhóm muốn sở hữu vòng đời service nhưng hiện không thể phát hành độc lập?
- Thay đổi ở một module thường gây regression diện rộng vì dependency không rõ?

Mỗi vấn đề cần có **baseline**: lead time, deployment frequency, change failure rate, incident count, p95/p99 latency, resource consumption, ticket waiting time hoặc số lần phối hợp giữa teams. Nếu không có baseline, sau khi tách rất khó biết lợi ích có thực sự đến từ kiến trúc mới hay chỉ do nhóm đã refactor code và cải thiện quy trình.

### Ví dụ phát biểu vấn đề tốt

Chưa đủ cụ thể:

> “Catalog đang nằm trong monolith nên cần tách thành microservice.”

Có thể kiểm chứng hơn:

> “Trong ba tháng gần đây, thay đổi catalog phải chờ release chung trung bình bốn ngày; các đợt import catalog tạo tải database làm p95 của checkout tăng. Nhóm Catalog có owner riêng, dữ liệu sản phẩm đã có ranh giới tương đối rõ. Chúng ta muốn thử tách read/update catalog để release độc lập và cách ly tải import, đồng thời không thay đổi đường xác nhận tồn kho/đơn hàng.”

Phát biểu thứ hai chỉ ra pain point, baseline, boundary giả định và những gì chưa đưa vào phạm vi.

## 4. Ba chiều đánh giá ứng viên

Một cách nhìn tổng quát:

~~~text
                  GIÁ TRỊ
       lợi ích khách hàng / tốc độ / scale
                    /\
                   /  \
                  /    \
                 /      \
                /        \
       KHẢ NĂNG TÁCH ---- RỦI RO
       domain/data/contract   blast radius,
       ownership/autonomy    data/security/ops
~~~

Ba chiều không độc lập hoàn toàn:

- Giá trị cao nhưng khả năng tách thấp có thể vẫn đáng đầu tư nếu có chiến lược giảm coupling theo giai đoạn.
- Khả năng tách cao nhưng giá trị thấp thường không phải ứng viên ưu tiên, trừ khi đây là bước chuẩn bị bắt buộc hoặc có lợi ích vận hành rõ.
- Giá trị và khả năng tách cao nhưng rủi ro dữ liệu không chấp nhận được thì phải giảm phạm vi, tăng guardrails hoặc chọn phần khác.
- Một ứng viên có rủi ro cao có thể trở thành pilot hợp lý sau khi thực hiện các bước giảm rủi ro trước, nhưng không nên dùng pilot đầu tiên để đồng thời thử mọi kỹ thuật mới.

**Không cộng điểm rồi bỏ qua điều kiện bắt buộc.** Một ứng viên không thể tách dữ liệu khách hàng an toàn hoặc không có owner có thể bị loại dù điểm giá trị rất cao.

## 5. Đánh giá giá trị kinh doanh

Giá trị nên gắn với outcome mà product owner và người sử dụng quan tâm, không chỉ với lợi ích nội bộ của đội kỹ thuật.

Các câu hỏi:

1. Phần nghiệp vụ này có ảnh hưởng tới doanh thu, retention, conversion hoặc chi phí phục vụ không?
2. Có thể phát hành tính năng nhanh hơn sau khi tách không?
3. Có nhóm khách hàng hoặc luồng nghiệp vụ đang bị chặn bởi release coupling không?
4. Việc tách có giảm lỗi hoặc thời gian gián đoạn mà người dùng thực sự cảm nhận không?
5. Có nhu cầu scale độc lập theo traffic/CPU/IO không?
6. Có thể thử nghiệm sản phẩm, thay đổi pricing hoặc chính sách độc lập không?
7. Lợi ích có xuất hiện trong thời gian đủ ngắn để đánh giá pilot không?
8. Ai chịu trách nhiệm xác nhận lợi ích, và dữ liệu nào sẽ chứng minh?

### 5.1. Nhóm giá trị cần cân nhắc

| Loại giá trị | Câu hỏi | Bằng chứng |
|---|---|---|
| Customer value | Có cải thiện trải nghiệm hoặc độ tin cậy không? | Conversion, completion, support complaints, SLO |
| Time-to-market | Có giảm thời gian chờ release không? | Lead time, release dependency, waiting time |
| Scalability | Có tải riêng cần scale độc lập không? | CPU/IO profile, request volume, peak pattern |
| Resilience | Có giới hạn được ảnh hưởng khi dependency lỗi không? | Incident history, blast radius, recovery time |
| Team autonomy | Có team sở hữu domain và release riêng không? | Ownership, change coordination, deployment data |
| Security/compliance | Có cần trust boundary riêng không? | Data classification, access audit, policy requirements |
| Cost efficiency | Có giảm overprovisioning hoặc chi phí vận hành không? | Cost per transaction, resource utilization |
| Innovation | Có cần thử nghiệm công nghệ hoặc sản phẩm riêng không? | Roadmap, experimentation frequency, delivery constraints |

Không phải lợi ích nào cũng cộng được thành tiền. Có thể dùng một số chỉ số định lượng kết hợp với mục tiêu chiến lược, nhưng phải tránh tính trùng: giảm lead time và tăng deployment frequency có thể là hai biểu hiện của cùng một lợi ích.

### 5.2. Phân biệt lợi ích thực với lợi ích giả định

“Tách ra sẽ scale tốt hơn” cần được kiểm chứng bằng profile tải. Nếu Catalog chỉ dùng 5% CPU của monolith và không có pattern riêng, việc tạo cluster/service riêng có thể tăng chi phí mà không cải thiện gì.

“Tách ra để team độc lập” cần kiểm tra team có quyền thay đổi contract, dữ liệu và release thực sự không. Nếu mọi lần thay đổi đều cần team monolith sửa bảng chung, autonomy chỉ tồn tại trên sơ đồ.

## 6. Đánh giá rủi ro

Rủi ro là tổng hợp xác suất, tác động và khả năng phát hiện/khôi phục. Không chỉ nhìn số lượng code hoặc độ khó kỹ thuật.

### 6.1. Rủi ro nghiệp vụ

- Service có nằm trên luồng thanh toán, đặt hàng, đăng nhập hoặc xử lý dữ liệu cốt lõi không?
- Có thể gây mất doanh thu, duplicate transaction hoặc dữ liệu không thể phục hồi không?
- Có workaround khi service mới ngừng hoạt động không?
- Có thể chuyển traffic trở lại thành phần cũ mà không mất trạng thái không?
- Một lỗi có ảnh hưởng tất cả tenants hay chỉ một cohort?

### 6.2. Rủi ro dữ liệu

- Dữ liệu có PII, tài chính, sức khỏe hoặc phân loại hạn chế không?
- Có nhiều writer cùng cập nhật bảng không?
- Có transaction xuyên nhiều aggregate hoặc service không?
- Có stored procedure, trigger, batch job hoặc báo cáo đọc trực tiếp không?
- Có foreign key hoặc constraint nối dữ liệu của nhiều domain không?
- Có yêu cầu ordering, idempotency, exactly-once business effect hoặc strong consistency không?
- Migration có thể chạy lặp và resume an toàn không?
- Backup/restore đã được kiểm thử chưa?

### 6.3. Rủi ro kỹ thuật và vận hành

- Service mới có dependency critical nào không?
- API/event contract đã ổn định chưa?
- Latency/network timeout có làm thay đổi semantics không?
- Có đủ logs, metrics, traces, alerts và runbooks không?
- Có capacity và quota cho service mới không?
- Team có on-call và kỹ năng vận hành không?
- Có version compatibility khi old/new chạy song song không?
- Có thể rollback image nhưng không rollback dữ liệu; đã có roll-forward/compensation plan chưa?

### 6.4. Rủi ro tổ chức

- Nhiều team cùng sở hữu module hoặc database không?
- Product owner và domain owner có đồng thuận boundary không?
- Team nhận service có đủ năng lực và capacity không?
- Có vendor/legacy system không thể thay đổi?
- Có deadline pháp lý/kinh doanh khiến việc tách không thể thử nghiệm dần?
- Có phụ thuộc vào một vài cá nhân nắm kiến thức không được tài liệu hóa?

Một thành phần có ít code nhưng có nhiều shared writers và quy trình thủ công có thể rủi ro hơn một module lớn nhưng domain boundary rõ.

## 7. Đánh giá khả năng tách (separability)

Khả năng tách trả lời: liệu có thể chuyển trách nhiệm cho một service mới mà không phải tiếp tục thay đổi nhiều thành phần khác cho mỗi lần phát hành?

### 7.1. Bounded context

Một ứng viên tốt có mô hình nghiệp vụ và ngôn ngữ riêng:

- Có các khái niệm, trạng thái và quy tắc nghiệp vụ tương đối thống nhất.
- Có thể mô tả bằng một nhóm use cases có đầu vào/đầu ra rõ.
- Có owner hiểu và quyết định được các quy tắc đó.
- Không cần biết trực tiếp nội bộ của các domain khác để thực hiện trách nhiệm chính.
- Có thể xác định những dữ liệu nó sở hữu và dữ liệu chỉ tham chiếu.

Ví dụ Catalog sở hữu mô tả, phân loại và thuộc tính sản phẩm. Inventory sở hữu lượng tồn và reservation. Hai domain cùng nhắc đến SKU nhưng không nhất thiết chia sẻ cùng một mô hình ghi dữ liệu.

### 7.2. Quyền sở hữu dữ liệu

Đây thường là yếu tố quyết định:

- Service mới có thể sở hữu dữ liệu riêng không?
- Có thể chuyển write path trước, rồi chuyển read path theo giai đoạn không?
- Những service khác đang query trực tiếp bảng nào?
- Có thể thay join xuyên schema bằng API, event hoặc read model không?
- Có thể giữ một source of truth cho từng loại dữ liệu không?
- Có kế hoạch xử lý consistency và eventual propagation không?

Một service có database riêng nhưng vẫn cho nhiều service khác ghi trực tiếp vào bảng của nó chưa có data ownership thực sự.

### 7.3. Hợp đồng và dependency

- Input/output có thể định nghĩa thành API/event contract không?
- Consumer có thể nâng cấp độc lập không?
- Có nhiều call đồng bộ trong một request path không?
- Có dependency cycle không?
- Có thể xử lý lỗi bằng timeout, retry budget, circuit breaker hoặc async workflow mà không thay đổi business semantics?
- Có schema registry/contract tests hoặc consumer-driven tests phù hợp không?

### 7.4. Deployment autonomy

- Có thể build và deploy service mới độc lập không?
- Có thể chạy old/new version song song không?
- Cấu hình và secrets có tách theo môi trường không?
- Có quyền runtime và observability riêng không?
- Team có thể rollback/scale mà không phải xin release toàn monolith không?

**Tách code thành repository riêng không đồng nghĩa tách được vòng đời.** Nếu mỗi lần đổi contract phải đồng bộ release của cả ba consumers, autonomy còn thấp.

## 8. Dấu hiệu ứng viên có thể tách tốt

Một ứng viên thường thuận lợi khi:

- Có business capability dễ gọi tên và ranh giới use case tương đối rõ.
- Có team hoặc owner chịu trách nhiệm dài hạn.
- Thay đổi của nó thường không yêu cầu sửa các domain khác.
- Dữ liệu có thể phân quyền sở hữu; số shared writers ít hoặc có đường chuyển đổi.
- Contract có thể ổn định và version hóa.
- Có nhu cầu triển khai/scale/reliability riêng.
- Có thể giới hạn một phần traffic hoặc một nhóm chức năng khi rollout.
- Có thể chuyển dần bằng facade/adapter/strangler pattern.
- Có test và telemetry đủ để so sánh old/new.
- Có phương án rollback/roll-forward không làm sai dữ liệu.

## 9. Dấu hiệu chưa nên tách ngay

Cân nhắc hoãn hoặc làm bước chuẩn bị trước nếu:

- Không ai thống nhất được service sở hữu nghiệp vụ nào.
- Module phụ thuộc trực tiếp vào hàng chục bảng và stored procedures dùng chung.
- Nhiều service cùng ghi vào một bảng mà chưa có owner.
- Có transaction nguyên tử xuyên toàn bộ use case và chưa có cách phân tách hợp lý.
- Hợp đồng giữa các thành phần thay đổi liên tục và không có versioning.
- Chưa có CI/CD, observability, on-call hoặc capacity vận hành cơ bản.
- Team chưa có quyền triển khai/rollback độc lập.
- Lợi ích duy nhất là “đang theo xu hướng microservices”.
- Chưa có baseline để đánh giá kết quả.
- Thời gian migration lớn hơn lợi ích có thể thu được trong roadmap hiện tại.
- Việc tách buộc phải thực hiện một lần với phạm vi quá rộng.
- Không thể tạo dữ liệu test hoặc rehearsal an toàn cho migration.

“Chưa tách” không có nghĩa là không làm gì. Có thể refactor thành module rõ ràng, loại bỏ dependency cycle, xác định owner, tạo API nội bộ và đưa data access qua repository/interface trước. Đây thường là khoản đầu tư làm tăng separability mà vẫn giữ hệ thống trong một deployment.

## 10. Scorecard ba chiều

Một scorecard giúp các bên nói cùng ngôn ngữ. Chọn thang 1–5 cho từng tiêu chí:

- **1:** rất bất lợi hoặc thiếu bằng chứng.
- **2:** yếu, còn nhiều trở ngại.
- **3:** trung bình, có thể làm nếu có kế hoạch giảm rủi ro.
- **4:** thuận lợi, đã có evidence đáng tin.
- **5:** rất thuận lợi, đã kiểm chứng trong thực tế.

### 10.1. Trọng số minh họa

| Nhóm | Tiêu chí | Trọng số gợi ý |
|---|---|---:|
| Value | Tác động khách hàng/kinh doanh | 20% |
| Value | Nhu cầu release/scale/autonomy độc lập | 15% |
| Value | Mức độ đo được và thời gian đạt lợi ích | 10% |
| Separability | Bounded context và ownership | 15% |
| Separability | Data ownership và migration path | 15% |
| Separability | Contract/dependency/deploy autonomy | 10% |
| Risk | Business/data/security/operational risk có thể kiểm soát | 15% |

Điểm rủi ro cần được diễn giải theo chiều **điểm cao = rủi ro dễ kiểm soát hơn** để công thức không bị hiểu ngược. Có thể tách risk thành xác suất và tác động nếu cần phân tích sâu. Trọng số chỉ là điểm khởi đầu; tổ chức nên điều chỉnh theo mục tiêu và mức độ trưởng thành.

### 10.2. Công thức

Nếu điểm mỗi tiêu chí là từ 1 đến 5 và trọng số tổng bằng 1:

~~~text
Candidate Score = Σ (criterion_score × criterion_weight)
~~~

Ví dụ:

- Business impact: 4 × 0,20
- Independent change/scale: 5 × 0,15
- Measurable benefit: 4 × 0,10
- Domain ownership: 4 × 0,15
- Data separation: 3 × 0,15
- Contract/deploy autonomy: 4 × 0,10
- Risk controllability: 3 × 0,15

~~~text
Score = 0,80 + 0,75 + 0,40 + 0,60 + 0,45 + 0,40 + 0,45
      = 3,85 / 5
~~~

Đây chỉ là ví dụ số học. Điểm tổng không thay thế các **hard gates**: không có owner, không có đường khôi phục dữ liệu, hoặc không đáp ứng yêu cầu bảo mật có thể khiến ứng viên bị HOLD dù tổng điểm cao.

## 11. Hard gates trước khi đưa ứng viên vào pilot

Một ứng viên có thể được đánh giá cao nhưng chưa đủ điều kiện triển khai. Một số gate nên bắt buộc:

| Gate | Câu hỏi | Nếu không đạt |
|---|---|---|
| Domain owner | Có người chịu trách nhiệm nghiệp vụ và kỹ thuật không? | HOLD, xác định ownership |
| Data authority | Biết source of truth và quyền ghi chưa? | HOLD, lập data ownership map |
| Security | Có phân loại dữ liệu và access model không? | HOLD, làm threat model |
| Recovery | Có rollback/roll-forward/restore path không? | HOLD, diễn tập trước |
| Observability | Có thể nhận ra regression và phân biệt old/new không? | HOLD, bổ sung telemetry |
| Contract | Consumers có thể tương thích trong giai đoạn chuyển tiếp không? | HOLD, version contract |
| Capacity | Có người on-call, tài nguyên và ngân sách không? | HOLD, chuẩn bị vận hành |
| Business value | Có outcome và baseline được sponsor xác nhận không? | Không ưu tiên pilot |

Không nên “bù” một hard gate bằng điểm cao ở tiêu chí khác. Rủi ro không thể chấp nhận cần được giảm hoặc chọn ứng viên khác.

## 12. Ví dụ so sánh ba ứng viên

Giả sử một hệ thống bán lẻ có ba module:

- **Catalog:** sản phẩm, mô tả, phân loại, import feed.
- **Inventory:** tồn kho, reservation, cập nhật sau giao dịch.
- **Reporting:** tổng hợp dữ liệu bán hàng và dashboard.

Scorecard giả định:

| Tiêu chí | Catalog | Inventory | Reporting |
|---|---:|---:|---:|
| Business impact | 4 | 5 | 3 |
| Independent change/scale | 5 | 4 | 4 |
| Measurable benefit | 4 | 4 | 4 |
| Domain ownership | 4 | 3 | 4 |
| Data separation | 4 | 2 | 4 |
| Contract/deploy autonomy | 4 | 2 | 4 |
| Risk controllability | 4 | 2 | 4 |
| Tổng có trọng số | 4,15 | 3,15 | 3,80 |

Các điểm trong bảng chỉ minh họa cách thảo luận, không phải đánh giá thực tế. Catalog có thể là ứng viên đầu tiên nếu feed import đang ảnh hưởng monolith và nhóm Catalog có owner. Reporting cũng có thể là pilot tốt nếu đọc dữ liệu qua CDC/snapshot và không nằm trên critical write path. Inventory có giá trị cao nhưng rủi ro correctness và transaction lớn hơn; có thể cần chuẩn bị domain/data boundary trước.

**Kết luận không phải luôn chọn Catalog.** Nếu Catalog không có pain point thật, hoặc Reporting có giá trị chiến lược cao hơn và data pipeline đã tách rõ, thứ tự có thể đảo. Phải dùng evidence và hard gates của hệ thống cụ thể.

## 13. Đừng chọn ứng viên chỉ theo kích thước code

Một module 2.000 dòng có thể phụ thuộc vào 20 bảng và được gọi trực tiếp bởi nhiều phần của monolith. Một module 40.000 dòng có thể sở hữu một domain rõ, có data model riêng và team độc lập. Số dòng code không phản ánh separability.

Những dấu hiệu hữu ích hơn:

- Fan-in/fan-out của dependency graph.
- Số lượng direct database readers/writers.
- Tần suất thay đổi đồng thời với các module khác.
- Số team cần phối hợp trong một release.
- Số API/event contracts đã ổn định.
- Mức độ chia sẻ transaction và data model.
- Tỷ lệ use cases có thể chạy qua một boundary rõ.
- Khả năng test độc lập và quan sát theo module.

Một module nhỏ nhưng gắn chặt vào monolith có thể cần refactor nội bộ trước. Đừng tách chỉ để đạt mục tiêu “mỗi service ít hơn X dòng”.

## 14. Domain map và dependency map trước khi quyết định

Vẽ hai bản đồ riêng:

1. **Domain map:** business capabilities, owner, dữ liệu và các quy tắc thuộc về từng miền.
2. **Dependency map:** lời gọi runtime, bảng được truy cập, events, jobs, shared libraries và release dependencies.

Ví dụ:

~~~text
DOMAIN MAP
Catalog Team       -> Product descriptions, categories
Inventory Team     -> Stock, reservation
Order Team         -> Order lifecycle
Reporting Team     -> Aggregated analytics

DEPENDENCY MAP
Order -> Inventory API
Order -> Payment API
Catalog -> Product DB
Inventory -> Product DB (direct read: legacy coupling)
Reporting -> Order DB (direct query)
Reporting -> Inventory DB (direct query)
~~~

Domain map nói rằng Catalog sở hữu product descriptions, nhưng dependency map cho thấy Inventory và Reporting còn query trực tiếp Product DB. Như vậy boundary nghiệp vụ có thể rõ, nhưng boundary kỹ thuật chưa sẵn sàng.

Các bước giảm coupling:

- Xác định ai là writer có thẩm quyền.
- Chuyển direct writes thành API/command hoặc event có owner.
- Tạo read model phù hợp cho consumer.
- Dùng compatibility view/adapter trong giai đoạn chuyển tiếp nếu cần.
- Theo dõi usage và loại bỏ direct queries khi consumer đã migrate.
- Chỉ tách database/ownership sau khi các đường phụ thuộc được xử lý.

## 15. Bắt đầu bằng modular monolith nếu boundary chưa rõ

Không phải module nào cũng phải thành microservice ngay. Có thể thiết kế modular monolith với:

- Module boundaries rõ và enforced ở build/test.
- Domain interfaces thay vì truy cập class nội bộ.
- Mỗi module sở hữu schema hoặc nhóm bảng riêng theo quy ước.
- Không cho module khác ghi trực tiếp dữ liệu sở hữu.
- Contract tests ở mức module.
- Dependency graph không có cycle ngoài chính sách.
- Release cùng artifact nhưng module có thể phát triển độc lập về logic.

Modular monolith giúp kiểm tra boundary mà không đưa thêm network failure, deployment và distributed data consistency. Khi module đã có ownership, contract và data separation ổn định, extraction thành service sẽ có chi phí thấp hơn.

**Một module có thể là ứng viên tốt nhưng chưa phải service tốt ở thời điểm hiện tại.** Hãy tách ranh giới logic trước, rồi dùng bằng chứng vận hành để quyết định có cần tách process/deployment không.

## 16. Chọn phạm vi nhỏ nhất tạo ra kết quả đo được

Phạm vi pilot nên đủ lớn để giải quyết một vấn đề nhưng đủ nhỏ để kiểm soát:

- Chọn một capability hoặc một luồng đọc/ghi rõ, không chuyển toàn bộ domain cùng lúc.
- Giữ những luồng có consistency phức tạp trong hệ thống cũ nếu chưa có cách xử lý an toàn.
- Không đồng thời thay framework, database engine, cloud provider và team ownership.
- Tách một loại dữ liệu hoặc một nhóm API trước khi tách toàn bộ schema.
- Giới hạn cohort/traffic hoặc batch size để có thể dừng.
- Có test dữ liệu đại diện và kịch bản failure.

Ví dụ Catalog có thể bắt đầu bằng **read API cho product descriptions** và import feed riêng, trong khi Order vẫn dùng nguồn dữ liệu chuẩn hiện tại cho các quyết định tồn kho/checkout. Khi đã chứng minh read path và ownership, mở rộng thêm chức năng write theo kế hoạch riêng.

## 17. Các chiến lược extraction

### 17.1. Strangler pattern

Một facade/gateway đứng trước chức năng cũ, rồi chuyển dần một số request sang service mới:

~~~text
Client
  |
  v
Facade / API Gateway
  |
  +--> old monolith (default)
  |
  +--> new service (selected routes/cohort)
~~~

Lợi ích: chuyển traffic theo từng endpoint hoặc cohort, quan sát kết quả và quay về đường cũ khi cần. Giới hạn: facade trở thành điểm cần quản lý route, auth, timeout và compatibility; nếu logic domain vẫn bị chia đôi không rõ owner, complexity có thể kéo dài.

### 17.2. Branch by abstraction

Đưa một interface vào code cũ, giữ implementation hiện tại rồi thêm implementation gọi service mới. Chuyển traffic qua cấu hình/feature flag:

~~~text
Business use case
      |
      v
Domain interface
      |
      +--> Legacy implementation
      |
      +--> Remote service adapter
~~~

Cách này phù hợp khi muốn thay thế dependency nội bộ từng bước. Cần giữ semantics tương đương, test cả hai đường và không cho phép switch gây duplicate side effects.

### 17.3. Anti-corruption layer (ACL)

ACL chuyển đổi mô hình cũ sang contract mới, ngăn domain mới phụ thuộc trực tiếp vào legacy concepts:

~~~text
Legacy data/model
       |
       v
Anti-corruption adapter
       |
       v
New service domain model
~~~

ACL hữu ích khi monolith có tên field, trạng thái hoặc quy tắc lịch sử không phù hợp với domain mới. Nó cũng là nơi xử lý mapping, validation và compatibility trong giai đoạn chuyển đổi. Tuy nhiên, ACL không nên trở thành nơi chứa toàn bộ business logic của cả hai phía.

### 17.4. Event-driven extraction

Một service có thể bắt đầu bằng việc nhận domain events, xây read model riêng hoặc xử lý một capability async. Cần outbox/CDC, schema version, idempotency, ordering semantics, retry/DLQ và reconciliation. Không chuyển sang async chỉ để tránh định nghĩa API; message delivery tạo thêm trạng thái và failure modes.

## 18. Quyền sở hữu dữ liệu: điều kiện cốt lõi

Một service thực sự sở hữu dữ liệu khi:

- Nó là nơi có quyền quyết định thay đổi hợp lệ.
- Các consumers dùng contract thay vì truy cập bảng nội bộ.
- Schema và migration có owner.
- Các dữ liệu derived/read model được phân biệt với source of truth.
- Có cách đồng bộ và sửa sai khi event/CDC bị trễ.
- Có quyền backup, retention, restore và deletion phù hợp.

### 18.1. Không tạo database riêng chỉ để có thêm database

Nếu service mới và monolith cùng ghi một database table, quyền sở hữu vẫn không rõ. Một database riêng nhưng copy dữ liệu từ DB cũ không có version/watermark cũng tạo hai nguồn sự thật.

Hãy thiết kế **ownership transition**:

1. Chỉ định writer hiện tại và writer đích.
2. Xác định nguồn chuẩn trong giai đoạn song song.
3. Tạo data contract và cơ chế sync.
4. Chuyển write authority tại một mốc có kiểm soát.
5. Đối chiếu dữ liệu và xử lý sai lệch.
6. Chuyển consumers sang API/read model mới.
7. Thu hồi quyền truy cập trực tiếp cũ.
8. Chỉ dừng đường legacy khi đã chứng minh không còn consumer.

## 19. Các mẫu di chuyển dữ liệu

### 19.1. Snapshot rồi CDC

Một quy trình phổ biến:

~~~text
Legacy database
   |
   +--> consistent snapshot (baseline)
   |
   +--> CDC stream from checkpoint
              |
              v
         New service store
              |
              v
       Reconcile versions/counts
              |
              v
         Cut over writes/reads
~~~

Cần biết snapshot được chụp tại thời điểm nào và CDC bắt đầu từ checkpoint nào để không có gap. Reconciliation không chỉ so sánh tổng row count; cần kiểm tra primary keys, version, totals, nulls, constraints và các business invariants.

### 19.2. Dual write

Ứng dụng ghi cả DB cũ và DB mới trong cùng request thường dễ nghĩ nhưng khó bảo đảm:

- Ghi cũ thành công, ghi mới thất bại.
- Ghi mới thành công, ghi cũ thất bại.
- Retry request làm ghi trùng.
- Hai nơi cập nhật theo thứ tự khác nhau.
- Một phía timeout nhưng đã commit.

Nếu buộc phải dùng trong giai đoạn chuyển tiếp, cần idempotency, version, retry/reconciliation và xác định nguồn có thẩm quyền. Tốt hơn thường là một writer duy nhất phát event/outbox, rồi consumer cập nhật bản sao/read model.

### 19.3. Expand–migrate–contract

1. **Expand:** thêm schema/field mới tương thích với code cũ.
2. **Migrate:** backfill và đồng bộ dữ liệu theo checkpoint.
3. **Switch:** chuyển consumer/writer theo giai đoạn.
4. **Verify:** kiểm tra invariants, traffic và error rates.
5. **Contract:** xóa schema/đường cũ sau khi không còn consumer.

Không drop cột/bảng ngay khi code mới đã deploy; old Pods, background jobs và báo cáo có thể vẫn đang đọc. Decommission phải có evidence từ query telemetry và owner xác nhận.

## 20. Thiết kế contract trước khi tách

API/event contract cần thể hiện:

- Resource identity và tenant scope.
- Operation semantics, không chỉ tên endpoint.
- Validation, errors và retryability.
- Idempotency key cho command có side effects.
- Pagination/filtering và giới hạn payload.
- Timeout/deadline và rate limits.
- Versioning và backward compatibility.
- Authentication/authorization.
- Observability/correlation metadata.
- Deprecation và consumer migration.

Ví dụ API:

~~~http
GET /v1/products/{productId}
Accept: application/json
~~~

Response:

~~~json
{
  "id": "product-42",
  "name": "Blue Shirt",
  "categoryRef": "category-7",
  "revision": 18
}
~~~

Ví dụ domain event:

~~~json
{
  "eventId": "evt-01",
  "eventType": "ProductDescriptionChanged",
  "schemaVersion": 1,
  "productRef": "product-42",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-12T03:15:24Z"
}
~~~

Đây là ví dụ giản lược. Không đưa raw PII/secret vào event, và không giả định field revision của response đồng nghĩa với database transaction version nếu contract chưa định nghĩa như vậy.

## 21. Đừng tách một phần chỉ vì nó có tải cao

Tải cao có thể được giải quyết bằng các phương án ít phức tạp hơn:

- Tối ưu query/index và connection pool.
- Cache có TTL/invalidation đúng.
- Read replica hoặc materialized view.
- Queue/batch để làm phẳng burst.
- Scale stateless replicas nếu bottleneck nằm ở compute.
- Tách worker process nhưng vẫn dùng modular monolith/artifact chung.
- Đưa static/public content qua CDN.

Microservice có thể cho phép scale độc lập, nhưng cũng thêm network, serialization, remote failure, identity và operational cost. Cần so sánh **chi phí của giải pháp tách** với phương án tối ưu nội bộ.

## 22. Tổ chức team và ownership trước khi extraction

Một service không nên được tạo ra mà chưa biết ai sở hữu:

- Product/domain owner có quyền quyết định semantics.
- Engineering owner chịu trách nhiệm code, release và reliability.
- Data owner quản lý schema, quality, access và lifecycle.
- On-call có runbook, alert và escalation.
- Platform/security hỗ trợ runtime, identity và guardrails.
- Consumer owners có cam kết contract/version migration.

Nếu service không có team owner, nó có thể trở thành “orphan service”: code tồn tại, nhưng không ai ưu tiên vulnerability, nâng runtime, trả lời alert hoặc quyết định decommission.

### 22.1. Team topology và ranh giới service

Một team sở hữu nhiều service có thể vẫn độc lập nếu domain rõ và workload hợp lý. Không nhất thiết một microservice tương ứng một team. Nhưng nếu service boundary cắt ngang quyền quyết định nghiệp vụ, mỗi thay đổi sẽ cần phối hợp nhiều team và lợi ích autonomy suy giảm.

Hãy đánh giá:

- Team có đủ capacity on-call không?
- Domain knowledge có nằm trong nhóm hay phụ thuộc một người?
- Service có API/contract đủ ổn định để consumer tự tích hợp không?
- Ai chịu trách nhiệm khi lỗi ở network/platform hay data?
- Có thể phát hành và rollback ngoài lịch release của monolith không?

## 23. Readiness vận hành trước khi tách

Service mới cần tối thiểu:

- Health/readiness/liveness phù hợp semantics.
- Resource requests/limits và autoscaling policy.
- Structured logs, metrics, traces và correlation IDs.
- SLI/SLO, alert thresholds và dashboard.
- Timeout, retry budget, circuit breaker/bulkhead theo dependency.
- Authentication, authorization và workload identity.
- Secrets/configuration lifecycle.
- Backup/restore nếu sở hữu state.
- Runbook, on-call, escalation và incident response.
- CI/CD, artifact digest, rollout/rollback.
- Capacity, cost owner và quota.
- Security scanning, patching và vulnerability response.

Không bắt buộc mọi service có cùng SLO hoặc topology. Profile phải dựa trên criticality. Một batch job có thể không cần HTTP readiness probe, nhưng cần job success/failure metrics, checkpoint và retry policy.

## 24. Lập baseline và định nghĩa kết quả pilot

Trước khi thay đổi, chụp baseline trong một khoảng đủ đại diện:

| Nhóm | Baseline có thể đo |
|---|---|
| Delivery | Lead time, deployment frequency, release coordination |
| Reliability | SLO, incident count, MTTR, change failure rate |
| Performance | p95/p99, throughput, CPU/IO, database load |
| Data | Data mismatch, replication lag, reconciliation exceptions |
| Autonomy | Số team/ticket cần phối hợp, thời gian chờ approval |
| Cost | Compute, database, network, observability và engineering effort |
| Quality | Defect rate, contract test failures, rollback frequency |

Sau pilot, so sánh trên cùng định nghĩa và workload. Nếu traffic thay đổi lớn, cần chuẩn hóa theo request/transaction hoặc so sánh cùng cohort.

### Ví dụ success criteria

- Catalog read path được deploy độc lập ít nhất một số lần mà không release monolith.
- p95 của luồng bị ảnh hưởng không regression quá ngưỡng đã thống nhất.
- Không có mismatch dữ liệu vượt tolerance hoặc invariant bị vi phạm.
- Rollback/traffic switch được hoàn tất trong thời gian mục tiêu đã thử nghiệm.
- Số lần phối hợp cross-team cho thay đổi catalog giảm.
- Cost và on-call load nằm trong ngân sách chấp nhận.
- Team có thể xử lý một incident mô phỏng bằng runbook mới.

Con số cụ thể phải được chọn từ SLO và baseline. Không đặt “100% microservices adoption” làm tiêu chí thành công của một pilot.

## 25. Kế hoạch pilot theo giai đoạn

### Giai đoạn 1 — Discovery và boundary

- Phỏng vấn product/domain owners và consumers.
- Vẽ domain/dependency/data maps.
- Xác định pain point, baseline và outcome.
- Chọn scope nhỏ và hard gates.
- Chốt team owner và sponsor.

### Giai đoạn 2 — Modularize bên trong hệ thống cũ

- Tạo module boundary và interface.
- Di chuyển logic vào module sở hữu.
- Loại dependency cycle.
- Tách data access và ghi nhận direct readers/writers.
- Thêm tests bảo vệ contract nội bộ.

### Giai đoạn 3 — Tạo service shell và contract

- Scaffold repository/pipeline.
- Định nghĩa API/event schema.
- Thiết lập identity, security và observability.
- Tạo database/schema đích nếu cần.
- Chạy integration/contract tests với monolith.

### Giai đoạn 4 — Chuyển dữ liệu và traffic từng phần

- Snapshot/CDC/backfill theo kế hoạch.
- Reconcile và kiểm tra invariants.
- Chuyển một route/cohort/batch.
- Theo dõi old/new metrics và mismatch.
- Có stop/rollback switch.

### Giai đoạn 5 — Chuyển ownership

- Chuyển writer authority.
- Migrate consumers.
- Thu hồi direct DB access cũ.
- Bàn giao on-call và tài liệu.
- Theo dõi service độc lập qua nhiều release.

### Giai đoạn 6 — Đánh giá và quyết định tiếp

- So sánh kết quả với baseline.
- Ghi lessons learned và chi phí phát sinh.
- Xác định pattern nào có thể tái sử dụng.
- Điều chỉnh scorecard và guardrails.
- Chọn ứng viên tiếp theo hoặc dừng mở rộng nếu lợi ích không đủ.

## 26. Promotion gates và điều kiện dừng

Một lộ trình extraction cần quyết định rõ khi nào được mở rộng:

- **PASS:** contract tests, data reconciliation, SLI và business invariants đạt; có đủ mẫu và telemetry mới.
- **FAIL:** lỗi nghiệp vụ, data mismatch, access violation, duplicate side effect hoặc SLO regression vượt ngưỡng.
- **UNKNOWN:** thiếu metrics, sample quá ít, replication lag chưa ổn định hoặc consumer chưa được xác minh.

Khi UNKNOWN, giữ phạm vi hiện tại và điều tra. Không coi dashboard rỗng là PASS.

### Các điều kiện dừng ví dụ

- Mismatch dữ liệu vượt tolerance.
- Duplicate charge/order hoặc event processing không idempotent.
- Canary lỗi cao hơn stable theo ngưỡng đã đặt.
- Database saturation tăng và không có capacity fallback.
- Rollback path không còn tương thích với schema đã đổi.
- Team owner hoặc on-call không sẵn sàng.
- Security policy bị bypass hoặc secret lộ.
- Metrics/trace không thể phân biệt traffic cũ/mới.

Các ngưỡng cần được định nghĩa trước và có người có quyền abort. Không kéo dài pilot chỉ vì đã đầu tư nhiều effort.

## 27. Rollback không phải lúc nào cũng là quay về code cũ

Có ba nhóm thay đổi:

1. **Reversible:** routing/feature flag hoặc image có thể đổi lại mà không ảnh hưởng state.
2. **Compensatable:** side effects đã xảy ra nhưng có nghiệp vụ bù trừ, ví dụ hủy reservation hoặc phát correction event.
3. **Irreversible hoặc khó đảo ngược:** schema contract đã bị phá, dữ liệu cũ bị xóa, giao dịch đã hoàn tất hoặc external partner đã xử lý.

Trước khi cutover, xác định nhóm nào áp dụng. Với stateful migration, cần roll-forward plan và restore/reconciliation. Với async events, có thể cần replay hoặc compensating event. Với API, giữ compatibility cho old/new clients trong giai đoạn chuyển đổi.

### Ví dụ chuyển write authority

~~~text
Phase A: Monolith là writer duy nhất
Phase B: Monolith ghi DB + outbox, service mới consume
Phase C: Service mới nhận command/write, monolith chỉ đọc qua API/read model
Phase D: Consumers chuyển hết sang service mới
Phase E: Thu hồi quyền ghi cũ và decommission legacy path
~~~

Mỗi phase có invariant và điểm dừng riêng. Tránh để cả hai bên cùng nhận command và tự ghi dữ liệu độc lập mà không có cơ chế ownership/version rõ.

## 28. Khi nào chọn read-first extraction?

Một read-first extraction có thể giảm rủi ro vì chưa chuyển quyền ghi ngay:

- Tạo API/query model mới.
- Copy/stream dữ liệu qua snapshot/CDC.
- Chạy shadow reads để so sánh kết quả.
- Chuyển một phần traffic đọc.
- Theo dõi freshness và mismatch.
- Sau khi ổn định mới xem xét command/write path.

Nhưng read-first không phải luôn an toàn: response có thể chứa dữ liệu nhạy cảm, cần authorization tương đương; stale read có thể gây quyết định nghiệp vụ sai; dual read có thể tăng tải DB; và hai nguồn có thể khác semantics.

Định nghĩa rõ **read contract**: dữ liệu nào được phép stale, watermark/freshness nào hiển thị, quyền được kiểm tra ở đâu và cách xử lý khi service mới không truy cập được.

## 29. Shadow traffic và so sánh old/new

Một kỹ thuật hữu ích là gửi bản sao request tới service mới nhưng chỉ trả response của hệ thống cũ:

~~~text
Client Request
    |
    v
Legacy Path ------------------------> Client Response
    |
    +---- shadow copy -------------> New Service
                                         |
                                         v
                                  Compare safe outputs
~~~

Chỉ dùng cho request không tạo side effect hoặc service mới chạy ở chế độ read-only/test-safe. Không nhân đôi payment, email, order creation hoặc external API calls chỉ để so sánh. Cần redaction, sampling và policy bảo vệ dữ liệu.

So sánh phải xét semantics, không chỉ JSON equality. Thứ tự danh sách, rounding, timezone, default và quyền lọc dữ liệu có thể khác dù cả hai response đều hợp lệ. Các mismatch cần phân loại và có owner.

## 30. Đánh giá chi phí tổng thể

Tách service tạo thêm các chi phí thường bị bỏ sót:

- Runtime/compute, network và load balancer.
- Database, broker, cache, storage và backup.
- Logging/metrics/tracing retention.
- CI/CD, registry, security scanning và artifact storage.
- On-call, incident response và nâng cấp dependency.
- Engineering time cho contract, migration và compatibility.
- Chi phí phối hợp khi domain boundary chưa rõ.
- Chi phí data duplication và reconciliation.
- Chi phí compliance/region isolation.

So sánh với lợi ích:

~~~text
Net Value =
  Customer/business benefit
+ Delivery/autonomy benefit
+ Reliability/scalability benefit
- New infrastructure cost
- Operational/support cost
- Migration and coordination cost
- Residual risk
~~~

Không cần biến mọi thành phần thành tiền chính xác; nhưng phải ghi rõ assumptions và chủ sở hữu. Nếu lợi ích chỉ xuất hiện sau nhiều năm trong khi chi phí vận hành tăng ngay, cần đánh giá chiến lược và lộ trình khác.

## 31. Những anti-pattern khi chọn service đầu tiên

### 31.1. Chọn module dễ nhất nhưng không có giá trị

Tách một chức năng phụ chỉ để tạo demo có thể dạy nhóm deploy service, nhưng không chứng minh vấn đề kiến trúc được giải quyết. Nếu dùng làm learning spike, phải gọi đúng mục tiêu và không báo cáo đó là business transformation thành công.

### 31.2. Chọn domain quan trọng nhất bất chấp rủi ro

Payment hoặc Order có thể mang giá trị cao nhưng transaction, data correctness và compliance làm pilot rất nguy hiểm. Có thể chuẩn bị boundary, idempotency và reconciliation trước, hoặc chọn một capability ít critical hơn để xây năng lực.

### 31.3. Chọn theo team boundary hiện tại

Một team sở hữu module không có nghĩa module đó là bounded context. Team boundary có thể được tổ chức theo lịch sử, không theo domain. Cần xác minh ownership bằng quy tắc nghiệp vụ và dependency.

### 31.4. Chọn theo công nghệ mới

Tách module để thử Kubernetes, Rust hoặc event streaming thường trộn mục tiêu kiến trúc với mục tiêu thử công nghệ. Nếu muốn thử công nghệ, tạo spike có phạm vi và success criteria riêng; không để khách hàng gánh rủi ro không cần thiết.

### 31.5. Tách service nhưng giữ shared database coupling

Service mới có endpoint riêng nhưng nhiều service vẫn đọc/ghi cùng bảng. Thay đổi schema của một service tiếp tục làm nhiều consumer hỏng; ownership chưa chuyển.

### 31.6. Tách quá nhiều thứ cùng lúc

Một pilot vừa đổi domain, database, framework, message broker, cloud provider và team owner khiến khi có sự cố không thể biết nguyên nhân. Thay đổi theo lớp, kiểm chứng từng giả thuyết.

### 31.7. Đánh giá thành công bằng số service

Số lượng service tăng không đồng nghĩa autonomy, reliability hoặc business value tăng. Đo outcome và chi phí vòng đời.

## 32. Ví dụ chi tiết: chọn Catalog hay Inventory?

Giả sử monolith bán lẻ có Catalog và Inventory. Hai module có các đặc điểm giả định:

| Đặc điểm | Catalog | Inventory |
|---|---|---|
| Thay đổi nghiệp vụ | Thuộc tính, category, import feed | Stock, reservation, reconciliation |
| Tần suất thay đổi | Cao ở import/admin, thấp ở product read | Cao theo giao dịch |
| Critical path | Listing/search; checkout đọc thông tin | Checkout và order confirmation |
| Data ownership | Có thể tách mô tả/category | Còn nhiều writers và transaction |
| Consumers | Web/mobile, search index, reporting | Order, warehouse, replenishment |
| Consistency | Read có thể chấp nhận stale ngắn | Reservation/commit cần correctness cao |
| Team | Có team Catalog | Nhiều nhóm cùng tham gia |
| Pilot risk | Vừa nếu read-first | Cao nếu chuyển write ngay |

Nếu pain point là import Catalog gây contention, một scope tốt có thể là **Catalog ingestion và read API**. Inventory cần tiếp tục chuẩn bị: xác định source of truth, reservation semantics, idempotency và transaction boundaries.

Nhưng nếu Catalog đang ổn định và Reporting có thể tách thành pipeline read-only độc lập, Reporting có thể là lựa chọn đầu tiên ít rủi ro hơn. Quyết định phải quay về mục tiêu và evidence.

## 33. Ví dụ chi tiết: khi Reporting là ứng viên đầu tiên

Reporting thường có một số thuận lợi:

- Chủ yếu đọc dữ liệu, không nằm trên đường commit giao dịch.
- Có thể nhận snapshot/CDC thay vì ghi trực tiếp DB nguồn.
- Có output và freshness SLO riêng.
- Có thể chạy song song để so sánh số liệu.
- Rollback routing sang dashboard/report cũ tương đối đơn giản nếu output được version hóa.

Rủi ro vẫn có:

- Dữ liệu cá nhân/financial cần classification và access controls.
- Backfill có thể gây tải database hoặc warehouse.
- Metric semantics có thể khác nhau giữa report cũ/mới.
- Event late/duplicate có thể làm sai tổng.
- Một số downstream export hoặc finance reconciliation có thể phụ thuộc vào báo cáo.

Một pilot Reporting tốt cần định nghĩa input snapshot, transformation revision, output version, reconciliation checks và ai xác nhận con số. Không vì read-only mà bỏ qua tính đúng đắn dữ liệu.

## 34. Mẫu scorecard cho workshop lựa chọn

~~~markdown
# Candidate assessment

## Candidate
- Name:
- Domain:
- Sponsor:
- Proposed owner:
- Scope of first extraction:

## Problem and value
- Current pain:
- Baseline evidence:
- Expected outcome:
- Time to measurable value:
- Business/customer impact:

## Separability
- Bounded context:
- Data owner/source of truth:
- Shared writers/readers:
- API/event contract:
- Dependency cycles:
- Deployment autonomy:
- Team/on-call readiness:

## Risk
- Business criticality:
- Data sensitivity:
- Consistency requirements:
- Security/compliance:
- Migration/rollback:
- Dependency blast radius:
- Operational maturity:

## Hard gates
- Domain owner confirmed:
- Data ownership agreed:
- Security model approved:
- Observability ready:
- Recovery plan tested:
- Contract compatibility proven:

## Score
- Value:
- Separability:
- Risk controllability:
- Weighted score:
- Evidence confidence:

## Decision
- SELECT / HOLD / REJECT / PREPARE FIRST
- Scope:
- Conditions:
- Stop criteria:
- Success measures:
- Review date:
~~~

Workshop nên có product, service owner, data, security, operations và platform đại diện. Nếu một nhóm không thể tham gia, ghi rõ assumption và owner cần xác nhận sau; không tự biến unknown thành điểm cao.

## 35. Cách xử lý khi hai ứng viên có điểm gần nhau

Nếu hai ứng viên gần điểm, đừng tranh luận về 0,1 điểm. Hãy so sánh:

1. Ứng viên nào giải quyết pain point có sponsor và baseline rõ hơn?
2. Ứng viên nào cho kết quả đo được sớm hơn?
3. Ứng viên nào tạo reusable pattern cho bước tiếp theo?
4. Ứng viên nào có hard gates đã đạt?
5. Ứng viên nào có blast radius nhỏ hơn khi thử?
6. Ứng viên nào có rollback/restore rõ hơn?
7. Ứng viên nào giúp tổ chức học được kỹ năng còn thiếu?
8. Chi phí cơ hội nếu trì hoãn từng ứng viên là gì?

Có thể chọn một ứng viên làm **technical spike** và một ứng viên làm **business pilot**, nhưng phải phân biệt mục tiêu và không mở hai production migrations lớn cùng lúc.

## 36. Quy trình ra quyết định theo stage gate

Một lộ trình lựa chọn có thể chia thành:

~~~text
DISCOVERY
  |
  v
PROBLEM + BASELINE
  |
  v
DOMAIN / DATA / DEPENDENCY MAP
  |
  v
VALUE-RISK-SEPARABILITY SCORECARD
  |
  v
HARD GATES
  |
  +-- Not ready --> PREPARE / HOLD
  |
  v
PILOT SCOPE + SUCCESS/STOP CRITERIA
  |
  v
REHEARSAL + TESTS
  |
  v
STAGED EXTRACTION
  |
  v
MEASURE OUTCOMES
  |
  +-- Benefit proven --> Select next candidate
  |
  +-- Benefit weak --> Reconsider architecture/strategy
~~~

Mỗi gate cần một người có quyền quyết định, evidence và ngày xem xét. Không nên để scorecard tự động chọn service mà thiếu workshop domain và data ownership.

## 37. Bài tập tình huống: chọn service đầu tiên cho hệ thống thương mại điện tử

Một monolith có các module:

- Customer Profile: thông tin và preference người dùng.
- Catalog: sản phẩm, category, mô tả.
- Inventory: tồn kho và reservation.
- Order: vòng đời đơn hàng.
- Payment: tích hợp cổng thanh toán.
- Reporting: báo cáo doanh thu và vận hành.

Bối cảnh:

- Catalog import mỗi giờ, đôi lúc làm DB CPU tăng.
- Order và Inventory cùng đọc/ghi một số bảng.
- Payment có yêu cầu audit và idempotency cao.
- Reporting có thể chạy read-only nhưng đang query trực tiếp DB monolith.
- Team Catalog có 5 người, owner rõ và có on-call.
- Team Reporting có 2 người, chưa có pipeline lineage.
- Hệ thống chưa có CDC production nhưng có thể triển khai trong staging.

### Câu hỏi

1. Chọn Catalog, Reporting hay module khác làm pilot? Bằng chứng nào cần bổ sung?
2. Giá trị nào của Catalog có thể đo được trước/sau?
3. Vì sao Payment có thể không phù hợp làm pilot đầu dù business criticality cao?
4. Reporting read-only có thực sự rủi ro thấp nếu dữ liệu nhạy cảm và metric dùng cho finance?
5. Catalog có thể bắt đầu bằng read API, import pipeline hay write ownership? Vì sao?
6. Những shared DB readers/writers nào cần inventory trước khi extraction?
7. Cần hard gates nào trước khi chuyển traffic?
8. Khi data mismatch xảy ra, dừng ở đâu và ai có quyền abort?
9. Success metrics nào phản ánh business outcome và team autonomy?
10. Nếu pilot không giảm lead time hoặc chi phí vận hành tăng mạnh, nên làm gì tiếp?

### Gợi ý phân tích

- Catalog có owner và pain point import cụ thể; có thể là ứng viên tốt nếu data boundary đủ rõ.
- Reporting có thể ít ảnh hưởng transaction path nhưng cần lineage, freshness, privacy và reconciliation; không tự động ít rủi ro.
- Payment có criticality và side effects cao; nên chuẩn bị idempotency, reconciliation và recovery trước khi dùng làm pilot đầu.
- Inventory shared writers/transactions làm separability thấp; có thể refactor domain boundary trước.
- Chọn scope hẹp: tách import/read path hoặc một nhóm endpoint, không chuyển toàn bộ Catalog và database cùng lúc.
- Success criteria phải có baseline về DB load, import duration, p95, deployment lead time, data mismatch và on-call effort.
- Nếu benefit không đủ, giữ module trong modular monolith hoặc điều chỉnh boundary; không bắt buộc tiếp tục tách vì đã tạo service.

## 38. Bài tập thực hành: tạo dependency inventory

Chọn một module ứng viên và lập bảng:

| Consumer | Loại phụ thuộc | Resource | Hướng truy cập | Tần suất | Owner | Kế hoạch |
|---|---|---|---|---|---|---|
| Order API | SQL | product table | Read | Cao | Order | Thay bằng API/read model |
| Admin portal | HTTP | Catalog API | Read/write | Trung bình | Catalog | Giữ contract |
| Import job | SQL | product table | Write | Theo batch | Catalog | Chuyển sang service mới |
| Reporting | SQL | product view | Read | Theo giờ | Data | CDC/read model |
| Search indexer | Event | ProductChanged | Consume | Cao | Search | Version event schema |

Sau đó trả lời:

- Có direct writer nào không được domain owner kiểm soát?
- Có query join xuyên domain không?
- Có batch job chạy ngoài giờ mà không nằm trong deployment inventory?
- Có consumer không ai sở hữu?
- Có dependency cycle?
- Có contract nào chưa được version hóa?
- Có thể đo usage để biết đường cũ đã không còn được gọi không?

Đừng chuyển sang cutover khi chưa hiểu những đường truy cập ẩn như cron jobs, stored procedures, BI tools, scripts và support operations.

## 39. Kết luận

Chọn dịch vụ đầu tiên là bài toán **tối ưu giá trị có kiểm soát rủi ro và khả năng tách**, không phải chọn module nhỏ nhất, nóng nhất hoặc đang được nhắc tới nhiều nhất. Giá trị cần gắn với pain point và baseline; rủi ro phải xét business/data/security/operations; separability phải được chứng minh bằng domain ownership, data authority, contract và khả năng phát hành độc lập.

Nếu boundary chưa rõ, hãy tạo modular monolith, loại dependency cycle và làm rõ ownership trước. Nếu ứng viên đã sẵn sàng, tách theo scope nhỏ bằng strangler/branch-by-abstraction, quản lý data migration và contract compatibility, rollout từng phần, quan sát business invariants và có điều kiện dừng rõ. Sau pilot, đo cả kết quả lẫn chi phí vận hành rồi mới chọn bước tiếp theo.

**Một service đầu tiên tốt không chỉ chạy được ở process riêng; nó chứng minh rằng một capability có thể được sở hữu, thay đổi, triển khai và vận hành độc lập với lợi ích thực tế mà rủi ro vẫn nằm trong giới hạn đã chấp nhận.**
