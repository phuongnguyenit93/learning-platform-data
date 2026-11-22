# Chuỗi, Unicode, enum và quy ước giá trị lưu

## 1. Vì sao kiểu chuỗi và quy ước lưu quan trọng?

Trong ứng dụng dùng **Spring Data MongoDB**, một trường trông đơn giản như tên khách hàng hoặc trạng thái đơn hàng có thể gây lỗi lâu dài nếu không thống nhất cách lưu:

- Tên **“Tiếng Việt”** có thể được biểu diễn bằng nhiều chuỗi mã Unicode khác nhau, dù hiển thị gần như giống hệt.
- So sánh `"PAID"` với `"paid"`, hoặc tìm tên có dấu và không dấu, phụ thuộc quy tắc chuẩn hóa và collation.
- Đổi tên một hằng số `enum` trong Java có thể làm document cũ không đọc được nếu ứng dụng lưu trực tiếp tên hằng số.
- Đặt tên BSON field thiếu nhất quán, lúc dùng `customerName`, lúc dùng `customer_name`, khiến truy vấn, index và aggregation không tìm thấy dữ liệu mong muốn.
- Cùng ý nghĩa “chưa có trạng thái” nhưng lưu `null`, chuỗi rỗng, một mã `"unknown"` hay không có trường sẽ tạo ra bốn cách xử lý khác nhau.

Đây là bài thuộc chương **Kiểu dữ liệu** của module **SPRING_DATA_MONGODB**. Mục tiêu là sử dụng Spring Data MongoDB để **ánh xạ chính xác chuỗi và enum giữa Java và BSON**, đặt quy ước giá trị bền vững, thực hành với repository/`MongoTemplate`, kiểm tra document thực tế, rồi kết nối các quyết định đó với truy vấn, index, aggregation, transaction, reactive access và kiểm thử hiệu năng.

**Nguyên tắc xuyên suốt:** trước khi chọn annotation hoặc viết query, hãy xác định *giá trị nào được lưu*, *cách so sánh giá trị*, *cách xử lý phiên bản cũ* và *quy tắc nào có hiệu lực đối với toàn bộ ứng dụng*.

## 2. BSON string và Java String

### 2.1. MongoDB lưu chuỗi như thế nào?

MongoDB lưu document dưới dạng BSON; **BSON string** chứa dữ liệu văn bản mã hóa bằng UTF-8. Java `String` biểu diễn chuỗi bằng các đơn vị mã UTF-16, nên độ dài hay vị trí ký tự trong Java không đồng nhất với số byte lưu trong MongoDB.

Ví dụ chạy trong `mongosh` trên database kiểm thử:

```javascript
db.string_examples.insertOne({
  _id: "sample-01",
  customer_name: "Đặng Thị Ánh",
  nickname: "Ánh 😊",
  status_code: "paid",
  notes: "",
  optional_note: null
});

db.string_examples.findOne({ _id: "sample-01" });
```

Dữ liệu mẫu có các điểm cần phân biệt:

| Field | Ví dụ | BSON type | Ý nghĩa |
| --- | --- | --- | --- |
| `customer_name` | `"Đặng Thị Ánh"` | `string` | Chuỗi tiếng Việt có dấu |
| `nickname` | `"Ánh 😊"` | `string` | Chuỗi có ký tự ngoài Basic Multilingual Plane |
| `status_code` | `"paid"` | `string` | Mã trạng thái được định nghĩa theo quy ước |
| `notes` | `""` | `string` | Chuỗi rỗng, *không phải* `null` |
| `optional_note` | `null` | `null` | Có field, nhưng giá trị không xác định |
| `field_not_present` | Không có | `missing` khi kiểm tra bằng aggregation `$type` | Field vắng mặt |

Không nên dựa vào hiển thị JSON bình thường để kết luận về kiểu. Dùng `$type` hoặc Extended JSON để kiểm tra dữ liệu BSON thật:

```javascript
db.string_examples.aggregate([
  { $match: { _id: "sample-01" } },
  {
    $project: {
      _id: 0,
      nameType: { $type: "$customer_name" },
      notesType: { $type: "$notes" },
      optionalNoteType: { $type: "$optional_note" },
      absentType: { $type: "$field_not_present" }
    }
  }
]);
```

Kết quả mong đợi: `nameType` và `notesType` đều là `"string"`, `optionalNoteType` là `"null"`, còn `absentType` là `"missing"`.

### 2.2. Không có một khái niệm “độ dài ký tự” duy nhất

Với chữ có dấu và emoji, cần phân biệt:

- **UTF-8 bytes:** dung lượng chuỗi mã hóa để lưu và truyền.
- **UTF-16 code units:** giá trị `String.length()` trong Java.
- **Unicode code points:** giá trị `String.codePointCount(...)`; một emoji có thể chiếm một hoặc nhiều code point.
- **Grapheme clusters:** ký tự người dùng cảm nhận được; một ký tự hiển thị có thể gồm nhiều code point, ví dụ chữ + dấu kết hợp hoặc emoji dùng zero-width joiner.

Ví dụ Java:

```java
String text = "A😊";

System.out.println(text.length());                 // 3 UTF-16 code units
System.out.println(text.codePointCount(
    0, text.length()));                            // 2 code points
System.out.println(text.getBytes(
    java.nio.charset.StandardCharsets.UTF_8).length); // 5 bytes
```

Với MongoDB, `$strLenBytes` đếm số byte UTF-8, còn `$strLenCP` đếm Unicode code points:

```javascript
db.string_examples.aggregate([
  {
    $project: {
      customer_name: 1,
      utf8Bytes: { $strLenBytes: "$customer_name" },
      codePoints: { $strLenCP: "$customer_name" }
    }
  }
]);
```

