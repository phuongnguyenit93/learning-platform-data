# Xác định độ trễ, thông lượng và số kết nối làm mục tiêu đo

Khi tối ưu hiệu năng Spring Data R2DBC, không nên bắt đầu bằng cách tăng kích thước connection pool hoặc thêm replica một cách cảm tính. Trước hết cần xác định hệ thống phải phục vụ bao nhiêu yêu cầu, phản hồi trong bao lâu và sử dụng bao nhiêu kết nối database ở mức tải dự kiến. Ba nhóm chỉ số nền tảng là **độ trễ (latency)**, **thông lượng (throughput)** và **số kết nối (connections)**.

Ba chỉ số này liên quan chặt chẽ nhưng không thể thay thế cho nhau. Một hệ thống có thể đạt throughput cao nhưng p99 latency rất tệ; một pool có nhiều connection nhưng database không xử lý nhanh hơn; hoặc latency thấp ở tải nhẹ nhưng tăng đột biến khi concurrency tăng. Mục tiêu đo cần mô tả workload thực tế, ngưỡng chấp nhận và điều kiện kiểm thử để kết quả có thể lặp lại.

## 1. Ba câu hỏi cần trả lời trước khi đo

Trước khi chạy benchmark, hãy chuyển yêu cầu nghiệp vụ thành ba câu hỏi có thể đo:

1. **Latency:** một request hoặc thao tác database được phép mất bao lâu, ở percentile nào?
2. **Throughput:** hệ thống cần hoàn tất bao nhiêu request hoặc transaction mỗi giây trong khi vẫn đáp ứng mục tiêu latency?
3. **Connections:** ứng dụng cần bao nhiêu connection đồng thời, pool được phép chờ bao lâu và database có đủ ngân sách connection cho tất cả instance không?

Ví dụ một API đọc sản phẩm có thể cần phục vụ tải bình thường 100 request/giây, tải đỉnh 250 request/giây, p95 dưới 200 ms và p99 dưới 500 ms. Đây chỉ là con số minh họa; mục tiêu thật phải xuất phát từ yêu cầu sản phẩm, trải nghiệm người dùng, chi phí và khả năng của database.

Không đặt mục tiêu kiểu “R2DBC phải nhanh hơn JDBC 30%” nếu chưa xác định cùng workload, cùng database, cùng cấu hình và cùng điều kiện đo. Reactive là mô hình xử lý I/O, không phải cam kết tự động về latency hoặc throughput.

## 2. Định nghĩa SLI, SLO và ngưỡng kiểm thử

Một mục tiêu hiệu năng rõ ràng thường gồm:

- **SLI (Service Level Indicator):** chỉ số quan sát được, ví dụ p95 latency của endpoint hoặc tỷ lệ request thành công.
- **SLO (Service Level Objective):** mục tiêu cần đạt trong một khoảng thời gian, ví dụ 99% request đọc hoàn tất trong 300 ms.
- **Load-test acceptance criteria:** điều kiện để một lần kiểm thử được coi là đạt, ví dụ throughput tối thiểu, p99 tối đa và tỷ lệ lỗi tối đa ở tải xác định.

Ví dụ bảng mục tiêu:

| Chỉ số | Workload | Mục tiêu minh họa |
| --- | --- | --- |
| Read latency | API lấy chi tiết sản phẩm | p95 ≤ 200 ms, p99 ≤ 500 ms |
| Write latency | API tạo đơn hàng | p95 ≤ 400 ms, p99 ≤ 800 ms |
| Throughput | Hỗn hợp đọc/ghi đã xác định | ≥ 150 request thành công/giây |
| Error rate | Cùng cửa sổ đo | < 0,5% lỗi ngoài dự kiến |
| Pool acquire | Thời gian chờ lấy connection | p95 ≤ 20 ms |
| Pending acquire | Tải ổn định | Không tăng liên tục |
| Connection count | Toàn bộ application instances | Không vượt ngân sách DB đã phân bổ |

Các giá trị trong bảng không phải mặc định của Spring hoặc R2DBC. Hãy thay chúng bằng yêu cầu của hệ thống. Một con số chỉ có ý nghĩa khi đi kèm endpoint/query, tải, thời gian đo, percentile và điều kiện môi trường.

## 3. Latency là gì?

Latency là thời gian từ lúc một thao tác bắt đầu đến khi kết quả cần thiết sẵn sàng. Với HTTP API, có thể đo từ lúc server nhận request đến khi response hoàn tất. Với database operation, có thể đo từ lúc bắt đầu lấy connection hoặc gửi query đến lúc nhận đủ kết quả.

Không gộp mọi latency thành một con số nếu cần tìm nguyên nhân. Một request WebFlux có thể trải qua:

1. Routing và xử lý Controller.
2. Validation và logic Service.
3. Chờ connection từ pool.
4. Gửi query và chờ database thực thi.
5. Nhận và mapping rows.
6. Gọi dịch vụ ngoài nếu có.
7. Serialize response và gửi qua HTTP.

Tổng thời gian API có thể lớn hơn nhiều so với thời gian SQL. Đo riêng các giai đoạn giúp biết bottleneck nằm ở pool, database, network, mapping hay dependency ngoài.

~~~mermaid
flowchart LR
    A[HTTP received]
    B[Controller / Service]
    C[Pool acquire]
    D[Database query]
    E[Mapping]
    F[Response encoding]
    G[HTTP completed]
    A --> B --> C --> D --> E --> F --> G
~~~

Nếu chỉ đo query duration mà kết luận API đạt SLO, có thể bỏ qua thời gian chờ pool hoặc serialize response. Ngược lại, nếu chỉ đo end-to-end, khó biết tầng nào cần tối ưu.

## 4. Dùng percentile thay vì chỉ dùng trung bình

