# Generation precondition và ngăn ghi đè ngoài ý muốn

## 1. Vì sao cần precondition?

Cloud Storage cho phép nhiều service instance, worker và người dùng cùng truy cập một object. Một object có thể bị ghi đè, xóa hoặc cập nhật metadata trong lúc request khác đang xử lý. Nếu ứng dụng đọc trạng thái object, quyết định dựa trên trạng thái đó rồi gửi lệnh ghi/xóa mà không kiểm tra lại, trạng thái có thể đã thay đổi trước khi lệnh tới Cloud Storage.

Ví dụ, hai request cùng đọc tài liệu có generation 100. Request A cập nhật file và tạo generation 101. Request B vẫn giữ nội dung cũ và gửi bản cập nhật của nó. Nếu B ghi đè vô điều kiện, thay đổi của A có thể bị mất. Một tình huống khác nguy hiểm hơn: worker đã lên lịch xóa object cũ, nhưng trong lúc chờ, object cùng tên đã được người dùng upload phiên bản mới. Lệnh xóa không điều kiện có thể xóa nhầm file mới.

**Request precondition** là điều kiện để Cloud Storage chỉ thực hiện một thao tác khi object đang ở đúng trạng thái mà ứng dụng kỳ vọng. Với object, hai giá trị quan trọng nhất là **generation** và **metageneration**. Chúng giúp xây dựng thao tác compare-and-set, bảo vệ read-modify-write, chống race condition và làm cho một số request an toàn khi retry.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào generation precondition và cách ngăn ghi đè ngoài ý muốn khi dùng Cloud Storage Java client.

Sau bài học, bạn có thể:

- Phân biệt generation, metageneration và ETag.
- Chọn precondition phù hợp cho create, overwrite, delete, read và metadata update.
- Dùng giá trị generation 0 để chỉ tạo object khi chưa có live version.
- Dùng generation-match để chỉ thay thế hoặc xóa đúng phiên bản đã đọc.
- Kết hợp generation-match và metageneration-match khi cập nhật metadata.
- Xử lý HTTP 412 và 304 theo đúng ý nghĩa.
- Thiết kế retry an toàn khi request timeout hoặc mất response.
- Tích hợp optimistic concurrency control vào service Spring Boot và database.
- Kiểm thử race condition trên bucket GCP riêng.

> **Phạm vi phiên bản:** Ví dụ dùng Google Cloud Storage Java client, artifact com.google.cloud:google-cloud-storage. Hãy quản lý version bằng BOM phù hợp với baseline Java/Spring của dự án và kiểm tra Javadoc của version thực tế. Tên bucket, object và generation trong ví dụ chỉ là dữ liệu minh họa.

## 2. Generation và metageneration

Cloud Storage object gồm dữ liệu (bytes) và metadata. Hai phần này có vòng đời liên quan nhưng được phiên bản hóa riêng.

### 2.1. Generation: phiên bản dữ liệu

**Generation** là số phiên bản của object data. Mỗi lần object được tạo hoặc ghi một phiên bản dữ liệu mới, generation thay đổi. Generation là giá trị do Cloud Storage cấp và không thể tự đặt.

Ví dụ:

| Thời điểm | Thao tác | Generation | Nội dung |
| --- | --- | ---: | --- |
| T1 | Upload tài liệu lần đầu | 100 | Bản A |
| T2 | Cập nhật bytes | 101 | Bản B |
| T3 | Cập nhật bytes lần nữa | 102 | Bản C |

Các con số 100, 101, 102 chỉ minh họa. Generation thực tế là giá trị số lớn do Cloud Storage tạo ra; không dựa vào nó để suy ra thời gian, thứ tự toàn cục hoặc số lần upload trong hệ thống khác.

Nếu Object Versioning được bật, các generation cũ có thể còn tồn tại dưới dạng noncurrent version. Nếu versioning tắt, phiên bản cũ thường không còn được truy cập như một object version bình thường sau khi bị thay thế. Dù cấu hình versioning ra sao, object name vẫn xác định live object; muốn truy cập generation cũ cần chỉ rõ generation.

### 2.2. Metageneration: phiên bản metadata

**Metageneration** là số phiên bản metadata của một generation cụ thể. Khi cập nhật metadata như Content-Type, Cache-Control, custom metadata hoặc metadata khác, metageneration tăng. Thay đổi bytes tạo generation mới và metageneration của generation mới bắt đầu lại từ 1.

Ví dụ:

| Thời điểm | Thao tác | Generation | Metageneration |
| --- | --- | ---: | ---: |
| T1 | Upload bytes và metadata ban đầu | 100 | 1 |
| T2 | Đổi Content-Type | 100 | 2 |
| T3 | Sửa custom metadata | 100 | 3 |
| T4 | Upload bytes mới | 101 | 1 |
| T5 | Đổi Cache-Control của bản mới | 101 | 2 |

Do đó:

- Generation trả lời: **bytes đang là phiên bản nào?**
- Metageneration trả lời: **metadata của phiên bản bytes đó đang là phiên bản nào?**

Bucket cũng có metageneration cho metadata của bucket, nhưng bucket không có generation như object data.

### 2.3. ETag khác generation như thế nào?

ETag là validator được Cloud Storage trả về trong response. Ứng dụng không nên giả định ETag luôn là MD5 hoặc có cùng biểu diễn giữa JSON API và XML API. ETag hữu ích cho HTTP conditional request như If-Match và If-None-Match, nhưng generation và metageneration thường là lựa chọn rõ ràng hơn cho thao tác object trong Cloud Storage.

| Giá trị | Thay đổi khi nào? | Dùng để bảo vệ |
| --- | --- | --- |
| Generation | Bytes object có phiên bản mới | Đọc, ghi đè, xóa đúng phiên bản dữ liệu |
| Metageneration | Metadata của object được cập nhật | Read-modify-write metadata |
| ETag | Theo validator do dịch vụ trả về | HTTP cache/conditional retrieval |

Không dùng metageneration một mình để bảo vệ object metadata update. Nếu object data bị thay thế, generation mới có thể có cùng metageneration number (ví dụ 1). Với object request, hãy kết hợp generation-match và metageneration-match khi cả dữ liệu lẫn metadata cần đúng với snapshot đã đọc.

## 3. Các loại precondition

Cloud Storage hỗ trợ bốn điều kiện chính trên generation và metageneration.

| Precondition | Điều kiện để request tiếp tục | Khi không thỏa |
| --- | --- | --- |
| ifGenerationMatch = N | Generation hiện tại bằng N | HTTP 412 Precondition Failed |
| ifGenerationNotMatch = N | Generation hiện tại khác N | HTTP 304 Not Modified |
| ifMetagenerationMatch = M | Metageneration hiện tại bằng M | HTTP 412 Precondition Failed |
| ifMetagenerationNotMatch = M | Metageneration hiện tại khác M | HTTP 304 Not Modified |

ifGenerationMatch và ifGenerationNotMatch loại trừ nhau; tương tự cho hai điều kiện metageneration. Có thể kết hợp một điều kiện generation với một điều kiện metageneration trong cùng request. Nếu bất kỳ điều kiện nào không thỏa, request không được thực hiện.

### 3.1. Giá trị đặc biệt generation = 0

ifGenerationMatch=0 có ý nghĩa đặc biệt khi ghi object data: request chỉ thành công nếu bucket hiện không có **live object** cùng tên. Nếu chỉ còn noncurrent versions do Object Versioning, thao tác vẫn có thể thành công. Nếu đã có live version, Cloud Storage trả 412.

Chỉ dùng giá trị 0 cho thao tác ghi object data như upload/insert. Không dùng generationMatch(0) như điều kiện chung cho read, delete hoặc metadata update.

Trong Java client, option doesNotExist() biểu đạt mục đích create-only rõ hơn việc truyền số 0 trực tiếp.

### 3.2. JSON API và XML API

| API | Generation match | Metageneration match |
| --- | --- | --- |
| JSON API | Query parameter ifGenerationMatch | Query parameter ifMetagenerationMatch |
| XML API | Header x-goog-if-generation-match | Header x-goog-if-metageneration-match |

Với các điều kiện not-match, JSON API hỗ trợ query parameter tương ứng. XML API không hỗ trợ mọi biến thể not-match. Khi dùng Java client, chọn option tương ứng của SDK thay vì tự ghép query string hoặc header.

### 3.3. Preconditions không thay thế IAM

Precondition chỉ xác nhận trạng thái tài nguyên tại thời điểm Cloud Storage xử lý request. Nó không cấp quyền. Principal vẫn cần IAM permission phù hợp:

- Upload object cần storage.objects.create.
- Ghi đè object có thể cần thêm storage.objects.delete theo semantics của thao tác.
- Đọc bytes/metadata cần storage.objects.get.
- List object cần storage.objects.list.
- Xóa object cần storage.objects.delete.

Retention policy, object hold, soft delete và các policy khác vẫn áp dụng. Một request có generation match đúng vẫn có thể bị từ chối vì principal thiếu quyền hoặc object đang bị retention/hold bảo vệ.

