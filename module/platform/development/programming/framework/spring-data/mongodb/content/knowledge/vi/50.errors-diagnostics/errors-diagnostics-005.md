# Mapping constructor, _class, TypeAlias và converter bị thiếu

## 1. Bài toán: document tồn tại nhưng Spring không đọc được

Trong ứng dụng **Spring Data MongoDB**, thao tác **MongoTemplate.find(...)**, **MongoRepository.findById(...)** hoặc API reactive tương ứng có thể thất bại dù MongoDB đã trả về document hợp lệ. Nguyên nhân không nhất thiết là truy vấn, kết nối hoặc index: có thể **Spring không chuyển được BSON thành đối tượng Java** mà ứng dụng yêu cầu.

Ví dụ, collection **invoices** có bản ghi:

~~~javascript
{
  _id: "INV-100",
  customer_id: "C-42",
  totalCents: NumberLong(120000),
  _class: "com.example.billing.Invoice"
}
~~~

Trong khi code hiện tại vừa đổi tên trường **customerId**, chuyển từ POJO sang **record**, thay đổi package **Invoice**, hoặc thêm một value object cho **totalCents**. Các thay đổi này có thể làm lỗi mapping xuất hiện chỉ khi đọc dữ liệu cũ.

Chủ đề **Lỗi và chẩn đoán** này tập trung vào bốn nhóm vấn đề liên quan đến **MappingMongoConverter**:

1. **Mapping constructor**: Spring không xác định hoặc gọi được constructor, hoặc không gán được tham số từ document.
2. **_class**: metadata kiểu trong BSON trỏ tới class đã đổi tên, class không có trên classpath, hoặc thiếu thông tin để dựng subtype.
3. **@TypeAlias**: alias ghi trong **_class** không khớp hoặc mapping context chưa đăng ký kiểu tương ứng.
4. **Converter bị thiếu hoặc không được sử dụng**: kiểu Java và kiểu BSON lưu thực tế không có hướng chuyển đổi thích hợp.

Sau bài học, bạn có thể phân biệt lỗi tại **server/query** với lỗi tại **Java mapping**, đọc BSON gốc để xác định khác biệt, xử lý an toàn dữ liệu cũ và viết test ngăn lỗi tái diễn.

## 2. Dòng dữ liệu đi qua những lớp nào?

Khi sử dụng Spring Data MongoDB, đường đi của dữ liệu đọc có thể hình dung như sau:

~~~mermaid
flowchart TB
    API["MongoRepository / MongoTemplate<br/>hoặc API reactive"]
    Driver["MongoDB Java Driver<br/>giải mã BSON"]
    Raw["org.bson.Document<br/>giá trị từ server"]
    Type["MongoTypeMapper<br/>đọc _class / alias"]
    Conv["MappingMongoConverter<br/>conversion + entity metadata"]
    Ctor["Chọn constructor / factory<br/>gán tham số và property"]
    Entity["Invoice / Payment / DTO<br/>đối tượng Java"]
    API --> Driver --> Raw --> Type --> Conv --> Ctor --> Entity
~~~

**MongoDB trả Document thành công** chỉ xác nhận rằng server có dữ liệu và driver đọc được BSON. Từ đó, mapper còn phải xác định class đích, chuyển các kiểu giá trị rồi tạo đối tượng Java.

### Các khái niệm không nên nhầm

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **@Document** | Xác định entity được ánh xạ tới collection MongoDB | **@Document("invoices")** |
| **@Field** | Quy định tên hoặc kiểu lưu của một **property** | **@Field("customer_id")** |
| **@Id / @MongoId** | Ánh xạ định danh Java tới trường BSON **_id** | **@Id String id** |
| **_class** | Trường type hint do Spring Data MongoDB thường ghi để nhận diện kiểu Java | **"com.example.billing.Invoice"** |
| **@TypeAlias** | Thay tên class đầy đủ trong type hint bằng bí danh | **@TypeAlias("invoice-v1")** |
| **@PersistenceCreator** | Chỉ ra constructor hoặc factory dùng khi dựng entity | **@PersistenceCreator Invoice(...)** |
| **@ReadingConverter** | Xác định phép đổi dữ liệu đã đọc thành giá trị Java | **Converter<String, TrackingCode>** |
| **@WritingConverter** | Xác định phép đổi giá trị Java trước khi ghi BSON | **Converter<TrackingCode, String>** |

**@Field** đổi tên trường chứa dữ liệu; **@TypeAlias** đổi cách biểu diễn loại đối tượng. Đặt **@Field("_class")** trên một property nghiệp vụ không phải cách sửa cơ chế phân giải subtype của MongoDB.

## 3. Nhận diện nhóm lỗi từ exception

Các thông báo dưới đây là **dấu hiệu thường gặp**, không phải chuỗi cố định của mọi phiên bản Spring Data MongoDB. Hãy đọc exception gốc và nguyên nhân (**Caused by**) sâu nhất.

