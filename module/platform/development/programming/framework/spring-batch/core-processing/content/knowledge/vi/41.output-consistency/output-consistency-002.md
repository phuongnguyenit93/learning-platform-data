# File output và restart safety

Trong Spring Batch, ghi file theo chunk có thể chạy thành công ở lần đầu nhưng gặp lỗi giữa chừng do process bị dừng, database mất kết nối, ổ đĩa đầy hoặc một item không hợp lệ. Khi Job được restart, writer phải tiếp tục từ checkpoint đã commit và tạo ra output không bị thiếu hoặc lặp ngoài ý muốn.

Restart safety của file output phụ thuộc vào nhiều thành phần cùng lúc: writer phải lưu state, tên writer và đường dẫn output phải ổn định, file phải còn nguyên giữa các lần chạy, chunk transaction phải được hiểu đúng, và quy trình publish/cleanup phải tôn trọng trạng thái Job. `FlatFileItemWriter` hỗ trợ checkpoint qua `ItemStream` và `ExecutionContext`, nhưng filesystem không tự tham gia cùng một transaction nguyên tử với JobRepository. Vì vậy, một thiết kế production thường ghi vào file staging riêng của JobInstance, xác nhận file hoàn chỉnh rồi mới publish thành file chính thức.

## 1. Vì sao file output cần restart safety?

Giả sử một Step đọc 1 triệu đơn hàng và ghi CSV. Chunk size là 1.000. Sau khi đã ghi và commit 300 chunk, process bị dừng khi đang xử lý chunk tiếp theo.

Khi restart, hệ thống cần:

- Tiếp tục từ checkpoint cuối cùng đã commit.
- Giữ lại nội dung của các chunk đã commit.
- Không ghi lặp những dòng thuộc chunk đã commit.
- Ghi lại các dòng của chunk chưa commit nếu chunk đó phải được xử lý lại.
- Không tạo header/footer sai vị trí hoặc làm hỏng cấu trúc file.
- Đảm bảo downstream chỉ đọc file sau khi Job xác nhận output hoàn chỉnh.

Nếu writer luôn truncate file mỗi lần mở, restart sẽ xóa output đã commit. Nếu writer luôn append một cách thủ công mà không khôi phục checkpoint, restart có thể ghi lặp dữ liệu. Restart safety cần phối hợp trạng thái trong JobRepository với trạng thái thực tế của file.

## 2. File writer tham gia ItemStream lifecycle

Các writer file tích hợp của Spring Batch như `FlatFileItemWriter` triển khai `ItemStreamWriter<T>`. Interface này kết hợp thao tác `write` với lifecycle của `ItemStream`:

- `open(ExecutionContext)`: mở file và khôi phục state nếu đây là lần restart.
- `write(Chunk<? extends T>)`: ghi các item của chunk.
- `update(ExecutionContext)`: lưu state writer để checkpoint cùng chunk.
- `close()`: flush/đóng resource khi Step kết thúc.

Luồng khái niệm:

```text
Step bắt đầu
    |
    v
writer.open(ExecutionContext)
    |
    v
Reader -> Processor -> Writer.write(chunk)
    |
    v
writer.update(ExecutionContext)
    |
    v
Chunk transaction commit
    |
    +--> Lặp lại cho chunk kế tiếp
    |
    v
writer.close()
```

Spring Batch gọi lifecycle cho stream đã được đăng ký trong Step. Khi dùng writer tích hợp trực tiếp trong `.writer(...)`, framework nhận diện stream theo cơ chế cấu hình của Step. Nếu bọc writer bằng decorator hoặc custom component, lớp bọc cần triển khai/chuyển tiếp `ItemStream` hoặc delegate cần được đăng ký như stream của Step. Nếu không, `open`, `update` và `close` có thể không được gọi đúng, khiến restart state không được lưu.

## 3. FlatFileItemWriter cơ bản

`FlatFileItemWriter<T>` ghi mỗi item thành một dòng thông qua `LineAggregator<T>`. Với CSV, có thể dùng builder `.delimited()` để ánh xạ field:

```java
@Bean
@StepScope
FlatFileItemWriter<OrderExport> orderFileWriter(
        @Value("#{jobParameters['output.file']}") String outputFile) {

    return new FlatFileItemWriterBuilder<OrderExport>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .lineSeparator("\n")
            .saveState(true)
            .transactional(true)
            .forceSync(true)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount", "currency")
            .build();
}
```

Các cấu hình đáng chú ý:

- `name`: tên stream ổn định và duy nhất trong Step; tên được dùng để namespace state trong `ExecutionContext`.
- `resource`: file đích của writer.
- `encoding`: charset của file; UTF-8 thường phù hợp cho dữ liệu đa ngôn ngữ.
- `lineSeparator`: quy định newline nhất quán giữa các lần chạy và môi trường.
- `saveState(true)`: yêu cầu writer lưu state để restart.
- `transactional(true)`: dùng cơ chế ghi có tính đến transaction của chunk theo hỗ trợ của writer.
- `forceSync(true)`: yêu cầu đồng bộ nội dung file xuống storage ở mức hệ điều hành/provider hỗ trợ; có thể làm giảm throughput.

