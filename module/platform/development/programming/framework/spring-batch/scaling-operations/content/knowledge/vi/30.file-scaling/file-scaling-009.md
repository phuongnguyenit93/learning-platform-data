# Object storage và remote worker trong Spring Batch

> **Chương:** File scaling
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Khi một job xử lý hàng terabyte dữ liệu và worker chạy ở nhiều máy hoặc container, đường dẫn `/data/import/orders.csv` trên manager **không mặc nhiên tồn tại ở worker**. Gắn network filesystem cho mọi node đôi khi giúp khởi đầu nhanh nhưng dễ tạo điểm nghẽn và ràng buộc triển khai. Object storage như Amazon S3, Google Cloud Storage hoặc Azure Blob Storage là một lựa chọn để **chia sẻ dữ liệu đầu vào/đầu ra qua API** mà không bắt buộc các worker có ổ đĩa chung.

Tuy nhiên, thay `File` bằng URI `s3://...` **chưa làm batch phân tán trở nên đúng**. Worker cần truy cập **đúng phiên bản object**, đọc đúng phần dữ liệu, có checkpoint khôi phục được, không ghi đè kết quả của worker khác và xử lý an toàn khi **đã upload thành công nhưng phản hồi thất lạc**. Bài này xây dựng mô hình từ **manifest bất biến → partitioner → remote workers → staging output → đối soát/publish**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa **object storage**, shared filesystem và đĩa cục bộ của pod; chọn phương án đọc phù hợp với file lớn và worker phân tán.
2. Định nghĩa **input manifest bất biến** với bucket/container, object key, version/generation, size và checksum, rồi dùng manifest để tạo partition ổn định.
3. Tổ chức `Partitioner`, `ExecutionContext`, `@StepScope` và `FlatFileItemReader` để mỗi remote worker đọc đúng object, không phụ thuộc đường dẫn trên manager.
4. Phân biệt **phân chia theo file/object** với **HTTP Range GET theo byte** và các rủi ro khi cắt CSV, UTF-8, gzip hoặc định dạng nhiều dòng.
5. Thiết kế output staging theo partition/attempt, chống ghi trùng và **publish bằng manifest** thay vì coi mỗi lần PUT là commit của toàn job.
6. Xử lý checkpoint, retry/restart, redelivery, worker crash và kết quả chưa rõ bằng version cố định, unique operation key và reconciliation.
7. Tối ưu số worker theo băng thông, request rate, chi phí, disk, heap, connection pools, bảo mật và observability; viết kiểm thử fault injection trên môi trường gần production.

## 1. Vì sao remote worker cần thay đổi cách quản lý file?

Trong môi trường chạy đơn máy:

~~~text
Manager JVM
  /data/orders/part-001.csv
  /data/orders/part-002.csv
          |
          +--> worker threads cùng máy có thể đọc path này
~~~

Trong Kubernetes hoặc VM riêng biệt:

~~~text
Manager pod       Worker pod A        Worker pod B
/data/import      /tmp/work-A         /tmp/work-B
      |                 |                   |
      +---------- không có filesystem chung --------+
~~~

Nếu manager đưa cho worker `/data/import/part-001.csv`, đường dẫn đó là **đường dẫn cục bộ của manager**, không phải địa chỉ dữ liệu có thể phân giải từ xa. `@StepScope` hoặc `ExecutionContext` chỉ vận chuyển **tham số**, không tự chép file giữa các máy.

Với object storage:

~~~mermaid
flowchart TB
    U["Upstream: tạo input objects"] --> OS[("Object storage<br/>immutable input versions")]
    U --> MF["Sealed input manifest"]
    MF --> M["Spring Batch manager<br/>Partitioner + JobRepository"]
    M --> Q["Partition requests<br/>broker / remote handler"]
    Q --> A["Worker pod A<br/>download/stream object A"]
    Q --> B["Worker pod B<br/>download/stream object B"]
    Q --> C["Worker pod C<br/>download/stream object C"]
    OS --> A
    OS --> B
    OS --> C
    A --> OUT[("Staged output objects / business DB")]
    B --> OUT
    C --> OUT
    OUT --> V["Reconcile + publish manifest"]
~~~

**Manager khởi chạy một job logic**; manager step phân công nhiều worker `StepExecution`. Mỗi worker phải có quyền đọc đúng dữ liệu từ object storage. Shared metadata trong `JobRepository` theo dõi tiến độ và restart; object storage giữ payload, **không thay thế repository**.

## 2. Những đặc tính object storage khác filesystem

| Khía cạnh | Filesystem cục bộ/NFS | Object storage |
| --- | --- | --- |
| Truy cập | `File`, POSIX streams và đường dẫn | API/SDK qua bucket + object key |
| Định danh | Path, inode/metadata tùy hệ thống | Bucket/container + key + version/generation nếu bật |
| Sửa một phần file | Có thể seek/append tùy filesystem | Thường thay thế object; không coi là file POSIX có thể append tại chỗ |
| Đọc một vùng | `FileChannel.position(...)` hoặc stream | HTTP Range GET nếu provider/object hỗ trợ |
| Đổi tên/publish | Một số filesystem có atomic rename trong cùng volume | Thường **không có atomic rename chung**; copy+delete không tương đương |
| Danh sách nhiều file | Directory listing | Prefix listing và pagination; không phải transaction snapshot đa object |
| Độ trễ | Thường thấp khi dữ liệu gần CPU | Network latency, request overhead và giới hạn service |
| Khả năng chia sẻ | Cần mount/volume chung | Workers có network + credentials phù hợp |
| Retry | Lỗi local I/O/volume | HTTP 429/5xx, timeout, auth, version conflict, throttling |

**Không gom mọi provider thành một semantics duy nhất.** Amazon S3 hiện có bảo đảm strong read-after-write cho PUT/DELETE và LIST theo tài liệu dịch vụ, nhưng điều đó **không tạo snapshot transaction atomic của nhiều keys**. Những hành vi như conditional write, generation precondition, range requests và tính nhất quán cần được kiểm chứng trên **provider, vùng và API cụ thể**.

### URI là địa chỉ, không phải snapshot

~~~text
s3://orders-input/2026-11-25/part-0001.csv
~~~

URI này xác định một **object key**, nhưng nếu producer có thể overwrite key thì worker A đọc phiên bản cũ, worker B đọc phiên bản mới khi restart. Cùng key **không chứng minh bytes giống nhau**.

An toàn hơn là:

~~~text
provider      = S3
bucket        = orders-input
key           = 2026-11-25/part-0001.csv
versionId     = <ID phiên bản object đã chốt>
sizeBytes     = 734003200
sha256Hex     = <SHA-256 của bytes chính thức>
sourceVersion = orders-2026-11-25-v1
~~~

`versionId` là ví dụ cho S3 bucket đã bật Versioning; GCS dùng `generation`, Azure Blob có version/snapshot hoặc điều kiện ETag tùy cấu hình. Nếu nhà cung cấp hoặc bucket chưa hỗ trợ versioning, có thể sử dụng **immutable key theo content/run** cùng policy cấm ghi đè, nhưng phải kiểm thử việc không ai thay đổi dữ liệu sau khi manifest được chốt.

## 3. Dùng manifest để đóng băng tập đầu vào

### Tại sao không để Partitioner gọi LIST mỗi lần?

Giả sử manager liệt kê prefix lúc 01:00, upstream tiếp tục upload file mới lúc 01:02. Khi worker bị lỗi và job restart lúc 02:00, `Partitioner` gọi LIST lại và nhận danh sách khác. Một số logical partition có thể bị đổi nội dung, làm checkpoint không còn tương ứng với input cũ.

**Manifest** là danh sách **đã được xác nhận hoàn chỉnh** của một batch input. Tạo manifest sau khi upstream upload/validate tất cả objects; manager load **đúng manifest version** gắn với `JobInstance`.

