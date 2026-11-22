# Quy tắc đặt tên

## 1. Quy tắc đặt tên trong sinh mã là gì?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), người dùng đặt tên cho biến, thuộc tính, rule, kiểu dữ liệu, hàm hoặc tài nguyên theo cách gần với miền nghiệp vụ. Khi sinh mã (code generation), compiler hoặc generator phải chuyển các tên đó sang ngôn ngữ đích như Java, TypeScript, Python, SQL hoặc một định dạng cấu hình khác.

**Quy tắc đặt tên (naming rules)** xác định cách ánh xạ tên từ DSL sang tên hợp lệ và dễ hiểu trong mã được sinh ra. Quy tắc này bao gồm:

- Cách viết hoa và viết thường.
- Ký tự được phép xuất hiện trong identifier.
- Từ khóa dành riêng của ngôn ngữ đích.
- Xử lý tên trùng trong cùng phạm vi.
- Tạo tên cho thành phần phụ trợ mà generator tự sinh.
- Bảo toàn quan hệ giữa tên DSL và tên target.
- Tính ổn định khi sinh lại mã.

Ví dụ, DSL có thể cho phép:

~~~text
entity customer_profile {
  field first-name: String
  field created-at: Timestamp
}
~~~

Generator Java có thể tạo:

~~~java
public final class CustomerProfile {
    private String firstName;
    private Instant createdAt;
}
~~~

Tên customer_profile được chuyển thành CustomerProfile; first-name thành firstName; created-at thành createdAt. Đây không chỉ là thay dấu gạch ngang bằng chữ hoa. Generator phải bảo đảm tên mới hợp lệ, không xung đột và giữ đúng ý nghĩa của symbol gốc.

Một generator tốt nên áp dụng chính sách đặt tên thống nhất, có thể cấu hình và có thể dự đoán. Cùng một đầu vào và cùng cấu hình cần tạo cùng tên đầu ra.

## 2. Tên trong DSL và tên trong ngôn ngữ đích

Tên trong DSL và identifier của ngôn ngữ đích thuộc hai hệ quy tắc khác nhau.

DSL có thể cho phép tên:

~~~text
field "customer-id"
field "Ngày tạo"
field "class"
~~~

Nhưng ngôn ngữ đích có thể:

- Không cho phép dấu gạch ngang trong identifier.
- Hạn chế ký tự Unicode.
- Dùng class làm từ khóa.
- Phân biệt hoặc không phân biệt chữ hoa/chữ thường.
- Có giới hạn riêng về tên bảng, cột hoặc biến.

Do đó, không nên sao chép tên DSL trực tiếp vào mã sinh ra mà không qua bước chuẩn hóa và kiểm tra.

### 2.1 Symbol identity khác tên hiển thị

Một symbol cần có định danh nội bộ ổn định, ví dụ SymbolId. Tên hiển thị là thuộc tính có thể thay đổi.

Ví dụ:

~~~text
SymbolId: entity-42
Source name: customer-profile
Generated Java name: CustomerProfile
Generated SQL name: customer_profile
~~~

Nếu người dùng đổi tên hiển thị, symbol vẫn có thể giữ identity trong hệ thống hỗ trợ rename hoặc migration. Điều này giúp generator liên kết đúng tham chiếu và không nhầm hai symbol chỉ vì chúng có tên giống nhau.

### 2.2 Không dùng tên hiển thị làm khóa nội bộ

Nếu dùng chuỗi tên làm khóa duy nhất, các trường hợp sau dễ gây lỗi:

- Hai scope có cùng tên.
- Hai module có cùng tên entity.
- Một tên bị chuẩn hóa thành cùng dạng với tên khác.
- Người dùng đổi tên một symbol.
- Hai target language ánh xạ cùng tên nguồn theo cách khác nhau.

Hãy dùng SymbolId hoặc một định danh tương đương trong semantic model. Tên nguồn và tên sinh ra chỉ là các cách biểu diễn của symbol.

## 3. Pipeline chuyển đổi tên

Quá trình đặt tên nên là một bước rõ ràng trong pipeline sinh mã.

~~~text
DSL source
    |
    v
Parse / Name resolution
    |
    v
Symbol table with stable IDs
    |
    v
Target naming policy
    |
    +--> normalize style
    +--> validate identifier
    +--> handle reserved words
    +--> resolve collisions
    +--> allocate generated names
    |
    v
Name mapping table
    |
    v
Code generator
    |
    v
Target source files
~~~

Các bước chính:

1. Lấy symbol đã được phân giải từ semantic model.
2. Chọn chính sách đặt tên theo target language và cấu hình project.
3. Chuẩn hóa cách viết.
4. Kiểm tra identifier có hợp lệ không.
5. Xử lý từ khóa dành riêng.
6. Phát hiện xung đột trong phạm vi đích.
7. Cấp tên cho symbol và các thành phần phụ trợ.
8. Lưu mapping để generator và source map dùng lại.

Không nên để mỗi template tự viết một hàm đổi tên riêng. Khi quy tắc nằm rải rác, cùng một symbol có thể được sinh thành firstName ở một file nhưng FirstName ở file khác.

## 4. Các kiểu quy ước đặt tên phổ biến

Ngôn ngữ đích và cộng đồng phát triển thường có quy ước viết tên khác nhau.

| Kiểu | Ví dụ | Cách dùng thường gặp |
|---|---|---|
| camelCase | customerName | Biến, thuộc tính, method |
| PascalCase | CustomerProfile | Class, type, record |
| snake_case | customer_name | Biến, hàm, cột SQL |
| UPPER_SNAKE_CASE | MAX_RETRY_COUNT | Hằng số |
| kebab-case | customer-name | Tên cấu hình, command, file |
| SCREAMING-KEBAB | CUSTOMER-NAME | Một số mã hoặc format đặc thù |

Không có một kiểu viết phù hợp cho mọi vị trí. Một chính sách thường có các hàm riêng:

