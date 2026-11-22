# Thiết kế version schema để nhiều cấu trúc document cùng tồn tại

## 1. Vì sao MongoDB cần version schema?

MongoDB lưu dữ liệu theo document BSON và không bắt buộc mọi document trong một collection có cùng bộ trường. Tính linh hoạt này cho phép ứng dụng thêm trường, đổi cấu trúc lồng nhau hoặc phát triển mô hình dữ liệu theo từng phiên bản. Tuy nhiên, khi hệ thống hoạt động lâu dài, cùng một collection có thể chứa document được tạo bởi nhiều phiên bản ứng dụng. Nếu mã nguồn chỉ hiểu cấu trúc mới nhất, một bản ghi cũ có thể bị đọc sai, cập nhật làm mất dữ liệu hoặc không còn phù hợp với truy vấn.

**Schema versioning** là cách gắn phiên bản cấu trúc vào document và quy định rõ cách đọc, ghi, chuyển đổi giữa các phiên bản. Mục tiêu không phải làm cho tất cả document giống nhau ngay lập tức; mục tiêu là cho phép các cấu trúc **cùng tồn tại có kiểm soát** trong suốt quá trình triển khai, di chuyển dữ liệu và duy trì tương thích.

Trong module **SPRING_DATA_MONGODB**, đây là kỹ năng thiết kế document trực tiếp phục vụ kết nối và ánh xạ dữ liệu bằng Spring Data MongoDB, thao tác qua **MongoTemplate** hoặc repository. Lựa chọn version ảnh hưởng đến truy vấn, aggregation, index, transaction, reactive access, kiểm thử và khả năng phân tích hiệu năng.

Sau bài này, bạn cần làm được các việc sau:

1. Phân biệt **phiên bản schema**, **phiên bản phần mềm** và **phiên bản để khóa lạc quan**.
2. Thiết kế trường định danh schema, quy ước phiên bản cũ thiếu metadata và hợp đồng đọc/ghi.
3. Xây bộ đọc hiểu nhiều schema nhưng trả về một mô hình nghiệp vụ thống nhất.
4. Lập kế hoạch chuyển đổi từng bước, có thể triển khai cuốn chiếu và xử lý cạnh tranh cập nhật.
5. Thiết kế truy vấn, index, validation, migration và kiểm thử cho collection chứa nhiều cấu trúc.

## 2. Một ví dụ xuyên suốt: nâng cấp cấu trúc đơn hàng

Giả sử phiên bản đầu tiên của dịch vụ lưu tên và số điện thoại khách hàng ở hai trường phẳng:

~~~javascript
// Document ở schema v1, dùng để minh họa trong mongosh.
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  schemaVersion: NumberInt(1),
  customerName: "Lan",
  customerPhone: "0901234567",
  items: [
    { sku: "BOOK-01", quantity: NumberInt(2) }
  ],
  totalMinor: NumberLong("199000"),
  placedAt: ISODate("2025-04-10T08:00:00Z"),
  revision: NumberLong("3")
}
~~~

Khi ứng dụng cần lưu thêm thông tin liên hệ và địa chỉ, nhóm phát triển quyết định gom dữ liệu khách hàng vào một object. Document mới có cấu trúc:

~~~javascript
// Document ở schema v2; khác _id để có thể cùng tồn tại với ví dụ v1.
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  schemaVersion: NumberInt(2),
  customer: {
    fullName: "Minh",
    contact: { phone: "0987654321" },
    address: { city: "Hà Nội" }
  },
  items: [
    { sku: "BOOK-02", quantity: NumberInt(1) }
  ],
  totalMinor: NumberLong("129000"),
  placedAt: ISODate("2025-04-11T08:00:00Z"),
  revision: NumberLong("1")
}
~~~

Trong ví dụ, **totalMinor** là số nguyên đơn vị tiền nhỏ nhất theo quy ước của hệ thống; không dùng giá trị dấu phẩy động để minh họa giá tiền. Trường **revision** dùng theo dõi xung đột ghi, độc lập với schemaVersion. Trường **placedAt** là BSON Date, vẫn giữ nguyên ngữ nghĩa qua hai phiên bản.

| Nội dung | Schema v1 | Schema v2 | Tác động |
| --- | --- | --- | --- |
| Phiên bản | schemaVersion = 1 | schemaVersion = 2 | Bộ đọc cần phân nhánh. |
| Tên khách hàng | customerName | customer.fullName | Truy vấn và index phải xử lý hai đường dẫn. |
| Điện thoại | customerPhone | customer.contact.phone | Mapper cần chuẩn hóa đường dẫn. |
| Địa chỉ | Chưa hỗ trợ | customer.address | Trường mới phải có quy tắc thiếu/giá trị mặc định. |
| Dòng hàng | items | items | Không cần chuyển đổi. |
| Tổng tiền | totalMinor | totalMinor | Giữ nguyên kiểu và đơn vị. |
| Thời gian tạo | placedAt | placedAt | Giữ nguyên BSON Date. |
| Cạnh tranh ghi | revision | revision | Không được dùng schemaVersion thay thế revision. |

**Hai document trên có thể nằm trong cùng collection**. Đó chính là trạng thái chuyển tiếp mà hệ thống phải vận hành an toàn. Không nên tạo một collection mới cho mỗi thay đổi nhỏ nếu dữ liệu vẫn thuộc một thực thể nghiệp vụ và cần cùng quy tắc truy vấn, phân quyền, lưu giữ.

## 3. Thiết kế hợp đồng schemaVersion

Một quy ước phổ biến là trường **schemaVersion** có giá trị nguyên trong từng document:

~~~json
{
  "schemaVersion": 2
}
~~~

Đặt schemaVersion ở cấp gốc giúp truy vấn, migration, thống kê và đọc bằng driver đơn giản hơn. Trường này mô tả **cấu trúc dữ liệu đang lưu**, không phải phiên bản của Spring Boot, API hay service phát sinh document.