| Dấu hiệu | Khả năng cần kiểm tra | Hướng điều tra đầu tiên |
| --- | --- | --- |
| **MappingInstantiationException** | Constructor ném lỗi, tham số null/khác kiểu, class trừu tượng không tạo được | Constructor được chọn, trường BSON có mặt và kiểu dữ liệu |
| **MappingException**, không bind được constructor parameter | Tên tham số không có trong metadata, không trùng property, thiếu **-parameters** | Constructor, property name, compiler options |
| **ConverterNotFoundException** hoặc lỗi conversion | BSON là String/Document/Decimal128 nhưng Java yêu cầu kiểu khác | Kiểu BSON thực tế, converter đọc, cách đăng ký |
| Lỗi kiểu **ClassNotFoundException** hoặc không resolve được type hint | Giá trị **_class** trỏ tới class đã xóa/đổi package, hoặc alias chưa được nhận diện | BSON **_class**, mapping context, deployment/version |
| **CodecConfigurationException** | Đường truy cập trực tiếp qua driver hoặc codec BSON/POJO chưa hỗ trợ kiểu được gửi | Có đang bỏ qua MongoTemplate và MappingMongoConverter không? |
| Đọc thành **Document/Map** thay vì subtype mong muốn | Thiếu hoặc bỏ type hint, declared type quá tổng quát, metadata kiểu không được nhận diện | Declared type, **_class**, **@TypeAlias** |
| Trường thành **null** hoặc giá trị mặc định bất ngờ | Tên lưu trữ khác property, converter không chạy, dữ liệu legacy thiếu field | Raw Document và **@Field** |

Không nên sửa bằng cách thêm **try/catch** rồi trả **null** cho mọi lỗi mapping. Điều đó che giấu dữ liệu không tương thích, có thể khiến nghiệp vụ cập nhật đè mất trường hoặc ghi document sai cấu trúc.

## 4. Mapping constructor: Spring dựng đối tượng bằng cách nào?

Khi chuyển BSON thành object, Spring Data cần chọn một phương thức tạo instance. Quy tắc chi tiết tùy phiên bản và loại ngôn ngữ, nhưng các trường hợp Java phổ biến là:

- Có constructor hoặc static factory được đánh dấu **@PersistenceCreator**: mapper sử dụng lựa chọn phù hợp đó.
- Chỉ có một constructor: thường dùng chính constructor ấy.
- Java **record**: sử dụng canonical constructor của record khi không có cấu hình đặc biệt.
- Có nhiều constructor mà không đánh dấu rõ: constructor không tham số có thể được ưu tiên nếu tồn tại; các trường hợp còn lại dễ bị mơ hồ.

**Tên tham số constructor** phải khớp với **property Java được ánh xạ**, rồi mapper dùng metadata property để tìm tên trường BSON tương ứng. Trên class Java thông thường, tên tham số cần hiện diện trong bytecode (thường qua cờ **-parameters** hoặc metadata thích hợp). Với record, tên component có sẵn theo mô hình record.

### 4.1. Ví dụ immutable entity có constructor rõ ràng

~~~java
// Invoice.java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("invoices")
public class Invoice {
    @Id
    private final String id;

    @Field("customer_id")
    private final String customerId;

    private final long totalCents;

    @PersistenceCreator
    public Invoice(String id, String customerId, long totalCents) {
        this.id = Objects.requireNonNull(id, "id");
        this.customerId =
            Objects.requireNonNull(customerId, "customerId");
        if (totalCents < 0) {
            throw new IllegalArgumentException("Negative invoice amount");
        }
        this.totalCents = totalCents;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public long getTotalCents() {
        return totalCents;
    }
}
~~~

Đối với document ví dụ ở đầu bài:

1. Mapper xác định **Invoice** là kiểu cần dựng.
2. Tham số **id** nhận giá trị của BSON **_id** thông qua **@Id**.
3. Tham số **customerId** được liên kết với Java property **customerId**, có tên BSON **customer_id** nhờ **@Field**.
4. Tham số **totalCents** nhận số nguyên từ **totalCents**.
5. Spring gọi constructor; nếu constructor tự ném **IllegalArgumentException**, lỗi được bọc trong exception liên quan instantiation.

**Điểm dễ nhầm:** đổi tham số constructor thành **customer_id** để khớp trực tiếp với BSON thường là sai, vì Spring giải quyết qua **tên property Java** và metadata mapping. Hãy giữ **customerId** trong code và khai báo tên lưu qua **@Field**.

### 4.2. Khi tên tham số constructor bị mất

Với Java class có constructor được chọn, nếu thông tin tên tham số không có trong bytecode, mapper có thể không bind được.

Với Gradle Groovy DSL, một cách khai báo là:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Với Maven, cấu hình **maven-compiler-plugin** để bật **parameters** theo phiên bản đang dùng.

Cờ **-parameters** giúp mapper đọc tên tham số thực từ bytecode. Nó **không** sửa được property bị đổi tên, trường thiếu trong document, kiểu BSON sai hoặc constructor chứa logic ném exception.

### 4.3. Nhiều constructor và no-args constructor

Ví dụ dễ sinh hành vi ngoài ý muốn:

~~~java
class Customer {
    private String id;
    private String displayName;

    Customer() {
        // Được chọn trong một số trường hợp khi có nhiều constructor.
    }

