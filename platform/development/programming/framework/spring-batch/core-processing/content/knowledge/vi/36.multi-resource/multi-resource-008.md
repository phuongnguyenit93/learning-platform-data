# Tên file suffix

Khi một job Spring Batch phải xuất một lượng dữ liệu lớn thành nhiều file, **MultiResourceItemWriter** có thể chia output thành các resource nhỏ theo giới hạn số item. Mỗi resource cần một tên riêng để không ghi đè file trước và để downstream có thể tìm đúng từng phần dữ liệu. Spring Batch cung cấp **ResourceSuffixCreator** để xác định phần suffix được thêm vào tên resource cơ sở khi writer tạo file tiếp theo.

Suffix là phần chuỗi được nối vào tên resource gốc. Với cách mặc định, writer thường tạo các tên dạng **orders.csv.1**, **orders.csv.2**... Nếu hệ thống nhận file yêu cầu extension ở cuối, ví dụ **orders-001.csv**, có thể cung cấp suffix creator tùy chỉnh. Việc đặt tên cần nhất quán, xác định được thứ tự, an toàn khi restart và tránh xung đột với output của những lần chạy khác.

## 1. MultiResourceItemWriter và suffix

**MultiResourceItemWriter<T>** là một writer bao ngoài một writer khác. Nó chuyển item đến delegate writer, đồng thời quyết định resource nào đang được ghi. Khi số item của resource hiện tại đạt giới hạn, writer đóng resource đó, tạo resource tiếp theo bằng cách thêm suffix vào resource cơ sở rồi tiếp tục ghi.

Ví dụ một export có 10.000 item, giới hạn 3.000 item mỗi file:

~~~text
orders.csv.1
orders.csv.2
orders.csv.3
orders.csv.4
~~~

Nếu dùng naming convention khác, có thể tạo:

~~~text
orders-part-001.csv
orders-part-002.csv
orders-part-003.csv
orders-part-004.csv
~~~

**MultiResourceItemWriter** quản lý việc rollover giữa các resource. Delegate như **FlatFileItemWriter** chịu trách nhiệm ghi nội dung item vào resource đang được gán. **ResourceSuffixCreator** chỉ quyết định phần tên thêm vào; nó không định dạng nội dung file, không chia chunk và không quyết định số item mỗi resource.

## 2. Resource cơ sở và suffix được ghép như thế nào?

Writer nhận một resource cơ sở, ví dụ **orders.csv**. Khi cần tạo resource tiếp theo, nó lấy tên resource cơ sở và nối chuỗi do suffix creator trả về. Với suffix mặc định theo số thứ tự, kết quả có thể là:

| Resource cơ sở | Suffix | Tên file được tạo |
|---|---|---|
| orders.csv | .1 | orders.csv.1 |
| orders.csv | .2 | orders.csv.2 |
| orders.csv | .3 | orders.csv.3 |

Điểm quan trọng là suffix được nối vào resource cơ sở. Writer không tự hiểu phần **.csv** là extension cần giữ ở cuối. Vì vậy, nếu consumer yêu cầu **orders-001.csv**, cần thiết kế base resource và suffix creator sao cho phép nối tạo ra đúng tên đó.

Một cách đơn giản là dùng base resource không có extension:

| Resource cơ sở | Suffix tùy chỉnh | Kết quả |
|---|---|---|
| orders | -part-001.csv | orders-part-001.csv |
| orders | -part-002.csv | orders-part-002.csv |

Không nên thêm **.csv** vào cả base resource và suffix nếu kết quả mong muốn chỉ có một extension. Ví dụ base **orders.csv** cộng suffix **-part-001.csv** sẽ tạo tên có hai đoạn **.csv**.

## 3. ResourceSuffixCreator là gì?

**ResourceSuffixCreator** là extension point của Spring Batch để tạo suffix cho resource tiếp theo. Interface nhận chỉ số resource và trả về chuỗi suffix:

~~~java
public interface ResourceSuffixCreator {

    String getSuffix(int index);
}
~~~

**MultiResourceItemWriter** sử dụng creator khi cần tạo resource mới. Suffix creator không cần biết item đang được ghi hoặc nội dung record; nó chỉ nhận index và tạo tên phần tiếp theo.

Spring Batch có implementation mặc định **SimpleResourceSuffixCreator**. Implementation này thêm dấu chấm và index vào tên resource, tạo convention như **.1**, **.2**, **.3**. Nếu convention đó phù hợp với hệ thống nhận file, có thể dùng mặc định. Nếu cần giữ extension, zero-padding hoặc quy ước tên riêng, hãy cung cấp implementation tùy chỉnh.

## 4. Cấu hình MultiResourceItemWriter cơ bản

