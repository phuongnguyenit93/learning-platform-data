# Xác định mục tiêu có thể đo trước khi chuyển sang vi dịch vụ

## 1. Vì sao phải bắt đầu bằng mục tiêu?

Chuyển từ ứng dụng nguyên khối (monolith) sang kiến trúc vi dịch vụ (microservices) là một quyết định đầu tư vào khả năng phát triển, triển khai và vận hành các thành phần độc lập. Việc tách dịch vụ làm tăng chi phí giao tiếp qua mạng, điều phối dữ liệu, quan sát hệ thống và quản trị vận hành. Vì vậy, “muốn dùng microservices”, “muốn hiện đại hóa công nghệ” hoặc “muốn dễ mở rộng” chưa phải là mục tiêu có thể kiểm chứng.

Trước khi thay đổi kiến trúc, nhóm cần trả lời bốn câu hỏi:

1. **Vấn đề kinh doanh hoặc kỹ thuật hiện tại là gì?** Ai đang chịu tác động và bằng chứng nào cho thấy vấn đề tồn tại?
2. **Kết quả mong muốn là gì?** Kết quả ấy được biểu diễn bằng một chỉ số cụ thể, đơn vị đo và phạm vi rõ ràng ra sao?
3. **Mức cải thiện nào đủ để biện minh cho chi phí chuyển đổi?** Mốc hiện tại (baseline), ngưỡng đích, thời hạn và giới hạn không được vi phạm là gì?
4. **Microservices có thật sự cần thiết để đạt kết quả đó không?** Có phương án ít phức tạp hơn, như tối ưu ứng dụng hiện có hoặc modular monolith, đạt cùng kết quả với chi phí thấp hơn không?

Nguyên tắc trung tâm: **mục tiêu quyết định kiến trúc, không để tên kiến trúc thay thế mục tiêu**.

## 2. Phân biệt mục tiêu, chỉ số và giải pháp

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Vấn đề | Điều gì đang gây tổn thất? | Mỗi đợt phát hành phải kiểm thử lại toàn hệ thống, khiến tính năng thanh toán ra mắt chậm |
| Mục tiêu | Muốn thay đổi kết quả nào? | Rút ngắn thời gian đưa thay đổi thanh toán từ hoàn tất code đến production |
| Chỉ số | Đo tiến triển bằng gì? | Lead time for changes, tính theo giờ hoặc ngày |
| Baseline | Hiện tại là bao nhiêu? | Trung vị 8 ngày qua 12 tuần gần nhất |
| Target | Khi nào coi là đạt? | Trung vị ≤ 2 ngày trong quý tới |
| Guardrail | Điều gì không được xấu đi? | Tỷ lệ lỗi khi triển khai không tăng; không làm giảm khả năng thanh toán thành công |
| Giải pháp giả định | Thay đổi nào có thể tạo ra kết quả? | Tách khả năng triển khai của miền thanh toán, trước tiên thử tạo ranh giới module và pipeline độc lập |

Các số trong bảng là **ví dụ giả định**, không phải mức chuẩn cho mọi tổ chức.

Một mục tiêu tốt phải cho phép nhóm kết luận cả **đạt** lẫn **không đạt**, ngay cả khi việc chuyển đổi kỹ thuật đã hoàn tất. “Đã có 12 microservices” chỉ là kết quả triển khai kiến trúc, không phải bằng chứng cho thấy người dùng hoặc tổ chức được hưởng lợi.

## 3. Viết mục tiêu theo cấu trúc có thể kiểm chứng

Sử dụng mẫu:

> Trong **[phạm vi dịch vụ/luồng nghiệp vụ]**, giảm/tăng **[chỉ số được định nghĩa chính xác]** từ **[baseline và thời kỳ đo]** đến **[target]** trước **[mốc thời gian]**, với điều kiện **[guardrail]**, được đối chiếu trên **[nguồn dữ liệu và phương pháp đo]**.

Ví dụ:

> Trong luồng tạo đơn hàng, giảm p95 độ trễ API từ 900 ms (đo ở production trong 28 ngày, loại trừ traffic thử nghiệm) xuống dưới 450 ms trong ba tháng; đồng thời duy trì tỷ lệ lỗi 5xx dưới 0,2% và không tăng chi phí hạ tầng trên mỗi đơn hàng thành công quá 15%.

Để mục tiêu có khả năng kiểm chứng, xác định đầy đủ:

