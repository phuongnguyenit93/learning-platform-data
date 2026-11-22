# File mới xuất hiện khi job chạy

Trong Spring Batch, một Job thường đọc một tập file đầu vào được tìm thấy trong thư mục hoặc được truyền qua JobParameters. Một tình huống vận hành phổ biến là **file mới được đưa vào thư mục sau khi Job đã bắt đầu**.

Cần phân biệt thời điểm file xuất hiện:

- File đã được công bố trước khi reader tìm resource: có thể nằm trong tập file của lần chạy.
- File xuất hiện sau khi reader đã chụp danh sách resource: reader hiện tại thường không tự phát hiện file đó.
- File đang được producer ghi dở khi Job quét thư mục: Job có thể nhìn thấy một file chưa hoàn chỉnh nếu quy trình ingest không có cơ chế publish an toàn.

MultiResourceItemReader đọc một danh sách Resource đã được cung cấp. Nó không phải watcher theo dõi thư mục liên tục. Để xử lý file đến trong lúc Job chạy, cần thiết kế quy trình phát hiện, công bố, claim và lập manifest rõ ràng, đồng thời giữ tập input ổn định cho restart.

## 1. MultiResourceItemReader đọc nhiều file như thế nào?

MultiResourceItemReader là ItemReader đọc lần lượt nhiều Resource bằng một delegate reader. Delegate thường là FlatFileItemReader hoặc một reader triển khai ResourceAwareItemReaderItemStream.

Ví dụ thư mục có ba file:

~~~text
/inbox
    orders-001.csv
    orders-002.csv
    orders-003.csv
~~~

Luồng đọc:

~~~text
MultiResourceItemReader
       |
       +--> orders-001.csv
       |       |
       |       +--> Delegate reader đọc các record
       |
       +--> orders-002.csv
       |       |
       |       +--> Delegate reader đọc các record
       |
       +--> orders-003.csv
               |
               +--> Delegate reader đọc các record
~~~

Khi hết một resource, MultiResourceItemReader chuyển delegate sang resource tiếp theo. Mỗi record được trả về như một item của Step; chunk processing diễn ra như với reader thông thường.

Composite này giúp tái sử dụng cùng một delegate reader cho nhiều file có cùng format. Nó không tự quản lý lịch đến file mới, queue, file lock hay quy trình claim.

## 2. Danh sách Resource được chụp tại thời điểm nào?

Ứng dụng thường tìm file bằng ResourcePatternResolver, PathMatchingResourcePatternResolver hoặc tự tạo Resource array. Kết quả là một danh sách Resource được truyền vào MultiResourceItemReader.

Ví dụ:

~~~java
Resource[] resources =
        new PathMatchingResourcePatternResolver()
                .getResources("file:/data/batch/inbox/*.csv");
~~~

Lệnh getResources thực hiện việc tìm kiếm tại thời điểm được gọi. MultiResourceItemReader nhận danh sách đó để xử lý.

Nếu reader được tạo trong StepScope, việc resolve JobParameters và tìm resource thường xảy ra khi target bean được tạo trong lifecycle của Step. Các file đã được công bố trước lần scan có thể được đưa vào danh sách. File xuất hiện sau lần scan không tự động được thêm vào reader đang chạy.

Không có cơ chế mặc định liên tục gọi lại glob pattern sau mỗi chunk. Đổi nội dung thư mục không làm Resource[] mà reader đang giữ tự thay đổi.

## 3. Ví dụ: file đến trước và sau lúc scan

Giả sử Step bắt đầu lúc 09:00 và reader quét thư mục lúc 09:01:

~~~text
08:55  orders-A.csv được công bố
09:00  Job bắt đầu
09:01  Reader tìm *.csv
       Snapshot = [orders-A.csv]
09:05  orders-B.csv được công bố
09:10  Reader đọc xong orders-A.csv
09:11  Step kết thúc
~~~

Trong lần chạy này:

- orders-A.csv nằm trong snapshot nên được đọc.
- orders-B.csv xuất hiện sau snapshot nên không tự được thêm vào.
- Step có thể hoàn thành dù inbox hiện đã có orders-B.csv.

orders-B.csv cần được xử lý trong một lần scan/JobExecution tiếp theo hoặc trong một vòng polling được thiết kế riêng.

Nếu file xuất hiện đúng lúc hệ thống đang scan, không nên dựa vào timing để quyết định nó thuộc lần chạy nào. Quy trình ingest cần có một ranh giới công bố hoặc manifest xác định.

## 4. Cấu hình MultiResourceItemReader