Ví dụ dùng **FlatFileItemWriter** làm delegate:

~~~java
@Bean
public FlatFileItemWriter<Order> orderFileDelegate() {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileDelegate")
            .delimited()
            .delimiter(",")
            .names("orderId", "customerId", "amount")
            .build();
}

@Bean
public MultiResourceItemWriter<Order> multiOrderWriter(
        FlatFileItemWriter<Order> orderFileDelegate) {

    return new MultiResourceItemWriterBuilder<Order>()
            .name("multiOrderWriter")
            .resource(new FileSystemResource("output/orders.csv"))
            .delegate(orderFileDelegate)
            .itemCountLimitPerResource(3000)
            .saveState(true)
            .build();
}
~~~

Trong ví dụ, writer chia dữ liệu thành các resource, mỗi resource tối đa 3.000 item theo giới hạn được cấu hình. Nếu không chỉ định suffix creator, writer sử dụng cơ chế mặc định của phiên bản Spring Batch tương ứng.

Tên resource trong ví dụ là minh họa. Trước khi dùng trong production, hãy xác định thư mục output, quyền ghi, output identity theo job instance và chính sách xử lý file đã tồn tại.

## 5. Dùng suffix mặc định

Nếu không có yêu cầu naming đặc biệt, suffix mặc định là lựa chọn đơn giản:

~~~java
MultiResourceItemWriter<Order> writer =
        new MultiResourceItemWriterBuilder<Order>()
                .name("multiOrderWriter")
                .resource(new FileSystemResource("output/orders.csv"))
                .delegate(orderFileDelegate)
                .itemCountLimitPerResource(3000)
                .saveState(true)
                .build();
~~~

Với base resource **orders.csv**, các resource tiếp theo được đặt tên theo index. Cách này dễ cấu hình và phù hợp khi downstream có thể đọc danh sách file theo prefix hoặc manifest.

Hãy coi suffix mặc định là một phần của contract tên file. Nếu downstream đang tìm **orders-001.csv**, đổi sang mặc định có thể làm consumer không tìm thấy file dù nội dung được ghi đúng.

## 6. Tùy chỉnh suffix để extension nằm cuối

Nếu hệ thống nhận file yêu cầu tên dạng **orders-1.csv**, có thể cung cấp lambda hoặc class triển khai **ResourceSuffixCreator**:

~~~java
ResourceSuffixCreator suffixCreator =
        index -> "-" + index + ".csv";

MultiResourceItemWriter<Order> writer =
        new MultiResourceItemWriterBuilder<Order>()
                .name("multiOrderWriter")
                .resource(new FileSystemResource("output/orders"))
                .delegate(orderFileDelegate)
                .itemCountLimitPerResource(3000)
                .resourceSuffixCreator(suffixCreator)
                .saveState(true)
                .build();
~~~

Base resource là **output/orders**, suffix creator trả **-1.csv**, **-2.csv**... nên tên cuối có extension **.csv**.

Nếu API builder của phiên bản dự án không hỗ trợ lambda trực tiếp hoặc method có tên khác, có thể khai báo một class implements **ResourceSuffixCreator** rồi truyền instance vào builder/setter tương ứng. Luôn dùng đúng API của Spring Batch version trong ứng dụng.

## 7. Dùng số thứ tự có zero-padding

Nhiều hệ thống cần các tên file được sắp xếp đúng thứ tự khi liệt kê theo tên. Số thứ tự không padding có thể sắp xếp từ điển thành **part-1**, **part-10**, **part-2**. Zero-padding tạo tên nhất quán:

~~~java
ResourceSuffixCreator suffixCreator =
        index -> String.format("-part-%03d.csv", index);
~~~

Ví dụ kết quả:

~~~text
orders-part-001.csv
orders-part-002.csv
orders-part-003.csv
...
orders-part-010.csv
~~~

Độ rộng **03** trong format là ba chữ số tối thiểu. Nếu số resource có thể vượt 999, cần chọn độ rộng đủ lớn hoặc chấp nhận tên dài hơn khi index tăng.

Zero-padding chỉ ảnh hưởng cách biểu diễn tên. Nó không thay đổi thứ tự xử lý item, số item mỗi file hay checkpoint của writer.

## 8. Viết class suffix creator riêng

Khi naming convention có nhiều quy tắc, class riêng giúp dễ đọc và test:

~~~java
public class PaddedCsvSuffixCreator implements ResourceSuffixCreator {

    private final String prefix;
    private final int width;

    public PaddedCsvSuffixCreator(String prefix, int width) {
        this.prefix = prefix;
        this.width = width;
    }

    @Override
    public String getSuffix(int index) {
        return String.format(
                "%s%0" + width + "d.csv",
                prefix,
                index);
    }
}
~~~

