# Comparator cho resource

Trong Spring Batch, `MultiResourceItemReader<T>` cho phép một Step đọc tuần tự nhiều resource bằng cách sử dụng một reader delegate. Khi có nhiều file đầu vào, thứ tự đọc file ảnh hưởng trực tiếp đến thứ tự item được phát ra. `Comparator<Resource>` xác định thứ tự mà `MultiResourceItemReader` duyệt các resource đó.

Ví dụ, một Job nhập dữ liệu từ các file `orders-001.csv`, `orders-002.csv` và `orders-003.csv`. Nếu thứ tự file có ý nghĩa theo ngày, số thứ tự hoặc batch sequence, cần cấu hình comparator để đảm bảo reader mở các file đúng thứ tự. Comparator cũng rất quan trọng với restart: Spring Batch lưu vị trí resource hiện tại, vì vậy danh sách resource và thứ tự sắp xếp phải ổn định giữa lần chạy đầu và lần restart.

## 1. MultiResourceItemReader đọc nhiều file như thế nào?

`MultiResourceItemReader<T>` là một reader bao bọc một delegate reader. Nó quản lý danh sách `Resource`, chọn resource hiện tại, rồi giao việc đọc nội dung của resource đó cho delegate.

Ví dụ có ba file:

```text
inbound/
  orders-001.csv
  orders-002.csv
  orders-003.csv
```

Luồng xử lý:

```text
MultiResourceItemReader<Order>
          |
          +--> resource[0] --> FlatFileItemReader --> các Order trong file 001
          |
          +--> resource[1] --> FlatFileItemReader --> các Order trong file 002
          |
          +--> resource[2] --> FlatFileItemReader --> các Order trong file 003
          |
          +--> hết resource --> null
```

Delegate chịu trách nhiệm đọc từng dòng hoặc item bên trong một file. `MultiResourceItemReader` chịu trách nhiệm chuyển sang resource tiếp theo khi delegate đã đọc hết resource hiện tại.

Comparator không sắp xếp các dòng bên trong từng file. Nó chỉ sắp xếp danh sách resource trước khi reader duyệt chúng. Thứ tự dòng trong mỗi file do delegate reader và cấu trúc file quyết định.

## 2. Comparator<Resource> có vai trò gì?

`Comparator<Resource>` là quy tắc so sánh hai resource. `MultiResourceItemReader` sử dụng comparator để sắp xếp mảng resource trước khi bắt đầu đọc.

Một comparator có dạng:

```java
public interface Comparator<T> {
    int compare(T first, T second);
}
```

Kết quả:

- Giá trị âm: `first` đứng trước `second`.
- Giá trị bằng 0: hai resource được xem là tương đương theo tiêu chí so sánh.
- Giá trị dương: `first` đứng sau `second`.

Ví dụ sắp xếp theo tên file:

```java
Comparator<Resource> byFilename =
        Comparator.comparing(Resource::getFilename);
```

Trong cấu hình chuẩn, `MultiResourceItemReader` có comparator mặc định dựa trên tên file. Tuy nhiên, nếu thứ tự có ý nghĩa nghiệp vụ, nên khai báo comparator tường minh để quy tắc sắp xếp được nhìn thấy trong cấu hình và có thể kiểm thử.

## 3. Vì sao thứ tự resource quan trọng?

Thứ tự resource có thể ảnh hưởng đến:

- Thứ tự item được reader phát ra.
- Thứ tự các nhóm dữ liệu được ghi hoặc xử lý.
- Kết quả khi dữ liệu giữa các file có quan hệ phụ thuộc.
- Vị trí checkpoint và khả năng restart.
- Khả năng tái lập kết quả giữa các lần chạy.

Ví dụ, file chứa dữ liệu theo ngày:

```text
orders-2026-11-13.csv
orders-2026-11-14.csv
orders-2026-11-15.csv
```

Nếu Job cần đọc theo ngày tăng dần, comparator phải sắp xếp theo ngày được parse từ tên file hoặc metadata tương đương. Không nên dựa vào thứ tự mà filesystem hoặc resource resolver trả về, vì thứ tự liệt kê file không phải lúc nào cũng được bảo đảm.