- convertTypeName
- convertPropertyName
- convertMethodName
- convertConstantName
- convertPackageName
- convertFileName

Ví dụ, cùng một symbol nguồn:

~~~text
customer-profile
~~~

có thể được chuyển thành:

| Vai trò | Tên sinh ra |
|---|---|
| Java class | CustomerProfile |
| Java field | customerProfile |
| Python class | CustomerProfile |
| Python attribute | customer_profile |
| SQL table | customer_profile |
| File name | customer-profile |

Generator nên áp dụng quy ước của target và vai trò symbol, thay vì một phép chuyển đổi chung cho mọi tên.

## 5. Chuẩn hóa tên thành các từ

Trước khi chuyển sang camelCase, PascalCase hoặc snake_case, generator cần nhận diện các thành phần từ.

Ví dụ:

~~~text
customer-profile
CustomerProfile
customerProfile
customer_profile
HTTPServer
userID
created_at
~~~

Một bộ tách từ có thể nhận diện:

- Dấu gạch ngang, gạch dưới và dấu cách.
- Ranh giới giữa chữ thường và chữ hoa.
- Ranh giới giữa chữ cái và chữ số.
- Các viết tắt viết hoa liên tiếp.

### 5.1 Chuyển đổi cơ bản

Ví dụ:

~~~text
customer-profile -> customerProfile
created_at       -> createdAt
customer name    -> customerName
~~~

### 5.2 Viết tắt

Tên có acronym cần một quy tắc nhất quán:

~~~text
HTTPServer
userID
XMLParser
~~~

Một chính sách có thể chuyển thành:

~~~text
httpServer
userId
xmlParser
~~~

Chính sách khác có thể giữ acronym:

~~~text
httpServer
userID
xmlParser
~~~

Không có cách duy nhất đúng. Điều quan trọng là định nghĩa quy tắc cho chữ viết tắt và dùng nhất quán ở mọi vị trí.

### 5.3 Chữ số

Các tên:

~~~text
ipv6Address
version2Config
sha256Digest
~~~

cần được tách từ mà không làm mất ý nghĩa chữ số. Không nên xóa mọi ký tự số hoặc tự thêm dấu gạch dưới nếu target cho phép identifier chứa số sau ký tự đầu.

### 5.4 Tên chỉ có dấu phân cách

Các tên như:

~~~text
---
___
"   "
~~~

có thể không tạo ra từ nào sau khi chuẩn hóa. Generator cần một chính sách rõ:

- Báo lỗi và yêu cầu tên hợp lệ.
- Dùng tên thay thế được quy định.
- Sinh tên kỹ thuật từ SymbolId.

Không nên tạo một identifier rỗng hoặc chỉ có dấu phân cách.

## 6. Quy tắc identifier của ngôn ngữ đích

Mỗi target language có grammar riêng cho identifier.

Một identifier thường cần:

- Bắt đầu bằng ký tự được phép.
- Không chứa ký tự phân cách không hợp lệ.
- Không trùng từ khóa dành riêng.
- Không vi phạm giới hạn của target như tên cột hoặc schema.

Ví dụ minh họa:

| Tên | Java | SQL phổ biến |
|---|---|---|
| customerName | Hợp lệ | Có thể hợp lệ |
| customer-name | Không hợp lệ nếu dùng trực tiếp | Cần quote hoặc đổi tên |
| 2ndValue | Không hợp lệ nếu bắt đầu bằng số | Tùy hệ quản trị |
| class | Từ khóa | Có thể là identifier tùy dialect |
| select | Hợp lệ trong Java | Từ khóa SQL |

Không nên dùng một regex duy nhất để kiểm tra identifier cho tất cả target. Hãy tạo IdentifierPolicy hoặc TargetLanguageProfile riêng.

### 6.1 Kiểm tra tên sau chuẩn hóa

Tên nguồn có thể hợp lệ trong DSL nhưng sau chuyển đổi lại không hợp lệ trong target. Ví dụ:

~~~text
2nd-value -> 2ndValue
~~~

Kết quả vẫn bắt đầu bằng số. Generator cần thêm tiền tố hoặc báo lỗi theo chính sách.

Một cách sửa có thể là:

~~~text
_2ndValue
~~~

hoặc:

~~~text
secondValue
~~~

Chọn cách nào phụ thuộc quy ước target và khả năng giữ mapping ổn định.

### 6.2 Identifier Unicode

Một số ngôn ngữ cho phép ký tự Unicode trong identifier, nhưng công cụ, formatter hoặc hệ thống build có thể hỗ trợ không đồng nhất.

Generator cần xác định:

- Có cho phép chữ cái Unicode không?
- Có chuẩn hóa NFC/NFD không?
- Có chuyển dấu tiếng Việt thành ASCII không?
- Có giữ nguyên ký tự không phải Latin không?
- Có giới hạn ký tự theo database hoặc file system không?

Nếu chuyển tiếng Việt thành ASCII, ví dụ customerTên thành customerTen, cần hiểu đây là chính sách có thể gây trùng tên và mất thông tin. Không nên âm thầm transliterate nếu dự án yêu cầu bảo toàn tên gốc.

### 6.3 Unicode normalization

Hai chuỗi có thể nhìn giống nhau nhưng có biểu diễn Unicode khác nhau, chẳng hạn ký tự dựng sẵn và ký tự kết hợp dấu. Nếu không chuẩn hóa, chúng có thể được coi là hai tên khác nhau ở một tầng nhưng giống nhau ở tầng khác.

Một chính sách thường dùng là chuẩn hóa NFC trước khi so sánh hoặc phát hiện xung đột. Tuy nhiên, cần giữ source spelling ban đầu để hiển thị và không thay đổi dữ liệu nguồn ngoài ý muốn.

## 7. Từ khóa dành riêng và tên xung đột với target

