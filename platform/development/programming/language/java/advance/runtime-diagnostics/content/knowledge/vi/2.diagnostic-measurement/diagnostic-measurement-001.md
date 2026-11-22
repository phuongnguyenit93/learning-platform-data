# 2.1 Xác định tình huống tái hiện, tải đầu vào và tiêu chí hoàn thành chẩn đoán

## Mục tiêu học tập

Một cuộc điều tra lỗi Java chỉ đáng tin khi người khác có thể hiểu **lỗi xuất hiện trong điều kiện nào**, **hệ thống phải xử lý loại tải gì** và **bằng chứng nào đủ để khép lại việc chẩn đoán**. Bài này hướng dẫn thiết kế ba thành phần đó trước khi thu thập nhiều log, thread dump hay hồ sơ hiệu năng.

Sau bài học, bạn có thể:

- Viết một **hợp đồng tái hiện** (reproduction contract): thao tác kích hoạt, môi trường, dữ liệu, dấu hiệu lỗi, điều kiện kiểm soát và cách lặp lại.
- Mô tả **workload** bằng tốc độ đến của request, mức đồng thời, cơ cấu thao tác, cỡ payload, thời lượng, dữ liệu và giai đoạn warm-up.
- Đặt **tiêu chí hoàn thành chẩn đoán** có thể kiểm tra: bằng chứng đủ xác nhận/bác bỏ giả thuyết, mức độ tái hiện, độ tin cậy và bước bàn giao xử lý.
- Phân biệt **“đã chẩn đoán xong”**, **“đã có biện pháp giảm thiểu”** và **“đã sửa lỗi, kiểm chứng xong”**.

## 1. Bắt đầu bằng một triệu chứng có thể quan sát

Các mô tả như “JVM chậm”, “service treo” hoặc “thỉnh thoảng chết” chưa đủ để tạo một phép đo. Chúng không cho biết đối tượng, thời điểm, tác động và điều gì được coi là lỗi.

Hãy biến báo cáo thành một phát biểu có thể kiểm tra:

> “Trong phiên bản ứng dụng X, khi xử lý khoảng 100 request/giây trong 10 phút, đường đi `POST /checkout` có p95 latency tăng từ khoảng 180 ms lên trên 800 ms; hiện tượng tập trung trên hai instance sau khi tải tăng, được xác định qua request ID và biểu đồ độ trễ.”

Các con số trên **chỉ minh họa**. Với một sự cố thực, phải điền số đo, nguồn dữ liệu và cửa sổ thời gian thực.

Một phát biểu đủ dùng thường trả lời:

| Câu hỏi | Thông tin cần ghi |
| --- | --- |
| **Cái gì sai?** | Trả kết quả sai, HTTP 5xx, timeout, treo request, throughput sụt, heap tăng sau GC, CPU cao hay restart |
| **Sai ở đâu?** | Tên service, endpoint/job, instance/pod, vùng triển khai, bản build và JDK |
| **Bắt đầu khi nào?** | Timestamp có múi giờ, thời lượng, tần suất, có tương quan deploy/cấu hình hay không |
| **Ảnh hưởng ai và bao nhiêu?** | Nhóm người dùng, request, partition, tenant, tác động nghiệp vụ |
| **So với điều gì?** | Baseline là cùng loại thao tác, dữ liệu và tải ở trạng thái được coi là khỏe |
| **Bằng chứng gốc?** | Metric query, trace ID, log có timestamp, test case, thread/JFR snapshot và nguồn lưu trữ |

**Triệu chứng khác nguyên nhân.** Một request timeout chỉ xác nhận request vượt deadline; nó chưa chứng minh nguồn gốc là GC, database, queue, mạng hay một đoạn code cụ thể. Viết hiện tượng theo cách không “gài sẵn” giả thuyết nguyên nhân.

## 2. Tình huống tái hiện (reproduction scenario) là gì?

Một tình huống tái hiện là **tập điều kiện và hành động được mô tả đủ rõ để lặp lại hiện tượng**. Nó giống một thí nghiệm có thể thực hiện lại: giữ các yếu tố cần thiết ổn định, thay đổi có chủ đích một yếu tố, quan sát kết quả.

Nó gồm sáu phần:

1. **Điểm xuất phát:** artifact/build hash, JDK/JVM, flags quan trọng, hệ điều hành/container, cấu hình, dependency và trạng thái dữ liệu ban đầu.
2. **Tác nhân kích hoạt:** request, job, lịch tác vụ, input cụ thể, thứ tự thao tác hoặc thời điểm tăng tải.
3. **Cách thực hiện:** từng bước hoặc kịch bản tạo tải, bao gồm giai đoạn khởi động, warm-up, thời lượng đo và cách dừng.
4. **Dấu hiệu nhận biết lỗi (failure oracle):** điều kiện có thể xác minh như mã lỗi, kết quả sai, deadline vượt ngưỡng, luồng bị chặn hoặc tiến trình bị thoát.
5. **Bằng chứng và đối chứng:** request ID, log, trace, biểu đồ, metric, test output và một lần chạy khỏe với điều kiện tương đương.
6. **Khả năng lặp lại:** lỗi xảy ra ở bao nhiêu lần chạy, có phụ thuộc thời gian/tải/thứ tự/seed không, và còn yếu tố nào chưa kiểm soát.

### 2.1 Ghi đủ ngữ cảnh để người khác tái hiện

Thông tin cần cố định hoặc ghi nhận tùy loại sự cố:

- **Mã và JVM:** commit hoặc image digest, phiên bản JDK và vendor, startup flags, `-Xms`/`-Xmx` nếu liên quan, thư viện/driver.
- **Hệ thống:** số CPU được cấp, giới hạn memory của container, OS, vùng triển khai, topology, DNS, network route.
- **Ứng dụng:** profile, feature flag, timeout/retry, kích thước thread/connection pool, cache TTL, log sampling.
- **Dữ liệu:** dữ liệu khởi tạo, kích thước tập dữ liệu, kiểu phân phối, khóa nóng, tình trạng index, schema/migration, tenant/permission cần thiết.
- **Phụ thuộc:** database, queue, object storage, API ngoài, phiên bản và độ trễ/giới hạn của chúng.
- **Thời gian và vòng đời:** mới khởi động hay đã warm, cache lạnh hay nóng, thời gian chạy trước khi lỗi xuất hiện, cron/batch chạy đồng thời.
- **Đầu vào:** method/path, headers có liên quan, request body đã loại bỏ bí mật, số lượng phần tử, kích thước payload, loại request.

Không nhất thiết đóng băng **mọi** biến của hệ thống: hãy ghi những biến có thể ảnh hưởng hiện tượng và làm rõ điều gì vẫn chưa biết. Đặc biệt, “cùng source” không đồng nghĩa “cùng binary, JDK, flags, cấu hình và tải”.

### 2.2 Phân loại mức tái hiện

**Tái hiện xác định (deterministic).** Cùng input và tiền điều kiện, lỗi luôn xảy ra. Ví dụ một input cố định làm hàm Java trả kết quả sai. Dùng unit/integration test và kiểm tra code thường hiệu quả.

**Tái hiện phụ thuộc tải/trạng thái.** Lỗi chỉ xuất hiện khi số kết nối đang dùng tăng, bộ nhớ đầy dần, cache nguội, hàng đợi dài hoặc thứ tự thao tác cụ thể. Cần mô tả cả *lịch sử trạng thái trước khi đo*, không chỉ một request.

**Tái hiện gián đoạn (intermittent/probabilistic).** Lỗi xuất hiện không đều, có thể do race condition, scheduling, network hay deadline. Thay vì đòi “phải lỗi 100%”, ghi `k/n` lần chạy, thời lượng và điều kiện của mỗi lần. Ví dụ “6/20 lần có timeout trong 10 phút/tần suất tương đương”, chưa đủ để kết luận xác suất thực sự là đúng 30%.

**Không thể tái hiện trong môi trường kiểm soát.** Vẫn có thể chẩn đoán từ evidence production (logs/traces/JFR/metrics) nếu lưu dấu vết đầy đủ. Hãy ghi rõ giới hạn và mức tin cậy, không tuyên bố một giả thuyết đã được chứng minh chỉ vì “test local không bị”.

### 2.3 Mẫu hợp đồng tái hiện

```text
Sự cố: [triệu chứng định lượng, tác động]
Run ID / thời gian / múi giờ:
Service, build, JDK, JVM flags:
Môi trường: CPU/memory limit, dependency và cấu hình liên quan
Trạng thái ban đầu: dữ liệu, cache, queue, kết nối, warm/cold
Input: thao tác, tỉ lệ request, kích thước/kiểu dữ liệu
Cách kích hoạt: từng bước, seed (nếu có), mức tải và thời lượng
Dấu hiệu lỗi: oracle rõ ràng, ví dụ timeout > 2 s hay kết quả sai
Đối chứng: phiên bản/cửa sổ khỏe dưới điều kiện tương đương
Quan sát: k/n lần hoặc metric p95/p99, lỗi, throughput
Evidence: tên nguồn, thời gian, request/trace ID, vị trí lưu
Điều kiện dừng và cách dọn dữ liệu thử:
Điều chưa kiểm soát / giả thuyết cần kiểm chứng:
```

