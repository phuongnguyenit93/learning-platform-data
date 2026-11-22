# Azurite và quy trình phát triển Storage tại máy cá nhân

## 1. Bài toán phát triển Azure Storage ở máy cá nhân

Trong một ứng dụng triển khai trên Microsoft Azure, dữ liệu không nhất thiết chỉ nằm trong cơ sở dữ liệu. Ứng dụng có thể lưu ảnh, tài liệu và tệp sao lưu vào **Azure Blob Storage**; gửi các công việc bất đồng bộ vào **Azure Queue Storage**; hoặc dùng **Azure Table Storage** để lưu những thực thể NoSQL đơn giản.

Khi lập trình tại laptop, nếu mọi thao tác thử nghiệm đều đi vào storage account thật, nhóm phát triển sẽ gặp một số vấn đề:

- Phải có kết nối Internet và quyền truy cập vào Azure.
- Cần cấp phát tài nguyên cloud, quản lý tài khoản, khóa truy cập và chi phí.
- Dữ liệu thử nghiệm có thể lẫn với dữ liệu được chia sẻ của cả nhóm.
- Tự động hóa kiểm thử khó chạy ổn định khi mạng hoặc dịch vụ bên ngoài gặp sự cố.
- Các thao tác xóa, ghi đè hoặc kiểm tra lỗi có thể ảnh hưởng đến tài nguyên thật.

**Azurite** là bộ giả lập Azure Storage mã nguồn mở, chạy trên máy cá nhân hoặc trong container. Azurite tạo các endpoint cục bộ có hành vi tương tự một phần các dịch vụ Azure Storage, giúp ứng dụng sử dụng Storage SDK để đọc/ghi dữ liệu và kiểm thử luồng nghiệp vụ trước khi triển khai lên Azure.

Azurite không phải một storage account Azure thật. Vai trò của nó là cung cấp một **vòng phản hồi phát triển nhanh, cách ly và có thể tái tạo**. Sau giai đoạn local, vẫn cần kiểm thử trên một storage account thật trong môi trường integration/staging với cấu hình mạng, danh tính và tính năng cloud tương ứng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Azurite giả lập những dịch vụ nào và khác Azure Storage thật ở đâu.
2. Khởi chạy Azurite bằng npm hoặc Docker Compose.
3. Sử dụng endpoint Blob, Queue, Table và chuỗi kết nối local phù hợp.
4. Kết nối ứng dụng Java với Blob Storage qua Azure SDK, thực hiện upload/download.
5. Tổ chức cấu hình theo local, test, staging và production mà không để lộ khóa.
6. Viết kiểm thử tích hợp có thể lặp lại và dọn dữ liệu đúng cách.
7. Nhận diện các giới hạn giả lập và cách xác nhận trên Azure thật.
8. Xử lý các lỗi kết nối, xác thực, container/queue và xung đột cổng thường gặp.

## 2. Azurite là gì và giả lập được những dịch vụ nào?

Azurite là trình giả lập được xây dựng để phát triển cục bộ với các giao diện dữ liệu của Azure Storage. Nó có thể chạy như tiến trình Node.js hoặc trong Docker và được dùng bởi các ứng dụng gọi Storage SDK hay REST API thích hợp.

| Dịch vụ Azure Storage | Azurite mô phỏng | Ví dụ sử dụng trong ứng dụng |
|---|---|---|
| **Blob Storage** | Có, trong phạm vi tính năng và phiên bản API Azurite hỗ trợ | Lưu ảnh sản phẩm, tài liệu, file tải lên |
| **Queue Storage** | Có, trong phạm vi tính năng hỗ trợ | Hàng đợi gửi email hoặc xử lý ảnh |
| **Table Storage** | Có, trong phạm vi tính năng hỗ trợ | Lưu thực thể key-value với PartitionKey và RowKey |
| **Azure Files** | Không phải mục tiêu giả lập của Azurite | File share SMB/NFS cần môi trường kiểm thử khác |
| **Azure Data Lake Storage Gen2** | Không thay thế kiểm thử đầy đủ khả năng hierarchical namespace/ACL của ADLS Gen2 | Workload phân tích dữ liệu cần kiểm tra trên Azure thật |

Azurite cho phép kiểm tra các thao tác như tạo container, upload blob, đọc blob, tạo queue, thêm message hoặc tạo entity trong Table, tùy theo mức hỗ trợ hiện có.

**Điều quan trọng:** Azurite không bảo đảm tương thích 100% với tất cả REST API version, giới hạn kích thước, hành vi tính nhất quán, tính năng bảo mật, lỗi mạng, hiệu năng hay chính sách của Azure Storage thật. Một đoạn code chạy được trên Azurite là bằng chứng tốt cho logic cơ bản, **không phải bằng chứng đã sẵn sàng production**.

## 3. Azurite nằm ở đâu trong kiến trúc ứng dụng?

Một quy trình phát triển hợp lý tách riêng mã ứng dụng và cấu hình endpoint Storage.

~~~mermaid
flowchart LR
    A[Ứng dụng Java trên laptop] -->|Azure Storage SDK| B{Environment configuration}
    B -->|local| C[Azurite]
    B -->|integration hoặc staging| D[Azure Storage Account thử nghiệm]
    B -->|production| E[Azure Storage Account production]
    C --> F[Blob / Queue / Table giả lập]
    D --> G[Storage thật và policy cloud]
    E --> H[Storage thật với RBAC, mạng, giám sát]
~~~

Ý tưởng chính là dùng cùng giao diện SDK và nghiệp vụ, nhưng thay đổi cấu hình:

- **Local:** sử dụng endpoint trên máy hoặc container, dữ liệu giả và tài khoản emulator.
- **Automated test:** khởi tạo Azurite độc lập, dữ liệu thử nghiệm cách ly.
- **Staging:** kiểm tra khả năng tích hợp thực với Azure và các tính năng không được giả lập.
- **Production:** sử dụng storage account được bảo vệ bằng Microsoft Entra ID, Azure RBAC, mạng riêng, monitoring và quản trị chi phí theo kiến trúc.

Trong module Azure tổng thể, Azurite hỗ trợ giai đoạn phát triển của tầng lưu trữ; còn subscription, resource group, Entra ID, mạng và chính sách vận hành vẫn cần được học và kiểm tra riêng trên nền tảng thực tế.

