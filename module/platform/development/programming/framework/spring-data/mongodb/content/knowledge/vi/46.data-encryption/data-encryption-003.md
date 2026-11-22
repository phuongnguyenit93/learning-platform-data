# Key vault, data encryption key và KMS provider

## 1. Ba thành phần trong bài toán mã hóa dữ liệu MongoDB

Khi xây dựng ứng dụng **Spring Data MongoDB**, lập trình viên thường dùng **MongoTemplate** hoặc **MongoRepository** để lưu document. Với các trường nhạy cảm như số định danh, thông tin thanh toán hoặc dữ liệu cá nhân, cần xác định **ai được nhìn thấy bản rõ**, **khóa mã hóa nằm ở đâu** và **ứng dụng lấy khóa như thế nào**. MongoDB cung cấp cơ chế **mã hóa ở phía client** (client-side field level encryption, CSFLE; và Queryable Encryption ở các trường hợp được hỗ trợ), cho phép chọn các trường để mã hóa trước khi chúng rời khỏi ứng dụng.

Ba khái niệm trọng tâm:

| Khái niệm | Vai trò | Thực tế lưu ở đâu? |
| --- | --- | --- |
| **Key vault** | Collection lưu thông tin và bản **đã được mã hóa** của data encryption key (DEK); giúp client tìm được khóa cần dùng. | Một collection MongoDB do ứng dụng chỉ định, ví dụ **encryption.__keyVault**. |
| **Data Encryption Key (DEK)** | Khóa đối xứng dùng để mã hóa/giải mã giá trị dữ liệu nhạy cảm. | Dạng được bọc (wrapped/encrypted) trong key vault; vật liệu khóa ở dạng rõ chỉ được xử lý tạm thời trong phía client khi cần. |
| **KMS provider** | Cách client truy cập **khóa chủ (master key/KEK)** để bọc hoặc mở bọc DEK. | Có thể là dịch vụ quản lý khóa như AWS KMS, Azure Key Vault, Google Cloud KMS, KMIP hoặc khóa local dùng khi phát triển. |

**KMS provider không phải bản thân DEK.** Khóa chủ được quản lý qua KMS; DEK phục vụ mã hóa giá trị document; key vault giữ metadata và DEK đã được mã hóa. Đó là cơ chế **envelope encryption** (mã hóa theo lớp khóa).

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ được luồng mã hóa/giải mã giữa ứng dụng Spring, key vault và KMS provider.
2. Nhận diện các trường quan trọng của một document trong key vault.
3. Tạo và sử dụng DEK bằng MongoDB Java Driver trong ứng dụng Spring.
4. Chọn local KMS để học và chọn KMS ngoài cho môi trường triển khai.
5. Lập kế hoạch quyền truy cập, sao lưu, rotation, khắc phục lỗi và tích hợp với MongoTemplate/repository.

## 2. Phân biệt các lớp mã hóa

Trước khi cấu hình key vault, cần biết nó giải quyết đúng loại bảo vệ nào.

| Lớp bảo vệ | Bảo vệ điều gì? | Key vault và DEK có liên quan không? |
| --- | --- | --- |
| **TLS trên đường truyền** | Dữ liệu truyền giữa client và MongoDB trước việc nghe lén/sửa đổi trên mạng. | Không trực tiếp; TLS bảo vệ kênh kết nối. |
| **Encryption at rest** | Tệp dữ liệu, thiết bị hoặc bản lưu trữ khi nằm trên hệ thống lưu trữ. | Không trực tiếp theo cơ chế client-side; server hoặc nền tảng lưu trữ quản lý riêng. |
| **Client-Side Field Level Encryption (CSFLE)** | Giá trị các trường được chọn được mã hóa tại client trước khi gửi lên MongoDB. | Có: dùng DEK và key vault; thao tác giải mã cần truy cập DEK và KMS. |
| **Queryable Encryption (QE)** | Mã hóa phía client và hỗ trợ một số loại truy vấn trên dữ liệu mã hóa theo tính năng/phiên bản hỗ trợ. | Có: cũng cần key vault, DEK và KMS; cấu hình truy vấn, metadata và điều kiện triển khai có thêm yêu cầu. |

**Ví dụ:** TLS không ngăn người quản trị database có quyền đọc nhìn thấy giá trị trường bản rõ đã lưu; encryption at rest không có nghĩa giá trị được mã hóa riêng ở tầng document. Với mã hóa phía client, chỉ các trường và đường truy cập được cấu hình phù hợp mới được bảo vệ. Các trường không mã hóa, tên collection, metadata và đặc điểm truy cập vẫn có thể lộ một phần thông tin.

## 3. Envelope encryption diễn ra như thế nào?

Giả sử ứng dụng lưu trường **citizenId** của document **customers**.

