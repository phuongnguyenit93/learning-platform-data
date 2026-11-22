# Dọn output sau khi job failed

Trong Spring Batch, một job có thể xử lý hàng triệu bản ghi theo từng chunk. Khi một chunk lỗi, transaction của chunk hiện tại thường được rollback, nhưng các chunk đã commit trước đó vẫn còn dữ liệu. Với output là file, bản ghi trong database khác transaction, hoặc lời gọi sang hệ thống bên ngoài, kết quả dở dang cũng có thể tồn tại sau khi job chuyển sang trạng thái FAILED.

Vì vậy, dọn output sau khi job failed cần gắn với chính sách chạy lại của job. Nếu job sẽ được restart, output dở dang thường phải được giữ lại để khớp với checkpoint đã lưu. Nếu lần chạy bị loại bỏ và sẽ bắt đầu lại từ đầu, output tạm của lần chạy cũ cần được dọn có kiểm soát. Xóa file một cách máy móc ngay khi job lỗi có thể làm hỏng lần restart tiếp theo.

## 1. Hiểu trạng thái job trước khi dọn output

Spring Batch phân biệt một lần chạy logic với từng lần thực thi:

- **JobInstance** đại diện cho một lần chạy logic của job. Nó được xác định bởi tên job và các JobParameters được đánh dấu là identifying.
- **JobExecution** đại diện cho một lần thực thi cụ thể của JobInstance. Khi một JobInstance thất bại và được restart, Spring Batch tạo JobExecution mới nhưng vẫn thuộc cùng JobInstance.
- **ExecutionContext** lưu trạng thái cần thiết để tiếp tục xử lý, chẳng hạn vị trí đọc hoặc trạng thái của một ItemStream writer.

Ví dụ, job xuất báo cáo cho ngày 2026-11-15 chạy với businessDate là tham số identifying. Lần thực thi đầu tiên xử lý được ba chunk rồi thất bại. Khi restart với cùng identifying parameters, Spring Batch tiếp tục JobInstance đó bằng một JobExecution mới. Checkpoint được lưu từ lần chạy trước có thể cho biết dữ liệu đã được xử lý đến đâu.

Điều này tạo ra hai tình huống rất khác nhau:

| Tình huống | Cách xử lý output |
|---|---|
| Restart cùng JobInstance | Giữ output tạm và checkpoint tương ứng; writer phải có khả năng restart. |
| Bỏ lần chạy cũ và chạy lại từ đầu | Dọn output tạm của lần chạy cũ, sau đó tạo JobInstance mới với output tạm mới. |

Không nên xóa file đang được writer dùng để restart trong khi vẫn giữ ExecutionContext của lần chạy cũ. Checkpoint có thể trỏ đến vị trí trong file đã bị xóa hoặc thay đổi, khiến kết quả tiếp theo thiếu dữ liệu, sai vị trí ghi hoặc không thể mở writer.

## 2. Dùng output tạm và chỉ công bố khi job hoàn tất

Với output dạng file, một thiết kế an toàn là ghi vào thư mục staging. Chỉ sau khi các bước xử lý và kiểm tra hoàn tất, job mới chuyển file staging thành file chính thức.

~~~mermaid
flowchart TD
    A[Job bắt đầu] --> B[Ghi vào file staging theo JobInstance]
    B --> C{Job hoàn tất thành công?}
    C -->|Có| D[Kiểm tra output]
    D --> E[Publish file staging]
    C -->|Không| F{Có kế hoạch restart?}
    F -->|Có| G[Giữ file staging và checkpoint]
    F -->|Không| H[Xóa file staging của JobInstance]
~~~

Ví dụ, file staging có thể được đặt tên theo JobInstance:

~~~text
output/staging/job-10482.part
output/final/report-2026-11-15.csv
~~~

Sử dụng JobInstance ID giúp đường dẫn ổn định qua các lần restart của cùng một JobInstance. Không nên dùng JobExecution ID làm định danh file staging nếu muốn restart tiếp tục file cũ: mỗi lần restart có JobExecution ID mới, trong khi checkpoint vẫn thuộc cùng JobInstance.

Một bước publish riêng có thể được đặt sau bước xử lý:

~~~java
@Bean
Job reportJob(
        JobRepository jobRepository,
        Step processStep,
        Step publishOutputStep) {

    return new JobBuilder("reportJob", jobRepository)
            .start(processStep)
            .next(publishOutputStep)
            .build();
}
~~~

