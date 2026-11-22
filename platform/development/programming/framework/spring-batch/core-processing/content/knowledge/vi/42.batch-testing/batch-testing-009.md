# Assert `StepExecution` counts trong Spring Batch

## 1. Vì sao cần kiểm tra các bộ đếm của `StepExecution`?

Trong Spring Batch, một `Step` có thể kết thúc với trạng thái `COMPLETED` nhưng kết quả xử lý vẫn không đúng nghiệp vụ. Chẳng hạn, job nhập 100 bản ghi chạy thành công nhưng chỉ ghi được 90 bản ghi; 10 bản ghi còn lại có thể đã bị lọc theo chủ đích, bị bỏ qua do lỗi, hoặc không đi qua luồng xử lý như mong đợi. Chỉ kiểm tra `BatchStatus.COMPLETED` không phân biệt được các tình huống đó.

`StepExecution` lưu thông tin của **một lần thực thi Step**, gồm trạng thái, thời điểm, các exception và nhiều bộ đếm. Trong kiểm thử batch, việc *assert counts* nghĩa là so sánh những bộ đếm ấy với kết quả kỳ vọng từ bộ dữ liệu kiểm thử đã biết trước.

Sau bài này, bạn có thể:

- Phân biệt `readCount`, `writeCount`, `filterCount`, các loại `skipCount`, `commitCount` và `rollbackCount`.
- Chạy một Step trong test bằng `spring-batch-test` rồi lấy đúng `StepExecution` để kiểm tra.
- Viết assertion cho luồng bình thường, luồng lọc dữ liệu và luồng chịu lỗi (*fault tolerant*).
- Giải thích vì sao phép so sánh số lượng có thể sai khi Step có retry, rollback, restart hoặc partition.

## 2. `StepExecution` và ý nghĩa của các count

Mỗi lần một `Step` được thực thi, Spring Batch ghi nhận một đối tượng `StepExecution` tương ứng. Hai lần chạy cùng một tên Step có thể tạo ra hai `StepExecution` khác nhau. Vì vậy, một count luôn cần được hiểu trong **phạm vi lần thực thi** mà bạn đang assert.

Các thuộc tính thường dùng:

| Phương thức | Ý nghĩa trong Step xử lý item | Khi nào nên assert? |
| --- | --- | --- |
| `getReadCount()` | Số item mà reader đọc thành công và chuyển vào xử lý; không phải số dòng có sẵn trong nguồn dữ liệu. | Xác nhận số item được tiếp nhận từ bộ dữ liệu kiểm thử. |
| `getWriteCount()` | Số item được Spring Batch tính là đã ghi qua writer. | Xác nhận lượng output mà Step ghi nhận. |
| `getFilterCount()` | Số item bị loại vì `ItemProcessor` trả về `null`. | Xác nhận quy tắc lọc dữ liệu hoạt động đúng. |
| `getReadSkipCount()` | Số lỗi đọc được chính sách skip cho phép bỏ qua. | Kiểm thử dữ liệu nguồn lỗi hoặc reader có thể skip. |
| `getProcessSkipCount()` | Số item có lỗi ở processor được skip. | Kiểm thử các lỗi chuyển đổi, kiểm tra dữ liệu. |
| `getWriteSkipCount()` | Số item có lỗi ở writer được skip. | Kiểm thử lỗi ghi khi cấu hình cho phép skip. |
| `getSkipCount()` | Tổng số lần skip: read skip + process skip + write skip. | Kiểm tra tổng skip và đối chiếu với từng loại. |
| `getCommitCount()` | Số lần transaction commit được Step ghi nhận. | Khi kiểm thử hành vi giao dịch/chunk và đã kiểm soát cấu hình. |
| `getRollbackCount()` | Số lần rollback được Step ghi nhận. | Khi kiểm thử rollback/retry hay xử lý lỗi giao dịch. |

Ngoài count, các thuộc tính cần đọc cùng nhau là `getStatus()` (giá trị kiểu `BatchStatus`), `getExitStatus()` (kiểu `ExitStatus`) và `getFailureExceptions()`.

### Luồng item làm thay đổi count như thế nào?

```text
                    ItemReader
                        |
           đọc thành công: readCount + 1
                        |
                        v
                  ItemProcessor
                        |
           +------------+-------------+
           |            |             |
       trả về null   trả về item   lỗi được skip
           |            |             |
   filterCount + 1      |     processSkipCount + 1
                        v
                    ItemWriter
                        |
           ghi thành công: writeCount
                        |
                  transaction commit

  Lỗi reader được skip  --> readSkipCount + 1
  Lỗi writer được skip  --> writeSkipCount + 1
```

