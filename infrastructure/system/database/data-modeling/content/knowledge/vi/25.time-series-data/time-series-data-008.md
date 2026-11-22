# Thời gian lưu theo từng mức chi tiết và yêu cầu truy vết

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Thiết kế **chính sách thời gian lưu (retention)** cho dữ liệu chuỗi thời gian theo từng độ phân giải: điểm đo gốc, tổng hợp 1 phút, 1 giờ, 1 ngày và dữ liệu sự cố.
- Phân biệt **độ chi tiết**, **độ tươi**, **khoảng thời gian lưu**, **thời gian sự kiện** và **thời gian nạp**; không đánh đồng việc làm thưa dữ liệu với xóa lịch sử nghiệp vụ.
- Chọn những thống kê có thể tổng hợp đúng từ cấp nhỏ lên cấp lớn, đồng thời nhận biết thông tin **không thể khôi phục** sau downsampling.
- Xác định **yêu cầu truy vết** ở các cấp: kiểm tra KPI, chẩn đoán sự cố, đối soát nguồn và lưu bằng chứng có thể kiểm chứng.
- Thiết kế khóa, bucket thời gian, partition, rollup, chỉ mục, metadata dòng dữ liệu và quy trình xóa/lưu trữ bằng ví dụ PostgreSQL.
- Xử lý dữ liệu đến muộn, bản ghi trùng, hiệu chỉnh hồi tố, lỗi đồng hồ thiết bị, thiếu điểm đo và yêu cầu giữ lại bằng chứng đang điều tra.
- Đưa ra lựa chọn có cơ sở giữa chi phí lưu trữ, tốc độ truy vấn, quyền riêng tư và khả năng tái lập kết quả, thay vì đặt một TTL duy nhất cho mọi dữ liệu.

Trong module **DATABASE_DATA_MODELING**, thiết kế dữ liệu không dừng ở bảng, khóa, chỉ mục và tính nhất quán lúc ghi. Với **dữ liệu chuỗi thời gian**, một quyết định quan trọng khác là: **giữ dữ liệu ở độ chi tiết nào trong bao lâu để vừa trả lời báo cáo, vừa đủ bằng chứng khi có vấn đề?** Giữ tất cả điểm đo mãi mãi có thể làm chi phí và thời gian vận hành tăng mạnh. Ngược lại, chỉ giữ trung bình theo ngày có thể khiến một sự cố kéo dài vài phút biến mất khỏi lịch sử. Bài học này tập trung vào sự đánh đổi ấy và cách biến nó thành một hợp đồng dữ liệu có thể kiểm chứng.

## 1. Bài toán xuyên suốt: giám sát nhiệt độ chuỗi lạnh

Giả sử một doanh nghiệp vận chuyển dược phẩm vận hành nhiều kho lạnh. Mỗi thiết bị cảm biến gửi **một phép đo nhiệt độ mỗi phút**. Nền tảng phải đáp ứng các nhu cầu:

1. **Vận hành tức thời:** biết kho nào vừa vượt ngưỡng; mở biểu đồ chi tiết 30 phút gần đây để xác định dao động.
2. **Phân tích ngắn hạn:** so sánh nhiệt độ tối thiểu, tối đa và trung bình theo giờ trong 6 tháng.
3. **Phân tích dài hạn:** xem xu hướng theo ngày và tỷ lệ thời gian ở ngoài ngưỡng trong nhiều năm.
4. **Điều tra sự cố:** khi báo động lúc 10:15, phải tìm được dữ liệu đo liên quan, chất lượng mẫu, mốc nhận dữ liệu, thiết bị và chính sách ngưỡng đã áp dụng.
5. **Tuân thủ hợp đồng:** một số sự cố đã xác nhận cần bằng chứng dài hạn; các điểm đo thông thường không nhất thiết có cùng thời hạn.
6. **Quyền riêng tư và vòng đời dữ liệu:** dữ liệu về nhân sự/định vị, nếu có, không được giữ chỉ vì hệ thống có đủ dung lượng.

Các thời hạn dưới đây đều là **giả định thiết kế để học**, không phải quy định pháp luật cho dược phẩm hoặc lời khuyên tuân thủ áp dụng chung:

| Lớp dữ liệu | Grain / mức chi tiết | Ví dụ thời gian giữ | Phục vụ mục đích gì? |
| --- | --- | --- | --- |
| Điểm đo gốc (hot raw) | Một mẫu theo thiết bị và thời điểm đo | 30 ngày trên kho truy vấn nhanh | Debug, cảnh báo, biểu đồ chi tiết |
| Điểm đo gốc lưu trữ lạnh | Vẫn là từng mẫu gốc | Thêm 150 ngày, tổng cộng 180 ngày | Điều tra muộn và tái xử lý khi cần |
| Rollup 5 phút | Một thiết bị–một bucket 5 phút | 180 ngày | Quan sát biến động ngắn hạn rẻ hơn raw |
| Rollup 1 giờ | Một thiết bị–một giờ UTC | 3 năm | Báo cáo mùa vụ, chất lượng vận hành |
| Rollup 1 ngày | Một thiết bị–một ngày theo lịch doanh nghiệp | 5 năm | Xu hướng dài hạn, KPI đã định nghĩa |
| Gói bằng chứng sự cố nghiêm trọng | Một vụ việc và những đoạn raw/metadata có liên quan | Theo hợp đồng, ví dụ 5 năm | Truy vết quyết định và kiểm tra độc lập |
| Audit / lineage của pipeline | Một lần nạp, phiên bản phép biến đổi, manifest | Theo chính sách kiểm toán riêng | Giải thích dữ liệu được tạo và thay đổi thế nào |

**Lưu ý:** "raw 30 ngày hot + 150 ngày cold" là **hai tầng lưu trữ của cùng mức chi tiết**, không phải hai bản ghi nghiệp vụ khác nhau. Cần quyết định thời hạn **tổng** và trách nhiệm xóa từng bản; không hiểu rằng 30 ngày hot cộng thêm 180 ngày archive thành 210 ngày nếu hợp đồng quy định tổng chỉ 180 ngày.

### Ba câu hỏi trước khi đặt TTL

- **Nếu xóa raw sau 180 ngày, báo cáo còn cần biết sự cố nào xảy ra ở phút thứ 15 không?** Nếu có, phải lưu sự kiện vượt ngưỡng hoặc bằng chứng chi tiết trước khi xóa.
- **Nếu chỉ còn trung bình ngày, có thể chứng minh cảm biến chưa từng vượt ngưỡng không?** Không; giá trị trung bình không chứa đầy đủ mọi cực trị hay thời lượng vượt ngưỡng.
- **Nếu một phép đo gốc nằm trong vụ việc đang điều tra, có được xóa theo TTL thông thường không?** Phụ thuộc chính sách giữ bằng chứng. Phải có cơ chế đánh dấu giữ có kiểm soát và lịch giải phóng, không mặc định xóa.

## 2. Đừng nhầm độ phân giải với thời gian lưu

Hai trục thiết kế độc lập:

- **Độ phân giải (resolution):** một hàng đại diện cho một điểm đo hay cho một bucket 5 phút/giờ/ngày?
- **Thời hạn lưu (retention period):** hàng ở độ phân giải đó có thể được truy cập trong bao lâu kể từ mốc bắt đầu tính thời hạn?

Một số khái niệm dễ lẫn:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Sampling cadence | Nhịp thiết bị dự kiến gửi mẫu | Mỗi 60 giây |
| Event time / observed_at | Khi nhiệt độ thực tế được thiết bị đo theo nguồn thời gian được tin cậy | 10:15:00Z |
| Ingest time / received_at | Khi nền tảng nhận mẫu | 10:16:12Z |
| Bucket start | Đầu cửa sổ gom mẫu theo chuẩn được quy định | 10:00:00Z cho bucket 1 giờ |
| Granularity | Một hàng tổng hợp đại diện cho bao nhiêu thời gian và thực thể | Một thiết bị–một giờ |
| Freshness | Dữ liệu gần nhất đã tới pipeline đến đâu | Đã xử lý dữ liệu nguồn đến 10:20Z |
| Retention cutoff | Mốc mà dữ liệu quá tuổi sẽ được lưu trữ/xóa theo chính sách | Raw trước ngày D−180 |
| Completeness | Bucket có đủ dữ liệu theo nguồn/chính sách hay không | Nhận 58/60 mẫu dự kiến |
| Traceability | Có thể giải thích/đối chiếu bằng chứng đến mức nào | Từ báo cáo → bucket → điểm đo hoặc archive |

