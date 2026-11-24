# Kiểm chứng dữ liệu scrape khi ứng dụng khởi động lại hoặc meter ngừng hoạt động

Prometheus thu thập metrics theo từng lần scrape. Mỗi lần scrape là một ảnh chụp các mẫu mà endpoint đang công bố tại thời điểm thu thập. Vì vậy, dữ liệu trên Prometheus chịu ảnh hưởng bởi vòng đời tiến trình, trạng thái đăng ký meter, thời điểm ghi nhận sự kiện và cấu hình scrape.

Khi ứng dụng khởi động lại hoặc một meter ngừng hoạt động, biểu đồ có thể xuất hiện đoạn phẳng, khoảng trống hoặc một chuỗi thời gian mới. Những biểu hiện này không có cùng nguyên nhân. Cần phân biệt target không scrape được, meter vẫn được xuất nhưng không có cập nhật mới, và meter đã biến mất khỏi endpoint. Bài học này trình bày cách đọc từng trường hợp và xác minh bằng PromQL.

## 1. Hiểu luồng scrape và vòng đời dữ liệu

Trong mô hình pull, Prometheus định kỳ gửi HTTP request đến endpoint metrics của ứng dụng, thường là endpoint do Spring Boot Actuator và Micrometer registry cung cấp. Mỗi lần scrape thành công, Prometheus lưu các mẫu metric kèm timestamp và bộ label.

Luồng cơ bản:

~~~mermaid
flowchart LR
    A[Ứng dụng Java] --> B[Micrometer MeterRegistry]
    B --> C[Endpoint metrics]
    C -->|Scrape theo lịch| D[Prometheus]
    D --> E[Time series]
    E --> F[PromQL và alert]
~~~

Có ba lớp cần kiểm tra:

1. **Tiến trình ứng dụng:** ứng dụng đang chạy, vừa khởi động lại hay đã dừng?
2. **Instrumentation và endpoint:** meter có còn được đăng ký và được xuất trong response không?
3. **Prometheus:** target có scrape thành công không, mẫu được lưu với label nào và truy vấn có đang chọn đúng series không?

Một dashboard trống không tự chứng minh rằng ứng dụng không ghi nhận sự kiện. Lỗi có thể nằm ở đường mạng, endpoint, cấu hình scrape, thay đổi label, meter bị loại khỏi response hoặc truy vấn PromQL.

## 2. Phân biệt target down, meter phẳng và meter biến mất

Ba tình huống thường gặp có biểu hiện khác nhau:

| Tình huống | Endpoint/target | Dấu hiệu dữ liệu | Cách hiểu |
| --- | --- | --- | --- |
| Ứng dụng dừng hoặc endpoint không truy cập được | Scrape thất bại | up bằng 0; các series của target không có mẫu mới và được đánh dấu stale | Prometheus không lấy được response từ target. |
| Ứng dụng vẫn chạy, meter còn được xuất nhưng không có sự kiện mới | Scrape thành công | Counter hoặc Timer count/sum giữ nguyên; Gauge tiếp tục có giá trị | Meter vẫn tồn tại, chỉ không nhận cập nhật mới. |
| Meter bị gỡ hoặc không còn xuất trong response | Target có thể vẫn UP | Series bị đánh dấu stale sau lần scrape thành công không còn metric đó | Endpoint vẫn hoạt động nhưng metric cụ thể đã biến mất. |

Không nên gộp các tình huống này thành một trạng thái “metric bằng 0”. 0 là giá trị số được scrape; series không tồn tại là thiếu dữ liệu. Cảnh báo và dashboard cần giữ được sự khác biệt đó.

## 3. Điều gì xảy ra với Counter khi ứng dụng khởi động lại?

Counter của Micrometer thường giữ giá trị tích lũy trong bộ nhớ của tiến trình. Khi JVM khởi động lại, đối tượng registry được tạo lại và Counter bắt đầu từ giá trị ban đầu, thường là 0. Prometheus tiếp tục scrape cùng target và có thể nhìn thấy giá trị mới thấp hơn mẫu trước đó.