~~~mermaid
flowchart TB
    App["Spring Data MongoDB / Java Driver<br/>phía client"]
    Vault[("MongoDB Key Vault<br/>encryption.__keyVault<br/>DEK đã được bọc")]
    KMS["KMS provider<br/>quyền truy cập master key / KEK"]
    Data[("MongoDB customers<br/>trường mã hóa BSON BinData subtype 6")]

    App -->|"1. Tìm metadata và DEK đã bọc"| Vault
    Vault -->|"2. Trả về DEK đã bọc"| App
    App <-->|"3. Gửi yêu cầu bọc / mở bọc DEK"| KMS
    App -->|"4. Mã hóa trường rồi ghi ciphertext"| Data
    Data -->|"5. Đọc ciphertext; giải mã ở client"| App
~~~

### Khi tạo một DEK

1. Client sinh ngẫu nhiên vật liệu khóa DEK bằng cơ chế mã hóa của driver.
2. Client dùng KMS provider đã khai báo để mã hóa (wrap) vật liệu DEK bằng khóa chủ.
3. Client lưu document metadata và **DEK đã được bọc** vào key vault, nhận về **key ID** để tham chiếu.
4. Ứng dụng sử dụng key ID hoặc **keyAltNames** để xác định DEK cần dùng cho từng trường.

### Khi ghi dữ liệu đã mã hóa

1. Driver đọc thông tin DEK từ key vault khi cần; phần DEK đã bọc được mở bằng khóa chủ thông qua KMS provider.
2. Tại phía client, thư viện mã hóa dùng DEK để mã hóa giá trị trường.
3. MongoDB nhận và lưu ciphertext. Đối với các giá trị mã hóa phía client, định dạng BSON mã hóa thường có **binary subtype 6**.

### Khi đọc dữ liệu đã mã hóa

1. Ứng dụng nhận ciphertext từ MongoDB.
2. Client xác định DEK cần dùng từ thông tin trong giá trị mã hóa.
3. Driver lấy DEK từ key vault, yêu cầu KMS mở bọc nếu chưa có khóa phù hợp trong bộ nhớ/cache.
4. Client giải mã và trả bản rõ cho đoạn code có quyền dùng giá trị đó.

KMS có thể được gọi ít hơn số lượng document đọc/ghi vì driver có thể cache DEK đã mở bọc. Không nên giả định **mỗi lần đọc đều gọi KMS**, cũng không nên dựa vào cache để bỏ qua thiết kế quyền truy cập và độ sẵn sàng của KMS. Quyền đọc MongoDB một mình chưa đủ để giải mã nếu thiếu khóa và cấu hình client phù hợp.

## 4. Key vault là gì và có cấu trúc ra sao?

Key vault là một **collection thông thường trong MongoDB**, được xác định bằng chuỗi **database.collection** trong cấu hình driver. Ví dụ:

~~~text
Database:   encryption
Collection: __keyVault
Namespace:  encryption.__keyVault
~~~

Đây là namespace ví dụ, không phải tên bắt buộc. Key vault có thể nằm cùng cluster với dữ liệu ứng dụng hoặc ở một deployment phù hợp với chính sách bảo mật; driver phải được cấu hình kết nối chính xác và có quyền truy cập.

Một document khóa có dạng khái niệm:

~~~javascript
{
  _id: UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
  keyAltNames: ["customers-citizen-id-v1"],
  keyMaterial: BinData(0, "<DEK da duoc ma hoa>"),
  creationDate: ISODate("2026-10-01T00:00:00Z"),
  updateDate: ISODate("2026-10-01T00:00:00Z"),
  status: 0,
  masterKey: {
    provider: "aws",
    region: "ap-southeast-1",
    key: "arn:aws:kms:ap-southeast-1:123456789012:key/example-key-id"
  }
}
~~~

Đây chỉ là ví dụ hình dạng document để đọc hiểu; định dạng chi tiết phụ thuộc phương thức mã hóa và driver. Các trường đáng chú ý:

| Field | Ý nghĩa |
| --- | --- |
| **_id** | ID duy nhất của DEK, thường biểu diễn UUID BSON. Có thể được nhúng để xác định khóa khi giải mã dữ liệu đã mã hóa. |
| **keyMaterial** | Vật liệu DEK đã được mã hóa bằng master key. Không phải bản rõ của khóa dữ liệu. |
| **masterKey** | Metadata xác định KMS provider và khóa chủ liên quan, ví dụ khóa AWS KMS trong vùng cụ thể. |
| **keyAltNames** | Bí danh mang ý nghĩa nghiệp vụ, ví dụ **customers-citizen-id-v1**, dùng để tra cứu khóa dễ hơn. |
| **creationDate/updateDate** | Thời điểm tạo/cập nhật thông tin khóa, hữu ích cho kiểm toán và vận hành. |
| **status** | Trạng thái của tài liệu khóa theo biểu diễn của cơ chế mã hóa. Không nên tự ý sửa để “vô hiệu hóa” khóa. |

