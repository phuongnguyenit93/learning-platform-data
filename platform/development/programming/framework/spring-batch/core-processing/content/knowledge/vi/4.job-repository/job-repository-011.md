# Dọn metadata cũ và retention trong Spring Batch

Spring Batch lưu lịch sử thực thi của Job và Step trong cơ sở dữ liệu thông qua **JobRepository**. Metadata này cho phép ứng dụng biết một Job đã chạy lúc nào, Step nào đã hoàn tất, lần chạy nào thất bại và cần khôi phục checkpoint ở đâu khi restart.

Theo thời gian, các bảng metadata có thể tăng lên đáng kể, đặc biệt với hệ thống chạy nhiều Job theo lịch hoặc xử lý nhiều lô nhỏ mỗi ngày. Vì vậy, ứng dụng cần một chính sách **retention**: xác định metadata nào phải giữ, giữ trong bao lâu, khi nào được phép xóa và cách dọn dữ liệu an toàn.

Dọn metadata là công việc vận hành có ảnh hưởng trực tiếp đến khả năng restart và tra cứu lịch sử. Nếu xóa quá sớm, Job có thể mất thông tin cần để tiếp tục; nếu xóa không đúng thứ tự, có thể vi phạm quan hệ giữa các bảng hoặc để lại dữ liệu mồ côi.

## 1. Vì sao cần retention cho JobRepository?

Mỗi lần khởi chạy Job, Spring Batch ghi thêm metadata. Với một hệ thống chạy liên tục, dữ liệu có thể tăng theo số lần chạy, số Step và số item được xử lý.

Metadata được dùng cho nhiều mục đích:

- Xác định JobInstance theo tên Job và identifying JobParameters.
- Ghi lại từng JobExecution và StepExecution.
- Theo dõi trạng thái như COMPLETED, FAILED, STOPPED hoặc STARTED.
- Lưu thời điểm bắt đầu, kết thúc và các bộ đếm đọc, ghi, skip, commit, rollback.
- Lưu ExecutionContext để reader, writer hoặc thành phần tùy chỉnh khôi phục trạng thái.
- Tra cứu lịch sử để vận hành, điều tra lỗi và đối soát.

Khi metadata tăng không kiểm soát, hệ thống có thể gặp các vấn đề:

- Các bảng BATCH_* chiếm nhiều dung lượng lưu trữ.
- Truy vấn lịch sử, dashboard và công cụ vận hành chậm hơn.
- Backup, restore, replication hoặc bảo trì database tốn thêm thời gian.
- Các bảng context có thể tăng nhanh nếu Job lưu nhiều trạng thái.
- Dữ liệu metadata cũ gây khó khăn khi quản lý vòng đời và yêu cầu lưu trữ.

Retention giúp giới hạn phần lịch sử cần giữ trong cơ sở dữ liệu vận hành. Mục tiêu là giữ đủ dữ liệu cho restart, hỗ trợ vận hành và yêu cầu kiểm toán, sau đó dọn các execution đã hết thời hạn sử dụng.

Cần phân biệt **metadata của Spring Batch** với **dữ liệu nghiệp vụ do Job tạo ra**. Xóa lịch sử thực thi không đồng nghĩa với xóa đơn hàng, báo cáo, file đầu ra hoặc dữ liệu đã nhập. Hai loại dữ liệu cần chính sách lưu trữ riêng.

## 2. JobRepository lưu những loại metadata nào?

JobRepository là thành phần trung tâm để Spring Batch lưu và truy xuất metadata. Với cấu hình JDBC phổ biến, các bảng có tiền tố `BATCH_` được sử dụng.

Các bảng chính thường gặp:

| Bảng | Nội dung |
|---|---|
| `BATCH_JOB_INSTANCE` | Các JobInstance, được xác định bởi Job name và identifying JobParameters |
| `BATCH_JOB_EXECUTION` | Mỗi lần thực thi của một JobInstance |
| `BATCH_JOB_EXECUTION_PARAMS` | Các JobParameters của một JobExecution |
| `BATCH_JOB_EXECUTION_CONTEXT` | ExecutionContext ở phạm vi JobExecution |
| `BATCH_STEP_EXECUTION` | Mỗi lần thực thi một Step |
| `BATCH_STEP_EXECUTION_CONTEXT` | ExecutionContext ở phạm vi StepExecution |

Tên bảng và cấu trúc cột có thể thay đổi theo phiên bản, database, schema hoặc table prefix mà ứng dụng cấu hình. Khi viết script retention, phải dựa trên schema thực tế đang được triển khai.

### Quan hệ giữa các bảng

Một JobInstance có thể có nhiều JobExecution. Ví dụ, lần chạy đầu thất bại, lần chạy sau restart và hoàn tất. Mỗi JobExecution có thể chứa nhiều StepExecution. Các bảng context và parameters lưu dữ liệu phụ thuộc vào execution tương ứng.

~~~mermaid
flowchart TD
    A["BATCH_JOB_INSTANCE"] --> B["BATCH_JOB_EXECUTION"]
    B --> C["BATCH_JOB_EXECUTION_PARAMS"]
    B --> D["BATCH_JOB_EXECUTION_CONTEXT"]
    B --> E["BATCH_STEP_EXECUTION"]
    E --> F["BATCH_STEP_EXECUTION_CONTEXT"]
~~~

Có thể hiểu mối quan hệ như sau:

- Một JobInstance có thể liên kết với nhiều JobExecution.
- Mỗi JobExecution có thể có nhiều StepExecution.
- JobExecution có một vùng Job ExecutionContext.
- Mỗi StepExecution có một vùng Step ExecutionContext.
- JobExecution parameters gắn với lần thực thi cụ thể.