Ví dụ, Prometheus đã thu thập:

| Thời điểm | Giá trị orders_created_total |
| --- | ---: |
| 10:00 | 120 |
| 10:01 | 135 |
| 10:02 | 148 |
| 10:03 | 4 sau khi tiến trình khởi động lại |
| 10:04 | 12 |

Việc giá trị giảm từ 148 xuống 4 là counter reset. Đây là hành vi bình thường khi tiến trình khởi động lại, không nhất thiết là dữ liệu bị hỏng.

Prometheus có các hàm rate() và increase() được thiết kế để xử lý counter reset khi tính toán trên một range vector. Không nên tự lấy hiệu hai mẫu bằng phép trừ đơn giản vì phép trừ có thể cho kết quả âm khi Counter reset.

### Truy vấn tốc độ tăng

~~~promql
rate(orders_created_total[5m])
~~~

Truy vấn ước lượng tốc độ đơn hàng được tạo mỗi giây trong cửa sổ năm phút và xử lý việc Counter giảm do reset.

### Truy vấn số lượng tăng trong một khoảng

~~~promql
increase(orders_created_total[1h])
~~~

Truy vấn ước lượng số đơn hàng được tạo trong một giờ. Kết quả có thể là số thập phân do Prometheus ngoại suy theo ranh giới cửa sổ thời gian; nếu cần số giao dịch chính xác cho nghiệp vụ, hãy dùng hệ thống dữ liệu giao dịch làm nguồn sự thật.

### Đếm số lần reset

~~~promql
resets(orders_created_total[1h])
~~~

Hàm resets() đếm số lần Counter giảm trong cửa sổ. Nó hữu ích để kiểm chứng restart hoặc reset, nhưng một reset cũng có thể đến từ việc code chủ động tạo lại meter hay thay đổi tiến trình quản lý counter.

## 4. Giới hạn phát hiện reset giữa hai lần scrape

Prometheus chỉ nhìn thấy các mẫu tại thời điểm scrape. Nếu ứng dụng khởi động lại và Counter tăng vượt giá trị cũ trước lần scrape kế tiếp, Prometheus có thể không quan sát được giá trị thấp hơn và không phát hiện được lần reset đó.

Ví dụ:

1. Lần scrape trước ghi nhận Counter bằng 100.
2. Ứng dụng khởi động lại, Counter về 0.
3. Trước lần scrape tiếp theo, ứng dụng đã xử lý 150 sự kiện.
4. Lần scrape mới ghi nhận 150.

Prometheus chỉ thấy 100 rồi 150, nên không thể biết tiến trình đã reset ở giữa hai lần lấy mẫu. Phần tăng thực tế sau restart có thể bị hiểu như mức tăng liên tục từ 100 lên 150.

Để giảm khả năng bỏ lỡ reset:

- Chọn scrape interval phù hợp với tốc độ tăng Counter và thời gian khởi động lại.
- Theo dõi thêm metric thời điểm bắt đầu tiến trình nếu registry/exporter có cung cấp.
- Theo dõi vòng đời instance hoặc pod qua label target ổn định và metadata triển khai.
- Dùng resets() cùng các chỉ số sức khỏe target để tìm dấu hiệu restart.
- Không dùng Counter trong bộ nhớ làm kho lưu trữ lâu dài cho số liệu nghiệp vụ.

Không có scrape interval nào bảo đảm nhìn thấy mọi reset trong mọi tình huống. Nếu cần số đếm chính xác qua restart, dữ liệu nghiệp vụ phải được lưu bền vững ở hệ thống phù hợp.

## 5. Điều gì xảy ra với Timer và histogram khi restart?

Timer thường xuất ra các đại lượng tích lũy như số lần ghi nhận và tổng thời lượng. Histogram xuất các bucket đếm tích lũy. Những giá trị tích lũy này cũng thường bắt đầu lại khi tiến trình hoặc registry được tạo lại.

