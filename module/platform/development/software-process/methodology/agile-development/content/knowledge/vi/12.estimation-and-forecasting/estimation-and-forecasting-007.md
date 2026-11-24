# Dự báo từ thông lượng và dữ liệu thời gian hoàn thành

## 1. Vì sao Agile cần dự báo dựa trên dòng công việc?

Một nhóm phát triển nền tảng học trực tuyến có 18 hạng mục trong product backlog mà các bên liên quan muốn hoàn tất trước khi mở chương trình tuyển sinh. Câu hỏi xuất hiện rất tự nhiên:

> “Với năng lực giao hàng hiện tại, nhóm có thể hoàn thành 18 hạng mục vào thời điểm nào? Nếu chỉ còn ba tuần, phạm vi nào khả thi?”

Nhóm có thể trả lời bằng ước lượng từng hạng mục, nhưng vẫn cần đối mặt với bất định: câu hỏi nghiệp vụ đến muộn, lỗi tích hợp, kiểm thử, người dùng yêu cầu điều chỉnh và công việc khẩn cấp. Thay vì chỉ cộng các con số ước lượng, nhóm còn có thể quan sát **bao nhiêu hạng mục thực sự hoàn tất trong mỗi khoảng thời gian** và **mỗi hạng mục mất bao lâu để đi hết luồng công việc**.

Trong module **AGILE_DEVELOPMENT**, đây là một cách dùng dữ liệu để lập kế hoạch thích ứng: kết hợp product backlog, giao phần tăng dần, phản hồi sớm và cải tiến luồng công việc. Dữ liệu không loại bỏ bất định, nhưng giúp nhóm đưa ra dự báo minh bạch, cập nhật được và có căn cứ hơn.

Bài học tập trung vào hai câu hỏi khác nhau:

1. **“Bao nhiêu công việc có thể hoàn tất trước một thời điểm?”** — thường dự báo từ **thông lượng (throughput)**.
2. **“Một hạng mục cần bao lâu để hoàn tất sau khi bắt đầu?”** — thường xem **phân bố cycle time** và **tuổi công việc đang thực hiện (work item age)**.

Hai câu hỏi có thể liên hệ, nhưng **không đồng nhất**. Một nhóm có thể hoàn thành năm hạng mục mỗi tuần trong khi một hạng mục riêng vẫn mất ba tuần để đi qua các hàng đợi. Không nên dùng tốc độ hoàn tất trung bình để khẳng định một story cụ thể sẽ xong vào một ngày nhất định.

## 2. Ước lượng, dự báo và cam kết khác nhau thế nào?

| Khái niệm | Câu hỏi chính | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Ước lượng (estimation)** | Hạng mục có thể cần bao nhiêu công sức, độ phức tạp hoặc thời gian? | Nhóm đánh giá một tích hợp có rủi ro cao hơn việc sửa nhãn giao diện | Có bất định; không phải lời hứa chắc chắn |
| **Dự báo (forecasting)** | Với dữ liệu và giả định hiện có, điều gì *có khả năng* xảy ra? | Dự báo khoảng thời gian để hoàn thành 18 hạng mục | Cần ghi rõ phạm vi, điều kiện và mức tin cậy |
| **Mục tiêu (target)** | Tổ chức muốn đạt điều gì, vào khi nào? | Muốn sẵn sàng cho mùa tuyển sinh | Mục tiêu có thể khác kết quả dự báo |
| **Cam kết (commitment)** | Điều gì được các bên chịu trách nhiệm thống nhất thực hiện? | Trong Scrum, Sprint Goal là commitment của Sprint Backlog | Không nên giả vờ dự báo chắc chắn chỉ vì có áp lực thời hạn |

Một mốc kinh doanh quan trọng có thể không thay đổi; khi đó nhóm cần thảo luận **phạm vi, thứ tự ưu tiên, cách giảm rủi ro và chất lượng bắt buộc**, thay vì sửa số liệu dự báo cho khớp ngày mong muốn.

**Dự báo là một công cụ quyết định**, không phải phép bói toán. Một câu trả lời hữu ích thường có dạng:

> “Với 18 hạng mục có kích thước tương tự lịch sử, nếu tốc độ hoàn thành và lượng việc phát sinh giữ gần mức gần đây, kết quả trung tâm khoảng bốn tuần; để trao đổi xác suất hoàn thành trước từng mốc, chúng ta cần mô phỏng hoặc xem phân bố lịch sử. Dự báo sẽ được cập nhật hằng tuần.”

Tuyên bố “18 hạng mục chắc chắn xong sau bốn tuần” không được hỗ trợ chỉ bằng phép chia trung bình.

## 3. Những chỉ số dòng công việc cần hiểu đúng

### 3.1. Bốn chỉ số nền tảng

| Chỉ số | Ý nghĩa | Đơn vị và cách đọc |
| --- | --- | --- |
| **Throughput — Thông lượng** | Số hạng mục **hoàn tất** trong một đơn vị thời gian | Ví dụ: 5 hạng mục/tuần |
| **Cycle time — Thời gian chu kỳ** | Thời gian từ mốc **bắt đầu thực hiện** đến mốc **hoàn tất** đã định nghĩa | Ví dụ: 6 ngày làm việc/hạng mục |
| **Work Item Age — Tuổi công việc** | Thời gian đã trôi qua từ mốc bắt đầu đến hiện tại đối với **hạng mục chưa hoàn tất** | Ví dụ: một hạng mục đang làm được 9 ngày |
| **Work in Progress (WIP)** | Số hạng mục đang nằm trong phạm vi công việc đã bắt đầu nhưng chưa hoàn tất | Ví dụ: đang có 7 hạng mục trong luồng |

Nhóm cũng có thể đo **lead time** từ mốc tiếp nhận yêu cầu đến khi đáp ứng nhu cầu hoặc giao hàng. Điểm bắt đầu của lead time thường sớm hơn điểm bắt đầu của cycle time, nhưng các tổ chức có thể chọn ranh giới khác nhau. Vì vậy, **phải công bố rõ cách đo**, không suy rằng hai chỉ số luôn giống hoặc khác nhau một khoảng cố định.

### 3.2. Định nghĩa “bắt đầu” và “hoàn tất” trước khi đo

Ví dụ cho luồng xử lý user story:

~~~mermaid
flowchart LR
    A["Backlog: chưa bắt đầu"] --> B["Đang thực hiện"]
    B --> C["Review và kiểm thử"]
    C --> D["Đạt Definition of Done"]
    D --> E["Phát hành khi phù hợp"]
    C -->|"Cần sửa"| B
~~~

Nếu nhóm chọn **bắt đầu** ở lúc story chuyển vào “Đang thực hiện” và **hoàn tất** ở lúc đáp ứng Definition of Done (DoD), cycle time phải được đo nhất quán giữa hai mốc đó. Một nhóm khác có thể đo thời gian từ lúc khách hàng yêu cầu đến khi phát hành; chỉ số đó trả lời câu hỏi khác.

