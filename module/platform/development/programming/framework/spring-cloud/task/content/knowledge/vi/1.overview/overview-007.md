# Trường hợp sử dụng: nhập dữ liệu, báo cáo và bảo trì

Spring Cloud Task phù hợp với những công việc **có điểm bắt đầu, điểm kết thúc rõ ràng**: đọc một tệp dữ liệu rồi nhập vào hệ thống, tạo báo cáo theo kỳ hoặc dọn dẹp dữ liệu hết hạn. Mỗi lần khởi chạy là một lần thực thi độc lập; ứng dụng hoàn tất công việc rồi kết thúc tiến trình. Spring Cloud Task ghi lại thông tin thực thi trong cơ sở dữ liệu thông qua **TaskRepository**, giúp trả lời các câu hỏi: tác vụ nào đã chạy, bắt đầu khi nào, đã kết thúc chưa, mã thoát là gì và nếu lỗi thì lỗi gì.

Bài này tập trung vào việc **thiết kế và vận hành ba nhóm tác vụ thực tế**, không chỉ cách khởi tạo một ứng dụng Spring Boot. Sau khi học, bạn có thể chọn cách chia tác vụ, xác định tham số đầu vào, tổ chức chạy lại an toàn, kết hợp Spring Batch khi cần và quan sát kết quả qua dữ liệu metadata.

## 1. Nhận diện đúng bài toán

Một HTTP server phục vụ yêu cầu liên tục; một Spring Cloud Task thường được khởi chạy để hoàn thành **một đơn vị công việc hữu hạn**. Nó có thể được kích hoạt thủ công, theo yêu cầu từ hệ thống khác hoặc theo lịch bởi công cụ bên ngoài. **Spring Cloud Task không tự cung cấp bộ lập lịch**; Cron, Kubernetes CronJob, bộ điều phối workflow hoặc dịch vụ gọi tác vụ chịu trách nhiệm kích hoạt tiến trình.

| Trường hợp | Đầu vào và đầu ra | Điều kiện hoàn thành | Rủi ro khi chạy lại |
| --- | --- | --- | --- |
| **Nhập dữ liệu** | Tệp CSV, đối tượng trên object storage, bản ghi từ đối tác → bảng nghiệp vụ | Toàn bộ bản ghi hợp lệ đã được tiếp nhận hoặc đã có kết quả xử lý lỗi rõ ràng | Ghi trùng, xử lý lại bản ghi đã nhập, phát sinh tác dụng phụ lặp |
| **Báo cáo** | Khoảng thời gian, đơn vị kinh doanh, loại báo cáo → bảng tổng hợp hoặc tệp xuất | Kết quả được tính, kiểm tra và lưu ở vị trí có thể truy cập | Tạo nhiều phiên bản không kiểm soát, gửi báo cáo lặp, dùng kỳ dữ liệu khác nhau |
| **Bảo trì** | Thời điểm chốt, chính sách lưu trữ, kích thước lô → dữ liệu đã được làm sạch | Không còn bản ghi cần xử lý trong phạm vi đã định hoặc đạt giới hạn công việc | Xóa quá phạm vi, khóa bảng lâu, tác động tới dữ liệu đang được sử dụng |

**Nguyên tắc thiết kế:** mỗi lượt chạy phải có *danh tính nghiệp vụ* như mã tệp nguồn, ngày báo cáo hoặc ngày chốt dữ liệu. **TaskExecution ID** giúp phân biệt các lần chạy về mặt kỹ thuật; nó không thay thế khóa nghiệp vụ dùng để chống trùng.

### Luồng thực thi tổng quát

~~~mermaid
flowchart LR
    A["Cron / API / thao tác vận hành"] --> B["Khởi chạy tiến trình Spring Boot"]
    B --> C["Spring Cloud Task"]
    C --> D["Logic nhập / báo cáo / bảo trì"]
    C --> E[("TaskRepository: metadata thực thi")]
    D --> F[("CSDL nghiệp vụ / object storage")]
    D --> G["Log, metric, kết quả nghiệp vụ"]
    C --> H["Kết thúc tiến trình / mã thoát"]
