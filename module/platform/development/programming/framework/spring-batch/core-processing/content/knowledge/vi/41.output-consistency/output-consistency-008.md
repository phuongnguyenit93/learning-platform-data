# Temporary output và commit marker trong Spring Batch

Một batch job có thể ghi kết quả ra file, bảng database hoặc một hệ thống downstream. Trong lúc job đang chạy, output thường mới chỉ chứa một phần dữ liệu. Nếu consumer đọc output quá sớm, nó có thể xử lý file chưa hoàn chỉnh, nhìn thấy bảng chỉ được ghi một phần hoặc phát hành báo cáo có số liệu thiếu.

Temporary output và commit marker phối hợp để ngăn việc công bố dữ liệu dở dang. Job ghi kết quả vào một vị trí staging riêng, hoàn tất và xác minh output, sau đó mới công bố. Commit marker là tín hiệu bền vững cho biết output của một batch đã hoàn chỉnh và consumer có thể sử dụng. Marker không thay thế transaction của database hay checkpoint của Spring Batch; nó biểu diễn trạng thái công bố ở cấp nghiệp vụ.

Thiết kế này hữu ích khi job chạy lâu, có khả năng restart, ghi file cho hệ thống khác hoặc cần bảo đảm consumer không đọc dữ liệu dở dang. Cần xác định temporary output được giữ thế nào khi restart, thời điểm marker được ghi và cách khôi phục nếu process dừng giữa bước publish và cập nhật marker.

## 1. Vì sao cần temporary output?

Giả sử job xuất một file gồm 500.000 order. Nếu writer ghi trực tiếp vào đường dẫn mà hệ thống downstream đang theo dõi, consumer có thể nhìn thấy file ngay khi file mới có vài nghìn dòng.

~~~text
Batch job
   |
   v
orders.csv
   |
   +--> Consumer phát hiện file
   |
   +--> Đọc khi writer vẫn đang ghi
   |
   v
Output thiếu dữ liệu hoặc CSV bị cắt giữa chừng
~~~

Đây là lỗi công bố dữ liệu quá sớm. File tồn tại không có nghĩa file đã hoàn chỉnh. Tương tự, bảng đích có thể đã chứa một phần hàng của batch trong khi step chưa hoàn tất.

Temporary output tạo một vùng riêng cho lần xử lý:

~~~text
Input
  |
  v
Spring Batch step
  |
  v
Temporary output
  |
  +--> ghi các chunk
  +--> flush và close
  +--> kiểm tra count/checksum/schema
  |
  v
Publish output
  |
  v
Commit marker
  |
  v
Consumer được phép đọc
~~~

Consumer chỉ đọc output đã được publish và có marker hợp lệ. Các file staging hoặc hàng staging chưa được công bố sẽ không được xem là dữ liệu hoàn tất.

## 2. Temporary output và commit marker là gì?

**Temporary output** là output đang được xây dựng. Nó có thể là file tạm trong thư mục staging, bảng staging có batch ID, object trong bucket với key riêng cho lần chạy hoặc thư mục riêng của một batch/partition.

**Commit marker** là một bản ghi hoặc artifact nhỏ cho biết output đã được hoàn thành và công bố. Marker có thể là:

- Một hàng trong bảng control của database.
- Một file sidecar như orders.csv.done.
- Một manifest chứa batch ID, đường dẫn, số record và checksum.
- Một trạng thái COMMITTED trong bảng quản lý batch.

Marker cần được tạo sau khi output cuối cùng đã sẵn sàng. Consumer dựa vào marker để quyết định output nào có thể đọc.

Đừng nhầm commit marker với checkpoint trong ExecutionContext. Checkpoint cho Spring Batch biết reader/writer nên tiếp tục từ đâu khi restart. Commit marker cho consumer biết một output nghiệp vụ đã hoàn tất và có thể sử dụng.

## 3. Phân biệt chunk commit, step completion và output publication

Ba trạng thái này có phạm vi khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Chunk commit | Một chunk đã hoàn tất transaction của step | 100 order được ghi thành công |
| Step completion | Step đã xử lý xong toàn bộ input theo flow của nó | Export step có status COMPLETED |
| Output publication | Artifact được công bố để consumer sử dụng | File được rename và marker được ghi |

Một chunk commit không có nghĩa toàn bộ file đã hoàn tất. Step COMPLETED cũng chưa tự động chứng minh file đã được đưa tới vị trí consumer theo dõi. Publication là một thao tác có thể cần step riêng.

JobExecution status là metadata điều khiển execution. Commit marker là contract giữa producer và consumer về output. Có thể dùng cả hai, nhưng không nên để consumer suy đoán rằng chỉ cần thấy file hoặc thấy step đang chạy là output đã sẵn sàng.

## 4. Đặt tên và định danh temporary output

Temporary output phải được gắn với một logical batch identity ổn định. Thông thường có thể dùng batchId hoặc identifying JobParameters của JobInstance.

Ví dụ:

~~~text
staging/
  orders/
    batch-2026-11-15-001/
      orders.csv.tmp
      manifest.tmp
~~~

