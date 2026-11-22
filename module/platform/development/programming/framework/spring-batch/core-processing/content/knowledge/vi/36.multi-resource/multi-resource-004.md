# Lưu resource hiện tại trong checkpoint

Khi một Spring Batch Step đọc nhiều file hoặc nhiều resource, reader phải biết mình đang ở resource nào để có thể tiếp tục đúng vị trí sau khi Job restart. `MultiResourceItemReader` hỗ trợ việc này bằng cách lưu vị trí resource hiện tại vào `ExecutionContext`. Reader delegate bên trong, chẳng hạn `FlatFileItemReader`, lưu thêm vị trí đọc bên trong resource đó.

Checkpoint vì vậy có hai phần liên quan: **index của resource hiện tại trong danh sách resource** và **state của delegate trong resource hiện tại**. Khi restart, Spring Batch mở lại cùng danh sách resource, chuyển đến resource đã lưu và khôi phục vị trí đọc của delegate. Cơ chế này chỉ đáng tin cậy khi danh sách resource, thứ tự sắp xếp, nội dung file và tên reader được giữ ổn định qua các lần chạy.

## 1. Vấn đề khi đọc nhiều resource

Giả sử một Job đọc các file giao dịch theo ngày:

```text
transactions-2026-11-13.csv
transactions-2026-11-14.csv
transactions-2026-11-15.csv
transactions-2026-11-16.csv
```

Mỗi file chứa nhiều record. `MultiResourceItemReader` điều phối một delegate reader để đọc lần lượt từng file như một luồng item liên tục.

```text
MultiResourceItemReader
        |
        +--> Resource 0: transactions-2026-11-13.csv
        |       |
        |       +--> FlatFileItemReader đọc từng dòng
        |
        +--> Resource 1: transactions-2026-11-14.csv
        |       |
        |       +--> FlatFileItemReader đọc từng dòng
        |
        +--> Resource 2: transactions-2026-11-15.csv
        |       |
        |       +--> FlatFileItemReader đọc từng dòng
        |
        +--> Resource 3: transactions-2026-11-16.csv
                |
                +--> FlatFileItemReader đọc từng dòng
```

Nếu process bị dừng khi đang đọc file thứ ba, lần restart phải biết:

- File thứ ba là resource nào trong danh sách đã chọn.
- Delegate đã đọc đến dòng/record nào trong file đó tại checkpoint cuối cùng.
- Các file trước đã hoàn tất và không cần đọc lại từ đầu.
- Những file còn lại vẫn thuộc cùng input set của JobInstance.

Chỉ lưu số dòng hiện tại mà không lưu resource index là chưa đủ, vì dòng 500 có thể tồn tại trong nhiều file. Ngược lại, chỉ lưu resource index mà không lưu vị trí bên trong file cũng chưa đủ để tiếp tục chính xác.

## 2. MultiResourceItemReader lưu điều gì?

`MultiResourceItemReader<T>` là một `ItemStreamReader<T>` điều phối nhiều `Resource` và một delegate có khả năng đọc từng resource. Khi lưu state, reader ghi vị trí resource hiện tại vào `ExecutionContext`. Delegate cũng được mở, cập nhật và đóng theo vòng đời của từng resource; state của delegate giúp khôi phục vị trí bên trong file hiện tại.

Có thể hình dung checkpoint như sau:

```text
ExecutionContext
  |
  +-- multiOrderReader.resourceIndex = 2
  |
  +-- orderFileDelegate.currentItemCount = 451
  |
  +-- ...các state khác của delegate/Step
```

Tên key cụ thể được Spring Batch tạo dựa trên tên reader và implementation/version. Ví dụ trên chỉ minh họa ý nghĩa, không phải hợp đồng key để ứng dụng tự ghi hoặc sửa trực tiếp.

Hai phần state có vai trò khác nhau:

| Thành phần | State được khôi phục | Trách nhiệm |
|---|---|---|
| `MultiResourceItemReader` | Index resource hiện tại trong danh sách | Chọn đúng file để tiếp tục. |
| Delegate reader | Vị trí đọc bên trong resource hiện tại | Tiếp tục từ checkpoint của file đó. |

Reader ngoài không serialize toàn bộ đối tượng `Resource` vào checkpoint. Nó lưu vị trí trong danh sách resource. Vì vậy, cùng một index phải tiếp tục trỏ đến cùng một file sau restart; danh sách và thứ tự resource không được thay đổi ngoài dự kiến.

