# Kiểm tra tính duy nhất của Correlation ID trong Java Logging

## 1. Tính duy nhất nghĩa là gì?

Correlation ID là mã dùng để liên kết các log, sự kiện và lời gọi thuộc **cùng một luồng xử lý logic**. Khi kiểm tra tính duy nhất, cần phân biệt hai yêu cầu:

- **Khác luồng độc lập → khác Correlation ID.** Hai HTTP request độc lập, hai tác vụ nền độc lập hoặc hai giao dịch không liên quan không được vô tình dùng chung một ID.
- **Cùng luồng xử lý → giữ nguyên Correlation ID.** Tất cả log của một request khi đi qua controller, service, database, message consumer hoặc service khác cần giữ ID đã được gán ở điểm vào, kể cả khi có nhiều dòng log.

Ví dụ minh họa:

| Sự kiện | Correlation ID | Đánh giá |
| --- | --- | --- |
| Request A bắt đầu | cid-A | Khởi tạo ID cho A |
| A gọi Service B và ghi thêm log | cid-A | Đúng: cùng luồng dùng lại ID |
| Request C độc lập bắt đầu | cid-C | Đúng: luồng mới có ID mới |
| Request D độc lập bắt đầu | cid-A | Sai: vô tình trùng ID với A |

Vì thế **số dòng log có cùng ID không phải số lần va chạm**. Đếm duplicate trực tiếp trên mọi dòng log sẽ báo sai, bởi một request hợp lệ có thể ghi hàng trăm dòng cùng Correlation ID.

Trước khi kiểm tra, nhóm phải xác định rõ một **đơn vị cần duy nhất** là gì: mỗi lần xử lý HTTP độc lập, mỗi tác vụ, hay mỗi giao dịch logic. Với retry, có hệ thống cố ý giữ cùng ID để liên kết các lần thử của một giao dịch; có hệ thống cấp ID riêng cho từng attempt và dùng một transaction ID chung. Cả hai đều hợp lệ nếu được định nghĩa nhất quán. Không kết luận hai attempt có cùng ID là lỗi khi chúng thuộc cùng phạm vi đã chọn.

## 2. Sinh ID có xác suất trùng cực thấp

Với Java 17+, cách đơn giản và phù hợp cho Correlation ID tự sinh là **UUID phiên bản 4**:

~~~java
String correlationId = java.util.UUID.randomUUID().toString();
~~~

UUID v4 có 122 bit ngẫu nhiên trong cấu trúc 128 bit. Giả sử các giá trị được sinh độc lập và phân bố đều, với n ID, xác suất xuất hiện ít nhất một cặp trùng có thể xấp xỉ bằng công thức birthday bound:

~~~text
P(collision) ≈ n × (n - 1) / (2 × 2^122)
~~~

Chẳng hạn với khoảng một tỷ ID được sinh đúng cách, xác suất trùng theo mô hình này vào khoảng 9,4 × 10^-20. Đây là xác suất rất nhỏ, **không phải cam kết duy nhất tuyệt đối**. Kiểm thử một triệu hay một tỷ mẫu mà không thấy trùng cũng không phải chứng minh toán học rằng tương lai sẽ không trùng.

Các cách sinh ID dễ gây lỗi:

- Dùng riêng **System.currentTimeMillis()**: nhiều request có thể bắt đầu cùng mili giây; nhiều máy cũng có thể có thời gian giống nhau.
- Dùng một **bộ đếm cục bộ** mà không phân biệt instance hoặc lần khởi động lại: có thể lặp số ở các tiến trình khác.
- Dùng **thread ID**, user ID, session ID hoặc địa chỉ IP: những giá trị này được tái sử dụng, có thể chứa thông tin nhạy cảm và không biểu diễn đúng một luồng xử lý.
- Dùng **Random với không gian giá trị nhỏ** hoặc tự cắt ngắn UUID quá mức: tăng xác suất va chạm.
- Mỗi lần ghi log lại gọi UUID.randomUUID(): có thể rất ít trùng nhưng phá hỏng khả năng liên kết log cùng request.

