# Truyền dữ liệu lớn và lựa chọn cách tải có thể tiếp tục

## 1. Vì sao cần chiến lược truyền dữ liệu lớn?

Khi ứng dụng Spring Boot lưu video, bản sao lưu, tệp dữ liệu phân tích, bản xuất báo cáo hoặc tài liệu dung lượng lớn, một lần upload/download kéo dài có thể gặp timeout, mất kết nối, tiến trình khởi động lại hoặc máy chủ hết dung lượng tạm. Nếu ứng dụng luôn bắt đầu lại từ byte đầu tiên, băng thông đã sử dụng và thời gian chờ sẽ bị lãng phí.

Google Cloud Storage (GCS) cung cấp nhiều cách truyền dữ liệu: upload một lần, resumable upload, đọc theo luồng, đọc theo byte range và tải nhiều phần song song. Java client library bổ sung **WriteChannel**, **ReadChannel** và **TransferManager** để ứng dụng lựa chọn cách phù hợp.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module hướng tới thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào cách truyền dữ liệu lớn, khôi phục sau gián đoạn và cân bằng tốc độ, bộ nhớ, độ tin cậy, chi phí.

Sau bài học, bạn có thể:

- Chọn upload trực tiếp, resumable upload hoặc parallel composite upload.
- Điều chỉnh chunk/buffer size theo kích thước file, băng thông và số luồng đồng thời.
- Lưu và khôi phục trạng thái **WriteChannel**/**ReadChannel** khi cần tiếp tục công việc.
- Tải file lớn bằng streaming hoặc chia thành các byte range song song.
- Dùng generation để bảo đảm mọi phần tải thuộc cùng một phiên bản object.
- Kiểm tra toàn vẹn bằng CRC32C/MD5 theo loại object và API.
- Thiết kế retry, timeout, checkpoint, file tạm và cleanup trong Spring Boot.
- Đánh giá trade-off của Java TransferManager, resumable upload và các chiến lược song song.

> **Phạm vi phiên bản:** Các ví dụ dùng Google Cloud Storage Java client và TransferManager. API của TransferManager và cấu hình transport phụ thuộc phiên bản thư viện. Hãy khóa version bằng BOM phù hợp với Spring Boot/Java của dự án và kiểm tra Javadoc đúng version đang resolve. Các giá trị chunk size trong bài là điểm bắt đầu để thử nghiệm, không phải cấu hình tối ưu cho mọi workload.

## 2. Phân loại chiến lược truyền dữ liệu

Trước khi chọn API, cần phân biệt ba mục tiêu:

- **Streaming:** truyền từng phần dữ liệu qua bộ nhớ có giới hạn, không giữ toàn bộ object trong heap.
- **Resumable:** tiếp tục từ trạng thái hoặc offset đã được lưu sau khi request/tiến trình bị gián đoạn.
- **Parallel/sliced:** chia dữ liệu thành nhiều phần và truyền đồng thời để tăng throughput.

Một kỹ thuật có thể đáp ứng nhiều mục tiêu, nhưng không đồng nghĩa với nhau. Ví dụ, **WriteChannel** vừa streaming vừa dùng resumable upload; **TransferManager** có thể chia tải xuống song song; **ReadChannel.seek()** giúp tiếp tục đọc từ một offset xác định.

~~~mermaid
flowchart TD
    START["Dữ liệu lớn cần truyền"] --> DIR{"Chiều truyền"}
    DIR --> UP["Upload"]
    DIR --> DOWN["Download"]
    UP --> SMALL["Nhỏ, đã có trong RAM<br/>Storage.create"]
    UP --> RESUME["Lớn hoặc mạng không ổn định<br/>Storage.writer / createFrom"]
    UP --> FASTUP["Cần throughput cao<br/>Parallel composite upload"]
    DOWN --> STREAM["Xử lý tuần tự / HTTP response<br/>ReadChannel"]
    DOWN --> RESUME_D["Cần tiếp tục từ offset<br/>ReadChannel.seek / capture"]
    DOWN --> FASTDOWN["Cần tăng tốc tải toàn object<br/>TransferManager sliced download"]
~~~

### 2.1. Bảng lựa chọn nhanh

| Tình huống | Cách ưu tiên | Lý do |
| --- | --- | --- |
| JSON hoặc ảnh nhỏ, đã nằm trong bộ nhớ | **Storage.create(BlobInfo, byte[])** | Ít bước, đơn giản |
| File lớn từ local hoặc HTTP request | **Storage.writer** hoặc **Storage.createFrom** | Resumable upload và streaming |
| Upload có thể bị gián đoạn, cần khôi phục tiến trình | **WriteChannel.capture() / restore()** hoặc resumable session | Có thể tiếp tục từ trạng thái đã lưu |
| Nhiều file độc lập cần upload cùng lúc | TransferManager upload | Quản lý nhiều tác vụ song song |
| Một file rất lớn cần tăng tốc upload | Parallel composite upload khi bucket tương thích | Chia thành component, upload song song rồi compose |
| Download tuần tự tới HTTP response | **ReadChannel** | Không cần lưu toàn bộ file trong heap |
| Download một file lớn có thể bị ngắt | **ReadChannel.seek()** hoặc khôi phục trạng thái reader | Tiếp tục từ byte offset |
| Download toàn bộ object cần throughput cao | TransferManager sliced download | Nhiều range request chạy song song |

## 3. Upload trực tiếp và resumable upload

### 3.1. Upload trực tiếp bằng byte array

**Storage.create(BlobInfo, byte[])** phù hợp với nội dung nhỏ mà ứng dụng đã có sẵn trong bộ nhớ. Java client thực hiện direct upload; nếu request thất bại giữa chừng, ứng dụng thường phải gửi lại toàn bộ payload.

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadSmall(
        Storage storage,
        String bucket,
        String objectName,
        String text) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("text/plain; charset=utf-8")
        .build();

    return storage.create(
            info,
            text.getBytes(StandardCharsets.UTF_8),
            Storage.BlobTargetOption.doesNotExist());
}
~~~

Không dùng cách này cho file lớn nếu nội dung chưa được giới hạn kích thước. Một số request đồng thời có thể tạo nhiều bản sao byte array trong heap và gây áp lực GC hoặc OutOfMemoryError.

### 3.2. Resumable upload hoạt động thế nào?

Resumable upload chia việc truyền object thành một phiên upload. Client khởi tạo phiên, nhận session URI và gửi dữ liệu theo một hoặc nhiều request. Nếu kết nối bị ngắt, client có thể hỏi server đã nhận tới byte nào rồi gửi tiếp phần còn lại.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant GCS as Cloud Storage
    App->>GCS: Khởi tạo resumable upload
    GCS-->>App: Session URI
    App->>GCS: Gửi chunk 0..N
    GCS-->>App: Offset đã lưu
    App-xGCS: Mất kết nối khi gửi chunk tiếp
    App->>GCS: Kiểm tra trạng thái session
    GCS-->>App: Byte cuối đã được lưu
    App->>GCS: Gửi tiếp từ offset kế tiếp
    GCS-->>App: Upload hoàn tất + object metadata
~~~

Các đặc điểm cần nhớ:

- Object chưa xuất hiện như một object hoàn chỉnh trong bucket cho tới khi upload kết thúc thành công.
- Metadata được khai báo khi khởi tạo upload và gắn vào object khi hoàn tất.
- Session URI là thông tin nhạy cảm, phải truyền qua HTTPS và không ghi vào log.
- Session resumable của GCS có thời hạn tối đa một tuần; nếu hết hạn hoặc mất session URI, cần khởi tạo phiên mới.
- Session được gắn với region nơi nó được khởi tạo. Nên khởi tạo gần location bucket và giữ client tiếp tục upload ở khu vực phù hợp để tránh vòng truyền không cần thiết.
- Nếu retry từ một offset đã được server lưu, không được gửi dữ liệu khác cho các byte đó. Hãy bảo đảm nguồn upload không bị sửa giữa chừng.

### 3.3. Java Storage.writer luôn dùng resumable upload

Java Cloud Storage client có các overload upload resumable như **Storage.writer(...)** và **Storage.createFrom(...)**. Với file lớn, **writer** là lựa chọn phù hợp hơn việc tạo byte array.

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void uploadLarge(
        Storage storage,
        BlobInfo info,
        InputStream source) throws Exception {

    WriteChannel writer = storage.writer(
            info,
            Storage.BlobWriteOption.doesNotExist());

    writer.setChunkSize(15 * 1024 * 1024);

    try (OutputStream output = Channels.newOutputStream(writer)) {
        source.transferTo(output);
    }
}
~~~

Trong ví dụ, buffer 15 MiB là giá trị mặc định được tài liệu Java client công bố cho resumable upload hiện hành. Có thể thay đổi bằng **WriteChannel.setChunkSize(int)**. Buffer có mức tối thiểu 256 KiB; thư viện điều chỉnh kích thước theo bội số 256 KiB.

Đóng output stream sẽ đóng writer và hoàn tất upload. Nếu nguồn **InputStream** do caller quản lý, tầng gọi phải đóng stream nguồn. Trong ứng dụng thực tế, cần phân định rõ ownership của stream để không đóng sớm hoặc rò rỉ tài nguyên.

### 3.4. Upload từ file Path bằng createFrom

Khi nguồn là file local và không cần tự điều khiển từng lần ghi, có thể dùng **Storage.createFrom(...)**:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public Blob uploadPath(
        Storage storage,
        BlobInfo info,
        Path sourceFile) {

    return storage.createFrom(
            info,
            sourceFile,
            15 * 1024 * 1024,
            Storage.BlobWriteOption.doesNotExist());
}
~~~

Các overload **createFrom** nhận **Path** hoặc **InputStream** thực hiện resumable upload theo Java client reference. Dùng overload có buffer size nếu cần tinh chỉnh bộ nhớ và kích thước request. Không giả định mọi overload **Storage.create** đều resumable: overload byte array thực hiện direct upload.

## 4. Chọn chunk size và buffer size

Chunk size quyết định lượng dữ liệu client gom lại trước khi gửi một RPC. Nó ảnh hưởng throughput, số request, độ trễ, bộ nhớ và lượng dữ liệu cần xử lý lại khi một lần truyền thất bại.

### 4.1. Trade-off của chunk size

| Chunk size | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Nhỏ | Buffer ít; dễ phù hợp giới hạn bộ nhớ | Nhiều RPC hơn, tăng overhead và có thể giảm throughput |
| Trung bình | Cân bằng throughput và bộ nhớ trong nhiều workload | Vẫn cần benchmark theo mạng và số upload đồng thời |
| Lớn | Có thể tăng throughput trên mạng tốt | Tăng bộ nhớ mỗi upload; retry một chunk lớn tốn thời gian hơn |

Ví dụ Java:

~~~java
WriteChannel writer = storage.writer(blobInfo);
writer.setChunkSize(8 * 1024 * 1024);
~~~

8 MiB chỉ là ví dụ cấu hình. Không tăng chunk size theo cảm tính; đo tốc độ thực tế, memory footprint, số kết nối đồng thời và tỷ lệ retry.

### 4.2. Ước lượng bộ nhớ khi upload đồng thời

Nếu mỗi writer giữ buffer gần với chunk size, mức bộ nhớ dành cho buffer có thể tăng theo:

**Bộ nhớ buffer xấp xỉ = số upload đồng thời × chunk size mỗi upload**

Ví dụ 12 upload cùng lúc với buffer 15 MiB có thể cần khoảng 180 MiB chỉ cho các buffer đó, chưa tính heap của ứng dụng, stream, TLS, HTTP transport và các thành phần khác. Đây là ước lượng lập kế hoạch, không phải cam kết chính xác về heap allocation của client.

Hãy đặt giới hạn concurrency bằng executor/semaphore hoặc giới hạn worker của TransferManager. Tăng số luồng có thể làm giảm throughput nếu network, disk hoặc quota đã là nút thắt.

### 4.3. Chọn chunk theo nguồn dữ liệu

- File local có thể đọc lại: dễ retry vì nguồn ổn định và seek được.
- HTTP multipart stream: thường không thể đọc lại sau khi đã tiêu thụ; cần spool ra file tạm hoặc thiết kế upload session từ client để hỗ trợ resume.
- Dữ liệu được tạo động: cân nhắc ghi ra file tạm hoặc dùng writer có checkpoint; phải giữ đúng thứ tự byte và nội dung nguồn.
- Nguồn là stream không biết trước kích thước: resumable upload vẫn có thể hỗ trợ; cần quản lý luồng kết thúc và đóng writer để finalize.

## 5. Lưu và khôi phục trạng thái WriteChannel

Java **WriteChannel** triển khai giao diện **Restorable**. Có thể gọi **capture()** để chụp trạng thái writer, sau đó lưu đối tượng **RestorableState<WriteChannel>** và gọi **restore()** để khôi phục writer ở trạng thái đã lưu.

~~~java
import com.google.cloud.RestorableState;
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public RestorableState<WriteChannel> captureUploadState(
        Storage storage,
        BlobInfo info) {

    WriteChannel writer = storage.writer(info);
    writer.setChunkSize(15 * 1024 * 1024);

    // Lưu state bằng cơ chế checkpoint bền vững của ứng dụng.
    return writer.capture();
}
~~~

Khi khôi phục:

~~~java
import com.google.cloud.RestorableState;
import com.google.cloud.WriteChannel;
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

@SuppressWarnings("unchecked")
public WriteChannel restoreUploadState(Path checkpointFile)
        throws Exception {

    try (ObjectInputStream input = new ObjectInputStream(
            Files.newInputStream(checkpointFile))) {
        RestorableState<WriteChannel> state =
                (RestorableState<WriteChannel>) input.readObject();
        return state.restore();
    }
}
~~~

**RestorableState** được thiết kế để serialize và restore. Tuy nhiên, cần tuân thủ các quy tắc:

1. Không tiếp tục ghi đồng thời trên writer gốc và writer đã restore. Chỉ một trong hai được sử dụng.
2. Đóng một channel sẽ đóng channel còn lại; sau đó ghi tiếp sẽ thất bại.
3. Lưu checkpoint và trạng thái nghiệp vụ một cách nguyên tử, tránh trường hợp metadata checkpoint mới nhưng file nguồn hoặc offset cũ.
4. Giữ nguyên nguồn dữ liệu hoặc đảm bảo có thể đọc lại đúng các byte chưa gửi.
5. Bảo vệ checkpoint vì trạng thái có thể chứa thông tin phiên upload. Mã hóa khi lưu, giới hạn người đọc và không ghi state ra log.
6. Pin version thư viện trong deployment và kiểm thử khả năng restore khi khởi động lại trước khi dựa vào cơ chế này cho job quan trọng.

Nếu ứng dụng không cần tự quản lý checkpoint, hãy để Java client quản lý resumable upload thông qua **Storage.writer** hoặc **createFrom**. Chỉ dùng **capture/restore** khi có yêu cầu tiếp tục tác vụ qua ranh giới tiến trình hoặc cần bàn giao writer giữa các thành phần.

## 6. Resumable upload qua REST API và session URI

Trong một số kiến trúc, backend khởi tạo resumable session rồi giao session URI cho trình duyệt hoặc client tải file trực tiếp lên GCS. Cách này giảm tải băng thông đi qua backend, nhưng phải kiểm soát chặt quyền và vòng đời session.

~~~mermaid
sequenceDiagram
    participant Browser as Web client
    participant API as Spring Boot API
    participant GCS as Cloud Storage

    Browser->>API: Yêu cầu upload cho document ID
    API->>API: Xác thực user và kiểm tra quota
    API->>GCS: Khởi tạo resumable upload
    GCS-->>API: Session URI
    API-->>Browser: Session URI có thời hạn
    Browser->>GCS: Gửi chunk qua HTTPS
    GCS-->>Browser: Offset/tiến độ
    Browser->>GCS: Gửi phần còn lại
    GCS-->>Browser: Upload hoàn tất
    Browser->>API: Báo hoàn tất, gửi object ID
    API->>GCS: Xác minh metadata/generation
~~~

Một session URI có quyền tiếp tục upload object được khởi tạo; hãy xem nó như bearer credential. Không để URI xuất hiện trong URL analytics, access log, crash report hoặc telemetry. Không cho client tự chọn bucket/object name tùy ý. Backend phải ràng buộc session với người dùng, tenant, object name, content type, kích thước tối đa và thời gian hiệu lực.

Chỉ coi upload hoàn tất sau khi GCS xác nhận thành công và backend xác minh object metadata, generation, size hoặc checksum theo yêu cầu. Không tin riêng thông báo hoàn tất từ browser.

## 7. Parallel composite upload: khi cần throughput cao

### 7.1. Cơ chế

Parallel composite upload chia một file lớn thành các component object, upload các component song song, rồi dùng compose để tạo object cuối cùng. Các component tạm được dọn sau khi compose thành công.

~~~mermaid
flowchart TD
    FILE["File nguồn lớn"] --> SPLIT["Chia thành component"]
    SPLIT --> P1["Upload component 1"]
    SPLIT --> P2["Upload component 2"]
    SPLIT --> P3["Upload component 3"]
    P1 --> COMPOSE["Compose theo đúng thứ tự"]
    P2 --> COMPOSE
    P3 --> COMPOSE
    COMPOSE --> FINAL["Object hoàn chỉnh"]
    P1 -. "Cleanup" .-> CLEAN["Xóa component tạm"]
    P2 -. "Cleanup" .-> CLEAN
    P3 -. "Cleanup" .-> CLEAN
~~~

Java TransferManager hỗ trợ parallel composite upload khi bật cấu hình phù hợp và xác định kỹ thuật chia phần có lợi cho workload. Ví dụ:

~~~java
import com.google.cloud.storage.transfermanager.ParallelUploadConfig;
import com.google.cloud.storage.transfermanager.TransferManager;
import com.google.cloud.storage.transfermanager.TransferManagerConfig;
import com.google.cloud.storage.transfermanager.UploadResult;
import java.nio.file.Path;
import java.util.List;

public List<UploadResult> uploadFilesInParallel(
        String bucket,
        List<Path> files) throws Exception {

    TransferManager manager = TransferManagerConfig.newBuilder()
            .setAllowParallelCompositeUpload(true)
            .setMaxWorkers(8)
            .build()
            .getService();

    try (manager) {
        ParallelUploadConfig config = ParallelUploadConfig.newBuilder()
                .setBucketName(bucket)
                .build();

        return manager.uploadFiles(files, config).getUploadResults();
    }
}
~~~

**getUploadResults()** chờ các upload hoàn tất và trả kết quả từng file. Hãy kiểm tra trạng thái từng result; không coi job hoàn tất là mọi file đều thành công.

### 7.2. Điều kiện và giới hạn quan trọng

Parallel composite upload có thể tăng tốc nhưng tạo thêm nhiều object tạm và operation:

- Một lần compose nhận tối đa 32 source objects; TransferManager xử lý việc chia và compose theo giới hạn của dịch vụ.
- Object cuối là composite object, có CRC32C nhưng không có MD5 hash.
- Nếu consumer phụ thuộc MD5, không chọn chiến lược này nếu không thay đổi được hợp đồng kiểm tra toàn vẹn.
- Upload component và compose tạo thêm Class A operations; chi phí có thể tăng.
- Với storage class khác Standard, component tạm có thể phát sinh early deletion fee.
- Bucket có retention policy hoặc default object hold có thể ngăn cleanup component.
- Object Versioning và soft delete có thể giữ component đã xóa, làm tăng chi phí lưu trữ.
- Nếu tiến trình dừng giữa chừng, component tạm có thể còn lại; cần quy trình kiểm tra và cleanup.
- Cần quyền tạo, đọc/compose và xóa object component; role **roles/storage.objectUser** thường là điểm bắt đầu để đánh giá quyền.

Chỉ bật kỹ thuật này khi benchmark cho thấy throughput tăng đủ bù chi phí và độ phức tạp. Với upload thông thường, resumable **WriteChannel** thường dễ vận hành hơn.

## 8. Download tuần tự bằng ReadChannel

### 8.1. Streaming tới file

Với object lớn, không gọi **getContent()** để lấy toàn bộ bytes vào heap. Dùng **ReadChannel** và truyền từng buffer tới file:

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Path;

public void downloadToFile(
        Storage storage,
        String bucket,
        String objectName,
        Path destination) throws Exception {

    try (ReadChannel reader = storage.reader(
                BlobId.of(bucket, objectName));
         OutputStream output = Files.newOutputStream(destination)) {
        Channels.newInputStream(reader).transferTo(output);
    }
}
~~~

Ví dụ trên stream trực tiếp tới file. Trong production nên ghi vào file tạm cùng filesystem, kiểm tra checksum sau khi hoàn tất, rồi atomic move sang file đích. Nhờ vậy người dùng không nhìn thấy file tải dở dưới tên file hoàn chỉnh.

### 8.2. Điều chỉnh read chunk size

**ReadChannel.setChunkSize(int)** đặt kích thước tối thiểu của một lần đọc RPC; dữ liệu được buffer cục bộ cho tới khi ứng dụng tiêu thụ. Chunk lớn có thể giảm số RPC nhưng tăng bộ nhớ và lượng dữ liệu nạp trước. Chunk nhỏ phù hợp bộ nhớ hạn chế nhưng có thể tăng overhead.

Không dùng cùng một chunk size cho mọi workload. Đo latency, throughput, heap và số download đồng thời trong môi trường gần production.

## 9. Tiếp tục download từ byte offset

### 9.1. Vì sao phải ghim generation?

Nếu download bị ngắt rồi ứng dụng tiếp tục từ offset cũ bằng object name live, object có thể đã bị thay thế. Khi đó phần đầu file thuộc generation cũ còn phần tiếp theo thuộc generation mới, tạo ra file hỏng nhưng khó phát hiện.

Hãy đọc metadata trước, lưu generation và tải lại đúng generation đó. Generation được dùng trong **BlobId** để xác định phiên bản dữ liệu cụ thể.

### 9.2. Resume bằng seek

Ví dụ khung tiếp tục download từ offset đã checkpoint:

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public void resumeDownload(
        Storage storage,
        String bucket,
        String objectName,
        long generation,
        long completedBytes,
        Path partialFile) throws Exception {

    BlobId pinnedVersion = BlobId.of(bucket, objectName, generation);

    try (ReadChannel reader = storage.reader(pinnedVersion);
         FileChannel output = FileChannel.open(
                 partialFile,
                 StandardOpenOption.CREATE,
                 StandardOpenOption.READ,
                 StandardOpenOption.WRITE)) {

        if (output.size() < completedBytes) {
            throw new IllegalStateException("File tạm ngắn hơn checkpoint");
        }
        output.truncate(completedBytes);
        output.position(completedBytes);
        reader.seek(completedBytes);

        ByteBuffer buffer = ByteBuffer.allocate(8 * 1024 * 1024);
        int read;
        while ((read = reader.read(buffer)) != -1) {
            if (read == 0) {
                continue;
            }
            buffer.flip();
            while (buffer.hasRemaining()) {
                output.write(buffer);
            }
            buffer.clear();
        }
        output.force(true);
    }
}
~~~

Đoạn trên minh họa offset logic. Với triển khai thực tế, dùng **FileChannel.position(completedBytes)** hoặc một cơ chế append có kiểm soát để ghi đúng vị trí. Trước khi tiếp tục, xác nhận kích thước file tạm khớp checkpoint; truncate phần bytes ghi dở sau checkpoint nếu cần.

### 9.3. Resume bằng ReadChannel capture/restore

**ReadChannel** cũng triển khai **Restorable**. Có thể gọi **capture()** để lưu trạng thái reader rồi khôi phục bằng **RestorableState.restore()**. Cơ chế này hữu ích khi một worker khác tiếp tục tác vụ hoặc ứng dụng cần lưu trạng thái đọc.

Không dùng đồng thời reader gốc và reader đã restore. Lưu checkpoint bền vững, bảo vệ state, pin generation và kiểm thử khôi phục sau process restart. Với một tác vụ đơn giản, lưu generation + byte offset rồi **seek()** thường dễ quan sát và vận hành hơn.

## 10. Tải xuống theo byte range qua HTTP

Cloud Storage hỗ trợ HTTP Range để đọc một phần object. Ví dụ header:

~~~http
Range: bytes=0-8388607
~~~

Phạm vi byte là inclusive: **bytes=0-8388607** yêu cầu 8 MiB đầu tiên. Khi download bị ngắt, client có thể yêu cầu phần còn lại từ byte tiếp theo.

Một quy trình resume an toàn cần:

1. Đọc generation và size trước khi tải.
2. Gửi range request cho generation đã xác định.
3. Ghi dữ liệu vào file tạm tại đúng offset.
4. Lưu checkpoint sau khi bytes được ghi bền vững xuống đĩa.
5. Khi tiếp tục, dùng cùng generation và offset.
6. Sau khi tải đủ, kiểm tra kích thước và checksum toàn object.
7. Atomic move file tạm sang tên cuối.

Nếu tự gọi JSON/XML API, cần xử lý status code, **Content-Range**, response length, timeout và retry. Nếu dùng Java **ReadChannel**, client library giúp quản lý giao thức đọc; ứng dụng vẫn cần checkpoint và file tạm.

## 11. Sliced object download và TransferManager

### 11.1. Khi nào nên dùng?

Sliced download chia một object lớn thành nhiều range GET, tải song song vào các vùng của file tạm rồi ghép thành file hoàn chỉnh. Kỹ thuật này có thể tăng throughput khi network và disk đủ nhanh.

Java TransferManager hỗ trợ bật divide-and-conquer download:

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.transfermanager.DownloadResult;
import com.google.cloud.storage.transfermanager.ParallelDownloadConfig;
import com.google.cloud.storage.transfermanager.TransferManager;
import com.google.cloud.storage.transfermanager.TransferManagerConfig;
import java.nio.file.Path;
import java.util.List;

public List<DownloadResult> downloadInParallel(
        String bucket,
        List<BlobInfo> objects,
        Path destinationDirectory) throws Exception {

    TransferManager manager = TransferManagerConfig.newBuilder()
            .setAllowDivideAndConquerDownload(true)
            .setMaxWorkers(8)
            .build()
            .getService();

    try (manager) {
        ParallelDownloadConfig config = ParallelDownloadConfig.newBuilder()
                .setBucketName(bucket)
                .setDownloadDirectory(destinationDirectory)
                .build();

        return manager.downloadBlobs(objects, config).getDownloadResults();
    }
}
~~~

TransferManager nhận danh sách BlobInfo và tải các object song song; cấu hình divide-and-conquer cho phép chia object thành các lát khi thư viện xác định có lợi. **getDownloadResults()** chờ hoàn tất và cung cấp trạng thái từng download.

### 11.2. Pin generation cho từng object

Khi tải theo nhiều range, tất cả lát phải đọc cùng một generation. Hãy tạo BlobInfo với BlobId chứa generation đã đọc:

~~~java
BlobInfo sourceVersion = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName, expectedGeneration))
    .build();
~~~

Đưa BlobInfo đó vào danh sách download. Nếu object name live thay đổi trong lúc các range chạy, việc không pin generation có thể khiến các phần dữ liệu không đồng nhất. Tài liệu GCS khuyến nghị cung cấp generation nguồn cho mỗi request tải lát để tránh hỏng dữ liệu.

### 11.3. Chi phí và giới hạn

- Nhiều range request làm tăng số request và có thể tăng chi phí.
- Nhiều lát đồng thời tiêu thụ thread, connection, buffer và disk I/O.
- Ghi vào nhiều vị trí file có thể chậm trên ổ đĩa seek kém.
- Sliced download chỉ phù hợp khi tải toàn bộ object; nếu chỉ cần một đoạn, dùng range read đơn.
- Cần CRC32C để kiểm tra tính toàn vẹn của sliced download.
- Đảm bảo đủ dung lượng cho file tạm và có cleanup khi job thất bại.

Nếu disk hoặc network đã là nút thắt, tăng worker có thể không cải thiện tốc độ. Benchmark với số worker thấp trước rồi tăng dần.

## 12. Checksum và tính toàn vẹn

### 12.1. CRC32C và MD5

Cloud Storage hỗ trợ checksum để phát hiện dữ liệu bị thay đổi trong quá trình truyền:

- **CRC32C:** checksum được khuyến nghị cho nhiều luồng kiểm tra dữ liệu, đặc biệt với composite object và sliced download.
- **MD5:** có thể được dùng để kiểm tra một số object upload/download thông thường nếu object có giá trị MD5.
- **ETag:** là validator; không được mặc định coi ETag luôn bằng MD5.

Parallel composite upload tạo composite object chỉ có CRC32C, không có MD5. Nếu ứng dụng downstream yêu cầu MD5, phải chọn chiến lược upload khác hoặc thay đổi hợp đồng kiểm tra toàn vẹn.

### 12.2. Không kiểm tra từng chunk như checksum toàn object

Checksum object áp dụng cho toàn bộ object. Không so checksum toàn object với checksum của một byte range hoặc chunk riêng. Với sliced download, cần kiểm tra CRC32C theo cơ chế hỗ trợ của công cụ/client và sau cùng xác minh toàn bộ file.

### 12.3. Lưu manifest cho tác vụ truyền

Một tác vụ truyền lớn có thể lưu manifest:

~~~json
{
  "jobId": "transfer-2026-001",
  "bucket": "training-large-files-dev",
  "objectName": "exports/archive-001.bin",
  "generation": 1740000000000000,
  "expectedSize": 10737418240,
  "checksumType": "CRC32C",
  "completedBytes": 5368709120,
  "state": "IN_PROGRESS"
}
~~~

Đây là dữ liệu minh họa. Manifest nên lưu trong database/job store, không gắn toàn bộ trạng thái vào object metadata. Các trường cần thiết gồm job ID, bucket/object, generation, size, checksum, checkpoint/offset, thời điểm cập nhật, số lần retry và trạng thái. Không lưu session URI hoặc RestorableState dạng plaintext trong log.

## 13. Retry, timeout và idempotency

### 13.1. Retry lỗi tạm thời

Java Cloud Storage client có retry/backoff cho các operation được xác định là idempotent. Các lỗi tạm thời thường gồm:

- Connection reset hoặc connection bị đóng ngoài dự kiến.
- HTTP 408 Request Timeout.
- HTTP 429 Too Many Requests.
- HTTP 500, 502, 503 và 504.

Java client sử dụng exponential backoff và có thể cấu hình RetrySettings. Không tự tạo vòng lặp retry vô hạn quanh mọi exception.

### 13.2. Phân biệt lỗi có thể retry

| Lỗi | Cách xử lý |
| --- | --- |
| Timeout/mất kết nối | Kiểm tra trạng thái upload/download và tiếp tục từ checkpoint nếu có |
| 429 hoặc 5xx | Retry có backoff và giới hạn tổng thời gian |
| 401 | Kiểm tra ADC/token, không retry liên tục với credential sai |
| 403 | Kiểm tra IAM/policy, không retry nếu quyền không đổi |
| 404 | Kiểm tra bucket/object/generation và vòng đời dữ liệu |
| 412 Precondition Failed | Đọc lại generation, xử lý conflict; không bỏ precondition |
| Checksum mismatch | Không công bố file; tải lại/khởi tạo lại theo chiến lược đã chọn |

### 13.3. Idempotency khi upload

Một request upload có thể đã được GCS xử lý nhưng client mất response. Nếu retry không có precondition, ứng dụng có thể ghi đè object đã hoàn tất. Dùng **doesNotExist()** cho object mới hoặc generation precondition cho phép thay thế có điều kiện.

Khi nhận timeout không rõ kết quả, hãy kiểm tra object/generation/checksum trước khi khởi tạo một upload mới. Đừng giả định timeout đồng nghĩa server chưa nhận dữ liệu.

### 13.4. Timeout theo giai đoạn

Cần đặt timeout hợp lý cho:

- Khởi tạo session.
- Mỗi chunk hoặc RPC.
- Tổng thời gian job.
- Thời gian chờ khi ứng dụng shutdown.
- Thời gian chờ retry/backoff.

Upload lớn không nên dùng một timeout ngắn giống API đọc metadata. Tuy nhiên, tăng timeout vô hạn sẽ giữ worker và connection quá lâu. Dùng deadline tổng, cancellation và tiến độ để người vận hành biết job còn hoạt động hay đã bị kẹt.

## 14. Kiểm soát nguồn và đích truyền dữ liệu

### 14.1. Nguồn phải ổn định

Nếu file nguồn thay đổi trong lúc resumable upload, các lần retry có thể gửi nội dung không đồng nhất. Có thể:

- Tạo snapshot hoặc copy file vào thư mục staging.
- Ghi nhận size, modification time và checksum trước khi bắt đầu.
- Giữ file không thay đổi trong suốt upload.
- Kiểm tra checksum cuối cùng trước khi đánh dấu job hoàn tất.

Với nguồn stream không thể đọc lại, hãy ghi ra file tạm hoặc thiết kế pipeline có checkpoint riêng.

### 14.2. Đích download phải có file tạm

Không tải trực tiếp vào tên file mà người dùng hoặc service khác đang đọc. Dùng file tạm, lưu offset và chỉ rename sau khi xác minh toàn vẹn. Nếu job thất bại, giữ file tạm để resume hoặc cleanup theo chính sách.

### 14.3. Giới hạn concurrency

Mỗi job song song tiêu thụ:

- Một phần heap/buffer.
- Network connections.
- File descriptors.
- CPU để checksum/mã hóa.
- Disk bandwidth và IOPS.
- Request quota/operation của Cloud Storage.

Đặt max workers theo resource budget của container/VM. Tách pool upload/download khỏi HTTP request threads để không làm nghẽn API server.

## 15. Vận hành và quan sát tiến độ

Một transfer job nên có trạng thái rõ ràng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Đã tạo job, chưa truyền |
| INITIATING | Đang tạo resumable session hoặc chuẩn bị file |
| IN_PROGRESS | Đang truyền bytes |
| PAUSED | Đã checkpoint, chờ tiếp tục |
| VERIFYING | Đang kiểm tra size/checksum/generation |
| COMPLETED | Đã hoàn tất và xác minh |
| RETRYING | Đang xử lý lỗi tạm thời |
| FAILED | Lỗi không thể tự khôi phục |
| CANCELLED | Đã dừng theo yêu cầu |

Các metric hữu ích:

- Bytes đã gửi/nhận và tổng bytes.
- Tốc độ truyền trung bình/hiện tại.
- Chunk size và worker count.
- Số lần retry, mã lỗi và thời gian backoff.
- Thời gian khởi tạo, truyền, verify và cleanup.
- Heap/buffer, network throughput, disk free space.
- Số component tạm còn lại sau parallel composite upload.

Không log session URI, signed URL, access token, nội dung file hoặc RestorableState. Dùng job ID và object ID nội bộ để liên kết log/trace.

## 16. Ví dụ thiết kế TransferJob trong Spring Boot

Một service có thể tách API điều phối và worker truyền dữ liệu:

~~~java
public interface TransferJobRepository {
    TransferJob findById(String jobId);
    void save(TransferJob job);
}

public record TransferJob(
        String jobId,
        String bucket,
        String objectName,
        long generation,
        long totalBytes,
        long completedBytes,
        String checksum,
        TransferState state) {}

public enum TransferState {
    PENDING,
    IN_PROGRESS,
    PAUSED,
    VERIFYING,
    COMPLETED,
    FAILED,
    CANCELLED
}
~~~

Service điều phối chịu trách nhiệm:

1. Xác thực người dùng và quyền truy cập tài liệu.
2. Tạo job ID và object name ổn định.
3. Chọn phương thức truyền dựa trên size, nguồn dữ liệu và nhu cầu resume.
4. Lưu metadata/checkpoint.
5. Gửi công việc tới executor/queue.
6. Cập nhật bytes và trạng thái theo checkpoint.
7. Kiểm tra generation/size/checksum sau khi hoàn tất.
8. Công bố object cho nghiệp vụ sau khi xác minh.

Không giữ một HTTP request mở trong nhiều phút chỉ để upload file hàng GB. Trả job ID để client theo dõi tiến độ; backend thực hiện transfer trong worker có giới hạn tài nguyên.

## 17. Kiểm thử lỗi và khôi phục

### 17.1. Unit test

- Chọn chiến lược upload theo size và loại nguồn.
- Tạo object name và metadata ổn định.
- Tính checkpoint/offset đúng.
- Không tiến offset trước khi bytes được ghi bền vững.
- Mapping lỗi 403/404/412/5xx.
- Chỉ đánh dấu COMPLETED sau khi checksum/size được xác minh.

### 17.2. Integration test với GCP test project

1. Upload file đủ lớn để dùng resumable writer.
2. Kiểm tra object chỉ xuất hiện hoàn chỉnh sau khi writer đóng thành công.
3. Capture state, restore writer và tiếp tục ghi.
4. Download một object có generation cố định, seek từ offset và nối tiếp file tạm.
5. Thử thay object live giữa hai lần đọc; xác nhận generation pin bảo vệ nội dung.
6. Chạy sliced download với TransferManager và xác minh CRC32C.
7. Kiểm tra kết quả từng UploadResult/DownloadResult.
8. Kiểm tra IAM permission, timeout và retry.
9. Dọn component/file tạm và xác nhận không còn tài nguyên ngoài dự kiến.

### 17.3. Fault injection

Mô phỏng các tình huống:

- Ngắt mạng giữa chunk.
- Kill process sau khi checkpoint được lưu.
- Hết dung lượng đĩa khi download.
- File nguồn bị thay đổi giữa upload.
- Credential hết hạn.
- GCS trả 429/503.
- Object bị ghi đè trước khi resume download.
- Cleanup component thất bại sau parallel composite upload.

Kết quả cần đạt: không tạo file cuối bị hỏng, không trộn generation, không đánh dấu job hoàn tất sai, không retry vô hạn và có thể tiếp tục hoặc thất bại có kiểm soát.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Upload lại từ đầu sau khi mất mạng | Dùng direct upload hoặc không lưu session/checkpoint | Dùng resumable writer hoặc createFrom |
| Upload chậm dù file lớn | Chunk quá nhỏ, network round-trip cao hoặc buffer thấp | Benchmark chunk size và location |
| OOM khi nhiều upload cùng lúc | Buffer × worker count vượt memory budget | Giảm chunk size hoặc concurrency |
| Upload resume bị checksum mismatch | Nguồn file thay đổi giữa các lần gửi | Snapshot nguồn và xác minh checksum |
| Session URI không dùng được | Hết hạn, bị hủy hoặc thất lạc | Khởi tạo session mới và upload lại |
| Download tiếp tục nhưng file hỏng | Offset sai hoặc object live đã đổi generation | Pin generation và kiểm tra kích thước file tạm |
| Sliced download chậm hơn | Disk seek chậm hoặc worker quá nhiều | Giảm số lát, dùng streaming tuần tự |
| Composite upload thiếu MD5 | Final object là composite object | Dùng CRC32C hoặc chọn upload không composite |
| Component tạm còn trong bucket | Job chết trước cleanup | Theo dõi prefix tạm và có quy trình cleanup |
| Parallel composite upload bị 403 | Thiếu quyền get/delete component | Cấp IAM object permissions đúng phạm vi |
| Upload component không xóa được | Retention, hold, soft delete hoặc versioning | Kiểm tra bucket policy trước khi bật kỹ thuật |
| 412 khi resume/ghi tiếp | Generation precondition không còn khớp | Đọc lại trạng thái và tạo quyết định nghiệp vụ |
| Worker bị treo | Timeout quá dài hoặc retry không giới hạn | Đặt deadline tổng, cancellation và metric tiến độ |

## 19. So sánh với AWS S3 và Azure Blob Storage

| Khía cạnh | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Upload tiếp tục | Resumable upload session, Java WriteChannel | Multipart upload, upload ID và part number | Block blob staged blocks và commit block list |
| Download tiếp tục | Range request, ReadChannel seek/capture | Range GET và ETag/version conditions | Range download và ETag/version conditions |
| Upload song song | TransferManager parallel composite upload | Multipart upload | Parallel block upload |
| Version token | Generation | Version ID / ETag | Version ID / ETag |
| Checksum | CRC32C và MD5 theo object/API | CRC/checksum algorithm theo API | Transactional/content checksum theo API |
| Cleanup | Component objects sau compose | Abort multipart upload và dọn part | Uncommitted blocks/lifecycle theo API |

Không chuẩn hóa session URI, upload ID, generation, ETag và block ID thành một kiểu token giả định có cùng semantics. Adapter đa cloud nên đưa ra các thao tác nghiệp vụ như upload, resume, downloadRange và verify; adapter của từng provider giữ chi tiết session, part/block, precondition và cleanup.

## 20. Ghi nhớ

- File nhỏ có thể dùng direct upload; file lớn nên dùng resumable upload qua **Storage.writer** hoặc **Storage.createFrom**.
- Java **WriteChannel** và **ReadChannel** hỗ trợ **capture/restore**; checkpoint phải được lưu an toàn và chỉ một channel được tiếp tục sử dụng.
- Chunk size là trade-off giữa throughput, số RPC, retry và bộ nhớ; tính cả số worker đồng thời.
- Download tiếp tục phải pin generation và ghi vào file tạm theo offset đã xác nhận.
- TransferManager sliced download có thể tăng tốc khi network/disk phù hợp; cần CRC32C và giới hạn worker.
- Parallel composite upload có thể tăng throughput nhưng tạo object tạm, thêm operation, yêu cầu cleanup và không cung cấp MD5 cho object cuối.
- Retry phải dựa trên tính idempotent, precondition, deadline và trạng thái thật của object.
- Chỉ công bố file sau khi xác minh size/checksum; log tiến độ nhưng không log session URI hoặc nội dung nhạy cảm.

### Tài liệu tham khảo

- [Resumable uploads — Cloud Storage](https://docs.cloud.google.com/storage/docs/resumable-uploads)
- [Perform resumable uploads — Cloud Storage](https://docs.cloud.google.com/storage/docs/performing-resumable-uploads)
- [Retry strategy — Cloud Storage](https://docs.cloud.google.com/storage/docs/retry-strategy)
- [Sliced object downloads — Cloud Storage](https://docs.cloud.google.com/storage/docs/sliced-object-downloads)
- [Parallel composite uploads — Cloud Storage](https://docs.cloud.google.com/storage/docs/parallel-composite-uploads)
- [Object reads and downloads — Cloud Storage](https://docs.cloud.google.com/storage/docs/reads-and-downloads)
- [Java Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Java TransferManager](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.transfermanager.TransferManager)
- [Java TransferManagerConfig](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.transfermanager.TransferManagerConfig)
- [Java ReadChannel](https://docs.cloud.google.com/java/docs/reference/google-cloud-core/latest/com.google.cloud.ReadChannel)
- [Java WriteChannel](https://docs.cloud.google.com/java/docs/reference/google-cloud-core/latest/com.google.cloud.WriteChannel)
- [Java RestorableState](https://docs.cloud.google.com/java/docs/reference/google-cloud-core/latest/com.google.cloud.RestorableState)
