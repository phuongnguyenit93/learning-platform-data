# Quản lý output cũ

Trong Spring Batch, một Step có thể tạo nhiều file đầu ra bằng MultiResourceItemWriter. Ví dụ, mỗi file chỉ chứa tối đa 100.000 record và writer tự chuyển sang file tiếp theo khi đạt giới hạn. Sau mỗi lần chạy, số file được tạo có thể khác nhau.

Vấn đề xuất hiện khi một thư mục output được dùng lại. Lần chạy trước có thể tạo 12 file, còn lần chạy mới chỉ tạo 4 file. Nếu các file cũ từ lần trước vẫn còn, hệ thống nhận có thể đọc nhầm những file không thuộc kết quả mới. Một số file cũng có thể là output dở dang từ Job thất bại hoặc file được giữ lại sau một lần restart.

Quản lý output cũ cần trả lời ba câu hỏi:

- File thuộc JobInstance hoặc batch nào?
- Khi nào được phép xóa file cũ?
- Làm thế nào để consumer nhận biết bộ file đã hoàn tất?

Nguyên tắc quan trọng là phân biệt **lần chạy mới**, **restart cùng JobInstance** và **retention cleanup**. Lần chạy mới có thể cần một bộ output sạch; restart cần giữ lại file và checkpoint đã commit; retention cleanup chỉ xóa dữ liệu đã hết thời hạn lưu giữ và không còn được Job đang chạy sử dụng.

## 1. Vì sao output cũ gây lỗi?

Giả sử MultiResourceItemWriter tạo file theo giới hạn 3 record mỗi file.

Lần chạy thứ nhất có 10 record:

~~~text
orders-000.csv  -> record 1-3
orders-001.csv  -> record 4-6
orders-002.csv  -> record 7-9
orders-003.csv  -> record 10
~~~

Lần chạy tiếp theo chỉ có 5 record:

~~~text
orders-000.csv  -> output mới
orders-001.csv  -> output mới
~~~

Nếu writer chỉ ghi các file cần thiết mà không dọn những file còn lại, thư mục có thể vẫn chứa:

~~~text
orders-000.csv  -> output mới
orders-001.csv  -> output mới
orders-002.csv  -> output cũ
orders-003.csv  -> output cũ
~~~

Một consumer quét tất cả file có tên orders-*.csv sẽ đọc cả dữ liệu cũ. File cũ có thể hợp lệ về cú pháp nên lỗi không nhất thiết xuất hiện ngay; kết quả có thể bị trùng record, sai tổng hoặc xử lý lại một batch đã hoàn tất.

Các nguyên nhân thường gặp:

- Số file của lần chạy mới ít hơn lần trước.
- File cũ không nằm trong danh sách resource mà writer hiện tại tạo ra.
- Job thất bại giữa lúc ghi, để lại một số file chưa hoàn chỉnh.
- Một Job mới dùng lại cùng output path.
- Hai Job chạy đồng thời và ghi vào cùng prefix.
- Consumer quét thư mục trong khi writer vẫn đang tạo file.
- Cleanup xóa file quá rộng hoặc xóa nhầm file của Job đang restart.

MultiResourceItemWriter quản lý việc chia item sang các resource trong lần chạy của nó. Không nên coi nó là cơ chế retention tổng quát có trách nhiệm tìm và xóa mọi file suffix còn sót lại từ các lần chạy trước.

## 2. Phân biệt ba vòng đời

Một hệ thống cần quy định rõ ba tình huống:

| Tình huống | Output hiện có | Hành vi mong muốn |
| --- | --- | --- |
| JobInstance mới | Chưa có output của batch này | Tạo bộ output mới, dọn file cũ đúng phạm vi nếu cần |
| Restart cùng JobInstance | Có file và checkpoint từ lần chạy trước | Giữ file, tiếp tục từ checkpoint |
| Retention cleanup | Output của batch cũ đã hoàn tất hoặc hết hạn | Xóa/quarantine theo chính sách lưu trữ |

Không dùng một bước xóa file chung chạy trước mọi lần mở writer. Nếu bước đó chạy lại khi restart, nó có thể xóa các file mà writer cần để tiếp tục.

### JobInstance và JobExecution

Spring Batch phân biệt JobInstance với JobExecution:

- JobInstance đại diện cho một lần chạy logic được xác định bởi Job name và identifying JobParameters.
- JobExecution là một lần thực thi cụ thể của JobInstance.
- Khi restart, Spring Batch tạo JobExecution mới nhưng vẫn thuộc cùng JobInstance.

Vì vậy, không nên tạo đường dẫn output chỉ dựa trên JobExecution ID nếu restart cần tiếp tục cùng bộ file. Hãy dùng một batch key ổn định cho JobInstance, chẳng hạn batchId hoặc business date kết hợp mã nguồn, và giữ nguyên key đó khi restart.

Một JobInstance mới nên có batch key riêng nếu nó tạo một bộ output độc lập. Nếu doanh nghiệp chủ ý chạy lại cùng business batch như một lần xử lý mới, hãy tạo run key mới hoặc xác định rõ chiến lược thay thế output cũ.

