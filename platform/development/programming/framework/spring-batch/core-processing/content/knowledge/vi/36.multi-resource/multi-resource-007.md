# Phân chia output theo số item

Trong Spring Batch, MultiResourceItemWriter cho phép một Step ghi output ra nhiều resource thay vì dồn toàn bộ dữ liệu vào một file. Writer bao một delegate có khả năng nhận Resource, theo dõi số item đã ghi vào resource hiện tại và chuyển sang resource kế tiếp khi đạt giới hạn cấu hình.

Cơ chế này phù hợp khi hệ thống nhận yêu cầu mỗi file chỉ chứa tối đa một số record nhất định, chẳng hạn chia file xuất theo từng 100.000 dòng để truyền sang hệ thống khác. MultiResourceItemWriter phân chia theo số item mà writer nhận được, không dựa trên kích thước byte của file. Để sử dụng an toàn, cần cấu hình delegate, quy tắc đặt tên file, checkpoint/restart, transaction và resource lifecycle nhất quán.

## 1. Vì sao cần chia output thành nhiều resource?

Một batch có thể xử lý hàng triệu bản ghi. Ghi tất cả vào một file duy nhất có thể gây khó khăn cho downstream:

- Hệ thống nhận giới hạn số dòng hoặc kích thước file.
- File quá lớn khó truyền qua mạng hoặc lưu trữ.
- Nhiều consumer cần xử lý các phần dữ liệu độc lập.
- Vận hành cần chia file theo lô để kiểm tra, retry hoặc lưu trữ.
- Một file khổng lồ khó thao tác thủ công và khó phục hồi khi truyền thất bại.

Ví dụ Job xuất 1.000.000 đơn hàng, mỗi file tối đa 100.000 item:

~~~text
Input: 1.000.000 Order
             |
             v
    MultiResourceItemWriter
             |
      +------+------+------+
      |      |      |      |
      v      v      v      v
   File 1 File 2 File 3 ... File 10
   100k   100k   100k       100k
~~~

Thay vì phải tự đếm dòng, đóng file, tạo file tiếp theo và khởi tạo writer mới, ứng dụng giao phần điều phối resource cho MultiResourceItemWriter.

## 2. MultiResourceItemWriter hoạt động thế nào?

MultiResourceItemWriter là một writer bao quanh một delegate writer. Delegate phải hỗ trợ nhận resource mới, thông qua contract ResourceAwareItemWriterItemStream. Ví dụ phổ biến là FlatFileItemWriter.

Các trách nhiệm được tách ra:

- MultiResourceItemWriter theo dõi index resource và số item đã ghi vào resource hiện tại.
- Delegate writer thực hiện serialize item và ghi nội dung vào resource đang được gán.
- ResourceSuffixCreator tạo suffix để phân biệt từng file.
- Step và JobRepository quản lý checkpoint để hỗ trợ restart.

Luồng khái quát:

~~~text
Chunk items
    |
    v
MultiResourceItemWriter
    |
    +--> Kiểm tra số item ở resource hiện tại
    |
    +--> Còn chỗ: ghi vào resource hiện tại
    |
    +--> Đạt giới hạn: chuyển sang resource kế tiếp
    |                     |
    |                     v
    |               Delegate.setResource(...)
    |
    v
Delegate writer ghi item
~~~

Writer tiếp tục dùng delegate cho các resource kế tiếp. Ứng dụng không cần tự tạo một FlatFileItemWriter mới cho từng file.

## 3. Phân chia theo item count, không phải file size

Thuộc tính itemCountLimitPerResource đặt số item tối đa mà một resource được nhận theo cơ chế đếm của writer.

Ví dụ giới hạn là 3:

~~~text
Input: A, B, C, D, E, F, G, H

orders-00001.csv: A, B, C
orders-00002.csv: D, E, F
orders-00003.csv: G, H
~~~

Mỗi item được tính là một đơn vị, bất kể kích thước nội dung của nó. Nếu một record có payload dài 2 KB và record khác chỉ dài 30 byte, cả hai vẫn làm bộ đếm tăng một item.

