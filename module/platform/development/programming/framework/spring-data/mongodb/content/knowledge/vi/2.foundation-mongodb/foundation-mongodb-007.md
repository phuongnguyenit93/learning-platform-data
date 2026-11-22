# Tính nguyên tử của một document và thao tác trên nhiều document

Trong MongoDB, **một thao tác ghi trên một document có tính nguyên tử (atomic)**: các thay đổi của thao tác đó trên document được áp dụng như một đơn vị. Ngược lại, khi một nghiệp vụ thay đổi **nhiều document**, từng lần ghi đơn lẻ vẫn nguyên tử nhưng toàn bộ nghiệp vụ không tự động trở thành một giao dịch “tất cả hoặc không có gì”.

Đây là nền tảng để thiết kế mô hình dữ liệu và viết mã với **Spring Data MongoDB**. Bạn có thể tận dụng tính nguyên tử ở cấp document bằng các toán tử cập nhật của MongoDB, dùng điều kiện để tránh tranh chấp đồng thời, hoặc dùng transaction khi tính nhất quán của nghiệp vụ trải trên nhiều document.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích chính xác phạm vi nguyên tử của `insertOne`, `updateOne`, `findOneAndUpdate` và `updateMany`.
- Dùng điều kiện trong bộ lọc cùng `$inc`, `$set` và các toán tử cập nhật khác để bảo vệ bất biến của **một document** khi nhiều yêu cầu chạy đồng thời.
- Nhận diện tình huống nhiều document cần transaction, phân biệt với tình huống nên gom dữ liệu liên quan vào một document.
- Triển khai cập nhật nguyên tử qua `MongoTemplate` và transaction qua `MongoTransactionManager` cùng `@Transactional`.
- Phân biệt **atomicity**, **isolation**, **durability**, xác định giới hạn khi hệ thống có nhiều dịch vụ hoặc xử lý song song.
- Thiết kế kiểm thử cho các trường hợp thiếu dữ liệu, lỗi giữa quy trình và tranh chấp đồng thời.

## 2. Phạm vi nguyên tử của một document

Document là đơn vị lưu trữ chính của MongoDB; một document có thể chứa trường đơn, object lồng nhau và mảng. Một lệnh cập nhật có thể thay đổi **nhiều trường của cùng một document**, nhưng bên ngoài không quan sát thấy trạng thái trung gian của riêng lệnh ghi đó.

Ví dụ, đơn hàng được lưu như sau:

```json
{
  "_id": "ORD-1001",
  "status": "NEW",
  "payment": { "state": "PENDING" },
  "revision": 0
}
```

Chuyển trạng thái đơn hàng bằng **một** lệnh:

```javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  {
    $set: {
      status: "CONFIRMED",
      "payment.state": "AUTHORIZED"
    },
    $inc: { revision: 1 }
  }
);
```

Hai trường `status`, `payment.state` và trường `revision` được cập nhật nguyên tử trong document `ORD-1001`. Nếu document không còn ở trạng thái `NEW` tại thời điểm ghi, điều kiện lọc không thỏa và thao tác không cập nhật document ấy.

**Cần phân biệt:** MongoDB chỉ bảo đảm nguyên tử đối với những thay đổi nằm **trong cùng một lệnh ghi trên một document**. Nếu ứng dụng gọi ba lệnh `updateOne` riêng biệt để sửa ba trường, có thể có khoảng thời gian giữa các lệnh, khi một phần thay đổi đã được ghi và phần còn lại chưa được ghi.

### Điều kiện lọc là một phần quan trọng của cập nhật đồng thời

Xét tồn kho có `available = 5`. Hai khách hàng cùng đặt mua 4 sản phẩm:

