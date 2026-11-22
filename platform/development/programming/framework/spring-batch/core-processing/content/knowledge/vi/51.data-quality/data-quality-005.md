# Reconciliation sau Job trong Spring Batch

## 1. Reconciliation là gì?

Trong **Spring Batch Core Processing**, một Job có thể kết thúc với **BatchStatus.COMPLETED** trong khi dữ liệu ở hệ thống đích vẫn không đáp ứng đúng yêu cầu nghiệp vụ. Ví dụ: Job đã đọc file đơn hàng, writer không ném exception, nhưng một số đơn bị bỏ sót, một số tiền bị ghi sai, hoặc dữ liệu thuộc kỳ trước xuất hiện trong kỳ hiện tại.

**Reconciliation (đối soát)** là quá trình so sánh dữ liệu **thực tế sau xử lý** với một nguồn kỳ vọng đáng tin cậy để xác minh tính đầy đủ, chính xác và nhất quán. Nó là hoạt động cốt lõi của **Data quality**, bởi trạng thái thực thi kỹ thuật không thay thế được việc xác nhận kết quả nghiệp vụ.

Một báo cáo đối soát tốt phải trả lời được:

- Đã nhận đủ dữ liệu nguồn của kỳ/batch chưa?
- Bao nhiêu item hợp lệ phải xuất hiện ở đích?
- Có dòng bị thiếu, thừa hoặc trùng business key không?
- Tổng số lượng, tổng tiền và các trường quan trọng có đúng không?
- Các item filtered, rejected hoặc skipped đã được giải thích đúng chưa?
- Kết quả là **PASS**, **MISMATCH** hay **PENDING/INCONCLUSIVE**?
- Khi phát hiện sai lệch, hệ thống có ngăn công bố dữ liệu, lưu bằng chứng và hỗ trợ xử lý lại không?

Ví dụ luồng nhập đơn hàng:

~~~text
Source file / source database
               |
               v
       Staging + validation
               |
               v
      Spring Batch import
               |
               v
        Target database
               |
               v
       Reconciliation
        /     |      \
      PASS  MISMATCH  INCONCLUSIVE
       |       |          |
    Publish  Alert     Wait/retry
             + audit
~~~

**PASS** chỉ đúng khi các quy tắc đã định nghĩa đều thỏa. **MISMATCH** là một sai lệch đã xác định. **INCONCLUSIVE** nghĩa là chưa đủ dữ liệu hoặc nguồn chưa ổn định để kết luận; không nên tự coi đây là PASS.

## 2. Các cấp độ đối soát

Không phải mọi trường hợp đều cần so sánh từng cột của hàng triệu bản ghi. Có thể áp dụng các lớp kiểm tra tăng dần:

| Cấp độ | Nội dung | Ví dụ |
| --- | --- | --- |
| Tiếp nhận nguồn | Số dòng file, checksum, manifest, mã lô | Nhận đủ 10.000 dòng |
| Cấu trúc dữ liệu | Format, trường bắt buộc, dữ liệu lỗi | 3 dòng lỗi ngày tháng |
| Luồng xử lý | Đọc, lọc, skip, ghi | readCount, filterCount, skipCount, writeCount |
| Số lượng nghiệp vụ | Expected record count và actual count | 9.990 / 9.990 |
| Tổng hợp giá trị | Tổng tiền, tổng quantity, tổng số dư | SUM(amount) khớp |
| Business key | Khóa thiếu, thừa, trùng | O-103 thiếu, O-999 thừa |
| Thuộc tính | Sai amount, currency, status, mã khách hàng | Amount chênh 10,00 |
| Downstream | Receipt/acknowledgement ở hệ thống nhận | Đủ thông báo đã tiêu thụ |

**Count bằng nhau không chứng minh dữ liệu đúng**. Nếu đích thiếu O-103 nhưng thừa O-999, số lượng vẫn khớp. Tổng tiền cũng có thể tình cờ khớp khi hai lỗi bù trừ. Vì thế, với dữ liệu quan trọng, cần kiểm tra **khóa nghiệp vụ và giá trị chi tiết** bên cạnh các aggregate.

## 3. Phải xác định nguồn kỳ vọng độc lập

Nếu tính cả expected và actual từ chính bảng đích, kết quả sẽ luôn bằng nhau mà không phát hiện lỗi bị thiếu dữ liệu. Nguồn kỳ vọng nên đến từ:

- File input và manifest bất biến do bên cung cấp xác nhận.
- Bảng staging chứa snapshot nguồn đã chốt.
- Tập bản ghi đầu vào được xác định trước theo kỳ nghiệp vụ.
- Số liệu đối chứng được tính độc lập từ hệ thống nguồn.
- Quy tắc nghiệp vụ được phiên bản hóa và kiểm tra riêng.