Với flow này, publishOutputStep chỉ chạy sau khi processStep hoàn tất thành công. Nếu bước xử lý thất bại, file staging chưa được công bố thành output chính thức. Nếu bước publish thất bại, JobInstance cũng chưa được đánh dấu hoàn tất; khi restart, Spring Batch có thể bỏ qua step đã hoàn thành và tiếp tục step publish còn lỗi.

Trong tasklet publish, có thể dùng thao tác đổi tên file trên cùng filesystem:

~~~java
Path stagingFile = stagingDirectory.resolve(stagingFileName);
Path finalFile = finalDirectory.resolve(finalFileName);

if (!Files.exists(stagingFile)) {
    throw new IllegalStateException("Staging output does not exist: " + stagingFile);
}

Files.move(stagingFile, finalFile, StandardCopyOption.ATOMIC_MOVE);
~~~

Atomic move giúp người đọc output không nhìn thấy một file chính thức mới chỉ được copy một phần. Tùy filesystem, ATOMIC_MOVE có thể không được hỗ trợ; khi đó cần chọn một phương án publish phù hợp với môi trường triển khai. Staging và final nên nằm trên cùng filesystem nếu muốn dùng atomic move. Cũng cần quy định rõ việc xử lý khi file đích đã tồn tại: từ chối ghi đè, tạo tên phiên bản mới, hoặc thay thế theo một quy trình được kiểm soát.

## 3. Khi restart: giữ output và khôi phục đúng trạng thái writer

Nếu muốn restart cùng JobInstance, đừng xóa file staging khi job thất bại. Hãy bảo đảm writer và resource được cấu hình nhất quán giữa các lần thực thi:

- Dùng cùng đường dẫn staging cho cùng JobInstance.
- Dùng tên writer ổn định và duy nhất trong step để trạng thái writer được lưu đúng trong ExecutionContext.
- Với writer hỗ trợ restart như FlatFileItemWriter, giữ cơ chế lưu trạng thái được bật và để writer khôi phục trạng thái từ ExecutionContext.
- Không tự ý xóa, truncate hoặc thay thế file staging trước khi Spring Batch mở writer để restart.
- Nếu writer không hỗ trợ restart, thiết kế output theo hướng ghi lại từ đầu một cách idempotent, hoặc dùng một staging resource mới cùng với một lần chạy logic mới.

Các chunk đã commit trước khi lỗi thường không được chạy lại như một chunk chưa commit. Vì thế, writer phải phối hợp được với checkpoint: phần output đã ghi tương ứng với phần input đã commit, và phần còn lại được ghi tiếp khi restart. Nếu tự xóa file mà không làm mới trạng thái tương ứng, hai phía sẽ mất đồng bộ.

Không phải mọi output đều được Spring Batch khôi phục tự động. Việc lưu checkpoint chỉ có tác dụng khi reader/writer tham gia đúng cơ chế ItemStream và lưu trạng thái cần thiết. Với writer tự xây dựng, cần triển khai open, update và close phù hợp, đồng thời kiểm tra hành vi khi transaction rollback và khi restart.

## 4. Khi bỏ lần chạy cũ: dọn đúng artifact của lần chạy đó

Nếu nghiệp vụ quyết định không restart JobInstance đã thất bại, có thể dọn file staging sau khi job kết thúc với trạng thái FAILED. Listener dưới đây minh họa chính sách chỉ xóa output tạm khi cấu hình cho phép bỏ lần chạy lỗi:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class FailedOutputCleanupListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(FailedOutputCleanupListener.class);

    private final Path stagingDirectory;
    private final boolean discardOutputOnFailure;

    public FailedOutputCleanupListener(
            Path stagingDirectory,
            boolean discardOutputOnFailure) {
        this.stagingDirectory = stagingDirectory;
        this.discardOutputOnFailure = discardOutputOnFailure;
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (!discardOutputOnFailure
                || jobExecution.getStatus() != BatchStatus.FAILED) {
            return;
        }

        String fileName = "job-"
                + jobExecution.getJobInstance().getInstanceId()
                + ".part";
        Path stagingFile = stagingDirectory.resolve(fileName);

        try {
            Files.deleteIfExists(stagingFile);
        } catch (IOException exception) {
            log.error(
                    "Could not delete failed job output {}",
                    stagingFile,
                    exception);
        }
    }
}
~~~