## 3. Dùng thư mục riêng cho mỗi batch

Một cách dễ quản lý là tách output theo batch key:

~~~text
batch-output/
  BATCH-2026-11-15-A/
    orders-000.csv
    orders-001.csv
    manifest.json
  BATCH-2026-11-15-B/
    orders-000.csv
    manifest.json
~~~

Khi đó:

- Mỗi JobInstance ghi vào một thư mục riêng.
- Restart dùng lại đúng thư mục của batch key hiện tại.
- Job mới tạo thư mục mới nên không ghi đè file của batch khác.
- Consumer nhận batch key hoặc manifest để biết bộ file cần đọc.
- Retention có thể xóa cả thư mục của một batch đã hết hạn sau khi kiểm tra trạng thái.

Đây thường là cách đơn giản hơn việc nhiều Job cùng ghi vào một thư mục phẳng với các suffix giống nhau.

### Chọn batch key ổn định

Ví dụ Job nhận các JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-11-15-A")
        .addString("businessDate", "2026-11-15")
        .toJobParameters();
~~~

batchId phải được giữ nguyên khi restart cùng JobInstance. Không tạo một UUID mới ở mỗi lần restart nếu output path được suy ra từ UUID đó.

Nếu batchId được dùng làm tên thư mục, hãy giới hạn ký tự hợp lệ và kiểm tra đường dẫn sau khi normalize. Không dùng trực tiếp chuỗi tùy ý từ input để tạo path.

## 4. Cấu hình MultiResourceItemWriter

MultiResourceItemWriter chia output thành nhiều resource. Nó cần một resource gốc, một delegate có thể nhận resource mới, một giới hạn số item trên mỗi resource và một quy tắc tạo suffix.

Ví dụ:

~~~java
@Bean
@StepScope
public MultiResourceItemWriter<Order> multiOrderWriter(
        @Value("#{jobParameters['outputDirectory']}") String outputDirectory,
        FlatFileItemWriter<Order> orderFileDelegate) {

    Resource baseResource = new FileSystemResource(
            Path.of(outputDirectory, "orders").toString());

    return new MultiResourceItemWriterBuilder<Order>()
            .name("multiOrderWriter")
            .resource(baseResource)
            .resourceSuffixCreator(index ->
                    String.format("-%03d.csv", index))
            .itemCountLimitPerResource(100_000)
            .delegate(orderFileDelegate)
            .saveState(true)
            .build();
}
~~~

Với base resource có tên orders, suffix creator tạo các resource như orders-000.csv, orders-001.csv và tiếp tục tăng index. Thư mục output phải tồn tại và ứng dụng phải có quyền ghi.

Delegate có thể là FlatFileItemWriter:

~~~java
@Bean
public FlatFileItemWriter<Order> orderFileDelegate() {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileDelegate")
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerCode() + ","
                    + order.getTotalAmount())
            .saveState(true)
            .build();
}
~~~

MultiResourceItemWriter gán resource hiện tại cho delegate trước khi mở delegate để ghi file tương ứng. Delegate phải hỗ trợ ResourceAwareItemWriterItemStream. Cấu hình cụ thể của builder có thể khác theo phiên bản Spring Batch; hãy dùng API của version trong dự án và kiểm tra rằng resource được gán trước khi open.

### Đặt tên writer ổn định

Tên MultiResourceItemWriter và delegate writer phải ổn định khi restart. Spring Batch dùng tên và ExecutionContext để lưu state. Nếu đổi tên writer hoặc đổi cách tạo suffix giữa lần chạy đầu và restart, state có thể không còn khớp với resource đã tạo.

Không dùng tên writer giống nhau cho hai writer độc lập trong cùng phạm vi Step nếu chúng lưu state riêng.

## 5. Cleanup trước lần chạy mới

Nếu bắt buộc phải tái sử dụng cùng thư mục, hãy dọn output cũ trong một Step riêng chạy trước Step ghi file.

Luồng:

~~~text
prepareOutputStep
       |
       v
Xác định thư mục của batch mới
       |
       v
Xóa file cũ đúng prefix của batch
       |
       v
processOrdersStep
       |
       v
MultiResourceItemWriter tạo file mới
       |
       v
finalizeOutputStep
~~~

Tách cleanup thành Step riêng có hai lợi ích:

- Cleanup chỉ chạy trước khi bắt đầu tạo output.
- Khi Step xử lý thất bại và Job được restart, Step cleanup đã COMPLETED sẽ được bỏ qua theo hành vi mặc định, giúp giữ các file và checkpoint của lần chạy trước.

Không cấu hình cleanup Step để luôn chạy lại khi đã hoàn tất nếu nó có thể xóa output cần cho restart. Đặc biệt, không đặt thao tác xóa trong open() của writer hoặc trong constructor của delegate.

### Ví dụ Tasklet dọn file theo prefix

Ví dụ sau chỉ dọn các file CSV thuộc prefix orders trong thư mục của batch hiện tại:

~~~java
@Bean
@StepScope
public Tasklet cleanOldOrderFilesTasklet(
        @Value("#{environment.getProperty('batch.output.root')}") String outputRoot,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return (contribution, chunkContext) -> {
        if (batchId == null || !batchId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid batchId");
        }

        Path root = Paths.get(outputRoot)
                .toAbsolutePath()
                .normalize();
        Path batchDirectory = root.resolve(batchId).normalize();

        if (!batchDirectory.startsWith(root)) {
            throw new IllegalArgumentException(
                    "Output directory is outside configured root");
        }

        Files.createDirectories(batchDirectory);

        if (Files.isSymbolicLink(batchDirectory)) {
            throw new IllegalStateException(
                    "Batch output directory must not be a symbolic link");
        }

        try (Stream<Path> paths = Files.list(batchDirectory)) {
            for (Path path : paths.toList()) {
                String name = path.getFileName().toString();
                boolean ownedOutput =
                        name.startsWith("orders-")
                        && name.endsWith(".csv");

                if (ownedOutput
                        && Files.isRegularFile(
                                path, LinkOption.NOFOLLOW_LINKS)) {
                    Files.delete(path);
                }
            }
        }

        return RepeatStatus.FINISHED;
    };
}
~~~

Ví dụ cần import các kiểu Path, Files, LinkOption, Stream và các kiểu Spring Batch tương ứng. Với Java version chưa hỗ trợ Stream.toList(), có thể dùng Collectors.toList().

Một số điểm cần giữ:

- outputRoot là cấu hình tin cậy của ứng dụng, không lấy tùy ý từ file đầu vào.
- batchId được validate trước khi dùng làm tên thư mục.
- Chỉ xóa file regular file khớp prefix và extension do ứng dụng sở hữu.
- Không xóa thư mục cha hoặc toàn bộ output root.
- Không follow symbolic link khi kiểm tra file.
- Không chạy cleanup đồng thời với writer đang tạo file trong cùng batch directory.

Nếu ứng dụng dùng thư mục riêng mới hoàn toàn cho mỗi batchId và bảo đảm không tái sử dụng batchId, có thể không cần xóa file ở bước chuẩn bị. Khi đó, kiểm tra thư mục đã tồn tại và từ chối nếu có dữ liệu ngoài dự kiến thường an toàn hơn việc xóa tự động.

## 6. Cleanup Step phải an toàn khi restart

Giả sử Job có ba Step:

~~~text
cleanOutputStep
      |
      v
writeMultiResourceStep
      |
      v
publishOutputStep
~~~

Lần chạy đầu:

1. cleanOutputStep xóa file cũ trong phạm vi batch.
2. writeMultiResourceStep tạo các file phân mảnh.
3. Nếu ghi xong, publishOutputStep tạo manifest hoặc đánh dấu output sẵn sàng.

Nếu writeMultiResourceStep thất bại sau một vài chunk:

- JobInstance vẫn có thể được restart.
- cleanOutputStep đã COMPLETED nên không chạy lại theo mặc định.
- writeMultiResourceStep dùng checkpoint và resource đã lưu để tiếp tục.
- publishOutputStep chỉ chạy sau khi write Step hoàn tất.

Nếu cleanup Step bị lỗi trước khi Step ghi file bắt đầu, restart có thể chạy lại cleanup. Việc đó vẫn an toàn nếu cleanup chỉ xử lý output cũ của batch hiện tại và chưa có writer nào tạo dữ liệu mới.

Không bật allowStartIfComplete cho cleanup Step nếu nó sẽ xóa dữ liệu của lần chạy đã hoàn tất. Nếu có flow hoặc custom decider khiến cleanup được gọi lại, phải kiểm tra trạng thái JobInstance và chỉ cho phép cleanup trong giai đoạn chuẩn bị của một lần chạy mới.

### Không dựa vào JobExecution ID cho thư mục restart

Restart tạo JobExecution mới. Nếu thư mục được đặt theo JobExecution ID, lần restart có thể tạo thư mục khác và không tìm thấy các file cũ cần tiếp tục.

Dùng batchId hoặc key khác ổn định theo JobInstance để xác định output path. Có thể lưu thêm JobExecution ID vào manifest để truy vết từng lần thử, nhưng không dùng nó làm danh tính duy nhất của output cần restart.

## 7. Xóa output cũ theo suffix hay theo batch directory?

Có hai cách quản lý phổ biến:

| Cách | Ưu điểm | Rủi ro/cần lưu ý |
| --- | --- | --- |
| Xóa file theo prefix/suffix trong thư mục chung | Dễ tích hợp với cấu trúc hiện tại | Pattern có thể khớp nhầm file; nhiều Job cùng ghi thư mục sẽ xung đột |
| Dùng thư mục riêng theo batchId | Cô lập output, dễ restart và retention | Cần quản lý thêm thư mục và manifest |

Ưu tiên thư mục riêng theo batch nếu có thể. Nếu phải dùng thư mục chung, hãy tạo prefix chứa batchId:

~~~text
orders-BATCH-A-000.csv
orders-BATCH-A-001.csv
orders-BATCH-B-000.csv
orders-BATCH-B-001.csv
~~~