Ví dụ một reader xử lý các file CSV:

~~~java
@Bean
@StepScope
public MultiResourceItemReader<Order> orderReader(
        @Value("#{jobParameters['inputDirectory']}")
        String inputDirectory) throws IOException {

    Path directory = Paths.get(inputDirectory);
    ResourcePatternResolver resolver =
            new PathMatchingResourcePatternResolver();

    Resource[] resources =
            resolver.getResources(
                    directory.toUri().toString() + "*.csv");

    FlatFileItemReader<Order> delegate =
            new FlatFileItemReaderBuilder<Order>()
                    .name("orderFileDelegate")
                    .delimited()
                    .names("id", "customerId", "amount")
                    .targetType(Order.class)
                    .linesToSkip(1)
                    .saveState(true)
                    .build();

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(resources)
            .delegate(delegate)
            .saveState(true)
            .strict(true)
            .build();
}
~~~

Ví dụ minh họa việc tìm resource khi tạo reader. Cấu hình thực tế cần bảo đảm delegate nhận resource theo contract ResourceAwareItemReaderItemStream; MultiResourceItemReader sẽ gán từng Resource cho delegate trước khi đọc file đó.

Các thuộc tính quan trọng:

- name: tên ổn định để lưu state trong ExecutionContext.
- resources: danh sách file được đọc trong lần StepExecution.
- delegate: reader thực hiện đọc từng resource.
- saveState: lưu tiến độ để hỗ trợ restart.
- strict: quy định behavior khi danh sách resource rỗng.
- comparator: quy định thứ tự resource nếu cần.

API builder có thể khác theo phiên bản Spring Batch. Dùng method tương ứng với dependency của dự án.

## 5. strict không có nghĩa là chờ file mới

Khi không tìm thấy file, strict mode quyết định reader có báo lỗi hay không.

Thông thường:

- strict=true: danh sách resource rỗng là lỗi cấu hình/input.
- strict=false: reader có thể kết thúc ngay mà không đọc item nào.

strict=false không làm reader đợi cho tới khi file xuất hiện. Nó cũng không bật polling hoặc theo dõi thư mục.

Nếu Job chạy lúc inbox rỗng và reader được tạo với danh sách rỗng, Step có thể hoàn thành với 0 item. File được công bố sau đó vẫn cần một lần discovery khác.

Nếu file là bắt buộc, strict=true cùng validation đầu vào giúp phát hiện sớm. Nếu không có file là trạng thái hợp lệ, strict=false có thể phù hợp nhưng cần ghi nhận rõ số resource và số item đã đọc để tránh nhầm một lần chạy rỗng với một lần xử lý thành công dữ liệu.

## 6. Thứ tự resource phải ổn định

MultiResourceItemReader cần một thứ tự resource nhất quán để lưu và khôi phục vị trí khi restart. Nếu thứ tự thay đổi giữa lần chạy đầu và lần restart, index hiện tại có thể trỏ sang file khác.

Ví dụ thứ tự theo tên từ điển:

~~~text
orders-1.csv
orders-10.csv
orders-2.csv
~~~

Đây không phải thứ tự số mà nhiều người mong đợi.

Có thể dùng tên zero-padded:

~~~text
orders-0001.csv
orders-0002.csv
orders-0010.csv
~~~

Hoặc cấu hình comparator rõ ràng:

~~~java
.comparator(Comparator.comparing(
        resource -> resource.getFilename()))
~~~

Nếu thứ tự nghiệp vụ phụ thuộc ngày, sequence hoặc partition number, hãy định nghĩa comparator theo đúng trường đó và bảo đảm nó deterministic.

Không dùng thứ tự trả về ngẫu nhiên từ filesystem hoặc một collection không có thứ tự. Comparator cần xử lý cả trường hợp filename null hoặc trùng tên nếu resource có thể đến từ nhiều thư mục.

## 7. Vì sao file mới có thể làm hỏng restart?

Giả sử lần đầu reader nhận:

~~~text
[orders-A.csv, orders-C.csv, orders-D.csv]
~~~

Reader đã xử lý A và C, checkpoint đang ở D. Job thất bại trước khi D hoàn tất.

Trước khi restart, một file mới B được thêm vào và danh sách mới trở thành:

~~~text
[orders-A.csv, orders-B.csv, orders-C.csv, orders-D.csv]
~~~

Nếu reader khôi phục bằng resource index nhưng danh sách đã thay đổi, index cũ có thể trỏ tới resource khác. Kết quả có thể là đọc lặp, bỏ sót hoặc tiếp tục sai file tùy checkpoint và implementation.

