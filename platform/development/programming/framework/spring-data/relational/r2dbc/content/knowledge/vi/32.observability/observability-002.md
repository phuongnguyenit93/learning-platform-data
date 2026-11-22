# Quan sát pool: kết nối đang dùng, nhàn rỗi và yêu cầu chờ

## 1. Vì sao cần quan sát R2DBC connection pool?

Trong ứng dụng Spring WebFlux và Spring Data Relational R2DBC, connection pool quản lý một tập connection có thể tái sử dụng để truy cập database. Khi một thao tác cần database, ứng dụng mượn một connection từ pool. Khi thao tác kết thúc và connection được giải phóng đúng cách, pool có thể đưa connection đó trở lại trạng thái nhàn rỗi để request khác sử dụng.

Pool giúp tránh chi phí tạo kết nối vật lý cho mọi câu SQL và giới hạn số connection mà một instance ứng dụng có thể mở tới database. Tuy nhiên, pool cũng là một tài nguyên hữu hạn. Khi tất cả connection đã được mượn, request mới phải chờ hoặc thất bại nếu vượt timeout hay giới hạn hàng đợi.

Chỉ nhìn thời gian phản hồi của API không đủ để biết vấn đề nằm ở đâu. Một endpoint chậm có thể do:

- Database query chạy lâu.
- Connection pool đã hết connection nhàn rỗi.
- Request phải chờ trong hàng đợi acquire.
- Connection được giữ lâu trong transaction hoặc khi stream kết quả.
- Database từ chối tạo connection mới.
- Một dịch vụ bên ngoài đang chậm trong khi transaction R2DBC vẫn giữ connection.
- Tải tăng vượt giới hạn pool hoặc giới hạn connection của database.

Để chẩn đoán, cần quan sát ít nhất bốn trạng thái cốt lõi:

- **Acquired:** số connection đang được ứng dụng mượn khỏi pool.
- **Allocated:** số connection pool đã tạo hoặc đang quản lý.
- **Idle:** số connection đang nhàn rỗi, sẵn sàng được mượn.
- **Pending:** số yêu cầu đang chờ được cấp connection.

Bốn số liệu này cho biết pool đang còn dư khả năng, đang hoạt động bình thường ở tải cao, hay đã bị bão hòa. Bài này trình bày cách đọc các chỉ số, bật quan sát qua Micrometer và Spring Boot Actuator, đặt cảnh báo và lần theo nguyên nhân khi pool cạn.

## 2. Vòng đời của một connection trong pool

Một pool thường quản lý connection qua các trạng thái khái niệm sau:

~~~text
                Ứng dụng cần database
                         |
                         v
                Yêu cầu acquire connection
                         |
              +----------+----------+
              |                     |
              v                     v
       Có connection idle     Chưa có connection
              |                     |
              v                     v
       Chuyển sang acquired   Còn chỗ tạo mới?
                                    |
                          +---------+---------+
                          |                   |
                         Có                  Không
                          |                   |
                          v                   v
                   Tạo connection       Đưa request vào
                   rồi cấp cho app      hàng đợi pending
                          |                   |
                          v                   v
                       Acquired         Chờ connection được
                                        giải phóng hoặc tạo mới
              |                     |
              +----------+----------+
                         |
                         v
                Thao tác database hoàn tất
                         |
                         v
                 Release connection
                         |
                         v
                 Trở lại trạng thái idle
~~~

Trong vận hành thực tế, pool còn có các bước validation, eviction, timeout và xử lý connection lỗi. Sơ đồ trên chỉ mô tả luồng chính.

### 2.1. Acquired: connection đang được mượn

Acquired là số connection hiện đang được cấp cho consumer. Chúng chưa được trả về pool.

Một connection acquired có thể đang:

- Thực thi SQL.
- Chờ database trả kết quả.
- Nằm trong một transaction đang mở.
- Được giữ bởi một callback sử dụng Connection trực tiếp.
- Đang stream kết quả qua Flux.
- Chờ một bước xử lý khác trong cùng phạm vi giữ connection.

Vì vậy, acquired không đồng nghĩa với số câu SQL đang chạy tại database. Một connection có thể acquired nhưng tại thời điểm quan sát không có câu SQL nào thực thi, ví dụ service đang chờ HTTP call bên ngoài trong khi transaction vẫn mở.

Acquired tăng khi có nhiều thao tác đồng thời hoặc khi mỗi thao tác giữ connection lâu. Cần xem cùng pending, idle, pool max size và thời gian xử lý để kết luận.

### 2.2. Allocated: tổng connection pool quản lý

Allocated biểu diễn số connection đã được pool tạo hoặc phân bổ để quản lý. Trong cách đọc thông thường:

- Một phần allocated đang được acquired.
- Phần còn lại đang idle.
- Pool có thể tạo thêm connection cho tới giới hạn max size nếu có nhu cầu và database cho phép.

Trong trạng thái ổn định, acquired cộng idle thường xấp xỉ allocated. Khi pool đang tạo, đóng hoặc kiểm tra connection, số liệu có thể chuyển trạng thái và không nhất thiết khớp tuyệt đối ở mọi thời điểm.

Allocated giúp trả lời câu hỏi: pool đã mở bao nhiêu connection và còn khả năng mở thêm hay không?

Không nhầm allocated với max size. Ví dụ max size là 20 nhưng allocated mới là 8, pool vẫn có thể tạo thêm connection nếu có nhu cầu và database chấp nhận.

### 2.3. Idle: connection đang sẵn sàng

Idle là số connection đang nằm trong pool và chưa được consumer mượn. Đây là phần năng lực có thể cấp ngay cho yêu cầu mới.

Idle bằng 0 không nhất thiết là lỗi. Nếu tải ổn định, pool có thể sử dụng gần hết connection mà không có request nào phải chờ. Vấn đề xuất hiện khi idle bằng 0 kéo dài, acquired chạm giới hạn và pending tăng.

