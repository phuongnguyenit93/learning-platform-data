# Resource bị thiếu hoặc đổi tên

Trong Spring Batch, `MultiResourceItemReader<T>` thường được dùng để đọc một nhóm file theo pattern hoặc theo danh sách resource đã xác định. Trong suốt vòng đời Job, một file có thể chưa đến, bị xóa, bị di chuyển hoặc bị đổi tên. Những thay đổi này ảnh hưởng đến việc mở resource và đặc biệt nguy hiểm khi Job cần restart từ checkpoint.

Một vấn đề quan trọng là `MultiResourceItemReader` lưu tiến độ theo vị trí resource trong danh sách đã sắp xếp, còn delegate reader lưu tiến độ bên trong resource hiện tại. Nếu danh sách file thay đổi giữa lần chạy đầu và lần restart, resource index có thể trỏ đến file khác. Vì vậy, cần có chính sách rõ ràng cho file bắt buộc, file tùy chọn, file đến trễ và file bị đổi tên; đồng thời giữ ổn định tập resource trong suốt một JobInstance.

## 1. Các tình huống resource có thể bị thiếu hoặc đổi tên

Trong một batch nhập nhiều file, các tình huống thường gặp gồm:

- Pattern tìm file không khớp file nào vì upstream chưa gửi dữ liệu.
- Một file được liệt kê lúc chuẩn bị Job nhưng bị xóa trước khi reader mở nó.
- File đang được upstream ghi dở và chưa hoàn tất khi Job bắt đầu.
- File được đổi tên sau khi manifest hoặc pattern đã xác định resource.
- File được chuyển sang thư mục archive hoặc processing bởi một tiến trình khác.
- File bị thay thế bằng một nội dung mới nhưng vẫn giữ tên cũ.
- File hiện tại của checkpoint bị mất trước khi Job restart.
- Một file mới được thêm vào pattern và làm thay đổi thứ tự resource.

Các tình huống này không giống nhau. “Không có file nào trong batch” có thể là một batch rỗng hợp lệ hoặc lỗi đầu vào. “Một file bắt buộc bị mất” thường là lỗi nghiêm trọng. “File đến trễ” có thể là điều kiện chờ ở tầng orchestration. “File bị đổi tên” cần được xác định đó là thao tác publish bình thường hay thay đổi đầu vào sau khi Job đã bắt đầu.

## 2. MultiResourceItemReader và danh sách resource

`MultiResourceItemReader<T>` nhận một mảng `Resource`, sắp xếp chúng bằng comparator, sau đó lần lượt chuyển từng resource cho một delegate reader. Delegate đọc nội dung bên trong resource hiện tại.

```text
ResourcePatternResolver / Manifest
              |
              v
       Resource[] đầu vào
              |
              v
     MultiResourceItemReader
              |
       +------+------+
       |             |
       v             v
  Resource A     Resource B ...
       |             |
       v             v
  Delegate       Delegate
  FlatFile       FlatFile
  ItemReader     ItemReader
```

Có hai thời điểm khác nhau cần phân biệt:

1. **Resolve resource:** ứng dụng tìm file theo pattern hoặc đọc danh sách từ manifest và tạo `Resource[]`.
2. **Open resource:** khi reader chuyển đến một resource, delegate mới mở resource đó để đọc nội dung.

Một resource có thể tồn tại ở thời điểm resolve nhưng biến mất trước khi delegate mở nó. Vì vậy, chỉ kiểm tra kết quả `getResources(...)` chưa bảo đảm file vẫn tồn tại khi đọc.

## 3. Phân biệt strict của MultiResourceItemReader và delegate

`MultiResourceItemReader` và delegate reader có thể có cấu hình strict riêng, với mục đích khác nhau.

**Strict của MultiResourceItemReader** kiểm soát trường hợp danh sách resource rỗng. Khi `strict` được bật, reader báo lỗi nếu không có resource nào để đọc. Khi không strict, danh sách rỗng có thể được xem như không có item và reader kết thúc.