Cấu hình:

~~~java
.resourceSuffixCreator(new PaddedCsvSuffixCreator("-part-", 4))
~~~

Với base resource **orders**, suffix creator này tạo **orders-part-0001.csv**, **orders-part-0002.csv**... Class nên giữ cấu hình bất biến và cho cùng index một suffix giống nhau.

Nếu prefix hoặc width lấy từ job parameter, hãy xác thực giá trị trước khi mở writer. Không cho phép dữ liệu đầu vào tự do chứa path separator hoặc chuỗi có thể làm file được tạo ngoài thư mục output dự kiến.

## 9. Suffix creator phải xác định và ổn định

Trong batch, một job có thể bị dừng rồi restart. Writer cần xác định lại resource tương ứng với index đã lưu. Vì vậy, suffix creator phải deterministic:

~~~java
index -> "-part-" + index + ".csv"
~~~

Với cùng một index, kết quả luôn giống nhau. Không nên đưa giá trị thay đổi theo từng lần gọi vào suffix:

~~~java
// Không nên: mỗi lần gọi tạo tên khác nhau.
index -> "-" + UUID.randomUUID() + ".csv"
~~~

Nếu suffix creator tạo tên ngẫu nhiên, restart có thể tìm hoặc tạo resource khác với file đang chứa dữ liệu đã commit. Hậu quả có thể là file bị phân mảnh, item trùng hoặc output không đầy đủ.

Timestamp hiện tại, số ngẫu nhiên và trạng thái mutable trong creator cũng có rủi ro tương tự. Nếu cần phân biệt lần chạy nghiệp vụ, hãy đưa output version hoặc business identity vào base resource một cách ổn định cho toàn bộ **JobInstance**, còn suffix chỉ biểu diễn index của resource trong instance đó.

## 10. Suffix index và thứ tự resource

Index được suffix creator nhận để tạo tên resource kế tiếp. Nó biểu diễn thứ tự resource do **MultiResourceItemWriter** tạo ra, không phải item index toàn cục và không phải số chunk.

Ví dụ:

- itemCountLimitPerResource = 1000.
- Resource đầu tiên chứa tối đa 1.000 item.
- Khi cần resource tiếp theo, writer yêu cầu suffix cho index kế tiếp.
- Resource mới nhận các item tiếp theo theo thứ tự chunk.

Không suy ra số item toàn job chỉ từ suffix nếu chunk cuối chưa đầy. Ví dụ 2.250 item với giới hạn 1.000 tạo ba resource, nhưng file cuối chỉ có 250 item.

Nếu downstream cần biết số item của từng file, hãy ghi manifest hoặc đếm trong bước kiểm tra sau khi writer hoàn tất. Tên file chỉ cung cấp thứ tự/identity, không tự cung cấp record count.

## 11. ItemCountLimitPerResource và rollover

Suffix được sử dụng khi writer chuyển sang resource mới. Điều kiện chuyển resource do **itemCountLimitPerResource** kiểm soát:

~~~java
.itemCountLimitPerResource(5000)
~~~

Giới hạn này là số item tối đa được ghi vào mỗi resource theo cơ chế của writer. Nó không phải chunk size:

| Cấu hình | Ý nghĩa |
|---|---|
| chunk(500, transactionManager) | Số item xử lý trong một chunk transaction |
| itemCountLimitPerResource(5000) | Giới hạn item cho một output resource |
| resourceSuffixCreator(...) | Quy tắc tên resource tiếp theo |

Ví dụ với chunk size 500 và resource limit 5.000, một file có thể nhận nhiều chunk. Khi đạt giới hạn, writer rollover sang file mới. Suffix creator chỉ được dùng khi tạo tên resource mới, không phải sau mỗi chunk.

Giới hạn item không bảo đảm giới hạn byte. Nếu record có độ dài rất khác nhau, file chứa 5.000 item có thể lớn hơn hoặc nhỏ hơn nhiều so với file khác. Nếu downstream giới hạn kích thước file theo byte, cần thiết kế writer khác hoặc cơ chế rollover dựa trên byte size.

## 12. Delegate writer và resource mới

**MultiResourceItemWriter** cần delegate có khả năng ghi vào resource được thay đổi theo từng file. Với file text, **FlatFileItemWriter** là delegate phổ biến vì hỗ trợ resource-aware writing và **ItemStream** lifecycle.

Ví dụ:

~~~java
FlatFileItemWriter<Order> delegate =
        new FlatFileItemWriterBuilder<Order>()
                .name("orderDelegate")
                .delimited()
                .names("orderId", "customerId", "amount")
                .build();
~~~