~~~

TaskRepository lưu **metadata tiến trình**; còn số lượng bản ghi nhập, đường dẫn tệp báo cáo hoặc danh sách bản ghi đã xóa nên được ghi ở bảng nghiệp vụ, log có cấu trúc hoặc hệ thống quan sát phù hợp. Không nên giả định bảng metadata của Spring Cloud Task là nơi lưu mọi kết quả chi tiết.

## 2. Nền tảng chung cho ba loại tác vụ

Ứng dụng mẫu dùng Spring Boot, Spring Cloud Task, JDBC và PostgreSQL. Khi xây dựng dự án thực tế, cần chọn bản Spring Boot và Spring Cloud Task **tương thích** theo BOM của hệ sinh thái đang sử dụng, đồng thời quản lý sơ đồ bảng TaskRepository bằng cơ chế khởi tạo hoặc migration phù hợp môi trường.

Ví dụ các dependency Maven quan trọng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Phần quản lý phiên bản của Spring Cloud được khai báo ở **dependencyManagement** bằng BOM tương thích; ví dụ trên chỉ minh họa các thành phần cần thiết.

Cấu hình điển hình:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: data-operations
~~~

Giá trị kết nối được cung cấp qua biến môi trường hoặc hệ thống quản lý bí mật, không đưa mật khẩu vào mã nguồn. Cơ sở dữ liệu metadata cần có **schema của Spring Cloud Task đúng với phiên bản thư viện và loại CSDL** trước khi chạy trên môi trường sản xuất. Khi metadata và dữ liệu nghiệp vụ ở hai nguồn khác nhau, phải cấu hình rõ DataSource nào dành cho TaskRepository.

Một ứng dụng có thể nhận loại thao tác qua tham số. Để dễ quan sát, ví dụ dưới đây dùng ba service nghiệp vụ: **ImportService**, **ReportService** và **MaintenanceService**. Các service này là phần triển khai ứng với ba tình huống ở những mục tiếp theo.

~~~java
@SpringBootApplication
@EnableTask
public class DataOperationsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DataOperationsApplication.class, args);
    }

    @Bean
    ApplicationRunner execute(
            ImportService imports,
            ReportService reports,
            MaintenanceService maintenance) {

        return args -> {
            String operation = required(args, "operation");

            switch (operation) {
                case "import" -> imports.importSource(
                        required(args, "source-id"),
                        required(args, "input"));

                case "report" -> {
                    String reportDate = optional(
                            args, "date",
                            LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))
                                    .minusDays(1)
                                    .toString());
                    reports.generate(LocalDate.parse(reportDate));
                }

                case "cleanup" -> {
                    String mode = optional(args, "mode", "preview");
                    if (!mode.equals("preview") && !mode.equals("execute")) {
                        throw new IllegalArgumentException(
                                "mode must be preview or execute");
                    }
                    maintenance.clean(
                            Instant.parse(required(args, "cutoff")),
                            mode.equals("execute"));
                }

                default -> throw new IllegalArgumentException(
                        "Unsupported operation: " + operation);
            }
        };
    }

    private static String required(ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected exactly one --" + name + "=value");
        }
        return values.get(0);
    }

    private static String optional(
            ApplicationArguments args, String name, String defaultValue) {
        if (!args.containsOption(name)) {
            return defaultValue;
        }
        return required(args, name);
    }
}
~~~

Các import Java và phần cài đặt service được lược bớt để làm rõ điểm vào của tác vụ. Dấu **--** truyền tham số cho ứng dụng; ví dụ:

~~~bash
java -jar data-operations.jar --operation=import --source-id=partner-A-2026-11-24 --input=/data/orders.csv
java -jar data-operations.jar --operation=report --date=2026-11-23
java -jar data-operations.jar --operation=cleanup --cutoff=2026-10-01T00:00:00Z --mode=preview
~~~

Trong môi trường lớn, có thể tách ba loại tác vụ thành **ba ứng dụng hoặc ba image** để triển khai, giới hạn quyền và tài nguyên độc lập. Việc gộp trong một ứng dụng ở đây chủ yếu nhằm minh họa cách điều hướng theo tham số.

Lỗi đầu vào phải dẫn tới thất bại rõ ràng; không bắt mọi exception rồi chỉ ghi log và tiếp tục như thể xử lý thành công. Bộ điều phối cần mã thoát của tiến trình, còn người vận hành cần log và metadata để chẩn đoán.

## 3. Tình huống A: nhập dữ liệu từ đối tác

### 3.1. Bài toán và quyết định

Mỗi tối, đối tác gửi tệp giao dịch. Tệp có thể được giao lại do timeout hoặc hệ thống phải chạy lại vì mất kết nối CSDL. Nếu chương trình chỉ lặp qua các dòng rồi thực hiện INSERT, lần chạy lại rất dễ sinh dữ liệu trùng.

Một quy trình nhập tin cậy cần tách ba loại trạng thái:

1. **Nguồn nhập:** mã định danh tệp, checksum, phiên bản, thời điểm tiếp nhận.
2. **Bản ghi nghiệp vụ:** khóa ngoài do đối tác cung cấp và kết quả chuẩn hóa/kiểm tra.
3. **Lần thực thi:** TaskExecution ID, thời gian bắt đầu/kết thúc, mã thoát và lỗi.

Ví dụ, đối tác gửi lại cùng tệp có **source-id** giống nhau. Nếu checksum không đổi, có thể bỏ qua toàn bộ nguồn đã hoàn tất hoặc tiếp tục những phần chưa xử lý. Nếu checksum khác, phải coi là xung đột hay phiên bản mới theo quy tắc đã định; không âm thầm ghi đè dữ liệu.

### 3.2. Luồng xử lý đề xuất

~~~mermaid
flowchart TD
    A["Nhận source-id và vị trí tệp"] --> B{"Đã hoàn tất nguồn này?"}
    B -- Có, checksum trùng --> C["Ghi nhận đã xử lý; kết thúc"]
    B -- Chưa --> D["Kiểm tra tệp, định dạng, checksum"]
    B -- Checksum khác --> X["Báo xung đột phiên bản"]
    D --> E["Đọc và kiểm tra bản ghi theo lô"]
    E --> F["Upsert bằng khóa nghiệp vụ"]
    F --> G{"Còn bản ghi?"}
    G -- Có --> E
    G -- Không --> H["Đối soát tổng số và đánh dấu hoàn tất"]
~~~

Ví dụ bảng dữ liệu đích dùng PostgreSQL:

~~~sql
CREATE TABLE imported_order (
    source_id    varchar(200) NOT NULL,
    external_id  varchar(200) NOT NULL,
    amount       numeric(18, 2) NOT NULL,
    PRIMARY KEY (source_id, external_id)
);