Latency thường có phân bố lệch: phần lớn request nhanh nhưng một số request chậm do lock, cache miss, GC, connection wait hoặc truy vấn lớn.

Các percentile phổ biến:

- **p50:** 50% request hoàn tất trong hoặc dưới thời gian này; gần với median.
- **p90:** 90% request hoàn tất trong hoặc dưới thời gian này.
- **p95:** 95% request hoàn tất trong hoặc dưới thời gian này.
- **p99:** 99% request hoàn tất trong hoặc dưới thời gian này.
- **p99.9:** thể hiện phần đuôi rất chậm khi số mẫu đủ lớn.

Ví dụ:

| Chỉ số | Latency |
| --- | ---: |
| p50 | 45 ms |
| p90 | 110 ms |
| p95 | 180 ms |
| p99 | 620 ms |
| Maximum | 2.4 s |

Median 45 ms có vẻ tốt, nhưng 1% request chậm hơn 620 ms. Nếu người dùng gặp các request đó thường xuyên ở quy mô lớn, trải nghiệm vẫn kém.

Trung bình (mean) hữu ích để tính tải tổng thể và áp dụng một số mô hình hàng đợi, nhưng không mô tả tốt tail latency. Báo cáo hiệu năng nên có ít nhất p50, p95, p99, throughput và error rate.

Percentile cần đủ số mẫu. Một bài test chỉ có vài trăm request không đủ cơ sở vững chắc để diễn giải p99. Với p99/p99.9, hãy chạy đủ lâu và tạo đủ request trong từng nhóm endpoint.

## 5. Phân biệt latency của request, transaction và query

Một hệ thống R2DBC có thể đo nhiều lớp thời gian:

| Phạm vi | Bắt đầu/kết thúc | Dùng để trả lời |
| --- | --- | --- |
| HTTP latency | Request vào server → response hoàn tất | Người gọi API chờ bao lâu? |
| Service latency | Bắt đầu use case → publisher hoàn tất | Logic nghiệp vụ mất bao lâu? |
| Pool acquire latency | Yêu cầu connection → nhận connection | Có phải chờ pool không? |
| Query latency | Gửi statement → nhận kết quả theo cách đo | Database/driver xử lý query bao lâu? |
| Transaction duration | Bắt đầu transaction → commit/rollback | Connection và transaction bị giữ bao lâu? |
| External dependency latency | Gửi HTTP/message request → nhận kết quả | Dịch vụ ngoài ảnh hưởng bao nhiêu? |

Tên gọi và điểm đo cụ thể phụ thuộc instrumentation. Hãy ghi rõ cách đo: query latency có bao gồm acquire connection không, có bao gồm mapping và tiêu thụ toàn bộ Flux không, hay chỉ đến khi statement trả result?

Với một Flux lớn, thời gian đến phần tử đầu tiên (time to first row) khác với thời gian tiêu thụ toàn bộ stream. API streaming có thể bắt đầu trả dữ liệu nhanh nhưng vẫn mở connection lâu để đọc phần còn lại.

## 6. Throughput là gì?

Throughput là số lượng công việc hoàn tất trong một đơn vị thời gian. Với API, thường dùng request/second (RPS); với database có thể dùng transaction/second (TPS), query/second hoặc row/second tùy workload.

Công thức cơ bản:

\[
\text{Throughput} =
\frac{\text{Số thao tác hoàn tất trong cửa sổ đo}}
{\text{Thời gian cửa sổ đo}}
\]

Ví dụ, trong 60 giây có 9.000 request hoàn tất thành công:

\[
9.000 / 60 = 150\ \text{requests/second}
\]

Nên phân biệt:

- **Offered load:** số request client cố gắng gửi.
- **Started requests:** số request server bắt đầu xử lý.
- **Completed throughput:** số request hoàn tất.
- **Successful throughput/goodput:** số request hoàn tất đúng yêu cầu nghiệp vụ.

Nếu client gửi 300 request/giây nhưng server chỉ hoàn tất 180 request/giây, không thể báo hệ thống đạt 300 RPS. Cần xem số request pending, timeout và lỗi.

## 7. Throughput không thể tách khỏi latency và error rate

Một hệ thống có thể tăng throughput bằng cách chấp nhận queue dài hơn. Khi đó request vẫn hoàn tất nhưng người dùng phải chờ lâu. Một hệ thống khác có thể giữ latency thấp bằng cách từ chối phần lớn request; latency của các request còn lại đẹp nhưng goodput thấp.

Do đó, mục tiêu phải là một tập điều kiện đồng thời:

- Throughput tối thiểu.
- p95/p99 latency tối đa.
- Error rate tối đa.
- Pending queue không tăng không giới hạn.
- Connection usage nằm trong ngân sách.
- CPU, memory, I/O và database không bị bão hòa ngoài mức chấp nhận.

Không chọn một điểm benchmark chỉ vì nó có RPS lớn nhất. Hãy chọn điểm mà hệ thống vẫn đáp ứng latency và độ tin cậy ở workload dự kiến.

## 8. Mối liên hệ giữa throughput, latency và concurrency