Trong Scrum, Increment cần đáp ứng **Definition of Done**. Không nên đếm một story là hoàn tất khi chỉ “code xong” nhưng chưa kiểm thử hoặc tích hợp đúng tiêu chuẩn. Một Increment Done không bắt buộc phải được phát hành công khai ngay lập tức; nếu người hỏi muốn dự báo **ngày khách hàng sử dụng được**, cần tính thêm những bước phát hành hoặc phê duyệt nằm sau mốc Done.

Những điều cần thống nhất trong quy tắc dữ liệu:

- Một hạng mục được đếm **một lần** ở mốc hoàn tất, không cộng thêm mỗi khi bị mở lại.
- Throughput theo tuần sử dụng các tuần có độ dài và lịch làm việc so sánh được.
- Các trạng thái “Blocked” vẫn nằm trong phạm vi cycle time nếu hạng mục đã bắt đầu và chưa Done; đừng âm thầm bỏ thời gian chờ.
- Hạng mục chưa hoàn tất không có cycle time đầy đủ; phải xem **work item age** để không bỏ quên công việc tồn lâu.
- Các loại công việc (tính năng, lỗi, nghiên cứu, bảo trì) phải được phân nhóm rõ khi cách hoàn tất khác nhau.
- Nếu story lớn được chia nhỏ hoặc quy tắc Done thay đổi, chuỗi số liệu có thể không còn so sánh trực tiếp.

### 3.3. Đếm theo hạng mục, không theo số dòng mã

Throughput thường là **số hạng mục được hoàn tất**. Một chuyện quan trọng: hạng mục không đồng kích thước. Một story xử lý toàn bộ thanh toán có thể khác xa một lỗi sửa văn bản.

Vì vậy, dự báo từ throughput đáng tin hơn khi:

1. Hạng mục được chia tương đối nhất quán theo **lát cắt giá trị**.
2. Đơn vị đếm và chính sách “Done” ổn định.
3. Phân bố loại công việc trong tương lai gần giống dữ liệu lịch sử, hoặc đã được phân nhóm/điều chỉnh.
4. Nhóm không tăng số hạng mục bằng cách tách việc giả tạo nhằm “làm đẹp throughput”.

Đếm nhiều task kỹ thuật không nhất thiết chứng minh người dùng nhận được nhiều phần giá trị hơn. Mục đích của chỉ số là **dự báo và cải thiện hệ thống giao hàng**, không phải xếp hạng từng lập trình viên.

## 4. Tạo tập dữ liệu thông lượng lịch sử

Giả sử nhóm hoàn tất số hạng mục theo tuần như sau. Đây là dữ liệu **giả định để thực hành**, tất cả hạng mục được đo bằng cùng định nghĩa Done.

| Tuần | Hạng mục hoàn tất | Ghi chú tình huống |
| --- | ---: | --- |
| 1 | 4 | Nhịp thông thường |
| 2 | 5 | Nhịp thông thường |
| 3 | 3 | Có một sự cố tích hợp |
| 4 | 6 | Nhiều hạng mục nhỏ đã được hoàn tất |
| 5 | 5 | Nhịp thông thường |
| 6 | 4 | Có thời gian hỗ trợ vận hành |
| 7 | 5 | Nhịp thông thường |
| 8 | 4 | Nhịp thông thường |
| **Tổng 8 tuần** | **36** | **Trung bình 4,5 hạng mục/tuần** |

Thông lượng trung bình:

\[
\overline{T}=\frac{4+5+3+6+5+4+5+4}{8}
=\frac{36}{8}=4{,}5\ \text{hạng mục/tuần}
\]

Số 4,5 **không phải tuyên bố nhóm có thể hoàn thành nửa một hạng mục mỗi tuần**; đó là giá trị trung bình trên nhiều tuần. Thực tế mỗi tuần nhóm hoàn tất một số nguyên hạng mục.

Tập dữ liệu cho thấy các mức đã quan sát nằm từ **3 đến 6 hạng mục/tuần**. Đây chưa phải giới hạn chắc chắn của tương lai. Nếu tuần tới xuất hiện sự cố nghiêm trọng, thay đổi nhân sự hoặc backlog có nhiều công việc rất lớn, kết quả có thể nằm ngoài khoảng lịch sử.

### 4.1. Tại sao dùng phân bố thay vì chỉ một trung bình?

Hai nhóm đều có trung bình 5 hạng mục/tuần nhưng có thể khác rất nhiều:

- Nhóm A: 5, 5, 5, 5, 5, 5.
- Nhóm B: 1, 9, 2, 8, 1, 9.

Trung bình bằng nhau, nhưng khả năng dự báo một tuần cụ thể khác nhau. Nhóm B có mức biến động lớn và cần giải thích vì sao: luồng công việc theo lô, hạng mục không đều, phát hành dồn cuối kỳ, phụ thuộc hoặc cách ghi nhận.

Một biểu đồ đường đơn giản theo tuần và một bảng tần suất mức throughput có thể giúp quan sát:

| Throughput mỗi tuần | Số tuần xuất hiện trong ví dụ |
| --- | ---: |
| 3 | 1 |
| 4 | 3 |
| 5 | 3 |
| 6 | 1 |

Nếu dùng dữ liệu để dự báo theo tuần, cần giữ cả những tuần ít hoàn thành. **Bỏ tuần có sự cố khỏi chuỗi số liệu chỉ vì “không điển hình”** có thể làm dự báo lạc quan giả tạo, trừ khi đã có lý do và mô hình tách rõ các chế độ vận hành.

## 5. Dự báo khi nào hoàn tất một nhóm hạng mục

### 5.1. Phép tính trung tâm đơn giản

Giả sử hiện có **18 hạng mục** đã được làm rõ, và nhóm dự định hoàn tất toàn bộ. Nếu thông lượng trung bình tương lai giống mức 4,5 hạng mục/tuần:

\[
\text{Thời lượng trung tâm gần đúng}
=\frac{\text{Số hạng mục cần hoàn tất}}{\text{Thông lượng trung bình}}
=\frac{18}{4{,}5}=4\ \text{tuần}
\]

Phép chia này hữu ích để **ước lượng quy mô lịch giao**, nhưng cần nhắc rõ các điều kiện:

- 18 hạng mục không bị thêm bớt, hoặc việc thêm bớt được xử lý trong bản cập nhật dự báo.
- Quy tắc Done, cách chia hạng mục, nhóm người và năng lực vận hành tương đối ổn định.
- Throughput đo được phản ánh cả kiểm thử, tích hợp, sửa lỗi và sự cố thông thường.
- Không có phụ thuộc mới nghiêm trọng khiến nhiều hạng mục đồng thời bị chặn.
- Mức biến động được chấp nhận; bốn tuần không phải bảo đảm xác suất 100%.