Sơ đồ trên mô tả trường hợp đơn giản. Với chunk processing, writer nhận một **chunk gồm nhiều item**, không nhất thiết được gọi một lần cho từng item. Khi có retry hoặc rollback, các item có thể được xử lý lại; do đó không nên tự suy ra chính xác mọi count chỉ từ số lần phương thức reader/processor/writer được gọi.

### `filter` khác `skip`

Hai khái niệm này dễ bị nhầm:

- **Filter** là loại item một cách bình thường: `ItemProcessor#process` trả về `null`. `filterCount` tăng, không xem là lỗi, và không làm tăng `skipCount`.
- **Skip** là xử lý lỗi theo chính sách đã khai báo: một exception thuộc loại được phép skip xảy ra ở reader, processor hoặc writer. Count của vị trí lỗi tăng tương ứng.

Ví dụ, đọc 6 item: `A`, `B`, `IGNORE`, `C`, `BROKEN`, `D`. Processor loại `IGNORE`, còn `BROKEN` làm phát sinh exception được phép skip; các item còn lại được ghi thành công. Trong một lần chạy không có retry/rollback phát sinh ngoài ý muốn, ta kỳ vọng:

| Count | Kỳ vọng | Giải thích |
| --- | ---: | --- |
| `readCount` | 6 | Cả sáu item đã được reader đọc thành công. |
| `filterCount` | 1 | `IGNORE` bị lọc. |
| `processSkipCount` | 1 | `BROKEN` gây lỗi tại processor và được skip. |
| `writeCount` | 4 | `A`, `B`, `C`, `D` được ghi. |
| `readSkipCount` | 0 | Reader không gặp lỗi được skip. |
| `writeSkipCount` | 0 | Writer không gặp lỗi được skip. |
| `skipCount` | 1 | Chỉ có một process skip. |

Trong trường hợp này, công thức đối chiếu hợp lệ là:

```text
readCount = writeCount + filterCount + processSkipCount
        6 =          4 +           1 +                1
```

**Không coi công thức trên là invariant cho mọi Step.** Read skip, write skip, retry, rollback, restart, dữ liệu trùng, hay luồng writer đặc biệt có thể khiến phép đối chiếu đơn giản không còn thích hợp. Hãy thiết lập kỳ vọng dựa trên từng kịch bản thực tế.

## 3. Thiết lập kiểm thử Step bằng `spring-batch-test`

Ví dụ dưới đây dùng **Spring Batch 5.x, Spring Boot 3.x, JUnit 5 và AssertJ**. Đây là cách viết phù hợp khi dự án đã cấu hình một `Job` chứa Step tên `importCustomersStep` và có dữ liệu kiểm thử ổn định.

Nếu dùng Maven, thông thường dự án cần dependency kiểm thử như sau (phiên bản Spring Batch nên được BOM của Spring Boot quản lý):

```xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

`@SpringBatchTest` cung cấp các tiện ích kiểm thử batch, trong đó có `JobLauncherTestUtils`. `@SpringBootTest` khởi tạo application context chứa Job, Step, `JobRepository`, transaction manager và các bean liên quan. Với một ứng dụng Spring Boot, nên tắt chạy Job tự động trong test để chính test quyết định lúc nào khởi chạy:

```java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportCustomersStepTest {
    // Các ví dụ assertion nằm ở phần tiếp theo.
}
```

Test cần một `Job` và `Step` khả dụng trong context. Nếu có **nhiều Job**, hãy cấu hình rõ Job mục tiêu cho `JobLauncherTestUtils` (chẳng hạn inject Job bằng `@Qualifier` và gọi `jobLauncherTestUtils.setJob(job)` trước khi launch). Cấu hình repository/schema và dữ liệu đầu vào nên dùng môi trường kiểm thử độc lập để không phụ thuộc dữ liệu thật.

## 4. Chạy Step và assert các count cơ bản

Giả sử Step `importCustomersStep` được thiết kế để đọc sáu bản ghi như bảng ở phần 2. Processor trả về `null` với `IGNORE`; một exception cho `BROKEN` đã được cấu hình là skippable; writer ghi bốn item hợp lệ. Ví dụ integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportCustomersStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void shouldAssertStepExecutionCounts() throws Exception {
        // Dữ liệu test đã được chuẩn bị riêng: A, B, IGNORE, C, BROKEN, D.
        JobParameters parameters = new JobParametersBuilder()
                .addLong("test.run.id", System.nanoTime())
                .toJobParameters();

        JobExecution jobExecution = jobLauncherTestUtils.launchStep(
                "importCustomersStep", parameters);

        StepExecution stepExecution = jobExecution.getStepExecutions().stream()
                .filter(step -> "importCustomersStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "Không tìm thấy StepExecution của importCustomersStep"));

        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        assertThat(stepExecution.getReadCount()).isEqualTo(6);
        assertThat(stepExecution.getFilterCount()).isEqualTo(1);
        assertThat(stepExecution.getWriteCount()).isEqualTo(4);

        assertThat(stepExecution.getReadSkipCount()).isZero();
        assertThat(stepExecution.getProcessSkipCount()).isEqualTo(1);
        assertThat(stepExecution.getWriteSkipCount()).isZero();
        assertThat(stepExecution.getSkipCount()).isEqualTo(1);
    }
}
```