- Nếu ứng dụng đọc `available`, tự tính `available - 4` rồi gọi `save` mà không kiểm tra phiên bản hoặc điều kiện, có nguy cơ **ghi đè kết quả của nhau** (lost update).
- Nếu mỗi yêu cầu thực hiện một lệnh cập nhật với điều kiện `available >= 4` và `$inc: { available: -4 }`, chỉ một yêu cầu có thể trừ tồn kho thành công. Yêu cầu còn lại không còn thỏa điều kiện.

```javascript
const result = db.inventory.updateOne(
  { _id: "SKU-01", available: { $gte: 4 } },
  { $inc: { available: -4, reserved: 4 } }
);

if (result.modifiedCount !== 1) {
  // Không tìm thấy SKU hoặc tồn kho không đủ.
}
```

Điểm mấu chốt là **kiểm tra điều kiện và thay đổi giá trị xảy ra trong cùng lệnh ghi**. `$inc` tính dựa trên giá trị hiện tại trên server; ứng dụng không cần tự đọc rồi tính giá trị cuối cùng. Với bộ lọc không phụ thuộc trường thay đổi, các lần ghi cạnh tranh có thể vẫn ghi tiếp và ghi đè lẫn nhau: tính nguyên tử của từng lần ghi không tự giải quyết mọi bài toán đồng thời.

> **Nguyên tắc thực hành:** Khi một bất biến chỉ nằm trong một document, ưu tiên biểu diễn bất biến bằng bộ lọc và toán tử cập nhật trong **một** câu lệnh, rồi kiểm tra `matchedCount` / `modifiedCount` hoặc kết quả trả về.

## 3. Nhiều document: nguyên tử ở từng phần tử, không tự nguyên tử toàn bộ

Giả sử câu lệnh sau tăng giá cho mọi sản phẩm thuộc một nhóm:

```javascript
db.products.updateMany(
  { category: "books" },
  { $inc: { price: 1000 } }
);
```

Mỗi document được cập nhật nguyên tử. Tuy nhiên, **cả lệnh `updateMany` không phải một transaction nhiều document**. Trong khi thao tác đang diễn ra, truy vấn khác có thể thấy một số sản phẩm đã tăng giá và một số chưa tăng; nếu lệnh bị lỗi giữa chừng, các thay đổi đã thực hiện không tự động được rollback như một nhóm.

Điều tương tự áp dụng cho các lệnh ghi nhiều phần tử thông thường, kể cả `bulkWrite`: việc gom nhiều thao tác vào một lệnh gọi API **không** mặc nhiên tạo tính nguyên tử cho tất cả document. Các lựa chọn như thứ tự thực thi (`ordered` / `unordered`) chủ yếu chi phối cách tiếp tục sau lỗi, không biến toàn bộ batch thành một transaction.

| Thao tác | Phạm vi nguyên tử mặc định | Điều cần lưu ý |
| --- | --- | --- |
| `insertOne` / `replaceOne` | Một document | Toàn bộ document được ghi hoặc không được ghi bởi thao tác đó. |
| `updateOne` | Một document | Có thể cập nhật đồng thời nhiều trường và phần tử mảng của document ấy. |
| `findOneAndUpdate` / `findAndModify` | Một document | Tìm và sửa trong một thao tác nguyên tử; có thể trả về bản trước hoặc sau khi sửa. |
| `updateMany` | **Từng** document được sửa | Không có rollback tự động cho toàn bộ tập document. |
| Hai lệnh `updateOne` liên tiếp | Mỗi lệnh riêng lẻ | Có trạng thái trung gian giữa hai lệnh. |
| Các lệnh nằm trong một transaction hợp lệ | Các thay đổi thuộc transaction | Commit hoặc rollback theo transaction; phụ thuộc cấu hình, triển khai và xử lý lỗi. |

### Tình huống chuyển tiền giữa hai tài khoản

Giả sử số dư nằm trong **hai document**:

```json
{ "_id": "A", "balanceCents": 50000 }
{ "_id": "B", "balanceCents": 20000 }
```

Nghiệp vụ “chuyển 10.000 xu từ A sang B” gồm:

1. Trừ 10.000 xu ở document A.
2. Cộng 10.000 xu ở document B.

Nếu bước 1 thành công nhưng tiến trình dừng trước bước 2, tổng tiền bị sai. Tính nguyên tử của mỗi `updateOne` không bảo đảm hai lần cập nhật cùng thành công hoặc cùng thất bại. **Transaction** giải quyết yêu cầu nguyên tử xuyên nhiều document trong cùng hệ thống MongoDB.

## 4. Spring Data MongoDB: cập nhật nguyên tử qua MongoTemplate

Với Spring Data MongoDB, `MongoTemplate` giúp gửi trực tiếp bộ lọc và toán tử cập nhật xuống MongoDB. Ta dùng một document tồn kho:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("inventory")
public class Inventory {
    @Id
    private String id;
    private long available;
    private long reserved;

    public Inventory() {}

    // Getter/setter có thể được bổ sung khi ứng dụng cần đọc hoặc khởi tạo dữ liệu.
}
```

Dịch vụ đặt trước tồn kho:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final MongoTemplate mongoTemplate;

    public InventoryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean reserve(String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }

        Query query = Query.query(
            Criteria.where("_id").is(sku)
                    .and("available").gte(quantity)
        );
        Update update = new Update()
                .inc("available", -quantity)
                .inc("reserved", quantity);

        UpdateResult result =
                mongoTemplate.updateFirst(query, update, Inventory.class);

        return result.getModifiedCount() == 1;
    }
}
```

Bất biến được duy trì ở **một document**: `available` không âm; `available + reserved` không thay đổi sau khi đặt trước, miễn là mọi đường cập nhật khác cũng tuân thủ quy tắc nghiệp vụ.

Lưu ý:

- Không cần transaction nhiều document cho đúng **một** lệnh `updateFirst` như trên.
- `modifiedCount == 1` chỉ xác nhận có một document được thay đổi; `0` có thể do SKU không tồn tại hoặc không đủ tồn kho. Muốn trả lỗi khác nhau, có thể đọc thêm để hiển thị thông báo, nhưng quyết định thành công vẫn phải dựa trên **kết quả cập nhật nguyên tử**.
- Đảm bảo các thao tác khác không tự ý ghi lại trường `available` bằng giá trị cũ; tránh trộn lệnh `$inc` với chu trình “đọc rồi `save`” không có cơ chế kiểm soát xung đột.

### Khi nào dùng `@Version`?

Nếu nghiệp vụ phải đọc một document, tính toán nhiều quy tắc ở tầng Java rồi `save` lại document, có thể dùng **optimistic locking**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("profiles")
public class Profile {
    @Id
    private String id;

    @Version
    private Long version;

    private String displayName;
    private String address;

    // Constructor và getter/setter tùy nhu cầu ứng dụng.
}
```

Spring Data MongoDB dùng trường phiên bản để phát hiện khi document đã bị một thao tác tương thích thay đổi kể từ lần đọc; một lần `save` với phiên bản cũ có thể phát sinh `OptimisticLockingFailureException`. Cơ chế này hữu ích khi không thể diễn đạt thao tác chỉ bằng `$inc` / `$set` có điều kiện.

Để phát hiện xung đột đáng tin cậy, **mọi đường ghi liên quan phải tuân thủ cùng chiến lược phiên bản**, và write concern cần xác nhận kết quả ghi. `@Version` không biến hai document thành một transaction và không tự bảo vệ trước các ứng dụng khác cố tình bỏ qua version.

## 5. Transaction nhiều document trong Spring Data MongoDB

Để thao tác đồng thời trên nhiều document theo nguyên tắc “tất cả hoặc không có gì”, dùng MongoDB multi-document transaction.

**Điều kiện triển khai:** MongoDB phải chạy trên **replica set** hoặc **sharded cluster** hỗ trợ transaction; MongoDB standalone thông thường không hỗ trợ transaction nhiều document. Ứng dụng cần cấu hình transaction manager tương ứng và thực hiện các lệnh qua cùng ngữ cảnh transaction.

### 5.1. Cấu hình MongoTransactionManager

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
```