Mỗi lần đối soát phải có một **scope** cụ thể:

| Thông tin | Giá trị ví dụ | Lý do |
| --- | --- | --- |
| batchId | batch-20261115-001 | Phân biệt từng lô dữ liệu |
| businessDate | 2026-11-15 | Phân biệt kỳ nghiệp vụ |
| sourceVersion | snapshot-v3 | Biết đang so với phiên bản nguồn nào |
| ruleVersion | order-import-v2 | Gắn điều kiện chấp nhận/lọc dữ liệu |
| currency | VND | Không cộng các loại tiền khác đơn vị |
| jobExecutionId | 8542 | Truy vết lần chạy Job |
| reconciliationRunId | recon-001 | Phân biệt các lần kiểm tra lại |

Nguồn phải **ổn định** trong lúc đối soát. Nếu một thread đang thêm dòng vào staging trong khi service lấy expected count, phép so sánh có thể sai vì thời điểm đọc khác nhau. Nên có trạng thái **SOURCE_FINALIZED**, một snapshot bất biến, transaction isolation phù hợp, hoặc watermark rõ ràng.

Với dữ liệu đến muộn, quy định deadline và thời điểm chốt. Nếu bên nguồn tiếp tục cập nhật sau khi Batch hoàn tất, reconciliation phải đối soát đúng **snapshot mà Job thực sự đã dùng**, không tự so với một tập dữ liệu mới hơn.

## 4. Fixture ví dụ: 10 dòng nguồn, 8 dòng được ghi

Giả sử file đầu vào có 10 dòng dữ liệu, không tính header:

- **8 dòng READY**, hợp lệ, các orderId khác nhau, tổng tiền **1.250,00**.
- **1 dòng CANCELLED**, bị processor lọc bằng cách trả về **null**.
- **1 dòng INVALID**, làm phát sinh exception được cấu hình skip tại processor.

| Dòng | orderId | Số tiền | Disposition | Kết quả |
| ---: | --- | ---: | --- | --- |
| 1 | O-101 | 100,00 | READY | Ghi |
| 2 | O-102 | 200,00 | READY | Ghi |
| 3 | O-103 | 150,00 | READY | Ghi |
| 4 | O-104 | 100,00 | READY | Ghi |
| 5 | O-105 | 250,00 | READY | Ghi |
| 6 | O-106 | 100,00 | READY | Ghi |
| 7 | O-107 | 200,00 | READY | Ghi |
| 8 | O-108 | 150,00 | READY | Ghi |
| 9 | O-109 | 300,00 | CANCELLED | Filter |
| 10 | O-110 | -50,00 | INVALID | Process skip |

Kết quả kỳ vọng là **8 đơn hàng O-101 đến O-108**, tổng tiền **1.250,00**. Dòng CANCELLED và INVALID không phải dữ liệu đích cần ghi.

Trong một lần chạy đơn giản, không có read skip hoặc tình huống retry/rollback khác, StepExecution có thể có:

~~~text
readCount         = 10
writeCount        = 8
filterCount       = 1
processSkipCount  = 1
skipCount         = 1
~~~

Bộ đếm đó mô tả luồng xử lý; reconciliation còn phải kiểm tra **chính xác các khóa và amount** ở bảng đích. Một writer ghi sai orderId vẫn có thể làm writeCount tăng bình thường.

Điều kiện filtered/skip phải phản ánh **giao kèo nghiệp vụ**. Không mặc nhiên coi mọi item được skip là hợp lệ: nếu dữ liệu quan trọng bị lỗi, chính sách có thể yêu cầu Job FAILED thay vì cho phép skip.

## 5. Bảng staging và bảng đích

Ví dụ schema SQL tương đối độc lập database:

~~~sql
CREATE TABLE staging_order (
    batch_id        VARCHAR(64) NOT NULL,
    line_number     BIGINT NOT NULL,
    order_id        VARCHAR(64),
    amount          DECIMAL(18, 2),
    disposition     VARCHAR(16) NOT NULL,
    PRIMARY KEY (batch_id, line_number)
);

CREATE TABLE imported_order (
    batch_id        VARCHAR(64) NOT NULL,
    order_id        VARCHAR(64) NOT NULL,
    amount          DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);

CREATE INDEX idx_staging_order_recon
    ON staging_order (batch_id, disposition, order_id);
~~~

