# Kiểm tra output sau job complete

## 1. Vì sao job hoàn tất vẫn cần kiểm tra output?

Trong Spring Batch, một job chuyển sang trạng thái **COMPLETED** khi luồng thực thi của nó kết thúc thành công theo cấu hình. Điều này xác nhận các bước xử lý đã chạy đến điểm kết thúc hợp lệ, nhưng **không tự chứng minh rằng dữ liệu đầu ra đầy đủ, không trùng, đúng nghiệp vụ hoặc sẵn sàng cho hệ thống khác sử dụng**.

Ví dụ, một job đọc dữ liệu đơn hàng và ghi vào bảng đích có thể báo COMPLETED dù:

- Bộ xử lý vô tình lọc nhiều bản ghi hơn dự kiến.
- Bản ghi được ghi đủ số lượng nhưng sai số tiền hoặc sai khóa khách hàng.
- File CSV có đủ dòng nhưng sai header, encoding hoặc cách escape dấu phẩy.
- Writer thực hiện ghi ra API ngoài, API xác nhận yêu cầu nhưng xử lý bất đồng bộ chưa hoàn thành.
- Một lần chạy lại ghi đè hoặc nhân đôi dữ liệu đã xuất ở lần chạy trước.

**Kiểm tra output sau job complete** là bước đối soát dữ liệu thật sự đã được lưu hoặc phát hành với một **hợp đồng đầu ra (output contract)** được định nghĩa trước. Hợp đồng này phải nêu rõ tập bản ghi cần có, quy tắc biến đổi, tính duy nhất, tổng số liệu, định dạng và thời điểm output được xem là sẵn sàng.

Một luồng triển khai thường có dạng:

~~~text
Nguồn dữ liệu
    |
    v
Đọc -> Xử lý -> Ghi output
                    |
                    v
             Commit/đóng writer
                    |
                    v
             Đối soát output
               |          |
             Đạt        Không đạt
               |          |
               v          v
          Công bố      Đánh dấu FAILED,
          kết quả      cảnh báo và xử lý
~~~

Lý tưởng nhất, đối soát được triển khai thành **một Step xác minh nằm sau Step ghi dữ liệu**, để Spring Batch chỉ trả về trạng thái COMPLETED cho toàn bộ job khi cả xử lý lẫn kiểm tra đều thành công.

## 2. Phân biệt trạng thái thực thi và tính đúng đắn của dữ liệu

| Tín hiệu | Nó xác nhận điều gì? | Điều chưa thể kết luận |
|---|---|---|
| **JobExecution.status = COMPLETED** | Luồng điều khiển của job kết thúc thành công theo cấu hình | Giá trị và nội dung output đúng |
| **JobExecution.exitStatus** | Mã thoát được job/step gán; có thể là mã tùy chỉnh | Output đã đạt mọi tiêu chí nghiệp vụ |
| **StepExecution.readCount** | Số item được đọc theo thống kê của Step | Tất cả item đó phải xuất hiện ở đích |
| **StepExecution.filterCount** | Số item bị processor lọc bằng kết quả null | Việc lọc có đúng quy tắc hay không |
| **StepExecution.writeCount** | Số item được writer ghi theo bộ đếm của Spring Batch | Dữ liệu không trùng, không sai giá trị, đã bền vững ở mọi hệ thống ngoài |
| **Các chỉ số skip/rollback** | Có bỏ qua hoặc rollback trong quá trình xử lý | Skip có được nghiệp vụ chấp nhận và đầu ra có đủ hay không |
| **Truy vấn file/bảng/API đích** | Trạng thái output quan sát được sau khi ghi | Output có đúng kỳ vọng nếu chưa có baseline để đối soát |

Lưu ý: số item Spring Batch ghi nhận **không nhất thiết tương ứng 1:1 với số dòng trong bảng**. Một processor có thể lọc bản ghi, một writer có thể ghi nhiều dòng cho một item, hoặc writer có thể ghi ra hệ thống ngoài không tham gia transaction của Spring Batch. Vì vậy, không nên áp dụng công thức kiểu “readCount phải bằng writeCount” cho mọi job.

