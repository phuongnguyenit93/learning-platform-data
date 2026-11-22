# Đo độ trễ, số truy vấn và kích thước biểu diễn trước khi tối ưu

## Bối cảnh

Một endpoint Spring Data REST có thể trông đơn giản nhưng mỗi request có thể thực hiện nhiều công việc: xác thực, truy vấn repository, tải association, chuyển entity thành representation, tạo HAL links, serialize JSON và gửi response. Vì vậy, chỉ nhìn vào số dòng code hoặc thời gian truy vấn SQL riêng lẻ chưa đủ để kết luận endpoint nhanh hay chậm.

Trước khi tối ưu, hãy đo ít nhất ba nhóm dữ liệu:

1. **Độ trễ (latency):** request mất bao lâu từ góc nhìn client và server.
2. **Số truy vấn (query count):** request phát sinh bao nhiêu câu SQL và thời gian DB chiếm bao nhiêu.
3. **Kích thước representation:** response có bao nhiêu byte, gồm JSON/HAL metadata và nội dung dữ liệu.

Các phép đo cần gắn với endpoint, loại request, kích thước trang, bộ lọc, projection, dữ liệu thử nghiệm và mức tải cụ thể. Một con số riêng lẻ không đủ đại diện cho hiệu năng của toàn API.

Mục tiêu của baseline là trả lời được: request nào chậm, chậm ở tầng nào, có truy vấn thừa hay không, response lớn đến đâu và kết quả thay đổi ra sao sau mỗi lần điều chỉnh.

## 1. Chọn workload đại diện

Trước tiên, liệt kê các request quan trọng của API. Với Spring Data REST, nên xem xét các loại sau:

| Loại request | Ví dụ | Điều cần quan sát |
| --- | --- | --- |
| Collection resource | `GET /orders?page=0&size=20` | Số bản ghi, query phân trang/count, payload |
| Item resource | `GET /orders/42` | Query theo ID, association được tải, kích thước representation |
| Association resource | `GET /orders/42/customer` | Số truy vấn và dữ liệu quan hệ |
| Search resource | `GET /orders/search/by-status?status=PAID` | Query filter, sort, phân trang |
| Projection | `GET /orders/42?projection=summary` | Payload và query so với representation mặc định |
| Request ghi | `POST /orders`, `PUT /orders/42` | Validation, số lần đọc/ghi, transaction và thời gian xử lý |

Không nhất thiết đo mọi endpoint ngay từ đầu. Hãy ưu tiên những endpoint được gọi nhiều, có dữ liệu lớn, có association phức tạp hoặc đang bị người dùng phản ánh chậm.

Với từng request, ghi lại:

- Method và URI, gồm query parameters.
- Authentication/role sử dụng trong phép đo.
- Header `Accept` và kiểu representation.
- Page size, sort, filter và projection.
- Số bản ghi phù hợp với truy vấn và số bản ghi thực tế trong trang.
- Kích thước dataset và trạng thái cache.
- Mức tải đồng thời dự kiến.

Ví dụ, `GET /orders?page=0&size=10` và `GET /orders?page=0&size=100` là hai workload khác nhau. Không so sánh thời gian của chúng như thể server xử lý cùng một lượng dữ liệu.

## 2. Đo độ trễ từ phía client

Độ trễ client nhìn thấy bao gồm nhiều thành phần: thời gian truyền mạng, chờ server, xử lý ứng dụng, truy vấn database, serialize response và truyền body. Đây là chỉ số gần nhất với trải nghiệm của client.

Có thể dùng curl để lấy thời gian của một request:

    curl -sS -o response.json       -H "Accept: application/hal+json"       -w "status=%{http_code}\nstarttransfer=%{time_starttransfer}\ntotal=%{time_total}\nbytes=%{size_download}\n"       "http://localhost:8080/orders?page=0&size=20"

Các trường hữu ích:

- `time_starttransfer`: thời gian từ khi bắt đầu request tới byte đầu tiên của response (TTFB).
- `time_total`: tổng thời gian hoàn tất request.
- `size_download`: số byte body được curl ghi nhận cho lần tải.
- `http_code`: status code, giúp phát hiện request lỗi thay vì chỉ đo request thành công.

Một lần gọi chỉ là một mẫu. Để có baseline, chạy nhiều lần với cùng request và lưu lại kết quả. Tách lượt warm-up khỏi tập số liệu chính để giảm ảnh hưởng của khởi động JVM, JIT, connection pool và cache ban đầu.

