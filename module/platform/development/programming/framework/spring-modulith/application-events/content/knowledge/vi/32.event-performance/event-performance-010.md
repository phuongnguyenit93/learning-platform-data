# Đo đạc bằng profiling

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, publisher, Event Publication Registry, listener và adapter externalization cùng tham gia vào đường đi của application event. Khi throughput giảm hoặc độ trễ tăng, chỉ nhìn tổng thời gian request hay số message trong broker thường không đủ để biết thành phần nào đang tiêu tốn CPU, cấp phát bộ nhớ, chờ lock hoặc chờ I/O. **Profiling** giúp quan sát hoạt động bên trong tiến trình Java để tìm vị trí thực sự gây tốn tài nguyên.

Profiling có giá trị nhất khi được thực hiện theo một giả thuyết cụ thể, trên workload đại diện và có số liệu trước/sau để so sánh. Mục tiêu không phải thu thập càng nhiều dữ liệu càng tốt, mà là xác định phần việc nào chiếm thời gian hoặc tài nguyên, vì sao nó xảy ra và thay đổi nào cải thiện được hiệu năng mà vẫn giữ đúng semantics giao sự kiện.

## 1. Phân biệt profiling với metrics, tracing và logging

Bốn kỹ thuật quan sát bổ sung cho nhau nhưng trả lời những câu hỏi khác nhau:

| Kỹ thuật | Câu hỏi chính | Ví dụ |
|---|---|---|
| Metrics | Hệ thống đang hoạt động ở mức nào theo thời gian? | Event/s, listener latency p95, backlog, heap usage |
| Distributed tracing | Một event đi qua những chặng nào và chặng nào chậm? | Publish → broker → consumer → projection |
| Logging | Điều gì đã xảy ra tại một thời điểm cụ thể? | Listener lỗi với event ID, exception và correlation ID |
| Profiling | CPU, bộ nhớ, lock và thread đang được dùng ở đâu bên trong JVM? | Serialization chiếm CPU, allocation tạo nhiều object, thread chờ connection |

Metrics và tracing giúp khoanh vùng thành phần có vấn đề. Profiling đi sâu vào stack trace, method, thread hoặc loại allocation bên trong thành phần đó.

Ví dụ, metric cho thấy thời gian xử lý OrderConfirmed tăng từ 15 ms lên 120 ms. Trace cho thấy phần lớn thời gian nằm trong InventoryListener. CPU profile có thể chỉ ra JSON mapping chiếm CPU; allocation profile có thể phát hiện listener tạo nhiều object trung gian; lock profile có thể cho thấy nhiều thread tranh chấp cùng một lock.

Không dùng profiling thay cho metrics hoặc tracing. Một profile ngắn là ảnh chụp hoạt động của tiến trình trong một khoảng thời gian; nó không tự cho biết xu hướng backlog trong nhiều giờ hoặc SLO của từng consumer.

## 2. Bắt đầu bằng câu hỏi và giả thuyết

Trước khi chạy profiler, hãy mô tả triệu chứng và giả thuyết cần kiểm chứng.

Ví dụ:

- Throughput listener giảm khi số event tăng: nghi ngờ CPU-bound hoặc contention.
- Heap tăng nhanh khi backlog tăng: nghi ngờ payload lớn, queue trong bộ nhớ hoặc object được giữ tham chiếu quá lâu.
- CPU thấp nhưng latency cao: nghi ngờ I/O wait, database lock, connection pool hoặc broker.
- Chỉ một loại event chậm: nghi ngờ payload, serializer hoặc nhánh xử lý riêng của listener.
- Độ trễ tăng sau khi thêm listener: nghi ngờ fan-out, transaction work hoặc executor dùng chung.
- GC tăng khi event burst: nghi ngờ allocation rate cao hoặc object sống lâu do backlog.
- Nhiều thread ở trạng thái WAITING/BLOCKED: nghi ngờ lock, queue hoặc pool bị cạn.