### 3.1. Cần xác định gì trước khi thêm version?

| Câu hỏi | Quy ước nên định nghĩa |
| --- | --- |
| Version có ý nghĩa gì? | Mỗi giá trị xác định một hợp đồng cấu trúc và ngữ nghĩa cụ thể. |
| Kiểu dữ liệu của version? | Dùng BSON Int32 nhất quán; tránh cùng trường chứa cả String và Number. |
| Document cũ không có trường version? | Chỉ mặc định là v1 nếu đã kiểm tra rằng tất cả dữ liệu thiếu trường đều theo schema v1. |
| Khi nào tăng version? | Khi thay đổi không tương thích với cách đọc/ghi đã công bố, như đổi tên trường hoặc đổi ngữ nghĩa dữ liệu. |
| Có cần tăng khi thêm trường tùy chọn? | Phụ thuộc hợp đồng; thay đổi tương thích có thể không cần phiên bản mới nếu bộ đọc cũ bỏ qua trường lạ. |
| Gặp version chưa biết? | Báo lỗi rõ ràng, ghi nhận metric và cách xử lý vận hành; không tự gán về v1. |
| Phiên bản có bị giảm? | Chỉ khi tồn tại quy trình downgrade được định nghĩa và kiểm chứng. |
| Vòng đời version cũ? | Quy định tiêu chí ngừng đọc/ghi và khi nào có thể xóa nhánh tương thích. |

Một số hệ thống dùng tên **_schemaVersion** hoặc giá trị chuỗi như "v2"; điều quan trọng là chọn **một chuẩn**, dùng nhất quán và kiểm tra bằng schema validation. Ví dụ trong bài dùng **schemaVersion: 1, 2, 3...**.

### 3.2. Phân biệt ba dạng “version”

- **Schema version** cho biết *hình dạng document*; v1 có customerName, v2 có customer.fullName.
- **Application version** cho biết *bản phát hành mã nguồn*; một bản phát hành có thể đọc v1 và v2 đồng thời.
- **Optimistic-lock version** là bộ đếm thay đổi *của một document*, dùng phát hiện ghi đè đồng thời. Trong Spring Data MongoDB thường dùng **@Version** cho mục đích này.

Ví dụ v2 có schemaVersion = 2 và revision = 47 sau nhiều lần cập nhật. Việc sửa địa chỉ có thể làm revision tăng mà **không làm schemaVersion thay đổi**.

### 3.3. Không suy version chỉ qua sự có mặt của một trường

Một cách đọc thiếu ổn định là “có customer thì chắc chắn v2”. Nếu quá trình chuyển đổi lưu cả trường cũ và trường mới, cách suy đoán đó dễ sai. Trường mới có thể tạm thời được thêm vào document v1 nhưng chưa đáp ứng đầy đủ hợp đồng v2. Hãy dùng **schemaVersion làm nguồn xác định cấu trúc**, kết hợp validation để bảo đảm trường và kiểu đúng với version.

Đối với document legacy thật sự thiếu schemaVersion, một nhánh tương thích có thể coi thiếu trường là v1:

~~~javascript
// Chỉ dùng sau khi xác minh dữ liệu thiếu schemaVersion đúng là v1.
const version = doc.schemaVersion == null ? 1 : doc.schemaVersion;
~~~

Đừng dùng quy tắc này để che giấu trường schemaVersion có giá trị null hoặc kiểu sai trong dữ liệu mới. Trong kiểm thử và giám sát, hãy phân biệt rõ document **missing**, **null**, **string** và **int**.

## 4. Chọn chiến lược vận hành nhiều schema

Không tồn tại một cách triển khai phù hợp cho mọi hệ thống. Ba lựa chọn thường gặp:

| Chiến lược | Cách hoạt động | Phù hợp khi | Hạn chế |
| --- | --- | --- | --- |
| **Versioned readers** | Bộ đọc chọn mapper theo schemaVersion, không sửa dữ liệu khi đọc | Collection lớn, cần chuyển đổi dần | Phải duy trì nhiều nhánh đọc. |
| **Background migration** | Job chuyển các document cũ sang schema mới theo lô | Muốn kết thúc ở một schema thống nhất | Cần kiểm soát cạnh tranh ghi, tải DB và rollback. |
| **Dual write/compatibility fields** | Tạm ghi cả trường mới và trường cũ trong một document | Còn nhiều consumer cũ đang hoạt động | Dễ lệch dữ liệu giữa hai bản sao và tăng kích thước document. |

Hai cách đầu có thể phối hợp: ứng dụng mới đọc được cả v1 và v2 trong lúc migration chạy; sau khi mọi dữ liệu đã ở v2 và không còn consumer cũ, loại bỏ mã đọc v1. Dual write là phương tiện chuyển tiếp nếu thực sự cần hỗ trợ consumer chưa cập nhật.

Tránh thiết kế “đọc v1 thì tự động lưu lại v2” mà không có chính sách kiểm soát. **Lazy migration on read** có thể hoạt động, nhưng một thao tác GET có thể sinh ghi, làm thay đổi độ trễ, revision, auditing và gây xung đột nếu nhiều request cùng truy cập.

## 5. Thiết kế đường đọc: nhiều schema, một mô hình nghiệp vụ

Tầng xử lý nghiệp vụ không nên phải viết điều kiện version ở khắp nơi. Cách ổn định hơn là chuyển mỗi cấu trúc lưu trữ sang một **mô hình đọc chuẩn**.

~~~mermaid
flowchart TD
    A[(Collection orders: v1 và v2)] --> B[Đọc BSON Document]
    B --> C{schemaVersion?}
    C -->|Thiếu hoặc 1| D[Adapter V1]
    C -->|2| E[Adapter V2]
    C -->|Khác| F[Lỗi schema không hỗ trợ]
    D --> G[OrderView chuẩn]
    E --> G
    G --> H[API, nghiệp vụ, báo cáo]
~~~