Cleanup batch A chỉ được khớp đúng prefix của batch A. Không dùng pattern quá rộng như orders-*.csv khi nhiều batch có thể tồn tại đồng thời.

Nếu suffix index bắt đầu từ 0 hoặc 1 tùy implementation/version, đừng hard-code giả định để xóa file. Dùng prefix bao trùm mọi file thuộc batch và kiểm thử với đúng resourceSuffixCreator.

## 8. Phân biệt overwrite, append và restart

Ba hành vi này không giống nhau:

**Overwrite:** lần chạy mới tạo output sạch. File cũ cùng tên được thay thế hoặc xóa theo cấu hình writer.

**Append:** writer ghi thêm vào file đã tồn tại. Chỉ dùng khi output contract yêu cầu tích lũy dữ liệu.

**Restart:** cùng JobInstance tiếp tục ghi từ checkpoint đã lưu. Writer phải giữ file và state phù hợp.

Với MultiResourceItemWriter, append policy của wrapper và delegate phải được hiểu cùng nhau. Nếu version Spring Batch hỗ trợ cấu hình append trên MultiResourceItemWriter, hãy đặt giá trị rõ ràng; đồng thời kiểm tra hành vi append của delegate như FlatFileItemWriter. Không dựa vào default khi output đã tồn tại.

### Vì sao append có thể nguy hiểm?

Nếu lần chạy mới có ít record hơn lần trước và writer append vào các file cùng tên:

- File đầu có thể chứa record cũ và mới.
- File suffix không được mở lại vẫn chứa toàn bộ dữ liệu cũ.
- Header có thể lặp.
- Consumer có thể đọc record của nhiều batch cùng nhau.
- Checkpoint mới không nhất thiết mô tả đúng nội dung đã append từ một JobInstance khác.

Append chỉ phù hợp khi có quy tắc tích lũy rõ, chẳng hạn một file nhật ký append-only với record key duy nhất và consumer hiểu được batch boundary. Với file export theo batch, tạo output mới thường dễ kiểm soát hơn.

### shouldDeleteIfExists không thay thế cleanup tổng thể

FlatFileItemWriter có chính sách xử lý resource hiện tại khi mở. Chính sách đó không tự tìm và xóa mọi suffix cũ mà MultiResourceItemWriter không sử dụng trong lần chạy mới.

Ví dụ writer mới chỉ tạo orders-000.csv và orders-001.csv. Cấu hình xóa resource đang mở không đồng nghĩa nó sẽ tìm orders-002.csv đến orders-010.csv nếu các resource đó không được mở trong lần chạy hiện tại.

Vì vậy, cleanup output cũ cần được thực hiện ở cấp batch directory hoặc prefix, theo chính sách rõ ràng. Không dùng shouldDeleteIfExists như cơ chế retention.

## 9. Không xóa file khi restart

Khi restart, Spring Batch cần:

- JobInstance và identifying JobParameters giống lần chạy trước.
- Reader/writer name ổn định.
- Resource path ổn định.
- Resource suffix creator ổn định.
- Input và thứ tự item không thay đổi ngoài quy tắc cho phép.
- ExecutionContext còn checkpoint tương ứng.
- Các file đã ghi đến checkpoint vẫn tồn tại.

Nếu xóa output trước khi restart, writer có thể khôi phục offset cũ rồi tiếp tục ghi vào file mới rỗng. Kết quả có thể bị thiếu phần đầu, sai vị trí hoặc lỗi khi mở resource.

Nếu file bị mất hoặc bị sửa ngoài Job, không nên tự tạo file rỗng rồi tiếp tục với checkpoint cũ. Hãy phát hiện mismatch và fail rõ ràng, sau đó chọn một chiến lược phục hồi: khôi phục file từ backup, chạy lại JobInstance từ đầu theo quy trình được phê duyệt, hoặc tạo JobInstance mới với batch key mới.

Không sửa trực tiếp ExecutionContext trong JobRepository để ép writer bỏ qua lỗi file nếu chưa xác định dữ liệu đã commit.

## 10. Xử lý output dở dang của Job thất bại

Một Job thất bại có thể để lại:

- File đã hoàn tất một số chunk.
- File hiện tại chỉ có một phần record.
- File đã được tạo nhưng chưa có footer.
- Manifest chưa tồn tại.
- Manifest ở trạng thái PREPARING hoặc INCOMPLETE.

Không nên coi mọi file tồn tại là file hợp lệ để consumer đọc. Dùng trạng thái publish riêng:

~~~text
PREPARING
    |
    v
WRITING
    |
    v
VALIDATING
    |
    v
PUBLISHED
~~~

Consumer chỉ đọc output khi trạng thái PUBLISHED. Nếu Job thất bại, file có thể giữ trong thư mục batch để restart hoặc chuyển sang khu vực quarantine theo retention policy.

Không tạo manifest hoàn tất ngay khi writer mở file. Manifest chỉ nên được đánh dấu hoàn tất sau khi mọi Step ghi file thành công và các kiểm tra đầu ra đạt yêu cầu.

### Có nên xóa file của Job FAILED?

Không nhất thiết. Tùy yêu cầu vận hành:

- Giữ lại để restart cùng JobInstance.
- Giữ lại trong thời hạn ngắn để điều tra.
- Chuyển sang quarantine nếu JobInstance bị hủy và không còn restart.
- Xóa sau khi hết retention và xác nhận không có Job đang chạy.

Nếu Job còn khả năng restart, file dở dang và checkpoint có thể là một cặp cần được bảo toàn. Xóa file mà vẫn giữ metadata restart sẽ làm trạng thái không nhất quán.

## 11. Manifest mô tả bộ output

Với output gồm nhiều file, consumer không nên tự đoán file nào thuộc batch bằng cách quét toàn thư mục. Có thể tạo manifest sau khi writer hoàn tất:

~~~json
{
  "batchId": "BATCH-2026-11-15-A",
  "status": "PUBLISHED",
  "files": [
    {
      "name": "orders-000.csv",
      "recordCount": 100000,
      "sizeBytes": 8240000,
      "checksum": "..."
    },
    {
      "name": "orders-001.csv",
      "recordCount": 27500,
      "sizeBytes": 2260000,
      "checksum": "..."
    }
  ],
  "totalRecords": 127500
}
~~~

Manifest có thể chứa:

- batchId hoặc business key.
- Trạng thái PREPARING, WRITING, VALIDATING, PUBLISHED hoặc FAILED.
- Danh sách file thuộc batch.
- Số record mỗi file và tổng số record.
- Kích thước file và checksum.
- Encoding, delimiter và schema version.
- Thời điểm tạo và thời điểm publish.
- JobExecution ID dùng để truy vết, nếu cần.

Consumer chỉ đọc file được liệt kê trong manifest đã PUBLISHED. Như vậy file stale không nằm trong manifest sẽ không bị đọc nhầm.

### Ghi manifest bằng bước riêng

Một finalize Step có thể:

1. Liệt kê file thuộc batch directory hiện tại.
2. Xác nhận các file là regular file và khớp prefix.
3. Đếm record hoặc dùng counter đã được ghi nhận.
4. Tính checksum nếu yêu cầu.
5. Ghi manifest vào file tạm.
6. Đổi tên manifest tạm thành manifest chính thức sau khi ghi hoàn tất.
7. Cập nhật trạng thái batch thành PUBLISHED.

Không để consumer đọc manifest khi nó đang được ghi. Tên tạm và thao tác publish cần phù hợp với filesystem hoặc object storage đang dùng.

## 12. Atomic publish bằng thư mục staging

Một mẫu phổ biến là ghi output vào thư mục staging rồi publish cả bộ file sau khi hoàn tất:

~~~text
output/
  staging/
    BATCH-A/
      orders-000.csv
      orders-001.csv
      manifest.json
  published/
    BATCH-A/
      orders-000.csv
      orders-001.csv
      manifest.json
~~~

Luồng:

1. Writer chỉ ghi trong staging/BATCH-A.
2. Job hoàn thành và validation thành công.
3. Finalize Step tạo manifest.
4. Publish Step chuyển thư mục batch sang published.
5. Consumer chỉ quét published.

Nếu rename thư mục cùng filesystem được hỗ trợ atomic, consumer có thể nhìn thấy bộ output hoàn chỉnh tại một thời điểm. Atomicity phụ thuộc filesystem, mount, volume và vị trí nguồn/đích; không giả định rename qua hai filesystem là atomic.

Với object storage, rename thường không phải thao tác atomic thực sự; có thể cần copy object, xác minh xong rồi cập nhật một marker/manifest trạng thái PUBLISHED.

## 13. Retention cleanup cho batch cũ

Retention cleanup là công việc định kỳ xóa output đã hết hạn. Nó khác cleanup trước một JobInstance mới.

Một chính sách có thể quy định:

- Batch PUBLISHED được giữ 30 ngày.
- Batch FAILED được giữ 7 ngày để điều tra.
- Batch đang STARTED hoặc có JobExecution đang hoạt động không được xóa.
- Batch đang chờ consumer xác nhận không được xóa.
- Batch có lỗi đối soát được giữ đến khi xử lý xong.

Ví dụ bảng metadata:

| batch_id | status | completed_at | retention_until |
| --- | --- | --- | --- |
| BATCH-A | PUBLISHED | 2026-10-01 | 2026-10-31 |
| BATCH-B | FAILED | 2026-11-10 | 2026-11-17 |
| BATCH-C | WRITING | null | null |

Retention job nên kiểm tra trạng thái và thời hạn trong metadata trước khi xóa. Không chỉ xóa mọi thư mục cũ hơn một số ngày nếu Job có thể đang restart hoặc consumer chưa xử lý xong.

### Trình tự cleanup an toàn

1. Chọn batch đã hết retention và không còn trạng thái active.
2. Đánh dấu batch là DELETING bằng thao tác có kiểm soát.
3. Kiểm tra không có JobExecution đang chạy hoặc restart.
4. Kiểm tra consumer/acknowledgement nếu có yêu cầu.
5. Xóa đúng thư mục batch hoặc chuyển vào trash/quarantine.
6. Xác nhận xóa thành công.
7. Cập nhật metadata thành DELETED.