## 4. Tạo object chỉ khi tên chưa tồn tại

Đây là tình huống phổ biến nhất: người dùng upload tài liệu mới và ứng dụng không muốn ghi đè object cùng tên.

### 4.1. Cách dễ gây race condition

Một cách làm có vẻ hợp lý là đọc trước để xem object đã tồn tại chưa rồi mới upload:

~~~java
Blob existing = storage.get(bucket, objectName);

if (existing == null) {
    storage.create(blobInfo, content);
}
~~~

Cách này có khoảng thời gian giữa lần get và lần create. Hai request có thể cùng thấy object chưa tồn tại rồi cùng upload. Request đến sau có thể ghi đè object của request đến trước.

### 4.2. Dùng doesNotExist()

Hãy để Cloud Storage kiểm tra điều kiện ngay trong request ghi:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public Blob createOnly(
        Storage storage,
        String bucket,
        String objectName,
        byte[] content) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("application/pdf")
        .build();

    return storage.create(
            info,
            content,
            Storage.BlobTargetOption.doesNotExist());
}
~~~

Nếu chưa có live object, upload thành công. Nếu object đã tồn tại, Cloud Storage trả 412. Việc kiểm tra và ghi có điều kiện được thực hiện tại dịch vụ, không có khoảng hở giữa hai request của ứng dụng.

### 4.3. Upload file lớn bằng WriteChannel

Với dữ liệu lớn, vẫn cần precondition trong thao tác upload resumable:

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void createOnlyFromStream(
        Storage storage,
        BlobInfo info,
        InputStream source) throws Exception {

    try (WriteChannel writer = storage.writer(
                info,
                Storage.BlobWriteOption.doesNotExist());
         OutputStream output = Channels.newOutputStream(writer)) {
        source.transferTo(output);
    }
}
~~~

Precondition được áp dụng cho upload cuối cùng. Đóng writer hoàn tất upload; nếu điều kiện không còn thỏa, thao tác không được commit thành object live. Trong ứng dụng thực tế, quản lý ownership của InputStream nguồn rõ ràng và chỉ đóng stream ở tầng đã tạo hoặc sở hữu nó.

### 4.4. Khi object name phải duy nhất

Có thể sinh object name bằng UUID hoặc document ID nội bộ. Tuy nhiên, tên duy nhất không thay thế precondition: retry, bug hoặc request trùng lặp vẫn có thể gửi cùng object name. Dùng doesNotExist() làm hàng rào cuối tại Cloud Storage.

## 5. Ghi đè khi chỉ phiên bản đã đọc còn hiện hành

Một nghiệp vụ khác là cho phép thay thế object hiện có, nhưng chỉ khi chưa có ai cập nhật nó kể từ lúc ứng dụng đọc.

### 5.1. Read-modify-write với generation

Giả sử ứng dụng đọc metadata và nhận generation 100. Sau khi xử lý file, nó upload phiên bản mới với generationMatch(100):

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public Blob replaceIfUnchanged(
        Storage storage,
        String bucket,
        String objectName,
        long expectedGeneration,
        byte[] newContent) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("application/pdf")
        .build();

    return storage.create(
            info,
            newContent,
            Storage.BlobTargetOption.generationMatch(
                    expectedGeneration));
}
~~~

Nếu live object vẫn là generation 100, upload tạo generation mới. Nếu worker khác đã tạo generation 101, request bị từ chối với 412. Nhờ đó ứng dụng không âm thầm ghi đè thay đổi mới hơn.

### 5.2. Lưu generation trong database

Khi tạo document record, có thể lưu generation trả về từ GCS cùng với bucket/object name:

~~~java
Blob created = storage.create(
        blobInfo,
        content,
        Storage.BlobTargetOption.doesNotExist());

documentRepository.save(new DocumentRecord(
        documentId,
        bucket,
        objectName,
        created.getGeneration(),
        created.getMetageneration()));
~~~

DocumentRecord chỉ là kiểu dữ liệu minh họa. Trong thực tế, cập nhật database và GCS không nằm trong cùng một transaction ACID. Hãy thiết kế trạng thái nghiệp vụ như PENDING, UPLOADED, READY, FAILED và cơ chế reconciliation/outbox phù hợp nếu cần phối hợp hai hệ thống.

### 5.3. Compare-and-set với hai worker

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant GCS as Cloud Storage

    A->>GCS: GET metadata
    GCS-->>A: generation 100
    B->>GCS: GET metadata
    GCS-->>B: generation 100
    A->>GCS: Upload với ifGenerationMatch=100
    GCS-->>A: Thành công, generation 101
    B->>GCS: Upload với ifGenerationMatch=100
    GCS-->>B: 412 Precondition Failed
    B->>B: Đọc lại và xử lý conflict