Với ví dụ đơn hàng, mô hình đọc chỉ cần có tên, điện thoại và tổng tiền:

~~~java
public record OrderView(
    String id,
    String customerName,
    String phone,
    long totalMinor
) {}
~~~

### 5.1. Ví dụ bộ đọc bằng MongoTemplate

Ví dụ sau dùng **MongoTemplate** để lấy document BSON gốc qua MongoDB Java Driver và chuẩn hóa theo schemaVersion. Cách này giúp minh họa rõ vị trí xử lý đa phiên bản; trong ứng dụng lớn, nên tách các hàm chuyển đổi thành adapter có kiểm thử riêng.

~~~java
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class OrderReadService {
    private final MongoTemplate mongoTemplate;

    public OrderReadService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public record OrderView(
        String id, String customerName, String phone, long totalMinor
    ) {}

    public OrderView findById(ObjectId id) {
        // Lấy BSON Document thô để tránh ép mọi bản ghi v1 vào entity v2.
        Document raw = mongoTemplate.getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();

        if (raw == null) {
            return null;
        }

        Object encodedVersion = raw.get("schemaVersion");
        int schemaVersion;
        if (encodedVersion == null && !raw.containsKey("schemaVersion")) {
            schemaVersion = 1; // Chỉ áp dụng khi legacy thiếu version được xác nhận là v1.
        } else if (encodedVersion instanceof Integer number) {
            schemaVersion = number;
        } else {
            throw new IllegalStateException("Invalid schemaVersion for " + id);
        }

        String name;
        String phone;
        switch (schemaVersion) {
            case 1 -> {
                name = raw.getString("customerName");
                phone = raw.getString("customerPhone");
            }
            case 2 -> {
                Document customer = raw.get("customer", Document.class);
                if (customer == null) {
                    throw new IllegalStateException("Missing customer for " + id);
                }
                name = customer.getString("fullName");
                Document contact = customer.get("contact", Document.class);
                phone = contact == null ? null : contact.getString("phone");
            }
            default -> throw new IllegalStateException(
                "Unsupported schemaVersion=" + schemaVersion + " for " + id
            );
        }

        Long totalMinor = raw.getLong("totalMinor");
        if (name == null || totalMinor == null) {
            throw new IllegalStateException("Invalid order data for " + id);
        }
        return new OrderView(id.toHexString(), name, phone, totalMinor);
    }
}
~~~

Điểm thiết kế trong ví dụ:

- Bộ đọc chỉ chấp nhận **Int32** cho schemaVersion đã khai báo; sai kiểu bị báo lỗi thay vì âm thầm chuyển đổi.
- Document thiếu version được coi là v1 theo một điều kiện có chủ ý. **schemaVersion: null** bị coi là dữ liệu bất thường.
- Mọi nhánh trả về **OrderView**, nên tầng nghiệp vụ không cần biết cách bố trí trường trong MongoDB.
- Document v2 thiếu customer hoặc dữ liệu bắt buộc bị báo lỗi thay vì trả một đối tượng “hợp lệ giả”.
- Mã dùng kiểu BSON Long cho totalMinor theo đúng hợp đồng dữ liệu mẫu. Nếu lịch sử có dữ liệu Int32, String hoặc Decimal128, phải xác định cách chuyển có kiểm tra; không tự động làm tròn.

**Không sử dụng một entity v2 duy nhất để đọc rồi save nguyên document v1.** Nếu entity v2 không biết customerName/customerPhone, thao tác thay thế toàn bộ document có thể xóa mất các trường cũ. Trong giai đoạn chuyển đổi, nên giới hạn các thao tác ghi ở những trường thực sự cần thay đổi hoặc dùng adapter riêng cho từng schema.

### 5.2. Có thể dùng repository không?

Có. Repository rất phù hợp khi dữ liệu đã đồng nhất hoặc khi từng loại document có mapper rõ ràng. Tuy nhiên, một **MongoRepository** ánh xạ trực tiếp sang lớp v2 không tự bảo đảm hiểu đầy đủ schema v1. Các phương án là:

1. Dùng một tầng đọc có **MongoTemplate**/driver để chuẩn hóa dữ liệu trước khi đưa vào domain model; vẫn dùng repository cho các đường ghi v2 phù hợp.
2. Cấu hình **Spring Data converters** hoặc cơ chế mapping đa hình khi các phiên bản có yêu cầu rõ ràng và phạm vi đủ rộng để đáng đầu tư.
3. Nếu chia collection theo đặc điểm nghiệp vụ, có thể dùng repository riêng; cần cân nhắc truy vấn hợp nhất, index và lifecycle của dữ liệu.

Trường **_class** mà Spring Data có thể lưu để hỗ trợ mapping kiểu Java **không nên được dùng như schemaVersion nghiệp vụ**. Tên package/class có thể thay đổi khi refactor mà không đồng nghĩa schema dữ liệu đã đổi; ngược lại, cùng một class có thể đã thay đổi nội dung giữa các bản phát hành.

## 6. Thiết kế đường ghi và khả năng tương thích khi triển khai

Trong lúc cập nhật dần nhiều instance hoặc nhiều dịch vụ, có thể đồng thời tồn tại:

- **R1**: bộ đọc cũ chỉ hiểu v1.
- **R2**: bộ đọc mới hiểu cả v1 và v2.
- **W1**: bộ ghi cũ tạo/sửa document v1.
- **W2**: bộ ghi mới tạo/sửa document v2.

Nếu W2 bắt đầu ghi **v2 thuần** trong khi R1 vẫn nhận các document ấy, R1 có thể gặp lỗi ngay cả khi R2 hoạt động tốt.

| Trạng thái triển khai | Đọc v1 | Đọc v2 | Có nên ghi v2 thuần? |
| --- | --- | --- | --- |
| Chỉ R1 hoạt động | Có | Không | Không. |
| R1 và R2 cùng hoạt động | Có | Chỉ ở R2 | Không, nếu R1 có thể đọc document mới. |
| Tất cả đường đọc đã dùng R2 | Có | Có | Có, sau khi xác nhận các consumer ngoại vi. |
| Đã migrate hết và ngừng hỗ trợ v1 | Tùy chính sách lưu trữ cũ | Có | Có. |