Delegate không nên được cấu hình với một resource cố định khác nếu wrapper phải quản lý resource. **MultiResourceItemWriter** gán resource cho delegate khi rollover. Nếu delegate tự ghi sang một file khác hoặc giữ file handle cũ, tên suffix của wrapper sẽ không còn phản ánh output thực tế.

Khi dùng custom delegate, hãy bảo đảm nó hỗ trợ **ResourceAwareItemWriterItemStream** hoặc contract tương thích mà wrapper yêu cầu trong phiên bản Spring Batch. Delegate cũng cần xử lý open/update/close và state đúng.

## 13. Header và footer trong từng file

Khi writer rollover, mỗi resource là một file riêng. Nếu delegate **FlatFileItemWriter** có header/footer callback, cần xác định chúng được áp dụng cho từng resource theo lifecycle mở/đóng delegate.

Ví dụ nếu mỗi file CSV phải có header:

~~~text
orders-part-001.csv:
orderId,customerId,amount
1001,C001,250.00
...

orders-part-002.csv:
orderId,customerId,amount
6001,C006,100.00
...
~~~

Header phải xuất hiện trong mỗi file nếu mỗi file là một tài liệu độc lập. Không giả định chỉ file đầu tiên có header. Hãy kiểm thử hành vi rollover của delegate trong phiên bản Spring Batch đang sử dụng.

Footer cũng có thể được ghi cho từng resource khi delegate đóng file. Nếu footer cần record count hoặc checksum của từng file, cần tính theo resource hiện tại và bảo đảm giá trị được hoàn tất trước khi file đóng.

## 14. Tên suffix không thay đổi nội dung file

Suffix creator chỉ tạo tên resource. Nó không thay đổi:

- Delimiter CSV.
- Encoding.
- Header/footer.
- Field mapping.
- Item order.
- Chunk size.
- Transaction boundary.
- Quy tắc skip/retry.

Nếu cần thay đổi định dạng theo file index, suffix creator không phải nơi phù hợp. Hãy cấu hình delegate hoặc thiết kế writer riêng cho từng loại output. Giữ naming và serialization thành hai trách nhiệm riêng giúp dễ kiểm thử hơn.

## 15. Tạo tên file có ngày nghiệp vụ

Có thể đặt ngày nghiệp vụ vào base resource và dùng suffix cho part index:

~~~java
String baseName = "orders-" + businessDate + "-tenant-" + tenantId;
Resource baseResource = new FileSystemResource(
        outputDirectory.resolve(baseName).toFile());

ResourceSuffixCreator suffixCreator =
        index -> String.format("-part-%03d.csv", index);
~~~

Kết quả ví dụ:

~~~text
orders-2026-11-15-tenant-42-part-001.csv
orders-2026-11-15-tenant-42-part-002.csv
~~~

Ngày và tenant nên lấy từ identifying job parameters hoặc output key đã được xác thực, để restart cùng instance tạo lại đúng base name. Không lấy ngày hiện tại trong mỗi lần gọi creator, vì job chạy qua nửa đêm hoặc restart vào ngày khác có thể tạo resource mới ngoài dự kiến.

Nếu ngày nghiệp vụ có thể chứa ký tự không an toàn cho filename, hãy format theo quy ước cố định như ISO date. Tenant identifier cũng nên được chuẩn hóa và xác thực.

## 16. Kết hợp base resource và suffix đúng cách

Hãy tính tên cuối trước khi cấu hình writer. Ví dụ:

| Tên mong muốn | Base resource | Suffix creator |
|---|---|---|
| orders.csv.1 | orders.csv | Mặc định .1 |
| orders-1.csv | orders | -1.csv |
| orders-part-001.csv | orders | -part-001.csv |
| orders-20261115-001.csv | orders-20261115 | -001.csv |
| tenant-42/orders-001.json | tenant-42/orders | -001.json |

Không nên ghép path separator tùy tiện trong suffix creator. Suffix thông thường chỉ nên thay đổi filename. Thư mục output nên được xác định ở base resource hoặc output directory đã được kiểm soát.

## 17. Tránh path traversal và tên file không hợp lệ

Nếu prefix/suffix được lấy từ job parameters hoặc dữ liệu bên ngoài, cần giới hạn ký tự cho phép. Không đưa raw user input vào đường dẫn:

~~~java
String suffix = request.getFileSuffix();
Path output = outputDirectory.resolve("orders" + suffix + ".csv");
~~~

Nếu suffix chứa **../**, path separator hoặc ký tự đặc biệt, file có thể được tạo ngoài thư mục dự kiến hoặc bị ghi đè file khác.

Nên:

- Chỉ chấp nhận pattern filename đã định nghĩa.
- Không cho suffix chứa **/**, **\\**, **:** hoặc path traversal segment.
- Chuẩn hóa path và xác nhận nó vẫn nằm trong output directory.
- Dùng thư mục riêng cho từng job instance.
- Kiểm tra collision bằng thao tác tạo resource an toàn, không chỉ kiểm tra tồn tại trước đó.

