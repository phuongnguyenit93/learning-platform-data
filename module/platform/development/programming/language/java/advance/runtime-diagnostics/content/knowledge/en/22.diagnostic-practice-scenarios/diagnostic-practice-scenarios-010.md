# 22.10. Viết báo cáo triệu chứng, giả thuyết, bằng chứng, thay đổi và kết quả kiểm chứng

## Mục tiêu học tập

Một ca phân tích JVM chỉ thực sự có giá trị vận hành khi người khác đọc được **điều gì đã xảy ra**, **vì sao nhóm nghi một cơ chế cụ thể**, **bằng chứng nào ủng hộ hoặc bác bỏ**, **đã thay đổi gì** và **đã kiểm chứng kết quả ra sao**. Lệnh `jcmd`, biểu đồ JFR hay file heap dump tự chúng chưa phải là một báo cáo điều tra hoàn chỉnh.

Sau bài này, bạn có thể:

1. Viết báo cáo kỹ thuật theo chuỗi **triệu chứng → giả thuyết → bằng chứng → thay đổi → kiểm chứng**, tách rõ quan sát và diễn giải.
2. Định lượng phạm vi/tác động bằng thời gian, số request, tỷ lệ lỗi, throughput, latency p50/p95/p99, CPU/GC/heap, nhưng không lạm dụng thống kê hoặc so các cửa sổ tải không tương đương.
3. Tạo **evidence index** có ID, mốc thời gian/múi giờ, nguồn, phạm vi, giới hạn và vị trí lưu an toàn để người khác có thể kiểm tra lại.
4. Nêu **giả thuyết có thể bị bác bỏ** và chủ động ghi các kết quả ngược chiều, thay vì chọn vài ảnh chụp phù hợp với kết luận có sẵn.
5. Ghi thay đổi đủ cụ thể: phiên bản, phạm vi, lý do, nguy cơ, phương án rollback và guardrail; không nhầm “đã deploy” với “đã sửa xong”.
6. Thiết kế phép kiểm chứng **trước/sau có đối chứng hợp lý**, có điều kiện chấp nhận, biết khi nào chỉ được kết luận “tạm cải thiện” hoặc “chưa đủ bằng chứng”.
7. Dùng một chương trình Java 17+ độc lập để thực hành đọc bảng số liệu mẫu và viết **báo cáo mô phỏng** có số liệu nhất quán.

> **Nguyên tắc xuyên suốt:** Báo cáo tốt không phải là báo cáo có nhiều ảnh chụp, mà là báo cáo khiến người khác **truy được mỗi kết luận về đúng bằng chứng**, hiểu **độ không chắc chắn** và biết **bước kiểm chứng tiếp theo**. Một giả thuyết sai nhưng được bác bỏ rõ ràng vẫn là tiến bộ điều tra.

## 1. Năm phần bắt buộc và các phần bổ trợ

Bài báo cáo nên tổ chức theo thứ tự người đọc ra quyết định, không theo thứ tự bạn đã mở các công cụ:

| Thành phần | Câu hỏi phải trả lời | Nội dung tối thiểu | Sai lầm dễ gặp |
| --- | --- | --- | --- |
| **1. Triệu chứng (Symptom)** | Người dùng/hệ thống thấy điều gì bất thường? | Metric đo được, mức tác động, bắt đầu/kết thúc, baseline, workload, phiên bản. | “Ứng dụng chậm” không có khoảng thời gian hoặc thước đo. |
| **2. Giả thuyết (Hypothesis)** | Cơ chế nào *có thể* gây triệu chứng? | Dự đoán kiểm tra được, nguồn nghi vấn, bằng chứng sẽ bác bỏ. | Viết nguyên nhân như đã được chứng minh. |
| **3. Bằng chứng (Evidence)** | Quan sát thực tế nào ủng hộ/bác bỏ? | ID, timestamp, công cụ, snapshot/event/metric, sampling/threshold, giới hạn. | Dán screenshot không có trục thời gian, đơn vị hoặc nguồn. |
| **4. Thay đổi (Change)** | Đã can thiệp vào hệ thống như thế nào? | Code/config/runtime action, phiên bản, rollout, người quyết định, rollback. | Chỉ viết “đã tối ưu” hoặc che mất thay đổi song song. |
| **5. Kết quả kiểm chứng (Validation)** | Thay đổi có cải thiện, an toàn và lặp lại được không? | Cùng điều kiện đo, before/after, acceptance criteria, guardrail, phần chưa chắc chắn. | Xem một lần p95 giảm là đã xác nhận root cause. |

Năm phần trên thường cần thêm **metadata**, **tóm tắt điều hành**, **timeline**, **rủi ro/dữ liệu nhạy cảm**, **trạng thái kết luận** và **action items**. Các phần bổ trợ giúp người đọc tìm chứng cứ và hành động, nhưng không được thay thế năm câu hỏi chính.

### Đọc nhanh bằng ba mức độ

**Mức 1 — 30 giây:** Vấn đề gì, ảnh hưởng ai, đã giảm tác động chưa, còn rủi ro gì và trạng thái hiện tại?

**Mức 2 — 5 phút:** Bảng triệu chứng và so sánh, giả thuyết chính, bằng chứng phản biện, thay đổi, kết quả kiểm chứng, quyết định tiếp theo.

**Mức 3 — điều tra lại:** Timeline chi tiết, định danh môi trường, command/settings, artifacts và dữ liệu gốc được lưu an toàn, phương pháp phân tích, limitations, code/config diff và biên bản phê duyệt.

Một báo cáo phục vụ cả ba mức nhưng không bắt buộc nhét mọi dòng log hoặc dump thô vào nội dung.

## 2. Trước khi viết: định nghĩa “ca sự cố” và giới hạn phạm vi

**Phạm vi** cần được nói rõ để người đọc không diễn giải một đo đạc từ một JVM thành kết luận cho toàn bộ hệ thống.

Ví dụ mô phỏng một báo cáo:

| Trường | Giá trị đã điền trong ví dụ |
| --- | --- |
| Mã ca | `INC-DEMO-017` (chỉ là mã minh họa). |
| Dịch vụ | `catalog-api` trong môi trường **staging giả lập**. |
| JVM | Java 17, một tiến trình chạy ứng dụng trong container; không giả định mọi replica đều giống nhau. |
| Khung thời gian | 09:00–10:00 ngày 29/10/2026, múi giờ `UTC+07:00`. |
| Workload | Bộ 20 latency sample **được tạo sẵn**, không lấy từ production. |
| Phiên bản | `build-A` (baseline), `build-B` (giả lập sự cố), `build-C` (candidate). |
| Metric chính | Latency request theo mili giây, error count/rate trong cùng bộ mẫu. |
| Người đọc dự kiến | Developer, người vận hành và reviewer kiểm chứng. |
| Trạng thái | **Ví dụ đào tạo, không phải ca production đã điều tra thực tế.** |

Ở môi trường thật phải ghi **ứng dụng, cluster/namespace, instance/pod, vùng triển khai, JDK/GC, phiên bản cấu hình**, thời gian deploy và nguồn metric được phép chia sẻ. Nếu một thay đổi chỉ triển khai cho 10% replica, không viết như thể toàn bộ service đã sử dụng phiên bản đó.

### Thời gian: ghi sao cho ghép được log, JFR, metrics

Nên ghi timestamp có timezone/offset, ví dụ:

```text
2026-10-29T09:15:00+07:00
```