**Key vault là dữ liệu quan trọng phải sao lưu.** Nếu mất key vault, client có thể không tìm lại được DEK để giải mã, kể cả khi dữ liệu document vẫn còn. Nếu mất quyền truy cập khóa chủ ở KMS, DEK đã bọc cũng có thể trở nên vô dụng.

### Vì sao cần unique index trên keyAltNames?

Khi nhiều tiến trình cùng tạo khóa, bí danh phải xác định được duy nhất một DEK. MongoDB khuyến nghị tạo **unique partial index** cho **keyAltNames** để tránh nhiều khóa trùng bí danh trong key vault.

Chạy qua **mongosh** sau khi chuẩn bị database và quyền:

~~~javascript
db.getSiblingDB("encryption")
  .getCollection("__keyVault")
  .createIndex(
    { keyAltNames: 1 },
    {
      unique: true,
      partialFilterExpression: { keyAltNames: { $exists: true } }
    }
  );
~~~

Index này không thay thế quyền truy cập database. Nó cũng không có nghĩa rằng **key ID** và **keyAltName** là một: một DEK có một ID và có thể được gắn các bí danh theo API hỗ trợ. Trong code nghiệp vụ, đặt bí danh ổn định và tránh sinh DEK mới mỗi request.

## 5. Data Encryption Key (DEK) dùng để làm gì?

DEK là khóa mã hóa **giá trị dữ liệu**. Đây là khóa khác với khóa chủ của KMS và khác với mật khẩu kết nối MongoDB.

Ví dụ hệ thống quản lý khách hàng có thể dùng:

- **DEK A:** mã hóa trường citizenId của khách hàng.
- **DEK B:** mã hóa thông tin liên hệ nhạy cảm.
- **DEK C:** mã hóa dữ liệu một nhóm tenant có chính sách cách ly riêng.

Không có yêu cầu bắt buộc phải tạo đúng một DEK cho một document, một collection hoặc một tenant; chiến lược phân chia DEK tùy mức độ tách biệt, quyền truy cập và chi phí vận hành. Dùng quá ít DEK có thể mở rộng phạm vi ảnh hưởng khi khóa bị lộ; dùng quá nhiều DEK có thể làm vòng đời và quản trị phức tạp.

### Key ID so với keyAltName

| Truy cập theo | Phù hợp khi | Cần chú ý |
| --- | --- | --- |
| **Key ID** | Cần tham chiếu khóa cụ thể, ổn định và không mơ hồ. | Phải lưu hoặc xác định đúng UUID của khóa. |
| **keyAltName** | Muốn cấu hình theo bí danh dễ đọc cho từng nhóm dữ liệu. | Phải kiểm soát duy nhất bí danh và chính sách thay đổi/thu hồi. |

Ciphertext mã hóa phía client có thông tin nhận diện khóa cần thiết để driver tìm DEK giải mã. **Đổi bí danh không đồng nghĩa mã hóa lại ciphertext**; thay DEK mới để dữ liệu thực sự dùng khóa khác lại là một quy trình riêng.

## 6. KMS provider và khóa chủ

**Key Management Service (KMS)** quản lý hoặc cung cấp quyền truy cập đến **key-encryption key (KEK/master key)**. Client dùng khóa này để bọc/mở bọc DEK. Quyền KMS có thể tách riêng khỏi quyền đọc/ghi document và key vault.

MongoDB hỗ trợ các nhóm provider phổ biến tùy phiên bản driver và môi trường:

| Provider | Trường hợp dùng | Điều kiện triển khai cần xem xét |
| --- | --- | --- |
| **local** | Học, thử nghiệm và môi trường kiểm thử có kiểm soát. | Cung cấp khóa chủ **96 byte** tại phía client; tự chịu trách nhiệm lưu trữ, phân phối và sao lưu khóa. |
| **AWS KMS** | Ứng dụng dùng AWS và quyền IAM/KMS. | Cần cấu hình vùng, định danh KMS key, quyền và kết nối tới KMS. |
| **Azure Key Vault** | Ứng dụng có hạ tầng và danh tính Azure. | Cần endpoint/định danh khóa, quyền và cơ chế cấp danh tính phù hợp. |
| **Google Cloud KMS** | Ứng dụng có hạ tầng và danh tính Google Cloud. | Cần thông tin resource/phiên bản khóa, quyền và thông tin xác thực phù hợp. |
| **KMIP** | Doanh nghiệp dùng hệ thống quản lý khóa tương thích KMIP. | Cần máy chủ KMIP, TLS/chứng chỉ và chính sách quyền. |

Ba giá trị thường dễ nhầm:

1. **Tên provider** (ví dụ **aws**, **local**) giúp driver chọn cơ chế KMS.
2. **Thông tin xác thực provider** cho driver biết client có quyền gọi KMS bằng cách nào.
3. **Định danh master key** chỉ đúng khóa chủ mà provider quản lý để bọc DEK.

Ví dụ: ứng dụng có IAM role hợp lệ (thông tin xác thực) vẫn phải chỉ đúng ARN của KMS key (định danh khóa chủ) và có quyền thực hiện các thao tác cần thiết. **Khai báo provider thành công không đồng nghĩa đã tạo DEK**.

### Local KMS có an toàn cho production không?

Local provider yêu cầu ứng dụng giữ vật liệu khóa chủ. Điều này phù hợp để học quy trình, nhưng với production thường nên ưu tiên KMS có quản lý quyền, giám sát và chính sách phục hồi rõ ràng. Nếu dùng local trong hoàn cảnh đặc thù, cần cơ chế quản lý secret tương đương về kiểm soát truy cập và sao lưu. Không hardcode khóa chủ vào Java, YAML, Git hay log.

## 7. Thực hành tạo DEK với Spring và MongoDB Java Driver

Ví dụ này dùng **local KMS** để thấy rõ các bước và tránh phụ thuộc tài khoản dịch vụ ngoài. Giả sử:

- MongoDB đã chạy, tạo được collection **encryption.__keyVault**, và tài khoản kết nối có quyền phù hợp.
- Ứng dụng có dependency Spring Data MongoDB và các thành phần MongoDB Java Driver hỗ trợ CSFLE, bao gồm thư viện mã hóa cần thiết cho driver/OS đang dùng.
- Hai biến môi trường đã được đặt: **MONGODB_URI** và **LOCAL_KMS_KEY_BASE64**. Biến thứ hai chứa **96 byte ngẫu nhiên** được mã hóa Base64; nó là bí mật của ứng dụng, không đưa vào repository.
- Đã tạo unique partial index trên **keyAltNames** như phần trên.

### 7.1. Khai báo ClientEncryption dưới dạng Spring bean

