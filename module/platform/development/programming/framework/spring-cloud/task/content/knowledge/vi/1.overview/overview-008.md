# Giới hạn chức năng và tiêu chí lựa chọn giải pháp

## 1. Đặt đúng vai trò của Spring Cloud Task

**Spring Cloud Task** phù hợp để xây dựng ứng dụng Spring Boot **chạy trong một khoảng thời gian hữu hạn**: khởi động, nhận tham số, xử lý một công việc, ghi nhận kết quả rồi kết thúc tiến trình. Khác với dịch vụ HTTP hay consumer chạy liên tục, một lần chạy task có điểm bắt đầu và điểm kết thúc rõ ràng.

Trong hệ sinh thái Spring, giá trị nổi bật của Spring Cloud Task là **theo dõi vòng đời thực thi**. Khi được cấu hình thích hợp, thành phần **TaskRepository** lưu metadata của mỗi lần chạy trong cơ sở dữ liệu quan hệ, giúp trả lời các câu hỏi:

- Tác vụ nào đã chạy, bắt đầu lúc nào, kết thúc lúc nào?
- Lần thực thi nào thành công, thất bại hoặc chưa ghi nhận được thời điểm kết thúc?
- Lần chạy có mã định danh nào, mang tham số gì và trả về mã thoát nào?
- Hệ thống bên ngoài có thể tra cứu lịch sử để phục vụ vận hành hay kiểm toán không?

Ví dụ trong hệ thống thương mại điện tử, mỗi đêm cần đối soát dữ liệu đơn hàng đã thanh toán. Một tiến trình ngắn hạn nhận ngày đối soát, thực hiện xử lý, ghi kết quả nghiệp vụ và thoát. Spring Cloud Task có thể lưu lịch sử các lần chạy của tiến trình này. Tuy nhiên, **lịch chạy**, **quy tắc chống xử lý trùng**, **khả năng tiếp tục từ bản ghi đang dở** và **điều phối nhiều bước** là những nhu cầu cần đánh giá riêng.

~~~mermaid
flowchart LR
    A["Nguồn kích hoạt: CronJob, API, công cụ vận hành"] --> B["Ứng dụng Spring Boot + Spring Cloud Task"]
    B --> C["Xử lý nghiệp vụ hữu hạn"]
    B --> D["TaskRepository"]
    D --> E[("Cơ sở dữ liệu metadata")]
    C --> F["Kết quả nghiệp vụ / hệ thống đích"]
    B --> G["Kết thúc tiến trình, trả mã thoát"]
~~~

Điểm cần phân biệt: **TaskRepository ghi nhận lần thực thi của ứng dụng**, còn dữ liệu nghiệp vụ (đơn hàng đã đối soát, file đã xuất, giao dịch đã cập nhật...) vẫn phải được quản lý bởi hệ thống nghiệp vụ tương ứng. Một bản ghi thực thi có mã thoát bằng 0 không tự chứng minh rằng mọi tác động bên ngoài đã đạt yêu cầu.

## 2. Các giới hạn chức năng cần hiểu rõ

