# Nhiều lần thực thi cùng tên và nguy cơ chạy chồng

## 1. Bài toán: một tên task, nhiều lần chạy

**Spring Cloud Task** giúp xây dựng ứng dụng Spring Boot có **thời gian chạy hữu hạn**: nhận tham số, thực hiện công việc, ghi nhận metadata trong **TaskRepository** rồi kết thúc. Một task như `daily-reconciliation` có thể được gọi bằng lịch ban đêm, thao tác thủ công từ quản trị viên, yêu cầu API hoặc một cơ chế retry.

**Tên task không phải định danh của một lần chạy.** Mỗi lần khởi động có thể tạo một **TaskExecution** khác nhau với `TASK_EXECUTION_ID` riêng, dù `TASK_NAME` và tham số dòng lệnh giống hệt nhau. Khi hai tiến trình của cùng task hoạt động đồng thời, ta gọi đó là **chạy chồng (overlapping execution)**.

Ví dụ: tác vụ đối soát ngày `2026-11-23` cần 12 phút, nhưng lịch chạy lại kích hoạt sau 10 phút.

| Mốc minh họa | Tiến trình A | Tiến trình B |
| --- | --- | --- |
| 02:00 | Bắt đầu đối soát `2026-11-23` | Chưa chạy |
| 02:10 | Vẫn cập nhật dữ liệu | Scheduler khởi chạy lại cùng ngày |
| 02:11 | Đang cập nhật đơn `#381` | Cũng cập nhật đơn `#381` |
| 02:12 | Kết thúc | Vẫn đang chạy |
| 02:22 | Đã dừng | Kết thúc với kết quả có thể bị trùng hoặc sai |

**Nguy cơ:** hai tiến trình đọc cùng dữ liệu ban đầu rồi cùng ghi kết quả; một lần chạy khác ghi đè dữ liệu mới hơn; cùng file báo cáo được phát hành hai lần; hai email được gửi; pool kết nối quá tải; hoặc hai job Batch cạnh tranh tài nguyên.

Bài thuộc chương **Khóa và đồng thời** sẽ giúp bạn phân biệt **nhiều TaskExecution**, **tranh chấp tài nguyên**, **khóa theo tên task** và **tính idempotent theo khóa nghiệp vụ**, từ đó thiết kế task chạy theo lịch hoặc theo yêu cầu một cách an toàn.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện nhiều lần thực thi có cùng `TASK_NAME` nhưng khác `TASK_EXECUTION_ID`.
2. Giải thích vì sao `TaskRepository` ghi lịch sử mà không mặc định chống chạy chồng.
3. Cấu hình giới hạn **single instance** của Spring Cloud Task khi thực sự cần.
4. Phân biệt khóa ở framework với `concurrencyPolicy` của Kubernetes CronJob và khóa nghiệp vụ.
5. Chọn cách kiểm soát đồng thời, retry, TTL và cách phục hồi khi tiến trình bị kill.
6. Thực hành hai lần khởi chạy chồng nhau, đọc log và đối chiếu database.

## 2. Đừng nhầm ba cấp độ định danh

Trong hệ thống thường tồn tại đồng thời:

| Cấp độ | Ví dụ | Mục đích |
| --- | --- | --- |
| **Tên task** | `daily-reconciliation` | Nhận diện loại ứng dụng; có thể được dùng làm khóa single-instance |
| **Task execution ID** | `1041`, `1042` | Nhận diện **một lần chạy**; liên kết log, thời gian, mã thoát |
| **Khóa nghiệp vụ (business key)** | `tenantA:2026-11-23` | Nhận diện **đơn vị dữ liệu phải xử lý**; cơ sở chống tác động trùng |

Giả sử hai lần chạy đều có `TASK_NAME=daily-reconciliation` và `--businessDate=2026-11-23`. TaskRepository có thể tạo hai execution ID khác nhau. Điều này phản ánh hai lần khởi động ứng dụng, **không có nghĩa** hai lần cập nhật cùng ngày là an toàn.

Ngược lại, hai ứng dụng có **tên task khác nhau** — `reconcile-fast` và `reconcile-manual` — vẫn có thể cùng xử lý business key `tenantA:2026-11-23`. Khóa theo tên task không ngăn được trường hợp hai tên khác nhau cùng tranh chấp dữ liệu nghiệp vụ.