**staging_order** dùng khóa theo line_number để bảo toàn mỗi dòng đầu vào, kể cả khi nhiều dòng có cùng orderId. **imported_order** bảo vệ uniqueness trong phạm vi batch. Nếu nghiệp vụ cấm trùng orderId toàn hệ thống, khóa unique ở đích phải phản ánh phạm vi toàn hệ thống chứ không chỉ batch.

Một lỗi chung ở logic tạo disposition và logic import có thể khiến expected và actual cùng sai. Với dữ liệu nhạy cảm hoặc tài chính, nên có manifest/source checksum hoặc nguồn kiểm tra độc lập để giảm nguy cơ hai phía đồng thời mắc cùng một bug.

## 6. So sánh count và tổng tiền

Tổng kỳ vọng:

~~~sql
SELECT
    COUNT(*) AS expected_count,
    COALESCE(SUM(amount), 0) AS expected_amount
FROM staging_order
WHERE batch_id = :batchId
  AND disposition = 'READY';
~~~

Tổng thực tế:

~~~sql
SELECT
    COUNT(*) AS actual_count,
    COALESCE(SUM(amount), 0) AS actual_amount
FROM imported_order
WHERE batch_id = :batchId;
~~~

Với dữ liệu fixture:

~~~text
expected_count  = 8
actual_count    = 8
expected_amount = 1250.00
actual_amount   = 1250.00
~~~

Dùng kiểu **DECIMAL/NUMERIC** ở database và **BigDecimal** ở Java khi so tiền. Không sử dụng float/double cho đối soát tài chính. Nếu so bằng BigDecimal, **compareTo() == 0** kiểm tra bằng nhau theo giá trị số; **equals()** còn xét scale nên 1.0 và 1.00 có thể khác nhau theo equals.

Nếu có nhiều loại tiền, nên nhóm theo **currency** và đối soát riêng. Nếu buộc phải quy đổi, cần thống nhất nguồn tỷ giá, thời điểm tỷ giá và chính sách làm tròn.

Tổng tiền khớp chưa đủ. Ví dụ:

~~~text
O-101: expected 100.00, actual  90.00  (-10.00)
O-102: expected 200.00, actual 210.00  (+10.00)
~~~

Tổng tiền vẫn không đổi dù **hai dòng sai giá trị**. Đó là lý do phải có so sánh theo business key.

## 7. Phát hiện khóa thiếu, thừa, sai amount và trùng

### Khóa kỳ vọng bị thiếu

~~~sql
SELECT s.order_id
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.disposition = 'READY'
  AND NOT EXISTS (
      SELECT 1
      FROM imported_order t
      WHERE t.batch_id = s.batch_id
        AND t.order_id = s.order_id
  )
ORDER BY s.order_id;
~~~

### Khóa thừa hoặc không thuộc dữ liệu được chấp nhận

~~~sql
SELECT t.order_id
FROM imported_order t
WHERE t.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM staging_order s
      WHERE s.batch_id = t.batch_id
        AND s.order_id = t.order_id
        AND s.disposition = 'READY'
  )
ORDER BY t.order_id;
~~~

Truy vấn này cũng phát hiện khóa CANCELLED bị writer ghi nhầm.

### Sai số tiền ở các khóa tồn tại ở cả hai bên

~~~sql
SELECT
    s.order_id,
    s.amount AS expected_amount,
    t.amount AS actual_amount
FROM staging_order s
JOIN imported_order t
  ON t.batch_id = s.batch_id
 AND t.order_id = s.order_id
WHERE s.batch_id = :batchId
  AND s.disposition = 'READY'
  AND s.amount <> t.amount
ORDER BY s.order_id;
~~~

Nếu **NULL** có ý nghĩa nghiệp vụ, toán tử **<>** không bắt được mọi sai khác liên quan NULL. Cần điều kiện null-safe theo database hoặc xác minh trường bắt buộc đã NOT NULL trước khi đối soát.

### Khóa trùng trong nguồn

~~~sql
SELECT order_id, COUNT(*) AS occurrences
FROM staging_order
WHERE batch_id = :batchId
  AND disposition = 'READY'
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Nếu nghiệp vụ cố ý gộp nhiều dòng nguồn thành một dòng đích, phải đổi expected sang **GROUP BY order_id** với quy tắc gộp tiền/số lượng tương ứng. Khi đó duplicate ở staging có thể hợp lệ, còn so sánh vẫn cần theo khóa và phép biến đổi đã xác định.

Nếu writer thực hiện chuyển đổi (làm tròn, chuẩn hóa, split transaction thành nhiều bút toán), expected cũng phải áp dụng **hợp đồng chuyển đổi**, không đơn thuần so giá trị staging nguyên bản với dữ liệu đích.

## 8. Viết service đối soát với Spring JDBC

