# Metadata, phiên bản, tầng lưu trữ và vòng đời dữ liệu trong Azure Blob Storage

## 1. Bài toán và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành đưa ứng dụng Spring Boot kết nối các dịch vụ managed trên **AWS, Azure và Google Cloud**, sử dụng thư viện Spring Cloud/Azure SDK tương ứng, đồng thời cấu hình danh tính, quyền truy cập, bảo vệ secret và kiểm thử tích hợp. Bài này thuộc chương **Azure Storage** và trả lời một câu hỏi vận hành quan trọng: sau khi đã upload được blob, làm thế nào để **mô tả, theo dõi, khôi phục, chuyển tầng và xóa dữ liệu đúng thời điểm**?

Hãy xét hệ thống lưu hợp đồng của doanh nghiệp:

- Mỗi bản hợp đồng PDF được lưu vào container riêng tư `documents`.
- Ứng dụng cần biết file thuộc loại nào, có kích thước bao nhiêu và lần sửa cuối xảy ra khi nào.
- Khi người dùng ghi đè sai tài liệu, quản trị viên phải có khả năng khôi phục phiên bản trước.
- Tài liệu mới được truy cập thường xuyên; tài liệu cũ hầu như không đọc nhưng vẫn phải giữ trong vài năm.
- Sau thời hạn lưu giữ, dữ liệu có thể được xóa theo chính sách, trừ khi đang có yêu cầu giữ lại đặc biệt.

**Metadata, versioning, access tier và lifecycle management** giải quyết những phần khác nhau của bài toán. Chúng hỗ trợ nhau nhưng không thay thế cho **database nghiệp vụ, backup, authorization và kiểm thử khôi phục**.

Sau bài học, bạn có thể:

1. Phân biệt **system properties**, **user-defined metadata**, **blob index tags** và dữ liệu nghiệp vụ trong database.
2. Hiểu **ETag**, **version ID**, **snapshot**, **soft delete** và **immutability/retention**; chọn biện pháp bảo vệ phù hợp.
3. So sánh **Hot, Cool, Cold và Archive** theo tần suất truy cập, độ trễ, chi phí đọc và thời gian lưu giữ tối thiểu.
4. Viết **lifecycle management policy** chuyển tầng/xóa blob theo tuổi và biết giới hạn của cơ chế xử lý nền.
5. Áp dụng Spring Cloud Azure/Azure Storage SDK cho thao tác metadata, kiểm soát cập nhật đồng thời, đọc trạng thái tier và chuyển tier.
6. Thiết kế kiểm thử tích hợp, giám sát chi phí và tránh xóa/đưa vào Archive những tài liệu vẫn cần truy xuất nhanh.

## 2. Phân loại thông tin gắn với một blob

Một blob có **nội dung byte** (PDF, ảnh, video, dữ liệu export), **properties** do dịch vụ quản lý, **metadata** tùy chỉnh và có thể có **index tags**. Cần chọn đúng nơi lưu vì mỗi loại có cách truy cập và tìm kiếm khác nhau.

| Thành phần | Ví dụ | Nguồn/đặc tính | Dùng để |
|---|---|---|---|
| Nội dung blob | Byte của `contract-42.pdf` | Upload/download qua Blob API | Lưu tài liệu thật |
| **System properties** | `Content-Length`, `Content-Type`, `Last-Modified`, `ETag`, access tier | Storage quản lý hoặc cung cấp thao tác cập nhật phù hợp | Phục vụ HTTP, kiểm tra phiên bản, quan sát trạng thái |
| **Custom metadata** | `documentType=contract`, `source=portal` | Các cặp key-value do ứng dụng khai báo | Gắn mô tả kỹ thuật nhẹ, đọc cùng thuộc tính blob |
| **Blob index tags** | `department=finance`, `retentionClass=long` | Key-value có index phục vụ truy vấn/filter theo tính năng được hỗ trợ | Tìm và lọc blob theo tag; lọc chính sách lifecycle |
| **Database nghiệp vụ** | `ownerId`, `tenantId`, trạng thái duyệt, phân quyền | Ứng dụng quản lý, có schema/index/transaction riêng | Truy vấn nghiệp vụ, quan hệ dữ liệu, kiểm tra authorization |

Metadata của Blob **không phải một database có chỉ mục tìm kiếm theo mọi field**. Nếu cần tìm “tất cả hợp đồng của phòng kế toán được duyệt trong quý III”, hãy dùng database hoặc index dịch vụ chuyên dụng. Blob index tags có khả năng truy vấn riêng, nhưng vẫn có giới hạn về số lượng tag, kiểu dữ liệu, quyền và chi phí thao tác; không thay thế tất cả khả năng của database.

### 2.1. Những properties đáng quan tâm

Các thuộc tính thường cần đọc:

- **Content-Type**: loại MIME sử dụng khi tải về; ví dụ `application/pdf`. Không nên tin MIME do client khai báo mà không kiểm tra nội dung.
- **Blob size**: số byte của nội dung blob.
- **Last-Modified**: thời gian Storage ghi nhận lần sửa gần nhất của resource.
- **ETag**: token trạng thái cho yêu cầu có điều kiện `If-Match` hoặc `If-None-Match`.
- **Access tier**: tầng lưu trữ hiện tại hoặc thuộc tính tier liên quan đến trạng thái chuyển tầng.
- **Version ID**: mã định danh phiên bản khi versioning được bật và operation hỗ trợ.
- **Metadata map**: các cặp mô tả được gắn với blob.

ETag **không phải checksum hay version ID**: nó phục vụ so sánh điều kiện trên resource. Nếu muốn xác minh byte end-to-end, hãy lưu SHA-256 do ứng dụng tính và có quy trình kiểm tra riêng.

### 2.2. Metadata và blob index tags khác nhau thế nào?

Ví dụ một blob có:

~~~text
Blob name: documents/2026/contract-42.pdf
System property:
    Content-Type: application/pdf
    Content-Length: 284931
    ETag: "0x8E123456789ABCD"
Metadata:
    documentType: contract
    uploadChannel: portal
Index tags:
    department: finance
    retentionClass: long
Database:
    documentId: 42
    ownerId: user-117
    status: APPROVED