**BatchStatus và ExitStatus khác nhau:** BatchStatus thể hiện trạng thái vận hành (COMPLETED, FAILED, STOPPED...), trong khi ExitStatus là kết quả logic có thể được điều chỉnh bởi listener hoặc flow. Khi ứng dụng quy định một exit code đặc biệt, hãy kiểm tra cả hai theo hợp đồng của job. Không nên tự coi một exit code tùy chỉnh là bằng chứng output đúng.

## 3. Xây dựng hợp đồng đầu ra trước khi đối soát

Ví dụ một job nhập đơn hàng có tham số **batchId**, đọc bảng **staging_order**, lọc bản ghi không hợp lệ và ghi vào **processed_order**. Hợp đồng có thể quy định:

1. **Phạm vi:** chỉ các bản ghi thuộc đúng batchId; không dùng tổng của toàn bộ bảng đích.
2. **Tính đầy đủ:** mỗi đơn hợp lệ trong tập đầu vào có đúng một bản ghi tương ứng ở đích.
3. **Tính duy nhất:** khóa nghiệp vụ **(batch_id, source_id)** không trùng ở đích.
4. **Tính chính xác:** amount, currency, customer_id và các trường biến đổi khớp với quy tắc chuẩn hóa.
5. **Đối soát tổng:** tổng tiền hoặc tổng theo từng currency, trạng thái, khách hàng khớp với kỳ vọng.
6. **Tính cô lập:** lần chạy A không làm thay đổi output thuộc batch B.
7. **Tính sẵn sàng:** chỉ công bố batch cho consumer sau khi xác minh thành công.

Nên ghi hợp đồng thành tiêu chí có thể kiểm tra được:

| Nhóm kiểm tra | Ví dụ điều kiện đạt |
|---|---|
| Số lượng | Số đơn đích bằng số đơn hợp lệ được chấp nhận |
| Đầy đủ | Không có source_id hợp lệ nào thiếu ở đích |
| Không phát sinh ngoài phạm vi | Không có source_id đích không thuộc tập đầu vào hợp lệ |
| Không trùng | Mỗi (batch_id, source_id) xuất hiện đúng một lần |
| Giá trị | Từng amount/currency/status khớp kết quả transform đã định nghĩa |
| Định dạng | CSV đúng schema, delimiter, UTF-8, encoding và cách quote |
| Tính nhất quán trên restart | Chạy lại không tạo thêm record trùng hoặc output một phần |

**Nguồn kỳ vọng phải độc lập đủ mức cần thiết với output.** Nếu chỉ lấy chính dữ liệu đích để tính cả expected và actual, phép kiểm tra có thể tự xác nhận một kết quả sai. Expected nên đến từ snapshot đầu vào, tập record được chấp nhận, metadata nghiệp vụ hoặc bảng kiểm soát đã được chốt trước khi xuất.

### Xác định ranh giới dữ liệu

Mỗi kết quả đối soát phải gắn với một khóa rõ ràng, chẳng hạn **batchId**, ngày nghiệp vụ, tenant và version xuất. Tránh kiểm tra số lượng trên bảng chung khi nhiều job chạy đồng thời. Nếu dữ liệu nguồn có thể thay đổi trong lúc chạy, hãy dùng snapshot, watermark hoặc staging đã đóng băng để bảo đảm cùng một tập dữ liệu được dùng cho cả xử lý và đối soát.

### Quy định rõ cách xử lý filtered và skipped item

Giả sử có 1.000 bản ghi đầu vào, 75 bản ghi bị lọc theo quy tắc, 5 bản ghi khác được phép skip sau lỗi và mỗi item hợp lệ xuất đúng một dòng. Kỳ vọng có thể là **920 dòng** nếu hợp đồng chấp nhận cả 5 skip. Nếu nghiệp vụ không cho phép mất bất kỳ đơn hợp lệ nào, job phải FAILED thay vì tự động coi 920 dòng là đúng.

