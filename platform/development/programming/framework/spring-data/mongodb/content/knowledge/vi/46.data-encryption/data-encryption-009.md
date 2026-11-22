# Đối chiếu tính năng server, driver, thư viện mã hóa và edition

Trong ứng dụng **Spring Data MongoDB**, yêu cầu “mã hóa dữ liệu” chỉ trở thành một thiết kế triển khai được khi xác định rõ **mã hóa ở lớp nào**, **MongoDB Server hỗ trợ gì**, **edition nào đang chạy**, **Java driver có khả năng tương ứng hay không**, **thư viện mã hóa nào đã được đóng gói** và **khóa được quản lý ở đâu**.

Một cluster dùng TLS và đã mã hóa ổ đĩa vẫn có thể trả dữ liệu dạng rõ (plaintext) cho một tài khoản có quyền đọc. Ngược lại, một ứng dụng có **Client-Side Field Level Encryption (CSFLE)** có thể giữ các trường nhạy cảm ở dạng ciphertext trên server, nhưng vẫn cần TLS, phân quyền, quản lý khóa và phương án sao lưu. Bài này cung cấp cách đối chiếu các lớp đó trước khi chọn cấu hình **MongoTemplate**, repository hoặc **ReactiveMongoTemplate**.

> Phạm vi: MongoDB Community Server, MongoDB Enterprise Advanced và MongoDB Atlas; Java driver đồng bộ hoặc reactive được Spring Data MongoDB sử dụng. Mốc đối chiếu tài liệu: **tháng 11/2026**. Quyền sử dụng một tính năng cần được kiểm tra lại theo phiên bản thực tế, topology, FCV, gói phần mềm và tài liệu tương thích tại thời điểm triển khai.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt mã hóa **trên đường truyền**, **khi lưu trữ** và **tại phía ứng dụng trước khi gửi dữ liệu**.
2. Đọc bảng tương thích theo **server version × edition × topology × driver × thư viện mã hóa × kiểu truy vấn**.
3. Phân biệt **mã hóa thủ công (explicit)** và **mã hóa tự động (automatic)**, bao gồm trường hợp **tự động giải mã** nhưng không tự động mã hóa.
4. Biết vai trò riêng của **mongodb-crypt**, **libmongocrypt**, **crypt_shared**, **mongocryptd**, **DEK**, **CMK** và **KMS**.
5. Đưa ra quyết định có chứng cứ cho một yêu cầu truy vấn trên trường mã hóa và lập kế hoạch kiểm thử từ Spring Data MongoDB.

## 2. Nhìn theo các lớp bảo vệ

| Lớp | Ai thực hiện? | Dữ liệu được bảo vệ ở đâu? | Có tự che dữ liệu khỏi MongoDB Server không? |
| --- | --- | --- | --- |
| **TLS** | Driver và endpoint MongoDB | Khi truyền qua mạng | **Không**. Server giải mã TLS để xử lý truy vấn. |
| **Encryption at rest** | Cơ chế lưu trữ của Atlas, Enterprise hoặc hạ tầng/ổ đĩa | Tệp dữ liệu, volume và các bản sao lưu thuộc phạm vi được cấu hình | **Không**. Server đang hoạt động vẫn đọc được dữ liệu để xử lý. |
| **CSFLE** | Client/driver và thư viện mã hóa | Một số trường được mã hóa trước khi rời ứng dụng | **Có**, với các trường được cấu hình và khi khóa không nằm trong tay server. |
| **Queryable Encryption (QE)** | Client/driver; server xử lý truy vấn trên dữ liệu mã hóa theo cơ chế hỗ trợ | Trường nhạy cảm vẫn mã hóa và có thể hỗ trợ một số dạng truy vấn | **Có**, với dữ liệu được cấu hình đúng; khả năng truy vấn phụ thuộc phiên bản và giới hạn của QE. |

~~~mermaid
flowchart LR
    A["Spring Data MongoDB<br/>MongoTemplate / Repository"] --> B["Java MongoDB Driver"]
    B --> C{"Có mã hóa phía client?"}
    C -- "CSFLE hoặc QE" --> D["mongodb-crypt / libmongocrypt<br/>DEK + KMS + phân tích truy vấn nếu cần"]
    C -- "Không" --> E["TLS"]
    D --> E
    E --> F["MongoDB Server<br/>Community / Enterprise / Atlas"]
    F --> G["Lớp lưu trữ<br/>Encryption at rest"]
~~~

**Tách biệt mối đe dọa cần xử lý:**