    Customer(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }
}
~~~

Nếu kỳ vọng Spring luôn gọi constructor hai tham số để kiểm tra dữ liệu, hãy chỉ định rõ constructor bằng **@PersistenceCreator** hoặc thiết kế entity chỉ có một constructor phù hợp. Đừng giả định validation trong constructor sẽ chạy nếu mapper chọn con đường tạo object khác rồi gán property.

### 4.4. Record và trường legacy bị thiếu

~~~java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("profiles")
public record Profile(
    @Id String id,
    String fullName,
    String timezone
) {
    public Profile {
        Objects.requireNonNull(fullName, "fullName");
        if (timezone == null || timezone.isBlank()) {
            timezone = "UTC";
        }
    }
}
~~~

Record dùng canonical constructor để materialize. Ví dụ này chủ động áp dụng giá trị mặc định khi **timezone** chưa có trong document cũ. Nhưng nếu **fullName** thiếu, constructor ném lỗi: đó là tín hiệu dữ liệu không đáp ứng invariant. Cần lựa chọn rõ giữa **migrate dữ liệu**, **default có chủ đích** và **từ chối bản ghi không hợp lệ**.

Đặc biệt, **@Transient** trên property cần đưa vào constructor persistence sẽ khiến mapper không thể lấy giá trị từ BSON cho tham số đó. Tương tự, các field đọc qua SpEL, factory method hoặc constructor bất biến phải được kiểm tra theo quy tắc mapping của phiên bản đang dùng.

## 5. Trường _class: cách Spring phân biệt các kiểu Java

Mặc định **MappingMongoConverter** thường sử dụng **DefaultMongoTypeMapper**, ghi tên class đầy đủ vào trường **_class** của root document. Với nested value là một kiểu phức tạp và cần phân biệt subtype so với kiểu khai báo, Spring có thể ghi thêm **_class** tại nested document.

Ví dụ khái niệm:

~~~javascript
{
  _id: "P-001",
  customerId: "C-42",
  source: {
    lastFour: "1234",
    _class: "com.example.payments.CardSource"
  },
  _class: "com.example.payments.Payment"
}
~~~

Giả sử Java khai báo:

~~~java
interface PaymentSource {}

final class CardSource implements PaymentSource {
    String lastFour;
}

@Document("payments")
class Payment {
    @Id String id;
    String customerId;
    PaymentSource source;
}
~~~

Trường **source** được khai báo là **interface**. Khi đọc, Spring cần biết nên tạo **CardSource** hay một implementation khác. Type hint trong nested **source._class** là một cách giải quyết.

### 5.1. Khi document thiếu _class

Nếu code gọi **mongoTemplate.findById("INV-100", Invoice.class)** thì **Invoice.class** đã là kiểu đích cụ thể; một document không có **_class** vẫn có thể được ánh xạ bình thường nếu các field phù hợp.

Tình huống khó hơn là:

- Property khai báo là **interface**, **abstract class** hoặc kiểu tổng quát.
- Dữ liệu BSON không cung cấp type hint cho giá trị cần phân biệt.
- Không có custom reading converter hoặc cơ chế ánh xạ riêng để chọn implementation.

Khi đó, Spring có thể không biết phải tạo subtype nào, dẫn đến lỗi mapping hoặc giá trị không đúng kỳ vọng. Việc tùy ý xóa mọi **_class** trên dữ liệu đang lưu có thể làm hỏng khả năng đọc những field đa hình.

### 5.2. Khi _class chứa tên package hoặc class đã đổi

Trước khi refactor:

~~~javascript
{ _class: "com.legacy.billing.Invoice", _id: "INV-100" }
~~~

Sau khi đổi class sang **com.example.billing.Invoice**, document cũ vẫn giữ chuỗi type hint trước đó. Một bản deployment mới không còn class cũ có thể không phân giải được giá trị **_class**. Cách khắc phục phụ thuộc dữ liệu thực:

1. **Giữ tương thích tạm thời** khi vẫn còn dữ liệu được ghi bằng kiểu cũ, nếu kiến trúc cho phép.
2. **Migrate _class có kiểm soát** nếu mọi document tương ứng chắc chắn là loại mới và trường dữ liệu tương thích.
3. **Dùng @TypeAlias hoặc TypeInformationMapper tùy biến** để quản lý tên kiểu ổn định lâu dài; cần giải quyết cả dữ liệu cũ.
4. **Thử đọc trước và sau migration** trên mẫu chứa tất cả subtype liên quan.

**Đổi annotation @TypeAlias trong source code không tự cập nhật giá trị _class đã lưu từ trước.** Tương tự, đổi tên collection không biến đổi nội dung nested type hint.

### 5.3. Không tắt _class như một cách chữa lỗi mặc định

Spring Data cho phép tùy biến **DefaultMongoTypeMapper**, bao gồm cấu hình không ghi type hint trong những trường hợp thích hợp. Tuy nhiên, xóa type hint toàn cục làm mất thông tin cần cho nhiều mô hình polymorphism và có thể ảnh hưởng đọc các bản ghi đã lưu.

Chỉ cân nhắc cấu hình này khi dữ liệu có **schema rõ ràng**, các loại đích có thể được xác định mà không cần **_class**, và đã kiểm thử các entity lồng nhau, interface, projection và dữ liệu cũ. Không nên tắt **_class** chỉ để thông báo lỗi biến mất.

## 6. @TypeAlias: dùng tên kiểu ổn định và chẩn đoán alias bị thiếu

**@TypeAlias** cho phép Spring Data lưu bí danh ngắn thay cho tên class Java đầy đủ trong **_class**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("payments")
@TypeAlias("payment-v1")
public record Payment(
    @Id String id,
    PaymentSource source
) {}

interface PaymentSource {}

@TypeAlias("card-source-v1")
record CardSource(String lastFour) implements PaymentSource {}

@TypeAlias("bank-source-v1")
record BankSource(String bankCode) implements PaymentSource {}
~~~

Một document có thể được ghi ở dạng:

~~~javascript
{
  _id: "P-001",
  source: {
    lastFour: "1234",
    _class: "card-source-v1"
  },
  _class: "payment-v1"
}
~~~

Vì alias không chứa tên package, các đợt đổi tên package có thể bớt ảnh hưởng tới dữ liệu mới. Nhưng **alias vẫn là một phần của định dạng dữ liệu**: thay alias của cùng class tùy tiện sẽ làm dữ liệu cũ và mới dùng những mã khác nhau.

### 6.1. Alias có trên BSON nhưng mapper vẫn không nhận diện

Một lỗi dễ gặp là ứng dụng có class được đánh dấu **@TypeAlias("card-source-v1")**, nhưng **mapping context chưa biết class đó** lúc đọc document đầu tiên. Alias chỉ phát huy tác dụng khi metadata của entity đích đã được đăng ký.

Theo tài liệu Spring Data, entity metadata có thể được nhận diện khi lưu lần đầu hoặc cung cấp thông qua tập entity ban đầu (**initial entity set**), thường được xác định qua classpath scanning trong vùng cấu hình.

Các cách kiểm tra:

- **Class thực sự có trong artifact runtime?** Không chỉ nằm trong module test hoặc package bị loại khỏi build.
- **Annotation có trên đúng concrete subtype?** Không nhầm với interface cha.
- **Mapping context đã khám phá subtype?** Kiểm tra package scanning, danh sách initial entities hoặc cấu hình mapping riêng.
- **Alias có trùng nhau?** Hai kiểu khác nhau dùng cùng alias sẽ tạo dữ liệu mơ hồ.
- **Có nhiều MongoTemplate/MongoConverter?** Alias có thể được đăng ký trong một context nhưng lời gọi thực tế dùng converter khác.

Một ví dụ khi ứng dụng tự quản lý cấu hình Spring Data MongoDB bằng **AbstractMongoClientConfiguration**:

~~~java
import java.util.Set;
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;

// Phần override đặt trong class cấu hình MongoDB hoàn chỉnh,
// nơi mongoClient() và các cấu hình còn lại đã được cung cấp.
@Override
protected Set<Class<?>> getInitialEntitySet() {
    return Set.of(
        Payment.class,
        CardSource.class,
        BankSource.class
    );
}
~~~

Đây là **đoạn method minh họa**, không phải một class Java độc lập có thể copy chạy ngay. Nếu dùng Spring Boot auto-configuration, cần kiểm tra cơ chế entity scanning đang được bật thay vì tự thêm cấu hình có nguy cơ tạo converter/context thứ hai.

### 6.2. Lựa chọn alias như thế nào?

| Cách lưu _class | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Tên class đầy đủ | Spring có thể xác định class trực tiếp khi class vẫn tồn tại | Đổi package, đổi tên class có thể ảnh hưởng dữ liệu cũ |
| Alias ngắn, ổn định | Ít phụ thuộc cấu trúc package | Phải bảo đảm mapping context nhận diện, alias duy nhất và quản lý migration |
| Không lưu type hint | BSON gọn hơn trong mô hình đồng nhất | Đọc interface/subtype có thể không xác định được |

Alias nên mang tính định danh ổn định, ví dụ **payment-card-v1**. Phần **v1** là quyết định schema của hệ thống, không có nghĩa Spring tự thực hiện version migration.

## 7. Converter bị thiếu: Java type và BSON type không khớp

Giả sử trước đây trường **trackingCode** của collection **shipments** được lưu dưới dạng chuỗi:

~~~javascript
{
  _id: "S-100",
  trackingCode: "VN-TRK-001"
}
~~~

Sau đó ứng dụng thay **String trackingCode** thành **TrackingCode trackingCode** để kiểm soát định dạng:

~~~java
public record TrackingCode(String value) {
    public TrackingCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Tracking code must not be blank"
            );
        }
    }
}
~~~