Mỗi lần đo nên trả lời một câu hỏi chính. Nếu vừa thay serializer, tăng concurrency, đổi queue và bật thêm listener cùng lúc, sẽ khó xác định thay đổi nào tạo ra kết quả.

Một giả thuyết tốt có thể bị bác bỏ bằng dữ liệu. Ví dụ: “JSON serialization chiếm hơn 30% CPU của publisher khi phát 2.000 event/giây”. Sau khi profile, có thể xác nhận hoặc loại bỏ giả thuyết đó.

## 3. Chọn loại profiling phù hợp

### CPU profiling

CPU profile cho biết thread đang thực thi method nào trong khoảng thời gian lấy mẫu. Dùng khi CPU cao hoặc throughput bị giới hạn bởi xử lý tính toán.

Trong luồng event, stack có thể chỉ ra:

- JSON serialization/deserialization.
- Mapping DTO và validation.
- Chuyển đổi collection hoặc stream.
- Business rule trong listener.
- Hashing, compression hoặc encryption payload.
- Logging format và stack trace generation.
- Framework dispatch hoặc reflection nếu xuất hiện đáng kể.

CPU profile không trực tiếp đo thời gian chờ database hoặc network. Một method có tổng thời gian wall-clock dài có thể không xuất hiện nổi bật trong CPU flame graph nếu phần lớn thời gian của nó là chờ I/O.

### Allocation profiling

Allocation profile cho biết object nào được tạo nhiều hoặc tiêu tốn nhiều byte. Dùng khi heap tăng, GC chạy thường xuyên hoặc event throughput tạo áp lực bộ nhớ.

Các nguồn allocation thường gặp:

- Object graph lớn được serialize.
- Tạo nhiều String hoặc byte array cho mỗi event.
- Sao chép payload giữa adapter và converter.
- Buffer tạm trong compression hoặc encryption.
- Collection trung gian trong mapping.
- Exception được tạo trong luồng lỗi/retry.
- Message wrapper và metadata lặp lại.

Phân biệt allocation rate với retained heap. Một object được tạo nhiều nhưng sống rất ngắn có thể làm tăng GC; object được giữ lại bởi queue hoặc cache có thể làm heap tăng lâu dài. Cần dùng heap analysis khi nghi ngờ retained object, không chỉ dựa vào allocation flame graph.

### Lock và contention profiling

Lock profile giúp tìm thread bị chặn hoặc chờ monitor. Với ứng dụng event-driven, contention có thể xuất hiện ở:

- Một singleton listener có mutable state.
- Shared cache hoặc map.
- Khóa trên aggregate hoặc projection.
- Database row lock.
- Connection pool hoặc executor queue.
- Một đoạn đồng bộ hóa bao quanh serialize hoặc xử lý event.

Nếu nhiều thread cùng chờ một lock, tăng concurrency có thể làm throughput tệ hơn. Hãy tìm critical section và thời gian giữ lock trước khi tăng số worker.

### Wall-clock và I/O profiling

Wall-clock profile ghi nhận thời gian thực mà thread dành cho cả chạy và chờ. Nó hữu ích khi CPU không cao nhưng request hoặc listener vẫn chậm.

Cần phân biệt:
- CPU execution time.
- Thời gian chờ monitor/lock.
- Thời gian chờ socket hoặc database.
- Thời gian chờ executor hoặc queue.
- Thời gian chờ scheduler và timer.

Một profiler có thể đặt tên mode khác nhau; kiểm tra tài liệu của công cụ và phiên bản đang dùng trước khi diễn giải kết quả.

## 4. Java Flight Recorder và JDK Mission Control

Java Flight Recorder (JFR) là công cụ profiling và ghi sự kiện runtime tích hợp trong JDK hiện đại. JFR có thể thu thập thông tin về CPU samples, allocation, garbage collection, thread, lock, I/O và các sự kiện JVM khác với overhead thường phù hợp cho nhiều tình huống production khi cấu hình hợp lý.