Vì vậy:
- Nếu yêu cầu là tối đa 100.000 record/file, MultiResourceItemWriter phù hợp.
- Nếu yêu cầu là file không vượt quá 50 MB, giới hạn item count không bảo đảm điều đó.
- Nếu kích thước mỗi item biến động lớn, file có cùng số item có thể có dung lượng rất khác nhau.
- Nếu cần chia theo byte, cần custom writer hoặc bước phân chia khác đo kích thước serialized thực tế.

Không dùng itemCountLimitPerResource như một giới hạn dung lượng file.

## 4. Phân biệt chunk size và item count limit

Chunk size và item count limit điều khiển hai việc khác nhau:

| Tham số | Ý nghĩa |
|---|---|
| Chunk size | Số item được đọc/xử lý trong một chunk trước khi commit |
| itemCountLimitPerResource | Số item tối đa mà một output resource nhận trước khi chuyển file |

Ví dụ:
- Chunk size = 200.
- Item count limit = 1.000.

Mỗi resource sẽ nhận khoảng 5 chunk nếu mỗi chunk có đủ 200 item. Nhưng hai giới hạn không cần chia hết cho nhau.

Nếu resource hiện tại đã có 900 item và chunk tiếp theo có 200 item, writer phải phân chia chunk qua ranh giới resource:

~~~text
Resource 1 còn 100 chỗ
Chunk mới có 200 item

100 item đầu  -> Resource 1
100 item sau  -> Resource 2
~~~

Do đó, không cần đặt chunk size bằng item count limit. Chunk size nên được chọn theo transaction, bộ nhớ và hiệu năng; item count limit nên được chọn theo yêu cầu file của downstream.

## 5. Delegate phải nhận được Resource

MultiResourceItemWriter không tự định dạng dữ liệu. Nó cần delegate triển khai ResourceAwareItemWriterItemStream để có thể thay resource trước khi mở và ghi.

Một số delegate thường dùng:
- FlatFileItemWriter để ghi CSV, TSV hoặc text.
- StaxEventItemWriter để tạo XML resource riêng cho từng nhóm item nếu cấu hình XML tương thích.
- Custom writer triển khai ResourceAwareItemWriterItemStream.

Một ItemWriter thông thường chỉ có phương thức write nhưng không nhận Resource sẽ không đủ contract cho MultiResourceItemWriter.

Delegate thường cần:
- setResource(Resource) để nhận file hiện tại.
- open(ExecutionContext) để mở resource.
- write(...) để ghi item.
- update(ExecutionContext) để lưu state.
- close() để flush và đóng resource.

MultiResourceItemWriter quản lý việc chuyển resource và lifecycle của delegate theo từng file.

## 6. Cấu hình FlatFileItemWriter làm delegate

Ví dụ delegate ghi Order thành CSV:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderFileDelegate() {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileDelegate")
            // Resource thực tế sẽ được MultiResourceItemWriter gán.
            .resource(new FileSystemResource(
                    "target/delegate-placeholder.csv"))
            .lineAggregator(order ->
                    order.getId() + ","
                    + order.getCustomerId() + ","
                    + order.getAmount())
            .saveState(true)
            .build();
}
~~~

Resource trong cấu hình delegate là giá trị ban đầu để hoàn thiện bean. Khi MultiResourceItemWriter tạo file, nó gán resource tương ứng cho delegate trước khi mở file.

Trong ứng dụng thật, cần dùng CSV escaping đúng chuẩn cho dấu phẩy, dấu nháy kép và newline trong field. Có thể cấu hình DelimitedLineAggregator và FieldExtractor thay vì nối chuỗi thủ công.

Tên delegate cần ổn định vì writer có thể lưu state riêng vào ExecutionContext. Không dùng cùng một delegate instance cho các luồng xử lý đồng thời nếu nó giữ resource và state mutable.

## 7. Cấu hình MultiResourceItemWriter bằng Builder