Một tên hợp lệ trong DSL có thể trùng keyword của ngôn ngữ đích.

Ví dụ:

~~~text
entity class {
  field type: String
  field return: String
}
~~~

Khi sinh Java, class, type và return là các từ khóa. Generator cần xử lý trước khi in identifier.

### 7.1 Escape identifier

Một số target cho phép quote hoặc escape identifier:

~~~sql
SELECT "order" FROM "user";
~~~

Trong SQL, cách quote và phân biệt chữ hoa/chữ thường phụ thuộc dialect. Không nên giả định dấu ngoặc kép có cùng semantics trên mọi database.

Java không có cú pháp quote identifier tương đương SQL. Generator thường phải đổi tên:

~~~java
class Class_ {
    String type_;
    String return_;
}
~~~

### 7.2 Suffix hoặc prefix

Một chính sách phổ biến là thêm hậu tố:

~~~text
class  -> class_
return -> return_
type   -> type_
~~~

Một chính sách khác dùng tiền tố:

~~~text
class -> dsl_class
~~~

Hãy chọn một cách nhất quán và bảo đảm tên sau biến đổi không tạo thêm xung đột.

### 7.3 Bảng từ khóa theo target

Mỗi target cần một danh sách keyword riêng. Cần xem xét:

- Reserved keywords.
- Contextual keywords.
- Tên đặc biệt do compiler hoặc runtime sử dụng.
- Tên bị cấm hoặc dành riêng bởi database.
- Tên có ý nghĩa đặc biệt trong file system hoặc build tool.

Danh sách này cần gắn với phiên bản target language hoặc dialect. Một từ chưa phải keyword trong phiên bản cũ có thể trở thành keyword ở phiên bản mới.

## 8. Phát hiện và xử lý tên trùng

Sau khi chuẩn hóa, hai symbol khác nhau có thể tạo ra cùng identifier.

Ví dụ:

~~~text
field customer-id: String
field customer_id: String
~~~

Nếu cả hai được chuyển sang snake_case, tên có thể giống nhau. Tương tự:

~~~text
field user-name: String
field user_name: String
~~~

### 8.1 Collision trong cùng scope

Hai biến hoặc field cùng tên trong một class có thể không được phép. Generator cần phát hiện trước khi ghi mã.

### 8.2 Collision do không phân biệt hoa thường

Một số target hoặc file system không phân biệt chữ hoa và chữ thường. Các tên:

~~~text
Customer
customer
~~~

có thể xung đột khi tạo file hoặc resource dù ngôn ngữ đích cho phép hai identifier khác nhau.

### 8.3 Collision do normalization

Ví dụ:

~~~text
customer-name
customer_name
CustomerName
~~~

có thể cùng được chuyển thành CustomerName. Vì vậy, collision detection phải chạy sau bước chuẩn hóa cuối cùng và theo đúng quy tắc so sánh của target.

### 8.4 Collision với tên generator tự tạo

Generator có thể tạo thêm:

- Constructor.
- Getter và setter.
- Builder.
- Metadata field.
- Helper method.
- Method serialize/deserialize.
- Tên nội bộ như INSTANCE hoặc TYPE.

Nếu người dùng đã khai báo một field có tên getName, generator tạo getter getName() có thể gây xung đột tùy target và thiết kế class.

Nên dành trước namespace cho các tên kỹ thuật hoặc cấp phát tất cả tên trong một NameAllocator chung.

## 9. Chiến lược giải quyết collision

Có một số cách xử lý phổ biến.

### 9.1 Báo lỗi

Nếu hai tên nguồn khác nhau nhưng không thể biểu diễn thành hai identifier riêng trong target, generator có thể báo lỗi:

~~~text
Generated name collision:
  customer-id -> customerId
  customer_id -> customerId
~~~

Đây là lựa chọn phù hợp khi tự động đổi tên có thể làm thay đổi API công khai hoặc gây khó hiểu.

### 9.2 Thêm hậu tố tăng dần

Ví dụ:

~~~text
customerId
customerId2
customerId3
~~~

Cách này đơn giản nhưng có thể không ổn định nếu thứ tự duyệt symbol thay đổi. Nếu thêm một field mới ở đầu danh sách, tên đã cấp cho các field cũ có thể bị đổi.

### 9.3 Hậu tố dựa trên SymbolId

Có thể dùng một phần định danh ổn định:

~~~text
customerId_a17c
customerId_b83f
~~~

Điều này giảm phụ thuộc vào thứ tự duyệt, nhưng tên sinh ra dài và kém thân thiện. Nên dùng khi cần bảo đảm uniqueness ổn định qua các lần generate.

### 9.4 Dùng namespace hoặc cấu trúc lồng nhau

Hai symbol có thể được đặt trong package, module hoặc class khác nhau để tránh trùng. Cách này chỉ hợp lệ nếu semantics của DSL cho phép tách phạm vi như vậy.

### 9.5 Yêu cầu người dùng đặt tên rõ hơn

Với API công khai hoặc schema, báo lỗi để người dùng đổi một tên nguồn có thể là lựa chọn tốt nhất. Điều này giúp tên generated code dễ đọc và dễ duy trì.

### 9.6 Chọn chiến lược theo loại symbol

| Loại symbol | Chiến lược thường phù hợp |
|---|---|
| Field nội bộ | Có thể thêm suffix ổn định |
| Public API | Ưu tiên báo lỗi hoặc yêu cầu mapping tường minh |
| Tên file | Kiểm tra case-insensitive và giới hạn file system |
| SQL column | Kiểm tra dialect, schema và quote rules |
| Helper nội bộ | Dùng namespace dành riêng hoặc tên có prefix |
| Symbol được tham chiếu bên ngoài | Giữ mapping ổn định, không đổi tùy thứ tự |

## 10. Scope và namespace trong mã sinh ra

Tên chỉ có ý nghĩa khi biết phạm vi của nó.

Ví dụ DSL:

~~~text
module sales {
  entity Customer
}

module support {
  entity Customer
}
~~~

Hai entity cùng tên nhưng thuộc hai module khác nhau. Generator Java có thể tạo:

~~~text
sales.Customer
support.Customer
~~~

Hoặc dùng package:

~~~java
package sales;

public final class Customer {}
~~~

và:

~~~java
package support;

public final class Customer {}
~~~

### 10.1 Qualified name

Một qualified name gồm các thành phần namespace:

~~~text
sales.Customer
support.Customer
~~~

Generator nên ánh xạ từng segment theo quy tắc package và type, không áp dụng một phép đổi tên cho toàn chuỗi rồi bỏ mất ranh giới namespace.

### 10.2 Local scope

Biến local có thể trùng tên với field nếu ngôn ngữ cho phép shadowing. Tuy nhiên, khi sinh mã, cần bảo đảm việc tham chiếu được ánh xạ đúng symbol.

Ví dụ:

~~~text
field name: String

function display(name: String) {
  return name
}
~~~

Tên tham số name shadow field name. Generator không được chỉ thay chuỗi name theo văn bản; phải dựa trên symbol binding để tham chiếu đúng.

### 10.3 Overload

Một DSL có thể cho phép nhiều hàm cùng tên nhưng khác chữ ký:

~~~text
function find(id: Integer)
function find(email: String)
~~~

Nếu target hỗ trợ overload, có thể giữ cùng tên. Nếu target không hỗ trợ overload theo kiểu tham số, generator cần tạo tên riêng hoặc wrapper dispatch. Việc đổi tên phải giữ được khả năng phân giải lời gọi.

## 11. Quy tắc tên cho các thành phần sinh tự động

Generator thường tạo thêm nhiều thành phần không xuất hiện trực tiếp trong DSL.

Ví dụ một entity:

~~~text
entity Customer {
  field name: String
}
~~~

Generator có thể tạo:

~~~java
public final class Customer {
    private String name;

    public Customer() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Builder builder() {
        return new Builder();
    }
}
~~~

Tên constructor, getter, setter, builder và tham số cần tuân theo cùng một chính sách.

### 11.1 Tên accessor

Với field:

~~~text
is-active: Boolean
~~~

Generator có thể tạo isActive() hoặc getIsActive(). Cần định nghĩa quy tắc Boolean accessor và tránh tạo hai method cùng chữ ký.

### 11.2 Tên setter

Một số framework dùng setName; framework khác dùng name(value). Generator cần theo convention của target framework nếu mã được sinh ra phải tích hợp với framework đó.

### 11.3 Tên constructor và factory

Nếu DSL cho phép một entity có field hoặc method tên builder, init hoặc create, generator cần kiểm tra collision với factory method mà nó tự sinh.

### 11.4 Tên nội bộ

Các helper như __dslType, $metadata hoặc generatedSchema có thể được dành riêng. Cần chọn prefix ít có khả năng xung đột và kiểm tra trong toàn scope.

## 12. Tên file, package và tài nguyên

Tên sinh ra không chỉ là identifier trong source code. Generator còn có thể tạo:

- File source.
- Package hoặc namespace.
- Tên bảng và cột database.
- Tên endpoint.
- Tên JSON property.
- Tên class test.
- Tên artifact hoặc resource.

Mỗi loại có quy tắc riêng.

### 12.1 Tên file

Tên file có thể bị giới hạn bởi:

- Ký tự cấm của hệ điều hành.
- Độ dài path.
- Không phân biệt hoa thường.
- Tên thiết bị dành riêng trên một số hệ thống.
- Dấu chấm hoặc dấu cách ở đầu/cuối.

Ví dụ, CustomerProfile.java và customerprofile.java có thể cùng tồn tại trên một số file system nhưng xung đột trên hệ thống khác.

Generator đa nền tảng nên dùng chính sách tên file bảo thủ hoặc phát hiện collision theo file system mục tiêu.

### 12.2 Package và namespace

Java package thường dùng chữ thường và các segment identifier hợp lệ. Generator nên tách namespace DSL thành các segment rồi chuẩn hóa từng segment.

~~~text
com.example.sales
~~~

Không nên tạo package segment bắt đầu bằng số hoặc trùng từ khóa mà không có chính sách xử lý.

### 12.3 SQL table và column

SQL identifier có giới hạn và quy tắc quote theo dialect. Một số database giới hạn độ dài identifier; một số tự chuyển chữ hoa hoặc chữ thường; một số phân biệt identifier có quote và không quote.

Ví dụ:

~~~sql
CREATE TABLE customer_profile (
    customer_id BIGINT,
    created_at TIMESTAMP
);
~~~

Nếu tên quá dài, generator có thể rút gọn, nhưng phải bảo đảm không tạo collision. Một suffix hash ổn định có thể hữu ích khi cần giới hạn độ dài.

### 12.4 JSON property và API field

Tên JSON thường không cần tuân theo identifier của Java. Có thể giữ snake_case trong JSON nhưng ánh xạ sang camelCase trong class:

~~~json
{
  "customer_id": 42
}
~~~

~~~java
private long customerId;
~~~

Mapping cần được giữ trong annotation hoặc serializer configuration. Không nên đổi tên field nội bộ rồi vô tình thay đổi API contract.

## 13. Bảo toàn mapping giữa source và generated code

Khi sinh mã, cần có cách truy ngược một tên target về symbol DSL ban đầu.

Ví dụ:

~~~text
DSL symbol:
  ID = field-42
  name = customer-id

Java output:
  customerId

SQL output:
  customer_id
~~~

Mapping này hữu ích cho:

- Diagnostics từ generated code quay về DSL source.
- Debugger và source map.
- Rename symbol.
- Tạo tài liệu API.
- Incremental regeneration.
- Theo dõi thay đổi giữa các phiên bản.

### 13.1 Mapping table