## 3. Vai trò của ExecutionContext

`ExecutionContext` là vùng lưu state có thể được Spring Batch persist trong JobRepository. Các component triển khai `ItemStream` sử dụng ba callback chính:

- `open(ExecutionContext)`: đọc state đã lưu và khôi phục hoạt động.
- `update(ExecutionContext)`: ghi state hiện tại vào context tại điểm checkpoint.
- `close()`: giải phóng resource khi vòng đời reader kết thúc bình thường.

`MultiResourceItemReader` và delegate đều tham gia lifecycle này. Trong một chunk Step, framework gọi cập nhật state của stream trong quy trình commit chunk. Khi metadata được commit, checkpoint trở thành điểm khôi phục cho lần restart.

Không nên tự thêm một key index song song vào Job ExecutionContext rồi cố điều khiển reader nếu `MultiResourceItemReader` đã quản lý state của nó. Việc ghi đè key nội bộ có thể khiến reader mở sai file hoặc delegate khôi phục sai vị trí. Hãy cấu hình `name`, `saveState` và resource list đúng cách để reader tự quản lý checkpoint.

## 4. Cấu hình MultiResourceItemReader với FlatFileItemReader

Ví dụ Spring Batch 5 đọc nhiều file CSV có cùng schema. JobParameter `input.pattern` chứa resource pattern như `file:/data/in/transactions-*.csv`.

```java
@Bean
@StepScope
MultiResourceItemReader<TransactionRecord> transactionReader(
        ResourcePatternResolver resolver,
        @Value("#{jobParameters['input.pattern']}") String inputPattern)
        throws IOException {

    Resource[] resources = resolver.getResources(inputPattern);

    Arrays.sort(resources,
            Comparator.comparing(Resource::getFilename,
                    Comparator.nullsLast(String::compareTo)));

    FlatFileItemReader<TransactionRecord> delegate =
            new FlatFileItemReaderBuilder<TransactionRecord>()
                    .name("transactionFileDelegate")
                    .delimited()
                    .names("transactionId", "accountId", "amount")
                    .targetType(TransactionRecord.class)
                    .saveState(true)
                    .build();

    return new MultiResourceItemReaderBuilder<TransactionRecord>()
            .name("multiTransactionReader")
            .resources(resources)
            .delegate(delegate)
            .saveState(true)
            .strict(true)
            .build();
}
```

Các điểm quan trọng:

- `multiTransactionReader` có tên ổn định để lưu resource index.
- `transactionFileDelegate` có tên ổn định để lưu vị trí đọc bên trong file.
- `saveState(true)` được bật ở cả reader ngoài và delegate.
- `ResourcePatternResolver` tìm tập file theo pattern.
- Danh sách được sắp xếp tường minh trước khi reader sử dụng.
- Delegate được cấu hình mà không gắn cứng vào một file; `MultiResourceItemReader` gán resource hiện tại cho delegate khi chuyển file.
- `strict(true)` giúp báo lỗi khi không tìm thấy resource theo cấu hình strict của reader.

Trong ví dụ, `ResourcePatternResolver` và `Resource` thuộc Spring Core; `MultiResourceItemReaderBuilder` và `FlatFileItemReaderBuilder` thuộc Spring Batch. Các import domain, `Arrays`, `Comparator` và `IOException` được bổ sung theo ứng dụng.

Nếu input file cần được truyền bằng danh sách manifest thay vì wildcard, có thể resolve manifest thành `Resource[]` rồi truyền cùng cách. Điều quan trọng là danh sách phải được tái tạo giống hệt khi restart.

## 5. Vì sao cả reader ngoài và delegate đều phải lưu state?

`MultiResourceItemReader` quản lý vị trí trong danh sách file. Delegate quản lý vị trí bên trong file. Chỉ bật state ở một trong hai tầng có thể làm checkpoint không đầy đủ.

| MultiResourceItemReader | Delegate | Hệ quả |
|---|---|---|
| `saveState(true)` | `saveState(true)` | Lưu được resource index và vị trí trong resource. |
| `saveState(false)` | `saveState(true)` | Không có index đáng tin cậy để chọn file khi restart. |
| `saveState(true)` | `saveState(false)` | Có thể chọn lại đúng file nhưng delegate không có vị trí để tiếp tục bên trong file. |
| `saveState(false)` | `saveState(false)` | Không có checkpoint reader đầy đủ; thường phải đọc lại từ đầu theo cấu hình. |