| Nhu cầu | Spring Cloud Task cung cấp | Giới hạn và thành phần bổ sung |
| --- | --- | --- |
| Theo dõi vòng đời tiến trình | Tạo và cập nhật bản ghi thực thi, thời điểm bắt đầu/kết thúc, mã thoát, thông tin lỗi | Không thay thế log nghiệp vụ, trace phân tán, metric hay cảnh báo |
| Kích hoạt theo lịch | Có thể được khởi chạy bởi hệ thống khác | Không phải bộ lập lịch độc lập; dùng Kubernetes CronJob, scheduler hoặc công cụ điều phối |
| Chạy theo yêu cầu | Ứng dụng có thể nhận tham số từ dòng lệnh hoặc môi trường | API, xác thực yêu cầu, hàng đợi và cơ chế tạo tiến trình phải được thiết kế bên ngoài |
| Xử lý dữ liệu số lượng lớn | Có thể chạy mã xử lý dữ liệu bất kỳ | Không tự có cơ chế chunk, checkpoint, skip, retry theo từng bản ghi; cân nhắc Spring Batch |
| Khởi động lại sau lỗi | Có metadata của lần chạy trước | Không tự khôi phục chính xác bước/bản ghi dang dở; cần logic nghiệp vụ hoặc Spring Batch |
| Tránh chạy trùng | Mỗi lần chạy có định danh thực thi riêng; có thể cấu hình giới hạn một số kiểu chạy đồng thời trong các phiên bản hỗ trợ | Không tự bảo đảm xử lý đúng một lần trên mọi hệ thống; vẫn cần khóa, ràng buộc dữ liệu và tính idempotent |
| Điều phối nhiều tác vụ | Mỗi ứng dụng task có thể là một đơn vị thực thi | Không tự biểu diễn đầy đủ DAG, phụ thuộc, phê duyệt và bù trừ; dùng orchestrator hoặc Spring Cloud Data Flow khi phù hợp |
| Xử lý liên tục, độ trễ thấp | Có thể làm việc khi chạy | Không phù hợp làm consumer hay dịch vụ sống lâu chỉ để tiếp nhận sự kiện liên tục |
| Quản trị dữ liệu metadata | Lưu thông tin thực thi qua TaskRepository | Cần thiết kế schema, quyền truy cập, lưu trữ, dọn dẹp và giám sát database |

### 2.1. Vòng đời hữu hạn là điều kiện quan trọng

Spring Cloud Task phát huy lợi thế khi công việc có thể xác định rõ **khi nào hoàn tất**. Ví dụ: tạo báo cáo ngày, đồng bộ một tập dữ liệu hữu hạn, nạp một file, chạy migration có kiểm soát, tính toán một kỳ đối soát.

Nếu ứng dụng mở web server, giữ thread nền hoặc liên tục chờ thông điệp, tiến trình có thể không thoát như dự kiến. Khi đó mô hình task ngắn hạn mất ý nghĩa. Với ứng dụng thuần tác vụ, có thể đặt thuộc tính cấu hình:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: order-reconciliation
~~~

Ứng dụng vẫn phải bảo đảm các runner và tài nguyên nền kết thúc đúng cách. Thuộc tính không chạy web server **không tự đóng mọi thread hay tác vụ bất đồng bộ**.

### 2.2. Có lịch sử thực thi không đồng nghĩa có cơ chế lên lịch

Việc lưu metadata của một lần chạy là trách nhiệm khác với quyết định **bao giờ** chạy. Có thể sử dụng:

- **Kubernetes CronJob** khi mỗi lần chạy được đóng gói thành container, cần lịch chạy, giới hạn tài nguyên và chính sách tạo pod.
- **Quartz hoặc bộ lập lịch hiện hữu** khi cần quản lý trigger và lịch thực thi trong một ứng dụng/hệ thống.
- **API hoặc hệ thống điều phối** khi người vận hành hay một quy trình khác quyết định thời điểm khởi chạy.
- **Spring Cloud Data Flow** khi hệ thống đã dùng nền tảng này để triển khai, khởi chạy và theo dõi các task trên hạ tầng hỗ trợ.

Với lịch chạy định kỳ, phải phân định ai là **nguồn quyết định lịch** và ai là **nguồn lưu trạng thái thực thi**. Không nên dựa vào việc có bản ghi TaskRepository rồi kết luận rằng tác vụ đã được lên lịch, tự thử lại hoặc tự xử lý lần chạy bị bỏ lỡ.

### 2.3. Metadata không thay thế cơ chế chịu lỗi nghiệp vụ

Một tiến trình có thể bị dừng bằng tín hiệu cưỡng bức, hết bộ nhớ, mất kết nối database hoặc bị nền tảng hạ tầng hủy. Khi ứng dụng không kịp thực hiện xử lý kết thúc, bản ghi thực thi **có thể thiếu thời điểm kết thúc hoặc chưa phản ánh trạng thái cuối cùng**. Vì vậy cần bổ sung giám sát tiến trình trên hạ tầng, timeout, cảnh báo lần chạy quá lâu và quy trình đối chiếu những lần thực thi bất thường.