Spring Batch cung cấp MultiResourceItemWriterBuilder để tạo writer:

~~~java
@Bean
@StepScope
MultiResourceItemWriter<Order> ordersMultiWriter(
        @Value("#{jobParameters['outputDirectory']}")
        String outputDirectory,
        FlatFileItemWriter<Order> orderFileDelegate) {

    return new MultiResourceItemWriterBuilder<Order>()
            .name("ordersMultiWriter")
            .resource(new FileSystemResource(
                    outputDirectory + "/orders"))
            .delegate(orderFileDelegate)
            .itemCountLimitPerResource(100_000)
            .resourceSuffixCreator(index ->
                    String.format("-%05d.csv", index))
            .saveState(true)
            .build();
}
~~~

Các cấu hình chính:

- name(...): tên ổn định của MultiResourceItemWriter trong ExecutionContext.
- resource(...): resource cơ sở dùng để tạo tên các file đầu ra.
- delegate(...): writer thực hiện việc ghi nội dung.
- itemCountLimitPerResource(...): số item tối đa trên mỗi resource.
- resourceSuffixCreator(...): quy tắc tạo suffix theo index resource.
- saveState(...): bật lưu checkpoint của wrapper.

Với suffix creator trong ví dụ, tên file được tạo theo index mà writer cung cấp, chẳng hạn orders-00001.csv, orders-00002.csv. Dùng số có padding giúp tên file được sắp xếp theo thứ tự từ điển dễ hơn.

Chữ ký và package cần theo phiên bản Spring Batch của dự án. Builder là cách khai báo rõ ràng và giảm lỗi do quên một thuộc tính bắt buộc.

## 8. Đặt tên file và ResourceSuffixCreator

Resource cơ sở là phần gốc của tên resource. ResourceSuffixCreator nhận index và trả về suffix để phân biệt file.

Ví dụ:

~~~java
.resource(new FileSystemResource("/batch/output/orders"))
.resourceSuffixCreator(index ->
        String.format("-%05d.csv", index))
~~~

Kết quả dự kiến theo index:

~~~text
/batch/output/orders-00001.csv
/batch/output/orders-00002.csv
/batch/output/orders-00003.csv
~~~

Một số nguyên tắc đặt tên:

- Tên file cần duy nhất trong phạm vi Job/JobInstance.
- Suffix phải xác định từ index, không sinh ngẫu nhiên.
- Không dùng timestamp mới cho mỗi lần restart nếu muốn tiếp tục cùng bộ file.
- Dùng zero-padding nếu consumer cần sort tên file theo thứ tự.
- Bảo đảm thư mục output tồn tại và process có quyền ghi.
- Tránh suffix chứa ký tự path separator hoặc dữ liệu không được kiểm soát.

Nếu dùng suffix mặc định của framework, hãy kiểm tra định dạng cụ thể trong phiên bản đang dùng. Nếu contract downstream yêu cầu một quy tắc tên file cố định, khai báo ResourceSuffixCreator tường minh và kiểm thử tên thực tế.

## 9. Đăng ký writer vào Step

MultiResourceItemWriter là writer chính được gắn vào Step:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        MultiResourceItemWriter<Order> ordersMultiWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(ordersMultiWriter)
            .build();
}
~~~

MultiResourceItemWriter triển khai ItemStream và quản lý lifecycle của delegate mà nó bao bọc. Trong cấu hình thông thường, đăng ký wrapper qua .writer(ordersMultiWriter) để Step gọi lifecycle của wrapper; wrapper điều phối delegate khi cần mở/đóng từng resource.

Không tự mở delegate bên ngoài wrapper hoặc dùng cùng delegate cho một Step khác cùng lúc. Nếu có thêm stream độc lập không thuộc wrapper, đăng ký stream đó riêng với Step.

## 10. Điều gì xảy ra khi một chunk vượt qua giới hạn?

Giả sử giới hạn mỗi file là 5 item, file hiện tại đã có 4 item và chunk mới có 3 item:

~~~text
Trước chunk:
  file-1: A, B, C, D
  còn 1 chỗ

Chunk mới:
  E, F, G

Sau khi ghi:
  file-1: A, B, C, D, E
  file-2: F, G
~~~

Writer chuyển sang resource tiếp theo khi giới hạn hiện tại đã đạt. Vì vậy, một chunk có thể được chia giữa hai hoặc nhiều file nếu chunk lớn hơn phần dung lượng item còn lại của file hiện tại.

Ứng dụng nên thiết kế consumer dựa trên thứ tự file và item thay vì giả định mỗi chunk luôn nằm trọn trong một file.

Chi tiết số lần gọi write tới delegate và cách chia các nhóm nhỏ là implementation detail có thể khác giữa phiên bản. Hãy dựa vào contract output và kiểm thử với phiên bản Spring Batch thực tế.

## 11. Thứ tự item giữa các resource

MultiResourceItemWriter ghi item theo thứ tự mà Step chuyển chúng tới writer. Khi resource hiện tại đạt giới hạn, các item tiếp theo được ghi vào resource mới.

Ví dụ:

~~~text
Input order:
  101, 102, 103, 104, 105, 106, 107

Limit = 3

File 1:
  101, 102, 103

File 2:
  104, 105, 106

File 3:
  107
~~~

Writer không tự sắp xếp dữ liệu. Nếu nguồn không có thứ tự ổn định, các file có thể chứa record theo thứ tự khác giữa các lần chạy hoặc restart.

Nếu thứ tự là yêu cầu nghiệp vụ:
- Dùng ORDER BY ổn định ở reader.
- Dùng khóa sort duy nhất nếu có thể.
- Không dựa vào thứ tự trả về tự nhiên của database.
- Giữ query và dữ liệu nguồn nhất quán qua restart.
- Kiểm tra thứ tự item trong từng file và giữa các file.

Tên file có index chỉ phản ánh thứ tự writer tạo resource, không tự đảm bảo thứ tự nghiệp vụ nếu input không được sắp xếp.

## 12. Bộ đếm tính những item nào?

Giới hạn được áp dụng trên item mà MultiResourceItemWriter nhận trong write path. Vì vậy, item bị filter ở processor và không đến writer sẽ không làm tăng bộ đếm output.

Ví dụ:
- Reader đọc 1.000 dòng.
- Processor loại 100 item bằng cách trả về null.
- Writer nhận 900 item.
- Với giới hạn 300, output có 3 resource chứa 300 item mỗi file.

Nếu có skip/retry ở writer, cần kiểm thử cách phiên bản framework cập nhật count và checkpoint trong tình huống lỗi. Không suy ra số record nguồn bằng tổng item output vì processor có thể filter hoặc biến đổi dữ liệu.

Nên đối chiếu:
- Read count.
- Process skip count.
- Write count.
- Item count trong từng resource.
- Tổng record trong các file cuối cùng.

## 13. Checkpoint và restart

MultiResourceItemWriter hỗ trợ lưu state để tiếp tục đúng resource khi Step restart. State của wrapper thường bao gồm thông tin như index resource hiện tại và số item đã ghi vào resource đó; delegate có thể có state riêng của nó.

Để restart đáng tin cậy:
- Đặt tên wrapper ổn định.
- Đặt tên delegate ổn định.
- Bật saveState(true) cho wrapper và delegate cần checkpoint.
- Giữ nguyên base resource.
- Giữ nguyên ResourceSuffixCreator và cách tạo suffix.
- Giữ nguyên item count limit.
- Giữ nguyên query, sort order và dữ liệu nguồn có ảnh hưởng đến thứ tự item.
- Không sửa hoặc xóa file đã được checkpoint.

Ví dụ lần đầu:
~~~text
JobInstance = 52
current resource index = 3
item count in current resource = 40
~~~

Sau khi restart cùng JobInstance, writer cần mở lại resource tương ứng và tiếp tục sau 40 item đã checkpoint theo state được lưu.