### Hai câu hỏi cần trả lời riêng

**Câu hỏi A: Có cho hai tiến trình cùng tên chạy đồng thời?** Nếu không, bạn cần cơ chế kiểm soát **overlap** ở cấp scheduler, runtime hoặc framework.

**Câu hỏi B: Có cho một công việc nghiệp vụ được thực hiện hai lần theo thời gian?** Nếu không, bạn cần **idempotency**, khóa/ràng buộc duy nhất theo business key và quy tắc xử lý lại.

**Chỉ giải quyết câu hỏi A không tự giải quyết câu hỏi B.** Hai task cùng tên chạy *lần lượt* không bị chồng nhưng vẫn có thể tạo dữ liệu trùng.

## 3. Mặc định Spring Cloud Task xử lý nhiều lần chạy thế nào?

Theo tài liệu cấu hình Spring Cloud Task, thuộc tính:

`spring.cloud.task.single-instance-enabled`

có **giá trị mặc định `false`**. Khi không bật cơ chế single-instance, framework không dùng tính năng khóa theo tên để chặn một process khác cùng tên. Mỗi process vẫn có thể ghi `TaskExecution` riêng trong TaskRepository nếu khởi tạo thành công và database cho phép.

~~~mermaid
sequenceDiagram
    participant S as Scheduler / API
    participant A as Task A (name=invoice-export)
    participant B as Task B (name=invoice-export)
    participant DB as TaskRepository

    S->>A: Run --businessDate=2026-11-23
    A->>DB: Ghi executionId=21
    A->>A: Xuất dữ liệu
    S->>B: Run --businessDate=2026-11-23
    B->>DB: Ghi executionId=22
    B->>B: Có thể xuất cùng dữ liệu
    A->>DB: Cập nhật kết quả #21
    B->>DB: Cập nhật kết quả #22
    Note over A,B: Hai ID riêng không đồng nghĩa không tranh chấp nghiệp vụ
~~~

**TaskRepository là kho lịch sử, không phải cơ chế đồng bộ nghiệp vụ mặc định.** Các truy vấn như “tìm TaskExecution đang chạy” không nên được dùng như khóa phân tán tự chế: giữa lúc đọc và lúc ghi, một process khác vẫn có thể khởi động. Đây là lỗi **check-then-act race condition**.

~~~text
Process A: SELECT -> chưa thấy ai đang chạy
Process B: SELECT -> chưa thấy ai đang chạy
Process A: bắt đầu xử lý
Process B: bắt đầu xử lý
~~~

Muốn ngăn chồng lấn trên nhiều process, việc “kiểm tra và giành quyền chạy” phải có một cơ chế **đồng bộ/atomic** đáng tin cậy.

## 4. Single-instance lock của Spring Cloud Task

Spring Cloud Task có tính năng **giới hạn một instance theo tên task**. Khi các lần chạy đều được cấu hình đúng, chúng cùng dùng cơ sở dữ liệu khóa và một task cùng tên đang giữ khóa, lần khởi chạy cạnh tranh sẽ bị từ chối thay vì cùng xử lý nghiệp vụ.

### 4.1. Cấu hình bật tính năng