Ngoài ra, việc ghi metadata và ghi dữ liệu nghiệp vụ không mặc nhiên nằm trong **một giao dịch nguyên tử**. Ví dụ, file báo cáo đã được gửi lên object storage nhưng tiến trình chết trước khi cập nhật trạng thái. Nếu chạy lại mà không có quy tắc kiểm tra, hệ thống có thể tạo file hoặc gửi thông báo hai lần.

Thiết kế an toàn thường cần:

1. **Khóa nghiệp vụ xác định** cho một đơn vị công việc, chẳng hạn mã khách hàng và ngày đối soát.
2. **Tính idempotent**: lặp lại cùng yêu cầu không gây thêm tác động ngoài ý muốn.
3. **Ràng buộc duy nhất hoặc trạng thái nghiệp vụ** trong kho dữ liệu sở hữu kết quả.
4. **Chính sách retry rõ ràng** về số lần, khoảng cách và loại lỗi được phép thử lại.
5. **Đối soát độc lập** khi trạng thái của tiến trình và trạng thái của kết quả nghiệp vụ khác nhau.

Chức năng giới hạn một số kiểu thực thi đồng thời, nếu được sử dụng trong phiên bản Spring Cloud Task tương ứng, chỉ giải quyết một phần bài toán chồng lấn. Nó không thay thế tính idempotent hay cơ chế chống ghi trùng ở nơi lưu kết quả.

### 2.4. Chia lô, checkpoint và restart thuộc phạm vi khác

Nếu công việc xử lý hàng triệu bản ghi, cần chia thành chunk, ghi lại điểm đã xử lý, retry/skip có điều kiện và tiếp tục từ lần dừng trước, **Spring Batch** là lựa chọn chuyên biệt. Khi kết hợp với Spring Cloud Task:

- **Spring Cloud Task / TaskRepository** theo dõi một lần chạy của **ứng dụng**.
- **Spring Batch / JobRepository** theo dõi **job, step và trạng thái xử lý theo lô**.
- Nếu bật phần tích hợp thích hợp, có thể liên kết bản ghi thực thi task và job để truy vết.

Hai repository giải quyết hai tầng trạng thái khác nhau. Không nên xây lại cơ chế checkpoint bằng cách tự thêm thông tin vào metadata của TaskRepository.

## 3. Tiêu chí quyết định có nên dùng Spring Cloud Task

Trước khi chọn framework, cần mô tả **đơn vị công việc**, **cách khởi chạy**, **điều kiện thành công** và **cách xử lý khi thất bại**. Bảng dưới đây hỗ trợ thẩm định kiến trúc:

| Tiêu chí | Dấu hiệu phù hợp với Spring Cloud Task | Câu hỏi phải trả lời trước khi triển khai |
| --- | --- | --- |
| Vòng đời | Mỗi lần chạy có đầu vào và điều kiện kết thúc rõ ràng | Tiến trình có chắc chắn thoát sau khi hoàn tất? |
| Truy vết | Cần lưu lịch sử thực thi ở database để kiểm tra lại | Cần giữ metadata bao lâu, ai được xem? |
| Tần suất và độ trễ | Công việc chạy định kỳ hoặc theo yêu cầu, chấp nhận chi phí khởi động ứng dụng | Tần suất có quá cao hoặc SLA có quá ngắn so với thời gian khởi động? |
| Độ phức tạp xử lý | Công việc hữu hạn, ít bước hoặc có thể giao cho thư viện chuyên biệt | Có cần chunk, checkpoint, restart từng bước? |
| Nguồn kích hoạt | Có scheduler, API, orchestrator hoặc thao tác vận hành phù hợp | Ai chịu trách nhiệm timeout, retry, lịch bị bỏ lỡ và giới hạn chạy đồng thời? |
| Trạng thái dữ liệu | Có khóa nghiệp vụ, khả năng chạy lại an toàn | Nếu tiến trình chết sau khi đã ghi một phần kết quả, lần sau xử lý ra sao? |
| Hạ tầng | Có database quan hệ và quy trình quản trị schema đáng tin cậy | TaskRepository có sẵn sàng khi nhiều tiến trình cùng khởi động? |
| Vận hành | Có log, metric, cảnh báo và công cụ tra cứu thực thi | Làm sao phát hiện task treo, chạy trùng, hoặc không được khởi chạy? |

