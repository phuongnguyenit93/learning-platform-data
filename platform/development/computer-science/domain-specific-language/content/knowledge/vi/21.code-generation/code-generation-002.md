# Ánh xạ mô hình sang mã

Trong một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), người dùng thường mô tả hệ thống bằng các khái niệm gần với miền nghiệp vụ: thực thể, thuộc tính, quan hệ, quy trình, quy tắc hoặc sự kiện. Máy tính cần chuyển những mô tả đó thành cấu trúc có thể thực thi hoặc tích hợp với phần mềm hiện có. **Ánh xạ mô hình sang mã (model-to-code mapping)** là quá trình xác định cách mỗi thành phần của mô hình được biểu diễn trong ngôn ngữ lập trình hoặc định dạng đích.

Ví dụ, một mô hình DSL khai báo thực thể Customer với các thuộc tính id và name có thể được chuyển thành một lớp Java. Một quan hệ một-nhiều giữa Customer và Order có thể được chuyển thành trường tham chiếu hoặc collection. Một ràng buộc miền có thể trở thành đoạn kiểm tra hợp lệ, annotation hoặc metadata cho framework.

Ánh xạ không đơn giản là thay tên từ mô hình bằng tên trong mã nguồn. Nó cần bảo toàn ý nghĩa của mô hình, xử lý kiểu dữ liệu, quan hệ, phạm vi, ràng buộc và phụ thuộc, đồng thời tạo mã dễ đọc, ổn định và có thể bảo trì.

Bài học này trình bày các nguyên tắc và kỹ thuật xây dựng ánh xạ mô hình sang mã cho DSL, từ việc chọn nền tảng đích, định nghĩa quy tắc ánh xạ và thiết kế template đến traceability, tái sinh mã, kiểm thử và quản lý thay đổi.

## 1. Ánh xạ mô hình sang mã là gì?

Mô hình (model) là biểu diễn có cấu trúc của hệ thống hoặc miền nghiệp vụ. Mô hình có thể được tạo từ DSL sau các bước parse, phân giải tên và kiểm tra ngữ nghĩa. Mã đích (target code) là đầu ra được tạo ra theo một ngôn ngữ hoặc nền tảng cụ thể, chẳng hạn Java, Kotlin, TypeScript, SQL, JSON Schema hoặc cấu hình cho một framework.

Ánh xạ mô hình sang mã xác định quan hệ giữa hai phía:

- Thành phần mô hình nào được chuyển thành thành phần đích nào.
- Giá trị và kiểu dữ liệu được chuyển đổi ra sao.
- Quan hệ giữa các thành phần được biểu diễn thế nào.
- Ràng buộc nào trở thành mã kiểm tra, annotation hay metadata.
- Thành phần nào chỉ tồn tại trong mô hình và không cần sinh mã.
- Những quy tắc nào được áp dụng cho tên, package, file và cấu trúc thư mục.

Ví dụ, mô hình:

~~~text
entity Customer {
  property id: CustomerId
  property name: String
  property active: Boolean = true
}
~~~

có thể được ánh xạ thành Java:

~~~java
public class Customer {
    private CustomerId id;
    private String name;
    private boolean active = true;

    public CustomerId getId() {
        return id;
    }