Những điều kiện cần có để test thực sự phản ánh kịch bản:

1. Reader phải đọc đúng bộ dữ liệu được chuẩn bị cho từng lần launch. Với reader có trạng thái như `ListItemReader`, cần tạo instance mới cho mỗi lần thực thi (ví dụ khai báo reader `@StepScope`) hoặc chủ động reset dữ liệu đúng cách.
2. Processor phải lọc `IGNORE` bằng cách trả về `null`; lỗi với `BROKEN` phải thuộc loại được cấu hình `skip` và chưa vượt `skipLimit`.
3. Writer phải ghi bốn item hợp lệ. Nếu kiểm thử writer thật, nên assert thêm nội dung bảng/file/đích ghi, bởi `writeCount` không tự chứng minh mọi side effect bên ngoài đã đúng.
4. `test.run.id` tạo tham số nhận diện lần chạy để tránh trường hợp repository coi đây là một `JobInstance` đã hoàn thành trước đó. Với test lặp, UUID hoặc một định danh test riêng cũng phù hợp.

Nếu điều quan trọng là hành vi **toàn bộ Job**, có thể dùng `jobLauncherTestUtils.launchJob(parameters)` và lấy Step tương ứng từ `JobExecution`. Nếu chỉ muốn chạy một Step có tên cụ thể, `launchStep(...)` gọn hơn; nhớ rằng cách chạy Step trực tiếp không kiểm thử đầy đủ luồng chuyển Step hay các Job listener của Job gốc.

### Truy xuất đúng `StepExecution`

Một `JobExecution` có thể chứa nhiều `StepExecution`. Không nên mặc định rằng phần tử đầu tiên trong `getStepExecutions()` là Step cần kiểm tra:

```java
StepExecution stepExecution = jobExecution.getStepExecutions().stream()
        .filter(s -> "importCustomersStep".equals(s.getStepName()))
        .findFirst()
        .orElseThrow();
```

Với test yêu cầu Step chỉ thực thi một lần, có thể assert điều kiện đó trước:

```java
assertThat(jobExecution.getStepExecutions())
        .filteredOn(s -> s.getStepName().equals("importCustomersStep"))
        .hasSize(1);
```

Nếu Step có nhiều lần thực thi hay job dùng partition, phải lựa chọn hoặc tổng hợp các lần thực thi phù hợp với mục tiêu test, thay vì dùng `findFirst()` tùy ý.

## 5. Các kịch bản assertion thường gặp

### 5.1. Không lọc, không skip

Reader trả về 12 item, processor biến đổi cả 12 và writer nhận đủ 12 item:

```java
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getReadCount()).isEqualTo(12);
assertThat(stepExecution.getWriteCount()).isEqualTo(12);
assertThat(stepExecution.getFilterCount()).isZero();
assertThat(stepExecution.getSkipCount()).isZero();
```

Đây là đường đi chuẩn (*happy path*). Nếu `readCount = 12` nhưng `writeCount = 10`, có thể hai item đã bị lọc; vì vậy assertion `filterCount == 0` giúp tìm ra sai lệch nhanh hơn chỉ kiểm tra tổng output.

### 5.2. Lọc item hợp lệ theo quy tắc nghiệp vụ

