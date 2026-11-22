# Restart với nhiều output file

Trong Spring Batch, một Step có thể cần ghi dữ liệu ra nhiều file thay vì một file duy nhất. Ví dụ, Job xuất dữ liệu khách hàng thành các file có tối đa một số lượng record nhất định, chia báo cáo theo nhóm, hoặc tạo nhiều file kết quả để hệ thống downstream tải song song. Khi Job thất bại giữa chừng, việc restart phải tiếp tục đúng file và đúng vị trí đã commit, đồng thời giữ nguyên các file đã hoàn tất.

Spring Batch cung cấp **MultiResourceItemWriter** để ghi item qua nhiều Resource. Writer này dùng một **ResourceAwareItemWriterItemStream** làm delegate, thường là FlatFileItemWriter. Nó quản lý resource hiện tại và chuyển sang resource mới theo giới hạn item. Để restart đáng tin cậy, cả writer bao ngoài và delegate cần lưu state, tên writer phải ổn định, tên file phải tái tạo được và input phải giữ nguyên qua lần restart.

## 1. Bài toán ghi nhiều output file

Giả sử một Job xuất 25.000 khách hàng. Yêu cầu vận hành là mỗi file chỉ chứa một lượng record giới hạn để dễ tải, chuyển giao hoặc xử lý tiếp.

Một kết quả có thể có dạng:

~~~text
export/
  customers-0001.csv
  customers-0002.csv
  customers-0003.csv
  ...
~~~

Nếu Job dừng sau khi ghi được một phần file thứ ba, lần restart cần:

- Giữ nguyên các file đã hoàn tất.
- Mở lại đúng file đang được ghi.
- Khôi phục vị trí ghi đã commit gần nhất.
- Không ghi đè hoặc xóa dữ liệu đã commit.
- Tiếp tục tạo file tiếp theo khi đạt giới hạn.
- Không tạo file trùng tên hoặc bỏ sót record.

Nếu chỉ dùng một FlatFileItemWriter thông thường, writer chỉ quản lý một Resource. Muốn xoay vòng qua nhiều file, ứng dụng phải tự quản lý index, tên file, state của từng resource và checkpoint. MultiResourceItemWriter đóng gói phần lớn cơ chế này.

## 2. MultiResourceItemWriter hoạt động như thế nào?

MultiResourceItemWriter nhận một base Resource, một delegate writer và giới hạn số item trên mỗi Resource. Khi đạt ngưỡng, nó chuyển delegate sang Resource kế tiếp.

~~~text
Chunk items
    |
    v
MultiResourceItemWriter
    |
    +--> Resource 1: delegate writer
    |
    +--> Resource 2: delegate writer
    |
    +--> Resource 3: delegate writer
    |
    v
Output files
~~~

Các trách nhiệm chính:

- Quản lý resource index và số item đã ghi vào resource hiện tại.
- Tạo Resource tiếp theo bằng base Resource và ResourceSuffixCreator.
- Gọi lifecycle của delegate khi resource thay đổi.
- Lưu trạng thái cần thiết vào ExecutionContext khi saveState được bật.
- Khôi phục resource hiện tại và số item khi Step restart.

Delegate chịu trách nhiệm ghi nội dung của từng item. Ví dụ, FlatFileItemWriter tạo dòng CSV, xử lý encoding, header/footer và checkpoint byte offset. MultiResourceItemWriter không thay thế chức năng định dạng file của delegate.

## 3. Cấu hình MultiResourceItemWriter cơ bản

Trong Spring Batch 5, có thể dùng MultiResourceItemWriterBuilder:

~~~java
@Bean
MultiResourceItemWriter<Customer> customerMultiWriter(
        FlatFileItemWriter<Customer> customerFileDelegate) {

    return new MultiResourceItemWriterBuilder<Customer>()
            .name("customerMultiWriter")
            .resource(new FileSystemResource("output/customers"))
            .resourceSuffixCreator(index ->
                    String.format("-%04d.csv", index))
            .itemCountLimitPerResource(5_000)
            .delegate(customerFileDelegate)
            .saveState(true)
            .build();
}
~~~

Các cấu hình quan trọng:

- name: tên ổn định để tạo key state trong ExecutionContext.
- resource: Resource gốc làm cơ sở tạo các output Resource.
- resourceSuffixCreator: tạo suffix theo resource index.
- itemCountLimitPerResource: ngưỡng số item cho mỗi output Resource.
- delegate: writer thực sự ghi nội dung.
- saveState(true): bật lưu state để hỗ trợ restart.

