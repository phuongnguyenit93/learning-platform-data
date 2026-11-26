# @ReadingConverter và @WritingConverter

Trong chương **Chuyển đổi dữ liệu** của Spring Data Commons, một converter không chỉ cần biết chuyển từ kiểu nào sang kiểu nào. Hạ tầng persistence còn cần biết phép chuyển đó phục vụ chiều đọc từ kho dữ liệu hay chiều ghi xuống kho dữ liệu.

`@ReadingConverter` và `@WritingConverter` cung cấp metadata cho việc phân loại này. Chúng đặc biệt quan trọng khi kiểu nguồn và kiểu đích đều có thể là kiểu đơn giản mà kho dữ liệu hỗ trợ, khiến framework không thể suy ra một chiều duy nhất từ chữ ký converter.

Bài học trình bày abstraction dùng chung, sau đó minh họa bằng một value object lưu dưới dạng chuỗi trong Spring Data MongoDB. Cách đăng ký và tập kiểu lưu trữ được hỗ trợ vẫn phụ thuộc module; annotation của Commons không biến một cấu hình MongoDB thành cấu hình dùng chung cho JPA, JDBC và mọi kho dữ liệu khác.

## 1. Xác định chiều từ góc nhìn persistence

Hai annotation được import từ:

```java
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;
```

Chiều được hiểu từ ranh giới giữa mô hình miền và biểu diễn lưu trữ:

```text
Đọc:
    giá trị từ kho dữ liệu → giá trị trong mô hình miền

Ghi:
    giá trị trong mô hình miền → giá trị để lưu xuống kho dữ liệu
```

Ví dụ một mã sản phẩm được biểu diễn bằng value object `ProductCode` trong Java nhưng lưu bằng chuỗi:

| Chiều | Kiểu nguồn | Kiểu đích | Annotation |
| --- | --- | --- | --- |
| Đọc | `String` | `ProductCode` | `@ReadingConverter` |
| Ghi | `ProductCode` | `String` | `@WritingConverter` |

“Đọc” không có nghĩa là converter chỉ được dùng khi chạy SQL `SELECT`. “Ghi” cũng không chỉ tên một HTTP method như POST hoặc PUT. Đây là vai trò trong cơ chế chuyển đổi dữ liệu của module persistence.

Một request HTTP cập nhật có thể cần đọc dữ liệu trước rồi ghi lại sau. Hai thao tác có thể dùng hai converter khác nhau trong cùng một ca sử dụng.

## 2. Annotation không thay chữ ký Converter

Một converter thông thường triển khai hợp đồng của Spring Framework:

```java
import org.springframework.core.convert.converter.Converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

Chữ ký xác định phép chuyển từ `S` sang `T`. Annotation chỉ cung cấp vai trò đọc hoặc ghi để hạ tầng custom conversions phân loại.

Ví dụ:

```java
@ReadingConverter
class ProductCodeReadConverter implements Converter<String, ProductCode> {
    // Chuyển String thành ProductCode.
}
```

Annotation không khiến phép chuyển tự đảo chiều. Nếu cần chuyển `ProductCode` thành `String`, phải có implementation tương ứng cho chiều đó.

Tương tự, hai annotation không phải cơ chế chặn việc gọi trực tiếp phương thức `convert`. Mã Java vẫn có thể gọi converter như một đối tượng thông thường; ý nghĩa đọc hoặc ghi được hạ tầng đăng ký và mapping sử dụng.

Cần phân biệt ba việc:

1. **Implementation:** viết cách chuyển giá trị.
2. **Phân loại:** chỉ rõ chiều mà custom conversion phục vụ.
3. **Đăng ký:** đưa converter vào đúng hạ tầng mapping của module.

Thiếu một trong ba có thể làm dữ liệu không được xử lý như dự kiến.

## 3. Khi nào hạ tầng có thể suy ra chiều?

Nếu một phía là kiểu miền do ứng dụng định nghĩa và phía còn lại là kiểu được module lưu trữ hỗ trợ trực tiếp, hạ tầng thường có đủ thông tin để phân loại converter.

Ví dụ:

```text
ProductCode → String
```

Với module xem `String` là kiểu lưu trữ đơn giản, đây là hình dạng tự nhiên của một writing converter.

Chiều ngược lại:

```text
String → ProductCode
```

là hình dạng tự nhiên của một reading converter.

Dù chiều có thể được suy ra, khai báo annotation rõ ràng vẫn giúp người đọc hiểu hợp đồng của converter. Khi phân loại có thể mơ hồ, annotation còn giúp giới hạn vai trò mà phép chuyển được đăng ký phục vụ.

### 3.1. Trường hợp mơ hồ: cả hai phía đều là kiểu lưu trữ đơn giản

Xét:

```java
Converter<String, Long>
```

Nếu cả `String` và `Long` đều được module hỗ trợ như kiểu lưu trữ đơn giản, chỉ nhìn chữ ký chưa cho biết ý định:

- Đọc một chuỗi lưu sẵn thành một thuộc tính `Long` trong miền?
- Hay ghi một thuộc tính Java kiểu `String` dưới dạng số nguyên trong kho dữ liệu?

Ở đây cần công bố chiều có chủ đích:

```text
@ReadingConverter  + Converter<String, Long>
    dùng cho vai trò đọc tương ứng