## 4. Endpoint mặc định và tài khoản phát triển

Theo cấu hình cục bộ mặc định, Azurite cung cấp ba dịch vụ qua các cổng HTTP:

| Dịch vụ | Local endpoint mặc định | Cổng |
|---|---|---:|
| Blob | http://127.0.0.1:10000/devstoreaccount1 | 10000 |
| Queue | http://127.0.0.1:10001/devstoreaccount1 | 10001 |
| Table | http://127.0.0.1:10002/devstoreaccount1 | 10002 |

Tên account mặc định của emulator là **devstoreaccount1**. Azurite cung cấp khóa emulator mặc định được công bố công khai dành riêng cho mục đích phát triển. Khóa này **không phải** khóa của storage account Azure thật và không được sử dụng như một thông tin xác thực an toàn cho production.

Nhiều Azure Storage SDK chấp nhận chuỗi kết nối rút gọn:

~~~text
UseDevelopmentStorage=true
~~~

Chuỗi này thường được diễn giải thành account và các endpoint emulator mặc định. Nếu SDK/phiên bản bạn dùng không hỗ trợ chuỗi rút gọn, hoặc Azurite được triển khai qua hostname/cổng tùy chỉnh, cần sử dụng **connection string đầy đủ** với AccountName, AccountKey và các endpoint tương ứng theo hướng dẫn của phiên bản Azurite/SDK.

Ví dụ cấu trúc kết nối khi ứng dụng chạy trên **cùng máy host**:

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=<development-emulator-account-key>;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
~~~

Trong file cấu hình thực tế, chuỗi phải viết trên **một dòng**; ví dụ xuống dòng chỉ giúp dễ đọc. Giá trị AccountKey phải là khóa hợp lệ của emulator đã cấu hình, không phải chuỗi placeholder.

**Chỉ dùng HTTP và shared emulator credential trong môi trường local cách ly.** Khi lên Azure thật, dùng HTTPS và cơ chế nhận dạng/quản trị khóa phù hợp.

## 5. Cách 1: chạy Azurite bằng Node.js và npm

Khi đã cài một phiên bản Node.js được Azurite hiện tại hỗ trợ, có thể cài Azurite như một công cụ dòng lệnh:

~~~bash
npm install --global azurite
~~~

Tạo thư mục lưu dữ liệu thử nghiệm và chạy:

~~~bash
mkdir azurite-data
azurite --location ./azurite-data
~~~

Azurite thường khởi chạy các dịch vụ Blob, Queue và Table trên ba cổng mặc định. Để giới hạn kết nối vào máy cục bộ, có thể chỉ định host rõ ràng:

~~~bash
azurite \
  --location ./azurite-data \
  --blobHost 127.0.0.1 \
  --queueHost 127.0.0.1 \
  --tableHost 127.0.0.1
~~~

Dùng lệnh ở trên trong shell hỗ trợ dấu gạch chéo ngược để nối dòng như Bash. Trên Windows PowerShell, có thể viết toàn bộ lệnh trên một dòng hoặc dùng cách nối dòng tương ứng của PowerShell.

**Dữ liệu được lưu ở đâu?** Thư mục chỉ định bằng tham số location chứa trạng thái và dữ liệu emulator. Sau khi dừng và chạy lại bằng cùng thư mục, dữ liệu có thể vẫn còn. Điều này hữu ích khi phát triển thủ công, nhưng với kiểm thử tự động nên tạo thư mục riêng để tránh dữ liệu cũ làm sai kết quả.

Có thể bổ sung tùy chọn debug log để xử lý sự cố. Tuy nhiên, log có thể chứa đường dẫn, metadata và nội dung request phục vụ chẩn đoán; không nên bật logging quá chi tiết lâu dài hoặc đưa debug log chứa dữ liệu nhạy cảm lên repository.

## 6. Cách 2: dùng Docker Compose để tái tạo môi trường

Docker thường phù hợp với nhóm phát triển vì không bắt buộc cài Azurite trực tiếp trên máy và có thể quản lý phiên bản image tập trung.

Một ví dụ **docker-compose.yml**:

~~~yaml
services:
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    container_name: azurite-local
    command: >
      azurite --location /data
      --blobHost 0.0.0.0
      --queueHost 0.0.0.0
      --tableHost 0.0.0.0
    ports:
      - "127.0.0.1:10000:10000"
      - "127.0.0.1:10001:10001"
      - "127.0.0.1:10002:10002"
    volumes:
      - ./azurite-data:/data
~~~

Khởi động và xem trạng thái:

~~~bash
docker compose up -d
docker compose ps
docker compose logs azurite
~~~

Dừng container:

~~~bash
docker compose down
~~~

Cấu hình trên:

- Gắn cổng bên ngoài chỉ vào **127.0.0.1**, hạn chế máy khác truy cập qua giao diện mạng công khai của host.
- Gắn thư mục **./azurite-data** vào **/data** để lưu dữ liệu emulator.
- Mở đúng ba cổng cho Blob, Queue và Table.
- Dùng hostname **azurite** làm tên service trong Docker Compose network.

Trong dự án thực, nên **pin image theo version hoặc digest đã kiểm thử**, thay vì mặc định luôn dùng bản mới nhất trong pipeline lâu dài. Điều này giúp kết quả CI ổn định khi emulator phát hành phiên bản mới.

### 6.1. Phân biệt localhost của máy host và localhost của container

Nếu ứng dụng Java chạy **trực tiếp trên laptop**, endpoint có thể là:

~~~text
http://127.0.0.1:10000/devstoreaccount1
~~~

Nếu ứng dụng Java chạy **trong một container khác của cùng Compose network**, **127.0.0.1 bên trong container Java là chính container Java**, không phải container Azurite. Lúc này phải dùng hostname dịch vụ, ví dụ:

~~~text
http://azurite:10000/devstoreaccount1
~~~

Chuỗi **UseDevelopmentStorage=true** thường hướng SDK tới localhost mặc định, nên có thể không dùng được từ container ứng dụng riêng. Hãy cấu hình connection string đầy đủ với hostname **azurite**, tài khoản/khóa emulator và endpoint Blob/Queue/Table tương ứng.