Không tự đặt lại index về 1 khi restart. Không tạo suffix mới dựa trên timestamp. Nếu output path thay đổi, checkpoint có thể trỏ tới resource không còn tồn tại hoặc không còn khớp.

## 14. Giữ ổn định output path theo JobInstance

Nếu Job cần restart và tiếp tục bộ file cũ, output base path nên ổn định theo JobInstance. Có thể tạo directory hoặc tên prefix từ JobInstance ID trong JobExecutionListener, sau đó inject qua Job ExecutionContext.

Ví dụ listener:

~~~java
public class MultiOutputPathListener
        implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution execution) {
        long instanceId =
                execution.getJobInstance().getInstanceId();

        String outputDirectory =
                "/batch/output/orders-" + instanceId;

        execution.getExecutionContext().putString(
                "orders.output.directory",
                outputDirectory);
    }
}
~~~

Writer step-scoped nhận đường dẫn:

~~~java
@Value("#{jobExecutionContext['orders.output.directory']}")
String outputDirectory
~~~

JobInstance ID giữ nguyên khi restart cùng instance, trong khi JobExecution ID thay đổi. Dùng ID của instance hoặc identifying business key ổn định giúp các file của cùng một đơn vị xử lý logic có cùng prefix.

Trong hệ thống có nhiều JobRepository hoặc nhiều môi trường, thêm tên Job, tenant hoặc environment vào đường dẫn để tránh trùng ID giữa các repository độc lập.

## 15. Overwrite và file đã tồn tại

Chính sách overwrite cần được xem xét cùng restart.

Có ba trường hợp khác nhau:

1. JobInstance mới: tạo một bộ output mới với prefix hoặc directory mới.
2. Restart cùng JobInstance: tiếp tục resource và checkpoint đã có.
3. Chạy lại logic nghiệp vụ mới: tạo JobInstance mới, thường có prefix khác.

Delegate như FlatFileItemWriter có các thuộc tính điều khiển xử lý resource đã tồn tại. Cần cấu hình phù hợp với việc tạo output mới và khôi phục output cũ. Không bật overwrite một cách máy móc nếu có thể xóa file đã chứa dữ liệu của chunk commit trước.

Nếu file tồn tại nhưng metadata không có checkpoint tương ứng, có thể đó là file orphan sau process crash hoặc lỗi vận hành. Cần đối chiếu JobRepository và output trước khi quyết định xóa, đổi tên hoặc tiếp tục ghi.

## 16. Header và footer được áp dụng cho từng file

Delegate được mở và đóng theo resource hiện tại. Vì vậy, header/footer callback của delegate thường được thực thi theo lifecycle của từng file, không phải chỉ một lần cho toàn bộ bộ file.

Ví dụ nếu delegate là FlatFileItemWriter có header callback:

~~~text
orders-00001.csv
  header
  item 1
  item 2
  ...
  item 100000

orders-00002.csv
  header
  item 100001
  item 100002
  ...
  footer
~~~

Mỗi file cần độc lập và hợp lệ theo contract. Nếu CSV yêu cầu header cột, mỗi resource nên có header riêng để consumer đọc file riêng lẻ được.

Nếu delegate là XML writer, mỗi resource cần là một XML document hoàn chỉnh với XML declaration và root element riêng. Không ghép byte nhiều file XML thành một document bằng cách nối file; cần parse và merge theo cấu trúc XML nếu muốn một tài liệu tổng.

Hãy xác nhận header/footer được ghi đúng ở file đầu, file giữa, file cuối và khi restart.

## 17. Empty input và file cuối chưa đầy

Nếu tổng số item không chia hết cho giới hạn, file cuối sẽ có ít item hơn các file trước.

Ví dụ 10 item, limit 4:

~~~text
File 1: 4 item
File 2: 4 item
File 3: 2 item
~~~

Không cần tạo thêm file rỗng chỉ để đủ số lượng file. Với input rỗng, hành vi tạo resource phụ thuộc lifecycle và phiên bản writer; không nên giả định file rỗng luôn được tạo.

