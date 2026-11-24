# Số tích lũy và số theo bước thời gian được công bố khác nhau

## Cùng một meter có thể được xuất theo hai cách thời gian

Micrometer cung cấp API thống nhất để ứng dụng Java tạo Counter, Timer, DistributionSummary, Gauge và các loại meter khác. Tuy nhiên, API không bắt buộc mọi registry phải công bố số liệu theo cùng một cách tích lũy theo thời gian.

Hai mô hình thường gặp là:

- **Cumulative:** giá trị được tích lũy từ khi meter bắt đầu hoạt động trong vòng đời của registry hoặc tiến trình. Count và tổng giá trị thường không giảm giữa các lần thu thập.
- **Step-based:** giá trị được gom trong một khoảng thời gian cố định gọi là step. Khi bước thời gian hoàn tất, registry công bố số liệu của khoảng đó; bước tiếp theo bắt đầu tích lũy cho khoảng mới.

Khác biệt này ảnh hưởng trực tiếp đến cách đọc Counter, Timer, DistributionSummary, cách tính rate, cách so sánh giữa các instance và cách viết dashboard hoặc cảnh báo. Cùng một lệnh increment trong mã Java có thể tạo ra dữ liệu cumulative ở một registry và dữ liệu theo step ở registry khác.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, ứng dụng cần đo lường bằng các loại meter, xuất metrics đến hệ giám sát và diễn giải số đo vận hành. Vì vậy, khi đổi registry hoặc backend, cần kiểm tra semantics thời gian của dữ liệu được xuất, không chỉ kiểm tra tên meter và tag.

## Mô hình cumulative

### Giá trị tiếp tục tăng qua các lần thu thập

Trong mô hình cumulative, một Counter tích lũy các lần tăng kể từ khi meter bắt đầu. Ví dụ, ứng dụng nhận 100 request, rồi thêm 40 request. Hai lần scrape có thể quan sát các giá trị lần lượt là 100 và 140.

~~~java
Counter requests = Counter.builder("service.requests")
    .description("Tong so request da tiep nhan")
    .register(registry);

requests.increment(100);
requests.increment(40);
~~~

Nếu registry xuất Counter theo cumulative semantics, giá trị công bố là tổng tích lũy hiện tại. Khi không có request mới, giá trị vẫn giữ nguyên ở lần scrape tiếp theo. Nó không trở về 0 chỉ vì khoảng scrape vừa rồi không có request.

Đối với Timer, count và total time cũng thường được công bố tích lũy trong registry cumulative. Nếu 10 thao tác đã hoàn tất với tổng thời gian 2 giây, count là 10 và total time là 2 giây. Sau 5 thao tác tiếp theo có tổng thời gian 1 giây, count trở thành 15 và total time thành 3 giây.

### Backend tính tốc độ từ chênh lệch giữa các mẫu

Với counter cumulative, backend có thể tính tốc độ dựa trên mức tăng trong một cửa sổ truy vấn. Trong Prometheus, ví dụ thường gặp là:

~~~promql
rate(service_requests_total[5m])
~~~

Hàm rate tính tốc độ trung bình mỗi giây từ các mẫu counter cumulative trong khoảng 5 phút và xử lý trường hợp counter reset theo quy tắc của Prometheus.

Tên series thực tế phụ thuộc NamingConvention và registry. Ví dụ trên minh họa cách truy vấn một counter cumulative; cần kiểm tra tên metric được exporter thực sự công bố.

Nếu giá trị counter là 100 ở lần scrape trước và 160 ở lần scrape sau cách nhau 10 giây, mức tăng là 60. Tốc độ trung bình trong khoảng đó xấp xỉ 6 request mỗi giây. Backend cần có các mẫu theo thời gian để thực hiện phép tính này.

### Khi không có quan sát mới

Nếu không có request mới, counter cumulative giữ nguyên giá trị. Rate trong cửa sổ có thể tiến về 0 khi không còn mức tăng, nhưng tổng counter vẫn giữ số đã tích lũy.

Điều này giúp phân biệt hai câu hỏi:

- Tổng số request kể từ khi tiến trình bắt đầu là bao nhiêu?
- Trong vài phút gần đây, tốc độ request là bao nhiêu?