**Quan trọng:** Kết quả của \(\text{số việc}/\text{throughput trung bình}\) chỉ là **tỷ số của hai giá trị**, không nhất thiết bằng thời gian hoàn tất trung bình được mô phỏng khi tính đến sự biến động và làm tròn theo tuần. Không nên tự gắn cho phép tính này nhãn “P50” hoặc “85% chắc chắn”.

### 5.2. So sánh kịch bản theo thông lượng đã quan sát

Với cùng 18 hạng mục:

| Thông lượng giả định | Thời gian theo phép chia | Cách diễn giải |
| --- | ---: | --- |
| 6 hạng mục/tuần | 3 tuần | Kịch bản tốc độ bằng tuần tốt nhất đã quan sát |
| 4,5 hạng mục/tuần | 4 tuần | Kịch bản tốc độ bằng trung bình lịch sử |
| 3 hạng mục/tuần | 6 tuần | Kịch bản tốc độ bằng tuần thấp nhất đã quan sát |

Các mức **3–6 tuần** chỉ là **kịch bản minh họa**, không phải khoảng tin cậy thống kê. Một chuỗi tuần tương lai có thể chậm hơn 3 hạng mục/tuần hoặc nhanh hơn 6; backlog có thể lớn lên, và số lượng cần hoàn tất có thể thay đổi.

Nếu người liên quan hỏi “Có thể giao trong ba tuần không?”, dữ liệu gợi ý phải duy trì **6 hạng mục/tuần trong cả ba tuần**, tức liên tiếp đạt mức tốt nhất trong mẫu lịch sử. Đó là mục tiêu rủi ro hơn phép chia trung bình, không thể chỉ trả lời “có” vì đã từng có một tuần đạt 6.

### 5.3. Dự báo từ thời hạn cố định

Đảo lại câu hỏi: nếu chỉ còn **4 tuần**, nhóm có thể hoàn tất khoảng bao nhiêu hạng mục?

\[
\text{Sản lượng trung tâm gần đúng}
=4\ \text{tuần}\times4{,}5\ \text{hạng mục/tuần}
=18\ \text{hạng mục}
\]

Kết quả này giúp thảo luận **phạm vi**. Ví dụ, nếu backlog có 26 hạng mục nhưng hạn giao còn bốn tuần, không nên mặc định cả 26 sẽ hoàn tất. Nhóm có thể xác định 18 hạng mục ưu tiên cao theo giả định trung tâm, làm rõ rủi ro và chuẩn bị phương án điều chỉnh. Tuy nhiên, **18 vẫn không phải cam kết chắc chắn**.

Trong Agile, nên ưu tiên **giá trị và các lát cắt có thể sử dụng**, không chọn hạng mục chỉ để đủ số lượng. Một lỗi bảo mật nghiêm trọng hoặc khả năng thanh toán cốt lõi có thể cần ưu tiên dù làm giảm tổng số hạng mục được đếm.

## 6. Dự báo theo xác suất bằng mô phỏng Monte Carlo

Khi muốn trả lời câu hỏi “**Có bao nhiêu phần trăm khả năng hoàn tất trước ngày X?**”, việc lấy trung bình rồi gắn nhãn xác suất là sai phương pháp. Một cách phổ biến là dùng **mô phỏng Monte Carlo dựa trên dữ liệu lịch sử**.

Ý tưởng cơ bản: xem từng tuần throughput lịch sử là một mẫu đại diện có thể xuất hiện trong tương lai; lấy mẫu ngẫu nhiên nhiều lần, cộng dồn cho đến khi hoàn tất số hạng mục mong muốn, rồi xem phân bố số tuần cần dùng.

### 6.1. Các bước mô phỏng cho 18 hạng mục

**Đầu vào minh họa:**

~~~text
Thông lượng tuần lịch sử: [4, 5, 3, 6, 5, 4, 5, 4]
Số hạng mục còn lại: 18
Số lần mô phỏng đề xuất: 10.000
Đơn vị thời gian: tuần
~~~

**Giả mã mô phỏng:**

~~~text
history = [4, 5, 3, 6, 5, 4, 5, 4]
remaining_items = 18
results = []

repeat 10_000 times:
    completed = 0
    weeks = 0
    while completed < remaining_items:
        sample = random_choice_with_replacement(history)
        completed = completed + sample
        weeks = weeks + 1
    results.append(weeks)

sort(results)
report(percentile(results, 50))
report(percentile(results, 85))
report(percentile(results, 95))
~~~

Đây là **giả mã để giải thích ý tưởng**, không phải một chương trình đã chạy hay kết quả mô phỏng thật. Mỗi lượt mô phỏng giả định mức throughput của một tuần được rút từ các quan sát lịch sử **có hoàn lại**, tức cùng một giá trị có thể xuất hiện nhiều tuần.

**Cách đọc đầu ra khi đã chạy mô phỏng:**

- **P50 của số tuần:** Khoảng một nửa kịch bản mô phỏng hoàn tất không muộn hơn mốc này.
- **P85 của số tuần:** Khoảng 85% kịch bản mô phỏng hoàn tất không muộn hơn mốc này, theo mô hình đã dùng.
- **P95 của số tuần:** Mốc thận trọng hơn, đổi lại thường có thời gian dài hơn.

Không được diễn giải “P85” thành **cam kết rằng xác suất thực tế đúng chính xác 85%**. Mô phỏng phụ thuộc các giả định về tính đại diện của dữ liệu, mức độc lập giữa tuần, backlog, năng lực và thay đổi hệ thống.

### 6.2. Vì sao không nên tự gắn xác suất từ mẫu nhỏ?

Tám tuần dữ liệu là ví dụ phù hợp để học phép tính, nhưng chưa đủ để mô tả đáng tin cậy mọi biến cố. Có thể có mùa cao điểm, tuần nghỉ lễ, đợt bảo trì lớn hoặc sự cố hiếm chưa từng xuất hiện.

Ngay cả mô phỏng 10.000 lần cũng **không tạo ra 10.000 tuần quan sát độc lập**: các lượt đó chỉ tổ hợp lại tám tuần đã có. Tăng số lần chạy giúp kết quả tính toán ổn định hơn dưới mô hình, **không khắc phục được việc mẫu lịch sử không đại diện**.

Nên ghi vào báo cáo:

- Khoảng thời gian lịch sử được dùng và lý do chọn.
- Định nghĩa “Done” và đơn vị throughput.
- Số hạng mục còn lại, việc đang làm dở, mức thay đổi phạm vi dự kiến.
- Thay đổi năng lực, chính sách WIP hoặc quy trình có thể khiến lịch sử không còn tương đồng.
- Các kết quả P50/P85/P95 **chỉ sau khi mô phỏng thực sự được thực hiện**, không bịa số hoặc xem chúng là bảo đảm.

### 6.3. Hai câu hỏi mô phỏng cần phân biệt