**Quy tắc lựa chọn:** dùng Spring Cloud Task khi cần mô hình ứng dụng ngắn hạn **và** lợi ích của lịch sử thực thi được lưu bền vững. Nếu chỉ chạy một script rất đơn giản mà không cần lịch sử này, một chương trình CLI, container job hoặc công cụ có sẵn có thể đủ. Nếu tính phức tạp nằm ở xử lý theo lô, điều phối hay sự kiện liên tục thì chọn thêm thành phần chuyên trách.

~~~mermaid
flowchart TD
    A{"Công việc có điểm kết thúc rõ ràng?"}
    A -->|Không| B["Dịch vụ liên tục / consumer / hệ thống xử lý sự kiện"]
    A -->|Có| C{"Cần checkpoint, chunk, restart theo bước?"}
    C -->|Có| D["Spring Batch"]
    C -->|Không| E{"Cần lịch sử thực thi bền vững theo từng lần chạy?"}
    E -->|Không| F["CLI, script hoặc container job đơn giản"]
    E -->|Có| G["Spring Cloud Task"]
    D --> H{"Muốn chạy job như ứng dụng hữu hạn có metadata task?"}
    H -->|Có| I["Spring Batch + Spring Cloud Task"]
    H -->|Không| J["Spring Batch với hạ tầng chạy phù hợp"]
    G --> K["Bổ sung scheduler / orchestrator nếu cần"]
    I --> K
~~~

Sơ đồ này chỉ giúp tìm **thành phần xử lý chính**. Ví dụ dù chọn Spring Batch hay Spring Cloud Task, nếu muốn chạy vào 2 giờ sáng mỗi ngày thì vẫn cần một cơ chế kích hoạt theo lịch.

## 4. So sánh với các lựa chọn thường gặp

| Giải pháp | Điểm mạnh chính | Chọn khi nào |
| --- | --- | --- |
| **Spring Cloud Task** | Theo dõi vòng đời và metadata của ứng dụng Spring Boot chạy hữu hạn | Công việc ngắn hạn cần truy vết từng lần thực thi |
| **Spring Batch** | Tổ chức job/step, chunk, checkpoint, restart, skip/retry phục vụ xử lý theo lô | Khối lượng dữ liệu lớn hoặc cần khôi phục chi tiết |
| **Spring Cloud Task + Spring Batch** | Có cả lịch sử tiến trình và quản lý trạng thái xử lý theo lô | Job batch được đóng gói thành ứng dụng khởi chạy theo yêu cầu/lịch |
| **Kubernetes Job / CronJob** | Chạy tiến trình trong container; quản lý lịch, pod, tài nguyên và một số chính sách thử lại | Cần hạ tầng thực thi và lập lịch container; có thể kết hợp Spring Cloud Task |
| **Quartz / Spring Scheduling** | Tổ chức trigger hoặc lịch chạy trong hệ thống ứng dụng | Yêu cầu chính là lập lịch; có thể kích hoạt một task riêng |
| **Spring Cloud Data Flow / workflow orchestrator** | Triển khai, kích hoạt và điều phối nhiều tác vụ cùng quan hệ phụ thuộc | Quy trình gồm nhiều lần chạy/phụ thuộc, cần giao diện vận hành tập trung |
| **Message consumer / service dài hạn** | Nhận và xử lý sự kiện liên tục, thường tối ưu độ trễ và thông lượng | Sự kiện đến liên tục, không có điểm kết thúc tự nhiên cho ứng dụng |