Nếu mapper không có phép chuyển **String -> TrackingCode**, dữ liệu cũ dạng scalar String có thể không được đọc thành value object như mong đợi. Ngược lại, nếu chỉ có converter đọc mà thiếu converter ghi, document mới có thể được lưu theo cấu trúc khác, khiến hai phiên bản ứng dụng không tương thích.

### 7.1. Khai báo reading và writing converters

~~~java
// TrackingCodeReadConverter.java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class TrackingCodeReadConverter
        implements Converter<String, TrackingCode> {

    @Override
    public TrackingCode convert(String source) {
        return new TrackingCode(source);
    }
}
~~~

~~~java
// TrackingCodeWriteConverter.java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class TrackingCodeWriteConverter
        implements Converter<TrackingCode, String> {

    @Override
    public String convert(TrackingCode source) {
        return source.value();
    }
}
~~~

Các annotation **@ReadingConverter** và **@WritingConverter** phân biệt hướng chuyển đổi. Điều này đặc biệt quan trọng khi hai phía đều là kiểu driver có thể biểu diễn trực tiếp, khiến Spring không thể suy đoán chính xác converter dùng lúc đọc hay ghi.

### 7.2. Đăng ký converter với MongoCustomConversions

~~~java
// MongoValueConversionConfig.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class MongoValueConversionConfig {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new TrackingCodeReadConverter());
            adapter.registerConverter(new TrackingCodeWriteConverter());
        });
    }
}
~~~