@WritingConverter  + Converter<String, Long>
    dùng cho vai trò ghi tương ứng
```

Nguồn vẫn là `String`, đích vẫn là `Long` trong cả hai trường hợp. Annotation không hoán đổi chúng.

Một converter rộng như vậy có thể ảnh hưởng nhiều thuộc tính cùng kiểu trong phạm vi custom conversions của mapping converter. Nếu ý nghĩa chỉ dành cho một loại mã đặc biệt, dùng một value object riêng thường giúp giới hạn phạm vi tốt hơn một quy tắc chung cho mọi `String`.

### 3.2. “Native” phụ thuộc module

Không suy ra rằng một lớp nằm trong JDK luôn là kiểu native của mọi kho dữ liệu, hoặc một kiểu được driver này hỗ trợ sẽ được driver khác hỗ trợ giống hệt.

Tập simple types, kiểu đích được driver chấp nhận và các converter có sẵn là một phần của module cùng cấu hình mapping. Điều đó ảnh hưởng cách phân loại và cách kết quả converter được ghi thực tế.

## 4. Ví dụ value object ProductCode

Ví dụ Java sau sử dụng record, phù hợp với Java 17 trở lên. Mã sản phẩm có tối đa 32 ký tự, bắt đầu bằng chữ hoa hoặc chữ số; các ký tự còn lại có thể gồm chữ hoa, chữ số và dấu gạch ngang.

```java
package com.example.catalog;

import java.util.Objects;
import java.util.regex.Pattern;

public record ProductCode(String value) {

    private static final Pattern VALID_CODE =
            Pattern.compile("[A-Z0-9][A-Z0-9-]{0,31}");

    public ProductCode {
        Objects.requireNonNull(value, "product code must not be null");
        if (!VALID_CODE.matcher(value).matches()) {
            throw new IllegalArgumentException("invalid product code");
        }
    }
}
```

Value object không tự viết hoa hoặc cắt khoảng trắng. Thiết kế này cố ý giữ hợp đồng rõ ràng: giá trị hợp lệ được giữ nguyên; giá trị không hợp lệ bị từ chối.

Nếu nghiệp vụ muốn chuẩn hóa, cần định nghĩa quy tắc đó riêng và đánh giá tác động đến dữ liệu đã lưu, tính duy nhất và truy vấn. Không thêm một phép chuẩn hóa ngầm trong converter chỉ để làm ví dụ dễ chạy.

## 5. Writing converter: từ value object thành chuỗi

File `ProductCodeWriteConverter.java`:

```java
package com.example.catalog;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class ProductCodeWriteConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
```

Hợp đồng:

```text
ProductCode("BOOK-001") → "BOOK-001"
```

Converter không dùng `toString()` của record để ghi dữ liệu. `toString()` của một đối tượng có thể phục vụ chẩn đoán và chứa tên lớp hoặc tên thuộc tính, không phải một định dạng lưu trữ ổn định.

Giá trị được trả về phải phù hợp với kiểu lưu trữ mà module sẽ xử lý tiếp. Trong ví dụ, chuỗi là biểu diễn đã được chọn cho mã sản phẩm.

## 6. Reading converter: từ chuỗi thành value object

File `ProductCodeReadConverter.java`:

```java
package com.example.catalog;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class ProductCodeReadConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
```

Hợp đồng:

```text
"BOOK-001" → ProductCode("BOOK-001")
```

Constructor của value object kiểm tra dữ liệu đọc. Vì vậy, một bản ghi cũ chứa giá trị không hợp lệ có thể làm đường đọc thất bại. Đây là hệ quả của hợp đồng đã chọn, không phải lý do để âm thầm trả null hoặc tạo một mã giả.

Nếu hệ thống có dữ liệu lịch sử ở định dạng khác, cần có chính sách tương thích hoặc migration rõ ràng. Một reading converter có thể hỗ trợ có chủ đích nhiều định dạng, nhưng phải chỉ ra cách phân biệt chúng và khi nào hỗ trợ cũ được loại bỏ.

## 7. Hai converter phải có hợp đồng round-trip

Với một giá trị miền hợp lệ `code`, mong muốn cơ bản là:

```text
read(write(code)) tương đương code
```

Ở ví dụ:

```java
ProductCode original = new ProductCode("BOOK-001");