~~~

Đây là optimistic concurrency control: nhiều worker có thể đọc cùng lúc, nhưng chỉ một worker cập nhật thành công từ một generation cụ thể. Worker còn lại phải đọc trạng thái mới và quyết định có áp dụng lại nghiệp vụ hay báo conflict.

## 6. Xóa đúng object đã xác nhận

### 6.1. Nguy cơ xóa nhầm phiên bản mới

Giả sử một job đọc generation 200 rồi lên lịch xóa object sau vài phút. Trong thời gian đó, người dùng upload bản mới generation 201. Nếu job gọi delete(bucket, objectName) không điều kiện, nó có thể xóa live object 201 dù job chỉ định xóa bản 200.

### 6.2. Delete với generationMatch

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public boolean deleteIfUnchanged(
        Storage storage,
        String bucket,
        String objectName,
        long expectedGeneration) {

    return storage.delete(
            BlobId.of(bucket, objectName),
            Storage.BlobSourceOption.generationMatch(
                    expectedGeneration));
}
~~~

Nếu live generation vẫn khớp, delete được thực hiện. Nếu object đã bị thay thế, request thất bại với 412. Nếu không còn live object, kết quả phụ thuộc trạng thái hiện tại và API response; hãy xử lý not-found/false theo contract của method đang dùng.

Nếu cần xóa một noncurrent version cụ thể khi Object Versioning được bật, tạo BlobId có generation cụ thể và dùng API/options phù hợp để chỉ định đúng version. Đừng nhầm thao tác xóa live object với xóa một noncurrent generation.

### 6.3. Delete và retry sau timeout

Tình huống nguy hiểm:

1. Client gửi lệnh delete và bị timeout.
2. Ứng dụng không biết server đã xóa object hay chưa.
3. Một upload mới tạo object cùng tên.
4. Client retry lệnh delete vô điều kiện.
5. Phiên bản mới có thể bị xóa nhầm.

Nếu delete gắn với generation đã đọc, request retry chỉ nhắm đúng generation đó. Khi live object đã đổi generation, precondition không còn thỏa và request không xóa phiên bản mới.

## 7. Cập nhật metadata với metageneration

Metadata update có thể gặp race condition ngay cả khi bytes không đổi. Ví dụ hai service cùng sửa Cache-Control và Content-Disposition. Nếu mỗi service đọc metadata cũ rồi gửi bản cập nhật vô điều kiện, thay đổi của service đến trước có thể bị ghi đè bởi bản cập nhật cũ của service đến sau.

### 7.1. Dùng generation và metageneration cùng nhau

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob updateContentType(
        Storage storage,
        String bucket,
        String objectName,
        String newContentType) {

    Blob current = storage.get(
            BlobId.of(bucket, objectName));

    if (current == null) {
        throw new IllegalStateException("Object không tồn tại");
    }

    BlobInfo updated = current.toBuilder()
            .setContentType(newContentType)
            .build();

    return storage.update(
            updated,
            Storage.BlobTargetOption.generationMatch(
                    current.getGeneration()),
            Storage.BlobTargetOption.metagenerationMatch(
                    current.getMetageneration()));
}
~~~

Hai điều kiện bảo vệ hai giả định:

- Generation match bảo đảm metadata đang sửa vẫn thuộc đúng phiên bản bytes đã đọc.
- Metageneration match bảo đảm metadata chưa bị service khác thay đổi kể từ lúc đọc.

Nếu chỉ dùng metageneration, một generation mới cũng có thể có metageneration 1 giống phiên bản trước. Vì vậy, với object metadata update, hãy kết hợp cả hai khi thao tác dựa trên snapshot metadata đã đọc.

### 7.2. Cập nhật một metadata field

Nếu ứng dụng chỉ muốn đổi một field, vẫn phải giữ lại các field cần thiết trong BlobInfo được gửi. Dùng current.toBuilder() giúp bắt đầu từ metadata snapshot đã đọc. Nếu một worker khác thay đổi metadata trước khi request chạy, precondition sẽ ngăn ứng dụng ghi đè snapshot cũ.

Không tự tạo BlobInfo chỉ có một field rồi giả định mọi metadata khác sẽ được giữ nguyên. Kiểm tra semantics PATCH/UPDATE của API và phiên bản SDK.

## 8. Bảo vệ thao tác đọc metadata và bytes