Builder `.delimited()` tạo line aggregator từ tên field. Với định dạng đặc biệt, có thể dùng `.lineAggregator(...)` để kiểm soát serialization.

## 4. Writer lưu state gì?

Writer file cần biết tiến độ output đã được checkpoint để khi restart có thể mở file hiện có và tiếp tục. `FlatFileItemWriter` quản lý state nội bộ như số dòng đã ghi và thông tin cần thiết để phân biệt lần mở mới với lần restart.

Không nên tự phụ thuộc vào tên key nội bộ trong `ExecutionContext`. Key cụ thể là chi tiết implementation dựa trên tên writer và phiên bản Spring Batch. Hãy đặt `.name(...)` ổn định và để writer tự gọi `update`/`open` để lưu/khôi phục state.

Hai nguồn thông tin phải nhất quán:

| Nguồn | Thông tin |
|---|---|
| JobRepository / `ExecutionContext` | Checkpoint cuối cùng mà Spring Batch đã commit. |
| File trên filesystem | Nội dung output thực tế đang tồn tại. |

Nếu metadata nói writer đã ghi đến chunk 300 nhưng file bị xóa hoặc thay bằng file khác, writer không thể tự tái tạo chính xác các byte đã mất chỉ từ số dòng. Vì vậy, file đang dùng để restart phải được giữ nguyên và bảo vệ khỏi cleanup ngoài ý muốn.

## 5. Tên writer phải ổn định

Tên writer không chỉ dùng để log. `ItemStreamSupport` sử dụng tên component để tạo key trong `ExecutionContext`.

Ví dụ:

```java
.name("orderFileWriter")
```

Tên cần:

- Không rỗng khi writer lưu state.
- Ổn định qua các lần restart của cùng Step.
- Duy nhất giữa các stream trong cùng StepExecution.
- Không được tạo ngẫu nhiên theo thời điểm hoặc JobExecution ID.

Nếu đổi tên writer giữa hai lần chạy, writer có thể không tìm thấy checkpoint cũ và coi file như một lần mở mới. Khi nâng cấp ứng dụng trong lúc có Job cần restart, cần giữ tương thích tên stream hoặc có kế hoạch hoàn tất/migrate execution cũ.

## 6. Output path phải ổn định qua restart

Đường dẫn file cần đại diện cho output của một JobInstance hoặc một lần nghiệp vụ, không đại diện cho từng lần JobExecution.

Ví dụ dùng business date và run key:

```text
/data/staging/orders-2026-11-15-run-42.csv.part
```

JobParameters có thể cung cấp path:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("business.date", "2026-11-15", true)
        .addString("run.id", "42", true)
        .addString("output.file",
                "/data/staging/orders-2026-11-15-run-42.csv.part", true)
        .toJobParameters();
```

Các identifying parameters phải giữ nguyên khi restart cùng JobInstance. Nếu output path được truyền như parameter không identifying, cần bảo đảm launcher vẫn truyền đúng giá trị ban đầu; tốt hơn là để định danh output gắn với identifying run key và kiểm soát path trong Job.

Không tạo path bằng timestamp của mỗi lần JobExecution. Restart là một execution mới của cùng JobInstance; nếu path đổi theo thời điểm restart, writer có thể mở một file trống trong khi checkpoint metadata thuộc file cũ.

## 7. Phân biệt JobInstance, JobExecution và lần chạy mới

Spring Batch phân biệt JobInstance với JobExecution:

- JobInstance đại diện cho một lần nghiệp vụ được xác định bởi identifying JobParameters.
- JobExecution là một lần thực thi cụ thể của JobInstance.
- Restart tạo JobExecution mới nhưng tiếp tục cùng JobInstance và dùng lại trạng thái/checkpoint phù hợp.
- Một lần chạy nghiệp vụ mới cần identifying parameters khác để tạo JobInstance mới.

Ví dụ:

```text
JobInstance: export-orders / businessDate=2026-11-15 / runId=42
    |
    +--> JobExecution 1: FAILED sau chunk 300
    |
    +--> JobExecution 2: RESTARTED, tiếp tục cùng output staging file
    |
    +--> JobExecution 2: COMPLETED

JobInstance mới: export-orders / businessDate=2026-11-16 / runId=43
    |
    +--> Dùng output path riêng