Các bộ đếm đọc/ghi/skip hỗ trợ điều tra; **số lượng hợp lệ kỳ vọng phải được xác định theo chính sách nghiệp vụ**, đặc biệt khi có retry, rollback, xử lý 1:n hoặc dữ liệu biến đổi qua nhiều Step.

## 4. Thứ tự kiểm tra sau khi ghi xong

Một quy trình thực tế nên thực hiện theo thứ tự sau:

1. **Xác nhận thời điểm kết thúc.** Chỉ đối soát output đã commit và writer đã đóng; nếu chạy job bất đồng bộ, đợi hoặc truy vấn đến khi JobExecution có trạng thái kết thúc.
2. **Kiểm tra trạng thái Step.** Xem các Step đã chạy, Step thất bại/skip, exit code và các lỗi ghi nhận.
3. **Khoanh vùng output của lần chạy.** Sử dụng batchId hoặc output location/version bất biến.
4. **Đối soát số lượng, khóa và giá trị.** Ưu tiên các truy vấn xác minh cụ thể thay vì chỉ đếm tổng số dòng.
5. **Kiểm tra tính toàn vẹn vật lý.** Với file: tồn tại, kích thước, schema, khả năng parse và checksum. Với DB: dữ liệu đã commit, khóa duy nhất và trạng thái xuất bản.
6. **Ghi nhận bằng chứng.** Lưu số kỳ vọng, số thực tế, số missing/duplicate, mẫu lỗi, thời điểm, jobExecutionId và batchId để truy vết.
7. **Chỉ công bố khi đạt.** Đánh dấu batch READY, cập nhật manifest hoặc gửi sự kiện cho consumer sau khi hoàn tất toàn bộ tiêu chí.

Một vài dòng log “write succeeded” hay một lần đếm số row chỉ giúp quan sát, không thay thế kiểm tra dữ liệu dựa trên hợp đồng.

## 5. Ví dụ đối soát output trong database

Giả sử dữ liệu minh họa như sau:

- **staging_order(batch_id, source_id, valid, amount, currency)** chứa input đã đóng băng.
- **processed_order(batch_id, source_id, amount, currency)** là output.
- Với **valid = TRUE**, mỗi source_id phải có đúng một dòng output với số tiền và tiền tệ đã được transform theo quy tắc nghiệp vụ. Ví dụ dưới đây tập trung vào tính đầy đủ và không trùng; phần kiểm tra giá trị cần bổ sung theo phép biến đổi thực tế.
- Hệ thống nên đặt unique constraint trên **processed_order(batch_id, source_id)** để hỗ trợ tính idempotent ngay ở tầng dữ liệu.

### 5.1. Đếm số dòng đúng phạm vi

~~~sql
-- Expected: số bản ghi đầu vào được phép xuất
SELECT COUNT(*)
FROM staging_order
WHERE batch_id = :batchId
  AND valid = TRUE;

-- Actual: số bản ghi đã có ở đích
SELECT COUNT(*)
FROM processed_order
WHERE batch_id = :batchId;
~~~

Hai con số bằng nhau là điều kiện cần trong ví dụ ánh xạ 1:1 này, **chưa phải điều kiện đủ**: một đơn bị thiếu và một đơn khác bị trùng vẫn cho cùng tổng số dòng.

### 5.2. Tìm bản ghi thiếu

~~~sql
SELECT s.source_id
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.valid = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM processed_order t
      WHERE t.batch_id = s.batch_id
        AND t.source_id = s.source_id
  );
~~~

Kết quả phải rỗng. Nếu có dòng, lưu một số source_id làm bằng chứng để điều tra bước lọc, skip, writer và trạng thái transaction.

### 5.3. Tìm bản ghi thừa hoặc không hợp lệ

~~~sql
SELECT t.source_id
FROM processed_order t
WHERE t.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM staging_order s
      WHERE s.batch_id = t.batch_id
        AND s.source_id = t.source_id
        AND s.valid = TRUE
  );
~~~