Các biểu thức độ dài trên đòi hỏi đầu vào là chuỗi hợp lệ; với document thiếu trường hoặc `null`, cần xử lý điều kiện trước khi gọi. Nếu UI giới hạn “50 ký tự người dùng nhìn thấy”, chỉ giới hạn bằng `String.length()` hay `$strLenCP` có thể chưa đáp ứng quy tắc; hãy chọn định nghĩa độ dài phù hợp với mục đích và kiểm thử trường hợp dấu kết hợp/emoji.

### 2.3. Khác biệt giữa chuỗi UTF-8 và Unicode đã chuẩn hóa

Unicode cho phép biểu diễn cùng một ký tự có dấu theo các cách khác nhau. Ví dụ, ký tự **é** có thể tồn tại dưới dạng:

- Một code point được dựng sẵn: `U+00E9`.
- Hai code point: `U+0065` (e) + `U+0301` (dấu sắc kết hợp).

Về mặt hiển thị, hai chuỗi có thể rất giống nhau, nhưng chuỗi byte và phép so sánh đơn giản có thể khác. Tiếng Việt có nhiều ký tự kết hợp dấu nên vấn đề đáng chú ý hơn khi nhập từ nhiều nguồn, sao chép từ trình duyệt hoặc đồng bộ giữa hệ thống.

Sử dụng Java để quan sát:

```java
import java.text.Normalizer;

String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false

String nfc = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC
);
System.out.println(composed.equals(nfc));        // true
```

**NFC (Normalization Form C)** thường phù hợp khi muốn lưu văn bản hiển thị theo một biểu diễn nhất quán. **NFD** tách ký tự và dấu kết hợp; **NFKC/NFKD** còn thực hiện một số biến đổi tương thích, vì vậy không nên dùng một cách vô điều kiện khi sự khác biệt hình thức có giá trị nghiệp vụ.

Một số chuỗi như khóa truy cập, chữ ký số, mật khẩu, mã tham chiếu bên ngoài hoặc nội dung pháp lý có thể yêu cầu giữ nguyên từng đơn vị dữ liệu. **Chuẩn hóa phải theo hợp đồng từng field**: không tự áp dụng một quy tắc cho mọi chuỗi.

## 3. Chọn quy ước cho dữ liệu văn bản

### 3.1. Phân biệt văn bản hiển thị, mã định danh và khóa tìm kiếm

Ba loại chuỗi sau có yêu cầu khác nhau:

| Loại giá trị | Ví dụ | Quy tắc nên xác định |
| --- | --- | --- |
| Văn bản hiển thị | `customer_name = "Đặng Thị Ánh"` | Giữ dấu và cách viết người dùng; có thể áp dụng NFC nếu hợp đồng cho phép |
| Mã định danh/mã nghiệp vụ | `order_code = "ORD-2026-0001"` | Định dạng, tập ký tự, chữ hoa/thường, tính duy nhất và khả năng thay đổi |
| Khóa tìm kiếm bổ trợ | `customer_name_key = "đặng thị ánh"` | Sinh theo quy tắc cố định; chỉ phục vụ lọc/tìm kiếm, không thay bản hiển thị |
| Enum code | `status_code = "paid"` | Một mã ổn định, có tập giá trị hợp lệ |
| Dữ liệu nguyên bản | Nội dung do hệ thống thứ ba ký số hoặc phát hành | Không tự sửa, chuẩn hóa hay loại bỏ ký tự nếu sẽ phá tính toàn vẹn |

Không nên dùng `customer_name_key` để in tên khách hàng trên hóa đơn. Tên gốc được bảo tồn cho hiển thị; khóa tìm kiếm có thể đổi theo chiến lược tìm kiếm.

### 3.2. Chuẩn hóa có kiểm soát tại biên ghi dữ liệu

Ví dụ hàm Java xây dựng khóa tìm kiếm từ một tên người dùng. Quy tắc đơn giản: bỏ khoảng trắng Unicode ở đầu/cuối theo `strip()`, chuẩn hóa NFC, đổi chữ thường theo `Locale.ROOT`. Không xóa dấu hay thay đổi các khoảng trắng bên trong vì điều đó cần quyết định nghiệp vụ riêng:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public final class NameText {
    private NameText() {}

    public static String displayName(String input) {
        Objects.requireNonNull(input, "customer name is required");

        String value = Normalizer.normalize(
            input.strip(), Normalizer.Form.NFC
        );

        if (value.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng rỗng");
        }
        return value;
    }

    public static String searchKey(String displayName) {
        return Normalizer.normalize(
            displayName, Normalizer.Form.NFC
        ).toLowerCase(Locale.ROOT);
    }
}
```

`strip()` xử lý whitespace theo cách Java xác định Unicode whitespace, không có nghĩa là loại bỏ mọi ký tự vô hình, zero-width space hoặc mọi kiểu khoảng trắng trên thế giới. `Locale.ROOT` tạo phép chuyển chữ thường ổn định và không phụ thuộc locale của máy chạy; nó **không tương đương** phép so sánh theo ngôn ngữ tự nhiên hoặc Unicode case folding toàn diện. Nếu cần tìm kiếm tiếng Việt theo ngữ nghĩa cụ thể, hãy thử **collation** hoặc hệ tìm kiếm chuyên dụng.

**Với mã nghiệp vụ:** cần chính sách riêng. Chẳng hạn, mã voucher có phân biệt chữ hoa/thường hay không? Nếu không, có thể tạo mã canonical một lần bằng quy tắc đã công bố. Nhưng không tự viết hoa tất cả SKU, token hay mã do đối tác cấp; một số hệ thống coi `"AbC"` và `"abc"` là hai giá trị khác nhau.

### 3.3. Lưu cả bản hiển thị và khóa tìm kiếm khi cần

Một document khách hàng có thể mang cả hai:

```javascript
db.customers.insertOne({
  _id: "customer-01",
  display_name: "Đặng Thị Ánh",
  display_name_key: "đặng thị ánh",
  preferred_locale: "vi"
});
```

Ở đây `display_name_key` là dữ liệu **dẫn xuất**. Ứng dụng phải sinh lại nó **trong cùng thao tác cập nhật** khi tên hiển thị thay đổi; nếu cập nhật hai field bằng hai thao tác riêng, dữ liệu có thể lệch khi một thao tác lỗi.

```javascript
db.customers.updateOne(
  { _id: "customer-01" },
  {
    $set: {
      display_name: "Đặng Thị Ánh Nguyễn",
      display_name_key: "đặng thị ánh nguyễn"
    }
  }
);
```

Một `updateOne` trên một document có tính nguyên tử. Nếu muốn đồng bộ mã tìm kiếm từ nhiều luồng ghi, nên gom logic ở một service chung hoặc dùng biện pháp bảo vệ bổ sung; MongoDB không tự biết khóa dẫn xuất được sinh theo quy tắc Java nào.

## 4. So sánh chuỗi: equality, collation và tìm kiếm

### 4.1. So sánh trực tiếp không giống tìm kiếm theo ngôn ngữ

Nếu không cấu hình collation khác, MongoDB sử dụng **simple binary comparison**. Bởi vậy, các giá trị khác chữ hoa/thường hay khác cách mã hóa Unicode có thể không được xem là bằng nhau:

```javascript
db.customers.find({ display_name: "Đặng Thị Ánh" });