Có thể lưu:

~~~java
record GeneratedName(
    SymbolId symbolId,
    String sourceName,
    String targetName,
    TargetKind targetKind,
    SourceRange sourceRange
) {}
~~~

Mỗi target có thể có mapping riêng. Không nên giả định Java name và SQL name luôn giống nhau.

### 13.2 Source map

Nếu compiler sinh một method từ nhiều node DSL, source map có thể ánh xạ đoạn mã đích về một hoặc nhiều source range. Tên sinh ra cần tham gia mapping để IDE có thể tìm symbol gốc khi người dùng đặt con trỏ trên generated identifier.

### 13.3 Không dùng tên đã sinh để phân giải source

Name resolution nên dựa trên symbol của DSL trước code generation. Tên target chỉ phục vụ việc biểu diễn. Nếu dùng tên generated làm khóa phân giải ngược, collision hoặc thay đổi naming policy có thể làm mất liên kết.

## 14. Tính ổn định và khả năng tái lập

Một generator nên tạo cùng kết quả khi đầu vào và cấu hình không đổi.

Ví dụ, nếu có hai tên cùng chuẩn hóa thành customerId, cách thêm suffix không nên phụ thuộc vào thứ tự duyệt Map không ổn định.

### 14.1 Deterministic naming

Để tên ổn định:

- Sắp xếp symbol theo định danh ổn định trước khi cấp tên nếu cần.
- Dùng SymbolId làm cơ sở cho suffix.
- Giữ mapping qua các lần generate khi có yêu cầu tương thích.
- Không dựa vào timestamp hoặc random.
- Xác định quy tắc collision rõ ràng.

### 14.2 Tên ổn định qua phiên bản

Nếu generated code được commit vào repository hoặc dùng như public API, thay đổi naming policy có thể tạo diff rất lớn và phá vỡ caller.

Có thể cần:

- Version hóa naming policy.
- Giữ mapping cũ.
- Cung cấp migration hoặc rename map.
- Cảnh báo khi tên công khai thay đổi.
- Tách thay đổi formatting khỏi thay đổi API.

### 14.3 Suffix dựa trên thứ tự

Tên customerId2 có thể đổi thành customerId3 nếu một symbol mới được thêm trước nó. Nếu tên được dùng bên ngoài, điều này không ổn định.

Với symbol public, nên yêu cầu mapping tường minh hoặc dùng suffix dựa trên identity ổn định. Nếu dùng hash, cần chọn đủ độ dài và kiểm tra collision thực tế.

## 15. Tên công khai và tên nội bộ

Generator nên phân biệt:

- **Public name:** tên được dùng trong API, schema hoặc mã mà người dùng khác tham chiếu.
- **Internal name:** tên chỉ tồn tại trong generated implementation.
- **Temporary name:** tên tạm trong biểu thức hoặc block.
- **Synthetic name:** tên do compiler tạo ra nhưng không có khai báo trực tiếp trong DSL.

Mỗi loại có thể có chính sách khác nhau.

Ví dụ:

~~~text
Public class: CustomerProfile
Internal field: _dslState
Temporary variable: temp1
Synthetic helper: __dsl_convert_7f2a
~~~

Tên public nên dễ đọc, ổn định và có thể cấu hình. Tên nội bộ cần tránh collision và không nên trở thành API vô tình.

### 15.1 Synthetic symbol

Một số node không có tên nguồn nhưng cần tên target. Ví dụ, biểu thức lambda hoặc closure có thể cần class phụ trợ trong target không hỗ trợ closure trực tiếp.

Generator có thể tạo tên từ vị trí nguồn hoặc SymbolId:

~~~text
Lambda_12_4
Closure_a17c
~~~

Không nên dùng số dòng duy nhất nếu việc chèn một dòng ở đầu file làm đổi tên tất cả closure. Nếu cần ổn định qua chỉnh sửa, dùng identity hoặc mapping incremental.

## 16. Tùy chỉnh naming policy

Một DSL có thể cho phép project chọn convention:

~~~yaml
codegen:
  target: java
  naming:
    types: PascalCase
    fields: camelCase
    methods: camelCase
    constants: UPPER_SNAKE_CASE
    files: PascalCase
~~~

Đây là cấu hình minh họa. Cần định nghĩa rõ:

- Tên nào do generator tự quyết định.
- Tên nào người dùng có thể override.
- Tùy chỉnh có áp dụng cho mọi target hay riêng từng target.
- Override có được kiểm tra keyword và collision không.
- Naming policy có version không.

### 16.1 Annotation hoặc directive

DSL có thể cho phép tên target tường minh:

~~~text
@targetName("customer_id")
field customerId: Integer
~~~

Điều này hữu ích khi phải giữ tương thích với database hoặc API đã tồn tại.

Directive nên được kiểm tra:

- Có đúng target không?
- Tên có hợp lệ trong target không?
- Có collision không?
- Người dùng có quyền thay đổi public name không?
- Mapping có được giữ trong metadata không?

### 16.2 Tách source name và external name

Một field có thể có tên DSL, tên Java và tên JSON khác nhau:

~~~text
field customerId: Integer
  javaName = "customerId"
  jsonName = "customer_id"
  sqlName = "customer_id"
~~~

Không nên dùng một override chung nếu các hệ thống ngoài có contract riêng.

### 16.3 Cấu hình có thứ tự ưu tiên

Một chính sách có thể kết hợp:

1. Convention mặc định của target.
2. Override ở cấp project.
3. Override ở cấp module.
4. Override tại symbol.

Thứ tự ưu tiên cần được công bố và hiển thị. Nếu hai cấu hình xung đột, compiler nên báo lỗi hoặc áp dụng một quy tắc xác định, không chọn ngẫu nhiên.

## 17. Name allocator

Một thành phần hữu ích là NameAllocator, chịu trách nhiệm cấp identifier duy nhất trong một scope.

API khái quát:

~~~java
interface NameAllocator {
    String allocate(
        SymbolId symbol,
        String preferredName,
        NameKind kind
    );

    boolean isReserved(String name);
}
~~~

Allocator có thể:

1. Nhận preferred name đã chuẩn hóa.
2. Kiểm tra identifier hợp lệ.
3. Xử lý keyword.
4. Kiểm tra tên đã được cấp trong scope.
5. Tạo candidate thay thế nếu collision.
6. Ghi mapping symbol → generated name.

### 17.1 Ví dụ Java đơn giản

~~~java
final class SimpleNameAllocator {
    private final Set<String> used = new HashSet<>();
    private final Set<String> keywords;

    SimpleNameAllocator(Set<String> keywords) {
        this.keywords = Set.copyOf(keywords);
    }

    String allocate(String preferredName) {
        String base = preferredName;

        if (!isValidIdentifier(base)) {
            base = "_" + base;
        }

        if (keywords.contains(base)) {
            base = base + "_";
        }

        String candidate = base;
        int suffix = 2;

        while (used.contains(candidate)) {
            candidate = base + suffix++;
        }

        used.add(candidate);
        return candidate;
    }

    private boolean isValidIdentifier(String name) {
        if (name == null || name.isEmpty()) {
            return false;
        }
        if (!Character.isJavaIdentifierStart(name.charAt(0))) {
            return false;
        }
        for (int i = 1; i < name.length(); i++) {
            if (!Character.isJavaIdentifierPart(name.charAt(i))) {
                return false;
            }
        }
        return true;
    }
}
~~~

Đây là ví dụ tối giản. Java có quy tắc identifier và keyword chi tiết hơn, bao gồm Unicode và contextual keywords. Một implementation production cần dùng API hoặc bảng keyword đúng phiên bản Java target; đồng thời cần kiểm tra collision theo scope và quy ước của file system.

### 17.2 Allocator theo scope

Không nên dùng một Set toàn cục cho mọi identifier. Hai method ở hai class khác nhau có thể cùng tên hợp lệ. Cần một allocator hoặc namespace riêng cho:

- Package.
- Class.
- Field.
- Method.
- Local variable.
- File.
- Database schema.

Một số target có quy tắc overload nên allocator method cần xét chữ ký, không chỉ chuỗi tên.

### 17.3 Dành trước tên synthetic

Trước khi cấp tên cho symbol người dùng, generator có thể đăng ký các tên helper sẽ tạo ra. Cách này tránh trường hợp field người dùng chiếm tên cần thiết cho runtime helper.

## 18. Khác biệt giữa các target language

Naming policy cần được thiết kế theo target.

### 18.1 Java

Quy ước thường dùng:

- Class và interface: PascalCase.
- Method và field: camelCase.
- Hằng số: UPPER_SNAKE_CASE.
- Package: chữ thường.

Java phân biệt hoa thường trong identifier. Từ khóa và một số tên đặc biệt cần được kiểm tra theo phiên bản target. Constructor có cùng tên class nên đổi tên class cũng ảnh hưởng constructor và các tham chiếu tạo object.

### 18.2 TypeScript

Quy ước thường dùng:

- Class và type: PascalCase.
- Function và variable: camelCase.
- Constant: thường camelCase hoặc UPPER_SNAKE_CASE theo convention project.
- JSON property: thường giữ tên external theo schema.

TypeScript có reserved words và contextual keywords; một số từ có thể được dùng ở vị trí identifier nhất định nhưng không nên giả định mọi vị trí đều hợp lệ.

### 18.3 Python

PEP 8 thường khuyến nghị:

- Class: CapWords.
- Function và variable: snake_case.
- Constant: UPPER_SNAKE_CASE.
- Module: tên ngắn, chữ thường, có thể dùng dấu gạch dưới.

Generator nên xem xét tên đặc biệt như __init__ và các method magic. Không nên tự tạo dunder name tùy tiện vì chúng có ý nghĩa đặc biệt trong Python.

### 18.4 SQL

SQL phụ thuộc dialect:

- Quy tắc quote identifier khác nhau.
- Tên có thể bị giới hạn độ dài.
- Case folding khác nhau giữa database.
- Một số từ khóa có thể trùng tên bảng hoặc cột.
- Schema và catalog có namespace riêng.

Generator cần một SqlDialectNamingPolicy thay vì giả định SQL là một target duy nhất.

### 18.5 Target có quy tắc khác nhau

Nếu cùng một DSL sinh ra nhiều target, hãy giữ một SymbolId và nhiều mapping:

~~~text
Symbol: field-42
Source: customer-id
Java: customerId
Python: customer_id
SQL: customer_id
JSON: customer_id
~~~

Không nên lấy tên Java làm nguồn để sinh SQL hoặc ngược lại. Mỗi mapping cần được tính từ symbol và policy tương ứng.

## 19. Tên và tương thích ngược

Thay đổi naming policy có thể thay đổi public API dù DSL source không đổi.

Ví dụ, phiên bản generator trước tạo:

~~~java
getCustomerID()
~~~

Phiên bản mới tạo:

~~~java
getCustomerId()
~~~

Đây có thể là thay đổi breaking đối với code gọi bên ngoài.

### 19.1 Phân biệt thay đổi nội bộ và công khai

Đổi tên local variable thường không ảnh hưởng API. Đổi tên class, method public, SQL column hoặc JSON property có thể ảnh hưởng hệ thống khác.

Generator nên biết visibility và external contract của symbol.

### 19.2 Migration map

Khi đổi tên công khai, có thể tạo mapping:

~~~text
Old: getCustomerID
New: getCustomerId
~~~

Tooling có thể sinh adapter, alias hoặc migration script nếu target hỗ trợ.

### 19.3 Pin naming policy

Project có thể pin version naming policy để lần generate sau không âm thầm đổi tên. Khi nâng phiên bản, generator có thể hiển thị diff tên và yêu cầu migration.