### 6.1. Triển khai theo Expand → Migrate → Contract

~~~mermaid
flowchart LR
    A[Expand: Deploy R2 đọc v1 và v2] --> B[Bật W2 có kiểm soát]
    B --> C[Migrate: Chuyển document v1 theo lô]
    C --> D[Đối soát, quan sát, xử lý lỗi]
    D --> E[Contract: Bỏ đường ghi và đọc v1]
~~~

**Expand — Mở rộng tương thích**

1. Bổ sung trường schemaVersion và adapter mới vào code.
2. Triển khai R2 trên toàn bộ luồng đọc, gồm API, job, báo cáo, consumer sự kiện và công cụ quản trị.
3. Chạy R2 với dữ liệu v1 hiện tại; lúc này W1 vẫn có thể ghi v1.
4. Bật W2 sau khi xác nhận mọi consumer cần thiết đọc được v2.

Nếu consumer cũ bắt buộc phải chạy tiếp, có thể tạm **dual write**:

~~~javascript
{
  schemaVersion: NumberInt(2),
  customerName: "Lan",         // Giữ cho consumer legacy.
  customerPhone: "0901234567", // Giữ cho consumer legacy.
  customer: {
    fullName: "Lan",
    contact: { phone: "0901234567" }
  }
}
~~~

Dual write chỉ giúp consumer cũ nếu nó **không từ chối schemaVersion = 2** và vẫn nhận diện đúng các trường tương thích. Các đường ghi phải cập nhật hai bản sao thông tin trong **cùng một thao tác document atomic**; nếu chỉ cập nhật một bên, hai bộ đọc có thể nhìn thấy hai giá trị khác nhau. Cần xác định trường nào là **nguồn sự thật** và thời điểm chấm dứt dual write.

**Migrate — Chuyển dần dữ liệu**

1. Đếm số document v1, v2, thiếu version và version không hợp lệ.
2. Thử chuyển một tập nhỏ, kiểm tra kết quả đọc mới và kiểm tra tác động query/index.
3. Chạy migration theo lô có checkpoint và khả năng chạy lại.
4. Giới hạn tốc độ để không làm tăng bất thường độ trễ của ứng dụng, tải ghi và replication lag.
5. Theo dõi số lượng còn lại, xung đột cập nhật và document chuyển đổi lỗi.

**Contract — Thu gọn**

1. Xác minh không còn đường ghi v1.
2. Xác minh collection không còn document v1 (hoặc có ngoại lệ được lưu trữ riêng và đã được xử lý).
3. Bỏ adapter, trường legacy và index legacy sau khi hết cửa sổ rollback.
4. Siết schema validation để chỉ nhận v2 nếu dữ liệu và mọi consumer đã sẵn sàng.

Thứ tự triển khai rất quan trọng. Không xóa nhánh v1 chỉ vì bản phát hành mới đã chạy: cần dựa trên **dữ liệu thực**, trạng thái consumer và chính sách rollback.

## 7. Truy vấn một collection có hai cấu trúc

Đọc theo một khóa chung như _id có thể không cần biết version. Nhưng truy vấn theo tên khách hàng phải xét hai đường dẫn.

### 7.1. Truy vấn tương thích

~~~javascript
db.orders.find({
  $or: [
    { schemaVersion: NumberInt(2), "customer.fullName": "Lan" },
    { schemaVersion: NumberInt(1), customerName: "Lan" },
    { schemaVersion: { $exists: false }, customerName: "Lan" }
  ]
});
~~~

Nhánh thứ ba chỉ cần thiết nếu dữ liệu legacy thực sự thiếu schemaVersion. Nếu còn v1 nhưng cũng lưu schemaVersion = 1, nhánh thứ hai đủ cho phần đó. Các điều kiện business như trạng thái đơn hàng, tenant hoặc thời gian cần áp dụng nhất quán cho cả hai kiểu.

Trong Spring Data MongoDB, có thể diễn đạt điều kiện tương đương qua **Criteria.orOperator**:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Criteria customerName = new Criteria().orOperator(
    Criteria.where("schemaVersion").is(2)
        .and("customer.fullName").is("Lan"),
    Criteria.where("schemaVersion").is(1)
        .and("customerName").is("Lan"),
    new Criteria().andOperator(
        Criteria.where("schemaVersion").exists(false),
        Criteria.where("customerName").is("Lan")
    )
);

Query query = new Query(customerName);
~~~

Đây là ví dụ về **điều kiện query**, chưa phải code của repository hoàn chỉnh. Nếu repository tự tạo truy vấn dựa trên một field Java duy nhất, nó không mặc nhiên triển khai đủ các nhánh đường dẫn trên.

### 7.2. Chuẩn hóa dữ liệu bằng aggregation

Khi cần biểu diễn chung cho báo cáo, sử dụng aggregation để dựa theo schemaVersion và trả một đường dẫn chuẩn:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      totalMinor: 1,
      placedAt: 1,
      customerNameNormalized: {
        $cond: [
          { $eq: ["$schemaVersion", 2] },
          "$customer.fullName",
          "$customerName"
        ]
      }
    }
  }
]);
~~~

Document thiếu version được coi là v1 trong ví dụ này. Nếu collection có các version khác hoặc dữ liệu lỗi, cần lọc/đánh dấu rõ trước khi chạy báo cáo nghiệp vụ.

Lưu ý hiệu năng: biểu thức chuẩn hóa được tính tại thời điểm aggregation. Nếu đưa điều kiện **$match theo customerNameNormalized** sau **$project**, truy vấn có thể không sử dụng trực tiếp index trên đường dẫn trường gốc như khi lọc trước bằng **$or**. Với bảng dữ liệu lớn, nên so sánh kế hoạch thực thi thay vì chỉ quan tâm sự gọn gàng của pipeline.