- Chống nghe lén giữa ứng dụng và MongoDB: cấu hình **TLS** và xác minh chứng chỉ.
- Chống đọc trái phép thiết bị lưu trữ bị thất lạc: **encryption at rest**, chính sách khóa và backup.
- Hạn chế người quản trị DB hoặc dịch vụ có quyền đọc dữ liệu thấy trường bí mật: **mã hóa phía client** với khóa được bảo vệ tách khỏi tài khoản quản trị DB.
- Cần tìm kiếm trên trường mã hóa: phải chọn đúng **CSFLE deterministic** hoặc **Queryable Encryption**, không thể giả định một truy vấn MongoDB thông thường sẽ hoạt động.

## 3. Bảng khả năng theo edition và cơ chế

Ở bảng dưới, **Có điều kiện** nghĩa là phải xét thêm version, topology, driver, cấu hình và quyền truy cập thành phần. Đây là ma trận định hướng, **không thay thế compatibility matrix chính thức**.

| Năng lực | Community Server | Enterprise Advanced tự quản lý | MongoDB Atlas |
| --- | --- | --- | --- |
| TLS giữa driver và server | Có, khi cấu hình TLS | Có, khi cấu hình TLS | Có, kết nối theo chính sách Atlas |
| Mã hóa tệp bằng **native encrypted WiredTiger storage engine** | Không phải tính năng native của Community; có thể mã hóa ở tầng OS/volume | Có, trên WiredTiger, khi cấu hình đúng | Encryption at rest mặc định; lớp mã hóa và CMK tùy sản phẩm/tier |
| **CSFLE explicit encryption** | Có điều kiện; server tương thích từ 4.2 | Có điều kiện; server tương thích từ 4.2 | Có điều kiện |
| **CSFLE automatic encryption** | **Không** theo ma trận cấp edition | Có điều kiện | Có điều kiện |
| **CSFLE automatic decryption** cho dữ liệu đã mã hóa | Có điều kiện, với client và khóa phù hợp | Có điều kiện | Có điều kiện |
| **QE explicit encryption** | Có điều kiện, với server và topology QE hỗ trợ | Có điều kiện | Có điều kiện |
| **QE automatic encryption** | **Không** theo ma trận cấp edition | Có điều kiện | Có điều kiện |
| **QE automatic decryption** cho dữ liệu đã mã hóa | Có điều kiện, với cấu hình client và khóa | Có điều kiện | Có điều kiện |
| Chế độ FIPS của MongoDB Server | Không mặc định có như tính năng Enterprise | Cần đối chiếu cấu hình và bản phân phối Enterprise | Cần xác nhận theo dịch vụ, tier và yêu cầu tuân thủ |

**Ba nhầm lẫn thường gặp:**

1. **Có TLS không đồng nghĩa có CSFLE/QE.** TLS bảo vệ kết nối; server vẫn xử lý plaintext đối với trường không được mã hóa ở client.
2. **Community hỗ trợ explicit không có nghĩa hỗ trợ automatic encryption.** Ứng dụng Community có thể chủ động gọi API mã hóa/giải mã, hoặc dùng cơ chế tự động giải mã tương ứng, nhưng tính năng phân tích truy vấn và mã hóa tự động có ràng buộc edition.
3. **Atlas có mã hóa lưu trữ mặc định không có nghĩa ứng dụng đã bật QE.** Field encryption phải thiết kế riêng; các lựa chọn khóa do khách hàng quản lý còn phụ thuộc sản phẩm/tier.

**Tình huống ví dụ:** một nhóm dùng Community Server 8.x trên replica set, Java driver hỗ trợ QE và có **mongodb-crypt**. Họ có thể đánh giá **QE explicit encryption**; họ **không** được kết luận “QE automatic encryption hoạt động” chỉ từ việc đã nâng server và thêm JAR. Với Enterprise/Atlas cũng phải cấu hình thành phần phân tích truy vấn và KMS.

## 4. Server version, topology và khả năng truy vấn

Khả năng tìm kiếm trên trường đã mã hóa không chỉ do driver quyết định. Server phải hiểu cấu trúc metadata và dạng truy vấn mã hóa đang sử dụng.

| Nhu cầu | Cơ chế | Mốc tương thích cần kiểm tra | Lưu ý quan trọng |
| --- | --- | --- | --- |
| Mã hóa trường và chỉ đọc sau khi giải mã | CSFLE randomized/explicit | CSFLE có từ MongoDB Server 4.2, kèm driver hỗ trợ | Không tìm bằng giá trị plaintext trên trường mã hóa randomized. |
| Tìm chính xác theo giá trị | CSFLE deterministic | Server và driver hỗ trợ CSFLE | Ciphertext của giá trị bằng nhau có thể trùng, để lộ mẫu tần suất. |
| Tìm chính xác với ciphertext được ngẫu nhiên hóa | QE equality | **MongoDB 7.0+ GA** và driver/QE runtime tương thích | QE 6.x public preview không tương thích trực tiếp với định dạng GA 7.0. |
| Tìm khoảng trên trường mã hóa | QE range | **MongoDB 8.0+**, driver và crypto library hỗ trợ query type tương ứng | Cần cấu hình đúng kiểu dữ liệu, miền giá trị, tham số và index mã hóa. |
| Tìm tiền tố, hậu tố, chuỗi con | QE prefix/suffix/substring | **MongoDB 9.0+ GA** và bộ driver/library hỗ trợ API mới | Bản preview 8.2–8.x có API/định dạng khác; không nâng cấp bằng cách đổi tên tùy ý. |