Idle quá cao trong thời gian dài có thể cho thấy pool được cấu hình lớn hơn nhu cầu. Tuy nhiên, không nên giảm pool chỉ dựa trên một ảnh chụp ngắn; cần quan sát theo giờ cao điểm, độ trễ và khả năng tăng tải.

### 2.4. Pending: yêu cầu đang chờ acquire

Pending là số yêu cầu đã xin connection nhưng chưa được cấp. Chúng đang chờ một connection được release hoặc chờ pool tạo thêm connection.

Pending là tín hiệu trực tiếp cho thấy ứng dụng không thể lấy connection ngay lập tức.

- Pending bằng 0: tại thời điểm đo không có yêu cầu acquire đang chờ.
- Pending tăng ngắn hạn: có thể là burst tải ngắn và không nhất thiết là sự cố.
- Pending tăng liên tục: pool có thể đã bão hòa hoặc việc tạo connection mới quá chậm.
- Pending đạt giới hạn hàng đợi: yêu cầu mới có thể bị từ chối tùy cấu hình pool.

Cần quan sát cả thời gian chờ acquire và số lần acquire timeout. Một hàng đợi nhỏ nhưng request chờ lâu vẫn có thể làm độ trễ API vượt SLO.

## 3. Đọc bốn chỉ số cùng nhau

Không nên kết luận từ một gauge riêng lẻ. Bảng sau minh họa một số trạng thái:

| Acquired | Idle | Pending | Cách diễn giải ban đầu |
|---|---|---|---|
| Thấp | Cao | 0 | Pool còn dư năng lực |
| Cao | Còn một ít | 0 | Tải sử dụng pool cao nhưng chưa có hàng đợi |
| Gần max | 0 | Tăng | Có dấu hiệu pool bão hòa |
| Bằng max | 0 | Cao kéo dài | Pool không cấp đủ connection cho tải hiện tại |
| Thấp hơn max | 0 | Tăng | Có thể tạo connection chậm, lỗi tạo connection hoặc cấu hình giới hạn khác |
| Thấp | Cao | 0 | Pool không phải nguyên nhân rõ ràng của độ trễ hiện tại |

Ví dụ pool có max size bằng 20:

| Chỉ số | Giá trị | Ý nghĩa |
|---|---:|---|
| allocated | 20 | Pool đã tạo đủ số connection tối đa |
| acquired | 20 | Tất cả connection đang được mượn |
| idle | 0 | Không còn connection sẵn sàng |
| pending | 35 | Có 35 yêu cầu đang chờ |

Đây là dấu hiệu rõ ràng của saturation. Tuy nhiên, tăng max size ngay chưa chắc giải quyết được nguyên nhân. Nếu query chậm hoặc transaction giữ connection lâu, pool lớn hơn chỉ chuyển áp lực sang database và có thể làm database quá tải.

Một ví dụ khác:

| Chỉ số | Giá trị | Ý nghĩa |
|---|---:|---|
| allocated | 12 | Pool chưa cần mở hết max size 30 |
| acquired | 3 | Chỉ 3 connection đang được mượn |
| idle | 9 | Còn nhiều connection sẵn sàng |
| pending | 0 | Không có yêu cầu phải chờ |

Nếu API vẫn chậm trong tình huống này, hãy xem query latency, downstream, CPU, event-loop và network. Pool không phải nghi phạm đầu tiên.

## 4. Các metric phổ biến của R2DBC Pool

Khi sử dụng R2DBC Pool cùng tích hợp Micrometer phù hợp, các metric pool phổ biến có tên:

| Metric | Ý nghĩa |
|---|---|
| r2dbc.pool.acquired | Số connection đang được mượn |
| r2dbc.pool.allocated | Số connection pool đã phân bổ |
| r2dbc.pool.idle | Số connection đang nhàn rỗi |
| r2dbc.pool.pending | Số yêu cầu đang chờ acquire |
| r2dbc.pool.max.allocated | Mức allocated tối đa được ghi nhận, nếu phiên bản cung cấp |
| r2dbc.pool.max.pending | Mức pending tối đa được ghi nhận, nếu phiên bản cung cấp |

Danh sách metric, tag và cách bật phụ thuộc phiên bản R2DBC Pool, Micrometer và cấu hình ứng dụng. Không nên giả định mọi phiên bản đều xuất toàn bộ metric trong bảng. Hãy kiểm tra endpoint Actuator và tài liệu đúng phiên bản đang chạy.

Các metric acquired, allocated, idle và pending thường là gauge: chúng biểu diễn trạng thái tại thời điểm quan sát, không phải tổng số request tích lũy từ lúc ứng dụng khởi động.

### 4.1. Gauge khác counter như thế nào?

Gauge có thể tăng hoặc giảm theo trạng thái hiện tại:

- Acquired tăng khi connection được mượn.
- Acquired giảm khi connection được release.
- Idle tăng khi connection trở lại pool.
- Pending tăng khi request phải chờ và giảm khi được cấp connection hoặc bị hủy.

Counter thường chỉ tăng, ví dụ tổng số request, tổng số lỗi hoặc tổng số timeout kể từ lần reset process/registry.

Không áp dụng phép tính rate() cho gauge như thể nó là counter. Với gauge, thường quan sát giá trị hiện tại, max, average theo cửa sổ hoặc thời gian liên tục vượt ngưỡng.

### 4.2. Metric tên giống nhau nhưng tag khác nhau

Khi có nhiều pool, metric cần được phân biệt theo tag nhận diện pool. Tag có thể mang tên như name, pool hoặc một key do tích hợp cụ thể cung cấp.

Không tự giả định tag luôn tên là name. Hãy đọc danh sách availableTags trên Actuator hoặc label trên Prometheus để biết chính xác tag đang được xuất.