Count cumulative trả lời câu hỏi thứ nhất; rate trên chuỗi cumulative giúp trả lời câu hỏi thứ hai.

## Mô hình step-based

### Giá trị được gom theo từng khoảng cố định

Trong registry theo step, phép đo được tích lũy trong một khoảng thời gian xác định. Khi step kết thúc, registry công bố số liệu của khoảng vừa hoàn tất và bắt đầu thu thập cho step tiếp theo.

Ví dụ, với step 10 giây:

| Khoảng thời gian | Request nhận được | Count được công bố cho step |
|---|---:|---:|
| 10:00:00–10:00:10 | 120 | 120 |
| 10:00:10–10:00:20 | 75 | 75 |
| 10:00:20–10:00:30 | 0 | 0 |
| 10:00:30–10:00:40 | 90 | 90 |

Giá trị 75 là số request trong step thứ hai, không phải tổng số request kể từ lúc ứng dụng khởi động. Nếu dashboard cộng các giá trị step, nó có thể tính tổng trong một khoảng truy vấn; nếu muốn tốc độ mỗi giây, cần diễn giải count theo độ dài step hoặc theo quy tắc truy vấn của backend.

Các registry push thường dùng mô hình step để gom số liệu rồi gửi định kỳ. Micrometer có các registry dựa trên cơ chế StepMeterRegistry; loại registry cụ thể và cấu hình của nó quyết định chu kỳ công bố cũng như cách từng meter được ánh xạ.

### Step không phải là cửa sổ truy vấn của dashboard

Step là khoảng tích lũy ở phía registry trước khi công bố dữ liệu. Cửa sổ truy vấn ở backend là khoảng thời gian mà truy vấn dùng để tổng hợp các điểm đã nhận. Hai khái niệm có liên quan nhưng không đồng nhất.

Ví dụ, registry có step 10 giây nhưng dashboard truy vấn 5 phút. Dashboard có thể tổng hợp nhiều điểm step trong 5 phút. Ngược lại, nếu registry có step 1 phút, một dashboard truy vấn 10 giây không thể khôi phục độ phân giải 10 giây từ dữ liệu chỉ được công bố mỗi phút.

Tăng tần suất refresh dashboard không làm dữ liệu step trở nên chi tiết hơn. Độ phân giải đầu vào bị giới hạn bởi thời điểm và cách registry công bố số liệu.

### Điều gì xảy ra khi một step không có quan sát?

Với các thống kê step như count và total amount, step không có phép ghi mới thường được công bố với giá trị 0 cho khoảng đó. Điều này khác với counter cumulative: cumulative giữ tổng cũ, còn step biểu diễn lượng phát sinh trong khoảng hiện tại.

Ví dụ, nếu một step có 75 request và step tiếp theo không có request, registry step có thể công bố 75 rồi 0. Registry cumulative có thể công bố 75 rồi tiếp tục giữ 75.

Không nên diễn giải số 0 của step là tổng lịch sử đã bị xóa. Nó chỉ cho biết không có giá trị được ghi nhận trong khoảng step đó. Backend có thể vẫn giữ các điểm step trước đó theo chính sách retention của nó.

## So sánh cumulative và step-based

| Khía cạnh | Cumulative | Step-based |
|---|---|---|
| Giá trị Counter | Tổng tích lũy trong vòng đời meter | Số tăng trong step đã hoàn tất |
| Count của Timer | Tổng số observation tích lũy | Số observation trong step |
| Total time của Timer | Tổng thời gian tích lũy | Tổng thời gian trong step |
| Không có observation mới | Giá trị cumulative giữ nguyên | Count/sum của step mới thường là 0 |
| Tính rate | Backend tính từ chênh lệch các mẫu cumulative | Dựa trên delta mỗi step hoặc cơ chế rate của backend |
| Độ phân giải | Phụ thuộc chu kỳ scrape/thu thập | Bị giới hạn bởi step và chu kỳ công bố |
| Restart tiến trình | Counter cumulative bắt đầu lại theo vòng đời mới | Step đang tích lũy có thể chưa được công bố và bị mất khi dừng đột ngột |
| Tổng trong một khoảng truy vấn | Dùng increase hoặc tổng mức tăng | Cộng các delta step thuộc khoảng đó |
| Phân tích Timer | Count/sum tích lũy; histogram theo registry | Count/sum theo step; thống kê phân phối có thể có cửa sổ riêng |