Nếu xóa thất bại giữa chừng, lần cleanup sau cần có thể tiếp tục idempotently. Không xóa metadata trước khi chắc chắn file đã được xử lý theo chính sách.

## 14. Không xóa output của Job đang chạy

Hai Job có thể chạy đồng thời. Nếu cleanup quét một thư mục chung và xóa file theo prefix quá rộng, nó có thể xóa resource mà Job khác đang ghi.

Các biện pháp:

- Mỗi JobInstance có batchId riêng.
- Không tái sử dụng output directory giữa các batch active.
- Dùng JobRepository hoặc bảng batch control để biết trạng thái active.
- Có lease/lock khi cần nhiều process quản lý cùng thư mục.
- Cleanup chỉ chọn batch đã kết thúc và qua thời hạn bảo vệ.
- Không dựa vào timestamp file để suy ra Job không còn chạy.

File có thể không được cập nhật timestamp trong lúc writer đang giữ resource, hoặc process có thể tạm dừng lâu. Trạng thái Job và cơ chế lock đáng tin cậy hơn việc chỉ nhìn thời gian sửa file.

## 15. Quản lý output khi nhiều partition ghi file

Trong partitioned Step, mỗi worker có thể tạo một hoặc nhiều file. Cần tránh các partition tạo cùng tên resource:

~~~text
staging/BATCH-A/
  partition-000/
    orders-000.csv
    orders-001.csv
  partition-001/
    orders-000.csv
  partition-002/
    orders-000.csv
~~~

Hoặc suffix có thể bao gồm partition ID:

~~~text
orders-part-000-000.csv
orders-part-000-001.csv
orders-part-001-000.csv
orders-part-002-000.csv
~~~

Mỗi worker cần resource path và writer state riêng. Không để nhiều MultiResourceItemWriter độc lập cùng dùng một base resource và suffix sequence giống nhau.

Sau khi mọi partition hoàn tất, một finalize Step có thể:

- Xác nhận tất cả partition đã COMPLETED.
- Thu thập danh sách file của từng partition.
- Kiểm tra tổng record và số file.
- Ghi manifest chung.
- Publish output.

Nếu một partition thất bại, không publish bộ file chung. Giữ output và checkpoint của partition có thể restart; chỉ cleanup khi batch đã bị hủy hoặc hết retention theo quy định.

## 16. Dọn file khi số resource giảm

Đây là trường hợp điển hình gây stale output:

~~~text
Lần A: tạo 8 file
  output-000 ... output-007

Lần B: chỉ tạo 3 file
  output-000 ... output-002

File còn sót:
  output-003 ... output-007
~~~

Nếu buộc phải dùng cùng prefix cho hai lần chạy độc lập, hãy:

- Dọn tất cả file thuộc đúng prefix trước lần chạy mới.
- Thực hiện cleanup trong Step chuẩn bị, không trong writer open.
- Đảm bảo lần chạy mới không phải restart của JobInstance cũ.
- Không cho hai Job cùng sử dụng prefix đó đồng thời.
- Chỉ publish sau khi tất cả file mới được xác nhận.

Một lựa chọn tốt hơn là dùng prefix hoặc thư mục riêng theo batch key, tránh phải dọn suffix cũ ngay trước khi ghi.

## 17. Output cũ và lỗi cấu hình resource suffix

ResourceSuffixCreator quyết định tên file được tạo. Nếu suffix không duy nhất hoặc không ổn định, có thể ghi đè file hoặc restart vào sai resource.

Ví dụ không an toàn:

~~~java
.resourceSuffixCreator(index ->
        "-" + System.currentTimeMillis() + ".csv")
~~~

Mỗi lần gọi có thể tạo tên khác nhau, khiến restart không tìm lại resource cũ.

Ví dụ ổn định:

~~~java
.resourceSuffixCreator(index ->
        String.format("-%03d.csv", index))
~~~

Khi có partition:

~~~java
String partitionId = "part-001";

.resourceSuffixCreator(index ->
        "-" + partitionId + "-" + String.format("%03d", index) + ".csv")
~~~

partitionId phải ổn định cho partition đó qua restart. Không tạo suffix dựa trên random value hoặc thời gian hiện tại nếu cần khôi phục resource.

Nếu đổi itemCountLimitPerResource, thứ tự input hoặc suffix creator giữa lần chạy và restart, số lượng và ranh giới file có thể khác. Giữ các tham số này ổn định trong cùng JobInstance.

## 18. Append và nhiều file

Append với MultiResourceItemWriter cần được cân nhắc ở hai cấp:

- Wrapper quyết định resource sequence và trạng thái resource hiện tại.
- Delegate quyết định cách mở từng file, ghi tiếp hay xóa nội dung cũ.

Nếu ứng dụng muốn tiếp tục cùng một file qua restart, hãy dùng cơ chế saveState/checkpoint của writer. Không bật append chỉ để xử lý restart nếu framework đã có state tương ứng.

Nếu ứng dụng muốn nối output của nhiều batch độc lập vào cùng file, cần xác định:

- File nào được append.
- Số record và batch boundary.
- Header có được ghi lại không.
- Checkpoint của mỗi JobInstance được quản lý thế nào.
- Hai Job có thể append đồng thời không.
- Consumer phân biệt dữ liệu của các batch ra sao.

Append đồng thời từ nhiều Job thường không an toàn nếu không có cơ chế serialize/lock. Với export batch, tách file theo batch và hợp nhất ở bước riêng thường dễ kiểm soát hơn.

## 19. Kiểm tra output trước khi publish

Sau khi writer hoàn tất, không nên chỉ kiểm tra số file. Cần xác nhận nội dung:

- Tất cả file được tạo trong batch directory hiện tại.
- Tên file đúng prefix và suffix.
- Không có file rỗng ngoài dự kiến.
- Tổng số record bằng số item dự kiến ghi, có tính đến filter/skip.
- Header/footer đúng format.
- Encoding và line separator đúng contract.
- Không có file từ batch khác.
- Checksum hoặc hash khớp nếu được yêu cầu.
- File cuối cùng có thể được parser phía consumer đọc.

Có thể ghi thống kê file trong ExecutionContext hoặc bảng batch metadata. Tuy nhiên, dữ liệu thống kê phải được cập nhật theo transaction/chunk phù hợp và có khả năng khôi phục qua restart.

Không dùng số file hoặc tổng kích thước làm đại diện duy nhất cho tính đúng đắn. Một file có thể có đúng kích thước nhưng chứa record trùng hoặc thiếu.

## 20. Quản lý file output với tên tạm

Một chiến lược khác là ghi mỗi file vào tên tạm rồi đổi tên khi hoàn tất:

~~~text
orders-000.csv.part
orders-001.csv.part
orders-002.csv.part
~~~

Sau khi writer đóng file và validation thành công:

~~~text
orders-000.csv
orders-001.csv
orders-002.csv
~~~

Consumer chỉ đọc file có extension chính thức hoặc chỉ đọc manifest PUBLISHED. File .part biểu thị file chưa hoàn tất.

Với MultiResourceItemWriter, việc thêm extension tạm có thể được thực hiện bằng base resource/suffix hoặc một bước publish sau khi writer đóng. Cần giữ mapping tên tạm sang tên chính thức ổn định qua restart.

Không đổi tên resource đang được writer mở. Publish chỉ thực hiện sau khi Step đã đóng writer và xác nhận mọi resource hoàn tất.

## 21. Xử lý file cũ trong môi trường nhiều node

Nếu Job có thể chạy trên nhiều application instance, filesystem local của một node có thể không phải nơi node khác nhìn thấy. Một cleanup tasklet chạy trên node A có thể không xóa file trên node B nếu mỗi node có local disk riêng.

Cần xác định loại storage:

- Shared filesystem.
- Persistent volume dùng chung.
- Object storage.
- Local disk riêng từng node.

Với shared filesystem, cần cơ chế lock/ownership để cleanup không đụng vào Job đang chạy. Với object storage, dùng prefix theo batchId và manifest/marker; thao tác delete có thể thực hiện theo danh sách object. Với local disk riêng, cần bảo đảm worker và restart được định tuyến về cùng storage hoặc dùng storage bền vững chung.

Không giả định path giống nhau trên hai node có nghĩa đó là cùng một resource.

## 22. Những lỗi thường gặp

### Không dọn suffix cũ khi lần chạy mới tạo ít file hơn

Consumer đọc cả file mới và file cũ. Dùng batch directory hoặc cleanup đúng prefix trước lần chạy mới.

### Xóa file trong mỗi lần mở writer

Restart có thể mất output đã commit. Đặt cleanup ở Step chuẩn bị chỉ chạy cho lần chạy mới.

### Dùng JobExecution ID làm output identity

Restart tạo JobExecution mới và có thể trỏ sang thư mục khác. Dùng batch key ổn định theo JobInstance.

### Dùng prefix chung cho nhiều Job

Job có thể ghi đè hoặc cleanup file của nhau. Tách output theo batchId/partitionId.

### Dựa vào shouldDeleteIfExists để dọn mọi file cũ

Chính sách của delegate chỉ tác động resource nó mở, không nhất thiết xóa suffix cũ không được sử dụng. Cleanup toàn bộ batch output ở cấp directory/prefix.

### Append mà không kiểm soát

Có thể lặp header, nối batch khác nhau và ghi trùng dữ liệu. Chỉ append khi contract quy định rõ.

### Publish trước khi writer đóng

Consumer có thể đọc file đang được ghi. Chờ Step hoàn tất, kiểm tra output rồi publish.

### Xóa output FAILED trước khi quyết định restart

Checkpoint vẫn tham chiếu file đã mất. Giữ file cho restart hoặc chuyển sang trạng thái không còn restart trước khi cleanup.

### Dùng glob quá rộng

Cleanup có thể xóa file không thuộc batch. Chỉ match prefix và thư mục do ứng dụng sở hữu.

### Retention chỉ dựa vào thời gian sửa file

File của Job đang chạy có thể không đổi timestamp trong thời gian dài. Kiểm tra Job status và batch metadata.