Kết quả phải rỗng. Truy vấn này bắt các bản ghi không thuộc tập input hợp lệ, kể cả dữ liệu tồn dư của lần chạy trước nếu dùng chung batchId sai cách.

### 5.4. Tìm duplicate và sai giá trị

~~~sql
-- Mỗi source_id phải xuất hiện đúng một lần trong batch.
SELECT batch_id, source_id, COUNT(*) AS occurrences
FROM processed_order
WHERE batch_id = :batchId
GROUP BY batch_id, source_id
HAVING COUNT(*) > 1;

-- Ví dụ khi amount/currency được copy nguyên từ staging.
-- Nếu có transform, so với giá trị EXPECTED sau transform.
SELECT s.source_id,
       s.amount AS expected_amount,
       t.amount AS actual_amount,
       s.currency AS expected_currency,
       t.currency AS actual_currency
FROM staging_order s
JOIN processed_order t
  ON t.batch_id = s.batch_id
 AND t.source_id = s.source_id
WHERE s.batch_id = :batchId
  AND s.valid = TRUE
  AND (
      s.amount <> t.amount
      OR s.currency <> t.currency
  );
~~~

Truy vấn so sánh cuối chỉ minh họa trường hợp trường dữ liệu **không biến đổi** và **không null**. Nếu phép biến đổi có làm tròn hoặc quy đổi tiền tệ, phải so với giá trị sau biến đổi và quy định rõ precision/scale. Với cột nullable, dùng phép so sánh null-safe phù hợp với database; toán tử **<>** thông thường không phát hiện đầy đủ trường hợp một phía null.

Ngoài kiểm tra từng dòng, có thể đối soát **SUM(amount)** theo currency, tổng theo trạng thái và số khách hàng riêng biệt. Không cộng các số tiền khác loại tiền tệ vào cùng một tổng mà chưa có quy tắc chuyển đổi.

## 6. Gắn kiểm tra thành Step sau Step xử lý

Với Spring Batch sử dụng cấu hình builder có **JobRepository** và **PlatformTransactionManager**, một hướng triển khai là tạo tasklet xác minh chạy sau Step nhập dữ liệu. Mẫu sau dùng **JdbcTemplate**, giả định cả hai bảng cùng truy cập được từ datasource và **processOrdersStep** đã được định nghĩa ở cấu hình khác.