Ví dụ với Spring Boot 3.x, Spring Batch 5.x, Java 17 và **NamedParameterJdbcTemplate**. Service nhận một batchId đã chốt và trả về report; bảng ví dụ ở phần trước phải tồn tại.

~~~java
import java.math.BigDecimal;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderReconciliationService {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReconciliationService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public ReconciliationResult reconcile(String batchId) {
        Map<String, ?> params = Map.of("batchId", batchId);

        Totals expected = queryTotals("""
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(amount), 0) AS amount_total
            FROM staging_order
            WHERE batch_id = :batchId
              AND disposition = 'READY'
            """, params);

        Totals actual = queryTotals("""
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(amount), 0) AS amount_total
            FROM imported_order
            WHERE batch_id = :batchId
            """, params);

        long missing = queryCount("""
            SELECT COUNT(*) FROM staging_order s
            WHERE s.batch_id = :batchId
              AND s.disposition = 'READY'
              AND NOT EXISTS (
                  SELECT 1 FROM imported_order t
                  WHERE t.batch_id = s.batch_id
                    AND t.order_id = s.order_id
              )
            """, params);

        long unexpected = queryCount("""
            SELECT COUNT(*) FROM imported_order t
            WHERE t.batch_id = :batchId
              AND NOT EXISTS (
                  SELECT 1 FROM staging_order s
                  WHERE s.batch_id = t.batch_id
                    AND s.order_id = t.order_id
                    AND s.disposition = 'READY'
              )
            """, params);

        long wrongAmount = queryCount("""
            SELECT COUNT(*) FROM staging_order s
            JOIN imported_order t
              ON t.batch_id = s.batch_id
             AND t.order_id = s.order_id
            WHERE s.batch_id = :batchId
              AND s.disposition = 'READY'
              AND s.amount <> t.amount
            """, params);

        long duplicateGroups = queryCount("""
            SELECT COUNT(*) FROM (
                SELECT order_id
                FROM staging_order
                WHERE batch_id = :batchId
                  AND disposition = 'READY'
                GROUP BY order_id
                HAVING COUNT(*) > 1
            ) d
            """, params);

        boolean matched =
                expected.count() == actual.count()
                && expected.amount().compareTo(actual.amount()) == 0
                && missing == 0 && unexpected == 0
                && wrongAmount == 0 && duplicateGroups == 0;

        return new ReconciliationResult(
                batchId, expected, actual,
                missing, unexpected, wrongAmount,
                duplicateGroups, matched);
    }

    private Totals queryTotals(String sql, Map<String, ?> params) {
        return jdbc.queryForObject(sql, params, (rs, rowNum) ->
                new Totals(
                    rs.getLong("cnt"),
                    rs.getBigDecimal("amount_total")));
    }

    private long queryCount(String sql, Map<String, ?> params) {
        Long count = jdbc.queryForObject(sql, params, Long.class);
        if (count == null) {
            throw new IllegalStateException("Count query returned null");
        }
        return count;
    }

    public record Totals(long count, BigDecimal amount) {}

    public record ReconciliationResult(
            String batchId,
            Totals expected,
            Totals actual,
            long missingCount,
            long unexpectedCount,
            long wrongAmountCount,
            long duplicateSourceGroups,
            boolean matched) {}
}
~~~

Cách này đưa số liệu **expected**, **actual** và các loại mismatch vào một đối tượng, giúp báo cáo rõ hơn câu thông báo chung “Job có lỗi”.

Một số điều kiện triển khai:

- Mọi truy vấn lọc theo cùng **batchId** và dùng parameter binding.
- **COUNT(*)** là số dòng; duplicateGroups ở đây là số nhóm orderId bị trùng, không phải số dòng dư.
- Nếu dữ liệu nguồn được cập nhật đồng thời, nhiều câu query liên tiếp có thể đọc các snapshot khác nhau. Cần khóa logic kỳ xử lý hoặc transaction isolation/snapshot thích hợp.
- Với hàng triệu dòng, cần index đúng và có thể phân vùng/tổng hợp từng nhóm để tránh quét toàn bộ nhiều lần.
- Report chi tiết có thể lấy thêm danh sách orderId sai qua các truy vấn phần 7, nhưng nên giới hạn payload/log và giữ bằng chứng đầy đủ ở kho audit thích hợp.

## 9. Đặt reconciliation ở đâu trong lifecycle Job?

“Reconciliation sau job” có thể được triển khai theo hai kiểu, cần chọn theo **giao kèo trạng thái nghiệp vụ**.

### 9.1. Reconciliation Step cuối cùng trong cùng Job