Sai khác host/container là một trong những nguyên nhân phổ biến nhất khiến ứng dụng chạy được trên laptop nhưng integration test trong Docker trả lỗi **Connection refused**.

## 7. Kiểm tra Azurite đã chạy hay chưa

Trên Windows PowerShell, thử kiểm tra cổng Blob:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 10000
~~~

Trên shell thông thường, có thể dùng một HTTP request để xác định có phản hồi từ cổng:

~~~bash
curl -i http://127.0.0.1:10000/devstoreaccount1
~~~

Một HTTP status như **400**, **403** hoặc lỗi xác thực từ Storage API không nhất thiết có nghĩa Azurite chưa hoạt động. Vì endpoint Storage REST API có yêu cầu phương thức, header và chữ ký phù hợp, request GET đơn giản bằng curl chỉ có ý nghĩa kiểm tra sơ bộ **cổng có dịch vụ phản hồi**.

Kiểm thử đúng chức năng bằng Storage SDK hoặc Azure Storage Explorer đáng tin cậy hơn: tạo container, upload blob, tải về, đọc dữ liệu và kiểm tra kết quả.

Nếu cổng đã bị ứng dụng khác chiếm, đổi cổng qua tham số tương ứng của Azurite và cập nhật toàn bộ connection string/client configuration. Không chỉ sửa cổng trên Docker mà quên chỉnh endpoint ứng dụng.

## 8. Dùng Azure Storage Explorer với Azurite

**Azure Storage Explorer** là công cụ giao diện đồ họa để duyệt và thao tác trên tài nguyên Storage. Trong môi trường local, công cụ này hữu ích để quan sát dữ liệu khi đang debug SDK.

Quy trình khái quát:

1. Khởi chạy Azurite.
2. Mở Azure Storage Explorer.
3. Chọn phương án kết nối tới **local emulator** hoặc attach Storage resource tương ứng với phiên bản ứng dụng.
4. Sử dụng các cổng và account emulator mặc định nếu chạy bằng cấu hình ở mục 4.
5. Mở phần Blob Containers, Queues hoặc Tables.
6. Tạo container thử nghiệm, tải một file lên và mở lại file để xem nội dung.

Nếu Storage Explorer không thể kết nối, hãy kiểm tra Azurite có đang chạy, các port mapping, account key và phiên bản ứng dụng đang sử dụng. Không chuyển sang thao tác trên storage account thật chỉ vì một lỗi local chưa được hiểu rõ.

Storage Explorer tiện lợi cho kiểm tra thủ công, nhưng **không thay thế automated tests**: các bước click không dễ lặp lại, không phát hiện hồi quy đều đặn và khó kiểm soát dữ liệu phụ thuộc giữa những người cùng nhóm.

## 9. Mô hình Blob Storage trên Azurite

Các khái niệm cơ bản của Azure Blob Storage vẫn hữu ích khi học với Azurite:

- **Storage account:** ranh giới tên miền và thông tin xác thực của dịch vụ; trên Azurite dùng emulator account.
- **Blob container:** nhóm các blob; tên thường phải thỏa quy tắc naming của Blob Storage.
- **Blob:** đối tượng dữ liệu, ví dụ tài liệu, hình ảnh hoặc nội dung JSON.
- **Blob name:** tên đối tượng trong container, có thể dùng dấu gạch chéo để tạo cấu trúc giống thư mục.
- **Metadata và properties:** thông tin liên quan đến object, như content type hoặc application metadata.
- **ETag:** giá trị giúp xử lý điều kiện đồng thời khi API tương ứng hỗ trợ.

Ví dụ tổ chức dữ liệu:

~~~text
devstoreaccount1
└── container: product-images
    ├── products/1001/front.jpg
    ├── products/1001/back.jpg
    └── products/1002/front.jpg
~~~

Phần lớn trường hợp, các dấu gạch chéo trong blob name tạo **cấu trúc tên logic**; không nên tự suy luận Azurite có đầy đủ hệ thống thư mục hay ACL của Azure Data Lake Storage Gen2.

Một luồng ứng dụng có thể là:

1. Người dùng chọn ảnh sản phẩm.
2. Backend kiểm tra nội dung/giới hạn kích thước theo chính sách ứng dụng.
3. Backend tạo container nếu cần và upload Blob.
4. Backend lưu blob name hoặc ID tham chiếu trong cơ sở dữ liệu.
5. Khi đọc, backend dùng SDK để tải nội dung và trả cho người dùng sau khi kiểm tra quyền.

Dữ liệu giả lập nên dùng nội dung không nhạy cảm: ảnh mẫu, tệp text hoặc dữ liệu tổng hợp thay cho dữ liệu khách hàng thật.

## 10. Thực hành Java: upload và download Blob bằng Azure SDK

Trong module học phát triển ứng dụng với Azure, cách hữu ích nhất là viết mã gọi Azure SDK, sau đó chuyển endpoint giữa Azurite và Azure Storage thật bằng cấu hình.

### 10.1. Dependency

Với Maven, thư viện Blob Storage có tọa độ:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>VERSION_DA_KIEM_THU</version>
</dependency>
~~~

Thay **VERSION_DA_KIEM_THU** bằng phiên bản thư viện hiện hành mà dự án đã xác minh tương thích với Java runtime và dependency management của mình. Trong dự án lớn, có thể quản lý phiên bản qua Azure SDK BOM hoặc cơ chế quản lý dependency nội bộ. Không nên chọn một số phiên bản ngẫu nhiên chỉ để code build được.

### 10.2. Biến môi trường kết nối

Trên PowerShell cho phiên làm việc hiện tại:

~~~powershell
$env:AZURE_STORAGE_CONNECTION_STRING = "UseDevelopmentStorage=true"
~~~

Trên Bash:

~~~bash
export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
~~~

Một số phiên bản SDK hoặc thư viện có thể không nhận dạng chuỗi rút gọn. Khi gặp trường hợp đó, dùng connection string emulator **đầy đủ** với AccountName, AccountKey và endpoint chính xác từ cấu hình Azurite. Tuyệt đối không dùng chuỗi giả lập làm credential của tài khoản Azure thật.