Với Prometheus, các chuỗi count, sum và bucket được xử lý theo ngữ nghĩa counter. Dùng rate() hoặc increase() trên chúng để phân tích theo thời gian, thay vì tự lấy hiệu mẫu.

Ví dụ:

~~~promql
rate(http_server_requests_seconds_count[5m])
~~~

~~~promql
rate(http_server_requests_seconds_sum[5m])
~~~

~~~promql
rate(http_server_requests_seconds_bucket[5m])
~~~

Tên metric thực tế phụ thuộc phiên bản Micrometer registry và instrumentation. Hãy kiểm tra exposition của endpoint trước khi dùng truy vấn.

Các series có hậu tố _bucket chỉ xuất hiện khi histogram được bật cho Timer hoặc có cấu hình bucket phù hợp. Nếu chỉ công bố count/sum hoặc client-side percentile, truy vấn bucket sẽ không có dữ liệu.

Các quantile được tính tại ứng dụng bằng publishPercentiles() có ngữ nghĩa khác histogram bucket. Giá trị quantile là thống kê phân phối cục bộ và không nên dùng rate() hoặc cộng gộp chúng như các counter. Nếu cần percentile toàn service qua nhiều instance, hãy dùng histogram và histogram_quantile() theo cách đã thiết kế.

## 6. Khi meter vẫn tồn tại nhưng không còn sự kiện

Không có sự kiện mới không đồng nghĩa meter biến mất. Nếu Counter vẫn được đăng ký trong MeterRegistry và endpoint tiếp tục xuất nó, Prometheus vẫn scrape giá trị hiện tại dù giá trị không thay đổi.

Ví dụ Counter tăng đến 50, sau đó không có sự kiện mới:

| Lần scrape | Giá trị Counter |
| --- | ---: |
| 12:00 | 50 |
| 12:01 | 50 |
| 12:02 | 50 |
| 12:03 | 50 |

Series vẫn tồn tại. rate() sẽ tiến về 0 khi cửa sổ truy vấn chỉ còn các mẫu phẳng và có đủ mẫu để tính toán.

~~~promql
rate(queue_messages_received_total[5m])
~~~

Giá trị gần 0 có thể có nghĩa queue không nhận message mới, nhưng cũng có thể là lưu lượng thấp. Hãy xem cùng up, số lượng request tổng thể và kỳ vọng lưu lượng để xác định có thực sự bất thường hay không.

### Timer không có thao tác mới

Nếu Timer còn đăng ký nhưng không có lần record() mới, count và sum vẫn được xuất với giá trị cuối cùng. Rate của count trong cửa sổ đủ mẫu sẽ bằng 0. Điều này khác với việc metric Timer bị gỡ khỏi registry.

### Gauge tiếp tục được đọc

Gauge có thể tiếp tục được scrape dù không có sự kiện tăng/giảm. Hàm đọc vẫn trả về trạng thái hiện tại của đối tượng. Nếu trạng thái giữ nguyên, Gauge sẽ phẳng; nếu object nguồn bị thu hồi do chỉ còn weak reference, giá trị có thể không còn hữu ích hoặc không được xuất theo cách mong đợi của registry.

## 7. Khi meter bị gỡ hoặc không còn xuất hiện

Nếu meter bị loại khỏi registry, bị lọc bởi MeterFilter, không còn được binder đăng ký hoặc endpoint không xuất metric đó nữa, response scrape thành công tiếp theo sẽ không chứa series này.

Prometheus sử dụng stale marker để đánh dấu series không còn xuất hiện trong scrape. Với instant query, series thường không còn được trả về sau stale marker. Đây là khác biệt với một Counter đang đứng yên, vốn vẫn có mẫu mới ở mỗi lần scrape.

Khi một lần scrape thất bại, Prometheus cũng đánh dấu các series ứng dụng của target đó là stale; metric up vẫn được cập nhật thành 0 để thể hiện scrape thất bại. Khi target hoạt động trở lại, các mẫu mới sẽ tiếp tục hoặc tạo lại series theo label set được scrape. Nếu label set đã đổi, dữ liệu sau phục hồi thuộc một time series mới.