~~~java
import java.util.Objects;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersJobConfiguration {

    @Bean
    public Step verifyOutputStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {

        return new StepBuilder("verifyOutputStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    Object rawBatchId = chunkContext.getStepContext()
                            .getJobParameters().get("batchId");

                    if (!(rawBatchId instanceof String batchId)
                            || batchId.isBlank()) {
                        throw new IllegalArgumentException(
                                "Thiếu job parameter batchId");
                    }

                    Long expected = jdbcTemplate.queryForObject(
                            """
                            SELECT COUNT(*)
                            FROM staging_order
                            WHERE batch_id = ? AND valid = TRUE
                            """,
                            Long.class, batchId);

                    Long actual = jdbcTemplate.queryForObject(
                            """
                            SELECT COUNT(*)
                            FROM processed_order
                            WHERE batch_id = ?
                            """,
                            Long.class, batchId);

                    Long missing = jdbcTemplate.queryForObject(
                            """
                            SELECT COUNT(*)
                            FROM staging_order s
                            WHERE s.batch_id = ? AND s.valid = TRUE
                              AND NOT EXISTS (
                                  SELECT 1 FROM processed_order t
                                  WHERE t.batch_id = s.batch_id
                                    AND t.source_id = s.source_id
                              )
                            """,
                            Long.class, batchId);

                    Long unexpected = jdbcTemplate.queryForObject(
                            """
                            SELECT COUNT(*)
                            FROM processed_order t
                            WHERE t.batch_id = ?
                              AND NOT EXISTS (
                                  SELECT 1 FROM staging_order s
                                  WHERE s.batch_id = t.batch_id
                                    AND s.source_id = t.source_id
                                    AND s.valid = TRUE
                              )
                            """,
                            Long.class, batchId);

                    Long duplicateKeys = jdbcTemplate.queryForObject(
                            """
                            SELECT COUNT(*)
                            FROM (
                                SELECT source_id
                                FROM processed_order
                                WHERE batch_id = ?
                                GROUP BY source_id
                                HAVING COUNT(*) > 1
                            ) d
                            """,
                            Long.class, batchId);

                    if (!Objects.equals(expected, actual)
                            || missing == null || missing != 0L
                            || unexpected == null || unexpected != 0L
                            || duplicateKeys == null || duplicateKeys != 0L) {
                        throw new IllegalStateException(
                                "Output mismatch, batchId=" + batchId
                                + ", expected=" + expected
                                + ", actual=" + actual
                                + ", missing=" + missing
                                + ", unexpected=" + unexpected
                                + ", duplicateKeys=" + duplicateKeys);
                    }

                    // Có thể ghi audit và kiểm tra tổng tiền tại đây.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job processOrdersJob(
            JobRepository jobRepository,
            @Qualifier("processOrdersStep") Step processOrdersStep,
            @Qualifier("verifyOutputStep") Step verifyOutputStep) {

        return new JobBuilder("processOrdersJob", jobRepository)
                .start(processOrdersStep)
                .next(verifyOutputStep)
                .build();
    }
}
~~~

**Điều kiện áp dụng mẫu:** input có source_id duy nhất trong phạm vi batch, một input valid tạo một output, và không có skip nghiệp vụ được chấp nhận sau khi tập valid được xác định. Với mapping 1:n, phép gộp dữ liệu hoặc skip có kiểm soát, phải thay expected và các truy vấn đối soát cho đúng contract của job. Đoạn mẫu chưa kiểm tra amount/currency; phải bổ sung nếu đó là điều kiện công bố output.

Khi một truy vấn đối soát phát hiện sai lệch, tasklet ném exception; **verifyOutputStep FAILED và job không kết thúc COMPLETED** trong flow tuần tự thông thường. Exception cần chứa batchId, số kỳ vọng/số thực tế và mức sai lệch; không ghi toàn bộ nội dung nhạy cảm của các bản ghi vào log.

Nếu chỉ đặt kiểm tra trong **JobExecutionListener.afterJob**, đây là thời điểm thích hợp để log, audit hoặc gửi thông báo, nhưng **không nên dựa vào exception của afterJob để chuyển một job đã hoàn tất thành FAILED**. Muốn kết quả xác minh quyết định trạng thái job, sử dụng Step xác minh hoặc điều khiển flow với nhánh failure rõ ràng.

### Khi nào đọc JobExecution từ bên ngoài?

Nếu hệ thống giám sát chạy ngoài job, nó có thể tra cứu **JobExecution** bằng JobExplorer/JobOperator theo ID thực thi và chỉ kiểm tra khi status ở trạng thái kết thúc. Lưu ý launcher có thể chạy bất đồng bộ: giá trị trả ngay sau khi khởi chạy chưa chắc đã là kết quả cuối cùng.

~~~java
// Đoạn này chỉ minh họa việc đọc trạng thái của một JobExecution đã lấy được.
if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
    // Đối soát output theo batchId của lần chạy đã hoàn tất.
} else if (jobExecution.getStatus() == BatchStatus.FAILED) {
    // Điều tra exception và Step thất bại trước khi công bố output.
}
~~~

Với job dừng ở **STOPPED**, **FAILED** hoặc đang chạy, không được coi output là phiên bản cuối. Nếu cần báo cáo thống kê, có thể xem **getStepExecutions()** để đọc các counter và lỗi của từng Step, sau đó đối chiếu với dữ liệu thật ở đích.

## 7. Kiểm tra output là file CSV/JSON/XML

Với output dạng file, số item trong writer chưa đủ để xác nhận rằng consumer có thể đọc đúng. Một quy trình kiểm tra nên bao gồm:

| Hạng mục | Cách xác minh |
|---|---|
| Đúng artifact | Đường dẫn/tên object có batchId hoặc version; không nhầm file cũ |
| Tồn tại và đã ghi xong | File đóng hoàn toàn, kích thước hợp lệ; không đọc file đang được append |
| Schema | Đúng số cột, tên header, thứ tự cột khi contract yêu cầu |
| Khả năng parse | Dùng parser CSV/JSON/XML thực tế; không đếm dòng bằng cách tách tùy tiện theo dấu xuống dòng |
| Ký tự và format | Encoding, BOM, newline, quote/escape, định dạng ngày, dấu thập phân |
| Số lượng record | Đếm record logic sau khi parse, phân biệt header/trailer |
| Tính duy nhất và toàn vẹn | Khóa nghiệp vụ không trùng, kiểm tra các trường bắt buộc, tổng/checksum |
| Tính công bố | Consumer chỉ thấy file đã xác minh hoặc manifest/marker READY |

Ví dụ một file CSV:

~~~csv
batch_id,source_id,amount,currency
B20261116,O001,120.00,VND
B20261116,O002,95.50,USD
~~~

Trong ví dụ này, kiểm tra phải xác nhận header có bốn cột, từng record parse hợp lệ, batch_id khớp, source_id không lặp, amount đọc được theo định dạng được công bố, và tập source_id đúng với expected input. **Không dùng phép đếm ký tự xuống dòng** làm bằng chứng số lượng bản ghi CSV: trường được quote có thể chứa newline.

Khi xuất file lớn, cách tổ chức thường là:

~~~text
orders-B20261116.csv.part
    -> writer đóng file
    -> kiểm tra schema + record + checksum
    -> công bố orders-B20261116.csv
    -> tạo manifest/READY marker
    -> downstream bắt đầu đọc
~~~

Rename nguyên tử có thể dùng khi **cùng filesystem và filesystem hỗ trợ**; đừng mặc định rename sang storage khác là nguyên tử. Với object storage, nên tạo object theo key/version duy nhất, xác minh chính object đó (ví dụ metadata, size và checksum), sau đó mới ghi manifest/READY marker. Không dùng việc list thấy object làm bằng chứng rằng một giao dịch xuyên nhiều hệ thống đã hoàn tất.

Nếu phải đưa file cho hệ thống khác qua SFTP/API, phân biệt **đã upload xong** với **đã được bên nhận xử lý xong**. Chỉ tuyên bố hoàn tất theo cấp độ được hợp đồng đầu ra quy định và có tín hiệu xác nhận tương ứng.

## 8. Restart, retry và idempotency sau job

Đối soát đặc biệt quan trọng khi một job đã ghi được một phần output rồi thất bại. Spring Batch có thể quản lý rollback đối với tài nguyên tham gia transaction, nhưng tác động lên file, HTTP API, message broker hoặc một datasource khác **không tự động bị rollback cùng transaction**.

Các chiến lược thường dùng:

- **Khóa idempotent:** unique key như (batch_id, source_id), ghi theo upsert có quy tắc hoặc bỏ qua bản ghi đã hoàn tất một cách có kiểm soát.
- **Staging rồi publish:** ghi output vào vùng tạm, kiểm tra toàn bộ, sau đó chuyển trạng thái READY hoặc thay con trỏ phiên bản.
- **Không dùng file đích đang được tiêu thụ:** ghi vào tên tạm/version mới, chỉ phát hành sau khi đã đóng và xác minh.
- **Theo dõi từng attempt:** phân biệt **JobInstance**, **JobExecution** và batchId nghiệp vụ; job có thể có nhiều execution khi restart.
- **Xác minh trên tập cuối cùng:** nếu restart được thiết kế để nối tiếp dữ liệu hợp lệ đã ghi trước đó, expected/actual phải phản ánh tập output cuối của batch, không đơn giản chỉ lấy writeCount của execution mới nhất.