Định luật Little (Little's Law) mô tả quan hệ trung bình trong một hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- L: số công việc trung bình đang ở trong hệ thống (concurrency/in-flight work).
- λ: throughput trung bình, đơn vị công việc/giây.
- W: thời gian trung bình một công việc ở trong hệ thống, đơn vị giây.

Ví dụ API hoàn tất 120 request/giây, latency trung bình 250 ms (0,25 giây):

\[
L = 120 \times 0,25 = 30
\]

Trung bình có khoảng 30 request đang được xử lý hoặc chờ trong hệ thống.

Đây là quan hệ ở trạng thái ổn định, dùng số trung bình và cùng một phạm vi đo. Không thay p99 vào công thức rồi coi kết quả là concurrency chính xác. Nếu queue đang tăng liên tục, hệ thống chưa ở trạng thái ổn định và phép tính không mô tả được tình trạng đó.

## 9. Concurrency của request không bằng số connection database

Một request WebFlux có thể:

- Chỉ thực hiện một query rất ngắn.
- Thực hiện nhiều query tuần tự.
- Thực hiện một số query song song.
- Chờ HTTP service mà không giữ connection DB.
- Chờ một publisher khác trước khi lấy connection.

Vì vậy, 100 request HTTP đang in-flight không có nghĩa cần 100 connection R2DBC.

Để ước lượng connection đang được sử dụng, có thể áp dụng Little's Law ở phạm vi database connection:

\[
\text{Average active DB connections}
\approx
\text{DB operations per second}
\times
\text{Average connection hold time}
\]

Ví dụ ứng dụng hoàn tất 80 transaction/giây và mỗi transaction giữ connection trung bình 40 ms (0,04 giây):

\[
80 \times 0,04 = 3,2
\]

Mức active connection trung bình xấp xỉ 3,2 trong điều kiện ổn định. Pool vẫn cần headroom cho burst, độ biến thiên, transaction dài và các hoạt động nền; nhưng ví dụ cho thấy không nên đặt pool size bằng tổng số request concurrency một cách máy móc.

## 10. Connection count gồm những gì?

Khi nói số connection, cần phân biệt:

- **Active/acquired:** connection đã được cấp cho caller và đang được sử dụng.
- **Idle:** connection đang nằm trong pool, chưa được caller sử dụng.
- **Allocated:** connection vật lý đã được pool tạo và đang quản lý, gồm active và idle theo cách đo của pool.
- **Pending acquire:** yêu cầu đang chờ được cấp connection.
- **Maximum allocated:** giới hạn connection pool có thể tạo.

Tên metric và định nghĩa chính xác phụ thuộc phiên bản R2DBC Pool và instrumentation. Không cộng active + allocated nếu allocated đã bao gồm active; như vậy sẽ đếm hai lần.

Một pool có thể có nhiều connection idle mà không có tải. Đó không phải lỗi nếu database có ngân sách phù hợp. Ngược lại, pending acquire tăng liên tục dù CPU database thấp có thể chỉ ra pool quá nhỏ, connection bị giữ lâu hoặc có leak.

## 11. Connection pool trong R2DBC

R2DBC Pool quản lý tập connection để ứng dụng tái sử dụng thay vì mở kết nối mới cho từng query. Cấu hình thường bao gồm:

- Initial size: số connection khởi tạo ban đầu.
- Max size: số connection tối đa pool được phép quản lý.
- Max idle time: thời gian connection có thể nhàn rỗi trước khi bị loại theo policy.
- Max life time: tuổi thọ tối đa của connection.
- Max acquire time: thời gian tối đa caller chờ lấy connection.
- Validation: cách kiểm tra connection còn dùng được.

Ví dụ cấu hình Java:

~~~java
ConnectionPoolConfiguration configuration =
        ConnectionPoolConfiguration.builder(connectionFactory)
                .initialSize(5)
                .maxSize(20)
                .maxIdleTime(Duration.ofMinutes(10))
                .maxLifeTime(Duration.ofMinutes(30))
                .maxAcquireTime(Duration.ofSeconds(2))
                .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

Đây là cấu hình minh họa, không phải khuyến nghị mặc định. Tên API và các option có thể thay đổi theo phiên bản r2dbc-pool. Khi dùng Spring Boot, nên cấu hình pool qua cơ chế được phiên bản Boot hỗ trợ và quản lý vòng đời pool như bean, thay vì tự tạo pool trong mỗi request.

## 12. Tính ngân sách connection cho toàn hệ thống

Giới hạn connection của database là giới hạn toàn cụm hoặc instance database, không phải giới hạn riêng của một pod ứng dụng.

Giả sử:

- Database cho phép tối đa 200 connection.
- Cần dành 30 connection cho quản trị, migration, monitoring và dịch vụ khác.
- Có 5 application instances.
- Mỗi instance có một writer pool.

Ngân sách tối đa dành cho ứng dụng:

\[
200 - 30 = 170
\]

Nếu chia đều:

\[
170 / 5 = 34
\]

Về số học, mỗi instance không thể vượt khoảng 34 connection nếu chỉ có một pool và không có pool khác. Tuy nhiên, thực tế cần chừa thêm headroom cho scale-out, rollout tạm thời có cả phiên bản cũ và mới, worker nền và các dịch vụ khác.

Một công thức lập ngân sách:

\[
\text{Total possible connections}
=
\sum (\text{instances} \times \text{pool max size})
+ \text{other clients}
\]

Tổng này phải thấp hơn giới hạn database với phần dự phòng rõ ràng. Nếu mỗi instance có cả writer pool và reader pool, phải cộng cả hai. Nếu deployment có thể scale từ 5 lên 10 replicas, tính theo 10 chứ không chỉ theo số instance bình thường.

## 13. Pool size lớn không đồng nghĩa throughput cao

Tăng max pool size có thể giảm thời gian chờ connection khi pool thực sự là bottleneck. Nhưng nó cũng có thể:

- Tăng số query đồng thời tới database.
- Làm CPU, I/O hoặc lock contention của database bão hòa.
- Tăng memory và chi phí context/connection phía server.
- Tăng cạnh tranh giữa transaction.
- Làm p95/p99 xấu hơn dù pool acquire latency giảm.

Nếu database đã bão hòa ở 30 connection, tăng pool lên 100 có thể làm queue chuyển từ pool sang database. Request vẫn chờ, nhưng chờ ở nơi khó kiểm soát hơn.

Hãy đo đồng thời pool wait, active connections, database CPU/I/O, query latency và lock waits trước khi thay pool size. Tăng từng bước và so sánh tại cùng workload.

## 14. Connection hold time và transaction duration

Connection hold time là thời gian connection được giữ bởi một thao tác hoặc transaction. Nó có thể lớn hơn query execution time nếu transaction gồm nhiều câu lệnh hoặc có logic nằm giữa các query.

Ví dụ không nên:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentClient.authorize(toPaymentRequest(order))
                            .thenReturn(order)
            );
}
~~~