Tên file thực tế phụ thuộc cách MultiResourceItemWriter kết hợp base Resource với suffix. Hãy kiểm tra quy tắc index bắt đầu và tên file được tạo trong phiên bản Spring Batch đang dùng bằng integration test. Không để suffix phụ thuộc thời gian hiện tại hoặc giá trị ngẫu nhiên, vì restart phải tạo lại đúng tên Resource đã dùng trước đó.

## 4. Cấu hình FlatFileItemWriter làm delegate

Delegate cần triển khai ResourceAwareItemWriterItemStream để MultiResourceItemWriter có thể gán Resource mới và gọi lifecycle open/update/close. FlatFileItemWriter là lựa chọn phổ biến:

~~~java
@Bean
FlatFileItemWriter<Customer> customerFileDelegate() {
    return new FlatFileItemWriterBuilder<Customer>()
            .name("customerFileDelegate")
            .encoding("UTF-8")
            .lineAggregator(customer ->
                    String.join(",",
                            csv(customer.getCustomerId()),
                            csv(customer.getFullName()),
                            csv(customer.getEmail())))
            .saveState(true)
            .build();
}

private String csv(String value) {
    if (value == null) {
        return "";
    }
    String escaped = value.replace("\"", "\"\"");
    return "\"" + escaped + "\"";
}
~~~

MultiResourceItemWriter sẽ gán Resource hiện tại cho delegate trước khi mở file. Vì vậy, delegate không cần tự quyết định tên file cho từng resource; việc tạo tên thuộc trách nhiệm của writer bao ngoài.

Tên delegate cũng cần ổn định và duy nhất trong phạm vi Step. FlatFileItemWriter dùng tên để tạo key lưu trạng thái riêng trong ExecutionContext. Không đổi tên writer giữa lần chạy đầu và restart nếu muốn khôi phục checkpoint cũ.

Ví dụ line aggregator ở trên minh họa CSV cơ bản. Với dữ liệu có delimiter, quote, newline hoặc encoding đặc thù, nên dùng formatter/CSV library phù hợp thay vì tự ghép chuỗi. Việc escape CSV cần đúng quy tắc của định dạng downstream.

## 5. ResourceSuffixCreator và tên file ổn định

ResourceSuffixCreator quyết định phần suffix được thêm vào Resource gốc khi tạo các output file. Có thể dùng lambda:

~~~java
.resourceSuffixCreator(index -> String.format("-%04d.csv", index))
~~~

Một chiến lược tên file cần bảo đảm:

- Cùng một index luôn tạo cùng suffix.
- Tên file không phụ thuộc thread scheduling.
- Tên file không phụ thuộc thời gian gọi writer.
- Không có collision với file của JobExecution khác.
- Tên file có thể được tái tạo sau khi process khởi động lại.

Ví dụ, một base Resource có thể được đặt theo batch ID cố định, còn suffix biểu diễn số thứ tự resource. Nếu cùng batch được restart, base path và suffix algorithm phải giống lần chạy đầu.

Không nên dùng các biểu thức như:

~~~java
.resourceSuffixCreator(index ->
        "-" + Instant.now().toEpochMilli() + ".csv")
~~~

Vì cùng một index có thể tạo tên khác sau restart. Tương tự, không dùng UUID mới cho mỗi lần tạo resource nếu UUID không được lưu và khôi phục một cách bền vững.

Nếu downstream cần biết danh sách output file, hãy lưu manifest hoặc metadata sau khi Step hoàn tất. Không nên để consumer tự đoán tất cả file chỉ từ một pattern nếu có khả năng file cũ hoặc file dở dang còn tồn tại trong thư mục.

## 6. itemCountLimitPerResource

itemCountLimitPerResource đặt ngưỡng số item mà writer dùng để quyết định chuyển sang Resource kế tiếp.

Ví dụ:

~~~java
.itemCountLimitPerResource(10_000)
~~~

Với 25.000 item, kết quả dự kiến là nhiều resource liên tiếp. Số file thực tế phụ thuộc tổng số item, giới hạn, cách writer xử lý chunk boundary và việc có item bị filter hay skip.

Lưu ý:

- Đây là giới hạn theo số item, không phải số byte hoặc kích thước file.
- Record có độ dài khác nhau nên kích thước file có thể khác đáng kể.
- Item bị filter trong processor không đi tới writer và không làm tăng số item được writer ghi.
- Item bị skip ở giai đoạn write cần được tính theo hành vi thực tế của Step và writer.
- Cần kiểm tra cách chia chunk qua ranh giới resource ở phiên bản framework đang dùng.