String stored = new ProductCodeWriteConverter().convert(original);
ProductCode restored = new ProductCodeReadConverter().convert(stored);

// restored.equals(original) là true.
```

Đây là đoạn minh họa hợp đồng chuyển đổi, chưa kiểm chứng việc đăng ký với module lưu trữ.

Chiều ngược lại cũng cần được cân nhắc:

```text
write(read(storedValue))
```

Nếu reading converter chuẩn hóa dữ liệu, kết quả có thể khác chuỗi gốc dù đối tượng miền vẫn hợp lệ. Điều đó có thể ảnh hưởng index, so sánh bằng và tính duy nhất.

Trong ví dụ không có chuẩn hóa ngầm, nên một chuỗi hợp lệ được giữ nguyên qua hai chiều. Quyết định này giúp định dạng lưu có thể dự đoán được.

### 7.1. Xử lý null là một hợp đồng khác

Hợp đồng `Converter<S, T>` của Spring Framework cung cấp nguồn không null cho lời gọi chuyển đổi thông thường qua conversion infrastructure. Việc xử lý thuộc tính null, thuộc tính bị thiếu hoặc giá trị mặc định còn phụ thuộc đường mapping và module.

Không giả định rằng converter sẽ luôn được gọi với null để tự tạo một giá trị mặc định. Cũng không xem một converter từ `String` là cách tự khôi phục một thuộc tính hoàn toàn không có trong dữ liệu.

Nếu gọi trực tiếp converter bằng mã ứng dụng, mã gọi vẫn phải tuân theo hợp đồng đầu vào. Các annotation không bổ sung một cơ chế kiểm tra null riêng.

## 8. Annotation không tự đăng ký converter

Hai lớp được đánh dấu đúng chưa đủ để mapping converter biết phải sử dụng chúng.

```text
Có lớp converter trên classpath
    ≠
Converter đã nằm trong custom conversions của module đang chạy
```

Tương tự, một bean `Converter` phục vụ Spring MVC hoặc một `ConversionService` của ứng dụng không mặc nhiên là cùng hạ tầng chuyển đổi mà Spring Data MongoDB, JDBC hoặc module khác đang dùng.

Cần đăng ký theo cơ chế của module. Khi tự xây dựng một mapping converter, còn phải đưa custom conversions vào đúng instance mapping converter được repository hoặc template sử dụng.

## 9. Cấu hình thực hành với Spring Data MongoDB

### 9.1. Đăng ký cặp converter

Ví dụ dưới dành cho ứng dụng Spring Boot dùng hạ tầng MongoDB tự cấu hình và API `MongoCustomConversions.create`. Chỉ định nghĩa một cấu hình custom conversions phù hợp với ứng dụng; nếu đã có cấu hình, hợp nhất converter vào cấu hình đó.

```java
package com.example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class MongoConversionConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new ProductCodeReadConverter());
            adapter.registerConverter(new ProductCodeWriteConverter());
        });
    }
}
```

Hai converter được đăng ký tường minh nên không cần dựa vào component scanning để tìm các lớp converter.

Nếu ứng dụng tự cấu hình `MappingMongoConverter` hoặc dùng nhiều Mongo template, phải xác định converter nào nhận được bộ custom conversions này. Một bean được tạo nhưng không nối vào template đang dùng sẽ không đổi hành vi repository tương ứng.

Không thay cấu hình converter đã có bằng một cấu hình mới mà bỏ sót các tùy biến khác của ứng dụng. Các kiểu thời gian, kiểu giá trị khác hoặc cách lưu đặc biệt vẫn cần được giữ theo yêu cầu hệ thống.

### 9.2. Entity sử dụng ProductCode

```java
package com.example.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;