Khi Step có thể restart, thứ tự resource phải nhất quán với checkpoint đã lưu. Nếu lần chạy đầu đọc file A, B, C nhưng lần restart sắp xếp thành B, A, C, chỉ số resource hiện tại có thể trỏ đến file khác.

## 4. Cấu hình MultiResourceItemReader cơ bản

Có thể dùng `MultiResourceItemReaderBuilder<T>` để cấu hình danh sách resource, delegate và comparator:

```java
@Bean
public MultiResourceItemReader<Order> multiOrderReader(
        Resource[] orderResources,
        FlatFileItemReader<Order> orderFileDelegate,
        Comparator<Resource> orderResourceComparator) {

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(orderResources)
            .delegate(orderFileDelegate)
            .comparator(orderResourceComparator)
            .saveState(true)
            .build();
}
```

Các cấu hình chính:

- `name(...)`: tên ổn định của multi-resource reader, được dùng cho state của reader.
- `resources(...)`: các resource cần đọc.
- `delegate(...)`: reader thực hiện đọc từng resource.
- `comparator(...)`: quy tắc sắp xếp resource.
- `saveState(true)`: bật lưu checkpoint để hỗ trợ restart.

Delegate thường là `FlatFileItemReader<T>` hoặc một reader triển khai `ResourceAwareItemReaderItemStream<T>`, để `MultiResourceItemReader` có thể cung cấp resource hiện tại cho delegate trước khi mở nó.

## 5. Cấu hình delegate FlatFileItemReader

Delegate đọc nội dung của từng file. Nó cần được cấu hình line mapper, tokenizer và field mapping giống một `FlatFileItemReader` thông thường.

```java
@Bean
public FlatFileItemReader<Order> orderFileDelegate() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderFileDelegate")
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount")
            .targetType(Order.class)
            .linesToSkip(1)
            .saveState(true)
            .build();
}
```

Trong ví dụ, resource không được gắn cố định trong builder vì resource sẽ được `MultiResourceItemReader` cung cấp cho delegate khi chuyển file. `FlatFileItemReader` có khả năng nhận resource qua contract `ResourceAwareItemReaderItemStream`.

Tên delegate cũng nên ổn định. Multi-resource reader và delegate có thể lưu những phần state khác nhau trong cùng Step `ExecutionContext`; tên riêng giúp key state của chúng không xung đột.

## 6. Sắp xếp theo tên file

Nếu tên file có định dạng và thứ tự từ điển khớp với thứ tự mong muốn, có thể dùng comparator theo filename:

```java
@Bean
public Comparator<Resource> orderResourceComparator() {
    return Comparator.comparing(
            Resource::getFilename,
            Comparator.nullsLast(Comparator.naturalOrder())
    );
}
```

Comparator trên sắp xếp tên theo thứ tự chuỗi tăng dần. `nullsLast` quy định resource không có filename sẽ đứng cuối; với ứng dụng production, thường nên validate resource và từ chối filename null thay vì âm thầm chấp nhận.

Ví dụ:

```text
orders-001.csv
orders-002.csv
orders-010.csv
```

Vì số thứ tự được đệm bằng số 0, thứ tự từ điển cũng là thứ tự số mong muốn.

Đây là cách đơn giản khi quy ước đặt tên file được kiểm soát. Nếu tên file không được đệm số 0, cần comparator hiểu phần số thay vì so sánh chuỗi thông thường.

## 7. Vấn đề lexical ordering với số thứ tự

Sắp xếp chuỗi không giống sắp xếp số. Ví dụ:

```text
orders-1.csv
orders-10.csv
orders-2.csv
```

Thứ tự từ điển có thể là:

```text
orders-1.csv
orders-10.csv
orders-2.csv
```

Trong khi thứ tự số mong muốn là:

```text
orders-1.csv
orders-2.csv
orders-10.csv
```

Nếu số thứ tự biểu diễn sequence nghiệp vụ, hãy parse phần số và dùng `Comparator.comparingLong(...)` hoặc `Comparator.comparingInt(...)` thay vì dựa vào filename string.