**Bucket 1 giờ không nhất thiết chứa đúng 60 điểm đo**, dù cadence là mỗi phút. Thiết bị có thể mất mạng, gửi bù, gửi lặp hoặc đổi chu kỳ đo. Đừng suy ra sampleCount=60 chỉ từ tên bảng hourly.

### Minh họa lượng dữ liệu

Nếu có **1.000 cảm biến**, mỗi cảm biến gửi một mẫu mỗi phút:

\[
N_{\text{raw/ngày}}=1000\times 60\times 24
=1.440.000\;\text{mẫu}.
\]

Giữ 90 ngày raw tương đương khoảng **129,6 triệu mẫu** trước khi tính bản lặp, metadata, chỉ mục, sao lưu hoặc dữ liệu bất thường. Trong khi đó một rollup 1 giờ có tối đa **24.000 hàng mỗi ngày** nếu mỗi thiết bị đủ một hàng/giờ. Đây là phép tính về **số bản ghi**, không phải ước lượng byte đã được benchmark; kích thước thực tế phụ thuộc nén, kiểu dữ liệu, hệ quản trị, chỉ mục và lượng metadata.

Tỷ lệ giảm hàng là lý do thường giữ rollup lâu hơn raw. Tuy nhiên giảm số hàng chỉ đáng giá nếu không xóa **thông tin thiết yếu cho mục đích sử dụng**.

## 3. Grain của các cấp phải được định nghĩa tường minh

Đối với dữ liệu nhiệt độ, có thể viết:

| Bảng / lớp | Phát biểu grain | Khóa duy nhất ứng viên |
| --- | --- | --- |
| sensor_reading | Một mẫu đo từ một thiết bị, theo timestamp và sequence do nguồn phát | tenant, device, observedAt, sourceSequence |
| temperature_5m | Một thiết bị trong một bucket UTC 5 phút | tenant, device, bucketStart |
| temperature_1h | Một thiết bị trong một bucket UTC 1 giờ | tenant, device, bucketStart |
| temperature_daily | Một thiết bị trong một **ngày nghiệp vụ** xác định | tenant, device, businessDate, calendarPolicyVersion nếu cần |
| temperature_excursion | Một **lần vượt ngưỡng liên tục** được xác nhận theo chính sách | tenant, excursionId |
| evidence_manifest | Một gói bằng chứng có định danh độc lập | tenant, evidenceId |

Với từng bảng, phải giải thích:

1. **Một hàng là gì?** Mẫu thực, thống kê nhiều mẫu hay một sự cố được phát hiện?
2. **Khóa danh tính nào ổn định qua retry?** Nếu mỗi lần ingest tự tạo eventId mới, sẽ không khử trùng lặp đúng.
3. **Phạm vi tenant/device có rõ không?** Hai cảm biến khác nhau có thể cùng timestamp.
4. **Ngày bắt đầu từ đâu?** Bucket UTC 1 giờ khác ngày kinh doanh theo giờ địa phương.
5. **Chất lượng mẫu được xét như thế nào?** Có loại INVALID/SUSPECT khỏi trung bình không?
6. **Khi sửa lịch sử thì làm gì?** Ghi correction, cập nhật rollup hay phát hành phiên bản mới?

Grain không phải chỉ là thứ tự cột trong PRIMARY KEY. Nó là **lời cam kết về ý nghĩa hàng** để mọi báo cáo có thể kiểm tra.

## 4. Thiết kế đường dữ liệu nhiều mức

~~~mermaid
flowchart TB
    D["Cảm biến + gateway<br/>deviceId, sequence, observedAt"]
    I["Ingest<br/>xác thực, dedup, kiểm tra clock/quality"]
    R["Raw readings<br/>hot → cold archive"]
    F["Rollup 5 phút<br/>count, sum, min, max, quality"]
    H["Rollup 1 giờ<br/>count, sum, min, max, quality"]
    Y["Rollup ngày<br/>timezone/cutoff rõ ràng"]
    X["Phát hiện ngoại lệ<br/>excursion event + evidence"]
    A["Lineage / watermark / audit"]
    Q["API biểu đồ, BI, đối soát"]

    D --> I
    I --> R
    R --> F
    F --> H
    H --> Y
    R --> X
    X --> A
    R --> A
    F --> A
    H --> A
    Y --> A
    F --> Q
    H --> Q
    Y --> Q
    X --> Q
~~~

Sơ đồ mô tả các lớp chức năng, không bắt buộc mọi dữ liệu phải đi tuần tự raw → 5 phút → 1 giờ → ngày. Có thể tính rollup 1 giờ trực tiếp từ raw hoặc từ các bucket 5 phút **nếu những thống kê có thể hợp nhất đúng**. Muốn tính ngày theo múi giờ địa phương, không được tự động gộp 24 bucket UTC bắt đầu lúc 00:00Z nếu ngày địa phương có ranh giới khác.

**Nguồn có thẩm quyền vẫn là hệ thống ghi nhận mẫu/sự kiện**, không phải biểu đồ đã giảm độ phân giải. Việc một giờ có avg=5°C không chứng minh từng mẫu đều ở 5°C.

## 5. Giảm độ phân giải mà không làm sai phép đo

Giả sử trong một bucket có các giá trị nhiệt độ hợp lệ:

~~~text
04:00  3°C
04:01  4°C
04:02  10°C
04:03  3°C
~~~

Khi đó:

- sampleCount = 4.
- sumTemperature = 20.
- average = 5°C.
- min = 3°C, max = 10°C.

Nếu ngưỡng cho phép là tối đa 8°C, **trung bình 5°C hoàn toàn không phát hiện được một điểm đã vượt ngưỡng**. MIN/MAX giúp biết đã có cực trị, nhưng vẫn chưa trả lời điểm vượt kéo dài bao lâu, có liên tục hay không, hoặc nó xảy ra trước/sau một sự kiện cửa mở kho.

### Giữ thống kê đủ để hợp nhất nhiều bucket

Một hourly rollup nên giữ ít nhất những đại lượng cần cho KPI:

\[
\text{avg}=\frac{\text{sum}}{\text{validCount}}
\quad\text{khi validCount}>0.
\]

Để gộp nhiều bucket:

\[
\text{sum}_{all}=\sum_i \text{sum}_i,\quad
\text{validCount}_{all}=\sum_i \text{validCount}_i,\quad
\text{min}_{all}=\min_i \text{min}_i,\quad
\text{max}_{all}=\max_i \text{max}_i.
\]

**Không lấy trung bình của các trung bình** khi số mẫu khác nhau. Ví dụ bucket A có một mẫu 10°C, bucket B có chín mẫu 2°C:

~~~text
Sai:  (10 + 2) / 2 = 6°C
Đúng: (10 × 1 + 2 × 9) / (1 + 9) = 2,8°C
~~~

Sự khác biệt không phải sai số làm tròn; đó là **sai grain và sai trọng số**.

### Không phải thống kê nào cũng hợp nhất từ avg/min/max