- **Đối tượng đo:** API, hành trình người dùng, năng lực nghiệp vụ, nhóm phát triển hay toàn bộ hệ thống.
- **Định nghĩa công thức:** p95 latency là phân vị thứ 95 của mẫu yêu cầu nào; lead time tính từ commit, merge hay thời điểm bắt đầu phát triển; availability có loại trừ planned maintenance không.
- **Nguồn dữ liệu:** tracing/metrics, CI/CD, quản lý sự cố, APM, hóa đơn cloud, dữ liệu đơn hàng.
- **Khoảng lấy mẫu:** đủ dài để bao phủ ngày cao điểm, phát hành và chu kỳ nghiệp vụ; ghi chú tính mùa vụ.
- **Thời điểm và người chịu trách nhiệm:** ai thu thập, ai quyết định đạt/không đạt, khi nào xem lại.
- **Giới hạn và tác động phụ:** độ tin cậy, bảo mật, tính nhất quán dữ liệu, trải nghiệm người dùng, chi phí và năng lực đội ngũ.

Không nên chọn mức đích trước khi biết phân bố hiện tại, khối lượng tải và những biến cố gây nhiễu. Với hệ thống biến động mạnh, ngoài trung vị cần theo dõi p95/p99 hoặc chỉ số theo từng phân khúc.

## 4. Bộ chỉ số để xác định lý do chuyển đổi

Chọn một số ít chỉ số phù hợp với vấn đề thật sự, không dùng mọi chỉ số như mục tiêu đồng thời.

### 4.1. Tốc độ cung cấp giá trị

**Lead time for changes:** thời gian từ một điểm bắt đầu thống nhất (thí dụ commit/merge) đến khi thay đổi chạy ở production. Nên phân tích thêm theo miền nghiệp vụ để biết điểm nghẽn ở đâu.

**Deployment frequency:** số lần triển khai thành công mỗi ngày/tuần cho đúng phạm vi cần cải thiện. Tần suất cao chỉ hữu ích khi thay đổi có giá trị và an toàn.

**Thời gian chờ do phụ thuộc nhóm:** số giờ/ngày một thay đổi chờ đội khác phê duyệt, phối hợp phát hành hoặc sửa giao diện chung. Chỉ số này giúp kiểm tra giả thuyết “cần triển khai độc lập”.

### 4.2. Chất lượng và khả năng phục hồi

**Change failure rate:** tỷ lệ triển khai gây suy giảm dịch vụ và cần rollback, hotfix hoặc can thiệp khẩn cấp, theo định nghĩa sự cố đã thống nhất.

**Thời gian khôi phục dịch vụ:** đo từ khi sự cố bắt đầu hoặc được phát hiện (chọn một cách nhất quán) đến khi dịch vụ phục hồi theo tiêu chí đã định. Theo dõi cả phạm vi ảnh hưởng và số người dùng chịu tác động.

**Availability và SLO:** tỷ lệ yêu cầu đáp ứng điều kiện hoạt động trong một cửa sổ thời gian, kèm error budget. Việc tách dịch vụ có thể cô lập một số lỗi, nhưng cũng có thể tạo chuỗi phụ thuộc và lỗi dây chuyền.

### 4.3. Hiệu năng và mở rộng

**Latency:** p50/p95/p99 theo endpoint và hành trình người dùng, phân biệt thời gian xử lý ứng dụng, truy vấn dữ liệu và các lời gọi mạng.

**Throughput, mức tải và khả năng chịu đỉnh:** số yêu cầu/giao dịch thành công mỗi giây ở mức tải xác định, trong khi latency và lỗi vẫn dưới ngưỡng.

**Hiệu quả mở rộng:** số tài nguyên bổ sung hoặc chi phí cần để xử lý thêm một đơn vị công việc. Microservices chỉ có lợi về mở rộng độc lập khi mỗi miền có đặc điểm tải riêng và cấu trúc dữ liệu cho phép.

### 4.4. Kinh tế và tổ chức

**Chi phí trên giao dịch thành công:** tổng chi phí vận hành liên quan chia cho số giao dịch thành công; quy định rõ chi phí cloud, license, logging, lưu trữ, mạng và nhân sự nào được đưa vào.

**Thời gian onboarding và quyền sở hữu:** thời gian một kỹ sư mới có thể thực hiện thay đổi an toàn, số thành phần mỗi nhóm cần đồng bộ để phát hành.

**Độ độc lập giữa nhóm:** tỷ lệ thay đổi của một miền có thể triển khai mà không buộc nhóm khác triển khai cùng lúc. Đây là chỉ số gần với giá trị cốt lõi của việc tách dịch vụ.

