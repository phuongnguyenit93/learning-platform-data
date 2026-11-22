# Thực hành xử lý tệp tải lên bằng hàm Java trên Cloud Run functions và Eventarc

> **Chương:** Cloud Run functions và Eventarc  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

**Bài toán:** người dùng đưa một tệp **.txt** vào Cloud Storage. Hệ thống cần tự động đọc tệp, đếm số dòng/số byte, tính SHA-256 và ghi một báo cáo JSON vào bucket khác mà không cần máy chủ chạy liên tục. Ta thực hiện bằng **Cloud Run functions (Java 21)**, **Eventarc Standard** và **Cloud Storage**. Bài học giới hạn tệp đầu vào tối đa **1 MiB** để ví dụ đọc nội dung trong bộ nhớ an toàn; sản xuất với file lớn nên xử lý streaming hoặc dùng kiến trúc batch.

Hai yêu cầu không thể bỏ qua: **Eventarc có thể giao cùng sự kiện nhiều lần** và **Cloud Storage object có thể bị ghi đè**. Hàm vì vậy dùng **bucket + object name + generation** làm định danh bản tệp, và tạo file kết quả với **precondition không tồn tại** để tránh ghi trùng.

## Mục tiêu học tập

Hoàn thành bài này, người học có thể:

1. Phân biệt **Cloud Run functions**, **Functions Framework**, **CloudEvents**, **Eventarc trigger** và **Cloud Storage object finalized**.
2. Viết Java class triển khai **CloudEventsFunction** và phân tích metadata object.
3. Đọc **đúng generation** của tệp từ Cloud Storage, kiểm tra loại/kích thước và xử lý văn bản UTF-8.
4. Ghi báo cáo JSON với tên ổn định và precondition chống trùng lặp.
5. Cấu hình **build identity**, **runtime service account**, **trigger identity** và **Cloud Storage service agent** theo nguyên tắc ít quyền nhất.
6. Deploy hàm, tạo trigger, tải tệp kiểm thử, đọc log/output và xử lý các lỗi thường gặp.
7. Giải thích retry, idempotency, nguy cơ vòng lặp trigger, dữ liệu bị ghi đè, bảo mật tệp và chi phí.
8. Dọn tài nguyên lab đúng phạm vi, rồi mở rộng sang xử lý ảnh/PDF hoặc hàng đợi khi phù hợp.

## 1. Kiến trúc và thứ tự xử lý

~~~mermaid
sequenceDiagram
    participant U as Uploader
    participant IN as Cloud Storage input bucket
    participant EA as Eventarc Standard
    participant FN as Cloud Run function Java
    participant OUT as Cloud Storage output bucket
    U->>IN: Upload incoming/hello.txt
    IN-->>EA: Object finalized event
    EA->>FN: HTTP CloudEvent đã xác thực
    FN->>FN: Kiểm tra bucket/name/generation
    FN->>IN: Read object@generation
    IN-->>FN: Nội dung UTF-8
    FN->>FN: Đếm dòng, byte, SHA-256
    FN->>OUT: Create summary JSON, doesNotExist
    OUT-->>FN: Created hoặc already exists
    FN-->>EA: 2xx thành công
~~~

**Tách hai bucket** là biện pháp đơn giản để tránh vòng lặp: một object **output** được tạo sau xử lý không nằm trong **input bucket** mà trigger theo dõi. Nếu dùng cùng bucket, cần filter/prefix và guard trong code để chặn trigger tự gọi lại; chỉ filter ở code vẫn tạo events và phí.