Điểm quan trọng khi dọn dữ liệu là **không xóa một JobInstance trong khi vẫn còn execution cần giữ**. Lịch sử restart và quan hệ giữa các bảng phải được xem như một nhóm dữ liệu thống nhất.

### JobInstance và JobExecution khác nhau thế nào khi retention?

Giả sử Job `dailyImportJob` chạy với tham số nhận diện `businessDate=2026-11-01`:

1. Lần chạy đầu tạo một JobInstance và một JobExecution.
2. JobExecution thất bại sau khi Step nhập dữ liệu đã commit một số chunk.
3. Job được restart với cùng identifying JobParameters, tạo JobExecution mới thuộc JobInstance đó.
4. Lần chạy mới hoàn tất và có thêm các StepExecution tương ứng.

Nếu chỉ xóa JobExecution thất bại mà không xem xét JobInstance và execution hoàn tất, lịch sử của cùng một lần xử lý logic sẽ bị chia cắt. Nếu xóa toàn bộ JobInstance, ứng dụng không còn metadata để restart hoặc tra cứu các execution thuộc instance đó.

Vì vậy, retention thường chọn và xóa theo **nhóm JobInstance**, sau khi tất cả execution của instance đều đủ điều kiện được dọn.

## 3. Phân loại trạng thái trước khi dọn

Không phải mọi execution cũ đều có thể xóa ngay. Cần xem trạng thái và thời điểm kết thúc của từng execution.

| Trạng thái | Ý nghĩa vận hành | Cách xử lý trong retention |
|---|---|---|
| COMPLETED | Execution đã hoàn tất | Có thể đưa vào retention sau thời hạn lưu |
| FAILED | Execution thất bại | Giữ trong khoảng thời gian cho phép điều tra hoặc restart |
| STOPPED | Execution đã dừng | Giữ nếu còn khả năng restart hoặc cần điều tra |
| ABANDONED | Execution được đánh dấu không tiếp tục | Có thể dọn theo chính sách sau thời hạn lưu |
| STARTING / STARTED | Execution đang khởi động hoặc chạy | Không đưa vào danh sách xóa |
| STOPPING | Execution đang trong quá trình dừng | Không đưa vào danh sách xóa |
| UNKNOWN | Không xác định được trạng thái đáng tin cậy | Giữ lại để điều tra |

FAILED và STOPPED thường vẫn có ý nghĩa với khả năng restart. Một execution thất bại hôm nay có thể được đội vận hành khởi động lại vào ngày mai. Vì vậy, không nên đặt quy tắc đơn giản rằng cứ FAILED là xóa.

Có thể thiết kế thời hạn khác nhau theo trạng thái:

- COMPLETED: giữ 30, 60 hoặc 90 ngày tùy yêu cầu vận hành.
- FAILED: giữ lâu hơn để điều tra và restart, ví dụ 90 hoặc 180 ngày.
- STOPPED: giữ theo thời hạn tương tự FAILED hoặc theo quy trình dừng của hệ thống.
- ABANDONED: giữ đủ lâu cho audit rồi mới dọn.
- STARTED hoặc trạng thái không xác định: không tự động xóa.

Các con số trên chỉ là ví dụ. Thời hạn thực tế phải dựa trên thời gian cho phép restart, yêu cầu kiểm toán, quy định lưu trữ và khả năng lưu trữ của hệ thống.

### Điều kiện tối thiểu để một JobInstance đủ điều kiện

Một JobInstance chỉ nên được đưa vào danh sách purge khi thỏa tất cả điều kiện đã định nghĩa, chẳng hạn:

1. Job name nằm trong danh sách được phép dọn.
2. JobInstance có ít nhất một JobExecution.
3. Mọi JobExecution của instance đều đã kết thúc.
4. Mọi execution đều có trạng thái được chính sách retention cho phép.
5. Thời điểm kết thúc của mọi execution đã cũ hơn cutoff tương ứng.
6. Không còn yêu cầu restart, điều tra hoặc audit cần metadata đó.
7. Không có quy trình vận hành đang sử dụng instance để đối soát hoặc khôi phục.

Dùng điều kiện trên toàn bộ JobExecution của JobInstance giúp tránh xóa một phần lịch sử. Nếu một instance có execution cũ đã FAILED nhưng execution mới hơn vẫn đang chạy, cả instance phải được giữ.

## 4. Thiết kế chính sách retention

Một chính sách retention tốt cần trả lời được bốn câu hỏi: dọn Job nào, dọn dữ liệu nào, giữ trong bao lâu và ai chịu trách nhiệm vận hành.

### Retention theo Job name

Không phải Job nào cũng có cùng vòng đời dữ liệu. Ví dụ:

| Nhóm Job | Chính sách tham khảo |
|---|---|
| Job nhập dữ liệu hàng ngày | Giữ metadata hoàn tất 60 ngày |
| Job đối soát tài chính | Giữ theo yêu cầu kiểm toán, có thể lâu hơn |
| Job tạo báo cáo tạm | Giữ metadata trong thời hạn ngắn hơn |
| Job xử lý lỗi cần restart | Giữ FAILED và STOPPED đến hết cửa sổ restart |
| Job chạy một lần để migration | Giữ lịch sử theo chính sách phát hành và audit |

Không nên áp dụng một khoảng thời gian duy nhất cho toàn bộ Job nếu yêu cầu nghiệp vụ khác nhau.