Ví dụ, Step đọc tám giao dịch, hai giao dịch không thỏa điều kiện được lọc bằng `return null`, sáu giao dịch còn lại được ghi:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(8);
assertThat(stepExecution.getFilterCount()).isEqualTo(2);
assertThat(stepExecution.getWriteCount()).isEqualTo(6);
assertThat(stepExecution.getSkipCount()).isZero();
```

Ở đây hai giao dịch bị loại là kết quả mong đợi. Nếu test lại assert `writeCount == readCount`, test sẽ sai về mặt nghiệp vụ ngay cả khi code xử lý đúng.

### 5.3. Bỏ qua lỗi trong processor

Để một lỗi processor được tính là skip, Step phải có cấu hình fault tolerance, ví dụ:

```java
new StepBuilder("importCustomersStep", jobRepository)
        .<String, Customer>chunk(3, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(InvalidCustomerException.class)
        .skipLimit(2)
        .build();
```

Trong đoạn cấu hình trên, `InvalidCustomerException` là exception nghiệp vụ do ứng dụng định nghĩa; `customerReader`, `customerProcessor` và `customerWriter` là các bean tương ứng của ứng dụng. Với một item gây `InvalidCustomerException` tại processor và chỉ một item được filter như ví dụ trước:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(6);
assertThat(stepExecution.getProcessSkipCount()).isEqualTo(1);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(4);
assertThat(stepExecution.getSkipCount()).isEqualTo(1);
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

`skipLimit(2)` nghĩa là có thể bỏ qua tối đa hai lỗi thuộc nhóm cho phép skip. Lỗi vượt giới hạn có thể khiến Step thất bại. Một test vượt giới hạn nên kiểm tra trạng thái `FAILED` và nguyên nhân lỗi, thay vì mặc định rằng count vẫn theo đúng phép cộng trong kịch bản thành công.

### 5.4. Phân biệt lỗi khi đọc và khi ghi

Mỗi loại skip nói lên lỗi xuất hiện ở đâu:

```java
assertThat(stepExecution.getReadSkipCount()).isEqualTo(expectedReadSkips);
assertThat(stepExecution.getProcessSkipCount()).isEqualTo(expectedProcessSkips);
assertThat(stepExecution.getWriteSkipCount()).isEqualTo(expectedWriteSkips);

assertThat(stepExecution.getSkipCount()).isEqualTo(
        expectedReadSkips + expectedProcessSkips + expectedWriteSkips);
```

Nếu chỉ kiểm tra `getSkipCount() == 2`, test không cho biết hai lỗi đó phát sinh tại reader, processor hay writer. Khi nghiệp vụ có kỳ vọng cụ thể về loại dữ liệu bị lỗi, nên kiểm tra từng bộ đếm để giữ thông tin chẩn đoán.

Với lỗi đọc, một item không đọc thành công thường **không** đóng góp vào `readCount`; lỗi được skip lại được thể hiện bằng `readSkipCount`. Vì thế, đừng mặc định `readCount` bằng số bản ghi vật lý trong file khi file có dòng lỗi.

### 5.5. `commitCount` và `rollbackCount`

Giả sử Step xử lý theo chunk size 5. Trong kịch bản thuận lợi, bạn có thể dự đoán số transaction xử lý, nhưng **không nên lấy** công thức `ceil(readCount / chunkSize)` để áp dụng máy móc cho `commitCount`. Giao dịch kiểm tra kết thúc dữ liệu, framework, lỗi, restart và cách Step được cấu hình có thể ảnh hưởng count.

Với test chỉ cần chắc chắn đã có giao dịch thành công và không có rollback:

```java
assertThat(stepExecution.getCommitCount()).isPositive();
assertThat(stepExecution.getRollbackCount()).isZero();
```

Chỉ assert chính xác `commitCount` hoặc `rollbackCount` khi đó là **hành vi đang được kiểm thử**, môi trường đã được cố định, và test kiểm soát nơi phát sinh lỗi, retry cùng ranh giới transaction. Rollback không đồng nghĩa với skip: một lỗi có thể làm rollback rồi được retry thành công; hoặc cuối cùng được skip theo chính sách Step.

## 6. Kiểm tra trạng thái cùng với count

Một count đơn lẻ không xác định liệu Step thành công hay thất bại. `BatchStatus` thể hiện trạng thái thực thi (`COMPLETED`, `FAILED`, `STOPPED`...), còn `ExitStatus` thể hiện kết quả kết thúc phục vụ luồng điều hướng hoặc kết quả tùy chỉnh.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;

assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.COMPLETED.getExitCode());
assertThat(stepExecution.getFailureExceptions()).isEmpty();
```

Không nên luôn cố định `ExitStatus.COMPLETED`: ứng dụng có thể dùng `ExitStatus` riêng như `COMPLETED_WITH_SKIPS`. Khi đó cần assert đúng giao kèo ứng dụng. Tương tự, một Step có thể `COMPLETED` dù `skipCount > 0`, nếu skip được cho phép và không vượt giới hạn.

Đối với kịch bản thất bại, ví dụ lỗi không được phép skip:

```java
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(stepExecution.getFailureExceptions()).isNotEmpty();
```

Có thể bổ sung assertion count tại thời điểm thất bại nếu mục tiêu là kiểm tra tiến độ xử lý trước lỗi. Hãy dựa trên semantics của Step đã cấu hình, vì một chunk bị rollback có thể ảnh hưởng số liệu ghi nhận.

## 7. Kiểm thử đơn vị với `MetaDataInstanceFactory`

Không phải test nào cũng cần chạy toàn bộ Step. Nếu bạn muốn kiểm tra một listener, formatter hoặc service **nhận `StepExecution` làm đầu vào**, `spring-batch-test` có `MetaDataInstanceFactory` để tạo đối tượng metadata cho unit test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.assertj.core.api.Assertions.assertThat;

class StepExecutionMetadataTest {

    @Test
    void shouldExposePreparedCounts() {
        StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
        stepExecution.setReadCount(10);
        stepExecution.setFilterCount(2);
        stepExecution.setWriteCount(8);

        assertThat(stepExecution.getReadCount()).isEqualTo(10);
        assertThat(stepExecution.getFilterCount()).isEqualTo(2);
        assertThat(stepExecution.getWriteCount()).isEqualTo(8);
    }
}
```

Đoạn trên minh họa cách **khởi tạo metadata giả lập**; tự đặt giá trị rồi tự assert cùng giá trị không chứng minh reader/processor/writer hoạt động đúng. Trong thực tế, hãy truyền `stepExecution` đã thiết lập vào **logic cần kiểm thử** (ví dụ một service tạo thông báo thống kê) và assert đầu ra của logic đó. Nếu cần xác minh count do quá trình batch thật tạo ra, phải launch Step/Job như phần 4.

## 8. Các điểm dễ gây assertion sai

### Dữ liệu đầu vào không ổn định

Nếu test dùng bảng đã có bản ghi từ lần chạy trước, số item thực đọc có thể tăng bất ngờ. Nên sử dụng fixture với dữ liệu xác định, dọn dữ liệu sau test hoặc dùng database riêng; đồng thời làm rõ liệu reader có phân trang, lọc tại câu SQL hay loại dữ liệu tại processor. Bản ghi đã bị loại ngay trong truy vấn **không** làm tăng `filterCount`, vì chưa tới processor.

### Reader giữ trạng thái giữa các lần chạy

Một `ListItemReader` hoặc reader có cursor được tái sử dụng có thể không đọc lại bộ dữ liệu từ đầu. Khi test Step nhiều lần, tạo reader mới cho mỗi `StepExecution` (thường nhờ `@StepScope`) hoặc cấu hình lifecycle đúng. Cấu hình sai sẽ làm `readCount` thấp hơn kỳ vọng dù không có lỗi nghiệp vụ.

### Retry và rollback

Một item thất bại lần đầu có thể được retry và xử lý thành công lần sau. Số lần gọi processor/writer có thể lớn hơn số item cuối cùng được ghi. Tương tự, rollback có thể khiến một chunk được thực thi lại; vì vậy không suy luận `readCount` từ số lần mock ghi nhận phương thức đã gọi, hoặc `writeCount` từ số lần writer được gọi, khi kiểm thử fault tolerance.

### Restart và những lần thực thi khác nhau

Khi Job restart, `StepExecution` của lần trước và lần sau là các đối tượng khác nhau. Nếu muốn kiểm tra số item **của một lần chạy**, dùng count từ đúng lần thực thi đó. Nếu muốn kiểm tra kết quả tổng hợp của cả quá trình restart, cần xác định rõ chỉ số nào được cộng dồn, tránh đếm lại item đã ghi trước khi restart; trong nhiều trường hợp, kiểm tra dữ liệu đầu ra thực tế sẽ có ý nghĩa hơn phép cộng count thuần túy.

### Partitioning và parallel Step

Trong một partitioned Step, mỗi worker partition có thể có `StepExecution` riêng, còn manager Step có thông tin tổng hợp. Không cộng tất cả StepExecution một cách mù quáng vì có nguy cơ đếm trùng số liệu của manager và worker. Nếu cần tổng theo partition, chọn đúng tập worker executions và đối chiếu theo cơ chế aggregation của cấu hình cụ thể. Với multi-threaded Step, thứ tự xử lý cũng không được đảm bảo, nên ưu tiên assert số lượng và nội dung kết quả cuối thay vì thứ tự item.

### Count không thay thế kiểm tra đầu ra

`writeCount == 100` chỉ cho biết framework ghi nhận 100 item được chuyển qua writer thành công theo contract của nó. Nó không bảo đảm dữ liệu được map đúng cột, giá trị chính xác, không trùng ID hoặc hệ thống ngoài đã xác nhận bền vững mọi thay đổi. Với một Step quan trọng, nên kiểm tra **cả count lẫn trạng thái dữ liệu đích**.

## 9. Mẫu assertion tái sử dụng

Khi nhiều test có cùng chính sách kiểm tra, có thể gom các assertion trong helper rõ nghĩa:

```java
import org.springframework.batch.core.StepExecution;

import static org.assertj.core.api.Assertions.assertThat;

final class StepCountAssertions {

    private StepCountAssertions() {}

    static void assertCounts(
            StepExecution step,
            int read,
            int written,
            int filtered,
            int readSkipped,
            int processSkipped,
            int writeSkipped) {

        assertThat(step.getReadCount()).as("readCount").isEqualTo(read);
        assertThat(step.getWriteCount()).as("writeCount").isEqualTo(written);
        assertThat(step.getFilterCount()).as("filterCount").isEqualTo(filtered);
        assertThat(step.getReadSkipCount()).as("readSkipCount").isEqualTo(readSkipped);
        assertThat(step.getProcessSkipCount()).as("processSkipCount")
                .isEqualTo(processSkipped);
        assertThat(step.getWriteSkipCount()).as("writeSkipCount")
                .isEqualTo(writeSkipped);
        assertThat(step.getSkipCount()).as("total skipCount")
                .isEqualTo(readSkipped + processSkipped + writeSkipped);
    }
}
```

Trong test kịch bản sáu item ở trên:

```java
StepCountAssertions.assertCounts(stepExecution, 6, 4, 1, 0, 1, 0);
```

Các nhãn `as(...)` giúp lỗi assertion nói rõ count nào sai. Tuy nhiên, vẫn nên đặt tên test theo hành vi nghiệp vụ, ví dụ `shouldFilterInactiveCustomersAndSkipMalformedRecord`, để người đọc hiểu **vì sao** từng giá trị được kỳ vọng, thay vì chỉ thấy một dãy số.

## 10. Cách chọn assertion đúng với mục tiêu test

| Mục tiêu | Assertion trọng tâm | Nên xác minh thêm |
| --- | --- | --- |
| Import toàn bộ dữ liệu hợp lệ | `readCount`, `writeCount`, `filterCount == 0`, `skipCount == 0` | Bản ghi đã ghi thực tế. |
| Lọc dữ liệu theo điều kiện | `filterCount`, `writeCount`, `readCount` | Nội dung item bị giữ lại và bị loại. |
| Cho phép bỏ qua bản ghi lỗi | `readSkipCount` / `processSkipCount` / `writeSkipCount`, trạng thái | Loại exception và dữ liệu hợp lệ vẫn được xử lý. |
| Vượt giới hạn skip | `BatchStatus.FAILED`, failure exceptions | Các thay đổi transaction đã rollback/commit. |
| Kiểm thử giao dịch | `commitCount`, `rollbackCount` theo kịch bản có kiểm soát | Trạng thái dữ liệu sau commit/rollback. |
| Kiểm thử restart hoặc partition | Đúng `StepExecution` của lần chạy/partition | Kết quả tổng cuối cùng, tránh đếm trùng. |

Nguyên tắc cốt lõi là **assert cả kết quả xử lý lẫn cách đạt được kết quả đó**. Dùng `BatchStatus` để xác nhận Step kết thúc như mong đợi, dùng các count của `StepExecution` để phát hiện item bị lọc hoặc skip sai, và kiểm tra dữ liệu đầu ra để chứng minh nghiệp vụ đã được thực hiện chính xác.