Bảng mô tả semantics phổ biến của hai mô hình. Một registry cụ thể có thể có quy tắc riêng cho max, percentile, histogram, gauge hoặc function meter. Không nên suy luận rằng mọi thống kê của mọi meter đều tuân theo cùng một quy tắc chỉ từ việc registry có step.

## Cách diễn giải Counter trong từng mô hình

### Counter cumulative

Counter cumulative thường được xuất dưới dạng một giá trị không giảm. Backend tính rate bằng mức tăng giữa các lần scrape. Khi tiến trình khởi động lại, counter có thể bắt đầu lại từ 0; hệ thống truy vấn cần nhận diện reset thay vì coi mức giảm là một lượng request âm.

Với Prometheus, thường dùng rate hoặc increase:

~~~promql
rate(service_requests_total[5m])
increase(service_requests_total[1h])
~~~

rate trả về tốc độ trung bình mỗi giây trong cửa sổ; increase ước lượng tổng mức tăng trong cửa sổ. Cần dùng đúng metric name thực tế do exporter công bố.

### Counter step-based

Counter step-based biểu diễn lượng tăng trong step vừa hoàn tất. Nếu một step 10 giây công bố 500 request, đó là 500 request trong step, không phải tổng từ khi tiến trình khởi động.

Để diễn giải thành tốc độ, có thể chia delta cho độ dài step nếu backend không tự chuẩn hóa:

~~~text
requests per second = step request count / step duration in seconds
                    = 500 / 10
                    = 50 requests/second
~~~

Nếu backend hoặc registry đã chuẩn hóa step count thành rate, không chia thêm lần nữa. Cần đọc tài liệu exporter và kiểm tra đơn vị series được xuất.

Không áp dụng máy móc hàm rate dành cho counter cumulative lên một chuỗi delta step. Nếu mỗi điểm đã là số lượng của một khoảng, rate trên các điểm đó có thể tính tốc độ thay đổi của delta thay vì tốc độ request. Trước khi viết query, xác định rõ dữ liệu là cumulative hay delta.

## Cách diễn giải Timer trong từng mô hình

### Timer cumulative

Với registry cumulative, count và total time của Timer thường tăng theo tổng số thao tác đã hoàn tất và tổng thời gian của chúng.

Có thể tính mean duration trong cùng phạm vi:

~~~text
mean duration = cumulative total time / cumulative count
~~~

Nếu count là 1.000 và total time là 50 giây, mean là 50 mili giây. Để tính mean trong 5 phút gần đây, cần lấy mức tăng của total time và count trong cùng cửa sổ, không chia tổng lifetime cho một count của cửa sổ ngắn.

Với Prometheus, Timer thường được ánh xạ thành các series count và sum; tên và đơn vị cụ thể phụ thuộc registry. Có thể tính tốc độ hoàn tất từ count cumulative và mean trong cửa sổ từ rate của sum chia cho rate của count, miễn là hai series có cùng phạm vi và đơn vị.

### Timer step-based

Với registry step, count và total time thường phản ánh các thao tác hoàn tất trong step vừa qua. Mean của step được tính từ total time của step chia cho count của cùng step.

Ví dụ, trong step 30 giây có 60 thao tác với tổng thời gian 12 giây:

~~~text
mean duration = 12 seconds / 60 = 0.2 seconds
~~~

Nếu step kế tiếp không có thao tác, count và total time của step mới thường bằng 0. Không được chia cho 0 hoặc diễn giải mean là 0 mili giây; đó là khoảng không có observation. Dashboard nên xử lý trường hợp count bằng 0 như dữ liệu không có mẫu cho phép tính mean.

## Histogram, percentile và max không phải lúc nào cũng theo cùng step

Count và total time dễ được hiểu theo cumulative hoặc step, nhưng thống kê phân phối cần được xem xét riêng.