Ví dụ `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-reconciliation
      single-instance-enabled: true
~~~

Hoặc truyền khi khởi động:

~~~bash
java -jar reconciliation-task.jar --spring.cloud.task.single-instance-enabled=true
~~~

**Điều kiện quan trọng:**

- Mọi tiến trình cần được kiểm soát phải có **cùng tên task** theo cấu hình `spring.cloud.task.name` hoặc cơ chế `TaskNameResolver`, đồng thời **đều bật** `single-instance-enabled=true`.
- Chúng phải dùng **cùng kho khóa JDBC** mà Spring Cloud Task/Spring Integration có thể truy cập; hai ứng dụng trỏ tới hai database khác nhau không thể dùng khóa ở database để phối hợp nhau.
- Phải có schema khóa, DataSource, transaction và quyền database phù hợp. Bật một dòng YAML **không đủ** nếu classpath hoặc bảng SQL còn thiếu.
- Tính năng khóa theo **tên**, không tự phân biệt `businessDate`, `tenantId` hay tham số của mỗi lần chạy.

Tài liệu Spring Cloud Task yêu cầu thêm các dependency Spring Integration cho tính năng này:

~~~xml
<!-- Một phần của pom.xml, phiên bản do BOM tương thích quản lý -->
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jdbc</artifactId>
</dependency>
~~~

Các dependency này **bổ sung** cho dependency Spring Cloud Task và driver JDBC bạn đang sử dụng. Hãy chọn BOM/version tương thích với Spring Boot của dự án; không sao chép một phiên bản thư viện cố định thiếu kiểm chứng.

### 4.2. Hai lần chạy cạnh tranh

~~~mermaid
sequenceDiagram
    participant A as Tiến trình A
    participant DB as Kho khóa JDBC
    participant B as Tiến trình B
    participant W as Xử lý nghiệp vụ

    A->>DB: Xin khóa name=daily-reconciliation
    DB-->>A: Giành khóa thành công
    A->>W: Thực thi
    B->>DB: Xin cùng khóa theo task name
    DB-->>B: Khóa đang được giữ
    B--xB: TaskExecutionException / khởi động thất bại
    A->>W: Hoàn tất
    A->>DB: Giải phóng khóa khi kết thúc bình thường
~~~

Theo tài liệu Spring Cloud Task, nếu đã có task cùng tên đang chạy với tính năng này được bật, lần gọi khác **thất bại** với thông báo dạng:

~~~text
Task with name "daily-reconciliation" is already running.
~~~

Tài liệu cũng nêu mã thoát tiến trình **`1`** cho lần bị từ chối trong trường hợp cạnh tranh thông thường. Đây là **tín hiệu thất bại do tranh chấp**, không phải lệnh tự động xếp hàng chờ và chạy lại sau đó.

Điểm cần thận trọng: một tiến trình bị từ chối **không nhất thiết đã tạo được bản ghi `TaskExecution` hoàn chỉnh**. Tùy bước khởi động bị lỗi, bạn có thể chỉ thấy lỗi trong log và trạng thái exit của process. Vì thế phải quan sát **cả hạ tầng khởi chạy lẫn TaskRepository**, không dựa vào số bản ghi database để đếm tuyệt đối mọi yêu cầu chạy đã bị từ chối.

### 4.3. Bảng TASK_LOCK

Schema Spring Cloud Task có bảng **`TASK_LOCK`** phục vụ tính năng single-instance (khi dùng tiền tố mặc định). Cấu trúc thường có các cột:

| Cột | Mục đích khái quát |
| --- | --- |
| `LOCK_KEY` | Định danh của bản ghi khóa |
| `REGION` | Nhóm/phạm vi khóa |
| `CLIENT_ID` | Định danh client chủ sở hữu khóa |
| `CREATED_DATE` | Thời điểm tạo bản ghi khóa |

Đây là **bảng hỗ trợ cơ chế khóa của framework**, khác với `TASK_EXECUTION` (lịch sử lần thực thi). Không tự áp đặt rằng `CLIENT_ID` là `TASK_EXECUTION_ID` hay `REGION` luôn chính là tên task nếu chưa kiểm tra schema và implementation tương ứng.

Ví dụ truy vấn **chỉ đọc** để kiểm tra trong môi trường lab:

~~~sql
SELECT LOCK_KEY, REGION, CLIENT_ID, CREATED_DATE
FROM TASK_LOCK
ORDER BY CREATED_DATE DESC;
~~~

Không thao tác `DELETE FROM TASK_LOCK` hoặc tự sửa nội dung khóa chỉ vì thấy process dừng. Khóa có thể vẫn hợp lệ cho process khác, hoặc cơ chế TTL/recovery đang xử lý; xóa tùy tiện có thể mở cửa cho hai process cùng chạy.

## 5. TTL, thời gian kiểm tra khóa và tình huống lỗi

Một khóa phân tán không chỉ có khái niệm **đang giữ** hay **đã thả**. Khi process chết đột ngột, mất mạng hoặc treo, cần chính sách hết hạn và phục hồi.

Các thuộc tính cấu hình Spring Cloud Task được liệt kê trong danh mục Spring Cloud gồm:

| Thuộc tính | Ý nghĩa | Giá trị mặc định được tài liệu công bố |
| --- | --- | --- |
| `spring.cloud.task.single-instance-enabled` | Bật khóa single-instance theo tên | `false` |
| `spring.cloud.task.single-instance-lock-check-interval` | Khoảng thời gian giữa các lượt kiểm tra khóa | `500` ms |
| `spring.cloud.task.single-instance-lock-ttl` | Thời gian tối đa một lượt thực thi được giữ khóa | `Integer.MAX_VALUE` ms |

Giá trị mặc định và hành vi chi tiết có thể thay đổi giữa phiên bản; hãy xem configuration properties của version bạn triển khai. **Đừng tự mặc định `lock-check-interval` biến cơ chế từ chối thành hàng đợi**: theo hướng dẫn single-instance, một lần khởi chạy cạnh tranh cùng tên sẽ thất bại. Interval liên quan đến cách cơ chế khóa kiểm tra trạng thái; cần xác minh khi bạn tinh chỉnh thay vì suy đoán lịch retry.

### 5.1. TTL quá ngắn có thể mở lại nguy cơ chồng lấn

Giả sử tác vụ mất 40 phút nhưng TTL của khóa chỉ 10 phút. Khi quyền giữ khóa hết hạn theo cơ chế triển khai, một process khác **có thể giành khóa** trong lúc process cũ vẫn đang thực hiện nghiệp vụ. Do đó đặt TTL ngắn không phải giải pháp an toàn để “tự phục hồi nhanh”.

**Nguyên tắc:** ước lượng thời gian chạy bình thường, thời gian xử lý chậm, timeout hạ tầng và các lần chờ bên ngoài; cấu hình TTL theo chiến lược kiểm soát khóa thực tế. Dù TTL có dài, vẫn cần **idempotency** vì các sự cố mạng hoặc giới hạn đồng bộ có thể tạo tình huống không chắc chắn.

### 5.2. TTL quá dài có thể khiến lần sau bị từ chối lâu

Nếu task chết khi đang giữ khóa và cơ chế không giải phóng kịp, lần chạy kế tiếp có thể không giành được quyền trong một khoảng thời gian lớn. Điều này cần quy trình vận hành:

1. Xác nhận process/pod đang giữ khóa **đã thật sự dừng**.
2. Kiểm tra log, trạng thái task, thời điểm tạo khóa và timeout.
3. Xem cơ chế hết hạn/giải phóng của phiên bản framework.
4. Thực hiện khôi phục khóa theo quy trình được phê duyệt, với quyền truy cập database phù hợp.
5. Kiểm tra kết quả nghiệp vụ trước khi retry để tránh xử lý trùng.

**Không hướng dẫn thao tác xóa khóa mù quáng:** metadata về việc giữ khóa và việc tác vụ đã ghi dữ liệu thật có thể khác nhau.

## 6. Kiểm soát chạy chồng từ scheduler: Kubernetes CronJob

Khi task đóng gói thành container và khởi chạy định kỳ bằng **Kubernetes CronJob**, scheduler có tùy chọn `spec.concurrencyPolicy`:

| Giá trị | Hành vi đối với Job do **cùng một CronJob** tạo |
| --- | --- |
| `Allow` | Mặc định; cho phép nhiều Job chồng nhau |
| `Forbid` | Nếu Job trước chưa xong, bỏ qua lần lên lịch mới thay vì khởi tạo Job đồng thời |
| `Replace` | Thay thế Job đang chạy bằng Job mới; có nguy cơ gián đoạn công việc dở |

Ví dụ cấu hình:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-reconciliation
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: reconciliation
              image: example.registry/reconciliation-task:1.0
              args:
                - "--businessDate=2026-11-23"
~~~

Đây là **YAML minh họa** cho lab; trong thực tế `businessDate` phải được tạo theo ngày cần xử lý, không cố định mãi một ngày, và cần cấu hình image, resource limit, secret và chính sách job phù hợp.

**Giới hạn rất quan trọng:** `concurrencyPolicy: Forbid` chỉ áp dụng cho các Job **do cùng CronJob đó tạo ra**. Một Job được chạy thủ công, một CronJob khác, hoặc một hệ thống ngoài Kubernetes vẫn có thể khởi chạy ứng dụng cùng tên. Nếu có nhiều đường kích hoạt, cần một cơ chế khóa chung hoặc ràng buộc dữ liệu nghiệp vụ phù hợp.

Kubernetes còn có thể tạo trường hợp khởi chạy lại, trễ lịch hoặc Job chạy nhiều hơn một lần trong tình huống nhất định; vì vậy không dựa vào `Forbid` để hứa hẹn xử lý đúng một lần.

## 7. Các lựa chọn khóa và cấp độ bảo vệ

Không phải mọi bài toán đều cần khóa toàn cục theo tên task. Lựa chọn tùy **tài nguyên tranh chấp** và **đơn vị công việc**.

| Giải pháp | Phạm vi điều khiển | Phù hợp | Điểm hạn chế |
| --- | --- | --- | --- |
| Spring Cloud Task `single-instance-enabled` | Một **tên task** trên kho khóa được chia sẻ | Chỉ cho một lần chạy của cùng ứng dụng tại một thời điểm | Không phân biệt business key; không chống tác động trùng ở các lần chạy nối tiếp |
| Kubernetes CronJob `Forbid` | Các Job thuộc **cùng CronJob** | Lịch chạy định kỳ trong cùng CronJob | Không chặn chạy thủ công hoặc CronJob khác |
| Khóa phân tán theo business key | `tenant + ngày + loại công việc` | Cho phép tenant/ngày khác chạy song song, chặn cùng đơn vị nghiệp vụ | Cần triển khai TTL/lease, fencing và phục hồi đúng |
| Ràng buộc duy nhất / idempotent ở database nghiệp vụ | Một kết quả hoặc thao tác duy nhất | Chống ghi trùng ngay cả khi request bị gửi lại | Không tự giới hạn CPU hoặc số process |
| Hàng đợi với giới hạn consumer | Số tác vụ được nhận/xử lý | Cần kiểm soát thông lượng và thứ tự | Cần xử lý giao nhận lại, ack và idempotency |
| Điều phối workflow | Công việc nhiều bước, phụ thuộc | Cần lịch, retry, giới hạn chạy đồng thời tập trung | Không thay thế tính đúng đắn của nghiệp vụ |

### 7.1. Khi nào khóa theo tên quá rộng?

Ví dụ `monthly-export` có thể chạy độc lập cho nhiều `tenantId`. Nếu bật single-instance theo tên, process của tenant B có thể bị từ chối chỉ vì tenant A đang chạy, dù hai bên không chia sẻ dữ liệu. Bạn có thể cân nhắc khóa theo `tenantId + kỳ báo cáo` nếu kiến trúc hỗ trợ.

### 7.2. Khi nào khóa theo tên quá hẹp?

Ví dụ `refund-batch` và `refund-manual` cùng cập nhật một giao dịch hoàn tiền. Hai tên task khác nhau không cạnh tranh **cùng tên khóa**, nhưng lại tranh chấp **cùng giao dịch**. Cần ràng buộc nghiệp vụ ở service/database để tránh hoàn tiền hai lần.

### 7.3. “Không chạy chồng” không có nghĩa “exactly once”

Ngay cả với single-instance, lần 1 có thể hoàn tất lúc 02:10 và lần 2 khởi chạy lúc 02:11 với cùng tham số. Vì không chồng lấn, khóa không từ chối lần 2. Nếu nghiệp vụ tạo file hoặc gửi email lần nữa, vẫn phát sinh tác động trùng.

Một cách làm an toàn là gắn một **business key**, ví dụ `reportDate + tenantId`. Trong database nghiệp vụ, thiết kế ràng buộc duy nhất cho kết quả và trạng thái xử lý (ví dụ `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) cùng transaction phù hợp. Nếu nhận lại cùng yêu cầu sau thành công, trả về kết quả cũ hoặc bỏ qua tác động đã hoàn tất.