### Retention theo thời điểm kết thúc

Đối với execution đã hoàn tất, thời điểm kết thúc thường là cơ sở phù hợp để tính tuổi dữ liệu. Ví dụ, giữ metadata hoàn tất 90 ngày:

~~~text
cutoff = thời điểm hiện tại - 90 ngày

đủ điều kiện khi:
    end_time < cutoff
    và status thuộc nhóm được phép dọn
~~~

Không nên chỉ dựa vào create_time. Một JobExecution có thể bắt đầu từ lâu nhưng chạy nhiều giờ hoặc nhiều ngày; xóa theo create_time có thể xóa một execution chưa kết thúc.

Execution không có end_time phải được giữ lại để kiểm tra. Với trạng thái STARTED lâu bất thường, hãy xác minh tiến trình, host và tình trạng database trước khi xử lý.

### Retention theo số lượng hoặc dung lượng

Ngoài thời hạn, hệ thống có thể đặt ngưỡng số lượng execution hoặc dung lượng metadata. Ví dụ, chỉ giữ 100 lần chạy gần nhất của một Job sau khi đã đáp ứng thời hạn tối thiểu.

Cần thận trọng với cách này:

- Không xóa execution đang chạy chỉ vì vượt ngưỡng số lượng.
- Không xóa execution thất bại còn trong cửa sổ restart.
- Không xóa một execution riêng lẻ nếu nó thuộc JobInstance vẫn cần giữ.
- Luôn áp dụng thời hạn tối thiểu trước khi áp dụng giới hạn số lượng.

### Lưu trữ trước khi xóa

Nếu cần giữ lịch sử lâu dài, có thể archive metadata trước khi purge khỏi database vận hành. Archive có thể là database lịch sử, bảng audit riêng hoặc file export có kiểm soát quyền truy cập.

Archive nên giữ tối thiểu:

- Job name và JobInstance ID.
- JobExecution ID, trạng thái và thời điểm bắt đầu/kết thúc.
- JobParameters đã được làm sạch dữ liệu nhạy cảm.
- StepExecution và các bộ đếm cần cho audit.
- ExitStatus và thông tin lỗi cần tra cứu.
- Mã tham chiếu đến dữ liệu nghiệp vụ hoặc báo cáo liên quan.

Không phải lúc nào cũng cần archive toàn bộ ExecutionContext. Context có thể chứa trạng thái nội bộ, dữ liệu nhạy cảm hoặc đối tượng đã serialize phụ thuộc phiên bản ứng dụng. Chỉ archive những trường thật sự có giá trị cho audit và điều tra.

## 5. Hệ quả khi xóa metadata

Dọn metadata có tác động đến khả năng vận hành của Spring Batch. Trước khi thiết kế retention, cần hiểu các hệ quả sau.

### Không thể restart JobInstance đã bị xóa

Spring Batch dựa vào JobRepository để tìm JobInstance và các execution trước đó. Khi metadata của JobInstance bị xóa, framework không còn lịch sử để tiếp tục instance cũ.

Nếu Job được khởi chạy lại với cùng identifying JobParameters sau khi metadata đã bị xóa, hệ thống có thể tạo một JobInstance mới. Job có thể xử lý lại dữ liệu nghiệp vụ đã được xử lý trước đó.

Do đó, cần thiết kế dữ liệu đầu ra theo hướng idempotent hoặc có khóa nghiệp vụ để tránh tạo dữ liệu trùng khi chạy lại cùng lô.

### Mất lịch sử trong công cụ vận hành

Các màn hình hoặc API tra cứu dựa trên JobExplorer và JobRepository sẽ không còn trả về execution đã bị purge. Nếu đội vận hành cần tra cứu lịch sử dài hạn, hãy archive trước khi xóa.

### Không xóa dữ liệu nghiệp vụ một cách mặc định

Metadata của Spring Batch và dữ liệu nghiệp vụ có vòng đời khác nhau. Ví dụ:

- BATCH_JOB_EXECUTION lưu lịch sử một lần chạy.
- Bảng CUSTOMER lưu dữ liệu khách hàng được nhập.
- Bảng IMPORT_AUDIT có thể lưu mã lô, số bản ghi và kết quả đối soát.
- File output có thể được lưu trong object storage.

Purge metadata không nên tự động xóa các bảng hoặc file nghiệp vụ. Nếu dữ liệu nghiệp vụ cũng cần retention, hãy thiết kế một quy trình riêng với khóa tham chiếu và yêu cầu lưu trữ của chính dữ liệu đó.

### Xem xét dữ liệu nhạy cảm

JobParameters và ExecutionContext có thể chứa đường dẫn file, mã khách hàng, token hoặc thông tin khác tùy cách ứng dụng sử dụng. Không nên lưu mật khẩu hoặc secret trong metadata. Khi cần xóa dữ liệu nhạy cảm theo yêu cầu, cần xác định dữ liệu nằm trong bảng nào, archive nào và log nào; retention tổng thể phải đáp ứng yêu cầu bảo mật tương ứng.

## 6. Thứ tự xóa metadata an toàn

Khi schema có ràng buộc khóa ngoại, phải xóa bản ghi con trước bản ghi cha. Ngay cả khi schema hiện tại không khai báo foreign key, thứ tự này vẫn giúp giữ tính nhất quán và tránh dữ liệu mồ côi.

Với các bảng chuẩn thường gặp, thứ tự logic là:

1. `BATCH_STEP_EXECUTION_CONTEXT` — context của từng StepExecution.
2. `BATCH_STEP_EXECUTION` — các lần thực thi Step.
3. `BATCH_JOB_EXECUTION_CONTEXT` — context của từng JobExecution.
4. `BATCH_JOB_EXECUTION_PARAMS` — tham số của từng JobExecution.
5. `BATCH_JOB_EXECUTION` — các lần thực thi Job.
6. `BATCH_JOB_INSTANCE` — JobInstance sau cùng.

~~~mermaid
flowchart TD
    A["Chọn JobInstance đủ điều kiện"] --> B["Xóa Step ExecutionContext"]
    B --> C["Xóa StepExecution"]
    C --> D["Xóa Job ExecutionContext"]
    D --> E["Xóa JobExecutionParams"]
    E --> F["Xóa JobExecution"]
    F --> G["Xóa JobInstance"]
    G --> H["Ghi audit và số lượng đã dọn"]
~~~

Thứ tự trên áp dụng cho các bảng metadata chuẩn. Nếu ứng dụng có bảng tùy chỉnh tham chiếu đến JobExecution ID, StepExecution ID hoặc JobInstance ID, phải xác định và xử lý các bảng đó theo quan hệ thực tế. Không được xóa bản ghi cha khi còn bản ghi con phụ thuộc.

Các bảng sequence hoặc generator dùng để cấp ID thường không cần xóa theo từng JobInstance. Không đặt lại sequence về giá trị thấp hơn vì có thể gây trùng ID với dữ liệu còn tồn tại.

## 7. Xác định tập JobInstance đủ điều kiện

Bước quan trọng nhất của quy trình retention là xác định candidate chính xác. Không nên bắt đầu bằng lệnh DELETE trực tiếp trên một bảng execution.

Một candidate nên được xác định ở cấp JobInstance, sau đó mới xóa tất cả execution và dữ liệu con liên quan.

Ví dụ điều kiện logic:

~~~sql
SELECT ji.JOB_INSTANCE_ID
FROM BATCH_JOB_INSTANCE ji
WHERE ji.JOB_NAME = :jobName
  AND EXISTS (
      SELECT 1
      FROM BATCH_JOB_EXECUTION je
      WHERE je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
  )
  AND NOT EXISTS (
      SELECT 1
      FROM BATCH_JOB_EXECUTION je
      WHERE je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
        AND (
            je.END_TIME IS NULL
            OR je.END_TIME >= :cutoff
            OR je.STATUS NOT IN (:allowedTerminalStatuses)
        )
  );
~~~

Đây là ví dụ mô tả điều kiện chọn candidate; cú pháp binding danh sách trạng thái phụ thuộc JDBC framework và database đang dùng.

Ý nghĩa:

- Chỉ xét Job name được chỉ định.
- JobInstance phải có execution.
- Nếu bất kỳ execution nào chưa kết thúc, còn mới hơn cutoff hoặc có trạng thái không được phép dọn, JobInstance không đủ điều kiện.
- Chỉ khi tất cả execution đều thỏa chính sách thì instance mới được đưa vào danh sách purge.

Trong thực tế, chính sách có thể cần nhiều cutoff khác nhau cho COMPLETED, FAILED, STOPPED và ABANDONED. Khi đó, điều kiện candidate cần đánh giá tuổi và trạng thái của từng execution theo đúng quy tắc thay vì dùng một danh sách trạng thái chung.

### Vì sao phải giữ execution chưa kết thúc?

Một execution có END_TIME là NULL có thể đang chạy hoặc đã gặp sự cố khiến metadata chưa được cập nhật hoàn chỉnh. Xóa nó có thể làm hỏng trạng thái vận hành hoặc xóa metadata mà một tiến trình khác vẫn đang sử dụng.

Không nên kết luận một execution bị treo chỉ vì thời gian START_TIME đã cũ. Hãy kiểm tra tiến trình thực tế, heartbeat, log ứng dụng và trạng thái lock của database. Nếu cần dừng hoặc abandon execution, hãy dùng quy trình vận hành có kiểm soát trước khi xét retention.

## 8. Ví dụ quy trình SQL purge

Ví dụ dưới đây minh họa cách dùng một bảng candidate tạm hoặc staging table để giữ danh sách JobInstance đã được phê duyệt. Cách tạo bảng tạm và cú pháp transaction phụ thuộc database; hãy điều chỉnh theo hệ quản trị đang sử dụng.

Giả sử bảng staging `PURGE_JOB_INSTANCE` chứa các `JOB_INSTANCE_ID` đã được chọn theo chính sách ở phần trước và chỉ tồn tại trong phạm vi một lần chạy maintenance.