Một quy trình thường đọc metadata trước để lấy size, Content-Type hoặc generation rồi tải bytes trong request tiếp theo. Object có thể thay đổi giữa hai request.

### 8.1. Pin generation khi đọc bytes

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Path;

public void downloadSameGeneration(
        Storage storage,
        String bucket,
        String objectName,
        Path destination) throws Exception {

    Blob metadata = storage.get(
            BlobId.of(bucket, objectName));

    if (metadata == null) {
        throw new IllegalStateException("Object không tồn tại");
    }

    BlobId pinnedVersion = BlobId.of(
            bucket,
            objectName,
            metadata.getGeneration());

    try (ReadChannel reader = storage.reader(pinnedVersion);
         InputStream input = Channels.newInputStream(reader);
         var output = Files.newOutputStream(destination)) {
        input.transferTo(output);
    }
}
~~~

Việc pin generation bảo đảm bytes tải về thuộc đúng phiên bản mà metadata ban đầu mô tả. Nếu generation đó không còn được lưu giữ, request có thể trả not found. Nếu chỉ dùng object name, ứng dụng có thể lấy metadata của phiên bản cũ nhưng tải bytes của phiên bản mới.

### 8.2. Dùng generationMatch trên read

Có thể dùng Storage.BlobSourceOption.generationMatch(expectedGeneration) khi gọi API đọc có hỗ trợ source options. Khi dùng BlobId đã chứa generation, request cũng chỉ định rõ version cần đọc. Đọc Javadoc của method cụ thể để chọn đúng overload và loại option.

### 8.3. Cache và kiểm tra object đã thay đổi

Nếu local cache đang lưu generation 100, ứng dụng có thể dùng ifGenerationNotMatch=100 để chỉ tải khi object trên bucket khác generation local. Khi object chưa thay đổi, JSON API trả 304 Not Modified và không tải lại bytes. Đây là kỹ thuật cache validation; không nhầm 304 với 412 của match precondition.

## 9. Tích hợp Java Storage client trong Spring Boot

### 9.1. Dependency

Nếu dự án đã quản lý Google Cloud libraries bằng BOM:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
</dependency>
~~~

Không tự gắn một version độc lập nếu BOM của dự án đã quản lý version.

### 9.2. Cấu hình Storage bean

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcsConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Nếu Spring Framework on Google Cloud starter đã auto-configure bean Storage, inject bean có sẵn. Không tạo client mới cho từng request.

### 9.3. Đưa bucket vào cấu hình

~~~yaml
app:
  gcs:
    bucket: training-documents-dev
~~~

Bucket name theo môi trường nên được quản lý bằng configuration hoặc environment variable. Không cho client tùy ý gửi bucket name trong request.

### 9.4. Tách adapter khỏi nghiệp vụ

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GcsDocumentAdapter {

    private final Storage storage;
    private final String bucket;

    public GcsDocumentAdapter(
            Storage storage,
            @Value("#{environment['app.gcs.bucket']}") String bucket) {
        this.storage = storage;
        this.bucket = bucket;
    }

    public Blob create(
            String objectName,
            byte[] content,
            String contentType) {

        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
            .setContentType(contentType)
            .build();

        return storage.create(
                info,
                content,
                Storage.BlobTargetOption.doesNotExist());
    }

    public Blob replace(
            String objectName,
            long expectedGeneration,
            byte[] content,
            String contentType) {

        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
            .setContentType(contentType)
            .build();

        return storage.create(
                info,
                content,
                Storage.BlobTargetOption.generationMatch(
                        expectedGeneration));
    }

    public boolean delete(
            String objectName,
            long expectedGeneration) {

        return storage.delete(
                BlobId.of(bucket, objectName),
                Storage.BlobSourceOption.generationMatch(
                        expectedGeneration));
    }
}
~~~

Adapter nhận generation từ service nghiệp vụ. Controller không nên tự quyết định generation hoặc bucket dựa trên input tùy ý; service cần lấy chúng từ document record đã được xác thực quyền truy cập.

## 10. Mô hình optimistic locking giữa database và Cloud Storage

Một ứng dụng thường lưu document metadata trong database và bytes trong GCS. Generation có thể đóng vai trò version token cho object storage, tương tự version column trong database.

### 10.1. Luồng upload mới

1. Tạo document record ở trạng thái PENDING với object name duy nhất.
2. Upload bằng doesNotExist().
3. Nhận generation và metageneration từ GCS.
4. Cập nhật record database thành READY, lưu generation và size.
5. Nếu database update thất bại sau khi upload thành công, job reconciliation tìm object mồ côi hoặc hoàn tất record theo idempotency key.