| Thành phần | Tên lab minh họa | Vai trò |
|---|---|---|
| Project | YOUR_PROJECT_ID | Chứa toàn bộ tài nguyên lab |
| Region | asia-southeast1 | Nơi đặt function, bucket và trigger |
| Input bucket | INPUT_BUCKET_UNIQUE | Chứa **incoming/*.txt** |
| Output bucket | OUTPUT_BUCKET_UNIQUE | Chứa **summaries/*.json** |
| Cloud Run function | file-upload-java-lab | Code xử lý event |
| Eventarc trigger | file-upload-finalized-lab | Lọc finalized events từ input bucket |
| Runtime service account | fileproc-runtime | Đọc input, tạo output |
| Trigger service account | fileproc-trigger | Nhận event và gọi function |
| Image repository | cloud-run-source-deploy | Image được build từ source, có thể dùng chung |

Các tên bucket phải **duy nhất toàn cục**. Trong ví dụ, người học phải thay placeholder bằng tên thật và ghi lại chúng trước khi chạy lệnh thay đổi.

### 1.1. Eventarc gửi gì cho hàm?

Eventarc gửi một **CloudEvent** tới Cloud Run qua HTTP. Với Cloud Storage direct events:

- **type:** google.cloud.storage.object.v1.finalized.
- **id:** mã sự kiện; có thể dùng cho tracing/dedup.
- **source:** nguồn phát event.
- **data.bucket:** tên bucket.
- **data.name:** tên object, không phải đường dẫn file trong VM.
- **data.generation:** phiên bản nội dung của object.
- **data.metageneration:** phiên bản metadata, **khác** generation.

**Finalized** xảy ra khi object mới được tạo hoặc bị overwrite khiến một generation mới được tạo. Nó **không** đồng nghĩa “file đã quét virus, đúng MIME, đã được duyệt hoặc không còn bị sửa”. Hệ thống vẫn phải xác minh content trước khi xử lý.

### 1.2. Cloud Run function không phải Cloud Functions thế hệ cũ

Cách triển khai chính của bài là:

~~~bash
gcloud run deploy SERVICE_NAME \
  --source . \
  --function functions.ProcessUpload \
  --base-image java21 \
  --region REGION
~~~

Sau đó mới tạo **Eventarc trigger** bằng **gcloud eventarc triggers create**. Không dùng cú pháp thế hệ cũ **gcloud functions deploy --trigger-resource/--trigger-event** để minh họa sản phẩm Cloud Run functions hiện hành. **--function** nhận tên class Java bao gồm package.

Hàm vẫn được Cloud Run quản lý như một service có URL và revisions. **Không cấp public unauthenticated access** chỉ để Eventarc gọi được; cấu hình **trigger identity** có quyền Cloud Run Invoker là giải pháp đúng.

## 2. Quyết định an toàn trước khi chạy

**Các lệnh triển khai có thể làm phát sinh phí** Cloud Build, Artifact Registry, Cloud Run, Eventarc/Pub/Sub, Cloud Storage, logs và mạng. Chỉ chạy trong project lab được cấp quyền và có ngân sách, không dùng bucket production của người khác.

| Rủi ro | Guardrail của lab |
|---|---|
| Tệp quá lớn | Tối đa **1 MiB**, từ chối tệp lớn hơn |
| Tệp không phải văn bản | Chỉ tên **.txt**, MIME text/plain nếu có; UTF-8 hợp lệ |
| Xử lý trùng | Kết quả theo **bucket/name/generation**, create-only |
| Ghi đè file đầu vào | Không overwrite cùng object key khi lab; xem versioning ở mục 9 |
| Vòng lặp trigger | Input và output **khác bucket** |
| Dữ liệu nhạy cảm | Không log nội dung tệp; chỉ ghi hash, kích thước, số dòng |
| Quyền quá rộng | Runtime chỉ đọc input, tạo object output; trigger chỉ invoke/receive |
| Bị retry liên tục | Phân biệt lỗi vĩnh viễn/tạm thời, theo dõi retry và DLQ |
| Tự ý mở public | Giữ service authenticated, Eventarc dùng service account |

**Phạm vi ví dụ:** tính SHA-256, số byte và số dòng; **không** xử lý PII, virus scan, giải nén archive, PDF hoặc chạy executable từ tệp tải lên. Nếu áp dụng vào hệ thống nhận file từ Internet, cần bổ sung kiểm tra nội dung thực, hạn mức, rate limiting, antivirus nếu có yêu cầu, và chính sách retention/quyền truy cập.

## 3. Chuẩn bị project, API, CLI và IAM

### 3.1. Kiểm tra context (chỉ đọc)

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
FUNCTION="file-upload-java-lab"
TRIGGER="file-upload-finalized-lab"
INPUT_BUCKET="INPUT_BUCKET_UNIQUE"
OUTPUT_BUCKET="OUTPUT_BUCKET_UNIQUE"

gcloud auth list
gcloud config list project
gcloud projects describe "$PROJECT_ID"

# Xem API đã bật.
gcloud services list --enabled --project="$PROJECT_ID"

# Xem có tài nguyên trùng tên không.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud eventarc triggers list --project="$PROJECT_ID" --location="$REGION"
gcloud storage buckets list --project="$PROJECT_ID"
~~~

Không chỉ dựa vào **gcloud config get project** khi thao tác nhiều môi trường: mọi lệnh thay đổi nên truyền **--project** hoặc giới hạn project rõ ràng. Bucket là tên duy nhất toàn cục, **không tạo bucket bằng tên của người khác**.

### 3.2. API và danh tính cần có

Các API chính gồm **run.googleapis.com**, **cloudbuild.googleapis.com**, **artifactregistry.googleapis.com**, **eventarc.googleapis.com**, **eventarcpublishing.googleapis.com**, **pubsub.googleapis.com**, **storage.googleapis.com** và các dịch vụ hỗ trợ logging/IAM. Kiểm tra organization policy/quota trước khi bật.

~~~bash
# THAY ĐỔI cấu hình project — chỉ khi được phép.
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  eventarc.googleapis.com \
  eventarcpublishing.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT_ID"
~~~

| Chủ thể | Quyền cần xét | Mục đích |
|---|---|---|
| Deployer | Cloud Run Source Developer, Service Account User trên runtime SA; quyền tạo trigger, quản lý bucket/IAM theo nhiệm vụ | Deploy code và tạo Eventarc trigger |
| Cloud Build identity | Cloud Run Builder và quyền liên quan Artifact Registry theo đường build | Build Java/đẩy image |
| Runtime SA | Storage Object Viewer **trên input bucket**, Storage Object Creator **trên output bucket** | Chỉ đọc đầu vào và tạo báo cáo mới |
| Trigger SA | Eventarc Event Receiver và Cloud Run Invoker trên đúng service | Nhận sự kiện và gọi function đã xác thực |
| Cloud Storage service agent | Pub/Sub Publisher theo hướng dẫn Eventarc direct Storage events | Phát sự kiện đến lớp vận chuyển |
| Eventarc service agent | Vai trò service agent do nền tảng cấp/quản lý | Điều phối trigger/transport |

**Không đồng nhất runtime SA với trigger SA**: runtime cần đọc/ghi object; trigger cần gọi Cloud Run service. **Cloud Build SA** là danh tính thứ ba dùng trong build và không nên có quyền ghi output bucket nếu không cần.

### 3.3. Tạo hai service accounts riêng

~~~bash
# THAY ĐỔI IAM — chỉ thực hiện trong project lab.
gcloud iam service-accounts create fileproc-runtime \
  --project="$PROJECT_ID" \
  --display-name="File processor runtime"

gcloud iam service-accounts create fileproc-trigger \
  --project="$PROJECT_ID" \
  --display-name="Eventarc delivery identity"

RUNTIME_SA="fileproc-runtime@$PROJECT_ID.iam.gserviceaccount.com"
TRIGGER_SA="fileproc-trigger@$PROJECT_ID.iam.gserviceaccount.com"

# CHỈ ĐỌC xác nhận tồn tại.
gcloud iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT_ID"
gcloud iam service-accounts describe "$TRIGGER_SA" --project="$PROJECT_ID"
~~~

Nếu SA đã có trong project, **không tạo lại**, chỉ xác minh owner/IAM. Trong production dùng IaC và approval. Việc tạo service account không tự cấp quyền deployer được dùng SA (**iam.serviceAccounts.actAs**); quản trị viên cấp **roles/iam.serviceAccountUser** ở phạm vi SA phù hợp.

## 4. Java project và Maven dependencies

Hãy tạo **thư mục lab riêng của người học**, không tạo các file mẫu này trong module kiến thức đang được worker cập nhật. Cấu trúc:

~~~text
file-upload-java-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── functions/
                └── ProcessUpload.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.example</groupId>
  <artifactId>file-upload-java-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.32.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.1.0</version>
      <scope>provided</scope>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloudevent-types</artifactId>
      <version>0.14.0</version>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-storage</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>com.google.cloud.functions</groupId>
        <artifactId>function-maven-plugin</artifactId>
        <version>0.11.0</version>
        <configuration>
          <functionTarget>functions.ProcessUpload</functionTarget>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Phiên bản thư viện** được cố định để ví dụ tái lập, dựa trên bộ mẫu chính thức đã được công bố; với production cần cập nhật BOM/framework theo lịch bảo mật, kiểm tra tương thích Java runtime và chạy test/scan. **Functions Framework API** định nghĩa giao diện CloudEventsFunction; **google-cloudevent-types** định nghĩa StorageObjectData; **google-cloud-storage** cung cấp SDK đọc/ghi object.

### 4.2. Quy tắc thiết kế code

Hàm cần:

1. Chỉ chấp nhận **google.cloud.storage.object.v1.finalized** và bucket đầu vào được cấu hình.
2. Chỉ đọc **incoming/*.txt**, không xử lý object ở thư mục khác.
3. Đọc **đúng generation**; không lấy “bản live mới nhất” khi event cũ được giao trễ.
4. Xác minh kích thước thật của object trước khi đọc vào RAM; giới hạn 1 MiB.
5. Kiểm tra MIME (khi có) và giải mã UTF-8 nghiêm ngặt.
6. Tính số dòng, số byte, SHA-256.
7. Đặt output object name theo hash của **bucket + name + generation**.
8. Tạo output với **doesNotExist()** để xử lý lặp an toàn; lỗi khác phải báo để retry/điều tra.

## 5. Viết hàm Java xử lý tệp

Tạo **src/main/java/functions/ProcessUpload.java**:

~~~java
package functions;

import com.google.cloud.functions.CloudEventsFunction;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import com.google.events.cloud.storage.v1.StorageObjectData;
import com.google.protobuf.util.JsonFormat;
import io.cloudevents.CloudEvent;

import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;
import java.util.logging.Logger;

public final class ProcessUpload implements CloudEventsFunction {
    private static final Logger LOG =
            Logger.getLogger(ProcessUpload.class.getName());
    private static final long MAX_BYTES = 1024L * 1024L;
    private static final String FINALIZED =
            "google.cloud.storage.object.v1.finalized";

    // SDK dùng Application Default Credentials, trên Cloud Run là runtime SA.
    private final Storage storage =
            StorageOptions.getDefaultInstance().getService();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!FINALIZED.equals(event.getType())) {
            LOG.warning("Bỏ qua event type không phải object.finalized");
            return;
        }
        if (event.getData() == null) {
            LOG.warning("Bỏ qua event không có data");
            return;
        }

        StorageObjectData.Builder builder = StorageObjectData.newBuilder();
        JsonFormat.parser()
                .ignoringUnknownFields()
                .merge(
                    new String(event.getData().toBytes(),
                               StandardCharsets.UTF_8),
                    builder
                );
        StorageObjectData data = builder.build();

        String inputBucket = requiredEnv("INPUT_BUCKET");
        String outputBucket = requiredEnv("OUTPUT_BUCKET");
        String bucket = data.getBucket();
        String name = data.getName();
        long generation = data.getGeneration();

        // Filter ở tầng code để phòng sai cấu hình và object không cần xử lý.
        if (!inputBucket.equals(bucket)
                || !name.startsWith("incoming/")
                || !name.toLowerCase(Locale.ROOT).endsWith(".txt")
                || generation <= 0) {
            LOG.info("Bỏ qua object không thuộc phạm vi lab");
            return;
        }

        // Luôn khóa tới generation của event, không lấy bản live mới nhất.
        Blob blob = storage.get(BlobId.of(bucket, name, generation));
        if (blob == null) {
            // Nếu version cũ không được giữ sau overwrite/delete, không thể
            // khôi phục nội dung bằng cách đọc generation mới.
            LOG.warning("Object generation không còn khả dụng; cần điều tra");
            return;
        }

        long size = blob.getSize();
        if (size > MAX_BYTES) {
            LOG.warning("Bỏ qua file lớn hơn 1 MiB");
            return;
        }

        String mime = blob.getContentType();
        if (mime != null
                && !mime.equals("text/plain")
                && !mime.startsWith("text/plain;")) {
            LOG.warning("Bỏ qua Content-Type không phải text/plain");
            return;
        }

        byte[] bytes = storage.readAllBytes(blob.getBlobId());
        if (bytes.length > MAX_BYTES) {
            LOG.warning("Bỏ qua file có kích thước thực quá giới hạn");
            return;
        }

        // Không thay byte lỗi bằng ký tự U+FFFD; file sai UTF-8 bị reject.
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (java.nio.charset.CharacterCodingException e) {
            LOG.warning("Bỏ qua file không phải UTF-8 hợp lệ");
            return;
        }

        long lines = text.lines().count();
        String contentHash = hexSha256(bytes);

        // Tên output an toàn, không dùng object name do uploader cung cấp
        // làm đường dẫn ghi tùy ý.
        String identity = bucket + "\n" + name + "\n" + generation;
        String outputName = "summaries/"
                + hexSha256(identity.getBytes(StandardCharsets.UTF_8))
                + ".json";

        String resultJson = String.format(
                Locale.ROOT,
                "{\"generation\":\"%d\",\"bytes\":%d,\"lines\":%d,"
                + "\"sha256\":\"%s\"}%n",
                generation, bytes.length, lines, contentHash
        );

        BlobInfo target = BlobInfo.newBuilder(
                BlobId.of(outputBucket, outputName))
                .setContentType("application/json")
                .build();

        try {
            // Atomic create-if-absent: cùng object generation chỉ có
            // một summary object, kể cả nhiều instances xử lý đồng thời.
            storage.create(
                    target,
                    resultJson.getBytes(StandardCharsets.UTF_8),
                    Storage.BlobTargetOption.doesNotExist()
            );
            LOG.info("processed eventId=" + event.getId()
                    + " output=" + outputName);
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                LOG.info("duplicate event: summary đã tồn tại "
                        + outputName);
                return;
            }
            // Lỗi IAM/network/quota/transient khác: không ACK giả.
            throw e;
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường " + name);
        }
        return value;
    }

    private static String hexSha256(byte[] data) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(data));
    }
}
~~~

### 5.1. Đọc luồng xử lý

- **CloudEventsFunction.accept** được Functions Framework gọi khi Eventarc gửi CloudEvent tới Cloud Run. Class entry point là **functions.ProcessUpload**.
- **StorageObjectData** là cấu trúc metadata sự kiện; trường **generation** giúp phân biệt hai lần upload cùng tên.
- **Storage.get(BlobId.of(bucket, name, generation))** lấy đúng object generation; nếu không còn phiên bản, ví dụ chọn **không** đọc bản mới để tránh xử lý sai nội dung.
- **Blob.getSize** được đọc trước **readAllBytes** để giới hạn bộ nhớ. Với tệp lớn cần streaming và giới hạn I/O thay vì readAllBytes.
- **String.lines()** đếm các dòng văn bản; một tệp rỗng có 0 dòng. Quy ước đếm dòng trống/ký tự xuống dòng phải được xác nhận nếu dùng cho nghiệp vụ thực.
- **SHA-256** ở output là checksum của bytes đầu vào, **không phải** chữ ký điện tử hay chứng nhận file sạch.
- **Storage.BlobTargetOption.doesNotExist()** bảo đảm không ghi đè report đã được tạo; nếu GCS trả **412 Precondition Failed** cho lần xử lý lặp, hàm xem như thành công.
- Nếu lỗi đọc/ghi khác không được xử lý, hàm ném exception để Eventarc có thể retry **theo chính sách retry của trigger**.

### 5.2. Vì sao code không log tên tệp?

Tên object có thể chứa email, mã đơn hàng hoặc thông tin khách hàng. Ví dụ chỉ log **eventId** và **tên output được băm**, không log content, signed URL, headers hay tokens. Với production, đưa eventId/traceId vào structured logging và áp dụng chính sách hạn chế dữ liệu nhạy cảm.

### 5.3. Điều kiện idempotency và ranh giới của ví dụ

Với cùng bộ **(bucket, name, generation)**, output object name giống nhau và precondition create-only khiến nhiều bản giao event không tạo nhiều reports. Nhưng ví dụ **không bảo đảm exactly-once execution**: code có thể chạy nhiều lần, chỉ **side effect lên output** được khống chế. Nếu thêm gửi email, trừ tiền, ghi database hoặc publish Pub/Sub, từng side effect cũng cần transaction, idempotency key hoặc outbox thích hợp.

Sự kiện có thể **đến sai thứ tự**: ví dụ generation 3 được xử lý trước generation 2. Bài này tạo report theo từng generation nên không cần áp đặt thứ tự; nếu mục tiêu là “trạng thái mới nhất”, phải so sánh generation và cập nhật dữ liệu có điều kiện/transaction.

### 5.4. Kiểm tra Maven

Trên máy học tập có JDK 21, Maven và internet/dependency mirror hợp lệ:

~~~bash
# CHỈ BIÊN DỊCH/TEST MÁY HỌC TẬP, không deploy cloud.
java -version
mvn -version
mvn -B clean test
~~~

Dấu hiệu đạt: Maven resolve dependencies, compile class và kết thúc **BUILD SUCCESS**. Bài không yêu cầu sửa dự án Java learning đang chứa nội dung này; người học tạo một thư mục lab riêng như đã hướng dẫn.

## 6. Tạo buckets và cấp Storage IAM

### 6.1. Tạo hai bucket riêng (có phí)

~~~bash
# THAY ĐỔI thật; tên bucket phải duy nhất toàn cục.
gcloud storage buckets create "gs://$INPUT_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access

gcloud storage buckets create "gs://$OUTPUT_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access

# CHỈ ĐỌC — kiểm tra location, policy.
gcloud storage buckets describe "gs://$INPUT_BUCKET"
gcloud storage buckets describe "gs://$OUTPUT_BUCKET"
~~~

**Bucket source và Eventarc trigger phải cùng region hoặc location tương thích theo quy định Eventarc;** ví dụ này chọn cả ba cùng một region. Đối với **Cloud Storage direct events tới Cloud Run**, bucket và destination service thuộc **cùng Google Cloud project** theo đường cấu hình được mô tả. Không đổi một bucket production sang region khác để khớp lab; chọn tài nguyên lab mới phù hợp.

### 6.2. Cấp quyền runtime SA theo bucket

~~~bash
# THAY ĐỔI IAM — chỉ trong hai bucket của lab.
gcloud storage buckets add-iam-policy-binding "gs://$INPUT_BUCKET" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding "gs://$OUTPUT_BUCKET" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/storage.objectCreator"

# CHỈ ĐỌC để xác minh.
gcloud storage buckets get-iam-policy "gs://$INPUT_BUCKET"
gcloud storage buckets get-iam-policy "gs://$OUTPUT_BUCKET"
~~~

**Object Creator** cho phép tạo object mới nhưng không được ghi đè, đọc hoặc xóa object đã tồn tại; phù hợp với **doesNotExist()**. Nếu hệ thống sau này cần đọc kết quả, cấp **Object Viewer** cho *reader* khác theo policy, không mở rộng runtime SA một cách mặc định.

**Lưu ý phiên bản:** soft delete, object versioning, lifecycle/retention của bucket quyết định khả năng lưu và phục hồi generations cũ, có thể phát sinh thêm phí. Không tắt retention hay xóa dữ liệu thật chỉ vì lab cần dọn nhanh.

## 7. Deploy hàm Java

Chạy tại thư mục **file-upload-java-lab/** chứa pom.xml và code Java. Với Cloud Run functions, source build dùng Cloud Build và lưu image vào Artifact Registry; project phải có build identity đã cấu hình đúng quyền (ví dụ **Cloud Run Builder** theo tài liệu deploy functions).

~~~bash
# THAY ĐỔI: tạo Cloud Run function service private từ source.
gcloud run deploy "$FUNCTION" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source . \
  --function functions.ProcessUpload \
  --base-image java21 \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated \
  --memory=512Mi \
  --timeout=120s \
  --max-instances=5 \
  --concurrency=1 \
  --set-env-vars="INPUT_BUCKET=$INPUT_BUCKET,OUTPUT_BUCKET=$OUTPUT_BUCKET"

# CHỈ ĐỌC — URL, ready revision, runtime identity.
gcloud run services describe "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(metadata.name,status.url,status.latestReadyRevisionName,spec.template)"
~~~

**Giải thích cấu hình:** runtime **java21**, RAM **512Mi**, timeout **120 giây**, tối đa **5 instances**, mỗi instance xử lý tối đa **1 request đồng thời** theo cấu hình. Đây là giới hạn để minh họa, không phải lựa chọn tối ưu cho mọi workload. Cloud Run max instances **không phải hard cap chi phí tuyệt đối**, có thể bị vượt ngắn hạn theo cơ chế dịch vụ. Nếu function phải xử lý file lớn, cần đánh giá timeout, memory, CPU và kiến trúc batch.

**Chưa có trigger ở bước này**: service đã Ready nhưng tải file lên bucket sẽ chưa tự gọi Java code cho đến khi Eventarc trigger được tạo và hoạt động. Nếu deploy lỗi, xem **Cloud Build logs** trước; nếu build xong nhưng revision không Ready, xem **Cloud Run logs/runtime settings**.

## 8. Tạo Eventarc trigger và quyền giao sự kiện

### 8.1. Quyền của trigger identity

Eventarc dùng **TRIGGER_SA** để nhận event và gọi Cloud Run service đã yêu cầu xác thực. Chỉ cấp quyền **Invoker trên đúng service**, thay vì trên toàn project:

~~~bash
# THAY ĐỔI IAM ở project và service lab.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/eventarc.eventReceiver"

gcloud run services add-iam-policy-binding "$FUNCTION" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/run.invoker"

# CHỈ ĐỌC kiểm tra service IAM.
gcloud run services get-iam-policy "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Một trigger có thể được tạo thành công nhưng **không giao sự kiện đến service** nếu thiếu Invoker. Cần đọc log/Eventarc delivery status thay vì mở public invocation.

### 8.2. Quyền Cloud Storage service agent

Direct Cloud Storage events dùng Pub/Sub làm lớp truyền tải của Eventarc Standard. Cloud Storage service agent cần được cấp **roles/pubsub.publisher** theo hướng dẫn chính thức:

~~~bash
# CHỈ ĐỌC — xác định service agent của Cloud Storage.
STORAGE_AGENT="$(gcloud storage service-agent --project="$PROJECT_ID")"

# THAY ĐỔI PROJECT IAM — chỉ khi cần và đã được phê duyệt.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$STORAGE_AGENT" \
  --role="roles/pubsub.publisher"
~~~

Với project lâu đời, **Pub/Sub service agent** có thể cần **roles/iam.serviceAccountTokenCreator** (đặc biệt khi Pub/Sub service agent được bật từ trước ngày 08/04/2021). Đây không phải quyền nên cấp đại trà; xác định service agent thực tế và chỉ sửa khi điều kiện tài liệu áp dụng.

### 8.3. Tạo trigger

~~~bash
# THAY ĐỔI: tạo Eventarc Standard trigger, lọc finalized của input.
gcloud eventarc triggers create "$TRIGGER" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --destination-run-service="$FUNCTION" \
  --destination-run-region="$REGION" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=$INPUT_BUCKET" \
  --service-account="$TRIGGER_SA"

# CHỈ ĐỌC — lọc cấu hình và trạng thái.
gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION" \
  --format=yaml

gcloud eventarc triggers list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Trigger phải dùng **đúng input bucket name**, **event type** và **region**. Filter type không chỉnh tùy tiện sau khi tạo; nếu thay nguồn/type, cần tạo trigger phù hợp và xử lý event overlap trong giai đoạn chuyển đổi.

**Thời gian kích hoạt:** trigger có thể cần vài phút để sẵn sàng sau create. Đợi trạng thái hoạt động trước khi upload file test; nếu upload quá sớm rồi không thấy xử lý, kiểm tra log và tạo **một object mới**, không kết luận hệ thống hỏng chỉ vì trigger chưa kịp đồng bộ.

### 8.4. Các lớp IAM cần phân biệt

~~~mermaid
flowchart TB
    GCS["Cloud Storage input"] -->|"Storage service agent\nPub/Sub Publisher"| PS["Eventarc/PubSub transport"]
    PS -->|"Trigger SA\nEvent Receiver + Run Invoker"| CR["Cloud Run Java function"]
    CR -->|"Runtime SA\nStorage Object Viewer"| GCS
    CR -->|"Runtime SA\nStorage Object Creator"| OUT["Cloud Storage output"]
    BLD["Cloud Build SA\nBuilder permissions"] --> AR["Artifact Registry"]
    AR --> CR
~~~

Các phân quyền trên giải quyết **những lời gọi khác nhau**; cấp Runtime SA quyền Reader bucket không chữa lỗi Eventarc 403 Invoker, và cấp Trigger SA Invoker không giúp Java đọc tệp khi runtime thiếu Object Viewer.

## 9. Upload tệp, xem JSON kết quả và thử tình huống biên

Các lệnh minh họa sử dụng **bash trên Cloud Shell/Linux/macOS/WSL**. Nếu chạy PowerShell, điều chỉnh cú pháp biến môi trường trước khi thực thi. Cần đứng trong thư mục lab, không chạy ở thư mục module kiến thức.

### 9.1. Upload một tệp hợp lệ

~~~bash
# TẠO FILE trên máy lab.
printf 'xin chao\ncloud run\njava eventarc\n' > sample-001.txt

# THAY ĐỔI CLOUD STORAGE: upload thành một object mới.
gcloud storage cp sample-001.txt \
  "gs://$INPUT_BUCKET/incoming/sample-001.txt"

# CHỈ ĐỌC — kiểm tra object metadata và generation.
gcloud storage objects describe \
  "gs://$INPUT_BUCKET/incoming/sample-001.txt" \
  --format="yaml(name,size,contentType,generation)"
~~~

Bài dùng ba dòng và dấu xuống dòng cuối tệp. **Kỳ vọng summary:** **lines=3**, **bytes** theo dữ liệu UTF-8 thực, và một SHA-256 tương ứng. Không dự đoán tổng bytes bằng số ký tự Unicode nếu file chứa dấu tiếng Việt; byte count phải lấy từ tệp.

### 9.2. Xem event, logs và output

~~~bash
# CHỈ ĐỌC — theo dõi logs Cloud Run service.
gcloud run services logs read "$FUNCTION" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=50

# CHỈ ĐỌC — liệt kê summary objects.
gcloud storage ls "gs://$OUTPUT_BUCKET/summaries/"
~~~

Sau khi lấy tên output thật từ danh sách, có thể đọc nội dung report:

~~~bash
# Thay bằng object path thực tế, không dùng placeholder.
RESULT_OBJECT="summaries/PASTE_REAL_SHA256.json"

gcloud storage cat "gs://$OUTPUT_BUCKET/$RESULT_OBJECT"
~~~

Ví dụ cấu trúc JSON kết quả:

~~~json
{
  "generation": "1730000000000000",
  "bytes": 33,
  "lines": 3,
  "sha256": "<SHA256_CUA_TEP_THUC>"
}
~~~

Các giá trị **generation, bytes và sha256** trong khối trên chỉ minh họa định dạng, không phải kết quả chắc chắn của file. Người học cần ghi lại giá trị thực; output name là **SHA-256 của identity**, không phải SHA-256 của nội dung.

### 9.3. Kiểm thử các trường hợp bắt buộc

| Input | Hành vi mong đợi | Điều cần xác minh |
|---|---|---|
| **incoming/a.txt**, UTF-8 nhỏ | Tạo 1 summary | Đúng lines/bytes/SHA-256 |
| **incoming/a.csv** | Bỏ qua | Không có summary mới |
| **other/a.txt** | Bỏ qua | Prefix guard hoạt động |
| **incoming/big.txt** lớn hơn 1 MiB | Bỏ qua | Không đọc toàn bộ vào RAM |
| **incoming/binary.txt** chứa UTF-8 lỗi | Bỏ qua | Có log cảnh báo |
| CloudEvent trùng **cùng generation** | Output không bị ghi đè | Log duplicate/precondition |
| Upload lại cùng tên tệp | Generation mới, có thể tạo summary mới | Output khác cho mỗi generation |
| Trigger tạm thời không có Invoker | Delivery 401/403 | IAM trên Cloud Run service |
| Runtime SA thiếu Object Viewer | Hàm lỗi đọc | Runtime logs và Storage IAM |

**Không nhầm hai lần upload cùng tên với duplicate event.** Nếu gcloud storage cp ghi đè object cùng key, Cloud Storage tạo **generation mới** và đúng thiết kế là sinh **một summary mới**. Duplicate event thực sự là **giao lại một finalized event cho cùng generation**; muốn kiểm thử cần replay CloudEvent có kiểm soát hoặc inject test đã được xác thực trong môi trường lab, không chỉnh producer production.

### 9.4. Kiểm tra checksum nội dung

Bên trong thư mục lab, có thể đối chiếu SHA-256 local của **sample-001.txt**:

~~~bash
# CHỈ ĐỌC dữ liệu local.
sha256sum sample-001.txt
wc -c sample-001.txt
wc -l sample-001.txt
~~~

Lệnh **wc -l** đếm ký tự newline; với một tệp không kết thúc bằng newline, kết quả có thể **khác String.lines().count()**. Trong bài demo có newline cuối nên kết quả dự kiến khớp. Không coi hàm đếm dòng minh họa là bộ parser CSV/JSON hợp lệ.

## 10. Idempotency, retry và xử lý lỗi vĩnh viễn

Eventarc Standard giao sự kiện theo nguyên tắc **at least once**, nghĩa là một finalized event có thể được gửi tới hàm nhiều lần. Trật tự xử lý giữa các object hoặc generations cũng không được bảo đảm như một transaction log.

### 10.1. Sơ đồ quyết định khi nhận event

~~~mermaid
flowchart TD
    E["CloudEvent finalized"] --> F{"Đúng bucket, prefix, .txt và generation?"}
    F -- "Không" --> SKIP["Skip, trả success"]
    F -- "Có" --> GET["Read object@generation"]
    GET --> VALID{"MIME, <= 1 MiB, UTF-8 hợp lệ?"}
    VALID -- "Không" --> SKIP
    VALID -- "Có" --> BUILD["Tính hash, lines, bytes"]
    BUILD --> PUT["Create summary: doesNotExist"]
    PUT --> RESULT{"Ghi được?"}
    RESULT -- "Tạo mới" --> ACK["Success"]
    RESULT -- "412 đã tồn tại" --> ACK
    RESULT -- "Lỗi transient/IAM khác" --> FAIL["Log lỗi và throw"]
    FAIL --> RETRY["Eventarc retry/DLQ theo policy"]
~~~

**Cách nhận ACK:** khi Java method trả bình thường, Functions Framework có thể trả response thành công cho Eventarc. Nếu phương thức ném lỗi, delivery có thể thất bại và được retry **chỉ nếu trigger transport đang bật retry**.

### 10.2. Điều quan trọng về retry

- Trigger tạo từ **gcloud CLI** thông thường bật retry theo chính sách của Pub/Sub transport; các đường tạo trigger từ Cloud Run console có thể khác mặc định.
- Theo Eventarc Standard, exponential backoff và message retention thường gắn với Pub/Sub subscription; cần kiểm tra cấu hình hiện tại thay vì dựa hoàn toàn vào mặc định.
- **Không retry vô hạn trong code** với một tệp sai định dạng hoặc lỗi vĩnh viễn; ví dụ đã chọn log và ACK cho trường hợp không phù hợp.
- Lỗi hạ tầng tạm thời có thể được retry; lỗi IAM bị thiếu kéo dài hoặc object generation không còn cần điều tra/đưa vào luồng lỗi.
- Nên cấu hình **dead-letter topic/subscription policy** theo yêu cầu hệ thống để phân tích persistent failures. Eventarc Standard vận chuyển qua Pub/Sub; cấu hình retry/DLQ được quản lý tại **subscription** do Eventarc tạo, không phải một biến Java.
- Chú ý retention, retry và nhiều instances có thể làm tăng chi phí khi downstream lỗi.

### 10.3. Object bị overwrite và mất generation

Nếu object được upload lại cùng tên trước khi event generation cũ được xử lý, việc đọc **object@generation** chỉ thành công khi phiên bản cũ còn được giữ và được phép đọc. Không bật **Object Versioning** thì older generation có thể không còn khả dụng; ví dụ chọn ghi warning và bỏ qua để tránh lấy nhầm generation mới.

Đối với nghiệp vụ cần xử lý *mọi* phiên bản, hãy cân nhắc:

1. Quy ước **object names bất biến**, không overwrite input.
2. Bật **Object Versioning** và lifecycle policy để giữ generation cũ đủ lâu.
3. Thiết kế retention/soft delete, chi phí và quyền đọc phù hợp.
4. Dùng transactional job records/checkpoints hoặc hệ thống queue/batch nếu RPO/RTO cao.
5. Không cho phép upload trực tiếp tới output prefix/bucket bởi các danh tính không cần thiết.

**Đây là giới hạn thiết kế quan trọng**, không phải lỗi mà retry luôn khắc phục được.

## 11. Troubleshooting theo từng tầng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **Maven BUILD FAILURE** | Thiếu JDK 21, lỗi dependency, package/class sai | java -version, pom.xml, Maven output |
| **Source build 403** | Build SA thiếu quyền Builder/Artifact Registry | Cloud Build logs và SA thực tế |
| **Cloud Run revision không Ready** | Entry point sai, class không implement CloudEventsFunction, memory/startup | Revision events, runtime logs |
| **Trigger tạo nhưng không hoạt động** | Eventarc service agent đang provision, sai filter/location | describe trigger, chờ đồng bộ, kiểm tra project |
| **Upload xong không có log** | Sai bucket, trigger chưa active, event type khác | describe trigger, object metadata, Eventarc delivery |
| **Eventarc delivery 401/403** | Trigger SA thiếu **roles/run.invoker**, service private | Service IAM, trigger SA, ingress |
| **Function bị Storage 403** | Runtime SA thiếu Object Viewer/Creator hoặc bucket sai | Runtime SA, bucket IAM, logs |
| **Chỉ thấy log skip** | Tên không phải incoming/*.txt, MIME sai, file >1 MiB | Object name, size, contentType |
| **Invalid UTF-8** | File binary hoặc encoding khác | Kiểm tra file encoding, không tắt validation tùy tiện |
| **Không tìm thấy generation** | Object bị overwrite/delete và version cũ không còn | Object Versioning, generations, retention |
| **Có nhiều sự kiện trùng** | Eventarc at-least-once/retry | Cùng bucket/name/generation, output create-only |
| **Tạo nhiều reports cùng tên file** | Object có **generation mới** sau overwrite | Kiểm tra generation, expected behavior |
| **Retry liên tục** | Lỗi tạm thời hoặc quyền bị thiếu lâu ngày | Logs, Pub/Sub subscription retry/DLQ |
| **Chi phí tăng bất thường** | Trigger loop, retries, nhiều upload, logs, storage | Eventarc metrics, Cloud Run request count, Billing |
| **Output không đọc được** | Viewer IAM của người kiểm thử thiếu, không phải runtime Writer | Bucket output IAM của caller |

### 11.1. Tập lệnh chỉ đọc

~~~bash
# Trạng thái trigger và Cloud Run service.
gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION" \
  --format=yaml

gcloud run services describe "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url,status.latestReadyRevisionName,status.conditions,spec.template)"

# Logs gần nhất.
gcloud run services logs read "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION" \
  --limit=100

# Xem quyền trigger và bucket khi có quyền IAM Reader.
gcloud run services get-iam-policy "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud storage buckets get-iam-policy "gs://$INPUT_BUCKET"
gcloud storage buckets get-iam-policy "gs://$OUTPUT_BUCKET"
~~~

**Phân biệt lỗi build và lỗi giao sự kiện.** Nếu không build được Java, Eventarc chưa liên quan. Nếu Cloud Run service Ready nhưng không có request logs, kiểm tra Eventarc/Cloud Storage; nếu request đến nhưng đọc object 403, xem **runtime SA**, không sửa quyền trigger SA.

### 11.2. Checklist trước khi escalations

1. Xác nhận đúng **project, region, bucket name, function, trigger**.
2. Xác nhận event **object.finalized** thực sự được tạo *sau khi trigger active*.
3. Xem IAM của **trigger SA**, **runtime SA**, **Cloud Storage service agent** độc lập.
4. Đọc log Cloud Run và Eventarc transport; ghi **eventId, generation, timestamp**, không ghi nội dung file.
5. Đánh giá lỗi thuộc loại **permanent** hay **transient**, rồi điều chỉnh retry/DLQ có kiểm soát.
6. Chỉ gửi ticket sau khi che credentials, signed URLs, dữ liệu nhạy cảm.

## 12. Theo dõi độ tin cậy, bảo mật và chi phí

### 12.1. Những chỉ số nên quan sát

| Nhóm | Metric/log | Vì sao |
|---|---|---|
| Eventarc delivery | Số sự kiện gửi thành công/thất bại, retry | Biết trigger có giao event không |
| Cloud Run | Invocations, 4xx/5xx, latency, cold starts, instance count | Chất lượng xử lý |
| Java code | Processed/skip/duplicate/failed; generation, eventId | Chẩn đoán không lộ nội dung |
| Cloud Storage | Input finalized count, output count, object size | Đối soát event ↔ summary |
| DLQ | Số event không xử lý được | Không làm mất sự kiện âm thầm |
| Cost | Build, Run, Eventarc/Pub/Sub, Storage requests, logging | Phân tích phí theo SKU |

Các phép so sánh count cần hiểu **at-least-once**: **invocations có thể nhiều hơn số object generations**; ví dụ duplicate được ACK vẫn là invocation. Không lấy số request Cloud Run làm số tệp unique.

### 12.2. Bảo mật tệp tải lên

- Dùng **Uniform bucket-level access**, IAM theo bucket/principal; không mở public object read nếu không có yêu cầu.
- Tránh cho uploader quyền ghi sang output bucket hoặc thay đổi Eventarc trigger.
- Không đưa secret vào source, CloudEvent payload hay function environment variables dạng không được bảo vệ.
- Không trust **file extension hoặc Content-Type** như kiểm tra nội dung hoàn chỉnh; hệ thống production có thể cần magic bytes, antivirus/DLP và kiểm tra schema.
- Giới hạn object size, concurrency, timeout và memory để tránh file độc hại gây cạn tài nguyên.
- Dùng Cloud Storage **generation preconditions** khi cập nhật/chuyển trạng thái file để tránh race.
- Không chạy file tải lên hoặc giải nén archive không được sandbox/kiểm tra.
- Ghi báo cáo/metadata có retention và quyền phù hợp; SHA-256 không ẩn danh hóa nội dung có thể đoán trước.
- Với dữ liệu cần CMEK/residency, xem chính sách của bucket, Cloud Run location và KMS trước khi triển khai.

### 12.3. Phân tích chi phí

Một lần upload có thể phát sinh **Cloud Storage write**, **Eventarc event/transport**, **Cloud Run execution**, **Cloud Storage read + create**, logs và lưu trữ output. Bên cạnh đó, build/deploy ban đầu có **Cloud Build/Artifact Registry**. Nếu function được retry nhiều lần, số invocations, read requests và logs tăng.

Ví dụ để lập ngân sách, **không phải giá niêm yết**:

~~~text
Uploads mỗi ngày:                 10.000
Bản sao event trung bình:         1,02 lần / generation
Cloud Run invocations ước tính:   10.200
Output JSON tối đa kỳ vọng:       10.000 nếu mọi input hợp lệ
Đọc input:                        Có thể nhiều hơn 10.000 khi retry
Phí thực:                         Tra Cloud Billing theo Service/SKU/region
~~~

Mục tiêu hiệu quả không phải chỉ **chi phí mỗi invocation** mà là **chi phí trên mỗi object generation xử lý thành công**. Cần tính thêm lỗi/retention/DLQ và chi phí egress nếu producer/consumer ở region khác.

## 13. Case study: hệ thống tiếp nhận chứng từ Java

**Bối cảnh giả định:** ứng dụng Java nhận chứng từ text từ đối tác, upload vào Cloud Storage. Một sự kiện finalized kích hoạt hàm Java tạo summary, hệ thống phân tích đọc metadata sau khi có output.

### 13.1. Thiết kế tối thiểu

~~~mermaid
flowchart LR
    PARTNER["Uploader đã xác thực"] --> IN["GCS input\nincoming/"]
    IN --> EVT["Eventarc finalized"]
    EVT --> FN["Java Cloud Run function"]
    FN --> OUT["GCS output\nsummaries/"]
    OUT --> JOB["Downstream job/indexer"]
    ERR["DLQ + alert"] -. "Persistent failures" .-> EVT
~~~

Quy tắc quan trọng:

- Mỗi tệp nguồn có **ID bất biến**, tránh overwrite nếu cần xử lý mọi bản.
- Event ID và object generation được theo dõi để phát hiện duplicate/delivery delay.
- Hàm **không nhận trách nhiệm lưu bản gốc**: input bucket và retention policy mới là nguồn dữ liệu chính.
- Đầu ra không bị ghi đè nhờ conditional write; consumer kiểm tra generation/source checksum nếu muốn đối soát.
- Khi xử lý ảnh/PDF kích thước lớn, chuyển sang streaming/batch và kiểm tra nội dung an toàn thay vì readAllBytes.

### 13.2. Bốn tình huống cần quyết định

| Tình huống | Hành động |
|---|---|
| Partner gửi lại object cùng tên | Generation thay đổi; xử lý từng generation hoặc cấm overwrite theo business rule |
| Event được giao lại | Ghi summary create-only, nếu đã có thì ACK, không tạo trùng |
| Cloud Storage trả 503 khi đọc | Cho phép retry với backoff/DLQ theo policy |
| Partner gửi file không phải UTF-8 | Ghi metric/reject reason, không retry vô hạn; có quy trình thông báo uploader |

**Mức tin cậy của bài demo** chỉ nằm ở output summary. Hệ thống nghiệp vụ hoàn chỉnh cần job registry/trạng thái, dead-letter handling, cảnh báo chậm xử lý và kiểm tra kết quả trước khi hứa với uploader rằng tệp đã được xử lý xong. **Upload thành công** chỉ chứng minh object đã được lưu, không chứng minh toàn bộ pipeline đã xử lý thành công.

## 14. Bài tập và đáp án định hướng

### 14.1. Bài tập A — Kiểm thử đường đi event

Trong lab đã được cấp quyền:

1. Tạo hai buckets cùng region với function và trigger.
2. Deploy Java function với runtime/trigger SA riêng.
3. Upload một tệp UTF-8 ba dòng dưới **incoming/**.
4. Đọc event logs và JSON output.
5. Ghi lại **eventId, generation, số dòng, số byte và SHA-256**; đối chiếu với lệnh local.
6. Upload file **.csv**, file **.txt** lớn hơn 1 MiB; kiểm tra log skip và không có output tương ứng.
7. Upload một object mới cùng tên, so sánh generations và output names.

**Tiêu chí đạt:** file hợp lệ tạo một summary cho mỗi generation; file không hợp lệ bị bỏ qua có thể quan sát; không có public Cloud Run invoke hoặc quyền admin không cần thiết.

### 14.2. Bài tập B — Suy luận retry/idempotency

Giả sử Eventarc giao cùng finalized event **3 lần** tới 3 instances đang chạy đồng thời. Cả ba đều đọc đúng cùng một generation. Đáp án đúng cho các câu hỏi:

- **Bao nhiêu lần code có thể chạy?** Có thể cả 3 lần.
- **Bao nhiêu JSON output objects được tạo với doesNotExist()?** Tối đa **1** cho cùng output identity.
- **Các lời gọi còn lại nhận lỗi gì nếu output đã có?** Create precondition có thể trả **412**; code bắt và ACK.
- **Điều gì xảy ra nếu thêm thao tác gửi email trước conditional write?** Email có thể gửi **3 lần**. Cần thiết kế idempotency cho email/side effect đó.
- **Nếu 3 events có generation khác nhau?** Đây là 3 bản nội dung khác nhau và có thể có 3 summaries.

### 14.3. Bài tập C — Thay đổi bài toán

Hãy sửa thiết kế để xử lý một ảnh JPEG được upload:

- Kiểm tra MIME/bytes thực, size limit và không chỉ dựa trên đuôi **.jpg**.
- Giới hạn kích thước và số pixel để chống decompression bomb.
- Tạo thumbnail trong **bucket output riêng**, không ghi trở lại bucket input mà trigger theo dõi.
- Dùng **object generation** trong idempotency key và output name.
- Với ảnh lớn, dùng streaming hoặc job chuyên biệt, không dồn toàn bộ ảnh vào memory.
- Thêm unit/integration tests cho retry, ảnh lỗi, ảnh quá lớn và object bị overwrite.

**Đáp án định hướng:** event type và trigger vẫn là **object.finalized**, nhưng handler/library, validation và output cần thay. Không gọi Cloud Storage object metadata là chứng minh tệp an toàn.

### 14.4. Bài tập D — Điều tra tình huống mất báo cáo

Một file **incoming/contract.txt** đã upload, nhưng không có JSON output. Trong Cloud Run logs xuất hiện **StorageException 403**; Eventarc trigger ACTIVE.

**Cần kiểm tra:** runtime SA của Cloud Run revision, đúng input bucket, **roles/storage.objectViewer**, quyền đọc generation, organization policy/VPC-SC (nếu có), và logs. Không cấp Invoker hay Pub/Sub Publisher thêm khi event đã vào hàm. Sau khi sửa IAM, xác minh retry hoặc tạo object test mới; nếu retention hết hạn, cần kế hoạch replay an toàn từ nguồn gốc.

### 14.5. Câu hỏi nhanh

1. **object.finalized** có phát sinh khi overwrite không?
2. **metageneration** có thay thế **generation** cho định danh nội dung không?
3. CloudEventsFunction khác HttpFunction ở đâu?
4. Runtime SA cần Invoker để tự đọc Cloud Storage không?
5. Trigger SA cần Object Viewer để Java đọc file không?
6. Vì sao đọc object name mà không khóa generation có thể sai?
7. Vì sao hai buckets giúp tránh vòng lặp?
8. Có thể dựa vào Eventarc để bảo đảm exactly-once processing không?
9. Vì sao summary JSON có SHA-256 vẫn không phải chứng nhận malware-free?
10. Xóa Cloud Run service có tự xóa input/output buckets không?

**Đáp án:** (1) Có, generation mới. (2) Không; metageneration là metadata version. (3) CloudEventsFunction tiêu thụ CloudEvents từ event provider, HttpFunction xử lý HTTP trực tiếp. (4) Không, cần Storage permissions. (5) Không, trigger SA cần quyền nhận event và gọi service. (6) Event đến trễ có thể đọc nhầm bản mới. (7) Event output không rơi vào bucket được trigger. (8) Không, at-least-once. (9) Hash chỉ xác định bytes. (10) Không.

### 14.6. Mẫu biên bản nghiệm thu

~~~text
PROJECT_ID / REGION:
INPUT_BUCKET / OUTPUT_BUCKET:
FUNCTION / READY_REVISION:
TRIGGER_NAME / TRIGGER_ACTIVE:
RUNTIME_SA / TRIGGER_SA:
IAM_REVIEW_RESULT:
SOURCE_OBJECT_NAME / GENERATION:
SOURCE_SIZE / CONTENT_TYPE:
CLOUD_EVENT_ID / TYPE:
OUTPUT_OBJECT / CONTENT:
LOCAL_SHA256_MATCH:
DUPLICATE_EVENT_RESULT:
INVALID_FILE_RESULT:
RETRY_POLICY / DLQ:
ERROR_LOGS / ALERT:
ESTIMATED_COST_SOURCES:
CLEANUP_RESULT / OPEN_ISSUES:
~~~

Chỉ ghi **PASS** với kết quả thật đã quan sát. Không đưa file nội bộ, tokens, signed URLs hoặc private customer data vào biên bản công khai.

## 15. Dọn tài nguyên lab an toàn

**Thứ tự hợp lý:** ngừng trigger trước, ngừng service, kiểm kê objects, rồi mới cân nhắc dọn buckets/IAM. Các lệnh xóa dưới đây là thao tác thật và **chỉ được chạy với tài nguyên lab do mình sở hữu**.

### 15.1. Xác minh phạm vi trước khi xóa

~~~bash
# CHỈ ĐỌC.
gcloud config list project

gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION"

gcloud run services describe "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud storage ls "gs://$INPUT_BUCKET/incoming/"
gcloud storage ls "gs://$OUTPUT_BUCKET/summaries/"
~~~

Nếu bất kỳ tài nguyên nào đang được người khác sử dụng, **không xóa** theo tên vì nó trùng với ví dụ. Kiểm tra billing, retention/holds, Object Versioning và soft delete để biết tài nguyên nào còn chi phí dù ngừng workload.

### 15.2. Xóa trigger và function lab

~~~bash
# XÓA TÀI NGUYÊN THẬT — chỉ sau khi owner chấp thuận.
gcloud eventarc triggers delete "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION"

gcloud run services delete "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**Sau khi xóa:** Eventarc không còn giao events mới qua trigger này, Cloud Run không còn revision service; những objects, logs, IAM bindings, service accounts, Pub/Sub resources còn tồn tại theo cơ chế dịch vụ và ownership của chúng. Không tự xóa bucket production hay project chung.

### 15.3. Dọn Storage và IAM chỉ khi được phê duyệt

- Kiểm kê từng object, generation và retention trong **hai bucket lab**.
- Nếu xóa objects, chỉ xóa **đúng những object của lab đã được xác nhận**, không dùng một câu lệnh recursive trên bucket chung.
- Xóa bucket chỉ khi chắc chắn nó được tạo riêng cho bài học, đã trống/đáp ứng retention và không có consumers.
- IAM bindings và **fileproc-runtime / fileproc-trigger** có thể được thu hồi sau khi chắc chắn không còn tài nguyên nào tham chiếu; không xóa Google service agents hoặc role bindings dùng chung.
- **cloud-run-source-deploy** có thể chứa images của các functions/services khác; không mặc định xóa repository này.
- Đối chiếu Cloud Billing sau thời gian ghi nhận dữ liệu; storage, logs và retention có thể tiếp tục phát sinh phí.

## 16. Tài liệu tham khảo và ghi nhớ

- [Cloud Run: Trigger functions from Cloud Storage using Eventarc](https://docs.cloud.google.com/run/docs/tutorials/trigger-functions-storage)
- [Cloud Run: Write Cloud Run functions](https://docs.cloud.google.com/run/docs/write-functions)
- [Cloud Run: Deploy a function](https://docs.cloud.google.com/run/docs/deploy-functions)
- [Cloud Run: Java runtimes](https://docs.cloud.google.com/run/docs/runtimes/java)
- [Cloud Run: Function triggers](https://docs.cloud.google.com/run/docs/function-triggers)
- [Eventarc: Cloud Storage trigger event types](https://docs.cloud.google.com/run/docs/triggering/storage-triggers)
- [Eventarc Standard: Retry events](https://docs.cloud.google.com/eventarc/docs/retry-events)
- [Eventarc: Roles and permissions for Cloud Run targets](https://docs.cloud.google.com/eventarc/docs/roles-permissions)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage Java client: BlobTargetOption.doesNotExist](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobTargetOption)
- [Cloud Run: Local functions development](https://docs.cloud.google.com/run/docs/local-dev-functions)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Eventarc pricing](https://cloud.google.com/eventarc/pricing)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)

**Checklist cốt lõi:** đúng project/region → input/output riêng → Java CloudEventsFunction và đúng generation → runtime SA tối thiểu → deploy private → trigger SA Event Receiver + Invoker → Storage service agent Pub/Sub Publisher → upload test → kiểm tra logs/summary/checksum → duplicate-safe write → retry/DLQ/monitoring → dọn đúng phạm vi.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** ví dụ này phối hợp **Cloud Run functions, Eventarc, Cloud Storage, Artifact Registry/Cloud Build, IAM và Cloud Logging/Billing**. Mô hình event-driven giúp không phải quản lý VM hoặc GKE node, nhưng độ tin cậy vẫn phụ thuộc vào **dữ liệu bền vững, đúng danh tính, xử lý idempotent, kiểm soát thất bại và quan sát chi phí**.









