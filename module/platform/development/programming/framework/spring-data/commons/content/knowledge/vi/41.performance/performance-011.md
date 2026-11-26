# Đánh giá hiệu năng bằng phép đo tái lập và dữ liệu đại diện

## 1. Một lần chạy nhanh chưa phải bằng chứng cải thiện

Trong chương **Hiệu năng** của **SPRING_DATA_COMMONS**, thay đổi repository, derived query, projection hoặc cách phân trang cần được đánh giá bằng phép đo có thể giải thích và lặp lại.

Một truy vấn có thể nhanh trên vài chục bản ghi nhưng chậm trên dữ liệu nhiều quan hệ. Một phiên bản có thể trông nhanh hơn vì cache đã nóng, fixture nhỏ hơn hoặc request không còn trả đủ dữ liệu. Vì vậy, trước khi kết luận “tối ưu thành công”, cần chứng minh hai điều:

1. Hành vi chức năng cần thiết vẫn được giữ.
2. Chênh lệch hiệu năng xuất hiện trong điều kiện đo được xác định rõ.

Phép đo tái lập không có nghĩa mọi lần chạy phải ra cùng một con số. Nó có nghĩa người khác có thể dựng lại dữ liệu, workload, cấu hình và cách tổng hợp để kiểm tra cùng giả thuyết trong một khoảng biến thiên hợp lý.

## 2. Đặt câu hỏi kiểm chứng cụ thể

Một câu hỏi quá rộng:

~~~text
Repository này có nhanh không?
~~~

Một câu hỏi có thể đo:

~~~text
Với cùng dữ liệu và workload, đổi Page<Entity> sang Page<Projection>
có giảm latency và allocation của API danh sách,
trong khi vẫn trả cùng nội dung, thứ tự và tổng số không?
~~~

Ở đây, projection chỉ lấy các field cần cho API, nhưng metadata tổng số vẫn được giữ. Không thể bỏ totalElements rồi coi hai phiên bản có cùng hợp đồng nếu client cần thông tin đó.

Có thể đặt các giả thuyết khác:

- Derived query có filter tại store giảm dữ liệu truyền so với lọc sau findAll.
- Keyset cải thiện việc tiếp nối ở vị trí sâu với sort và index phù hợp.
- Một converter mới làm tăng CPU khi materialize kết quả.
- Giảm window size làm giảm bộ nhớ nhưng tăng số lượt tương tác.
- Callback tùy biến làm phát sinh thêm truy vấn.

Mỗi giả thuyết cần có kết quả chức năng và metric quan sát tương ứng.

## 3. Xác định tầng cần đo

| Tầng | Câu hỏi phù hợp | Điều chưa được bao phủ |
| --- | --- | --- |
| Hàm Java thuần | Converter hoặc mapper tốn bao nhiêu CPU/allocation? | Mạng, store và transaction |
| Repository tích hợp | Query, mapping và driver có chi phí gì? | Toàn bộ serialization và request |
| Service/use case | Một chuỗi repository cùng transaction tốn bao nhiêu? | Chi phí ngoài ranh giới service |
| API end-to-end | Người gọi quan sát latency, lỗi và throughput thế nào? | Nguyên nhân bên trong nếu thiếu trace |
| Tác vụ batch/export | Hoàn tất bao nhiêu dữ liệu trong bao lâu, giữ bao nhiêu bộ nhớ? | Trải nghiệm request tương tác nếu workload khác |

Benchmark thuần Java không thay thế integration benchmark với database thật. Ngược lại, một phép đo API có nhiều thành phần không luôn chỉ ra chính xác mapper nào cần sửa.

Có thể phối hợp nhiều tầng: dùng end-to-end để xác nhận tác động, rồi trace và profiling để giải thích nguyên nhân.

### Đừng đo nhầm lúc tạo nguồn dữ liệu

Với Stream hoặc reactive publisher, cần đo đến khi dữ liệu thực sự được tiêu thụ trong phạm vi mong muốn. Chỉ đo thời gian tạo Stream hoặc Mono/Flux có thể bỏ qua phần truy cập store.

Với transaction do proxy quản lý, cần xác định phép đo có bao gồm commit hay không. Một timer bên trong thân phương thức service có thể dừng trước khi interceptor commit.