Đăng ký listener này với job và chỉ bật discardOutputOnFailure khi quy trình vận hành xác định rằng lần chạy lỗi sẽ bị loại bỏ. Nếu job cần restart, hãy tắt chính sách xóa này. Listener kiểm tra BatchStatus.FAILED để không xóa output sau một lần chạy COMPLETED. Trạng thái STOPPED cũng không bị xóa trong ví dụ vì job có thể được tiếp tục theo quy trình vận hành.

Có một điểm cần xử lý rõ: sau khi xóa output nhưng vẫn giữ metadata và checkpoint của JobInstance cũ, không được restart JobInstance đó như thể file còn nguyên. Hãy tạo JobInstance mới bằng một identifying parameter mới, đồng thời dùng staging path mới. Nếu nghiệp vụ bắt buộc chạy lại cùng định danh, cần có quy trình reset cả output lẫn trạng thái liên quan trong JobRepository; không tự xóa dữ liệu metadata bằng SQL tùy tiện.

Việc xóa có thể thất bại do quyền truy cập, file đang bị process khác giữ, hoặc lỗi filesystem. Vì afterJob chạy khi job đã kết thúc, lỗi dọn file cần được ghi log và đưa vào giám sát để xử lý artifact còn sót. Thao tác deleteIfExists có tính idempotent: gọi lại khi file đã không còn sẽ không gây lỗi.

## 5. Dọn output trong database

Với database, cần phân biệt transaction của từng chunk với toàn bộ vòng đời job. Nếu writer dùng cùng transaction manager và cùng transaction với chunk, dữ liệu của chunk đang lỗi sẽ được rollback. Tuy nhiên, những chunk đã commit trước đó vẫn tồn tại dù JobExecution cuối cùng có trạng thái FAILED.

Một cách dễ quản lý là ghi dữ liệu vào bảng staging cùng một mã lần chạy:

~~~sql
CREATE TABLE report_output_staging (
    run_id       BIGINT NOT NULL,
    business_key VARCHAR(100) NOT NULL,
    report_value VARCHAR(500),
    PRIMARY KEY (run_id, business_key)
);
~~~

Có thể dùng JobInstance ID làm run_id. Khi restart, các chunk tiếp tục ghi vào cùng vùng staging. Khi job hoàn tất, một bước publish sẽ chuyển dữ liệu của run_id đó sang bảng chính trong transaction phù hợp. Nếu bỏ lần chạy, chỉ xóa dữ liệu staging của đúng run_id:

~~~sql
DELETE FROM report_output_staging
WHERE run_id = :jobInstanceId;
~~~

Không xóa toàn bộ bảng staging nếu nhiều JobInstance có thể chạy đồng thời. Cũng không xóa dữ liệu bảng đích theo điều kiện rộng như ngày xử lý nếu ngày đó có thể được xử lý bởi một job khác. Phạm vi dọn cần xác định được chính xác bằng run_id hoặc một khóa sở hữu tương đương.

Nếu job ghi trực tiếp vào bảng đích, hãy thiết kế thao tác ghi có tính idempotent, ví dụ upsert theo business key hoặc lưu run_id để có thể xác định các dòng do lần chạy đó tạo ra. Xóa dữ liệu đã commit của job lỗi là một thao tác bù trừ ở cấp nghiệp vụ; nó không tự xảy ra chỉ vì chunk tiếp theo bị rollback.

## 6. Output gửi sang hệ thống bên ngoài

Các thao tác như gọi HTTP API, gửi email, đẩy message hoặc ghi vào object storage thường không nằm trong cùng transaction với JobRepository. Rollback database không thể tự thu hồi một request đã được hệ thống khác chấp nhận.

Với các side effect này:

- Gửi idempotency key ổn định theo nghiệp vụ để retry không tạo bản ghi hoặc giao dịch trùng.
- Lưu yêu cầu gửi trong outbox cùng transaction với dữ liệu nghiệp vụ, rồi để một bước riêng chuyển outbox sang hệ thống đích.
- Theo dõi trạng thái đã gửi, đang chờ và thất bại để có thể retry hoặc bù trừ.
- Chỉ xóa message hoặc bản ghi staging khi đã xác định chúng chưa được hệ thống đích xử lý, hoặc có quy trình bù trừ được nghiệp vụ chấp thuận.

