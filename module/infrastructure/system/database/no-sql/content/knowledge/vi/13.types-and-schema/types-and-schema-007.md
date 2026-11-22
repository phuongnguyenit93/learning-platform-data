# Kiểu dữ liệu lồng nhau, trường mở rộng và giới hạn kích thước

## 1. Vì sao kiểu dữ liệu và giới hạn kích thước ảnh hưởng trực tiếp đến thiết kế NoSQL?

Một hệ thống học trực tuyến cần lưu hồ sơ người học, địa chỉ liên hệ, danh sách khóa đang học, cấu hình thông báo và lịch sử hoạt động. Trong mô hình tài liệu (document model), ta có thể gom những thông tin liên quan vào một đối tượng JSON:

~~~json
{
  "learnerId": "L001",
  "displayName": "An",
  "contact": {
    "email": "an@example.test",
    "address": {
      "city": "Hồ Chí Minh",
      "country": "VN"
    }
  },
  "preferences": {
    "language": "vi",
    "notifications": {
      "email": true,
      "push": false
    }
  },
  "enrollments": [
    {
      "courseId": "C101",
      "status": "ACTIVE",
      "progressPercent": 65
    },
    {
      "courseId": "C102",
      "status": "COMPLETED",
      "progressPercent": 100
    }
  ]
}
~~~

Tài liệu này minh họa ba đặc điểm phổ biến của NoSQL:

1. **Kiểu dữ liệu lồng nhau:** Một trường có thể chứa một đối tượng khác, một mảng hoặc cấu trúc phức tạp nhiều cấp.
2. **Trường mở rộng (flexible/dynamic fields):** Hai tài liệu có thể không có cùng tập trường, hoặc mỗi nhóm đối tượng có thêm thuộc tính theo nhu cầu.
3. **Giới hạn kích thước và độ sâu:** Cơ sở dữ liệu vẫn giới hạn kích thước item/document, độ sâu lồng nhau, số thuộc tính, kiểu giá trị hoặc chi phí cập nhật; không thể nhúng vô hạn dữ liệu vào một bản ghi.

Khả năng lưu JSON linh hoạt rất hữu ích, nhưng cũng dễ dẫn đến thiết kế thiếu kiểm soát: mảng tăng mãi, trường động không biết ai sở hữu, dữ liệu cũ/ mới không tương thích, truy vấn khó lập chỉ mục và một lần cập nhật nhỏ phải xử lý đối tượng quá lớn.

**Mục tiêu của bài học:** Phân biệt các cấu trúc dữ liệu lồng nhau, thiết kế trường mở rộng có quy tắc, hiểu giới hạn theo sản phẩm, thao tác và lập chỉ mục đúng trên dữ liệu lồng nhau, nhận diện lúc nào nên nhúng hoặc tách thành bản ghi riêng, và xây dựng chiến lược tiến hóa schema an toàn.

**Phạm vi công nghệ:** Bài dùng MongoDB, DynamoDB, Cassandra/ScyllaDB và Redis làm ví dụ. Những hệ này không có cùng mô hình kiểu dữ liệu: BSON document, Map/List trong item, collection/UDT của CQL và giá trị Redis có ngữ nghĩa khác nhau. Các giới hạn định lượng cần hiểu trong đúng ngữ cảnh sản phẩm, API và phiên bản.

## 2. Phân loại kiểu dữ liệu: vô hướng, đối tượng, mảng và tập hợp

### 2.1. Kiểu vô hướng (scalar)

Các giá trị cơ bản thường gặp:

| Nhóm | Ví dụ JSON | Ghi chú |
|---|---|---|
| Chuỗi | "An", "C101" | Dùng cho tên, ID, mã trạng thái, mô tả |
| Số | 65, 1590000, 3.14 | Kiểu số cụ thể khác nhau giữa JSON, BSON, DynamoDB, CQL |
| Boolean | true, false | Dùng cho cờ bật/tắt có ý nghĩa rõ |
| Null | null | Giá trị tồn tại nhưng rỗng; khác trường vắng mặt |
| Ngày/giờ | "2026-11-14T08:40:00Z" | JSON chỉ có chuỗi; một số database có kiểu ngày riêng |
| Nhị phân | Không có biểu diễn chuẩn trực tiếp trong JSON | Nhiều database hỗ trợ binary ở dạng riêng |

Một lưu ý quan trọng: **JSON Number không phân biệt integer, float và decimal** theo cùng cách các cơ sở dữ liệu thực thi. Khi liên quan tiền tệ, định danh lớn, thời gian hoặc phép cộng chính xác, phải chọn kiểu lưu cụ thể.

Ví dụ, số tiền 1.590.000 VND có thể được biểu diễn bằng **số nguyên đơn vị đồng** thay vì số thực. Với tiền tệ có đơn vị phụ, cần quy ước số đơn vị nguyên nhỏ nhất hoặc kiểu decimal có độ chính xác được bảo đảm.

### 2.2. Object/Map: cấu trúc theo tên trường

Ví dụ:

~~~json
{
  "profile": {
    "displayName": "An",
    "avatar": "/avatars/L001.webp"
  },
  "settings": {
    "theme": "dark",
    "language": "vi"
  }
}
~~~

**Object** trong JSON hoặc **Map** trong một số database là tập các cặp tên–giá trị. Nó phù hợp khi các trường có ý nghĩa và có thể được truy cập theo tên, chẳng hạn profile.displayName hoặc settings.theme.

Tuy nhiên, Map không có nghĩa mọi trường đều được phép thay đổi kiểu tùy ý. Nếu một record dùng settings.notifications.email là boolean nhưng record khác dùng chuỗi "yes", ứng dụng phải xử lý trường hợp không nhất quán.

### 2.3. Array/List: cấu trúc nhiều phần tử có thứ tự

~~~json
{
  "chapters": [
    {"chapterId": "CH01", "title": "Giới thiệu"},
    {"chapterId": "CH02", "title": "Mô hình tài liệu"}
  ]
}
~~~

Mảng giữ **nhiều phần tử**, thường có thứ tự và có thể chứa đối tượng lồng nhau. Mảng phù hợp với danh sách nhỏ, được đọc cùng document cha và có vòng đời gần nhau.

Nhưng mảng có thể chứa hai phần tử giống nhau nếu ứng dụng không cấm. Nếu một bài chỉ có một enrollment hiện hành cho mỗi courseId, không thể suy “đã là mảng nên không bị trùng”.

### 2.4. Set: tập hợp không chứa phần tử trùng theo ngữ nghĩa

Ví dụ tập tag:

~~~text
{"nosql", "database", "backend"}
~~~

Set khác List ở chỗ **không giữ các phần tử trùng nhau** theo quy tắc của hệ. Trong Redis, kiểu SET là tập các chuỗi; DynamoDB có kiểu String Set, Number Set và Binary Set; Cassandra có set trong CQL. Các hệ này không đồng nhất về thứ tự, khả năng chứa object, giá trị rỗng hoặc các thao tác cập nhật.

Nếu cần hiển thị tag theo thứ tự người dùng kéo thả, set thường không phù hợp vì thứ tự không phải phần ý nghĩa của tập hợp. Nếu cần bảo đảm duy nhất và không quan tâm thứ tự, set có thể phù hợp.

### 2.5. Map/List/Set không phải lúc nào cũng dùng giống JSON

JSON chuẩn có object và array, nhưng **không có Set riêng**. Khi trao đổi dữ liệu qua HTTP JSON, một set thường được chuyển thành mảng; bước lưu trữ cần bảo đảm không có phần tử trùng. Ngược lại, khi đọc Set từ một driver, kiểu được trả về có thể là một cấu trúc tập hợp của ngôn ngữ lập trình chứ không chỉ là array.

## 3. Hiểu cấu trúc lồng nhau qua một ví dụ

Giả sử một đơn hàng:

~~~json
{
  "orderId": "O1001",
  "customerId": "C17",
  "shipping": {
    "recipient": {
      "name": "An",
      "phone": "0900000000"
    },
    "address": {
      "country": "VN",
      "city": "Đà Nẵng",
      "district": "Hải Châu",
      "line1": "Địa chỉ minh họa"
    }
  },
  "items": [
    {
      "lineId": "L1",
      "sku": "SKU-42",
      "qty": 2,
      "unitPriceMinor": 1590000,
      "attributes": {
        "color": "black",
        "warrantyMonths": 12
      }
    },
    {
      "lineId": "L2",
      "sku": "SKU-99",
      "qty": 1,
      "unitPriceMinor": 500000,
      "attributes": {
        "storage": "128GB"
      }
    }
  ],
  "status": "PENDING",
  "schemaVersion": 2
}
~~~

Có thể đọc cấu trúc theo đường dẫn:

~~~text
orderId
shipping
shipping.recipient
shipping.recipient.name
shipping.address.city
items
items[0]
items[0].sku
items[0].attributes.color
items[1].attributes.storage
~~~

Những đường dẫn giúp định nghĩa logic truy cập, nhưng **cú pháp query và update theo đường dẫn của từng database không nhất thiết giống cú pháp truy cập object trong JavaScript**.