| KPI cần tính | Cần giữ gì khi giảm độ phân giải? | Có suy lại từ avg/min/max/count không? |
| --- | --- | --- |
| Trung bình theo mẫu | sum và validCount | Có, nếu giữ sum/count đủ chính xác |
| Min/max của toàn khoảng | min/max các bucket | Có, nếu các bucket đầy đủ và cùng định nghĩa |
| Số mẫu vượt 8°C | aboveThresholdCount với policy version | Không |
| Số **phút liên tục** vượt ngưỡng | Chuỗi trạng thái/đoạn thời gian, quy tắc nội suy | Không |
| Percentile p95 | Raw hoặc histogram/sketch có thể hợp nhất theo kỹ thuật chọn | Không nói chung; p95 từng giờ không gộp ra p95 cả ngày |
| Trung bình theo **thời gian thực** | Tích phân giá trị theo thời gian và tổng duration hợp lệ | Không, nếu chỉ giữ trung bình theo số mẫu |
| Thời điểm chính xác đạt đỉnh | max cùng argmax timestamp hoặc raw | Chỉ max-value là không đủ |
| Thứ tự điểm bất thường | Raw hoặc chuỗi sự kiện đã lưu | Không |

Nếu sampling không đều, trung bình theo mẫu và trung bình theo thời gian không tương đương. Có thể cần:

\[
\overline{T}_{time}
=\frac{\sum_i T_i\,\Delta t_i}{\sum_i \Delta t_i},
\]

trong đó \(\Delta t_i\) được tính từ một **quy tắc nội suy/giữ giá trị** rõ ràng, có giới hạn khi thiết bị mất dữ liệu lâu. Không mặc định mỗi mẫu đại diện cho thời lượng bằng nhau khi cadence không ổn định.

### Lưu cả tín hiệu chất lượng

Ngoài sum/count/min/max, nên xem xét:

- observedCount: tổng số mẫu nhận được theo grain.
- validCount, suspectCount, invalidCount theo bộ tiêu chí chất lượng có version.
- expectedCount nếu có cadence đã biết và thời điểm hoạt động của thiết bị; không đoán từ độ dài bucket.
- coverageRatio = validCount / expectedCount, khi expectedCount thực sự có ý nghĩa.
- peakAt hoặc thresholdBreachCount nếu báo cáo cần.
- watermark/completeFlag và transformVersion để biết bucket còn có thể thay đổi không.

Khi validCount=0, average nên là **NULL**, không phải 0°C. "Không đo được" hoàn toàn khác "đã đo được nhiệt độ bằng 0".

## 6. Truy vết là yêu cầu cụ thể, không chỉ một cột ID

Người dùng nói "phải truy vết được" có thể đang yêu cầu những khả năng rất khác nhau:

| Cấp truy vết | Câu hỏi phải trả lời | Dữ liệu tối thiểu có thể cần |
| --- | --- | --- |
| KPI/giải thích kết quả | Số trung bình ngày được tính như thế nào? | Công thức, count/sum, khoảng thời gian, nguồn và transform version |
| Kiểm tra dữ liệu đầu vào | Bucket này gồm những mẫu nào? | Khóa nguồn, raw hoặc danh sách nguồn/batch có thể truy xuất |
| Chẩn đoán sự cố | Ngưỡng bị vượt lúc nào, kéo dài bao lâu? | Raw đủ chi tiết hoặc đoạn sự kiện vượt ngưỡng có chất lượng/bằng chứng |
| Điều tra/đối soát | Ai sửa dữ liệu, dùng ngưỡng nào, khi nào chốt báo cáo? | Audit, rule version, event/correction lineage, manifest |
| Bằng chứng kiểm chứng độc lập | Có thể tái xem và kiểm tra dữ liệu gốc cùng chuỗi xử lý? | Mẫu gốc được giữ, checksum/chữ ký nếu cần, phiên bản công cụ, quyền truy cập |

**Không thể hứa truy vết từng mẫu sau khi đã xóa mọi bản raw** và không giữ một bản lưu trữ phù hợp. Một hàng 1 ngày kèm min/max, checksum hay eventId chỉ chứng minh được một số điều, không cho phép tái dựng các điểm đo đã mất.

### Khóa liên kết và lineage

Một đồ thị truy vết hợp lý:

~~~mermaid
flowchart LR
    B["Báo cáo ngày D<br/>reportRunId + policy"]
    H["Rollup giờ<br/>tenant, device, bucket"]
    M["Raw manifest<br/>partition/object, checksum"]
    R["Raw samples<br/>source sequence, observedAt"]
    E["Excursion evidence<br/>incidentId, raw snapshot"]
    P["Thiết bị / cấu hình / calibration"]
    B --> H
    H --> M
    M --> R
    E --> R
    E --> P
    B --> P
~~~

Nếu raw còn trong hot hoặc cold archive, manifest có thể giúp định vị các file/phân vùng nguồn. Nếu raw đã hết hạn và bị xóa theo chính sách, manifest có thể chứng minh **đã dùng nguồn nào trong quá khứ**, nhưng không thể tự tái tạo các giá trị mẫu. Người thiết kế phải ghi **truy vết tới mức nào và trong bao lâu**.

### Hash, chữ ký và tính toàn vẹn

Checksum/hash giúp phát hiện nội dung một file raw được lấy về có khác nội dung đã ghi manifest hay không. Nhưng:

- Hash **không thay thế** nội dung mẫu gốc.
- Hash thông thường **không tự chứng minh** ai tạo dữ liệu và khi nào.
- Có thể cần chữ ký, kho bất biến, kiểm soát truy cập, log thao tác và đồng bộ thời gian nếu quy trình điều tra yêu cầu.
- Cần lưu thuật toán băm, phiên bản manifest và phương pháp canonicalization; không thể kiểm tra cùng một digest nếu thứ tự hoặc định dạng dữ liệu thay đổi tùy ý.

Một retention policy có yêu cầu bằng chứng mạnh phải được thiết kế **trước khi raw bị xóa**, không phải sau khi đã phát sinh tranh chấp.

## 7. Hai đồng hồ: thời gian xảy ra và thời gian nhận

Thiết bị đo một mẫu lúc 10:15 nhưng do mất kết nối, gateway chỉ gửi tới server lúc 12:00:

~~~text
observed_at  = 2026-10-15 10:15:00Z  (thời gian đo)
received_at  = 2026-10-15 12:00:00Z  (thời gian nền tảng nhận)
bucket_start = 2026-10-15 10:00:00Z  (bucket UTC 1 giờ)
~~~

Nếu xếp mẫu vào bucket theo received_at, dữ liệu sẽ sai ngữ nghĩa giờ đo. Nếu dựa hoàn toàn observed_at mà không kiểm tra thiết bị đồng hồ lệch, dữ liệu có thể bị phân loại sai. Thiết kế cần:

1. Xác định thời gian nào là **event time có thẩm quyền**, nguồn độ tin cậy và cách hiệu chỉnh đồng hồ.
2. Lưu thời gian nhận để đo latency và đối soát khi thiết bị kết nối trở lại.
3. Dùng một mốc timezone/cutoff nhất quán cho từng loại bucket.
4. Ghi cờ dữ liệu đáng ngờ nếu observed_at nằm quá xa tương lai/quá khứ so với chính sách.
5. Phân biệt sự kiện **đến muộn** với dữ liệu **sai timestamp**; chúng cần cách xử lý khác nhau.

### Một ngày không phải lúc nào cũng 24 giờ

Nếu một tổ chức có kho ở nhiều múi giờ, ngày kinh doanh có thể bắt đầu lúc 06:00 giờ địa phương; những khu vực có đổi giờ mùa hè còn có ngày địa phương dài 23 hoặc 25 giờ. Rollup 1 giờ UTC có 24 bucket trong một ngày UTC, nhưng không thể mặc định mọi **ngày địa phương** chứa đúng 24 bucket theo giờ địa phương.

Khuyến nghị lưu **bucket_start UTC** cho cấp phút/giờ, rồi tính **business_date** bằng timezone/cutoff của thiết bị/kho theo chính sách có hiệu lực. Nếu timezone hoặc giờ chốt thay đổi trong lịch sử, phải giữ phiên bản lịch tương ứng khi muốn tái lập báo cáo cũ.

## 8. Mô hình dữ liệu PostgreSQL: raw và rollup

