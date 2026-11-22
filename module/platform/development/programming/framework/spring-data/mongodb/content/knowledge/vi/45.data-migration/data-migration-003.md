# Đổi tên trường, chuyển kiểu BSON và bổ sung giá trị mặc định

Trong MongoDB, các document thuộc cùng một collection có thể mang cấu trúc khác nhau. Khi ứng dụng Spring Data MongoDB thay đổi mô hình dữ liệu, bản ghi cũ **không tự thay đổi** theo class Java mới. Migration dữ liệu giúp đưa các document về cấu trúc mà phiên bản ứng dụng mới mong đợi, đồng thời bảo toàn dữ liệu và khả năng hoạt động trong thời gian chuyển đổi.

Bài học này thực hành ba thao tác thường gặp: **đổi tên trường**, **chuyển kiểu BSON** và **bổ sung giá trị mặc định**. Ta sẽ sử dụng cả lệnh MongoDB và `MongoTemplate`, xem cách ánh xạ `Decimal128` trong Spring Data MongoDB, rồi kiểm chứng và triển khai migration an toàn.

## 1. Bài toán và cấu trúc dữ liệu mục tiêu

Giả sử collection `customers` đang có các document như sau:

```javascript
{
  _id: ObjectId("66d000000000000000000001"),
  fullName: "Nguyễn Lan",
  creditLimit: "1250.50",
  createdAt: ISODate("2024-07-01T08:00:00Z")
}
```

Phiên bản ứng dụng mới muốn:

| Trường | Trước migration | Sau migration | Ý nghĩa |
| --- | --- | --- | --- |
| Tên hiển thị | `fullName` | `displayName` | Thống nhất tên trường với mô hình mới |
| Hạn mức tín dụng | `creditLimit` kiểu BSON String | `creditLimit` kiểu BSON Decimal128 | Tính toán số thập phân chính xác hơn |
| Trạng thái kích hoạt | Có thể thiếu `isActive` | `isActive` kiểu Boolean | Có giá trị mặc định rõ ràng cho dữ liệu cũ |

Document mong muốn sau khi chuyển đổi:

```javascript
{
  _id: ObjectId("66d000000000000000000001"),
  displayName: "Nguyễn Lan",
  creditLimit: NumberDecimal("1250.50"),
  isActive: false,
  createdAt: ISODate("2024-07-01T08:00:00Z")
}
```

**Giả định nghiệp vụ của ví dụ:** khách hàng cũ không có `isActive` được xem là chưa kích hoạt (`false`). Với hệ thống thực tế, phải xác nhận ý nghĩa giá trị mặc định với nghiệp vụ trước khi cập nhật; không nên chọn `false` hoặc `true` chỉ vì đó là giá trị tiện dùng trong Java.

Migration cần giải quyết cả dữ liệu không đồng nhất:

- Document đã có `displayName`, hoặc có **cả** `fullName` lẫn `displayName`.
- `creditLimit` đã là Decimal128, là chuỗi hợp lệ, là chuỗi lỗi như `"không rõ"`, là `null` hoặc hoàn toàn vắng mặt.
- `isActive` chưa tồn tại, đã là `true`/`false` hoặc được lưu tường minh thành `null`.

Không nên áp dụng một lệnh cập nhật không có điều kiện cho mọi bản ghi, vì có thể ghi đè giá trị hợp lệ hoặc làm mất dữ liệu cần xử lý thủ công.

## 2. Khảo sát trước khi sửa dữ liệu

Trước khi chạy migration, kiểm tra bản sao lưu/khả năng khôi phục và thống kê các nhóm dữ liệu bằng `mongosh`:

```javascript
const customers = db.getCollection("customers");

// Có thể đổi tên vì tên mới chưa tồn tại.
customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: false }
});

// Cần xử lý xung đột thủ công: cả tên cũ và tên mới cùng tồn tại.
customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: true }
});

// Các giá trị hạn mức hiện đang là chuỗi.
customers.countDocuments({ creditLimit: { $type: "string" } });

// Phân bố kiểu dữ liệu thực tế của trường creditLimit.
customers.aggregate([
  {
    $group: {
      _id: { $type: "$creditLimit" },
      count: { $sum: 1 }
    }
  }
]);

// Phân biệt không có trường với trường hiện diện nhưng mang null.
customers.countDocuments({ isActive: { $exists: false } });
customers.countDocuments({ isActive: { $type: "null" } });
```