## 20. Tên trong code generation và incremental generation

Generator có thể chạy lại sau mỗi thay đổi nhỏ. Nếu tên sinh ra thay đổi không ổn định, diff sẽ lớn và khó review.

Ví dụ, generator dùng suffix tăng dần theo thứ tự duyệt. Khi thêm một symbol mới, nhiều tên cũ có thể bị đánh lại số.

Để giảm vấn đề:

- Dùng SymbolId ổn định.
- Lưu mapping của public symbols.
- Dùng deterministic allocation.
- Chỉ cấp lại tên cho symbol bị thay đổi khi có thể.
- Tách file generated khỏi file do người dùng chỉnh sửa.
- Không dùng tên tạm phụ thuộc thứ tự traversal.

### 20.1 Generated file và user code

Nếu người dùng cần mở rộng mã sinh ra, nên cung cấp partial class, extension method, subclass hoặc hook theo cơ chế target hỗ trợ. Tránh yêu cầu người dùng sửa trực tiếp generated file vì lần generate tiếp theo có thể ghi đè.

### 20.2 Mapping incremental

Một manifest có thể lưu:

~~~text
symbolId -> targetName
policyVersion
targetVersion
scopeId
~~~

Khi generate lại, allocator có thể tái sử dụng tên cũ nếu vẫn hợp lệ và không có collision mới.

### 20.3 Khi nào cần đổi tên?

Nếu người dùng đổi tên một symbol, generator cần cập nhật:

- Declaration.
- Các reference đã resolve.
- File hoặc package nếu tên ảnh hưởng path.
- Serialization mapping nếu contract thay đổi.
- Documentation hoặc metadata được sinh.

Không nên chỉ thay declaration mà bỏ sót các reference.

## 21. Xử lý tên không hợp lệ

Khi một tên không thể chuyển đổi an toàn, generator cần báo diagnostic rõ.

Ví dụ:

~~~text
entity "123-order" {
  field "customer name": String
}
~~~

Một diagnostic có thể nói:

~~~text
Generated type name is not a valid Java identifier.
Source name: "123-order"
Suggested name: "Order123"
~~~

### 21.1 Báo lỗi hay tự sửa?

Có thể tự sửa khi:

- Quy tắc chuyển đổi rõ.
- Không làm mất thông tin.
- Không tạo collision.
- Không ảnh hưởng API đã công bố.

Nên yêu cầu người dùng quyết định khi:

- Có nhiều cách chuyển đổi.
- Tên public đã được dùng bên ngoài.
- Transliteration có thể làm mất dấu hoặc ý nghĩa.
- Collision không thể giải quyết ổn định.

### 21.2 Source name và target name trong diagnostic

Diagnostic nên hiển thị cả hai:

~~~text
Source identifier: "class"
Target language: Java
Conflict: reserved keyword
Generated candidate: "class_"
~~~

Điều này giúp người dùng hiểu lỗi phát sinh ở bước sinh mã chứ không phải grammar DSL.

### 21.3 Không để target compiler là nơi phát hiện đầu tiên

Nếu generator biết tên target không hợp lệ, nó nên báo trước khi ghi file. Đợi target compiler báo lỗi sẽ khiến thông tin nguồn DSL khó truy nguyên hơn.

## 22. Kiểm thử quy tắc đặt tên

Naming policy cần được kiểm thử độc lập và qua toàn bộ pipeline sinh mã.

### 22.1 Unit test chuyển đổi convention

Ví dụ:

| Input | Policy | Expected |
|---|---|---|
| customer-profile | camelCase | customerProfile |
| customer_profile | PascalCase | CustomerProfile |
| HTTPServer | camelCase | httpServer |
| maxRetryCount | UPPER_SNAKE_CASE | MAX_RETRY_COUNT |
| created-at | snake_case | created_at |

Các test nên bao gồm chữ viết tắt, số, ký tự Unicode, chuỗi rỗng và dấu phân cách liên tiếp.

### 22.2 Test keyword

Với mỗi target, kiểm tra:

- Tên trùng reserved keyword.
- Contextual keyword.
- Tên đặc biệt do runtime dùng.
- Tên hợp lệ sau escape hoặc suffix.
- Candidate mới không trùng một symbol khác.

### 22.3 Test collision

- Hai tên nguồn chuẩn hóa thành cùng identifier.
- Collision do không phân biệt hoa thường.
- Collision do Unicode normalization.
- Collision với getter/setter/helper.
- Collision giữa generated file names.
- Collision trong hai scope khác nhau không bị báo nhầm.

### 22.4 Test deterministic

Sinh mã nhiều lần với cùng source và cấu hình rồi so sánh:

- Tên target.
- Nội dung file.
- Mapping table.
- Thứ tự cấp tên.

Có thể thay đổi thứ tự lưu symbol trong collection để xác nhận kết quả không phụ thuộc iteration order.

### 22.5 Test integration với target compiler

Một test có thể:

1. Tạo DSL fixture.
2. Sinh mã target.
3. Kiểm tra mapping.
4. Biên dịch mã target hoặc parse schema được sinh.
5. Xác nhận không có identifier invalid hoặc duplicate.

Việc target compile thành công không chứng minh tên có ý nghĩa tốt, nhưng giúp phát hiện vi phạm grammar và collision mà generator bỏ sót.

## 23. Những sai lầm thường gặp

### Dùng một quy tắc cho mọi loại tên

Class, field, method, package, file và SQL column có convention khác nhau.

**Cách khắc phục:** tách naming policy theo target và NameKind.

### Chỉ thay dấu gạch ngang bằng gạch dưới

Phép thay đơn giản có thể tạo tên bắt đầu bằng số, trùng keyword hoặc collision.

**Cách khắc phục:** tách từ, chuẩn hóa, validate và cấp tên trong scope.

### Không kiểm tra keyword