// Khác chữ thường/chữ hoa:
db.customers.find({ display_name: "đặng thị ánh" });
```

Không nên suy ra rằng MongoDB sẽ tự bỏ dấu tiếng Việt hoặc tự tìm chuỗi gần đúng. Cần định nghĩa rõ sản phẩm muốn:

- **Exact match:** đúng chuỗi đã lưu theo quy ước chuẩn hóa.
- **Case-insensitive match:** bỏ khác biệt chữ hoa/thường.
- **Accent-insensitive match:** có bỏ dấu hay không; với tiếng Việt, nhiều trường hợp bỏ dấu làm mất phân biệt tên khác nhau.
- **Prefix/full-text/fuzzy search:** yêu cầu tìm kiếm mở rộng, cần thiết kế riêng.

### 4.2. Collation của MongoDB

MongoDB cung cấp **collation** để so sánh/sắp xếp chuỗi theo quy tắc locale và mức độ phân biệt. Ví dụ với tiếng Việt:

```javascript
db.customers.find({ display_name: "đặng thị ánh" })
  .collation({ locale: "vi", strength: 2 });
```

Ở mức `strength: 2`, collation thường bỏ khác biệt chữ hoa/thường nhưng vẫn xét khác biệt dấu (nếu không có lựa chọn khác làm thay đổi hành vi). Mức `strength: 1` thường bỏ cả khác biệt dấu ở phép so sánh chính; hãy kiểm thử các cặp từ tiếng Việt cụ thể trước khi dùng để gộp giá trị hay enforce unique.

**Collation không thay thế cho quy tắc chuẩn hóa dữ liệu đầu vào.** Hãy kiểm chứng hành vi thực tế đối với NFC/NFD, dấu, chữ `đ`, khoảng trắng và các trường hợp người dùng thường nhập. Không có một thiết lập collation phù hợp cho mọi loại tên, địa chỉ, SKU và mã nghiệp vụ.

### 4.3. Index phải phù hợp với collation của truy vấn

Nếu thường xuyên tra cứu tên không phân biệt hoa/thường, có thể tạo index với cùng collation trên database kiểm thử:

```javascript
db.customers.createIndex(
  { display_name: 1 },
  { collation: { locale: "vi", strength: 2 } }
);

db.customers.find({ display_name: "đặng thị ánh" })
  .collation({ locale: "vi", strength: 2 })
  .explain("executionStats");
```

Truy vấn muốn sử dụng index theo collation cần tương thích với collation của index (đặc biệt đối với khóa dạng string). Một index `simple` và một index dùng locale khác không thay thế nhau hoàn toàn. Dùng `explain("executionStats")` quan sát kế hoạch, số index key/document đã duyệt, thời gian và mức độ phù hợp của sort.

Nếu đặt **unique index có collation**, các giá trị được coi là bằng nhau theo collation có thể bị từ chối khi ghi. Đó là quyết định nghiệp vụ; tránh vô tình coi hai tên khách hàng khác nhau là một danh tính. Với tài khoản/username, nên xác định khóa canonical và quy tắc unique riêng, không áp dụng unique trực tiếp cho tên hiển thị.

### 4.4. Regex không tự hưởng lợi từ collation

Truy vấn kiểu:

```javascript
db.customers.find({
  display_name: { $regex: "^đặng", $options: "i" }
});
```

dùng regex case-insensitive, nhưng cơ chế `$regex` **không collation-aware theo cách một phép equality dùng collation**, và thường không tận dụng tốt index case-insensitive có collation. Với chức năng tìm kiếm tăng dần, cân nhắc khóa tìm kiếm chuẩn hóa, index theo prefix, hoặc công cụ full-text/search phù hợp. Tránh nhận trực tiếp regex do người dùng cung cấp mà không giới hạn độ dài, escape và kiểm soát chi phí.

## 5. Java enum khi lưu vào MongoDB

### 5.1. Hành vi mặc định: enum thường lưu theo tên hằng số

Với mapping Spring Data MongoDB phổ biến, enum Java được lưu thành BSON string theo **tên hằng số enum** (tương đương `name()`), chẳng hạn:

```java
public enum PaymentStatus {
    PENDING,
    PAID,
    REFUNDED
}
```

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.annotation.Id;

@Document(collection = "payments")
public record PaymentDocument(
    @Id String id,
    PaymentStatus status
) {}
```

Khi ghi qua repository với cấu hình mặc định, có thể nhìn thấy:

```javascript
{
  "_id": "pay-001",
  "status": "PAID"
}
```

Đây là **ví dụ dạng document**, không phải lệnh `mongosh` để chạy nguyên khối. Nếu dùng custom converter, cách lưu enum có thể khác. Không nên đoán BSON type chỉ từ chữ `enum` trong Java; kiểm tra `$type` hoặc document thô sau khi ghi.