~~~java
import com.mongodb.ClientEncryptionSettings;
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.vault.ClientEncryption;
import com.mongodb.client.vault.ClientEncryptions;
import java.util.Base64;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MongoEncryptionConfiguration {

    @Bean(destroyMethod = "close")
    ClientEncryption clientEncryption() {
        byte[] localMasterKey = Base64.getDecoder().decode(
            requiredEnv("LOCAL_KMS_KEY_BASE64")
        );
        if (localMasterKey.length != 96) {
            throw new IllegalArgumentException(
                "Local KMS master key must contain exactly 96 bytes"
            );
        }

        MongoClientSettings keyVaultClientSettings =
            MongoClientSettings.builder()
                .applyConnectionString(
                    new ConnectionString(requiredEnv("MONGODB_URI"))
                )
                .build();

        ClientEncryptionSettings encryptionSettings =
            ClientEncryptionSettings.builder()
                .keyVaultNamespace("encryption.__keyVault")
                .keyVaultMongoClientSettings(keyVaultClientSettings)
                .kmsProviders(
                    Map.of("local", Map.of("key", localMasterKey))
                )
                .build();

        return ClientEncryptions.create(encryptionSettings);
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

Đối tượng **ClientEncryption** quản lý thao tác tạo DEK và mã hóa/giải mã tường minh. Ở ví dụ này, **keyVaultMongoClientSettings** chỉ rõ cấu hình kết nối để đọc/ghi key vault. Trong hệ thống thực, kết nối key vault có thể dùng credentials và deployment riêng.

Nếu thiếu thư viện hỗ trợ mã hóa native hoặc cấu hình phù hợp, driver có thể báo lỗi khi gọi thao tác mã hóa. Cần cài dependency/thành phần crypto đúng với phiên bản MongoDB Java Driver đang sử dụng.

### 7.2. Tạo khóa và mã hóa/giải mã một giá trị

~~~java
import com.mongodb.client.model.vault.DataKeyOptions;
import com.mongodb.client.model.vault.EncryptOptions;
import com.mongodb.client.vault.ClientEncryption;
import java.util.List;
import org.bson.BsonBinary;
import org.bson.BsonString;
import org.springframework.stereotype.Service;

@Service
class CustomerSensitiveDataService {

    private final ClientEncryption encryption;

    CustomerSensitiveDataService(ClientEncryption encryption) {
        this.encryption = encryption;
    }

    // Chỉ gọi trong quy trình provisioning khóa có kiểm soát.
    BsonBinary provisionCitizenIdKey() {
        return encryption.createDataKey(
            "local",
            new DataKeyOptions()
                .keyAltNames(List.of("customers-citizen-id-v1"))
        );
    }

    BsonBinary encryptCitizenId(BsonBinary dataKeyId, String plaintext) {
        return encryption.encrypt(
            new BsonString(plaintext),
            new EncryptOptions("AEAD_AES_256_CBC_HMAC_SHA_512-Random")
                .keyId(dataKeyId)
        );
    }

    String decryptCitizenId(BsonBinary ciphertext) {
        return encryption.decrypt(ciphertext).asString().getValue();
    }
}
~~~

**Ý nghĩa của ví dụ:**

- **createDataKey("local", ...)** sinh DEK, dùng local master key để bọc DEK, ghi document vào key vault và trả về key ID.
- **encrypt(...)** dùng DEK đã xác định để mã hóa giá trị, kết quả là một BSON binary mã hóa, không phải chuỗi văn bản.
- **decrypt(...)** lấy lại bản rõ khi có quyền truy cập key vault và KMS provider phù hợp.
- Thuật toán **Random** khiến cùng bản rõ được mã hóa nhiều lần có thể cho ciphertext khác nhau; phù hợp khi không cần tìm kiếm bằng phép so sánh trực tiếp trên giá trị mã hóa.

Đây là ví dụ **explicit encryption**: đoạn code chủ động gọi **encrypt** và **decrypt**. Bean ClientEncryption trong đoạn trên **không tự động khiến mọi MongoTemplate/MongoRepository mã hóa trường**. Muốn lưu ciphertext từ ví dụ, cần thiết kế mapping/codec phù hợp để giữ nguyên BSON encrypted binary; không được chuyển ciphertext thành chuỗi hoặc ghi lại bản rõ ngoài ý muốn.

**Không gọi provisionCitizenIdKey cho từng document hay từng request.** Việc tạo DEK là một thao tác quản trị có kiểm soát. Khi khởi động hoặc chạy job, ứng dụng nên tìm khóa đã được cấp theo bí danh/ID, xử lý trường hợp khóa đã tồn tại, rồi tái sử dụng nó cho nhóm dữ liệu đã thiết kế.

### 7.3. Khi nào MongoTemplate và repository mã hóa tự động?

Trong **automatic encryption**, **MongoClient mà Spring Data MongoDB thực sự sử dụng** phải được cấu hình **AutoEncryptionSettings** với:

- **keyVaultNamespace** và cấu hình truy cập key vault cần thiết.
- **kmsProviders** và thông tin xác thực/định danh khóa.
- Schema hoặc metadata chỉ rõ những trường cần mã hóa, thuật toán và DEK tương ứng.
- Các thư viện/thành phần mã hóa của driver theo cơ chế MongoDB và phiên bản được triển khai.

Ví dụ khái niệm một phần cấu hình driver:

~~~java
import com.mongodb.AutoEncryptionSettings;
import com.mongodb.MongoClientSettings;
import java.util.Map;

// kmsProviders và encryptedFieldsMap/schemaMap được xây dựng
// từ cấu hình triển khai thực tế, không phải map rỗng tùy ý.
AutoEncryptionSettings autoEncryptionSettings =
    AutoEncryptionSettings.builder()
        .keyVaultNamespace("encryption.__keyVault")
        .kmsProviders(kmsProviders)
        .build();

MongoClientSettings appClientSettings = MongoClientSettings.builder()
    .applyConnectionString(connectionString)
    .autoEncryptionSettings(autoEncryptionSettings)
    .build();
~~~

Đoạn này minh họa vị trí cấu hình, chưa phải cấu hình đầy đủ có thể chạy ngay: phải cung cấp **kmsProviders**, **connectionString**, mô tả trường mã hóa và thành phần crypto tương ứng. Ứng dụng cần sử dụng **MongoClient** được tạo từ appClientSettings; cấu hình một client khác không tác động tới client đã được Spring Data tạo.

Khi automatic encryption hoạt động và được khai báo đúng, các thao tác MongoTemplate/repository trên trường áp dụng có thể mã hóa và giải mã theo cấu hình client. Khi dùng **Queryable Encryption**, phải tuân thủ danh sách thuật toán/loại truy vấn và quy trình tạo collection tương ứng; **không** lấy thuật toán Random trong ví dụ explicit CSFLE rồi suy ra nó hỗ trợ truy vấn trên ciphertext.

## 8. Thay local provider bằng KMS ngoài

Với KMS ngoài, cấu hình phân thành hai nhóm:

- **KMS provider credentials:** quyền ứng dụng gọi API dịch vụ KMS, nên lấy từ cơ chế định danh được quản lý (chẳng hạn role hoặc workload identity) thay vì hardcode secret.
- **Master key descriptor:** thông tin xác định khóa chủ để bọc DEK, ví dụ region và ARN của AWS KMS key.

Ví dụ *định dạng* descriptor khi tạo DEK trên AWS; các giá trị minh họa cần thay bằng cấu hình do đội vận hành cấp:

~~~java
import com.mongodb.client.model.vault.DataKeyOptions;
import org.bson.BsonBinary;
import org.bson.BsonDocument;
import org.bson.BsonString;
import java.util.List;

// clientEncryption đã được cấu hình provider "aws" và quyền hợp lệ.
BsonDocument masterKey = new BsonDocument()
    .append("region", new BsonString("ap-southeast-1"))
    .append("key", new BsonString(
        "arn:aws:kms:ap-southeast-1:123456789012:key/example-key-id"
    ));

BsonBinary dataKeyId = clientEncryption.createDataKey(
    "aws",
    new DataKeyOptions()
        .masterKey(masterKey)
        .keyAltNames(List.of("customers-citizen-id-v2"))
);
~~~

Mẫu trên chỉ minh họa **cách chọn master key khi tạo DEK**, với giả định bạn đã có ClientEncryption cấu hình AWS KMS. Không thể dùng mã này riêng lẻ nếu chưa có provider credentials, chính sách quyền, kết nối KMS và key vault. Với Azure/GCP/KMIP, định dạng descriptor khác; hãy theo tài liệu đúng phiên bản driver/KMS.

### Quyền và phạm vi bảo vệ

Một ứng dụng có thể có quyền đọc collection nghiệp vụ nhưng không được truy cập key vault hoặc KMS. Ngược lại, quyền đọc key vault không tự cấp quyền giải mã nếu thiếu quyền sử dụng master key. Đây là một cơ sở để tách trách nhiệm giữa ứng dụng nghiệp vụ, dịch vụ cấp khóa và tác vụ quản trị.

Nên định nghĩa rõ:

1. Service nào được phép tạo DEK mới, đọc khóa và yêu cầu KMS giải mã.
2. Service nào chỉ được đọc document đã mã hóa mà không thể lấy bản rõ.
3. Ai được sửa alias, thay đổi metadata khóa, phục hồi backup và yêu cầu rotation.
4. Cách quản lý credential trong môi trường phát triển, CI và production.

Đừng nhầm **mã hóa trường** với **kiểm soát truy cập toàn hệ thống**: quyền MongoDB, secret management, TLS, kiểm toán và phân quyền ứng dụng vẫn cần thiết.

## 9. Quản lý vòng đời khóa: tạo, dùng, rotation và khôi phục

### 9.1. Cấp phát DEK (provisioning)

Khi triển khai dịch vụ mới, có thể dùng một job quản trị để tạo DEK đúng một lần và ghi nhận ID/bí danh. Cần:

- Chọn tên khóa theo phạm vi nghiệp vụ và chính sách phiên bản, ví dụ **customer-identity-v1**.
- Tạo unique index trên keyAltNames.
- Bảo đảm tạo khóa lặp lại không gây sai lệch; nếu có khóa hợp lệ đã tồn tại, phải sử dụng lại theo quy trình đã định.
- Phân quyền tạo khóa khác với quyền đọc/ghi document thường ngày nếu có thể.

### 9.2. Rotation của master key khác rotation của DEK

| Hoạt động | Thay đổi | Có cần mã hóa lại dữ liệu document không? |
| --- | --- | --- |
| **Rewrap DEK với master key khác** | Thay lớp mã hóa bảo vệ DEK trong key vault, ví dụ chuyển sang KMS key mới. | Về nguyên tắc **không**, nếu DEK mã hóa document vẫn giữ nguyên; cần kiểm tra khả năng và API theo phiên bản. |
| **Tạo DEK mới và chuyển dữ liệu** | Những giá trị dữ liệu mới hoặc được di chuyển sẽ dùng DEK khác. | **Có** với dữ liệu cũ cần chuyển sang DEK mới: phải giải mã rồi mã hóa lại theo kế hoạch. |
| **Đổi keyAltName** | Thay metadata/bí danh tham chiếu khóa. | Không tự làm ciphertext dùng DEK mới. |
| **Vô hiệu hóa/xóa master key hoặc DEK cũ** | Có thể cắt quyền mở dữ liệu hiện hữu. | Có nguy cơ **mất khả năng giải mã**; chỉ thực hiện sau khi xác minh dữ liệu và backup còn phụ thuộc vào khóa nào. |

Một số phiên bản MongoDB Driver cung cấp thao tác **rewrapManyDataKey** để bọc lại DEK theo provider/master key mới. Khả năng sử dụng, yêu cầu thư viện và tham số có thể khác theo phiên bản; cần thiết kế thủ tục thử nghiệm và rollback trước khi vận hành.

**Điểm quan trọng:** luồng giải mã dữ liệu đã ghi trước đây có thể vẫn phụ thuộc vào DEK cũ rất lâu sau khi ứng dụng chuyển sang DEK mới. Không xóa khóa chỉ vì mọi bản ghi mới đều đã dùng khóa khác.

### 9.3. Backup và disaster recovery

Để khôi phục dữ liệu mã hóa phía client, chỉ backup collection nghiệp vụ là chưa đủ. Cần bảo đảm:

- Có bản sao lưu nhất quán của **collection dữ liệu** và **key vault**, cùng khả năng phục hồi key ID/metadata.
- Master key vẫn truy cập được sau khi khôi phục, bao gồm quyền KMS, vùng/endpoint, version và danh tính dịch vụ liên quan.
- Cơ chế quản lý bí mật local (nếu dùng) có quy trình sao lưu và phục hồi riêng.
- Khôi phục thử trên môi trường cách ly: đọc ciphertext cũ, mở DEK và xác minh giải mã bằng client đúng phiên bản/cấu hình.

### 9.4. Audit và thời gian sống của khóa

Theo dõi việc tạo khóa, thay đổi alias, thay đổi quyền KMS, lỗi giải mã và hoạt động rotation qua các hệ thống audit phù hợp. Không ghi **master key**, **DEK ở dạng rõ** hoặc **giá trị giải mã** vào log. Metadata khóa cũng có thể chứa thông tin nghiệp vụ; chỉ công bố mức cần thiết.

## 10. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy DEK / key ID | Sai namespace key vault, sai deployment, khóa chưa tạo hoặc quyền đọc thiếu. | Kiểm tra keyVaultNamespace, key ID/alias, tài khoản kết nối và backup. |
| KMS từ chối truy cập hoặc timeout | Credential, quyền sử dụng master key, endpoint, TLS hoặc kết nối mạng. | Xác minh danh tính dịch vụ, policy, đường mạng và thời gian đáp ứng của KMS. |
| Tạo khóa bị lỗi trùng keyAltNames | Nhiều lần provision cùng bí danh hoặc nhiều job chạy đồng thời. | Kiểm tra unique index, đưa provisioning về thao tác kiểm soát/idempotent. |
| Dữ liệu đọc ra vẫn là ciphertext | Dùng client không được cấu hình giải mã hoặc explicit encryption nhưng chưa gọi decrypt. | Kiểm tra driver/client thực tế được MongoTemplate dùng và cấu hình key vault/KMS. |
| Không thể giải mã dữ liệu cũ sau rotation | Mất khóa chủ/DEK cũ, thay sai cấu hình provider hoặc xóa key vault. | Khôi phục quyền và khóa tương ứng; chỉ tiếp tục migration khi có thể giải mã dữ liệu cũ. |
| Truy vấn theo trường đã mã hóa không trả kết quả | Dùng thuật toán không hỗ trợ kiểu truy vấn, filter mã hóa sai hoặc thiếu cấu hình QE/CSFLE tương ứng. | Xác định chế độ mã hóa, thuật toán, truy vấn được hỗ trợ và so sánh với metadata. |
| Ứng dụng chạy trên máy A nhưng lỗi trên máy B | Thiếu native crypt library, sai biến môi trường, sai KMS credentials hoặc khác phiên bản driver. | So sánh dependency và cấu hình triển khai; kiểm tra từng lớp từ kết nối key vault đến KMS. |

### Quy trình chẩn đoán theo thứ tự

1. **Xác nhận phạm vi lỗi:** lỗi tạo DEK, ghi ciphertext, đọc ciphertext hay giải mã?
2. **Kiểm tra MongoDB:** ứng dụng đang dùng đúng cluster, database và keyVaultNamespace chưa?
3. **Kiểm tra metadata:** key ID/bí danh có tồn tại, được tạo hợp lệ và có quyền đọc không? Không xuất keyMaterial ra log.
4. **Kiểm tra KMS:** provider đúng, master key tồn tại, credentials có quyền và đường mạng có hoạt động không?
5. **Kiểm tra driver/Spring:** dependency mã hóa có sẵn, phiên bản tương thích và đúng MongoClient có AutoEncryptionSettings hay logic explicit không?
6. **Thử một document trong môi trường kiểm soát:** mã hóa, lưu, đọc, giải mã bằng client được cấp quyền; giữ lại log trạng thái an toàn để phân tích.

## 11. Tình huống thiết kế trong ứng dụng Spring Data MongoDB

**Tình huống A — ứng dụng quản lý hồ sơ khách hàng:** Collection **customers** gồm **name**, **citizenId**, **createdAt**. Chính sách yêu cầu chỉ một service đọc được citizenId. Có thể phân quyền tách riêng cho service này, sử dụng DEK cho citizenId và lựa chọn explicit hoặc automatic encryption. Các service khác vẫn có thể truy cập những trường không mã hóa theo phân quyền của chúng.

**Tình huống B — nhiều tenant có yêu cầu cách ly:** Mỗi tenant hoặc nhóm tenant có thể được gán DEK riêng theo chính sách, kết hợp với phân quyền key vault/KMS và quy trình cấp phát. Cần đo chi phí quản lý nhiều DEK, KMS call và hành vi cache; không mặc định “mỗi tenant một DEK” là bắt buộc.

**Tình huống C — cần tìm khách hàng theo định danh bí mật:** Nếu dùng thuật toán **Random** trong ví dụ, không thể giả định truy vấn bằng equality trên bản rõ sẽ hoạt động. Cần cân nhắc lựa chọn tính năng mã hóa hỗ trợ truy vấn (ví dụ Queryable Encryption với đúng loại truy vấn và phiên bản hỗ trợ), cũng như mức độ rò rỉ thông tin và giới hạn dữ liệu. Không được tự đổi sang mã hóa xác định chỉ để làm truy vấn chạy nếu chưa đánh giá rủi ro.

**Tình huống D — chuyển ứng dụng từ local KMS sang KMS quản lý:** Tạo cấu hình provider mới, chuẩn bị quyền và kế hoạch rewrap/migration theo phiên bản driver; giữ khả năng mở dữ liệu cũ. Phải kiểm thử backup, rollback và tác động tới client cache trước khi cắt cấu hình local.

## 12. Checklist trước khi đưa vào vận hành

1. **Chọn đúng lớp mã hóa:** xác định trường cần bảo vệ, đối tượng bị hạn chế quyền và truy vấn cần hỗ trợ; phân biệt CSFLE và Queryable Encryption.
2. **Thiết kế key vault:** namespace, địa chỉ triển khai, unique partial index, backup và quyền đọc/ghi.
3. **Chọn chiến lược DEK:** nhóm dữ liệu nào dùng chung khóa, cách đặt alias, provisioning, theo dõi ID và tuổi thọ khóa.
4. **Cấu hình KMS:** master key/KEK, danh tính, quyền, đường mạng và giám sát; không lưu secret trong Git hoặc log.
5. **Kết nối Spring Data MongoDB:** phân biệt explicit encryption với automatic encryption; bảo đảm MongoTemplate/repository dùng đúng MongoClient và codec/mapping.
6. **Kiểm thử chức năng:** dữ liệu ghi ra là ciphertext, ứng dụng có quyền giải mã được, ứng dụng thiếu quyền không thể lấy bản rõ.
7. **Kiểm thử vận hành:** KMS timeout, mất kết nối key vault, rotation, khôi phục bản sao lưu, migration và những trường hợp đọc dữ liệu cũ.
8. **Theo dõi hiệu năng:** độ trễ crypto ở client, thời gian truy cập key vault/KMS, cache, throughput và chi phí truy vấn trường mã hóa.

### Câu hỏi tự kiểm tra

**1. Vì sao có quyền đọc key vault vẫn chưa chắc giải mã được?** Vì key vault chứa **DEK đã được bọc**; client còn cần quyền truy cập master key phù hợp từ KMS provider để mở bọc khóa.

**2. Tại sao không nên tạo DEK mới mỗi lần gọi repository.save()?** Làm vậy tăng số khóa, chi phí quản lý và phức tạp trong rotation/khôi phục. Thông thường DEK được cấp phát theo phạm vi dữ liệu đã thiết kế và tái sử dụng có kiểm soát.

**3. Rewrap DEK có đồng nghĩa toàn bộ document được mã hóa lại?** Không. Rewrap đổi lớp bảo vệ DEK, còn mã hóa lại dữ liệu bằng DEK mới là hoạt động khác.

**4. Đã tạo ClientEncryption bean thì MongoTemplate tự mã hóa mọi trường chưa?** Chưa. Explicit encryption cần lời gọi encrypt/decrypt; automatic encryption cần cấu hình MongoClient, schema/metadata mã hóa và các thành phần crypto theo driver.

**5. Nếu backup dữ liệu còn đủ nhưng mất KMS master key thì sao?** Có thể không mở được DEK trong key vault và mất khả năng giải mã dữ liệu tương ứng. Thiết kế backup phải bao gồm cả khả năng phục hồi khóa.

## Kết luận

Trong Spring Data MongoDB, **key vault**, **DEK** và **KMS provider** tạo thành chuỗi tin cậy của mã hóa phía client: **key vault lưu DEK đã được bọc, KMS bảo vệ khóa chủ, còn DEK mã hóa giá trị document tại ứng dụng**. Thiết kế đúng đòi hỏi chọn thuật toán/tính năng theo nhu cầu truy vấn, cấp phát khóa có kiểm soát, phân quyền riêng cho dữ liệu và khóa, lưu trữ bí mật an toàn, cùng quy trình rotation và khôi phục đã được kiểm thử. MongoTemplate và repository vẫn là tầng thao tác dữ liệu, còn cách mã hóa phụ thuộc vào cấu hình MongoDB Java Driver và chính sách bảo vệ dữ liệu đã đặt ra.