```

Không dùng cùng một output path cho hai JobInstance độc lập nếu chúng có thể chạy đồng thời hoặc cần giữ output lịch sử. Path riêng theo run key giúp tránh ghi đè và nhầm file.

## 8. Restart và hành vi mở file

Khi writer mở lần đầu cho một StepExecution mới, nó áp dụng chính sách đối với file đã tồn tại theo cấu hình. Khi restart cùng StepExecution/JobInstance, writer dùng state đã lưu để nhận biết đây là lần tiếp tục và mở file hiện có theo cơ chế restart của implementation.

Điều này có nghĩa:

- Giữ nguyên file output staging khi Job thất bại nếu muốn restart.
- Giữ nguyên tên writer và đường dẫn resource.
- Không tự truncate file trước khi Spring Batch mở writer khi restart.
- Không tự append nội dung ngoài writer giữa hai execution.
- Không sửa/xóa một phần file đã checkpoint.

`shouldDeleteIfExists` và `append` là các lựa chọn ảnh hưởng đến cách xử lý file có sẵn ở lần mở mới. Chúng cần được chọn theo chính sách fresh run; không dùng chúng như cơ chế thay thế checkpoint. Writer tích hợp phân biệt trạng thái restart bằng ExecutionContext.

## 9. shouldDeleteIfExists và append

Hai tùy chọn này thường bị nhầm với restart:

- `shouldDeleteIfExists(true)`: khi bắt đầu một lần ghi mới, writer có thể xóa file đích đã tồn tại theo semantics builder/implementation.
- `append(true)`: cho phép nối vào file có sẵn trong trường hợp cấu hình append; phù hợp với nghiệp vụ append có chủ đích.

Với file staging riêng cho một JobInstance, thường nên chọn chính sách fresh run rõ ràng và để writer quản lý restart dựa trên checkpoint. Không đặt `append(true)` chỉ vì muốn restart; append thủ công không biết chunk nào đã commit và có thể tạo duplicate.

Ví dụ cấu hình fresh output:

```java
new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderFileWriter")
        .resource(stagingResource)
        .shouldDeleteIfExists(true)
        .saveState(true)
        .lineAggregator(orderLineAggregator)
        .build();
```

Chỉ dùng path riêng cho JobInstance và bảo đảm restart được nhận diện bằng state. Nếu dùng một file chung để append nhiều JobInstance, cần một thiết kế khác có record boundary, locking, deduplication và recovery riêng; không nên tái sử dụng cấu hình restart file thông thường cho trường hợp đó.

## 10. saveState và writer không restartable

`saveState(true)` cho phép writer lưu checkpoint trong `ExecutionContext`. Với writer có state, đây thường là yêu cầu để restart an toàn.

Nếu cấu hình `saveState(false)`:

- Writer không lưu checkpoint tiến độ.
- Khi restart, writer không có đủ state để biết nội dung nào thuộc chunk đã commit.
- Nếu file được giữ và append, dữ liệu có thể bị ghi lặp.
- Nếu file bị truncate, output đã commit trước đó có thể mất.
- Không nên kỳ vọng Step tự khôi phục chính xác vị trí file.

`saveState(false)` chỉ phù hợp khi ứng dụng chấp nhận đọc/ghi lại toàn bộ, dùng output tạm có thể xóa và tạo mới, hoặc có cơ chế checkpoint/idempotency khác được thiết kế riêng. Nếu yêu cầu restart từ giữa file, bật state ở writer và kiểm thử.

## 11. Chunk transaction và transactional writer

`FlatFileItemWriter` hỗ trợ transactional buffering. Với `transactional(true)`, writer phối hợp việc ghi file với transaction của chunk để dữ liệu được buffer và hoàn tất theo transaction synchronization. Khi chunk rollback trước khi buffer được commit, phần ghi của chunk đó có thể được loại bỏ theo cơ chế writer.

Ví dụ:

```text
Chunk 1: write 1,000 dòng -> commit -> output được giữ
Chunk 2: write 1,000 dòng -> rollback -> phần buffer của chunk 2 bị hủy
Restart: tiếp tục từ checkpoint sau chunk 1
```

Điều này hữu ích nhưng không biến filesystem thành resource transactionally enlisted giống database có XA. Writer không thể bảo đảm một transaction nguyên tử chung giữa file và JobRepository trong mọi tình huống process crash, filesystem error hoặc mất điện.

Nếu writer ghi trực tiếp (`transactional(false)`), một phần nội dung chunk có thể đã được ghi xuống file trước khi transaction thất bại. Restart có thể tạo duplicate hoặc output không khớp checkpoint. Chỉ tắt transactional buffering khi có lý do và recovery strategy rõ.

## 12. File và JobRepository không có một commit nguyên tử chung

Ngay cả khi writer hỗ trợ transaction-aware buffering, file và metadata JobRepository thường nằm ở hai resource khác nhau. Không nên tuyên bố “exactly once” chỉ vì writer có `saveState(true)`.

Một số cửa sổ lỗi cần xét:

- Process dừng sau khi file đã nhận bytes nhưng trước khi metadata checkpoint được commit.
- Metadata checkpoint được commit nhưng filesystem không giữ được bytes do lỗi storage/disk cache.
- Writer flush một phần dữ liệu rồi gặp lỗi I/O.
- File bị cleanup hoặc thay thế sau khi chunk đã commit.
- Process restart với output path khác hoặc file không còn khớp checkpoint.

Spring Batch cung cấp checkpoint và transaction integration cho writer, nhưng durability cuối cùng còn phụ thuộc filesystem, mount options, storage và cách triển khai publish. Với output quan trọng, hãy viết vào staging, xác nhận tính toàn vẹn và chỉ publish khi Step thành công.

## 13. Staging file và final file

Một pattern an toàn là tách file đang được tạo khỏi file downstream được phép đọc:

```text
JobInstance bắt đầu
      |
      v