Các ví dụ dưới đây dùng PostgreSQL để làm rõ grain, ràng buộc, partition và SQL tổng hợp. Một time-series database hay warehouse dạng cột có thể dùng TTL/compression/materialized view khác; **không coi SQL này là kiến trúc tối ưu bắt buộc cho mọi tải thực tế**.

### 8.1. Bảng raw phân vùng theo event time

~~~sql
CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE telemetry.sensor_reading (
    tenant_id UUID NOT NULL,
    device_id UUID NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    temperature_c NUMERIC(8, 3) NOT NULL,
    quality_code VARCHAR(12) NOT NULL
        CHECK (quality_code IN ('VALID', 'SUSPECT', 'INVALID')),
    source_batch_id UUID,
    PRIMARY KEY (tenant_id, device_id, observed_at, source_sequence)
) PARTITION BY RANGE (observed_at);

-- Phân vùng ví dụ: mọi observed_at trong tháng 11/2026 theo UTC.
CREATE TABLE telemetry.sensor_reading_2026_11
    PARTITION OF telemetry.sensor_reading
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE INDEX sensor_reading_device_time
    ON telemetry.sensor_reading (tenant_id, device_id, observed_at DESC);
~~~

**Vì sao partition theo observed_at?** Các truy vấn thường lọc theo khoảng thời gian đo; việc lưu trữ/xóa theo tuổi event time cũng có thể thao tác theo partition tháng/ngày. Nhưng có các ràng buộc thực tế:

- PostgreSQL yêu cầu **khóa duy nhất trên bảng partitioned phải chứa partition key**; PK trên có observed_at. Nó **không tự đảm bảo** (tenantId, deviceId, sourceSequence) duy nhất nếu cùng sequence bị gửi lại với timestamp khác. Nếu nguồn cam kết sequence là danh tính ổn định, có thể cần một ingest ledger/khóa trùng riêng hoặc cơ chế source dedup trước khi ghi.
- SourceSequence có thể reset khi thiết bị khởi động hoặc firmware đổi. Nếu vậy khóa cần thêm bootSessionId/sourceEpoch hoặc một eventId bất biến thực sự.
- Nếu đọc lại cùng mẫu ở cùng PK nhưng temperature khác, **ON CONFLICT DO NOTHING** có thể che mất sửa sai; cần chính sách conflict/correction.
- Dữ liệu đến muộn có thể nhắm vào phân vùng đã lưu trữ hoặc xóa; cần xử lý rõ, không tự tạo lại phân vùng hết hạn.
- Nếu nhiều tenant có retention khác nhau trong một partition thời gian, **DROP cả partition** có thể xóa nhầm dữ liệu chưa hết hạn hoặc đang được giữ bằng chứng.
- Timestamp hợp lệ không chứng minh đồng hồ thiết bị đúng; kiểm tra thời gian và chất lượng thuộc pipeline ingest.

Nếu hệ thống cần truy vết từng lần hiệu chỉnh, có thể lưu correction log hoặc phiên bản raw riêng thay vì ghi đè nhiệt độ đo và mất dấu nguồn gốc.

### 8.2. Bảng rollup theo giờ

~~~sql
CREATE TABLE telemetry.temperature_hourly (
    tenant_id UUID NOT NULL,
    device_id UUID NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    observed_count BIGINT NOT NULL CHECK (observed_count >= 0),
    valid_count BIGINT NOT NULL CHECK (valid_count >= 0),
    suspect_count BIGINT NOT NULL CHECK (suspect_count >= 0),
    invalid_count BIGINT NOT NULL CHECK (invalid_count >= 0),
    temperature_sum NUMERIC(24, 6) NOT NULL DEFAULT 0,
    temperature_min NUMERIC(8, 3),
    temperature_max NUMERIC(8, 3),
    source_watermark TIMESTAMPTZ,
    transform_version INTEGER NOT NULL CHECK (transform_version > 0),
    rollup_version BIGINT NOT NULL DEFAULT 1 CHECK (rollup_version > 0),
    is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, device_id, bucket_start),
    CHECK (observed_count = valid_count + suspect_count + invalid_count),
    CHECK (
        (valid_count = 0 AND temperature_min IS NULL
         AND temperature_max IS NULL)
        OR
        (valid_count > 0 AND temperature_min IS NOT NULL
         AND temperature_max IS NOT NULL
         AND temperature_min <= temperature_max)
    )
);

CREATE INDEX temperature_hourly_device_time
    ON telemetry.temperature_hourly
        (tenant_id, device_id, bucket_start DESC);
~~~

Các cột trên giữ **thống kê đủ để hợp nhất trung bình theo mẫu, min/max và tình trạng chất lượng**. Nếu tính SLA thời gian liên tục vượt ngưỡng, cần thêm đại lượng/đoạn thời gian chuyên biệt; không cố suy ra từ temperature_sum.

Không có trường average vật lý để tránh một nguồn dữ liệu dư thừa dễ lệch. Nếu muốn lưu average cho BI, có thể là biểu thức sinh/derived metric với công thức và độ chính xác rõ ràng.

### 8.3. Tính một khoảng bucket đầy đủ, không nạp lẫn lộn

PostgreSQL 14+ có hàm date_bin để gom bucket theo mốc cố định. Ví dụ tính lại **toàn bộ một giờ UTC**:

~~~sql
INSERT INTO telemetry.temperature_hourly AS target (
    tenant_id, device_id, bucket_start,
    observed_count, valid_count, suspect_count, invalid_count,
    temperature_sum, temperature_min, temperature_max,
    source_watermark, transform_version, is_finalized
)
SELECT
    r.tenant_id,
    r.device_id,
    date_bin(
        INTERVAL '1 hour',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS bucket_start,
    COUNT(*) AS observed_count,
    COUNT(*) FILTER (WHERE quality_code = 'VALID') AS valid_count,
    COUNT(*) FILTER (WHERE quality_code = 'SUSPECT') AS suspect_count,
    COUNT(*) FILTER (WHERE quality_code = 'INVALID') AS invalid_count,
    COALESCE(
        SUM(temperature_c) FILTER (WHERE quality_code = 'VALID'),
        0
    ) AS temperature_sum,
    MIN(temperature_c) FILTER (WHERE quality_code = 'VALID'),
    MAX(temperature_c) FILTER (WHERE quality_code = 'VALID'),
    :source_watermark,
    :transform_version,
    FALSE
FROM telemetry.sensor_reading AS r
WHERE r.tenant_id = :tenant_id
  AND r.device_id = :device_id
  AND r.observed_at >= :bucket_start
  AND r.observed_at <  :bucket_end
GROUP BY r.tenant_id, r.device_id,
    date_bin(
        INTERVAL '1 hour',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    )
ON CONFLICT (tenant_id, device_id, bucket_start)
DO UPDATE SET
    observed_count = EXCLUDED.observed_count,
    valid_count = EXCLUDED.valid_count,
    suspect_count = EXCLUDED.suspect_count,
    invalid_count = EXCLUDED.invalid_count,
    temperature_sum = EXCLUDED.temperature_sum,
    temperature_min = EXCLUDED.temperature_min,
    temperature_max = EXCLUDED.temperature_max,
    source_watermark = EXCLUDED.source_watermark,
    transform_version = EXCLUDED.transform_version,
    rollup_version = target.rollup_version + 1,
    is_finalized = FALSE,
    computed_at = CURRENT_TIMESTAMP;
~~~

**Điều kiện để câu lệnh được dùng an toàn:**

1. :bucket_start và :bucket_end phải được truyền cho **đúng một giờ** đã căn theo date_bin; không chạy truy vấn chỉ đọc 15 phút rồi ghi đè bucket 1 giờ hoàn chỉnh bằng một phần dữ liệu.
2. Bảng raw phải đủ dữ liệu theo **watermark/độ trễ đã thỏa thuận**, hoặc đánh dấu đây là bucket tạm chưa hoàn chỉnh.
3. Chỉ dùng dữ liệu VALID cho min/max/sum theo chính sách ví dụ; nếu tiêu chí chất lượng thay đổi, phải tăng transformVersion và quyết định có tính lại lịch sử hay không.
4. Khi raw không có **bất kỳ mẫu nào**, SELECT không sinh hàng. Nếu cần bucket rỗng với validCount=0, tạo lịch bucket/device theo lịch hoạt động có thẩm quyền rồi LEFT JOIN dữ liệu; không tự giả định "không có hàng" bằng nhiệt độ 0.
5. Nếu một bản rollup đã được chốt, pipeline phải kiểm tra **chính sách reopen/restate** trước khi ghi đè; đoạn SQL minh họa nhánh cho phép tính lại, chưa bao gồm quyền phê duyệt sửa kỳ đã chốt.
6. Một batch nạp đồng thời nhiều rollup trên cùng khóa cần cơ chế version/cutoff và transaction thích hợp để bản dữ liệu cũ không ghi đè bản mới.

### 8.4. Tính trung bình đúng từ các rollup giờ

~~~sql
SELECT
    tenant_id,
    device_id,
    SUM(temperature_sum)
        / NULLIF(SUM(valid_count), 0) AS sample_weighted_avg_c,
    MIN(temperature_min) AS min_c,
    MAX(temperature_max) AS max_c,
    SUM(valid_count) AS valid_samples,
    SUM(observed_count) AS all_received_samples
FROM telemetry.temperature_hourly
WHERE tenant_id = :tenant_id
  AND device_id = :device_id
  AND bucket_start >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND bucket_start <  TIMESTAMPTZ '2026-10-02 00:00:00+00'
  AND is_finalized = TRUE
GROUP BY tenant_id, device_id;
~~~

Nếu một số giờ chưa finalized, truy vấn này **chỉ tổng hợp những giờ đã chốt** và không chứng minh ngày đã đủ 24 giờ. Để báo cáo một ngày hoàn chỉnh, cần kiểm tra danh sách các bucket dự kiến, trạng thái hoàn thành và watermark — không chỉ WHERE is_finalized=TRUE rồi hiển thị kết quả như ngày đã đủ.

Nếu muốn nhóm ngày nghiệp vụ theo giờ địa phương, cần tái phân loại khoảng timestamp theo timezone/cutoff, không đổi nhãn ngày sau khi đã tổng hợp sai phạm vi.

## 9. Không có một TTL chung cho raw, rollup và bằng chứng

Một chính sách có thể được mô tả bằng các trường:

~~~text
retention_class       = RAW_NORMAL / ROLLUP_5M / ROLLUP_1H /
                        DAILY / INCIDENT_EVIDENCE / AUDIT
scope                 = tenant, device group, data category
time_anchor           = observed_at / bucket_end / incident_closed_at
hot_until             = time_anchor + hot_duration
archive_until         = time_anchor + total_retention
delete_after          = archive_until, trừ khi có hold hợp lệ
traceability_level    = aggregate-only / raw-replay / evidence-package
late_arrival_policy   = accept / restate / quarantine / reject
approver_and_version  = ai phê duyệt chính sách, phiên bản nào
~~~

Chỉ nên xóa khi đã xác định được:

- **Dữ liệu nào thuộc chính sách nào?** Một sensor chứa thông số vận hành có thể khác sự kiện vị trí nhân viên hay bằng chứng sự cố.
- **Thời hạn tính từ mốc nào?** Raw thường tính theo thời điểm đo; hồ sơ vụ việc có thể tính từ ngày vụ việc kết thúc hoặc ngày chốt, theo hợp đồng.
- **Đã tạo và đối soát rollup cần giữ chưa?** Không xóa raw trước khi các kết quả phụ thuộc được xác nhận.
- **Bản lưu trữ lạnh có thực sự truy xuất được không?** Chỉ chuyển file sang object storage không chứng minh hệ thống có index, manifest, quyền và quy trình restore.
- **Có bản ghi nào đang bị giữ để điều tra không?** Một hold cần có đối tượng, lý do, người phê duyệt, phạm vi và thời hạn kiểm tra lại.
- **Có chính sách xóa dữ liệu cá nhân không?** Không giữ mọi thứ vô hạn chỉ vì một báo cáo có thể hữu ích về sau.

### Bảo đảm không làm mất bằng chứng khi rollup

Giả sử ngưỡng quy định là nhiệt độ vượt 8°C **liên tục ít nhất 10 phút**. Một hourly max = 10°C không chứng minh điều kiện đủ 10 phút; hourly average = 5°C cũng không loại trừ vi phạm. Cần:

1. Một bộ phát hiện ngoại lệ trên **chuỗi dữ liệu đủ độ phân giải**.
2. Định nghĩa rõ liên tục: chấp nhận khoảng trống tối đa bao nhiêu giây, dùng nội suy nào, chất lượng mẫu SUSPECT có tính không?
3. Khi xác nhận vi phạm, ghi một **excursion event** với start/end, thresholdRuleVersion, thiết bị, kỳ hiệu lực và các giá trị minh họa.
4. Nếu cần kiểm tra độc lập, giữ **đoạn raw liên quan** (ví dụ trước/sau vụ việc một khoảng thời gian được chọn) cùng metadata, checksum/manifest; không chỉ ghi min/max.
5. Đảm bảo giữ bằng chứng trước khi tiến trình retention xóa raw gốc. Khi một vụ việc vẫn mở, chính sách có thể giữ thêm dữ liệu cần thiết theo quy trình phê duyệt.

Nếu nguồn bị mất dữ liệu trong một đoạn 20 phút, **không thể kết luận đã không có vi phạm** chỉ vì các mẫu còn lại dưới ngưỡng. Chính sách phải biểu diễn trạng thái thiếu dữ liệu/không thể xác nhận.

## 10. Thiết kế hồ sơ truy vết cho sự cố

Một cấu trúc logic cho bằng chứng:

| Thông tin | Ví dụ | Tại sao cần? |
| --- | --- | --- |
| incidentId | EX-901 | Nhận diện vụ việc độc lập với các điểm đo |
| tenantId / deviceId | T, D | Xác định nguồn và phạm vi quyền |
| eventStart / eventEnd | 10:11–10:28Z | Phạm vi sự kiện |
| detectedAt / confirmedAt | 10:12 / 10:45Z | Phân biệt phát hiện và xác nhận |
| policyId / policyVersion | TEMP_HIGH / v4 | Biết ngưỡng và cách tính có hiệu lực |
| sourceClockQuality | Synced / Unsynced / Suspect | Đánh giá độ tin cậy timestamp |
| evidenceObjectRef | URI nội bộ theo quyền | Truy xuất đoạn raw được giữ |
| evidenceChecksum | Digest của gói raw đã chuẩn hóa | Phát hiện sửa đổi nội dung |
| manifestVersion / schemaVersion | M1 / S3 | Diễn giải đúng file/gói nguồn |
| transformVersion | anomaly-detector v7 | Biết thuật toán được áp dụng |
| reviewer / decision | Người duyệt và quyết định | Truy vết nghiệp vụ |
| retentionClass / holdId | CRITICAL_INCIDENT / H-22 | Bảo vệ dữ liệu theo chính sách |

**Một gói bằng chứng là dữ liệu có vòng đời riêng**, không phải chỉ là copy tất cả raw vô hạn. Có thể có quyền truy cập khác với biểu đồ vận hành, quy trình xuất dữ liệu được ghi log và chính sách hủy/ẩn danh sau thời hạn.

### Chuỗi truy vết khi một báo cáo bị chất vấn

Ví dụ báo cáo công bố "tháng 10 có 12 lần vượt ngưỡng". Một chuỗi truy vết đủ rõ:

~~~text
report_run_id R-2026-10
  → metric "confirmed_excursions" version 4
  → incident IDs EX-901 ... EX-912
  → mỗi incident có threshold rule/version và decision
  → evidence manifest, source device, time window
  → raw archive (nếu vẫn trong thời hạn được giữ)
  → checksum, quyền tải, audit xuất bằng chứng
~~~

Khi raw đã được xóa hợp lệ, chỉ có thể giải thích theo mức bằng chứng còn giữ; không được nói có thể **replay từng điểm đo** nếu đường truy xuất tới raw không còn.

## 11. Data retention gắn với partition và vòng đời lưu trữ

Với hệ thống quan hệ, phân vùng theo thời gian có thể giúp quản lý những lô dữ liệu hết hạn. Nhưng việc xóa cả partition phải được ràng buộc bởi chính sách, không chỉ một cron job:

~~~mermaid
flowchart LR
    P["Partition raw sắp hết hạn"]
    W{"Rollup đầy đủ và đối soát?"}
    H{"Có hold hoặc retention đặc biệt?"}
    A["Archive raw + manifest<br/>xác minh có thể restore"]
    D["Detach / drop hoặc xóa có kiểm soát"]
    Q["Giữ lại hoặc xử lý ngoại lệ"]
    L["Audit: phạm vi, policy version, thời điểm"]
    P --> W
    W -->|"Chưa"| Q
    W -->|"Đã"| H
    H -->|"Có"| Q
    H -->|"Không"| A
    A -->|"PASS"| D
    D --> L
~~~

Trong ví dụ hot 30 ngày + archive thêm 150 ngày:

1. Ngày D, bucket raw có event time trước D−30 được đưa ra khỏi tầng hot theo chính sách.
2. Rollup đã được tạo và kiểm tra trước khi chuyển/xóa nguồn hot.
3. Raw archive được lưu đến tổng hạn 180 ngày, có manifest và khả năng truy xuất theo tenant/device/time.
4. Sau khi hết hạn, chỉ xóa nếu không có legal/business hold hợp lệ và không còn chính sách khác cần giữ.
5. Những đoạn raw được trích vào hồ sơ sự cố có thể có **retention riêng**; không mặc nhiên giữ cả partition vì chỉ một đoạn đang được điều tra.

**Partition theo thời gian không thể tự giải quyết retention khác nhau theo tenant.** Nếu nhiều tenant nằm chung một partition nhưng một tenant phải giữ 180 ngày và tenant khác 365 ngày, không thể DROP partition khi vẫn có dữ liệu phải giữ. Cần tổ chức vật lý phù hợp (ví dụ lưu trữ tách theo lớp chính sách), xóa chọn lọc hoặc một cơ chế quản lý archive riêng.

**Minh họa thao tác, không chạy máy móc:**

~~~sql
-- Chỉ thực hiện sau khi có approval, xác nhận cutoff,
-- đối soát rollup, archive/hold và backup policy phù hợp.
-- Đây là partition thời gian của ví dụ, KHÔNG phải lệnh TTL tự động.
--
-- ALTER TABLE telemetry.sensor_reading
--   DETACH PARTITION telemetry.sensor_reading_2026_11;
--
-- Sau khi dữ liệu đã được lưu/xóa theo chính sách, mới xử lý
-- bảng đã detach; tuyệt đối không DROP theo tháng hiện tại
-- khi còn giữ bằng chứng/late-arriving data.
~~~

Mặc dù thao tác partition có thể nhanh, **thời gian cần để xác minh an toàn** và bảo vệ dữ liệu chưa hết hạn mới là phần quan trọng của quy trình retention.

## 12. Dữ liệu đến muộn và sửa lịch sử sau khi chốt bucket

Đây là một trong những khó khăn chính của retention nhiều cấp. Tình huống:

- 10:00–11:00: thiết bị gửi các mẫu bình thường.
- 11:10: pipeline chốt bucket 10:00 và tạo rollup giờ.
- 12:00: gateway gửi thêm mẫu 10:15 bị giữ trong bộ nhớ do mất mạng.
- 40 ngày sau: raw hot của ngày đó đã bị chuyển archive, nhưng rollup còn được lưu.

Nếu không có quy tắc, số liệu giờ 10:00 và mọi rollup ngày/tháng phụ thuộc có thể **lệch**.

### Watermark và thời hạn nhận muộn

**Watermark** là cam kết có điều kiện về tiến độ xử lý event time, không phải lời hứa rằng trên thế giới không còn dữ liệu cũ. Có thể định nghĩa:

~~~text
bucket UTC 10:00-11:00
allowed lateness = 15 phút (ví dụ minh họa)
provisional until = 11:15 nếu checkpoint nguồn đã đủ
finalized when = watermark nguồn vượt cuối bucket + policy checks PASS
~~~

Khi một mẫu đến sau thời điểm finalized:

| Chính sách | Hành vi | Hậu quả cần kiểm soát |
| --- | --- | --- |
| Reopen/restate | Tính lại bucket giờ và các rollup ngày/tháng phụ thuộc | Báo cáo cũ có thể đổi; phải lưu version/audit |
| Ghi adjustment | Thêm thông tin điều chỉnh tách biệt, tính KPI theo hợp đồng mới | Tránh vừa sửa số gốc vừa cộng adjustment lần nữa |
| Quarantine/manual review | Đưa mẫu muộn vào hàng chờ xử lý và điều tra | Có SLA và trạng thái rõ |
| Bỏ qua theo chính sách | Không thay bucket đã chốt, ghi số mẫu bị bỏ | Chỉ chấp nhận khi nghiệp vụ/kiểm toán đã chấp thuận |

Đối với dữ liệu an toàn nhiệt độ, không nên mặc định chọn **bỏ qua**. Một mẫu trễ có thể chứa điểm vượt ngưỡng quan trọng. Quyết định phụ thuộc rủi ro và nghĩa vụ của ứng dụng.

### Khi raw đã bị xóa nhưng cần sửa rollup

Nếu chỉ có average/min/max/count, không thể tùy ý tính lại **mọi thống kê** theo một tập mẫu hiệu chỉnh:

- Muốn cộng thêm một mẫu hợp lệ mới, sum và count có thể cập nhật, min/max có thể tính thêm.
- Muốn **xóa/hiệu chỉnh một mẫu từng là giá trị min/max**, không thể suy min/max mới nếu không còn raw hoặc cấu trúc thống kê bổ sung.
- Muốn tính lại percentiles, duration vượt ngưỡng hoặc phát hiện liên tục, cần raw hoặc dữ liệu chuyên biệt đủ thông tin.

Vì vậy phải đặt **thời gian raw còn sẵn để sửa** phù hợp với **cửa sổ correction và SLA chốt báo cáo**, hoặc có archive/evidence để rebuild khi cần. Không hứa có thể tái tính hoàn toàn sau khi đã xóa nguồn chi tiết.

## 13. Chi phí, dung lượng và lựa chọn cấp phục vụ truy vấn

Không thể đánh đổi retention nếu không ước lượng khối lượng và truy vấn. Dùng các biến:

- \(N\): số thiết bị;
- \(f\): số mẫu dự kiến của một thiết bị mỗi ngày;
- \(s_{raw}\): byte lưu trung bình mỗi mẫu, **bao gồm ước lượng index/metadata/nén theo engine**;
- \(R_{raw}\): số ngày giữ raw;
- \(b\): số bucket tạo mỗi ngày cho mỗi thiết bị;
- \(s_{bucket}\): byte mỗi rollup;
- \(R_{bucket}\): số ngày giữ rollup.

Ước lượng sơ bộ:

\[
\text{RawBytes}\approx N \times f \times R_{raw}\times s_{raw},
\]

\[
\text{RollupBytes}\approx N \times b \times R_{bucket}
\times s_{bucket}.
\]

Nếu có bản sao dự phòng, index, storage lạnh, data transfer và backup, chi phí sẽ cao hơn những con số dữ liệu chính. Cần đo **compression ratio, cardinality, partition size, throughput, restore time, p95 query latency và đơn giá lưu trữ** trên hệ thống dự kiến.

### Ma trận chọn cấp độ truy vấn

| Yêu cầu | Cấp độ ứng viên | Cảnh báo |
| --- | --- | --- |
| Biểu đồ 30 phút vừa qua | Raw / 1 phút | Trả được dao động ngắn, nhưng tải truy vấn nhiều mẫu |
| Nhiệt độ trung bình 24 giờ | Rollup 1 giờ hoặc raw | Cần sum/count có trọng số và bucket hoàn chỉnh |
| Nhiệt độ cao nhất tháng | Rollup 1 giờ có max | Không biết thời điểm chính xác của max nếu không lưu argmax |
| Xu hướng theo ngày trong 3 năm | Rollup ngày | Có thể không phục vụ điều tra dao động trong vài phút |
| Xác định 12 phút liên tiếp vượt ngưỡng | Raw hoặc event vượt ngưỡng có duration theo policy | Avg/min/max theo ngày không đủ |
| Đối soát report khi bị khiếu nại | Raw archive + lineage hoặc evidence package | Không thể replay nếu nguồn đã bị xóa |
| Dashboard cập nhật mỗi 5 giây | Stream/projection gần thời gian thực | Độ tươi khác hoàn toàn với thời hạn giữ |

**Cache là tầng phục vụ, không phải retention gốc.** Một biểu đồ có cache 15 phút có thể dựa trên raw giữ 30 ngày; xóa cache không xóa sự thật gốc, và giữ cache không thay thế bằng chứng raw khi cần.

## 14. Phân biệt dữ liệu thường, ngoại lệ và dữ liệu cá nhân

Không nên lưu mọi thứ theo thời hạn dài nhất của nhóm rủi ro cao:

- **Telemetry thường:** có thể xuống cấp độ phân giải thấp dần và xóa raw đúng hạn.
- **Sự kiện cảnh báo/ngoại lệ:** có thể cần lưu một record có định danh, trạng thái điều tra, rule version và nguồn liên quan lâu hơn trung bình giờ.
- **Bằng chứng vụ việc được xác nhận:** có thể cần gói raw/metadata đầy đủ trong phạm vi hẹp, theo chính sách.
- **Thông tin định vị/cá nhân:** cần mục đích rõ, quyền truy cập hẹp, thời hạn tối thiểu theo chính sách và yêu cầu áp dụng.
- **Log truy cập và audit:** có thời hạn riêng; không mặc định log chứa dữ liệu nhạy cảm phải sống vô hạn.

### Retention hold và quyền xóa

Một hold không nên là cờ boolean không ai quản lý. Hồ sơ hold có thể có:

| Trường | Mục đích |
| --- | --- |
| holdId, scope | Chỉ ra chính xác tenant/device/time/object liên quan |
| reasonCode | Vì sao cần giữ |
| approverId, createdAt | Ai phê duyệt và khi nào |
| reviewBy / expiresAt | Khi nào cần xem lại hoặc kết thúc |
| affectedObjects / manifest | Bản raw/rollup/bằng chứng nào thuộc phạm vi |
| releaseAt, releasedBy | Truy vết quyết định gỡ hold |

Một yêu cầu xóa dữ liệu cá nhân có thể xung đột với nghĩa vụ lưu trữ hợp lệ. Không tự đặt ra luật xử lý chung. Hệ thống cần có chính sách được phê duyệt, khả năng giảm dữ liệu, tách thông tin nhận diện, hạn chế truy cập và quy trình đánh giá khi các nghĩa vụ cạnh tranh.

Nếu có dữ liệu thô trong archive, backup hoặc đối tác, xóa ở bảng hot **không chứng minh dữ liệu đã biến mất khỏi tất cả bản sao**. Phải nêu phạm vi xóa, lịch backup expiry và khả năng thực hiện xóa theo nghĩa vụ áp dụng.

## 15. Khi mô hình dữ liệu vật lý thay đổi: quan hệ, document, chuỗi thời gian và phân tích

| Cách lưu | Cách đáp ứng retention theo cấp | Cạm bẫy |
| --- | --- | --- |
| PostgreSQL quan hệ/partition | Raw partition theo event time, rollup bảng riêng, archive và xóa theo policy | Partition chia sẻ nhiều tenant/hold; UPDATE late data và index nóng |
| Time-series engine | Policy retention/compression, continuous aggregates hoặc materialized views theo chức năng sản phẩm | Không kiểm tra dependency trước khi TTL; tưởng auto-rollup luôn hỗ trợ correction |
| Document store | Raw documents có TTL index/cơ chế expiration, rollup collection theo bucket | TTL có thể không xóa đúng thời điểm tuyệt đối, không tự đảm bảo aggregate kịp tạo |
| Lưu trữ object/data lake | Raw files định danh qua manifest, chia partition, lifecycle rule, table format snapshot | Dữ liệu còn trong file/backup hoặc manifest mất liên kết; phải quản lý compaction/version |
| Kho phân tích dạng cột | Rollup nhiều cấp, phân vùng, clustering và materialized KPI | Dễ quét rộng, truy vấn sai grain, không phải nơi bảo vệ lệnh vận hành |
| Đồ thị | Nối sự cố–thiết bị–rule–bằng chứng–người duyệt để điều tra quan hệ | Cạnh đồ thị không thay raw, checksum hoặc chính sách lưu thực tế |

Thay đổi công nghệ không làm mất các yêu cầu cốt lõi: **grain, event time, policy version, idempotency, completeness, traceability và quyền sở hữu nguồn dữ liệu**. Một hệ thống lưu trữ có nút bật "TTL 90 ngày" vẫn cần chứng minh dữ liệu nào sẽ bị xóa và có bằng chứng nào phải được giữ lại.

### Chọn giữa tính lại và lưu bản chốt

Đối với KPI chính thức, có hai chiến lược:

1. **Recomputable:** giữ đủ raw/metadata để tính lại bất kỳ bucket nào trong phạm vi đã công bố.
2. **Versioned/published result:** lưu giá trị đã chốt, transformVersion, input lineage và correction history, chấp nhận rằng raw cũ sau retention sẽ không còn để replay đầy đủ.

Có thể kết hợp hai chiến lược theo từng kỳ hoặc loại sự kiện. Điều quan trọng là **không hứa tái lập từ đầu nếu chính sách xóa đã loại bỏ dữ liệu cần thiết**.

## 16. Kiểm thử retention và truy vết như một chức năng hệ thống

Không chỉ kiểm tra rằng dữ liệu biến mất sau TTL. Cần thử cả tình huống nó **không được biến mất** và các báo cáo tiếp tục đúng:

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Raw hết 30 ngày, rollup vừa tạo nhưng chưa đối soát | Chưa xóa/chuyển dữ liệu theo quy trình chưa đạt điều kiện |
| Raw hết hạn hot và đã archive | Manifest tìm được file; checksum khớp; có thể restore theo quyền |
| Raw hết 180 ngày, không có hold | Quy trình xóa có kiểm soát, ghi audit và phạm vi bản sao |
| Một đoạn raw liên quan incident đang mở | Đoạn bằng chứng được giữ theo policy, không bị xóa nhầm |
| Cùng sample gửi lại hai lần | Không đếm hai lần; conflict payload được phát hiện |
| Mẫu 10:15 tới server lúc 12:00 | Bucket event time 10:00 được xử lý theo late data policy |
| Bucket đã chốt rồi có correction | Restatement/adjustment được version và downstream cập nhật |
| Một bucket có 0 mẫu hợp lệ | Average NULL, không báo 0°C |
| Hai bucket có số mẫu khác nhau | Average gộp bằng sum/count, không AVG của hai average |
| Thiếu 5 phút trong một giờ | Completeness flag/coverage thể hiện khoảng trống |
| Một điểm 10°C trong 59 điểm 3°C | Max vẫn phản ánh 10°C dù avg thấp |
| Đổi cấu hình ngưỡng từ 8°C xuống 7°C | Lịch sử kết quả nêu đúng policyVersion; quyết định có backfill |
| Sự kiện source bị đổi sequence hoặc đồng hồ lệch | Gắn quality/epoch và đối soát, không nhập nhầm hay mất dedup |
| Tenant có retention dài hơn cùng partition | Không DROP cả partition trước hạn |
| Yêu cầu đối chiếu một report 2 năm tuổi | Trả rõ mức bằng chứng còn lại, có thể hoặc không thể replay raw |

### Chỉ số vận hành cần theo dõi

- Ingestion lag theo **event time** và theo nguồn.
- Số mẫu hợp lệ/không hợp lệ, tỷ lệ missing theo cadence đã định nghĩa.
- Số bucket provisional/finalized, bucket thiếu dữ liệu, số lần restatement.
- Số event duplicate và conflict payload.
- Rollup-vs-raw reconciliation difference theo thiết bị/ngày.
- Archive restore success, manifest/hash verification failure.
- Số hold đang hiệu lực, hold quá hạn xem xét lại.
- Dung lượng/chi phí theo cấp raw hot, raw cold, rollup 5 phút, giờ, ngày và bằng chứng.
- Số yêu cầu điều tra không thể đáp ứng do thiếu dữ liệu và nguyên nhân.

Các chỉ số này cho biết retention có đáp ứng **mục tiêu sử dụng** hay chỉ giảm dung lượng bằng mọi giá.

## 17. Bài tập thực hành: dữ liệu công tơ điện thông minh

**Bối cảnh:** Một công ty quản lý tòa nhà có 2.000 công tơ điện. Mỗi công tơ gửi số điện năng tích lũy (kWh) mỗi 15 phút; đôi khi reset bộ đếm sau thay thiết bị. Nền tảng muốn:

- Hiển thị công suất/điện năng gần đây theo căn hộ.
- Báo cáo điện năng tiêu thụ theo ngày và tháng trong 5 năm.
- Kiểm tra khi khách khiếu nại hóa đơn từ 18 tháng trước.
- Phát hiện đồng hồ mất tín hiệu hoặc chỉ số giảm bất thường.
- Giới hạn việc lưu dữ liệu liên quan từng cư dân theo chính sách quyền riêng tư.

### Câu hỏi

1. Viết **grain** cho bảng raw, rollup giờ, rollup ngày và hồ sơ khiếu nại. Cần những khóa nào để tránh ghi trùng khi gateway gửi lại?
2. Đề xuất **bảng retention** theo cấp raw hot/cold, 1 giờ, 1 ngày và evidence. Những con số nào chỉ là giả định và cần được người có thẩm quyền chốt?
3. Công tơ gửi **cumulative kWh** chứ không phải điện năng từng 15 phút. Có được cộng trực tiếp mọi chỉ số kWh trong ngày để ra điện năng tiêu thụ không? Hãy nêu cách tính delta và xử lý reset.
4. Nếu chỉ giữ trung bình kWh của mỗi giờ, có thể kiểm tra hóa đơn 18 tháng trước không? Cần lưu chỉ số đầu/cuối, delta hợp lệ, correction, chính sách giá và bằng chứng gì?
5. Một điểm đo của 17:45 đến sau khi rollup 17:00 đã finalized; hệ thống phải xử lý thế nào để rollup ngày và hóa đơn không lệch?
6. Nếu khách tranh chấp hóa đơn ở tháng đã hết hạn raw nhưng policy yêu cầu khả năng kiểm tra lại, nên làm gì từ **trước khi TTL chạy**?
7. Thiết kế hai test cho **duplicate sequence** và **reset bộ đếm**, một test cho **late data** và một test cho **hold** giữ bằng chứng.

### Hướng giải tham khảo

**Grain raw:** một mẫu công tơ (tenantId, meterId, sourceEpoch, sequence, observedAt), ghi cumulativeKwh, receivedAt và quality. Nếu thiết bị reset sequence, sourceEpoch/bootSessionId cần phân biệt các chuỗi phát; chỉ observedAt một mình có thể không đủ nhận diện.

**Không SUM cumulative kWh:** giá trị 100, 101, 103 là các **chỉ số tồn tích lũy**. Tiêu thụ trên khoảng đó là 103−100=3 kWh, không phải 304 kWh. Một reset từ 103 xuống 0 cần có dấu sự kiện reset/thay đồng hồ và quy tắc tạo delta hợp lệ, không ghi −103 kWh là mức tiêu thụ âm mặc định.

**Rollup giờ/ngày:** có thể lưu meterStartKwh, meterEndKwh, validConsumptionKwh, coverage, resetCount, sourceEventRange, policyVersion và thời điểm chốt. Một ngày có thể gồm nhiều segment nếu có reset. Tổng tiêu thụ tính từ **các delta đã xác thực**, không lấy AVG của các chỉ số tích lũy.

**Khiếu nại hóa đơn:** cần truy vết công tơ, chỉ số được dùng, kỳ chốt, giá/biểu giá đã áp dụng, thay đồng hồ, correction và có thể là raw/đoạn bằng chứng nếu hợp đồng đòi khả năng tính lại. Lưu mỗi số tiền cuối cùng mà không giữ quy tắc và nguồn sẽ khó đối chiếu.

**Late data:** không bỏ mặc phép đo về kỳ cũ; cần quy trình reopen/restate hoặc adjustment đúng chính sách thanh toán, version của hóa đơn, đối soát với khách hàng và log phê duyệt. **Hold:** phạm vi giữ dữ liệu phải được xác định và áp dụng trước khi xóa, rồi gỡ khi quy trình kết thúc hợp lệ.

## 18. Checklist ra quyết định và kết luận

- Mỗi mức chi tiết có **grain, khóa, cadence, bucket/timezone** rõ ràng chưa?
- Chính sách retention có ghi **thời hạn tổng, hot/cold, time anchor, tenant scope và phê duyệt** không?
- Đã xác định chính xác những KPI nào có thể tái tính từ **sum/count/min/max**, KPI nào cần raw hoặc dữ liệu chuyên biệt chưa?
- Không lấy average của các average thiếu trọng số; không mặc định missing = 0; không lẫn sample mean với time-weighted mean chứ?
- Rollup có count chất lượng, completeness, source watermark và transformVersion để biết số liệu đáng tin đến đâu không?
- Khi xóa raw, đã đối soát rollup, tạo manifest/archive/bằng chứng và kiểm tra hold chưa?
- Mức truy vết cam kết có nói rõ **đến mẫu gốc**, **đến thống kê**, hay **đến gói bằng chứng vụ việc** không?
- Nếu raw đã bị xóa, có tránh tuyên bố vẫn có thể replay hoàn toàn không?
- Event time, ingest time, business day và retention cutoff có được tách biệt, nhất quán không?
- Late event, correction, clock drift, duplicate, partition hết hạn và phiên bản báo cáo đã có quy trình xử lý chưa?
- Data privacy, backup expiry, quyền truy cập và thời hạn audit đã được xét riêng thay vì giữ mọi dữ liệu theo thời hạn dài nhất chưa?
- Có kiểm thử thực tế được archive restore, xử lý một incident đang hold, đối soát rollup và xóa an toàn chưa?

**Kết luận:** Thời gian lưu của dữ liệu chuỗi thời gian phải được xác định **theo độ phân giải và theo nghĩa vụ sử dụng**, không phải bằng một TTL áp cho mọi bảng. Điểm đo gốc cần cho chẩn đoán và khả năng tái xử lý; rollup theo phút/giờ/ngày giúp phân tích dài hạn với chi phí thấp hơn; hồ sơ sự cố và lineage duy trì khả năng giải thích hoặc chứng minh kết quả theo mức đã cam kết. Thiết kế vững chắc là thiết kế nói rõ **cái gì được giữ, đến khi nào, dựa trên mốc thời gian nào, có thể tái lập đến mức nào, và dữ liệu nào sẽ mất không thể khôi phục**. Khi các câu hỏi đó được trả lời cùng grain, thống kê, transaction, chính sách truy vết và quyền truy cập, mô hình dữ liệu sẽ dễ kiểm chứng và tiến hóa mà không đánh đổi âm thầm tính đúng của nghiệp vụ.