Các nguyên nhân thường gặp:

- Code không còn đăng ký meter do thay đổi cấu hình hoặc điều kiện khởi tạo.
- Một MeterBinder không còn được Spring áp dụng hoặc bị gỡ khỏi cấu hình.
- MeterFilter từ chối meter hoặc thay đổi tên/tag.
- Tag-value đổi khiến series cũ biến mất và một series mới xuất hiện.
- Gauge source bị garbage collector thu hồi.
- Endpoint metrics thay đổi cấu hình hoặc không còn expose metric cần thiết.

Khi một metric bị đổi tag, Prometheus xem tổ hợp label mới là một time series khác. Series cũ sẽ ngừng nhận mẫu và được đánh dấu stale khi không còn xuất hiện trong scrape; series mới bắt đầu có lịch sử riêng. Vì vậy, thay đổi tag có thể tạo khoảng trống trong dashboard ngay cả khi ứng dụng vẫn chạy bình thường.

## 8. Stale marker, lookback và truy vấn lịch sử

Prometheus không coi một series không có mẫu mới là giá trị 0. Khi series biến mất khỏi một lần scrape thành công, Prometheus thường ghi stale marker để thể hiện rằng series đã ngừng tồn tại từ thời điểm đó.

Với instant vector selector, stale marker khiến series không còn được chọn tại thời điểm đánh giá sau đó. Prometheus cũng có cơ chế lookback để tìm mẫu gần nhất trong quá khứ khi không có stale marker; lookback delta mặc định thường là năm phút và có thể được cấu hình.

Với range vector selector như [1h], truy vấn có thể vẫn nhìn thấy các mẫu lịch sử nằm trong khoảng thời gian được chọn, dù series đã stale cho instant query. Vì vậy, hai truy vấn sau có thể cho kết quả khác nhau:

~~~promql
orders_created_total
~~~

~~~promql
last_over_time(orders_created_total[1h])
~~~

Truy vấn đầu lấy giá trị hiện hành theo quy tắc instant selector và staleness. Truy vấn thứ hai tìm mẫu gần nhất trong range một giờ, nên có thể trả lại giá trị cũ của series đã ngừng xuất hiện. Không dùng last_over_time() như bằng chứng rằng meter vẫn đang hoạt động.

Stale marker là cơ chế nội bộ của Prometheus và không phải một mẫu số 0 được ứng dụng xuất ra. Khi điều tra dữ liệu cũ, cần xem timestamp và phạm vi range query.

## 9. Dùng up để kiểm tra sức khỏe scrape

Prometheus tự tạo metric up cho mỗi target:

- up = 1: lần scrape gần nhất thành công.
- up = 0: lần scrape gần nhất thất bại.

up do Prometheus tạo, không phải meter do Micrometer đăng ký trong ứng dụng.

Kiểm tra target của service:

~~~promql
up{job="orders-api"}
~~~

Nếu kết quả bằng 0, kiểm tra trạng thái target trong trang Targets của Prometheus, log scrape, DNS, routing, firewall, cổng, đường dẫn endpoint và xác thực.

Nếu không có series up phù hợp, target có thể đã bị loại khỏi service discovery hoặc bộ lọc target. Khi đó, kiểm tra cấu hình scrape và discovery thay vì chỉ nhìn dashboard metrics của ứng dụng.

## 10. Phân biệt metric bằng 0 với metric không tồn tại

Hai biểu thức có ý nghĩa khác nhau:

~~~promql
orders_created_total == 0
~~~

~~~promql
absent(orders_created_total{job="orders-api"})
~~~

Biểu thức đầu chọn series đang tồn tại với giá trị bằng 0. Biểu thức thứ hai trả về một vector khi không có series phù hợp với selector.

Để kiểm tra metric không có mẫu trong một khoảng thời gian:

~~~promql
absent_over_time(orders_created_total{job="orders-api"}[10m])
~~~