~~~json
{
  "manifestId": "orders-2026-11-25-v1",
  "createdAt": "2026-11-26T00:30:00Z",
  "schemaVersion": "orders-csv-v3",
  "recordCountExpected": 18000000,
  "objects": [
    {
      "partitionKey": "object-0000",
      "bucket": "orders-input",
      "key": "snapshots/2026-11-25/part-0000.csv",
      "versionId": "3HL4-example-version",
      "sizeBytes": 734003200,
      "sha256Hex": "sha256-of-exact-bytes"
    },
    {
      "partitionKey": "object-0001",
      "bucket": "orders-input",
      "key": "snapshots/2026-11-25/part-0001.csv",
      "versionId": "9hT4-example-version",
      "sizeBytes": 629145600,
      "sha256Hex": "sha256-of-exact-bytes"
    }
  ]
}
~~~

**Lưu ý:** Những giá trị `versionId`/`sha256Hex` trong JSON chỉ là **placeholder minh họa**, không phải kết quả checksum hợp lệ. Hệ thống thật phải tạo checksum từ bytes và lưu trong manifest.

### Hợp đồng manifest tối thiểu

| Trường | Chức năng |
| --- | --- |
| `manifestId` / `sourceVersion` | Nhận diện snapshot, giữ nguyên qua restart |
| `schemaVersion` | Reader chọn parser/mapping đúng |
| `partitionKey` | Tên logical partition duy nhất, ổn định |
| `bucket` + `key` | Vị trí object |
| `versionId` / `generation` | Ràng buộc bytes ở phiên bản cụ thể |
| `sizeBytes` | Phát hiện thay đổi, hỗ trợ ước lượng phân vùng |
| `sha256Hex` hoặc checksum đáng tin | Kiểm tra tính toàn vẹn; không lấy ETag làm SHA-256 |
| `recordCountExpected` | Đối soát số records nếu producer cung cấp đáng tin |
| `tenant/sourceSystem` | Cách ly dữ liệu và phân quyền |
| `compression` / `encoding` | Chọn reader đúng định dạng |

### Trình tự tạo snapshot an toàn

1. Upstream upload từng object vào prefix/key bất biến; chờ **PUT/multipart complete** thành công.
2. Đọc metadata, kiểm tra kích thước, checksum và quyền truy cập.
3. Tạo manifest có danh sách **chính xác** những objects thuộc kỳ dữ liệu.
4. Publish **một manifest version/marker** sau cùng bằng quy tắc không cho chỉnh sửa âm thầm.
5. Gắn `manifestId` hoặc immutable manifest pointer vào **identifying JobParameters**.
6. Manager/worker **không mở rộng danh sách bằng LIST** trong lúc job chạy/restart.

Việc publish một manifest cuối giúp xác định **tập dữ liệu được công nhận**, dù bản thân object storage không có multi-object transaction. Nếu một object trong manifest vẫn có thể bị xóa hoặc overwrite, manifest chưa đủ: phải thêm versioning, retention/immutability và validation.

### JobParameters dùng identity nào?

~~~text
jobName        = importOrdersJob
businessDate   = 2026-11-25   (identifying)
manifestId     = orders-2026-11-25-v1   (identifying)
triggeredBy    = SCHEDULER   (non-identifying)
~~~

Nếu retry một job thất bại, **giữ nguyên identifying parameters** để restart cùng `JobInstance`. Không sinh `run.id` mới hoặc tạo manifestId mới chỉ vì worker tạm thời không tải được file.

## 4. Chọn hạt phân vùng: một object hay nhiều object?

Giả sử manifest có 120 file CSV, mỗi file khoảng 500 MB–4 GB. Một lựa chọn thực dụng là **một object cho mỗi worker StepExecution**. Nhưng nếu có hàng triệu objects nhỏ, một StepExecution cho từng object sẽ tạo quá nhiều metadata và request overhead.

| Cách phân vùng | Phù hợp | Đánh đổi |
| --- | --- | --- |
| **Một object → một partition** | Số object vừa phải, file có thể xử lý độc lập | File quá lệch size sẽ gây straggler |
| **N objects → một partition** | Nhiều object nhỏ | Phải checkpoint object index + record index, ổn định danh sách |
| **Byte-range → một partition** | Object rất lớn, định dạng hỗ trợ chia vùng | Phải căn ranh giới record, compression/encoding phức tạp |
| **Một shard/row group → một partition** | Parquet/columnar có metadata chia vùng | Reader cần hiểu định dạng/row groups |
| **Dynamic work queue** | Số object/range nhiều và workload skew | Cần atomic claim, lease/fencing, restart reconciliation |

Mục tiêu không phải ép `gridSize` bằng số object; `gridSize` thường liên quan **số worker đồng thời được gợi ý cho handler**, còn `Partitioner` quyết định tạo bao nhiêu logical partitions tùy code/architecture.

**Quyết định theo dữ liệu:** Nếu có 500.000 file mỗi file 1 KB, tạo 500.000 `StepExecution` thường không phù hợp. Hãy group manifest ổn định hoặc dùng một cơ chế queue/reader chuyên dụng, rồi đo overhead của `JobRepository` và object store.

## 5. Partitioner lấy metadata từ manifest bất biến

Ví dụ Java 17 / Spring Batch 5.x: `Partitioner` nhận **danh sách đã sealed**, không trực tiếp gọi LIST mỗi khi được hỏi phân vùng.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public record ObjectRef(
        String partitionKey,
        String bucket,
        String key,
        String versionId,
        String sha256Hex,
        long sizeBytes) {}

public final class ObjectManifestPartitioner implements Partitioner {

    private final List<ObjectRef> objects;

    public ObjectManifestPartitioner(List<ObjectRef> sealedObjects) {
        this.objects = List.copyOf(sealedObjects);
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions =
                new LinkedHashMap<>();

        for (ObjectRef object : objects) {
            ExecutionContext context = new ExecutionContext();
            context.putString("partitionName", object.partitionKey());
            context.putString("bucket", object.bucket());
            context.putString("objectKey", object.key());
            context.putString("versionId", object.versionId());
            context.putString("sha256Hex", object.sha256Hex());
            context.putLong("sizeBytes", object.sizeBytes());

            ExecutionContext prior =
                    partitions.putIfAbsent(object.partitionKey(), context);
            if (prior != null) {
                throw new IllegalArgumentException(
                        "Trùng partitionKey: " + object.partitionKey());
            }
        }
        return partitions;
    }
}
~~~

`ObjectRef` và `ObjectManifestPartitioner` là **hai public types**, cần đặt ở hai file Java riêng khi triển khai. `gridSize` không được dùng trong ví dụ để thay đổi danh sách: manifest quyết định các partitions, còn handler/executor giới hạn số chạy đồng thời. Với rất nhiều objects, **group** ở bước tạo manifest/partition plan thay vì luôn trả một partition cho từng object.

### Các bất biến khi restart

~~~text
JobInstance + managerStep + partitionKey
    -> bucket/key/versionId/sha256Hex KHÔNG ĐỔI
~~~

Nếu `partition-0007` lần đầu đọc `part-0007.csv` nhưng lần restart đọc `part-0098.csv`, `ExecutionContext`/checkpoint cũ không còn đáng tin. Không tạo partition keys dựa trên thứ tự LIST thay đổi; dùng ID ổn định đã ghi trong manifest.

Một danh sách đối tượng được tải từ database/manifest trước khi chạy phải được **so sánh fingerprint** khi restart nếu có nguy cơ thay đổi cấu hình upstream. Không cho phép “tối ưu lại số partitions” bằng cách đổi mapping của một `JobInstance` đã có executions.

## 6. Remote worker đọc object như thế nào?

Có ba lựa chọn thông dụng:

1. **Stage về local disk** rồi dùng `FlatFileItemReader` chuẩn.
2. **Stream trực tiếp** từ SDK vào custom reader / custom `Resource`.
3. **Range GET / format-aware reader** cho các object lớn có khả năng chia vùng.

### Chọn đường nào?

| Tiêu chí | Stage xuống disk | Stream SDK trực tiếp | Range / format-aware |
| --- | --- | --- | --- |
| Tích hợp reader file truyền thống | Dễ nhất | Cần adapter/resource phù hợp | Cần reader chuyên dụng |
| Network retry | Tách khỏi parsing, tải lại object khi cần | Phải xử lý stream bị ngắt giữa chừng | Phải retry theo range + version |
| Checkpoint theo record | Dùng `ItemStream`/reader chuẩn trên bytes bất biến | Cần giữ/bù vị trí đọc khi mở lại | Cần ánh xạ checkpoint tới offset/record |
| Local disk | Cần đủ dung lượng per active partition | Có thể ít hơn | Tùy buffer và format |
| Object hàng trăm GB | Có thể tốn dung lượng và thời gian stage | Không cần chứa toàn bộ, nhưng restart khó | Có thể tốt nếu định dạng splittable |
| Độ phức tạp | Thấp đến vừa | Vừa đến cao | Cao |