Không có sự loại trừ tuyệt đối giữa các giải pháp: **Spring Cloud Task là một lớp theo dõi thực thi**, còn scheduler, runtime container, Batch và orchestrator có thể cùng tồn tại để đáp ứng các yêu cầu khác nhau.

## 5. Tình huống lựa chọn thực tế

### Tình huống A — Đối soát đơn hàng mỗi đêm

**Yêu cầu:** 2 giờ sáng hàng ngày đối soát giao dịch của ngày trước đó; mỗi lần chạy cần mã định danh, thời gian, kết quả và khả năng tìm nguyên nhân lỗi.

**Gợi ý:** Spring Cloud Task cho tiến trình đối soát; Kubernetes CronJob hoặc scheduler để khởi chạy; TaskRepository lưu lịch sử. Truyền ngày đối soát như tham số đầu vào; đặt ràng buộc duy nhất theo ngày/kỳ đối soát trong dữ liệu nghiệp vụ. Nếu chạy lại cùng ngày, logic phải nhận biết phần đã xử lý.

**Điểm đánh giá:** số bản ghi và khả năng xử lý lại. Nếu cần chunk và restart, bổ sung Spring Batch.

### Tình huống B — Nạp năm triệu dòng từ tệp

**Yêu cầu:** chia lô, tiếp tục sau lỗi, bỏ qua dòng sai theo chính sách và biết lô nào đã hoàn tất.

**Gợi ý:** Spring Batch là lõi xử lý. Có thể đóng gói thành ứng dụng Spring Cloud Task nếu cũng cần theo dõi từng lần khởi chạy tiến trình. TaskRepository **không đủ** để thay thế JobRepository.

### Tình huống C — Xử lý sự kiện đặt hàng trong vài chục mili giây

**Yêu cầu:** tiếp nhận thông điệp liên tục, độ trễ thấp và thông lượng cao.

**Gợi ý:** service/consumer lâu dài kết hợp broker phù hợp. Khởi động một Spring Boot task mới cho từng thông điệp thường gây chi phí khởi động và kết nối database không cần thiết.

### Tình huống D — Quy trình gồm nhập dữ liệu, kiểm tra và phát hành báo cáo

**Yêu cầu:** bước sau chỉ chạy khi bước trước thành công; có thể thử lại theo từng bước và giám sát toàn bộ quy trình.

**Gợi ý:** một hệ thống workflow hoặc Spring Cloud Data Flow (nếu phù hợp hạ tầng) làm nhiệm vụ điều phối; từng bước có thể triển khai dưới dạng Spring Cloud Task. Metadata của từng task vẫn cần liên kết với mã quy trình/ngày xử lý để tra cứu xuyên suốt.

### Tình huống E — Lệnh quản trị chạy một lần

**Yêu cầu:** cập nhật một cấu hình có phạm vi nhỏ, không có nhu cầu tra cứu lịch sử thực thi trong database.

**Gợi ý:** một CLI hoặc tác vụ vận hành đơn giản có thể đáp ứng. Không nên thêm TaskRepository và các bảng metadata nếu chúng không giải quyết yêu cầu thực tế.

## 6. Phác thảo ứng dụng để kiểm chứng tiêu chí lựa chọn

Giả sử đã thêm dependency Spring Cloud Task tương thích với phiên bản Spring Boot/Spring Cloud đang dùng và đã cấu hình DataSource cùng schema metadata. Ví dụ tối giản sau minh họa **đầu vào theo lần chạy và kết thúc hữu hạn**:

~~~java
@SpringBootApplication
@EnableTask
public class ReconciliationTaskApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(
            ReconciliationTaskApplication.class, args
        );
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner reconciliationRunner(ReconciliationService service) {
        return args -> {
            var values = args.getOptionValues("businessDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                    "Cần truyền --businessDate=yyyy-MM-dd"
                );
            }

            LocalDate businessDate = LocalDate.parse(values.get(0));
            service.reconcileOnce(businessDate);
        };
    }
}
~~~

Ví dụ giả định đã có bean **ReconciliationService** và phương thức **reconcileOnce** được triển khai với chính sách xử lý lại an toàn. Các import Java được lược bỏ để tập trung vào luồng xử lý.