Trong cấu hình imperative này, Spring dùng `MongoTransactionManager` để mở và gắn `ClientSession` với luồng thực thi. Các lệnh `MongoTemplate` hoặc repository tham gia transaction khi dùng đúng `MongoDatabaseFactory` và ngữ cảnh Spring transaction.

### 5.2. Hai lần cập nhật cùng thuộc một transaction

Định nghĩa document tài khoản; sử dụng **đơn vị tiền nhỏ nhất** dưới dạng số nguyên để phép `$inc` có ý nghĩa rõ ràng và tránh các sai số kiểu dấu phẩy động:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("accounts")
public class Account {
    @Id
    private String id;

    private long balanceCents;

    public Account() {}
}
```

Dịch vụ chuyển tiền:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final MongoTemplate mongoTemplate;

    public TransferService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional
    public void transfer(String fromId, String toId, long amountCents) {
        if (amountCents <= 0 || fromId == null || toId == null
                || fromId.equals(toId)) {
            throw new IllegalArgumentException("Thông tin chuyển tiền không hợp lệ");
        }

        UpdateResult debit = mongoTemplate.updateFirst(
            Query.query(Criteria.where("_id").is(fromId)
                                .and("balanceCents").gte(amountCents)),
            new Update().inc("balanceCents", -amountCents),
            Account.class
        );
        if (debit.getModifiedCount() != 1) {
            throw new IllegalStateException(
                "Tài khoản nguồn không tồn tại hoặc không đủ tiền");
        }

        UpdateResult credit = mongoTemplate.updateFirst(
            Query.query(Criteria.where("_id").is(toId)),
            new Update().inc("balanceCents", amountCents),
            Account.class
        );
        if (credit.getModifiedCount() != 1) {
            throw new IllegalStateException("Tài khoản đích không tồn tại");
        }
    }
}
```

Trong ngữ cảnh `@Transactional` hoạt động đúng, nếu không tìm thấy tài khoản đích thì exception không kiểm tra (`RuntimeException`) khiến Spring rollback cả lần trừ tiền trước đó. Nếu hai cập nhật thành công và transaction commit thành công, hai thay đổi thuộc một transaction.

**Không nên hiểu mã ví dụ là hệ thống thanh toán sản xuất đã hoàn chỉnh.** Với chuyển tiền thật, còn cần khóa nghiệp vụ duy nhất cho mỗi yêu cầu (idempotency key), sổ cái giao dịch, kiểm soát quyền, kiểm toán, đối soát và xử lý retry một cách an toàn.

### 5.3. Các giới hạn quan trọng của `@Transactional`

- Chỉ gắn `@Transactional` mà **không cấu hình transaction manager MongoDB phù hợp** thì chưa đủ để có transaction nhiều document như ví dụ.
- Lời gọi phương thức nội bộ trong cùng một bean (`this.transfer(...)`) thường không đi qua Spring proxy, nên có thể không kích hoạt interceptor transaction.
- Mặc định, Spring rollback cho `RuntimeException` và `Error`. Nếu muốn rollback cho checked exception, cấu hình `rollbackFor` hoặc quy tắc rollback tương ứng.
- Gọi một API ngoài (ví dụ cổng thanh toán) bên trong transaction **không đưa API ngoài vào transaction MongoDB**. Khi cần phối hợp sự kiện hoặc hệ thống khác, cân nhắc outbox, saga và thao tác bù.
- Với luồng reactive, sử dụng `ReactiveMongoTransactionManager` và ngữ cảnh phản ứng (`ReactiveMongoTemplate` / repository reactive); không áp dụng máy móc mô hình transaction theo thread của `MongoTransactionManager`.

### 5.4. Xử lý xung đột và lỗi commit