    public void setId(CustomerId id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Đây là một chính sách ánh xạ minh họa. DSL khác có thể sinh Java record, Kotlin data class, TypeScript interface hoặc cấu trúc khác. Một mô hình không nhất thiết chỉ có một cách biểu diễn mã.

### 1.1. Ánh xạ khác với dịch cú pháp

Parser chuyển văn bản DSL thành AST hoặc mô hình. Ánh xạ mô hình sang mã sử dụng mô hình đã được hiểu về mặt ngữ nghĩa để tạo đầu ra.

~~~text
Văn bản DSL
    |
    v
Lexer và Parser
    |
    v
AST
    |
    v
Phân giải tên và kiểm tra ngữ nghĩa
    |
    v
Mô hình đã kiểm tra
    |
    v
Ánh xạ mô hình sang mã
    |
    v
Mã nguồn hoặc tài nguyên đích
~~~

Ví dụ, parser có thể nhận diện khai báo thuộc tính tên CustomerId. Bước phân giải tên xác định CustomerId là kiểu được khai báo ở mô-đun nào. Bước kiểm tra ngữ nghĩa xác minh kiểu này tồn tại và được dùng hợp lệ. Sau đó, code generator quyết định kiểu đích tương ứng là lớp CustomerId, UUID hoặc một kiểu khác theo cấu hình ánh xạ.

Nếu sinh mã trực tiếp từ chuỗi token, generator dễ bỏ qua thông tin đã được phân giải, tạo tên sai hoặc sinh cấu trúc không hợp lệ.

### 1.2. Mô hình nguồn và mô hình đích

Trong chuyển đổi mô hình (model transformation), có thể phân biệt:

- **Source model:** mô hình DSL đầu vào, mô tả khái niệm miền.
- **Target model:** mô hình trung gian hoặc cấu trúc biểu diễn gần với nền tảng đích.
- **Target text:** văn bản mã nguồn được xuất ra từ target model hoặc trực tiếp từ source model.

Một pipeline có thể chuyển đổi nhiều giai đoạn:

~~~text
Domain Model
    |
    v
Platform-independent Model
    |
    v
Java-oriented Model
    |
    v
Java Source Files
~~~

Ví dụ, một Entity trong mô hình miền được chuyển thành Class trong mô hình hướng Java, rồi được render thành tệp .java. Cách chia giai đoạn giúp tách ý nghĩa nghiệp vụ khỏi chi tiết của ngôn ngữ đích.

## 2. Mục tiêu của một phép ánh xạ tốt

Một phép ánh xạ cần tạo ra mã đáp ứng yêu cầu kỹ thuật và giữ được ý nghĩa của mô hình.

### 2.1. Bảo toàn ngữ nghĩa

Nếu mô hình khai báo một thuộc tính bắt buộc, mã đích phải thể hiện hoặc thực thi được tính bắt buộc theo cách phù hợp. Nếu mô hình khai báo quan hệ một-nhiều, mã đích không nên vô tình tạo quan hệ một-một.

Bảo toàn ngữ nghĩa có thể cần nhiều cơ chế:

- Kiểu dữ liệu tương ứng.
- Ràng buộc hoặc validation.
- Quan hệ giữa lớp hoặc bảng.
- Giá trị mặc định.
- Quy tắc truy cập.
- Thứ tự thực thi.
- Hành vi lỗi.

Không phải mọi đặc điểm mô hình đều có biểu diễn trực tiếp trong ngôn ngữ đích. Khi đó, cần sinh thêm mã hỗ trợ hoặc metadata.

### 2.2. Mã đích hợp lệ và có thể biên dịch

Đầu ra cần tuân theo cú pháp và quy tắc của nền tảng đích. Ví dụ, tên lớp Java phải hợp lệ, package phải đúng, kiểu được tham chiếu phải tồn tại và import phải được tạo phù hợp.

Một generator không nên chỉ tạo văn bản trông có vẻ hợp lý. Cần xác định hợp đồng đầu ra: tệp nào được sinh, namespace nào được dùng, runtime nào được yêu cầu và cấu hình nào phải có.

### 2.3. Tính nhất quán

Cùng một khái niệm trong mô hình nên được ánh xạ nhất quán. Nếu kiểu String ở một thuộc tính được chuyển thành java.lang.String, các thuộc tính String khác cũng nên tuân theo chính sách đó.

Tính nhất quán còn áp dụng cho:

- Quy tắc đặt tên.
- Nullability.
- Collections.
- Visibility.
- Exception handling.
- Annotation.
- Cách biểu diễn ràng buộc.

Nếu cùng một cấu trúc được sinh theo hai cách khác nhau tùy thứ tự duyệt hoặc trạng thái runtime, đầu ra sẽ khó hiểu và khó bảo trì.

### 2.4. Tính tái lập

Cùng một mô hình, cùng phiên bản generator và cùng cấu hình nên tạo ra đầu ra giống nhau. Đây là tính xác định (determinism).

Tính tái lập giúp:

- So sánh thay đổi bằng version control.
- Tái tạo bản build.
- Điều tra lỗi.
- Kiểm tra đầu ra giữa các phiên bản.
- Tránh thay đổi không cần thiết trong pull request.

Không nên để timestamp hiện tại, thứ tự phần tử không ổn định hoặc đường dẫn máy cục bộ làm thay đổi mã sinh ra nếu không có lý do rõ ràng.

### 2.5. Khả năng bảo trì

Mã sinh ra thường được người dùng đọc, debug hoặc tích hợp với mã thủ công. Generator nên tạo cấu trúc dễ đọc, tên có ý nghĩa, định dạng ổn định và thông báo nguồn gốc.

Mã ngắn nhất không phải lúc nào cũng là mã tốt nhất. Một số dòng getter, setter hoặc validation có thể làm đầu ra dài hơn nhưng rõ ràng và dễ debug hơn.

## 3. Xác định nền tảng và hợp đồng đích

Trước khi viết mapping rule, cần xác định generator tạo ra loại đầu ra nào và ai sẽ sử dụng đầu ra đó.

Các đích thường gặp:

| Nền tảng đích | Đầu ra có thể sinh |
| --- | --- |
| Java | Class, record, enum, annotation, package |
| Kotlin | Class, data class, enum class, extension |
| TypeScript | Interface, type, class, enum |
| SQL | Table, column, constraint, index, view |
| JSON Schema | Object schema, property, required, reference |
| OpenAPI | Schema, operation, parameter, response |
| Cấu hình | YAML, JSON, XML hoặc file cấu hình framework |

Một DSL có thể hỗ trợ nhiều target. Ví dụ cùng mô hình Order có thể sinh Java domain class và SQL schema. Tuy nhiên, hai target có quy tắc biểu diễn khác nhau; không nên giả định mapping Java có thể dùng nguyên xi cho SQL.

### 3.1. Xác định phạm vi sinh mã

Cần quyết định generator tạo:

- Chỉ lớp miền.
- DTO và API model.
- Repository hoặc DAO.
- Service hoặc workflow handler.
- Database schema.
- Validation code.
- Serialization metadata.
- Cấu hình và tài liệu.

Không nên sinh mọi thứ chỉ vì mô hình có thể cung cấp thông tin. Phạm vi đầu ra nên phản ánh mục tiêu thực tế và có thể được điều khiển bằng cấu hình hoặc profile.

### 3.2. Xác định phiên bản ngôn ngữ đích

Một generator Java cần biết target Java version. Cú pháp record, sealed class, pattern matching hoặc một số API chỉ có ở phiên bản nhất định.

Ví dụ, một Entity đơn giản có thể được sinh thành class truyền thống cho Java cũ hoặc record cho phiên bản mới. Mapping rule phải kiểm tra cấu hình target và không tạo cú pháp vượt quá phiên bản được yêu cầu.

### 3.3. Xác định runtime contract

Một số cấu trúc sinh ra cần thư viện runtime:

- Annotation của validation framework.
- Base class hoặc interface chung.
- Kiểu dữ liệu miền.
- Helper để xử lý quan hệ.
- API serialization.
- Runtime cho workflow.

Generator cần ghi rõ dependency cần thiết và cách người dùng tích hợp chúng. Nếu mã sinh ra tham chiếu một lớp helper không tồn tại, đầu ra không thể sử dụng độc lập.

## 4. Thiết kế quy tắc ánh xạ

Quy tắc ánh xạ (mapping rule) mô tả cách một loại phần tử nguồn được chuyển thành một hoặc nhiều phần tử đích.

Một quy tắc khái quát:

~~~text
Source element
    |
    | điều kiện áp dụng
    v
Mapping rule
    |
    | chuyển đổi thuộc tính và quan hệ
    v
Target element(s)
~~~

Ví dụ:

~~~text
Rule: EntityToJavaClass

Input:
  Entity(name, properties)

Output:
  Java class
  - class name from Entity.name
  - one field per Property
  - constructor or factory
  - accessors according to policy
~~~

Một mapping rule nên xác định:

- Loại phần tử nguồn.
- Điều kiện áp dụng.
- Thông tin được đọc từ mô hình.
- Cách chuyển tên và kiểu.
- Các phần tử đích được tạo.
- Phụ thuộc cần có.
- Hành vi khi thông tin thiếu hoặc không hỗ trợ.
- Vị trí nguồn dùng cho traceability.

### 4.1. Ánh xạ một-một

Một phần tử nguồn tạo một phần tử đích.

Ví dụ:

~~~text
enum OrderStatus {
  PENDING
  PAID
  CANCELLED
}
~~~

có thể tạo một enum Java:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

### 4.2. Ánh xạ một-nhiều

Một phần tử nguồn có thể tạo nhiều phần tử đích.

Một Entity có thể tạo:

- Tệp Java class.
- Tệp builder.
- Tệp repository interface.
- Tệp mapper.
- Tệp schema tương ứng.

Việc tạo nhiều tệp cần được mô tả trong mapping rule hoặc một generator component rõ ràng. Tránh để một template âm thầm ghi nhiều tệp vào các đường dẫn không được quản lý.

### 4.3. Ánh xạ nhiều-một

Nhiều phần tử nguồn có thể cùng đóng góp vào một phần tử đích.

Ví dụ, nhiều khai báo property trong một entity cùng tạo ra nội dung của một Java class. Nhiều constraint có thể được tổng hợp thành một phương thức validation hoặc một tập annotation trên cùng trường.

Trong trường hợp này, thứ tự tổng hợp phải ổn định và quy tắc xử lý xung đột phải rõ.

### 4.4. Phần tử không sinh mã

Không phải mọi thành phần mô hình đều cần trở thành mã đích. Một comment mô tả, nhóm hiển thị trong editor hoặc metadata chỉ phục vụ tài liệu có thể không sinh mã thực thi.

Cũng có những phần tử được chuyển thành thông tin trong file phụ, chẳng hạn manifest, schema hoặc tài liệu. Cần xác định rõ để tránh bỏ sót hoặc sinh mã không cần thiết.

## 5. Ánh xạ kiểu dữ liệu

Ánh xạ kiểu (type mapping) là một trong những phần quan trọng nhất vì kiểu nguồn quyết định biểu diễn, kiểm tra và hành vi của dữ liệu đích.

Ví dụ một bảng ánh xạ cơ bản sang Java:

| Kiểu DSL | Kiểu Java có thể dùng | Lưu ý |
| --- | --- | --- |
| Boolean | boolean hoặc Boolean | Primitive không nhận null |
| Integer | int hoặc Integer | Cần xác định miền giá trị |
| Long | long hoặc Long | Phù hợp số nguyên lớn hơn |
| Decimal | BigDecimal | Giữ độ chính xác thập phân |
| String | String | Có thể thêm giới hạn độ dài |
| Date | LocalDate | Không chứa giờ hoặc múi giờ |
| Instant | Instant | Đại diện thời điểm tuyệt đối |
| UUID | UUID | Định danh chuẩn |
| Binary | byte[] | Cần quy định serialization |
| Enum | enum tương ứng | Giá trị phải được sinh hoặc tham chiếu |

Bảng chỉ là chính sách minh họa. DSL có thể định nghĩa kiểu miền riêng và mapping tùy nền tảng.

### 5.1. Primitive và wrapper

Trong Java, boolean, int và long là primitive, còn Boolean, Integer và Long là reference type.

Primitive thường có hiệu năng và ngữ nghĩa mặc định đơn giản, nhưng không biểu diễn được null. Wrapper có thể nhận null và sử dụng trong generic.

Nếu thuộc tính DSL cho phép vắng mặt hoặc null, ánh xạ sang primitive có thể làm mất ngữ nghĩa. Generator cần xem xét nullability và multiplicity trước khi chọn kiểu Java.

### 5.2. Số thập phân và độ chính xác

Nếu DSL có kiểu Decimal dùng cho tiền tệ hoặc giá trị cần độ chính xác, BigDecimal thường phù hợp hơn double.

Ánh xạ Decimal sang double có thể gây sai số dấu phẩy động. Ví dụ, một số thập phân không biểu diễn chính xác trong hệ nhị phân có thể tạo kết quả tính toán gần đúng.

Nếu mô hình có precision và scale, generator có thể sinh metadata hoặc validation tương ứng:

~~~text
property unitPrice: Decimal(precision = 12, scale = 2)
~~~

Ánh xạ sang BigDecimal cần giữ các ràng buộc precision và scale ở lớp validation hoặc schema đích.

### 5.3. Ngày, giờ và múi giờ

Không nên ánh xạ mọi kiểu thời gian thành một kiểu duy nhất.

- Date có thể thành LocalDate.
- Time có thể thành LocalTime.
- LocalDateTime không chứa múi giờ.
- Instant biểu diễn một thời điểm trên trục thời gian.
- ZonedDateTime giữ cả múi giờ.

Chọn sai kiểu có thể làm mất thông tin hoặc gây lệch thời gian. DSL cần phân biệt ngày nghiệp vụ với timestamp của sự kiện.

### 5.4. Kiểu miền tùy chỉnh

Một kiểu CustomerId có thể được ánh xạ thành UUID, String hoặc một value object riêng:

~~~java
public record CustomerId(UUID value) {}
~~~

Value object giúp thể hiện ý nghĩa miền và tránh nhầm CustomerId với OrderId dù cả hai có cùng biểu diễn cơ bản. Đổi lại, generator cần sinh hoặc tham chiếu kiểu wrapper và có quy tắc serialization.

## 6. Ánh xạ thuộc tính, nullability và giá trị mặc định

Một thuộc tính trong mô hình có thể có tên, kiểu, tính tùy chọn, multiplicity, default value và constraint.

Ví dụ:

~~~text
entity Customer {
  property id: CustomerId required
  property nickname: String optional
  property active: Boolean = true
}
~~~

Generator cần quyết định cách thể hiện từng đặc điểm.

### 6.1. Tính bắt buộc và tính tùy chọn

Tính bắt buộc có thể được biểu diễn bằng:

- Kiểu reference không nullable.
- Primitive nếu kiểu phù hợp.
- Annotation validation.
- Constructor bắt buộc tham số.
- Constraint ở schema hoặc database.

Không nên giả định chỉ một annotation là đủ. Nếu runtime không chạy validation, annotation có thể chỉ là metadata.

### 6.2. Nullability

Nếu DSL phân biệt absent, null và giá trị hiện diện, mapping cần bảo toàn khác biệt đó khi target hỗ trợ.

Ví dụ, thuộc tính optional String có thể ánh xạ thành String nullable, Optional<String> hoặc một wrapper trạng thái riêng. Mỗi lựa chọn có API khác nhau.

Không nên dùng Optional làm kiểu trường trong mọi trường hợp mà không cân nhắc convention của nền tảng. Có thể dùng Optional ở API trả về nhưng giữ nullable field trong model nội bộ.

### 6.3. Giá trị mặc định

Mặc định tĩnh có thể được sinh thành initializer:

~~~text
property active: Boolean = true
~~~

~~~java
private boolean active = true;
~~~

Mặc định động như thời điểm hiện tại có thể cần được đánh giá khi tạo instance:

~~~text
property createdAt: Instant = now()
~~~

Generator cần xác định biểu thức được tính khi khởi tạo, trong constructor, qua factory hay bởi runtime. Không nên biến một biểu thức động thành hằng số tại thời điểm sinh mã.

### 6.4. Constraint và validation

Một thuộc tính có giới hạn miền:

~~~text
property age: Integer
constraint age >= 0
constraint age <= 130
~~~

có thể sinh annotation hoặc validation code:

~~~java
if (age < 0 || age > 130) {
    throw new IllegalArgumentException("age is out of range");
}
~~~

Thông báo lỗi và mã lỗi có thể được tạo từ metadata của constraint. Nếu DSL hỗ trợ nhiều locale, nội dung validation nên dùng cơ chế diagnostic hoặc message catalog thống nhất.

## 7. Ánh xạ entity sang class hoặc cấu trúc dữ liệu

Entity thường là thành phần trung tâm của DSL mô hình miền. Một entity có thể được ánh xạ thành class, record, struct, interface hoặc table tùy target.

Ví dụ:

~~~text
entity Product {
  property sku: String
  property name: String
  property price: Decimal
}
~~~

Java class:

~~~java
public class Product {
    private String sku;
    private String name;
    private BigDecimal price;
}
~~~

TypeScript interface:

~~~typescript
export interface Product {
  sku: string;
  name: string;
  price: Decimal;
}
~~~

SQL table:

~~~sql
CREATE TABLE Product (
    sku VARCHAR(100),
    name VARCHAR(255),
    price DECIMAL(12, 2)
);
~~~

Cùng một entity nhưng biểu diễn đích khác nhau. Vì vậy, mapping cần phụ thuộc target profile và mục tiêu sử dụng.

### 7.1. Class hay record?

Java class có thể hỗ trợ trạng thái thay đổi, kế thừa, method và constructor linh hoạt. Java record phù hợp với dữ liệu bất biến, có constructor canonical và accessor được sinh tự động.

Một DSL có thể dùng metadata để chọn:

~~~text
entity Customer immutable {
  property id: CustomerId
  property name: String
}
~~~

Nếu immutable, generator có thể chọn record khi target Java version hỗ trợ. Nếu entity có lifecycle hoặc quan hệ hai chiều thay đổi được, class có thể phù hợp hơn.

### 7.2. Constructor và factory

Generator cần quyết định cách tạo đối tượng:

- Constructor nhận tất cả thuộc tính bắt buộc.
- Constructor rỗng kết hợp setter.
- Builder.
- Factory method.
- Static factory có validation.

Chính sách này ảnh hưởng API được sinh và khả năng tương thích giữa các phiên bản. Nếu thay constructor signature khi thêm thuộc tính bắt buộc, mã thủ công gọi constructor có thể không biên dịch nữa.

### 7.3. Getter, setter và encapsulation

Một generator có thể sinh getter/setter cho mọi property, chỉ getter cho thuộc tính bất biến hoặc method miền cho phép thay đổi trạng thái.

Không nên mặc định mọi property đều có setter công khai. Quy tắc ghi (writable), visibility và invariant của mô hình cần được phản ánh trong API đích.

## 8. Ánh xạ quan hệ giữa các entity

Quan hệ trong mô hình thường cần biểu diễn bằng tham chiếu, collection, khóa ngoại hoặc bảng liên kết.

Ví dụ:

~~~text
entity Customer {
  property id: CustomerId
}

entity Order {
  property id: OrderId
  property customer: Customer
}

relation places {
  from Customer [1]
  to Order [0..*]
}
~~~

Quan hệ một-nhiều có thể được biểu diễn trong Java:

~~~java
public class Customer {
    private List<Order> orders;
}

public class Order {
    private Customer customer;
}
~~~

Trong SQL, nó có thể trở thành khóa ngoại trong bảng Order:

~~~sql
CREATE TABLE Customer (
    id UUID PRIMARY KEY
);

CREATE TABLE Orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES Customer(id)
);
~~~

### 8.1. Multiplicity

Multiplicity xác định số lượng liên kết hợp lệ:

| Multiplicity | Ý nghĩa | Biểu diễn Java có thể dùng |
| --- | --- | --- |
| 1 | Chính xác một | Tham chiếu không nullable |
| 0..1 | Không hoặc một | Tham chiếu nullable hoặc Optional ở API |
| 0..* | Không hoặc nhiều | List hoặc Set |
| 1..* | Ít nhất một | Collection kèm validation |
| n..m | Từ n đến m | Collection kèm kiểm tra kích thước |

Collection type không tự bảo đảm multiplicity. Một List có thể rỗng dù mô hình yêu cầu ít nhất một phần tử. Generator cần sinh validation hoặc dùng abstraction có kiểm soát.

### 8.2. Quan hệ một-một

Có thể sinh một trường tham chiếu ở cả hai phía hoặc chỉ một phía tùy navigation trong mô hình.

Nếu cả hai phía được sinh, cần quản lý đồng bộ hai tham chiếu. Việc gán A.b không tự động bảo đảm B.a được cập nhật nếu runtime không có helper hoặc method quản lý quan hệ.

### 8.3. Quan hệ nhiều-nhiều

Trong Java, quan hệ nhiều-nhiều có thể dùng Set hoặc List ở hai phía. Trong SQL, thường cần bảng liên kết chứa hai khóa ngoại.

Nếu quan hệ có thuộc tính riêng như ngày tham gia hoặc vai trò, nên ánh xạ nó thành entity trung gian thay vì một collection đơn giản.

~~~text
relation Membership {
  from User [0..*]
  to Group [0..*]
  property joinedAt: Instant
  property role: MembershipRole
}
~~~

Có thể sinh class Membership và bảng Membership riêng để giữ dữ liệu của chính quan hệ.

### 8.4. Quan hệ có hướng và navigation

Một quan hệ trong mô hình có thể chỉ cho phép đi từ nguồn đến đích. Không nên tự sinh trường ngược nếu mô hình không yêu cầu hoặc target profile không quy định.

Navigation hai chiều làm API tiện hơn nhưng tăng độ phức tạp của trạng thái và serialization. Quy tắc cần được xác định rõ.

## 9. Ánh xạ kế thừa, interface và composition

Nếu mô hình hỗ trợ kế thừa, generator cần quyết định cách chuyển quan hệ generalization sang target.

Ví dụ:

~~~text
entity Person {
  property name: String
}

entity Employee extends Person {
  property employeeCode: String
}
~~~

Java:

~~~java
public class Person {
    protected String name;
}

public class Employee extends Person {
    private String employeeCode;
}
~~~

### 9.1. Kế thừa đơn

Nếu target hỗ trợ kế thừa đơn, một entity có thể mở rộng class tương ứng với kiểu cha. Cần xác định visibility của thành viên, constructor và method được kế thừa.

### 9.2. Đa kế thừa và interface

Nếu mô hình cho phép một kiểu kế thừa nhiều kiểu, nhưng Java class chỉ có một superclass, generator có thể:

- Chuyển các kiểu phụ thành interface.
- Dùng composition.
- Tạo adapter.
- Từ chối mô hình không thể biểu diễn trực tiếp.
- Áp dụng một chiến lược mapping được cấu hình.

Không nên âm thầm bỏ qua một quan hệ kế thừa chỉ vì target không hỗ trợ.

### 9.3. Composition

Một quan hệ whole-part có thể được biểu diễn bằng trường chứa đối tượng hoặc collection. Nếu vòng đời phần con phụ thuộc phần cha, generator hoặc runtime có thể cần quản lý cascade, ownership và xóa dữ liệu.

Composition trong mô hình không tự động tương đương với một trường Java. Cần xác định những quy tắc vòng đời nào phải được thực thi.

## 10. Ánh xạ enum, constraint và metadata

Các thành phần không phải entity cũng cần quy tắc ánh xạ riêng.

### 10.1. Enum

Mô hình:

~~~text
enum OrderStatus {
  PENDING
  PAID
  CANCELLED
}
~~~

Java:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Nếu DSL cho phép tên hiển thị khác tên kỹ thuật, generator có thể thêm trường hoặc annotation để giữ cả hai. Không nên dùng nhãn dịch làm giá trị enum ổn định nếu dữ liệu được lưu hoặc trao đổi giữa hệ thống.

### 10.2. Constraint

Constraint có thể được ánh xạ thành:

- Annotation validation.
- Method kiểm tra.
- Database CHECK constraint.
- Assertion trong test.
- Metadata cho runtime.

Ví dụ:

~~~text
constraint PositivePrice {
  require Product.price > 0
}
~~~

SQL có thể sinh:

~~~sql
CHECK (price > 0)
~~~

Java có thể sinh validation method. Hai đầu ra cần cùng thể hiện điều kiện, nhưng cơ chế thực thi và thông báo lỗi có thể khác nhau.

### 10.3. Metadata và annotation

Một số thông tin mô hình chỉ cần xuất hiện dưới dạng metadata:

~~~text
entity Customer {
  annotation tableName = "customers"
  property id: CustomerId
}
~~~

Java có thể sinh annotation của persistence framework; SQL generator có thể dùng tableName để đặt tên bảng. Annotation cụ thể phụ thuộc framework đích và không nên bị gắn cứng vào mô hình miền nếu muốn hỗ trợ nhiều target.

## 11. Quy tắc đặt tên và namespace

Tên trong DSL có thể không tuân theo quy tắc identifier của ngôn ngữ đích. Generator cần một chính sách chuyển tên có thể dự đoán.

Ví dụ:

| Tên DSL | Java class | Java property | SQL column |
| --- | --- | --- | --- |
| customer | Customer | customer | customer |
| order-item | OrderItem | orderItem | order_item |
| created_at | CreatedAt | createdAt | created_at |
| URLConfig | URLConfig | urlConfig | url_config |

Bảng chỉ là ví dụ. Chính sách cần quy định cách xử lý chữ hoa, dấu gạch nối, từ viết tắt và từ khóa dành riêng.

### 11.1. Chuẩn hóa tên

Có thể dùng các quy tắc:

- PascalCase cho class và enum.
- camelCase cho field và method.
- snake_case cho SQL table hoặc column.
- Package viết thường.
- Hậu tố hoặc tiền tố cho tên sinh tự động khi cần tránh xung đột.

Không nên biến đổi tên tùy ý ở nhiều template. Hãy có một thành phần NameMapper dùng chung để mọi mapping rule tạo tên nhất quán.

### 11.2. Từ khóa dành riêng

Nếu mô hình có property tên class hoặc package, generator Java không thể dùng trực tiếp tên đó trong mọi vị trí.

Có thể áp dụng quy tắc escape hoặc đổi tên có hậu tố:

~~~text
property class: String
~~~

thành:

~~~java
private String classValue;
~~~

Nhưng việc đổi tên phải được ghi nhận để người dùng hiểu và mapping serialization vẫn có thể giữ tên nguồn nếu cần.

### 11.3. Tên trùng sau chuẩn hóa

Hai tên nguồn khác nhau có thể chuyển thành cùng một tên đích. Ví dụ order-item và order_item có thể cùng thành orderItem.

Generator cần phát hiện xung đột sau khi chuẩn hóa. Không nên để compiler đích là nơi đầu tiên phát hiện hai trường trùng tên.

### 11.4. Package và namespace

Namespace DSL có thể được chuyển thành package Java hoặc module TypeScript. Cần quy định ánh xạ đường dẫn và cách xử lý tên đầy đủ.

Ví dụ:

~~~text
namespace sales.orders {
  entity Order { ... }
}
~~~

có thể sinh vào package:

~~~text
com.example.sales.orders
~~~

Phần tiền tố package có thể được cấu hình theo dự án. Không nên suy ra package từ đường dẫn máy cục bộ.

## 12. Tham chiếu, import và phụ thuộc giữa các phần tử

Một phần tử đích có thể tham chiếu kiểu hoặc thành phần được sinh từ phần tử nguồn khác.

Ví dụ, Order có property customer kiểu Customer. Nếu hai entity được sinh thành hai class, tệp Order.java cần import hoặc tham chiếu Customer.

Generator cần:

1. Phân giải tham chiếu trong mô hình.
2. Xác định kiểu đích của từng tham chiếu.
3. Tính package và namespace đích.
4. Thêm import cần thiết.
5. Phát hiện phụ thuộc vòng hoặc cấu trúc không hỗ trợ.
6. Sắp xếp import ổn định.

### 12.1. Không dựa vào thứ tự khai báo nguồn

Nếu Order được khai báo trước Customer, generator vẫn cần tạo tham chiếu hợp lệ đến Customer. Tất cả symbol và target name nên được thu thập trước khi render các tệp phụ thuộc.

### 12.2. Đồ thị phụ thuộc

Có thể mô hình hóa phụ thuộc bằng đồ thị:

~~~text
Order.java
   |
   +----> Customer.java
   |
   +----> OrderStatus.java

Customer.java
   |
   +----> CustomerId.java
~~~

Topological sort có thể giúp xác định thứ tự sinh hoặc biên dịch khi có phụ thuộc một chiều. Một số ngôn ngữ cho phép tham chiếu vòng giữa các class; khi đó, thứ tự file không nhất thiết phải phá vòng, nhưng generator vẫn cần nhận diện các chu trình có vấn đề như khởi tạo tĩnh phụ thuộc vòng.

### 12.3. Import không dùng và import trùng

Khi nhiều mapping rule thêm import, generator nên hợp nhất và sắp xếp chúng. Import không dùng có thể làm code kém sạch hoặc gây lỗi trong một số target. Có thể dùng target model để theo dõi kiểu thực sự được tham chiếu trước khi render import.

## 13. Ánh xạ hành vi và biểu thức

Ngoài cấu trúc dữ liệu, DSL có thể mô tả hành vi như operation, workflow, rule hoặc biểu thức. Những thành phần này cần được chuyển thành method, function, control flow hoặc cấu hình thực thi.

Ví dụ:

~~~text
operation calculateTotal(order: Order): Decimal {
  return order.unitPrice * order.quantity
}
~~~

Java có thể được sinh:

~~~java
public BigDecimal calculateTotal(Order order) {
    return order.getUnitPrice()
        .multiply(BigDecimal.valueOf(order.getQuantity()));
}
~~~

### 13.1. Ánh xạ biểu thức

Mỗi loại biểu thức cần mapping riêng:

| Biểu thức DSL | Biểu diễn đích có thể dùng |
| --- | --- |
| Số nguyên | Literal số nguyên |
| Chuỗi | String literal đã escape |
| Phép cộng | Toán tử + hoặc method phù hợp kiểu |
| Phép nhân Decimal | BigDecimal.multiply |
| So sánh | Toán tử hoặc comparator |
| Truy cập thuộc tính | Getter hoặc field theo target |
| Lời gọi action | Method hoặc runtime invocation |
| Biểu thức điều kiện | Boolean expression |

Không phải phép toán có cùng ký hiệu đều có cùng ngữ nghĩa trên mọi kiểu. Ví dụ, phép cộng Decimal trong Java BigDecimal cần method multiply/add thay vì toán tử số học thông thường.

### 13.2. Escape literal

Chuỗi trong DSL cần được escape đúng quy tắc ngôn ngữ đích. Nếu người dùng cung cấp chuỗi chứa dấu nháy, xuống dòng hoặc dấu gạch chéo ngược, generator phải tạo literal hợp lệ.

Không nên nối chuỗi nguồn trực tiếp vào mã đích. Dùng một literal serializer chuyên biệt cho từng target.

### 13.3. Control flow

Một workflow có điều kiện và vòng lặp có thể được chuyển thành if, switch, loop hoặc state machine. Nếu DSL có semantics khác với ngôn ngữ đích, generator cần sinh helper hoặc runtime để giữ đúng hành vi.

Ví dụ, một bước retry trong workflow có thể yêu cầu backoff, giới hạn số lần thử và xử lý lỗi. Chỉ chuyển nó thành vòng while đơn giản có thể làm mất ngữ nghĩa retry.

### 13.4. Action và tác động phụ

Action gọi dịch vụ bên ngoài thường cần runtime adapter hoặc dependency injection. Mapping nên tạo lời gọi qua interface đã định nghĩa, không nhúng URL, credential hoặc cấu hình môi trường vào mã nguồn sinh tự động.

## 14. Mô hình trung gian và các giai đoạn chuyển đổi

Với DSL lớn hoặc nhiều target, chuyển trực tiếp từ source model sang text có thể làm mapping rule phức tạp. Một mô hình trung gian (intermediate model) giúp tách các quyết định.

Ví dụ:

~~~text
Domain Entity
    |
    v
Target-neutral Model
    |
    v
Java Target Model
    |
    v
Java Text Generator
~~~

### 14.1. Target-neutral model

Mô hình trung gian độc lập nền tảng có thể chuẩn hóa:

- Kiểu dữ liệu.
- Visibility.
- Quan hệ.
- Method signature.
- Validation rule.
- Metadata.
- Source trace.

Nó có thể biểu diễn một class, field hoặc operation ở mức khái niệm mà chưa chứa cú pháp Java cụ thể.

### 14.2. Target-specific model

Bước target-specific quyết định chi tiết:

- Class hay record.
- Primitive hay wrapper.
- Annotation cụ thể.
- Package và import.
- Cách sinh method.
- Cách thể hiện nullability.
- Runtime helper nào được sử dụng.

Nếu hỗ trợ Java và TypeScript, mỗi target có thể có transformer riêng dùng chung source model và target-neutral model.

### 14.3. Khi nào cần mô hình trung gian?

Phù hợp khi:

- Có nhiều ngôn ngữ đích.
- Mapping có nhiều quy tắc phụ thuộc lẫn nhau.
- Cần tối ưu hoặc chuẩn hóa mô hình trước khi render.
- Cần phân tích phụ thuộc và phát hiện xung đột.
- Cần kiểm thử transformation riêng với template.

Với DSL nhỏ chỉ sinh một file cấu hình đơn giản, một bước mapping trực tiếp có thể đủ. Không nên tạo nhiều tầng chỉ để tăng số lượng abstraction.

## 15. Template-based code generation

Một cách phổ biến để sinh mã là dùng template. Template chứa cấu trúc văn bản đích và các điểm chèn dữ liệu từ mô hình.

Ví dụ template Java class:

~~~text
public class {{className}} {
{{#each properties}}
    private {{typeName}} {{propertyName}};
{{/each}}
}
~~~

Với entity Customer, template có thể tạo:

~~~java
public class Customer {
    private CustomerId id;
    private String name;
}
~~~

### 15.1. Tách dữ liệu khỏi template

Template nên nhận một context đã được chuẩn bị:

~~~text
ClassTemplateContext
  packageName
  className
  imports
  properties
  methods
  annotations
~~~

Không nên để template tự phân giải tên, tra cứu symbol table hoặc quyết định chính sách kiểu phức tạp. Những công việc đó thuộc mapping layer.

### 15.2. Template lặp và điều kiện

Template engine thường hỗ trợ:

- Lặp qua danh sách property.
- Điều kiện có annotation.
- Chèn import.
- Render method.
- Include template con.

Ví dụ, property có default value mới sinh initializer. Property không nullable có thể sinh validation. Template nên giữ logic trình bày vừa đủ; các quyết định ngữ nghĩa cần được giải quyết trước.

### 15.3. Template con và tái sử dụng

Có thể tách template:

~~~text
templates/
  java/
    class
    field
    constructor
    accessor
    enum
    validation
~~~

Việc tái sử dụng giúp mọi class có cùng định dạng. Tuy nhiên, template quá nhỏ và lồng quá nhiều tầng có thể làm luồng sinh mã khó theo dõi. Nên chia theo cấu trúc có ý nghĩa.

### 15.4. Escape đầu ra

Dữ liệu được chèn vào template phải được escape theo ngữ cảnh đích:

- Java string literal.
- SQL string literal.
- JSON string.
- XML attribute.
- HTML text.

Một hàm escape dùng cho Java không thể mặc nhiên dùng cho SQL hoặc HTML. Cần serializer riêng cho từng target và từng ngữ cảnh.

## 16. Sinh mã bằng visitor hoặc transformer

Thay vì template trực tiếp, generator có thể duyệt mô hình bằng visitor hoặc transformer.

Ví dụ, mỗi loại node có một phương thức:

~~~java
interface ModelVisitor<R> {
    R visitEntity(Entity entity);
    R visitProperty(Property property);
    R visitEnum(EnumType enumType);
    R visitRelation(Relation relation);
}
~~~

Generator triển khai visitor để tạo target element tương ứng.

### 16.1. Visitor

Visitor phù hợp khi tập loại node ổn định và có nhiều phép xử lý khác nhau trên cùng mô hình, chẳng hạn sinh Java, tạo tài liệu và tính dependency.

Ưu điểm:

- Tách logic theo loại node.
- Dễ bổ sung phép xử lý mới.
- Có thể kiểm soát thứ tự duyệt.

Hạn chế là khi thêm loại node mới, nhiều visitor có thể phải được cập nhật.

### 16.2. Transformer

Transformer có thể chuyển một node hoặc toàn bộ mô hình thành cấu trúc khác. Ví dụ EntityTransformer tạo ClassModel; PropertyTransformer tạo FieldModel.

Transformer hữu ích khi muốn kiểm thử mapping riêng mà không cần render văn bản.

### 16.3. Kết hợp mapping và template

Một kiến trúc thường hiệu quả:

1. Visitor đọc source model.
2. Mapping rule tạo target model hoặc template context.
3. Template engine render target model thành text.
4. File writer ghi output vào thư mục sinh mã.

Cách chia này giúp template tập trung vào định dạng và mapping tập trung vào ngữ nghĩa.

## 17. Traceability: truy vết từ mã về mô hình

Khi generator tạo hàng trăm tệp, người dùng cần biết một class, field hoặc đoạn mã đến từ phần nào trong DSL. **Traceability** là khả năng giữ liên kết giữa phần tử nguồn và đầu ra được sinh.

Ví dụ, field Java:

~~~java
private BigDecimal total;
~~~

có thể bắt nguồn từ:

~~~text
entity Order {
  property total: Decimal
}
~~~

Generator có thể ghi lại:

~~~text
GeneratedElement:
  targetFile = Order.java
  targetRange = lines 12..12
  sourceFile = sales.dsl
  sourceRange = lines 8..8
  sourceElement = Property(Order.total)
~~~

### 17.1. Lợi ích

- Điều hướng từ mã sinh về khai báo DSL.
- Giải thích vì sao một trường xuất hiện.
- Hỗ trợ diagnostics ở đúng nguồn.
- Phục vụ refactoring.
- Giúp người dùng không chỉnh sửa nhầm vùng được sinh.
- Hỗ trợ kiểm tra thay đổi sau khi mô hình cập nhật.

### 17.2. Source map và metadata

Có thể tạo source map hoặc file metadata riêng:

~~~json
{
  "target": "Order.java",
  "elements": [
    {
      "targetStartLine": 12,
      "targetEndLine": 12,
      "source": "sales.dsl",
      "sourceStartLine": 8,
      "sourceEndLine": 8,
      "element": "Order.total"
    }
  ]
}
~~~

Không nhất thiết phải xuất source map cho mọi generator. Với DSL dùng trong editor hoặc cần debug mã sinh, traceability có giá trị lớn.

### 17.3. Giữ source location qua các bước trung gian

Nếu source model chuyển thành nhiều target model, mỗi target element nên giữ nguồn gốc hoặc tập nguồn gốc. Nếu một dòng mã được tạo từ nhiều constraint, trace có thể trỏ đến nhiều phần tử nguồn.

## 18. Tổ chức file và quản lý đầu ra

Generator cần quy định file nào được tạo và đường dẫn của chúng.

Ví dụ:

~~~text
generated/
  src/
    main/
      java/
        com/example/sales/
          Customer.java
          Order.java
          OrderStatus.java
  metadata/
    generation-map.json
~~~

### 18.1. Một phần tử, một file hay nhiều phần tử, một file?

Với Java, thường một public top-level class nằm trong file cùng tên. Với SQL, nhiều bảng có thể được sinh vào một hoặc nhiều migration file. Với TypeScript, có thể gom nhiều type vào một module.

Chính sách cần phụ thuộc ngôn ngữ đích và convention của dự án.

### 18.2. Đường dẫn xác định

Đường dẫn nên được tính từ namespace, package và cấu hình output root. Không nên phụ thuộc thư mục hiện tại của tiến trình hoặc đường dẫn tuyệt đối trên máy phát triển.

### 18.3. Tạo thư mục và ghi file an toàn

File writer cần:

- Tạo thư mục cha khi cần.
- Ghi encoding thống nhất, thường là UTF-8.
- Dùng newline ổn định nếu yêu cầu tái lập.
- Tránh ghi file một phần khi quá trình render thất bại.
- Chỉ ghi những file thuộc quyền quản lý của generator.
- Phát hiện xung đột đường dẫn.

Có thể ghi vào file tạm rồi thay thế file đích sau khi ghi thành công để tránh đầu ra bị hỏng nếu tiến trình dừng giữa chừng.

### 18.4. Manifest đầu ra

Generator có thể lưu manifest liệt kê các file do lần sinh mã trước tạo ra. Manifest giúp nhận diện file cũ cần cập nhật hoặc xóa khi phần tử nguồn đã bị loại bỏ.

Không nên xóa mọi file trong thư mục output nếu người dùng có thể đặt file thủ công ở đó. Cần giới hạn thao tác vào các file đã được generator ghi nhận.

## 19. Tái sinh mã và bảo vệ phần mã thủ công

Một thách thức lớn là người dùng có thể chỉnh sửa mã sinh ra. Khi mô hình thay đổi, generator cần chạy lại. Nếu ghi đè toàn bộ file, các chỉnh sửa thủ công có thể bị mất.

### 19.1. Generated code và handwritten code

Có thể chia rõ:

~~~text
src/
  main/
    dsl/
      sales.dsl
    generated/
      Order.java
    custom/
      OrderService.java
~~~

Generator sở hữu thư mục generated; mã thủ công nằm ở custom. Đây là cách đơn giản và an toàn.

### 19.2. Partial class hoặc extension

Một số ngôn ngữ hỗ trợ partial class hoặc extension method. Có thể sinh phần cấu trúc và để người dùng mở rộng ở file riêng.

Java không có partial class theo nghĩa của C#, nhưng có thể dùng composition, subclass, interface hoặc helper class để mở rộng.

### 19.3. Protected region

Một số generator dùng marker cho vùng người dùng được phép sửa:

~~~java
// <user-code id="custom-methods">
public void customOperation() {
    // User implementation
}
// </user-code>
~~~

Khi tái sinh, generator cố giữ nội dung giữa các marker. Cách này cần xử lý cẩn thận nếu marker bị xóa, trùng hoặc lồng nhau. Nếu không thể ghép an toàn, nên báo xung đột thay vì âm thầm bỏ nội dung.

### 19.4. Không sửa trực tiếp file sinh nếu có thể tránh

Một quy ước hữu ích là coi mã sinh là đầu ra có thể tái tạo. Tùy chỉnh nên đặt trong extension point được hỗ trợ. Điều này giúp generator chạy lại mà không làm mất thay đổi.

## 20. Sinh mã gia tăng và hiệu năng

Với mô hình lớn, sinh lại toàn bộ đầu ra sau mỗi thay đổi có thể tốn thời gian. Incremental generation chỉ cập nhật những phần bị ảnh hưởng.

### 20.1. Theo dõi dependency

Nếu Order tham chiếu Customer, thay đổi kiểu CustomerId có thể ảnh hưởng cả Customer và Order. Generator cần biết dependency để xác định file nào phải sinh lại.

### 20.2. Hash nội dung hoặc fingerprint

Có thể tính fingerprint từ:

- Phần tử nguồn.
- Các phần tử phụ thuộc.
- Cấu hình target.
- Phiên bản generator.
- Phiên bản template.

Nếu fingerprint không đổi, file có thể được giữ nguyên.

Không nên chỉ hash văn bản của một entity nếu output còn phụ thuộc vào mapping rule hoặc template dùng chung. Thay đổi template có thể yêu cầu sinh lại nhiều file dù mô hình không đổi.

### 20.3. Xóa đầu ra lỗi thời

Nếu một entity bị xóa khỏi mô hình, file tương ứng có thể trở thành stale. Manifest giúp biết file nào do generator sở hữu và có thể xóa.

Cần cân nhắc chế độ dry run để hiển thị danh sách file sẽ tạo, cập nhật hoặc xóa trước khi thực hiện.

### 20.4. Tính xác định và incremental generation

Incremental generation phải tạo kết quả giống full generation. Đây là điều kiện quan trọng: chạy gia tăng nhiều lần không được tạo ra đầu ra khác với việc sinh lại toàn bộ từ cùng mô hình cuối cùng.

## 21. Xử lý lỗi trong quá trình ánh xạ

Không phải mô hình hợp lệ nào cũng có thể biểu diễn bằng mọi target. Generator cần phát hiện trường hợp không hỗ trợ và giải thích rõ.

Ví dụ:

- Mô hình có đa kế thừa nhưng target class chỉ hỗ trợ đơn kế thừa.
- Kiểu miền không có mapping.
- Hai tên property trùng sau chuẩn hóa.
- Quan hệ có multiplicity không thể biểu diễn trực tiếp.
- Biểu thức DSL không có chuyển đổi tương đương ở target.
- Target version không hỗ trợ cú pháp cần sinh.
- Package hoặc đường dẫn đầu ra bị xung đột.

### 21.1. Phân biệt lỗi mô hình và lỗi mapping

- **Model error:** mô hình vi phạm quy tắc DSL, chẳng hạn tham chiếu kiểu không tồn tại.
- **Mapping error:** mô hình hợp lệ nhưng target profile không biết cách biểu diễn.
- **Rendering error:** mapping đã tạo target model nhưng template hoặc file writer thất bại.
- **Target compilation error:** mã đã sinh nhưng compiler đích từ chối.

Phân biệt các loại lỗi giúp xác định nơi cần sửa. Không nên báo mọi trường hợp thành một lỗi chung “Code generation failed”.

### 21.2. Diagnostics có source trace

Nếu mapping không hỗ trợ một quan hệ, diagnostic nên trỏ về khai báo quan hệ trong DSL, không chỉ chỉ ra file Java chưa được sinh.

Ví dụ:

~~~text
Cannot map multiple inheritance to the selected Java target.
Entity: PremiumAccount
Source: account.dsl, line 18
Target profile: java-single-inheritance
~~~

### 21.3. Không tạo đầu ra nửa chừng

Nếu một mapping rule thiết yếu thất bại, generator nên xác định chính sách transaction: dừng toàn bộ, giữ file cũ hay chỉ xuất những phần độc lập. Với code generation cho build, thường nên tránh cập nhật một phần không nhất quán mà không thông báo.

## 22. Kiểm thử mapping và mã được sinh

Kiểm thử code generation có nhiều lớp. Mục tiêu là bảo đảm mapping đúng ý nghĩa và đầu ra có thể sử dụng.

### 22.1. Unit test cho mapping rule

Kiểm tra một source element tạo target model mong đợi.

Ví dụ, Entity Customer có ba property phải tạo ClassModel với ba field, kiểu và visibility phù hợp.

### 22.2. Golden file hoặc snapshot test

Có thể lưu đầu ra kỳ vọng:

~~~text
Expected:
Customer.java

Actual:
Customer.java
~~~

Test so sánh nội dung sinh với file chuẩn. Khi thay đổi định dạng hoặc mapping có chủ ý, cập nhật golden file cùng giải thích.

Snapshot test hữu ích nhưng không thay thế kiểm tra ngữ nghĩa. Một file có thể giống snapshot mà vẫn chứa lỗi kiểu do mapping rule sai trong trường hợp khác.

### 22.3. Compile test

Đưa mã sinh vào compiler của target. Với Java, có thể biên dịch đầu ra trong một fixture project cùng dependency cần thiết.

Compile test phát hiện:

- Import thiếu.
- Tên không hợp lệ.
- Kiểu không tồn tại.
- Method signature sai.
- Cú pháp không phù hợp target version.

### 22.4. Runtime test

Một số semantics chỉ có thể kiểm tra khi chạy. Ví dụ, quan hệ hai chiều phải được đồng bộ; validation phải từ chối dữ liệu không hợp lệ; serialization phải giữ đúng tên và giá trị.

### 22.5. Kiểm thử tính xác định

Chạy generator hai lần với cùng input và cấu hình. So sánh tập file và nội dung. Nếu có khác biệt, xác định xem đó là thay đổi có chủ ý hay phụ thuộc không ổn định.

### 22.6. Kiểm thử thay đổi mô hình

Thử thêm, sửa và xóa phần tử:

- Thêm property.
- Đổi kiểu.
- Đổi tên entity.
- Thay multiplicity.
- Thay default.
- Xóa enum value.
- Di chuyển entity sang namespace khác.

Kiểm tra file cập nhật đúng, dependency được tái sinh và mã thủ công không bị ghi đè.

## 23. Quản lý phiên bản mapping và khả năng tương thích

Mapping rule là một phần của ngữ nghĩa DSL. Thay đổi mapping có thể làm thay đổi mã sinh ngay cả khi source model không đổi.

Ví dụ, phiên bản generator trước ánh xạ Decimal sang double; phiên bản sau chuyển sang BigDecimal. Đây là thay đổi có thể ảnh hưởng API, serialization và phép toán.

### 23.1. Version target profile

Có thể định nghĩa profile:

~~~text
target java {
  version = 21
  mappingProfile = "domain-model-v2"
}
~~~

Profile xác định các chính sách kiểu, class, nullability, annotation và runtime dependency.

### 23.2. Semantic versioning cho generator

Nếu generator là công cụ được nhiều dự án dùng, có thể quản lý version:

- Patch: sửa lỗi không làm thay đổi hợp đồng đầu ra ngoài ý muốn.
- Minor: thêm mapping hoặc tùy chọn tương thích.
- Major: thay đổi output contract hoặc semantics.

Quy tắc cụ thể phụ thuộc dự án, nhưng người dùng cần biết vì sao cùng một DSL tạo ra mã khác sau khi nâng cấp generator.

### 23.3. Migration và diff

Khi mapping thay đổi, generator có thể cung cấp diff hoặc báo cáo:

- Kiểu field thay đổi.
- Tên method thay đổi.
- Annotation được thêm hoặc bỏ.
- File mới hoặc bị xóa.
- Dependency runtime thay đổi.

Báo cáo giúp người dùng đánh giá tác động trước khi cập nhật mã nguồn.

## 24. Ví dụ triển khai mapping Entity sang Java

Một cách tổ chức đơn giản là tách source model, mapping context và renderer.

Mô hình giả định:

~~~text
entity Customer {
  property id: CustomerId
  property name: String
  property active: Boolean = true
}
~~~

Một số kiểu dữ liệu Java:

~~~java
record PropertyModel(
    String name,
    String typeName,
    boolean required,
    String defaultExpression
) {}

record EntityModel(
    String name,
    List<PropertyModel> properties
) {}
~~~

Target model:

~~~java
record JavaField(
    String typeName,
    String name,
    String initializer
) {}

record JavaClass(
    String packageName,
    String name,
    List<JavaField> fields
) {}
~~~

Mapping function minh họa:

~~~java
JavaClass mapEntity(EntityModel entity, TypeMapper typeMapper) {
    List<JavaField> fields = entity.properties().stream()
        .map(property -> new JavaField(
            typeMapper.map(property.typeName()),
            toCamelCase(property.name()),
            property.defaultExpression()
        ))
        .toList();

    return new JavaClass(
        "com.example.domain",
        toPascalCase(entity.name()),
        fields
    );
}
~~~

Renderer:

~~~java
String render(JavaClass model) {
    StringBuilder out = new StringBuilder();

    out.append("package ")
       .append(model.packageName())
       .append(";\n\n");

    out.append("public class ")
       .append(model.name())
       .append(" {\n");

    for (JavaField field : model.fields()) {
        out.append("    private ")
           .append(field.typeName())
           .append(" ")
           .append(field.name());

        if (field.initializer() != null) {
            out.append(" = ").append(field.initializer());
        }

        out.append(";\n");
    }

    out.append("}\n");
    return out.toString();
}
~~~

Ví dụ này chỉ minh họa ranh giới giữa mapping và rendering. Một generator dùng thực tế cần xử lý escaping, import, generic type, nullability, source trace, constructor, accessor, annotation, lỗi mapping và định dạng mã.

### 24.1. Không dùng chuỗi thô cho mọi kiểu

Trong ví dụ đơn giản, defaultExpression là chuỗi. Một implementation đầy đủ nên giữ biểu thức dưới dạng AST hoặc ValueSpecification có kiểu. Khi render, target expression generator mới chuyển node đó thành cú pháp Java hợp lệ.

Điều này tránh việc chèn trực tiếp một đoạn DSL vào Java dù hai ngôn ngữ có cú pháp khác nhau.

### 24.2. Kiểm tra trước khi ghi file

Trước khi ghi output, có thể xác minh:

- Tên class và field hợp lệ.
- Không có tên trùng sau chuẩn hóa.
- Kiểu đích đã được ánh xạ.
- Import và package không xung đột.
- Mọi biểu thức đều có renderer.
- Target version hỗ trợ cú pháp được chọn.

Nếu có lỗi, diagnostic nên chỉ về source model và không để lại một tập file nửa hoàn chỉnh.

## 25. Các chiến lược ánh xạ phổ biến

Không có một chiến lược duy nhất phù hợp cho mọi DSL. Một số hướng thường gặp:

### 25.1. Direct mapping

Chuyển trực tiếp source model thành text. Phù hợp với DSL nhỏ, một target và mapping đơn giản.

Ưu điểm là ít tầng và dễ bắt đầu. Hạn chế là logic có thể bị trộn với template khi DSL lớn dần.

### 25.2. Model-to-model rồi model-to-text

Chuyển source model thành target model trước, sau đó render text. Phù hợp với mapping phức tạp hoặc nhiều target.

Ưu điểm là có thể kiểm tra target model độc lập. Hạn chế là cần thêm abstraction và quy tắc chuyển đổi.

### 25.3. Template-driven

Dùng template để mô tả cấu trúc đầu ra. Phù hợp khi mã đích chủ yếu là văn bản có cấu trúc và template engine hỗ trợ lặp, điều kiện.

Cần giữ logic ngữ nghĩa trong mapping layer để template không trở thành nơi chứa mọi quyết định.

### 25.4. Visitor-based

Duyệt mô hình và tạo output theo từng loại node. Phù hợp với generator có nhiều loại phần tử và cần kiểm soát logic.

Có thể kết hợp visitor với target model và template.

### 25.5. Rule-based mapping

Định nghĩa tập quy tắc có điều kiện, có thể cấu hình theo target profile. Phù hợp khi người dùng cần tùy chỉnh mapping hoặc hỗ trợ nhiều nền tảng.

Cần tránh để rule chồng lấn hoặc có thứ tự không rõ ràng. Khi hai rule cùng áp dụng cho một phần tử, generator phải có quy tắc ưu tiên hoặc báo xung đột.

## 26. Những lỗi thiết kế thường gặp

**Sinh mã trực tiếp từ chuỗi token.** Cách này bỏ qua thông tin ngữ nghĩa đã được phân giải. Hãy dùng mô hình đã kiểm tra làm đầu vào.

**Trộn mapping với template.** Template chứa quá nhiều logic kiểu và phạm vi sẽ khó bảo trì. Hãy chuẩn bị target context hoặc target model trước khi render.

**Không kiểm tra khả năng biểu diễn của target.** Một mô hình hợp lệ có thể không phù hợp với target cụ thể. Cần phát mapping diagnostic thay vì âm thầm bỏ qua cấu trúc.

**Ánh xạ kiểu quá đơn giản.** Chọn sai primitive, nullability, Decimal hoặc thời gian có thể làm mất ngữ nghĩa. Hãy xây type mapper có chính sách rõ.

**Không phát hiện tên trùng sau chuẩn hóa.** Hai tên DSL khác nhau có thể trở thành cùng identifier trong target. Cần kiểm tra trước khi ghi file.

**Dựa vào thứ tự khai báo.** Tham chiếu đến phần tử khai báo phía sau vẫn cần được xử lý. Hãy thu thập symbol và dependency trước khi render.

**Ghi đè mã thủ công.** Nếu generator sở hữu file không rõ ràng, tái sinh có thể làm mất chỉnh sửa. Hãy tách generated code và handwritten code hoặc có cơ chế protected region.

**Đầu ra không xác định.** Timestamp, thứ tự map hoặc đường dẫn máy có thể tạo diff không cần thiết. Hãy ổn định thứ tự và metadata.

**Không giữ traceability.** Khi lỗi xuất hiện trong mã sinh, người dùng khó tìm về khai báo nguồn. Hãy giữ source location và liên kết phần tử.

**Chỉ kiểm tra văn bản.** File có thể khớp snapshot nhưng không biên dịch hoặc không giữ semantics. Kết hợp kiểm tra mapping, compile và runtime phù hợp.

## 27. Quy trình thiết kế ánh xạ mô hình sang mã

Khi xây dựng generator cho DSL, có thể tiến hành theo trình tự:

### Bước 1: Xác định mô hình nguồn

Liệt kê entity, property, type, relation, operation, constraint, workflow và metadata. Xác định ý nghĩa của từng thành phần.

### Bước 2: Chọn target và hợp đồng đầu ra

Chọn ngôn ngữ, phiên bản, runtime dependency, thư mục output và loại file được sinh.

### Bước 3: Xây bảng ánh xạ

Xác định cách chuyển từng loại phần tử, kiểu dữ liệu, quan hệ, nullability, default và constraint. Ghi rõ trường hợp không hỗ trợ.

### Bước 4: Xác định quy tắc tên và namespace

Chuẩn hóa class, field, method, package, table và column. Kiểm tra từ khóa dành riêng và xung đột sau chuẩn hóa.

### Bước 5: Xử lý tham chiếu và dependency

Phân giải toàn bộ kiểu và quan hệ. Tạo đồ thị phụ thuộc, import và thứ tự cần thiết trước khi render.

### Bước 6: Chọn kiến trúc transformation

Quyết định direct mapping, target model, visitor, template hoặc kết hợp các cách. Giữ logic ngữ nghĩa tách khỏi định dạng văn bản.

### Bước 7: Tạo đầu ra có traceability

Giữ source location cho target element, tạo manifest nếu cần và xác định file nào generator sở hữu.

### Bước 8: Quản lý tái sinh

Quy định cách cập nhật, xóa file lỗi thời, bảo vệ mã thủ công và xử lý xung đột.

### Bước 9: Kiểm thử

Kiểm tra mapping rule, golden output, compile, runtime, tính xác định và các thay đổi mô hình.

### Bước 10: Quản lý phiên bản

Theo dõi phiên bản generator, target profile và mapping contract. Cung cấp diff hoặc migration khi output semantics thay đổi.

## 28. Ví dụ tổng hợp: từ mô hình đơn hàng đến Java và SQL

Xét mô hình DSL:

~~~text
namespace sales {
  enum OrderStatus {
    PENDING
    PAID
    CANCELLED
  }