Nếu Job **chỉ được coi là thành công khi dữ liệu đã được đối soát**, nên thêm một Step cuối sau Step import:

~~~text
stageInputStep
      |
      v
importOrdersStep
      |
      v
reconcileOrdersStep
      |
  PASS / FAILED
      |
  Job final status
~~~

Ví dụ cấu hình:

~~~java
@Bean
Step reconcileOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        OrderReconciliationService reconciliationService) {

    return new StepBuilder("reconcileOrdersStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                String batchId = chunkContext.getStepContext()
                        .getStepExecution()
                        .getJobExecution()
                        .getJobParameters()
                        .getString("batchId");

                var result = reconciliationService.reconcile(batchId);
                if (!result.matched()) {
                    throw new IllegalStateException(
                        "Reconciliation failed: batchId=" + batchId
                        + ", missing=" + result.missingCount()
                        + ", unexpected=" + result.unexpectedCount()
                        + ", wrongAmount=" + result.wrongAmountCount());
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step stageInputStep,
        Step importOrdersStep,
        Step reconcileOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(stageInputStep)
            .next(importOrdersStep)
            .next(reconcileOrdersStep)
            .build();
}
~~~

Ví dụ giả định các bean nhập dữ liệu đã được định nghĩa và **batchId** là identifying JobParameter. Nếu reconciliation Step ném exception chưa được xử lý, Step và Job sẽ kết thúc **FAILED** theo cơ chế flow bình thường.

**Chú ý audit transaction:** Nếu lưu discrepancy report trong cùng transaction của Tasklet rồi ném exception, ghi chép đó có thể bị rollback. Hãy lưu báo cáo bằng transaction độc lập phù hợp hoặc cơ chế audit bền vững, sau đó phát lỗi để Job phản ánh đúng trạng thái.

**Chú ý restart:** Khi Job đã hoàn thành Step import nhưng thất bại ở Step đối soát, restart cùng JobInstance thường bỏ qua các Step đã COMPLETED. Nếu lỗi bắt nguồn từ import sai, chỉ chạy lại đối soát sẽ không sửa dữ liệu. Cần có quy trình remedial import/reprocess idempotent hoặc một chính sách chạy lại Step có kiểm soát.

### 9.2. Reconciliation thật sự chạy sau khi Job đã kết thúc

Một hệ thống có thể cần chờ dữ liệu downstream, một service audit riêng hoặc nhiều Job cùng hoàn tất mới đối soát. Có thể dùng **JobExecutionListener.afterJob(...)** để phát tín hiệu/ghi log:

~~~java
@Component
public class ReconciliationSignalListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ReconciliationSignalListener.class);

    @Override
    public void afterJob(JobExecution execution) {
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            return;
        }

        log.info(
            "Reconciliation required: jobExecutionId={}, batchId={}",
            execution.getId(),
            execution.getJobParameters().getString("batchId"));
    }
}
~~~

**Không dựa vào exception ném từ afterJob để bảo đảm Job chuyển thành FAILED.** Callback xảy ra ở giai đoạn kết thúc; nếu reconciliation phải quyết định thành công/thất bại của Job, dùng một Step rõ ràng. Khi audit chạy **bất đồng bộ bên ngoài Job**, theo dõi trạng thái riêng: **PENDING, RUNNING, PASSED, FAILED, INCONCLUSIVE**.

Ví dụ một Job có thể **COMPLETED** nhưng workflow nghiệp vụ vẫn **PENDING_RECONCILIATION**. Hệ thống công bố dữ liệu nên kiểm tra trạng thái đối soát trước khi phát hành nếu đó là yêu cầu kinh doanh.

Việc gửi thông báo audit cần bền vững và idempotent; một dòng log sau Job không thay thế được outbox, queue có retry hoặc bảng yêu cầu đối soát.

## 10. Báo cáo sai lệch và quy trình khắc phục

Một bản ghi báo cáo nên chứa:

| Trường | Ví dụ |
| --- | --- |
| batchId | batch-20261115-001 |
| businessDate | 2026-11-15 |
| sourceVersion | snapshot-v3 |
| jobExecutionId | 8542 |
| reconciliationRunId | recon-003 |
| checkedAt | 2026-11-16T02:15:00Z |
| expectedCount / actualCount | 8 / 7 |
| expectedAmount / actualAmount | 1250.00 / 1150.00 |
| missingCount | 1 |
| unexpectedCount | 0 |
| wrongAmountCount | 0 |
| duplicateSourceGroups | 0 |
| status | FAILED |
| ruleVersion | recon-orders-v2 |

Một quy trình vận hành thường gồm:

~~~text
PENDING -> RUNNING
             |
         +---+----------+
         |              |
       PASSED         MISMATCH
         |              |
       Publish       Save report
                        |
                    Investigate
                        |
                    Remediate
                        |
                    RECHECK
                        |
                    PASSED / FAILED
~~~

Nếu nguồn hoặc hệ thống đích tạm thời chưa sẵn sàng, dùng **INCONCLUSIVE** và retry theo chính sách. Không đánh dấu PASS khi chưa có đủ bằng chứng.

Báo cáo nên ghi mẫu khóa sai lệch để dễ điều tra, nhưng không ghi toàn bộ dữ liệu nhạy cảm vào log. Lịch sử các lần reconciliation và remediation phải được giữ lại để audit; không xóa sạch mismatch cũ sau khi sửa.

## 11. Phân biệt StepExecution counts với kết quả nghiệp vụ

Spring Batch cung cấp **StepExecution** với các count như:

| Count | Ý nghĩa | Giới hạn khi đối soát |
| --- | --- | --- |
| readCount | Item đọc thành công | Không luôn bằng số dòng vật lý, nhất là khi reader skip lỗi |
| writeCount | Item framework ghi nhận được viết | Không đảm bảo giá trị hay khóa đúng ở đích |
| filterCount | Item processor trả về null | Có thể là loại hợp lệ theo chính sách |
| read/process/write skipCount | Lỗi được skip theo vị trí | Không chứng minh các skip đều được nghiệp vụ chấp thuận |
| commitCount | Transaction commit được ghi nhận | Không phải số item |
| rollbackCount | Transaction rollback được ghi nhận | Không nói trực tiếp số item bị mất |

Đối với fixture đơn giản:

~~~text
readCount = 10
filterCount = 1
processSkipCount = 1
writeCount = 8

Expected business rows = 8
Actual rows should be 8, correct keys and amounts
~~~

Chỉ có thể đối soát cuối cùng khi **expected được xác định từ nguồn đáng tin cậy** và **actual được truy vấn từ dữ liệu thực tế**. Các count giúp chẩn đoán Step hoạt động ra sao khi có mismatch.

## 12. Reconciliation khi Job restart

Ví dụ:

~~~text
JobInstance: importOrdersJob(batchId=batch-001)
  |
  +-- JobExecution #1: FAILED
  |      Chunk đầu đã commit
  |      Chunk sau bị rollback
  |
  +-- JobExecution #2: COMPLETED
         Reader khôi phục checkpoint
         Xử lý tiếp dữ liệu
         Reconcile kết quả cuối
~~~

Các quy tắc:

1. Dùng **cùng identifying JobParameters** cho lần restart của một JobInstance.
2. Snapshot nguồn và business rules phải nhất quán giữa hai lần chạy.
3. Writer cần **idempotency key** hoặc unique constraint để tránh trùng nếu xử lý lại.
4. Đối soát **dữ liệu đích cuối cùng theo batchId**, không chỉ count của StepExecution gần nhất.
5. Không cộng bừa các count của nhiều StepExecution để kết luận số business records duy nhất.

Nếu một Step import đã COMPLETED nhưng reconciliation FAILED, restart có thể chỉ chạy Step đối soát. Nếu cần sửa dữ liệu đích, phải thực hiện remediation trước hoặc thiết kế riêng một Step sửa lỗi có thể chạy lại an toàn.

## 13. Downstream và eventual consistency

Một pipeline thường có dạng:

~~~text
Spring Batch -> Message broker -> Consumer -> Data warehouse
~~~

Job có thể hoàn thành sau khi producer gửi message, nhưng warehouse chưa ghi xong. Đối soát ngay lúc Job COMPLETED sẽ thấy thiếu dữ liệu tạm thời.

Cần phân biệt:

- **Producer sent/acknowledged:** dữ liệu đã gửi vào broker theo contract của producer.
- **Consumer processed:** consumer xử lý message.
- **Target persisted:** dữ liệu đã tồn tại trong hệ thống đích.
- **Business finalized:** đã PASS reconciliation.

Nên chờ acknowledgement hoặc watermark theo batchId, có deadline rõ ràng, rồi đối soát. Khi điều kiện đồng bộ chưa đạt, ghi **PENDING/INCONCLUSIVE** thay vì MISMATCH vội vàng. Hết timeout có thể nâng mức cảnh báo.

Trong hệ thống phân tán, API bên ngoài có thể đã nhận side effect trước khi Step commit checkpoint. Restart có thể gửi lại request. **Reconciliation phát hiện sai lệch sau xử lý**; để ngăn duplicate cần thêm idempotency, outbox, deduplication và ràng buộc ở đích.

## 14. Đối soát dữ liệu lớn