Không giả định rằng một file luôn có đúng số byte hoặc một số dòng cố định chỉ vì đã cấu hình itemCountLimitPerResource. Nếu yêu cầu giới hạn kích thước byte, cần một chiến lược khác hoặc writer tùy chỉnh có theo dõi byte count.

Để kết quả dễ dự đoán, chọn chunk size và item limit phù hợp. Nếu chunk lớn hơn ngưỡng file, cần integration test để xác nhận cách MultiResourceItemWriter phân phối item trong chunk và số item tối đa thực tế trên mỗi resource.

## 7. Đưa writer vào chunk-oriented Step

MultiResourceItemWriter được dùng như một ItemWriter bình thường:

~~~java
@Bean
Step exportCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        MultiResourceItemWriter<Customer> customerMultiWriter) {

    return new StepBuilder("exportCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerMultiWriter)
            .build();
}
~~~

Step đọc và xử lý item theo chunk. Writer ghi output của chunk vào resource hiện tại; khi đạt ngưỡng, nó chuyển sang resource kế tiếp.

Transaction manager quản lý transaction của chunk. Với FlatFileItemWriter, cơ chế ghi có hỗ trợ transaction để dữ liệu chưa commit có thể được xử lý khi rollback/restart theo trạng thái đã lưu. Nếu delegate là writer tùy chỉnh hoặc ghi ra hệ thống ngoài database, cần tự bảo đảm semantics rollback/restart phù hợp.

## 8. MultiResourceItemWriter lưu state nào?

Để restart, writer cần biết resource hiện tại và vị trí ghi. MultiResourceItemWriter lưu state quản lý resource trong ExecutionContext, bao gồm thông tin như:

- Index của Resource đang sử dụng.
- Số item đã ghi vào Resource hiện tại.
- State của delegate writer, nếu delegate hỗ trợ ItemStream và save state.

Delegate thường lưu checkpoint riêng. Với FlatFileItemWriter, state có thể gồm số dòng đã ghi và byte offset đã commit để khôi phục file.

Có thể hình dung ExecutionContext:

~~~text
StepExecutionContext
  |
  +-- multiResourceWriter.resourceIndex
  |
  +-- multiResourceWriter.currentResourceItemCount
  |
  +-- customerFileDelegate.current.count
  |
  +-- customerFileDelegate.output.position
~~~

Tên key thực tế được tạo dựa trên tên component và implementation. Không nên phụ thuộc trực tiếp vào key nội bộ nếu không cần; hãy để writer quản lý state qua ItemStream lifecycle.

Nếu saveState bị tắt, writer không thể khôi phục đầy đủ resource index và checkpoint theo cơ chế thông thường. Khi đó, restart có thể bắt đầu lại hoặc ghi sai vị trí. Với Job cần restart, bật saveState cho writer bao ngoài và delegate.

## 9. Vì sao cả writer bao ngoài và delegate đều cần saveState?

Hai writer giữ hai loại state khác nhau:

| Thành phần | State cần khôi phục |
|---|---|
| MultiResourceItemWriter | Đang ở resource index nào và đã ghi bao nhiêu item vào resource hiện tại |
| FlatFileItemWriter delegate | Vị trí byte/dòng đã commit trong file hiện tại và thông tin ghi liên quan |

Nếu chỉ lưu state của delegate, framework có thể biết vị trí bên trong file nhưng không biết phải chọn resource index nào. Nếu chỉ lưu state của MultiResourceItemWriter, writer có thể biết tên file nhưng delegate không biết vị trí đã commit để tiếp tục.

Vì vậy, cấu hình restartable cần:

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileDelegate")
        .lineAggregator(customerLineAggregator)
        .saveState(true)
        .build();

new MultiResourceItemWriterBuilder<Customer>()
        .name("customerMultiWriter")
        .resource(baseResource)
        .itemCountLimitPerResource(5_000)
        .delegate(customerFileDelegate)
        .saveState(true)
        .build();
~~~

Tên của cả hai component phải ổn định. Không tạo tên theo UUID hoặc timestamp mới mỗi lần application context khởi tạo.

## 10. Restart sau khi một số file đã hoàn tất

Giả sử mỗi resource có giới hạn 1.000 item và Job xử lý 3.400 item. Job có thể đã hoàn tất file thứ nhất và thứ hai, đang ghi file thứ ba thì gặp lỗi.

Luồng khái quát:

~~~text
Lần chạy đầu
  Resource 1: 1.000 item -> hoàn tất
  Resource 2: 1.000 item -> hoàn tất
  Resource 3: 400 item đã commit
  Job thất bại

Restart cùng JobInstance
  Giữ Resource 1 và Resource 2
  Mở lại Resource 3
  Khôi phục vị trí đã commit
  Ghi các item còn lại
  Khi đạt ngưỡng, tạo Resource 4
~~~

Các file đã hoàn tất không nên bị xóa hoặc ghi lại nếu chúng thuộc cùng execution đã restart. Writer cần tái tạo đúng resource hiện tại từ state đã lưu và delegate cần khôi phục checkpoint trong resource đó.

Nếu output directory bị xóa trước khi restart, writer có thể không còn resource để khôi phục hoặc tạo ra output không đầy đủ. Hãy bảo vệ các file đã commit cho tới khi Job hoàn tất và downstream đã tiếp nhận theo quy trình.

## 11. Điều kiện để restart đúng

Restart với nhiều output file cần giữ ổn định nhiều yếu tố hơn restart với một file:

1. **Cùng JobInstance:** dùng lại identifying JobParameters của lần chạy ban đầu.
2. **Cùng input:** resource đầu vào, nội dung và thứ tự item phải tương ứng với lần chạy trước.
3. **Cùng base output Resource:** đường dẫn gốc không thay đổi.
4. **Cùng suffix algorithm:** mỗi resource index tạo cùng tên file.
5. **Cùng item limit:** không thay đổi itemCountLimitPerResource giữa lần chạy và restart.
6. **Cùng writer names:** tên MultiResourceItemWriter và delegate ổn định.
7. **State được bật:** saveState cho writer bao ngoài và delegate.
8. **Output chưa bị cleanup:** giữ các resource đã commit và file hiện tại.
9. **Cùng mapping/format:** line aggregator, encoding, header và schema output tương thích.
10. **Cùng thứ tự xử lý:** nếu item order thay đổi, file index và nội dung có thể thay đổi.

Nếu một trong các yếu tố này đổi, checkpoint cũ có thể không còn tương ứng với output hiện tại. Với yêu cầu thay đổi format hoặc chia file, thường nên tạo JobInstance mới hoặc thiết kế migration rõ ràng thay vì restart bằng cấu hình mới.

## 12. JobParameters và output path

Output path thường nên được xác định từ một identifying JobParameter hoặc một định danh batch ổn định. Ví dụ:

~~~text
input.file = /data/in/customers-2026-11-15.json
batch.id   = CUSTOMER-20261115
output.dir = /data/out/CUSTOMER-20261115
~~~

Khi restart, truyền lại cùng identifying parameters để Spring Batch tìm đúng JobInstance. Nếu output.dir được tính từ thời điểm hiện tại mỗi lần launch, restart có thể ghi vào thư mục khác dù JobRepository khôi phục checkpoint cũ.

Một cấu hình StepScope:

~~~java
@Bean
@StepScope
MultiResourceItemWriter<Customer> customerMultiWriter(
        @Value("#{jobParameters['output.dir']}") String outputDir,
        FlatFileItemWriter<Customer> customerFileDelegate) {

    Resource baseResource = new FileSystemResource(
            Path.of(outputDir, "customers").toFile());

    return new MultiResourceItemWriterBuilder<Customer>()
            .name("customerMultiWriter")
            .resource(baseResource)
            .resourceSuffixCreator(index ->
                    String.format("-%04d.csv", index))
            .itemCountLimitPerResource(5_000)
            .delegate(customerFileDelegate)
            .saveState(true)
            .build();
}
~~~

JobParameters output.dir cần được cố định cho JobInstance. Không dùng JobParameters non-identifying để thay đổi output directory giữa lần chạy và restart nếu writer state vẫn thuộc cùng execution.

## 13. Tên file và file collision giữa các lần chạy

Hai JobInstance khác nhau có thể chạy đồng thời. Nếu cả hai dùng cùng base Resource và suffix, chúng có thể ghi đè hoặc trộn output.

Nên tạo namespace output riêng theo batch ID hoặc JobInstance identity:

~~~text
output/
  CUSTOMER-20261115-A/
    customers-0001.csv
    customers-0002.csv
  CUSTOMER-20261115-B/
    customers-0001.csv
    customers-0002.csv
~~~

Đảm bảo:

- Batch ID không trùng giữa các lần chạy độc lập.
- Restart cùng JobInstance dùng lại đúng batch ID.
- Hai execution khác nhau không dùng chung output directory.
- Quyền ghi file được giới hạn theo ứng dụng.
- Quy trình cleanup không xóa thư mục đang được Job khác sử dụng.

Nếu Job có thể được launch đồng thời với cùng identifying parameters, JobRepository thường kiểm soát việc chạy cùng JobInstance theo trạng thái execution; tuy nhiên, hệ thống vẫn cần quy tắc chống collision cho các JobInstance khác nhau và các lần chạy được cấu hình sai.

## 14. Rollback và file output

Database transaction có thể rollback thay đổi database, nhưng file là một resource bên ngoài database transaction thông thường. FlatFileItemWriter của Spring Batch có hỗ trợ transaction-aware buffering và checkpoint để xử lý ghi file theo chunk. Tuy nhiên, không nên suy rộng bảo đảm đó sang mọi custom delegate hoặc mọi filesystem.

Các trường hợp cần phân biệt:

- Dữ liệu ghi trong buffer nhưng chunk rollback: writer transaction-aware có thể loại bỏ phần chưa commit.
- Dữ liệu đã commit ở chunk trước: phải giữ lại và restart sau checkpoint.
- Process bị kill đột ngột: file có thể có tail chưa được checkpoint; delegate cần khôi phục/truncate theo state đã lưu nếu implementation hỗ trợ.
- Custom writer ghi HTTP/object storage: transaction database không tự hoàn tác request đã gửi.
- File system hoặc disk lỗi: restart có thể không mở hoặc ghi được resource.

Nếu delegate không hỗ trợ rollback/restart, MultiResourceItemWriter không tự biến nó thành transaction-aware. Delegate phải tự triển khai ItemStream và có chiến lược phục hồi phù hợp.

## 15. FlatFileItemWriter và checkpoint khi restart

FlatFileItemWriter lưu state để biết vị trí đã ghi. Khi restart, nó có thể dùng checkpoint đã lưu để tiếp tục từ byte offset tương ứng, xử lý phần dữ liệu chưa commit theo semantics của implementation.

Các cấu hình liên quan:

- name: định danh state của delegate.
- saveState(true): lưu checkpoint.
- encoding: giữ nguyên encoding giữa các lần chạy.
- lineAggregator: giữ format dòng ổn định.
- header/footer callback: giữ logic header/footer nhất quán.
- append/shouldDeleteIfExists: cấu hình nhất quán với chiến lược restart.

Không tùy tiện bật append hoặc shouldDeleteIfExists khi Job cần restart. Việc mở file mới và mở lại file đang có checkpoint là hai tình huống khác nhau. Hãy kiểm tra behavior của FlatFileItemWriter trong phiên bản đang dùng và test cả fresh execution lẫn restart.

Đặc biệt, không chạy script xóa output directory trước mỗi lần launch nếu lần launch đó có thể là restart. Cleanup chỉ nên chạy khi xác định chắc chắn đó là một JobInstance mới hoặc một lần chạy mới có chủ đích.

## 16. Header và footer trên từng output file

FlatFileItemWriter có thể ghi header và footer. Khi dùng làm delegate cho MultiResourceItemWriter, lifecycle của delegate gắn với từng Resource. Do đó, header/footer có thể được áp dụng cho từng file tùy cấu hình writer.

Ví dụ:

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileDelegate")
        .headerCallback(writer ->
                writer.write("customerId,fullName,email"))
        .footerCallback(writer ->
                writer.write("# end of file"))
        .lineAggregator(customerLineAggregator)
        .saveState(true)
        .build();
~~~

Nếu mỗi file cần header riêng, cấu hình header callback ở delegate là phù hợp. Nếu chỉ file đầu tiên hoặc file cuối cùng cần metadata đặc biệt, cần thêm cơ chế nhận biết resource index hoặc tạo manifest sau Step.

Footer cần được xử lý cẩn thận khi restart. Một file chưa hoàn tất không nên bị xem như file hoàn chỉnh chỉ vì close được gọi trong đường cleanup. Với yêu cầu kiểm soát trạng thái file, có thể ghi marker hoàn tất hoặc manifest sau khi Step thành công.

## 17. File hoàn tất và file đang ghi

Trong lúc Job chạy, output directory có thể chứa cả file đã hoàn tất và file đang ghi. Downstream không nên tự động đọc mọi file xuất hiện trong thư mục nếu không biết Job đã hoàn tất hay chưa.

Một chiến lược an toàn là:

1. Ghi output vào thư mục staging riêng cho batch.
2. Chỉ đánh dấu batch hoàn tất sau khi Step/Job thành công.
3. Tạo manifest chứa danh sách file, số record và checksum nếu cần.
4. Công bố manifest hoặc chuyển thư mục sang vùng ready.
5. Downstream chỉ đọc batch đã được đánh dấu hoàn tất.

Ví dụ cấu trúc:

~~~text
staging/
  batch-CUSTOMER-20261115/
    customers-0001.csv
    customers-0002.csv
    customers-0003.csv
    manifest.json

ready/
  batch-CUSTOMER-20261115/
~~~

Việc publish thư mục hoặc manifest cần được thiết kế theo khả năng atomic của filesystem/object storage. Nếu không thể rename atomic, dùng trạng thái manifest hoặc marker file được ghi sau cùng.

MultiResourceItemWriter không tự quản lý quy trình publish toàn bộ batch. Đây là trách nhiệm của Step cuối, Job listener hoặc một bước publish riêng.

## 18. Tạo manifest cho nhiều output file

Manifest giúp downstream biết chính xác những file thuộc batch và file nào đã hoàn tất:

~~~json
{
  "batchId": "CUSTOMER-20261115",
  "status": "COMPLETED",
  "files": [
    {
      "name": "customers-0001.csv",
      "recordCount": 5000
    },
    {
      "name": "customers-0002.csv",
      "recordCount": 5000
    }
  ]
}
~~~

Trong ứng dụng thực tế, manifest có thể có:

- Batch ID và JobExecution ID.
- Input file ID hoặc checksum.
- Output file names.
- Record count theo từng file.
- Tổng record count.
- File size và checksum.
- Schema/format version.
- Timestamp bắt đầu và hoàn tất.
- Trạng thái COMPLETED hoặc FAILED.

Chỉ publish manifest trạng thái COMPLETED sau khi tất cả output đã đóng và Step/Job đạt trạng thái thành công. Nếu Job thất bại, có thể ghi metadata FAILED ở một vùng audit riêng nhưng downstream không được coi các file dở dang là batch hoàn chỉnh.

Nếu cần record count theo từng file, hãy thu thập từ một cơ chế có thể khôi phục hoặc quét file sau khi writer hoàn tất. Không dựa vào counter trong memory vì restart làm mất state và retry có thể làm counter tăng nhiều lần.

## 19. Restart khi số lượng file đã tạo thay đổi

Số file phụ thuộc tổng item, item limit và item nào thực sự tới writer. Nếu input hoặc logic filter thay đổi, cùng checkpoint có thể tạo ra cấu trúc output khác.

Ví dụ:

- Lần chạy đầu có 12.000 item hợp lệ.
- Sau đó nguồn thay đổi khiến còn 11.500 item.
- Job restart bằng file mới nhưng dùng checkpoint cũ.

Reader có thể tiếp tục từ vị trí cũ trong khi các file output trước đó phản ánh dữ liệu từ nguồn khác. Kết quả có thể thiếu hoặc trộn dữ liệu.

Để tránh:

- Giữ input bất biến theo batch ID.
- Kiểm tra checksum hoặc source version trước khi restart.
- Giữ cùng processor/filter logic trong một JobInstance.
- Không thay đổi itemCountLimitPerResource giữa chừng.
- Nếu nguồn hoặc logic thay đổi, tạo JobInstance mới và xử lý lại theo quy trình đối soát.

Restart là tiếp tục một execution đã có checkpoint, không phải chạy lại cùng tên Job với dữ liệu bất kỳ.

## 20. MultiResourceItemWriter trong partitioning

Khi partitioning, nhiều worker StepExecution có thể chạy đồng thời. Nếu mỗi worker dùng cùng base Resource và cùng suffix algorithm, các worker có thể ghi vào cùng một tập tên file.

Mỗi worker nên có output namespace riêng:

~~~text
output/
  partition-000/
    customers-0001.csv
    customers-0002.csv
  partition-001/
    customers-0001.csv
    customers-0002.csv
  partition-002/
    customers-0001.csv
~~~

Có thể tạo output directory từ StepExecutionContext:

~~~java
@Bean
@StepScope
MultiResourceItemWriter<Customer> partitionCustomerWriter(
        @Value("#{stepExecutionContext['partitionName']}") String partitionName,
        @Value("#{jobParameters['output.dir']}") String outputDir,
        FlatFileItemWriter<Customer> delegate) {

    Resource baseResource = new FileSystemResource(
            Path.of(outputDir, partitionName, "customers").toFile());

    return new MultiResourceItemWriterBuilder<Customer>()
            .name("partitionCustomerWriter")
            .resource(baseResource)
            .resourceSuffixCreator(index ->
                    String.format("-%04d.csv", index))
            .itemCountLimitPerResource(5_000)
            .delegate(delegate)
            .saveState(true)
            .build();
}
~~~

Tên partition phải ổn định khi restart cùng JobInstance. Không dùng thread name làm partition identifier vì thread pool có thể phân công worker khác nhau giữa các lần chạy.

Mỗi worker có StepExecutionContext riêng, nhưng delegate writer và writer bao ngoài vẫn phải được tạo/cấu hình theo scope phù hợp. Không chia sẻ một instance stateful của MultiResourceItemWriter giữa các partition đồng thời.

Sau khi tất cả worker hoàn tất, manager Step hoặc bước tiếp theo có thể tổng hợp manifest từ output directory của từng partition.

## 21. MultiResourceItemWriter và concurrency trong một Step

Không nên mặc định một MultiResourceItemWriter stateful có thể được nhiều thread gọi đồng thời. Nó quản lý resource index, item count và delegate resource hiện tại. Nếu nhiều thread cùng ghi, các thao tác kiểm tra ngưỡng, chuyển resource và cập nhật count có thể race.

Các rủi ro:

- Hai thread cùng quyết định tạo resource mới.
- Item được ghi vào resource không mong đợi.
- Count bị tăng sai hoặc vượt ngưỡng ngoài dự kiến.
- Delegate bị đổi Resource khi thread khác đang ghi.
- Checkpoint phản ánh sai thứ tự ghi/commit.

Nếu cần song song hóa output, ưu tiên partitioning với writer riêng cho mỗi worker, hoặc một writer chuyên xử lý concurrent output có hợp đồng rõ ràng. Một khóa synchronized quanh MultiResourceItemWriter có thể tuần tự hóa toàn bộ ghi và làm mất lợi ích concurrency.

## 22. Skip, retry và lỗi khi ghi file

Writer có thể gặp lỗi:

- Không tạo được thư mục output.
- Không có quyền ghi.
- Hết dung lượng đĩa.
- File bị khóa hoặc bị xóa khi đang chạy.
- Lỗi I/O khi flush/close.
- Delegate không thể khôi phục checkpoint.

Các lỗi hạ tầng này thường không phù hợp để skip item. Nếu disk full hoặc file không ghi được, bỏ qua item sẽ làm mất dữ liệu. Retry có giới hạn chỉ phù hợp với lỗi tạm thời mà thao tác có thể thực hiện lại an toàn.

Với lỗi do một item không thể biểu diễn trong output, có thể skip theo exception cụ thể nếu nghiệp vụ cho phép. Tuy nhiên, cần ghi nhận item bị loại vào audit/quarantine và phân biệt với lỗi I/O của toàn resource.

Nếu dùng retry, writer và delegate cần idempotent hoặc có transaction-aware checkpoint để lần gọi lại không nhân đôi dòng đã commit. Không tự retry ghi file bằng cách gọi lại delegate mà bỏ qua state/transaction của Spring Batch.

## 23. Kiểm tra output sau restart

Sau khi Job hoàn tất, nên xác nhận:

- Danh sách Resource được tạo đúng pattern.
- Không có file trùng tên hoặc file rỗng ngoài dự kiến.
- Mỗi file có header/footer đúng yêu cầu.
- Tổng record count bằng số item hợp lệ dự kiến.
- Không có duplicate business key ngoài chính sách.
- File được đóng và có thể đọc lại.
- Manifest chỉ liệt kê file hoàn tất.
- Checksum hoặc file size khớp metadata nếu được lưu.

Không chỉ kiểm tra trạng thái Job COMPLETED. Job có thể hoàn tất nhưng tên file hoặc phân phối record không đúng nếu suffix hoặc item limit được cấu hình sai.

## 24. Ví dụ kiểm thử restart với nhiều file

Một integration test nên chạy Job hai lần trên cùng JobRepository và cùng identifying parameters. Lần đầu tạo một số chunk rồi thất bại có chủ đích; lần hai restart cùng JobInstance và xác nhận output.

Luồng test:

~~~text
Arrange:
  input có 25 item
  item limit mỗi file = 10
  chunk size = 5
  writer saveState = true
  delegate saveState = true

First launch:
  commit một số chunk
  tạo lỗi có chủ đích
  Job FAILED

Restart:
  dùng cùng identifying JobParameters
  khôi phục writer state
  tiếp tục ghi
  Job COMPLETED

Assert:
  tất cả 25 item có mặt đúng một lần
  resource names ổn định
  không mất phần đã commit
  không có tail chưa commit bị giữ lại
~~~

Ví dụ test khung:

~~~java
@SpringBatchTest
@SpringJUnitConfig(MultiResourceExportTestConfiguration.class)
class MultiResourceWriterRestartTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void resumesCurrentOutputResourceAfterFailure() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "CUSTOMER-TEST-01", true)
                .addString("input.file", "src/test/resources/customers.json", true)
                .addString("output.dir", "target/test-output/CUSTOMER-TEST-01", true)
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.FAILED, first.getStatus());

        JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

        // Đọc tất cả output files và kiểm tra business keys không thiếu/trùng.
        assertEquals(expectedCustomerIds, readAllCustomerIds(outputDirectory));
    }
}
~~~