**Strict của delegate**, ví dụ `FlatFileItemReader`, kiểm soát việc resource cụ thể có tồn tại khi delegate mở nó hay không. Nếu file đã được resolve nhưng sau đó bị xóa, delegate strict sẽ báo lỗi khi mở file đó.

Ví dụ:

```java
@Bean
public FlatFileItemReader<Order> orderFileDelegate() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderFileDelegate")
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .strict(true)
            .saveState(true)
            .build();
}

@Bean
public MultiResourceItemReader<Order> multiOrderReader(
        Resource[] orderResources,
        FlatFileItemReader<Order> orderFileDelegate,
        Comparator<Resource> resourceComparator) {

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(orderResources)
            .delegate(orderFileDelegate)
            .comparator(resourceComparator)
            .strict(true)
            .saveState(true)
            .build();
}
```

Trong ví dụ, strict của multi-resource reader yêu cầu có ít nhất một resource. Strict của `FlatFileItemReader` yêu cầu file hiện tại phải tồn tại khi mở. Hai cấu hình này không thay thế nhau.

Tên builder/setter có thể khác theo phiên bản Spring Batch. Hãy kiểm tra API đúng với dependency của ứng dụng, nhưng luôn giữ rõ hai loại kiểm tra: danh sách rỗng và file cụ thể bị thiếu.

## 4. Khi nào danh sách resource rỗng là hợp lệ?

Không phải mọi Job đều cần ít nhất một file. Có những batch được phép hoàn tất khi không có dữ liệu, ví dụ ngày nghỉ không có giao dịch. Có những batch bắt buộc phải nhận file từ upstream và không có file là lỗi hợp đồng.

| Quy tắc nghiệp vụ | Chính sách phù hợp |
|---|---|
| Mỗi lần chạy phải có ít nhất một file | Bật strict ở MultiResourceItemReader hoặc kiểm tra đầu vào trước Step |
| Có thể không có file vào một số ngày | Cho phép danh sách rỗng và ghi nhận kết quả không có dữ liệu |
| File chưa đến nhưng sẽ đến sau | Chờ ở scheduler/orchestration rồi mới launch Job |
| Một file bắt buộc trong manifest bị thiếu | Fail trước khi xử lý hoặc fail khi mở delegate |
| File phụ là tùy chọn | Áp dụng chính sách optional riêng, ghi log/metric nếu thiếu |

Không nên dùng `strict(false)` chỉ để Job luôn xanh. Nếu danh sách rỗng là bất thường, việc bỏ qua sẽ che giấu lỗi upstream và tạo cảm giác batch đã xử lý thành công.

Nếu batch rỗng hợp lệ, nên ghi nhận rõ số resource bằng 0, số item bằng 0 và trạng thái nghiệp vụ phù hợp. Có thể dùng custom `ExitStatus` như `NO_INPUT` nếu flow hoặc dashboard cần phân biệt trường hợp này với một lần chạy đã đọc file nhưng file không có record.

## 5. Pattern không tìm thấy file

`ResourcePatternResolver` có thể trả về mảng rỗng khi pattern không khớp resource nào:

```java
Resource[] resources = resolver.getResources(
        "file:/var/batch/inbound/orders-*.csv"
);
```

Không nên giả định việc gọi `getResources(...)` sẽ luôn ném exception khi không tìm thấy file. Hãy kiểm tra số lượng resource và áp dụng chính sách rõ ràng:

```java
if (resources.length == 0) {
    throw new IllegalStateException(
            "No order files found for the requested batch"
    );
}
```

Nếu không có file là hợp lệ, có thể trả danh sách rỗng nhưng cần ghi nhận batch không có input. Nếu file phải đến trễ, đừng khởi chạy Job rồi kỳ vọng `MultiResourceItemReader` tự chờ file xuất hiện; reader không phải scheduler chờ input.

## 6. File bị xóa sau khi resolve

Một race condition thường gặp:

1. Job resolve pattern và nhận `orders-001.csv` cùng `orders-002.csv`.
2. Một tiến trình khác di chuyển `orders-002.csv` sang archive.
3. `MultiResourceItemReader` đọc xong file đầu tiên và chuyển sang file thứ hai.
4. Delegate cố mở resource cũ nhưng file không còn ở path đó.