Một runbook tốt đủ cụ thể để đồng đội chạy lại mà không phải hỏi “gọi endpoint nào?”, “dùng data nào?”, “tạo bao nhiêu request?” hay “thế nào được gọi là lỗi?”.

## 3. Tải đầu vào (workload) phải được định nghĩa trước khi đo

**Workload** là phân phối công việc chương trình nhận và xử lý theo thời gian. Hai lần chạy cùng tổng 10.000 request có thể gây trạng thái JVM rất khác nhau nếu một lần dàn đều trong 10 phút và một lần dồn vào 10 giây.

### 3.1 Các trục của workload

| Trục | Cách mô tả có ích |
| --- | --- |
| **Tốc độ đến (arrival rate)** | Request/giây (RPS), event/giây, message/giây, có ramp-up và spike không |
| **Mức đồng thời (concurrency)** | Số request hoặc tác vụ đang xử lý; với client đóng vòng lặp, số virtual users/in-flight tối đa |
| **Thành phần (mix)** | Ví dụ 70% đọc, 20% tìm kiếm, 10% ghi; phân biệt nhánh nhanh/chậm |
| **Kích thước/độ khó input** | Payload byte, số record, phân phối kích thước, kiểu truy vấn, key nóng/lạnh |
| **Thời lượng** | Warm-up, ramp, khoảng đo ổn định, đợt burst, thời gian hồi phục |
| **Dữ liệu và trạng thái** | Dataset, cache hit/miss, connection pool, số phần tử queue, dữ liệu tích lũy |
| **Điều kiện phụ thuộc** | Latency database/API, timeout, lỗi giả lập, giới hạn rate và số kết nối |
| **Điều kiện máy** | Giới hạn CPU/memory, số instance, GC/JVM flags, tác vụ nền |

**Đừng dùng “100 users” thay cho “100 RPS”.** Một user có thể gửi nhiều hoặc ít request tùy thời gian nghĩ (think time), response time và lịch điều phối. Số tác vụ đang xử lý cũng không nhất thiết bằng số client.

Ví dụ minh họa:

- **Load mở (open model):** bộ phát chủ động tạo 50 request mới mỗi giây dù server đang chậm; nếu server không theo kịp, queue/backlog có thể tăng.
- **Load đóng (closed model):** 20 client đồng thời, mỗi client chờ response rồi mới gửi tiếp; khi response chậm, tổng RPS thường giảm theo.

Hai mô hình trả lời hai câu hỏi khác nhau. Khi kiểm tra năng lực chịu tải trước lưu lượng từ bên ngoài, cần xem mô hình phát tải có giống thực tế không; khi tái hiện race condition, mức đồng thời và lịch tác vụ có thể quan trọng hơn RPS bình quân.

Ở trạng thái ổn định, định luật Little cho biết **số công việc trung bình trong hệ thống = tốc độ hoàn thành trung bình × thời gian ở trong hệ thống trung bình** (với ranh giới đo và giả định phù hợp). Đây là quan hệ để kiểm tra tính hợp lý, **không** phải phép quy đổi trực tiếp giữa RPS và số user khi hệ thống đang tắc nghẽn hoặc chưa ổn định.

### 3.2 Tách ba giai đoạn của mỗi lần chạy

1. **Chuẩn bị và warm-up:** khởi động hệ thống, làm nóng JIT, class loading, cache hoặc connection pool nếu kịch bản là warm state; ghi rõ nếu đang đo cold start. Không trộn mẫu warm-up vào cửa sổ đo của kịch bản ổn định.
2. **Giai đoạn đo:** cố định lịch phát tải, tập dữ liệu và cửa sổ thời gian. Thu latency, error rate, throughput thực đạt, backlog, CPU/heap/GC, thread/connection pool, dependency timing theo đúng loại vấn đề.
3. **Hồi phục và cleanup:** giảm/dừng load, kiểm tra queue có thoát nghẽn không, tài nguyên có trở về mức ổn định không, dọn dữ liệu test và lưu artifact. Với rò rỉ/bất thường tích lũy, cửa sổ quan sát sau tải có thể quyết định.

**Đo máy phát tải:** nếu load generator đã quá tải, mất kết nối hoặc lệch lịch gửi, biểu đồ server không còn phản ánh workload dự kiến. Ghi cả **RPS yêu cầu** và **RPS thực sự đạt**, lỗi phía client, timeout client, số in-flight và khả năng đáp ứng của load generator.

### 3.3 Chọn dữ liệu đầu vào đại diện