**Topology:** QE yêu cầu **replica set** hoặc **sharded cluster**; không hỗ trợ **standalone**. Ngoài version của binary, phải xét **featureCompatibilityVersion (FCV)** cùng yêu cầu cụ thể của tính năng. Việc một binary có version đủ cao chỉ là một phần của kiểm tra.

**Lưu ý về truy vấn:** các toán tử, aggregation stage, cập nhật, sharding, secondary read, đổi tên collection và đánh index đối với trường QE bị giới hạn riêng. Không suy ra rằng vì QE có tìm theo khoảng thì mọi lệnh **MongoTemplate.query(...)**, aggregation hay **MongoRepository** với toán tử bất kỳ đều được hỗ trợ. Phải thử đúng query shape và tham khảo mục **Supported Operations** và **Limitations** của phiên bản server dự kiến.

Ví dụ lựa chọn cho ứng dụng quản lý khách hàng:

| Trường | Nhu cầu | Phương án cần đánh giá |
| --- | --- | --- |
| **customer.notes** | Lưu và hiển thị, không tìm theo nội dung | CSFLE randomized hoặc QE unindexed; giải mã tại client |
| **customer.email** | Tìm bằng email chính xác | QE equality; hoặc CSFLE deterministic sau khi đánh giá nguy cơ lộ tần suất |
| **customer.salary** | Lọc khoảng lương | QE range trên stack tương thích; CSFLE deterministic không đáp ứng truy vấn khoảng |
| **customer.name** | Tìm tiền tố tên | QE string query trên MongoDB 9.0+ cùng driver/library hỗ trợ; kiểm tra giới hạn chuỗi |

Một số trường có cardinality thấp như trạng thái **ACTIVE/INACTIVE** không nên mặc định dùng deterministic encryption vì người quan sát có thể suy ra phân phối giá trị qua tần suất ciphertext.

## 5. Driver và thư viện mã hóa: ai làm việc gì?

Trong dự án Spring Data MongoDB, cần phân biệt rõ các thành phần sau:

| Thành phần | Vai trò | Kiểm tra khi chuẩn bị chạy |
| --- | --- | --- |
| **Spring Data MongoDB** | Mapping document, repository, MongoTemplate/ReactiveMongoTemplate và cấu hình truy cập DB | Phiên bản Spring Data/Spring Boot đang dùng và driver được quản lý |
| **mongodb-driver-sync** hoặc **mongodb-driver-reactivestreams** | Kết nối, BSON, lệnh MongoDB, API cấu hình mã hóa trên MongoClient | Version thực tế trên dependency tree; khả năng hỗ trợ thuật toán/QE |
| **org.mongodb:mongodb-crypt** | Thành phần Java được thêm để dùng in-use encryption | JAR có trong runtime và version phù hợp với Java driver |
| **libmongocrypt** | Thư viện mật mã lõi được driver/thành phần tích hợp sử dụng | Native binary tương thích OS/CPU, bản build và phiên bản |
| **crypt_shared** / **Automatic Encryption Shared Library** | Phân tích và viết lại các truy vấn cho automatic encryption; lựa chọn được khuyến nghị | Edition/quyền dùng, file shared library, đường dẫn và tương thích runtime |
| **mongocryptd** | Thành phần phân tích truy vấn kiểu cũ trong một số cấu hình CSFLE tự động | Có thể cần cho hệ thống cũ; **đã bị deprecated từ MongoDB 9.0**, nên ưu tiên crypt_shared |
| **KMS** và **Key Vault** | Quản lý khóa gốc và khóa mã hóa dữ liệu | Quyền truy cập, đường truyền tới KMS, vòng đời/backup và phân quyền vault |

**Không đánh đồng libmongocrypt với crypt_shared.** Thư viện lõi thực hiện công việc mật mã; thành phần query analysis hỗ trợ phát hiện/biến đổi truy vấn cần mã hóa tự động. **mongocryptd không phải nơi lưu khóa và không trực tiếp mã hóa dữ liệu**. Cài thêm driver hoặc JAR không tự tải sẵn, cấp phép hay cấu hình toàn bộ các thành phần khác.