### 7.3. Index trong giai đoạn hai schema

Hai đường dẫn tên khách hàng khác nhau có thể cần hai index:

~~~javascript
db.orders.createIndex({ customerName: 1 });
db.orders.createIndex({ "customer.fullName": 1 });
~~~

Nếu truy vấn luôn lọc theo tenantId, thời gian hoặc trạng thái, cân nhắc **compound index** theo mẫu truy vấn thực tế. Đừng mặc định index riêng cho schemaVersion có ích: hiệu quả phụ thuộc độ chọn lọc, số phiên bản, các điều kiện khác và kế hoạch query.

Đánh giá bằng:

~~~javascript
db.orders.find({
  $or: [
    { schemaVersion: 2, "customer.fullName": "Lan" },
    { schemaVersion: 1, customerName: "Lan" }
  ]
}).explain("executionStats");
~~~

Khi phân tích kết quả, quan sát số document/keys được quét, số document trả về, các nhánh của **$or**, kế hoạch dùng index và thời gian thực thi. Index cho trường legacy là chi phí tạm thời có thể được dọn sau khi migration và rollback window kết thúc.

## 8. Migration dữ liệu có kiểm soát

Migration là quá trình biến một document v1 thành document v2 **mà vẫn bảo toàn ý nghĩa nghiệp vụ**. Hãy tách ba việc: xác định bản ghi cần chuyển, tính cấu trúc mới và ghi thay đổi an toàn.

### 8.1. Khảo sát phân bố version

~~~javascript
// Phân biệt kiểu BSON thực đang được dùng cho trường schemaVersion.
db.orders.aggregate([
  { $group: {
      _id: { $type: "$schemaVersion" },
      documents: { $sum: 1 }
  }},
  { $sort: { documents: -1 } }
]);

// Đếm document thuộc v1, bao gồm các bản legacy chưa có metadata.
db.orders.countDocuments({
  $or: [
    { schemaVersion: NumberInt(1) },
    { schemaVersion: { $exists: false } }
  ]
});

db.orders.countDocuments({ schemaVersion: NumberInt(2) });
~~~

Kết quả nhóm theo **$type** có thể có **int**, **missing**, **null**, **string** hoặc các kiểu khác. Trước khi chuyển đổi, cần thống kê dữ liệu thiếu trường, trùng tên nhưng khác ngữ nghĩa và các ngoại lệ như trường customerName rỗng hoặc không phải String.

### 8.2. Ví dụ migration dùng update pipeline

MongoDB hỗ trợ **aggregation pipeline trong update**; mỗi document được cập nhật nguyên tử. Ví dụ sau thực hiện chuyển đổi đơn giản khi đã xác minh v1 có customerName và customerPhone hợp lệ và **không còn writer cũ chạy song song**:

~~~javascript
db.orders.updateMany(
  {
    $or: [
      { schemaVersion: NumberInt(1) },
      { schemaVersion: { $exists: false } }
    ],
    customerName: { $type: "string" },
    customerPhone: { $type: "string" }
  },
  [
    {
      $set: {
        customer: {
          fullName: "$customerName",
          contact: { phone: "$customerPhone" }
        },
        schemaVersion: NumberInt(2)
      }
    },
    { $unset: ["customerName", "customerPhone"] }
  ]
);
~~~

Pipeline này chỉ chuyển các bản ghi đáp ứng điều kiện. Những document khác cần được ghi nhận và xử lý theo chính sách, không nên lặng lẽ ép dữ liệu lỗi sang v2. Việc có **schemaVersion = 2** trong filter kết quả không còn phù hợp với lần chạy kế tiếp làm thao tác có tính **idempotent** trên dữ liệu đã chuyển: chạy lại không tiếp tục biến đổi document v2.

Tuy nhiên, **idempotent không đồng nghĩa an toàn trước cạnh tranh ghi**. Nếu người dùng cập nhật customerName trong lúc migration đang diễn ra, hoặc instance W1 ghi lại trường cũ sau migration, thay đổi có thể bị ghi đè hoặc sinh document lẫn cấu trúc.

### 8.3. Chống lost update bằng điều kiện revision

Khi ứng dụng vẫn tiếp tục ghi, nên chuyển từng document bằng thao tác có điều kiện trên **revision** (compare-and-set), hoặc dùng cơ chế phối hợp khác đã thống nhất giữa mọi writer.

Ví dụ minh họa với document v1 đã có revision là BSON Long:

~~~javascript
const id = ObjectId("507f1f77bcf86cd799439011");
const before = db.orders.findOne({ _id: id });

if (before &&
    typeof before.customerName === "string" &&
    typeof before.customerPhone === "string") {
  const result = db.orders.updateOne(
    {
      _id: before._id,
      revision: before.revision,
      $or: [
        { schemaVersion: NumberInt(1) },
        { schemaVersion: { $exists: false } }
      ]
    },
    {
      $set: {
        schemaVersion: NumberInt(2),
        customer: {
          fullName: before.customerName,
          contact: { phone: before.customerPhone }
        }
      },
      $unset: {
        customerName: "",
        customerPhone: ""
      },
      $inc: { revision: NumberLong(1) }
    }
  );

  // matchedCount = 0: dữ liệu đã thay đổi; đọc lại và tính chuyển đổi lại.
  printjson({ matched: result.matchedCount, modified: result.modifiedCount });
}
~~~

Điều kiện revision chỉ bảo vệ khi **mọi writer liên quan** cũng cập nhật revision nguyên tử và tôn trọng cùng giao thức cạnh tranh ghi. Nếu một writer cũ thay đổi document nhưng không tăng revision, migration không thể phát hiện xung đột chỉ qua trường này. Với dữ liệu thiếu revision, phải có kế hoạch khởi tạo bộ đếm hoặc dùng phương thức đồng bộ hóa khác; đừng mặc định đoạn mã trên xử lý được mọi bản ghi legacy.