**Không mặc định Spring Batch `FlatFileItemReader` hiểu `s3://bucket/key` như local path.** Nó dùng `Resource` được cung cấp; hỗ trợ protocol nào phụ thuộc Spring/extension thực tế. Nếu muốn tích hợp SDK S3/GCS/Azure, hãy dùng adapter tương ứng hoặc stage local, không dựa vào việc truyền chuỗi URI rồi hy vọng framework tự tải.

## 7. Ví dụ: stage S3 object version về local disk

Một pattern dễ kiểm thử là: **mỗi worker** nhận bucket/key/version/checksum, tải object về thư mục tạm riêng, kiểm tra checksum, sau đó mở `FlatFileItemReader` trên file đó.

~~~mermaid
flowchart LR
    E["StepExecutionContext<br/>bucket/key/version/hash"] --> S["S3 SDK GetObject<br/>đúng version"]
    S --> F["Worker local temp dir"]
    F --> C{"SHA-256 matches?"}
    C -- "Không" --> X["Fail worker<br/>không đọc dữ liệu sai"]
    C -- "Có" --> R["FlatFileItemReader<br/>ItemStream checkpoint"]
    R --> W["Processor / Writer"]
    W --> DB[("Business output / JobRepository")]
~~~

### 7.1. S3 SDK for Java v2: downloader có kiểm tra checksum

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public final class S3VersionedStager {

    private final S3Client s3;
    private final Path stagingRoot;

    public S3VersionedStager(S3Client s3, Path stagingRoot) {
        this.s3 = s3;
        this.stagingRoot = stagingRoot;
    }

    public Path stageAndVerify(
            String bucket, String key, String versionId,
            String expectedSha256Hex) throws IOException {

        Files.createDirectories(stagingRoot);
        Path workDir =
                Files.createTempDirectory(stagingRoot, "batch-object-");
        Path file = workDir.resolve("input.csv");

        try {
            GetObjectRequest request = GetObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .versionId(versionId)
                    .build();

            // Target path chưa tồn tại; SDK tải đúng object version.
            s3.getObject(request, ResponseTransformer.toFile(file));

            String actualSha256Hex = sha256Hex(file);
            if (!actualSha256Hex.equalsIgnoreCase(
                    expectedSha256Hex)) {
                throw new IOException(
                        "Checksum mismatch for staged input object");
            }
            return file;
        } catch (Exception error) {
            Files.deleteIfExists(file);
            Files.deleteIfExists(workDir);
            if (error instanceof IOException io) {
                throw io;
            }
            throw error;
        }
    }

    private static String sha256Hex(Path file) throws IOException {
        try {
            MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");
            try (InputStream stream = Files.newInputStream(file)) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = stream.read(buffer)) != -1) {
                    digest.update(buffer, 0, read);
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

Đây là **ví dụ học tập**, cần thêm dependency AWS SDK v2 `s3`, tạo/inject `S3Client`, cấp credentials và xử lý retry/timeout SDK phù hợp. Vì ví dụ đặt tên `input.csv`, nó dành cho object CSV chưa nén; file gzip/Parquet cần reader tương ứng.

**Các chi tiết cần nhớ:**

- `Files.createTempDirectory(...)` tạo folder riêng cho từng lần stage, tránh hai workers ghi cùng local path.
- `ResponseTransformer.toFile(file)` cần một target path **chưa tồn tại**. Code tạo work directory trước nhưng **không tạo file** trước.
- `versionId` chỉ dùng được khi object được versioning phù hợp; không tự truyền một string đoán từ ETag.
- Checksum lấy từ **manifest đáng tin** và tính từ **bytes chính thức**. `ETag` của S3 **không phải** SHA-256 và không luôn là MD5, nhất là multipart/encryption.
- Nếu download thất bại trước khi reader được tạo, step phải fail/retry theo policy, **không skip tất cả item** của object.
- Phải dọn `workDir` khi reader đã đóng/worker kết thúc; nếu process bị kill, cần cleanup job ở cấp container hoặc TTL để không đầy ephemeral disk.
- Exception runtime từ SDK có thể phát sinh trong `stageAndVerify`; cần phân loại lỗi network retryable và lỗi auth/version/checksum permanent ở tầng chịu trách nhiệm.

Không lưu `stagingRoot`/`file` local path như **nguồn checkpoint xuyên pod**. Khi worker chuyển node, đường dẫn cũ biến mất; worker phải tải lại **đúng object version** rồi phục hồi vị trí đọc hợp lệ.

### 7.2. Reader @StepScope lấy metadata từ ExecutionContext

~~~java
import java.io.IOException;
import java.nio.file.Path;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
import org.springframework.beans.factory.annotation.Value;

public record OrderInput(String operationId, long amountMinor) {}

@Bean
@StepScope
FlatFileItemReader<OrderInput> ordersReader(
        @Value("#{stepExecutionContext['bucket']}")
        String bucket,
        @Value("#{stepExecutionContext['objectKey']}")
        String objectKey,
        @Value("#{stepExecutionContext['versionId']}")
        String versionId,
        @Value("#{stepExecutionContext['sha256Hex']}")
        String sha256Hex,
        S3VersionedStager stager) throws IOException {

    Path localFile = stager.stageAndVerify(
            bucket, objectKey, versionId, sha256Hex);

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("ordersReader")
            .resource(new FileSystemResource(localFile))
            .linesToSkip(1)
            .delimited()
            .names("operationId", "amountMinor")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("operationId"),
                    fieldSet.readLong("amountMinor")))
            .build();
}
~~~

Đặt `OrderInput` trong file Java riêng theo quy tắc ngôn ngữ; phần `@Bean` nằm trong class cấu hình Spring phù hợp, không đặt một method top-level độc lập. Ví dụ reader sử dụng `ItemStream` của Spring Batch để lưu vị trí; **không** tự ghi checkpoint bằng offset mạng.

### Vòng đời và cleanup

Vì đây là **step-scoped bean**, nó được tạo khi worker có `StepExecutionContext` thích hợp. Nhưng việc stage có thể được gọi lại ở **lần restart**, và một bản sao file tạm có thể nằm lại nếu worker crash cứng.

Quy trình production cần:

1. Download sang **worker-owned temporary directory** có quota.
2. Validate object version, content hash và schema trước khi xử lý.
3. Mở reader, xử lý chunk, lưu checkpoint vào `JobRepository`.
4. Đóng reader khi step kết thúc; xóa file tạm bằng cleanup listener/hook sau khi reader đã đóng hoặc cơ chế quản lý workspace tương ứng.
5. Nếu worker/pod bị kill, hệ thống dọn ephemeral storage hoặc background cleanup/TTL với đường dẫn đã xác minh.
6. Khi restart ở pod mới, tải lại cùng object version rồi dùng `ExecutionContext` bền vững để resume.

Không xóa staged file khi writer đang đọc; không dùng một tên file tạm toàn cục cho các worker cùng pod. Nếu step có nhiều readers, `ItemStream.name` cần được đặt **ổn định và không đụng nhau trong cùng StepExecution**.

## 8. Những lưu ý đặc biệt khi dùng streaming trực tiếp

Staging toàn bộ object đôi khi không phù hợp với file hàng trăm GB hoặc pod chỉ có vài GB ephemeral disk. Có thể stream trực tiếp từ object storage qua SDK/HTTP, nhưng **restartability cần được thiết kế**, không thể suy từ việc có `InputStream`.

~~~text
Remote GET stream
  -> parse records
  -> ItemProcessor
  -> ItemWriter
  -> chunk commit
  -> ExecutionContext checkpoint
~~~

### Những câu hỏi một custom streaming reader phải trả lời