Ví dụ sử dụng API **MongoCustomConversions.create(...)** có trong các dòng Spring Data MongoDB hiện hành. Nếu dự án dùng phiên bản cũ, cách đăng ký có thể là truyền danh sách converter vào **MongoCustomConversions** hoặc override cấu hình chuyển đổi tương ứng; hãy kiểm tra API đúng phiên bản.

Các converter **không tự động được đăng ký chỉ vì class nằm trên classpath**. Khi dùng Spring Boot, phải đảm bảo bean **MongoCustomConversions** được auto-configuration của converter thực tế sử dụng. Khi tự khởi tạo **MappingMongoConverter**, cần truyền tập custom conversions vào converter và hoàn tất khởi tạo theo API tương ứng.

Với reactive access, cần xác nhận **ReactiveMongoTemplate** đang dùng converter có registration đó; cấu hình một converter không được client/template thực tế sử dụng sẽ không sửa được lỗi.

### 7.3. Áp dụng vào entity và test dữ liệu cũ

~~~java
// Shipment.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("shipments")
public record Shipment(
    @Id String id,
    TrackingCode trackingCode
) {}
~~~

Kỳ vọng sau khi đăng ký đúng converter:

| Hướng | Giá trị đầu vào | Giá trị sau chuyển |
| --- | --- | --- |
| Read | BSON String **"VN-TRK-001"** | **new TrackingCode("VN-TRK-001")** |
| Write | **new TrackingCode("VN-TRK-002")** | BSON String **"VN-TRK-002"** |

Không đặt conversion logic ở controller nếu vấn đề là cách một property được lưu và đọc trong MongoDB. Mọi luồng đọc, gồm repository và MongoTemplate, phải sử dụng quy tắc mapping thống nhất.

### 7.4. Converter cho Document lồng nhau

Nếu dữ liệu cũ là document dạng:

~~~javascript
{
  _id: "S-101",
  trackingCode: { prefix: "VN", number: "002" }
}
~~~

thì converter từ **String -> TrackingCode** không giải quyết được. Cần xem xét:

- Viết **@ReadingConverter** từ **Document -> TrackingCode** nếu có quy tắc đọc riêng phù hợp.
- Cho phép model đọc được dạng document đó bằng constructor/property mapping.
- **Migrate** dữ liệu cũ về một định dạng thống nhất.

Đừng tạo converter với signature sai chỉ vì exception đề cập tên kiểu Java. Hãy xác định **source BSON type thực** trước khi quyết định.

### 7.5. Chú ý kiểu BigDecimal và Decimal128

Trường tiền có thể được lưu dạng **String** hoặc **Decimal128**, tùy phiên bản Spring Data MongoDB và cấu hình. Với yêu cầu dùng Decimal128, có thể chỉ định:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

class ProductPrice {
    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal amount;
}
~~~

Tài liệu Spring Data MongoDB 5.x mô tả thay đổi trong lựa chọn biểu diễn mặc định cho số lớn. Vì vậy, khi nâng phiên bản, phải kiểm tra cả **BSON thực tế**, **@Field(targetType = ...)** và **MongoCustomConversions**, không mặc định mọi **BigDecimal** đều được ghi theo cùng một biểu diễn qua các phiên bản.

## 8. Quy trình chẩn đoán một lỗi mapping thực tế

Giả sử API **GET /shipments/S-100** trả lỗi 500, log có nguyên nhân liên quan đến **TrackingCode**. Quy trình hiệu quả là tách truy vấn dữ liệu khỏi chuyển đổi object.

### Bước 1 — Ghi nhận thông tin tối thiểu

Lưu lại (theo chính sách bảo mật của hệ thống):

- Tên collection, kiểu Java yêu cầu, ID hoặc mã tham chiếu đã được ẩn danh.
- Phiên bản ứng dụng/Spring Data MongoDB, và liệu lỗi xuất hiện sau deploy hay migration.
- Exception class, các dòng **Caused by**, tên property/constructor/converter bị đề cập.
- Sự khác biệt giữa document đọc được và document gây lỗi.

Không log toàn bộ dữ liệu khách hàng, mật khẩu, token hoặc trường nhạy cảm chỉ để chẩn đoán.

### Bước 2 — Đọc BSON gốc, bỏ qua bước dựng entity

Với **mongosh**:

~~~javascript
db.getSiblingDB("demo")
  .getCollection("shipments")
  .findOne({ _id: "S-100" });
~~~

Hoặc trong một test tích hợp có **MongoTemplate**:

~~~java
import static com.mongodb.client.model.Filters.eq;
import org.bson.Document;

Document raw = mongoTemplate.getCollection("shipments")
    .find(eq("_id", "S-100"))
    .first();

if (raw == null) {
    throw new IllegalStateException("Test fixture was not found");
}
System.out.println("Tracking value BSON shape: "
    + (raw.get("trackingCode") == null
        ? "null"
        : raw.get("trackingCode").getClass().getName()));
~~~

Đoạn trên giả định **mongoTemplate** đã được inject trong test/service. Để bảo vệ dữ liệu, chỉ log **tên kiểu** và metadata cần thiết, không in giá trị trường nhạy cảm.