### 5.2. Tại sao lưu `enum.name()` có rủi ro?

Giả sử ở phiên bản mới, lập trình viên đổi `PENDING` thành `WAITING_FOR_PAYMENT` cho dễ hiểu. MongoDB vẫn chứa `"PENDING"` trong các document cũ. Khi converter cố ánh xạ chuỗi cũ về enum mới, việc đọc có thể thất bại vì không còn hằng số cùng tên.

Những thay đổi cần cân nhắc:

| Thay đổi trong code | Tác động nếu lưu tên enum mặc định |
| --- | --- |
| Đổi tên `PAID` thành `COMPLETED` | Dữ liệu cũ chứa `"PAID"` có thể không giải mã được |
| Bỏ một hằng số cũ | Document cũ vẫn có giá trị ấy |
| Thêm hằng số mới | Code cũ có thể không đọc được document do code mới ghi |
| Thay đổi thứ tự enum | Không ảnh hưởng chuỗi tên, nhưng nguy hiểm nếu nơi khác lưu ordinal |
| Gộp/tách trạng thái | Cần migration và quy tắc nghiệp vụ cụ thể |

**Không lưu `enum.ordinal()`** làm hợp đồng dữ liệu dài hạn nếu enum có thể sửa thứ tự hoặc thêm/bớt phần tử. Chỉ cần chèn một giá trị mới ở giữa, các số trước đây đã mang ý nghĩa khác.

### 5.3. Mã ổn định tách khỏi tên enum

Một cách thiết kế dễ bảo trì là phân biệt:

- **Tên hằng số Java:** dùng trong code, có thể đổi khi refactor.
- **Mã lưu trữ (`code`):** thuộc hợp đồng dữ liệu, được version và không đổi tùy tiện.
- **Nhãn hiển thị:** phụ thuộc ngôn ngữ/UI, không dùng làm định danh.

Ví dụ:

```java
public enum OrderStatus {
    WAITING_FOR_PAYMENT("pending"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Mã trạng thái không được hỗ trợ: " + code
        );
    }
}
```

Nếu đổi tên hằng số `WAITING_FOR_PAYMENT` thành `AWAITING_PAYMENT`, mã `"pending"` vẫn giữ nguyên. Điều này giúp phân tách vòng đời refactor code với hợp đồng BSON.

Trong hệ thống cần đọc dữ liệu lịch sử từ phiên bản rất cũ, `fromCode` có thể hỗ trợ alias theo migration rõ ràng, ví dụ `"PENDING_PAYMENT"` và `"pending"` cùng ánh xạ đến một trạng thái nghiệp vụ trong giai đoạn chuyển tiếp. Cần ghi nhận alias nào còn tồn tại và thời hạn loại bỏ; **không âm thầm biến mã lạ thành `PAID`**.

### 5.4. Đừng dùng nhãn hiển thị làm enum code

Không nên lưu `"Đã thanh toán"` làm mã trạng thái chính nếu sản phẩm có thể đổi ngôn ngữ, sửa câu chữ hoặc cần đồng bộ nhiều dịch vụ. Thay vào đó:

```text
Mã lưu trữ:         "paid"
Tên hằng số Java:  OrderStatus.PAID
Nhãn tiếng Việt:   "Đã thanh toán"
Nhãn tiếng Anh:    "Paid"
```

Nhãn có thể được dịch ở lớp giao diện dựa trên mã trạng thái. Mã lưu trữ được quy định theo một bộ giá trị độc lập với locale.

## 6. Thiết kế document Spring Data MongoDB với mã ổn định

### 6.1. Ánh xạ String code rõ ràng

Ví dụ đơn hàng lưu tên khách, khóa tìm kiếm và mã trạng thái. Sử dụng chuỗi code trong entity lưu trữ để bảo đảm dữ liệu BSON ổn định, còn logic nghiệp vụ chuyển qua `OrderStatus`:

```java
import java.time.Instant;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("customer_name")
    String customerName,

    @Field("customer_name_key")
    String customerNameKey,

    @Field("status_code")
    String statusCode,

    @Field("created_at")
    Instant createdAt
) {
    public OrderStatus orderStatus() {
        return OrderStatus.fromCode(statusCode);
    }

    public static OrderDocument create(
        String id,
        String customerName,
        OrderStatus status,
        Instant createdAt
    ) {
        String display = NameText.displayName(customerName);
        return new OrderDocument(
            id,
            display,
            NameText.searchKey(display),
            status.code(),
            createdAt
        );
    }
}
```

Trong đoạn này, `@MongoId(FieldType.STRING)` yêu cầu lưu `id` dạng BSON string trong `_id`. `@Field` xác định tên BSON rõ ràng, tránh trộn camelCase và snake_case. `OrderStatus`, `NameText` từ các ví dụ trước là mã Java hỗ trợ cho entity này.

Nếu ứng dụng cần dùng `OrderStatus` làm field Java trực tiếp thay vì `String`, có thể xây dựng Spring Data `@WritingConverter` và `@ReadingConverter` để chuyển đổi giữa enum và chuỗi code. Khi làm vậy cần đăng ký converters trong cấu hình `MongoCustomConversions`, kiểm tra tác động đến các enum khác và kiểm thử round-trip. Bài này dùng **String code tường minh** để tránh đưa ra một converter toàn cục ngoài ý muốn.

### 6.2. Ghi và đọc bằng repository

```java
import java.time.Instant;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
}
```

Trong một service đã tiêm `OrderRepository`, dùng:

```java
OrderDocument saved = orderRepository.insert(
    OrderDocument.create(
        "order-1001",
        "Đặng Thị Ánh",
        OrderStatus.PAID,
        Instant.parse("2026-11-20T01:00:00Z")
    )
);

OrderDocument reloaded = orderRepository
    .findById(saved.id())
    .orElseThrow();

System.out.println(reloaded.orderStatus()); // PAID
```