Khởi chạy minh họa:

~~~bash
java -jar reconciliation-task.jar --businessDate=2026-11-23
~~~

Sau khi chạy, có thể tra cứu lịch sử ở bảng metadata (tên bảng/cột phụ thuộc schema Spring Cloud Task tương ứng):

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME,
       END_TIME, EXIT_CODE, EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'order-reconciliation'
ORDER BY START_TIME DESC;
~~~

Cần đọc đồng thời **trạng thái thực thi** và **kết quả nghiệp vụ**. Nếu bản ghi chưa có thời gian kết thúc, đó là dấu hiệu cần kiểm tra tiến trình thực tế, chứ không nên vội kết luận task vẫn đang chạy. Nếu kết quả nghiệp vụ đã tồn tại nhưng tiến trình báo lỗi, việc chạy lại phải theo quy tắc idempotent.

## 7. Checklist thiết kế và vận hành an toàn

Trước khi đưa ứng dụng vào môi trường production, rà soát các điểm sau:

1. **Đầu vào và kết quả:** tham số bắt buộc, định dạng, giá trị mặc định, mã thoát và định nghĩa “thành công” đã rõ ràng; không ghi dữ liệu nhạy cảm trực tiếp vào tên task, tham số hoặc log.
2. **DataSource và schema:** TaskRepository trỏ đúng database, tài khoản chỉ có quyền cần thiết, schema được quản lý bằng quy trình migration; không phụ thuộc vào cơ chế tự tạo bảng không kiểm soát trong production.
3. **Chạy lại an toàn:** có business key, ràng buộc dữ liệu hoặc cơ chế idempotent; retry do ai quản lý, retry lỗi nào và dừng sau bao nhiêu lần.
4. **Song song và chồng lấn:** xác định có cho chạy cùng task nhiều lần hay không; nếu không, kiểm soát ở scheduler/runtime và tầng dữ liệu nghiệp vụ.
5. **Timeout và hủy tác vụ:** giới hạn thời gian chạy; xử lý tín hiệu dừng khi có thể; có thủ tục kiểm tra metadata còn dang dở sau crash.
6. **Quan sát:** log có mã thực thi và mã nghiệp vụ để liên kết; metric về số lần thành công/thất bại, thời gian chạy, lần chạy trễ hoặc bị bỏ lỡ; cảnh báo theo SLA.
7. **Bảo mật:** không đưa mật khẩu, token hoặc dữ liệu khách hàng nhạy cảm vào tham số được lưu lại; phân quyền người kích hoạt và người xem lịch sử.
8. **Vòng đời metadata:** xác định thời gian lưu, chỉ mục tra cứu, chính sách dọn dữ liệu và chi phí database khi số lần chạy tăng lên.
9. **Thử nghiệm lỗi thực tế:** kiểm tra lỗi giữa chừng, mất kết nối database, chạy trùng, dừng cưỡng bức và khởi chạy lại với cùng tham số nghiệp vụ.

## 8. Kết luận lựa chọn

Chọn **Spring Cloud Task** khi một công việc có vòng đời hữu hạn, cần lịch sử thực thi bền vững và được triển khai như một ứng dụng Spring Boot độc lập. Chọn **Spring Batch** khi trọng tâm là xử lý dữ liệu theo lô với checkpoint và restart. Dùng **scheduler hoặc orchestrator** khi cần quyết định thời điểm chạy và điều phối nhiều công việc; dùng **service/consumer lâu dài** cho luồng sự kiện liên tục.

Một kiến trúc phù hợp thường phân chia rõ bốn trách nhiệm: **ai khởi chạy**, **ai thực hiện nghiệp vụ**, **ai lưu metadata thực thi**, và **ai bảo đảm không gây tác động trùng khi thử lại**. Phân chia được bốn trách nhiệm này sẽ giúp tận dụng Spring Cloud Task đúng phạm vi và tránh kỳ vọng framework tự giải quyết toàn bộ bài toán vận hành.