Để restart đúng, hãy bật state ở reader ngoài và delegate, đồng thời bảo đảm delegate triển khai `ItemStreamReader`/`ItemStream` và có khả năng khôi phục vị trí. `FlatFileItemReader` là một delegate thường dùng cho trường hợp này.

## 6. Resource index không phải tên file

Giả sử danh sách sau được dùng ở lần đầu:

| Index | Resource |
|---:|---|
| 0 | `transactions-01.csv` |
| 1 | `transactions-02.csv` |
| 2 | `transactions-03.csv` |

Checkpoint lưu `resourceIndex = 2`. Nếu trước lần restart, file `transactions-00.csv` mới được thêm vào đầu danh sách và danh sách được sort lại, index 2 có thể trỏ sang `transactions-02.csv`. Reader khi đó mở sai file mặc dù metadata index vẫn hợp lệ về mặt số học.

Vì vậy, resource index chỉ có ý nghĩa khi danh sách resource ổn định. Không nên coi index là định danh bền vững của file trên filesystem.

Để giữ danh sách ổn định:

- Tạo manifest input một lần cho JobInstance.
- Lưu danh sách đường dẫn/URI theo thứ tự đã chọn vào metadata bền vững.
- Giữ nguyên thứ tự comparator giữa lần đầu và restart.
- Không thêm hoặc xóa file trong thư mục input của Job đang chạy.
- Kiểm tra checksum/size/version để xác nhận file không bị thay thế.
- Nếu tập resource thay đổi, tạo JobInstance mới với định danh nghiệp vụ phù hợp thay vì âm thầm dùng checkpoint cũ.

## 7. Sắp xếp resource một cách xác định

`MultiResourceItemReader` có comparator để xác định thứ tự resource. Nên cấu hình comparator tường minh nếu thứ tự có ý nghĩa nghiệp vụ.

Ví dụ sắp xếp theo tên file:

```java
Comparator<Resource> resourceComparator =
        Comparator.comparing(Resource::getFilename,
                Comparator.nullsLast(String::compareTo));

return new MultiResourceItemReaderBuilder<TransactionRecord>()
        .name("multiTransactionReader")
        .resources(resources)
        .delegate(delegate)
        .comparator(resourceComparator)
        .saveState(true)
        .build();
```

Không phụ thuộc vào thứ tự filesystem trả về từ wildcard hoặc directory listing. Thứ tự có thể khác giữa hệ điều hành, filesystem, storage provider hoặc lần chạy.

Nếu tên file có số thứ tự, cần tránh sort từ điển gây thứ tự bất ngờ:

```text
batch-1.csv
batch-10.csv
batch-2.csv
```

Sort từ điển có thể xếp `batch-10.csv` trước `batch-2.csv`. Nếu cần thứ tự số, parse sequence number và dùng comparator theo số, hoặc dùng tên zero-padded như `batch-001.csv`, `batch-002.csv`.

Comparator dùng khi restart phải giống comparator ban đầu. Thay đổi quy tắc sort trong một lần deploy có thể khiến index checkpoint trỏ sang resource khác.

## 8. Delegate lưu vị trí bên trong file như thế nào?

Với `FlatFileItemReader`, delegate lưu tiến độ đọc của file hiện tại trong `ExecutionContext`. Khi mở lại cùng reader bằng context đã lưu, nó khôi phục vị trí đọc thay vì luôn bắt đầu từ dòng đầu.

Ví dụ một file:

```text
transactionId,accountId,amount
T001,A001,100.00
T002,A002,200.00
T003,A003,300.00
T004,A004,400.00
T005,A005,500.00
```

Nếu checkpoint được commit sau khi đọc `T003`, lần restart trên resource đó tiếp tục từ record kế tiếp theo state của delegate. Resource index cho biết đây là file nào; delegate checkpoint cho biết vị trí nào trong file.

Không tự lưu `BufferedReader`, `InputStream`, file handle hoặc object parser vào ExecutionContext. Context cần chứa dữ liệu state nhỏ, có thể lưu/khôi phục. Delegate reader chịu trách nhiệm chuyển state nội bộ của nó thành các giá trị checkpoint phù hợp.

## 9. Checkpoint được cập nhật theo chunk commit