Tên pool nên ổn định và có ý nghĩa như orders, audit hoặc reporting. Không đưa customer ID, request ID hay giá trị thay đổi theo từng request vào tag vì sẽ tạo cardinality rất lớn.

## 5. Bật quan sát bằng Spring Boot Actuator và Micrometer

### 5.1. Các dependency thường dùng

Với ứng dụng Spring Boot, thường cần:

- Spring Boot Actuator để cung cấp endpoint quản trị và metric.
- Micrometer registry tương ứng với hệ thống quan sát, ví dụ Prometheus registry nếu dùng Prometheus.
- R2DBC Pool nếu ứng dụng dùng connection pool.
- Driver R2DBC của database.

Tên artifact và phiên bản cần theo Spring Boot dependency management của dự án. Không tự trộn phiên bản Micrometer hoặc R2DBC Pool khác major version với phiên bản Spring Boot đang sử dụng.

### 5.2. Expose endpoint metrics

Ví dụ application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Hoặc dùng properties:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
~~~

Endpoint metrics cho phép xem một meter cụ thể. Endpoint Prometheus xuất metric theo định dạng Prometheus nếu registry tương ứng được cấu hình.

Trong production, cần bảo vệ endpoint quản trị bằng security, network policy hoặc cơ chế triển khai phù hợp. Không expose mọi endpoint quản trị công khai ra Internet.

### 5.3. Kiểm tra metric bằng Actuator

Có thể truy cập:

~~~http
GET /actuator/metrics
~~~

Để xem danh sách meter có sẵn. Sau đó truy vấn một metric cụ thể:

~~~http
GET /actuator/metrics/r2dbc.pool.acquired
GET /actuator/metrics/r2dbc.pool.allocated
GET /actuator/metrics/r2dbc.pool.idle
GET /actuator/metrics/r2dbc.pool.pending
~~~

Response của Actuator thường chứa tên metric, measurement và các availableTags. Nếu ứng dụng có nhiều pool, dùng tag thực tế được trả về để lọc một pool cụ thể.

Ví dụ minh họa cấu trúc response:

~~~json
{
  "name": "r2dbc.pool.acquired",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 8.0
    }
  ],
  "availableTags": [
    {
      "tag": "name",
      "values": ["orders", "audit"]
    }
  ]
}
~~~

Đây là ví dụ cấu trúc để minh họa cách đọc, không phải response cố định của mọi phiên bản. Tên tag và giá trị phụ thuộc cấu hình pool và registry.

Khi đã biết tag, có thể truy vấn theo tag, ví dụ:

~~~http
GET /actuator/metrics/r2dbc.pool.acquired?tag=name:orders
~~~

Chỉ dùng name nếu endpoint của ứng dụng thực sự công bố tag đó. Nếu tag là pool, hãy dùng đúng tên được trả về.

### 5.4. Endpoint metrics không phải dashboard lịch sử

Actuator metrics endpoint thường cho biết giá trị hiện tại hoặc snapshot của meter trong process. Nó không tự lưu lịch sử dài hạn và không thay thế hệ thống time-series.

Để quan sát xu hướng, cần scrape metric định kỳ vào Prometheus hoặc registry tương ứng, sau đó hiển thị trên dashboard và cấu hình alert.

## 6. Dùng Prometheus để quan sát pool

Nếu ứng dụng dùng Micrometer Prometheus registry, endpoint thường là:

~~~http
GET /actuator/prometheus
~~~

Metric có dấu chấm thường được chuyển thành tên phù hợp Prometheus, ví dụ:

~~~text
r2dbc_pool_acquired
r2dbc_pool_allocated
r2dbc_pool_idle
r2dbc_pool_pending
~~~

Tên thực tế có thể thay đổi theo phiên bản và cấu hình. Hãy kiểm tra trực tiếp nội dung endpoint trước khi viết dashboard hoặc alert.

### 6.1. Theo dõi pending

Ví dụ PromQL khái niệm:

~~~promql
r2dbc_pool_pending
~~~

Biểu đồ này cho thấy số yêu cầu đang chờ theo thời gian, tách theo label pool nếu metric có label tương ứng.

Một cảnh báo có thể bắt đầu từ điều kiện pending lớn hơn 0 liên tục trong một khoảng thời gian:

~~~promql
max_over_time(r2dbc_pool_pending[2m]) > 0
~~~

Đây chỉ là ví dụ. Trong production, nên bổ sung label pool, instance và điều kiện thời gian phù hợp với tải bình thường. Một spike ngắn không nhất thiết cần đánh thức on-call.

### 6.2. Theo dõi mức sử dụng pool

Có thể theo dõi acquired so với max size cấu hình. Nếu metric max allocated không phản ánh cấu hình max size mà chỉ là mức cao nhất đã ghi nhận, hãy dùng một metric cấu hình riêng hoặc dashboard variable để tính tỷ lệ.

Công thức khái niệm:

~~~text
pool utilization = acquired / configured max size
~~~

Ví dụ max size 20 và acquired 18 thì mức sử dụng là 90%.

Đừng dùng allocated làm mẫu số một cách máy móc nếu mục tiêu là so với max size cấu hình. Allocated có thể mới chỉ là số connection hiện đã tạo và chưa đạt giới hạn.

### 6.3. Theo dõi acquire timeout

Một số phiên bản/tích hợp cung cấp metric hoặc observation cho acquire timeout, create connection time và các lỗi pool. Nếu không có metric sẵn, có thể ghi nhận lỗi ở lớp service hoặc lớp acquire connection bằng Micrometer counter/timer riêng.

Các tên meter cụ thể cần được xác nhận từ phiên bản thư viện. Không tạo dashboard dựa trên metric giả định chưa được xuất.

### 6.4. Theo dõi từng pool và từng instance

Trong triển khai nhiều instance, cần phân biệt:

- Pool orders trên instance A.
- Pool orders trên instance B.
- Pool audit trên instance A.
- Pool audit trên instance B.

Nếu dashboard chỉ gộp tất cả thành một số tổng, có thể bỏ sót một instance bị bão hòa cục bộ. Hãy giữ các label có giá trị chẩn đoán như pool name, application, environment và instance.

Không thêm label có cardinality cao như user ID, order ID hoặc SQL parameter.

## 7. Cấu hình pool và liên hệ với metric

Các metric chỉ có ý nghĩa khi hiểu cấu hình pool đang dùng.

Ví dụ cấu hình thủ công với R2DBC Pool:

~~~java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(driverConnectionFactory)
        .name("orders")
        .initialSize(2)
        .maxSize(20)
        .maxPendingAcquire(100)
        .maxAcquireTime(Duration.ofSeconds(3))
        .maxCreateConnectionTime(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofMinutes(10))
        .maxLifeTime(Duration.ofMinutes(30))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

Ví dụ minh họa các thuộc tính phổ biến. API builder và thuộc tính được hỗ trợ cần đối chiếu với phiên bản R2DBC Pool của dự án.

Ý nghĩa:

- initialSize: số connection khởi tạo ban đầu.
- maxSize: giới hạn connection pool có thể quản lý.
- maxPendingAcquire: giới hạn số yêu cầu chờ acquire.
- maxAcquireTime: thời gian tối đa chờ cấp connection.
- maxCreateConnectionTime: giới hạn thời gian tạo connection mới.
- maxIdleTime: thời gian connection được phép nhàn rỗi trước khi bị loại bỏ theo cấu hình.
- maxLifeTime: vòng đời tối đa của connection trong pool.
- name: tên nhận diện pool, có thể được dùng trong metric tag tùy tích hợp.

Khi dùng Spring Boot auto-configuration cho một nguồn dữ liệu, các thuộc tính pool thường nằm dưới spring.r2dbc.pool.* nếu pool được bật và dependency phù hợp có mặt. Với nhiều ConnectionFactory tự tạo, cần cấu hình pool riêng cho từng nguồn dữ liệu thay vì giả định một prefix auto-config mặc định tự tạo tất cả pool.

### 7.1. Không tăng maxSize chỉ vì acquired cao

Acquired cao có thể là tải bình thường. Cần xem:

- Pending có tăng không?
- Acquire wait có vượt SLO không?
- Query latency có tăng không?
- Database còn capacity không?
- Số connection tổng từ mọi application instance là bao nhiêu?

Nếu pending bằng 0 và API vẫn đáp ứng SLO, pool có thể đang được sử dụng hiệu quả.

### 7.2. maxPendingAcquire là giới hạn hàng đợi

Hàng đợi quá lớn không làm database xử lý nhanh hơn. Nó có thể chỉ khiến request chờ lâu hơn, giữ thêm bộ nhớ và làm độ trễ tail tăng.

Hãy chọn giới hạn hàng đợi dựa trên thời gian chờ chấp nhận được. Nếu pool bão hòa, hệ thống cần backpressure hoặc từ chối sớm thay vì tích lũy vô hạn yêu cầu.

### 7.3. Timeout acquire và timeout query là hai việc khác nhau

- Acquire timeout giới hạn thời gian chờ lấy connection từ pool.
- Query timeout giới hạn thời gian chờ thực thi một câu SQL hoặc thao tác database theo hỗ trợ driver/framework.
- HTTP timeout giới hạn thời gian client chờ response.
- Transaction timeout giới hạn thời gian transaction theo khả năng transaction manager.

Một request có thể hết acquire timeout trước khi câu SQL bắt đầu. Không nên gộp tất cả thành một thông báo database query timeout.

## 8. Phân biệt connection đang dùng với query đang chạy

Đây là một trong những hiểu nhầm phổ biến nhất khi đọc dashboard.

**Acquired không phải active query count.**

Ví dụ một service thực hiện:

~~~java
@Transactional
public Mono<Order> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            paymentClient.authorize(order)
                .flatMap(result -> {
                    order.setStatus("PAID");
                    return orderRepository.save(order);
                })
        );
}
~~~

Nếu paymentClient mất 8 giây mới trả kết quả, transaction reactive có thể vẫn đang giữ connection R2DBC trong thời gian chờ đó. Trong phần lớn khoảng thời gian này, không có query nào chạy nhưng acquired vẫn tăng.

Các tình huống khác cũng có thể giữ acquired:

- Flux đọc dữ liệu được tiêu thụ chậm.
- Một callback inConnection đang chờ publisher hoàn tất.
- Một transaction được mở quá rộng.
- Code tự acquire connection nhưng quên release.
- Một publisher không hoàn tất hoặc không được cancel đúng cách.

Để hiểu query đang chạy, cần kết hợp metric pool với database monitoring, query statistics, tracing hoặc instrumentation ở lớp thực thi SQL. Pool metric chỉ cho biết trạng thái mượn connection.

## 9. Chẩn đoán các mẫu pool saturation

### 9.1. Acquired chạm max, idle bằng 0, pending tăng

Đây là mẫu saturation rõ nhất.

Quy trình điều tra:

1. Xác định pool nào đang bão hòa.
2. Xem pending bắt đầu tăng từ thời điểm nào.
3. So sánh query latency và transaction duration.
4. Kiểm tra database CPU, lock wait và số session.
5. Tìm request/transaction giữ connection lâu.
6. Kiểm tra downstream call có nằm trong transaction không.
7. Kiểm tra publisher có bị giữ bởi Flux consumer chậm không.
8. Kiểm tra code có acquire connection thủ công và thiếu cleanup không.

Tăng maxSize chỉ nên thực hiện sau khi xác nhận database còn capacity và connection được sử dụng hiệu quả.