### Hai partition dùng cùng resource suffix

Writer có thể ghi đè file của nhau. Thêm partition identity vào output path hoặc prefix.

### Thay suffix creator hoặc page/chunk configuration khi restart

Resource sequence và checkpoint có thể không còn khớp. Giữ cấu hình ổn định cho cùng JobInstance.

## 23. Kiểm thử quản lý output cũ

Nên kiểm thử với temporary directory để không ảnh hưởng file thật:

~~~java
@TempDir
Path outputRoot;
~~~

### Test dọn đúng prefix

Chuẩn bị:

~~~text
batch-A/
  orders-000.csv
  orders-001.csv
  customers-000.csv
  notes.txt
~~~

Sau cleanup cho orders:

~~~text
batch-A/
  customers-000.csv
  notes.txt
~~~

Test phải xác nhận file không thuộc prefix vẫn tồn tại. Nếu thư mục chứa subdirectory hoặc symbolic link, xác nhận cleanup không xóa theo đệ quy ngoài ý muốn.

### Test số file giảm giữa hai lần chạy mới

1. Tạo 8 file giả lập từ lần chạy trước.
2. Chạy cleanup của batch mới trên đúng output scope.
3. Tạo 3 file mới.
4. Liệt kê output và xác nhận chỉ còn 3 file thuộc batch hiện tại.

### Test restart không cleanup

1. Chạy cleanup Step và xác nhận Step COMPLETED.
2. Tạo một số file output và lưu checkpoint.
3. Làm Step ghi file thất bại.
4. Restart cùng JobInstance.
5. Xác nhận cleanup Step không chạy lại.
6. Xác nhận writer tiếp tục từ checkpoint và không mất file đã commit.

Đây là integration test cần JobRepository và Spring Batch infrastructure. Unit test của cleanup tasklet không chứng minh flow restart bỏ qua Step đã hoàn tất.

### Test không xóa batch khác

Tạo hai thư mục batch-A và batch-B, chạy cleanup batch-A và xác nhận toàn bộ file batch-B vẫn còn nguyên.

### Test publish và manifest

Xác nhận manifest chỉ được đánh dấu PUBLISHED khi:

- Mọi output file đã đóng.
- Số record và checksum hợp lệ.
- Tất cả partition đã hoàn tất.
- Không còn file tạm hoặc trạng thái ghi dở.

### Test lỗi giữa cleanup

Nếu một file không thể xóa do permission hoặc file đang được process khác giữ, cleanup Step nên thất bại rõ ràng. Không tiếp tục ghi vào thư mục có thể còn output cũ nếu điều đó làm consumer đọc sai.

## 24. Quy trình thiết kế quản lý output cũ

Khi xây dựng pipeline multi-resource, hãy xác định:

1. Một JobInstance tạo bộ file ở thư mục hoặc prefix nào?
2. Batch key có ổn định qua restart và khác nhau giữa các lần chạy độc lập không?
3. ResourceSuffixCreator có tạo tên ổn định và duy nhất không?
4. Số file có thể giảm giữa hai lần chạy không?
5. Output cũ được cleanup trước lần chạy mới hay được cô lập bằng thư mục riêng?
6. Cleanup Step có chạy lại khi restart không?
7. Job FAILED cần giữ output để restart hay quarantine?
8. Append, overwrite và restart được phân biệt thế nào?
9. Consumer nhận biết bộ file hoàn tất qua manifest hoặc trạng thái publish nào?
10. Retention job kiểm tra Job status, batch state và consumer acknowledgement ra sao?
11. Nhiều Job/partition/node có thể ghi hoặc xóa cùng prefix không?
12. Cleanup có giới hạn trong thư mục và pattern do ứng dụng sở hữu không?
13. Validation có kiểm tra record count, checksum, encoding và schema không?
14. Integration test có bao phủ số file giảm, restart và cleanup batch khác không?

Ưu tiên output directory riêng theo batch key, giữ nguyên trong restart, tạo manifest sau khi hoàn tất và chạy retention cleanup độc lập. Nếu phải tái sử dụng một thư mục, hãy dọn đúng prefix trong Step chuẩn bị của JobInstance mới và bảo đảm không có Job khác sử dụng cùng prefix.

## Kết luận

Quản lý output cũ trong Spring Batch là quản lý vòng đời của cả bộ file do MultiResourceItemWriter tạo ra. Writer chia item thành các resource mới nhưng không nên được xem là cơ chế tự dọn mọi suffix còn sót từ lần chạy trước. Dùng thư mục hoặc prefix riêng theo batchId ổn định qua restart; nếu phải tái sử dụng thư mục, cleanup đúng phạm vi trong Step chuẩn bị chỉ chạy cho JobInstance mới. Giữ file và checkpoint khi restart, phân biệt append với overwrite, không xóa output của Job đang chạy hoặc còn khả năng restart. Sau khi mọi writer và partition hoàn tất, xác nhận record count/checksum, tạo manifest và publish bộ file; retention cleanup xử lý các batch hết hạn theo trạng thái và chính sách lưu trữ.