Reader có thể đọc trước nhiều item để tạo chunk. Checkpoint bền vững tương ứng với ranh giới commit mà Spring Batch quản lý, không đơn giản là vị trí cuối cùng đã được gọi `read()` trong bộ nhớ.

Ví dụ chunk size là 100:

```text
Đọc item 1..100
        |
        v
Processor + Writer
        |
        v
update ExecutionContext
        |
        v
Commit chunk và metadata
```

Nếu chunk tiếp theo bị lỗi và rollback, checkpoint của chunk chưa commit không trở thành điểm restart đã commit. Khi restart, reader khôi phục từ checkpoint cuối cùng đã commit; một số item đã đọc trong chunk lỗi có thể được đọc lại.

Đây là lý do writer cần idempotent hoặc tham gia transaction phù hợp, nhất là khi có side effect ngoài database. Không được coi vị trí đọc trong memory là bằng chứng rằng item đã được ghi bền vững.

## 10. Ví dụ trạng thái checkpoint qua nhiều resource

Giả sử có ba file, mỗi file có 1.000 record và chunk size là 100. Job đã hoàn thành file 1, hoàn thành 400 record file 2 và đang xử lý file 2:

```text
Resource 0: file-01.csv  [1,000 records committed]
Resource 1: file-02.csv  [400 records committed | next records ...]
Resource 2: file-03.csv  [not started]

Checkpoint concept:
  current resource index = 1
  delegate position       = after committed record 400
```

Nếu process bị kill, restart chọn lại resource index 1, rồi delegate khôi phục vị trí bên trong `file-02.csv`. Khi file 2 kết thúc, reader tiếp tục sang file 3.

Index và delegate position được cập nhật theo checkpoint của chunk. Không cần lưu một bản sao toàn bộ nội dung file vào ExecutionContext.

## 11. Chuyển resource và checkpoint

Khi delegate đọc đến EOF của resource hiện tại, `MultiResourceItemReader` chuyển sang resource kế tiếp và gán resource mới cho delegate. Delegate được mở lại cho resource đó với state khởi đầu thích hợp.

Ví dụ:

```text
file-01.csv: đọc đến EOF
       |
       v
currentResource++
       |
       v
delegate.setResource(file-02.csv)
       |
       v
delegate.open(new state for this resource)
       |
       v
đọc item đầu tiên của file-02.csv
```

Khi Step cập nhật checkpoint, reader ngoài lưu index resource đang xử lý và delegate lưu tiến độ của resource đó. Nếu chunk đi qua ranh giới giữa hai file, checkpoint cần phản ánh resource/position tương ứng với item cuối cùng thuộc chunk đã commit.

Không tự thay đổi resource hiện tại trong lúc Step đang chạy. `MultiResourceItemReader` quản lý việc chuyển file; thay đổi mảng resource hoặc gọi `setResource` từ code nghiệp vụ có thể phá vỡ state và restart.

## 12. Giữ resource list ổn định bằng manifest

Với input pattern như `file:/data/in/*.csv`, số lượng file có thể thay đổi giữa hai lần chạy. Một cách chắc chắn hơn là chốt danh sách input khi tạo JobInstance.

Manifest có thể chứa:

```json
{
  "jobInstanceKey": "daily-transactions-2026-11-15",
  "resources": [
    {
      "sequence": 1,
      "path": "file:/data/in/transactions-01.csv",
      "size": 125004,
      "checksum": "sha256:..."
    },
    {
      "sequence": 2,
      "path": "file:/data/in/transactions-02.csv",
      "size": 138902,
      "checksum": "sha256:..."
    }
  ]
}
```

Job có thể đọc manifest để tái tạo đúng `Resource[]` theo sequence. Nếu resource không còn tồn tại hoặc checksum thay đổi, nên dừng và yêu cầu xử lý input thay vì dùng index cũ trên một danh sách khác.

Manifest có thể được lưu trong object storage, database hoặc file bền vững. Nếu lưu đường dẫn manifest trong JobParameters, hãy giữ identifying/non-identifying semantics phù hợp và không tạo manifest mới khi restart cùng JobInstance.

## 13. Wildcard pattern và resource discovery

Wildcard hữu ích để tìm nhiều file:

```java
Resource[] resources = resolver.getResources(
        "file:/data/in/transactions-*.csv");
```

