# Đọc Counter bằng rate và độ trễ trung bình từ dữ liệu Timer

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, Micrometer ghi nhận sự kiện và thời lượng qua các meter như `Counter` và `Timer`. Khi xuất sang Prometheus, các meter này trở thành time series có nhãn. PromQL giúp chuyển các giá trị tích lũy thành tốc độ trong một khoảng thời gian, đồng thời tính độ trễ trung bình từ tổng thời gian và số lần ghi nhận của Timer.

Điểm quan trọng là phải hiểu dữ liệu đang được lưu dưới dạng counter tích lũy. `rate()` tính tốc độ tăng mỗi giây và tự xử lý counter reset; Timer cung cấp `_count` và `_sum`, từ đó ta tính được thời lượng trung bình của những lần đo đã hoàn tất. Các truy vấn cần giữ đúng nhãn và thứ tự tổng hợp để không làm sai kết quả khi service chạy nhiều instance.

## 1. Counter và Timer được xuất thành time series

`Counter` trong Micrometer dùng để đếm sự kiện chỉ tăng. Ví dụ, ứng dụng đếm số đơn hàng được tạo:

```java
Counter ordersCreated = Counter.builder("orders.created")
    .description("Number of orders created")
    .tag("channel", "web")
    .register(registry);

ordersCreated.increment();
```

Với Prometheus registry, counter thường được chuẩn hóa thành tên có hậu tố `_total`, chẳng hạn `orders_created_total`, cùng label `channel="web"`. Tên chính xác có thể thay đổi theo quy tắc đặt tên và phiên bản registry; hãy kiểm tra endpoint exposition của ứng dụng trước khi viết truy vấn.

`Timer` ghi nhận thời lượng và số lần thao tác hoàn tất:

```java
Timer createOrder = Timer.builder("orders.create.duration")
    .description("Time spent creating an order")
    .tag("result", "success")
    .register(registry);

createOrder.record(() -> orderService.create(command));
```

Với Prometheus registry, timer thường xuất ít nhất hai chuỗi số liệu quan trọng:

- `<timer_name>_seconds_count`: số lần ghi nhận đã hoàn tất.
- `<timer_name>_seconds_sum`: tổng thời lượng của các lần ghi nhận, tính bằng giây.

Nếu histogram được bật, registry còn xuất các bucket `_bucket`; tùy cấu hình có thể có thêm `_max` hoặc các thống kê khác. Đối với ví dụ trên, tên sau chuẩn hóa có thể là `orders_create_duration_seconds_count` và `orders_create_duration_seconds_sum`.

Timer chỉ cập nhật count và sum khi lần đo kết thúc. Một thao tác vẫn đang chạy chưa được tính vào `_count` hoặc `_sum` cho đến khi `record(...)` hoặc sample được dừng.

## 2. Vì sao cần rate()?

Counter lưu tổng tích lũy kể từ khi meter bắt đầu. Ví dụ, một time series có thể tăng từ 100 lên 160 rồi lên 250. Chỉ nhìn giá trị 250 không cho biết hệ thống đang xử lý bao nhiêu sự kiện mỗi giây.

Prometheus `rate()` tính tốc độ tăng trung bình mỗi giây trong một range vector:

```promql
rate(orders_created_total[5m])
```

Truy vấn này trả về tốc độ tăng của counter trong cửa sổ 5 phút, đơn vị là sự kiện/giây. Prometheus ước lượng độ dốc từ các mẫu trong cửa sổ và điều chỉnh cho counter reset. Vì phép tính được nội suy đến ranh giới cửa sổ, kết quả có thể là số thập phân dù sự kiện được đếm theo số nguyên.

`rate()` phù hợp cho dashboard và alert cần tốc độ tương đối ổn định. Cửa sổ dài làm đường biểu diễn mượt hơn nhưng phản ứng chậm hơn; cửa sổ ngắn phản ứng nhanh nhưng nhạy với dao động và scrape thưa.

## 3. Chọn cửa sổ rate theo scrape interval

Range vector trong `rate(metric[5m])` xác định khoảng thời gian Prometheus dùng để tính tốc độ. Cửa sổ cần chứa đủ mẫu scrape để phép tính ổn định. Một quy tắc thực hành thường dùng là chọn ít nhất khoảng bốn lần scrape interval.

Ví dụ:

| Scrape interval | Cửa sổ rate thường dùng để bắt đầu |
| --- | --- |
| 10 giây | 1 phút |
| 15 giây | 1 phút hoặc 5 phút |
| 30 giây | 2 phút hoặc 5 phút |
| 60 giây | 5 phút |