Khi restart một JobInstance, Spring Batch tạo JobExecution mới nhưng vẫn tiếp tục cùng JobInstance. Vì vậy, nếu mục tiêu là tiếp tục output dở dang, đường dẫn staging nên được tạo từ logical batch ID ổn định, không phụ thuộc JobExecution ID của từng lần thử.

Nếu dùng JobExecution ID để đặt tên file, lần restart có thể ghi sang file mới trong khi checkpoint cũ tham chiếu file trước đó. Nếu muốn mỗi attempt có artifact riêng, phải có bước resume/copy hoặc tái tạo dữ liệu có chủ đích; không tự thay path giữa restart.

Một batch nghiệp vụ mới cần batch ID mới để không ghi đè output của batch đã công bố. Nếu chạy lại từ đầu cùng batch ID, cần một quy trình reset/replace rõ ràng và kiểm soát consumer.

## 5. Cấu trúc bảng quản lý output

Với database output hoặc file output được quản lý qua database, có thể tạo bảng control:

~~~sql
create table batch_output_control (
    batch_id varchar(100) primary key,
    output_type varchar(30) not null,
    state varchar(20) not null,
    temporary_location varchar(500),
    final_location varchar(500),
    expected_count bigint,
    actual_count bigint,
    checksum varchar(128),
    created_at timestamp not null,
    committed_at timestamp,
    error_message varchar(1000)
);
~~~

Một số trạng thái thường dùng:

| State | Ý nghĩa |
| --- | --- |
| PENDING | Batch output đã được đăng ký, chưa bắt đầu ghi |
| WRITING | Job đang tạo temporary output |
| READY | Output đã đóng và qua bước kiểm tra, chờ publish |
| COMMITTED | Output đã được publish và consumer có thể sử dụng |
| FAILED | Lần xử lý kết thúc lỗi, output chưa được công bố |
| ABANDONED | Batch bị hủy theo quyết định vận hành |

Không bắt buộc phải dùng đúng các tên trạng thái này. Điều quan trọng là chuyển trạng thái theo một state machine rõ ràng, có điều kiện và có thể phục hồi sau crash.

## 6. State transition của output

Một luồng thông thường:

~~~text
PENDING
   |
   v
WRITING
   |
   v
READY
   |
   v
COMMITTED
~~~

Nếu có lỗi trước publication:

~~~text
WRITING / READY
       |
       v
     FAILED
       |
       +--> restart cùng batch
       |
       +--> hoặc ABANDONED sau quyết định vận hành
~~~

Không chuyển sang COMMITTED khi chỉ mới tạo file tạm hoặc ghi xong một vài chunk. COMMITTED phải có nghĩa output cuối cùng đã sẵn sàng theo contract với consumer.

Các chuyển trạng thái nên có điều kiện từ state hiện tại, ví dụ chỉ cho phép WRITING chuyển sang READY. Có thể dùng optimistic version hoặc câu UPDATE có điều kiện để tránh hai execution cùng thay đổi marker.

## 7. Ghi file vào thư mục staging

Với file output, cấu hình FlatFileItemWriter trỏ tới đường dẫn tạm:

~~~java
@Bean
@StepScope
FlatFileItemWriter<OrderExportRow> temporaryOrderWriter(
        @Value("#{jobParameters['temporaryPath']}") String path) {

    return new FlatFileItemWriterBuilder<OrderExportRow>()
        .name("temporaryOrderWriter")
        .resource(new FileSystemResource(path))
        .headerCallback(writer ->
            writer.write("orderId,customerId,total"))
        .lineAggregator(row ->
            row.orderId() + "," +
            row.customerId() + "," +
            row.total()
        )
        .saveState(true)
        .build();
}
~~~

Ví dụ dùng path được truyền từ JobParameters để minh họa. Trong production, path nên được tạo từ batch ID đã được xác thực và một thư mục staging được cấu hình; không nhận đường dẫn tùy ý từ payload không tin cậy.

Reader/writer name và resource path cần ổn định khi restart cùng JobInstance. FlatFileItemWriter hỗ trợ lưu state để khôi phục vị trí ghi; việc restart phải dùng đúng resource và execution context của step trước đó.

Không xóa file tạm khi step thất bại nếu dự định restart từ checkpoint. Nếu writer mở lại một file đã bị xóa hoặc bị ghi đè, checkpoint có thể không còn khớp với nội dung file.

## 8. Temporary file cần được ẩn khỏi consumer

Consumer không nên quét tất cả file trong thư mục staging. Chỉ thư mục publish hoặc manifest COMMITTED mới là nguồn output hợp lệ.

~~~text
output/
  staging/
    batch-001/
      orders.csv.tmp
  published/
    batch-000/
      orders.csv
      orders.csv.done
~~~

Consumer chỉ theo dõi published và yêu cầu marker .done. Nếu consumer quét cả staging, temporary output mất tác dụng vì consumer vẫn có thể đọc file dở dang.

Đối với object storage, dùng prefix riêng cho staging và chỉ ghi manifest/commit object sau khi toàn bộ object đã được upload và xác minh. Không giả định rename trên object storage có semantics giống atomic rename của filesystem.

## 9. Đóng writer trước khi publish

Trước khi di chuyển file, phải bảo đảm writer đã kết thúc lifecycle:

- Step đã hoàn tất ghi.
- Writer đã flush và close.
- Không còn thread nào ghi vào file.
- File có thể được mở lại để kiểm tra.
- Số record và checksum đã được tính sau khi file ổn định.

Không rename file trong khi writer còn giữ handle mở. Trên một số hệ điều hành, thao tác này có thể thất bại; trên hệ thống khác, writer vẫn có thể tiếp tục ghi vào file đã được di chuyển, tạo ra behavior khó dự đoán.

Một finalization step chạy sau export step là nơi phù hợp để xác minh và publish. Nó giúp thứ tự flow rõ ràng và có thể retry/restart theo một đơn vị riêng.

## 10. Publish file bằng atomic rename

Nếu temporary file và final file nằm trên cùng filesystem, có thể dùng atomic move:

~~~java
public void publish(Path temporary, Path target) throws IOException {
    try {
        Files.move(
            temporary,
            target,
            StandardCopyOption.ATOMIC_MOVE
        );
    } catch (AtomicMoveNotSupportedException ex) {
        throw new IllegalStateException(
            "Filesystem does not support atomic publication",
            ex
        );
    }
}
~~~

Atomic rename giúp consumer nhìn thấy tên file cuối cùng sau khi file đã được chuyển. Consumer không quan sát được quá trình copy từng byte như khi ghi trực tiếp vào final path.

Atomic move thường chỉ có thể được bảo đảm trong cùng filesystem và phụ thuộc filesystem/provider. Nếu staging và published nằm trên hai mount khác nhau, move có thể không atomic hoặc không được hỗ trợ.

Không âm thầm bỏ ATOMIC_MOVE rồi giả định move thường cũng atomic. Nếu không hỗ trợ, dùng chiến lược copy-to-new-name, verify nội dung, rồi tạo marker sau khi copy hoàn tất; consumer phải dựa vào marker thay vì chỉ nhìn thấy file.

## 11. Vì sao marker được ghi sau khi file đã publish?

Thứ tự publish cần tránh hai failure window:

**Ghi marker trước, rồi mới move file:** consumer có thể thấy marker COMMITTED trong khi final file chưa tồn tại hoặc chưa hoàn chỉnh.

**Move file trước, rồi ghi marker:** nếu process dừng giữa hai bước, final file có thể đã tồn tại nhưng chưa có marker. Consumer vẫn bỏ qua file vì marker chưa COMMITTED. Recovery có thể xác minh file và hoàn tất marker.

Vì vậy, với marker trong database:

~~~text
1. Close temporary file
2. Verify temporary file
3. Atomic move to final path
4. Commit marker in database
5. Consumer reads only when marker is COMMITTED
~~~

Nếu bước 4 thất bại, file đã publish nhưng chưa được công bố theo contract. Đây là trạng thái có thể phục hồi: kiểm tra batch ID, file path, checksum và cập nhật marker một cách idempotent.

## 12. Marker dạng sidecar file

Với consumer chỉ quan sát filesystem, có thể dùng sidecar marker:

~~~text
orders-2026-11-15.csv
orders-2026-11-15.csv.done
~~~

Sau khi file output đã hoàn tất và được publish, producer tạo marker tạm rồi rename:

~~~java
public void createDoneMarker(Path marker, String content)
        throws IOException {

    Path temporaryMarker = marker.resolveSibling(
        marker.getFileName() + ".tmp"
    );

    Files.writeString(
        temporaryMarker,
        content,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW
    );

    Files.move(
        temporaryMarker,
        marker,
        StandardCopyOption.ATOMIC_MOVE
    );
}
~~~

Marker có thể chứa batch ID, record count, checksum, schema version và thời điểm publish. Nếu chỉ cần một tín hiệu đơn giản, file rỗng .done cũng có thể đủ, nhưng manifest có dữ liệu giúp consumer xác minh output.

Consumer phải yêu cầu marker và kiểm tra marker tương ứng với đúng file. Không dùng một marker chung cho nhiều batch nếu không có cách xác định artifact nào đã hoàn tất.

## 13. Manifest thay cho marker rỗng

Một manifest có thể mô tả chính xác output:

~~~json
{
  "batchId": "batch-2026-11-15-001",
  "state": "COMMITTED",
  "file": "orders.csv",
  "recordCount": 125000,
  "sha256": "9b1f...example",
  "schemaVersion": 2,
  "committedAt": "2026-11-15T16:00:00Z"
}
~~~

Consumer có thể kiểm tra batch ID, file tồn tại, checksum, schema version và record count. Manifest cũng giúp điều tra khi file đã được publish nhưng consumer không xử lý được.

## 14. Database staging table

Với output database, thay vì ghi trực tiếp vào bảng consumer đọc, có thể ghi vào staging table:

~~~sql
create table order_export_stage (
    batch_id varchar(100) not null,
    source_order_id varchar(100) not null,
    customer_id varchar(100) not null,
    total_amount decimal(18, 2) not null,
    constraint uk_order_export_stage
        unique (batch_id, source_order_id)
);
~~~

Mỗi hàng gắn với batch ID. Consumer hoặc view chỉ đọc dữ liệu thuộc batch có marker COMMITTED:

~~~sql
select s.source_order_id, s.customer_id, s.total_amount
from order_export_stage s
join batch_output_control c
  on c.batch_id = s.batch_id