import java.util.Objects;

@Document("catalog_products")
public class CatalogProduct {

    @Id
    private String id;

    private ProductCode code;
    private String name;

    @PersistenceCreator
    public CatalogProduct(String id, ProductCode code, String name) {
        this.id = id;
        this.code = Objects.requireNonNull(
                code, "code must not be null");
        this.name = Objects.requireNonNull(
                name, "name must not be null");
    }

    public String getId() {
        return id;
    }

    public ProductCode getCode() {
        return code;
    }

    public String getName() {
        return name;
    }
}
```

Khi ghi, mapping sử dụng writing converter cho giá trị `code`. Khi đọc một chuỗi cho thuộc tính kiểu `ProductCode`, reading converter cung cấp giá trị miền trước khi đối tượng được tái tạo theo đường mapping tương ứng.

Metadata tên tham số constructor và cấu hình creator vẫn cần đúng. Các annotation chuyển đổi không tự sửa một lỗi chọn constructor hoặc một tham số không liên hệ được với thuộc tính.

### 9.3. Repository

```java
package com.example.catalog;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Optional<CatalogProduct> findByCode(ProductCode code);
}
```

Cách dùng trong một service đã inject repository:

```java
CatalogProduct draft = new CatalogProduct(
        null,
        new ProductCode("BOOK-001"),
        "Spring Data Handbook");

CatalogProduct saved = repository.save(draft);
CatalogProduct loaded = repository.findById(saved.getId())
        .orElseThrow();