### 10.2. Luồng cập nhật tài liệu

1. Đọc document record và generation đã lưu.
2. Kiểm tra quyền sửa và trạng thái nghiệp vụ.
3. Upload bytes mới bằng generationMatch(expectedGeneration).
4. Nếu thành công, lưu generation mới vào database.
5. Nếu 412, đọc lại object và document record; trả conflict hoặc chạy lại nghiệp vụ dựa trên bản mới.

### 10.3. Không có transaction phân tán tự động

Database transaction không bao trùm Cloud Storage request. Không giả định @Transactional sẽ rollback một upload GCS nếu câu lệnh SQL sau đó thất bại. Hãy dùng state machine, outbox/job, idempotency key, retry có kiểm soát và reconciliation để phối hợp hai hệ thống.

## 11. Retry, idempotency và HTTP status

### 11.1. Vì sao precondition làm retry an toàn hơn?

Một request timeout có thể đã được Cloud Storage xử lý nhưng response không đến được client. Nếu client retry một lệnh ghi/xóa không điều kiện, request thứ hai có thể tác động lên object mới được tạo sau request đầu. Generation precondition giúp request chỉ có hiệu lực với trạng thái mà ứng dụng dự kiến.

Các ví dụ:

- Create-only upload với doesNotExist() chỉ thành công khi chưa có live object.
- Replace với generationMatch(expected) chỉ thành công nếu object vẫn là generation đã đọc.
- Delete với generationMatch(expected) chỉ xóa đúng generation đó.
- Metadata update với metagenerationMatch(expected) chỉ cập nhật metadata nếu nó chưa thay đổi.

Java Cloud Storage client hỗ trợ retry các lỗi tạm thời và chỉ tự retry những thao tác có tính idempotent theo cấu hình. Với các thao tác conditionally idempotent, truyền generation hoặc metageneration precondition tương ứng để SDK nhận biết điều kiện retry.

### 11.2. Bảng xử lý lỗi

| Status/lỗi | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| 200/201 | Request thành công | Lưu generation/metageneration trả về |
| 304 Not Modified | Điều kiện not-match không thỏa vì resource vẫn khớp giá trị so sánh | Dùng cache hiện có hoặc kết thúc lần tải |
| 404 Not Found | Object/version không tồn tại | Kiểm tra object name, generation và vòng đời |
| 403 Forbidden | Principal thiếu quyền hoặc policy từ chối | Kiểm tra IAM, retention/hold và policy |
| 412 Precondition Failed | Resource đã đổi so với giả định | Đọc lại trạng thái và xử lý conflict |
| 408/429/5xx | Lỗi tạm thời hoặc quá tải | Retry exponential backoff nếu operation idempotent |
| Timeout/mất kết nối | Không chắc server đã xử lý hay chưa | Kiểm tra trạng thái bằng generation/metadata trước khi quyết định retry |

Không retry vô hạn với 403 hoặc 412. 412 thường là tín hiệu có writer khác đã thay đổi object; đọc lại và quyết định nghiệp vụ. Nếu timeout xảy ra sau upload create-only, lần retry có thể trả 412 vì lần đầu đã thành công. Khi đó hãy đọc object và so sánh operation ID, size/checksum hoặc metadata do ứng dụng lưu để xác định request trước đã thành công hay một writer khác đã tạo object.

### 11.3. Exponential backoff

Với lỗi tạm thời như 408, 429, 500, 502, 503, 504 và lỗi kết nối, dùng exponential backoff có jitter. Giới hạn số lần retry hoặc tổng deadline. Không dùng retry để che lỗi permission hoặc xung đột dữ liệu.

## 12. Object Versioning, soft delete và precondition

Object Versioning giữ các generation cũ dưới dạng noncurrent version khi live object bị ghi đè hoặc xóa. Soft delete có thể giữ object đã xóa trong một khoảng thời gian. Retention policy và hold có thể ngăn xóa object trước thời hạn.

Các cơ chế này bổ sung khả năng khôi phục, nhưng không thay precondition:

- Generation match vẫn xác định đúng live generation hoặc generation cụ thể được yêu cầu.
- Versioning giúp giữ lại generation cũ nếu bucket được cấu hình phù hợp.
- Soft delete ảnh hưởng khả năng khôi phục object sau delete.
- Retention/hold có thể khiến delete thất bại dù generation match chính xác.
- ifGenerationMatch=0 kiểm tra live object; sự tồn tại của noncurrent version không nhất thiết chặn tạo live version mới.