Truy vấn so từng dòng hàng trăm triệu bản ghi có thể tốn I/O. Một chiến lược thực tế:

1. **Aggregate nhanh:** count, sum, min/max, tổng theo currency/status.
2. **Chia phạm vi:** đối soát theo businessDate, batchId, tenant hoặc partition.
3. **Tìm nhóm sai:** count và sum theo nhóm nhỏ để thu hẹp vùng discrepancy.
4. **So từng key:** SQL anti-join tìm missing/extra; join tìm field mismatch.
5. **Lưu kết quả:** chỉ trả mẫu nhỏ lên dashboard, lưu dữ liệu đầy đủ ở kho báo cáo thích hợp.

Ví dụ:

~~~sql
SELECT
    batch_id,
    disposition,
    COUNT(*) AS row_count,
    COALESCE(SUM(amount), 0) AS total_amount
FROM staging_order
WHERE batch_id = :batchId
GROUP BY batch_id, disposition;
~~~

Lưu ý:

- Index trên batch_id và các cột join/filter giúp giảm full scan.
- Với input/target đang thay đổi, cần snapshot/transaction isolation thích hợp.
- Nếu dùng read replica, replication lag có thể tạo mismatch giả.
- Hash/checksum có thể giúp định vị vùng sai nhưng không đảm bảo tuyệt đối không có collision hoặc vấn đề canonicalization.
- Trường tiền cần quy tắc precision, scale, rounding và currency nhất quán.
- Dữ liệu lớn có thể dùng partition và parallel reconciliation, nhưng phải cộng đúng phạm vi, tránh trùng.

## 15. Kiểm thử reconciliation

Bộ test tối thiểu nên bao phủ các tình huống sau:

| Kịch bản | Expected | Actual | Kết quả |
| --- | --- | --- | --- |
| Đủ 8 đơn | 8 khóa, tổng 1250.00 | Đúng khóa/tiền | PASS |
| Thiếu O-103 | 8 khóa | 7 khóa | Missing |
| Thêm O-999 | 8 khóa | 9 khóa | Unexpected |
| Sai amount O-101 | 100.00 | 90.00 | Wrong amount |
| Hai amount sai bù trừ | Tổng vẫn bằng nhau | Hai dòng sai | Field mismatch |
| Hai READY dòng cùng orderId | Key bị trùng ở staging | Một key tại đích | Duplicate source |
| Job fail giữa chunk | Input chưa hoàn tất | Dữ liệu chưa đầy đủ | Chờ restart/remediation |
| Downstream chưa bắt kịp | Input đã chốt | Target đang xử lý | PENDING/INCONCLUSIVE |

### Unit/integration test cho service

Với Spring Boot Test, seed dữ liệu vào database test rồi gọi service:

~~~java
@Test
void shouldDetectMissingOrder() {
    String batchId = "missing-order-fixture";

    // Fixture:
    // staging: O-101 và O-102 đều READY.
    // target: chỉ có O-101.

    var report = reconciliationService.reconcile(batchId);

    assertThat(report.matched()).isFalse();
    assertThat(report.missingCount()).isEqualTo(1);
    assertThat(report.expected().count()).isEqualTo(2);
    assertThat(report.actual().count()).isEqualTo(1);
}
~~~

Fixture cần được chuẩn bị thật trước test. Nếu chỉ mock các query trả về count như mong muốn, test sẽ không chứng minh anti-join SQL hoạt động đúng.

### Integration test toàn Job