Một giải pháp khác là quy định tên file zero-padded, ví dụ `orders-0001.csv`. Cách đó đơn giản nhưng chỉ phù hợp khi độ rộng số được xác định và hệ thống tạo file tuân thủ quy ước.

## 8. Comparator theo số thứ tự trong filename

Giả sử file có format `orders-<sequence>.csv`. Có thể parse sequence bằng regex:

```java
private static final Pattern ORDER_FILE_PATTERN =
        Pattern.compile("orders-(\\d+)\\.csv");

private static long sequenceOf(Resource resource) {
    String filename = Objects.requireNonNull(
            resource.getFilename(), "Resource filename must not be null");

    Matcher matcher = ORDER_FILE_PATTERN.matcher(filename);
    if (!matcher.matches()) {
        throw new IllegalArgumentException(
                "Unexpected order file name: " + filename);
    }

    return Long.parseLong(matcher.group(1));
}

@Bean
public Comparator<Resource> orderResourceComparator() {
    return Comparator.comparingLong(MyBatchConfiguration::sequenceOf)
            .thenComparing(Resource::getFilename)
            .thenComparing(Resource::getDescription);
}
```

Comparator này:

1. Kiểm tra filename tồn tại.
2. Yêu cầu filename khớp đúng format.
3. Parse sequence thành số.
4. So sánh theo sequence tăng dần.
5. Dùng filename và description làm tie-breaker để tạo thứ tự xác định nếu sequence trùng.

Nếu sequence có thể vượt giới hạn `long`, dùng `BigInteger`. Không nên parse số bằng `Integer` nếu quy mô sequence có thể lớn.

Fail fast khi filename sai format thường tốt hơn tự đưa file lỗi về đầu/cuối danh sách, vì file sai tên có thể cho thấy upstream gửi sai manifest hoặc batch.

## 9. Comparator theo ngày nghiệp vụ

Nếu tên file chứa ngày, nên parse thành kiểu ngày thay vì so sánh chuỗi nếu format có thể thay đổi hoặc không sắp xếp từ điển đúng.

Ví dụ filename `orders-15-11-2026.csv` dùng format `dd-MM-yyyy`:

```java
private static final Pattern DAILY_FILE_PATTERN =
        Pattern.compile("orders-(\\d{2}-\\d{2}-\\d{4})\\.csv");

private static LocalDate businessDateOf(Resource resource) {
    String filename = Objects.requireNonNull(resource.getFilename());
    Matcher matcher = DAILY_FILE_PATTERN.matcher(filename);

    if (!matcher.matches()) {
        throw new IllegalArgumentException("Invalid daily file name: " + filename);
    }

    return LocalDate.parse(
            matcher.group(1),
            DateTimeFormatter.ofPattern("dd-MM-uuuu")
    );
}

@Bean
public Comparator<Resource> dailyResourceComparator() {
    return Comparator.comparing(MyBatchConfiguration::businessDateOf)
            .thenComparing(Resource::getFilename)
            .thenComparing(Resource::getDescription);
}
```

Kết quả là file có ngày nghiệp vụ sớm hơn được đọc trước. Nếu một ngày có nhiều file part, thêm sequence hoặc part number vào comparator:

```java
Comparator<Resource> comparator =
        Comparator.comparing(MyBatchConfiguration::businessDateOf)
                .thenComparingLong(MyBatchConfiguration::partNumberOf)
                .thenComparing(Resource::getDescription);
```

Thứ tự ngày và part phải phản ánh hợp đồng dữ liệu. Không dùng `lastModified()` làm ngày nghiệp vụ nếu timestamp sửa file có thể thay đổi khi copy, restore hoặc archive.

## 10. Comparator nhiều tiêu chí

Một comparator có thể kết hợp nhiều tiêu chí bằng `thenComparing(...)`:

```java
Comparator<Resource> comparator =
        Comparator.comparing(MyBatchConfiguration::businessDateOf)
                .thenComparing(MyBatchConfiguration::regionOf)
                .thenComparingLong(MyBatchConfiguration::sequenceOf)
                .thenComparing(Resource::getDescription);
```

Thứ tự trên có nghĩa:

1. Ngày nghiệp vụ tăng dần.
2. Trong cùng ngày, region theo thứ tự chuỗi.
3. Trong cùng region, sequence tăng dần.
4. Nếu các khóa nghiệp vụ vẫn trùng, dùng resource description làm tie-breaker.

Nên ghi rõ thứ tự ưu tiên trong tên method hoặc comment để người bảo trì hiểu vì sao file A phải được đọc trước file B. Tránh viết comparator phức tạp bằng nhiều nhánh `if` khó kiểm tra.

## 11. Comparator cần có thứ tự toàn phần và ổn định

Comparator phải tuân theo contract của Java: kết quả so sánh cần nhất quán, có tính bắc cầu và không thay đổi tùy tiện trong quá trình sort. Một comparator không ổn định có thể khiến thứ tự resource khác nhau giữa các lần chạy.

Các nguyên tắc thực tế:

- Cùng một cặp resource phải cho cùng kết quả so sánh trong cùng điều kiện.
- Không phụ thuộc vào counter thay đổi theo lần gọi.
- Không đọc dữ liệu file hoặc gọi API từ bên trong comparator.
- Không dùng thời gian hiện tại làm tiêu chí sort.
- Xác định rõ cách xử lý filename null hoặc không hợp lệ.
- Nếu hai resource có cùng khóa nghiệp vụ, thêm tie-breaker ổn định.
- Tránh phụ thuộc vào thứ tự đầu vào của mảng nếu resolver có thể trả resource theo thứ tự khác nhau.

Ví dụ không nên dùng:

```java
Comparator<Resource> unstable = (left, right) ->
        ThreadLocalRandom.current().nextInt(-1, 2);
```

Kết quả thay đổi theo từng lần so sánh, vi phạm contract và có thể khiến sort thất bại hoặc tạo thứ tự không xác định.

## 12. Xử lý filename trùng nhau

Hai resource có thể có cùng filename nhưng nằm ở hai thư mục khác nhau:

```text
region-a/orders-001.csv
region-b/orders-001.csv
```

Nếu comparator chỉ so sánh `getFilename()`, hai resource được xem là bằng nhau. Khi đó, thứ tự giữa chúng có thể phụ thuộc thứ tự mảng đầu vào.

Nếu hai file là hai nguồn khác nhau và thứ tự cần xác định, hãy thêm tiêu chí như region, path hoặc resource description:

```java
Comparator<Resource> comparator =
        Comparator.comparing(Resource::getFilename)
                .thenComparing(Resource::getDescription);
```

Trong môi trường filesystem, có thể dùng đường dẫn chuẩn hóa làm tie-breaker nếu ứng dụng quản lý path cụ thể. Với resource không có path filesystem, chọn một định danh ổn định do nguồn resource cung cấp.

Nếu hai resource hoàn toàn giống nhau theo mọi khóa so sánh, cần quyết định đó là duplicate ngoài ý muốn hay hai bản sao hợp lệ. Đừng âm thầm bỏ một resource chỉ vì comparator trả về 0; comparator không có trách nhiệm deduplicate.

## 13. Kết hợp ResourcePatternResolver và comparator

Thường dùng `ResourcePatternResolver` để tìm file theo pattern, rồi truyền danh sách resource cho `MultiResourceItemReader`:

```java
@Bean
public Resource[] orderResources(ResourcePatternResolver resolver) throws IOException {
    return resolver.getResources("file:/var/batch/inbound/orders-*.csv");
}
```

Không nên dựa vào thứ tự mà `getResources(...)` trả về. Hãy để `MultiResourceItemReader` áp dụng comparator rõ ràng.

Ví dụ kết hợp:

```java
@Bean
public MultiResourceItemReader<Order> multiOrderReader(
        Resource[] orderResources,
        FlatFileItemReader<Order> orderFileDelegate,
        Comparator<Resource> orderResourceComparator) {

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(orderResources)
            .delegate(orderFileDelegate)
            .comparator(orderResourceComparator)
            .saveState(true)
            .build();
}
```

Nếu pattern không tìm thấy file nào, hãy xác định chính sách rõ ràng: Job được phép hoàn tất với zero item hay phải fail vì thiếu input. Có thể dùng strict behavior của reader hoặc một bước kiểm tra resource trước khi chạy. Không để một danh sách rỗng được hiểu nhầm là batch đã xử lý dữ liệu thành công.