Phép kiểm tra `$type` quan trọng vì BSON phân biệt `string`, `int`, `long`, `double` và `decimal`. Cùng một giá trị khi hiển thị có vẻ là số nhưng có thể được lưu dưới nhiều kiểu khác nhau. Với tiền tệ hoặc hạn mức cần độ chính xác thập phân, nên dùng `Decimal128` và `BigDecimal`; chuyển từ `double` không thể tự khôi phục độ chính xác đã mất từ trước.

## 3. Đổi tên trường bằng `$rename`

MongoDB hỗ trợ `$rename` trong câu lệnh update thông thường:

```javascript
const renameResult = db.customers.updateMany(
  {
    fullName: { $exists: true },
    displayName: { $exists: false }
  },
  {
    $rename: { fullName: "displayName" }
  }
);

printjson({
  matched: renameResult.matchedCount,
  modified: renameResult.modifiedCount
});
```

Điều kiện `displayName: { $exists: false }` rất quan trọng: nếu tên đích đã tồn tại, `$rename` có thể thay thế giá trị trường đích. Khi một document chứa cả hai tên, cần kiểm tra xem đó là dữ liệu trùng, dữ liệu mới hơn hay mâu thuẫn nghiệp vụ trước khi quyết định giữ giá trị nào.

`$rename` không tạo giá trị mới khi trường nguồn vắng mặt. Nó phù hợp với việc đổi tên trường ở cấp document hoặc đường dẫn trường lồng nhau thông thường; **không** dùng để đổi tên trực tiếp các trường nằm trong phần tử của mảng. Với mảng subdocument, cần thiết kế phép biến đổi riêng, chẳng hạn dùng `$map` trong aggregation pipeline.

Trong Spring Data MongoDB, `MongoTemplate` cung cấp API tương ứng:

```java
Query query = Query.query(
    Criteria.where("fullName").exists(true)
        .and("displayName").exists(false)
);

Update update = new Update().rename("fullName", "displayName");
UpdateResult result = mongoTemplate.updateMulti(query, update, "customers");
```

Đây là thao tác trực tiếp trên collection. Việc đổi tên property trong class Java hoặc thêm `@Field("displayName")` **không tự đổi tên** trường đang lưu trong database.

## 4. Chuyển BSON String sang Decimal128

MongoDB có các toán tử `$toDecimal` và `$convert`. `$toDecimal` ngắn gọn khi dữ liệu nguồn chắc chắn hợp lệ, nhưng một giá trị không thể chuyển đổi có thể làm lệnh cập nhật thất bại. `$convert` cho phép đặt quy tắc `onError` và `onNull`.

Ví dụ dưới đây chỉ xử lý document có `creditLimit` là BSON String; chuỗi hợp lệ được đổi thành Decimal128, còn chuỗi lỗi được **giữ nguyên** để điều tra:

```javascript
const convertResult = db.customers.updateMany(
  { creditLimit: { $type: "string" } },
  [
    {
      $set: {
        creditLimit: {
          $convert: {
            input: "$creditLimit",
            to: "decimal",
            onError: "$creditLimit",
            onNull: "$creditLimit"
          }
        }
      }
    }
  ]
);

printjson({
  matched: convertResult.matchedCount,
  modified: convertResult.modifiedCount
});
```

Đây là **update bằng aggregation pipeline**: tham số cập nhật là một mảng stage, trong đó `"$creditLimit"` là biểu thức tham chiếu giá trị trường đang lưu. Chẳng hạn, `"1250.50"` được chuyển thành `NumberDecimal("1250.50")`. Với `"không rõ"`, biểu thức `onError` trả lại chuỗi gốc; sau migration, bản ghi này vẫn cần được xử lý.

Không dùng `onError: 0` hoặc `onError: null` chỉ để lệnh chạy hết, bởi cách đó có thể làm mất thông tin gốc. Khi nguồn dữ liệu có dấu phân cách tiền tệ, khoảng trắng không chuẩn hoặc định dạng theo địa phương như `"1.250,50"`, hãy định nghĩa quy tắc làm sạch và kiểm tra trước khi chuyển đổi. Việc chuyển sai số sang Decimal128 còn nguy hiểm hơn việc giữ lại dữ liệu lỗi để xử lý sau.

Với Spring Data MongoDB, có thể sử dụng bộ API của MongoDB Java Driver thông qua `MongoTemplate.getCollection(...)` cho trường hợp cần cú pháp pipeline thô:

```java
Document convert = new Document("$convert",
    new Document("input", "$creditLimit")
        .append("to", "decimal")
        .append("onError", "$creditLimit")
        .append("onNull", "$creditLimit")
);

List<Document> pipeline = List.of(
    new Document("$set", new Document("creditLimit", convert))
);

UpdateResult result = mongoTemplate.getCollection("customers").updateMany(
    new Document("creditLimit", new Document("$type", "string")),
    pipeline
);
```

Cách gọi collection trực tiếp này dùng **tên trường BSON thực tế**. Nó không tự áp dụng các quy tắc ánh xạ property của entity hay các sự kiện lifecycle của `MappingMongoConverter`; cần viết đúng tên trường lưu trong database.

### Ánh xạ Decimal128 trong entity

Khi ứng dụng bắt đầu ghi kiểu mới, entity nên biểu diễn chủ đích lưu `BigDecimal` dưới BSON Decimal128:

```java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("customers")
public class Customer {
    @Id
    private String id;

    @Field("displayName")
    private String displayName;

    @Field(value = "creditLimit", targetType = FieldType.DECIMAL128)
    private BigDecimal creditLimit;

    @Field("isActive")
    private Boolean active;

    // Constructor, getter và setter được lược bớt.
}
```

Chỉ khai báo `BigDecimal` chưa đủ để khẳng định dữ liệu MongoDB sẽ được ghi thành Decimal128: cấu hình converter và `@Field(targetType = FieldType.DECIMAL128)` cần được xem xét cùng nhau. Annotation này tác động đến việc ánh xạ trong ứng dụng; nó **không chuyển đổi hồi tố** document đã tồn tại. Khi còn chuỗi lỗi trong database, việc đọc vào thuộc tính `BigDecimal` có thể gặp lỗi chuyển đổi, nên phải xác minh và xử lý những bản ghi đó trước khi bắt buộc tất cả luồng đọc dùng entity mới.

## 5. Bổ sung giá trị mặc định cho trường thiếu

Giá trị mặc định cho bản ghi cũ nên được ghi có điều kiện:

```javascript
const defaultResult = db.customers.updateMany(
  { isActive: { $exists: false } },
  { $set: { isActive: false } }
);

printjson({
  matched: defaultResult.matchedCount,
  modified: defaultResult.modifiedCount
});
```

Lệnh trên chỉ cập nhật document **chưa có** `isActive`. Document đã lưu `true` hoặc `false` được giữ nguyên. Document có `isActive: null` cũng được giữ nguyên, vì `null` và trường vắng mặt có thể biểu thị hai trạng thái nghiệp vụ khác nhau.

Tương đương trong `MongoTemplate`:

```java
Query query = Query.query(Criteria.where("isActive").exists(false));
Update update = Update.update("isActive", false);

UpdateResult result = mongoTemplate.updateMulti(
    query, update, "customers"
);
```

Nếu nghiệp vụ quy định `null` cũng phải nhận giá trị mặc định, hãy kiểm tra riêng các document có `{ isActive: { $type: "null" } }` rồi chạy một bản cập nhật được phê duyệt cho nhóm đó. Đừng dùng điều kiện `{ isActive: null }` khi chỉ muốn tìm giá trị null tường minh, vì biểu thức đối sánh này còn tìm cả document thiếu trường.

Khi tạo document mới, ứng dụng phải tự ghi `isActive` theo quy tắc nghiệp vụ. Việc backfill dữ liệu cũ không tự cung cấp default cho mọi document được insert trong tương lai.

## 6. Tổ chức migration trong Spring Data MongoDB

Một cách triển khai là đặt logic vào một lớp migration được gọi có kiểm soát từ công cụ vận hành hoặc một tác vụ chỉ chạy một lần. Đoạn mã sau kết hợp ba phép cập nhật đã giải thích:

```java
import java.util.List;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class CustomerDataMigration {
    private final MongoTemplate mongoTemplate;

    public CustomerDataMigration(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void migrate() {
        UpdateResult renamed = mongoTemplate.updateMulti(
            Query.query(
                Criteria.where("fullName").exists(true)
                    .and("displayName").exists(false)
            ),
            new Update().rename("fullName", "displayName"),
            "customers"
        );

        Document convert = new Document("$convert",
            new Document("input", "$creditLimit")
                .append("to", "decimal")
                .append("onError", "$creditLimit")
                .append("onNull", "$creditLimit")
        );
        UpdateResult converted = mongoTemplate
            .getCollection("customers")
            .updateMany(
                new Document("creditLimit", new Document("$type", "string")),
                List.of(new Document("$set",
                    new Document("creditLimit", convert)))
            );

        UpdateResult defaulted = mongoTemplate.updateMulti(
            Query.query(Criteria.where("isActive").exists(false)),
            Update.update("isActive", false),
            "customers"
        );

        System.out.printf(
            "Renamed=%d; converted=%d; defaulted=%d%n",
            renamed.getModifiedCount(),
            converted.getModifiedCount(),
            defaulted.getModifiedCount()
        );
    }
}
```