Transaction có thể thất bại khi có cập nhật cạnh tranh, lỗi mạng hoặc lỗi tạm thời. Ứng dụng phải nhận biết kết quả và triển khai **retry có kiểm soát**, dựa trên loại lỗi phù hợp; không được giả định mọi transaction tự động retry đến thành công.

Trong thực tế cần phân biệt:

- Lỗi cho thấy transaction cần **chạy lại toàn bộ**; trước lần thử mới phải tạo ngữ cảnh transaction mới.
- Kết quả `commitTransaction` **chưa rõ** do lỗi kết nối; không được vội thực hiện lại nghiệp vụ với một mã giao dịch mới vì có nguy cơ thực thi trùng.
- Logic nghiệp vụ cần có idempotency để một yêu cầu lặp lại không tạo thêm lần chuyển tiền ngoài ý muốn.

Không nên giữ transaction mở để chờ tương tác người dùng hay thực hiện truy vấn chậm. Chuẩn bị index phù hợp, giảm số document phải ghi và giữ transaction ngắn.

## 6. Atomicity khác isolation và durability

Ba thuộc tính thường bị nhầm lẫn:

| Thuộc tính | Câu hỏi cần trả lời | Minh họa |
| --- | --- | --- |
| **Atomicity** (nguyên tử) | Thao tác/transaction có áp dụng toàn bộ hay không? | Một lần cập nhật `available` và `reserved` trong cùng document không bị ghi dở. |
| **Isolation** (cô lập) | Các thao tác đồng thời có thể nhìn thấy và ảnh hưởng nhau thế nào? | Transaction có mô hình đọc nhất quán và có thể gặp write conflict; không mặc nhiên tương đương mọi mức cô lập của SQL. |
| **Durability** (bền vững) | Dữ liệu đã được xác nhận có còn an toàn khi có sự cố hay failover? | Write concern, cấu hình replica set và chính sách ghi ảnh hưởng khả năng dữ liệu đã xác nhận được duy trì. |

Ví dụ, một lần `updateOne` luôn nguyên tử trên document ngay cả khi dùng write concern yếu; nhưng **nguyên tử không đồng nghĩa** rằng thay đổi chắc chắn bền vững qua mọi sự cố. Khi cần bảo đảm trước failover, cần lựa chọn write concern phù hợp (thường cân nhắc `majority`), cùng các thiết lập đọc và commit tương ứng.

Transaction hỗ trợ nguyên tử ở phạm vi nhiều document, nhưng cách các client khác quan sát dữ liệu còn tùy **read concern, read preference, write concern và topology**. Không nên suy từ “transaction” ra rằng mọi kiểu đọc của mọi client ở mọi thời điểm đều là serializable.

## 7. Thiết kế dữ liệu để tận dụng nguyên tử cấp document

Một quyết định quan trọng với MongoDB là **embed** (nhúng dữ liệu liên quan vào một document) hay **reference** (liên kết nhiều document).

Giả sử đơn hàng cần cập nhật trạng thái đơn, danh sách dòng hàng và tổng tiền như một đơn vị. Nếu dữ liệu có kích thước vừa phải và thường được đọc/sửa cùng nhau, lưu trong một document giúp nhiều quy tắc được bảo vệ bằng một thao tác cập nhật.

```json
{
  "_id": "ORD-1002",
  "status": "DRAFT",
  "items": [
    { "sku": "SKU-01", "qty": 2, "unitPriceCents": 12000 },
    { "sku": "SKU-02", "qty": 1, "unitPriceCents": 9000 }
  ],
  "totalCents": 33000
}
```

Ngược lại, nếu tài khoản, sản phẩm, kho và đơn hàng có vòng đời riêng và được cập nhật thường xuyên bởi các tác vụ khác nhau, việc cố nhét tất cả vào một document có thể gây tăng kích thước, tranh chấp ghi và khó truy vấn. Khi cần bảo vệ bất biến trải trên nhiều document, hãy dùng transaction hoặc điều chỉnh thiết kế nghiệp vụ.