Suffix creator là thành phần nội bộ của ứng dụng, nhưng đầu vào cấu hình của nó vẫn cần được xác thực.

## 18. Không dùng timestamp ngẫu nhiên cho mỗi part

Tên file có timestamp có thể hữu ích cho output version, nhưng cần phân biệt timestamp của job với timestamp tạo part:

- Job timestamp/launch identity có thể được xác định một lần và dùng trong base resource.
- Part index cần ổn định theo thứ tự resource.
- Không sinh timestamp mới mỗi lần getSuffix(index) được gọi.

Ví dụ không tốt:

~~~java
index -> "-" + Instant.now() + "-" + index + ".csv"
~~~

Nếu writer gọi lại creator trong restart, cùng index có thể cho tên khác. Một cách tốt hơn là tính runKey một lần từ identifying parameters, dùng nó trong base resource, còn suffix chỉ là **-part-001.csv**.

## 19. Restart và suffix creator

**MultiResourceItemWriter** hỗ trợ lưu state qua **ItemStream**. Khi restart cùng **JobInstance**, writer cần biết resource index hiện tại và số item đã ghi vào resource đó. Suffix creator phải tái tạo đúng tên resource tương ứng với index đã lưu.

Để restart an toàn:

- Đặt tên wrapper writer ổn định bằng name(...).
- Bật saveState(true) nếu cần checkpoint.
- Giữ cùng base resource cho restart.
- Giữ cùng suffix creator và cấu hình của nó.
- Giữ cùng item count limit.
- Giữ cùng delegate name và cấu hình mapping.
- Không xóa/đổi tên các resource đã được ghi và commit.
- Giữ input data ổn định để checkpoint vẫn trỏ đúng item.

Nếu thay suffix format giữa lần chạy đầu và restart, writer có thể không tìm thấy resource cũ hoặc tạo một tên mới. Không nên đổi từ **.1** sang **-part-001.csv** giữa một **JobInstance** đang cần restart.

Khi cần đổi naming convention, hãy tạo output version hoặc job instance mới, hoặc triển khai migration rõ ràng cho output cũ. Không thay cấu hình writer tùy tiện trong lúc job đang dở dang.

## 20. JobInstance identity và base filename

Base resource thường nên phản ánh identity của output nghiệp vụ:

- Job name hoặc loại export.
- Ngày nghiệp vụ.
- Tenant hoặc partition key.
- Input snapshot/version.
- Output version/reprocess ID nếu cần.

Ví dụ:

~~~text
orders-2026-11-15-tenant-42-v1-part-001.csv
orders-2026-11-15-tenant-42-v1-part-002.csv
~~~

Các phần **2026-11-15**, **tenant-42**, **v1** được cố định cho một output identity. Part suffix thay đổi theo resource index.

Nếu base resource chỉ là **orders**, nhiều JobInstance có thể cùng tạo **orders-part-001.csv**, gây collision. Hãy tạo base resource riêng theo identifying parameters hoặc output key duy nhất đã được reserve.

Không dùng **JobExecution** ID làm identity duy nhất nếu restart tạo execution ID mới nhưng phải tiếp tục cùng resource. Có thể lưu execution ID trong manifest để audit, còn filename nên dựa trên identity ổn định của **JobInstance**.

## 21. Tránh ghi đè file cũ

Suffix creator tạo tên có thể xác định, nhưng không tự bảo vệ file khỏi bị ghi đè. Nếu một job mới dùng cùng base resource và cùng index, tên resource có thể trùng output đã có.

Các biện pháp:

- Base resource bao gồm output version hoặc business key.
- Dùng thư mục staging riêng theo job instance.
- Cấu hình delegate/writer không xóa file cũ ngoài chủ đích.
- Dùng reservation/manifest hoặc thao tác create-new để phát hiện collision.
- Chỉ publish sau khi mọi resource đã được ghi và xác minh.
- Không để downstream đọc các file staging chưa hoàn tất.

Với filesystem, có thể dùng thao tác tạo file mới chỉ khi chưa tồn tại trong bước prepare/reservation. Với object storage, dùng conditional create nếu provider hỗ trợ. Chỉ kiểm tra Files.exists() rồi mở file vẫn có race condition nếu hai job chạy đồng thời.

## 22. Multi-resource output và manifest

Khi một job tạo nhiều file, downstream cần biết tập file nào thuộc cùng một lần export và đã hoàn tất hay chưa. Một manifest có thể mô tả các resource:

~~~json
{
  "jobKey": "orders:2026-11-15:tenant-42:v1",
  "status": "PUBLISHED",
  "files": [
    {"name": "orders-2026-11-15-tenant-42-v1-part-001.csv", "records": 3000},
    {"name": "orders-2026-11-15-tenant-42-v1-part-002.csv", "records": 3000},
    {"name": "orders-2026-11-15-tenant-42-v1-part-003.csv", "records": 450}
  ]
}
~~~

Manifest nên được tạo sau khi writer đóng tất cả resource và các file đã được xác minh. Nó có thể lưu record count, byte size và checksum để consumer phát hiện file thiếu hoặc hỏng.

Suffix index giúp consumer sắp xếp các part, nhưng không thay thế manifest. Nếu file cuối không đầy hoặc job thất bại giữa chừng, consumer không thể biết tập resource nào hoàn chỉnh chỉ bằng cách nhìn một file đơn lẻ.

## 23. Header/footer và manifest không cùng vai trò

Header/footer thuộc nội dung từng file. Manifest mô tả tập file và trạng thái của cả lần export.

Ví dụ mỗi CSV có header:

~~~text
orderId,customerId,amount
1001,C001,250.00
~~~

Manifest có thể mô tả:

~~~json
{
  "jobKey": "orders:2026-11-15:v1",
  "status": "PUBLISHED",
  "parts": 3
}
~~~

Không nhét metadata tổng thể vào suffix. Tên file nên ngắn, ổn định và có thể parse; manifest là nơi phù hợp để lưu chi tiết về mỗi part.

## 24. ResourceSuffixCreator và multi-threading

Suffix creator nên stateless và thread-safe. Trong nhiều cấu hình, writer được gọi tuần tự theo chunk; tuy vậy, không nên dựa vào một mutable counter trong suffix creator để quyết định index.

Ví dụ không nên:

~~~java
public class StatefulSuffixCreator implements ResourceSuffixCreator {

    private int counter;

    @Override
    public String getSuffix(int ignored) {
        return "-" + (++counter) + ".csv";
    }
}
~~~

Counter riêng có thể không đồng bộ với resource index được lưu trong checkpoint. Khi restart, counter quay về 0 hoặc tiếp tục sai vị trí và tạo tên file trùng/khác dự kiến.

Nên dùng index mà writer truyền vào:

~~~java
public class IndexedSuffixCreator implements ResourceSuffixCreator {

    @Override
    public String getSuffix(int index) {
        return String.format("-part-%03d.csv", index);
    }
}
~~~

Cùng một index luôn tạo cùng một suffix. Không lưu state mutable trong creator trừ khi contract của ứng dụng thực sự yêu cầu và state đó được quản lý bền vững, đồng bộ với writer.

## 25. Kiểm thử suffix creator độc lập

Suffix creator là logic nhỏ, có thể unit test trực tiếp:

~~~java
class PaddedCsvSuffixCreatorTest {

    private final ResourceSuffixCreator creator =
            index -> String.format("-part-%03d.csv", index);

    @Test
    void createsPaddedSuffix() {
        assertEquals("-part-001.csv", creator.getSuffix(1));
        assertEquals("-part-009.csv", creator.getSuffix(9));
        assertEquals("-part-010.csv", creator.getSuffix(10));
        assertEquals("-part-125.csv", creator.getSuffix(125));
    }
}
~~~

Test nên bao gồm:

- Index đầu tiên theo convention của writer.
- Chuyển từ 9 sang 10 để xác nhận zero-padding.
- Index lớn hơn độ rộng tối thiểu.
- Prefix/suffix rỗng hoặc cấu hình không hợp lệ nếu class cho phép cấu hình.
- Cùng một index được gọi nhiều lần phải trả cùng kết quả.
- Không tạo path separator hoặc ký tự bị cấm.

Nếu dùng default creator, test có thể xác nhận naming convention mà ứng dụng downstream đang phụ thuộc. Tránh khóa test vào implementation detail không được contract yêu cầu.

## 26. Kiểm thử tên file thực tế qua MultiResourceItemWriter

Unit test creator không chứng minh wrapper thực sự ghép suffix với base resource như mong đợi. Cần test writer với resource tạm và item count limit nhỏ.

Ví dụ khung test:

~~~java
@TempDir
Path tempDir;

@Test
void createsExpectedPartNames() throws Exception {
    FlatFileItemWriter<Order> delegate =
            new FlatFileItemWriterBuilder<Order>()
                    .name("testOrderDelegate")
                    .delimited()
                    .names("orderId", "customerId")
                    .build();

    MultiResourceItemWriter<Order> writer =
            new MultiResourceItemWriterBuilder<Order>()
                    .name("testMultiWriter")
                    .resource(new FileSystemResource(
                            tempDir.resolve("orders").toFile()))
                    .delegate(delegate)
                    .itemCountLimitPerResource(2)
                    .resourceSuffixCreator(
                            index -> String.format("-part-%02d.csv", index))
                    .saveState(true)
                    .build();

    // Mở writer, ghi đủ item để tạo nhiều resource, cập nhật state và đóng.
    // Sau đó liệt kê tempDir và assert đúng tên file mong đợi.
}
~~~