- Chọn trường hợp điển hình **và** trường hợp biên: payload lớn, khóa nóng, số bản ghi nhiều, cache miss, request có nhiều dependency.
- Cố định seed khi sinh dữ liệu ngẫu nhiên để có thể tái hiện; đồng thời lưu ý một seed đơn lẻ có thể không đại diện. Có thể dùng nhiều seed được ghi rõ nếu lỗi phụ thuộc phân phối.
- Với trường hợp cập nhật dữ liệu, đảm bảo mỗi lần chạy bắt đầu từ trạng thái tương đương hoặc có cách reset. Dữ liệu tích lũy có thể khiến lần sau chậm hơn dù code không đổi.
- Dùng dữ liệu tổng hợp hoặc dữ liệu đã được loại bỏ thông tin nhạy cảm; tránh sao chép token, dữ liệu cá nhân hoặc thông tin production thô vào log và báo cáo.
- Một kịch bản “request nhỏ, cache nóng” không đủ đại diện cho sự cố chỉ xảy ra ở truy vấn lớn, cache lạnh hoặc dữ liệu skew.

## 4. Đặt baseline và chọn thước đo trước khi chạy

**Baseline** là quan sát tham chiếu để so sánh. Nó có thể là môi trường khỏe, bản phát hành trước, hoặc khoảng thời gian khỏe trên cùng môi trường. Baseline đáng tin khi ghi rõ **điều kiện tương đương** về dữ liệu, workload, thời lượng, số instance và cấu hình.

Với Java service, thường cần kết hợp:

- **Tín hiệu người dùng:** latency p50/p95/p99, error rate, timeout rate, correctness của output.
- **Khối lượng:** request đến, request hoàn tất, throughput thực tế, số request đang chờ, queue depth.
- **JVM:** CPU của process, heap used sau GC, allocation rate, GC pause time/frequency, thread count và blocked/waiting threads.
- **Hạ tầng và dependency:** CPU throttling, memory/container OOM, kết nối DB, pool wait time, network/error, độ trễ downstream.
- **Bằng chứng định vị:** log có correlation/request ID, trace span, JFR hoặc thread/heap dump khi cần.

Một metric đơn lẻ hiếm khi đủ. Ví dụ p99 tăng cùng GC pause tăng chỉ tạo **giả thuyết** GC đóng góp vào độ trễ; cần khớp timestamp, đối chiếu request/trace và loại trừ queue/dependency trước khi kết luận.

### 4.1 Định nghĩa metric rõ để tránh đo sai

- **Latency:** đo từ đâu đến đâu? Tại client từ khi gửi đến khi nhận đủ response, tại gateway hay trong handler? Có tính hàng đợi, retry và timeout không? Không so sánh các metric khác ranh giới như thể chúng giống nhau.
- **Error rate:** mẫu số là mọi request đến, mọi request hoàn tất hay chỉ request hợp lệ? Tử số gồm 5xx, timeout, lỗi nghiệp vụ nào? Ghi rõ cách xử lý 4xx dự kiến.
- **p95:** phân vị thứ 95 của các quan sát; khác giá trị trung bình. Với ít mẫu, p95/p99 kém ổn định, nên chọn cửa sổ và cỡ mẫu tương xứng, lặp lại khi biến thiên lớn.
- **Thông lượng:** RPS mà bộ phát yêu cầu khác RPS server hoàn tất. Khi bão hòa, lượng request tồn đọng có thể tăng dù throughput hoàn tất đứng yên.
- **Ngưỡng:** ngưỡng đưa ra cần xuất phát từ SLO, baseline hoặc mục tiêu điều tra, không tùy tiện chọn sau khi đã thấy kết quả.

Phải xác định cả cách tính request lỗi trong phân vị độ trễ: có hệ thống chỉ báo latency thành công, nơi khác tính mọi attempt. Nếu bỏ các timeout khỏi histogram thành công, p95 có thể trông rất tốt trong khi error rate tăng mạnh.

## 5. Thiết kế các lần chạy so sánh được

Một thiết kế đơn giản dùng **một biến thay đổi có chủ đích** giữa các lần chạy:

| Run | Artifact | Workload | Cấu hình | Mục tiêu |
| --- | --- | --- | --- | --- |
| A – baseline | Bản khỏe đã biết | Cùng mô hình input/tải | Cấu hình tham chiếu | Ghi hành vi ổn định |
| B – incident | Bản đang điều tra | Giống A ở các trục có liên quan | Giống A, trừ khác biệt đang kiểm tra | Xác minh triệu chứng |
| C – hypothesis | Bản như B | Giống B | Chỉ thay một yếu tố nghi vấn | Kiểm tra giả thuyết |
| D – verify | Bản có biện pháp sửa | Giống B | Cấu hình dự định triển khai | Kiểm chứng hiệu quả và hồi quy |