Restart phải dùng cùng tập resource và cùng thứ tự như lần chạy ban đầu. Không quét lại inbox rồi tùy ý thêm file mới vào giữa một JobInstance đang restart.

## 8. Snapshot manifest cho mỗi JobInstance

Một cách đáng tin cậy là tạo manifest bất biến mô tả chính xác các file thuộc một lần chạy.

Ví dụ manifest:

~~~json
{
  "batchId": "orders-20261115-0900",
  "files": [
    {
      "name": "orders-A.csv",
      "size": 1048576,
      "checksum": "sha256:..."
    },
    {
      "name": "orders-C.csv",
      "size": 2097152,
      "checksum": "sha256:..."
    }
  ]
}
~~~

Quy trình:

1. Discovery tìm các file đã sẵn sàng.
2. Claim file để một Job sở hữu.
3. Tạo manifest với thứ tự cố định.
4. Lưu manifest ID/path và checksum làm metadata của Job.
5. Reader chỉ xử lý các resource trong manifest.
6. Restart đọc lại chính manifest đó.

File mới xuất hiện sau khi manifest được chốt sẽ thuộc batch tiếp theo. Cách này tạo ranh giới rõ ràng giữa các lần chạy và tránh thay đổi resource list giữa restart.

Manifest nên được lưu ở nơi bền vững, có version hoặc checksum. Không chỉ lưu một danh sách tên file trong biến Java tạm thời vì process restart sẽ mất trạng thái đó.

## 9. Chốt manifest trước khi xử lý

Có thể dùng một Step chuẩn bị để discovery và tạo manifest, sau đó một Step xử lý đọc manifest.

~~~text
Job
 |
 v
Discovery / Claim Step
 |
 +--> tìm file READY
 +--> claim file
 +--> tạo manifest bất biến
 +--> lưu manifest ID
 |
 v
Process Files Step
 |
 +--> đọc manifest
 +--> tạo Resource[] theo đúng thứ tự
 +--> MultiResourceItemReader
 |
 v
Finalize / Archive Step
~~~

Khi Job restart:

- Nếu Discovery Step đã hoàn thành, không tạo một manifest khác cho cùng lần chạy.
- Process Files Step dùng lại manifest đã lưu.
- Chỉ file thuộc manifest mới được đọc tiếp.
- File đến muộn được giữ cho batch kế tiếp.

Nếu Discovery Step thất bại trước khi manifest được commit, cần thiết kế claim/manifest operation có thể retry mà không mất hoặc claim trùng file. Có thể dùng transaction database để lưu manifest và file claims.

## 10. Công bố file an toàn từ producer

Một rủi ro lớn là producer tạo file trực tiếp với đuôi .csv trong inbox. Job có thể scan khi producer mới ghi được một phần nội dung.

Không nên coi sự tồn tại của tên file là bằng chứng file đã hoàn chỉnh.

Một pattern phổ biến:

~~~text
Producer
   |
   v
orders-001.csv.part
   |
   | ghi xong, flush và close
   v
orders-001.csv.tmp
   |
   | atomic rename nếu filesystem hỗ trợ
   v
orders-001.csv
   |
   v
Batch discovery quét *.csv
~~~

Consumer chỉ tìm file có đuôi cuối cùng .csv. Producer ghi file tạm ngoài pattern được scan, sau khi hoàn tất mới đổi tên thành tên sẵn sàng.

Atomic rename thường chỉ có thể bảo đảm trong cùng filesystem và phụ thuộc filesystem/provider. Nếu move qua volume khác hoặc object storage, thao tác có thể thành copy/delete và không atomic.

Không dùng file extension .csv cho file đang ghi dở nếu reader cũng quét *.csv.

## 11. Ready marker và manifest marker

Một lựa chọn khác là producer ghi dữ liệu trước rồi tạo marker:

~~~text
orders-001.csv
orders-001.csv.ready
~~~

Consumer chỉ xử lý file khi marker tồn tại.

Marker nên được tạo sau khi file đã được đóng và kiểm tra hoàn tất. Nếu marker được tạo quá sớm, nó không giải quyết được race condition.

Với nhiều file thuộc cùng một batch, có thể dùng manifest hoặc một marker ở cấp batch:

~~~text
batch-20261115/
    orders-A.csv
    orders-B.csv
    manifest.json
    _READY
~~~

Consumer chỉ nhận batch khi _READY được công bố. Manifest xác định tập file, thứ tự và metadata. Đây là cách hữu ích khi các file phải được xử lý như một nhóm logic.