Về ngữ nghĩa:

- shipping.recipient là một object đơn.
- items là một mảng line item.
- attributes là một object chứa thuộc tính tùy nhóm sản phẩm.
- schemaVersion là thông tin phiên bản để ứng dụng diễn giải các document được ghi theo schema khác nhau.

**Điểm cần phân tích:** Đơn hàng có thể gồm vài line item, nhưng nếu nghiệp vụ cho phép hàng chục nghìn line item hoặc liên tục bổ sung lịch sử giao hàng, cấu trúc nhúng có thể trở nên không phù hợp dù cú pháp JSON vẫn hợp lệ.

## 4. Lồng nhau và mở rộng là hai quyết định khác nhau

### 4.1. Lồng nhau để phản ánh cấu trúc và vòng đời

Ví dụ:

~~~json
{
  "customerId": "C17",
  "preferredContact": {
    "channel": "email",
    "address": "an@example.test"
  }
}
~~~

preferredContact thuộc về khách hàng, số lượng nhỏ, thường đọc cùng profile nên có lý do để nhúng.

### 4.2. Trường mở rộng để hỗ trợ biến thể nghiệp vụ

Ví dụ sản phẩm:

~~~json
{
  "sku": "SKU-42",
  "category": "HEADPHONE",
  "attributes": {
    "color": "black",
    "wireless": true,
    "batteryHours": 20
  }
}
~~~

Trong khi sản phẩm điện thoại có:

~~~json
{
  "sku": "SKU-99",
  "category": "PHONE",
  "attributes": {
    "storageGb": 128,
    "simType": "eSIM",
    "screenSizeInches": 6.1
  }
}
~~~

Hai sản phẩm có cùng các trường lõi sku/category nhưng attributes khác nhau theo loại. Đây là **schema linh hoạt có chủ đích**; không có nghĩa toàn bộ đối tượng được phép tùy tiện đổi kiểu hoặc thêm tên trường không kiểm soát.

### 4.3. Một schema linh hoạt vẫn cần hợp đồng

Thay vì cho mọi client ghi bất kỳ nội dung nào, có thể quy định:

~~~text
Trường lõi bắt buộc:
  sku: non-empty string
  category: enum
  status: enum
  schemaVersion: integer

Trường mở rộng:
  attributes: object
  Tập key được phép phụ thuộc category.
  Mỗi key có kiểu, phạm vi và đơn vị đo cụ thể.
  Giới hạn độ sâu, số key, kích thước.
~~~

Không có một hợp đồng như vậy, việc thêm trường sẽ dần biến thành **schema không thể dự đoán**, gây khó lập chỉ mục, tìm lỗi và tiến hóa ứng dụng.

## 5. Khi nào nên nhúng, khi nào nên tách thành bản ghi khác?

### 5.1. Những yếu tố ủng hộ embedding

Nhúng phù hợp khi dữ liệu con:

- Có số lượng **nhỏ hoặc giới hạn rõ ràng**.
- Được đọc cùng đối tượng cha trong phần lớn yêu cầu.
- Được cập nhật cùng cha hoặc trong phạm vi nguyên tử của một document.
- Không cần truy vấn độc lập bởi nhiều cách truy cập khác nhau.
- Có cùng vòng đời lưu trữ và xóa với đối tượng cha.

Ví dụ hồ sơ người học có tối đa hai địa chỉ liên hệ hoặc một tập cấu hình thông báo tương đối nhỏ.

### 5.2. Những yếu tố ủng hộ reference/separate collection

Tách riêng phù hợp khi dữ liệu con:

- Có thể **tăng không giới hạn**: lịch sử thao tác, bình luận, follower, thông báo.
- Có tải ghi cao hoặc nhiều client cùng cập nhật.
- Có yêu cầu phân trang, lọc, sắp xếp riêng.
- Được nhiều đối tượng khác cùng tham chiếu.
- Có retention hoặc quyền truy cập khác cha.
- Là dữ liệu lớn như ảnh, video, file đính kèm.

Ví dụ:

~~~text
Learner document
  learnerId
  displayName
  preferences

LearningActivity collection
  activityId
  learnerId
  occurredAt
  eventType
  metadata
~~~

Không nên đưa toàn bộ LearningActivity vào mảng learner.activities chỉ vì MongoDB hoặc một document store cho phép array.

### 5.3. Bảng quyết định

| Yêu cầu | Nhúng | Tách riêng |
|---|---|---|
| Một vài địa chỉ có kích thước nhỏ | Thường phù hợp | Cần nếu địa chỉ có vòng đời riêng |
| 10 mục cấu hình cố định | Phù hợp | Ít lợi ích |
| 1 triệu sự kiện người dùng | Không phù hợp thành một mảng | Phù hợp theo khóa/bucket thời gian |
| 5 ảnh sản phẩm có metadata nhỏ | Có thể nhúng metadata | File nhị phân nên lưu ngoài document lớn |
| Số lần người học đăng ký khóa khác nhau | Tùy quy mô | Thường nên tách enrollment |
| Lịch sử phiên bản cần audit | Không nên tăng vô hạn trong cha | Bảng phiên bản hoặc event log |
| Một subobject thường cần cập nhật nguyên tử cùng cha | Có lợi khi nhúng | Cần transaction hoặc thiết kế khác nếu tách |

### 5.4. Không nên nhầm nhúng với lặp dữ liệu

Nhúng **một** danh sách con vào document cha là quyết định **gom nhóm dữ liệu**. Lặp title khóa học vào nhiều EnrollmentView là quyết định **denormalization**. Hai kỹ thuật có thể kết hợp nhưng không giống nhau.

## 6. Sự khác biệt giữa trường vắng mặt, null và giá trị rỗng

### 6.1. Ba trạng thái khác nhau

Xét:

~~~json
{"learnerId": "L001"}
~~~

~~~json
{"learnerId": "L001", "middleName": null}
~~~

~~~json
{"learnerId": "L001", "middleName": ""}
~~~

Ba trường hợp:

1. **Missing:** Trường middleName không có trong document.
2. **Null:** Trường tồn tại nhưng giá trị null.
3. **Empty string:** Trường tồn tại và là chuỗi rỗng.

Tương tự, mảng rỗng [] khác mảng không tồn tại và khác null.

### 6.2. Ảnh hưởng đến schema evolution

Giả sử field notificationsEnabled được thêm vào schema phiên bản 2. Những document phiên bản 1 có thể thiếu field này.

Ứng dụng phải định nghĩa:

~~~text
Nếu thiếu notificationsEnabled:
    mặc định false hay true?

Nếu notificationsEnabled = null:
    nghĩa là chưa cấu hình, không xác định
    hay phải coi là dữ liệu lỗi?

Nếu notificationsEnabled = "yes":
    chấp nhận giá trị cũ hay từ chối vì sai kiểu?
~~~

Không thể mặc định “field vắng mặt = null” trong mọi query engine. Chẳng hạn một số toán tử của MongoDB có ngữ nghĩa đặc biệt khi tìm null và có thể khớp trường thiếu; nếu cần phân biệt chắc chắn, phải dùng điều kiện tồn tại/kiểu tương ứng.

### 6.3. Thiết kế một ý nghĩa duy nhất

Ví dụ cho shipping.address.line2:

- Missing: Chưa có trường này theo schema cũ.
- Null: Người dùng chủ động khai báo không có dòng địa chỉ thứ hai.
- "": Form gửi chuỗi rỗng nhưng cần chuẩn hóa khi ghi.

Nếu những trạng thái đó không có ý nghĩa khác nhau về nghiệp vụ, nên chuẩn hóa về một cách lưu để giảm nhánh xử lý.

## 7. Kiểu số, ngày và giá trị nhị phân trong môi trường JSON

### 7.1. JSON Number không phải là hợp đồng về độ chính xác

JSON có giá trị số như 10, 10.5, 9007199254740993; nhưng các runtime và database có thể dùng biểu diễn integer/float/decimal khác nhau.

Một số integer lớn có thể mất độ chính xác khi đi qua môi trường dùng số thực IEEE-754 double, chẳng hạn JavaScript Number. Vì vậy **ID số nguyên lớn, version, tiền tệ hoặc counter** cần được thiết kế với kiểu dữ liệu và cách serialize rõ ràng.

Ví dụ nên cân nhắc:

~~~json
{
  "amountMinor": 1590000,
  "currency": "VND",
  "paymentReference": "9007199254740993"
}
~~~

paymentReference là chuỗi vì đây là **định danh**, không phải số để tính toán.

### 7.2. Ngày/giờ và múi giờ

~~~json
{
  "occurredAt": "2026-11-14T08:30:00Z",
  "timezone": "Asia/Ho_Chi_Minh"
}
~~~

Một ISO 8601 string có UTC offset và một timestamp native đều có thể biểu diễn thời điểm, nhưng không phải mọi hệ lưu và so sánh chúng theo cùng cách. Nên quy định:

- Thời điểm có UTC/offset hay chỉ là ngày lịch?
- Múi giờ nghiệp vụ được lưu ở đâu?
- Độ chính xác đến giây, mili giây hay micro giây?
- Dữ liệu được sắp xếp bằng kiểu date hay chuỗi?

