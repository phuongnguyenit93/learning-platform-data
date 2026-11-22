# Kiểm tra số lượng, kiểu dữ liệu và tính nhất quán sau chuyển đổi

## 1. Vì sao migration chạy xong chưa có nghĩa dữ liệu đã đúng?

Trong module **SPRING_DATA_MONGODB**, chúng ta sử dụng Spring Data MongoDB để kết nối, ánh xạ document và làm việc với MongoDB qua MongoTemplate hoặc repository. Khi thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng, một nhu cầu xuyên suốt là thay đổi cách lưu trữ dữ liệu mà không làm sai kết quả nghiệp vụ. Chương **Migration dữ liệu** tập trung vào bài toán đó.

Hãy xét ứng dụng bán hàng chuyển từ collection cũ sang một schema MongoDB mới. Công cụ migration có thể báo đã xử lý 100.000 document, nhưng vẫn có khả năng:

- Chỉ 99.998 document được ghi thành công; hai document bị bỏ qua vì dữ liệu lỗi.
- Trường số tiền được lưu thành BSON double thay vì Decimal128, khiến phép tính tiền có nguy cơ sai lệch.
- Trường ngày được lưu thành string hoặc bị lệch múi giờ.
- Một document có trạng thái bị đổi từ PAID sang PENDING trong quá trình mapping.
- Một ID bị gán nhầm cho khách hàng khác, dù tổng số document vẫn bằng nhau.
- Dữ liệu mới có đủ bản ghi nhưng còn tham chiếu tới khách hàng đã bị xóa.

Vì vậy, **kiểm tra sau chuyển đổi (post-migration verification)** phải trả lời ba câu hỏi độc lập:

1. **Đủ chưa?** Mọi document thuộc phạm vi migration đều có bản tương ứng ở đích, không phát sinh bản ghi ngoài dự kiến và không trùng khóa nghiệp vụ.
2. **Đúng kiểu chưa?** Các giá trị thực sự có kiểu BSON và hình dạng schema mong muốn, kể cả trường thiếu hoặc null.
3. **Còn đúng nghĩa nghiệp vụ không?** ID, số tiền, thời gian, trạng thái, tham chiếu và các bất biến nghiệp vụ được bảo toàn sau khi biến đổi.

Số đếm bằng nhau chỉ là **điều kiện cần**, không đủ để xác nhận migration an toàn. Bài học này xây dựng quy trình kiểm tra có thể lặp lại, đưa ra bằng chứng và làm cơ sở quyết định có thể chuyển lưu lượng ứng dụng sang schema mới hay chưa.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa tập dữ liệu nguồn/đích và tiêu chí chấp nhận trước khi so sánh.
2. Dùng countDocuments, aggregation và truy vấn khóa để xác minh số lượng và độ bao phủ.
3. Dùng toán tử $type để phát hiện kiểu BSON sai, null và trường bị thiếu.
4. So sánh các trường đã chuẩn hóa sau chuyển đổi: Decimal128, ngày tháng, enum, ID và quan hệ tham chiếu.
5. Thực hiện kiểm tra qua mongosh và Spring Data MongoDB, đồng thời hiểu giới hạn của kiểm tra từng mẫu.
6. Thiết kế báo cáo reconciliation, xử lý dữ liệu sai và kiểm tra lại trong điều kiện có ghi đồng thời.

## 2. Ví dụ xuyên suốt: chuyển đổi đơn hàng

Giả sử ứng dụng lưu dữ liệu trong cùng một database MongoDB và migration từ collection **orders_legacy** sang **orders_v2**. Quy tắc chuyển đổi đã được phê duyệt như sau:

| Trường ở nguồn | Trường ở đích | Quy tắc |
| --- | --- | --- |
| _id: ObjectId | _id: ObjectId | Giữ nguyên ID để đối soát từng document. |
| totalCents: string | amount: Decimal128 | Diễn giải chuỗi là số nguyên đơn vị cent, chia chính xác cho 100. |
| createdAt: ISO-8601 string UTC | createdAt: BSON Date | Parse theo UTC, không thay đổi thời điểm thực tế. |
| customerId: string | customerId: string | Bảo toàn mã khách hàng. |
| status: string | status: string | Giữ nguyên trạng thái hợp lệ. |

Ví dụ document nguồn:

~~~javascript
// orders_legacy
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  totalCents: "125000",
  createdAt: "2026-10-01T10:15:30Z",
  customerId: "C001",
  status: "PAID"
}
~~~

Kết quả mong đợi ở đích:

~~~javascript
// orders_v2
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  amount: NumberDecimal("1250.00"),
  createdAt: ISODate("2026-10-01T10:15:30Z"),
  customerId: "C001",
  status: "PAID"
}
~~~