~~~

Đây là dữ liệu **minh họa**, không phải kết quả đọc một tài khoản Azure thật.

- **Metadata** thích hợp cho thông tin mô tả ít thay đổi, thường được biết khi đã có blob name. SDK trả metadata qua `getProperties()`.
- **Index tags** được Azure Storage lập chỉ mục để hỗ trợ tìm blob theo biểu thức tag khi tính năng và role cho phép. Azure lifecycle management có thể dùng tag filter bên cạnh prefix.
- **Database** giữ thông tin quyền truy cập, quan hệ nghiệp vụ và trạng thái quy trình. Không dùng metadata hay index tag làm **nguồn thẩm quyền duy nhất** để quyết định người dùng có quyền tải tài liệu.

Tên metadata phải tuân theo quy tắc của Azure Storage; tránh khoảng trắng, ký tự đặc biệt hoặc key không hợp lệ. Không đặt token, mật khẩu, thông tin định danh nhạy cảm vào metadata/tag vì chúng có thể hiện trong thao tác quản trị, SDK, log hoặc các kênh truy cập khác.

## 3. Thao tác metadata bằng Azure Storage SDK for Java

### 3.1. Đọc properties và metadata

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
BlobProperties properties = blob.getProperties();

System.out.println("Content-Type: " + properties.getContentType());
System.out.println("Số byte: " + properties.getBlobSize());
System.out.println("ETag: " + properties.getETag());
System.out.println("Sửa gần nhất: " + properties.getLastModified());
System.out.println("Access tier: " + properties.getAccessTier());
System.out.println("Metadata: " + properties.getMetadata());
~~~

`getProperties()` là một request tới Storage; không tải toàn bộ byte của PDF. Đối với file lớn, chỉ đọc properties để hiển thị thông tin là phù hợp hơn việc download blob vào RAM rồi đếm kích thước.

### 3.2. Ghi metadata

~~~java
import java.util.Map;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
blob.setMetadata(Map.of(
        "documentType", "contract",
        "uploadChannel", "portal"
));
~~~

**Điểm quan trọng:** `setMetadata(...)` **thay thế toàn bộ custom metadata hiện tại**, không đơn thuần bổ sung hai key mới. Ví dụ trên sẽ làm mất các key metadata khác nếu đã tồn tại. Metadata không làm thay đổi byte nội dung, nhưng sửa metadata là một thay đổi trạng thái resource và có thể tác động đến ETag/khả năng đồng thời.

### 3.3. Cập nhật metadata có điều kiện để không mất dữ liệu

Giả sử worker A thêm `documentType` còn worker B thêm `uploadChannel`. Nếu cả hai cùng đọc metadata cũ rồi gọi `setMetadata`, kết quả của thao tác đến sau có thể làm mất key mà thao tác trước vừa thêm.

Để bảo vệ, ta:

1. Đọc properties chứa **ETag và map metadata**.
2. Tạo bản sao map và chỉ sửa field mong muốn.
3. Gửi `setMetadataWithResponse` với **`BlobRequestConditions.setIfMatch(etag)`**.
4. Nếu Azure trả **412 Precondition Failed**, đọc lại trạng thái mới và **hợp nhất lại có kiểm soát**; không âm thầm ghi đè metadata cũ.

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;
import com.azure.storage.blob.models.BlobRequestConditions;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

public static void updateMetadataIfUnchanged(
        BlobClient blob, String key, String value) {

    BlobProperties before = blob.getProperties();
    Map<String, String> merged =
            new HashMap<>(before.getMetadata());
    merged.put(key, value);

    BlobRequestConditions conditions = new BlobRequestConditions()
            .setIfMatch(before.getETag());

    blob.setMetadataWithResponse(
            merged, conditions, Duration.ofSeconds(30), Context.NONE);
}
~~~

Đoạn code là **một lần cập nhật có điều kiện**. Trong ứng dụng thực, bắt `BlobStorageException`, xử lý 412 bằng logic retry có giới hạn **sau khi tải lại metadata** nếu thao tác hợp nhất an toàn; đừng xóa điều kiện `If-Match` để “hết lỗi”. Các cập nhật metadata thường xuyên có thể làm tăng tranh chấp với update nội dung; nếu đây là dữ liệu thay đổi liên tục, nên cân nhắc giữ tại database.

### 3.4. Gắn blob index tags

~~~java
import java.util.Map;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
blob.setTags(Map.of(
        "department", "finance",
        "retentionClass", "long"
));
~~~

Tags và metadata có API, giới hạn, quyền và mục đích khác nhau. `setTags` là thao tác thay thế tập tag theo API của dịch vụ; nếu cần duy trì tag cũ, phải thiết kế merge và xử lý concurrent update riêng. Không mặc định mọi storage account/blob type đều hỗ trợ đồng nhất các thao tác tag hoặc filter lifecycle; phải kiểm tra cấu hình và phiên bản SDK.

## 4. Versioning: giữ lịch sử khi blob bị thay đổi

Khi bật **Blob versioning** cho một storage account được hỗ trợ, Azure lưu các phiên bản trước của blob khi blob bị thay đổi theo những operation được áp dụng. Ứng dụng có thể truy cập dữ liệu đã ghi ở thời điểm trước và khôi phục nếu người dùng ghi đè nhầm.

~~~mermaid
flowchart TD
    N[Blob hiện tại: contract-42.pdf] --> C[Current version v3]
    N --> P2[Previous version v2]
    N --> P1[Previous version v1]
    C -->|Nội dung người dùng đang thấy| App[Spring Boot API]
    P2 -->|Chọn phiên bản muốn khôi phục| Restore[Quy trình restore]
    P1 -->|Audit/đối soát| Audit[Đánh giá lịch sử]
~~~

### 4.1. Version ID, ETag và snapshot