## 8. Đọc TaskRepository để phát hiện chạy chồng

`TaskRepository` lưu từng lần thực thi, còn `TaskExplorer` giúp đọc metadata. Khi có database SQL, hai bảng thường dùng là `TASK_EXECUTION` và `TASK_EXECUTION_PARAMS`.

### 8.1. Liệt kê những lần chạy cùng tên

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-reconciliation'
ORDER BY START_TIME DESC, TASK_EXECUTION_ID DESC;
~~~

Ví dụ minh họa:

| ID | Tên task | Bắt đầu | Kết thúc | Mã thoát |
| --- | --- | --- | --- | --- |
| 1041 | daily-reconciliation | 02:00 | 02:12 | 0 |
| 1042 | daily-reconciliation | 02:10 | 02:22 | 0 |
| 1043 | daily-reconciliation | 03:00 | 03:05 | 0 |

Hai khoảng `[02:00, 02:12)` và `[02:10, 02:22)` giao nhau 2 phút. Vậy **1041 và 1042 chạy chồng**. Đều có mã thoát `0` không chứng minh kết quả nghiệp vụ chính xác.

### 8.2. Truy vấn tìm các cặp khoảng thời gian giao nhau

Với những bản ghi **đã kết thúc**, có thể tự nối bảng để tìm cặp có thời gian chồng lấn:

~~~sql
SELECT
    a.TASK_EXECUTION_ID AS execution_a,
    b.TASK_EXECUTION_ID AS execution_b,
    a.START_TIME AS a_start,
    a.END_TIME AS a_end,
    b.START_TIME AS b_start,
    b.END_TIME AS b_end
FROM TASK_EXECUTION a
JOIN TASK_EXECUTION b
  ON a.TASK_NAME = b.TASK_NAME
 AND a.TASK_EXECUTION_ID < b.TASK_EXECUTION_ID
 AND a.START_TIME < b.END_TIME
 AND b.START_TIME < a.END_TIME
WHERE a.TASK_NAME = 'daily-reconciliation'
  AND a.END_TIME IS NOT NULL
  AND b.END_TIME IS NOT NULL
ORDER BY a.START_TIME, b.START_TIME;
~~~

Quy tắc giao khoảng thời gian ở đây dùng **[start, end)**: hai lần chạy chạm nhau đúng thời điểm một lần kết thúc **không được coi là chồng lấn**. Truy vấn này chỉ minh họa kiểm tra hậu kỳ; thời gian lưu trong repository có thể có độ phân giải thấp hoặc khác múi giờ hiển thị, nên cần diễn giải thận trọng.

**Lưu ý:** bản ghi có `END_TIME IS NULL` đã bị loại khỏi truy vấn, vì nó có thể là task đang chạy hoặc tiến trình đã chết trước khi cập nhật metadata. Không tự thay `NULL` bằng `CURRENT_TIMESTAMP` rồi khẳng định chắc chắn hai process đã chồng lấn; phải kiểm tra log/hạ tầng thực tế.

