# Chuyển đổi từng thuộc tính bằng @ValueConverter

Trong một ứng dụng Java, một thuộc tính của entity đôi khi dùng kiểu dữ liệu miền riêng thay vì kiểu nguyên thủy. Ví dụ, số điện thoại có thể được biểu diễn bằng lớp PhoneNumber, mã tiền tệ bằng CurrencyCode, hoặc trạng thái đơn hàng bằng kiểu OrderStatus. Khi lưu entity vào Elasticsearch, ứng dụng có thể muốn biểu diễn những kiểu này dưới dạng chuỗi, số hoặc cấu trúc dữ liệu mà Elasticsearch hiểu được.

Spring Data Elasticsearch cung cấp annotation @ValueConverter để gắn một bộ chuyển đổi vào một thuộc tính cụ thể. Converter chuyển giá trị Java thành giá trị có thể lưu trong Elasticsearch khi ghi, rồi chuyển ngược lại khi đọc. Điểm quan trọng là converter chỉ áp dụng cho property được đánh dấu, kể cả khi những property khác có cùng kiểu Java.

Ví dụ, cùng kiểu PhoneNumber có thể được lưu dưới dạng E.164 trong một field, còn một property khác của cùng kiểu vẫn giữ cách biểu diễn khác. Đây là trường hợp @ValueConverter hữu ích hơn một converter toàn cục theo kiểu dữ liệu.

## 1. @ValueConverter giải quyết vấn đề gì?

MappingElasticsearchConverter là thành phần Spring Data Elasticsearch dùng để chuyển entity Java thành document và khôi phục entity từ document. Nó đọc mapping metadata, bao gồm các annotation như @Document, @Id, @Field và các custom conversions.

Khi một kiểu Java cần cách biểu diễn riêng ở một property, có hai lựa chọn thường gặp:

- Đăng ký Converter trong ElasticsearchCustomConversions. Quy tắc này áp dụng theo cặp kiểu nguồn và kiểu đích trong mapping context, nên mọi property phù hợp có thể chịu cùng quy tắc.
- Gắn @ValueConverter lên property. Quy tắc chỉ áp dụng cho property đó, không tự động áp dụng cho tất cả property có cùng kiểu Java.

Ví dụ, entity có hai trường cùng kiểu PhoneNumber:

~~~java
public class CustomerDocument {

    private PhoneNumber primaryPhone;
    private PhoneNumber importedPhone;
}
~~~

Ứng dụng có thể muốn lưu primaryPhone ở định dạng E.164, còn importedPhone cần giữ một quy tắc biểu diễn khác để tương thích với dữ liệu nhập từ hệ thống cũ. Converter gắn ở từng property giúp thể hiện rõ sự khác biệt này.

Theo tài liệu Spring Data Elasticsearch, @ValueConverter định nghĩa class converter cho property được đánh dấu. Khác với converter được đăng ký toàn cục, nó chỉ chuyển đổi property đó, không chuyển đổi mọi property có cùng kiểu dữ liệu.

## 2. Vị trí của converter trong quá trình mapping

Khi ghi một entity, converter property tham gia vào bước Spring Data tạo document:

~~~text
Entity Java
    |
    v
Mapping metadata của Spring Data
    |
    v
Đọc property có @ValueConverter
    |
    v
PropertyValueConverter.write(...)
    |
    v
Giá trị native của Elasticsearch
    |
    v
Document JSON và Elasticsearch client
~~~

Khi đọc document, converter chạy theo chiều ngược lại:

~~~text
Document từ Elasticsearch
    |
    v
Giá trị đã lưu của property
    |
    v
PropertyValueConverter.read(...)
    |
    v
Giá trị Java của property
    |
    v
Entity Java
~~~

Hai phương thức có vai trò riêng:

| Phương thức | Hướng chuyển đổi | Ví dụ |
| --- | --- | --- |
| write(Object value) | Giá trị Java sang giá trị Elasticsearch | PhoneNumber thành chuỗi +84901234567 |
| read(Object value) | Giá trị Elasticsearch sang giá trị Java | Chuỗi +84901234567 thành PhoneNumber |