Nhưng kết quả wildcard là một snapshot tại thời điểm resolve. Nếu file mới xuất hiện sau khi Job bắt đầu, lần restart có thể nhận danh sách khác nếu resolver chạy lại.

Các lựa chọn:

- Chốt resource list và lưu manifest trước khi launch Job.
- Copy input vào thư mục staging riêng theo JobInstance rồi đọc từ đó.
- Dùng một batch membership table chứa chính xác các file thuộc Job.
- Dùng identifying parameter đại diện cho input set/version.
- Kiểm tra input list/checksum trước khi mở reader khi restart.

Không để producer tiếp tục ghi vào cùng thư mục wildcard trong lúc consumer Batch đang đọc, trừ khi có giao thức handoff rõ ràng. File chưa hoàn tất có thể bị đưa vào resource list và làm reader parse dữ liệu dở dang.

## 14. Lưu tên resource hiện tại cho log hoặc audit

`MultiResourceItemReader` quản lý resource index trong checkpoint, nhưng code nghiệp vụ có thể cần tên file hiện tại để ghi log, audit hoặc đưa vào reject record. Không nên đọc key nội bộ của reader bằng một tên hardcode không được API bảo đảm.

Một cách là dùng một delegate resource-aware tùy chỉnh hoặc listener/collaborator được cập nhật khi resource được mở. Ví dụ delegate wrapper:

```java
public class TrackingFlatFileReader<T>
        extends FlatFileItemReader<T> {

    private final Consumer<Resource> resourceObserver;

    public TrackingFlatFileReader(Consumer<Resource> resourceObserver) {
        this.resourceObserver = resourceObserver;
    }

    @Override
    public void setResource(Resource resource) {
        super.setResource(resource);
        resourceObserver.accept(resource);
    }
}
```

Đây là ví dụ minh họa cách quan sát resource được gán cho delegate. `resourceObserver` cần là collaborator theo scope của Step và phải tránh side effect không idempotent vì resource có thể được gán lại khi restart. Nếu cần lưu tên file cho audit bền vững, ghi vào `StepExecution`/ExecutionContext qua API được hỗ trợ hoặc lưu cùng record nghiệp vụ; không dùng field singleton dùng chung giữa các Job.

Một lựa chọn đơn giản hơn là mỗi item mang source file name nếu reader/delegate được thiết kế để gắn metadata nguồn vào item. Điều này hữu ích khi reject hoặc audit cần chỉ ra chính xác file nguồn của từng record.

## 15. Tên reader phải ổn định

`ItemStreamSupport` dùng tên reader để tạo key trong `ExecutionContext`. Vì vậy, `.name(...)` không chỉ là nhãn log; nó tham gia namespace của checkpoint.

Ví dụ:

```java
.name("multiTransactionReader")
```

và delegate:

```java
.name("transactionFileDelegate")
```

Các tên này cần:

- Không rỗng khi lưu state.
- Ổn định qua các lần restart của cùng Step.
- Không trùng với reader/stream khác trong cùng StepExecution.
- Không được tạo ngẫu nhiên theo thời điểm hoặc JobExecution ID.

Nếu đổi tên reader trong phiên bản ứng dụng mới, key checkpoint cũ có thể không còn được tìm thấy. Khi thay đổi tên, hãy xác định rõ JobExecution cũ có cần restart qua phiên bản mới hay không và có kế hoạch migration/hoàn tất các execution đang chạy.

## 16. Khi nào dùng saveState(false)?

`saveState(false)` tắt việc lưu checkpoint của reader. Điều này có thể phù hợp khi:

- Reader chỉ chạy một lần và không cần restart.
- Input có thể đọc lại toàn bộ với chi phí thấp.
- Ứng dụng chủ động quản lý checkpoint ở cơ chế khác đã được thiết kế và kiểm thử.
- Không muốn component lưu state trong một ngữ cảnh đặc biệt như reader dùng song song nhưng không hỗ trợ state phù hợp.

Với `MultiResourceItemReader`, nếu yêu cầu là restart từ file và vị trí hiện tại, không nên tắt state ở reader ngoài hoặc delegate. Hãy bật `saveState(true)` ở cả hai tầng.

Không dùng `saveState(false)` để né lỗi restart do resource list thay đổi. Làm vậy chỉ bỏ checkpoint, không sửa nguyên nhân input set không ổn định.

## 17. Strict mode và danh sách resource rỗng