// loaded.getCode() là ProductCode, không phải String.
```

Phần dữ liệu nghiệp vụ trong document mong muốn có hình dạng:

```json
{
  "code": "BOOK-001",
  "name": "Spring Data Handbook"
}
```

Document còn có định danh theo mapping MongoDB. Ví dụ chỉ tập trung vào biểu diễn của `code`: một chuỗi thay vì một object lồng chứa trường `value`.

Việc đổi từ object lồng sang chuỗi là thay đổi định dạng lưu thực tế. Nếu trước đây dữ liệu đã được lưu ở dạng khác, đăng ký converter mới không tự di chuyển các document cũ.

## 10. Phạm vi converter rộng hơn một field đơn lẻ

Một converter đăng ký theo cặp kiểu có thể được áp dụng cho nhiều thuộc tính cùng kiểu trong phạm vi mapping converter đó.

Ví dụ:

```text
ProductCode → String
```

thường biểu đạt một định dạng thống nhất cho mọi thuộc tính `ProductCode` mà cấu hình này xử lý.

Nếu chỉ một field cần định dạng khác, một converter toàn cục cho `String → String` hoặc một cặp kiểu phổ biến có thể quá rộng. Cần đánh giá khả năng chuyển đổi theo property của module, một kiểu miền riêng hoặc một mô hình lưu riêng.

Không dùng `@ReadingConverter` như annotation đặt lên một field để yêu cầu chỉ field đó được xử lý. Trong mô hình đang trình bày, annotation phân loại lớp converter; nó không chỉ định tên property đích.

### 10.1. Ảnh hưởng đến truy vấn

Biểu diễn lưu ảnh hưởng tới truy vấn và index. Khi `ProductCode` lưu dưới dạng chuỗi, một truy vấn MongoDB sử dụng đường mapping thích hợp có thể cần chuyển tham số miền thành chuỗi tương ứng.

Cần kiểm chứng đường truy vấn thực tế, chẳng hạn `findByCode`, thay vì chỉ kiểm tra lưu và đọc theo ID. Không suy ra mọi raw query hoặc lời gọi driver trực tiếp đều tự dùng cùng custom conversions.

Nếu trước đây truy vấn dùng đường dẫn `code.value`, sau khi đổi sang chuỗi thì đường dẫn đó không còn phản ánh cùng cấu trúc. Tương tự, chiến lược sắp xếp và index phải phù hợp với giá trị được lưu.

Một converter không tự cập nhật schema, index hoặc mọi đoạn truy vấn đã viết trước đó.

## 11. Khác biệt với JDBC, JPA và JSON

### 11.1. Spring Data JDBC

JDBC có cơ chế custom conversions của module và tập kiểu mà driver hoặc mapping relational xử lý. Cặp converter ở mức ý tưởng có thể giống nhau, nhưng cấu hình MongoDB không được dùng thay cho cấu hình JDBC.

Một converter ghi phải trả về biểu diễn mà đường ghi JDBC chấp nhận. Khi cần thông tin kiểu SQL cụ thể hoặc xử lý một kiểu đặc biệt, có thể cần cơ chế bổ sung của JDBC thay vì chỉ giả định một chuỗi Java luôn đủ cho mọi cột.

### 11.2. JPA AttributeConverter

JPA có hợp đồng chuyển đổi riêng, chẳng hạn `jakarta.persistence.AttributeConverter` cùng cơ chế đăng ký của JPA provider.

Đặt `@ReadingConverter` hoặc `@WritingConverter` lên một Spring `Converter` không tự biến lớp đó thành JPA attribute converter cho các thuộc tính entity.

Cần xác định thành phần nào đang thực hiện mapping: mapping converter của Spring Data hay JPA provider. Tên phương thức repository giống nhau không làm hai cơ chế chuyển đổi trở thành một.

### 11.3. JSON và HTTP binding

Một JSON deserializer hoặc converter phục vụ binding request có mục tiêu khác với converter cho persistence.

Việc API nhận chuỗi `"BOOK-001"` và tạo được `ProductCode` không chứng minh MongoDB đã được cấu hình lưu value object đó thành chuỗi. Ngược lại, một reading converter của MongoDB không tự cấu hình cách Jackson tạo `ProductCode` từ JSON request.

Giữ ranh giới này rõ ràng giúp chẩn đoán đúng khi một đường hoạt động nhưng đường khác vẫn báo lỗi.

## 12. Thiết kế converter dễ kiểm soát

Một converter giá trị nên có trách nhiệm nhỏ và kết quả có thể dự đoán:

- Giữ một định dạng lưu trữ được công bố rõ ràng.
- Không gọi repository để bổ sung thông tin cho từng giá trị chuyển đổi.
- Không phát sự kiện nghiệp vụ hoặc gửi thông báo trong lúc đọc dữ liệu.
- Không giữ trạng thái mutable của lần chuyển đổi trước để quyết định lần tiếp theo.
- Báo lỗi dữ liệu không hợp lệ theo chính sách đã chọn, thay vì âm thầm tạo giá trị giả.

Converter thường được dùng lặp lại và có thể được dùng đồng thời. Các implementation không có trạng thái trong ví dụ phù hợp với cách sử dụng đó.

Nếu một phép chuyển cần biết tenant, thời điểm hiện tại hoặc một cấu hình thay đổi, phải đánh giá nguồn ngữ cảnh và tính ổn định của biểu diễn lưu. Một quy tắc phụ thuộc ngữ cảnh có thể làm cùng dữ liệu lưu được đọc thành những ý nghĩa khác nhau.

Không nên chọn converter làm nơi điều phối ca sử dụng. Nó phục vụ chuyển đổi biểu diễn, trong khi transaction và nghiệp vụ nhiều bước cần ranh giới riêng.

## 13. Những lỗi thường gặp

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Converter có annotation nhưng không được gọi | Đã đăng ký vào đúng custom conversions và mapping converter chưa? |
| Ghi được nhưng đọc lại lỗi | Có reading converter đúng chiều, đúng kiểu nguồn thực tế không? |
| Một kiểu giá trị vẫn lưu thành object lồng | Writing converter có được nhận diện và dùng ở cấu hình hiện tại không? |
| Nhiều thuộc tính String bị đổi biểu diễn ngoài dự kiến | Converter theo cặp kiểu có phạm vi quá rộng không? |
| Truy vấn không tìm thấy dữ liệu vừa lưu | Giá trị tham số, tên đường dẫn và biểu diễn lưu có thống nhất không? |
| Dữ liệu cũ đọc lỗi sau khi triển khai | Có thay đổi định dạng hoặc quy tắc validation mà chưa migration không? |
| JPA không dùng Spring Converter | Đang cần cơ chế AttributeConverter của JPA thay vì custom conversion của module khác? |
| REST hoạt động nhưng persistence lỗi | Cấu hình JSON hoặc MVC có đang bị nhầm với cấu hình mapping dữ liệu không? |

Không sửa lỗi chiều bằng cách đặt cả hai annotation lên cùng một converter rồi kỳ vọng framework tự đảo phép chuyển. Hãy viết và đăng ký hai phép chuyển riêng khi cần hai chiều.

Cũng không tự thêm nhiều converter cùng cặp kiểu mà không quyết định implementation nào là hợp đồng chính. Trùng lặp khiến hành vi khó đánh giá và có thể phụ thuộc cách đăng ký, lựa chọn converter hoặc cấu hình thực tế.

## 14. Cách kiểm chứng khi tích hợp

Hai mức kiểm chứng phục vụ hai mục đích khác nhau:

| Mức | Điều chứng minh được |
| --- | --- |
| Gọi trực tiếp converter | Logic chuyển giá trị và chính sách lỗi |
| Đi qua repository hoặc template đã cấu hình | Việc đăng ký, phân loại chiều, biểu diễn lưu và đường đọc thực tế |

Những tình huống đáng kiểm chứng:

1. Một `ProductCode` hợp lệ đi qua hai chiều vẫn tương đương giá trị gốc.
2. Giá trị lưu thực tế là chuỗi đã chọn, không phải `toString()` hoặc object lồng ngoài ý định.
3. Đọc lại tạo đúng value object và constructor nhận được kiểu phù hợp.
4. Dữ liệu sai định dạng có kết quả lỗi rõ ràng.
5. Thuộc tính null hoặc thiếu được xử lý theo hợp đồng mô hình và module.
6. Truy vấn theo `ProductCode` dùng cùng biểu diễn với dữ liệu đã ghi.
7. Converter không ảnh hưởng những kiểu hoặc mapping converter ngoài phạm vi dự kiến.
8. Bản ghi lịch sử được xử lý theo chính sách tương thích đã thiết kế.

Một phép round-trip có ích nhưng chưa đủ để phát hiện mọi lỗi định dạng. Nếu cả chiều ghi và chiều đọc cùng dùng một quy tắc sai, chúng vẫn có thể khôi phục được giá trị mà không tương thích với dữ liệu có sẵn hoặc hệ thống khác.

Vì vậy, cần có các giá trị lưu đã biết để đối chiếu, đặc biệt khi định dạng được chia sẻ giữa nhiều dịch vụ hoặc nhiều phiên bản ứng dụng.

## 15. Bài tập áp dụng

Một ứng dụng có value object `WarehouseCode`, dự định lưu bằng chuỗi. Nhóm phát triển viết `Converter<WarehouseCode, String>`, đánh dấu `@WritingConverter`, nhưng không thêm nó vào cấu hình custom conversions. Sau đó nhóm viết thêm một converter `String → Long` để phục vụ riêng một mã kho số ở một tính năng khác.

Hãy phân tích:

1. Vì sao annotation đúng vẫn chưa bảo đảm converter đầu tiên được sử dụng?
2. Cần thêm converter nào để đọc lại chuỗi thành `WarehouseCode`?
3. Vì sao cặp `String → Long` cần làm rõ vai trò đọc hoặc ghi?
4. Phạm vi của cặp kiểu phổ biến này có thể rộng hơn yêu cầu của một field như thế nào?
5. Ngoài kiểm tra gọi trực tiếp `convert`, cần kiểm chứng điều gì qua module lưu trữ?

Hướng giải quyết là đăng ký đúng cặp converter, công bố chiều của từng phép chuyển và cân nhắc value object riêng cho ý nghĩa hẹp. Kiểm tra cả hình dạng dữ liệu lưu, đường đọc và truy vấn sử dụng giá trị đó.

Khi đọc một cấu hình chuyển đổi, hãy xác định đầy đủ **kiểu nguồn, kiểu đích, chiều persistence và nơi đăng ký**. Bốn thông tin này kết hợp mới giải thích được converter sẽ tham gia vào đường dữ liệu nào.