Với log/JFR ở `UTC`, chuyển về cùng múi giờ trước khi kết luận hai sự kiện trùng nhau. Ghi cả **thời điểm sự kiện**, **thời điểm thu**, **thời điểm file được tạo** khi chúng khác nhau. Ví dụ JFR chứa event xảy ra lúc 09:15, nhưng `JFR.dump` thực hiện lúc 09:20; **09:20 không phải thời điểm mọi event trong file xảy ra**.

Nếu đồng hồ host/container khác nhau hoặc có clock skew, ghi độ lệch và phương pháp đối chiếu. Các mốc thời gian có thể cho thấy **tương quan**; một timeline chính xác không tự chứng minh quan hệ nhân quả.

## 3. Viết phần “Triệu chứng” theo số đo có thể kiểm tra

### 3.1. Tách ba tầng: phản ánh, quan sát, tác động

1. **Phản ánh người dùng:** “Tải trang tìm kiếm có lúc quay lâu hoặc báo lỗi.” Đó là tín hiệu đầu vào, chưa phải chẩn đoán.
2. **Quan sát hệ thống:** “Trong cửa sổ 09:12–09:17, p95 latency tăng từ khoảng 120 ms ở baseline lên 980 ms trong bộ mẫu; 4/20 request lỗi.” Đây là kết quả đo của ví dụ **giả lập**.
3. **Tác động:** “Người dùng có nguy cơ chờ lâu/timeout, công suất xử lý giảm.” Trên production cần có số người dùng/request bị ảnh hưởng thực tế; không suy số người dùng từ một tập 20 mẫu của lab.

Cấu trúc một câu triệu chứng tốt:

> Trong **cửa sổ thời gian xác định**, **thành phần và nhóm request xác định** có **metric bất thường** so với **baseline cùng điều kiện**, với **phạm vi ảnh hưởng đo được**; đây là **triệu chứng**, chưa phải kết luận nguyên nhân.

### 3.2. Chọn chỉ số đúng

| Chỉ số | Trả lời tốt điều gì? | Điều kiện kèm theo |
| --- | --- | --- |
| **Request count** | Có bao nhiêu mẫu thực sự được đo? | Đơn vị đo, cửa sổ và nguồn số liệu. |
| **Error rate** | Tỷ lệ request lỗi trong tập định nghĩa. | Phải nói lỗi gì: HTTP 5xx, timeout, exception unhandled… |
| **p50** | Độ trễ điển hình của tập mẫu. | Cần mô tả phương pháp/histogram nếu so giữa hệ thống. |
| **p95/p99** | Phần đuôi phân bố latency; phát hiện nhóm request chậm. | Sample đủ lớn, cùng loại request, cùng cách tính. |
| **Throughput** | Request/s, jobs/s, bytes/s. | Không trộn tải đầu vào với số request hoàn tất. |
| **CPU** | Tải CPU của process/host/container. | Phân biệt CPU quota/throttling, per-core và host CPU. |
| **GC pause** | Thời lượng/cường độ dừng do GC. | Dựa GC log/JFR với khoảng thời gian bao phủ rõ. |
| **Heap/Metaspace** | Bộ nhớ đã dùng/committed và xu hướng theo thời gian. | Không nhầm heap với native memory hoặc leak chỉ từ một điểm. |
| **Thread/lock wait** | Chờ monitor, park, I/O hoặc queue. | Có threshold và sampling; cần call stack/timeline. |

Báo cáo lỗi hiệu năng phải có **đơn vị**. “Latency 300” thiếu `ms`; “CPU 2.0” thiếu cách diễn giải; “heap 80%” thiếu giới hạn và loại vùng nhớ.

### 3.3. Công thức nhỏ nhưng hay bị viết sai

Nếu có 4 lỗi trong 20 request:

\[
\text{Error rate}=\frac{4}{20}\times100\%=20\%.
\]

Nếu giảm từ 20% xuống 5% thì:

- **Giảm tuyệt đối:** 15 **điểm phần trăm** (percentage points).
- **Giảm tương đối:** `(20 - 5) / 20 = 75%`.

Không viết “giảm 15%” khi muốn nói giảm **15 điểm phần trăm**. Với 20 mẫu, tỷ lệ rất nhạy với một request: chỉ **một lỗi** làm thay đổi tỷ lệ **5 điểm phần trăm**. Không dùng tập nhỏ để xác nhận một SLO dài hạn.

Nếu latency p95 từ 980 ms xuống 195 ms trong dữ liệu mẫu:

\[
\text{Giảm tương đối}=\frac{980-195}{980}\times100\%\approx80{,}1\%.
\]

Nhưng **195 ms vẫn cao hơn baseline 120 ms**, nên câu “đã trở về bình thường” chưa được chứng minh.

### 3.4. Baseline không phải một con số tự nhiên có sẵn

Phải ghi rõ baseline thu từ đâu và trong điều kiện nào: cùng loại endpoint, request size, số client, khoảng thời gian, phiên bản dữ liệu, traffic mix, warm-up, cache state, phần cứng/CPU quota, GC và mức instrument.

So sánh có thể sai khi:

- Baseline đo một JVM vừa warm-up xong, incident đo khi cold-start.
- Trước sửa dùng 10 req/s, sau sửa dùng 1 req/s.
- Trước sửa p95 trên request thành công, sau sửa p95 trên **tất cả request**, kể cả timeout.
- P95 của một pod so với p95 toàn fleet, hoặc tập trung bình của p95 nhiều pod.
- Số mẫu trước/sau chênh lệch lớn nhưng không nêu.
- Recording JFR hoặc profiler thay đổi cấu hình ngay giữa hai khoảng đo.

Nếu điều kiện chưa tương đương, ghi **“so sánh tham khảo, chưa đủ cơ sở nhân quả”** và lập kế hoạch đo lại.

## 4. Viết giả thuyết có thể kiểm chứng và có thể bị bác bỏ

Một giả thuyết có cấu trúc tốt:

```text
Nếu [cơ chế nghi vấn] gây [triệu chứng],
thì khi [cửa sổ / workload / điều kiện tương ứng],
ta dự đoán sẽ quan sát [dấu hiệu cụ thể].
Nếu không thấy dấu hiệu hoặc thấy [dữ liệu ngược chiều],
giả thuyết phải bị hạ mức tin cậy hoặc bác bỏ.
```

Ví dụ:

| ID | Giả thuyết | Dự đoán có thể kiểm tra | Bằng chứng có thể bác bỏ |
| --- | --- | --- | --- |
| **H1** | Một `synchronized` giữ monitor lâu làm worker chờ, tăng p95. | Nhiều thread `BLOCKED` tại cùng monitor; JFR có `jdk.JavaMonitorEnter` duration cao; owner đang chạy đoạn critical section dài. | Không có contention cùng time window với settings đủ; số liệu cho thấy latency đến từ nơi khác. |
| **H2** | GC pause là nguyên nhân chính của đỉnh latency. | GC log/JFR cho thấy pause đủ dài, trùng phần lớn request chậm; latency giảm khi GC pattern được cải thiện. | Các request chậm không trùng pause đáng kể hoặc pause nhỏ hơn nhiều độ trễ. |
| **H3** | Backend/downstream phản hồi chậm. | Tracing và `jdk.SocketRead` hoặc log upstream cho thấy thời gian đợi ở call liên quan tăng. | Upstream thời gian ổn định trong cùng workload; không có request chậm ở giao tiếp này. |
| **H4** | CPU throttling/compute saturation. | CPU utilization/quota throttling và stack samples phù hợp giai đoạn latency tăng. | CPU/quota ổn, thread chủ yếu chờ I/O/monitor, giả thuyết ít được ủng hộ. |