Trong Spring Data MongoDB, **@Version** hỗ trợ optimistic locking với các thao tác được framework quản lý đúng cách; migration chạy qua mongosh, driver hay các lệnh update khác cần tự bảo đảm điều kiện revision tương đương.

### 8.4. Migration theo lô và khả năng tiếp tục

Với hàng triệu document, một lệnh updateMany áp dụng khắp collection có thể tạo tải ghi lớn và khó điều tiết. Một job migration thực tế nên:

1. Duyệt theo khóa ổn định, ví dụ **_id**, kết hợp filter schemaVersion; không dựa vào skip với offset ngày càng lớn.
2. Chuyển từng batch có kích thước phù hợp, giới hạn đồng thời và có thể tạm dừng.
3. Ghi nhận checkpoint, số document thành công, bị bỏ qua, lỗi dữ liệu và xung đột.
4. Nếu xung đột, đọc lại dữ liệu mới nhất rồi tính toán lại, không lặp lại một payload đã cũ.
5. Sau mỗi batch, đo độ trễ ứng dụng, độ trễ ghi, độ trễ replica và thời gian truy vấn.
6. Có lệnh chạy lại chỉ tác động version cũ, kèm cơ chế truy vết lỗi để sửa thủ công các trường hợp không hợp lệ.

Không nên gói toàn bộ migration lớn vào **một transaction duy nhất**. Tính nguyên tử của update trên **một document** thường đủ cho thao tác thay đổi cấu trúc của chính document đó. Nếu thay đổi liên quan đồng thời đến nhiều document hoặc collection và cần giữ bất biến nghiệp vụ xuyên document, phải thiết kế giao thức nhất quán hoặc transaction phù hợp với môi trường MongoDB đang dùng.

## 9. Schema validation khi nhiều cấu trúc cùng tồn tại

MongoDB cho phép cấu hình validator với **$jsonSchema** để mô tả các kiểu BSON và trường bắt buộc. Trong giai đoạn chuyển tiếp, validator có thể cho phép **v1 hoặc v2** bằng **oneOf**.

Ví dụ minh họa cấu trúc validator cho một collection mới:

~~~javascript
db.createCollection("orders_versioned", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      oneOf: [
        {
          required: ["customerName"],
          properties: {
            schemaVersion: { enum: [1] },
            customerName: { bsonType: "string" }
          }
        },
        {
          required: ["schemaVersion", "customer"],
          properties: {
            schemaVersion: { enum: [2] },
            customer: {
              bsonType: "object",
              required: ["fullName"],
              properties: {
                fullName: { bsonType: "string" },
                contact: { bsonType: "object" }
              }
            }
          }
        }
      ]
    }
  }
});
~~~

Nhánh v1 cho phép schemaVersion = 1 **hoặc không có trường**, nhưng không cho phép giá trị version khác khi trường có mặt. Nhánh v2 yêu cầu schemaVersion = 2 và object customer có fullName. Ví dụ cố ý lược bớt các trường chung để tập trung vào version; production cần bổ sung validation cho **items**, **totalMinor**, **placedAt**, kiểu **revision**, quy tắc trường tùy chọn và dữ liệu dual-write.

Với collection đã tồn tại, validator thường được chỉnh qua lệnh **collMod**, đồng thời lựa chọn **validationLevel** và **validationAction** có chủ đích. Đừng bật ngay quy tắc chỉ chấp nhận v2 nếu dữ liệu v1 còn được cập nhật. Validator giúp ngăn dữ liệu sai từ nay về sau; nó **không tự chuyển dữ liệu đã lưu** thành schema mới.

Một lỗi khác là validator quá chặt khiến writer v1 lỗi trong quá trình rolling deploy. Nên triển khai validator ở trạng thái tương thích trước, quan sát lỗi và chỉ siết điều kiện khi đã hoàn thành migration.

## 10. Ánh xạ với Spring Data MongoDB

Lớp lưu trữ v2 có thể được viết rõ ràng bằng annotation, ví dụ:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderV2(
    @Id ObjectId id,
    int schemaVersion,
    Customer customer,
    List<LineItem> items,
    long totalMinor,
    Instant placedAt,
    @Version Long revision
) {
    public record Customer(String fullName, Contact contact) {}
    public record Contact(String phone) {}
    public record LineItem(String sku, int quantity) {}
}
~~~

Trong mô hình này, **schemaVersion** là một thuộc tính dữ liệu bình thường được ứng dụng đặt là **2** khi tạo document mới; **revision** dùng cơ chế optimistic locking của Spring Data. Hai trường không có quan hệ số học và không thể thay thế cho nhau.

Một repository khai báo cho OrderV2 sẽ có những phương thức CRUD thông thường, nhưng **không tự tạo adapter chuyển v1 thành v2**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderV2Repository
        extends MongoRepository<OrderV2, ObjectId> {
}
~~~

Trong giai đoạn collection lẫn nhiều schema, tránh gọi **findAll** của repository này rồi mặc nhiên coi mọi bản ghi là v2. Nên giới hạn truy vấn theo version hoặc đặt một lớp đọc tương thích phía trước.

### 10.1. Khi nào dùng custom converters?

**ReadingConverter** và **WritingConverter** có thể gom logic chuyển đổi ở tầng Spring Data mapping, đặc biệt khi nhiều repository và service đều cần cùng quy tắc. Tuy nhiên, converter phải quy định rõ:

- Nó nhận dạng phiên bản bằng trường nào.
- Version cũ thiếu field được xử lý thế nào.
- Có trả về mô hình bất biến, không bị mất dữ liệu nếu ghi lại không.
- Version lạ được báo lỗi hay đi vào quy trình cách ly dữ liệu.
- Những đường code nào đọc qua mapping converter và đường nào đọc BSON thô.