orders-run-42.csv.part
      |
      +--> Writer ghi theo chunk và checkpoint
      |
      +--> Job fail: giữ file .part để restart
      |
      +--> Restart: tiếp tục cùng file .part
      |
      v
Step ghi file COMPLETED
      |
      v
Validate count/schema/checksum
      |
      v
Atomic rename/move
      |
      v
orders-run-42.csv
      |
      v
Downstream được phép đọc
```

Downstream chỉ theo dõi final extension/path hoặc một manifest trạng thái `READY`. Nó không quét file `.part` như output hoàn chỉnh.

Staging giúp tránh trường hợp downstream đọc file đang được writer bổ sung hoặc file của một Job thất bại. Nó cũng cho phép giữ lại file lỗi để điều tra và restart.

## 14. Publish bằng atomic move

Sau khi Step ghi file thành công và validation hoàn tất, có thể đổi tên file staging thành final file. Nếu source và target nằm trên cùng filesystem, `Files.move` với `ATOMIC_MOVE` có thể cung cấp rename nguyên tử theo khả năng filesystem:

```java
@Bean
@StepScope
Tasklet publishOrdersFileTasklet(
        @Value("#{jobParameters['staging.file']}") String stagingFile,
        @Value("#{jobParameters['final.file']}") String finalFile) {

    return (contribution, chunkContext) -> {
        Path source = Path.of(stagingFile);
        Path target = Path.of(finalFile);

        if (Files.exists(target)) {
            throw new FileAlreadyExistsException(target.toString());
        }

        Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        return RepeatStatus.FINISHED;
    };
}

@Bean
Step publishOrdersFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet publishOrdersFileTasklet) {

    return new StepBuilder("publishOrdersFileStep", jobRepository)
            .tasklet(publishOrdersFileTasklet, transactionManager)
            .build();
}
```

Đây là ví dụ minh họa; cần bổ sung import, exception handling và policy target-exists phù hợp. `ATOMIC_MOVE` có thể không được hỗ trợ trên một số filesystem/provider hoặc khi source/target nằm khác filesystem. Nếu atomic move là yêu cầu, hãy fail rõ khi không được hỗ trợ thay vì âm thầm coi copy-delete là tương đương.

Đoạn code trên dùng chính sách fail-closed khi target đã tồn tại; riêng nó chưa xử lý trường hợp move thành công ở lần trước nhưng metadata Step chưa kịp commit. Production cần bổ sung nhánh xác minh target bằng manifest/checksum của đúng run và coi đó là publish đã hoàn tất nếu source không còn. Không bỏ qua target-exists chỉ dựa trên việc file có mặt.

Tasklet publish có transaction metadata của Spring Batch nhưng thao tác filesystem vẫn không nằm trong cùng một transaction nguyên tử với JobRepository. Vì vậy, publish cần idempotent để xử lý trường hợp move thành công nhưng metadata Step chưa kịp commit.

## 15. Publish step phải idempotent

Giả sử file đã được move sang final path nhưng process dừng trước khi Step publish ghi trạng thái `COMPLETED` vào JobRepository. Khi restart, tasklet publish được gọi lại. Source staging không còn, nhưng target final đã tồn tại.

Một publish step an toàn cần phân biệt:

- Target đã tồn tại và được xác minh là output đúng của cùng run: coi thao tác publish đã hoàn tất.
- Target tồn tại nhưng thuộc run khác hoặc checksum khác: fail, không ghi đè.
- Source tồn tại và target chưa tồn tại: thực hiện move.
- Cả source và target đều không tồn tại: fail và yêu cầu recovery.

Có thể lưu run ID, record count và checksum trong manifest cạnh file. Khi restart publish, tasklet xác minh manifest trước khi quyết định bước tiếp theo. Không chỉ kiểm tra target tồn tại rồi mặc định file đó đúng.

## 16. Validate output trước khi publish

Sau khi writer Step hoàn tất, có thể kiểm tra:

- File tồn tại và có kích thước lớn hơn mức tối thiểu mong đợi.
- Số record bằng số item writer đã commit hoặc số liệu đối soát.
- Header đúng và chỉ xuất hiện một lần.
- Footer/trailer có checksum hoặc tổng tiền nếu định dạng yêu cầu.
- Encoding và line separator đúng hợp đồng downstream.
- Không có dòng lỗi hoặc record thiếu field bắt buộc.
- File parse được bằng parser của định dạng đích.
- Checksum của file được tính và ghi vào manifest.

Không chỉ kiểm tra Job `COMPLETED`; một writer có thể ghi file rỗng hợp lệ về mặt kỹ thuật nếu input filter hết, trong khi nghiệp vụ yêu cầu có ít nhất một record. Validation cần hiểu điều kiện nghiệp vụ.

Nếu output có thể rỗng hợp lệ, hãy xác định file rỗng có được publish hay không và cách biểu diễn rõ ràng trong manifest.

## 17. Header và footer khi restart

CSV hoặc fixed-width file thường có header; một số định dạng có footer/trailer tổng hợp. Writer tích hợp quản lý callback theo lifecycle và state restart. Không tự ghi header trong processor hoặc trước mỗi lần mở writer.

Ví dụ:

```java
new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderFileWriter")
        .resource(stagingResource)
        .headerCallback(writer ->
                writer.write("orderId,customerName,amount,currency"))
        .footerCallback(writer ->
                writer.write("# END OF EXPORT"))
        .lineAggregator(orderLineAggregator)
        .saveState(true)
        .build();