Đặc biệt, trường **activityDay** được dùng làm partition/bucket cần tính theo múi giờ thống nhất. Nếu hai service phân ngày khác nhau, cùng sự kiện có thể rơi vào hai partition khác nhau.

### 7.3. Binary payload không nên nhúng tùy tiện

Hình ảnh, file PDF, video hoặc blob có thể được biểu diễn bằng binary type trong một số database hoặc base64 trong JSON. Nhưng base64 làm payload lớn hơn dữ liệu nhị phân thô, chưa kể overhead document.

Mẫu phổ biến:

~~~json
{
  "attachmentId": "A1001",
  "fileName": "assignment.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 3500000,
  "objectKey": "assignments/A1001",
  "sha256": "digest-minh-hoa"
}
~~~

Metadata nhỏ nằm trong document; nội dung lớn ở **object storage hoặc một cơ chế lưu file phù hợp**. Trường objectKey cần được truy cập qua quyền kiểm soát phù hợp, không mặc định URL công khai.

## 8. Giới hạn kích thước: phải nghĩ bằng byte, không phải số dòng JSON

### 8.1. Những giới hạn thường gặp

| Hệ/kiểu dữ liệu | Giới hạn tiêu biểu cần nhớ | Ngữ cảnh |
|---|---|---|
| **MongoDB** | Kích thước một BSON document tối đa **16 MiB**; độ sâu lồng nhau tối đa **100 cấp** | Giới hạn document và nested BSON objects/arrays; dữ liệu lớn có thể dùng GridFS hoặc tách document |
| **Amazon DynamoDB** | Một item tối đa **400 KB** theo quy ước kích thước item của dịch vụ; độ sâu Map/List tối đa **32 cấp** | Tính cả kích thước thuộc tính và overhead liên quan, không chỉ JSON hiển thị |
| **Cassandra/ScyllaDB** | Có giới hạn kỹ thuật theo kiểu collection, kích thước value/partition, request và phiên bản triển khai | Không nên nhúng collection cực lớn; phải đánh giá mô hình partition và cập nhật |
| **Redis** | Giới hạn phụ thuộc kiểu dữ liệu, phiên bản, cấu hình bộ nhớ và cơ chế lưu | Một giá trị JSON dạng string hoặc một collection lớn vẫn có chi phí bộ nhớ, mạng và cập nhật |
| **Search index** | Giới hạn field/mapping, kích thước tài liệu và độ sâu có thể phụ thuộc engine/cấu hình | Dữ liệu nested nhiều trường động có thể gây mapping explosion |

**Không được suy** rằng một hệ “hỗ trợ JSON lồng nhau” đồng nghĩa có thể gửi object lớn tùy ý. Số liệu trong bảng là những mốc phổ biến, nhưng khi triển khai phải xác nhận **phiên bản, API và chế độ lưu trữ thực tế**. MongoDB giới hạn 16 MiB theo BSON document, không phải đúng 16 triệu ký tự JSON.

### 8.2. Byte và ký tự khác nhau

Ví dụ:

~~~text
"A"       -> một ký tự ASCII, thường 1 byte UTF-8.
"Đ"       -> một ký tự Unicode, thường nhiều byte UTF-8.
"📚"      -> một emoji, thường 4 byte UTF-8.
~~~

Kích thước một document có thể gồm:

- Byte của tên field.
- Byte của giá trị.
- Thông tin kiểu và metadata theo định dạng lưu.
- Cấu trúc mảng/object, ID và các field hệ thống.

Vì vậy, phép đếm ký tự của JSON pretty-print **không chính xác bằng cách đo kích thước BSON/item sau serialize**. Dữ liệu tiếng Việt có dấu và emoji càng dễ làm phép ước lượng theo ký tự bị sai.

### 8.3. Dung lượng trung bình nhân số phần tử

Một learner có 120.000 activity, mỗi activity trung bình 300 byte phần dữ liệu ứng dụng:

\[
120.000 \times 300 = 36.000.000\ \text{byte}.
\]

Đây đã là khoảng **36 MB phần dữ liệu thô**, chưa kể overhead. Nếu cố lưu vào một MongoDB document thì vượt giới hạn 16 MiB; nếu đưa vào một DynamoDB item thì vượt rất xa giới hạn 400 KB.

Giải pháp không phải “nén JSON thêm một ít rồi bỏ kiểm tra”, mà thường là tách activity thành các document/item theo khóa, theo ngày hoặc theo bucket.

### 8.4. Cần chừa khoảng tăng trưởng

Nếu một document đang gần giới hạn, một lần thêm trường hoặc phần tử nhỏ có thể làm ghi thất bại. Vì vậy **không nên thiết kế đến sát giới hạn tối đa**.

Hệ thống nên có giới hạn ứng dụng thấp hơn giới hạn kỹ thuật, ví dụ:

~~~text
Max items trong mảng nhúng: 100
Max độ sâu object từ input: 8
Max kích thước metadata tùy chỉnh: 16 KiB
Max kích thước request: theo API contract
~~~

Các số trên chỉ là **ví dụ chính sách ứng dụng**, không phải giới hạn mặc định của MongoDB/DynamoDB. Giới hạn thực phải phù hợp với truy vấn, tốc độ tăng trưởng và khả năng vận hành.

### 8.5. Tối đa một document/item không phải giới hạn duy nhất

Ngay cả khi document còn nhỏ hơn 16 MiB hoặc item nhỏ hơn 400 KB, một thao tác có thể vẫn bị giới hạn bởi:

- Kích thước request/response.
- Kích thước batch và số item trong batch.
- Dung lượng trang kết quả.
- Số biểu thức update, trường hoặc index được hỗ trợ.
- Timeout, CPU/IO, mạng và giới hạn tốc độ.
- Hot partition, khóa được cập nhật quá thường xuyên.

Do đó, **hợp lệ về kích thước không đồng nghĩa hiệu quả về hiệu năng**.

## 9. Độ sâu lồng nhau và số lượng field

### 9.1. Độ sâu lớn có thể làm code khó hiểu

Ví dụ:

~~~json
{
  "config": {
    "ui": {
      "dashboard": {
        "widgets": {
          "course": {
            "progress": {
              "display": {
                "format": "percent"
              }
            }
          }
        }
      }
    }
  }
}
~~~

Khi cấu trúc quá sâu:

- Validation nhiều tầng dễ bỏ sót.
- Update theo đường dẫn dài dễ sai.
- Mỗi thay đổi cấu trúc ảnh hưởng nhiều client.
- Dễ tạo object ở cấp sai hoặc thay thế nhầm cả subobject.
- Truy vấn và lập chỉ mục phụ thuộc giới hạn của database.

Thiết kế nên phản ánh cấu trúc nghiệp vụ thật, không lồng thêm cấp chỉ vì muốn tổ chức tên trường “đẹp”.

### 9.2. Trường mở rộng vô hạn gây bùng nổ schema

Một hệ quản lý sản phẩm cho phép mỗi client gửi:

~~~json
{
  "attributes": {
    "color": "black",
    "storageGb": 128,
    "vendor_random_field_001": "value",
    "vendor_random_field_002": "value"
  }
}
~~~

Trong cơ sở dữ liệu document, hàng nghìn tên trường khác nhau gây khó bảo trì schema, index và truy vấn. Trong search engine sử dụng dynamic mapping, mỗi field mới có thể tạo một field mapping mới, dẫn tới **mapping explosion** và chi phí bộ nhớ/metadata lớn.

Không nên hiểu rằng “không khai báo cột trước” nghĩa là **không cần giới hạn danh sách tên trường**.

### 9.3. Mẫu attributes động có kiểm soát

Có thể định nghĩa:

~~~json
{
  "category": "PHONE",
  "attributes": {
    "storageGb": 128,
    "screenSizeInches": 6.1,
    "hasEsim": true
  },
  "attributesSchemaVersion": 3
}
~~~

Ứng dụng dùng một registry:

| Category | Key được phép | Kiểu | Ràng buộc |
|---|---|---|---|
| PHONE | storageGb | integer | Trong danh sách dung lượng hợp lệ |
| PHONE | screenSizeInches | decimal | Số dương |
| PHONE | hasEsim | boolean | true/false |
| HEADPHONE | batteryHours | number | Không âm |
| HEADPHONE | wireless | boolean | true/false |

Các key ngoài registry có thể bị từ chối, chuyển vào nhóm extension ít rủi ro hoặc lưu sau khi được phê duyệt theo chính sách sản phẩm.

## 10. MongoDB: BSON document lồng nhau

### 10.1. BSON không hoàn toàn giống JSON

MongoDB lưu BSON, hỗ trợ những kiểu dữ liệu đặc thù như ObjectId, Date, Decimal128, binary và các kiểu số khác nhau. JSON trong ví dụ giao tiếp chỉ là cách diễn đạt gần gũi; driver có thể chuyển đổi giữa kiểu của ngôn ngữ lập trình và BSON.

Ví dụ:

~~~javascript
db.learners.insertOne({
  _id: "L001",
  displayName: "An",
  contact: {
    email: "an@example.test",
    address: {
      city: "Hồ Chí Minh",
      country: "VN"
    }
  },
  preferences: {
    language: "vi",
    notifications: { email: true, push: false }
  },
  enrolledCourses: [
    { courseId: "C101", progressPercent: 65 },
    { courseId: "C102", progressPercent: 100 }
  ],
  schemaVersion: 2
});
~~~

Nếu số khóa nhúng được giới hạn rõ ràng, document có thể thuận tiện. Nếu enrolledCourses tăng không giới hạn hoặc nhiều tiến trình cập nhật tiến độ liên tục, nên xem lại mô hình.

### 10.2. Truy vấn đường dẫn bằng dot notation

~~~javascript
db.learners.find(
  { "contact.address.city": "Hồ Chí Minh" },
  { displayName: 1, "contact.address.city": 1 }
);
~~~

Dot notation chỉ định đường dẫn của trường lồng nhau. Chỉ mục có thể được tạo theo một đường dẫn cụ thể:

~~~javascript
db.learners.createIndex({
  "contact.address.city": 1
});
~~~

Không nên lập chỉ mục mọi trường lồng nhau theo phản xạ; index tốn dung lượng và chi phí mỗi lần ghi.

### 10.3. Cập nhật một field lồng nhau

~~~javascript
db.learners.updateOne(
  { _id: "L001" },
  {
    $set: {
      "preferences.notifications.push": true
    }
  }
);
~~~

Ở đây, $set vào **đường dẫn cụ thể** thay đổi field con. Đối chiếu với:

~~~javascript
db.learners.updateOne(
  { _id: "L001" },
  {
    $set: {
      preferences: {
        notifications: { push: true }
      }
    }
  }
);
~~~

Lệnh thứ hai **thay cả object preferences**, có thể làm mất preferences.language và notifications.email. Đây là lỗi phổ biến khi cập nhật nested data: nhầm **patch một field** với **thay thế một object**.

### 10.4. Thêm phần tử vào mảng

~~~javascript
db.learners.updateOne(
  { _id: "L001" },
  {
    $push: {
      enrolledCourses: {
        courseId: "C103",
        progressPercent: 0
      }
    }
  }
);
~~~

$push có thể thêm nhiều phần tử nếu chạy lại cùng request. Nếu muốn “mỗi người chỉ có một enrollment hiện hành cho mỗi course”, không nên dựa vào $push mà không có cơ chế kiểm soát trùng.

$addToSet có thể tránh thêm **một giá trị mảng trùng hệt theo ngữ nghĩa so sánh của MongoDB**, nhưng điều đó **không đồng nghĩa unique theo một thuộc tính con** như courseId: hai object có cùng courseId nhưng progress khác có thể được coi là các giá trị khác.

Với yêu cầu unique nghiệp vụ, thường cần thiết kế enrollment thành collection riêng với compound unique index hoặc dùng update/điều kiện được thiết kế phù hợp.

### 10.5. Cập nhật phần tử mảng theo điều kiện

Ví dụ cập nhật tiến độ cho courseId C101:

~~~javascript
db.learners.updateOne(
  { _id: "L001" },
  {
    $set: {
      "enrolledCourses.$[course].progressPercent": 70
    }
  },
  {
    arrayFilters: [
      { "course.courseId": "C101" }
    ]
  }
);
~~~

arrayFilters cho phép chọn phần tử phù hợp trong mảng. Nếu mảng đã có **hai object cùng courseId**, nhiều phần tử có thể cùng được cập nhật; nó không phải cơ chế tự làm sạch dữ liệu trùng.

### 10.6. Atomicity và cập nhật đồng thời

MongoDB cung cấp tính nguyên tử cho thao tác ghi trên **một document** trong phạm vi hỗ trợ. Điều đó hữu ích nếu nhiều trường lồng nhau phải thay đổi cùng nhau.

Tuy nhiên, hai client đọc cùng bản cũ rồi cùng ghi đè một object lớn có thể gây lost update nếu không có điều kiện version hoặc toán tử update thích hợp.

Ví dụ một mô hình optimistic concurrency:

~~~javascript
const result = db.learners.updateOne(
  { _id: "L001", version: 7 },
  {
    $set: {
      "preferences.language": "en"
    },
    $inc: {
      version: 1
    }
  }
);
~~~

Ứng dụng cần kiểm tra matchedCount/modifiedCount theo hợp đồng API và xử lý trường hợp version đã đổi. Một thao tác nguyên tử trên document không tự ngăn việc ứng dụng ghi đè vô điều kiện từ dữ liệu đã đọc cũ.

## 11. MongoDB: truy vấn mảng lồng nhau và vấn đề khớp sai phần tử

### 11.1. Hai điều kiện có thể khớp hai phần tử khác nhau

Xét document:

~~~json
{
  "_id": "L001",
  "enrolledCourses": [
    { "courseId": "C101", "progressPercent": 100 },
    { "courseId": "C102", "progressPercent": 20 }
  ]
}
~~~

Ứng dụng muốn tìm người đang học **C101 và có progress dưới 50% trong chính C101**. Một filter viết không cẩn thận:

~~~javascript
db.learners.find({
  "enrolledCourses.courseId": "C101",
  "enrolledCourses.progressPercent": { $lt: 50 }
});
~~~

có thể khớp document này do **courseId C101 thuộc phần tử thứ nhất**, còn **progressPercent 20 thuộc phần tử thứ hai**. Như vậy không chứng minh rằng cùng một phần tử thỏa cả hai điều kiện.

### 11.2. Dùng $elemMatch để ràng buộc cùng một phần tử

~~~javascript
db.learners.find({
  enrolledCourses: {
    $elemMatch: {
      courseId: "C101",
      progressPercent: { $lt: 50 }
    }
  }
});
~~~

Với dữ liệu trên, truy vấn này không khớp L001 vì phần tử C101 có progress 100.

Đây là khác biệt quan trọng khi truy vấn array of objects. **Đường dẫn cùng tên mảng không tự ràng buộc mọi điều kiện vào cùng một phần tử**.

### 11.3. Multikey index

MongoDB có thể sử dụng **multikey index** cho trường mảng. Ví dụ:

~~~javascript
db.learners.createIndex({
  "enrolledCourses.courseId": 1
});
~~~

Việc index một mảng thường tạo các entry index liên quan đến những phần tử. Khi kết hợp nhiều đường dẫn từ mảng, cần hiểu giới hạn compound multikey index, tính năng $elemMatch và cách planner sử dụng điều kiện.

Không nên tạo compound index gồm nhiều mảng độc lập mà không xem xét giới hạn của MongoDB. Một compound multikey index có những hạn chế về nhiều array field trên cùng document; không phải mọi tổ hợp array đều hợp lệ hay hiệu quả.

### 11.4. Lập chỉ mục có giải quyết mảng tăng vô hạn không?

Không. Index giúp truy vấn hiệu quả hơn, nhưng **không biến một document chứa hàng triệu phần tử thành thiết kế có thể mở rộng vô hạn**. Số phần tử vẫn ảnh hưởng:

- Kích thước document.
- Kích thước và cập nhật index.
- Tải ghi lên document.
- Serialize/deserialize.
- Đường xóa và retention.

Nếu các enrollment cần truy vấn riêng theo learnerId và courseId, có thể tách thành collection Enrollment:

~~~javascript
db.enrollments.createIndex(
  { learnerId: 1, courseId: 1 },
  { unique: true }
);
~~~

Index này chỉ hợp lý nếu **nghiệp vụ cấm nhiều enrollment giữa cùng người và khóa** trong phạm vi collection. Nếu học lại nhiều kỳ là hợp lệ, identity cần thêm enrollmentId hoặc term, và unique constraint phải điều chỉnh.

## 12. DynamoDB: Map, List và Set trong item

### 12.1. Một item với nested Map/List

Ví dụ:

~~~json
{
  "PK": "LEARNER#L001",
  "SK": "PROFILE",
  "displayName": "An",
  "contact": {
    "city": "Hồ Chí Minh",
    "country": "VN"
  },
  "preferences": {
    "language": "vi",
    "notifications": {
      "email": true,
      "push": false
    }
  },
  "recentCourses": [
    {
      "courseId": "C101",
      "lastAccessedAt": "2026-11-14T08:40:00Z"
    }
  ]
}
~~~

Trong DynamoDB, Map và List là các **document data types**. String, Number, Binary, Boolean, Null và các tập String/Number/Binary Set có những quy tắc khác nhau; Map/List có thể chứa cấu trúc lồng nhau trong giới hạn được hỗ trợ.

**Kích thước item tối đa 400 KB** và **độ sâu Map/List tối đa 32 cấp** là hai ràng buộc cần thiết kế ngay từ đầu. Không nên dùng một item PROFILE để lưu toàn bộ lịch sử hoạt động của người học.

### 12.2. List khác Set

Một List có thứ tự và có thể chứa những giá trị lặp. Một DynamoDB Set biểu diễn tập giá trị không trùng thuộc loại string, number hoặc binary theo quy tắc dịch vụ; nó không phải tập Map tùy ý.