INSERT INTO imported_order (source_id, external_id, amount)
VALUES (:source_id, :external_id, :amount)
ON CONFLICT (source_id, external_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

Ràng buộc khóa duy nhất khiến lần chạy lại cùng dữ liệu không tạo thêm dòng. Tuy nhiên, **upsert chỉ là một phần của idempotency**: nếu mỗi dòng còn kích hoạt gửi email, trừ tiền hoặc gọi API đối tác, phải có cơ chế chống lặp riêng cho những tác dụng phụ đó. Nếu giao dịch nguồn có thể thay đổi, cần làm rõ nghiệp vụ cho phép cập nhật, từ chối hay tạo phiên bản.

Với tệp nhỏ, service có thể dùng parser CSV đúng chuẩn, kiểm tra từng dòng và gọi JDBC. Không nên tách CSV bằng dấu phẩy thủ công vì trường dữ liệu có thể chứa dấu phẩy, dấu nháy và xuống dòng. Với tệp lớn, **Spring Batch** phù hợp hơn nhờ đọc/ghi theo chunk, trạng thái từng step và khả năng khởi động lại có kiểm soát.

### 3.3. Xử lý lỗi và chạy lại

| Sự cố | Cách ứng xử |
| --- | --- |
| Tệp sai header hoặc thiếu cột bắt buộc | Dừng sớm, ghi lỗi xác thực nguồn; không đánh dấu nguồn thành công |
| Một số dòng không hợp lệ | Xác định chính sách reject toàn tệp hay lưu danh sách dòng lỗi; nêu rõ ngưỡng chấp nhận |
| Mất kết nối CSDL giữa chừng | Rollback giao dịch hiện tại; lần sau dựa vào khóa nghiệp vụ và checkpoint để xử lý tiếp |
| Nhận lại cùng tệp | So sánh source-id và checksum, bảo đảm kết quả không tăng số dòng |
| Hai phiên bản cùng source-id | Báo xung đột hoặc quản lý version tường minh, không tự chọn bản cuối |

**Điểm cần kiểm tra:** chạy cùng tệp hai lần phải cho cùng kết quả nghiệp vụ; số dòng hợp lệ, số dòng bị từ chối và tổng giá trị sau nhập phải đối soát được với nguồn. TaskRepository cho biết **lần chạy** thành công hay thất bại, còn bảng trạng thái nhập phải mô tả **nguồn dữ liệu** đã hoàn tất hay chưa.

## 4. Tình huống B: tạo báo cáo theo kỳ

### 4.1. Xác định kỳ dữ liệu trước khi tính toán

Giả sử hệ thống cần báo cáo doanh thu cho ngày kinh doanh trước đó, hiển thị theo giờ Việt Nam. Tham số **date** xác định ngày nghiệp vụ, còn logic báo cáo chuyển khoảng thời gian trong múi giờ **Asia/Ho_Chi_Minh** sang hai mốc UTC: **[from, to)**. Khoảng nửa mở giúp tránh tính trùng giao dịch ở thời điểm giao ngày.

Ví dụ truy vấn tổng hợp (cú pháp named parameters của lớp truy cập dữ liệu, không phải SQL chạy trực tiếp nguyên văn trong psql):

~~~sql
SELECT currency,
       COUNT(*) AS transaction_count,
       SUM(amount) AS total_amount
FROM payment
WHERE status = 'SETTLED'
  AND paid_at >= :from_utc
  AND paid_at <  :to_utc
GROUP BY currency;
~~~

Dữ liệu cần có quy ước riêng cho giao dịch đến muộn, hủy hoặc điều chỉnh sau ngày chốt. Nếu báo cáo được phép thay đổi, hãy dùng số phiên bản hoặc thời điểm chốt để người đọc biết đang xem kết quả nào.

### 4.2. Xuất kết quả an toàn

Một lần tạo báo cáo nên thực hiện theo thứ tự:

1. Xác định **report key** từ loại báo cáo, kỳ và phiên bản; kiểm tra có lần phát hành thành công chưa.
2. Chụp hoặc xác định mốc dữ liệu nhất quán, tính tổng hợp và đối soát số lượng.
3. Ghi tệp ở vị trí tạm; xác thực kích thước, checksum và nội dung cơ bản.
4. Chuyển tệp sang vị trí chính thức theo thao tác có tính nguyên tử trong phạm vi hệ lưu trữ hỗ trợ, rồi cập nhật trạng thái **READY** trong bảng kết quả.
5. Chỉ gửi thông báo qua cơ chế có khóa chống lặp (chẳng hạn outbox) sau khi kết quả đã sẵn sàng.

Ví dụ mô hình kết quả nghiệp vụ:

| Trường | Vai trò |
| --- | --- |
| report_type, business_date, version | Khóa định danh logic của báo cáo |
| source_watermark | Mốc dữ liệu đầu vào đã sử dụng |
| artifact_uri, checksum | Nơi lưu và tính toàn vẹn của tệp |
| status | PENDING, READY, FAILED theo luồng nghiệp vụ |
| generated_at | Thời điểm phát hành thành công |

Nếu tiến trình chết sau khi tải tệp lên nhưng trước khi cập nhật database, lần chạy kế tiếp kiểm tra **report key** và tệp đã tồn tại để hoàn tất, tránh nhân bản. Nếu bước gửi thông báo lỗi, không nên đánh dấu lại toàn bộ phép tính là thất bại rồi gửi các thông báo cũ nhiều lần.

**Phân biệt hai kết quả:** Spring Cloud Task trả lời “tiến trình tạo báo cáo đã kết thúc như thế nào?”, bảng báo cáo trả lời “phiên bản báo cáo nào hiện sẵn sàng để người dùng tải xuống?”.

## 5. Tình huống C: bảo trì và dọn dẹp dữ liệu

### 5.1. Đặt phạm vi trước khi xóa

Các tác vụ bảo trì thường gồm xóa phiên đăng nhập hết hạn, lưu trữ bản ghi cũ, tái tính toán chỉ mục nghiệp vụ hoặc thu hồi dữ liệu tạm. Chúng có thể ngắn nhưng thường tác động trực tiếp đến tính toàn vẹn và hiệu năng hệ thống.

Ví dụ chính sách: xóa các phiên đã hết hạn **trước cutoff**. Không lấy thời điểm hiện tại trong từng vòng lặp vì phạm vi sẽ dịch chuyển theo thời gian; hãy chốt cutoff ngay lúc bắt đầu và ghi lại trong log/kết quả nghiệp vụ.

Trước khi tác động dữ liệu, thực hiện **preview**: đếm số bản ghi thỏa điều kiện, lấy mẫu khóa, kiểm tra phụ thuộc và ước tính kích thước. Mode **execute** phải được chỉ định tường minh. Có thể kết hợp xác nhận từ hệ thống điều phối đối với tác vụ đặc biệt nhạy cảm.

### 5.2. Xóa theo lô có giới hạn

Một lệnh DELETE rất lớn có thể giữ khóa lâu và tạo đột biến I/O. Thực hiện theo lô nhỏ, mỗi lô có transaction riêng, đo thời gian rồi điều chỉnh kích thước lô theo tải thực tế. Ví dụ PostgreSQL:

~~~sql
WITH victims AS (
    SELECT id
    FROM user_session
    WHERE expires_at < :cutoff
    ORDER BY id
    LIMIT :chunk_size
)
DELETE FROM user_session s
USING victims v
WHERE s.id = v.id;
~~~

Lặp đến khi số dòng bị xóa bằng 0 hoặc đã đạt giới hạn thời gian/lượt xóa được định nghĩa. Cần index phù hợp với điều kiện lọc và thứ tự truy vấn; với bảng lớn, thử kế hoạch thực thi và lượng khóa trong môi trường kiểm thử tương đương.

Nếu nhiệm vụ phải tiếp tục qua nhiều lần chạy, lưu **checkpoint** hoặc xác định lại các bản ghi còn thỏa điều kiện. Phải thiết kế rõ dữ liệu nào có thể bị cập nhật song song, dữ liệu nào cần giữ vì ràng buộc pháp lý và khi nào cần archive thay cho xóa hẳn. Không tự động dọn các bảng metadata **TASK_EXECUTION** của Spring Cloud Task như một phần tác vụ bảo trì nghiệp vụ nếu chưa có chính sách retention riêng.

### 5.3. Quy tắc an toàn khi thực thi

| Cơ chế | Mục đích |
| --- | --- |
| Preview mặc định, execute khi chỉ định | Giảm khả năng chạy nhầm thao tác phá hủy |
| Cutoff cố định, chính sách retention rõ | Tránh phạm vi xóa bị mở rộng ngoài ý muốn |
| Batch size, timeout, tốc độ xử lý có giới hạn | Tránh quá tải và transaction quá dài |
| Chống chạy chồng lấn hoặc khóa phân tán | Ngăn hai tiến trình xử lý cùng vùng dữ liệu gây cạnh tranh |
| Ghi số bản ghi dự kiến, đã xử lý, lỗi và thời lượng | Giúp đối soát và đánh giá hiệu năng |
| Quy trình khôi phục hoặc lưu trữ trước xóa | Bảo đảm khả năng xử lý sai sót nghiệp vụ |

Đối với tác vụ dùng để sửa dữ liệu, **chạy lại an toàn** còn có nghĩa là chỉ xử lý những bản ghi chưa đạt trạng thái đích; không chỉ kiểm tra tiến trình trước đó đã được gọi hay chưa.

## 6. Kích hoạt theo lịch, theo yêu cầu và kiểm soát trùng lịch

Ba tác vụ có thể dùng chung cơ chế ghi metadata nhưng **khác cơ chế kích hoạt**:

- **Nhập dữ liệu:** kích hoạt khi tệp được tiếp nhận hoặc người vận hành yêu cầu xử lý lại một source-id.
- **Báo cáo:** chạy sau mốc chốt dữ liệu, theo lịch ngày/tuần hoặc khi người dùng yêu cầu tạo lại một kỳ.
- **Bảo trì:** thường chạy ngoài giờ cao điểm và có thể đặt giới hạn về số bản ghi hoặc thời gian mỗi lượt.

Ví dụ Kubernetes CronJob cho ứng dụng tạo báo cáo. Image cần được đóng gói với entrypoint thực thi file JAR; ứng dụng chọn ngày báo cáo theo quy tắc ngày nghiệp vụ đã cấu hình nếu không truyền date.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example/data-operations:1.0.0
              args:
                - "--operation=report"
~~~

**Lưu ý:** trường timeZone cần phiên bản Kubernetes hỗ trợ; nếu cụm chưa hỗ trợ, phải quy đổi lịch ở bộ điều phối. **concurrencyPolicy: Forbid** ngăn chồng lấn các Job thuộc cùng CronJob, nhưng không tự ngăn một người dùng khởi chạy tác vụ tương đương bằng API hay dòng lệnh. Với yêu cầu “mỗi kỳ chỉ có một bản phát hành”, cần thêm ràng buộc duy nhất hoặc khóa nghiệp vụ ở CSDL.

API nhận yêu cầu chạy không nên giữ kết nối HTTP chờ nhiều phút. Nó có thể tạo yêu cầu, gửi đến Job launcher và trả về định danh để hệ thống khác truy vấn trạng thái. Tránh tạo TaskExecution như thể tác vụ đã thành công ngay khi yêu cầu vừa được tiếp nhận; cần phân biệt **đã yêu cầu chạy**, **đang chạy** và **đã hoàn tất**.

## 7. Theo dõi thực thi với TaskRepository

Spring Cloud Task ghi nhận thời gian bắt đầu/kết thúc, tên tác vụ, tham số và kết quả thực thi. Với schema quan hệ tiêu chuẩn, bảng **TASK_EXECUTION** cung cấp các trường như **TASK_EXECUTION_ID, TASK_NAME, START_TIME, END_TIME, EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE**. Tên chi tiết của cột và DDL phải đối chiếu với schema đi kèm phiên bản đang chạy.

Ví dụ truy vấn kiểm tra những lượt gần nhất:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC
LIMIT 20;
~~~

Cách diễn giải:

| Quan sát | Ý nghĩa và bước kiểm tra tiếp |
| --- | --- |
| Có END_TIME và exit code thành công | Tiến trình hoàn tất; kiểm tra thêm kết quả nghiệp vụ tương ứng |
| Có END_TIME và exit code lỗi | Đọc log, ERROR_MESSAGE, tham số và dữ liệu đầu vào của lượt chạy |
| START_TIME có nhưng END_TIME chưa có | Có thể đang chạy hoặc đã chết bất thường; đối chiếu trạng thái tiến trình/Job và timeout |
| Không thấy bản ghi thực thi | Kiểm tra ứng dụng đã khởi động tới Task lifecycle, kết nối CSDL metadata, migration và cấu hình TaskRepository |

Không suy luận rằng một bản ghi có **END_TIME trống** luôn đang chạy: tiến trình có thể đã bị kill trước khi kịp cập nhật. Việc phát hiện “treo” cần phối hợp thời gian chạy tối đa, heartbeat/log và trạng thái container hoặc launcher.

Ở lớp ứng dụng, nên ghi log có cấu trúc với **executionId** (nếu có), operation, business key, số dòng đọc/ghi/bỏ qua, thời lượng và mã lỗi. Giữ thông tin nhạy cảm ngoài log. Bộ điều phối nên giám sát thời gian thực thi, mã thoát và tỷ lệ lỗi; dùng truy vấn repository để điều tra lịch sử.

### Xử lý mã thoát và lỗi

- **Thành công:** logic nghiệp vụ hoàn thành, ghi kết quả và cho tiến trình kết thúc bình thường.
- **Lỗi có thể thử lại:** ví dụ mất kết nối tạm thời; ném exception hoặc báo lỗi tường minh để launcher biết lần chạy thất bại, sau đó thử lại theo giới hạn.
- **Lỗi dữ liệu cố định:** ví dụ schema CSV sai; ghi lý do rõ ràng, dừng và yêu cầu sửa nguồn trước khi chạy lại.
- **Chết bất thường:** không phụ thuộc duy nhất vào listener cuối tiến trình; có cách phát hiện lần chạy hết hạn và đối soát những trạng thái chưa hoàn tất.

Nếu ứng dụng tự bắt toàn bộ exception mà không truyền lỗi hay mã thoát phù hợp, hệ thống điều phối có thể coi tác vụ là thành công dù dữ liệu chưa được xử lý.

## 8. Khi nào cần phối hợp với Spring Batch?

**Spring Cloud Task** quản lý vòng đời và metadata của **tiến trình có thời gian chạy hữu hạn**. **Spring Batch** cung cấp mô hình **Job/Step**, đọc–xử lý–ghi theo chunk, checkpoint, retry/skip có chính sách và metadata chi tiết của công việc theo lô. Hai công cụ có thể phối hợp trong cùng ứng dụng: một lần thực thi Spring Cloud Task chạy một Batch Job hoặc một chuỗi Job phù hợp.

| Yêu cầu | Gợi ý |
| --- | --- |
| Đọc một tệp nhỏ, gọi một API và ghi kết quả đơn giản | Spring Cloud Task với ApplicationRunner/CommandLineRunner |
| Nhập hàng triệu bản ghi, cần khởi động lại từ checkpoint | Spring Cloud Task kết hợp Spring Batch |
| Báo cáo chỉ gồm một truy vấn tổng hợp và tạo một tệp | Spring Cloud Task có thể đủ |
| Báo cáo nhiều bước ETL, xử lý từng khối và cần theo dõi step | Spring Cloud Task kết hợp Spring Batch |
| Xóa dữ liệu theo lô nhỏ với vòng lặp kiểm soát | Spring Cloud Task; cân nhắc Batch nếu cần checkpoint/step phức tạp |

Khi kết hợp, **TaskRepository** và **JobRepository** có mục đích khác nhau, yêu cầu schema tương ứng và cấu hình transaction rõ ràng. Không đồng nhất **TaskExecution** với **JobExecution**; một tiến trình Task có thể gắn với một hoặc nhiều lần thực thi Job. Với Job có thể restart, cần thiết kế **JobParameters** nhận diện đúng phiên dữ liệu và tránh vô tình tạo một phiên Job mới ở mỗi lần retry.

## 9. Checklist trước khi đưa tác vụ vào vận hành

| Nhóm | Câu hỏi kiểm tra |
| --- | --- |
| Đầu vào | Tham số bắt buộc được xác thực? Đường dẫn, kỳ báo cáo, cutoff có định dạng và giới hạn hợp lệ? |
| Idempotency | Chạy lại sau khi hoàn thành hoặc thất bại một phần có tạo dữ liệu hay tác dụng phụ trùng không? |
| Giao dịch | Ranh giới transaction có đủ ngắn? Chấp nhận trạng thái xử lý dở dang nào? |
| Metadata | TaskRepository đã được tạo đúng schema, có quyền đọc/ghi và được sao lưu phù hợp? |
| Lỗi | Lỗi dữ liệu, lỗi tạm thời, timeout và chết tiến trình có thể phân biệt và giám sát được? |
| Điều phối | Có giới hạn retry, timeout, số lần chạy đồng thời và tài nguyên CPU/RAM? |
| Bảo mật | Chỉ cấp quyền dữ liệu cần thiết, truyền secret qua kênh an toàn, ẩn dữ liệu cá nhân trên log? |
| Đối soát | Có số bản ghi, checksum, report key hoặc thông tin phục hồi để xác nhận đầu ra? |
| Vận hành | Có runbook xem lịch sử, chạy lại theo business key, dừng tác vụ và xử lý metadata treo? |

### Bài tập thực hành

Thiết kế ba lệnh chạy thực tế cho một hệ thống bán hàng:

1. **Import**: nhận tệp chứa 10.000 đơn hàng. Chạy lần đầu, chạy lại y nguyên, rồi giả lập lỗi CSDL giữa một lô. Đối soát tổng số đơn để chứng minh không trùng.
2. **Report**: tạo báo cáo cho một ngày theo múi giờ nghiệp vụ. Chạy lại cùng ngày và xác nhận report key, version, checksum của tệp được kiểm soát; kiểm tra giao dịch đúng thời điểm ranh giới ngày.
3. **Cleanup**: preview số phiên hết hạn trước cutoff, chạy execute với chunk nhỏ, ngắt tiến trình giữa chừng rồi chạy tiếp. Đối chiếu số dòng trước/sau và xác nhận không xóa bản ghi mới hơn cutoff.

Với mỗi lượt chạy, lưu **TaskExecution ID**, business key, mã thoát, kết quả đầu ra và lý do lỗi nếu có. Sau đó truy vấn TaskRepository để phân biệt lần chạy thành công, lần thất bại và lần chưa có kết thúc.

## 10. Các điểm cần ghi nhớ

- Spring Cloud Task đặc biệt hữu ích cho **công việc hữu hạn cần truy vết lần chạy**; lịch và cơ chế kích hoạt do công cụ khác cung cấp.
- **Import** ưu tiên khóa nghiệp vụ, kiểm tra nguồn, idempotency và khả năng chạy lại sau lỗi một phần.
- **Report** ưu tiên xác định kỳ dữ liệu nhất quán, report key, xuất tệp an toàn và tránh gửi thông báo trùng.
- **Maintenance** ưu tiên giới hạn phạm vi, preview, xử lý theo lô, kiểm soát tải và phương án khôi phục.
- **TaskRepository** ghi kết quả kỹ thuật của lần chạy; **dữ liệu kết quả nghiệp vụ** cần được quản lý riêng. Khi cần xử lý khối lượng lớn với checkpoint và step, phối hợp thêm Spring Batch.