**Phân biệt “không thấy” với “đã bác bỏ”:** Không có `jdk.JavaMonitorEnter` trong JFR không chắc loại trừ lock contention nếu event bị tắt, threshold quá cao hoặc recording không bao trùm thời điểm. Bác bỏ phải dựa trên **chất lượng phép đo đủ thích hợp**.

### Xếp hạng giả thuyết mà không tạo chắc chắn giả

Có thể gắn mức **cao / trung bình / thấp / chưa đánh giá**, kèm điều kiện và nguồn bằng chứng. Tránh đặt xác suất kiểu “87,4% chắc chắn GC” nếu không có mô hình định lượng được hiệu chuẩn.

Bảng ngắn:

| ID | Mức tin cậy hiện tại | Vì sao | Thử nghiệm tiếp theo |
| --- | --- | --- | --- |
| H1 | Trung bình | Thread dump mô phỏng cho thấy waiter chờ monitor; chưa chứng minh owner giữ do thay đổi code. | Đối chiếu JFR và mã vùng critical section trước/sau. |
| H2 | Thấp | GC pause không đủ dài trong cùng cửa sổ minh họa. | Kiểm tra GC log chính xác ở các request chậm. |
| H3 | Chưa đánh giá | Chưa có log/tracing của downstream. | Thu thời gian call theo request ID. |
| H4 | Chưa đánh giá | Chưa có CPU quota/throttle metrics. | Bổ sung CPU throttling và JFR samples. |

Khi bằng chứng mới đến, cập nhật mức tin cậy thay vì chỉnh sửa ngược lại timeline cho giống kết luận cuối.

## 5. Lập chỉ mục bằng chứng trước khi viết kết luận

**Evidence** không chỉ là link tới file. Nó là một bản ghi đủ metadata để một reviewer biết **từ đâu**, **khi nào**, **có thể nói gì** và **không thể nói gì**.

### 5.1. Cấu trúc mỗi bằng chứng

Một mục có thể bao gồm:

- **ID cố định:** `E01`, `E02`… dùng xuyên suốt báo cáo.
- **Nguồn và tên phép đo:** metric exporter, APM, request log, GC log, `jfr`, `jcmd`, heap dump, code diff, thử nghiệm.
- **Khoảng thời gian tuyệt đối:** timezone, khung đo, JVM/instance và tình trạng đồng bộ đồng hồ.
- **Cách thu:** command, JDK/agent version, event settings, sampling/threshold, scrape interval, filters và mọi công thức biến đổi.
- **Quan sát:** số liệu/trích đoạn đã kiểm tra, không suy diễn ngoài dữ liệu.
- **Giới hạn:** snapshot hay chuỗi thời gian; event có thể thiếu; JFR sampling/threshold; loại đối tượng heap được đo; tính đại diện.
- **Nơi lưu/nhãn bảo mật:** artifact ID trong kho nội bộ đã phân quyền; không chèn raw heap dump/secret vào báo cáo chia sẻ rộng.
- **Liên kết với giả thuyết:** ủng hộ, phản bác hay chưa phân định được.

### 5.2. Các loại chứng cứ Java và giới hạn

| Nguồn | Dùng tốt khi | Giới hạn cần ghi |
| --- | --- | --- |
| **Application logs / tracing** | Nối request ID, endpoint, lỗi, caller và downstream theo thời gian. | Log có thể thiếu hoặc bị lấy mẫu, clock skew, dữ liệu PII. |
| **Metrics** | Xu hướng request rate, error rate, p95, CPU, heap, GC trên nhiều phút/instance. | Aggregation window, sampling interval, histogram buckets có thể ảnh hưởng kết quả. |
| **GC log** | Kiểm tra pause timestamp, loại GC, heap before/after, chu kỳ thu hồi. | Không tự suy ra request cụ thể bị ảnh hưởng nếu chưa ghép timeline. |
| **JFR `.jfr`** | Event CPU sample, GC, lock wait, allocation sample, I/O, thread theo thời gian. | Event settings/threshold/sampling; `duration` thường là elapsed time, không tự bằng CPU time. |
| **Thread dump** | Stack và trạng thái thread tại một thời điểm, lock owner/contender nếu thấy. | Ảnh chụp tức thời, không chứng minh một thread chờ liên tục từ lúc nào. |
| **`GC.class_histogram`** | Đếm instance và tổng **shallow bytes** theo class. | Không đo retained size/root cause leak; có thể ảnh hưởng GC; không đồng nghĩa RSS. |
| **Heap dump + MAT** | Tìm object graph, dominator tree, paths to GC roots. | Nặng và nhạy cảm; tập heap tại snapshot, không tự cho biết xu hướng nhiều ngày. |
| **`VM.native_memory`** | NMT category native memory với baseline/diff nếu đã bật từ startup. | Không bao phủ mọi native allocation; cần phân biệt reserved/committed. |
| **Code/config diff** | Cho biết thay đổi thực tế có tác động tới cơ chế nghi vấn. | “Có diff” không có nghĩa diff là nguyên nhân. |
| **Thử nghiệm kiểm chứng** | Quan sát hiệu quả và regression theo tiêu chí rõ. | Có confounders, noise; trước/sau thiếu control không tự chứng minh causality. |

### 5.3. Ví dụ evidence index mô phỏng

| ID | Khoảng/nguồn | Quan sát được ghi | Hạn chế |
| --- | --- | --- | --- |
| **E01** | 09:00–09:05, sample baseline | 20 request, p95 = 120 ms, lỗi 0/20. | Số liệu giả lập, mẫu rất nhỏ. |
| **E02** | 09:12–09:17, sample incident | 20 request, p95 = 980 ms, lỗi 4/20. | Số liệu giả lập; không có traffic mix thực. |
| **E03** | 09:14, thread dump minh họa | Nhiều worker `BLOCKED` ở một monitor; một thread giữ monitor. | Chỉ snapshot; cần lấy nhiều mẫu/timeline để xác định thời lượng. |
| **E04** | 09:15–09:17, JFR minh họa | Một số `jdk.JavaMonitorEnter` duration cao tại stack cùng đường code. | Đã giả định event enabled và time window phù hợp; cần kiểm tra thực tế. |
| **E05** | 09:18, code review minh họa | Một thao tác I/O được gọi từ bên trong vùng `synchronized`. | Chỉ gợi cơ chế; cần kiểm chứng tác động thay đổi. |
| **E06** | 09:30–09:35, sample after-change | 20 request, p95 = 195 ms, lỗi 1/20. | Candidate giả lập, chưa là kết luận production. |

**Toàn bộ E01–E06 là dữ liệu bài tập giả lập**, không phải recording hoặc dump thực đã được thu. Chương trình ở mục 10 tạo ra số liệu E01, E02, E06; E03–E05 là tình huống giả định để học cách nối bằng chứng nhiều nguồn.

### 5.4. Bảo quản và chia sẻ bằng chứng

HPROF có thể chứa object chứa token, dữ liệu người dùng; JFR có thể chứa class/method, thread, đường dẫn, endpoint và thậm chí JVM arguments/properties tùy event. Command line có thể chứa secret được truyền qua `-D`. Vì vậy:

- Hạn chế người có thể thu/đọc artifact bằng quyền tối thiểu và phê duyệt phù hợp.
- Lưu raw files ở kho/volume có ACL, mã hóa, audit và retention; báo cáo dùng **artifact ID** cùng trích dẫn đã làm sạch.
- Không gửi raw dump, danh sách property, URL chứa token, stack có PII vào ticket/chat công khai.
- Có thể mô tả “đã lưu HPROF trong kho điều tra hạn chế” mà không xuất bản link download rộng rãi.
- Đối chiếu checksum khi quy trình yêu cầu; tránh chỉnh sửa file gốc chỉ để có số liệu đẹp.
- Ghi rõ ai đã thu, thời điểm thu, công cụ và quyền sở hữu; bảo đảm có người dọn dữ liệu theo chính sách.

## 6. Thu bằng chứng JVM phù hợp với câu hỏi, không thu theo thói quen

Các lệnh bên dưới là **hướng dẫn minh họa** cho JVM được quản trị hợp pháp. PID `12345` chỉ là số minh họa; phải xác minh PID thực, quyền attach, namespace/container và tác động trước khi dùng. Một số lệnh có impact vừa/cao hoặc tạo dữ liệu nhạy cảm.

### 6.1. Thread và lock

```bash
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

`Thread.print -l` cung cấp stack thread và thông tin lock của `java.util.concurrent` khi có. Trong báo cáo:

- Ghi thời điểm chính xác của thread dump và bao nhiêu thread cùng loại.
- Tách `BLOCKED` (chờ intrinsic monitor) với `WAITING/TIMED_WAITING` (có thể do park/condition/sleep).
- Kiểm tra lock owner, call site và snapshot thứ hai nếu có để tránh kết luận một lần.
- Không gọi việc có vài thread `WAITING` là deadlock; idle executor cũng có thể chờ bình thường.

### 6.2. JFR theo khung điều tra

```bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=incident-investigation settings=profile
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=incident-investigation filename=/tmp/incident-investigation.jfr
jcmd 12345 JFR.stop name=incident-investigation
```

- `settings=profile` có thể tốn tài nguyên hơn `default`; cần giới hạn thời lượng/khối lượng và kiểm tra khuyến nghị của đội vận hành.
- `JFR.dump` tạo file trong filesystem **JVM đích** và **không tự dừng recording**.
- Khi phân tích: `jfr summary incident-investigation.jfr` để biết file chứa type nào; dùng `jfr print --events jdk.JavaMonitorEnter ...` nếu type thực sự có trong file.
- Event dưới threshold hoặc bị tắt không có trong file; thiếu event không tự bác bỏ giả thuyết.
- Đồng bộ timezone/clock với metric và log trước khi ghép timestamp.

### 6.3. GC và memory

```bash
jcmd 12345 GC.heap_info
jcmd 12345 help GC.class_histogram
jcmd 12345 GC.class_histogram
jcmd 12345 VM.native_memory summary
```

**Không phải lúc nào cũng chạy tất cả các lệnh này.** `GC.class_histogram` có impact cao trong một số tình huống và có thể kích hoạt thu gom (phụ thuộc option); nó đo shallow bytes theo class, không đo trực tiếp root cause leak. `VM.native_memory summary` chỉ hữu ích khi NMT đã được bật lúc khởi động JVM; đừng hiểu output “not enabled” là “0 byte native memory”. Heap dump `GC.heap_dump` có impact và dữ liệu nhạy cảm lớn hơn nữa; chỉ thu khi câu hỏi cần object graph và đã được chấp thuận.

Báo cáo tốt ghi **vì sao** chọn một phép đo, dữ liệu nào được thu, và dữ liệu nào **không** được thu vì không cần thiết hoặc có rủi ro.

### 6.4. Bảng chọn bằng chứng theo giả thuyết

| Câu hỏi | Ưu tiên thu | Khi nào thêm dữ liệu sâu |
| --- | --- | --- |
| Request chậm do lock? | Thread dumps, JFR monitor/park event, request/queue metrics. | Khi cần thấy owner/contender qua nhiều cửa sổ, xem code và thread dumps bổ sung. |
| Do CPU/JIT? | Process/thread CPU metrics, JFR execution samples và compilation events. | Profile sâu/async-profiler được phê duyệt khi samples không đủ. |
| Do GC? | GC logs, JFR GC pause, heap usage và allocation rate. | Heap dump khi nghi retained objects/leak, không chỉ vì GC chậm. |
| Do socket/file I/O? | Tracing, socket/file JFR events, downstream metrics. | Hạ tầng network/storage nếu bằng chứng ứng dụng chưa đủ. |
| Do memory/native? | Heap/Metaspace metrics, NMT (nếu bật), RSS/container memory. | Heap dump, MAT/Native Memory Tracking detail có kiểm soát. |

## 7. Phân biệt bằng chứng, tương quan và nguyên nhân

Ba câu này **không giống nhau**:

1. **Quan sát:** “Trong cùng phút, p95 tăng và `JavaMonitorEnter` có một số duration cao.”
2. **Giả thuyết:** “Lock contention có thể góp phần làm p95 tăng.”
3. **Kết luận nhân quả:** “Sau khi kiểm soát workload và thay đổi đúng critical section, lock wait giảm và latency cải thiện lặp lại; nhiều nguồn bằng chứng phù hợp, các giả thuyết thay thế đã được xem xét.”

Chỉ câu thứ nhất là quan sát trực tiếp từ các con số. Câu thứ hai là **diễn giải để kiểm tra**. Câu thứ ba yêu cầu **thiết kế kiểm chứng**; khi chưa đủ bằng chứng phải nói “được ủng hộ mạnh”, “chưa chứng minh”, hoặc “đã bác bỏ trong phạm vi đo”.

### 7.1. Bẫy thường gặp

- **Correlation ≠ causation:** hai metric cùng tăng không có nghĩa cái trước gây cái sau; có thể cùng do traffic spike.
- **Survivorship bias:** chỉ nhìn request thành công khiến latency ở những request timeout bị bỏ qua.
- **Selection bias:** chọn vài snapshot có lock contention rồi bỏ qua hàng nghìn snapshot bình thường.
- **Observer effect:** bật JFR event rất chi tiết hoặc debugger breakpoint làm workload thay đổi.
- **Regression to the mean:** triệu chứng có thể tự hạ sau spike dù chưa có sửa code; so before/after sát spike dễ nhận công lao nhầm.
- **Confounding:** scale out, cache warm-up, network hồi phục, GC hay thay đổi traffic xảy ra cùng lúc deploy bản sửa.
- **Aggregate masking:** fleet p95 cải thiện trong khi một nhóm tenant/endpoint lại tệ hơn; phân tách theo nhóm có ý nghĩa.

### 7.2. Ghi mức tin cậy theo câu chữ

Dùng các câu có mức độ đúng với chứng cứ:

| Mức độ | Cách viết |
| --- | --- |
| Quan sát được | “E02 ghi nhận p95 980 ms trên 20 mẫu synthetic.” |
| Ủng hộ giả thuyết | “E03–E05 phù hợp với giả thuyết contention trên monitor, nhưng còn thiếu thử nghiệm kiểm soát.” |
| Bằng chứng ngược | “Không quan sát GC pause cùng mức thời gian trong cửa sổ đã ghi; giả thuyết GC chính bị giảm ưu tiên.” |
| Đã thay đổi | “Candidate đưa I/O ra khỏi critical section trong nhánh code được kiểm soát.” |
| Kết quả có giới hạn | “Trong mẫu synthetic, p95 giảm còn 195 ms; vẫn cao hơn baseline 120 ms và chưa chứng minh ổn định production.” |
| Chưa biết | “Chưa thu đủ throughput/CPU/traffic mix và dữ liệu cho nhiều vòng để kết luận.” |

Báo cáo trung thực về điều chưa biết giúp đội vận hành ra quyết định tốt hơn báo cáo tuyên bố “đã root cause” chỉ vì trùng timestamp.

## 8. Ghi thay đổi sao cho người khác tái hiện và rollback được

Phần **thay đổi** phải mô tả **cụ thể can thiệp** và tác động có thể có.

Cấu trúc hữu ích:

1. **Mục đích:** xử lý giả thuyết nào, metric nào được dự đoán cải thiện?
2. **Phạm vi:** module/class/method/config, JVM/instance, version/build và tỷ lệ rollout.
3. **Cơ chế:** thay đổi loại lock, giảm critical section, chỉnh caching, deadline hoặc pool nào?
4. **Rủi ro:** race condition, thứ tự cập nhật dữ liệu, stale cache, memory pressure, throughput, timeouts.
5. **Kiểm thử trước rollout:** unit/integration/concurrency tests liên quan, điều kiện pass/fail.
6. **Tác động quan sát:** thời điểm triển khai, dashboard/recording dùng so sánh, guardrail.
7. **Rollback:** quay về build/config nào, điều kiện kích hoạt và người chịu trách nhiệm theo quy trình.
8. **Thay đổi song song:** scale pod, traffic shift, DB migration, feature flag… nếu có, vì chúng có thể là confounder.

### 8.1. Ví dụ giải thích việc rút I/O khỏi critical section

Đoạn **trước** minh họa (không phải file Java đầy đủ):

```java
synchronized (cacheLock) {
    byte[] fresh = storage.readCurrent(); // Có thể chờ I/O lâu
    cache.put(key, fresh);
}
```

Đoạn **sau** minh họa một cách làm có điều kiện:

```java
byte[] fresh = storage.readCurrent();     // Tính ngoài monitor
synchronized (cacheLock) {
    cache.put(key, fresh);
}
```

`cacheLock`, `storage`, `cache`, `key` là các thành phần có sẵn trong ứng dụng giả định. Đây chỉ là **mã minh họa**, không phải chương trình biên dịch độc lập.

**Đây không phải phép biến đổi luôn đúng.** Nếu nhiều thread đọc/ghi đồng thời, cấu trúc dữ liệu và yêu cầu tính nhất quán có thể cần version check, compare-and-set, đồng bộ theo key, immutable snapshot hoặc một chiến lược khác. Đưa I/O ra ngoài lock **có thể gây race/stale write** nếu không chứng minh invariant. Trước khi ghi “đã sửa”, phải có concurrency tests và kiểm chứng tính đúng đắn nghiệp vụ.

### 8.2. “Thay đổi” khác “giải pháp đã thành công”

- “Đã deploy build C” là **hành động**.
- “CPU giảm sau deploy” là **quan sát**.
- “Build C làm giảm CPU” là **giả thuyết nhân quả**.
- “Đã xác minh code change là nguyên nhân chính” chỉ được viết khi bằng chứng và thiết kế thử nghiệm đủ mạnh.

Ngay cả khi rollback đưa triệu chứng trở lại và redeploy lại cải thiện, đó là bằng chứng mạnh hơn, nhưng vẫn phải xem tác động của cache, traffic và biến động môi trường.

## 9. Thiết kế phần “Kết quả kiểm chứng” trước khi thực hiện thay đổi

Nếu không định nghĩa **tiêu chí pass/fail** trước, người điều tra dễ chọn chỉ số sau triển khai theo hướng có lợi cho bản sửa. Ghi trước:

| Hạng mục | Ví dụ tiêu chí trong staging giả lập | Ý nghĩa |
| --- | --- | --- |
| **Metric chính** | p95 latency giảm xuống **≤ 150 ms** ở workload giống baseline. | Đây là mục tiêu phục hồi của bài tập. |
| **Error rate** | Không lớn hơn baseline; nếu có lỗi cần điều tra. | Tránh “nhanh hơn” nhờ loại bỏ request lỗi khỏi mẫu. |
| **Throughput** | Không giảm dưới mức baseline ở cùng tải. | Một thay đổi có thể giảm latency của request thành công nhưng hạ thông lượng. |
| **CPU/GC** | Không tăng bất thường sau thay đổi. | Guardrail để phát hiện trade-off. |
| **Concurrency correctness** | Không có race/stale write/data corruption trong test liên quan. | Một sửa lock sai có thể làm hệ thống nhanh nhưng không đúng. |
| **Thời gian quan sát** | Nhiều cửa sổ tương đương, sau warm-up, có giờ cao điểm nếu cần. | Phát hiện regression trễ, tránh một điểm đo thuận lợi. |
| **Rollback trigger** | Tỷ lệ lỗi tăng hoặc violation guardrail theo policy được duyệt. | Giúp quyết định không phụ thuộc cảm tính. |

Những ngưỡng trong bảng là **giả định dành cho bài tập**, không phải SLO áp dụng cho mọi service.

### 9.1. Tối thiểu nên có bảng before / incident / after

| Metric | Baseline | Incident | After-change | Diễn giải đúng |
| --- | ---: | ---: | ---: | --- |
| Số request | 20 | 20 | 20 | Tập cực nhỏ; chưa đủ kết luận production. |
| Error count | 0 | 4 | 1 | Sau sửa vẫn còn một lỗi. |
| Error rate | 0,0% | 20,0% | 5,0% | Giảm 15 điểm phần trăm từ incident; chưa về baseline. |
| p50 latency | 100 ms | 150 ms | 130 ms | Trung vị cải thiện nhưng vẫn cao hơn baseline. |
| p95 latency | 120 ms | 980 ms | 195 ms | Giảm ~80,1% từ incident; **chưa đạt mục tiêu ≤150 ms**. |
| p99 latency | 120 ms | 1250 ms | 220 ms | Với chỉ 20 mẫu, cách nearest-rank cho p99 chọn giá trị lớn nhất. |
| Điều kiện đo | Mẫu dựng sẵn | Mẫu dựng sẵn | Mẫu dựng sẵn | Không có inference thống kê về service thật. |

Các giá trị trên được sinh từ dữ liệu cố định của chương trình Java ở mục 10. **Chúng không phải kết quả benchmark hoặc quan sát JVM production.**

### 9.2. Các câu hỏi bắt buộc khi so before/after

1. Khung thời gian, endpoint, request mix, data size, số client, CPU quota, heap/GC/JDK có giống nhau không?
2. Số request, số lỗi, timeout và sampling có được tính theo **cùng mẫu số** không?
3. Load generator, client và server có cùng instrumentation/clock/cấu hình không?
4. Có thay đổi deploy, cache warm-up, autoscaling, feature flag hay downstream trong lúc đo không?
5. Sai lệch lớn hơn mức noise bình thường không? Có các lần lặp/đối chứng để tin cậy không?
6. Các chỉ số phụ (error rate, throughput, memory, CPU, correctness) có tệ đi không?
7. Có tiêu chí đạt được **và** tiêu chí chưa đạt được không?
8. Cần theo dõi lâu hơn hay rollback/giảm phạm vi trước khi tuyên bố giải quyết?

Nếu điều kiện không thể tương đương hoàn toàn, ghi **giới hạn** và dùng phương pháp phù hợp hơn: traffic replay, canary theo cohort, so cùng request mix, test A/B hoặc rollback/redeploy được phê duyệt. Tránh gắn nhãn **“A/B test”** cho phép so hai thời điểm khác tải mà không có phân nhóm/kiểm soát đúng nghĩa.

## 10. Thực hành Java 17+: đo phân vị trên dữ liệu giả lập rồi viết kết luận trung thực

Để kiểm tra cách trình bày các chỉ số, ta tạo **ba bộ số liệu cố định**, không dùng `Thread.sleep`, mạng hoặc GC, vì mục tiêu bài này là **cách báo cáo và suy luận**, không phải benchmark JVM.

Chương trình dùng cách tính **nearest-rank percentile**: sắp tăng dần các latency, chọn phần tử ở vị trí `ceil(p × n)` (đếm từ 1). Có nhiều quy ước tính percentile khác; cần ghi quy ước khi so với hệ thống metrics thật.

Tạo file **`EvidenceMetricsDemo.java`**:

```java
import java.util.Arrays;