Nếu downstream yêu cầu một file ngay cả khi không có dữ liệu, hãy định nghĩa rõ hành vi:
- Tạo file rỗng có header.
- Tạo file chỉ có header/footer.
- Tạo manifest báo zero records.
- Không tạo file và đánh dấu batch không có dữ liệu.

Có thể cần một bước riêng xử lý trường hợp zero item thay vì ép writer tạo resource không có nội dung.

## 18. Ghi theo số item khác với chia theo file size

Khi item có kích thước biến động, số item không tương quan tuyến tính với số byte.

Ví dụ:
~~~text
File A: 10.000 item x trung bình 100 byte  ~= 1 MB
File B: 10.000 item x trung bình 5 KB      ~= 50 MB
~~~

Cả hai file đều đạt cùng item count limit nhưng kích thước chênh lệch lớn.

Nếu yêu cầu là giới hạn file size:
- Tính kích thước serialized trước khi ghi.
- Dùng custom ResourceAwareItemWriterItemStream theo dõi byte.
- Chuyển resource khi item tiếp theo làm vượt giới hạn.
- Xử lý trường hợp một item riêng lẻ lớn hơn giới hạn.
- Đảm bảo checkpoint lưu được resource index và byte offset.
- Kiểm thử encoding, newline và header/footer vì chúng cũng chiếm byte.

Không thay itemCountLimitPerResource bằng một giá trị ước lượng để giả lập byte limit nếu contract yêu cầu giới hạn dung lượng nghiêm ngặt.

## 19. Resource lifecycle và delegate

MultiResourceItemWriter quản lý resource hiện tại và delegate writer. Khi cần chuyển file, wrapper đóng delegate của resource cũ, gán resource mới và mở delegate cho file mới.

Điều này có nghĩa:
- Delegate phải hỗ trợ đổi resource.
- Delegate phải mở/đóng đúng cách nhiều lần trong cùng Step.
- Delegate không được giữ reference tới resource cũ sau khi chuyển file.
- Header/footer hoặc initialization của delegate có thể chạy lại trên mỗi file.
- State của wrapper và delegate cần được lưu đúng để restart.

Không tự gọi open hoặc close delegate từ processor hoặc listener. Hãy để wrapper quản lý lifecycle.

Nếu custom delegate có nhiều resource phụ thuộc nhau, phải đảm bảo setResource cập nhật tất cả resource liên quan và open/close an toàn khi được gọi nhiều lần.

## 20. Transaction và lỗi khi chuyển resource

Chunk transaction bao quanh xử lý item, nhưng file system không tự tham gia transaction JDBC. Khi một chunk vượt qua ranh giới file, wrapper có thể ghi một phần item vào resource cũ và phần còn lại vào resource mới.

Nếu lỗi xảy ra giữa lúc chuyển resource:
- Resource cũ có thể đã được flush/đóng.
- Resource mới có thể đã được tạo hoặc mở.
- Database transaction của chunk có thể rollback.
- File output cần được khôi phục theo checkpoint của writer.

Không giả định nhiều file và JobRepository được commit nguyên tử cùng nhau. Kiểm thử rollback đúng tại ranh giới rollover, đặc biệt nếu delegate ghi file hoặc external storage.

Với output quan trọng, nên ghi vào staging directory theo JobInstance, xác minh tổng số record/checksum rồi publish bộ file sau khi Job thành công. Có thể tạo manifest để downstream biết file nào thuộc batch và file nào đã hoàn tất.

## 21. Partitioning và nhiều writer đồng thời

MultiResourceItemWriter quản lý một index và một resource hiện tại cho instance của nó. Không nên chia sẻ cùng một writer instance cho nhiều thread hoặc nhiều worker đồng thời nếu không có cơ chế thread safety rõ ràng.

Nếu dùng partitioning:
- Mỗi worker StepExecution nên có writer target riêng.
- Resource prefix cần chứa JobInstance ID và partition key.
- Các worker không được ghi đè cùng tên file.
- Sau khi worker hoàn thành, một bước tổng hợp hoặc manifest có thể công bố bộ file.