## 4. Viết đặc tả phép đo trước khi chạy

Một đặc tả tối thiểu cần trả lời:

| Thành phần | Nội dung cần xác định |
| --- | --- |
| Use case | Endpoint hoặc thao tác nghiệp vụ nào? |
| Kết quả bắt buộc | Field, thứ tự, tổng số, tính đầy đủ và mức nhất quán |
| Phiên bản so sánh | Baseline và phương án thay đổi cụ thể |
| Dữ liệu | Cách tạo, seed, kích thước, phân bố và quan hệ |
| Workload | Loại request, tham số, mức đồng thời hoặc tốc độ đến |
| Cache | Những tầng nào được giữ hoặc reset? |
| Ranh giới thời gian | Từ mốc nào đến mốc nào? |
| Metric | Latency, throughput, lỗi, truy vấn, byte, allocation |
| Warm-up | Cách chuẩn bị và tiêu chí kết thúc |
| Lặp lại | Số run, thứ tự chạy và cách reset |
| Cách báo cáo | Phân vị, từng run, sai lệch và giới hạn kết luận |

Đây là nội dung cần mô tả trong tài liệu kết quả; không bắt buộc phải xây một framework benchmark lớn.

Các ví dụ số liệu trong bài đều là minh họa, không phải phép đo đã thực hiện trên dự án.

## 5. Dữ liệu đại diện cần nhiều hơn số lượng bản ghi

Một triệu bản ghi có cấu trúc đồng nhất chưa chắc đại diện tốt hơn một tập nhỏ nhưng phản ánh đúng độ lệch và quan hệ.

### Quy mô và độ rộng

Cần xét cả:

- Số aggregate root.
- Kích thước các field văn bản, document hoặc payload.
- Tỷ lệ field rỗng, null và giá trị lớn.
- Số phần tử trong collection thuộc aggregate.
- Số đối tượng liên quan được tải.
- Dữ liệu cũ và dữ liệu mới.

Nếu production có ghi chú dài nhưng fixture chỉ dùng chuỗi ngắn, chi phí truyền và materialization có thể bị đánh giá thấp.

Không dùng byte của JSON làm kích thước heap của entity. Object graph, chuỗi và cấu trúc quản lý có chi phí riêng.

### Phân bố và độ chọn lọc

Giả sử mọi tenant trong fixture có đúng cùng số hóa đơn, mọi status xuất hiện đều nhau và mọi request đều vào trang đầu. Phép đo đó có thể bỏ qua:

- Tenant lớn chiếm phần lớn tải.
- Filter chỉ khớp vài phần tử trong một tập rất lớn.
- Filter khớp phần lớn dữ liệu.
- Trang sâu hoặc cursor ở vùng dữ liệu dày.
- Nhiều bản ghi có cùng giá trị sort.

Các trường hợp này có thể tạo kế hoạch và lượng công việc rất khác nhau.

### Tương quan giữa các thuộc tính

Dữ liệu thực tế thường có tương quan:

~~~text
Hóa đơn gần đây có tỷ lệ PENDING cao hơn.
Tenant lớn có nhiều quan hệ hơn.
Một số trạng thái có payload rộng hơn.
Một khoảng thời gian tập trung nhiều sự kiện.
~~~

Sinh độc lập mọi field theo phân bố đều có thể làm mất những đặc điểm ảnh hưởng đến query planner và mapping.

### Null và giá trị trùng

Null ảnh hưởng filter, sort và keyset. Giá trị sort trùng ảnh hưởng ranh giới phân trang hoặc scrolling.

Một fixture không có null, không có trùng và chỉ có quan hệ một-một có thể khiến phương án trông tốt nhưng bỏ qua những trường hợp khó của sản phẩm.

## 6. Thiết kế các mức dữ liệu và workload có chủ đích

Một ma trận minh họa:

| Kịch bản | Dữ liệu đáng chú ý | Mục đích |
| --- | --- | --- |
| Kiểm tra nhỏ | Ít bản ghi nhưng đủ nhánh dữ liệu | Xác nhận setup và tính đúng |
| Quy mô điển hình | Số lượng và độ rộng gần môi trường đích | Đánh giá use case phổ biến |
| Tenant nóng | Một tenant có nhiều bản ghi và nhiều request | Kiểm tra độ lệch |
| Filter chọn lọc thấp | Nhiều dữ liệu phù hợp | Đo payload, count và mapping |
| Filter chọn lọc cao | Ít kết quả trong tập lớn | Kiểm tra công việc tìm kiếm |
| Quan hệ nhiều phần tử | Fan-out cao | Phát hiện N+1 hoặc nhân hàng khi join |
| Vị trí sâu | Offset lớn hoặc cursor tiếp nối | Đánh giá đường đọc sâu |
| Dữ liệu biên | Null, sort trùng, payload lớn | Kiểm tra hành vi và chi phí ở biên |

Không cần chạy mọi tổ hợp cho mọi thay đổi. Chọn các kịch bản có khả năng ảnh hưởng đến giả thuyết, sau đó mở rộng khi kết quả cho thấy vấn đề chưa giải thích được.

### Workload phải phản ánh kiểu sử dụng

Cần xác định:

- Tỷ lệ đọc và ghi.
- Tỷ lệ các loại query.
- Kích thước trang/window.
- Phân bố tenant và tham số.
- Tỷ lệ cache hit nếu có thể kiểm soát.
- Thời gian nghỉ hoặc tốc độ gửi request.
- Tình huống cạnh tranh dữ liệu.

Nếu chỉ phát cùng một query với cùng tham số, phép đo có thể chủ yếu đánh giá trường hợp lặp lại thuận lợi cho cache, không phải workload hỗn hợp.

Một workload lấy trang đầu và workload export toàn bộ là hai bài toán khác nhau. Không dùng kết quả của cái này để kết luận cho cái kia.

## 7. Seed cố định giúp tái tạo, nhưng chưa đủ

Có thể dùng seed cố định để sinh dữ liệu và chuỗi request:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;

record SearchRequest(
        String tenantId,
        InvoiceStatus status,
        int pageNumber,
        int pageSize) {
}

static List<SearchRequest> createRequests(long seed, int count) {
    SplittableRandom random = new SplittableRandom(seed);
    List<SearchRequest> requests = new ArrayList<>(count);

    for (int i = 0; i < count; i++) {
        String tenant = random.nextInt(100) < 70
                ? "tenant-hot"
                : "tenant-" + random.nextInt(1, 101);

        InvoiceStatus status = random.nextInt(100) < 80
                ? InvoiceStatus.PAID
                : InvoiceStatus.PENDING;

        int page = random.nextInt(100) < 60
                ? 0
                : random.nextInt(1, 11);

        requests.add(new SearchRequest(tenant, status, page, 50));
    }

    return List.copyOf(requests);
}
~~~

Đây là ví dụ tạo workload có tenant nóng và thiên về trang đầu. Các tỷ lệ 70%, 80%, 60% chỉ là tham số minh họa, không đại diện mặc định cho ứng dụng thực tế.

Để tái tạo cần ghi lại cả:

- Seed.
- Thuật toán và phiên bản generator.
- Cấu hình phân bố.
- Mốc thời gian cố định.
- Cách cấp ID và tạo quan hệ.
- Quy tắc tạo payload.
- Kịch bản nạp dữ liệu và trạng thái sau khi nạp.

Nếu dữ liệu sinh theo thời điểm hiện tại, cùng seed vẫn có thể tạo kết quả query khác. Nên dùng một mốc thời gian cố định khi đó là điều kiện của phép đo.

### Đừng tạo payload quá thuận lợi

Lặp cùng một ký tự để tạo chuỗi lớn có thể cho tỷ lệ nén khác xa dữ liệu thực tế. Nếu có nén, cần mô phỏng đặc điểm nội dung phù hợp hoặc ghi rõ giới hạn của fixture.

Các page được tạo cũng phải phù hợp với dữ liệu. Nếu phần lớn request vô tình rơi vào trang rỗng, phép đo không còn phản ánh việc đọc 50 dòng như dự kiến.

## 8. Giữ môi trường so sánh nhất quán

Những yếu tố cần được ghi nhận hoặc kiểm soát:

| Nhóm | Ví dụ |
| --- | --- |
| Ứng dụng | Build/commit, phiên bản Spring Data, module store, cấu hình mapping |
| Runtime | JDK, GC, heap, CPU và giới hạn tài nguyên |
| Driver | Phiên bản, fetch/batch size, timeout |
| Store | Engine, phiên bản, topology, cấu hình liên quan |
| Schema | Migration, index, constraint và thống kê planner |
| Kết nối | Pool size, giới hạn kết nối, khoảng cách mạng |
| Tải nền | Tác vụ khác, backup, compaction, job định kỳ |
| Quan sát | Mức log, trace sampling, profiler |

Abstraction Commons không loại bỏ khác biệt giữa các engine hoặc module. Một kết quả trên store thay thế không tự chứng minh hành vi tương đương ở môi trường đích.

Nếu thay đổi index chính là phương án cần đánh giá, index được phép khác giữa A và B. Khi đó phải mô tả nó là biến của thử nghiệm, thay vì gọi hai môi trường là hoàn toàn giống nhau.

### Không để cấu hình test che khác biệt

Một test JPA bao toàn bộ phép đo trong cùng transaction và persistence context có thể tái sử dụng entity theo cách request thực tế không làm.

Tương tự, một test slice có thể dùng datasource khác dự kiến hoặc chỉ nạp một phần cấu hình converter/callback.

Cần xác định đối tượng thực sự được đo: repository bean thật, store thật, custom implementation nào, và cấu hình nào đang có hiệu lực. Một mock trả danh sách cố định không đo hiệu năng truy cập dữ liệu.

## 9. Cache và warm-up phải được mô tả theo từng tầng

“Warm” và “cold” không phải hai trạng thái đơn giản cho toàn hệ thống.

Có thể có:

- JIT và class loading của JVM.
- Cache ứng dụng.
- Persistence context.
- Cache cấp khác của provider.
- Connection pool.
- Bộ đệm của driver.
- Buffer/page cache của store và hệ điều hành.

Xóa một cache ứng dụng không đồng nghĩa database đang cold. Khởi động lại ứng dụng không đồng nghĩa store mất dữ liệu trong bộ nhớ.

### Cách tổ chức

1. Xác định trạng thái cần đánh giá theo use case.
2. Chuẩn bị hoặc reset những tầng có thể kiểm soát.
3. Ghi lại những tầng không kiểm soát được.
4. Warm-up theo một kế hoạch được xác định trước.
5. Chỉ đưa các mẫu thuộc giai đoạn đo chính thức vào thống kê tương ứng.

Warm-up có thể cần để JVM, pool và workload đi đến trạng thái ổn định. Không chọn điểm kết thúc warm-up sau khi nhìn thấy con số thuận lợi cho một phương án.

Nếu cold start là yêu cầu sản phẩm, đo nó thành kịch bản riêng. Không loại bỏ cold start khỏi mọi kết luận chỉ vì nó tạo latency cao.

## 10. Đo đủ phần công việc cần thiết

Một helper đồng bộ đơn giản có thể diễn đạt ranh giới:

~~~java
import java.util.concurrent.Callable;

record ReadOutcome(long rows, long fingerprint) {
}

record TimedSample(
        long elapsedNanos,
        ReadOutcome outcome) {
}

static TimedSample measure(
        Callable<ReadOutcome> operation) throws Exception {

    long started = System.nanoTime();
    ReadOutcome outcome = operation.call();
    long elapsed = System.nanoTime() - started;

    return new TimedSample(elapsed, outcome);
}
~~~

System.nanoTime dùng để đo khoảng thời gian trong cùng tiến trình, thay vì dùng đồng hồ lịch có thể bị điều chỉnh. Timestamp theo giờ thực vẫn hữu ích để đối chiếu log, nhưng có vai trò khác.

Hợp đồng của operation phải rõ:

~~~text
Thực hiện entry point cần đo.
Tiêu thụ đủ kết quả.
Thực hiện mapping/serialization nếu chúng nằm trong ranh giới.
Trả số phần tử và một dấu kiểm tra cơ bản.
~~~