## 14. MultiResourceItemReader và checkpoint

`MultiResourceItemReader` lưu tiến độ ở cấp resource hiện tại và phối hợp với delegate để lưu tiến độ bên trong resource đó. Khi restart, reader cần biết đang ở file nào và delegate cần biết đang ở item nào trong file.

Ví dụ:

```text
Resource list sau khi sort:
  0 -> orders-001.csv
  1 -> orders-002.csv
  2 -> orders-003.csv

Checkpoint đã commit:
  current resource index = 1
  delegate state = dòng/item tiếp theo trong orders-002.csv
```

Khi restart, reader mở lại resource ở index 1 theo danh sách đã sort và khôi phục state của delegate. Vì vậy, comparator là một phần của hợp đồng restart: cùng input phải tạo cùng danh sách và cùng thứ tự resource.

Tên multi-resource reader và tên delegate nên ổn định. `saveState(true)` cần được bật cho reader nếu muốn checkpoint được lưu. Delegate cũng cần hỗ trợ `ItemStream` nếu nó có state bên trong file.

## 15. Vì sao thay đổi comparator có thể làm restart sai?

Giả sử lần chạy đầu có thứ tự:

```text
0 -> file-A.csv
1 -> file-B.csv
2 -> file-C.csv
```

Job đã commit đến giữa `file-B.csv`, nên checkpoint lưu resource index 1 cùng state của delegate. Trước khi restart, comparator được đổi khiến thứ tự thành:

```text
0 -> file-B.csv
1 -> file-A.csv
2 -> file-C.csv
```

Index 1 giờ trỏ đến `file-A.csv`, trong khi state delegate được lưu cho phần đã đọc của `file-B.csv`. Kết quả có thể là đọc thiếu, đọc trùng hoặc lỗi mapping/checkpoint.

Các thay đổi nguy hiểm gồm:

- Thay comparator giữa hai lần chạy.
- Thêm file mới đứng trước resource hiện tại.
- Xóa file đã đọc hoặc file hiện tại.
- Đổi tên file làm thay đổi thứ tự.
- Đổi pattern khiến danh sách resource khác.
- Thay đổi cách phân tích date/sequence trong filename.
- Dùng tiêu chí mutable như last-modified time.

Với Job cần restart, giữ nguyên danh sách resource và comparator trong suốt vòng đời của JobInstance. Nếu tập file thay đổi, hãy coi đó là một input batch mới hoặc lưu manifest để tái tạo đúng danh sách cũ.

## 16. Dùng manifest để giữ tập resource ổn định

Với batch quan trọng, có thể tạo manifest trước khi launch Job. Manifest liệt kê các file thuộc cùng một batch theo thứ tự đã xác định:

```text
batchId=20261115-001
files:
  - /var/batch/staging/orders-20261115-001.csv
  - /var/batch/staging/orders-20261115-002.csv
  - /var/batch/staging/orders-20261115-003.csv
```

Job sử dụng manifest hoặc batch ID để chọn lại đúng tập file khi restart. Có thể lưu checksum, kích thước và version của từng file để xác nhận nguồn không bị thay đổi.

Manifest giúp tránh việc một pattern như `orders-*.csv` vô tình nhận thêm file mới được upstream đưa đến trong lúc Job cũ đang dở. Comparator vẫn cần thiết để sắp xếp resource theo thứ tự nghiệp vụ, nhưng danh sách đầu vào đã được cố định.

Không nên ghi toàn bộ danh sách path lớn vào `ExecutionContext` nếu manifest có thể được lưu ở một kho bền vững và tham chiếu bằng batch ID. ExecutionContext nên giữ checkpoint gọn, không trở thành nơi lưu file catalog lớn.

## 17. Comparator và delegate reader là hai trách nhiệm khác nhau

Comparator sắp xếp resource; delegate đọc nội dung từng resource. Hai phần này không thay thế nhau.