Trên object storage, ready marker/manifest thường đáng tin cậy hơn giả định rename directory là atomic.

## 12. Kiểm tra file ổn định trước khi claim

Nếu producer không hỗ trợ atomic publish hoặc ready marker, một biện pháp tạm thời là kiểm tra file không còn thay đổi trong một khoảng thời gian.

Ví dụ kiểm tra:

- Kích thước file tại hai thời điểm cách nhau một khoảng.
- Last modified timestamp không thay đổi.
- Có thể mở file để đọc.
- Header hoặc trailer hợp lệ.
- Checksum được tính và khớp với metadata producer cung cấp.

Cách này chỉ là heuristic. File có thể tạm dừng ghi rồi tiếp tục sau khoảng kiểm tra; timestamp có độ phân giải thấp; file handle có thể vẫn đang mở.

Ưu tiên hợp đồng publish rõ ràng. Nếu buộc phải dùng stability window, hãy chọn khoảng thời gian theo behavior producer và vẫn validate nội dung trước khi xử lý.

## 13. Claim file để tránh hai Job xử lý cùng lúc

Nếu hai Job cùng quét một inbox, cả hai có thể tìm thấy cùng một file trước khi file được di chuyển. Cả hai sau đó đều có thể xử lý duplicate.

Cần một cơ chế claim có tính nguyên tử hoặc được điều phối:

- Rename file từ inbox sang processing trong cùng filesystem.
- Tạo claim record có unique key trong database.
- Dùng lease với owner ID và expiry.
- Dùng queue/manifest service làm nguồn phân phối.
- Dùng lock phù hợp với storage nếu semantics được hỗ trợ.

Ví dụ thư mục:

~~~text
inbox/
    orders-A.csv

processing/
    job-123/
        orders-A.csv
~~~

Job claim file trước khi tạo manifest. Chỉ Job sở hữu file trong processing/job-123 mới được đọc file đó.

Rename chỉ là atomic trong phạm vi filesystem hỗ trợ và thường cần source/destination cùng filesystem. Trên network share hoặc object storage, hãy xác minh semantics thực tế.

## 14. Không di chuyển file sau khi reader đã mở nếu restart cần path cũ

Reader có thể đang giữ stream mở tới file. Trên một số hệ điều hành, file vẫn đọc được sau khi rename; trên hệ điều hành khác, thao tác move có thể bị chặn bởi file handle hoặc share mode.

Dù stream đang mở còn đọc được, restart thường cần mở lại resource bằng path đã lưu. Nếu file đã được chuyển đi, path cũ có thể không tồn tại.

Vì vậy, nên claim file trước khi Step xử lý bắt đầu và giữ path ổn định trong suốt thời gian Job có thể restart. Chỉ chuyển sang archive sau khi xử lý thành công và trạng thái Job được ghi nhận phù hợp.

Nếu cần archive ngay sau từng file, lưu location mới và trạng thái claim một cách bền vững, rồi thiết kế reader/restart dựa trên manifest thay vì dựa vào đường dẫn inbox ban đầu.

## 15. Discovery theo lịch thay vì một Job chạy mãi

Với batch file thông thường, mô hình dễ vận hành là mỗi lần chạy xử lý một snapshot:

~~~text
09:00  Scheduler launch Job A
09:01  Job A claim files A, B
09:10  Job A hoàn tất
09:15  File C đến
10:00  Scheduler launch Job B
10:01  Job B claim file C
~~~

Mỗi JobInstance có manifest riêng. File đến muộn được xử lý trong lần chạy tiếp theo.

Ưu điểm:

- Job có điểm bắt đầu và kết thúc rõ ràng.
- Restart chỉ cần khôi phục snapshot của lần chạy.
- Dễ đo số file và record theo batch.
- Dễ đối soát và archive.
- Không giữ một Step/transaction mở trong thời gian dài chỉ để chờ file.

Tần suất scheduler phụ thuộc SLA: mỗi phút, mỗi 15 phút, mỗi giờ hoặc theo lịch nghiệp vụ. Không nên tạo một JobInstance mới liên tục với cùng identifying parameters nếu muốn xử lý từng batch; cần batch ID hoặc window ID ổn định.

## 16. Polling trong khi Job đang chạy

Nếu yêu cầu nghiệp vụ là một Job phải tiếp tục nhận file mới trong một khoảng thời gian, cần một vòng polling được thiết kế rõ ràng.

Ví dụ:

~~~text
Start Job
   |
   v
Discover and claim files
   |
   v
Process current manifest
   |
   v
Wait / backoff
   |
   v