JDK Mission Control (JMC) giúp mở file recording và phân tích:
- Hot methods và execution samples.
- Thread states và thread contention.
- Allocation và garbage collection.
- Socket/file I/O.
- GC pauses và heap behavior.
- Các sự kiện runtime theo timeline.

### Bắt đầu recording bằng jcmd

Có thể kiểm tra tiến trình Java và recording đang có bằng các lệnh JDK:

~~~bash
jcmd -l
jcmd <PID> JFR.check
~~~

Bắt đầu một recording có thời hạn, dùng profile settings và ghi ra file:

~~~bash
jcmd <PID> JFR.start name=event-profile settings=profile duration=60s filename=event-profile.jfr
~~~

Nếu muốn chủ động dừng trước thời hạn hoặc dump recording đang chạy:

~~~bash
jcmd <PID> JFR.dump name=event-profile filename=event-profile.jfr
jcmd <PID> JFR.stop name=event-profile
~~~

Thay `<PID>` bằng process ID thực tế. Các lệnh cần chạy bằng user có quyền attach phù hợp với JVM. Đường dẫn file phải có quyền ghi và đủ dung lượng. Tùy JDK version, runtime container và chính sách bảo mật, attach có thể bị giới hạn.

Có thể dùng `settings=default` cho recording nhẹ hơn hoặc `settings=profile` khi cần nhiều chi tiết hơn. Hãy kiểm tra cấu hình JFR và overhead trong môi trường đại diện trước khi thu trên production. Recording dài hoặc cấu hình quá chi tiết có thể tạo file lớn và tăng chi phí quan sát.

### Phân tích recording

Mở file `event-profile.jfr` bằng JMC và kiểm tra theo giả thuyết:

1. Xem CPU usage và top methods trong khoảng tải cao.
2. Chọn thread liên quan đến publisher hoặc listener.
3. Kiểm tra stack trace có lặp lại ở serializer, mapper hoặc business code không.
4. Xem allocation và GC nếu heap/GC là triệu chứng.
5. Kiểm tra monitor blocked và thread park nếu throughput thấp dù CPU còn dư.
6. Xem socket/database I/O nếu listener chờ downstream.
7. So sánh các khoảng thời gian có và không có backlog.

Không kết luận từ một stack đơn lẻ. Hãy kiểm tra tỷ lệ xuất hiện, số thread bị ảnh hưởng, thời gian và mối liên hệ với workload.

## 5. Async-profiler và flame graph

Async-profiler là một công cụ profiling cho JVM có thể lấy mẫu CPU, allocation, lock và một số dạng hoạt động khác tùy hệ điều hành và phiên bản. Công cụ thường tạo flame graph để biểu diễn stack trace tích lũy.

Trong flame graph:
- Trục ngang biểu diễn lượng mẫu tích lũy, không phải thứ tự thời gian.
- Khối rộng cho biết stack hoặc method xuất hiện trong nhiều mẫu.
- Khối cao thể hiện độ sâu của call stack.
- Một nhánh rộng ở dưới thường là nơi đáng điều tra trước.

Có thể dùng các mode CPU, allocation hoặc lock để kiểm tra giả thuyết tương ứng. Hãy chọn mode theo tài liệu đúng phiên bản async-profiler, JVM và hệ điều hành. Không chạy đồng thời nhiều profiler nặng nếu chưa đánh giá overhead.

Flame graph giúp phát hiện hot path nhưng không chứng minh method đó là nguyên nhân gốc. Ví dụ Jackson xuất hiện rộng có thể do payload lớn, do serialize lặp hoặc do listener fan-out; cần kết hợp số event, kích thước payload và trace để giải thích.

## 6. Profiling một luồng application event

Đường đi event nên được chia thành các chặng có thể đo độc lập:

1. Command handler và publisher tạo event.
2. Ghi nhận publication vào Event Publication Registry.
3. Serialize payload nếu implementation cần lưu event.
4. Dispatch đến listener hoặc đưa task vào executor.
5. Listener deserialize/map dữ liệu và thực hiện logic.
6. Listener truy cập database hoặc dịch vụ ngoài.
7. Registry cập nhật trạng thái hoàn tất.
8. Adapter externalization gửi message đến broker nếu có.
9. Consumer bên ngoài xử lý message và cập nhật projection.

Không phải ứng dụng nào cũng thực hiện mọi chặng theo cùng thứ tự hoặc dùng cùng serializer. Hãy dựa trên cấu hình thực tế và đo đúng ranh giới đang tồn tại.

Một bảng phân tích có thể dùng:

| Chặng | Metric/trace | Câu hỏi profiling |
|---|---|---|
| Publisher | Publish duration, event rate | Tạo event hoặc mapping có tốn CPU không? |
| Registry persistence | DB duration, connection wait | Insert/update publication có chậm hoặc tranh chấp không? |
| Serialization | Serialize duration, payload bytes | Mapper, reflection hoặc allocation có chiếm tài nguyên không? |
| Executor | Queue depth, active threads | Task đang chờ hay thread bị block? |
| Listener | Handler duration, CPU samples | Business logic nào là hot path? |
| Downstream | DB/API latency, pool wait | Thread đang chờ tài nguyên nào? |
| Externalization | Publish confirm latency, send rate | Network, conversion hay broker response gây chậm? |
| Consumer | Consumer lag, processing duration | Nút thắt nằm ở dịch vụ nhận hay projection? |

Publication Registry đo trạng thái giao đến listener của ứng dụng; nó không thay thế profiling hoặc đo broker consumer. Nếu event được externalize, cần quan sát thêm chặng transport và consumer.

## 7. Tạo workload profiling đại diện

Profile chỉ hữu ích nếu workload gần với production. Một test chỉ phát vài event nhỏ không phản ánh luồng có nhiều listener, payload lớn, database và retry.

Hãy chuẩn bị workload có kiểm soát:

- Event type đại diện cho luồng phổ biến và luồng nặng.
- Payload với kích thước trung bình và phân vị lớn.
- Số listener thực tế và fan-out tương ứng.
- Tỷ lệ listener thành công/lỗi gần với workload dự kiến.
- Cấu hình executor, connection pool và broker tương tự production.
- Số instance và concurrency có ý nghĩa.
- Tải ổn định đủ lâu để JIT warm-up và hệ thống đạt trạng thái steady state.
- Một đợt burst nếu cần đánh giá allocation, queue và GC khi tải tăng đột biến.

Ghi lại tốc độ event, số listener, kích thước payload, backlog, latency p50/p95/p99, CPU, heap, GC và cấu hình môi trường cùng recording. Nếu không có thông tin workload, rất khó so sánh hai profile.

Không tạo tải production tùy tiện chỉ để lấy profile. Dùng staging hoặc canary có giới hạn; nếu cần thu production, chọn cửa sổ tải và thời lượng phù hợp với chính sách vận hành.

## 8. Warm-up và cách lấy mẫu

JVM có JIT compilation, class loading, cache và connection pool. Những phút đầu sau startup có thể khác đáng kể so với steady state.

Một quy trình đo hợp lý:

1. Khởi động ứng dụng với cấu hình đã ghi lại.
2. Đợi readiness và các dependency sẵn sàng.
3. Phát workload warm-up để JIT và cache ổn định.
4. Bắt đầu đo baseline metrics.
5. Chạy workload ổn định trong khoảng thời gian xác định.
6. Bắt đầu recording/profile trong cửa sổ đo.
7. Kết thúc recording và lưu thông tin workload.
8. Lặp lại cùng điều kiện để xác nhận kết quả có thể tái lập.