Một chỉ số đơn lẻ hiếm khi đủ để ra quyết định. Ví dụ, tăng deployment frequency nhưng change failure rate tăng mạnh có thể khiến kết quả thực tế kém hơn.

## 5. Đo baseline đúng trước khi đề xuất giải pháp

1. **Khoanh vùng:** chọn một hành trình quan trọng (như đặt hàng, thanh toán), không lấy số trung bình toàn hệ thống để che khuất một điểm nghẽn cụ thể.
2. **Thu thập đủ chứng cứ:** lấy dữ liệu từ môi trường production và pipeline hiện hành; ghi lại ngày bắt đầu/kết thúc, lưu lượng, version và cơ chế lấy mẫu.
3. **Kiểm tra nguyên nhân:** phân biệt điểm nghẽn do kiến trúc với điểm nghẽn do SQL chậm, thiếu index, deploy thủ công, kiểm thử bất ổn, cấu hình sai hoặc thiếu nhân sự.
4. **Tính baseline:** ghi cả giá trị trung tâm, phân bố, biến thiên và những ngày ngoại lệ; lưu truy vấn/dashboard để có thể tái lập phép đo.
5. **Đặt mục tiêu và guardrail:** gắn với lợi ích có thể lượng hóa, thời hạn thực tế và rủi ro chấp nhận được.
6. **Chọn phương án để thử:** so sánh tối ưu monolith, modular monolith, tách một dịch vụ hoặc cải thiện quy trình phát hành.
7. **Đo lại cùng định nghĩa:** giữ nguyên phạm vi, công thức, điều kiện tải và nguồn dữ liệu khi so sánh trước/sau; ghi các thay đổi đồng thời.

Nếu chưa có khả năng đo lead time, p95 latency hoặc lỗi đầu cuối, ưu tiên xây dựng telemetry và định nghĩa phép đo trước. Thực hiện migration mà không có baseline khiến việc quy kết cải thiện cho kiến trúc trở nên thiếu căn cứ.

## 6. Ví dụ quyết định: hệ thống thương mại điện tử

Giả sử một ứng dụng nguyên khối chứa Catalog, Checkout, Payment và Notification. Nhóm phát triển đang cân nhắc tách Payment thành vi dịch vụ.

**Dấu hiệu ban đầu:**

- Payment có quy định tích hợp và chu kỳ phát hành riêng.
- Sửa một thành phần nhỏ phải chạy kiểm thử tích hợp toàn bộ và đợi lịch phát hành chung.
- Đợt tải tăng ở Catalog thường làm ứng dụng chịu áp lực tài nguyên, nhưng chưa chứng minh rằng Payment cần mở rộng riêng.

Đặt giả thuyết H1: tạo ranh giới triển khai độc lập cho Payment sẽ giảm thời gian đưa thay đổi lên production mà không tăng rủi ro giao dịch.

| Chỉ số (ví dụ giả định) | Baseline | Ngưỡng chấp nhận sau thử nghiệm |
|---|---:|---:|
| Median lead time của thay đổi Payment | 7 ngày | ≤ 2 ngày |
| Tỷ lệ phát hành Payment cần đồng bộ với nhóm khác | 80% | ≤ 20% |
| Change failure rate liên quan Payment | 5% | ≤ 5% |
| Tỷ lệ thanh toán thành công | 98,8% | ≥ 98,8% ở cùng loại giao dịch |
| Chi phí vận hành Payment / giao dịch thành công | 100 đơn vị | ≤ 115 đơn vị |

Thay vì tách ngay toàn bộ hệ thống, thử theo từng cổng quyết định:

**Giai đoạn A – cải thiện hệ thống hiện hữu.** Tách module Payment về mặt mã nguồn, xác định interface, xây dựng contract test, rút ngắn pipeline và đưa quy trình phát hành vào tự động hóa. Đo lại lead time và dependency. Nếu đạt mục tiêu với modular monolith, chưa cần nhận thêm chi phí phân tán.

**Giai đoạn B – thử tách giới hạn.** Nếu triển khai độc lập thật sự vẫn bị ràng buộc bởi tiến trình chạy chung, chọn một đường đi hẹp của Payment với ownership rõ, giao diện API/version, kế hoạch xử lý thất bại và khả năng rollback. Chạy thử có kiểm soát và đo độ trễ, lỗi, mức phụ thuộc cũng như chi phí.