Khi đo qua mạng thật, giữ nguyên đường đi của request (gateway, reverse proxy, TLS, compression) giữa các lần so sánh. Nếu đo trực tiếp localhost trước rồi đo qua gateway sau, kết quả không còn cùng điều kiện.

## 3. Dùng percentile thay vì chỉ nhìn trung bình

Latency thường có phân bố lệch: phần lớn request nhanh nhưng một số request chậm do GC, DB contention, cache miss, connection pool hoặc truy vấn bất thường.

Nên báo cáo tối thiểu:

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50 | 50% request hoàn tất trong thời gian này hoặc nhanh hơn; gần với trải nghiệm điển hình |
| p95 | 95% request hoàn tất trong thời gian này hoặc nhanh hơn; thể hiện nhóm request chậm hơn |
| p99 | 99% request hoàn tất trong thời gian này hoặc nhanh hơn; giúp quan sát tail latency |
| max | Request chậm nhất trong tập đo; nhạy với outlier |
| throughput | Số request hoàn tất mỗi giây ở mức tải đã xác định |
| error rate | Tỷ lệ request lỗi hoặc timeout |

Ví dụ kết quả minh họa:

| Phiên đo | p50 | p95 | p99 | Throughput | Error rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 45 ms | 180 ms | 420 ms | 120 req/s | 0,1% |
| Sau thay đổi | 38 ms | 95 ms | 210 ms | 145 req/s | 0,1% |

Các số trên chỉ minh họa cách trình bày, không phải benchmark của Spring Data REST. Khi báo cáo thực tế, luôn ghi dataset, số virtual users, thời lượng, warm-up, môi trường và phiên bản ứng dụng.

Không nên kết luận tối ưu thành công chỉ vì p50 giảm. Nếu p95/p99 hoặc error rate tăng mạnh, thay đổi có thể làm trải nghiệm của một nhóm client xấu đi.

## 4. Đo latency ở phía server bằng Micrometer

Nếu ứng dụng dùng Spring Boot Actuator và Micrometer, metric HTTP server thường được công bố dưới tên `http.server.requests` (tên/tag cụ thể phụ thuộc phiên bản và cấu hình).

Ví dụ cấu hình endpoint metrics trong môi trường phát triển:

    management.endpoints.web.exposure.include=health,metrics,prometheus

Không nên mở mọi actuator endpoint công khai trên production. Chỉ expose metric cần thiết qua mạng quản trị và bảo vệ bằng authentication/network policy phù hợp.

Có thể kiểm tra metric qua Actuator:

    GET /actuator/metrics/http.server.requests

Tham số tag có thể lọc theo method, status, URI hoặc outcome nếu instrumentation của ứng dụng cung cấp các tag đó. Hãy xem response thực tế để biết tag nào có sẵn; không giả định tên URI luôn được ghi dưới dạng path đầy đủ.

Nếu xuất Prometheus, có thể xây dashboard cho:

- Request rate theo endpoint.
- Phân bố duration.
- Status code và error rate.
- So sánh latency giữa các endpoint.
- Tương quan với DB connection pool và JVM metrics.

Micrometer server timer đo thời gian xử lý tại ứng dụng theo instrumentation; nó không bao gồm toàn bộ thời gian client chờ trên mạng. Hãy giữ cả phép đo client và server để phân biệt thời gian ứng dụng với độ trễ bên ngoài.

## 5. Đo số truy vấn SQL

Một endpoint đọc collection có thể tạo nhiều SQL query hơn dự kiến. Ví dụ:

- Một query lấy trang dữ liệu.
- Một query đếm tổng số bản ghi cho metadata phân trang.
- Nhiều query bổ sung để tải association của từng entity.
- Query khác do listener, security hoặc logic ứng dụng.

Số query cần được đo trên cùng một request và cùng một dataset. Không chỉ nhìn vào query count toàn ứng dụng trong vài phút, vì số đó không thể quy trách nhiệm cho một endpoint cụ thể.

### 5.1 Bật Hibernate statistics trong môi trường thử nghiệm

Với Hibernate, có thể bật statistics để quan sát số liệu tích lũy:

    spring.jpa.properties.hibernate.generate_statistics=true