### 10.3. Java code

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public class AzuriteBlobDemo {
    public static void main(String[] args) {
        String connectionString =
                System.getenv("AZURE_STORAGE_CONNECTION_STRING");

        if (connectionString == null || connectionString.trim().isEmpty()) {
            throw new IllegalStateException(
                    "AZURE_STORAGE_CONNECTION_STRING chua duoc cau hinh");
        }

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();

        BlobContainerClient container =
                service.getBlobContainerClient("dev-documents");
        container.createIfNotExists();

        BlobClient blob = container.getBlobClient("hello.txt");
        blob.upload(BinaryData.fromString("Xin chao Azurite!"), true);

        String downloaded = blob.downloadContent().toString();
        System.out.println("Downloaded content: " + downloaded);
    }
}
~~~

Diễn giải:

- **BlobServiceClientBuilder** tạo SDK client từ cấu hình môi trường.
- **getBlobContainerClient** chọn container bằng tên.
- **createIfNotExists** giúp thao tác setup chạy lại thuận tiện trong local.
- **getBlobClient** chọn blob cụ thể.
- **upload(..., true)** cho phép ghi đè blob cùng tên; chỉ dùng khi logic nghiệp vụ hoặc bài lab cho phép.
- **downloadContent** đọc nội dung Blob về để đối chiếu.

Kết quả mong đợi khi chạy thành công:

~~~text
Downloaded content: Xin chao Azurite!
~~~

Sau khi chạy, mở Azure Storage Explorer và kiểm tra container **dev-documents** có blob **hello.txt**. Nếu không thấy dữ liệu, xác nhận Storage Explorer đang nối tới cùng emulator endpoint/account với ứng dụng Java.

**Lưu ý Java SDK:** tên API và các overload có thể thay đổi qua các phiên bản SDK. Hãy giữ dependency và code cùng một phiên bản đã kiểm thử; nếu lỗi build, kiểm tra tài liệu của đúng phiên bản SDK trước khi thay đổi logic.

### 10.4. Vì sao không hardcode connection string?

Một ứng dụng thường chạy trên máy cá nhân, CI, staging và production. Nếu connection string được hardcode, việc chuyển môi trường sẽ kéo theo sửa source code, dễ làm lộ credential và khó rollback.

Nên dùng biến môi trường hoặc hệ thống cấu hình an toàn. Ở production, ưu tiên Microsoft Entra ID với managed identity và Azure RBAC khi SDK/dịch vụ hỗ trợ, thay vì phân phối account key dài hạn.

## 11. Java SDK: tách local và Azure thật