| Câu hỏi | Đầu vào cố định | Kết quả mô phỏng |
| --- | --- | --- |
| **When — Khi nào xong?** | Số hạng mục cần hoàn tất, phân bố throughput lịch sử | Phân bố số tuần cần để hoàn tất |
| **How many — Xong bao nhiêu?** | Số tuần còn lại, phân bố throughput lịch sử | Phân bố số hạng mục có thể hoàn tất trong thời hạn |

Không được dùng kết quả “P85 của số tuần cần hoàn tất 18 hạng mục” thay thế trực tiếp cho “P85 số hạng mục hoàn tất trong bốn tuần”. Hai bài toán có **biến đầu ra khác nhau**, cần mô phỏng và diễn giải đúng.

## 7. Cycle time: dự báo thời gian hoàn thành một hạng mục

Thông lượng trả lời về **tập hạng mục**. Với một hạng mục đã bắt đầu, người liên quan có thể muốn biết: “Story này thường đi hết luồng trong bao lâu?”.

Hãy dùng **phân bố cycle time** của những hạng mục hoàn tất, cùng định nghĩa bắt đầu/kết thúc và cùng loại công việc nếu có thể.

### 7.1. Ví dụ dữ liệu cycle time

Giả sử 12 hạng mục cùng loại đã hoàn tất có cycle time tính theo **ngày làm việc**, sắp xếp tăng dần:

~~~text
2, 3, 4, 4, 5, 5, 6, 6, 7, 8, 9, 14
~~~

| Thống kê mô tả | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Số hạng mục | 12 | Quy mô mẫu nhỏ, chỉ để minh họa |
| Nhỏ nhất | 2 ngày | Hạng mục nhanh nhất trong mẫu |
| Trung vị (median) | 5,5 ngày | Trung bình của giá trị ở vị trí 6 và 7 trong 12 quan sát |
| Trung bình | \(73/12\approx6{,}08\) ngày | Bị kéo lên bởi hạng mục 14 ngày |
| P85 theo cách **nearest-rank** | 9 ngày | Quan sát tại vị trí \(\lceil0{,}85\times12\rceil=11\) |
| P95 theo cách **nearest-rank** | 14 ngày | Quan sát tại vị trí \(\lceil0{,}95\times12\rceil=12\) |

**Lưu ý về phân vị:** Có nhiều phương pháp ước lượng percentile, nên công cụ thống kê khác có thể cho số khác với cách **nearest-rank** ở mẫu nhỏ. Khi dùng một con số trong báo cáo hoặc Service Level Expectation, hãy ghi rõ phương pháp tính và khung dữ liệu.

Trong 12 quan sát này, có **11 hạng mục hoàn tất trong không quá 9 ngày**, còn một hạng mục mất 14 ngày. Nói “P85 khoảng 9 ngày trong mẫu” là cách mô tả lịch sử theo phương pháp đã chọn; **không bảo đảm hạng mục tiếp theo sẽ xong trong 9 ngày với xác suất đúng bằng 85%**.

### 7.2. Vì sao chỉ nhìn trung bình dễ gây hiểu nhầm?

Nếu nhóm chỉ báo “cycle time trung bình 6 ngày”, một người có thể ngộ nhận rằng phần lớn story sẽ xong đúng ngày thứ sáu. Nhưng dữ liệu có một hạng mục kéo dài 14 ngày; phân bố không đối xứng.

Trung vị, các phân vị cao hơn và biểu đồ phân bố giúp diễn đạt rõ mức biến động. **Phân vị cao không phải hạn chót phải ép mọi hạng mục đạt bằng mọi giá**. Nó là cơ sở nhận diện rủi ro và trao đổi kỳ vọng.

Khi chọn dữ liệu nên cân nhắc:

- Hạng mục nào đủ giống nhau về loại, kích thước và điều kiện hoàn tất?
- Số lượng mẫu có đủ lớn để ước lượng phân vị ổn định không?
- Có thay đổi lớn nào về nhóm, quy trình, môi trường hoặc cách đo?
- Có hạng mục bị chặn rất lâu chưa hoàn tất và do đó chưa xuất hiện trong tập cycle time hoàn thành?
- Có cần đo theo ngày làm việc hay ngày lịch, và điểm bắt đầu đã được xác định giống nhau?

## 8. Service Level Expectation và tuổi công việc đang làm

Trong quản lý dòng chảy, nhóm có thể thiết lập **Service Level Expectation (SLE)**: một kỳ vọng dựa trên dữ liệu về thời gian một hạng mục cần để đi hết luồng, thường được diễn đạt bằng **thời gian và xác suất/khoảng tỷ lệ dự kiến**.

Ví dụ:

> “Đối với loại hạng mục tính năng nhỏ với ranh giới từ lúc bắt đầu phát triển đến lúc đạt Done, chúng tôi đang dùng kỳ vọng khoảng **85% hoàn tất trong không quá 9 ngày làm việc**, dựa trên số liệu lịch sử hiện có. Mẫu này còn nhỏ và sẽ được cập nhật.”

Đây là **ví dụ về cách phát biểu SLE**, không phải chỉ tiêu bắt buộc của mọi nhóm. Nếu chỉ có 12 hạng mục như mẫu trên, hãy nói rõ mức tin cậy của ước lượng còn hạn chế và không biến con số đó thành điều khoản bảo đảm.

### 8.1. Work item age giúp phát hiện sớm việc có nguy cơ chậm

**Cycle time** chỉ tính đầy đủ khi một hạng mục đã Done. **Work item age** đo từ lúc bắt đầu đến *hiện tại* cho hạng mục còn đang làm.

Giả sử có ba hạng mục đang thực hiện:

| Hạng mục | Tuổi hiện tại | So với P85 = 9 ngày của mẫu | Hành động phù hợp |
| --- | ---: | --- | --- |
| A — Sửa thông tin khóa | 2 ngày | Còn trẻ so với mẫu | Theo dõi bình thường, bảo đảm không bị chặn |
| B — Lưu yêu thích | 8 ngày | Gần mốc lịch sử | Kiểm tra hàng chờ review, phụ thuộc, khả năng hoàn tất |
| C — Tích hợp đăng ký | 11 ngày | Đã vượt mốc lịch sử | Tập trung gỡ nghẽn, trao đổi tác động và điều chỉnh ưu tiên |

**Không nên tính “C chắc còn 14 − 11 = 3 ngày”** chỉ vì cycle time dài nhất trong mẫu cũ là 14. Các hạng mục còn tồn tại đã vượt qua một số mốc của phân bố; dự báo thời gian còn lại cần dữ liệu và mô hình phù hợp với **điều kiện đã sống sót đến tuổi hiện tại**, cùng bối cảnh thực tế của hạng mục.

Một thông tin đơn giản như “Story C đã 11 ngày và chưa Done, đang chờ môi trường tích hợp” thường hữu ích hơn lời hứa thiếu căn cứ về đúng ngày hoàn tất.

### 8.2. Tránh thiên lệch chỉ nhìn công việc đã Done