Converter là công cụ kỹ thuật; chính sách schema và tương thích vẫn phải được thiết kế độc lập. Nếu chỉ một vài truy vấn cần chuyển đổi, một adapter rõ ràng như ví dụ MongoTemplate có thể dễ bảo trì hơn.

### 10.2. Reactive access

Khi dùng **ReactiveMongoTemplate** hoặc reactive repository, nguyên tắc version vẫn giống nhau. Bộ đọc phải nhận biết cấu trúc trong dữ liệu mà nó phát ra; bước chuẩn hóa nên được thực hiện bằng phép biến đổi không chặn trong reactive pipeline. Nếu migration thực hiện bởi job riêng, phải giám sát tốc độ đọc/ghi để không làm suy giảm tài nguyên dành cho luồng reactive của ứng dụng.

Không tạo các thao tác blocking bên trong **map** của Reactor chỉ để tra cứu thêm field. Nếu cần truy cập dữ liệu bên ngoài để chuyển đổi, phải thiết kế đường xử lý bất đồng bộ thích hợp và xem xét tính nhất quán.

## 11. Những thay đổi schema thường gặp và cách đánh giá

| Kiểu thay đổi | Ví dụ | Có thể tương thích với reader cũ? | Điều phải kiểm tra |
| --- | --- | --- | --- |
| Thêm trường tùy chọn | thêm customer.address | Thường có, nếu reader bỏ qua field lạ | Default, missing/null, validator. |
| Thêm trường bắt buộc | thêm customer.country | Không bảo đảm | Backfill, quy tắc tạo mới, validation. |
| Đổi tên trường | customerName → customer.fullName | Thường không | Adapter, truy vấn, index, payload của API. |
| Đổi kiểu dữ liệu | String → BSON Date | Không bảo đảm | Parse, timezone, range query, index, lỗi input. |
| Đổi đơn vị | tiền đồng → tiền xu | Không | Hợp đồng unit, độ chính xác, quy tắc chuyển. |
| Chia một document thành nhiều collection | đơn hàng → đơn hàng + lịch sử | Phụ thuộc mô hình | Giao dịch, tham chiếu, truy vấn hợp nhất. |
| Gộp nhiều trường | firstName + lastName → fullName | Có nguy cơ mất thông tin | Quy tắc nối/tách, tìm kiếm, rollback. |
| Đổi ý nghĩa trạng thái | status = 1 từ “mới” thành “đã duyệt” | Không | Cần migration ngữ nghĩa, không chỉ mapping kiểu. |

Một schema version có ý nghĩa khi gắn với **hợp đồng ngữ nghĩa** của dữ liệu. Nếu cùng một field vẫn có tên cũ nhưng quy ước đơn vị hoặc ý nghĩa thay đổi, giữ nguyên version có thể gây lỗi nghiêm trọng hơn việc đổi cấu trúc hiển nhiên.

## 12. Kiểm thử cho hệ thống có nhiều phiên bản

Bộ kiểm thử nên chứa document mẫu v1, v2 và các trường hợp bất thường. Test với dữ liệu lưu thật trong MongoDB giúp phát hiện lỗi mapping mà unit test chỉ dùng object Java khó tìm ra.

| Trường hợp | Kỳ vọng |
| --- | --- |
| Đọc document v1 có schemaVersion = 1 | Trả OrderView chuẩn với đúng tên, điện thoại, tổng tiền. |
| Đọc document legacy thiếu schemaVersion | Đọc như v1 chỉ khi phù hợp chính sách đã xác nhận. |
| Đọc document v2 | Trả OrderView tương đương về ngữ nghĩa với v1. |
| Version = 3 khi reader chỉ hỗ trợ 1 và 2 | Báo lỗi/metric rõ, không âm thầm đọc thành v1. |
| schemaVersion là String, null hoặc Double | Bị phát hiện là dữ liệu sai hợp đồng. |
| V2 thiếu trường customer.fullName | Không trả dữ liệu rỗng giả; xử lý theo chính sách chất lượng dữ liệu. |
| Chuyển v1 sang v2 rồi đọc lại | Giá trị nghiệp vụ được giữ nguyên. |
| Chạy migration lần hai | Không làm thay đổi document đã chuyển đúng. |
| Hai writer cùng sửa một document | Xung đột được phát hiện khi sử dụng revision đúng cách. |
| Đường truy vấn theo tên và thời gian | Tìm được cả v1/v2 và dùng index như dự kiến. |
| Dừng rollout và rollback ứng dụng | Ứng dụng quay lại vẫn đọc được dữ liệu theo phạm vi tương thích đã cam kết. |

Một chiến lược hữu ích là **contract test**: cùng một dữ liệu đầu vào nghiệp vụ, adapter v1 và v2 phải sinh ra cùng **OrderView**. Những test này nên kiểm chứng cả giá trị và kiểu BSON thật: ObjectId, Int32, Long, Date, Decimal128 nếu hệ thống sử dụng.

## 13. Quan sát và chẩn đoán hiệu năng trong giai đoạn chuyển đổi

Việc duy trì hai schema có chi phí vận hành cần đo được:

1. **Phân bố version**: đếm document theo schemaVersion, missing và kiểu sai.
2. **Tỉ lệ chuyển đổi**: tổng v1 còn lại, số chuyển thành công, số bị bỏ qua, số lỗi/xung đột.
3. **Độ trễ đọc**: chi phí phân nhánh mapper, các truy vấn nhiều nhánh và pipeline chuẩn hóa.
4. **Hiệu năng truy vấn**: theo dõi executionStats, index scan và document scan cho hai đường dẫn trường.
5. **Chi phí ghi**: lưu tạm trường dual write, index bổ sung, lưu lượng replication và kích thước document.
6. **Lỗi tương thích**: schema version lạ, field bắt buộc thiếu, lỗi converter, lỗi validator và optimistic locking.