Ví dụ: attempt 1 ghi 600/1.000 đơn vào hệ thống ngoài rồi thất bại. Attempt 2 xử lý lại có thể tạo 600 đơn trùng nếu writer không idempotent. Ngay cả khi attempt 2 kết thúc COMPLETED và report ghi đủ 1.000 item, output cuối vẫn có thể chứa 1.600 bản ghi. Đối soát uniqueness và exact set sẽ phát hiện lỗi mà một status check không phát hiện.

Khi kiểm tra thất bại, việc chạy lại phải có **quy trình khắc phục đã xác định**: xóa hoặc cách ly output tạm, ghi tiếp theo checkpoint, hoặc reprocess với khóa idempotent. Tránh tự động xóa cả batch đích nếu nó có dữ liệu đã được consumer xác nhận hoặc còn đang được job khác sử dụng.

## 9. Tính nhất quán giữa nhiều hệ thống

Một job có thể vừa ghi DB, vừa xuất CSV, vừa gửi sự kiện. Nếu ba đích không nằm trong cùng một transaction, **COMPLETED** không đồng nghĩa với tất cả bên nhận đã đạt trạng thái nhất quán.

Ví dụ với quy trình xuất đơn hàng:

1. Ghi đơn vào bảng staging của output.
2. Kiểm tra các bản ghi trong bảng đã commit, đầy đủ và đúng giá trị.
3. Đánh dấu batch là READY trong cùng database hoặc tạo bản ghi outbox trong transaction phù hợp.
4. Publisher chuyển manifest/sự kiện ra ngoài và ghi nhận trạng thái phát hành.
5. Bên tiêu thụ dựa trên batchId/version và idempotency key để tránh xử lý trùng.

Mẫu **transactional outbox** hữu ích nếu cần nhất quán giữa cập nhật database và phát sự kiện: ghi dữ liệu cùng bản ghi outbox trong một transaction, sau đó một publisher gửi event và retry nếu lỗi. Điều này hỗ trợ giao hàng tin cậy nhưng vẫn cần consumer idempotent vì có thể có giao hàng lặp.

Nếu hệ thống đích có độ trễ cập nhật, hãy định nghĩa rõ thời điểm dữ liệu được coi là quan sát được và cơ chế chờ/retry có giới hạn. **Không nới lỏng đối soát vô hạn** chỉ để biến một batch lỗi thành trạng thái thành công.

## 10. Audit, cảnh báo và cách xử lý mismatch

Kết quả đối soát nên tạo bản ghi audit đủ để lần ngược lại phiên bản output và quyết định tiếp theo:

~~~text
jobName          = processOrdersJob
jobExecutionId   = 98765
batchId          = B20261116
outputVersion    = v3
expectedRecords  = 1000
actualRecords    = 999
missingRecords   = 1
unexpectedRecords= 0
duplicateKeys    = 0
amountMismatch   = 0
verification     = FAILED
verifiedAt       = 2026-11-16T09:30:00+07:00
~~~

Đây chỉ là một ví dụ cấu trúc audit, không phải dữ liệu lấy từ một job thực tế. Nếu phép kiểm tra thất bại:

1. **Chặn công bố** hoặc đặt batch ở trạng thái QUARANTINED/INVALID để downstream không dùng nhầm.
2. **Ghi metric và cảnh báo**: sai số record, tổng tiền, số record trùng, thời gian xác minh, tỷ lệ lỗi theo batch.
3. **Thu thập mẫu chẩn đoán có giới hạn**, ví dụ một số source_id bị thiếu, cùng metadata execution/Step và correlation ID.
4. **Đối chiếu với policy:** một số chênh lệch có thể được cho phép nếu contract ghi rõ ngưỡng; dữ liệu tiền hoặc sổ cái thường cần đối soát nghiêm ngặt.
5. **Khắc phục theo nguyên nhân:** lỗi filter, logic transform, retry, commit, file chưa hoàn chỉnh, dữ liệu nguồn thay đổi hoặc consumer xử lý bất đồng bộ.
6. **Đối soát lại sau khi sửa:** chỉ chuyển sang READY khi toàn bộ điều kiện bắt buộc đều đạt và có bằng chứng mới.