Tên hợp lệ trong DSL có thể trở thành từ khóa target.

**Cách khắc phục:** dùng keyword set theo phiên bản target và chính sách escape hoặc rename.

### Xử lý collision bằng suffix theo thứ tự không ổn định

Tên có thể thay đổi khi thêm symbol hoặc thay thứ tự duyệt.

**Cách khắc phục:** dùng identity ổn định, mapping lưu lại hoặc yêu cầu tên tường minh.

### So sánh tên không theo quy tắc target

Một target phân biệt hoa thường; file system hoặc database có thể không.

**Cách khắc phục:** collision comparer phải phù hợp với nơi tên được sử dụng.

### Dùng tên generated làm symbol identity

Đổi naming convention có thể làm mất liên kết giữa source và target.

**Cách khắc phục:** dùng SymbolId độc lập với tên hiển thị.

### Không giữ mapping external name

Đổi tên field Java có thể vô tình đổi JSON property hoặc database column.

**Cách khắc phục:** giữ mapping riêng cho từng target và contract bên ngoài.

### Tạo tên helper mà không dành trước

Tên người dùng có thể chiếm tên method hoặc field mà generator cần tạo.

**Cách khắc phục:** đăng ký tên synthetic trong cùng NameAllocator.

### Để target compiler phát hiện lỗi tên

Diagnostic từ target compiler có thể không chỉ ra chính xác DSL symbol gây ra vấn đề.

**Cách khắc phục:** kiểm tra identifier và collision trước khi ghi mã.

## 24. Quy trình thiết kế naming policy

Khi xây dựng code generator cho DSL, có thể thực hiện:

1. **Xác định target:** ngôn ngữ, database dialect, framework và phiên bản.
2. **Phân loại symbol:** type, field, method, constant, package, file, resource hoặc synthetic name.
3. **Giữ identity:** gán SymbolId và source range trước khi chuyển tên.
4. **Tách từ nguồn:** xử lý separator, chữ hoa, chữ số và acronym.
5. **Chuẩn hóa convention:** áp dụng camelCase, PascalCase, snake_case hoặc policy riêng.
6. **Kiểm tra identifier:** ký tự hợp lệ, Unicode, keyword và giới hạn target.
7. **Cấp tên theo scope:** phát hiện collision với symbol người dùng và helper do generator tạo.
8. **Giữ mapping:** lưu source name, target name, target kind và policy version.
9. **Kiểm tra tính ổn định:** bảo đảm cùng input/config tạo cùng output.
10. **Kiểm tra tương thích:** xem thay đổi tên public có ảnh hưởng API hoặc schema không.
11. **Tạo diagnostics:** giải thích source name, target conflict và lựa chọn sửa.
12. **Kiểm thử:** unit, collision, Unicode, deterministic và target integration.

Một naming policy tốt không chỉ tạo ra identifier hợp lệ. Nó còn giúp generated code dễ đọc, giữ mapping rõ ràng và hạn chế thay đổi không cần thiết qua các lần sinh mã.

## 25. Ví dụ tổng hợp

Giả sử DSL:

~~~text
module sales {
  entity customer-profile {
    field customer-id: Integer
    field class: String
    field created-at: Timestamp
  }
}
~~~

Target là Java và SQL.

### 25.1 Mapping Java

| Symbol nguồn | Vai trò | Tên Java |
|---|---|---|
| sales | Package segment | sales |
| customer-profile | Class | CustomerProfile |
| customer-id | Field | customerId |
| class | Field | class_ |
| created-at | Field | createdAt |

### 25.2 Mapping SQL

| Symbol nguồn | Vai trò | Tên SQL |
|---|---|---|
| customer-profile | Table | customer_profile |
| customer-id | Column | customer_id |
| class | Column | class_ hoặc identifier được quote |
| created-at | Column | created_at |

Tên SQL cuối cùng phụ thuộc dialect và quy tắc quote. Generator phải kiểm tra keyword, độ dài và collision theo database mục tiêu.

### 25.3 Mapping metadata

~~~text
SymbolId: entity-42
Source name: customer-profile
Java name: CustomerProfile
SQL name: customer_profile
Policy version: 1
~~~

Các field cũng có mapping riêng. Khi người dùng đổi customer-id thành customer-key, generator có thể xác định đúng symbol cần cập nhật và đánh giá tác động đến Java API, SQL schema và JSON contract.

## 26. Câu hỏi tự kiểm tra

1. Vì sao tên DSL không thể luôn được sao chép trực tiếp vào ngôn ngữ đích?
2. Phân biệt SymbolId, source name và generated name.
3. camelCase, PascalCase, snake_case và UPPER_SNAKE_CASE thường được dùng ở đâu?
4. Vì sao cần tách từ và xử lý acronym trước khi chuyển convention?
5. Reserved keyword và contextual keyword ảnh hưởng code generation như thế nào?
6. Collision có thể xuất hiện sau normalization trong những trường hợp nào?
7. Vì sao NameAllocator cần hoạt động theo scope và NameKind?
8. Tên synthetic do generator tạo có thể xung đột với tên người dùng ra sao?
9. Vì sao tên file và SQL identifier cần policy riêng?
10. Làm thế nào để giữ mapping giữa source symbol và nhiều target language?
11. Tại sao suffix theo thứ tự có thể làm generated code không ổn định?
12. Khi nào cần yêu cầu người dùng cung cấp targetName tường minh?
13. Naming policy version ảnh hưởng tương thích ngược như thế nào?
14. Những test nào cần có cho Unicode, keyword, collision và tính xác định?

Quy tắc đặt tên là một phần của hợp đồng code generation. Khi generator phân biệt identity với cách viết tên, áp dụng policy theo target và vai trò symbol, kiểm tra keyword cùng collision, đồng thời giữ mapping ổn định, mã được sinh ra sẽ dễ đọc, hợp lệ và có thể duy trì qua nhiều phiên bản.