where c.state = 'COMMITTED';
~~~

Các chunk có thể commit dần vào staging table. Nếu job thất bại, một phần staging rows vẫn tồn tại nhưng consumer không nhìn thấy chúng vì marker chưa COMMITTED.

Khi step hoàn tất, finalization step kiểm tra số hàng và chuyển marker sang COMMITTED. Nếu staging table chính là output consumer sử dụng, có thể không cần copy sang bảng khác; marker là cổng công bố dữ liệu.

## 15. Promote staging rows vào bảng đích

Nếu cần một bảng đích không chứa trạng thái staging, finalization step có thể chuyển dữ liệu:

~~~sql
insert into imported_order (
    source_order_id,
    customer_id,
    total_amount
)
select
    source_order_id,
    customer_id,
    total_amount
from order_export_stage
where batch_id = :batchId;
~~~

Sau đó cập nhật marker:

~~~sql
update batch_output_control
set state = 'COMMITTED',
    committed_at = current_timestamp,
    actual_count = :actualCount
where batch_id = :batchId
  and state = 'READY';
~~~

Hai thao tác phải chạy trong cùng transaction database nếu muốn consumer chỉ thấy target rows khi marker đã COMMITTED. Khi transaction commit, cả dữ liệu đích và marker cùng trở nên visible theo isolation semantics của database.

Nếu insert target thành công nhưng update marker thất bại trong cùng transaction, cả hai thay đổi rollback. Nếu dùng hai datasource hoặc hai transaction độc lập, không có guarantee nguyên tử như vậy nếu không dùng distributed transaction phù hợp.

## 16. Commit marker trong cùng database transaction

Đây là lợi thế của output database. Nếu final output và marker nằm trong cùng database, cùng transaction manager, có thể công bố đồng thời:

~~~java
@Service
public class OrderOutputFinalizer {

    private final JdbcTemplate jdbc;

    public OrderOutputFinalizer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void commitBatch(String batchId, long count) {
        jdbc.update("""
            insert into imported_order
                (source_order_id, customer_id, total_amount)
            select source_order_id, customer_id, total_amount
            from order_export_stage
            where batch_id = ?
            """, batchId);

        int changed = jdbc.update("""
            update batch_output_control
            set state = 'COMMITTED',
                actual_count = ?,
                committed_at = current_timestamp
            where batch_id = ?
              and state = 'READY'
            """, count, batchId);

        if (changed != 1) {
            throw new IllegalStateException(
                "Batch output marker was not transitioned"
            );
        }
    }
}
~~~

Đây là ví dụ minh họa. Cần xử lý unique constraint, upsert, batch ID đã commit và khả năng finalization được gọi lại. Nếu bảng đích có unique key, lần gọi lại sau khi transaction trước commit có thể cần xác định marker state trước khi insert.

Điều kiện WHERE state = READY giúp tránh chuyển marker từ state không mong muốn. Kiểm tra số hàng update để phát hiện batch đã bị thay đổi hoặc finalization chạy đồng thời.

## 17. Marker không nên được cập nhật sau mỗi item

Một commit marker ở cấp batch phải có nghĩa toàn bộ output đã hoàn chỉnh. Nếu cập nhật state COMMITTED sau mỗi chunk, consumer có thể đọc batch khi chỉ một phần dữ liệu đã ghi.

Có thể lưu progress riêng:

~~~text
state = WRITING
last_committed_chunk = 42
rows_written = 4200
~~~

Đây là progress/checkpoint metadata, không phải commit marker cuối cùng.

Chỉ khi tất cả chunk đã commit, writer đóng, kiểm tra hoàn tất và publication thành công mới chuyển state sang COMMITTED.

Nếu consumer cần xử lý incremental từng chunk, hãy thiết kế một contract khác: mỗi chunk có sequence ID và marker riêng, consumer xác nhận từng chunk. Không dùng batch-level COMMITTED để biểu diễn progress.

## 18. Tạo marker bằng dedicated finalization step

Một cách rõ ràng trong Spring Batch là tách job thành các step:

~~~text
InitializeOutputStep
       |
       v
WriteTemporaryOutputStep
       |
       v
ValidateTemporaryOutputStep
       |
       v
PublishOutputStep
       |
       v
CommitMarkerStep
       |
       v
Job COMPLETED
~~~

Dedicated finalization step có thể dùng tasklet để kiểm tra trạng thái batch, xác minh temporary artifact, xác nhận writer đã đóng, move file hoặc promote staging rows, ghi marker và lưu count/checksum.

Không nên đặt logic publish phức tạp vào một callback không có transaction boundary rõ ràng. JobExecutionListener hoặc StepExecutionListener hữu ích cho thông báo/metrics, nhưng dedicated step giúp orchestration và restart dễ quan sát hơn.

## 19. Không đánh dấu COMMITTED trong afterWrite

afterWrite được gọi sau một lần writer ghi chunk thành công. Nó không có nghĩa toàn bộ step đã hoàn tất. Sau callback này, chunk khác vẫn có thể thất bại.

Tương tự, beforeStep không thể xác nhận output cuối cùng và onWriteError chỉ báo lỗi của lần ghi hiện tại. Commit marker phải dựa trên trạng thái hoàn tất của toàn bộ output.