  entity Customer {
    property id: UUID required
    property name: String required
  }

  entity Order {
    property id: UUID required
    property status: OrderStatus = PENDING
    property total: Decimal
    property customer: Customer required
  }

  constraint PositiveTotal {
    require Order.total >= 0
  }
}
~~~

### 28.1. Phân tích mô hình

Trước khi sinh mã, hệ thống cần xác định:

- OrderStatus là enum hợp lệ.
- Customer và Order là hai entity.
- Order.customer tham chiếu đến Customer.
- total có kiểu Decimal.
- status có default là PENDING.
- PositiveTotal tham chiếu đến thuộc tính total.
- Các thuộc tính required phải được biểu diễn trong target.

### 28.2. Ánh xạ sang Java

Một target profile Java có thể chọn:

- Entity thành class.
- UUID thành java.util.UUID.
- String thành java.lang.String.
- Decimal thành java.math.BigDecimal.
- Enum thành Java enum.
- Quan hệ customer thành trường Customer.
- Constraint thành validation method hoặc annotation.
- Giá trị mặc định status thành initializer.

Java đầu ra giản lược:

~~~java
package com.example.sales;

import java.math.BigDecimal;
import java.util.UUID;

public class Order {
    private UUID id;
    private OrderStatus status = OrderStatus.PENDING;
    private BigDecimal total;
    private Customer customer;