Mẫu document kỳ vọng sau khi ghi:

```javascript
{
  "_id": "order-1001",
  "customer_name": "Đặng Thị Ánh",
  "customer_name_key": "đặng thị ánh",
  "status_code": "paid",
  "created_at": ISODate("2026-11-20T01:00:00Z")
}
```

Tùy cấu hình Spring Data MongoDB, document cũng có thể chứa trường metadata `_class`. Ví dụ không giả định mọi cấu hình đều loại bỏ type hint này. Giá trị thực tế phải được đọc lại từ collection.

### 6.3. Truy vấn bằng `MongoTemplate` dùng tên property Java

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderDocument> findPaid(MongoTemplate template) {
    Query query = Query.query(
        Criteria.where("statusCode").is(OrderStatus.PAID.code())
    );
    return template.find(query, OrderDocument.class);
}
```

Khi Spring Data lập query thông qua mapping `OrderDocument`, tên property `statusCode` được ánh xạ thành field BSON `status_code`. Nhưng trong `mongosh`, cần dùng tên đã lưu:

```javascript
db.orders.find({ status_code: "paid" });
```

Đừng nhầm query raw `{ statusCode: "paid" }` với query qua `MongoTemplate` dùng tên property Java; raw query không tự đọc annotation để đổi tên.

### 6.4. Cập nhật trạng thái có điều kiện, giữ nguyên quy ước

Nếu đơn chỉ được chuyển từ `pending` sang `paid`, dùng thao tác cập nhật có điều kiện để tránh vô tình ghi đè trạng thái đã đổi bởi một request khác:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import com.mongodb.client.result.UpdateResult;

public void markPaid(MongoTemplate template, String id) {
    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("statusCode").is(OrderStatus.WAITING_FOR_PAYMENT.code())
    );

    Update update = new Update()
        .set("statusCode", OrderStatus.PAID.code());

    UpdateResult result = template.updateFirst(
        query, update, OrderDocument.class
    );

    if (result.getMatchedCount() != 1) {
        throw new IllegalStateException(
            "Không tìm thấy đơn ở trạng thái pending"
        );
    }
}
```

Thao tác ghi một document trong MongoDB là nguyên tử, và điều kiện trên trạng thái giúp từ chối một số cập nhật đồng thời không còn hợp lệ. Nó không thay thế các transaction đa document nếu quy trình còn phải thay đổi nhiều collection. Để đồng bộ thanh toán bên ngoài, cần thiết kế idempotency và quy trình xác nhận riêng.

## 7. Quy ước đặt tên trường và giá trị lưu

Một quy ước nên đủ rõ để người viết Java, người dùng `mongosh` và hệ thống phân tích đều hiểu cùng dữ liệu.

### 7.1. Tên BSON field

Ví dụ chọn **snake_case** cho field trong MongoDB, camelCase cho property Java:

| Java property | BSON field | BSON type dự kiến |
| --- | --- | --- |
| `id` | `_id` | `string` (theo `@MongoId(FieldType.STRING)`) |
| `customerName` | `customer_name` | `string` |
| `customerNameKey` | `customer_name_key` | `string` |
| `statusCode` | `status_code` | `string` |
| `createdAt` | `created_at` | `date` |

Đây là **quy ước ví dụ**, không phải yêu cầu bắt buộc của MongoDB. Một hệ thống đã dùng camelCase nhất quán có thể tiếp tục dùng nó. Quan trọng là thống nhất, có tài liệu và tránh đổi tên khi không có kế hoạch migration.

Không đưa dữ liệu do người dùng nhập trực tiếp thành **tên field tùy ý**. Những ký tự đặc biệt như dấu chấm, ký tự `$` và quy tắc của field path có thể làm truy vấn, cập nhật hay xuất nhập dữ liệu khó xử lý; các key động cần chiến lược rõ ràng, chẳng hạn mảng cặp `{key, value}` hoặc map được kiểm soát.

### 7.2. Giá trị lưu phải có hợp đồng

Ví dụ hợp đồng cho `status_code`:

| Mã lưu | Ý nghĩa | Chuyển trạng thái ví dụ |
| --- | --- | --- |
| `"pending"` | Đơn đang chờ xác nhận thanh toán | Sang `"paid"` hoặc `"cancelled"` |
| `"paid"` | Thanh toán được xác nhận | Các bước giao hàng được quản lý ở trường/quy trình thích hợp |
| `"cancelled"` | Đơn đã hủy | Thường là trạng thái kết thúc theo nghiệp vụ |

Các mã chỉ là **ví dụ** để học cách thiết kế; không nên tự suy luận rằng nghiệp vụ thực tế có đúng ba trạng thái, hay mọi đơn đều được phép chuyển trạng thái theo cùng sơ đồ.

Chọn một phong cách giá trị nhất quán, chẳng hạn lowercase ASCII với dấu gạch dưới cho mã nhiều từ: `"awaiting_payment"`, `"partially_refunded"`. Không trộn `"PAID"`, `"Paid"`, `"Đã thanh toán"` và `1` trong cùng field vì sự tương đương giữa chúng chỉ tồn tại trong đầu người lập trình, không nằm trong BSON.

### 7.3. Null, missing, empty và unknown phải được định nghĩa

Bốn cách biểu diễn sau có ý nghĩa khác nhau:

```javascript
{ "_id": "a", "status_code": "pending" }
{ "_id": "b", "status_code": "" }
{ "_id": "c", "status_code": null }
{ "_id": "d" }
```

Trong dữ liệu thực tế:

- `"pending"`: một trạng thái cụ thể được công nhận.
- `""`: chuỗi rỗng, không nên tự hiểu là “chưa thanh toán” nếu chưa quy định.
- `null`: field có mặt nhưng không có giá trị.
- `missing`: document không chứa field, có thể do dữ liệu từ phiên bản schema cũ.

Truy vấn `{ status_code: null }` của MongoDB có thể khớp cả giá trị null và field thiếu. Để phân biệt, dùng `$type` hoặc `$exists`:

```javascript
db.orders.find({ status_code: { $type: "null" } });
db.orders.find({ status_code: { $exists: false } });
db.orders.find({ status_code: "" });
```

Nếu nghiệp vụ yêu cầu field trạng thái luôn hợp lệ, nên ngăn null/rỗng ngay khi ghi, bổ sung validation và kế hoạch sửa dữ liệu cũ. **Không dùng giá trị mặc định `"paid"`** khi dữ liệu thiếu hay mã không nhận diện được; điều này có thể gây sai nghiêm trọng về thanh toán.

## 8. Kiểm tra dữ liệu BSON thực tế

### 8.1. Đọc thô sau khi ghi qua Spring Data

Một repository trả về entity đúng chưa chứng minh BSON thực sự có tên trường và kiểu mong muốn. Spring Data có thể chuyển đổi ở cả chiều ghi/đọc. Sau khi lưu, dùng `MongoTemplate.getCollection(...)` để đọc trực tiếp driver:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

import static com.mongodb.client.model.Filters.eq;

public void inspectRaw(
    MongoTemplate template,
    String id
) {
    Document raw = template.getCollection("orders")
        .find(eq("_id", id))
        .first();

    if (raw == null) {
        throw new IllegalStateException("Document không tồn tại");
    }

    System.out.println(raw.toJson());
    System.out.println(raw.keySet());
    System.out.println(raw.get("customer_name"));
    System.out.println(raw.get("status_code").getClass().getName());
}
```

Ví dụ giả định đã kết nối đến database kiểm thử. `getCollection("orders")` trả về driver collection, không tự ánh xạ theo entity Java. Việc in `Document.toJson()` cho thấy hình dạng dữ liệu, nhưng để kiểm tra BSON type chính xác có thể dùng `$type` và canonical Extended JSON trong `mongosh`.

### 8.2. Extended JSON và `$type`

```javascript
const order = db.orders.findOne({ _id: "order-1001" });

if (order != null) {
  print(EJSON.stringify(order, null, 2, { relaxed: false }));
}

db.orders.aggregate([
  { $match: { _id: "order-1001" } },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      nameType: { $type: "$customer_name" },
      keyType: { $type: "$customer_name_key" },
      statusType: { $type: "$status_code" },
      createdAtType: { $type: "$created_at" }
    }
  }
]);
```

Với entity và mapping ở trên, kết quả mong đợi gồm `"string"` cho ID, tên, khóa tìm kiếm, mã trạng thái và `"date"` cho thời gian. Nếu ID là ObjectId hoặc `status_code` là số/chuỗi khác, cần xác minh đường ghi và converter thực tế.

### 8.3. Thống kê sự không đồng nhất trong collection

Sau một migration hoặc thay đổi ứng dụng, cùng field có thể chứa nhiều kiểu và mã khác nhau. Kiểm tra theo nhóm:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        type: { $type: "$status_code" },
        value: "$status_code"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Khi group theo `value`, hãy nhớ đây là biểu thức aggregation; document thiếu field, null và cách biểu diễn kết quả có thể cần phân tách bằng `$type` như đã làm. Với dữ liệu lớn, pipeline có thể tốn tài nguyên và nên được chạy trên phạm vi cho phép hoặc môi trường kiểm thử/sao chép thích hợp.

Nếu thấy các mã `"PAID"`, `"paid"` và `"Đã thanh toán"` cùng tồn tại, **đừng sửa hàng loạt ngay**. Trước tiên xác định mã chuẩn, những phiên bản ứng dụng còn ghi giá trị cũ, logic đọc trong giai đoạn chuyển tiếp và kế hoạch rollback.

## 9. Index và truy vấn ảnh hưởng thế nào đến quy ước string/enum?

### 9.1. Index trên mã trạng thái và thời điểm

Một trang quản trị thường liệt kê đơn mới nhất của trạng thái `paid`:

```javascript
db.orders.createIndex({
  status_code: 1,
  created_at: -1
});

db.orders.find({ status_code: "paid" })
  .sort({ created_at: -1 })
  .limit(20)
  .explain("executionStats");
```

Đây là ví dụ cho database kiểm thử. Nếu code ứng dụng dùng field Java `statusCode` với `@Field("status_code")` thì index raw MongoDB phải đặt theo tên BSON `status_code`. Index được chọn cần dựa trên mẫu truy vấn, tỷ lệ phân bố trạng thái, yêu cầu sort và thống kê thực tế; không mặc định mọi truy vấn đều cần một index riêng.

Mã enum thuộc tập giá trị nhỏ nên trường trạng thái có độ chọn lọc thấp trong một số hệ thống. Ghép với `created_at`, `customer_id` hoặc điều kiện khác tùy mẫu truy vấn có thể hữu ích hơn index đơn lẻ; đánh giá bằng `explain` và khối lượng dữ liệu thật.

### 9.2. Chữ hoa, collation và tính duy nhất

Đối với mã trạng thái chuẩn hóa như `"paid"`, nên **ghi cùng một dạng mã**; không cần áp dụng collation phân biệt ngôn ngữ. Với tên hiển thị, có thể cần locale và index collation tương ứng như mục 4.

Ví dụ **unique index** trên username đã canonical hóa:

```javascript
db.accounts.createIndex(
  { username_key: 1 },
  { unique: true }
);
```

Ở đây giả định `username_key` được ứng dụng sinh theo hợp đồng cố định và không thiếu trên các account được quản lý. Unique index có thể cho phép nhiều tài liệu thiếu field tùy loại index và điều kiện, nên nếu field bắt buộc cần phối hợp validation và thiết kế index phù hợp. Đừng dùng cùng logic cho username, email và tên người; mỗi loại có quy tắc nhận dạng riêng.

### 9.3. Aggregation theo enum code

Ví dụ thống kê số đơn theo trạng thái:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status_code",
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1 } }
]);
```