Một số tiêu chí:

| Câu hỏi | Hướng thiết kế |
| --- | --- |
| Dữ liệu có thường được thay đổi và đọc cùng lúc không? | Cân nhắc nhúng để hưởng tính nguyên tử một document. |
| Mảng có thể tăng không giới hạn không? | Tránh nhúng không giới hạn; MongoDB có giới hạn kích thước BSON của document (thông thường 16 MiB). |
| Các thực thể có vòng đời và tần suất cập nhật độc lập không? | Cân nhắc tách document; nếu cập nhật liên quan cần tất cả hoặc không có gì, đánh giá transaction. |
| Một document bị nhiều luồng ghi nóng liên tục không? | Đánh giá contention, partition mô hình dữ liệu và tải thực tế. |
| Nghiệp vụ đi qua database/hệ thống bên ngoài MongoDB không? | Transaction MongoDB không bao trùm hệ thống khác; cân nhắc cơ chế điều phối phù hợp. |

**Không nhất thiết mọi quan hệ đều cần transaction.** Nhiều trường hợp chấp nhận nhất quán cuối cùng (eventual consistency), chẳng hạn đồng bộ một giá trị tổng hợp phục vụ báo cáo. Quyết định phụ thuộc **bất biến nghiệp vụ**, không chỉ số lượng collection tham gia.

## 8. Kiểm thử tính nguyên tử và transaction

Nên kiểm thử cả kết quả dữ liệu cuối cùng lẫn các trường hợp lỗi. Một bộ kiểm thử tích hợp nên kết nối MongoDB có cấu hình replica set khi kiểm tra transaction; chỉ chạy MongoDB standalone có thể làm test transaction thất bại ngay ở bước bắt đầu.

### Kịch bản A — Hai yêu cầu đặt trước cùng một lượng hàng

Dữ liệu ban đầu: `available = 5`, `reserved = 0`. Chạy đồng thời hai lần `reserve("SKU-01", 4)`.

Kỳ vọng: chỉ **một** yêu cầu trả về `true`; dữ liệu cuối cùng `available = 1` và `reserved = 4`. Xác nhận bất biến không âm, không phụ thuộc thứ tự hai luồng chạy.

### Kịch bản B — Rollback chuyển tiền

Ban đầu: `A = 50_000`, `B = 20_000`. Thực hiện `transfer("A", "MISSING", 10_000)`.

Kỳ vọng: dịch vụ báo lỗi; transaction rollback, nên số dư của A vẫn là `50_000` và B vẫn là `20_000`. Nếu thấy A đã bị trừ thì cần kiểm tra transaction manager, topology hoặc cách gọi service.

### Kịch bản C — Chuyển tiền hợp lệ

Thực hiện `transfer("A", "B", 10_000)`.

Kỳ vọng: A còn `40_000`, B thành `30_000`; tổng số dư không đổi. Chạy thêm kịch bản nhiều yêu cầu đồng thời để phát hiện xung đột và kiểm tra chính sách retry của ứng dụng.

### Kịch bản D — Phân biệt updateMany và transaction

Chuẩn bị nhiều document, thực hiện `updateMany` rồi tạo lỗi có kiểm soát trong quy trình nhiều lệnh. Không đặt kỳ vọng rằng một lỗi ở câu lệnh sau sẽ tự hoàn tác kết quả `updateMany` trước đó khi **không có transaction**. Chạy lại quy trình bên trong transaction để kiểm tra ranh giới rollback.

### Điểm quan sát khi chẩn đoán