    public void validate() {
        if (total != null && total.signum() < 0) {
            throw new IllegalArgumentException(
                "Order.total must be non-negative"
            );
        }
    }
}
~~~

Đây chỉ là một cách biểu diễn. Nếu total bắt buộc, validation cần kiểm tra null; nếu framework hỗ trợ annotation, generator có thể sinh annotation tương ứng.

### 28.3. Ánh xạ sang SQL

SQL target có thể sinh:

~~~sql
CREATE TABLE Customer (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE Orders (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    total DECIMAL(12, 2),
    customer_id UUID NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES Customer(id),
    CONSTRAINT chk_order_total
        CHECK (total >= 0)
);
~~~

SQL cần chính sách riêng về tên bảng, kiểu UUID, độ chính xác Decimal, tên constraint và cách biểu diễn enum. Không nên lấy nguyên mapping Java rồi suy ra SQL.

### 28.4. Traceability và kiểm tra đầu ra

Mỗi field và constraint trong mã đích nên có thể truy về phần tử nguồn. Sau khi sinh:

- Kiểm tra file Java biên dịch với dependency đã khai báo.
- Kiểm tra SQL phù hợp dialect đã chọn.
- Kiểm tra giá trị default và constraint được giữ.
- Kiểm tra tên bảng và cột không xung đột.
- Kiểm tra cùng mô hình và profile tạo ra cùng đầu ra.

Ví dụ này cho thấy một mô hình miền có thể sinh nhiều loại tài nguyên, nhưng mỗi target cần một bộ mapping rule được xác định rõ.

## 29. Kết luận

Ánh xạ mô hình sang mã chuyển các khái niệm và quy tắc của DSL thành cấu trúc trong một ngôn ngữ hoặc nền tảng đích. Một phép ánh xạ tốt phải bảo toàn ngữ nghĩa, tạo mã hợp lệ, nhất quán, tái lập và dễ bảo trì.

Để thực hiện điều đó, cần định nghĩa rõ target contract, mapping rule, type mapping, quy tắc quan hệ, kế thừa, tên, namespace, biểu thức và constraint. Với generator lớn, có thể tách source model, target model và template renderer; traceability giúp liên kết mã sinh với mô hình nguồn; manifest và chính sách tái sinh giúp bảo vệ mã thủ công và cập nhật đầu ra an toàn.

Hãy xem mapping là một phần của ngữ nghĩa DSL, không chỉ là thao tác định dạng văn bản. Khi mỗi quy tắc được mô tả rõ và kiểm tra độc lập, generator có thể tạo đầu ra ổn định cho nhiều nền tảng mà vẫn giữ ý nghĩa của mô hình miền.