Ví dụ báo cáo số lượng từng version sau khi loại trừ dữ liệu lỗi:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $cond: [
          { $eq: [{ $type: "$schemaVersion" }, "missing"] },
          "legacy-missing",
          "$schemaVersion"
        ]
      },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
~~~

Nếu collection lớn, không nên chạy aggregation quét toàn collection quá thường xuyên trong giờ cao điểm chỉ để làm dashboard. Có thể thu thập thống kê theo batch migration, metric ở đường ghi hoặc chạy truy vấn định kỳ phù hợp với khả năng hệ thống.

## 14. Rollback và tiêu chí bỏ schema cũ

Rollback là phần của thiết kế version, không phải bước ứng phó sau khi sự cố xảy ra. Nếu một bản phát hành đã ghi **v2 thuần**, quay về code **R1** không thể đọc v2 chỉ bằng việc đổi phiên bản ứng dụng.

Một kế hoạch rollback cần trả lời:

- Đường đọc của bản ứng dụng dự phòng có nhận v2 không?
- Các trường cũ có đang được dual write hay đã xóa?
- Có thể khôi phục ngữ nghĩa v1 từ v2 mà không mất thông tin không?
- Có snapshot/backup và cách phục hồi phù hợp trong trường hợp migration làm sai dữ liệu không?
- Sau khi rollback, writer nào được phép tạo document ở mỗi schema?

Chỉ ngừng hỗ trợ v1 khi có bằng chứng rằng **mọi consumer cần thiết đọc được v2**, **không còn writer tạo v1**, **migration đã được đối soát**, và **cửa sổ rollback đã kết thúc**. Sau đó mới xóa index và converter v1 để giảm gánh nặng bảo trì.

## 15. Thực hành tự kiểm tra

### Bài tập 1: kiểm tra phiên bản đang cùng tồn tại

Giả sử collection có các document:

~~~javascript
db.orders_lab.insertMany([
  { customerName: "Lan", totalMinor: NumberLong("10000") },
  { schemaVersion: NumberInt(1), customerName: "Minh",
    totalMinor: NumberLong("20000") },
  { schemaVersion: NumberInt(2),
    customer: { fullName: "An", contact: { phone: "0900000000" } },
    totalMinor: NumberLong("30000") },
  { schemaVersion: "2", customer: { fullName: "Hà" },
    totalMinor: NumberLong("40000") }
]);
~~~

Hãy xác định số document v1, v2 và không hợp lệ theo hợp đồng schemaVersion kiểu Int32. Viết truy vấn tìm tên “Lan” hoặc “An” mà không lẫn document có version sai kiểu.

**Gợi ý:** document đầu tiên là legacy thiếu version (chỉ coi là v1 nếu đã xác minh); document thứ hai là v1; document thứ ba là v2; document cuối có schemaVersion kiểu String nên cần báo dữ liệu bất thường. Không nên dùng so sánh String "2" làm nhánh v2 hợp lệ.

### Bài tập 2: thiết kế quá trình triển khai

Hệ thống có ba instance: một instance chỉ đọc v1 và hai instance đã đọc v1/v2. Product muốn bật ghi v2 ngay. Hãy chọn trình tự để không làm instance cũ lỗi.

**Gợi ý:** trước hết nâng cấp instance cuối cùng lên reader tương thích; xác nhận các job và dịch vụ phụ thuộc; sau đó mới bật writer v2. Nếu buộc giữ reader cũ, cần đánh giá dual write có đủ tương thích với chính reader đó hay không, rồi thiết kế cách đồng bộ hai nhóm trường trong một lần ghi.

### Bài tập 3: migration với cập nhật đồng thời

Một job đọc customerName = “Lan” từ document v1. Trước lúc job ghi v2, API đổi tên thành “Lan Anh”. Điều gì xảy ra nếu job cập nhật theo _id mà không kiểm tra revision?

**Đáp án:** job có thể dùng dữ liệu cũ để ghi customer.fullName = “Lan”, làm mất thay đổi mới. Cần mọi writer tuân theo cơ chế revision/điều kiện đồng thời hoặc một giao thức nhất quán khác; nếu điều kiện không khớp, job phải đọc lại và chuyển đổi từ trạng thái mới.

### Bài tập 4: thiết kế index

API tìm đơn hàng bằng tên khách hàng, lọc theo khoảng thời gian đặt hàng và hỗ trợ cả v1/v2. Hãy đề xuất truy vấn, index và cách đo.

**Gợi ý:** dùng các nhánh tương thích cho customerName và customer.fullName, kết hợp điều kiện placedAt; kiểm tra hai đường dẫn với **explain("executionStats")**, đánh giá compound index theo dữ liệu thật và chỉ bỏ index v1 khi không còn truy vấn cần nó.

## 16. Tổng kết nguyên tắc thiết kế

- **Ghi version vào document và giữ hợp đồng của mỗi version rõ ràng.** Version phải phản ánh cấu trúc/ý nghĩa dữ liệu, không phụ thuộc tên class Java.
- **Đọc được trước khi ghi mới.** Triển khai reader hiểu cả v1 và v2 trước khi writer tạo v2 thuần.
- **Chuẩn hóa ở biên persistence.** Mapper/adapter chuyển nhiều cấu trúc BSON thành một mô hình nghiệp vụ duy nhất.
- **Migration phải kiểm chứng được và chạy lại an toàn.** Quản lý batch, checkpoint, dữ liệu lỗi và xung đột cập nhật.
- **Tối ưu truy vấn trong thời kỳ hai schema.** Đo index, aggregation, chi phí dual write và độ trễ thực.
- **Kết thúc tương thích dựa trên bằng chứng.** Chỉ xóa schema cũ sau khi tất cả consumer, dữ liệu và chính sách rollback cho phép.

Làm chủ schema versioning giúp dịch vụ **SPRING_DATA_MONGODB** đổi cấu trúc document liên tục mà vẫn duy trì hoạt động ổn định của Spring Data MongoDB, MongoTemplate, repository và các luồng xử lý dữ liệu liên quan.