Nếu delegate strict, Step thường thất bại khi mở file. Đây là hành vi phù hợp khi file thuộc manifest bắt buộc. Không nên âm thầm bỏ file chỉ vì file không còn tồn tại tại thời điểm mở.

Để giảm race condition, cần quy định quyền sở hữu file. Khi Job đã nhận batch, upstream không được xóa, đổi tên hoặc ghi đè file cho đến khi Job hoàn tất hoặc batch được giải phóng theo quy trình rõ ràng.

## 7. File đến trễ: chờ trước khi launch Job

Nếu file có thể đến trễ, xử lý thời gian chờ ở scheduler, orchestration service hoặc một bước kiểm tra đầu vào trước khi chạy Step đọc dữ liệu.

Một quy trình thường dùng:

```text
Scheduler nhận lịch chạy
        |
        v
Kiểm tra manifest / ready marker
        |
        +---- Chưa đủ file ----> Chờ / retry có giới hạn
        |                            |
        |                            +--> Kiểm tra lại
        |
        +---- Đã đủ file ------> Chốt danh sách đầu vào
                                     |
                                     v
                               Launch Job
                                     |
                                     v
                          MultiResourceItemReader
```

Không nên dùng một vòng lặp chờ vô hạn bên trong `read()` để liên tục kiểm tra filesystem. Cách đó giữ Step và tài nguyên mở trong thời gian dài, làm khó timeout, vận hành và restart.

Nếu cần chờ, hãy có timeout, số lần thử, khoảng cách retry, log và trạng thái cuối rõ ràng. Khi hết thời gian mà file vẫn thiếu, fail hoặc chuyển batch sang trạng thái chờ can thiệp tùy nghiệp vụ.

## 8. Ready marker và file ghi dở

Một pattern phổ biến là upstream ghi file vào tên tạm rồi đổi tên khi ghi xong:

```text
orders-20261115.csv.part   # đang ghi
orders-20261115.csv        # hoàn tất
```

Job chỉ tìm `orders-*.csv`, không tìm `*.part`. Việc rename trong cùng filesystem thường có thể thực hiện nguyên tử theo semantics của filesystem, giúp consumer không nhìn thấy file đích ở trạng thái ghi dở. Cần xác nhận behavior với filesystem/network storage thực tế.

Một cách khác là upstream tạo marker:

```text
orders-20261115.csv
orders-20261115.csv.ready
```

Job chỉ nhận file có marker `.ready`, hoặc manifest đánh dấu file đã hoàn tất. Marker cần được tạo sau khi dữ liệu file đã flush và đóng. Nếu marker và file có thể được publish không đồng bộ, cần kiểm tra kích thước/checksum hoặc quy trình hoàn tất của upstream.

Không dùng thời gian file không thay đổi trong vài giây làm bằng chứng duy nhất rằng file đã hoàn tất nếu upstream có thể tạm dừng ghi. Một ready marker hoặc manifest do upstream cam kết thường rõ ràng hơn.

## 9. File bị đổi tên

Đổi tên file làm thay đổi resource location mà reader đã được cấu hình. `Resource` thường giữ path/URL mà nó đại diện; nó không tự tìm file cùng nội dung ở tên mới.

Ví dụ:

```text
Tên đã resolve: /var/batch/inbound/orders-001.csv
Tên hiện tại:   /var/batch/inbound/orders-001-final.csv
```

Nếu file được đổi tên trước khi Job mở resource, path cũ không còn tồn tại và delegate có thể thất bại. Nếu file được đổi tên sau khi reader đã mở stream, hành vi phụ thuộc filesystem và cách stream được mở; không nên dựa vào việc stream cũ vẫn đọc được như một hợp đồng vận hành.

Khi file đổi tên hợp lệ trước khi Job launch, hãy cập nhật manifest hoặc cấu hình input để Job nhận đúng tên mới. Khi Job đã bắt đầu, không tự đổi tên file trong danh sách resource. Nếu cần đổi tên để claim file, thực hiện trước khi chốt manifest và lưu path/identity cuối cùng dùng cho Job.