| Thành phần | Trách nhiệm |
|---|---|
| `Resource[]` | Danh sách file/resource cần đọc |
| `Comparator<Resource>` | Thứ tự chuyển qua các resource |
| `MultiResourceItemReader` | Quản lý resource hiện tại và chuyển delegate sang resource kế tiếp |
| `ResourceAwareItemReaderItemStream` delegate | Nhận resource hiện tại và đọc item bên trong nó |
| `LineMapper`/`RowMapper`/parser | Chuyển nội dung từng record thành object |

Nếu item trong từng file cần sắp xếp theo `orderId`, comparator resource không giải quyết yêu cầu đó. Cần đảm bảo file đã được sắp xếp đúng hoặc delegate/query xử lý thứ tự item phù hợp.

Tương tự, nếu cần xử lý nhiều file song song, comparator chỉ xác định thứ tự tuần tự. Nó không tạo partition hay concurrency. Có thể dùng partitioned Step với mỗi worker xử lý một resource hoặc nhóm resource nếu cần tăng throughput.

## 18. Resource comparator trong partitioning

Trong một số thiết kế, mỗi file được giao cho một partition. Khi đó, việc phân phối resource cho partition là trách nhiệm của `Partitioner` hoặc logic phân chia, còn comparator có thể được dùng để xác định thứ tự trước khi tạo partition.

Ví dụ:

```text
Resource list
   |
   v
Sort by business date / sequence
   |
   +--> partition-0: file A
   +--> partition-1: file B
   +--> partition-2: file C
```

Nếu mỗi file được xử lý độc lập, các partition có thể chạy song song. Nhưng khi dữ liệu giữa các file có thứ tự phụ thuộc, không nên chạy song song chỉ vì đã sort resource. Thứ tự sort không bảo đảm partition hoàn tất theo thứ tự đó.

Nếu cần thứ tự tuần tự giữa các file, dùng `MultiResourceItemReader` trong một Step tuần tự hoặc tách thành các Step/flow có dependency rõ ràng. Nếu cần partitioning, đảm bảo mỗi partition độc lập và output có thể hợp nhất an toàn.

## 19. Kiểm tra resource trước khi sort

Comparator không nên gánh toàn bộ validation của resource. Trước khi đưa resource vào reader, có thể kiểm tra:

- Filename có tồn tại và đúng naming convention.
- Resource tồn tại và đọc được.
- Resource thuộc đúng thư mục/batch được phép.
- Không có file trùng hoặc file tạm như `.part`, `.tmp` lọt vào pattern.
- Metadata ngày/sequence có thể parse.
- Tập file đã được chốt trước khi Job bắt đầu.

Ví dụ helper kiểm tra filename:

```java
private static void validateOrderResources(Resource[] resources) {
    for (Resource resource : resources) {
        String filename = resource.getFilename();
        if (filename == null || !ORDER_FILE_PATTERN.matcher(filename).matches()) {
            throw new IllegalArgumentException(
                    "Invalid order resource: " + resource.getDescription());
        }
    }
}
```

Nếu resource không hợp lệ, fail trước khi mở reader sẽ dễ điều tra hơn để comparator tự đưa file lỗi vào vị trí cuối cùng rồi Job mới thất bại khi đọc.

## 20. Những lỗi thường gặp

**Dựa vào thứ tự ResourcePatternResolver trả về.** Thứ tự liệt kê không phải hợp đồng nghiệp vụ. Cấu hình comparator rõ ràng.

**So sánh số thứ tự bằng chuỗi.** `file-10` có thể đứng trước `file-2`. Parse phần số hoặc dùng tên zero-padded.

**Không thêm tie-breaker.** Hai resource có cùng ngày/sequence có thể được xem là bằng nhau và thứ tự phụ thuộc đầu vào. Thêm filename/path/description ổn định.

**Dùng lastModified làm tiêu chí chính.** Timestamp có thể thay đổi khi copy, restore hoặc archive; restart có thể tạo thứ tự khác.

**Đổi comparator khi Job đang cần restart.** Resource index có thể trỏ đến file khác. Giữ comparator và resource set ổn định.

**Nhầm comparator resource với sort item.** Comparator chỉ sắp xếp file, không sắp xếp record bên trong file.

**Cho rằng comparator tạo xử lý song song.** `MultiResourceItemReader` duyệt resource tuần tự. Muốn chạy song song, thiết kế partitioning.