Các thành phần của Java driver thường được quản lý bằng **Bill of Materials (BOM)** hoặc dependency management của Spring Boot. Không tự ghép phiên bản **mongodb-crypt** mới nhất với một Java driver cũ khi chưa kiểm tra hỗ trợ. Khi build artifact triển khai bằng Docker, cần kiểm tra cả **runtime image**: native library có thể có trên máy phát triển nhưng thiếu trong container hoặc sai kiến trúc CPU.

Ví dụ dependency Maven cho in-use encryption khi dự án đã dùng dependency management phù hợp:

~~~xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-crypt</artifactId>
</dependency>
~~~

Không nên thêm một phiên bản cố định một cách độc lập nếu nó xung đột với driver version được Spring quản lý. Đối với Java reactive, xác nhận tính năng mã hóa được **bản driver reactive** đang dùng hỗ trợ; ví dụ Java sync không bảo đảm một API y hệt tồn tại trong toàn bộ bản reactive.

## 6. Khóa, vault và dịch vụ KMS

Ngay cả khi edition và driver đều hỗ trợ, job mã hóa vẫn thất bại nếu ứng dụng không lấy được khóa:

- **Data Encryption Key (DEK):** dùng để mã hóa từng trường dữ liệu. DEK ở dạng được bảo vệ sẽ được lưu trong collection **Key Vault**.
- **Customer Master Key (CMK):** bảo vệ DEK; thường nằm tại AWS KMS, Azure Key Vault, Google Cloud KMS, KMIP hoặc một lựa chọn hỗ trợ khác.
- **Key Vault collection:** MongoDB collection chuyên lưu tài liệu khóa; đây **không phải** nơi nên đặt CMK plaintext.
- **KMS credentials và quyền mạng:** ứng dụng cần có khả năng xác thực, gọi KMS và đọc được DEK liên quan. Xác thực MongoDB và xác thực KMS là hai bài toán riêng.

~~~mermaid
sequenceDiagram
    participant App as "Ứng dụng Spring"
    participant Driver as "MongoDB Driver + Crypto"
    participant KMS as "KMS / Master Key"
    participant Vault as "MongoDB Key Vault"
    participant DB as "MongoDB Collection"
    App->>Driver: "Lưu document có trường nhạy cảm"
    Driver->>Vault: "Đọc DEK đã được bảo vệ"
    Driver->>KMS: "Yêu cầu mở khóa DEK theo quyền"
    KMS-->>Driver: "Phản hồi vật liệu khóa hợp lệ"
    Driver->>Driver: "Mã hóa trường tại client"
    Driver->>DB: "Gửi BSON chứa ciphertext qua TLS"
    DB-->>Driver: "Đọc ciphertext"
    Driver->>Driver: "Giải mã ở client có quyền khóa"
    Driver-->>App: "Giá trị đã giải mã"
~~~

Luồng trên là hình minh họa, không phải thứ tự lời gọi mạng cố định của từng driver. Driver có thể cache thông tin phù hợp với chính sách thư viện. Không hardcode CMK/DEK, không ghi plaintext hoặc vật liệu khóa ra log, và phải lập kế hoạch rotation/khôi phục khóa. **Mất khóa có thể khiến ciphertext không thể giải mã**, dù dữ liệu MongoDB vẫn còn nguyên vẹn.

## 7. Đối chiếu cấu hình thực tế trước khi viết code

Một lần kiểm tra hợp lệ cần ghi nhận đủ **server version, edition/deployment, topology, FCV, driver version, crypto dependency, query analysis component, KMS và yêu cầu query**. Không dùng một dòng **db.version()** làm “chứng cứ” duy nhất.

### Bước 1 — Xác minh server và topology

Chạy trong **mongosh** với tài khoản có quyền phù hợp:

~~~javascript
db.version();

db.adminCommand({ buildInfo: 1 });

db.adminCommand({ hello: 1 });

// Có thể cần quyền cao hơn; môi trường managed có thể giới hạn.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

Đọc kết quả theo mục đích:

- **buildInfo.version:** version binary server, là đầu vào cho ma trận.
- **buildInfo.modules** và thông tin triển khai: một dấu hiệu để xem xét edition; đối với Atlas hãy xác nhận loại cluster/tier từ hệ thống quản trị Atlas, không suy luận hoàn toàn từ chuỗi version.
- **hello.setName**, danh sách host hoặc mô tả topology: phân biệt replica set với standalone; với kết nối qua **mongos**, xác nhận đó là sharded cluster.
- **featureCompatibilityVersion:** kiểm tra trạng thái tương thích tính năng ở server. Nếu lệnh không có quyền, ghi rõ **chưa xác minh**, nhờ đội quản trị cung cấp thông tin thay vì đoán.