Test này cần một cơ chế failure injection chỉ làm lần chạy đầu thất bại tại điểm xác định. JobRepository phải giữ metadata giữa hai lần launch và output directory không được cleanup trước restart. Không dùng test repository hoặc thư mục output mới cho lần thứ hai nếu muốn kiểm tra restart thật.

## 25. Kiểm thử tên file và ranh giới resource

Ngoài restart, cần kiểm tra suffix creator và item limit:

1. Ít item hơn limit: số resource được tạo như mong đợi.
2. Item count bằng đúng limit: resource boundary đúng.
3. Item count vượt limit một item: resource tiếp theo được tạo.
4. Chunk cắt qua ranh giới limit: xác nhận phân phối item theo API phiên bản.
5. Resource suffix ổn định giữa hai lần khởi tạo writer.
6. Hai JobInstance có output directory khác nhau.
7. Partition khác nhau không tạo collision.
8. Resource không thể ghi: Step thất bại rõ ràng.
9. Restart khi đang ở resource đầu tiên.
10. Restart khi đã chuyển qua nhiều resource.

Nên đọc nội dung thực tế của mọi file trong test, không chỉ đếm số file. Kiểm tra header, record, thứ tự và business key để phát hiện việc ghi trùng hoặc bỏ sót.

## 26. Các lỗi thường gặp