```

Header chỉ nên được ghi khi tạo file mới; restart phải tiếp tục nội dung hiện có mà không thêm header thứ hai. Footer chỉ có ý nghĩa khi writer kết thúc theo lifecycle thành công phù hợp. Cần kiểm tra behavior của writer/version cụ thể khi Step fail và restart; downstream không nên coi file `.part` có footer hay không là dấu hiệu duy nhất của trạng thái hoàn tất.

Với định dạng JSON array, việc mở/đóng dấu ngoặc và dấu phẩy giữa record làm restart phức tạp hơn định dạng record-per-line. Hãy dùng writer có hỗ trợ restart cho đúng format hoặc ghi NDJSON/staging rồi chuyển đổi/đóng gói ở bước publish riêng.

## 18. Charset, line separator và serialization ổn định

Restart nối tiếp vào cùng file nên cần cùng quy tắc serialize:

- Giữ nguyên encoding, thường là UTF-8.
- Giữ nguyên line separator (`\n` hoặc `\r\n`).
- Giữ nguyên delimiter, quote/escape và null representation.
- Giữ locale, timezone và format số/ngày giờ ổn định.
- Giữ thứ tự field và schema version.
- Không thay đổi line aggregator giữa lần đầu và restart của cùng JobInstance.

Nếu deploy phiên bản mới trong lúc một Job cần restart, thay đổi serializer có thể làm file chứa nửa đầu theo schema cũ và nửa sau theo schema mới. Hãy giữ compatibility với execution cũ hoặc hoàn tất/khởi tạo lại Job theo quy trình có kiểm soát.

Không dùng locale mặc định của máy để format số tiền hoặc ngày tháng trong file trao đổi. Hãy chỉ định format và timezone rõ ràng.

## 19. Định dạng record và newline

`FlatFileItemWriter` dùng line aggregator để chuyển object thành text. Với CSV, cần escape delimiter, quote, newline và ký tự đặc biệt đúng chuẩn mà downstream yêu cầu. Không nối chuỗi đơn giản nếu field có thể chứa dấu phẩy hoặc dấu ngoặc kép.

Ví dụ dùng `DelimitedLineAggregator`:

```java
DelimitedLineAggregator<OrderExport> aggregator =
        new DelimitedLineAggregator<>();
aggregator.setDelimiter(",");