Hãy xác định rõ nghiệp vụ cần “thay thế live object”, “giữ phiên bản cũ”, “ẩn tài liệu”, “xóa live object” hay “xóa vĩnh viễn”. Đây là các hành vi khác nhau.

## 13. Chi phí và hiệu năng

Precondition thường cần biết generation/metageneration hiện tại. Nếu ứng dụng chưa lưu các giá trị này, nó có thể phải gọi thêm một request đọc metadata trước thao tác chính.

Chi phí của cách làm này gồm:

- Thêm một round trip network và tăng latency.
- Thêm một operation tính phí và có thể thêm networking cost.
- Tăng tải cho Cloud Storage nếu mỗi request đều đọc metadata trước khi ghi.

Có thể giảm overhead bằng cách lưu generation/metageneration cùng document record sau mỗi lần tạo/cập nhật object. Chỉ dùng giá trị đã lưu nếu ứng dụng quản lý được consistency của record; khi database có thể stale, precondition vẫn bảo vệ object và trả 412 nếu token cũ.

Không bỏ precondition chỉ để giảm một request metadata trong các luồng có nguy cơ ghi đè/xóa nhầm. Đo latency và chọn nơi lưu version token phù hợp với yêu cầu nghiệp vụ.

## 14. Kiểm thử generation precondition

### 14.1. Unit test

Kiểm tra service truyền đúng precondition cho adapter:

- Upload mới phải dùng doesNotExist().
- Replace phải dùng generation đã lưu.
- Delete phải dùng generation của object đã được xác nhận.
- Metadata update phải dùng generation và metageneration.
- 412 được ánh xạ thành conflict nghiệp vụ.
- Timeout không tự động được coi là upload thất bại.
- Retry không được bỏ precondition.
- Controller không cho client tự gửi bucket hoặc generation tùy ý.

Mock có thể kiểm tra option được truyền vào SDK, nhưng không chứng minh hành vi Cloud Storage thật.

### 14.2. Integration test trên bucket riêng

1. Upload object bằng doesNotExist() và lưu generation.
2. Upload lại cùng tên bằng doesNotExist(); kỳ vọng 412.
3. Upload phiên bản mới với generation match hiện tại; kỳ vọng thành công.
4. Thử replace bằng generation cũ; kỳ vọng 412.
5. Thử delete bằng generation cũ sau khi object đã thay đổi; xác nhận live version mới còn nguyên.
6. Đọc metadata, cập nhật Content-Type với generation + metageneration match.
7. Cập nhật metadata bằng metageneration cũ; kỳ vọng 412.
8. Đọc generation hiện tại, thay bytes trước khi tải; xác minh read pinned generation không trộn dữ liệu.
9. Kiểm thử object versioning/soft delete nếu bucket test có bật các tính năng này.
10. Dọn object test và kiểm tra bucket không còn dữ liệu ngoài dự kiến.

### 14.3. Mô phỏng race condition

Dùng hai worker hoặc hai test thread:

- Cả hai cùng đọc generation G.
- Worker A cập nhật với generationMatch(G).
- Worker B cập nhật với generationMatch(G).
- Chỉ một worker được thành công; worker còn lại nhận 412.
- Worker B đọc lại generation mới rồi quyết định retry hoặc báo conflict.

Không kiểm thử bằng cách chỉ chạy tuần tự hai lệnh trong một thread; cần tạo điểm đồng bộ để cả hai worker cùng đọc một snapshot trước khi ghi.

## 15. Dùng gcloud để thử precondition

### 15.1. Chỉ tạo khi object chưa có

~~~bash
gcloud storage cp ./report.pdf \
  gs://training-documents-dev/reports/report.pdf \
  --if-generation-match=0
~~~

### 15.2. Ghi đè đúng generation đã đọc

~~~bash
gcloud storage cp ./report-updated.pdf \
  gs://training-documents-dev/reports/report.pdf \
  --if-generation-match=1234567890123456
~~~

### 15.3. Xem metadata và generation

~~~bash
gcloud storage objects describe \
  gs://training-documents-dev/reports/report.pdf
~~~

Các lệnh chỉ dùng để thực hành trên bucket test. Xác minh project, principal và bucket trước khi chạy. Không thử delete hoặc overwrite trên dữ liệu production.

## 16. So sánh với AWS S3 và Azure Blob Storage