**Chỉ bật saveState cho MultiResourceItemWriter:** delegate không lưu checkpoint vị trí ghi, nên restart có thể không tiếp tục đúng trong file hiện tại. Bật saveState cho cả writer bao ngoài và delegate.

**Không đặt tên writer ổn định:** key ExecutionContext có thể thay đổi và state cũ không được tìm thấy. Đặt name rõ ràng cho cả hai writer.

**Suffix phụ thuộc thời gian hoặc random:** restart có thể tạo tên file khác. Dùng suffix xác định theo index.

**Thay itemCountLimitPerResource:** resource index và current count đã lưu có thể không còn tương ứng. Giữ cùng cấu hình qua restart.

**Thay base output path:** writer có thể mở một tập file khác trong khi state thuộc tập cũ. Giữ output path cố định cho JobInstance.

**Xóa output directory trước restart:** các file đã commit bị mất hoặc delegate không thể khôi phục offset. Chỉ cleanup cho execution mới đã được xác định.

**Cho rằng chunk transaction tự rollback mọi file:** chỉ delegate có cơ chế transaction/restart phù hợp mới hỗ trợ semantics đó. Custom output ngoài database cần tự thiết kế phục hồi.

**Dùng chung writer stateful giữa các partition:** resource index và delegate có thể bị ghi đè. Tạo writer riêng theo worker và output namespace riêng.