Nếu chỉ tính cycle time của hạng mục hoàn tất trong một tuần, nhóm có thể thấy chỉ số rất đẹp vì toàn bộ hạng mục khó còn tồn trong luồng. Đây là một dạng **thiên lệch chọn mẫu**.

Khi đánh giá khả năng giao hàng, hãy xem đồng thời:

1. Phân bố cycle time của hạng mục đã hoàn tất.
2. Work item age của hạng mục chưa hoàn tất.
3. Số lượng WIP và nơi công việc đang bị chặn.
4. Throughput theo thời gian để biết luồng đang hoàn tất được bao nhiêu.

Cải thiện một chỉ số riêng lẻ không bảo đảm hệ thống đã tốt hơn. Ví dụ, chỉ chọn hạng mục cực nhỏ có thể làm cycle time thấp nhưng backlog có giá trị cao vẫn tồn đọng.

## 9. Mối quan hệ giữa WIP, throughput và cycle time

Trong một hệ thống luồng **đủ ổn định và thỏa mãn các giả định cần thiết**, **Little's Law** diễn đạt mối quan hệ giữa WIP trung bình, tốc độ hoàn tất trung bình và thời gian một hạng mục nằm trong hệ thống:

\[
\text{WIP trung bình}
=\text{Thông lượng trung bình}\times\text{Cycle time trung bình}
\]

Ví dụ *độc lập với dữ liệu ở các phần trên*: một hệ thống có WIP trung bình khoảng **6 hạng mục** và throughput trung bình **3 hạng mục/tuần**. Khi các ranh giới và giả định ổn định được đáp ứng, cycle time trung bình tương ứng xấp xỉ:

\[
\frac{6\ \text{hạng mục}}{3\ \text{hạng mục/tuần}}
=2\ \text{tuần}
\]

Đây là **quan hệ ở mức trung bình dài hạn**, không nói hạng mục nào cũng mất hai tuần và không thể được dùng như công thức dự báo chắc chắn trong hệ thống có biến động lớn.

Các điều kiện phải cân nhắc: cùng ranh giới đo, đơn vị thời gian nhất quán, quá trình đủ ổn định, dòng vào và ra không tạo xu hướng WIP tăng vô hạn, không có cách đếm lại hạng mục hoặc thay đổi quy tắc đo liên tục.

**Giảm WIP có thể giúp giảm thời gian chờ và cycle time**, nhất là khi nhóm đang mở quá nhiều việc. Nhưng không phải cứ giảm WIP một nửa là mọi story chắc chắn nhanh gấp đôi: năng lực và throughput cũng có thể thay đổi khi luồng bị thiếu việc, phụ thuộc bên ngoài hoặc giới hạn kỹ năng.

### Đừng tối ưu WIP bằng cách giấu công việc

Nếu nhóm đổi trạng thái từ “Đang làm” sang “Chưa bắt đầu” chỉ để con số WIP nhỏ đi dù công việc vẫn thực chất đang thực hiện, số liệu sẽ mất ý nghĩa. Chính sách luồng và ranh giới đo cần phản ánh công việc thật.

## 10. Những biến động khiến dự báo cũ không còn phù hợp

Dữ liệu lịch sử là bằng chứng, không phải định luật. Khi điều kiện vận hành thay đổi, nhóm cần cập nhật giả định hoặc chia dữ liệu thành những nhóm so sánh được.

| Thay đổi | Tác động có thể có | Cách xử lý |
| --- | --- | --- |
| Nhóm tăng hoặc giảm người, đổi chuyên môn | Throughput và hàng chờ có thể thay đổi | Dùng dữ liệu mới và xem phụ thuộc kỹ năng |
| Phân rã story nhỏ hơn nhiều | Số item hoàn tất có thể tăng mà giá trị không tăng tương ứng | Chuẩn hóa đơn vị hạng mục hoặc phân nhóm theo loại |
| Definition of Done thay đổi | Số được tính Done không còn tương đồng | Ghi ngày thay đổi, tránh so sánh trực tiếp mà không giải thích |
| Sự cố vận hành tăng đột ngột | Năng lực cho backlog giảm, WIP có thể bị chặn | Phân loại sự cố, cập nhật dự báo và chính sách ưu tiên |
| Phần mềm mới có nhiều tích hợp phức tạp | Cycle time có thể dài hơn lịch sử tính năng đơn giản | Dự báo riêng cho loại công việc hoặc mô hình rủi ro |
| Tự động hóa kiểm thử và CI ổn định hơn | Luồng có thể cải thiện, nhưng cần thời gian quan sát | Theo dõi mẫu sau cải tiến, không áp lịch sử cũ mãi |
| Ngày nghỉ, mùa cao điểm, thay đổi thị trường | Lượng việc mới hoặc thời gian khả dụng thay đổi | Dự báo theo lịch thực tế, tránh coi mọi tuần tương đương |
| Backlog liên tục được bổ sung | Mốc hoàn thành toàn bộ backlog có thể lùi mãi | Tách phạm vi mục tiêu đã thống nhất khỏi mọi yêu cầu mới |

### 10.1. “Bao giờ hết backlog?” có thể là câu hỏi không phù hợp

Product Backlog là danh sách phát triển theo điều nhóm học được. Nó có thể được bổ sung, loại bỏ hoặc sắp thứ tự lại sau phản hồi người dùng. Nếu mỗi tuần xuất hiện năm hạng mục mới trong khi throughput trung bình là bốn hạng mục/tuần, **số lượng backlog có xu hướng tăng**; việc dự báo “ngày xong toàn bộ backlog” có thể không mang ý nghĩa.

Một câu hỏi tốt hơn:

> “Khi nào chúng ta có thể hoàn thành **nhóm hạng mục cần thiết cho phiên bản tuyển sinh**, với các điều kiện chất lượng và ranh giới phạm vi đã thống nhất?”

Khi phạm vi thay đổi, cần tính lại số việc còn lại; giữ bản ghi giả định để tránh việc hai bên trao đổi trên hai backlog khác nhau.

### 10.2. Tách luồng cho các loại hạng mục thật khác nhau

Thông lượng tổng có thể bao gồm sửa lỗi nhỏ, yêu cầu hỗ trợ, tính năng lớn và nghiên cứu. Nếu bản phát hành mới chỉ có những tích hợp phức tạp, lấy số item tổng rồi chia trung bình có thể lạc quan.

Có thể:

- Tạo phân loại theo **loại công việc và quy tắc Done tương đồng**.
- Đánh giá kích thước story và chia hạng mục thành phần giá trị nhỏ, tương đối nhất quán.
- Mô phỏng riêng theo nhóm hoặc bổ sung giả định năng lực, nhưng không phân nhóm quá nhỏ khiến mỗi nhóm có ít dữ liệu.
- Trình bày mức bất định rõ hơn nếu dữ liệu tương đồng không đủ.

Phân nhóm không phải để loại bỏ những tuần “xấu” hoặc hạng mục khó khỏi kết quả. Nó nhằm mô hình hóa **sự khác biệt thực sự có căn cứ**.