Đọc bằng **MongoTemplate.getCollection(...)** trả API collection của driver, giúp quan sát document mà không yêu cầu mapper dựng **Shipment**. Cách này phân biệt vấn đề dữ liệu tồn tại/không tồn tại với vấn đề **materialization**.

### Bước 3 — So kiểu BSON thực với Java property

Ví dụ:

| Raw BSON | Property Java | Hướng chẩn đoán |
| --- | --- | --- |
| **trackingCode: "VN-TRK-001"** | **TrackingCode** | Cần đọc String -> TrackingCode hoặc migration |
| **trackingCode: {prefix, number}** | **TrackingCode** | Mapping subdocument hoặc Document -> TrackingCode |
| **totalCents: "120000"** | **long** | Kiểm tra dữ liệu legacy/convert số, không mặc định String sẽ tự chuyển |
| **customer_id: "C-42"** | **customerId** | Cần metadata **@Field("customer_id")** |
| **source._class: "old.package.CardSource"** | **PaymentSource** | Cần tương thích type hint/migration |
| Không có **source._class** | Interface **PaymentSource** | Cần cách chọn subtype rõ ràng |
| Thiếu **fullName** | Record yêu cầu non-null | Cần default có chủ đích hoặc làm sạch dữ liệu |

### Bước 4 — Thử materialize một document cô lập

Nếu đã có một BSON document **raw**, có thể thử mapper đang dùng:

~~~java
Shipment mapped =
    mongoTemplate.getConverter().read(Shipment.class, raw);
~~~

Khi mapper thất bại trên input có thể tái lập, việc xem stack trace và data shape thường rõ ràng hơn debug cả REST endpoint. Cần dùng đúng **MongoTemplate/MappingMongoConverter** mà ứng dụng đang chạy, vì dùng converter thử nghiệm khác có thể dẫn tới kết quả giả.

### Bước 5 — Kiểm tra metadata và registration

Nếu lỗi thuộc constructor:

1. Entity có bao nhiêu constructor/factory?
2. Constructor nào được chọn?
3. **@PersistenceCreator** có trên lựa chọn mong muốn?
4. Java bytecode có parameter names?
5. Tham số có trùng tên **property Java**? Có **@Field** nào đổi tên lưu?
6. Trường thiếu/null có khiến constructor ném exception?

Nếu lỗi thuộc **_class/@TypeAlias**:

1. BSON thực có **_class** ở root và nested cần polymorphism không?
2. Type hint là tên class cũ hay alias?
3. Class còn tồn tại trong runtime artifact?
4. Alias đã được mapping context đăng ký trước khi đọc?
5. Các alias có duy nhất và ổn định giữa phiên bản không?

Nếu lỗi thuộc custom converter:

1. Source là **String**, **Document**, **Decimal128** hay loại BSON khác?
2. Có converter **đúng cặp source/target** và **đúng chiều read/write**?
3. Converter đã được đăng ký với MongoCustomConversions chưa?
4. Spring có thực sự dùng converter đó tại runtime?
5. Converter có thể ném exception khi gặp dữ liệu sai định dạng không?

### Bước 6 — Chọn sửa code hay sửa dữ liệu

Nếu dữ liệu là **schema cũ vẫn được hỗ trợ**, có thể dùng constructor thích hợp, **@Field**, converter tương thích hoặc mapping type alias. Nếu dữ liệu **không còn đúng nghiệp vụ**, nên migrate thành schema mới có test và khả năng rollback. Nếu dữ liệu sai do lỗi ghi, cần sửa cả đường ghi để ngăn phát sinh bản ghi lỗi mới.

Không cập nhật hàng loạt **_class** hoặc đổi định dạng tiền trong production trước khi thống kê các biến thể BSON, thử trên bản sao dữ liệu và đánh giá các ứng dụng khác vẫn đang đọc collection.

## 9. Tình huống chẩn đoán từ những lần refactor thường gặp

### Tình huống A — Từ JavaBean sang record

Trước đó **Customer** có constructor rỗng và setter. Sau refactor, **Customer** thành record có ba component, trong khi document cũ thiếu một field. Khi đọc, canonical constructor có thể nhận **null** và ném lỗi.

**Cách xử lý:** xác định field bắt buộc, đưa default hợp lý vào constructor hoặc migration; test cả document cũ và document mới. Nếu dữ liệu thiếu là lỗi nghiệp vụ không thể suy ra, phải giữ thông báo lỗi rõ ràng, tránh tự bịa giá trị.

### Tình huống B — Đổi Java package sau khi đã lưu dữ liệu

Collection có **_class: "legacy.app.Order"**, runtime chỉ còn **new.app.Order**. Một số bản ghi có thể đọc được nếu ứng dụng luôn yêu cầu class đích cụ thể và không phụ thuộc type hint; những chỗ dùng subtype hoặc kiểu tổng quát có thể thất bại.

**Cách xử lý:** kiểm kê cách đọc entity, triển khai alias hoặc migration có kiểm soát và test những trường hợp polymorphism. Không dựa vào việc một lời gọi **findById(Order.class)** thành công để kết luận toàn bộ dữ liệu không còn phụ thuộc type hint.

### Tình huống C — Đổi @TypeAlias trong phiên bản mới