Để dùng trong hệ thống thật, cần bổ sung **khóa điều phối hoặc cơ chế ghi nhận phiên bản migration**, log và thống kê đầy đủ, chính sách retry, và giám sát tiến độ. Tránh chạy một tác vụ cập nhật hàng loạt không có kiểm soát từ `@PostConstruct` của mọi instance ứng dụng: nhiều instance có thể cùng khởi động, còn migration lớn có thể khiến quá trình deploy kéo dài hoặc phát sinh tải ghi ngoài dự kiến.

Ba lệnh trên **không tạo thành một giao dịch nguyên tử cho toàn bộ collection**. MongoDB bảo đảm tính nguyên tử của thao tác ghi trên từng document, nhưng nếu tiến trình dừng giữa các bước thì collection có thể tạm thời chứa cả hai dạng dữ liệu. Hệ thống cần chấp nhận trạng thái chuyển tiếp hoặc có quy trình deploy theo giai đoạn; không nên đưa toàn bộ collection lớn vào một transaction kéo dài chỉ để áp dụng backfill.

## 7. Kiểm chứng kết quả và khả năng chạy lại

Sau migration, chạy truy vấn kiểm chứng độc lập với `modifiedCount`:

```javascript
// Đã hết document có tên cũ mà chưa có tên mới hay chưa?
db.customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: false }
});

// Có document chứa cả hai tên không? Cần đối soát thủ công.
db.customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: true }
});

// Chuỗi còn lại là các giá trị không chuyển được hoặc chưa xử lý.
db.customers.find(
  { creditLimit: { $type: "string" } },
  { displayName: 1, creditLimit: 1 }
);

// Trường mặc định còn bị thiếu không?
db.customers.countDocuments({ isActive: { $exists: false } });

// Quan sát cấu trúc BSON sau chuyển đổi.
db.customers.aggregate([
  { $group: { _id: { $type: "$creditLimit" }, count: { $sum: 1 } } }
]);
```

Với bộ dữ liệu mẫu hợp lệ, chạy lại các bước nên giữ nguyên kết quả: trường đã đổi tên không được đổi lại; Decimal128 không khớp bộ lọc kiểu String; document có `isActive` không khớp điều kiện thiếu trường. Riêng chuỗi chuyển đổi lỗi vẫn được giữ lại và có thể được thử lại ở những lần chạy sau; số lượng nhóm lỗi này cần được theo dõi cho đến khi được xử lý.

Một bộ kiểm thử tích hợp hữu ích nên tạo các tình huống:

| Dữ liệu ban đầu | Kết quả cần xác nhận |
| --- | --- |
| Chỉ có `fullName` | Đổi thành `displayName`, không mất nội dung |
| Có cả `fullName` và `displayName` | Không ghi đè `displayName`; báo nhóm xung đột |
| `creditLimit: "1250.50"` | BSON sau migration là `decimal` |
| `creditLimit: "không rõ"` | Chuỗi gốc được giữ, được thống kê để xử lý |
| `creditLimit` đã là Decimal128 | Không bị chuyển đổi lại |
| Thiếu `isActive` | Thêm Boolean `false` theo giả định nghiệp vụ |
| `isActive: true` hoặc `isActive: null` | Không bị thay đổi ngoài ý muốn |
| Chạy migration lần thứ hai | Các document hợp lệ không đổi trạng thái |

Đặc biệt, hãy so sánh **số document trước/sau**, các trường nghiệp vụ quan trọng và một tập mẫu đã biết, thay vì chỉ dựa vào việc lệnh trả về không có exception. `matchedCount` và `modifiedCount` là chỉ số tiến độ, không phải bằng chứng rằng tất cả dữ liệu đã đúng schema.

## 8. Triển khai trên hệ thống đang hoạt động

Với hệ thống có nhiều phiên bản ứng dụng cùng hoạt động trong quá trình deploy, thứ tự thực tế thường là:

1. **Khảo sát và chuẩn bị:** thống kê kiểu BSON, tên trường, giá trị null, nhóm xung đột; lưu bản sao có thể khôi phục và chọn khung giờ phù hợp.
2. **Bảo đảm khả năng tương thích:** phiên bản ứng dụng chuyển tiếp có thể đọc cả `fullName` và `displayName`, đồng thời xử lý dữ liệu `creditLimit` chưa chuyển xong. Xác định rõ thời điểm ngừng ghi kiểu cũ.
3. **Chạy migration có theo dõi:** ưu tiên điều kiện lọc chính xác; với collection lớn, chia thành các đợt theo `_id` hoặc khoảng dữ liệu ổn định, giới hạn tải và ghi log số lượng xử lý/lỗi.
4. **Đối soát:** xác minh dữ liệu, xử lý chuỗi sai định dạng và tên trường xung đột, kiểm tra các truy vấn và phép tính trên Decimal128.
5. **Chuyển hoàn toàn sang schema mới:** cập nhật entity/repository, chỉ mục và quy tắc kiểm tra schema; bỏ logic tương thích cũ khi toàn bộ nơi đọc/ghi đã chuyển.

Nếu truy vấn của ứng dụng sử dụng `displayName`, xem xét chỉ mục tương ứng sau khi đo hiệu năng:

```javascript
db.customers.createIndex({ displayName: 1 });
```

Chỉ mục của `fullName` có thể vẫn cần cho phiên bản ứng dụng cũ trong giai đoạn chuyển tiếp. Việc tạo/xóa chỉ mục, quét collection và cập nhật số lượng lớn document có ảnh hưởng đến thời gian phản hồi, I/O, replication lag và dung lượng lưu trữ. Nên đo trên dữ liệu thử gần với thực tế và theo dõi hệ thống khi chạy từng đợt.

Khi cần quay lui, không mặc định rằng ba phép cập nhật đảo ngược được hoàn toàn: đổi tên có thể tạo xung đột sau đó, chuyển kiểu có thể thay đổi biểu diễn gốc, còn việc thêm `false` làm mất thông tin “trước đây trường này chưa tồn tại”. Bản sao lưu hoặc nhật ký thay đổi trước migration là cơ sở khôi phục đáng tin cậy.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Chạy `$rename` khi trường đích đã tồn tại | Có thể làm mất giá trị mới | Lọc `$exists: false` và xử lý bản ghi xung đột riêng |
| Dùng `$toDecimal` trên dữ liệu chưa kiểm tra | Giá trị lỗi làm cập nhật thất bại | Dùng `$convert` có `onError`, thống kê dữ liệu lỗi |
| Coi `null` như trường không tồn tại | Ghi đè một trạng thái nghiệp vụ | Phân biệt `$exists: false` và `$type: "null"` |
| Chỉ đổi `@Field` hoặc kiểu Java | Document cũ vẫn mang schema cũ | Chạy data migration, xác minh BSON thật |
| Chạy cập nhật lớn ngay lúc mọi instance khởi động | Tăng tải, xung đột và khó điều phối | Dùng migration runner/đợt chạy có kiểm soát |
| Tin rằng nhiều lệnh `updateMany` là một transaction | Có dữ liệu ở trạng thái chuyển tiếp | Thiết kế deploy tương thích và phép cập nhật chạy lại an toàn |

## 10. Bài thực hành

Tạo collection `customers` thử nghiệm gồm ít nhất sáu document: tên cũ đơn lẻ, hai tên xung đột, hạn mức là chuỗi số đúng, chuỗi sai, Decimal128 đã chuẩn và trạng thái `isActive` là `null`. Thực hiện lần lượt các bước đổi tên, chuyển kiểu và điền mặc định bằng `mongosh` hoặc `MongoTemplate`.

Kết quả đạt yêu cầu khi:

- Tất cả document đủ điều kiện được đổi sang `displayName` mà không ghi đè tên mới đã có.
- Các chuỗi hạn mức hợp lệ trở thành BSON Decimal128; chuỗi lỗi vẫn được giữ để điều tra.
- Chỉ document thiếu `isActive` nhận mặc định đã thỏa thuận.
- Các truy vấn kiểm chứng chỉ ra chính xác các bản ghi cần xử lý tiếp và chạy migration lần hai không làm hỏng dữ liệu đã hợp lệ.

**Ghi nhớ:** migration thành công không chỉ là việc chạy được `updateMany`. Nó phải diễn giải đúng ý nghĩa dữ liệu cũ, giới hạn đối tượng cập nhật, giữ khả năng phát hiện lỗi và chứng minh được cấu trúc BSON sau chuyển đổi phù hợp với Spring Data MongoDB.