**Dùng comparator để loại file trùng.** Comparator trả 0 không có nghĩa framework tự loại resource. Cần validation/deduplication riêng nếu có yêu cầu.

**Để filename sai format âm thầm lọt vào danh sách.** Validate trước khi mở Step và fail rõ ràng khi input không đúng hợp đồng.

## 21. Kiểm thử comparator

Nên kiểm thử comparator độc lập bằng các resource có tên đại diện cho tình huống thực tế:

```java
@Test
void sortsOrderFilesByNumericSequence() {
    List<Resource> resources = new ArrayList<>(List.of(
            new FileSystemResource("/inbound/orders-10.csv"),
            new FileSystemResource("/inbound/orders-2.csv"),
            new FileSystemResource("/inbound/orders-1.csv")
    ));

    resources.sort(orderResourceComparator());

    assertEquals(
            List.of("orders-1.csv", "orders-2.csv", "orders-10.csv"),
            resources.stream().map(Resource::getFilename).toList()
    );
}
```

Các trường hợp nên kiểm thử:

1. Tên file có số thứ tự một chữ số và nhiều chữ số.
2. Hai file có cùng sequence nhưng khác thư mục.
3. Filename null hoặc không đúng naming convention.
4. Ngày nghiệp vụ ở nhiều tháng/năm khác nhau.
5. Hai resource có cùng mọi khóa nghiệp vụ và cần tie-breaker.
6. Cùng một danh sách resource luôn tạo cùng thứ tự.
7. Resource resolver trả đầu vào theo thứ tự khác nhau nhưng comparator vẫn tạo cùng kết quả.
8. Danh sách resource rỗng và chính sách strict được áp dụng đúng.

## 22. Kiểm thử MultiResourceItemReader và restart

Unit test comparator chưa chứng minh được reader chuyển file và khôi phục checkpoint đúng. Cần integration test với delegate reader:

1. Tạo hai hoặc ba file fixture với các record có ID dễ nhận biết.
2. Cấu hình `MultiResourceItemReader` cùng comparator và delegate.
3. Đọc toàn bộ, xác nhận record xuất hiện theo đúng thứ tự file.
4. Dùng chunk/Step test để commit một phần file đầu tiên và một phần file tiếp theo.
5. Dừng Job sau checkpoint, sau đó restart cùng JobInstance và cùng resource list.
6. Xác nhận reader tiếp tục đúng file và đúng vị trí bên trong file.
7. Thử thêm, xóa, đổi tên hoặc thay nội dung file trước restart để xác nhận cơ chế manifest/version phát hiện thay đổi.
8. Kiểm tra delegate `ItemStream` được open/update/close đúng lifecycle.

Integration test restart cần JobRepository giữ metadata giữa các lần chạy. Nếu tạo reader/repository mới mà không giữ ExecutionContext, test chỉ chứng minh lần đọc mới từ đầu chứ không chứng minh checkpoint được khôi phục.

## 23. Cách thiết kế comparator cho resource

Hãy chọn tiêu chí sắp xếp phản ánh thứ tự nghiệp vụ: filename zero-padded, sequence số, ngày nghiệp vụ, region hoặc một khóa trong manifest. Dùng comparator tường minh, có tie-breaker ổn định và từ chối resource không đúng naming convention. Không phụ thuộc thứ tự filesystem trả về hoặc tiêu chí mutable như thời điểm sửa file.

Đặt comparator vào `MultiResourceItemReaderBuilder` cùng resource list và delegate reader. Đặt tên reader/delegate ổn định và bật `saveState` khi cần restart. Giữ nguyên danh sách resource, nội dung file và comparator trong suốt vòng đời JobInstance; nếu tập file có thể thay đổi, tạo manifest hoặc batch snapshot trước khi launch.

Comparator chỉ quyết định thứ tự file. Delegate vẫn chịu trách nhiệm đọc item trong từng file, còn partitioning mới quyết định xử lý song song. Khi phân biệt đúng các trách nhiệm này, `MultiResourceItemReader` có thể đọc nhiều file theo thứ tự tái lập được và khôi phục checkpoint đáng tin cậy sau khi Job bị gián đoạn.