Nếu Correlation ID đồng thời được dùng làm khóa nghiệp vụ cần tính duy nhất nghiêm ngặt, hãy dùng thêm ràng buộc **UNIQUE** trong kho dữ liệu hoặc cơ chế cấp phát có kiểm soát. Correlation ID trong logging trước hết là metadata quan sát hệ thống, không tự thay thế khóa nghiệp vụ.

## 3. Chương trình Java kiểm tra nhiều ID, kể cả sinh song song

Ví dụ dưới đây chạy độc lập trên Java 17+. Nó sinh 100.000 UUID v4 từ nhiều luồng qua parallel stream, dùng tập hợp đồng thời để đếm chính xác số ID khác nhau, đồng thời cố tình thêm một ID hai lần để xác nhận bộ phát hiện duplicate hoạt động.

Lưu mã thành **CorrelationIdUniquenessCheck.java**:

~~~java
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class CorrelationIdUniquenessCheck {
    public static void main(String[] args) {
        int samples = 100_000;
        Set<UUID> seen = ConcurrentHashMap.newKeySet();
        AtomicInteger duplicates = new AtomicInteger();

        IntStream.range(0, samples).parallel().forEach(i -> {
            UUID id = UUID.randomUUID();
            if (!seen.add(id)) {
                duplicates.incrementAndGet();
            }
        });

        System.out.printf("Generated: %d%n", samples);
        System.out.printf("Unique: %d%n", seen.size());
        System.out.printf("Duplicates: %d%n", duplicates.get());

        // Kiểm tra bộ phát hiện trùng bằng một ID cố định.
        Set<String> detector = ConcurrentHashMap.newKeySet();
        if (!detector.add("fixed-id") || detector.add("fixed-id")) {
            throw new AssertionError("Duplicate detection failed");
        }
        System.out.println("Detector check: OK");

        if (duplicates.get() != 0) {
            throw new IllegalStateException("Duplicate IDs detected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CorrelationIdUniquenessCheck.java
java CorrelationIdUniquenessCheck
~~~

Một kết quả thường gặp:

~~~text
Generated: 100000
Unique: 100000
Duplicates: 0
Detector check: OK
~~~

Trong ví dụ, **Generated** là tổng lần cấp phát, **Unique** là số UUID khác nhau và **Duplicates** là số lần ID đã có trong tập. Ba dòng số liệu phụ thuộc dữ liệu ngẫu nhiên; kết quả không trùng ở trên là kỳ vọng thực tế, không phải stdout được bảo đảm tuyệt đối. Dòng **Detector check: OK** kiểm thử nhánh phát hiện trùng bằng dữ liệu cố định.

Tại sao chọn ConcurrentHashMap.newKeySet() và AtomicInteger? Vì thao tác add và tăng bộ đếm xảy ra trên nhiều luồng. Dùng HashSet thông thường không có đồng bộ hóa trong phép thử song song có thể gây race condition và làm phép đo sai. Bài thử chỉ xác minh generator trong một tiến trình và một lượt chạy; nó chưa kiểm tra nhiều JVM, nhiều máy hoặc sự cố tại điểm chuyển tiếp giữa các service.

## 4. Kiểm tra đúng hành vi trong một request

Một hệ thống có thể sinh UUID gần như không trùng nhưng vẫn sử dụng Correlation ID sai. Cần kiểm tra **tính duy nhất giữa các luồng** cùng với **tính ổn định bên trong một luồng**:

1. Khi luồng xử lý mới bắt đầu tại ingress đáng tin cậy, cấp một Correlation ID mới nếu chưa có ID hợp lệ từ hệ thống upstream được tin cậy.
2. Gắn ID đó vào ngữ cảnh logging, chẳng hạn MDC của SLF4J, và ghi ID trong các log thuộc luồng.
3. Chuyển tiếp cùng ID tới lời gọi HTTP/message downstream theo giao ước của hệ thống; service nhận không tự thay bằng ID mới khi chỉ đang tiếp tục luồng hiện có.
4. Nếu tác vụ chuyển sang thread pool, CompletableFuture hoặc worker bất đồng bộ, chuyển ngữ cảnh một cách tường minh nếu cơ chế logging không tự hỗ trợ; MDC thường gắn với luồng hiện tại.
5. Xóa hoặc khôi phục giá trị MDC trong finally sau khi xử lý, tránh thread được tái sử dụng mang ID của request cũ.

Ví dụ rút gọn về vòng đời MDC (cần thư viện SLF4J và integration HTTP thực tế, nên **không phải chương trình Java độc lập**):

~~~java
String correlationId = createOrAcceptTrustedCorrelationId(request);
try {
    org.slf4j.MDC.put("correlationId", correlationId);
    // Ghi log, xử lý request và chuyển tiếp correlationId downstream.
    processRequest(request, correlationId);
} finally {
    org.slf4j.MDC.remove("correlationId");
}
~~~

Hàm createOrAcceptTrustedCorrelationId và processRequest là tên minh họa cho phần tích hợp của ứng dụng, không phải API có sẵn trong JDK hoặc SLF4J. Nếu nhận X-Correlation-ID từ bên ngoài, cần giới hạn độ dài, ký tự và nguồn tin cậy. Một client có thể cố tình gửi lại ID cũ; kiểm tra định dạng **không chứng minh tính duy nhất**. Khi yêu cầu bắt buộc mỗi request độc lập có ID riêng, nên sinh ID nội bộ tại ingress và lưu external request ID ở trường khác nếu cần tra cứu.

## 5. Kiểm tra trên log ở nhiều service

Giả sử request R1 đi từ Gateway → Order Service → Payment Service, rồi phát sự kiện cho worker. Tất cả điểm xử lý thuộc R1 phải giữ cùng Correlation ID. Request R2 độc lập phải có ID khác.

Nên kiểm tra ít nhất các trường hợp sau:

| Tình huống | Tiêu chí đạt |
| --- | --- |
| Hai request độc lập liên tiếp | Correlation ID khác nhau |
| Nhiều request đồng thời | Không phát hiện trùng ID giữa các root độc lập |
| Một request qua nhiều service | ID được giữ nguyên trên các bước của cùng luồng |
| Gửi message / chạy async | ID được truyền theo message hoặc context đã định nghĩa |
| Thread pool xử lý request mới | Không rò rỉ ID từ request trước |
| Khởi động lại ứng dụng hoặc mở rộng nhiều instance | Không tái sử dụng ID do bộ đếm cục bộ bị reset |
| Retry, redelivery hoặc duplicate message | Phân biệt đúng cùng giao dịch logic với luồng độc lập theo quy ước ID |

Đặc biệt, cùng một Correlation ID xuất hiện ở Gateway và Payment Service là bằng chứng về **lan truyền ngữ cảnh**, không tự động là collision. Ngược lại, hai root request độc lập cùng ID mới là dấu hiệu cần điều tra.

## 6. Phát hiện trùng trong môi trường production

Phép thử trong bộ nhớ chỉ bao quát một JVM. Để phát hiện các ID bị cấp lại ở nhiều instance, cần quan sát **sự kiện bắt đầu của luồng độc lập**, thay vì đếm tất cả dòng log.

Một phương án:

1. Ghi hoặc thu thập sự kiện ingress/root-start với các trường như event_time, correlation_id, root_event_id, service_instance và loại luồng. root_event_id là mã duy nhất cho bản ghi/sự kiện gốc, độc lập với correlation_id.
2. Chuẩn hóa ý nghĩa của retry/redelivery và lọc các bản ghi chỉ là bản sao do hệ thống thu thập log tạo ra.
3. Gom nhóm theo correlation_id trong khoảng thời gian cần giám sát. Nếu một ID gắn với nhiều **root độc lập** thì báo nghi vấn trùng.
4. Truy vết thời điểm cấp ID, instance, đường đi và nguồn ID (tự sinh hay nhận từ upstream). Chỉ kết luận lỗi khi các root thật sự phải có ID riêng.

Ví dụ truy vấn SQL mang tính minh họa, giả sử bảng ingress_root_events **chỉ chứa các root độc lập** sau khi đã loại bản ghi trùng do ingest và áp dụng quy ước retry:

~~~sql
SELECT correlation_id,
       COUNT(DISTINCT root_event_id) AS distinct_roots
FROM ingress_root_events
WHERE event_time >= :from_time
  AND event_time < :to_time
GROUP BY correlation_id
HAVING COUNT(DISTINCT root_event_id) > 1;
~~~

Đây là truy vấn gợi ý cho dữ liệu quan sát; tên bảng/cột và cú pháp tham số phụ thuộc kho lưu trữ thực tế. Nếu bảng còn chứa các attempt được phép dùng chung Correlation ID thì phải nhóm theo **logical root** trước, nếu không sẽ có false positive. Đừng dùng COUNT(*) trực tiếp trên bảng mọi dòng log để kết luận trùng.

Các chỉ số hữu ích gồm: số sự kiện root không có ID, số ID đầu vào bị từ chối do định dạng/nguồn, số nghi vấn trùng sau khi đã loại false positive và tỷ lệ giữ nguyên ID qua các chặng. Tránh đưa giá trị Correlation ID cụ thể thành label của metric vì số lượng nhãn sẽ tăng rất lớn. Nếu dùng một bộ phát hiện trùng có trạng thái theo thời gian, phải quy định thời hạn lưu và cách xử lý khi hết hạn; không giữ vô hạn mọi ID trong bộ nhớ.

## 7. Xử lý khi phát hiện trùng

Khi có cảnh báo, xác minh tuần tự:

- **Có phải cùng một luồng được ghi log nhiều lần?** Nếu đúng, ID lặp là hành vi mong muốn.
- **Có phải retry hoặc redelivery của cùng công việc?** Đối chiếu quy ước ID đã chọn.
- **Có phải log collector nhận trùng bản ghi?** Kiểm tra root_event_id và hệ thống ingest.
- **Có phải hai root độc lập?** Xác định điểm cấp ID, instance và thuật toán sinh; tìm lỗi dùng timestamp, bộ đếm reset, seed ngẫu nhiên yếu, biến dùng chung hoặc chấp nhận ID client không đáng tin cậy.
- **Có phải rò rỉ ngữ cảnh thread?** Kiểm tra việc đưa ID vào MDC và dọn dẹp trong finally.
- **Có thật sự là va chạm UUID v4?** Chỉ cân nhắc sau khi loại các lỗi cấp phát/lan truyền thường gặp; lưu bằng chứng đầy đủ, có kiểm soát dữ liệu nhạy cảm.

Nếu uniqueness là ràng buộc nghiệp vụ, từ chối hoặc cấp lại ID tại điểm phát hiện theo thiết kế và dựa trên ràng buộc duy nhất của kho dữ liệu. Với hệ thống logging, ưu tiên sửa nguyên nhân ở điểm sinh/tiếp nhận ID và bổ sung cảnh báo. Không âm thầm đổi ID giữa một luồng đang chạy vì sẽ làm đứt chuỗi truy vết.

## 8. Tiêu chí hoàn thành

Một triển khai được xem là kiểm soát tốt tính duy nhất khi:

- Mỗi **luồng độc lập** nhận ID mới theo đúng chính sách; cùng luồng giữ ID thống nhất.
- Generator dùng không gian ID đủ lớn, cơ chế ngẫu nhiên thích hợp và được thử nghiệm dưới tải song song.
- Kiểm thử xác nhận cả **phát hiện duplicate cố ý** lẫn việc phát hiện rò rỉ/sai truyền ID ở các ranh giới HTTP, async, thread pool và service.
- Hệ thống giám sát phân biệt **nhiều log cùng một luồng** với **nhiều luồng độc lập cùng ID**.
- Các trường hợp retry, ID do upstream gửi, thời hạn quan sát và cách xử lý nghi vấn trùng có quy ước rõ ràng.

Điểm mấu chốt: **tính duy nhất của Correlation ID là tính duy nhất giữa các luồng xử lý độc lập; việc lặp lại cùng ID trong nhiều log của một luồng là đúng và cần thiết để truy vết.**