Converter cần có khả năng đọc lại định dạng mà nó đã ghi. Nếu chỉ triển khai đúng chiều ghi mà không xử lý chiều đọc, thao tác đọc entity có thể lỗi hoặc tạo ra giá trị không đúng.

## 3. Khai báo một PropertyValueConverter

@ValueConverter nhận class triển khai interface PropertyValueConverter trong package:

~~~java
org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter
~~~

Trong API Spring Data Elasticsearch hiện hành, interface cung cấp hai phương thức read và write, mỗi phương thức nhận và trả về một Object.

Ví dụ dưới đây dùng PhoneNumber làm kiểu miền:

~~~java
public final class PhoneNumber {

    private final String e164;

    private PhoneNumber(String e164) {
        if (e164 == null || !e164.startsWith("+")) {
            throw new IllegalArgumentException(
                "Phone number must use an international format"
            );
        }
        this.e164 = e164;
    }

    public static PhoneNumber of(String e164) {
        return new PhoneNumber(e164);
    }

    public String toE164() {
        return e164;
    }
}
~~~

Converter:

~~~java
import org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter;

public final class PhoneNumberValueConverter
        implements PropertyValueConverter {

    @Override
    public Object write(Object value) {
        if (!(value instanceof PhoneNumber)) {
            throw new IllegalArgumentException(
                "Expected a PhoneNumber value"
            );
        }

        PhoneNumber phoneNumber = (PhoneNumber) value;
        return phoneNumber.toE164();
    }

    @Override
    public Object read(Object value) {
        if (!(value instanceof String)) {
            throw new IllegalArgumentException(
                "Expected a stored phone number string"
            );
        }

        return PhoneNumber.of((String) value);
    }
}
~~~

Ở chiều ghi, converter lấy giá trị PhoneNumber và trả về chuỗi E.164. Ở chiều đọc, converter nhận chuỗi từ document và tạo lại PhoneNumber.

Converter nên tập trung vào chuyển đổi giá trị. Không nên để nó thực hiện truy vấn mạng, đọc file, gọi repository hoặc chứa logic nghiệp vụ phụ thuộc vào request hiện tại. Một converter đơn giản, xác định và không giữ trạng thái mutable sẽ dễ dùng và dễ kiểm thử hơn.

### 3.1. Quy tắc về constructor và khởi tạo

Theo API của @ValueConverter, nếu converter là class thông thường, class phải có constructor không tham số để framework có thể tạo instance. Nếu dùng enum làm singleton converter, enum chỉ được có đúng một phần tử.

Ví dụ converter dạng enum:

~~~java
public enum PhoneNumberValueConverter
        implements PropertyValueConverter {

    INSTANCE;

    @Override
    public Object write(Object value) {
        return ((PhoneNumber) value).toE164();
    }

    @Override
    public Object read(Object value) {
        return PhoneNumber.of((String) value);
    }
}
~~~

Với class thông thường, dùng constructor không tham số:

~~~java
public class PhoneNumberValueConverter
        implements PropertyValueConverter {

    public PhoneNumberValueConverter() {
    }

    // read và write
}
~~~

Không nên mặc định rằng converter được khai báo trong annotation sẽ tự động được Spring inject như một bean @Component. Cơ chế factory mặc định có thể khởi tạo converter bằng constructor không tham số. Nếu converter cần dependency từ Spring, cần cấu hình PropertyValueConverterFactory hoặc registry phù hợp với phiên bản Spring Data đang sử dụng; tài liệu API có factory hỗ trợ BeanFactory.

## 4. Gắn converter vào property bằng @ValueConverter

Sau khi có converter, gắn annotation vào đúng field cần chuyển đổi:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.ValueConverter;

@Document(indexName = "contacts")
public class ContactDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    @ValueConverter(PhoneNumberValueConverter.class)
    private PhoneNumber phoneNumber;

    // Constructors, getters và setters
}
~~~

Ở đây có hai cấu hình khác nhau:

- @ValueConverter chuyển giá trị Java của property thành chuỗi E.164 và ngược lại.
- @Field(type = FieldType.Keyword) khai báo kiểu mapping Elasticsearch cho field được lưu dưới dạng chuỗi cần so khớp chính xác.