## 10. Đổi tên file giữa lần chạy và restart

Đây là trường hợp nguy hiểm hơn. `MultiResourceItemReader` lưu resource index hiện tại và delegate lưu checkpoint bên trong resource. Nó không hiểu rằng `orders-001-old.csv` và `orders-001-new.csv` là cùng một file chỉ vì nội dung giống nhau.

Ví dụ lần chạy đầu:

```text
index 0 -> orders-A.csv
index 1 -> orders-B.csv
index 2 -> orders-C.csv

Checkpoint: index 1, đang ở giữa orders-B.csv
```

Trước restart, file được đổi tên hoặc danh sách pattern thay đổi:

```text
index 0 -> orders-A.csv
index 1 -> orders-C.csv
```

Index 1 hiện trỏ đến file C trong khi delegate state được lưu từ file B. Reader có thể mở sai file và áp dụng checkpoint cũ lên nội dung khác, gây bỏ sót hoặc đọc trùng dữ liệu.

Không xử lý rename giữa restart bằng cách chỉ giữ nguyên số lượng resource. Cần giữ nguyên danh sách, thứ tự và identity của từng resource trong suốt JobInstance.

## 11. Checkpoint của MultiResourceItemReader

Với `saveState(true)`, multi-resource reader lưu tiến độ ở cấp danh sách resource, còn delegate lưu vị trí bên trong resource hiện tại nếu delegate hỗ trợ `ItemStream`.

```text
Step ExecutionContext
   |
   +--> MultiResourceItemReader state
   |       +--> resource index hiện tại
   |
   +--> Delegate reader state
           +--> dòng/item đã đọc trong resource hiện tại
```

Khi restart, reader cần cùng resource list đã sắp xếp. Sau đó nó khôi phục index và mở lại delegate với resource tương ứng, rồi delegate khôi phục vị trí đọc trong file.

Điều này có nghĩa:

- Thêm file mới đứng trước file hiện tại có thể làm lệch resource index.
- Xóa file đã đọc có thể làm thay đổi index của file hiện tại.
- Đổi tên file có thể khiến resource cũ không tồn tại.
- Thay nội dung file tại cùng path có thể làm checkpoint trỏ vào dữ liệu khác.
- Thay comparator có thể thay đổi thứ tự resource.

Checkpoint chỉ đáng tin khi resource set, thứ tự và nội dung nguồn ổn định. Tên reader và delegate cũng cần ổn định để các key trong `ExecutionContext` được khôi phục đúng.

## 12. Manifest cố định danh sách resource

Với batch quan trọng, không nên resolve lại một glob rộng ở mỗi lần restart rồi hy vọng danh sách giống hệt lần đầu. Thay vào đó, tạo manifest cho batch trước khi launch Job.

Ví dụ manifest:

```json
{
  "batchId": "20261115-001",
  "files": [
    {
      "path": "/var/batch/staging/orders-001.csv",
      "sequence": 1,
      "size": 125000,
      "sha256": "..."
    },
    {
      "path": "/var/batch/staging/orders-002.csv",
      "sequence": 2,
      "size": 98000,
      "sha256": "..."
    }
  ]
}
```

Manifest xác định:

- Những file thuộc batch.
- Thứ tự nghiệp vụ của file.
- Path đã chốt sau khi claim/stage.
- Metadata để xác nhận file không bị thay đổi.
- Batch ID dùng làm identifying JobParameter hoặc khóa tra cứu manifest.

Khi restart, Job tải lại đúng manifest theo batch ID, không tìm mọi file hiện có trong thư mục. Có thể kiểm tra size/checksum trước khi mở reader để phát hiện file bị sửa hoặc thay thế.

Nếu manifest rất lớn, không nhất thiết đưa toàn bộ nội dung manifest vào `ExecutionContext`. Lưu manifest ở storage bền vững và chỉ lưu batch ID, version hoặc checksum tham chiếu trong JobParameters/metadata.

## 13. Claim file và thư mục processing

Một cách giảm việc upstream thay đổi file trong lúc Job chạy là chuyển file từ inbound sang thư mục processing trước khi launch.