public final class EvidenceMetricsDemo {
    record Series(String name, int[] latencyMs, int errors) {}

    private static int nearestRank(int[] values, double quantile) {
        if (values.length == 0) {
            throw new IllegalArgumentException("Empty sample");
        }
        int[] sorted = Arrays.copyOf(values, values.length);
        Arrays.sort(sorted);
        int rank = (int) Math.ceil(quantile * sorted.length);
        return sorted[Math.max(1, rank) - 1];
    }

    private static void report(Series series) {
        int n = series.latencyMs().length;
        double errorRate = 100.0 * series.errors() / n;
        System.out.printf(
                "%s n=%d errors=%d errorRate=%.1f%% p50=%dms p95=%dms p99=%dms%n",
                series.name(), n, series.errors(), errorRate,
                nearestRank(series.latencyMs(), 0.50),
                nearestRank(series.latencyMs(), 0.95),
                nearestRank(series.latencyMs(), 0.99));
    }

    public static void main(String[] args) {
        report(new Series("baseline", new int[]{
                80,90,100,105,110,95,90,85,100,110,
                105,115,120,90,100,85,110,120,95,100
        }, 0));

        report(new Series("incident", new int[]{
                90,95,105,110,115,120,125,130,140,150,
                160,190,220,320,410,600,780,900,980,1250
        }, 4));

        report(new Series("after-change", new int[]{
                85,90,95,100,105,110,115,120,125,130,
                140,145,150,155,165,170,175,185,195,220
        }, 1));

        System.out.println("Synthetic illustration; not a benchmark.");
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 EvidenceMetricsDemo.java
java EvidenceMetricsDemo
```

**Stdout chính xác** của chương trình (các sample là cố định):

```text
baseline n=20 errors=0 errorRate=0.0% p50=100ms p95=120ms p99=120ms
incident n=20 errors=4 errorRate=20.0% p50=150ms p95=980ms p99=1250ms
after-change n=20 errors=1 errorRate=5.0% p50=130ms p95=195ms p99=220ms
Synthetic illustration; not a benchmark.
```

Đoạn code đã được biên dịch bằng `javac --release 17` và chạy thử trên một JDK mới hơn; output trên đã được kiểm tra.

### 10.1. Cách đọc từ dữ liệu tới câu báo cáo

**Câu nên viết:**

> Trong tập dữ liệu giả lập 20 mẫu mỗi giai đoạn, p95 tăng từ 120 lên 980 ms; ở tập after-change p95 là 195 ms, giảm khoảng 80,1% so với incident nhưng vẫn cao hơn baseline. Error rate giảm từ 20% còn 5% nhưng chưa về 0%. Kết quả phù hợp với cải thiện trong bài tập; **chưa đủ để chứng minh bản sửa hiệu quả trên production**.

**Câu không nên viết:**

> Build C đã sửa dứt điểm lỗi latency, hiệu năng tăng 80% và mọi user đã bình thường.

Câu sau không đúng vì: p95 còn 195 ms, còn 1 lỗi/20 request, chưa có dữ liệu về throughput, số user hay workload thật; và phần trăm **latency giảm** không phải mặc nhiên tương đương “hiệu năng tăng” cùng tỷ lệ.

### 10.2. Vì sao n=20 là cảnh báo quan trọng?

Khi n = 20 và nearest-rank:

- p95 lấy phần tử thứ `ceil(0,95 × 20) = 19` sau sắp xếp.
- p99 lấy phần tử thứ `ceil(0,99 × 20) = 20`, tức **giá trị lớn nhất**.
- Thêm/bớt một request có thể thay đổi percentile mạnh.
- Error rate mỗi lỗi tương đương **5 điểm phần trăm**.
- Không có khoảng tin cậy, traffic mix, đối chứng hoặc nhiều lần lặp trong chương trình.

**Bài học:** code giúp tính toán nhất quán, nhưng chất lượng **kết luận** phụ thuộc thiết kế thu mẫu, tính đại diện và bằng chứng độc lập. Một chương trình tạo số đẹp không thay thế kiểm chứng.

## 11. Ví dụ báo cáo hoàn chỉnh đã điền: ca staging giả lập

> **Ghi chú:** Tất cả nhân vật, số liệu, timeline, snapshot và thay đổi trong mục này đều là **mô phỏng phục vụ học tập**, không mô tả một hệ thống thật. Các metric E01/E02/E06 tương ứng với chương trình mục 10; E03/E04/E05 là bằng chứng giả định được dùng để minh họa cách lập luận.

### Tóm tắt

**Mã sự cố:** `INC-DEMO-017`  
**Đối tượng:** `catalog-api`, staging giả lập, Java 17  
**Thời gian:** 09:00–09:40, 29/10/2026 (`UTC+07:00`)  
**Trạng thái:** Candidate cải thiện các chỉ số trên dữ liệu mẫu, **chưa đạt tiêu chí p95 ≤150 ms**, cần thêm kiểm chứng.

**Tác động quan sát trong bài tập:** bộ 20 request có p95 tăng từ 120 ms (baseline) lên 980 ms (incident), lỗi tăng từ 0/20 lên 4/20. Không suy ra số người dùng production bị ảnh hưởng vì dữ liệu là synthetic.

**Giả thuyết chính:** contention ở một monitor có thể là thành phần lớn của latency, trong khi một thao tác I/O nằm bên trong critical section. Một số bằng chứng minh họa E03–E05 tương thích với giả thuyết, nhưng cần đo bằng JFR và thử nghiệm tải có kiểm soát trên hệ thống thật.

**Thay đổi minh họa:** candidate chuyển phần đọc I/O ra ngoài monitor trong nhánh được đánh giá, kèm yêu cầu kiểm thử tính nhất quán dữ liệu. Không triển khai production trong bài tập này.

**Kết quả mẫu:** p95 giảm từ 980 ms xuống 195 ms; error rate giảm từ 20% xuống 5%, nhưng baseline là 120 ms và 0%. **Chưa thể đóng ca với trạng thái “đã khôi phục hoàn toàn”.**

### Triệu chứng và timeline

| Thời điểm UTC+07 | Sự kiện/tác vụ mô phỏng | Dấu vết |
| --- | --- | --- |
| 09:00–09:05 | Chạy bộ mẫu baseline `build-A`. | E01: p95=120 ms, 0/20 lỗi. |
| 09:12–09:17 | Phát hiện p95 tăng ở bộ mẫu `build-B`. | E02: p95=980 ms, 4/20 lỗi. |
| 09:14 | Lấy thread dump giả định trong cửa sổ incident. | E03: waiter chờ monitor, một thread owner. |
| 09:15–09:17 | Xem JFR event giả định cùng khoảng thời gian. | E04: các wait event trên cùng call path. |
| 09:18 | Đối chiếu mã giả định của critical section. | E05: thao tác I/O nằm trong monitor. |
| 09:20 | Xác định candidate và điều kiện cần kiểm thử. | Đề xuất thay đổi, chưa coi là fix. |
| 09:25 | Chạy kiểm tra tính đúng đắn/đánh giá risk của candidate. | Kết quả test cần bổ sung khi thực hiện thật. |
| 09:30–09:35 | Đọc bộ mẫu after-change `build-C`. | E06: p95=195 ms, 1/20 lỗi. |
| 09:40 | Viết kết luận và kế hoạch kiểm chứng tiếp. | Trạng thái **cải thiện chưa đủ**. |

### Giả thuyết

- **H1 — Monitor contention:** được E03/E04/E05 *minh họa* là phù hợp. Cần thử nghiệm có đối chứng để xác nhận vai trò nhân quả.
- **H2 — GC pause:** chưa đủ dữ liệu giả lập để khẳng định hay loại trừ. Cần GC log/JFR cùng time window nếu là incident thật.
- **H3 — Downstream chậm:** chưa có đo đạc downstream. Dự kiến xem tracing và socket event.
- **H4 — CPU saturation:** chưa có CPU/quota metrics. Chưa xếp thành nguyên nhân.

### Bằng chứng

E01, E02, E06 là các sample và chỉ số được chương trình Java ở mục 10 tính. E03, E04, E05 là tình huống giả định, không có raw artifact thật để tải; vì thế đây **không phải hồ sơ nghiệm thu production**.

Mức tin cậy về nguyên nhân chính: **chưa xác nhận**. Sự đồng thời của monitor wait và latency (nếu quan sát thật) chỉ tạo giả thuyết có cơ sở, chưa loại trừ toàn bộ biến khác.

### Thay đổi và rủi ro

**Candidate:** chuyển thao tác I/O ra ngoài critical section, giữ phần cập nhật shared state dưới monitor. 

**Nguy cơ:** stale data/race khi hai thread cùng đọc và update; cần chứng minh invariant, kiểm tra tính thứ tự và retry policy.

**Triển khai:** chỉ trong mô phỏng; production rollout sẽ cần review, canary và rollback.

**Rollback trong quy trình thực:** trở về bản đã được kiểm chứng, điều kiện kích hoạt dựa error rate/latency/correctness guardrail. Đừng coi rollback là phép xóa mọi side effect đã xảy ra.

### Kiểm chứng

| Tiêu chí | Mục tiêu mô phỏng | After-change | Đánh giá |
| --- | --- | --- | --- |
| p95 latency | ≤150 ms | **195 ms** | **Chưa đạt**. |
| Error rate | Không cao hơn baseline 0% | **5%** | **Chưa đạt**. |
| Throughput | Không giảm | Chưa đo | **Chưa kết luận**. |
| CPU/GC/memory | Không thoái lui | Chưa đo | **Chưa kết luận**. |
| Data consistency | Không race/stale write | Chưa test thực | **Chưa kết luận**. |
| Tái lập kết quả | Nhiều vòng cùng workload | Mới một bộ synthetic | **Chưa đủ**. |

**Quyết định:** Không tuyên bố “incident resolved”; ưu tiên thu thêm dữ liệu đủ mẫu, kiểm thử concurrency và kiểm chứng trên workload tương đương trong staging. Nếu gặp regression ở dữ liệu thật, dừng rollout theo policy đã duyệt.

### Kế hoạch hành động sau báo cáo

| Hành động | Mục đích | Tiêu chí hoàn thành |
| --- | --- | --- |
| Bổ sung quan sát monitor wait và thread owner vào cửa sổ test. | Kiểm tra H1 trực tiếp. | Có JFR/thread dump với timestamp, settings, call path và quyền lưu đúng. |
| Chạy stress/concurrency tests cho candidate. | Phát hiện stale write và race do rút I/O khỏi monitor. | Invariant và test assertions đều đạt; không chỉ dựa latency. |
| Chạy cùng traffic mix và đủ sample trong nhiều vòng. | Giảm sampling noise/confounders. | Có before/after lặp lại, số mẫu và cách tính p95 công bố. |
| Đo CPU/GC/throughput/error rate. | Kiểm tra guardrails. | Không có regression vượt tiêu chí đã phê duyệt. |
| Cập nhật kết luận và quyết định rollout/rollback. | Khép vòng phản hồi. | Có người duyệt, bằng chứng và hành động tiếp theo rõ ràng. |

Bản báo cáo ví dụ vẫn **hữu ích** dù trạng thái là “chưa xác nhận”: người đọc biết phép đo nào đã có, giả thuyết nào chưa được kiểm tra, rủi ro của candidate và kết quả cần đạt trước khi đóng ca.

## 12. Cách diễn đạt khiến báo cáo dễ được tin cậy

### 12.1. Tránh câu kết luận mạnh hơn bằng chứng

| Không nên viết | Nên viết |
| --- | --- |
| “JVM chết do GC.” | “GC log ghi pause 1.2 s đúng thời điểm nhiều request timeout; cần đối chiếu với request tracing để xác định mức đóng góp.” |
| “Thread dump chứng minh deadlock.” | “Một dump có hai thread chờ lock. Chưa xác định vòng chờ; cần owner graph hoặc deadlock detection.” |
| “Bị memory leak vì heap cao.” | “Heap used tăng qua nhiều chu kỳ và không trở về baseline; cần kiểm tra retained objects/GC roots sau ổn định.” |
| “Đã fix vì JFR hết event chậm.” | “Không thấy event trong recording mới; cần xác nhận event enabled, threshold và workload giống nhau trước khi so.” |
| “P95 giảm 80%, hiệu năng tăng 80%.” | “P95 latency trong tập mẫu giảm ~80,1%; chưa suy ra throughput, tài nguyên hoặc tác động toàn dịch vụ.” |
| “Ai đó cấu hình sai.” | “Một thay đổi cấu hình không có guardrail/validation đã làm tăng rủi ro; cần tăng kiểm thử và khả năng phát hiện.” |
| “Không tái hiện được nên không có lỗi.” | “Chưa tái hiện dưới điều kiện hiện tại; cần so dữ liệu, tải và môi trường với thời điểm sự cố.” |
| “Root cause đã chứng minh 100%.” | “Dữ liệu và thử nghiệm trong phạm vi đo ủng hộ mạnh H1; vẫn còn giới hạn về thời lượng/mẫu/điều kiện.” |

### 12.2. Báo cáo không đổ lỗi cá nhân

Mô tả **hệ thống, quyết định, dữ liệu, kiểm soát thiếu và cách ngăn tái diễn** thay vì định danh người để quy trách nhiệm cảm tính. Tinh thần postmortem là cải thiện cơ chế vận hành: guardrail, review, test, monitoring, deploy/rollback.

Phân biệt:

- **Tác nhân trực tiếp (trigger):** ví dụ một bản triển khai làm tăng thời gian critical section.
- **Cơ chế kỹ thuật (mechanism):** nhiều thread chờ monitor tạo queue và latency.
- **Điều kiện đóng góp (contributing factors):** thiếu load test trên traffic mix, cảnh báo lock wait hoặc code review check.
- **Kết quả (impact):** p95 tăng, error rate/timeout tăng.
- **Hành động phòng ngừa:** giảm phạm vi lock, test invariant, thêm alert, rollout canary và rollback trigger.

Không cần kết luận “một cá nhân là nguyên nhân” để viết được report chất lượng cao.

## 13. Kiểm tra chất lượng cuối trước khi gửi

### 13.1. Kiểm tra dữ liệu

- [ ] Có thời gian bắt đầu/kết thúc, timezone và môi trường/instance/JDK xác định.
- [ ] Triệu chứng được ghi thành chỉ số, đơn vị, baseline và phạm vi ảnh hưởng.
- [ ] Tên metric, mẫu số, thời lượng cửa sổ và phương pháp percentile nhất quán.
- [ ] Số count/error rate/p95 trong bảng, biểu đồ và văn bản **không mâu thuẫn**.
- [ ] Có evidence index; mỗi kết luận quan trọng dẫn đến một/một nhóm ID kiểm tra lại được.
- [ ] Phân biệt **snapshot**, event có threshold/sampling, số đo tổng hợp và dữ liệu thô.
- [ ] Không đánh đồng timestamp của file dump với timestamp của event hoặc request.
- [ ] Không đăng trực tiếp secret/PII, heap dump/JFR raw hoặc command line chứa credentials.

### 13.2. Kiểm tra lập luận

- [ ] Mỗi giả thuyết có dấu hiệu kỳ vọng và điều kiện có thể bác bỏ.
- [ ] Các kết quả **không phù hợp giả thuyết chính** cũng được ghi.
- [ ] Không nhầm tương quan với nguyên nhân, hay một lần thử với kết luận sản xuất.
- [ ] Thay đổi kỹ thuật có lý do, phạm vi, phiên bản, rủi ro và rollback.
- [ ] Kiểm chứng có điều kiện tải tương đương, đủ cửa sổ/mẫu và các chỉ số guardrail.
- [ ] Mỗi tiêu chí rõ **đạt / chưa đạt / chưa đo**; không điền “PASS” cho phép đo còn thiếu.
- [ ] Có trạng thái hiện tại và người nhận quyết định tiếp theo.
- [ ] Báo cáo không đổ lỗi và có action items phòng ngừa cụ thể.

### 13.3. Kiểm tra văn bản

- [ ] Bắt đầu bằng tóm tắt dễ đọc, không mở đầu bằng hàng nghìn dòng log.
- [ ] Tránh thuật ngữ viết tắt chưa giải thích; bảng/ảnh có trục, thời gian và đơn vị.
- [ ] Phân biệt **số liệu thực**, **số liệu mô phỏng** và **giả thuyết** bằng nhãn rõ.
- [ ] Code snippet được ghi là minh họa hay chương trình chạy được, stdout có căn cứ.
- [ ] Có đường dẫn/hình thức truy xuất artifact an toàn theo quyền, không giả định link public.
- [ ] Báo cáo đủ để một người ngoài nhóm điều tra hiểu và đặt lại câu hỏi cần kiểm chứng.

## 14. Bài tập áp dụng

### Bài tập 1: sửa câu triệu chứng

Câu chưa đủ: “Server lag, chắc do GC.”

**Cách sửa:** “Trong 10 phút gần sự cố, endpoint X có p95 latency tăng từ khoảng 140 ms lên 850 ms, error rate tăng từ 0,5% lên 4,2% theo metric cùng cửa sổ. GC là một giả thuyết cần đối chiếu GC log/JFR theo timestamp.” Các số ở đây là **ví dụ giả định**, không phải kết quả thật.

### Bài tập 2: tìm điểm yếu của bằng chứng

Dữ liệu: một thread dump có 12 thread `WAITING`.

**Hỏi:** Có thể kết luận deadlock không?

**Đáp:** Không. Thread idle trong executor hoặc đang đợi `BlockingQueue.take()` cũng có thể `WAITING`. Cần stack, owner/lock graph, chuỗi snapshot và kiểm tra khả năng tiến triển của công việc.

### Bài tập 3: đánh giá kết quả sau sửa

Từ mã mục 10: p95 từ 980 xuống 195 ms, baseline là 120 ms và tiêu chí là 150 ms.

**Đáp:** Đã cải thiện **trong dữ liệu giả lập** nhưng **chưa đạt** mục tiêu phục hồi. Vì chỉ có 20 mẫu/giai đoạn và không có hệ thống thật, chưa đủ chứng minh một bug đã được sửa.

### Bài tập 4: một thay đổi và hai metric ngược chiều

Đã giảm p95 nhưng throughput giảm một nửa, error rate tăng, hoặc test concurrency fail.

**Đáp:** Không công bố “PASS” chỉ vì latency tốt lên. Phải xem guardrail, ưu tiên tính đúng đắn và quyết định rollback/điều chỉnh theo tiêu chí đã đề ra.

### Bài tập 5: câu kết luận thiếu kiểm chứng

Câu: “Sau deploy, CPU thấp hơn nên bản code mới giải quyết root cause.”

**Đáp:** Chưa đủ. Có thể do traffic giảm, autoscaling, cache warm-up, thay đổi số request lỗi hoặc CPU throttling. Cần so tải tương đương, xem profiling và các metric phụ, thử lặp hoặc đối chứng.

## 15. Ghi nhớ

- **Triệu chứng:** mô tả cái gì bị sai bằng metric có ngữ cảnh.
- **Giả thuyết:** mô tả cơ chế có thể gây sai, kèm cách kiểm tra và điều kiện bác bỏ.
- **Bằng chứng:** ghi quan sát kiểm tra được với ID, thời gian, nguồn và giới hạn.
- **Thay đổi:** ghi cụ thể can thiệp nào, vì sao, rủi ro và rollback.
- **Kiểm chứng:** so trước/sau dưới điều kiện hợp lý, có tiêu chí đạt/chưa đạt và biết điều chưa đo.
- **Kết luận tốt:** không xóa dữ liệu ngược chiều, không giấu uncertainty, không vượt quá phạm vi bằng chứng.

Một báo cáo có thể kết thúc với **“đã giảm tác động nhưng chưa khẳng định nguyên nhân”**. Đó là kết quả điều tra có giá trị nếu nó đi kèm bằng chứng, rủi ro, người chịu trách nhiệm và hành động tiếp theo.

## Tài liệu tham khảo

- [Oracle JDK 21 — `jcmd` và các diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print`, `GC.heap_info`, `GC.class_histogram`, `JFR.start/dump/stop`, `VM.native_memory`.
- [Oracle JDK 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `metadata`, `print`, lọc JFR events.
- [Oracle Java 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): chọn công cụ phù hợp cho CPU, thread, GC, memory và sự cố runtime.
- [Google SRE — Postmortem Culture: Learning from Failure](https://sre.google/resources/book-update/postmortem-culture/): văn hóa học từ sự cố, bằng chứng, tránh đổ lỗi và cải tiến hệ thống.
- [Google SRE — Lessons Learned: Postmortem Culture](https://sre.google/sre-book/lessons-learned/): cách đánh giá điều đã xảy ra, hiệu quả phản ứng và hành động phòng ngừa.