Converter không thay thế mapping. Nó quyết định giá trị được biểu diễn như thế nào; @Field hoặc mapping JSON quyết định cách Elasticsearch lập chỉ mục giá trị đó.

Với document có số điện thoại +84901234567, phần _source có thể có dạng:

~~~json
{
  "id": "contact-1001",
  "phoneNumber": "+84901234567"
}
~~~

Trong Java, thuộc tính vẫn có kiểu PhoneNumber. Ứng dụng không cần đổi kiểu domain thành String chỉ vì Elasticsearch lưu field dưới dạng chuỗi.

## 5. Một kiểu Java, nhiều cách chuyển đổi ở các property khác nhau

Đây là lợi ích quan trọng nhất của @ValueConverter: phạm vi chuyển đổi là property.

Ví dụ, cả hai thuộc tính đều dùng kiểu PhoneNumber, nhưng có thể được lưu khác nhau:

~~~java
@Document(indexName = "contacts")
public class ContactDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    @ValueConverter(E164PhoneNumberConverter.class)
    private PhoneNumber primaryPhone;

    @Field(type = FieldType.Keyword)
    @ValueConverter(DigitsOnlyPhoneNumberConverter.class)
    private PhoneNumber legacyPhone;
}
~~~

E164PhoneNumberConverter có thể lưu chuỗi như +84901234567; DigitsOnlyPhoneNumberConverter có thể lưu chuỗi chữ số như 84901234567. Cả hai converter vẫn khôi phục về cùng kiểu Java PhoneNumber.

Điều này hữu ích khi:

- Một property cần chuẩn hóa trước khi lập chỉ mục, property khác cần giữ định dạng cũ.
- Hai nguồn dữ liệu có quy ước lưu trữ khác nhau.
- Một kiểu value object được dùng ở nhiều nơi nhưng không phải mọi nơi đều cần cùng cách biểu diễn.
- Cần thay đổi format một field mà không ảnh hưởng các property khác cùng kiểu Java.

Khi dùng nhiều converter, tên class nên mô tả rõ quy tắc lưu trữ. Tránh đặt tên chung chung như StringConverter, vì sau này khó biết converter đang chuẩn hóa theo chuẩn nào.

## 6. Chọn kiểu mapping phù hợp với giá trị sau chuyển đổi

@ValueConverter không tự khai báo mapping type cho Elasticsearch. Kiểu field cần phù hợp với giá trị mà write trả về.

| Giá trị converter trả về | Mapping thường phù hợp | Ví dụ |
| --- | --- | --- |
| String dùng để so khớp chính xác | keyword | Mã định danh, số điện thoại chuẩn hóa |
| String cần tìm kiếm toàn văn | text | Mô tả, nội dung |
| Long hoặc Integer | long hoặc integer | Số lượng, mã số thực sự có ý nghĩa số học |
| Double hoặc BigDecimal được biểu diễn thành kiểu số tương thích | double, scaled_float hoặc kiểu số phù hợp | Giá trị đo, điểm số |
| Boolean | boolean | Cờ trạng thái |
| Map hoặc object có cấu trúc | object hoặc nested tùy yêu cầu truy vấn | Một value object có nhiều thành phần |

Ví dụ, nếu PhoneNumberValueConverter.write() trả về chuỗi, field nên được khai báo là keyword khi ứng dụng cần tìm chính xác số điện thoại:

~~~java
@Field(type = FieldType.Keyword)
@ValueConverter(PhoneNumberValueConverter.class)
private PhoneNumber phoneNumber;
~~~

Nếu converter trả về một chuỗi nhưng field lại được mapping là kiểu số, Elasticsearch có thể từ chối document hoặc xử lý dữ liệu không theo ý định. Ngược lại, chọn text cho một mã cần so khớp chính xác có thể làm thay đổi hành vi truy vấn do analyzer tách token.

Với converter trả về cấu trúc Map, cần xác định rõ mapping object và các field con. Nếu chỉ cần một giá trị scalar, không nên trả về cấu trúc phức tạp không cần thiết.