Phiên bản A ghi **_class: "card-v1"**, phiên bản B chỉ biết **@TypeAlias("card-v2")**. Các document cũ không tự đổi alias.

**Cách xử lý:** quản lý phiên bản schema, đảm bảo reader hỗ trợ mã cũ hoặc có migration trước khi loại bỏ alias; tránh để hai service đang chạy song song ghi các alias không tương thích.

### Tình huống D — Converter viết có, converter đọc không

Ứng dụng ghi **TrackingCode** thành String nhưng khi đọc cần tạo lại **TrackingCode**. Nếu thiếu **String -> TrackingCode**, việc ghi thành công không chứng minh đọc sẽ thành công.

**Cách xử lý:** đăng ký cả hai chiều cần thiết, viết test save-read bằng dữ liệu thật và test đọc trực tiếp BSON legacy. Nếu giá trị Java chứa invariant, đảm bảo reading converter kiểm tra invariant như lúc tạo mới.

### Tình huống E — Converter có nhưng không chạy

Team đã viết đúng **@ReadingConverter**, nhưng một **MongoTemplate** được tạo thủ công, không dùng bean **MongoCustomConversions** có converter đó.

**Cách xử lý:** xác định bean MongoTemplate được inject trong service, các bean MongoConverter, MongoMappingContext tương ứng và cấu hình auto-configuration. Hạn chế tạo converter riêng lẻ nếu không có lý do và test rõ sự thống nhất giữa repository/MongoTemplate/reactive.

### Tình huống F — DTO projection bị hiểu nhầm là entity mapping

Repository trả về projection hoặc DTO mà constructor/property không phù hợp với các trường được chọn. Lỗi có thể xuất hiện dù entity gốc vẫn đọc bình thường.

**Cách xử lý:** xác định lỗi xảy ra khi materialize **entity**, **projection** hay DTO từ aggregation. Kiểm tra alias các field trong kết quả **$project**, signature constructor và quy tắc property mapping. Không sửa **_class** của entity khi nguyên nhân nằm ở projection.

## 10. Viết test ngăn lỗi mapping tái diễn

Đối với lỗi kiểu dữ liệu hoặc alias, test hiệu quả nhất thường cần ít nhất một **raw BSON fixture** giống dữ liệu đã phát sinh lỗi. Mock repository không chạy **MappingMongoConverter**, vì vậy mock chỉ kiểm tra logic service, không thể chứng minh mapping đúng.

### 10.1. Unit test converter độc lập

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TrackingCodeConverterTest {

    @Test
    void convertsBothDirections() {
        TrackingCode value =
            new TrackingCodeReadConverter().convert("VN-TRK-001");

        assertEquals(new TrackingCode("VN-TRK-001"), value);
        assertEquals(
            "VN-TRK-001",
            new TrackingCodeWriteConverter().convert(value)
        );
    }

    @Test
    void rejectsInvalidLegacyValue() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new TrackingCodeReadConverter().convert(" ")
        );
    }
}
~~~

Test này không cần MongoDB. Nó kiểm tra nội dung converter, **chưa kiểm tra Spring đã đăng ký converter** hoặc data mapping có gọi converter đúng chỗ.

### 10.2. Integration test đọc raw BSON qua MappingMongoConverter

Ví dụ với Spring Boot 3.x, **@DataMongoTest** và một MongoDB test đã được cấu hình đúng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoValueConversionConfig.class)
class ShipmentMappingIntegrationTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void readsLegacyTrackingCodeStoredAsString() {
        String id = "SHIP-" + UUID.randomUUID();
        Document raw = new Document("_id", id)
            .append("trackingCode", "VN-TRK-001");

        mongoTemplate.getCollection("shipments").insertOne(raw);

        Shipment shipment =
            mongoTemplate.findById(id, Shipment.class);

        assertNotNull(shipment);
        assertEquals(
            new TrackingCode("VN-TRK-001"),
            shipment.trackingCode()
        );
    }

    @Test
    void writingUsesStableBsonStringFormat() {
        String id = "SHIP-" + UUID.randomUUID();
        mongoTemplate.save(new Shipment(
            id, new TrackingCode("VN-TRK-002")
        ));

        Document raw = mongoTemplate.getCollection("shipments")
            .find(new Document("_id", id))
            .first();

        assertNotNull(raw);
        assertEquals("VN-TRK-002", raw.getString("trackingCode"));
    }
}
~~~

**Lưu ý về test:** **@DataMongoTest** là slice test của Spring, nhưng không tự tạo MongoDB server trong mọi môi trường. Cần cung cấp database test bằng Testcontainers, instance kiểm thử được quản lý hoặc cơ chế phù hợp với phiên bản Boot. Phần **@Import** nhằm bảo đảm cấu hình converter có mặt trong test slice; việc đăng ký tự động trong ứng dụng production cần được kiểm tra riêng.

### 10.3. Test type alias và constructor

Với các entity có subtype, cần có fixture mô phỏng cả:

- Root document có **_class** đầy đủ.
- Root document có alias, ví dụ **"payment-v1"**.
- Nested document có alias, ví dụ **"card-source-v1"**.
- Document legacy thiếu field tùy chọn.
- Document có **_class** kiểu cũ trước khi migrate.
- Document có BSON type lạ (ví dụ String thay vì số hoặc subdocument thay vì scalar).