Khi không tìm thấy resource, cần xác định Job nên xử lý thế nào. Với `strict(true)`, reader có thể báo lỗi khi không có resource theo semantics của implementation. Nếu nghiệp vụ cho phép không có file, có thể cấu hình hành vi không strict và xử lý trường hợp không có item ở flow phù hợp.

Không nên coi danh sách rỗng là thành công nếu điều đó có thể che giấu lỗi upstream như file chưa được upload hoặc pattern sai. Có thể kiểm tra resource count trước khi launch và ghi trạng thái rõ ràng.

Khi restart, resource list rỗng trong khi checkpoint cho biết đã có resource index trước đó là dấu hiệu input set đã thay đổi hoặc resource bị xóa. Nên fail với thông tin đủ để vận hành khôi phục manifest/file đúng.

## 18. Resource biến mất hoặc thay đổi giữa các lần chạy

Các lỗi phổ biến:

- File đã được archive hoặc xóa sau lần chạy đầu.
- File bị thay thế bằng nội dung mới tại cùng path.
- Permission thay đổi khiến process không thể đọc lại.
- Wildcard tìm được thêm file mới.
- Một file trong danh sách bị rename.
- Thứ tự comparator thay đổi.

Reader index có thể vẫn hợp lệ về số nhưng trỏ đến resource khác. Để phát hiện:

- Lưu manifest gồm path, size và checksum.
- Xác minh resource identity trước khi mở delegate.
- Giữ input immutable đến khi JobInstance hết thời hạn restart.
- Chỉ archive/xóa input sau khi Job hoàn tất và retention cho phép.
- Khi input set thay đổi, tạo JobInstance mới hoặc thực hiện recovery có kiểm soát.

Không tự động bỏ qua resource bị mất rồi tiếp tục file kế tiếp nếu điều đó làm mất dữ liệu mà không có audit/reconciliation.

## 19. Resource checkpoint và partitioning

Nếu dùng partitioning, mỗi partition thường có reader/ExecutionContext riêng. Có thể chia resource list thành các nhóm và tạo `MultiResourceItemReader` riêng cho từng partition.

```text
Manager Step
    |
    +--> Partition 0: files 01, 02 --> MultiResourceReader 0
    |
    +--> Partition 1: files 03, 04 --> MultiResourceReader 1
    |
    +--> Partition 2: files 05, 06 --> MultiResourceReader 2
```

Mỗi partition cần có:

- Resource list riêng, không chồng lấn ngoài ý muốn.
- Thứ tự resource ổn định trong partition.
- Reader name/ExecutionContext key riêng phù hợp với partition.
- Delegate state độc lập.
- Manifest hoặc partition metadata đủ để tái tạo cùng input set khi restart.

Không chia sẻ một instance `MultiResourceItemReader` mutable giữa nhiều worker. Reader giữ `currentResource` và delegate hiện tại; nhiều thread cùng thay đổi state có thể làm lẫn file và checkpoint.

## 20. Lỗi thường gặp khi lưu resource hiện tại

### Chỉ lưu dòng hiện tại, không lưu resource index

Vị trí dòng không xác định file nào đang được đọc. Dùng `MultiResourceItemReader` để quản lý resource index và delegate để quản lý vị trí trong file.

### Chỉ bật saveState ở reader ngoài

Reader biết file hiện tại nhưng delegate có thể không khôi phục được vị trí bên trong file. Bật state cho delegate có khả năng restart.

### Chỉ bật saveState ở delegate

Delegate không đủ thông tin để chọn đúng resource trong danh sách. Bật state ở `MultiResourceItemReader`.

### Dùng wildcard có danh sách thay đổi khi restart

Resource index có thể trỏ sang file khác. Chốt input list bằng manifest hoặc staging directory.

### Không sắp xếp resource tường minh

Thứ tự trả về từ filesystem có thể khác. Dùng comparator ổn định và giữ nguyên qua restart.

### Đổi reader name

ExecutionContext key thay đổi và checkpoint cũ có thể không được khôi phục. Giữ tên ổn định cho JobExecution có thể restart.

### Đổi nội dung file tại cùng đường dẫn

Delegate position cũ có thể trỏ đến record khác. Giữ input bất biến và xác minh checksum.

### Tự sửa key nội bộ trong ExecutionContext

Key là chi tiết implementation dựa trên reader name/version. Để reader tự ghi/đọc state qua ItemStream lifecycle.