Nếu không thể chỉ thay một biến (ví dụ môi trường production khác staging), liệt kê khác biệt còn lại và đánh giá chúng có làm yếu kết luận hay không. Đừng gọi khác biệt đó là “đã loại trừ” khi chưa đo.

**Ví dụ giả định:** API xử lý ổn ở 40 RPS nhưng lỗi timeout tăng khi lên 120 RPS. Thử tăng kết nối DB đồng thời thấy timeout giảm có thể ủng hộ giả thuyết pool nghẽn, nhưng cũng cần xem connection wait time, số kết nối sử dụng, query latency và tác động lên DB. Chỉ “tăng pool thì đỡ” chưa đủ chứng minh nguyên nhân gốc.

Đối với hiện tượng hiếm hoặc race condition, có thể phải thu nhiều thread dump/JFR samples, lặp chạy dài hơn, thử nhiều seed hoặc đồng bộ lịch tác vụ. Khi khó tái hiện, hãy chủ động ghi **mức độ không chắc chắn** và điều kiện quan sát còn thiếu.

## 6. Tiêu chí hoàn thành chẩn đoán: định nghĩa trước, đánh giá sau

Một cuộc chẩn đoán có thể kết thúc theo nhiều trạng thái; không nên dùng một chữ “done” để che mất chênh lệch giữa việc hiểu lỗi và việc sửa lỗi.

### 6.1 Ba mốc khác nhau

| Mốc | Điều gì phải có? | Điều gì chưa được hàm ý? |
| --- | --- | --- |
| **Diagnosis complete** | Triệu chứng, ảnh hưởng và điều kiện xảy ra rõ ràng; bằng chứng đủ để xác nhận nguyên nhân hoặc khoanh vùng với mức tin cậy/giới hạn cụ thể; bước tiếp theo có chủ sở hữu | Chưa chắc đã sửa hoặc hết lỗi |
| **Mitigation verified** | Biện pháp giảm tác động có số đo trước–sau, không tạo sự cố mới rõ ràng; có kế hoạch theo dõi và hoàn tác nếu cần | Chưa chắc nguyên nhân gốc đã được loại bỏ |
| **Fix verified** | Thay đổi sửa đúng nguyên nhân; bài test/kịch bản gây lỗi và workload liên quan qua cổng chấp nhận; theo dõi sau triển khai và kiểm tra hồi quy phù hợp | Không có nghĩa hệ thống tuyệt đối không bao giờ lỗi |

Nếu **chưa xác minh được nguyên nhân**, kết quả hợp lệ có thể là “điều tra đang mở, đã có bằng chứng và giả thuyết ưu tiên”. Không nâng thành `Diagnosis complete` chỉ vì đã hết thời gian hoặc không còn tái hiện được tạm thời.

### 6.2 Checklist “đủ để khép chẩn đoán”

1. **Phạm vi đã xác định:** tình huống lỗi, môi trường, build và điều kiện kích hoạt được ghi thành runbook.
2. **Bằng chứng có thể truy vết:** mỗi kết luận quan trọng chỉ tới metric query, trace/log ID, dump/test output, timestamp và run ID.
3. **Đã tái hiện hoặc giải thích giới hạn tái hiện:** tần suất và điều kiện rõ; nếu chưa tái hiện, evidence hiện trường và độ không chắc chắn được nêu.
4. **Giả thuyết đã được kiểm chứng:** mô tả phép thử hoặc đối chiếu nào ủng hộ/bác bỏ từng giả thuyết; tránh kết luận chỉ từ tương quan.
5. **Nguyên nhân và cơ chế được mô tả:** lớp gây lỗi (logic, pool, GC, dependency, input, cấu hình, tài nguyên...) với mức tin cậy phù hợp.
6. **Tiêu chí kiểm chứng hành động đã có:** ngưỡng, workload, số lần chạy và môi trường cần dùng để xác nhận bản sửa.
7. **Bàn giao rõ:** người xử lý, thay đổi dự kiến, rủi ro còn lại, quy trình theo dõi hoặc quyết định giữ điều tra mở.

Khi mục tiêu chỉ là **xác định nguyên nhân**, không bắt buộc đợi fix triển khai mới đóng bước chẩn đoán; phải ghi trạng thái remediation riêng. Khi mục tiêu là **khôi phục dịch vụ hoàn toàn**, cần thêm cổng xác minh fix và giám sát.

### 6.3 Tiêu chí định lượng cho một kịch bản đo

Một tiêu chí tốt đủ cụ thể để trả lời PASS/FAIL và có điều kiện áp dụng.