**Coi item limit là byte limit:** record dài/ngắn khác nhau làm kích thước file thay đổi. Dùng cơ chế theo dõi byte nếu yêu cầu giới hạn dung lượng.

**Downstream đọc file khi Job còn chạy:** có thể lấy phải file chưa hoàn tất. Dùng staging, manifest hoặc marker hoàn tất.

**Không giữ input bất biến:** checkpoint cũ có thể tiếp tục trên nội dung khác. Lưu batch ID/checksum và xác minh nguồn khi restart.

**Không kiểm thử restart qua JobRepository thật:** unit test writer đơn lẻ không chứng minh việc khôi phục state giữa hai lần JobExecution.

## Kết luận

MultiResourceItemWriter cho phép Spring Batch ghi item ra nhiều Resource bằng cách xoay vòng theo itemCountLimitPerResource và giao việc ghi nội dung cho một ResourceAwareItemWriterItemStream delegate. Để restart đúng, bật saveState cho cả writer bao ngoài và delegate, đặt tên writer ổn định, giữ nguyên base output Resource, suffix creator, item limit, input và thứ tự xử lý trong cùng JobInstance. FlatFileItemWriter có thể lưu checkpoint vị trí file, nhưng custom delegate phải tự bảo đảm rollback/restart semantics. Với partitioning, mỗi worker cần output namespace và writer state riêng. Giữ file đã commit, không cleanup trước restart, kiểm thử failure/restart qua JobRepository bền vững và chỉ công bố manifest khi toàn bộ output hoàn tất để downstream không đọc nhầm file dở dang.