Không nên xem việc xóa file local hoặc reset ExecutionContext là cách hoàn tác một side effect đã xảy ra ở hệ thống ngoài.

## 7. Chọn chính sách dọn theo loại output

| Loại output | Khi restart | Khi bỏ lần chạy |
|---|---|---|
| File được ghi bởi writer restartable | Giữ file staging và checkpoint; tiếp tục cùng resource. | Xóa file staging thuộc JobInstance đó rồi chạy JobInstance mới. |
| File được tạo lại toàn bộ từ đầu | Chỉ dùng cách này nếu có thể ghi lại an toàn và không tạo output trùng. | Xóa file tạm cũ và tạo file mới cho lần chạy mới. |
| Bảng database staging | Giữ các dòng đã commit, tiếp tục theo run_id và khóa idempotent. | Xóa các dòng staging theo đúng run_id. |
| Bảng đích được cập nhật trực tiếp | Dùng upsert hoặc cơ chế nhận diện bản ghi đã xử lý để tránh ghi trùng. | Chạy thao tác bù trừ theo phạm vi dữ liệu của lần chạy. |
| API, email hoặc message | Retry với idempotency key và trạng thái gửi được lưu bền vững. | Thực hiện bù trừ nếu hệ thống đích hỗ trợ; không thể giả định rollback tự thu hồi side effect. |

## 8. Các lỗi thiết kế thường gặp

**Xóa file ngay khi thấy FAILED.** Điều này có thể phá vỡ restart vì checkpoint vẫn tham chiếu trạng thái của file cũ. Chỉ xóa khi đã quyết định bỏ lần chạy đó.

**Tạo tên file theo JobExecution ID.** Mỗi lần restart có ID mới, nên writer có thể tạo file mới trong khi Spring Batch tiếp tục từ checkpoint cũ. Hãy dùng định danh ổn định theo JobInstance cho output cần restart.

**Ghi trực tiếp vào file cuối cùng trong lúc xử lý.** Consumer có thể đọc phải output chưa hoàn chỉnh. Ghi vào staging và publish sau khi job thành công.

**Cho rằng job FAILED sẽ rollback toàn bộ dữ liệu.** Transaction chunk chỉ bảo vệ phạm vi transaction của chunk. Các chunk trước đó đã commit và side effect bên ngoài vẫn có thể tồn tại.

**Xóa output chung của nhiều lần chạy.** Job chạy song song có thể dùng chung thư mục hoặc bảng staging. Mọi thao tác cleanup cần giới hạn theo JobInstance ID, run_id hoặc khóa sở hữu duy nhất.

**Bỏ qua lỗi cleanup.** File còn sót có thể bị hiểu nhầm là output mới ở lần chạy sau. Hãy ghi log, phát cảnh báo và có quy trình dọn artifact tồn đọng dựa trên trạng thái job cùng thời gian lưu giữ.

## 9. Tình huống cần kiểm tra khi triển khai

1. Cho job lỗi sau khi đã commit nhiều chunk. Xác nhận các chunk đã commit vẫn còn và chunk lỗi được rollback theo transaction.
2. Restart bằng cùng identifying JobParameters. Xác nhận JobInstance ID và đường dẫn staging giữ nguyên, writer tiếp tục đúng vị trí và không tạo dòng trùng.
3. Bỏ lần chạy lỗi rồi chạy với JobInstance mới. Xác nhận chỉ artifact thuộc JobInstance cũ bị dọn và output mới được tạo đầy đủ.
4. Làm cho bước publish thất bại. Xác nhận output cuối chưa bị công bố một phần và job chưa được xem là hoàn tất.
5. Mô phỏng lỗi quyền truy cập khi xóa file. Xác nhận lỗi cleanup được ghi log/cảnh báo và không làm xóa nhầm output của job khác.
6. Chạy hai JobInstance đồng thời. Xác nhận staging path, run_id và thao tác cleanup của chúng độc lập.

Chính sách dọn output đúng phải trả lời được ba câu hỏi: output thuộc JobInstance nào, job có được phép restart hay không, và khi nào output được xem là chính thức. Khi ba điều này được biểu diễn rõ trong đường dẫn staging, ExecutionContext và khóa dữ liệu, việc xử lý output sau job failed sẽ dự đoán được và an toàn hơn.