Sampling profiler lấy mẫu stack theo chu kỳ, nên ít gây ảnh hưởng hơn instrumentation ở mọi method trong nhiều trường hợp. Nhưng sampling có thể bỏ lỡ method rất ngắn hoặc hiếm. Instrumentation profiler có thể đo chính xác hơn một số method nhưng làm thay đổi timing và overhead đáng kể.

Dùng sampling để tìm hot path trước. Chỉ dùng instrumentation hoặc event chi tiết hơn khi cần trả lời câu hỏi mà sampling không giải quyết được.

## 9. Đọc CPU profile và flame graph

Khi CPU profile cho thấy một method nổi bật, cần kiểm tra toàn bộ call path và workload liên quan.

Ví dụ các dấu hiệu:

- `ObjectMapper.writeValueAsBytes` hoặc các method Jackson rộng: kiểm tra payload size, cấu hình mapper và số lần serialize.
- `StringBuilder`, encoder hoặc byte array copy rộng: kiểm tra tạo chuỗi, chuyển đổi charset và sao chép payload.
- Collection mapping rộng: xem có tạo nhiều collection trung gian hoặc lặp qua dữ liệu không cần thiết.
- Logging method rộng: giảm log đồng bộ hoặc format payload lớn ở hot path.
- Reflection/proxy rộng: kiểm tra mapping và dispatch; không tối ưu framework internals nếu chưa chứng minh được lợi ích.
- Domain method rộng: xem thuật toán, truy vấn lặp hoặc việc tải entity không cần thiết.

CPU profile thể hiện nơi CPU được dùng, không phải nơi mọi latency phát sinh. Nếu CPU thấp mà listener chậm, chuyển sang wall-clock, thread, lock và I/O analysis.

Sau khi thay đổi, đo lại cùng workload. Một method bớt CPU nhưng tạo thêm allocation hoặc tăng database round-trip có thể làm end-to-end latency xấu hơn.

## 10. Đọc allocation và GC profile

Event processing thường tạo nhiều object ngắn hạn: event envelope, DTO, JSON tree, byte array, message properties và collection. Allocation rate cao có thể khiến GC chạy thường xuyên, dù heap sau GC vẫn còn trống.

Hãy xem:
- Bytes allocated per event.
- Allocation rate theo thời gian.
- Loại object được tạo nhiều nhất.
- Object nào được giữ lại bởi queue hoặc listener.
- GC frequency, pause duration và concurrent GC CPU.
- Heap occupancy sau GC.
- Số lượng thread-local hoặc cache giữ object lâu dài.

Các hướng tối ưu thường gặp:
- Giảm payload và tránh serialize object graph dư thừa.
- Tránh tạo nhiều bản sao byte array hoặc String.
- Dùng DTO gọn thay entity ORM.
- Hạn chế collection trung gian trong hot path.
- Giới hạn queue trong bộ nhớ để backlog không giữ vô hạn object.
- Không cache payload/event nếu không có chính sách kích thước và eviction rõ.

Không tối ưu bằng object pooling một cách mặc định. Pooling có thể giữ object lâu hơn, tạo contention và làm code phức tạp. Chỉ cân nhắc sau khi profile chứng minh allocation cụ thể là bottleneck và benchmark cho thấy cải thiện.

## 11. Thread, lock và blocking I/O

Event listener bất đồng bộ thường chạy trên executor. Nếu thread pool có nhiều thread nhưng downstream chỉ có ít connection, thread có thể chờ pool thay vì làm việc hữu ích.

Khi profile thread, kiểm tra:
- RUNNABLE: thread đang chạy hoặc sẵn sàng chạy; cần đối chiếu CPU.
- BLOCKED: thread chờ monitor lock.
- WAITING/TIMED_WAITING: thread chờ condition, queue, future, sleep hoặc timeout.
- Socket read/write: thread chờ network.
- JDBC call: thread chờ database hoặc connection pool.
- Executor queue: task chưa được thread xử lý.