Nếu cần kiểm tra TLS từ client, kiểm tra connection string và cấu hình SSL của driver; kiểm tra chứng chỉ hợp lệ trong môi trường thật. Đừng vô hiệu hóa hostname verification hoặc cho phép chứng chỉ không tin cậy để “chạy được”. Trong Atlas dùng cấu hình TLS theo hướng dẫn của dịch vụ.

### Bước 2 — Ghi nhận phiên bản phía Java

Kiểm tra dependency tree của đúng artifact sẽ triển khai (Maven hoặc Gradle) và ghi lại ít nhất:

~~~text
Spring Boot:                 <version>
Spring Data MongoDB:         <version>
mongodb-driver-sync/reactive:<version>
mongodb-crypt:               <version>
libmongocrypt/native:        <version/hệ điều hành/kiến trúc>
crypt_shared:                <version/đường dẫn nếu dùng>
MongoDB Server + FCV:        <version + FCV>
Edition / Deployment:        <Community | Enterprise | Atlas + tier>
Topology:                    <standalone | replica set | sharded>
KMS provider:                <provider + thông tin truy cập, không ghi secret>
Feature / Query:             <CSFLE/QE + explicit/automatic + loại truy vấn>
~~~

Mỗi **version** và điều kiện tối thiểu phải được xác nhận qua compatibility matrix của chính loại driver và encryption feature; phiên bản ở một bài hướng dẫn cũ có thể không còn đúng với runtime mới.

### Bước 3 — Chọn chế độ mã hóa

| Điều kiện ứng dụng | Hướng triển khai |
| --- | --- |
| Community và muốn chủ động mã hóa từng field | Xem **CSFLE explicit** hoặc **QE explicit** tùy server/topology/query; ứng dụng chịu trách nhiệm encrypt trước khi ghi và encrypt giá trị tìm kiếm đúng API. |
| Enterprise/Atlas và muốn tự động mã hóa | Xem **automatic CSFLE** hoặc **automatic QE**, cấu hình **AutoEncryptionSettings**, query analysis component và quy tắc/schema cho đúng loại tính năng. |
| Có ciphertext cần đọc nhưng không muốn client tự động mã hóa write | Xem cơ chế **automatic decryption** cùng cấu hình bypass tương ứng; kiểm tra API theo feature và driver version. |
| Chỉ cần mã hóa bản sao lưu/ổ đĩa | Cấu hình **at-rest encryption** ở lớp hạ tầng hoặc native engine đúng edition; không gọi đó là field encryption. |

Hai chế độ **CSFLE automatic encryption** và **QE automatic encryption** có metadata/quy tắc riêng. Không dùng **schemaMap** của CSFLE làm thay thế cho **encryptedFieldsMap** của QE. Với QE phải tạo collection và cấu trúc encrypted-fields hỗ trợ theo quy trình chính thức; không thể đơn thuần thêm thuộc tính trên một collection đã có rồi kỳ vọng mọi truy vấn được mã hóa.

## 8. Ví dụ cấu hình Java driver để tích hợp với MongoTemplate

Spring Data MongoDB thực hiện thao tác qua **MongoClient**. Cấu hình mã hóa tự động thường được gắn ở **MongoClientSettings**; **MongoTemplate** hoặc repository dùng client đó để thực hiện I/O. Ví dụ sau thể hiện đúng các điểm nối cần kiểm tra với **CSFLE automatic** trên Enterprise/Atlas.

~~~java
import com.mongodb.AutoEncryptionSettings;
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.Map;
import org.bson.BsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class MongoCsfleClientFactory {

    // Chỉ là skeleton cấu hình: các map và đường dẫn phải được cấp từ
    // hệ thống quản lý bí mật và schema thực tế của ứng dụng.
    public static MongoClient create(
            String connectionString,
            Map<String, Map<String, Object>> kmsProviders,
            Map<String, BsonDocument> csfleSchemaMap,
            String cryptSharedLibraryFile) {

        AutoEncryptionSettings encryption = AutoEncryptionSettings.builder()
            .keyVaultNamespace("keyvault.datakeys")
            .kmsProviders(kmsProviders)
            .schemaMap(csfleSchemaMap)
            .extraOptions(Map.of(
                "cryptSharedLibPath", cryptSharedLibraryFile,
                "cryptSharedLibRequired", true
            ))
            .build();

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(connectionString))
            .autoEncryptionSettings(encryption)
            .build();

        return MongoClients.create(settings);
    }

    public static MongoTemplate createTemplate(MongoClient client) {
        return new MongoTemplate(client, "appdb");
    }
}
~~~

**Đọc ví dụ đúng cách:**