Fingerprint có thể giúp phát hiện bỏ qua tiêu thụ dữ liệu, nhưng không thay thế kiểm tra tính đúng: các fingerprint có thể trùng, và kết quả sai vẫn có thể có đúng số hàng.

Helper này chỉ minh họa ranh giới đo. Nó chưa phải một hệ thống benchmark đầy đủ: chưa xử lý warm-up, histogram, tải đồng thời, lỗi, timeout và chi phí của chính bộ đo.

### Dùng công cụ phù hợp

Với microbenchmark thuần Java, một harness chuyên dụng như JMH giúp kiểm soát nhiều vấn đề của JVM tốt hơn một vòng lặp tự viết. Tuy nhiên, microbenchmark không tự đại diện cho repository qua mạng.

Với API hoặc database integration, cần công cụ và harness cho phép kiểm soát workload, vòng đời tài nguyên và quan sát các thành phần liên quan. Không suy ra tính đại diện chỉ từ tên công cụ.

## 11. Đo latency, throughput và lỗi cùng nhau

### Latency

Nên quan sát phân bố thay vì chỉ trung bình:

- p50 thể hiện vùng trung tâm của các quan sát.
- p95 và p99 giúp thấy phần đuôi.
- Cực đại có thể hỗ trợ chẩn đoán nhưng nhạy với số mẫu và điều kiện chạy.

Cần ghi rõ tập mẫu: chỉ request thành công, mọi request đã kết thúc, hay một nhóm nghiệp vụ cụ thể.

Không bỏ request timeout khỏi báo cáo rồi kết luận phương án có tail latency tốt. Timeout là một phần kết quả và thường chỉ cho biết công việc chưa hoàn tất trong thời hạn đó.

### Throughput

Cần phân biệt:

~~~text
Tải được đưa vào.
Request được chấp nhận hoặc bắt đầu xử lý.
Request hoàn tất.
Request thành công.
Lỗi và timeout.
Công việc còn chờ.
~~~

Hai phương án cùng được cấp 100 request/giây không có nghĩa cả hai đều hoàn tất ổn định 100 request/giây.

Nếu hàng đợi tăng liên tục, phép đo chưa thể được diễn giải như một trạng thái ổn định chỉ bằng latency của các request đã hoàn tất.

### Mô hình phát tải

Với một số client cố định liên tục chờ response rồi mới gửi tiếp, hệ thống chậm có thể tự làm giảm tốc độ request mới. Kết quả đó hữu ích cho mô hình client ấy, nhưng không tương đương tốc độ đến cố định từ bên ngoài.

Khi đo theo lịch gửi định trước, cần quan sát cả việc bộ phát tải có gửi đúng lịch hay không và thời gian chờ trước khi request được thực sự gửi.

Không để giới hạn của máy phát tải bị hiểu nhầm thành giới hạn của ứng dụng.

## 12. Thu thập metric để giải thích nguyên nhân

| Metric | Giúp giải thích điều gì? |
| --- | --- |
| Query/command count | Count, N+1, callback hoặc truy vấn bổ sung |
| Lượt trao đổi mạng | Cursor batching và chi phí giao tiếp |
| Hàng/document/index entry được xét | Công việc thực tế của engine theo đơn vị metric |
| Số phần tử trả về/materialize | Dữ liệu được đưa lên tầng ứng dụng |
| Byte truyền và response size | Độ rộng dữ liệu và chi phí đầu ra |
| CPU và allocation | Mapping, conversion, DTO, serialization |
| GC | Áp lực cấp phát và tác động trong run |
| Pool wait và số connection đang dùng | Tranh chấp tài nguyên kết nối |
| Thời gian transaction | Phạm vi giữ tài nguyên và commit |
| Kế hoạch thực thi | Scan, index, sort, join và lựa chọn planner |

Không phải mọi công cụ cung cấp mọi metric. Ghi “chưa đo” tốt hơn suy diễn số byte từ kích thước JSON hoặc suy diễn số lượt mạng từ số lần gọi repository.

Một query trả một hàng count vẫn có thể xét rất nhiều dữ liệu. Một query trả ít root entity vẫn có thể tạo nhiều hàng join.

### Chi phí quan sát