Ví dụ:

~~~text
orders-instance-52/
  partition-0/
    orders-00001.csv
    orders-00002.csv
  partition-1/
    orders-00001.csv
    orders-00002.csv
~~~

Index resource của mỗi partition có thể bắt đầu lại trong namespace riêng vì directory/prefix đã phân biệt worker. Nếu nhiều worker ghi chung một directory với suffix index giống nhau, file có thể bị đè.

Nếu mục tiêu là giới hạn file theo số item trong từng partition, đặt limit trên writer của worker. Nếu mục tiêu là giới hạn tổng item của toàn Job, cần tính toán cách hợp nhất hoặc điều phối output ở cấp Job.

## 22. Tên file và thứ tự tiêu thụ

Downstream thường đọc nhiều file theo wildcard hoặc manifest. Cần xác định rõ thứ tự file và quy tắc phát hiện bộ file hoàn chỉnh.

Các lựa chọn:
- Numeric suffix có zero-padding để sort đúng.
- Manifest liệt kê tên file theo thứ tự.
- Thư mục riêng cho từng JobInstance.
- File marker hoặc trạng thái PUBLISHED sau khi mọi resource hoàn tất.

Không để downstream đọc file trong khi Job vẫn đang ghi. File cuối có thể chưa có footer hoặc chưa được đóng. Một cách phổ biến là ghi trong staging directory rồi di chuyển/công bố manifest sau khi hoàn thành.

Nếu consumer đọc theo wildcard, hãy bảo đảm wildcard không bắt cả file tạm, file cũ hoặc file của JobInstance khác.

## 23. Kiểm soát số lượng resource và dung lượng lưu trữ

Chia file theo item count có thể tạo ra rất nhiều resource nếu limit quá nhỏ. Điều này ảnh hưởng:
- Số lượng file trong directory.
- Metadata filesystem.
- Thời gian list/scan file.
- Số lần open/close.
- Số thao tác truyền và lưu trữ.
- Thời gian downstream lập lịch xử lý từng file.

Nếu limit quá lớn, file lại khó truyền hoặc vượt giới hạn consumer. Chọn item count dựa trên:
- Giới hạn của hệ thống nhận.
- Kích thước trung bình và phân bố item.
- Throughput và thời gian xử lý file.
- Số worker/consumer song song.
- Giới hạn số file trong storage.
- Chính sách retention.

Đo bằng dữ liệu gần với production. Đừng chọn limit chỉ dựa trên số lượng item trung bình nếu có record có payload lớn bất thường.

## 24. Kiểm thử MultiResourceItemWriter

Nên kiểm thử cả cách chia file và khả năng restart.

Các kịch bản:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Item count nhỏ | File được rollover đúng ngưỡng |
| Số item chia hết cho limit | Số resource đúng |
| Số item không chia hết | File cuối chứa phần dư |
| Một chunk vượt ranh giới | Item được phân vào file đúng |
| Chunk lớn hơn limit | Có thể tạo nhiều resource trong một write |
| Processor filter item | Chỉ item tới writer được tính |
| Empty input | Hành vi zero-resource đúng contract |
| Header/footer | Mỗi file có cấu trúc đúng |
| Suffix creator | Tên file duy nhất và sort đúng |
| Resource directory | Được tạo/kiểm tra theo chính sách |
| Restart giữa resource | Tiếp tục đúng index và item count |
| Restart sau rollover | Không ghi trùng hoặc bỏ sót item |
| Lỗi tại rollover | Resource cũ/mới được phục hồi đúng |
| File tồn tại | Overwrite và restart theo chính sách |
| Partitioning | Worker không đè file của nhau |
| Unicode và special characters | Nội dung file được encode/escape đúng |
| Disk full hoặc I/O failure | Step thất bại và cleanup rõ ràng |