Đây là khung minh họa; cần tạo các item, gọi lifecycle writer hoặc chạy qua step test theo API version của dự án. Với limit 2 và 5 item, dự kiến có ba resource: hai file đủ hai item và một file cuối có một item. Hãy xác nhận tên file thực tế và số item từng file bằng cách đọc lại output.

## 27. Kiểm thử extension và nội dung file

Test nên xác nhận:

- Extension nằm đúng vị trí cuối tên file.
- Không có extension lặp như **.csv.csv**.
- Tất cả resource có cùng naming convention.
- Resource index tăng theo thứ tự.
- Mỗi file có header nếu contract yêu cầu.
- File cuối có số item còn lại chính xác.
- Nội dung item không bị mất hoặc lặp khi rollover.

Không chỉ assert danh sách filename. Hãy đọc lại tất cả file, ghép business key và xác nhận tổng số item bằng số đầu vào; mỗi key xuất hiện đúng số lần mong đợi.

## 28. Kiểm thử restart với suffix creator

Test restart nên dùng cùng base resource, suffix creator, delegate name và item count limit như lần đầu:

1. Launch job và cho một số chunk commit.
2. Cố ý làm job thất bại sau khi một hoặc nhiều resource đã được tạo.
3. Lưu danh sách resource và nội dung đã commit.
4. Restart cùng **JobInstance**.
5. Xác nhận writer tiếp tục đúng resource/index theo checkpoint.
6. Xác nhận không tạo thêm tên file ngẫu nhiên cho cùng part.
7. Đọc lại toàn bộ part và xác nhận không thiếu hoặc trùng item.

Nếu đổi suffix creator hoặc base resource giữa lần chạy và restart, test nên chứng minh ứng dụng từ chối cấu hình không tương thích hoặc dùng output version mới. Không âm thầm tiếp tục một output đang dở với naming convention khác.

## 29. Kiểm thử hai job cùng tạo output

Hai **JobInstance** khác nhau có thể chạy cùng lúc. Nếu base resource giống nhau, cả hai có thể cố tạo cùng tên part:

~~~text
orders-part-001.csv
orders-part-002.csv
~~~

Test concurrency nên xác nhận:

- Mỗi instance có base path/output key riêng, hoặc
- Một instance giữ reservation và instance còn lại bị từ chối rõ ràng.

Suffix index chỉ duy nhất trong phạm vi một writer/instance; nó không tạo namespace toàn cục. Không coi **part-001** là unique giữa mọi job.

## 30. Suffix cho JSON/XML hoặc định dạng khác

Suffix creator chỉ thay đổi tên resource nên có thể áp dụng cho các delegate ghi định dạng khác, miễn delegate đáp ứng contract resource-aware của wrapper.

Ví dụ naming:

~~~text
orders-part-001.json
orders-part-002.json
orders-part-003.json
~~~

hoặc:

~~~text
orders-part-001.xml
orders-part-002.xml
~~~

Tuy nhiên, mỗi resource cần là một tài liệu hoàn chỉnh. Với JSON, mỗi file có thể cần là một array JSON hợp lệ; với XML, mỗi file cần có root element riêng. Hãy kiểm thử header/footer/document framing của delegate sau mỗi lần rollover.

## 31. Khi nào nên dùng suffix và khi nào nên dùng naming strategy khác?

**ResourceSuffixCreator** phù hợp khi:

- Tất cả file có cùng base name.
- Các part được đánh số tuần tự.
- Chỉ cần thêm hậu tố theo resource index.
- Quy tắc đặt tên đơn giản và deterministic.

Có thể cần custom wrapper hoặc writer khác khi:

- Tên file phụ thuộc vào dữ liệu item đầu tiên của mỗi resource.
- Cần rollover theo byte size thay vì item count.
- Mỗi resource có schema hoặc format khác nhau.
- Cần tạo thư mục con theo tenant hoặc partition động.
- Cần đặt tên dựa trên timestamp của từng cửa sổ dữ liệu.

Không nên cố đưa toàn bộ business logic vào suffix creator. Nó chỉ nhận index và trả chuỗi suffix; nếu naming cần thông tin mà interface không cung cấp, hãy chuẩn bị base resource từ job context hoặc chọn một abstraction phù hợp hơn.

