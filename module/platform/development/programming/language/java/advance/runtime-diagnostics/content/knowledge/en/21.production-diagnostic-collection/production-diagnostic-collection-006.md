# 21.6. Đặt tên file kèm PID, thời gian, phiên bản ứng dụng và hành động đã thực hiện

## 1. Vì sao quy ước tên file là một phần của chẩn đoán production?

Khi vận hành ứng dụng Java, cùng một sự cố có thể tạo ra nhiều hiện vật (*diagnostic artifacts*): thread dump, heap dump, bản ghi Java Flight Recorder (JFR), kết quả `jcmd`, GC log, báo cáo native memory và ảnh chụp cấu hình. Chúng có thể được thu từ **nhiều JVM, nhiều pod, nhiều phiên bản triển khai và nhiều thời điểm**. Nếu chỉ đặt tên `dump.txt`, `heap.hprof` hoặc `recording.jfr`, kỹ sư rất dễ so nhầm hai tiến trình, mất thứ tự thời gian, ghi đè file hoặc gửi sai chứng cứ cho một incident.

Mục tiêu của bài: thiết kế một **tên file có thể đọc nhanh bằng mắt, tự động phân loại được và không làm mất ngữ cảnh**, trong đó có ít nhất:

- **PID** của **JVM đích** (không vô tình lấy PID của script thu thập).
- **Thời gian** thu thập, định dạng rõ timezone, ưu tiên UTC.
- **Phiên bản ứng dụng** hoặc mã build đã chạy tại thời điểm lấy dữ liệu.
- **Hành động đã thực hiện**, ví dụ `thread-dump`, `heap-dump`, `jfr-dump` hoặc `vm-flags`.

Để tránh trùng tên, quy ước còn thêm **service**, **môi trường**, **instance** và **capture ID**. Bài cũng giải thích vì sao tên file chỉ là *nhãn tra cứu*, cần một manifest/metadata và cơ chế ghi an toàn để chứng cứ đáng tin.

Sau khi học, bạn có thể:

1. Nhìn tên file và phân biệt bản ghi của các pod/JVM, thời điểm, bản phát hành và loại hành động.
2. Tạo filename an toàn trên Windows/Linux/container, không ghi đè, không đưa dữ liệu bí mật vào path.
3. Gắn tên file với **đúng thời điểm và đúng PID** dù lệnh được gọi từ máy quản trị, container hoặc JVM đích.
4. Xây một manifest liên kết file, lệnh, người thu, status, kích thước, checksum, incident và chính sách bảo mật.
5. Chạy mã Java 17+ tạo tên chuẩn, dùng `CREATE_NEW` và chứng minh tên trùng **không** được ghi đè.
6. Thiết kế một quy trình hoàn tất/tải lên/xóa artifact có thể audit, không coi việc đặt tên là bằng chứng file thu thành công.

Phạm vi tập trung vào **định danh và quản lý file chẩn đoán khi vận hành Java**. Đừng chạy heap dump hoặc debugger trên production chỉ để thử quy ước tên: một số lệnh có tác động lớn, cần phê duyệt riêng.

## 2. Quy ước tên file đề xuất

Cấu trúc nhất quán:

~~~text
<service>__<environment>__<instance>__pid-<pid>__<utc-time>__<version>__<action>__<capture-id>.<extension>
~~~

Dấu phân cách giữa các thành phần là **hai dấu gạch dưới `__`**. Ví dụ có dữ liệu minh họa, không phải file của hệ thống thực:

~~~text
orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__thread-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.txt
orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__jfr-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.jfr
orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__heap-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.hprof
~~~

Các ví dụ trên dùng **cùng capture ID để minh họa một lần thu có nhiều hiện vật**, với `action` khác nhau. Trong quy trình thực, nếu mỗi artifact cần một ID riêng, lưu thêm `collectionId` chung trong manifest, còn `captureId` là riêng cho từng file. Quan trọng nhất là **định nghĩa rõ ID biểu diễn một file hay một phiên** và áp dụng thống nhất; không để hai job đồng thời tạo trùng cùng một tên.

### 2.1. Ý nghĩa và nguồn sự thật của từng trường

| Thành phần | Ví dụ | Nguồn tin cậy ưu tiên | Những điều không được suy đoán |
| --- | --- | --- | --- |
| `service` | `orders-api` | Service identifier trong deployment/inventory | Tên class main không luôn trùng tên service |
| `environment` | `prod` | Metadata môi trường do platform quản lý | Không đoán từ hostname hay port |
| `instance` | `pod-7c2` | Pod/instance ID hoặc mã rút gọn có mapping ổn định | Một service có thể có nhiều JVM trên một instance |
| `pid` | `pid-3142` | PID **JVM đích** trong namespace được ghi rõ | PID máy operator hoặc PID host không nhất thiết bằng PID trong container |
| `utc-time` | `20261029T095501.123Z` | Đồng hồ theo UTC tại **thời điểm đã định nghĩa** | Giờ local không có offset không đủ để so chéo cụm |
| `version` | `v2.8.1` | Build/release metadata của **binary đang chạy** | Không lấy version app từ `java -version` |
| `action` | `thread-dump` | Danh sách hành động cho phép (*enum/registry*) | Không chép nguyên command line chứa tùy chọn và secret |
| `capture-id` | 32 ký tự hex | UUID/random ID do hệ thống thu tạo | PID + mili-giây không bảo đảm tính duy nhất |
| `extension` | `txt`, `jfr`, `hprof` | Định dạng thực được tạo | Không đổi phần mở rộng để giả định format khác |

Một quy ước dễ đọc phải có **ngữ nghĩa ổn định**, không chỉ cố nhét càng nhiều trường càng tốt. Các trường dài như đường dẫn đầy đủ, tên namespace, commit SHA 40 ký tự, incident ID hoặc command options nên nằm trong **manifest** nếu làm filename quá dài. Tên file cung cấp thông tin định hướng; manifest là bản ghi chính xác hơn về quá trình thu.

### 2.2. Khi nào cần thêm cluster/region/node?

Với nhiều cluster hoặc region, có thể thêm `cluster`/`region` vào **đường thư mục** thay vì mỗi filename:

~~~text
diagnostics/
  prod/
    ap-southeast/
      cluster-blue/
        orders-api/
          2026/10/29/
            orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__thread-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.txt
~~~

Đây chỉ là cây thư mục minh họa. Nếu file có thể được tải xuống hoặc chuyển khỏi cây này, **không đặt toàn bộ định danh quan trọng chỉ trong tên thư mục**. Có thể giữ `cluster` và `region` trong manifest và tên object ở kho lưu trữ được quản lý. Tránh tạo đường dẫn quá sâu vượt giới hạn OS/tooling và tránh đưa hostname nội bộ nhạy cảm vào nơi công khai.

## 3. PID: định danh tiến trình, không phải định danh vĩnh viễn

### 3.1. Phải ghi PID của JVM nhận lệnh

Có ba PID dễ bị nhầm:

1. **Target JVM PID:** tiến trình Java mà thread dump/heap dump/JFR được thu từ đó.
2. **Collector PID:** tiến trình `jcmd`, script Python/Bash/PowerShell hoặc chương trình Java chạy thu thập.
3. **Host PID và container PID:** cùng một JVM có thể hiện dưới PID khác nhau trong namespace host và container.

Ví dụ một worker chạy `jcmd 3142 Thread.print`, trong khi `ProcessHandle.current().pid()` ở **chương trình collector** có thể là 8921. Nếu filename là `pid-8921`, bài điều tra sẽ dẫn tới tiến trình sai. Khi chạy lệnh từ ngoài, phải lấy target PID từ **đối tượng được chọn** hoặc tham số đã xác minh, không tự gọi `current()` rồi gắn cho JVM khác.

Java 17+ có `ProcessHandle.current().pid()` để lấy PID **của chính tiến trình Java đang chạy đoạn code đó**. Điều này chính xác nếu chính JVM tạo artifact của nó, nhưng **không phải** API lấy PID từ một JVM remote. Nếu dùng `ProcessHandle.of(targetPid)`, hãy nhớ PID có thể được OS tái sử dụng và trạng thái process có thể thay đổi giữa kiểm tra và chạy lệnh.

### 3.2. PID có thể trùng theo thời gian

PID không phải ID toàn cục:

- OS có thể tái sử dụng PID sau khi process kết thúc.
- Nhiều host hoặc container có thể cùng có PID `1`, `3142`...
- Trong Kubernetes, JVM PID nhìn từ bên trong pod có thể khác host PID.
- Process có thể restart giữa lúc bạn lấy metadata và lúc lệnh dump thực sự chạy.

**Vì thế tên nên đi kèm `instance`, UTC timestamp, capture ID và nếu có `processStartTime` trong manifest.** Một service restart cùng pod và PID có thể vẫn được phân biệt bởi process start time, build/run identity và capture ID.

Khi gửi lệnh `jcmd`, xác minh đúng PID/VM theo quyền được cấp; trên HotSpot có thể dùng `jcmd <pid> VM.version` và `VM.command_line` phù hợp policy. Không thu thập full `VM.system_properties` bừa bãi vì có thể chứa thông tin nhạy cảm. Nếu một lệnh attach thất bại, không được thay bằng một PID “gần giống” đoán từ tên Java.

## 4. Thời gian: UTC, độ phân giải và ý nghĩa của timestamp

Đề xuất format filename là:

~~~text
uuuuMMdd'T'HHmmss.SSS'Z'
20261029T095501.123Z
~~~

Nó có ưu điểm: không chứa `:` hay `/` vốn khó dùng làm filename trên một số OS, giữ thứ tự từ năm đến mili-giây và có ký hiệu `Z` chỉ UTC. Với cùng quy tắc format, **sắp theo tên của cùng một service/instance** thường cũng sắp theo timestamp.

- Trong Java: `Instant.now()` là thời điểm UTC, được format bằng `DateTimeFormatter` với `ZoneOffset.UTC`.
- `Z` chỉ có ý nghĩa đúng nếu **thật sự format UTC**; đừng nối chữ `Z` vào giờ local.
- Dùng **cùng một timestamp** từ lúc khởi tạo cuộc thu cho mọi artifact liên quan nếu quy tắc của bạn nói `utc-time` là `captureStartedAt`; ghi thêm `captureCompletedAt` trong manifest.
- Nếu tên file biểu thị thời điểm **kết thúc ghi** thay vì bắt đầu, đổi tên trường/tiêu chuẩn và bảo đảm mọi collector cùng hiểu.

**Mẫu nên chốt:** `utc-time` trong filename là **thời điểm bắt đầu hành động thu**. Thời điểm hoàn tất, thời gian từ khi ra lệnh đến khi JVM trả kết quả, time window mà JFR chứa và mốc file được tải lên **không phải cùng một thời điểm**.

### 4.1. Với JFR: cửa sổ sự kiện có thể khác thời điểm dump

Giả sử một JFR recording chạy 14:00–14:30 UTC và operator gọi `JFR.dump` lúc 14:25. File có thể chứa sự kiện trước 14:25, phụ thuộc retention và tùy chọn dump. Filename `...T142500Z...jfr-dump...` chỉ xác định **hành động xuất snapshot**, không đại diện chính xác khoảng thời gian dữ liệu bên trong. Manifest nên ghi `recordingStartedAt`, `recordingEndedAt` hoặc thời điểm event min/max khi đã kiểm tra.

### 4.2. Độ phân giải mili-giây không phải cơ chế chống trùng

Hai collector có thể bắt đầu trong cùng mili-giây, hoặc nhiều lệnh xuất cùng một tên do job retry. Không dựa vào `yyyyMMddHHmmssSSS` để bảo đảm không trùng. Thêm **capture ID** và dùng thao tác ghi **không ghi đè nếu đã tồn tại**. UUID giúp xác suất trùng cực thấp nhưng vẫn cần xử lý lỗi `FileAlreadyExistsException`/storage conflict.

### 4.3. Clock skew và thứ tự sự kiện

Giữa các node, đồng hồ có thể lệch dù đều dùng UTC. Nếu cần chứng minh thứ tự chính xác cho sự cố phân tán, kết hợp NTP/clock health, time sync, tracing correlation, build/deploy timeline và event timestamps bên trong artifact. Filename **không chứng minh** quan hệ happens-before giữa hai JVM.