### 9.2. Acquired thấp hơn max nhưng pending vẫn tăng

Pool chưa đạt max size nhưng yêu cầu vẫn chờ có thể do:

- Pool đang tạo connection mới chậm.
- Database từ chối hoặc giới hạn số connection mới.
- maxCreateConnectionTime bị chạm.
- Connection validation hoặc initialization mất thời gian.
- Một giới hạn khác trong pool hoặc driver đang tác động.
- Metric được lấy ở thời điểm khác nhau và có độ trễ quan sát.

Kiểm tra log lỗi tạo connection, thời gian connect, DNS, network, TLS, database authentication và giới hạn connection phía server.

### 9.3. Allocated đạt max nhưng acquired không cao

Có thể pool giữ nhiều connection idle do tải trước đó hoặc min idle. Đây không phải vấn đề nếu idle vẫn sẵn sàng và pending bằng 0.

Nếu database bị quá nhiều session dù application load thấp, xem xét max size, min idle, max idle time và số instance ứng dụng.

### 9.4. Idle bằng 0 nhưng pending bằng 0

Có thể tất cả connection đang được sử dụng nhưng chưa có request nào phải chờ. Đây có thể là tải cao bình thường.

Cần theo dõi thêm:
- Acquire latency.
- Pending có tăng khi burst tiếp theo không.
- API latency.
- Query latency.
- Transaction duration.

Một snapshot idle bằng 0 không đủ để kết luận pool cần tăng.

### 9.5. Pending tăng cùng query latency

Nếu query latency tăng trước rồi acquired và pending tăng theo, nguyên nhân có thể nằm ở database hoặc câu SQL:

- Query thiếu index.
- Lock contention.
- Database CPU hoặc I/O cao.
- Execution plan thay đổi.
- Database đang vacuum/checkpoint hoặc thực hiện tác vụ nền nặng.
- Một truy vấn đọc quá nhiều hàng.

Pool saturation lúc này có thể là triệu chứng của database chậm, không phải nguyên nhân gốc.

### 9.6. Pending tăng cùng transaction duration

Nếu transaction duration tăng nhưng query latency không tăng tương ứng, hãy tìm công việc nằm giữa các thao tác SQL:

- HTTP call hoặc SDK blocking.
- Gửi message.
- Xử lý file.
- Chờ người dùng hoặc một publisher khác.
- Retry có thời gian chờ.
- Stream kết quả với consumer chậm.

Thu hẹp transaction để chỉ bao quanh thao tác database cần tính nguyên tử.

## 10. Những nguyên nhân thường khiến connection bị giữ lâu

### 10.1. Transaction bao quanh lời gọi bên ngoài database

Không giữ transaction R2DBC trong lúc chờ payment gateway, HTTP service hoặc email provider nếu nghiệp vụ không yêu cầu điều đó.

Hãy tách thành:
1. Đọc dữ liệu cần thiết.
2. Kết thúc transaction đọc nếu có.
3. Gọi dịch vụ ngoài.
4. Mở transaction ghi ngắn, tải lại trạng thái và cập nhật kết quả.

Nếu cần phối hợp đáng tin cậy, dùng outbox, saga và idempotency thay vì giữ connection trong suốt quy trình.

### 10.2. Flux được tiêu thụ chậm

Với thao tác trả Flux, connection có thể còn được giữ trong thời gian publisher đang đọc kết quả.

Nếu downstream xử lý từng hàng rất chậm hoặc đẩy dữ liệu tới client HTTP có tốc độ thấp, connection có thể bị chiếm lâu.

Cân nhắc:
- Phân trang.
- Giới hạn số hàng.
- Chuyển dữ liệu sang DTO nhẹ.
- Không thực hiện công việc blocking trong callback xử lý Row.
- Tách phần xử lý ngoài database sau khi đọc xong nếu có thể.
- Tránh transaction dài chỉ để stream dữ liệu lớn.

### 10.3. Không release connection khi dùng R2DBC SPI trực tiếp

Nếu ứng dụng tự gọi ConnectionFactory.create(), nó chịu trách nhiệm giải phóng connection trong mọi đường complete, error và cancel.

Với publisher, có thể dùng usingWhen để quản lý cleanup bất đồng bộ:

~~~java
Mono.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> executeQuery(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
~~~

Nếu chỉ cần truy cập connection trong phạm vi callback, ưu tiên DatabaseClient.inConnection hoặc inConnectionMany để Spring quản lý vòng đời theo cơ chế của nó. Không tự close connection mà DatabaseClient hoặc transaction manager đang quản lý.

### 10.4. Publisher không hoàn tất

Một publisher không hoàn tất có thể giữ connection và transaction lâu hơn dự kiến. Kiểm tra:

- Mono/Flux có chờ một nguồn không bao giờ phát tín hiệu không?
- Có ghép publisher vô hạn vào transaction không?
- Có tạo subscription lồng nhau khiến cleanup không chạy theo luồng chính không?
- Có callback bị treo hoặc blocking không có timeout không?

Đặt timeout ở đúng lớp và bảo đảm cleanup theo reactive lifecycle.

## 11. Quan sát nhiều pool trong cùng ứng dụng

Ứng dụng có thể có nhiều ConnectionFactory như orders, audit và reporting. Mỗi pool cần được quan sát riêng.

Ví dụ:

| Pool | Max size | Vai trò |
|---|---:|---|
| orders | 20 | Giao dịch đơn hàng |
| audit | 8 | Ghi lịch sử |
| reporting | 12 | Truy vấn báo cáo |

Dashboard nên có một nhóm panel cho mỗi pool:

- Acquired.
- Allocated.
- Idle.
- Pending.
- Acquire timeout/error.
- Acquire wait nếu có instrumentation.
- Pool utilization so với max size.

Không chỉ nhìn tổng connection của ứng dụng. Pool orders có thể bão hòa trong khi pool audit còn dư. Nếu chỉ nhìn tổng, sự cố cục bộ có thể bị che khuất.

### 11.1. Tính ngân sách connection cho tất cả instance

Giả sử một instance có ba pool:

- orders max size = 20.
- audit max size = 8.
- reporting max size = 12.

Một instance có thể mở tối đa 40 connection. Nếu chạy 5 instance, giới hạn tiềm năng là 200 connection, chưa tính các ứng dụng khác, migration job, admin client và worker.

Hãy tính:

~~~text
Tổng connection tiềm năng
  = số instance
    x tổng max size của các pool trên mỗi instance
    + connection từ các workload khác
~~~

Đối chiếu con số này với giới hạn connection của database và phần dự phòng cho vận hành. Không cấu hình max size riêng lẻ mà bỏ qua số replica.

### 11.2. Tách tên pool rõ ràng

Tên pool ổn định giúp metric có thể lọc theo datasource. Dùng tên ngắn và có ý nghĩa, ví dụ orders, audit, reporting.

Tránh:
- Tạo tên pool mới theo từng request.
- Gắn customer ID vào metric tag.
- Gắn SQL đầy đủ hoặc query parameter vào tag.
- Dùng tên thay đổi theo thời gian triển khai nếu không cần thiết.

Tag cardinality cao làm tăng bộ nhớ và chi phí lưu trữ của hệ thống metrics.

## 12. Đặt cảnh báo có ý nghĩa

Không có một ngưỡng duy nhất phù hợp với mọi hệ thống. Hãy dựa trên SLO, pool max size, thời gian xử lý và baseline của ứng dụng.

Các tín hiệu thường hữu ích:

| Tín hiệu | Ý nghĩa | Hành động |
|---|---|---|
| Pending lớn hơn 0 liên tục | Có yêu cầu chờ acquire | Kiểm tra saturation và thời gian chờ |
| Acquired gần max trong thời gian dài | Pool gần hết năng lực | Kiểm tra connection hold time và DB capacity |
| Idle bằng 0 cùng pending tăng | Không còn connection sẵn sàng | Điều tra pool saturation |
| Acquire timeout tăng | Request không lấy được connection đúng hạn | Kiểm tra pool, DB và timeout |
| Create connection failure tăng | Pool không mở được connection mới | Kiểm tra database, network, credentials và giới hạn session |
| Transaction duration tăng | Connection có thể bị giữ lâu | Tìm transaction dài và side effect ngoài DB |
| API latency tăng nhưng pool còn idle | Nguyên nhân có thể nằm ở lớp khác | Kiểm tra query, CPU, downstream và event-loop |

### 12.1. Cảnh báo theo thời gian liên tục

Một pending spike ngắn có thể là burst bình thường. Cảnh báo nên yêu cầu điều kiện tồn tại trong một khoảng thời gian, ví dụ pending lớn hơn 0 liên tục 2 phút, tùy hệ thống.

Ví dụ PromQL khái niệm:

~~~promql
max_over_time(r2dbc_pool_pending[2m]) > 0
~~~

Trong dashboard thật, thêm label lọc pool và environment dựa trên label đang được xuất. Nếu cần alert theo từng pool, nhóm theo label pool tương ứng.

### 12.2. Kết hợp metric pool với SLO

Pool utilization cao không nhất thiết là sự cố nếu API latency và error rate vẫn tốt. Ngược lại, pending nhỏ nhưng kéo dài có thể gây p99 latency xấu.

Một cảnh báo có chất lượng nên kết hợp:
- Pending hoặc acquire timeout.
- API latency.
- Error rate.
- Transaction duration.
- Database latency hoặc saturation.

Không alert chỉ vì acquired đạt 90% một lần. Hãy xem mức độ kéo dài và tác động đến người dùng.

## 13. Xây dựng dashboard vận hành

Một dashboard pool hữu ích có thể chia thành các hàng:

### Hàng 1: Sức khỏe tổng quan

- API request rate.
- API p95/p99 latency.
- HTTP 5xx/error rate.
- Database availability.

### Hàng 2: Trạng thái pool theo datasource

- Acquired.
- Allocated.
- Idle.
- Pending.
- Max size cấu hình.

### Hàng 3: Thời gian và lỗi acquire

- Acquire wait duration nếu có.
- Acquire timeout count.
- Connection creation failure.
- Validation failure.

### Hàng 4: Database

- Active sessions.
- Running query count.
- Query latency.
- Lock wait.
- CPU, memory và I/O.

### Hàng 5: Transaction và ứng dụng

- Transaction duration.
- Slow query.
- Request đang chờ.
- Scheduler saturation nếu có blocking workload.
- Downstream latency.

Khi các panel dùng cùng time range, có thể nhìn được quan hệ nguyên nhân:

~~~text
Database query latency tăng
          |
          v
Connection được giữ lâu hơn
          |
          v
Acquired tăng
          |
          v
Idle giảm
          |
          v
Pending tăng
          |
          v
Acquire timeout và API latency tăng
~~~

Đây là một chuỗi nguyên nhân có thể xảy ra, không phải quy luật luôn đúng. Một transaction dài hoặc blocking call ngoài database cũng có thể khiến acquired tăng trước khi query latency thay đổi.

## 14. Phân biệt pool metric và database session metric

Hai hệ thống quan sát đo các góc nhìn khác nhau:

| Góc nhìn | Đo lường |
|---|---|
| R2DBC pool acquired | Connection pool đã cấp cho ứng dụng |
| R2DBC pool idle | Connection còn trong pool và chưa được mượn |
| R2DBC pool allocated | Connection pool đã tạo/quản lý |
| R2DBC pool pending | Request ứng dụng đang chờ connection |
| Database active sessions | Session database đang kết nối và trạng thái phía server |
| Database running queries | Câu SQL đang chạy tại thời điểm quan sát |
| Database lock wait | Transaction đang chờ khóa ở database |

Một connection acquired có thể không chạy query. Một session database có thể vẫn tồn tại dù đang idle trong pool.

Khi so sánh số connection:
- Cộng allocated của tất cả pool trên mọi instance.
- Cộng connection từ các service khác.
- Tính thêm connection của migration, admin và monitoring.
- So sánh với session limit phía database.

Nếu số session server lớn hơn allocated của một instance, điều đó không tự động là bất thường vì còn nhiều nguồn kết nối khác.

## 15. Kiểm thử pool saturation

Kiểm thử pool giúp xác nhận giới hạn và timeout hoạt động đúng.

### 15.1. Tạo tải có kiểm soát

Có thể cấu hình test pool nhỏ, ví dụ max size 2 và max pending acquire thấp. Sau đó tạo các publisher giữ connection đủ lâu để quan sát acquired, idle và pending.

Không dùng Thread.sleep trên event-loop để giữ connection. Có thể dùng một publisher test được điều khiển bởi Sinks hoặc Mono.delay trong test để chủ động quyết định thời điểm hoàn tất.

### 15.2. Kiểm tra pending

Kịch bản:

1. Hai thao tác đầu acquire hai connection.
2. Cả hai chờ một tín hiệu test nên chưa release.
3. Thao tác thứ ba yêu cầu connection.
4. Xác nhận pending tăng.
5. Phát tín hiệu cho một thao tác kết thúc.
6. Xác nhận request đang chờ được cấp connection và pending giảm.

Test cần truy cập metric hoặc pool metrics API phù hợp với phiên bản đang dùng. Nếu không có API metric trực tiếp, có thể kiểm tra hành vi bằng thời gian acquire và kết quả publisher.

### 15.3. Kiểm tra acquire timeout và pending limit

Một test khác giữ hết connection rồi phát thêm request:

- Request chờ trong giới hạn cho phép.
- Khi quá acquire timeout, publisher phát lỗi tương ứng.
- Khi pending vượt giới hạn, pool từ chối request mới theo behavior của phiên bản.
- Sau khi connection được release, pool vẫn có thể tiếp tục phục vụ request mới.

Không assert tên exception quá cụ thể nếu phiên bản driver/pool bọc lỗi khác nhau. Hãy kiểm tra nguyên nhân và contract thực tế của thư viện.

### 15.4. Kiểm tra cleanup sau lỗi và cancel

Cần xác nhận connection trở lại pool sau:
- Publisher hoàn tất.
- Publisher phát lỗi.
- Subscriber cancel.
- Query timeout.
- Callback sử dụng connection trực tiếp kết thúc.

Nếu acquired không giảm sau khi tất cả publisher đã kết thúc, điều tra việc cleanup, subscription tách rời hoặc connection được giữ ở nơi khác.

### 15.5. Không dùng test pool nhỏ để suy ra pool production

Pool max size 2 giúp tái hiện saturation dễ dàng nhưng không nói rằng production cũng nên dùng 2. Mục tiêu test là kiểm chứng semantics, timeout và cleanup. Kích thước production cần dựa trên tải, database capacity và số replica.

## 16. Những lỗi thường gặp khi đọc metric

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| Acquired là số query đang chạy | Connection có thể đang giữ trong transaction nhưng không chạy SQL | Acquired là số connection đang được mượn |
| Idle bằng 0 luôn là lỗi | Pool có thể được sử dụng hết nhưng chưa có ai phải chờ | Xem pending, latency và timeout |
| Allocated là max size | Allocated là số đã tạo, max size là giới hạn cấu hình | So sánh allocated với max size |
| Pending tăng nghĩa database chắc chắn chậm | Có thể connection bị giữ bởi transaction hoặc downstream | Kết hợp query latency và transaction duration |
| Tăng maxSize luôn giải quyết saturation | Database có thể bị quá tải khi mở thêm session | Kiểm tra database capacity và hold time |
| Pending bằng 0 chứng minh pool khỏe | Acquire timeout có thể xảy ra trước snapshot hoặc không có hàng chờ tại thời điểm đo | Xem timeout/error rate và acquire latency |
| Actuator metrics lưu lịch sử | Endpoint chủ yếu trả snapshot meter | Dùng Prometheus hoặc time-series backend |
| Metric tag luôn tên name | Tag tùy phiên bản/tích hợp | Kiểm tra availableTags thực tế |
| Mỗi instance có maxSize nhỏ nên tổng cũng nhỏ | Tổng connection nhân với số replica và số pool | Tính ngân sách toàn hệ thống |
| Pool allocated bằng DB active sessions | Có nhiều nguồn kết nối và session idle | Đối chiếu hai góc nhìn riêng |
| Tăng pending queue làm tăng throughput | Hàng đợi dài có thể chỉ làm request chờ lâu hơn | Giới hạn queue theo latency budget |
| Chỉ xem dashboard tổng | Một pool riêng có thể bão hòa | Tách metric theo pool và instance |

## 17. Quy trình điều tra khi pool cạn connection

Khi nhận cảnh báo pool saturation, hãy làm theo thứ tự:

1. Xác định datasource/pool nào có pending tăng.
2. Kiểm tra acquired, allocated, idle và max size cùng thời điểm.
3. Xem acquire timeout và connection creation failure.
4. Kiểm tra query latency, database CPU, lock wait và session limit.
5. Kiểm tra transaction duration và các transaction dài bất thường.
6. Tìm service có lời gọi HTTP, SDK blocking hoặc xử lý file nằm trong transaction.
7. Kiểm tra Flux lớn hoặc consumer chậm đang giữ connection.
8. Kiểm tra đường dùng ConnectionFactory trực tiếp có cleanup cho complete/error/cancel.
9. Kiểm tra số replica và tổng connection tiềm năng của tất cả pool.
10. Chỉ tăng max size khi database còn capacity và workload thực sự cần thêm connection.
11. Điều chỉnh acquire timeout, pending limit và concurrency theo latency budget.
12. Chạy lại load test và xác nhận pending, timeout, p95/p99 latency đã cải thiện.

Nếu query latency cao, xử lý query/database trước. Nếu query nhanh nhưng acquired vẫn cao, tìm thời gian connection bị giữ giữa các thao tác. Nếu allocated thấp hơn max mà pending tăng, điều tra quá trình tạo connection và giới hạn phía server.

## 18. Bài tập tự kiểm tra

### Bài 1: Đọc trạng thái pool

Pool có max size 20, acquired 20, idle 0, pending 15. Bạn nên kết luận điều gì?

Gợi ý: Pool đang bão hòa tại thời điểm đo. Cần tìm nguyên nhân connection bị giữ lâu và xác nhận database còn capacity trước khi tăng max size.

### Bài 2: Acquired không phải query count

Acquired bằng 12 nhưng database chỉ có 2 query đang chạy. Điều này có thể xảy ra không?

Gợi ý: Có. Các connection còn lại có thể được giữ trong transaction, chờ downstream, stream dữ liệu hoặc đang ở trạng thái không thực thi SQL.

### Bài 3: Idle bằng 0

Pool có acquired bằng max, idle bằng 0 nhưng pending luôn bằng 0 và API đáp ứng SLO. Đây có nhất thiết là sự cố không?

Gợi ý: Không. Pool đang được sử dụng hết nhưng chưa có yêu cầu phải chờ. Tiếp tục theo dõi burst, acquire latency và timeout.

### Bài 4: Pending tăng nhưng allocated chưa đạt max

Nguyên nhân nào cần kiểm tra?

Gợi ý: Tạo connection chậm hoặc thất bại, giới hạn phía database, validation, network, authentication hoặc cấu hình pool khác.

### Bài 5: Transaction dài

Một service gọi payment gateway trong transaction R2DBC 10 giây. Điều gì có thể xảy ra với acquired?

Gợi ý: Connection có thể bị giữ trong thời gian chờ payment dù không chạy query, khiến idle giảm và pending tăng.

### Bài 6: Nhiều instance

Một ứng dụng có 4 replica, mỗi replica có orders pool max size 20 và audit pool max size 5. Tổng connection tiềm năng từ hai pool là bao nhiêu?

Gợi ý: Mỗi replica có thể mở 25 connection; 4 replica có thể mở tổng cộng 100 connection, chưa tính các ứng dụng khác.

### Bài 7: Actuator tag

Endpoint metrics trả availableTags với tag là poolName. Có nên dùng tag name trong truy vấn không?

Gợi ý: Không. Phải dùng đúng tag key mà endpoint công bố.

### Bài 8: Timeout

Request nhận acquire timeout. Điều đó có nghĩa câu SQL đã chạy quá lâu không?

Gợi ý: Không. Acquire timeout xảy ra khi chờ connection trước khi có thể thực thi SQL.

### Bài 9: Pool metric và database session

Allocated của pool orders là 20 nhưng database báo 60 session. Điều đó có thể bình thường không?

Gợi ý: Có thể có các instance khác, service khác, pool khác, migration hoặc admin connection. Cần cộng toàn bộ nguồn kết nối.

### Bài 10: Tăng pool size

Pending tăng nhưng query latency và database CPU cũng rất cao. Có nên tăng maxSize ngay không?

Gợi ý: Không nên quyết định chỉ từ pending. Database có thể đang là nút thắt; mở thêm connection có thể làm tải nặng hơn. Điều tra query, lock và capacity trước.

## 19. Ghi nhớ

- Connection pool quản lý connection có thể tái sử dụng và giới hạn số connection mà ứng dụng mở tới database.
- Acquired là số connection đang được mượn, không phải số query đang chạy.
- Allocated là số connection pool đã tạo/quản lý; max size là giới hạn cấu hình.
- Idle là số connection sẵn sàng được mượn.
- Pending là số yêu cầu đang chờ acquire.
- Acquired gần max, idle bằng 0 và pending tăng kéo dài là dấu hiệu pool saturation.
- Idle bằng 0 một mình chưa đủ kết luận sự cố; cần xem pending, latency và timeout.
- Các metric pool phổ biến gồm r2dbc.pool.acquired, allocated, idle và pending; tên/tag cụ thể phụ thuộc phiên bản và tích hợp.
- Spring Boot Actuator cung cấp endpoint metrics; Prometheus hoặc time-series backend dùng để lưu lịch sử và tạo dashboard/alert.
- Kiểm tra availableTags thực tế, không đoán tên tag.
- Tách metric theo pool và instance để không che khuất saturation cục bộ.
- Tính tổng connection theo số replica, tất cả pool và các workload khác trước khi tăng max size.
- Transaction dài, Flux consumer chậm, blocking call ngoài database và thiếu cleanup đều có thể giữ acquired lâu.
- Acquire timeout khác query timeout; pending khác số query đang chạy.
- Kết hợp pool metric với query latency, transaction duration, database session, lock wait và API SLO.
- Test pool saturation bằng barrier/publisher điều khiển, không dùng Thread.sleep để tạo trạng thái.
- Chỉ tăng pool size sau khi xác nhận database còn capacity và nguyên nhân thực sự cần thêm connection.

Khi quan sát R2DBC pool, hãy đọc acquired, allocated, idle và pending như một nhóm trạng thái. Kết hợp chúng với thời gian acquire, transaction duration và sức khỏe database để xác định connection đang được sử dụng hiệu quả hay bị giữ quá lâu. Dashboard theo từng pool, giới hạn connection có tính tới số replica và cảnh báo theo SLO giúp phát hiện sớm tình trạng chờ connection mà không phải tăng pool một cách mù quáng.