- Ghi log **ID nghiệp vụ, số document khớp/sửa**, thời gian xử lý và mã lỗi; hạn chế ghi dữ liệu nhạy cảm.
- Theo dõi `writeConflict`, lỗi transaction tạm thời, timeout và retry tăng bất thường.
- Dùng `explain` cho các truy vấn lọc thường xuyên; index phù hợp giúp giảm thời gian và chi phí thực thi, dù không thay đổi bản chất nguyên tử của thao tác.
- Kiểm tra dữ liệu tồn tại và đúng kiểu số trước khi dùng `$inc`; thống nhất đơn vị tiền hoặc số lượng giữa các dịch vụ.

## 9. Sai lầm thường gặp

**“`updateMany` là một câu lệnh nên phải nguyên tử trên mọi document?”**  
Không. Lệnh này cập nhật nguyên tử **từng document**, không phải toàn bộ tập kết quả.

**“`@Transactional` là đủ để transaction tự chạy trên mọi MongoDB?”**  
Không. Cần transaction manager, MongoDB deployment hỗ trợ và đường gọi thực sự đi qua Spring transaction interceptor.

**“Đọc số dư rồi `save` đã an toàn vì `save` là một thao tác nguyên tử?”**  
Chưa đủ. Lần `save` có thể nguyên tử nhưng vẫn ghi đè giá trị mới do luồng khác thay đổi trong khoảng thời gian sau lần đọc. Hãy dùng cập nhật có điều kiện/toán tử nguyên tử hoặc optimistic locking.

**“Transaction MongoDB sẽ rollback cả lời gọi HTTP, Kafka và email?”**  
Không. Transaction chỉ bao phủ các thao tác MongoDB tham gia cùng transaction; hệ thống ngoài cần cơ chế nhất quán riêng.

**“Có transaction thì không cần xử lý xung đột?”**  
Không. Concurrent transaction có thể gặp write conflict hoặc lỗi tạm thời. Ứng dụng cần chiến lược retry và idempotency phù hợp.

## 10. Bài tập tự luyện

1. Viết API `POST /inventory/{sku}/reserve` dùng `MongoTemplate`, từ chối `quantity <= 0` và số lượng vượt tồn kho; giải thích vì sao hai yêu cầu đồng thời không thể cùng trừ vượt `available`.
2. Một giỏ hàng lưu ở một document gồm các sản phẩm và `totalCents`. Đề xuất một cách cập nhật nguyên tử hai trường này; phân tích khi nào nên tách sang collection khác.
3. Tạo service chuyển điểm giữa hai ví khách hàng; chạy kiểm thử lỗi khi không tồn tại ví nhận, kiểm tra cả hai số dư sau rollback.
4. Giải thích vì sao một batch `bulkWrite` không tương đương transaction, và mô tả trường hợp nên dùng transaction thay vì thay đổi mô hình dữ liệu.
5. Phân tích tình huống retry khi commit transaction báo kết quả chưa rõ. Thiết kế một `transferId` duy nhất để tránh phát sinh giao dịch trùng.

## 11. Tổng kết kiến thức

- **Một lệnh ghi, một document:** nguyên tử; nhiều trường trong document có thể được sửa cùng lúc.
- **Một lệnh cập nhật nhiều document:** nguyên tử trên **từng document**; không có nguyên tử xuyên cả tập theo mặc định.
- **Nhiều thao tác liên quan:** dùng điều kiện và toán tử cập nhật nếu bất biến gói trong một document; dùng MongoDB transaction nếu bất biến trải trên nhiều document và cần commit/rollback cùng nhau.
- **Ở tầng Spring Data MongoDB:** `MongoTemplate` biểu diễn bộ lọc/toán tử; `@Version` hỗ trợ optimistic locking; `MongoTransactionManager` kết hợp `@Transactional` tạo ranh giới transaction khi môi trường phù hợp.
- **Trong hệ thống thực tế:** kiểm thử cạnh tranh, rollback, read/write concern, retry và idempotency là phần không thể bỏ qua khi đánh giá tính đúng đắn của quy trình.

### Tài liệu tham khảo chính thức

- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- Spring Data MongoDB — [Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).