Một thread dump tại một thời điểm có thể giúp hiểu trạng thái, nhưng nhiều thread dump cách nhau một khoảng ngắn sẽ cho biết trạng thái có kéo dài hay chỉ thoáng qua. JFR có thể bổ sung timeline cho lock và thread events.

Nếu listener gọi dịch vụ ngoài đồng bộ, profiling có thể cho thấy phần lớn thời gian nằm ở socket wait. Khi đó tối ưu CPU không giải quyết được bottleneck; cần xem timeout, connection reuse, concurrency, batching, async client hoặc giới hạn tải.

## 12. Đo serializer và Event Publication Registry

Serialization và persistence có thể nằm trên đường phát hoặc phục hồi publication. Hãy đo riêng thời gian và tài nguyên:

- Thời gian serialize/deserialize theo event type.
- Payload bytes trung bình và p95.
- Allocation bytes per event.
- Thời gian ghi publication và cập nhật trạng thái hoàn tất.
- Database connection acquisition và query latency.
- Lock wait/deadlock.
- Số publication chưa hoàn tất và tuổi lớn nhất.

Không suy luận registry chậm chỉ từ việc bảng publication tăng. Có thể listener đang chậm hoặc executor không theo kịp. Cần kết hợp database metrics và profile thread để phân biệt thời gian query với thời gian chờ connection.

Tránh viết truy vấn trực tiếp vào schema nội bộ của registry chỉ để đo performance nếu framework cung cấp API hoặc metric phù hợp. Schema có thể thay đổi theo implementation/version; dashboard nên dựa trên contract quan sát được.

## 13. Profiling listener và fan-out

Một event có thể được giao cho nhiều listener. Tổng chi phí có thể tăng theo số listener, nhưng không nhất thiết tuyến tính vì listener dùng chung CPU, database, cache hoặc executor.

Khi thêm listener mới, đo:
- Chi phí dispatch và tạo publication.
- Số publication tăng thêm trên mỗi event.
- Executor queue và thread utilization.
- Listener latency theo từng loại.
- Database queries và connection usage.
- Tổng CPU/alloc trên mỗi event nguồn.
- Tác động đến các listener hiện có.

Nếu một listener rất chậm, hãy tách nó khỏi executor hoặc luồng có SLO nghiêm ngặt khi kiến trúc cho phép. Nếu nhiều listener cùng ghi một database, tối ưu truy vấn và transaction trước khi tăng concurrency.

Không kết luận một listener là nguyên nhân chỉ vì nó có duration lớn. Có thể listener đang chờ một downstream mà nhiều luồng khác cũng sử dụng. Tracing và profiling cần được đọc cùng nhau.

## 14. Profiling externalization và broker adapter

Khi application event được externalize, có thêm serialization cho wire format, network I/O, broker confirm và consumer processing. Cần phân biệt thời gian publisher gửi message với thời gian consumer hoàn tất.

Các câu hỏi cần trả lời:

- Adapter có serialize lại payload hay chuyển đổi DTO không?
- Có sao chép payload nhiều lần giữa object, byte array và message wrapper không?
- Publisher confirm latency có tăng không?
- Connection/channel có được tái sử dụng không?
- Broker có flow control hoặc disk alarm không?
- Consumer prefetch và concurrency có phù hợp không?
- Consumer lag tăng ở partition hoặc queue nào?
- Retry có tạo thêm CPU/network load không?

Nếu publisher nhanh nhưng consumer lag tăng, profiling publisher không giải quyết được vấn đề. Cần profile consumer process và kiểm tra broker metrics riêng. Với RabbitMQ, quan sát ready/unacked và consumer count; với Kafka, xem consumer lag, partition assignment và poll/commit behavior.

## 15. Dùng tracing để nối profile với event