**Giai đoạn C – quyết định dựa trên số liệu.** Mở rộng khi mục tiêu chính đạt, guardrails giữ ổn định và lợi ích đủ bù chi phí. Dừng hoặc quay về phương án đơn giản hơn khi cải thiện không đáng kể hoặc rủi ro tăng.

Lưu ý rằng chính xác một giao dịch thanh toán xuyên ranh giới dịch vụ có thể đòi hỏi idempotency, thiết kế trạng thái, timeout, retry an toàn, outbox/saga hoặc đối soát. Các cơ chế này cần được tính trong chi phí và nguy cơ, không mặc định là miễn phí.

## 7. So sánh phương án dựa trên mục tiêu

| Phương án | Khi phù hợp | Giới hạn cần kiểm tra |
|---|---|---|
| Tối ưu monolith và CI/CD | Điểm nghẽn là database, kiểm thử, pipeline hoặc quy trình | Khó giải quyết triển khai độc lập thực sự nếu chung runtime |
| Modular monolith | Cần ranh giới miền rõ và khả năng phát triển độc lập ở cấp code | Vẫn triển khai theo một đơn vị, cần kỷ luật giữ ranh giới |
| Tách một vài dịch vụ | Có miền cần scaling, release, bảo mật hoặc ownership độc lập có bằng chứng | Tăng độ phức tạp mạng, dữ liệu, observability và vận hành |
| Chuyển sang microservices trên diện rộng | Nhiều miền đã có nhu cầu độc lập, có năng lực platform và dữ liệu thực nghiệm hỗ trợ | Chi phí nền tảng lớn, rủi ro migration và phối hợp tổ chức |

Đánh giá các phương án trên cùng một bộ KPI và guardrail. Chỉ số “số lượng dịch vụ được tạo” có thể dùng để quản lý tiến độ dự án nhưng không chứng minh thành công kiến trúc.

## 8. Thiết kế thí nghiệm và điều kiện dừng

Định nghĩa một **decision gate** trước khi chạy thử:

- **Giả thuyết:** điều gì khiến kiến trúc hiện tại không đạt target?
- **Can thiệp:** thay đổi cụ thể nào được thực hiện trong phạm vi hẹp?
- **Nhóm so sánh:** dùng cùng hành trình nghiệp vụ, hoặc so với miền tương tự nếu có; nêu các yếu tố gây nhiễu.
- **Khoảng đánh giá:** dài đủ để quan sát nhiều chu kỳ phát hành và tải điển hình.
- **Tiêu chí mở rộng:** target đạt bền vững và guardrail không bị vi phạm.
- **Tiêu chí dừng/quay lui:** lỗi giao dịch tăng, budget vận hành vượt ngưỡng, độ phức tạp vượt khả năng hỗ trợ hoặc kết quả không khác baseline đáng kể.
- **Quyền quyết định:** người phụ trách sản phẩm, kiến trúc, vận hành, bảo mật và dữ liệu cùng xác nhận kết quả.

Ví dụ sơ đồ ra quyết định:

```text
Vấn đề có bằng chứng?
  ├─ Không → đo và xác minh vấn đề
  └─ Có → định nghĩa KPI, baseline, target, guardrails
             ↓
        Thử tối ưu phương án đơn giản
             ├─ Đạt mục tiêu → giữ phương án hiện tại
             └─ Chưa đạt → thử tách miền nhỏ có rollback
                              ├─ Đạt target + giữ guardrails → cân nhắc mở rộng
                              └─ Không → dừng/điều chỉnh giả thuyết
```

Một dự án chuyển đổi có thể hoàn thành đúng kế hoạch mà không cải thiện KPI; trường hợp đó phải được ghi nhận là **chưa chứng minh hiệu quả**, không tự động tuyên bố thành công.

## 9. Mẫu tài liệu quyết định kiến trúc (ADR)

```markdown
# ADR: Có nên tách <bounded context> thành microservice?

Ngày / người chịu trách nhiệm:
Bối cảnh và vấn đề có bằng chứng:
Phạm vi người dùng và nghiệp vụ:
Các phương án: tối ưu monolith / modular monolith / tách dịch vụ

KPI chính:
- Tên và công thức:
- Baseline, nguồn dữ liệu, khoảng đo:
- Target và ngày đánh giá:

Guardrails:
- Độ tin cậy / dữ liệu:
- Hiệu năng / bảo mật:
- Chi phí / năng lực vận hành:

Giả thuyết và can thiệp:
Chi phí ước tính và dependency cần xử lý:
Phương án rollback:
Kết quả thử nghiệm (số liệu trước/sau):
Quyết định: Giữ / Thử tiếp / Mở rộng / Dừng
Ngày xem xét lại:
```