Một integration test restart hữu ích:
1. Launch Job với JobParameters và output directory cố định.
2. Ghi qua ít nhất hai resource.
3. Cố ý làm Step thất bại sau một số chunk đã commit.
4. Lưu JobInstance ID, resource index và output files.
5. Restart cùng JobInstance.
6. Xác nhận writer tiếp tục đúng resource, không tạo suffix ngẫu nhiên.
7. Đọc tất cả file theo thứ tự và kiểm tra tổng item, thứ tự và business key.
8. Xác nhận không thiếu hoặc ghi trùng item.
9. Chỉ publish bộ file sau khi validation cần thiết hoàn tất.

Unit test builder và suffix creator không thay thế integration test với JobRepository thật.

## 25. Lỗi thường gặp

**Nhầm item count limit với file size limit.** Một file có thể vượt dung lượng dù số item đúng giới hạn.

**Nhầm chunk size với item count limit.** Chunk có thể nhỏ hơn, lớn hơn hoặc cắt qua ranh giới resource.

**Delegate không implement ResourceAwareItemWriterItemStream.** Wrapper không thể gán resource và quản lý lifecycle như yêu cầu.

**Không đặt tên writer ổn định.** State trong ExecutionContext có thể không được khôi phục đúng.

**Đổi base resource hoặc suffix creator khi restart.** Writer có thể mở file khác với file đã checkpoint.

**Không bật saveState.** Wrapper không lưu đủ thông tin để tiếp tục từ resource hiện tại.

**Không lưu state của delegate.** Delegate có thể không khôi phục được vị trí ghi của file hiện tại.

**Chia sẻ writer instance giữa các worker.** Index và current resource có thể bị race hoặc ghi đè.

**Cho rằng chunk luôn nằm trọn trong một file.** Một chunk có thể bị tách ở ngưỡng item count.

**Cho rằng file và database commit nguyên tử.** Filesystem không tự tham gia transaction JDBC.

**Dùng suffix không duy nhất.** Nhiều file có thể ghi đè nhau hoặc khó sắp xếp.

**Consumer đọc file trước khi đóng.** Downstream có thể nhận file chưa hoàn chỉnh.

**Không xử lý input rỗng.** Consumer có thể chờ một file mà writer không tạo.

**Không tính số lượng file.** Limit quá nhỏ có thể làm directory và storage quá tải.

## 26. Quy trình triển khai phân chia output theo số item

Khi cần chia output theo số record, hãy thực hiện theo trình tự:

1. Xác định giới hạn là số item hay dung lượng byte.
2. Chọn MultiResourceItemWriter nếu yêu cầu là giới hạn số item trên mỗi resource.
3. Chọn delegate triển khai ResourceAwareItemWriterItemStream.
4. Đặt tên wrapper và delegate ổn định.
5. Cấu hình base Resource và ResourceSuffixCreator xác định.
6. Đặt itemCountLimitPerResource theo contract downstream.
7. Bật saveState cho wrapper và delegate khi cần restart.
8. Gắn wrapper vào writer(...) của Step để nó quản lý delegate lifecycle.
9. Giữ output path, suffix, limit và thứ tự input ổn định qua restart.
10. Không chia sẻ một writer instance giữa các worker chạy đồng thời.
11. Dùng staging và manifest/publish để consumer chỉ nhận bộ file hoàn chỉnh.
12. Kiểm thử rollover trong chunk, file cuối, empty input, rollback, restart và partitioning.
13. Theo dõi số file, số item/file, dung lượng và lỗi I/O trong vận hành.

MultiResourceItemWriter tách việc quản lý nhiều resource khỏi logic ghi từng item. itemCountLimitPerResource quyết định khi nào chuyển file; delegate quyết định cách serialize; suffix creator quyết định tên resource; ExecutionContext hỗ trợ restart. Khi giữ các cấu hình này ổn định và kiểm thử đúng ranh giới chunk/resource, Spring Batch có thể xuất dữ liệu thành nhiều file theo số item mà vẫn duy trì thứ tự, checkpoint và khả năng phục hồi.