Nếu HTTP call mất 2 giây, transaction có thể giữ connection trong suốt thời gian chờ. Điều này làm active connection tăng và pool dễ cạn.

Hãy đo transaction duration và connection hold time, không chỉ SQL duration. Giữ transaction ngắn bằng cách thực hiện lời gọi ngoài transaction hoặc chia workflow thành các transaction cục bộ, có trạng thái phục hồi.

## 15. Pool saturation biểu hiện ra sao?

Một số dấu hiệu:

- Active/acquired connection chạm max size trong thời gian dài.
- Pending acquire tăng.
- Acquire latency tăng p95/p99.
- Request timeout xảy ra trước khi query bắt đầu.
- Database CPU vẫn thấp nhưng ứng dụng chờ connection.
- Connection không quay về idle sau khi publisher kết thúc, có thể do leak hoặc transaction kéo dài.

Nếu active thấp nhưng query latency cao, bottleneck có thể ở database, network hoặc lock. Nếu pending cao và active luôn bằng max, cần xem connection hold time và workload. Nếu pool allocated thấp nhưng acquire timeout, kiểm tra lỗi tạo connection, validation hoặc cấu hình.

Đừng chỉ tăng max size khi thấy pending. Trước tiên xác định tại sao connection đang bị giữ và database có thể xử lý thêm concurrency hay không.

## 16. Throughput và connection pool có điểm bão hòa

Khi tăng tải, hệ thống thường trải qua các vùng:

1. **Underloaded:** ít request; latency thấp, pool còn idle.
2. **Efficient operating region:** throughput tăng gần tuyến tính, latency vẫn ổn định.
3. **Knee/saturation point:** throughput bắt đầu tăng chậm, latency và queue tăng nhanh.
4. **Overloaded:** pending request/connection tăng, timeout và lỗi xuất hiện; goodput có thể giảm.

~~~mermaid
flowchart LR
    A[Low load]
    B[Efficient region]
    C[Knee / saturation]
    D[Overload]
    A --> B --> C --> D
~~~

Mục tiêu vận hành nên nằm dưới điểm bão hòa với headroom cho burst và tăng trưởng. Không đặt SLO ngay tại mức tải tối đa mà benchmark có thể đạt trong vài giây.

## 17. Chọn workload để đo

Một bài test có ý nghĩa phải phản ánh các loại thao tác thực tế:

| Nhóm workload | Ví dụ | Đặc điểm cần ghi |
| --- | --- | --- |
| Read point lookup | Tìm entity theo ID | Số hàng nhỏ, thường có index |
| Read list | Danh sách có filter/sort/page | Cardinality và page size |
| Write single row | Insert/update một entity | Constraint, generated ID |
| Multi-step transaction | Tạo Order và OrderLine | Số query, transaction duration |
| Join/projection | Đọc DTO từ nhiều bảng | Join plan và row count |
| Bulk/streaming | Đọc hoặc ghi batch | Số hàng, memory, connection hold |
| Contended update | Nhiều request sửa cùng hàng | Lock wait và deadlock |

Ghi lại tỷ lệ hỗn hợp, ví dụ 70% read, 25% write, 5% workflow nhiều query. Tỷ lệ phải dựa trên telemetry hoặc yêu cầu dự kiến, không tùy chọn chỉ để kết quả đẹp.

## 18. Dữ liệu test phải đại diện

Benchmark với 100 hàng trong một bảng không mô tả tốt production có hàng chục triệu hàng. Dữ liệu test nên phản ánh:

- Số lượng hàng và kích thước bảng.
- Phân bố giá trị, mức độ trùng lặp và cardinality.
- Tỷ lệ NULL và dữ liệu dài.
- Index, constraint và foreign key.
- Hot key hoặc một số hàng bị truy cập thường xuyên.
- Tỷ lệ cache hit/miss.
- Độ rộng row và kích thước result set.
- Mức độ cập nhật đồng thời.

Nếu mọi request đều truy vấn một ID cố định, cache có thể làm benchmark nhanh bất thường. Nếu dữ liệu test quá nhỏ, index và working set có thể nằm hoàn toàn trong memory. Hãy mô phỏng phân bố truy cập thực tế.

## 19. Quy trình load test có thể lặp lại

Một lần kiểm thử nên có các giai đoạn:

1. **Environment preparation:** ghi lại phiên bản ứng dụng, JVM, driver, database, schema, pool và hạ tầng.
2. **Warm-up:** cho JVM, connection pool, JIT và database cache ổn định.
3. **Ramp-up:** tăng dần tải để quan sát lúc bắt đầu xuất hiện queue.
4. **Steady state:** giữ tải mục tiêu đủ lâu để đo latency/throughput ổn định.
5. **Burst:** kiểm tra khả năng hấp thụ đợt tăng tải ngắn.
6. **Soak:** chạy lâu để tìm leak, pool drift, memory growth hoặc degradation.
7. **Cool-down:** giảm tải và xác nhận resource được giải phóng.

Không so sánh một bản build được warm-up 10 phút với bản khác vừa khởi động. Cũng không so sánh benchmark khi database một bên đã cache dữ liệu còn bên kia chưa.

## 20. Open workload và closed workload

Hai mô hình phát tải phổ biến:

**Closed workload**

- Có số lượng virtual users cố định.
- Mỗi user gửi request, chờ response, rồi mới gửi request tiếp.
- Khi latency tăng, tốc độ phát request tự giảm.
- Phù hợp mô phỏng người dùng có think time.

**Open workload**

- Phát request theo tốc độ định trước, ví dụ 200 request/giây.
- Tốc độ gửi không tự giảm chỉ vì server chậm.
- Phù hợp kiểm tra khả năng đáp ứng offered load và phát hiện queue tăng.

Closed workload có thể che giấu saturation: server chậm thì client tự giảm tải, khiến throughput không tăng nhưng số request gửi cũng giảm. Open workload thể hiện rõ hơn việc hệ thống có theo kịp tốc độ yêu cầu hay không.

Chọn mô hình theo mục tiêu; có thể dùng cả hai. Luôn ghi lại offered load và completed throughput.

## 21. Ví dụ kịch bản đo bằng k6

Một kịch bản khung:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const failed = new Rate('failed_requests');

export const options = {
  scenarios: {
    api_load: {
      executor: 'ramping-arrival-rate',
      startRate: 20,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { target: 50, duration: '2m' },
        { target: 100, duration: '3m' },
        { target: 150, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
    failed_requests: ['rate<0.005'],
  },
};

export default function () {
  const response = http.get(
    'http://localhost:8080/api/products/42'
  );

  const ok = check(response, {
    'status is 200': (r) => r.status === 200,
  });

  failed.add(!ok);
}
~~~

Đây là ví dụ kịch bản, không phải ngưỡng production được khuyến nghị. Hãy điều chỉnh endpoint, dữ liệu, auth, tỷ lệ read/write, stages, VU và thresholds theo workload thật. Arrival-rate executor cần đủ VU để duy trì tốc độ phát; nếu không đủ, k6 có thể không tạo được offered load dự kiến và báo dropped iterations.

Đặt load generator trên máy hoặc hạ tầng riêng đủ mạnh. Nếu generator CPU bão hòa, kết quả không phản ánh năng lực server.

## 22. Đo riêng API và query database

Một bài test HTTP cho biết trải nghiệm bên ngoài, nhưng cần thêm telemetry ở ứng dụng/database:

- HTTP request duration và request count theo route.
- Service/use-case duration.
- R2DBC pool acquire latency, acquired, allocated, idle và pending.
- Query/statement duration theo loại thao tác.
- Transaction duration.
- Database CPU, memory, I/O, active sessions.
- Lock wait, deadlock và slow query.
- JVM CPU, heap, GC pause, thread và event-loop utilization.

Nếu HTTP p99 tăng nhưng query duration ổn định, hãy kiểm tra pool acquire, service logic, external dependency, serialization và event loop. Nếu query p99 tăng cùng database CPU hoặc lock wait, điều tra database và execution plan.

## 23. Instrumentation với Spring Boot Actuator và Micrometer

Spring Boot Actuator và Micrometer có thể cung cấp metrics cho HTTP server, JVM và các integration được hỗ trợ. R2DBC Pool có khả năng expose metrics khi bật instrumentation phù hợp.

Một số metric pool thường gặp trong hệ sinh thái R2DBC Pool có tên như:

- r2dbc.pool.acquired
- r2dbc.pool.allocated
- r2dbc.pool.idle
- r2dbc.pool.pending

Tên, tag và cách đăng ký phụ thuộc phiên bản pool, Spring Boot và registry. Hãy mở endpoint metrics/Prometheus của ứng dụng và kiểm tra metric thực tế thay vì giả định mọi tên luôn có sẵn.

Dependency Actuator và registry ví dụ:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Ví dụ cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
~~~

Chỉ expose endpoint metrics phù hợp với chính sách bảo mật. Không để endpoint quản trị mở công khai nếu có thông tin nội bộ.

## 24. Đo latency bằng histogram

Để tính percentile ở backend metrics, thường cần histogram hoặc distribution statistic phù hợp. Nếu chỉ gửi một gauge mean, hệ thống giám sát không thể khôi phục p95/p99 đáng tin cậy.

Histogram chia latency thành các bucket. Backend có thể tính percentile xấp xỉ từ phân bố bucket. Một số registry hỗ trợ percentile histogram ở client hoặc server; cách cấu hình tùy Micrometer registry.

Ví dụ khái niệm cấu hình distribution:

~~~java
Timer.builder("service.operation.duration")
        .description("Duration of a service operation")
        .publishPercentileHistogram()
        .register(meterRegistry);
~~~

Có thể đo một đoạn publisher bằng Reactor:

~~~java
return serviceOperation()
        .name("product.lookup")
        .tap(Micrometer.metrics(meterRegistry));
~~~

Đoạn code minh họa Reactor Micrometer integration; dependency và API chính xác phụ thuộc phiên bản Reactor/Micrometer. Nếu dùng Observation API của Spring, có thể instrument ở ranh giới service hoặc repository theo cách framework hỗ trợ.

Không bật quá nhiều histogram bucket cho mọi metric nếu chi phí cardinality và storage quá cao. Chọn số lượng metric và độ phân giải phù hợp với SLO.

## 25. Tránh high-cardinality metric tags

Không dùng các giá trị thay đổi theo từng request làm tag:

- User ID.
- Order ID.
- Email.
- Request ID.
- SQL parameter hoặc giá trị filter tùy ý.

Mỗi giá trị tag có thể tạo một time series riêng, khiến hệ thống metrics tốn memory, storage và query cost. Dùng tag có tập giá trị giới hạn:

- operation = read / write / search.
- repository = product / order / customer.
- outcome = success / error / timeout.
- route = template endpoint, ví dụ /api/products/{id}.

Correlation ID thuộc log/trace, không nên là metric label.

## 26. Tracing để tìm giai đoạn chậm

Distributed tracing có thể cho thấy một request chia thành các span:

~~~text
HTTP GET /api/orders/{id}              420 ms
  Controller / Service                 415 ms
    R2DBC pool acquire                   8 ms
    SELECT order                         35 ms
    SELECT order lines                   22 ms
    HTTP shipping service               330 ms
    DTO mapping                          10 ms
~~~

Trong ví dụ, database không phải bottleneck chính; lời gọi shipping service chiếm phần lớn latency. Tăng pool size sẽ không giải quyết được nguyên nhân.

Tracing nên ghi span cho external HTTP và database operation khi instrumentation hỗ trợ. Lấy mẫu trace (sampling) phù hợp ở production để tránh chi phí quá cao. Không gắn payload nhạy cảm vào span attributes.

## 27. Đo connection pool acquire và query riêng

Pool acquire latency trả lời câu hỏi: ứng dụng phải chờ bao lâu để có connection? Query latency trả lời: sau khi có connection, câu lệnh mất bao lâu?

Ví dụ:

| Kịch bản | Acquire p95 | Query p95 | Nhận định |
| --- | ---: | ---: | --- |
| A | 2 ms | 180 ms | Chủ yếu chậm ở query/database |
| B | 120 ms | 35 ms | Pool wait đáng kể |
| C | 3 ms | 40 ms | Database path tương đối ổn; tìm phần chậm ở service/HTTP |

Nếu không có metric acquire trực tiếp, có thể cần instrument ở connection factory/pool hoặc dùng metrics mà pool cung cấp. Đừng suy ra acquire time bằng cách trừ hai percentile độc lập; percentile của tổng và từng thành phần không cộng/trừ tuyến tính.

## 28. Đo transaction duration và lock contention

Transaction duration tăng có thể do:

- Nhiều query tuần tự.
- Query chậm.
- Lock wait.
- Logic CPU nằm trong transaction.
- Gọi HTTP hoặc chờ publisher khác khi transaction đang mở.
- Consumer chậm trong một Flux thuộc transaction.

Đo duration cùng số query/transaction, lock wait và connection hold time. Nếu transaction giữ connection 1 giây nhưng SQL chỉ chạy 50 ms, phần còn lại nằm ở logic hoặc chờ khác.

Với workflow nhiều bước, chỉ bao các thao tác cần nguyên tử trong transaction. Đặt HTTP call, gửi email và chờ broker ngoài transaction, hoặc dùng outbox để phát sau commit.

## 29. Đo query cụ thể và execution plan

Tổng query latency theo repository có thể che giấu một truy vấn rất chậm. Phân loại query theo operation/template hoặc statement name, rồi dùng database slow query log và execution plan.

Các yếu tố cần quan sát:

- Index scan hay full table scan.
- Số hàng ước lượng so với thực tế.
- Join strategy.
- Sort/hash operation.
- Rows returned và bytes transferred.
- Lock wait.
- Buffer/cache hit.
- Disk read/write.

Dùng EXPLAIN hoặc EXPLAIN ANALYZE theo database. EXPLAIN ANALYZE thực thi query, nên thận trọng với câu lệnh ghi và workload production. Query plan phụ thuộc dữ liệu và statistics; không kết luận chỉ từ schema nhỏ ở local.

## 30. Throughput của R2DBC và số query mỗi request

Một endpoint có thể tạo nhiều query cho mỗi HTTP request. Nếu throughput API là 100 request/giây và mỗi request thực hiện trung bình 4 query:

\[
\text{DB query rate} \approx 100 \times 4 = 400\ \text{queries/second}
\]

Đây là ước lượng trung bình; query song song và nhánh điều kiện có thể làm phân bố khác nhau. Hãy đo số query thực tế cho mỗi use case.

Nếu một endpoint tạo N+1 queries, query rate có thể tăng theo số entity trả về. Tối ưu JOIN hoặc batch loading có thể giảm số round trip và connection occupancy mà không cần tăng pool.

## 31. So sánh cấu hình pool bằng cùng một phương pháp

Khi thử pool size 10, 20 và 30:

1. Giữ nguyên ứng dụng, database, dữ liệu và workload.
2. Khởi động lại/đặt pool ở trạng thái tương đương.
3. Warm-up theo cùng thời gian.
4. Chạy cùng offered load và steady-state duration.
5. Thu thập p50/p95/p99, successful throughput, error rate, acquire wait, active/pending connections và DB CPU.
6. Lặp lại để nhận biết biến thiên.
7. So sánh mức cải thiện với chi phí connection tăng thêm.

Ví dụ kết quả:

| Pool max | Goodput | API p95 | Acquire p95 | DB CPU |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 90 RPS | 420 ms | 80 ms | 45% |
| 20 | 145 RPS | 230 ms | 12 ms | 68% |
| 30 | 148 RPS | 310 ms | 2 ms | 92% |

Bảng minh họa một điểm quan trọng: pool 30 giảm acquire wait nhưng throughput gần như không tăng và API p95 xấu hơn vì database gần bão hòa. Pool 20 có thể là điểm vận hành tốt hơn trong kịch bản này.

Không chọn cấu hình chỉ theo acquire latency. Mục tiêu là goodput và SLO ở mức tải cần thiết, đồng thời giữ headroom cho database.

## 32. Xác định ngưỡng tải và headroom

Sau khi chạy ramp test, xác định điểm mà:

- Throughput bắt đầu tăng chậm hơn offered load.
- p95/p99 bắt đầu tăng nhanh.
- Pending acquire hoặc request queue tăng liên tục.
- Database CPU/I/O hoặc lock wait gần giới hạn.
- Error/timeout xuất hiện.

Đây là vùng saturation/knee. Mục tiêu tải bình thường nên thấp hơn vùng này. Headroom có thể được xác định bằng mức tăng tải dự kiến, burst và thời gian cần để scale thêm instance/replica.

Ví dụ nếu hệ thống bắt đầu vi phạm p99 ở 220 RPS, không nên đặt capacity mục tiêu bình thường bằng 220 RPS. Cần chọn mức thấp hơn có dự phòng, ví dụ 150–170 RPS tùy biến động và kế hoạch tăng trưởng. Đây là cách minh họa; ngưỡng cụ thể phải dựa trên kết quả nhiều lần đo.

## 33. Soak test để phát hiện vấn đề theo thời gian

Một test 5 phút có thể không phát hiện:

- Connection leak tăng dần.
- Pool không trả connection sau cancellation.
- Memory tăng do buffer hoặc collectList trên dữ liệu lớn.
- Transaction dài hoặc job bị kẹt.
- Connection hết tuổi thọ đồng loạt.
- Replication lag hoặc queue tích tụ.

Soak test chạy workload ổn định trong thời gian dài hơn, ví dụ hàng chục phút hoặc vài giờ tùy mục tiêu. Theo dõi active/idle/pending, heap, GC, DB sessions, error rate và latency theo thời gian.

Nếu active connections tăng dần rồi không giảm khi tải giữ nguyên hoặc đã dừng, cần điều tra resource lifecycle và transaction boundary.

## 34. Đo khi có cancellation và timeout

Trong WebFlux, client có thể ngắt kết nối; Reactor có thể hủy subscription. Cần đo:

- Số request bị cancel.
- Thời gian từ cancellation đến khi connection được trả về pool.
- Số connection active sau khi test client dừng.
- Query còn chạy trên database sau khi caller cancel hay không.
- Transaction rollback count.

Cancellation không bảo đảm database dừng statement ngay lập tức; hành vi phụ thuộc driver/database. Kết hợp timeout ở Reactor, statement/query timeout ở database và metric pool để đánh giá.

Một test có thể:

1. Gửi request tạo stream dài.
2. Nhận một phần dữ liệu rồi đóng client.
3. Quan sát cancellation.
4. Kiểm tra pool active/idle và DB session.
5. Xác nhận connection có thể được tái sử dụng.

## 35. Đặt mục tiêu connection acquire và pool wait

Không chỉ đặt max connection. Cần xác định thời gian chờ tối đa để lấy connection:

- Nếu acquire timeout quá dài, request có thể chờ rất lâu rồi mới thất bại.
- Nếu quá ngắn, burst ngắn có thể tạo lỗi dù hệ thống sắp giải phóng connection.
- Nếu pending queue không giới hạn, memory và latency có thể tăng.

Đặt acquire timeout dựa trên request deadline và latency budget. Ví dụ request có deadline 1 giây thì không nên cho pool acquire chờ 5 giây. Cần dành thời gian cho query, service logic và serialize response.

Khi pool hết connection, hãy quyết định rõ ứng dụng chờ có giới hạn hay từ chối sớm. Không để request queue vô hạn.

## 36. Phân bổ latency budget

Một API có SLO 500 ms có thể phân bổ ngân sách nội bộ:

| Thành phần | Budget minh họa |
| --- | ---: |
| Routing/Controller/Service | 40 ms |
| Pool acquire | 20 ms |
| Database queries | 180 ms |
| External dependency | 150 ms |
| Mapping/serialization/network overhead | 60 ms |
| Safety margin | 50 ms |
| **Tổng** | **500 ms** |

Đây là ví dụ lập kế hoạch, không phải percentile cộng chính xác. Các thành phần có thể chạy song song, và percentile của từng span không cộng thành percentile end-to-end. Dùng budget để đặt ngưỡng cảnh báo/điều tra, sau đó xác minh bằng trace thực tế.

## 37. Mục tiêu cho từng loại endpoint

Không nên áp một SLO cho mọi endpoint:

| Loại endpoint | Latency cần chú ý | Throughput cần chú ý | Connection behavior |
| --- | --- | --- | --- |
| Point read | p95/p99, cache hit | Read RPS | Query ngắn |
| Search/list | Time to first row, total response | RPS và rows/s | Result size, streaming |
| Create/update | End-to-end commit latency | Successful writes/s | Transaction duration |
| Multi-step workflow | Tổng thời gian và từng dependency | Workflow completions/s | Không giữ connection khi gọi HTTP |
| Bulk export | Total duration, throughput rows/s | Rows/s | Stream/batch, connection hold |
| Contended write | p99, lock wait, error rate | Goodput dưới contention | Active connections, deadlock |

Một endpoint list có thể cần giới hạn page size; một endpoint export cần streaming; một endpoint ghi có thể ưu tiên tính đúng đắn hơn RPS cực đại.

## 38. Tác động của event loop và CPU

R2DBC là non-blocking I/O, nhưng phần code ứng dụng vẫn có thể block event-loop:

- Gọi JDBC/blocking HTTP client.
- Dùng block() trên Mono/Flux.
- Chạy xử lý CPU nặng trực tiếp trên event-loop.
- Serialize payload rất lớn mà không kiểm soát.

Khi event-loop bị block, latency có thể tăng trên nhiều request dù database query vẫn nhanh. Theo dõi CPU, event-loop utilization, thread dump và blocking detection nếu có.

Không chuyển mọi thao tác sang boundedElastic một cách máy móc. Dùng scheduler phù hợp cho công việc blocking thật sự và ưu tiên API non-blocking trong luồng reactive.

## 39. So sánh R2DBC với JDBC công bằng

Nếu mục tiêu đo là đánh giá lựa chọn R2DBC, cần giữ các điều kiện tương đương:

- Cùng database instance và schema.
- Cùng dữ liệu, index và query.
- Cùng transaction semantics.
- Cùng connection budget.
- Cùng số application instances.
- Cùng workload mix và arrival model.
- Cùng thời gian warm-up và steady-state.
- Cùng cách đo percentile, error và goodput.

Không so một JDBC pool 50 connection với R2DBC pool 10 connection rồi kết luận về protocol. Cũng không so JDBC blocking với R2DBC trong benchmark mà một bên có số thread hoặc client concurrency khác biệt đáng kể mà không ghi rõ.

Đo cả throughput, tail latency, CPU, memory, thread, connection count và chi phí vận hành. R2DBC có thể hữu ích khi cần xử lý nhiều I/O đồng thời với ít thread hơn, nhưng hiệu quả thực tế phụ thuộc workload và driver.

## 40. Ghi lại benchmark để có thể tái lập

Mỗi lần đo nên lưu:

- Git commit/build version.
- Java/JVM version và flags.
- Spring Boot, Spring Data Relational, Reactor và R2DBC driver versions.
- Database engine/version và cấu hình.
- Schema, số hàng và index.
- Connection pool options.
- Số instance và tài nguyên CPU/memory.
- Workload mix, data distribution và arrival model.
- Ramp-up, warm-up, steady-state, soak duration.
- p50/p95/p99, goodput, error rate.
- Active/idle/pending connections và acquire latency.
- Database CPU/I/O, locks và slow queries.

Nếu thiếu các thông tin này, hai kết quả benchmark không thể so sánh đáng tin cậy.

## 41. Ví dụ báo cáo mục tiêu đo

Một báo cáo có thể trình bày:

~~~text
Use case: GET /api/products/{id}
Database: PostgreSQL, phiên bản đã ghi nhận
Application: 3 instances
Pool: max size 20 per instance
Workload: 90% point reads, 10% updates
Arrival rate: ramp 50 -> 150 -> 200 RPS
Warm-up: 5 minutes
Steady state: 10 minutes per stage

At 150 offered RPS:
  successful throughput: 149 RPS
  p50: 38 ms
  p95: 115 ms
  p99: 280 ms
  error rate: 0.1%
  pool acquired: peak 14 per instance
  pool pending: 0 sustained
  acquire p95: 4 ms

Database:
  CPU: 62%
  active sessions: measured separately
  lock waits: within agreed threshold
~~~

Đây là mẫu định dạng báo cáo, không phải kết quả đo thật. Cần thay mọi giá trị bằng dữ liệu thu được từ test.

## 42. Các lỗi thường gặp khi đặt mục tiêu đo

1. **Chỉ dùng latency trung bình.** Tail latency có thể rất xấu dù mean thấp.
2. **Báo offered load là throughput.** Request gửi đi chưa chắc đã hoàn tất thành công.
3. **Đặt pool size bằng HTTP concurrency.** Request không giữ connection DB trong toàn bộ vòng đời.
4. **Tăng pool để sửa mọi timeout.** Bottleneck có thể ở database hoặc transaction hold time.
5. **Không tính tổng pool trên nhiều instance.** Tổng connection có thể vượt database limit khi scale-out.
6. **Đo query nhưng bỏ qua pool acquire.** Request có thể chờ lâu trước khi SQL bắt đầu.
7. **Đo HTTP nhưng không có database telemetry.** Khó tìm tầng gây chậm.
8. **Dùng dataset quá nhỏ.** Cache và execution plan không đại diện production.
9. **Chỉ chạy test ngắn.** Không thấy leak, pool drift hoặc degradation.
10. **Dùng closed workload mà không ghi offered load.** Khi server chậm, client tự giảm tốc độ gửi.
11. **Chọn điểm RPS tối đa dù p99 vi phạm SLO.** Goodput cao không đủ nếu trải nghiệm không đạt.
12. **Cộng/trừ percentile của các span.** Percentile không có tính cộng tuyến tính.
13. **Bật metric tag theo user/request ID.** Tạo high cardinality và tăng chi phí monitoring.
14. **Không ghi lại cấu hình benchmark.** Kết quả không thể tái lập.
15. **Cho rằng reactive tự động tăng throughput.** Database, query, pool, CPU và network vẫn có giới hạn.

## Quy trình xác định mục tiêu đo

1. Chọn các use case quan trọng và phân loại read, write, transaction, streaming.
2. Xác định workload mix, offered load bình thường, tải đỉnh và burst.
3. Đặt latency SLO theo p95/p99 cho từng nhóm endpoint.
4. Đặt goodput tối thiểu và error rate tối đa ở tải mục tiêu.
5. Ước lượng connection demand từ DB operation rate và connection hold time; đối chiếu bằng pool metrics.
6. Tính ngân sách tổng connection theo số instance, writer/reader pool và client khác.
7. Instrument HTTP, service, pool, query, transaction và database.
8. Chạy warm-up, ramp, steady-state, burst và soak test trên dữ liệu đại diện.
9. Tìm điểm saturation và chọn operating target có headroom.
10. Lưu cấu hình và kết quả để so sánh sau mỗi thay đổi.

Độ trễ, thông lượng và số kết nối là ba góc nhìn bổ sung để xác định khả năng phục vụ của ứng dụng Spring Data R2DBC. Hãy đo latency bằng percentile ở cả HTTP, pool, query và transaction; đo throughput bằng số thao tác hoàn tất thành công ở workload đã định nghĩa; và quản lý connection theo active/idle/pending cùng ngân sách toàn hệ thống. Kết hợp Little's Law, load test có thể lặp lại, telemetry của Micrometer/R2DBC Pool và chỉ số database giúp tìm điểm bão hòa, chọn pool size hợp lý và đặt mục tiêu vận hành có dự phòng thay vì tối ưu một con số đơn lẻ.