## 7. Chuyển đổi một value object thành chuỗi

Một ví dụ khác là CurrencyCode. Trong domain, ứng dụng có thể dùng một kiểu riêng để tránh truyền chuỗi tùy ý:

~~~java
public final class CurrencyCode {

    private final String code;

    private CurrencyCode(String code) {
        this.code = code;
    }

    public static CurrencyCode of(String code) {
        if (code == null || code.length() != 3) {
            throw new IllegalArgumentException(
                "Currency code must contain three characters"
            );
        }
        return new CurrencyCode(code.toUpperCase());
    }

    public String value() {
        return code;
    }
}
~~~

Converter:

~~~java
import org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter;

public class CurrencyCodeValueConverter
        implements PropertyValueConverter {

    @Override
    public Object write(Object value) {
        return ((CurrencyCode) value).value();
    }

    @Override
    public Object read(Object value) {
        return CurrencyCode.of((String) value);
    }
}
~~~

Entity:

~~~java
@Field(type = FieldType.Keyword)
@ValueConverter(CurrencyCodeValueConverter.class)
private CurrencyCode currency;
~~~

Document lưu currency thành chuỗi như USD, còn code Java vẫn làm việc với CurrencyCode. Các thao tác kiểm tra hợp lệ của currency được tập trung trong value object, trong khi converter chỉ chuyển đổi giữa hai cách biểu diễn.

## 8. Chuyển đổi kiểu enum hoặc trạng thái nghiệp vụ

Một enum có thể được lưu theo tên, mã ổn định hoặc một giá trị rút gọn. Ví dụ:

~~~java
public enum OrderStatus {
    CREATED,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Nếu lưu trực tiếp enum theo tên, Spring Data có thể đã xử lý kiểu này theo quy tắc mặc định. Tuy nhiên, khi cần lưu mã ổn định như C, P, S, X, có thể dùng converter riêng:

~~~java
import org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter;

public class OrderStatusValueConverter
        implements PropertyValueConverter {

    @Override
    public Object write(Object value) {
        OrderStatus status = (OrderStatus) value;
        switch (status) {
            case CREATED:
                return "C";
            case PAID:
                return "P";
            case SHIPPED:
                return "S";
            case CANCELLED:
                return "X";
            default:
                throw new IllegalArgumentException("Unsupported status");
        }
    }

    @Override
    public Object read(Object value) {
        String code = (String) value;
        switch (code) {
            case "C":
                return OrderStatus.CREATED;
            case "P":
                return OrderStatus.PAID;
            case "S":
                return OrderStatus.SHIPPED;
            case "X":
                return OrderStatus.CANCELLED;
            default:
                throw new IllegalArgumentException(
                    "Unknown order status code: " + code
                );
        }
    }
}
~~~

Gắn converter:

~~~java
@Field(type = FieldType.Keyword)
@ValueConverter(OrderStatusValueConverter.class)
private OrderStatus status;
~~~

Lợi ích của mã ổn định là có thể đổi tên enum constant trong Java mà không nhất thiết phải đổi dữ liệu lưu trữ. Tuy nhiên, khi thay đổi mã lưu trữ, cần bảo đảm converter vẫn đọc được dữ liệu cũ hoặc có kế hoạch chuyển đổi document.

## 9. Giá trị null và lỗi chuyển đổi

Converter cần tuân theo hợp đồng API của phiên bản Spring Data Elasticsearch đang sử dụng. Trong API hiện hành, read và write nhận giá trị khác null và phải trả về giá trị khác null. Vì vậy:

- Không viết converter với giả định nó luôn nhận null.
- Không trả null để biểu thị một chuyển đổi thất bại.
- Xác định rõ property null được xử lý thế nào trong mapping của ứng dụng.
- Nếu dữ liệu lưu trữ không hợp lệ, nên báo lỗi có thông tin đủ để tìm document và field gây lỗi.

Ví dụ, nếu converter mong đợi chuỗi nhưng document cũ chứa một object JSON, không nên âm thầm gọi toString() rồi tạo một PhoneNumber sai định dạng. Nên kiểm tra kiểu dữ liệu và phát sinh lỗi rõ ràng.

Trong các phiên bản Spring Data Commons khác nhau, interface PropertyValueConverter có thể có thêm generic type và conversion context hoặc hook xử lý null. Hãy dùng đúng chữ ký trong Javadoc của phiên bản dependency mà dự án đang chạy. Không sao chép chữ ký từ tài liệu phiên bản khác mà chưa đối chiếu.

### 9.1. Khi dữ liệu cũ không còn cùng format

Giả sử trước đây phoneNumber lưu số dạng 0901234567, nhưng phiên bản mới lưu theo E.164 là +84901234567. Converter đọc mới cần biết cách xử lý document cũ.

Có thể chọn một trong các hướng:

1. Viết logic đọc tương thích cả hai format trong một giai đoạn chuyển tiếp.
2. Reindex hoặc cập nhật document cũ sang format mới.
3. Tạo index phiên bản mới, chuyển dữ liệu và đổi alias sau khi xác nhận.

Không nên để converter đoán format một cách mơ hồ. Quy tắc đọc cần có tính xác định và được kiểm tra bằng dữ liệu đại diện.

## 10. @ValueConverter và ElasticsearchCustomConversions khác nhau thế nào?

Hai cơ chế đều thuộc mapping/conversion của Spring Data Elasticsearch, nhưng phạm vi áp dụng khác nhau.

| Tiêu chí | @ValueConverter | ElasticsearchCustomConversions |
| --- | --- | --- |
| Phạm vi | Property được đánh dấu | Theo cặp kiểu nguồn/đích trong mapping context |
| Interface | PropertyValueConverter | Spring Converter<S, T> |
| Hai chiều | Một converter có write và read | Thường khai báo converter đọc và ghi riêng |
| Đăng ký | Gắn class converter lên property | Đăng ký converter trong custom conversions |
| Phù hợp khi | Chỉ một hoặc vài property cần format riêng | Mọi property của kiểu đó nên dùng chung quy tắc |

Ví dụ, nếu mọi thuộc tính CurrencyCode trong ứng dụng đều phải chuyển thành chuỗi theo cùng một quy tắc, converter toàn cục có thể phù hợp hơn. Nếu chỉ billingCurrency cần cách biểu diễn đặc biệt còn reportingCurrency dùng quy tắc khác, @ValueConverter cho từng property rõ ràng hơn.

Không nên đăng ký đồng thời converter toàn cục và property converter cho cùng một trường mà không hiểu thứ tự ưu tiên của mapping context. Khi hai cơ chế cùng có khả năng chuyển đổi một giá trị, hãy kiểm tra converter thực tế được áp dụng trong phiên bản đang dùng.

## 11. @ValueConverter và @Field có trách nhiệm khác nhau

@ValueConverter không làm các việc sau:

- Đổi tên field trong Elasticsearch.
- Chọn analyzer hoặc normalizer.
- Chọn text, keyword, date, nested hoặc kiểu mapping khác.
- Định nghĩa dynamic templates.
- Thay thế việc tạo index và mapping.

Những việc đó thuộc mapping metadata, @Field, mapping JSON hoặc cấu hình index của Elasticsearch.

Ví dụ:

~~~java
@Field(name = "phone_e164", type = FieldType.Keyword)
@ValueConverter(PhoneNumberValueConverter.class)
private PhoneNumber phoneNumber;
~~~

Trong đó:

- name = phone_e164 đặt tên field trong document.
- type = FieldType.Keyword chọn kiểu mapping.
- PhoneNumberValueConverter chuyển đổi giá trị property.

Ba thiết lập phối hợp với nhau nhưng không thay thế nhau.

## 12. Ảnh hưởng tới truy vấn

Khi query theo property đã gắn @ValueConverter, giá trị truy vấn cần có cùng cách biểu diễn với giá trị được lưu.

Spring Data Elasticsearch có API ElasticsearchConverter.updateQuery(query, domainClass) để cập nhật tên field và chuyển đổi giá trị query theo metadata của domain class. Khi property có PropertyValueConverter và query đi qua luồng mapping này với domain type phù hợp, Spring Data có thể chuyển giá trị truy vấn sang dạng lưu trữ.

Ví dụ repository:

~~~java
public interface ContactRepository
        extends ElasticsearchRepository<ContactDocument, String> {

    Optional<ContactDocument> findByPhoneNumber(PhoneNumber phoneNumber);
}
~~~

Với PhoneNumberValueConverter, query method được xử lý qua hạ tầng Spring Data có thể dùng giá trị E.164 tương ứng khi tạo truy vấn cho property.

Tuy nhiên, khi tự xây dựng JSON query ở tầng Elasticsearch Java API Client hoặc gửi request DSL trực tiếp, ứng dụng phải tự cung cấp giá trị đúng định dạng đã lưu. Không nên giả định mọi truy vấn thô đều đi qua MappingElasticsearchConverter.

Khi truy vấn không trả kết quả như mong đợi:

1. Đọc document trong _source để xác nhận giá trị được lưu.
2. Kiểm tra mapping của field.
3. Xem query DSL thực tế sau khi Spring Data chuyển đổi.
4. Xác nhận query đang dùng đúng domain class để converter property có thể được áp dụng.
5. Nếu gọi client cấp thấp trực tiếp, tự chuẩn hóa giá trị query theo format lưu trữ.

## 13. @ValueConverter không phải Jackson serializer

Jackson serializer/deserializer xử lý JSON theo cấu hình ObjectMapper. @ValueConverter thuộc mapping metadata của Spring Data Elasticsearch và được MappingElasticsearchConverter sử dụng khi chuyển entity thành document hoặc ngược lại.

Ví dụ:

- @JsonSerialize điều khiển cách Jackson serialize property trong JSON API.
- @JsonDeserialize điều khiển cách Jackson tạo object từ JSON API.
- @ValueConverter điều khiển cách Spring Data chuyển giá trị property khi lưu và đọc Elasticsearch.

Nếu cùng một class vừa là request/response DTO vừa là Elasticsearch document, có thể cần cấu hình riêng cho hai luồng. Với hệ thống lớn, tách DTO API và document persistence thường giúp tránh việc một annotation vô tình được kỳ vọng có hiệu lực ở cả hai nơi.

## 14. Kiểm thử PropertyValueConverter

Converter là thành phần nhỏ, có thể kiểm thử độc lập mà không cần chạy Elasticsearch.

Ví dụ kiểm tra hai chiều:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PhoneNumberValueConverterTest {

    private final PhoneNumberValueConverter converter =
        new PhoneNumberValueConverter();

    @Test
    void writesPhoneNumberAsE164String() {
        PhoneNumber phoneNumber = PhoneNumber.of("+84901234567");

        Object storedValue = converter.write(phoneNumber);

        assertEquals("+84901234567", storedValue);
    }

    @Test
    void readsE164StringAsPhoneNumber() {
        Object storedValue = "+84901234567";

        PhoneNumber phoneNumber = (PhoneNumber) converter.read(storedValue);

        assertEquals("+84901234567", phoneNumber.toE164());
    }
}
~~~

Ngoài unit test cho converter, integration test nên kiểm tra:

- Entity có converter được ghi thành giá trị mong đợi trong _source.
- Đọc document tạo lại đúng kiểu Java.
- Property khác không gắn converter không bị ảnh hưởng.
- Mapping field tương thích với giá trị converter trả về.
- Derived query hoặc query qua ElasticsearchOperations dùng đúng giá trị đã chuyển đổi.
- Dữ liệu cũ hoặc không hợp lệ được xử lý theo quy tắc đã thiết kế.

Unit test xác nhận logic chuyển đổi; integration test xác nhận converter thực sự được Spring Data phát hiện và dùng trong mapping.

## 15. Các lỗi thường gặp

**Dùng Converter<S, T> thay cho PropertyValueConverter.** @ValueConverter yêu cầu class triển khai PropertyValueConverter. Converter Spring thông thường được đăng ký qua ElasticsearchCustomConversions.

**Quên chiều read.** Entity ghi thành công nhưng lỗi khi đọc lại vì converter không thể tạo kiểu Java từ giá trị lưu trữ. Hãy triển khai cả write và read.

**Gắn annotation lên sai property.** Converter chỉ áp dụng cho property được đánh dấu. Kiểm tra annotation có nằm trên field mà mapping metadata nhận diện hay không.

**Cho rằng converter áp dụng cho mọi property cùng kiểu.** @ValueConverter có phạm vi property. Nếu muốn quy tắc toàn cục, cân nhắc ElasticsearchCustomConversions.

**Không khai báo mapping type phù hợp.** Converter trả chuỗi nhưng field được map thành số hoặc kiểu khác. Kết hợp @ValueConverter với @Field hoặc mapping JSON tương thích.

**Dùng converter có dependency nhưng không có constructor phù hợp.** Converter class thông thường cần constructor không tham số với factory mặc định. Nếu cần Spring dependency, cấu hình factory/registry phù hợp với phiên bản.

**Trả null từ converter.** API hiện hành yêu cầu giá trị đầu vào và đầu ra của read/write khác null. Xử lý null theo hợp đồng mapping của ứng dụng.

**Thay đổi format ghi mà quên dữ liệu cũ.** Converter mới có thể không đọc được document cũ. Dùng logic tương thích tạm thời hoặc migration/reindex.

**Tưởng converter đổi tên field.** Tên field do @Field(name = "...") hoặc mapping JSON quyết định.

**Tưởng converter tự làm mọi query thô được chuyển đổi.** Query đi qua mapping converter có domain metadata có thể được cập nhật; request DSL cấp thấp cần tự dùng giá trị lưu trữ.

**Dùng converter để chứa logic nghiệp vụ lớn.** Converter nên là phép biến đổi dữ liệu nhỏ, ổn định và dễ kiểm thử.

## 16. Quy trình triển khai @ValueConverter

Khi cần chuyển đổi một property trong entity Spring Data Elasticsearch, thực hiện theo trình tự:

1. Xác định kiểu Java hiện tại và kiểu dữ liệu muốn lưu trong Elasticsearch.
2. Xác định property nào cần chuyển đổi; nếu mọi property cùng kiểu đều cần quy tắc giống nhau, cân nhắc custom conversions toàn cục.
3. Viết class triển khai PropertyValueConverter.
4. Cài đặt write để tạo giá trị Elasticsearch và read để khôi phục kiểu Java.
5. Đảm bảo converter đáp ứng hợp đồng null và constructor của phiên bản Spring Data.
6. Gắn @ValueConverter(ConverterClass.class) lên field cần chuyển đổi.
7. Khai báo @Field hoặc mapping JSON để chọn kiểu mapping tương thích với giá trị sau chuyển đổi.
8. Kiểm thử độc lập hai chiều chuyển đổi.
9. Kiểm thử lưu, đọc và truy vấn qua Spring Data.
10. Kiểm tra _source, mapping và query DSL thực tế.
11. Lập kế hoạch tương thích hoặc migration nếu format lưu trữ thay đổi.

## 17. Tài liệu tham khảo

- [Spring Data Elasticsearch - Elasticsearch Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): vai trò của MappingElasticsearchConverter, mapping annotations và phạm vi của @ValueConverter.
- [Spring Data Elasticsearch - ValueConverter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/ValueConverter.html): cách khai báo converter class và yêu cầu constructor.
- [Spring Data Elasticsearch - PropertyValueConverter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/mapping/PropertyValueConverter.html): hợp đồng read và write.
- [Spring Data Elasticsearch - ElasticsearchConverter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/convert/ElasticsearchConverter.html): cập nhật tên field và giá trị query theo mapping metadata.
- [Spring Data Commons - PropertyValueConverterFactory API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/PropertyValueConverterFactory.html): factory tạo converter, cache và hỗ trợ BeanFactory.

@ValueConverter có từ Spring Data Elasticsearch 4.3. Chữ ký API và cơ chế khởi tạo converter có thể khác theo phiên bản Spring Data Elasticsearch/Spring Data Commons. Khi triển khai, hãy đối chiếu Javadoc đúng với dependency của dự án.