Ví dụ:

~~~text
List:
  ["C101", "C101", "C102"]  -> có phần tử trùng

String Set:
  {"C101", "C102"}          -> không chứa trùng
~~~

Nếu phải lưu nhiều lượt đăng ký cùng Course và có metadata mỗi lần, một set courseId sẽ làm mất thông tin. Nên thiết kế các item Enrollment riêng với khóa đầy đủ.

### 12.3. Cập nhật nested Map bằng UpdateExpression

Giả sử item đã có:

~~~json
{
  "PK": "LEARNER#L001",
  "SK": "PROFILE",
  "preferences": {
    "notifications": {
      "email": true,
      "push": false
    }
  },
  "version": 7
}
~~~

Ví dụ AWS SDK for JavaScript v3 với Document Client:

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  UpdateCommand
} from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: "ap-southeast-1" })
);

await client.send(new UpdateCommand({
  TableName: "LearningData",
  Key: {
    PK: "LEARNER#L001",
    SK: "PROFILE"
  },
  UpdateExpression:
    "SET #prefs.#notifications.#push = :enabled, #v = #v + :one",
  ConditionExpression:
    "attribute_exists(PK) AND #v = :expected",
  ExpressionAttributeNames: {
    "#prefs": "preferences",
    "#notifications": "notifications",
    "#push": "push",
    "#v": "version"
  },
  ExpressionAttributeValues: {
    ":enabled": true,
    ":one": 1,
    ":expected": 7
  }
}));
~~~

Lệnh này cập nhật đường dẫn lồng nhau **nếu các Map cha đã tồn tại** và version vẫn bằng 7. Nếu Map cha thiếu, cập nhật đường dẫn sâu có thể thất bại; ứng dụng cần khởi tạo Map cha hoặc dùng cách cập nhật khác theo schema.

ConditionExpression được đánh giá cùng thao tác ghi trên item, giúp ngăn một lần ghi dùng version cũ ghi đè trạng thái mới trong phạm vi thao tác DynamoDB hỗ trợ.

### 12.4. Ghi cả Map khác ghi một field

Ví dụ muốn chỉ đổi push từ false sang true:

~~~text
SET preferences.notifications.push = true
~~~

khác với:

~~~text
SET preferences = {"notifications": {"push": true}}
~~~

Cách thứ hai có thể thay thế **cả Map preferences** và mất language hoặc notifications.email. Tương tự MongoDB, việc cập nhật cả subobject có nguy cơ xóa các field không được client gửi kèm.

### 12.5. Không dùng List lớn làm lịch sử vô hạn

Giả sử mỗi lần học xong một bài lại thêm event vào List của item PROFILE. Sau nhiều năm, item có thể đạt 400 KB và mọi lần ghi đều tranh chấp trên cùng item.

Một mô hình khác:

~~~text
PK = LEARNER#L001, SK = PROFILE
PK = LEARNER#L001, SK = ACTIVITY#2026-11-14#E1001
PK = LEARNER#L001, SK = ACTIVITY#2026-11-14#E1002
~~~

Đây là nhiều item, mỗi item có khóa riêng, thay vì một item chứa List vô hạn. Có thể thêm time bucket hoặc một bảng khác nếu một partition key trở nên quá nóng hoặc truy vấn theo ngày cần hiệu quả hơn.

### 12.6. Điều kiện truy vấn với thuộc tính lồng nhau

DynamoDB có thể dùng một số biểu thức điều kiện và filter trên đường dẫn Map/List phù hợp. Tuy nhiên, **đường dẫn lồng nhau không tự trở thành một partition key hoặc GSI key**.

Nếu API cần Query hiệu quả theo city của mọi learner, có thể phải đưa city thành **thuộc tính scalar được lập chỉ mục** ở một mô hình đọc/secondary index phù hợp. Chỉ thêm contact.city vào Map không tự tạo đường Query hiệu quả từ city.

## 13. Cassandra/ScyllaDB: collection, tuple và user-defined type

### 13.1. Khác với document JSON tự do

Cassandra dùng schema bảng và CQL types. Nó hỗ trợ những kiểu collection như **list, set, map**, cũng như **tuple** và **user-defined type (UDT)** ở những phiên bản/tính năng tương ứng.

Ví dụ:

~~~sql
CREATE TABLE learner_settings (
    learner_id text PRIMARY KEY,
    language text,
    favorite_tags set<text>,
    ordered_topics list<text>,
    preferences map<text, text>
);
~~~

Ý nghĩa:

- favorite_tags: tập tag không trùng.
- ordered_topics: danh sách có thứ tự.
- preferences: Map với key và value cùng kiểu đã khai báo.

Không nên đọc ví dụ trên như “Cassandra lưu mọi JSON object bất kỳ”. Kiểu của từng collection được xác định trong schema.

### 13.2. UDT cho cấu trúc có tên trường

Ví dụ:

~~~sql
CREATE TYPE postal_address (
    country text,
    city text,
    line1 text
);

CREATE TABLE learner_profile (
    learner_id text PRIMARY KEY,
    display_name text,
    address frozen<postal_address>
);
~~~

UDT cho phép mô tả dữ liệu có cấu trúc, giúp một field address gồm những thành phần có tên. Việc dùng **frozen** có ảnh hưởng đến cách giá trị được lưu/cập nhật như một đơn vị; cơ chế và giới hạn của frozen/non-frozen UDT khác nhau theo phiên bản và tình huống.

### 13.3. Tại sao không dùng collection cực lớn?

Giả sử dùng:

~~~sql
CREATE TABLE learner_history (
    learner_id text PRIMARY KEY,
    events list<text>
);
~~~

Rồi đưa mọi sự kiện nhiều năm vào events. Những vấn đề:

- Giá trị collection có thể phát triển rất lớn.
- Mọi cập nhật tập trung vào một partition/hàng.
- Khó phân trang theo thời gian và truy vấn riêng từng event.
- Cập nhật/xóa phần tử và tombstone có thể gây chi phí.

Một mô hình thời gian:

~~~sql
CREATE TABLE activity_by_learner_day (
    learner_id text,
    activity_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
      (learner_id, activity_day),
      occurred_at,
      event_id
    )
) WITH CLUSTERING ORDER BY (
      occurred_at DESC,
      event_id ASC
);
~~~

Mỗi sự kiện là một hàng, được nhóm theo người/ngày và sắp theo thời gian. Thiết kế này phù hợp hơn cho truy vấn “20 hoạt động mới nhất trong ngày” so với một List khổng lồ.

### 13.4. Khả năng cập nhật collection không đồng nghĩa transaction rộng

CQL có thao tác cập nhật collection theo kiểu dữ liệu. Nhưng điều đó không tự đảm bảo một chuỗi thay đổi ở nhiều hàng/bảng khác nhau có ACID đầy đủ như một transaction quan hệ. Phải phân biệt atomicity của thao tác cụ thể, LWT/conditional update và consistency level của hệ đang dùng.

## 14. Redis: value dạng string và cấu trúc JSON tùy module

### 14.1. JSON có thể là một chuỗi

Một ứng dụng có thể lưu:

~~~redis
SET learner:L001 "{\"displayName\":\"An\",\"preferences\":{\"language\":\"vi\"}}"
GET learner:L001
~~~

Đây là **Redis string** có nội dung JSON đã serialize. Redis không tự hiểu từng trường con chỉ vì nội dung trông giống JSON; ứng dụng thường phải GET, parse, sửa rồi SET lại toàn bộ chuỗi nếu không dùng một tính năng bổ sung.

Hai client cùng GET rồi SET từ phiên bản cũ có thể gây **lost update**. Cần WATCH/MULTI, script hoặc mô hình cập nhật có điều kiện thích hợp nếu có tranh chấp.

### 14.2. RedisJSON là một tính năng riêng

Trong những môi trường cài **RedisJSON** hoặc biến thể Redis có chức năng tương ứng, có thể thao tác đường dẫn JSON bằng các lệnh như:

~~~redis
JSON.SET learner:L001 $ "{\"displayName\":\"An\",\"preferences\":{\"language\":\"vi\"}}"
JSON.GET learner:L001 $.preferences.language
JSON.SET learner:L001 $.preferences.language "\"en\""
~~~

Các lệnh JSON.* trên **không phải luôn có sẵn ở mọi triển khai Redis**; phải kiểm tra module/tính năng và phiên bản. Việc có đường dẫn JSON không làm mất các giới hạn về bộ nhớ, kích thước dữ liệu, persistence, replication hay thiết kế concurrency.

### 14.3. Dùng Redis Hash cho object phẳng

Một số dữ liệu phẳng có thể lưu bằng Hash:

~~~redis
HSET learner:L001 displayName "An" language "vi"
HGET learner:L001 language
HSET learner:L001 language "en"
~~~

Hash phù hợp với các cặp field–value đơn giản, nhưng không phải bản sao hoàn toàn của JSON nested object tùy ý. Khi cần lưu cấu trúc phức tạp, phải chọn cách serialize, mô hình nhiều key hoặc module phù hợp.