Thay vì lẫn nhiều điều kiện kiểm thử vào logic nghiệp vụ, hãy tạo một factory/cấu hình chung cho client:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class StorageClientFactory {
    private StorageClientFactory() {}

    public static BlobServiceClient create() {
        String connectionString =
                System.getenv("AZURE_STORAGE_CONNECTION_STRING");

        BlobServiceClientBuilder builder = new BlobServiceClientBuilder();

        if (connectionString != null &&
                !connectionString.trim().isEmpty()) {
            // Local Azurite hoặc cấu hình kết nối test được phép.
            return builder.connectionString(connectionString)
                    .buildClient();
        }

        String endpoint = System.getenv("AZURE_STORAGE_BLOB_ENDPOINT");
        if (endpoint == null || endpoint.trim().isEmpty()) {
            throw new IllegalStateException(
                    "Phai cau hinh connection string hoac Blob endpoint");
        }

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return builder.endpoint(endpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

Để sử dụng nhánh Azure thật trong ví dụ trên, dự án cần thêm dependency **com.azure:azure-identity** với phiên bản phù hợp.

Ví dụ hai cách cấu hình:

| Môi trường | Cấu hình client | Cơ chế xác thực |
|---|---|---|
| Local | AZURE_STORAGE_CONNECTION_STRING với emulator connection | Credential giả lập |
| CI integration bằng Azurite | Connection string tới Azurite của test run | Credential giả lập |
| Azure staging | AZURE_STORAGE_BLOB_ENDPOINT trỏ tới https://<storage-account>.blob.core.windows.net | DefaultAzureCredential |
| Azure production | Endpoint Blob thực tế và managed identity | DefaultAzureCredential với managed identity |

**Điểm bảo mật quan trọng:** trong staging/production, chỉ đặt **AZURE_STORAGE_BLOB_ENDPOINT**, không cung cấp emulator connection string. Biến môi trường connection string đang có sẽ được ưu tiên trong ví dụ factory này; nếu triển khai nhầm sang production, ứng dụng có thể kết nối sai đích. Hệ thống thực tế cần kiểm tra rõ environment name và xác thực cấu hình ở bước startup để fail fast khi phát hiện endpoint không được phê duyệt.

Với Azure Blob thật, principal chạy ứng dụng cần vai trò **data-plane** phù hợp, ví dụ **Storage Blob Data Contributor** ở scope cần thiết để upload. Quyền Azure RBAC quản lý resource group như Reader không mặc nhiên cung cấp quyền đọc/ghi dữ liệu blob.

## 12. Bài toán Queue Storage trên Azurite

**Azure Queue Storage** phù hợp cho các tác vụ nền đơn giản. Thay vì xử lý ảnh ngay trong HTTP request, ứng dụng tạo một message và worker xử lý sau:

~~~mermaid
sequenceDiagram
    participant API as Ứng dụng API
    participant Q as Azurite Queue
    participant W as Background worker
    participant B as Azurite Blob
    API->>B: Upload ảnh nguồn
    API->>Q: Gửi message xử lý ảnh
    W->>Q: Receive message
    Q-->>W: Nội dung + pop receipt
    W->>B: Tạo ảnh thumbnail
    W->>Q: Delete message sau khi xử lý xong
~~~

Khái niệm:

- **Queue:** nơi chứa message.
- **Message:** dữ liệu tác vụ, thường nên nhỏ và có ID tham chiếu.
- **Visibility timeout:** sau khi worker nhận, message được ẩn tạm thời để worker xử lý.
- **Pop receipt:** giá trị cần dùng khi xóa hoặc cập nhật message đã nhận.
- **Dequeue count:** thông tin hữu ích để phát hiện message xử lý thất bại nhiều lần.

### 12.1. Java dependency và luồng cơ bản

Có thể dùng SDK **com.azure:azure-storage-queue** với phiên bản tương thích dự án. Luồng cơ bản:

1. Tạo **QueueServiceClient** từ connection string.
2. Chọn queue, ví dụ **image-jobs** và tạo nếu chưa có.
3. Gửi message chứa ID blob cần xử lý.
4. Worker receive message, đọc ID và thực hiện tác vụ.
5. Sau khi xử lý thành công, xóa message bằng message ID và pop receipt hiện hành.
6. Nếu xử lý lỗi, quản lý retry, visibility timeout và ngưỡng chuyển vào hàng đợi lỗi theo thiết kế ứng dụng.

Không nên suy luận một message chỉ được giao **đúng một lần**. Ứng dụng cần thiết kế xử lý **idempotent**, vì cùng tác vụ có thể được xử lý lại sau retry, timeout hoặc sự cố worker. Không đặt nội dung tệp lớn trực tiếp vào message; lưu tệp trong Blob rồi gửi tham chiếu.

### 12.2. Những điều không thể kết luận chỉ từ Azurite

Queue emulator giúp kiểm tra luồng tạo/nhận/xóa message, nhưng không thay thế load test, đánh giá giới hạn quy mô và cơ chế vận hành ở cloud. Nếu cần topic/subscription, broker semantics hoặc các tính năng nhắn tin doanh nghiệp chuyên sâu, hãy xem xét **Azure Service Bus**; Azurite Queue không phải emulator đầy đủ của Service Bus.

## 13. Bài toán Table Storage trên Azurite

**Azure Table Storage** là mô hình NoSQL đơn giản lưu **entity** theo khóa phân vùng và khóa hàng.

Các thành phần cốt lõi:

- **Table:** tập hợp entity.
- **PartitionKey:** khóa dùng để nhóm dữ liệu và hỗ trợ truy vấn.
- **RowKey:** khóa định danh entity trong partition.
- **Properties:** các cột/thuộc tính của entity.
- **ETag:** hỗ trợ kiểm soát thay đổi cạnh tranh trong những thao tác được hỗ trợ.

Ví dụ bảng **UserPreferences**:

| PartitionKey | RowKey | Theme | Language |
|---|---|---|---|
| tenant-a | user-001 | dark | vi |
| tenant-a | user-002 | light | en |
| tenant-b | user-001 | dark | vi |

Entity được nhận diện bởi cặp **PartitionKey + RowKey**. Cách chọn PartitionKey ảnh hưởng đến mô hình truy vấn và phân phối dữ liệu khi lên Azure thật. Không nên thiết kế Table như một cơ sở dữ liệu quan hệ có join tự do.

SDK Java dùng cho thao tác Table là **com.azure:azure-data-tables**. Luồng học tập cơ bản:

1. Tạo TableServiceClient từ cấu hình kết nối local.
2. Tạo bảng thử nghiệm hoặc chọn bảng có sẵn.
3. Tạo entity với PartitionKey, RowKey và properties.
4. Đọc entity theo khóa và cập nhật một property.
5. Thử xử lý trường hợp entity đã tồn tại hoặc ETag xung đột.
6. Xóa dữ liệu thử nghiệm khi hoàn thành.

Một số khác biệt về API, indexing, batch transaction, kiểu dữ liệu hoặc giới hạn trong emulator cần được kiểm thử lại trên Azure Storage thật trước khi chốt thiết kế hệ thống.

## 14. Quy trình phát triển local lặp lại được

Một vòng làm việc nên có trình tự nhất quán:

~~~mermaid
flowchart TD
    A[Checkout code ứng dụng] --> B[Khởi chạy Azurite]
    B --> C[Load cấu hình môi trường local]
    C --> D[Khởi tạo container / queue / table cho lab]
    D --> E[Chạy ứng dụng Java]
    E --> F[Thực thi nghiệp vụ Blob / Queue / Table]
    F --> G[Quan sát dữ liệu và log]
    G --> H{Kết quả đúng?}
    H -->|Không| I[Sửa code hoặc cấu hình]
    I --> E
    H -->|Có| J[Chạy integration tests]
    J --> K[Dọn dữ liệu thử nghiệm và dừng emulator]
~~~

Đối với phát triển thủ công, có thể dùng một volume tồn tại qua nhiều phiên. Đối với CI hoặc integration test, nên dùng môi trường mới mỗi lần chạy để giảm phụ thuộc vào dữ liệu cũ.

### 14.1. Đặt tên tài nguyên nhất quán

Ví dụ:

- Container Blob: **dev-documents**, **test-uploads**.
- Queue: **image-jobs**.
- Table: **UserPreferences**.
- Blob name: **users/u001/profile.json**.

Tên container/queue/table có quy tắc riêng về chữ hoa, ký tự và độ dài. Nên dùng quy ước tên mà cả Azure thật lẫn Azurite đều chấp nhận; không dựa vào một ngoại lệ mà emulator cho phép.

### 14.2. Cấu hình local không được đi vào production

Trong source code và manifest triển khai, tách rõ:

- Cấu hình **local** chỉ dùng khi developer chủ động chọn environment local.
- Cấu hình **test** dùng trong pipeline với Azurite được tạo cho chính pipeline đó.
- Cấu hình **staging/prod** dùng endpoint Azure và cơ chế xác thực bảo mật đã phê duyệt.

Không nên dùng một biến chung mặc định luôn trỏ local mà khi thiếu env production lại âm thầm ghi vào emulator. Ứng dụng cần **fail fast** nếu thiếu endpoint hoặc credential của môi trường thật.

## 15. Tổ chức kiểm thử tích hợp tự động

Azurite hữu ích nhất khi kết hợp với kiểm thử tạo tài nguyên thật trong emulator thay vì chỉ mock SDK.

### 15.1. Phân tầng kiểm thử

| Loại kiểm thử | Cần gì? | Nên xác minh |
|---|---|---|
| Unit test | Mock/fake ứng dụng và repository, không bắt buộc Azurite | Điều kiện nghiệp vụ, validate input, phân nhánh lỗi |
| Integration test local | Azurite mới hoặc dữ liệu cô lập | SDK kết nối, create/upload/download/list/delete, queue workflow |
| Contract/compatibility test cloud | Storage account Azure thử nghiệm | API version, authentication, tính năng cloud, hạn mức, networking |
| End-to-end staging | Ứng dụng và các thành phần Azure thật | Quyền danh tính, xử lý dữ liệu, retry, observability, private networking |

Azurite không thay thế tất cả các loại kiểm thử khác. Một bộ test tốt có lớp nhanh trên local và một lớp kiểm tra cloud có kiểm soát.

### 15.2. Nguyên tắc test độc lập

- Mỗi test suite có container/queue/table riêng hoặc suffix định danh duy nhất.
- Setup tạo những tài nguyên cần thiết; teardown dọn đúng những đối tượng test sở hữu.
- Không phụ thuộc thứ tự chạy test, dữ liệu từ hôm trước hoặc máy của một developer.
- Dùng nội dung file nhỏ, dữ liệu giả, payload có kết quả mong đợi rõ.
- Test cả thành công và lỗi hợp lý: đọc blob không tồn tại, upload overwrite, xử lý cùng queue message nhiều lần, tên không hợp lệ.
- Đặt thời hạn chờ cho các lời gọi có retry; nếu test lỗi phải hiển thị thông tin endpoint/log giúp điều tra.
- Dùng phiên bản Azurite được kiểm soát để tránh khác biệt giữa CI và máy cá nhân.

### 15.3. Dữ liệu mẫu cho bài thực hành

Một kịch bản integration test Blob:

~~~text
Given: container test-docs chưa tồn tại
When:  ứng dụng khởi tạo container và upload hello.txt
Then:  blob có nội dung "hello-local"

When:  ứng dụng download hello.txt
Then:  nội dung đúng với dữ liệu đã upload

When:  ứng dụng xóa blob
Then:  blob không còn đọc được theo kỳ vọng SDK/API
~~~

Một kịch bản Queue:

~~~text
Given: queue image-jobs đang rỗng
When:  producer gửi message "job-001"
And:   worker nhận và xử lý thành công
Then:  worker xóa message với pop receipt hợp lệ
And:   lần nhận tiếp theo không còn thấy message đó
~~~

Các test trên kiểm tra **hợp đồng ứng dụng với Storage SDK**. Chúng không chứng minh hiệu năng hệ thống dưới tải lớn, bảo mật mạng production hay mọi retry behavior ở Azure thật.

### 15.4. Cleanup an toàn

Trong kiểm thử, có thể xóa container/queue/table của chính bài lab khi đã kết thúc. Tránh dùng lệnh xóa hàng loạt trỏ tới storage account cloud chỉ vì biến môi trường sai. Trước mọi teardown tự động, cần kiểm tra hostname, account name và environment.

## 16. Kết hợp Azurite với CI/CD

Trong CI/CD, Azurite có thể chạy dưới dạng **service container** hoặc một container được khởi động trước test. Cách triển khai cụ thể tùy công cụ CI, nhưng mô hình chung là:

1. Pipeline tạo môi trường test và chạy Azurite.
2. Kiểm tra ba cổng sẵn sàng ở hostname mà job test sử dụng.
3. Cung cấp connection string local cho tiến trình test.
4. Chạy unit/integration tests.
5. Thu thập log Azurite và kết quả test nếu có lỗi.
6. Dừng container và dọn volume tạm sau job.

Nếu CI runner thực thi ứng dụng **ngoài Docker**, có thể dùng localhost và mapped ports. Nếu runner/test ở **container khác**, phải dùng hostname DNS của service trong container network và connection string có endpoint tương ứng.

Đừng chỉ chờ một khoảng thời gian cố định rồi mặc định emulator đã khởi động; nên kiểm tra TCP port hoặc một thao tác SDK thật và có giới hạn retry. Việc này giảm lỗi test chập chờn trên máy CI chạy chậm.

Pin image Azurite và các SDK dependency vào các phiên bản đã kiểm thử; thực hiện nâng cấp có kế hoạch, vì thay đổi hỗ trợ API/version của emulator có thể làm test cũ khác kết quả.

## 17. Phân biệt kết nối bằng khóa giả lập và Managed Identity

Điều kiện bảo mật ở local và cloud khác nhau đáng kể.

### 17.1. Local

Trong local, **devstoreaccount1** và khóa emulator là dữ liệu mặc định phục vụ phát triển. Storage SDK có thể xác thực request bằng khóa này, nhưng đó **không phải hệ thống Azure RBAC thật**.

### 17.2. Azure staging/production

Trong Azure, nên cân nhắc:

- **Managed identity** cho VM, App Service, Functions hoặc workload hỗ trợ.
- **DefaultAzureCredential** trong SDK để dùng phương thức nhận dạng phù hợp với môi trường chạy.
- **Storage Blob Data Reader/Contributor** hoặc vai trò data-plane tương ứng theo nhu cầu.
- **HTTPS**, firewall và private endpoint theo yêu cầu kiến trúc.
- **Key Vault** cho các bí mật buộc phải dùng, cùng cơ chế luân chuyển và hạn chế truy cập.
- **Azure Monitor** và cấu hình log phù hợp để điều tra thao tác dữ liệu.

Một số cơ chế mô phỏng OAuth của Azurite có thể tồn tại ở các phiên bản/cấu hình nhất định, nhưng **không thay thế xác minh chính sách Microsoft Entra ID, Conditional Access, RBAC data-plane và managed identity thực tế**. Vì thế, mọi chức năng liên quan tới quyền cloud cần có bài kiểm tra riêng trên Azure thật.

### 17.3. Không nhầm quyền management-plane và data-plane

Có quyền chỉnh sửa storage account ở Azure Resource Manager không mặc nhiên đồng nghĩa ứng dụng được phép đọc dữ liệu Blob. Quyền dữ liệu được kiểm tra bằng role/credential và network restrictions thích hợp. Đây là khác biệt quan trọng mà môi trường Azurite local thường không biểu diễn đầy đủ.

## 18. Những điểm khác biệt cần test lại trên Azure thật

| Chủ đề | Azurite có thể giúp | Bắt buộc xác minh bổ sung trên Azure thật |
|---|---|---|
| Blob CRUD | Tạo container, upload/download/delete trong phạm vi hỗ trợ | Giới hạn dịch vụ, performance, network, encryption policies |
| Queue CRUD | Gửi/nhận/xóa message cơ bản | Hành vi dưới tải, retry, concurrency, giới hạn dịch vụ |
| Table operations | Tạo/read/update entity theo khóa | Query behavior, scale, transaction/ETag theo nhu cầu |
| Authentication | Development key và chế độ giả lập được hỗ trợ | Microsoft Entra ID, managed identity, SAS/RBAC thực tế |
| HTTPS/TLS | Cấu hình local có thể tùy chỉnh | TLS, certificate và policy production |
| Networking | Kết nối localhost/container network | Storage firewall, VNet/private endpoint, DNS riêng |
| Monitoring | Log tiến trình emulator | Azure Monitor, diagnostic settings, metrics, audit |
| Availability/DR | Test logic retry/fallback cơ bản | Geo-redundancy, replication, failover của storage account |
| Performance | Test chức năng trên máy cá nhân | Độ trễ, thông lượng, quota, throttling thật |
| API versions | Test những API mà emulator triển khai | Tương thích SDK/API mới và tính năng đặc thù trên Azure |

Một số SDK khi sử dụng API version mới hơn bản Azurite hỗ trợ có thể trả lỗi không tương thích. Không nên tùy tiện bật tùy chọn **bỏ kiểm tra phiên bản API** để tuyên bố hệ thống đã tương thích; đó chỉ là mẹo debug hạn chế và không thay thế việc dùng đúng phiên bản emulator/SDK.

## 19. Xử lý sự cố thường gặp

### 19.1. Connection refused hoặc ECONNREFUSED

**Triệu chứng:** ứng dụng không thể kết nối đến 127.0.0.1:10000.

**Kiểm tra:** Azurite có chạy không, cổng có map đúng không, container đã khởi tạo xong chưa, hostname có đang trỏ về đúng network namespace không. Trong Docker Compose, nếu cả ứng dụng và Azurite đều chạy trong container, dùng hostname service **azurite** thay vì localhost.

### 19.2. AuthorizationFailure hoặc AuthenticationFailed

**Triệu chứng:** SDK nhận lỗi 403 hoặc chữ ký không hợp lệ.

**Kiểm tra:** account name, account key, endpoint Blob/Queue/Table và kết cấu connection string. Dùng **UseDevelopmentStorage=true** khi đúng phiên bản SDK và cấu hình mặc định. Nếu đã cấu hình account tùy chỉnh hoặc cổng khác, phải cập nhật toàn bộ string.

Đừng dùng connection string của Azure thật để kết nối local hoặc dùng emulator key để kết nối storage account cloud.

### 19.3. Lỗi HTTP/HTTPS

Azurite mặc định chạy HTTP. Nếu client được cấu hình endpoint **https://127.0.0.1:10000** nhưng Azurite không bật TLS, kết nối có thể thất bại vì handshake hoặc lỗi certificate.

Giữ local HTTP trên loopback trong lab đơn giản; nếu cần test HTTPS thật, cấu hình chứng chỉ và TLS cho emulator theo hướng dẫn sản phẩm. Production phải dùng endpoint HTTPS thật.

### 19.4. ContainerNotFound hoặc BlobNotFound

**Triệu chứng:** upload hoặc download trả lỗi 404.

**Kiểm tra:** container đã được tạo chưa, tên container/blob có đúng chữ hoa/chữ thường không, thao tác có chạy vào cùng emulator account và data directory không, có tiến trình khác xóa dữ liệu hay không.

### 19.5. Lỗi Unsupported API Version hoặc InvalidHeaderValue

Có thể do SDK gọi phiên bản Storage REST API mới hơn bản Azurite đang chạy, hoặc endpoint không hỗ trợ thao tác đó. Hãy ghi version SDK, version Azurite và API version trong request rồi cân nhắc nâng emulator hoặc điều chỉnh test cho đúng khả năng hỗ trợ.

Không nên coi bỏ kiểm tra API version là giải pháp lâu dài hay bằng chứng tính năng được giả lập chính xác.

### 19.6. Data khác giữa các lần chạy

Nếu dùng volume/thư mục lưu data, blob hoặc queue từ lần thử trước có thể còn tồn tại. Trong manual testing, hãy biết đang tái sử dụng volume nào. Trong integration test, dùng volume tạm hoặc tên tài nguyên duy nhất và cleanup sau suite.

### 19.7. Xung đột cổng 10000/10001/10002

Một tiến trình Azurite khác hoặc dịch vụ khác có thể chiếm cổng. Kiểm tra tiến trình đang nghe cổng, dừng tiến trình không cần thiết hoặc đổi port. Mọi endpoint và connection string phải khớp port mới.

### 19.8. Storage Explorer thấy dữ liệu khác ứng dụng

Thường do Storage Explorer trỏ vào emulator khác, cổng khác, account khác hoặc volume khác. Kiểm tra Blob endpoint và tên container trong SDK cùng thông tin kết nối ở Storage Explorer.

### 19.9. Test thành công local nhưng lỗi ở staging

Kiểm tra credential Azure, quyền data-plane, private endpoint/firewall, DNS, TLS và API behavior. Đây là lý do cần lớp **cloud integration test** thay vì chỉ dùng Azurite.

## 20. Đề xuất tổ chức dự án phát triển

Một dự án Java có thể sắp xếp như sau:

~~~text
storage-demo/
├── src/
│   ├── main/java/.../StorageClientFactory.java
│   ├── main/java/.../DocumentService.java
│   └── test/java/.../DocumentStorageIntegrationTest.java
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
~~~

Đây là **mô hình tham khảo**. Trong nhiệm vụ viết bài này, không tạo hoặc chỉnh sửa các file dự án trên.

Nội dung gợi ý cho **.env.example**:

~~~dotenv
APP_ENV=local
AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true
~~~

Khi chạy trên Azure, dùng environment configuration độc lập, ví dụ:

~~~text
APP_ENV=production
AZURE_STORAGE_BLOB_ENDPOINT=https://<storage-account>.blob.core.windows.net
~~~

Không để private key, account key cloud hay connection string sản xuất vào **.env.example**, Git hoặc log. Nếu dùng file **.env** có thông tin cá nhân/credential, cần thêm vào cơ chế ignore của repository và bảo vệ quyền truy cập file.

Đối với production, nên triển khai cấu hình qua managed identity hoặc bộ quản lý cấu hình/secret phù hợp thay vì copy file local lên server.

## 21. Bài thực hành xuyên suốt: tài liệu và xử lý nền

**Bối cảnh:** bạn đang viết dịch vụ upload tài liệu cho một ứng dụng Java. Tài liệu được lưu ở Blob, còn tác vụ xử lý thumbnail hoặc phân tích metadata được đưa vào Queue.

### Phần A — Khởi chạy local Storage

1. Chạy Azurite bằng npm hoặc Docker Compose.
2. Kiểm tra cổng 10000 và 10001 đang phản hồi.
3. Dùng **UseDevelopmentStorage=true** nếu ứng dụng chạy trên máy host và SDK hỗ trợ.
4. Mở Azure Storage Explorer và xác nhận đã kết nối emulator.

### Phần B — Blob

1. Tạo Blob container **dev-documents**.
2. Dùng chương trình Java ở mục 10 để upload **hello.txt**.
3. Tải về và đối chiếu nội dung.
4. Thử upload cùng blob name với overwrite được bật và không được bật để hiểu hành vi ứng dụng.
5. Thử đọc một blob không tồn tại và ghi nhận SDK exception.

### Phần C — Queue

1. Tạo queue **image-jobs**.
2. Gửi một message chứa tên blob **hello.txt** hoặc job ID tương ứng.
3. Worker đọc message và ghi log xử lý giả lập.
4. Xóa message chỉ khi công việc hoàn thành.
5. Tạo tình huống worker lỗi trước khi xóa, quan sát message có thể được nhận lại sau visibility timeout.

### Phần D — Kiểm thử

1. Thêm một integration test upload/download Blob.
2. Thêm một integration test Queue send/receive/delete.
3. Chạy test nhiều lần với dữ liệu cách ly để kiểm tra tính lặp lại.
4. Quan sát dữ liệu trong Storage Explorer và log Azurite khi test lỗi.
5. Xóa đúng tài nguyên do lab tạo, giữ lại những tài nguyên không thuộc bài thực hành.

### Phần E — Chuyển sang Azure thử nghiệm

1. Chuẩn bị một Azure Storage Account **staging** được phê duyệt.
2. Cấu hình endpoint Azure HTTPS và danh tính có quyền data-plane cần thiết.
3. Chạy lại các kịch bản tích hợp trong staging với dữ liệu giả.
4. Kiểm tra network/firewall, credential, logging, retry và các tính năng Azure mà emulator chưa phản ánh.
5. Tổng hợp khác biệt và điều chỉnh code hoặc cấu hình theo nguyên nhân thực tế.

**Tiêu chí hoàn thành:** ứng dụng sử dụng một lớp Storage SDK thống nhất, local test dùng Azurite, staging dùng storage account thật, và không để credential cloud trong source code.

## 22. Checklist trước khi đưa Storage vào ứng dụng thật

- [ ] Đã xác định đúng Blob, Queue hoặc Table, không nhầm với Azure Files/Service Bus.
- [ ] Azurite đã chạy đúng port, hostname và data directory.
- [ ] Các connection string local chỉ dùng cho local/test.
- [ ] Ứng dụng có cơ chế fail fast khi thiếu cấu hình staging/production.
- [ ] Đã có integration test cho CRUD và những trường hợp lỗi quan trọng.
- [ ] Dữ liệu test là dữ liệu giả, không chứa thông tin khách hàng thật.
- [ ] CI tạo môi trường Azurite độc lập và thu thập log khi lỗi.
- [ ] Test có cleanup theo scope, không xóa nhầm storage account thật.
- [ ] Đã kiểm tra API/version và những tính năng Azurite không hỗ trợ.
- [ ] Azure staging dùng HTTPS, RBAC data-plane, identity và network policy phù hợp.
- [ ] Có monitoring, retry, timeout và chính sách bảo vệ dữ liệu ở Azure thật.
- [ ] Đã dự trù chi phí cloud và quy trình cleanup tài nguyên staging khi không dùng.

## 23. Câu hỏi tự kiểm tra

1. Vì sao Azurite giúp giảm thời gian phản hồi khi phát triển ứng dụng Storage trên laptop?
2. Azurite giả lập những dịch vụ nào, và vì sao không dùng nó để kiểm thử toàn bộ Azure Files hay Data Lake Storage Gen2?
3. Các cổng mặc định 10000, 10001 và 10002 tương ứng với dịch vụ nào?
4. Vì sao **UseDevelopmentStorage=true** có thể hoạt động trên máy host nhưng thất bại trong container ứng dụng chạy cùng Docker Compose?
5. Tại sao một lần GET bằng curl trả HTTP 403 không đủ để kết luận Azurite bị tắt?
6. Trong Java, tại sao nên tách connection string khỏi logic nghiệp vụ?
7. Khi nào nên dùng managed identity thay vì emulator account key?
8. Với Queue, vì sao worker phải thiết kế idempotent?
9. Một integration test nên thiết lập dữ liệu và cleanup như thế nào để không phụ thuộc vào lần chạy trước?
10. Những loại kiểm thử nào phải được thực hiện trên Azure thật dù mọi test Azurite đã PASS?

## 24. Tổng kết

**Azurite** là công cụ giả lập Azure Blob, Queue và Table Storage trên máy cá nhân hoặc trong container. Nó cho phép ứng dụng Java tương tác qua Azure SDK, tạo dữ liệu thử nghiệm, kiểm tra upload/download và quy trình xử lý bất đồng bộ mà không phải sử dụng storage account cloud trong mọi vòng sửa code.

Một quy trình tốt tách rõ **local Azurite → automated integration test → Azure staging → production**, quản lý endpoint qua cấu hình, không hardcode credential và luôn xác minh khả năng tương thích trên Azure thật. Hãy dùng Azurite để tăng tốc phát triển, nhưng dựa vào Microsoft Entra ID, Azure RBAC, cấu hình mạng, giám sát và các bài test cloud để đảm bảo an toàn và độ tin cậy khi triển khai ứng dụng Storage vào môi trường thực tế.