| Khía cạnh | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Version token | Generation | Version ID, ETag | Version ID, ETag |
| Create-only | ifGenerationMatch=0 | Conditional request với If-None-Match: * hoặc cơ chế tương ứng | Conditional request với If-None-Match: * |
| Replace-if-unchanged | ifGenerationMatch | If-Match ETag hoặc version-aware request | If-Match ETag hoặc lease |
| Metadata update | ifGenerationMatch + ifMetagenerationMatch | ETag/version conditional headers | ETag conditional headers |
| Delete có điều kiện | Generation match | Version ID / conditional request | ETag condition / lease |
| Xung đột | HTTP 412 | HTTP 412 hoặc lỗi conditional theo API | HTTP 412 |

Các provider đều hỗ trợ conditional request nhưng token và semantics không hoàn toàn tương đương. Generation là version number của GCS; S3 Version ID và Azure version ID có mô hình riêng. ETag có thể dùng làm validator, nhưng không coi ETag là generation. Adapter đa cloud nên biểu diễn hành vi nghiệp vụ như create-if-absent, replace-if-version, update-metadata-if-current và delete-if-version; adapter từng provider ánh xạ sang precondition tương ứng.

## 17. Bài tập thực hành tổng hợp

**Bối cảnh:** Ứng dụng Spring Boot document-api lưu file theo tenant trong bucket training-documents-dev. Nhiều worker có thể cập nhật hoặc xóa cùng một tài liệu; người dùng cũng có thể upload phiên bản mới trong khi một job xử lý cũ vẫn đang chạy.

### Nhiệm vụ A — Hiểu version token

1. Upload một object và ghi nhận generation/metageneration.
2. Chỉ cập nhật Content-Type; quan sát metageneration thay đổi.
3. Upload bytes mới; quan sát generation thay đổi và metageneration bắt đầu lại.
4. Giải thích vì sao generation và metageneration giải quyết hai loại race khác nhau.

### Nhiệm vụ B — Create và replace

1. Upload object bằng doesNotExist().
2. Thử upload trùng object name và xử lý 412.
3. Đọc generation hiện tại.
4. Replace bằng generationMatch(expectedGeneration).
5. Thử replace bằng token cũ và trả conflict.

### Nhiệm vụ C — Delete và metadata update

1. Đọc object generation G.
2. Tạo phiên bản G+1.
3. Chạy delete với generation G; xác nhận không xóa G+1.
4. Đọc generation + metageneration rồi update metadata có cả hai điều kiện.
5. Mô phỏng một worker khác update metadata giữa hai request; xác nhận 412.

### Nhiệm vụ D — Retry và integration test

- Mô phỏng timeout sau upload và xác minh object trước khi retry.
- Test create-only retry không tạo bản ghi trùng.
- Test hai worker cùng cập nhật từ một generation.
- Test 412, 304, 403 và 404.
- Test bucket có Object Versioning hoặc soft delete.
- Kiểm tra IAM permission riêng cho create/get/delete.

**Tiêu chí đạt:** Ứng dụng ngăn được create trùng, overwrite từ snapshot cũ và delete nhầm generation; metadata update dùng đúng cặp generation/metageneration; xử lý 412 theo nghiệp vụ; và có integration test chứng minh race condition trên Cloud Storage.

## 18. Ghi nhớ

- Generation đại diện phiên bản bytes; metageneration đại diện phiên bản metadata của generation đó.
- ifGenerationMatch=0 là create-only precondition cho thao tác ghi object data; noncurrent versions có thể vẫn tồn tại.
- doesNotExist() là cách diễn đạt rõ ràng create-only trong Java Storage client.
- Replace và delete nên dùng generation đã đọc để chỉ tác động lên đúng phiên bản.
- Metadata update nên kết hợp generation-match và metageneration-match.
- Match precondition không thỏa thường trả 412; not-match precondition có thể trả 304.
- Precondition làm một số operation conditionally idempotent và giúp retry an toàn hơn.
- Preconditions không thay IAM, retention, hold hoặc authorization nghiệp vụ.
- Lưu version token cùng document record để giảm round trip; xử lý database/GCS consistency bằng state machine hoặc reconciliation.

### Tài liệu tham khảo

- [Request preconditions — Cloud Storage](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Retry strategy — Cloud Storage](https://docs.cloud.google.com/storage/docs/retry-strategy)
- [Storage Java interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Storage.BlobTargetOption Java API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobTargetOption)
- [Storage.BlobSourceOption Java API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobSourceOption)
- [Storage.BlobWriteOption Java API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobWriteOption)
- [Upload objects from a file system](https://docs.cloud.google.com/storage/docs/uploading-objects)
- [Upload objects from memory](https://docs.cloud.google.com/storage/docs/uploading-objects-from-memory)
- [Object Versioning — Cloud Storage](https://docs.cloud.google.com/storage/docs/object-versioning)