- Nếu socket bị cắt ở byte thứ 2.000.000, reader mở lại từ đâu?
- Checkpoint là **byte offset**, record sequence hay logical source key?
- Có thể parse lại record đúng ranh giới **UTF-8/CSV quoting** không?
- Nếu object nén gzip, offset trong compressed stream có tương ứng record boundary không?
- Object version có bị thay đổi giữa hai lần HTTP GET không?
- Nếu reader buffered quá nhiều records trước commit, restart có thể mất/đọc lặp gì?
- Khi StepExecution fail giữa chunk, reader có thể **reposition** không?

**Không** triển khai reader bằng một `InputStream` singleton chia sẻ giữa nhiều chunk threads; trạng thái stream và checkpoint sẽ cạnh tranh. Với một object cho một partition, một step-scoped reader mỗi worker là lựa chọn dễ kiểm soát hơn.

### Staging hay streaming?

- **Stage local** nếu file vừa với disk, cần reader chuẩn và restart đơn giản.
- **Stream** nếu không đủ disk, dữ liệu định dạng tuần tự và có khả năng mở lại/resume có kiểm chứng.
- **Range GET** nếu định dạng splittable và reader hiểu vị trí/ranh giới bản ghi.
- **Chia nhỏ upstream** thành các object vừa phải thường đơn giản, bền vững hơn cố cắt giữa một file CSV khổng lồ.

## 9. Range GET: không được cắt CSV tại byte tùy ý

HTTP Range GET thường yêu cầu vùng byte:

~~~http
GET /snapshots/2026-11-25/huge.csv HTTP/1.1
Range: bytes=0-1048575
~~~

Ví dụ header là minh họa; SDK/provider có cú pháp phù hợp riêng. Vấn đề là **record không trùng ranh giới byte**:

~~~text
...,"ho ten co xuong dong
trong truong CSV",125000,...
       ^
       byte boundary có thể nằm giữa quoted field
~~~

Nếu worker 1 đọc `[0, 1MB)` và worker 2 đọc `[1MB, 2MB)`, hai workers có thể:

- Cùng parse một record hoặc bỏ sót record.
- Bắt đầu giữa **ký tự UTF-8** đa byte.
- Bắt đầu giữa dấu nháy CSV hoặc record nhiều dòng.
- Đọc thiếu record cuối range.

### Khi nào byte-range splitting an toàn?

Chỉ khi **format và parser** cho phép tìm ranh giới record, ví dụ:

1. File có các record theo **dòng vật lý** thật, không cho newline trong field.
2. Worker tìm **ranh giới newline hợp lệ** sau start offset, và cho phép đọc vượt end để hoàn tất record cuối.
3. Mỗi record có một **owner duy nhất**, quy tắc start-inclusive/end-exclusive rõ.
4. UTF-8/encoding được xác định; không bắt đầu parse từ giữa code point.
5. Object version/checksum được cố định, range length và `Content-Range` được xác minh.
6. Replay checkpoint dựa trên record key/offset hợp lệ và không đổi.

Đối với CSV có quoted newline, cần **parser aware** xác định ranh giới logical records từ đầu hoặc có index chuẩn bị trước. Không lấy `positionOfNextNewline` làm ranh giới chắc chắn.

### Gzip và các định dạng nén

Một file `.csv.gz` thông thường **không splittable theo byte-range đơn giản**: offset byte của object nén không tương ứng offset record sau giải nén. Có thể:

- Nén từng object nhỏ độc lập ở upstream.
- Tạo block index/splittable codec được hỗ trợ và kiểm chứng.
- Dùng Parquet/ORC/columnar với row groups có metadata, nếu pipeline và reader phù hợp.
- Xử lý nguyên file nén trong một partition rồi tăng số files.

Không tự dùng Range GET giữa gzip stream và hy vọng `GZIPInputStream` có thể khởi tạo từ bất kỳ offset nào.

## 10. Remote partitioning hay remote chunking khi nguồn là object storage?

Hai kiến trúc thường bị nhầm vì đều có manager và remote worker.

| Tiêu chí | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Ai đọc object? | **Worker** thường đọc object/range của partition | **Manager** thường đọc input/chia chunks |
| Request gửi qua broker | Worker step execution / partition context | Chunk items |
| Worker quản lý | Reader + processor + writer trong worker step | Processor/writer trên chunk request |
| Dữ liệu đi qua broker | Chủ yếu **metadata công việc**, không phải toàn bộ records | Có thể chứa lượng lớn **item payload** |
| Phù hợp object storage lớn | Thường tự nhiên với file/object độc lập | Có thể tạo manager/network bottleneck |
| Checkpoint | Worker `StepExecution`/`ItemStream` theo partition | Manager + request/reply/chunk state theo thiết kế |
| Scale | Bằng partition plan, worker count và capacity | Bằng chunk flow, broker throughput và worker consumers |

**Kết luận có điều kiện:** Khi object storage giữ nhiều file lớn và worker có thể tự truy cập chúng, remote partitioning thường giảm nhu cầu chuyển **toàn bộ item payload qua broker**. Remote chunking vẫn hữu ích nếu cần **một reader tập trung** hoặc quy trình nghiệp vụ đã được thiết kế theo chunk messages.

Không khẳng định remote chunking là “sai” với object storage; hãy tính throughput của manager reader, kích thước message, broker quotas, serialization overhead, consumer concurrency, restart semantics và chi phí egress trước khi chọn.

### Manager không nên đọc bytes chỉ để phát tên object

Một partition request thường chỉ cần:

~~~text
jobInstanceId
workerStepExecutionId
partitionName
manifestId
bucket / object key / versionId / checksum
~~~

Đây là **envelope logic**, không phải một lớp message cố định của Spring Batch Integration. Remote worker lấy metadata thực từ `StepExecution`/`ExecutionContext` theo adapter đang dùng; không tự dựng một `StepExecution` mới từ string tùy ý hoặc gọi `JobLauncher` cho mỗi object.

## 11. Từ partitioner đến worker step

Ở Spring Batch 5.x, một cấu hình manager local để minh họa partition mechanics có thể có dạng:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;