### 14.4. Không dùng một key để lưu dữ liệu không có giới hạn

Một Redis key chứa JSON/String cực lớn:

- Tốn bộ nhớ.
- Tăng độ trễ truyền/serialize.
- Có thể làm những thao tác đọc/ghi toàn bộ giá trị trở nên đắt.
- Gây áp lực replication/persistence và eviction.

Redis có các giới hạn cụ thể theo kiểu dữ liệu và cấu hình; nhưng giới hạn thấp hơn do **SLO hiệu năng và dung lượng RAM** thường mới là điều quyết định thiết kế.

## 15. Search engine và nguy cơ mapping explosion

### 15.1. Field động có thể biến thành rất nhiều field index

Giả sử sản phẩm có:

~~~json
{
  "productId": "P1001",
  "attributes": {
    "brand": "A",
    "batteryHours": 20,
    "vendorCustomName01": "x",
    "vendorCustomName02": "y"
  }
}
~~~

Nếu search engine tự động tạo mapping cho từng tên field mới, hàng nghìn vendor gửi hàng nghìn key khác nhau có thể làm metadata của index tăng rất lớn.

Đây là **mapping explosion**, khác với giới hạn kích thước của một document. Một document có thể nhỏ, nhưng tổng số tên field trên toàn index vẫn không kiểm soát được.

### 15.2. Object và nested query có thể có ngữ nghĩa khác nhau

Một mảng object:

~~~json
{
  "variants": [
    { "color": "red", "size": "M" },
    { "color": "blue", "size": "L" }
  ]
}
~~~

Truy vấn “có biến thể color = red và size = L trong **cùng một biến thể**” phải bảo toàn quan hệ giữa hai field của **một phần tử mảng**.

Trong Elasticsearch/OpenSearch, cách mapping object thông thường và kiểu **nested** có ngữ nghĩa truy vấn khác nhau. Với object array thông thường, query trên các field có thể tạo hiệu ứng khớp chéo phần tử; mapping/query nested có thể giữ ngữ nghĩa “cùng một object con” khi được thiết kế đúng.

Chọn nested có chi phí index và truy vấn riêng; không nên mặc định mọi mảng object cần được đánh index nested.

### 15.3. Trường mở rộng không có nghĩa index mọi thứ

Một số lựa chọn tùy sản phẩm:

- Registry cho các field được tìm kiếm/lọc thường xuyên.
- Giới hạn số field mapping và độ sâu.
- Dùng kiểu dữ liệu dành cho key–value linh hoạt (ví dụ flattened ở hệ hỗ trợ) khi không cần mọi tính năng truy vấn của nested field.
- Lưu phần metadata chỉ hiển thị ở nguồn thay vì đánh index.
- Chuyển các thuộc tính phổ biến thành những field chuẩn hóa.

**Nguồn dữ liệu nghiệp vụ** và **search index** có thể có schema khác nhau: nguồn chấp nhận một object attributes linh hoạt, còn search chỉ index một phần key được phê duyệt.

## 16. Schema linh hoạt vẫn cần validation

### 16.1. Validation ở nhiều tầng

Một hệ thống nên kiểm tra:

1. **API boundary:** Kiểu và kích thước payload từ client.
2. **Domain validation:** Quy tắc nghiệp vụ như phần trăm 0–100, qty dương, trạng thái hợp lệ.
3. **Database validation:** Những ràng buộc schema và thao tác mà database hỗ trợ.
4. **Projection validation:** Dữ liệu biến đổi trước khi ghi search/read model.

Không nên chỉ trông cậy vào front-end: client có thể là ứng dụng cũ, script hoặc request được gửi trực tiếp.

### 16.2. Ví dụ JSON Schema

Một schema đơn giản cho cấu hình người học:

~~~json
{
  "type": "object",
  "required": ["learnerId", "preferences"],
  "properties": {
    "learnerId": {
      "type": "string",
      "minLength": 1
    },
    "preferences": {
      "type": "object",
      "required": ["language"],
      "properties": {
        "language": {
          "type": "string",
          "enum": ["vi", "en"]
        },
        "notifications": {
          "type": "object",
          "properties": {
            "email": { "type": "boolean" },
            "push": { "type": "boolean" }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "extensions": {
      "type": "object",
      "maxProperties": 20
    }
  },
  "additionalProperties": false
}
~~~

Ví dụ sử dụng **JSON Schema thông thường** để thể hiện hợp đồng, không phải một bản khai báo nguyên xi mọi tùy chọn của MongoDB $jsonSchema. MongoDB có những khác biệt về keyword/kiểu BSON và cách validation hoạt động, cần áp dụng theo API thực tế.

Trong schema này:

- Trường lõi được kiểm soát chặt.
- preferences không cho thêm key tùy ý.
- extensions là vùng mở rộng có giới hạn số lượng field.

**Chỉ maxProperties chưa đủ:** Cần thêm giới hạn độ sâu, kích thước giá trị, loại key, tổng byte và quyền ghi từng extension.

### 16.3. Strict, permissive và extension bag

Có ba cách phổ biến:

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Strict schema | Dễ dự đoán và kiểm soát | Thêm field cần thay đổi hợp đồng |
| Permissive toàn bộ | Phát triển thử nghiệm nhanh | Dễ có dữ liệu sai kiểu, lỗi tên trường và mapping explosion |
| Lõi strict + extensions có giới hạn | Cân bằng ổn định và linh hoạt | Cần registry/policy cho trường mở rộng |

Với nghiệp vụ quan trọng, **lõi strict + vùng mở rộng có quy tắc** thường dễ quản trị hơn cho phép toàn bộ document hoàn toàn tự do.

## 17. Schema evolution: dữ liệu cũ và mới cùng tồn tại

### 17.1. Ví dụ thay đổi schema

Phiên bản 1:

~~~json
{
  "schemaVersion": 1,
  "learnerId": "L001",
  "fullName": "Nguyễn Văn An"
}
~~~

Phiên bản 2:

~~~json
{
  "schemaVersion": 2,
  "learnerId": "L001",
  "name": {
    "givenName": "An",
    "familyName": "Nguyễn Văn"
  }
}
~~~

Thay fullName string bằng object name là **thay đổi cấu trúc không tương thích trực tiếp**. Một client cũ đọc fullName có thể không biết dùng name.givenName và name.familyName.

### 17.2. Chiến lược expand–migrate–contract

Một quy trình an toàn thường gồm:

1. **Expand:** Bổ sung trường mới và code có thể đọc cả phiên bản cũ/mới.
2. **Dual-read hoặc dual-write có quy tắc:** Trong thời gian chuyển tiếp, phục vụ client cũ và mới theo hợp đồng rõ.
3. **Backfill:** Chuyển dữ liệu cũ sang cấu trúc mới theo từng batch, có checkpoint.
4. **Measure:** Theo dõi số document còn schema cũ, lỗi parse, truy vấn và index liên quan.
5. **Contract:** Chỉ bỏ trường cũ khi các client và dữ liệu cần thiết đã chuyển đổi.

Khi có nhiều service, cần xác định **thứ tự triển khai**: reader thường nên hỗ trợ cấu trúc mới trước khi writer bắt đầu chỉ ghi định dạng mới.

### 17.3. Version đặt ở đâu?

Tùy bài toán:

- schemaVersion ở document root cho định dạng của cả document.
- eventSchemaVersion cho sự kiện.
- attributesSchemaVersion cho nhóm extension theo category.
- version nghiệp vụ phục vụ optimistic concurrency.

Không nên dùng một con số version để thay thế tất cả khái niệm. **Schema version** nói về hình dạng dữ liệu, trong khi **entity version** nói về thứ tự cập nhật một thực thể.

### 17.4. Dữ liệu cũ có thể thiếu trường mới

Ví dụ reader:

~~~javascript
function getLanguage(learner) {
  const value = learner.preferences?.language;
  return typeof value === "string" ? value : "vi";
}
~~~

Đây là mẫu áp dụng giá trị mặc định khi trường chưa có hoặc không đúng kiểu theo hợp đồng. Trong code nghiệp vụ thật, việc gặp **kiểu sai** có thể phải báo lỗi hoặc đưa vào hàng xử lý dữ liệu hỏng thay vì âm thầm dùng mặc định.

### 17.5. Đổi cấu trúc có thể cần xây lại index/read model

Nếu trước kia API lọc trên fullName, nay dữ liệu dùng name.givenName và name.familyName, cần xem lại:

- Query condition.
- Index trên nested fields.
- Projection sang search.
- Serialize cho client cũ.
- Report/export.

Thêm một nested field không tự cập nhật tất cả đường đọc đã dựa vào schema trước đó.

## 18. Bảo mật với trường mở rộng và nested update

### 18.1. Tránh mass assignment

Một request từ người dùng:

~~~json
{
  "displayName": "An",
  "role": "ADMIN",
  "accountBalanceMinor": 999999999
}
~~~

Nếu server đưa mọi key client gửi vào database mà không kiểm tra quyền, người dùng có thể sửa các field không được phép. Schema linh hoạt **không phải quyền ghi tự do**.

Phải có danh sách field được cập nhật theo từng endpoint/role:

~~~text
PATCH /me/profile:
  được sửa: displayName, avatarUrl, preferences.language
  không được sửa: learnerId, role, balance, tenantId
~~~

### 18.2. Tránh field-path injection

Nếu API cho client gửi đường dẫn tùy ý:

~~~text
path = "permissions.isAdmin"
value = true
~~~

rồi thực hiện update động, có thể cho phép sửa field đặc quyền. Các tên key chứa ký tự điều khiển đường dẫn hoặc toán tử đặc biệt cũng cần được xử lý theo ngữ nghĩa database, không nối trực tiếp dữ liệu không tin cậy vào câu query.

Nên:

- Chỉ chấp nhận những đường dẫn được allowlist.
- Xác thực kiểu, độ sâu và kích thước.
- Escape hoặc ánh xạ key theo API an toàn.
- Không cho sửa field nhận diện hoặc quyền từ endpoint công khai.
- Ghi audit cho thay đổi nhạy cảm.

### 18.3. Tránh quá tải vì JSON quá sâu hoặc quá lớn

Input lồng nhiều cấp hoặc chứa hàng triệu phần tử có thể gây quá tải:

- Parse JSON dùng CPU/bộ nhớ lớn.
- Validation đệ quy tốn thời gian.
- Serialize response lớn.
- Tạo quá nhiều field index.
- Ghi document vượt giới hạn và tạo nhiều retry thất bại.

API nên đặt **giới hạn request bytes, depth, count, string length**, đồng thời trả lỗi cụ thể cho payload không hợp lệ trước khi đưa vào database.

### 18.4. Giảm dữ liệu nhạy cảm trong object động

Một trường extensions có thể vô tình chứa email, token, số điện thoại hoặc thông tin thanh toán. Nếu extensions được nhân sang search/read model hoặc log, phạm vi rò rỉ mở rộng.

Nên có danh mục key được phép, chính sách che dữ liệu, retention, quyền đọc/ghi và quy trình xóa thông tin cá nhân trên mọi bản sao.

## 19. Vấn đề cập nhật và độ trễ khi document lớn

### 19.1. Một thao tác nhỏ không luôn có chi phí nhỏ

Giả sử document chứa 10.000 phần tử trong nested array. Thêm một phần tử có thể làm:

- Tăng kích thước document.
- Thay đổi nhiều entry index.
- Gây tranh chấp khi nhiều client cập nhật cùng document.
- Tăng chi phí đọc hoặc truyền khi API lấy cả document.
- Khó phân trang, lọc hoặc xóa một phần lịch sử.

Cách lưu trữ nội bộ có thể tối ưu một số thao tác, nhưng thiết kế vẫn phải xem **kích thước, tốc độ tăng và độ đồng thời**, không chỉ nhìn cú pháp update một trường.

### 19.2. Hot document/item

Một document Course chứa một mảng progress của 100.000 người học. Khi mỗi học viên hoàn thành bài, nhiều worker cùng ghi lên **một document Course**, tạo điểm tranh chấp.

Phương án tốt hơn:

~~~text
Course C101:
  metadata, chapter summaries

Progress:
  key = (learnerId, courseId)
  completedLessons, version
~~~

Mỗi tiến độ được cập nhật theo khóa riêng. Nếu dashboard cần thống kê tổng số người hoàn thành, có thể duy trì aggregate/read model với quy tắc idempotency riêng.

### 19.3. Chia bucket khi dữ liệu là chuỗi thời gian

Lịch sử hoạt động nên được phân theo người/ngày hoặc thiết bị/giờ nếu phù hợp:

~~~text
activity:L001:2026-11-14
activity:L001:2026-11-15
~~~

Trong Cassandra, partition key có thể chứa learnerId và activityDay. Trong DynamoDB, có thể dùng nhiều item với sort key theo thời gian; trong MongoDB, dùng document riêng được index theo learnerId + occurredAt.

**Không có bucket phù hợp cho tất cả hệ thống.** Bucket nhỏ giảm kích thước phân vùng nhưng tăng số partition phải truy vấn và ghép khi xem lịch sử dài.

### 19.4. Giao thức API có thể có giới hạn nhỏ hơn database

Ngay cả khi MongoDB cho phép document 16 MiB, API HTTP có thể chỉ cho payload 1 MiB. Việc đọc một document 8 MiB để lấy ba field là tốn mạng. Tối ưu schema còn phải phù hợp:

- Hạn mức request/response của gateway.
- Giao diện phân trang.
- Thời gian serialize/deserialize.
- Giới hạn bộ nhớ của mobile/browser.
- Cache và CDN.

Giới hạn document của database **không phải mục tiêu kích thước response**.

## 20. Mô hình thiết kế thực tế: đơn hàng và line items

### 20.1. Trường hợp đơn hàng ít dòng

Một đơn hàng bán lẻ thông thường có vài line item, cần xem chi tiết đơn cùng giá chốt:

~~~json
{
  "orderId": "O1001",
  "customerId": "C17",
  "status": "PAID",
  "currency": "VND",
  "lines": [
    {
      "lineId": "L1",
      "sku": "SKU-42",
      "qty": 2,
      "unitPriceMinor": 1590000
    },
    {
      "lineId": "L2",
      "sku": "SKU-99",
      "qty": 1,
      "unitPriceMinor": 500000
    }
  ],
  "totalMinor": 3680000,
  "schemaVersion": 2
}
~~~

Nhúng lines có thể hợp lý nếu số line được giới hạn và cần được đọc cùng đơn. **Giá chốt** được lưu trong từng line để lịch sử đơn không phụ thuộc vào giá catalog có thể thay đổi sau này.

### 20.2. Trường hợp đơn hàng có lượng dòng cực lớn

Một đơn xuất hàng doanh nghiệp có 50.000 line item, mỗi item có hàng chục thuộc tính và nhiều lần điều chỉnh. Nhúng tất cả vào một document sẽ gây rủi ro kích thước và cập nhật.

Mô hình thay thế:

~~~text
Order:
  orderId, customerId, status, totals, version

OrderLine:
  key = (orderId, lineId)
  sku, qty, unitPriceMinor, attributes
~~~

API chi tiết có thể phân trang OrderLine và lấy aggregate tổng. Nếu cần kiểm soát invariant “tổng tiền đúng bằng tổng các line”, phải xác định cách commit/đối soát theo phạm vi giao dịch, không mặc định việc tách item vẫn giữ nguyên atomicity ban đầu.

### 20.3. Nested custom attributes theo loại sản phẩm

Các line khác loại có attributes khác nhau:

~~~json
{
  "lineId": "L3",
  "sku": "PHONE-128",
  "attributes": {
    "storageGb": 128,
    "color": "black"
  }
}
~~~

Với dữ liệu nghiệp vụ quan trọng, cần lưu cả **snapshot giá trị thuộc tính tại thời điểm mua** nếu chính sách yêu cầu. Không phải mọi custom attribute đều nên cập nhật theo catalog hiện tại.

## 21. Checklist thiết kế kiểu lồng nhau và trường mở rộng

Khi chuẩn bị một schema, hãy đặt các câu hỏi:

| Câu hỏi | Quyết định liên quan |
|---|---|
| Một trường con có bao nhiêu phần tử ở mức tối đa? | Nhúng hay tách item riêng |
| Dữ liệu con có được đọc cùng cha thường xuyên không? | Tối ưu đường đọc |
| Cùng lúc bao nhiêu tác nhân cập nhật nó? | Ranh giới atomicity và hot document |
| Mỗi nhóm đối tượng có những field mở rộng gì? | Registry/validation và schema version |
| Các field động có cần filter/index không? | Thiết kế index, tránh mapping explosion |
| Thiếu, null và rỗng khác nhau thế nào? | Hợp đồng API và migration |
| Cần kiểu số chính xác đến mức nào? | Decimal/integer, serialize |
| Kích thước đo theo byte hay ký tự? | Giới hạn database và API |
| Dữ liệu có tăng mãi không? | Time bucket, phân trang, tách lịch sử |
| Có cần xóa/ẩn một phần theo retention khác nhau không? | Tách dữ liệu và quyền |
| Schema cũ có thể tồn tại bao lâu? | Expand–migrate–contract |
| Nếu cập nhật field lồng nhau bị retry thì sao? | Idempotency/version/CAS |
| Có cách đo kích thước và phát cảnh báo sớm không? | Vận hành và SLO |

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nhúng lịch sử không giới hạn vào một document | Vượt kích thước, document nóng | Tách bản ghi, chia theo khóa hoặc thời gian |
| Cho mọi client tự thêm field tùy ý | Schema không kiểm soát, lỗi bảo mật | Lõi strict + extensions có giới hạn |
| Đếm ký tự để suy kích thước BSON/item | Sai giới hạn bytes | Đo serialize theo định dạng lưu |
| Nhầm thiếu field với null | Sai logic mặc định/truy vấn | Định nghĩa rõ missing/null/empty |
| Đặt số tiền dưới dạng floating-point tùy ý | Rủi ro sai số | Dùng integer minor units hoặc decimal phù hợp |
| Ghi cả nested Map khi chỉ sửa một field | Mất field khác | Update đường dẫn hoặc merge có kiểm soát |
| Dùng $push và tin rằng không có trùng | Thêm duplicate khi retry | Unique ID và điều kiện nghiệp vụ |
| Dùng $addToSet và tin rằng unique theo courseId | Hai object cùng ID khác thuộc tính vẫn tồn tại | Collection riêng/unique key hoặc logic đúng |
| Truy vấn nhiều điều kiện trên array nhưng không gắn cùng phần tử | Khớp chéo phần tử | Dùng $elemMatch/nested query phù hợp |
| Đánh index mọi nested field | Tăng chi phí ghi, mapping explosion | Chỉ index access pattern |
| Cho schema cũ và mới dùng một cách diễn giải ngầm | Client đọc sai | schemaVersion, migration và reader tương thích |
| Dùng một version cho mọi nguồn field | Event cũ ghi đè nhóm field mới | Version riêng hoặc projection nguyên khối có hợp đồng |
| Không kiểm tra depth và size ở API | Payload quá lớn gây lỗi, quá tải | Limits trước khi ghi |
| Lưu binary lớn inline không cần thiết | Document lớn, tốn mạng | Object storage + metadata |
| Cho client ghi đường dẫn nested bất kỳ | Mass assignment/field injection | Allowlist và quyền ghi theo trường |
| Tin một item nhỏ hơn max size thì truy vấn sẽ nhanh | Hot key, fan-out, index nặng | Đo p95/p99, payload, partition |
| Không có cách backfill schema mới | Dữ liệu cũ tồn tại vô hạn | Expand–migrate–contract và đối soát |

## 23. Bài tập thực hành

### Bài 1. Phân loại kiểu dữ liệu

Cho document:

~~~json
{
  "userId": "U17",
  "age": 25,
  "verified": true,
  "address": {
    "city": "Đà Nẵng",
    "geo": {"lat": 16.05, "lon": 108.2}
  },
  "interests": ["database", "nosql"],
  "preferredChannels": null
}
~~~

Hãy chỉ ra trường nào là scalar, object, nested object, array và null. Sau đó trả lời: nếu preferredChannels bị **thiếu hoàn toàn**, có thể coi tương đương null không? Cần hợp đồng gì để ứng dụng xử lý nhất quán?

### Bài 2. Giải thích lỗi cập nhật nested object

Ban đầu:

~~~json
{
  "preferences": {
    "language": "vi",
    "notifications": {
      "email": true,
      "push": false
    }
  }
}
~~~

Một worker dùng MongoDB $set để gán:

~~~json
{
  "preferences": {
    "notifications": {
      "push": true
    }
  }
}
~~~

Hãy giải thích field nào có thể bị mất và viết lại ý tưởng update chỉ đường dẫn preferences.notifications.push.

**Gợi ý:** Cần phân biệt thay cả object với sửa đúng field con.

### Bài 3. Tìm lỗi query array

Cho:

~~~json
{
  "enrolledCourses": [
    {"courseId": "C101", "progressPercent": 100},
    {"courseId": "C102", "progressPercent": 20}
  ]
}
~~~

Yêu cầu: “Người học có **C101** với tiến độ **dưới 50%**.”

1. Vì sao hai điều kiện dot path riêng trên enrolledCourses có thể trả kết quả sai?
2. Viết filter MongoDB dùng $elemMatch.
3. Nếu hệ search dùng object array, cần đánh giá kiểu mapping/query nào để bảo đảm điều kiện cùng phần tử?

### Bài 4. Tính kích thước và đề xuất chia dữ liệu

Một thiết bị phát 3.000 sự kiện/giây, mỗi sự kiện trung bình 200 byte dữ liệu ứng dụng.

1. Tính số sự kiện trong một giờ.
2. Ước lượng byte thô trong một giờ.
3. Có hợp lý khi nhúng toàn bộ sự kiện một giờ vào một MongoDB document hoặc DynamoDB item không?
4. Thiết kế nhiều item/document theo deviceId và time bucket, nêu ảnh hưởng đến truy vấn “100 sự kiện mới nhất”.

**Gợi ý:**

\[
3.000 \times 3.600 = 10.800.000\ \text{sự kiện/giờ}
\]

\[
10.800.000 \times 200 = 2.160.000.000\ \text{byte}
\]

Đây là dung lượng thô khoảng 2,16 GB, vượt xa giới hạn một document/item được đề cập trong bài.

### Bài 5. Thiết kế trường mở rộng

Một catalog có hai category PHONE và HEADPHONE. Những field mở rộng là:

~~~text
PHONE:
  storageGb, screenSizeInches, hasEsim

HEADPHONE:
  wireless, batteryHours, noiseCancelling
~~~

Hãy:

1. Xác định field lõi chung và vùng attributes.
2. Định nghĩa kiểu và validation cho từng category.
3. Quy định giới hạn tổng field, độ sâu và byte.
4. Chọn field nào cần đánh index cho truy vấn thực tế.
5. Giải thích cách tránh mapping explosion nếu nhà bán hàng gửi nhiều key tùy ý.

### Bài 6. Tiến hóa schema

Phiên bản 1 dùng:

~~~json
{
  "schemaVersion": 1,
  "fullName": "Nguyễn Văn An"
}
~~~

Phiên bản 2 dùng:

~~~json
{
  "schemaVersion": 2,
  "name": {
    "givenName": "An",
    "familyName": "Nguyễn Văn"
  }
}
~~~

Hãy lập kế hoạch expand–migrate–contract sao cho client cũ và mới không bị lỗi trong thời gian chuyển đổi. Nêu cách đo số document phiên bản 1 còn tồn tại, cách backfill, và những index/read model cần đổi.

### Bài 7. Bảo vệ update từ client

Một API PATCH /me/profile nhận object tùy ý. Client gửi:

~~~json
{
  "displayName": "An",
  "permissions": {
    "isAdmin": true
  },
  "preferences": {
    "language": "en"
  }
}
~~~

Hãy xác định field nào được sửa, field nào phải bị từ chối và cách cập nhật đúng đường dẫn để không mất những cấu hình khác. Giải thích vì sao schema linh hoạt và nested object không đồng nghĩa cho phép mass assignment.

### Bài 8. Tách quan hệ học tập khỏi document Learner

Một Learner có 200.000 Enrollment và mỗi Enrollment chứa 3 KB thông tin. Màn hình thường dùng:

- 20 khóa học gần nhất.
- Tiến độ của một khóa cụ thể.
- Báo cáo tổng số khóa hoàn thành.

Hãy đề xuất:

1. Document Learner nên giữ thông tin gì?
2. Collection/bảng Enrollment có khóa chính và index nào?
3. Read model/tổng hợp nào giúp màn hình nhanh?
4. Cách chống duplicate enrollment và cập nhật tiến độ đồng thời?
5. Vì sao không nên nhúng cả 200.000 Enrollment vào Learner dù document database hỗ trợ array?

## 24. Tổng kết

NoSQL có thể hỗ trợ **kiểu dữ liệu lồng nhau** như object, map, array/list, set và các cấu trúc đặc thù. **Trường mở rộng** giúp cùng một hệ thống lưu nhiều biến thể dữ liệu mà không phải thêm cột cố định cho mọi thuộc tính. Nhưng độ linh hoạt đó không loại bỏ yêu cầu về schema, tính đúng đắn hoặc hiệu năng.

Các nguyên tắc cốt lõi:

1. **Nhúng dữ liệu nhỏ, có giới hạn, thường đọc cùng nhau**; tách dữ liệu tăng vô hạn, cần truy vấn độc lập hoặc có tải ghi cao.
2. **Định nghĩa rõ kiểu và ý nghĩa field:** missing khác null, array khác set, chuỗi ID khác số dùng để tính.
3. **Đo kích thước theo định dạng lưu thực tế**, không chỉ đếm ký tự JSON. MongoDB có giới hạn BSON document 16 MiB; DynamoDB có giới hạn item 400 KB; các hệ khác có giới hạn riêng.
4. **Cập nhật nested field đúng phạm vi** để không vô tình thay thế cả subobject hoặc ghi đè dữ liệu đồng thời.
5. **Truy vấn và lập chỉ mục array/object phải giữ đúng quan hệ phần tử**; dùng các công cụ như $elemMatch hoặc nested query khi cần.
6. **Trường động vẫn cần registry/validation, giới hạn độ sâu và số field**, đặc biệt khi dữ liệu được đưa sang search index.
7. **Schema phải tiến hóa có kế hoạch:** schemaVersion, reader tương thích, backfill, thay index và đo dữ liệu cũ.
8. **Bảo vệ dữ liệu ở API và database:** giới hạn payload, quyền ghi theo field, tránh mass assignment, theo dõi kích thước và có đường sửa sai.

Câu hỏi cuối cùng không phải “Database có lưu được JSON lồng nhau không?” mà là **“Cấu trúc này sẽ phát triển tới đâu, được đọc/ghi như thế nào, cần ràng buộc gì và còn an toàn khi dữ liệu tăng lên gấp hàng nghìn lần hay không?”**