- **kmsProviders** chứa cấu hình KMS phù hợp, không đặt bí mật ở source code. **csfleSchemaMap** phải có key namespace đầy đủ (ví dụ **appdb.customers**) và một schema CSFLE hợp lệ cho trường cần mã hóa. Nếu map trống và server cũng không có schema encryption thích hợp thì client không tự động mã hóa trường mong muốn.
- **cryptSharedLibraryFile** phải trỏ tới **file** thư viện thực tế đúng hệ điều hành/CPU, không phải thư mục. **cryptSharedLibRequired=true** giúp lỗi rõ ràng nếu thư viện bắt buộc không được tải.
- Đây là **khung tích hợp**, chưa phải mẫu production hoàn chỉnh: còn phải tạo DEK/CMK, cấp quyền Key Vault/KMS, chọn TLS, thiết lập cấu hình schema chính xác, kiểm soát vòng đời client và kiểm thử ciphertext lưu trong DB.
- Trong ứng dụng Spring Boot, đăng ký đúng **MongoClient bean** để MongoTemplate/repository thực sự dùng client đã cấu hình; nếu tạo một MongoClient mới không có auto-encryption cho tác vụ ghi thì tác vụ đó có thể không được mã hóa.
- Với **Queryable Encryption**, dùng cấu hình encrypted-fields và quy trình tạo collection QE tương ứng (chẳng hạn **encryptedFieldsMap**), không sao chép nguyên schema CSFLE ở trên.
- Với **explicit encryption**, dùng API **ClientEncryption** của driver và lưu ciphertext phù hợp kiểu BSON; bản thân lời gọi **MongoTemplate.save** thông thường không tự suy ra trường nào phải encrypt khi chưa có cơ chế automatic.

Mã hóa phía client có thể ảnh hưởng đến truy vấn **Criteria**, projection, aggregation, index và mapping các trường nhạy cảm. Repository method suy ra từ tên hàm không mặc nhiên chứng minh rằng phép truy vấn trên ciphertext được hỗ trợ. Hãy kiểm thử query shape qua chính bean và đúng phiên bản driver sẽ dùng trong sản xuất.

## 9. Bảng quyết định từ yêu cầu tới cấu hình

Giả sử đội dự án cần lưu **email**, **mã số giấy tờ**, **ghi chú nội bộ** và **thu nhập** của khách hàng. Các câu hỏi đặt ra:

1. **Ai không được thấy dữ liệu?** Chỉ người lấy được ổ đĩa, hay cả quản trị viên có quyền query DB?
2. **Trường nào cần truy vấn và bằng toán tử gì?** Equal, range, prefix, aggregation?
3. **Server là gì?** Community, Enterprise Advanced hay Atlas; phiên bản, topology, FCV?
4. **Ứng dụng có sửa được code mã hóa từng thao tác không?** Nếu không, automatic có đáp ứng đủ edition và thành phần query analysis?
5. **Bộ driver và crypto library có hỗ trợ loại mã hóa và query type đó không?** Đã xác minh đúng artifact build và container image chưa?
6. **Ai giữ khóa?** KMS ở đâu, ai có quyền giải mã, làm sao phục hồi khi mất quyền?

| Bối cảnh | Lựa chọn sơ bộ | Điều kiện quyết định |
| --- | --- | --- |
| Community, cần bí mật dữ liệu khỏi DB admin, chỉ đọc trường sau khi lấy document | **CSFLE explicit randomized** | Driver + mongodb-crypt, DEK/KMS, mã hóa và giải mã tại ứng dụng |
| Community, cần tìm email chính xác | **CSFLE deterministic** hoặc **QE explicit equality** | Đánh giá rò rỉ tần suất của deterministic; QE cần version/topology và API phù hợp |
| Enterprise/Atlas, không muốn thay tất cả lệnh ghi | **CSFLE/QE automatic** | Edition, query analysis component, schema/metadata, driver, KMS, kiểm thử thực tế |
| Cần lọc khoảng thu nhập trên ciphertext | **QE range** | Server 8.0+ cùng driver/library hỗ trợ và encrypted collection đúng chuẩn |
| Cần tìm chuỗi con trong tên mã hóa | **QE string** | Server 9.0+ GA cùng bộ driver/library hỗ trợ, kiểm tra hạn chế và chi phí |
| Chỉ cần bảo vệ volume hoặc bản sao lưu | **At-rest encryption** | Xác minh lớp hỗ trợ của edition/hạ tầng; không giải quyết yêu cầu che dữ liệu khỏi query DBA |

Lưu ý: khả năng mã hóa tìm kiếm theo văn bản **không đồng nghĩa** toàn bộ tính năng search engine, regex hoặc full-text của MongoDB đều dùng được trên ciphertext. Hãy xác định toán tử được hỗ trợ, hiệu năng và rủi ro suy luận từ mẫu truy vấn trước khi chọn giải pháp.

## 10. Kiểm thử tương thích: chứng minh bằng hành vi

Với môi trường thử nghiệm gần giống production, nên lập một **bảng bằng chứng** trước khi quyết định go-live:

| Kiểm thử | Cách thực hiện | Điều kiện đạt |
| --- | --- | --- |
| Kết nối TLS | Dùng chính cấu hình MongoClient production với trust store hợp lệ | Kết nối được, xác thực hostname đúng; cấu hình không bỏ kiểm tra chứng chỉ |
| Hỗ trợ edition và topology | Ghi version, FCV, edition, topology và đối chiếu tài liệu feature | Tất cả tiền điều kiện chính thức đều thỏa |
| Thư viện crypto có thể nạp | Khởi tạo MongoClient mã hóa trong runtime thật | Không lỗi native library, crypt_shared hay ABI/architecture |
| KMS/DEK truy cập được | Tạo hoặc đọc DEK thử với key vault riêng | Khóa được giải mã bởi tài khoản ứng dụng có quyền |
| Không lọt plaintext khi lưu | Ghi mẫu có trường nhạy cảm qua client đã mã hóa; đọc lại bằng client **không có khóa** | Trường cần bảo vệ lưu dạng encrypted BSON/ciphertext, không hiện giá trị rõ |
| Giải mã đúng quyền | Đọc cùng document bằng client có quyền và client không có quyền | Client được phép giải mã nhận đúng giá trị; client không có khóa không giải mã được |
| Truy vấn trên ciphertext | Thử đúng **Criteria/query type** (equal, range, string nếu cần) | Trả đúng tập kết quả theo giới hạn của tính năng |
| Truy vấn không hỗ trợ | Thử toán tử đã biết không hỗ trợ trên trường mã hóa | Hệ thống từ chối có kiểm soát, không tự chuyển sang truy vấn plaintext nguy hiểm |
| Khác phiên bản runtime | Chạy cùng bài thử trên image/build sẽ triển khai | Không khác API/native library/định dạng so với môi trường kiểm thử |
| Thu hồi quyền KMS và khôi phục | Thử môi trường cô lập, không làm trên production | Lỗi có thể quan sát, không lộ secret; quy trình khôi phục có tài liệu |

**Tại sao cần client thứ hai không có khóa?** Vì nếu chỉ kiểm thử bằng client đã bật automatic decryption, dữ liệu đọc ra luôn có vẻ là plaintext đúng như thiết kế. Điều đó **không chứng minh dữ liệu được lưu ciphertext**; client có khóa đã giải mã kết quả cho ứng dụng. Dùng đường đọc không tự động giải mã và đối chiếu raw BSON giúp kiểm tra hiệu quả mã hóa thực tế.

Đối với **@DataMongoTest** và Testcontainers, phân biệt rõ test chức năng mapping với test tương thích mã hóa. Một MongoDB Testcontainer Community standalone có thể kiểm thử CRUD và một số thao tác CSFLE explicit, nhưng **không đủ** để xác minh QE yêu cầu replica set/sharding, automatic encryption theo edition hoặc thư viện native được cấp trong môi trường sản xuất. Không đánh dấu toàn bộ stack là tương thích chỉ vì repository test xanh.

Các metric nên theo dõi trong bài thử tải: latency p95/p99 khi encrypt/decrypt, CPU của ứng dụng, thời gian KMS, kích thước ciphertext, chi phí index/metadata QE, kích thước bộ nhớ và tác động đến tốc độ truy vấn. Với **ReactiveMongoTemplate**, cần thêm kiểm thử backpressure, concurrency, retry và đường đi mã hóa bất đồng bộ; đừng suy ra hiệu năng từ bài thử với driver sync.

## 11. Chẩn đoán lỗi theo đúng lớp

| Dấu hiệu | Khả năng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Kết nối báo TLS handshake/certificate error | Trust store, hostname, CA, thời hạn chứng chỉ | Sửa chuỗi tin cậy và chứng chỉ, không tắt xác minh TLS |
| Mã hóa auto không thực hiện, hoặc báo edition unsupported | Community đang dùng automatic encryption; query analysis thiếu | Đối chiếu edition, chọn explicit nếu phù hợp hoặc chuyển sang edition/tier hỗ trợ |
| Native library load failed | Sai đường dẫn, OS/CPU, JAR/native version, quyền file | Xác minh artifact runtime và compatibility matrix của driver |
| Không tìm thấy **crypt_shared** | Chưa cài file, sai đường dẫn, không đủ quyền | Cài/đóng gói thư viện đúng edition, cấu hình **cryptSharedLibPath** tới file |
| KMS authentication/permission error | Credential hết hạn, IAM/role sai, lỗi mạng hoặc master key bị khóa | Kiểm tra quyền và đường truyền tới KMS bằng môi trường an toàn |
| Đọc ra ciphertext mà không giải mã | Client không bật decryption, không có KMS key hoặc Key Vault | Xác minh client thực tế của MongoTemplate/repository và quyền khóa |
| Truy vấn range/prefix lỗi | Server, FCV, driver, crypto library chưa hỗ trợ query type | Quay lại ma trận version và định dạng trường/collection |
| Ghi plaintext dù kỳ vọng ciphertext | Không có schema/metadata đúng hoặc ghi bằng client khác | Kiểm tra schema map, encryptedFields, namespace và bean đang dùng |
| Bản preview QE không mở được bằng cấu hình GA | Định dạng QE khác thế hệ | Lập kế hoạch giải mã và di trú dữ liệu theo hướng dẫn version tương ứng |