## 5. Phiên bản ứng dụng: không nhầm với JDK và image tag

Có ít nhất bốn version:

| Nhãn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `appVersion` | `v2.8.1` | Phiên bản logic của ứng dụng |
| `buildId` | `build-483` | ID pipeline/build |
| `commitSha` | `6a2f...` | Commit nguồn gắn với binary |
| `jvmVersion` | `21.0.5` | JDK đang thực thi, độc lập với phiên bản ứng dụng |

Nếu deploy qua container, còn có `imageDigest` và `imageTag`; **tag có thể được gán lại**, còn digest tham chiếu content cụ thể hơn. Khi chẩn đoán bản phát hành sai, build ID/commit SHA/image digest trong manifest quan trọng hơn một nhãn app version ngắn.

Nguồn lấy app version nên được **nhúng vào artifact build** hoặc deployment metadata có kiểm chứng, ví dụ:

- Manifest JAR `Implementation-Version` hoặc tệp generated version trong build.
- Biến môi trường do pipeline thiết lập, **được kiểm tra** với image digest/build metadata.
- Release metadata/annotations trên workload, đi kèm định danh instance và thời điểm.
- Endpoint thông tin build, nếu có, với quyền và dữ liệu hạn chế.

Không khẳng định `System.getProperty("java.version")` là app version. Không copy version do người vận hành gõ mà không đối chiếu. Nếu version không lấy được, dùng một nhãn chuẩn như `unknown` trong filename và đặt `metadataStatus=missing` trong manifest, đồng thời ghi lý do. **Không tự bịa phiên bản** để tên file trông đầy đủ.

Cần thống nhất cách chuẩn hóa version khi nguồn có ký tự không hợp với filename. Ví dụ SemVer `2.8.1+build.483` có dấu `+`: có thể biểu diễn filename `v2.8.1-build.483` nhưng manifest phải lưu **giá trị gốc** `2.8.1+build.483` và mô tả quy tắc chuyển đổi. Tránh sanitizer âm thầm biến hai giá trị khác nhau thành cùng một nhãn.

## 6. Hành động đã thực hiện: dùng từ vựng có kiểm soát

`action` trả lời: “**Đã yêu cầu JVM hoặc collector làm gì để sinh file này?**” Nó không phải tên sự cố, kết luận lỗi hay tên người thực hiện.

| Action đề xuất | Dạng artifact | Ví dụ nguồn thu |
| --- | --- | --- |
| `thread-dump` | `.txt` | `jcmd <pid> Thread.print`, stdout được lưu ở collector |
| `heap-dump` | `.hprof` | `jcmd <pid> GC.heap_dump`, file do JVM đích tạo |
| `jfr-dump` | `.jfr` | `jcmd <pid> JFR.dump`, snapshot một recording |
| `jfr-stop` | `.jfr` | `JFR.stop filename=...`, kết thúc và xuất recording |
| `class-histogram` | `.txt` | `GC.class_histogram` |
| `vm-flags` | `.txt` | `VM.flags` |
| `vm-version` | `.txt` | `VM.version` |
| `nmt-summary` | `.txt` | `VM.native_memory summary` nếu NMT đã bật và có quyền |
| `gc-log-export` | `.log` hoặc `.log.gz` | Sao chép tập GC log đã có, **không tự động coi là lệnh JVM vừa chạy** |

Tên hành động nên giữ ổn định, viết chữ thường, cách nhau bởi `-`. Khi thay đổi action registry, version schema; đừng tùy tiện chuyển `heap-dump` thành `memory-dump` mà không có mapping. Không bao gồm toàn bộ command line trong tên: tham số có thể chứa đường dẫn nội bộ, token, URL chứa secret và tên quá dài.

**Đặt action theo việc làm, không theo giả thuyết:** file `heap-dump` không nên mặc định gọi `leak-confirmed.hprof` vì mới có dump, chưa chứng minh leak. Nếu cần ghi `suspectedCause`, đặt trong incident notes với trạng thái “giả thuyết”.

### 6.1. Phân biệt phần mở rộng và nội dung thực

Một `.jfr` là dữ liệu JFR; `.hprof` là heap dump định dạng HPROF; `.txt` phù hợp text dump; `.gz` là lớp nén. Nếu `GC.heap_dump -gz` tạo HPROF nén, extension cần phản ánh rõ `.hprof.gz` khi thực tế đúng định dạng, và manifest ghi compression. Đổi phần mở rộng không biến file text thành HPROF. Không tuyên bố file hợp lệ chỉ vì tên kết thúc đúng.

## 7. Tránh trùng và tránh ghi đè

Một tên có PID, thời gian và action **vẫn có thể trùng** trong retry hoặc nhiều collector chạy đồng thời. Mẫu an toàn nên có ba thành phần:

1. **ID riêng cho lần thu:** UUID 128-bit hoặc định danh tương đương có quản lý; tên file không phải khóa dữ liệu duy nhất.
2. **Tạo file không ghi đè:** khi tự tạo bằng Java, dùng `StandardOpenOption.CREATE_NEW`; nếu file tồn tại, ghi thất bại thay vì làm mất chứng cứ cũ.
3. **Trạng thái hoàn tất:** file mới bắt đầu ghi không được đem đi phân tích như kết quả hoàn tất. Chỉ publish/index sau khi lệnh thành công, đóng file, kiểm tra định dạng/kích thước và ghi manifest.

**Không làm điều này:**

~~~java
// Đoạn minh họa SAI: có race và có thể ghi đè.
if (!java.nio.file.Files.exists(destination)) {
    java.nio.file.Files.writeString(destination, report); // Mặc định có thể ghi đè.
}
~~~

Giữa `exists` và `writeString`, một collector khác có thể đã tạo file. Cần bảo vệ ở thao tác tạo file **nguyên tử theo filesystem provider**, như `CREATE_NEW`. Khi sử dụng object storage, cần cơ chế conditional put/if-none-match hoặc object key bất biến tương đương; không cho rằng API `upload()` mặc định sẽ từ chối overwrite.

### 7.1. File tạm và publish hoàn tất