Trong ví dụ này:

- Mỗi document nguồn phải có đúng **một** document đích cùng _id.
- Tất cả đơn hàng trong orders_legacy đều thuộc phạm vi chuyển đổi; orders_v2 chỉ chứa các document của migration đang kiểm tra.
- Nguồn dùng thời gian ISO-8601 có ký hiệu múi giờ rõ ràng; giá tiền ở nguồn là chuỗi số nguyên hợp lệ.
- Collection customers có trường _id trùng với customerId của đơn hàng.

Đây là **giả định của bài thực hành**. Trong hệ thống có dữ liệu được loại trừ, nhiều đợt migration hoặc phải tạo ID mới, cần viết rõ bộ lọc eligible, migrationBatchId và khóa ánh xạ trước khi chạy phép so sánh. Không được tự hiểu toàn bộ collection nguồn và đích đều thuộc cùng một lần chuyển đổi.

Sơ đồ kiểm tra:

~~~mermaid
flowchart TD
    A[Chốt phạm vi và quy tắc chuyển đổi] --> B[Kiểm tra số lượng]
    B --> C[Kiểm tra bao phủ theo ID]
    C --> D[Kiểm tra kiểu BSON]
    D --> E[Đối soát giá trị và quan hệ]
    E --> F[Kiểm tra trong lúc có ghi đồng thời]
    F --> G{Tất cả tiêu chí đạt?}
    G -->|Có| H[Phê duyệt chuyển đổi / cutover]
    G -->|Không| I[Ghi nhận sai lệch và xác định nguyên nhân]
    I --> J[Sửa migration hoặc dữ liệu theo quy trình]
    J --> B
~~~

## 3. Đối soát số lượng: không chỉ đếm toàn collection

### 3.1. Đếm chính xác trong phạm vi đã chốt

Chạy trong mongosh:

~~~javascript
const sourceCount = db.orders_legacy.countDocuments({});
const targetCount = db.orders_v2.countDocuments({});

printjson({
  sourceCount,
  targetCount,
  missingByCount: sourceCount - targetCount
});
~~~

**countDocuments(filter)** đếm các document phù hợp bộ lọc. **estimatedDocumentCount()** dùng ước tính dựa trên metadata collection, thích hợp cho các bài toán ước lượng nhanh nhưng **không phù hợp làm bằng chứng chính để nghiệm thu migration**.

Kết quả mong đợi theo giả định của bài:

~~~text
sourceCount = 100000
targetCount = 100000
missingByCount = 0
~~~

Nếu migration chỉ lấy những đơn hàng có trạng thái thuộc một tập cụ thể, cả hai phép đếm phải dùng **cùng định nghĩa đối tượng đủ điều kiện**, có thể qua bộ lọc trạng thái, batch ID hoặc manifest ID. Ví dụ target có migrationBatchId:

~~~javascript
db.orders_v2.countDocuments({
  migrationBatchId: "batch-2026-11"
});
~~~

Không so sánh bộ đếm nguồn được lọc với **toàn bộ** target nếu target đã có những bản ghi từ đợt khác. Cũng không coi hai số bằng nhau là đủ: một document thiếu và một document được ghi thừa vẫn làm tổng số cân bằng.

### 3.2. Kiểm tra phân bố theo trạng thái

Đếm từng loại trạng thái để tìm sai lệch bị che bởi tổng số:

~~~javascript
db.orders_legacy.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);

db.orders_v2.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

So sánh cả **tên nhóm** và **số lượng** giữa hai kết quả. Ví dụ, tổng đều là 100.000 nhưng có 20 đơn PAID bị đổi thành PENDING thì so sánh tổng sẽ không phát hiện được; phép đếm theo trạng thái có thể tìm ra.

Có thể mở rộng đối soát theo ngày, tenant, khu vực hoặc nguồn dữ liệu, miễn quy tắc phân nhóm sau chuyển đổi tương ứng với quy tắc ở nguồn. Khi trường ngày đổi từ string sang BSON Date, cần chuẩn hóa cùng múi giờ trước khi nhóm.

### 3.3. Kiểm tra ID nguồn có mặt ở đích

Trong ví dụ hai collection nằm **cùng database**, dùng $lookup để tìm những ID nguồn không có bản đích:

~~~javascript
db.orders_legacy.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "_id",
      as: "targetMatches"
    }
  },
  {
    $match: {
      "targetMatches.0": { $exists: false }
    }
  },
  { $project: { _id: 1 } },
  { $limit: 20 }
]);
~~~

Nếu có document trả về, đó là các ID nguồn chưa tìm thấy ở target. Kiểm tra chiều ngược lại để bắt bản ghi ngoài phạm vi:

~~~javascript
db.orders_v2.aggregate([
  {
    $lookup: {
      from: "orders_legacy",
      localField: "_id",
      foreignField: "_id",
      as: "sourceMatches"
    }
  },
  {
    $match: {
      "sourceMatches.0": { $exists: false }
    }
  },
  { $project: { _id: 1 } },
  { $limit: 20 }
]);
~~~

Lưu ý: hai truy vấn trên trả tối đa 20 **ví dụ sai lệch**, không phải tổng số sai lệch. Muốn kết luận đạt, thay bước $limit bằng **$count** hoặc ghi kết quả kiểm tra phân vùng đầy đủ, rồi xác nhận số sai lệch bằng 0. Với tập dữ liệu lớn, hãy chia theo dải _id/tenant và ghi checkpoint. Tra cứu _id có index mặc định, nhưng $lookup vẫn có thể tiêu tốn tài nguyên trên collection rất lớn.

Trường hợp migration sinh _id mới, cần lưu **legacyId** hoặc bảng ánh xạ sourceId → targetId có tính duy nhất để thực hiện hai phép kiểm tra này. Việc chỉ đếm tổng số không chứng minh được ánh xạ một-một.

## 4. Kiểm tra kiểu BSON và hình dạng document

### 4.1. Vì sao kiểu Java chưa chứng minh kiểu BSON?

Spring Data MongoDB có thể chuyển đổi giá trị khi đọc document vào POJO/record. Một giá trị từ BSON string hoặc double đôi khi vẫn được chuyển thành BigDecimal hoặc kiểu Java mong muốn. Vì vậy, việc test repository trả về một object đọc được **không chứng minh** dữ liệu trong database đã đúng kiểu lưu trữ.

Đối với ví dụ:

- amount phải là BSON **decimal** (Decimal128), không phải double, string hoặc int.
- createdAt phải là BSON **date**, không phải string.
- customerId và status phải là BSON **string** và tồn tại.
- _id phải là **objectId** theo hợp đồng đã thống nhất.

Kiểm tra phân bố kiểu thực tế trực tiếp bằng aggregation:

~~~javascript
db.orders_v2.aggregate([
  {
    $group: {
      _id: {
        amountType: { $type: "$amount" },
        createdAtType: { $type: "$createdAt" },
        customerIdType: { $type: "$customerId" },
        statusType: { $type: "$status" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Kỳ vọng chỉ có một nhóm:

~~~javascript
{
  _id: {
    amountType: "decimal",
    createdAtType: "date",
    customerIdType: "string",
    statusType: "string"
  },
  count: 100000
}
~~~

Toán tử aggregation **$type** trả về tên kiểu BSON của biểu thức. Khi field không tồn tại, nó trả về **"missing"**; khi field có giá trị null, nó trả về **"null"**. Hai trạng thái đó khác nhau và đều cần xử lý nếu schema yêu cầu trường bắt buộc.

### 4.2. Truy tìm document có kiểu sai

~~~javascript
db.orders_v2.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      createdAtType: { $type: "$createdAt" },
      customerIdType: { $type: "$customerId" },
      statusType: { $type: "$status" }
    }
  },
  {
    $match: {
      $or: [
        { amountType: { $ne: "decimal" } },
        { createdAtType: { $ne: "date" } },
        { customerIdType: { $ne: "string" } },
        { statusType: { $ne: "string" } }
      ]
    }
  },
  { $limit: 20 }
]);
~~~

Kết quả trả về phải rỗng. Để có **tổng số** document sai, dùng $count thay $limit như phần trước. Có thể thêm kiểm tra _id bằng cách đưa biểu thức **{ $type: "$_id" }** vào $project, nếu yêu cầu _id phải là ObjectId.

Với collection dùng schema linh hoạt, không nên áp một bộ quy tắc cứng cho tất cả document. Nếu có version schema hoặc nhiều loại document, hãy **tách theo version/type** rồi kiểm tra bằng hợp đồng tương ứng. Một trường optional có thể hợp lệ khi missing, nhưng field bắt buộc không thể bỏ qua chỉ vì ứng dụng có default value lúc deserialize.

### 4.3. Đặc biệt cẩn thận với số tiền và thời gian

Các chuyển đổi dễ mắc lỗi:

| Dữ liệu | Chuyển đổi có rủi ro | Cách kiểm tra/thiết kế |
| --- | --- | --- |
| "125000" cent → tiền | Đi qua double rồi làm tròn ngầm | Dùng BigDecimal/Decimal128 và phép chia thập phân chính xác. |
| Long → int | Giá trị vượt phạm vi int | Phát hiện overflow, thống nhất kiểu BSON int/long. |
| Timestamp dạng chuỗi | Parse theo timezone mặc định của máy | Thống nhất offset/UTC và precision; so sánh thời điểm, không chỉ chuỗi. |
| "true"/"false" → boolean | So sánh sai hoa/thường hoặc mặc định null | Định nghĩa tập giá trị hợp lệ, kiểm tra kiểu bool thực tế. |
| ID String → ObjectId | String không phải 24 ký tự hex hợp lệ | Kiểm tra quy tắc định danh, tính duy nhất, tham chiếu. |
| null/missing → giá trị mặc định | Biến thiếu dữ liệu thành giá trị có nghĩa nghiệp vụ | Chỉ điền mặc định khi quy tắc migration đã nêu rõ. |

Ví dụ chuyển amount chính xác ở Java:

~~~java
import java.math.BigDecimal;

public final class MoneyMigration {

    private MoneyMigration() {}

    public static BigDecimal centsToAmount(String totalCents) {
        // Chuỗi nguồn phải là số nguyên hợp lệ và có chính sách xử lý lỗi riêng.
        return new BigDecimal(totalCents).movePointLeft(2);
    }
}
~~~

Trong entity Spring Data MongoDB, có thể chỉ định cách lưu BigDecimal bằng Decimal128:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "orders_v2")
public class OrderV2 {
    @Id
    private ObjectId id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private Instant createdAt;
    private String customerId;
    private String status;
}
~~~

Đoạn entity minh họa khai báo kiểu lưu trữ; nó không thay thế phép kiểm tra trực tiếp trên BSON đã ghi. Cách ánh xạ ngày tháng có thể phụ thuộc cấu hình converter, phiên bản driver/Spring Data và quy ước timezone của ứng dụng, nên phải xác minh giá trị BSON Date thực tế.

## 5. Kiểm tra tính nhất quán theo từng document

Sau khi xác định đủ ID và đúng kiểu, cần kiểm tra **giá trị tương đương theo quy tắc chuyển đổi**. So sánh JSON thô của nguồn với đích sẽ sai vì tên trường và kiểu dữ liệu đã thay đổi; thay vào đó, chuẩn hóa giá trị nguồn rồi đối chiếu với target.

### 5.1. So sánh tiền, ngày, khách hàng và trạng thái

Trong ví dụ hai collection cùng database và _id được giữ nguyên, có thể dùng pipeline sau:

~~~javascript
db.orders_legacy.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "_id",
      as: "target"
    }
  },
  // Document không có target đã được xử lý ở bước đối soát độ bao phủ.
  { $unwind: "$target" },
  {
    $set: {
      sourceCentsDecimal: {
        $convert: {
          input: "$totalCents",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      sourceInstant: {
        $dateFromString: {
          dateString: "$createdAt",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      expectedAmount: {
        $divide: ["$sourceCentsDecimal", NumberDecimal("100")]
      }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          { $eq: ["$sourceCentsDecimal", null] },
          { $eq: ["$sourceInstant", null] },
          { $ne: ["$expectedAmount", "$target.amount"] },
          { $ne: ["$sourceInstant", "$target.createdAt"] },
          { $ne: ["$customerId", "$target.customerId"] },
          { $ne: ["$status", "$target.status"] }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      totalCents: 1,
      expectedAmount: 1,
      "target.amount": 1,
      createdAt: 1,
      "target.createdAt": 1,
      customerId: 1,
      "target.customerId": 1,
      status: 1,
      "target.status": 1
    }
  },
  { $limit: 20 }
]);
~~~

Ý nghĩa:

1. $lookup tìm bản đích của mỗi ID nguồn; $unwind đưa bản đích từ mảng về một object.
2. $convert đưa số cent về Decimal128 và chuyển lỗi parse thành null để ghi nhận thay vì dừng pipeline.
3. $dateFromString chuẩn hóa ngày nguồn thành BSON Date.
4. $divide dùng mẫu số Decimal128 để so sánh tiền thập phân.
5. $match giữ lại những bản nguồn không parse được hoặc có bất kỳ trường nào không khớp với target.

Pipeline chỉ cho **20 ví dụ sai** để điều tra. Để nghiệm thu, cần đếm toàn bộ sai lệch thay vì dựa trên $limit, đồng thời xác nhận truy vấn đối soát ID ở phần 3 có số bản thiếu bằng 0. Các phép so sánh số và thời gian phải tuân theo quy tắc làm tròn/độ chính xác đã thống nhất. Ví dụ nguồn có timestamp độ chính xác microsecond nhưng BSON Date chỉ lưu millisecond thì quy tắc giảm precision cần được xác nhận trước.

Nếu lượng dữ liệu rất lớn, việc đối chiếu từng document bằng $lookup có thể tốn nhiều I/O. Có thể chia nhỏ theo dải _id, tenant hoặc batch, lưu kết quả từng phần và xác minh tổng số phần đã kiểm tra. Đặt $match lọc phân vùng càng sớm càng tốt trong pipeline.

### 5.2. Kiểm tra tổng hợp để phát hiện sai lệch hệ thống

Ngoài so sánh từng document, hãy so sánh tổng số tiền theo **cùng đơn vị**. Nguồn lưu cent nên tổng nguồn phải được chia cho 100; đích lưu đơn vị tiền:

~~~javascript
db.orders_legacy.aggregate([
  {
    $set: {
      cents: {
        $convert: {
          input: "$totalCents",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $group: {
      _id: null,
      invalidRows: {
        $sum: { $cond: [{ $eq: ["$cents", null] }, 1, 0] }
      },
      totalCents: { $sum: "$cents" }
    }
  },
  {
    $project: {
      _id: 0,
      invalidRows: 1,
      expectedAmount: {
        $divide: ["$totalCents", NumberDecimal("100")]
      }
    }
  }
]);

db.orders_v2.aggregate([
  {
    $group: {
      _id: null,
      actualAmount: { $sum: "$amount" }
    }
  },
  { $project: { _id: 0, actualAmount: 1 } }
]);
~~~

Tiêu chí ở đây là **invalidRows = 0** và expectedAmount bằng actualAmount theo phép so sánh Decimal128 chính xác. Không tự chấp nhận một dung sai tiền tệ nếu hợp đồng migration yêu cầu bảo toàn đến cent. Lưu ý $sum có thể bỏ qua giá trị không phải số, vì vậy phải chạy kiểm tra kiểu dữ liệu trước và không coi tổng tiền khớp là bằng chứng duy nhất.

Nếu phát hiện tổng số lệch, tiếp tục phân nhóm theo trạng thái, tháng hoặc tenant để xác định phần bị ảnh hưởng. Khi dữ liệu nguồn có thể chứa giá trị quá lớn so với miền Decimal128, phải ghi nhận lỗi chuyển đổi trước khi dùng tổng để kết luận.

### 5.3. Kiểm tra tham chiếu và ràng buộc nghiệp vụ

MongoDB không tự áp đặt khóa ngoại giống nhiều hệ quản trị quan hệ. Vì vậy, document đơn hàng tồn tại chưa chứng minh customerId còn trỏ đến khách hàng hợp lệ.

Nếu customers._id là chuỗi khách hàng như "C001" trong cùng database:

~~~javascript
db.orders_v2.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $match: { "customer.0": { $exists: false } } },
  { $project: { _id: 1, customerId: 1 } },
  { $limit: 20 }
]);
~~~

Kiểm tra loại này cần phản ánh đúng nghiệp vụ: có thể hệ thống cho phép đơn hàng cũ tham chiếu tới khách hàng đã ẩn/được xóa mềm; khi đó tiêu chí phải mô tả trạng thái hợp lệ, không tùy tiện đánh dấu tất cả là lỗi.

Những bất biến thường phải kiểm tra thêm:

- **Tính duy nhất:** _id luôn duy nhất trong collection; nếu _id mới được tạo thì legacyId/orderCode cũng cần được kiểm tra trùng và có thể cần unique index.
- **Bảo toàn thuộc tính:** tổng tiền không âm nếu nghiệp vụ cấm âm, status thuộc danh sách hợp lệ, ngày tạo không nằm trong tương lai nếu không được phép.
- **Quan hệ giữa các trường:** ví dụ trạng thái REFUNDED cần refundAmount phù hợp, trạng thái PAID cần ngày thanh toán.
- **Quan hệ liên collection:** mã khách hàng, sản phẩm, paymentId và invoiceId phải dẫn tới bản ghi tương ứng theo đúng version.
- **Cấu trúc mảng và object lồng nhau:** giữ đúng số phần tử, thứ tự khi có ý nghĩa và các giá trị không trùng.
- **Metadata phục vụ hệ thống:** tenantId, audit fields, version, createdAt/updatedAt và soft-delete flag không bị mất ngoài chủ đích.

## 6. Dùng Spring Data MongoDB trong kiểm thử migration

MongoTemplate cho phép viết kiểm tra tối thiểu ở Java, phù hợp khi một phần kiểm tra cần tích hợp vào bài test hoặc job nghiệm thu.

Ví dụ kiểm tra số lượng và một mẫu kiểu BSON thô:

~~~java
package example.migration;

import java.util.Date;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MigrationVerificationSmokeTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void sourceAndTargetHaveEqualCounts() {
        long source = mongoTemplate.count(
            new Query(), "orders_legacy"
        );
        long target = mongoTemplate.count(
            new Query(), "orders_v2"
        );
        assertEquals(source, target);
    }

    @Test
    void sampleTargetHasExpectedRawBsonTypes() {
        // Đọc Document từ driver để tránh converter Java che khuất kiểu BSON.
        Document raw = mongoTemplate.getCollection("orders_v2")
            .find()
            .first();

        assertNotNull(raw, "Target collection must not be empty");
        assertInstanceOf(Decimal128.class, raw.get("amount"));
        assertInstanceOf(Date.class, raw.get("createdAt"));
        assertInstanceOf(String.class, raw.get("customerId"));
        assertInstanceOf(String.class, raw.get("status"));
    }
}
~~~

**Đây chỉ là smoke test.** Test count có thể bỏ sót một document bị thiếu và một document bị ghi thừa; kiểm tra một document bằng first() không chứng minh toàn bộ collection đúng kiểu. Để nghiệm thu, dùng aggregation kiểm tra tất cả bản ghi, đối soát theo ID và ghi nhận kết quả từng phân vùng. Với dữ liệu lớn, có thể triển khai job reconciliation theo batch, lưu số lượng bản đã kiểm tra, mismatch IDs (có giới hạn hiển thị) và checkpoint.

Nếu chạy kiểm thử cùng database production, nên dùng tài khoản chỉ đọc và tránh vô tình gọi repository.save/delete hoặc các lệnh sửa collection. Các phép verification được thiết kế là read-only; việc sửa sai cần một quy trình migration riêng có khả năng lặp lại an toàn.

### 6.1. Khi cần so sánh từ Java

Với quy tắc chuyển đổi tiền trong bài, không nên so sánh:

~~~java
// Không phù hợp cho tiền: dễ đưa sai số dấu phẩy động vào đối soát.
double amount = Double.parseDouble(totalCents) / 100.0;
~~~

Thay vào đó:

~~~java
import java.math.BigDecimal;

BigDecimal expected = new BigDecimal(totalCents).movePointLeft(2);
BigDecimal actual = decimal128FromMongo.bigDecimalValue();

if (expected.compareTo(actual) != 0) {
    // Ghi nhận sai lệch theo ID và đưa vào báo cáo reconciliation.
}
~~~

BigDecimal.compareTo so sánh giá trị số; BigDecimal.equals còn phân biệt scale, ví dụ 1.0 và 1.00. Nếu hợp đồng yêu cầu bảo toàn cả scale, phải kiểm tra scale riêng. Decimal128 trong MongoDB có giới hạn miền giá trị và độ chính xác; migration cần xử lý rõ trường hợp không biểu diễn được giá trị nguồn.

## 7. Khi nguồn vẫn thay đổi trong lúc kiểm tra

Một nguồn sai lệch phổ biến là đọc số lượng nguồn lúc 10:00, trong khi vẫn có đơn hàng mới ghi vào lúc 10:01 và kiểm tra đích lúc 10:02. Hai phép count có thể đều đúng tại thời điểm chạy nhưng không phản ánh **cùng tập dữ liệu**.

Các lựa chọn tùy hạ tầng và yêu cầu:

| Chiến lược | Cách làm | Điểm cần lưu ý |
| --- | --- | --- |
| Tạm dừng ghi (maintenance window) | Chặn/đợi các thao tác ghi hoàn tất, chốt snapshot và kiểm tra | Dễ đối soát nhất nhưng cần thời gian bảo trì. |
| Phân vùng theo watermark | Chốt thời điểm/ID tối đa hoặc migrationBatchId, so sánh cùng phạm vi | Điều kiện watermark phải ổn định; không đủ nếu dữ liệu cũ vẫn được cập nhật. |
| Backfill + change stream | Nạp lịch sử, tiếp tục áp dụng thay đổi rồi chốt lag trước cutover | Cần kiểm tra thứ tự, resume token, idempotency và các sự kiện chưa xử lý. |
| Snapshot/transaction thích hợp | Đọc các phần quan trọng ở góc nhìn nhất quán khi hạ tầng hỗ trợ | Không giữ transaction lớn, dài hoặc quét toàn bộ dữ liệu chỉ để kiểm tra. |

Trong môi trường replica set/sharded cluster, read concern, write concern, độ trễ replication và thời điểm nhìn thấy dữ liệu có thể ảnh hưởng phép kiểm tra. Cần ghi rõ nguồn, đích, thời điểm chốt, checkpoint và chế độ đọc nhất quán; **majority read** riêng lẻ không tự đảm bảo hai truy vấn chạy lúc khác nhau nhìn thấy cùng snapshot.

Nếu dữ liệu vẫn được cập nhật, một cách an toàn là chốt phạm vi bằng ID/version hoặc watermark, kiểm tra các bản ghi trong phạm vi đó, xác minh change stream đã được áp dụng đến checkpoint và kiểm tra lại ngay trước khi chuyển lưu lượng đọc/ghi.

### 7.1. Hiệu năng kiểm tra quy mô lớn

- Chia nhỏ theo dải khóa ổn định như _id, tenantId hoặc batch ID; ưu tiên **keyset pagination** thay vì skip rất lớn.
- Xác định index phục vụ _id, legacyId, migrationBatchId hoặc các bộ lọc thường dùng; không tạo index vào giờ cao điểm mà chưa đánh giá tác động.
- Đọc theo batch và giới hạn concurrency, tránh làm quá tải CPU, I/O, network hoặc pool kết nối MongoDB.
- Chạy kiểm tra **toàn bộ** nếu kết quả dùng để cutover dữ liệu quan trọng; kiểm tra mẫu phân tầng chỉ là bổ sung để tìm lỗi nhanh.
- Có thể dùng checksum/hash cho dữ liệu đã chuẩn hóa, nhưng cần quy tắc canonical rõ ràng về thứ tự field, thứ tự mảng, Decimal128, null/missing, Unicode và thời gian UTC. Hai checksum của JSON thô có thể khác dù giá trị nghiệp vụ tương đương.
- Ghi lại mismatch IDs và thống kê theo nhóm; giới hạn số ví dụ lưu/log để không vô tình phát tán dữ liệu nhạy cảm.

Một lỗi migration có thể ảnh hưởng đều 1% đơn hàng trong một tháng nhất định, nên lấy 100 bản ngẫu nhiên toàn collection có thể bỏ sót. Chọn mẫu có chủ đích theo tenant, thời gian, trạng thái, giá trị biên và kiểu nguồn khác thường để bổ trợ kiểm tra đầy đủ.

## 8. Lập báo cáo reconciliation và quyết định nghiệm thu

Nên lưu một báo cáo verification riêng cho mỗi lần migration, có thể đọc lại được mà không cần đoán bối cảnh:

| Chỉ số | Giá trị ví dụ | Tiêu chí đạt |
| --- | ---: | --- |
| Phạm vi | orders_legacy → orders_v2, batch A | Đã chốt và ghi rõ bộ lọc, thời điểm. |
| Source eligible | 100.000 | Có nguồn so sánh xác định. |
| Target trong phạm vi | 100.000 | Khớp số lượng nguồn. |
| Source ID không có target | 0 | Bằng 0. |
| Target ID không có source | 0 | Bằng 0, trừ ngoại lệ được phê duyệt. |
| Document sai BSON type/schema | 0 | Bằng 0. |
| Document có giá trị không khớp | 0 | Bằng 0. |
| Tham chiếu không hợp lệ | 0 | Bằng 0 hoặc đúng ngoại lệ nghiệp vụ. |
| Chênh lệch tổng tiền | 0.00 | Bằng 0 theo đơn vị và độ chính xác đã chốt. |
| Change-stream lag tại cutover | 0 sự kiện chưa áp dụng | Đạt checkpoint đã chốt. |

*Các con số trong bảng chỉ là ví dụ minh họa, không phải kết quả chạy trên database.*

Một báo cáo đủ dùng trong thực tế nên kèm:

1. Mã run/batch, version migration script, source/target database và collection, revision hợp đồng schema.
2. Bộ lọc phạm vi, watermark hoặc snapshot, thời điểm bắt đầu/kết thúc và cơ chế xử lý ghi đồng thời.
3. Số lượng đã kiểm tra, số lỗi theo loại, mẫu ID sai lệch, checksum/tổng nhóm nếu có.
4. Kết quả pass/fail cho từng bất biến, ngoại lệ được duyệt, người chịu trách nhiệm xác nhận và kế hoạch rollback.
5. Trạng thái rerun sau khi khắc phục, tránh ghi đè báo cáo thất bại ban đầu.

**Điều kiện PASS** nên rõ ràng và có thể tự động đánh giá: đủ số lượng, bao phủ ID hai chiều, không sai kiểu BSON, không sai giá trị đã chuẩn hóa, không có ràng buộc vi phạm chưa xử lý và đã chốt hết thay đổi trong thời gian migration. Nếu phát hiện lỗi, không tự chỉnh tay một vài document rồi tuyên bố thành công; phải tìm nguyên nhân, sửa quy tắc hoặc dữ liệu theo quy trình, chạy lại trên phạm vi ảnh hưởng và xác minh lại.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ so sánh tổng document | Không thấy thiếu/thừa bù trừ và sai mapping | Kiểm tra ID hai chiều, kiểu và giá trị từng bản. |
| Dùng estimatedDocumentCount để nghiệm thu | Số liệu ước lượng có thể không khớp thực tế | Dùng countDocuments với phạm vi xác định. |
| Kiểm tra bằng entity Java đã map | Converter có thể che kiểu BSON sai | Đọc raw Document hoặc aggregation $type. |
| Chuyển tiền qua double | Sai lệch khi tính toán/làm tròn | Dùng BigDecimal và Decimal128 phù hợp hợp đồng. |
| So sánh ngày chỉ theo chuỗi | Bỏ qua offset, precision hoặc thời điểm | Chuẩn hóa thành Instant/BSON Date theo timezone cụ thể. |
| Dùng $lookup cho cả tập rất lớn không chia batch | Kiểm tra kéo dài, gây tải lên database | Phân vùng, index, checkpoint và theo dõi tải. |
| Chỉ kiểm tra khi write vẫn tiếp tục không có watermark | Đối chiếu hai tập dữ liệu ở thời điểm khác nhau | Chốt snapshot/phạm vi, CDC hoặc maintenance window. |
| Bỏ qua null/missing | Giá trị bắt buộc bị mất không được phát hiện | Kiểm tra $type và required fields. |
| Bỏ qua foreign key logic | Document tồn tại nhưng tham chiếu sai | Dùng $lookup hoặc job kiểm tra quan hệ nghiệp vụ. |
| Chỉ lấy vài mẫu rồi kết luận đủ | Lỗi hiếm hoặc lỗi theo phân vùng bị bỏ sót | Kiểm tra đầy đủ cho nghiệm thu, mẫu là bước hỗ trợ. |

## 10. Bài thực hành đề xuất

Tự tạo tối thiểu 6 đơn hàng nguồn đại diện cho các trường hợp: hợp lệ, số tiền 0, cent có phần lẻ sau quy đổi, trạng thái khác, ngày sát ranh giới UTC và lỗi dữ liệu nguồn. Tạo collection đích từ quy tắc migration đã thống nhất, sau đó cố ý tạo ba dạng sai lệch:

1. Bỏ sót một document và thêm một document không có ở nguồn để tổng số hai collection vẫn bằng nhau.
2. Đổi amount của một document từ Decimal128 sang double.
3. Đổi status hoặc thời gian của một document nhưng vẫn giữ nguyên _id.

Hãy chạy các phép kiểm tra ở phần 3–5 và ghi lại truy vấn nào phát hiện được từng lỗi. Cuối cùng, sửa script migration, chạy lại theo cơ chế idempotent và tạo báo cáo reconciliation với số sai lệch bằng 0. Nếu có dữ liệu khách hàng, bổ sung một tham chiếu customerId không tồn tại để kiểm tra tính toàn vẹn giữa các collection.

**Câu hỏi tự đánh giá:**

- Vì sao sourceCount = targetCount không đủ để đưa hệ thống sang schema mới?
- Khi Spring Data đọc amount thành BigDecimal, làm sao chứng minh dữ liệu MongoDB đã được lưu là Decimal128?
- Nếu hai collection thay đổi trong lúc kiểm tra, cần thông tin nào để biết mình đang đối chiếu cùng một tập dữ liệu?
- Khi nguồn dùng chuỗi cent và đích dùng Decimal128, vì sao không nên so sánh JSON thô hoặc chuyển qua double?

Kiểm tra sau migration là một hoạt động **đối soát có hợp đồng**, nơi mỗi kết luận phải gắn với phạm vi dữ liệu, quy tắc chuyển đổi và bằng chứng đo được. Một lần chạy hoàn tất chỉ chứng minh chương trình đã kết thúc; hệ thống chỉ nên chuyển sang dữ liệu mới khi đã chứng minh đầy đủ, đúng kiểu và nhất quán theo các bất biến nghiệp vụ được chấp nhận.

## 11. Tài liệu tham khảo

- [Spring Data MongoDB – MongoTemplate Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): truy vấn và đếm document bằng MongoTemplate.
- [Spring Data MongoDB – Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): ánh xạ đối tượng Java và BSON.
- [MongoDB – countDocuments()](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/): đếm theo truy vấn.
- [MongoDB – $type (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/): nhận diện kiểu BSON, null và missing.
- [MongoDB – $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): so sánh dữ liệu và tham chiếu giữa collection.
- [MongoDB – $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/): chuyển kiểu và xử lý lỗi chuyển đổi.
- [MongoDB – Decimal128](https://www.mongodb.com/docs/manual/tutorial/model-monetary-data/): mô hình dữ liệu tiền tệ và số thập phân.