## 32. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| File có tên orders.csv.1 thay vì orders-1.csv | Dùng suffix mặc định nối sau toàn bộ base filename | Dùng base không extension và custom suffix |
| File có .csv.csv | Extension đã nằm trong base và suffix | Tính tên cuối trước khi cấu hình |
| Tên part không ổn định khi restart | Suffix creator dùng UUID/timestamp/counter mutable | Dựa trên index writer truyền vào |
| Resource mới ghi sai thư mục | Suffix chứa path separator hoặc base path không được kiểm soát | Giữ suffix là filename fragment và validate path |
| Hai job ghi cùng part file | Base resource không phân biệt JobInstance | Đưa business identity/version vào base path |
| File part không có header | Delegate/header callback không được cấu hình theo lifecycle mỗi resource | Kiểm thử từng file sau rollover |
| File cuối thiếu/thừa item | Nhầm chunk size với item count limit | Kiểm tra itemCountLimitPerResource và đọc lại từng part |
| Restart tạo part trùng hoặc part mới sai | Suffix creator hoặc item limit thay đổi giữa restart | Giữ naming/config ổn định theo JobInstance |
| Downstream đọc thiếu file | Chỉ dò file theo pattern và không có manifest | Publish manifest sau khi xác minh toàn bộ resource |
| Test chỉ kiểm tra suffix creator | Chưa kiểm tra wrapper ghép suffix với base resource | Integration test MultiResourceItemWriter |
| Tên file sắp xếp sai | Index không zero-pad | Dùng format có độ rộng phù hợp |
| File cũ bị ghi đè | Cùng base/index được tái sử dụng | Dùng output version, reservation và staging |

## 33. Quy trình thiết kế tên file suffix

1. **Xác định contract tên file:** consumer cần extension, prefix, part number và thứ tự như thế nào?
2. **Chọn base resource:** chứa thư mục, job/business identity và phần tên chung.
3. **Chọn suffix creator:** dùng mặc định nếu .1, .2 phù hợp; nếu không, triển khai ResourceSuffixCreator.
4. **Quy định index format:** zero-padding, prefix và extension phải ổn định.
5. **Giữ creator deterministic:** cùng index luôn trả cùng suffix.
6. **Cấu hình rollover riêng:** đặt itemCountLimitPerResource, không nhầm với chunk size.
7. **Cấu hình delegate:** bảo đảm writer nhận resource mới và xử lý header/footer đúng.
8. **Thiết kế restart:** giữ base resource, creator, writer name và item limit ổn định.
9. **Bảo vệ output:** dùng base identity riêng, staging và collision detection.
10. **Tạo manifest:** ghi danh sách file, record count, checksum và trạng thái publish.
11. **Kiểm thử writer thực tế:** assert tên file, extension, số item, nội dung và restart.
12. **Kiểm thử concurrency:** xác nhận các JobInstance không chia sẻ cùng output namespace ngoài ý muốn.

## 34. Những nguyên tắc cần nhớ

- **MultiResourceItemWriter** chia output thành nhiều resource và dùng suffix creator khi tạo resource tiếp theo.
- **ResourceSuffixCreator** nhận resource index và trả về phần suffix được nối vào base resource.
- **SimpleResourceSuffixCreator** mặc định tạo suffix đánh số dạng .1, .2... theo convention của Spring Batch.
- Suffix được nối vào tên resource cơ sở; writer không tự di chuyển extension về cuối.
- Muốn **orders-part-001.csv**, có thể dùng base **orders** và suffix **-part-001.csv**.
- Dùng zero-padding nếu downstream cần sắp xếp file theo tên.
- Suffix creator phải deterministic và stateless; không dùng UUID, timestamp hiện tại hoặc mutable counter cho mỗi lần gọi.
- **itemCountLimitPerResource** quyết định rollover; chunk size quyết định transaction batch.
- Delegate cần hỗ trợ resource-aware writing và có lifecycle/state phù hợp.
- Header/footer thường cần được tạo cho từng file độc lập; kiểm tra bằng test rollover.
- Giữ base resource, suffix creator, writer name và item limit ổn định qua restart.
- Suffix index chỉ duy nhất trong phạm vi writer; base resource cần phân biệt output của các JobInstance.
- Suffix creator không ngăn ghi đè; cần staging, output version, reservation hoặc conditional create.
- Manifest giúp downstream biết toàn bộ part đã hoàn tất và xác minh được hay chưa.
- Kiểm thử cả tên file thực tế, nội dung, record count, restart và concurrency.

Tên file suffix là một phần của contract output trong batch job. Khi base resource biểu diễn đúng output identity, suffix creator tạo tên deterministic theo index và writer được kiểm thử qua rollover/restart, mỗi part file có tên ổn định, dễ sắp xếp và có thể được downstream tiêu thụ an toàn.