Ví dụ **minh họa, không phải SLO khuyến nghị chung**:

```text
Service: checkout-service, bản build và JDK đã ghi
Workload: 100 RPS yêu cầu, 70% read / 30% checkout,
          payload theo bộ dữ liệu mẫu cố định
Phát tải: open model, ramp 2 phút
Warm-up: 3 phút; cửa sổ đo: 10 phút
Lặp lại: tối thiểu 3 lần độc lập, cùng mô hình và trạng thái đầu
Nguồn đo: client metrics + server metrics + traces gắn run ID
Cửa kiểm tra: p95 < 300 ms; HTTP 5xx và timeout < 1%
                 throughput hoàn tất không tụt dưới mục tiêu đo;
                 không có queue tăng mãi trong khoảng ổn định
Nguyên tắc tính: latency của request thành công và lỗi
                 được ghi riêng, lỗi không bị bỏ khỏi error rate
Điều kiện so sánh: số instance, dữ liệu, JVM flags,
                   dependency và resource limits tương đương
Đầu ra: bảng từng run, metric query, trace ID và sai lệch
Dừng an toàn: ngắt tải khi ảnh hưởng dịch vụ hoặc tài nguyên
               vượt ngưỡng đã thống nhất
```

Các giá trị như `100 RPS`, `300 ms`, `1%` phải được thay bằng ngưỡng của hệ thống thực. Nếu không đạt được 100 RPS đầu vào vì bộ phát tải chậm hoặc môi trường không đủ, không nên đánh dấu PASS dựa trên một p95 “đẹp” ở mức tải thấp hơn.

**Đừng ép mọi hiện tượng vào tiêu chí latency/error.** Với memory leak, tiêu chí có thể là heap used sau full/major GC hoặc heap ổn định trong một khoảng quan sát đủ dài dưới cùng workload. Với deadlock, tiêu chí có thể là không còn đồ thị chờ khóa theo mẫu tái hiện và toàn bộ tác vụ hoàn tất trong deadline. Với dữ liệu sai, tiêu chí là assertions về correctness, không phải p95.

## 7. Ví dụ Java 17+: kiểm tra tiêu chí bằng số liệu cố định

Ví dụ tự chạy sau đây **không phải công cụ benchmark hay bộ phát tải**. Nó cho thấy cách biến một tiêu chí định lượng thành phép tính có thể kiểm tra, tách trạng thái baseline và incident. Mỗi lần chạy dùng **20 mẫu cố định được mô phỏng trong code**; kết quả hoàn toàn xác định. Hai mươi mẫu quá ít để kết luận p95 có ý nghĩa thống kê cho production.