Audit cần phản ánh **verification của outputVersion cụ thể**. Nếu ghi lại output sau đó, bản audit trước không còn đủ để chứng minh phiên bản mới đã được kiểm tra.

## 11. Tình huống kiểm thử cho chính cơ chế đối soát

Khi thiết kế kiểm tra output, nên thử ít nhất các tình huống sau trên dữ liệu mẫu:

| Tình huống | Kết quả kỳ vọng |
|---|---|
| 100 đơn hợp lệ, ghi đủ 100 đơn và đúng giá trị | Verification thành công; job có thể COMPLETED |
| Thiếu 1 đơn dù số lượng writer báo bình thường | Phát hiện source_id thiếu; job FAILED/chặn publish |
| 1 đơn bị ghi hai lần, 1 đơn khác thiếu | Phát hiện đồng thời duplicate và missing dù tổng số dòng có thể đúng |
| Đủ số dòng nhưng amount bị sai | Kiểm tra trường/tổng tiền phát hiện mismatch |
| Lọc hoặc skip đúng theo chính sách | Không báo lỗi nếu expected set đã phản ánh quy tắc được phê duyệt |
| Restart sau khi ghi một phần output | Không trùng record; đối soát trên tập cuối cùng |
| File CSV có header sai hoặc quote lỗi | Parser/schema validation thất bại |
| Hai batch chạy cùng lúc | Đối soát mỗi batch độc lập, không lẫn dữ liệu |
| Ghi object thành công nhưng marker READY chưa có | Consumer chưa được coi là có output để sử dụng |
| Không thể truy cập database/file khi xác minh | Verification thất bại hoặc ở trạng thái chưa xác minh, tuyệt đối không tự coi là đạt |

Các tình huống này giúp chứng minh rằng cơ chế kiểm tra thực sự bắt lỗi **output consistency**, thay vì chỉ lặp lại trạng thái của framework.

## 12. Những sai lầm thường gặp

**Chỉ kiểm tra JobExecution là COMPLETED.** Khắc phục bằng Step đối soát dữ liệu thực với baseline độc lập.

**Chỉ so sánh readCount và writeCount.** Khắc phục bằng cách xác định logic filter, skip, transform và mapping trước khi đặt điều kiện số lượng.

**Chỉ so sánh COUNT(*).** Khắc phục bằng đối soát missing/extra/duplicate, khóa nghiệp vụ, giá trị và tổng nghiệp vụ.

**Đọc output khi writer chưa đóng hoặc transaction chưa commit.** Khắc phục bằng cách đặt verification ở sau Step ghi và thống nhất tín hiệu sẵn sàng.

**Kiểm tra trên toàn bảng không có batchId.** Khắc phục bằng khóa đối soát chặt chẽ theo batch/tenant/version và snapshot input.

**Công bố output trước khi verify.** Khắc phục bằng staging, kiểm tra, rồi mới chuyển READY hoặc tạo manifest.

**Cho rằng restart luôn an toàn.** Khắc phục bằng idempotency key, unique constraint, cơ chế xử lý output dở dang và phép kiểm tra sau restart.

**Để listener sau job ném exception như cơ chế fail duy nhất.** Khắc phục bằng Step kiểm tra hoặc flow có xử lý FAILED rõ ràng.

## 13. Nguyên tắc áp dụng

Một job xử lý dữ liệu đáng tin cậy cần hai lớp xác nhận: **thực thi đúng luồng** và **đầu ra đúng hợp đồng**. Với Spring Batch, hãy đặt kiểm tra dữ liệu sau khi output đã bền vững, biến các điều kiện bắt buộc thành Step hoặc cơ chế xác minh có trạng thái rõ ràng, giữ bằng chứng đối soát theo từng batch/phiên bản, và chỉ công bố output khi tất cả điều kiện đạt.

Nhờ vậy, COMPLETED có ý nghĩa thực tế hơn: không chỉ là “framework không gặp lỗi không xử lý được”, mà còn là “kết quả batch đã được xác minh đủ tin cậy cho bước sử dụng tiếp theo”.