### 8.3. Tìm những bản ghi chưa ghi kết thúc

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-reconciliation'
  AND END_TIME IS NULL
ORDER BY START_TIME;
~~~

Kết quả này là danh sách **cần xác minh**, không phải danh sách process chắc chắn còn sống. Nếu JVM bị kill, metadata có thể còn dang dở dù không còn khóa hợp lệ.

## 9. Ví dụ Spring Boot để thử chạy chồng

Giả sử ứng dụng đã được tạo từ Spring Boot tương thích với Spring Cloud Task và có DataSource/schema dùng chung. Runner sau chỉ **đợi có giới hạn** để bạn kịp khởi chạy hai process từ hai terminal, không cần tác động đến dữ liệu thật.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class OverlapDemoApplication {

    private static final Logger log =
            LoggerFactory.getLogger(OverlapDemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(OverlapDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runTask() {
        return args -> {
            log.info("WORK_BEGIN businessDate={}",
                    args.getOptionValues("businessDate"));

            // Mô phỏng xử lý hữu hạn để có thời gian chạy lần thứ hai.
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw ex;
            }

            log.info("WORK_DONE");
        };
    }
}
~~~

Cấu hình lab lần 1 — **cho phép chồng lấn**:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: overlap-demo
      single-instance-enabled: false
~~~

Trong hai terminal kết nối cùng môi trường/database, chạy cùng lệnh gần như đồng thời:

~~~bash
java -jar overlap-demo.jar --businessDate=2026-11-23
~~~

**Kỳ vọng:** nếu cả hai process khởi tạo thành công, có thể thấy hai lần chạy `overlap-demo`, ID khác nhau, khoảng thời gian giao nhau. Đây là minh họa của cơ chế mặc định, không áp dụng cho xử lý nghiệp vụ thật.

Cấu hình lab lần 2 — **bật giới hạn single-instance**:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: overlap-demo
      single-instance-enabled: true
~~~

Đảm bảo đã thêm `spring-integration-core`, `spring-integration-jdbc`, tạo schema khóa và dùng **cùng database**. Chạy tiến trình A, sau đó chạy tiến trình B trong lúc A còn `sleep`.

**Kỳ vọng:** tiến trình A giành khóa, B bị từ chối do cùng tên; kiểm tra thông báo lỗi và mã thoát. Sau khi A kết thúc bình thường, có thể khởi chạy tiến trình C mới. Đây là giới hạn **chồng lấn**, không ngăn C xử lý lại cùng `businessDate`.

**Mẹo kiểm thử:** không cần gửi `kill -9` vào môi trường sản xuất để tạo tình huống stale lock. Muốn khảo sát sự cố hãy dùng môi trường tách biệt, biết cách khôi phục dữ liệu và quan sát các trường hợp timeout/kết thúc đúng cách trước.

## 10. Spring Batch và các lần chạy song song

Khi một ứng dụng Spring Cloud Task khởi chạy **Spring Batch**:

- `TaskRepository` theo dõi vòng đời **process task**.
- `JobRepository` theo dõi **JobInstance, JobExecution, StepExecution**, tham số job và trạng thái xử lý.
- `TaskExecution` khác với `JobExecution`. Một task có thể liên kết Batch job theo cấu hình tích hợp.

Spring Batch có các quy tắc định danh JobInstance theo tên job và **identifying job parameters**. Một JobInstance đang chạy có thể làm một yêu cầu chạy tương đương bị từ chối theo chính sách của Batch. Tuy nhiên, đó **không phải cùng cơ chế** với single-instance theo **task name** của Spring Cloud Task.

Ví dụ: hai task cùng tên có thể chạy với hai ngày khác nhau; single-instance sẽ chặn theo tên dù Batch coi chúng là hai JobInstance độc lập. Ngược lại, hai ứng dụng task khác tên có thể kích hoạt cùng một JobInstance trong Batch; khi đó kiểm soát concurrency của Batch mới có vai trò.

Nếu dùng JobLauncher bất đồng bộ, runner có thể trả về trước khi job kết thúc; cần thiết kế để **task chỉ kết thúc khi công việc Batch bắt buộc hoàn tất** hoặc quản lý trạng thái của job độc lập. Nếu không, khóa theo vòng đời task có thể được thả quá sớm trong khi Batch vẫn đang chạy.

## 11. Xử lý sự cố và quyết định vận hành

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Hai task cùng tên vẫn chạy đồng thời | `single-instance-enabled` chưa bật trên tất cả, tên task khác thực tế, database khóa khác nhau hoặc classpath/schema sai | Kiểm tra cấu hình runtime, tên task, DataSource, dependency và log khóa |
| Lần khởi chạy thứ hai thất bại | Single-instance đã từ chối vì khóa đang được giữ | Kiểm tra process A, log B và mã thoát; quyết định bỏ qua hay retry qua scheduler |
| Lần chạy sau bị từ chối dù process cũ đã chết | Khóa chưa được giải phóng, TTL quá dài hoặc phục hồi chưa hoàn tất | Xác nhận process thực sự chết, kiểm tra khóa và quy trình recovery |
| Chạy lại sau TTL nhưng công việc cũ vẫn hoạt động | TTL ngắn hơn thời gian chạy/không có kiểm soát lease phù hợp | Xem cấu hình TTL, timeout, tài nguyên, trạng thái process; bảo vệ dữ liệu bằng fencing/idempotency nếu cần |
| Có nhiều `TASK_EXECUTION` cùng tên | Nhiều yêu cầu đã khởi tạo thành công vào các thời điểm khác nhau | Đối chiếu timeline; khác ID là bình thường, cần xem có thực sự chồng lấn không |
| CronJob đã dùng `Forbid` nhưng vẫn có hai task | Hai Job không cùng CronJob, chạy thủ công hoặc đường kích hoạt khác | Kiểm tra nguồn tạo Job, chính sách retry và khóa dùng chung |
| Metadata `END_TIME` trống | Process còn chạy hoặc chết trước khi ghi kết thúc | Đối chiếu pod/PID, log và dữ liệu nghiệp vụ, không kết luận chỉ từ SQL |
| Không chạy chồng nhưng kết quả vẫn bị trùng | Cùng business key được chạy lại tuần tự | Bổ sung idempotency, unique constraint, quy trình đối soát |

### Quy trình xử lý khi bị từ chối do khóa

1. **Tìm task đang giữ khóa:** kiểm tra log, hạ tầng và metadata theo `taskName` / thời điểm.
2. **Đánh giá nguyên nhân:** đây là lần lịch chạy trùng hợp lệ, do admin chạy tay, retry tự động hay process cũ bị kẹt?
3. **Chọn hành động:** bỏ qua lần đến sau, đưa vào hàng đợi, hẹn retry có backoff hoặc dừng điều phối mới; không retry tức thì vô hạn.
4. **Kiểm tra trạng thái nghiệp vụ:** lần chạy trước có ghi dữ liệu chưa? Nếu đã hoàn tất, xử lý yêu cầu trùng theo business key.
5. **Phục hồi khóa khi cần:** chỉ khi đã xác minh chủ sở hữu và quy trình lease/TTL, tránh sửa trực tiếp bảng SQL thiếu kiểm soát.
6. **Ghi nhận sự kiện:** log lý do từ chối, task name, execution ID nếu có, job/pod ID, business key an toàn và quyết định xử lý.

## 12. Checklist thiết kế an toàn

Trước khi triển khai production:

- [ ] Đã xác định **đơn vị không được chạy chồng**: toàn task, từng tenant, từng ngày hay từng bản ghi.
- [ ] Biết những nguồn có thể kích hoạt task: scheduler, API, chạy tay, retry, orchestrator.
- [ ] Có **một chính sách cạnh tranh rõ ràng**: từ chối, bỏ qua, xếp hàng, thay thế hay chạy song song có kiểm soát.
- [ ] Nếu dùng single-instance, mọi process cần kiểm soát cùng tên task, cùng cấu hình bật khóa và **cùng kho JDBC**.
- [ ] Đã chuẩn bị schema `TASK_LOCK` và dependency Spring Integration tương thích, quản lý bảng qua migration.
- [ ] TTL, timeout tác vụ, thời gian dừng graceful và phục hồi stale lock được kiểm tra bằng thử nghiệm.
- [ ] Có **business key** và idempotency/ràng buộc duy nhất ở hệ thống lưu kết quả.
- [ ] Có chính sách retry với backoff và điều kiện dừng, không tạo bão khởi chạy.
- [ ] Log chứa task name, execution ID khi có, nguồn kích hoạt và tham số nghiệp vụ không nhạy cảm.
- [ ] Giám sát đồng thời TaskRepository, trạng thái pod/process và kết quả nghiệp vụ thật.
- [ ] Nếu dùng Spring Batch, đã đối chiếu cơ chế khóa task với nhận diện JobInstance/JobExecution.
- [ ] Có kịch bản thử hai lần chạy đồng thời, chạy tuần tự cùng tham số, process bị dừng và timeout.

## 13. Ghi nhớ

**Có nhiều `TaskExecution` cùng `taskName` là bình thường; nguy hiểm xuất hiện khi chúng cùng thao tác lên tài nguyên không được thiết kế cho truy cập đồng thời.** Spring Cloud Task lưu lịch sử thực thi, còn cơ chế `single-instance-enabled` giúp từ chối lần chạy cạnh tranh **cùng tên** khi được bật và cấu hình chung một kho khóa. Kubernetes CronJob `Forbid` chỉ chặn chồng lấn **trong cùng CronJob**.

Để vận hành an toàn, luôn trả lời cả hai câu hỏi: **có cho chạy chồng không?** và **chạy lại cùng một công việc có tạo tác động trùng không?** Khóa theo tên chỉ xử lý câu đầu; business key, idempotency và ràng buộc dữ liệu giúp xử lý câu sau. Kết hợp metadata TaskRepository, giám sát hạ tầng và chính sách retry sẽ giúp các ứng dụng Spring Cloud Task hữu hạn hoạt động ổn định theo lịch hoặc theo yêu cầu.

### Tài liệu tham khảo

- [Spring Cloud Task Reference — Restricting Spring Cloud Task Instances](https://docs.spring.io/spring-cloud-task/reference/features.html#restricting-spring-cloud-task-instances)
- [Spring Cloud Task Reference Guide — Task Lock Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Cloud configuration properties — Task single-instance](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
- [Kubernetes — CronJob concurrency policy](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/#concurrency-policy)