Discover new files
   |
   +--> Có file mới? -- Yes --> Process next manifest
   |
   +--> Không có và chưa hết window? -- Yes --> Wait
   |
   +--> Hết window? -- Yes --> Finalize
~~~

Mỗi vòng nên tạo một snapshot/manifest riêng. Không thay đổi Resource[] của một MultiResourceItemReader đang mở.

Các giới hạn cần có:

- Thời gian tối đa Job được chạy.
- Khoảng polling/backoff.
- Số lần polling tối đa.
- Điều kiện dừng khi không có file.
- Cách xử lý shutdown hoặc restart giữa các vòng.
- Giới hạn số file và tổng dung lượng mỗi vòng.

Không tạo vòng while vô hạn bên trong một chunk transaction. Việc chờ file không nên giữ database transaction mở.

## 17. WatchService và file-system events

Java NIO WatchService có thể nhận sự kiện tạo, sửa hoặc xóa file trên một thư mục:

~~~java
WatchService watchService =
        FileSystems.getDefault().newWatchService();

Path inbox = Paths.get("/data/batch/inbox");

inbox.register(
        watchService,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY);
~~~

WatchService có thể hữu ích để giảm độ trễ phát hiện file. Tuy nhiên, filesystem event không nên là nguồn sự thật duy nhất:

- Event có thể bị overflow hoặc mất.
- Một file có thể phát sinh nhiều event.
- Event có thể tới khi producer chưa ghi xong.
- Network filesystem có thể hỗ trợ event khác nhau.
- Process restart có thể bỏ lỡ event đã xảy ra khi service offline.

Một thiết kế bền vững dùng event như tín hiệu đánh thức discovery, sau đó quét lại inbox/manifest để xác định file thực sự READY. Khi service khởi động lại, nó cũng phải rescan để khôi phục file chưa claim.

## 18. Không cập nhật Resource[] của reader đang chạy

Một ý tưởng dễ gặp là khi file mới xuất hiện, gọi setResources() trên MultiResourceItemReader đang hoạt động để thêm file vào cuối danh sách.

Cách này không phải workflow discovery/restart an toàn mặc định:

- Reader đã lưu resource index và delegate state.
- Thay đổi danh sách có thể làm index cũ không còn ý nghĩa.
- Delegate có thể đang giữ stream cho resource hiện tại.
- Việc update không được phối hợp tự động với ExecutionContext.
- Hai thread có thể nhìn thấy danh sách khác nhau.
- Restart không biết chính xác resource list nào đã được xử lý.

Hãy tạo reader mới cho một snapshot/manifest mới trong một StepExecution hoặc vòng xử lý riêng. Nếu cần một reader động, phải tự thiết kế state machine, persistence của manifest và recovery; không chỉ sửa Resource[].

## 19. Dùng Tasklet để discovery và claim

Một Tasklet có thể thực hiện discovery, xác thực file và tạo manifest trước Step xử lý.

Ví dụ khái niệm:

~~~java
@Bean
public Step discoverFilesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FileDiscoveryTasklet tasklet) {

    return new StepBuilder("discoverFilesStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Tasklet có thể:

1. Tìm file có ready marker.
2. Kiểm tra tên, kích thước, checksum và schema.
3. Claim file.
4. Lưu manifest ID vào JobExecutionContext hoặc database.
5. Trả về FINISHED.

Step xử lý sau đó đọc manifest và tạo MultiResourceItemReader từ danh sách đã cố định.

Nếu file claim bằng filesystem rename và metadata lưu trong database, hai thao tác đó không tự động cùng transaction. Cần có recovery protocol cho trường hợp rename thành công nhưng transaction database rollback, hoặc database claim thành công nhưng move thất bại.

Một claim table với unique constraint và lease có thể dễ đối soát hơn nếu môi trường có nhiều node.

## 20. Lưu manifest trong ExecutionContext

ExecutionContext phù hợp để lưu metadata nhỏ, cần phục hồi cùng JobExecution/StepExecution. Không nên nhét nội dung file hoặc toàn bộ dữ liệu record vào context.

Có thể lưu:

- Manifest ID.
- Manifest path hoặc URI.
- Manifest version/checksum.
- Số resource.
- Batch/window ID.
- Quy tắc sort/version.

Ví dụ:

~~~java
jobExecution.getExecutionContext()
        .putString("inputManifestId", manifestId);
~~~

Trong thực tế, việc cập nhật JobExecutionContext cần đi qua lifecycle/DAO và transaction phù hợp; không tự sửa object ngoài lifecycle rồi giả định nó đã được persist.

Nếu manifest có hàng chục nghìn đường dẫn, có thể lưu manifest ở file/database/object storage và chỉ giữ ID/URI/checksum trong ExecutionContext.

## 21. Restart sau khi một số file đã được xử lý

MultiResourceItemReader có state về resource hiện tại và state của delegate. Khi restart, nó cần cùng resource list và thứ tự để tiếp tục chính xác.

Ví dụ:

~~~text
Manifest M1:
  A.csv
  B.csv
  C.csv

Lần chạy đầu:
  A.csv hoàn tất
  B.csv đọc một phần
  Job thất bại

Restart:
  Dùng lại M1
  Khôi phục reader state tại B.csv
  Tiếp tục B.csv
  Sau đó đọc C.csv
~~~

D không được tự thêm vào M1 dù D xuất hiện trong inbox trước restart. D thuộc manifest tiếp theo.

Nếu file A đã archive sau khi hoàn tất nhưng restart state vẫn cần tham chiếu A hoặc reader phải replay từ đầu, cần xác minh semantics của reader và checkpoint. An toàn hơn là giữ các resource thuộc manifest ở vị trí ổn định cho tới khi Job hoàn tất, hoặc dùng trạng thái per-file để restart từng file độc lập.

## 22. Một file mới không được làm thay đổi JobInstance identity

JobParameters identifying xác định JobInstance. Nếu một JobInstance đã thất bại và cần restart, không thêm file mới vào manifest rồi dùng cùng JobInstance như thể đó là cùng một lần xử lý.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "orders-20261115-0900", true)
        .addString("manifestId", "manifest-001", true)
        .toJobParameters();
~~~

manifestId mô tả tập input của lần chạy. Khi restart, dùng cùng batchId và manifestId. Batch mới cần một batchId/manifestId mới để tạo JobInstance phù hợp.

Nếu manifest ID chỉ là non-identifying nhưng nó thay đổi query/resource set, restart có thể tiếp tục trên dữ liệu khác. Hãy cân nhắc identifying status theo ý nghĩa dữ liệu.

## 23. Idempotency khi file có thể được phát hiện lại

Discovery có thể tìm lại file nếu Job dừng sau khi đọc nhưng trước khi archive/mark complete. Do đó, cần chống xử lý trùng.

Có thể dùng:

- Unique constraint theo source file ID và record business key.
- Bảng file-processing với trạng thái CLAIMED/PROCESSING/COMPLETED/FAILED.
- Checksum để nhận diện cùng nội dung được gửi lại.
- Idempotent upsert cho output.
- Archive và manifest status được cập nhật có kiểm soát.
- Event ID duy nhất nếu phát sinh message.

Không dùng tên file làm định danh duy nhất nếu producer có thể tái sử dụng tên. Kết hợp producer ID, file sequence, checksum hoặc batch ID theo contract.

Nếu file được gửi lại với cùng tên nhưng nội dung khác, hệ thống phải có quy tắc rõ ràng: từ chối, version hóa hay coi là batch mới.

## 24. Xử lý file lỗi hoặc file chưa hoàn chỉnh

Một file có thể xuất hiện nhưng không hợp lệ:

- File rỗng.
- Header không đúng.
- Thiếu trailer hoặc record count.
- Encoding sai.
- CSV/XML/JSON bị truncate.
- Checksum không khớp.
- Schema version không được hỗ trợ.

Discovery Step nên kiểm tra metadata và trạng thái READY. Validation nội dung có thể diễn ra trong processing Step, nhưng cần phân biệt lỗi file toàn cục với lỗi record riêng lẻ.

Khi file lỗi:

- Ghi trạng thái FAILED cùng nguyên nhân.
- Di chuyển/copy sang khu vực quarantine nếu an toàn.
- Giữ manifest và checksum để audit.
- Không đánh dấu COMPLETED chỉ vì reader đã mở được file.
- Có quy trình sửa và replay rõ ràng.

Nếu file đang được producer ghi, không quarantine chỉ vì một lần scan sớm. Dùng ready marker hoặc publish protocol để phân biệt file đang ghi với file thực sự lỗi.

## 25. Xử lý nhiều Job cùng discovery

Trong cluster có nhiều scheduler hoặc nhiều application instance, hai Job có thể scan cùng inbox gần như đồng thời.

Một quy trình chỉ gồm:

~~~text
if file exists:
    process file
~~~

không đủ an toàn vì hai process có thể cùng thấy file trước khi một process thay đổi trạng thái.

Cần atomic claim:

- Database: INSERT claim với unique key; chỉ một process thành công.
- Filesystem: rename file vào processing path duy nhất nếu operation atomic trong filesystem.
- Object storage: conditional write/lease theo API storage.
- Queue: consumer group hoặc visibility timeout.

Claim cần có owner ID và thời điểm claim. Nếu worker chết, lease có thể hết hạn và file được recovery. Nhưng trước khi claim lại, phải kiểm tra JobExecution cũ có còn chạy hay không để tránh hai worker cùng ghi.

## 26. File lớn và thời gian xử lý dài

Nếu một file rất lớn đang được đọc, file mới xuất hiện không nên làm thay đổi reader hiện tại. Hãy để Step hoàn tất snapshot đang xử lý rồi xử lý file mới ở vòng sau.

Nếu cần giảm độ trễ, có thể chia file lớn thành shard ở phía producer hoặc một ingest step riêng:

~~~text
Large source file
       |
       v
Streaming split at record boundaries
       |
       +--> shard-001.csv
       +--> shard-002.csv
       +--> shard-003.csv
       |
       v
Manifest
       |
       v
Parallel partition workers
~~~

Không cắt file theo byte hoặc số dòng tùy tiện nếu record có thể multiline hoặc encoding multibyte. Chia tại boundary của record theo đúng format.

Một shard nên đủ lớn để giảm overhead nhưng đủ nhỏ để retry/restart không phải xử lý lại quá nhiều dữ liệu.

## 27. Object storage và cloud file arrival

Với S3-compatible storage, Azure Blob hoặc GCS, khái niệm directory có thể chỉ là prefix. Rename thường không giống atomic filesystem rename; nhiều dịch vụ thực hiện copy rồi delete.

Một số pattern:

- Upload object dưới key tạm, sau đó publish manifest/ready marker.
- Dùng immutable object key chứa version hoặc batch ID.
- Ghi checksum và content length vào manifest.
- Chỉ discovery manifest đã hoàn chỉnh.
- Dùng conditional operation/lease để claim nếu storage hỗ trợ.
- Không giả định list operation và event notification luôn có semantics giống local filesystem.

Event notification có thể tới trễ hoặc trùng. Hãy dùng event để kích hoạt discovery, rồi xác minh object metadata và manifest trước khi xử lý.

## 28. Monitoring file arrival và processing lag

Với pipeline nhận file liên tục, cần theo dõi cả discovery lẫn processing.

Một số metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| discovered_file_count | Số file tìm thấy trong một lần scan |
| ready_file_count | Số file đã đáp ứng điều kiện READY |
| claimed_file_count | Số file đã được Job sở hữu |
| processed_file_count | Số file xử lý thành công |
| failed_file_count | Số file bị quarantine/FAILED |
| pending_file_count | Số file đang chờ xử lý |
| oldest_pending_age | Tuổi của file chờ lâu nhất |
| discovery_lag | Thời gian từ publish tới discovery |
| processing_duration | Thời gian xử lý từng file/batch |
| input_bytes | Tổng dung lượng input |
| record_count | Số record đã đọc/ghi |

Log nên có file ID, manifest ID, JobExecution ID và StepExecution ID. Không log toàn bộ nội dung file nếu chứa dữ liệu nhạy cảm.

Alert khi file pending quá lâu, claim bị treo, file FAILED tăng đột biến hoặc Job hoàn tất với 0 file ngoài dự kiến.

## 29. Kiểm thử file xuất hiện trong lúc Job chạy

Một integration test có thể điều khiển thời điểm tạo file:

1. Tạo inbox với A.csv.
2. Launch Job; discovery tạo manifest chỉ gồm A.csv.
3. Dừng hoặc chặn writer ở một điểm đồng bộ test.
4. Tạo B.csv và publish READY.
5. Tiếp tục Job.
6. Xác nhận lần chạy hiện tại chỉ xử lý A.csv.
7. Launch Job mới.
8. Xác nhận B.csv được xử lý trong manifest mới.

Test này chứng minh snapshot semantics. Không dùng sleep dài tùy tiện; dùng latch, barrier hoặc test hook để điều khiển thời điểm.

Cũng cần test trường hợp producer tạo file .part rồi rename sau khi scan. File .part không được reader nhận nếu pattern chỉ lấy *.csv.

## 30. Kiểm thử restart với manifest cố định

Kịch bản:

~~~text
Initial manifest:
  A.csv
  C.csv

First execution:
  A.csv hoàn tất
  C.csv đọc một phần
  Step fail

Before restart:
  B.csv xuất hiện trong inbox

Restart:
  Vẫn dùng manifest [A.csv, C.csv]
  Tiếp tục C.csv
  Không tự thêm B.csv

Next Job:
  Discovery claim B.csv
  Manifest mới chứa B.csv
~~~

Kiểm tra:

- Manifest ID không đổi khi restart.
- Resource list và comparator không đổi.
- File A/C giữ nguyên checksum.
- Reader state khôi phục đúng.
- B không bị xử lý trong JobInstance cũ.
- B được xử lý trong JobInstance mới.
- Không có duplicate record do retry/restart.

Nếu restart phải replay một file từ đầu, output cần idempotent hoặc có trạng thái per-file để tránh ghi trùng.

## 31. Những lỗi thường gặp

### Nghĩ MultiResourceItemReader tự theo dõi thư mục

Reader dùng Resource[] đã được cung cấp. File mới sau snapshot cần discovery mới.

### Đặt strict=false và nghĩ reader sẽ đợi file

strict=false chỉ cho phép danh sách rỗng theo behavior của reader; nó không polling.

### Scan khi producer còn đang ghi

Job có thể đọc file chưa hoàn chỉnh. Dùng temp extension, atomic publish hoặc ready marker.

### Thêm file mới vào Resource[] đang chạy

Có thể làm hỏng state và restart. Tạo snapshot/manifest mới cho vòng xử lý mới.

### Rescan inbox khi restart

Tập resource hoặc thứ tự có thể thay đổi. Dùng manifest bất biến của JobInstance.

### Không đặt comparator ổn định

Filesystem order hoặc lexical order có thể khác mong đợi. Chọn comparator deterministic và test.

### Hai Job cùng xử lý một file

Discovery không phải claim. Dùng unique database claim, atomic move hoặc lease.

### Archive file quá sớm

Restart có thể không mở lại được resource. Giữ path ổn định cho tới khi lifecycle Job hoàn tất hoặc lưu trạng thái per-file rõ ràng.

### Dùng WatchService làm nguồn sự thật duy nhất

Event có thể mất hoặc trùng. Rescan inbox/manifest sau event và khi service khởi động.

### Dùng polling vô hạn trong transaction

Transaction và resource có thể bị giữ quá lâu. Dùng vòng hữu hạn, mỗi vòng có snapshot riêng và backoff.

### Chỉ dùng filename làm idempotency key

Producer có thể tái sử dụng tên. Dùng file ID, batch ID, checksum hoặc version theo hợp đồng.

### Không kiểm tra file READY

File tồn tại chưa chắc đã hoàn tất. Xác minh marker, manifest, size/checksum hoặc protocol publish.

## 32. Quy trình thiết kế file arrival

Khi một Job cần xử lý file có thể xuất hiện trong lúc chạy, hãy xác định:

1. Producer công bố file bằng atomic rename, ready marker hay manifest?
2. Reader scan thư mục ở thời điểm nào?
3. Tập Resource của JobInstance có được cố định không?
4. File đến sau snapshot sẽ thuộc batch tiếp theo hay một polling cycle mới?
5. Discovery có claim file để tránh hai Job xử lý trùng không?
6. Comparator có deterministic và ổn định qua restart không?
7. Manifest có lưu danh sách, thứ tự, checksum và version không?
8. Job restart có dùng lại đúng manifest cũ không?
9. Input path có ổn định trong suốt thời gian restart không?
10. File chỉ được archive sau khi trạng thái xử lý đã bền vững chưa?
11. WatchService/event notification có cơ chế rescan dự phòng không?
12. Polling có giới hạn thời gian và không giữ transaction khi chờ không?
13. Có idempotency cho trường hợp file được phát hiện hoặc gửi lại không?
14. Monitoring có phát hiện file pending lâu, claim treo và file lỗi không?
15. Integration test có tạo file mới giữa lúc Job chạy và xác nhận nó được xử lý ở lần chạy phù hợp không?

MultiResourceItemReader xử lý tuần tự một danh sách Resource đã được chụp khi reader được cấu hình. File mới xuất hiện sau thời điểm đó không tự được thêm vào Step đang chạy. Muốn xử lý file đến liên tục, hãy dùng quy trình publish/READY, discovery và claim rõ ràng; chốt một manifest bất biến cho mỗi JobInstance; giữ thứ tự và resource ổn định qua restart; rồi xử lý file đến muộn trong Job hoặc polling cycle tiếp theo. Cách này tránh đọc file đang ghi dở, tránh hai Job claim cùng file và giữ checkpoint có ý nghĩa khi Job phải restart.