Không ghi plaintext, raw DEK, CMK, URI có mật khẩu hoặc thông tin người dùng nhạy cảm vào log chẩn đoán. Khi cần điều tra sâu, tạo mẫu dữ liệu giả và log ID lệnh, loại lỗi, phiên bản driver, thư viện đã nạp cùng correlation ID.

## 12. Checklist phê duyệt lựa chọn công nghệ

- [ ] Mô tả được mối đe dọa cần chống: đường truyền, lưu trữ hay người có quyền truy cập server.
- [ ] Đã xác nhận **edition**, loại Atlas cluster nếu có, **server version**, **FCV** và **topology**.
- [ ] Đã ghi version **Spring Data MongoDB**, Java driver sync/reactive, **mongodb-crypt**, native **libmongocrypt** và **crypt_shared** nếu dùng.
- [ ] Đã xác nhận tính năng cần dùng là **CSFLE** hay **QE**, **explicit** hay **automatic**, và cách giải mã.
- [ ] Đã đối chiếu loại truy vấn thực tế với version và giới hạn được tài liệu chính thức hỗ trợ.
- [ ] Đã cấu hình và thử **KMS**, **Key Vault**, DEK/CMK, chính sách truy cập, rotation và khôi phục.
- [ ] Đã xác minh document được lưu ciphertext bằng cách đọc thô từ một client không giải mã.
- [ ] Đã chạy thử qua đúng **MongoClient** được MongoTemplate, repository hoặc ReactiveMongoTemplate sử dụng.
- [ ] Đã đo hiệu năng và kiểm thử lỗi TLS, native library, KMS và truy vấn không tương thích.
- [ ] Có biên bản nêu rõ những tính năng **chưa hỗ trợ**, chưa được thử hoặc cần nâng cấp.

## 13. Tài liệu tham khảo để xác nhận lại phiên bản

Đọc tài liệu của đúng **phiên bản** triển khai, đặc biệt khi chuẩn bị nâng MongoDB Server hoặc Java driver:

1. [MongoDB — In-Use Encryption (Java Sync Driver)](https://www.mongodb.com/docs/drivers/java/sync/current/security/encrypt-fields/): dependency **mongodb-crypt**, CSFLE, QE và khả năng truy vấn.
2. [MongoDB — Compatibility: QE và CSFLE](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/compatibility/): version, edition và driver; chọn đúng encryption feature và Java driver.
3. [MongoDB — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/): mô hình, hạn chế và các kiểu truy vấn được hỗ trợ.
4. [MongoDB — Queryable Encryption Limitations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/limitations/): topology, collection, sharding và các thao tác không hỗ trợ.
5. [MongoDB — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): automatic/explicit encryption và quản lý khóa.
6. [MongoDB — Install CSFLE Query Analysis Component](https://www.mongodb.com/docs/manual/core/csfle/reference/install-library/): **crypt_shared**, **mongocryptd** và điều kiện runtime.
7. [MongoDB — Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/): native WiredTiger encrypted storage engine của Enterprise.
8. [MongoDB Atlas — Encryption at Rest Overview](https://www.mongodb.com/docs/atlas/security-encryption-at-rest-overview/): các lớp mã hóa mặc định và customer-managed key theo sản phẩm.
9. [MongoDB — TLS/SSL Transport Encryption](https://www.mongodb.com/docs/manual/core/security-transport-encryption/): xác thực và mã hóa đường truyền.
10. [MongoDB Java Driver — AutoEncryptionSettings.Builder](https://mongodb.github.io/mongo-java-driver/5.12/apidocs/driver-core/com/mongodb/AutoEncryptionSettings.Builder.html): các lựa chọn **schemaMap**, **encryptedFieldsMap** và đường dẫn crypt_shared.

**Thông điệp cần nhớ:** “MongoDB hỗ trợ mã hóa” không đủ để ra quyết định. Chỉ nên xác nhận một tính năng **sẵn sàng triển khai** sau khi chứng minh đủ **đúng lớp bảo vệ + đúng edition + đúng server/FCV/topology + đúng driver/library + đúng quản lý khóa + đúng kiểu truy vấn**, và đã kiểm thử từ đường đi thực tế của ứng dụng Spring Data MongoDB.