Một step finalization chạy sau writer step chỉ được thực hiện khi flow cho phép tiếp tục từ trạng thái thành công. Nếu writer step FAILED, finalization không nên chạy như một publish bình thường.

## 20. Restart với temporary file

Khi job thất bại giữa lúc ghi file, có hai hướng:

**Resume:** giữ file tạm và checkpoint. Khi restart cùng JobInstance, writer mở lại đúng file, khôi phục state và tiếp tục từ vị trí đã commit.

**Rebuild:** xóa staging output cũ theo một quy trình được kiểm soát rồi chạy lại toàn bộ từ đầu với checkpoint/JobInstance mới.

Không trộn hai hướng. Nếu xóa file nhưng vẫn dùng checkpoint cũ, writer có thể cố tiếp tục ở vị trí không tồn tại. Nếu giữ file nhưng reader bắt đầu từ đầu, output có thể bị lặp.

Với resume, dùng cùng temporary path qua restart, giữ writer name và state configuration ổn định, bật saveState cho writer nếu cần checkpoint và không xóa temp file khi execution FAILED nếu còn khả năng restart.

Với rebuild, tạo một logical attempt/batch identity mới hoặc reset có chủ đích, bảo đảm không có consumer đọc artifact cũ, xóa staging data/file theo batch ID chính xác và tạo checkpoint mới từ đầu.

## 21. Restart với temporary database output

Staging rows đã commit ở các chunk trước thường được giữ lại khi job thất bại. Khi restart cùng JobInstance, reader tiếp tục sau checkpoint và writer ghi các chunk còn lại.

Để tránh duplicate staging rows nếu một chunk được replay, đặt unique constraint trên batch_id và source_record_id, dùng upsert/insert-if-absent theo contract, bảo đảm chunk transaction và staging writer cùng transaction manager khi có thể.

Không xóa toàn bộ staging rows ở beforeStep của mọi lần restart. Nếu step được thiết kế để rebuild từ đầu, cleanup staging rows một cách rõ ràng và dùng execution/JobInstance mới phù hợp. Đừng tự xóa staging chỉ vì step bắt đầu; step có thể đang là lần restart hợp lệ.

## 22. Failure window giữa publish và marker

Với file output và marker database, hai thao tác không thể mặc nhiên nằm trong cùng transaction:

~~~text
File rename thành công
       |
       v
Process dừng đột ngột
       |
       v
Marker vẫn READY
~~~

Consumer không đọc file vì marker chưa COMMITTED. Khi recovery chạy, nó kiểm tra batch đang ở READY hay chưa, final file có tồn tại không, file có đúng batch ID/checksum không, số record có khớp không và marker COMMITTED đã tồn tại chưa.

Nếu file hợp lệ và marker chưa commit, recovery có thể ghi marker. Nếu file thiếu hoặc checksum sai, chuyển trạng thái lỗi và publish lại từ staging nếu có thể.

Đây là lý do final path nên bất biến theo batch ID và marker update phải idempotent. Recovery có thể được chạy nhiều lần mà không tạo thêm artifact hoặc đánh dấu nhầm batch.

## 23. Failure window trước publish

Nếu process dừng khi writer vẫn đang tạo temporary output, marker chưa COMMITTED và consumer vẫn không đọc output. Khi restart, Spring Batch khôi phục writer state và tiếp tục nếu artifact còn phù hợp.

Nếu file bị hỏng hoặc không thể resume, chuyển batch sang quy trình rebuild. Không rename một file chưa xác minh thành final path chỉ để job hoàn tất.

## 24. Failure window sau marker

Nếu marker COMMITTED đã được ghi thành công, consumer có thể bắt đầu xử lý. Nếu job process dừng ngay sau đó nhưng trước khi JobExecution metadata được cập nhật COMPLETED, lần restart có thể chạy lại finalization.

Finalization phải idempotent:

- Nếu marker đã COMMITTED và artifact khớp, coi publication đã hoàn tất.
- Không overwrite final output đã commit bằng dữ liệu khác.
- Không tạo marker mới mâu thuẫn với marker cũ.
- Không promote staging rows lần thứ hai nếu thao tác không idempotent.

JobExecution status và marker state có thể tạm thời khác nhau. Marker là contract output; JobRepository là contract execution. Recovery cần đối chiếu cả hai thay vì tự động hạ marker COMMITTED chỉ vì execution trước không có status COMPLETED.

## 25. Marker cần chứa thông tin nào?

Một marker hữu ích thường có batch ID hoặc JobInstance identity, output type và schema version, final location/object key, record count, file size, checksum/hash, thời điểm commit và source batch/date hoặc tenant nếu cần.

Không cần đưa toàn bộ dữ liệu vào marker. Marker nên nhỏ, có thể kiểm tra nhanh và đủ để consumer xác nhận artifact đúng batch.

Checksum giúp phát hiện file bị cắt, thay đổi hoặc copy sai. Record count giúp phát hiện output thiếu hàng. Hai phép kiểm tra bổ sung cho nhau; checksum không tự chứng minh dữ liệu đúng về nghiệp vụ.

## 26. Consumer phải kiểm tra marker

Consumer cần tuân thủ publication contract:

~~~text
1. Discover candidate batch
2. Read marker/manifest
3. Require state COMMITTED
4. Verify batch ID and schema version
5. Verify artifact exists and checksum/count match
6. Process artifact
7. Record consumer acknowledgement
~~~

Nếu consumer chỉ kiểm tra file tồn tại, nó có thể đọc final file đã rename nhưng marker chưa được ghi. Nếu consumer chỉ đọc marker mà không xác minh batch ID/path, có thể dùng nhầm file của batch khác.

Consumer cũng cần idempotency. Nó có thể nhận lại cùng marker sau restart hoặc polling nhiều lần. Lưu batch ID đã consume bằng unique constraint hoặc inbox table để không xử lý output hai lần.

## 27. Commit marker và consumer acknowledgement là hai trạng thái khác nhau

COMMITTED nghĩa producer đã công bố output. Nó không có nghĩa consumer đã xử lý thành công.

~~~text
Producer:
  WRITING -> COMMITTED

Consumer:
  PENDING -> PROCESSING -> CONSUMED
                       |
                       +--> FAILED
~~~

Không đổi producer marker từ COMMITTED về CONSUMED khi consumer đọc xong. Producer và consumer có trách nhiệm riêng; acknowledgement nên được lưu ở bảng hoặc hệ thống consumer quản lý.

Nếu có nhiều consumer, mỗi consumer cần trạng thái acknowledgement riêng. Một marker COMMITTED có thể được nhiều consumer hợp lệ sử dụng.

## 28. Atomic rename không phải distributed transaction

Atomic rename có thể bảo đảm một thay đổi tên file trên filesystem, nhưng không phối hợp atomic với database marker, message broker hoặc remote consumer.

Ví dụ:

~~~text
Filesystem: rename file thành công
Database:   update marker thất bại
~~~

Hai resource ở hai hệ thống khác nhau không tự rollback cùng nhau. Dùng marker để điều khiển visibility và recovery để hoàn tất trạng thái là một cách xử lý failure window, không phải distributed atomic commit.

Nếu yêu cầu atomic commit thực sự giữa nhiều resource, cần transaction coordinator phù hợp và chấp nhận độ phức tạp. Với nhiều batch export, publish file trước rồi ghi marker và dùng recovery thường đơn giản hơn.

## 29. Temporary output trên object storage

Object storage như S3 hoặc blob storage thường không có thao tác rename nguyên tử giống filesystem. Rename có thể được triển khai bằng copy rồi delete, do đó consumer có thể nhìn thấy object trong quá trình copy tùy cách publish.

Một pattern an toàn:

~~~text
staging/batch-001/orders.csv
       |
       v
Upload hoàn tất
       |
       v
Verify size/checksum
       |
       v
Write manifest COMMITTED
       |
       v
Consumer chỉ đọc object được manifest tham chiếu
~~~

Manifest được tạo sau khi object upload và xác minh hoàn tất. Nếu upload multipart, chỉ công bố sau khi complete multipart upload thành công.

Nếu cần copy sang prefix final, copy object tới key mới, xác minh object đích, sau đó mới ghi marker. Consumer không được suy luận rằng object trong prefix final đã hoàn chỉnh nếu chưa có manifest.

## 30. Tên output bất biến và tránh overwrite

Đường dẫn final nên chứa batch ID hoặc version để mỗi output đã commit là bất biến:

~~~text
published/orders/batch-001/orders.csv
published/orders/batch-002/orders.csv
~~~

Không dùng một đường dẫn chung orders.csv cho mọi batch nếu consumer có thể đang đọc file cũ trong lúc producer ghi file mới. Overwrite tạo race giữa consumer và producer, và marker cũ có thể trỏ tới nội dung mới.

Nếu cần một alias latest, cập nhật alias sau khi batch output mới đã COMMITTED. Alias chỉ là pointer tới artifact bất biến, không phải nơi writer ghi trực tiếp.

## 31. Partitioned output

Nếu step chạy theo partition, mỗi partition có thể tạo temporary file riêng:

~~~text
staging/batch-001/
  partition-000.csv.tmp
  partition-001.csv.tmp
  partition-002.csv.tmp
~~~

Sau khi mọi partition thành công, xác minh tất cả partition output, kiểm tra tổng record count, ghép file hoặc tạo manifest liệt kê các part, publish toàn bộ output rồi ghi một batch-level commit marker.

Không ghi marker COMMITTED ngay khi partition đầu tiên hoàn tất. Batch chỉ được công bố khi tất cả partition cần thiết đã sẵn sàng.

Nếu consumer có thể xử lý từng partition độc lập, có thể dùng marker theo partition và một manifest batch-level biểu diễn tập partition hoàn chỉnh. Hợp đồng phải xác định rõ consumer được phép xử lý partial batch hay không.

## 32. Dọn temporary output

Temporary output có thể tích lũy khi job thất bại hoặc bị hủy. Cleanup cần dựa trên trạng thái và retention, không chỉ dựa vào tuổi file.

Một policy có thể là:

- Giữ output WRITING/FAILED trong khoảng thời gian cho phép restart.
- Không xóa artifact của batch COMMITTED nếu còn trong retention cho consumer.
- Chỉ cleanup batch ABANDONED sau khi có quyết định vận hành.
- Xóa file .tmp mồ côi khi đã xác nhận không có JobExecution có thể restart.
- Ghi log batch ID, path và lý do cleanup.