Chu trình khuyến nghị:

~~~text
COLLECT_REQUESTED
       |
       v
đặt captureId + metadata + tên cuối
       |
       v
ghi vào khu vực/staging path bảo mật, tên riêng
       |
       v
collector/JVM hoàn tất thành công? ----- không ----> FAILED / PARTIAL; giữ log lỗi,
       |                                            không phát hành như file hoàn chỉnh
      có
       |
       v
xác minh artifact: tồn tại, định dạng, kích thước, checksum,
khoảng thời gian được ghi, exit status, quyền đọc
       |
       v
publish tới final path/key KHÔNG ghi đè + ghi manifest
       |
       v
READY_FOR_ANALYSIS -> RETAIN/DELETE theo policy
~~~

Nếu muốn dùng atomic rename của filesystem, staging và final nên ở **cùng filesystem** và phải kiểm tra `ATOMIC_MOVE` có được hỗ trợ không. Các ngữ nghĩa khi destination đã tồn tại có thể phụ thuộc provider; **không dùng mỗi `Files.move(..., ATOMIC_MOVE)` như bằng chứng chống overwrite**, phải có chiến lược tránh trùng/độc quyền ở đích. Di chuyển qua volume hoặc upload qua mạng có thể không atomic. Với bộ thu nhiều node, nên dùng storage API có **no-overwrite precondition** và lifecycle metadata.

Không nên pre-create một file HPROF rỗng rồi yêu cầu `GC.heap_dump` ghi đúng tên đó khi công cụ mặc định từ chối file đã tồn tại. Với lệnh **JVM tự ghi file**, chọn filename riêng trong thư mục bảo mật và dựa vào chính sách no-overwrite của command hoặc dùng staging path, không áp dụng máy móc cách mở file của collector.

### 7.2. Thất bại sau khi tạo file

Nếu `jcmd` timeout, JVM bị kill hoặc ổ đĩa hết chỗ, có thể còn file dở dang hoặc manifest chưa hoàn thành. **Không xóa âm thầm** mà bỏ mất bằng chứng lỗi; nhưng cũng không đưa partial file vào danh sách “đã thu thành công”. Đánh dấu `FAILED`/`PARTIAL`, lưu exit code và stderr đã lọc, thời điểm lỗi, cho phép cleanup theo chính sách. Nếu retry, cấp **capture ID mới** và liên kết `retryOf` với lần trước.

Một checksum SHA-256 giúp phát hiện file bị thay đổi/khác khi sao chép, nhưng **không chứng minh tính xác thực** nếu kẻ sửa file cũng được sửa checksum. Muốn chống sửa trái phép cần kho lưu trữ có quyền chặt, audit, object lock/chữ ký hoặc cơ chế integrity của tổ chức.

## 8. Java 17+: tạo tên đúng chuẩn và kiểm tra không ghi đè

Bài lab này **chỉ tạo một file text giả lập**, tuyệt đối không sinh heap dump, không attach vào JVM khác và không thao tác trên production. Chương trình có đầu vào được cố định để stdout dễ kiểm tra; trong collector thực tế hãy cấp PID JVM đích và thời gian thật **từ nguồn đã kiểm chứng**.