| Khái niệm | Cách hình thành | Giá trị chính |
|---|---|---|
| **Current blob** | Nội dung hiện hành của tên blob | Phục vụ request thường ngày |
| **Previous version** | Được Azure ghi nhận theo cơ chế versioning khi blob thay đổi | Truy cập/khôi phục nội dung trước đó |
| **Version ID** | ID do dịch vụ sinh để tham chiếu một phiên bản cụ thể | Đọc, sao chép hoặc quản lý phiên bản xác định |
| **Snapshot** | Bản chụp của blob tại thời điểm ứng dụng/yêu cầu quản trị tạo snapshot | Điểm khôi phục có chủ đích |
| **ETag** | Token trạng thái của resource hoặc phiên bản được yêu cầu | Điều kiện đồng thời trên thao tác đọc/ghi |

**Versioning và snapshots không tương đương nhau.** Versioning tạo lịch sử theo cơ chế dịch vụ đã cấu hình; snapshot cần một thao tác tạo rõ ràng. Đều có thể phát sinh chi phí lưu trữ. Azure Blob Storage versioning có giới hạn tương thích, chẳng hạn theo loại tài khoản, hierarchical namespace hoặc tính năng cụ thể; luôn kiểm tra điều kiện của account đang triển khai.

### 4.2. Ví dụ các lần ghi và version

~~~text
Thời điểm   Thao tác                         Kết quả minh họa
09:00       Upload v1 (10 trang)             Current = v1
09:15       Ghi đè PDF bằng v2 (12 trang)   Current = v2; v1 được giữ
09:20       Ghi đè nhầm bằng v3 (2 trang)   Current = v3; v1/v2 còn lịch sử
09:30       Chọn khôi phục v2                Sao chép v2 thành current mới (v4)
~~~

Khi cần khôi phục, quy trình nên chọn **đúng version ID** rồi dùng cơ chế copy/restore được Storage hỗ trợ để tạo **current version mới**, không sửa trực tiếp dữ liệu của previous version. Điều kiện sao chép, quyền đọc nguồn/ghi đích và trạng thái copy cần được kiểm tra. Không chỉ dựa vào nhãn “v2” trong ví dụ vì version ID thực được dịch vụ sinh.

### 4.3. Truy cập một phiên bản xác định

Azure Storage SDK for Java hỗ trợ client tham chiếu version riêng của blob. Ví dụ mô tả API:

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.OutputStream;

BlobClient current =
        container.getBlobClient("documents/2026/contract-42.pdf");
String versionId = "<version-id-do-azure-cung-cap>";

BlobClient older = current.getVersionClient(versionId);
// output là OutputStream đã được tạo và quản lý vòng đời ở bên gọi.
older.downloadStream(output);
~~~

Code giả định `versionId` đã được lấy từ API liệt kê versions và current account đã bật versioning phù hợp. Nếu bản SDK được chọn có overload khác cho thao tác truy cập phiên bản, hãy dùng đúng phương thức được tài liệu phiên bản đó hỗ trợ. Một previous version có thể có tier/trạng thái riêng; đừng mặc định mọi version đều online hoặc có thể đọc ngay.

**Không coi versioning là backup độc lập hoàn toàn**. Xóa tài khoản hoặc sự cố quyền quản trị, cấu hình retention sai, lifecycle policy xóa các version quá sớm vẫn có thể khiến dữ liệu không khôi phục được. Với dữ liệu quan trọng, cân nhắc phương án bảo vệ dữ liệu và khả năng phục hồi phù hợp bên ngoài cơ chế versioning.

## 5. Soft delete, snapshots, retention và immutability

Các cơ chế bảo vệ có mục tiêu khác nhau:

| Cơ chế | Mục tiêu | Khi hữu ích | Giới hạn |
|---|---|---|---|
| **Blob soft delete** | Cho phép khôi phục blob hoặc bản liên quan đã bị xóa trong thời hạn cấu hình | Lỡ tay xóa file | Hết hạn retention hoặc các thao tác không hỗ trợ khôi phục sẽ không cứu được |
| **Blob versioning** | Giữ các phiên bản cũ sau cập nhật | Overwrite nhầm, theo dõi lịch sử nội dung | Tăng dữ liệu lưu; chính sách lifecycle có thể xóa version |
| **Snapshot** | Tạo điểm khôi phục tại thời điểm chỉ định | Trước migration/chuyển đổi quan trọng | Phải tạo và quản lý riêng |
| **Container soft delete** | Hỗ trợ khôi phục container vô tình bị xóa trong khoảng giữ lại | Sự cố thao tác quản trị | Khác phạm vi với soft delete của blob |
| **Immutability policy / legal hold** | Hạn chế thay đổi/xóa dữ liệu theo chính sách lưu giữ | Dữ liệu phải chống sửa/xóa trong thời hạn quy định | Có thể ngăn lifecycle delete và thao tác quản trị thường ngày |

**Soft delete không ngăn người có quyền gửi lệnh xóa**; nó giúp khôi phục theo chính sách. **Immutability** mới là cơ chế áp đặt hạn chế thay đổi/xóa khi yêu cầu lưu giữ phù hợp. Để đáp ứng một quy định cụ thể, cần xác minh kiểu policy, phạm vi, trạng thái lock và quy trình vận hành, không tự coi tính năng mặc định đã bảo đảm tuân thủ.

### 5.1. Ví dụ thiết kế bảo vệ cho hợp đồng

- Bật **versioning** để tránh mất nội dung khi overwrite.
- Bật **blob soft delete** trong khoảng đủ cho thời gian phát hiện/xử lý sự cố.
- Áp dụng **lifecycle policy** cho versions cũ để chi phí không tăng vô hạn, nhưng không đặt thời hạn xóa ngắn hơn yêu cầu khôi phục.
- Với hồ sơ phải giữ bất biến, xem xét **immutable storage** và tách container/prefix theo chính sách.
- Thường xuyên **thử phục hồi** một blob hoặc previous version trên môi trường không có dữ liệu nhạy cảm.

Versioning, soft delete và immutability có thể tương tác; một policy phù hợp riêng lẻ chưa chắc tạo ra hành vi mong muốn khi kết hợp. Kiểm thử theo cấu hình account thực, đặc biệt là thao tác delete, restore và archive.

## 6. Access tier: Hot, Cool, Cold và Archive

**Azure Blob Storage access tiers** tối ưu tổng chi phí giữa lưu trữ và truy cập. Với block blob trên loại storage account hỗ trợ, thường xét:

| Tier | Truy cập dữ liệu | Mẫu sử dụng phù hợp | Đánh đổi chính |
|---|---|---|---|
| **Hot** | Online, đọc trực tiếp | Dữ liệu mới, thường xuyên truy cập | Giá lưu theo dung lượng thường cao hơn các online tier lạnh hơn |
| **Cool** | Online, đọc trực tiếp | Dữ liệu ít đọc, cần truy xuất nhanh khi cần | Phí truy cập/lấy dữ liệu và minimum retention cao hơn Hot |
| **Cold** | Online, đọc trực tiếp | Dữ liệu rất ít đọc nhưng vẫn cần phản hồi online | Giá lưu thấp hơn, chi phí access/retrieval cao hơn Cool; yêu cầu giữ tối thiểu dài hơn |
| **Archive** | **Offline**; phải rehydrate trước khi đọc nội dung theo cách thông thường | Lưu trữ dài hạn rất ít truy cập | Truy xuất cần quy trình rehydrate, độ trễ có thể tính bằng giờ và phát sinh phí |

Không có quy tắc “càng lạnh càng rẻ” cho **tổng chi phí**. Archive có chi phí lưu mỗi GiB thấp nhưng nếu phải truy xuất nhiều lần hoặc liên tục chuyển tầng, tổng phí retrieval, operation và thời gian chờ có thể lớn hơn Hot.

### 6.1. Minimum retention và early deletion charge

Đối với các tier được cung cấp với cơ chế tính phí thông dụng, thời hạn lưu giữ tối thiểu thường là:

- **Hot:** không có yêu cầu tối thiểu theo cơ chế early deletion của các tier lạnh.
- **Cool:** khoảng **30 ngày**.
- **Cold:** khoảng **90 ngày**.
- **Archive:** khoảng **180 ngày**.

Nếu xóa hoặc chuyển blob ra khỏi tier trước mốc tối thiểu, có thể phát sinh **early deletion charge** cho phần thời gian còn thiếu. Các giá trị trên là mốc hướng dẫn để lập phương án; phải xác nhận trong **Azure pricing** áp dụng tại region, redundancy, loại tài khoản và thời điểm triển khai. Không tạo chính sách chuyển tier “mỗi tuần một lần” mà bỏ qua chi phí này.

### 6.2. Trường hợp Archive

Một blob ở tier **Archive** không thể được đọc nội dung trực tiếp như một blob Hot/Cool/Cold. Cần **rehydrate** bằng cách chuyển sang một online tier được hỗ trợ hoặc thực hiện thao tác copy/rehydrate phù hợp. Quá trình này là **bất đồng bộ**, có thể mất nhiều giờ và phụ thuộc ưu tiên xử lý, kích thước blob cũng như đặc tính dịch vụ.

Khi thiết kế API download:

1. Đọc properties/tier của blob.
2. Nếu tier online, cho phép download theo quyền và chính sách nghiệp vụ.
3. Nếu đang Archive, tạo **restore request/job** hoặc quy trình rehydrate.
4. Trả trạng thái **PENDING_REHYDRATION** và thông báo kỳ vọng cho người dùng thay vì cố mở stream và báo “404”.
5. Theo dõi trạng thái rehydrate, xử lý lỗi/timeout và chỉ phát hành link tải khi blob đã online.

Nhớ rằng phần dữ liệu còn trong Archive có thể bị tính phí rehydrate và phí lưu giữ tối thiểu; việc chuyển tier không thay thế chính sách quyền truy cập.

### 6.3. Chọn tier theo vòng đời sản phẩm

~~~mermaid
flowchart LR
    N[File mới tạo] --> H[Hot: truy cập nhiều]
    H -->|Sau thời gian ít dùng| C[Cool: online, ít đọc]
    C -->|Tiếp tục ít đọc| D[Cold: online, rất ít đọc]
    D -->|Lưu dài hạn không cần đọc nhanh| A[Archive: offline]
    A -->|Yêu cầu khôi phục| R[Rehydrate về online tier]
    R --> U[Cho phép đọc sau khi sẵn sàng]
~~~

Đây là lộ trình **có thể lựa chọn**, không phải mọi blob buộc phải đi qua đủ bốn tier. Các tài liệu giao dịch đang được xử lý có thể ở Hot lâu; sao lưu dài hạn có thể chuyển từ Hot/Cool sang Archive khi chính sách và hỗ trợ dịch vụ cho phép.

## 7. Tầng lưu trữ ở cấp account và cấp blob

Với storage account có hỗ trợ access tiers:

- Có thể có **default access tier** ở cấp account cho blob chưa có tier được đặt riêng.
- Có thể đặt **tier cụ thể** cho từng block blob, trong giới hạn tính năng của loại account.
- **Blob properties** cho biết trạng thái tier hiện tại; trạng thái rehydration có thể được biểu diễn bằng các properties bổ sung khi đang chuyển từ Archive.
- Một số cấu hình **premium storage**, hierarchical namespace, page/append blob hoặc tính năng đặc biệt không có cùng cơ chế tier như **standard block blob**. Không giả định mọi storage account hỗ trợ Archive.

Ví dụ Azure Java SDK:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.AccessTier;

BlobClient blob = container.getBlobClient("documents/2026/contract-42.pdf");
blob.setAccessTier(AccessTier.COOL);

var current = blob.getProperties();
System.out.println("Tier hiện tại: " + current.getAccessTier());
~~~

Lệnh này **thay đổi trạng thái lưu trữ và có thể phát sinh chi phí**; chỉ chạy khi nghiệp vụ/quy trình vận hành đã quyết định chuyển tier. Không đặt `setAccessTier` trong luồng mỗi lần người dùng download vì sẽ gây thao tác dư và thay đổi chi phí ngoài dự kiến.

Nếu chuyển từ Archive về online, đừng kỳ vọng `setAccessTier(AccessTier.HOT)` đồng nghĩa có thể đọc ngay trong cùng request. Ứng dụng cần theo dõi trạng thái rehydration trước khi trả nội dung.

## 8. Lifecycle management: tự động chuyển tier và xóa