absent_over_time() chỉ trả kết quả khi range không có mẫu nào trong cửa sổ chỉ định. Nếu metric vừa biến mất nhưng mẫu cũ vẫn nằm trong 10 phút đó, truy vấn chưa báo absent. Đây là hành vi hữu ích để phân biệt một khoảng gián đoạn ngắn với việc metric đã biến mất lâu hơn.

Không nên tự động biến mọi trường hợp absent thành 0 bằng or vector(0) nếu chưa hiểu nguyên nhân. Cách đó có thể che giấu lỗi instrumentation hoặc scrape.

## 11. Kiểm tra thời điểm mẫu cuối cùng

Khi series vẫn được trả về bởi instant selector, có thể kiểm tra timestamp của mẫu:

~~~promql
timestamp(orders_created_total{job="orders-api"})
~~~

Để tính tuổi của mẫu đang được chọn:

~~~promql
time() - timestamp(orders_created_total{job="orders-api"})
~~~

Nếu series đã stale và không còn được instant selector chọn, hai biểu thức trên có thể không trả kết quả cho series đó. Trong trường hợp cần xem mẫu lịch sử, hãy dùng range query và kiểm tra timestamp trong kết quả.

Ngoài metric ứng dụng, có thể xem các metric scrape do Prometheus tạo:

| Metric | Mục đích |
| --- | --- |
| scrape_duration_seconds | Thời gian thực hiện scrape. |
| scrape_samples_scraped | Số sample đọc được từ endpoint trong lần scrape. |
| scrape_samples_post_metric_relabeling | Số sample còn lại sau metric relabeling. |

Nếu scrape_samples_scraped vẫn cao nhưng scrape_samples_post_metric_relabeling giảm bất thường, hãy kiểm tra metric relabeling có đang loại bỏ metric cần theo dõi hay không.

## 12. Kiểm chứng một lần restart theo từng bước

Giả sử service orders-api được triển khai lại nhưng target labels vẫn giữ cùng job và instance. Có thể thực hiện quy trình:

1. Ghi lại giá trị Counter trước restart và timestamp mẫu gần nhất.
2. Theo dõi up{job="orders-api"} trong thời gian ứng dụng dừng và khởi động.
3. Sau khi target UP trở lại, kiểm tra endpoint metrics trực tiếp để xác nhận meter được đăng ký.
4. Quan sát Counter có giảm về giá trị ban đầu hay không.
5. Dùng resets(orders_created_total[1h]) để kiểm tra reset trong cửa sổ.
6. Dùng rate() hoặc increase() thay cho phép trừ hai mẫu.
7. Kiểm tra label set trước và sau restart có giữ nguyên không.

Nếu instance label thay đổi sau triển khai, series mới có thể xuất hiện song song với series cũ trong lịch sử. Điều đó không nhất thiết là Counter reset trên cùng series; có thể là một target mới. Hãy phân tích theo job, instance, pod hoặc label triển khai thực tế.

Ví dụ xem tốc độ tạo đơn theo instance:

~~~promql
sum by (instance) (
  rate(orders_created_total{job="orders-api"}[5m])
)
~~~

Nếu muốn tổng hợp toàn service, có thể bỏ instance khỏi phép nhóm:

~~~promql
sum by (job) (
  rate(orders_created_total{job="orders-api"}[5m])
)
~~~

Chỉ gộp khi các series thực sự đại diện cho các phần độc lập của lưu lượng. Nếu cùng một sự kiện được scrape qua nhiều đường hoặc nhiều replica exporter, phép cộng có thể đếm trùng.

## 13. Kiểm chứng meter ngừng ghi nhận sự kiện

Để xác định meter còn hoạt động nhưng không có sự kiện mới:

1. Kiểm tra up vẫn bằng 1.
2. Gọi trực tiếp endpoint metrics và xác nhận tên metric, label vẫn có mặt.
3. Quan sát Counter hoặc Timer count có giữ nguyên qua nhiều lần scrape hay không.
4. Dùng rate() trên cửa sổ đủ dài để xem tốc độ có về 0 không.
5. Xác nhận nghiệp vụ thực sự không phát sinh sự kiện trong khoảng đó.

Ví dụ:

~~~promql
rate(queue_messages_received_total{queue="orders"}[5m])
~~~

Nếu kết quả bằng 0 trong khi target UP và series vẫn tồn tại, có thể queue không nhận message mới. Nếu không có series trả về, cần kiểm tra meter có còn được xuất hay không, tag có thay đổi hay metric có bị relabel/drop.

Đừng kết luận Counter bị lỗi chỉ vì rate bằng 0. Một hệ thống ít lưu lượng có thể thực sự không có sự kiện trong cửa sổ truy vấn. Ngược lại, rate không có dữ liệu có thể do chưa đủ hai mẫu trong range, series vừa xuất hiện hoặc metric đã stale.

## 14. Cấu hình scrape và ảnh hưởng đến khả năng quan sát

Một cấu hình scrape có thể trông như sau:

~~~yaml
scrape_configs:
  - job_name: orders-api
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - orders-api:8080
~~~

Các điểm cần kiểm tra:

- scrape_interval quyết định khoảng cách giữa các lần lấy mẫu.
- scrape_timeout phải nhỏ hơn hoặc bằng scrape_interval.
- metrics_path phải khớp endpoint thực tế.
- Target phải có thể truy cập từ môi trường mạng của Prometheus.
- Cấu hình service discovery phải theo dõi đúng instance sau restart hoặc rollout.
- Metric relabeling không được vô tình loại metric cần quan sát.

Scrape interval quá dài có thể bỏ lỡ biến động ngắn và khó phát hiện reset giữa hai lần scrape. Interval quá ngắn làm tăng tải lên ứng dụng và Prometheus. Chọn chu kỳ theo độ dài sự kiện cần quan sát, lượng series và năng lực hệ thống.

Với rate(), range window thường cần chứa nhiều mẫu; quy tắc thực tế hay dùng là chọn cửa sổ lớn hơn vài lần scrape interval. Ví dụ scrape mỗi 15 giây thì cửa sổ 5 phút có đủ mẫu trong điều kiện scrape ổn định, nhưng cần điều chỉnh theo mục tiêu độ trễ cảnh báo và lưu lượng.

## 15. Thiết kế cảnh báo không đánh đồng các trạng thái

Nên tách cảnh báo theo nguyên nhân:

| Mục tiêu | Biểu thức minh họa | Ý nghĩa |
| --- | --- | --- |
| Target không scrape được | up{job="orders-api"} == 0 | Prometheus không lấy được metrics ở lần scrape gần nhất. |
| Counter không tăng | rate(orders_created_total[10m]) == 0 | Series tồn tại và tốc độ tăng đang bằng 0; cần đối chiếu với lưu lượng kỳ vọng. |
| Metric biến mất lâu | absent_over_time(orders_created_total{job="orders-api"}[10m]) | Không có mẫu metric trong cửa sổ 10 phút. |
| Counter reset | resets(orders_created_total[1h]) > 0 | Có dấu hiệu Counter giảm trong cửa sổ. |

Các biểu thức trên là ví dụ, cần điều chỉnh label, cửa sổ và ngưỡng theo môi trường. Cảnh báo “không có đơn hàng mới” chỉ có ý nghĩa khi service được kỳ vọng phải có lưu lượng; với dịch vụ theo mùa hoặc lưu lượng thấp, nên kết hợp với lịch hoạt động hoặc metric request tổng thể.

Nếu target bị loại khỏi service discovery, up có thể không còn series để so sánh với 0. Khi đó cần một cảnh báo riêng phát hiện target mong đợi không còn xuất hiện, dựa trên inventory hoặc metric giám sát service discovery.

## 16. Bảng chẩn đoán nhanh