BeanWrapperFieldExtractor<OrderExport> extractor =
        new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
        "orderId", "customerName", "amount", "currency"
});
aggregator.setFieldExtractor(extractor);
```

Nếu yêu cầu CSV RFC-compliant hoặc field có newline, dùng serializer/library phù hợp hoặc custom aggregator có test cho quoting/escaping. `lineSeparator` của writer xác định dấu kết thúc record; nó không thay thế việc escape newline bên trong field.

## 20. MultiResourceItemWriter

Khi output lớn, có thể chia thành nhiều file theo số item bằng `MultiResourceItemWriter`. Writer này điều phối một delegate writer và tạo resource mới khi đạt giới hạn item mỗi file.

Ví dụ khái niệm:

```java
@Bean
@StepScope
MultiResourceItemWriter<OrderExport> multiOrderWriter(
        @Value("#{jobParameters['output.directory']}") String directory,
        LineAggregator<OrderExport> orderLineAggregator) {

    FlatFileItemWriter<OrderExport> delegate =
            new FlatFileItemWriterBuilder<OrderExport>()
                    .name("orderFileDelegate")
                    .encoding(StandardCharsets.UTF_8.name())
                    .lineAggregator(orderLineAggregator)
                    .saveState(true)
                    .build();

    return new MultiResourceItemWriterBuilder<OrderExport>()
            .name("multiOrderWriter")
            .resource(new FileSystemResource(
                    Path.of(directory, "orders").toString()))
            .itemCountLimitPerResource(100_000)
            .resourceSuffixCreator(index ->
                    String.format("-%03d.csv", index))
            .delegate(delegate)
            .saveState(true)
            .build();
}
```

Đoạn code minh họa ý tưởng; cấu hình delegate cần dùng line aggregator/format đúng với output thực tế. `MultiResourceItemWriter` quản lý resource index và số item trong resource; delegate quản lý state của file hiện tại. Tên wrapper và delegate phải ổn định, `saveState` cần bật ở cả wrapper và delegate khi yêu cầu restart.

Các suffix/resource name phải tái tạo giống nhau khi restart. Không thay `itemCountLimitPerResource`, prefix hoặc suffix creator giữa các lần execution của cùng JobInstance. Nếu file đã được publish/cleanup trước khi Job hoàn tất, restart có thể không mở được resource cần thiết.

## 21. Custom writer phải triển khai ItemStreamWriter nếu cần restart

Nếu writer ghi định dạng riêng hoặc gọi một thư viện file khác, chỉ triển khai `ItemWriter<T>` là chưa đủ khi cần checkpoint. Hãy triển khai `ItemStreamWriter<T>` và lưu state cần thiết vào `ExecutionContext`.

Ví dụ khung:

```java
public class CheckpointedRecordWriter
        implements ItemStreamWriter<ExportRecord> {

    private static final String RECORD_COUNT_KEY =
            "checkpointedRecordWriter.recordCount";

    private final Resource resource;
    private long recordCount;
    private Writer writer;

    public CheckpointedRecordWriter(Resource resource) {
        this.resource = resource;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        recordCount = context.containsKey(RECORD_COUNT_KEY)
                ? context.getLong(RECORD_COUNT_KEY)
                : 0L;
        // Open the resource using a restart-aware strategy.
        // Verify existing file state before appending after a restart.
    }

    @Override
    public void write(Chunk<? extends ExportRecord> chunk) throws Exception {
        for (ExportRecord record : chunk.getItems()) {
            writer.write(serialize(record));
            writer.write("\n");
            recordCount++;
        }
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        context.putLong(RECORD_COUNT_KEY, recordCount);
    }

    @Override
    public void close() throws ItemStreamException {
        // Flush and close the owned resource.
    }
}
```

Đây là khung minh họa, chưa phải implementation production: writer thực tế phải xác định cách lưu vị trí byte/record, cách rollback buffer của chunk, cách phân biệt lần mở mới với restart, xử lý partial write và đồng bộ với transaction. Chỉ lưu `recordCount` không đủ nếu file có thể bị sửa hoặc truncate. Ưu tiên writer tích hợp khi định dạng phù hợp.

Khi custom writer được bọc bởi delegate, lớp ngoài phải chuyển tiếp `open`, `update`, `close` và bảo đảm state của wrapper/delegate được lưu theo một quy tắc nhất quán.

## 22. Output path theo JobInstance và tránh collision

Một output file nên có ownership rõ ràng. Có thể tạo path từ business date, tenant, export type và run ID:

```text
/exports/staging/tenant-17/orders-2026-11-15-run-42.csv.part
```

Tránh:

- Tất cả Job cùng ghi `/exports/orders.csv`.
- Tên file chỉ có ngày khi có thể chạy lại nhiều lần trong cùng ngày.
- Dùng JobExecution ID làm path nếu restart tạo execution ID mới.
- Dùng timestamp hiện tại trong bean factory mỗi lần mở writer.
- Cho phép hai JobInstance khác nhau ghi cùng resource.

Nếu cần output theo tenant, bảo đảm tenant ID là một phần của identifying input hoặc output key. Nếu Job có thể chạy đồng thời cho cùng business date, thêm run key/partition ID để path không va chạm.

## 23. Restart sau khi writer Step hoàn tất

Một Job có thể gồm các Step:

```text
prepareOutputStep
        |
        v
writeOrdersFileStep
        |
        v
validateOutputStep
        |
        v