Micrometer có thể cấu hình percentile phía ứng dụng, histogram bucket và SLO cho Timer hoặc DistributionSummary. Những thống kê này có thể có expiry, buffer length hoặc semantics do registry/backend quyết định. Ví dụ, max trong Micrometer có thể được duy trì theo time window; nó không nhất thiết là max lifetime hoặc max của đúng step vừa qua.

Vì vậy:

- Không suy luận rằng max sẽ reset cùng lúc với count của step.
- Không mặc định percentile phía client có cùng cửa sổ với step.
- Không giả định histogram bucket là cumulative hay delta nếu chưa xem định dạng exporter.
- Giữ cấu hình bucket, đơn vị và tag nhất quán giữa các instance khi cần tổng hợp.
- Kiểm tra cách backend nhận và truy vấn histogram thực tế.

Một dashboard có thể hiển thị count theo step, max theo cửa sổ và percentile được tính ở backend trong cửa sổ truy vấn. Những số liệu này không sai chỉ vì phạm vi khác nhau, nhưng phải được gắn nhãn và diễn giải đúng.

## Gauge không phải Counter step

Gauge biểu diễn giá trị hiện tại tại thời điểm registry đọc nó. Gauge không phải số tích lũy và cũng không phải delta của một step.

Ví dụ, số tác vụ đang chờ trong queue là trạng thái hiện tại. Registry có thể đọc 20 ở một lần scrape và 5 ở lần sau. Việc giá trị giảm là hợp lệ đối với Gauge.

Không cộng các giá trị Gauge qua nhiều step để tính tổng sự kiện. Nếu cần tổng số lần enqueue, dùng Counter. Nếu cần số lượng hiện đang chờ, dùng Gauge.

Một số registry có thể lấy mẫu Gauge theo chu kỳ công bố của chúng. Tần suất và thời điểm đọc vẫn phụ thuộc registry; Gauge không tự lưu lịch sử các giá trị trung gian giữa hai lần thu thập.

## Restart, mất dữ liệu và khoảng trống công bố

### Cumulative khi tiến trình khởi động lại

Counter cumulative thường bắt đầu lại theo vòng đời tiến trình hoặc registry mới. Backend cần nhận diện counter reset. Với hệ thống có nhãn instance, series của instance cũ và instance mới có thể tách biệt; nếu instance identity bị tái sử dụng, cần kiểm tra cách backend xử lý reset.

Timer cumulative cũng có count và total time bắt đầu lại theo vòng đời registry. Khi truy vấn qua thời điểm restart, phải dùng phép tính hỗ trợ reset và không coi mức giảm là dữ liệu âm.

### Step khi tiến trình dừng giữa khoảng

Với registry step, số liệu của step hiện tại có thể chưa được công bố cho đến khi step hoàn tất hoặc lần publish tiếp theo chạy. Nếu tiến trình bị dừng đột ngột trước khi publish, phần dữ liệu đang tích lũy có thể không được gửi đến backend.

Một số registry có cơ chế flush khi shutdown hoặc retry khi gửi thất bại; hành vi phụ thuộc implementation và cấu hình. Không nên giả định mọi step registry đều bảo đảm giao nhận exactly-once hoặc tự phục hồi dữ liệu chưa publish.

Khi cần độ tin cậy cao, cần kiểm tra lifecycle shutdown, flush, retry và cơ chế buffer của exporter. Metrics thường phục vụ quan sát vận hành; nếu một sự kiện phải được lưu bền vững để đối soát nghiệp vụ, hãy dùng message log hoặc kho dữ liệu phù hợp.

## Chọn độ dài step

Độ dài step là một quyết định vận hành. Step ngắn giúp dữ liệu phản ánh biến động nhanh hơn và giảm độ trễ từ lúc sự kiện xảy ra đến lúc được công bố. Tuy nhiên, step ngắn cũng có thể tạo nhiều lần gửi, tăng overhead mạng, chi phí ingest và khiến các khoảng ít traffic có nhiều điểm 0.

Step dài giảm tần suất publish và có thể làm số liệu ổn định hơn, nhưng làm chậm khả năng phát hiện spike hoặc sự cố. Các biến động ngắn có thể bị gộp vào một điểm tổng hợp lớn.