## 11. Dùng dữ liệu để cập nhật dự báo theo nhịp Agile

Một quy trình nhẹ có thể dùng hằng tuần hoặc tại thời điểm bổ sung backlog:

~~~mermaid
flowchart TD
    A["Xác định phạm vi và câu hỏi dự báo"]
    B["Lấy dữ liệu Done, throughput, cycle time, WIP, age"]
    C["Kiểm tra chất lượng và tính tương đồng"]
    D["Tính kịch bản hoặc mô phỏng phân bố"]
    E["Trình bày giả định, mốc và mức bất định"]
    F["Trao đổi ưu tiên, phạm vi, rủi ro và năng lực"]
    G["Giao phần tăng dần, nhận phản hồi và cập nhật"]
    A --> B --> C --> D --> E --> F --> G --> B
~~~

### Bước 1 — Xác định câu hỏi cần trả lời

Đừng bắt đầu bằng “hãy xuất biểu đồ đẹp”. Hỏi rõ:

- Dự báo **khi nào hoàn thành N hạng mục** hay **bao nhiêu hạng mục trước ngày X**?
- Đang tính tới mốc **Done**, **phát hành** hay **người dùng đã sử dụng được**?
- Người nhận dự báo cần mốc trung tâm hay cần khoảng phù hợp mức rủi ro của quyết định?
- Phạm vi là toàn bộ backlog thay đổi liên tục hay một nhóm hạng mục có mục tiêu rõ?

### Bước 2 — Thu thập dữ liệu và kiểm tra ranh giới

Lấy ngày bắt đầu/hoàn tất, loại hạng mục, WIP, tuổi công việc, các tuần throughput; kiểm tra trạng thái bị ghi sai, thay đổi workflow, gộp/chia task và sự khác biệt về thời gian nghỉ.

Không có dữ liệu đáng tin thì **chưa nên khẳng định một xác suất giao hàng**. Có thể dùng nhận định của chuyên gia như giả định ban đầu, đồng thời thiết lập đo lường để cập nhật bằng dữ liệu thật.

### Bước 3 — Lập dự báo với giả định phù hợp

- Với số hạng mục cố định: thử **throughput trung bình**, kịch bản và mô phỏng.
- Với thời gian hạng mục: xem **cycle time distribution**, percentiles, work item age.
- Với công việc có WIP cao: tìm nút nghẽn trước khi chỉ dựa vào tỷ lệ hoàn tất.
- Với thay đổi đột ngột: dùng kịch bản năng lực khác nhau hoặc ghi rõ dữ liệu mới còn thiếu.

### Bước 4 — Thảo luận quyết định dựa trên dự báo

Nếu thời hạn ba tuần nhưng phạm vi 18 hạng mục đòi hỏi liên tục đạt tuần cao nhất lịch sử, nhóm có thể:

1. Ưu tiên những lát cắt mang lại giá trị thiết yếu cho người dùng.
2. Chia nhỏ các hạng mục có thể giao độc lập.
3. Giảm WIP và ưu tiên xử lý review/kiểm thử để tăng khả năng hoàn tất.
4. Giải quyết phụ thuộc hoặc rủi ro tích hợp càng sớm càng tốt.
5. Thương lượng phạm vi, thời hạn hoặc nguồn lực với người có thẩm quyền.
6. Giữ **Definition of Done** và các tiêu chuẩn an toàn bắt buộc; không tạo throughput giả bằng cách đổi nghĩa chữ “hoàn tất”.

Không nên tự suy ra rằng “thêm người chắc chắn tăng throughput theo tỷ lệ”, vì onboarding, phụ thuộc kỹ năng và khả năng phối hợp có thể khiến hiệu quả thay đổi chậm.

### Bước 5 — Cập nhật và kiểm tra sai lệch

Mỗi kỳ, xem:

- Số hạng mục thực sự hoàn tất so với phân bố dự báo.
- Câu hỏi sản phẩm hoặc yêu cầu mới nào làm thay đổi phạm vi.
- Công việc nào già đi trong luồng, tại sao còn bị chặn.
- Những thay đổi năng lực hoặc chất lượng làm dữ liệu cũ kém phù hợp.
- Dự báo có đang liên tục quá lạc quan hoặc quá bi quan, và vì sao.

Nếu dự báo lệch, hãy cải thiện **mô hình và hệ thống làm việc**, không sửa số liệu quá khứ hoặc tìm người chịu lỗi chỉ vì tuần vừa rồi có biến động.

## 12. Trình bày dự báo sao cho người liên quan có thể quyết định

Một bản báo cáo dự báo tốt có thể rất ngắn nhưng cần đủ ngữ cảnh:

| Thành phần | Ví dụ minh họa |
| --- | --- |
| **Câu hỏi** | Khi nào hoàn tất 18 hạng mục cốt lõi của luồng đăng ký khóa học? |
| **Mốc Done** | Hạng mục đáp ứng DoD, chưa bao gồm thủ tục phát hành sau đó nếu có |
| **Dữ liệu** | 8 tuần gần nhất: 4, 5, 3, 6, 5, 4, 5, 4 hạng mục hoàn tất/tuần |
| **Thông tin trung tâm** | Trung bình 4,5/tuần; phép chia 18/4,5 cho kết quả 4 tuần |
| **Biến động** | Quan sát trong mẫu có tuần từ 3 đến 6 hạng mục |
| **Giới hạn** | Mẫu nhỏ, phạm vi và cách chia item cần tương đồng; dự báo chưa bao gồm thay đổi lớn |
| **Quyết định cần thiết** | Ưu tiên lát cắt phải có trong bản mở tuyển sinh; xử lý rủi ro tích hợp sớm |
| **Cập nhật** | Xem lại sau mỗi tuần khi có throughput và WIP mới |

Nếu đã chạy mô phỏng, thêm **mốc P50/P85/P95 thực tế** và phương pháp lấy mẫu. Nếu chưa chạy, chỉ trình bày kịch bản hoặc phép tính trung tâm và **nói rõ chưa có xác suất định lượng đáng tin cậy**.

### Cách diễn đạt nên tránh và nên dùng

| Tránh nói | Nên nói |
| --- | --- |
| “Theo tốc độ trung bình, chắc chắn bốn tuần xong.” | “Bốn tuần là phép tính trung tâm theo dữ liệu hiện tại; còn biến động và giả định cần theo dõi.” |
| “85% story sẽ xong trong chín ngày nên story này còn đúng ba ngày.” | “P85 lịch sử là chín ngày; story hiện tại đã tồn lâu cần kiểm tra trạng thái và rủi ro riêng.” |
| “Tuần trước chỉ làm được ba việc nên đội kém hiệu quả.” | “Tuần đó có sự cố tích hợp; cần xem công việc bị chặn, chất lượng và mức biến động trước khi kết luận.” |
| “Tăng velocity là có thể cam kết giao sớm hơn.” | “Cần xem throughput thực tế, chất lượng Done, loại công việc và năng lực để dự báo.” |
| “Đã tăng throughput nên chắc chắn giá trị sản phẩm tăng.” | “Cần kiểm tra phản hồi người dùng và outcome; số hạng mục hoàn tất không tự đo giá trị.” |