Log SQL chi tiết, thu stack và profiler có thể ảnh hưởng kết quả. Có thể tách run chẩn đoán với run so sánh chính, hoặc giữ cùng cấu hình quan sát cho cả A và B.

Không so sánh A bật log dày đặc với B tắt log rồi quy toàn bộ chênh lệch cho query mới.

Trace thường có quan hệ cha-con. Không cộng duration của span cha và span con như những khoảng thời gian độc lập.

## 13. Lặp lại và đổi thứ tự để giảm thiên lệch

Chạy A một lần rồi B một lần có thể bị ảnh hưởng bởi cache, tải nền hoặc JVM.

Một kế hoạch có thể dùng:

~~~text
Chuẩn bị → Warm-up → Đo A
Chuẩn bị → Warm-up → Đo B
Lặp lại với thứ tự B/A hoặc một thứ tự được cân bằng.
~~~

ABBA hoặc thứ tự ngẫu nhiên có seed là các cách tổ chức có thể cân nhắc. Số run cần phù hợp độ biến thiên và mức quan trọng của quyết định; không có một con số nhỏ bảo đảm mọi kết luận.

Nếu phép đo có ghi dữ liệu, cần reset hoặc dùng dataset tương đương để phương án sau không nhận trạng thái khác.

Có thể cần nhiều tiến trình ứng dụng độc lập khi muốn đánh giá ảnh hưởng warm-up và runtime. Những điều kiện đó phải được ghi lại.

### Không xóa ngoại lệ chỉ vì làm số liệu xấu

GC pause, tranh chấp pool hoặc store compaction có thể là một phần hành vi cần biết. Chỉ loại một run khi có tiêu chí hợp lý, chẳng hạn harness bị lỗi hoặc cấu hình không đúng.

Giữ lý do loại run và trình bày nó. Không loại các quan sát hợp lệ chỉ để giảm p95.

## 14. Tổng hợp thống kê đúng ý nghĩa

Không lấy trung bình các p95 của từng run rồi gọi đó là p95 của tất cả request.

Hai cách báo cáo hợp lệ nhưng khác nhau:

- Giữ từng run và tóm tắt biến thiên giữa các run.
- Gộp các mẫu hoặc histogram tương thích theo một quy tắc rõ ràng rồi tính phân vị của tập gộp.

Nếu dùng “trung vị của p95 từng run”, hãy gọi đúng tên đó. Nó không phải p95 gộp.

Với ít mẫu, p99 có thể không ổn định. Cần xem số mẫu, thời lượng đo và phân bố workload trước khi diễn giải phần đuôi.

### Ví dụ minh họa

| Run | p95 A | p95 B |
| --- | --- | --- |
| 1 | 245 ms | 180 ms |
| 2 | 260 ms | 185 ms |
| 3 | 250 ms | 178 ms |

Trung vị của p95 từng run là 250 ms cho A và 180 ms cho B. Theo chỉ tiêu đó, mức giảm là:

~~~text
(250 - 180) / 250 × 100% = 28%
~~~

Kết luận đúng phạm vi là chỉ tiêu này giảm 28% trong ba run minh họa và điều kiện đã nêu. Không suy ra throughput tăng 28%, không suy ra mọi request nhanh hơn 28% và không coi đây là số liệu của dự án.

Nếu chênh lệch nhỏ hơn biến thiên giữa các run, cần thêm bằng chứng trước khi quy nó cho thay đổi.

## 15. Giữ kiểm tra tính đúng trong quy trình đánh giá

Một phương án có thể nhanh hơn vì:

- Bỏ điều kiện filter.
- Lấy thiếu dữ liệu.
- Đổi thứ tự.
- Bỏ count cần thiết.
- Bỏ callback hoặc auditing bắt buộc.
- Không chờ ghi/commit hoặc không tiêu thụ publisher.
- Chỉ xử lý window đầu rồi dừng.

Do đó, trước khi tin vào metric, cần kiểm tra kết quả với oracle độc lập phù hợp.

Với API danh sách, có thể kiểm tra ID, field cần trả, thứ tự và metadata. Với export, kiểm tra tính đầy đủ, không lặp ngoài chính sách và điều kiện kết thúc.