Tạo tệp `DiagnosticCriteriaDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class DiagnosticCriteriaDemo {
    record Sample(int latencyMs, boolean error) { }

    record Metrics(int total, int errors, int p95Ms) {
        double errorRate() {
            return (double) errors / total;
        }
    }

    static List<Sample> samples(boolean incident) {
        List<Sample> result = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            int latency = (incident && i >= 18)
                    ? 600
                    : 100 + (i % 5) * 10;
            boolean error = incident && i == 19;
            result.add(new Sample(latency, error));
        }
        return result;
    }

    static Metrics summarize(List<Sample> samples) {
        if (samples.isEmpty()) {
            throw new IllegalArgumentException("empty samples");
        }

        int[] latencies = samples.stream()
                .mapToInt(Sample::latencyMs)
                .sorted()
                .toArray();
        int errors = (int) samples.stream()
                .filter(Sample::error)
                .count();

        // Nearest-rank p95: ceil(0.95 * n), one-based.
        int index = (int) Math.ceil(0.95 * latencies.length) - 1;
        return new Metrics(samples.size(), errors, latencies[index]);
    }

    static void report(String runId, Metrics m) {
        boolean pass = m.p95Ms() <= 200 && m.errorRate() <= 0.01;
        System.out.printf(Locale.ROOT,
                "%s: n=%d errors=%d errorRate=%.1f%% p95=%dms verdict=%s%n",
                runId, m.total(), m.errors(), m.errorRate() * 100,
                m.p95Ms(), pass ? "PASS" : "FAIL");
    }

    public static void main(String[] args) {
        report("baseline", summarize(samples(false)));
        report("incident", summarize(samples(true)));
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên:

```bash
javac DiagnosticCriteriaDemo.java
java DiagnosticCriteriaDemo
```

Stdout chính xác:

```text
baseline: n=20 errors=0 errorRate=0.0% p95=140ms verdict=PASS
incident: n=20 errors=1 errorRate=5.0% p95=600ms verdict=FAIL
```

Vì sao kết quả đúng?

- Baseline có 20 mẫu với độ trễ lần lượt thuộc `100, 110, 120, 130, 140 ms`, mỗi giá trị xuất hiện bốn lần. Vị trí nearest-rank p95 là vị trí thứ 19 (đếm từ 1), bằng `140 ms`; không có lỗi.
- Incident có 18 mẫu nhỏ và hai mẫu `600 ms`. Vị trí thứ 19 là `600 ms`; một mẫu đánh dấu lỗi nên error rate là `1/20 = 5%`.
- Quy tắc minh họa đặt `p95 <= 200 ms` **và** `error rate <= 1%`. Baseline PASS, incident FAIL.
- Chương trình tính latency percentile trên **mọi mẫu, gồm mẫu được đánh dấu error**. Trong hệ thống thực, cần nêu rõ quy tắc này và thường báo thêm latency thành công riêng để không che timeout.

**Giới hạn quan trọng:** code này *không* sinh 100 RPS, không tạo concurrency thật, không đo thời gian xử lý, không mô phỏng JIT, GC hay network. Nó chỉ kiểm tra một tiêu chí trên tập dữ liệu biết trước. Khi chạy benchmark thực, phải thay `samples(...)` bằng dữ liệu được thu từ đúng cửa sổ đo, giữ cả request lỗi, kết hợp evidence JVM/dependency và lặp đủ số lần.

## 8. Ví dụ đầy đủ: đi từ báo cáo timeout tới hợp đồng đo

Giả sử có báo cáo: “Sau khi tăng tải, `POST /checkout` timeout nhiều hơn.” Hãy thực hiện theo thứ tự sau, với các số bên dưới chỉ là **kịch bản minh họa**.

### Bước 1: Định nghĩa triệu chứng

- API `POST /checkout` trả timeout khi tải tăng; cần xác minh tỷ lệ timeout, latency và giới hạn client deadline.
- Ghi phiên bản, khu vực, instance và timestamp cụ thể. Gắn request ID để nối client, gateway, application và database trace.
- Không tự kết luận “GC bị lỗi” hoặc “thiếu connection” ở bước này.

### Bước 2: Dựng tình huống tái hiện

- Dùng bộ dữ liệu thử với kích thước đã ghi, không chứa thông tin khách hàng thật.
- Ghi `JDK 17`, artifact image digest, `-Xmx` và cấu hình timeout/pool nếu có liên quan.
- Với cùng trạng thái dữ liệu đầu, lần lượt thử 20, 60, 100 RPS, mỗi mức có warm-up và cửa sổ đo được ghi. Nếu đổi workload giữa các lần, ghi rõ sự khác biệt đó.
- Đo RPS yêu cầu và hoàn tất, p95/p99, 5xx/timeout, connection pool wait, DB latency, GC pause và CPU. Ghi run ID cho từng mức.

### Bước 3: Kiểm chứng giả thuyết

Giả sử ở mức 100 RPS, p95 tăng cùng pool wait và số connection đang dùng chạm giới hạn. Đó là **dấu hiệu ủng hộ** giả thuyết pool nghẽn, chưa phải bằng chứng duy nhất. Kiểm tra thêm query slow, transaction kéo dài, timeout phía DB và queueing; nếu điều chỉnh pool ở test environment, giữ các yếu tố còn lại tương đương và đo tác dụng lên database.

### Bước 4: Khép kết luận có căn cứ

Một kết luận tốt sẽ ghi:

```text
Triệu chứng: tăng timeout ở POST /checkout khi tải >= [mức đo]
Điều kiện: build/JDK/config/dataset/run ID cụ thể
Bằng chứng: trace [ID], pool wait [metric], error rate [metric]
Giả thuyết được xác nhận/bác bỏ: [kết luận và phép thử]
Giới hạn: [yếu tố chưa đo hoặc khác biệt môi trường]
Quyết định: [hướng sửa hoặc mitigation, chủ sở hữu]
Cửa xác minh: [workload, số lần lặp, latency, lỗi, tài nguyên]
Trạng thái: diagnosis / mitigation / fix verified, ghi rõ từng mốc
```

Không nên kết thúc bằng “đã thấy pool đầy nên tăng pool”. Tăng pool có thể che triệu chứng hoặc tạo quá tải cho DB. Mục tiêu là tìm cơ chế gây nghẽn rồi kiểm chứng biện pháp tương ứng.

## 9. Các lỗi thường gặp khi xác định kịch bản và tiêu chí

**1. Không có oracle lỗi.** “Chạy xong thì xem có vẻ chậm không” không thể so sánh giữa các run. Định nghĩa mã lỗi, độ trễ, kết quả sai, deadline, hàng đợi hoặc trạng thái thread cụ thể.

**2. Chỉ ghi tổng request.** 10.000 request rải trong 30 phút rất khác burst 10.000 request trong 10 giây. Ghi lịch phát, mix, concurrency, input, warm-up và thời lượng.

**3. Đổi nhiều biến cùng lúc.** Vừa tăng `-Xmx`, đổi query, tăng pool và giảm tải rồi thấy hết lỗi thì không biết yếu tố nào có tác dụng. Dùng các run có kiểm soát và ghi sự khác biệt.

**4. So baseline khác điều kiện.** Bản khỏe được đo với cache nóng trên máy 8 CPU, bản lỗi dùng cache lạnh trên container 2 CPU; so p95 trực tiếp có thể đưa tới kết luận sai.

**5. Chỉ xem request thành công.** Timeout tăng nhưng histogram chỉ chứa response 200 khiến p95 trông thấp. Báo cả error/timeout và chính sách tính latency.

**6. Nhầm độ đồng thời với tốc độ đến.** Dùng số virtual user làm RPS mà không đo throughput thực tế; kết luận tải tương đương trong khi nó không tương đương.

**7. Thu một lần rồi khái quát.** Hiện tượng phụ thuộc JIT, GC, race, cache hoặc network có độ biến thiên. Lặp lại, ghi phân phối và mức tin cậy, đặc biệt với p99 hay lỗi hiếm.

**8. Quên yếu tố gây nhiễu từ công cụ đo.** Profiler, verbose logging, heap dump và load generator đều có thể làm lệch thời gian hoặc tải; ghi cấu hình quan sát và chi phí của nó. Chạy test tải ở môi trường có kiểm soát và dừng khi vượt giới hạn an toàn.

**9. Tuyên bố “đã sửa” vì không còn tái hiện một lần.** Một lần PASS ở workload thấp hơn không chứng minh hết lỗi. Chạy đúng kịch bản kích hoạt, đạt đủ số lần lặp và kiểm tra tác dụng phụ.

**10. Không lưu bằng chứng.** Kết luận không đi kèm thời điểm, run ID, metric query và trace/log khó được kiểm toán hoặc tái điều tra.

## 10. Mẫu bàn giao ngắn cho một cuộc điều tra

```text
[SCENARIO]
Issue / impact:
Service + build + JDK + env:
Trigger + preconditions:
Input dataset / seed / payload:
Load model / RPS / concurrency / mix / duration:
Warm-up + measurement window + timezone:
Failure oracle + baseline:
Reproduction k/n runs + run IDs:

[EVIDENCE]
Metrics and query/window:
Trace/log/thread/JFR IDs:
Hypotheses tested, controls, observations:
Root cause or remaining uncertainties:

[EXIT CRITERIA]
Diagnosis evidence gate:
Mitigation validation (if applicable):
Fix verification workload + numerical thresholds:
Regression checks + monitoring window:
Owner / decision / remaining risk:
```

## 11. Câu hỏi tự kiểm tra

1. Vì sao 100 virtual users không đồng nghĩa 100 request/giây? Hai mô hình phát tải open và closed khác nhau thế nào?
2. Lỗi chỉ xảy ra trên production sau 30 phút hoạt động, không tái hiện khi khởi động lại local. Những yếu tố trạng thái và vòng đời nào cần bổ sung vào runbook?
3. Hệ thống báo p95 = 200 ms nhưng 15% request timeout. Vì sao không thể kết luận “đạt mục tiêu latency” nếu không biết mẫu số và cách ghi nhận request lỗi?
4. Bạn đã thay `-Xmx`, tăng DB pool và sửa query trong cùng một lượt; lỗi biến mất. Bạn còn thiếu điều gì để nói đã tìm thấy nguyên nhân?
5. Tiêu chí nào cho phép đánh dấu **diagnosis complete** nhưng **chưa** đánh dấu **fix verified**? Trong trường hợp không tái hiện được, phải ghi giới hạn gì?
6. Nếu một benchmark đặt mục tiêu 100 RPS nhưng server chỉ nhận/hoàn thành 50 RPS, điều gì phải kiểm tra trước khi công nhận kết quả PASS?

**Ghi nhớ:** Trước khi đo, hãy viết rõ **kịch bản và trạng thái tái hiện**, **mô hình tải đầu vào**, **điều kiện xác định lỗi**, **đối chứng tương đương** và **cổng hoàn thành có thể kiểm chứng**. Khi đó log, metrics, traces và dữ liệu JVM mới trở thành bằng chứng giúp ra quyết định, thay vì những ảnh chụp rời rạc.