## 13. Áp dụng dự báo với Scrum, Kanban và XP

### 13.1. Scrum: dự báo để hỗ trợ mục tiêu, không thay thế Sprint Goal

Trong Scrum, Product Owner chịu trách nhiệm giá trị và thứ tự Product Backlog. Developers chọn các Product Backlog Item trong Sprint Planning qua trao đổi với Product Owner, dựa trên năng lực, hiểu biết về công việc và Definition of Done. Scrum Team cùng tạo Sprint Goal.

Thông lượng và cycle time có thể giúp thảo luận việc gì **có khả năng hoàn tất**, nhưng Scrum **không bắt buộc** dùng số story point, velocity hoặc một phương pháp dự báo duy nhất. **Sprint Goal là commitment**, còn danh sách item được chọn và kế hoạch thực hiện có thể được làm rõ hoặc điều chỉnh phù hợp khi có thông tin mới.

Sprint Review cung cấp cơ hội kiểm tra kết quả và điều chỉnh Product Backlog theo giá trị mới học được; Sprint Retrospective giúp nhóm xem lại nút nghẽn, DoD và độ tin cậy của cách dự báo.

**Lưu ý:** Nếu throughput được tính theo tuần trong khi Sprint dài hai tuần, cần thống nhất cách quy đổi và lấy dữ liệu. Không nên trộn “item/Sprint” với “item/tuần” trong một phép tính.

### 13.2. Kanban: dự báo dòng công việc và Service Level Expectation

Kanban thường chú trọng **WIP, throughput, work item age và cycle time**, cùng chính sách luồng rõ ràng. Dữ liệu này hỗ trợ:

- Dự báo khi nào một nhóm hạng mục có thể hoàn tất.
- Thiết lập kỳ vọng thời gian hoàn thành theo loại công việc.
- Phát hiện hạng mục già đi và hàng chờ cần ưu tiên gỡ nghẽn.
- Điều chỉnh giới hạn WIP, chính sách kéo việc và mức ưu tiên khi công việc khẩn xuất hiện.

Một SLE rõ ràng cần nêu **đơn vị thời gian, xác suất/kỳ vọng và các mốc bắt đầu/kết thúc**. Nó giúp trao đổi với các bên liên quan nhưng không mặc định là bảo đảm theo hợp đồng.

### 13.3. XP: dữ liệu phải phản ánh khả năng giao giá trị có chất lượng

XP nhấn mạnh kiểm thử tự động, tích hợp liên tục, refactoring, phản hồi nhanh và phát hành nhỏ. Những thực hành này có thể giúp giảm hàng chờ, lỗi tích hợp và thời gian giao một lát cắt giá trị.

Dự báo không nên thưởng cho việc bỏ kiểm thử để làm đẹp throughput. Cần đo các hạng mục **thực sự đáp ứng chuẩn hoàn tất**, có thể sử dụng và tạo cơ hội nhận phản hồi.

| Cách tiếp cận | Dữ liệu hữu ích | Quyết định được hỗ trợ |
| --- | --- | --- |
| **Scrum** | Throughput, cycle time, năng lực, số hạng mục Done, trở ngại | Thảo luận phạm vi và rủi ro hướng tới Sprint Goal/Product Goal |
| **Kanban** | Throughput, WIP, work item age, cycle time, SLE | Dự báo dòng chảy, điều chỉnh WIP và chính sách phục vụ |
| **XP** | Luồng hoàn tất, lỗi tích hợp, thời gian phản hồi CI, chu kỳ giao nhỏ | Cải thiện thực hành kỹ thuật để giao phần tăng dần an toàn |

Mỗi cách tiếp cận có trọng tâm riêng; **không nên biến một công thức throughput thành quy định bắt buộc cho mọi framework**.

## 14. Những sai lầm thường gặp khi dự báo

**1. Dùng trung bình như ngày chắc chắn hoàn tất.** Phép chia số hạng mục cho throughput trung bình không tự cung cấp xác suất hoặc mức tin cậy.

**2. Nhầm throughput với velocity.** Throughput đếm hạng mục Done theo thời gian; velocity thường là tổng đơn vị ước lượng hoàn tất trong một Sprint. Hai chỉ số không tương đương và velocity không phải yêu cầu bắt buộc của Scrum.

**3. Đếm việc “code xong” như hoàn tất.** Khi story chưa đạt DoD, số liệu làm lạc quan giả tạo và che khuất hàng chờ kiểm thử/tích hợp.

**4. Thay đổi kích thước hạng mục liên tục nhưng vẫn so sánh số lượng.** Throughput có thể tăng chỉ vì chia task nhỏ hơn, không chứng minh khả năng giao giá trị tăng tương ứng.

**5. Bỏ các tuần có sự cố để làm đẹp dữ liệu.** Những tuần khó khăn có thể là một phần rủi ro vận hành. Chỉ tách dữ liệu khi có giả định và lý do rõ.

**6. Đưa backlog có thêm việc mới vào phép chia như một con số cố định.** Nếu số hạng mục liên tục thay đổi, dự báo hoàn tất toàn bộ backlog cần được cập nhật hoặc xác định lại phạm vi mục tiêu.

**7. Dùng cycle time của item đã Done mà không xem work item age.** Hạng mục chậm đang nằm dở có thể bị bỏ khỏi thống kê, khiến nhóm tưởng mọi việc đều nhanh.

**8. Gắn xác suất tùy tiện cho một khoảng kịch bản.** “3–6 tuần” từ min/max thông lượng lịch sử **không phải** khoảng tin cậy 85% hoặc 95%.

**9. Chạy mô phỏng nhiều lần rồi coi kết quả là chắc chắn.** Số lượt mô phỏng lớn không cứu được dữ liệu đầu vào không đại diện hoặc giả định không còn đúng.

**10. Dùng P85 của cycle time để nói story hiện tại chắc còn vài ngày.** Hạng mục đã tồn lâu cần phân tích trạng thái, các biến cố và thời gian còn lại có điều kiện.

**11. Tối ưu chỉ số thay vì sản phẩm.** Nhóm có thể tăng số item đóng nhưng bỏ qua chất lượng, bảo mật hoặc nhu cầu người dùng.

**12. Giấu bất định vì muốn làm hài lòng người nhận dự báo.** Minh bạch mức tin cậy và phương án thích ứng giúp quyết định tốt hơn một mốc “chắc chắn” không có căn cứ.

## 15. Bài tập tình huống: dự báo cho đợt mở tuyển sinh

Một nhóm phát triển nền tảng học trực tuyến có **18 hạng mục cốt lõi** cần cân nhắc cho bản mở tuyển sinh. Nhóm có dữ liệu Done theo tám tuần:

~~~text
Tuần:        1  2  3  4  5  6  7  8
Hoàn tất:    4  5  3  6  5  4  5  4
~~~

Một mẫu riêng gồm **12 hạng mục cùng loại đã hoàn tất** có cycle time tính theo ngày làm việc:

~~~text
2, 3, 4, 4, 5, 5, 6, 6, 7, 8, 9, 14
~~~

Ngoài ra, một story tích hợp hiện đã **11 ngày làm việc kể từ khi bắt đầu**, vẫn đang chờ review và kiểm tra môi trường. Khách hàng muốn bàn giao toàn bộ 18 hạng mục trong **ba tuần**.

### Câu hỏi

1. Tính tổng throughput và throughput trung bình của tám tuần.
2. Nếu giữ mức trung bình, phép chia đơn giản gợi ý bao nhiêu tuần để hoàn tất 18 hạng mục?
3. Để hoàn tất trong ba tuần, nhóm cần throughput bình quân bao nhiêu mỗi tuần? Điều này có đáng lo theo dữ liệu không?
4. Theo cách tính percentile **nearest-rank**, xác định trung vị, P85 và P95 của 12 cycle time.
5. Có thể khẳng định story đang có tuổi 11 ngày chắc chắn hoàn tất trong ba ngày nữa không? Vì sao?
6. Muốn trình bày xác suất hoàn tất 18 item trước mốc bốn tuần, nhóm cần làm thêm gì?
7. Nếu khách hàng không thể dời thời điểm mở tuyển sinh, nhóm nên thảo luận những phương án nào mà không hạ DoD?

### Gợi ý lời giải

**Câu 1:** Tổng \(4+5+3+6+5+4+5+4=36\) hạng mục. Trung bình \(36/8=4{,}5\) hạng mục/tuần.

**Câu 2:** \(18/4{,}5=4\) tuần là **mốc trung tâm theo phép chia**, không phải hạn giao được bảo đảm.

**Câu 3:** \(18/3=6\) hạng mục/tuần. Mức 6 chỉ xuất hiện **một trong tám tuần**; duy trì liên tiếp mức này trong ba tuần là giả định rủi ro hơn mức thông thường. Không đủ căn cứ để hứa chắc sẽ đạt.

**Câu 4:** Dữ liệu đã sắp xếp tăng dần. Trung vị bằng trung bình của vị trí 6 và 7 là \((5+6)/2=5{,}5\) ngày làm việc. Với **nearest-rank**, P85 ở vị trí \(\lceil0{,}85\times12\rceil=11\), bằng **9 ngày**; P95 ở vị trí \(\lceil0{,}95\times12\rceil=12\), bằng **14 ngày**.

**Câu 5:** Không. Việc một item đã 11 ngày và chưa Done cần được xem theo **work item age**, nguyên nhân chờ review, rủi ro tích hợp và trạng thái thực tế. Lấy 14 trừ 11 chỉ là phép trừ từ giá trị dài nhất trong mẫu, **không phải dự báo thời gian còn lại**.

**Câu 6:** Nhóm có thể mô phỏng **how many** cho bốn tuần bằng cách lấy mẫu throughput tuần lịch sử nhiều lần, cộng số item hoàn tất trong mỗi kịch bản rồi tính tỷ lệ mô phỏng đạt **ít nhất 18 item**. Cần nêu các giả định: mẫu đại diện, cách đo Done ổn định, số item không thay đổi, các tuần đủ tương đồng. Nếu chưa chạy mô phỏng, không tự công bố xác suất.

**Câu 7:** Làm rõ hạng mục nào **thật sự cần có** để người học đăng ký thành công; ưu tiên lát cắt giá trị, chia việc lớn thành phần dùng được, giải quyết hàng chờ review/tích hợp, giảm WIP, thảo luận nguồn lực hoặc cách phát hành theo giai đoạn. Tất cả thay đổi ảnh hưởng cam kết phải được người có thẩm quyền thống nhất; **không bỏ kiểm thử hay hạ Definition of Done** để đạt một mốc giả tạo.

### Bài tập mở rộng: đặt câu hỏi đúng về rủi ro

Giả sử sau tuần tiếp theo nhóm chỉ hoàn tất hai hạng mục do một sự cố bảo mật. Hãy viết lại bản báo cáo dự báo gồm: **số việc còn lại, dữ liệu nào vừa thay đổi, giả định nào không còn đúng, phương án phạm vi và mốc cập nhật tiếp theo**. Không chỉ lấy trung bình cũ rồi tiếp tục tuyên bố “đúng bốn tuần sẽ xong”.

## 16. Danh sách kiểm tra trước khi công bố một dự báo

Trước khi gửi mốc dự báo cho Product Owner hoặc các bên liên quan, tự hỏi:

1. **Câu hỏi rõ chưa?** Khi nào hoàn tất N item, hay xong bao nhiêu item trước ngày X?
2. **Mốc rõ chưa?** Đang đo Done, phát hành hay người dùng đã nhận được giá trị?
3. **Ranh giới thống nhất chưa?** Điểm bắt đầu, điểm hoàn tất, loại item và đơn vị thời gian đã được định nghĩa?
4. **Dữ liệu đủ tin cậy chưa?** Có lỗi ghi nhận, thay đổi workflow, chia/gộp item hoặc thiếu tuần bất thường không?
5. **Phạm vi có ổn định hoặc được kiểm soát chưa?** Backlog sẽ còn thêm việc nào, dự báo có cần tách một nhóm mục tiêu?
6. **Có xem biến động không?** Ngoài trung bình, đã xem phân bố, tuổi item, WIP và hàng chờ?
7. **Có phân biệt kịch bản và xác suất không?** Có chạy mô phỏng thật mới công bố P50/P85/P95?
8. **Giả định có hợp lý không?** Loại công việc, năng lực, DoD và mức hỗ trợ vận hành tương đồng quá khứ?
9. **Có cách thích ứng không?** Nếu dự báo lệch, nhóm sẽ điều chỉnh phạm vi, thứ tự ưu tiên hoặc giải quyết nút nghẽn ra sao?
10. **Kết quả có giá trị không?** Mục tiêu không chỉ là đếm item, mà là giao phần mềm có chất lượng và giúp người dùng đạt kết quả?

**Ghi nhớ:** **Thông lượng** giúp dự báo lượng công việc hoàn tất theo thời gian; **cycle time** mô tả phân bố thời gian hoàn thành; **work item age** giúp nhận diện rủi ro của công việc còn dở; **WIP** và các chính sách luồng giải thích vì sao công việc bị chờ. Dự báo đáng tin cậy cần dữ liệu có ranh giới rõ, mức bất định được nói thẳng và cập nhật theo phản hồi thực tế. Agile không đòi hỏi dự đoán tương lai chính xác tuyệt đối, mà giúp nhóm **ra quyết định tốt hơn khi tương lai chưa chắc chắn**.