```text
inbound/
  orders-001.csv
  orders-002.csv

       | claim batch
       v

processing/batch-20261115-001/
  orders-001.csv
  orders-002.csv
  manifest.json
```

Quy trình claim có thể là:

1. Xác nhận file đã hoàn tất bằng ready marker hoặc manifest.
2. Chọn tập file thuộc batch.
3. Di chuyển file sang thư mục processing riêng nếu filesystem hỗ trợ thao tác phù hợp.
4. Tạo manifest chứa path cuối cùng và metadata file.
5. Launch Job với batch ID/manifest ID.
6. Giữ file trong processing cho đến khi Job hoàn tất hoặc được xử lý phục hồi.
7. Sau thành công, chuyển file sang archive; khi thất bại, giữ lại để restart hoặc điều tra.

Việc claim cần tránh hai Job cùng nhận một file. Có thể dùng lock/lease, database trạng thái batch hoặc thao tác rename có tính nguyên tử trên filesystem. Với storage mạng hoặc object storage, cần dùng cơ chế claim phù hợp vì semantics rename có thể khác filesystem cục bộ.

## 14. Preflight kiểm tra tất cả resource trước khi đọc

Trước khi Step bắt đầu, có thể kiểm tra toàn bộ danh sách resource để phát hiện file thiếu sớm thay vì đọc nhiều file rồi mới thất bại ở file cuối.

Ví dụ:

```java
public void validateResources(Resource[] resources) {
    if (resources.length == 0) {
        throw new IllegalStateException("No input resources were supplied");
    }

    for (Resource resource : resources) {
        try {
            if (!resource.exists() || !resource.isReadable()) {
                throw new IllegalStateException(
                        "Input resource is missing or unreadable: "
                                + resource.getDescription());
            }
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot inspect input resource: " + resource.getDescription(), ex);
        }
    }
}
```

Preflight có thể chạy trong một validation service hoặc Tasklet trước Step đọc file. Nó giúp lỗi đầu vào xuất hiện sớm và có thông báo rõ ràng.

Tuy nhiên, `exists()` và `isReadable()` chỉ là kiểm tra tại một thời điểm. File vẫn có thể biến mất sau preflight. Cần kết hợp preflight với quyền sở hữu file, thư mục processing, manifest và delegate strict. Đây là một race condition kiểu time-of-check/time-of-use; kiểm tra trước không thay thế việc giữ nguồn ổn định.

## 15. Không tự động bỏ qua file bị thiếu

Một cách xử lý có vẻ tiện là đặt delegate `strict(false)` để nếu file không tồn tại thì reader bỏ qua. Điều này chỉ phù hợp khi nghiệp vụ xác định rõ file đó là tùy chọn và việc thiếu file được ghi nhận.

Rủi ro nếu bỏ qua âm thầm:

- Một phần dữ liệu batch bị mất nhưng Job vẫn báo hoàn tất.
- Báo cáo tổng hợp không khớp manifest.
- Các file phụ thuộc lẫn nhau bị xử lý thiếu.
- Restart có thể cho kết quả khác vì file xuất hiện ở lần sau.
- Vận hành không biết upstream đã vi phạm hợp đồng giao file.

Nếu file optional, nên có danh sách optional rõ ràng, ghi log/metric về file vắng mặt và quyết định Job `COMPLETED`, `COMPLETED_WITH_WARNINGS` hay cần review. Nếu file bắt buộc, fail rõ ràng để upstream có thể gửi lại hoặc vận hành can thiệp.

Không dùng `strict(false)` như một cơ chế retry chờ file đến. Delegate có thể xem file thiếu là không có dữ liệu và Step tiếp tục sang resource kế tiếp, trong khi file đáng lẽ phải xuất hiện sau đó.

## 16. Retry khi resource tạm thời chưa sẵn sàng

Có thể có lỗi tạm thời như file đang bị khóa, mount storage tạm thời mất kết nối hoặc quyền truy cập chưa được cập nhật. Cần phân loại lỗi:

| Tình huống | Hướng xử lý |
|---|---|
| File chưa đến theo lịch | Chờ ở scheduler/orchestration trước khi launch |
| File bị lock tạm thời | Retry có giới hạn hoặc chờ theo chính sách storage |
| File bị xóa vĩnh viễn | Fail và yêu cầu upstream gửi lại |
| Filename sai format | Fail validation; không retry vô hạn |
| File checksum khác manifest | Cách ly batch và điều tra |
| Storage outage tạm thời | Retry theo chính sách lỗi hạ tầng, có timeout |

Không phải mọi `FileNotFoundException` đều là lỗi tạm thời. Nếu path sai hoặc file đã bị xóa, retry liên tục chỉ làm Job thất bại muộn hơn. Retry cần có giới hạn, backoff và phân loại lỗi thực tế.

Với file đến trễ, thường tốt hơn là chưa launch Job cho đến khi manifest/ready marker xác nhận batch hoàn chỉnh. Nếu Job đã launch và fail vì file thiếu, restart chỉ có ý nghĩa sau khi file được phục hồi đúng path và đúng nội dung đã được chốt.

## 17. File optional và file bắt buộc

Một manifest có thể biểu diễn rõ file bắt buộc và tùy chọn:

```json
{
  "batchId": "20261115-001",
  "files": [
    { "path": "orders.csv", "required": true },
    { "path": "customer-notes.csv", "required": false }
  ]
}
```

Trước khi tạo `Resource[]`, validation service có thể:

- Fail nếu file `required=true` bị thiếu.
- Ghi nhận cảnh báo nếu file `required=false` bị thiếu.
- Chỉ đưa các resource hiện có và được phép vào reader.
- Lưu kết quả validation trong metadata của batch.

Không nên dựa vào một `MultiResourceItemReader` duy nhất để diễn đạt chính sách optional phức tạp nếu từng file có quy tắc khác nhau. Manifest/preflight là nơi thích hợp để quyết định resource nào được đưa vào danh sách.

## 18. File bị đổi tên hợp lệ trước khi Job bắt đầu

Nếu upstream có quy trình đổi tên file từ tên tạm sang tên chính thức trước khi Job chạy, hãy chỉ resolve file sau khi bước publish hoàn tất.

Ví dụ:

```text
orders-20261115.csv.uploading
             |
             | upload hoàn tất và đóng file
             v
orders-20261115.csv
             |
             | tạo manifest / ready marker
             v
Job nhận resource chính thức
```

Job nên nhận path cuối cùng trong manifest hoặc JobParameters. Không lưu path tạm trong metadata rồi kỳ vọng reader tự tìm path mới. Nếu cần giữ mối quan hệ giữa tên tạm và tên chính thức, manifest có thể lưu cả originalName và stagedPath để audit.

## 19. File bị đổi tên sau khi Job hoàn tất

Sau khi Job đã hoàn tất, có thể chuyển file từ processing sang archive hoặc đổi tên để biểu diễn trạng thái đã xử lý. Việc này nên nằm trong bước hoàn tất/publish riêng, sau khi xác nhận JobExecution thành công và dữ liệu đầu ra đã được commit.

Không di chuyển file ngay khi reader đọc xong file cuối cùng nhưng trước khi Step commit chunk cuối. Nếu writer thất bại hoặc transaction rollback, Job có thể cần restart nhưng resource đã biến mất khỏi path cũ.

Một quy trình an toàn hơn:

1. Step đọc và ghi dữ liệu hoàn tất.
2. JobExecution/StepExecution được xác nhận thành công.
3. Bước archive chuyển file từ processing sang archive.
4. Ghi trạng thái archive vào manifest hoặc batch table.

Nếu archive thất bại, có thể retry thao tác archive riêng mà không phải đọc lại dữ liệu nghiệp vụ. Hãy làm thao tác archive idempotent: nếu file đã ở archive đúng vị trí, lần chạy lại cần nhận diện trạng thái đó.

## 20. Path cũ và path mới: không tự đoán bằng filename gần giống

Khi file cũ bị thiếu, không nên quét thư mục rồi chọn file có tên gần giống hoặc file mới nhất để thay thế. Hai file có thể thuộc batch khác nhau hoặc chứa dữ liệu khác nhau.