### Dùng một delegate singleton cho nhiều Job đồng thời

Delegate giữ resource và state mutable. Tạo instance phù hợp theo StepExecution hoặc bảo đảm ownership riêng.

### Xóa file đã đọc trước khi Job hoàn tất

Restart có thể cần mở lại file. Chỉ archive/xóa sau khi Job terminal và retention/recovery cho phép.

### Nghĩ checkpoint được cập nhật ngay sau từng read

Checkpoint bền vững gắn với chunk commit. Item trong chunk rollback có thể được đọc lại.

## 21. Kiểm thử checkpoint của MultiResourceItemReader

Kiểm thử cần chứng minh reader khôi phục đúng cả resource và vị trí bên trong resource.

### Fixture nhiều file

Tạo hai file nhỏ:

```text
file-01.csv
id,value
1,A
2,B
3,C

file-02.csv
id,value
4,D
5,E
6,F
```

Sắp xếp resources theo tên file và cấu hình delegate `FlatFileItemReader` với `saveState(true)`. Đọc hai item đầu, gọi `update` để ghi checkpoint vào `ExecutionContext`, rồi đóng reader.

### Mở reader mới với cùng checkpoint

Tạo một instance reader mới với cùng:

- Reader name.
- Delegate name.
- Resource list và thứ tự.
- Nội dung file.
- Cấu hình mapping và encoding.

Mở reader mới bằng `ExecutionContext` đã lưu và xác nhận item kế tiếp là item thứ ba của file đầu, không phải item đầu tiên. Tiếp tục đọc đến khi qua file thứ hai và xác nhận thứ tự không trùng/thiếu.

### Kiểm thử qua ranh giới file

Đặt chunk/checkpoint gần cuối file đầu để lần đọc tiếp theo đi sang file thứ hai. Sau khi lưu state, restart và xác nhận reader ở đúng resource thứ hai cùng vị trí tương ứng.

### Kiểm thử danh sách thay đổi

Thêm file mới trước resource đã checkpoint hoặc đổi comparator giữa hai lần mở. Test nên cho thấy input list không còn tương thích; production nên phát hiện khác biệt qua manifest/checksum và dừng thay vì âm thầm xử lý nhầm.

## 22. Ví dụ kiểm thử state ở mức reader

Đoạn dưới minh họa ý tưởng dùng cùng `ExecutionContext` qua hai instance reader. Các helper tạo reader phải dùng cùng resource array, comparator và reader names:

```java
@Test
void resumesFromSavedResourceAndDelegatePosition() throws Exception {
    Resource[] resources = {
            new FileSystemResource(file01),
            new FileSystemResource(file02)
    };

    ExecutionContext checkpoint = new ExecutionContext();
    MultiResourceItemReader<String> firstReader =
            createReader(resources);

    firstReader.open(checkpoint);
    try {
        assertThat(firstReader.read()).isEqualTo("1,A");
        assertThat(firstReader.read()).isEqualTo("2,B");
        firstReader.update(checkpoint);
    } finally {
        firstReader.close();
    }

    MultiResourceItemReader<String> restartedReader =
            createReader(resources);

    restartedReader.open(checkpoint);
    try {
        assertThat(restartedReader.read()).isEqualTo("3,C");
        assertThat(restartedReader.read()).isEqualTo("4,D");
    } finally {
        restartedReader.close();
    }
}
```

`createReader(resources)` là helper tạo `MultiResourceItemReader` với delegate `FlatFileItemReader` có cùng tên, `saveState(true)` và cùng comparator. Ví dụ kiểm tra lifecycle reader trực tiếp; integration test với Spring Batch Step vẫn cần thiết để xác nhận checkpoint được persist trong JobRepository cùng transaction của chunk.

Khi tự gọi `open`, `update`, `close`, test đang mô phỏng lifecycle ở mức stream; nó không tự kiểm tra transaction rollback hoặc metadata JobExecution. Không dùng test này làm bằng chứng duy nhất cho restart production.

## 23. Kiểm thử restart ở cấp Job

Integration test nên dùng `@SpringBatchTest` và `JobLauncherTestUtils` để chạy Job thật:

1. Tạo resource manifest cố định cho test.
2. Launch Job với identifying parameters đại diện cho input set.
3. Dừng/để Job thất bại sau một số chunk đã commit bằng test fixture có kiểm soát.
4. Xác nhận ExecutionContext lưu resource index và delegate position tại checkpoint cuối.
5. Restart cùng JobInstance bằng cùng identifying parameters.
6. Xác nhận file đã xử lý trước checkpoint không bị đọc lại ngoài ý muốn.
7. Xác nhận phần còn lại của resource hiện tại và các resource sau được đọc đủ.
8. Kiểm tra writer output không trùng và không thiếu item.

Không thay input file giữa hai lần chạy. Nếu cần test tình huống input thay đổi, tạo một test riêng xác nhận Job phát hiện manifest/checksum mismatch và fail rõ ràng.

## 24. Quy trình vận hành khi restart nhiều resource

Trước khi restart một Job đọc nhiều file:

1. Xác định JobInstance và JobExecution cũ.
2. Xác minh process cũ đã dừng và execution đủ điều kiện restart.
3. Tải manifest input của đúng JobInstance.
4. Tái tạo resource list theo đúng thứ tự ban đầu.
5. Kiểm tra mọi resource cần thiết còn tồn tại và checksum/size khớp.
6. Giữ nguyên reader name, delegate name, fragment/line mapping và JobParameters.
7. Để `MultiResourceItemReader` đọc index checkpoint và delegate khôi phục vị trí file.
8. Theo dõi JobExecution mới, resource hiện tại và counters.
9. Đối soát dữ liệu đã commit và side effect của writer.
10. Chỉ archive/xóa file input sau khi Job hoàn tất và cửa sổ restart/reprocess kết thúc.

Nếu manifest không khớp hoặc file hiện tại đã bị thay thế, không nên ép reader dùng checkpoint cũ. Hãy xác định cách reprocess/new JobInstance hoặc khôi phục đúng input trước khi tiếp tục.

## 25. Quy trình thiết kế checkpoint resource

Khi xây dựng Step đọc nhiều resource, hãy làm theo trình tự:

1. Chọn `MultiResourceItemReader` và một delegate có hỗ trợ `ItemStream`.
2. Chốt tập resource thuộc JobInstance.
3. Sắp xếp resource bằng comparator xác định.
4. Đặt tên reader ngoài và delegate ổn định, duy nhất trong Step.
5. Bật `saveState(true)` ở cả reader ngoài và delegate.
6. Đảm bảo delegate lưu được vị trí bên trong resource hiện tại.
7. Giữ resource path, nội dung, encoding và schema ổn định qua restart.
8. Để framework cập nhật ExecutionContext theo chunk commit; không tự sửa key nội bộ.
9. Dùng manifest/checksum để phát hiện resource list hoặc file bị thay đổi.
10. Tạo test qua nhiều file, nhiều page/record và ranh giới resource.
11. Integration test restart qua JobRepository để xác nhận checkpoint thực tế.
12. Chỉ cleanup input sau khi Job và chính sách retention cho phép.

| Cần khôi phục | Thành phần quản lý |
|---|---|
| File nào trong danh sách đang được đọc | `MultiResourceItemReader` resource index |
| Dòng/record nào trong file hiện tại | Delegate reader `ExecutionContext` |
| Thứ tự file giữa lần đầu và restart | Resource list + comparator/manifest |
| File có còn đúng nội dung ban đầu | Input immutability, size/checksum |
| Vị trí commit cuối cùng | Spring Batch chunk transaction và JobRepository |
| Side effect đã xảy ra ở hệ thống đích | Writer idempotency và reconciliation |

## Kết luận

`MultiResourceItemReader` lưu index của resource hiện tại trong `ExecutionContext`; delegate như `FlatFileItemReader` lưu vị trí đọc bên trong resource đó. Để restart đúng, bật `saveState(true)` ở cả hai tầng, đặt tên reader ổn định và giữ nguyên resource list cùng thứ tự sắp xếp qua các lần chạy. Vì checkpoint lưu vị trí trong danh sách chứ không phải định danh bất biến của file, wildcard có thể trả về tập file khác khi restart; hãy chốt input bằng manifest, xác minh path/size/checksum và giữ file không thay đổi đến khi hết cửa sổ restart. Spring Batch cập nhật checkpoint theo chunk commit, nên item trong chunk chưa commit có thể được đọc lại. Không tự sửa key nội bộ trong `ExecutionContext`; hãy để reader và delegate quản lý lifecycle `open`, `update`, `close`.