Chạy test **read** trên những fixture này; chỉ kiểm tra việc **save rồi find** bằng dữ liệu mới là chưa đủ để chứng minh khả năng đọc dữ liệu cũ.

Với immutable class dùng constructor có invariant, nên test cả **điều kiện hợp lệ** và **đầu vào bị thiếu/sai kiểu**. Nếu invariant phải từ chối dữ liệu sai, test nên xác minh lỗi xuất hiện rõ ràng thay vì trông đợi Spring tự sửa giá trị.

### 10.4. Khi nào cần kiểm tra với MongoDB thật?

| Điều muốn chứng minh | Unit test đủ? | Integration test cần? |
| --- | --- | --- |
| Hàm **TrackingCodeReadConverter.convert** cho kết quả đúng | Có | Không bắt buộc |
| **MongoCustomConversions** được Spring sử dụng | Chưa | Có ích, nên kiểm tra |
| **@Field** ánh xạ đúng trường BSON | Không nếu chỉ mock | Có |
| **@TypeAlias** nhận diện khi đọc lần đầu sau khởi động | Không nếu chỉ mock | Có |
| **Invoice** được tạo từ BSON legacy và constructor thực | Không nếu chỉ mock | Có |
| Update/aggregation trả đúng entity/projection | Không nếu chỉ mock | Có |
| Dữ liệu cũ đọc được sau migration trong môi trường tương thích | Không | Có, nên dùng fixture thực tế đã ẩn danh |

## 11. Checklist khi xử lý lỗi production

1. **Xác nhận lỗi ở tầng nào:** server/driver, mapping converter, constructor, projection hay logic nghiệp vụ sau khi đọc.
2. **Lấy exception gốc:** xem **Caused by**, property, class, constructor hoặc cặp source/target converter.
3. **Đọc raw BSON an toàn:** kiểm tra tên trường, kiểu giá trị, **_id**, **_class**, nested type hint mà không log dữ liệu nhạy cảm.
4. **So khớp schema:** property Java, **@Field**, nullability, record component và constructor parameters.
5. **Kiểm tra metadata Java:** **@PersistenceCreator**, cờ **-parameters**, static factory và runtime classpath.
6. **Kiểm tra type hint:** package/class cũ, alias bị đổi, mapping context chưa đăng ký subtype.
7. **Kiểm tra converter:** signature read/write, annotation hướng, registration và MongoConverter thực tế đang được dùng.
8. **Sửa đúng lớp:** bổ sung mapping tương thích, converter đúng cặp loại hoặc migration dữ liệu nếu cần.
9. **Viết fixture hồi quy:** lưu BSON trước khi sửa, test đọc thành công, test ghi schema mới và thử dữ liệu lỗi có chủ đích.
10. **Triển khai có kiểm soát:** phân tích tác động tới phiên bản ứng dụng khác, backup, batch migration, giám sát lỗi mapping sau deploy.

### Câu hỏi tự kiểm tra

**1. Repository tìm thấy document nhưng vẫn ném MappingInstantiationException, có chắc MongoDB bị lỗi không?** Không. Driver có thể đã đọc BSON thành công, nhưng **MappingMongoConverter** không dựng được instance Java do constructor, tham số hoặc dữ liệu sai.

**2. Có thể đổi parameter Java thành tên field BSON để sửa constructor mapping không?** Thông thường không nên. Mapper dựa vào **property Java**, còn tên BSON được khai báo qua **@Field** và metadata tương ứng.

**3. Vì sao dữ liệu không có _class đôi khi vẫn đọc được?** Vì caller đã cung cấp một kiểu Java đích cụ thể. Với field interface/abstract hoặc subtype cần phân biệt, thiếu type hint có thể gây lỗi.

**4. Đã dùng @TypeAlias thì Spring luôn tìm được subtype khi đọc document đầu tiên?** Chưa chắc. Mapping context phải biết concrete subtype; cần xem entity scanning hoặc initial entity set.

**5. Viết @ReadingConverter rồi thêm @Component có đủ để MongoTemplate sử dụng không?** Không nên giả định. Custom converters phải được đăng ký vào cơ chế **MongoCustomConversions** được converter thực sự sử dụng.

**6. Test save rồi find bằng entity mới có chứng minh đọc được BSON legacy không?** Không. Cần kiểm thử riêng raw fixture chứa hình dạng BSON cũ.

**7. Tắt toàn bộ _class có phải cách tốt nhất để xử lý package đổi tên?** Không. Nó có thể làm mất thông tin subtype; cần phân tích cách đọc polymorphism và lên phương án tương thích/migration.

## Kết luận

Các lỗi **mapping constructor, _class, @TypeAlias và converter bị thiếu** thường xuất hiện khi Java model, metadata mapping và BSON đã lưu không còn khớp. Trong Spring Data MongoDB, cách chẩn đoán có hiệu quả là **đọc raw Document**, xác định đúng **class đích và constructor**, kiểm tra **type hint/alias**, rồi so khớp **source BSON type với converter đọc/ghi**. Sau khi sửa, cần test cả dữ liệu mới lẫn fixture cũ bằng **MappingMongoConverter** và MongoDB test phù hợp, đặc biệt khi ứng dụng có record, immutable object, polymorphism hoặc nhiều phiên bản cùng truy cập collection.

### Tài liệu tham khảo

- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Type Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/converters-type-mapping.html)
- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html)