~~~sql
-- 1. Xóa StepExecutionContext trước.
DELETE FROM BATCH_STEP_EXECUTION_CONTEXT
WHERE STEP_EXECUTION_ID IN (
    SELECT se.STEP_EXECUTION_ID
    FROM BATCH_STEP_EXECUTION se
    JOIN BATCH_JOB_EXECUTION je
      ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 2. Xóa StepExecution.
DELETE FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID IN (
    SELECT je.JOB_EXECUTION_ID
    FROM BATCH_JOB_EXECUTION je
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 3. Xóa JobExecutionContext.
DELETE FROM BATCH_JOB_EXECUTION_CONTEXT
WHERE JOB_EXECUTION_ID IN (
    SELECT je.JOB_EXECUTION_ID
    FROM BATCH_JOB_EXECUTION je
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 4. Xóa JobExecution parameters.
DELETE FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID IN (
    SELECT je.JOB_EXECUTION_ID
    FROM BATCH_JOB_EXECUTION je
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 5. Xóa JobExecution.
DELETE FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID IN (
    SELECT JOB_INSTANCE_ID
    FROM PURGE_JOB_INSTANCE
);

-- 6. Xóa JobInstance sau cùng.
DELETE FROM BATCH_JOB_INSTANCE
WHERE JOB_INSTANCE_ID IN (
    SELECT JOB_INSTANCE_ID
    FROM PURGE_JOB_INSTANCE
);
~~~

Đây là mẫu SQL minh họa theo tên bảng chuẩn, không phải script có thể chạy nguyên trạng trên mọi database. Cần xác nhận schema, kiểu dữ liệu, table prefix, tên cột và các foreign key của phiên bản Spring Batch đang triển khai. Một số hệ thống còn có bảng tùy chỉnh tham chiếu đến metadata; các bảng đó phải được xử lý trước khi xóa bản ghi cha.

### Transaction và batch size

Nếu purge hàng triệu execution trong một transaction lớn, transaction log có thể tăng mạnh, lock kéo dài và rollback trở nên tốn kém.

Có thể chia công việc thành từng nhóm JobInstance:

1. Chọn một batch candidate nhỏ.
2. Xóa các bảng con theo đúng thứ tự.
3. Xóa JobExecution và JobInstance.
4. Ghi nhận số lượng đã xử lý.
5. Commit transaction.
6. Lặp lại cho batch tiếp theo.

Kích thước batch phụ thuộc database, dung lượng metadata và thời gian lock chấp nhận được. Hãy đo trên bản sao dữ liệu đại diện trước khi áp dụng ở production.

Nếu cần bảo đảm tất cả bảng của một candidate được xóa nguyên tử, giữ các thao tác của candidate trong cùng transaction. Nếu chia nhỏ theo nhóm candidate, mỗi nhóm có thể là một đơn vị transaction độc lập.

### Không dựa vào ON DELETE CASCADE khi chưa xác nhận

Một số schema có thể khai báo foreign key với cascade, một số schema khác không có hoặc được tùy chỉnh. Không nên giả định xóa JobInstance sẽ tự động xóa toàn bộ dữ liệu liên quan.

Hãy kiểm tra DDL thực tế. Nếu dùng cascade, vẫn phải hiểu rõ các bảng tùy chỉnh có bị xóa theo hay không và việc xóa có ảnh hưởng đến dữ liệu audit cần giữ không.

## 9. Các API Spring Batch liên quan đến metadata

Spring Batch cung cấp nhiều API để tra cứu và vận hành Job. Cần phân biệt chức năng của chúng khi xây dựng retention.

### JobRepository

`JobRepository` là nơi lưu metadata của Job và Step. Framework sử dụng nó trong quá trình tạo execution, cập nhật trạng thái và lưu ExecutionContext.

JobRepository không phải là một API retention tổng quát để xóa lịch sử JobInstance theo thời hạn. Không nên tìm cách gọi các phương thức nội bộ của DAO hoặc repository implementation để xóa tùy tiện.

Nếu cần purge, ứng dụng thường triển khai quy trình maintenance riêng bằng JDBC hoặc công cụ quản trị database, dựa trên schema và chính sách đã xác định.

### JobExplorer

`JobExplorer` cung cấp cách đọc thông tin JobInstance, JobExecution và StepExecution đã lưu. Nó hữu ích để:

- Tra cứu lịch sử thực thi.
- Tìm Job đang chạy.
- Đọc JobParameters và ExecutionContext.
- Xem trạng thái và thống kê của Step.
- Hỗ trợ dashboard hoặc công cụ vận hành.

JobExplorer là API tra cứu, không phải API xóa metadata. Có thể dùng nó để phục vụ màn hình hoặc bước xác minh trước khi purge, nhưng không nên nhầm việc đọc được execution với quyền xóa execution.

### JobOperator

`JobOperator` cung cấp các thao tác vận hành như start, restart, stop hoặc abandon JobExecution tùy cấu hình và phiên bản. Đây là công cụ để điều khiển vòng đời Job.

JobOperator không thay thế chính sách retention. Ví dụ, abandon một execution là một quyết định vận hành về khả năng tiếp tục execution đó; nó không có nghĩa metadata được xóa hoặc đã hết thời hạn lưu.

### JDBC và dịch vụ retention riêng

Một dịch vụ retention có thể dùng JdbcTemplate hoặc JDBC thuần để:

- Tính cutoff.
- Chọn candidate theo Job name và trạng thái.
- Kiểm tra quan hệ execution.
- Archive nếu cần.
- Xóa dữ liệu con và cha theo thứ tự.
- Ghi audit và metrics.

Dịch vụ này cần chạy trên đúng datasource chứa JobRepository metadata và dùng transaction manager phù hợp. Không nên chạy script bằng datasource nghiệp vụ khác rồi giả định nó đang thao tác cùng database metadata.

## 10. Tổ chức maintenance thành một Job riêng

Với hệ thống Spring Batch lớn, có thể xây dựng một Job riêng để dọn metadata. Việc dùng Job riêng giúp theo dõi lần chạy maintenance, cấu hình lịch, ghi log và áp dụng cơ chế retry hoặc giám sát thống nhất.

Ví dụ một Tasklet gọi dịch vụ retention:

~~~java
@Bean
Tasklet purgeBatchMetadataTasklet(
        MetadataRetentionService retentionService) {

    return (contribution, chunkContext) -> {
        RetentionResult result = retentionService.purgeEligibleInstances();

        contribution.incrementWriteCount(result.deletedJobInstances());

        return RepeatStatus.FINISHED;
    };
}

@Bean
Step purgeBatchMetadataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet purgeBatchMetadataTasklet) {

    return new StepBuilder("purgeBatchMetadataStep", jobRepository)
        .tasklet(purgeBatchMetadataTasklet, transactionManager)
        .build();
}

@Bean
Job purgeBatchMetadataJob(
        JobRepository jobRepository,
        Step purgeBatchMetadataStep) {

    return new JobBuilder("purgeBatchMetadataJob", jobRepository)
        .start(purgeBatchMetadataStep)
        .build();
}
~~~

Ví dụ tập trung vào cách tổ chức Job và Step. Phần chọn candidate, archive, transaction và xóa các bảng phải được triển khai trong `MetadataRetentionService` theo schema thật.

Cần lưu ý Job maintenance cũng có metadata của chính nó. Khi đang chạy, JobExecution của maintenance chưa có END_TIME và phải được retention bảo vệ. Không được chọn instance của chính Job đang thực thi làm candidate. Có thể giới hạn danh sách Job name được dọn hoặc loại trừ Job maintenance rõ ràng.

Nếu dịch vụ purge dùng transaction riêng hoặc commit theo từng batch, không nên giả định toàn bộ thao tác được bao bởi transaction của Tasklet. Hãy cấu hình transaction boundary có chủ đích để tránh báo cáo một kết quả hoàn tất khi một phần purge vẫn chưa được commit.

### Lịch chạy maintenance

Có thể chạy Job retention ngoài giờ cao điểm hoặc theo lịch tuần. Tần suất phụ thuộc tốc độ tăng metadata và yêu cầu lưu trữ.

Một số nguyên tắc:

- Không chạy nhiều instance purge đồng thời trên cùng một schema nếu chưa có cơ chế khóa.
- Dùng identifying JobParameters phù hợp để kiểm soát từng lần chạy maintenance.
- Ghi lại cutoff, danh sách Job được xét và số lượng candidate.
- Đặt giới hạn số candidate cho mỗi lần chạy.
- Có khả năng tiếp tục sau lỗi mà không xóa trùng hoặc bỏ sót.
- Giám sát thời gian chạy, số hàng xóa và dung lượng database.

## 11. Kiểm soát chạy đồng thời và execution bị treo

Một trong những rủi ro lớn nhất của retention là chọn candidate trong khi Job khác vẫn đang chạy hoặc vừa được khởi chạy.

Ví dụ, maintenance đọc metadata và thấy một JobExecution cũ. Nếu ứng dụng khác đang restart JobInstance đó, retention có thể xóa dữ liệu đúng lúc framework cần đọc checkpoint.

Một số biện pháp kiểm soát:

- Chỉ chọn execution đã kết thúc và đủ thời hạn lưu.
- Giữ FAILED và STOPPED trong cửa sổ restart.
- Không dọn JobInstance có bất kỳ execution nào đang hoạt động.
- Chạy maintenance với một cơ chế lock hoặc singleton phù hợp.
- Giới hạn candidate và thực hiện purge theo batch nhỏ.
- Nếu có thể, dùng transaction isolation và khóa phù hợp với database để giảm race condition.
- Không cho phép nhiều tiến trình retention chạy chồng lấn trên cùng tập dữ liệu.

### Execution có STARTED quá lâu

Một execution có START_TIME rất cũ nhưng không có END_TIME có thể do:

- Ứng dụng bị tắt đột ngột.
- Máy chủ hoặc container bị mất kết nối.
- Tiến trình chết trước khi cập nhật trạng thái.
- Có một execution thực sự đang chạy lâu.
- Có lỗi hoặc sự cố khiến metadata ở trạng thái không nhất quán.

Không nên dùng điều kiện `START_TIME < cutoff` để tự động xóa các execution này.

Quy trình xử lý nên là:

1. Tra cứu JobExecution và StepExecution liên quan.
2. Kiểm tra host, process, container và log.
3. Xác nhận execution có còn hoạt động không.
4. Nếu cần, yêu cầu dừng hoặc xử lý trạng thái bằng quy trình vận hành.
5. Chỉ đưa metadata vào retention sau khi trạng thái cuối đã rõ và hết thời hạn lưu.

Không tự cập nhật status trong các bảng BATCH_* bằng SQL chỉ để làm cho candidate đủ điều kiện. Việc thay đổi trạng thái trực tiếp có thể khiến metadata không phản ánh đúng thực tế của Job.

## 12. Archive, backup và audit

Retention không nhất thiết có nghĩa là dữ liệu biến mất hoàn toàn. Với hệ thống có yêu cầu truy vết dài hạn, có thể chuyển metadata sang vùng lưu trữ lịch sử trước khi purge.

Một quy trình archive có thể gồm:

1. Chọn JobInstance đủ điều kiện.
2. Đọc toàn bộ JobExecution và StepExecution liên quan.
3. Tạo bản ghi archive hoặc file export.
4. Ghi checksum hoặc mã phiên bản archive.
5. Xác nhận archive có thể đọc lại.
6. Ghi audit về số lượng instance và execution đã archive.
7. Chỉ sau đó mới purge metadata trong database vận hành.

Archive cần bảo toàn quan hệ giữa JobInstance, JobExecution và StepExecution để khi tra cứu có thể hiểu lịch sử của một lần xử lý logic.

Không nên archive bằng cách sao chép tùy tiện các bảng BATCH_* rồi cho rằng có thể khôi phục nguyên trạng vào một database khác. Việc restore metadata có thể phụ thuộc schema version, sequence, kiểu dữ liệu context đã serialize và cấu hình ứng dụng. Nếu cần khả năng khôi phục, hãy thiết kế và thử nghiệm quy trình restore rõ ràng.

Backup database trước một đợt purge lớn cũng là một biện pháp bảo vệ. Backup chỉ hữu ích khi đã kiểm tra khả năng restore và thời hạn lưu backup đáp ứng yêu cầu vận hành.

## 13. Hiệu năng và bảo trì database sau purge

Xóa metadata không phải lúc nào cũng làm file database trên đĩa giảm ngay. Cách database thu hồi không gian phụ thuộc hệ quản trị.

Sau một đợt purge lớn, cần theo dõi:

- Số hàng còn lại trong từng bảng BATCH_*.
- Dung lượng dữ liệu và index.
- Thời gian truy vấn JobExplorer hoặc dashboard.
- Transaction log và replication lag.
- Lock wait và thời gian transaction.
- Kế hoạch thực thi truy vấn candidate.
- Tốc độ tăng metadata sau khi áp dụng retention.

Một số database cần thao tác bảo trì riêng để cập nhật thống kê hoặc thu hồi không gian. Ví dụ, PostgreSQL có cơ chế VACUUM; SQL Server có các thao tác quản lý index và file; Oracle có các phương thức quản lý segment tương ứng. Không chạy lệnh thu hồi dung lượng theo thói quen mà không hiểu ảnh hưởng đến lock, I/O và thời gian bảo trì của hệ thống.

### Index và truy vấn candidate

Truy vấn retention thường lọc theo Job name, JobInstance ID, JobExecution ID, status và end_time. Các index mặc định của Spring Batch có thể hỗ trợ một phần truy vấn, nhưng hiệu năng phụ thuộc database, số lượng metadata và điều kiện lọc thực tế.

Trước khi thêm index:

1. Đo thời gian truy vấn candidate trên dữ liệu đại diện.
2. Xem execution plan.
3. Kiểm tra index hiện có trong schema.
4. Xác định index bổ sung có cải thiện truy vấn không.
5. Đánh giá chi phí ghi metadata khi thêm index.

Không nên thêm index trùng lặp hoặc thay đổi schema Spring Batch mà không có migration và kế hoạch tương thích.

## 14. Bảo mật và quyền thực thi purge

Dịch vụ retention có quyền xóa dữ liệu metadata nên cần được kiểm soát.

Một số nguyên tắc:

- Tài khoản database dùng cho retention chỉ có quyền cần thiết trên schema metadata.
- Không cấp quyền xóa toàn bộ schema nếu chỉ cần xóa các bảng BATCH_*.
- Tách quyền đọc candidate, archive và delete khi quy trình yêu cầu kiểm soát nhiều bước.
- Lưu audit về người hoặc tiến trình khởi chạy, thời điểm, cutoff và kết quả.
- Không ghi secret hoặc dữ liệu nhạy cảm từ JobParameters vào log.
- Yêu cầu xác nhận hoặc phê duyệt cho lần purge đầu tiên hoặc đợt purge quy mô lớn theo quy trình tổ chức.

Nếu retention chạy tự động, cấu hình cần có giới hạn an toàn. Ví dụ, không cho phép cutoff vượt quá một ngưỡng mặc định hoặc xóa quá số lượng JobInstance cho phép trong một lần chạy nếu chưa có xác nhận vận hành.

## 15. Kiểm thử quy trình retention

Trước khi áp dụng vào production, cần kiểm thử trên database thử nghiệm có schema và phiên bản Spring Batch tương ứng.

Các tình huống cần kiểm tra:

| Tình huống | Kết quả mong đợi |
|---|---|
| JobInstance chỉ có execution COMPLETED đã quá hạn | Được chọn để purge |
| JobInstance có execution COMPLETED còn mới | Được giữ |
| JobInstance có execution FAILED còn trong cửa sổ restart | Được giữ |
| JobInstance có execution STOPPED chưa hết hạn | Được giữ |
| JobInstance có execution STARTED hoặc END_TIME null | Được giữ |
| JobInstance có trạng thái UNKNOWN | Được giữ để điều tra |
| JobInstance có nhiều execution, một execution còn mới | Giữ toàn bộ instance |
| JobInstance có đủ execution terminal và đều quá hạn | Được chọn theo policy |
| Có bảng tùy chỉnh tham chiếu execution | Bản ghi phụ thuộc được xử lý đúng thứ tự |
| Purge gặp lỗi giữa transaction | Không để lại nhóm metadata ở trạng thái xóa dở nếu thiết kế yêu cầu atomicity |
| Chạy lại maintenance sau lần purge thành công | Không xóa nhầm dữ liệu mới hoặc dữ liệu không đủ điều kiện |

Cũng cần kiểm thử các hệ quả nghiệp vụ:

- Job đã hoàn tất nhưng metadata bị purge có thể được khởi chạy lại với identifying parameters cũ như một JobInstance mới.
- Writer có idempotency hoặc khóa nghiệp vụ để ngăn dữ liệu trùng.
- Dashboard và công cụ vận hành không còn hiển thị execution đã purge.
- Archive có thể tra cứu độc lập nếu hệ thống có yêu cầu lưu lịch sử.
- Job maintenance không tự chọn execution đang chạy của chính nó.

Không chỉ kiểm thử số lượng hàng đã xóa. Cần xác nhận các bảng con và cha đều nhất quán, không còn bản ghi mồ côi và các JobInstance được giữ vẫn có thể restart như mong đợi.

## 16. Quy trình vận hành đề xuất

Một quy trình retention thực tế có thể tổ chức theo các bước sau:

1. **Đọc chính sách:** xác định Job name, trạng thái được phép dọn và thời hạn lưu tương ứng.
2. **Tính cutoff:** dùng mốc thời gian rõ ràng, thống nhất múi giờ và ghi nhận giá trị cutoff.
3. **Chọn candidate:** chọn JobInstance mà mọi JobExecution đều đã kết thúc và đáp ứng retention.
4. **Bảo vệ execution hoạt động:** loại bỏ instance có execution chưa kết thúc hoặc trạng thái không rõ.
5. **Archive hoặc backup:** thực hiện nếu yêu cầu audit hoặc khôi phục cần giữ lịch sử.
6. **Kiểm tra số lượng:** ghi nhận số JobInstance, JobExecution và StepExecution dự kiến xóa.
7. **Purge theo thứ tự:** xóa context, StepExecution, parameters, JobExecution và JobInstance.
8. **Commit theo batch:** giới hạn kích thước transaction để tránh lock kéo dài.
9. **Ghi audit:** lưu cutoff, số hàng đã xóa, thời gian chạy và lỗi.
10. **Theo dõi database:** kiểm tra dung lượng, lock, transaction log và truy vấn metadata sau purge.

Có thể chạy quy trình này theo lịch hàng ngày hoặc hàng tuần. Tần suất nên dựa trên tốc độ tăng metadata và mức độ ảnh hưởng của việc lưu trữ đến database.

## 17. Những sai lầm thường gặp

### Xóa trực tiếp các JobExecution cũ

Một JobInstance có thể có nhiều JobExecution do restart. Xóa từng execution mà không xét toàn bộ instance có thể làm mất quan hệ lịch sử và tạo metadata không nhất quán. Hãy chọn và dọn theo nhóm JobInstance.

### Chỉ kiểm tra START_TIME

Một Job chạy lâu có thể bắt đầu từ trước cutoff nhưng vẫn đang hoạt động. Dùng END_TIME và trạng thái terminal làm điều kiện chính; execution chưa kết thúc phải được giữ.

### Xóa FAILED ngay sau khi thất bại

FAILED có thể là trạng thái cần restart. Hãy giữ đủ thời gian cho điều tra và khôi phục, hoặc chỉ purge sau khi execution được xử lý theo chính sách vận hành.

### Chỉ xóa bảng cha

Xóa JobInstance hoặc JobExecution khi các bảng context, parameters và StepExecution vẫn còn có thể gây lỗi foreign key hoặc dữ liệu mồ côi. Luôn xác định quan hệ và xóa bản ghi con trước.

### Dựa vào cascade mà không kiểm tra schema

Không phải mọi schema Spring Batch đều có cùng foreign key hoặc cascade. Kiểm tra DDL thực tế trước khi triển khai script.

### Coi metadata là dữ liệu nghiệp vụ

Purge BATCH_* không nên xóa dữ liệu đầu ra, còn giữ BATCH_* cũng không thay thế việc lưu trữ dữ liệu nghiệp vụ. Hai chính sách phải độc lập.

### Không tính đến việc chạy lại cùng JobParameters

Khi metadata bị xóa, cùng identifying JobParameters có thể tạo JobInstance mới. Nếu writer không idempotent, dữ liệu nghiệp vụ có thể bị ghi trùng.

### Chạy purge trong một transaction quá lớn

Transaction quá lớn có thể làm tăng lock, transaction log và thời gian rollback. Hãy chia candidate thành batch phù hợp và đo hiệu năng.

### Không lưu audit

Nếu không ghi cutoff, số lượng và phạm vi đã xóa, rất khó giải thích vì sao một JobInstance không còn trong dashboard hoặc truy vết một đợt purge.

## 18. Những điểm cần nhớ

- JobRepository lưu metadata cần thiết để nhận diện JobInstance, theo dõi JobExecution và StepExecution, cũng như hỗ trợ restart.
- Retention phải dựa trên Job name, trạng thái, end_time và cửa sổ restart của từng loại Job.
- Chọn candidate ở cấp JobInstance; chỉ purge khi tất cả execution liên quan đều đủ điều kiện.
- Execution đang chạy, chưa có end_time hoặc có trạng thái UNKNOWN phải được bảo vệ.
- Xóa bảng con trước bảng cha: StepExecutionContext, StepExecution, JobExecutionContext, JobExecutionParams, JobExecution và JobInstance.
- JobExplorer dùng để đọc metadata; JobOperator dùng cho thao tác vận hành; không coi chúng là API purge tổng quát.
- Khi cần xóa metadata, có thể triển khai dịch vụ JDBC hoặc maintenance Job riêng dựa trên schema thực tế.
- Archive và audit trước khi purge nếu yêu cầu vận hành hoặc kiểm toán cần giữ lịch sử.
- Purge metadata không xóa dữ liệu nghiệp vụ và có thể khiến JobInstance cũ không thể restart.
- Writer và quy trình nghiệp vụ cần idempotency phù hợp để tránh ghi trùng khi Job được chạy lại sau khi metadata đã hết hạn.
- Chạy theo batch, có kiểm soát đồng thời, kiểm thử trên schema thật và theo dõi tác động đến database.

Một chính sách retention được thiết kế đúng giúp JobRepository duy trì dung lượng hợp lý mà vẫn giữ được khả năng restart, điều tra và kiểm toán trong khoảng thời gian cần thiết.