**Azure Blob Storage lifecycle management** cho phép áp dụng policy theo điều kiện như **tuổi blob**, **prefix** và **index tags** (khi được hỗ trợ), để chuyển tier hoặc xóa dữ liệu cũ. Policy giúp giảm thao tác thủ công nhưng là **công việc nền**, không phải một scheduler đảm bảo sẽ hoàn thành đúng phút thứ 30 của ngày.

### 8.1. Một chính sách mẫu

Giả sử container `documents` có những file hoạt động mạnh trong 30 ngày đầu, ít được đọc sau ba tháng và lưu trữ dài hạn sau một năm:

- Sau **30 ngày** kể từ lần sửa cuối: chuyển **Cool**.
- Sau **90 ngày**: chuyển **Cold**.
- Sau **365 ngày**: chuyển **Archive**, nếu blob đủ điều kiện.
- Sau **730 ngày**: xóa blob hiện hành **nếu yêu cầu lưu giữ cho phép**.
- Previous versions và snapshots được quản lý bằng thời hạn riêng.

Ví dụ JSON policy ở dạng khai báo Azure Storage Lifecycle Management:

~~~json
{
  "rules": [
    {
      "enabled": true,
      "name": "documents-retention",
      "type": "Lifecycle",
      "definition": {
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["documents/"]
        },
        "actions": {
          "baseBlob": {
            "tierToCool": {
              "daysAfterModificationGreaterThan": 30
            },
            "tierToCold": {
              "daysAfterModificationGreaterThan": 90
            },
            "tierToArchive": {
              "daysAfterModificationGreaterThan": 365
            },
            "delete": {
              "daysAfterModificationGreaterThan": 730
            }
          },
          "snapshot": {
            "delete": {
              "daysAfterCreationGreaterThan": 180
            }
          },
          "version": {
            "delete": {
              "daysAfterCreationGreaterThan": 365
            }
          }
        }
      }
    }
  ]
}
~~~

**Đây là ví dụ minh họa**, không phải policy mặc định nên áp dụng vào production. Hãy xác nhận tính tương thích của **tierToCold, version action và các điều kiện** với storage account/region/API đang dùng. Với dữ liệu có retention dài hơn, điều chỉnh tuổi xóa cho đúng yêu cầu. Không triển khai nguyên mẫu xóa 730 ngày cho tài liệu cần lưu 5–10 năm.

### 8.2. Cách Azure đánh giá các điều kiện

- **`baseBlob`** áp dụng cho blob hiện hành; hành động chọn theo tuổi và policy.
- **`snapshot`** và **`version`** là tài nguyên riêng có hành động riêng. Xóa base blob không đồng nghĩa phải xóa version/snapshot theo cùng mốc thời gian.
- **`prefixMatch`** lọc theo **container/prefix blob name**; `documents/` nhắm vào tên thuộc container `documents`. Tên cần kiểm tra trước khi áp dụng policy diện rộng.
- **Blob index tags** cho phép lọc trên tag khi account/tính năng hỗ trợ; phù hợp phân biệt `retentionClass=short` và `retentionClass=long` mà không cần tạo hàng loạt container.
- **Tuổi theo modification** khác **tuổi từ khi tạo**. Thao tác cập nhật có thể đổi mốc tính tuổi của base blob; không nên mặc định “file đã upload ba năm thì tự xóa” nếu liên tục có thay đổi làm mới modified time.

Lifecycle chạy bất đồng bộ; cách áp dụng khi **nhiều rule đồng thời** có thể phụ thuộc thứ tự/ưu tiên logic của dịch vụ. Thiết kế rule rõ ràng, tránh cấu hình xung đột và kiểm thử trên tập tài nguyên test trước khi bật diện rộng.

### 8.3. Khác biệt giữa lifecycle và cron job trong Spring Boot

| Tiêu chí | Azure lifecycle policy | Spring Boot scheduled job |
|---|---|---|
| Nơi thực thi | Dịch vụ Azure Storage | Ứng dụng/worker của bạn |
| Dựa vào | Tuổi, prefix, tag và action được Azure hỗ trợ | Mọi quy tắc nghiệp vụ mà code truy vấn được |
| Điểm mạnh | Quản lý dữ liệu lớn mà không cần app liệt kê/xóa từng blob | Kiểm tra database, phê duyệt, ngoại lệ và quy trình nghiệp vụ |
| Giới hạn | Không thể biểu diễn mọi logic như “chỉ xóa sau khi hợp đồng kết thúc và đã duyệt” | Phải vận hành scheduler, xử lý paging, retry, tính đúng quyền và trạng thái |

Một thiết kế tốt có thể kết hợp hai cơ chế: app quyết định **retentionClass**/điều kiện nghiệp vụ; lifecycle xử lý quy tắc kỹ thuật đơn giản theo tuổi/tier; một job đối soát phát hiện dữ liệu không còn được tham chiếu hoặc hành động bị chặn bởi policy.

## 9. Ví dụ Spring Boot quản lý metadata và tier

### 9.1. Maven dependencies