Ví dụ không an toàn:

```java
// Không nên: tự chọn file mới nhất làm thay thế cho input bị thiếu.
File candidate = findNewestFile("orders-*.csv");
```

Thay vào đó, dùng định danh batch/file đã được upstream cung cấp:

- Batch ID.
- File ID hoặc sequence.
- Manifest version.
- Checksum hoặc content hash.
- Original path và staged path đã được ghi nhận.

Nếu upstream thông báo rename, cập nhật manifest theo quy trình có kiểm soát trước khi launch Job mới. Với Job đã có checkpoint, chỉ cho phép thay path nếu có thể chứng minh file mới chính là cùng nội dung/identity và thứ tự resource vẫn giữ nguyên; nếu không, tạo batch execution mới theo quy tắc nghiệp vụ.

## 21. Tác động của comparator và danh sách resource

Ngay cả khi file không bị thiếu, một file mới được thêm vào pattern cũng có thể làm thay đổi thứ tự resource. Ví dụ:

```text
Lần đầu:
  0 -> orders-002.csv
  1 -> orders-003.csv

Restart:
  0 -> orders-001.csv  # file mới đến
  1 -> orders-002.csv
  2 -> orders-003.csv
```

Checkpoint index 1 ban đầu là `orders-003.csv`, nhưng sau khi danh sách thay đổi index 1 lại là `orders-002.csv`. Vì vậy, cần giữ ổn định cả:

- Resource list.
- Comparator và các tiêu chí tie-breaker.
- Filename/path hoặc định danh resource.
- Nội dung file.
- Tên reader và delegate.

Nếu danh sách được lấy từ glob, không nên re-resolve glob trên thư mục inbound có file mới liên tục khi restart. Dùng manifest hoặc thư mục staging riêng cho batch.

## 22. Phân biệt missing resource với empty file

File không tồn tại và file tồn tại nhưng không có record là hai trường hợp khác nhau:

| Trạng thái | Ý nghĩa |
|---|---|
| Không có resource trong danh sách | Pattern/manifest không cung cấp file nào |
| Resource được liệt kê nhưng file đã mất | Đầu vào bị thay đổi hoặc lỗi storage |
| File tồn tại nhưng 0 byte | Có file nhưng không có nội dung |
| File chỉ có header | Có schema nhưng không có record |
| File có record nhưng tất cả bị filter | Có dữ liệu đầu vào nhưng không có item đầu ra |

Không nên gộp mọi trường hợp thành “zero items”. Với file bắt buộc, file 0 byte có thể là lỗi. Với file optional, file rỗng có thể hợp lệ. Với CSV có header, file chỉ có header có thể biểu thị không có giao dịch. Chính sách cần theo hợp đồng dữ liệu.

Preflight có thể kiểm tra kích thước file, header và checksum. Delegate reader vẫn cần xử lý đúng EOF và parse lỗi khi đọc.

## 23. Observability và thông báo lỗi

Khi resource thiếu hoặc đổi tên, log nên cung cấp đủ thông tin để vận hành biết batch nào bị ảnh hưởng:

- Job name và JobExecution ID.
- Batch ID/manifest ID.
- Resource path hoặc resource description.
- File sequence hoặc business date.
- Resource index hiện tại nếu có.
- Expected checksum/size và actual metadata nếu kiểm tra được.
- Lỗi phát sinh ở giai đoạn resolve, preflight, open, read hay archive.
- Số lần retry và kết quả cuối.

Không log dữ liệu nhạy cảm trong file. Có thể ghi filename, file ID và checksum để đối soát mà không ghi toàn bộ nội dung.

Metric hữu ích gồm số resource dự kiến, số resource tìm thấy, số resource bị thiếu, số file bị quarantine, số lần retry open và số batch chờ input. Những metric này giúp phân biệt upstream chưa gửi file với lỗi reader.

## 24. Kiểm thử resource bị thiếu hoặc đổi tên

Nên kiểm thử từng giai đoạn thay vì chỉ kiểm tra Job có `FAILED` hay không:

1. Pattern không khớp file nào và strict của MultiResourceItemReader được bật.
2. Pattern không khớp file nào nhưng batch cho phép empty input.
3. Resource được resolve thành công nhưng bị xóa trước khi delegate mở.
4. Delegate strict bật và báo lỗi khi file cụ thể không tồn tại.
5. Delegate strict tắt theo chính sách optional và kết quả được ghi nhận rõ.
6. File đang có đuôi `.part` không bị pattern chính thức chọn.
7. File được rename sang tên chính thức trước khi manifest được chốt.
8. File bị rename sau khi Job đã bắt đầu và restart được kiểm tra.
9. Thêm file mới đứng trước resource index checkpoint để xác nhận manifest ngăn danh sách thay đổi.
10. Thay nội dung file tại cùng path để xác nhận checksum/version phát hiện thay đổi.
11. Job fail giữa resource thứ hai rồi restart với cùng resource list và thứ tự.
12. Archive file sau thành công có thể retry mà không làm thay đổi kết quả dữ liệu.

Integration test restart cần giữ JobRepository và ExecutionContext giữa hai lần chạy. Dùng file fixture trong thư mục tạm để mô phỏng xóa, rename và thay nội dung một cách có kiểm soát.

## 25. Những lỗi thiết kế thường gặp

**Cho rằng strict của MultiResourceItemReader kiểm tra mọi file.** Strict của multi-resource reader chủ yếu xử lý danh sách rỗng; strict của delegate kiểm tra resource cụ thể khi mở.

**Để strict=false và coi file bắt buộc bị thiếu là bình thường.** Job có thể hoàn tất với dữ liệu thiếu. Chỉ dùng chế độ không strict khi optional input được định nghĩa rõ.

**Chờ file đến bằng vòng lặp vô hạn trong read().** Cách đó giữ Step và tài nguyên mở. Chờ ở scheduler/orchestration với timeout và retry có giới hạn.

**Resolve lại glob trên thư mục đang thay đổi khi restart.** Danh sách và resource index có thể lệch. Chốt manifest hoặc staging directory.

**Tự chọn file gần giống khi tên cũ biến mất.** Có thể đọc nhầm batch. Dùng file ID, manifest và checksum.

**Di chuyển file trước khi Step commit xong.** Restart có thể không mở lại được resource. Archive sau khi Job/Step thành công.

**Chỉ kiểm tra exists() một lần.** File vẫn có thể biến mất sau preflight. Kết hợp kiểm tra với quyền sở hữu và cơ chế claim.

**Coi file 0 byte giống file không tồn tại.** Hai trường hợp có ý nghĩa nghiệp vụ khác nhau; xác định chính sách riêng.

## 26. Cách thiết kế xử lý resource thiếu hoặc đổi tên

Trước khi launch Job, hãy xác định batch cần những file nào và file nào optional. Chờ upstream hoàn tất việc ghi, kiểm tra ready marker/manifest, claim file vào thư mục processing và chốt resource list theo một batch ID. Validate path, tồn tại, quyền đọc, naming convention, kích thước và checksum nếu cần.

Khi cấu hình reader, bật strict ở `MultiResourceItemReader` nếu danh sách rỗng là lỗi và bật strict ở delegate nếu từng file là bắt buộc. Chỉ cho phép bỏ qua resource khi chính sách optional đã rõ và việc thiếu file được ghi nhận. Đặt comparator, tên reader và tên delegate ổn định.

Khi restart, nạp lại đúng manifest và đúng thứ tự resource đã dùng lần đầu. Không tự tìm file thay thế bằng tên gần giống, không thêm file mới vào danh sách của JobInstance cũ và không đổi tên/di chuyển file đang được xử lý. Sau khi Job hoàn tất, archive file bằng một bước riêng có thể retry.

`MultiResourceItemReader` có thể quản lý nhiều file và checkpoint của chúng, nhưng không thể tự giải quyết thay đổi bên ngoài filesystem. Một quy trình manifest, claim, preflight, strict policy và archive rõ ràng giúp Job phân biệt đầu vào thiếu, file đến trễ và file bị đổi tên; đồng thời giữ cho restart tiếp tục đúng resource và đúng dữ liệu.