Tạo tệp **`DiagnosticArtifactNameDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.UUID;

public final class DiagnosticArtifactNameDemo {
    enum Action {
        THREAD_DUMP("thread-dump", "txt"),
        JFR_DUMP("jfr-dump", "jfr"),
        HEAP_DUMP("heap-dump", "hprof");

        final String slug;
        final String extension;

        Action(String slug, String extension) {
            this.slug = slug;
            this.extension = extension;
        }
    }

    private static final DateTimeFormatter UTC =
            DateTimeFormatter.ofPattern("uuuuMMdd'T'HHmmss.SSS'Z'", Locale.ROOT)
                    .withZone(ZoneOffset.UTC);

    private static String component(String label, String value) {
        if (value == null || !value.matches("[a-z0-9][a-z0-9.-]{0,62}")
                || value.endsWith(".") || value.contains("..")) {
            throw new IllegalArgumentException("Invalid " + label);
        }
        return value;
    }

    static String name(String service, String environment, String instance,
                       long targetPid, Instant capturedAt, String version,
                       Action action, UUID captureId) {
        if (targetPid <= 0 || capturedAt == null || action == null
                || captureId == null) {
            throw new IllegalArgumentException("Missing or invalid metadata");
        }
        String stem = String.join("__",
                component("service", service),
                component("environment", environment),
                component("instance", instance),
                "pid-" + targetPid,
                UTC.format(capturedAt),
                component("version", version),
                action.slug,
                captureId.toString().replace("-", ""));
        return stem + "." + action.extension;
    }

    public static void main(String[] args) throws Exception {
        Instant capturedAt = Instant.parse("2026-10-29T09:55:01.123Z");
        UUID id = UUID.fromString("f8c47de5-d7c7-4ef7-a59c-c89c935e7d2b");
        String filename = name("orders-api", "prod", "pod-7c2",
                3142L, capturedAt, "v2.8.1", Action.THREAD_DUMP, id);
        Path directory = Files.createTempDirectory("artifact-name-demo-");
        Path artifact = directory.resolve(filename);

        try {
            Files.writeString(artifact, "demo-only\n",
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            boolean duplicateRejected = false;
            try {
                Files.writeString(artifact, "do-not-overwrite",
                        StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
            } catch (FileAlreadyExistsException expected) {
                duplicateRejected = true;
            }

            System.out.println("file=" + filename);
            System.out.println("created=" + Files.isRegularFile(artifact));
            System.out.println("duplicateRejected=" + duplicateRejected);
            System.out.println("content=" +
                    Files.readString(artifact, StandardCharsets.UTF_8).strip());
        } finally {
            Files.deleteIfExists(artifact);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac DiagnosticArtifactNameDemo.java
java DiagnosticArtifactNameDemo
~~~

Stdout đã kiểm chứng với JDK 24:

~~~text
file=orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__thread-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.txt
created=true
duplicateRejected=true
content=demo-only
~~~

### 8.1. Phân tích code

- `DateTimeFormatter` dùng `uuuuMMdd'T'HHmmss.SSS'Z'` và `ZoneOffset.UTC` để tạo timestamp nhất quán; `Instant` không phụ thuộc timezone mặc định của host.
- `component(...)` từ chối dấu cách, slash, backslash, ký tự phân cách `__` và tên không phù hợp. Nó **không** thay thế một hệ thống kiểm tra path/permission tổng thể; vẫn cần cấu hình base directory cố định, không tin input không kiểm chứng và kiểm tra symlink trên môi trường có đối tượng không tin cậy.
- `targetPid=3142` trong lab là giá trị minh họa, không phải PID của JVM chạy chương trình. Trong collector thật, **không tự thay bằng `ProcessHandle.current().pid()`** nếu bạn đang ghi file cho một process khác.
- `UUID.fromString(...)` tạo capture ID cố định để output kiểm thử lặp được. Khi vận hành, mỗi lần thu cần `UUID.randomUUID()` và lưu ID tương ứng vào manifest.
- `Action` là enum giúp giới hạn từ vựng và phần mở rộng. Việc chọn extension trong enum chỉ an toàn khi loại dữ liệu thực được kiểm tra sau khi thu; lab ghi file giả lập `.txt`.
- `CREATE_NEW` tạo file mới và từ chối nếu tên đã có; lần viết thứ hai ném `FileAlreadyExistsException` nên `duplicateRejected=true`.
- `Files.readString(...).strip()` xác nhận nội dung đầu không bị lệnh thử ghi đè thay thế.
- `try/finally` dọn file và thư mục tạm; đây là bài test, **không dùng tự động xóa bằng chứng production ngay sau khi tạo**.
- File lab được tạo ở thư mục temp của OS và chỉ chứa chữ `demo-only`. Với dữ liệu thật, không dùng temp chung chưa thẩm định, vì heap dump/thread dump có thể chứa dữ liệu nhạy cảm.

**Giới hạn cần biết:** ví dụ không thực hiện atomic publish, không sinh checksum/manifest và không quản lý ACL. Nó chứng minh riêng việc **chuẩn hóa filename và không overwrite**; pipeline production cần các bước tiếp theo.

### 8.2. Mở rộng cho collector thực tế

Trong phần code nghiệp vụ thu thập, nên trừu tượng:

~~~text
ArtifactIdentity:
  serviceId
  environment
  instanceId
  targetPid
  processStartTime
  appVersion
  buildId
  captureStartedAt
  action
  captureId

ArtifactWriter:
  reserveUniqueDestination()
  executeCollectorWithTimeout()
  validateOutput()
  calculateSha256()
  publishWithoutOverwrite()
  writeManifest()
~~~

Đây là **sơ đồ thiết kế, không phải Java code**. Collector cần nhận metadata đáng tin từ deployment/orchestrator, không lấy tất cả từ biến môi trường tự do do user gửi. Đảm bảo những nhiệm vụ I/O/GC có tác động lớn chỉ được thực hiện qua workflow có quyền và hạn mức phù hợp.

## 9. Khác biệt quan trọng giữa output do collector và JVM ghi

Hai loại lệnh có **chủ thể ghi file khác nhau**, ảnh hưởng trực tiếp tới path, permission và nơi kiểm chứng.

### 9.1. Thu thread dump bằng stdout của jcmd

Ví dụ POSIX shell, chỉ dùng trên JVM và host **được ủy quyền**:

~~~bash
# PID=3142 và tên output chỉ để minh họa.
PID=3142
OUT_DIR=/srv/diag/private
FILE_NAME='orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__thread-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.txt'

# Quản trị viên phải chuẩn bị OUT_DIR an toàn, đúng owner/quota trước.
# Noclobber giúp shell từ chối ghi đè một path đã tồn tại.
if ( umask 077; set -C; jcmd "$PID" Thread.print > "$OUT_DIR/$FILE_NAME" ); then
    echo 'collector finished'
else
    echo 'collector failed: review partial file and stderr' >&2
fi
~~~

Đây là **ví dụ thu stdout**. Shell của collector mở đích `OUT_DIR/FILE_NAME`; đường dẫn được diễn giải ở **nơi collector chạy**, không nhất thiết trong namespace của JVM. `set -C` (noclobber) giúp từ chối overwrite qua redirect trên nhiều POSIX shells, nhưng không thay thế bảo vệ thư mục và symlink, không tạo publication atomic, và file có thể còn partial nếu `jcmd` thất bại. Trước khi dùng, kiểm tra shell cụ thể và policy xử lý file trống/lỗi. Không coi việc shell tạo file là đủ xác nhận dump có nội dung hợp lệ.

Với `Thread.print`, nếu JVM đang có nhiều thread hoặc đang bận, thao tác vẫn có chi phí; không chạy theo chu kỳ dày trên production mà chưa đo.

### 9.2. Thu HPROF hoặc JFR: file có thể do JVM đích tạo

~~~bash
# Ví dụ trên máy/namespace có công cụ jcmd và quyền phù hợp.
jcmd 3142 help GC.heap_dump
jcmd 3142 GC.heap_dump /srv/diag/private/heap-capture.hprof

jcmd 3142 JFR.check
jcmd 3142 JFR.dump name=diag filename=/srv/diag/private/jfr-capture.jfr
~~~

Ở đây đường dẫn `/srv/diag/private/...` của `GC.heap_dump`/`JFR.dump` được **JVM đích** sử dụng. Nếu JVM ở trong container, file có thể nằm **bên trong container** hoặc một volume mount khác với filesystem của collector. Phải xác minh target JVM có quyền ghi, volume còn đủ chỗ và người tải file có quyền đọc. Đổi path output theo tên chuẩn ở phần 2 khi áp dụng thật; các tên ngắn `heap-capture.hprof`/`jfr-capture.jfr` ở đây chỉ để diễn giải cú pháp.

**Không thêm `-overwrite` vào `GC.heap_dump` để chạy lại cho tiện.** Trên HotSpot JDK 21, tùy chọn `-overwrite` mặc định false; cho phép overwrite có thể phá hủy bằng chứng. Heap dump có **impact cao**, có thể yêu cầu full GC, tạo file rất lớn, dừng ứng dụng và chứa dữ liệu nhạy cảm. `JFR.dump` xuất snapshot trong khi recording có thể tiếp tục chạy; nó không tự dừng recording và thời gian dữ liệu bên trong có thể khác timestamp filename. Luôn kiểm tra `jcmd <pid> help <command>` trên JDK đích.

Nếu hai lệnh cùng tạo file, **đừng đặt cùng capture ID và action không đổi** mà mong không collision; dùng ID artifact riêng hoặc manifest gồm `collectionId` và `artifactId`.

### 9.3. Ghi file sau khi lệnh thành công

Với text dump, cần xác minh nội dung có header/data phù hợp, process/command trả exit status đúng, file đã đóng. Với JFR có thể dùng `jfr summary file.jfr`; với HPROF dùng MAT/đầu đọc phù hợp để kiểm tra format và kích thước. Trên Linux, sau khi hoàn tất:

~~~bash
# Chỉ kiểm tra một file đã thu hợp lệ, không in nội dung nhạy cảm.
stat -c '%n %s bytes' /srv/diag/private/heap-capture.hprof
sha256sum /srv/diag/private/heap-capture.hprof
~~~

Số byte và SHA-256 phải được lưu trong manifest **sau khi file đã đóng hoàn tất**. Nếu tính hash khi JVM vẫn đang ghi, hash không đại diện cho artifact cuối. Khi chuyển file qua node khác, tính lại checksum và so với metadata đã ký/quản lý. Hash không ngăn truy cập trái phép, nên vẫn phải bảo vệ đường truyền, file và manifest.

## 10. Manifest: biến tên file thành chứng cứ có thể audit

Tên file là **chỉ mục rút gọn**, nhưng điều tra sự cố cần hơn thế: ai yêu cầu, lệnh nào đã chạy, trên JVM nào, vì sao, dữ liệu lưu ở đâu, kết quả có thành công và có được phép chia sẻ không.

Ví dụ manifest JSON cho một lần thu **giả định**, đặt bên cạnh hoặc lưu trong kho metadata được quản lý. Đây là mẫu dữ liệu minh họa, không phải kết quả của chương trình ở phần 8:

~~~json
{
  "schemaVersion": 1,
  "artifactId": "f8c47de5-d7c7-4ef7-a59c-c89c935e7d2b",
  "incidentId": "inc-20261029-42",
  "service": "orders-api",
  "environment": "prod",
  "cluster": "cluster-blue",
  "instance": "pod-7c2",
  "targetPid": 3142,
  "pidNamespace": "container",
  "targetProcessStartedAt": "2026-10-29T08:40:00Z",
  "appVersion": "2.8.1+build.483",
  "buildId": "build-483",
  "commitSha": "6a2fc8b",
  "jvmVersion": "21.0.5",
  "action": "thread-dump",
  "captureStartedAt": "2026-10-29T09:55:01.123Z",
  "captureFinishedAt": "2026-10-29T09:55:01.823Z",
  "commandTemplate": "jcmd TARGET_PID Thread.print",
  "collectorLocation": "approved-bastion",
  "status": "SUCCEEDED",
  "fileName": "orders-api__prod__pod-7c2__pid-3142__20261029T095501.123Z__v2.8.1__thread-dump__f8c47de5d7c74ef7a59cc89c935e7d2b.txt",
  "sizeBytes": 123456,
  "sha256": "example-only-not-a-real-digest",
  "sensitivity": "restricted",
  "retentionDays": 7
}
~~~

**Cảnh báo:** `sizeBytes`, `sha256` và mốc thời gian ở mẫu là **giá trị minh họa**, không được đưa vào hệ thống thật như số đo. Trong workflow thực, `sha256` phải chứa chuỗi digest hợp lệ được tính từ file cuối; manifest phải có trạng thái rõ nếu chưa tính được hoặc file thất bại. Không tự lưu raw command với mật khẩu/token; chỉ lưu **command template** đã loại bí mật và các tham số không nhạy cảm.

### 10.1. Các trường quan trọng không nằm trong filename

- `targetProcessStartedAt`: phân biệt PID tái sử dụng, nếu lấy được từ nguồn đáng tin.
- `pidNamespace`, `cluster`, `node`, `podUid` hoặc deployment instance: giải quyết nhầm PID host/container.
- `captureStartedAt` và `captureFinishedAt`: cho phép tính thời gian lệnh chạy và so với sự cố.
- `recordingWindow` (cho JFR): thời gian sự kiện thực sự chứa trong file, nếu được xác minh.
- `commandTemplate`, `exitCode`, `stderrSummary`: phân biệt thành công, lỗi, timeout và thao tác đã thực thi.
- `fileName`, `objectKey`, `sizeBytes`, `sha256`, `format`: giúp định vị và kiểm tra tính toàn vẹn.
- `sensitivity`, `retentionUntil`, `authorizedBy`, `collectedBy`: quản lý phân quyền, hạn sử dụng và audit.
- `retryOf`/`collectionId`: liên kết các lần thử lại và nhiều artifact của cùng một sự cố.

Không bắt buộc nhồi toàn bộ các trường này vào một filename; file dài quá dễ bị truncate trong UI, vượt giới hạn path hoặc lộ thông tin nhạy cảm. Nếu có hệ thống quản lý artifact, manifest có thể nằm trong database, metadata object storage hoặc sidecar; cần đảm bảo **liên kết bất biến** giữa artifact và record.

### 10.2. Tên file và manifest không có cùng vai trò

- **Tên file:** đọc nhanh, dùng để lọc ban đầu, sắp xếp gần đúng, tránh tên “dump”.
- **Manifest:** record có schema, trạng thái và dữ liệu đầy đủ phục vụ automation.
- **Checksum:** giúp phát hiện file thay đổi sau khi thu.
- **Audit log:** ghi hoạt động người dùng/hệ thống; không nên tự tin chỉ nhờ trường `collectedBy` do client có thể tự gửi.
- **Object store ACL/retention:** quyết định ai thực sự xem và khi nào được xóa.

Để điều tra nhiều người, quy tắc filename dễ đọc là cần, nhưng **không thay thế** quản lý phiên thu và security controls.

## 11. Quy ước an toàn cho hệ điều hành và dữ liệu

### 11.1. Ký tự, độ dài và phân cách

Dùng các component đã được **validate hoặc chuẩn hóa có kiểm soát**. Trong ví dụ Java, từng component nhận chữ thường a–z, chữ số 0–9, dấu gạch ngang và dấu chấm; không nhận dấu cách, `/`, `\\`, dấu `:` hay `__`. Điều này dễ dùng trên nhiều hệ điều hành nhưng không phải cam kết mọi filesystem đều có cùng giới hạn.

Tránh:

- Tên quá dài (giới hạn từng filename component và tổng path có thể khác nhau).
- Ký tự đặc biệt cần escape khi shell dùng `&`, `;`, `$`, dấu cách hoặc Unicode không được xử lý nhất quán.
- Trộn chữ hoa/chữ thường trên filesystem case-insensitive.
- Cắt version/hash mà không lưu bản gốc và cách mapping.
- Coi regex filename là cơ chế chặn symlink/path traversal đầy đủ. Cần base directory tin cậy, permission/ownership và API tạo file phù hợp.

Thường tốt hơn là **reject metadata bất hợp lệ**, báo lỗi rõ, thay vì âm thầm “làm sạch” chuỗi người dùng và tạo hai filename trùng nhau.

### 11.2. Tên file cũng có thể làm lộ thông tin

Một tên file như `user-123456__token-abcdef__customer-a.hprof` dễ làm lộ PII/secret trong ticket, email, storage logs hoặc URL chia sẻ. Không đặt token, credential, payload, tên người dùng, email, query string hoặc customer ID nhạy cảm trực tiếp trong filename. Nếu cần liên kết, dùng incident ID hoặc mã nội bộ đã phân quyền; lưu mapping ở manifest hệ thống riêng.

Dù filename đã an toàn, **nội dung artifact có thể cực kỳ nhạy cảm**:

- Heap dump có thể chứa password/token, session, PII và payload.
- Thread dump có thể lộ stack trace, class names, đường dẫn hoặc dữ liệu tùy cách log.
- JFR có thể chứa tên method, file path, IP/host và custom event fields.
- JVM command line và system properties có thể có secrets.

Cấp quyền filesystem chặt, mã hóa khi truyền/lưu theo policy, TTL/retention, audit tải xuống, và giới hạn những người có thể truy cập. Đừng đưa raw artifact lên ticket công khai chỉ vì filename không chứa thông tin mật.

### 11.3. Không để tạo file làm đầy disk

Tên file không ngăn thư mục bị đầy. Collector cần giới hạn số artifact, quota, free space dự phòng, size estimate, per-incident rate limit và thời gian lưu. Với heap dump, kích thước có thể rất lớn và hoạt động có high impact; không tạo lặp lại chỉ vì job retry. Nếu file đã có và lệnh báo collision, không tự thêm `-overwrite` để làm tác vụ “thành công”.

## 12. Lỗi vận hành thường gặp

| Quan sát / lỗi | Tại sao nguy hiểm | Cách kiểm chứng và khắc phục |
| --- | --- | --- |
| Hai file cùng tên `dump.txt` | Ghi đè, không biết nguồn | Áp schema với service + PID + UTC + version + action + capture ID |
| Filename có PID của script `jcmd` | Quy kết sai JVM | Xác minh PID target, manifest pid namespace và process start |
| App version lấy từ `java -version` | Nhầm bản phát hành Java với app | Lấy build/release metadata của binary đang chạy |
| Timestamp giờ local không có offset | Khó so chéo node/timezone/DST | Format UTC có `Z`; lưu cả start/finish trong manifest |
| Tên có timestamp nhưng vẫn bị ghi đè | Retry hoặc concurrent job trùng mili-giây | UUID + `CREATE_NEW`/conditional publish |
| `File.exists()` rồi `writeString()` | Race TOCTOU, overwrite sau check | Tạo file mới bằng API atomic create; không check-then-write |
| `jcmd Thread.print > output` nhưng exit nonzero | File có thể chỉ chứa lỗi/một phần output | Ghi exit code, parse/validate, đánh dấu PARTIAL/FAILED |
| `GC.heap_dump` được yêu cầu từ bastion | JVM không nhìn thấy path của bastion | Kiểm tra JVM filesystem/container mount và quyền JVM |
| JFR dump lúc 10:00, filename là 10:00 | Không mô tả tất cả event time window | Lưu recording/event window riêng |
| File `.hprof.gz` đổi tên thành `.hprof` | Parser đọc sai format | Đặt extension phản ánh định dạng và compression thực |
| Dùng một capture ID cho retry nhưng cùng action | Tên đụng nhau hoặc thay file cũ | ID mới, manifest `retryOf` |
| File tồn tại nhưng chưa đóng | Người phân tích nhận file partial | Staging/validation/publish status |
| Tên đúng, hash không trùng sau upload | Truyền tải/copy chưa đầy đủ hoặc bị thay | Tính lại SHA-256, không đánh dấu ready |
| Manifest không có quyền bảo vệ | Người khác sửa metadata, khó audit | Kho có ACL, log, quyền ghi hạn chế, integrity bảo đảm |
| Đưa customer ID vào filename | Rò rỉ thông tin qua path/log | Dùng alias/incident ID và mapping đã phân quyền |
| Tên rất dài, bị script cắt | Không parse được, collision | Đặt limit component, chuyển chi tiết sang manifest |
| Xóa file sớm vì GC log “đã lên cloud” | Mất chứng cứ khi upload lỗi | Xác nhận checksum/durability rồi mới cleanup |
| Parse filename bằng dấu `_` đơn | Dễ vỡ khi component cũng có underscore | Quy định delimiter `__` và validate component, hoặc đọc manifest |

Một nguyên tắc QA quan trọng: **báo lỗi sớm hơn là tự sửa tên thiếu dữ liệu**. Nếu không xác minh được PID/version/timestamp, hãy ghi trạng thái metadata thiếu, không bịa giá trị hoặc dùng default gây nhầm.

## 13. Bài tập thực hành

**Bài 1 — đọc tên.** Cho file:

~~~text
billing-api__staging__pod-9f1__pid-87__20261029T101500.000Z__v3.2.0__jfr-dump__0123456789abcdef0123456789abcdef.jfr
~~~

Hãy nhận diện service, môi trường, instance, PID, thời gian UTC, version, action và định dạng. Đáp án lần lượt: `billing-api`, `staging`, `pod-9f1`, `87`, **2026-10-29 10:15:00.000 UTC**, `v3.2.0`, `jfr-dump`, `.jfr`. Chưa thể biết JFR chứa event bắt đầu từ lúc nào nếu chưa đọc manifest/file.

**Bài 2 — PID sai.** Một collector có PID 9000 lấy thread dump của JVM PID 313 trong container. Filename dùng `pid-9000`. Sửa thế nào? Ghi **PID JVM đích là 313**, bổ sung namespace/processStartTime và collector identity trong manifest, không ghép PID tự động của collector vào tên file JVM.

**Bài 3 — timeout.** Một file `.hprof` xuất hiện sau khi `GC.heap_dump` timeout. Có được phân tích như file hoàn chỉnh? **Không được mặc định.** Đánh dấu `PARTIAL`, kiểm tra exit/status, kích thước và định dạng. Nếu cần retry, cấp ID mới và phê duyệt impact.

**Bài 4 — cùng mili-giây.** Hai operator cùng thu `thread-dump` từ một JVM trong một mili-giây. Vì sao tên chỉ có PID và timestamp có thể trùng? Vì độ phân giải không đảm bảo uniqueness. Dùng capture ID và no-overwrite.

**Bài 5 — tên rút gọn.** Raw version `2.8.1+build.483`. Trong filename chọn `v2.8.1-build.483`. Đảm bảo manifest lưu gì? Raw version nguyên bản, build ID, commit/image digest và quy tắc normalize để không mất khả năng phân biệt.

**Bài 6 — sai định dạng.** File có đuôi `.jfr` nhưng `jfr summary` không đọc được. Có nên đổi thành `.txt` và kết luận lệnh chạy thành công? **Không.** Điều tra file partial/corrupt/wrong format, path và exit code; extension không sửa được dữ liệu.

**Bài 7 — quyền ghi.** `Thread.print > /collector/data/x.txt` chạy thành công, còn `GC.heap_dump /collector/data/x.hprof` báo permission denied. Khác biệt ở đâu? Thread dump được **shell collector** redirect; HPROF được **JVM đích** ghi theo path nó nhìn thấy. Kiểm tra namespace và quyền từng process.

**Bài 8 — checksum.** Tính SHA-256 trước khi JVM đóng file rồi upload, phía nhận tính hash khác. Có chắc mạng làm hỏng file không? **Không.** File có thể đã tiếp tục được ghi sau lần tính hash đầu; chỉ hash sau khi hoàn thành và xác nhận trạng thái.

**Bài 9 — thu theo incident.** Một lần thu gồm 2 thread dump và 1 JFR. Nên dùng ID thế nào? Đặt một `collectionId` chung cho incident/cửa sổ và **artifactId riêng** cho từng file; manifest liên kết, tránh dùng lại cùng action+name cho hai dump.

**Bài 10 — file nhạy cảm.** Tên file chứa PID/version hợp lệ nhưng heap dump có session token. Có thể tự động đính kèm vào ticket không giới hạn? **Không**. Cần phân loại và giới hạn quyền, retention, mã hóa theo policy. Filename chuẩn không phải bằng chứng dữ liệu vô hại.

## 14. Checklist trước và sau khi thu file

**Trước khi thu:**

- [ ] Biết rõ JVM đích, PID đúng namespace, process start/instance identity.
- [ ] Có service/environment/app version đúng từ nguồn build/deployment đáng tin.
- [ ] Chốt timestamp UTC là **captureStartedAt**; đồng bộ thời gian đủ cho điều tra.
- [ ] Chọn `action` từ danh sách hợp lệ; extension phản ánh format thực.
- [ ] Tạo capture ID riêng và final filename không vượt giới hạn path.
- [ ] Chọn output dir/volume đã kiểm tra permission, dung lượng, quota và sensitivity.
- [ ] Đã phê duyệt lệnh chẩn đoán có tác động cao, thời hạn và người chịu trách nhiệm.
- [ ] Có no-overwrite policy, staging/partial-state và đường xử lý khi retry.

**Sau khi thu:**

- [ ] Lệnh thực sự thành công; exit code và thời điểm bắt đầu/kết thúc được ghi.
- [ ] File đã đóng, có kích thước hợp lệ và có thể mở bằng công cụ tương ứng.
- [ ] Ghi SHA-256, format, compression, size và location chính xác trong manifest.
- [ ] Manifest gắn đúng capture ID, PID, app version, action và incident.
- [ ] File/metadata được kiểm tra permission, quy định người xem và hạn lưu.
- [ ] Sao chép/upload đã được xác minh trước khi dọn staging files.
- [ ] Không overwrite hoặc ghi đè chứng cứ của lần thu trước.
- [ ] Những file partial/FAILED được đánh dấu đúng, không bị lẫn với file đã xác minh.

**Kết luận:** tên file tốt giúp nối đúng **JVM nào – lúc nào – phiên bản nào – đã làm gì**, còn capture ID chống trùng, manifest cung cấp ngữ cảnh và cơ chế ghi/kiểm tra đảm bảo artifact có thể dùng trong điều tra. Hãy coi naming là một phần của quy trình **thu thập có kiểm soát**, không phải một thủ thuật ghép chuỗi.

## Tài liệu tham khảo

- Oracle Java SE 21, [ProcessHandle API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html) — `pid()`, PID reuse và giới hạn identity/liveness.
- Oracle Java SE 21, [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) và [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) — tạo mốc UTC, format timestamp.
- Oracle Java SE 21, [StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html) và [Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html) — `CREATE_NEW`, ghi file, tạo thư mục, chuyển file.
- Oracle Java SE 21, [jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — `Thread.print`, `GC.heap_dump`, `JFR.dump` và hành vi/impact của diagnostic commands.
- Oracle Java SE 21, [jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `summary`, `metadata` và kiểm tra file `.jfr`.
- Oracle Java SE 21, [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html) — sử dụng `jcmd` và thu thập chứng cứ chẩn đoán.