publishOutputStep
```

Nếu `writeOrdersFileStep` đã `COMPLETED` nhưng `publishOutputStep` thất bại, restart Job thường tiếp tục từ Step chưa hoàn tất theo flow/restart rules. Không nên chạy lại writer chỉ để publish lại file nếu writer Step đã hoàn thành và output staging còn nguyên.

Nếu publish đã move file nhưng JobRepository chưa ghi nhận Step hoàn tất, publish tasklet phải idempotent như đã mô tả. Nếu validate thất bại, giữ file staging để điều tra hoặc cleanup theo policy rõ ràng; không publish file không hợp lệ.

## 24. Cleanup file khi Job fail hoặc restart

Không xóa file staging ngay khi Step fail nếu Job còn được phép restart. File có thể chứa dữ liệu của các chunk đã commit và là phần tiếp nối cần thiết.

Chính sách cleanup nên phân biệt:

- Job đang `FAILED` nhưng có thể restart: giữ file staging và manifest.
- Job `COMPLETED` và publish thành công: archive/cleanup staging theo retention.
- Job bị abandon hoặc restart window hết hạn: quarantine/xóa theo quy trình vận hành.
- File không khớp checkpoint/checksum: giữ bản để điều tra, không tự động append.
- JobInstance mới: dùng path mới để tránh ghi lên file cũ.

Cleanup nên chạy sau khi xác nhận trạng thái terminal và không có execution đang hoạt động. Một scheduled cleanup không được xóa file chỉ vì phần mở rộng `.part` đã tồn tại quá một khoảng thời gian ngắn.

## 25. Kiểm thử restart cho FlatFileItemWriter

Một integration test nên chứng minh writer tiếp tục cùng file mà không ghi trùng hoặc mất dòng.

Kịch bản:

1. Tạo input có 5 item và chunk size 2.
2. Chạy Job lần đầu với writer staging và một test hook làm Step fail sau hai chunk đã commit.
3. Xác nhận file staging chứa đúng các dòng đã commit.
4. Xác nhận `ExecutionContext` của Step có state writer.
5. Restart cùng JobInstance với cùng output path và reader/writer names.
6. Xác nhận writer tiếp tục từ checkpoint, không truncate file đã có.
7. Xác nhận file cuối có đủ 5 record, mỗi record đúng một lần.
8. Xác nhận header chỉ có một lần và footer/trailer hợp lệ.

Không chỉ assert số dòng; hãy parse output và so sánh tập/order các business key để phát hiện duplicate hoặc thiếu item.

## 26. Kiểm thử rollback giữa chunk

Tạo writer hoặc collaborator test có thể ném exception trong lúc xử lý một chunk:

- Chunk trước đã commit phải còn trong output.
- Chunk thất bại không được xuất hiện một phần nếu transactional buffering được bật và writer hoạt động theo hợp đồng.
- Sau restart, chunk lỗi được xử lý lại.
- Output cuối không có duplicate.

Nên test cả exception từ processor trước writer và lỗi I/O của writer. Hai tình huống có thể có behavior khác nhau vì một lỗi xảy ra trước khi writer ghi, còn lỗi kia có thể xảy ra sau khi file đã nhận một phần bytes.

Đối với crash process thật, có thể dùng test harness riêng hoặc mô phỏng restart ở các điểm đồng bộ; không nên chỉ dựa vào unit test writer để khẳng định filesystem và JobRepository luôn commit nguyên tử.

## 27. Kiểm thử file bị thay đổi hoặc mất trước restart

Tạo checkpoint sau một số chunk rồi chủ động:

- Xóa file staging.
- Truncate file.
- Thay file bằng nội dung khác tại cùng path.
- Đổi encoding/line separator/serializer.
- Thay output path trong JobParameters.

Job cần fail rõ hoặc quy trình recovery phải xác minh và tái tạo output có chủ đích. Không được âm thầm append vào file không tương ứng checkpoint.

Nếu dùng manifest, test xác nhận checksum/size mismatch được phát hiện trước khi tiếp tục writer. Với file quá lớn, có thể dùng checksum streaming để tránh nạp toàn bộ file vào memory.

## 28. Kiểm thử header, footer và empty output

Các trường hợp nên có:

- File có item: header một lần, record đầy đủ, footer đúng.
- Restart giữa file: không thêm header lần nữa.
- Restart sau chunk cuối nhưng trước publish: output vẫn hợp lệ.
- Không có item: policy `shouldDeleteIfEmpty`/empty file được áp dụng đúng.
- Job fail: file staging chưa được downstream coi là hoàn chỉnh.
- Writer close: buffer được flush và resource được đóng.

Footer có thể được ghi trong lifecycle close tùy writer/configuration. Nếu process bị kill đột ngột, close callback không nhất thiết chạy. Do đó, marker hoàn tất nên được tạo ở publish step sau khi Job/validation thành công, thay vì chỉ dựa vào footer.

## 29. Kiểm thử MultiResourceItemWriter

Nếu một Step tạo nhiều file, test thêm:

- Số item mỗi resource đúng giới hạn.
- Suffix và thứ tự file xác định.
- Restart giữa resource không tạo file suffix trùng hoặc bỏ sót.
- Wrapper và delegate đều lưu state.
- Resource list/prefix/suffix không thay đổi qua restart.
- Header được ghi đúng ở mỗi file theo format.
- Downstream chỉ thấy các file đã publish hoàn chỉnh.

Khi restart, giữ nguyên `itemCountLimitPerResource`, resource prefix, suffix creator và delegate name. Thay đổi chúng có thể làm state cũ trỏ đến resource không đúng.

## 30. Những lỗi thường gặp

### Truncate file mỗi lần restart

Writer mở như lần chạy mới và xóa output đã commit. Giữ cùng JobInstance, output path, writer name và checkpoint để writer nhận diện restart.

### Dùng append(true) thay cho checkpoint

Append không biết chunk nào đã commit. Restart có thể ghi lặp. Dùng writer state và chỉ append thủ công khi có giao thức riêng.

### Tắt saveState

Writer không có checkpoint để tiếp tục. Bật `saveState(true)` cho writer restartable.

### Đổi tên writer

ExecutionContext key thay đổi và state cũ không được khôi phục. Giữ name ổn định.

### Đổi output path khi restart

Checkpoint thuộc file cũ nhưng writer mở file mới. Dùng identifying run key/path ổn định.

### Xóa file staging khi Job fail

Mất dữ liệu của chunk đã commit. Giữ file trong restart window.

### Cho downstream đọc file đang ghi

Downstream có thể đọc file chưa hoàn chỉnh. Dùng staging extension/path và publish sau validation.

### Cho rằng file và JobRepository commit nguyên tử

Filesystem và metadata không có một transaction chung mặc định. Dùng staging, manifest, checksum và publish idempotent.

### Dùng custom ItemWriter không có ItemStream

Writer không lưu/khôi phục state. Triển khai `ItemStreamWriter` và quản lý lifecycle đầy đủ.

### Quên đăng ký stream khi bọc delegate

Delegate không nhận callback `open/update/close`. Forward lifecycle hoặc đăng ký stream với Step.

### Thay format giữa lần chạy

File có thể chứa record theo hai schema/encoding khác nhau. Giữ serializer tương thích cho cùng JobInstance.

### Dựa vào footer để nhận biết file hoàn chỉnh

Process crash có thể không gọi close. Chỉ publish/đánh dấu READY sau validation thành công.

## 31. Quy trình thiết kế file output restart-safe

Khi xây dựng Step ghi file có khả năng restart, hãy thực hiện theo trình tự:

1. Chọn writer tích hợp như `FlatFileItemWriter` nếu phù hợp định dạng.
2. Đặt writer name ổn định và duy nhất trong Step.
3. Bật `saveState(true)` và transactional buffering phù hợp.
4. Tạo output path riêng cho JobInstance từ identifying parameters.
5. Giữ nguyên path, encoding, line separator, serializer và schema qua restart.
6. Giữ nguyên file staging sau failure nếu Job còn restart được.
7. Không tự truncate hoặc append ngoài writer khi restart.
8. Đảm bảo wrapper/custom writer chuyển tiếp `ItemStream` lifecycle.
9. Ghi output vào staging path; downstream không đọc file đang ghi.
10. Sau Step thành công, validate record count, schema, checksum và trailer.
11. Publish bằng atomic move trên cùng filesystem nếu được hỗ trợ.
12. Làm publish step idempotent để restart sau move không ghi đè output sai.
13. Cleanup/archive theo trạng thái Job và retention, không xóa file còn cần restart.
14. Kiểm thử fail/restart, rollback, file mismatch, header/footer và output trùng/thiếu.

| Nhu cầu | Cơ chế |
|---|---|
| Tiếp tục ghi cùng file sau restart | `ItemStreamWriter`, `saveState(true)`, tên writer ổn định |
| Không ghi trùng khi rollback chunk | Transaction-aware buffering của writer và kiểm thử chunk rollback |
| Tách output giữa các JobInstance | Path riêng theo identifying run key |
| Tránh downstream đọc file dở | Staging file và publish sau validation |
| Publish có thể restart | Tasklet move idempotent, manifest/checksum |
| Ghi nhiều file theo ngưỡng | `MultiResourceItemWriter` + delegate stream có state |
| Định dạng riêng | Custom `ItemStreamWriter` với checkpoint/lifecycle rõ |

## Kết luận

File output restart-safe cần đồng bộ checkpoint trong `ExecutionContext` với file thực tế. Dùng `FlatFileItemWriter` hoặc writer hỗ trợ `ItemStream`, đặt tên ổn định, bật `saveState(true)`, giữ nguyên output path và serializer qua restart của cùng JobInstance, đồng thời bảo vệ file đã có chunk commit khỏi cleanup hoặc chỉnh sửa. Transaction-aware buffering hỗ trợ rollback chunk nhưng không tạo một transaction nguyên tử chung giữa filesystem và JobRepository. Với output quan trọng, hãy ghi vào staging file riêng, validate số record/schema/checksum rồi publish bằng thao tác move phù hợp; publish step cần idempotent để xử lý restart sau khi file đã được move. Kiểm thử cả restart, rollback, crash window, file bị thay đổi, header/footer và nhiều resource để bảo đảm output không bị thiếu, trùng hoặc được downstream đọc trước khi hoàn tất.