Profiler thường quan sát stack trong JVM, trong khi tracing theo dõi một event cụ thể qua các chặng. Để kết nối hai góc nhìn, event nên mang metadata truy vết ổn định:

- eventId để nhận diện event.
- correlationId để liên kết luồng nghiệp vụ.
- causationId để biết message nào tạo ra event.
- eventType để phân nhóm.
- aggregateId hoặc business key khi được phép.
- timestamp hoặc sequence có ý nghĩa.

Không đưa các ID có cardinality cao thành metric tag. Chúng phù hợp với log/trace hoặc công cụ tra cứu có phân quyền. Metrics nên dùng tag giới hạn như event type, listener name, outcome và destination đã chuẩn hóa.

Trong async execution, trace context cần được truyền qua executor hoặc transport bằng cơ chế instrumentation phù hợp. Không giả định ThreadLocal tự động tồn tại sau khi chuyển thread hoặc qua broker.

## 16. So sánh trước và sau tối ưu

Một thay đổi chỉ được xem là cải thiện khi kết quả được đo lại trên cùng workload và điều kiện tương đương.

Ghi baseline:

| Chỉ số | Trước thay đổi | Sau thay đổi |
|---|---:|---:|
| Event throughput | Đo thực tế | Đo lại |
| Listener latency p95/p99 | Đo thực tế | Đo lại |
| CPU per event | Đo thực tế | Đo lại |
| Allocation bytes/event | Đo thực tế | Đo lại |
| GC pause/time | Đo thực tế | Đo lại |
| Oldest publication age | Đo thực tế | Đo lại |
| Executor queue depth | Đo thực tế | Đo lại |
| DB wait/lock time | Đo thực tế | Đo lại |

Giữ nguyên event mix, payload, listener set, concurrency, JVM flags và dependency version khi so sánh. Nếu một điều kiện buộc phải thay đổi, ghi rõ để tránh kết luận sai.

Không chỉ tối ưu average latency. Theo dõi tail latency, tỷ lệ lỗi, retry, duplicate và backlog. Tối ưu throughput bằng cách tăng concurrency có thể làm p99 tệ hơn hoặc gây quá tải database.

## 17. Những sai lầm thường gặp khi profiling

**Profile workload không đại diện.** Event nhỏ, ít listener hoặc không có database khiến kết quả không giống production.

**Đo ngay sau startup.** JIT, class loading và cache chưa ổn định có thể làm sai số liệu.

**Chỉ nhìn CPU.** CPU thấp nhưng thread có thể chờ lock, database, network hoặc executor.

**Bật quá nhiều instrumentation.** Profiler có thể làm thay đổi timing, allocation và lock behavior.

**Đọc flame graph như timeline.** Chiều ngang biểu diễn lượng mẫu tích lũy, không phải thứ tự thời gian.

**Tối ưu method nổi bật mà không hiểu call path.** Method có thể xuất hiện rộng vì được gọi nhiều lần do một vòng lặp hoặc fan-out sai.

**Thay nhiều biến cùng lúc.** Không thể quy kết cải thiện cho một thay đổi cụ thể.

**Bỏ qua tính đúng đắn.** Giảm latency bằng cách bỏ listener, bỏ ack hoặc giảm độ bền publication có thể làm mất event hoặc sai nghiệp vụ.

**Giữ recording quá lâu.** File lớn, overhead và dữ liệu nhạy cảm có thể tạo rủi ro vận hành.

## 18. Quy trình profiling thực tế

Có thể áp dụng quy trình lặp sau:

1. **Xác định triệu chứng:** throughput, latency, CPU, heap, GC, lock hay backlog.
2. **Chọn một giả thuyết:** nêu rõ thành phần và loại tài nguyên nghi ngờ.
3. **Chọn workload:** event type, payload, listener, concurrency và tải đại diện.
4. **Ghi baseline:** metrics, trace, JVM configuration và môi trường.
5. **Warm-up:** để JVM và dependency đạt trạng thái ổn định.
6. **Thu profile:** dùng JFR hoặc profiler phù hợp, giới hạn thời gian và mức chi tiết.
7. **Phân tích:** tìm hot method, allocation, blocking, contention hoặc I/O wait.
8. **Đối chiếu:** liên kết profile với listener, event type và trace.
9. **Đưa ra một thay đổi nhỏ:** sửa bottleneck có bằng chứng.
10. **Đo lại:** chạy cùng workload và so sánh cùng bộ chỉ số.
11. **Kiểm tra tính đúng đắn:** xác minh publication không mất, listener không bị bỏ qua, retry/idempotency vẫn đúng.
12. **Ghi kết quả:** lưu recording đã được làm sạch, cấu hình, giả thuyết, phát hiện và kết quả trước/sau.

Nếu profile không xác nhận giả thuyết, quay lại metrics/tracing để chọn hướng khác. Không tối ưu theo cảm giác.

## 19. Bảo mật và an toàn khi thu profile

Recording và heap dump có thể chứa thông tin nhạy cảm: chuỗi kết nối, token, payload event, dữ liệu cá nhân hoặc nội dung request. Dù profiler không cố ý thu payload, một số event hoặc heap snapshot có thể giữ tham chiếu đến object chứa dữ liệu đó.

Áp dụng các nguyên tắc:

- Chỉ thu profile trong thời gian và phạm vi cần thiết.
- Dùng workload giả lập hoặc dữ liệu đã làm sạch khi có thể.
- Bảo vệ file JFR, heap dump và flame graph như dữ liệu nội bộ.
- Giới hạn quyền truy cập và thời gian lưu.
- Không đính kèm payload hoặc secret vào báo cáo profiling.
- Xóa recording tạm sau khi phân tích theo chính sách.
- Đánh giá overhead trước khi bật profiler ở production.
- Không dùng công cụ attach hoặc agent chưa được phê duyệt trên môi trường nhạy cảm.

## 20. Checklist profiling cho application events

- [ ] Đã xác định triệu chứng và giả thuyết có thể kiểm chứng.
- [ ] Đã có baseline metrics và trace.
- [ ] Workload có event mix, payload và fan-out đại diện.
- [ ] JVM đã warm-up trước khi đo.
- [ ] Chọn đúng CPU, allocation, lock hoặc wall-clock profiling.
- [ ] Recording có thời lượng và mức chi tiết giới hạn.
- [ ] Đã kiểm tra hot methods và call stacks.
- [ ] Đã phân tích allocation, GC và retained object khi cần.
- [ ] Đã kiểm tra thread state, lock, executor và I/O wait.
- [ ] Đã đo riêng publisher, registry, listener và adapter.
- [ ] Đã phân biệt publication backlog với broker/consumer lag.
- [ ] Có event/correlation metadata để nối profile với trace.
- [ ] Đã so sánh trước/sau trên cùng workload.
- [ ] Đã xác minh retry, idempotency và publication correctness sau tối ưu.
- [ ] Recording và báo cáo được bảo vệ khỏi lộ dữ liệu nhạy cảm.

## 21. Nguyên tắc đo đạc bằng profiling

Profiling giúp tìm chi phí thực sự bên trong JVM: CPU hot path, allocation, GC, lock contention và thời gian chờ I/O. Với Spring Modulith application events, hãy đo riêng publisher, Event Publication Registry, executor, listener và adapter externalization; dùng metrics và tracing để xác định chặng chậm, rồi dùng JFR hoặc profiler phù hợp để tìm nguyên nhân bên trong chặng đó.

Luôn đo trên workload đại diện, có warm-up, baseline và so sánh trước/sau. Chỉ tối ưu khi có bằng chứng và xác minh lại tính đúng đắn của publication, retry và listener. Cách làm này giúp cải thiện hiệu năng mà vẫn giữ được độ tin cậy của giao tiếp bất đồng bộ giữa các module.