Nếu field có nhiều biến thể `"PAID"`, `"paid"`, `"Paid"`, kết quả phân nhóm sẽ không đại diện cho một hợp đồng trạng thái thống nhất. Có thể dùng phép biến đổi trong pipeline cho báo cáo tạm thời, nhưng nên xử lý nguyên nhân phát sinh dữ liệu lệch chuẩn, không chỉ gộp kết quả ở báo cáo.

## 10. Kiểm soát dữ liệu với validation và migration

### 10.1. Schema validation phía MongoDB

MongoDB hỗ trợ `$jsonSchema` validator. Ví dụ fragment cấu hình cho collection `orders`:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["customer_name", "status_code", "created_at"],
    properties: {
      customer_name: { bsonType: "string" },
      customer_name_key: { bsonType: "string" },
      status_code: {
        bsonType: "string",
        enum: ["pending", "paid", "cancelled"]
      },
      created_at: { bsonType: "date" }
    }
  }
}
```

Đoạn trên là **fragment validator**, không phải lệnh `mongosh` hoàn chỉnh. Cần tích hợp nó qua cơ chế quản lý schema của môi trường và cân nhắc dữ liệu cũ trước khi bật mức kiểm tra/điều kiện chặn ghi. Validator không tự biết cách `customer_name_key` được tạo từ `customer_name`; bất biến giữa hai trường vẫn phải được ứng dụng và kiểm thử bảo đảm.

Ngoài database validator, dùng validation tại API/service để phát hiện mã không hợp lệ ngay khi tiếp nhận request. **Không tin mã trạng thái từ client** cho các bước nghiệp vụ có quyền hạn như xác nhận thanh toán; mã có thể hợp lệ về kiểu mà vẫn không được phép chuyển theo quy trình.

### 10.2. Khi cần đổi mã enum đã lưu

Giả sử dữ liệu cũ lưu `"PENDING"`, dữ liệu mới muốn dùng `"pending"`. Quy trình thường cần:

1. Xác định các phiên bản ứng dụng còn đọc/ghi `"PENDING"`.
2. Xây dựng cơ chế đọc tương thích có kiểm soát nếu có giai đoạn hai phiên bản chạy song song.
3. Thử chuyển đổi trên database kiểm thử, ghi nhận số bản ghi và các giá trị lạ.
4. Phối hợp triển khai code, đổi đường ghi sang mã chuẩn, rồi migration dữ liệu theo thứ tự an toàn.
5. Kiểm tra `$type`, phân bố `status_code`, truy vấn và thống kê sau migration.
6. Loại bỏ alias và quy tắc tạm khi chứng minh dữ liệu cũ đã được xử lý.

Một lệnh `updateMany` có thể đổi các giá trị rõ ràng, nhưng cần giới hạn đúng collection, điều kiện và giai đoạn migration. Không chạy trên dữ liệu thật khi chưa kiểm chứng kế hoạch tương thích và rollback.

### 10.3. Phiên bản quy ước chuẩn hóa Unicode

Nếu ban đầu ứng dụng chỉ `trim` tên, sau đó chuyển sang NFC hoặc tạo `customer_name_key`, document cũ có thể chưa tuân theo quy tắc mới. Một lựa chọn là bổ sung `text_normalization_version` hoặc quản lý version qua migration nếu sự khác biệt ảnh hưởng tìm kiếm/index.

Không nên chạy `lowercase` hay bỏ dấu trên toàn bộ dữ liệu nguồn để “dọn sạch” bởi có thể thay đổi nội dung cần giữ nguyên. Nếu có yêu cầu tìm kiếm mới, hãy tạo khóa dẫn xuất từ dữ liệu hiển thị, dùng chiến lược rebuild nhất quán và xác minh số lượng bản ghi trước/sau.

## 11. Kiểm thử và chẩn đoán các trường hợp biên

### 11.1. Một bộ kiểm thử nên bảo vệ điều gì?

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Tên tiếng Việt có dấu | Ghi/đọc giữ đúng chuỗi hiển thị và mã Unicode kỳ vọng |
| Hai biểu diễn NFC/NFD của cùng tên | Được chuẩn hóa nhất quán nếu field quy định NFC |
| Tên chứa emoji ngoài BMP | Không bị cắt sai giữa cặp surrogate; đo độ dài bằng tiêu chí phù hợp |
| Chuỗi rỗng/blank/null/missing | Validation và logic đọc phân biệt đúng từng tình huống |
| Tên cần tìm không phân biệt hoa/thường | Query, collation và index cùng tuân theo quy tắc mong muốn |
| Java enum được đổi tên nhưng mã lưu không đổi | Dữ liệu cũ vẫn ánh xạ được qua mã ổn định |
| Mã enum lạ xuất hiện từ dữ liệu cũ | Bị phát hiện hoặc đi qua đường xử lý tương thích đã định |
| Lưu qua repository | BSON thực dùng `customer_name`, `status_code` và các kiểu đúng |
| Cập nhật tên | `customer_name_key` được cập nhật đồng thời với tên |
| Nhiều request đổi trạng thái | Không ghi đè trạng thái ngoài đường chuyển được phép |

### 11.2. Kiểm thử Java cho Unicode và enum

Ví dụ JUnit 5:

```java
import java.text.Normalizer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TextAndCodeTest {

    @Test
    void nfcMakesEquivalentAccentedTextEqual() {
        String nfd = Normalizer.normalize(
            "Tiếng Việt", Normalizer.Form.NFD
        );
        String nfc = NameText.displayName(nfd);

        assertEquals(
            Normalizer.normalize("Tiếng Việt", Normalizer.Form.NFC),
            nfc
        );
    }

    @Test
    void enumCodeIsIndependentOfDisplayLabel() {
        assertEquals("paid", OrderStatus.PAID.code());
        assertEquals(OrderStatus.PAID, OrderStatus.fromCode("paid"));
        assertThrows(
            IllegalArgumentException.class,
            () -> OrderStatus.fromCode("Đã thanh toán")
        );
    }
}
```

Kiểm thử đơn vị như trên kiểm tra quy tắc Java. Để chắc chắn Spring Data MongoDB lưu đúng BSON, cần **kiểm thử tích hợp với MongoDB thực** (chẳng hạn Testcontainers), ghi qua repository, đọc raw document bằng `MongoTemplate.getCollection(...)` hoặc `mongosh` rồi xác minh `status_code` là BSON string, tên field đúng và chuỗi Unicode round-trip chính xác.

Ví dụ đoạn kiểm tra tích hợp bên trong test đã được cấu hình MongoDB:

```java
OrderDocument input = OrderDocument.create(
    "unicode-check-01",
    "Đặng Thị Ánh 😊",
    OrderStatus.PAID,
    java.time.Instant.parse("2026-11-20T01:00:00Z")
);
orderRepository.insert(input);