Khi dùng Spring Cloud Azure, chọn **BOM tương thích với phiên bản Spring Boot** của dự án. Không cố định phiên bản ngẫu nhiên:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure.version` phải được định nghĩa ở POM hoặc dependency management tương ứng.

### 9.2. application.yml

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  blob:
    documents-container: ${DOCUMENTS_CONTAINER:documents}
~~~

Ví dụ sử dụng Azure Identity mặc định theo cấu hình Spring Cloud Azure. Trên Azure, ưu tiên **managed identity**; local có thể dùng developer identity qua Azure CLI. Storage account/container phải được provision trước. Không đưa account key, client secret, SAS vào Git.

### 9.3. Service đọc thông tin và gắn metadata có điều kiện

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.AccessTier;
import com.azure.storage.blob.models.BlobProperties;
import com.azure.storage.blob.models.BlobRequestConditions;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentBlobLifecycleService {
    private final BlobContainerClient container;

    public DocumentBlobLifecycleService(
            BlobServiceClient serviceClient,
            @Value("${app.blob.documents-container}") String containerName) {
        this.container = serviceClient.getBlobContainerClient(containerName);
    }

    public BlobSummary describe(String authorizedBlobName) {
        BlobProperties props = blob(authorizedBlobName).getProperties();
        return new BlobSummary(
                props.getBlobSize(),
                props.getContentType(),
                props.getETag(),
                String.valueOf(props.getAccessTier()),
                props.getMetadata());
    }

    public void updateDocumentType(
            String authorizedBlobName, String documentType) {
        BlobClient target = blob(authorizedBlobName);
        BlobProperties old = target.getProperties();

        Map<String, String> merged = new HashMap<>(old.getMetadata());
        merged.put("documentType", documentType);

        BlobRequestConditions condition = new BlobRequestConditions()
                .setIfMatch(old.getETag());
        target.setMetadataWithResponse(
                merged, condition, Duration.ofSeconds(30), Context.NONE);
    }

    // Chỉ gọi khi chính sách vận hành đã cho phép chuyển tier.
    public void moveToCool(String authorizedBlobName) {
        blob(authorizedBlobName).setAccessTier(AccessTier.COOL);
    }

    private BlobClient blob(String authorizedBlobName) {
        return container.getBlobClient(authorizedBlobName);
    }

    public record BlobSummary(
            long size, String contentType, String etag,
            String tier, Map<String, String> metadata) {
    }
}
~~~

**Giới hạn chủ đích của ví dụ:** `authorizedBlobName` phải được lấy **sau khi tầng ứng dụng kiểm tra documentId, owner/tenant và quyền truy cập**; không cho client truyền blob name tự do rồi gọi service. Ví dụ chưa bắt lỗi 412, chưa có phân quyền thao tác tier và chưa quản lý workflow rehydration. Đây là service minh họa cơ chế SDK, không phải endpoint quản trị production hoàn chỉnh.

Ứng dụng thật nên tách **API đọc properties**, **API cập nhật metadata nghiệp vụ**, **tác vụ quản trị tier/retention** với các identity/role phù hợp. Quyền ghi/xóa Blob không đồng nghĩa người dùng web được tự chọn tier hoặc yêu cầu xóa dữ liệu.

## 10. Thiết kế vòng đời end-to-end

Một cách tổ chức hệ thống lưu hợp đồng theo nhiều giai đoạn:

~~~mermaid
flowchart TD
    U[Người dùng upload PDF] --> A[Spring Boot API]
    A -->|Blob + metadata kỹ thuật| B[(Private Blob Container)]
    A -->|documentId, owner, retentionClass| DB[(Database)]
    B --> V[Versioning + Soft Delete]
    DB --> P[Quy tắc nghiệp vụ giữ/xóa]
    P --> L[Lifecycle Policy theo prefix/tag/tuổi]
    L --> T{Tầng lưu trữ}
    T --> H[Hot / Cool / Cold: online]
    T --> AR[Archive: offline]
    AR -->|Khi cần đọc lại| R[Rehydration job]
    R --> H
    P --> X[Kiểm tra chính sách retention/hold trước khi xóa]
~~~

### 10.1. Các quyết định nghiệp vụ trước khi dùng policy

1. **Phân loại dữ liệu:** tài liệu thường dùng, tệp đã đóng hồ sơ, dữ liệu phải giữ vì quy định hoặc file tạm.
2. **Xác định chủ sở hữu và ngày hết hạn nghiệp vụ:** lưu trong database; không suy đoán chỉ từ tên file hoặc ngày upload.
3. **Chọn prefix/container/tags:** ví dụ `documents/active/` và `documents/archive-eligible/` hoặc `retentionClass=long`.
4. **Bật cơ chế bảo vệ:** versioning, soft delete, backup/restore, immutability khi phù hợp.
5. **Thiết kế policy tier và delete:** xét truy cập, SLA khôi phục, early deletion và yêu cầu giữ tối thiểu.
6. **Kiểm thử chính sách bằng dữ liệu giả lập có tuổi và các version/snapshot:** xác nhận trước khi áp dụng cho production.
7. **Giám sát thường xuyên:** tình trạng tier, khả năng rehydrate, dung lượng phiên bản cũ, chi phí storage/transactions và số lỗi đọc Archive.

Một **retentionClass** có ý nghĩa nghiệp vụ nên được xác định từ quy tắc có kiểm soát. Không cho người dùng tự gửi `retentionClass=short` để được xóa hợp đồng sớm, cũng không chỉ kiểm tra tag khi quyết định tuân thủ yêu cầu pháp lý.

### 10.2. Khôi phục tài liệu đã bị ghi đè

Luồng khuyến nghị:

1. Người dùng báo sai nội dung và cung cấp `documentId`.
2. Backend kiểm tra quyền của người yêu cầu và quy trình phê duyệt khôi phục.
3. Quản trị viên liệt kê các version (theo blob name) với version ID và thời điểm tương ứng.
4. Xác minh nội dung đúng ở version cũ, kiểm tra tier/trạng thái online của version đó.
5. Copy/restore version được chọn thành current mới **theo operation có điều kiện** nếu cần tránh ghi đè một thay đổi vừa phát sinh.
6. Ghi audit log `documentId`, actor, version nguồn, current version/ETag mới và lý do.

Không xóa tất cả versions cũ chỉ vì “đã khôi phục thành công”; chúng có thể cần cho kiểm tra lịch sử hoặc rollback tiếp.

## 11. Xác thực, phân quyền và bảo vệ dữ liệu

| Thành phần | Quyền cần kiểm tra | Rủi ro nếu cấu hình sai |
|---|---|---|
| API tải/đọc properties | `Storage Blob Data Reader` tại scope phù hợp | Rò rỉ nội dung/metadata giữa tenant |
| API ghi metadata/upload | `Storage Blob Data Contributor` hoặc vai trò custom phù hợp | Có thể sửa/xóa blob vượt yêu cầu nghiệp vụ |
| Job thay đổi tier/xóa | Data-plane permission cho thao tác tương ứng, giới hạn scope | Chuyển Archive hoặc xóa hàng loạt do logic sai |
| Lifecycle policy quản trị | Management-plane quyền cấu hình lifecycle cho storage account | Tác động rộng lên nhiều container/blob/version |
| Người dùng cuối | Authorization của ứng dụng theo documentId/owner/tenant | Biết blob name nhưng không được phép đọc |
| Azure Files / Queue | Vai trò và ngữ nghĩa riêng theo service | Nhầm rằng Blob RBAC áp dụng tự động cho Files/Queue |

Ưu tiên **Microsoft Entra ID + managed identity** cho ứng dụng trên Azure. Nếu phát hành URL **SAS** để tải trực tiếp, cấp quyền đọc cho **đúng blob**, thời hạn ngắn và thông qua backend đã kiểm tra authorization; không log SAS hoặc cấp tài khoản key cho client.

**Immutability policy/legal hold** có thể ngăn xóa hoặc thay đổi ngay cả khi một principal có role Blob Data Contributor. Chúng là lớp bảo vệ khác với IAM. Storage firewall/private endpoint và TLS cũng độc lập với role RBAC; có quyền đúng vẫn có thể bị chặn bởi network.

## 12. Chi phí, độ trễ và quan sát vận hành

Quyết định tier/lifecycle nên dựa vào **tổng chi phí**:

~~~text
Tổng chi phí gần đúng =
    dung lượng lưu theo tier và thời gian
  + số request đọc/ghi/list/đổi tier
  + chi phí retrieval/rehydration (nếu có)
  + early deletion charge (nếu vi phạm minimum retention)
  + network egress và các chi phí vận hành liên quan
~~~

Ví dụ cùng một tệp 100 GiB:

- Đọc hàng ngày cho API analytics → Hot có thể phù hợp vì tần suất read lớn.
- Đọc 1–2 lần/quý, cần trả kết quả ngay → Cool/Cold đáng đánh giá.
- Lưu 7 năm, rất hiếm đọc, chấp nhận chờ vài giờ khi phục hồi → Archive có thể tối ưu lưu trữ, nhưng cần workflow rehydrate và dự trù phí.

Không so sánh chỉ bằng **đơn giá GiB/tháng**. Hãy ước lượng số lần truy xuất, dữ liệu đọc ra, tần suất ghi lại và khả năng phải chuyển ngược tier. Bảng giá thay đổi theo region, redundancy, account type và thời điểm, vì vậy cần lấy **Azure Pricing Calculator** và dữ liệu sử dụng thực tế để tính ngân sách.

Các chỉ số nên đo:

- Tổng dung lượng Blob theo container, tier và số lượng current/previous versions.
- Số thao tác list/read/write/delete, tỉ lệ lỗi `403`, `404`, `409`, `412` và `5xx`.
- Số blob đang Archive, số job rehydrate đang chờ và thời gian hoàn tất.
- Chi phí theo tier, phí retrieval, phí early deletion và lượng egress.
- Lượng orphan blob do database ghi lỗi hoặc upload bỏ dở.
- Tỷ lệ khôi phục thành công và thời gian RTO thực tế khi thử restore.

## 13. Kiểm thử tích hợp và các lỗi thường gặp

### 13.1. Test với Azurite và Azure thật

**Azurite** hữu ích để kiểm tra một số API Blob cơ bản ở local. Tuy nhiên, nó **không mô phỏng đầy đủ** tất cả behavior của versioning, lifecycle management, Archive/rehydration, IAM managed identity, firewall/private endpoint và tính phí thực tế. Vì thế phải tách hai lớp:

- **Local/unit/integration test:** kiểm tra logic metadata, blob name, upload/download, điều kiện ETag và xử lý lỗi API thông dụng bằng Azurite/SDK.
- **Azure integration test:** dùng account test riêng để kiểm tra versioning, soft delete, tier, lifecycle policy, rehydrate, data-plane RBAC, private endpoint và hoạt động khi policy chạy nền.

Không chạy thử chính sách delete trên storage account production. Dùng prefix/container riêng, dữ liệu không nhạy cảm, thời hạn lifecycle ngắn cho thí nghiệm (nếu môi trường cho phép) và dọn tài nguyên theo quy trình an toàn.

### 13.2. Ma trận kiểm thử

| Trường hợp | Điều cần xác minh |
|---|---|
| Gắn metadata mới | Properties trả đúng key-value; không lộ dữ liệu nhạy cảm |
| Hai worker cùng cập nhật metadata | Một request nhận 412 khi ETag thay đổi; merge không làm mất key cũ |
| Cập nhật HTTP headers | Nội dung và header sau update đúng; biết tác động tới ETag và các header khác |
| Upload/overwrite khi versioning bật | Previous version truy xuất/khôi phục được theo version ID |
| Xóa nhầm khi soft delete bật | Có thể phục hồi trong retention window đã cấu hình |
| Đến mốc chuyển Cool/Cold | Tier được chuyển khi lifecycle áp dụng; không dùng mốc chạy đến phút chính xác |
| Chuyển vào Archive | Download trực tiếp bị hạn chế, app báo trạng thái restore phù hợp |
| Yêu cầu đọc blob Archive | Rehydrate được theo workflow và cập nhật trạng thái khi online |
| Lifecycle xóa version/snapshot | Chỉ dữ liệu đáp ứng rule bị ảnh hưởng; retention và hold được tôn trọng |
| Principal thiếu quyền | Không thể sửa metadata/tier/xóa nếu RBAC không cho phép |
| Policy áp dụng sai prefix | Test phát hiện trước khi deploy và không làm mất dữ liệu ngoài dự tính |
| Database lỗi sau upload | Có đối soát blob mồ côi và quy tắc giữ/xóa an toàn |

### 13.3. Bảng lỗi chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `403 Forbidden` | Thiếu RBAC, SAS hết hạn, firewall/Shared Key policy | Kiểm tra principal, role/scope, credential, network |
| `404 Not Found` | Sai account/container/blob name hoặc chỉ còn previous version | Kiểm tra resource, version list, soft delete, trạng thái current |
| `412 Precondition Failed` | ETag đã thay đổi, cập nhật metadata/HTTP properties xung đột | Đọc lại, merge theo nghiệp vụ, retry có giới hạn |
| Metadata cũ biến mất | `setMetadata` ghi đè toàn bộ map | Lấy/merge đầy đủ và dùng If-Match |
| Không thể tải blob Archive | Blob offline, chưa rehydrate xong | Tạo job, theo dõi trạng thái, trả kết quả khi online |
| Chi phí tăng đột biến | Nhiều versions/snapshots, tier sai, retrieval và early deletion | Đo theo tier/operation, điều chỉnh policy sau phân tích |
| Không xóa được blob dù có Contributor | Immutable policy, legal hold, lease hoặc quyền khác | Kiểm tra policy/lease và điều kiện storage operation |
| Lifecycle không chuyển ngay | Engine chạy nền, điều kiện chưa đạt, account không hỗ trợ hoặc bị policy khác tác động | Kiểm tra rule, prefix/tags, modified time, trạng thái tier, log và giới hạn dịch vụ |

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — Hợp đồng cần giữ 5 năm:** Tài liệu được đọc liên tục trong 30 ngày đầu, sau đó chỉ đọc vài lần mỗi năm. Hãy thiết kế prefix/tag và lộ trình Hot → Cool/Cold → Archive, đồng thời bảo đảm không xóa trước 5 năm và vẫn hỗ trợ khôi phục theo yêu cầu.

**Tình huống B — Hai job sửa metadata:** Job OCR ghi `ocrStatus=READY`, job phân loại ghi `documentType=contract`. Cả hai đọc cùng ETag cũ. Hãy dùng `If-Match` để tránh mất một field và mô tả cách retry/merge khi nhận 412.

**Tình huống C — Ghi đè PDF nhầm:** Versioning đã bật, current bị sửa sai nhưng previous version đúng. Hãy thiết kế quy trình chọn version ID, xác minh quyền khôi phục, copy nội dung thành current mới và lưu audit log.

**Tình huống D — Download file Archive:** Người dùng cần ngay một tài liệu 6 năm trước, trong khi blob đang Archive. Hãy giải thích vì sao endpoint không thể trả nội dung tức thì, cách tạo trạng thái `PENDING_REHYDRATION` và cơ chế thông báo sau khi khôi phục.

**Tình huống E — Đa đám mây:** So sánh Azure Blob metadata/index tags/lifecycle với **Amazon S3 object metadata, object tags, versioning, storage classes** và **Google Cloud Storage custom metadata, object generations, storage classes, lifecycle rules**. Tập trung vào **nguyên tắc**; tên API, chính sách retention, tầng lưu và cách áp dụng điều kiện khác nhau theo provider.

### Tự kiểm tra

1. **Metadata có thay thế database truy vấn nghiệp vụ không?** Không. Metadata mô tả object; database vẫn cần cho quan hệ, chủ sở hữu, quyền và truy vấn phức tạp.
2. **`setMetadata` có thêm một key mà giữ nguyên mọi key cũ không?** Không mặc định; phải merge và ghi lại map, dùng ETag để tránh lost update.
3. **ETag có giống version ID hoặc SHA-256 không?** Không. ETag phục vụ điều kiện trạng thái, version ID tham chiếu một phiên bản và SHA-256 kiểm tra byte.
4. **Versioning có làm cho mọi trường hợp xóa đều phục hồi được mãi mãi không?** Không. Policy, quyền quản trị, thời hạn giữ và khả năng tương thích vẫn ảnh hưởng đến phục hồi.
5. **Blob Archive có đọc ngay như Hot không?** Không. Archive offline và thường cần rehydrate bất đồng bộ.
6. **Vì sao có phí early deletion?** Cool/Cold/Archive thường có thời gian lưu tối thiểu; chuyển ra hoặc xóa trước hạn có thể bị tính thêm.
7. **Lifecycle chạy chính xác vào 00:00 ngày đủ 90 ngày không?** Không. Đây là cơ chế xử lý nền, nên thiết kế có độ trễ và theo dõi trạng thái.
8. **Chính sách lifecycle có thay thế immutable retention không?** Không. Lifecycle quản lý chuyển/xóa theo điều kiện; immutability áp đặt hạn chế sửa/xóa khi luật/nhu cầu bắt buộc.
9. **Bật Blob Data Contributor có đủ bảo đảm người dùng web chỉ xem tài liệu của họ không?** Không. Backend phải kiểm tra owner/tenant và chỉ cấp SAS/stream sau khi được phép.

## 15. Tổng kết

Trong Azure Blob Storage, **properties và metadata** mô tả object, **index tags** giúp lọc theo nhãn, **ETag** bảo vệ cập nhật có điều kiện, còn **versioning/snapshots/soft delete** hỗ trợ khôi phục. **Hot/Cool/Cold/Archive** tối ưu những kiểu truy cập khác nhau và **lifecycle management** tự động hóa chuyển tier hoặc xóa theo chính sách. Mỗi chức năng có giới hạn và chi phí; cần thiết kế chúng dựa trên **yêu cầu lưu giữ, SLA truy xuất, quyền truy cập, kế hoạch phục hồi và mức sử dụng thực tế**.

Trong Spring Boot, sử dụng Spring Cloud Azure và Azure Storage SDK để đọc properties, cập nhật metadata có `If-Match` và điều chỉnh tier qua service có phân quyền. Khi chuyển sang AWS S3 hoặc Google Cloud Storage, cách tổ chức object/version/storage class có nét tương đồng nhưng **IAM, API, lifecycle và các ràng buộc tính phí khác nhau**, vì vậy cần kiểm chứng riêng cho từng provider.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Set and retrieve properties and metadata for blobs](https://learn.microsoft.com/azure/storage/blobs/storage-blob-properties-metadata)
- [Microsoft Learn — Manage and find Azure Blob data with blob index tags](https://learn.microsoft.com/azure/storage/blobs/storage-manage-find-blobs)
- [Microsoft Learn — Blob versioning](https://learn.microsoft.com/azure/storage/blobs/versioning-overview)
- [Microsoft Learn — Soft delete for blobs](https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview)
- [Microsoft Learn — Azure Blob Storage access tiers](https://learn.microsoft.com/azure/storage/blobs/access-tiers-overview)
- [Microsoft Learn — Rehydrate an archived blob](https://learn.microsoft.com/azure/storage/blobs/archive-rehydrate-overview)
- [Microsoft Learn — Lifecycle management policies](https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-overview)
- [Microsoft Learn — Azure Blob Storage client library for Java](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