| Quan sát | Nguyên nhân có thể | Việc cần làm |
| --- | --- | --- |
| up=0 | Ứng dụng dừng, endpoint lỗi, timeout hoặc network bị chặn | Kiểm tra Targets, log ứng dụng, endpoint, DNS và network. |
| up=1, Counter giữ nguyên | Không có sự kiện mới hoặc code không còn gọi increment | Xác minh lưu lượng nghiệp vụ và điểm ghi nhận Counter. |
| up=1, metric biến mất | Meter không còn đăng ký, MeterFilter loại bỏ, tag đổi hoặc exposition thay đổi | So sánh response endpoint và cấu hình Actuator/registry/filter. |
| Counter giảm sau restart | Process-local counter reset | Dùng rate(), increase() và resets(); kiểm tra process lifecycle. |
| Counter không giảm dù ứng dụng restart | Restart xảy ra giữa hai lần scrape và giá trị mới đã vượt mẫu cũ, hoặc series thuộc target khác | Kiểm tra scrape interval, label target và thời điểm restart. |
| Dashboard có khoảng trống nhưng range query còn dữ liệu cũ | Series đã stale nhưng mẫu cũ vẫn nằm trong range window | Kiểm tra instant selector, range selector và timestamp. |
| Metric bị chia thành hai series | Label set thay đổi | Chuẩn hóa tag và kiểm tra label trước/sau triển khai. |
| Metric không có sample sau relabeling | Rule metric relabeling đã drop series | Kiểm tra scrape_samples_scraped và scrape_samples_post_metric_relabeling. |

## 17. Quy trình xác minh trước khi kết luận

Khi biểu đồ thay đổi sau restart hoặc meter ngừng hoạt động, thực hiện theo thứ tự:

1. **Kiểm tra target:** xem up và trạng thái Targets để xác nhận Prometheus có scrape thành công.
2. **Kiểm tra endpoint:** gọi trực tiếp endpoint metrics và tìm tên metric cùng tag mong đợi.
3. **Kiểm tra identity:** so sánh toàn bộ label set trước và sau sự kiện.
4. **Kiểm tra timestamp:** xác định mẫu mới nhất và khoảng trống trong lịch sử.
5. **Kiểm tra reset:** dùng resets() cho Counter và các chuỗi tích lũy.
6. **Kiểm tra tốc độ:** dùng rate() hoặc increase() thay vì trừ mẫu thủ công.
7. **Phân biệt flat và absent:** xác nhận metric vẫn được xuất nhưng không thay đổi, hay đã biến mất khỏi exposition.
8. **Kiểm tra relabeling:** xác nhận Prometheus không loại series sau khi scrape.
9. **Đối chiếu nghiệp vụ:** xác nhận có sự kiện mới thực sự phát sinh trong khoảng thời gian đó.

Quy trình này tránh sửa instrumentation khi nguyên nhân thực tế nằm ở scrape config, service discovery hoặc truy vấn dashboard.

## 18. Checklist vận hành

- [ ] Đã phân biệt target down, meter phẳng và meter biến mất.
- [ ] Biết Counter trong bộ nhớ có thể reset khi tiến trình khởi động lại.
- [ ] Dùng rate() và increase() cho Counter thay vì phép trừ mẫu thủ công.
- [ ] Biết Prometheus có thể bỏ lỡ reset xảy ra giữa hai lần scrape.
- [ ] Kiểm tra up trước khi kết luận ứng dụng không xuất metrics.
- [ ] Phân biệt giá trị 0 với series absent.
- [ ] Hiểu stale marker và sự khác nhau giữa instant query với range query.
- [ ] Kiểm tra label set khi triển khai hoặc thay đổi tag.
- [ ] Xác minh metric relabeling không loại bỏ series cần thiết.
- [ ] Cảnh báo không đánh đồng không có traffic với instrumentation bị lỗi.
- [ ] Dùng dữ liệu nghiệp vụ bền vững nếu cần số đếm chính xác qua restart.

Prometheus lưu các mẫu theo thời gian và phản ánh đúng những gì endpoint công bố tại từng lần scrape. Muốn xác minh dữ liệu sau restart hoặc khi meter ngừng hoạt động, hãy kiểm tra đồng thời trạng thái target, vòng đời meter, label set, timestamp và ngữ nghĩa truy vấn. Counter phẳng, Counter reset, series stale và target down là những trạng thái khác nhau, cần được chẩn đoán riêng.