Không xóa temp file chỉ vì JobExecution hiện tại FAILED; operator có thể dự định restart. Cũng không xóa staging rows của một batch đang READY nhưng finalization chưa chạy.

Cleanup job cần có lock/claim hoặc kiểm tra trạng thái để không xóa output trong lúc một execution khác đang dùng.

## 33. Marker và concurrency

Hai execution cùng batch ID không nên cùng publish output. Có thể bảo vệ bằng unique primary key trên batch ID, state transition có điều kiện, optimistic locking/version column, database lock/lease nếu cần ownership trong thời gian dài và unique final path theo batch ID.

Ví dụ:

~~~sql
update batch_output_control
set state = 'READY'
where batch_id = :batchId
  and state = 'WRITING';
~~~

Kiểm tra số hàng cập nhật. Nếu bằng 0, execution không sở hữu transition hoặc batch đã ở state khác. Không bỏ qua kết quả này.

Một row lock trong transaction ngắn có thể bảo vệ transition, nhưng không nên giữ database transaction mở trong suốt quá trình copy file lớn. Claim state/lease riêng và finalization ngắn thường phù hợp hơn.

## 34. Version hóa output và marker

Consumer cần biết schema output nào đang được publish. Nếu đổi cột CSV hoặc JSON format, marker/manifest nên chứa schemaVersion:

~~~json
{
  "batchId": "batch-001",
  "state": "COMMITTED",
  "schemaVersion": 3,
  "file": "orders.csv"
}
~~~

Consumer kiểm tra version được hỗ trợ trước khi parse. Nếu version không tương thích, consumer báo lỗi và giữ batch ở trạng thái chưa consume để xử lý sau.

Không thay format output dưới cùng một schema version. Restart một batch cũ bằng code mới cần dùng đúng output version hoặc có migration/rebuild plan.

## 35. Ví dụ flow job cho file output

Một job có thể chia trách nhiệm như sau:

~~~java
@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        Step initializeOutputStep,
        Step writeTemporaryFileStep,
        Step validateOutputStep,
        Step publishOutputStep) {

    return new JobBuilder("exportOrdersJob", jobRepository)
        .start(initializeOutputStep)
        .next(writeTemporaryFileStep)
        .next(validateOutputStep)
        .next(publishOutputStep)
        .build();
}
~~~

Trong flow này, initializeOutputStep tạo/claim batch control record và xác định staging path; writeTemporaryFileStep dùng FlatFileItemWriter ghi theo chunk và lưu state; validateOutputStep kiểm tra file đã đóng, count và checksum; publishOutputStep move file sang final path rồi ghi commit marker.

Ví dụ chỉ minh họa orchestration. Các step cần dùng đúng JobParameters/ExecutionContext để chia sẻ batch ID và path; finalization cần xử lý idempotent khi được restart.

## 36. Ví dụ tasklet publish và marker

Tasklet có thể gọi một service finalizer:

~~~java
@Bean
Step publishOutputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet publishOutputTasklet) {

    return new StepBuilder("publishOutputStep", jobRepository)
        .tasklet(publishOutputTasklet, transactionManager)
        .build();
}
~~~

Service finalizer nên chia phần filesystem và database thành các thao tác có thể recovery:

~~~java
public void finalizeOutput(OutputMetadata metadata) throws IOException {
    verifyTemporaryArtifact(metadata);
    publishFileIfNeeded(metadata);
    markerService.markCommitted(metadata);
}
~~~

Không đặt một transaction database dài bao trùm thao tác copy file lớn. Việc cập nhật marker có thể chạy trong transaction ngắn sau khi file đã được publish. Nếu marker update lỗi, lần restart gọi lại finalizer sẽ xác minh file final và thử cập nhật marker.

## 37. Kiểm tra file trước khi commit marker

Các kiểm tra có thể gồm:

- File tồn tại và không rỗng nếu output không được phép rỗng.
- Kích thước file nằm trong giới hạn hợp lý.
- Header/schema đúng version.
- Số dòng dữ liệu bằng expected count.
- Checksum được tính và lưu.
- File có thể mở và parse đến cuối.
- Không còn file partition nào thiếu.

Không chỉ kiểm tra file size lớn hơn zero. File có thể chứa header nhưng thiếu toàn bộ record. Nếu output được phép rỗng, count bằng zero có thể hợp lệ và phải được biểu diễn rõ trong manifest.

Expected count cần đến từ một nguồn đáng tin cậy. Nếu count chỉ được tính từ chính file vừa ghi, nó xác nhận tính nhất quán nội bộ nhưng không phát hiện được việc reader bỏ sót input.

## 38. Đối soát input và output

Nếu cần kiểm tra toàn vẹn nghiệp vụ, có thể lưu read count, filter count, process skip count, write count và rejected count.

Các con số phải được hiểu theo semantics của Spring Batch. Ví dụ item processor trả null làm tăng filter count và không tới writer; skip count là item bị bỏ qua do exception. Không cộng các counter một cách tùy tiện nếu chúng không cùng đơn vị hoặc cùng phase.