org.bson.Document raw = mongoTemplate
    .getCollection("orders")
    .find(com.mongodb.client.model.Filters.eq(
        "_id", "unicode-check-01"
    ))
    .first();

org.junit.jupiter.api.Assertions.assertNotNull(raw);
org.junit.jupiter.api.Assertions.assertEquals(
    "paid", raw.getString("status_code")
);
org.junit.jupiter.api.Assertions.assertEquals(
    "Đặng Thị Ánh 😊", raw.getString("customer_name")
);
```

Mẫu trên giả định `orderRepository` và `mongoTemplate` được inject trong test, có cấu hình database kiểm thử riêng và document ID chưa tồn tại. Đây là hướng dẫn soạn test, không phải kết quả đã chạy.

### 11.3. Chẩn đoán lỗi thực tế

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Tên giống nhau nhưng query `equals` không ra | NFC/NFD, hoa/thường, dấu, khoảng trắng vô hình, collation |
| Sort tiếng Việt khó hiểu | Locale/strength/collation của query và index |
| Đổi tên enum xong đọc document cũ lỗi | BSON lưu `enum.name()` cũ, thiếu converter hoặc mã tương thích |
| Báo cáo đếm `PAID` và `paid` riêng | Quy ước enum code không thống nhất |
| `MongoTemplate` query ra dữ liệu nhưng raw `mongosh` không ra | Tên Java property được mapping bởi `@Field`; raw query dùng tên BSON |
| Tên bị cắt ở emoji | Giới hạn theo UTF-16 code units thay vì yêu cầu độ dài thực |
| Unique index từ chối tên khác nhau | Collation hoặc canonicalization gộp các giá trị mà nghiệp vụ xem là riêng biệt |
| Tìm kiếm regex chậm | Query regex không tận dụng index như equality có collation, thiếu giới hạn/prefix |
| Index không được dùng dù trường tồn tại | Tên BSON sai, collation không khớp, thứ tự khóa hoặc chọn lọc thấp |
| Reactive và imperative ghi ra khác dạng | Converter/client/config khác nhau; kiểm tra BSON raw của cả hai đường |

**Hiệu năng:** Khi phân tích truy vấn chuỗi, sử dụng `explain("executionStats")` để quan sát `COLLSCAN`/`IXSCAN`, số document/key đọc và phạm vi sort. Index dùng collation có thể có chi phí lưu trữ lớn hơn index so sánh đơn giản; không nên tạo nhiều index chỉ để xử lý sai quy ước viết hoa. Việc thống nhất mã ngay từ lúc ghi thường giảm độ phức tạp về lâu dài.

**Reactive access:** `ReactiveMongoRepository` và `ReactiveMongoTemplate` dùng nguyên tắc mapping chuỗi/enum tương tự khi có cùng converter và cấu hình. Reactive không tự chuẩn hóa Unicode, tạo canonical code hay giải quyết lỗi migration. Nếu thao tác phải cập nhật nhiều document theo cùng một nghiệp vụ, thiết kế tính nhất quán/transaction và retry phù hợp với triển khai MongoDB; xử lý reactive có thể cần `ReactiveMongoTransactionManager` khi sử dụng transaction.

## 12. Checklist thiết kế dữ liệu chuỗi và enum

1. Xác định mỗi field là **văn bản hiển thị**, **mã nghiệp vụ**, **khóa tìm kiếm** hay **dữ liệu nguyên bản**.
2. Chọn cách chuẩn hóa Unicode (nếu cần) cho từng field; thử NFC/NFD, dấu kết hợp và emoji.
3. Định nghĩa quy tắc chữ hoa/thường, dấu và whitespace, cũng như cách tìm kiếm theo locale.
4. Phân biệt null, missing, chuỗi rỗng và mã `unknown`; chỉ dùng mỗi giá trị khi có ý nghĩa nghiệp vụ rõ.
5. Định nghĩa mã enum bền vững, không phụ thuộc tên hằng số Java hoặc nhãn giao diện.
6. Thống nhất tên BSON field, dùng `@Field` có chủ đích và hiểu cách mapping của repository/`MongoTemplate`.
7. Chọn index và collation theo đúng truy vấn thực tế; xác minh bằng `explain`.
8. Kiểm tra document BSON đã ghi và round-trip Java, không chỉ dựa trên annotation.
9. Thiết kế tương thích dữ liệu cũ khi thay đổi tên, chuẩn Unicode hay bộ giá trị enum.
10. Kiểm thử các trường hợp biên và quan sát dữ liệu thực để phát hiện giá trị không đồng nhất.

Một quy ước lưu trữ tốt làm cho **chuỗi tiếng Việt giữ đúng nội dung**, **enum có mã ổn định qua các phiên bản code**, và **truy vấn MongoDB nhất quán với giá trị BSON thực tế**. Trong Spring Data MongoDB, hãy kết hợp ánh xạ tường minh, chuẩn hóa có kiểm soát, kiểm tra dữ liệu thô, index/collation phù hợp và kiểm thử tích hợp để hệ thống dễ thay đổi mà không đánh mất ý nghĩa dữ liệu.