Nếu dữ liệu thay đổi đồng thời, phải định nghĩa mức nhất quán kỳ vọng. Không yêu cầu một phép duyệt dữ liệu đang thay đổi có hành vi snapshot nếu hệ thống chưa thiết kế điều đó.

Không xây oracle bằng chính query đang được tối ưu rồi xem sự trùng khớp là bằng chứng đầy đủ cho cả hai.

## 16. Mẫu báo cáo giúp người khác tái lập

Một báo cáo ngắn nhưng đủ dùng có thể gồm:

| Phần | Nội dung |
| --- | --- |
| Giả thuyết | Thay đổi nào và chi phí nào dự kiến giảm? |
| Hợp đồng | Hành vi cần giữ nguyên |
| Phiên bản | Baseline, candidate và khác biệt liên quan |
| Dữ liệu | Generator, seed, quy mô, phân bố, quan hệ |
| Workload | Request mix, tham số, tốc độ đến hoặc concurrency |
| Môi trường | Runtime, driver, store, schema/index và tài nguyên |
| Cache/warm-up | Tầng được kiểm soát và giai đoạn bị loại khỏi đo chính |
| Kết quả | Từng run, latency, throughput, lỗi và metric giải thích |
| Kiểm chứng | Bằng chứng về kết quả chức năng |
| Giới hạn | Điều chưa đo và phạm vi áp dụng |
| Quyết định | Chấp nhận, bác bỏ hoặc cần thêm bằng chứng |

Một kết luận hữu ích nên nối được metric với nguyên nhân:

~~~text
Projection giảm byte và allocation trong workload đọc danh sách.
Latency giảm khi cùng giữ nội dung, thứ tự và tổng số.
Chưa đánh giá tác vụ export hoặc workload ghi.
~~~

Không chỉ ghi “nhanh hơn” mà thiếu điều kiện. Cũng không khẳng định nguyên nhân nếu mới có tương quan; cần trace, query hoặc profiling hỗ trợ giải thích.

## 17. Những lỗi cần tránh

| Lỗi | Hệ quả |
| --- | --- |
| Một lần chạy duy nhất | Không biết biến thiên |
| Fixture chỉ vài bản ghi | Không bộc lộ scan, quan hệ và bộ nhớ |
| Mọi field phân bố đều | Bỏ qua tenant nóng và tương quan |
| So sánh khác schema/index ngoài chủ đích | Không xác định được biến gây chênh lệch |
| A cold, B warm nhưng không ghi rõ | Thiên lệch do cache |
| Chỉ đo lúc tạo publisher | Bỏ qua công việc thực |
| Chỉ báo latency của request thành công | Che lỗi và timeout |
| Chỉ đo query count | Bỏ qua byte, số hàng và CPU |
| Trung bình hóa p95 rồi gọi là p95 gộp | Sai ý nghĩa thống kê |
| Candidate bỏ bớt yêu cầu | So sánh hai hành vi khác nhau |
| Bỏ các run xấu không có tiêu chí | Kết quả thiếu tin cậy |
| Mock repository rồi kết luận về store | Không có query/mapping thực để đánh giá |

## 18. Bài tập áp dụng

1. Chọn một use case đọc dữ liệu và viết một giả thuyết tối ưu cụ thể.
2. Xác định hợp đồng nội dung, thứ tự, metadata và mức nhất quán.
3. Thiết kế fixture có quy mô, độ rộng, độ lệch và quan hệ phù hợp.
4. Dùng seed cùng mốc thời gian cố định để tạo lại dữ liệu/workload.
5. Xác định tầng cache và warm-up cần kiểm soát.
6. Đo nhiều run với thứ tự cân bằng, giữ cả lỗi và timeout.
7. Thu metric đủ để giải thích chênh lệch, không chỉ một thời gian trung bình.
8. Viết kết luận nêu rõ phạm vi và những kịch bản chưa được đánh giá.

Một phép đo tốt phải giúp người khác kiểm tra lại kết luận và hiểu vì sao nó xuất hiện. Dữ liệu đại diện, workload rõ ràng và điều kiện tái lập là cơ sở để lựa chọn đúng abstraction cùng cách truy cập dữ liệu của từng store.