Đây là điểm bắt đầu, không phải công thức cố định. Hãy cân nhắc độ trễ mong muốn, lưu lượng và cách dashboard hiển thị. Nếu cửa sổ quá ngắn, có thể không đủ hai mẫu hợp lệ sau một lần restart hoặc gián đoạn scrape; nếu quá dài, sự cố ngắn có thể bị làm mờ.

## 4. Tính thông lượng từ Counter

**Số đơn được tạo mỗi giây:**

```promql
rate(orders_created_total[5m])
```

Nếu có nhiều instance, Prometheus lưu một time series cho từng instance. Muốn biết thông lượng toàn service, tính rate cho từng series rồi cộng lại:

```promql
sum(rate(orders_created_total[5m]))
```

Muốn xem theo kênh:

```promql
sum by (channel) (
  rate(orders_created_total[5m])
)
```

Kết quả vẫn có đơn vị sự kiện/giây. Để hiển thị số đơn ước tính mỗi phút, nhân kết quả với 60:

```promql
sum by (channel) (
  rate(orders_created_total[5m])
) * 60
```

Chỉ giữ các label có ý nghĩa và cardinality thấp. Nếu `channel` là tập giá trị hữu hạn như `web`, `mobile` và `partner`, việc nhóm theo kênh hữu ích cho dashboard.

## 5. Dùng increase() để tính số sự kiện trong cửa sổ

`increase()` trả về mức tăng ước tính của counter trong toàn bộ khoảng thời gian chỉ định:

```promql
increase(orders_created_total[1h])
```

Truy vấn này cho biết số đơn ước tính được tạo trong một giờ gần nhất. Kết quả có thể là số thập phân do Prometheus nội suy ở ranh giới range; không nên mặc định nó luôn là số nguyên.

Khi tổng hợp nhiều instance:

```promql
sum by (channel) (
  increase(orders_created_total[1h])
)
```

`increase()` hữu ích cho thống kê lượng sự kiện trong cửa sổ, còn `rate()` thường phù hợp hơn khi vẽ thông lượng liên tục hoặc tạo alert. Về bản chất, `increase()` tương đương `rate()` nhân với độ dài cửa sổ tính theo giây, với cùng cơ chế xử lý reset và nội suy.

## 6. Counter reset khi ứng dụng khởi động lại

Counter trong Micrometer thường nằm trong bộ nhớ của tiến trình. Khi JVM hoặc container khởi động lại, counter bắt đầu lại từ đầu. Ví dụ, time series có thể tăng từ 500 lên 530, sau đó giảm về 0 khi instance restart rồi tăng lên 12.

Đây là counter reset, không nhất thiết là dữ liệu sai. Prometheus `rate()` và `increase()` nhận biết counter giảm và điều chỉnh phép tính để ước lượng mức tăng trong cửa sổ. Điều này hoạt động tốt khi mỗi instance có nhãn nhận diện riêng, chẳng hạn `instance`, `pod` hoặc `instance_id`.

Khi tổng hợp nhiều instance, phải tính rate cho từng time series trước rồi mới cộng:

```promql
sum by (service) (
  rate(orders_created_total[5m])
)
```

Không cộng counter thô của các instance rồi mới tính rate. Nếu một instance reset, tổng đã cộng có thể che mất lần reset hoặc tạo một bước giảm khó diễn giải. `rate()` cần nhìn thấy từng chuỗi riêng để xử lý reset đúng.

## 7. Timer cung cấp count và sum

Một Timer tích lũy hai đại lượng cần thiết để tính độ trễ trung bình:

- `count`: số lần thao tác đã được ghi nhận.
- `sum`: tổng thời lượng của tất cả lần ghi nhận.

Ví dụ, ba request hoàn tất lần lượt trong 0,1 giây, 0,2 giây và 0,3 giây. Khi đó count bằng 3, sum bằng 0,6 giây và trung bình là 0,2 giây/request.

Trong Prometheus, tên metric thường có hậu tố `_seconds_count` và `_seconds_sum`. Đây là các giá trị tích lũy; muốn tính trung bình trong một cửa sổ 5 phút, hãy tính tốc độ tăng của từng đại lượng rồi chia:

```promql
sum(rate(http_server_requests_seconds_sum[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Tử số có đơn vị giây/giây, tức số giây thời lượng được ghi nhận trong mỗi giây thực. Mẫu số có đơn vị request/giây. Chia hai giá trị cho nhau cho kết quả giây/request, chính là độ trễ trung bình của các request hoàn tất trong cửa sổ.

Không dùng trực tiếp `_sum / _count` nếu mục tiêu là trung bình trong 5 phút. Cách chia raw counter cho kết quả trung bình kể từ khi meter bắt đầu, không phải chỉ trong cửa sổ 5 phút.

## 8. Độ trễ trung bình theo route hoặc method

Spring Boot thường tự ghi nhận HTTP server request bằng meter `http.server.requests` khi Actuator và instrumentation web được cấu hình. Prometheus registry chuẩn hóa tên thành dạng như `http_server_requests_seconds_count` và `http_server_requests_seconds_sum`.

Để tính trung bình theo route:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_sum[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Để xem theo method và route:

```promql
sum by (method, uri) (
  rate(http_server_requests_seconds_sum[5m])
)
/
sum by (method, uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Hai vế phải được tổng hợp theo cùng tập label để Prometheus ghép đúng series khi chia. Có thể bổ sung `status` hoặc `outcome` nếu dashboard cần phân biệt kết quả HTTP. Tên tag mặc định có thể thay đổi theo phiên bản Spring Boot hoặc instrumentation; hãy xác nhận label thực tế trước khi dùng.

Với tag `uri`, dùng route template như `/api/orders/{id}`. Không đưa đường dẫn có ID thật vào label, vì mỗi ID có thể tạo time series riêng và làm cardinality tăng nhanh.

## 9. Vì sao phải rate trước rồi mới sum?

Khi service chạy nhiều replica, mỗi instance có một counter riêng. Prometheus cần phát hiện reset của từng counter trước khi các giá trị được cộng thành tổng.

**Cách đúng:**

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

`rate()` xử lý từng time series theo nhãn đầy đủ, gồm cả instance. Sau đó `sum by(uri)` cộng tốc độ giữa các instance nhưng giữ lại chiều route.

**Cách dễ gây sai:**

```promql
rate(
  (sum by (uri) (http_server_requests_seconds_count))[5m:]
)
```

Biểu thức thứ hai tạo một tổng trước khi tính rate. Nếu một instance reset trong khi instance khác vẫn tăng, bước tổng hợp có thể che mất reset của instance đã khởi động lại. Quy tắc thực hành là áp dụng `rate()` hoặc `increase()` lên từng counter series trước khi aggregate.

## 10. Trung bình có trọng số khác với trung bình các instance

Không nên tính độ trễ trung bình toàn service bằng cách lấy trung bình cộng của các độ trễ trung bình từng instance. Mỗi instance có thể xử lý số request khác nhau.

Ví dụ:

| Instance | Số request | Độ trễ trung bình |
| --- | ---: | ---: |
| A | 100 | 100 ms |
| B | 900 | 300 ms |

Trung bình cộng của hai instance là 200 ms, nhưng trung bình của toàn bộ 1.000 request là:

\[
\frac{100\times100 + 900\times300}{100+900}=280\text{ ms}
\]

Truy vấn `sum(rate(_sum)) / sum(rate(_count))` tự tạo ra trung bình có trọng số theo số request, vì tử số và mẫu số đều được cộng từ các quan sát gốc. Tránh `avg()` trên các giá trị trung bình per-instance nếu muốn biết độ trễ trung bình của toàn service.

## 11. Lọc lỗi và tính tỷ lệ lỗi từ Timer count

Timer HTTP có thể mang tag `status` hoặc `outcome`. Nếu muốn tính tỷ lệ phản hồi 5xx, dùng count rate của nhóm lỗi chia cho count rate của toàn bộ request:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Kết quả là tỷ lệ trong khoảng từ 0 đến 1 khi có traffic. Nhân với 100 để hiển thị phần trăm. Nếu muốn phân tích theo route, thêm `uri` vào cả hai vế và giữ cùng tập label.

Nếu ứng dụng không có tag `status`, hãy dùng tag thực tế như `outcome` hoặc bổ sung instrumentation phù hợp. Không suy đoán tên label từ dashboard khác.

## 12. Trung bình không thay thế p95 hoặc p99

Trung bình cho biết tổng thời gian chia cho số lần hoàn tất. Nó có thể che khuất một nhóm nhỏ request rất chậm. Ví dụ, 99 request mất 50 ms và một request mất 5 giây có thể tạo ra trung bình tương đối thấp, trong khi người dùng của request chậm vẫn có trải nghiệm rất xấu.

Nếu cần p95 hoặc p99, phải bật histogram cho Timer và truy vấn bucket. Với classic histogram của Prometheus:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

`histogram_quantile()` ước lượng percentile từ bucket đã tổng hợp. Nếu chỉ có `_sum` và `_count`, ta tính được trung bình nhưng không thể tái dựng p95/p99. Histogram làm tăng số time series nên cần chọn bucket và tag có cardinality phù hợp.

## 13. Không có request trong cửa sổ thì không có độ trễ trung bình

Nếu không có request hoàn tất trong 5 phút, tốc độ tăng của `_count` bằng 0 hoặc không có series trong cửa sổ. Khi đó không có mẫu để tính trung bình có ý nghĩa. Phép chia có thể trả `NaN`, vô cực hoặc không có series tùy dữ liệu và biểu thức.

Dashboard nên thể hiện trạng thái “No data” hoặc ẩn giá trị trung bình khi mẫu số bằng 0. Không tự thay kết quả thành 0 ms, vì 0 ms có nghĩa đã có request và chúng hoàn tất tức thì; điều đó khác hoàn toàn với việc không có request.

Khi service có traffic thấp, tăng cửa sổ từ 1 phút lên 5 hoặc 10 phút có thể giúp truy vấn ổn định hơn. Tuy nhiên, cửa sổ dài cũng làm phản ứng với thay đổi chậm hơn.

## 14. Kiểm tra dữ liệu trước khi viết PromQL

Với Spring Boot, có thể thêm Actuator và Prometheus registry:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Expose endpoint Prometheus trong `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Khi ứng dụng chạy, kiểm tra `/actuator/prometheus` để xác nhận:

- Counter có tên và hậu tố thực tế nào.
- Timer có `_seconds_count` và `_seconds_sum` không.
- Label có đúng `uri`, `method`, `status`, `outcome` như truy vấn dự kiến không.
- Histogram bucket `_bucket` có xuất hiện nếu cần percentile không.
- Các instance có label phân biệt để Prometheus nhận biết từng chuỗi counter không.

Sau đó tạo một số request thử, chờ ít nhất vài lần scrape và quan sát counter tăng. Với Timer, so sánh count và sum trước/sau khi các request hoàn tất. Không kỳ vọng request đang chạy đã được cộng vào count.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| `rate()` trả về rỗng | Range window chưa có đủ mẫu scrape hoặc tên/label metric sai |
| Tốc độ tăng đột biến sau restart | Counter reset, nhãn instance thay đổi hoặc truy vấn aggregate trước rate |
| Thông lượng toàn service thấp hơn tổng từng instance | Có filter hoặc grouping label làm mất series; kiểm tra selector và `sum by` |
| Độ trễ trung bình sai đơn vị | Chia metric không cùng đơn vị hoặc dùng timer metric không có hậu tố `_seconds` như dự kiến |
| Trung bình thay đổi dù latency từng instance ổn định | Lưu lượng giữa các instance thay đổi; dùng tỷ lệ tổng sum trên tổng count |
| Trung bình bằng 0 khi không có request | Dashboard đã thay no-data bằng 0; không có quan sát thì không có độ trễ trung bình |
| Không thấy p95 | Histogram chưa bật hoặc truy vấn không có `_bucket` và label `le` |
| p95 toàn service sai | Đang lấy trung bình các quantile client-side thay vì tổng hợp histogram bucket |
| Timer count thấp hơn số request đang chạy | Timer chỉ ghi nhận khi thao tác hoàn tất |

Khi truy vấn sai, hãy xác nhận tên metric và label từ exposition trước, kiểm tra reset và số mẫu scrape tiếp theo, rồi xác minh thứ tự `rate` trước `sum`. Đối với độ trễ, kiểm tra riêng `_sum`, `_count` và đơn vị trước khi đánh giá biểu thức trung bình.

## 16. Nguyên tắc áp dụng

Dùng `rate()` để chuyển counter tích lũy thành tốc độ mỗi giây và `increase()` để ước lượng lượng sự kiện trong một cửa sổ. Khi có nhiều instance, áp dụng hàm này lên từng time series trước rồi mới tổng hợp. Prometheus xử lý counter reset tốt hơn khi còn nhìn thấy nhãn nhận diện từng instance.

Với Timer, tính độ trễ trung bình trong cửa sổ bằng tốc độ tăng của `_sum` chia cho tốc độ tăng của `_count`. Giữ cùng tập label ở hai vế, hiểu kết quả theo đơn vị giây/request và xử lý riêng trường hợp không có request. Trung bình mô tả xu hướng chung; muốn quan sát đuôi phân phối, hãy bật histogram và truy vấn p95/p99 từ bucket.
