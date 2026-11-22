# Kiểm thử danh sách resource

Trong Spring Batch, MultiResourceItemReader điều phối việc đọc qua một mảng Resource[] và chuyển từng resource cho delegate reader, chẳng hạn FlatFileItemReader. Kiểm thử không chỉ cần xác nhận item được đọc đúng mà còn phải xác nhận danh sách resource được tìm thấy, sắp xếp, lọc và giữ ổn định giữa lần chạy đầu với lần restart.

Một danh sách đúng nhưng thứ tự không ổn định có thể khiến restart đọc nhầm file. Một resource bị thiếu có thể khiến step fail. Một danh sách rỗng có thể là input hợp lệ hoặc lỗi nghiệp vụ tùy cấu hình. Vì vậy, bài kiểm thử nên bao phủ resource discovery, thứ tự xử lý, delegate lifecycle, lỗi file, checkpoint và integration test qua JobRepository.

## 1. Multi-resource reader hoạt động như thế nào?

MultiResourceItemReader là wrapper reader. Nó không tự parse nội dung file; nó giữ danh sách resource và ủy quyền việc đọc từng resource cho một ResourceAwareItemReaderItemStream.

~~~text
Resource resolver / manifest
          |
          v
       Resource[]
          |
          v
 MultiResourceItemReader
          |
          +--> Resource A --> delegate reader --> items A1, A2
          |
          +--> Resource B --> delegate reader --> items B1, B2
          |
          +--> Resource C --> delegate reader --> items C1, C2
          |
          v
         EOF
~~~

| Thành phần | Trách nhiệm |
|---|---|
| ResourcePatternResolver hoặc manifest | Tìm và tạo danh sách resource |
| Resource[] | Xác định tập file đầu vào |
| MultiResourceItemReader | Chuyển lần lượt qua từng resource |
| Delegate reader | Mở và parse nội dung một resource |
| ExecutionContext | Lưu resource hiện tại và state của delegate để restart |

MultiResourceItemReader đọc theo thứ tự danh sách resource sau khi áp dụng comparator/cấu hình tương ứng. Không nên dựa vào thứ tự tình cờ mà filesystem hoặc resolver trả về.

## 2. Xác định rõ danh sách resource là một phần của input

Trước khi viết test, xác định nguồn tạo danh sách:

- Một pattern như file:/data/inbound/*.csv.
- Một thư mục được truyền qua JobParameters.
- Một manifest liệt kê các file thuộc cùng batch.
- Một danh sách resource được lấy từ database hoặc service.
- Một tập resource được tạo bởi bước upstream.

Danh sách resource quyết định dữ liệu mà step xử lý. Vì vậy, nên kiểm tra cả nội dung danh sách và metadata quan trọng như tên file, URI, version hoặc checksum.

Nếu job phải restart, danh sách cần giữ nguyên giữa các execution của cùng JobInstance. Chỉ giữ nguyên tên thư mục là chưa đủ nếu file mới có thể được thêm, xóa hoặc đổi tên trong lúc job đang chạy.

## 3. Tìm resource bằng ResourcePatternResolver

Một trường hợp phổ biến là lấy tất cả file CSV trong thư mục. PathMatchingResourcePatternResolver có thể mở rộng pattern thành Resource[].

~~~java
ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
    "file:/data/inbound/*.csv"
);
~~~

Trong ứng dụng thực tế, thư mục có thể đến từ JobParameters. Nên tách việc tìm resource thành một factory hoặc resolver có thể kiểm thử độc lập:

~~~java
@Component
public class InputResourceResolver {

    private final ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

    public Resource[] findCsvFiles(String directory) throws IOException {
        String pattern = Path.of(directory)
            .toAbsolutePath()
            .normalize()
            .toUri()
            .toString() + "*.csv";

        Resource[] resources = resolver.getResources(pattern);

        Arrays.sort(
            resources,
            Comparator.comparing(Resource::getDescription)
        );

        return resources;
    }
}
~~~

Ví dụ dùng URI từ Path để tránh tự ghép dấu phân cách filesystem. Cần kiểm tra pattern cuối cùng trên hệ điều hành triển khai, đặc biệt khi chạy trên Windows hoặc khi directory đến từ cấu hình bên ngoài.

Test cho resolver nên xác nhận:

- Chỉ file có phần mở rộng mong đợi được chọn.
- File trong thư mục con có được lấy hay không theo pattern.
- File tạm, file archive hoặc file marker không bị lấy nhầm.
- Không có kết quả khi pattern không khớp.
- Kết quả được sắp xếp ổn định.
- Lỗi truy cập thư mục được truyền ra với thông tin có thể điều tra.

## 4. Thứ tự resource phải xác định

Filesystem không bảo đảm thứ tự liệt kê file giống nhau giữa các môi trường hoặc lần gọi. Nếu Resource[] thay đổi thứ tự, thứ tự item do reader phát ra cũng thay đổi.

Ví dụ có các file:

~~~text
orders-03.csv
orders-01.csv
orders-02.csv
~~~

Nếu thứ tự mong muốn là theo số thứ tự trong tên file, hãy sort trước khi đưa vào reader:

~~~java
Arrays.sort(
    resources,
    Comparator.comparing(Resource::getFilename)
);
~~~

Nếu tên file có thể trùng giữa các thư mục hoặc không mô tả đúng thứ tự nghiệp vụ, dùng manifest có thứ tự rõ ràng hoặc comparator theo khóa nghiệp vụ.

Một test nên xác nhận thứ tự item xuyên suốt các file:

~~~java
@Test
void readsResourcesInDeterministicOrder() throws Exception {
    Resource[] resources = {
        new FileSystemResource(fileB),
        new FileSystemResource(fileA)
    };

    Arrays.sort(
        resources,
        Comparator.comparing(Resource::getDescription)
    );

    MultiResourceItemReader<String> reader = newReader(resources);

    assertThat(readAll(reader))
        .containsExactly("A-1", "A-2", "B-1", "B-2");
}
~~~

Trong test này, fileA và fileB chứa hai record sau header. Việc đưa resource vào mảng theo thứ tự ngược giúp xác nhận sorting thực sự có tác dụng.

## 5. Tạo file test với JUnit 5 @TempDir

JUnit 5 có @TempDir để tạo thư mục tạm cho test. Đây là cách phù hợp để kiểm thử resource resolver và reader bằng filesystem thật mà không phụ thuộc thư mục local cố định.

~~~java
class MultiResourceReaderTests {

    @TempDir
    Path tempDir;

    private Path writeCsv(String fileName, String... lines)
            throws IOException {
        Path file = tempDir.resolve(fileName);
        Files.write(
            file,
            List.of(lines),
            StandardCharsets.UTF_8
        );
        return file;
    }
}
~~~

Mỗi test có thư mục riêng và JUnit dọn dẹp sau khi test kết thúc. Dùng tên file rõ ràng để assertion thể hiện thứ tự mong đợi.

Tránh dùng file mẫu cố định bên ngoài thư mục test nếu test có thể chạy đồng thời hoặc nhiều developer cùng chạy trên một workspace.

## 6. Tạo delegate FlatFileItemReader cho test

Với file CSV đơn giản, có thể dùng FlatFileItemReader<String> làm delegate và trả lại nguyên dòng sau header. MultiResourceItemReader sẽ gọi setResource(...) trên delegate cho từng file.

~~~java
private FlatFileItemReader<String> csvDelegate() {
    FlatFileItemReader<String> delegate =
        new FlatFileItemReader<>();

    delegate.setName("csvDelegate");
    delegate.setEncoding(StandardCharsets.UTF_8.name());
    delegate.setLinesToSkip(1);
    delegate.setLineMapper((line, lineNumber) -> line);

    return delegate;
}
~~~

Delegate được cấu hình không gắn một resource cố định vì wrapper sẽ gán resource trước khi mở từng file. linesToSkip(1) minh họa trường hợp mỗi file có một dòng header.

Nếu file có nhiều cột, hãy dùng tokenizer và field mapper thật của ứng dụng trong test integration. Test danh sách resource không nên thay toàn bộ mapping bằng mock nếu mục tiêu là xác nhận nhiều file được đọc đúng.

## 7. Tạo MultiResourceItemReader dùng lại trong test

Có thể gom cấu hình reader vào helper để các test chỉ tập trung vào danh sách resource và kết quả:

~~~java
private MultiResourceItemReader<String> newReader(
        Resource[] resources) {

    return new MultiResourceItemReaderBuilder<String>()
        .name("multiCsvReader")
        .resources(resources)
        .delegate(csvDelegate())
        .saveState(true)
        .strict(true)
        .build();
}
~~~

Name phải ổn định để reader lưu và khôi phục state. saveState(true) bật checkpoint. strict(true) yêu cầu có resource đầu vào; với danh sách rỗng, reader sẽ báo lỗi thay vì coi như không có dữ liệu.

Nếu muốn kiểm thử input rỗng được phép, tạo reader riêng với strict(false) để test đúng policy đó.

## 8. Helper đọc hết item và đóng reader

Test unit có thể mở reader với một ExecutionContext, đọc cho đến EOF và đóng reader trong finally:

~~~java
private List<String> readAll(
        MultiResourceItemReader<String> reader) throws Exception {

    List<String> items = new ArrayList<>();
    reader.open(new ExecutionContext());

    try {
        String item;
        while ((item = reader.read()) != null) {
            items.add(item);
        }
        return items;
    } finally {
        reader.close();
    }
}
~~~

Không bỏ qua close() trong test. Delegate có thể giữ file handle hoặc parser; không đóng resource có thể khiến test sau không xóa được file trên một số hệ điều hành.

Nếu test đang kiểm tra checkpoint, không dùng helper này vì helper tạo context mới và đọc đến EOF. Hãy tự quản lý context và vòng đời reader để có thể gọi update() tại điểm cần kiểm tra.

## 9. Kiểm thử nhiều file và thứ tự item

Tạo hai file với nội dung khác nhau:

~~~java
@Test
void readsEveryRecordFromEveryResource() throws Exception {
    Path fileA = writeCsv(
        "orders-a.csv",
        "orderId,amount",
        "A-1,10",
        "A-2,20"
    );

    Path fileB = writeCsv(
        "orders-b.csv",
        "orderId,amount",
        "B-1,30",
        "B-2,40"
    );

    Resource[] resources = {
        new FileSystemResource(fileB),
        new FileSystemResource(fileA)
    };

    Arrays.sort(
        resources,
        Comparator.comparing(Resource::getDescription)
    );

    MultiResourceItemReader<String> reader = newReader(resources);

    assertThat(readAll(reader))
        .containsExactly(
            "A-1,10",
            "A-2,20",
            "B-1,30",
            "B-2,40"
        );
}
~~~

Test xác nhận ba điều cùng lúc:

1. Mỗi resource đều được mở.
2. Header được bỏ qua ở từng file.
3. Item được phát theo thứ tự resource đã xác định và thứ tự record bên trong file.

Nếu ứng dụng yêu cầu xử lý file theo ngày hoặc theo sequence number, hãy tạo test với tên file thể hiện quy tắc đó thay vì chỉ dựa vào alphabetic order.

## 10. Kiểm thử pattern chỉ lấy file mong muốn

Khi danh sách đến từ wildcard, nên test cả file phù hợp và file không phù hợp:

~~~java
@Test
void patternSelectsOnlyCsvFiles() throws Exception {
    writeCsv("orders-a.csv", "id", "A-1");
    writeCsv("orders-b.csv", "id", "B-1");
    writeCsv("orders-a.done", "marker");
    writeCsv("readme.txt", "not an input");

    ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

    Resource[] resources = resolver.getResources(
        tempDir.toUri().toString() + "*.csv"
    );

    assertThat(resources)
        .extracting(Resource::getFilename)
        .containsExactlyInAnyOrder(
            "orders-a.csv",
            "orders-b.csv"
        );
}
~~~

Assertion dùng containsExactlyInAnyOrder để chỉ kiểm tra tập file được chọn. Thứ tự cần được kiểm tra riêng sau bước sort. Không nên dùng một assertion không phân biệt thứ tự rồi suy luận rằng reader cũng sẽ đọc theo thứ tự đó.

## 11. Kiểm thử danh sách resource rỗng

Không có resource có thể mang hai ý nghĩa:

- Không có file đến là tình huống hợp lệ, ví dụ ngày đó không phát sinh dữ liệu.
- Không có file là lỗi vận hành, ví dụ upstream chưa giao batch bắt buộc.

strict quyết định cách MultiResourceItemReader xử lý khi danh sách rỗng. Với strict mode, reader từ chối mở; nếu tắt strict, reader có thể kết thúc ngay mà không phát item.

Test strict mode:

~~~java
@Test
void rejectsEmptyResourceListWhenStrict() {
    MultiResourceItemReader<String> reader =
        new MultiResourceItemReaderBuilder<String>()
            .name("emptyReader")
            .resources(new Resource[0])
            .delegate(csvDelegate())
            .strict(true)
            .saveState(true)
            .build();

    assertThatThrownBy(
        () -> reader.open(new ExecutionContext())
    ).isInstanceOf(IllegalStateException.class);
}
~~~

Test cho input rỗng hợp lệ:

~~~java
@Test
void returnsNoItemsWhenEmptyListIsAllowed() throws Exception {
    MultiResourceItemReader<String> reader =
        new MultiResourceItemReaderBuilder<String>()
            .name("optionalReader")
            .resources(new Resource[0])
            .delegate(csvDelegate())
            .strict(false)
            .saveState(true)
            .build();

    ExecutionContext context = new ExecutionContext();
    reader.open(context);

    try {
        assertThat(reader.read()).isNull();
    } finally {
        reader.close();
    }
}
~~~

Không tắt strict chỉ để job không báo lỗi. Policy phải phản ánh yêu cầu nghiệp vụ; nếu input bắt buộc, không có file nên làm step fail rõ ràng.

## 12. Phân biệt không tìm thấy file với resource không tồn tại

Hai tình huống này khác nhau:

| Tình huống | Ví dụ | Nơi cần kiểm thử |
|---|---|---|
| Pattern không khớp file nào | *.csv nhưng thư mục chỉ có .txt | Resource resolver và strict list policy |
| Danh sách có resource nhưng file đã bị xóa | Resolver trả resource, sau đó file biến mất | Delegate reader khi mở resource |
| Resource không thể đọc | Thiếu quyền hoặc lỗi storage | Mở resource và xử lý lỗi I/O |
| File có tồn tại nhưng nội dung sai | CSV malformed hoặc encoding không đúng | Delegate reader và mapping |

Một Resource object có thể được tạo ngay cả khi file không tồn tại. Vì vậy, chỉ kiểm tra resources.length > 0 không chứng minh mọi file đều mở được.

Có thể xác thực trước khi chạy:

~~~java
for (Resource resource : resources) {
    if (!resource.exists() || !resource.isReadable()) {
        throw new IllegalStateException(
            "Input resource is missing or unreadable: "
                + resource.getDescription()
        );
    }
}
~~~

Đây là kiểm tra sớm, nhưng vẫn có thể xảy ra race condition: file bị xóa hoặc quyền thay đổi sau validation. Delegate vẫn phải xử lý lỗi mở resource thực tế.

## 13. Kiểm thử header được bỏ qua ở từng file

Nếu mỗi CSV có header, delegate cần áp dụng linesToSkip cho mỗi resource. Đây là điểm quan trọng vì wrapper mở lại delegate khi chuyển sang file kế tiếp.

Test nên có header khác nhau để chứng minh header của file thứ hai không bị đọc như data:

~~~java
@Test
void skipsHeaderForEveryResource() throws Exception {
    Path fileA = writeCsv(
        "a.csv",
        "id,name",
        "A-1,An"
    );

    Path fileB = writeCsv(
        "b.csv",
        "order_id,customer",
        "B-1,Binh"
    );

    Resource[] resources = {
        new FileSystemResource(fileA),
        new FileSystemResource(fileB)
    };

    MultiResourceItemReader<String> reader = newReader(resources);

    assertThat(readAll(reader))
        .containsExactly("A-1,An", "B-1,Binh");
}
~~~

Trong ứng dụng thật, header có thể cần xác thực. Dùng skippedLinesCallback hoặc một bước validation riêng để kiểm tra schema của từng file. Nếu tất cả file phải có cùng schema, test nên chứng minh header không hợp lệ làm step fail.

## 14. Kiểm thử resource bị thiếu hoặc không đọc được

Với một resource tồn tại trong danh sách nhưng file không tồn tại tại thời điểm reader mở, delegate FlatFileItemReader ở strict mode sẽ báo lỗi. Test có thể tạo resource trỏ đến path chưa được tạo:

~~~java
@Test
void failsWhenListedResourceDoesNotExist() {
    Resource missing = new FileSystemResource(
        tempDir.resolve("missing.csv").toFile()
    );

    MultiResourceItemReader<String> reader =
        newReader(new Resource[] { missing });

    assertThatThrownBy(
        () -> reader.open(new ExecutionContext())
    ).isInstanceOf(RuntimeException.class);
}
~~~

Trong test production, có thể assert loại exception cụ thể theo phiên bản Spring Batch và cách delegate mở resource. Điều quan trọng là xác nhận step không âm thầm coi file bắt buộc bị thiếu như một resource rỗng.

Không nên dựa vào test permission trên Windows/Linux vì quyền truy cập của tài khoản chạy test có thể làm kết quả khác nhau. Nếu cần test lỗi I/O, dùng một Resource giả có hành vi mở stream thất bại có kiểm soát.

## 15. Kiểm thử delegate đọc lỗi ở một file

Resource list có thể hợp lệ nhưng một file trong danh sách chứa record lỗi. Hãy kiểm thử rằng exception được báo đúng và không làm các file trước đó bị đọc lại ngoài policy.

Ví dụ delegate LineMapper có thể parse số tiền và ném lỗi khi giá trị không hợp lệ:

~~~java
delegate.setLineMapper((line, lineNumber) -> {
    String[] fields = line.split(",");
    if (fields.length != 2) {
        throw new IllegalArgumentException(
            "Invalid record at line " + lineNumber
        );
    }
    return fields[0] + ":" + new BigDecimal(fields[1]);
});
~~~

Với file đầu vào có schema cố định, nên dùng tokenizer/mapper thực tế thay cho split trong code production. Đoạn code trên chỉ minh họa một mapper dễ kiểm soát trong test.

Nếu step cho phép skip lỗi record, hãy test skip policy ở cấp step và xác nhận SkipListener nhận lỗi phù hợp. Không nhầm lỗi parse một record với lỗi mở resource hoặc lỗi đọc toàn bộ file.

## 16. Kiểm thử checkpoint khi restart giữa một resource

MultiResourceItemReader lưu state của resource hiện tại và delegate. Khi restart, nó cần mở đúng resource và khôi phục vị trí bên trong resource đó.

Test reader trực tiếp có thể dùng một ExecutionContext chung:

~~~java
@Test
void resumesWithinCurrentResourceFromSavedContext() throws Exception {
    Resource[] resources = sortedResources(fileA, fileB);

    ExecutionContext context = new ExecutionContext();
    MultiResourceItemReader<String> firstRun = newReader(resources);

    firstRun.open(context);
    try {
        assertThat(firstRun.read()).isEqualTo("A-1");
        firstRun.update(context);
    } finally {
        firstRun.close();
    }

    MultiResourceItemReader<String> restarted = newReader(resources);
    restarted.open(context);
    try {
        assertThat(restarted.read()).isEqualTo("A-2");
        assertThat(restarted.read()).isEqualTo("B-1");
    } finally {
        restarted.close();
    }
}
~~~

Test này kiểm tra việc reader khôi phục từ context sau khi update được gọi. Nó chưa chứng minh transaction commit và JobRepository hoạt động đúng; phần đó cần integration test với step thật.

sortedResources(...) là helper tạo Resource[] theo thứ tự ổn định, giống quy tắc mà job production sử dụng.

## 17. Kiểm thử checkpoint sau khi chuyển sang resource tiếp theo

Trường hợp quan trọng khác là checkpoint được tạo sau khi reader đã đọc hết một file và bắt đầu file tiếp theo. Khi restart, wrapper cần chọn đúng resource hiện tại và delegate phải tiếp tục đúng vị trí.

Ví dụ với hai file:

~~~text
a.csv: A-1, A-2
b.csv: B-1, B-2

Lần chạy:
  đọc A-1
  đọc A-2
  chuyển sang b.csv
  đọc B-1
  update checkpoint

Restart:
  mở b.csv
  khôi phục delegate state
  đọc tiếp B-2
~~~

Nên có test riêng cho ranh giới resource vì lỗi thường xuất hiện khi wrapper cập nhật resource index và delegate state không đồng bộ. Dùng cùng reader name, cùng resource order và cùng context trong hai lần mở.

Nếu test cho thấy item đầu của file hiện tại bị lặp hoặc bị bỏ qua, hãy kiểm tra delegate có được đăng ký đúng lifecycle hay không và resource list có giữ nguyên thứ tự hay không.

## 18. Resource list phải giữ nguyên khi restart

Checkpoint của multi-resource reader có thể chứa index của resource hiện tại. Nếu danh sách resource thay đổi, index cũ có thể trỏ tới file khác.

Ví dụ:

~~~text
Lần chạy đầu:
  [a.csv, b.csv, c.csv]
  resourceIndex = 1  -> b.csv

Trước khi restart:
  [0-new.csv, a.csv, b.csv, c.csv]

Restart:
  resourceIndex = 1  -> a.csv
~~~

Reader có thể tiếp tục từ một file không tương ứng với checkpoint cũ. Vì vậy, test restart phải mô phỏng trường hợp resource list thay đổi và xác nhận ứng dụng phát hiện hoặc từ chối tình huống đó.

Các cách giữ ổn định:

- Tạo manifest bất biến trước khi launch.
- Lưu manifest ID hoặc source batch ID trong identifying JobParameters.
- Giữ danh sách file và thứ tự đến khi JobInstance hoàn tất.
- Lưu checksum/version nếu nội dung file có thể bị thay thế.
- Không thêm file mới vào đầu danh sách của một batch đang restart.

Không chỉ sort lại danh sách ở mỗi lần chạy rồi cho rằng restart đã an toàn. Nếu tập file thay đổi, thứ tự ổn định vẫn không bảo đảm cùng input.

## 19. Kiểm thử manifest thay cho wildcard động

Với batch quan trọng, manifest thường là cách rõ ràng hơn wildcard. Manifest ghi lại các file thuộc batch và thứ tự của chúng.

~~~text
batchId: B-2026-11-15
files:
  - orders-001.csv
  - orders-002.csv
  - orders-003.csv
~~~

Resolver đọc manifest rồi tạo resource theo đúng thứ tự đã lưu. Test nên xác nhận:

- Manifest thiếu file thì fail với tên file cụ thể.
- Manifest có file trùng thì policy deduplicate hoặc fail rõ ràng.
- File ngoài manifest không được đọc.
- Thứ tự manifest được giữ nguyên.
- Restart dùng lại cùng manifest version.

Cách này tránh việc một file mới được đưa vào thư mục giữa hai lần chạy và vô tình trở thành một phần của cùng JobInstance.

## 20. Kiểm thử resource trùng lặp

Nếu danh sách chứa cùng một file hai lần, MultiResourceItemReader có thể đọc file đó hai lần. Có thể do pattern chồng lấn, manifest bị lặp hoặc resolver ghép nhiều nguồn.

Ví dụ:

~~~java
Resource resource = new FileSystemResource(fileA);

Resource[] resources = {
    resource,
    resource,
    new FileSystemResource(fileB)
};
~~~

Cần xác định policy của ứng dụng:

- Từ chối danh sách trùng để tránh import duplicate.
- Deduplicate theo URI chuẩn hóa hoặc file identity.
- Cho phép trùng nếu mỗi lần xuất hiện có ý nghĩa nghiệp vụ riêng.

Không deduplicate chỉ bằng getFilename() nếu hai thư mục có thể chứa file cùng tên. Dùng URI/canonical path hoặc một source ID ổn định.

Test nên tạo hai resource trỏ cùng file nhưng khác object instance và xác nhận resolver xử lý theo policy đã chọn.

## 21. Kiểm thử nhiều resource với schema khác nhau

Nếu mỗi file có header hoặc schema version khác nhau, một delegate cố định có thể không đủ. Có thể cần bước validation trước, hoặc một reader/mapping strategy có thể chọn theo metadata của resource.

Không nên cho phép mỗi file có cấu trúc tùy ý rồi hy vọng cùng một LineMapper xử lý được. Hãy xác định:

- Tất cả file có cùng schema version hay không.
- Có file header khác nhau nhưng cùng column mapping không.
- Có cần map theo version của từng file không.
- Một file không hợp lệ làm fail cả step hay chỉ bị loại khỏi manifest.

Test nên có ít nhất một file cho mỗi schema version được hỗ trợ và một file có version không được hỗ trợ. Nếu schema không được hỗ trợ, fail sớm trước khi ghi dữ liệu.

## 22. Kiểm thử ResourceAware delegate lifecycle

Delegate reader cần nhận resource hiện tại trước khi được mở. Với custom delegate, test có thể xác nhận setResource, open, read, update và close được gọi đúng thứ tự.

Nếu dùng mock để kiểm tra tương tác, chỉ mock delegate khi mục tiêu là xác nhận orchestration của wrapper. Không dùng mock thay cho mọi test vì như vậy không kiểm tra được file I/O, header, encoding và checkpoint thật.

Với delegate tự viết, hãy kiểm tra:

- Resource mới được gán trước mỗi lần open.
- Resource trước được đóng khi chuyển sang file kế tiếp.
- update lưu state của resource hiện tại.
- close giải phóng delegate khi step kết thúc.
- Exception trong delegate được truyền lên step và resource được cleanup phù hợp.

## 23. Kiểm thử qua Spring Batch step và JobRepository

Unit test gọi open/read/update/close rất hữu ích, nhưng không xác nhận transaction, checkpoint và restart của cả job. Nên có ít nhất một integration test khởi chạy step thật với JobRepository và transaction manager.

Có thể dùng @SpringBatchTest và JobLauncherTestUtils nếu dự án đã có Spring Batch Test:

~~~java
@SpringBatchTest
@SpringBootTest
class MultiResourceJobRestartTests {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void restartsFromCommittedMultiResourceCheckpoint() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("manifestId", "batch-001", true)
            .toJobParameters();

        JobExecution first =
            jobLauncherTestUtils.launchJob(parameters);

        assertThat(first.getStatus())
            .isEqualTo(BatchStatus.FAILED);

        JobExecution restarted =
            jobLauncherTestUtils.launchJob(parameters);

        assertThat(restarted.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    }
}
~~~

Ví dụ giả định job test được cấu hình để lần chạy đầu thất bại có chủ đích sau ít nhất một chunk commit, sau đó lần restart có thể tiếp tục. Cơ chế fail-once nên được kiểm soát bằng test fixture và không ảnh hưởng test khác.

Hai lần launch dùng cùng identifying JobParameters để tiếp tục cùng JobInstance. Nếu thay manifestId bằng giá trị identifying mới, test sẽ tạo instance khác và không kiểm tra restart.

Integration test cần xác nhận thêm dữ liệu đầu ra, không chỉ status:

- Các record thuộc chunk đã commit không bị ghi lại ngoài policy.
- Record của chunk chưa commit được xử lý lại.
- Resource index và delegate checkpoint được khôi phục.
- Step execution đầu tiên và lần restart thuộc cùng JobInstance.
- File nguồn và manifest giống nhau giữa hai lần chạy.

## 24. Kiểm thử JobParameters và resource manifest

Nếu resource directory hoặc manifest được truyền qua JobParameters, cần test cả việc chọn resource và identity của job.

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("manifestId", "batch-001", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
~~~

manifestId được đánh dấu identifying vì nó xác định tập file của lần xử lý. requestedBy chỉ là thông tin audit nên không cần tạo JobInstance mới khi thay đổi.

Test nên xác nhận:

- Cùng manifest ID và cùng job name tìm lại cùng JobInstance khi restart.
- Manifest ID khác tạo JobInstance mới.
- Manifest không tồn tại làm job fail trước khi ghi dữ liệu.
- Manifest có file bị thiếu không bị âm thầm bỏ qua.
- Manifest version không đổi trong khi JobInstance còn có thể restart.

## 25. Kiểm thử encoding và nội dung file

Danh sách resource đúng chưa đủ; mỗi file phải được đọc với encoding và parser đúng. Nên tạo file test có ký tự Unicode, dấu tiếng Việt và dữ liệu có dấu phân cách.

~~~java
Files.writeString(
    file,
    "id,name\nA-1,Nguyễn An\n",
    StandardCharsets.UTF_8
);
~~~

Kiểm tra delegate có cấu hình cùng encoding:

~~~java
delegate.setEncoding(StandardCharsets.UTF_8.name());
~~~

Nếu file nguồn có BOM, CRLF, header nhiều dòng hoặc delimiter đặc thù, tạo fixture thực tế để xác nhận từng file được đọc giống nhau. Không chỉ kiểm tra file đầu tiên vì delegate được mở lại cho từng resource.

## 26. Kiểm thử hiệu năng và số lượng resource

Với hàng trăm hoặc hàng nghìn file, cần kiểm tra chi phí discovery, sorting, mở/đóng file và restart. Không nhất thiết tạo hàng triệu record trong unit test; có thể benchmark riêng với số lượng resource gần production.

Các chỉ số hữu ích:

- Thời gian resolver tạo danh sách resource.
- Số resource được chọn và số resource bị loại.
- Thời gian mở/đóng từng resource.
- Tổng item và item theo file.
- Thời gian restart khi checkpoint ở file gần cuối.
- Số connection/thread nếu job kết hợp partitioning.
- Bộ nhớ khi manifest hoặc danh sách resource lớn.

Nếu danh sách rất lớn, tránh log toàn bộ path ở mỗi lần chạy. Ghi count, manifest ID, checksum và một số mẫu để điều tra; lưu manifest đầy đủ ở nơi có thể truy xuất.

## 27. MultiResourceItemReader không tự chạy song song

MultiResourceItemReader thường điều phối đọc tuần tự qua danh sách resource. Nó không tự tạo thread cho mỗi file.

Nếu cần xử lý file song song, có thể partition theo resource hoặc nhóm resource để mỗi worker step có reader riêng. Khi đó cần kiểm thử:

- Mỗi resource chỉ được gán cho worker theo policy.
- Mỗi worker có StepExecution và ExecutionContext riêng.
- Không có hai worker cùng ghi cùng output nếu không được thiết kế.
- Mỗi partition có transaction/checkpoint độc lập.
- Lỗi một partition không làm mất kết quả đã commit của partition khác.
- Danh sách resource và partition assignment ổn định khi restart.

Không chia sẻ một delegate reader stateful giữa các worker. FlatFileItemReader và nhiều reader tương tự không được thiết kế để nhiều thread gọi read() đồng thời trên cùng instance.

## 28. Kiểm thử lỗi và cleanup khi chuyển resource

Khi delegate đọc file A xong và chuyển sang file B, reader phải đóng resource A trước khi mở B. Nếu mở B thất bại, step cần báo lỗi và cleanup resource đang mở phù hợp.

Các test nên mô phỏng:

1. File đầu đọc thành công, file thứ hai không tồn tại.
2. File đầu đọc thành công, file thứ hai không có quyền đọc.
3. Delegate ném lỗi khi parse record ở file giữa danh sách.
4. Step bị dừng khi delegate đang mở một resource.
5. Reader được đóng sau EOF bình thường.
6. Restart trong file thứ hai và lỗi mở file thứ hai.

Có thể dùng một custom Resource test double để kiểm soát lỗi getInputStream(). Với lỗi filesystem thật, nên tránh dựa vào permission bits vì kết quả khác nhau theo OS và tài khoản chạy test.

## 29. Bảng test case đề xuất

| Nhóm | Tình huống | Kết quả cần xác nhận |
|---|---|---|
| Discovery | Pattern có nhiều file phù hợp | Chọn đủ resource |
| Filtering | Có file .txt, .done, .tmp | Không lấy file ngoài policy |
| Ordering | Resolver trả về thứ tự không ổn định | Reader phát item theo thứ tự đã sort |
| Empty | Danh sách rỗng, strict bật | Reader fail khi mở |
| Empty | Danh sách rỗng, strict tắt | Reader trả EOF |
| Missing | Resource trong danh sách đã bị xóa | Delegate báo lỗi mở file |
| Header | Mỗi file có header | Header được bỏ qua ở từng resource |
| Parsing | File có record malformed | Exception/skip theo policy |
| Duplicate | Cùng file xuất hiện hai lần | Resolver áp dụng policy duplicate |
| Restart | Checkpoint giữa một file | Tiếp tục từ item sau checkpoint |
| Restart | Checkpoint sau khi chuyển file | Khôi phục đúng resource và delegate state |
| Manifest | Danh sách thay đổi giữa hai execution | Phát hiện hoặc từ chối restart không an toàn |
| Integration | Chunk đầu commit, chunk sau fail | Restart giữ chunk đã commit và xử lý lại chunk chưa commit |
| Parallel | Partition theo resource | Mỗi worker có state/resource riêng |

## 30. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dựa vào thứ tự resolver trả về | Kết quả khác nhau giữa môi trường | Sort theo khóa ổn định hoặc dùng manifest |
| Chỉ test resource đầu tiên | Lỗi ở file sau không được phát hiện | Tạo fixture có nhiều resource |
| Chỉ kiểm tra số resource | Không phát hiện file sai nội dung hoặc không đọc được | Đọc thực tế qua delegate |
| Dùng strict(false) cho input bắt buộc | Không có file nhưng job có thể hoàn tất rỗng | Chọn strict policy theo nghiệp vụ |
| Nghĩ resource object tồn tại nghĩa là file tồn tại | File có thể đã bị xóa trước khi open | Kiểm tra và xử lý lỗi mở resource |
| Thay danh sách file trước restart | Resource index trỏ sang file khác | Giữ manifest/input bất biến |
| Không sort resource | Thứ tự item không xác định | Dùng comparator rõ ràng |
| Không kiểm tra header ở từng file | Header của file sau có thể bị ghi thành data | Cấu hình skip/validate header cho mỗi resource |
| Mock toàn bộ delegate | Không kiểm tra file I/O và parsing | Kết hợp unit test với file fixture thật |
| Chia sẻ reader giữa worker | Race condition và sai checkpoint | Mỗi partition có reader riêng |
| Chỉ assert job COMPLETED | Có thể bỏ sót duplicate hoặc record thiếu | Assert dữ liệu và checkpoint cuối |

## 31. Quy trình xây dựng test cho resource list

Khi thêm một multi-resource step, có thể triển khai test theo thứ tự:

1. Tạo helper tạo file fixture trong @TempDir.
2. Kiểm thử resolver/pattern để xác nhận đúng tập resource.
3. Kiểm thử sort và thứ tự item qua nhiều file.
4. Kiểm thử header, encoding và parser trên từng resource.
5. Kiểm thử danh sách rỗng theo cả strict và non-strict policy.
6. Kiểm thử resource bị thiếu, không đọc được và record lỗi.
7. Kiểm thử duplicate resource và manifest validation.
8. Kiểm thử ExecutionContext restart trong cùng file và sau khi chuyển file.
9. Thêm integration test với JobRepository, chunk commit và restart.
10. Nếu có partitioning, kiểm thử assignment và state độc lập của từng worker.

Giữ nguyên resource resolver, comparator, delegate reader name và manifest semantics giữa test và production. Nếu test tạo một danh sách khác với cách job thật tạo resource, kết quả test có thể không phản ánh hành vi triển khai.

## Kết luận

Kiểm thử danh sách resource trong Spring Batch cần xác nhận cả tập resource, thứ tự xử lý, khả năng mở/đọc từng file và checkpoint khi restart. MultiResourceItemReader điều phối qua Resource[], còn delegate reader chịu trách nhiệm parse nội dung từng resource. Hãy dùng @TempDir và file fixture thật để kiểm tra resolver, header, encoding, strict mode, missing resource và thứ tự item.

Đối với restart, giữ danh sách resource và thứ tự bất biến, dùng cùng identifying JobParameters, bật saveState và kiểm tra cả resource index lẫn state của delegate qua ExecutionContext. Unit test xác nhận hành vi reader; integration test với JobRepository xác nhận transaction, checkpoint và restart của step. Nếu xử lý song song, mỗi partition cần reader và state riêng.