Ghi nhận các giả định chưa xác minh để người đọc không hiểu các số mục tiêu thành thực tế quan sát được.

## 10. Các sai lầm thường gặp

**Đưa giải pháp vào mục tiêu:** “Tách thành 20 dịch vụ trong 6 tháng” khuyến khích tăng số dịch vụ ngay cả khi năng suất giảm. Hãy ưu tiên mục tiêu về lead time, resilience hoặc chi phí có baseline và guardrail.

**Chọn KPI chỉ dễ đo:** số container, API hoặc repository không trực tiếp phản ánh giá trị người dùng. Tốt hơn là chọn chỉ số tác động và giữ chỉ số triển khai như dữ liệu phụ trợ.

**So sánh không cùng điều kiện:** p95 trên traffic thấp sau migration không thể so trực tiếp với p95 ở mùa cao điểm trước migration. Cần cố định hoặc hiệu chỉnh phân khúc và điều kiện đo.

**Bỏ qua tác động xuyên dịch vụ:** một endpoint nhanh hơn nhưng trải nghiệm checkout chậm hơn do gọi nhiều hop không đáp ứng mục tiêu người dùng. Đo end-to-end thay vì chỉ đo dịch vụ riêng.

**Không tính chi phí vận hành:** service mesh, tracing, on-call, incident coordination, versioning, data migration và năng lực vận hành đều là một phần của bài toán hiệu quả.

**Không thiết lập quyền dừng:** nếu không có tiêu chí dừng từ đầu, nhóm dễ tiếp tục migration chỉ vì đã đầu tư nhiều. Decision gate làm quyết định minh bạch hơn.

## 11. Checklist trước khi thông qua chuyển đổi

- [ ] Có vấn đề được chứng minh bằng dữ liệu hoặc sự cố cụ thể.
- [ ] Xác định miền nghiệp vụ và nhóm người dùng chịu tác động.
- [ ] Có 1–3 KPI chính với công thức, baseline, target, thời hạn và nguồn đo.
- [ ] Có guardrails cho độ tin cậy, bảo mật, dữ liệu, trải nghiệm và chi phí.
- [ ] Đã phân tích nguyên nhân và thử hoặc đánh giá phương án đơn giản hơn.
- [ ] Có giả thuyết cho lợi ích riêng của việc tách dịch vụ.
- [ ] Có khả năng quan sát luồng đầu cuối và so sánh trước/sau.
- [ ] Có phạm vi thử nghiệm nhỏ, kế hoạch rollback và tiêu chí dừng.
- [ ] Có người chịu trách nhiệm và lịch đánh giá quyết định.

## 12. Bài tập áp dụng

Một ứng dụng bán vé hiện có median lead time 9 ngày cho mỗi thay đổi, p95 thời gian đặt vé 1,2 giây và change failure rate 4%. Nhóm cho rằng microservices sẽ giải quyết mọi vấn đề.

Hãy thực hiện:

1. Viết **hai giả thuyết nguyên nhân** khác nhau cho lead time cao (một do kiến trúc, một do quy trình).
2. Viết **một mục tiêu có thể đo**, chỉ rõ công thức và phạm vi của ít nhất một KPI, baseline, target, thời hạn và nguồn dữ liệu.
3. Chọn **hai guardrails** bảo vệ hành trình đặt vé và chi phí.
4. Đề xuất **một thử nghiệm ngắn hạn trên monolith** và **một thử nghiệm tách dịch vụ có kiểm soát**; nói rõ phép đo giúp so sánh chúng.
5. Mô tả điều kiện để **giữ monolith, mở rộng microservices hoặc dừng chuyển đổi**.

Không có đáp án duy nhất về ngưỡng đích: cách lập luận và khả năng chứng minh kết quả quan trọng hơn việc chọn một con số hấp dẫn.

## 13. Ghi nhớ

Microservices là một phương án kiến trúc có đánh đổi. Quyết định chuyển đổi cần được bảo vệ bằng vấn đề thật, chỉ số có công thức, baseline đáng tin cậy, mục tiêu gắn với thời hạn, guardrails và kết quả thử nghiệm. **Một chuyển đổi chỉ tạo giá trị khi cải thiện kết quả cần thiết với chi phí và rủi ro chấp nhận được.**