@Bean
Step objectManagerStep(
        JobRepository jobRepository,
        Partitioner objectManifestPartitioner,
        Step objectWorkerStep,
        TaskExecutor partitionExecutor) {

    return new StepBuilder("objectManagerStep", jobRepository)
            .partitioner(
                    objectWorkerStep.getName(),
                    objectManifestPartitioner)
            .step(objectWorkerStep)
            .gridSize(8)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

Đây là **local partitioning sample** để minh họa `Partitioner` và `gridSize`, **không phải cấu hình remote**. Khi chuyển sang remote partitioning, manager/worker cần Spring Batch Integration, message channels, request/reply transports và `PartitionHandler` tương ứng theo phiên bản. Worker phải có bean worker step và shared JobRepository phù hợp.

### Worker step có reader theo StepScope

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step objectWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> ordersReader,
        ItemProcessor<OrderInput, OutputOrder> processor,
        ItemWriter<OutputOrder> writer) {

    return new StepBuilder("objectWorkerStep", jobRepository)
            .<OrderInput, OutputOrder>chunk(200, transactionManager)
            .reader(ordersReader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

`OrderInput`, `OutputOrder`, `ordersReader`, processor và writer do ứng dụng định nghĩa. Khi nhiều worker JVM chạy đồng thời:

- Mỗi worker `StepExecution` nhận **ExecutionContext riêng**.
- `@StepScope` hỗ trợ late binding context và target state theo step execution.
- Không dùng singleton `currentObjectKey` mutable để nhiều workers thay đổi.
- Nếu còn **multi-threaded chunks trong một worker StepExecution**, `@StepScope` **không tự bảo đảm** reader stateful thread-safe.
- Worker step không tự giữ `JobExecution` mới cho từng object; manager điều phối executions theo cơ chế partitioning.

## 12. Output object storage: không coi PUT là commit của toàn job

Giả sử workers cần tạo 8 file kết quả rồi publish bộ dữ liệu. Một lỗi phổ biến là tất cả workers append vào `output.csv` hoặc mỗi worker overwrite cùng object key:

~~~text
Worker A -> PUT reports/orders.csv
Worker B -> PUT reports/orders.csv

Kết quả có thể là version cuối ghi đè kết quả trước;
không phải thao tác append transaction chung.
~~~

### Thiết kế output theo partition

~~~text
staging/
  jobInstance-100/
    partition-0000/
      attempt-501-701/part.csv
    partition-0001/
      attempt-501-702/part.csv

published/
  orders/2026-11-25/manifest.json
~~~

**Attempt key** giúp các workers không ghi đè nhau. Nó **khác business operation key**: hai attempts có thể tạo hai staging objects khác nhau cho **cùng dữ liệu logic**, nhưng chỉ một kết quả **được công nhận/publish** sau khi đối soát.

### Quy trình output an toàn

1. Mỗi worker ghi vào file/object **riêng** cho partition/attempt, không đụng object của worker khác.
2. Đóng writer, hoàn tất upload/multipart upload; kiểm tra size/checksum/record count.
3. Lưu **partition output descriptor** gồm partition name, input manifest ID, output key/version, checksum, status và execution/attempt.
4. Đối soát mọi logical partitions: đúng đầu vào, đúng counts, không duplicate business operation; giải quyết những worker `FAILED/UNKNOWN`.
5. Chọn đúng một output descriptor **được chấp nhận** cho mỗi logical partition theo policy.
6. Publish **một manifest/pointer** chỉ đến các objects đã được xác thực, kèm schema/sourceVersion.
7. Downstream đọc theo **published manifest**, không quét mọi objects trong staging prefix.

~~~mermaid
flowchart TB
    A["Worker A / attempt 1"] --> O1[("Staged object A1")]
    A2["Worker A / attempt 2"] --> O2[("Staged object A2")]
    B["Worker B"] --> O3[("Staged object B")]
    O1 --> R["Reconciliation / select winner"]
    O2 --> R
    O3 --> R
    R --> G{"Input/object/outcome checks pass?"}
    G -- "Không" --> H["Fail publish; investigate"]
    G -- "Có" --> M["Publish immutable manifest"]
    M --> D["Downstream readers"]
~~~

### Không có atomic rename đa object

Một số filesystem cho atomic rename trong cùng volume, nhưng object storage thường **không** có thao tác rename atomic của **cả một tập objects**. `copy + delete` không thay thế transaction publish.

Một manifest/pointer duy nhất được cập nhật theo **conditional write/optimistic version check** có thể là ranh giới công bố logic, tùy provider/contract. Nếu dùng database làm publish registry, có thể update một row `PUBLISHED` atomically để trỏ tới immutable output manifest; những bytes của outputs vẫn nằm ngoài transaction DB và phải được xác minh trước.

### Multipart upload, version và checksum

- Object multipart upload cần **complete** thành công trước khi downstream đọc như một artifact hoàn chỉnh.
- Multipart ETag **không được coi mặc định là MD5 nội dung**.
- Nếu PUT/complete thành công nhưng worker mất response, hãy **HEAD/GET và xác minh metadata/version/checksum** trước khi upload lại.
- Cleanup các multipart uploads bị bỏ dở qua policy/điều phối thích hợp.
- Với một publish key có thể bị race giữa hai managers, dùng **conditional create/update** khi dịch vụ hỗ trợ (ví dụ preconditions `If-None-Match`/version-generation match), không “last writer wins”.
- Các precondition và atomicity cụ thể phải được xác minh theo API và provider/version.

## 13. Writer và external side effects: cần idempotency riêng

Object storage PUT là **external side effect** đối với transaction chunk của Spring Batch. Một writer upload file xong rồi `JobRepository` chưa lưu checkpoint có thể dẫn tới retry và upload lại.

~~~text
Worker:
  upload object O thành công
  broker/repository reply bị mất
  StepExecution bị retry/restart
  upload lại cùng work unit
~~~

Nếu object key gắn với attempt, có thể tồn tại nhiều **staging objects** — điều này **không tự là dữ liệu xuất bản trùng** khi publish manifest chọn đúng kết quả. Nếu key là output cuối cùng và overwrite không kiểm soát, kết quả có thể bị thay đổi âm thầm.

### Ba mức identity cần giữ

| Identity | Ví dụ | Công dụng |
| --- | --- | --- |
| `JobInstance` + `manifestId` | `ordersImport/2026-11-25/v1` | Một logical input run |
| `partitionKey` | `object-0007` | Một work unit logic, ổn định xuyên restart |
| **Business operation key** | `(tenantId, operationId)` | Một nghiệp vụ chỉ áp dụng tác dụng hợp lệ một lần |

`StepExecutionId` và attempt ID hữu ích cho audit/staging nhưng có thể đổi sau restart. **Không** dùng nó làm business operation identity nếu retry cùng giao dịch có thể tạo side effect kép.

### Nếu worker ghi database

Sử dụng unique constraint theo business operation key và transaction. Khi replay cùng key:

- Payload/semantics giống nhau → idempotent no-op hoặc trả kết quả đã có.
- Payload khác nhau → conflict, quarantine/reconciliation.
- Operation chưa commit → retry an toàn trong transaction mới.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE order_result (
    tenant_id VARCHAR(100) NOT NULL,
    operation_id VARCHAR(160) NOT NULL,
    manifest_id VARCHAR(160) NOT NULL,
    source_key VARCHAR(300) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    amount_minor BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Unique constraint chỉ bảo vệ **business database này**. Nếu writer còn gửi HTTP, Kafka hoặc email ngoài transaction, cần idempotency phía nhận hoặc transactional outbox/durable operation intent và reconciliation.

## 14. Checkpoint và restart khi worker chuyển pod

`FlatFileItemReader` là `ItemStream` có khả năng ghi trạng thái đọc vào `ExecutionContext` theo lifecycle của Spring Batch khi được cấu hình phù hợp. Sau chunk commit, metadata checkpoint giúp restart tại vị trí gần đúng đã xác nhận.

~~~text
partitionName = object-0007
object        = bucket/orders/part-0007.csv
versionId     = immutable-version-123

JobExecution #501 / StepExecution #701:
  chunk 1..10 COMMIT
  chunk 11 crash trước commit

JobExecution #502 / StepExecution #743 (restart):
  tải lại đúng object version
  mở reader theo saved ExecutionContext
  tiếp tục/replay phần chưa được commit
~~~

### Những điều phải bất biến

1. `manifestId` không đổi cho cùng JobInstance/restart.
2. `partitionName` ánh xạ đến **cùng object/range/format**.
3. Reader có `name`/checkpoint key ổn định, không dùng tên dựa trên pod random UUID.
4. Source bytes và parse schema không đổi.
5. Writer có idempotency cho những item có thể bị replay.
6. Business output và metadata commit boundaries được hiểu rõ.

### Đừng lưu local path làm checkpoint lâu dài

~~~text
JobExecution #501 ở pod A: /tmp/batch-object-123/input.csv
JobExecution #502 ở pod B: không có file đó
~~~

Checkpoint cần gắn với **source identity + vị trí logic**; worker pod mới tải lại object và phục hồi reader. Nếu lưu path để debug, coi nó là thông tin tạm **không thể dùng làm nguồn dữ liệu khôi phục**.

### Nếu object bị xóa hoặc version không còn đọc được

**Fail rõ ràng**, không lặng lẽ đọc “latest version” cùng key. Có thể:

- Khôi phục object version từ retention/backup theo policy.
- Reconstruct **đúng bytes** và kiểm tra checksum, nếu quy trình cho phép.
- Hủy/khóa phiên xử lý rồi tạo **snapshot/version mới và JobInstance mới có chủ đích**.

Không đổi object key hoặc checksum trong `ExecutionContext` của một partition đã có checkpoint chỉ để làm job chạy tiếp.

## 15. Lỗi mạng và kết quả chưa rõ: không phải bad record

Object storage qua network có nhiều lỗi hơn truy cập file local:

| Lỗi/tín hiệu | Nhóm | Hành động ưu tiên |
| --- | --- | --- |
| HTTP 429 / 503 / throttling | Transient nếu provider công bố có thể retry | Backoff + jitter + bounded retries |
| Connect timeout khi tải object | Transient có điều kiện | Retry GET cùng version; kiểm tra deadline |
| GET bị cắt giữa stream | Transient | Tải lại/reposition từ checkpoint/range đã xác minh |
| 403 AccessDenied | Thường cấu hình/quyền | Fail fast, kiểm tra identity/IAM; không skip |
| Object/version missing (404 hoặc code tương ứng) | Input contract bị phá vỡ hoặc object chưa sẵn sàng | Kiểm tra manifest/publish; fail, không tự dùng latest |
| Checksum mismatch | Dữ liệu không khớp manifest | **Fail/quarantine artifact**, không xử lý bytes khác |
| Range 416 | Offset/range không hợp lệ | Kiểm tra plan/version/parser; không tự skip item |
| PUT timeout sau khi gửi | Kết quả upload **không rõ** | HEAD/GET/check checksum, reconcile trước khi PUT lại |
| DB checkpoint commit failure | Metadata không chắc chắn | Đối chiếu business output/JobRepository trước restart |
| Worker mất reply với manager | Worker có thể đã commit | Dedupe/reconciliation, không tạo JobInstance mới mù |

**Không dùng `skip(Exception.class)` để bỏ qua mọi file không đọc được.** Lỗi thiếu quyền hoặc mất mạng không chứng minh tất cả records trong object đều sai. Với lỗi mạng diện rộng, retry vô hạn trên 64 workers có thể gây request storm; cần circuit breaker/backpressure.

### Retry policy theo loại thao tác

- **GET đúng immutable version**: thường có thể retry với cùng key/version sau lỗi transient, nhưng phải giới hạn attempts và kiểm tra checksum/bytes.
- **PUT vào staging key độc lập**: cần xử lý unknown outcome, conditional write hoặc verify object trước khi retry.
- **Publish manifest cuối**: cần atomic conditional update/compare-and-swap theo provider hoặc registry, không last-writer-wins.
- **Commit SQL business**: retry transaction chỉ khi idempotency/atomic write phù hợp.
- **External API**: retry cùng idempotency key và query status khi timeout.

## 16. Cửa sổ lỗi giữa object storage và JobRepository

Object storage không tự tham gia transaction JDBC của Spring Batch. Vì vậy:

~~~mermaid
sequenceDiagram
    participant W as Remote worker
    participant S as Object storage
    participant R as JobRepository
    participant M as Manager
    W->>S: Upload result object
    S-->>W: PUT completed
    W->>R: Store checkpoint/StepExecution status
    W--xM: Reply lost / worker crash
    Note over M: Chưa biết chắc trạng thái worker
    M->>R: Reconcile StepExecution
    M->>S: Verify object version/checksum
    M->>M: Quyết định tiếp tục / retry / publish
~~~

Một số tình huống:

| Điểm crash | Storage | Repository | Khôi phục |
| --- | --- | --- | --- |
| Trước upload | Chưa có object | Chưa xác nhận bước | Retry work unit |
| Trong upload trước complete | Có thể có multipart upload chưa hoàn tất | Chưa hoàn tất | Cleanup/abort khi phù hợp; retry |
| Sau upload commit, trước repository update | Object đã tồn tại | Có thể checkpoint cũ | Replay idempotent, verify và chọn output đúng |
| Repository đánh dấu completed sai trước external write | Không có output thật | Trông như hoàn thành | **Incident**; cần kiểm tra output trước publish |
| Manager mất reply, worker đã hoàn tất | Output có thể đã có | Worker metadata có thể completed | Reconcile, không tạo upload/operation trùng mù |
| Publish marker đã ghi, operator nhận timeout | Downstream có thể đã thấy manifest | Manager chưa biết | Query/verify marker và contract; không tạo bản publish mới vô điều kiện |

**Không có transaction hai pha tự động** giữa object storage và repository chỉ vì code nằm trong một `ItemWriter` hoặc `@Transactional`. Hãy thiết kế **idempotent stage + verify + publish**, và một nguồn sự thật về **kết quả cuối**.

## 17. Bảo mật, quyền truy cập và secret management

Remote workers cần xác thực tới object storage. Dùng credentials tĩnh hardcode trong `ExecutionContext` hoặc log là rủi ro lớn khi mở rộng sang nhiều pods.

### Nguyên tắc

1. **Workload identity** theo nền tảng: IAM role cho workload, service account, managed identity hoặc cơ chế tương đương.
2. Worker chỉ có quyền **read** input bucket/prefix cần thiết; quyền **write** output prefix riêng nếu nghiệp vụ yêu cầu.
3. Manager có thể chỉ cần đọc manifest và gửi partition requests; không nhất thiết cần quyền GET mọi objects.
4. Áp dụng least privilege theo namespace/tenant/environment.
5. Dùng TLS, encryption at rest và khóa quản lý thích hợp (KMS/CMEK nếu quy định).
6. Không đưa access key/secret/session token/presigned URL nhạy cảm vào `ExecutionContext` hoặc logs.
7. Kiểm soát egress/network path, private endpoints, firewall và DNS theo cloud environment.
8. Audit quyền truy cập, hết hạn credential, rotation và điều kiện truy cập versions.

### Presigned URL có phù hợp làm input identity?

Presigned URL có thể hết hạn khi job còn chạy hoặc khi worker restart. Nó là **phương thức truy cập tạm thời**, không phải identity ổn định của object. Nếu dùng presigned URL, phải thiết kế cấp lại URL cho **cùng bucket/key/version** qua một dịch vụ được ủy quyền; không lưu URL hết hạn làm nguồn checkpoint lâu dài.

### Không lộ dữ liệu trong log

Object key có thể chứa tenant/customer ID hoặc thông tin nhạy cảm. Log `partitionName`, `manifestId`, mã lỗi và sanitized key/hash; chỉ lưu thông tin chi tiết hơn vào audit store có quyền truy cập phù hợp. Không log raw CSV rows, thông tin thanh toán hoặc nội dung object khi retry.

## 18. Tối ưu throughput và chi phí

Object storage thường scale được nhiều requests nhưng **bandwidth, latency, request quotas, network path và worker capacity** vẫn hữu hạn.

### Tính sơ bộ năng lực

Ví dụ 800 objects, mỗi object trung bình 1,5 GB:

~~~text
Tổng input bytes ≈ 1.200 GB (đơn vị thập phân minh họa)

32 workers, mỗi worker download ổn định 25 MB/s:
  tổng lý thuyết ≈ 800 MB/s

Thời gian truyền lý thuyết:
  1.200.000 MB / 800 MB/s ≈ 1.500 s
  ≈ 25 phút
~~~

Đây **không** phải thời gian job thực tế. Nó bỏ qua CSV parsing, CPU, bandwidth chia sẻ, contention, kiểm tra checksum, disk writes, request setup, retry, DB writes, kích cỡ object lệch và throttling. Nếu 32 workers cạnh tranh một network gateway hoặc một database, tổng throughput thực có thể thấp hơn nhiều.

### Những bottleneck thường gặp

| Bottleneck | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Bandwidth/network egress | Worker CPU thấp, download latency cao | Đặt worker gần bucket/region, tăng capacity phù hợp, đo throughput |
| Quá nhiều objects nhỏ | Request overhead, nhiều StepExecutions | Group objects, batch manifests, giảm metadata overhead |
| Object rất lớn không cân bằng | Một worker chạy lâu hơn các worker khác | Chia upstream objects, format-aware ranges |
| Pod ephemeral disk thiếu | `No space left on device` | Giới hạn staging, cleanup, streaming, tăng disk khi hợp lý |
| CPU parse/giải nén | CPU cao, network chưa bão hòa | Tối ưu parser, compression/format, thêm worker có kiểm soát |
| Database writer nghẽn | Pool wait/lock waits/rollback tăng | Batch writes, indices, partitioning theo key, rate limit |
| Object storage throttling | HTTP 429/503, retries tăng | Bounded exponential backoff + jitter, giảm concurrency |
| JobRepository nóng | StepExecution updates chậm | Giảm quá nhiều tiny partitions, tuning pool/metadata |
| Broker request/reply chậm | Remote lag, worker idle | Đo middleware capacity/correlation, tránh gửi payload quá lớn |

### Đừng đặt mọi concurrency knobs ở mức tối đa

~~~text
active manager JobExecutions
    × active partitions per job
    × chunk threads per worker
    × concurrent GET/PUT per worker
~~~

Đây là **nguồn khuếch đại tải**, không phải công thức đếm chính xác số connections. Cần đặt giới hạn ở launcher, partition handler, worker consumer, HTTP SDK connection pool và DB connection pool theo benchmark.

### Đặt worker cùng vùng dữ liệu

Khi dữ liệu nằm ở region khác worker, latency và egress cost có thể tăng; việc truyền hàng TB qua region/cloud khác thường ảnh hưởng cả chi phí lẫn deadline. Xem xét:

- Đặt worker cùng region/network locality với storage.
- Sử dụng private endpoints/peering khi hợp lý.
- Tiền xử lý/chia shard ngay tại nơi dữ liệu được tạo.
- Compression nếu CPU giải nén và băng thông thực sự có lợi.
- Tối ưu số lần tải cùng object khi retry bằng cache/staging có kiểm chứng checksum và lifecycle.

Không cache “latest object” theo key mà bỏ qua version/checksum; cache có thể biến thành nguồn đọc dữ liệu cũ/sai.

## 19. Observability: nhìn được từng object và partition

Log nên nối được:

~~~text
jobName
jobInstanceId / jobExecutionId
manifestId
partitionName
workerStepExecutionId
workerPodId
bucket + sanitizedObjectKey + versionId
chunkCommitCount / readCount / writeCount / rollbackCount
objectDownloadBytes / time / retryCount
outputObjectKey / checksum / publishStatus
~~~

### Ví dụ structured log

~~~json
{
  "event": "object_download_verified",
  "jobExecutionId": 502,
  "stepExecutionId": 719,
  "partitionName": "object-0007",
  "manifestId": "orders-2026-11-25-v1",
  "sourceBytes": 734003200,
  "elapsedMs": 42000,
  "checksumVerified": true,
  "workerId": "orders-worker-b"
}
~~~

Đây là **log contract minh họa**. MDC/structured logging chỉ tự có những fields ứng dụng hoặc instrumentation đã cung cấp. Remote worker phải tái tạo `partitionName` từ `StepExecutionContext`; `ThreadLocal/MDC` của manager không tự đi qua broker.

### Metric nào quan trọng?

| Metric | Mục đích |
| --- | --- |
| `object_get_requests_total`, retries | Đo tần suất network operations |
| `object_download_bytes_total` | Throughput thực |
| `object_download_duration_seconds` | Phát hiện stragglers/latency |
| `object_checksum_mismatch_total` | Integrity incidents |
| `staging_disk_bytes` | Ngăn disk exhaustion |
| `active_partition_workers` | Concurrency thực |
| `partition_duration_seconds` | Data skew và bottleneck |
| `chunk_rollback_total` | Lỗi transaction/retry |
| `output_publish_conflict_total` | Hai attempts/managers cùng publish |
| `staged_objects_pending_cleanup` | Chi phí/rác sau crash |
| `reconciliation_mismatch_total` | Tính đúng của dữ liệu cuối |

Đừng gắn mọi full object key, `StepExecutionId` hay source row ID làm label time series dài hạn: cardinality có thể rất lớn. Dùng structured logs/audit để tra cứu từng object; metrics aggregate theo job, storage region, status, size bucket và error class.

## 20. Kiểm thử object storage và remote worker

Unit test riêng parser không đủ. Cần xác minh **versioning, SDK, transaction, restart và remote deployment**.

### 20.1. Test manifest và partitioner

Kiểm tra:

1. Hai objects có partition keys khác nhau tạo hai contexts đúng.
2. Partition key trùng làm fail rõ, không ghi đè silent.
3. Manifest cố định tạo **cùng map** qua hai lần gọi/restart.
4. Bucket/key/version/checksum và sourceVersion được bind đúng.
5. Manifest thay đổi trong lúc job chạy bị từ chối thay vì “cập nhật” context cũ.
6. Số objects quá lớn có grouping/limits đã benchmark, không tạo StepExecutions vô hạn.

Test minh họa:

~~~java
@Test
void partitionerTruyenDungObjectVersion() {
    ObjectRef ref = new ObjectRef(
            "object-0007",
            "orders-input",
            "snapshots/2026-11-25/part-0007.csv",
            "version-abc",
            "0123456789abcdef",
            4096L);

    ObjectManifestPartitioner partitioner =
            new ObjectManifestPartitioner(List.of(ref));

    Map<String, ExecutionContext> parts =
            partitioner.partition(8);

    assertEquals(1, parts.size());
    assertEquals("version-abc",
            parts.get("object-0007").getString("versionId"));
    assertEquals("orders-input",
            parts.get("object-0007").getString("bucket"));
}
~~~

Test cần JUnit 5, imports `List/Map/ExecutionContext`; checksum trong ví dụ không phải SHA-256 hợp lệ nên **chỉ test truyền metadata**, không gọi downloader xác thực checksum.

### 20.2. Integration test với object store tương thích

Có thể dùng **LocalStack/MinIO** hoặc test bucket riêng để kiểm tra SDK wiring. Nhưng emulator **không nhất thiết mô phỏng chính xác** versioning, IAM, conditional writes, consistency và throttling của cloud production.

Một test có ích:

1. Upload object CSV mẫu và chốt đúng version/generation.
2. Tạo checksum SHA-256 từ bytes nguồn.
3. Dùng stager stage đúng version và assert bytes/checksum.
4. Overwrite key bằng bytes khác, assert worker vẫn đọc **version đã chốt**, hoặc fail rõ nếu version không truy cập được.
5. Cố đưa checksum sai, assert worker fail **trước khi ghi business output**.
6. Xóa version được reference, assert không fallback sang latest.
7. Mô phỏng object stream bị ngắt/retry có giới hạn.
8. Verify cleanup các temporary files khi step kết thúc; chạy một test kill pod/process để kiểm tra cleanup ngoài listener.

### 20.3. Test không có shared filesystem

Chạy manager và worker ở **hai containers/nodes** khác nhau. Manager chỉ có manifest và không có local CSV. Worker vẫn tải/read được input nhờ object store credentials/SDK.

Không coi một integration test chạy manager/worker trong **cùng JVM** là bằng chứng đủ cho remote file access. Nó có thể vô tình dùng path được mount chung trên máy dev.

### 20.4. Test restart ở pod khác

~~~text
Worker pod A:
  tải object version v1
  commit 4 chunks
  crash trong chunk thứ 5

Worker pod B (restart cùng JobInstance):
  tải lại đúng version v1
  phục hồi reader checkpoint
  hoàn tất các items còn lại
~~~

Kỳ vọng:

- Không yêu cầu `/tmp/...` từ pod A.
- Không đọc “latest version” nếu source key bị overwrite.
- Không bỏ sót/nhân đôi business operation sau replay.
- StepExecution mới có ID khác nhưng cùng logical partition name.
- `JobRepository` và output manifest xác nhận đúng thành công.

### 20.5. Ma trận fault injection

| Lỗi giả lập | Kỳ vọng |
| --- | --- |
| Object chưa có khi manager tạo manifest | Không seal manifest lỗi |
| Object bị xóa sau manifest | Worker fail với missing version; không đổi input mù |
| Object key bị overwrite | Đọc đúng pinned version/generation hoặc fail |
| Checksum mismatch | Không xử lý sai bytes, có alert |
| GET timeout, sau đó hồi phục | Retry cùng object version, đúng checkpoint |
| GET fail giữa file | Tải lại/resume an toàn, không bỏ record |
| Một CSV record chứa quoted newline | Partition theo byte không cắt sai logical record |
| gzip không hỗ trợ random split | Không Range GET tùy ý rồi parse lỗi |
| Worker pod hết ephemeral disk | Fail/backpressure, không tạo output thiếu |
| Hai workers cùng logical partition | Claim/metadata và business idempotency chống duplicate |
| Worker đã upload, reply mất | Reconcile staged object rồi xử lý duplicate attempt |
| PUT timeout sau server commit | HEAD/GET verify trước retry với key mới |
| Hai manager cùng publish manifest | Conditional publish chặn last-writer-wins |
| Multipart upload bị bỏ dở | Cleanup policy phát hiện/giải quyết |
| JobRepository commit fail sau output | Restart không tạo effect nghiệp vụ kép |
| 403 AccessDenied/expired credentials | Fail/alert, không skip cả object |
| Region egress hoặc request throttle | Metrics thể hiện bottleneck, bounded retry/backoff |
| Manifest được sửa giữa restart | Detect mismatch, không lặng lẽ đổi partition mapping |

### 20.6. Integration test Spring Batch

Với `spring-batch-test`, có thể:

1. Khởi tạo manifest fixture bất biến, object store test và business DB.
2. Launch job với identifying `manifestId` cụ thể, xác minh manager tạo worker StepExecutions/context.
3. Gây lỗi có chủ đích sau vài chunks commit, xác minh status/checkpoint.
4. Khôi phục resource và restart **cùng JobInstance**, không tạo identifying run ID mới.
5. Đọc business output theo unique operation key, so với manifest/source record keys và checksum/amount mong đợi.
6. Nếu job tạo output objects, assert **chỉ một published manifest** trỏ tới bộ staged objects hợp lệ.
7. Kiểm tra per-partition counters và logs, nhưng không coi `writeCount` là số row mới khi writer idempotent.

## 21. Runbook xử lý sự cố với remote object worker

1. **Chốt identity:** `JobInstance`, identifying `manifestId`, partitionName, bucket/key/version/checksum, worker `StepExecutionId`.
2. **Xem metadata:** Worker `COMPLETED/FAILED/STARTED`, checkpoint, rollback/commit counts và manager reply status.
3. **Xác minh object:** Version/generation có tồn tại, kích thước/checksum/schema đúng và worker được quyền đọc?
4. **Kiểm tra runtime:** Pod có đủ disk, heap, bandwidth, DNS, TLS và SDK connection pool không?
5. **Đọc error class:** 403, 404, 429, 503, timeout, checksum mismatch, 416 range hay lỗi parse dữ liệu?
6. **Xác định vị trí commit:** Input GET, database writer, output PUT/multipart complete, JobRepository checkpoint hay publish manifest?
7. **Tách lỗi hạ tầng khỏi bad record:** Không skip dữ liệu hợp lệ chỉ vì object store outage.
8. **Kiểm tra worker cũ:** Có process vẫn chạy dù manager timeout? Có object staging/HTTP side effects chưa xác nhận?
9. **Khôi phục nguồn:** Chỉ dùng **pinned object version**; nếu không còn, thực hiện restore/new snapshot theo policy.
10. **Restart đúng cách:** Giữ JobInstance/manifest/partition mapping; xác minh duplicate effects trước khi replay.
11. **Đối soát:** Tập source records vs output unique operations/quarantine, record counts, checksums và staged outputs được chọn.
12. **Publish có kiểm soát:** Chỉ ghi manifest/pointer cuối khi mọi invariants đạt và không còn `UNKNOWN` quan trọng.
13. **Dọn dẹp sau sự cố:** Ephemeral staged files, unfinished multipart uploads, superseded attempt outputs theo retention/audit.
14. **Cập nhật vận hành:** Benchmark concurrency, retry budgets, IAM/credentials, alert và fault-injection case vừa gây lỗi.

### Không nên làm

- Đổi `versionId` thành latest mà không đổi `JobInstance`/manifest.
- Tăng `skipLimit` để bỏ qua cả một object do lỗi 403 hoặc network.
- Gửi local path từ manager cho remote pod và coi đó là durable address.
- Ghi nhiều partitions vào cùng output key bằng PUT overwrite.
- Xóa staging objects của attempt cũ trước khi reconciliation hoàn tất.
- Publish bằng cách downstream LIST tất cả objects trong staging prefix.
- Lấy S3 ETag làm SHA-256 hoặc checksum universal cho mọi multipart object.
- Chạy lại job bằng identifying timestamp mới chỉ vì mất reply từ remote worker.

## 22. Bài tập tình huống: 600 file trên 24 remote workers

Một tổ chức nhập **600 CSV objects** mỗi đêm từ S3, mỗi file 200 MB–3 GB. Job dùng Spring Batch remote partitioning với 24 worker pods. Manager tạo `Partitioner` bằng cách gọi `ListObjects` rồi đánh số `partition-0 ... partition-599`. Các worker đọc bằng local path `/mnt/import/part-x.csv` do manager gửi. Tất cả workers upload kết quả vào cùng key `reports/daily.csv`.

Trong lần chạy đầu:

- 480 partitions hoàn tất.
- Một worker bị kill sau khi upload kết quả nhưng trước khi manager nhận reply.
- Một số objects nguồn bị producer overwrite trong lúc job chạy.
- Lần restart manager LIST lại và thứ tự objects thay đổi; `partition-127` đọc object khác.
- Hai workers ghi đè `reports/daily.csv`, khiến báo cáo mất nhiều dòng.
- Operator đề xuất dùng `skip(Exception.class)` cho các file không đọc được để job `COMPLETED`.

**Câu hỏi:**

1. Vì sao một local path do manager gửi không phải địa chỉ hợp lệ cho mọi remote workers?
2. Vì sao LIST lại lúc restart có thể phá checkpoint dù `partitionName` không đổi?
3. Phải ghi những trường gì vào sealed input manifest?
4. Cần dùng `versionId`/`generation` và checksum như thế nào để tránh đọc input bị overwrite?
5. Nếu CSV có quoted multiline records, có được chia byte-range tùy ý không?
6. Sau khi worker đã upload nhưng mất reply, phải kiểm tra những gì trước khi retry?
7. Vì sao nhiều PUT vào một `daily.csv` không tạo một báo cáo ghép đúng?
8. Thiết kế output staging/publish nào bảo vệ 600 partitions và giúp downstream chỉ thấy kết quả đầy đủ?
9. Khi restart, cần giữ metadata nào ổn định, metadata nào có thể đổi?
10. Cần metrics, test và runbook gì trước khi tăng lên 48 workers?

**Định hướng trả lời:** Manager phải tạo sealed manifest gồm logical partition key, bucket/key, object version/generation, size, checksum và schema/sourceVersion. Remote worker dùng SDK truy cập object đã pin, stage hoặc stream theo reader có checkpoint; không giả định shared filesystem. Partition mapping phải bất biến khi restart. CSV quoted multiline không thể split theo newline byte tùy ý. Worker ghi từng attempt/partition vào object key riêng; reconciler xác minh checksums, số record và chọn đúng output cho mỗi partition, rồi publish **một manifest/pointer cuối**. Sau upload/reply loss phải verify object và business operations, không ghi lại mù. Lỗi object store/hạ tầng không phải item lỗi nên phải retry/fail/reconcile. Benchmark network/disk/DB/metadata và kiểm thử worker crash, overwrite, mismatch, duplicate requests.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và các hình thức scale.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking và remote partitioning.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, `ExecutionContext` và checkpoint.
- [Spring Batch Reference — Flat File Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): `FlatFileItemReader` và cách đọc record.
- [Spring Batch Reference — JobRepository Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `StepExecution`, counters và metadata phục hồi.
- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/late-binding.html): late binding metadata trong worker `@StepScope`.
- [AWS SDK for Java v2 — Amazon S3 GetObject](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-objects.html): tải objects bằng SDK và APIs.
- [Amazon S3 — Strong Consistency](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel): read-after-write và LIST consistency trong S3.
- [Amazon S3 — Object Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html): `versionId` và truy cập lịch sử object.
- [Amazon S3 — Checking Object Integrity](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html): checksum, multipart và ETag caveats.
- [Amazon S3 — Conditional Requests](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-requests.html): điều kiện chống overwrite/race khi PUT.
- [Google Cloud Storage — Object Versioning](https://cloud.google.com/storage/docs/object-versioning): generation/version semantics.
- [Azure Blob Storage — Versioning](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview): object versions và snapshot.

> **Ghi nhớ:** **Object storage chia sẻ bytes; Spring Batch chia sẻ metadata và tiến độ; business idempotency bảo vệ tác dụng cuối cùng.** Muốn remote worker chạy an toàn, hãy dùng **sealed manifest, pinned object version/checksum, partition mapping bất biến, reader có checkpoint**, giới hạn concurrency theo network/DB/disk và **output staging + publish manifest sau đối soát**. Không thay đổi input theo “latest”, không dùng đường dẫn local của manager và không coi một lần PUT hoặc một reply thành công là transaction atomic của toàn job.