Có thể kiểm tra phương trình đối soát theo thiết kế job, chẳng hạn:

~~~text
Read items = Written items + Filtered items + Skipped items
~~~

Đây là ví dụ khái niệm; cần tính thêm retry, error handling và item được tách/gộp nếu pipeline có các behavior đó. Chỉ ghi marker khi reconciliation rules của batch đã đạt.

## 39. Bảo mật temporary output

Temporary output có thể chứa dữ liệu nhạy cảm giống final output. Nó cần cùng mức bảo vệ:

- Thư mục staging có quyền truy cập hạn chế.
- Không đặt temp file trong web root hoặc public bucket.
- Dùng encryption at rest nếu yêu cầu.
- Không đưa secret/token vào file name hoặc manifest.
- Áp dụng retention và secure deletion theo policy.
- Không log toàn bộ nội dung file khi verify lỗi.

Việc đổi tên từ staging sang published không tự thay đổi access control nếu cả hai path nằm cùng filesystem. Với object storage, kiểm tra ACL/policy của cả hai prefix và manifest.

## 40. Những lỗi thường gặp khi dùng temporary output và commit marker

**Ghi trực tiếp vào final path:** consumer có thể đọc output chưa hoàn chỉnh. Ghi vào staging trước.

**Tạo marker sau mỗi chunk:** consumer có thể coi partial batch là hoàn tất. Chỉ tạo batch-level marker sau toàn bộ output.

**Ghi marker trước khi publish file:** marker có thể trỏ tới artifact chưa tồn tại hoặc chưa hoàn chỉnh. Publish rồi mới commit marker.

**Dùng JobExecution ID làm temp path khi cần restart:** lần restart có thể dùng path khác checkpoint cũ. Dùng batch identity ổn định.

**Xóa temp file khi job FAILED:** làm mất dữ liệu để restart. Chỉ cleanup khi batch không còn được phép restart.

**Đổi writer name hoặc path giữa restart:** ExecutionContext không còn khớp resource. Giữ cấu hình ổn định hoặc rebuild có chủ đích.

**Cho rằng atomic rename phối hợp với database transaction:** hai resource không tự commit cùng nhau. Dùng marker và recovery.

**Dùng move thường khi atomic move không hỗ trợ:** có thể tạo cửa sổ consumer đọc file copy dở dang. Dùng marker gating hoặc một publish protocol khác.

**Đặt marker COMMITTED trước khi file được xác minh:** consumer có thể nhận file sai hoặc thiếu record. Verify count/checksum trước.

**Không làm finalization idempotent:** restart có thể copy/publish lặp hoặc chèn staging rows hai lần. Kiểm tra marker/path/state trước khi hành động.

**Dựa vào Job status thay marker:** JobExecution và output publication có failure window riêng. Consumer cần contract marker.

**Không kiểm tra marker ở consumer:** temporary output vẫn có thể bị đọc sớm. Consumer chỉ xử lý batch COMMITTED.

**Không quản lý consumer acknowledgement:** consumer có thể đọc lại marker và xử lý output lần nữa. Lưu batch ID đã consume.

**Cleanup dựa chỉ vào tuổi file:** có thể xóa artifact của execution đang chờ restart. Kiểm tra batch state và ownership.

**Không kiểm soát concurrency theo batch ID:** hai execution có thể publish cùng final path. Dùng unique key và conditional state transition.

## 41. Quy trình triển khai temporary output và commit marker

Trước tiên, xác định output được ghi ở đâu và consumer nhận biết output hoàn tất bằng cách nào. Chọn batch ID ổn định, tạo staging path/table riêng và định nghĩa state machine như PENDING, WRITING, READY, COMMITTED, FAILED. Consumer phải chỉ đọc artifact có marker COMMITTED.

Tiếp theo, ghi output theo chunk vào staging. Với file, giữ path và writer identity ổn định để restart có thể tiếp tục; với database, gắn batch ID vào từng staging row và dùng unique key để chống replay. Khi writer step hoàn tất, đóng output, kiểm tra schema, record count và checksum. Dùng finalization step để publish: atomic rename trong cùng filesystem nếu hỗ trợ, hoặc copy/verify/manifest với object storage.

Cuối cùng, ghi marker sau khi artifact đã được publish. Với database output, promote rows và update marker trong cùng transaction nếu cùng database/transaction manager. Với file output, xử lý failure window giữa rename và marker bằng recovery idempotent. Consumer kiểm tra marker, version, checksum và ghi acknowledgement riêng. Giữ temporary output khi restart còn được phép; cleanup chỉ sau retention và kiểm tra trạng thái.

Temporary output và commit marker giúp tách quá trình tạo dữ liệu khỏi thời điểm công bố dữ liệu. Spring Batch có thể commit từng chunk trong lúc output vẫn đang WRITING; consumer chỉ nên nhìn thấy artifact sau khi toàn bộ output được xác minh và marker chuyển sang COMMITTED. Với database, dữ liệu cuối và marker có thể cùng transaction; với file/object storage, cần publish protocol và recovery cho failure window giữa artifact và marker. Khi batch identity ổn định, finalization idempotent và consumer tuân thủ marker, job có thể restart an toàn mà không để hệ thống downstream đọc dữ liệu dở dang.