Có thể lấy `SessionFactory` statistics trong code:

    @Component
    public class HibernateStatisticsProbe {

        private final EntityManagerFactory entityManagerFactory;

        public HibernateStatisticsProbe(
                EntityManagerFactory entityManagerFactory) {
            this.entityManagerFactory = entityManagerFactory;
        }

        public Statistics statistics() {
            SessionFactory sessionFactory =
                    entityManagerFactory.unwrap(SessionFactory.class);
            return sessionFactory.getStatistics();
        }
    }

API trên minh họa cách lấy statistics; cách reset và đọc counter nên được giới hạn trong test hoặc môi trường profiling. Hibernate statistics thường là counter tích lũy ở cấp SessionFactory. Khi nhiều request chạy đồng thời, hiệu số counter trước/sau một request không thể được coi là query count chính xác của riêng request đó.

### 5.2 Ghi nhận SQL có correlation theo request

Để quy query về đúng request, dùng một trong các cách:

- SQL logging trong môi trường thử nghiệm với log correlation/request ID.
- Datasource proxy hoặc JDBC instrumentation có khả năng đếm statement theo request context.
- APM/tracing instrument JDBC spans và gắn chúng với HTTP trace.
- Integration test chạy một request trong điều kiện cô lập rồi đếm statement.

Datasource proxy có thể ghi số lần execute, thời gian từng statement và loại thao tác. Chọn công cụ phù hợp với stack hiện tại; tránh tự viết bộ đếm dựa trên global static counter trong ứng dụng nhiều luồng.

Không bật SQL log chi tiết kéo dài trên production nếu chưa đánh giá tác động hiệu năng, dung lượng log và dữ liệu nhạy cảm trong parameter. Logging chính nó có thể làm thay đổi latency mà bạn đang cố đo.

### 5.3 Đo cả thời gian DB

Query count thấp không tự động đồng nghĩa với DB nhanh. Một query có thể scan bảng lớn, join phức tạp hoặc chờ lock. Ngược lại, nhiều query nhỏ cũng có thể gây overhead do round trip và N+1.

Với mỗi request, cố gắng ghi:

- Tổng số SQL statement.
- Số SELECT, INSERT, UPDATE, DELETE.
- Tổng thời gian DB và thời gian từng query chậm.
- Query plan của các câu truy vấn quan trọng.
- Số connection được mượn và thời gian chờ connection nếu có.

Dùng database slow query log hoặc `EXPLAIN`/`EXPLAIN ANALYZE` theo hệ quản trị đang dùng để tìm vấn đề ở execution plan. Chỉ chạy lệnh phân tích có thể thực thi query trên môi trường phù hợp; không tùy tiện chạy trên production nếu câu lệnh gây tải hoặc thay đổi dữ liệu.

## 6. Nhận diện N+1 và truy vấn do association

Một vấn đề phổ biến của ORM là N+1: lấy danh sách N entity bằng một query, sau đó phát sinh thêm query cho association của từng entity.

Ví dụ khái niệm:

    SELECT * FROM orders LIMIT 20;
    SELECT * FROM customers WHERE id = 1;
    SELECT * FROM customers WHERE id = 2;
    SELECT * FROM customers WHERE id = 3;
    ...

Nếu response của mỗi Order cần Customer, cách truy cập association trong quá trình serialize có thể kích hoạt nhiều truy vấn tùy fetch strategy và cấu hình persistence context.

Dấu hiệu:

- Query count tăng gần tuyến tính theo số item trong trang.
- Một request size 10 có nhiều query hơn đáng kể so với size 1.
- Log SQL lặp lại cùng một mẫu, chỉ khác foreign key.
- Latency tăng nhanh khi tăng page size.

Không phải mọi query lặp đều là N+1; cần xem trace và mapping thực tế. Sau khi xác định nguyên nhân, có thể cân nhắc:

- Projection chỉ lấy trường cần thiết.
- Fetch join hoặc entity graph phù hợp với use case.
- Batch fetching.
- Query DTO/read model cho endpoint tổng hợp.
- Tránh serialize association không cần thiết.

Không áp dụng fetch join một cách máy móc cho collection pagination: join collection có thể nhân bản hàng, làm phân trang không chính xác hoặc khiến Hibernate phải xử lý phân trang trong bộ nhớ. Hãy kiểm tra SQL và kết quả thực tế sau thay đổi.

## 7. Đo kích thước representation

Spring Data REST thường trả HAL JSON. Payload có thể bao gồm:

- Dữ liệu trong `_embedded`.
- Các link trong `_links`.
- Metadata phân trang trong `page`.
- Các trường của entity hoặc projection.
- Các association và embedded resource.

Kích thước representation ảnh hưởng tới băng thông, thời gian serialize, thời gian parse ở client và bộ nhớ. Hãy đo byte thực tế của response body thay vì ước lượng từ số trường.

Có thể lưu response để xem kích thước:

    curl -sS       -H "Accept: application/hal+json"       -o response.json       -w "status=%{http_code} bytes=%{size_download} total=%{time_total}\n"       "http://localhost:8080/orders?page=0&size=20"

Giữ nguyên header compression giữa các lần đo. Nếu so sánh body nén và không nén, ghi rõ đang đo byte truyền trên mạng hay byte JSON sau giải nén. `Content-Length` có thể không xuất hiện khi response dùng chunked transfer; client vẫn có thể đếm byte đã nhận.

Đối với một tập response đại diện, ghi:

| Chỉ số | Mục đích |
| --- | --- |
| Response bytes | Dung lượng body ở chế độ truyền đã chọn |
| Items returned | Số item trong collection page |
| Bytes per item | Ước lượng payload trung bình trên mỗi item |
| Link count | Số hyperlink được serialize |
| Embedded depth | Mức lồng representation/association |
| Compressed bytes | Dung lượng truyền khi compression được bật |

`Bytes per item` chỉ là chỉ số so sánh gần đúng vì HAL links và page metadata có phần chi phí cố định, không tăng tuyến tính theo số item.

## 8. So sánh representation mặc định và projection

Một cách kiểm tra chi phí payload là so sánh representation mặc định với projection:

    GET /orders?page=0&size=20
    Accept: application/hal+json

    GET /orders?page=0&size=20&projection=summary
    Accept: application/hal+json

Nếu projection trả ít trường hơn, payload có thể giảm. Tuy nhiên, không mặc định rằng projection luôn làm giảm query count hoặc latency. Việc đọc các property và association trong projection có thể vẫn kích hoạt query bổ sung.

Đo cả ba nhóm dữ liệu trước khi kết luận:

- Client/server latency.
- SQL query count và thời gian DB.
- Response bytes.

Nếu payload giảm nhưng query count tăng, hãy xem lại cách projection truy cập association. Nếu query count giảm nhưng response bytes tăng, có thể representation mới đang nhúng nhiều dữ liệu hơn.

## 9. Thiết kế một phép đo lặp lại được

Một quy trình baseline có thể thực hiện như sau:

1. Chuẩn bị dataset đại diện, gồm cả số lượng bản ghi và độ phân bố association.
2. Chọn một endpoint và request cụ thể.
3. Cố định page size, sort, filter, projection, header và authentication.
4. Khởi động ứng dụng và database; thực hiện warm-up.
5. Gửi nhiều request tuần tự để đo latency cơ bản.
6. Chạy một bài load test với concurrency và thời lượng xác định.
7. Thu thập p50, p95, p99, throughput và error rate.
8. Ghi query count, thời gian DB và response bytes.
9. Lưu cấu hình, log/trace và kết quả cùng một mã phiên đo.
10. Lặp lại cùng quy trình sau từng thay đổi.

Có thể dùng k6, Gatling hoặc JMeter để tạo workload lặp lại và concurrency có kiểm soát. Công cụ load test phải chạy trên máy/tài nguyên đủ mạnh; nếu chính máy tạo tải bị nghẽn CPU hoặc mạng, kết quả sẽ không phản ánh server.

Không thay đổi nhiều yếu tố cùng lúc. Nếu cùng lúc đổi page size, projection, fetch strategy và database index, bạn sẽ khó biết yếu tố nào tạo ra cải thiện hoặc regression.

## 10. Mẫu bảng baseline

Dùng một bảng thống nhất để so sánh trước và sau:

| Endpoint / scenario | Page size | p50 | p95 | p99 | SQL count | DB time | Body bytes | Error rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET /orders | 20 | — | — | — | — | — | — | — |
| GET /orders/42 | — | — | — | — | — | — | — | — |
| GET /orders?projection=summary | 20 | — | — | — | — | — | — | — |

Ghi chú cho mỗi lần đo:

    Run ID:
    Commit/build:
    Environment:
    Dataset:
    JVM / heap:
    Database:
    Warm-up:
    Test duration:
    Virtual users:
    Cache state:
    Compression:
    Request headers:
    Observations:

Không điền số liệu ước lượng vào bảng baseline. Nếu chưa có phép đo, để trống và ghi rõ dữ liệu nào chưa thu thập.

## 11. Diễn giải kết quả để chọn hướng tối ưu

### Latency cao, query count thấp

Có thể cần xem query plan, lock, network, serialization, CPU, GC hoặc downstream service. Một câu SQL đơn lẻ vẫn có thể rất chậm.

### Latency cao, query count tăng theo page size

Kiểm tra N+1, lazy association, projection và fetch strategy. So sánh size 1, 10 và 20 trong cùng điều kiện.

### Query count thấp nhưng DB time cao

Kiểm tra execution plan, index, cardinality, sort và lock. Không thêm index chỉ dựa trên tên cột; cần xem truy vấn thực tế và chi phí ghi.

### Payload lớn nhưng DB nhanh

Xem projection, association embedded, số link, trường văn bản lớn và page size. Đánh giá compression và representation phù hợp với client.

### Server latency thấp nhưng client latency cao

Kiểm tra TLS, gateway, proxy, DNS, network, response transfer và vị trí của client. Phép đo client/server giúp xác định phần thời gian nằm ngoài ứng dụng.

### p50 tốt nhưng p95/p99 xấu

Tìm request chậm bất thường, query plan không ổn định, cache miss, connection pool wait, GC pause và tải đồng thời. Tránh tối ưu chỉ theo request trung bình.

## 12. Nguyên tắc trước khi tối ưu

- **Đo trước, thay đổi sau:** ghi baseline trước khi chỉnh fetch strategy, index hoặc serialization.
- **Giữ workload cố định:** so sánh cùng dataset, request, page size, auth, cache state và concurrency.
- **Đo nhiều tầng:** client, server, database và payload.
- **Tách warm-up khỏi số liệu chính:** JVM và cache có thể làm các request đầu chậm hơn.
- **Không tin một lần chạy:** dùng nhiều mẫu và báo percentile.
- **Không tối ưu query count đơn độc:** một query có thể đắt hơn nhiều query nhỏ.
- **Không bỏ qua error rate:** latency đẹp nhưng request thất bại không phải cải thiện.
- **Ghi lại thay đổi:** mỗi lần tối ưu phải có commit/build và mô tả thay đổi để đối chiếu.
- **Đánh giá trade-off:** giảm payload có thể tăng query; cache giảm latency nhưng có thể ảnh hưởng freshness; fetch join giảm query nhưng làm result set lớn.

Sau khi tìm được bottleneck có bằng chứng, chỉ thay đổi một yếu tố chính, chạy lại đúng workload và so sánh các chỉ số. Giữ thay đổi khi cải thiện mục tiêu mà không tạo regression đáng kể ở các chỉ số còn lại.

## 13. Bài thực hành

Giả sử endpoint:

    GET /orders?page=0&size=20
    Accept: application/hal+json

trả về 20 đơn hàng. Hãy thực hiện trong môi trường thử nghiệm:

1. Đo `time_starttransfer`, `time_total` và response bytes bằng curl.
2. Lặp lại nhiều lần và tính p50, p95, p99.
3. Bật metric HTTP server và ghi lại thời gian ở phía ứng dụng.
4. Thu SQL trace gắn với một request ID để đếm số statement.
5. Xác định query count có tăng theo số item hay không.
6. Ghi tổng thời gian DB và kiểm tra query chậm.
7. Lặp lại với page size 1, 10 và 20.
8. Lặp lại với projection summary.
9. So sánh latency, query count và payload bytes giữa các scenario.
10. Viết kết luận bottleneck dựa trên dữ liệu đã thu thập, sau đó đề xuất một thay đổi có thể kiểm chứng.

Câu hỏi tự kiểm tra:

- Vì sao p95/p99 hữu ích hơn chỉ số trung bình?
- Tại sao Hibernate global statistics không đủ để quy query cho một request khi có concurrency?
- Làm thế nào nhận biết N+1 từ query trace?
- Vì sao response HAL có thể lớn dù entity chỉ có vài trường?
- Projection có luôn làm giảm số query không?
- Khi nào latency client cao nhưng latency server thấp?
- Cần giữ những điều kiện nào giống nhau khi so sánh trước và sau tối ưu?

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Boot Reference — Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/)
- [Hibernate ORM User Guide — Statistics](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [k6 Documentation](https://grafana.com/docs/k6/latest/)