Nếu reconciliation là Step cuối, có thể dùng **spring-batch-test** và **JobLauncherTestUtils**:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ReconciliationJobTest {

    @Autowired
    private JobLauncherTestUtils testUtils;

    @Test
    void completesWhenReconciliationPasses() throws Exception {
        String batchId = UUID.randomUUID().toString();
        // Seed staging fixture với batchId và output kỳ vọng.

        JobParameters params = new JobParametersBuilder()
                .addString("batchId", batchId, true)
                .toJobParameters();

        JobExecution job = testUtils.launchJob(params);

        assertThat(job.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(job.getStepExecutions())
                .anyMatch(step ->
                    step.getStepName().equals("reconcileOrdersStep")
                    && step.getStatus() == BatchStatus.COMPLETED);
    }
}
~~~

Giả định JobLauncher đồng bộ, fixture tồn tại, Job được set đúng trong test utility và bảng nguồn/đích đã được chuẩn bị. Nên có test thứ hai tạo sai lệch ở đích và xác nhận **reconcileOrdersStep FAILED**, kéo Job thành FAILED.

Với audit chạy ngoài Job, kiểm tra **reconciliation status** và quyền công bố dữ liệu trong workflow thay vì chỉ xem BatchStatus.

### Kiểm thử restart và idempotency

Một test quan trọng cần thực hiện:

1. Cho Job import chunk đầu thành công.
2. Tạo lỗi có kiểm soát ở chunk sau.
3. Restart cùng JobInstance và giữ nguyên dữ liệu nguồn.
4. Kiểm tra kết quả đích **đầy đủ, không trùng**.
5. Chạy reconciliation, yêu cầu PASS và kiểm tra lịch sử execution.

Test này xác minh rằng checkpoint/restart vẫn tạo dữ liệu đúng; nó cũng giúp phát hiện lỗi writer gửi side effect hai lần.

## 16. Sai lầm thường gặp

**Chỉ xem BatchStatus.COMPLETED.** Trạng thái phản ánh flow kỹ thuật, không chứng minh dữ liệu đúng.

**Chỉ so COUNT(*).** Thiếu một khóa và thêm một khóa khác vẫn làm count bằng nhau.

**Chỉ so SUM(amount).** Hai sai lệch trái dấu có thể bù trừ; cần so theo business key.

**Dùng writeCount làm expected.** Đây không phải nguồn kỳ vọng độc lập.

**Tính expected và actual trên cùng bảng đích.** Phép kiểm tra trở thành tự đối chiếu và bỏ sót lỗi.

**Không khóa phạm vi kỳ xử lý.** Dữ liệu từ batch khác bị trộn vào count/sum.

**Không xử lý NULL, currency, rounding.** Giá trị có thể trông bằng nhau nhưng sai nghiệp vụ hoặc bị so sánh sai.

**Dùng afterJob exception để buộc FAILED.** Nếu reconciliation phải quyết định trạng thái Job, dùng một Step phù hợp.

**Lưu báo cáo lỗi trong transaction sẽ rollback.** Báo cáo có thể biến mất khi Step ném exception.

**Đối soát trước khi downstream ổn định.** Replication lag hoặc message lag tạo false mismatch.

**Không lưu lịch sử remediation.** Sau khi sửa dữ liệu, hệ thống mất bằng chứng về lần đối soát thất bại.

## 17. Checklist áp dụng trong production

- [ ] Có **batchId/businessDate/sourceVersion** cố định.
- [ ] Snapshot nguồn được chốt trước khi so sánh.
- [ ] Quy tắc READY, CANCELLED, INVALID và skip được định nghĩa rõ.
- [ ] Có nguồn expected độc lập với output đang kiểm tra.
- [ ] So count, tổng số tiền/quantity và tập business key.
- [ ] So các trường quan trọng sau đúng transformation rules.
- [ ] Phát hiện missing, unexpected, duplicate và mismatched values.
- [ ] Xử lý rõ decimal precision, rounding, NULL và currency.
- [ ] Chọn reconciliation Step hay external audit phù hợp trạng thái Job.
- [ ] Lưu kết quả, discrepancy, ruleVersion, lần kiểm tra và lịch sử sửa lỗi.
- [ ] Có PENDING/INCONCLUSIVE cho nguồn hoặc downstream chưa ổn định.
- [ ] Có chính sách chặn công bố dữ liệu khi chưa PASSED.
- [ ] Có kế hoạch remediation và restart/idempotency an toàn.
- [ ] Có SQL/index/snapshot strategy phù hợp quy mô dữ liệu.
- [ ] Có test cho đúng, thiếu, thừa, sai tiền, trùng, restart và downstream lag.

## 18. Luồng vận hành tham khảo

~~~text
1. Nhận nguồn + manifest
                |
                v
2. Chốt staging snapshot theo batchId
                |
                v
3. Chạy Spring Batch import
                |
          +-----+------+
          |            |
       FAILED      Import COMPLETED
          |            |
      Retry /          v
      Restart      Reconciliation
                       |
                +------+------+
                |             |
               PASS        MISMATCH
                |             |
             Publish      Audit + Alert
                              |
                          Remediate
                              |
                           Recheck
~~~

Một lần chạy chỉ thực sự đạt yêu cầu chất lượng khi kết quả được xác nhận theo **đúng lô, đúng kỳ, đúng business key, đúng giá trị** và tuân thủ chính sách công bố dữ liệu. Các count của StepExecution giúp giải thích quá trình xử lý; reconciliation dùng nguồn kỳ vọng độc lập để xác minh kết quả cuối. Kết hợp đối soát với audit, restart và writer idempotent giúp phát hiện sai lệch sớm, hỗ trợ khắc phục và giảm nguy cơ lan truyền dữ liệu sai sang hệ thống downstream.