Khi chọn step, cân nhắc:

1. Thời gian phản hồi cảnh báo mong muốn.
2. Tần suất scrape hoặc push mà backend hỗ trợ.
3. Lưu lượng và độ biến động của ứng dụng.
4. Chi phí gửi dữ liệu và giới hạn ingest.
5. Khả năng tổng hợp giữa nhiều instance.
6. Cửa sổ truy vấn và retention của backend.

Các instance cùng một nhóm nên dùng cấu hình step tương thích. Nếu mỗi instance công bố các khoảng khác nhau, việc cộng các delta theo timestamp có thể lệch cửa sổ và làm biểu đồ tổng hợp khó diễn giải.

## Tổng hợp giữa nhiều instance

Với cumulative metrics, cách phổ biến là tính rate hoặc increase cho từng series rồi tổng hợp theo nhóm. Ví dụ, tính rate của từng instance rồi sum theo service giúp tránh cộng trực tiếp các giá trị counter có vòng đời khác nhau.

Với step metrics, mỗi series đã là delta của một khoảng. Có thể cộng các delta thuộc cùng khoảng thời gian nếu các instance dùng step và ranh giới thời gian tương thích, đơn vị giống nhau và mỗi sự kiện chỉ được tính đúng một lần.

Không lấy trung bình các giá trị cumulative counter của nhiều instance để tính tổng request. Cũng không cộng một rate đã chuẩn hóa với một delta thô. Trước khi tổng hợp, đưa các series về cùng ý nghĩa: cùng đơn vị, cùng phạm vi thời gian và cùng kiểu cumulative/delta.

## Cấu hình và xác minh trong Spring Boot

Trong Spring Boot, registry exporter thường được tạo tự động từ dependency và cấu hình. Một số exporter có thuộc tính cấu hình step riêng; tên thuộc tính và giá trị mặc định phụ thuộc registry, phiên bản Spring Boot và phiên bản Micrometer.

Không có một thuộc tính step duy nhất áp dụng cho mọi backend. Hãy kiểm tra cấu hình exporter cụ thể đang dùng và xác minh registry thực tế được tạo trong application context.

Quy trình kiểm tra nên gồm:

- Xác định loại registry được inject vào MeterRegistry.
- Xác định registry dùng pull hay push.
- Kiểm tra cấu hình step nếu registry hỗ trợ step.
- Ghi một số giá trị có thể dự đoán trong hai hoặc ba khoảng thời gian.
- Quan sát giá trị được công bố ở từng thời điểm.
- Đối chiếu count, sum, rate và đơn vị với semantics dự kiến.
- Kiểm tra trường hợp một step không có observation.
- Kiểm tra hành vi khi ứng dụng shutdown hoặc restart.

Nếu ứng dụng dùng CompositeMeterRegistry để xuất cùng meter đến nhiều backend, mỗi registry thành phần có thể có cách công bố khác nhau. Cùng một meter có thể được nhìn dưới dạng cumulative ở một backend và step/delta ở backend khác. Không nên dùng chung một truy vấn cho cả hai chỉ vì tên meter trong mã giống nhau.

## Kiểm thử semantics thời gian

SimpleMeterRegistry hữu ích để kiểm tra instrumentation cơ bản, nhưng không đại diện cho mọi semantics của registry step. Một test xác nhận Counter tăng từ 0 lên 5 trong SimpleMeterRegistry không chứng minh exporter step sẽ công bố 5 trong khoảng nào.

Với registry step cụ thể, nên kiểm thử bằng clock có thể điều khiển hoặc fixture mà registry cung cấp:

1. Tạo registry với step xác định.
2. Ghi một số observation trong step đầu.
3. Kiểm tra giá trị trước và sau thời điểm rollover theo semantics của registry.
4. Không ghi observation trong step tiếp theo và xác minh giá trị được công bố.
5. Ghi observation ở step mới và xác minh dữ liệu không bị cộng nhầm vào step trước.
6. Kiểm tra thời điểm publish, flush và shutdown.
7. Kiểm tra payload exporter và cách backend diễn giải cumulative hoặc delta.

Không nên dùng Thread.sleep dài trong unit test để chờ step nếu có thể điều khiển clock. Test dựa trên thời gian thật thường chậm và dễ dao động do scheduler hoặc tải máy.

Đối với cumulative registry, kiểm tra rằng count/sum tiếp tục tăng qua nhiều lần thu thập và giữ nguyên khi không có observation mới. Đối với step registry, kiểm tra từng khoảng riêng. Bộ test nên phản ánh chính registry sẽ được triển khai.

## Những sai lầm thường gặp

**Coi số step là tổng lifetime.** Count của step chỉ phản ánh khoảng vừa hoàn tất. Muốn tổng lịch sử, cần cộng các delta hoặc dùng nguồn cumulative phù hợp.

**Áp dụng rate lên dữ liệu delta như counter cumulative.** Có thể tạo ra tốc độ biến thiên của delta thay vì tốc độ sự kiện. Xác định temporality trước khi viết query.

**Coi count step bằng 0 là counter đã reset.** Nó có thể chỉ là một khoảng không có observation. Không nhầm delta rỗng với reset của chuỗi cumulative.

**Giả định mọi thống kê Timer đều theo step.** Max, percentile và histogram có thể có cửa sổ hoặc quy tắc riêng. Kiểm tra từng series được xuất.

**Dùng SimpleMeterRegistry để kết luận semantics của exporter.** Registry trong bộ nhớ không mô phỏng đầy đủ step, push, rollover và retry. Kiểm thử registry cụ thể.

**Cấu hình step khác nhau giữa các instance.** Các delta có thể lệch khoảng thời gian và gây sai lệch khi tổng hợp. Chuẩn hóa step và ranh giới công bố.

**Bỏ qua dữ liệu chưa publish khi shutdown.** Step đang mở có thể chưa được gửi nếu tiến trình dừng đột ngột. Kiểm tra flush và lifecycle exporter.

**Dùng cùng dashboard cho cumulative và step.** Một query rate có thể đúng với cumulative nhưng sai với delta. Dashboard cần phản ánh semantics thực tế của backend.

**Cộng các Gauge qua thời gian.** Gauge là trạng thái tại thời điểm đọc, không phải số sự kiện của mỗi step. Dùng Counter cho sự kiện.

## Checklist khi chuyển registry hoặc backend

Trước khi triển khai hoặc thay registry, hãy xác minh:

1. Registry hiện tại xuất cumulative hay step/delta cho từng loại meter?
2. Registry mới có cùng semantics hay không?
3. Counter và Timer count/sum được công bố theo lifetime hay theo khoảng?
4. Giá trị không có observation được giữ nguyên hay công bố bằng 0?
5. Rate và increase trong dashboard có phù hợp với kiểu dữ liệu không?
6. Histogram, max và percentile có cửa sổ riêng nào?
7. Step duration và ranh giới công bố có giống nhau giữa các instance không?
8. Backend có tự chuẩn hóa delta thành rate hay không?
9. Dữ liệu step đang mở được flush thế nào khi shutdown?
10. Query, dashboard và alert đã được điều chỉnh theo semantics mới chưa?
11. Kiểm thử có chạy trên registry exporter thực tế không?
12. Các series có cùng đơn vị, tag và phạm vi thời gian trước khi tổng hợp không?

## Kết luận

Cumulative và step-based mô tả hai cách khác nhau để công bố số đo theo thời gian. Cumulative giữ tổng đã tích lũy qua các lần thu thập; step-based công bố lượng phát sinh trong từng khoảng cố định. Khi không có observation mới, cumulative thường giữ nguyên giá trị còn step count/sum thường là 0 cho khoảng mới.

Sự khác biệt này quyết định cách tính rate, mean, tổng trong cửa sổ, cách xử lý restart và cách tổng hợp giữa các instance. Hãy xác định semantics của registry cụ thể, kiểm tra riêng count, sum, max, histogram và Gauge, rồi điều chỉnh query và cảnh báo theo dữ liệu thực tế. Khi đổi backend, cần kiểm thử cả thời điểm rollover, step rỗng và shutdown để tránh dashboard hiển thị đúng cú pháp nhưng sai ý nghĩa.
